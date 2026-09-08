"""K.N. Rao field-determination module."""
from __future__ import annotations

import os as _os
from typing import Any, Dict, List

# Print-output optimization (2026-08-20): gate the per-field debug prints
# (K.N. Rao confirmation bonus / `[CROSS-VERIFICATION NARRATIVE]`) behind
# the same opt-in verbosity flag engine.py uses, so a normal run only
# prints the final summary report. Set JYOTISH_VERBOSE_FIELD_LOG=1 to
# restore them.
_VERBOSE_FIELD_LOG = _os.environ.get("JYOTISH_VERBOSE_FIELD_LOG", "0") == "1"

from jyotish.astro import (
    _compute_arudha_pada,
    _compute_whole_sign_houses,
    _get_active_dasha_lord,
    _is_vargottama,
    compute_dignity,
)
from jyotish.boosts import (
    _d1_vitality_coefficient,
    _d9_h10_bonus,
    _d10_lagna_lord_bonus,
    _dusthana_lord_penalty,
    _functional_malefic_dig_factor,
    _life_science_cluster_bonus,
    _space_aerospace_cluster_bonus,
    _karakatwa_domain_bonus,
    _house_signification_bonus,
    _vimsopaka_bala_coefficient,
    _planet_combustion_penalty,
    _ODD_SIGNS,
    _wm,
)
from jyotish.constants import _SIGN_LORD, _SIGN_NUM, _KENDRA_HOUSES, _TRIKONA_HOUSES, _DUSTHANA_HOUSES
from .common import (
    METHOD_SCORE_CAPS,
    build_gate_text,
    build_score_rubric,
    chandra_lagna_h10_lord,
    surya_lagna_h10_lord,
    clamp_score,
    method_result,
    rubric_section,
    top_weighted_planets,
)


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
    # Stage 5 (Astro-OS v3 gap-audit implementation plan, 2026-08): timing
    # separated from structure. Dasha_Lord/Antardasha_Lord previously carried
    # 1.5x/0.90x multipliers directly into this method's STRUCTURAL
    # role_weight (the same value that scales every planet's core
    # contribution below) -- meaning "which field a person is astrologically
    # suited to" and "what their chart currently activates" were fused into
    # one number, with no way for a caller to see the structural fit on its
    # own. That fusion is exactly the class of problem
    # confidence_dimensions.py's dedicated timing_fit dimension (Stage 4) was
    # built to hold instead. Neutralized to 1.0 (the same non-elevating
    # baseline already used by AK/Lagna_lord/Own_Sign below) so the current
    # dasha/antardasha lord no longer inflates or discounts a planet's
    # structural contribution here. Role detection itself is UNCHANGED --
    # "Dasha_Lord"/"Antardasha_Lord" still appear in `roles`/trace/components
    # for audit visibility, they simply no longer participate in the
    # role_weight = max(...) that feeds `contribution` (search: total_factor).
    "Dasha_Lord": 1.0,
    "Antardasha_Lord": 1.0,  # G5
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
    "Antardasha_Lord",  # G5
    "AmK",
    "BK",
    "5th_lord",
    "9th_lord",
    "10th_lord",
    "AK",
    "Lagna_lord",
    "Own_Sign",
)
# ── Systematic karaka-to-field table (BPHS/Jataka Parijata karakatwa) ─────────
# The T2 blocks below (_TATVA_FIELD_KW, _SERVICE_FIELDS_KN, _MODERN_FIELDS_KN, H3
# skill list) each hand-curate a keyword list per pattern, so any field whose id/
# label doesn't happen to contain one of those exact substrings gets *no* signal
# from an otherwise-valid classical yoga (e.g. Rahu-in-H10 for a field named
# "quantitative_trading" gets nothing because "trading" isn't in _MODERN_FIELDS_KN).
# This table instead maps each graha to its classical significator *domains* per
# BPHS/Jataka Parijata karakatwa, and every career `domain` bucket used by this
# engine (see the domain sets referenced throughout this module and payload.py) to
# the karaka domain(s) it belongs to. Any planet whose karaka domain matches the
# chart's `domain` contributes a systematic (non-keyword) bonus, so the classical
# planet-house yogas above generalize to *any* field in a matching domain rather
# than only the ones an author remembered to add to a keyword list.
#
# Promoted to constants.py + boosts.py::_karakatwa_domain_bonus so every field
# method (not just this one) gets the same systematic fallback — see call site
# below, which now delegates to the shared helper instead of duplicating the
# table and the scoring loop.

_D24_BOOST_HOUSES = {1, 4, 5, 9, 10}
_D24_PENALTY_HOUSES = {6, 8, 12}
_STREAM_SCALE = 10.0

# BPHS (Ch. 27) minimum required shadbala per planet, in Rupas — each planet has a
# distinct "pass mark" (Sun 5, Moon 6, Mars 5, Mercury 7, Jupiter 6.5, Venus 5.5,
# Saturn 5). A planet below its own minimum is classically "weak" regardless of how
# that compares to another planet's minimum — Mercury needs more raw shadbala than
# Mars to be considered functionally strong. The previous version applied one
# universal virupa ladder (200/350/500/700) to every planet alike, which is not
# what BPHS specifies and silently mis-rates planets whose minimum differs from the
# implicit ~500-virupa (8.3 rupa) midpoint the old ladder was tuned around.
_BPHS_MIN_SHADBALA_RUPAS = {
    "Sun": 5.0, "Moon": 6.0, "Mars": 5.0, "Mercury": 7.0,
    "Jupiter": 6.5, "Venus": 5.5, "Saturn": 5.0,
    # Rahu/Ketu have no classical shadbala minimum in BPHS; treat as neutral.
}
_VIRUPAS_PER_RUPA = 60.0


def _shadbala_mult(shadbala_virupas: float, planet: str = "") -> float:
    """Continuous 0.70-1.30 multiplier, scaled against the planet's own BPHS minimum.

    `shadbala_virupas` is expected in virupas (shashtiamsas); BPHS minimums are
    published in rupas, so we convert and score the planet's shadbala as a ratio
    of *its own* required minimum rather than against one fixed virupa scale.
    """
    if shadbala_virupas <= 0:
        return 1.00  # unknown — neutral
    min_rupas = _BPHS_MIN_SHADBALA_RUPAS.get(planet)
    if not min_rupas:
        # Rahu/Ketu or unrecognized planet — fall back to the old fixed-scale ladder.
        if shadbala_virupas < 200:  return 0.70
        if shadbala_virupas < 350:  return 0.85
        if shadbala_virupas < 500:  return 1.00
        if shadbala_virupas < 700:  return 1.15
        return 1.30
    ratio = shadbala_virupas / (min_rupas * _VIRUPAS_PER_RUPA)  # 1.0 == exactly at BPHS minimum
    if ratio < 0.60:  return 0.70
    if ratio < 0.85:  return 0.85
    if ratio < 1.00:  return 0.95
    if ratio < 1.30:  return 1.00
    if ratio < 1.70:  return 1.15
    return 1.30

