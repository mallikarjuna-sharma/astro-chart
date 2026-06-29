"""JyotishAI — Prashna (Horary Astrology) Engine  v1.0

Prashna = the moment of the question becomes the chart. No birth data required.

Architecture
------------
1. cast_prashna_chart(moment, lat, lon)
       → computes planetary longitudes for that instant using ephem (Swiss Eph wrapper)
       → returns PrashnaChart (planets_d1, kp_cusps, lagna_sign, etc.)

2. analyze_prashna(chart, category, question)
       → routes to per-category analyzer (_analyze_career, _analyze_business, …)
       → each analyzer applies:
             a) KP sub-lord method (House cusp sub-lord significators)
             b) Classical Parashari rules (lord-of-house, aspect, application)
             c) Moon application / void-of-course test
             d) Sarvatobhadra / Tajika aspect modifiers (simplified)
       → returns PrashnaResult

3. generate_prashna_html(result) → standalone HTML report string

Categories supported
--------------------
  career_employment  → H1, H6, H10, H11
  business           → H1, H7, H10, H11
  education          → H1, H4, H5, H9
  foreign_opportunity→ H1, H9, H12
  financial          → H1, H2, H11
  job_change         → H1, H3, H6, H10, H12
  health             → H1, H6, H8
  relationship       → H1, H7
  property           → H1, H4
  legal              → H1, H6, H7, H9

Integration
-----------
  from jyotish.prashna import cast_prashna_chart, analyze_prashna, generate_prashna_html
  chart  = cast_prashna_chart(datetime.now(), lat=12.97, lon=77.59)
  result = analyze_prashna(chart, category="career_employment", question="Will I get the job?")
  html   = generate_prashna_html(result)
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional, Tuple
# --- ADD THIS LINE HERE ---
from dataclasses import dataclass, field
logger = logging.getLogger("jyotish_prashna")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Vimshottari sequence & years
_VIMSHO_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
_VIMSHO_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
                 "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}
_VIMSHO_TOTAL = 120.0

# Sign → ruler
_SIGN_LORD: Dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}
_SIGN_NUM: Dict[str, int] = {
    "Aries": 1, "Taurus": 2, "Gemini": 3, "Cancer": 4,
    "Leo": 5, "Virgo": 6, "Libra": 7, "Scorpio": 8,
    "Sagittarius": 9, "Capricorn": 10, "Aquarius": 11, "Pisces": 12,
}
_NUM_SIGN: Dict[int, str] = {v: k for k, v in _SIGN_NUM.items()}

# Nakshatra lords (27 nakshatras, 0-indexed)
_NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishtha",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
_NAKSHATRA_LORD_SEQ = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
]

# KP sub-lord divides each nakshatra into 9 sub-periods proportional to Vimshottari years
# Each nakshatra = 13°20' = 800'. Each sub-period = 800' × (years/120)
_SUB_ORB: List[Tuple[str, float]] = []  # built lazily in _build_sub_ords()

# Dignity
_EXALT_SIGN = {"Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
               "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces",
               "Saturn": "Libra", "Rahu": "Gemini", "Ketu": "Sagittarius"}
_DEBIL_SIGN  = {"Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
                "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo",
                "Saturn": "Aries", "Rahu": "Sagittarius", "Ketu": "Gemini"}
_OWN_SIGNS   = {"Sun": ["Leo"], "Moon": ["Cancer"], "Mars": ["Aries", "Scorpio"],
                "Mercury": ["Gemini", "Virgo"], "Jupiter": ["Sagittarius", "Pisces"],
                "Venus": ["Taurus", "Libra"], "Saturn": ["Capricorn", "Aquarius"]}

# Natural benefics / malefics
_NATURAL_BENEFICS  = {"Jupiter", "Venus", "Moon", "Mercury"}
_NATURAL_MALEFICS  = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}

# House significations per category
_CATEGORY_HOUSES: Dict[str, Dict[str, List[int]]] = {
    "career_employment":  {"primary": [10, 6], "support": [1, 11], "denial": [12]},
    "business":           {"primary": [10, 7], "support": [1, 11], "denial": [12]},
    "education":          {"primary": [5, 9],  "support": [1, 4],  "denial": [6, 8]},
    "foreign_opportunity":{"primary": [12, 9], "support": [1, 3],  "denial": [6]},
    "financial":          {"primary": [2, 11], "support": [1, 5],  "denial": [12, 8]},
    "job_change":         {"primary": [10, 3], "support": [6, 1],  "denial": [12]},
    "health":             {"primary": [1, 6],  "support": [11],    "denial": [8, 12]},
    "relationship":       {"primary": [7, 2],  "support": [1, 11], "denial": [6, 8, 12]},
    "property":           {"primary": [4, 11], "support": [1, 2],  "denial": [8, 12]},
    "legal":              {"primary": [6, 9],  "support": [1, 11], "denial": [8, 12]},
    "marriage":           {"primary": [7],     "support": [2, 11], "denial": [6, 8, 12]},
    "travel":             {"primary": [3, 9, 12], "support": [1, 7], "denial": [6]},
    "pregnancy":          {"primary": [5, 8],  "support": [1, 11], "denial": [6, 12]},
    "competition":        {"primary": [6, 10], "support": [1, 11], "denial": [8, 12]},
}

# Question → affirm vs. deny sub-lord target houses
_AFFIRM_HOUSES = {k: v["primary"] + v["support"] for k, v in _CATEGORY_HOUSES.items()}
_DENY_HOUSES   = {k: v["denial"]                  for k, v in _CATEGORY_HOUSES.items()}

# Friendly narration labels per category
_CATEGORY_LABELS: Dict[str, str] = {
    "career_employment":   "Career & Employment",
    "business":            "Business",
    "education":           "Education",
    "foreign_opportunity": "Foreign Opportunity",
    "financial":           "Financial",
    "job_change":          "Job Change",
    "health":              "Health",
    "relationship":        "Relationship",
    "property":            "Property",
    "legal":               "Legal",
    "marriage":            "Marriage",
    "travel":              "Travel",
    "pregnancy":           "Pregnancy",
    "competition":         "Competition",
}

# Primary house per category for KP analysis
_PRIMARY_HOUSE: Dict[str, int] = {
    "career_employment": 10, "business": 10, "education": 5,
    "foreign_opportunity": 12, "financial": 11, "job_change": 10,
    "health": 1, "relationship": 7, "property": 4, "legal": 6,
    "marriage": 7, "travel": 12, "pregnancy": 5, "competition": 6,
}

# Timing units per category (for "when will it happen" estimate)
_TIMING_UNIT: Dict[str, str] = {
    "career_employment": "weeks", "business": "months", "education": "months",
    "foreign_opportunity": "months", "financial": "weeks", "job_change": "weeks",
    "health": "days", "relationship": "months", "property": "months", "legal": "months",
    "marriage": "months", "travel": "weeks", "pregnancy": "months", "competition": "days",
}

# Aspect orbs for Vedic full-aspect check
_PLANET_ASPECTS: Dict[str, List[int]] = {
    "Sun":     [7], "Moon": [7], "Mercury": [7], "Venus": [7],
    "Jupiter": [7, 5, 9],        # 7th, 5th, 9th
    "Mars":    [7, 4, 8],        # 7th, 4th, 8th
    "Saturn":  [7, 3, 10],       # 7th, 3rd, 10th
    "Rahu":    [7, 5, 9],        "Ketu": [7, 5, 9],
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PrashnaChart:
    """Planetary positions at the moment of the question."""
    moment: datetime
    lat: float
    lon: float
    city: str = ""

    # Computed fields
    lagna_sign: str = ""
    lagna_degree: float = 0.0
    planets_d1: Dict[str, Dict] = field(default_factory=dict)
    # {planet: {sign, degree, abs_degree, retrograde, nakshatra, nakshatra_lord, sub_lord, house}}
    house_cusps: List[float] = field(default_factory=list)   # 12 cusp longitudes (abs degrees)
    house_cusp_signs: List[str] = field(default_factory=list)
    house_lords: Dict[str, str] = field(default_factory=dict)  # {"1": "Mars", ...}
    kp_sublords: Dict[str, str] = field(default_factory=dict)  # {"10": "Saturn", ...}  cusp sub-lords
    moon_void: bool = False
    moon_applying_to: Optional[str] = None


@dataclass
class PrashnaSignificator:
    """A planet's significator score for the query."""
    planet: str
    house_occupied: int = 0
    houses_ruled: List[int] = field(default_factory=list)
    houses_aspected: List[int] = field(default_factory=list)
    affirm_houses_touched: List[int] = field(default_factory=list)
    deny_houses_touched: List[int] = field(default_factory=list)
    score: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class PrashnaResult:
    """Complete Prashna analysis result."""
    # Inputs
    question: str = ""
    category: str = ""
    moment: str = ""
    city: str = ""

    # Core verdict
    verdict: str = "UNCERTAIN"          # YES / NO / UNCERTAIN / CONDITIONAL
    confidence: float = 0.5             # 0–1
    confidence_band: str = "MODERATE"  # STRONG / MODERATE / WEAK

    # Evidence
    kp_sublord_verdict: str = ""
    kp_sublord_planet: str = ""
    kp_sublord_signifies_affirm: bool = False
    moon_status: str = ""               # e.g. "Applying to Jupiter (benefic)"
    moon_void: bool = False

    # Timing
    timing_estimate: str = ""
    timing_unit: str = ""

    # Significators
    affirm_significators: List[str] = field(default_factory=list)
    deny_significators: List[str] = field(default_factory=list)

    # Chart snapshot
    lagna_sign: str = ""
    lagna_lord: str = ""
    moon_sign: str = ""
    moon_nakshatra: str = ""
    planets_summary: Dict[str, Dict] = field(default_factory=dict)
    house_lords: Dict[str, str] = field(default_factory=dict)

    # Detailed factors (for HTML rendering)
    factors: List[Dict[str, Any]] = field(default_factory=list)
    classical_rules_fired: List[str] = field(default_factory=list)
    remedy_suggestions: List[str] = field(default_factory=list)

    # Raw chart reference
    chart: Optional[PrashnaChart] = None


