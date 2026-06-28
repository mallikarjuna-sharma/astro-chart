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
    _NEECHA_BHANGA_DATA, _SIGN_NUM, _SIGN_LORD,_JAIMINI_RASI_DRISHTI,
)



_SIGN_ABS: Dict[str, float] = {
    "Aries": 0, "Taurus": 30, "Gemini": 60, "Cancer": 90,
    "Leo": 120, "Virgo": 150, "Libra": 180, "Scorpio": 210,
    "Sagittarius": 240, "Capricorn": 270, "Aquarius": 300, "Pisces": 330,
}

def compute_dignity(planet: str, sign: str, planets_d1: Dict = None) -> str:
    """
    ASTRO-7: Sanivad Rahu, Kujavad Ketu. Nodes act as their dispositor.
    """
    if planet in ("Rahu", "Ketu") and planets_d1:
        # Node adopts the dignity of the lord of the sign it sits in
        dispositor = _SIGN_LORD.get(sign, "")
        if dispositor:
            disp_sign = planets_d1.get(dispositor, {}).get("sign", "")
            if disp_sign:
                return compute_dignity(dispositor, disp_sign) # Recursive check for dispositor dignity

    if _EXALT_SIGN.get(planet) == sign: return "EXALTED"
    if _DEBIL_SIGN.get(planet)  == sign: return "DEBILITATED"
    if sign in _OWN_SIGN.get(planet, []): return "OWN"
    return ""

def _planet_abs_degree(sign, degree):
    return (_SIGN_NUM.get(sign, 1) - 1) * 30 + degree

def _compute_whole_sign_houses(planets_d1: Dict, lagna_sign: str) -> Dict[str, int]:
    """
    BVB Standard: Strict Whole Sign Houses (Rasi Chart).
    Replaces Bhava Chalit. 1st house is strictly the Lagna sign.
    """
    houses = {}
    if not lagna_sign: return houses
    lagna_idx = _SIGN_NUM.get(lagna_sign, 1)
    
    for p, pdata in planets_d1.items():
        sign = pdata.get("sign")
        if not sign: 
            houses[p] = 0
            continue
        p_idx = _SIGN_NUM.get(sign, 1)
        
        # Whole sign math: (Planet Sign - Lagna Sign) % 12 + 1
        house = (p_idx - lagna_idx) % 12 + 1
        houses[p] = house
        
    return houses
def _compute_jaimini_chara_dasha_lengths(planets_d1: Dict) -> Dict[str, int]:
    """Calculates Jaimini Chara Dasha sign lengths per K.N. Rao method.

    AC13 doc: Implements K.N. Rao's Scorpio exception:
      Ketu is Scorpio's Chara Dasha lord only when Ketu is placed in Scorpio;
      otherwise Mars is used. This differs from Sanjay Rath's school (always Mars).
    Length formula: for odd signs, count forward from sign to lord's sign;
      for even signs, count backward. If count == 0, length = 12 years.
    Unit test: For Saturn in Aquarius, Aquarius Chara Dasha = |Aquarius - Saturn_sign| forward.
    """
    lengths = {}
    for sign, num in _SIGN_NUM.items():
        lord = _SIGN_LORD.get(sign)
        # Scorpio/Aquarius dual-lord exception (simplified for standard lord)
        if sign == "Scorpio" and planets_d1.get("Ketu", {}).get("sign"): lord = "Mars"
        if sign == "Aquarius" and planets_d1.get("Rahu", {}).get("sign"): lord = "Saturn"
        
        lord_sign = planets_d1.get(lord, {}).get("sign", "Aries")
        lord_num = _SIGN_NUM.get(lord_sign, 1)
        
        # K.N. Rao Direct/Indirect counting
        if num in (1, 2, 3, 7, 8, 9):  # Forward counting
            diff = (lord_num - num)
        else:                          # Reverse counting
            diff = (num - lord_num)
            
        if diff < 0: diff += 12
        length = diff if diff != 0 else 12
        lengths[sign] = length
    return lengths

