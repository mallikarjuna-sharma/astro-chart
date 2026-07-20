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
    calculation_identity: Dict[str, Any] = field(default_factory=dict)

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
    # BUGFIX: previously only the applying planet's name was retained; the
    # actual remaining angular distance to the aspect that _check_moon_status
    # detected (which may be sextile/square/trine/opposition, not just
    # conjunction) was discarded. _estimate_timing then silently recomputed
    # a conjunction-only distance, giving wrong timing whenever the Moon's
    # real applying aspect is not a conjunction. Store it so timing can be
    # computed against the actual aspect being perfected (standard KP/
    # Parashari timing convention: time-to-perfection is measured against
    # the applying aspect's own closing degree, not a straight-line
    # planet-to-planet distance).
    moon_applying_aspect_deg: Optional[float] = None
    # P-1: Panchang at query moment
    panchang: Dict = field(default_factory=dict)
    # Signed daily motion in degrees/day (negative = retrograde), keyed by
    # planet name. Needed for Tajika Ithasala/Isbaha (mutual-application)
    # detection, which requires knowing which of two planets is closing the
    # angular gap faster, not just whether either one is retrograde.
    planet_speeds: Dict[str, float] = field(default_factory=dict)


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
    # gap fix (2026-07-19 audit, 2nd pass): CONDITIONAL previously always
    # displayed as "Conditionally Favourable" (a yes-leaning label) even
    # when the underlying affirm/deny ratio was BELOW 50% -- i.e. more of
    # the weighted evidence favoured denial, but the label still read as a
    # soft yes and `confidence` silently switched meaning (became "how
    # confident in NO", not "how confident in the verdict shown"). Two new
    # fields make this explicit instead of implicit:
    #   verdict_leaning : "YES" or "NO" -- which side the raw ratio actually
    #                      favours, independent of the CONDITIONAL hedge.
    #   binary_answer   : a strict YES/NO reading of the ratio (>=0.5 -> YES,
    #                      <0.5 -> NO), for callers/users who explicitly want
    #                      a plain yes-or-no rather than a hedged verdict.
    verdict_leaning: str = ""
    binary_answer: str = ""

    # Evidence
    kp_sublord_verdict: str = ""
    kp_sublord_planet: str = ""
    kp_sublord_signifies_affirm: bool = False
    # Joint KP cusp check (gap fix): KP doctrine requires the sub-lords of ALL
    # relevant houses for the query type -- not just the single "primary"
    # house -- to jointly signify affirmation (classically: 10/6 for career
    # PLUS 11 for gain/fulfilment of desire) before a confident YES is
    # warranted. kp_joint_houses/kp_joint_details record the per-house
    # breakdown; kp_joint_verdict is the combined judgement across all of them.
    kp_joint_houses: List[int] = field(default_factory=list)
    kp_joint_details: Dict[str, str] = field(default_factory=dict)   # {"10": "affirms", "11": "mixed", ...}
    kp_joint_verdict: str = ""            # "ALL_AFFIRM" / "ALL_DENY" / "MIXED"
    moon_status: str = ""               # e.g. "Applying to Jupiter (benefic)"
    moon_void: bool = False
    # Precision caveat when Moon is within a razor-thin arc of its sign end --
    # the VoC determination is then sensitive to sub-degree ayanamsa/ephemeris
    # drift and should be flagged to the reader rather than stated flatly.
    moon_status_caveat: str = ""
    # Tajika Ithasala/Isbaha (mutual application) between the querent
    # significator (lagna lord) and quesited significator (primary house
    # lord) -- the classical technique this engine previously omitted
    # entirely. Empty string if not computable (e.g. missing speed data).
    tajika_aspect_note: str = ""
    # Populated when the aggregate verdict (YES/CONDITIONAL) is contradicted
    # by two or more independent negative classical signals (dusthana lagna
    # lord, void Moon, retrograde significator, KP joint denial, combustion
    # of a key planet) -- surfaced as a visible caution banner in the HTML
    # report and used to select hedged remedies instead of a blanket
    # "proceed with confidence" message.
    internal_conflict_notes: List[str] = field(default_factory=list)
    # De-duplicated, first-seen-order list of planets that fired at least
    # one negative classical rule (2026-07-19 audit-fix pass). Computed
    # structurally by _classical_rules() at the point each rule fires,
    # replacing the previous text-scanning approach in both the internal-
    # conflict counter and the remedy generator (which could undercount
    # newer rule phrasings or misattribute a planet merely *named* in a
    # sentence about a different planet's affliction, e.g. Virodhargala).
    afflicted_planets: List[str] = field(default_factory=list)

    # P-1: Panchang audit at query moment
    panchang: Dict = field(default_factory=dict)
    panchang_score: float = 0.5         # 0-1 from panchang_quality()
    panchang_positive: List[str] = field(default_factory=list)
    panchang_negative: List[str] = field(default_factory=list)

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
    classical_rules_fired: List[str] = field(default_factory=list)   # positive rules
    denial_rules_fired: List[str]    = field(default_factory=list)   # A-3: negative rules separated
    remedy_suggestions: List[str] = field(default_factory=list)

    # Raw chart reference
    chart: Optional[PrashnaChart] = None
    validation_status: Dict[str, Any] = field(default_factory=lambda: {
        "calculation_status": "COMPUTED",
        "reference_validation": "NOT_RUN_MISSING_GOLDEN_FIXTURES",
        "empirical_validation": "NOT_RUN_MISSING_LABELLED_BENCHMARK",
        "statistical_calibration": "NOT_CALIBRATED",
        "validated_claim_allowed": False,
    })
    score_semantics: str = "RULE_SCORE_NOT_EMPIRICAL_PROBABILITY"
    disclaimer: str = (
        "Traditional interpretive guidance; not scientifically validated and not a substitute "
        "for qualified educational, career, financial, legal or medical advice."
    )


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
    """Return (nakshatra, nakshatra_lord, sub_lord) for a given absolute degree.

    FIX-2 (NODE_MODE): When Rahu/Ketu longitudes are used as the input degree,
    the answer depends on whether the caller used TRUE or MEAN nodes.  True Rahu
    can differ by up to ±1.5° from Mean Rahu, which may shift it into the next
    sub-lord division (each sub spans ≈0.4°–2.9°).  The node mode is declared
    in constants.NODE_MODE ("TRUE" | "MEAN") and must be respected by the
    ephemeris layer (pyhora / swisseph) before this function is called.
    This function is node-mode-agnostic: it simply returns the sub-lord for
    whatever degree it receives; correctness rests on the upstream ephemeris.
    """
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


def _cast_prashna_chart_canonical(
    moment: datetime, lat: float, lon: float, city: str = "",
) -> PrashnaChart:
    """Cast KP Prashna with Krishnamurti ayanamsha, true nodes and Placidus."""
    from jyotish.ephemeris import get_house_cusps_placidus, get_planet_longitudes, get_planet_speeds
    from jyotish.llm_policy import AYANAMSHA, NODE_TYPE
    local_moment = moment.replace(tzinfo=None)
    offset = moment.utcoffset() if moment.tzinfo is not None else None
    tz_hours = offset.total_seconds() / 3600.0 if offset is not None else None
    longitudes = get_planet_longitudes(local_moment, lat, lon, AYANAMSHA, tz_hours)
    speeds = get_planet_speeds(local_moment, lat, lon, AYANAMSHA, tz_hours)
    cusp_map = get_house_cusps_placidus(local_moment, lat, lon, AYANAMSHA, tz_hours)
    if not longitudes or len(cusp_map) != 12:
        raise RuntimeError("Canonical Prashna requires nine-graha longitudes and 12 Placidus cusps")
    chart = PrashnaChart(moment=moment, lat=lat, lon=lon, city=city)
    chart.calculation_identity = {"ayanamsha": AYANAMSHA, "node_type": NODE_TYPE,
                                  "house_system": "Placidus", "approximation_fallback_used": False}
    cusps = [float(cusp_map[i]) for i in range(1, 13)]
    chart.house_cusps = cusps
    chart.house_cusp_signs = [_lon_to_sign_degree(c)[0] for c in cusps]
    chart.lagna_sign, chart.lagna_degree = _lon_to_sign_degree(cusps[0])
    lagna_num = _SIGN_NUM[chart.lagna_sign]
    for i, sign in enumerate(chart.house_cusp_signs, 1):
        chart.house_lords[str(i)] = _SIGN_LORD.get(sign, "")
    for i, cusp in enumerate(cusps, 1):
        chart.kp_sublords[str(i)] = _kp_sublord_for_degree(cusp)[2]
    for planet, longitude in longitudes.items():
        sign, degree = _lon_to_sign_degree(longitude)
        nakshatra, nak_lord, sub_lord = _kp_sublord_for_degree(longitude)
        chart.planets_d1[planet] = {
            "sign": sign, "degree": round(degree, 6), "abs_degree": round(longitude, 6),
            "retrograde": bool(speeds.get(planet, 0.0) < 0.0),
            "nakshatra": nakshatra, "nakshatra_lord": nak_lord, "sub_lord": sub_lord,
            "house": ((_SIGN_NUM[sign] - lagna_num) % 12) + 1,
        }
    chart.planet_speeds = {p: float(v) for p, v in speeds.items()}
    moon = longitudes["Moon"]
    chart.moon_void, chart.moon_applying_to, chart.moon_applying_aspect_deg = _check_moon_status(moon, longitudes, moment)
    try:
        from jyotish.panchang import compute_panchang
        chart.panchang = compute_panchang(longitudes["Sun"], moon, moment)
    except Exception as exc:
        chart.panchang = {"status": "NOT_COMPUTED", "reason": str(exc)}
    return chart


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
    return _cast_prashna_chart_canonical(moment, lat, lon, city)



