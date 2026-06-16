"""JyotishAI — JSON payload parser, course registry loader, aptitude scorer."""
import json, os
from datetime import datetime, date
from typing import Dict, List, Tuple, Set, Any, Optional

from .payload import NatalPayloadV2, logger
from .constants import DOMAIN_STRATEGIES, _SIGN_LORD
from .astro import (
    compute_dignity, _planet_abs_degree, _compute_bhava_chalit_houses,
    _detect_neecha_bhanga, _detect_yogas, _detect_planetary_war,
    _compute_eff_strengths, _is_vargottama, _detect_combust_planets, _calc_age,
    get_nakshatra_from_longitude,
)

from .constants import (
    _NODAL_DEFAULT_VIRUPAS, _PLANET_MIN_SHADBALA, _SIGN_NUM,
    _SIGN_LORD, _KARAKAMSHA_OCCUPANT_KW,
)
from .affinity import BRANCH_PLANET_AFFINITY


def parse_json_payload(data, student_name="Unknown") -> NatalPayloadV2:
    pyh = data.get("pyhora_calculations", {})
    ctx = data.get("student_context", {})
    sys_cfg = data.get("system_config", {})
    if student_name in ("Unknown", "Student", ""):
        student_name = ctx.get("student_name") or ctx.get("name") or student_name
    
    lagna_sign = pyh.get("d1_lagna", "")
    lagna_deg  = pyh.get("d1_lagna_degree", 15.0) 
    planets_d1 = pyh.get("planets_d1", {})
    
    planet_retrograde = {p: bool(planets_d1[p].get("is_retrograde", False)) for p in planets_d1}
    
    sun_data = planets_d1.get("Sun", {})
    sun_abs = _planet_abs_degree(sun_data.get("sign","Aries"), sun_data.get("degree",0))
    combust_planets, cazimi_planets = _detect_combust_planets(planets_d1, sun_abs, planet_retrograde)
    
    # ASTRO-8: Dynamic Equal House Bhava Chalit
    planet_house = _compute_bhava_chalit_houses(planets_d1, lagna_sign, lagna_deg)
    
    shadbala = {p: planets_d1[p]["shadbala_virupas"] for p in planets_d1 if "shadbala_virupas" in planets_d1[p]}
    for _node in ("Rahu","Ketu"):
        if _node in planets_d1 and _node not in shadbala:
            node_sign = planets_d1[_node].get("sign", "")
            dispositor = _SIGN_LORD.get(node_sign, "")
            # ASTRO-9 FIX: Apply 0.75 proxy discount when inheriting dispositor shadbala.
            # Nodes act THROUGH their dispositor, not AS the dispositor — direct inheritance
            # caused a double-echo when the dispositor was already a Yogakaraka: Rahu was
            # getting Saturn's full raw_ratio AND Saturn's Yogakaraka func_mod simultaneously.
            # The 0.75 factor breaks this echo chain while preserving the dispositor linkage.
            shadbala[_node] = shadbala.get(dispositor, _NODAL_DEFAULT_VIRUPAS) * 0.75
            
    kp_cusps = pyh.get("kp_cusp_data", {})
    jaimini = pyh.get("kn_rao_jaimini_data", {})
    karakas = jaimini.get("chara_karakas", {})
    div_charts = pyh.get("divisional_charts", {})
    d10 = div_charts.get("D10_dashamsha", {})
    d9 = div_charts.get("D9_navamsha", {})
    d24 = div_charts.get("D24_siddhamsam", {})
    
    moon_data = planets_d1.get("Moon", {})
    sun_moon_diff = abs(_planet_abs_degree(moon_data.get("sign","Aries"), moon_data.get("degree",0)) - sun_abs)
    if sun_moon_diff > 180: sun_moon_diff = 360 - sun_moon_diff
    
    d9_planet_dignities = {p: compute_dignity(p, s) for p, s in d9.items() if p != "Lagna"}
    
    planet_dignities = {p: compute_dignity(p, planets_d1[p]["sign"]) for p in planets_d1 if "sign" in planets_d1[p]}
    d24_planet_dignities = {p: compute_dignity(p, s) for p, s in d24.items() if p != "Lagna"}

    detected_yogas = _detect_yogas(planets_d1, planet_house, planet_dignities)
    
    # Apply Parivartana Dignity Upgrade BEFORE Neecha Bhanga
    for yoga in detected_yogas:
        if yoga.startswith("Parivartana_"):
            parts = yoga.split("_")
            if len(parts) == 3:
                planet_dignities[parts[1]] = "OWN"
                planet_dignities[parts[2]] = "OWN"

    neecha_bhanga_set = _detect_neecha_bhanga(planet_dignities, planet_house)

    nakshatra_data = {}
    for p, details in planets_d1.items():
        if "nakshatra" in details:
            nakshatra_data[p] = details["nakshatra"]
        else:
            nakshatra_data[p] = get_nakshatra_from_longitude(_planet_abs_degree(details.get("sign","Aries"), details.get("degree",0)))

       
    
    # House occupancy for D10 consistency
    d10_house_occ = {}
    d10_lagna = d10.get("Lagna", lagna_sign)
    for p, s in d10.items():
        if p != "Lagna":
            h = ((_SIGN_NUM.get(s, 1) - _SIGN_NUM.get(d10_lagna, 1)) % 12) + 1
            d10_house_occ.setdefault(str(h), []).append(p)

    # FIX-14: Extract transit house positions if present in JSON.
    transit_hp: Dict[str, int] = {}
    for planet, house_n in pyh.get("transit_house_positions", {}).items():
        try:
            transit_hp[planet] = int(house_n)
        except (ValueError, TypeError):
            pass

    # FIX-14: Extract pratyantar / antardasha lord if present.
    prd_lord_raw  = pyh.get("pratyantar_dasha_lord", "") or pyh.get("antardasha_lord", "")
    prd_houses_raw: List[int] = []
    if prd_lord_raw:
        prd_houses_raw = [planet_house.get(prd_lord_raw, 0)]

    maheshwara_raw = jaimini.get("jaimini_special_lords", {}).get("maheshwara", "")

    return NatalPayloadV2(
        name=student_name, lagna_sign=lagna_sign, lagna_lord=_SIGN_LORD.get(lagna_sign,""),
        h10_lord=kp_cusps.get("H10",{}).get("sign_lord",""), atmakaraka=karakas.get("AK",""),
        amatyakaraka=karakas.get("AmK",""), karakamsha=jaimini.get("karakamsha_sign",""),
        planet_strength={p:round(v/600,4) for p,v in shadbala.items()}, shadbala=shadbala,
        planet_house=planet_house, house_lords={str(i): kp_cusps.get(f"H{i}",{}).get("sign_lord","") for i in range(1,13)},
        yogas_present=detected_yogas, dasha_sequence=[{"lord":d.get("md_planet",""),"start_age":d.get("age_start"),"end_age":d.get("age_end")} for d in pyh.get("vimshottari_dasha_sequence",[])],
        current_age=_calc_age(ctx.get("dob",""), sys_cfg.get("current_date","")),
        sun_moon_degrees_apart=round(sun_moon_diff,4),
        sav_points_houses=pyh.get("ashtakavarga_sav",{}), combust_planets=combust_planets, cazimi_planets=cazimi_planets,
        kp_significators=pyh.get("kp_planetary_significators",{}), kp_cusps=kp_cusps,
        planet_dignities=planet_dignities, d24_planet_dignities=d24_planet_dignities,
        planet_retrograde=planet_retrograde, detected_yogas=detected_yogas, h5_lord=kp_cusps.get("H5",{}).get("sign_lord",""),
        amk_house=planet_house.get(karakas.get("AmK",""), 0), upapada_lagna=jaimini.get("upapada_lagna_sign",""),
        h10_lord_planet=kp_cusps.get("H10",{}).get("sign_lord",""), d9_planet_dignities=d9_planet_dignities,
        planets_d1=planets_d1, divisional_charts=div_charts, nakshatra_data=nakshatra_data,
        d9_lagna_sign=d9.get("Lagna", ""), karakamsha_occupants=[p for p, s in d9.items() if p != "Lagna" and s == jaimini.get("karakamsha_sign","")],
        neecha_bhanga_planets=list(neecha_bhanga_set), gender=ctx.get("gender", ""),
        interested_in=ctx.get("student_preference", {}).get("interested_in", []),
        already_excel_at=ctx.get("student_preference", {}).get("already_excel_at", []),
        brahma_lord=jaimini.get("jaimini_special_lords", {}).get("brahma", ""),
        d10_house_occupancy=d10_house_occ,
        transit_house_positions=transit_hp,          # FIX-12
        pratyantar_dasha_lord=prd_lord_raw,          # FIX-12
        prd_lord_houses=prd_houses_raw,              # FIX-12
        maheshwara_lord=maheshwara_raw,              # FIX-6
        dob=ctx.get("dob",""),
    )

