"""JyotishAI — Module 2 Micro-Timing Engine

Four tactical features that convert the macro timeline into a daily SaaS dashboard:

  1. compute_negotiation_heatmap()  — Moon/Mercury transit calendar (interview windows)
  2. compute_stakeholder_radar()    — Malefic transit over natal H6/H10 (office politics)
  3. compute_whatif_scenario()      — 6-month forward scan for action advisability
  4. compute_habit_tracker()        — 30-day weekly push plan per AD/PD lord

Ephemeris: uses the `ephem` library for accurate tropical positions.
Ayanamsa: Lahiri linear approximation (23.85 deg base at J2000 +
0.013968 deg/year precession) -- FALLBACK ONLY. The engine's canonical
declared ayanamsha is KP/Krishnamurti (see jyotish/llm_policy.py:AYANAMSHA),
which differs from Lahiri by a small (sub-degree) offset not modeled by this
linear approximation. This module is used only for tactical/advisory
micro-timing output (negotiation windows, stakeholder radar), never for the
core dignity/strength/final_score calculations, which route through
jyotish/ephemeris.py's real swisseph SIDM_KRISHNAMURTI computation when
available. GAP-FIX (2026-07, ayanamsha-consistency audit): documented this
divergence explicitly rather than silently presenting a Lahiri-based figure
as if it matched the declared policy ayanamsha.

All functions are deterministic and stateless — no LLM required.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ayanamsa & ephemeris helpers
# ---------------------------------------------------------------------------

# Lahiri ayanamsa at J2000 (Jan 1.5, 2000 TT) = 23.85281°
# Annual precession ≈ 0.013968° (50.29 arcsec/year)
_AYANAMSA_J2000 = 23.85281
_AYANAMSA_ANNUAL = 0.013968   # degrees per year

_SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
_SIGN_INDEX = {s: i for i, s in enumerate(_SIGN_NAMES)}


def _lahiri_ayanamsa(year: float) -> float:
    """Return Lahiri ayanamsa in degrees for a given decimal year.

    NOTE: this is a fallback linear approximation, not the engine's
    canonical declared ayanamsha (KP/Krishnamurti, see llm_policy.py).
    Used only for this module's tactical micro-timing advisories."""
    return _AYANAMSA_J2000 + _AYANAMSA_ANNUAL * (year - 2000.0)


def _tropical_to_sidereal(tropical_lon: float, year: float) -> float:
    """Convert tropical longitude (0–360°) to sidereal longitude."""
    return (tropical_lon - _lahiri_ayanamsa(year)) % 360.0


def _lon_to_sign(sidereal_lon: float) -> str:
    """Convert sidereal longitude to sign name."""
    return _SIGN_NAMES[int(sidereal_lon / 30) % 12]


def _sign_to_house(sign: str, lagna_sign: str) -> int:
    """Whole-sign house number (1–12) for a sign given the lagna sign."""
    lagna_idx = _SIGN_INDEX.get(lagna_sign, 0)
    sign_idx  = _SIGN_INDEX.get(sign, 0)
    return (sign_idx - lagna_idx) % 12 + 1


def _date_to_decimal_year(d: date) -> float:
    """Convert a date to decimal year (e.g. 2026-06-21 → 2026.47)."""
    start = date(d.year, 1, 1)
    end   = date(d.year + 1, 1, 1)
    frac  = (d - start).days / (end - start).days
    return d.year + frac


try:
    import ephem as _ephem

    def _planet_lon(planet_obj, d: date) -> float:
        """Tropical ecliptic longitude of an ephem body on a given date."""
        planet_obj.compute(d.isoformat(), epoch="2000")
        return math.degrees(planet_obj.hlong)

    def _get_moon_sign(d: date) -> str:
        m = _ephem.Moon()
        lon = _planet_lon(m, d)
        return _lon_to_sign(_tropical_to_sidereal(lon, _date_to_decimal_year(d)))

    def _get_mercury_sign(d: date) -> str:
        me = _ephem.Mercury()
        lon = _planet_lon(me, d)
        return _lon_to_sign(_tropical_to_sidereal(lon, _date_to_decimal_year(d)))

    def _get_mars_sign(d: date) -> str:
        ma = _ephem.Mars()
        lon = _planet_lon(ma, d)
        return _lon_to_sign(_tropical_to_sidereal(lon, _date_to_decimal_year(d)))

    def _get_saturn_sign(d: date) -> str:
        sa = _ephem.Saturn()
        lon = _planet_lon(sa, d)
        return _lon_to_sign(_tropical_to_sidereal(lon, _date_to_decimal_year(d)))

    def _get_venus_sign(d: date) -> str:
        ve = _ephem.Venus()
        lon = _planet_lon(ve, d)
        return _lon_to_sign(_tropical_to_sidereal(lon, _date_to_decimal_year(d)))

    def _get_rahu_sign(d: date) -> str:
        """Rahu = True North Node (ephem TLE approach via orbital elements).
        ephem doesn't have a TrueNorthNode body; approximate via sidereal speed model.
        Rahu retrogrades ~0.053°/day; seed from known position.
        """
        # Seed: Rahu at ~6° Pisces (sidereal) on 2025-01-01
        seed = date(2025, 1, 1)
        seed_lon = 336.0   # Pisces 6° sidereal
        delta = (d - seed).days
        lon = (seed_lon - 0.053 * delta) % 360.0
        return _lon_to_sign(lon)

    _EPHEM_AVAILABLE = True