# ---------------------------------------------------------------------------
# KP Sub-lord table builder
# ---------------------------------------------------------------------------

def _build_sub_lords() -> List[Tuple[float, str, str, str]]:
    """
    Return list of (start_abs_degree, nakshatra, nakshatra_lord, sub_lord)
    for all 249 KP sub-divisions (27 naks × 9 subs).
    """
    nak_span = 800.0 / 60.0  # 13°20' in degrees
    result: List[Tuple[float, str, str, str]] = []
    abs_deg = 0.0
    for nak_idx in range(27):
        nak_name   = _NAKSHATRA_NAMES[nak_idx]
        nak_lord   = _NAKSHATRA_LORD_SEQ[nak_idx]
        nak_lord_pos = _VIMSHO_ORDER.index(nak_lord)
        for sub_k in range(9):
            sub_lord = _VIMSHO_ORDER[(nak_lord_pos + sub_k) % 9]
            sub_span = nak_span * _VIMSHO_YEARS[sub_lord] / _VIMSHO_TOTAL
            result.append((abs_deg, nak_name, nak_lord, sub_lord))
            abs_deg += sub_span
    return result


_KP_SUB_TABLE: List[Tuple[float, str, str, str]] = _build_sub_lords()


def _kp_sublord_for_degree(abs_deg: float) -> Tuple[str, str, str]:
    """Return (nakshatra, nakshatra_lord, sub_lord) for a given absolute degree."""
    abs_deg = abs_deg % 360
    for i in range(len(_KP_SUB_TABLE) - 1):
        start = _KP_SUB_TABLE[i][0]
        nxt   = _KP_SUB_TABLE[i + 1][0]
        if start <= abs_deg < nxt:
            return _KP_SUB_TABLE[i][1], _KP_SUB_TABLE[i][2], _KP_SUB_TABLE[i][3]
    # last entry
    return _KP_SUB_TABLE[-1][1], _KP_SUB_TABLE[-1][2], _KP_SUB_TABLE[-1][3]


# ---------------------------------------------------------------------------
# Ephemeris: compute planetary positions using ephem
# ---------------------------------------------------------------------------

_EPHEM_PLANET_MAP = {
    "Sun": "Sun", "Moon": "Moon", "Mars": "Mars", "Mercury": "Mercury",
    "Jupiter": "Jupiter", "Venus": "Venus", "Saturn": "Saturn",
}


def _ephem_lon(body, dt: datetime) -> float:
    """Return ecliptic longitude (degrees, tropical) for an ephem body at dt."""
    import ephem
    body.compute(dt.strftime("%Y/%m/%d %H:%M:%S"), epoch=ephem.J2000)
    return math.degrees(body.hlong) % 360


def _tropical_to_sidereal(tropical_lon: float, dt: datetime) -> float:
    """Apply Lahiri ayanamsa to convert tropical → sidereal longitude."""
    # Lahiri ayanamsa approximation (accurate to ~0.1° 1900-2100)
    year = dt.year + (dt.month - 1) / 12.0 + (dt.day - 1) / 365.25
    ayanamsa = 23.85 + (year - 1900) * 0.01397
    return (tropical_lon - ayanamsa) % 360


