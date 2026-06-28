"""K.N. Rao field-determination module."""
from __future__ import annotations

from typing import Any, Dict, List

from ..astro import (
    _compute_arudha_pada,
    _compute_bvb_7_karakas,
    _compute_whole_sign_houses,
    _get_active_dasha_lord,
    _is_vargottama,
    compute_dignity,
)
from ..boosts import (
    _d1_vitality_coefficient,
    _d9_h10_bonus,
    _d10_lagna_lord_bonus,
    _dusthana_lord_penalty,
    _functional_malefic_dig_factor,
    _life_science_cluster_bonus,
    _space_aerospace_cluster_bonus,
    _ODD_SIGNS,
)
from ..constants import _SIGN_LORD, _SIGN_NUM
from .common import build_score_rubric, clamp_score, method_result, rubric_section


_OWN_SIGNS = {
    "Sun": {"Leo"},
    "Moon": {"Cancer"},
    "Mars": {"Aries", "Scorpio"},
    "Mercury": {"Gemini", "Virgo"},
    "Jupiter": {"Sagittarius", "Pisces"},
    "Venus": {"Taurus", "Libra"},
    "Saturn": {"Capricorn", "Aquarius"},
}
_ROLE_WEIGHTS = {
    "Dasha_Lord": 1.5,
    "AmK": 1.4,
    "BK": 1.2,
    "5th_lord": 1.1,
    "9th_lord": 1.1,
    "10th_lord": 1.1,
    "AK": 1.0,
    "Lagna_lord": 1.0,
    "Own_Sign": 1.0,
}
_ROLE_PRIORITY = (
    "Dasha_Lord",
    "AmK",
    "BK",
    "5th_lord",
    "9th_lord",
    "10th_lord",
    "AK",
    "Lagna_lord",
    "Own_Sign",
)
_D24_BOOST_HOUSES = {1, 4, 5, 9, 10}
_D24_PENALTY_HOUSES = {6, 8, 12}
_STREAM_SCALE = 10.0


def _sign_house_from_lagna(sign: str, lagna_sign: str) -> int:
    if not sign or not lagna_sign:
        return 0
    return (((_SIGN_NUM.get(sign, 1) - _SIGN_NUM.get(lagna_sign, 1)) % 12) + 1)


def _d24_house(planet: str, d24_chart: Dict[str, str], d24_lagna: str) -> int:
    return _sign_house_from_lagna(d24_chart.get(planet, ""), d24_lagna)


def _is_mrita(sign: str, degree: float) -> bool:
    if not sign:
        return False
    if sign in _ODD_SIGNS and degree >= 24.0:
        return True
    if sign not in _ODD_SIGNS and degree < 6.0:
        return True
    return False


def _planet_own_sign(planet: str, sign: str) -> bool:
    return bool(sign) and sign in _OWN_SIGNS.get(planet, set())


def _dominant_role(roles: List[str]) -> str:
    best_role = ""
    best_weight = -1.0
    for role in _ROLE_PRIORITY:
        if role not in roles:
            continue
        weight = _ROLE_WEIGHTS.get(role, 1.0)
        if weight > best_weight:
            best_role = role
            best_weight = weight
    return best_role


def _mrita_alpha(planet: str, roles: List[str], sign: str, degree: float, shadbala: float) -> tuple[float, List[str]]:
    notes: List[str] = []
    if _is_mrita(sign, degree):
        alpha = 0.40
        notes.append("Mrita baseline 0.40")
        if "AmK" in roles or "AK" in roles:
            alpha += 0.30
            notes.append("AmK/AK rescue +0.30")
        if shadbala >= 380.0:
            alpha += 0.20
            notes.append(f"Shadbala rescue +0.20 ({shadbala:.2f})")
        if _planet_own_sign(planet, sign):
            alpha += 0.20
            notes.append("Own-sign rescue +0.20")
        return min(alpha, 1.0), notes

    return 0.85, ["Non-Mrita baseline 0.85"]


