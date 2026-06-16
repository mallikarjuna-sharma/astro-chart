"""JyotishAI — Gap-boost scoring helpers (all _*_bonus / _*_penalty functions)."""
import math as _math
from typing import Dict, List, Tuple, Set, Any, Optional

from .payload import NatalPayloadV2, logger
from .constants import (
    _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES,
    _SIGN_LORD, _SIGN_NUM, _NODAL_DEFAULT_VIRUPAS,
    _D24_ACADEMIC_KW, _H12_FIELDS, _H6_FIELDS, _H9_FIELDS, _H5_FIELDS,
    _FRONTIER_KW, _TRADITIONAL_KW, _H9_STELLIUM_KW, _H12_STELLIUM_KW,
    _FUNCTIONAL_TRIKONA_FALLBACK, _ALL_PLANETS_SET, _DUSTHANA_EXEMPT_KW,
    _MAHESHWARA_DOMAIN_KW, _STREAM_MAP, _KARAKAMSHA_OCCUPANT_KW,
)
from .astro import _get_planetary_aspects, _get_planetary_aspects_weighted, _drishti_bala

_ALL_PLANETS: Tuple = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")


# ===========================================================================
# GAP HELPER CONSTANTS
# ===========================================================================
DASHA_KEYWORDS: Dict[str, List[str]] = {
    "Sun":     ["civil services","leadership","medicine","physics","administration","government","energy","political"],
    "Moon":    ["psychology","nursing","hospitality","social work","counseling","public health","ecology","sociology","agriculture","food","nutrition","marine","aquaculture"],
    "Mars":    ["defence","surgery","engineering","military","police","metallurgy","civil engineering","sports"],
    "Mercury": ["data science","computer","artificial intelligence","communication","journalism","statistics","research","mathematics","accounting"],
    "Jupiter": ["law","education","philosophy","economics","teaching","management","theology","international"],
    "Venus":   ["arts","design","fashion","music","architecture","performing arts","fine arts","luxury"],
    "Saturn":  ["metallurgy","mining","civil","industrial","petroleum","materials science","environmental","construction","manufacturing"],
    "Rahu":    ["artificial intelligence","cybersecurity","space","biotechnology","forensic","nuclear","robotics","information technology","foreign","unconventional","machine learning","data science","medicine","hospital"],
    "Ketu":    ["research","philosophy","alternative medicine","ayurveda","spiritual","occult","investigation","archaeology"],
}
_KARAKAMSHA_CO_LORD: Dict[str, str] = {"Aquarius":"Rahu","Scorpio":"Ketu","Pisces":"Ketu"}
_D24_ACADEMIC_KW = ["research","medicine","science","mathematics","biology","chemistry",
                    "physics","philosophy","education","academia","law","psychology",
                    "biotechnology","statistics","ayurveda","pharmacy"]
_H12_FIELDS = ["research","forensic","hospital","medicine","psychology","spiritual","alternative","international","investigation","hidden"]
_H6_FIELDS  = ["medicine","defence","military","nursing","service","public health"]
_H9_FIELDS  = ["law","philosophy","international","education","research","academia","theology","journalism"]
_H5_FIELDS  = ["research","mathematics","science","medicine","education","physics","statistics","data","artificial intelligence","philosophy","psychology","computer","analytics","chemistry","biology","biotechnology","law"]
_FRONTIER_KW    = ["artificial intelligence","cybersecurity","space","robotics","nuclear","forensic","biotechnology","astrophysics","genetic","performing arts","investigative","journalism","biomedical","environmental science"]
_TRADITIONAL_KW = ["commerce","accounting","education teaching","civil services","law llb","medicine mbbs","business management","agriculture"]
_H9_STELLIUM_KW = ["philosophy","law","research","academia","international","medicine","higher","education","space","religion","theology","journalism","science","psychology","sociology"]
_H12_STELLIUM_KW= ["research","forensic","hospital","medicine","psychology","spiritual","alternative","investigat"]

_YOGAKARAKA_PLANET: Dict[str, str] = {
    "Taurus":"Saturn","Libra":"Saturn","Cancer":"Mars","Leo":"Mars",
    "Capricorn":"Venus","Aquarius":"Venus",
}
_FUNCTIONAL_TRIKONA_FALLBACK = {
    "Aries":"Sun","Gemini":"Venus","Scorpio":"Moon","Sagittarius":"Sun","Pisces":"Moon","Virgo":"Venus"
}

_AK_PLANET_DOMAIN_KW: Dict[str, List[str]] = {
    "Jupiter": ["philosophy","law","education","theology","research","management",
                "international","teaching","economics","higher","academia","religion"],
    "Mercury": ["communication","media","journalism","data","analytics","computer",
                "statistics","commerce","accounting","mathematics","writing","it"],
    "Mars":    ["engineering","surgery","defence","military","medicine","technical",
                "mechanical","metallurgy","mining","police","sports","emergency"],
    "Saturn":  ["law","administration","civil services","architecture","mining",
                "construction","agriculture","infrastructure","government",
                "materials","metallurg","geological","earth science"],
    "Venus":   ["arts","design","music","fashion","finance","architecture",
                "performing arts","fine arts","luxury","film","photography"],
    "Moon":    ["psychology","nursing","social","education","hospitality",
                "food","public","caretaking","environment","counselling"],
    "Sun":     ["governance","leadership","public policy","civil services",
                "medicine","management","politics","administration"],
    "Ketu":    ["research","spiritual","occult","philosophy","alternative medicine",
                "ayurveda","forensic","investigation","archaeology"],
    "Rahu":    ["technology","foreign","innovation","data science","media","cinema",
                "politics","mass communication","artificial intelligence"],
}

_MAHESHWARA_DOMAIN_KW: Dict[str, List[str]] = {
    # Maheshwara (Jaimini) governs longevity, transformation, and institutional peaks.
    # Jupiter Maheshwara → education, law, philosophy, expansion.
    # Saturn Maheshwara → engineering, materials, construction, agriculture, mining.
    # Venus Maheshwara → arts, design, architecture, luxury.
    "Jupiter": ["law","education","philosophy","medicine","economics","management","research","international","theology"],
    "Mercury": ["data science","computer","mathematics","accounting","statistics","communication","artificial intelligence"],
    "Venus":   ["arts","design","fashion","music","architecture","fine arts","performing arts","real estate","luxury"],
    "Saturn":  ["engineering","mining","civil","metallurgy","agriculture","industrial","petroleum","materials","construction","environment"],
    "Mars":    ["defence","surgery","military","police","sports","mechanical","fire"],
    "Sun":     ["civil services","administration","medicine","government","leadership","physics","energy"],
    "Moon":    ["nursing","psychology","social work","public health","ecology","hospitality","counseling"],
    "Rahu":    ["artificial intelligence","cybersecurity","biotechnology","space","robotics","forensic"],
    "Ketu":    ["research","ayurveda","spiritual","philosophy","archaeology","investigation"],
}

from .constants import _PLANET_MIN_SHADBALA
from .affinity import _GENERIC_9P_WEIGHTS
from .astro import _get_active_dasha_lord, _paksha_bala


def _maheshwara_lord_bonus(label: str, maheshwara_lord: str, affinity: Dict[str, float]) -> float:
    """FIX-6: Maheshwara lord (Jaimini special lord) now contributes to branch scoring.
    Maheshwara represents the peak institutional authority phase of the native's career.
    When a branch aligns with the Maheshwara lord's domain keywords, it receives a bonus."""
    if not maheshwara_lord:
        return 0.0
    kws = _MAHESHWARA_DOMAIN_KW.get(maheshwara_lord, [])
    if not any(kw in label.lower() for kw in kws):
        return 0.0
    w = affinity.get(maheshwara_lord, 0.0)
    if   w >= 0.25: return 0.07
    if   w >= 0.15: return 0.04
    if   w >= 0.08: return 0.02
    return 0.0