def _lon_to_sign_degree(sidereal_lon: float) -> Tuple[str, float]:
    sign_idx = int(sidereal_lon // 30)
    degree   = sidereal_lon % 30
    return _NUM_SIGN.get(sign_idx + 1, "Aries"), degree


def _compute_lagna(dt: datetime, lat: float, lon: float) -> Tuple[float, str, float]:
    """
    Compute sidereal lagna (ascendant) at given moment.
    Returns (abs_sidereal_lon, sign, degree_in_sign).
    """
    import ephem
    obs          = ephem.Observer()
    obs.lat      = str(lat)
    obs.lon      = str(lon)
    obs.date     = dt.strftime("%Y/%m/%d %H:%M:%S")
    obs.epoch    = ephem.J2000
    obs.pressure = 0   # no refraction
    # ephem.degrees gives the sidereal time-based ascendant via:
    sidereal_time = obs.sidereal_time()  # radians → degrees
    lst_deg = math.degrees(sidereal_time)
    # RAMC = lst_deg
    # Ascendant = atan(cos(RAMC) / (-(sin(RAMC)*cos(ε) + tan(φ)*sin(ε))))
    # where ε = obliquity, φ = latitude
    epsilon = math.radians(23.4397)  # J2000 obliquity
    phi     = math.radians(lat)
    ramc    = math.radians(lst_deg)
    y       = math.cos(ramc)
    x       = -(math.sin(ramc) * math.cos(epsilon) + math.tan(phi) * math.sin(epsilon))
    asc_tropical = math.degrees(math.atan2(y, x)) % 360
    # Quadrant correction
    if 90 < lst_deg <= 270:
        asc_tropical = (asc_tropical + 180) % 360
    asc_sid = _tropical_to_sidereal(asc_tropical, dt)
    sign, deg = _lon_to_sign_degree(asc_sid)
    return asc_sid, sign, deg


def _compute_house_cusps_equal(lagna_abs: float) -> List[float]:
    """Equal-house cusps (Vedic Rasi / Whole-sign approximation)."""
    return [(lagna_abs + i * 30) % 360 for i in range(12)]


def cast_prashna_chart(
    moment: datetime,
    lat: float,
    lon: float,
    city: str = "",
) -> PrashnaChart:
    """
    Cast a Prashna (Horary) chart for the given moment and location.

    Parameters
    ----------
    moment : datetime  — moment of the question (timezone-aware or naive UTC)
    lat    : float     — observer latitude (+ north)
    lon    : float     — observer longitude (+ east)
    city   : str       — city name (cosmetic only)

    Returns
    -------
    PrashnaChart with all planetary positions, KP sub-lords, and Moon status.
    """
    import ephem

    chart = PrashnaChart(moment=moment, lat=lat, lon=lon, city=city)

    # 1. Lagna
    lagna_abs, lagna_sign, lagna_deg = _compute_lagna(moment, lat, lon)
    chart.lagna_sign   = lagna_sign
    chart.lagna_degree = lagna_deg

    # 2. House cusps (equal / Rasi Chakra)
    cusps = _compute_house_cusps_equal(lagna_abs)
    chart.house_cusps = cusps
    chart.house_cusp_signs = [_lon_to_sign_degree(c)[0] for c in cusps]

    # House lords
    for i, cs in enumerate(chart.house_cusp_signs, start=1):
        chart.house_lords[str(i)] = _SIGN_LORD.get(cs, "")

    # 3. KP sub-lords of cusps
    for i, c in enumerate(cusps, start=1):
        _, _, sub = _kp_sublord_for_degree(c)
        chart.kp_sublords[str(i)] = sub

    # 4. Planets
    ephem_objects = {
        "Sun":     ephem.Sun(),
        "Moon":    ephem.Moon(),
        "Mars":    ephem.Mars(),
        "Mercury": ephem.Mercury(),
        "Jupiter": ephem.Jupiter(),
        "Venus":   ephem.Venus(),
        "Saturn":  ephem.Saturn(),
    }
    dt_str = moment.strftime("%Y/%m/%d %H:%M:%S")

    planet_lons: Dict[str, float] = {}
    for pname, pobj in ephem_objects.items():
        pobj.compute(dt_str, epoch=ephem.J2000)
        trop = math.degrees(pobj.hlong) % 360
        sid  = _tropical_to_sidereal(trop, moment)
        planet_lons[pname] = sid
        sign, deg = _lon_to_sign_degree(sid)
        nak_name, nak_lord, sub_lord = _kp_sublord_for_degree(sid)
        retro = False
        try:
            retro = bool(pobj.a_ra < 0)
        except Exception:
            pass

        # House number (whole-sign)
        sign_num   = _SIGN_NUM.get(sign, 1)
        lagna_num  = _SIGN_NUM.get(lagna_sign, 1)
        house_num  = ((sign_num - lagna_num) % 12) + 1

        chart.planets_d1[pname] = {
            "sign": sign, "degree": round(deg, 4),
            "abs_degree": round(sid, 4),
            "retrograde": retro,
            "nakshatra": nak_name, "nakshatra_lord": nak_lord,
            "sub_lord": sub_lord, "house": house_num,
        }

    # 5. Rahu / Ketu (mean nodes — approx)
    # Rahu moves retrograde ~19.3°/year
    j2000_days = (moment - datetime(2000, 1, 1, 12, 0, 0)).total_seconds() / 86400
    rahu_trop  = (125.044555 - 0.052954 * j2000_days) % 360
    rahu_sid   = _tropical_to_sidereal(rahu_trop, moment)
    ketu_sid   = (rahu_sid + 180) % 360

    for nodename, node_sid in [("Rahu", rahu_sid), ("Ketu", ketu_sid)]:
        sign, deg = _lon_to_sign_degree(node_sid)
        nak_name, nak_lord, sub_lord = _kp_sublord_for_degree(node_sid)
        sign_num  = _SIGN_NUM.get(sign, 1)
        lagna_num = _SIGN_NUM.get(lagna_sign, 1)
        house_num = ((sign_num - lagna_num) % 12) + 1
        chart.planets_d1[nodename] = {
            "sign": sign, "degree": round(deg, 4),
            "abs_degree": round(node_sid, 4),
            "retrograde": True,
            "nakshatra": nak_name, "nakshatra_lord": nak_lord,
            "sub_lord": sub_lord, "house": house_num,
        }
        planet_lons[nodename] = node_sid

    # 6. Moon application / void-of-course
    moon_abs  = planet_lons.get("Moon", 0)
    chart.moon_void, chart.moon_applying_to = _check_moon_status(moon_abs, planet_lons, moment)

    return chart


def _check_moon_status(
    moon_abs: float,
    planet_lons: Dict[str, float],
    dt: datetime,
) -> Tuple[bool, Optional[str]]:
    """
    Return (void_of_course, planet_moon_applies_to).
    Moon is void-of-course if it makes no exact Vedic conjunction within its
    current sign (next 0–13.33°).
    """
    moon_sign_end = (math.floor(moon_abs / 30) + 1) * 30  # degrees to end of sign
    remaining_deg = moon_sign_end - moon_abs
    if remaining_deg < 0:
        remaining_deg += 360

    # Planets ahead of Moon within current sign
    candidates: List[Tuple[float, str]] = []
    for pname, plon in planet_lons.items():
        if pname == "Moon":
            continue
        diff = (plon - moon_abs) % 360
        if diff < remaining_deg:
            candidates.append((diff, pname))

    candidates.sort()
    if not candidates:
        return True, None   # Void of course
    return False, candidates[0][1]


# ---------------------------------------------------------------------------
# Significator analysis
# ---------------------------------------------------------------------------

def _planet_significators(chart: PrashnaChart) -> Dict[str, PrashnaSignificator]:
    """
    Build a significator map for every planet.
    A planet signifies a house if it:
      - Occupies it (strongest, weight 3)
      - Rules it via house lord (weight 2)
      - Aspects it with Vedic full aspect (weight 1)
    """
    sigs: Dict[str, PrashnaSignificator] = {}
    lagna_num = _SIGN_NUM.get(chart.lagna_sign, 1)

    for pname, pdata in chart.planets_d1.items():
        sig = PrashnaSignificator(planet=pname)
        sig.house_occupied = pdata.get("house", 0)

        # Houses ruled
        for h_str, lord in chart.house_lords.items():
            if lord == pname:
                sig.houses_ruled.append(int(h_str))

        # Houses aspected (Vedic full aspect)
        p_house = sig.house_occupied
        for asp_offset in _PLANET_ASPECTS.get(pname, [7]):
            asp_house = ((p_house - 1 + asp_offset) % 12) + 1
            if asp_house not in sig.houses_aspected:
                sig.houses_aspected.append(asp_house)

        sigs[pname] = sig
    return sigs


def _score_significators(
    sigs: Dict[str, PrashnaSignificator],
    category: str,
) -> Dict[str, PrashnaSignificator]:
    """Assign scores and label affirm vs deny."""
    affirm  = set(_AFFIRM_HOUSES.get(category, []))
    deny    = set(_DENY_HOUSES.get(category, []))

    for pname, sig in sigs.items():
        score = 0.0
        all_houses_touched = {sig.house_occupied} | set(sig.houses_ruled) | set(sig.houses_aspected)

        for h in all_houses_touched:
            if h == sig.house_occupied and h in affirm:
                score += 3
                sig.affirm_houses_touched.append(h)
            elif h in sig.houses_ruled and h in affirm:
                score += 2
                if h not in sig.affirm_houses_touched:
                    sig.affirm_houses_touched.append(h)
            elif h in sig.houses_aspected and h in affirm:
                score += 1
                if h not in sig.affirm_houses_touched:
                    sig.affirm_houses_touched.append(h)

            if h in deny:
                score -= 1.5
                if h not in sig.deny_houses_touched:
                    sig.deny_houses_touched.append(h)

        sig.score = round(score, 2)
    return sigs


# ---------------------------------------------------------------------------
# Dignity helper
# ---------------------------------------------------------------------------

def _planet_dignity(pname: str, sign: str) -> str:
    if _EXALT_SIGN.get(pname) == sign:   return "Exalted"
    if _DEBIL_SIGN.get(pname)  == sign:  return "Debilitated"
    if sign in _OWN_SIGNS.get(pname, []): return "Own"
    return ""


# ---------------------------------------------------------------------------
# Classical rule checkers
# ---------------------------------------------------------------------------

def _classical_rules(
    chart: PrashnaChart,
    sigs: Dict[str, PrashnaSignificator],
    category: str,
) -> Tuple[List[str], List[str]]:
    """
    Apply classical Prashna rules.
    Returns (positive_rules_fired, negative_rules_fired).
    """
    pos, neg = [], []
    cat = _CATEGORY_HOUSES.get(category, {})
    primary_h = _PRIMARY_HOUSE.get(category, 10)
    pdata = chart.planets_d1

    # Rule 1: Lagna lord in primary house or primary house lord in lagna
    lagna_lord  = chart.house_lords.get("1", "")
    primary_lord = chart.house_lords.get(str(primary_h), "")
    if lagna_lord and pdata.get(lagna_lord, {}).get("house") == primary_h:
        pos.append(f"Lagna lord {lagna_lord} occupies H{primary_h} (question house) — strong YES indicator")
    if primary_lord and pdata.get(primary_lord, {}).get("house") == 1:
        pos.append(f"H{primary_h} lord {primary_lord} occupies Lagna — very auspicious for {_CATEGORY_LABELS.get(category,'query')}")

    # Rule 2: Moon applying to a planet that signifies primary house
    if not chart.moon_void and chart.moon_applying_to:
        applying_sig = sigs.get(chart.moon_applying_to)
        if applying_sig and applying_sig.affirm_houses_touched:
            pos.append(f"Moon applying to {chart.moon_applying_to} (significator of H{applying_sig.affirm_houses_touched[0]}) — timing confirms YES")
        if applying_sig and applying_sig.deny_houses_touched:
            neg.append(f"Moon applying to {chart.moon_applying_to} (significator of denial H{applying_sig.deny_houses_touched[0]}) — unfavorable")
    elif chart.moon_void:
        neg.append("Moon is Void-of-Course — matter will not come to fruition as intended")

    # Rule 3: Benefics in primary and support houses
    affirm_hs = set(_AFFIRM_HOUSES.get(category, []))
    for pname in _NATURAL_BENEFICS:
        pd = pdata.get(pname, {})
        if pd.get("house") in affirm_hs:
            dig = _planet_dignity(pname, pd.get("sign", ""))
            dig_note = f" ({dig})" if dig else ""
            pos.append(f"{pname}{dig_note} in H{pd['house']} — benefic in question house supports YES")

    # Rule 4: Malefics in primary house without benefic aspect
    deny_hs = set(_DENY_HOUSES.get(category, []))
    for pname in _NATURAL_MALEFICS:
        pd = pdata.get(pname, {})
        h  = pd.get("house")
        if h and h in affirm_hs:
            dig = _planet_dignity(pname, pd.get("sign", ""))
            if dig == "Debilitated":
                neg.append(f"{pname} debilitated in H{h} — weakens the query house")
            elif pname in ("Rahu", "Ketu"):
                neg.append(f"{pname} in H{h} — shadowy node can delay or distort outcome")

    # Rule 5: Retrograde significators
    for pname, sig in sigs.items():
        pd = pdata.get(pname, {})
        if pd.get("retrograde") and sig.affirm_houses_touched:
            neg.append(f"{pname} is retrograde — matter may be delayed, reversed, or reconsidered")
            break

    # Rule 6: 7th lord in H10 / H10 lord in H7 (mutual exchange relevant for career/business)
    if category in ("career_employment", "business"):
        h7_lord  = chart.house_lords.get("7", "")
        h10_lord = chart.house_lords.get("10", "")
        if h7_lord and pdata.get(h7_lord, {}).get("house") == 10:
            pos.append(f"H7 lord {h7_lord} in H10 — partnerships fuel career growth")
        if h10_lord and pdata.get(h10_lord, {}).get("house") == 7:
            pos.append(f"H10 lord {h10_lord} in H7 — professional alliance brings opportunity")

    # Rule 7: H12 lord or H12 tenants — indicates expenditure / loss for financial query
    if category == "financial":
        h12_lord = chart.house_lords.get("12", "")
        if h12_lord and pdata.get(h12_lord, {}).get("house") in (2, 11):
            neg.append(f"H12 lord {h12_lord} in wealth house — gains may be offset by expenses")

    # Rule 8: H9 activated for foreign / education
    if category in ("foreign_opportunity", "education"):
        h9_lord = chart.house_lords.get("9", "")
        if h9_lord and pdata.get(h9_lord, {}).get("house") in (1, 9, 12):
            pos.append(f"H9 lord {h9_lord} well-placed — auspicious for {_CATEGORY_LABELS.get(category,'')}")

    # Rule 9: H3 (change, short journeys) activated for job change
    if category == "job_change":
        h3_lord = chart.house_lords.get("3", "")
        if h3_lord and pdata.get(h3_lord, {}).get("house") in (10, 6, 11):
            pos.append(f"H3 lord {h3_lord} links with career houses — change is imminent")

    return pos, neg


# ---------------------------------------------------------------------------
# Timing estimate
# ---------------------------------------------------------------------------

def _estimate_timing(
    chart: PrashnaChart,
    sigs: Dict[str, PrashnaSignificator],
    category: str,
    verdict: str,
) -> str:
    """
    Classical KP timing: degrees remaining for Moon to perfect the applying aspect.
    Rough rule: 1 degree ≈ 1 unit of _TIMING_UNIT[category].
    """
    if verdict == "NO":
        return "Not indicated within near term"

    unit = _TIMING_UNIT.get(category, "months")
    moon_data = chart.planets_d1.get("Moon", {})
    moon_abs  = moon_data.get("abs_degree", 0)

    if chart.moon_applying_to:
        applying_planet = chart.planets_d1.get(chart.moon_applying_to, {})
        target_abs      = applying_planet.get("abs_degree", moon_abs)
        diff = (target_abs - moon_abs) % 360
        if diff > 180:
            diff = 360 - diff
        diff = round(diff, 1)
        return f"~{diff} {unit} (Moon is {diff}° from {chart.moon_applying_to})"

    # Fallback: sub-lord change timing
    primary_h   = _PRIMARY_HOUSE.get(category, 10)
    cusp_abs    = chart.house_cusps[primary_h - 1] if len(chart.house_cusps) >= primary_h else 0
    diff_to_sub = 0.5  # default half-degree within sub
    return f"~{diff_to_sub}–{round(diff_to_sub * 3, 1)} {unit} (based on H{primary_h} sub-lord)"


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def analyze_prashna(
    chart: PrashnaChart,
    category: str,
    question: str = "",
) -> PrashnaResult:
    """
    Analyze a cast Prashna chart for the given category.

    Parameters
    ----------
    chart    : PrashnaChart from cast_prashna_chart()
    category : one of the _CATEGORY_HOUSES keys
    question : original question text (stored in result)

    Returns
    -------
    PrashnaResult with verdict, confidence, evidence, and HTML-ready factors.
    """
    category = category.lower().replace(" ", "_").replace("&", "and")
    # Normalize common aliases
    _aliases = {
        "career_and_employment": "career_employment",
        "career": "career_employment",
        "foreign": "foreign_opportunity",
        "finance": "financial",
        "job": "job_change",
    }
    category = _aliases.get(category, category)
    if category not in _CATEGORY_HOUSES:
        category = "career_employment"

    result = PrashnaResult(
        question=question,
        category=category,
        moment=chart.moment.strftime("%d-%m-%Y %H:%M"),
        city=chart.city,
        lagna_sign=chart.lagna_sign,
        lagna_lord=chart.house_lords.get("1", ""),
        moon_sign=chart.planets_d1.get("Moon", {}).get("sign", ""),
        moon_nakshatra=chart.planets_d1.get("Moon", {}).get("nakshatra", ""),
        house_lords=chart.house_lords,
        chart=chart,
        timing_unit=_TIMING_UNIT.get(category, "months"),
    )

    # 1. Significators
    sigs = _planet_significators(chart)
    sigs = _score_significators(sigs, category)

    affirm_sigs = sorted([s for s in sigs.values() if s.score > 0],
                         key=lambda x: -x.score)
    deny_sigs   = sorted([s for s in sigs.values() if s.score < 0],
                         key=lambda x: x.score)

    result.affirm_significators = [s.planet for s in affirm_sigs[:5]]
    result.deny_significators   = [s.planet for s in deny_sigs[:3]]

    # 2. KP sub-lord of primary house cusp
    primary_h      = _PRIMARY_HOUSE.get(category, 10)
    kp_sub         = chart.kp_sublords.get(str(primary_h), "")
    result.kp_sublord_planet = kp_sub
    kp_sig         = sigs.get(kp_sub)
    kp_affirms     = bool(kp_sig and kp_sig.affirm_houses_touched)
    kp_denies      = bool(kp_sig and kp_sig.deny_houses_touched)
    result.kp_sublord_signifies_affirm = kp_affirms

    if kp_affirms and not kp_denies:
        result.kp_sublord_verdict = (
            f"H{primary_h} cusp sub-lord {kp_sub} signifies "
            f"H{kp_sig.affirm_houses_touched} — KP confirms YES"
        )
    elif kp_denies and not kp_affirms:
        result.kp_sublord_verdict = (
            f"H{primary_h} cusp sub-lord {kp_sub} signifies "
            f"denial H{kp_sig.deny_houses_touched} — KP confirms NO"
        )
    else:
        result.kp_sublord_verdict = (
            f"H{primary_h} cusp sub-lord {kp_sub} gives mixed signals — outcome uncertain"
        )

    # 3. Classical rules
    pos_rules, neg_rules = _classical_rules(chart, sigs, category)
    result.classical_rules_fired = pos_rules + neg_rules

    # 4. Moon status
    if chart.moon_void:
        result.moon_status = "Void-of-Course (no applying aspect within sign)"
        result.moon_void   = True
    elif chart.moon_applying_to:
        applying_planet = chart.moon_applying_to
        nat_type = "benefic" if applying_planet in _NATURAL_BENEFICS else "malefic"
        result.moon_status = f"Applying to {applying_planet} ({nat_type})"
    else:
        result.moon_status = "Separating from all planets"

    # 5. Verdict engine
    affirm_score = sum(s.score for s in affirm_sigs)
    deny_score   = abs(sum(s.score for s in deny_sigs))

    kp_weight = 2.5
    kp_affirm_pts = kp_weight if kp_affirms else 0
    kp_deny_pts   = kp_weight if kp_denies  else 0

    moon_affirm_pts = 0
    moon_deny_pts   = 0
    if chart.moon_void:
        moon_deny_pts = 2
    elif chart.moon_applying_to in _NATURAL_BENEFICS:
        moon_affirm_pts = 1.5
    elif chart.moon_applying_to in _NATURAL_MALEFICS:
        moon_deny_pts   = 1

    total_affirm = affirm_score + kp_affirm_pts + moon_affirm_pts + len(pos_rules) * 0.5
    total_deny   = deny_score   + kp_deny_pts   + moon_deny_pts   + len(neg_rules) * 0.5
    total        = total_affirm + total_deny
    ratio        = (total_affirm / total) if total > 0 else 0.5

    if ratio >= 0.68:
        result.verdict    = "YES"
        result.confidence = round(min(ratio, 0.95), 2)
    elif ratio <= 0.32:
        result.verdict    = "NO"
        result.confidence = round(min(1 - ratio, 0.95), 2)
    elif 0.45 <= ratio <= 0.55 and chart.moon_void:
        result.verdict    = "UNCERTAIN"
        result.confidence = 0.5
    elif ratio > 0.55:
        result.verdict    = "CONDITIONAL"
        result.confidence = round(ratio, 2)
    else:
        result.verdict    = "CONDITIONAL"
        result.confidence = round(1 - ratio, 2)

    conf = result.confidence
    result.confidence_band = ("STRONG" if conf >= 0.75 else
                              "MODERATE" if conf >= 0.55 else "WEAK")

    # 6. Timing
    result.timing_estimate = _estimate_timing(chart, sigs, category, result.verdict)

    # 7. Planet summary (for HTML)
    for pname, pdata in chart.planets_d1.items():
        dig = _planet_dignity(pname, pdata.get("sign", ""))
        result.planets_summary[pname] = {
            "sign": pdata.get("sign"), "degree": pdata.get("degree"),
            "house": pdata.get("house"), "nakshatra": pdata.get("nakshatra"),
            "sub_lord": pdata.get("sub_lord"), "retrograde": pdata.get("retrograde"),
            "dignity": dig,
        }

    # 8. Factors for HTML cards
    result.factors = _build_factors(chart, sigs, result, category, kp_affirms, kp_denies)

    # 9. Remedies
    result.remedy_suggestions = _suggest_remedies(result, category)

    return result


def _build_factors(
    chart: PrashnaChart,
    sigs: Dict[str, PrashnaSignificator],
    result: PrashnaResult,
    category: str,
    kp_affirms: bool,
    kp_denies: bool,
) -> List[Dict[str, Any]]:
    """Build factor cards list for HTML rendering."""
    factors = []
    primary_h = _PRIMARY_HOUSE.get(category, 10)

    # KP sub-lord card
    kp_planet = result.kp_sublord_planet
    kp_sig_obj = sigs.get(kp_planet)
    factors.append({
        "name": f"KP Sub-Lord of H{primary_h}",
        "value": kp_planet,
        "detail": result.kp_sublord_verdict,
        "polarity": "positive" if kp_affirms and not kp_denies else
                    ("negative" if kp_denies and not kp_affirms else "neutral"),
        "weight": "HIGH",
    })

    # Moon card
    factors.append({
        "name": "Moon Status",
        "value": result.moon_status,
        "detail": (
            "Void Moon — matter may not materialise as expected"
            if chart.moon_void else
            f"Moon applying to {chart.moon_applying_to} — timing indicator"
        ),
        "polarity": "negative" if chart.moon_void else
                    ("positive" if chart.moon_applying_to in _NATURAL_BENEFICS else "neutral"),
        "weight": "HIGH",
    })

    # Lagna lord card
    lagna_lord = chart.house_lords.get("1", "")
    ll_data    = chart.planets_d1.get(lagna_lord, {})
    factors.append({
        "name": "Lagna Lord",
        "value": f"{lagna_lord} in H{ll_data.get('house', '?')} ({ll_data.get('sign', '?')})",
        "detail": (f"Dignity: {_planet_dignity(lagna_lord, ll_data.get('sign',''))}"
                   if _planet_dignity(lagna_lord, ll_data.get("sign", "")) else "No special dignity"),
        "polarity": ("positive" if _planet_dignity(lagna_lord, ll_data.get("sign","")) in ("Exalted","Own")
                     else ("negative" if _planet_dignity(lagna_lord, ll_data.get("sign","")) == "Debilitated"
                           else "neutral")),
        "weight": "MEDIUM",
    })

    # Primary house lord card
    ph_lord   = chart.house_lords.get(str(primary_h), "")
    phl_data  = chart.planets_d1.get(ph_lord, {})
    factors.append({
        "name": f"H{primary_h} Lord (Query House)",
        "value": f"{ph_lord} in H{phl_data.get('house', '?')} ({phl_data.get('sign', '?')})",
        "detail": (f"Dignity: {_planet_dignity(ph_lord, phl_data.get('sign',''))}"
                   if _planet_dignity(ph_lord, phl_data.get("sign", "")) else
                   f"Sub-lord: {phl_data.get('sub_lord','?')}"),
        "polarity": ("positive" if _planet_dignity(ph_lord, phl_data.get("sign","")) in ("Exalted","Own")
                     else ("negative" if _planet_dignity(ph_lord, phl_data.get("sign","")) == "Debilitated"
                           else "neutral")),
        "weight": "HIGH",
    })

    # Top significators
    top_affirm = result.affirm_significators[:3]
    top_deny   = result.deny_significators[:2]
    if top_affirm:
        factors.append({
            "name": "Affirming Planets",
            "value": ", ".join(top_affirm),
            "detail": (f"{top_affirm[0]} is strongest affirming significator "
                       f"(score {sigs[top_affirm[0]].score:.1f})"),
            "polarity": "positive",
            "weight": "MEDIUM",
        })
    if top_deny:
        factors.append({
            "name": "Denying Planets",
            "value": ", ".join(top_deny),
            "detail": (f"{top_deny[0]} links to denial houses "
                       f"(score {sigs[top_deny[0]].score:.1f})"),
            "polarity": "negative",
            "weight": "MEDIUM",
        })

    return factors


def _suggest_remedies(result: PrashnaResult, category: str) -> List[str]:
    """Return contextual remedy suggestions based on verdict and category."""
    if result.verdict == "YES":
        return ["Proceed with confidence; time the event when Moon transits a benefic nakshatra",
                "Begin the effort on a Thursday (Jupiter's day) or Friday (Venus's day) for best support"]

    remedies = []
    if result.moon_void:
        remedies.append("Delay action until Moon moves to the next sign and applies to a benefic")

    category_remedies = {
        "career_employment": [
            "Strengthen Mercury and Jupiter: recite Vishnu Sahasranama on Thursdays",
            "Wear a Yellow Sapphire (consult astrologer) or use yellow in attire on Thursdays",
        ],
        "business": [
            "Worship Lakshmi on Fridays; light a ghee lamp facing east",
            "Initiate partnership discussions when Moon transits Rohini or Pushya nakshatra",
        ],
        "education": [
            "Worship Saraswati; recite Gayatri Mantra 108 times at sunrise",
            "Begin studies when Moon is in Gemini, Virgo, or Sagittarius",
        ],
        "foreign_opportunity": [
            "Worship Lord Vishnu; recite Om Namo Narayanaya for travel blessings",
            "Travel when Rahu is favorably placed or Moon transits Ardra / Swati",
        ],
        "financial": [
            "Worship Kuber on Thursdays; keep a yellow cloth wallet",
            "Invest / act when Jupiter transits H2 or H11 from natal Moon",
        ],
        "job_change": [
            "Strengthen Mars and Jupiter; recite Hanuman Chalisa on Tuesdays",
            "Make the change when Moon transits Aries, Leo, or Sagittarius",
        ],
    }
    remedies.extend(category_remedies.get(category, [
        "Strengthen the Lagna lord planet through its associated mantra",
        "Act when Moon is waxing and transiting favorable nakshatras",
    ]))
    return remedies[:3]


# ---------------------------------------------------------------------------
# HTML Report Generator
# ---------------------------------------------------------------------------

_VERDICT_COLORS = {
    "YES": "#3fb950", "NO": "#f85149", "UNCERTAIN": "#e3b341", "CONDITIONAL": "#79c0ff",
}
_BAND_COLORS = {
    "STRONG": "#3fb950", "MODERATE": "#e3b341", "WEAK": "#f85149",
}
_POLARITY_COLORS = {
    "positive": "rgba(63,185,80,.15)", "negative": "rgba(248,81,73,.12)", "neutral": "rgba(255,255,255,.06)",
}
_POLARITY_BORDERS = {
    "positive": "#3fb950", "negative": "#f85149", "neutral": "#555",
}


def generate_prashna_html(result: PrashnaResult) -> str:
    """
    Generate a self-contained dark-theme HTML string for the Prashna result.
    Ready to write directly to an .html file or serve via Flask/FastAPI.
    """
    import html as hl
    def _h(s):
        return hl.escape(str(s or ""))

    verdict_col  = _VERDICT_COLORS.get(result.verdict, "#aaa")
    band_col     = _BAND_COLORS.get(result.confidence_band, "#aaa")
    conf_pct     = int(result.confidence * 100)
    cat_label    = _CATEGORY_LABELS.get(result.category, result.category.replace("_", " ").title())

    # Planet table rows
    planet_rows = []
    for pname, pd in result.planets_summary.items():
        retro = " ℞" if pd.get("retrograde") else ""
        dig   = pd.get("dignity", "")
        dig_style = ("color:#3fb950" if dig in ("Exalted", "Own") else
                     "color:#f85149" if dig == "Debilitated" else "")
        planet_rows.append(
            f"<tr>"
            f"<td><b>{_h(pname)}{retro}</b></td>"
            f"<td>{_h(pd.get('sign',''))}</td>"
            f"<td style='text-align:right'>{pd.get('degree',0):.2f}°</td>"
            f"<td>H{pd.get('house','')}</td>"
            f"<td style='font-size:11px'>{_h(pd.get('nakshatra',''))}</td>"
            f"<td style='font-size:11px'>{_h(pd.get('sub_lord',''))}</td>"
            f"<td style='{dig_style};font-size:11px'>{_h(dig)}</td>"
            f"</tr>"
        )

    # Factor cards
    factor_cards_html = ""
    for fac in result.factors:
        pol    = fac.get("polarity", "neutral")
        wt     = fac.get("weight", "MEDIUM")
        bg     = _POLARITY_COLORS[pol]
        border = _POLARITY_BORDERS[pol]
        icon   = "✅" if pol == "positive" else ("❌" if pol == "negative" else "⚠️")
        wt_badge = (f"<span style='font-size:9px;background:rgba(255,255,255,.1);"
                    f"padding:1px 5px;border-radius:3px;vertical-align:middle'>{wt}</span>")
        factor_cards_html += (
            f"<div style='background:{bg};border:1px solid {border};border-radius:8px;"
            f"padding:12px 15px;margin-bottom:10px'>"
            f"<div style='font-size:12px;color:#8b949e;font-weight:600;margin-bottom:4px'>"
            f"{icon} {_h(fac.get('name',''))} {wt_badge}</div>"
            f"<div style='font-size:14px;font-weight:700;color:#e6edf3;margin-bottom:3px'>"
            f"{_h(fac.get('value',''))}</div>"
            f"<div style='font-size:12px;color:#8b949e'>{_h(fac.get('detail',''))}</div>"
            f"</div>"
        )

    # Classical rules
    rules_html = ""
    for r in result.classical_rules_fired:
        col = "#3fb950" if any(w in r.lower() for w in ["yes", "auspicious", "confirms yes", "growth", "confirms"]) else "#e3b341"
        rules_html += f"<li style='margin-bottom:6px;color:{col}'>{_h(r)}</li>"
    if not rules_html:
        rules_html = "<li style='color:#8b949e'>No classical rules fired</li>"

    # Remedies
    remedy_html = ""
    for rem in result.remedy_suggestions:
        remedy_html += f"<li style='margin-bottom:6px'>{_h(rem)}</li>"

    # House lords table
    house_lords_rows = ""
    for i in range(1, 13):
        lord = result.house_lords.get(str(i), "—")
        house_lords_rows += f"<tr><td>H{i}</td><td>{_h(lord)}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Prashna (Horary) — {_h(cat_label)}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0d1117; color: #e6edf3; min-height: 100vh;
    padding: 24px;
  }}
  h1 {{ font-size: 22px; font-weight: 700; color: #e6edf3; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; font-weight: 600; color: #8b949e; text-transform: uppercase;
        letter-spacing: .05em; margin: 24px 0 12px; border-bottom: 1px solid #21262d;
        padding-bottom: 6px; }}
  h3 {{ font-size: 14px; font-weight: 600; color: #c9d1d9; margin-bottom: 8px; }}
  .subtitle {{ color: #8b949e; font-size: 13px; margin-bottom: 24px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  @media (max-width: 800px) {{ .grid-2, .grid-3 {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: #161b22; border: 1px solid #21262d;
    border-radius: 10px; padding: 18px;
  }}
  .verdict-box {{
    background: linear-gradient(135deg, #161b22, #0d1117);
    border: 2px solid {verdict_col};
    border-radius: 12px; padding: 24px; text-align: center;
  }}
  .verdict-word {{ font-size: 48px; font-weight: 900; color: {verdict_col}; line-height: 1; }}
  .confidence-bar-bg {{
    background: #21262d; border-radius: 4px; height: 8px; margin: 12px 0 6px;
  }}
  .confidence-bar {{
    background: {band_col}; border-radius: 4px;
    height: 8px; width: {conf_pct}%;
    transition: width .6s ease;
  }}
  .meta-chip {{
    display: inline-block; background: rgba(255,255,255,.07);
    border: 1px solid #30363d; border-radius: 4px;
    padding: 3px 10px; font-size: 12px; color: #8b949e; margin: 3px 2px;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; font-size: 11px; font-weight: 600; color: #8b949e;
        border-bottom: 1px solid #21262d; padding: 4px 8px; text-transform: uppercase; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid rgba(255,255,255,.04); }}
  tr:hover td {{ background: rgba(255,255,255,.02); }}
  ul {{ list-style: disc; padding-left: 20px; }}
  .tag {{
    display: inline-block; background: rgba(121,192,255,.1); border: 1px solid rgba(121,192,255,.3);
    color: #79c0ff; border-radius: 3px; padding: 1px 6px; font-size: 11px; margin: 2px;
  }}
  .kp-box {{
    background: rgba(63,185,80,.08); border: 1px solid rgba(63,185,80,.4);
    border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;
  }}
  footer {{ text-align: center; color: #30363d; font-size: 11px; margin-top: 40px; }}
</style>
</head>
<body>
<h1>Prashna (Horary) — {_h(cat_label)}</h1>
<div class="subtitle">
  <span class="meta-chip">🕐 {_h(result.moment)}</span>
  <span class="meta-chip">📍 {_h(result.city) or 'Location provided'}</span>
  <span class="meta-chip">⬆ Lagna: {_h(result.lagna_sign)}</span>
  <span class="meta-chip">🌙 Moon: {_h(result.moon_sign)} · {_h(result.moon_nakshatra)}</span>
</div>

{"<div style='background:rgba(255,200,0,.10);border:1px solid rgba(255,200,0,.4);border-radius:8px;padding:12px 16px;margin-bottom:16px;'><b style='color:#e3b341'>Question: </b>" + _h(result.question) + "</div>" if result.question else ""}

<div class="grid-2" style="margin-bottom:20px">

  <div class="verdict-box">
    <div style="font-size:12px;color:#8b949e;margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em">Prashna Verdict</div>
    <div class="verdict-word">{_h(result.verdict)}</div>
    <div class="confidence-bar-bg"><div class="confidence-bar"></div></div>
    <div style="font-size:13px;color:{band_col}">{_h(result.confidence_band)} confidence &nbsp;·&nbsp; {conf_pct}%</div>
    <div style="font-size:13px;color:#8b949e;margin-top:12px">
      🕐 Timing: <b style="color:#e6edf3">{_h(result.timing_estimate)}</b>
    </div>
  </div>

  <div class="card">
    <h3>KP Sub-Lord Analysis</h3>
    <div class="kp-box" style="{'background:rgba(248,81,73,.08);border-color:rgba(248,81,73,.4)' if not result.kp_sublord_signifies_affirm else ''}">
      <div style="font-size:13px;color:#e6edf3">{_h(result.kp_sublord_verdict)}</div>
    </div>
    <h3>Moon Status</h3>
    <div style="font-size:13px;color:{'#f85149' if result.moon_void else '#3fb950'};margin-bottom:10px">
      {_h(result.moon_status)}
    </div>
    <h3>Significators</h3>
    <div style="margin-bottom:6px">
      <span style="font-size:11px;color:#3fb950;font-weight:600">AFFIRM: </span>
      {"".join(f"<span class='tag'>{_h(p)}</span>" for p in result.affirm_significators) or "<span style='color:#555'>None</span>"}
    </div>
    <div>
      <span style="font-size:11px;color:#f85149;font-weight:600">DENY: </span>
      {"".join(f"<span class='tag' style='background:rgba(248,81,73,.1);border-color:rgba(248,81,73,.3);color:#f85149'>{_h(p)}</span>" for p in result.deny_significators) or "<span style='color:#555'>None</span>"}
    </div>
  </div>

</div>

<h2>Key Factors</h2>
<div class="grid-2">
  <div>{factor_cards_html}</div>
  <div>
    <h3 style="margin-bottom:12px">Classical Rules</h3>
    <ul style="font-size:13px;line-height:1.8">{rules_html}</ul>
    <h3 style="margin-top:20px;margin-bottom:12px">Remedies</h3>
    <ul style="font-size:13px;line-height:1.8;color:#8b949e">{remedy_html}</ul>
  </div>
</div>

<h2>Prashna Chart — Planetary Positions</h2>
<div class="card">
  <table>
    <thead><tr>
      <th>Planet</th><th>Sign</th><th>Degree</th><th>House</th>
      <th>Nakshatra</th><th>KP Sub-Lord</th><th>Dignity</th>
    </tr></thead>
    <tbody>{"".join(planet_rows)}</tbody>
  </table>
</div>

<div class="grid-2" style="margin-top:16px">
  <div class="card">
    <h3 style="margin-bottom:10px">House Lords</h3>
    <table>
      <thead><tr><th>House</th><th>Lord</th></tr></thead>
      <tbody>{house_lords_rows}</tbody>
    </table>
  </div>
  <div class="card">
    <h3 style="margin-bottom:10px">KP Cusp Sub-Lords</h3>
    <table>
      <thead><tr><th>Cusp</th><th>Sub-Lord</th></tr></thead>
      <tbody>{"".join(f"<tr><td>H{i}</td><td>{_h(chart.kp_sublords.get(str(i),''))}</td></tr>" for i in range(1, 13) if (chart := result.chart) is not None)}</tbody>
    </table>
  </div>
</div>

<footer>JyotishAI Prashna Engine v1.0 &nbsp;·&nbsp; {_h(result.moment)}</footer>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Convenience: cast + analyze + write HTML in one call
# ---------------------------------------------------------------------------

def run_prashna(
    moment: datetime,
    lat: float,
    lon: float,
    city: str,
    category: str,
    question: str = "",
    output_dir: str = ".",
) -> Tuple[PrashnaResult, str]:
    """
    Full pipeline: cast chart → analyze → write HTML.

    Returns (PrashnaResult, html_file_path).
    """
    chart  = cast_prashna_chart(moment, lat, lon, city)
    result = analyze_prashna(chart, category, question)
    html   = generate_prashna_html(result)

    os.makedirs(output_dir, exist_ok=True)
    safe_cat  = category.replace(" ", "_").lower()
    fname     = f"prashna_{safe_cat}_{moment.strftime('%Y%m%d_%H%M')}.html"
    fpath     = os.path.join(output_dir, fname)
    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write(html)
    logger.info("[Prashna] HTML written: %s", fpath)
    return result, fpath


# ---------------------------------------------------------------------------
# Geocode helper: city name → (lat, lon)
# ---------------------------------------------------------------------------

_CITY_COORDS: Dict[str, Tuple[float, float]] = {
    "mumbai": (19.0760, 72.8777), "delhi": (28.6139, 77.2090),
    "bangalore": (12.9716, 77.5946), "bengaluru": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707), "kolkata": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867), "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714), "jaipur": (26.9124, 75.7873),
    "new york": (40.7128, -74.0060), "london": (51.5074, -0.1278),
    "dubai": (25.2048, 55.2708), "singapore": (1.3521, 103.8198),
    "sydney": (-33.8688, 151.2093), "toronto": (43.6510, -79.3470),
}


def city_to_coords(city: str) -> Tuple[float, float]:
    """
    Resolve a city name to (lat, lon). Falls back to Delhi if unknown.
    Extend _CITY_COORDS or hook in a geocoding API for full coverage.
    """
    key = city.strip().lower()
    if key in _CITY_COORDS:
        return _CITY_COORDS[key]
    # Try partial match
    for k, v in _CITY_COORDS.items():
        if k in key or key in k:
            return v
    logger.warning("[Prashna] Unknown city '%s', defaulting to Delhi coords", city)
    return 28.6139, 77.2090


# ---------------------------------------------------------------------------
# API-ready dict serializer
# ---------------------------------------------------------------------------

def prashna_result_to_dict(result: PrashnaResult) -> Dict[str, Any]:
    """Serialize PrashnaResult to a JSON-safe dict for API responses."""
    return {
        "question":             result.question,
        "category":             result.category,
        "category_label":       _CATEGORY_LABELS.get(result.category, result.category),
        "moment":               result.moment,
        "city":                 result.city,
        "verdict":              result.verdict,
        "confidence":           result.confidence,
        "confidence_band":      result.confidence_band,
        "kp_sublord_planet":    result.kp_sublord_planet,
        "kp_sublord_verdict":   result.kp_sublord_verdict,
        "kp_signifies_affirm":  result.kp_sublord_signifies_affirm,
        "moon_status":          result.moon_status,
        "moon_void":            result.moon_void,
        "timing_estimate":      result.timing_estimate,
        "timing_unit":          result.timing_unit,
        "affirm_significators": result.affirm_significators,
        "deny_significators":   result.deny_significators,
        "lagna_sign":           result.lagna_sign,
        "lagna_lord":           result.lagna_lord,
        "moon_sign":            result.moon_sign,
        "moon_nakshatra":       result.moon_nakshatra,
        "factors":              result.factors,
        "classical_rules":      result.classical_rules_fired,
        "remedies":             result.remedy_suggestions,
        "planets":              result.planets_summary,
        "house_lords":          result.house_lords,
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from datetime import datetime

    moment   = datetime.now()
    lat, lon = city_to_coords("bangalore")
    city     = "Bangalore"
    category = sys.argv[1] if len(sys.argv) > 1 else "career_employment"
    question = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Will I get this job offer?"

    print(f"\n[Prashna] Casting chart for {moment.strftime('%d-%m-%Y %H:%M')} at {city}")
    result, html_path = run_prashna(moment, lat, lon, city, category, question, output_dir="prashna_reports")

    print(f"\n  Verdict    : {result.verdict}  ({result.confidence_band}, {int(result.confidence*100)}%)")
    print(f"  KP Sub-Lord: {result.kp_sublord_verdict}")
    print(f"  Moon       : {result.moon_status}")
    print(f"  Timing     : {result.timing_estimate}")
    print(f"  HTML       : {html_path}\n")