def _varga_multiplier(planet: str, sign: str, d24_chart: Dict[str, str], d24_lagna: str) -> tuple[float, int, List[str]]:
    vm = 1.0
    notes: List[str] = []
    d24_house = _d24_house(planet, d24_chart, d24_lagna)
    if d24_house in _D24_BOOST_HOUSES:
        vm += 0.30
        notes.append(f"D24 kendra/trikona boost (+0.30) via house {d24_house}")
    elif d24_house in _D24_PENALTY_HOUSES:
        vm -= 0.25
        notes.append(f"D24 dusthana penalty (-0.25) via house {d24_house}")
    if sign and d24_chart.get(planet, "") == sign:
        vm += 0.40
        notes.append("Siddhamsottama boost (+0.40)")
    return vm, d24_house, notes


def score_knrao(payload_data: Any, domain: str, field_affinity: Dict[str, float], field_id: str = "") -> Dict[str, Any]:
    """K.N. Rao field scorer using role hierarchy, Mrita rescue, and D24 gating."""

    planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    house_lords = getattr(payload_data, "house_lords", {}) or {}
    kn_rao_jaimini = getattr(payload_data, "kn_rao_jaimini", {}) or {}
    divisional_charts = getattr(payload_data, "divisional_charts", {}) or {}
    d24_chart = divisional_charts.get("D24_siddhamsam", {}) or {}
    d9_chart = divisional_charts.get("D9_navamsha", {}) or {}
    d10_chart = divisional_charts.get("D10_dashamsha", {}) or {}
    d10_occ = getattr(payload_data, "d10_house_occupancy", {}) or {}
    lagna_sign = getattr(payload_data, "lagna_sign", "")
    eff = getattr(payload_data, "eff_strengths", {}) or {}
    combust_planets = set(getattr(payload_data, "combust_planets", []) or [])
    neecha_bhanga = set(getattr(payload_data, "neecha_bhanga_planets", []) or [])
    current_age = float(getattr(payload_data, "current_age", 0.0) or 0.0)
    active_dasha_lord = getattr(payload_data, "active_dasha_lord", "") or _get_active_dasha_lord(
        getattr(payload_data, "dasha_sequence", []) or [],
        current_age,
    )

    ak = getattr(payload_data, "atmakaraka", "") or kn_rao_jaimini.get("chara_karakas", {}).get("AK", "")
    amk = getattr(payload_data, "amatyakaraka", "") or kn_rao_jaimini.get("chara_karakas", {}).get("AmK", "")

    whole_houses = _compute_whole_sign_houses(planets_d1, lagna_sign) if lagna_sign else {}
    d10_lagna = d10_chart.get("Lagna", "")
    d9_lagna = d9_chart.get("Lagna", "")
    d24_lagna = d24_chart.get("Lagna", "")

    al_sign = _compute_arudha_pada(1, lagna_sign, planets_d1) if lagna_sign else ""
    a10_sign = _compute_arudha_pada(10, lagna_sign, planets_d1) if lagna_sign else ""
    al_lord = _SIGN_LORD.get(al_sign, "")
    a10_lord = _SIGN_LORD.get(a10_sign, "")

    h10_lord = house_lords.get("10", "")
    h10_lord_house = whole_houses.get(h10_lord, 0)
    d10_digs = getattr(payload_data, "d10_planet_dignities", {}) or {}
    d10_h10_planets = d10_occ.get("10", []) or d10_occ.get(10, [])
    d10_ll = _SIGN_LORD.get(d10_lagna, "")

    score = 0.0
    trace: List[str] = []
    components: Dict[str, float] = {}
    rubric_core = 0.0
    rubric_support = 0.0
    rubric_validation = 0.0
    rubric_penalty = 0.0
    alpha_by_planet: Dict[str, float] = {}

    # Core educational/career field scoring loop.
    for planet in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
        pdata = planets_d1.get(planet, {}) or {}
        sign = pdata.get("sign", "")
        try:
            degree = float(pdata.get("degree", 0.0))
        except (TypeError, ValueError):
            degree = 0.0
        shadbala = float(pdata.get("shadbala_virupas", 0.0) or 0.0)

        roles: List[str] = []
        if active_dasha_lord and planet == active_dasha_lord:
            roles.append("Dasha_Lord")
        if planet == amk:
            roles.append("AmK")
        if planet == ak:
            roles.append("AK")

        chara_karakas = kn_rao_jaimini.get("chara_karakas", {}) or {}
        for karaka_key in ("AmK", "BK", "AK"):
            if chara_karakas.get(karaka_key, "") == planet:
                roles.append(karaka_key)

        if house_lords.get("5", "") == planet:
            roles.append("5th_lord")
        if house_lords.get("9", "") == planet:
            roles.append("9th_lord")
        if house_lords.get("10", "") == planet:
            roles.append("10th_lord")
        if house_lords.get("1", "") == planet:
            roles.append("Lagna_lord")
        if _planet_own_sign(planet, sign):
            roles.append("Own_Sign")

        role_weight = max((_ROLE_WEIGHTS.get(r, 1.0) for r in roles), default=1.0)
        dominant_role = _dominant_role(roles)
        alpha, alpha_notes = _mrita_alpha(planet, roles, sign, degree, shadbala)
        vm, d24_house, vm_notes = _varga_multiplier(planet, sign, d24_chart, d24_lagna)
        total_factor = role_weight * alpha * vm
        field_weight = float(field_affinity.get(planet, 0.0) or 0.0)
        contribution = field_weight * total_factor * _STREAM_SCALE

        if contribution > 0:
            score += contribution
            rubric_core += contribution
            dignity_label = compute_dignity(planet, sign) or "neutral"
            trace.append(f"{planet} aligns with {dignity_label} dignity.")
            components[f"{planet.lower()}_contribution"] = round(contribution, 2)

        # Vitality drag — always apply for impaired planets with meaningful affinity
        if field_weight >= 0.10 and planet not in neecha_bhanga:
            vit = _d1_vitality_coefficient(planet, payload_data)
            if vit < 0.80:
                drag = field_weight * (0.80 - vit) * _STREAM_SCALE * 0.5
                score -= drag
                rubric_penalty -= drag
                components[f"{planet.lower()}_vitality_penalty"] = round(-drag, 2)
                trace.append(
                    f"{planet} vitality is reduced by D1 impairments, trimming {drag:.1f} points."
                )
        alpha_by_planet[planet] = alpha

    # ── Life-science / space-aerospace cluster bonuses ────────────────────────
    life_bonus  = _life_science_cluster_bonus(field_id, field_id.replace("_"," ").lower(), field_affinity, eff) * 20.0
    space_bonus = _space_aerospace_cluster_bonus(field_id, field_id.replace("_"," ").lower(), field_affinity, eff) * 20.0
    if life_bonus > 0:
        _b = (100.0 - score) * (life_bonus / 100.0)
        score += _b; rubric_support += _b
        components["life_science_cluster"] = round(_b, 2)
    if space_bonus > 0:
        _b = (100.0 - score) * (space_bonus / 100.0)
        score += _b; rubric_support += _b
        components["space_aerospace_cluster"] = round(_b, 2)

    # ── Dusthana lord penalty ─────────────────────────────────────────────────
    lagna_lord = getattr(payload_data, "lagna_lord", "") or house_lords.get("1", "")
    planet_dignities = getattr(payload_data, "planet_dignities", {}) or {}
    dusthana_pen = _dusthana_lord_penalty(
        field_affinity,
        lagna_sign,
        house_lords,
        lagna_lord,
        field_id,
        eff,
    ) * 100.0
    if dusthana_pen > 0:
        score -= dusthana_pen; rubric_penalty -= dusthana_pen
        components["dusthana_penalty"] = round(-dusthana_pen, 2)
        trace.append("Dusthana lordship weakens the career signature.")

    # ── D9 10th house alignment ───────────────────────────────────────────────
    d9_bonus = _d9_h10_bonus(field_affinity, d9_chart, d9_lagna) * 20.0
    if d9_bonus > 0:
        _b = (100.0 - score) * (d9_bonus / 100.0)
        score += _b; rubric_validation += _b
        components["d9_validation"] = round(_b, 2)
        trace.append("D9 10th house alignment: karaka planet in navamsha career house.")

    # ── D10 H10 occupant bonus ────────────────────────────────────────────────
    d10_h10_bonus = 0.0
    for p in d10_h10_planets:
        w = field_affinity.get(p, 0.0)
        if w >= 0.10:
            d10_h10_bonus += 4.0 * w
    if d10_h10_bonus > 0:
        d10_h10_bonus = min(d10_h10_bonus, 6.0)
        _b = (100.0 - score) * (d10_h10_bonus / 100.0)
        score += _b; rubric_validation += _b
        components["d10_h10"] = round(_b, 2)
        trace.append("D10 10th house placement confirms professional capacity.")

    # ── D10 lagna lord dignity bonus ──────────────────────────────────────────
    d10_ll_bonus = _d10_lagna_lord_bonus(field_affinity, d10_chart, d10_lagna) * 14.0
    if d10_ll_bonus > 0:
        _b = (100.0 - score) * (d10_ll_bonus / 100.0)
        score += _b; rubric_validation += _b
        components["d10_lagna_lord_bonus"] = round(_b, 2)
        trace.append("D10 lagna lord dignified -- career path has structural support.")

    # ── Whole-sign career house alignment ─────────────────────────────────────
    ws_score = 0.0
    _career_houses = {1, 2, 5, 9, 10, 11}
    for planet, weight in field_affinity.items():
        if weight < 0.10:
            continue
        wh = whole_houses.get(planet, 0)
        if wh in _career_houses:
            ws_score += weight * (1.35 if wh in {10, 5, 9} else 0.55)
    if ws_score > 0:
        ws_max = sum(v for v in field_affinity.values() if v >= 0.10) or 1.0
        ws_norm = min(ws_score / ws_max, 1.0)
        _b = 18.0 * ws_norm
        score += _b; rubric_support += _b
        components["whole_sign_career"] = round(_b, 2)
        trace.append("Whole-sign placements in career houses reinforce professional potential.")

    # ── H10 lord kendra/trikona or dusthana placement ────────────────────────
    if h10_lord and h10_lord_house > 0:
        if h10_lord_house in {1, 4, 7, 10, 5, 9}:
            _b = 26.0 * field_affinity.get(h10_lord, 0.0)
            if _b > 0:
                score += _b; rubric_core += _b
                components["h10_lord_kendra_trikona"] = round(_b, 2)
                trace.append(f"H10 lord ({h10_lord}) in house {h10_lord_house} -- kendra/trikona.")
        elif h10_lord_house in {6, 8, 12}:
            _pen = 18.0 * field_affinity.get(h10_lord, 0.0)
            if _pen > 0:
                score -= _pen; rubric_penalty -= _pen
                components["h10_lord_dusthana"] = round(-_pen, 2)
                trace.append(f"H10 lord ({h10_lord}) in dusthana house {h10_lord_house} -- weakens career.")

    rubric = build_score_rubric(
        "knrao",
        [
            rubric_section("core", rubric_core, 60.0,
                note="Planet role × Mrita alpha × D24 varga multiplier × affinity.",
                items=["contribution", "h10_lord_kendra_trikona"]),
            rubric_section("support", rubric_support, 20.0,
                note="Cluster bonuses and whole-sign career house alignment.",
                items=["life_science_cluster", "space_aerospace_cluster", "whole_sign_career"]),
            rubric_section("validation", rubric_validation, 20.0,
                note="D9/D10 divisional confirmation.",
                items=["d9_validation", "d10_h10", "d10_lagna_lord_bonus"]),
            rubric_section("penalty", rubric_penalty, 20.0, kind="penalty",
                note="Dusthana lordship, H10 lord in dusthana, and vitality drag.",
                items=["dusthana_penalty", "h10_lord_dusthana", "vitality_penalty"]),
        ],
    )

    return method_result("knrao", clamp_score(score), trace, components, rubric=rubric, normalization_cap=80.0)