# G12: H10 from Chandra Lagna — Gap-14 fix: delegate to common.chandra_lagna_h10_lord
_chandra_lagna_h10_lord = chandra_lagna_h10_lord
# §9 remediation (2026-08-19): the Sun-anchored half of the spec's named
# "10th house from Lagna, Moon, AND Sun" triple-confirmation technique --
# previously this existed only inside sudarshana.py, so knrao.py itself
# never performed the actual named check. See common.py::surya_lagna_h10_lord.
_surya_lagna_h10_lord = surya_lagna_h10_lord


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


def _dasha_career_thread(dasha_sequence: List[Dict], current_age: float, field_affinity: Dict[str, float]) -> tuple[str, str, int]:
    """K.N. Rao's signature dasha-sequential technique.

    Rao reads career timing not merely by asking "is this planet the current dasha
    lord" but by tracing the *thread* of dashas already run to see which one first
    activated the profession -- the "originating dasha" -- and treats every
    subsequent dasha of an aligned planet as a continuation/fructification of that
    thread. This lets the engine explain *why this dasha specifically* rather than
    just identifying the field.

    Returns (originating_lord, current_lord, dashas_elapsed).
    """
    if not dasha_sequence:
        return "", "", 0
    passed = [d for d in dasha_sequence if float(d.get("start_age", 0) or 0) <= current_age]
    if not passed:
        return "", "", 0
    passed.sort(key=lambda d: float(d.get("start_age", 0) or 0))
    originating_lord = ""
    for d in passed:
        lord = d.get("lord", "") or d.get("md_planet", "")
        if lord and field_affinity.get(lord, 0.0) >= 0.15:
            originating_lord = lord
            break
    current_lord = passed[-1].get("lord", "") or passed[-1].get("md_planet", "") or ""
    return originating_lord, current_lord, len(passed)


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


def _mrita_alpha(planet: str, roles: List[str], sign: str, degree: float, shadbala: float,
                  neecha_bhanga: bool = False) -> tuple[float, List[str]]:
    notes: List[str] = []
    if _is_mrita(sign, degree):
        alpha = 0.40
        notes.append("Mrita baseline 0.40")
        # S153 fix (2026-07-04): Neecha Bhanga (classically-cancelled
        # debilitation) previously only suppressed the separate "vitality
        # drag" penalty below (planet not in neecha_bhanga), leaving this
        # function — which sets the actual CONTRIBUTION multiplier — blind
        # to NB entirely. A debilitated planet with no AK/AmK role and
        # middling shadbala (e.g. Mars debilitated in Cancer but NB-cancelled
        # via its exaltation-sign lord Saturn sitting in a kendra) stayed
        # near the 0.40 floor even though classical doctrine treats a
        # confirmed Neecha Bhanga as a substantial strength restoration, not
        # merely "no longer penalized." Rescue magnitude matches the
        # existing AK/AmK rescue (+0.30) since both are comparably strong,
        # explicitly-classical restoration signals — this is a genuine
        # partial recovery, not full exaltation-equivalent (which stays
        # capped at 1.0 by the existing min() below).
        if neecha_bhanga:
            alpha += 0.30
            notes.append("Neecha Bhanga rescue +0.30")
        if "AmK" in roles or "AK" in roles:
            alpha += 0.30
            notes.append("AmK/AK rescue +0.30")
        # N2 (BPHS fix): rescue scale keyed to the planet's own BPHS minimum shadbala,
        # not one shared virupa scale — Mercury's 380-virupa mark is well below its
        # BPHS pass mark (7 rupas = 420 virupas) while the same 380 clears Mars's
        # (5 rupas = 300 virupas) comfortably. Ratio-based thresholds fix that.
        _min_rupas = _BPHS_MIN_SHADBALA_RUPAS.get(planet)
        if _min_rupas:
            _ratio = shadbala / (_min_rupas * _VIRUPAS_PER_RUPA)
            _sdb_rescue = (0.25 if _ratio >= 1.40 else
                           0.20 if _ratio >= 1.00 else
                           0.12 if _ratio >= 0.75 else
                           0.06 if _ratio >= 0.60 else 0.0)
        else:
            _sdb_rescue = (0.25 if shadbala >= 700 else
                           0.20 if shadbala >= 500 else
                           0.12 if shadbala >= 380 else
                           0.06 if shadbala >= 300 else 0.0)
        if _sdb_rescue > 0:
            alpha += _sdb_rescue
            notes.append(f"Shadbala rescue +{_sdb_rescue:.2f} ({shadbala:.2f})")
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