except ImportError:
    _EPHEM_AVAILABLE = False

    # ── Fallback: simplified sidereal-speed orbital model ──────────────────
    # Average daily sidereal motion (degrees/day)
    _SIDEREAL_SPEED = {
        "Moon":    13.176,
        "Mercury":  1.383,
        "Mars":     0.524,
        "Saturn":   0.034,
        "Rahu":    -0.053,  # retrograde
    }
    # Approximate sidereal longitude at 2025-01-01 (from published ephemeris)
    _SEED_DATE = date(2025, 1, 1)
    _SEED_LON = {
        "Moon":    94.0,   # Cancer ~4°
        "Mercury": 270.0,  # Capricorn ~0°
        "Mars":    100.0,  # Cancer ~10°
        "Saturn":  330.0,  # Pisces ~0°
        "Rahu":    177.0,  # Virgo ~27° (retrograde)
    }

    def _planet_lon_approx(planet: str, d: date) -> float:
        delta_days = (d - _SEED_DATE).days
        speed = _SIDEREAL_SPEED.get(planet, 0.0)
        return (_SEED_LON.get(planet, 0.0) + speed * delta_days) % 360.0

    def _get_moon_sign(d: date) -> str:
        return _lon_to_sign(_planet_lon_approx("Moon", d))

    def _get_mercury_sign(d: date) -> str:
        return _lon_to_sign(_planet_lon_approx("Mercury", d))

    def _get_mars_sign(d: date) -> str:
        return _lon_to_sign(_planet_lon_approx("Mars", d))

    def _get_saturn_sign(d: date) -> str:
        return _lon_to_sign(_planet_lon_approx("Saturn", d))

    def _get_venus_sign(d: date) -> str:
        # Venus: ~0.616°/day sidereal, seed at Capricorn ~20° on 2025-01-01
        seed = date(2025, 1, 1)
        seed_lon = 290.0
        delta = (d - seed).days
        lon = (seed_lon + 0.616 * delta) % 360.0
        return _lon_to_sign(lon)

    def _get_rahu_sign(d: date) -> str:
        return _lon_to_sign(_planet_lon_approx("Rahu", d))


# ---------------------------------------------------------------------------
# Class-12 transit helper
# ---------------------------------------------------------------------------