def _get_active_chara_dasha_sign(lagna_sign: str, current_age: float, planets_d1: Dict) -> str:
    """Returns the currently active Jaimini Chara Dasha Sign.

    AC6 fix + AC13 doc: Implements K.N. Rao's directional rule:
      - Odd signs (Aries=1, Gemini=3, Leo=5, Libra=7, Sagittarius=9, Aquarius=11):
        sequence proceeds FORWARD zodiacally from lagna sign.
      - Even signs (Taurus=2, Cancer=4, Virgo=6, Scorpio=8, Capricorn=10, Pisces=12):
        sequence proceeds BACKWARD (reverse zodiacal order) from lagna sign.
    Prior code used forward-only, giving wrong active sign for all even-sign lagnas.
    Reference: K.N. Rao, 'Ups and Downs in Career', Chapter 3 (Chara Dasha).
    Unit test: For Scorpio lagna, sequence should go Scorpio→Libra→Virgo→...
    """
    if not lagna_sign: return ""
    lengths = _compute_jaimini_chara_dasha_lengths(planets_d1)
    all_signs = list(_SIGN_NUM.keys())  # canonical zodiacal order Aries→Pisces
    start_idx = all_signs.index(lagna_sign)
    lagna_num = _SIGN_NUM.get(lagna_sign, 1)
    # AC6 fix: odd lagna → forward; even lagna → backward (K.N. Rao direction rule)
    _is_odd_lagna = (lagna_num % 2 == 1)
    if _is_odd_lagna:
        seq = [all_signs[(start_idx + i) % 12] for i in range(12)]
    else:
        seq = [all_signs[(start_idx - i) % 12] for i in range(12)]
    accumulated_age = 0.0
    for sign in seq:
        dasha_len = lengths.get(sign, 0)
        accumulated_age += dasha_len
        if current_age < accumulated_age:
            return sign
    return seq[0]  # Fallback: first sign in sequence

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
    """
    BVB Standard: Strict Whole Sign Parashari Aspects.
    A planet aspects the entire sign, regardless of degrees.
    """
    aspects = {p: [] for p in planet_house}
    for p, h in planet_house.items():
        if h == 0: continue
        # Universal 7th house aspect
        aspects[p].append((h + 6 - 1) % 12 + 1)
        # Special outer planet aspects
        if p == "Mars":
            aspects[p].extend([(h + 4 - 2) % 12 + 1, (h + 8 - 2) % 12 + 1])
        elif p == "Jupiter":
            aspects[p].extend([(h + 5 - 2) % 12 + 1, (h + 9 - 2) % 12 + 1])
        elif p in ("Rahu", "Ketu"):
            # AC12 fix: configurable Rahu/Ketu aspect convention
            # RAHU_KETU_ASPECT_MODE env var: "5th_9th" (default, KP/Parashara),
            # "7th_only" (some Jaimini scholars), "none" (strict nodes = no aspect)
            import os as _os_ac12
            _rk_mode = _os_ac12.getenv("RAHU_KETU_ASPECT_MODE", "5th_9th").lower()
            if _rk_mode == "5th_9th":
                aspects[p].extend([(h + 5 - 2) % 12 + 1, (h + 9 - 2) % 12 + 1])
            elif _rk_mode == "7th_only":
                pass  # universal 7th already added above
            # "none" → only universal 7th; strip it
            elif _rk_mode == "none":
                aspects[p] = []  # nodes cast no aspect in this mode
        elif p == "Saturn":
            aspects[p].extend([(h + 3 - 2) % 12 + 1, (h + 10 - 2) % 12 + 1])
            
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
                           planet_house: Dict[str, int],
                           moon_house: int = 0) -> Set[str]:
    """Parashari Neecha Bhanga: dispositor/exalt-lord in kendra from Lagna OR from Moon (Chandra Lagna).
    Gap-3 fix: classical rules require both Lagna-kendra AND Moon-kendra checks.
    moon_house: the house number of Moon from Lagna (used to compute Chandra Lagna kendras).
    """
    cancelled: Set[str] = set()
    # Kendras from Moon (Chandra Lagna): houses that are 1,4,7,10 relative to Moon's house.
    if moon_house:
        _moon_kendra = frozenset(((moon_house - 1 + k) % 12 + 1) for k in (0, 3, 6, 9))
    else:
        _moon_kendra = frozenset()

    for planet, dignity in planet_dignities.items():
        if dignity != "DEBILITATED": continue
        nb = _NEECHA_BHANGA_DATA.get(planet, {})
        if not nb: continue
        sl, el = nb.get("debil_sign_lord", ""), nb.get("exalt_lord", "")
        sl_h  = planet_house.get(sl, 0)
        el_h  = planet_house.get(el, 0) if el and el != planet else 0
        # Lagna-kendra check (existing rule)
        if sl and sl_h in _KENDRA_HOUSES:
            cancelled.add(planet)
        elif el and el != planet and el_h in _KENDRA_HOUSES:
            cancelled.add(planet)
        elif planet_house.get(planet, 0) in _KENDRA_HOUSES and sl_h in _KT_HOUSES:
            cancelled.add(planet)
        # Chandra Lagna kendra check (Gap-3: Moon-based kendra)
        elif _moon_kendra and sl and sl_h in _moon_kendra:
            cancelled.add(planet)
        elif _moon_kendra and el and el != planet and el_h in _moon_kendra:
            cancelled.add(planet)
        # AC3 fix rule (a): exaltation lord aspects the debilitated planet
        elif el and el != planet:
            _el_aspects = set(_get_planetary_aspects({p: h for p, h in planet_house.items()}).get(el, []))
            if planet_house.get(planet, 0) in _el_aspects:
                cancelled.add(planet)

    # AC3 fix rule (b): mutual debilitation cancellation
    # If planet A is debilitated in B's exaltation sign AND B is debilitated in A's exaltation sign simultaneously
    _deb_planets = [p for p, d in planet_dignities.items() if d == 'DEBILITATED']
    for i, p1 in enumerate(_deb_planets):
        for p2 in _deb_planets[i+1:]:
            nb1 = _NEECHA_BHANGA_DATA.get(p1, {})
            nb2 = _NEECHA_BHANGA_DATA.get(p2, {})
            # Check if p1's exaltation lord is p2 AND p2's exaltation lord is p1
            if nb1.get('exalt_lord') == p2 and nb2.get('exalt_lord') == p1:
                cancelled.add(p1)
                cancelled.add(p2)
    return cancelled


