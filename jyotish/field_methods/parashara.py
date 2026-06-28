"""Parashara field-determination module."""
from __future__ import annotations

from typing import Any, Dict, List

from ..boosts import (
    _yogakaraka_bonus, _h10_lord_strength_bonus, _h10_lord_trikona_bonus,
    _exalted_planet_domain_bonus, _aspect_h10_bonus, _yoga_bonus,
    _stellium_bonus, _dusthana_lord_penalty, _dharma_karma_bonus,
    _life_science_cluster_bonus, _space_aerospace_cluster_bonus,
    _d24_full_chart_bonus,
    _planet_combustion_penalty,
    _d9_h10_bonus,
    _d10_lagna_lord_bonus,
    _d1_vitality_coefficient,
)
from .common import build_score_rubric, clamp_score, method_result, rubric_section, top_weighted_planets


def score_parashara(payload_data: Any, domain: str, field_affinity: Dict[str, float], field_id: str = "") -> Dict[str, Any]:
    planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    ph = getattr(payload_data, "planet_house", {}) or {}
    shadbala = getattr(payload_data, "shadbala", {}) or {}
    planet_dignities = getattr(payload_data, "planet_dignities", {}) or {}
    house_lords = getattr(payload_data, "house_lords", {}) or {}
    lagna_sign = getattr(payload_data, "lagna_sign", "") or ""
    lagna_lord = getattr(payload_data, "lagna_lord", "") or ""
    h10_lord = getattr(payload_data, "h10_lord", "") or ""
    yogas = getattr(payload_data, "detected_yogas", []) or []
    eff_strengths = getattr(payload_data, "eff_strengths", {}) or {}
    combust_planets = getattr(payload_data, "combust_planets", []) or []
    neecha_bhanga = set(getattr(payload_data, "neecha_bhanga_planets", []) or [])
    d10_occ = getattr(payload_data, "d10_house_occupancy", {}) or {}

    score = 0.0
    trace: List[str] = []
    components: Dict[str, float] = {}
    rubric_core = 0.0
    rubric_support = 0.0
    rubric_validation = 0.0
    rubric_penalty = 0.0

    yg = _yogakaraka_bonus(field_affinity, lagna_sign, shadbala, planet_dignities) * 100.0
    hl = _h10_lord_strength_bonus(field_affinity, h10_lord, shadbala, planet_dignities) * 100.0
    ht = _h10_lord_trikona_bonus(field_affinity, h10_lord, ph, planet_dignities) * 100.0
    dh = _dharma_karma_bonus(field_affinity, house_lords, ph) * 100.0
    ex = _exalted_planet_domain_bonus(field_affinity, planet_dignities, field_id or "", lagna_sign) * 100.0
    as10 = _aspect_h10_bonus(field_affinity, ph, planet_dignities, planets_d1) * 100.0
    yog = _yoga_bonus(field_id or "", yogas, house_lords, planet_dignities) * 100.0
    st = _stellium_bonus(field_id or "", ph) * 100.0
    # Gap-A fix: dusthana penalty also scaled ×0.75 for Parashara (applied after _PARA_PENALTY_SCALE is defined below).
    # Raw value computed here; scaling applied at deduction.
    dp = _dusthana_lord_penalty(field_affinity, lagna_sign, house_lords, lagna_lord, field_id or "", eff_strengths) * 100.0

    # Gap-7 fix: split into rubric_core (structural fundamentals) and rubric_support
    # (dignity-match / aspect / yoga / stellium extras that support but don't define the field).
    # Previously all 8 items went to rubric_core, making support section near-empty.
    for key, val in (
        ("yogakaraka", yg),
        ("h10_lord_strength", hl),
        ("h10_lord_trikona", ht),
        ("dharma_karma", dh),
    ):
        score += val
        rubric_core += val
        if val > 0:
            components[key] = round(val, 2)

    for key, val in (
        ("exalted_domain", ex),
        ("aspect_h10", as10),
        ("yoga", yog),
        ("stellium", st),
    ):
        score += val
        rubric_support += val
        if val > 0:
            components[key] = round(val, 2)

    # Gap-A fix: scale dusthana_penalty by _PARA_PENALTY_SCALE (×0.75); defined further below
    # but constant value referenced here for clarity.
    _dp_scaled = dp * 0.75
    score -= _dp_scaled
    if _dp_scaled > 0:
        rubric_penalty -= _dp_scaled
        components["dusthana_penalty"] = round(-_dp_scaled, 2)

    # S2: Apply vitality gate to exalted/own bonus — Mrita/combust planets should not get full bonus
    for planet in top_weighted_planets(field_affinity, 2):
        dig = planet_dignities.get(planet, "")
        if dig in ("EXALTED", "OWN"):
            # S4: Neecha Bhanga — cancelled debilitation treated as neutral, not a bonus here;
            # this block only fires for EXALTED/OWN so neecha_bhanga doesn't change logic here.
            vit = _d1_vitality_coefficient(planet, payload_data)
            bonus = 3.5 * field_affinity.get(planet, 0.0) * vit
            if bonus > 0:
                score += bonus
                rubric_support += bonus
                components[f"{planet.lower()}_exalted_bonus"] = round(bonus, 2)

    life_bonus = _life_science_cluster_bonus(field_id, field_id.replace("_", " "), field_affinity, eff_strengths) * 20.0
    space_bonus = _space_aerospace_cluster_bonus(field_id, field_id.replace("_", " "), field_affinity, eff_strengths) * 20.0
    if life_bonus > 0:
        score += life_bonus
        rubric_support += life_bonus
        components["life_science_cluster"] = round(life_bonus, 2)
    if space_bonus > 0:
        score += space_bonus
        rubric_support += space_bonus
        components["space_aerospace_cluster"] = round(space_bonus, 2)

    # Gap-A fix: Parashara's yoga system (Raj yoga, Dhana yoga, Yogakaraka) can partially
    # override combustion and dusthana effects — a combust yogakaraka still activates the
    # yoga, it just delivers results with some delay.  Penalty scale: ×0.75.
    _PARA_PENALTY_SCALE = 0.75

    combustion_penalty = _planet_combustion_penalty(
        field_affinity,
        combust_planets,
        planet_dignities,
        planets_d1,
    ) * 100.0 * _PARA_PENALTY_SCALE
    if combustion_penalty > 0:
        score -= combustion_penalty
        rubric_penalty -= combustion_penalty
        components["combustion_penalty"] = round(-combustion_penalty, 2)

    # S3: Extend vitality penalty to top-4 field planets (was top-2)
    # S4: Skip vitality penalty if planet has Neecha Bhanga (cancelled debilitation = neutral)
    # Gap-A fix: vitality penalty scaled ×0.75 — Parashara's yogas compensate moderate impairment.
    for planet in top_weighted_planets(field_affinity, 4):
        if planet in neecha_bhanga:
            continue  # Neecha Bhanga: cancellation restores to neutral — no vitality penalty
        vitality = _d1_vitality_coefficient(planet, payload_data)
        if vitality < 1.0:
            penalty = (1.0 - vitality) * field_affinity.get(planet, 0.0) * 20.0 * _PARA_PENALTY_SCALE
            if penalty > 0:
                score -= penalty
                rubric_penalty -= penalty
                components[f"{planet.lower()}_vitality_penalty"] = round(-penalty, 2)

    # D10 Dashamsha cross-validation: D10 lagna lord in H10 + H10 occupants affirm career.
    d10_chart  = getattr(payload_data, "divisional_charts", {}).get("D10_dashamsha", {}) or {}
    d10_lagna  = d10_chart.get("Lagna", "") or ""
    from ..constants import _SIGN_LORD
    d10_ll     = _SIGN_LORD.get(d10_lagna, "")
    d10_bonus  = 0.0
    d10_h10_planets = d10_occ.get("10", []) or d10_occ.get(10, [])  # M3: fixed missing [] default
    if d10_ll and d10_ll in d10_h10_planets:
        d10_bonus += 6.0 * field_affinity.get(d10_ll, 0.0) * _d1_vitality_coefficient(d10_ll, payload_data)
        trace.append(f"D10 lagna lord {d10_ll} occupies D10 H10 — strong dashamsha career yoga.")
    else:
        for p in d10_h10_planets:
            w = field_affinity.get(p, 0.0)
            if w >= 0.10:
                d10_bonus += 2.5 * w * _d1_vitality_coefficient(p, payload_data)
    d10_bonus = min(d10_bonus, 10.0)
    if d10_bonus > 0:
        score += d10_bonus
        rubric_validation += d10_bonus
        components["d10_validation"] = round(d10_bonus, 2)

    # C1: Restore orphaned D9/D24/D10-lagna-lord bonus calls (lost during file corruption fix)
    d9_chart     = getattr(payload_data, "divisional_charts", {}).get("D9_navamsha", {}) or {}
    d9_lagna     = getattr(payload_data, "d9_lagna_sign", "") or d9_chart.get("Lagna", "") or ""
    d9_bonus     = _d9_h10_bonus(field_affinity, d9_chart, d9_lagna, payload_data) * 100.0
    if d9_bonus > 0:
        score += d9_bonus
        rubric_validation += d9_bonus
        components["d9_h10"] = round(d9_bonus, 2)
        trace.append("Navamsha H10 placement affirms Parashara career yoga.")

    d24_bonus = _d24_full_chart_bonus(field_affinity, payload_data) * 100.0
    if d24_bonus > 0:
        score += d24_bonus
        rubric_validation += d24_bonus
        components["d24_bonus"] = round(d24_bonus, 2)
        trace.append("Siddhamsha (D24) dignified planets support educational/professional domain.")

    d10_ll_dig_bonus = _d10_lagna_lord_bonus(field_affinity, d10_chart, d10_lagna) * 100.0
    if d10_ll_dig_bonus > 0:
        d10_ll_dig_bonus *= _d1_vitality_coefficient(d10_ll, payload_data)
        if d10_ll_dig_bonus > 0:
            score += d10_ll_dig_bonus
            rubric_validation += d10_ll_dig_bonus
            components["d10_ll_bonus"] = round(d10_ll_dig_bonus, 2)
        trace.append("D10 lagna lord dignified — dashamsha career path has structural support.")
    rubric = build_score_rubric(
        "parashara",
        [
            rubric_section(
                "core",
                rubric_core,
                40.0,
                note="Yogakaraka, H10 lord, and dharma-karma fundamentals.",
                items=["yogakaraka", "h10_lord_strength", "h10_lord_trikona", "dharma_karma"],
            ),
            rubric_section(
                "support",
                rubric_support,
                25.0,
                note="Dignity-matched field support, aspects, yogas, and stellium.",
                items=["exalted_domain", "aspect_h10", "yoga", "stellium", "_exalted_bonus",
                       "life_science_cluster", "space_aerospace_cluster"],
            ),
            rubric_section(
                "validation",
                rubric_validation,
                20.0,
                note="D10, D9, and D24 confirmation signals.",
                items=["d10_validation", "d9_h10", "d24_bonus", "d10_ll_bonus"],
            ),
            rubric_section(
                "penalty",
                rubric_penalty,
                20.0,
                kind="penalty",
                note="Dusthana, combustion, and vitality friction.",
                items=["dusthana_penalty", "combustion_penalty", "_vitality_penalty"],
            ),
        ],
    )

    return method_result("parashara", clamp_score(score), trace, components, rubric=rubric, normalization_cap=55.0)
