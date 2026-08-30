"""Business_Prediction/business_determination/d10_rectification.py
=====================================================================
D10 (Dashamsha) birth-time rectification sensitivity test.

Audit gap (item 4): the engine's D10-native evidence (see
house_evidence._d10_native_house_evidence) always reads a SINGLE, fixed
D10 chart -- built once from the recorded birth time -- with no way to
tell a reader whether that chart's decisive findings (10th/11th/3rd/5th
lord placement, 8th-house connections) are robust to ordinary birth-time
recording uncertainty, or whether they flip on a only-a-few-minutes
timing error. Since D10 lagna (and therefore every D10-native house
lord) is directly sensitive to the Ascendant, which moves roughly 1 deg
per 4 minutes of clock time, a birth time that is off by even a couple
of minutes can occasionally shift the D10 Lagna into a different D10
sign/segment and change which planet is being read as (say) the D10-H10
lord.

This module does NOT reimplement any chart math. It reuses:
  - jyotish.ephemeris.get_planet_longitudes() / get_house_cusps_placidus()
    (the same real Skyfield/DE421-backed primitives already used
    elsewhere in the repo, e.g. jyotish/engine_io.py, check_placidus_
    cusps.py) to recompute D1 planetary longitudes and the Ascendant at
    birth-time offsets, and
  - jyotish.astro.compute_d10_chart() (the existing, tested D10
    sign-construction function -- see jyotish/tests/test_d10_construction.py)
    to turn those shifted D1 longitudes into a D10 chart.

The only NEW logic here is: (1) shifting the birth clock time by a small
offset before calling the above primitives, (2) turning a D10 chart's
per-planet SIGN into a per-planet HOUSE (via whole-sign counting from the
D10 Lagna sign -- elementary arithmetic, not astronomical computation),
and (3) comparing the resulting decisive findings across offsets.

Degrades gracefully (never raises) to an explicit NO_DATA / EPHEMERIS_
UNAVAILABLE / COMPUTE_FAILED status with `stability: "UNKNOWN"` when the
payload lacks dob/tob/latitude/longitude, when Skyfield/DE421 isn't
available in this environment, or when any per-offset computation fails
-- matching the diagnostic conventions used throughout this package.

Public API
----------
    d10_rectification_sensitivity(payload) -> Dict[str, Any]
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .constants import _record_diagnostic

__all__ = ["d10_rectification_sensitivity"]

_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
_SIGN_LORD = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

# 10th (livelihood), 11th (gains), 3rd (initiative), 5th (strategy) --
# mirrors the same house set _d10_native_house_evidence() in
# house_evidence.py already treats as the D10-native decisive houses.
_DECISIVE_HOUSES: Tuple[int, ...] = (10, 11, 3, 5)

# +/- 1, 2, 5 minutes -- ordinary birth-time recording uncertainty range.
_OFFSETS_MIN: Tuple[int, ...] = (-5, -2, -1, 1, 2, 5)

_DOB_TOB_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
)


def _lon_to_sign_degree(lon: float) -> Tuple[str, float]:
    lon = float(lon) % 360.0
    idx = int(lon // 30)
    return _SIGN_ORDER[idx], lon - idx * 30.0


def _build_d10_house_map(
    planet_longitudes: Dict[str, float], lagna_longitude: float,
) -> Tuple[Dict[int, List[str]], Dict[int, str], str]:
    """Turns raw D1 longitudes + Ascendant longitude into a D10 house
    occupancy/house-lord map, via jyotish.astro.compute_d10_chart() (the
    existing, tested D10 sign-construction function) plus whole-sign
    house counting from the resulting D10 Lagna sign."""
    from jyotish.astro import compute_d10_chart

    planets_d1: Dict[str, Dict[str, Any]] = {}
    for planet, lon in (planet_longitudes or {}).items():
        sign, deg = _lon_to_sign_degree(lon)
        planets_d1[planet] = {"sign": sign, "degree": deg}

    lagna_sign, lagna_deg = _lon_to_sign_degree(lagna_longitude)
    d10 = compute_d10_chart(planets_d1, lagna_sign, lagna_deg)
    d10_lagna_sign = (d10.get("Lagna") or {}).get("sign", "")
    if not d10_lagna_sign:
        return {}, {}, ""

    lagna_idx = _SIGN_ORDER.index(d10_lagna_sign)
    sign_of_house = {h: _SIGN_ORDER[(lagna_idx + h - 1) % 12] for h in range(1, 13)}
    house_of_sign = {sign: h for h, sign in sign_of_house.items()}

    occupancy: Dict[int, List[str]] = {h: [] for h in range(1, 13)}
    for planet, pdata in d10.items():
        if planet == "Lagna":
            continue
        sign = pdata.get("sign", "")
        house_num = house_of_sign.get(sign)
        if house_num:
            occupancy[house_num].append(planet)

    house_lords = {h: _SIGN_LORD.get(sign_of_house[h], "") for h in range(1, 13)}
    return occupancy, house_lords, d10_lagna_sign


def _decisive_findings(occupancy: Dict[int, List[str]], house_lords: Dict[int, str]) -> Dict[str, Any]:
    def _native_house_of(planet: str) -> int:
        for h in range(1, 13):
            if planet in occupancy.get(h, []):
                return h
        return 0

    findings: Dict[str, Any] = {}
    connected_to_8: List[str] = []
    for h in _DECISIVE_HOUSES:
        lord = house_lords.get(h, "")
        lord_house = _native_house_of(lord) if lord else 0
        findings[f"H{h}_lord"] = lord
        findings[f"H{h}_lord_d10_house"] = lord_house
        if lord and lord_house == 8:
            connected_to_8.append(lord)
    findings["H8_occupants"] = sorted(set(occupancy.get(8, [])))
    findings["decisive_lords_connected_to_H8"] = sorted(set(connected_to_8))
    return findings


def _parse_birth_datetime(dob: str, tob: str) -> Optional[datetime]:
    combined = f"{dob} {tob}"
    for fmt in _DOB_TOB_FORMATS:
        try:
            return datetime.strptime(combined, fmt)
        except (ValueError, TypeError):
            continue
    return None


def d10_rectification_sensitivity(payload: Any) -> Dict[str, Any]:
    """Recomputes D10 lagna + decisive D10-native house-lord placements
    (10th/11th/3rd/5th lords, 8th-house connections) at birth-time
    offsets of -5,-2,-1,+1,+2,+5 minutes from the recorded birth time,
    and flags the result "STABLE" (all offsets agree with the recorded-
    time baseline) or "FRAGILE" (at least one offset changes a decisive
    finding).

    Requires payload.dob ("YYYY-MM-DD"), payload.tob ("HH:MM[:SS]"),
    payload.latitude, payload.longitude, and a working Skyfield/DE421
    ephemeris backend (jyotish.ephemeris.is_available()). Degrades
    gracefully (never raises) to an explicit diagnostic status +
    stability="UNKNOWN" otherwise.
    """
    try:
        from jyotish import ephemeris
        try:
            from jyotish.llm_policy import AYANAMSHA
        except Exception:
            AYANAMSHA = "LAHIRI"

        dob = str(getattr(payload, "dob", "") or "")
        tob = str(getattr(payload, "tob", "") or "")
        lat = getattr(payload, "latitude", None)
        lon = getattr(payload, "longitude", None)

        if not dob or not tob or lat is None or lon is None:
            return {
                "status": "NO_DATA", "stability": "UNKNOWN",
                "note": "D10 rectification sensitivity skipped: payload.dob/tob/latitude/longitude not fully available.",
            }
        if not ephemeris.is_available():
            return {
                "status": "EPHEMERIS_UNAVAILABLE", "stability": "UNKNOWN",
                "note": "D10 rectification sensitivity skipped: Skyfield/DE421 ephemeris backend not available in this environment.",
            }

        base_dt = _parse_birth_datetime(dob, tob)
        if base_dt is None:
            return {
                "status": "NO_DATA", "stability": "UNKNOWN",
                "note": f"D10 rectification sensitivity skipped: could not parse dob={dob!r}/tob={tob!r}.",
            }

        def _snapshot(dt: datetime) -> Optional[Tuple[Dict[str, Any], str]]:
            longitudes = ephemeris.get_planet_longitudes(dt, float(lat), float(lon), AYANAMSHA)
            if not longitudes:
                return None
            cusp_map = ephemeris.get_house_cusps_placidus(dt, float(lat), float(lon), AYANAMSHA)
            lagna_lon = cusp_map.get(1) if cusp_map else None
            if lagna_lon is None:
                return None
            occupancy, house_lords, d10_lagna_sign = _build_d10_house_map(longitudes, lagna_lon)
            if not occupancy or not house_lords:
                return None
            return _decisive_findings(occupancy, house_lords), d10_lagna_sign

        baseline = _snapshot(base_dt)
        if baseline is None:
            return {
                "status": "COMPUTE_FAILED", "stability": "UNKNOWN",
                "note": "D10 rectification sensitivity skipped: baseline D10 chart could not be computed from ephemeris.",
            }
        baseline_findings, baseline_lagna = baseline

        offset_results: List[Dict[str, Any]] = []
        fragile_reasons: List[Dict[str, Any]] = []
        for minutes in _OFFSETS_MIN:
            dt = base_dt + timedelta(minutes=minutes)
            snap = _snapshot(dt)
            if snap is None:
                offset_results.append({"offset_minutes": minutes, "status": "COMPUTE_FAILED"})
                continue
            findings, lagna_sign = snap
            diffs = {
                k: {"baseline": baseline_findings[k], "offset": findings[k]}
                for k in baseline_findings
                if baseline_findings[k] != findings[k]
            }
            if diffs:
                fragile_reasons.append({"offset_minutes": minutes, "diffs": diffs})
            offset_results.append({
                "offset_minutes": minutes,
                "d10_lagna": lagna_sign,
                "findings": findings,
                "matches_baseline": not diffs,
            })

        stability = "FRAGILE" if fragile_reasons else "STABLE"
        return {
            "status": "OK",
            "stability": stability,
            "baseline_d10_lagna": baseline_lagna,
            "baseline_findings": baseline_findings,
            "offsets_tested_minutes": list(_OFFSETS_MIN),
            "offset_results": offset_results,
            "fragile_reasons": fragile_reasons,
            "note": (
                "D10 birth-time rectification sensitivity: decisive D10-native findings "
                "(10th/11th/3rd/5th lord placement + 8th-house connections) recomputed at "
                "+/-1/2/5-minute birth-time offsets -> "
                + (
                    "STABLE (every tested offset reproduces the same decisive findings as the recorded birth time)."
                    if stability == "STABLE"
                    else "FRAGILE (at least one tested offset changes a decisive finding -- this chart's D10 reading is sensitive to birth-time precision; treat D10-native conclusions with added caution and prioritize birth-time rectification)."
                )
            ),
        }
    except Exception as exc:  # pragma: no cover - defensive
        _record_diagnostic("d10_rectification.d10_rectification_sensitivity", exc)
        return {
            "status": "ERROR", "stability": "UNKNOWN",
            "note": f"D10 rectification sensitivity failed: {exc}",
        }