def _detect_yogas(planets_d1: Dict, planet_house: Dict,
                  planet_dignities: Dict = None,
                  combust_set: Set[str] = None,
                  house_lords: Dict = None) -> List[str]:
    if planet_dignities is None: planet_dignities = {}
    if combust_set is None: combust_set = set()
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
            # Rasi Parivartana (sign exchange)
            if s2 in _OWN_SIGN.get(p1,[]) and s1 in _OWN_SIGN.get(p2,[]):
                yogas.append(f"Parivartana_{p1}_{p2}")

    # Gap-5: Nakshatra Parivartana (KP star-lord exchange)
    # Planet A in nakshatra whose lord is Planet B, AND Planet B in nakshatra whose lord is Planet A.
    _planet_naks: Dict[str, str] = {}
    for p, pd in planets_d1.items():
        sign, deg = pd.get("sign", ""), pd.get("degree", 0)
        if sign:
            abs_deg = _planet_abs_degree(sign, deg)
            _planet_naks[p] = get_nakshatra_from_longitude(abs_deg)

    _checked_nak: Set[Tuple] = set()
    for p1, nak1 in _planet_naks.items():
        lord1 = _NAKSHATRA_LORD.get(nak1, "")
        if not lord1 or lord1 == p1: continue
        for p2, nak2 in _planet_naks.items():
            if p2 == p1: continue
            pair_n = tuple(sorted([p1, p2]))
            if pair_n in _checked_nak: continue
            lord2 = _NAKSHATRA_LORD.get(nak2, "")
            # Exchange: lord of p1's star = p2, lord of p2's star = p1
            if lord1 == p2 and lord2 == p1:
                _checked_nak.add(pair_n)
                yogas.append(f"NakParivartana_{p1}_{p2}")

    # --- BVB Fix: Amala Yoga (Spotless Career) ---
    # Benefic (Jup, Ven, strong Moon, Mercury) in the 10th from Lagna or Moon
    moon_h10 = (planet_house.get("Moon", 1) + 9 - 1) % 12 + 1
    benefics = ["Jupiter", "Venus", "Mercury"]
    for b in benefics:
        b_h = planet_house.get(b, 0)
        if b_h == 10 or b_h == moon_h10:
            if b not in combust_set: # Must not be combust to give Amala results
                yogas.append(f"Amala_{b}")

    # --- BVB Fix: Generalized Raja Yogas (Dharma-Karma Adhipati) ---
    # Conjunction of a Kendra Lord (1,4,7,10) and a Trikona Lord (1,5,9)
    if house_lords:
        kendra_lords = {house_lords.get(str(h)) for h in (1,4,7,10) if house_lords.get(str(h))}
        trikona_lords = {house_lords.get(str(h)) for h in (1,5,9) if house_lords.get(str(h))}
        
        for p1 in kendra_lords:
            for p2 in trikona_lords:
                if p1 == p2: continue # Exclude planets that own both (e.g., Yogakarakas)
                if planets_d1.get(p1, {}).get("sign") == planets_d1.get(p2, {}).get("sign"):
                    yogas.append(f"RajaYoga_{p1}_{p2}")

    return yogas