def _edu_sav_mod(sav: Dict) -> float:
    # FIX-9: H10 raised (career house primary); H11 added (income/gains); H4 reduced.
    h4  = sav.get("H4",  28); h5  = sav.get("H5",  28)
    h9  = sav.get("H9",  28); h10 = sav.get("H10", 28); h11 = sav.get("H11", 28)
    weighted = 0.10*h4 + 0.25*h5 + 0.25*h9 + 0.30*h10 + 0.10*h11
    return 1.0 + (weighted - 28) / 100

def compute_aptitude_by_domain(domain, raw_shadbala, sav_points, eff_strengths: Dict[str, float] = None,
                                branch_affinity_weights: Dict[str, float] = None,
                                field_id: str = ""):
    """Compute domain aptitude using hardcoded BRANCH_PLANET_AFFINITY multi-karaka weights.

    Looks up field_id in BRANCH_PLANET_AFFINITY for deterministic top-2 karakas.
    Falls back to branch_affinity_weights (legacy) then Mercury+Jupiter if neither available.
    """
    strat = DOMAIN_STRATEGIES.get(domain.lower(), {"w1":0.40,"w2":0.40,"min_score":50})

    # Task#2: use hardcoded multi-karaka dict (deterministic, no LLM hallucination)
    if field_id and field_id in BRANCH_PLANET_AFFINITY:
        top = sorted(BRANCH_PLANET_AFFINITY[field_id].items(), key=lambda x: -x[1])
        p1 = top[0][0]
        p2 = top[1][0]
    elif branch_affinity_weights:
        top = sorted(branch_affinity_weights.items(), key=lambda x: -x[1])
        p1 = top[0][0] if len(top) > 0 else "Mercury"
        p2 = top[1][0] if len(top) > 1 else "Jupiter"
    else:
        top = []
        p1, p2 = "Mercury", "Jupiter"   # generic fallback

    if eff_strengths:
        p1_str = min(eff_strengths.get(p1, 0.0), 2.0)
        p2_str = min(eff_strengths.get(p2, 0.0), 2.0)
        # If p2 is near-zero (e.g. Moon at new-moon Paksha Bala) but a stronger
        # p3 exists in the affinity list, substitute p3 as the secondary karaka.
        # Classical principle: a debilitated or near-powerless secondary karaka
        # should not entirely negate the field when p1 is very strong — use the
        # next-best karaka that the field itself recognises.
        if p2_str < 0.50 and p1_str >= 1.20 and len(top) > 2:
            p3 = top[2][0]
            p3_str = min(eff_strengths.get(p3, 0.0), 2.0)
            if p3_str > p2_str:
                p2, p2_str = p3, p3_str
    else:
        p1_str = raw_shadbala.get(p1, 0.0) / _PLANET_MIN_SHADBALA.get(p1, 300.0)
        p2_str = raw_shadbala.get(p2, 0.0) / _PLANET_MIN_SHADBALA.get(p2, 300.0)

    sav_mod = _edu_sav_mod(sav_points)
    val1    = min(100, int(p1_str * 100 * strat["w1"] * sav_mod))
    val2    = min(100, int(p2_str * 100 * strat["w2"] * sav_mod))
    composite = val1 + val2
    return {"composite_score":composite,"primary_aptitude":val1,"secondary_aptitude":val2,
            "threshold_required":strat["min_score"],"meets_threshold":composite>=strat["min_score"]}

