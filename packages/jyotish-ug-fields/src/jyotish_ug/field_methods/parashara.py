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
    bhavat_bhavam,
    build_gate_text,
    build_score_rubric,
    chandra_lagna_h10_lord,
    clamp_score,
    detect_career_yogas,
    detect_vidya_yogas,
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
    eff_strengths = (getattr(payload_data, "eff_strengths_tier1", None) or getattr(payload_data, "eff_strengths", {}) or {})
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

    # 2026-08-17 audit fix: h10_lord's *dignity* (planet_dignities[h10_lord])
    # is the underlying classical fact fed into THREE separate components in
    # this file -- h10_lord_strength (hl, below), h10_lord_trikona (ht,
    # below), and d1_d10_double_dignity (dd_b, further down, which re-checks
    # h10_lord's D1 dignity alongside its D10 dignity). The previous rubric
    # cap comment did not disclose this triple-count. hl is the first/
    # primary appearance (it is also gated by shadbala/SAV, the most
    # structurally distinct check of the three) and keeps full credit; ht
    # and the D1 half of dd_b are the same dignity fact re-scored under a
    # different gate (trikona placement / D10 corroboration respectively)
    # and are now correlation-discounted rather than deleted -- each is
    # still a distinct classical technique worth partial credit, same
    # reasoning as common.py's correlation_discount_factor() for the
    # cross-method SIGNAL_REGISTRY.
    _H10_DIGNITY_TRIKONA_DISCOUNT = 0.6   # ht: same dignity fact, different (trikona) gate
    _H10_DIGNITY_D1D10_DISCOUNT = 0.75    # dd_b: half-new fact (D10 dignity is independent)

    yg = _yogakaraka_bonus(field_affinity, lagna_sign, shadbala, planet_dignities) * 100.0
    hl = _h10_lord_strength_bonus(field_affinity, h10_lord, shadbala, planet_dignities) * 100.0 * _sav_mult * _sb_mult
    ht = _h10_lord_trikona_bonus(field_affinity, h10_lord, ph, planet_dignities) * 100.0 * _sb_mult * _H10_DIGNITY_TRIKONA_DISCOUNT
    dh = _dharma_karma_bonus(field_affinity, house_lords, ph) * 100.0
    ex = _exalted_planet_domain_bonus(field_affinity, planet_dignities, field_id or "", lagna_sign) * 100.0
    as10 = _aspect_h10_bonus(field_affinity, ph, planet_dignities, planets_d1) * 100.0
    # FIX (2026-08-20): this call previously passed a 5th positional arg,
    # field_affinity, but jyotish/boosts.py::_yoga_bonus only ever accepted
    # (label, detected_yogas, house_lords=None, planet_dignities=None) and
    # never referenced a 5th parameter anywhere in its body -- a stray
    # leftover argument (probably from a copy/paste of a call like
    # _yogakaraka_bonus's on line 99, which does take field_affinity) that
    # raised TypeError on every call. Dropped to match the real signature;
    # no behavior change since the argument was never used.
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
    # 2026-08-17 audit fix: this generic top-4 exalted/own bonus and the
    # vidya_karaka_strength bonus further below both score dignity for
    # Mercury/Jupiter/Venus when one of them is both a top-weighted field
    # planet AND a vidya karaka in strong dignity -- same underlying "this
    # planet is exalted/own" fact rewarded twice. Track which planets get
    # full credit here so the vidya-karaka loop below can discount the
    # overlap instead of double-paying it.
    _exalted_bonus_planets: set = set()
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
                _exalted_bonus_planets.add(planet)

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

    # ── Phase-3 remediation (2026-08 gap-audit): H4 lord + vidya-karaka support ──
    # Classical vidya houses were previously absent from Parashara's model here
    # (only H9/Bhagya was checked above). H4 = early/formal education (BPHS);
    # added with the same shape/weight as the H9 block for consistency. Also
    # scores Mercury/Jupiter/Venus (vidya karakas) directly, since they were
    # previously treated identically to any other planet via field_affinity
    # alone with no karaka-specific recognition.
    _h4_lord = house_lords.get("4", "")
    _h4_house = ph.get(_h4_lord, 0)
    if _h4_lord and _h4_house in {1, 4, 5, 7, 9, 10}:
        _h4_aff = field_affinity.get(_h4_lord, 0.0)
        if _h4_aff >= 0.10:
            _h4_dig_m = {"EXALTED": 1.4, "OWN": 1.2, "NEUTRAL": 1.0, "DEBILITATED": 0.5}.get(
                planet_dignities.get(_h4_lord, "NEUTRAL"), 1.0)
            _h4_b = _h4_aff * 8.0 * _h4_dig_m * _d1_vitality_coefficient(_h4_lord, payload_data)
            score += _h4_b; rubric_support += _h4_b
            components["h4_lord_strength"] = round(_h4_b, 2)
            trace.append(f"H4 (vidya/foundation) lord {_h4_lord} in H{_h4_house} supports learning.")

    # 2026-08-17 audit fix: _VK_EXALTED_DISCOUNT accounts for the overlap with
    # the generic top-4 exalted/own bonus above -- when a vidya karaka
    # (Mercury/Jupiter/Venus) already collected an "_exalted_bonus" component
    # up there, its EXALTED/OWN dignity here is the same fact re-scored, not
    # new corroboration. Discounted (not skipped) since the vidya-karaka
    # multiplier table itself is a distinct classical technique (a wider
    # dignity gradient than the binary EXALTED/OWN check above).
    _VK_EXALTED_DISCOUNT = 0.5
    _vidya_karaka_dig_m = {"EXALTED": 1.4, "OWN": 1.2, "MOOLATRIKONA": 1.25, "NEUTRAL": 1.0,
                            "FRIEND": 1.1, "ENEMY": 0.7, "DEBILITATED": 0.5}
    _vk_total = 0.0
    for _vk in ("Mercury", "Jupiter", "Venus"):
        _vk_aff = field_affinity.get(_vk, 0.0)
        if _vk_aff < 0.08:
            continue
        _vk_dig = str(planet_dignities.get(_vk, "NEUTRAL")).upper()
        _vk_m = _vidya_karaka_dig_m.get(_vk_dig, 1.0)
        _vk_b = _vk_aff * 6.0 * _vk_m * _d1_vitality_coefficient(_vk, payload_data)
        if _vk in _exalted_bonus_planets:
            _vk_b *= _VK_EXALTED_DISCOUNT
            trace.append(f"Vidya karaka {_vk} dignity={_vk_dig} supports field "
                         "(correlation-discounted: exalted/own bonus already scored above).")
        else:
            trace.append(f"Vidya karaka {_vk} dignity={_vk_dig} supports field.")
        _vk_total += _vk_b
    if _vk_total:
        score += _vk_total; rubric_support += _vk_total
        components["vidya_karaka_strength"] = round(_vk_total, 2)

    # ── Phase-4 remediation: Saraswati / Budh-Aditya yoga detection ─────────
    _vidya_yogas = detect_vidya_yogas(planets_d1, ph, planet_dignities)
    _yoga_bonus_total = 0.0
    if _vidya_yogas["saraswati_yoga"]:
        _yoga_bonus_total += 9.0
        components["saraswati_yoga"] = 9.0
    if _vidya_yogas["budh_aditya_yoga"]:
        _yoga_bonus_total += 5.0
        components["budh_aditya_yoga"] = 5.0
    if _yoga_bonus_total:
        score += _yoga_bonus_total; rubric_support += _yoga_bonus_total
        trace.extend(_vidya_yogas["notes"])

    # ── Stage 2 (Astro-OS v3 gap-audit implementation plan, 2026-08): Pattern
    # Ontology Layer -- generalizes the two hard-coded yogas above into a
    # data-driven table covering guru-mangal/shukra-budha/shani-mangal/
    # chandra-mangal/guru-shukra. See detect_career_yogas() docstring in
    # common.py for the field-relevance gating rationale (a yoga only
    # contributes when the field's own affinity table supports one of its
    # constituent planets, not a flat "combination exists" bonus).
    _career_yogas = detect_career_yogas(ph, field_affinity)
    if _career_yogas["total_bonus"]:
        score += _career_yogas["total_bonus"]; rubric_support += _career_yogas["total_bonus"]
        for _yn, _yd in _career_yogas["active"].items():
            if _yd["relevant"]:
                components[_yn] = _yd["bonus"]
        trace.extend(_career_yogas["notes"])

    # ── G12: H10 from Chandra Lagna (Gap-14 fix: shared common helper) ────────
    _cl_h10_p = chandra_lagna_h10_lord(planets_d1)
    if _cl_h10_p:
        _cl_aff_p = field_affinity.get(_cl_h10_p, 0.0)
        if _cl_h10_p and _cl_aff_p >= 0.10:
            _cl_pb = _cl_aff_p * 7.0 * _d1_vitality_coefficient(_cl_h10_p, payload_data)
            score += _cl_pb; rubric_support += _cl_pb
            components["chandra_h10_parashara"] = round(_cl_pb, 2)
            trace.append(f"H10 from Chandra Lagna ({_cl_h10_p}) aligns with field.")

    # §6 remediation (2026-08): D10 (Dashamsha) evidence used below is ALSO
    # independently scored, in full, by dashamsha.py as its own dedicated
    # voting method in the blend (METHOD_WEIGHTS["dashamsha"]). Letting
    # Parashara additionally count the same D10 lagna-lord/H10-occupant
    # facts at full strength effectively triple-votes the same D10 evidence
    # (once here as "D10 validation", once here as "D10-D1 concordance",
    # once again as the whole dashamsha.py method) with no corresponding
    # increase in independent testimony. Rather than deleting these
    # classically-real cross-validation yogas (they ARE meaningful --
    # Parashara doctrine does treat D1/D10 concordance as significant), each
    # of the three D10-derived bonus blocks below is discounted by this
    # factor so their combined contribution to Parashara's own score stays
    # a modest corroboration signal rather than a second full D10 vote.
    _D10_INTERNAL_DAMPENING = 0.5
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
    d10_bonus = min(d10_bonus, 10.0) * _D10_INTERNAL_DAMPENING
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
            _dl_b = _dl_aff * 7.0 * _d1_vitality_coefficient(d10_ll, payload_data) * _D10_INTERNAL_DAMPENING
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

    d10_ll_dig_bonus = _d10_lagna_lord_bonus(field_affinity, d10_chart, d10_lagna) * 100.0 * _D10_INTERNAL_DAMPENING
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
    # 2026-08-17 audit fix: benefic/malefic status here was previously a
    # UNIVERSAL hardcoded table (Jupiter/Venus/Mercury/Moon always benefic;
    # Sun/Mars/Saturn/Rahu/Ketu always malefic). Classical BPHS functional
    # benefic/malefic status is ASCENDANT-RELATIVE -- it depends on which
    # houses a planet lords for this specific lagna (e.g. Saturn is a
    # Yogakaraka, hence functionally benefic, for Taurus/Libra ascendants;
    # Jupiter is a functional malefic as a trik-lord for Gemini/Virgo
    # ascendants). Scoped to only this Amala/Vasumati block (the only place
    # _BENEFICS/_MALEFICS were used in this file) rather than threaded
    # through the rest of the module, so the fix is local and independently
    # verifiable. Standard house-lordship rule used:
    #   - lords BOTH a kendra (1/4/7/10) AND a trikona (1/5/9) -> Yogakaraka,
    #     strongly benefic (e.g. Mars for Cancer/Leo lagna).
    #   - lords a kendra/trikona and NO dusthana (6/8/12) -> benefic.
    #   - lords a dusthana and NO kendra/trikona -> malefic.
    #   - dual lordship mixing dusthana with kendra/trikona (common, since
    #     every planet but Sun/Moon rules two signs), or lording only
    #     upachaya (3/6/10/11 minus kendra/dusthana already counted) ->
    #     left NEUTRAL here (counted as neither benefic nor malefic) rather
    #     than guessed, since the classical resolution of mixed lordship
    #     depends on additional factors (which lordship is "stronger",
    #     natural benefic/malefic status of the planet itself) outside this
    #     scoped fix's verification budget -- this only narrows the Amala/
    #     Vasumati count, it never mis-classifies a planet in the wrong
    #     direction.
    #   - Rahu/Ketu hold no sign lordship; kept as always-malefic per
    #     classical convention (unaffected by this fix).
    def _functional_benefic_malefic_sets(_house_lords: Dict[str, str]):
        _planet_houses: Dict[str, set] = {}
        for _h_key, _lord in _house_lords.items():
            if not _lord:
                continue
            try:
                _h_num = int(_h_key)
            except (TypeError, ValueError):
                continue
            _planet_houses.setdefault(_lord, set()).add(_h_num)
        _benefics_f: set = set()
        _malefics_f: set = set()
        for _pl, _houses in _planet_houses.items():
            _kendra_h = _houses & {1, 4, 7, 10}
            _trikona_h = _houses & {1, 5, 9}
            _dusthana_h = _houses & {6, 8, 12}
            if _kendra_h and _trikona_h:
                _benefics_f.add(_pl)  # Yogakaraka
            elif _dusthana_h and not (_kendra_h or _trikona_h):
                _malefics_f.add(_pl)
            elif (_kendra_h or _trikona_h) and not _dusthana_h:
                _benefics_f.add(_pl)
            # else: mixed dusthana+kendra/trikona, or upachaya-only -> neutral, added to neither set
        _malefics_f.add("Rahu"); _malefics_f.add("Ketu")  # nodes: no sign lordship, classical convention
        return _benefics_f, _malefics_f

    _BENEFICS, _MALEFICS = _functional_benefic_malefic_sets(house_lords)
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

    # ── T2-F: Graha Yuddha (planetary war) detection (2026-08-17 gap-fix) ────
    # BPHS: two of {Mars, Mercury, Jupiter, Venus, Saturn} (never the
    # luminaries or the nodes) occupying the same sign within ~1 degree of
    # longitude are in "planetary war" -- one is considered defeated, the
    # other victorious. This file had no graha yuddha detection at all.
    # Tie-break rule used here: since only within-sign degree (not celestial
    # latitude) is available on payload_data.planets_d1, we follow the common
    # software convention of treating the planet with the LOWER degree
    # (closer to 0 deg, "behind" in the zodiac) as defeated -- classical
    # texts that use latitude are not reproducible from this data, so this is
    # documented as the deliberate, data-driven tie-break rather than left
    # silently ambiguous. Magnitude kept modest and within this file's
    # existing per-component range (~4-12 pts): defeated planet loses a small
    # penalty scaled by its own field affinity; the victor gets a small
    # bonus, not a swing larger than e.g. the exalted_domain/h6_service_lord
    # components above.
    _YUDDHA_PLANETS = ("Mars", "Mercury", "Jupiter", "Venus", "Saturn")
    _YUDDHA_ORB_DEG = 1.0
    for _ya, _yb in _itertools_pari.combinations(_YUDDHA_PLANETS, 2):
        _ya_info = planets_d1.get(_ya) or {}
        _yb_info = planets_d1.get(_yb) or {}
        _ya_sign = _ya_info.get("sign", "")
        _yb_sign = _yb_info.get("sign", "")
        if not _ya_sign or _ya_sign != _yb_sign:
            continue
        try:
            _ya_deg = float(_ya_info.get("degree"))
            _yb_deg = float(_yb_info.get("degree"))
        except (TypeError, ValueError):
            continue
        if abs(_ya_deg - _yb_deg) > _YUDDHA_ORB_DEG:
            continue
        _loser, _winner = (_ya, _yb) if _ya_deg < _yb_deg else (_yb, _ya)
        _loser_aff = field_affinity.get(_loser, 0.0)
        _winner_aff = field_affinity.get(_winner, 0.0)
        _yuddha_penalty = min(_loser_aff * 6.0 * _d1_vitality_coefficient(_loser, payload_data), 5.0)
        if _yuddha_penalty > 0:
            score -= _yuddha_penalty
            rubric_penalty -= _yuddha_penalty
            components[f"graha_yuddha_{_loser.lower()}_defeated"] = round(-_yuddha_penalty, 2)
        _yuddha_bonus = min(_winner_aff * 2.0 * _d1_vitality_coefficient(_winner, payload_data), 2.0)
        if _yuddha_bonus > 0:
            score += _yuddha_bonus
            rubric_support += _yuddha_bonus
            components[f"graha_yuddha_{_winner.lower()}_victor"] = round(_yuddha_bonus, 2)
        trace.append(
            f"Graha Yuddha: {_ya} and {_yb} conjunct in {_ya_sign} within "
            f"{abs(_ya_deg - _yb_deg):.2f} deg — {_loser} (lower degree) treated as "
            f"defeated, {_winner} as victor."
        )

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
            # 2026-08-17 audit fix: the D1 half of this compound (_d1_h10_dig) is
            # the same h10_lord dignity fact already scored in full via hl above
            # and at a discount via ht -- only the D10 half is a genuinely new
            # signal. Discounted (not deleted) per _H10_DIGNITY_D1D10_DISCOUNT.
            _dd_b *= _H10_DIGNITY_D1D10_DISCOUNT
            score += _dd_b; rubric_validation += _dd_b
            components["d1_d10_double_dignity"] = round(_dd_b, 2)
            trace.append(f"D1+D10 double-dignity: {h10_lord} is {_d1_h10_dig} in D1 and {_d10_h10_dig} in D10 — exceptional career mandate "
                         "(correlation-discounted: D1 dignity already scored above).")

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

    # ── gap fix 2026-08-18 (D): Dig Bala corroboration for H10 lord + career karakas ──
    # jyotish/shadbala.py::compute_dig_bala already computes classical directional
    # strength (BPHS: Sun/Mars ideal at H10, Moon/Venus at H4, Jupiter/Mercury at H1,
    # Saturn at H7), and jyotish/engine_io.py exposes the full six-fold breakdown as
    # payload.shadbala_computed (additive alongside the older single-number
    # `payload.shadbala` this file already reads above for hl/ht/_sb_mult -- that
    # older field is the pre-2026-07 upstream `shadbala_virupas` ingestion and does
    # NOT include dig_bala, so this is new signal, not double-counting). Small, bounded
    # (max +/-4, matching competency_ontology.py's bounded-adjustment convention) additive
    # corroboration: if the H10 lord and the two fixed classical career karakas
    # (Sun = soul/authority/govt, Saturn = karma/labor/longevity of career, Mercury =
    # intellect/trade/communication) sit near their classical directional-strength
    # cusp, that is small extra corroborating evidence for career delivery -- it does
    # not replace or override h10_lord_strength/karaka_domain_bonus above.
    _dig_bala_planets = {payload_data.h10_lord} if getattr(payload_data, "h10_lord", "") else set()
    _dig_bala_planets |= {"Sun", "Saturn", "Mercury"}
    _shadbala_computed = getattr(payload_data, "shadbala_computed", {}) or {}
    _sb_by_planet = (_shadbala_computed or {}).get("planets", {}) or {}
    _dig_vals = []
    for _dp in _dig_bala_planets:
        _dp_detail = _sb_by_planet.get(_dp)
        if isinstance(_dp_detail, dict) and "dig_bala" in _dp_detail:
            _dig_vals.append(float(_dp_detail["dig_bala"]))
    if _dig_vals:
        _dig_avg = sum(_dig_vals) / len(_dig_vals)
        # 0-60 shashtiamsa scale; 30 = neutral midpoint. Map deviation from midpoint
        # to a small +/-4 bonus, same cap style as competency_ontology.py's bounded gaps.
        _dig_b = max(-4.0, min(4.0, (_dig_avg - 30.0) / 30.0 * 4.0))
        if abs(_dig_b) > 0.05:
            score += _dig_b
            rubric_support += _dig_b
            components["dig_bala_corroboration"] = round(_dig_b, 2)
            trace.append(
                f"Dig Bala corroboration (H10 lord + Sun/Saturn/Mercury): avg "
                f"{_dig_avg:.1f}/60 shashtiamsas -- "
                f"{'supports' if _dig_b > 0 else 'weakens'} career-house delivery "
                "(small bounded classical directional-strength signal)."
            )

    # ── gap fix 2026-08-18 (G): minimal retrograde (vakri) extension for H10 lord ──
    # Classical basis (Phaladeepika/Saravali): a retrograde planet's influence is
    # not confined to its own placement -- it also carries some of the significance
    # of the house it is regressing INTO (the previous house from its D1 placement,
    # same house-direction convention KP already uses in kp.py's retrograde
    # expansion above, kept consistent across methods per this session's remit).
    # Minimal, single-fact, bounded (+/-2) nudge: if the H10 lord is retrograde AND
    # occupies (or regresses into) another career-relevant house (2/6/10/11), that
    # is small corroborating evidence; this does not touch dignity scoring elsewhere.
    _retro_set_p = getattr(payload_data, "retrograde_planets", set()) or set()
    if h10_lord and h10_lord in _retro_set_p:
        _h10l_house = ph.get(h10_lord, 0)
        if _h10l_house:
            _h10l_prev_house = ((_h10l_house - 2) % 12) + 1
            if _h10l_prev_house in (2, 6, 10, 11):
                _retro_b = 2.0
                score += _retro_b
                rubric_support += _retro_b
                components["retrograde_h10_lord_extension"] = round(_retro_b, 2)
                trace.append(
                    f"Retrograde (vakri) H10 lord {h10_lord}: also carries significance of "
                    f"H{_h10l_prev_house} (the house it regresses into), a career-relevant house -- "
                    "small corroborating evidence (classical vakri house-extension)."
                )

    # ── gap fix 2026-08-18 (F): Bhavat Bhavam corroboration for career houses ──
    # common.py::bhavat_bhavam(N) = Nth house counted again from itself (BPHS/
    # Phaladeepika chained-house technique; formula verified against the
    # classical 7th-from-7th=1st worked example -- see that function's
    # docstring). For each career-relevant house (2nd wealth/resources, 6th
    # service/employment, 10th career/status, 11th gains/income), the
    # Bhavat-Bhavam house's LORD's dignity is small, bounded, corroborating
    # evidence -- NOT a replacement for the primary house-lord analysis
    # already scored above (h10_lord_strength, dharma_karma, bhava_bala_*).
    # Capped at +/-4 total, same bounded-adjustment convention as
    # competency_ontology.py's family-cohesion/yoga-alignment nudges.
    _BB_DIG_SCORE = {"EXALTED": 2.0, "OWN": 1.5, "MOOLATRIKONA": 1.5, "FRIEND": 0.5,
                      "NEUTRAL": 0.0, "ENEMY": -0.5, "DEBILITATED": -2.0}
    _bb_total = 0.0
    _bb_notes = []
    for _career_house in (2, 6, 10, 11):
        _bb_house = bhavat_bhavam(_career_house)
        _bb_lord = house_lords.get(str(_bb_house), "")
        if not _bb_lord:
            continue
        _bb_dig = str(planet_dignities.get(_bb_lord, "NEUTRAL")).upper()
        _bb_pts = _BB_DIG_SCORE.get(_bb_dig, 0.0)
        if _bb_pts:
            _bb_total += _bb_pts
            _bb_notes.append(f"H{_career_house}->Bhavat-Bhavam H{_bb_house} lord {_bb_lord} ({_bb_dig})")
    if _bb_total:
        _bb_b = max(-4.0, min(4.0, _bb_total))
        score += _bb_b
        rubric_support += _bb_b
        components["bhavat_bhavam_corroboration"] = round(_bb_b, 2)
        trace.append(
            "Bhavat Bhavam (house-from-house) corroboration for 2nd/6th/10th/11th: "
            + "; ".join(_bb_notes) + f" -- net {'supports' if _bb_b > 0 else 'weakens'} career delivery."
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
                     "house-signification-first bonus, and Graha Yuddha victor bonus.",
                items=["exalted_domain", "aspect_h10", "yoga", "stellium", "_exalted_bonus",
                       "life_science_cluster", "space_aerospace_cluster", "karaka_domain_bonus",
                       "house_signification_bonus", "graha_yuddha_victor", "dig_bala_corroboration",
                       "bhavat_bhavam_corroboration", "retrograde_h10_lord_extension"],
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
                note="Dusthana, combustion, vitality friction, and Graha Yuddha defeat penalty.",
                items=["dusthana_penalty", "combustion_penalty", "_vitality_penalty", "graha_yuddha_defeated"],
            ),
        ],
    )

    # Gap-1 (audit 2026-07) fix: cap unified with bundle via METHOD_SCORE_CAPS["parashara"] = 55.0.
    # Gap-3/9 fix: pass raw signed `score` (not pre-clamped) so contraindicated
    # charts (net penalties > positives) are distinguishable from neutral ones;
    # method_result() still clamps internally for the "score" field.
    return method_result("parashara", score, trace, components, rubric=rubric,
                         normalization_cap=METHOD_SCORE_CAPS["parashara"])