def _detect_planetary_war(planets_d1: Dict) -> Dict[str, str]:
    """
    Detects Planetary War (Graha Yuddha) within a 1-degree orb boundary.
    Differentiates between friendly defeats and enemy structural strikes.
    """
    # Classical Natural Relationships Map (Friends list for each planet)
    _NATURAL_FRIENDS = {
        "Mars": ["Sun", "Moon", "Jupiter"],
        "Mercury": ["Sun", "Venus"],
        "Jupiter": ["Sun", "Moon", "Mars"],
        "Venus": ["Mercury", "Saturn"],
        "Saturn": ["Mercury", "Venus"]
    }
    
    result: Dict[str, str] = {}
    p_list = [p for p in planets_d1 if p not in ("Sun", "Moon", "Rahu", "Ketu")]
    
    for i in range(len(p_list)):
        for j in range(i + 1, len(p_list)):
            p1, p2 = p_list[i], p_list[j]
            d1, d2 = planets_d1[p1], planets_d1[p2]
            deg1 = _planet_abs_degree(d1.get("sign", "Aries"), d1.get("degree", 0))
            deg2 = _planet_abs_degree(d2.get("sign", "Aries"), d2.get("degree", 0))
            
            diff = abs(deg1 - deg2)
            if diff > 180: diff = 360 - diff
            
            if diff < 1.0:
                # Venus always wins planetary war by default classical decree
                if p1 == "Venus": winner, loser = p1, p2
                elif p2 == "Venus": winner, loser = p2, p1
                else: winner, loser = (p1, p2) if deg1 <= deg2 else (p2, p1)
                
                # Context-Aware Relationship Grading: Check if conqueror is an enemy
                is_friendly_conquest = winner in _NATURAL_FRIENDS.get(loser, [])
                
                result[winner] = "winner"
                result[loser] = "loser_friendly" if is_friendly_conquest else "loser_bitter"
                
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
    """ASTRO-3, 7 & 10: Lagna Lord Exception, Node Sign Lord mapping, and Moolatrikona mixed-lordship resolution."""
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
    
    # ── MIXED LORDSHIP: Moolatrikona Dominance (Gap 5 Fix) ───────────────────
    # If a planet rules both an auspicious house and a dusthana, resolve its functional
    # benefic/malefic status by finding exactly which house its Moolatrikona sign occupies.
    if (trikona > 0 and dusthana > 0) or (kendra > 0 and dusthana > 0):
        # 1. Deduce Lagna sign mathematically from house_lords to avoid breaking upstream signatures
        l1, l2 = house_lords.get("1"), house_lords.get("2")
        lagna_sign = ""
        if l1 == "Mars" and l2 == "Venus": lagna_sign = "Aries"
        elif l1 == "Venus" and l2 == "Mercury": lagna_sign = "Taurus"
        elif l1 == "Mercury" and l2 == "Moon": lagna_sign = "Gemini"
        elif l1 == "Moon" and l2 == "Sun": lagna_sign = "Cancer"
        elif l1 == "Sun" and l2 == "Mercury": lagna_sign = "Leo"
        elif l1 == "Mercury" and l2 == "Venus": lagna_sign = "Virgo"
        elif l1 == "Venus" and l2 == "Mars": lagna_sign = "Libra"
        elif l1 == "Mars" and l2 == "Jupiter": lagna_sign = "Scorpio"
        elif l1 == "Jupiter" and l2 == "Saturn": lagna_sign = "Sagittarius"
        elif l1 == "Saturn" and l2 == "Saturn": lagna_sign = "Capricorn"
        elif l1 == "Saturn" and l2 == "Jupiter": lagna_sign = "Aquarius"
        elif l1 == "Jupiter" and l2 == "Mars": lagna_sign = "Pisces"

        _MOOLATRIKONA_SIGN = {
            "Sun": "Leo", "Moon": "Taurus", "Mars": "Aries",
            "Mercury": "Virgo", "Jupiter": "Sagittarius",
            "Venus": "Libra", "Saturn": "Aquarius"
        }

        mt_sign = _MOOLATRIKONA_SIGN.get(planet)
        if lagna_sign and mt_sign:
            lagna_idx = _SIGN_NUM.get(lagna_sign, 1)
            mt_idx = _SIGN_NUM.get(mt_sign, 1)
            mt_house = (mt_idx - lagna_idx) % 12 + 1
            
            # Moolatrikona rules apply:
            if mt_house in (1, 5, 9):
                return 1.05  # MT is Trikona -> Retains positive functional benefic status
            elif mt_house in (1, 4, 7, 10):
                return 1.02  # MT is Kendra -> Marginally positive despite dusthana
            elif mt_house in (6, 8, 12):
                return 0.90  # MT is Dusthana -> Dusthana dominates, planet acts as functional malefic
    
    # Standard Parashari fallback if MT dominance resolution fails to trigger
    if trikona > 0 and dusthana > 0: return 1.05 
    if kendra > 0 and dusthana > 0: return 0.95  
    
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

