"""JyotishAI — Gap-boost scoring helpers (all _*_bonus / _*_penalty functions)."""
import math as _math
import re as _re
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
from .astro import (
    _get_planetary_aspects, _get_planetary_aspects_weighted, _drishti_bala,
    _detect_planetary_war, _planet_abs_degree,
)

_ALL_PLANETS: Tuple = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")

# ── Functional Status Table (all 12 lagnas) ──────────────────────────────────
# YOGAKARAKA: planet ruling both a kendra (H1/4/7/10) and a trikona (H1/5/9) → boosts.
# MALEFIC: functional malefic for the lagna (primary ruler of H6/H8/H12) → dampen.
# BENEFIC: natural benefic ruling good houses → neutral multiplier (1.0).
# Planets absent from a lagna mapping are treated as NEUTRAL.
_FUNCTIONAL_STATUS: Dict[str, Dict[str, str]] = {
    "Aries":       {"Saturn": "MALEFIC",    "Mercury": "MALEFIC",  "Venus": "MALEFIC",
                    "Jupiter": "MALEFIC",   "Sun": "BENEFIC",      "Mars": "BENEFIC"},
    "Taurus":      {"Saturn": "YOGAKARAKA", "Jupiter": "MALEFIC",  "Mars": "MALEFIC",
                    "Venus": "BENEFIC",     "Mercury": "BENEFIC"},
    "Gemini":      {"Jupiter": "MALEFIC",   "Mars": "MALEFIC",    "Venus": "MALEFIC",
                    "Saturn": "MALEFIC",    "Mercury": "BENEFIC"},
    "Cancer":      {"Mars": "YOGAKARAKA",   "Jupiter": "MALEFIC",  "Saturn": "MALEFIC",
                    "Mercury": "MALEFIC",   "Moon": "BENEFIC"},
    "Leo":         {"Mars": "YOGAKARAKA",   "Saturn": "MALEFIC",   "Venus": "MALEFIC",
                    "Mercury": "MALEFIC",   "Sun": "BENEFIC",      "Jupiter": "BENEFIC"},
    "Virgo":       {"Mars": "MALEFIC",      "Saturn": "MALEFIC",   "Sun": "MALEFIC",
                    "Moon": "MALEFIC",      "Venus": "BENEFIC",    "Mercury": "BENEFIC"},
    "Libra":       {"Saturn": "YOGAKARAKA", "Jupiter": "MALEFIC",  "Mercury": "MALEFIC",
                    "Mars": "MALEFIC",      "Venus": "BENEFIC"},
    "Scorpio":     {"Venus": "MALEFIC",     "Mercury": "MALEFIC",  "Saturn": "MALEFIC",
                    "Mars": "BENEFIC",      "Jupiter": "BENEFIC"},
    "Sagittarius": {"Venus": "MALEFIC",     "Mercury": "MALEFIC",  "Saturn": "MALEFIC",
                    "Jupiter": "BENEFIC",   "Mars": "BENEFIC"},
    "Capricorn":   {"Venus": "YOGAKARAKA",  "Jupiter": "MALEFIC",  "Mars": "MALEFIC",
                    "Moon": "MALEFIC",      "Saturn": "BENEFIC"},
    "Aquarius":    {"Venus": "YOGAKARAKA",  "Jupiter": "MALEFIC",  "Moon": "MALEFIC",
                    "Mercury": "BENEFIC",   "Saturn": "BENEFIC"},
    "Pisces":      {"Saturn": "MALEFIC",    "Venus": "MALEFIC",    "Sun": "MALEFIC",
                    "Mercury": "MALEFIC",   "Jupiter": "BENEFIC",  "Mars": "BENEFIC"},
}

# Odd signs (for Mrita Avastha detection: degree 24°–30° in odd sign = dead state)
_ODD_SIGNS: Set[str] = {"Aries","Gemini","Leo","Libra","Sagittarius","Aquarius"}


def _functional_status_factor(planet: str, lagna_sign: str) -> float:
    """Return a dignity multiplier adjustment based on functional lordship.

    YOGAKARAKA: 1.15 (slight uplift — ruling both kendra and trikona)
    MALEFIC:    0.60 (dampen — dignity amplifies dusthana significations)
    BENEFIC:    1.00 (neutral — natural + functional benefic; existing bonuses apply)
    NEUTRAL:    1.00 (no data)
    """
    if not lagna_sign:
        return 1.0
    status = _FUNCTIONAL_STATUS.get(lagna_sign, {}).get(planet, "NEUTRAL")
    if status == "YOGAKARAKA":
        return 1.15
    if status == "MALEFIC":
        return 0.60
    return 1.0


def _d1_vitality_coefficient(planet: str, payload) -> float:
    """D1 structural vitality coefficient (0.0–1.0) for a planet.

    Divisional charts have no independent physical existence; their scores must
    be gated by the planet's D1 integrity.  Three structural impairments reduce
    a planet's ability to manifest even exalted varga results:

      • Combustion (absorbed by Sun): coefficient 0.45
      • Graha Yuddha loser:
            - Bitter defeat (by a natural enemy): 0.35
            - Friendly defeat:                   0.60
      • Mrita Avastha (dead degrees):
            - Odd signs 24°–30°:                 0.15
            - Even signs 0°–6°:                  0.15
      • Multiple impairments → take the lowest coefficient.
      • No impairment → 1.0
    """
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    combust    = set(getattr(payload, "combust_planets", []) or [])
    coeff      = 1.0

    # Combustion check
    if planet in combust:
        coeff = min(coeff, 0.45)

    # Graha Yuddha check (re-detect from planets_d1 each call; results are tiny)
    if planets_d1:
        war_result = _detect_planetary_war(planets_d1)
        war_status = war_result.get(planet, "")
        if war_status == "loser_bitter":
            coeff = min(coeff, 0.35)
        elif war_status == "loser_friendly":
            coeff = min(coeff, 0.60)

    # Mrita Avastha check — with AK and own-sign dignity floors
    pdata = planets_d1.get(planet, {})
    if pdata:
        sign   = pdata.get("sign", "")
        degree = float(pdata.get("degree", 0))
        is_mrita = (sign in _ODD_SIGNS and degree >= 24.0) or (sign and sign not in _ODD_SIGNS and degree < 6.0)
        if is_mrita:
            mrita_floor = 0.15  # default dead-state coefficient
            # AK protection: soul indicator retains partial manifestation capacity
            _ak = getattr(payload, "atmakaraka", "") or ""
            if planet == _ak:
                mrita_floor = max(mrita_floor, 0.45)
            # Own-sign / exalted mitigation: dignity partially shields from dead-state
            _digs = getattr(payload, "planet_dignities", {}) or {}
            _dig  = _digs.get(planet, "")
            if _dig == "EXALTED":
                mrita_floor = max(mrita_floor, 0.40)
            elif _dig == "OWN":
                mrita_floor = max(mrita_floor, 0.35)
            coeff = min(coeff, mrita_floor)

    return coeff


def _wm(kw: str, text: str) -> bool:
    """Word-boundary match — prevents 'art' hitting 'artificial', 'age' hitting 'management'.

    Underscores in field_ids (e.g. 'fine_arts') are treated as word separators
    so 'arts' correctly matches 'fine_arts' → 'fine arts'.
    """
    import re as _re_local
    normalized = text.replace("_", " ")
    return bool(_re_local.search(r'\b' + _re_local.escape(kw) + r'\b', normalized))


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
    "Rahu":    ["artificial intelligence","cybersecurity","space","biotechnology","forensic","nuclear","robotics","information technology","foreign","unconventional","machine learning","data science","hospital","technology","economics","data","finance","quantitative","computational"],
    "Ketu":    ["research","philosophy","alternative medicine","ayurveda","spiritual","occult","investigation","archaeology"],
}
_KARAKAMSHA_CO_LORD: Dict[str, str] = {"Aquarius":"Rahu","Scorpio":"Ketu","Pisces":"Ketu"}
# A9 fix: constants canonically defined in constants.py — import from there
from .constants import (_D24_ACADEMIC_KW, _H12_FIELDS, _H6_FIELDS, _H9_FIELDS,
                        _H5_FIELDS, _FRONTIER_KW, _TRADITIONAL_KW)
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
                "management","politics","administration"],
    "Ketu":    ["research","spiritual","occult","philosophy","alternative medicine",
                "ayurveda","forensic","investigation","archaeology"],
    "Rahu":    ["technology","foreign","innovation","data science","media","cinema",
                "politics","mass communication","artificial intelligence"],
}

# A9 fix: _MAHESHWARA_DOMAIN_KW imported from constants.py
from .constants import _MAHESHWARA_DOMAIN_KW  # noqa: F811

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
    if not any(_wm(kw, label.lower()) for kw in kws):
        return 0.0
    w = affinity.get(maheshwara_lord, 0.0)
    if   w >= 0.25: return 0.07
    if   w >= 0.15: return 0.04
    if   w >= 0.08: return 0.02
    return 0.0

# ── Gap-boost helper constants (extracted from original monolith) ──────────
_YOGA_DOMAIN_KW: Dict[str, List[str]] = {
    "Saraswati":    ["education","research","mathematics","science","law","literature","philosophy","economics","design","management","statistics","medicine","data","commerce","computer","analytics","writing","scholarship"],
    "GajaKesari":   ["law","education","philosophy","management","public policy","policy","economics","medicine","psychology","international","governance"],
    "BudhaAditya":  ["research","computer","artificial intelligence","data science","communication","statistics","mathematics","journalism","analytics","science","space"],
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

# Gap-5: Which planets form each yoga (for quality-grading the bonus).
# Mahapurusha yogas are formed by a single planet in own/exalt in a kendra.
# Compound yogas list all forming planets — quality = average of their dignities.
_YOGA_FORMING_PLANETS: Dict[str, List[str]] = {
    "Hamsa":          ["Jupiter"],
    "Ruchaka":        ["Mars"],
    "Shasha":         ["Saturn"],
    "Malavya":        ["Venus"],
    "Bhadra":         ["Mercury"],
    "GajaKesari":     ["Jupiter", "Moon"],
    "BudhaAditya":    ["Sun", "Mercury"],
    "Saraswati":      ["Venus", "Mercury", "Jupiter"],
    "ChandraMangala": ["Moon", "Mars"],
}

def _yoga_quality_factor(yoga: str, planet_dignities: Dict[str, str]) -> float:
    """Return a 0.30–1.0 quality multiplier for a yoga based on its forming planets.

    A pristine Mahapurusha yoga (planet in own/exalt kendra) → full 1.0.
    Same yoga with a debilitated or combust-weakened planet → 0.30–0.65.
    Yogas not in the map get 0.75 (mild benefit of the doubt).
    """
    planets = _YOGA_FORMING_PLANETS.get(yoga)
    if not planets:
        return 0.75
    _DIG_SCORE = {"EXALTED": 1.0, "OWN": 0.85, "NEECHA_BHANGA": 0.60,
                  "": 0.65, "DEBILITATED": 0.30}
    scores = [_DIG_SCORE.get(planet_dignities.get(p, ""), 0.65) for p in planets]
    return sum(scores) / len(scores)

# ── Functional Malefic Map (Parashari) ───────────────────────────────────────
# For each lagna, planets that lord dusthana houses (H6/H8/H12) are functional
# malefics. Their exaltation/own-sign strength amplifies dusthana significations,
# not career success. "pure" = rules only dusthana(s); "mixed" = rules dusthana
# plus a kendra/trikona/upachaya (some tempering of maleficence).
# Lagna lord is always excluded (it is a functional benefic by default).
_FUNCTIONAL_MALEFIC_MAP: Dict[str, Dict[str, str]] = {
    "Aries":       {"Mercury": "mixed",  "Jupiter": "mixed"},
    "Taurus":      {"Jupiter": "mixed",  "Mars":    "mixed"},
    "Gemini":      {"Mars":    "mixed",  "Saturn":  "mixed",  "Venus":   "mixed"},
    "Cancer":      {"Jupiter": "mixed",  "Saturn":  "mixed",  "Mercury": "mixed"},
    "Leo":         {"Saturn":  "mixed",  "Jupiter": "mixed",  "Moon":    "pure"},
    "Virgo":       {"Saturn":  "mixed",  "Mars":    "mixed",  "Sun":     "pure"},
    "Libra":       {"Jupiter": "mixed",  "Mercury": "mixed"},
    "Scorpio":     {"Mercury": "mixed",  "Venus":   "mixed"},
    "Sagittarius": {"Venus":   "mixed",  "Moon":    "pure",   "Mars":    "mixed"},
    "Capricorn":   {"Mercury": "mixed",  "Sun":     "pure",   "Jupiter": "mixed"},
    "Aquarius":    {"Moon":    "pure",   "Mercury": "mixed"},
    "Pisces":      {"Sun":     "pure",   "Venus":   "mixed",  "Saturn":  "mixed"},
}

def _functional_malefic_dig_factor(planet: str, lagna_sign: str, dig: str) -> float:
    """Return a dampening factor for a planet's dignity bonus when it is a
    functional malefic for the chart's lagna.

    Classical logic: an exalted FM still produces results, but in its own
    dusthana domain (obstacles, litigation, hidden crises), not smooth career
    success.  Factor is applied as a multiplier on the dignity-driven bonus.

    Returns 1.0 (no dampening) when the planet is not a FM for this lagna.
    """
    if not lagna_sign or dig not in ("EXALTED", "OWN"):
        return 1.0
    fm_type = _FUNCTIONAL_MALEFIC_MAP.get(lagna_sign, {}).get(planet, "")
    if not fm_type:
        return 1.0
    if fm_type == "pure":
        return 0.55 if dig == "EXALTED" else 0.65
    # mixed — rules dusthana + kendra/trikona; partial dampening
    return 0.75 if dig == "EXALTED" else 0.80

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


def _kp_career_h2h11_strength(affinity: Dict[str, float], kp_sigs: Dict) -> float:
    """KP 4-level significator scan across H2 (wealth) and H11 (gains) — secondary career branch.

    Classical KP requires H2+H6+H10+H11 to connect for career materialisation.
    H2 and H11 matter especially when H10 has only one L1 significator.
    House priority: H11=1.0 (income/gains), H2=0.8 (accumulated wealth/speech).
    Level weights: L1=1.0, L2=0.75, L3=0.50, L4=0.25. Normalised to 0-1."""
    if not kp_sigs:
        return 0.0
    _HP = {2: 0.8, 11: 1.0}
    _LW = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25}
    score = 0.0
    for planet, weight in affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(["level_1", "level_2", "level_3", "level_4"]):
            matched = [h for h in sig.get(key, []) if h in _HP]
            if matched:
                hp = max(_HP[h] for h in matched)
                score += weight * _LW[idx] * hp
                break
    max_possible = sum(affinity.values()) * 1.0 if affinity else 1.0
    return min(score / max_possible, 1.0) if max_possible > 0 else 0.0


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


def _kp_edu_branch_strength(affinity: Dict[str, float], kp_sigs: Dict) -> float:
    """KP 4-level significator scan across all education houses (H4, H5, H9, H11).

    Implements the KP spec house-priority matrix for EDUCATION mode:
      H11=1.5 (gains/success), H4=1.2 (stream selection), H9=1.2 (specialisation),
      H5=1.0 (intellect/creativity).
    Level weights: L1=1.0, L2=0.75, L3=0.50, L4=0.25.
    Score normalised to 0–1 against the theoretical maximum.
    H10 is intentionally excluded here — it is handled by _kp_h10_branch_strength
    as the career anchor so the two signals remain orthogonal.
    """
    if not kp_sigs:
        return 0.0
    _HP = {4: 1.2, 5: 1.0, 9: 1.2, 11: 1.5}
    _LW = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25}
    score = 0.0
    for planet, weight in affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(["level_1", "level_2", "level_3", "level_4"]):
            for house in sig.get(key, []):
                if house in _HP:
                    score += weight * _LW[idx] * _HP[house]
    # Theoretical maximum: every affinity unit at L1 in H11 (priority 1.5)
    max_possible = sum(affinity.values()) * 1.5 if affinity else 1.0
    return min(score / max_possible, 1.0) if max_possible > 0 else 0.0


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


_SPACE_AEROSPACE_HINTS: frozenset = frozenset({
    "aerospace", "aeronautical", "astronautical", "space", "satellite",
    "rocket", "propulsion", "orbital", "mission", "launch", "astronomy",
    "astrophysics", "planetary", "remote sensing", "earth observation",
    "space systems", "space science", "space technology",
})


