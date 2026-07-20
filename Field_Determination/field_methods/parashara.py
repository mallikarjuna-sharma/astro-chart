"""Parashara field-determination module."""
from __future__ import annotations

from typing import Any, Dict, List

from jyotish.astro import _is_vargottama  # G7
from jyotish.boosts import (
    _yogakaraka_bonus, _h10_lord_strength_bonus, _h10_lord_trikona_bonus,
    _exalted_planet_domain_bonus, _aspect_h10_bonus, _yoga_bonus,
    _stellium_bonus, _dusthana_lord_penalty, _dharma_karma_bonus,
    _h10_bhava_bala,
    _career_houses_bhava_bala_bonus,
    _life_science_cluster_bonus, _space_aerospace_cluster_bonus,
    _d24_full_chart_bonus,
    _planet_combustion_penalty,
    _d9_h10_bonus,
    _d10_lagna_lord_bonus,
    _d1_vitality_coefficient,
    _karakatwa_domain_bonus,
    _house_signification_bonus,
    _vimsopaka_bala_coefficient,
    _wm,
)
from .common import (
    METHOD_SCORE_CAPS,
    build_gate_text,
    build_score_rubric,
    chandra_lagna_h10_lord,
    clamp_score,
    method_result,
    rubric_section,
    top_weighted_planets,
)