from .constants import _JAIMINI_RASI_DRISHTI


def _compute_eff_strengths(raw_shadbala: Dict, planet_dignities: Dict,
                            planet_retrograde: Dict, war_result: Dict[str, str],
                            vargottama_list: List[str], nakshatras: Dict[str, str],
                            neecha_bhanga_set: Set[str], paksha_bala_val: float,
                            house_lords: Dict[str, str], lagna_lord: str,
                            planet_house: Dict[str, int], cazimi_set: Set[str],
                            planets_d1: Dict,
                            combust_set: Set[str] = None,
                            yoga_set: Set[str] = None,
                            d9_chart: Dict = None) -> Tuple[Dict[str, float], Dict[str, Dict]]:
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
            # GAP-3 FIX: Gradient combustion — linear ease-out over outer 30% of orb.
            # A planet just inside the orb edge gets a much milder penalty than one
            # deep inside the orb, eliminating the binary scoring cliff.
            _orb      = _COMBUST_ORB.get(p, 12)
            _sun_abs  = sun_abs  # already in scope from caller
            _pdata    = planets_d1.get(p, {})
            _p_abs    = _planet_abs_degree(_pdata.get("sign","Aries"), _pdata.get("degree",0))
            _dist     = abs(_p_abs - _sun_abs)
            if _dist > 180: _dist = 360 - _dist
            # Full penalty zone: dist < 70% of orb; gradient zone: 70%–100% of orb
            _full_zone = 0.70 * _orb
            if actual_dig in ("OWN", "EXALTED"):
                _full_pen, _edge_pen = 0.85, 0.92
            else:
                _full_pen, _edge_pen = 0.75, 0.90
            if _dist <= _full_zone:
                comb_mod = _full_pen
            else:
                # Linear interpolation: _full_pen at _full_zone → _edge_pen at _orb
                _t = (_dist - _full_zone) / (0.30 * _orb)
                comb_mod = _full_pen + _t * (_edge_pen - _full_pen)
            comb_note = f"combust_gradient dist={_dist:.1f} orb={_orb}→{comb_mod:.3f}"
        else:
            comb_mod, comb_note = 1.0, "not combust"

        # ── Digbala ──────────────────────────────────────────────────────────
        digbala_house = _DIGBALA_HOUSE.get(p, 0)
        digbala_mod   = _get_digbala_multiplier(p, house)

        # ── War modifier ─────────────────────────────────────────────────────
        # Context-aware war status evaluation
        if war_status == "winner":
            war_mod = 1.05
        elif war_status == "loser_friendly":
            war_mod = 0.72  # Mild structural friction if defeated by a natural friend
        elif war_status == "loser_bitter":
            war_mod = 0.45  # Intense degradation of capabilities if defeated by an enemy
        else:
            war_mod = 1.0

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
        nak_house_note = "nakshatra lord house: neutral"
        if nak:
            from .constants import _NAKSHATRA_LORD as _NL
            nak_lord = _NL.get(nak, "")
            if nak_lord:
                nak_lord_house = planet_house.get(nak_lord, 0)
                if nak_lord_house in (6, 8, 12):
                    nak_house_mod = 0.85  # 15% penalty — dusthana positioning weakens channel
                    nak_house_note = f"Nak lord {nak_lord} in H{nak_lord_house} (dusthana: -15%)"
                elif nak_lord_house in (1, 4, 7, 10):
                    nak_house_mod = 1.08  # 8% kendra bonus — angular positioning strengthens
                    nak_house_note = f"Nak lord {nak_lord} in H{nak_lord_house} (kendra: +8%)"

        # ── Final effective strength ──────────────────────────────────────────
        base = (raw / min_v) if min_v > 0 else 1.0
        eff = (base
               * dig * caz_mod * comb_mod * digbala_mod * war_mod
               * var_mod * nak_mod * pb_mod * func_mod
               * eclipse_mod * dispositor_mod * nak_house_mod)
        eff = max(0.05, round(eff, 4))  # floor at 0.05 (no planet is fully inert)

        result[p] = eff
        trace[p] = {
            "base_shadbala_ratio": round(base, 4),
            "dignity_mod":         round(dig, 4),
            "cazimi_mod":          round(caz_mod, 4),
            "combustion_mod":      round(comb_mod, 4),
            "digbala_mod":         round(digbala_mod, 4),
            "war_mod":             round(war_mod, 4),
            "vargottama_mod":      round(var_mod, 4),
            "nakshatra_mod":       round(nak_mod, 4),
            "paksha_bala_mod":     round(pb_mod, 4),
            "functional_role_mod": round(func_mod, 4),
            "eclipse_mod":         round(eclipse_mod, 4),
            "dispositor_mod":      round(dispositor_mod, 4),
            "nak_house_mod":       round(nak_house_mod, 4),
            "eff_strength":        eff,
            "dignity":             actual_dig,
            "notes": {
                "dignity":         dig_note,
                "combustion":      comb_note,
                "eclipse":         eclipse_note,
                "dispositor":      dispositor_note,
                "nak_house":       nak_house_note,
            },
        }

    return result, trace