def _space_aerospace_signal(eff_strengths: Dict[str, float]) -> float:
    """Cluster signal for space/aerospace-style vocational signatures."""
    mars = max(0.0, eff_strengths.get("Mars", 0.0))
    rahu = max(0.0, eff_strengths.get("Rahu", 0.0))
    saturn = max(0.0, eff_strengths.get("Saturn", 0.0))
    jupiter = max(0.0, eff_strengths.get("Jupiter", 0.0))
    ketu = max(0.0, eff_strengths.get("Ketu", 0.0))
    raw = 0.30 * mars + 0.26 * rahu + 0.18 * saturn + 0.14 * jupiter + 0.12 * ketu
    return max(0.0, min(1.0, raw / 2.0))


def _space_aerospace_cluster_bonus(
    field_id: str,
    label: str,
    affinity: Dict[str, float],
    eff_strengths: Dict[str, float],
) -> float:
    """Boost modern space/aerospace branches when the cluster is present."""
    # Include raw snake_case field_id AND its space-form so both "space_systems"
    # and "space systems" exact-match lookups resolve correctly downstream.
    text = f"{field_id} {field_id.replace('_', ' ')} {label}".lower()
    if not any(h in text for h in _SPACE_AEROSPACE_HINTS):
        return 0.0

    signal = _space_aerospace_signal(eff_strengths)
    base = 0.04 + 0.10 * signal
    if any(k in text for k in ("aerospace", "aeronautical", "astronautical", "rocket", "propulsion")):
        base += 0.05
        base += 0.03 * min(1.0, affinity.get("Mars", 0.0) + affinity.get("Rahu", 0.0) + affinity.get("Saturn", 0.0))
    elif any(k in text for k in ("satellite", "remote sensing", "earth observation")):
        base += 0.04
        base += 0.03 * min(1.0, affinity.get("Mercury", 0.0) + affinity.get("Rahu", 0.0))
    elif any(k in text for k in ("astronomy", "astrophysics", "planetary")):
        base += 0.05
        base += 0.03 * min(1.0, affinity.get("Ketu", 0.0) + affinity.get("Jupiter", 0.0))
    elif "space systems" in text or "space science" in text or "space technology" in text:
        base += 0.04
        base += 0.03 * min(1.0, affinity.get("Rahu", 0.0) + affinity.get("Mars", 0.0))

    if "space_systems" in text or "mission_design" in text:
        base += 0.12
    if "astronautical" in text or "rocket_propulsion" in text:
        base += 0.08

    return min(0.22, base)


def _space_extractive_counterweight(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Softly reduce extractive branches when the chart is space-dominant."""
    text = f"{field_id} {label}".lower()
    if not any(k in text for k in ("mining", "petroleum", "metallurgical", "metallurgy")):
        return 0.0
    signal = _space_aerospace_signal(eff_strengths)
    if signal < 0.45:
        return 0.0
    return -min(0.08, 0.03 + 0.06 * signal)


def _life_science_signal(eff_strengths: Dict[str, float]) -> float:
    """Cluster signal for medicine, psychology, biotech, and research-heavy life sciences."""
    moon = max(0.0, eff_strengths.get("Moon", 0.0))
    jupiter = max(0.0, eff_strengths.get("Jupiter", 0.0))
    venus = max(0.0, eff_strengths.get("Venus", 0.0))
    saturn = max(0.0, eff_strengths.get("Saturn", 0.0))
    mercury = max(0.0, eff_strengths.get("Mercury", 0.0))
    raw = 0.28 * moon + 0.24 * jupiter + 0.18 * venus + 0.16 * saturn + 0.14 * mercury
    return max(0.0, min(1.0, raw / 2.0))


def _life_science_cluster_bonus(
    field_id: str,
    label: str,
    affinity: Dict[str, float],
    eff_strengths: Dict[str, float],
) -> float:
    """Boost medicine / neuroscience / biotech / genetics branches when life-science signals are strong."""
    # Include raw snake_case field_id AND its space-form so underscore-keyed exact
    # matches like "healthcare_management" resolve even when label uses spaces.
    text = f"{field_id} {field_id.replace('_', ' ')} {label}".lower()
    if not any(k in text for k in (
        "medicine", "medical", "clinical", "psychology", "psychiatry", "neuroscience",
        "bioinformatics", "biotechnology", "genetic", "genomics", "biomedical",
        "pharmacy", "public health", "healthcare", "radiography", "laboratory",
        "pathology", "prosthetics", "physiotherapy", "nursing", "veterinary",
    )):
        return 0.0

    signal = _life_science_signal(eff_strengths)
    base = 0.03 + 0.11 * signal
    if any(k in text for k in ("psychology", "psychiatry", "neuroscience", "cognitive")):
        base += 0.04
        base += 0.03 * min(1.0, affinity.get("Moon", 0.0) + affinity.get("Mercury", 0.0) + affinity.get("Jupiter", 0.0))
    elif any(k in text for k in ("biotech", "bioinformatics", "genetic", "genomics", "biomedical")):
        base += 0.03
        base += 0.03 * min(1.0, affinity.get("Mercury", 0.0) + affinity.get("Jupiter", 0.0) + affinity.get("Saturn", 0.0))
    elif any(k in text for k in ("medicine", "medical", "pharmacy", "public health", "healthcare", "radiography", "laboratory", "pathology", "prosthetics", "physiotherapy", "nursing", "veterinary")):
        base += 0.03
        base += 0.03 * min(1.0, affinity.get("Moon", 0.0) + affinity.get("Jupiter", 0.0) + affinity.get("Saturn", 0.0))

    if "research" in text:
        base += 0.02
    if "healthcare_management" in text:
        base += 0.16
    if "public_health" in text:
        base += 0.08
    if "medical_research" in text:
        base += 0.05

    return min(0.24, base)




def _life_science_space_counterweight(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Reduce space fields when life-science signatures dominate and space signals are weak."""
    text = f"{field_id} {label}".lower()
    if not any(k in text for k in _SPACE_AEROSPACE_HINTS):
        return 0.0
    life_signal = _life_science_signal(eff_strengths)
    if life_signal < 0.55:
        return 0.0
    if _space_aerospace_signal(eff_strengths) >= 0.45:
        return 0.0
    return -min(0.07, 0.02 + 0.05 * life_signal)


def _life_science_engineering_counterweight(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Reduce non-life engineering branches when the chart strongly favors life sciences."""
    text = f"{field_id} {label}".lower()
    if "engineering" not in text:
        return 0.0
    if any(k in text for k in ("biomedical", "biotechnology", "bioinformatics", "medical", "health", "pharmacy", "clinical")):
        return 0.0
    life_signal = _life_science_signal(eff_strengths)
    if life_signal < 0.58:
        return 0.0
    if any(k in text for k in ("space", "aerospace", "aeronautical", "astronautical", "rocket")):
        return -min(0.12, 0.03 + 0.09 * life_signal)
    if any(k in text for k in ("materials", "metallurgical", "production", "industrial", "mechanical", "civil", "mining", "petroleum", "automotive", "chemical")):
        return -min(0.08, 0.02 + 0.06 * life_signal)
    return -min(0.05, 0.015 + 0.04 * life_signal)


def _priority_cluster_field_bonus(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Final, bounded bonus for the most strongly signaled priority fields.

    This is used only to keep the leaderboard's top-20 from dropping the
    chart's dominant life-science or aerospace branches behind unrelated
    extractive/structural fields.
    """
    text = f"{field_id} {label}".lower()
    life_signal = _life_science_signal(eff_strengths)
    space_signal = _space_aerospace_signal(eff_strengths)

    if life_signal >= 0.56:
        if "medical_research" in text:
            return min(0.35, 0.18 + 0.22 * life_signal)
        if "healthcare_management" in text:
            return min(0.22, 0.08 + 0.14 * life_signal)
        if "public_health" in text:
            return min(0.24, 0.10 + 0.16 * life_signal)
        if "psychiatry" in text or "neuroscience" in text:
            return min(0.15, 0.05 + 0.10 * life_signal)
        if any(k in text for k in ("medicine", "medical", "psychiatry", "neuroscience", "psychology", "pharmacy", "biotech", "bioinformatics", "genetic")):
            return min(0.10, 0.04 + 0.08 * life_signal)

    if space_signal >= 0.45:
        if "space_systems_engineering" in text or "space_systems" in text:
            return min(0.28, 0.12 + 0.18 * space_signal)
        if "astronautical" in text or "rocket_propulsion" in text:
            return min(0.14, 0.06 + 0.10 * space_signal)
        if "planetary_science" in text or "astronomy_astrophysics" in text:
            return min(0.12, 0.05 + 0.08 * space_signal)

    return 0.0

def _h10_sublord_bonus(affinity, kp_cusps):
    h10 = kp_cusps.get("H10",{}); sub_lord = h10.get("sub_lord","")
    if not sub_lord: return 0.0
    w = affinity.get(sub_lord, 0.0)
    if w >= 0.30: return 0.08
    if w >= 0.20: return 0.05
    if w >= 0.10: return 0.02
    return 0.0
def _get_prime_career_lord_local(dasha_seq):
    """Prime career lord — ages 25-45 overlap (inline; avoids circular import from engine)."""
    lord_durations = {}
    for d in dasha_seq:
        start = d.get("start_age"); end = d.get("end_age")
        if start is None or end is None: continue
        overlap_start = max(25.0, start); overlap_end = min(45.0, end)
        if overlap_start < overlap_end:
            l = d.get("lord", "")
            lord_durations[l] = lord_durations.get(l, 0.0) + (overlap_end - overlap_start)
    if not lord_durations: return ""
    return max(lord_durations.items(), key=lambda x: x[1])[0]


def _dasha_bonus(label, payload):
    """Active Mahadasha keyword bonus — smoothly blended over the student transition window.

    CLIFF FIX: Replaces the hard binary cut at age 22 with a linear blend over ages 18–25.
    Below 18 → pure prime-career lord (ages 25–45 window).
    Age 18–25 → weighted blend: prime lord weight fades from 1.0 → 0.0 as current age
                rises from 18 → 25.  Current lord weight rises correspondingly.
    Above 25 → pure current active lord.

    Dignity-scaled: a strong dasha lord sends a stronger timing signal.
      EXALTED  → 0.12  (peak timing activation)
      OWN      → 0.10  (full signal)
      neutral  → 0.08  (moderate signal)
      DEBIL    → 0.05  (weakened timing)

    Triple-stacking guard: run_engine caps total dasha-family boosts at 0.22.
    """
    dasha_seq   = getattr(payload, "dasha_sequence", [])
    current_age = float(getattr(payload, "current_age", 0))
    planet_digs = getattr(payload, "planet_dignities", {})

    def _base_for(lord: str) -> float:
        if not lord: return 0.0
        dig = planet_digs.get(lord, "")
        b = {"EXALTED": 0.12, "OWN": 0.10, "NEECHA_BHANGA": 0.09}.get(dig, 0.08)
        return 0.05 if dig == "DEBILITATED" else b

    prime_lord   = _get_prime_career_lord_local(dasha_seq) or ""
    current_lord = _get_active_dasha_lord(dasha_seq, current_age) or ""
    _lbl = label.lower()

    if current_age < 18:
        # Pure projection to prime career window
        lord = prime_lord or current_lord
        if not lord: return 0.0
        if not any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(lord, [])): return 0.0
        return _base_for(lord)

    if current_age >= 25:
        # Fully in current-dasha territory
        if not current_lord: return 0.0
        if not any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(current_lord, [])): return 0.0
        return _base_for(current_lord)

    # Transition zone 18–25: linearly blend prime lord → current lord
    t = (current_age - 18.0) / 7.0          # 0.0 at age 18, 1.0 at age 25
    prime_kw_match   = prime_lord   and any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(prime_lord,   []))
    current_kw_match = current_lord and any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(current_lord, []))
    prime_contrib   = (1.0 - t) * _base_for(prime_lord)   if prime_kw_match   else 0.0
    current_contrib = t          * _base_for(current_lord) if current_kw_match else 0.0
    blended = prime_contrib + current_contrib
    return blended if blended > 0.0 else 0.0

def _karakamsha_bonus(affinity, karakamsha):
    if not karakamsha: return 0.0
    sign_lord = _SIGN_LORD.get(karakamsha,""); co_lord = _KARAKAMSHA_CO_LORD.get(karakamsha,"")
    bonus = 0.0
    if sign_lord and affinity.get(sign_lord,0) >= 0.20: bonus += 0.05
    if co_lord   and affinity.get(co_lord,  0) >= 0.20: bonus += 0.03
    return min(bonus, 0.08)

def _combustion_degree_factor(planet: str, planets_d1: dict) -> float:
    """M3: Sliding combustion coefficient based on exact degree proximity to the Sun.

    Returns a multiplier (0.0–1.5) applied to the base combustion penalty:
      Cazimi  (<1°)       →  0.0   (no penalty; Cazimi = in the heart of the Sun, amplified)
      Mild    (1°–6°)     →  0.50  (partial penalty; outer edge of deep combustion)
      Standard(6°–12°)   →  1.00  (full penalty; standard combust range)
      Fallback (no data) →  1.00  (conservative default when degree info is absent)

    Binary combust flag for degrees beyond 12° should not appear in combust_planets,
    but if it does the factor defaults to 0.0 (not penalised beyond expected range).
    """
    if not planets_d1:
        return 1.0
    sun_d = planets_d1.get("Sun", {})
    pla_d = planets_d1.get(planet, {})
    if not sun_d or not pla_d:
        return 1.0
    sun_abs = _planet_abs_degree(sun_d.get("sign", ""), float(sun_d.get("degree", 0)))
    pla_abs = _planet_abs_degree(pla_d.get("sign", ""), float(pla_d.get("degree", 0)))
    dist = abs(sun_abs - pla_abs)
    if dist > 180.0:
        dist = 360.0 - dist
    if dist < 1.0:
        return 0.0   # Cazimi — no penalty
    elif dist < 6.0:
        return 0.50  # Mild combustion
    elif dist < 12.0:
        return 1.00  # Standard combustion
    else:
        return 0.0   # Beyond combust range — shouldn't be in combust_planets, guard anyway


def _ak_combustion_penalty(affinity, ak, combust_planets, planet_dignities=None, planets_d1=None):
    """M3: Penalty now uses degree-proximity sliding scale instead of binary flag.

    Cazimi AK (<1° from Sun) receives zero penalty.
    Mild combustion (1°–6°) receives half the standard penalty.
    """
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
    # M3: apply degree-proximity factor
    base *= _combustion_degree_factor(ak, planets_d1 or {})
    return base

def _d24_full_chart_bonus(field_affinity: Dict[str, float], payload) -> float:
    """D24 (Siddhamsha) full-chart evaluation — Gap-1 fix.

    The prior implementation (_d24_ak_delta) only checked the AK planet's
    dignity in D24.  This function evaluates ALL planets in educationally
    significant D24 houses (H4 = learning foundation, H5 = intelligence/siddhi,
    H10 = peak academic achievement) and rewards dignified planets whose natural
    signification aligns with the field's affinity profile.

    Scoring per qualifying planet:
      - EXALTED in D24-H5 (siddhi house): up to 0.14 * field_affinity
      - EXALTED in D24-H10: up to 0.11 * field_affinity
      - EXALTED in D24-H4: up to 0.08 * field_affinity
      - OWN reduces each tier by ~35%
    Cap: 0.15 total (prevents a single D24 concentration from overwhelming D1 signal).
    """
    div_charts  = getattr(payload, "divisional_charts", {}) or {}
    d24         = div_charts.get("D24_siddhamsam", {}) or {}
    d24_digs    = getattr(payload, "d24_planet_dignities", {}) or {}

    if not d24 or not d24_digs:
        return 0.0

    d24_lagna = d24.get("Lagna", "")
    if not d24_lagna:
        return 0.0

    _SIGNS = sorted(_SIGN_NUM, key=_SIGN_NUM.__getitem__)
    try:
        lagna_idx = _SIGNS.index(d24_lagna)
    except ValueError:
        return 0.0

    # House weight: H5 (siddhi) > H10 > H4
    _HOUSE_W = {5: 0.14, 10: 0.11, 4: 0.08}

    bonus = 0.0
    for planet, sign in d24.items():
        if planet == "Lagna":
            continue
        dig = d24_digs.get(planet, "")
        if dig not in ("EXALTED", "OWN"):
            continue
        w = field_affinity.get(planet, 0.0)
        if w < 0.08:
            continue
        try:
            sign_idx  = _SIGNS.index(sign)
        except ValueError:
            continue
        d24_house = (sign_idx - lagna_idx) % 12 + 1
        hw = _HOUSE_W.get(d24_house)
        if hw is None:
            continue
        dig_factor = 1.0 if dig == "EXALTED" else 0.65
        # Gate by D1 vitality: a structurally impaired planet cannot deliver D24 results
        vit = _d1_vitality_coefficient(planet, payload)
        bonus += w * hw * dig_factor * vit

    return min(bonus, 0.15)


