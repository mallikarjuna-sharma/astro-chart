"""Phase A of the §10-refined composite scoring migration (see the delivered
SPEC_LITERAL_ARCHITECTURE_MIGRATION_PLAN.md for the full design rationale).

This module builds the per-planet PRIMITIVE quantities the refined §10
formula needs (Tier 1 structural strength, Tier 2 capped refinement,
Yogakaraka, D10 strength, D9 gate, wealth bonus, dasha-continuity bonus,
a capped Rahu/Ketu strength band, and birth-time confidence scaling) as
standalone, chart-level, field-independent functions.

IMPORTANT: nothing in this module is wired into the live scoring pipeline
yet. Per the migration plan's phased rollout, Phase A is build-and-unit-test
only -- `Field_Determination/field_methods/__init__.py`'s existing blend and
`jyotish/tiered_ranking.py`'s tiered override remain the live, shipped
scoring path until Phase B (shadow-score comparison) and Phase C (cutover)
are explicitly approved and executed as their own reviewed phases.

Formula recap (see the migration plan's §1/§1a for full reasoning):

    tier1_strength[planet]    = base_strength[planet] * dignity_mult[planet] * graha_yuddha_mult[planet]
    tier2_adjustment[planet]  = exp(clamp(mean(ln(f) for f in tier2_factors[planet]), -0.25, +0.20))
    adjusted_strength[planet] = tier1_strength[planet] * tier2_adjustment[planet] * yogakaraka_mult[planet]

    d1d10_component  = sum(weight * adjusted_strength[planet] * d10_strength[planet] for planet, weight in vec)
    wealth_component = sum(weight * wealth_bonus[planet] for planet, weight in vec)
    dasha_component  = sum(weight * dasha_continuity_bonus[planet] for planet, weight in vec)
    d9_gate           = weighted_average(d9_sustainability_mult[planet] for planet, weight in vec), bounded [0.85, 1.15]

    composite   = (0.55 * d1d10_component * d9_gate) + (0.225 * K * wealth_component) + (0.225 * K * dasha_component)
    field_score = composite * 100 * birth_time_confidence_factor
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from jyotish.constants import _SIGN_LORD, _SIGN_NUM

# ═══════════════════════════════════════════════════════════════════════
# Tier 1: structural strength (dignity + Graha Yuddha)
# ═══════════════════════════════════════════════════════════════════════

_DIGNITY_MULT = {
    "EXALTED": 1.40,
    "OWN": 1.20,
    "OWN_SIGN": 1.20,
    "MOOLATRIKONA": 1.25,
    "FRIEND": 1.05,
    "NEUTRAL": 1.00,
    "ENEMY": 0.85,
    "DEBILITATED": 0.65,
}


def dignity_mult(dignity: str) -> float:
    """Tier-1 dignity multiplier from a dignity label (EXALTED/OWN/.../DEBILITATED)."""
    return _DIGNITY_MULT.get((dignity or "").upper(), 1.00)


# Migration-plan §1a.3: Graha Yuddha requires TWO winner-determination
# criteria to agree before a winner/loser is declared, rather than
# committing unilaterally to one classical text's convention (celestial
# latitude vs. apparent size -- genuinely disputed between texts).
#
# Criterion A (apparent size): a fixed classical mean-angular-diameter
# ranking. This is itself an approximation (true apparent size varies with
# geocentric distance at the moment of observation, which would require
# ephemeris data this payload does not carry) but is a defensible, commonly
# cited ordering for the five Graha-Yuddha-eligible planets.
# Criterion B (longitude): the pre-existing "lower absolute longitude wins"
# heuristic from dignity.py::graha_yuddha(), kept as the second, independent
# check specifically so agreement/disagreement between two DIFFERENT
# heuristics is meaningful rather than trivially always agreeing.
#
# NOTE: true celestial latitude data is not available in this payload
# (jyotish/payload.py's `latitude` field is birth-location geographic
# latitude, not a planet's ecliptic latitude). If/when planetary latitude
# becomes available, criterion B should be replaced with a real
# latitude-based rule per BPHS convention; documented here as a known
# limitation of this Phase A implementation, not a design choice.
_YUDDHA_ELIGIBLE = frozenset({"Mars", "Mercury", "Jupiter", "Venus", "Saturn"})

_APPARENT_SIZE_RANK = {
    # Larger number = classically larger apparent size / closer to Earth.
    # Ordering: Venus > Jupiter > Mars > Saturn > Mercury (approximate mean
    # angular-diameter ordering as seen from Earth).
    "Venus": 5, "Jupiter": 4, "Mars": 3, "Saturn": 2, "Mercury": 1,
}

_GRAHA_YUDDHA_WINNER_MULT = 1.05
_GRAHA_YUDDHA_LOSER_MULT = 0.90
_GRAHA_YUDDHA_DISAGREEMENT_MULT = 0.95  # smaller, symmetric mutual-weakening


def compute_graha_yuddha_dual_criteria(planet_longitudes: Mapping[str, float]) -> Dict[str, Any]:
    """Detect Graha Yuddha (planetary war) using pure angular separation
    (<=1 degree, sign-boundary-agnostic per spec §5h), then resolve
    winner/loser using two independent criteria, only declaring an
    asymmetric winner/loser when they agree (§1a.3).

    Returns {"wars": [...], "graha_yuddha_mult": {planet: float}}.
    Every Yuddha-eligible planet not in a war gets multiplier 1.0.
    """
    eligible = {
        p: lon for p, lon in (planet_longitudes or {}).items()
        if p in _YUDDHA_ELIGIBLE and lon is not None
    }
    names = sorted(eligible)
    wars: List[Dict[str, Any]] = []
    mult: Dict[str, float] = {p: 1.0 for p in _YUDDHA_ELIGIBLE}

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            try:
                lon_a, lon_b = float(eligible[a]), float(eligible[b])
            except (TypeError, ValueError):
                continue
            diff = abs(lon_a - lon_b) % 360.0
            diff = min(diff, 360.0 - diff)
            if diff > 1.0:
                continue

            # Criterion A: apparent size (larger wins).
            size_winner = a if _APPARENT_SIZE_RANK.get(a, 0) > _APPARENT_SIZE_RANK.get(b, 0) else b
            # Criterion B: lower absolute longitude wins (pre-existing heuristic).
            longitude_winner = a if lon_a <= lon_b else b

            agree = size_winner == longitude_winner
            if agree:
                winner, loser = size_winner, (b if size_winner == a else a)
                mult[winner] = max(mult[winner], _GRAHA_YUDDHA_WINNER_MULT)
                mult[loser] = min(mult[loser], _GRAHA_YUDDHA_LOSER_MULT)
                wars.append({
                    "planets": [a, b], "winner": winner, "loser": loser,
                    "separation_degrees": round(diff, 4), "criteria_agree": True,
                    "note": f"Graha Yuddha: {winner} wins over {loser} (apparent-size and "
                            "longitude criteria agree).",
                })
            else:
                mult[a] = min(mult[a], _GRAHA_YUDDHA_DISAGREEMENT_MULT)
                mult[b] = min(mult[b], _GRAHA_YUDDHA_DISAGREEMENT_MULT)
                wars.append({
                    "planets": [a, b], "winner": None, "loser": None,
                    "separation_degrees": round(diff, 4), "criteria_agree": False,
                    "note": f"Graha Yuddha detected between {a} and {b}; apparent-size "
                            f"({size_winner}) and longitude ({longitude_winner}) criteria "
                            "disagree -- treated as mutual weakening, not a clear win/loss.",
                })

    return {"wars": wars, "graha_yuddha_mult": mult, "in_graha_yuddha": bool(wars)}


def compute_tier1_strength(
    base_strength: Mapping[str, float],
    dignity_labels: Mapping[str, str],
    graha_yuddha_mult: Mapping[str, float],
) -> Dict[str, float]:
    """tier1_strength[planet] = base_strength * dignity_mult * graha_yuddha_mult."""
    out: Dict[str, float] = {}
    for planet, base in (base_strength or {}).items():
        dm = dignity_mult(dignity_labels.get(planet, ""))
        gym = float((graha_yuddha_mult or {}).get(planet, 1.0))
        out[planet] = round(float(base) * dm * gym, 6)
    return out


# ═══════════════════════════════════════════════════════════════════════
# Tier 2: capped refinement layer (§1a.1)
# ═══════════════════════════════════════════════════════════════════════

_TIER2_ADJUSTMENT_MIN_LOG = -0.25
_TIER2_ADJUSTMENT_MAX_LOG = 0.20


def compute_tier2_adjustment(factors: Sequence[float]) -> float:
    """Combine an arbitrary number of Tier-2 refinement multipliers
    (combustion, maitri, avastha, vargottama, kp, knrao, sudarshan) via a
    capped log-average instead of a straight product, so several
    individually-minor issues can't compound into an overstated penalty
    (migration plan §1a.1). Factors <= 0 are ignored (invalid/neutral).
    """
    valid = [f for f in factors if f and f > 0]
    if not valid:
        return 1.0
    mean_log = sum(math.log(f) for f in valid) / len(valid)
    clamped = max(_TIER2_ADJUSTMENT_MIN_LOG, min(_TIER2_ADJUSTMENT_MAX_LOG, mean_log))
    return round(math.exp(clamped), 6)


def compute_adjusted_strength(
    tier1_strength: Mapping[str, float],
    tier2_factors: Mapping[str, Sequence[float]],
    yogakaraka_mult: Mapping[str, float],
) -> Dict[str, float]:
    """adjusted_strength[planet] = tier1_strength * tier2_adjustment * yogakaraka_mult.

    Yogakaraka is deliberately applied OUTSIDE the capped Tier-2 layer
    (migration plan §1a.1) -- its own spec-defined 18-25% range is already
    its own cap, and folding it into Tier 2's average would let a genuine
    Yogakaraka's clearly-decisive classical role get diluted/clipped by
    unrelated minor refinement factors.
    """
    out: Dict[str, float] = {}
    for planet, t1 in (tier1_strength or {}).items():
        t2 = compute_tier2_adjustment(tier2_factors.get(planet, []))
        yk = float((yogakaraka_mult or {}).get(planet, 1.0))
        out[planet] = round(float(t1) * t2 * yk, 6)
    return out


# ═══════════════════════════════════════════════════════════════════════
# D10 strength (explicit, per-planet -- migration plan §1a.2)
# ═══════════════════════════════════════════════════════════════════════

_D10_KENDRA_TRIKONA = frozenset({1, 4, 5, 7, 9, 10})
_D10_DUSTHANA = frozenset({6, 8, 12})


def _d10_house_from_lagna(planet_sign: str, d10_lagna: str) -> int:
    if not planet_sign or not d10_lagna or planet_sign not in _SIGN_NUM or d10_lagna not in _SIGN_NUM:
        return 0
    return ((_SIGN_NUM[planet_sign] - _SIGN_NUM[d10_lagna]) % 12) + 1


def compute_d10_strength(
    d10_chart: Mapping[str, Any],
    d10_planet_dignities: Optional[Mapping[str, str]] = None,
) -> Dict[str, float]:
    """d10_strength[planet]: a standalone per-planet D10 (Dashamsha) strength
    multiplier (roughly 0.7-1.3), independent of any field's affinity vector
    -- previously D10 dignity/house-lordship logic only existed buried
    inside dashamsha.py's field-level scorer (migration plan §1a.2, §2 row
    for d10_strength). Combines D10 sign dignity with D10 house placement
    (kendra/trikona vs. dusthana from the D10 lagna).

    `d10_chart`: the flat {planet: sign, "Lagna": sign, ...} dict already
    used elsewhere in this codebase (e.g. divisional_charts["D10_dashamsha"]).
    """
    d10_lagna = (d10_chart or {}).get("Lagna", "") or (d10_chart or {}).get("lagna", "")
    out: Dict[str, float] = {}
    for planet, sign in (d10_chart or {}).items():
        if planet.lower() in ("lagna",):
            continue
        dig = (d10_planet_dignities or {}).get(planet, "")
        dig_component = dignity_mult(dig) if dig else 1.0
        house = _d10_house_from_lagna(sign, d10_lagna) if d10_lagna else 0
        # Audit fix (2026-08-20, deep D1/D9/D10 audit): the single most
        # decisive classical Dashamsha technique is a planet's placement
        # specifically in the 10th house FROM THE D10 LAGNA (the "career of
        # career" house -- e.g. "Venus exalted in D10's own 10th" is a
        # textbook strong-career signal) -- yet this function previously
        # gave H10 no more weight than any other kendra/trikona house (H1,
        # H4, H5, H7, H9 all scored identically at 1.15). The OTHER, richer
        # D10 scorer in this codebase (dashamsha.py::score_dashamsha()) has
        # always given D10-H10 occupancy its own dedicated, most-heavily-
        # weighted branch -- this brings the standalone per-planet primitive
        # used by the v2-primary score into line with that same emphasis,
        # rather than leaving the two D10 implementations disagreeing on how
        # much D10's own 10th house matters.
        if house == 10:
            house_component = 1.30
        elif house in _D10_KENDRA_TRIKONA:
            house_component = 1.15
        elif house in _D10_DUSTHANA:
            house_component = 0.85
        else:
            house_component = 1.0
        # Blend, then clamp to the documented 0.7-1.3 band.
        raw = 0.5 * dig_component + 0.5 * house_component
        out[planet] = round(max(0.7, min(1.3, raw)), 4)
    return out


# ═══════════════════════════════════════════════════════════════════════
# D9 gate (per-planet dignity -> per-field weighted-average gate; §1a.2)
# ═══════════════════════════════════════════════════════════════════════

_D9_GATE_MIN = 0.85
_D9_GATE_MAX = 1.15

_D9_DIGNITY_SCORE = {
    "EXALTED": 1.0, "OWN": 0.85, "OWN_SIGN": 0.85, "MOOLATRIKONA": 0.90,
    # GREAT_FRIEND/GREAT_ENEMY are the fuller five-fold scheme's mutual-
    # relationship tiers from dignity.py::dignity_state() (not returned by
    # the narrow compute_dignity() scheme this table was originally built
    # against) -- interpolated on the same EXALTED=1.0..DEBILITATED=0.10
    # scale, one notch either side of the plain FRIEND/ENEMY/NEUTRAL tiers.
    "GREAT_FRIEND": 0.75, "FRIEND": 0.65, "NEUTRAL": 0.50,
    "ENEMY": 0.30, "GREAT_ENEMY": 0.20, "DEBILITATED": 0.10,
    "NEECHA_BHANGA": 0.50,
}


def compute_d9_sustainability_mult(d9_dignity: str) -> float:
    """Spec-literal per-planet D9 sign-dignity -> [0.85, 1.15] multiplier
    (migration plan §2: stripped down from the richer blended version in
    navamsha.py, which is kept as a separate `d9_confirmation_detail`
    diagnostic rather than the scoring path)."""
    score = _D9_DIGNITY_SCORE.get((d9_dignity or "").upper(), 0.50)
    frac = (score - 0.5) / 0.5  # -1..+1
    mult = 1.0 + frac * (_D9_GATE_MAX - 1.0 if frac >= 0 else 1.0 - _D9_GATE_MIN)
    return round(max(_D9_GATE_MIN, min(_D9_GATE_MAX, mult)), 4)


def compute_d9_gate(
    field_affinity: Mapping[str, float],
    d9_planet_dignities: Mapping[str, str],
) -> float:
    """d9_gate: weighted average of compute_d9_sustainability_mult() across a
    field's affinity vector, bounded [0.85, 1.15] -- applied as a
    MULTIPLICATIVE gate on d1d10_component (migration plan §1a.2), not a
    parallel additive 30% term."""
    if not field_affinity:
        return 1.0
    total_w = sum(w for w in field_affinity.values() if w) or 1.0
    acc = 0.0
    for planet, weight in field_affinity.items():
        if not weight:
            continue
        m = compute_d9_sustainability_mult(d9_planet_dignities.get(planet, ""))
        acc += weight * m
    gate = acc / total_w
    return round(max(_D9_GATE_MIN, min(_D9_GATE_MAX, gate)), 4)


# ═══════════════════════════════════════════════════════════════════════
# Wealth bonus (per-planet, field-independent -- reuses chart-wide Dhana
# yoga scan already built this session in jyotish/boosts.py)
# ═══════════════════════════════════════════════════════════════════════

_WEALTH_PRIMARY_BONUS = 0.115    # spec §7.4: 0.08-0.15
_WEALTH_DHARMA_BONUS = 0.06      # spec §7.4: 0.04-0.08
_WEALTH_SPECULATIVE_BONUS = 0.045  # spec §7.4: 0.03-0.06


def compute_wealth_bonus_per_planet(
    house_lords: Mapping[str, str],
    planet_house: Mapping[str, int],
) -> Dict[str, float]:
    """wealth_bonus[planet]: field-independent per-planet magnitude dict,
    built from the chart-wide Dhana-yoga scan (jyotish.boosts._chart_wide_dhana_yogas,
    already field-independent per this session's §7 work) using the exact
    §7.4 magnitude ranges. A planet participating in more than one axis
    takes the higher applicable bonus (not summed, to avoid double-counting
    the same planet's single placement across overlapping axis checks)."""
    from jyotish.boosts import _chart_wide_dhana_yogas
    yogas = _chart_wide_dhana_yogas(dict(house_lords or {}), dict(planet_house or {}))
    out: Dict[str, float] = {}
    for planet in yogas.get("secondary_speculative", {}):
        out[planet] = max(out.get(planet, 0.0), _WEALTH_SPECULATIVE_BONUS)
    for planet in yogas.get("secondary_dharma", {}):
        out[planet] = max(out.get(planet, 0.0), _WEALTH_DHARMA_BONUS)
    for planet in yogas.get("primary", {}):
        out[planet] = max(out.get(planet, 0.0), _WEALTH_PRIMARY_BONUS)
    return out


# ═══════════════════════════════════════════════════════════════════════
# Dasha-continuity bonus (per-planet, chart-level -- migration plan §2)
# ═══════════════════════════════════════════════════════════════════════

_DASHA_CONTINUITY_BONUS_PER_CRITERION = 0.06  # spec §8: 0.10-0.18 total per qualifying planet
_DASHA_CONTINUITY_BONUS_MAX = 0.18
_CAREER_WINDOW_START_AGE = 15.0
_CAREER_WINDOW_END_AGE = 55.0


def compute_dasha_continuity_bonus_per_planet(
    dasha_sequence: Sequence[Mapping[str, Any]],
    atmakaraka: str = "",
    amatyakaraka: str = "",
    yogakaraka: str = "",
    strongest_planet: str = "",
) -> Dict[str, float]:
    """dasha_continuity_bonus[planet]: chart-level (field-independent)
    per-planet bonus, per migration plan §2 -- a planet either satisfies
    the §8 special-weight criteria (AK/AmK/Yogakaraka/strongest-planet/2+
    consecutive favorable MDs covering the career window) or it doesn't,
    regardless of which field is asking. The §8.5 age-35-40 sustainability
    REJECT stays a separate per-field exclusion filter (§11 filter 2), not
    part of this bonus.
    """
    from jyotish.dasha_longevity import _normalize_sequence

    seq = _normalize_sequence(dasha_sequence)
    out: Dict[str, float] = {}
    if not seq:
        return out

    window_entries = [
        e for e in seq
        if e["end_age"] > _CAREER_WINDOW_START_AGE and e["start_age"] < _CAREER_WINDOW_END_AGE
    ]
    for idx, entry in enumerate(window_entries):
        lord = entry["lord"]
        criteria = 0
        if atmakaraka and lord == atmakaraka:
            criteria += 1
        if amatyakaraka and lord == amatyakaraka:
            criteria += 1
        if yogakaraka and lord == yogakaraka:
            criteria += 1
        if strongest_planet and lord == strongest_planet:
            criteria += 1
        if idx + 1 < len(window_entries):
            # crude "consecutive favorable" proxy at the chart level: two
            # back-to-back MDs both ruled by karaka/strongest planets.
            nxt = window_entries[idx + 1]["lord"]
            if nxt in (atmakaraka, amatyakaraka, yogakaraka, strongest_planet) and nxt:
                criteria += 1
        if criteria:
            bonus = min(_DASHA_CONTINUITY_BONUS_MAX, criteria * _DASHA_CONTINUITY_BONUS_PER_CRITERION)
            out[lord] = max(out.get(lord, 0.0), bonus)

    # Instrumentation (audit pass, 2026-08-20): print the final, chart-level
    # dasha-continuity bonus for every qualifying planet, following the same
    # unconditional-print convention as the three prior instrumentation
    # passes (astro.py::_compute_eff_strengths, engine.py::_score_one_field,
    # tiered_ranking.py::compute_tiered_ranking, boosts.py::compute_wealth_potential).
    if out:
        for _lord, _bonus in out.items():
            _reason_bits = []
            if atmakaraka and _lord == atmakaraka:
                _reason_bits.append("Atmakaraka")
            if amatyakaraka and _lord == amatyakaraka:
                _reason_bits.append("Amatyakaraka")
            if yogakaraka and _lord == yogakaraka:
                _reason_bits.append("Yogakaraka")
            if strongest_planet and _lord == strongest_planet:
                _reason_bits.append("chart's strongest planet")
            _md_spans = [
                f"{e['start_age']:.0f}-{e['end_age']:.0f}" for e in window_entries if e["lord"] == _lord
            ]
            _reason_txt = " + ".join(_reason_bits) if _reason_bits else "consecutive favorable MD stacking"
            _span_txt = ", ".join(_md_spans) if _md_spans else "n/a"
            print(
                f"Dasha-continuity bonus — {_lord}: {_bonus:.2f} "
                f"({_reason_txt}; MD age span {_span_txt}, career window "
                f"{_CAREER_WINDOW_START_AGE:.0f}-{_CAREER_WINDOW_END_AGE:.0f})"
            )
        # Explicit "triple stack" check per §8.3: a chara-karaka (either
        # Atmakaraka OR Amatyakaraka) + Yogakaraka + strongest planet all the
        # SAME planet, ruling 2+ consecutive favorable MDs spanning the
        # window (the rare, strongest-possible argument case).
        #
        # Fix (2026-08-20 audit, hands-on chart trace): this used to check
        # ONLY amatyakaraka (AmK) here, never atmakaraka (AK) -- even though
        # the per-planet bonus loop/reason-string above treats AK and AmK as
        # equally valid criteria (see "Atmakaraka"/"Amatyakaraka" reason
        # bits). A planet is AK or AmK by construction, essentially never
        # both (they're the 1st- and 2nd-highest-degree chara karakas), so
        # an AK-holding planet could satisfy 2 of {yogakaraka, strongest}
        # but could never reach the old amatyakaraka-only 3rd criterion,
        # meaning this branch could never fire for an AK-based confluence no
        # matter how rare/strong it was -- and the chart would then print
        # "No rare AmK+Yogakaraka+strongest-planet triple stack was present"
        # directly beneath a per-planet bonus line that had just credited
        # that same planet with "(Atmakaraka + Yogakaraka + chart's
        # strongest planet)", reading as a flat self-contradiction. Now
        # checks both AK-based and AmK-based confluence and names whichever
        # karaka(s) actually qualified.
        _triple_stack_planet = None
        _triple_stack_karaka_bits: List[str] = []
        for _lord in out:
            _lord_karaka_bits = []
            if atmakaraka and _lord == atmakaraka:
                _lord_karaka_bits.append("Atmakaraka")
            if amatyakaraka and _lord == amatyakaraka:
                _lord_karaka_bits.append("Amatyakaraka")
            _n_criteria = (
                (1 if _lord_karaka_bits else 0)
                + bool(yogakaraka and _lord == yogakaraka)
                + bool(strongest_planet and _lord == strongest_planet)
            )
            _consec = sum(1 for e in window_entries if e["lord"] == _lord) >= 2
            if _n_criteria >= 3 and _consec:
                _triple_stack_planet = _lord
                _triple_stack_karaka_bits = _lord_karaka_bits
                break
        if _triple_stack_planet:
            _karaka_txt = " and ".join(_triple_stack_karaka_bits) if _triple_stack_karaka_bits else "a chara karaka"
            print(
                f"[DASHA-CONTINUITY NARRATIVE] Rare triple-stack case: {_triple_stack_planet} is "
                f"simultaneously {_karaka_txt}, Yogakaraka, and the chart's single strongest planet, "
                f"ruling {sum(1 for e in window_entries if e['lord'] == _triple_stack_planet)} "
                f"Mahadasha period(s) inside the {_CAREER_WINDOW_START_AGE:.0f}-{_CAREER_WINDOW_END_AGE:.0f} "
                "sustainability window — the strongest possible dasha-continuity argument for any "
                "field this planet significates."
            )
        else:
            # Note which planet(s), if any, already hold the karaka+strongest
            # confluence but simply don't rule 2+ MDs in the window -- so this
            # sentence never reads as denying a confluence a reader just saw
            # credited on the per-planet bonus line(s) printed above.
            _near_miss = []
            for _lord in out:
                _bits = []
                if atmakaraka and _lord == atmakaraka:
                    _bits.append("Atmakaraka")
                if amatyakaraka and _lord == amatyakaraka:
                    _bits.append("Amatyakaraka")
                _confluence = bool(_bits) and (yogakaraka and _lord == yogakaraka) and (strongest_planet and _lord == strongest_planet)
                if _confluence:
                    _near_miss.append(f"{_lord} ({' and '.join(_bits)} + Yogakaraka + strongest planet, but rules only "
                                       f"{sum(1 for e in window_entries if e['lord'] == _lord)} MD period(s) in this window, not 2+)")
            _near_miss_txt = (" " + "; ".join(_near_miss) + ".") if _near_miss else ""
            print(
                "[DASHA-CONTINUITY NARRATIVE] "
                f"{len(out)} planet(s) qualify for a dasha-continuity bonus within the "
                f"{_CAREER_WINDOW_START_AGE:.0f}-{_CAREER_WINDOW_END_AGE:.0f} sustainability window: "
                + ", ".join(f"{p} ({b:.2f})" for p, b in out.items())
                + ". No rare Atmakaraka/Amatyakaraka+Yogakaraka+strongest-planet triple stack "
                  "ruling 2+ Mahadasha periods in this window was present in this chart."
                + _near_miss_txt
            )
    else:
        print(
            "[DASHA-CONTINUITY NARRATIVE] No dasha lord within the "
            f"{_CAREER_WINDOW_START_AGE:.0f}-{_CAREER_WINDOW_END_AGE:.0f} sustainability window matched "
            "Atmakaraka, Amatyakaraka, Yogakaraka, the chart's strongest planet, or 2+ consecutive "
            "favorable Mahadashas — no dasha-continuity bonus applies to any field this chart."
        )

    return out


# ═══════════════════════════════════════════════════════════════════════
# Rahu/Ketu strength ceiling (§1a.4)
# ═══════════════════════════════════════════════════════════════════════

_NODE_STRENGTH_CEILING = 0.9
_NODE_STRENGTH_FLOOR = 0.6


def cap_node_base_strength(raw_node_strength_0_1: float) -> float:
    """Cap Rahu/Ketu's substitute strength (jyotish.shadbala.estimate_node_strength,
    which ranges 0-1 with no ceiling relative to classical Shadbala-backed
    planets) into a tighter [0.6, 0.9] band, per migration plan §1a.4, so a
    node can never register as the single strongest planet in the chart --
    there is no classical Shadbala for the nodes, so any numeric strength
    for them is already an approximation layered on doctrine, not doctrine
    itself, and should never out-rank a real Shadbala-backed planet."""
    raw = max(0.0, min(1.0, float(raw_node_strength_0_1 or 0.0)))
    return round(_NODE_STRENGTH_FLOOR + raw * (_NODE_STRENGTH_CEILING - _NODE_STRENGTH_FLOOR), 4)


def dominant_significator_is_node(field_affinity: Mapping[str, float]) -> bool:
    """True if a field's highest-affinity-weight planet is Rahu or Ketu --
    surfaced as an independent low-confidence flag (migration plan §1a.4),
    distinct from the general birth-time-confidence flag."""
    if not field_affinity:
        return False
    top = max(field_affinity, key=field_affinity.get)
    return top in ("Rahu", "Ketu")


# ═══════════════════════════════════════════════════════════════════════
# Birth-time confidence factor (§1a.5)
# ═══════════════════════════════════════════════════════════════════════

_BIRTH_TIME_CONFIDENCE_FACTOR = {
    "exact": 1.0,
    "approximate": 0.88,
    "unknown": 0.75,
}


def compute_birth_time_confidence_factor(birth_time_precision: str) -> float:
    """Multiplier on the WHOLE field_score (migration plan §1a.5), not just a
    gate on which techniques run -- compresses Lagna-dependent rankings
    toward the middle when the input data doesn't support the false
    precision a full-strength score would otherwise imply."""
    return _BIRTH_TIME_CONFIDENCE_FACTOR.get((birth_time_precision or "exact").lower(), 1.0)


# ═══════════════════════════════════════════════════════════════════════
# Composite formula (not wired into the live pipeline -- Phase A exposes
# this for unit testing / Phase B shadow-scoring only)
# ═══════════════════════════════════════════════════════════════════════

# 2026-08-20 recalibration (Stage-1a/1b consolidation): d1d10_component's
# per-planet input switched from a max-normalized base_strength (~0.4-1.3
# range) to astro.py::_compute_eff_strengths' eff_strength (~0.5-1.5 range,
# plus Yogakaraka's 1.25x now landing on top of an already-higher baseline
# instead of a normalized one) -- a real, systematic upward shift in
# d1d10_component's typical magnitude, not just a change in what it means.
# Left at the old 0.55 weight, every field's field_score_v2_refined would
# have inflated by roughly the same proportion the underlying component
# did, silently shifting the whole published 0-100 scale upward regardless
# of a field's actual chart support. Rescaled here by the ratio of mean
# d1d10_component observed across a 4-field spot-check (Finance & Banking,
# Materials Science & Engineering, Engineering Management, Construction
# Engineering & Management) on one real chart, old-wiring vs new-wiring
# (0.8754 / 1.1611 ~= 0.754), so the AVERAGE composite magnitude across
# those fields lands close to where it did before the wiring change --
# preserving downstream absolute-threshold consumers (e.g. LOW_SIGNAL
# status bands, hard_lockout-adjacent score gates) calibrated against the
# old scale. This is a first-pass calibration from a small sample on one
# chart, not a rigorously re-tuned constant -- re-validate against several
# more charts before treating 0.415 as final.
_COMPOSITE_D1D10_WEIGHT = 0.415
_COMPOSITE_WEALTH_WEIGHT = 0.225
_COMPOSITE_DASHA_WEIGHT = 0.225
_COMPOSITE_K = 4.0


def compute_field_score(
    field_affinity: Mapping[str, float],
    adjusted_strength: Mapping[str, float],
    d10_strength: Mapping[str, float],
    d9_gate: float,
    wealth_bonus: Mapping[str, float],
    dasha_continuity_bonus: Mapping[str, float],
    birth_time_confidence_factor: float = 1.0,
    corroboration_mult: float = 1.0,
) -> Dict[str, Any]:
    """The refined §10 composite formula (migration plan §1). Returns a dict
    with the four raw components plus the final field_score, for
    transparency/audit -- not just the bare number.

    `corroboration_mult` (audit fix, 2026-08-20): spec §9's "Cross-
    Verification Layers" -- KP cuspal chain, K.N. Rao 2-of-3, Sudarshana
    triple-lagna overlay, Yogakaraka status, Argala on H10, D24 study-vs-
    career testimony, Vimshopaka Bala, and the other per-field
    confirmation/contradiction checks already computed every run in
    engine.py's `_score_one_field()` accumulator (`acc.gap_boost`/
    `acc.gap_penalty`, printed per field as "[FIELD SCORE]"/gap_detail) --
    is real, chart-and-field-specific classical evidence that this field's
    D1/D10 promise is independently corroborated (or contradicted) by other
    techniques. Before this fix, that whole layer was computed, audited, and
    printed every run but never actually reached `field_score` once v2
    became the primary/authoritative score (2026-08-20 architecture
    change) -- it was orphaned, not merely under-weighted. That silently
    defeated the entire point of §9: cross-verification exists specifically
    to widen the gap between a field that several independent techniques
    agree on and one that only the base D1/D10 strength happens to favor,
    which is exactly the kind of differentiation a real astrologer would
    apply by hand. Folded in here as a bounded multiplier on the D1/D10
    term, the same treatment already given to `d9_gate` (a confirming/
    dampening modifier on the base-strength term, not a free-standing
    scoring category of its own) -- consistent with how D9 sustainability
    is treated, and keeps the wealth/dasha components (which already have
    their own dedicated, unmultiplied signal paths) untouched. Callers pass
    `(1 + acc.gap_boost) * (1 - acc.gap_penalty)`, which is already capped
    upstream at acc.gap_boost in [-0.20, 0.55] and acc.gap_penalty >= 0
    (see engine.py's accumulator), so this factor cannot itself blow up an
    otherwise-modest D1/D10 term; defensively re-clamped to [0.75, 1.60]
    here as well so a caller passing an unclamped value can't either.
    """
    if not field_affinity:
        return {
            "d1d10_component": 0.0, "wealth_component": 0.0, "dasha_component": 0.0,
            "d9_gate": d9_gate, "corroboration_mult": 1.0, "composite": 0.0, "field_score": 0.0,
        }
    corroboration_mult = max(0.75, min(1.60, float(corroboration_mult or 1.0)))
    d1d10_component = sum(
        weight * adjusted_strength.get(planet, 0.0) * d10_strength.get(planet, 1.0)
        for planet, weight in field_affinity.items()
    )
    wealth_component = sum(
        weight * wealth_bonus.get(planet, 0.0) for planet, weight in field_affinity.items()
    )
    dasha_component = sum(
        weight * dasha_continuity_bonus.get(planet, 0.0) for planet, weight in field_affinity.items()
    )
    composite = (
        _COMPOSITE_D1D10_WEIGHT * d1d10_component * d9_gate * corroboration_mult
        + _COMPOSITE_WEALTH_WEIGHT * _COMPOSITE_K * wealth_component
        + _COMPOSITE_DASHA_WEIGHT * _COMPOSITE_K * dasha_component
    )
    field_score = composite * 100.0 * birth_time_confidence_factor

    # Instrumentation (audit pass, 2026-08-20): print the final, scaled and
    # weighted contribution of each of the four §10 components to this
    # field's composite score, the per-planet adjusted_strength this call
    # received (the composite of whichever of the 9 §5/§9 multipliers were
    # actually folded in upstream -- see engine.py::_build_composite_v2_chart_primitives
    # and ::_composite_v2_field_tier2_bonus), and one dynamic narrative
    # paragraph -- following the same unconditional-print convention as the
    # dasha-continuity-bonus instrumentation earlier in this file. Read-only:
    # does not change what is returned/used downstream.
    _d1d10_contrib = round(_COMPOSITE_D1D10_WEIGHT * d1d10_component * d9_gate * corroboration_mult, 4)
    _wealth_contrib = round(_COMPOSITE_WEALTH_WEIGHT * _COMPOSITE_K * wealth_component, 4)
    _dasha_contrib = round(_COMPOSITE_DASHA_WEIGHT * _COMPOSITE_K * dasha_component, 4)
    # print(
    #     f"FIELD_SCORE_V2 component contributions: d1d10={_d1d10_contrib} "
    #     f"(raw {round(d1d10_component, 4)} x weight {_COMPOSITE_D1D10_WEIGHT} x d9_gate {round(d9_gate, 4)} "
    #     f"x cross-verification {round(corroboration_mult, 4)}), "
    #     f"wealth={_wealth_contrib} (raw {round(wealth_component, 4)} x weight {_COMPOSITE_WEALTH_WEIGHT} x K {_COMPOSITE_K}), "
    #     f"dasha={_dasha_contrib} (raw {round(dasha_component, 4)} x weight {_COMPOSITE_DASHA_WEIGHT} x K {_COMPOSITE_K}) "
    #     f"-> composite={round(composite, 4)}, field_score={round(field_score, 2)}"
    # )
    # if adjusted_strength:
    #     for _planet, _val in adjusted_strength.items():
    #         print(f"FIELD_SCORE_V2 final adjusted_strength — {_planet}: {round(float(_val), 4)}")

    _contribs = {"d1d10": _d1d10_contrib, "wealth": _wealth_contrib, "dasha": _dasha_contrib}
    _dominant = max(_contribs, key=lambda k: abs(_contribs[k])) if any(_contribs.values()) else "d1d10"
    _dominant_txt = {
        "d1d10": "D1 base strength (as gated/scaled by D9 sustainability)",
        "wealth": "the wealth-bonus term",
        "dasha": "the dasha-continuity term",
    }[_dominant]
    # adjusted_strength here holds final per-planet strength values (base
    # strength x the §5/§9 multiplier stack), not the multipliers
    # themselves -- so "moved by the multiplier stack" is read off the
    # spread across planets actually weighted by this field's affinity
    # vector, not an absolute-1.0 comparison.
    _weighted_vals = sorted(
        ((p, float(adjusted_strength.get(p, 0.0))) for p, _w in field_affinity.items()),
        key=lambda pv: pv[1], reverse=True,
    ) if adjusted_strength and field_affinity else []
    _moved_planets = [p for p, v in _weighted_vals[:2] if v > 0]
    _durability_read = (
        "durable (D9-sustainability and dasha-continuity terms carry real weight here, not just "
        "peak D1 placement)" if (_dasha_contrib + (d1d10_component * (d9_gate - 1.0))) > 0
        else "more prestige-only (dominated by raw D1/D10 base strength with little D9/dasha "
        "reinforcement)"
    )
    _corrob_read = (
        "independently corroborated by this field's cross-verification layer (KP/Sudarshana/"
        "K.N. Rao/Yogakaraka/D24/Vimshopaka checks net confirm more than they contradict)"
        if corroboration_mult > 1.02 else
        "cross-verification-neutral (confirmations and contradictions across KP/Sudarshana/"
        "K.N. Rao/Yogakaraka/D24/Vimshopaka roughly cancel out for this field)"
        if corroboration_mult >= 0.98 else
        "net contradicted by this field's cross-verification layer (more of the KP/Sudarshana/"
        "K.N. Rao/Yogakaraka/D24/Vimshopaka checks disagree with the base D1/D10 promise than "
        "confirm it)"
    )
    # print(
    #     f"[COMPOSITE-V2 FIELD-SCORE NARRATIVE] field_score={round(field_score, 2)} is dominated by "
    #     f"{_dominant_txt} (contributing {_contribs[_dominant]} of the {round(composite, 4)} composite). "
    #     f"D9 gate={round(d9_gate, 4)} ({'sustaining' if d9_gate >= 1.0 else 'dampening'} the D1d10 term). "
    #     f"This field is {_corrob_read} (cross-verification multiplier={round(corroboration_mult, 4)}). "
    #     + (
    #         f"Among this field's weighted planets, {', '.join(_moved_planets)} carry the highest "
    #         f"final adjusted_strength (the cumulative product of whichever §5/§9 multipliers were "
    #         f"in play for them). "
    #         if _moved_planets else
    #         "No planet's adjusted_strength could be resolved against this field's affinity vector. "
    #     )
    #     + f"Overall this composite score reads as {_durability_read}."
    # )

    return {
        "d1d10_component": round(d1d10_component, 4),
        "wealth_component": round(wealth_component, 4),
        "dasha_component": round(dasha_component, 4),
        "d9_gate": d9_gate,
        "corroboration_mult": round(corroboration_mult, 4),
        "composite": round(composite, 4),
        "field_score": round(field_score, 2),
    }
