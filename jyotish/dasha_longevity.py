"""Vimshottari Dasha longevity filter — shared by both career engines.

GAP FIX (2026-08-17): the 9-step career-determination framework's Step 7
("Dasha-Based Longevity Filter") asks for two things neither engine
previously did with Vimshottari data:
    1. Prioritize fields whose supporting planets have long, stable dasha
       periods ahead (not just a currently-active period).
    2. Flag (not necessarily exclude) fields resting only on a significator
       whose current dasha lord is about to hand off to a low-affinity lord.

Prior state: Job_Career/astro_enhancer.py scores Yogini/Chara/Ashtottari
sub-systems but has no Vimshottari-based longevity concept at all (it scores
one dasha *period* at a time, which is a different question — "is this
specific MD/AD window good" — not "does this field have staying power").
Field_Determination had no Vimshottari dasha signal of any kind.

This module answers the Step-7 question directly: given a chart's
Vimshottari Mahadasha sequence (already computed upstream — this module
does no ephemeris work, only reads the sequence already on
jyotish.payload's `dasha_sequence` field) and a field's planet-affinity
weights, how much staying power does this field's astrological support have
over the next several years?
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

_LONGEVITY_MULT_MIN = 0.90
# §8 remediation (2026-08-19): widened from 1.10 to 1.25 to make room for
# the new §8.3 special-criteria additive bonus (up to +0.15 once scaled,
# see special_raw_bonus below) stacking on top of the pre-existing
# stable-fraction term (up to +0.08) -- both terms share this one ceiling
# rather than each getting an independent uncapped allowance.
_LONGEVITY_MULT_MAX = 1.25

# §8 remediation (2026-08-19): spec asks the full MD sequence be mapped out
# to roughly age 55-70 -- the entire working-life horizon -- not just a
# short lookahead from the current age. 10 years was far short of that for
# a young native (e.g. current_age=22 -> old window ended at 32, nowhere
# near even the conservative 55 end of the spec's band). No caller
# overrode this default, so every field's stable_years_fraction was
# effectively answering "is the next decade good," not "is this
# sustainable across a career." Raised to 45 years, which combined with
# _effective_lookahead() below (capped at the spec's 70y anchor) reaches
# the full band for any working-age native.
_DEFAULT_LOOKAHEAD_YEARS = 45.0
_CAREER_HORIZON_END_AGE = 70.0
_SHORT_LIVED_THRESHOLD_YEARS = 2.0
_STRONG_AFFINITY_RATIO = 0.5
_WEAK_AFFINITY_RATIO = 0.3

# ── §8.3 special-weight criteria (2026-08-19 remediation) ──────────────────
# Full Methodology Spec §8.3: a dasha lord that is ALSO the Atmakaraka,
# Amatyakaraka, Yogakaraka, the chart's single strongest planet, or part of
# 2+ consecutive favorable Mahadashas deserves extra weight beyond the
# generic "affinity >= 0.5" test -- none of these four criteria were
# referenced anywhere in this module before. Modeled as a bounded ADDITIVE
# per-planet bonus (spec's own 0.10-0.18 range) layered on top of the
# existing multiplicative stable-fraction term, rather than folded into a
# single blended multiplier, so each qualifying planet's contribution stays
# individually traceable. Capped in total (_SPECIAL_CRITERIA_MAX_BONUS) so a
# chart with many qualifying planets can't blow past a modest ceiling --
# this is still a confirmation layer, not a new primary vote.
_SPECIAL_CRITERIA_BONUS_PER_PLANET = 0.14  # mid of spec's 0.10-0.18 band
_SPECIAL_CRITERIA_MAX_BONUS = 0.30
_CONSECUTIVE_FAVORABLE_MIN_COUNT = 2

# ── §8.5 hard reject/downrank: dasha coverage ending before ~age 35-40 ──────
# Full Methodology Spec §8.5: "Reject or heavily downrank any field whose
# supporting planets' favorable dasha coverage ends before roughly age
# 35-40 -- such a field cannot be argued as long-term sustainable regardless
# of its D1/D9/D10 strength." Previously nothing in this module (or anywhere
# else in the codebase) checked cumulative coverage against an absolute age
# threshold -- the only "coverage ending soon" signal was short_lived_flag
# above, which only ever looks one dasha ahead from the *current* age and
# only fires if under 2 years remain in the CURRENT period. A field whose
# strong-affinity coverage effectively ends at, say, age 24, followed by a
# long dead stretch before resuming at 38, would raise no flag at all under
# the old logic. _CAREER_MATURITY_AGE anchors the conservative (earlier) end
# of the spec's "~35-40" band so the reject is not over-eager for charts
# whose data legitimately runs out before full analysis is possible.
_CAREER_MATURITY_AGE = 35.0
_DASHA_COVERAGE_REJECT_MULT = 0.55  # heavy downrank, not a full exclusion multiplier


def _normalize_sequence(dasha_sequence: Sequence[Mapping]) -> List[Dict[str, Any]]:
    """Accept either Field_Determination's simple `dasha_sequence`
    ({lord, start_age, end_age}) or Job_Career's pyhora-style MD entries
    ({md_planet/lord/planet, start_age/age_start, end_age/age_end}), and
    normalize both into a single sorted [{lord, start_age, end_age}, ...]."""
    out: List[Dict[str, Any]] = []
    for entry in dasha_sequence or []:
        lord = entry.get("lord") or entry.get("md_planet") or entry.get("planet", "")
        start = entry.get("start_age")
        if start is None:
            start = entry.get("age_start", None)
        end = entry.get("end_age")
        if end is None:
            end = entry.get("end_age") if entry.get("end_age") is not None else entry.get("age_end", None)
        if not lord or start is None or end is None:
            continue
        try:
            start_f, end_f = float(start), float(end)
        except (TypeError, ValueError):
            continue
        if end_f <= start_f:
            continue
        out.append({"lord": lord, "start_age": start_f, "end_age": end_f})
    out.sort(key=lambda e: e["start_age"])
    return out


def _affinity_ratio(planet: str, field_affinity: Mapping[str, float], max_aff: float) -> float:
    if not planet or max_aff <= 0:
        return 0.0
    val = field_affinity.get(planet, 0.0) or 0.0
    return min(1.0, max(0.0, val / max_aff))


def _effective_lookahead(current_age: float, lookahead_years: float) -> float:
    """Ensure the mapped window reaches the spec's ~55-70 career-horizon
    anchor for a working-age native, without the caller having to know the
    right number to pass. Takes the LARGER of the caller's requested
    lookahead and "years remaining until age 70", capped at 60y so a very
    young native's chart doesn't map an absurdly long span."""
    if current_age is None:
        return lookahead_years
    horizon_needed = max(0.0, _CAREER_HORIZON_END_AGE - current_age)
    return max(lookahead_years, min(horizon_needed, 60.0))


def score_dasha_longevity(
    dasha_sequence: Sequence[Mapping],
    current_age: float,
    field_affinity: Mapping[str, float] | None,
    lookahead_years: float = _DEFAULT_LOOKAHEAD_YEARS,
    atmakaraka: str = "",
    amatyakaraka: str = "",
    yogakaraka: str = "",
    strongest_planet: str = "",
) -> Dict[str, Any]:
    """Score how much dasha-based staying power a field's significators have.

    Returns a dict:
        status: "CONFIRMED" | "UNCONFIRMED_NO_DASHA_DATA"
        multiplier: bounded [_LONGEVITY_MULT_MIN, _LONGEVITY_MULT_MAX], 1.0 = neutral.
            Composes the stable-fraction term with the §8.3 special-criteria
            additive bonus (see special_criteria_planets/special_criteria_raw_bonus).
        current_md_lord: str
        years_remaining_current_md: float | None
        short_lived_flag: bool — current lord is strong for this field but
            hands off soon to a weak-affinity lord (per framework: this is a
            caution flag, NOT grounds to drop the field from the ranked list)
        stable_years_fraction: float 0-1 — fraction of the lookahead window
            covered by dasha lords with strong (>= _STRONG_AFFINITY_RATIO)
            affinity to this field
        trace: List[str]
    """
    seq = _normalize_sequence(dasha_sequence)
    if not seq or current_age is None or not field_affinity:
        return {
            "status": "UNCONFIRMED_NO_DASHA_DATA",
            "multiplier": 1.0,
            "current_md_lord": "",
            "years_remaining_current_md": None,
            "short_lived_flag": False,
            "stable_years_fraction": None,
            "trace": ["Vimshottari dasha sequence, current age, or field affinity unavailable — "
                      "no longevity filter applied (neutral 1.0x, not a penalty: absence of "
                      "timing data says nothing about the field's D1/D10/KP suitability)."],
        }

    max_aff = max((v for v in field_affinity.values() if v is not None), default=0.0)

    # Find current MD entry (or, if current_age is past the known sequence,
    # fall back to the last entry so we can still reason about "handoff").
    current_entry = None
    for entry in seq:
        if entry["start_age"] <= current_age < entry["end_age"]:
            current_entry = entry
            break
    if current_entry is None:
        current_entry = seq[-1] if seq[-1]["end_age"] <= current_age else seq[0]

    current_lord = current_entry["lord"]
    years_remaining = max(0.0, current_entry["end_age"] - current_age)
    current_ratio = _affinity_ratio(current_lord, field_affinity, max_aff)

    # §8 remediation: use the full career-horizon lookahead (see
    # _effective_lookahead()) instead of the caller's raw lookahead_years,
    # so a young native's window actually reaches the spec's ~55-70 anchor.
    lookahead_years = _effective_lookahead(current_age, lookahead_years)

    # Stable-years-in-lookahead: sum, across all sequence entries overlapping
    # [current_age, current_age + lookahead_years], the portion of time ruled
    # by a lord with strong affinity to this field.
    window_end = current_age + lookahead_years
    strong_years = 0.0
    covered_years = 0.0
    next_entry = None
    # §8 remediation: cautions are now collected across the WHOLE lookahead
    # window (every handoff from a strong-affinity lord to a weak one),
    # not just the current->next transition -- a field whose support ends
    # at 24 and doesn't resume until 38 previously raised no caution at all
    # if the CURRENT lord wasn't the one about to hand off.
    window_cautions: List[str] = []
    for i, entry in enumerate(seq):
        overlap_start = max(entry["start_age"], current_age)
        overlap_end = min(entry["end_age"], window_end)
        if overlap_end <= overlap_start:
            continue
        span = overlap_end - overlap_start
        covered_years += span
        ratio = _affinity_ratio(entry["lord"], field_affinity, max_aff)
        if ratio >= _STRONG_AFFINITY_RATIO:
            strong_years += span
        if entry["start_age"] > current_age and next_entry is None:
            next_entry = entry
        # Look for a strong->weak handoff anywhere within the window.
        if ratio >= _STRONG_AFFINITY_RATIO and i + 1 < len(seq):
            _nxt = seq[i + 1]
            if _nxt["start_age"] < window_end:
                _nxt_ratio = _affinity_ratio(_nxt["lord"], field_affinity, max_aff)
                if _nxt_ratio < _WEAK_AFFINITY_RATIO:
                    window_cautions.append(
                        f"{entry['lord']}'s strong support for this field ends at age "
                        f"{entry['end_age']:.1f}, handing off to {_nxt['lord']} "
                        f"(weak affinity, ratio {_nxt_ratio:.2f})."
                    )

    stable_fraction = (strong_years / covered_years) if covered_years > 0 else None

    # Short-lived flag: current lord strong for this field, but < threshold
    # years remain, and the immediately-following lord is weak for this field.
    # Kept as a narrower, CURRENT-period-specific signal alongside the
    # window-wide window_cautions list above (broader scope, see §8.5 note).
    short_lived_flag = False
    next_ratio = _affinity_ratio(next_entry["lord"], field_affinity, max_aff) if next_entry else None
    if (current_ratio >= _STRONG_AFFINITY_RATIO
            and years_remaining < _SHORT_LIVED_THRESHOLD_YEARS
            and next_ratio is not None and next_ratio < _WEAK_AFFINITY_RATIO):
        short_lived_flag = True

    # Multiplier: reward a high stable_fraction. §8 remediation: the
    # short-lived/caution signal is now PURELY INFORMATIONAL (per spec:
    # "weak-dasha periods noted, not disqualifying") -- it no longer
    # subtracts from the multiplier. Only the reject/downrank check below
    # (§8.5, a genuinely different and much stronger claim: coverage never
    # reaches career maturity at all) is allowed to move the score down.
    multiplier = 1.0
    trace: List[str] = []
    if stable_fraction is not None:
        multiplier += (stable_fraction - 0.5) * 0.16  # +/-0.08 swing across the 0-1 range
        trace.append(
            f"Current MD lord {current_lord} ({years_remaining:.1f}y remaining, "
            f"affinity ratio {current_ratio:.2f}); {stable_fraction:.0%} of the next "
            f"{lookahead_years:.0f}y is ruled by strong-affinity lords."
        )
    if short_lived_flag:
        # Informational only (see the comment above `multiplier = 1.0`) --
        # no longer subtracted from the multiplier.
        trace.append(
            f"CAUTION: {current_lord}'s strong support for this field ends in "
            f"{years_remaining:.1f}y, handing off to {next_entry['lord']} "
            f"(weak affinity, ratio {next_ratio:.2f}) — sustained pursuit of this field "
            f"may need a transition plan around that dasha change, not that the field "
            f"should be dropped."
        )
    for _caution in window_cautions:
        # Avoid duplicating the current->next caution already appended above.
        if not (short_lived_flag and _caution.startswith(current_lord + "'s")):
            trace.append(f"CAUTION (window-wide): {_caution}")

    # ── §8.3 special-weight criteria: AK/AmK/Yogakaraka/strongest-planet/
    # 2+ consecutive favorable MDs ────────────────────────────────────────
    # Additive per-planet bonus (spec's 0.10-0.18 band, see
    # _SPECIAL_CRITERIA_BONUS_PER_PLANET) for each dasha lord within the
    # lookahead window that BOTH has strong affinity to this field AND
    # meets at least one of the four special criteria. Kept as a separate,
    # traceable addend rather than folded into the stable-fraction term
    # above, and capped in total so it stays a confirmation layer.
    special_planets: Dict[str, List[str]] = {}
    _window_entries = [
        e for e in seq
        if min(e["end_age"], window_end) > max(e["start_age"], current_age)
    ]
    for idx, entry in enumerate(_window_entries):
        lord = entry["lord"]
        ratio = _affinity_ratio(lord, field_affinity, max_aff)
        if ratio < _STRONG_AFFINITY_RATIO:
            continue
        reasons = []
        if atmakaraka and lord == atmakaraka:
            reasons.append("Atmakaraka")
        if amatyakaraka and lord == amatyakaraka:
            reasons.append("Amatyakaraka")
        if yogakaraka and lord == yogakaraka:
            reasons.append("Yogakaraka")
        if strongest_planet and lord == strongest_planet:
            reasons.append("chart's strongest planet")
        # 2+ consecutive favorable MDs: this lord and the next lord in the
        # window are BOTH strong-affinity.
        if idx + 1 < len(_window_entries):
            _nxt_ratio = _affinity_ratio(_window_entries[idx + 1]["lord"], field_affinity, max_aff)
            if _nxt_ratio >= _STRONG_AFFINITY_RATIO:
                reasons.append(f"part of {_CONSECUTIVE_FAVORABLE_MIN_COUNT}+ consecutive favorable MDs")
        if reasons:
            special_planets[lord] = reasons

    special_raw_bonus = min(
        _SPECIAL_CRITERIA_MAX_BONUS,
        len(special_planets) * _SPECIAL_CRITERIA_BONUS_PER_PLANET,
    )
    if special_planets:
        for _p, _reasons in special_planets.items():
            trace.append(f"Special-weight dasha lord {_p}: {', '.join(_reasons)} (§8.3).")
        # Scaled by 0.5 before entering the multiplier space: the spec's
        # 0.10-0.18 additive range is calibrated for a different (additive,
        # 0-1 scored) architecture than this module's bounded post-blend
        # multiplier -- per the "adapt existing architecture" approach used
        # throughout this remediation, the raw spec magnitude is preserved
        # in the trace/output (special_raw_bonus) while its effect on the
        # actual multiplier is proportionally scaled to stay consistent
        # with the other bounded confirmation layers (D9, Yogini, etc.)
        # this module's multiplier already composes with.
        multiplier += special_raw_bonus * 0.5

    multiplier = round(min(_LONGEVITY_MULT_MAX, max(_LONGEVITY_MULT_MIN, multiplier)), 4)

    # ── §8.5 hard reject/downrank check ──────────────────────────────────
    # Scan the FULL mapped sequence (not just the lookahead window) for the
    # last age at which a strong-affinity lord's period is active. Only
    # fires when: (a) the native hasn't already passed the maturity anchor
    # (past that point the question is moot), and (b) the sequence data
    # actually extends far enough to make the determination meaningful --
    # otherwise this would misfire as "coverage ends early" merely because
    # the caller didn't supply dasha data that far out.
    dasha_coverage_reject = False
    last_strong_end_age = None
    for entry in seq:
        ratio = _affinity_ratio(entry["lord"], field_affinity, max_aff)
        if ratio >= _STRONG_AFFINITY_RATIO:
            if last_strong_end_age is None or entry["end_age"] > last_strong_end_age:
                last_strong_end_age = entry["end_age"]
    sequence_end_age = seq[-1]["end_age"] if seq else None
    data_extends_far_enough = sequence_end_age is not None and sequence_end_age >= _CAREER_MATURITY_AGE
    if (current_age < _CAREER_MATURITY_AGE
            and data_extends_far_enough
            and (last_strong_end_age is None or last_strong_end_age < _CAREER_MATURITY_AGE)):
        dasha_coverage_reject = True
        multiplier = round(multiplier * _DASHA_COVERAGE_REJECT_MULT, 4)
        if last_strong_end_age is None:
            trace.append(
                "REJECT/DOWNRANK (§8.5): no dasha lord in the mapped sequence has strong "
                f"affinity to this field before age {_CAREER_MATURITY_AGE:.0f} -- favorable dasha "
                "coverage does not reach career maturity, so this field cannot be argued as "
                "long-term sustainable regardless of D1/D9/D10 strength."
            )
        else:
            trace.append(
                f"REJECT/DOWNRANK (§8.5): this field's strong-affinity dasha coverage ends at "
                f"age {last_strong_end_age:.1f}, before the ~{_CAREER_MATURITY_AGE:.0f}-40 career-"
                "maturity anchor -- favorable coverage does not carry through to career "
                "maturity, so this field cannot be argued as long-term sustainable regardless "
                "of D1/D9/D10 strength."
            )

    return {
        "status": "CONFIRMED",
        "multiplier": multiplier,
        "current_md_lord": current_lord,
        "years_remaining_current_md": round(years_remaining, 2),
        "short_lived_flag": short_lived_flag,
        "window_cautions": window_cautions,
        "stable_years_fraction": round(stable_fraction, 3) if stable_fraction is not None else None,
        "special_criteria_planets": special_planets,
        "special_criteria_raw_bonus": round(special_raw_bonus, 4),
        "lookahead_years_used": round(lookahead_years, 1),
        "dasha_coverage_reject": dasha_coverage_reject,
        "last_strong_affinity_end_age": (round(last_strong_end_age, 2)
                                          if last_strong_end_age is not None else None),
        "trace": trace,
    }