# ── Gap-boost helper constants (extracted from original monolith) ──────────
_YOGA_DOMAIN_KW: Dict[str, List[str]] = {
    "Saraswati":    ["education","research","mathematics","science","law","literature","arts","philosophy","economics","music","design","management","statistics","medicine","data","commerce","computer","analytics"],
    "GajaKesari":   ["law","education","philosophy","management","public policy","policy","economics","medicine","psychology","international","governance"],
    "BudhaAditya":  ["research","computer","artificial intelligence","data science","medicine","communication","statistics","mathematics","journalism","analytics","science","space"],
    "Shasha":       ["engineering","mining","civil","metallurgy","agriculture","industrial","environmental","materials","petroleum","construction","mechanical"],
    "Hamsa":        ["law","education","philosophy","medicine","ayurveda","international","economics","management","governance","theology","research"],
    "Ruchaka":      ["defence","surgery","engineering","military","police","sports","metallurgy","civil engineering","aerospace","mechanical","mining"],
    "Bhadra":       ["data science","computer","mathematics","accounting","communication","law","statistics","research","artificial intelligence","journalism"],
    "Malavya":      ["arts","design","fashion","music","performing arts","fine arts","architecture","luxury","media","mass communication"],
    "ChandraMangala":["commerce","finance","business","economics","banking","trading","entrepreneurship"],
}

_AMK_HOUSE_KW: Dict[int, List[str]] = {
    5:  ["research","mathematics","science","philosophy","statistics","education","medicine","data","computer","artificial intelligence","analytics"],
    9:  ["law","philosophy","international","education","research","medicine","higher","journalism","management","governance","theology","space"],
    10: ["engineering","commerce","business","civil services","management","public policy","governance","medicine","administration"],
    4:  ["education","teaching","public","psychology","social","nursing"],
    1:  ["defence","sports","entrepreneurship","innovation","surgery"],
}

_YOGA_BONUS_AMT: Dict[str, float] = {
    "Hamsa":          0.09,   # Jupiter Mahapurusha → philosophy/law/education
    "Ruchaka":        0.10,   # Mars Mahapurusha    → engineering/military/surgery
    "Shasha":         0.09,   # Saturn Mahapurusha  → civil services/law/admin
    "GajaKesari":     0.08,   # Jupiter-Moon kendra → public/philosophy
    "Saraswati":      0.09,   # Venus+Merc+Jup kendra → arts/literature/research
    "Malavya":        0.08,   # Venus Mahapurusha   → arts/design/luxury
    "Bhadra":         0.08,   # Mercury Mahapurusha → data/math/communication
    "BudhaAditya":    0.07,
    "ChandraMangala": 0.07,
}

_KARAKAMSHA_DOMAIN_KW: Dict[str, List[str]] = {
    "Aries":       ["defence","military","surgery","engineering","sports","police","mechanical","firefighting"],
    "Taurus":      ["arts","music","finance","luxury","architecture","design","fashion","agriculture","beauty"],
    "Gemini":      ["communication","media","journalism","computer","mathematics","commerce","writing","it","data"],
    "Cancer":      ["psychology","nursing","education","social","food","real estate","teaching","public","hospitality"],
    "Leo":         ["civil services","governance","performing arts","management","law","politics","administration","government"],
    "Virgo":       ["medicine","pharmacy","analytics","accounting","data","commerce","law","statistics","health","nutrition"],
    "Libra":       ["law","diplomacy","design","arts","international","hr","management","finance","aesthetics"],
    "Scorpio":     ["research","forensic","mining","psychology","surgery","cybersecurity","investigation","occult","insurance"],
    "Sagittarius": ["law","philosophy","academia","theology","international","sports","education","religion","higher"],
    "Capricorn":   ["engineering","construction","agriculture","government","mining","industrial","architecture","infrastructure"],
    "Aquarius":    ["technology","social","research","computer","astronomy","electronics","it","data","innovation","reform"],
    "Pisces":      ["spiritual","arts","medicine","research","philosophy","psychology","hospital","charity","alternative","healing"],
}

_MD_ROLE_WEIGHT: Dict[str, float] = {
    "amk":  0.35, "h10":  0.28, "ak":   0.20, "h9":   0.12, "h1":   0.08, 
}

_AK_PLANET_BONUS: Dict[str, float] = {
    "Jupiter": 0.11, "Mercury": 0.10, "Mars": 0.10,
    "Saturn":  0.09, "Venus":   0.09, "Moon":  0.08,
    "Sun":     0.08, "Ketu":    0.08, "Rahu":  0.07,
}


def _kp_h10_branch_strength(affinity, kp_sigs):
    if not kp_sigs: return 0.0
    _LW = {0:1.0,1:0.75,2:0.50,3:0.25}
    score = 0.0
    for planet, weight in affinity.items():
        sig = kp_sigs.get(planet, {})
        for idx, key in enumerate(["level_1","level_2","level_3","level_4"]):
            if 10 in sig.get(key, []):
                score += weight * _LW[idx]; break
    return min(score, 1.0)

def _stellium_bonus(label, planet_house):
    if not planet_house: return 0.0
    hc: Dict[int,int] = {}
    for h in planet_house.values(): hc[h] = hc.get(h,0) + 1
    label_lower = label.lower(); bonus = 0.0
    if hc.get(9,0) >= 3 and any(k in label_lower for k in _H9_STELLIUM_KW):
        bonus += 0.04 * (hc[9] - 2)
    if hc.get(12,0) >= 2 and any(k in label_lower for k in _H12_STELLIUM_KW):
        bonus += 0.06
    if hc.get(10,0) >= 2: bonus += 0.04
    return min(bonus, 0.12)

def _h10_sublord_bonus(affinity, kp_cusps):
    h10 = kp_cusps.get("H10",{}); sub_lord = h10.get("sub_lord","")
    if not sub_lord: return 0.0
    w = affinity.get(sub_lord, 0.0)
    if w >= 0.30: return 0.08
    if w >= 0.20: return 0.05
    if w >= 0.10: return 0.02
    return 0.0
def _dasha_bonus(label, payload):
    """Active Mahadasha keyword bonus.

    Restored from 0.05 → 0.10 (base) because 5% was too weak to capture meaningful
    timing signals — Jupiter MD students were ranking the same as Saturn MD students
    despite being in completely different life phases.

    Dignity-scaled: a strong dasha lord sends a stronger timing signal.
      EXALTED  → 0.12  (peak timing activation)
      OWN      → 0.10  (full signal)
      neutral  → 0.08  (moderate signal)
      DEBIL    → 0.05  (weakened timing)

    Triple-stacking guard: run_engine caps total dasha-family boosts at 0.22
    (dasha_bonus + dasha_affinity_boost + peak_md_boost ≤ 0.22).
    This replaces the blanket 0.05 cap which was too blunt.
    """
    lord = _get_active_dasha_lord(getattr(payload,"dasha_sequence",[]), float(getattr(payload,"current_age",0)))
    if not lord: return 0.0
    if not any(kw in label.lower() for kw in DASHA_KEYWORDS.get(lord,[])): return 0.0
    dig = getattr(payload, "planet_dignities", {}).get(lord, "")
    base = {"EXALTED": 0.12, "OWN": 0.10, "NEECHA_BHANGA": 0.09}.get(dig, 0.08)
    if dig == "DEBILITATED": base = 0.05
    return base

def _karakamsha_bonus(affinity, karakamsha):
    if not karakamsha: return 0.0
    sign_lord = _SIGN_LORD.get(karakamsha,""); co_lord = _KARAKAMSHA_CO_LORD.get(karakamsha,"")
    bonus = 0.0
    if sign_lord and affinity.get(sign_lord,0) >= 0.20: bonus += 0.05
    if co_lord   and affinity.get(co_lord,  0) >= 0.20: bonus += 0.03
    return min(bonus, 0.08)

def _ak_combustion_penalty(affinity, ak, combust_planets, planet_dignities=None):
    if planet_dignities is None: planet_dignities = {}
    if not ak or ak not in combust_planets: return 0.0
    w = affinity.get(ak, 0.0)
    # FIX-1: bases halved — effective strength already carries combustion via comb_mod.
    if   w >= 0.35: base = 0.10
    elif w >= 0.25: base = 0.06
    elif w >= 0.15: base = 0.03
    else: return 0.0
    dig = planet_dignities.get(ak, "")
    if dig == "EXALTED": base *= 0.30
    elif dig == "OWN":   base *= 0.50
    return base

