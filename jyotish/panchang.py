"""JyotishAI — Vedic Panchang (Five Limbs) calculator.

Computes the five classical Panchang elements plus Hora for any
sun_lon / moon_lon pair and datetime:

  1. Tithi    — lunar day 1-30 (Shukla 1-15, Krishna 1-15)
  2. Vara     — weekday + planetary lord
  3. Nakshatra— Moon's sidereal nakshatra (1-27) + lord
  4. Yoga     — Sun+Moon combined nakshatra index (1-27)
  5. Karana   — half-tithi (1-11 cyclically)
  + Hora      — current planetary hour lord (Chaldean sequence)

All longitudes are expected in sidereal degrees (ayanamsha already applied
by the caller -- this module performs no ayanamsha conversion itself and is
agnostic to which one was used; the engine's canonical declared ayanamsha is
KP/Krishnamurti, see jyotish/llm_policy.py:AYANAMSHA).

Public API
----------
  compute_panchang(sun_lon, moon_lon, dt) -> dict
  panchang_quality(panchang, primary_houses)  -> (score, good, bad)
  hora_lord_at(dt) -> str   (planet name)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_SIGN_LORD = {
    "Aries": "Mars",   "Taurus": "Venus",  "Gemini": "Mercury",
    "Cancer": "Moon",  "Leo": "Sun",       "Virgo": "Mercury",
    "Libra": "Venus",  "Scorpio": "Mars",  "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

# 27 Nakshatras in sidereal order, each spanning 13°20' (= 360/27)
_NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha",
    "Anuradha", "Jyeshtha", "Moola", "Purva Ashadha", "Uttara Ashadha",
    "Shravana", "Dhanishtha", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
]

# Nakshatra lords in Vimshottari order (repeating cycle of 9)
_NK_LORDS = ["Ketu", "Venus", "Sun", "Moon", "Mars",
             "Rahu", "Jupiter", "Saturn", "Mercury"]

# 27 Panchang Yogas
_YOGAS = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana",
    "Atiganda", "Sukarma", "Dhriti", "Shoola", "Ganda", "Vriddhi",
    "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata",
    "Variyan", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha",
    "Shukla", "Brahma", "Indra", "Vaidhriti",
]

# Malefic Yogas (inauspicious for initiating activities)
_MALEFIC_YOGAS = {
    "Vishkambha", "Atiganda", "Shoola", "Ganda", "Vyaghata",
    "Vajra", "Vyatipata", "Parigha", "Vaidhriti",
}

# 11 Karanas (first 4 fixed, last 7 movable and repeating)
_KARANAS_FIXED  = ["Kimstughna", "Shakuni", "Chatushpada", "Naga"]
_KARANAS_MOVABLE = ["Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti"]
# Inauspicious karana for most activities
_MALEFIC_KARANAS = {"Vishti", "Shakuni", "Chatushpada", "Naga", "Kimstughna"}

# Tithi names (Shukla 1-15 then Krishna 1-15 = Pratipada…Amavasya)
_TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima",   # Shukla
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Amavasya",  # Krishna
]

# Inauspicious tithis for examinations and new ventures
_MALEFIC_TITHIS = {4, 8, 12, 14, 15, 19, 23, 27, 29, 30}  # 1-indexed

# Vara (weekday) lords  — Python weekday: Mon=0 … Sun=6
_VARA_LORDS = {
    6: "Sun",      # Sunday
    0: "Moon",     # Monday
    1: "Mars",     # Tuesday
    2: "Mercury",  # Wednesday
    3: "Jupiter",  # Thursday
    4: "Venus",    # Friday
    5: "Saturn",   # Saturday
}

# Chaldean sequence (used for hora progression)
_CHALDEAN = ["Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars"]

# Benefic planets for Panchang quality scoring
_BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
_MALEFICS = {"Saturn", "Mars", "Rahu", "Ketu", "Sun"}

# ---------------------------------------------------------------------------
# Core Panchang element computations
# ---------------------------------------------------------------------------

def _tithi(sun_lon: float, moon_lon: float) -> Tuple[int, str, str]:
    """Return (tithi_number 1-30, name, paksha)."""
    diff = (moon_lon - sun_lon) % 360
    num  = int(diff / 12) + 1          # 1-30
    num  = min(num, 30)
    paksha = "Shukla" if num <= 15 else "Krishna"
    return num, _TITHI_NAMES[num - 1], paksha


def _vara(dt: datetime, sunrise_hour: float = 6.0) -> Tuple[str, str]:
    """Return (weekday_name, vara_lord) for a (possibly naive) datetime.

    FIX-3: Vara rules from sunrise to sunrise, NOT calendar midnight.
    If the time is before sunrise_hour, the Vara still belongs to the
    previous calendar day — e.g., 3 AM on Wednesday is Vara of Tuesday.

    Args:
        dt           : local datetime of the query moment.
        sunrise_hour : decimal hour of local sunrise (default 6.0 = 6:00 AM).
                       Pass a site-computed value for higher precision.
    """
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    current_decimal_hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    if current_decimal_hour < sunrise_hour:
        # Before today's sunrise → still previous day's Vara
        wd = (dt.weekday() - 1) % 7
    else:
        wd = dt.weekday()
    lord = _VARA_LORDS[wd]
    return days[wd], lord


def _nakshatra(moon_lon: float) -> Tuple[int, str, str]:
    """Return (nakshatra_index 1-27, name, lord)."""
    idx  = int(moon_lon / (360 / 27))  # 0-26
    idx  = min(idx, 26)
    name = _NAKSHATRAS[idx]
    lord = _NK_LORDS[idx % 9]
    return idx + 1, name, lord


def _yoga(sun_lon: float, moon_lon: float) -> Tuple[int, str, bool]:
    """Return (yoga_index 1-27, name, is_malefic)."""
    combined = (sun_lon + moon_lon) % 360
    idx      = int(combined / (360 / 27))
    idx      = min(idx, 26)
    name     = _YOGAS[idx]
    return idx + 1, name, name in _MALEFIC_YOGAS


def _karana(sun_lon: float, moon_lon: float) -> Tuple[int, str, bool]:
    """Return (karana_index 1-60, name, is_malefic).

    Each tithi has 2 karanas (first and second half).
    The first karana of Krishnapaksha 14 (tithi 29) is Vishti (fixed).
    """
    diff    = (moon_lon - sun_lon) % 360
    half_num = int(diff / 6)           # 0-59 across 30 tithis × 2 halves

    # Karanas 0-3 (very start of Shukla cycle) and karanas 57-59 are fixed
    # Standard mapping:
    if half_num == 0:
        name = "Kimstughna"
    elif half_num >= 57:
        fixed_idx = half_num - 57      # 0,1,2 → Shakuni, Chatushpada, Naga
        name = _KARANAS_FIXED[1 + fixed_idx]
    else:
        movable_idx = (half_num - 1) % 7
        name = _KARANAS_MOVABLE[movable_idx]

    return half_num + 1, name, name in _MALEFIC_KARANAS


def hora_lord_at(dt: datetime, sunrise_hour: float = 6.0) -> str:
    """Return the planetary hora lord for the given datetime.

    FIX-3: Hora sequence starts from the Vara lord at sunrise, not midnight.
    Equal 1-hour horas (simplified) from the sunrise-corrected day lord.

    Args:
        dt           : local datetime of the query moment.
        sunrise_hour : decimal hour of local sunrise (default 6.0).
    """
    # Use sunrise-corrected Vara lord as the Hora sequence anchor
    _, day_lord = _vara(dt, sunrise_hour=sunrise_hour)
    dl_idx      = _CHALDEAN.index(day_lord)
    # Hours elapsed since today's sunrise
    current_h   = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    hours_since_sunrise = (current_h - sunrise_hour) % 24
    hora_num    = int(hours_since_sunrise) % 24
    hora_idx    = (dl_idx + hora_num) % 7
    return _CHALDEAN[hora_idx]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_panchang(
    sun_lon:      float,
    moon_lon:     float,
    dt:           datetime,
    sunrise_hour: float = 6.0,
) -> Dict[str, Any]:
    """Compute all five Panchang limbs + Hora for the given sidereal positions.

    Args:
        sun_lon      : Sidereal Sun longitude in degrees (Lahiri).
        moon_lon     : Sidereal Moon longitude in degrees (Lahiri).
        dt           : Moment of interest (naive=local or timezone-aware).
        sunrise_hour : Local sunrise as a decimal hour (default 6.0 = 6:00 AM).
                       FIX-3: Vara and Hora are sunrise-to-sunrise, not midnight-
                       to-midnight. Pass site/date-specific sunrise for full
                       accuracy (e.g., 5.75 for 5:45 AM in summer latitudes).

    Returns dict with keys:
        tithi_num, tithi_name, paksha,
        vara_name, vara_lord,
        nakshatra_num, nakshatra_name, nakshatra_lord,
        yoga_num, yoga_name, yoga_malefic,
        karana_num, karana_name, karana_malefic,
        hora_lord,
        auspicious  (bool — all 5 elements are benign),
        malefic_count (int),
        sunrise_hour (float — the sunrise used for Vara/Hora correction),
    """
    t_num, t_name, paksha       = _tithi(sun_lon, moon_lon)
    vara_name, vara_lord         = _vara(dt, sunrise_hour=sunrise_hour)
    nk_num, nk_name, nk_lord    = _nakshatra(moon_lon)
    y_num, y_name, y_mal        = _yoga(sun_lon, moon_lon)
    k_num, k_name, k_mal        = _karana(sun_lon, moon_lon)
    h_lord                       = hora_lord_at(dt, sunrise_hour=sunrise_hour)

    tithi_malefic = t_num in _MALEFIC_TITHIS

    malefic_count = sum([
        tithi_malefic,
        vara_lord in _MALEFICS and vara_lord not in {"Sun"},  # Sun vara is neutral
        y_mal,
        k_mal,
        nk_lord in _MALEFICS,
    ])

    return {
        "tithi_num":       t_num,
        "tithi_name":      t_name,
        "paksha":          paksha,
        "tithi_malefic":   tithi_malefic,
        "vara_name":       vara_name,
        "vara_lord":       vara_lord,
        "nakshatra_num":   nk_num,
        "nakshatra_name":  nk_name,
        "nakshatra_lord":  nk_lord,
        "yoga_num":        y_num,
        "yoga_name":       y_name,
        "yoga_malefic":    y_mal,
        "karana_num":      k_num,
        "karana_name":     k_name,
        "karana_malefic":  k_mal,
        "hora_lord":       h_lord,
        "malefic_count":   malefic_count,
        "auspicious":      malefic_count == 0,
        "sunrise_hour":    sunrise_hour,      # FIX-3: record the sunrise used
    }


def panchang_quality(
    panchang: Dict[str, Any],
    primary_houses: List[int],
    house_lords: Dict[str, str],
) -> Tuple[float, List[str], List[str]]:
    """Score the Panchang for a specific query's relevant houses.

    Args:
        panchang       : Output of compute_panchang().
        primary_houses : Houses relevant to the question category (e.g. [1,6,10,11]).
        house_lords    : {house_str: planet} map from the chart.

    Returns:
        (score 0.0-1.0, positive_factors, negative_factors)
    """
    positive: List[str] = []
    negative: List[str] = []

    # --- Hora lord corroboration (P-2) ---
    hora = panchang.get("hora_lord", "")
    h_lords_of_primary = {
        house_lords.get(str(h), "") for h in primary_houses
    }
    if hora and hora in h_lords_of_primary:
        positive.append(f"Hora lord {hora} rules a primary house — strong timing signal")
    elif hora in _MALEFICS:
        negative.append(f"Hora lord {hora} is a natural malefic — timing is strained")

    # --- Tithi ---
    if not panchang.get("tithi_malefic"):
        positive.append(f"Tithi {panchang.get('tithi_name','')} is auspicious")
    else:
        negative.append(f"Tithi {panchang.get('tithi_name','')} is inauspicious")

    # --- Nakshatra ---
    nk_lord = panchang.get("nakshatra_lord", "")
    if nk_lord in _BENEFICS:
        positive.append(f"Nakshatra lord {nk_lord} is a natural benefic")
    elif nk_lord in {"Saturn", "Mars", "Rahu", "Ketu"}:
        negative.append(f"Nakshatra lord {nk_lord} is a natural malefic")

    # --- Yoga ---
    if panchang.get("yoga_malefic"):
        negative.append(f"Yoga {panchang.get('yoga_name','')} is inauspicious")
    else:
        positive.append(f"Yoga {panchang.get('yoga_name','')} is auspicious")

    # --- Karana ---
    if panchang.get("karana_malefic"):
        negative.append(f"Karana {panchang.get('karana_name','')} is inauspicious")

    # --- Hora lord relevance to primary houses ---
    hora_lord = panchang.get("hora_lord", "")
    h_lords_primary = {house_lords.get(str(h), "") for h in primary_houses}
    if hora_lord and hora_lord in h_lords_primary:
        positive.append(
            f"Hora lord {hora_lord} rules a primary significator house "
            f"(H{[h for h in primary_houses if house_lords.get(str(h)) == hora_lord]}) "
            "— timing is confirmed"
        )

    # --- Score ---
    total  = len(positive) + len(negative)
    if total == 0:
        score = 0.5
    else:
        score = round(len(positive) / total, 3)

    return score, positive, negative