def _load_course_registry(
    registry_path: str = "",
) -> Dict[str, Dict]:
    """Load the India course registry (planet_affinity already stripped).

    Search order (first hit wins):
      1. Explicit ``registry_path`` argument if provided.
      2. COURSE_REGISTRY_PATH environment variable.
      3. CWD / india_course_registry_no_planets.json
      4. Parent of this module's directory (e.g. LLMbased/)
      5. This module's directory (jyotish/)

    Returns a dict keyed by field_id. Falls back to {} on any error.
    """
    import os as _os
    _fname = "india_course_registry_no_planets.json"
    candidates: List[str] = []
    if registry_path:
        candidates.append(registry_path)
    env_path = _os.environ.get("COURSE_REGISTRY_PATH", "")
    if env_path:
        candidates.append(env_path)
    # CWD
    candidates.append(_os.path.join(_os.getcwd(), _fname))
    # Parent of jyotish/ (i.e. LLMbased/)
    _module_dir = _os.path.dirname(_os.path.abspath(__file__))
    candidates.append(_os.path.join(_os.path.dirname(_module_dir), _fname))
    # jyotish/ itself
    candidates.append(_os.path.join(_module_dir, _fname))

    for _path in candidates:
        if not _os.path.isfile(_path):
            continue
        try:
            with open(_path, "r", encoding="utf-8") as _f:
                _data = json.load(_f)
            branches = _data.get("branches", {})
            logger.info(f"Course registry loaded: {len(branches)} branches from {_path}")
            return branches
        except Exception as _e:
            logger.warning(f"Could not parse registry at {_path}: {_e}")

    logger.warning(
        f"Course registry not found (searched: {candidates}); "
        "scoring loop will be empty. Set COURSE_REGISTRY_PATH env var or place "
        f"\'{_fname}\' next to field_deterministic_engine_v1_llm.py."
    )
    return {}