def _d24_ak_delta(label, payload):
    ak = getattr(payload,"atmakaraka",""); d24_digs = getattr(payload,"d24_planet_dignities",{})
    if not ak or not d24_digs: return 0.0
    if not any(kw in label.lower() for kw in _D24_ACADEMIC_KW): return 0.0
    dig = d24_digs.get(ak,"")
    if dig == "EXALTED":    return  0.10
    if dig == "OWN":        return  0.05
    if dig == "DEBILITATED": return -0.05
    return 0.0

def _lagna_lord_bonus(label, payload):
    lagna_lord = getattr(payload,"lagna_lord",""); planet_house = getattr(payload,"planet_house",{})
    if not lagna_lord: return 0.0
    ll_house = planet_house.get(lagna_lord,0); label_lower = label.lower()
    if ll_house == 12 and any(kw in label_lower for kw in _H12_FIELDS): return 0.08
    if ll_house == 10: return 0.05
    if ll_house ==  9 and any(kw in label_lower for kw in _H9_FIELDS):  return 0.05
    if ll_house ==  6 and any(kw in label_lower for kw in _H6_FIELDS):  return 0.06
    if ll_house ==  5 and any(kw in label_lower for kw in _H5_FIELDS):  return 0.06
    return 0.0

def _risk_appetite_bonus(label: str, risk: str) -> float:
    """Bidirectional risk-appetite modifier.

    Positive (+0.08): student's stated appetite matches the field's risk profile.
    Negative penalty: mismatch — a HIGH-risk student shouldn't be pushed toward
    actuarial/audit fields; a LOW-risk student shouldn't be pushed toward
    frontier/speculative fields. Penalties are mild (-0.06 to -0.08) to nudge
    ranks without overriding strong astrological signals.
    """
    label_lower = label.lower()
    is_frontier    = any(kw in label_lower for kw in _FRONTIER_KW)
    is_traditional = any(kw in label_lower for kw in _TRADITIONAL_KW)

    if risk == "HIGH":
        if is_frontier:    return  0.08   # reward speculative/cutting-edge match
        if is_traditional: return -0.06   # mild penalty: safe fields for a risk-seeker
    elif risk == "LOW":
        if is_traditional: return  0.08   # reward stable/institutional match
        if is_frontier:    return -0.08   # stronger penalty: volatile fields for risk-averse
    # MODERATE or no preference set → no modifier either way
    return 0.0

def _yogakaraka_bonus(affinity, lagna_sign, shadbala, digs):
    yk = _YOGAKARAKA_PLANET.get(lagna_sign, _FUNCTIONAL_TRIKONA_FALLBACK.get(lagna_sign,""))
    if not yk: return 0.0
    w = affinity.get(yk, 0.0)
    ratio = shadbala.get(yk, 300.0) / _PLANET_MIN_SHADBALA.get(yk, 300.0)
    dig_mod = {"EXALTED":1.3,"DEBILITATED":-0.5,"OWN":1.1}.get(digs.get(yk,""), 1.0)
    if   w >= 0.20: base = 0.12
    elif w >= 0.12: base = 0.07
    elif w >= 0.07: base = 0.04
    else: return 0.0
    return max(0.0, base * ratio * dig_mod)

def _h10_lord_strength_bonus(affinity, h10_lord, shadbala, planet_dignities=None):
    """H10 lord strength bonus — scaled by dignity.

    An exalted H10 lord is the strongest possible career indicator in classical
    Jyotish (Rajayoga via 10th bhava lord in uccha). The bonus now mirrors the
    Yogakaraka formula: base × shadbala_ratio × dignity_multiplier.
    """
    if planet_dignities is None: planet_dignities = {}
    if not h10_lord: return 0.0
    w = affinity.get(h10_lord, 0.0)
    if w < 0.10: return 0.0
    ratio    = shadbala.get(h10_lord, 0.0) / _PLANET_MIN_SHADBALA.get(h10_lord, 300.0)
    dig      = planet_dignities.get(h10_lord, "")
    dig_mult = {"EXALTED": 1.5, "OWN": 1.2, "NEECHA_BHANGA": 1.0, "DEBILITATED": 0.4}.get(dig, 1.0)
    if   w >= 0.30: base = 0.12
    elif w >= 0.20: base = 0.08
    elif w >= 0.10: base = 0.04
    else: return 0.0
    return min(base * ratio * dig_mult, 0.18)


def _h10_lord_trikona_bonus(affinity: dict, h10_lord: str, planet_house: dict,
                             planet_dignities: dict = None) -> float:
    """H10 lord in trikona (H5 or H9) domain-specific bonus.

    When the career lord (H10 lord) occupies a trikona (5th or 9th house), it
    gains wisdom/creative power and delivers enhanced results in the domains
    signified by that trikona:
      H5 → arts, education, creative/speculative fields
      H9 → law, philosophy, religion, international fields
    Bonus is modest (≤0.12) and requires minimum affinity weight of 0.12 to fire.
    """
    if planet_dignities is None: planet_dignities = {}
    if not h10_lord: return 0.0
    h10_lord_house = planet_house.get(h10_lord, 0)
    if h10_lord_house not in (5, 9): return 0.0
    w = affinity.get(h10_lord, 0.0)
    if w < 0.12: return 0.0
    dig = planet_dignities.get(h10_lord, "")
    dig_mult = {"EXALTED": 1.5, "OWN": 1.2}.get(dig, 1.0)
    base = 0.07 if h10_lord_house == 5 else 0.06
    return min(base * dig_mult, 0.12)


# Natural signification keywords for each planet when exalted —
# classical rule: exalted planets deliver superior results in their domains.
_EXALT_DOMAIN_KW: Dict[str, List[str]] = {
    "Venus":   ["art", "music", "design", "fashion", "film", "perform", "aesthetic",
                "creative", "visual", "textile", "interior", "dance", "theatre"],
    "Jupiter": ["law", "philosophy", "education", "medicine", "research", "management",
                "economics", "theology", "international"],
    "Moon":    ["nursing", "psychology", "social", "ecology", "public health", "counseling",
                "hospitality", "aquaculture", "nutrition"],
    "Mars":    ["engineering", "defence", "military", "surgery", "sports", "mechanical"],
    "Mercury": ["data", "computer", "mathematics", "accounting", "statistics", "communication"],
    "Saturn":  ["mining", "civil", "metallurgy", "agriculture", "industrial", "petroleum",
                "construction", "materials"],
    "Sun":     ["civil services", "administration", "government", "leadership", "energy"],
}


def _exalted_planet_domain_bonus(affinity: Dict[str, float],
                                  planet_dignities: Dict[str, str],
                                  label: str) -> float:
    """Bonus when an EXALTED planet's natural signification matches the field label.

    Classical principle: a planet in uccha (exaltation) delivers its highest
    results in its own domain.  This ensures e.g. exalted Venus in Pisces
    actively promotes arts/design fields for that chart.
    """
    label_lower = label.lower()
    bonus = 0.0
    for planet, kws in _EXALT_DOMAIN_KW.items():
        if planet_dignities.get(planet, "") != "EXALTED":
            continue
        w = affinity.get(planet, 0.0)
        if w < 0.15:
            continue
        if any(kw in label_lower for kw in kws):
            if   w >= 0.35: bonus += 0.10
            elif w >= 0.25: bonus += 0.07
            elif w >= 0.15: bonus += 0.04
    return min(bonus, 0.15)

def _ul_lord_bonus(affinity, upapada_lagna):
    ul_lord = _SIGN_LORD.get(upapada_lagna,"")
    if not ul_lord: return 0.0
    w = affinity.get(ul_lord, 0.0)
    if w >= 0.25: return 0.06
    if w >= 0.15: return 0.03
    return 0.0

