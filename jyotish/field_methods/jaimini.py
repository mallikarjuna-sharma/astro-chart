"""Jaimini field-determination module."""
from __future__ import annotations

from typing import Any, Dict, List

from ..astro import _compute_jaimini_argala, _detect_jaimini_raj_yogas, _compute_bvb_7_karakas
from ..constants import _SIGN_NUM
from ..boosts import (
    _karakamsha_bonus,
    _brahma_lord_bonus,
    _maheshwara_lord_bonus,
    _dharma_karma_bonus,
    _life_science_cluster_bonus,
    _space_aerospace_cluster_bonus,
    _planet_combustion_penalty,
    _dusthana_lord_penalty,
    _d1_vitality_coefficient,
)
from .common import build_score_rubric, clamp_score, method_result, rubric_section, top_weighted_planets


def _zodiac_signs() -> List[str]:
    return [sign for sign, _ in sorted(_SIGN_NUM.items(), key=lambda item: item[1])]


def _house_distance(from_sign: str, to_sign: str) -> int:
    if not from_sign or not to_sign:
        return 0
    zodiac_signs = _zodiac_signs()
    try:
        idx_from = zodiac_signs.index(from_sign)
        idx_to = zodiac_signs.index(to_sign)
    except ValueError:
        return 0
    return ((idx_to - idx_from) % 12) + 1


def _check_chara_drishti(planet_sign: str, target_sign: str) -> bool:
    """Jaimini rasi-drishti with the adjacency exclusion used in the spec."""
    zodiac_signs = _zodiac_signs()
    movable = {"Aries", "Cancer", "Libra", "Capricorn"}
    fixed = {"Taurus", "Leo", "Scorpio", "Aquarius"}
    dual = {"Gemini", "Virgo", "Sagittarius", "Pisces"}

    if not planet_sign or not target_sign or planet_sign == target_sign:
        return False

    try:
        p_idx = zodiac_signs.index(planet_sign)
    except ValueError:
        return False

    adjacent = {
        zodiac_signs[(p_idx - 1) % 12],
        zodiac_signs[(p_idx + 1) % 12],
    }
    if target_sign in adjacent:
        return False

    if planet_sign in movable and target_sign in fixed:
        return True
    if planet_sign in fixed and target_sign in movable:
        return True
    if planet_sign in dual and target_sign in dual:
        return True
    return False


