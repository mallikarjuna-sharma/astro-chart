"""Dashamsha (D10) field-determination module.

BPHS dedicates an entire chapter to D10 as the primary career varga.
This method scores the field exclusively from D10 chart structure —
treating D10 as a self-contained career chart with its own lagna,
house lords, yogas, and functional status table.

Scoring rubric (raw cap ~35, normalization cap 35):
  Core       (~40 pts) — D10 lagna lord, D10 H10 lord strength + dignity
  Support    (~25 pts) — D10 H10 occupants, D10 Raj yoga, stellium
  Validation (~20 pts) — D10 lagna sign field affinity, D10 H9 dharma support
  Penalty    (up to −15) — D10 H10 lord in dusthana, D10 H10 combust planets
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from jyotish.boosts import (
    _d1_vitality_coefficient, _karakatwa_domain_bonus, _house_signification_bonus,
    _vimsopaka_bala_coefficient,
    _FUNCTIONAL_STATUS as _D1_FUNCTIONAL_STATUS,
)
from jyotish.constants import _SIGN_LORD, _SIGN_NUM, _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES
from .common import (
    METHOD_SCORE_CAPS,
    build_gate_text,
    build_score_rubric,
    clamp_score,
    method_result,
    rubric_section,
    top_weighted_planets,
)


# ── Functional Status in D10 ──────────────────────────────────────────────────
# Each D10 lagna sign produces its own functional malefic/yogakaraka map.
# Yogakaraka = planet ruling both a kendra (1/4/7/10) AND trikona (1/5/9) in D10.
#
# Consolidation fix (audit): this table used to be a second, hand-transcribed
# copy of boosts.py's `_FUNCTIONAL_STATUS` (same 12-sign x up-to-7-planet
# YOGAKARAKA/MALEFIC/BENEFIC assignment, since D10's functional table follows
# the same whole-sign kendra/trikona rulership logic as D1, just anchored to
# the D10 lagna instead of the D1 lagna). Verified identical to the source
# table cell-by-cell (including all 6 classical yogakarakas: Taurus/Cancer/
# Leo/Libra/Capricorn/Aquarius) before consolidating -- but two independently
# hand-typed copies of the same table is a standing transcription-drift risk
# on the next edit, so this now imports the single canonical table instead of
# maintaining a duplicate.
_D10_FUNCTIONAL_STATUS: Dict[str, Dict[str, str]] = _D1_FUNCTIONAL_STATUS

_DIG_MULT: Dict[str, float] = {
    "EXALTED":       1.40,
    "OWN":           1.20,
    "NEECHA_BHANGA": 1.05,
    "NEUTRAL":       1.00,
    "DEBILITATED":   0.50,
}

_LAGNA_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


def _d10_house_lord(d10_lagna: str, house_num: int) -> str:
    """Lord of the Nth house in D10 using whole-sign house system."""
    if not d10_lagna or d10_lagna not in _SIGN_NUM:
        return ""
    lagna_idx = _SIGN_NUM[d10_lagna] - 1          # 0-based
    target_idx = (lagna_idx + house_num - 1) % 12
    target_sign = _LAGNA_SIGN_ORDER[target_idx]
    return _SIGN_LORD.get(target_sign, "")


def _d10_planet_house(planet: str, d10_chart: Dict, d10_lagna: str) -> int:
    """Whole-sign house of a planet within D10, given D10 lagna sign."""
    if not d10_lagna or d10_lagna not in _SIGN_NUM:
        return 0
    planet_sign = d10_chart.get(planet, "")
    if not planet_sign or planet_sign not in _SIGN_NUM:
        return 0
    lagna_num = _SIGN_NUM[d10_lagna]
    planet_num = _SIGN_NUM[planet_sign]
    return ((planet_num - lagna_num) % 12) + 1


def _d10_functional_factor(planet: str, d10_lagna: str) -> float:
    """Functional status multiplier for a planet given the D10 lagna."""
    status = _D10_FUNCTIONAL_STATUS.get(d10_lagna, {}).get(planet, "NEUTRAL")
    if status == "YOGAKARAKA":
        return 1.15
    if status == "MALEFIC":
        return 0.65
    return 1.00


def _d10_aspects_house(planet: str, planet_house: int, target_house: int) -> bool:
    """True if `planet` sitting in planet_house aspects target_house.

    Fix: previously only the universal 7th-house aspect was modeled, so Mars's
    4th/8th, Jupiter's 5th/9th, and Saturn's 3rd/10th special (Parashari)
    aspects were silently dropped for every D10 calculation. This mirrors the
    same special-aspect convention already used for D1 in astro.py's
    _get_planetary_aspects — applied here to the D10 chart's own house frame.
    """
    if planet_house == 0 or target_house == 0:
        return False
    offset = (target_house - planet_house) % 12  # 0-indexed offset from planet's house
    # Universal 7th aspect: offset 6
    if offset == 6:
        return True
    if planet == "Mars" and offset in (3, 7):       # 4th and 8th
        return True
    if planet == "Jupiter" and offset in (4, 8):     # 5th and 9th
        return True
    if planet == "Saturn" and offset in (2, 9):      # 3rd and 10th
        return True
    return False


def score_dashamsha(
    payload_data: Any,
    domain: str,
    field_affinity: Dict[str, float],
    field_id: str = "",
    field_entry: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """D10 Dashamsha career scorer — BPHS primary career varga.

    Treats D10 as a standalone career chart with its own lagna, house lords,
    and functional planet table. Scores independently of D1.
    """
    # ── Extract D10 data ─────────────────────────────────────────────────────
    d10_chart    = (getattr(payload_data, "divisional_charts", {}) or {}).get("D10_dashamsha", {}) or {}
    d10_lagna    = d10_chart.get("Lagna", "") or ""
    d10_occ      = getattr(payload_data, "d10_house_occupancy", {}) or {}
    d10_digs     = getattr(payload_data, "d10_planet_dignities", {}) or {}
    combust      = set(getattr(payload_data, "combust_planets", []) or [])
    planets_d1   = getattr(payload_data, "planets_d1", {}) or {}
    house_lords  = getattr(payload_data, "house_lords", {}) or {}   # D1 house lords
    d1_h10_lord  = house_lords.get("10", "")
    neecha_bhanga = set(getattr(payload_data, "neecha_bhanga_planets", []) or [])
    # Gap-18b (generalized fix, audit 2026-07): see field_methods/common.py::build_gate_text.
    label        = build_gate_text(field_id, field_entry)

    def _vit(planet: str) -> float:
        return _d1_vitality_coefficient(planet, payload_data) if planet else 1.0

    # 2026-07 astrologer's audit follow-up: this method previously never
    # read payload_data.eff_strengths at all -- of the five field-
    # determination methods, dashamsha (the BPHS-primary career varga) was
    # the one method that ignored planetary Shadbala entirely, even after
    # eff_strengths was upgraded to blend in the new first-principles
    # six-fold Shadbala computation (jyotish/shadbala.py). A D10 H10 lord
    # that is structurally well-placed (kendra/trikona, good dignity) but
    # classically WEAK (low Shadbala) was scored identically to one that is
    # both well-placed and strong -- exactly the "thematically present but
    # actually weak" blind spot flagged by that audit. This adds a bounded
    # [0.85, 1.20] strength multiplier (deliberately narrower than dignity's
    # [0.50, 1.40] range, since Shadbala and dignity are correlated but not
    # identical signals and stacking two wide multipliers would double-count)
    # applied to the method's core structural signals only (D10 lagna lord,
    # D10 H10 lord, D10 Raj yoga, D10 Yogakaraka) -- not to occupancy/aspect
    # signals, which are about placement/connection rather than the planet's
    # own strength.
    _eff_strengths_d = getattr(payload_data, "eff_strengths", {}) or {}

    def _str_mult(planet: str) -> float:
        if not planet:
            return 1.0
        ratio = _eff_strengths_d.get(planet)
        if ratio is None:
            return 1.0
        # eff_strengths is a 0-2.5 ratio (1.0 = meets classical minimum);
        # compress to a bounded [0.85, 1.20] multiplier so a single very
        # high/low ratio can't swamp the structural placement signal it's
        # modifying.
        return round(max(0.85, min(1.20, 0.85 + (ratio / 2.5) * 0.35)), 4)

    score          = 0.0
    trace: List[str] = []
    components: Dict[str, float] = {}
    rubric_core       = 0.0
    rubric_support    = 0.0
    rubric_validation = 0.0
    rubric_penalty    = 0.0

    # ── Early exit if D10 chart absent ───────────────────────────────────────
    if not d10_lagna:
        return method_result(
            "dashamsha", 0.0, ["D10 chart data not available — method skipped."],
            {}, normalization_cap=METHOD_SCORE_CAPS["dashamsha"]
        )

    # ── Precompute D10 house lords ────────────────────────────────────────────
    d10_ll   = _d10_house_lord(d10_lagna, 1)    # D10 lagna lord
    d10_h9l  = _d10_house_lord(d10_lagna, 9)    # D10 9th lord (dharma)
    d10_h10l = _d10_house_lord(d10_lagna, 10)   # D10 10th lord (career)
    d10_h5l  = _d10_house_lord(d10_lagna, 5)    # D10 5th lord (intelligence/past karma)

    # Positions of key lords within D10
    d10_ll_house   = _d10_planet_house(d10_ll,   d10_chart, d10_lagna) if d10_ll   else 0
    d10_h10l_house = _d10_planet_house(d10_h10l, d10_chart, d10_lagna) if d10_h10l else 0
    d10_h9l_house  = _d10_planet_house(d10_h9l,  d10_chart, d10_lagna) if d10_h9l  else 0

    d10_h10_planets = d10_occ.get("10", []) or d10_occ.get(10, [])
    d10_h1_planets  = d10_occ.get("1",  []) or d10_occ.get(1, [])

    # ── C1: D10 Lagna Lord in kendra/trikona of D10 ──────────────────────────
    # The D10 lagna lord represents the native's career identity in the dashamsha.
    # Placed in kendra/trikona → strong professional self-expression.
    if d10_ll and d10_ll_house in _KT_HOUSES:
        _ll_aff   = field_affinity.get(d10_ll, 0.0)
        _ll_dig_m = _DIG_MULT.get(d10_digs.get(d10_ll, "NEUTRAL"), 1.0)
        _ll_func  = _d10_functional_factor(d10_ll, d10_lagna)
        _ll_vit   = _vit(d10_ll)
        _ll_pts   = max(_ll_aff * 12.0, 2.5) * _ll_dig_m * _ll_func * _ll_vit * _str_mult(d10_ll)
        score += _ll_pts; rubric_core += _ll_pts
        components["d10_lagna_lord_kendra"] = round(_ll_pts, 2)
        trace.append(
            f"D10 lagna lord {d10_ll} in D10 H{d10_ll_house} "
            f"({d10_digs.get(d10_ll,'?')}) — career identity strong."
        )
    elif d10_ll and d10_ll_house in _DUSTHANA_HOUSES:
        _pen = field_affinity.get(d10_ll, 0.0) * 6.0 * _vit(d10_ll)
        score -= _pen; rubric_penalty -= _pen
        components["d10_lagna_lord_dusthana"] = round(-_pen, 2)
        trace.append(f"D10 lagna lord {d10_ll} in dusthana H{d10_ll_house} — weakens career expression.")

    # ── C2: D10 H10 Lord strength and dignity within D10 ─────────────────────
    # This is the most direct D10 career signal: where does the 10th house
    # lord of the dashamsha sit within its own chart?
    if d10_h10l:
        _h10l_dig  = d10_digs.get(d10_h10l, "NEUTRAL")
        _h10l_dm   = _DIG_MULT.get(_h10l_dig, 1.0)
        _h10l_func = _d10_functional_factor(d10_h10l, d10_lagna)
        _h10l_aff  = field_affinity.get(d10_h10l, 0.0)
        _h10l_vit  = _vit(d10_h10l)

        if d10_h10l_house in _KT_HOUSES:
            # Kendra/trikona placement — full strength
            _h10l_pts = max(_h10l_aff * 18.0, 3.0) * _h10l_dm * _h10l_func * _h10l_vit * _str_mult(d10_h10l)
            score += _h10l_pts; rubric_core += _h10l_pts
            components["d10_h10_lord_kendra"] = round(_h10l_pts, 2)
            trace.append(
                f"D10 H10 lord {d10_h10l} in D10 H{d10_h10l_house} "
                f"({_h10l_dig}) — primary dashamsha career yoga."
            )
        elif d10_h10l_house in _DUSTHANA_HOUSES:
            # Dusthana placement — penalty
            _h10l_pen = max(_h10l_aff * 10.0, 2.0) * _h10l_vit
            score -= _h10l_pen; rubric_penalty -= _h10l_pen
            components["d10_h10_lord_dusthana"] = round(-_h10l_pen, 2)
            trace.append(f"D10 H10 lord {d10_h10l} in D10 dusthana H{d10_h10l_house}.")
        else:
            # Neutral placement (H2/H3/H6/H8/H11/H12 that aren't dusthana)
            _h10l_pts = max(_h10l_aff * 8.0, 1.5) * _h10l_dm * 0.7 * _h10l_vit
            score += _h10l_pts; rubric_core += _h10l_pts
            components["d10_h10_lord_neutral"] = round(_h10l_pts, 2)

        # Dignity bonus regardless of house — exalted D10 H10 lord is a stellar signal
        if _h10l_dig in ("EXALTED", "OWN") and d10_h10l_house not in _DUSTHANA_HOUSES:
            _dig_bonus = _h10l_aff * 8.0 * _h10l_vit
            score += _dig_bonus; rubric_core += _dig_bonus
            components["d10_h10_lord_dignity_bonus"] = round(_dig_bonus, 2)
            trace.append(f"D10 H10 lord {d10_h10l} is {_h10l_dig} in D10 — exceptional career strength.")

    # ── C3: D10 H10 Occupants — planets physically in D10's 10th house ───────
    for planet in d10_h10_planets:
        if planet in ("Rahu", "Ketu"):
            _rk_aff = field_affinity.get(planet, 0.0)
            if _rk_aff >= 0.10:
                _rk_b = _rk_aff * 6.0 * _vit(planet)
                score += _rk_b; rubric_support += _rk_b
                components[f"d10_h10_{planet.lower()}"] = round(_rk_b, 2)
            continue
        _occ_aff = field_affinity.get(planet, 0.0)
        _occ_dig = d10_digs.get(planet, "NEUTRAL")
        _occ_dm  = _DIG_MULT.get(_occ_dig, 1.0)
        _occ_func= _d10_functional_factor(planet, d10_lagna)
        _occ_vit = _vit(planet)

        if _occ_aff >= 0.08:
            _occ_pts = _occ_aff * 12.0 * _occ_dm * _occ_func * _occ_vit
            score += _occ_pts; rubric_support += _occ_pts
            components[f"d10_h10_{planet.lower()}"] = round(_occ_pts, 2)
            if _occ_pts > 1.0:
                trace.append(
                    f"{planet} in D10 H10 ({_occ_dig}) with affinity {_occ_aff:.2f} "
                    f"— dashamsha occupant signal."
                )

    # ── C4: D10 Raj Yoga — H9 lord + H10 lord connected in D10 ──────────────
    # Classical rule: when the lord of dharma (H9) and karma (H10) in D10 are
    # in conjunction (same house) or mutual 7th aspect, it creates a D10 Raj yoga.
    if d10_h9l and d10_h10l and d10_h9l != d10_h10l:
        _ry_conj = (d10_h9l_house > 0 and d10_h9l_house == d10_h10l_house)
        _ry_7th  = (
            d10_h9l_house > 0 and d10_h10l_house > 0 and
            (d10_h9l_house + 6 - 1) % 12 + 1 == d10_h10l_house
        )
        if _ry_conj or _ry_7th:
            _ry_aff = (field_affinity.get(d10_h9l, 0.0) + field_affinity.get(d10_h10l, 0.0))
            _ry_vit = (_vit(d10_h9l) + _vit(d10_h10l)) / 2.0
            _ry_pts = max(_ry_aff * 14.0, 3.0) * _ry_vit * ((_str_mult(d10_h9l) + _str_mult(d10_h10l)) / 2.0)
            score += _ry_pts; rubric_support += _ry_pts
            components["d10_raj_yoga"] = round(_ry_pts, 2)
            _ry_type = "conjunction" if _ry_conj else "mutual aspect"
            trace.append(
                f"D10 Raj yoga: H9 lord {d10_h9l} + H10 lord {d10_h10l} in "
                f"{_ry_type} within D10 (dharma-karma union)."
            )

    # ── C5: D10 H10 Stellium (2+ field planets in D10 H10) ───────────────────
    _field_planets_in_d10_h10 = [
        p for p in d10_h10_planets if field_affinity.get(p, 0.0) >= 0.10
    ]
    if len(_field_planets_in_d10_h10) >= 2:
        _stl_aff = sum(field_affinity.get(p, 0.0) for p in _field_planets_in_d10_h10)
        _stl_vit = sum(_vit(p) for p in _field_planets_in_d10_h10) / len(_field_planets_in_d10_h10)
        _stl_pts = _stl_aff * 10.0 * _stl_vit
        score += _stl_pts; rubric_support += _stl_pts
        components["d10_h10_stellium"] = round(_stl_pts, 2)
        trace.append(
            f"D10 H10 stellium: {', '.join(_field_planets_in_d10_h10)} "
            f"all occupy D10 10th house — career mandate reinforced."
        )

    # ── C5b: Parashari aspect (incl. special aspects) onto D10 H10 ───────────
    # Fix: _d10_aspects_house was defined but never called anywhere in this
    # module — the special-aspect logic was dead code. Now scans every placed
    # planet for an aspect (7th, or Mars 4th/8th, Jupiter 5th/9th, Saturn
    # 3rd/10th) onto D10 H10 and rewards field-aligned aspecting planets that
    # are not already occupants (occupancy is scored separately above).
    for _asp_p, _asp_info in planets_d1.items():
        if _asp_p in d10_h10_planets:
            continue
        _asp_house = _d10_planet_house(_asp_p, d10_chart, d10_lagna)
        if not _asp_house:
            continue
        if _d10_aspects_house(_asp_p, _asp_house, 10):
            _asp_aff = field_affinity.get(_asp_p, 0.0)
            if _asp_aff >= 0.10:
                _asp_dig = d10_digs.get(_asp_p, "NEUTRAL")
                _asp_dm  = _DIG_MULT.get(_asp_dig, 1.0)
                _asp_func = _d10_functional_factor(_asp_p, d10_lagna)
                _asp_pts = _asp_aff * 7.0 * _asp_dm * _asp_func * _vit(_asp_p)
                score += _asp_pts; rubric_support += _asp_pts
                components[f"d10_h10_aspect_{_asp_p.lower()}"] = round(_asp_pts, 2)
                if _asp_pts > 1.0:
                    trace.append(
                        f"{_asp_p} in D10 H{_asp_house} aspects D10 H10 "
                        f"({_asp_dig}) — career house reinforced by Parashari drishti."
                    )

    # ── C6: D10 Yogakaraka planet strength ───────────────────────────────────
    # If the D10 lagna has a Yogakaraka planet, and that planet is in D10 kendra/trikona,
    # it confers a special career yoga exclusive to this lagna.
    _d10_yk = next(
        (p for p, s in _D10_FUNCTIONAL_STATUS.get(d10_lagna, {}).items() if s == "YOGAKARAKA"),
        ""
    )
    if _d10_yk:
        _yk_house = _d10_planet_house(_d10_yk, d10_chart, d10_lagna)
        if _yk_house in _KT_HOUSES:
            _yk_aff  = field_affinity.get(_d10_yk, 0.0)
            _yk_dig  = d10_digs.get(_d10_yk, "NEUTRAL")
            _yk_dm   = _DIG_MULT.get(_yk_dig, 1.0)
            _yk_vit  = _vit(_d10_yk)
            _yk_pts  = max(_yk_aff * 14.0, 2.0) * _yk_dm * _yk_vit * _str_mult(_d10_yk)
            score += _yk_pts; rubric_core += _yk_pts
            components["d10_yogakaraka"] = round(_yk_pts, 2)
            trace.append(
                f"D10 Yogakaraka {_d10_yk} in D10 H{_yk_house} ({_yk_dig}) "
                f"— functional yoga for {d10_lagna} D10 lagna."
            )

    # ── V1: D10 Lagna Sign Field Affinity ────────────────────────────────────
    # The D10 lagna sign's natural lord indicates the domain of career destiny.
    # E.g. D10 lagna in Aries → Mars rules → Mars-aligned fields supported.
    _d10_ll_natural = _SIGN_LORD.get(d10_lagna, "")
    if _d10_ll_natural:
        _d10_ln_aff = field_affinity.get(_d10_ll_natural, 0.0)
        if _d10_ln_aff >= 0.12:
            _ln_vit = _vit(_d10_ll_natural)
            _ln_pts = _d10_ln_aff * 9.0 * _ln_vit
            score += _ln_pts; rubric_validation += _ln_pts
            components["d10_lagna_sign_affinity"] = round(_ln_pts, 2)
            trace.append(
                f"D10 lagna {d10_lagna} ruled by {_d10_ll_natural} "
                f"(affinity {_d10_ln_aff:.2f}) — dashamsha career sign aligns with field."
            )

    # ── V2: D10 H9 lord in kendra/trikona (dharma supports career) ───────────
    if d10_h9l and d10_h9l_house in _KT_HOUSES:
        _h9l_aff  = field_affinity.get(d10_h9l, 0.0)
        _h9l_dig  = d10_digs.get(d10_h9l, "NEUTRAL")
        _h9l_dm   = _DIG_MULT.get(_h9l_dig, 1.0)
        _h9l_vit  = _vit(d10_h9l)
        _h9l_pts  = max(_h9l_aff * 8.0, 1.5) * _h9l_dm * _h9l_vit
        score += _h9l_pts; rubric_validation += _h9l_pts
        components["d10_h9_dharma_support"] = round(_h9l_pts, 2)
        trace.append(f"D10 H9 (dharma) lord {d10_h9l} in D10 kendra/trikona — career has dharmic backing.")

    # ── V3: D1 H10 lord occupies D10 H10 (double career mandate) ─────────────
    # When the planet that lords D1 H10 also physically sits in D10 H10,
    # the career house is doubly emphasised across both natal and dashamsha.
    if d1_h10_lord and d1_h10_lord in d10_h10_planets:
        _d1h10_aff = field_affinity.get(d1_h10_lord, 0.0)
        _d1h10_vit = _vit(d1_h10_lord)
        _d1h10_pts = max(_d1h10_aff * 10.0, 2.5) * _d1h10_vit
        score += _d1h10_pts; rubric_validation += _d1h10_pts
        components["d1_h10_lord_in_d10_h10"] = round(_d1h10_pts, 2)
        trace.append(
            f"D1 H10 lord {d1_h10_lord} occupies D10 H10 — "
            f"career mandate echoes across natal and dashamsha."
        )

    # ── V4: D10 H5 lord in kendra/trikona (intelligence + past karma) ────────
    d10_h5l_house = _d10_planet_house(d10_h5l, d10_chart, d10_lagna) if d10_h5l else 0
    if d10_h5l and d10_h5l_house in _KT_HOUSES:
        _h5l_aff = field_affinity.get(d10_h5l, 0.0)
        if _h5l_aff >= 0.10:
            _h5l_dm  = _DIG_MULT.get(d10_digs.get(d10_h5l, "NEUTRAL"), 1.0)
            _h5l_pts = _h5l_aff * 6.0 * _h5l_dm * _vit(d10_h5l)
            score += _h5l_pts; rubric_validation += _h5l_pts
            components["d10_h5_intelligence"] = round(_h5l_pts, 2)

    # ── P1: Combust planets in D10 H10 weaken career delivery ────────────────
    for planet in d10_h10_planets:
        if planet in combust and planet not in neecha_bhanga:
            _comb_aff = field_affinity.get(planet, 0.0)
            _comb_pen = _comb_aff * 5.0
            if _comb_pen > 0:
                score -= _comb_pen; rubric_penalty -= _comb_pen
                components[f"d10_h10_{planet.lower()}_combust"] = round(-_comb_pen, 2)
                trace.append(f"{planet} combust in D10 H10 — dashamsha delivery weakened.")

    # ── P2: D10 functional malefic in D10 H10 ────────────────────────────────
    for planet in d10_h10_planets:
        if _D10_FUNCTIONAL_STATUS.get(d10_lagna, {}).get(planet, "") == "MALEFIC":
            _fm_aff = field_affinity.get(planet, 0.0)
            _fm_pen = max(_fm_aff * 4.0, 1.0) * _vit(planet)
            score -= _fm_pen; rubric_penalty -= _fm_pen
            components[f"d10_{planet.lower()}_funcmal_h10"] = round(-_fm_pen, 2)

    # ── Systematic karaka-domain bonus (cross-cutting gap fix) ────────────────
    # Same shared BPHS/Jataka Parijata karakatwa fallback used elsewhere. Uses
    # D1 house placement (career capacity in the natal chart) alongside D10
    # field-affinity weighting, since this is a general significator check, not
    # a D10-specific structural one (those are already covered above).
    _ph_d1 = getattr(payload_data, "planet_house", {}) or {}
    _karaka_dom_b_d, _karaka_dom_hits_d = _karakatwa_domain_bonus(
        domain, field_affinity, planets_d1, _ph_d1, payload_data, scale=5.0, cap=10.0,
    )
    if _karaka_dom_b_d > 0:
        score += _karaka_dom_b_d; rubric_support += _karaka_dom_b_d
        components["karaka_domain_bonus"] = round(_karaka_dom_b_d, 2)
        trace.append(
            f"Karakatwa domain match ({domain}): {', '.join(_karaka_dom_hits_d)} carry classical "
            "significator authority for this domain (systematic karaka-to-field mapping)."
        )

    # ── Ontology fix: house-signification-first primitive ────────────────────
    # Unlike the other four methods, this scorer is entirely D10-scoped and
    # never consults D1 house lordship at all. Classical practice
    # cross-validates D1 and D10 rather than treating them as unrelated;
    # this adds the D1 domain-significant-house signal (H6/H8/H12 for
    # medicine, H6/H7/H9 for law, etc.) as a light natal cross-check
    # alongside D10's own structural scoring above.
    _house_dom_b_d, _house_dom_hits_d = _house_signification_bonus(
        domain, field_affinity, house_lords, _ph_d1, planets_d1, payload_data, scale=4.0, cap=8.0,
    )
    if _house_dom_b_d > 0:
        score += _house_dom_b_d; rubric_support += _house_dom_b_d
        components["house_signification_bonus"] = round(_house_dom_b_d, 2)
        trace.append(
            f"D1 house signification ({domain}): {', '.join(_house_dom_hits_d)} lord(s) "
            "cross-validate the D10 career picture from the natal chart."
        )

    # ── Vimshopaka Bala: unified divisional-strength coefficient ─────────────
    # D10 already dominates this method's own scoring, so the nudge here is
    # deliberately small — it reconciles D10 with the other computed vargas
    # (D1/D3/D9/D20/D24/D30) rather than duplicating D10's own weight.
    _vim_planets_d = [p for p in (d10_ll, d10_h10l) if p]
    if _vim_planets_d:
        _vim_avg_d = sum(_vimsopaka_bala_coefficient(p, payload_data) for p in _vim_planets_d) / len(_vim_planets_d)
        _vim_adj_d = (_vim_avg_d - 1.0) * 10.0
        if abs(_vim_adj_d) > 0.05:
            score += _vim_adj_d
            rubric_validation += _vim_adj_d
            components["vimsopaka_bala"] = round(_vim_adj_d, 2)
            trace.append(
                f"Vimshopaka Bala for D10 lagna/H10 lord ({', '.join(_vim_planets_d)}): "
                f"avg coefficient {_vim_avg_d:.2f} -- unified divisional strength "
                f"{'supports' if _vim_adj_d > 0 else 'weakens'} this field."
            )

    rubric = build_score_rubric(
        "dashamsha",
        [
            rubric_section(
                "core", rubric_core, 40.0,
                note="D10 lagna lord, D10 H10 lord strength/dignity, yogakaraka.",
                items=["d10_lagna_lord_kendra", "d10_h10_lord_kendra",
                       "d10_h10_lord_dignity_bonus", "d10_yogakaraka"],
            ),
            rubric_section(
                "support", rubric_support, 25.0,
                note="D10 H10 occupants, D10 Raj yoga, stellium, aspects onto D10 H10, karakatwa domain, "
                     "and D1 house-signification cross-check.",
                items=["d10_h10_occupants", "d10_raj_yoga", "d10_h10_stellium", "d10_h10_aspect",
                       "karaka_domain_bonus", "house_signification_bonus"],
            ),
            rubric_section(
                "validation", rubric_validation, 20.0,
                note="D10 lagna sign affinity, H9 dharma, D1 H10 lord in D10 H10, Vimshopaka Bala.",
                items=["d10_lagna_sign_affinity", "d10_h9_dharma_support",
                       "d1_h10_lord_in_d10_h10", "d10_h5_intelligence", "vimsopaka_bala"],
            ),
            rubric_section(
                "penalty", rubric_penalty, 15.0, kind="penalty",
                note="D10 H10 lord in dusthana, combust occupants, functional malefics.",
                items=["d10_lagna_lord_dusthana", "d10_h10_lord_dusthana",
                       "d10_h10_combust", "d10_funcmal_h10"],
            ),
        ],
    )

    # Gap-3/9 fix: pass raw signed `score` (not pre-clamped) so contraindicated
    # charts (net penalties > positives) are distinguishable from neutral ones;
    # method_result() still clamps internally for the "score" field.
    return method_result(
        "dashamsha", score, trace, components, rubric=rubric,
        normalization_cap=METHOD_SCORE_CAPS["dashamsha"])