def score_knrao(
    payload_data: Any,
    domain: str,
    field_affinity: Dict[str, float],
    field_id: str = "",
    field_entry: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """K.N. Rao field scorer using role hierarchy, Mrita rescue, and D24 gating."""
    # Gap-18b (generalized fix, audit 2026-07): gate text now also draws on the
    # registry's descriptive text (label/track/niche/description) when
    # field_entry is supplied, not just the bare field_id -- see
    # field_methods/common.py::build_gate_text for the full rationale.
    label = build_gate_text(field_id, field_entry)

    planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    house_lords = getattr(payload_data, "house_lords", {}) or {}
    kn_rao_jaimini = getattr(payload_data, "kn_rao_jaimini", {}) or {}
    divisional_charts = getattr(payload_data, "divisional_charts", {}) or {}
    d24_chart = divisional_charts.get("D24_siddhamsam", {}) or {}
    d9_chart = divisional_charts.get("D9_navamsha", {}) or {}
    d10_chart = divisional_charts.get("D10_dashamsha", {}) or {}
    d10_occ = getattr(payload_data, "d10_house_occupancy", {}) or {}
    lagna_sign = getattr(payload_data, "lagna_sign", "")
    eff = (getattr(payload_data, "eff_strengths_tier1", None) or getattr(payload_data, "eff_strengths", {}) or {})
    combust_planets = set(getattr(payload_data, "combust_planets", []) or [])
    neecha_bhanga = set(getattr(payload_data, "neecha_bhanga_planets", []) or [])
    current_age = float(getattr(payload_data, "current_age", 0.0) or 0.0)
    active_dasha_lord = getattr(payload_data, "active_dasha_lord", "") or _get_active_dasha_lord(
        getattr(payload_data, "dasha_sequence", []) or [],
        current_age,
    )
    antardasha_lord = getattr(payload_data, "antardasha_lord", "") or ""  # G5
    dasha_sequence = getattr(payload_data, "dasha_sequence", []) or []

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
        if antardasha_lord and planet == antardasha_lord and planet != active_dasha_lord:  # G5
            roles.append("Antardasha_Lord")
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
        alpha, alpha_notes = _mrita_alpha(planet, roles, sign, degree, shadbala,
                                          neecha_bhanga=(planet in neecha_bhanga))
        vm, d24_house, vm_notes = _varga_multiplier(planet, sign, d24_chart, d24_lagna)
        sdb_mult    = _shadbala_mult(shadbala, planet)  # G6, per-planet BPHS minimum
        total_factor = role_weight * alpha * vm * sdb_mult
        field_weight = float(field_affinity.get(planet, 0.0) or 0.0)
        contribution = field_weight * total_factor * _STREAM_SCALE

        if contribution > 0:
            score += contribution
            rubric_core += contribution
            dignity_label = compute_dignity(planet, sign) or "neutral"
            _timing_roles = [r for r in ("Dasha_Lord", "Antardasha_Lord") if r in roles]
            _timing_note = f" (currently {'/'.join(_timing_roles)}, informational only)" if _timing_roles else ""
            trace.append(f"{planet} aligns with {dignity_label} dignity.{_timing_note}")
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

    # ── G1: Rahu / Ketu — unconventional / shadow-planet career significators ────
    for planet in ("Rahu", "Ketu"):
        pdata    = planets_d1.get(planet, {}) or {}
        sign     = pdata.get("sign", "")
        try:
            degree = float(pdata.get("degree", 0.0))
        except (TypeError, ValueError):
            degree = 0.0
        rk_roles: list = []
        if active_dasha_lord and planet == active_dasha_lord:
            rk_roles.append("Dasha_Lord")
        if antardasha_lord and planet == antardasha_lord:
            rk_roles.append("Antardasha_Lord")
        # Stage 5 fix: rk_roles above can ONLY ever contain Dasha_Lord/
        # Antardasha_Lord (Rahu/Ketu have no other role class in this
        # method), so the old `max(_ROLE_WEIGHTS.get(r,1.0) for r in
        # rk_roles, default=0.70)` was a pure timing-gated elevation --
        # Rahu/Ketu got the full 0.70 shadow-planet structural discount
        # UNLESS they happened to be the current dasha/antardasha lord, in
        # which case the discount vanished (1.0) or nearly doubled to 1.5x.
        # Same fusion problem as the main loop above: kept as a fixed
        # structural discount now, independent of current timing (which
        # confidence_dimensions.py's timing_fit already covers separately).
        # rk_roles is still populated and available in trace below for
        # audit visibility.
        # 2026-08-20 gap-audit fix (hands-on chart-audit finding): this was
        # a FLAT 0.70 discount applied to every Rahu/Ketu contribution
        # regardless of house quality -- a node sitting in a kendra (e.g.
        # Ketu in the 10th/Karma Bhava, one of the most classically
        # decisive placements a chart can have) got the exact same
        # discount as one sitting in a dusthana. Made house-placement-aware
        # instead: kendra placement keeps the least discount (nodes are
        # still treated more cautiously than a dignified graha, per
        # classical convention), dusthana placement keeps the heaviest.
        _rk_house = whole_houses.get(planet, 0)
        if _rk_house in _KENDRA_HOUSES:
            rk_role_weight = 0.85
        elif _rk_house in _TRIKONA_HOUSES:
            rk_role_weight = 0.80
        elif _rk_house in _DUSTHANA_HOUSES:
            rk_role_weight = 0.55
        else:
            rk_role_weight = 0.70
        vm_rk, _, _ = _varga_multiplier(planet, sign, d24_chart, d24_lagna)
        field_weight = float(field_affinity.get(planet, 0.0) or 0.0)
        contribution = field_weight * rk_role_weight * vm_rk * _STREAM_SCALE
        if contribution > 0:
            score += contribution; rubric_core += contribution
            _rk_timing_note = f" (currently {'/'.join(rk_roles)})" if rk_roles else ""
            trace.append(
                f"{planet} shadow-planet contribution to field ({planet} weight={field_weight:.2f})."
                f"{_rk_timing_note}"
            )
            components[f"{planet.lower()}_contribution"] = round(contribution, 2)

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
        planet_house=whole_houses,
    ) * 100.0
    if dusthana_pen > 0:
        score -= dusthana_pen; rubric_penalty -= dusthana_pen
        components["dusthana_penalty"] = round(-dusthana_pen, 2)
        trace.append("Dusthana lordship weakens the career signature.")

    # 2026-07 engine-gap audit fix (Phase 4, centralized debility/combustion
    # penalty): KP, Jaimini, and Parashara all call the shared
    # _planet_combustion_penalty() helper; KNRao -- one of the two
    # highest-weighted methods (24% authority prior) -- never called it at
    # all, so a genuinely combust field-driving planet was invisible to
    # KNRao's score while three of the other four methods penalized it,
    # producing exactly the "same placement penalized here but not there"
    # inconsistency the audit found repeatedly. Same shared helper, same
    # call shape as parashara.py, so KNRao is now held to the same standard.
    combustion_pen = _planet_combustion_penalty(
        field_affinity,
        combust_planets,
        planet_dignities,
        planets_d1,
        vargottama_planets=getattr(payload_data, "vargottama_planets", []),
    ) * 100.0
    if combustion_pen > 0:
        score -= combustion_pen; rubric_penalty -= combustion_pen
        components["combustion_penalty"] = round(-combustion_pen, 2)
        trace.append("Combust field-driving planet weakens KNRao's career signature.")

    # D9 gap-audit fix (2026-08): the "D9 first-class career signal" block
    # formerly here (D9 lagna lord + D9-H10 lord, capped ~15 pts) has been
    # removed -- it computed the D9 lagna lord's DIGNITY using its D1 sign
    # (`compute_dignity(_d9_ll, _d9_ll_d1_sign)`), which evaluates the planet
    # as if placed in D1, not D9. That mislabeled a D1-thread signal as a D9
    # test and duplicated (inconsistently) the properly D9-internal version
    # of this exact technique now built into navamsha.py's
    # score_navamsha_adjustment() -- see that module's `_d9_h10_score` (uses
    # real D9 sign dignity via d9_planet_dignities, plus D9-internal house
    # placement and Vargottama, none of which this block had). Removing here
    # avoids double-counting the same classical technique once correctly and
    # once with a sign-source bug.
    # Legacy validation bonus (kept for backward compat)
    d9_bonus = _d9_h10_bonus(field_affinity, d9_chart, d9_lagna) * 20.0
    if d9_bonus > 0:
        _b = (100.0 - score) * (d9_bonus / 100.0)
        score += _b; rubric_validation += _b
        components["d9_validation"] = round(_b, 2)
        trace.append("D9 10th house alignment: karaka planet in navamsha career house.")

    # ── D10 H10 occupant bonus ────────────────────────────────────────────────
    d10_h10_bonus = 0.0
    _D10_DIG_MULT = {"EXALTED":1.5,"OWN":1.3,"NEECHA_BHANGA":1.1,"NEUTRAL":1.0,"DEBILITATED":0.5}
    for p in d10_h10_planets:
        w = field_affinity.get(p, 0.0)
        if w >= 0.10:
            d10_dig_m = _D10_DIG_MULT.get(d10_digs.get(p,"NEUTRAL"), 1.0)  # G13
            d10_h10_bonus += 4.0 * w * d10_dig_m
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

    # ── G2: Arudha Lagna (AL) & A10 alignment ────────────────────────────────
    for pada_lord, label_str in ((al_lord, "AL"), (a10_lord, "A10")):
        if not pada_lord:
            continue
        _pa_w = field_affinity.get(pada_lord, 0.0)
        if _pa_w >= 0.10:
            _pa_b = _pa_w * 10.0 * (eff.get(pada_lord, 0.5))
            score += _pa_b; rubric_support += _pa_b
            components[f"{label_str.lower()}_lord"] = round(_pa_b, 2)
            trace.append(f"{label_str} lord {pada_lord} aligns with field (public/career standing).")

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

    # ── N2: SAV H10 bindu gate ───────────────────────────────────────────────
    _sav_kn = getattr(payload_data, "sav_points_houses", {}) or {}
    _sav_h10_kn = _sav_kn.get("10", _sav_kn.get(10, 28))
    _sav_mult_kn = 1.20 if _sav_h10_kn >= 35 else 1.10 if _sav_h10_kn >= 30 else 0.85 if _sav_h10_kn <= 20 else 1.0

    # ── H10 lord kendra/trikona or dusthana placement ────────────────────────
    _kn_h10_kt_bonus = 0.0
    if h10_lord and h10_lord_house > 0:
        if h10_lord_house in {1, 4, 7, 10, 5, 9}:
            _b = 26.0 * field_affinity.get(h10_lord, 0.0) * _sav_mult_kn
            if _b > 0:
                score += _b; rubric_core += _b
                components["h10_lord_kendra_trikona"] = round(_b, 2)
                trace.append(f"H10 lord ({h10_lord}) in house {h10_lord_house} -- kendra/trikona.")
                _kn_h10_kt_bonus = _b
        elif h10_lord_house in {6, 8, 12}:
            _pen = 18.0 * field_affinity.get(h10_lord, 0.0)
            if _pen > 0:
                score -= _pen; rubric_penalty -= _pen
                components["h10_lord_dusthana"] = round(-_pen, 2)
                trace.append(f"H10 lord ({h10_lord}) in dusthana house {h10_lord_house} -- weakens career.")

    # ── N1: H6 (Seva), H11 (Labha) and H2 (Dhana) lord scoring ──────────────
    # H10 (scored above, up to 26 pts) is the sole PRIMARY career house. These
    # three are classically CONFIRMATORY, not primary, and are weighted in
    # descending classical relevance: H6 = service/employment/daily labor
    # (K.N. Rao treats a strong, well-placed 6th lord as a genuine
    # service-career signal in its own right, not limited to any particular
    # profession); H11 = labha, the realized fruit/gains of professional
    # effort -- a more direct career-confirmatory house than H2; H2 =
    # accumulated wealth/speech, the weakest and most indirect of the three,
    # mainly relevant to speech-driven professions.
    #
    # Astrological-calibration fix (2026-08-20, Claude session, real-chart
    # audit): this block previously also scored H4 (Vidya/foundational-
    # education lord) here, inside the SAME career-RANKING blend that
    # jyotish/tiered_ranking.py deliberately excludes Siddhamsha (the
    # dedicated D24 education varga) from -- see that module's own docstring:
    # "Siddhamsha... is the classical education/learning varga, not a
    # career-field varga... folding it into the field-ranking blend was part
    # of what let the old flat blend's field-choice and education-route
    # signals bleed into each other." KNRao (a Tier-1 method) carrying its
    # own H4-Vidya-lord bonus reopened exactly that leak from inside the
    # blend the exclusion was meant to protect. Removed here -- H4/education
    # is Siddhamsha's job, not KNRao's.
    #
    # It also previously multiplied every one of these contributions by an
    # undocumented, unexplained `* 2.0` -- directly contradicting this same
    # block's own prior comment ("H2 = 12 pts x affinity... < H10's 26 pts").
    # With dignity (up to 1.40x) and position (up to 1.30x) also stacked in,
    # a single one of these SECONDARY houses could reach ~44 points under the
    # old code -- exceeding H10's own ~31-point ceiling (26 x up to 1.2 SAV
    # multiplier), i.e. a confirmatory house could outscore the one primary
    # career house it exists to confirm. Confirmed live on a real chart
    # (Ramsunder): H2's inflated contribution alone (12.26 pts) was the
    # single largest KNRao component separating international_law from
    # materials_science_engineering, more than the fields' entire final
    # KNRao gap. The `* 2.0` is removed; base weights below are recalibrated
    # to stay clearly subordinate to H10 and reflect the corrected
    # H6 > H11 > H2 classical ordering.
    #
    # H6 was previously scored ONLY as a separate, narrower special case
    # (see the removed "H6 lord as positive service-field signal" block
    # below this function) gated on the FIELD'S ENGLISH LABEL matching one
    # of nine hardcoded keywords (medicine/defence/military/law/police/
    # nursing/surgery/forensics/social work) -- meaning "law" had structural
    # access to a service-house bonus that e.g. "materials_science_
    # engineering" could never reach, regardless of what the chart itself
    # showed. Folded into this general loop instead, gated the same way
    # H2/H10/H11 already are (the chart's own placement and dignity), not by
    # the field's name.
    h6_lord  = house_lords.get("6", "")
    h11_lord = house_lords.get("11", "")
    h2_lord  = house_lords.get("2", "")
    for _hl, _pts, _label in ((h6_lord, 12.0, "H6-Seva"), (h11_lord, 10.0, "H11-Labha"), (h2_lord, 7.0, "H2-Dhana")):
        if not _hl:
            continue
        _hw = field_affinity.get(_hl, 0.0)
        if _hw >= 0.10:
            _hh = whole_houses.get(_hl, 0)
            # Dignity-based multiplier for the confirmatory house lord
            _hdig = compute_dignity(_hl, (planets_d1.get(_hl) or {}).get("sign", ""))
            _hdig_m = {"EXALTED": 1.40, "OWN": 1.20, "NEECHA_BHANGA": 1.05,
                       "NEUTRAL": 1.00, "DEBILITATED": 0.60}.get(_hdig or "NEUTRAL", 1.00)
            # Position modifier: kendra/trikona = 1.3×, neutral = 1.0×, dusthana = 0.7×
            _hpos_m = (1.30 if _hh in {1,4,7,10,5,9} else
                       0.70 if _hh in {6,8,12} else 1.00)
            _hb = _hw * _pts * _hdig_m * _hpos_m * eff.get(_hl, 0.5)
            score += _hb; rubric_support += _hb
            components[f"{_label.lower().replace('-','_')}_lord"] = round(_hb, 2)
            trace.append(f"{_label} lord {_hl} (H{_hh}) aligns with field — confirmatory house support.")

    # ── Fix 7: H3 (Parakrama) lord — hands-on skill and effort house ───────────
    # H3 governs courage, personal skill, technical effort, and direct action.
    # Classical: strong H3 lord → native excels through self-effort rather than position.
    # Key fields: engineering, surgery, sports, journalism, military, music performance,
    #             crafts, programming, design, photography, architecture.
    h3_lord = house_lords.get("3", "")
    if h3_lord:
        _h3w = field_affinity.get(h3_lord, 0.0)
        _h3_skill_kws = ["engineering","surgery","sports","journalism","military","craft",
                         "music","mechanical","technical","data","communication","computer",
                         "media","design","writing","photography","architecture","programming","robotics"]
        if _h3w >= 0.08 and any(_kw in field_id.lower() for _kw in _h3_skill_kws):
            _h3h = whole_houses.get(h3_lord, 0)
            _h3dig = compute_dignity(h3_lord, (planets_d1.get(h3_lord) or {}).get("sign", ""))
            _h3dig_m = {"EXALTED": 1.30, "OWN": 1.15, "NEECHA_BHANGA": 1.05,
                        "NEUTRAL": 1.00, "DEBILITATED": 0.60}.get(_h3dig or "NEUTRAL", 1.00)
            _h3pos_m = (1.20 if _h3h in {1,3,9,10,5} else
                        0.75 if _h3h in {6,8,12} else 1.00)
            # 2026-08-22 reconciliation (JyotishAI reference-audit method #7,
            # owner-approved fix): removed an undocumented trailing "* 2.0"
            # that pushed this stated-7.0-weight confirmatory (H3 Parakrama)
            # bonus's ceiling above the H10 lord's own primary 26pt kendra/
            # trikona bonus -- the exact anti-pattern this file's own N1
            # comment block (H6/H11/H2 section, ~line 656) documents fixing
            # for the H2/H6/H11 confirmatory houses ("a confirmatory house
            # could outscore the one primary career house it exists to
            # confirm"), reintroduced here for H3 without comment.
            _h3b = _h3w * 7.0 * _h3dig_m * _h3pos_m * eff.get(h3_lord, 0.5)
            score += _h3b; rubric_support += _h3b
            components["h3_parakrama_lord"] = round(_h3b, 2)
            trace.append(f"H3 (Parakrama) lord {h3_lord} (H{_h3h}) supports skill-driven field.")

    # ── G12: H10 from Chandra Lagna ────────────────────────────────────────────
    _cl_h10_lord = _chandra_lagna_h10_lord(planets_d1)
    if _cl_h10_lord:
        _cl_w = field_affinity.get(_cl_h10_lord, 0.0)
        if _cl_w >= 0.10:
            _cl_b = _cl_w * 8.0 * eff.get(_cl_h10_lord, 0.5)
            score += _cl_b; rubric_support += _cl_b
            components["chandra_lagna_h10"] = round(_cl_b, 2)
            trace.append(f"H10 from Chandra Lagna lord {_cl_h10_lord} aligns with field.")

    # ── §9 remediation: H10 from Surya Lagna (Sun-based ascendant) ────────────
    # Completes the spec's named triple-confirmation technique (Lagna + Moon +
    # Sun) directly in the K.N. Rao module, at the same modest magnitude as
    # the Chandra Lagna layer just above -- this is a confirmation check, not
    # an independent scoring channel, so it stays capped small like its
    # Chandra sibling rather than opening a new full sub-scorer.
    _sl_h10_lord = _surya_lagna_h10_lord(planets_d1)
    if _sl_h10_lord:
        _sl_w = field_affinity.get(_sl_h10_lord, 0.0)
        if _sl_w >= 0.10:
            _sl_b = _sl_w * 8.0 * eff.get(_sl_h10_lord, 0.5)
            score += _sl_b; rubric_support += _sl_b
            components["surya_lagna_h10"] = round(_sl_b, 2)
            trace.append(f"H10 from Surya Lagna lord {_sl_h10_lord} aligns with field.")

    # ── §9 remediation: explicit triple-ascendant confirmation ────────────────
    # The named technique's actual point is agreement across the three bases
    # (Lagna, Chandra, Surya). Per §9, "a planet occupying or ruling 2 or more
    # of these three derived 10th houses gets a confirmation bonus (+5%)" --
    # a 2-of-3 threshold, not strict 3-of-3 agreement. We find whichever
    # candidate lord (from h10_lord / _cl_h10_lord / _sl_h10_lord) has the
    # highest agreement count and, if it reaches 2+, apply one small, bounded
    # confirmation bonus (capped at 5 points -- roughly a 5% nudge on this
    # method's own ~100-pt scale, in line with §9's "modest confirmation
    # bonus (5-10%)" ceiling). Full 3-of-3 agreement gets the full bonus;
    # partial 2-of-3 agreement gets a slightly reduced bonus, since full
    # agreement is the strongest form of this confirmation.
    from collections import Counter as _KNTripleCounter
    _kn_lord_counts = _KNTripleCounter(
        l for l in (h10_lord, _cl_h10_lord, _sl_h10_lord) if l
    )
    _triple_lord, _triple_count = (
        max(_kn_lord_counts.items(), key=lambda kv: kv[1])
        if _kn_lord_counts else ("", 0)
    )
    _triple_b = 0.0
    if _triple_count >= 2 and field_affinity.get(_triple_lord, 0.0) > 0:
        _agreement_mult = 1.0 if _triple_count == 3 else 0.7
        _triple_b = min(5.0, 5.0 * field_affinity.get(_triple_lord, 0.0)) * _agreement_mult
        score += _triple_b; rubric_support += _triple_b
        components["triple_ascendant_h10_confirmation"] = round(_triple_b, 2)
        if _triple_count == 3:
            trace.append(
                f"K.N. Rao triple-ascendant confirmation: H10 lord {_triple_lord} agrees across "
                "Lagna, Chandra Lagna, AND Surya Lagna simultaneously — the named §9 technique."
            )
        else:
            trace.append(
                f"K.N. Rao confirmation: H10 lord {_triple_lord} occupies/rules 2 of the 3 "
                "derived 10th houses (Lagna, Chandra Lagna, Surya Lagna) — the named §9 "
                "technique's 2-of-3 confirmation threshold."
            )

    # ── §9 remediation: family/environmental/interest-context flag ────────────
    # Full Methodology Spec §9 also requires checking a strongly-supported
    # field against the native's STATED family/environmental/interest
    # context, to flag fields that are astrologically strong but outside
    # what the person has been exposed to ("high-potential, needs deliberate
    # exposure") -- previously no such data ingestion or flag existed
    # anywhere in the codebase. This reads an OPTIONAL payload field
    # (`stated_interests` / `family_environment_context`, either a list of
    # strings or a single string) that a caller may not populate; when
    # absent, the flag is simply never raised (never a penalty for missing
    # context data, matching this engine's consistent pattern elsewhere).
    _stated_ctx = (
        getattr(payload_data, "stated_interests", None)
        or getattr(payload_data, "family_environment_context", None)
    )
    high_potential_needs_exposure = False
    if _stated_ctx:
        if isinstance(_stated_ctx, str):
            _stated_ctx = [_stated_ctx]
        _ctx_text = " ".join(str(c) for c in _stated_ctx).lower()
        _field_text = (label or "").lower()
        _mentioned = bool(_field_text) and any(
            tok in _ctx_text for tok in _field_text.split() if len(tok) > 3
        )
        _strongly_supported = (
            _triple_count >= 2
            and field_affinity.get(_triple_lord, 0.0) >= 0.3
        )
        if _strongly_supported and not _mentioned:
            high_potential_needs_exposure = True
            trace.append(
                "FLAG: this field has strong triple-ascendant astrological support but does not "
                "appear among the native's stated family/environmental/interest context — "
                "high-potential, may need deliberate exposure rather than being astrologically weak."
            )

    # ── G19: Nakshatra lord house chain ────────────────────────────────────────
    from jyotish.constants import _NAKSHATRA_LORD
    _planet_naks = getattr(payload_data, "planet_nakshatras", {}) or {}
    _ph = getattr(payload_data, "planet_house", {}) or {}
    for _p, _pw in field_affinity.items():
        if _pw < 0.15:
            continue
        _nak = _planet_naks.get(_p, "")
        if not _nak:
            continue
        _nak_lord = _NAKSHATRA_LORD.get(_nak, "")
        _nak_house = _ph.get(_nak_lord, 0)
        if _nak_house in {1, 5, 9, 10}:
            _nb = _pw * 4.0
            score += _nb; rubric_support += _nb
            components[f"{_p.lower()}_nak_lord_kendra"] = round(_nb, 2)
        elif _nak_house in {6, 8, 12}:
            _np = _pw * 3.0
            score -= _np; rubric_penalty -= _np
            components[f"{_p.lower()}_nak_lord_dusthana"] = round(-_np, 2)

    # ── N3: Badhaka lord penalty ─────────────────────────────────────────────
    # Badhaka = obstacle house lord. Classical rule:
    #   Movable lagna (Aries/Cancer/Libra/Capricorn) → H11 is Badhaka
    #   Fixed lagna (Taurus/Leo/Scorpio/Aquarius)    → H9 is Badhaka
    #   Dual lagna (Gemini/Virgo/Sagittarius/Pisces) → H7 is Badhaka
    # When the Badhaka lord is a top career planet, it creates life-obstacles.
    _BADHAKA_LAGNA_MAP = {
        "Aries": 11, "Cancer": 11, "Libra": 11, "Capricorn": 11,
        "Taurus": 9, "Leo": 9, "Scorpio": 9, "Aquarius": 9,
        "Gemini": 7, "Virgo": 7, "Sagittarius": 7, "Pisces": 7,
    }
    if lagna_sign:
        _bh_num = _BADHAKA_LAGNA_MAP.get(lagna_sign, 0)
        if _bh_num:
            _badhaka_lord = house_lords.get(str(_bh_num), "")
            if _badhaka_lord:
                _bk_w = field_affinity.get(_badhaka_lord, 0.0)
                if _bk_w >= 0.15:
                    _bk_pen = _bk_w * 6.0
                    score -= _bk_pen; rubric_penalty -= _bk_pen
                    components["badhaka_lord_penalty"] = round(-_bk_pen, 2)
                    trace.append(f"Badhaka lord {_badhaka_lord} (H{_bh_num}) "
                                 f"is a field planet — obstacle indicator.")

    # ── Systematic karaka-domain bonus (replaces reliance on hand-curated keywords) ──
    # Unlike the T2 keyword blocks below, this fires for *any* field whose coarse
    # `domain` maps to a karaka category, using each planet's own field_affinity
    # weight, dignity, and house placement — not a substring match against field_id.
    _karaka_total, _karaka_hits = _karakatwa_domain_bonus(
        domain, field_affinity, planets_d1, whole_houses, payload_data,
        scale=6.0, cap=12.0,
    )
    if _karaka_total > 0:
        score += _karaka_total; rubric_support += _karaka_total
        components["karaka_domain_bonus"] = round(_karaka_total, 2)
        trace.append(
            f"Karakatwa domain match ({domain}): {', '.join(_karaka_hits)} carry classical "
            "significator authority for this domain (systematic karaka-to-field mapping)."
        )

    # ── Ontology fix: house-signification-first primitive ────────────────────
    # KNRao's own technique is already house-centric (H10 lord, H2/H11 artha,
    # H3 parakrama, Badhaka), but each check above is field-*label* keyword
    # gated (e.g. _SERVICE_FIELDS_KN). This adds the domain-driven house
    # signal (H6/H8/H12 for medicine, H6/H7/H9 for law, etc.) that applies to
    # every field in a matching domain regardless of label wording.
    _house_total_kn, _house_hits_kn = _house_signification_bonus(
        domain, field_affinity, house_lords, whole_houses, planets_d1,
        payload_data, scale=5.0, cap=12.0,
    )
    if _house_total_kn > 0:
        score += _house_total_kn; rubric_support += _house_total_kn
        components["house_signification_bonus"] = round(_house_total_kn, 2)
        trace.append(
            f"House signification ({domain}): {', '.join(_house_hits_kn)} lord(s) "
            "carry classical house authority for this field."
        )

    # ── T2-A: Lagna tatva career cluster ────────────────────────────────────
    _TATVA_FIELD_KW = {
        "fire":  ["defence","military","surgery","engineering","sports","police","metallurgy","pioneer","leadership"],
        "earth": ["medicine","pharmacy","agriculture","finance","banking","commerce","accounting","law","administration","management","architecture"],
        "air":   ["technology","software","research","media","communication","psychology","teaching","journalism","aviation","animation"],
        "water": ["nursing","healing","arts","music","film","creative","spiritual","hospitality","marine","social work"],
    }
    _TATVA_SIGN = {
        "Aries":"fire","Leo":"fire","Sagittarius":"fire",
        "Taurus":"earth","Virgo":"earth","Capricorn":"earth",
        "Gemini":"air","Libra":"air","Aquarius":"air",
        "Cancer":"water","Scorpio":"water","Pisces":"water",
    }
    _kn_lagna_sign = getattr(payload_data, "lagna_sign", "") or ""
    _kn_lagna_lord = getattr(payload_data, "lagna_lord", "") or ""
    _lagna_tatva_kn = _TATVA_SIGN.get(_kn_lagna_sign, "")
    if _lagna_tatva_kn:
        _tatva_kws_kn = _TATVA_FIELD_KW.get(_lagna_tatva_kn, [])
        if any(_wm(kw, label) for kw in _tatva_kws_kn):
            _tatva_b_kn = 4.0 * _d1_vitality_coefficient(_kn_lagna_lord, payload_data)
            score += _tatva_b_kn; rubric_support += _tatva_b_kn
            components["lagna_tatva_cluster"] = round(_tatva_b_kn, 2)
            trace.append(f"Lagna tatva ({_lagna_tatva_kn}): {_kn_lagna_sign} lagna resonates with {domain}.")

    # T2-C (H6 lord as service-field signal) removed 2026-08-20, Claude
    # session, real-chart audit: folded into the general N1 loop earlier in
    # this function (h6_lord, now weighted highest of the three confirmatory
    # houses: H6 > H11 > H2), gated on the chart's own placement/dignity like
    # H2/H10/H11 already are, rather than on the field's English label
    # matching one of a fixed keyword list (which structurally favored
    # "law"/"medicine"/etc. over every other field regardless of the actual
    # chart). See the N1 block's own comment for the full rationale.
    _kn_house_lords = getattr(payload_data, "house_lords", {}) or {}
    _kn_ph = getattr(payload_data, "planet_house", {}) or {}
    _kn_planet_digs = getattr(payload_data, "planet_dignities", {}) or {}

    # ── T2-E: Rahu in H10 career yoga ───────────────────────────────────────
    _RAHU_FRIENDLY_KN = {"Gemini","Virgo","Libra","Sagittarius","Aquarius","Taurus"}
    _RAHU_EXALTED_KN  = {"Gemini", "Taurus"}
    _MODERN_FIELDS_KN = ["technology","software","ai","media","digital","international","aviation","animation",
                         "film","foreign","research","commerce","entrepreneurship","engineering","architecture"]
    _kn_planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    _kn_rahu_h = _kn_ph.get("Rahu", 0)
    _kn_rahu_sign = (_kn_planets_d1.get("Rahu") or {}).get("sign", "")
    if _kn_rahu_h == 10 and any(_wm(kw, label) for kw in _MODERN_FIELDS_KN):
        if _kn_rahu_sign in _RAHU_FRIENDLY_KN:
            _kn_rahu_mult = 1.3 if _kn_rahu_sign in _RAHU_EXALTED_KN else 1.0
            _kn_rahu_b = field_affinity.get("Rahu", 0.1) * 8.0 * _kn_rahu_mult
            _kn_rahu_b = min(_kn_rahu_b, 9.0)
            if _kn_rahu_b > 0:
                score += _kn_rahu_b; rubric_support += _kn_rahu_b
                components["rahu_h10_yoga"] = round(_kn_rahu_b, 2)
                trace.append(f"Rahu in H10 ({_kn_rahu_sign}): modern career yoga (KNRao).")

    # ── T2-D: D1+D10 double-dignity compound ────────────────────────────────
    _kn_h10_lord = getattr(payload_data, "h10_lord", "") or ""
    _kn_d1_h10_dig  = _kn_planet_digs.get(_kn_h10_lord, "")
    _kn_d10_planets = getattr(payload_data, "d10_planet_dignities", {}) or {}
    _kn_d10_h10_dig = _kn_d10_planets.get(_kn_h10_lord, "")
    # Gap 0.2 fix: dignity strings are UPPERCASE — lowercase set made T2-D dead code.
    _DIG_STRONG_KN  = {"EXALTED", "OWN", "MOOLATRIKONA"}
    if _kn_h10_lord and _kn_d1_h10_dig in _DIG_STRONG_KN and _kn_d10_h10_dig in _DIG_STRONG_KN:
        _kn_dd_aff = field_affinity.get(_kn_h10_lord, 0.0)
        if _kn_dd_aff >= 0.10:
            _kn_dd_b = _kn_dd_aff * 10.0 * _d1_vitality_coefficient(_kn_h10_lord, payload_data)
            _kn_dd_b = min(_kn_dd_b, 12.0)
            score += _kn_dd_b; rubric_validation += _kn_dd_b
            components["d1_d10_double_dignity"] = round(_kn_dd_b, 2)
            trace.append(f"D1+D10 double-dignity: {_kn_h10_lord} is {_kn_d1_h10_dig}/{_kn_d10_h10_dig} — exceptional career mandate (KNRao).")

    # ── Rao's dasha-sequential thread technique ───────────────────────────────
    # Trace across the full dasha sequence (not just the active dasha) to find
    # which mahadasha *first* activated affinity for this field, then check
    # whether the current dasha lord continues, or is itself, that originating
    # thread. This is Rao's signature: career timing is read dasha-by-dasha,
    # explaining *why this dasha specifically* rather than only *which field*.
    _orig_lord, _cur_lord, _elapsed = _dasha_career_thread(dasha_sequence, current_age, field_affinity)
    if _orig_lord:
        _thread_w = field_affinity.get(_orig_lord, 0.0)
        _thread_vit = _d1_vitality_coefficient(_orig_lord, payload_data)
        if _orig_lord == _cur_lord:
            # The originating dasha is running right now — direct timing confirmation.
            _thread_b = min(_thread_w * 9.0 * _thread_vit, 9.0)
            trace.append(
                f"Dasha thread: {_orig_lord} first activated this field and is the "
                f"currently running dasha lord -- direct timing confirmation (KNRao method)."
            )
        else:
            # A later dasha lord continues the thread activated earlier.
            _continuation_aff = field_affinity.get(_cur_lord, 0.0)
            _continuation_bonus = 1.4 if _continuation_aff >= 0.15 else 1.0
            _thread_b = min(_thread_w * 5.0 * _thread_vit * _continuation_bonus, 7.0)
            trace.append(
                f"Dasha thread: field first activated in {_orig_lord}'s dasha "
                f"({_elapsed} dasha(s) elapsed), now continuing into {_cur_lord or 'the running'} "
                f"dasha -- explains why the profession is timed through this sequence (KNRao method)."
            )
        if _thread_b > 0:
            score += _thread_b
            rubric_validation += _thread_b
            components["dasha_thread"] = round(_thread_b, 2)

    # ── gap fix 2026-08-18 (G): minimal retrograde (vakri) strength note ───────
    # Classical basis: BPHS's own Cheshta Bala (part of Shadbala, jyotish/
    # shadbala.py::compute_cheshta_bala) already treats retrograde motion as a
    # STRENGTH-ADDING state for the visible planets (a planet appearing to move
    # backward is judged to be exerting unusually intense effort/cheshta), not
    # a weakness -- distinct from the KP convention (kp.py, above) that a
    # retrograde planet's SIGNIFICATION extends to its previous house. KNRao's
    # method already emphasizes planet-role and dasha-thread strength (see
    # above), so the appropriate minimal retrograde signal here is strength,
    # not house-extension: if the H10 lord itself is retrograde, add a small
    # bounded (+1.5 flat) corroboration, since a strengthened H10 lord is
    # itself already the method's central technique.
    _kn_retro_set = getattr(payload_data, "retrograde_planets", set()) or set()
    if _kn_h10_lord and _kn_h10_lord in _kn_retro_set:
        _kn_retro_b = 1.5
        score += _kn_retro_b
        rubric_validation += _kn_retro_b
        components["retrograde_h10_lord_cheshta"] = round(_kn_retro_b, 2)
        trace.append(
            f"Retrograde (vakri) H10 lord {_kn_h10_lord}: classical Cheshta Bala treats "
            "retrograde motion as strength-adding, not weakening -- small corroboration (KNRao)."
        )
    else:
        _kn_retro_b = 0.0

    # 2026-08-22 reconciliation (JyotishAI reference-audit method #7,
    # owner-approved fix): h10_lord_kendra_trikona (up to 26pt),
    # d1_d10_double_dignity (up to 12pt), and retrograde_h10_lord_cheshta
    # (flat 1.5pt) are three independently-designed positive bonuses that
    # all credit the SAME planet's SAME underlying strength/placement fact
    # -- the H10 lord's dignity and position -- with no group ceiling
    # (only role_weight in the earlier core-planet loop and 3 more indirect
    # H10-lord-adjacent components -- d9_validation, d10_h10, Vimshopaka --
    # also touch this planet, but those aren't gated strictly to "the H10
    # lord" the way these three are, so this cap covers the unambiguous
    # subset first). Bound this specific three-component family at 32pt --
    # modest headroom above the kendra/trikona bonus's own 26pt ceiling for
    # a genuine multi-technique convergence -- clawing back from the
    # smallest/most-derivative signals first (retrograde corroboration,
    # then double-dignity) before touching the primary placement bonus.
    _kn_h10_family_ceiling = 32.0
    _kn_h10_family_total = _kn_h10_kt_bonus + components.get("d1_d10_double_dignity", 0.0) + _kn_retro_b
    if _kn_h10_family_total > _kn_h10_family_ceiling:
        _kn_h10_excess = _kn_h10_family_total - _kn_h10_family_ceiling
        _kn_dd_current = components.get("d1_d10_double_dignity", 0.0)
        _take_retro = min(_kn_retro_b, _kn_h10_excess)
        if _take_retro > 0:
            score -= _take_retro; rubric_validation -= _take_retro
            components["retrograde_h10_lord_cheshta"] = round(_kn_retro_b - _take_retro, 2)
            _kn_h10_excess -= _take_retro
        if _kn_h10_excess > 0 and _kn_dd_current > 0:
            _take_dd = min(_kn_dd_current, _kn_h10_excess)
            score -= _take_dd; rubric_validation -= _take_dd
            components["d1_d10_double_dignity"] = round(_kn_dd_current - _take_dd, 2)
            _kn_h10_excess -= _take_dd
        trace.append(
            f"KNRao H10-lord family (kendra/trikona + double-dignity + retrograde) "
            f"exceeded {_kn_h10_family_ceiling}pt combined ceiling -- clawed back from "
            "the smallest/most-derivative signals first, primary placement bonus left intact."
        )

    # ── Vimshopaka Bala: unified divisional-strength coefficient ─────────────
    # Fix (cross-cutting gap): divisional strength was previously approximated
    # ad hoc per method (D9/D10 dignity multipliers scattered through the score
    # above) with no single reconciling signal. This applies the shared reduced
    # Vimshopaka Bala (D1/D3/D9/D10/D20/D24/D30 dignity, weighted per BPHS) as a
    # bounded nudge on the field's top-weighted planets, so a planet strong
    # across most of its divisional charts gets modest additional credit here
    # (and a planet weak across most of them a modest debit) independent of
    # whichever single varga each bonus above happened to check.
    _vim_planets = top_weighted_planets(field_affinity, 2)
    if _vim_planets:
        _vim_avg = sum(_vimsopaka_bala_coefficient(p, payload_data) for p in _vim_planets) / len(_vim_planets)
        _vim_adj = (_vim_avg - 1.0) * 15.0
        if abs(_vim_adj) > 0.05:
            score += _vim_adj
            rubric_validation += _vim_adj
            components["vimsopaka_bala"] = round(_vim_adj, 2)
            trace.append(
                f"Vimshopaka Bala (D1/D3/D9/D10/D20/D24/D30) for {', '.join(_vim_planets)}: "
                f"avg coefficient {_vim_avg:.2f} -- unified divisional strength "
                f"{'supports' if _vim_adj > 0 else 'weakens'} this field."
            )

    rubric = build_score_rubric(
        "knrao",
        [
            rubric_section("core", rubric_core, 60.0,
                note="Planet role × Mrita alpha × D24 varga multiplier × affinity.",
                items=["contribution", "h10_lord_kendra_trikona"]),
            rubric_section("support", rubric_support, 20.0,
                note="Cluster bonuses, systematic karaka-domain mapping, house-signification-first bonus, "
                     "and whole-sign career house alignment.",
                items=["life_science_cluster", "space_aerospace_cluster", "karaka_domain_bonus",
                       "house_signification_bonus", "whole_sign_career"]),
            rubric_section("validation", rubric_validation, 20.0,
                note="D9/D10 divisional confirmation, dasha-sequential thread timing, Vimshopaka Bala.",
                items=["d9_validation", "d10_h10", "d10_lagna_lord_bonus", "dasha_thread", "vimsopaka_bala",
                       "retrograde_h10_lord_cheshta"]),
            rubric_section("penalty", rubric_penalty, 20.0, kind="penalty",
                note="Dusthana lordship, H10 lord in dusthana, and vitality drag.",
                items=["dusthana_penalty", "h10_lord_dusthana", "vitality_penalty"]),
        ],
    )

    # Phase B (shadow-score migration, audit item A): surface the specific
    # planet(s) that actually drove this field's score -- purely additive,
    # sourced from the per-planet `{planet.lower()}_contribution` components
    # this function already populates in the core scoring loops above (never
    # a re-derivation of scoring logic). Does not change score/components/
    # trace or any existing return key.
    _knrao_confirming_planets = [
        p for p in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
        if components.get(f"{p.lower()}_contribution", 0.0) > 0.0
    ]

    # [CROSS-VERIFICATION NARRATIVE] (§9 audit, real-technique instrumentation):
    # K.N. Rao's "triple confirmation" — 10th-from-Lagna, 10th-from-Moon
    # (Chandra Lagna), 10th-from-Sun (Surya Lagna) — with each derived 10th
    # house's lord already computed above as h10_lord / _cl_h10_lord /
    # _sl_h10_lord. Report which planet(s) actually qualify (occupy/rule 2+
    # of the three derived 10ths) and that planet's own final confirmation
    # bonus for THIS method, built from local variables only.
    _kn_lord_agreement = _kn_lord_counts
    for _kp_lord, _kp_count in _kn_lord_agreement.items():
        if _kp_count >= 2:
            _kp_lord_bonus = _triple_b if _kp_lord == _triple_lord else 0.0
            if _VERBOSE_FIELD_LOG:
                print(
                    f"K.N. Rao confirmation bonus — {_kp_lord}: {(_kp_lord_bonus / 100.0):.3f} "
                    f"(rules {_kp_count} of 3 derived 10th houses)"
                )
    _kn_qualifying = [p for p, c in _kn_lord_agreement.items() if c >= 2]
    if _VERBOSE_FIELD_LOG:
        print(
        f"[CROSS-VERIFICATION NARRATIVE] K.N. Rao triple confirmation checked the "
        f"10th house derived from Lagna ({h10_lord or '—'}), from Chandra Lagna "
        f"({_cl_h10_lord or '—'}), and from Surya Lagna ({_sl_h10_lord or '—'}); "
        + (
            f"planet(s) {', '.join(_kn_qualifying)} rule 2 or more of these three derived "
            "10th houses -- the +5% confirmation bonus (scaled to 70% for a 2-of-3 "
            "match, full for 3-of-3) was applied per the spec's '2 of 3' threshold. "
            if _kn_qualifying else
            "no planet ruled 2 or more of the three derived 10th houses this pass. "
        )
        + (
            "The stated family/environmental/interest-context cross-check flagged this "
            "field as high-potential-but-needs-deliberate-exposure (strong triple-"
            "ascendant support not mentioned in the native's stated context)."
            if high_potential_needs_exposure else
            "The stated family/environmental/interest-context cross-check did not raise "
            "the 'needs deliberate exposure' flag for this field this pass."
        )
    )

    # Gap-1 (audit 2026-07) fix: cap unified with bundle via METHOD_SCORE_CAPS["knrao"].
    # Gap-3/9 fix: pass raw signed `score` (not pre-clamped) so contraindicated
    # charts (net penalties > positives) are distinguishable from neutral ones;
    # method_result() still clamps internally for the "score" field.
    return method_result("knrao", score, trace, components, rubric=rubric,
                         normalization_cap=METHOD_SCORE_CAPS["knrao"],
                         metadata={
                             "confirming_planets": _knrao_confirming_planets,
                             "triple_ascendant_h10_lord": (
                                 _triple_lord if _triple_count >= 2 else ""
                             ),
                             "high_potential_needs_exposure": high_potential_needs_exposure,
                         })