def score_jaimini(payload_data: Any, domain: str, field_affinity: Dict[str, float], field_id: str = "") -> Dict[str, Any]:
    planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    ph = getattr(payload_data, "planet_house", {}) or {}
    jdata = getattr(payload_data, "kn_rao_jaimini", None) or getattr(payload_data, "kn_rao_jaimini_data", None) or {}
    if not isinstance(jdata, dict):
        jdata = {}
    try:
        ak, amk = _compute_bvb_7_karakas(planets_d1)
    except Exception:
        ak, amk = "", ""
    if not ak:
        ak = getattr(payload_data, "atmakaraka", "") or ""
    if not amk:
        amk = getattr(payload_data, "amatyakaraka", "") or ""
    chara_karakas = dict(jdata.get("chara_karakas", {}) or {})
    if ak and "AK" not in chara_karakas:
        chara_karakas["AK"] = ak
    if amk and "AmK" not in chara_karakas:
        chara_karakas["AmK"] = amk
    karakamsha = getattr(payload_data, "karakamsha", "") or jdata.get("karakamsha_sign", "") or ""
    karakamsha_occupants = set(getattr(payload_data, "karakamsha_occupants", []) or [])
    brahma_lord = getattr(payload_data, "brahma_lord", "") or jdata.get("jaimini_special_lords", {}).get("brahma", "") or ""
    maheshwara_lord = getattr(payload_data, "maheshwara_lord", "") or jdata.get("jaimini_special_lords", {}).get("maheshwara", "") or ""
    house_lords = getattr(payload_data, "house_lords", {}) or {}
    upapada = getattr(payload_data, "upapada_lagna", "") or jdata.get("upapada_lagna_sign", "") or ""
    neecha_bhanga = set(getattr(payload_data, "neecha_bhanga_planets", []) or [])

    def _vit(planet: str) -> float:
        return _d1_vitality_coefficient(planet, payload_data) if planet else 1.0

    score = 0.0
    trace: List[str] = []
    components: Dict[str, float] = {}
    rubric_core = 0.0
    rubric_support = 0.0
    rubric_validation = 0.0
    rubric_penalty = 0.0

    # Jaimini matrix: karaka role weight + Karakamsha house modifier + Chara Drishti.
    karaka_weights = {
        "AmK": 2.0,
        "AK": 1.6,
        "PK": 1.4,
        "BK": 1.3,
        "MK": 1.1,
        "GK": 0.8,
        "DK": 0.7,
    }
    jaimini_matrix_score = 0.0
    if karakamsha:
        for planet, info in planets_d1.items():
            if planet in {"Rahu", "Ketu"}:
                continue
            planet_sign = info.get("sign", "") if isinstance(info, dict) else ""
            if not planet_sign:
                continue

            p_karaka = ""
            for k_name, p_name in chara_karakas.items():
                if p_name == planet:
                    p_karaka = k_name
                    break
            base_weight = karaka_weights.get(p_karaka, 1.0)
            house_from_kl = _house_distance(karakamsha, planet_sign)
            house_modifier = 1.0
            if house_from_kl in [1, 10]:
                house_modifier = 1.5
            elif house_from_kl in [2, 5]:
                house_modifier = 1.3
            elif house_from_kl in [6, 8, 12]:
                house_modifier = 0.8
            drishti_boost = 0.5 if _check_chara_drishti(planet_sign, karakamsha) else 0.0
            jaimini_strength = (base_weight * house_modifier) + drishti_boost
            planet_affinity = float(field_affinity.get(planet, 0.0) or 0.0)
            if planet_affinity <= 0.0:
                continue

            # Gap-5 fix: formula is affinity_weight × (karaka_weight × house_modifier + drishti) × 10
            # The ×10 scalar keeps matrix totals comparable with other positive sections.
            contribution = planet_affinity * jaimini_strength * 10.0
            jaimini_matrix_score += contribution
            score += contribution
            rubric_core += contribution
            components[f"{planet.lower()}_karaka_weight"] = round(base_weight, 2)
            components[f"{planet.lower()}_karakamsha_house"] = house_from_kl
            components[f"{planet.lower()}_house_modifier"] = round(house_modifier, 2)
            components[f"{planet.lower()}_drishti_boost"] = round(drishti_boost, 2)
            components[f"{planet.lower()}_jaimini_strength"] = round(jaimini_strength, 4)
            components[f"{planet.lower()}_jaimini_contribution"] = round(contribution, 2)

            trace_bits = [planet]
            if p_karaka:
                trace_bits.append(f"karaka={p_karaka}")
            trace_bits.append(f"karakamsha={karakamsha}")
            trace_bits.append(f"house={house_from_kl}")
            trace_bits.append(f"weight={base_weight:.2f}")
            trace_bits.append(f"modifier={house_modifier:.2f}")
            trace_bits.append(f"drishti={drishti_boost:.2f}")
            trace_bits.append(f"contrib={contribution:.2f}")
            trace.append("Jaimini matrix: " + " | ".join(trace_bits))
    components["jaimini_matrix"] = round(jaimini_matrix_score, 2)

    # C3: Raj yoga weighted by AK/AMK field affinity instead of flat +22.
    raj_yogas = _detect_jaimini_raj_yogas(ak, amk, planets_d1)
    if raj_yogas:
        _ak_w  = field_affinity.get(ak, 0.0) if ak else 0.0
        _amk_w = field_affinity.get(amk, 0.0) if amk else 0.0
        _yoga_affinity = min(1.0, (_ak_w + _amk_w) / 0.50)
        _yoga_bonus = 22.0 * (0.25 + 0.75 * _yoga_affinity)
        _yoga_bonus *= (_vit(ak) + _vit(amk)) / 2.0 if (ak or amk) else 1.0
        score += _yoga_bonus
        rubric_core += _yoga_bonus
        components["raj_yoga"] = round(_yoga_bonus, 2)
        trace.append(
            "Jaimini Raja-yoga support present "
            f"({', '.join(raj_yogas)}; affinity-weighted {_yoga_affinity:.2f})."
        )

    # C2: Argala weighted by field affinity of aspecting planets.
    argala = _compute_jaimini_argala(10, ph)
    if argala:
        _argala_field_wt = sum(field_affinity.get(p, 0.0) for p in argala)
        _argala_avg_aff  = _argala_field_wt / len(argala)
        _raw_count_bonus = max(0.0, min(12.0, (len(argala) - 1.0) * 100.0 * 0.45))
        _alignment = min(1.0, _argala_avg_aff / 0.20)
        argala_vit = sum(_vit(p) for p in argala) / len(argala)
        argala_bonus = _raw_count_bonus * (0.30 + 0.70 * _alignment) * argala_vit
        if argala_bonus > 0:
            trace.append(
                "Argala support from "
                f"{', '.join(argala)} (avg affinity {_argala_avg_aff:.2f}, vitality {argala_vit:.2f})."
            )
    else:
        argala_bonus = 0.0
    score += argala_bonus
    rubric_support += argala_bonus
    components["argala"] = round(argala_bonus, 2)

    karaka_bonus = _karakamsha_bonus(field_affinity, karakamsha) * 100.0
    karaka_bonus *= sum(_vit(p) for p in karakamsha_occupants) / len(karakamsha_occupants) if karakamsha_occupants else 1.0
    score += karaka_bonus
    rubric_core += karaka_bonus
    components["karakamsha"] = round(karaka_bonus, 2)
    if karaka_bonus > 0:
        trace.append(
            f"Karakamsha resonance at {karakamsha} with occupants {sorted(karakamsha_occupants)} "
            f"and matrix score {jaimini_matrix_score:.2f}."
        )

    brahma_bonus = _brahma_lord_bonus(field_id or "", brahma_lord, field_affinity) * 100.0 * _vit(brahma_lord)
    maha_bonus = _maheshwara_lord_bonus(field_id or "", maheshwara_lord, field_affinity) * 100.0 * _vit(maheshwara_lord)
    score += brahma_bonus + maha_bonus
    rubric_core += brahma_bonus + maha_bonus
    components["brahma"] = round(brahma_bonus, 2)
    components["maheshwara"] = round(maha_bonus, 2)
    if brahma_bonus > 0:
        trace.append(f"Brahma lord alignment through {brahma_lord}.")
    if maha_bonus > 0:
        trace.append(f"Maheshwara lord alignment through {maheshwara_lord}.")

    # S5: Normalize keys to strings to avoid int-vs-str mismatch in dharma_karma lookup.
    _hl_str = {str(k): v for k, v in house_lords.items()}
    _ph_str = {k if isinstance(k, str) else str(k): v for k, v in ph.items()}
    h9_lord = _hl_str.get("9", "")
    h10_lord = _hl_str.get("10", "")
    dharma_karma = _dharma_karma_bonus(field_affinity, _hl_str, _ph_str) * 100.0
    dharma_karma *= (_vit(h9_lord) + _vit(h10_lord)) / 2.0 if (h9_lord or h10_lord) else 1.0
    score += dharma_karma
    rubric_core += dharma_karma
    components["dharma_karma"] = round(dharma_karma, 2)
    if dharma_karma > 0:
        trace.append(f"Dharma-Karma linkage through H9 lord {h9_lord} and H10 lord {h10_lord}.")

    if upapada and field_affinity.get("Jupiter", 0.0) >= 0.20:
        _bonus = (100.0 - score) * 0.05 * _vit("Jupiter")
        score += _bonus
        rubric_support += _bonus
        components["upapada"] = round(_bonus, 2)

    for planet in top_weighted_planets(field_affinity, 2):
        if planet in karakamsha_occupants:
            _bonus = (100.0 - score) * 0.025 * _vit(planet)
            score += _bonus
            rubric_validation += _bonus
            components[f"karakamsha_{planet.lower()}"] = round(_bonus, 2)

    life_bonus = _life_science_cluster_bonus(field_id, field_id.replace("_", " "), field_affinity, getattr(payload_data, "eff_strengths", {}) or {}) * 20.0
    space_bonus = _space_aerospace_cluster_bonus(field_id, field_id.replace("_", " "), field_affinity, getattr(payload_data, "eff_strengths", {}) or {}) * 20.0
    if life_bonus > 0:
        _bonus = (100.0 - score) * (life_bonus / 100.0)
        score += _bonus
        rubric_validation += _bonus
        components["life_science_cluster"] = round(_bonus, 2)
    if space_bonus > 0:
        _bonus = (100.0 - score) * (space_bonus / 100.0)
        score += _bonus
        rubric_validation += _bonus
        components["space_aerospace_cluster"] = round(_bonus, 2)

    # Gap-A fix: Jaimini operates at soul/karaka level (Karakamsha is sidereal-soul lagna).
    # Combustion and dusthana lordship affect event-fructification (a KP concern) less
    # than they affect Karakamsha occupants and argala dynamics.  Penalty scale: ×0.60.
    _JAI_PENALTY_SCALE = 0.60

    combustion_penalty = _planet_combustion_penalty(
        field_affinity,
        getattr(payload_data, "combust_planets", []) or [],
        getattr(payload_data, "planet_dignities", {}) or {},
        planets_d1,
    ) * 100.0 * _JAI_PENALTY_SCALE
    if combustion_penalty > 0:
        score -= combustion_penalty
        rubric_penalty -= combustion_penalty
        components["combustion_penalty"] = round(-combustion_penalty, 2)

    dusthana_penalty = _dusthana_lord_penalty(
        field_affinity,
        getattr(payload_data, "lagna_sign", "") or "",
        house_lords,
        getattr(payload_data, "lagna_lord", "") or "",
        field_id or "",
        getattr(payload_data, "eff_strengths", {}) or {},
    ) * 100.0 * _JAI_PENALTY_SCALE
    if dusthana_penalty > 0:
        score -= dusthana_penalty
        rubric_penalty -= dusthana_penalty
        components["dusthana_penalty"] = round(-dusthana_penalty, 2)

    # S3: top-4 vitality penalty; S4: skip Neecha Bhanga planets.
    # Gap-A fix: vitality penalty also scaled ×0.60 for Jaimini — soul-level strength
    # (AK position in Karakamsha) partially compensates D1 vitality impairments.
    for planet in top_weighted_planets(field_affinity, 4):
        if planet in neecha_bhanga:
            continue
        vitality = _d1_vitality_coefficient(planet, payload_data)
        if vitality < 1.0:
            penalty = (1.0 - vitality) * field_affinity.get(planet, 0.0) * 20.0 * _JAI_PENALTY_SCALE
            if penalty > 0:
                score -= penalty
                rubric_penalty -= penalty
                components[f"{planet.lower()}_vitality_penalty"] = round(-penalty, 2)

    rubric = build_score_rubric(
        "jaimini",
        [
            rubric_section(
                "core",
                rubric_core,
                40.0,
                note="Raj yoga, karakamsha, brahma, maheshwara, and dharma-karma links.",
                items=["raj_yoga", "karakamsha", "brahma", "maheshwara", "dharma_karma"],
            ),
            rubric_section(
                "support",
                rubric_support,
                25.0,
                note="Upapada support and argala pressure.",
                items=["argala", "upapada"],
            ),
            rubric_section(
                "penalty",
                rubric_penalty,
                20.0,
                kind="penalty",
                note="Combustion, dusthana, and vitality friction.",
                items=["combustion_penalty", "dusthana_penalty", "_vitality_penalty"],
            ),
        ],
    )

    return method_result("jaimini", clamp_score(score), trace, components, rubric=rubric, normalization_cap=30.0)
