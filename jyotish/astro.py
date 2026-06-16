"""JyotishAI — Core Vedic astrological calculations.

Covers: dignity, Bhava Chalit, Graha Drishti (with Drishti Bala),
Neecha Bhanga, yoga detection, combustion, Shadbala-derived effective strengths.
"""
import math as _math
from datetime import date
from typing import Dict, List, Tuple, Set, Any, Optional

from .constants import (
    _EXALT_SIGN, _DEBIL_SIGN, _OWN_SIGN, _DIGNITY_MOD,
    _KENDRA_HOUSES, _KT_HOUSES, _COMBUST_ORB,
    _NODAL_DEFAULT_VIRUPAS, _PLANET_MIN_SHADBALA,
    _NAKSHATRA_LORD, _FAVORABLE_NAKSHATRA_BASE,
    _NEECHA_BHANGA_DATA, _SIGN_NUM, _SIGN_LORD,
)

_SIGN_ABS: Dict[str, float] = {
    "Aries": 0, "Taurus": 30, "Gemini": 60, "Cancer": 90,
    "Leo": 120, "Virgo": 150, "Libra": 180, "Scorpio": 210,
    "Sagittarius": 240, "Capricorn": 270, "Aquarius": 300, "Pisces": 330,
}

def compute_dignity(planet: str, sign: str) -> str:
    """ASTRO-7: Node dignity added alongside classical mapping."""
    if planet == "Rahu":
        if sign in ["Taurus", "Gemini"]: return "EXALTED"
        if sign in ["Scorpio", "Sagittarius"]: return "DEBILITATED"
        if sign == "Aquarius": return "OWN"
    if planet == "Ketu":
        if sign in ["Scorpio", "Sagittarius"]: return "EXALTED"
        if sign in ["Taurus", "Gemini"]: return "DEBILITATED"
        # NOTE: "OWN" for Scorpio was dead code (Scorpio already returns EXALTED above) — removed (ASTRO-7 fix)

    if _EXALT_SIGN.get(planet) == sign: return "EXALTED"
    if _DEBIL_SIGN.get(planet)  == sign: return "DEBILITATED"
    if sign in _OWN_SIGN.get(planet, []): return "OWN"
    return ""

def _planet_abs_degree(sign, degree):
    return (_SIGN_NUM.get(sign, 1) - 1) * 30 + degree