def _kp_edu_starlord_bonus(affinity, kp_cusps):
    h5_star = kp_cusps.get("H5",{}).get("star_lord","")
    h9_star = kp_cusps.get("H9",{}).get("star_lord","")
    bonus = 0.0
    for sl in set(filter(None,[h5_star,h9_star])):
        w = affinity.get(sl,0.0)
        if w >= 0.25: bonus += 0.03
        elif w >= 0.15: bonus += 0.02
    return min(bonus, 0.05)

def _d9_ak_delta(label, payload):
    ak = getattr(payload,"atmakaraka",""); d9_digs = getattr(payload,"d9_planet_dignities",{})
    if not ak or not d9_digs: return 0.0
    dig = d9_digs.get(ak,"")
    if dig == "EXALTED":     return  0.06
    if dig == "OWN":         return  0.03
    if dig == "DEBILITATED": return -0.04
    return 0.0

def _classify_parivartana(p1: str, p2: str, house_lords: Dict[str, str]) -> str:
    def _roles(p):
        kendra   = any(house_lords.get(h) == p for h in ("1","4","7","10"))
        trikona  = any(house_lords.get(h) == p for h in ("1","5","9"))
        dusthana = any(house_lords.get(h) == p for h in ("6","8","12"))
        h3       = house_lords.get("3") == p
        return kendra, trikona, dusthana, h3
    k1,t1,d1,h3_1 = _roles(p1)
    k2,t2,d2,h3_2 = _roles(p2)
    if d1 or d2:      return "Dainya"
    if h3_1 or h3_2:  return "Khala"
    if (k1 or t1) and (k2 or t2): return "Mahayoga"
    return "Neutral"

def _yoga_bonus(label, detected_yogas, house_lords=None):
    if not detected_yogas: return 0.0
    if house_lords is None: house_lords = {}
    label_lower = label.lower(); bonus = 0.0
    for yoga in detected_yogas:
        if yoga.startswith("Parivartana_"):
            parts = yoga.split("_")
            if len(parts) == 3:
                ptype = _classify_parivartana(parts[1], parts[2], house_lords)
                if   ptype == "Mahayoga": bonus += 0.08
                elif ptype == "Dainya":   bonus -= 0.05
                elif ptype == "Khala":    bonus += 0.0
                else:                     bonus += 0.03
        elif any(kw in label_lower for kw in _YOGA_DOMAIN_KW.get(yoga,[])):
            bonus += _YOGA_BONUS_AMT.get(yoga, 0.07)
    return max(-0.10, min(bonus, 0.21))
def _h5_lord_bonus(affinity, h5_lord):
    if not h5_lord: return 0.0
    w = affinity.get(h5_lord, 0.0)
    if w >= 0.25: return 0.06
    if w >= 0.15: return 0.03
    return 0.0

def _amk_house_bonus(label, amk_house):
    kws = _AMK_HOUSE_KW.get(amk_house,[])
    if kws and any(kw in label.lower() for kw in kws):
        return 0.06 if amk_house in (5,9) else 0.04
    return 0.0
def _ak_house_bonus(ak, ak_house, label):
    """v9.4: AK house → field orientation boost (expanded to all houses)."""
    lb = label.lower()
    # Trikona houses (H1/H5/H9) — soul's dharma direction
    if ak_house == 1 and any(k in lb for k in [
        "leadership","entrepreneurship","management","public","administration",
        "sports","defence","governance","self-employment","politics",
    ]):
        return 0.07
    if ak_house == 2 and any(k in lb for k in [
        "finance","commerce","banking","accounting","economics","trading",
        "food","speech","communication","family business","valuables",
    ]):
        return 0.06
    if ak_house == 3 and any(k in lb for k in [
        "communication","media","journalism","writing","publishing","content",
        "pr","advertising","broadcast","arts","performing arts","music",
    ]):
        return 0.07
    if ak_house == 4 and any(k in lb for k in [
        "architecture","real estate","education","teaching","psychology",
        "agriculture","environment","social","hospitality","public",
    ]):
        return 0.06
    if ak_house == 5 and any(k in lb for k in [
        "research","education","science","mathematics","statistics","data",
        "creative","arts","philosophy","sports","investment","intelligence",
    ]):
        return 0.08
    if ak_house == 6 and any(k in lb for k in [
        "medicine","nursing","surgery","doctor","physician","clinical","health",
        "pharmacy","ayurveda","hospital","public health","service","defence","law",
    ]):
        return 0.07   # H6 = disease/healing/service
    if ak_house == 7 and any(k in lb for k in [
        "international","diplomacy","law","public relations","marketing",
        "trade","partnership","consulting","foreign","hr","hospitality",
    ]):
        return 0.06
    if ak_house == 8 and any(k in lb for k in [
        "medicine","surgery","anatomy","doctor","physician","clinical","emergency",
        "research","forensic","psychology","investigation","data science","cybersecurity",
        "economics","audit","tax","insurance","metallurgy","mining","occult",
    ]):
        return 0.08   # H8 = deep biology, crisis medicine, hidden research
    if ak_house == 9 and any(k in lb for k in [
        "law","philosophy","higher","theology","medicine","science",
        "international","education","academia","religion","journalism",
    ]):
        return 0.08
    if ak_house == 10 and any(k in lb for k in [
        "public","management","career","administration","engineering",
        "government","corporate","civil services","politics","leadership",
    ]):
        return 0.08
    if ak_house == 11 and any(k in lb for k in [
        "engineering","metallurgy","mining","industrial","materials",
        "petroleum","technology","commerce","finance","economics",
        "data","computer","artificial","robotics","electronics",
        "geology","geoscience","earth science","geophysics","law",
        "agriculture","architecture","real estate","environment","construction",
    ]):
        return 0.06
    if ak_house == 12 and any(k in lb for k in [
        "research","spiritual","hospital","medicine","psychology","forensic",
        "international","foreign","philosophy","alternative","charity","social",
        "investigation","hidden","occult","ayurveda","theology",
    ]):
        return 0.07   # H12 = moksha, foreign lands, hidden research
    return 0.0

def _planet_combustion_penalty(affinity, combust_planets, planet_dignities=None):
    if planet_dignities is None: planet_dignities = {}
    penalty = 0.0
    for p in combust_planets:
        if p not in affinity: continue
        base = affinity[p] * 0.15
        dig  = planet_dignities.get(p,"")
        if dig == "EXALTED": base *= 0.30
        elif dig == "OWN":   base *= 0.50
        penalty += base
    return min(penalty, 0.20)

# Fields where 8th-house energy (hidden, crisis, deep investigation) is required
# Unified exemption keywords — fields that positively require dusthana energy
def _dusthana_lord_penalty(affinity, lagna_sign, house_lords, lagna_lord: str = "",
                            label: str = ""):
    """Dusthana lord penalty — exempt fields that require 6th/8th house energy.

    H6 (disease/service/law), H8 (surgery/research/hidden), H12 (renunciation/hospital).
    Penalising their lords for fields that specifically REQUIRE these energies
    actively suppresses the correct astrological match.
    """
    lb = label.lower()
    if any(kw in lb for kw in _DUSTHANA_EXEMPT_KW):
        return 0.0

    dusthanas = {house_lords.get("6"), house_lords.get("8"), house_lords.get("12")} - {None, ""}
    penalty = 0.0
    for p, w in affinity.items():
        if p == lagna_lord:
            continue   # lagna lord immune
        if p in dusthanas and w > 0.15:
            penalty += w * 0.10
    return min(penalty, 0.15)

