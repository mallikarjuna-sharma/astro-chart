"""D9 (Navamsha) field-determination module.

Historically this file only exposed `score_navamsha_confirmation`, a bounded
proposition-confirmation helper (`independent_vote: False`) that required a
caller-supplied `propositions` list and never influenced `final_score` on its
own. Phase-2 remediation (2026-08): D9 is wired into the method bundle as a
genuine (bounded) +/- adjustment on the combined score, applied AFTER the
seven-method weighted blend rather than as an eighth vote -- D9 is
classically a *confirmation* chart (general fortune, marriage, and whether a
D1/D24 promise "comes true"), not a primary field-determination technique,
so giving it a full independent vote alongside D24/Dashamsha would overstate
its role. Concretely: does the field's supporting planets (from
field_affinity) sit well-dignified in D9? If yes, the combined score is
nudged up; if they are debilitated/enemy in D9, nudged down. Bounded to
+/-8% so it can shift close rankings without overriding the primary seven
methods.

Phase-3c remediation (2026-08 gap-audit): Phase-2's version only examined
planet-level D9 dignity via a synthetic proposition, missing two signals
D24's scorer already uses -- the D9 LAGNA LORD's own strength/dignity, and
D9 HOUSE LORDSHIPS for the vidya-relevant houses (4th/5th/9th) counted from
the navamsha lagna. Both are added here as additional confirmation
sub-scores, blended with the original planet-level check, still surfaced as
a single bounded multiplier (D9's confirmatory role is unchanged -- only the
evidence feeding that one number is now more complete). House-lord/lagna-
lord derivation mirrors siddhamsha.py's D24 pattern (whole-sign counting
from the divisional lagna) for consistency between the two vargas' code.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from jyotish.constants import _SIGN_LORD, _SIGN_NUM
from jyotish.boosts import _vimsopaka_bala_coefficient
from .common import is_vargottama  # gap fix 2026-08-18 (I): shared Vargottama check

# Confirmation multiplier bounds (Phase-2 remediation).
# §6 fix: spec (Full Methodology Spec §6) requires the D9 sustainability
# multiplier to range 0.85 (afflicted) to 1.15 (own/exalted/strong), with the
# explicit guarantee that "a D1 signal that collapses in D9 should never
# carry more than a 0.85-0.90 multiplier into the composite." The previous
# 0.92-1.08 band made that guarantee structurally impossible (floor never
# went below 0.92). Widened to match the spec's exact range.
_D9_MULT_MIN = 0.85
_D9_MULT_MAX = 1.15

# §11 remediation (2026-08-19): filter 1 ("core-three D9-collapse
# exclusion"). Severely-collapsed threshold on the 0-100 blended D9
# confirmation score (well below the 50 neutral midpoint -- this is deep
# affliction territory, distinct from merely "below average"), and the
# extra heavy-downrank multiplier applied on top of the ordinary bounded
# band when it fires. See score_navamsha_adjustment()'s d9_collapse_exclusion
# block below for the full rationale.
_D9_COLLAPSE_SCORE_THRESHOLD = 25.0
_D9_COLLAPSE_REJECT_MULT = 0.65

# Dignity -> 0-100 confirmation-strength scale (Phase-3c). Mirrors
# siddhamsha.py's STRONG map's ordering/intent, expressed on the 0-100 scale
# this module already uses for its blended sub-scores.
_DIGNITY_SCORE = {
    "EXALTED": 100.0, "OWN": 85.0, "OWN_SIGN": 85.0, "MOOLATRIKONA": 90.0,
    "FRIEND": 65.0, "NEUTRAL": 50.0, "ENEMY": 30.0, "DEBILITATED": 10.0,
}

# Houses relevant to education (same convention as siddhamsha.py's
# _VIDYA_HOUSES): 4th (early/formal education), 5th (intelligence, higher
# learning), 9th (higher wisdom, guru, advanced study).
_VIDYA_HOUSES = (4, 5, 9)

_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


def _d9_house_lord(d9_lagna: str, house_num: int) -> str:
    """Lord of the Nth house in D9 using whole-sign house system."""
    if not d9_lagna or d9_lagna not in _SIGN_NUM:
        return ""
    lagna_idx = _SIGN_NUM[d9_lagna] - 1
    target_idx = (lagna_idx + house_num - 1) % 12
    return _SIGN_LORD.get(_SIGN_ORDER[target_idx], "")


def _d9_house_num(sign: str, d9_lagna: str) -> int:
    """Whole-sign house number of `sign` counted from the D9 lagna (1-12), 0 if unknown."""
    if not sign or not d9_lagna or sign not in _SIGN_NUM or d9_lagna not in _SIGN_NUM:
        return 0
    return ((_SIGN_NUM[sign] - _SIGN_NUM[d9_lagna]) % 12) + 1


# D9 gap-audit fix (2026-08), addition 1 of 3: D9-internal house placement.
# Previously the lagna-lord/vidya-house-lord checks below scored ONLY sign
# dignity (exalted/own/debilitated) -- never whether that lord actually SITS
# in a kendra/trikona/dusthana of D9 itself. Sign dignity and house placement
# are classically distinct strength axes (Parashara's D1 methods already
# separate them -- e.g. _h10_lord_strength_bonus vs _h10_lord_trikona_bonus);
# D9 had only the first. This multiplier folds placement into the existing
# 0-100 dignity score before blending, at a deliberately modest range so it
# nudges rather than dominates the sign-dignity signal.
_KENDRA = {1, 4, 7, 10}
_TRIKONA = {5, 9}
_DUSTHANA = {6, 8, 12}


def _d9_placement_mult(house_num: int) -> float:
    if house_num in _KENDRA:
        return 1.15
    if house_num in _TRIKONA:
        return 1.10
    if house_num in _DUSTHANA:
        return 0.85
    return 1.0


def score_navamsha_confirmation(payload: Any, propositions: Iterable[Mapping]) -> dict:
    """Legacy proposition-confirmation entry point, preserved unchanged for
    any existing caller that supplies its own propositions list."""
    digs = getattr(payload, "d9_planet_dignities", {}) or {}
    rows = []
    total = weighted = 0.0
    if not digs:
        return {"contract_version": "d9-confirmation.v1", "status": "MISSING", "score": None, "independent_vote": False, "confirmations": []}
    for item in propositions or []:
        planets = list(item.get("supporting_planets") or [])
        weight = max(0.0, float(item.get("weight", 1) or 1))
        states = [str(digs.get(p, "NEUTRAL")).upper() for p in planets]
        pos = sum(s in {"EXALTED", "OWN", "OWN_SIGN", "MOOLATRIKONA", "VARGOTTAMA"} for s in states)
        neg = sum(s in {"DEBILITATED", "ENEMY", "MRITA"} for s in states)
        value = 0.0 if not states else max(-1.0, min(1.0, (pos - neg) / len(states)))
        weighted += value * weight
        total += weight
        rows.append({"proposition_id": item.get("proposition_id"), "supporting_planets": planets, "confirmation": round(value, 4), "role": "CONFIRMATION_ONLY"})
    return {"contract_version": "d9-confirmation.v1", "status": "OBSERVED", "score": round(max(0, min(100, 50 + 50 * weighted / total if total else 50)), 2), "independent_vote": False, "confirmations": rows}


def _d9_lagna_lord_score(payload_data: Any, d9_lagna: str, field_affinity: Mapping[str, float],
                          d9_chart: Mapping[str, str] | None = None) -> tuple[float | None, str]:
    """Phase-3c: D9 lagna lord's own dignity, weighted by its field affinity
    (floored, matching siddhamsha.py's affinity-floor convention so the
    chart's general D9 capacity still counts for fields the lagna lord
    doesn't specifically rule). D9 gap-audit fix: now also folds in the
    lord's own D9-internal house placement (kendra/trikona/dusthana),
    previously untested here -- sign dignity and house placement are
    classically distinct strength axes."""
    if not d9_lagna:
        return None, ""
    lord = _SIGN_LORD.get(d9_lagna, "")
    if not lord:
        return None, ""
    digs = getattr(payload_data, "d9_planet_dignities", {}) or {}
    dig = str(digs.get(lord, "NEUTRAL")).upper()
    base = _DIGNITY_SCORE.get(dig, 50.0)
    _lord_house = _d9_house_num((d9_chart or {}).get(lord, ""), d9_lagna) if d9_chart else 0
    _placement_note = ""
    if _lord_house:
        _mult = _d9_placement_mult(_lord_house)
        base = max(0.0, min(100.0, base * _mult))
        if _mult != 1.0:
            _placement_note = f", D9 H{_lord_house} placement x{_mult}"
    aff = float((field_affinity or {}).get(lord, 0.0) or 0.0)
    aaf = 0.35 + 0.65 * max(0.0, min(1.0, aff))  # same 0.35 floor convention as siddhamsha.py
    blended = 50.0 + (base - 50.0) * aaf  # pull toward neutral 50 when affinity is low
    return blended, (f"D9 lagna {d9_lagna}, lord {lord} dignity={dig}{_placement_note} "
                      f"(affinity x{round(aaf,2)}) -> {round(blended,1)}")


def _d9_vidya_house_lord_score(payload_data: Any, d9_lagna: str, field_affinity: Mapping[str, float],
                                d9_chart: Mapping[str, str] | None = None) -> tuple[float | None, List[str]]:
    """Phase-3c: average D9 dignity of the 4th/5th/9th house lords counted
    from the navamsha lagna, each weighted by its own field affinity --
    mirrors siddhamsha.py's vidya_house_lord_support section so D9 and D24
    examine the same classical house set, just within their own vargas.
    D9 gap-audit fix: each lord's dignity is now also folded with its own
    D9-internal house placement, same as the lagna-lord check above."""
    if not d9_lagna:
        return None, []
    digs = getattr(payload_data, "d9_planet_dignities", {}) or {}
    notes: List[str] = []
    total = weight_sum = 0.0
    for h in _VIDYA_HOUSES:
        lord = _d9_house_lord(d9_lagna, h)
        if not lord:
            continue
        dig = str(digs.get(lord, "NEUTRAL")).upper()
        base = _DIGNITY_SCORE.get(dig, 50.0)
        _lord_house = _d9_house_num((d9_chart or {}).get(lord, ""), d9_lagna) if d9_chart else 0
        _placement_note = ""
        if _lord_house:
            _mult = _d9_placement_mult(_lord_house)
            base = max(0.0, min(100.0, base * _mult))
            if _mult != 1.0:
                _placement_note = f", D9 H{_lord_house} placement x{_mult}"
        aff = float((field_affinity or {}).get(lord, 0.0) or 0.0)
        aaf = 0.35 + 0.65 * max(0.0, min(1.0, aff))
        blended = 50.0 + (base - 50.0) * aaf
        total += blended * aaf
        weight_sum += aaf
        notes.append(f"D9 H{h} lord {lord} dignity={dig}{_placement_note} "
                     f"(affinity x{round(aaf,2)}) -> {round(blended,1)}")
    if weight_sum <= 0:
        return None, notes
    return total / weight_sum, notes


# D9 gap-audit fix (2026-08), addition 2 of 3: the D9 career house (10th
# from the D9 lagna) is now tested directly. This exact technique previously
# existed only as an ad hoc block in knrao.py that (bug) computed the D9
# lagna lord's dignity from its D1 sign rather than its D9 sign -- removed
# from there; this is the corrected, properly D9-internal version, home now
# in the module whose job is D9.
def _d9_h10_score(payload_data: Any, d9_lagna: str, field_affinity: Mapping[str, float],
                   d9_chart: Mapping[str, str] | None = None) -> tuple[float | None, List[str]]:
    if not d9_lagna:
        return None, []
    digs = getattr(payload_data, "d9_planet_dignities", {}) or {}
    d9_chart = d9_chart or {}
    notes: List[str] = []
    total = weight_sum = 0.0

    h10_lord = _d9_house_lord(d9_lagna, 10)
    if h10_lord:
        dig = str(digs.get(h10_lord, "NEUTRAL")).upper()
        base = _DIGNITY_SCORE.get(dig, 50.0)
        lord_house = _d9_house_num(d9_chart.get(h10_lord, ""), d9_lagna)
        mult = _d9_placement_mult(lord_house) if lord_house else 1.0
        base = max(0.0, min(100.0, base * mult))
        aff = float((field_affinity or {}).get(h10_lord, 0.0) or 0.0)
        aaf = 0.35 + 0.65 * max(0.0, min(1.0, aff))
        blended = 50.0 + (base - 50.0) * aaf
        total += blended * aaf
        weight_sum += aaf
        notes.append(f"D9 H10 lord {h10_lord} dignity={dig}, D9 H{lord_house or '?'} placement x{mult} "
                     f"(affinity x{round(aaf,2)}) -> {round(blended,1)}")

    h10_sign = ""
    lagna_idx = _SIGN_NUM.get(d9_lagna, 0)
    if lagna_idx:
        h10_sign = _SIGN_ORDER[(lagna_idx - 1 + 9) % 12]
    occupants = [p for p, s in d9_chart.items() if p != "Lagna" and s == h10_sign] if h10_sign else []
    for occ in occupants:
        aff = float((field_affinity or {}).get(occ, 0.0) or 0.0)
        if aff < 0.10:
            continue
        dig = str(digs.get(occ, "NEUTRAL")).upper()
        base = _DIGNITY_SCORE.get(dig, 50.0)
        aaf = 0.35 + 0.65 * max(0.0, min(1.0, aff))
        blended = 50.0 + (base - 50.0) * aaf
        total += blended * aaf
        weight_sum += aaf
        notes.append(f"D9 H10 occupant {occ} dignity={dig} (affinity x{round(aaf,2)}) -> {round(blended,1)}")

    if weight_sum <= 0:
        return None, notes
    return total / weight_sum, notes


# D9 gap-audit fix (2026-08), addition 3 of 3: Vargottama (a planet occupying
# the SAME sign in D1 and D9) is arguably the single strongest, most
# universally-agreed D9 confirmation signal in classical astrology -- a
# vargottama planet delivers its results with kendra-like stability
# regardless of its D1 house. Previously this was checked only inside
# parashara.py, scoped to that method's own top-4 field-weighted planets and
# feeding a small bonus THERE -- the dedicated "does D9 confirm the promise"
# module never asked the question at all. Bounded 50 (no vargottama
# field-planets) to 100 (all of them); vargottama is a confirming signal,
# never used to penalize its absence.
def _d9_vargottama_score(payload_data: Any, field_affinity: Mapping[str, float],
                          d9_chart: Mapping[str, str] | None = None) -> tuple[float | None, List[str]]:
    planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    d9_chart = d9_chart or {}
    if not planets_d1 or not d9_chart:
        return None, []
    total_aff = weighted_varg = 0.0
    notes: List[str] = []
    for p, aff in (field_affinity or {}).items():
        aff = float(aff or 0.0)
        if aff < 0.10:
            continue
        d1_sign = (planets_d1.get(p) or {}).get("sign", "")
        if not d1_sign:
            continue
        total_aff += aff
        # gap fix 2026-08-18 (I): was an inline `d1_sign == d9_chart.get(p, "")`
        # equality test duplicating jyotish/astro.py::_is_vargottama's rule;
        # now calls the shared field_methods.common.is_vargottama() wrapper
        # instead so the same-sign check lives in one place. Same inputs,
        # same result: _is_vargottama(p, d1_sign, d9_chart) reduces to
        # `bool(d1_sign) and d1_sign == d9_chart.get(p, "")`, and d1_sign is
        # already guaranteed truthy here by the `if not d1_sign: continue`
        # above, so behavior is unchanged.
        if is_vargottama(p, d1_sign, d9_chart):
            weighted_varg += aff
            notes.append(f"{p} is Vargottama (D1=D9={d1_sign}) -- kendra-stable career delivery.")
    if total_aff <= 0:
        return None, notes
    score = 50.0 + 50.0 * (weighted_varg / total_aff)
    return score, notes


# gap fix 2026-08-18 (E): Vimshopaka Bala consumption. jyotish/vimshopaka.py
# already implements the full classical Dasavarga Vimshopaka Bala (10-varga,
# BPHS Ch.6 20-point weighting); jyotish/boosts.py::_vimsopaka_bala_coefficient
# is the reduced 7-varga (D1/D3/D9/D10/D20/D24/D30) practical variant already
# wired into parashara.py/dashamsha.py/siddhamsha.py -- this reuses that same
# existing, tested coefficient rather than reimplementing either. It is
# deliberately DISTINCT from every other sub-score in this file: those all
# score dignity/placement WITHIN D9 specifically, while this coefficient
# aggregates a planet's strength ACROSS all vargas the pipeline has computed.
# CORRECTION (2026-08-22 audit): the "without duplicating any of the
# sub-scores above" claim is not accurate as stated -- D9 is itself one of
# the 7 vargas folded into avg_coeff (see _vimsopaka_bala_coefficient), so
# for the same top-3 affinity planets this does re-introduce a (1/7-weighted)
# slice of the same D9 dignity fact already scored directly by planet_score/
# lagna_score/house_score/h10_score above. Given vim_score's own blend weight
# is already small (0.10 of the total), and it is a genuinely distinct
# cross-varga signal for the other 6/7 of its input, this is judged a minor,
# already-small overlap rather than one requiring a further discount -- flagged
# here for transparency rather than silently left as a false "no duplication"
# claim.
def _d9_vimsopaka_score(payload_data: Any, field_affinity: Mapping[str, float]) -> tuple[float | None, str]:
    top = [p for p, aff in sorted((field_affinity or {}).items(), key=lambda x: -x[1])[:3] if aff and aff > 0]
    if not top:
        return None, ""
    avg_coeff = sum(_vimsopaka_bala_coefficient(p, payload_data) for p in top) / len(top)
    # avg_coeff in [0.75, 1.25]; map onto this module's 0-100 sub-score scale.
    score = max(0.0, min(100.0, 50.0 + (avg_coeff - 1.0) * 200.0))
    return score, (f"Vimshopaka Bala (reduced, cross-varga) for {', '.join(top)}: "
                    f"avg coefficient {avg_coeff:.2f} -> {round(score,1)}")


def score_navamsha_adjustment(
    payload_data: Any,
    domain: str = "",
    field_affinity: Mapping[str, float] | None = None,
    field_id: str = "",
    field_entry: Mapping = None,
) -> Dict[str, Any]:
    """Phase-2/3c remediation: blend three D9 confirmation sub-scores --
    (1) planet-level dignity of the field's top-affinity planets (legacy,
        Phase-2),
    (2) D9 lagna lord's own dignity/strength (Phase-3c, new),
    (3) D9 4th/5th/9th house-lord dignity, the same vidya-house set D24 uses
        (Phase-3c, new) --
    into a single bounded confirmation multiplier the bundle applies to
    `combined_score`. Still a confirmatory adjustment, not a vote: D9 does
    not gain weight in the primary blend, it now just examines more of what
    a real astrologer would check in navamsha before trusting D1/D24's
    verdict.

    Returns {"status", "multiplier", "trace", "components", "d9_confirmation_score"}.
    multiplier is in [_D9_MULT_MIN, _D9_MULT_MAX]; 1.0 = neutral/no data.
    """
    digs = getattr(payload_data, "d9_planet_dignities", {}) or {}
    trace: List[str] = []
    if not digs or not field_affinity:
        # 2026-08 methodology-gap fix: D9 data is genuinely absent here (not
        # weak-but-present), so this is NOT the same as "D9 was checked and
        # found neutral." A D1/D10 finding with no independent D9 corroboration
        # available deserves a mild confidence dampener -- not a penalty, since
        # the underlying D1/D10 signal may still be entirely correct, just
        # unconfirmable -- and downstream consumers need a status string that
        # distinguishes "unconfirmed" from both "confirmed" and any genuine
        # neutral-D9 case. 0.97x is roughly half the smallest real confirmation
        # effect (band is 0.92-1.08, i.e. +/-0.08 around neutral).
        # 2026-08-18 regression fix: restored to the pre-existing MISSING/1.0x
        # contract (jyotish/tests/test_phase1_2_remediation.py::
        # test_missing_data_returns_neutral_multiplier pins status=="MISSING",
        # multiplier==1.0). The intermediate "UNCONFIRMED_NO_D9_DATA"/0.97x
        # dampener this briefly held was never reconciled with that locked
        # test's contract -- reverting to the documented, tested convention
        # ("1.0 = neutral/no data", see this function's docstring) rather than
        # leaving a genuinely-missing-data case silently penalized in a way no
        # test or downstream consumer was ever updated to expect.
        return {
            "status": "MISSING", "multiplier": 1.0,
            "trace": ["D9 dignities or field affinity unavailable — no adjustment."],
            "components": {}, "d9_confirmation_score": None,
        }

    top_planets = [p for p, _ in sorted(field_affinity.items(), key=lambda x: -x[1])[:4] if field_affinity.get(p, 0) > 0]
    propositions = [{"proposition_id": field_id or domain, "supporting_planets": top_planets, "weight": 1.0}]
    legacy = score_navamsha_confirmation(payload_data, propositions)
    planet_score = legacy.get("score")

    d9_lagna = (
        (getattr(payload_data, "divisional_charts", {}) or {}).get("D9_navamsha", {}) or {}
    ).get("Lagna", "") or getattr(payload_data, "d9_lagna_sign", "") or ""

    d9_chart_for_scores = (
        (getattr(payload_data, "divisional_charts", {}) or {}).get("D9_navamsha", {}) or {}
    )
    lagna_score, lagna_note = _d9_lagna_lord_score(payload_data, d9_lagna, field_affinity, d9_chart_for_scores)
    house_score, house_notes = _d9_vidya_house_lord_score(payload_data, d9_lagna, field_affinity, d9_chart_for_scores)
    h10_score, h10_notes = _d9_h10_score(payload_data, d9_lagna, field_affinity, d9_chart_for_scores)
    varg_score, varg_notes = _d9_vargottama_score(payload_data, field_affinity, d9_chart_for_scores)
    vim_score, vim_note = _d9_vimsopaka_score(payload_data, field_affinity)

    # D9 gap-audit fix: weights rebalanced to make room for the two new
    # sub-scores (D9-H10 career house, Vargottama) alongside the original
    # three. sub_scores' weights are only ever summed and divided (see
    # weight_total below), so any subset present still renormalizes cleanly
    # if some signals are missing for a given chart.
    sub_scores: List[tuple[float, float]] = []  # (score, weight)
    if planet_score is not None:
        sub_scores.append((planet_score, 0.25))
        trace.append(f"D9 planet-level confirmation on {', '.join(top_planets) or '—'}: score={planet_score}")
    if lagna_score is not None:
        sub_scores.append((lagna_score, 0.20))
        trace.append(lagna_note)
    if house_score is not None:
        sub_scores.append((house_score, 0.20))
        trace.extend(house_notes)
    if h10_score is not None:
        sub_scores.append((h10_score, 0.20))
        trace.extend(h10_notes)
    if varg_score is not None:
        sub_scores.append((varg_score, 0.15))
        trace.extend(varg_notes)
    if vim_score is not None:
        sub_scores.append((vim_score, 0.10))
        trace.append(vim_note)

    if not sub_scores:
        # Same genuinely-missing-data case as above (2026-08-18 regression
        # fix: same MISSING/1.0x contract restored, same reason).
        return {
            "status": "MISSING", "multiplier": 1.0,
            "trace": ["No D9-supporting planets or house-lord data found for this field."],
            "components": {}, "d9_confirmation_score": None,
        }

    weight_total = sum(w for _, w in sub_scores)
    d9_score = round(sum(s * w for s, w in sub_scores) / weight_total, 2)

    # Map 0-100 D9 confirmation score onto the bounded multiplier band.
    frac = (d9_score - 50.0) / 50.0  # -1..+1
    multiplier = round(1.0 + frac * (_D9_MULT_MAX - 1.0 if frac >= 0 else 1.0 - _D9_MULT_MIN), 4)
    multiplier = max(_D9_MULT_MIN, min(_D9_MULT_MAX, multiplier))
    trace.append(f"D9 blended confirmation: {d9_score} -> multiplier={multiplier}")

    # ── §11 remediation (2026-08-19): core-three D9-collapse exclusion ────
    # Full Methodology Spec §11 filter 1: when a field's CORE significators
    # (its top affinity-weighted planets -- the ones actually carrying its
    # D1/D10/Jaimini support) collapse hard in D9, the field should be
    # excluded/heavily downranked, not merely nudged by the ordinary bounded
    # +/-15% confirmation band above. Previously no such exclusion existed
    # at all -- the only hard lockout anywhere in the engine fires on an
    # unrelated absolute low-score/affliction threshold (final_score < 20 OR
    # is_afflicted), which has nothing to do with D9 specifically collapsing
    # a field that otherwise looks D1/D10-strong. This is a SEPARATE,
    # stronger signal from the ordinary multiplier band: it fires only when
    # the top-3 core planets' blended D9 confirmation score is severely low
    # (deep affliction territory, not just "below neutral"), and layers an
    # additional heavy downrank on top of the already-floored 0.85x
    # multiplier -- mirroring the same two-tier pattern §8.5's dasha-
    # coverage-reject uses (an ordinary bounded band, PLUS a separate hard
    # reject/downrank for the genuinely severe case).
    _core_three = top_planets[:3]
    _core_three_present = len(_core_three) >= 1 and sum(field_affinity.get(p, 0.0) for p in _core_three) > 0
    d9_collapse_exclusion = bool(_core_three_present and d9_score <= _D9_COLLAPSE_SCORE_THRESHOLD)
    if d9_collapse_exclusion:
        multiplier = round(multiplier * _D9_COLLAPSE_REJECT_MULT, 4)
        trace.append(
            f"EXCLUDE/HEAVY-DOWNRANK (§11.1): core significator(s) {', '.join(_core_three) or '—'} "
            f"collapse severely in D9 (blended confirmation score {d9_score} <= "
            f"{_D9_COLLAPSE_SCORE_THRESHOLD:.0f}) -- this field's D1/D10 promise does not survive "
            "D9 scrutiny for its own core planets, regardless of how strong the primary blend looks."
        )

    return {
        "status": "OBSERVED",
        "multiplier": multiplier,
        "trace": trace,
        "components": {
            "d9_confirmation_score": d9_score,
            "d9_planet_score": planet_score,
            "d9_lagna_lord_score": round(lagna_score, 2) if lagna_score is not None else None,
            "d9_vidya_house_lord_score": round(house_score, 2) if house_score is not None else None,
            "d9_h10_score": round(h10_score, 2) if h10_score is not None else None,
            "d9_vargottama_score": round(varg_score, 2) if varg_score is not None else None,
            "d9_vimsopaka_score": round(vim_score, 2) if vim_score is not None else None,
        },
        "d9_confirmation_score": d9_score,
        "d9_collapse_exclusion": d9_collapse_exclusion,
        "core_three_planets": _core_three,
        "confirmations": legacy.get("confirmations", []),
    }
