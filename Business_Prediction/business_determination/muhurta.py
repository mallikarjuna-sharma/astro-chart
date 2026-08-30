"""Business_Prediction/business_determination/muhurta.py
==========================================================
Electional-astrology (muhurta) calculator for business events.

Everything else in this package analyzes a FIXED natal chart (birth
data already given) to judge a person's aptitude/timing for business in
general (see timing.py's Mahadasha/Antardasha windows, which explicitly
disclaim -- see its `timing_precision` note -- that they are period-level,
"not muhurta-grade"). This module is the complementary, deliberately
SEPARATE capability: given a date RANGE and an event type, scan candidate
dates/times and rank them for auspiciousness, the way a traditional
"panchangam + muhurta shastra" lookup would for picking a launch date,
contract-signing date, branch-opening date, or partnership-registration
date. It does not touch or gate `compute_business_prediction()` in any way.

Ephemeris / Panchang reuse
---------------------------
This module reuses, rather than reimplements, two existing primitives:

  * jyotish/ephemeris.py -- Skyfield + DE421 (`de421.bsp`) sidereal
    longitude, sunrise/sunset (Julian Day, TT) computation. Same module
    Job_Career/micro_timing.py and jyotish/*.py already depend on.
    `is_available()` reports whether Skyfield + the ephemeris file loaded;
    if not, this module degrades to the EPHEMERIS_UNAVAILABLE diagnostic
    below rather than raising or fabricating positions.
  * jyotish/panchang.py -- the five classical Panchang limbs (tithi, vara,
    nakshatra, yoga, karana) + hora, computed from sidereal Sun/Moon
    longitude and local datetime. Written and tested independently of this
    module; reused verbatim here (`compute_panchang`).

Rahu Kalam / Yamaganda / Gulika Kalam
--------------------------------------
No existing module in this repo computes these three inauspicious daily
time-windows, so they are implemented here from the standard classical
rule: divide the sunrise-to-sunset daytime span into 8 equal parts
("horas" of daytime, not to be confused with the 24-hour planetary Hora
in panchang.py), and each weekday has a FIXED assigned portion-index
(1-8, counting from sunrise) for each of the three inauspicious periods.
This portion-index table is the standard one used across virtually all
published Panchang references/software (e.g. the commonly cited
Rahu Kalam / Yamaganda / Gulika Kalam weekday tables); it is a widely
used CONVENTION, not claimed here as uniquely authoritative classical
citation-verified doctrine down to the exact source verse.

Nakshatra suitability for business events
-------------------------------------------
The per-event favorable-nakshatra lists below are a curated subset drawn
from commonly cited muhurta-shastra guidance for commercial/mercantile
activity (e.g. Rohini, Pushya, Hasta, the three "Uttara" nakshatras, and
Anuradha are widely cited as favorable for starting trade/commerce and
for auspicious beginnings generally). This is NOT an exhaustive or
uniquely authoritative classical citation -- it is one commonly used
reading, the same "one documented reading, not the only one a
traditional astrologer would accept" caveat that applies to every other
module in this package (see constants.py MATURITY_STATEMENT).

Public API
----------
    find_business_muhurta(start_date, end_date, event_type, location,
                           native_payload=None) -> Dict[str, Any]
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .constants import MODEL_STATUS, CALIBRATION_STATUS, MATURITY_STATEMENT, _record_diagnostic

__all__ = [
    "find_business_muhurta",
    "EVENT_TYPES",
]

# ---------------------------------------------------------------------------
# Config / lookup tables
# ---------------------------------------------------------------------------

MAX_SCAN_DAYS = 90  # sanity cap on the scanned date range

EVENT_TYPES = (
    "BUSINESS_LAUNCH",
    "CONTRACT_SIGNING",
    "BRANCH_OPENING",
    "PARTNERSHIP_REGISTRATION",
)

# Classical basis: Tuesday (Mars, "Bhaumavara") is widely cited in muhurta
# guidance as unfavorable for INITIATING new ventures (Mars = conflict/
# rashness); Wednesday (Mercury -- commerce/trade), Thursday (Jupiter --
# expansion/wisdom/wealth) and Friday (Venus -- prosperity/harmony) are
# commonly favored for commercial undertakings. Saturday (Saturn) and
# Sunday (Sun) are treated here as neutral-leaning-cautious (Saturn =
# delay, Sun = authority/ego -- workable but not classically emphasized
# as *favorable* for commerce specifically), Monday (Moon) as mildly
# favorable (Moon = public/mass appeal, good for retail-facing launches).
_VARA_SCORE = {
    "Tuesday":   -25,
    "Wednesday":  15,
    "Thursday":   15,
    "Friday":     15,
    "Monday":      5,
    "Sunday":      0,
    "Saturday":  -10,
}

# Classical basis: "Rikta" (empty) tithis 4, 9, 14 (in each paksha) are
# widely cited as unfavorable for starting new undertakings; Amavasya
# (new moon, tithi 30) is avoided for auspicious beginnings generally;
# Shukla Paksha (waxing moon, tithi 1-15) is preferred over Krishna Paksha
# for growth-oriented new ventures (waxing moon = growth symbolism).
_RIKTA_TITHIS = {4, 9, 14, 19, 24, 29}  # rikta recurs each paksha (4/9/14 numbering)
_AMAVASYA_TITHI = 30

# Event -> favorable nakshatras (curated subset, see module docstring).
_EVENT_FAVORABLE_NAKSHATRAS: Dict[str, List[str]] = {
    "BUSINESS_LAUNCH": [
        "Rohini", "Pushya", "Hasta", "Uttara Phalguni", "Uttara Ashadha",
        "Uttara Bhadrapada", "Anuradha", "Revati",
    ],
    "CONTRACT_SIGNING": [
        "Hasta", "Pushya", "Anuradha", "Mrigashira", "Chitra", "Revati",
    ],
    "BRANCH_OPENING": [
        "Rohini", "Uttara Phalguni", "Uttara Ashadha", "Uttara Bhadrapada",
        "Pushya", "Dhanishtha",
    ],
    "PARTNERSHIP_REGISTRATION": [
        "Anuradha", "Mrigashira", "Hasta", "Revati", "Uttara Phalguni",
    ],
}

# Event -> primary significator planet, used only for the (optional)
# combustion check. Classical basis: Mercury = trade/commerce/contracts,
# Jupiter = expansion/growth (branch opening), Venus = harmony/agreements
# (partnership). This mirrors, in spirit, significators.py's use of
# planetary karakas elsewhere in this package, but is a separate, simpler
# single-planet mapping local to this module.
_EVENT_SIGNIFICATOR_PLANET: Dict[str, str] = {
    "BUSINESS_LAUNCH": "Mercury",
    "CONTRACT_SIGNING": "Mercury",
    "BRANCH_OPENING": "Jupiter",
    "PARTNERSHIP_REGISTRATION": "Venus",
}

# Combustion orb (degrees from Sun) by planet -- standard classical
# "Asta" combustion orbs (approximate, commonly cited values; varies
# slightly by source/retrograde status, not modeled here at that
# precision).
_COMBUSTION_ORB_DEG = {
    "Moon": 12.0, "Mars": 17.0, "Mercury": 14.0, "Jupiter": 11.0,
    "Venus": 10.0, "Saturn": 15.0,
}

# Rahu Kalam / Yamaganda / Gulika Kalam: weekday -> 1-indexed portion (of
# 8 equal portions of the sunrise-to-sunset daytime span). Standard
# convention used across published Panchang references (see module
# docstring). Python weekday(): Mon=0 ... Sun=6.
_RAHU_KALAM_PORTION = {6: 8, 0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3}
_YAMAGANDA_PORTION  = {6: 5, 0: 4, 1: 3, 2: 2, 3: 1, 4: 7, 5: 6}
_GULIKA_KALAM_PORTION = {6: 7, 0: 6, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1}

_TIER_THRESHOLDS = (("EXCELLENT", 80), ("GOOD", 60), ("ACCEPTABLE", 40))


# ---------------------------------------------------------------------------
# Ephemeris / panchang access (lazy imports so a missing skyfield install
# never breaks importing this module or the rest of the package)
# ---------------------------------------------------------------------------

def _ephemeris_module():
    try:
        from jyotish import ephemeris as _eph  # type: ignore
        return _eph
    except Exception as exc:
        _record_diagnostic("muhurta._load_ephemeris", exc)
        return None


def _panchang_module():
    try:
        from jyotish import panchang as _pn  # type: ignore
        return _pn
    except Exception as exc:
        _record_diagnostic("muhurta._load_panchang", exc)
        return None


# ---------------------------------------------------------------------------
# Kalam window computation
# ---------------------------------------------------------------------------

def _portion_window(sunrise_dt: datetime, sunset_dt: datetime, portion_1indexed: int) -> Tuple[datetime, datetime]:
    """1 of 8 equal portions of the sunrise->sunset daytime span."""
    total = (sunset_dt - sunrise_dt).total_seconds()
    portion_len = total / 8.0
    start = sunrise_dt + timedelta(seconds=portion_len * (portion_1indexed - 1))
    end = start + timedelta(seconds=portion_len)
    return start, end


def _kalam_windows(day: date, sunrise_dt: datetime, sunset_dt: datetime) -> Dict[str, Tuple[datetime, datetime]]:
    wd = day.weekday()
    return {
        "rahu_kalam": _portion_window(sunrise_dt, sunset_dt, _RAHU_KALAM_PORTION[wd]),
        "yamaganda": _portion_window(sunrise_dt, sunset_dt, _YAMAGANDA_PORTION[wd]),
        "gulika_kalam": _portion_window(sunrise_dt, sunset_dt, _GULIKA_KALAM_PORTION[wd]),
    }


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _best_window_avoiding_kalam(
    sunrise_dt: datetime, sunset_dt: datetime, kalams: Dict[str, Tuple[datetime, datetime]],
) -> Tuple[Optional[datetime], Optional[datetime], bool]:
    """Scan 1-hour blocks across the daytime span, preferring late-morning
    to early-afternoon blocks (commonly favored for commercial muhurta),
    and return the first preferred block that avoids all three kalams.
    Returns (start, end, avoided_all_kalam)."""
    blocks: List[Tuple[datetime, datetime]] = []
    cur = sunrise_dt
    while cur + timedelta(hours=1) <= sunset_dt:
        blocks.append((cur, cur + timedelta(hours=1)))
        cur += timedelta(hours=1)
    if not blocks:
        return None, None, False

    def _clean(block: Tuple[datetime, datetime]) -> bool:
        b_start, b_end = block
        for k_start, k_end in kalams.values():
            if _overlaps(b_start, b_end, k_start, k_end):
                return False
        return True

    clean_blocks = [b for b in blocks if _clean(b)]
    if not clean_blocks:
        # Nothing avoids all three kalams in a full hour block -- fall back
        # to the midpoint block (still reported, but the caller applies the
        # kalam-overlap scoring penalty).
        mid = blocks[len(blocks) // 2]
        return mid[0], mid[1], False

    # Prefer the block closest to the daytime midpoint (late-morning /
    # early-afternoon commercial preference) among the clean ones.
    midpoint = sunrise_dt + (sunset_dt - sunrise_dt) / 2
    clean_blocks.sort(key=lambda b: abs((b[0] - midpoint).total_seconds()))
    chosen = clean_blocks[0]
    return chosen[0], chosen[1], True


def _candidate_day_windows(
    sunrise_dt: datetime, sunset_dt: datetime,
    kalams: Dict[str, Tuple[datetime, datetime]], max_windows: int = 3,
) -> List[Tuple[datetime, datetime, bool]]:
    """Return several clean intraday candidates instead of one midpoint."""
    candidates: List[Tuple[datetime, datetime, bool]] = []
    cur = sunrise_dt
    while cur + timedelta(hours=1) <= sunset_dt:
        end = cur + timedelta(hours=1)
        clean = not any(_overlaps(cur, end, ks, ke) for ks, ke in kalams.values())
        if clean:
            candidates.append((cur, end, True))
        cur += timedelta(minutes=30)
    midpoint = sunrise_dt + (sunset_dt - sunrise_dt) / 2
    candidates.sort(key=lambda row: abs((row[0] - midpoint).total_seconds()))
    if candidates:
        selected: List[Tuple[datetime, datetime, bool]] = []
        for candidate in candidates:
            if all(not _overlaps(candidate[0], candidate[1], row[0], row[1]) for row in selected):
                selected.append(candidate)
                if len(selected) >= max_windows:
                    break
        return selected
    fallback = _best_window_avoiding_kalam(sunrise_dt, sunset_dt, kalams)
    return [fallback] if fallback[0] is not None else []


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_day(
    panchang: Dict[str, Any],
    event_type: str,
    kalam_avoided: bool,
    combustion_flag: bool,
    native_bonus: int,
    electional_adjustment: int = 0,
    electional_reasons: Optional[List[str]] = None,
) -> Tuple[int, List[str], List[str]]:
    score = 50  # neutral baseline
    reasons: List[str] = []   # client-safe, plain language
    citations: List[str] = []  # technical
    electional_reasons = electional_reasons or []

    vara = panchang.get("vara_name", "")
    v_score = _VARA_SCORE.get(vara, 0)
    score += v_score
    if v_score > 0:
        reasons.append(f"{vara} is a favorable day of the week for commerce.")
    elif v_score < 0:
        reasons.append(f"{vara} is classically discouraged for starting new ventures.")
    citations.append(f"Vara={vara} (lord {panchang.get('vara_lord','')}), weekday score {v_score:+d}.")

    tithi_num = panchang.get("tithi_num", 0)
    tithi_name = panchang.get("tithi_name", "")
    paksha = panchang.get("paksha", "")
    if tithi_num == _AMAVASYA_TITHI:
        score -= 40
        reasons.append("Amavasya (new moon) — generally avoided for auspicious beginnings.")
        citations.append(f"Tithi={tithi_name} ({tithi_num}) = Amavasya, heavy penalty applied.")
    elif tithi_num in _RIKTA_TITHIS:
        score -= 20
        reasons.append(f"{tithi_name} is a Rikta (empty) tithi — avoided for new undertakings.")
        citations.append(f"Tithi={tithi_name} ({tithi_num}) is Rikta, penalty applied.")
    else:
        if paksha == "Shukla":
            score += 10
            reasons.append("Waxing moon (Shukla Paksha) — favorable growth symbolism.")
        citations.append(f"Tithi={tithi_name} ({tithi_num}), paksha={paksha}.")

    nk_name = panchang.get("nakshatra_name", "")
    favorable = _EVENT_FAVORABLE_NAKSHATRAS.get(event_type, [])
    if nk_name in favorable:
        score += 25
        reasons.append(f"Moon in {nk_name} — a nakshatra classically favored for this kind of event.")
        citations.append(f"Nakshatra={nk_name}, in favorable list for {event_type}.")
    else:
        nk_lord = panchang.get("nakshatra_lord", "")
        if nk_lord in ("Saturn", "Mars", "Rahu", "Ketu"):
            score -= 5
            citations.append(f"Nakshatra={nk_name} (lord {nk_lord}, natural malefic) — not in favorable list.")
        else:
            citations.append(f"Nakshatra={nk_name} — neutral (not in curated favorable list for {event_type}).")

    if panchang.get("yoga_malefic"):
        score -= 10
        citations.append(f"Yoga={panchang.get('yoga_name','')} is classically inauspicious.")
    if panchang.get("karana_malefic"):
        score -= 10
        citations.append(f"Karana={panchang.get('karana_name','')} is classically inauspicious.")

    if kalam_avoided:
        score += 10
        reasons.append("Chosen time window avoids Rahu Kalam, Yamaganda and Gulika Kalam.")
    else:
        score -= 30
        reasons.append("Could not fully avoid Rahu Kalam / Yamaganda / Gulika Kalam on this day.")
    citations.append(f"Kalam avoidance in chosen window: {kalam_avoided}.")

    if combustion_flag:
        score -= 15
        planet = _EVENT_SIGNIFICATOR_PLANET.get(event_type, "")
        reasons.append(f"{planet} (significator for this event) is combust (too close to the Sun).")
        citations.append(f"{planet} within combustion orb of Sun.")

    hora_lord = panchang.get("hora_lord", "")
    event_planet = _EVENT_SIGNIFICATOR_PLANET.get(event_type, "")
    if hora_lord == event_planet:
        score += 8
        reasons.append(f"{hora_lord} Hora matches the event significator.")
        citations.append(f"Hora lord={hora_lord}; event significator match +8.")
    elif hora_lord in {"Jupiter", "Venus", "Mercury", "Moon"}:
        score += 3
        citations.append(f"Hora lord={hora_lord}; general benefic Hora +3.")
    elif hora_lord in {"Mars", "Saturn"}:
        score -= 4
        citations.append(f"Hora lord={hora_lord}; natural-malefic Hora -4.")

    if electional_adjustment:
        score += electional_adjustment
    reasons.extend(electional_reasons)
    citations.append(f"Electional lagna/Moon/event-significator adjustment {electional_adjustment:+d}.")

    if native_bonus:
        score += native_bonus
        reasons.append("Bonus: this date's day-lord/Moon placement resonates favorably with the native chart provided.")
        citations.append(f"Native cross-check bonus applied: +{native_bonus}.")

    score = max(0, min(100, score))
    return score, reasons, citations


def _tier_for_score(score: int) -> str:
    for tier, threshold in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "AVOID"


# ---------------------------------------------------------------------------
# Optional native cross-check (bonus only)
# ---------------------------------------------------------------------------

def _native_cross_check_bonus(native_payload: Any, panchang: Dict[str, Any]) -> int:
    """Very light-touch, OPTIONAL bonus scoring only -- never required, never
    penalizes. If the candidate day's Vara lord or Nakshatra lord matches a
    planet the native chart marks as a natal benefic occupying a kendra/
    trikona/2nd/11th house (wealth/growth houses), award a small bonus.
    Silently returns 0 on any missing/unexpected payload shape."""
    if native_payload is None:
        return 0


_NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
          "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]


def _tara_chandra_bala(native_payload: Any, panchang: Dict[str, Any], moon_lon: float) -> Tuple[int, List[str], Dict[str, Any]]:
    if native_payload is None:
        return 0, [], {"status": "NOT_REQUESTED"}
    adjustment = 0
    reasons: List[str] = []
    natal_nak = str(getattr(native_payload, "moon_nakshatra", "") or "")
    current_nak_num = int(panchang.get("nakshatra_num", 0) or 0)
    tara = None
    if natal_nak in _NAKSHATRAS and 1 <= current_nak_num <= 27:
        distance = (current_nak_num - (_NAKSHATRAS.index(natal_nak) + 1)) % 27 + 1
        tara = ((distance - 1) % 9) + 1
        if tara in {2, 4, 6, 8, 9}:
            adjustment += 6; reasons.append(f"Tara Bala is supportive (Tara {tara}).")
        elif tara in {3, 5, 7}:
            adjustment -= 8; reasons.append(f"Tara Bala is adverse (Tara {tara}).")
    natal_moon_sign = (getattr(native_payload, "planet_signs", {}) or {}).get("Moon", "")
    current_moon_sign = _SIGNS[int(moon_lon % 360.0 // 30.0)]
    chandra_house = None
    if natal_moon_sign in _SIGNS:
        chandra_house = ((_SIGNS.index(current_moon_sign) - _SIGNS.index(natal_moon_sign)) % 12) + 1
        if chandra_house in {1, 3, 6, 7, 10, 11}:
            adjustment += 6; reasons.append(f"Chandra Bala is supportive (Moon H{chandra_house} from natal Moon).")
        else:
            adjustment -= 4; reasons.append(f"Chandra Bala is not supportive (Moon H{chandra_house} from natal Moon).")
    return adjustment, reasons, {"status": "OK", "tara_number": tara, "chandra_house": chandra_house}
    try:
        from .house_evidence import _effective_benefic_malefic_sets, _rich_planet_dignities
        planet_house = getattr(native_payload, "planet_house", {}) or {}
        house_lords = getattr(native_payload, "house_lords", {}) or {}
        benefics, _ = _effective_benefic_malefic_sets(native_payload)
        dignities = _rich_planet_dignities(native_payload)
        good_houses = {1, 2, 5, 9, 10, 11}

        def _h(num: int) -> str:
            return house_lords.get(str(num), house_lords.get(num, ""))

        candidate_planets = {panchang.get("vara_lord", ""), panchang.get("nakshatra_lord", "")}
        candidate_planets.discard("")
        bonus = 0
        for p in candidate_planets:
            # A planet is not a natal-benefic compatibility signal merely
            # because it occupies/rules a nominally good house.
            if p not in benefics or dignities.get(p, "") == "DEBILITATED":
                continue
            ph = planet_house.get(p)
            if ph in good_houses:
                bonus += 5
            for gh in good_houses:
                if _h(gh) == p:
                    bonus += 2
        return min(bonus, 15)
    except Exception as exc:
        _record_diagnostic("muhurta._native_dasha_bonus", exc)
        return 0


def _electional_chart_adjustment(
    eph: Any, moment: datetime, lat: float, lon: float, tz_offset: float,
    longitudes: Dict[str, float], event_type: str, panchang: Optional[Dict[str, Any]] = None,
) -> Tuple[int, List[str], Dict[str, Any]]:
    """Small, bounded electional-chart layer on top of Panchang selection."""
    try:
        from jyotish.constants import _SIGN_LORD
        cusps = eph.get_house_cusps_placidus(moment, lat, lon, tz_offset_hours=tz_offset)
        if not cusps or 1 not in cusps:
            return 0, [], {"status": "UNAVAILABLE"}
        signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                 "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        asc_sign_index = int(float(cusps[1]) % 360.0 // 30.0)
        asc_sign = signs[asc_sign_index]
        asc_lord = _SIGN_LORD[asc_sign]

        def _house(planet: str) -> Optional[int]:
            value = longitudes.get(planet)
            if value is None:
                return None
            return ((int(float(value) % 360.0 // 30.0) - asc_sign_index) % 12) + 1

        adjustment = 0
        reasons: List[str] = []
        asc_lord_house = _house(asc_lord)
        event_planet = _EVENT_SIGNIFICATOR_PLANET.get(event_type, "")
        event_planet_house = _house(event_planet)
        moon_house = _house("Moon")
        if asc_lord_house in {1, 4, 5, 7, 9, 10}:
            adjustment += 8
            reasons.append(f"Electional Lagna lord {asc_lord} is in a kendra/trikona (H{asc_lord_house}).")
        elif asc_lord_house in {6, 8, 12}:
            adjustment -= 10
            reasons.append(f"Electional Lagna lord {asc_lord} falls in H{asc_lord_house}; initiation strength is reduced.")
        if event_planet_house in {1, 7, 10, 11}:
            adjustment += 8
            reasons.append(f"Event significator {event_planet} is angular/gains-linked (H{event_planet_house}).")
        elif event_planet_house in {6, 8, 12}:
            adjustment -= 10
            reasons.append(f"Event significator {event_planet} falls in H{event_planet_house}; caution is required.")
        if moon_house in {1, 4, 5, 7, 9, 10, 11}:
            adjustment += 5
        elif moon_house in {6, 8, 12}:
            adjustment -= 8
            reasons.append(f"Electional Moon falls in H{moon_house}, weakening the selected window.")

        # Muhurta Panchaka: tithi + vara + nakshatra + lagna, modulo 9.
        panchang = panchang or {}
        vara_num = {"Sunday": 1, "Monday": 2, "Tuesday": 3, "Wednesday": 4,
                    "Thursday": 5, "Friday": 6, "Saturday": 7}.get(panchang.get("vara_name"), 0)
        panchaka_remainder = (
            int(panchang.get("tithi_num", 0) or 0) + vara_num
            + int(panchang.get("nakshatra_num", 0) or 0) + asc_sign_index + 1
        ) % 9
        panchaka_name = {1: "Mrityu", 2: "Agni", 4: "Raja", 6: "Chora", 8: "Roga"}.get(panchaka_remainder)
        if panchaka_name:
            adjustment -= 10
            reasons.append(f"{panchaka_name} Panchaka is present (remainder {panchaka_remainder}).")

        # Degree-sensitive graha drishti to electional Lagna and event karaka.
        aspect_score = 0.0
        aspect_notes: List[str] = []
        patterns = {
            "Sun": (180.0,), "Moon": (180.0,), "Mars": (90.0, 180.0, 210.0),
            "Mercury": (180.0,), "Jupiter": (120.0, 180.0, 240.0),
            "Venus": (180.0,), "Saturn": (60.0, 180.0, 270.0),
            "Rahu": (180.0,), "Ketu": (180.0,),
        }
        natural_weight = {
            "Sun": -4.0, "Moon": 3.0, "Mars": -4.0, "Mercury": 2.0,
            "Jupiter": 4.0, "Venus": 4.0, "Saturn": -4.0, "Rahu": -4.0, "Ketu": -4.0,
        }
        if "Sun" in longitudes and "Moon" in longitudes:
            elongation = (float(longitudes["Moon"]) - float(longitudes["Sun"])) % 360.0
            natural_weight["Moon"] = 3.0 if elongation <= 180.0 else -3.0
        if "Mercury" in longitudes:
            for malefic in ("Sun", "Mars", "Saturn", "Rahu", "Ketu"):
                if malefic in longitudes:
                    delta = abs((float(longitudes["Mercury"]) - float(longitudes[malefic]) + 180.0) % 360.0 - 180.0)
                    if delta <= 8.0:
                        natural_weight["Mercury"] = -2.0
                        break

        ruled_houses: Dict[str, List[int]] = {}
        for house_no in range(1, 13):
            sign = signs[(asc_sign_index + house_no - 1) % 12]
            ruled_houses.setdefault(_SIGN_LORD[sign], []).append(house_no)
        functional_modifier = {
            planet: float(sum(h in {1, 5, 9} for h in houses) - sum(h in {6, 8, 12} for h in houses))
            for planet, houses in ruled_houses.items()
        }
        targets = {"Lagna": float(cusps[1])}
        if event_planet in longitudes:
            targets[event_planet] = float(longitudes[event_planet])
        for planet, angles in patterns.items():
            if planet not in longitudes:
                continue
            for target_name, target_lon in targets.items():
                separation = (target_lon - float(longitudes[planet])) % 360.0
                orb = min(abs(separation - angle) for angle in angles)
                if orb <= 6.0:
                    strength = 1.0 - orb / 6.0
                    signed = max(-5.0, min(5.0, natural_weight[planet] + functional_modifier.get(planet, 0.0))) * strength
                    aspect_score += signed
                    aspect_notes.append(
                        f"{planet} aspects {target_name} (orb {orb:.2f} degrees, "
                        f"strength {strength:.2f}, signed contribution {signed:+.2f})"
                    )
        adjustment += round(aspect_score)
        reasons.extend(aspect_notes)
        adjustment = max(-35, min(30, adjustment))
        return adjustment, reasons, {
            "status": "OK", "lagna_sign": asc_sign, "lagna_lord": asc_lord,
            "lagna_lord_house": asc_lord_house, "event_significator": event_planet,
            "event_significator_house": event_planet_house, "moon_house": moon_house,
            "panchaka_remainder": panchaka_remainder, "panchaka": panchaka_name or "CLEAR",
            "aspect_score": round(aspect_score, 2), "aspect_notes": aspect_notes,
        }
    except Exception as exc:
        _record_diagnostic("muhurta._electional_chart_adjustment", exc)
        return 0, [], {"status": "COMPUTATION_FAILED"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_business_muhurta(
    start_date: Any,
    end_date: Any,
    event_type: str,
    location: Optional[Dict[str, Any]],
    native_payload: Any = None,
) -> Dict[str, Any]:
    """Scan [start_date, end_date] and rank candidate business-event
    muhurta windows.

    Args:
        start_date, end_date : date/datetime (or ISO "YYYY-MM-DD" strings).
        event_type            : one of EVENT_TYPES.
        location              : {"lat": float, "lon": float,
                                  "tz_offset_hours": float (optional)}.
        native_payload         : optional natal chart object (same shape
                                  used elsewhere in this package -- needs
                                  .planet_house / .house_lords) for a
                                  BONUS-only personal-compatibility check.

    Returns a dict:
        {
          "status": "OK" | "RANGE_TOO_LARGE" | "NO_LOCATION" |
                    "INVALID_EVENT_TYPE" | "INVALID_DATES" |
                    "EPHEMERIS_UNAVAILABLE",
          "note": str,
          "event_type": str,
          "scanned_days": int,
          "results": [ { date, window_start, window_end, score_0_100,
                         tier, reasons, citations, panchang }, ... ]
                       sorted best-first,
          "model_status": ..., "calibration_status": ..., "maturity_statement": ...,
        }

    Never raises -- any unexpected failure downgrades to a diagnostic
    status with an empty results list, matching the rest of this
    package's conventions (see legal_risk.py / yogas.py doc for the same
    contract).
    """
    base = {
        "event_type": event_type,
        "results": [],
        "scanned_days": 0,
        "model_status": MODEL_STATUS,
        "calibration_status": CALIBRATION_STATUS,
        "maturity_statement": MATURITY_STATEMENT,
    }

    if event_type not in EVENT_TYPES:
        return {**base, "status": "INVALID_EVENT_TYPE",
                "note": f"event_type must be one of {EVENT_TYPES}."}

    try:
        sd = _coerce_date(start_date)
        ed = _coerce_date(end_date)
    except Exception:
        return {**base, "status": "INVALID_DATES",
                "note": "start_date/end_date could not be parsed as dates."}

    if sd is None or ed is None or ed < sd:
        return {**base, "status": "INVALID_DATES",
                "note": "start_date must be a valid date <= end_date."}

    span_days = (ed - sd).days + 1
    if span_days > MAX_SCAN_DAYS:
        return {**base, "status": "RANGE_TOO_LARGE",
                "note": f"Requested span is {span_days} days; max supported scan is "
                        f"{MAX_SCAN_DAYS} days to keep ephemeris computation bounded. "
                        f"Narrow the date range and retry."}

    if not location or "lat" not in location or "lon" not in location:
        return {**base, "status": "NO_LOCATION",
                "note": "location must be provided as {'lat': float, 'lon': float, "
                        "'tz_offset_hours': float (optional)}."}

    try:
        lat = float(location["lat"])
        lon = float(location["lon"])
    except Exception:
        return {**base, "status": "NO_LOCATION",
                "note": "location.lat/location.lon could not be parsed as numbers."}
    tz_offset = location.get("tz_offset_hours")

    eph = _ephemeris_module()
    pn = _panchang_module()
    if eph is None or pn is None or not eph.is_available():
        return {**base, "status": "EPHEMERIS_UNAVAILABLE",
                "note": "Skyfield/DE421 ephemeris (jyotish/ephemeris.py) or "
                        "jyotish/panchang.py is not available in this "
                        "environment -- cannot compute planetary longitudes."}

    if tz_offset is None:
        try:
            tz_offset = eph._infer_tz_offset_hours(lon)  # best-effort, same fallback ephemeris.py uses internally
        except Exception as exc:
            _record_diagnostic("muhurta.find_business_muhurta.timezone_fallback", exc)
            tz_offset = 5.5

    results: List[Dict[str, Any]] = []
    scanned = 0
    cur_day = sd
    while cur_day <= ed:
        scanned += 1
        try:
            sunrise_jd = eph.get_sunrise_jd(cur_day, lat, lon, tz_offset)
            sunset_jd = eph.get_sunset_jd(cur_day, lat, lon, tz_offset)
            if sunrise_jd is not None and sunset_jd is not None:
                sunrise_dt = eph.tt_jd_to_local_datetime(sunrise_jd, tz_offset)
                sunset_dt = eph.tt_jd_to_local_datetime(sunset_jd, tz_offset)
                kalams = _kalam_windows(cur_day, sunrise_dt, sunset_dt)
                for window in _candidate_day_windows(sunrise_dt, sunset_dt, kalams):
                    record = _evaluate_day(
                        eph, pn, cur_day, lat, lon, tz_offset, event_type,
                        native_payload, selected_window=window,
                    )
                    if record is not None:
                        results.append(record)
        except Exception as exc:
            _record_diagnostic("muhurta.find_business_muhurta.candidate_day", exc)
        cur_day += timedelta(days=1)

    results.sort(key=lambda r: r["score_0_100"], reverse=True)

    return {
        **base,
        "status": "OK",
        "scanned_days": scanned,
        "candidate_windows_evaluated": len(results),
        "results": results,
        "note": f"Scanned {scanned} day(s) for {event_type}. Ranked best-first; "
                f"see each result's 'citations' for technical basis and 'reasons' "
                f"for a client-safe plain-language summary.",
    }


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    raise ValueError(f"Unsupported date value: {value!r}")


def _evaluate_day(
    eph: Any, pn: Any, day: date, lat: float, lon: float, tz_offset: float,
    event_type: str, native_payload: Any,
    selected_window: Optional[Tuple[datetime, datetime, bool]] = None,
) -> Optional[Dict[str, Any]]:
    sunrise_jd = eph.get_sunrise_jd(day, lat, lon, tz_offset)
    sunset_jd = eph.get_sunset_jd(day, lat, lon, tz_offset)
    if sunrise_jd is None or sunset_jd is None:
        return None
    sunrise_dt = eph.tt_jd_to_local_datetime(sunrise_jd, tz_offset)
    sunset_dt = eph.tt_jd_to_local_datetime(sunset_jd, tz_offset)
    if sunset_dt <= sunrise_dt:
        return None

    kalams = _kalam_windows(day, sunrise_dt, sunset_dt)
    if selected_window is None:
        win_start, win_end, kalam_avoided = _best_window_avoiding_kalam(sunrise_dt, sunset_dt, kalams)
    else:
        win_start, win_end, kalam_avoided = selected_window
    if win_start is None:
        return None

    midpoint_dt = win_start + (win_end - win_start) / 2
    sunrise_hour = sunrise_dt.hour + sunrise_dt.minute / 60.0

    longitudes = eph.get_planet_longitudes(midpoint_dt, lat, lon, tz_offset_hours=tz_offset)
    if not longitudes:
        return None
    sun_lon = longitudes.get("Sun")
    moon_lon = longitudes.get("Moon")
    if sun_lon is None or moon_lon is None:
        return None

    panchang = pn.compute_panchang(sun_lon, moon_lon, midpoint_dt, sunrise_hour=sunrise_hour)

    sig_planet = _EVENT_SIGNIFICATOR_PLANET.get(event_type, "")
    combustion_flag = False
    sig_lon = longitudes.get(sig_planet)
    if sig_lon is not None and sig_planet in _COMBUSTION_ORB_DEG:
        diff = abs((sig_lon - sun_lon + 180) % 360 - 180)
        combustion_flag = diff <= _COMBUSTION_ORB_DEG[sig_planet]

    native_bonus = _native_cross_check_bonus(native_payload, panchang)
    electional_adjustment, electional_reasons, electional_chart = _electional_chart_adjustment(
        eph, midpoint_dt, lat, lon, tz_offset, longitudes, event_type, panchang
    )
    bala_adjustment, bala_reasons, bala_detail = _tara_chandra_bala(native_payload, panchang, moon_lon)
    electional_adjustment += bala_adjustment
    electional_reasons.extend(bala_reasons)

    score, reasons, citations = _score_day(
        panchang, event_type, kalam_avoided, combustion_flag, native_bonus,
        electional_adjustment, electional_reasons,
    )
    tier = _tier_for_score(score)

    return {
        "date": day.isoformat(),
        "window_start": win_start.strftime("%Y-%m-%d %H:%M"),
        "window_end": win_end.strftime("%Y-%m-%d %H:%M"),
        "score_0_100": score,
        "tier": tier,
        "reasons": reasons,
        "citations": citations,
        "electional_chart": electional_chart,
        "native_bala": bala_detail,
        "panchang": {
            "tithi": panchang.get("tithi_name"),
            "paksha": panchang.get("paksha"),
            "vara": panchang.get("vara_name"),
            "nakshatra": panchang.get("nakshatra_name"),
            "yoga": panchang.get("yoga_name"),
            "karana": panchang.get("karana_name"),
        },
        "rahu_kalam": f"{kalams['rahu_kalam'][0].strftime('%H:%M')}-{kalams['rahu_kalam'][1].strftime('%H:%M')}",
        "yamaganda": f"{kalams['yamaganda'][0].strftime('%H:%M')}-{kalams['yamaganda'][1].strftime('%H:%M')}",
        "gulika_kalam": f"{kalams['gulika_kalam'][0].strftime('%H:%M')}-{kalams['gulika_kalam'][1].strftime('%H:%M')}",
    }