def _is_vargottama(planet: str, d1_sign: str, d9_chart: Dict) -> bool:
    """A planet is Vargottama if it occupies the same sign in D1 and D9."""
    d9_sign = d9_chart.get(planet, "")
    return bool(d1_sign) and d1_sign == d9_sign


def _get_active_dasha_lord(dasha_sequence: List[Dict], current_age: float) -> str:
    """Return the current Mahadasha lord based on the native's age."""
    for d in dasha_sequence:
        start = float(d.get("start_age", 0) or 0)
        end   = float(d.get("end_age",   99) or 99)
        if start <= current_age < end:
            return d.get("lord", "") or d.get("md_planet", "")
    return ""


def _detect_combust_planets(
    planets_d1: Dict,
    sun_abs: float = None,
    planet_retrograde: Dict = None,
) -> tuple:
    """Detect planets within combustion orb of the Sun (classical Diptamsha).

    Returns (combust_list, cazimi_list).  Cazimi = within 1 degree of Sun.
    Retrograde arg accepted for signature compatibility.
    """
    from .constants import _COMBUST_ORB
    combust: List[str] = []
    cazimi: List[str]  = []
    sun_data = planets_d1.get("Sun", {})
    if not sun_data:
        return combust, cazimi
    if sun_abs is None:
        sun_abs = _planet_abs_degree(sun_data.get("sign", "Aries"), sun_data.get("degree", 0))
    for planet, orb in _COMBUST_ORB.items():
        p_data = planets_d1.get(planet, {})
        if not p_data:
            continue
        p_abs = _planet_abs_degree(p_data.get("sign", "Aries"), p_data.get("degree", 0))
        diff  = abs(p_abs - sun_abs)
        if diff > 180: diff = 360 - diff
        if diff <= 1.0:
            cazimi.append(planet)
        elif diff <= orb:
            combust.append(planet)
    return combust, cazimi