def _compute_bhava_chalit_houses(planets_d1: Dict, lagna_sign: str, lagna_degree: float = 15.0) -> Dict[str, int]:
    """ASTRO-8: Dynamic Equal House Bhava Chalit using Lagna degree."""
    chalit_houses = {}
    lagna_abs = _planet_abs_degree(lagna_sign, lagna_degree)
    
    for p, pdata in planets_d1.items():
        if "sign" not in pdata or "degree" not in pdata: continue
        p_abs = _planet_abs_degree(pdata["sign"], pdata["degree"])
        diff = (p_abs - lagna_abs) % 360
        house = int((diff + 15) // 30) + 1
        if house == 13: house = 1
        chalit_houses[p] = house
        
    return chalit_houses

def get_nakshatra_from_longitude(abs_degree: float) -> str:
    nakshatras = [
        "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
        "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni",
        "Uttara Phalguni","Hasta","Chitra","Swati","Vishakha",
        "Anuradha","Jyeshtha","Mula","Purva Ashadha","Uttara Ashadha",
        "Shravana","Dhanishta","Shatabhisha","Purva Bhadrapada",
        "Uttara Bhadrapada","Revati",
    ]
    index = int(abs_degree / 13.333333333333334)
    return nakshatras[min(index, 26)]


# ===========================================================================
# GRAHA DRISHTI (PLANETARY ASPECTS) — with Drishti Bala orb weighting
# ===========================================================================
def _drishti_bala(planet_degree: float) -> float:
    """Drishti Bala strength modifier based on position within house.

    Classical Drishti Bala gives maximum aspect strength at the house midpoint
    (15° within sign) and diminishes toward the cusps (0° or 30°).
    Returns a multiplier in [0.5, 1.0].
    """
    within_house = planet_degree % 30.0
    centrality   = 1.0 - abs(within_house - 15.0) / 15.0   # 0 at cusps, 1 at midpoint
    return round(0.5 + 0.5 * centrality, 4)


def _get_planetary_aspects(planet_house: Dict[str, int]) -> Dict[str, List[int]]:
    """ASTRO-6: Maps full planetary aspects (Drishti) per classical rules."""
    aspects = {p: [] for p in planet_house}
    for p, h in planet_house.items():
        if h == 0: continue
        # Universal 7th house aspect
        aspects[p].append((h + 6 - 1) % 12 + 1)
        # Special outer planet aspects
        if p == "Mars":
            aspects[p].extend([(h + 4 - 2) % 12 + 1, (h + 8 - 2) % 12 + 1])  # FIX-3
        elif p in ("Jupiter", "Rahu", "Ketu"):
            aspects[p].extend([(h + 5 - 2) % 12 + 1, (h + 9 - 2) % 12 + 1])  # FIX-3
        elif p == "Saturn":
            aspects[p].extend([(h + 3 - 2) % 12 + 1, (h + 10 - 2) % 12 + 1])  # FIX-3
    return {p: list(set(v)) for p, v in aspects.items()}


def _get_planetary_aspects_weighted(
    planet_house: Dict[str, int],
    planets_d1: Dict,
) -> Dict[str, Dict[int, float]]:
    """Drishti Bala orb-weighted aspects.

    Returns {planet: {aspected_house: strength}} where strength ∈ [0.5, 1.0].
    Strength = 1.0 at house midpoint, 0.5 at house cusp — classical Drishti Bala.
    """
    binary = _get_planetary_aspects(planet_house)
    weighted: Dict[str, Dict[int, float]] = {}
    for p, houses in binary.items():
        p_deg    = planets_d1.get(p, {}).get("degree", 15.0)
        strength = _drishti_bala(p_deg)
        weighted[p] = {h: strength for h in houses}
    return weighted
def _drishti_bala(planet_degree: float) -> float:
    """Drishti Bala strength modifier based on position within house.

    Classical Drishti Bala gives maximum aspect strength at the house midpoint
    (15° within sign) and diminishes toward the cusps (0° or 30°).
    Returns a multiplier in [0.5, 1.0].
    """
    within_house = planet_degree % 30.0
    centrality   = 1.0 - abs(within_house - 15.0) / 15.0   # 0 at cusps, 1 at midpoint
    return round(0.5 + 0.5 * centrality, 4)


def _get_planetary_aspects(planet_house: Dict[str, int]) -> Dict[str, List[int]]:
    """ASTRO-6: Maps full planetary aspects (Drishti) per classical rules."""
    aspects = {p: [] for p in planet_house}
    for p, h in planet_house.items():
        if h == 0: continue
        # Universal 7th house aspect
        aspects[p].append((h + 6 - 1) % 12 + 1)
        # Special outer planet aspects
        if p == "Mars":
            aspects[p].extend([(h + 4 - 2) % 12 + 1, (h + 8 - 2) % 12 + 1])  # FIX-3
        elif p in ("Jupiter", "Rahu", "Ketu"):
            aspects[p].extend([(h + 5 - 2) % 12 + 1, (h + 9 - 2) % 12 + 1])  # FIX-3
        elif p == "Saturn":
            aspects[p].extend([(h + 3 - 2) % 12 + 1, (h + 10 - 2) % 12 + 1])  # FIX-3
    return {p: list(set(v)) for p, v in aspects.items()}


def _get_planetary_aspects_weighted(
    planet_house: Dict[str, int],
    planets_d1: Dict,
) -> Dict[str, Dict[int, float]]:
    """Drishti Bala orb-weighted aspects.

    Returns {planet: {aspected_house: strength}} where strength ∈ [0.5, 1.0].
    Strength = 1.0 at house midpoint, 0.5 at house cusp — classical Drishti Bala.
    """
    binary = _get_planetary_aspects(planet_house)
    weighted: Dict[str, Dict[int, float]] = {}
    for p, houses in binary.items():
        p_deg    = planets_d1.get(p, {}).get("degree", 15.0)
        strength = _drishti_bala(p_deg)
        weighted[p] = {h: strength for h in houses}
    return weighted
def _detect_neecha_bhanga(planet_dignities: Dict[str, str],
                           planet_house: Dict[str, int]) -> Set[str]:
    cancelled: Set[str] = set()
    for planet, dignity in planet_dignities.items():
        if dignity != "DEBILITATED": continue
        nb = _NEECHA_BHANGA_DATA.get(planet, {})
        if not nb: continue
        sl, el = nb.get("debil_sign_lord", ""), nb.get("exalt_lord", "")
        if sl and planet_house.get(sl, 0) in _KENDRA_HOUSES: cancelled.add(planet)
        elif el and el != planet and planet_house.get(el, 0) in _KENDRA_HOUSES: cancelled.add(planet)
        elif planet_house.get(planet, 0) in _KENDRA_HOUSES and planet_house.get(sl, 0) in _KT_HOUSES:
            cancelled.add(planet)
    return cancelled


def _detect_yogas(planets_d1: Dict, planet_house: Dict,
                  planet_dignities: Dict = None) -> List[str]:
    if planet_dignities is None: planet_dignities = {}
    yogas: List[str] = []
    
    jup_h, ven_h, mer_h = planet_house.get("Jupiter", 0), planet_house.get("Venus", 0), planet_house.get("Mercury", 0)
    sat_h, mar_h, moon_h = planet_house.get("Saturn", 0), planet_house.get("Mars", 0), planet_house.get("Moon", 0)
    
    jup_sign = planets_d1.get("Jupiter", {}).get("sign","")
    sat_sign = planets_d1.get("Saturn", {}).get("sign","")
    sun_sign = planets_d1.get("Sun", {}).get("sign","")
    mer_sign = planets_d1.get("Mercury", {}).get("sign","")
    moon_sign = planets_d1.get("Moon", {}).get("sign","")
    ven_sign = planets_d1.get("Venus", {}).get("sign","")
    mar_sign = planets_d1.get("Mars", {}).get("sign","")

    aspects = _get_planetary_aspects(planet_house)

    if jup_h in _KT_HOUSES and ven_h in _KT_HOUSES and mer_h in _KT_HOUSES: yogas.append("Saraswati")
    if moon_sign and jup_sign and (moon_h in aspects.get("Jupiter", []) or jup_h in aspects.get("Moon", [])):
        yogas.append("GajaKesari")
    # BudhaAditya: same rashi OR within 15 deg (Mercury combust orb).
    # This catches charts where Sun/Mercury straddle a sign boundary near lagna
    # (e.g. Sun at Scorpio 0.1 deg, Mercury at Libra 24.5 deg = 5.6 deg apart,
    # both in H1 by Bhava Chalit). Without this, combust Mercury loses the yoga.
    _sun_d1  = planets_d1.get("Sun", {})
    _mer_d1  = planets_d1.get("Mercury", {})
    _sun_abs = _planet_abs_degree(_sun_d1.get("sign","Aries"), _sun_d1.get("degree",0))
    _mer_abs = _planet_abs_degree(_mer_d1.get("sign","Aries"), _mer_d1.get("degree",0))
    _sm_diff = abs(_sun_abs - _mer_abs)
    if _sm_diff > 180: _sm_diff = 360 - _sm_diff
    # ASTRO-9 FIX: BudhaAditya requires same-sign conjunction (classical Parasara rule).
    # Cross-sign proximity (< 15°) is NOT sufficient — different rashis = different lords.
    if sun_sign and mer_sign and sun_sign == mer_sign:
        yogas.append("BudhaAditya")
    
    if sat_sign and compute_dignity("Saturn", sat_sign) in ("OWN","EXALTED") and sat_h in _KENDRA_HOUSES: yogas.append("Shasha")
    if jup_sign and compute_dignity("Jupiter", jup_sign) in ("OWN","EXALTED") and jup_h in _KENDRA_HOUSES: yogas.append("Hamsa")
    if mar_sign and compute_dignity("Mars", mar_sign) in ("OWN","EXALTED") and mar_h in _KENDRA_HOUSES: yogas.append("Ruchaka")
    if mer_sign and compute_dignity("Mercury", mer_sign) in ("OWN","EXALTED") and mer_h in _KENDRA_HOUSES: yogas.append("Bhadra")
    if ven_sign and compute_dignity("Venus", ven_sign) in ("OWN","EXALTED") and ven_h in _KENDRA_HOUSES: yogas.append("Malavya")
    
    if moon_h and mar_h:
        if moon_h == mar_h or moon_h in aspects.get("Mars", []) or mar_h in aspects.get("Moon", []):
            yogas.append("ChandraMangala")
            
    checked_pairs: Set[Tuple] = set()
    for p1, pd1 in planets_d1.items():
        for p2, pd2 in planets_d1.items():
            if p1 >= p2: continue
            pair = (p1, p2)
            if pair in checked_pairs: continue
            checked_pairs.add(pair)
            s1, s2 = pd1.get("sign",""), pd2.get("sign","")
            if not s1 or not s2: continue
            if s2 in _OWN_SIGN.get(p1,[]) and s1 in _OWN_SIGN.get(p2,[]):
                yogas.append(f"Parivartana_{p1}_{p2}")
                
    return yogas


def _detect_planetary_war(planets_d1: Dict) -> Dict[str, str]:
    """ASTRO-1: Venus exception added."""
    result: Dict[str, str] = {}
    p_list = [p for p in planets_d1 if p not in ("Sun","Moon","Rahu","Ketu")]
    
    for i in range(len(p_list)):
        for j in range(i + 1, len(p_list)):
            p1, p2 = p_list[i], p_list[j]
            d1, d2 = planets_d1[p1], planets_d1[p2]
            
            deg1 = _planet_abs_degree(d1.get("sign","Aries"), d1.get("degree",0))
            deg2 = _planet_abs_degree(d2.get("sign","Aries"), d2.get("degree",0))
            
            diff = abs(deg1 - deg2)
            if diff > 180: diff = 360 - diff
            
            if diff < 1.0:
                if p1 == "Venus": winner, loser = p1, p2
                elif p2 == "Venus": winner, loser = p2, p1
                else: winner, loser = (p1, p2) if deg1 <= deg2 else (p2, p1)
                
                result[winner], result[loser] = "winner", "loser"
    return result

def _get_nakshatra_dignity(planet: str, nakshatra: str,
                            planet_dignities: Dict[str, str]) -> float:
    base = _FAVORABLE_NAKSHATRA_BASE.get(nakshatra, 1.0)
    if base == 1.0: return 1.0
    lord = _NAKSHATRA_LORD.get(nakshatra, "")
    if not lord: return base
    lord_dig = planet_dignities.get(lord, "")
    if lord_dig == "DEBILITATED": return 1.0
    if lord_dig == "EXALTED": return min(base + 0.10, 1.35)
    if lord_dig == "OWN": return min(base + 0.05, 1.30)
    return base

def _functional_role_modifier(planet: str, house_lords: Dict[str, str], lagna_lord: str, planets_d1: Dict = None) -> float:
    """ASTRO-3 & 7: Lagna Lord Exception & Node Sign Lord mapping."""
    if planet == lagna_lord:
        return 1.20 
        
    if planet in ("Rahu", "Ketu") and planets_d1:
        node_sign = planets_d1.get(planet, {}).get("sign", "")
        if node_sign:
            planet = _SIGN_LORD.get(node_sign, planet)

    kendra   = sum(1 for h in ("1","4","7","10")  if house_lords.get(h) == planet)
    trikona  = sum(1 for h in ("1","5","9")       if house_lords.get(h) == planet)
    dusthana = sum(1 for h in ("6","8","12")      if house_lords.get(h) == planet)
    
    if kendra > 0 and trikona > 0: return 1.20
    if trikona > 0 and dusthana == 0: return 1.10
    if kendra > 0 and dusthana == 0: return 1.05
    if dusthana >= 2 and kendra == 0 and trikona == 0: return 0.80
    if dusthana == 1 and kendra == 0 and trikona == 0: return 0.90
    return 1.0

def _paksha_bala(sun_moon_degrees_apart: float) -> float:
    phase = min(abs(sun_moon_degrees_apart), 360 - abs(sun_moon_degrees_apart))
    return round(0.333 + (min(phase, 180.0) / 180.0) * 0.667, 4)  # FIX-2: classical min=60/180=0.333

def _get_digbala_multiplier(planet: str, house: int) -> float:
    """ASTRO-5: Directional Strength proxy."""
    digbala_map = {"Sun": 10, "Mars": 10, "Moon": 4, "Venus": 4, "Jupiter": 1, "Mercury": 1, "Saturn": 7}
    return 1.15 if digbala_map.get(planet) == house else 1.0


def _rasi_sandhi_mod(degree: float, sign: str) -> float:
    """Avastha degrees reverse based on Even/Odd sign polarity."""
    is_even = _SIGN_NUM.get(sign, 1) % 2 == 0
    if degree < 0:  degree = 0.0
    if degree > 30: degree = 30.0
    
    # Reverse degrees for even signs (Taurus, Cancer, Virgo, etc.)
    check_deg = (30.0 - degree) if is_even else degree
    
    if check_deg < 1.0:   return 0.65  # Mrita / Sandhi
    if check_deg < 3.0:   return 0.80  # Bala
    if check_deg < 6.0:   return 0.90  # Kumara
    if check_deg >= 27.0: return 0.75  # Vriddha
    if check_deg >= 24.0: return 0.95  # Yuva tail-end
    return 1.00 # Peak Yuva


def _compute_eff_strengths(raw_shadbala: Dict, planet_dignities: Dict,
                            planet_retrograde: Dict, war_result: Dict[str, str],
                            vargottama_list: List[str], nakshatras: Dict[str, str],
                            neecha_bhanga_set: Set[str], paksha_bala_val: float,
                            house_lords: Dict[str, str], lagna_lord: str,
                            planet_house: Dict[str, int], cazimi_set: Set[str],
                            planets_d1: Dict,
                            combust_set: Set[str] = None,
                            yoga_set: Set[str] = None) -> Tuple[Dict[str, float], Dict[str, Dict]]:
    """Compute planet effective strengths in a single pass with Nodal Structural Patches.

    Updates (v10.1):
      PATCH-NODAL-1: Eclipse Pen (Grahana Dosha) applied if node is within 10° of Sun.
      PATCH-NODAL-2: Dispositor affliction brake dampens echo inflation.
      PATCH-NODAL-3: Nakshatra Lord House verification applies a 15% penalty if lord is in H6/8/12.
    """
    if combust_set is None:
        combust_set = set()
    _ALL_PLANETS = ("Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu")
    _DIGBALA_HOUSE = {"Sun":10,"Mars":10,"Moon":4,"Venus":4,"Jupiter":1,"Mercury":1,"Saturn":7}
    result: Dict[str, float] = {}
    trace:  Dict[str, Dict]  = {}

    # Pre-compute Sun absolute longitude for eclipse proximity math
    sun_data = planets_d1.get("Sun", {})
    sun_abs = _planet_abs_degree(sun_data.get("sign", "Aries"), sun_data.get("degree", 0)) if sun_data else 0.0

    for p in _ALL_PLANETS:
        min_v        = _PLANET_MIN_SHADBALA.get(p, 300.0)
        raw          = raw_shadbala.get(p, 0.0)
        actual_dig   = planet_dignities.get(p, "")
        is_retro     = planet_retrograde.get(p, False) and p not in ("Sun", "Moon", "Rahu", "Ketu")
        in_nb        = p in neecha_bhanga_set
        in_cazimi    = p in cazimi_set
        in_combust   = p in combust_set and p not in cazimi_set and p not in ("Sun", "Rahu", "Ketu")
        in_vargottama= p in vargottama_list
        war_status   = war_result.get(p, "")
        nak          = nakshatras.get(p, "")
        house        = planet_house.get(p, 0)

        # ── Dignity modifier (with Retrograde Paradox) ──────────────────────
        if is_retro:
            if actual_dig == "EXALTED":
                dig, dig_note = _DIGNITY_MOD["DEBILITATED"], "retro paradox: exalted→0.60"
            elif actual_dig == "DEBILITATED":
                dig, dig_note = _DIGNITY_MOD["EXALTED"],     "retro paradox: debil→1.40"
            else:
                dig = _DIGNITY_MOD.get(actual_dig, 1.0)
                dig_note = f"retro neutral: {actual_dig or 'nil'}→{dig}"
        else:
            if actual_dig == "DEBILITATED" and in_nb:
                dig, dig_note = _DIGNITY_MOD["NEECHA_BHANGA"], "neecha bhanga applied"
            else:
                dig = _DIGNITY_MOD.get(actual_dig, 1.0)
                dig_note = f"{actual_dig or 'neutral'}→{dig}"

        # ── Cazimi boost ─────────────────────────────────────────────────────
        caz_mod = 1.30 if in_cazimi else 1.0

        # ── Combustion modifier ──────────────────────────────────────────────
        _ys = yoga_set or set()
        if in_combust and p == "Mercury" and "BudhaAditya" in _ys:
            # BudhaAditya (same-sign only) grants classical combustion immunity
            comb_mod, comb_note = 1.00, "BudhaAditya yoga: classical immunity→1.0"
        elif in_combust:
            # Dignity-adjusted combustion penalty (ASTRO-9 FIX):
            # OWN/EXALTED sign provides partial residual strength against combustion;
            # neutral placement has no such buffer.
            if actual_dig in ("OWN", "EXALTED"):
                comb_mod, comb_note = 0.85, f"combust {actual_dig.lower()}→0.85"
            else:
                comb_mod, comb_note = 0.75, "combust neutral→0.75"
        else:
            comb_mod, comb_note = 1.0, "not combust"

        # ── Digbala ──────────────────────────────────────────────────────────
        digbala_house = _DIGBALA_HOUSE.get(p, 0)
        digbala_mod   = _get_digbala_multiplier(p, house)

        # ── War modifier ─────────────────────────────────────────────────────
        war_mod = 0.50 if war_status == "loser" else (1.05 if war_status == "winner" else 1.0)

        # ── Vargottama ───────────────────────────────────────────────────────
        if in_vargottama and actual_dig != "DEBILITATED": var_mod = 1.2
        elif in_vargottama and actual_dig == "DEBILITATED": var_mod = 0.85
        else: var_mod = 1.0

        # ── Nakshatra modifier ───────────────────────────────────────────────
        nak_mod  = _get_nakshatra_dignity(p, nak, planet_dignities)

        # ── Paksha bala (Moon only) ──────────────────────────────────────────
        pb_mod   = paksha_bala_val if p == "Moon" else 1.0

        # ── Functional role modifier ─────────────────────────────────────────
        func_mod = _functional_role_modifier(p, house_lords, lagna_lord, planets_d1)

        # ── NODAL PATCH 1: Eclipse Proximity Loop (Grahana Dosha) ───────────
        eclipse_mod = 1.0
        eclipse_note = "clear of solar eclipse boundaries"
        if p in ("Rahu", "Ketu"):
            p_data = planets_d1.get(p, {})
            if p_data:
                p_abs = _planet_abs_degree(p_data.get("sign", "Aries"), p_data.get("degree", 0))
                diff = abs(p_abs - sun_abs)
                if diff > 180: diff = 360 - diff
                if diff <= 10.0:  # Critical 10-degree eclipse orb
                    eclipse_mod = round(max(0.65, 1.0 - (10.0 - diff) * 0.035), 4)
                    eclipse_note = f"Grahana Dosha applied: proximity to Sun is {diff:.2f}°"

        # ── NODAL PATCH 2: Dispositor Affliction Validation ─────────────────
        dispositor_mod = 1.0
        dispositor_note = "dispositor dignity functional"
        if p in ("Rahu", "Ketu"):
            node_sign = planets_d1.get(p, {}).get("sign", "")
            disp = _SIGN_LORD.get(node_sign, "")
            if disp:
                disp_dig   = planet_dignities.get(disp, "")
                disp_comb  = disp in combust_set
                disp_loser = war_result.get(disp, "") == "loser"
                if disp_dig == "DEBILITATED" or disp_comb or disp_loser:
                    dispositor_mod = 0.82  # Apply 18% damping brake to control dispositor echo
                    dispositor_note = f"Dispositor ({disp}) afflicted: structural layout weakened"

        # ── NODAL PATCH 3: Nakshatra Lord House Verification ────────────────
        nak_house_mod = 1.0
        nak_house_note = "nakshatra lord placement clear"
        if p in ("Rahu", "Ketu"):
            lord = _NAKSHATRA_LORD.get(nak, "")
            if lord:
                lord_house = planet_house.get(lord, 0)
                if lord_house in (6, 8, 12):
                    # Nakshatra lord is trapped in a Dusthana, draining operational capacity
                    stringency_map = {6: 0.90, 12: 0.88, 8: 0.85}
                    nak_house_mod = stringency_map.get(lord_house, 0.85)
                    nak_house_note = f"Nakshatra Lord ({lord}) drained in House {lord_house}"

        # ── Final effective strength integration (FIXED: Volatility Dampener) ──
        raw_ratio = (raw / min_v) if raw > 0 else 0.0
        _deg = planets_d1.get(p, {}).get("degree", 15.0)
        sandhi_mod = _rasi_sandhi_mod(_deg, planets_d1.get(p, {}).get("sign", "Aries"))
        
        raw_eff_strength = (raw_ratio * dig * war_mod * var_mod * nak_mod * pb_mod
                        * func_mod * digbala_mod * caz_mod * comb_mod
                        * sandhi_mod * eclipse_mod * dispositor_mod * nak_house_mod) if raw > 0 else 0.0

        # Apply a soft-cap dampener (square root scaling for values over 1.5) to prevent exponential runaway
        if raw_eff_strength > 1.5:
            eff_strength = 1.5 + ((raw_eff_strength - 1.5) ** 0.65)
        else:
            eff_strength = raw_eff_strength

        result[p] = round(eff_strength, 4)

        # ── Trace update (preserves explainability layout downstream) ──────
        trace[p] = {
            "sign":          planets_d1.get(p, {}).get("sign", "?"),
            "house":         house,
            "raw_shadbala":  round(raw, 2),
            "min_v":         min_v,
            "raw_ratio":     round(raw_ratio, 4),
            "dignity":       actual_dig or "neutral",
            "is_retro":      is_retro,
            "in_nb":         in_nb,
            "dig_mod":       round(dig, 2),
            "dig_note":      dig_note,
            "war_status":    war_status or "none",
            "war_mod":       war_mod,
            "vargottama":    in_vargottama,
            "var_mod":       var_mod,
            "nakshatra":     nak or "?",
            "nak_mod":       round(nak_mod, 4),
            "paksha_bala":   round(pb_mod, 4),
            "func_mod":      round(func_mod, 4),
            "digbala_house": digbala_house,
            "digbala_mod":   digbala_mod,
            "cazimi":        in_cazimi,
            "caz_mod":       caz_mod,
            "degree":        round(_deg, 2),
            "sandhi_mod":    round(sandhi_mod, 4),
            "combust":       in_combust,
            "comb_mod":      comb_mod,
            "comb_note":     comb_note,
            "eclipse_mod":   eclipse_mod,
            "eclipse_note":  eclipse_note,
            "dispositor_mod":dispositor_mod,
            "disp_note":     dispositor_note,
            "nak_house_mod":  nak_house_mod,
            "nak_house_note": nak_house_note,
            "eff_strength":  round(eff_strength, 4),
        }

    return result, trace



def _is_vargottama(planet: str, d1_sign: str, d9_chart: Dict) -> bool:
    return d9_chart.get(planet) == d1_sign

def _detect_combust_planets(planets_d1: Dict, sun_abs: float, planet_retrograde: Dict) -> Tuple[List[str], List[str]]:
    """ASTRO-2: Dynamic combustion orb & Cazimi isolation."""
    combust, cazimi = [], []
    for planet, base_orb in _COMBUST_ORB.items():
        p = planets_d1.get(planet)
        if not p: continue
        diff = abs(_planet_abs_degree(p["sign"], p["degree"]) - sun_abs)
        if diff > 180: diff = 360 - diff
        if diff <= 1.0:
            cazimi.append(planet)
            continue
        active_orb = base_orb - 2 if planet_retrograde.get(planet, False) else base_orb
        if diff <= active_orb:
            combust.append(planet)
    return combust, cazimi

def _calc_age(dob_str, current_date_str=None) -> float:
    try:
        dob = date.fromisoformat(dob_str)
        today = date.fromisoformat(current_date_str) if current_date_str else date.today()
        return round((today - dob).days / 365.25, 2)
    except: return 0.0

def _get_active_dasha_lord(dasha_seq, current_age):
    for d in dasha_seq:
        start = d.get("start_age"); end = d.get("end_age")
        if start is None: continue
        if end is None:
            if current_age >= start: return d.get("lord","")
        elif start <= current_age < end:
            return d.get("lord","")
    return ""