def _get_all_planet_positions(d: date, lagna_sign: str) -> Dict[str, Dict]:
    """Return transit planet dict {planet: {sign, degree, nakshatra, house}} for date d.

    Used for SBC when we want a specific future date rather than today.
    Covers all 9 Jyotish grahas (Rahu/Ketu computed from Node).
    """
    try:
        from jyotish.ephemeris import get_transit_house_positions
        from jyotish.llm_policy import AYANAMSHA
        dt = datetime(d.year, d.month, d.day, 12)
        houses, degrees, retrograde = get_transit_house_positions(
            dt, 0.0, 0.0, lagna_sign, AYANAMSHA, 0.0,
        )
        if degrees:
            names = ["Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
                     "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni",
                     "Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha","Mula",
                     "Purva Ashadha","Uttara Ashadha","Shravana","Dhanishtha","Shatabhisha",
                     "Purva Bhadrapada","Uttara Bhadrapada","Revati"]
            zodiac = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
                      "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
            return {p: {"sign": zodiac[int(lon % 360 // 30)], "degree": round(lon % 30, 6),
                        "nakshatra": names[int(lon * 27 / 360) % 27],
                        "house": houses.get(p, 0), "retrograde": p in retrograde,
                        "calculation_status": "CANONICAL_EPHEMERIS"}
                    for p, lon in degrees.items()}
    except Exception:
        pass
    return {}

    dec_year = _date_to_decimal_year(d)
    ayanamsa = _lahiri_ayanamsa(dec_year)

    _NAKSHATRA_NAMES = [
        "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
        "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni",
        "Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha",
        "Mula","Purva Ashadha","Uttara Ashadha","Shravana","Dhanishtha",
        "Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati",
    ]

    def _lon_to_nakshatra(lon: float) -> str:
        return _NAKSHATRA_NAMES[int(lon * 27 / 360) % 27]

    result: Dict[str, Dict] = {}

    if _EPHEM_AVAILABLE:
        import ephem as _e
        bodies = {
            "Sun":     _e.Sun(),
            "Moon":    _e.Moon(),
            "Mars":    _e.Mars(),
            "Mercury": _e.Mercury(),
            "Jupiter": _e.Jupiter(),
            "Venus":   _e.Venus(),
            "Saturn":  _e.Saturn(),
        }
        for name, body in bodies.items():
            body.compute(d.isoformat(), epoch="2000")
            trop_lon = math.degrees(body.hlong)
            sid_lon  = (trop_lon - ayanamsa) % 360.0
            sign     = _lon_to_sign(sid_lon)
            degree   = sid_lon % 30.0
            result[name] = {
                "sign":      sign,
                "degree":    round(degree, 2),
                "nakshatra": _lon_to_nakshatra(sid_lon),
                "house":     _sign_to_house(sign, lagna_sign),
            }
        # Rahu: True Node via ephem (retrograde mean node)
        node = _e.Moon()
        node.compute(d.isoformat(), epoch="2000")
        # ephem Moon().g_ra doesn't give node; use orbital elements approximation
        # Fall back to seed model for Rahu
        seed_date = date(2025, 1, 1)
        seed_lon  = 336.0  # Pisces ~6° sidereal
        delta_days = (d - seed_date).days
        rahu_lon  = (seed_lon - 0.053 * delta_days) % 360.0
        ketu_lon  = (rahu_lon + 180.0) % 360.0
    else:
        # Fallback: orbital speed model
        _SPEED = {"Sun": 0.9856, "Moon": 13.176, "Mars": 0.524,
                  "Mercury": 1.383, "Jupiter": 0.083, "Venus": 1.200, "Saturn": 0.034}
        _SEED_DATE2 = date(2025, 1, 1)
        _SEED_LON2  = {"Sun": 280.0, "Moon": 94.0, "Mars": 100.0,
                       "Mercury": 270.0, "Jupiter": 60.0, "Venus": 300.0, "Saturn": 330.0}
        delta_days = (d - _SEED_DATE2).days
        for name, speed in _SPEED.items():
            sid_lon = (_SEED_LON2[name] + speed * delta_days) % 360.0
            sign    = _lon_to_sign(sid_lon)
            degree  = sid_lon % 30.0
            result[name] = {
                "sign":      sign,
                "degree":    round(degree, 2),
                "nakshatra": _lon_to_nakshatra(sid_lon),
                "house":     _sign_to_house(sign, lagna_sign),
            }
        seed_date  = date(2025, 1, 1)
        seed_lon   = 336.0
        delta_days2 = (d - seed_date).days
        rahu_lon   = (seed_lon - 0.053 * delta_days2) % 360.0
        ketu_lon   = (rahu_lon + 180.0) % 360.0

    rahu_sign = _lon_to_sign(rahu_lon)
    ketu_sign = _lon_to_sign(ketu_lon)
    result["Rahu"] = {
        "sign":      rahu_sign,
        "degree":    round(rahu_lon % 30.0, 2),
        "nakshatra": _lon_to_nakshatra(rahu_lon),
        "house":     _sign_to_house(rahu_sign, lagna_sign),
    }
    result["Ketu"] = {
        "sign":      ketu_sign,
        "degree":    round(ketu_lon % 30.0, 2),
        "nakshatra": _lon_to_nakshatra(ketu_lon),
        "house":     _sign_to_house(ketu_sign, lagna_sign),
    }
    return result


def compute_class12_transits(
    dob: str,
    lagna_sign: str,
) -> tuple:
    """Compute transit planets for the native's Class 12 board exam date.

    Class 12 boards in India peak around March 15.
    Age at Class 12: 17 years (if born Jan–June) or 18 years (born July–Dec).

    Returns:
        (transit_dict, exam_date)   where exam_date is a datetime.date
    """
    # Parse DOB — handle DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY
    from datetime import date as _date
    import re as _re

    dob_clean = dob.strip()
    parsed = None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            from datetime import datetime as _dt
            parsed = _dt.strptime(dob_clean, fmt).date()
            break
        except ValueError:
            continue

    if parsed is None:
        # Last resort: extract 4-digit year
        m = _re.search(r'\b(19|20)\d{2}\b', dob_clean)
        birth_year = int(m.group()) if m else 2007
        birth_month = 1
    else:
        birth_year  = parsed.year
        birth_month = parsed.month

    # Class 12 board exam year
    # If born Jan–June: boards in birth_year+17 (age 17 by March)
    # If born July–Dec: boards in birth_year+18 (still 17 in March, turning 18 later)
    # CBSE cut-off: child must be 6 by April 1st to enter Class 1 that year.
    # Born Jan–Mar: starts Class 1 one cohort earlier → boards birth_year + 17
    # Born Apr–Dec: starts Class 1 in the following cohort → boards birth_year + 18
    exam_year = birth_year + 17 if birth_month < 4 else birth_year + 18
    exam_date = date(exam_year, 3, 15)   # March 15 — board exam peak

    transit_dict = _get_all_planet_positions(exam_date, lagna_sign)
    return transit_dict, exam_date


# ---------------------------------------------------------------------------
# 1. Negotiation Heatmap
# ---------------------------------------------------------------------------

_PEAK_HOUSES       = {2, 10, 11}   # wealth, career, gains
_SUPPORTIVE_HOUSES = {1, 5, 9}     # trine houses — auspicious
_DIFFICULT_HOUSES  = {6, 8, 12}    # dusthana — avoid for negotiations


def compute_negotiation_heatmap(
    today: date,
    lagna_sign: str,
    days: int = 30,
) -> Dict:
    """Return a 30-day negotiation heatmap based on Moon, Mercury, and Venus transits.

    Logic:
    - Moon transits H2/H10/H11 → high-score window (2.5-day clusters)
    - Mercury in H2/H10/H11 concurrently → bonus multiplier
    - Venus in H2/H11/H5 → salary/pleasure gain bonus
    - Moon in dusthana (H6/H8/H12) → avoid flag
    - Mercury retrograde period → caution flag

    Returns:
        {
          "windows": [{"date_start", "date_end", "moon_house", "mercury_house",
                       "venus_house", "score", "label", "advice"}, ...],
          "best_window": {"date_start", ...},
          "current_month_label": "June 2026",
          "caution_periods": [{"date_start", "date_end", "reason"}, ...]
        }
    """
    windows      = []
    caution      = []
    current_sign_start: Optional[date] = None
    current_moon_sign:  Optional[str]  = None

    for offset in range(days):
        d = today + timedelta(days=offset)
        moon_sign    = _get_moon_sign(d)
        mercury_sign = _get_mercury_sign(d)
        venus_sign   = _get_venus_sign(d)

        moon_house    = _sign_to_house(moon_sign, lagna_sign)
        mercury_house = _sign_to_house(mercury_sign, lagna_sign)
        venus_house   = _sign_to_house(venus_sign, lagna_sign)

        # Track Moon sign transitions to define window start
        if moon_sign != current_moon_sign:
            if current_moon_sign is not None and current_sign_start is not None:
                _flush_window(
                    windows, caution, current_sign_start, d - timedelta(days=1),
                    _sign_to_house(current_moon_sign, lagna_sign), mercury_house, venus_house,
                )
            current_moon_sign  = moon_sign
            current_sign_start = d

    # Flush final window
    if current_moon_sign and current_sign_start:
        _flush_window(
            windows, caution, current_sign_start, today + timedelta(days=days - 1),
            _sign_to_house(current_moon_sign, lagna_sign), mercury_house, venus_house,
        )

    # Sort by score desc for best_window
    scored_windows = sorted(
        [w for w in windows if w["score"] >= 2],
        key=lambda x: x["score"],
        reverse=True,
    )
    best = scored_windows[0] if scored_windows else None
    month_label = today.strftime("%B %Y")

    return {
        "windows":             windows,
        "best_window":         best,
        "current_month_label": month_label,
        "caution_periods":     caution,
        "lagna_sign":          lagna_sign,
        "ephem_source":        "ephem" if _EPHEM_AVAILABLE else "orbital_model",
    }


def _flush_window(
    windows: list, caution: list,
    d_start: date, d_end: date,
    moon_house: int, mercury_house: int, venus_house: int = 0,
) -> None:
    score = 0
    advice_parts = []

    # Moon in peak house
    if moon_house in _PEAK_HOUSES:
        score += 2
        h_label = {2: "2nd (wealth)", 10: "10th (career)", 11: "11th (gains)"}[moon_house]
        advice_parts.append(f"Moon activates {h_label} house")

    # Moon in supportive trine
    elif moon_house in _SUPPORTIVE_HOUSES:
        score += 1
        advice_parts.append(f"Moon in supportive trine (H{moon_house})")

    # Moon in dusthana
    elif moon_house in _DIFFICULT_HOUSES:
        score -= 1
        caution.append({
            "date_start": d_start.isoformat(),
            "date_end":   d_end.isoformat(),
            "reason":     f"Moon transits H{moon_house} (dusthana) — emotional turbulence, postpone sensitive negotiations",
        })

    # Mercury bonus
    if mercury_house in _PEAK_HOUSES:
        score += 1
        h_label = {2: "H2", 10: "H10", 11: "H11"}[mercury_house]
        advice_parts.append(f"Mercury in {h_label} — excellent for contract/offer communication")

    # Venus bonus — karaka for salary, pleasure, and smooth negotiations
    if venus_house in (2, 11, 5):
        score += 1
        vl = {2: "H2 (wealth)", 11: "H11 (gains)", 5: "H5 (creativity)"}[venus_house]
        advice_parts.append(f"Venus in {vl} — favourable for salary discussions and deal-closing")
    elif venus_house in (6, 8, 12):
        score -= 1
        caution.append({
            "date_start": d_start.isoformat(),
            "date_end":   d_end.isoformat(),
            "reason":     f"Venus in H{venus_house} (dusthana) — avoid luxury commitments or compensation negotiations",
        })

    # Label
    if score >= 4:
        label  = "Peak — Schedule Now"
        colour = "peak"
    elif score >= 2:
        label  = "Favourable"
        colour = "favourable"
    elif score == 1:
        label  = "Neutral"
        colour = "neutral"
    else:
        label  = "Avoid"
        colour = "avoid"

    advice = ". ".join(advice_parts) if advice_parts else "No strong activation — routine days."

    windows.append({
        "date_start":    d_start.isoformat(),
        "date_end":      d_end.isoformat(),
        "moon_house":    moon_house,
        "mercury_house": mercury_house,
        "venus_house":   venus_house,
        "score":         score,
        "label":         label,
        "colour":        colour,
        "advice":        advice,
    })


# ---------------------------------------------------------------------------
# 2. Stakeholder Radar — quarterly workplace climate
# ---------------------------------------------------------------------------

_MALEFICS = {"Saturn", "Mars", "Rahu"}


def compute_stakeholder_radar(
    today: date,
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    lagna_sign: str,
) -> Dict:
    """Return a quarterly workplace climate assessment.

    Logic:
    - Compute current transiting positions of Saturn, Mars, Rahu.
    - Compare against natal H6/H10/H7 (colleagues, boss, partnerships).
    - If malefic transits the same sign as natal H6 lord or is in H6/H10 → affliction.

    Returns:
        {
          "h6_afflicted": bool,
          "h10_afflicted": bool,
          "h7_afflicted": bool,
          "climate_label": str,
          "afflictors": {"h6": [...], "h10": [...]},
          "advice": str,
          "quarter_label": str
        }
    """
    quarter_map = {1: "Q1", 2: "Q1", 3: "Q1",
                   4: "Q2", 5: "Q2", 6: "Q2",
                   7: "Q3", 8: "Q3", 9: "Q3",
                   10: "Q4", 11: "Q4", 12: "Q4"}
    quarter_label = f"{quarter_map[today.month]} {today.year}"

    # Current transiting house for each malefic
    transit_fn = {"Saturn": _get_saturn_sign, "Mars": _get_mars_sign, "Rahu": _get_rahu_sign}
    malefic_houses: Dict[str, int] = {}
    for planet, fn in transit_fn.items():
        sign = fn(today)
        malefic_houses[planet] = _sign_to_house(sign, lagna_sign)

    h6_lord  = house_lords.get("6",  "")
    h10_lord = house_lords.get("10", "")
    h7_lord  = house_lords.get("7",  "")

    # Natal house of each lord (where it lives natally)
    natal_h6_lord_house  = planet_house.get(h6_lord,  6)
    natal_h10_lord_house = planet_house.get(h10_lord, 10)

    h6_afflictors:  List[str] = []
    h10_afflictors: List[str] = []
    h7_afflictors:  List[str] = []

    for planet, t_house in malefic_houses.items():
        # Malefic in natal H6 or on H6 lord's natal house
        if t_house == 6 or t_house == natal_h6_lord_house:
            h6_afflictors.append(planet)
        # Malefic in natal H10 or on H10 lord's natal house
        if t_house == 10 or t_house == natal_h10_lord_house:
            h10_afflictors.append(planet)
        # Malefic in H7
        if t_house == 7:
            h7_afflictors.append(planet)

    h6_afflicted  = len(h6_afflictors)  > 0
    h10_afflicted = len(h10_afflictors) > 0
    h7_afflicted  = len(h7_afflictors)  > 0

    advice_parts = []

    if h6_afflicted:
        planets_str = " + ".join(h6_afflictors)
        advice_parts.append(
            f"⚠ H6 afflicted by {planets_str}: Elevated indication of team friction or "
            f"subordinate attrition (traditional interpretive signal, not a statistical "
            f"probability). Practise defensive communication — avoid confrontational "
            f"language in group settings. Document agreements in writing."
        )

    if h10_afflicted:
        planets_str = " + ".join(h10_afflictors)
        advice_parts.append(
            f"⚠ H10 afflicted by {planets_str}: Leadership restructure likely. "
            f"Your direct manager may face pressure or change roles. "
            f"Manage upward carefully — visibility with senior sponsors is critical now."
        )

    if h7_afflicted:
        planets_str = " + ".join(h7_afflictors)
        advice_parts.append(
            f"⚠ H7 under pressure from {planets_str}: Partnership tensions or "
            f"client-facing friction possible. Clarify contracts and scope boundaries proactively."
        )

    if not advice_parts:
        advice_parts.append(
            "✓ No major malefic pressure on career houses this quarter. "
            "Workplace climate is stable — focus on output and visibility."
        )

    # Climate label
    total_afflictions = len(h6_afflictors) + len(h10_afflictors) + len(h7_afflictors)
    if total_afflictions >= 3:
        climate_label = "Storm Warning"
        climate_colour = "storm"
    elif total_afflictions >= 2:
        climate_label = "Turbulent"
        climate_colour = "turbulent"
    elif total_afflictions == 1:
        climate_label = "Caution"
        climate_colour = "caution"
    else:
        climate_label = "Clear"
        climate_colour = "clear"

    return {
        "h6_afflicted":    h6_afflicted,
        "h10_afflicted":   h10_afflicted,
        "h7_afflicted":    h7_afflicted,
        "climate_label":   climate_label,
        "climate_colour":  climate_colour,
        "afflictors":      {"h6": h6_afflictors, "h10": h10_afflictors, "h7": h7_afflictors},
        "malefic_houses":  malefic_houses,
        "advice":          " ".join(advice_parts),
        "quarter_label":   quarter_label,
    }


# ---------------------------------------------------------------------------
# 3. What-If Scenario Simulator
# ---------------------------------------------------------------------------

# ── Per-scenario opportunity event types ─────────────────────────────────────
# Each scenario defines which event types count as positive signals.
# Generic fallback used when action_key not found.
_SCENARIO_OPP_TYPES: Dict[str, set] = {
    "negotiate": {
        "SALARY_HIKE", "INCOME_INFLECTION", "BREAKTHROUGH",
        "PROMOTION",                          # designation bump implies pay rise
        "LEADERSHIP_EXPANSION",               # expanded scope → leverage for raise
    },
    "quit": {
        "JOB_CHANGE", "LATERAL_MOVE", "BREAKTHROUGH",
        "FOREIGN_POSTING",                    # relocation is a form of quit+join
        "ENTREPRENEURSHIP_WINDOW",            # quitting to found = strong quit signal
    },
    "promotion": {
        "PROMOTION", "BREAKTHROUGH", "LEADERSHIP_EXPANSION",
        "INCOME_INFLECTION",
        "SKILL_UPGRADE_PHASE",               # credentialing before promotion ask
    },
    "freelance": {
        "ENTREPRENEURSHIP_WINDOW", "INCOME_INFLECTION",
        "JOB_CHANGE",                        # voluntary exit to freelance
        "LATERAL_MOVE",                      # pivot to consulting/fractional
        "BREAKTHROUGH",
    },
    "join": {
        "JOB_CHANGE", "BREAKTHROUGH", "FOREIGN_POSTING",
        "SKILL_UPGRADE_PHASE",
    },
    "relocate": {
        "FOREIGN_POSTING", "JOB_CHANGE", "BREAKTHROUGH",
    },
    "invest": {
        "INCOME_INFLECTION", "BREAKTHROUGH", "SALARY_HIKE",
    },
}
_SCENARIO_OPP_TYPES["_default"] = {
    "PROMOTION", "BREAKTHROUGH", "SALARY_HIKE", "JOB_CHANGE",
    "INCOME_INFLECTION", "ENTREPRENEURSHIP_WINDOW", "SKILL_UPGRADE_PHASE",
}

# ── Per-scenario risk event types ─────────────────────────────────────────────
_SCENARIO_RISK_TYPES: Dict[str, set] = {
    "negotiate": {
        "RISK_PERIOD", "STABILITY", "STAGNATION", "CAREER_PLATEAU",
    },
    "quit": {
        "RISK_PERIOD", "STAGNATION", "CAREER_PLATEAU",
        "STABILITY",                         # stability period = poor exit window
    },
    "promotion": {
        "RISK_PERIOD", "STABILITY", "STAGNATION", "CAREER_PLATEAU",
    },
    "freelance": {
        "RISK_PERIOD", "STAGNATION",
        # NOT STABILITY — a stable employed phase is fine while bootstrapping
        # NOT LEADERSHIP_EXPANSION — broader scope can signal freelance readiness
    },
    "join": {
        "RISK_PERIOD", "STABILITY", "STAGNATION",
    },
    "relocate": {
        "RISK_PERIOD", "CAREER_PLATEAU",
    },
    "invest": {
        "RISK_PERIOD", "STAGNATION", "CAREER_PLATEAU",
    },
}
_SCENARIO_RISK_TYPES["_default"] = {
    "RISK_PERIOD", "STABILITY", "STAGNATION", "CAREER_PLATEAU",
}

# ── H8 risk weight: some scenarios treat H8 as transformation, not pure risk ──
_H8_RISK_WEIGHT: Dict[str, int] = {
    "negotiate": 2,    # H8 during salary talk → disruption, avoid
    "quit":      1,    # mild risk — H8 can force the exit
    "promotion": 2,    # H8 during promotion bid → obstruction
    "freelance": 0,    # H8 = career transformation → catalytic, not risky
    "join":      1,
    "relocate":  0,    # relocation often happens during H8/H12 transits
    "invest":    2,    # H8 = loss of capital
}

# ── Scenario-specific opportunity message fragments ───────────────────────────
_SCENARIO_OPP_MSG: Dict[str, str] = {
    "negotiate": "strong planetary momentum for salary negotiation",
    "quit":      "favourable window for a career exit or transition",
    "promotion": "auspicious period for promotion or role elevation",
    "freelance": "planetary support for independent ventures and freelance income",
    "join":      "strong dasha energy for joining or onboarding",
    "relocate":  "favourable planetary configuration for relocation",
    "invest":    "auspicious window for investments and financial crystallisation",
}

_H8_ACTIVATION_KEYWORDS = {"8", 8}

_ACTION_TEMPLATES = {
    "quit":         ("Quitting / Resigning", "employment"),
    "resign":       ("Quitting / Resigning", "employment"),
    "leave":        ("Leaving Current Role", "employment"),
    "start_business": ("Starting a Business", "entrepreneurship"),
    "freelance":    ("Going Freelance", "freelance"),
    "negotiate":    ("Salary Negotiation", "compensation"),
    "promotion":    ("Applying for Promotion", "promotion"),
    "join":         ("Joining a New Company", "employment"),
    "relocate":     ("Geographic Relocation", "relocation"),
    "invest":       ("Making a Major Investment", "financial"),
}

def compute_whatif_scenario(
    action_key: str,
    query_date: date,
    timeline_blocks: List[Dict],
) -> Dict:
    """Simulate a hypothetical career action against the next 6 months of the timeline.

    Args:
        action_key:      One of the keys in _ACTION_TEMPLATES (e.g. "quit", "negotiate").
        query_date:      The date from which to look forward (typically today).
        timeline_blocks: Full list of timeline AD blocks from build_career_timeline().

    Returns:
        {
          "action_label": str,
          "advisability": "Favourable" | "Caution" | "Unadvisable",
          "advisability_colour": "green" | "amber" | "red",
          "timing_note": str,
          "earliest_opportunity_date": str | None,
          "risk_factors": [str, ...],
          "opportunity_factors": [str, ...],
          "recommendation": str,
        }
    """
    # Fuzzy match: if action_key isn't an exact key, scan for substring match
    _resolved_key = action_key.lower().strip()
    if _resolved_key not in _ACTION_TEMPLATES:
        for _k in _ACTION_TEMPLATES:
            if _k in _resolved_key or _resolved_key in _k:
                _resolved_key = _k
                break
        else:
            # Last resort: keep original key, treat as free-form label
            _ACTION_TEMPLATES[_resolved_key] = (action_key.title(), "general")
    action_key = _resolved_key
    action_label = _ACTION_TEMPLATES.get(action_key, (action_key.title(), "general"))[0]
    horizon = query_date + timedelta(days=180)

    # Collect blocks that overlap the next 6 months
    def _parse_ym(s: str) -> date:
        y, m = s.split("-")
        return date(int(y), int(m), 1)

    relevant = [
        b for b in timeline_blocks
        if _parse_ym(b["end_date"]) >= query_date
        and _parse_ym(b["start_date"]) <= horizon
    ]

    risk_factors         = []
    opportunity_factors  = []
    earliest_opp: Optional[str] = None
    risk_score           = 0
    opp_score            = 0

    # Resolve per-scenario event maps (fall back to _default)
    _opp_types  = _SCENARIO_OPP_TYPES.get(action_key)  or _SCENARIO_OPP_TYPES["_default"]
    _risk_types = _SCENARIO_RISK_TYPES.get(action_key) or _SCENARIO_RISK_TYPES["_default"]
    _h8_weight  = _H8_RISK_WEIGHT.get(action_key, 2)
    _opp_msg    = _SCENARIO_OPP_MSG.get(action_key, "strong planetary momentum for this move")

    for block in relevant:
        et       = block.get("event_type", "")
        cs       = float(block.get("career_score", 0.5))
        houses   = block.get("active_houses", [])
        macro_hw = block.get("macro_headwinds", False)
        ad_lord  = block.get("ad_lord", "")
        start    = block.get("start_date", "")

        # Risk signals
        if et in _risk_types:
            risk_score += 2
            risk_factors.append(
                f"{ad_lord} AD ({start}): '{et}' — consolidation phase, "
                f"not aligned with {action_label.lower()}"
            )

        if any(str(h) in _H8_ACTIVATION_KEYWORDS for h in houses) and _h8_weight > 0:
            risk_score += _h8_weight
            if _h8_weight >= 2:
                risk_factors.append(
                    f"{ad_lord} AD: 8th house activated — sudden disruption or gap period; "
                    f"avoid irreversible moves during this window"
                )
            else:
                risk_factors.append(
                    f"{ad_lord} AD: 8th house active — transformation energy; "
                    f"proceed with a clear fallback plan"
                )

        if cs < 0.35:
            risk_score += 1
            risk_factors.append(
                f"{ad_lord} AD: low career score ({cs:.2f}) — diminished planetary support"
            )

        if macro_hw:
            risk_score += 1
            risk_factors.append(
                f"Macro headwinds active in {start[:7]} — sector contraction may delay offers"
            )

        # Opportunity signals
        if et in _opp_types:
            opp_score += 2
            _et_label = et.replace("_", " ").title()
            opportunity_factors.append(
                f"{ad_lord} AD ({start[:7]}): '{_et_label}' — {_opp_msg}"
            )
            if earliest_opp is None:
                earliest_opp = start

        if cs >= 0.65:
            opp_score += 1
            opportunity_factors.append(
                f"{ad_lord} AD: high career score ({cs:.2f}) — auspicious planetary window"
            )

    # Derive advisability
    net = opp_score - risk_score
    if net >= 2:
        advisability        = "Favourable"
        advisability_colour = "green"
        timing_note = (
            f"Planetary momentum over the next 6 months strongly supports {action_label.lower()}. "
            f"Act within the highlighted opportunity windows."
        )
    elif net >= 0:
        advisability        = "Caution"
        advisability_colour = "amber"
        timing_note = (
            f"Mixed signals for {action_label.lower()}. "
            f"Proceed only after securing the next step in hand — do not leave before landing."
        )
    else:
        advisability        = "Unadvisable"
        advisability_colour = "red"
        # Find earliest opportunity beyond the risk window (use per-scenario types)
        future_opps = [
            b for b in timeline_blocks
            if b.get("event_type") in _opp_types
            and _parse_ym(b["start_date"]) > horizon
        ]
        if future_opps:
            earliest_opp = future_opps[0]["start_date"]
            timing_note = (
                f"Astrologically unadvisable in the immediate window. "
                f"The upcoming planetary configuration shows a {risk_score}-point risk overlay. "
                f"The next strong opportunity window opens around {earliest_opp}. "
                f"Secure a concrete offer before making any irreversible moves."
            )
        else:
            timing_note = (
                f"Significant risk overlay detected in the next 6 months. "
                f"Recommend waiting for planetary support to build before acting."
            )

    recommendation = _build_whatif_recommendation(
        action_key, advisability, risk_factors, opportunity_factors, earliest_opp
    )

    return {
        "action_label":               action_label,
        "action_key":                 action_key,
        "advisability":               advisability,
        "advisability_colour":        advisability_colour,
        "timing_note":                timing_note,
        "earliest_opportunity_date":  earliest_opp,
        "risk_factors":               risk_factors,
        "opportunity_factors":        opportunity_factors,
        "recommendation":             recommendation,
        "risk_score":                 risk_score,
        "opp_score":                  opp_score,
    }


def _build_whatif_recommendation(
    action_key: str,
    advisability: str,
    risk_factors: List[str],
    opp_factors: List[str],
    earliest_opp: Optional[str],
) -> str:
    """Build a concise 2-3 sentence recommendation string."""
    if advisability == "Favourable":
        return (
            f"The stars align for this move. "
            f"{opp_factors[0] if opp_factors else 'Planetary support is strong.'}. "
            f"Initiate the process now and close during the peak transit windows shown in your heatmap."
        )
    elif advisability == "Caution":
        risk_note = risk_factors[0] if risk_factors else "Mixed signals present."
        return (
            f"Proceed with measured confidence. {risk_note}. "
            f"Have a signed offer or secured alternative before exiting any current arrangement."
        )
    else:
        risk_note = risk_factors[0] if risk_factors else "Risk overlay detected."
        opp_note  = f"The clearest astrological window opens at {earliest_opp}." if earliest_opp else ""
        return (
            f"Not advisable in this window. {risk_note}. "
            f"{opp_note} Use this period to prepare, build leverage, and line up options — "
            f"then execute when planetary support returns."
        )


# ---------------------------------------------------------------------------
# 4. Strategic Habit Tracker
# ---------------------------------------------------------------------------

# Maps each planet to 4 weekly executive habits (derived from _PLANET_REMEDY themes)
_PLANET_WEEKLY_HABITS: Dict[str, List[Dict]] = {
    "Sun": [
        {"week": 1, "title": "Visibility Audit",
         "detail": "Identify 3 senior stakeholders who do not know your current impact. Schedule a 15-min update with each.", "frequency": "Weekly"},
        {"week": 2, "title": "Authority Positioning",
         "detail": "Write and share one insight document (even 1 page) positioning you as a subject-matter authority in your domain.", "frequency": "Once"},
        {"week": 3, "title": "Decision Log",
         "detail": "Log every strategic decision you make this week. Present a summary to your manager as 'executive reporting.'", "frequency": "Weekly"},
        {"week": 4, "title": "Recognition Strategy",
         "detail": "Nominate a peer for recognition AND ensure at least one of your own achievements is formally credited in writing.", "frequency": "Once"},
    ],
    "Moon": [
        {"week": 1, "title": "Stakeholder Empathy Map",
         "detail": "For your 3 most difficult relationships at work, write down their core motivation and one thing they need from you.", "frequency": "Once"},
        {"week": 2, "title": "Communication Cadence",
         "detail": "Implement a consistent weekly check-in rhythm with your direct team. Consistency builds trust in Moon periods.", "frequency": "Weekly"},
        {"week": 3, "title": "Intuition Journal",
         "detail": "Each evening, note one decision you made on instinct. Review at week end — Moon periods amplify intuitive accuracy.", "frequency": "Daily"},
        {"week": 4, "title": "Network Nourishment",
         "detail": "Reach out to 5 people in your extended network with a value-add message (article, introduction, or compliment).", "frequency": "Once"},
    ],
    "Mars": [
        {"week": 1, "title": "Execution Sprint",
         "detail": "Pick one stalled project. Define a 5-day sprint goal and execute it to completion without scope creep.", "frequency": "Once"},
        {"week": 2, "title": "Conflict Resolution",
         "detail": "Address one unresolved workplace tension directly and constructively. Mars energy channelled toward resolution, not avoidance.", "frequency": "Once"},
        {"week": 3, "title": "Physical Resilience Ritual",
         "detail": "Add 20 minutes of physical activity daily. Mars rules physical stamina — bodily discipline translates directly to professional drive.", "frequency": "Daily"},
        {"week": 4, "title": "Courage Challenge",
         "detail": "Volunteer for one high-visibility, high-risk assignment this week. Mars periods reward those who step forward.", "frequency": "Once"},
    ],
    "Mercury": [
        {"week": 1, "title": "Resume & LinkedIn Refresh",
         "detail": "Update your resume and LinkedIn with the last 3 months of achievements. Mercury periods are optimal for positioning.", "frequency": "Once"},
        {"week": 2, "title": "Skill Acquisition",
         "detail": "Enrol in one short course, certification, or workshop directly relevant to your next career level.", "frequency": "Once"},
        {"week": 3, "title": "Strategic Networking",
         "detail": "Attend one industry event (virtual or in-person) and follow up with 3 new connections within 48 hours.", "frequency": "Once"},
        {"week": 4, "title": "Communication Precision",
         "detail": "Review and rewrite your 3 most-forwarded emails. Sharpen them. Mercury rewards those who communicate with precision.", "frequency": "Weekly"},
    ],
    "Jupiter": [
        {"week": 1, "title": "Mentor a Peer",
         "detail": "Identify someone junior you can guide. Teaching accelerates Jupiter's growth energy back onto you.", "frequency": "Weekly"},
        {"week": 2, "title": "Strategic Learning Block",
         "detail": "Dedicate 2 hours to reading a business, philosophy, or strategy book. Jupiter periods expand frameworks, not tactics.", "frequency": "Weekly"},
        {"week": 3, "title": "Advisory Circle Expansion",
         "detail": "Add 2 senior advisors or mentors to your professional circle. Reach out to one this week with a specific question.", "frequency": "Once"},
        {"week": 4, "title": "Gratitude & Reciprocity",
         "detail": "Write 3 genuine acknowledgment notes to colleagues or mentors who have contributed to your growth.", "frequency": "Once"},
    ],
    "Venus": [
        {"week": 1, "title": "Personal Brand Audit",
         "detail"
: "Review how you present in meetings, on video calls, and in written communications. Venus rewards aesthetic coherence.", "frequency": "Once"},
        {"week": 2, "title": "Partnership Cultivation",
         "detail": "Identify one strategic alliance or collaboration opportunity. Venus periods excel at building mutually beneficial relationships.", "frequency": "Once"},
        {"week": 3, "title": "Workspace Aesthetics",
         "detail": "Optimise your physical or digital workspace. A well-curated environment signals status and accelerates creative output.", "frequency": "Once"},
        {"week": 4, "title": "Client & Relationship Audit",
         "detail": "Review your top 5 professional relationships. Invest in deepening one — a personalised gesture, introduction, or shared experience.", "frequency": "Once"},
    ],
    "Saturn": [
        {"week": 1, "title": "Process Audit",
         "detail": "Document one recurring workflow. Identify one manual step that could be systematised or delegated permanently.", "frequency": "Once"},
        {"week": 2, "title": "Long-Game Planning",
         "detail": "Write a 1-year professional roadmap with quarterly milestones. Saturn rewards those who plan with discipline and patience.", "frequency": "Once"},
        {"week": 3, "title": "Accountability Ritual",
         "detail": "Create a simple weekly review: 3 wins, 3 learnings, 1 commitment for next week. Share it with a trusted peer.", "frequency": "Weekly"},
        {"week": 4, "title": "Skill Depth Investment",
         "detail": "Identify one foundational skill gap. Commit to a structured 30-day improvement plan with measurable milestones.", "frequency": "Once"},
    ],
    "Rahu": [
        {"week": 1, "title": "Pattern Interrupt",
         "detail": "Try one new approach to a recurring problem. Rahu favours those who experiment outside convention.", "frequency": "Once"},
        {"week": 2, "title": "Ambition Mapping",
         "detail": "Write down your most ambitious 3-year career goal as if it were already achieved. Identify the first concrete step.", "frequency": "Once"},
        {"week": 3, "title": "Cross-Industry Learning",
         "detail": "Spend 2 hours studying a domain completely outside your current field. Rahu cross-pollinates ideas across sectors.", "frequency": "Once"},
        {"week": 4, "title": "Digital Presence Sprint",
         "detail": "Publish one piece of content (article, post, or video) showcasing your expertise. Rahu amplifies those who put themselves forward.", "frequency": "Once"},
    ],
    "Ketu": [
        {"week": 1, "title": "Detachment Practice",
         "detail": "Identify one outcome you are overly attached to at work. Practice releasing the attachment — focus only on the action.", "frequency": "Daily"},
        {"week": 2, "title": "Deep Expertise Review",
         "detail": "Revisit your oldest and deepest area of mastery. Ketu periods resurface past-life skills for current application.", "frequency": "Once"},
        {"week": 3, "title": "Simplification Sprint",
         "detail": "Eliminate one recurring meeting, report, or commitment that no longer adds value. Ketu rewards those who strip the unnecessary.", "frequency": "Once"},
        {"week": 4, "title": "Contemplative Strategy",
         "detail": "Schedule 2 uninterrupted hours of solo thinking about where you are heading. No phone. No input. Just reflection.", "frequency": "Once"},
    ],
}


def compute_habit_plan(
    active_ad_lord: str,
    active_pd_lord: str,
) -> Dict:
    """Return the 4-week habit plan for the active dasha lords.

    Returns:
        {
          "primary_planet":  str,
          "secondary_planet": str,
          "weeks": [
            {"week": int, "title": str, "detail": str, "frequency": str,
             "planet": str, "is_current": bool, "pd_note": str}, ...
          ]
        }
    """
    primary   = active_ad_lord   or "Saturn"
    secondary = active_pd_lord   or "Saturn"

    primary_habits   = _PLANET_WEEKLY_HABITS.get(primary,   _PLANET_WEEKLY_HABITS["Saturn"])
    secondary_habits = _PLANET_WEEKLY_HABITS.get(secondary, _PLANET_WEEKLY_HABITS["Saturn"])

    weeks = []
    from datetime import date
    _today = date.today()
    _week_of_month = (_today.day - 1) // 7 + 1  # 1-4

    for w in primary_habits:
        wk = dict(w)
        wk["planet"]     = primary
        wk["is_current"] = (wk["week"] == _week_of_month)
        wk["pd_note"]    = ""
        weeks.append(wk)

    # Annotate week matching the PD lord's theme
    _pd_hint = secondary_habits[0] if secondary_habits else {}
    if weeks:
        weeks[0]["pd_note"] = (
            f"PD lord {secondary}: {_pd_hint.get('title','')}: "
            f"{_pd_hint.get('detail','')[:80]}..."
        ) if _pd_hint else ""

    return {
        "primary_planet":   primary,
        "secondary_planet": secondary,
        "weeks":            weeks,
    }


# ---------------------------------------------------------------------------
# 5. Master orchestrator: compute_all_micro_timing
# ---------------------------------------------------------------------------

def compute_all_micro_timing(
    today: "date",
    lagna_sign: str,
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    active_ad_lord: str,
    active_pd_lord: str,
    timeline_blocks: List[Dict],
    whatif_keys: Optional[List[str]] = None,
) -> Dict:
    """Compute all micro-timing modules in one call.

    Returns a dict with keys consumed by web_report.py's _build_micro_timing_html():
        negotiation_heatmap  — 3-month lunar heatmap
        stakeholder_radar    — workplace climate
        whatif_scenarios     — per-scenario advisability dict
        hora_timing          — 4-week habit plan (repurposed slot)
    """
    result: Dict = {}

    # 1. Negotiation Heatmap
    try:
        result["negotiation_heatmap"] = compute_negotiation_heatmap(
            today=today,
            lagna_sign=lagna_sign,
            planet_house=planet_house,
            house_lords=house_lords,
            active_ad_lord=active_ad_lord,
        )
    except Exception:
        result["negotiation_heatmap"] = {}

    # 2. Stakeholder Radar
    try:
        result["stakeholder_radar"] = compute_stakeholder_radar(
            today=today,
            lagna_sign=lagna_sign,
            planet_house=planet_house,
            house_lords=house_lords,
            active_ad_lord=active_ad_lord,
        )
    except Exception:
        result["stakeholder_radar"] = {}

    # 3. What-If Scenarios — default to 4 core scenarios when no list given
    _default_keys = ["negotiate", "quit", "promotion", "freelance"]
    _wi_keys = whatif_keys or _default_keys
    wi_scenarios: Dict = {}
    for _k in _wi_keys:
        try:
            wi_scenarios[_k] = compute_whatif_scenario(
                action_key=_k,
                query_date=today,
                timeline_blocks=timeline_blocks,
            )
        except Exception:
            pass
    result["whatif_scenarios"] = wi_scenarios

    # 4. Hora Timing (habit plan) — reused in the hora_timing slot
    try:
        _hp = compute_habit_plan(
            active_ad_lord=active_ad_lord,
            active_pd_lord=active_pd_lord,
        )
        result["hora_timing"] = {
            "weeks": [
                {
                    "week_label":  f"Week {w['week']}",
                    "title":       w["title"],
                    "detail":      w["detail"],
                    "frequency":   w.get("frequency",""),
                    "is_current":  w.get("is_current", False),
                    "pd_note":     w.get("pd_note",""),
                }
                for w in _hp.get("weeks", [])
            ]
        }
    except Exception:
        result["hora_timing"] = {}

    return result