def _calc_age(birth_date_str: str, current_date_str: str = "") -> float:
    """Calculate age in years from birth date string (ISO format: YYYY-MM-DD)."""
    from datetime import date
    try:
        bd = date.fromisoformat(str(birth_date_str)[:10])
        if current_date_str:
            today = date.fromisoformat(str(current_date_str)[:10])
        else:
            today = date.today()
        return round((today - bd).days / 365.25, 2)
    except Exception:
        return 0.0


def _detect_jaimini_raj_yogas(
    ak: str,
    amk: str,
    planet_house_or_d1: object,
    planet_dignities: Dict[str, str] = None,
) -> List[str]:
    """Detect Jaimini Raj Yogas based on AK/AmK positions and dignities.

    Key Jaimini Raj Yogas:
    • AK and AmK in kendra to each other → Raja Yoga
    • AK in its own sign/exaltation in Karakamsha → strong dharmic mandate
    • Exalted AmK → career raja yoga
    """
    yogas: List[str] = []
    # planet_house_or_d1 can be:
    #   (a) Dict[str,int]  — maps planet → house number  (legacy callers)
    #   (b) Dict[str,dict] — raw planets_d1              (field_methods callers)
    _ph_arg = planet_house_or_d1 or {}
    _sample = next(iter(_ph_arg.values()), None) if _ph_arg else None
    if isinstance(_sample, dict):
        # planets_d1: extract house by sign position would require lagna; fall back gracefully
        planet_house_map: Dict[str, int] = {
            p: v.get("house", 0) for p, v in _ph_arg.items() if isinstance(v, dict)
        }
    else:
        planet_house_map = _ph_arg  # type: ignore[assignment]

    ak_h  = planet_house_map.get(ak, 0)
    amk_h = planet_house_map.get(amk, 0)

    if ak_h and amk_h:
        diff = abs(ak_h - amk_h) % 12
        if diff in (0, 3, 6, 9):
            yogas.append("Jaimini_AK_AMK_Kendra_Raja_Yoga")
        if diff in (0, 4, 8):
            yogas.append("Jaimini_AK_AMK_Trikona_Dharma_Yoga")

    _digs = planet_dignities or {}
    if ak and _digs.get(ak, "") in ("EXALTED", "OWN"):
        yogas.append(f"Jaimini_Exalted_AK_{ak}")
    if amk and _digs.get(amk, "") in ("EXALTED", "OWN"):
        yogas.append(f"Jaimini_Exalted_AMK_{amk}")

    return yogas


def _compute_arudha_pada(
    house_num: int,
    lagna_sign: str,
    planets_d1: Dict,
) -> str:
    """Compute the Arudha Pada sign of a given house using classical Parashara method.

    Args:
        house_num:   House number (1-12) whose Arudha is needed.
        lagna_sign:  Lagna (Ascendant) sign name, e.g. "Aries".
        planets_d1:  D1 planet dict {planet: {"sign": ..., "degree": ...}}.

    Returns:
        The sign name of the Arudha Pada (e.g. "Gemini"), or "" on failure.

    Classical method:
    1. Find the lord of the target house (sign lord of Lagna + house_num - 1).
    2. Count houses from target house to lord's house.
    3. Count same distance from lord's house → Arudha house.
    4. If Arudha == target house or its 7th, shift by +10 signs.
    """
    from .constants import _SIGN_LORD, _SIGN_NUM
    # Signs in zodiacal order (derived from _SIGN_NUM)
    _SIGNS = sorted(_SIGN_NUM, key=_SIGN_NUM.__getitem__)

    # House sign = lagna_sign rotated by (house_num - 1)
    try:
        lagna_idx = _SIGNS.index(lagna_sign)
    except ValueError:
        return ""
    house_sign = _SIGNS[(lagna_idx + house_num - 1) % 12]
    lord = _SIGN_LORD.get(house_sign, "")
    if not lord:
        return ""

    # Find lord's house from D1 data
    lord_data = planets_d1.get(lord, {})
    lord_sign = lord_data.get("sign", "") if isinstance(lord_data, dict) else ""
    if not lord_sign:
        return ""
    try:
        lord_sign_idx = _SIGNS.index(lord_sign)
    except ValueError:
        return ""
    # House number of lord (1-based, relative to lagna)
    lord_house = (lord_sign_idx - lagna_idx) % 12 + 1

    steps  = (lord_house - house_num) % 12
    arudha_house = (lord_house + steps - 1) % 12 + 1

    # Classical correction (iterative): Arudha cannot be the house itself or its 7th.
    # Loop covers the rare second-order case where the +10 shift itself lands on
    # house_num or its 7th again (BV Raman / Parashara school).
    for _ in range(2):
        seventh = (house_num + 5) % 12 + 1
        if arudha_house == house_num:
            arudha_house = (house_num + 9) % 12 + 1
        elif arudha_house == seventh:
            arudha_house = (seventh + 9) % 12 + 1
        else:
            break

    return _SIGNS[(lagna_idx + arudha_house - 1) % 12]


