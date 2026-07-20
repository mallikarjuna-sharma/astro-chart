"""Jaimini field-determination module."""
from __future__ import annotations

from typing import Any, Dict, List

from jyotish.astro import (
    _compute_jaimini_argala,
    _compute_jaimini_virodhargala,
    _detect_jaimini_raj_yogas,
    _compute_bvb_7_karakas,
)
from jyotish.astro import _get_active_chara_dasha_sign
from jyotish.constants import _SIGN_NUM, _SIGN_LORD
from jyotish.boosts import (
    _karakamsha_bonus,
    _brahma_lord_bonus,
    _maheshwara_lord_bonus,
    _dharma_karma_bonus,
    _life_science_cluster_bonus,
    _space_aerospace_cluster_bonus,
    _planet_combustion_penalty,
    _dusthana_lord_penalty,
    _d1_vitality_coefficient,
    _karakatwa_domain_bonus,
    _house_signification_bonus,
    _vimsopaka_bala_coefficient,
    DASHA_KEYWORDS,
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
    """Jaimini rasi-drishti — pure Parashari-Jaimini school (Jaimini Sutras).

    Classical rules (Sutras 1.1.28-31):
      - Movable signs aspect Fixed signs (not adjacent Fixed)
      - Fixed signs aspect Movable signs (not adjacent Movable)
      - Dual signs aspect all other Dual signs (no adjacency exclusion)

    L3 fix: The dual-to-dual adjacency exclusion was a KNRao convention applied in
    jaimini.py, making it identical to knrao.py's drishti rule.  This reduced method
    diversity and inflated convergence scores.  Pure Jaimini (Sutras) says all dual
    signs aspect each other — the adjacency exclusion is removed here.
    The adjacency exclusion is still applied for movable↔fixed aspects below,
    because adjacent movable-fixed pairs (e.g. Aries-Taurus) are NOT in aspect
    per any Jaimini school.
    """
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

    if planet_sign in movable and target_sign in fixed:
        return target_sign not in adjacent
    if planet_sign in fixed and target_sign in movable:
        return target_sign not in adjacent
    if planet_sign in dual and target_sign in dual:
        # L3 fix: pure Jaimini — all dual signs aspect all other dual signs,
        # no adjacency exclusion (that is the KNRao convention, not in Sutras).
        return True
    return False


_MOVABLE_SIGNS = {"Aries", "Cancer", "Libra", "Capricorn"}
_FIXED_SIGNS = {"Taurus", "Leo", "Scorpio", "Aquarius"}
_DUAL_SIGNS = {"Gemini", "Virgo", "Sagittarius", "Pisces"}


def _jaimini_kendradhipati_cancellation(house_lords: Dict[str, str], lagna_sign: str) -> tuple[str, float, str]:
    """Jaimini-school Kendradhipati dosha cancellation.

    Classical Parashara notes that a planet ruling only a kendra (4/7/10, not
    counting lagna) without also ruling a trikona (5/9) picks up a mild dosha
    despite being functionally strong. Jaimini commentary (via later exponents
    such as Sanjay Rath, building on the Jaimini Sutras' treatment of movable /
    fixed / dual rashis) holds that whether this dosha is cancelled depends on
    the *nature* of the lagna:
      - Movable lagna: dosha is fully cancelled for a kendra-trikona dual lord.
      - Fixed lagna:   dosha is only partially cancelled.
      - Dual lagna:    dosha is NOT cancelled -- it stands at full strength.

    Returns (planet, cancellation_factor 0..1, lagna_type) for the first
    kendra+trikona dual-lord found, or ("", 0.0, "") if none exists.
    """
    if not lagna_sign:
        return "", 0.0, ""
    kendra_houses = {"4", "7", "10"}
    trikona_houses = {"5", "9"}
    kendra_lords = {house_lords.get(h, "") for h in kendra_houses if house_lords.get(h, "")}
    trikona_lords = {house_lords.get(h, "") for h in trikona_houses if house_lords.get(h, "")}
    dual_lords = kendra_lords & trikona_lords
    if not dual_lords:
        return "", 0.0, ""
    planet = sorted(dual_lords)[0]
    if lagna_sign in _MOVABLE_SIGNS:
        return planet, 1.0, "movable"
    if lagna_sign in _FIXED_SIGNS:
        return planet, 0.5, "fixed"
    return planet, 0.0, "dual"


def score_jaimini(
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
            planet_sign = info.get("sign", "") if isinstance(info, dict) else ""
            if not planet_sign:
                continue

            p_karaka = ""
            for k_name, p_name in chara_karakas.items():
                if p_name == planet:
                    p_karaka = k_name
                    break
            # Fix: Rahu/Ketu are no longer skipped outright. Many Jaimini sub-schools
            # (8-karaka scheme) assign Rahu the Darakaraka role and treat nodes as
            # full participants in the chara-karaka matrix. Even under the 7-karaka
            # scheme used here (no node karaka role), Rahu/Ketu still occupy signs,
            # receive chara drishti, and sit at a house-from-karakamsha distance —
            # all of which are legitimate Jaimini matrix inputs. They default to the
            # base (non-karaka) weight of 1.0 unless explicitly assigned a karaka role.
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
        # G15: tier by yoga count — more simultaneous yogas = higher quality
        _yoga_quality = 1.0 if len(raj_yogas) >= 3 else 0.75 if len(raj_yogas) == 2 else 0.50
        _yoga_bonus = 22.0 * _yoga_quality * (0.25 + 0.75 * _yoga_affinity)
        _yoga_bonus *= (_vit(ak) + _vit(amk)) / 2.0 if (ak or amk) else 1.0
        score += _yoga_bonus
        rubric_core += _yoga_bonus
        components["raj_yoga"] = round(_yoga_bonus, 2)
        trace.append(
            "Jaimini Raja-yoga support present "
            f"({', '.join(raj_yogas)}; affinity-weighted {_yoga_affinity:.2f})."
        )

    # C2: Argala weighted by field affinity of aspecting planets.
    # Virodhargala fix: raw argala is filtered through obstruction (Virodhargala)
    # cancellation before being rewarded — an argala group whose paired obstruction
    # house holds an equal-or-greater planet count is classically cancelled and must
    # not contribute points.
    argala_raw = _compute_jaimini_argala(10, ph)
    argala = _compute_jaimini_virodhargala(10, ph)
    _cancelled = sorted(set(argala_raw) - set(argala))
    if _cancelled:
        trace.append(
            f"Virodhargala cancels raw argala from {', '.join(_cancelled)} "
            "(obstruction house planet count met or exceeded the argala house)."
        )
    if argala:
        _argala_field_wt = sum(field_affinity.get(p, 0.0) for p in argala)
        _argala_avg_aff  = _argala_field_wt / len(argala)
        # Gap-12 (audit 2026-07) fix: the old formula ((n-1)*100*0.45 clamped to 12)
        # was a leftover scale bug — any 2+ argala planets always hit the 12-pt cap,
        # so the count carried no information. Now scales smoothly:
        # 1 planet → 0, 2 → 4.5, 3 → 9.0, 4+ → 12.0.
        _raw_count_bonus = min(12.0, 4.5 * max(0.0, len(argala) - 1.0))
        _alignment = min(1.0, _argala_avg_aff / 0.20)
        argala_vit = sum(_vit(p) for p in argala) / len(argala)
        argala_bonus = _raw_count_bonus * (0.30 + 0.70 * _alignment) * argala_vit
        if argala_bonus > 0:
            trace.append(
                "Argala support (post-Virodhargala) from "
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

    # G11: Upapada lord's field affinity for any field, not just Jupiter-dominant
    # N7: Dignity-weighted (was flat 0.05 — debilitated UL shouldn't get same bonus)
    if upapada:
        from jyotish.constants import _SIGN_LORD as _SL
        _upa_lord = _SL.get(upapada, "")
        _upa_aff  = field_affinity.get(_upa_lord, 0.0) if _upa_lord else 0.0
        if _upa_aff >= 0.10:
            _upa_digs = getattr(payload_data, "planet_dignities", {}) or {}
            _upa_dig  = _upa_digs.get(_upa_lord, "NEUTRAL")
            _upa_dig_m = {"EXALTED": 1.30, "OWN": 1.10, "NEECHA_BHANGA": 1.05,
                          "NEUTRAL": 1.00, "DEBILITATED": 0.50}.get(_upa_dig, 1.00)
            _bonus = (100.0 - score) * 0.05 * _vit(_upa_lord) * _upa_dig_m
            score += _bonus; rubric_support += _bonus
            components["upapada"] = round(_bonus, 2)
            trace.append(f"Upapada lord {_upa_lord} aligns with field "
                         f"(affinity {_upa_aff:.2f}, dignity {_upa_dig}).")

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
        vargottama_planets=getattr(payload_data, "vargottama_planets", []),
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

    # ── G17: Atmakaraka position in D24 (academic varga cross-check) ────────────
    if ak:
        _d24c = getattr(payload_data, "divisional_charts", {}).get("D24_siddhamsam", {}) or {}
        _d24l = _d24c.get("Lagna", "")
        _ak_d24_sign = _d24c.get(ak, "")
        if _ak_d24_sign and _d24l:
            _ak_d24_h = _house_distance(_d24l, _ak_d24_sign)
            if _ak_d24_h in (5, 9, 10):
                _ak_d24_b = field_affinity.get(ak, 0.0) * 8.0 * _vit(ak)
                score += _ak_d24_b; rubric_validation += _ak_d24_b
                components["ak_d24"] = round(_ak_d24_b, 2)
                trace.append(f"AK ({ak}) in D24 H{_ak_d24_h} — academic/professional confirmation.")

    # ── G12: H10 from Chandra Lagna (Gap-14 fix: shared common helper) ────────
    _cl_h10_j = chandra_lagna_h10_lord(planets_d1)
    if _cl_h10_j:
        _cl_h10_aff = field_affinity.get(_cl_h10_j, 0.0)
        if _cl_h10_j and _cl_h10_aff >= 0.10:
            _cl_b = _cl_h10_aff * 6.0 * _vit(_cl_h10_j)
            score += _cl_b; rubric_support += _cl_b
            components["chandra_h10_jaimini"] = round(_cl_b, 2)

    # ── T1-C: Chara Dasha as first-class Jaimini signal ──────────────────────
    # The active Chara Dasha sign's lord is Jaimini's equivalent of the Vimshottari
    # MD lord — equal career authority. Use keyword matching with DASHA_KEYWORDS
    # and award 15-18 pts when the lord's domain aligns with the field.
    _current_age_j = float(getattr(payload_data, "current_age", 30) or 30)
    _lagna_sign_j  = getattr(payload_data, "lagna_sign", "") or ""
    _planets_d1_j  = getattr(payload_data, "planets_d1", {}) or {}
    _active_cd_sign = (
        getattr(payload_data, "active_chara_dasha_sign", "")
        or getattr(payload_data, "chara_dasha_sign", "")
        or _get_active_chara_dasha_sign(_lagna_sign_j, _current_age_j, _planets_d1_j)
    )
    if _active_cd_sign:
        _cd_lord = _SIGN_LORD.get(_active_cd_sign, "")
        if _cd_lord:
            _cd_kws = DASHA_KEYWORDS.get(_cd_lord, [])
            _cd_aff = field_affinity.get(_cd_lord, 0.0)
            if any(_wm(kw, label) for kw in _cd_kws):
                _cd_pts = max(_cd_aff * 16.0, 1.5) * _vit(_cd_lord)
                _cd_pts = min(_cd_pts, 18.0)
                score += _cd_pts; rubric_core += _cd_pts
                components["chara_dasha_sign_lord"] = round(_cd_pts, 2)
                trace.append(
                    f"T1-C Chara Dasha: active sign {_active_cd_sign} (lord {_cd_lord}) "
                    f"career keywords match {domain} field — Jaimini timing confirms."
                )

    # ── N7: H10 from Karakamsha — Jaimini's deepest career mandate ──────────
    # Karakamsha is the navamsha sign of the Atmakaraka. H10 from it gives the
    # soul's career calling. When that lord aligns with the field, it is the
    # strongest possible Jaimini career confirmation.
    _karak_sign = getattr(payload_data, "karakamsha_sign", "") or getattr(payload_data, "karakamsha", "") or ""
    if _karak_sign:
        _SIGNS_J = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda x: x[1])]
        _kar_h10_sign = _SIGNS_J[(_SIGN_NUM[_karak_sign] - 1 + 9) % 12] if _karak_sign in _SIGN_NUM else ""
        _kar_h10_lord = _SIGN_LORD.get(_kar_h10_sign, "")
        if _kar_h10_lord:
            _kar_aff = field_affinity.get(_kar_h10_lord, 0.0)
            if _kar_aff >= 0.08:
                _kar_pts = _kar_aff * 12.0 * _vit(_kar_h10_lord)
                _kar_pts = min(_kar_pts, 14.0)
                score += _kar_pts; rubric_core += _kar_pts
                components["karakamsha_h10"] = round(_kar_pts, 2)
                trace.append(
                    f"N7 H10 from Karakamsha ({_karak_sign}): lord {_kar_h10_lord} "
                    f"aligns with {domain} — soul career mandate confirmed."
                )

    # ── Jaimini Kendradhipati dosha cancellation (lagna-type dependent) ──────
    _lagna_sign_kd = getattr(payload_data, "lagna_sign", "") or ""
    _kd_planet, _kd_factor, _kd_lagna_type = _jaimini_kendradhipati_cancellation(house_lords, _lagna_sign_kd)
    if _kd_planet and _kd_factor > 0:
        _kd_aff = field_affinity.get(_kd_planet, 0.0)
        if _kd_aff >= 0.10:
            _kd_b = _kd_aff * 9.0 * _kd_factor * _vit(_kd_planet)
            _kd_b = min(_kd_b, 9.0)
            score += _kd_b; rubric_core += _kd_b
            components["kendradhipati_cancellation"] = round(_kd_b, 2)
            trace.append(
                f"Kendradhipati dosha on {_kd_planet} (kendra+trikona dual lord) is "
                f"{'fully' if _kd_factor == 1.0 else 'partially'} cancelled for {_lagna_sign_kd} "
                f"({_kd_lagna_type} lagna) -- Jaimini rule restores its yogakaraka strength."
            )
    elif _kd_planet and _kd_lagna_type == "dual":
        trace.append(
            f"Kendradhipati dosha on {_kd_planet} stands uncancelled for dual-sign {_lagna_sign_kd} lagna "
            f"per Jaimini rule -- no bonus applied."
        )

    # ── Karakamsha's rasi drishti (chara drishti) onto D1 lagna ──────────────
    # Jaimini's deepest career-confirmation technique operates from Karakamsha
    # (AK's navamsha sign) as the soul lagna. When Karakamsha itself casts rasi
    # drishti onto the D1 (physical/embodied) lagna, the soul's purpose actively
    # directs the native's worldly life -- a Karakamsha-Rasi drishti union yoga.
    if karakamsha and _lagna_sign_kd and _check_chara_drishti(karakamsha, _lagna_sign_kd):
        _kd_lagna_b = 6.0 * _vit(ak) if ak else 5.0
        _kd_lagna_b = min(_kd_lagna_b, 6.0)
        score += _kd_lagna_b; rubric_validation += _kd_lagna_b
        components["karakamsha_lagna_drishti"] = round(_kd_lagna_b, 2)
        trace.append(
            f"Karakamsha ({karakamsha}) casts rasi drishti onto the D1 lagna ({_lagna_sign_kd}) -- "
            f"soul purpose directly aspects and shapes embodied career life (Jaimini union yoga)."
        )

    # ── Systematic karaka-domain bonus (cross-cutting gap fix) ────────────────
    # Jaimini's own matrix above weights planets by chara-karaka role, but still
    # depends on field_affinity being populated by keyword matching elsewhere.
    # This adds the shared BPHS/Jataka Parijata karakatwa fallback (previously
    # only in knrao.py) so a classically valid graha-domain match isn't lost
    # just because a field's id/label falls outside every hand-curated list.
    _karaka_dom_b, _karaka_dom_hits = _karakatwa_domain_bonus(
        domain, field_affinity, planets_d1, ph, payload_data, scale=5.0, cap=10.0,
    )
    if _karaka_dom_b > 0:
        score += _karaka_dom_b; rubric_support += _karaka_dom_b
        components["karaka_domain_bonus"] = round(_karaka_dom_b, 2)
        trace.append(
            f"Karakatwa domain match ({domain}): {', '.join(_karaka_dom_hits)} carry classical "
            "significator authority for this domain (systematic karaka-to-field mapping)."
        )

    # ── Ontology fix: house-signification-first primitive ────────────────────
    # Jaimini's own technique already runs largely through karakas/karakamsha
    # rather than bhava lordship, so this domain-driven house signal (H6/H8/H12
    # for medicine, H6/H7/H9 for law, etc.) restores the bhava-lordship axis
    # that Parashari/Jaimini synthesis traditionally cross-checks against
    # karaka testimony, independent of field-id keyword matching.
    _house_dom_b, _house_dom_hits = _house_signification_bonus(
        domain, field_affinity, house_lords, ph, planets_d1, payload_data, scale=5.0, cap=10.0,
    )
    if _house_dom_b > 0:
        score += _house_dom_b; rubric_support += _house_dom_b
        components["house_signification_bonus"] = round(_house_dom_b, 2)
        trace.append(
            f"House signification ({domain}): {', '.join(_house_dom_hits)} lord(s) "
            "carry classical house authority for this field."
        )

    # ── Vimshopaka Bala: unified divisional-strength coefficient ─────────────
    # Fix (cross-cutting gap): applies the shared reduced Vimshopaka Bala
    # (D1/D3/D9/D10/D20/D24/D30 dignity) as a bounded nudge on AK/AmK — Jaimini's
    # own primary karakas — so divisional strength is read consistently with
    # the other methods instead of only through Jaimini-specific varga checks
    # (D24 academic cross-check) that were already present.
    _vim_planets_j = [p for p in (ak, amk) if p]
    if _vim_planets_j:
        _vim_avg_j = sum(_vimsopaka_bala_coefficient(p, payload_data) for p in _vim_planets_j) / len(_vim_planets_j)
        _vim_adj_j = (_vim_avg_j - 1.0) * 15.0
        if abs(_vim_adj_j) > 0.05:
            score += _vim_adj_j
            rubric_validation += _vim_adj_j
            components["vimsopaka_bala"] = round(_vim_adj_j, 2)
            trace.append(
                f"Vimshopaka Bala for AK/AmK ({', '.join(_vim_planets_j)}): "
                f"avg coefficient {_vim_avg_j:.2f} -- unified divisional strength "
                f"{'supports' if _vim_adj_j > 0 else 'weakens'} this field."
            )

    rubric = build_score_rubric(
        "jaimini",
        [
            rubric_section(
                "core",
                rubric_core,
                60.0,
                # Gap-13 fix: raj_yoga points accumulate into rubric_core, so it is
                # listed here (it was previously mislabeled under validation).
                note="Chara karaka matrix, karakamsha, raj yoga, dharma-karma, brahma/maheshwara, chara dasha, kendradhipati.",
                items=["contribution", "karakamsha", "karakamsha_h10", "dharma_karma",
                       "brahma", "maheshwara", "chara_dasha_sign_lord", "raj_yoga",
                       "kendradhipati_cancellation"],
            ),
            rubric_section(
                "support",
                rubric_support,
                25.0,
                note="Argala, upapada, cluster, chandra lagna, karakatwa domain, and house-signification signals.",
                items=["argala", "upapada", "chandra_h10_jaimini", "karakamsha_lagna_drishti",
                       "karaka_domain_bonus", "house_signification_bonus"],
            ),
            rubric_section(
                "validation",
                rubric_validation,
                20.0,
                note="D24 and divisional cross-checks, Vimshopaka Bala.",
                items=["ak_d24", "d24_bonus", "life_science_cluster", "space_aerospace_cluster",
                       "vimsopaka_bala"],
            ),
            rubric_section(
                "penalty",
                rubric_penalty,
                20.0,   # Gap-13 fix: cap was 0.0, so penalty display always showed 0
                kind="penalty",
                note="Dusthana lordship and vitality friction.",
                items=["combustion_penalty", "dusthana_penalty", "_vitality_penalty"],
            ),
        ],
    )

    # Gap-1 (audit 2026-07) fix: cap unified with bundle via METHOD_SCORE_CAPS["jaimini"].
    # Gap-3/9 fix: pass raw signed `score` (not pre-clamped) so contraindicated
    # charts (net penalties > positives) are distinguishable from neutral ones;
    # method_result() still clamps internally for the "score" field.
    return method_result("jaimini", score, trace, components, rubric=rubric,
                         normalization_cap=METHOD_SCORE_CAPS["jaimini"])