def _d24_ak_delta(label, payload):
    ak = getattr(payload,"atmakaraka",""); d24_digs = getattr(payload,"d24_planet_dignities",{})
    if not ak or not d24_digs: return 0.0
    if not any(_wm(kw, label.lower()) for kw in _D24_ACADEMIC_KW): return 0.0
    dig = d24_digs.get(ak,"")
    if dig == "EXALTED":    return  0.10
    if dig == "OWN":        return  0.05
    if dig == "DEBILITATED": return -0.05
    return 0.0

def _lagna_lord_bonus(label, payload):
    lagna_lord = getattr(payload,"lagna_lord",""); planet_house = getattr(payload,"planet_house",{})
    if not lagna_lord: return 0.0
    ll_house = planet_house.get(lagna_lord,0); label_lower = label.lower()
    if ll_house == 12 and any(_wm(kw, label_lower) for kw in _H12_FIELDS): return 0.08
    if ll_house == 10: return 0.05
    if ll_house ==  9 and any(_wm(kw, label_lower) for kw in _H9_FIELDS):  return 0.05
    if ll_house ==  6 and any(_wm(kw, label_lower) for kw in _H6_FIELDS):  return 0.06
    if ll_house ==  5 and any(_wm(kw, label_lower) for kw in _H5_FIELDS):  return 0.06
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
    is_frontier    = any(_wm(kw, label_lower) for kw in _FRONTIER_KW)
    is_traditional = any(_wm(kw, label_lower) for kw in _TRADITIONAL_KW)

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
    dig = digs.get(yk, "")
    # LS3 fix: debilitated YK returns 0; caller uses _yogakaraka_debilitation_penalty()
    # to accumulate the penalty into gap_penalty (not silently subtract from gap_boost).
    if dig == "DEBILITATED": return 0.0
    dig_mod = {"EXALTED": 1.3, "OWN": 1.1, "NEECHA_BHANGA": 1.05}.get(dig, 1.0)
    if   w >= 0.20: base = 0.12
    elif w >= 0.12: base = 0.07
    elif w >= 0.07: base = 0.04
    else: return 0.0
    return max(0.0, base * ratio * dig_mod)


def _yogakaraka_debilitation_penalty(affinity, lagna_sign, shadbala, digs):
    """LS3 fix: gap_penalty contribution when the Yogakaraka is debilitated.
    Called by engine.py gap_penalty accumulator instead of reducing gap_boost."""
    yk = _YOGAKARAKA_PLANET.get(lagna_sign, _FUNCTIONAL_TRIKONA_FALLBACK.get(lagna_sign,""))
    if not yk: return 0.0
    if digs.get(yk, "") != "DEBILITATED": return 0.0
    w = affinity.get(yk, 0.0)
    if w < 0.07: return 0.0
    ratio = shadbala.get(yk, 300.0) / _PLANET_MIN_SHADBALA.get(yk, 300.0)
    return round(min(0.06, 0.05 * ratio * (1.0 if w >= 0.20 else 0.6)), 4)

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
    # Soften dig_mult: field_affinity already encodes dignity via effective strengths.
    # Applying a heavy multiplier here causes exponential double-compounding.
    dig_mult = {"EXALTED": 1.15, "OWN": 1.08, "NEECHA_BHANGA": 1.0, "DEBILITATED": 0.70}.get(dig, 1.0)
    if   w >= 0.30: base = 0.12
    elif w >= 0.20: base = 0.08
    elif w >= 0.10: base = 0.04
    else: return 0.0
    return min(base * ratio * dig_mult, 0.18)


# Natural signification keywords for each planet when exalted —
# classical rule: exalted planets deliver superior results in their domains.
_EXALT_DOMAIN_KW: Dict[str, List[str]] = {
    # Use complete/plural word forms so _wm (word-boundary match) works correctly.
    # e.g. "arts" not "art" (avoids "artificial"), "performing" not "perform".
    "Venus":   ["arts", "music", "design", "fashion", "film", "performing arts",
                "fine arts", "aesthetics", "creative arts", "visual arts",
                "textile", "interior design", "dance", "theatre"],
    "Jupiter": ["law", "philosophy", "education", "medicine", "research", "management",
                "economics", "theology", "international"],
    "Moon":    ["nursing", "psychology", "social work", "ecology", "public health", "counseling",
                "hospitality", "aquaculture", "nutrition"],
    "Mars":    ["engineering", "defence", "military", "surgery", "sports", "mechanical"],
    "Mercury": ["data science", "computer science", "mathematics", "accounting",
                "statistics", "communication"],
    "Saturn":  ["mining", "civil engineering", "metallurgy", "agriculture", "industrial",
                "petroleum", "construction", "materials science"],
    "Sun":     ["civil services", "administration", "government", "leadership", "energy"],
}


def _exalted_planet_domain_bonus(affinity: Dict[str, float],
                                  planet_dignities: Dict[str, str],
                                  label: str,
                                  lagna_sign: str = "") -> float:
    """Bonus when an EXALTED/OWN planet's natural signification matches the field label.

    Classical principle: a planet in uccha (exaltation) delivers its highest
    results in its own domain.  This ensures e.g. exalted Venus in Pisces
    actively promotes arts/design fields for that chart.

    Functional-malefic dampening (Gap-4 fix): if the dignified planet is a
    functional malefic for the chart's lagna (lord of H6/H8/H12), its exaltation
    amplifies dusthana significations rather than smooth career success — so the
    bonus is reduced via _functional_malefic_dig_factor().

    Uses whole-word boundary matching (_wm) to prevent false positives.
    """
    label_lower = label.lower()
    bonus = 0.0
    for planet, kws in _EXALT_DOMAIN_KW.items():
        dig = planet_dignities.get(planet, "")
        if dig not in ("EXALTED", "OWN"):
            continue
        w = affinity.get(planet, 0.0)
        if w < 0.15:
            continue
        if not any(_wm(kw, label_lower) for kw in kws):
            continue
        if   w >= 0.35: raw = 0.10
        elif w >= 0.25: raw = 0.07
        else:           raw = 0.04
        # OWN is slightly weaker than EXALTED
        if dig == "OWN":
            raw *= 0.70
        fm_factor  = _functional_malefic_dig_factor(planet, lagna_sign, dig)
        # Additionally apply functional status factor (MALEFIC→0.6×, YOGAKARAKA→1.15×)
        fs_factor  = _functional_status_factor(planet, lagna_sign)
        bonus += raw * fm_factor * fs_factor
    return min(bonus, 0.15)

def _ul_lord_bonus(affinity, upapada_lagna):
    ul_lord = _SIGN_LORD.get(upapada_lagna,"")
    if not ul_lord: return 0.0
    w = affinity.get(ul_lord, 0.0)
    if w >= 0.25: return 0.06
    if w >= 0.15: return 0.03
    return 0.0

def _kp_edu_starlord_bonus(affinity, kp_cusps):
    # KP rule: the Sub Lord (not the Star Lord) is the structural gate that
    # determines whether a house's results fructify.  All three education CSL
    # targets — H4 (stream), H5 (intellect), H9 (higher learning) — are read
    # from sub_lord.  Cap raised from 0.05 → 0.08 to reflect three cusps.
    h4_sub = kp_cusps.get("H4", {}).get("sub_lord", "")
    h5_sub = kp_cusps.get("H5", {}).get("sub_lord", "")
    h9_sub = kp_cusps.get("H9", {}).get("sub_lord", "")
    bonus = 0.0
    for sl in set(filter(None, [h4_sub, h5_sub, h9_sub])):
        w = affinity.get(sl, 0.0)
        if w >= 0.25: bonus += 0.03
        elif w >= 0.15: bonus += 0.02
    return min(bonus, 0.08)

def _d9_ak_delta(label, payload):
    ak = getattr(payload,"atmakaraka",""); d9_digs = getattr(payload,"d9_planet_dignities",{})
    if not ak or not d9_digs: return 0.0
    dig = d9_digs.get(ak,"")
    raw = 0.0
    if dig == "EXALTED":     raw =  0.06
    elif dig == "OWN":       raw =  0.03
    elif dig == "DEBILITATED": raw = -0.04
    if raw == 0.0: return 0.0
    # D1 vitality gate: a combust/war-loser/Mrita AK cannot fully deliver D9 results
    vit = _d1_vitality_coefficient(ak, payload)
    return raw * vit

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

def _yoga_bonus(label, detected_yogas, house_lords=None, planet_dignities=None):
    """Domain-matched yoga bonus with quality grading (Gap-5 fix).

    For known yogas the base bonus is multiplied by _yoga_quality_factor(), which
    scales from 0.30 (all forming planets debilitated) to 1.0 (all exalted/own).
    This prevents a severely weakened GajaKesari from scoring the same as a
    pristine one.  Parivartana yogas retain their existing Mahayoga/Dainya logic.
    """
    if not detected_yogas: return 0.0
    if house_lords is None: house_lords = {}
    if planet_dignities is None: planet_dignities = {}
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
        elif any(_wm(kw, label_lower) for kw in _YOGA_DOMAIN_KW.get(yoga,[])):
            base  = _YOGA_BONUS_AMT.get(yoga, 0.07)
            qual  = _yoga_quality_factor(yoga, planet_dignities)
            bonus += base * qual
    return max(-0.10, min(bonus, 0.21))
def _h5_lord_bonus(affinity, h5_lord):
    if not h5_lord: return 0.0
    w = affinity.get(h5_lord, 0.0)
    if w >= 0.25: return 0.06
    if w >= 0.15: return 0.03
    return 0.0

def _amk_house_bonus(label, amk_house):
    kws = _AMK_HOUSE_KW.get(amk_house,[])
    if kws and any(_wm(kw, label.lower()) for kw in kws):
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

def _planet_combustion_penalty(affinity, combust_planets, planet_dignities=None, planets_d1=None):
    """M3: Sliding combustion penalty — uses degree proximity from Sun instead of binary flag."""
    if planet_dignities is None: planet_dignities = {}
    penalty = 0.0
    for p in combust_planets:
        if p not in affinity: continue
        base = affinity[p] * 0.15
        dig  = planet_dignities.get(p,"")
        if dig == "EXALTED": base *= 0.30
        elif dig == "OWN":   base *= 0.50
        base *= _combustion_degree_factor(p, planets_d1 or {})
        penalty += base
    return min(penalty, 0.20)

# Fields where 8th-house energy (hidden, crisis, deep investigation) is required
# Unified exemption keywords — fields that positively require dusthana energy
def _dusthana_lord_penalty(affinity, lagna_sign, house_lords, lagna_lord: str = "",
                            label: str = "", eff_strengths=None):
    """Dusthana lord penalty — with capacity-conditioned exemption (Gap-3 fix).

    H6 (disease/service/law), H8 (surgery/research/hidden), H12 (renunciation/hospital).
    Fields that require dusthana energy (medicine, research, etc.) receive a reduced
    penalty — but NOT a blanket zero.  The exemption is now conditioned on the native's
    actual capacity: if the relevant dusthana lord is strong (eff_strength ≥ 0.60),
    the penalty is fully waived.  A weak lord (< 0.40) still draws a partial penalty
    even for exempt fields, because the native lacks the capacity to channel that energy.
    """
    if eff_strengths is None:
        eff_strengths = {}
    lb = label.lower()
    is_exempt_domain = any(kw in lb for kw in _DUSTHANA_EXEMPT_KW)

    dusthana_lords = {
        "6":  house_lords.get("6", ""),
        "8":  house_lords.get("8", ""),
        "12": house_lords.get("12", ""),
    }
    dusthanas = {v for v in dusthana_lords.values() if v}

    # AC9 fix: Upachaya exemption — malefics (Saturn/Mars) placed in Upachaya houses
    # (H3/H6/H10/H11) grow stronger over time; classical rule says they give good
    # career results despite dusthana lordship. Exempt them from career penalty.
    _UPACHAYA = {3, 6, 10, 11}
    _NATURAL_MALEFICS = {"Saturn", "Mars", "Sun", "Rahu"}

    penalty = 0.0
    for p, w in affinity.items():
        if p == lagna_lord:
            continue   # lagna lord always immune
        if p not in dusthanas or w <= 0.15:
            continue

        # AC9: H6 lord that is a natural malefic placed in an Upachaya house → exempt
        # (only applies to H6 lords — H8/H12 lords still carry penalty regardless)
        _p_house = affinity.get("__planet_house__", {}).get(p, 0)  # injected by caller if avail
        if (house_lords.get("6") == p and p in _NATURAL_MALEFICS and _p_house in _UPACHAYA):
            penalty += w * 0.02  # token penalty (not zero — field-specificity still matters)
            continue

        if is_exempt_domain:
            # Capacity check: how strong is this dusthana lord?
            lord_strength = eff_strengths.get(p, 0.5)   # default 0.5 = unknown
            if lord_strength >= 0.60:
                continue   # strong lord → domain exemption holds, no penalty
            elif lord_strength >= 0.40:
                # Moderate lord → half penalty (native has partial capacity)
                penalty += w * 0.05
            else:
                # Weak lord → 70% of normal penalty even for exempt fields
                penalty += w * 0.07
        else:
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
    kw_match = any(_wm(kw, label.lower()) for kw in DASHA_KEYWORDS.get(prd_lord,[]))
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
        if any(_wm(kw, label.lower()) for kw in kws):
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
        if any(_wm(kw, label_lower) for kw in placement_kws):
            w = affinity.get(lord, 0.0)
            if   w >= 0.25: bonus += 0.05
            elif w >= 0.15: bonus += 0.03
            elif w >= 0.08: bonus += 0.01

    return min(bonus, 0.12)

def _d9_h10_bonus(affinity, d9_chart, d9_lagna_sign, payload=None):
    """Bonus for planets in D9 H10 — gated by D1 vitality coefficient."""
    if not d9_lagna_sign or not d9_chart: return 0.0
    bonus = 0.0
    for planet, sign in d9_chart.items():
        if planet == "Lagna": continue
        if (((_SIGN_NUM.get(sign, 1) - _SIGN_NUM.get(d9_lagna_sign, 1)) % 12) + 1) == 10:
            w = affinity.get(planet, 0.0)
            raw = 0.05 if w >= 0.20 else (0.02 if w >= 0.10 else 0.0)
            if raw > 0:
                vit = _d1_vitality_coefficient(planet, payload) if payload else 1.0
                bonus += raw * vit
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
        if   w >= 0.20 and dig == "EXALTED": raw = 0.10
        elif w >= 0.20:                       raw = 0.06
        elif w >= 0.10 and dig == "EXALTED": raw = 0.06
        elif w >= 0.10:                       raw = 0.03
        else:                                 raw = 0.0
        bonus += raw  # vitality not applied here (no payload reference; caller can gate)
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
# A9 fix: duplicate _maheshwara_lord_bonus removed (canonical at line 204)


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

# ── Brahma Lord Domain Keywords ────────────────────────────────────────────────
# Brahma (Jaimini) governs the timing of peak creative/dharmic expression.
# Maps brahma lord to domains it amplifies — similar to Maheshwara but emphasis on
# creative intelligence and dharmic purpose rather than institutional peaks.
_BRAHMA_DOMAIN_KW: Dict[str, List[str]] = {
    "Jupiter": ["law","education","philosophy","research","international","theology","economics"],
    "Mercury": ["data science","computer","mathematics","communication","statistics","analytics","artificial intelligence"],
    "Venus":   ["arts","design","fashion","music","performing arts","fine arts","architecture","media","mass communication"],
    "Saturn":  ["engineering","mining","civil","metallurgy","agriculture","industrial","construction","environment"],
    "Mars":    ["defence","surgery","military","police","sports","mechanical","fire service"],
    "Sun":     ["civil services","administration","government","leadership","energy","physics"],
    "Moon":    ["nursing","psychology","social work","public health","ecology","hospitality","counseling"],
    "Rahu":    ["artificial intelligence","cybersecurity","biotechnology","space","robotics","forensic","data science"],
    "Ketu":    ["research","ayurveda","spiritual","philosophy","archaeology","investigation","occult"],
}