def _compute_bvb_7_karakas(planets_d1: Dict) -> tuple:
    """Compute the top-2 Chara Karakas (AK and AmK) from D1 longitudes.

    Classical rule: sort the 7 planets (excluding Rahu/Ketu) by their degree
    within the sign in descending order. Highest degree = AK, next = AmK.
    Retrograde planets use (30 - degree) for the sorting — classical exception.
    """
    _KARAKA_PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")
    degrees: Dict[str, float] = {}
    for p in _KARAKA_PLANETS:
        d = planets_d1.get(p, {})
        if not d:
            continue
        deg = float(d.get("degree", 0) or 0)
        if d.get("retrograde", False):
            deg = 30.0 - deg  # retro paradox for karaka ordering
        degrees[p] = deg

    if not degrees:
        return "", ""
    sorted_p = sorted(degrees.items(), key=lambda x: -x[1])
    # AC2 fix: return all 7 karakas (AK through DK)
    _KARAKA_NAMES = ["AK", "AmK", "BK", "MK", "PiK", "PuK", "GK", "DK"]
    all_karakas = {_KARAKA_NAMES[i]: p for i, (p, _) in enumerate(sorted_p) if i < len(_KARAKA_NAMES)}
    ak  = all_karakas.get("AK", "")
    amk = all_karakas.get("AmK", "")
    # Store full karaka dict as module-level for callers that need it
    _compute_bvb_7_karakas._last_all_karakas = all_karakas
    return ak, amk


def _compute_jaimini_argala(reference_house: int, planet_house: Dict[str, int]) -> List[str]:
    """Compute Argala (interference/support) planets for a reference house.

    Argala houses: 2nd, 4th, 11th from reference → support.
    Obstruction: 12th, 10th, 3rd from reference → virodha argala.
    Returns list of planets causing argala.
    """
    argala: List[str] = []
    # Houses are stored as 1-based numbers, so the 2nd/4th/11th from the
    # reference house map to offsets 1, 3, and 10 respectively.
    _ARGALA_OFFSETS = {1, 3, 10}
    for planet, house in planet_house.items():
        if not house:
            continue
        offset = (house - reference_house) % 12
        if offset in _ARGALA_OFFSETS:
            argala.append(planet)
    return argala


def _compute_varga_aspect_dignity(planet: str, varga_house_map: Dict[str, int]) -> float:
    """Evaluate planet's dignity in a varga (divisional) chart.

    Returns a multiplier based on the planet's house position in the varga chart.
    Kendra placement = 1.10, trikona = 1.08, dusthana = 0.85, other = 1.0.
    """
    house = varga_house_map.get(planet, 0)
    if not house:
        return 1.0
    if house in (1, 4, 7, 10):   # kendra
        return 1.10
    if house in (5, 9):           # trikona (excluding 1st, already in kendra)
        return 1.08
    if house in (6, 8, 12):       # dusthana
        return 0.85
    return 1.0


def _evaluate_12h_intellectual_strength(
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    house_lords: Dict[str, str],
) -> float:
    """Evaluate H12 intellectual strength for research/foreign/spiritual careers.

    Returns average effective strength of planets placed in H12.
    H12 stelliums with strong planets indicate research, abroad study, hospital careers.
    """
    h12_planets = [p for p, h in planet_house.items() if h == 12]
    if not h12_planets:
        h12_lord = house_lords.get("12", "")
        if h12_lord:
            return round(eff_strengths.get(h12_lord, 0.0), 4)
        return 0.0
    avg_str = sum(eff_strengths.get(p, 0.0) for p in h12_planets) / len(h12_planets)
    return round(avg_str, 4)