def _peak_career_dasha(
    dasha_seq: List[Dict], shadbala: Dict[str, float],
    planet_dignities: Dict[str, str], house_lords: Dict[str, str],
    ak: str, amk: str, current_age: float = 0.0,
    eff_strengths: Dict[str, float] = None,
    planet_house: Dict[str, int] = None,
) -> Tuple[str, Dict[str, float]]:
    # FIX-6: uses effective strengths; age>80 reachability cap (0.2x); dusthana-lord penalty (0.7x)
    if eff_strengths is None:
        eff_strengths = {}
    if planet_house is None:
        planet_house = {}

    scores: Dict[str, float] = {}
    seen: set = set()
    h1_lord  = house_lords.get("1",  "")
    h9_lord  = house_lords.get("9",  "")
    h10_lord = house_lords.get("10", "")
    dusthana_lords = {house_lords.get("6"), house_lords.get("8"), house_lords.get("12")} - {None, ""}

    for d in dasha_seq:
        end_age   = d.get("end_age") or float("inf")
        start_age = d.get("start_age") or d.get("age_start") or 0.0
        if end_age <= current_age: continue
        lord = d.get("lord", "") or d.get("md_planet", "")
        if not lord or lord in seen: continue
        seen.add(lord)

        # Use effective strength (retro paradox, combustion, digbala, vargottama baked in)
        if lord in eff_strengths and eff_strengths[lord] > 0:
            eff = min(eff_strengths[lord], 2.0)
        else:
            min_v = _PLANET_MIN_SHADBALA.get(lord, 300)
            eff   = min(shadbala.get(lord, min_v) / min_v, 2.0)

        dig = planet_dignities.get(lord, "")
        dig_mult = {"EXALTED": 1.40, "OWN": 1.15, "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.40}.get(dig, 1.0)

        role_mult = 1.0
        if lord == amk:      role_mult += _MD_ROLE_WEIGHT["amk"]
        if lord == h10_lord: role_mult += _MD_ROLE_WEIGHT["h10"]
        if lord == ak:       role_mult += _MD_ROLE_WEIGHT["ak"]
        if lord == h9_lord:  role_mult += _MD_ROLE_WEIGHT["h9"]
        if lord == h1_lord:  role_mult += _MD_ROLE_WEIGHT["h1"]

        reach_mod = 0.2 if start_age > 80 else 1.0   # dasha starting after 80 = speculative
        dust_mod  = 0.7 if lord in dusthana_lords else 1.0  # dusthana lord is weak career peak

        scores[lord] = eff * dig_mult * role_mult * reach_mod * dust_mod

    if not scores: return ("", {})
    peak = max(scores, key=scores.get)
    return (peak, scores)

def _peak_career_dasha_boost(affinity: Dict[str, float], peak_lord: str, active_lord: str, planet_dignities: Dict[str, str]) -> float:
    if not peak_lord or peak_lord not in affinity: return 0.0
    dig = planet_dignities.get(peak_lord, "")
    dig_scale = {"EXALTED": 1.40, "OWN": 1.15, "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.60}.get(dig, 1.0)  
    base = affinity[peak_lord] * 0.22 * dig_scale
    if peak_lord == active_lord: base *= 0.50 
    return round(base, 4)

def _dasha_active_affinity_boost(affinity, active_lord, planet_dignities=None):
    if planet_dignities is None: planet_dignities = {}
    if active_lord not in affinity: return 0.0
    dig = planet_dignities.get(active_lord,"")
    dig_scale = {"EXALTED":1.40,"OWN":1.15,"DEBILITATED":0.40,"NEECHA_BHANGA":1.05}.get(dig,1.0)
    return affinity[active_lord] * 0.25 * dig_scale

def _d10_consistency_penalty(affinity, d10_house_occ):
    _COEFF = {"6":0.15,"8":0.30,"12":0.20}
    penalty = 0.0
    for house_str, coeff in _COEFF.items():
        for planet in d10_house_occ.get(house_str,[]):
            w = affinity.get(planet,0.0)
            if w >= 0.15: penalty += w * coeff
    return min(penalty, 0.25)

def _pratyantar_dasha_bonus(label, prd_lord, prd_houses):
    if not prd_lord: return 0.0
    kw_match = any(kw in label.lower() for kw in DASHA_KEYWORDS.get(prd_lord,[]))
    h_strong = any(h in prd_houses for h in [5, 9, 10])
    h_gain   = any(h in prd_houses for h in [1, 11])
    bonus = 0.0
    if kw_match and h_strong: bonus += 0.06
    elif kw_match: bonus += 0.03
    if kw_match and h_gain: bonus += 0.04
    elif h_gain and not kw_match: bonus += 0.01 
    return min(bonus, 0.08)

def _karakamsha_occupant_bonus(label, karakamsha_occupants, shadbala: Dict[str, float] = None):
    if shadbala is None: shadbala = {}
    bonus = 0.0
    for planet in karakamsha_occupants:
        kws = _KARAKAMSHA_OCCUPANT_KW.get(planet, [])
        if any(kw in label.lower() for kw in kws):
            min_v = _PLANET_MIN_SHADBALA.get(planet, 300)
            ratio = shadbala.get(planet, min_v) / min_v
            ratio = max(0.0, min(ratio, 1.5))
            planet_bonus = 0.06 * ratio
            bonus += min(planet_bonus, 0.09) 
    return min(bonus, 0.15)
# ===========================================================================
# BHAVESHA PHALA (HOUSE LORD PLACEMENT) EDUCATIONAL LOGIC
# ===========================================================================
_BHAVESHA_PHALA_KW: Dict[int, List[str]] = {
    1: ["management", "business", "leadership", "entrepreneurship", "administration"],
    2: ["finance", "accounting", "commerce", "economics", "data", "banking", "wealth"],
    3: ["media", "journalism", "computer", "communication", "technology", "coding", "software"],
    4: ["agriculture", "civil", "architecture", "environmental", "teaching", "real estate"],
    5: ["mathematics", "design", "arts", "artificial intelligence", "data science", "statistics", "innovation"],
    6: ["medicine", "law", "cybersecurity", "defence", "analytics", "nursing", "problem solving"],
    7: ["international", "business", "management", "commerce", "public", "foreign"],
    8: ["research", "mining", "metallurgy", "data science", "cybersecurity", "psychology",
        "backend", "forensic", "medicine", "surgery", "anatomy", "doctor", "physician",
        "medical", "emergency", "hospital", "clinical", "pathology", "radiology"],  # FIX-19
    9: ["philosophy", "law", "academia", "science", "physics", "theology", "higher education"],
    10: ["engineering", "civil services", "management", "administration", "technology", "executive"],
    11: ["computer science", "artificial intelligence", "networking", "sociology", "public policy", "systems", "finance", "accounting", "commerce", "economics"],
    12: ["medicine", "hospital", "research", "space", "foreign", "spiritual", "psychology"]
}

def _bhavesha_phala_edu_bonus(label: str, affinity: Dict[str, float], house_lords: Dict[str, str], planet_house: Dict[str, int]) -> float:
    """FIX-20: Bhavesha Phala — extended to H2+H11 for commerce/finance/wealth fields.

    Classical Jyotish:
      H4 lord (formal schooling), H5 lord (intellect), H9 lord (higher education)
      are primary educational lords.
      H2 lord (accumulated wealth/accounting) and H11 lord (financial gains/networks)
      are primary commerce/finance lords — mandatory for CA, CS, banking paths.
    """
    bonus = 0.0
    label_lower = label.lower()

    # H2 (dhana/wealth), H4 (formal), H5 (intellect), H9 (higher ed), H11 (labha/gains)
    # H2+H11 always checked — placement keywords filter what each house signals for each field
    edu_houses = ["2", "4", "5", "9", "11"]

    for h in edu_houses:
        lord = house_lords.get(h, "")
        if not lord:
            continue
        placed_in_house = planet_house.get(lord, 0)
        if placed_in_house == 0:
            continue
        placement_kws = _BHAVESHA_PHALA_KW.get(placed_in_house, [])
        if any(kw in label_lower for kw in placement_kws):
            w = affinity.get(lord, 0.0)
            if   w >= 0.25: bonus += 0.05
            elif w >= 0.15: bonus += 0.03
            elif w >= 0.08: bonus += 0.01

    return min(bonus, 0.12)

def _d9_h10_bonus(affinity, d9_chart, d9_lagna_sign):
    if not d9_lagna_sign or not d9_chart: return 0.0
    bonus = 0.0
    for planet, sign in d9_chart.items():
        if planet == "Lagna": continue
        if (((_SIGN_NUM.get(sign, 1) - _SIGN_NUM.get(d9_lagna_sign, 1)) % 12) + 1) == 10:
            w = affinity.get(planet, 0.0)
            if w >= 0.20: bonus += 0.05
            elif w >= 0.10: bonus += 0.02
    return min(bonus, 0.08)

def _dharma_karma_bonus(affinity, house_lords, planet_house):
    h9_lord, h10_lord = house_lords.get("9",""), house_lords.get("10","")
    if not h9_lord or not h10_lord or h9_lord == h10_lord: return 0.0
    h9l_house, h10l_house = planet_house.get(h9_lord, 0), planet_house.get(h10_lord, 0)
    if h9l_house == 0 or h10l_house == 0: return 0.0
    same_house = (h9l_house == h10l_house)
    mutual_kendra = abs(h9l_house - h10l_house) in (0,3,6,9)
    if not (same_house or mutual_kendra): return 0.0
    w9, w10  = affinity.get(h9_lord, 0.0), affinity.get(h10_lord, 0.0)
    if w9 >= 0.15 or w10 >= 0.15: return 0.08
    if w9 >= 0.10 or w10 >= 0.10: return 0.04
    return 0.0

# ════════════════════════════════════════════════════════════════════════════
# NEW GAP FUNCTIONS (v8.9)
# ════════════════════════════════════════════════════════════════════════════

def _d10_h10_bonus(affinity: Dict[str, float], d10_chart: Dict, d10_lagna_sign: str,
                   d10_planet_dignities: Dict[str, str] = None) -> float:
    """FIX-3: Credit planets occupying D10's 10th house (mirrors _d9_h10_bonus).
    Exalted planets in D10 H10 receive extra weight — this is the career chart's
    most important house and any strong planet there is a direct professional indicator."""
    if not d10_lagna_sign or not d10_chart:
        return 0.0
    if d10_planet_dignities is None:
        d10_planet_dignities = {}
    bonus = 0.0
    for planet, sign in d10_chart.items():
        if planet == "Lagna":
            continue
        h = ((_SIGN_NUM.get(sign, 1) - _SIGN_NUM.get(d10_lagna_sign, 1)) % 12) + 1
        if h != 10:
            continue
        w = affinity.get(planet, 0.0)
        dig = d10_planet_dignities.get(planet, "")
        if   w >= 0.20 and dig == "EXALTED": bonus += 0.10
        elif w >= 0.20:                       bonus += 0.06
        elif w >= 0.10 and dig == "EXALTED": bonus += 0.06
        elif w >= 0.10:                       bonus += 0.03
    return min(bonus, 0.12)


# Lagnas where Venus is a functional malefic — rules dusthana/upachaya pairs.
# Scorpio: Venus rules H7+H12; Sagittarius: H6+H11; Pisces: H3+H8.
# For these lagnas, a blanket Venus boost is astrologically incorrect.
_VENUS_MALEFIC_LAGNAS: frozenset = frozenset({
    "Scorpio",    # Venus rules H7 (maraka) + H12 (vyaya/loss)
    "Sagittarius",# Venus rules H6 (roga/dusthana) + H11 (labha but not KT)
    "Pisces",     # Venus rules H3 (upachaya) + H8 (randhra/dusthana)
})

def _gender_field_modifier(label: str, gender: str, affinity: Dict[str, float],
                            house_lords: Dict[str, str] = None) -> float:
    """Gender-aware Venus modifier — checks Venus functional status from actual house lordships.

    Classical Jyotish: Venus boosts female-relevant fields ONLY when Venus is a
    functional benefic. If Venus rules H6, H8, or H12, it is a functional malefic
    for that chart regardless of lagna — no boost should be granted.
    This chart-driven check is more accurate than a hardcoded lagna list.
    """
    if not gender:
        return 0.0
    g = gender.strip().upper()
    if g not in ("F", "FEMALE"):
        return 0.0
    # Suppress bonus if Venus rules a dusthana (H6/H8/H12) in this chart
    if house_lords:
        venus_dusthana = (
            house_lords.get("6") == "Venus" or
            house_lords.get("8") == "Venus" or
            house_lords.get("12") == "Venus"
        )
        if venus_dusthana:
            return 0.0
    v_weight = affinity.get("Venus", 0.0)
    if   v_weight >= 0.25: return 0.06
    elif v_weight >= 0.15: return 0.03
    return 0.0


def _aspect_h10_bonus(affinity: Dict[str, float], planet_house: Dict[str, int],
                      planet_dignities: Dict[str, str] = None,
                      planets_d1: Dict = None) -> float:
    """FIX-5 (Drishti Bala upgraded): Bonus when a high-affinity planet aspects H10.

    When planets_d1 is supplied, the bonus is scaled by Drishti Bala: a planet at
    the house midpoint (15°) gives full strength; one near a cusp gives 50%.
    This implements the classical principle that aspect potency is not uniform.
    """
    if planet_dignities is None:
        planet_dignities = {}
    aspects = _get_planetary_aspects(planet_house)
    if planets_d1:
        weighted = _get_planetary_aspects_weighted(planet_house, planets_d1)
        aspect_strength = {p: d.get(10, 0.0) for p, d in weighted.items()}
    else:
        aspect_strength = {p: (1.0 if 10 in hs else 0.0) for p, hs in aspects.items()}
    bonus = 0.0
    for planet, aspected_houses in aspects.items():
        if 10 not in aspected_houses:
            continue
        w         = affinity.get(planet, 0.0)
        dig       = planet_dignities.get(planet, "")
        dig_scale = {"EXALTED": 1.40, "OWN": 1.15}.get(dig, 1.0)
        drishti   = aspect_strength.get(planet, 1.0)   # 0.5 (cusp) → 1.0 (midpoint)
        if   w >= 0.25: bonus += 0.06 * dig_scale * drishti
        elif w >= 0.15: bonus += 0.03 * dig_scale * drishti
        elif w >= 0.08: bonus += 0.01 * dig_scale * drishti
    return min(bonus, 0.10)
def _maheshwara_lord_bonus(label: str, maheshwara_lord: str, affinity: Dict[str, float]) -> float:
    """FIX-6: Maheshwara lord (Jaimini special lord) now contributes to branch scoring.
    Maheshwara represents the peak institutional authority phase of the native's career.
    When a branch aligns with the Maheshwara lord's domain keywords, it receives a bonus."""
    if not maheshwara_lord:
        return 0.0
    kws = _MAHESHWARA_DOMAIN_KW.get(maheshwara_lord, [])
    if not any(kw in label.lower() for kw in kws):
        return 0.0
    w = affinity.get(maheshwara_lord, 0.0)
    if   w >= 0.25: return 0.07
    if   w >= 0.15: return 0.04
    if   w >= 0.08: return 0.02
    return 0.0


_INTEREST_KEYWORD_ALIASES: Dict[str, List[str]] = {
    # Professional streams → degree field labels they map to (DESIGN-2 fix)
    "chartered accountant": ["commerce", "accounting", "finance", "economics"],
    "company secretary":    ["commerce", "accounting", "corporate", "law", "business"],
    "ca foundation":        ["commerce", "accounting", "finance"],
    "cs exam":              ["corporate", "law", "commerce", "business"],
    "chartered":            ["commerce", "accounting", "finance"],
    "actuary":              ["statistics", "mathematics", "finance", "economics"],
    "data science":         ["data", "statistics", "artificial intelligence", "computer", "mathematics"],
    "machine learning":     ["artificial intelligence", "data", "computer", "robotics"],
    "economics":            ["economics", "public policy", "commerce", "finance", "business"],
    "civil service":        ["civil services", "public policy", "law", "political"],
    "defence":              ["defence", "military", "aerospace", "mechanical"],
    "medicine":             ["medicine", "mbbs", "biomedical", "nursing", "pharmacy", "biology"],
}

def _interest_preference_boost(label: str, interested_in: List[str], already_excel_at: List[str]) -> float:
    """DESIGN-2 fix: Alias professional streams (CA, CS, etc.) to matching degree-field label keywords."""
    label_lower = label.lower()
    interest_boost = 0.0
    for kw in (interested_in or []):
        if not kw:
            continue
        kw_lower = kw.lower()
        # Direct substring match
        if kw_lower in label_lower:
            interest_boost += 0.10
            continue
        # Alias-based match: expand professional/common terms to degree-field keywords
        aliases = _INTEREST_KEYWORD_ALIASES.get(kw_lower, [])
        if any(alias in label_lower for alias in aliases):
            interest_boost += 0.08   # slightly lower than direct match
    interest_boost = min(interest_boost, 0.20)

    excel_boost = 0.0
    for kw in (already_excel_at or []):
        if not kw:
            continue
        kw_lower = kw.lower()
        if kw_lower in label_lower:
            excel_boost += 0.06
            continue
        aliases = _INTEREST_KEYWORD_ALIASES.get(kw_lower, [])
        if any(alias in label_lower for alias in aliases):
            excel_boost += 0.04
    excel_boost = min(excel_boost, 0.12)

    return round(interest_boost + excel_boost, 4)

_BRAHMA_DOMAIN_KW: Dict[str, List[str]] = {
    "Jupiter": ["law","education","philosophy","medicine","economics","management","research","theology","international"],
    "Mercury": ["data science","computer","mathematics","accounting","statistics","communication","artificial intelligence"],
    "Venus":   ["arts","design","fashion","music","architecture","fine arts","performing arts"],
    "Saturn":  ["engineering","mining","civil","metallurgy","agriculture","industrial","petroleum","environmental"],
    "Mars":    ["defence","surgery","engineering","military","police","sports"],
    "Sun":     ["civil services","administration","medicine","government","leadership","physics"],
    "Moon":    ["nursing","psychology","social work","public health","ecology","hospitality"],
    "Rahu":    ["artificial intelligence","cybersecurity","biotechnology","space","robotics","forensic"],
    "Ketu":    ["research","ayurveda","spiritual","philosophy","archaeology","investigation"],
}

def _brahma_lord_bonus(label: str, brahma_lord: str, affinity: Dict[str, float]) -> float:
    if not brahma_lord: return 0.0
    kws = _BRAHMA_DOMAIN_KW.get(brahma_lord, [])
    if not any(kw in label.lower() for kw in kws): return 0.0
    w = affinity.get(brahma_lord, 0.0)
    if w >= 0.25: return 0.08
    if w >= 0.15: return 0.05
    if w >= 0.08: return 0.02
    return 0.0
def _chart_specific_aptitude_supplement(
    domain: str, h5_lord: str, lagna_lord: str, h10_lord: str,
    eff_strengths: Dict[str, float],
) -> int:
    """FIX-23: Chart-specific domain aptitude supplement.

    Corrects the global hardcoding of DOMAIN_APTITUDE_PLANETS by checking
    if the student's own chart lords (5th/lagna/10th) have strong domain affinity.

    Classical logic:
      • 5th lord (intellect) strong in a domain → native excels through that domain
      • Lagna lord (self) strong in a domain → native identifies with that field
      • 10th lord (career) strong in a domain → native succeeds in that career path
    If any of these lords aligns well with the domain AND is strong (eff ≥ 1.0),
    supplement the aptitude score with up to 20 additional points.
    """
    domain_wts = _GENERIC_9P_WEIGHTS
    supplement = 0
    for lord in (h5_lord, lagna_lord, h10_lord):
        if not lord:
            continue
        lord_wt  = domain_wts.get(lord, 0.0)
        lord_eff = eff_strengths.get(lord, 0.0)
        if lord_wt >= 0.25 and lord_eff >= 1.20:
            supplement += 12   # strongly aligned lord with strong chart strength
        elif lord_wt >= 0.15 and lord_eff >= 1.00:
            supplement += 6    # moderately aligned
    return min(supplement, 20)




def _ak_planet_domain_boost(label: str, ak: str, ak_dig: str, ph: Dict[str,int]) -> float:
    """v9.5 Gap-1/8: AK planet identity -> domain-specific field bonus.
    Jupiter AK -> philosophy/law/education +0.11 (soul seeks wisdom)
    Mercury AK -> communication/analytics +0.10 (soul seeks intellect)
    Mars AK    -> engineering/defence/surgery +0.10 (soul seeks mastery/action)
    Saturn AK  -> civil services/law/architecture +0.09 (soul seeks structure)
    Venus AK   -> arts/design/finance +0.09 (soul seeks beauty)
    +0.02 when AK is exalted or own sign (soul expresses domain fully).
    """
    if not ak: return 0.0
    domain_kws = _AK_PLANET_DOMAIN_KW.get(ak, [])
    if not domain_kws: return 0.0
    lb = label.lower()
    if not any(kw in lb for kw in domain_kws): return 0.0
    base = _AK_PLANET_BONUS.get(ak, 0.07)
    if ak_dig in ("EXALTED", "OWN"): base += 0.02
    return min(base, 0.13)

# ===========================================================================
# v9.4 GAP-FIX FUNCTIONS
# ===========================================================================

def _karakamsha_domain_boost(label: str, domain: str, karakamsha: str) -> float:
    """v9.4 Fix-1: Karakamsha sign drives domain-specific field boosts.
    Addresses the core gap: karakamsha was only affinity-based, not domain-specific.
    """
    if not karakamsha: return 0.0
    domain_kws = _KARAKAMSHA_DOMAIN_KW.get(karakamsha, [])
    if not domain_kws: return 0.0
    lb = label.lower()
    if any(kw in lb for kw in domain_kws):
        # Strong spiritual/research signs get higher boost for their domains
        if karakamsha in ("Pisces", "Scorpio", "Sagittarius"): return 0.09
        if karakamsha in ("Leo", "Virgo", "Aquarius"):          return 0.08
        return 0.07
    return 0.0


def _h3_lord_communication_boost(label: str, domain: str,
                                   house_lords: Dict[str,str],
                                   eff_strengths: Dict[str,float],
                                   ph: Dict[str,int]) -> float:
    """v9.4 Fix-5: H3 lord effective strength → Communication/Media/Journalism boost."""
    _H3_COMM_KW = frozenset(["communication","media","journalism","writing","publishing",
                              "content","advertising","pr","broadcast","performing arts",
                              "music","social media","film","radio","literature"])
    lb = label.lower()
    if not any(kw in lb for kw in _H3_COMM_KW): return 0.0
    h3_lord = house_lords.get("H3","") or house_lords.get("3","")
    if not h3_lord: return 0.0
    strength = eff_strengths.get(h3_lord, 0.0)
    h3_lord_house = ph.get(h3_lord, 0)
    boost = 0.0
    if strength >= 1.20: boost = 0.08
    elif strength >= 0.90: boost = 0.05
    elif strength >= 0.65: boost = 0.03
    else: return 0.0
    # Extra if H3 lord in kendra/trikona
    if h3_lord_house in (1,4,5,7,9,10): boost += 0.02
    return min(boost, 0.10)


def _h12_stellium_penalty(label: str, domain: str, ph: Dict[str,int]) -> float:
    """v9.4 Fix-7: 4+ planets in H12 → suppress public-facing career fields.
    Charts with heavy H12 → foreign/research/spiritual; public admin over-ranked.
    """
    _PUBLIC_FACING_KW = frozenset(["civil services","governance","politics","administration",
                                   "public policy","management","corporate","banking",
                                   "public","marketing","pr","mass communication","journalism"])
    lb = label.lower()
    if not any(kw in lb for kw in _PUBLIC_FACING_KW): return 0.0
    h12_count = sum(1 for house in ph.values() if house == 12)
    if h12_count >= 4: return -0.10
    if h12_count == 3: return -0.05
    return 0.0



def _build_critical_warnings(house_lords: Dict[str,str],
                              planets_d1: Dict[str,dict],
                              shadbala: Dict[str,float],
                              planet_trace: Dict[str,dict]) -> List[Dict]:
    """v9.5 Gap-9: Flag Rasi Sandhi and below-minimum Shadbala for critical lords.
    Returns warning list attached to every field result as chart-level metadata.
    """
    CRITICAL_HOUSES = {
        1: "H1 (self/lagna)",   4: "H4 (education/home)",
        5: "H5 (intelligence)", 9: "H9 (higher education/dharma)",
        10: "H10 (career)",     11: "H11 (gains/income)",
    }
    warnings = []
    seen = set()
    for h_num, h_label in CRITICAL_HOUSES.items():
        lord = house_lords.get(f"H{h_num}","") or house_lords.get(str(h_num),"")
        if not lord or lord in seen: continue
        seen.add(lord)
        trace      = planet_trace.get(lord, {})
        deg        = planets_d1.get(lord, {}).get("degree", 15.0)
        sandhi_mod = trace.get("sandhi_mod", 1.0)
        raw_shad   = shadbala.get(lord, 0.0)
        min_shad   = _PLANET_MIN_SHADBALA.get(lord, 300.0)

        if sandhi_mod < 0.80:
            warnings.append({
                "type":       "RASI_SANDHI",
                "planet":     lord,
                "house_lord": h_label,
                "degree":     round(deg, 2),
                "sandhi_mod": round(sandhi_mod, 4),
                "impact": (
                    f"{lord} (lord of {h_label}) at {round(deg,2)}: "
                    f"Rasi Sandhi reduces strength to {round(sandhi_mod*100)}%. "
                    f"Significations of {h_label} are weakened or delayed."
                ),
            })
        if raw_shad > 0 and (raw_shad / min_shad) < 0.80:
            pct = round(raw_shad / min_shad * 100)
            warnings.append({
                "type":         "BELOW_MIN_SHADBALA",
                "planet":       lord,
                "house_lord":   h_label,
                "shadbala":     round(raw_shad, 1),
                "min_shadbala": min_shad,
                "pct_of_min":   pct,
                "impact": (
                    f"{lord} (lord of {h_label}) at {pct}% of minimum Shadbala — "
                    f"significations of {h_label} manifest with difficulty."
                ),
            })
    return warnings

def _apply_domain_deduplication(results: List[Dict], payload_data=None) -> List[Dict]:
    """v9.4 Fix-2 & Fix-8: Cluster deduplication + textile rarity gate.

    Engineering/science clusters capped at 3 each to prevent over-segmentation.
    Textile suppressed unless Venus+Saturn+Mars all in earth signs.
    """
    _CLUSTER_MAP: Dict[str, str] = {}
    _ENG_KW = ("engineering","technology","metallurgy","mining","petroleum","aerospace",
                "robotics","automation","electronics","microelectronics","vlsi","nuclear",
                "materials_science","naval","ceramics","chemical_eng","biomedical_eng")
    _SCI_KW = ("physics","chemistry","biology","mathematics","statistics","earth_science",
                "environmental_science","astronomy","biotechnology","biochemistry","data_science")
    _MED_KW = ("medicine","surgery","dentistry","pharmacy","nursing","ayurveda",
                "public_health","veterinary","physiotherapy","clinical")

    cluster_counts: Dict[str, int] = {"engineering": 0, "science": 0, "medicine": 0}
    _MAX_PER_CLUSTER = {"engineering": 4, "science": 4, "medicine": 4}
    domain_counts: Dict[str, int] = {"technology": 0, "law": 0}
    _MAX_PER_DOMAIN = {"technology": 4, "law": 3}

    # Textile rarity gate
    _EARTH_SIGNS = {"Taurus","Virgo","Capricorn"}
    textile_allowed = True
    if payload_data is not None:
        planets_d1 = getattr(payload_data, "planets_d1", {})
        planet_signs = {p: info.get("sign","") if isinstance(info,dict) else ""
                       for p, info in planets_d1.items()}
        earth_count = sum(1 for pl in ("Venus","Saturn","Mars")
                         if planet_signs.get(pl,"") in _EARTH_SIGNS)
        textile_allowed = (earth_count >= 2)

    out = []
    for r in results:
        label = r.get("field_label","").lower()
        branch = r.get("branch","").lower()

        # Textile gate
        if "textile" in label or "textile" in branch:
            if not textile_allowed:
                continue

        # Cluster deduplication
        def _in_cluster(kws):
            return any(kw in label or kw in branch for kw in kws)

        cluster = None
        if _in_cluster(_ENG_KW):   cluster = "engineering"
        elif _in_cluster(_SCI_KW): cluster = "science"
        elif _in_cluster(_MED_KW): cluster = "medicine"

        if cluster:
            if cluster_counts[cluster] >= _MAX_PER_CLUSTER[cluster]:
                continue
            cluster_counts[cluster] += 1
        # Domain-level cap: technology and law fields capped to avoid single-domain sweeps.
        dom = r.get("domain", "")
        if dom in _MAX_PER_DOMAIN:
            if domain_counts[dom] >= _MAX_PER_DOMAIN[dom]:
                continue
            domain_counts[dom] += 1
        out.append(r)
    return out


# ─ Modernize-karakas constants ────────────────────────────────────────────────
# Narrower than _MATERIAL_GRIT_FIELDS: only extractive/industrial-era fields
# that have lower growth prospects for risk-seeking students.
_LEGACY_HEAVY_INDUSTRY: frozenset = frozenset({
    "mining_engineering",
    "petroleum_engineering",
    "leather_technology",
})

_CYBER_FIELDS: frozenset = frozenset({
    "cybersecurity",
    "intelligence_security_studies",
})


def _modernize_karakas_modifier(
    field_id: str,
    risk_appetite: str,
    amk: str,
    kp_10_star_lord: str,
    planets_d1: Dict,
) -> float:
    """Modern career-mapping modifier — two independent sub-rules.

    Rule 1 - Legacy industry risk penalty:
      Mining / metallurgy / petroleum / leather get a downward nudge when the
      student's stated risk appetite is HIGH or MODERATE.
      When risk_appetite is LOW the penalty is SUPPRESSED — a risk-averse
      student benefits from the stability of these fields and the material_grit
      boost (+0.15) should stand unchallenged.
        HIGH     -> -0.10
        MODERATE -> -0.05
        LOW      ->  0.00

    Rule 2 - Cybersecurity / InfoSec Mars activation:
      Elevates cyber/security fields when Mars is functionally strong:
      AmK, KP H10 star-lord, or raw shadbala > 400 virupas.
        Match -> +0.08
    """
    result = 0.0

    # Rule 1: legacy heavy-industry risk penalty
    if field_id in _LEGACY_HEAVY_INDUSTRY and risk_appetite not in ("LOW", ""):
        if risk_appetite == "HIGH":
            result -= 0.10
        else:   # MODERATE
            result -= 0.05

    # Rule 2: cybersecurity Mars activation boost
    if field_id in _CYBER_FIELDS:
        mars_info = planets_d1.get("Mars", {})
        mars_shadbala = (mars_info.get("shadbala_virupas", 0)
                         if isinstance(mars_info, dict) else 0)
        if amk == "Mars" or kp_10_star_lord == "Mars" or mars_shadbala > 400:
            result += 0.08

    return result


def _d10_lagna_lord_bonus(affinity: Dict[str, float], d10_chart: Dict,
                          d10_lagna_sign: str, d10_planet_dignities: Dict[str, str]) -> float:
    """Bonus for the D10 (Dashamsha) Lagna Lord, especially if well-placed."""
    if not d10_lagna_sign or not d10_chart:
        return 0.0

    d10_lagna_lord = _SIGN_LORD.get(d10_lagna_sign, "")
    if not d10_lagna_lord:
        return 0.0

    w = affinity.get(d10_lagna_lord, 0.0)
    if w < 0.10:
        return 0.0

    dig = d10_planet_dignities.get(d10_lagna_lord, "")
    bonus = 0.0

    if w >= 0.20 and dig == "EXALTED":   bonus += 0.08
    elif w >= 0.20 and dig == "OWN":     bonus += 0.06
    elif w >= 0.20:                      bonus += 0.04
    elif w >= 0.10 and dig == "EXALTED": bonus += 0.05
    elif w >= 0.10:                      bonus += 0.02

    return min(bonus, 0.10)