def score_parashara(
    payload_data: Any,
    domain: str,
    field_affinity: Dict[str, float],
    field_id: str = "",
    field_entry: Dict[str, Any] = None,
) -> Dict[str, Any]:
    # Gap-18b (generalized fix, audit 2026-07): see field_methods/common.py::build_gate_text.
    label = build_gate_text(field_id, field_entry)
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

    # ── N2: SAV H10 bindu strength gate ─────────────────────────────────────
    # Sarvashtakavarga: H10 bindu count reflects cumulative planetary support.
    # 8+ bindus = outstanding career house; 4- = weak delivery despite dignities.
    _sav = getattr(payload_data, "sav_points_houses", {}) or {}
    _sav_h10 = _sav.get("10", _sav.get(10, 28))  # default 28 = average
    _sav_mult = 1.20 if _sav_h10 >= 35 else 1.10 if _sav_h10 >= 30 else 0.85 if _sav_h10 <= 20 else 1.0

    # ── N6: Shadbala threshold gate for H10 lord ────────────────────────────
    # Shadbala rupa: >1.0 = strong (amplify), <0.5 = weak (dampen).
    _h10_sb = shadbala.get(h10_lord, 1.0) if h10_lord else 1.0
    _sb_mult = 1.15 if _h10_sb >= 1.0 else 0.80 if _h10_sb <= 0.5 else 1.0

    yg = _yogakaraka_bonus(field_affinity, lagna_sign, shadbala, planet_dignities) * 100.0
    hl = _h10_lord_strength_bonus(field_affinity, h10_lord, shadbala, planet_dignities) * 100.0 * _sav_mult * _sb_mult
    ht = _h10_lord_trikona_bonus(field_affinity, h10_lord, ph, planet_dignities) * 100.0 * _sb_mult
    dh = _dharma_karma_bonus(field_affinity, house_lords, ph) * 100.0
    ex = _exalted_planet_domain_bonus(field_affinity, planet_dignities, field_id or "", lagna_sign) * 100.0
    as10 = _aspect_h10_bonus(field_affinity, ph, planet_dignities, planets_d1) * 100.0
    yog = _yoga_bonus(field_id or "", yogas, house_lords, planet_dignities) * 100.0
    st = _stellium_bonus(field_id or "", ph) * 100.0
    # Gap-A fix: dusthana penalty also scaled ×0.75 for Parashara (applied after _PARA_PENALTY_SCALE is defined below).
    # Raw value computed here; scaling applied at deduction.
    dp = _dusthana_lord_penalty(field_affinity, lagna_sign, house_lords, lagna_lord, field_id or "", eff_strengths) * 100.0

    # ── Unified Bhava Bala for H10 (BPHS composite: occupant + aspect + own-lord) ──
    # Closes the classical gap where several *separate* bonuses (aspect_h10, stellium,
    # dharma_karma) approximated house strength piecemeal; this is the single composite
    # BPHS itself uses for career-house adjudication, so it credits charts where H10's
    # strength comes primarily from aspectual support rather than occupancy/lordship.
    _bhava_bala_composite = _h10_bhava_bala(field_affinity, h10_lord, ph, planet_dignities, shadbala, planets_d1)
    bb = _bhava_bala_composite * 100.0 * 0.16

    # 2026-07 astrologer's audit follow-up: Bhava Bala was previously H10-only.
    # Career signification classically extends to H2 (resources), H6
    # (service/employment/competition), and H11 (gains/income) as well --
    # this adds those three at a deliberately lower combined weight (0.08 vs
    # H10's 0.16) so they corroborate rather than compete with the primary
    # career-house signal.
    _bb_career, _bb_career_houses = _career_houses_bhava_bala_bonus(
        field_affinity, house_lords, ph, planet_dignities, shadbala, planets_d1
    )

    # Gap-7 fix: split into rubric_core (structural fundamentals) and rubric_support
    # (dignity-match / aspect / yoga / stellium extras that support but don't define the field).
    # Previously all 8 items went to rubric_core, making support section near-empty.
    for key, val in (
        ("yogakaraka", yg),
        ("h10_lord_strength", hl),
        ("h10_lord_trikona", ht),
        ("dharma_karma", dh),
        ("bhava_bala_h10", bb),
        ("bhava_bala_career_houses", _bb_career),
    ):
        score += val
        rubric_core += val
        if val > 0:
            components[key] = round(val, 2)
            if key == "bhava_bala_h10":
                trace.append(
                    f"Unified Bhava Bala for H10 ({_bhava_bala_composite:.2f} composite of "
                    f"occupant + aspect + own-lord strength) supports the career house."
                )
            if key == "bhava_bala_career_houses":
                trace.append(
                    "Secondary career-house Bhava Bala (H2 resources={:.2f}, H6 service/employment={:.2f}, "
                    "H11 gains={:.2f}) corroborates the primary H10 signal.".format(
                        _bb_career_houses.get(2, 0.0), _bb_career_houses.get(6, 0.0), _bb_career_houses.get(11, 0.0)
                    )
                )

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
    for planet in top_weighted_planets(field_affinity, 4):  # G16: was top-2
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
        vargottama_planets=getattr(payload_data, "vargottama_planets", []),
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

    # ── G7: Vargottama bonus ─────────────────────────────────────────────────
    _d9c_para = getattr(payload_data, "divisional_charts", {}).get("D9_navamsha", {}) or {}
    for _p, _pw in field_affinity.items():
        if _pw < 0.15: continue
        _p_sign = (planets_d1.get(_p) or {}).get("sign", "")
        if _p_sign and _is_vargottama(_p, _p_sign, _d9c_para):
            _varg_b = _pw * 5.0 * _d1_vitality_coefficient(_p, payload_data)
            score += _varg_b; rubric_support += _varg_b
            components[f"{_p.lower()}_vargottama"] = round(_varg_b, 2)
            trace.append(f"{_p} is vargottama (D1=D9 sign) — enhanced career strength.")

    # ── G8: Panchamahapurusha Yoga ───────────────────────────────────────────
    _PANCHA = {
        "Mars":    {"signs":{"Aries","Scorpio","Capricorn"}, "name":"Ruchaka"},
        "Mercury": {"signs":{"Gemini","Virgo"},              "name":"Bhadra"},
        "Jupiter": {"signs":{"Sagittarius","Pisces","Cancer"},"name":"Hamsa"},
        "Venus":   {"signs":{"Taurus","Libra","Pisces"},     "name":"Malavya"},
        "Saturn":  {"signs":{"Capricorn","Aquarius","Libra"}, "name":"Shasha"},
    }
    _KENDRA = {1, 4, 7, 10}
    for _pp, _pd in _PANCHA.items():
        _pp_sign  = (planets_d1.get(_pp) or {}).get("sign", "")
        _pp_house = ph.get(_pp, 0)
        if _pp_sign in _pd["signs"] and _pp_house in _KENDRA:
            _pp_w = field_affinity.get(_pp, 0.0)
            if _pp_w >= 0.10:
                _pp_b = _pp_w * 12.0 * _d1_vitality_coefficient(_pp, payload_data)
                score += _pp_b; rubric_core += _pp_b
                components[f"pancha_{_pd['name'].lower()}"] = round(_pp_b, 2)
                trace.append(f"{_pd['name']} yoga ({_pp} in {_pp_sign} H{_pp_house}).")

    # ── G9: Parivartana (house exchange) yoga ────────────────────────────────
    # Gap fix: previously only three H10-involving pairs were checked, so any
    # exchange not touching H10 (e.g. H2-H11, H4-H9) went entirely undetected.
    # Now every unique house pair is scanned generally; the H10-involving pairs
    # keep their full weight (career-relevant), everything else scores at a
    # reduced weight since it is not a direct career signal but still a
    # legitimate classical Rasi Parivartana strengthening both houses' affairs.
    import itertools as _itertools_pari
    _H10_PAIRS = {(1, 10), (5, 10), (9, 10)}
    for _ha, _hb in _itertools_pari.combinations(range(1, 13), 2):
        _la = house_lords.get(str(_ha), "")
        _lb = house_lords.get(str(_hb), "")
        if not _la or not _lb or _la == _lb:
            continue
        if ph.get(_la, 0) == _hb and ph.get(_lb, 0) == _ha:
            _aff_ab = field_affinity.get(_la, 0.0) + field_affinity.get(_lb, 0.0)
            _is_h10 = (_ha, _hb) in _H10_PAIRS or (_hb, _ha) in _H10_PAIRS
            _weight = 8.0 if _is_h10 else 4.0
            _threshold = 0.15 if _is_h10 else 0.20
            if _aff_ab >= _threshold:
                _pari_b = _aff_ab * _weight
                score += _pari_b; rubric_core += _pari_b
                components[f"parivartana_h{_ha}_h{_hb}"] = round(_pari_b, 2)
                trace.append(f"Parivartana yoga H{_ha}-H{_hb}: {_la}↔{_lb} exchange.")

    # ── G18: H9 lord strength in kendra/trikona ──────────────────────────────
    _h9_lord = house_lords.get("9", "")
    _h9_house = ph.get(_h9_lord, 0)
    if _h9_lord and _h9_house in {1, 4, 5, 7, 9, 10}:
        _h9_aff = field_affinity.get(_h9_lord, 0.0)
        if _h9_aff >= 0.10:
            _h9_dig_m = {"EXALTED":1.4,"OWN":1.2,"NEUTRAL":1.0,"DEBILITATED":0.5}.get(
                planet_dignities.get(_h9_lord, "NEUTRAL"), 1.0)
            _h9_b = _h9_aff * 8.0 * _h9_dig_m * _d1_vitality_coefficient(_h9_lord, payload_data)
            score += _h9_b; rubric_support += _h9_b
            components["h9_lord_strength"] = round(_h9_b, 2)
            trace.append(f"H9 Bhagya lord {_h9_lord} in H{_h9_house} supports career.")

    # ── G12: H10 from Chandra Lagna (Gap-14 fix: shared common helper) ────────
    _cl_h10_p = chandra_lagna_h10_lord(planets_d1)
    if _cl_h10_p:
        _cl_aff_p = field_affinity.get(_cl_h10_p, 0.0)
        if _cl_h10_p and _cl_aff_p >= 0.10:
            _cl_pb = _cl_aff_p * 7.0 * _d1_vitality_coefficient(_cl_h10_p, payload_data)
            score += _cl_pb; rubric_support += _cl_pb
            components["chandra_h10_parashara"] = round(_cl_pb, 2)
            trace.append(f"H10 from Chandra Lagna ({_cl_h10_p}) aligns with field.")

    # D10 Dashamsha cross-validation: D10 lagna lord in H10 + H10 occupants affirm career.
    d10_chart  = getattr(payload_data, "divisional_charts", {}).get("D10_dashamsha", {}) or {}
    d10_lagna  = d10_chart.get("Lagna", "") or ""
    from jyotish.constants import _SIGN_LORD
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

    # ── N8: D10-D1 lagna lord concordance yoga ──────────────────────────────
    # When the same planet rules both D1 and D10 lagna (same sign lagna in both charts),
    # career is doubly mandated — the soul and dashamsha architecture align perfectly.
    if d10_ll and d10_ll == lagna_lord:
        _dl_aff = field_affinity.get(d10_ll, 0.0)
        if _dl_aff >= 0.10:
            _dl_b = _dl_aff * 7.0 * _d1_vitality_coefficient(d10_ll, payload_data)
            score += _dl_b; rubric_validation += _dl_b
            components["d10_d1_concordance_yoga"] = round(_dl_b, 2)
            trace.append(f"D10-D1 lagna lord concordance ({d10_ll}): "
                         f"career doubly mandated by natal and dashamsha.")

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

    # ── T2-A: Lagna tatva career cluster ────────────────────────────────────
    # Fire lagna → action/pioneer fields; Earth → material/precision; Air → intellect/comm; Water → healing/arts.
    _TATVA_FIELD_KW = {
        "fire":  ["defence","military","surgery","engineering","sports","police","metallurgy","fire","pioneer","leadership"],
        "earth": ["medicine","pharmacy","agriculture","finance","banking","commerce","accounting","law","administration","management","architecture"],
        "air":   ["technology","software","research","media","communication","social","psychology","teaching","journalism","aviation","animation"],
        "water": ["nursing","healing","arts","music","film","creative","spiritual","hospitality","marine","oceanography","social work"],
    }
    _TATVA_SIGN = {
        "Aries":"fire","Leo":"fire","Sagittarius":"fire",
        "Taurus":"earth","Virgo":"earth","Capricorn":"earth",
        "Gemini":"air","Libra":"air","Aquarius":"air",
        "Cancer":"water","Scorpio":"water","Pisces":"water",
    }
    _lagna_tatva = _TATVA_SIGN.get(lagna_sign, "")
    if _lagna_tatva:
        _tatva_kws = _TATVA_FIELD_KW.get(_lagna_tatva, [])
        if any(_wm(kw, label) for kw in _tatva_kws):
            _tatva_b = 4.0 * _d1_vitality_coefficient(lagna_lord, payload_data)
            score += _tatva_b; rubric_support += _tatva_b
            components["lagna_tatva_cluster"] = round(_tatva_b, 2)
            trace.append(f"Lagna tatva ({_lagna_tatva}): {lagna_sign} ascendant resonates with {domain} field.")

    # ── T2-B: Amala, Vasumati, Nipuna yogas ─────────────────────────────────
    _BENEFICS = {"Jupiter", "Venus", "Moon", "Mercury"}
    _MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}
    # Amala Yoga: only benefics occupy H10 (no malefic in H10)
    _h10_occ = [pl for pl, h in ph.items() if h == 10]
    _h10_benefics = [p for p in _h10_occ if p in _BENEFICS]
    _h10_malefics = [p for p in _h10_occ if p in _MALEFICS]
    if _h10_benefics and not _h10_malefics:
        _amala_b = sum(field_affinity.get(p, 0.0) * _d1_vitality_coefficient(p, payload_data) for p in _h10_benefics) * 6.0
        _amala_b = min(_amala_b, 7.0)
        if _amala_b > 0:
            score += _amala_b; rubric_support += _amala_b
            components["amala_yoga"] = round(_amala_b, 2)
            trace.append(f"Amala Yoga: only benefics in H10 — pure career environment.")
    # Vasumati Yoga: benefics in H3/H6/H10/H11 from Moon
    _moon_house = ph.get("Moon", 0)
    if _moon_house:
        _vasumati_houses = {((_moon_house - 1 + offset) % 12) + 1 for offset in (2, 5, 9, 10)}
        _vas_benefics = [pl for pl, h in ph.items() if pl in _BENEFICS and h in _vasumati_houses]
        if len(_vas_benefics) >= 2:
            _vas_b = sum(field_affinity.get(p, 0.0) for p in _vas_benefics) * 3.5
            _vas_b = min(_vas_b, 5.0)
            if _vas_b > 0:
                score += _vas_b; rubric_support += _vas_b
                components["vasumati_yoga"] = round(_vas_b, 2)
                trace.append("Vasumati Yoga: benefics in H3/H6/H10/H11 from Moon — abundant career support.")
    # Nipuna Yoga: Mercury + Saturn conjunct or mutual aspect → precision/skill careers
    _merc_h = ph.get("Mercury", 0); _sat_h = ph.get("Saturn", 0)
    _NIP_FIELDS = ["law","medicine","accounting","engineering","research","finance","surgery","dentistry","pharmacy","architecture"]
    if _merc_h and _sat_h and any(_wm(kw, label) for kw in _NIP_FIELDS):
        _nip_active = (_merc_h == _sat_h) or abs(_merc_h - _sat_h) in (3, 6, 9, 12) or (abs(_merc_h - _sat_h) == 7)
        if _nip_active:
            _nip_b = (field_affinity.get("Mercury", 0.0) + field_affinity.get("Saturn", 0.0)) * 4.0
            _nip_b = min(_nip_b, 5.5)
            if _nip_b > 0:
                score += _nip_b; rubric_support += _nip_b
                components["nipuna_yoga"] = round(_nip_b, 2)
                trace.append("Nipuna Yoga (Mercury+Saturn): precision/skill career strongly indicated.")

    # ── T2-C: H6 lord as positive service-field signal ──────────────────────
    # Classical: H6 lord in kendra or exalted/own → excellence in service professions.
    _SERVICE_FIELDS = ["medicine","defence","military","law","police","nursing","surgery","forensics","social work","pharmacy"]
    _h6_lord = house_lords.get("6", "") or house_lords.get(6, "")
    if _h6_lord and any(_wm(kw, label) for kw in _SERVICE_FIELDS):
        _h6_house = ph.get(_h6_lord, 0)
        _h6_dig = planet_dignities.get(_h6_lord, "")
        _h6_in_kendra = _h6_house in (1, 4, 7, 10)
        # Gap 0.2 fix: planet_dignities values are UPPERCASE — lowercase check was dead.
        _h6_dignified = _h6_dig in ("EXALTED", "OWN", "MOOLATRIKONA")
        if _h6_in_kendra or _h6_dignified:
            _h6_b = field_affinity.get(_h6_lord, 0.1) * 7.0 * _d1_vitality_coefficient(_h6_lord, payload_data)
            _h6_b = min(_h6_b, 8.0)
            if _h6_b > 0:
                score += _h6_b; rubric_support += _h6_b
                components["h6_service_lord"] = round(_h6_b, 2)
                trace.append(f"H6 lord {_h6_lord} in kendra/dignified: service-field excellence yoga.")

    # ── T2-E: Rahu in H10 career yoga ───────────────────────────────────────
    # Rahu in H10 in friendly/exalted sign → strong modern/unconventional career drive.
    _RAHU_FRIENDLY = {"Gemini","Virgo","Libra","Sagittarius","Aquarius","Taurus"}
    _RAHU_EXALTED  = {"Gemini", "Taurus"}
    _MODERN_FIELDS = ["technology","software","ai","media","digital","international","aviation","animation",
                      "film","foreign","research","commerce","entrepreneurship","engineering","architecture"]
    _rahu_house = ph.get("Rahu", 0)
    _rahu_sign_info = (planets_d1.get("Rahu") or {}).get("sign", "")
    if _rahu_house == 10 and any(_wm(kw, label) for kw in _MODERN_FIELDS):
        _rahu_in_friendly = _rahu_sign_info in _RAHU_FRIENDLY
        _rahu_in_exalted  = _rahu_sign_info in _RAHU_EXALTED
        if _rahu_in_friendly or _rahu_in_exalted:
            _rahu_mult = 1.3 if _rahu_in_exalted else 1.0
            _rahu_b = field_affinity.get("Rahu", 0.1) * 8.0 * _rahu_mult
            _rahu_b = min(_rahu_b, 9.0)
            if _rahu_b > 0:
                score += _rahu_b; rubric_support += _rahu_b
                components["rahu_h10_yoga"] = round(_rahu_b, 2)
                trace.append(f"Rahu in H10 ({_rahu_sign_info}): modern/unconventional career yoga active.")

    # ── T2-D: D1+D10 double-dignity compound ────────────────────────────────
    # H10 lord exalted or own in BOTH D1 and D10 → exceptional career mandate.
    _d1_h10_dig  = planet_dignities.get(h10_lord, "")
    _d10_planets = getattr(payload_data, "d10_planet_dignities", {}) or {}
    _d10_h10_dig = _d10_planets.get(h10_lord, "")
    # Gap 0.2 fix: dignity strings are UPPERCASE — lowercase set made T2-D dead code.
    # Doc fix (audit): compute_dignity() DOES emit MOOLATRIKONA when called with a
    # degree (see astro.py) -- D1's planet_dignities is built that way in
    # engine_io.py, so this branch is live, not merely future-proofing.
    _DIG_STRONG  = {"EXALTED", "OWN", "MOOLATRIKONA"}
    if h10_lord and _d1_h10_dig in _DIG_STRONG and _d10_h10_dig in _DIG_STRONG:
        _dd_aff = field_affinity.get(h10_lord, 0.0)
        if _dd_aff >= 0.10:
            _dd_b = _dd_aff * 10.0 * _d1_vitality_coefficient(h10_lord, payload_data)
            _dd_b = min(_dd_b, 12.0)
            score += _dd_b; rubric_validation += _dd_b
            components["d1_d10_double_dignity"] = round(_dd_b, 2)
            trace.append(f"D1+D10 double-dignity: {h10_lord} is {_d1_h10_dig} in D1 and {_d10_h10_dig} in D10 — exceptional career mandate.")

    # ── Systematic karaka-domain bonus (cross-cutting gap fix) ────────────────
    # Same shared BPHS/Jataka Parijata karakatwa fallback used in knrao.py and
    # jaimini.py, so Parashara's yoga-based scoring also generalizes to fields
    # outside its hand-curated keyword blocks.
    _karaka_dom_b_p, _karaka_dom_hits_p = _karakatwa_domain_bonus(
        domain, field_affinity, planets_d1, ph, payload_data, scale=5.0, cap=10.0,
    )
    if _karaka_dom_b_p > 0:
        score += _karaka_dom_b_p; rubric_support += _karaka_dom_b_p
        components["karaka_domain_bonus"] = round(_karaka_dom_b_p, 2)
        trace.append(
            f"Karakatwa domain match ({domain}): {', '.join(_karaka_dom_hits_p)} carry classical "
            "significator authority for this domain (systematic karaka-to-field mapping)."
        )

    # ── Ontology fix: house-signification-first primitive ────────────────────
    # Parashara's own system is already house-centric (h10_lord_strength,
    # h10_lord_trikona, Bhava Bala), but the domain-specific sub-houses
    # (H6/H8/H12 for medicine, H6/H7/H9 for law, etc.) were previously only
    # reachable through field-*label* keyword gates (T2-C service fields,
    # T2-E modern fields). This applies to every field in a matching domain.
    _house_dom_b_p, _house_dom_hits_p = _house_signification_bonus(
        domain, field_affinity, house_lords, ph, planets_d1, payload_data, scale=5.0, cap=10.0,
    )
    if _house_dom_b_p > 0:
        score += _house_dom_b_p; rubric_support += _house_dom_b_p
        components["house_signification_bonus"] = round(_house_dom_b_p, 2)
        trace.append(
            f"House signification ({domain}): {', '.join(_house_dom_hits_p)} lord(s) "
            "carry classical house authority for this field."
        )

    # ── Vimshopaka Bala: unified divisional-strength coefficient ─────────────
    # Applies the shared reduced Vimshopaka Bala (D1/D3/D9/D10/D20/D24/D30
    # dignity) to Parashara's top field-weighted planets, reconciling the
    # multiple separate per-varga dignity checks above (D10, D9, D24) into one
    # consistent unified-strength signal shared across all field methods.
    _vim_planets_p = top_weighted_planets(field_affinity, 2)
    if _vim_planets_p:
        _vim_avg_p = sum(_vimsopaka_bala_coefficient(p, payload_data) for p in _vim_planets_p) / len(_vim_planets_p)
        _vim_adj_p = (_vim_avg_p - 1.0) * 15.0
        if abs(_vim_adj_p) > 0.05:
            score += _vim_adj_p
            rubric_validation += _vim_adj_p
            components["vimsopaka_bala"] = round(_vim_adj_p, 2)
            trace.append(
                f"Vimshopaka Bala for {', '.join(_vim_planets_p)}: avg coefficient {_vim_avg_p:.2f} "
                f"-- unified divisional strength {'supports' if _vim_adj_p > 0 else 'weakens'} this field."
            )

    rubric = build_score_rubric(
        "parashara",
        [
            rubric_section(
                "core",
                rubric_core,
                40.0,
                note="Yogakaraka, H10 lord, dharma-karma, and unified Bhava Bala fundamentals (H10 primary, H2/H6/H11 secondary).",
                items=["yogakaraka", "h10_lord_strength", "h10_lord_trikona", "dharma_karma", "bhava_bala_h10", "bhava_bala_career_houses"],
            ),
            rubric_section(
                "support",
                rubric_support,
                25.0,
                note="Dignity-matched field support, aspects, yogas, stellium, karakatwa domain, "
                     "and house-signification-first bonus.",
                items=["exalted_domain", "aspect_h10", "yoga", "stellium", "_exalted_bonus",
                       "life_science_cluster", "space_aerospace_cluster", "karaka_domain_bonus",
                       "house_signification_bonus"],
            ),
            rubric_section(
                "validation",
                rubric_validation,
                20.0,
                note="D10, D9, and D24 confirmation signals, Vimshopaka Bala.",
                items=["d10_validation", "d9_h10", "d24_bonus", "d10_ll_bonus", "vimsopaka_bala"],
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

    # Gap-1 (audit 2026-07) fix: cap unified with bundle via METHOD_SCORE_CAPS["parashara"] = 55.0.
    # Gap-3/9 fix: pass raw signed `score` (not pre-clamped) so contraindicated
    # charts (net penalties > positives) are distinguishable from neutral ones;
    # method_result() still clamps internally for the "score" field.
    return method_result("parashara", score, trace, components, rubric=rubric,
                         normalization_cap=METHOD_SCORE_CAPS["parashara"])