def _check_moon_status(
    moon_abs: float,
    planet_lons: Dict[str, float],
    dt: datetime,
) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Return (void_of_course, planet_moon_applies_to).
    Moon is void-of-course if it makes no applying aspect (conjunction, sextile,
    square, trine, or opposition) to any planet before leaving its current sign.

    B-3 fix: original code only checked same-sign conjunctions.  Now we check all
    five major Ptolemaic aspects across all planets — Moon is truly VoC only when
    none of those aspect hits occur within the remaining degrees of the sign.
    """
    moon_sign_end = (math.floor(moon_abs / 30) + 1) * 30  # degrees to end of sign
    remaining_deg = moon_sign_end - moon_abs
    if remaining_deg < 0:
        remaining_deg += 360

    # Major aspect offsets (degrees that the planet must be ahead of Moon)
    _ASPECTS = [0, 60, 90, 120, 180]   # conjunction, sextile, square, trine, opposition

    # Planets that form an applying aspect to Moon within remaining_deg
    candidates: List[Tuple[float, str, float]] = []
    for pname, plon in planet_lons.items():
        if pname == "Moon":
            continue
        for _asp in _ASPECTS:
            # Apparent distance Moon must travel to reach this aspect with pname
            aspect_lon = (plon - _asp) % 360
            diff = (aspect_lon - moon_abs) % 360
            if diff < remaining_deg:
                candidates.append((diff, pname, diff))
                break  # count pname once (nearest aspect)

    candidates.sort(key=lambda c: c[0])
    if not candidates:
        return True, None, None   # Void of course
    return False, candidates[0][1], candidates[0][2]


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


# V1.3 merge plan item 1: delegates to the canonical jyotish/dignity.py::
# is_combust(), retiring this module's own orb table (which was already
# consistent with the canonical one on Rahu/Ketu exclusion, but kept its own
# duplicate copy of the Moon/Mars/Mercury/Jupiter/Venus/Saturn orb values).
#
# 2026-07-18 gap-remediation pass: also pull in the canonical friend/enemy/
# neecha-bhanga dignity_state() and graha_yuddha() so this module's dignity
# vocabulary stops being limited to Exalted/Debilitated/Own (the "enemy-sign
# placements are invisible" gap) and combustion/planetary-war are surfaced
# as first-class classical rules rather than a silent 50% score discount.
from jyotish.dignity import (
    is_combust as _dignity_is_combust,
    dignity_state as _dignity_state,
    graha_yuddha as _dignity_graha_yuddha,
    debilitation_dispositor as _dignity_debil_dispositor,
)
# 2026-07-19: Prashna Marga 30-rule implementation pass — reuse the
# canonical kendra/trikona/dusthana house sets rather than redefining them.
from jyotish.constants import _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES
_UPACHAYA_HOUSES = frozenset({3, 6, 10, 11})


def _is_combust(pname: str, planets_d1: Dict[str, Dict]) -> bool:
    """Return True if planet is within combust orb of Sun."""
    sun_abs = planets_d1.get("Sun",  {}).get("abs_degree", -999)
    p_abs   = planets_d1.get(pname, {}).get("abs_degree", -999)
    if sun_abs < 0 or p_abs < 0:
        return False
    return _dignity_is_combust(pname, p_abs, sun_abs)


def _score_significators(
    sigs: Dict[str, PrashnaSignificator],
    category: str,
    planets_d1: Optional[Dict[str, Dict]] = None,
) -> Dict[str, PrashnaSignificator]:
    """Assign scores and label affirm vs deny.

    Combust planets (within their classical orb of the Sun) are penalised by
    50% — they lose the ability to fully deliver their significations.
    """
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

        # P-3: Combustion penalty — combust planets lose 50% of positive score
        if score > 0 and planets_d1 and _is_combust(pname, planets_d1):
            score *= 0.50

        sig.score = round(score, 2)
    return sigs


# ---------------------------------------------------------------------------
# Dignity helper
# ---------------------------------------------------------------------------

_DIGNITY_DISPLAY_LABELS: Dict[str, str] = {
    "EXALTED": "Exalted", "MOOLATRIKONA": "Moolatrikona", "OWN_SIGN": "Own",
    "GREAT_FRIEND": "Great Friend", "FRIEND": "Friend", "NEUTRAL": "",
    "ENEMY": "Enemy", "GREAT_ENEMY": "Great Enemy",
    "DEBILITATED": "Debilitated", "NEECHA_BHANGA": "Neecha Bhanga (cancelled)",
}
# Tiers that should render as a positive (green) signal vs. a negative (red)
# one in the HTML report and in classical-rule polarity checks.
_DIGNITY_POSITIVE_TIERS = {"EXALTED", "MOOLATRIKONA", "OWN_SIGN", "GREAT_FRIEND", "FRIEND"}
_DIGNITY_NEGATIVE_TIERS = {"DEBILITATED", "ENEMY", "GREAT_ENEMY"}


def _planet_dignity(
    pname: str,
    sign: str,
    planet_signs: Optional[Dict[str, str]] = None,
) -> str:
    """Friendly display label for a planet's dignity in `sign`.

    2026-07-18 gap fix: previously only ever returned "Exalted" /
    "Debilitated" / "Own" / "" -- an enemy-sign placement (e.g. Venus in Leo,
    Sun's sign) rendered identically to a neutral placement, silently hiding
    a materially weakening classical factor. Now delegates to the canonical
    jyotish.dignity.dignity_state() five/nine-fold classification (adds
    Friend/Great Friend/Enemy/Great Enemy/Neutral/Moolatrikona/Neecha
    Bhanga), so every state is visible. `planet_signs` (optional
    {planet: sign} map from the same chart) lets the mutual-friendship
    (Great Friend/Great Enemy) refinement run; without it, natural
    (one-way) friendship is used.
    """
    if not pname or not sign:
        return ""
    state = _dignity_state(pname, sign, planet_signs=planet_signs)
    return _DIGNITY_DISPLAY_LABELS.get(state, "")


def _planet_dignity_state(
    pname: str,
    sign: str,
    planet_signs: Optional[Dict[str, str]] = None,
) -> str:
    """Raw dignity_state() tier (e.g. "ENEMY", "OWN_SIGN") for internal
    polarity checks, kept separate from the display label above."""
    if not pname or not sign:
        return "NEUTRAL"
    return _dignity_state(pname, sign, planet_signs=planet_signs)


# ---------------------------------------------------------------------------
# Classical rule checkers
# ---------------------------------------------------------------------------

def _classical_rules(
    chart: PrashnaChart,
    sigs: Dict[str, PrashnaSignificator],
    category: str,
) -> Tuple[List[str], List[str], str, List[str], int, int]:
    """
    Apply classical Prashna rules.
    Returns (positive_rules_fired, negative_rules_fired, tajika_aspect_note,
    afflicted_planets, pos_signal_count, neg_signal_count).

    tajika_aspect_note is always returned (even for the "neutral"/no-aspect
    case) so callers can surface it to the reader regardless of whether it
    moved the pos/neg tally.

    afflicted_planets (2026-07-19 audit-fix pass) is a de-duplicated,
    first-seen-order list of the specific planets each fired negative rule
    is actually about. This replaces two previously-separate, brittle
    mechanisms that both re-derived "which planet is this rule about" by
    substring-matching planet names out of the rendered rule *text*
    (analyze_prashna's internal-conflict affliction counter, and
    _suggest_remedies' _extract_afflicted_planets): text-scanning silently
    undercounted newer rule phrasings and could misattribute an affliction
    to a planet merely *named* in a sentence about another planet's problem
    (e.g. the Virodhargala rule names both the supporting AND countering
    planets; only the countering side is actually "afflicted"). Every
    _add_neg() call below tags the correct planet(s) at the point the rule
    fires, so no re-parsing is needed downstream.
    """
    pos, neg = [], []
    # gap fix (2026-07-19 audit, 2nd pass): trackers used to detect
    # *compounding* afflictions -- e.g. a planet that is BOTH retrograde AND
    # combust, or a lagna that is afflicted at both the lord level (dusthana)
    # and the occupancy level (malefic/node sitting in H1) -- so these can be
    # surfaced as one explicit "compounded" signal rather than silently
    # relying on the reader to notice two separate bullet points are about
    # the same underlying weakness.
    _combust_flagged: set = set()
    _retrograde_flagged: set = set()
    _lagna_lord_in_dusthana = False
    # Parallel lists: pos_tags[i]/neg_tags[i] = the planet(s) pos[i]/neg[i]
    # is about, or [] for a structural rule not tied to one specific planet
    # (e.g. Paksha, a pure house-lord-vs-house-lord yoga check). Consumed
    # by analyze_prashna to de-duplicate afflictions per planet (rather
    # than per rule-string) for both scoring and remedy generation.
    pos_tags: List[List[str]] = []
    neg_tags: List[List[str]] = []

    def _add_pos(text: str, planets: Optional[List[str]] = None) -> None:
        pos.append(text)
        pos_tags.append([p for p in (planets or []) if p])

    def _add_neg(text: str, planets: Optional[List[str]] = None) -> None:
        neg.append(text)
        neg_tags.append([p for p in (planets or []) if p])

    primary_h = _PRIMARY_HOUSE.get(category, 10)
    pdata = chart.planets_d1
    # Shared {planet: sign} map so dignity_state() can resolve mutual
    # (two-way) Great Friend/Great Enemy relationships, not just one-way
    # natural friendship.
    planet_signs = {p: d.get("sign", "") for p, d in pdata.items()}

    # Rule 0 (P-4): Lagna lord in dusthana (6/8/12) — matter is afflicted
    lagna_lord  = chart.house_lords.get("1", "")
    if lagna_lord:
        ll_house = pdata.get(lagna_lord, {}).get("house", 0)
        if ll_house in (6, 8, 12):
            _add_neg(
                f"Lagna lord {lagna_lord} occupies H{ll_house} (dusthana) — the query itself is afflicted; "
                f"obstacles and hidden difficulties even if other indicators are positive",
                planets=[lagna_lord],
            )
            _lagna_lord_in_dusthana = True
        # Rule 0b (gap fix): enemy-sign lagna lord was previously invisible —
        # _planet_dignity() only ever reported Exalted/Debilitated/Own, so an
        # enemy-sign placement rendered identically to a neutral one. Now
        # surfaced explicitly since it materially weakens the query's own
        # significator.
        ll_sign  = pdata.get(lagna_lord, {}).get("sign", "")
        ll_state = _planet_dignity_state(lagna_lord, ll_sign, planet_signs)
        if ll_state in ("ENEMY", "GREAT_ENEMY"):
            _add_neg(
                f"Lagna lord {lagna_lord} is in {'a great enemy' if ll_state == 'GREAT_ENEMY' else 'an enemy'} "
                f"sign ({ll_sign}) — the querent's own significator is weakened",
                planets=[lagna_lord],
            )
        # Rule 0c (gap fix): combustion of the lagna lord was previously only
        # a silent 50% score discount inside _score_significators(); readers
        # never saw *why* a planet's contribution was halved. Surface it.
        if _is_combust(lagna_lord, pdata):
            _add_neg(
                f"Lagna lord {lagna_lord} is combust (too close to the Sun) — "
                f"its significations are weakened and less able to independently confirm the matter",
                planets=[lagna_lord],
            )
            _combust_flagged.add(lagna_lord)

    # Rule 0d (gap fix): same combustion visibility for the primary house
    # lord (the "quesited" significator), and enemy-sign check too.
    primary_lord_early = chart.house_lords.get(str(primary_h), "")
    if primary_lord_early:
        pl_sign  = pdata.get(primary_lord_early, {}).get("sign", "")
        pl_state = _planet_dignity_state(primary_lord_early, pl_sign, planet_signs)
        if pl_state in ("ENEMY", "GREAT_ENEMY"):
            _add_neg(
                f"H{primary_h} lord {primary_lord_early} is in {'a great enemy' if pl_state == 'GREAT_ENEMY' else 'an enemy'} "
                f"sign ({pl_sign}) — the query-house significator is weakened",
                planets=[primary_lord_early],
            )
        if _is_combust(primary_lord_early, pdata):
            _add_neg(
                f"H{primary_h} lord {primary_lord_early} is combust — the query-house significator "
                f"is weakened and less able to independently confirm the matter",
                planets=[primary_lord_early],
            )
            _combust_flagged.add(primary_lord_early)

    # Rule 0e (gap fix): Graha Yuddha (planetary war) — a significator that
    # loses a planetary war is classically weakened even if otherwise well
    # placed. Previously not checked anywhere in this module.
    _planet_lons = {p: d.get("abs_degree") for p, d in pdata.items() if d.get("abs_degree") is not None}
    _yuddha = _dignity_graha_yuddha(_planet_lons)
    for _war in _yuddha.get("wars", []):
        loser = _war["loser"]
        loser_sig = sigs.get(loser)
        if loser_sig and (loser_sig.affirm_houses_touched or loser == lagna_lord or loser == primary_lord_early):
            _add_neg(
                f"{loser} loses planetary war (Graha Yuddha) with {_war['winner']} "
                f"(separation {_war['separation_degrees']}°) — its significations are weakened",
                planets=[loser],
            )

    # Rule 1: Lagna lord in primary house or primary house lord in lagna
    primary_lord = chart.house_lords.get(str(primary_h), "")
    if lagna_lord and pdata.get(lagna_lord, {}).get("house") == primary_h:
        _add_pos(f"Lagna lord {lagna_lord} occupies H{primary_h} (question house) — strong YES indicator", planets=[lagna_lord])
    if primary_lord and pdata.get(primary_lord, {}).get("house") == 1:
        _add_pos(f"H{primary_h} lord {primary_lord} occupies Lagna — very auspicious for {_CATEGORY_LABELS.get(category,'query')}", planets=[primary_lord])

    # Rule 2: Moon applying to a planet that signifies primary house
    #
    # gap fix (2026-07-19 audit, 2nd pass): when chart.moon_applying_to is a
    # DUAL significator (it touches both an affirm house and a deny house
    # for this category -- common, since many planets rule more than one
    # house), the old code fired _add_pos AND _add_neg from the exact same
    # single Tajika aspect. That double-dipped one astronomical event into
    # both tallies as if it were two independent confirmations, inflating
    # both pos_signal_count and neg_signal_count (and, via afflicted_planets,
    # the affliction-count used for the YES->CONDITIONAL downgrade) from a
    # single fact. A planet genuinely signifying both outcomes is itself a
    # classical caution sign (the aspect that times the matter is inherently
    # mixed/contested), so now it's surfaced as ONE explicit negative note
    # describing the conflict, instead of contradictory pos+neg bullets.
    if not chart.moon_void and chart.moon_applying_to:
        applying_sig = sigs.get(chart.moon_applying_to)
        _touches_affirm = bool(applying_sig and applying_sig.affirm_houses_touched)
        _touches_deny   = bool(applying_sig and applying_sig.deny_houses_touched)
        if _touches_affirm and _touches_deny:
            _add_neg(
                f"Moon applying to {chart.moon_applying_to}, which signifies BOTH H{applying_sig.affirm_houses_touched[0]} "
                f"(affirm) and H{applying_sig.deny_houses_touched[0]} (denial) — this timing aspect is inherently mixed/"
                f"contested, not a clean confirmation; treat the outcome it times with caution",
                planets=["Moon", chart.moon_applying_to],
            )
        elif _touches_affirm:
            _add_pos(f"Moon applying to {chart.moon_applying_to} (significator of H{applying_sig.affirm_houses_touched[0]}) — timing confirms YES", planets=["Moon", chart.moon_applying_to])
        elif _touches_deny:
            _add_neg(f"Moon applying to {chart.moon_applying_to} (significator of denial H{applying_sig.deny_houses_touched[0]}) — unfavorable", planets=["Moon", chart.moon_applying_to])
    elif chart.moon_void:
        _add_neg("Moon is Void-of-Course — matter will not come to fruition as intended", planets=["Moon"])

    # Rule 3: Benefics in primary and support houses
    affirm_hs = set(_AFFIRM_HOUSES.get(category, []))
    for pname in _NATURAL_BENEFICS:
        pd = pdata.get(pname, {})
        if pd.get("house") in affirm_hs:
            dig = _planet_dignity(pname, pd.get("sign", ""), planet_signs)
            dig_note = f" ({dig})" if dig else ""
            _add_pos(f"{pname}{dig_note} in H{pd['house']} — benefic in question house supports YES", planets=[pname])

    # Rule 4: Malefics in primary house without benefic aspect
    # (gap fix: previously only checked for the string "Debilitated" — an
    # enemy-sign malefic in an affirm house is also weakened and was
    # silently missed. Also now checks combustion of any affirm-house
    # significator, not just the lagna/primary lords handled in Rule 0.)
    deny_hs = set(_DENY_HOUSES.get(category, []))
    for pname in _NATURAL_MALEFICS:
        pd = pdata.get(pname, {})
        h  = pd.get("house")
        if h and h in affirm_hs:
            dig_state = _planet_dignity_state(pname, pd.get("sign", ""), planet_signs)
            if dig_state in ("DEBILITATED", "ENEMY", "GREAT_ENEMY"):
                label = _DIGNITY_DISPLAY_LABELS.get(dig_state, dig_state).lower()
                _add_neg(f"{pname} {label} in H{h} — weakens the query house", planets=[pname])
            elif pname in ("Rahu", "Ketu"):
                _add_neg(f"{pname} in H{h} — shadowy node can delay or distort outcome", planets=[pname])
            if _is_combust(pname, pdata):
                _add_neg(f"{pname} is combust in H{h} — its significations are weakened", planets=[pname])
                _combust_flagged.add(pname)

    # Rule 5: Retrograde significators
    for pname, sig in sigs.items():
        pd = pdata.get(pname, {})
        if pd.get("retrograde") and sig.affirm_houses_touched:
            _add_neg(f"{pname} is retrograde — matter may be delayed, reversed, or reconsidered", planets=[pname])
            _retrograde_flagged.add(pname)
            break

    # Rule 6: 7th lord in H10 / H10 lord in H7 (mutual exchange relevant for career/business)
    if category in ("career_employment", "business"):
        h7_lord  = chart.house_lords.get("7", "")
        h10_lord = chart.house_lords.get("10", "")
        if h7_lord and pdata.get(h7_lord, {}).get("house") == 10:
            _add_pos(f"H7 lord {h7_lord} in H10 — partnerships fuel career growth", planets=[h7_lord])
        if h10_lord and pdata.get(h10_lord, {}).get("house") == 7:
            _add_pos(f"H10 lord {h10_lord} in H7 — professional alliance brings opportunity", planets=[h10_lord])

    # Rule 7: H12 lord or H12 tenants — indicates expenditure / loss for financial query
    if category == "financial":
        h12_lord = chart.house_lords.get("12", "")
        if h12_lord and pdata.get(h12_lord, {}).get("house") in (2, 11):
            _add_neg(f"H12 lord {h12_lord} in wealth house — gains may be offset by expenses", planets=[h12_lord])

    # Rule 8: H9 activated for foreign / education
    if category in ("foreign_opportunity", "education"):
        h9_lord = chart.house_lords.get("9", "")
        if h9_lord and pdata.get(h9_lord, {}).get("house") in (1, 9, 12):
            _add_pos(f"H9 lord {h9_lord} well-placed — auspicious for {_CATEGORY_LABELS.get(category,'')}", planets=[h9_lord])

    # Rule 9: H3 (change, short journeys) activated for job change
    if category == "job_change":
        h3_lord = chart.house_lords.get("3", "")
        if h3_lord and pdata.get(h3_lord, {}).get("house") in (10, 6, 11):
            _add_pos(f"H3 lord {h3_lord} links with career houses — change is imminent", planets=[h3_lord])

    # Rule 10 (gap fix): Tajika Ithasala/Isbaha — mutual application between
    # the querent's own significator (lagna lord) and the quesited
    # significator (primary house lord). This is the single most load-
    # bearing classical horary technique for confirming *whether the matter
    # will actually happen*, distinct from the KP/house-based scoring above,
    # and was previously absent from this engine entirely.
    tajika_note = ""
    tajika_polarity = "neutral"
    if lagna_lord and primary_lord and lagna_lord != primary_lord:
        tajika_note, tajika_polarity = _check_tajika_ithasala(chart, lagna_lord, primary_lord)
        if tajika_note:
            if tajika_polarity == "positive":
                _add_pos(tajika_note, planets=[lagna_lord, primary_lord])
            elif tajika_polarity == "negative":
                _add_neg(tajika_note, planets=[lagna_lord, primary_lord])
            # "neutral" tajika notes (no aspect relationship at all) are
            # informational only and surfaced via result.tajika_aspect_note,
            # not added to the classical pos/neg rule lists.

    # ------------------------------------------------------------------
    # Rules 11-30: Prashna Marga 30-rule implementation pass (2026-07-19,
    # explicit user request). Numbered per the compiled 30-rule list
    # discussed with the user; each docstring references the list item it
    # implements. All of these are simplified, best-effort approximations
    # of classical techniques (Argala, Sahams, Manau/Kambool especially),
    # clearly labelled as such — not verbatim reproductions of any single
    # source text.
    # ------------------------------------------------------------------

    # Rule 11 (list item 1): Lagna lord in a kendra/trikona from itself
    # (i.e. its own occupied house) strengthens the querent's position.
    if lagna_lord:
        ll_house = pdata.get(lagna_lord, {}).get("house", 0)
        if ll_house in _KT_HOUSES:
            _add_pos(
                f"Lagna lord {lagna_lord} occupies H{ll_house} (kendra/trikona) — "
                f"strengthens the querent's own position",
                planets=[lagna_lord],
            )

    # Rule 12 (list item 5): Lagna lord retrograde specifically — the
    # querent themself will change their mind, delay, or reconsider the
    # question (distinct from Rule 5's general significator-retrograde
    # check, which fires for any affirming planet, not the querent's own).
    if lagna_lord and pdata.get(lagna_lord, {}).get("retrograde"):
        _add_neg(
            f"Lagna lord {lagna_lord} is retrograde — the querent themself is likely to "
            f"change their mind, hesitate, or reconsider the question",
            planets=[lagna_lord],
        )
        _retrograde_flagged.add(lagna_lord)

    # Rule 13 (list item 6): Quesited (primary house) lord in a kendra/
    # trikona from the Lagna favors fruition.
    if primary_lord:
        pl_house = pdata.get(primary_lord, {}).get("house", 0)
        if pl_house in _KT_HOUSES:
            _add_pos(
                f"H{primary_h} lord {primary_lord} occupies H{pl_house} (kendra/trikona) — "
                f"favors fruition of the matter",
                planets=[primary_lord],
            )

    # Rule 14 (list item 9): Parivartana Yoga (mutual exchange) — Lagna
    # lord occupies the query house AND the query-house lord occupies the
    # Lagna simultaneously. Rule 1 above already reports each half
    # individually; this fires only when BOTH hold at once, since the full
    # mutual exchange is a materially stronger yoga than either half alone.
    if (lagna_lord and primary_lord and lagna_lord != primary_lord
            and pdata.get(lagna_lord, {}).get("house") == primary_h
            and pdata.get(primary_lord, {}).get("house") == 1):
        _add_pos(
            f"Parivartana Yoga: Lagna lord {lagna_lord} and H{primary_h} lord {primary_lord} "
            f"are in mutual exchange — one of the strongest classical yogas for a definite YES",
            planets=[lagna_lord, primary_lord],
        )

    # Rule 15 (list item 14): Moon's nakshatra lord placement modifies the
    # Moon's overall favorability independent of void-of-course status.
    moon_nak_lord = pdata.get("Moon", {}).get("nakshatra_lord", "")
    if moon_nak_lord and moon_nak_lord in pdata:
        mnl_house = pdata.get(moon_nak_lord, {}).get("house", 0)
        if mnl_house in _KT_HOUSES:
            _add_pos(f"Moon's nakshatra lord {moon_nak_lord} is in H{mnl_house} (kendra/trikona) — supports a favorable flow of events", planets=["Moon", moon_nak_lord])
        elif mnl_house in _DUSTHANA_HOUSES:
            _add_neg(f"Moon's nakshatra lord {moon_nak_lord} is in H{mnl_house} (dusthana) — the flow of events is troubled", planets=["Moon", moon_nak_lord])

    # Rule 16 (list item 15): Paksha (waxing/waning Moon) — Shukla
    # (waxing) generally favors growth/fruition-type questions; Krishna
    # (waning) favors questions about decline, loss, or ending something.
    # Low-weight/contextual: added as a single informational rule, not a
    # strong affirm/deny signal, and phrased so it never contradicts itself
    # across categories. Deliberately untagged (no planets=) -- this is a
    # structural/timing factor, not a specific planet's affliction, so it
    # should never drive a per-planet remedy recommendation.
    _sun_abs = pdata.get("Sun", {}).get("abs_degree")
    _moon_abs_pk = pdata.get("Moon", {}).get("abs_degree")
    if _sun_abs is not None and _moon_abs_pk is not None:
        _elong = (_moon_abs_pk - _sun_abs) % 360.0
        if _elong < 180.0:
            _add_pos("Shukla Paksha (waxing Moon) — favors growth, increase, and fruition-type matters")
        else:
            _add_neg("Krishna Paksha (waning Moon) — favors completion/reduction matters; less support for new growth")

    # Rule 17 (list items 19-20): Manau Yoga (transfer of light) / Kambool
    # Yoga — when the Lagna lord and quesited lord are separating (Isbaha,
    # already flagged negative above by the Tajika check), a third planet
    # positioned between them in longitude can "carry" the connection
    # through even though direct Ithasala failed. If that transferring
    # planet is itself well-placed (not debilitated/combust/enemy), the
    # matter is rescued (Manau); if the transferring planet is weak, the
    # rescue fails (Kambool) and the original separation stands.
    if tajika_polarity == "negative" and lagna_lord and primary_lord:
        manau_note, manau_polarity, manau_planets = _check_manau_kambool(chart, lagna_lord, primary_lord, planet_signs)
        if manau_note:
            if manau_polarity == "positive":
                _add_pos(manau_note, planets=manau_planets)
            elif manau_polarity == "negative":
                _add_neg(manau_note, planets=manau_planets)

    # Rule 18 (list item 21, generalized): combustion of any of the
    # leading affirm/deny significators (not just the Lagna/query-house
    # lords already checked in Rule 0c/0d/Rule 4).
    _ranked_sigs = sorted(sigs.values(), key=lambda s: -abs(s.score))
    _combust_already_noted = {lagna_lord, primary_lord}
    for _sig in _ranked_sigs[:5]:
        if _sig.planet in _combust_already_noted:
            continue
        if _sig.score != 0 and _is_combust(_sig.planet, pdata):
            _add_neg(f"{_sig.planet} (leading significator) is combust — its significations are weakened", planets=[_sig.planet])
            _combust_already_noted.add(_sig.planet)
            _combust_flagged.add(_sig.planet)

    # Rule 19 (list item 24): Neecha Bhanga (cancelled debilitation) —
    # previously dignity_state() could compute this, but _classical_rules()
    # never passed the dispositor/Moon-house context needed to trigger it,
    # so a cancelled debilitation was always reported as a plain
    # (uncancelled) affliction. Wire the context through for the Lagna and
    # quesited lords, the two significators already checked for plain
    # debilitation above.
    _moon_house = pdata.get("Moon", {}).get("house", 0)
    for _role, _planet in (("Lagna lord", lagna_lord), (f"H{primary_h} lord", primary_lord)):
        if not _planet:
            continue
        _p_sign = pdata.get(_planet, {}).get("sign", "")
        if _EXALT_SIGN.get(_planet) == _p_sign or _DEBIL_SIGN.get(_planet) != _p_sign:
            continue  # not debilitated — nothing to cancel
        _debil_lord = _dignity_debil_dispositor(_planet)
        _dispositor_house = pdata.get(_debil_lord, {}).get("house") if _debil_lord else None
        _dispositor_sign  = pdata.get(_debil_lord, {}).get("sign") if _debil_lord else None
        _p_house_from_moon = (
            ((pdata.get(_planet, {}).get("house", 0) - _moon_house) % 12) + 1
            if _moon_house else None
        )
        _state = _dignity_state(
            _planet, _p_sign,
            dispositor_house=_dispositor_house, dispositor_sign=_dispositor_sign,
            planet_house_from_moon=_p_house_from_moon,
        )
        if _state == "NEECHA_BHANGA":
            _add_pos(
                f"{_role} {_planet} is debilitated in {_p_sign} but Neecha Bhanga cancels it — "
                f"the apparent weakness is offset; treat as materially stronger than plain debilitation",
                planets=[_planet],
            )

    # Rule 20 (list item 26): Argala (intervention) / Virodhargala
    # (counter-argala) on the query house — simplified to occupancy-based
    # counting rather than full aspect-weighted Argala. Supporting argala
    # houses are the 2nd, 4th, and 11th counted from the query house;
    # counter-argala houses are the 3rd, 10th, and 12th counted from it.
    def _house_from(base: int, offset: int) -> int:
        return ((base - 1 + offset - 1) % 12) + 1
    _argala_houses = {_house_from(primary_h, 2), _house_from(primary_h, 4), _house_from(primary_h, 11)}
    _virodhargala_houses = {_house_from(primary_h, 3), _house_from(primary_h, 10), _house_from(primary_h, 12)}
    _argala_occupants = [p for p, d in pdata.items() if d.get("house") in _argala_houses]
    _virodhargala_occupants = [p for p, d in pdata.items() if d.get("house") in _virodhargala_houses]
    if len(_argala_occupants) > len(_virodhargala_occupants) and _argala_occupants:
        _add_pos(
            f"Argala on H{primary_h} from {', '.join(_argala_occupants)} is unobstructed by counter-argala — "
            f"supports fruition",
            planets=_argala_occupants,
        )
    elif _virodhargala_occupants and len(_virodhargala_occupants) >= len(_argala_occupants) and _argala_occupants:
        # gap fix (audit finding #5): only the countering (Virodhargala)
        # planets are actually "afflicted" here -- the supporting Argala
        # planets named in this same sentence lost the argument, they
        # aren't themselves the problem, so they must NOT be tagged.
        _add_neg(
            f"Argala on H{primary_h} from {', '.join(_argala_occupants)} is countered (Virodhargala) by "
            f"{', '.join(_virodhargala_occupants)} — support is neutralised",
            planets=_virodhargala_occupants,
        )

    # Rule 21 (list item 27): Parashari (non-KP) 11th-house connection
    # check — H11 (gain / fulfilment of desire) is, per KP-adjacent
    # doctrine generally and Parashari practice specifically, as important
    # as the matter's own house for a "will I get X" judgement. Reinstated
    # here without any KP sub-lord machinery (which has been removed
    # entirely from this module per a prior request).
    h11_lord = chart.house_lords.get("11", "")
    if h11_lord and h11_lord != primary_lord:
        h11_house = pdata.get(h11_lord, {}).get("house", 0)
        if h11_house in _KT_HOUSES or h11_house == primary_h:
            _add_pos(f"H11 lord {h11_lord} is well-placed (H{h11_house}) — supports fulfilment/gain of the matter", planets=[h11_lord])
        elif h11_house in _DUSTHANA_HOUSES:
            _add_neg(f"H11 lord {h11_lord} occupies H{h11_house} (dusthana) — fulfilment of the desire is obstructed", planets=[h11_lord])

    # Rule 22 (list item 28): general chart signature — benefics in
    # kendras and malefics in upachaya (3/6/10/11, "growing" houses where
    # malefics do relatively little harm) is a broadly favorable
    # signature; the inverse (malefics in kendras, benefics in dusthana)
    # is broadly unfavorable.
    # gap fix (2026-07-19 audit, 2nd pass): this rule is a whole-chart
    # signature, not a targeted lagna/house-lord/significator finding, so it
    # was previously tagged with EVERY malefic/benefic involved -- e.g. 3
    # malefics in kendras counted as 3 separate "afflicted planets" on top of
    # whatever those same 3 planets were already individually flagged for
    # elsewhere (dusthana, combust, retrograde...), letting one broad
    # contextual observation multiply the affliction tally by re-naming
    # planets already penalised on their own merits. Left untagged now (a
    # single structural signal, like Paksha) so it still counts once toward
    # neg_signal_count/pos_signal_count as background context, without
    # inflating afflicted_planets or the remedy list with planets that are
    # already accounted for by their own specific rules above.
    _benefics_in_kendra = [p for p in _NATURAL_BENEFICS if pdata.get(p, {}).get("house") in _KENDRA_HOUSES]
    _malefics_in_kendra = [p for p in _NATURAL_MALEFICS if pdata.get(p, {}).get("house") in _KENDRA_HOUSES]
    if len(_benefics_in_kendra) >= 2 and len(_malefics_in_kendra) == 0:
        _add_pos(f"Benefics ({', '.join(_benefics_in_kendra)}) occupy kendras with no malefic interference — broadly favorable chart signature (contextual)")
    if len(_malefics_in_kendra) >= 2:
        _add_neg(f"Multiple malefics ({', '.join(_malefics_in_kendra)}) occupy kendras — broadly unfavorable chart signature (contextual)")

    # Rule 23 (list item 29): the Lagna house itself (not just its lord)
    # occupied or aspected by benefics vs. malefics.
    _lagna_occupants = [p for p, d in pdata.items() if d.get("house") == 1]
    _lagna_benefics = [p for p in _lagna_occupants if p in _NATURAL_BENEFICS]
    _lagna_malefics = [p for p in _lagna_occupants if p in _NATURAL_MALEFICS]
    if _lagna_benefics:
        _add_pos(f"Lagna occupied by benefic(s) {', '.join(_lagna_benefics)} — supports a favorable outcome", planets=_lagna_benefics)
    if _lagna_malefics:
        _add_neg(f"Lagna occupied by malefic(s) {', '.join(_lagna_malefics)} — the querent's own house is afflicted", planets=_lagna_malefics)
    _lagna_aspecting_malefics = [
        p for p in _NATURAL_MALEFICS
        if p not in _lagna_occupants and 1 in (sigs.get(p).houses_aspected if sigs.get(p) else [])
    ]
    if _lagna_aspecting_malefics and not _lagna_benefics:
        _add_neg(f"Lagna aspected by malefic(s) {', '.join(_lagna_aspecting_malefics)} without benefic mitigation — denial signal", planets=_lagna_aspecting_malefics)

    # Rule 24 (list item 30): Karyasiddhi Saham (general success point) —
    # simplified classical Tajika formula: day birth => Saturn - Sun +
    # Lagna; night birth => Sun - Saturn + Lagna (mod 360). Day/night
    # determined by whether the Sun is above the horizon (houses 7-12
    # from Lagna) or below it (houses 1-6) at the query moment. The
    # resulting point's house lord's dignity/dusthana status is checked
    # as a category-general confirmation layer, distinct from the
    # matter's own house-lord logic above.
    _sun_house = pdata.get("Sun", {}).get("house", 0)
    _sun_lon = pdata.get("Sun", {}).get("abs_degree")
    _sat_lon = pdata.get("Saturn", {}).get("abs_degree")
    _lagna_lon = chart.house_cusps[0] if chart.house_cusps else None
    if _sun_lon is not None and _sat_lon is not None and _lagna_lon is not None:
        _is_day = _sun_house in (7, 8, 9, 10, 11, 12)
        _saham_lon = ((_sat_lon - _sun_lon + _lagna_lon) if _is_day else (_sun_lon - _sat_lon + _lagna_lon)) % 360.0
        _saham_sign, _ = _lon_to_sign_degree(_saham_lon)
        _saham_house = ((_SIGN_NUM[_saham_sign] - _SIGN_NUM[chart.lagna_sign]) % 12) + 1
        _saham_lord = chart.house_lords.get(str(_saham_house), "")
        if _saham_lord:
            _sl_house = pdata.get(_saham_lord, {}).get("house", 0)
            if _sl_house in _KT_HOUSES:
                _add_pos(f"Karyasiddhi Saham falls in H{_saham_house}, lord {_saham_lord} well-placed (H{_sl_house}) — supports overall success", planets=[_saham_lord])
            elif _sl_house in _DUSTHANA_HOUSES:
                _add_neg(f"Karyasiddhi Saham falls in H{_saham_house}, lord {_saham_lord} in dusthana (H{_sl_house}) — obstructs overall success", planets=[_saham_lord])

    # Rule 25 (2026-07-19 audit, 2nd pass — compounding-affliction fixes).
    # Several individually-weak signals become classically much more severe
    # when they stack on the SAME planet or the SAME house (lagna). Firing
    # them only as separate equal-weight bullets (the old behaviour) buries
    # this; make the compounding explicit as its own note. Left untagged
    # (structural) since the underlying planet(s) are already tagged by
    # their individual rules above — this just adds the "these combine"
    # signal without re-counting the same planet a second time.
    if _lagna_lord_in_dusthana and _lagna_malefics:
        _add_neg(
            f"Compounded lagna affliction: lagna lord {lagna_lord} sits in a dusthana AND the lagna "
            f"itself is occupied by malefic(s) {', '.join(_lagna_malefics)} — the querent's position is "
            f"afflicted at both the lord level and the occupancy level; this is a materially stronger "
            f"denial signal than either alone"
        )
    if len(_combust_flagged) >= 2:
        _add_neg(
            f"Compounded combustion: {len(_combust_flagged)} significators ({', '.join(sorted(_combust_flagged))}) "
            f"are simultaneously combust — losing multiple significators to the Sun's proximity at once is a "
            f"materially stronger weakening than any one combustion alone; the chart's capacity to independently "
            f"confirm the matter is structurally compromised"
        )
    _both_retro_and_combust = _combust_flagged & _retrograde_flagged
    for _p in sorted(_both_retro_and_combust):
        _add_neg(
            f"Compounded affliction on {_p}: retrograde AND combust simultaneously — two independent classical "
            f"weaknesses on the same planet, not two mild ones; treat {_p}'s signification as substantially, "
            f"not marginally, weakened"
        )

    # De-duplicated, first-seen-order afflicted-planet list (audit-fix):
    # collapse repeated mentions of the same planet across multiple rules
    # into a single entry, so downstream scoring/remedy logic treats "one
    # planet flagged four ways" as ONE affliction, not four independent
    # ones.
    afflicted_planets: List[str] = []
    for tags in neg_tags:
        for p in tags:
            if p not in afflicted_planets:
                afflicted_planets.append(p)

    def _distinct_signal_count(tag_lists: List[List[str]]) -> int:
        """Count independent 'signals' among a rule side (pos or neg):
        planet-tagged rules collapse by planet (repeated mentions of the
        same planet count once), while untagged/structural rules (Paksha,
        etc.) each count as their own independent signal since they aren't
        about a single planet's repeated affliction."""
        distinct_planets: set = set()
        structural_count = 0
        for tags in tag_lists:
            if tags:
                distinct_planets.update(tags)
            else:
                structural_count += 1
        return len(distinct_planets) + structural_count

    pos_signal_count = _distinct_signal_count(pos_tags)
    neg_signal_count = _distinct_signal_count(neg_tags)

    return pos, neg, tajika_note, afflicted_planets, pos_signal_count, neg_signal_count


# ---------------------------------------------------------------------------
# Tajika Ithasala / Isbaha (mutual application) — simplified
# ---------------------------------------------------------------------------

_TAJIKA_ASPECTS: List[Tuple[float, str]] = [
    (0.0, "conjunction"), (60.0, "sextile"), (90.0, "square"),
    (120.0, "trine"), (180.0, "opposition"),
]
# Simplified fixed orb (classical deeptamsa/combined-orb tables vary by
# planet pair and text; a uniform orb keeps this tractable and conservative).
_TAJIKA_ORB_DEG = 8.0


def _check_tajika_ithasala(
    chart: "PrashnaChart",
    planet_a: str,
    planet_b: str,
) -> Tuple[str, str]:
    """Simplified Tajika Ithasala/Isbaha check between two significators.

    Ithasala Yoga: the two planets are within orb of a major aspect AND
    closing the angular gap (mutual application) — classically means the
    matter signified WILL come to pass, because the "union" completes.

    Already-separating (the aspect has passed its exact point and the gap is
    widening) within orb: the connection has already peaked/is fading —
    treated as a mild negative ("support already crested").

    No aspect relationship within orb at all: classically this absence
    (Na-Ithasala) is itself informative — it means neither significator is
    reinforcing the other, so it is surfaced as a neutral caveat rather than
    silently omitted, but does not by itself move the pos/neg rule tally.

    Returns (note_text, polarity) where polarity is "positive"/"negative"/
    "neutral". note_text is "" if the required data (positions/speeds) is
    unavailable, so callers can skip cleanly.
    """
    pdata = chart.planets_d1
    speeds = chart.planet_speeds
    a = pdata.get(planet_a, {})
    b = pdata.get(planet_b, {})
    a_lon, b_lon = a.get("abs_degree"), b.get("abs_degree")
    a_speed, b_speed = speeds.get(planet_a), speeds.get(planet_b)
    if a_lon is None or b_lon is None:
        return "", "neutral"

    gap = abs(a_lon - b_lon) % 360.0
    gap = min(gap, 360.0 - gap)

    # Find nearest major aspect to the current gap
    nearest_aspect_deg, nearest_aspect_name = min(
        _TAJIKA_ASPECTS, key=lambda t: abs(gap - t[0])
    )
    orb_diff = abs(gap - nearest_aspect_deg)
    if orb_diff > _TAJIKA_ORB_DEG:
        return (
            f"No Ithasala (mutual application) between {planet_a} and {planet_b} — "
            f"neither significator reinforces the other; outcome not strongly confirmed by application",
            "neutral",
        )

    # Determine application vs separation using relative daily motion, if
    # both speeds are known. Convention: gap is closing (applying) if the
    # relative motion is reducing |a_lon - b_lon| toward the aspect point.
    if a_speed is None or b_speed is None:
        # Speeds unavailable — report the conjunction/aspect proximity but
        # can't determine application direction.
        return (
            f"{planet_a} and {planet_b} are within orb of a {nearest_aspect_name} "
            f"({orb_diff:.2f}° from exact) — application direction could not be determined (missing speed data)",
            "neutral",
        )

    relative_speed = a_speed - b_speed  # deg/day, signed
    # Signed angular position difference (not the folded 0-180 gap) — sign
    # tells us whether a_lon is ahead of or behind b_lon + aspect_deg.
    target = (b_lon + nearest_aspect_deg) % 360.0
    signed_diff = (target - a_lon + 540.0) % 360.0 - 180.0  # in [-180, 180)
    # If the relative speed is moving a_lon toward `target`, the gap is
    # applying (closing); this is a simplified proxy, not a rigorous
    # Tajika Ithasala deeptamsa calculation.
    applying = (signed_diff > 0 and relative_speed > 0) or (signed_diff < 0 and relative_speed < 0)

    if applying:
        return (
            f"Ithasala Yoga: {planet_a} (querent) and {planet_b} (quesited) are applying to a "
            f"{nearest_aspect_name} ({orb_diff:.2f}° from exact) — mutual application confirms the matter will come to pass",
            "positive",
        )
    else:
        return (
            f"{planet_a} and {planet_b} are separating from a {nearest_aspect_name} "
            f"({orb_diff:.2f}° past exact) — the connection has already crested; support is fading rather than building",
            "negative",
        )


def _check_manau_kambool(
    chart: "PrashnaChart",
    planet_a: str,
    planet_b: str,
    planet_signs: Dict[str, str],
) -> Tuple[str, str, List[str]]:
    """Simplified Manau Yoga / Kambool Yoga check (Prashna Marga 30-rule
    list, item 19-20).

    Only meaningful once Ithasala/Isbaha has already found planet_a and
    planet_b separating (Isbaha) — this checks whether a third planet
    positioned angularly between them can "carry" (transfer) the
    connection through anyway. If such a planet exists and is itself
    reasonably strong (not debilitated, not combust, not in an enemy
    sign), the matter is rescued (Manau Yoga, positive). If the only
    candidate transferring planet is weak, the rescue fails (Kambool
    Yoga failure) and the original separation stands (returns "", "neutral",
    [] so the Isbaha negative already recorded is left as the final word).

    This is a simplified approximation (no deeptamsa/speed-based transfer
    timing), not a rigorous reproduction of the classical technique.

    Returns (note_text, polarity, relevant_planets) — relevant_planets is
    the transferring planet (Manau) or the weak candidate(s) (Kambool
    failure), for structural affliction tagging by the caller.
    """
    pdata = chart.planets_d1
    a_lon = pdata.get(planet_a, {}).get("abs_degree")
    b_lon = pdata.get(planet_b, {}).get("abs_degree")
    if a_lon is None or b_lon is None:
        return "", "neutral", []

    # Shorter arc between a and b
    lo, hi = sorted([a_lon, b_lon])
    span_direct = hi - lo
    span_wrap = 360.0 - span_direct
    if span_direct <= span_wrap:
        lo_b, hi_b, wrap = lo, hi, False
    else:
        lo_b, hi_b, wrap = hi, lo, True  # arc goes through 0°/360°

    candidates = []
    for pname, pd in pdata.items():
        if pname in (planet_a, planet_b, "Rahu", "Ketu"):
            continue
        p_lon = pd.get("abs_degree")
        if p_lon is None:
            continue
        between = (lo_b <= p_lon <= hi_b) if not wrap else (p_lon >= lo_b or p_lon <= hi_b)
        if between:
            candidates.append(pname)

    if not candidates:
        return "", "neutral", []

    for pname in candidates:
        p_sign = pdata.get(pname, {}).get("sign", "")
        state = _planet_dignity_state(pname, p_sign, planet_signs)
        if state not in ("DEBILITATED", "ENEMY", "GREAT_ENEMY") and not _is_combust(pname, pdata):
            return (
                f"Manau Yoga: {pname} stands between {planet_a} and {planet_b} and is well-placed — "
                f"transfers/carries the connection through despite their separation (Isbaha rescued)",
                "positive",
                [pname],
            )

    return (
        f"Kambool Yoga failure: {', '.join(candidates)} stand between {planet_a} and {planet_b} but "
        f"are too weak (debilitated/enemy/combust) to carry the connection through — the separation (Isbaha) stands",
        "negative",
        candidates,
    )


# ---------------------------------------------------------------------------
# Timing estimate
# ---------------------------------------------------------------------------

_HORIZON_UNIT_DAYS = {"day": 1, "days": 1, "week": 7, "weeks": 7,
                       "month": 30, "months": 30, "year": 365, "years": 365}


def _parse_stated_horizon(question: str) -> str:
    """Extract the querent's own stated timeframe from the question text
    (e.g. "next 1 year", "within 3 months"), if any, for display alongside
    the astrologically-derived estimate (gap fix — the engine previously
    ignored this entirely and always used a hardcoded per-category unit).

    Returns a short display string like "1 year" or "" if none was found.
    """
    import re as _re
    if not question:
        return ""
    m = _re.search(
        r"(\d+)\s*(day|days|week|weeks|month|months|year|years)\b",
        question, flags=_re.IGNORECASE,
    )
    if not m:
        return ""
    return f"{m.group(1)} {m.group(2)}"


def _estimate_timing(
    chart: PrashnaChart,
    sigs: Dict[str, PrashnaSignificator],
    category: str,
    verdict: str,
    question: str = "",
) -> str:
    """
    Timing based on the Moon's applying aspect (degrees remaining to perfect
    it). Moon moves ~13.3°/day; the angular gap maps to a time unit:
      ≤ 7°  → express the gap in days   (gap × 1 day  per degree)
      ≤ 30° → express the gap in weeks  (gap / 7)
      > 30° → express the gap in months (gap / 30)

    For non-Moon categories (health, competition) we scale to the category's
    natural unit instead.

    2026-07-18: KP sub-lord-based timing has been removed entirely (along
    with the rest of the KP analysis). The fallback branch (no Moon
    application to time against) now gives an honest, category-scaled
    estimate rather than the previous "~1-3 days based on H{n} sub-lord
    activation" claim, which relied on KP logic that no longer exists here.

    `question`: the querent's own stated horizon (e.g. "next 1 year") is
    parsed out and appended for context/comparison, since the category's
    default timing unit previously ignored it entirely.
    """
    _horizon = _parse_stated_horizon(question)
    _horizon_note = f" (querent's stated horizon: ~{_horizon})" if _horizon else ""

    if verdict == "NO":
        return f"Not indicated within near term{_horizon_note}"

    moon_data = chart.planets_d1.get("Moon", {})
    moon_abs  = moon_data.get("abs_degree", 0)

    if chart.moon_applying_to:
        # BUGFIX: previously recomputed a straight Moon-to-planet conjunction
        # distance here, ignoring that the Moon may actually be applying by
        # sextile/square/trine/opposition (as detected in _check_moon_status).
        # That mismatch could report a wildly wrong timing (e.g. treating a
        # near-exact applying square as if it were a far-off conjunction).
        # Use the stored aspect-closing distance when available; only fall
        # back to the raw conjunction distance if it wasn't captured.
        if chart.moon_applying_aspect_deg is not None:
            diff = round(chart.moon_applying_aspect_deg, 2)
        else:
            applying_planet = chart.planets_d1.get(chart.moon_applying_to, {})
            target_abs      = applying_planet.get("abs_degree", moon_abs)
            diff = (target_abs - moon_abs) % 360
            if diff > 180:
                diff = 360 - diff
            diff = round(diff, 2)

        # Convert degrees to time units using classical KP rule
        if diff <= 7:
            display = round(diff, 1)
            unit = "days"
        elif diff <= 30:
            display = round(diff / 7, 1)
            unit = "weeks"
        else:
            display = round(diff / 30, 1)
            unit = "months"

        # Override to "hours" for same-day categories when gap is very small
        if diff <= 1 and category in ("health", "competition"):
            display = round(diff * 24, 0)
            unit = "hours"

        # gap fix (2026-07-19 audit, 2nd pass): the planet this estimate is
        # timed against can simultaneously be a DENIAL-house significator
        # (flagged as a negative classical rule elsewhere in the same
        # report) -- previously the timing line gave a confident-sounding
        # specific date with no indication that the same aspect it's based
        # on is also the reason the verdict was hedged/downgraded. Surface
        # that link explicitly instead of leaving the reader to notice the
        # same planet name in two unconnected sections.
        _timing_sig = sigs.get(chart.moon_applying_to)
        _denial_caveat = ""
        if _timing_sig and _timing_sig.deny_houses_touched:
            _denial_caveat = (
                f" — caution: {chart.moon_applying_to} is also a denial-house significator "
                f"(H{_timing_sig.deny_houses_touched[0]}), so this date times WHEN the matter resolves "
                f"one way or the other, not a guarantee it resolves favourably"
            )

        return f"~{display} {unit} (Moon {diff}° from {chart.moon_applying_to}){_horizon_note}{_denial_caveat}"

    # Fallback: no Moon application to time against, and (since KP analysis
    # has been removed) no sub-lord signal to lean on either. Give an
    # honest, category-scaled estimate rather than a confident short window
    # derived from a technique this module no longer uses.
    unit = _TIMING_UNIT.get(category, "months")
    return (
        f"No applying Moon aspect to time against — estimate based on {category.replace('_',' ')}'s "
        f"typical {unit}-scale horizon rather than a precise degree-based calculation{_horizon_note}"
    )


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
    sigs = _score_significators(sigs, category, chart.planets_d1)

    affirm_sigs = sorted([s for s in sigs.values() if s.score > 0],
                         key=lambda x: -x.score)
    deny_sigs   = sorted([s for s in sigs.values() if s.score < 0],
                         key=lambda x: x.score)

    result.affirm_significators = [s.planet for s in affirm_sigs[:5]]
    result.deny_significators   = [s.planet for s in deny_sigs[:3]]

    # 2. KP sub-lord analysis — REMOVED (2026-07-18, explicit user request).
    # Chart casting still computes chart.kp_sublords (cusp sub-lords) as
    # before and that data is still shown as raw chart data in the HTML
    # ("KP Cusp Sub-Lords" table / per-planet nakshatra sub-lord column) —
    # only the *interpretive use* of KP sub-lords for the verdict (joint
    # cusp affirm/deny check, KP score weighting, "KP Sub-Lord Analysis"
    # card) has been removed. kp_affirms/kp_denies are kept as inert False
    # values purely so _build_factors()'s signature doesn't need changing;
    # they no longer influence the verdict.
    kp_affirms, kp_denies = False, False

    # 3. Classical rules
    (pos_rules, neg_rules, tajika_note, afflicted_planets,
     pos_signal_count, neg_signal_count) = _classical_rules(chart, sigs, category)
    result.classical_rules_fired = pos_rules   # A-3: positive rules only
    result.denial_rules_fired    = neg_rules   # A-3: negative rules separate
    result.tajika_aspect_note    = tajika_note
    result.afflicted_planets     = afflicted_planets

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

    # 4b (gap fix): precision caveat when the Moon is within a razor-thin arc
    # of its sign end. The Void-of-Course test only has that remaining arc
    # to search for an applying aspect, so a sub-degree ayanamsa/ephemeris
    # drift can flip the VoC verdict outright — flag it rather than stating
    # VoC status with unwarranted confidence.
    _moon_abs = chart.planets_d1.get("Moon", {}).get("abs_degree", 0.0)
    _moon_remaining_deg = (math.floor(_moon_abs / 30) + 1) * 30 - _moon_abs
    if _moon_remaining_deg < 0:
        _moon_remaining_deg += 360
    if _moon_remaining_deg < 1.5:
        result.moon_status_caveat = (
            f"Moon is only {_moon_remaining_deg:.2f}° from the end of its sign — this "
            f"Void-of-Course/applying determination is sensitive to sub-degree ayanamsa "
            f"or ephemeris precision and should be treated with caution"
        )

    # 5. Verdict engine
    affirm_score = sum(s.score for s in affirm_sigs)
    deny_score   = abs(sum(s.score for s in deny_sigs))

    # KP scoring contribution — REMOVED along with the rest of the KP
    # analysis (2026-07-18, explicit user request). No kp_affirm_pts/
    # kp_deny_pts term is added to total_affirm/total_deny below anymore.
    moon_affirm_pts = 0
    moon_deny_pts   = 0
    if chart.moon_void:
        # gap fix: Moon Void-of-Course is one of the strongest classical
        # denial signals (near-automatic non-fruition per Bhrigu/Tajika
        # unless mitigated) — raised from 2 to 3 so it can no longer be
        # trivially outweighed by a single Panchang bonus, matching the
        # weight given to a full KP joint denial above.
        moon_deny_pts = 3
    elif chart.moon_applying_to in _NATURAL_BENEFICS:
        moon_affirm_pts = 1.5
    elif chart.moon_applying_to in _NATURAL_MALEFICS:
        moon_deny_pts   = 1

    # P-2: Hora lord corroboration — adjust affirm/deny totals using Panchang quality.
    # The hora lord at query time strengthens or weakens the evidence if it
    # significates a primary house for this category.
    _panchang_affirm_pts = 0.0
    _panchang_deny_pts   = 0.0
    if chart.panchang:
        try:
            from jyotish.panchang import panchang_quality as _pg_quality
            _primary_hs = list(_CATEGORY_HOUSES.get(category, {}).get("primary", []))
            _pg_score, _pg_pos, _pg_neg = _pg_quality(
                chart.panchang, _primary_hs, chart.house_lords
            )
            result.panchang          = chart.panchang
            result.panchang_score    = _pg_score
            result.panchang_positive = _pg_pos
            result.panchang_negative = _pg_neg
            # Hora/Panchang contributes up to ±1.5 pts on the ratio tally
            if _pg_score >= 0.65:
                _panchang_affirm_pts = (_pg_score - 0.5) * 3.0
                pos_rules.append(
                    f"Panchang quality {round(_pg_score * 100)}% — "
                    f"hora lord {chart.panchang.get('hora_lord','')} supports the query"
                )
                pos_signal_count += 1  # Panchang is its own independent signal
            elif _pg_score <= 0.40:
                _panchang_deny_pts = (0.5 - _pg_score) * 3.0
                neg_rules.append(
                    f"Panchang quality {round(_pg_score * 100)}% — "
                    f"query timing has {chart.panchang.get('malefic_count', 0)} inauspicious elements"
                )
                neg_signal_count += 1
        except Exception as _pg_err:
            import logging as _pg_log
            _pg_log.getLogger("jyotish_engine_v11_0").debug(
                "P-2 panchang_quality skipped: %s", _pg_err
            )

    # gap fix (audit finding #1): previously used len(pos_rules)*0.5 /
    # len(neg_rules)*0.5 -- a flat per-rule-STRING term. After the 30-rule
    # expansion, a single afflicted planet can generate 3-4 separate rule
    # strings (dusthana + enemy-sign + combust + graha-yuddha), so that
    # term grew unboundedly and began dominating/swamping the significator
    # and Panchang scores it was originally calibrated against (~10 rules).
    # Now uses pos_signal_count/neg_signal_count from _classical_rules(),
    # which collapse repeated mentions of the SAME planet into one signal
    # (structural/non-planet-specific rules like Paksha still count
    # individually), and caps the contribution so the magnitude stays in
    # the same ballpark as the original ~10-rule-era calibration.
    _RULE_SIGNAL_CAP = 8
    total_affirm = affirm_score + moon_affirm_pts + min(pos_signal_count, _RULE_SIGNAL_CAP) * 0.5 + _panchang_affirm_pts
    total_deny   = deny_score   + moon_deny_pts   + min(neg_signal_count, _RULE_SIGNAL_CAP) * 0.5 + _panchang_deny_pts
    total        = total_affirm + total_deny
    ratio        = (total_affirm / total) if total > 0 else 0.5

    # C-2: per-category YES/NO thresholds — high-stakes categories (marriage, pregnancy,
    # legal, competition) require stronger evidence before issuing a firm YES or NO.
    _HIGH_STAKES = {"marriage", "pregnancy", "legal", "competition"}
    if category in _HIGH_STAKES:
        _yes_thr, _no_thr = 0.72, 0.28   # need stronger signal for definitive verdict
    else:
        _yes_thr, _no_thr = 0.68, 0.32   # default thresholds

    if ratio >= _yes_thr:
        result.verdict    = "YES"
        result.confidence = round(min(ratio, 0.95), 2)
        result.verdict_leaning = "YES"
    elif ratio <= _no_thr:
        result.verdict    = "NO"
        result.confidence = round(min(1 - ratio, 0.95), 2)
        result.verdict_leaning = "NO"
    elif 0.45 <= ratio <= 0.55 and chart.moon_void:
        result.verdict    = "UNCERTAIN"
        result.confidence = 0.5
        result.verdict_leaning = "YES" if ratio >= 0.5 else "NO"
    elif ratio > 0.55:
        result.verdict    = "CONDITIONAL"
        result.confidence = round(ratio, 2)
        result.verdict_leaning = "YES"
    else:
        # gap fix (2026-07-19 audit, 2nd + 3rd pass): ratio here is <= 0.55
        # -- this branch used to still say verdict="CONDITIONAL" (reads as
        # yes-leaning) while silently reporting confidence = round(1 -
        # ratio, 2), the NO-side confidence, under the same "Conditionally
        # Favourable" label. That's exactly how two real different charts
        # both surfaced as "CONDITIONAL, 45%"/"65%" while actually leaning
        # NO.
        #
        # 3rd-pass correction: the first fix here hardcoded
        # verdict_leaning="NO" for this entire branch, but the branch covers
        # ratio in (_no_thr, 0.55] -- which INCLUDES ratio in [0.5, 0.55],
        # where more than half the evidence actually favours YES (just not
        # enough to clear the 0.55 "confident CONDITIONAL-YES" cutoff). That
        # produced exactly the contradiction a real run just surfaced:
        # "Confidence 45%" + "Plain answer: YES / leaning YES" together,
        # which is nonsensical -- 45% confidence in NO cannot also be a YES
        # lean. The lean must be decided by ratio vs. 0.5 (the only
        # meaningful yes/no midpoint), independent of the 0.55 threshold
        # that only decides how firmly CONDITIONAL is worded.
        result.verdict = "CONDITIONAL"
        if ratio >= 0.5:
            result.confidence      = round(ratio, 2)
            result.verdict_leaning = "YES"
        else:
            result.confidence      = round(1 - ratio, 2)
            result.verdict_leaning = "NO"

    # Strict binary reading of the raw ratio, independent of the hedged
    # CONDITIONAL/UNCERTAIN wording, for callers who want a plain yes/no.
    result.binary_answer = "YES" if ratio >= 0.5 else "NO"

    conf = result.confidence
    result.confidence_band = ("STRONG" if conf >= 0.75 else
                              "MODERATE" if conf >= 0.55 else "WEAK")

    # 5b (gap fix — internal conflict / contradiction detection). Checks
    # whether the aggregate YES/CONDITIONAL ratio is being contradicted by
    # multiple independent negative classical signals fired above
    # (dusthana lagna lord, enemy-sign/combust significators, Moon VoC,
    # retrograde significator, Tajika separation) — a report could say
    # "YES, 69%" right next to unrelated negative classical rules with no
    # reconciling note, and remedies would still say "proceed with
    # confidence". Count afflictions and, when they outnumber the
    # arithmetic verdict's support, surface a visible caution and (if
    # severe) downgrade YES to CONDITIONAL. (No longer includes any KP
    # signal — KP analysis has been removed entirely.)
    #
    # gap fix (audit finding #2/#3): previously re-parsed denial_rules_fired
    # text against a fixed _AFFLICTION_MARKERS substring list, which (a)
    # went stale as new rules were added with phrasings the list didn't
    # recognise (e.g. Rule 4's plain "enemy" label, Virodhargala, Saham
    # "obstructs"), silently undercounting real afflictions, and (b) counted
    # every rule-STRING once, so a single badly-placed planet firing 3-4
    # separate rules (dusthana + enemy-sign + combust) alone satisfied the
    # "≥3 independent afflictions" downgrade threshold even though it isn't
    # 3 independent signals. Now uses result.afflicted_planets, which
    # _classical_rules() already de-duplicated by planet at the point each
    # rule fired, plus 1 for each remaining structural (non-planet-specific)
    # negative rule such as Krishna Paksha or a general Virodhargala note
    # with no occupants -- giving a true count of distinct classical
    # afflictions rather than distinct sentences.
    _structural_neg_count = neg_signal_count - len(afflicted_planets)
    _affliction_count = len(afflicted_planets) + max(_structural_neg_count, 0)

    if result.verdict in ("YES", "CONDITIONAL") and _affliction_count >= 2:
        result.internal_conflict_notes.append(
            f"Verdict leans {result.verdict} on the aggregate score/ratio, but {_affliction_count} "
            f"independent classical affliction(s) fired against it (see Classical Rules below) — "
            f"treat this as a hedged reading, not an unqualified yes."
        )
        if result.verdict == "YES" and _affliction_count >= 3:
            result.internal_conflict_notes.append(
                "Verdict downgraded from YES to CONDITIONAL: the volume of independent negative "
                "classical signals (e.g. void Moon, dusthana/enemy/combust significators, retrograde "
                "significator) outweighs a purely arithmetic YES from the significator/Panchang tally."
            )
            result.verdict    = "CONDITIONAL"
            # gap fix (2026-07-19 audit): this used to be a flat
            # `min(result.confidence, 0.65)` ceiling, which meant every
            # downgraded chart landed on the exact same 65% regardless of
            # how many afflictions fired or how strongly the raw ratio had
            # favoured YES -- two genuinely different charts (e.g. 3
            # afflictions vs. 6) both printed "CONDITIONAL, 65%", which is
            # what actually gets reported here, not a real distinguishing
            # confidence value. Replace the fixed ceiling with a ceiling
            # that scales down with the affliction count: each affliction
            # beyond the 3-affliction downgrade threshold shaves further
            # off the cap, floored at 0.45 (WEAK band) so confidence never
            # implies false precision, and never raised above the
            # pre-downgrade value.
            _excess_afflictions = max(_affliction_count - 3, 0)
            _downgrade_ceiling = max(0.65 - 0.05 * _excess_afflictions, 0.45)
            result.confidence = round(min(result.confidence, _downgrade_ceiling), 2)
            result.confidence_band = "MODERATE" if result.confidence >= 0.55 else "WEAK"

            # gap fix (2026-07-19 audit, 3rd pass): a real run surfaced this
            # exact case -- the downgrade ceiling floors at 0.45, which is
            # BELOW 50%, but result.verdict_leaning was set to "YES" back
            # when the raw ratio first classified as YES and this block
            # never revisited it. That produced "Confidence 45% / leaning
            # YES / Plain answer YES" together -- self-contradictory, since
            # confidence in a lean cannot legitimately be under 50%. Once
            # the affliction pile-up is severe enough to drag confidence
            # below the halfway point, the honest reading has flipped: the
            # classical negatives now outweigh the arithmetic yes, so the
            # lean and binary answer must flip with it, expressed as
            # confidence in that NO lean instead.
            if result.confidence < 0.5:
                result.confidence      = round(1 - result.confidence, 2)
                result.verdict_leaning = "NO"
                result.binary_answer   = "NO"
                result.confidence_band = "MODERATE" if result.confidence >= 0.55 else "WEAK"

    # 6. Timing
    result.timing_estimate = _estimate_timing(
        chart, sigs, category, result.verdict,
        question=question,
    )

    # 7. Planet summary (for HTML)
    _planet_signs_for_summary = {p: d.get("sign", "") for p, d in chart.planets_d1.items()}
    for pname, pdata in chart.planets_d1.items():
        dig = _planet_dignity(pname, pdata.get("sign", ""), _planet_signs_for_summary)
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
    """Build factor cards list for HTML rendering.

    kp_affirms/kp_denies are accepted for call-site compatibility but are
    now always False,False — the "KP Sub-Lord" factor card has been removed
    entirely (2026-07-18, explicit user request); KP analysis no longer
    exists in this module.
    """
    factors = []
    primary_h = _PRIMARY_HOUSE.get(category, 10)
    # gap fix (2026-07-19 audit, real-run finding): the Lagna Lord / H-lord
    # factor cards below called _planet_dignity(planet, sign) with NO
    # planet_signs context, so mutual (two-way) Great Friend/Great Enemy
    # relationships could never be detected here -- only the one-way
    # "natural friendship" fallback. The Planetary Positions table (further
    # down, via result.planets_summary) DOES pass the full chart's
    # planet_signs map, so the exact same planet in the exact same sign
    # could show "Friend" on this card and "Great Friend" in the table --
    # which is exactly what a real report surfaced. Compute the same
    # chart-wide sign map here and reuse it for every dignity lookup in
    # this function so both sections of the report always agree.
    _factor_planet_signs = {p: d.get("sign", "") for p, d in chart.planets_d1.items()}
    _POSITIVE_DIGNITIES = {"Exalted", "Own", "Moolatrikona", "Great Friend", "Friend", "Neecha Bhanga"}
    _NEGATIVE_DIGNITIES  = {"Debilitated", "Enemy", "Great Enemy"}

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
    _ll_dignity = _planet_dignity(lagna_lord, ll_data.get("sign", ""), _factor_planet_signs)
    factors.append({
        "name": "Lagna Lord",
        "value": f"{lagna_lord} in H{ll_data.get('house', '?')} ({ll_data.get('sign', '?')})",
        "detail": f"Dignity: {_ll_dignity}" if _ll_dignity else "Dignity: Neutral (no special strength or weakness)",
        "polarity": ("positive" if _ll_dignity in _POSITIVE_DIGNITIES
                     else ("negative" if _ll_dignity in _NEGATIVE_DIGNITIES else "neutral")),
        "weight": "MEDIUM",
    })

    # Primary house lord card
    ph_lord   = chart.house_lords.get(str(primary_h), "")
    phl_data  = chart.planets_d1.get(ph_lord, {})
    # gap fix (2026-07-19 audit, real-run finding): fell back to a KP
    # sub-lord string when _planet_dignity() returned "" -- but "" here
    # just means the planet is in a NEUTRAL sign (no special dignity label
    # to show), not that dignity is unavailable. That silently put a
    # "Sub-lord: Ketu" line back into the Key Factors card despite KP
    # analysis having been removed from this module entirely per an
    # earlier explicit request. Use a plain "Neutral dignity" label
    # instead -- no KP machinery involved. Also now passes the same
    # chart-wide planet_signs map as the Lagna Lord card above and the
    # Planetary Positions table, so all three agree on Friend vs. Great
    # Friend / Enemy vs. Great Enemy for the same planet+sign.
    _phl_dignity = _planet_dignity(ph_lord, phl_data.get("sign", ""), _factor_planet_signs)
    factors.append({
        "name": f"H{primary_h} Lord (Query House)",
        "value": f"{ph_lord} in H{phl_data.get('house', '?')} ({phl_data.get('sign', '?')})",
        "detail": f"Dignity: {_phl_dignity}" if _phl_dignity else "Dignity: Neutral (no special strength or weakness)",
        "polarity": ("positive" if _phl_dignity in _POSITIVE_DIGNITIES
                     else ("negative" if _phl_dignity in _NEGATIVE_DIGNITIES else "neutral")),
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


# ---------------------------------------------------------------------------
# Planet-specific graha-shanti remedies (2026-07-19 addition)
# ---------------------------------------------------------------------------
# Standard graha-shanti remedy tradition (day of worship, mantra/deity, dana
# item) that classical dharmashastra/muhurta compendia such as Nirnaya
# Sindhu, Dharma Sindhu, and the Shanti Kaustubha/Ratnakara texts codify for
# planetary affliction generally. This is a best-effort synthesis of that
# widely-attested tradition, not a verbatim reproduction of any single
# source text (those texts are untranslated Sanskrit and not available to
# quote directly here) -- applied per-planet, dynamically, to whichever
# grahas are actually flagged as afflicted in a given chart, rather than a
# fixed category boilerplate.
_PLANET_REMEDIES: Dict[str, str] = {
    "Sun":     "Sun afflicted: Aditya Hrudayam recitation or Surya Namaskar at sunrise; donate wheat/jaggery on Sundays",
    "Moon":    "Moon afflicted: Chandra Graha Shanti — Monday fasting, white-item dana (rice, milk, silver), Chandra mantra (\"Om Som Somaya Namah\") japa",
    "Mars":    "Mars afflicted: Hanuman Chalisa on Tuesdays; donate red lentils or red cloth; Mangal Graha Shanti if severe",
    "Mercury": "Mercury afflicted: Budha Graha Shanti — Wednesday fasting, green-item dana (moong dal, green cloth), Vishnu Sahasranama or Budha mantra japa",
    "Jupiter": "Jupiter afflicted: Guru Graha Shanti — Thursday fasting, yellow-item dana (turmeric, chana dal, yellow cloth) to a teacher/Brahmin, Guru Beeja mantra (\"Om Gram Greem Graum Sah Gurave Namah\") japa",
    "Venus":   "Venus afflicted: worship Lakshmi on Fridays; donate white/light-colored items; Venus mantra (\"Om Shum Shukraya Namah\") japa",
    "Saturn":  "Saturn afflicted: Shani Graha Shanti — Saturday fasting, donate black sesame/mustard oil/iron; Hanuman Chalisa (Saturn responds to Hanuman worship classically)",
    "Rahu":    "Rahu afflicted: Durga Saptashati recitation or Rahu Beeja mantra japa on Saturdays; donate black sesame or mustard oil — pacification/obstruction-removal rather than empowerment",
    "Ketu":    "Ketu afflicted: worship Ganesha; donate multi-colored/blanket items on Tuesdays; Ketu mantra japa for obstruction removal",
}


def _suggest_remedies(result: PrashnaResult, category: str) -> List[str]:
    """Return contextual remedy suggestions based on verdict, category, AND
    (2026-07-19) the specific grahas actually flagged as afflicted in the
    fired classical rules — applicable to any category/question, not just
    career_employment, since remedies are now driven by which planets
    misbehave rather than a hardcoded per-category list alone.

    gap fix: previously any verdict == "YES" short-circuited straight to a
    blanket "proceed with confidence" message, even when the same report's
    Classical Rules panel had just listed multiple negative signals (void
    Moon, dusthana lagna lord, retrograde significator, etc.) — a direct,
    visible contradiction between the remedy tone and the evidence right
    above it. Remedies are now hedged whenever result.internal_conflict_notes
    is non-empty (populated in analyze_prashna's conflict-detection step),
    regardless of the final verdict label.
    """
    if result.verdict == "YES" and not result.internal_conflict_notes:
        return ["Proceed with confidence; time the event when Moon transits a benefic nakshatra",
                "Begin the effort on a Thursday (Jupiter's day) or Friday (Venus's day) for best support"]

    remedies = []
    if result.internal_conflict_notes:
        remedies.append(
            "Verdict is contradicted by multiple classical afflictions (see Classical Rules) — "
            "treat as a conditional yes: mitigate the afflictions below before acting, don't proceed on confidence alone"
        )
    if result.moon_void:
        remedies.append("Delay action until Moon moves to the next sign and applies to a benefic")

    # Dynamic, affliction-driven planet remedies (up to 3 planets, in the
    # order they first appear among the fired denial rules).
    # gap fix (audit finding #4/#5): previously re-derived this list by
    # substring-scanning rule text (_extract_afflicted_planets), which
    # could misattribute a planet merely *named* in a sentence about a
    # different planet's problem (e.g. Virodhargala names both the
    # supporting and countering planets). result.afflicted_planets is now
    # built structurally by _classical_rules() at the point each rule
    # fires, so only genuinely afflicted planets appear here.
    afflicted_planets = result.afflicted_planets
    for planet in afflicted_planets[:3]:
        if planet == "Moon" and result.moon_void:
            continue  # already covered by the moon_void-specific line above
        line = _PLANET_REMEDIES.get(planet)
        if line:
            remedies.append(line)

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
    # Allow extra slots when a conflict caveat and/or planet-specific
    # remedies are present, so dynamic content doesn't crowd out category
    # remedies entirely.
    cap = 4 + (1 if result.internal_conflict_notes else 0) + min(len(afflicted_planets), 3)
    return remedies[:cap]


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


# ---------------------------------------------------------------------------
# South Indian chart box (2026-07-19, explicit request)
# ---------------------------------------------------------------------------

# Fixed South-Indian layout: signs occupy fixed screen positions (they never
# rotate with the Lagna, unlike North Indian charts) in this exact 4x4
# arrangement, reading clockwise from the top-left cell. The two middle rows'
# inner two cells are merged into one central title block.
_SOUTH_INDIAN_GRID = [
    ["Pisces",      "Aries",  "Taurus", "Gemini"],
    ["Aquarius",    None,     None,     "Cancer"],
    ["Capricorn",   None,     None,     "Leo"],
    ["Sagittarius", "Scorpio","Libra",  "Virgo"],
]

_PLANET_ABBR = {
    "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
    "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke",
}


def _south_indian_chart_html(result: PrashnaResult) -> str:
    """Render the Prashna D1 chart as a fixed-sign South Indian box chart.

    Each of the 12 boxes is a permanently assigned sign (Aries always
    top-row-2nd, etc.); planets are placed in whichever box matches their
    own sign, and the Lagna box is highlighted with an "Asc" marker --
    unlike the North Indian diamond style (where house 1 is always the
    fixed center-top diamond and signs rotate around it), which this engine
    did not previously offer at all.
    """
    def _h(s):
        import html as _hl
        return _hl.escape(str(s or ""))

    chart = result.chart
    if not chart:
        return ""

    # {sign: [planet_abbr, ...]}
    sign_occupants: Dict[str, List[str]] = {s: [] for s in _SIGN_NUM}
    for pname, pd in chart.planets_d1.items():
        sign = pd.get("sign", "")
        if sign in sign_occupants:
            abbr = _PLANET_ABBR.get(pname, pname[:2])
            if pd.get("retrograde"):
                abbr += "℞"
            sign_occupants[sign].append(abbr)

    lagna_sign = result.lagna_sign

    cells_html = []
    for row in _SOUTH_INDIAN_GRID:
        for sign in row:
            if sign is None:
                continue
            house_num = ((_SIGN_NUM[sign] - _SIGN_NUM.get(lagna_sign, 1)) % 12) + 1
            occupants = sign_occupants.get(sign, [])
            is_lagna  = (sign == lagna_sign)
            border    = "border:2px solid #79c0ff;" if is_lagna else "border:1px solid #30363d;"
            bg        = "background:rgba(121,192,255,.08);" if is_lagna else "background:#0d1117;"
            asc_tag   = "<div style='position:absolute;top:2px;left:4px;font-size:9px;color:#79c0ff;font-weight:700'>ASC</div>" if is_lagna else ""
            cells_html.append(
                f"<div style='grid-area:{sign};{border}{bg}border-radius:4px;padding:6px;"
                f"position:relative;min-height:64px;display:flex;flex-direction:column;justify-content:space-between'>"
                f"{asc_tag}"
                f"<div style='font-size:9px;color:#8b949e;text-align:right'>H{house_num}</div>"
                f"<div style='font-size:10px;color:#6e7681;text-align:center'>{_h(sign)}</div>"
                f"<div style='font-size:12px;color:#e6edf3;text-align:center;font-weight:600;line-height:1.4'>"
                f"{'&nbsp;'.join(_h(o) for o in occupants) or ''}</div>"
                f"</div>"
            )

    # gap fix (2026-07-19 audit, real-run finding): grid-template-areas
    # values are themselves double-quoted strings per the CSS spec (each
    # row is "sign1 sign2 sign3 sign4"). The previous version embedded that
    # value directly inside an HTML style="..." attribute -- also
    # double-quoted -- so the FIRST embedded quote silently terminated the
    # attribute early and the browser treated everything after it as raw
    # (broken/garbled) markup instead of CSS. Moved the grid-template-areas
    # declaration into a real <style> block with a dedicated class instead
    # of an inline attribute, which sidesteps the quoting collision
    # entirely (CSS inside <style> is never HTML-attribute-quoted).
    grid_template_areas = "\n".join(
        "\"" + " ".join(sign if sign else "center" for sign in row) + "\""
        for row in _SOUTH_INDIAN_GRID
    )

    return f"""
<div class="card">
  <h3 style="margin-bottom:10px">South Indian Chart (D1 — Rasi)</h3>
  <style>
    .si-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      grid-template-rows: repeat(4, 1fr);
      grid-template-areas:
        {grid_template_areas};
      gap: 3px; max-width: 420px; margin: 0 auto;
    }}
  </style>
  <div class="si-grid">
    {"".join(cells_html)}
    <div style="grid-area:center;display:flex;align-items:center;justify-content:center;
                text-align:center;font-size:11px;color:#8b949e;padding:8px">
      <div>
        <div style="font-size:13px;font-weight:700;color:#e6edf3">{_h(result.category.replace('_',' ').title())}</div>
        <div style="margin-top:4px">Asc: <b style="color:#79c0ff">{_h(lagna_sign)}</b></div>
        <div style="margin-top:2px">{_h(result.moment)}</div>
      </div>
    </div>
  </div>
  <div style="font-size:10px;color:#6e7681;margin-top:10px;text-align:center">
    Fixed-sign layout — signs never rotate; ASC marks the Lagna box. Each box's top-right label is its house number from Lagna.
  </div>
</div>"""


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
    # gap fix: dignity labels now include Friend/Great Friend/Enemy/Great
    # Enemy/Moolatrikona/Neecha Bhanga (see _planet_dignity), so the color
    # mapping must recognise all of them, not just Exalted/Own/Debilitated —
    # otherwise e.g. an enemy-sign placement would render in the default
    # (uncolored) style, silently hiding the affliction again.
    _POSITIVE_DIGNITY_LABELS = {"Exalted", "Own", "Moolatrikona", "Great Friend", "Friend"}
    _NEGATIVE_DIGNITY_LABELS = {"Debilitated", "Enemy", "Great Enemy"}

    def _house_position_label(h: int) -> str:
        if h in _KENDRA_HOUSES: return "Kendra"
        if h in _TRIKONA_HOUSES: return "Trikona"
        if h in _DUSTHANA_HOUSES: return "Dusthana"
        if h in _UPACHAYA_HOUSES: return "Upachaya"
        return "—"

    planet_rows = []
    for pname, pd in result.planets_summary.items():
        retro = " ℞" if pd.get("retrograde") else ""
        dig   = pd.get("dignity", "")
        dig_style = ("color:#3fb950" if dig in _POSITIVE_DIGNITY_LABELS else
                     "color:#f85149" if dig in _NEGATIVE_DIGNITY_LABELS else "")
        _house = pd.get("house") or 0
        _house_pos = _house_position_label(_house)
        _house_lord = result.house_lords.get(str(_house), "")
        # gap fix (2026-07-19 audit, screen-real-estate pass): every row
        # repeated the same Lagna sign (it's a chart-level constant, not a
        # per-planet fact), burning a whole column's width to say the exact
        # same thing 9 times. It's already shown once in the header meta
        # chip ("⬆ Lagna: ..."); dropped from the per-row table so the
        # remaining columns (esp. Nakshatra/Dignity) get more breathing room.
        planet_rows.append(
            f"<tr>"
            f"<td><b>{_h(pname)}{retro}</b></td>"
            f"<td>{_h(pd.get('sign',''))}</td>"
            f"<td style='text-align:right'>{pd.get('degree',0):.2f}°</td>"
            f"<td>H{_house}</td>"
            f"<td style='font-size:11px'>{_h(pd.get('nakshatra',''))}</td>"
            f"<td style='{dig_style};font-size:11px'>{_h(dig) or 'Neutral'}</td>"
            f"<td style='font-size:11px'>{_h(_house_pos)}</td>"
            f"<td style='font-size:11px'>{_h(_house_lord)}</td>"
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

    # gap fix (2026-07-19 audit, screen-real-estate pass): positive and
    # negative classical rules used to be interleaved into ONE long vertical
    # <ul> (often 15-20+ items after the 30-rule expansion), forcing the
    # reader to scan a single narrow column and distinguish rows purely by
    # text colour. Rendered as two side-by-side sub-lists instead (Supports
    # / Opposes) -- same information, roughly half the vertical scroll, and
    # the pos-vs-neg split is now structural, not just colour-coded.
    pos_rules_html = "".join(f"<li>{_h(r)}</li>" for r in result.classical_rules_fired) or "<li style='color:#8b949e;list-style:none'>None fired</li>"
    neg_rules_html = "".join(f"<li>{_h(r)}</li>" for r in result.denial_rules_fired) or "<li style='color:#8b949e;list-style:none'>None fired</li>"

    # Remedies
    remedy_html = ""
    for rem in result.remedy_suggestions:
        remedy_html += f"<li style='margin-bottom:6px'>{_h(rem)}</li>"

    # gap fix: visible caution banner when the aggregate verdict is
    # contradicted by multiple independent negative classical signals —
    # previously a report could say "YES, 69%" with three negative rules
    # listed right below it and no reconciling note anywhere on the page.
    conflict_banner_html = ""
    if result.internal_conflict_notes:
        _notes_html = "".join(f"<li style='margin-bottom:4px'>{_h(n)}</li>" for n in result.internal_conflict_notes)
        conflict_banner_html = (
            "<div style='background:rgba(248,81,73,.10);border:1px solid rgba(248,81,73,.5);"
            "border-radius:8px;padding:12px 16px;margin-bottom:16px;'>"
            "<b style='color:#f85149'>⚠ Verdict/Evidence Conflict: </b>"
            f"<ul style='font-size:13px;line-height:1.6;margin-top:6px'>{_notes_html}</ul>"
            "</div>"
        )

    # (KP joint-cusp breakdown removed along with the rest of KP analysis.)

    # House lords table
    house_lords_rows = ""
    for i in range(1, 13):
        lord = result.house_lords.get(str(i), "—")
        house_lords_rows += f"<tr><td>H{i}</td><td>{_h(lord)}</td></tr>"

    south_indian_html = _south_indian_chart_html(result)

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
  /* gap fix (2026-07-19 audit, screen-real-estate pass): previously no
     max-width container -- on a wide monitor the page just stretched
     edge-to-edge, making already-long rule sentences run the full screen
     width (bad readability) while never using that width for anything
     structural (e.g. more columns). A capped, centred container plus wider
     multi-column breakpoints lets the layout actually use extra horizontal
     space for more columns instead of just longer lines. */
  .container {{ max-width: 1440px; margin: 0 auto; }}
  h1 {{ font-size: 22px; font-weight: 700; color: #e6edf3; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; font-weight: 600; color: #8b949e; text-transform: uppercase;
        letter-spacing: .05em; margin: 24px 0 12px; border-bottom: 1px solid #21262d;
        padding-bottom: 6px; }}
  h3 {{ font-size: 14px; font-weight: 600; color: #c9d1d9; margin-bottom: 8px; }}
  .subtitle {{ color: #8b949e; font-size: 13px; margin-bottom: 24px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  /* Dashboard row: factor cards | rules (supports+opposes) | remedies.
     Rules gets the most width since it holds two sub-columns of its own. */
  .grid-dashboard {{ display: grid; grid-template-columns: 1fr 1.6fr 1fr; gap: 16px; align-items: start; }}
  /* Chart row: planetary-positions table (wide) beside the compact
     12-row house-lords table (narrow) instead of two full-width tables
     stacked vertically -- the house-lords table alone in a full-width row
     used to leave most of the row empty. */
  .grid-chart {{ display: grid; grid-template-columns: 2.4fr 1fr; gap: 16px; align-items: start; }}
  .rules-split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  @media (max-width: 1100px) {{ .grid-dashboard, .grid-chart {{ grid-template-columns: 1fr; }} }}
  @media (max-width: 700px) {{ .grid-2, .grid-3, .rules-split {{ grid-template-columns: 1fr; }} }}
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
  .rules-col h3 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 8px; }}
  .rules-col ul {{ font-size: 12.5px; line-height: 1.55; padding-left: 18px; }}
  .rules-col.supports h3 {{ color: #3fb950; }}
  .rules-col.supports li {{ color: #d8f5df; margin-bottom: 5px; }}
  .rules-col.opposes h3 {{ color: #f85149; }}
  .rules-col.opposes li {{ color: #fbd9d6; margin-bottom: 5px; }}
  footer {{ text-align: center; color: #30363d; font-size: 11px; margin-top: 40px; }}
</style>
</head>
<body>
<div class="container">
<h1>Prashna (Horary) — {_h(cat_label)}</h1>
<div class="subtitle">
  <span class="meta-chip">🕐 {_h(result.moment)}</span>
  <span class="meta-chip">📍 {_h(result.city) or 'Location provided'}</span>
  <span class="meta-chip">⬆ Lagna: {_h(result.lagna_sign)}</span>
  <span class="meta-chip">🌙 Moon: {_h(result.moon_sign)} · {_h(result.moon_nakshatra)}</span>
</div>

{"<div style='background:rgba(255,200,0,.10);border:1px solid rgba(255,200,0,.4);border-radius:8px;padding:12px 16px;margin-bottom:16px;'><b style='color:#e3b341'>Question: </b>" + _h(result.question) + "</div>" if result.question else ""}

{conflict_banner_html}

<div class="grid-2" style="margin-bottom:20px">

  <div class="verdict-box">
    <div style="font-size:12px;color:#8b949e;margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em">Prashna Verdict</div>
    <div class="verdict-word">{_h(result.verdict)}</div>
    <div class="confidence-bar-bg"><div class="confidence-bar"></div></div>
    <div style="font-size:13px;color:{band_col}">{_h(result.confidence_band)} confidence &nbsp;·&nbsp; {conf_pct}%</div>
    {f'<div style="font-size:13px;color:#8b949e;margin-top:8px">Plain answer: <b style="color:{verdict_col}">{_h(result.binary_answer)}</b> (leaning {_h(result.verdict_leaning)}, hedged — see caveats below)</div>' if result.verdict == "CONDITIONAL" and result.binary_answer else ''}
    <div style="font-size:13px;color:#8b949e;margin-top:12px">
      🕐 Timing: <b style="color:#e6edf3">{_h(result.timing_estimate)}</b>
    </div>
  </div>

  <div class="card">
    {"<div style='font-size:12px;color:#79c0ff;margin-bottom:10px'>" + _h(result.tajika_aspect_note) + "</div>" if result.tajika_aspect_note else ""}
    <h3>Moon Status</h3>
    <div style="font-size:13px;color:{'#f85149' if result.moon_void else '#3fb950'};margin-bottom:4px">
      {_h(result.moon_status)}
    </div>
    {"<div style='font-size:11px;color:#e3b341;margin-bottom:10px'>⚠ " + _h(result.moon_status_caveat) + "</div>" if result.moon_status_caveat else ""}
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
<div class="grid-dashboard">
  <div>{factor_cards_html}</div>
  <div class="card">
    <div class="rules-split">
      <div class="rules-col supports">
        <h3>✓ Supports ({len(result.classical_rules_fired)})</h3>
        <ul>{pos_rules_html}</ul>
      </div>
      <div class="rules-col opposes">
        <h3>✗ Opposes ({len(result.denial_rules_fired)})</h3>
        <ul>{neg_rules_html}</ul>
      </div>
    </div>
  </div>
  <div>
    <div class="card">
      <h3 style="margin-bottom:10px">Remedies</h3>
      <ul style="font-size:12.5px;line-height:1.7;color:#8b949e;padding-left:18px">{remedy_html}</ul>
    </div>
    {"<div style='background:rgba(255,255,255,.04);border:1px solid #30363d;border-radius:8px;padding:10px 14px;margin-top:14px;font-size:11px;color:#8b949e;line-height:1.6'><b>Validation: </b>" + _h(result.validation_status.get('statistical_calibration','')) + "<br/><b>Score semantics: </b>" + _h(result.score_semantics) + "<br/>" + _h(result.disclaimer) + "</div>" if result.validation_status else ""}
  </div>
</div>

<h2>Prashna Chart</h2>
<div class="grid-2" style="margin-bottom:16px;align-items:start">
  {south_indian_html}
  <div class="card">
    <h3 style="margin-bottom:10px">House Lords</h3>
    <table>
      <thead><tr><th>House</th><th>Lord</th></tr></thead>
      <tbody>{house_lords_rows}</tbody>
    </table>
  </div>
</div>

<div class="card">
  <h3 style="margin-bottom:10px">Planetary Positions</h3>
  <table>
    <thead><tr>
      <th>Planet</th><th>Sign</th><th>Degree</th><th>House</th>
      <th>Nakshatra</th><th>Dignity</th><th>House Position</th><th>House Lord</th>
    </tr></thead>
    <tbody>{"".join(planet_rows)}</tbody>
  </table>
</div>

<footer>JyotishAI Prashna Engine v1.0 &nbsp;·&nbsp; {_h(result.moment)}</footer>
</div>
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
    # ── Indian metros ──────────────────────────────────────────────────────────
    "mumbai": (19.0760, 72.8777), "bombay": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090), "new delhi": (28.6139, 77.2090),
    "bangalore": (12.9716, 77.5946), "bengaluru": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707), "madras": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639), "calcutta": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567), "poona": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "surat": (21.1702, 72.8311),
    "lucknow": (26.8467, 80.9462),
    "kanpur": (26.4499, 80.3319),
    "nagpur": (21.1458, 79.0882),
    "indore": (22.7196, 75.8577),
    "bhopal": (23.2599, 77.4126),
    "patna": (25.5941, 85.1376),
    "vadodara": (22.3072, 73.1812), "baroda": (22.3072, 73.1812),
    "coimbatore": (11.0168, 76.9558),
    "vizag": (17.6868, 83.2185), "visakhapatnam": (17.6868, 83.2185),
    "kochi": (9.9312, 76.2673), "cochin": (9.9312, 76.2673),
    "thiruvananthapuram": (8.5241, 76.9366), "trivandrum": (8.5241, 76.9366),
    "chandigarh": (30.7333, 76.7794),
    "amritsar": (31.6340, 74.8723),
    "bhubaneswar": (20.2961, 85.8245),
    "guwahati": (26.1445, 91.7362),
    "dehradun": (30.3165, 78.0322),
    "ranchi": (23.3441, 85.3096),
    "raipur": (21.2514, 81.6296),
    "agra": (27.1767, 78.0081),
    "varanasi": (25.3176, 82.9739), "banaras": (25.3176, 82.9739),
    "mathura": (27.4924, 77.6737),
    "haridwar": (29.9457, 78.1642),
    "jodhpur": (26.2389, 73.0243),
    "udaipur": (24.5854, 73.7125),
    "mysore": (12.2958, 76.6394), "mysuru": (12.2958, 76.6394),
    "mangalore": (12.9141, 74.8560), "mangaluru": (12.9141, 74.8560),
    "hubli": (15.3647, 75.1240),
    "tiruchirappalli": (10.7905, 78.7047), "trichy": (10.7905, 78.7047),
    "madurai": (9.9252, 78.1198),
    "vijayawada": (16.5062, 80.6480),
    "goa": (15.2993, 74.1240), "panaji": (15.4909, 73.8278),
    "shimla": (31.1048, 77.1734),
    "jammu": (32.7266, 74.8570),
    "srinagar": (34.0837, 74.7973),
    "imphal": (24.8170, 93.9368),
    "shillong": (25.5788, 91.8933),
    "gangtok": (27.3314, 88.6138),
    "leh": (34.1526, 77.5771),
    # International
    "new york": (40.7128, -74.0060), "nyc": (40.7128, -74.0060),
    "london": (51.5074, -0.1278),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
    "sydney": (-33.8688, 151.2093),
    "toronto": (43.6510, -79.3470),
    "paris": (48.8566, 2.3522),
    "berlin": (52.5200, 13.4050),
    "amsterdam": (52.3676, 4.9041),
    "zurich": (47.3769, 8.5417),
    "frankfurt": (50.1109, 8.6821),
    "milan": (45.4642, 9.1900),
    "madrid": (40.4168, -3.7038),
    "moscow": (55.7558, 37.6173),
    "istanbul": (41.0082, 28.9784),
    "riyadh": (24.7136, 46.6753),
    "abu dhabi": (24.4539, 54.3773),
    "doha": (25.2854, 51.5310),
    "kuwait city": (29.3759, 47.9774),
    "muscat": (23.5880, 58.3829),
    "kuala lumpur": (3.1390, 101.6869), "kl": (3.1390, 101.6869),
    "bangkok": (13.7563, 100.5018),
    "jakarta": (-6.2088, 106.8456),
    "hong kong": (22.3193, 114.1694),
    "shanghai": (31.2304, 121.4737),
    "beijing": (39.9042, 116.4074),
    "tokyo": (35.6762, 139.6503),
    "osaka": (34.6937, 135.5023),
    "seoul": (37.5665, 126.9780),
    "los angeles": (34.0522, -118.2437), "la": (34.0522, -118.2437),
    "san francisco": (37.7749, -122.4194), "sf": (37.7749, -122.4194),
    "chicago": (41.8781, -87.6298),
    "houston": (29.7604, -95.3698),
    "boston": (42.3601, -71.0589),
    "washington": (38.9072, -77.0369), "washington dc": (38.9072, -77.0369),
    "seattle": (47.6062, -122.3321),
    "vancouver": (49.2827, -123.1207),
    "melbourne": (-37.8136, 144.9631),
    "auckland": (-36.8509, 174.7645),
    "johannesburg": (-26.2041, 28.0473),
    "nairobi": (-1.2921, 36.8219),
    "cairo": (30.0444, 31.2357),
}

def city_to_coords(city_name: str) -> Tuple[float, float]:
    """Look up (lat, lon) for a city name; defaults to Delhi if not found.

    Normalises spaces, underscores, hyphens and case before lookup.
    """
    key = city_name.lower().strip().replace("_", " ").replace("-", " ")
    return _CITY_COORDS.get(key, (28.6139, 77.2090))   # default: Delhi


def prashna_result_to_dict(result: "PrashnaResult") -> dict:
    """Serialize PrashnaResult to a plain dict for JSON output.

    Exposes both classical_rules_fired (positive) and denial_rules_fired
    (negative) as separate keys (A-3 requirement).
    Also includes panchang audit fields (P-1).
    """
    all_rules = result.classical_rules_fired + result.denial_rules_fired
    return {
        "question":                  result.question,
        "category":                  result.category,
        "category_label":            _CATEGORY_LABELS.get(result.category, result.category),
        "moment":                    result.moment,
        "city":                      result.city,
        "verdict":                   result.verdict,
        "verdict_leaning":           result.verdict_leaning,
        "binary_answer":             result.binary_answer,
        "confidence":                result.confidence,
        "confidence_band":           result.confidence_band,
        "kp_sublord_verdict":        result.kp_sublord_verdict,
        "kp_sublord_planet":         result.kp_sublord_planet,
        "kp_signifies_affirm":       result.kp_sublord_signifies_affirm,
        "moon_status":               result.moon_status,
        "moon_void":                 result.moon_void,
        "timing_estimate":           result.timing_estimate,
        "timing_unit":               result.timing_unit,
        "affirm_significators":      result.affirm_significators,
        "deny_significators":        result.deny_significators,
        "lagna_sign":                result.lagna_sign,
        "lagna_lord":                result.lagna_lord,
        "moon_sign":                 result.moon_sign,
        "moon_nakshatra":            result.moon_nakshatra,
        "classical_rules_fired":     result.classical_rules_fired,   # A-3: positive only
        "denial_rules_fired":        result.denial_rules_fired,      # A-3: negative only
        "classical_rules":           all_rules,                      # compat alias
        "remedies":                  result.remedy_suggestions,      # alias expected by PrashnaResponse
        "remedy_suggestions":        result.remedy_suggestions,      # kept for back-compat
        "factors":                   result.factors,
        "planets":                   result.planets_summary,         # alias expected by PrashnaResponse
        "planets_summary":           result.planets_summary,         # kept for back-compat
        "house_lords":               result.house_lords,
        # P-1: Panchang audit
        "panchang":                  result.panchang,
        "panchang_score":            result.panchang_score,
        "panchang_positive":         result.panchang_positive,
        "panchang_negative":         result.panchang_negative,
        # Gap-remediation (2026-07-18): joint KP cusp check, Tajika
        # Ithasala/Isbaha note, Moon precision caveat, and the verdict/
        # evidence conflict banner.
        "kp_joint_houses":           result.kp_joint_houses,
        "kp_joint_details":          result.kp_joint_details,
        "kp_joint_verdict":          result.kp_joint_verdict,
        "moon_status_caveat":        result.moon_status_caveat,
        "tajika_aspect_note":        result.tajika_aspect_note,
        "internal_conflict_notes":   result.internal_conflict_notes,
        "afflicted_planets":         result.afflicted_planets,
        "validation_status":         result.validation_status,
        "score_semantics":           result.score_semantics,
        "disclaimer":                result.disclaimer,
    }
