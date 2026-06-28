"""KP field-determination module."""
from __future__ import annotations

from typing import Any, Dict, List

from ..boosts import (
    _kp_h10_branch_strength,
    _kp_career_h2h11_strength,
    _kp_edu_branch_strength,
    _h10_sublord_bonus,
    _kp_edu_starlord_bonus,
    _life_science_cluster_bonus,
    _space_aerospace_cluster_bonus,
    _planet_combustion_penalty,
    _dusthana_lord_penalty,
    _d1_vitality_coefficient,
)
from .common import build_score_rubric, clamp_score, method_result, rubric_section, top_weighted_planets

# Earth/underground-domain field cluster — H8 career indicator applies for these
_EARTH_FIELD_HINTS = (
    "mining", "petroleum", "oil_gas", "metallurg", "geology", "geological",
    "mineral", "ore", "excavat", "quarr", "drill",
    "materials_science", "polymer", "rubber", "leather", "ceramic",
    "water_resource", "coal", "foundry",
)

def _is_earth_field(field_id: str, label: str) -> bool:
    combined = f"{field_id} {label}".lower()
    return any(h in combined for h in _EARTH_FIELD_HINTS)


def score_kp(payload_data: Any, domain: str, field_affinity: Dict[str, float], field_id: str = "") -> Dict[str, Any]:
    kp_sigs   = getattr(payload_data, "kp_significators", {}) or {}
    kp_cusps  = getattr(payload_data, "kp_cusps", {}) or {}
    d10_occ   = getattr(payload_data, "d10_house_occupancy", {}) or {}
    label     = field_id.replace("_", " ").lower()
    neecha_bhanga = set(getattr(payload_data, "neecha_bhanga_planets", []) or [])

    def _vit(planet: str) -> float:
        return _d1_vitality_coefficient(planet, payload_data) if planet else 1.0

    score = 0.0
    trace: List[str] = []
    components: Dict[str, float] = {}
    rubric_core       = 0.0
    rubric_support    = 0.0
    rubric_validation = 0.0
    rubric_penalty    = 0.0

    branch_strength = _kp_h10_branch_strength(field_affinity, kp_sigs)
    sublord_bonus   = _h10_sublord_bonus(field_affinity, kp_cusps)
    edu_star_bonus  = _kp_edu_starlord_bonus(field_affinity, kp_cusps)

    # ── H10 career branch vitality gate ──────────────────────────────────────
    branch_vitality_total  = 0.0
    branch_vitality_weight = 0.0
    for planet, weight in field_affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
            if 10 in sig.get(key, []):
                branch_piece = weight * (1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25)
                branch_vitality_total  += branch_piece * _vit(planet)
                branch_vitality_weight += branch_piece
                break

    branch_vitality = (branch_vitality_total / branch_vitality_weight) if branch_vitality_weight > 0 else 1.0
    _h10_branch     = 40.0 * branch_strength * branch_vitality

    h10_sub      = kp_cusps.get("H10", {}).get("sub_lord", "")
    _h10_sublord = 30.0 * sublord_bonus * _vit(h10_sub)

    # ── Education house CSL sub-lords (H4/H5/H9) ─────────────────────────────
    edu_sub_lords = [
        kp_cusps.get("H4", {}).get("sub_lord", ""),
        kp_cusps.get("H5", {}).get("sub_lord", ""),
        kp_cusps.get("H9", {}).get("sub_lord", ""),
    ]
    edu_vit_values = [_vit(p) for p in edu_sub_lords if p]
    edu_vitality   = sum(edu_vit_values) / len(edu_vit_values) if edu_vit_values else 1.0
    _edu_star      = 20.0 * edu_star_bonus * edu_vitality

    # ── KP Education House Combination (H4/H5/H9/H11) ────────────────────────
    edu_branch_strength = _kp_edu_branch_strength(field_affinity, kp_sigs)
    edu_bvit_total  = 0.0
    edu_bvit_weight = 0.0
    _EDU_HOUSES = {4, 5, 9, 11}
    for planet, weight in field_affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
            if any(h in sig.get(key, []) for h in _EDU_HOUSES):
                piece = weight * (1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25)
                edu_bvit_total  += piece * _vit(planet)
                edu_bvit_weight += piece
                break
    edu_branch_vitality = (edu_bvit_total / edu_bvit_weight) if edu_bvit_weight > 0 else 1.0
    _edu_branch = 15.0 * edu_branch_strength * edu_branch_vitality

    # ── Gap 3: H2+H11 secondary career branch ────────────────────────────────
    # Classical KP: H2+H6+H10+H11 must all connect. H2 (wealth) and H11 (gains)
    # are primary significators for earth/industry charts where H10 is Venus-locked.
    h2h11_strength      = _kp_career_h2h11_strength(field_affinity, kp_sigs)
    h2h11_vit_total     = 0.0
    h2h11_vit_weight    = 0.0
    _H2H11 = {2, 11}
    for planet, weight in field_affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
            if any(h in sig.get(key, []) for h in _H2H11):
                lw = 1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25
                piece = weight * lw
                h2h11_vit_total  += piece * _vit(planet)
                h2h11_vit_weight += piece
                break
    h2h11_vitality = (h2h11_vit_total / h2h11_vit_weight) if h2h11_vit_weight > 0 else 1.0
    _h2h11_branch  = 20.0 * h2h11_strength * h2h11_vitality

    score       += _h10_branch + _h10_sublord + _edu_star + _edu_branch + _h2h11_branch
    rubric_core += _h10_branch + _h10_sublord + _edu_star + _edu_branch
    rubric_support += _h2h11_branch
    components["h10_branch"]   = round(_h10_branch, 2)
    components["h10_sublord"]  = round(_h10_sublord, 2)
    components["edu_star"]     = round(_edu_star, 2)
    components["edu_branch"]   = round(_edu_branch, 2)
    components["h2h11_branch"] = round(_h2h11_branch, 2)

    # ── Career keyword bonus ──────────────────────────────────────────────────
    if any(k in label for k in ("career", "management", "engineering", "medicine", "research", "science", "law", "technology")):
        _bonus = (100.0 - score) * 0.05
        score += _bonus
        rubric_support += _bonus
        components["career_keyword"] = round(_bonus, 2)

    # ── Top-2 planet L1 H10 / H5 / H9 bonus ─────────────────────────────────
    for planet in top_weighted_planets(field_affinity, 2):
        sig = kp_sigs.get(planet, {}) or {}
        if 10 in sig.get("level_1", []):
            _bonus = 4.0 * field_affinity.get(planet, 0.0) * _vit(planet)
            score += _bonus
            rubric_core += _bonus
            trace.append(f"KP level-1 H10 significator alignment via {planet}.")
        elif 5 in sig.get("level_1", []) or 9 in sig.get("level_1", []):
            _bonus = 2.5 * field_affinity.get(planet, 0.0) * _vit(planet)
            score += _bonus
            rubric_support += _bonus

    # ── H10 cusp consensus (sub_lord == star_lord) ───────────────────────────
    if h10_sub and h10_sub == kp_cusps.get("H10", {}).get("star_lord", ""):
        _bonus = (100.0 - score) * 0.06 * _vit(h10_sub)
        score += _bonus
        rubric_validation += _bonus
        components["h10_consensus"] = round(_bonus, 2)
        trace.append("KP H10 cusp consensus is strong.")

    # ── C4: H4 H11 H6 H2 sub-lord scoring ────────────────────────────────────
    for cusp_key, base_pts in (("H4", 7.0), ("H11", 8.0), ("H6", 6.0), ("H2", 5.0)):
        sub = kp_cusps.get(cusp_key, {}).get("sub_lord", "")
        if not sub:
            continue
        w = field_affinity.get(sub, 0.0)
        v = _vit(sub)
        if w >= 0.25:
            b = base_pts * v
        elif w >= 0.15:
            b = base_pts * 0.55 * v
        elif w >= 0.08:
            b = base_pts * 0.20 * v
        else:
            continue
        score += b
        rubric_support += b
        components[f"{cusp_key.lower()}_sublord"] = round(b, 2)
        trace.append(f"KP {cusp_key} sub-lord {sub} aligns with field (w={w:.2f}).")

    # ── Life-science / space-aerospace cluster bonuses ────────────────────────
    life_bonus  = _life_science_cluster_bonus(field_id, label, field_affinity, getattr(payload_data, "eff_strengths", {}) or {}) * 20.0
    space_bonus = _space_aerospace_cluster_bonus(field_id, label, field_affinity, getattr(payload_data, "eff_strengths", {}) or {}) * 20.0
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

    # ── Gap 4: H8 earth/underground branch (mining, petroleum, geology, etc.) ─
    if _is_earth_field(field_id, label):
        h8_raw        = 0.0
        h8_vit_total  = 0.0
        h8_vit_weight = 0.0
        for planet, weight in field_affinity.items():
            sig = kp_sigs.get(planet, {}) or {}
            for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
                if 8 in sig.get(key, []):
                    lw = 1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25
                    piece = weight * lw
                    h8_raw        += piece
                    h8_vit_total  += piece * _vit(planet)
                    h8_vit_weight += piece
                    break
        if h8_raw > 0:
            h8_vitality  = (h8_vit_total / h8_vit_weight) if h8_vit_weight > 0 else 1.0
            _max_h8      = sum(field_affinity.values()) or 1.0
            h8_strength  = min(h8_raw / _max_h8, 1.0)
            _h8_branch   = 24.0 * h8_strength * h8_vitality   # 0.6 × 40 pts max
            score         += _h8_branch
            rubric_support += _h8_branch
            components["h8_earth_branch"] = round(_h8_branch, 2)
            trace.append("KP H8 (underground/earth resources) branch active for earth-domain field.")

    # ── D10 H10 occupant bonus ────────────────────────────────────────────────
    d10_h10_planets = d10_occ.get("10", []) or d10_occ.get(10, [])
    d10_bonus = 0.0
    for p in d10_h10_planets:
        w = field_affinity.get(p, 0.0)
        if w >= 0.10:
            d10_bonus += 3.5 * w
    if d10_bonus > 0:
        d10_bonus = min(d10_bonus, 8.0)
        _bonus    = (100.0 - score) * (d10_bonus / 100.0)
        occupant_vits = [_vit(p) for p in d10_h10_planets if field_affinity.get(p, 0.0) >= 0.10]
        if occupant_vits:
            _bonus *= sum(occupant_vits) / len(occupant_vits)
        score             += _bonus
        rubric_validation += _bonus
        components["d10_h10_occupants"] = round(_bonus, 2)
        trace.append("D10 H10 occupants reinforce KP career significators.")

    # ── Gap 6: D10 H11 occupant bonus (gains/income, secondary career) ────────
    d10_h11_planets  = d10_occ.get("11", []) or d10_occ.get(11, [])
    d10_h11_bonus    = 0.0
    for p in d10_h11_planets:
        w = field_affinity.get(p, 0.0)
        if w >= 0.10:
            d10_h11_bonus += 3.5 * w * 0.5   # 0.5× weight vs H10
    if d10_h11_bonus > 0:
        d10_h11_bonus = min(d10_h11_bonus, 4.0)
        _bonus_h11    = (100.0 - score) * (d10_h11_bonus / 100.0)
        h11_vits      = [_vit(p) for p in d10_h11_planets if field_affinity.get(p, 0.0) >= 0.10]
        if h11_vits:
            _bonus_h11 *= sum(h11_vits) / len(h11_vits)
        score             += _bonus_h11
        rubric_validation += _bonus_h11
        components["d10_h11_occupants"] = round(_bonus_h11, 2)
        trace.append("D10 H11 occupants provide gains/income signal (secondary career).")

    # ── Combustion penalty ────────────────────────────────────────────────────
    combustion_penalty = _planet_combustion_penalty(
        field_affinity,
        getattr(payload_data, "combust_planets", []) or [],
        getattr(payload_data, "planet_dignities", {}) or {},
        getattr(payload_data, "planets_d1", {}) or {},
    ) * 100.0
    if combustion_penalty > 0:
        score         -= combustion_penalty
        rubric_penalty -= combustion_penalty
        components["combustion_penalty"] = round(-combustion_penalty, 2)
        trace.append("Combust planets weaken KP event-fructification.")

    # ── Dusthana lord penalty ─────────────────────────────────────────────────
    dusthana_penalty = _dusthana_lord_penalty(
        field_affinity,
        getattr(payload_data, "lagna_sign", "") or "",
        getattr(payload_data, "house_lords", {}) or {},
        getattr(payload_data, "lagna_lord", "") or "",
        field_id or "",
        getattr(payload_data, "eff_strengths", {}) or {},
    ) * 100.0
    if dusthana_penalty > 0:
        score         -= dusthana_penalty
        rubric_penalty -= dusthana_penalty
        components["dusthana_penalty"] = round(-dusthana_penalty, 2)
        trace.append("Dusthana lordship weakens KP cusp delivery.")

    # ── S3: top-4 vitality penalty; S4: skip Neecha Bhanga planets ────────────
    for planet in top_weighted_planets(field_affinity, 4):
        if planet in neecha_bhanga:
            continue
        vitality = _d1_vitality_coefficient(planet, payload_data)
        if vitality < 1.0:
            penalty = (1.0 - vitality) * field_affinity.get(planet, 0.0) * 20.0
            if penalty > 0:
                score         -= penalty
                rubric_penalty -= penalty
                components[f"{planet.lower()}_vitality_penalty"] = round(-penalty, 2)
                trace.append(f"{planet} vitality is reduced by D1 impairments.")

    rubric = build_score_rubric(
        "kp",
        [
            rubric_section(
                "core",
                rubric_core,
                40.0,
                note="H10 branch, H10 sub-lord, education CSL (H4/H5/H9 sub-lords), and edu house significators.",
                items=["h10_branch", "h10_sublord", "edu_star", "edu_branch", "h10_level_1"],
            ),
            rubric_section(
                "support",
                rubric_support,
                25.0,
                note="Career keyword, H2+H11 career branch, H8 earth branch, and secondary cusp support.",
                items=["career_keyword", "h2h11_branch", "h8_earth_branch", "h4_sublord", "h11_sublord", "h6_sublord", "h2_sublord"],
            ),
            rubric_section(
                "validation",
                rubric_validation,
                20.0,
                note="D10 occupancy (H10+H11) and cluster confirmations.",
                items=["h10_consensus", "life_science_cluster", "space_aerospace_cluster", "d10_h10_occupants", "d10_h11_occupants"],
            ),
            rubric_section(
                "penalty",
                rubric_penalty,
                20.0,
                kind="penalty",
                note="Combustion, dusthana, and vitality friction.",
                items=["combustion_penalty", "dusthana_penalty", "vitality_penalty"],
            ),
        ],
    )

    return method_result("kp", clamp_score(score), trace, components, rubric=rubric, normalization_cap=80.0)