def _brahma_lord_bonus(label: str, brahma_lord: str, affinity: Dict[str, float]) -> float:
    """Brahma lord (Jaimini) domain alignment bonus.
    Fires when the brahma lord's creative domain matches the field AND
    it has meaningful affinity weight in the branch's planet vector."""
    if not brahma_lord:
        return 0.0
    kws = _BRAHMA_DOMAIN_KW.get(brahma_lord, [])
    label_lower = label.lower()
    if not any(_wm(kw, label_lower) for kw in kws):
        return 0.0
    w = affinity.get(brahma_lord, 0.0)
    if   w >= 0.25: return 0.07
    if   w >= 0.15: return 0.04
    if   w >= 0.08: return 0.02
    return 0.0


def _chart_specific_aptitude_supplement(
    domain: str,
    h5_lord: str,
    lagna_lord: str,
    h10_lord: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Add a small flat bonus to composite_score when key lords strongly support the domain.

    H5 lord supports learning/intelligence domains. H10 and lagna lords support
    career domains they rule. Capped at +10 to avoid overwhelming the base score.
    Classical principle: H5/H10/lagna lords in good dignity acting through their
    natural domains raise the competence ceiling for that field.
    """
    _DOMAIN_LORDS: Dict[str, List[str]] = {
        "medicine":       ["Moon", "Jupiter", "Mars"],
        "engineering":    ["Mars", "Saturn"],
        "technology":     ["Mercury", "Rahu"],
        "science":        ["Mercury", "Jupiter", "Saturn"],
        "law":            ["Jupiter", "Mercury", "Sun"],
        "arts":           ["Venus", "Moon"],
        "design":         ["Venus", "Mercury"],
        "humanities":     ["Moon", "Jupiter", "Venus"],
        "commerce":       ["Mercury", "Jupiter", "Saturn"],
        "education":      ["Jupiter", "Mercury"],
        "research":       ["Ketu", "Jupiter", "Saturn"],
        "media":          ["Mercury", "Venus", "Rahu"],
        "public":         ["Sun", "Jupiter", "Saturn"],
        "agriculture":    ["Moon", "Saturn", "Mars"],
        "interdisciplinary": ["Mercury", "Jupiter"],
    }
    relevant = _DOMAIN_LORDS.get(domain, [])
    supplement = 0.0
    for lord in [h5_lord, h10_lord, lagna_lord]:
        if lord and lord in relevant:
            s = eff_strengths.get(lord, 0.0)
            if s >= 1.40:
                supplement += 3.5
            elif s >= 1.15:
                supplement += 2.0
            elif s >= 0.90:
                supplement += 0.8
    return min(supplement, 10.0)


def _ak_planet_domain_boost(
    label: str,
    ak: str,
    ak_dig: str,
    planet_house: Dict[str, int],
    amk: str = "",
    amk_dig: str = "",
) -> float:
    """AK (and optionally AmK) planet natural-domain keyword boost.

    Maps the Atmakaraka planet to its natural career domains and boosts
    fields whose label matches those domain keywords.  This encodes the
    Jaimini principle that AK = soul purpose and MUST shape field ranking
    regardless of the planet's temporal strength (Mrita etc.).

    Planet → domain mapping:
      Mercury  → technology, data science, computing, analytics, mathematics
      Jupiter  → law, economics, education, philosophy, management, finance
      Venus    → arts, design, music, fashion, hospitality, film
      Mars     → engineering, defence, surgery, sports, mechanical, electrical
      Saturn   → engineering, government, agriculture, mining, construction
      Sun      → civil services, administration, medicine, nuclear, leadership
      Moon     → psychology, nursing, medicine, social work, hospitality
      Rahu     → technology, AI, data science, foreign, media, space
      Ketu     → research, philosophy, medicine, forensic, ayurveda

    Base boosts: primary match = +0.13, secondary match = +0.07.
    Multiplied by dignity (EXALTED 1.4×, OWN 1.2×, DEBILITATED 0.6×)
    and house position (trikona 1.2×, karma 1.1×, dusthana 0.8×).
    AmK applies the same mapping at 60 % base weight.
    """
    # ── keyword table ─────────────────────────────────────────────────────────
    _KW: Dict[str, Tuple[List[str], List[str]]] = {
        "Mercury": (
            ["technology", "computer", "software", "data science", "machine learning",
             "artificial intelligence", "analytics", "mathematics", "programming",
             "information technology", "statistics", "computational"],
            ["communication", "media", "writing", "journalism", "research",
             "commerce", "accounting", "economics", "finance", "digital"],
        ),
        "Jupiter": (
            ["law", "economics", "education", "philosophy", "management",
             "finance", "banking", "consulting", "teaching", "governance",
             "political science", "public policy"],
            ["theology", "international", "administration", "research",
             "humanities", "social science", "commerce", "medicine",
             "business", "policy"],
        ),
        "Venus": (
            ["arts", "design", "music", "fashion", "beauty", "hospitality",
             "film", "performing", "visual", "creative", "architecture",
             "animation", "dance"],
            ["luxury", "tourism", "entertainment", "interior", "textile",
             "jewellery", "culinary", "drama", "photography", "media"],
        ),
        "Mars": (
            ["engineering", "defence", "military", "surgery", "sports",
             "mechanical", "electrical", "manufacturing", "aerospace",
             "civil engineering", "energy"],
            ["physical", "nuclear", "police", "security", "firefighting",
             "materials", "metallurgy", "construction", "mining", "petroleum"],
        ),
        "Saturn": (
            ["engineering", "government", "administration", "agriculture",
             "mining", "construction", "infrastructure", "materials",
             "civil engineering", "public works", "industrial"],
            ["law", "policy", "social work", "environmental", "geology",
             "architecture", "urban", "mechanical", "labour", "textile"],
        ),
        "Sun": (
            ["government", "civil services", "administration", "leadership",
             "nuclear", "medicine", "political", "public", "law", "energy"],
            ["management", "corporate", "executive", "defence", "history",
             "social", "pharmacy", "ophthalmology", "cardiology", "surgery"],
        ),
        "Moon": (
            ["psychology", "nursing", "medicine", "counseling", "social work",
             "public health", "hospitality", "food", "agriculture", "childcare",
             "mental health"],
            ["humanities", "education", "community", "welfare", "health",
             "pharmacy", "marine", "tourism", "literature", "naturopathy"],
        ),
        "Rahu": (
            ["technology", "artificial intelligence", "data science",
             "machine learning", "cybersecurity", "robotics", "space",
             "biotechnology", "foreign", "media", "digital"],
            ["film", "research", "analytics", "finance", "economics",
             "engineering", "computer", "international", "aviation"],
        ),
        "Ketu": (
            ["research", "philosophy", "spiritual", "medicine", "forensic",
             "ayurveda", "archaeology", "investigative", "alternative",
             "astrology", "mathematics"],
            ["psychology", "metaphysics", "science", "theology", "history",
             "ancient", "language", "occult", "analytics"],
        ),
    }

    def _planet_boost(planet: str, dig: str, base_scale: float) -> float:
        if not planet:
            return 0.0
        primary_kw, secondary_kw = _KW.get(planet, ([], []))
        lbl = label.lower()
        if any(kw in lbl for kw in primary_kw):
            base = 0.13 * base_scale
        elif any(kw in lbl for kw in secondary_kw):
            base = 0.07 * base_scale
        else:
            return 0.0
        dig_mod = {"EXALTED": 1.4, "OWN": 1.2,
                   "NEECHA_BHANGA": 1.0, "DEBILITATED": 0.6}.get(dig, 1.0)
        ak_house = planet_house.get(planet, 0)
        if ak_house in (1, 5, 9):
            house_mod = 1.2
        elif ak_house == 10:
            house_mod = 1.1
        elif ak_house in (4, 7):
            house_mod = 1.0
        elif ak_house in (2, 11):
            house_mod = 0.9
        else:
            house_mod = 0.8   # dusthana or unknown
        return min(base * dig_mod * house_mod, 0.20)

    boost = _planet_boost(ak, ak_dig, 1.0)
    if amk and amk != ak:
        boost = max(boost, _planet_boost(amk, amk_dig, 0.65))
    return round(boost, 4)


def _ak_domain_flat_supplement(
    label: str,
    ak: str,
    amk: str = "",
    digs: Optional[Dict[str, str]] = None,
) -> float:
    """Flat additive to final_score ensuring AK/AmK soul-domain fields reach top-35.

    gap_boost is a *multiplier* on blended_score.  When the AK planet is Mrita
    (weak eff_strength), technology/economics fields can have a blended_score of
    ~55–65 while strongly-placed planet domains score 90–110.  A 0.15 multiplier
    on 60 = only +9 extra, not enough to compete.

    This function adds a FLAT score supplement (independent of blended_score) so
    that soul-purpose fields stay structurally visible regardless of AK weakness.
    The flat values are tuned so they add ~28–30 for a primary keyword match —
    just enough to cross the top-35 threshold without inverting the entire chart.

    AK (soul purpose) uses full weight; AmK (career means) uses 65 % weight.
    Final supplement = max(ak_flat, amk_flat) — soul and career point from
    different angles so we take the stronger signal, not cumulative.
    """
    if digs is None:
        digs = {}

    _KW: Dict[str, Tuple[List[str], List[str]]] = {
        "Mercury": (
            ["technology", "computer", "software", "data science", "machine learning",
             "artificial intelligence", "analytics", "mathematics", "programming",
             "information technology", "statistics", "computational"],
            ["communication", "media", "writing", "journalism", "research",
             "commerce", "accounting", "economics", "finance", "digital"],
        ),
        "Jupiter": (
            ["law", "economics", "education", "philosophy", "management",
             "finance", "banking", "consulting", "teaching", "governance",
             "political science", "public policy"],
            ["theology", "international", "administration", "research",
             "humanities", "social science", "commerce", "medicine",
             "business", "policy"],
        ),
        "Venus": (
            ["arts", "design", "music", "fashion", "beauty", "hospitality",
             "film", "performing", "visual", "creative", "architecture",
             "animation", "dance"],
            ["luxury", "tourism", "entertainment", "interior", "textile",
             "jewellery", "culinary", "drama", "photography", "media"],
        ),
        "Mars": (
            ["engineering", "defence", "military", "surgery", "sports",
             "mechanical", "electrical", "manufacturing", "aerospace",
             "civil engineering", "energy"],
            ["physical", "nuclear", "police", "security", "firefighting",
             "materials", "metallurgy", "construction", "mining", "petroleum"],
        ),
        "Saturn": (
            ["engineering", "government", "administration", "agriculture",
             "mining", "construction", "infrastructure", "materials",
             "civil engineering", "public works", "industrial"],
            ["law", "policy", "social work", "environmental", "geology",
             "architecture", "urban", "mechanical", "labour", "textile"],
        ),
        "Sun": (
            ["government", "civil services", "administration", "leadership",
             "nuclear", "medicine", "political", "public", "law", "energy"],
            ["management", "corporate", "executive", "defence", "history",
             "social", "pharmacy", "ophthalmology", "cardiology", "surgery"],
        ),
        "Moon": (
            ["psychology", "nursing", "medicine", "counseling", "social work",
             "public health", "hospitality", "food", "agriculture", "childcare",
             "mental health"],
            ["humanities", "education", "community", "welfare", "health",
             "pharmacy", "marine", "tourism", "literature", "naturopathy"],
        ),
        "Rahu": (
            ["technology", "artificial intelligence", "data science",
             "machine learning", "cybersecurity", "robotics", "space",
             "biotechnology", "foreign", "media", "digital"],
            ["film", "research", "analytics", "finance", "economics",
             "engineering", "computer", "international", "aviation"],
        ),
        "Ketu": (
            ["research", "philosophy", "spiritual", "medicine", "forensic",
             "ayurveda", "archaeology", "investigative", "alternative",
             "astrology", "mathematics"],
            ["psychology", "metaphysics", "science", "theology", "history",
             "ancient", "language", "occult", "analytics"],
        ),
    }

    def _flat_for(planet: str, scale: float) -> float:
        if not planet:
            return 0.0
        primary_kw, secondary_kw = _KW.get(planet, ([], []))
        lbl = label.lower()
        if any(kw in lbl for kw in primary_kw):
            base = 55.0
        elif any(kw in lbl for kw in secondary_kw):
            base = 25.0
        else:
            return 0.0
        dig_mod = {"EXALTED": 1.4, "OWN": 1.2,
                   "NEECHA_BHANGA": 1.0, "DEBILITATED": 0.5}.get(digs.get(planet, ""), 1.0)
        return base * scale * dig_mod

    ak_flat  = _flat_for(ak,  1.00)
    amk_flat = _flat_for(amk, 0.65)
    raw      = max(ak_flat, amk_flat)
    # LS2 fix: cap at 20 pts; caller scales by (blended/100) to prevent weak-base fields
    # jumping top-5 purely on AK keyword matching (was up to 77 pts unbounded).
    return round(min(raw, 20.0), 2)


def _karakamsha_domain_boost(label: str, domain: str, karakamsha: str) -> float:
    """Karakamsha sign (navamsa sign of AK) domain affinity bonus.

    The karakamsha sign reveals the soul's deepest natural expression.
    Certain signs naturally amplify specific domains via their ruling planet.
    """
    if not karakamsha:
        return 0.0

    _KM_DOMAIN: Dict[str, List[str]] = {
        "Aries":       ["engineering","defence","surgery","sports"],
        "Taurus":      ["arts","design","finance","commerce","luxury","architecture"],
        "Gemini":      ["technology","media","communication","data science","mathematics"],
        "Cancer":      ["medicine","nursing","psychology","public health","hospitality"],
        "Leo":         ["civil services","administration","law","leadership","performing arts"],
        "Virgo":       ["medicine","pharmacy","analytics","data","accounting","biotechnology"],
        "Libra":       ["law","arts","design","economics","commerce","fashion"],
        "Scorpio":     ["research","psychology","forensic","investigation","surgery","cybersecurity"],
        "Sagittarius": ["law","philosophy","education","international","theology","sports","economics","commerce","finance","data science","political","policy"],
        "Capricorn":   ["engineering","civil","mining","construction","government","agriculture"],
        "Aquarius":    ["technology","artificial intelligence","space","robotics","science","data science"],
        "Pisces":      ["arts","spiritual","medicine","research","philosophy","psychology","charity"],
    }
    label_lower = label.lower()
    matched_domains = _KM_DOMAIN.get(karakamsha, [])
    if any(kw in label_lower for kw in matched_domains):
        return 0.05
    return 0.0


def _h3_lord_communication_boost(
    label: str,
    domain: str,
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    planet_house: Dict[str, int],
) -> float:
    """H3 lord (skills, communication, effort) boost for communication-heavy domains.

    When H3 lord is strong, it enhances fields requiring writing, speaking,
    media, communication, sales, or technical exposition. H3 strength also
    aids technical/hands-on engineering fields via skill amplification.
    """
    h3_lord = house_lords.get("3", "")
    if not h3_lord:
        return 0.0
    s = eff_strengths.get(h3_lord, 0.0)
    h3_house = planet_house.get(h3_lord, 0)
    _COMM_KW = [
        "communication", "media", "journalism", "writing", "marketing",
        "public relations", "advertising", "broadcasting", "content", "social media",
        "sales", "copywriting", "digital marketing", "mass communication",
    ]
    _TECH_KW = ["engineering", "technology", "computer", "science", "mathematics", "research"]
    label_lower = label.lower()

    if not any(kw in label_lower for kw in _COMM_KW + _TECH_KW):
        return 0.0

    if s < 0.30:
        return 0.0

    bonus = 0.0
    if any(kw in label_lower for kw in _COMM_KW):
        bonus += 0.04 + 0.04 * min(1.0, s)
        if h3_house in (1, 4, 5, 7, 9, 10):
            bonus += 0.02
    elif any(kw in label_lower for kw in _TECH_KW):
        bonus += 0.02 + 0.02 * min(1.0, s)

    return min(bonus, 0.10)


def _h10_lord_trikona_bonus(affinity, h10_lord, planet_house, planet_dignities=None):
    """Bonus when H10 lord occupies a trikona (H1/H5/H9) with good dignity."""
    if not h10_lord: return 0.0
    if planet_dignities is None: planet_dignities = {}
    house = planet_house.get(h10_lord, 0) if isinstance(planet_house, dict) else 0
    if house not in (1, 5, 9): return 0.0
    w = affinity.get(h10_lord, 0.0)
    if w < 0.10: return 0.0
    dig = planet_dignities.get(h10_lord, "")
    base = 0.06 if w >= 0.20 else 0.03
    if dig == "EXALTED": base += 0.04
    elif dig == "OWN":   base += 0.02
    return min(base, 0.12)


def _h12_stellium_penalty(label, domain, planet_house):
    """Penalty when 3+ planets occupy H12 — research/medicine/spiritual fields exempt."""
    _EXEMPT = {"research", "medicine", "spiritual", "psychology", "philosophy",
               "theology", "foreign", "international", "ayurveda"}
    label_lower = label.lower()
    if any(k in label_lower or k in domain for k in _EXEMPT):
        return 0.0
    h12_count = sum(1 for h in planet_house.values() if h == 12)
    if h12_count >= 4: return -0.07
    if h12_count >= 3: return -0.04
    return 0.0


def _d10_lagna_lord_bonus(affinity, d10_chart, d10_lagna_sign, d10_digs=None):
    """Bonus when D10 lagna lord is dignified in D10."""
    if not d10_lagna_sign or not d10_chart: return 0.0
    if d10_digs is None: d10_digs = {}
    from .constants import _SIGN_LORD
    d10_ll = _SIGN_LORD.get(d10_lagna_sign, "")
    if not d10_ll: return 0.0
    dig = d10_digs.get(d10_ll, "")
    w = affinity.get(d10_ll, 0.0)
    if w < 0.10: return 0.0
    if dig == "EXALTED": return min(0.08 * w, 0.10)
    if dig == "OWN":     return min(0.05 * w, 0.07)
    return 0.0


def _modernize_karakas_modifier(field_id, risk, amk, kp_h10_star_lord, planets_d1):
    """Small nudge for Rahu/Mercury AmK in modern/tech fields."""
    if amk not in ("Rahu", "Mercury"): return 0.0
    _TECH_IDS = {"artificial_intelligence_ml", "data_science_analytics", "cybersecurity",
                             "machine_learning_ai", "robotics_automation", "space_technology",
               "biotechnology_research", "nuclear_engineering", "forensic_science",
               "information_technology", "computer_science_engineering",
               "electronics_communication", "nanotechnology", "bioinformatics",
               "aerospace_engineering", "space_systems_engineering",
               "blockchain_web3", "quantum_computing", "environmental_engineering"}
    if field_id not in _TECH_IDS:
        return 0.0
    # Rahu AMK in modern tech: unconventional disruptor energy — stronger nudge
    if amk == "Rahu":
        base = 0.06
    else:  # Mercury AMK
        base = 0.04
    # KP H10 star lord aligned to Rahu/Mercury in tech: extra confirmation
    if kp_h10_star_lord in ("Rahu", "Mercury"):
        base += 0.02
    # Rahu in planets_d1 strong (kendra or trikona house) amplifies the effect
    if planets_d1:
        rahu_house = None
        lagna_sign = ""
        # detect Rahu's approximate house from sign offset not available here;
        # use presence of Rahu in a known strong sign as a proxy
        rahu_sign = planets_d1.get("Rahu", {}).get("sign", "")
        if rahu_sign in ("Gemini", "Virgo", "Taurus", "Aquarius", "Aries"):
            base += 0.01
    return round(min(base, 0.10), 3)


def _build_critical_warnings(payload, war_result=None) -> list:
    """Build a list of critical astrological warning strings for reporting.

    Checks combustion, Graha Yuddha losers, and Mrita Avastha states for the
    chart's key planets (AK, AMK, lagna lord, H10 lord) and returns human-readable
    warning strings for display in the web report or advisory layer.
    """
    war_result   = war_result or {}
    warnings     = []
    combust      = set(getattr(payload, "combust_planets", []) or [])
    cazimi       = set(getattr(payload, "cazimi_planets",  []) or [])
    planets_d1   = getattr(payload, "planets_d1",  {}) or {}
    digs         = getattr(payload, "planet_dignities", {}) or {}
    ak           = getattr(payload, "atmakaraka",  "") or ""
    amk          = getattr(payload, "amatyakaraka", "") or ""
    lagna_lord   = getattr(payload, "lagna_lord",  "") or ""
    h10_lord     = (getattr(payload, "house_lords", {}) or {}).get("10", "")

    key_planets  = {p for p in (ak, amk, lagna_lord, h10_lord) if p}

    for planet in key_planets:
        role = []
        if planet == ak:        role.append("AK")
        if planet == amk:       role.append("AMK")
        if planet == lagna_lord: role.append("Lagna lord")
        if planet == h10_lord:  role.append("H10 lord")
        role_str = "/".join(role)
        if planet in combust and planet not in cazimi:
            warnings.append(f"COMBUST: {planet} ({role_str}) is combust — D1 vitality significantly reduced.")
        if planet in cazimi:
            warnings.append(f"CAZIMI: {planet} ({role_str}) is in the heart of the Sun — amplified but volatile.")
        war_status = war_result.get(planet, "")
        if war_status == "loser_bitter":
            warnings.append(f"GRAHA YUDDHA (bitter loss): {planet} ({role_str}) lost planetary war — severely weakened.")
        elif war_status == "loser_friendly":
            warnings.append(f"GRAHA YUDDHA (friendly loss): {planet} ({role_str}) lost planetary war — moderately weakened.")
        pdata = planets_d1.get(planet, {})
        if pdata:
            sign   = pdata.get("sign", "")
            degree = float(pdata.get("degree", 0))
            is_odd  = sign in _ODD_SIGNS
            is_mrita = (is_odd and degree >= 24.0) or (not is_odd and sign and degree < 6.0)
            if is_mrita:
                warnings.append(f"MRITA AVASTHA: {planet} ({role_str}) is in dead degrees ({sign} {degree:.1f}°) — severely weakened.")
        if digs.get(planet, "") == "DEBILITATED" and planet not in combust:
            warnings.append(f"DEBILITATED: {planet} ({role_str}) is in debilitation — check for Neecha Bhanga.")

    return warnings


def apply_domain_deduplication(
    results: List[Dict],
    per_domain_cap: int = 4,
    exempt_window: int = 5,
) -> List[Dict]:
    """Post-LLM domain deduplication — caps results per domain.

    The first ``exempt_window`` results are always kept regardless of domain
    so the absolute top fields are never filtered out.  After that, each
    additional domain entry beyond ``per_domain_cap`` is moved to the bottom
    of the list (not discarded) to preserve full coverage.
    """
    if not results:
        return results
    domain_counts: Dict[str, int] = {}
    kept: List[Dict] = []
    deferred: List[Dict] = []
    for idx, item in enumerate(results):
        domain = item.get("domain", "")
        if idx < exempt_window:
            kept.append(item)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        else:
            count = domain_counts.get(domain, 0)
            if count < per_domain_cap:
                kept.append(item)
                domain_counts[domain] = count + 1
            else:
                deferred.append(item)
    return kept + deferred


# =============================================================================
# MODULE 1 EXPANSION — 360° COMPETENCY & ENVIRONMENT PROFILING
# =============================================================================

# ── Feature 1: Corporate vs Entrepreneurial Balance ──────────────────────────
# House weights reflecting employment vs self-driven energy.
# Corporate: H6 (service), H10 (hierarchy/bosses), H2 (steady income)
# Entrepreneurial: H3 (courage/self-effort), H7 (partnerships/business), H11 (independent gains)

# Corporate:      H6 (service/employment), H10 (career hierarchy), H2 (steady salary)
# Entrepreneurial: H1 (self-initiative), H3 (courage/self-effort), H5 (creativity/risk),
#                  H7 (partnerships/business), H9 (fortune/venture), H11 (independent gains)
# H4 removed from corporate — home/comfort has no employment signal
# H2 kept in corporate only (steady income from employer); H5 added to entrepreneurial
_CORP_HOUSE_WEIGHTS   = {6: 1.0, 10: 1.0, 2: 0.6}
_ENTREP_HOUSE_WEIGHTS = {1: 0.4, 3: 0.9, 5: 0.6, 7: 1.0, 9: 0.5, 11: 0.7}

def compute_corporate_entrepreneurial_score(
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    atmakaraka: str = "",
) -> Dict:
    """Return a 0–1 float (1=fully corporate, 0=fully entrepreneurial) and a label.

    Strategy:
    - Sum effective strength of planets placed in corporate houses.
    - Sum effective strength of planets placed in entrepreneurial houses.
    - Normalize to a ratio.

    Also checks if the Atmakaraka is in an entrepreneurial house (strong signal).
    """
    corp_score   = 0.0
    entrep_score = 0.0

    for planet, house in planet_house.items():
        strength = eff_strengths.get(planet, 1.0)
        corp_score   += _CORP_HOUSE_WEIGHTS.get(house, 0.0)   * strength
        entrep_score += _ENTREP_HOUSE_WEIGHTS.get(house, 0.0) * strength

    # Atmakaraka in H1/H7/H9/H11 → strong entrepreneurial pull
    ak_house = planet_house.get(atmakaraka, 0)
    if ak_house in _ENTREP_HOUSE_WEIGHTS:
        entrep_score += _ENTREP_HOUSE_WEIGHTS[ak_house] * 1.5   # AK weight boost

    total = corp_score + entrep_score
    if total == 0:
        corporate_pct = 50
    else:
        corporate_pct = int(round(corp_score / total * 100))

    entrep_pct = 100 - corporate_pct

    if corporate_pct >= 75:
        style_label = "Strong Corporate"
        style_note  = "Built for MNCs, established organisations, and structured hierarchies."
    elif corporate_pct >= 60:
        style_label = "Corporate-Leaning"
        style_note  = "Thrives within organisations but benefits from intrapreneurial roles with autonomy."
    elif corporate_pct >= 45:
        style_label = "Balanced / Hybrid"
        style_note  = "Equally suited to corporate roles with independent scope or consulting tracks."
    elif corporate_pct >= 30:
        style_label = "Entrepreneurial-Leaning"
        style_note  = "Consulting, freelance, or founding roles within larger ecosystems will outperform pure employment."
    else:
        style_label = "Strong Entrepreneurial"
        style_note  = "Independent practice, business ownership, or venture-backed founding are natural paths."

    return {
        "corporate_pct":   corporate_pct,
        "entrep_pct":      entrep_pct,
        "style_label":     style_label,
        "style_note":      style_note,
    }


# ── Feature 2: Dhana Yoga / Wealth Potential per Field ───────────────────────
# A field can generate career success but low financial return if the
# 2nd/11th lords (wealth planets) are disconnected from that field's planets.

_FIELD_PRIMARY_PLANETS: Dict[str, List[str]] = {
    # Maps domain → typical primary planets (add more as needed)
    "law":         ["Jupiter", "Mercury", "Saturn"],
    "technology":  ["Mercury", "Rahu", "Mars"],
    "medicine":    ["Mars", "Sun", "Moon", "Ketu"],
    "finance":     ["Venus", "Mercury", "Jupiter"],
    "arts":        ["Venus", "Moon", "Mercury"],
    "teaching":    ["Jupiter", "Mercury", "Moon"],
    "engineering": ["Mars", "Saturn", "Mercury"],
    "research":    ["Ketu", "Saturn", "Mercury"],
    "management":  ["Sun", "Jupiter", "Saturn"],
    "consulting":  ["Mercury", "Jupiter", "Venus"],
    "military":    ["Mars", "Sun", "Saturn"],
    "_default":    ["Mercury", "Jupiter"],
}

def compute_wealth_potential(
    field_result: Dict,
    house_lords: Dict[str, str],
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
) -> Dict:
    """Return a wealth potential score and label for a specific field.

    Logic:
    - Identify field primary planets from domain.
    - Check if any primary planet is also the lord of H2 or H11 (wealth houses),
      or is placed in H2/H11, or aspects H2/H11.
    - Score the connection strength.
    """
    domain = field_result.get("domain", "_default")
    primaries = _FIELD_PRIMARY_PLANETS.get(domain, _FIELD_PRIMARY_PLANETS["_default"])

    h2_lord  = house_lords.get("2",  "")
    h11_lord = house_lords.get("11", "")
    wealth_planets = {p for p in [h2_lord, h11_lord] if p}

    wealth_score = 0.0
    connections  = []

    for planet in primaries:
        strength = eff_strengths.get(planet, 1.0)
        ph = planet_house.get(planet, 0)

        # Direct: planet IS a wealth lord
        if planet in wealth_planets:
            wealth_score += 1.5 * strength
            connections.append(f"{planet} is lord of H2/H11")

        # Planet placed in H2 or H11
        elif ph in (2, 11):
            wealth_score += 1.0 * strength
            connections.append(f"{planet} placed in H{ph}")

        # Wealth lords placed in field-primary planet's house
        for wl in wealth_planets:
            wl_house = planet_house.get(wl, 0)
            if wl_house == ph and ph != 0:
                wealth_score += 0.5 * strength
                connections.append(f"Wealth lord {wl} co-placed with {planet}")

    # Normalise: max possible ≈ 3 planets × 1.5 × avg strength 2.0 = 9
    normalised = min(wealth_score / 9.0, 1.0)

    if normalised >= 0.65:
        label = "High"
        note  = "Strongest financial alignment — this field connects to your wealth-generating planets."
    elif normalised >= 0.35:
        label = "Medium"
        note  = "Solid earning potential with focused monetisation strategy."
    else:
        label = "Low"
        note  = "Technical aptitude is high but financial returns may require supplementary income streams."

    return {
        "wealth_potential":     label,
        "wealth_score":         round(normalised, 3),
        "wealth_connections":   connections[:3],
        "wealth_note":          note,
    }


# ── Feature 3: Geographic Suitability ────────────────────────────────────────

def compute_geo_suitability(
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    lagna_sign: str = "",
) -> Dict:
    """Return geographic direction: Domestic | Hybrid | International/Relocation.

    Astrological basis:
    - H9 (long journeys, higher wisdom, foreign connections)
    - H12 (foreign lands, isolation, expatriate life)
    - H3 (short travel, courage, neighbouring regions)
    - Rahu (foreign, unconventional, cross-cultural ambition)
    - Moon (home, comfort, native land)

    Strong H9/H12 + Rahu in mobile signs → International/Relocation
    Strong Moon + H4 + fixed-sign dominance → Domestic
    Mixed → Hybrid (remote roles for multinationals)
    """
    rahu_house = planet_house.get("Rahu", 0)
    moon_house = planet_house.get("Moon", 0)
    h9_lord    = house_lords.get("9",  "")
    h12_lord   = house_lords.get("12", "")
    h4_lord    = house_lords.get("4",  "")

    foreign_score  = 0.0
    domestic_score = 0.0

    # H9 lord strength
    h9_strength = eff_strengths.get(h9_lord, 1.0) if h9_lord else 1.0
    if planet_house.get(h9_lord, 0) in (9, 12, 3, 11):
        foreign_score += h9_strength * 1.2

    # H12 lord strength
    h12_strength = eff_strengths.get(h12_lord, 1.0) if h12_lord else 1.0
    if planet_house.get(h12_lord, 0) in (9, 12, 1):
        foreign_score += h12_strength * 1.0

    # Rahu in angular/upachaya houses → foreign movement
    if rahu_house in (1, 4, 7, 10):
        foreign_score += 1.5
    elif rahu_house in (3, 9, 11):
        foreign_score += 1.0

    # Moon in H4 or H1 → domestic comfort
    if moon_house in (4, 1, 2):
        domestic_score += eff_strengths.get("Moon", 1.0) * 1.2

    # H4 lord in own house or exalted → strong domestic roots
    h4_strength = eff_strengths.get(h4_lord, 1.0) if h4_lord else 1.0
    h4_lord_house = planet_house.get(h4_lord, 0) if h4_lord else 0
    if h4_lord_house == 4:
        domestic_score += h4_strength * 1.2

    total = foreign_score + domestic_score
    if total == 0:
        foreign_pct = 50
    else:
        foreign_pct = int(round(foreign_score / total * 100))

    if foreign_pct >= 65:
        geo_label = "International / Relocation"
        geo_note  = ("Planetary configuration strongly favours foreign employment, "
                     "overseas postings, or remote roles with multinational scope. "
                     "Consider roles in global companies or cross-border practices.")
    elif foreign_pct >= 45:
        geo_label = "Hybrid"
        geo_note  = ("Both domestic and international paths are viable. "
                     "Remote work for global organisations, or domestic roles "
                     "with significant travel, optimise this configuration.")
    else:
        geo_label = "Domestic"
        geo_note  = ("Strongest career growth likely within the home country or region. "
                     "Roles in domestic-focused organisations, government, or local enterprise "
                     "will align best with your chart.")

    return {
        "geo_suitability":   geo_label,
        "geo_foreign_pct":   foreign_pct,
        "geo_domestic_pct":  100 - foreign_pct,
        "geo_note":          geo_note,
    }


# ── Feature 4: Burnout & Stress Vector ───────────────────────────────────────

_HIGH_STRESS_DOMAINS = {
    "medicine", "military", "law enforcement", "finance",
    "law", "consulting", "technology", "engineering",
}

def compute_burnout_risk(
    field_result: Dict,
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    combust_planets: List[str] = None,
) -> Dict:
    """Return a burnout risk level and role recommendation for a specific field.

    Logic:
    - Identify primary planets for the field's domain.
    - Check if any primary planet is placed in H6 (chronic stress), H8 (crisis/sudden events),
      or is combust (Sun's proximity → burnout of planetary energy).
    - Combine with domain inherent stress level.
    - Return Low / Medium / High + specific sub-role recommendation.
    """
    combust_planets = set(combust_planets or [])
    domain  = field_result.get("domain", "_default")
    primaries = _FIELD_PRIMARY_PLANETS.get(domain, _FIELD_PRIMARY_PLANETS["_default"])

    h6_lord  = house_lords.get("6",  "")
    h8_lord  = house_lords.get("8",  "")
    h6_occupants = [p for p, h in planet_house.items() if h == 6]
    h8_occupants = [p for p, h in planet_house.items() if h == 8]

    stress_score = 0.0
    stress_flags = []

    for planet in primaries:
        ph = planet_house.get(planet, 0)

        if ph == 6:
            stress_score += 1.5
            stress_flags.append(f"{planet} (primary planet) placed in H6 — chronic daily friction")

        if ph == 8:
            stress_score += 1.8
            stress_flags.append(f"{planet} (primary planet) placed in H8 — crisis/sudden disruption risk")

        if planet == h6_lord:
            stress_score += 1.0
            stress_flags.append(f"{planet} is H6 lord — field activates the stress house")

        if planet == h8_lord:
            stress_score += 1.2
            stress_flags.append(f"{planet} is H8 lord — transformation/crisis energy in this field")

        if planet in combust_planets:
            stress_score += 0.8
            stress_flags.append(f"{planet} is combust — energy burns bright but depletes faster")

    # Domain inherent stress baseline
    if domain in _HIGH_STRESS_DOMAINS:
        stress_score += 0.5

    # Normalise: max realistic ≈ 6.0
    normalised = min(stress_score / 6.0, 1.0)

    if normalised >= 0.60:
        risk_label = "High"
        risk_note = (
            "Significant burnout risk in frontline roles. "
            "Strongly recommend targeting research, advisory, policy, or academic sub-roles "
            "within this field rather than high-pressure delivery or clinical environments."
        )
    elif normalised >= 0.30:
        risk_label = "Medium"
        risk_note = (
            "Manageable stress with deliberate boundary-setting. "
            "Avoid roles with 24/7 on-call requirements. "
            "Regular recovery rituals (structured breaks, delegation culture) are essential."
        )
    else:
        risk_label = "Low"
        risk_note = (
            "Your chart is well-suited to absorb the demands of this field. "
            "The primary planets carry the necessary resilience for sustained performance."
        )

    return {
        "burnout_risk":   risk_label,
        "burnout_score":  round(normalised, 3),
        "stress_flags":   stress_flags[:3],
        "burnout_note":   risk_note,
    }


# =============================================================================
# MODULE 1 GAPS: Academic Path, Institutional Tier, Micro-Niches, Confidence
# =============================================================================

# A9 fix: _NAKSHATRA_LORD imported from constants.py (canonical, no spelling drift)
from .constants import _NAKSHATRA_LORD  # noqa: F811

# ── Domain × Secondary Planet → Micro-Niches ─────────────────────────────────
_DOMAIN_MICRO_NICHES: Dict[str, Dict[str, List[str]]] = {
    "technology": {
        "Sun":     ["Enterprise Architecture", "Tech Leadership", "CTO/CIO Track"],
        "Moon":    ["UX Research", "Human-Computer Interaction", "Conversational AI"],
        "Mars":    ["Cybersecurity", "Robotics & Edge Computing", "Systems Engineering"],
        "Mercury": ["Algorithms & Compilers", "Distributed Systems", "Developer Tools"],
        "Jupiter": ["AI Governance", "Tech Ethics & Policy", "EdTech Platforms"],
        "Venus":   ["Creative Technology", "UI/UX Design Systems", "Digital Product"],
        "Saturn":  ["Infrastructure & DevOps", "Legacy Modernisation", "SRE"],
        "Rahu":    ["Blockchain & Web3", "Quantum Computing", "Emerging Platforms"],
        "Ketu":    ["Deep Learning Research", "Theoretical CS", "Open-Source AI"],
        "_default": ["Software Engineering", "Machine Learning", "Cloud Architecture"],
    },
    "law": {
        "Sun":     ["Constitutional Law", "Government Affairs", "Public Policy"],
        "Moon":    ["Family & Child Law", "Victim Advocacy", "Mental Health Law"],
        "Mars":    ["Criminal Litigation", "Military/Defence Law", "Sports Law"],
        "Mercury": ["Intellectual Property", "Tech & Cyber Law", "Contract Drafting"],
        "Jupiter": ["International Law", "Human Rights", "Arbitration & ADR"],
        "Venus":   ["Entertainment Law", "Fashion & Brand IP", "Creative Industries"],
        "Saturn":  ["Corporate Compliance", "Insolvency Law", "Labour & Employment"],
        "Rahu":    ["Cross-Border Transactions", "Crypto Regulation", "Immigration"],
        "Ketu":    ["Legal Research & Academia", "Ancient/Comparative Law", "Legal Tech"],
        "_default": ["Corporate Law", "Litigation", "Regulatory Compliance"],
    },
    "finance": {
        "Sun":     ["Investment Banking", "Private Equity", "Capital Markets"],
        "Moon":    ["Retail Banking", "Wealth Management", "Behavioural Finance"],
        "Mars":    ["Hedge Funds", "Derivatives Trading", "Distressed Assets"],
        "Mercury": ["Quantitative Finance", "Algo Trading", "FinTech Analytics"],
        "Jupiter": ["ESG Investing", "Development Finance", "Microfinance"],
        "Venus":   ["Art & Alternative Assets", "Luxury Brand Finance", "Impact Investing"],
        "Saturn":  ["Risk Management", "Actuarial Science", "Audit & Compliance"],
        "Rahu":    ["Crypto & DeFi", "Cross-Border M&A", "Disruptive Fintech"],
        "Ketu":    ["Commodity Research", "Niche Fund Management", "Forensic Accounting"],
        "_default": ["Corporate Finance", "Financial Analysis", "Portfolio Management"],
    },
    "medicine": {
        "Sun":     ["Cardiology", "Oncology", "Hospital Administration"],
        "Moon":    ["Psychiatry", "Paediatrics", "Palliative Care"],
        "Mars":    ["Surgery", "Emergency Medicine", "Orthopaedics"],
        "Mercury": ["Neurology", "Clinical Genetics", "Medical Informatics"],
        "Jupiter": ["Public Health", "Global Health Policy", "Medical Ethics"],
        "Venus":   ["Dermatology", "Aesthetic Medicine", "Reproductive Health"],
        "Saturn":  ["Epidemiology", "Geriatrics", "Preventive Medicine"],
        "Rahu":    ["Rare Disease Research", "Gene Therapy", "Experimental Medicine"],
        "Ketu":    ["Pathology", "Integrative Medicine", "Medical Research"],
        "_default": ["General Medicine", "Clinical Research", "Healthcare Management"],
    },
    "engineering": {
        "Sun":     ["Project Leadership", "Infrastructure Policy", "Energy Systems"],
        "Moon":    ["Environmental Engineering", "Water Resources", "Human Factors"],
        "Mars":    ["Mechanical Engineering", "Aerospace", "Manufacturing"],
        "Mercury": ["Electronics & VLSI", "Signal Processing", "Embedded Systems"],
        "Jupiter": ["Structural Engineering", "Urban Planning", "Sustainable Design"],
        "Venus":   ["Product Design", "Architecture", "Industrial Design"],
        "Saturn":  ["Civil & Geotechnical", "Quality Engineering", "Process Engineering"],
        "Rahu":    ["Space Technology", "New Materials", "Autonomous Systems"],
        "Ketu":    ["Research Engineering", "Theoretical Physics", "Metrology"],
        "_default": ["Systems Engineering", "Product Development", "R&D Engineering"],
    },
    "management": {
        "Sun":     ["C-Suite Leadership", "Board Advisory", "Organisational Design"],
        "Moon":    ["HR & People Ops", "Culture & Change Management", "DEI Strategy"],
        "Mars":    ["Operations Management", "Supply Chain", "P&L Leadership"],
        "Mercury": ["Strategy & Consulting", "Business Analytics", "Digital Transformation"],
        "Jupiter": ["Social Enterprise", "NGO Leadership", "Educational Management"],
        "Venus":   ["Brand Management", "Luxury & Lifestyle Brands", "Creative Direction"],
        "Saturn":  ["Risk & Compliance", "Project Management", "Process Excellence"],
        "Rahu":    ["Startup Leadership", "International Business", "New Ventures"],
        "Ketu":    ["Turnaround Management", "Niche Markets", "Research Management"],
        "_default": ["General Management", "Business Strategy", "Leadership Development"],
    },
    "education": {
        "Sun":     ["Policy & Administration", "Institutional Leadership", "Curriculum Design"],
        "Moon":    ["Special Education", "Child Psychology", "Early Childhood"],
        "Mars":    ["Physical Education", "STEM Instruction", "Vocational Training"],
        "Mercury": ["EdTech", "Linguistics & Language Teaching", "Instructional Design"],
        "Jupiter": ["Higher Education", "Philosophy of Education", "International Schools"],
        "Venus":   ["Arts Education", "Music & Drama", "Creative Learning"],
        "Saturn":  ["Remedial Education", "Assessment & Evaluation", "Distance Learning"],
        "Rahu":    ["Global EdTech", "Online Academies", "Alternative Education"],
        "Ketu":    ["Research & Publication", "Vedic & Classical Studies", "Academic Writing"],
        "_default": ["Teaching", "Curriculum Development", "Educational Research"],
    },
    "research": {
        "Sun":     ["Policy Research", "Leadership Studies", "Think Tanks"],
        "Moon":    ["Psychology Research", "Anthropology", "Behavioural Science"],
        "Mars":    ["Materials Science", "Defence Research", "Biomechanics"],
        "Mercury": ["Computational Research", "Linguistics", "Information Science"],
        "Jupiter": ["Philosophy", "Comparative Religion", "Social Science"],
        "Venus":   ["Arts Research", "Cultural Studies", "Aesthetic Theory"],
        "Saturn":  ["Long-Term Studies", "Archival Research", "Demographic Studies"],
        "Rahu":    ["Futurism & Foresight", "Interdisciplinary Studies", "Fringe Science"],
        "Ketu":    ["Quantum/Abstract Research", "Ancient Texts", "Deep Specialisation"],
        "_default": ["Applied Research", "Data Science", "Scientific Writing"],
    },
    "arts": {
        "Sun":     ["Direction & Production", "Performance Arts", "Cultural Leadership"],
        "Moon":    ["Poetry & Literature", "Photography", "Therapeutic Arts"],
        "Mars":    ["Graphic Design", "Animation", "Game Design"],
        "Mercury": ["Screenwriting", "Journalism", "Content Strategy"],
        "Jupiter": ["Classical Music", "Heritage Arts", "Art Curation"],
        "Venus":   ["Fashion Design", "Fine Art", "Interior Design"],
        "Saturn":  ["Documentary", "Architectural Photography", "Technical Illustration"],
        "Rahu":    ["Digital Art & NFTs", "Experimental Media", "Cross-cultural Arts"],
        "Ketu":    ["Abstract Art", "Esoteric Themes", "Independent Film"],
        "_default": ["Visual Arts", "Creative Writing", "Media Production"],
    },
    "consulting": {
        "Sun":     ["Executive Coaching", "Board Consulting", "Government Advisory"],
        "Moon":    ["People & Culture Consulting", "Wellness Consulting", "UX Research"],
        "Mars":    ["Operations Consulting", "Crisis Management", "Due Diligence"],
        "Mercury": ["Digital Strategy", "Technology Consulting", "Data Analytics"],
        "Jupiter": ["ESG Consulting", "Education Consulting", "Ethics Advisory"],
        "Venus":   ["Brand & Communications", "Luxury Consulting", "Design Consulting"],
        "Saturn":  ["Risk & Regulatory", "Process Consulting", "Audit Advisory"],
        "Rahu":    ["Startup Advisory", "International Expansion", "Disruption Consulting"],
        "Ketu":    ["Niche Expertise", "Research Consulting", "Innovation Labs"],
        "_default": ["Management Consulting", "Strategy", "Business Advisory"],
    },
    "_default": {
        "_default": ["Primary Specialisation", "Applied Practice", "Research Track"],
    },
}


# ── GAP 1: Academic Depth Vector ─────────────────────────────────────────────

def compute_academic_path(
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    planet_house: Dict[str, int],
) -> Dict:
    """Return the recommended academic depth based on H4/H9/H8+Ketu strengths.

    Logic:
    - H4 lord strength → UG (undergraduate) potential
    - H9 lord strength vs H4 lord strength → PG recommendation
    - H8 lord + Ketu strength → PhD / research support
    - Multiple planets in H9 → academic extension signal

    Returns:
        {
          "ug_strong": bool,
          "pg_recommended": bool,
          "phd_supported": bool,
          "depth_label": str,
          "path_stages": [{"stage", "label", "strength_label", "recommended"}],
          "reasoning": str,
        }
    """
    h4_lord = house_lords.get("4", "")
    h9_lord = house_lords.get("9", "")
    h8_lord = house_lords.get("8", "")

    h4_str  = eff_strengths.get(h4_lord, 1.0) if h4_lord else 1.0
    h9_str  = eff_strengths.get(h9_lord, 1.0) if h9_lord else 1.0
    h8_str  = eff_strengths.get(h8_lord, 1.0) if h8_lord else 1.0
    ketu_str = eff_strengths.get("Ketu", 1.0)

    # Planets placed in H9 (multiple occupants = strong academic pull)
    h9_occupants = [p for p, h in planet_house.items() if h == 9]
    h9_occupied  = len(h9_occupants) > 0

    # Thresholds calibrated against eff_strength range (typically 0.3–2.5)
    ug_strong       = h4_str >= 0.8
    pg_recommended  = (h9_str >= h4_str * 0.9) or h9_occupied or h9_str >= 1.2
    phd_supported   = ((h8_str + ketu_str) / 2.0) >= 1.1 and ketu_str >= 1.0

    # Strength labels
    def _s_label(v: float) -> str:
        if v >= 1.5: return "Very Strong"
        if v >= 1.1: return "Strong"
        if v >= 0.8: return "Moderate"
        return "Weak"

    stages = [
        {
            "stage":         "UG",
            "label":         "Bachelor's Degree",
            "strength_label": _s_label(h4_str),
            "recommended":   True,  # always required
            "score":         round(h4_str, 3),
        },
        {
            "stage":         "PG",
            "label":         "Master's / Postgraduate",
            "strength_label": _s_label(h9_str),
            "recommended":   pg_recommended,
            "score":         round(h9_str, 3),
        },
        {
            "stage":         "PhD",
            "label":         "Doctorate / Research",
            "strength_label": _s_label((h8_str + ketu_str) / 2.0),
            "recommended":   phd_supported,
            "score":         round((h8_str + ketu_str) / 2.0, 3),
        },
    ]

    # Overall depth label
    if phd_supported:
        depth_label = "Research-Depth Profile — PhD pathway supported"
    elif pg_recommended:
        depth_label = "Masters-Level Profile — PG strongly recommended for peak impact"
    else:
        depth_label = "Practitioner Profile — UG + professional certification is sufficient"

    # Build reasoning string
    parts = []
    if ug_strong:
        parts.append(f"H4 lord ({h4_lord}, {_s_label(h4_str)}) ensures a solid undergraduate foundation")
    if pg_recommended:
        if h9_occupied:
            parts.append(f"H9 occupied by {', '.join(h9_occupants)} — academic extension is natural")
        else:
            parts.append(f"H9 lord ({h9_lord}, {_s_label(h9_str)}) matches or exceeds H4 strength — postgraduate studies unlock career acceleration")
    if phd_supported:
        parts.append(f"Ketu ({_s_label(ketu_str)}) + H8 lord ({h8_lord}, {_s_label(h8_str)}) support deep investigation and thesis-level research")

    return {
        "ug_strong":      ug_strong,
        "pg_recommended": pg_recommended,
        "phd_supported":  phd_supported,
        "depth_label":    depth_label,
        "path_stages":    stages,
        "reasoning":      ". ".join(parts) if parts else "Standard academic path applicable.",
    }


# ── GAP 2: Institutional Prestige Tier ───────────────────────────────────────

# Target institution archetypes per tier
_TIER_ARCHETYPES = {
    "Tier1_Premier": {
        "archetype":       "Premier National / Ivy-League Equivalent",
        "target_examples": ["IITs / IIMs / AIIMS (India)", "Oxbridge / Russell Group (UK)",
                            "Ivy League / Top-20 Research Universities (US)",
                            "NUS / NTU (Singapore)", "ETH Zürich / TU Munich (Europe)"],
    },
    "Tier1_Foreign": {
        "archetype":       "Premier International / Global Research University",
        "target_examples": ["MIT / Stanford / Caltech (US)", "Imperial / LSE / UCL (UK)",
                            "University of Toronto / UBC (Canada)", "Monash / ANU (Australia)",
                            "Sciences Po / INSEAD (Europe)"],
    },
    "Tier2_Technical": {
        "archetype":       "Specialist Technical / Applied Institute",
        "target_examples": ["NITs / BITS / VIT (India)", "Top State Engineering Colleges",
                            "Polytechnics with Industry Tie-ups", "Applied Science Universities"],
    },
    "Tier2_Professional": {
        "archetype":       "Professional School / Mid-Tier National College",
        "target_examples": ["Accredited Private Universities", "State Universities with Strong Departments",
                            "Professional Institutes (Law / Finance / Medical colleges)"],
    },
}

def compute_institutional_tier(
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    lagna_sign: str,
    md_lord: str = "",
    ad_lord: str = "",
    transit_planets: Dict = None,
) -> Dict:
    """Return institutional prestige tier driven primarily by MD-AD + transits,
    with natal chart as the baseline floor.

    Tier decision logic:
    ─────────────────────────────────────────────────────────────────────────
    MD/AD activation (primary signal):
      • MD/AD = Jupiter → strong Premier uplift
      • MD/AD = Sun     → moderate Premier uplift
      • MD/AD = Rahu    → foreign pull activated
      • MD/AD = Saturn  → Technical/applied orientation
      • MD/AD = Mars    → Technical/applied orientation

    Transit amplifiers (secondary):
      • Jupiter transiting H4, H9, H1, H5 → Premier boost
      • Jupiter transiting H12 → Foreign boost
      • Saturn transiting H4 or H9         → Technical/applied signal
      • Rahu transiting H9 or H12          → Foreign pull

    Natal baseline (floor — prevents absurd downgrades):
      • Sun × 0.4 + Jupiter × 0.6 + 0.3 if Jupiter natal in H4/H9/H1/H5
      • Mars × 0.5 + Saturn × 0.5 for technical floor
    ─────────────────────────────────────────────────────────────────────────
    """
    transit_planets = transit_planets or {}

    # ── Natal strengths ───────────────────────────────────────────────────
    sun_str  = eff_strengths.get("Sun",     1.0)
    jup_str  = eff_strengths.get("Jupiter", 1.0)
    mar_str  = eff_strengths.get("Mars",    1.0)
    sat_str  = eff_strengths.get("Saturn",  1.0)
    rahu_str = eff_strengths.get("Rahu",    1.0)

    jup_house  = planet_house.get("Jupiter", 0)
    rahu_house = planet_house.get("Rahu",    0)
    h12_lord   = house_lords.get("12", "")
    h12_str    = eff_strengths.get(h12_lord, 1.0) if h12_lord else 1.0

    jup_academic   = jup_house in (1, 4, 5, 9)
    rahu_foreign   = rahu_house in (9, 12, 4, 3)
    h12_foreign    = h12_str >= 1.1

    natal_premier  = (sun_str * 0.4 + jup_str * 0.6) + (0.3 if jup_academic else 0)
    natal_technical = mar_str * 0.5 + sat_str * 0.5
    natal_foreign  = (rahu_str * 0.5 + h12_str * 0.3) + (0.4 if rahu_foreign else 0) + (0.2 if h12_foreign else 0)

    # ── MD-AD activation (primary) ───────────────────────────────────────
    _PREMIER_LORDS  = {"Jupiter", "Sun", "Moon"}       # Moon in 4th/9th gives educational prestige
    _TECHNICAL_LORDS = {"Mars", "Saturn", "Ketu"}
    _FOREIGN_LORDS   = {"Rahu", "Ketu", "Venus"}       # Venus → overseas creative/arts

    md_premier   = 0.5 if md_lord in _PREMIER_LORDS  else 0.0
    md_technical = 0.4 if md_lord in _TECHNICAL_LORDS else 0.0
    md_foreign   = 0.5 if md_lord in _FOREIGN_LORDS  else 0.0

    # AD adds half the MD weight
    ad_premier   = 0.25 if ad_lord in _PREMIER_LORDS   else 0.0
    ad_technical = 0.20 if ad_lord in _TECHNICAL_LORDS else 0.0
    ad_foreign   = 0.25 if ad_lord in _FOREIGN_LORDS   else 0.0

    # ── Transit amplifiers ───────────────────────────────────────────────
    tr_jup_house  = (transit_planets.get("Jupiter") or {}).get("house", 0)
    tr_sat_house  = (transit_planets.get("Saturn")  or {}).get("house", 0)
    tr_rahu_house = (transit_planets.get("Rahu")    or {}).get("house", 0)

    transit_premier  = 0.3 if tr_jup_house in (1, 4, 5, 9) else 0.0
    transit_foreign  = (0.3 if tr_jup_house == 12 else 0.0) + (0.2 if tr_rahu_house in (9, 12) else 0.0)
    transit_technical = 0.2 if tr_sat_house in (4, 9) else 0.0

    # ── Final composite scores ────────────────────────────────────────────
    premier_score  = natal_premier  + md_premier  + ad_premier  + transit_premier
    technical_score = natal_technical + md_technical + ad_technical + transit_technical
    foreign_score  = natal_foreign  + md_foreign  + ad_foreign  + transit_foreign

    # ── Tier decision ─────────────────────────────────────────────────────
    if foreign_score >= 1.5 and premier_score >= 1.2:
        tier_key  = "Tier1_Foreign"
        tier_label = "Tier 1 International"
    elif premier_score >= 1.2:
        tier_key  = "Tier1_Premier"
        tier_label = "Tier 1 National / Premier"
    elif technical_score >= 1.1:
        tier_key  = "Tier2_Technical"
        tier_label = "Tier 2 Technical / Specialist"
    else:
        tier_key  = "Tier2_Professional"
        tier_label = "Tier 2 Professional"

    archetype_data = _TIER_ARCHETYPES.get(tier_key, _TIER_ARCHETYPES["Tier2_Professional"])

    return {
        "tier":             tier_label,
        "tier_key":         tier_key,
        "archetype":        archetype_data["archetype"],
        "target_examples":  archetype_data["target_examples"],
        "prestige_score":   round(premier_score, 3),
        "foreign_pull":     foreign_score >= 1.2,
        "foreign_score":    round(foreign_score, 3),
        "md_lord":          md_lord,
        "ad_lord":          ad_lord,
    }


# ── GAP 3: Micro-Niche Specialisations ───────────────────────────────────────

def compute_micro_niches(
    field_result: Dict,
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    amatyakaraka: str = "",
    nakshatra_data: Dict[str, str] = None,
) -> Dict:
    """Return 2-4 micro-niche specialisations for a field.

    Priority source hierarchy:
    1. Registry niche string (field-specific, e.g. "Reservoir / Drilling / Production / EOR")
       Split by '/' and return up to 3 sub-niches — this ensures each field has distinct niches.
    2. If registry niche absent, fall back to planet-domain map (AmK nakshatra lord → domain map).

    Planet driver still applied: indicates WHICH of the registry sub-niches to rank first,
    based on AmK nakshatra lord or secondary affinity planet.

    Returns:
        {"micro_niches": [str, ...], "niche_driver": str, "driver_planet": str,
         "niche_source": "registry" | "planet_map"}
    """
    nakshatra_data = nakshatra_data or {}
    domain = field_result.get("domain", "_default")

    # ── Planet driver logic (used for ranking registry sub-niches) ─────────────
    amk_nakshatra  = nakshatra_data.get(amatyakaraka, "")
    amk_nak_lord   = _NAKSHATRA_LORD.get(amk_nakshatra, "")

    affinity = field_result.get("affinity_planets", {})
    sorted_planets = sorted(affinity.items(), key=lambda x: x[1], reverse=True)
    secondary_planet = sorted_planets[1][0] if len(sorted_planets) >= 2 else ""
    top_planet       = sorted_planets[0][0]  if len(sorted_planets) >= 1 else ""

    amk_house    = planet_house.get(amatyakaraka, 0)
    conjunct_amk = [p for p, h in planet_house.items()
                    if h == amk_house and p != amatyakaraka and p not in ("Ketu",)]

    driver_planet = amk_nak_lord or secondary_planet or top_planet or "Mercury"
    if amk_nak_lord:
        niche_driver = f"AmK ({amatyakaraka}) in {amk_nakshatra} Nakshatra (lord: {amk_nak_lord})"
    elif secondary_planet:
        niche_driver = f"Secondary affinity planet: {secondary_planet}"
    else:
        niche_driver = f"Primary affinity planet: {top_planet}"

    # ── Source 1: registry niche (field-specific) ──────────────────────────────
    _reg = field_result.get("registry") or {}
    reg_niche_str = _reg.get("niche", "")

    # Reject generic placeholders — fall through to planet_map or field-level specialization
    _GENERIC_PLACEHOLDERS = {"specialized industry practice", "core industry practice", ""}
    if reg_niche_str and reg_niche_str.strip().lower() not in _GENERIC_PLACEHOLDERS:
        pass  # use it as-is below
    elif reg_niche_str.strip().lower() in _GENERIC_PLACEHOLDERS and reg_niche_str:
        # Build a unique niche from specialization + track from the registry
        spec  = _reg.get("specialization", "")
        track = _reg.get("track", "")
        label = _reg.get("label", "")
        # Compose up to 3 distinct sub-niches from available fields
        composed = []
        if spec  and spec  not in composed: composed.append(spec)
        if track and track not in composed: composed.append(track)
        if label and label not in composed: composed.append(label)
        reg_niche_str = " / ".join(composed[:3]) if composed else ""

    if reg_niche_str and reg_niche_str.strip().lower() not in _GENERIC_PLACEHOLDERS:
        # Split "Open-Pit / Underground / Mine Planning / Blasting" → individual sub-niches
        raw_subs = [s.strip() for s in reg_niche_str.replace("|", "/").split("/") if s.strip()]

        # Use planet driver to re-rank: if driver planet's domain_map has hints, promote matching
        domain_map   = _DOMAIN_MICRO_NICHES.get(domain, _DOMAIN_MICRO_NICHES["_default"])
        planet_hints = [n.lower() for n in domain_map.get(driver_planet, [])]

        def _relevance(sub: str) -> int:
            sub_l = sub.lower()
            return sum(1 for hint in planet_hints if hint[:8] in sub_l or sub_l[:8] in hint)

        ranked_subs = sorted(raw_subs, key=_relevance, reverse=True)

        # Optionally append one cross-domain niche from conjunct AmK planet
        cross_niche = None
        if conjunct_amk:
            conj_niches = domain_map.get(conjunct_amk[0], [])
            if conj_niches and conj_niches[0] not in ranked_subs:
                cross_niche = conj_niches[0]

        result_niches = ranked_subs[:3]
        if cross_niche and len(result_niches) < 4:
            result_niches.append(cross_niche)

        return {
            "micro_niches":   result_niches[:4],
            "niche_driver":   niche_driver,
            "driver_planet":  driver_planet,
            "amk_nakshatra":  amk_nakshatra,
            "niche_source":   "registry",
        }

    # ── Source 2: fallback to planet-domain map ────────────────────────────────
    domain_map = _DOMAIN_MICRO_NICHES.get(domain, _DOMAIN_MICRO_NICHES["_default"])
    niches = domain_map.get(driver_planet, domain_map.get("_default", [
        "Core Practice", "Applied Research", "Leadership Track"
    ]))

    cross_niche = None
    if conjunct_amk and driver_planet not in conjunct_amk:
        conj_niches = domain_map.get(conjunct_amk[0], [])
        if conj_niches and conj_niches[0] not in niches:
            cross_niche = conj_niches[0]

    result_niches = list(niches[:3])
    if cross_niche and len(result_niches) < 4:
        result_niches.append(cross_niche)

    return {
        "micro_niches":   result_niches[:3],
        "niche_driver":   niche_driver,
        "driver_planet":  driver_planet,
        "amk_nakshatra":  amk_nakshatra,
        "niche_source":   "planet_map",
    }


# ── GAP 4: Confidence Matrix (called in engine.py merge step) ────────────────

def build_confidence_matrix(field_result: Dict) -> Dict:
    """Normalise method scores into a % confidence matrix.

    Uses method_normalized_scores (already 0–100 scale, relative to best field).
    Falls back to raw scores if normalised not present.

    Returns:
        {
          "knrao_pct":            int,   # KN Rao (whole-sign + karakas) — weight 0.35
          "kp_pct":               int,   # KP (cusp sub-lords)           — weight 0.25
          "jaimini_pct":          int,   # Jaimini (aptitude/vocational) — weight 0.20
          "parashara_pct":        int,   # Parashara (yoga strength)     — weight 0.20
          "sbc_pct":              int,   # SBC event-timing score as %   — display only
          "alignment_confidence": int,   # concordance: mean × (1 - spread/100)
        }
    """
    mn = field_result.get("method_normalized_scores") or \
         field_result.get("method_scores_normalized_0_100") or \
         field_result.get("method_scores_normalized") or {}

    # method_normalized_scores are already 0–100 relative to best field in run
    knrao_raw     = float(mn.get("knrao",    field_result.get("knrao_score",    0)) or 0)
    kp_raw        = float(mn.get("kp",       field_result.get("kp_score",       0)) or 0)
    jaimini_raw   = float(mn.get("jaimini",  field_result.get("jaimini_score",  0)) or 0)
    parashara_raw = float(mn.get("parashara",field_result.get("parashara_score",0)) or 0)

    # SBC (Sthira Bhava Chakra) event-timing score: already 0–100 scale
    sbc_raw = float(field_result.get("sbc_event_score", 0) or 0)

    # Soft compression: keeps top scores high, lifts lower scores slightly
    def _pct(v: float) -> int:
        return min(int(round(v * 0.92 + 5)), 99) if v > 5 else int(round(v))

    knrao_pct     = _pct(knrao_raw)
    kp_pct        = _pct(kp_raw)
    jaimini_pct   = _pct(jaimini_raw)
    parashara_pct = _pct(parashara_raw)
    # SBC is already a 0–100 confidence score — apply same compression for display consistency
    sbc_pct       = _pct(sbc_raw)

    # Concordance-based alignment:
    #   mean        = weighted average (KNRao 35%, KP 25%, Jaimini 20%, Parashara 20%)
    #   spread      = max - min across the 4 raw method %s
    #   concordance = max(0, 1 - spread/150)
    #                 ÷150 (not ÷100) so a 30pt spread → 20% penalty, not 30%.
    #                 Prevents over-penalising charts where one method is
    #                 structurally bounded lower (e.g. KP capped at 60).
    #   alignment%  = round(mean × concordance)   ← round avoids truncation bias
    _method_scores = [knrao_pct, kp_pct, jaimini_pct, parashara_pct]
    _mean = (
        knrao_pct * 0.35 + kp_pct * 0.25 + jaimini_pct * 0.20 + parashara_pct * 0.20
    )
    _spread      = max(_method_scores) - min(_method_scores)
    _concordance = max(0.0, 1.0 - _spread / 150.0)
    alignment    = int(round(_mean * _concordance))

    return {
        "knrao_pct":            knrao_pct,
        "kp_pct":               kp_pct,
        "jaimini_pct":          jaimini_pct,
        "parashara_pct":        parashara_pct,
        "sbc_pct":              sbc_pct,
        "alignment_confidence": alignment,
    }

# ── Chart-type detection ──────────────────────────────────────────────────────

# Substring fragments matched case-insensitively against registry track values
# e.g. "Computer Science & Engineering" → matches "computer science" → "Technology"
_TRACK_DOMAIN_FRAGMENTS: List[tuple] = [
    # Technology / CS
    ("computer science",        "Technology"),
    ("data science",            "Technology"),
    ("information technology",  "Technology"),
    ("artificial intelligence", "Technology"),
    ("software",                "Technology"),
    # Engineering
    ("engineering",             "Engineering"),
    ("architecture",            "Engineering"),
    # Science
    ("physics",                 "Science"),
    ("chemistry",               "Science"),
    ("biology",                 "Science"),
    ("mathematics",             "Science"),
    ("statistics",              "Science"),
    ("life science",            "Science"),
    ("earth science",           "Science"),
    ("agricultural",            "Science"),
    ("environmental",           "Science"),
    # Medicine / Health
    ("medical",                 "Medicine & Health"),
    ("medicine",                "Medicine & Health"),
    ("pharmacy",                "Medicine & Health"),
    ("nursing",                 "Medicine & Health"),
    ("health",                  "Medicine & Health"),
    ("psychology",              "Medicine & Health"),
    ("dentistry",               "Medicine & Health"),
    # Law / Governance
    ("law",                     "Law & Governance"),
    ("legal",                   "Law & Governance"),
    ("public policy",           "Law & Governance"),
    ("governance",              "Law & Governance"),
    ("political",               "Law & Governance"),
    # Business / Finance
    ("business",                "Business & Finance"),
    ("finance",                 "Business & Finance"),
    ("economics",               "Business & Finance"),
    ("commerce",                "Business & Finance"),
    ("management",              "Business & Finance"),
    ("accounting",              "Business & Finance"),
    # Humanities / Arts / Media
    ("humanities",              "Humanities & Arts"),
    ("literature",              "Humanities & Arts"),
    ("journalism",              "Humanities & Arts"),
    ("media",                   "Humanities & Arts"),
    ("design",                  "Humanities & Arts"),
    ("performing arts",         "Humanities & Arts"),
    ("fine arts",               "Humanities & Arts"),
    ("language",                "Humanities & Arts"),
    ("history",                 "Humanities & Arts"),
    ("philosophy",              "Humanities & Arts"),
    # Education / Research
    ("research",                "Research & Academia"),
    ("education",               "Research & Academia"),
    ("teaching",                "Research & Academia"),
]


def _track_to_domain(track: str, label: str = "") -> str:
    """Map a registry track string to a broad domain label via substring matching."""
    t = (track or label or "").lower()
    for fragment, domain in _TRACK_DOMAIN_FRAGMENTS:
        if fragment in t:
            return domain
    return "Other"


def detect_chart_type(fields: List[Dict]) -> Dict:
    """Detect whether the chart is Specialist or Cluster (Polymathic).

    Uses METHOD scores (KNRao/KP/Jaimini/Parashara average), NOT final_score.
    final_score is LLM-adjusted and inflated — method scores reflect true
    astrological signal convergence across methods.

    Cluster    : avg method score < 55 AND top-5 method spread < 15
                 → aptitude distributed, no single field dominates
    Specialist : avg method score >= 60 AND spread >= 20
                 → clear dominant field
    Mixed      : everything in between

    Returns a dict with:
        type            : "specialist" | "cluster" | "mixed"
        is_cluster      : bool
        top_score       : float  (top method avg)
        spread          : float
        domain_clusters : Dict[domain_label → List[field_id]]
        cluster_label   : human-readable label
    """
    def _method_avg(f: Dict) -> float:
        """Return alignment_confidence for this field (0–100).

        alignment_confidence = mean × concordance = method avg × (1 - spread/100)
        It captures both signal strength AND method agreement, making it the right
        anchor for cluster detection: a cluster chart has no field with high,
        concordant multi-method support.

        Priority:
        1. confidence_matrix["alignment_confidence"]  (set by build_confidence_matrix)
        2. Recompute from *_pct keys if alignment key missing
        3. Raw method_normalized_scores (0-100 scale) fallback — no concordance applied
        """
        cm = f.get("confidence_matrix") or {}

        # Best case: alignment_confidence already computed
        ac = cm.get("alignment_confidence")
        if ac is not None and float(ac or 0) > 0:
            return float(ac)

        # Recompute from pct keys
        if cm.get("knrao_pct") or cm.get("kp_pct"):
            k  = float(cm.get("knrao_pct",    0) or 0)
            kp = float(cm.get("kp_pct",       0) or 0)
            j  = float(cm.get("jaimini_pct",  0) or 0)
            p  = float(cm.get("parashara_pct",0) or 0)
            mean_  = k * 0.35 + kp * 0.25 + j * 0.20 + p * 0.20
            spread = max(k, kp, j, p) - min(k, kp, j, p)
            return round(mean_ * max(0.0, 1.0 - spread / 100.0), 2)

        # Last resort: plain method avg from normalized scores (0-100 scale)
        mn = (f.get("method_normalized_scores") or
              f.get("method_scores_normalized_0_100") or
              f.get("method_scores_normalized") or {})
        vals = [float(v or 0) for v in mn.values() if float(v or 0) > 0]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    sorted_fields = sorted(fields, key=_method_avg, reverse=True)
    top5  = sorted_fields[:5]
    scores = [_method_avg(f) for f in top5]

    if not scores:
        return {"type": "unknown", "is_cluster": False, "top_score": 0,
                "spread": 0, "domain_clusters": {}, "cluster_label": ""}

    top_score = scores[0]
    spread    = scores[0] - scores[-1] if len(scores) > 1 else 0

    if top_score >= 65 and spread >= 20:
        chart_type    = "specialist"
        is_cluster    = False
        cluster_label = "Specialist Aptitude"
    elif top_score < 60 and spread < 15:
        # Cluster: even the best field scores below 60 AND top-5 are tightly bunched
        # → aptitude distributed, no single field dominates
        chart_type    = "cluster"
        is_cluster    = True
        cluster_label = "Polymathic / Cluster Aptitude"
    else:
        chart_type    = "mixed"
        is_cluster    = False
        cluster_label = "Focused Aptitude"

    # Build domain clusters from top-15 fields using substring matching
    domain_clusters: Dict[str, List[str]] = {}
    for f in sorted_fields[:15]:
        reg    = f.get("registry") or {}
        track  = reg.get("track", "")
        label  = reg.get("label", "")
        domain = _track_to_domain(track, label)
        fid    = f.get("field_id", "")
        if fid:
            domain_clusters.setdefault(domain, []).append(fid)

    return {
        "type":            chart_type,
        "is_cluster":      is_cluster,
        "top_score":       round(top_score, 1),
        "spread":          round(spread, 1),
        "domain_clusters": domain_clusters,
        "cluster_label":   cluster_label,
    }


# ── Additional domain mappings appended post-initial-write ───────────────────
_DOMAIN_MICRO_NICHES.update({
    "humanities": {
        "Sun":     ["Classical Studies", "Heritage & Cultural Policy", "Political Philosophy"],
        "Moon":    ["Linguistics & Language Acquisition", "Literature & Narrative", "Sociolinguistics"],
        "Mars":    ["History of Conflict", "Rhetoric & Persuasion", "Journalism"],
        "Mercury": ["Computational Linguistics", "Translation Studies", "Semiotics"],
        "Jupiter": ["Philosophy", "Comparative Religion", "Moral Theory"],
        "Venus":   ["Creative Writing", "Aesthetics & Art History", "Gender Studies"],
        "Saturn":  ["Archival Studies", "Economic History", "Social Policy Research"],
        "Rahu":    ["Digital Humanities", "Cross-Cultural Studies", "Global Communication"],
        "Ketu":    ["Ancient Languages", "Mythology & Symbolism", "Deep Textual Analysis"],
        "_default": ["Linguistics", "Cultural Studies", "Academic Research"],
    },
    "science": {
        "Sun":     ["Astrophysics", "Nuclear Physics", "Scientific Leadership"],
        "Moon":    ["Marine Biology", "Ecology", "Behavioural Science"],
        "Mars":    ["Forensic Science", "Sports Science", "Biomechanics"],
        "Mercury": ["Data Science", "Computational Biology", "Bioinformatics"],
        "Jupiter": ["Evolutionary Biology", "Climate Science", "Science Policy"],
        "Venus":   ["Biochemistry", "Food Science", "Pharmaceutical Research"],
        "Saturn":  ["Geology", "Materials Science", "Environmental Monitoring"],
        "Rahu":    ["Quantum Physics", "Space Science", "Nanotechnology"],
        "Ketu":    ["Pure Mathematics", "Theoretical Physics", "Deep Research"],
        "_default": ["Applied Sciences", "Research & Development", "Laboratory Science"],
    },
    "commerce": {
        "Sun":     ["Investment Banking", "Corporate Governance", "Trade Policy"],
        "Moon":    ["Retail & Consumer Markets", "FMCG", "Market Research"],
        "Mars":    ["Commodities Trading", "Supply Chain", "Sales Leadership"],
        "Mercury": ["E-Commerce", "Digital Marketing", "Business Analytics"],
        "Jupiter": ["Social Enterprise", "Ethical Commerce", "International Trade"],
        "Venus":   ["Luxury Goods", "Fashion Retail", "Brand Commerce"],
        "Saturn":  ["Accounting & Audit", "Tax Strategy", "Risk & Compliance"],
        "Rahu":    ["Startup Commerce", "Crypto Commerce", "Cross-Border Trade"],
        "Ketu":    ["Commodity Niche Markets", "Niche Exports", "Research Commerce"],
        "_default": ["Commerce & Trade", "Business Development", "Financial Management"],
    },
    "public": {
        "Sun":     ["Government Administration", "Public Policy", "Political Leadership"],
        "Moon":    ["Social Work", "Community Development", "Public Health"],
        "Mars":    ["Defence & Security", "Law Enforcement", "Disaster Management"],
        "Mercury": ["Public Communications", "Policy Research", "E-Governance"],
        "Jupiter": ["International Relations", "Human Rights", "Diplomacy"],
        "Venus":   ["Cultural Affairs", "Public Arts", "Urban Design"],
        "Saturn":  ["Urban Planning", "Infrastructure Policy", "Regulatory Bodies"],
        "Rahu":    ["Global Policy", "International Development", "Multilateral Affairs"],
        "Ketu":    ["Historical Archives", "Tribal & Rural Development", "Niche Advocacy"],
        "_default": ["Public Administration", "Policy Analysis", "Civil Services"],
    },
    "interdisciplinary": {
        "Sun":     ["Leadership Studies", "Innovation Management", "Future Studies"],
        "Moon":    ["Cognitive Science", "Behavioural Economics", "Psychology & Tech"],
        "Mars":    ["Sports Analytics", "Bio-Engineering", "Action Research"],
        "Mercury": ["Information Science", "Digital Humanities", "Tech-Humanities Bridge"],
        "Jupiter": ["Philosophy of Science", "Ethics in Technology", "Global Development"],
        "Venus":   ["Creative Industries", "Design Thinking", "Experience Design"],
        "Saturn":  ["Systems Thinking", "Sustainability Studies", "Complex Systems"],
        "Rahu":    ["Futurism", "Emerging Disciplines", "Cross-Domain Innovation"],
        "Ketu":    ["Integral Studies", "Ancient Wisdom Meets Modern Science", "Deep Research"],
        "_default": ["Cross-Domain Studies", "Applied Interdisciplinary", "Innovation Research"],
    },
})


# ─────────────────────────────────────────────────────────────────────────────
# Field Summary JSON builder  (Schema v1)
# ─────────────────────────────────────────────────────────────────────────────

def build_field_summary_json(field_result: dict) -> dict:
    """Return a clean, schema-compliant summary dict for a single field result."""
    # ── Academic path stages ──────────────────────────────────────────────────
    _ap     = field_result.get("academic_path") or {}
    _stages = _ap.get("path_stages", [])
    ug_req  = any(s.get("stage") == "UG"  for s in _stages)
    pg_rec  = any(s.get("stage") == "PG"  and s.get("recommended") for s in _stages)
    phd_sup = any(s.get("stage") == "PhD" and s.get("recommended") for s in _stages)

    # ── Confidence matrix ─────────────────────────────────────────────────────
    _cm = field_result.get("confidence_matrix") or {}
    confidence_matrix = {
        "knrao_classical":     f"{_cm.get('knrao_pct', 0)}%",
        "kp_alignment":        f"{_cm.get('kp_pct', 0)}%",
        "jaimini_aptitude":    f"{_cm.get('jaimini_pct', 0)}%",
        "parashara_strength":  f"{_cm.get('parashara_pct', 0)}%",
        "sbc_timing":          f"{_cm.get('sbc_pct', 0)}%",
        "overall":             f"{_cm.get('alignment_confidence', 0)}%",
    }

    # ── Institutional tier ────────────────────────────────────────────────────
    _it       = field_result.get("institutional_tier") or {}
    tier_str  = _it.get("tier", "")
    arch_str  = _it.get("archetype", "")
    tier_label = f"{tier_str} — {arch_str}" if tier_str and arch_str else tier_str or arch_str
    _tier_key  = _it.get("tier_key", "")

    _reg_av  = (field_result.get("registry") or {}).get("available_at") or {}
    if isinstance(_reg_av, str):
        try:
            import ast as _avast; _reg_av = _avast.literal_eval(_reg_av)
        except Exception: _reg_av = {}

    _TIER_ALLOW = {
        "Tier1_Premier":      {"IIT", "IISER", "ISI", "BITS", "central_universities", "liberal_arts_private"},
        "Tier1_Foreign":      {"IIT", "IISER", "ISI", "BITS", "central_universities"},
        "Tier2_Technical":    {"NIT", "BITS", "IIIT", "deemed_private", "state_universities"},
        "Tier2_Professional": {"central_universities", "liberal_arts_private", "deemed_private", "state_universities", "BITS"},
    }
    _av_allowed = _TIER_ALLOW.get(_tier_key, set(_TIER_ALLOW["Tier2_Professional"]))

    def _avail_examples(av: dict) -> list:
        _PREFIX_KEYS = {"IIT", "NIT", "BITS", "IISER", "ISI"}
        _BOOL_LABEL  = {
            "IIIT": "IIITs", "state_universities": "State Universities",
            "deemed_private": "Deemed / Private",
            "central_universities": None, "liberal_arts_private": None,
        }
        out = []
        for key, val in av.items():
            if key not in _av_allowed: continue
            if val is False or val is None: continue
            if val is True:
                label = _BOOL_LABEL.get(key, key.replace("_", " ").title())
                if label: out.append(label)
            elif isinstance(val, list) and val:
                if val == ["All_IITs"]: out.append("All IITs"); continue
                if val == ["All_NITs"]: out.append("All NITs"); continue
                clean = [v.replace(f"{key}_", "").replace("_", " ") for v in val[:3]]
                if key in _PREFIX_KEYS:
                    out.append(f"{key} {' / '.join(clean)}")
                else:
                    out.append(" / ".join(clean))
        return out[:4]

    _field_target_examples = _avail_examples(_reg_av) if _reg_av else _it.get("target_examples", [])

    # ── 360° Insights ────────────────────────────────────────────────────────────
    _wp  = field_result.get("wealth_potential") or {}
    _br  = field_result.get("burnout_risk_detail") or {}
    _geo = field_result.get("geography_insight") or {}
    geo_label = _geo.get("geography_label", "") or _geo.get("geography", "")

    insights = {
        "wealth":    _wp.get("wealth_potential", ""),
        "geography": geo_label,
        "burnout":   _br.get("burnout_risk", ""),
    }

    _mn = field_result.get("micro_niches") or []

    return {
        "field_id":          field_result.get("field_id", ""),
        "total_score":       field_result.get("final_score", field_result.get("total_score", 0)),
        "confidence_matrix": confidence_matrix,
        "execution_path": {
            "ug_required":     ug_req,
            "pg_recommended":  pg_rec,
            "phd_supported":   phd_sup,
            "tier":            tier_label,
            "target_examples": _field_target_examples,
        },
        "micro_niches": _mn,
        "insights":     insights,
    }
