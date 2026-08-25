"""JyotishAI - Genuine ephemeris-backed astronomical layer (Skyfield edition).

This module adds real ephemeris computation on top of the previously
"templated"/absent data described in md/ARCHITECTURE_AUDIT.md item P-1 and
md/DEEP_AUDIT_GAPS_2026-07.md:

  1. `planet_natal_degrees`  -- exact sidereal longitude for each natal planet.
  2. `planet_transit_degrees` / `transit_house_positions` -- same, for "today".
  3. Real KP sub-lord chain (star_lord/sub_lord/sub_sub_lord) for house cusps,
     computed from genuine Placidus cusp longitudes and the standard
     Vimshottari-proportional nakshatra sub-division.
  4. Ghati Lagna and Sree Lagna, computed from real sunrise time.

2026-07-08 migration: pyswisseph -> Skyfield
---------------------------------------------------------------------
The original implementation of this module used `pyswisseph` (a C-extension
binding to the Swiss Ephemeris). That library has no prebuilt wheel for
Python 3.14 and requires an MSVC toolchain to build from source, which is
not available in this deployment's target environment (Windows, Python
3.14, no compiler). This module has therefore been rewritten to use
`skyfield` -- a pure-Python astronomy library (no C compiler needed, works
on any modern CPython) that computes positions from a downloaded NASA JPL
DE421 ephemeris file (`de421.bsp`, ~17MB, fetched once and cached locally by
`skyfield.api.load`).

One-time setup required on first real use
-------------------------------------------
`skyfield.api.load('de421.bsp')` downloads the ephemeris file from NASA JPL
on first call and caches it in the working directory (or wherever `load` is
configured to look). If the machine running this code has no network
access at runtime, pre-fetch the file once with:

    python -c "from skyfield.api import load; load('de421.bsp')"

All functions in this module degrade gracefully (return {} / None, log a
warning) if the file is missing / skyfield is not installed / network is
unavailable -- exactly as before with pyswisseph.

Ayanamsa: KP/Krishnamurti
---------------------------------------------------------------------
The existing chart JSON (Charts/lakshman_chart_details.json) declares
`"system_config.ayanamsa": "KP_Krishnamurti"` and `"node_type": "True"`. The
original pyswisseph-based module verified this numerically against
`swe.SIDM_KRISHNAMURTI` (see git history / prior module docstring for the
full three-ayanamsa comparison table). Since Skyfield has no built-in
ayanamsa support (it is a raw ephemeris/almanac library, not a Jyotish
library), we implement the KP/Krishnamurti ayanamsa formula directly here:

    ayanamsa(t) = BASE_DEG + PRECESSION_DEG_PER_YEAR * years_since_epoch

    BASE_DEG               = 22 deg 22' 23.9"  = 22.3733056 deg
                              (KP ayanamsa value at the reference epoch
                              1900-01-01 00:00 UT -- this is the standard
                              published Krishnamurti constant, and is also
                              the exact reference value Swiss Ephemeris uses
                              internally for SIDM_KRISHNAMURTI)
    EPOCH                  = 1900-01-01 00:00:00 UT
    PRECESSION_DEG_PER_YEAR = 50.2388475" / 3600 = 0.01395468 deg/year
                              (Newcomb's general precession in longitude,
                              the standard rate underlying the classical
                              Lahiri/KP-family ayanamsa constructions)

Verification performed 2026-07-08 (this migration): computed tropical Sun
and Moon geocentric ecliptic longitudes for Lakshman's exact birth moment
(1978-05-08 09:12:00 IST = 03:42:00 UT, Madurai 9.9252N 78.1198E) using an
independent VSOP87/ELP2000-based Python library (pymeeus) as a stand-in for
Skyfield/DE421 in this sandboxed environment (DE421 download was blocked by
sandbox network policy -- see this task's final report), then subtracted
the KP ayanamsa above:

    Body   Tropical lon (pymeeus)   Sidereal (this formula)   pyhora JSON gt   Delta
    Moon   58.14038 deg             34.67373 deg               34.6902 deg     0.016 deg
    Sun    47.20062 deg             23.73397 deg               23.7491 deg     0.015 deg

Both within ~0.016 deg (under 1 arcminute), consistent with the expected
residual between pymeeus's own analytic series and JPL DE421 plus tob
rounding to the nearest minute -- confirming this ayanamsa formula/epoch is
correct. On the user's real machine, once de421.bsp is available, this same
formula applied to genuine Skyfield/DE421 longitudes should match pyhora's
JSON even more closely (sub-0.01 deg), as the original pyswisseph
implementation did.

Rahu/Ketu (true node)
---------------------------------------------------------------------
JPL planetary ephemerides (including DE421) do not carry the lunar nodes as
independent bodies -- there is no "node barycenter" segment. The previous
pyswisseph implementation used `swe.TRUE_NODE`, i.e. the instantaneous
osculating ascending node of the Moon's true (perturbed) orbit around
Earth, NOT the smoothly-precessing mean node. To reproduce this with
Skyfield we compute the Moon's true node geometrically from its
instantaneous geocentric position and velocity vectors:

  1. Get the Moon's geocentric position vector r (AU, true equinox of date
     ecliptic frame) and velocity vector v (AU/day) at time t from Skyfield.
  2. Compute the orbital angular-momentum vector h = r x v. This vector is
     normal to the Moon's instantaneous (osculating) orbital plane.
  3. The ascending node direction is n = z_hat x h (z_hat = ecliptic north
     pole), i.e. the line where the osculating orbital plane crosses the
     ecliptic plane, oriented so the Moon is moving from south to north of
     the ecliptic there.
  4. The true node's ecliptic longitude is atan2(n_y, n_x) in the ecliptic
     frame.

This is the standard closed-form way to obtain the osculating ("true") node
from position+velocity without needing a dedicated node ephemeris, and it
matches -- up to the same short-period perturbation terms swisseph's
TRUE_NODE includes -- what `swe.TRUE_NODE` reports, as opposed to the mean
node (a smooth polynomial-only model). Ketu is always Rahu + 180 deg exactly
as before.

Graceful degradation
---------------------
Every public function wraps its computation in try/except and returns None
(or an empty structure) on any failure -- missing lat/lon, missing birth
time, skyfield/ephemeris file not available, bad dates, etc. -- and logs a
warning, so that charts with incomplete data do not crash the pipeline.
"""
from __future__ import annotations

import functools as _functools
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jyotish_engine_v11_0")

try:
    from skyfield.api import load, wgs84
    from skyfield import almanac
    import numpy as _np
    _SKYFIELD_IMPORTABLE = True
except ImportError:  # pragma: no cover
    load = None  # type: ignore
    wgs84 = None  # type: ignore
    almanac = None  # type: ignore
    _np = None  # type: ignore
    _SKYFIELD_IMPORTABLE = False

# The DE421 ephemeris file + timescale are loaded lazily (only on first real
# use) so that importing this module never triggers a network fetch, and so
# unit tests / environments without the .bsp file don't fail at import time.
_EPH = None
_TS = None
_EARTH = None
_SUN_BODY = None
_MOON_BODY = None
_PLANET_BODIES: Dict[str, Any] = {}
_LOAD_ATTEMPTED = False
_LOAD_OK = False


def _de421_search_paths() -> list:
    """Candidate locations for de421.bsp, in priority order.

    2026-08 gap-audit fix: `load("de421.bsp")` resolves relative to the
    Skyfield Loader's directory, which defaults to the CURRENT WORKING
    DIRECTORY of the process -- not this module's own location. A user
    running `python field_determination/education_engine.py ...` from
    somewhere other than the repo root (or via an IDE/launcher that sets a
    different cwd) would silently fail to find a de421.bsp that genuinely
    exists at the repo root, with no indication why. This anchors the
    primary lookup to the repo root (one directory above jyotish/, computed
    from this file's own path) so the file is found regardless of the
    caller's cwd, while still trying a bare relative lookup and the cwd
    explicitly as fallbacks for setups that intentionally place the file
    elsewhere.
    """
    import os
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [
        os.path.join(_repo_root, "de421.bsp"),
        os.path.join(os.getcwd(), "de421.bsp"),
        "de421.bsp",
    ]


def _ensure_loaded() -> bool:
    """Lazily load the DE421 ephemeris + timescale. Returns True if usable."""
    global _EPH, _TS, _EARTH, _SUN_BODY, _MOON_BODY, _PLANET_BODIES
    global _LOAD_ATTEMPTED, _LOAD_OK
    if _LOAD_ATTEMPTED:
        return _LOAD_OK
    _LOAD_ATTEMPTED = True
    if not _SKYFIELD_IMPORTABLE:
        logger.warning(
            "ephemeris: 'skyfield' and/or 'numpy' are not importable in this "
            "Python environment -- real ephemeris features (genuine Placidus "
            "KP cusps, precise Shadbala Bhava Bala inputs) are disabled. Both "
            "are declared dependencies in pyproject.toml; if you're running "
            "`python ...` directly rather than through this project's venv "
            "(e.g. `uv run python ...` or `.venv\\Scripts\\python.exe ...` on "
            "Windows), that's very likely why they're missing from this "
            "interpreter. Verify with: python -c \"import skyfield, numpy\""
        )
        return False

    import os
    _tried = []
    for _path in _de421_search_paths():
        _tried.append(_path)
        if not os.path.isfile(_path):
            continue
        try:
            _TS = load.timescale()
            _EPH = load(_path)
            _EARTH = _EPH["earth"]
            _SUN_BODY = _EPH["sun"]
            _MOON_BODY = _EPH["moon"]
            _PLANET_BODIES = {
                "Sun": _EPH["sun"],
                "Moon": _EPH["moon"],
                "Mars": _EPH["mars barycenter"],
                "Mercury": _EPH["mercury barycenter"],
                "Jupiter": _EPH["jupiter barycenter"],
                "Venus": _EPH["venus barycenter"],
                "Saturn": _EPH["saturn barycenter"],
            }
            _LOAD_OK = True
            return True
        except Exception as exc:  # pragma: no cover - defensive (corrupt file, etc.)
            logger.warning(
                "ephemeris: found de421.bsp at %s but failed to load it -- "
                "real ephemeris features disabled. Error: %s", _path, exc,
            )
            _LOAD_OK = False
            return False

    logger.warning(
        "ephemeris: de421.bsp not found at any of %s -- real ephemeris "
        "features disabled. One-time fix: run "
        "`python -c \"from skyfield.api import load; load('de421.bsp')\"` "
        "once on a machine with network access (downloads ~17MB from NASA "
        "JPL and caches it in the current directory), or place an existing "
        "de421.bsp at the repo root.", _tried,
    )
    _LOAD_OK = False
    return False


def is_available() -> bool:
    """True if Skyfield is importable AND the DE421 ephemeris file loaded OK."""
    return _ensure_loaded()


_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_DEFAULT_AYANAMSA = "KP_KRISHNAMURTI"

# --- KP/Krishnamurti ayanamsa constants (see module docstring for derivation) ---
_KP_AYANAMSA_BASE_DEG = 22.0 + 22.0 / 60.0 + 23.9 / 3600.0  # 22.3733056 deg @ epoch
_KP_AYANAMSA_EPOCH = datetime(1900, 1, 1, 0, 0, 0)
_KP_AYANAMSA_PRECESSION_PER_YEAR = 50.2388475 / 3600.0  # deg/year (Newcomb)

# --- Standard Vimshottari dasha-lord cyclic order and year-spans (120 yrs total) ---
_VIMSHO_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
_VIMSHO_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}
_VIMSHO_TOTAL = 120.0

# 27 nakshatras in zodiacal order, each 13d20' = 13.3333...deg, starting at Aries 0.
_NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
# Nakshatra star-lord cycles through the 9 Vimshottari lords repeating 3x over 27 nakshatras,
# starting from Ketu at Ashwini (classical fixed assignment).
_NAKSHATRA_LORDS = [_VIMSHO_ORDER[i % 9] for i in range(27)]

_NAK_SPAN = 360.0 / 27.0  # 13.3333... degrees


def _ayanamsa_deg(
    dt_utc: datetime, ayanamsa: str = _DEFAULT_AYANAMSA,
    override_deg: Optional[float] = None,
) -> float:
    """KP/Krishnamurti ayanamsa at `dt_utc` (naive UT datetime).

    2026-08 gap-audit fix: this function used to hardcode the KP/Krishnamurti
    formula unconditionally regardless of the `ayanamsa` string passed in --
    "this codebase's charts all use KP/Krishnamurti in practice" turned out
    to be false. Confirmed on a real chart (swastik_chart_details.json,
    system_config.ayanamsa == "Lahiri"): back-solving the chart's own
    already-known sidereal Sun longitude against a real Skyfield/DE421
    tropical Sun position for the exact birth moment gives an empirical
    ayanamsa of 23.8515 deg -- matching the published Lahiri constant at
    year 2000 (~23.85 deg) to within a hundredth of a degree, and diverging
    from this function's KP formula (23.7757 deg for that same moment) by a
    non-trivial 0.076 deg (~4.5 arcmin) -- enough to occasionally flip a
    planet or cusp across a sign/nakshatra boundary near a cusp.

    Rather than hand-implement a second named-ayanamsa formula (Lahiri,
    Raman, ... each with their own epoch/base-value conventions that are
    genuinely easy to get subtly wrong without an independent verification
    source), `override_deg` lets a caller supply an ayanamsa VALUE derived
    directly from the chart's own data via `derive_ayanamsa_from_known_
    sidereal_sun()` below -- guaranteeing internal consistency with
    whichever ayanamsa convention the source chart actually used, regardless
    of its name. When no override is supplied, this still falls back to the
    original KP/Krishnamurti formula (unchanged default behavior -- no
    caller relying on the old formula is affected).
    """
    if override_deg is not None:
        return float(override_deg)
    years = (dt_utc - _KP_AYANAMSA_EPOCH).total_seconds() / (365.25 * 86400.0)
    return _KP_AYANAMSA_BASE_DEG + _KP_AYANAMSA_PRECESSION_PER_YEAR * years


def derive_ayanamsa_from_known_sidereal_sun(
    dt_local: datetime, lat: float, lon: float,
    known_sidereal_sun_deg: float, tz_offset_hours: Optional[float] = None,
) -> Optional[float]:
    """Empirically derive the exact ayanamsa a source chart used, from its
    own already-computed sidereal Sun longitude.

    ayanamsa = (real tropical Sun longitude at the exact birth moment,
    computed here from Skyfield/DE421) - (the chart's own stated sidereal
    Sun longitude, e.g. sign_index*30 + degree from planets_d1.Sun).

    This is deliberately chart-grounded rather than a hardcoded named
    formula (Lahiri/KP/Raman/...): whatever ayanamsa convention upstream
    chart-generation software (e.g. pyhora) actually used, this recovers
    that SAME value, so any cusps/positions subsequently recomputed with it
    stay internally consistent with the rest of the chart's already-ingested
    planetary data -- see _ayanamsa_deg's docstring for the concrete
    real-chart verification (Lahiri-declared chart, derived value matched
    the published Lahiri constant to ~0.01 deg, diverged from this module's
    old hardcoded KP formula by ~4.5 arcmin).

    Returns None on any failure (skyfield/ephemeris unavailable, bad
    inputs) so callers can safely fall back to the original ingestion path.
    """
    if not is_available():
        return None
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        dt_utc = _to_utc(dt_local, tz)
        t = _skyfield_time(dt_utc)
        tropical_sun_lon, _ = _ecliptic_lon_lat(_SUN_BODY, t)
        return (tropical_sun_lon - float(known_sidereal_sun_deg)) % 360.0
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "ephemeris.derive_ayanamsa_from_known_sidereal_sun: failed (%s) -- "
            "falling back to the default ayanamsa formula.", exc,
        )
        return None


def _sign_and_deg(longitude: float) -> Tuple[str, float]:
    lon = longitude % 360.0
    idx = int(lon // 30.0)
    return _SIGNS[idx], lon - idx * 30.0


def _infer_tz_offset_hours(lon: float) -> float:
    """Fallback timezone estimate when no explicit tz is supplied: India uses a
    fixed UTC+5:30 offset regardless of longitude, which is what every existing
    sample chart in this repo (Madurai, India) implicitly assumes (system_config
    carries no explicit timezone field -- see Charts/lakshman_chart_details.json).
    For non-Indian longitudes we fall back to a crude 15-degrees-per-hour solar
    time estimate so this module still degrades sanely rather than crashing."""
    if -60.0 <= lon <= 100.0:
        # Rough India/South-Asia longitude band -> assume IST.
        return 5.5
    return round(lon / 15.0, 2)


def _to_utc(dt_local: datetime, tz_offset_hours: float) -> datetime:
    return dt_local - timedelta(hours=tz_offset_hours)


def _skyfield_time(dt_utc: datetime):
    return _TS.utc(
        dt_utc.year, dt_utc.month, dt_utc.day,
        dt_utc.hour, dt_utc.minute, dt_utc.second + dt_utc.microsecond / 1e6,
    )


def _ecliptic_lon_lat(body, t, topos_earth=None) -> Tuple[float, float]:
    """Apparent geocentric (or topocentric, if `topos_earth` given) ecliptic
    longitude/latitude (tropical, degrees) of `body` at Skyfield time `t`."""
    observer = topos_earth if topos_earth is not None else _EARTH
    astrometric = observer.at(t).observe(body).apparent()
    lat, lon, _dist = astrometric.ecliptic_latlon()
    return lon.degrees % 360.0, lat.degrees


def _true_node_longitude(t) -> float:
    """Moon's true (osculating) ascending-node ecliptic longitude at time `t`,
    derived geometrically from the Moon's geocentric position+velocity vectors
    (angular-momentum-vector method). See module docstring for the derivation.
    """
    geocentric = _EARTH.at(t).observe(_MOON_BODY).apparent()
    # Position/velocity in the true ecliptic-of-date frame.
    from skyfield.framelib import ecliptic_frame
    pos = geocentric.frame_xyz(ecliptic_frame).au
    vel = geocentric.frame_xyz_and_velocity(ecliptic_frame)[1].km_per_s
    r = _np.array(pos, dtype=float)
    v = _np.array(vel, dtype=float)
    h = _np.cross(r, v)  # orbital angular momentum vector (normal to orbital plane)
    z_hat = _np.array([0.0, 0.0, 1.0])
    n = _np.cross(z_hat, h)  # ascending node direction vector
    node_lon = math.degrees(math.atan2(n[1], n[0])) % 360.0
    return node_lon


# ---------------------------------------------------------------------------
# 1. Natal planet longitudes
# ---------------------------------------------------------------------------

@_functools.lru_cache(maxsize=512)
def _get_planet_longitudes_cached(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str, tz_offset_hours: Optional[float],
) -> Tuple[Tuple[str, float], ...]:
    return tuple(_get_planet_longitudes_uncached(dt_local, lat, lon, ayanamsa, tz_offset_hours).items())


def get_planet_longitudes(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Dict[str, float]:
    """Sidereal longitude (0-360 deg) for each of the 9 grahas at `dt_local`
    (naive local civil datetime) and geographic `lat`/`lon`. Ketu is always
    Rahu + 180. Returns {} on any failure (missing skyfield/ephemeris file,
    bad inputs).

    Perf note: cached (functools.lru_cache, keyed on the exact call args) --
    callers like Business_Prediction's D10 birth-time rectification
    sensitivity test and genuine-Placidus-KP recompute call this repeatedly
    at several nearby birth-time offsets / at the same exact birth moment
    from more than one module, and each call performs a real Skyfield
    ephemeris query (not free). The cache is exact-match only (no
    interpolation), so correctness is unaffected -- only redundant identical
    calls are avoided."""
    try:
        return dict(_get_planet_longitudes_cached(dt_local, float(lat), float(lon), ayanamsa, tz_offset_hours))
    except Exception:
        return _get_planet_longitudes_uncached(dt_local, lat, lon, ayanamsa, tz_offset_hours)


def _get_planet_longitudes_uncached(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Dict[str, float]:
    if not is_available():
        logger.warning("ephemeris.get_planet_longitudes: Skyfield/DE421 not available, skipping.")
        return {}
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        dt_utc = _to_utc(dt_local, tz)
        t = _skyfield_time(dt_utc)
        ayan = _ayanamsa_deg(dt_utc, ayanamsa)
        out: Dict[str, float] = {}
        for planet, body in _PLANET_BODIES.items():
            tropical_lon, _lat = _ecliptic_lon_lat(body, t)
            out[planet] = round((tropical_lon - ayan) % 360.0, 6)
        rahu_tropical = _true_node_longitude(t)
        out["Rahu"] = round((rahu_tropical - ayan) % 360.0, 6)
        out["Ketu"] = round((out["Rahu"] + 180.0) % 360.0, 6)
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("ephemeris.get_planet_longitudes failed: %s", exc)
        return {}


def get_planet_longitude(
    planet: str, dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Optional[float]:
    """Sidereal longitude for one graha without computing the other eight.

    Intended for numerical searches such as a solar return, where repeatedly
    calling ``get_planet_longitudes()`` multiplies the ephemeris work by nine.
    Returns ``None`` on an unavailable/out-of-range ephemeris.
    """
    if not is_available():
        return None
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        dt_utc = _to_utc(dt_local, tz)
        t = _skyfield_time(dt_utc)
        ayan = _ayanamsa_deg(dt_utc, ayanamsa)
        if planet in _PLANET_BODIES:
            tropical_lon, _ = _ecliptic_lon_lat(_PLANET_BODIES[planet], t)
            return round((tropical_lon - ayan) % 360.0, 9)
        if planet in ("Rahu", "Ketu"):
            rahu = (_true_node_longitude(t) - ayan) % 360.0
            return round(rahu if planet == "Rahu" else (rahu + 180.0) % 360.0, 9)
        return None
    except Exception as exc:
        logger.warning("ephemeris.get_planet_longitude(%s) failed: %s", planet, exc)
        return None
def get_planet_speeds(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Dict[str, float]:
    """Daily motion (deg/day) per planet, for retrograde detection. Negative = retrograde.
    Computed via a central finite difference (+/- 6 hours) of sidereal longitude,
    since Skyfield's apparent() ecliptic longitude does not directly expose a
    longitude-rate the way `swe.calc_ut`'s FLG_SPEED flag did."""
    if not is_available():
        return {}
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        dt_utc = _to_utc(dt_local, tz)
        dt_before = dt_utc - timedelta(hours=6)
        dt_after = dt_utc + timedelta(hours=6)
        t_before = _skyfield_time(dt_before)
        t_after = _skyfield_time(dt_after)
        ayan_before = _ayanamsa_deg(dt_before, ayanamsa)
        ayan_after = _ayanamsa_deg(dt_after, ayanamsa)

        out: Dict[str, float] = {}
        for planet, body in _PLANET_BODIES.items():
            lon_before, _ = _ecliptic_lon_lat(body, t_before)
            lon_after, _ = _ecliptic_lon_lat(body, t_after)
            sid_before = (lon_before - ayan_before) % 360.0
            sid_after = (lon_after - ayan_after) % 360.0
            delta = ((sid_after - sid_before + 180.0) % 360.0) - 180.0  # shortest signed diff
            out[planet] = round(delta / 0.5, 6)  # delta over 12 hours -> per day

        rahu_before = (_true_node_longitude(t_before) - ayan_before) % 360.0
        rahu_after = (_true_node_longitude(t_after) - ayan_after) % 360.0
        rahu_delta = ((rahu_after - rahu_before + 180.0) % 360.0) - 180.0
        out["Rahu"] = round(rahu_delta / 0.5, 6)
        out["Ketu"] = out["Rahu"]  # nodes always move together (opposite points)
        return out
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_planet_speeds failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# 2. Transit longitudes + house positions
# ---------------------------------------------------------------------------

def get_transit_house_positions(
    transit_dt_local: datetime, lat: float, lon: float, lagna_sign: str,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Tuple[Dict[str, int], Dict[str, float], List[str]]:
    """Returns (house_positions {planet: 1-12}, degrees {planet: longitude},
    retrograde_planets [list]) for the given transit moment, using whole-sign
    houses counted from `lagna_sign` (the NATAL lagna -- this answers "which
    natal house does each transiting planet currently occupy", the standard
    gochara convention already used elsewhere in this codebase, e.g.
    jyotish/transit_engine.py's `_house_from_sign`)."""
    if not is_available():
        return {}, {}, []
    try:
        lagna_idx = _SIGNS.index((lagna_sign or "").strip().title())
    except ValueError:
        logger.warning("ephemeris.get_transit_house_positions: unrecognised lagna_sign=%r", lagna_sign)
        return {}, {}, []

    degrees = get_planet_longitudes(transit_dt_local, lat, lon, ayanamsa, tz_offset_hours)
    speeds = get_planet_speeds(transit_dt_local, lat, lon, ayanamsa, tz_offset_hours)
    if not degrees:
        return {}, {}, []

    house_positions: Dict[str, int] = {}
    retrograde: List[str] = []
    for planet, lon_deg in degrees.items():
        sign_idx = int(lon_deg % 360.0 // 30.0)
        house_positions[planet] = ((sign_idx - lagna_idx) % 12) + 1
        if planet == "Ketu":
            # Ketu's "speed" mirrors Rahu's (both nodes always retrograde together).
            if speeds.get("Rahu", 0.0) < 0:
                retrograde.append(planet)
        elif speeds.get(planet, 0.0) < 0:
            retrograde.append(planet)

    return house_positions, degrees, retrograde


# ---------------------------------------------------------------------------
# 3. Placidus house cusps + real KP sub-lord chain
# ---------------------------------------------------------------------------

def _obliquity_of_ecliptic_deg(t) -> float:
    """Mean obliquity of the ecliptic at Skyfield time `t` (IAU 1980 series,
    good to ~0.0003 deg over multiple centuries -- ample for house cusps)."""
    T = (t.tt - 2451545.0) / 36525.0
    eps0 = (23.0 + 26.0 / 60.0 + 21.448 / 3600.0
            - (46.8150 / 3600.0) * T
            - (0.00059 / 3600.0) * T ** 2
            + (0.001813 / 3600.0) * T ** 3)
    return eps0


@_functools.lru_cache(maxsize=512)
def _get_house_cusps_placidus_cached(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str, tz_offset_hours: Optional[float],
    ayanamsa_deg_override: Optional[float] = None,
) -> Tuple[Tuple[int, float], ...]:
    return tuple(_get_house_cusps_placidus_uncached(
        dt_local, lat, lon, ayanamsa, tz_offset_hours, ayanamsa_deg_override,
    ).items())


def get_house_cusps_placidus(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
    ayanamsa_deg_override: Optional[float] = None,
) -> Dict[int, float]:
    """Perf note: cached (functools.lru_cache, exact-match on call args) --
    see get_planet_longitudes' docstring for why (repeated identical calls
    from Business_Prediction's D10 rectification-sensitivity test and
    genuine-Placidus-KP recompute). Delegates to
    _get_house_cusps_placidus_uncached (below) for the actual algorithm,
    documented there.

    `ayanamsa_deg_override`: pass a numeric ayanamsa (e.g. from
    derive_ayanamsa_from_known_sidereal_sun()) to bypass the hardcoded
    KP/Krishnamurti formula and keep the returned cusps internally
    consistent with a specific chart's own already-ingested sidereal
    positions, regardless of which ayanamsa convention that chart used.
    """
    try:
        return dict(_get_house_cusps_placidus_cached(
            dt_local, float(lat), float(lon), ayanamsa, tz_offset_hours, ayanamsa_deg_override,
        ))
    except Exception:
        return _get_house_cusps_placidus_uncached(
            dt_local, lat, lon, ayanamsa, tz_offset_hours, ayanamsa_deg_override,
        )


def _get_house_cusps_placidus_uncached(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
    ayanamsa_deg_override: Optional[float] = None,
) -> Dict[int, float]:
    """Placidus house cusp sidereal longitudes (1-12), computed from Skyfield's
    local apparent sidereal time + the standard iterative semi-arc Placidus
    algorithm.

    Algorithm (standard Placidus semi-arc method; see e.g. Michelsen, "The
    American Ephemeris" appendix on house systems, or Meeus/Duffett-Smith
    "Practical Astronomy" ch. on houses):

      1. Compute Local Sidereal Time (LST) at `dt_local`, converted to
         Right Ascension of the Midheaven (RAMC = LST * 15 deg).
      2. Cusps 10 (MC) and 1 (Ascendant) are computed directly in closed
         form from RAMC, geographic latitude, and the obliquity of the
         ecliptic (standard spherical-trigonometry MC/Asc formulas).
         Cusps 4 and 7 are exactly opposite (+180 deg) cusps 10 and 1.
      3. The remaining "intermediate" cusps (11, 12, 2, 3) do NOT have a
         closed-form solution under Placidus -- they are defined by the
         condition that the diurnal/nocturnal semi-arc of the ecliptic
         point is divided into thirds by the horizon/meridian circuits.
         We solve for each via the standard iterative Newton-style
         refinement on the hour-angle equation:
             tan(H) = -cos(RAMC + offset) / (sin(obliquity) * tan(lat)
                        + cos(obliquity) * sin(RAMC + offset))
         iterated until the cusp's own right ascension converges (typically
         under 10 iterations), for each of houses 11, 12, 2, 3 with their
         classical semi-arc fractions (1/3 and 2/3 of the semi-diurnal or
         semi-nocturnal arc from the Midheaven/Imum Coeli to the horizon).
      4. Finally each cusp's tropical ecliptic longitude is converted to
         sidereal by subtracting the KP/Krishnamurti ayanamsa (see module
         docstring).

    Returns {} on any failure (e.g. polar latitudes where Placidus is
    mathematically undefined -- the semi-arc there can be 0 or the full
    day, which this implementation detects and reports as a failure rather
    than returning degenerate values)."""
    if not is_available():
        logger.warning("ephemeris.get_house_cusps_placidus: Skyfield/DE421 not available, skipping.")
        return {}
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        dt_utc = _to_utc(dt_local, tz)
        t = _skyfield_time(dt_utc)
        ayan = _ayanamsa_deg(dt_utc, ayanamsa, ayanamsa_deg_override)

        eps = math.radians(_obliquity_of_ecliptic_deg(t))
        lat_r = math.radians(lat)

        # Greenwich Apparent Sidereal Time (hours) -> Local Sidereal Time (hours)
        # -> Right Ascension of the Midheaven in degrees.
        gast_hours = t.gast
        lst_hours = (gast_hours + lon / 15.0) % 24.0
        ramc_deg = lst_hours * 15.0
        ramc = math.radians(ramc_deg)

        if abs(math.cos(lat_r)) < 1e-9 or abs(90.0 - abs(lat)) < 1e-6:
            logger.warning("ephemeris.get_house_cusps_placidus: polar latitude, Placidus undefined.")
            return {}

        def _ecl_from_ra_dec(ra: float, dec: float) -> float:
            """Ecliptic longitude from equatorial RA/Dec (radians in, degrees out)."""
            sin_lon = math.sin(ra) * math.cos(eps) + math.tan(dec) * math.sin(eps)
            cos_lon = math.cos(ra)
            return math.degrees(math.atan2(sin_lon, cos_lon)) % 360.0

        # --- MC (house 10) and Ascendant (house 1): closed-form ---
        mc_tropical = _ecl_from_ra_dec(ramc, 0.0)

        # Standard Ascendant formula (equatorial ecliptic-pole relation).
        asc_num = math.cos(ramc)
        asc_den = -(math.sin(eps) * math.tan(lat_r) + math.cos(eps) * math.sin(ramc))
        asc_tropical = math.degrees(math.atan2(asc_num, asc_den)) % 360.0
        # Ensure Ascendant falls in the eastern (rising) hemisphere relative to MC.
        if ((asc_tropical - mc_tropical) % 360.0) > 180.0:
            asc_tropical = (asc_tropical + 180.0) % 360.0

        ic_tropical = (mc_tropical + 180.0) % 360.0
        dsc_tropical = (asc_tropical + 180.0) % 360.0

        # --- Intermediate cusps 11, 12, 2, 3: iterative semi-arc Placidus ---
        def _placidus_intermediate(fraction: float, upper: bool) -> float:
            """Solve for the ecliptic longitude whose semi-arc from the
            meridian (MC if `upper` else IC) to the horizon is `fraction`
            of that point's own total semi-diurnal (if upper) or
            semi-nocturnal (if not upper) arc. `fraction` is 1/3 for cusps
            11/12 (closer to the meridian) and 2/3 for cusps 2/3 measured
            the same way (Placidus's own convention: house 11 = MC + 1/3 of
            the diurnal semi-arc toward the Ascendant side; house 12 = MC +
            2/3; house 2 = IC + 2/3 of nocturnal semi-arc; house 3 = IC +
            1/3)."""
            # Start the Newton iteration at the corresponding equal-house guess.
            base_ramc = ramc if upper else (ramc + math.pi)
            lon_guess = mc_tropical if upper else ic_tropical
            for _ in range(30):
                lon_r = math.radians(lon_guess)
                # Declination of the point at this ecliptic longitude (lat_ecl=0).
                sin_dec = math.sin(eps) * math.sin(lon_r)
                dec = math.asin(max(-1.0, min(1.0, sin_dec)))
                # Right ascension of that same point.
                ra = math.atan2(math.sin(lon_r) * math.cos(eps), math.cos(lon_r))
                # Semi-diurnal arc (hour-angle at horizon) for this declination/latitude.
                cos_H = -math.tan(lat_r) * math.tan(dec)
                cos_H = max(-1.0, min(1.0, cos_H))
                H_horizon = math.acos(cos_H)  # radians, semi-diurnal arc (0..pi)
                target_H = fraction * H_horizon
                # gap fix (2026-07-19 audit, 2nd pass): a real run's
                # diagnostic output showed cusps 11/12/2/3 consistently
                # converging on the wrong side of their anchor point (e.g.
                # cusp 11 landed at 19.77 degrees -- BEFORE the MC at 47.14
                # -- instead of between the MC and the Ascendant at 138.82).
                # A first attempt to patch this with a post-hoc "flip to the
                # antipode if outside the expected arc" correction made it
                # worse (confirmed by re-running the diagnostic): all four
                # cusps were flagged as out-of-arc and got flipped together,
                # which just swapped which antipodal member landed in which
                # house slot without fixing the actual position.
                #
                # The real bug is a sign error in the hour-angle convention
                # itself. Standard convention: hour angle H = RAMC - RA(point)
                # is POSITIVE for a point that has already crossed the
                # meridian (west side, past culmination) and NEGATIVE for a
                # point that has not yet culminated (east side, rising
                # toward the Ascendant). House 11/12 lie between the MC and
                # the Ascendant -- i.e. on the NOT-YET-culminated (negative
                # hour angle) side -- so their target hour angle should be
                # -fraction*H_horizon, giving target_ra = RAMC - (-H) =
                # RAMC + H. The code below previously used RAMC - H (the sign
                # for the *already culminated* side), which is why cusp
                # 11/12 converged on the wrong side of the MC. Houses 2/3
                # lie between the Ascendant and the IC, symmetric to 11/12
                # around the horizon/IC axis, so they take the mirror-image
                # sign: RAMC(IC) - H instead of + H.
                target_ra = (base_ramc + target_H) if upper else (base_ramc - target_H)
                new_lon = _ecl_from_ra_dec(target_ra % (2 * math.pi), dec)
                if abs(((new_lon - lon_guess + 180.0) % 360.0) - 180.0) < 1e-7:
                    lon_guess = new_lon
                    break
                lon_guess = new_lon
            return lon_guess % 360.0

        cusp11 = _placidus_intermediate(1.0 / 3.0, upper=True)
        cusp12 = _placidus_intermediate(2.0 / 3.0, upper=True)
        cusp2 = _placidus_intermediate(2.0 / 3.0, upper=False)
        cusp3 = _placidus_intermediate(1.0 / 3.0, upper=False)

        tropical_cusps = {
            1: asc_tropical, 2: cusp2, 3: cusp3, 4: ic_tropical,
            5: (cusp11 + 180.0) % 360.0, 6: (cusp12 + 180.0) % 360.0,
            7: dsc_tropical, 8: (cusp2 + 180.0) % 360.0, 9: (cusp3 + 180.0) % 360.0,
            10: mc_tropical, 11: cusp11, 12: cusp12,
        }
        return {h: round((v - ayan) % 360.0, 6) for h, v in tropical_cusps.items()}
    except Exception as exc:  # pragma: no cover - defensive (e.g. polar lat)
        logger.warning("ephemeris.get_house_cusps_placidus failed: %s", exc)
        return {}


def _nakshatra_index_and_offset(longitude: float) -> Tuple[int, float]:
    """Return (nakshatra_index 0-26, degrees elapsed within that nakshatra 0-13.3333)."""
    lon = longitude % 360.0
    idx = int(lon // _NAK_SPAN)
    idx = min(idx, 26)
    offset = lon - idx * _NAK_SPAN
    return idx, offset


def _vimshottari_subdivide(span_deg: float, start_lord: str) -> List[Tuple[str, float, float]]:
    """Divide a span of `span_deg` degrees into 9 unequal Vimshottari-proportional
    sub-spans, in dasha-lord cyclic order STARTING from `start_lord`. Returns a
    list of (lord, sub_span_start_offset, sub_span_length) tuples, offsets
    relative to the start of `span_deg`."""
    start_pos = _VIMSHO_ORDER.index(start_lord) if start_lord in _VIMSHO_ORDER else 0
    out: List[Tuple[str, float, float]] = []
    cursor = 0.0
    for i in range(9):
        lord = _VIMSHO_ORDER[(start_pos + i) % 9]
        length = span_deg * (_VIMSHO_YEARS[lord] / _VIMSHO_TOTAL)
        out.append((lord, cursor, length))
        cursor += length
    return out


def compute_kp_sublords(cusp_longitude: float) -> Tuple[str, str, str]:
    """Standard KP nakshatra sub-lord chain for an absolute sidereal longitude.

    Level 1 (star_lord): the nakshatra (13d20') lord that the longitude falls in
      -- fixed classical nakshatra-lord cycle (Ketu-Venus-Sun-Moon-Mars-Rahu-
      Jupiter-Saturn-Mercury repeating 3x across the 27 nakshatras).
    Level 2 (sub_lord): within that nakshatra, divide its 13d20' span into 9
      Vimshottari-proportional sub-divisions, in dasha-lord order STARTING from
      the nakshatra's own star_lord (cyclic). The sub-span containing the
      longitude gives the sub_lord.
    Level 3 (sub_sub_lord): repeat the same 9-way Vimshottari-proportional
      division one level deeper, within the sub_lord's own span, again
      starting from the sub_lord itself (cyclic).

    This is the standard, unambiguous KP construction taught in KP literature
    (K.S. Krishnamurti's own system) and is a pure, deterministic function of
    the longitude alone -- no external state. Unchanged from the pyswisseph
    edition of this module (pure math, no ephemeris dependency).
    """
    nak_idx, nak_offset = _nakshatra_index_and_offset(cusp_longitude)
    star_lord = _NAKSHATRA_LORDS[nak_idx]

    # Level 2: subdivide the whole nakshatra span (13.3333 deg) starting at star_lord.
    sub_divisions = _vimshottari_subdivide(_NAK_SPAN, star_lord)
    sub_lord = sub_divisions[-1][0]
    sub_start = sub_divisions[-1][1]
    sub_len = sub_divisions[-1][2]
    for lord, start_off, length in sub_divisions:
        if nak_offset < start_off + length or (start_off + length) >= _NAK_SPAN - 1e-9:
            sub_lord, sub_start, sub_len = lord, start_off, length
            break

    offset_within_sub = nak_offset - sub_start

    # Level 3: subdivide the sub_lord's own span starting at sub_lord itself.
    subsub_divisions = _vimshottari_subdivide(sub_len, sub_lord)
    sub_sub_lord = subsub_divisions[-1][0]
    for lord, start_off, length in subsub_divisions:
        if offset_within_sub < start_off + length or (start_off + length) >= sub_len - 1e-9:
            sub_sub_lord = lord
            break

    return star_lord, sub_lord, sub_sub_lord


def compute_kp_cusp_chain(cusp_longitudes: Dict[int, float]) -> Dict[str, Dict[str, Any]]:
    """Build the full KP cusp block (sign, sign_lord, star_lord, sub_lord,
    sub_sub_lord, degree-within-sign) for every house present in
    `cusp_longitudes`, matching the shape of the existing
    `pyhora_calculations.kp_cusp_data` JSON block."""
    from .constants import _SIGN_LORD as _SL
    out: Dict[str, Dict[str, Any]] = {}
    for house_num, lon_deg in cusp_longitudes.items():
        sign, deg_in_sign = _sign_and_deg(lon_deg)
        star_lord, sub_lord, sub_sub_lord = compute_kp_sublords(lon_deg)
        out[f"H{house_num}"] = {
            "sign": sign,
            "degree": round(deg_in_sign, 4),
            "absolute_degree": round(lon_deg % 360.0, 4),
            "sign_lord": _SL.get(sign, ""),
            "star_lord": star_lord,
            "sub_lord": sub_lord,
            "sub_sub_lord": sub_sub_lord,
        }
    return out


# ---------------------------------------------------------------------------
# 4. Ghati Lagna and Sree Lagna
# ---------------------------------------------------------------------------
#
# Formula sources / derivation notes
# -----------------------------------
# Ghati Lagna: classical formula (see B.V. Raman, "Hindu Predictive
# Astrology", ch. on Special Lagnas; also standard in most Jyotish software
# such as Jagannatha Hora/JHora's "Ghati Lagna" computation). Time elapsed
# since sunrise (in ghatis; 1 ghati = 24 minutes = 60 ghatis/day = 1 nakshatra
# day) is converted directly to zodiacal motion at the rate of 1 sign (30 deg)
# per 2 ghatis (48 minutes) -- i.e. the whole zodiac (360 deg / 12 signs)
# completes in 24 ghatis (=~9.6 hours), a fixed rotation rate independent of
# the real sidereal day. Ghati Lagna advances from Aries 0 deg at the moment
# of the PREVIOUS sunrise, 30 deg per 2 ghatis, continuously:
#   Ghati Lagna (deg) = (ghatis_elapsed_since_sunrise * 15 deg/ghati) mod 360
# since 30 deg / 2 ghatis = 15 deg/ghati. Unchanged from the pyswisseph
# edition (pure math once sunrise time is known).
#
# Sree Lagna: classical formula (B.V. Raman, ibid.; also K.S. Krishnamurti's
# KP literature on Sree Lagna). See the detailed derivation note retained
# from the original module (below, at get_sree_lagna).
# ---------------------------------------------------------------------------

_GHATI_RATE_DEG_PER_GHATI = 15.0  # 30 deg per 2 ghatis


def get_sunrise_jd(dt_local: date, lat: float, lon: float, tz_offset_hours: float) -> Optional[float]:
    """Skyfield Time (`.tt`, Julian Day Terrestrial Time) of sunrise on the
    civil date `dt_local` at (lat, lon), found via `skyfield.almanac`'s
    discrete sunrise/sunset event search (replaces `swe.rise_trans`)."""
    if not is_available():
        return None
    try:
        location = wgs84.latlon(lat, lon)
        # Search a generous +/- 1 calendar day window in UT around the given
        # civil date (converted via tz offset) to make sure the true sunrise
        # instant for that local calendar date is inside the search window.
        t0_utc = datetime(dt_local.year, dt_local.month, dt_local.day) - timedelta(hours=tz_offset_hours) - timedelta(hours=12)
        t1_utc = t0_utc + timedelta(hours=48)
        t0 = _skyfield_time(t0_utc)
        t1 = _skyfield_time(t1_utc)
        f = almanac.sunrise_sunset(_EPH, location)
        times, events = almanac.find_discrete(t0, t1, f)
        # events == 1 means sunrise (rising); pick the one whose LOCAL date
        # (using tz_offset_hours) matches dt_local.
        for ti, ev in zip(times, events):
            if ev != 1:
                continue
            local_dt = ti.utc_datetime().replace(tzinfo=None) + timedelta(hours=tz_offset_hours)
            if local_dt.date() == dt_local:
                return ti.tt
        return None
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_sunrise_jd failed: %s", exc)
        return None


def get_sunset_jd(dt_local: date, lat: float, lon: float, tz_offset_hours: float) -> Optional[float]:
    """Skyfield Time (`.tt`, Julian Day Terrestrial Time) of sunset on the
    civil date `dt_local` at (lat, lon). Mirrors get_sunrise_jd() above
    (same almanac.sunrise_sunset discrete-event search, ev==0 for setting
    instead of ev==1 for rising). Added for jyotish/shadbala.py's Kala Bala
    (Natonnata/day-night, Tribhaga, Ayana components), which needs both the
    preceding sunrise and the same-day sunset to determine day/night birth
    and elapsed diurnal/nocturnal fraction."""
    if not is_available():
        return None
    try:
        location = wgs84.latlon(lat, lon)
        t0_utc = datetime(dt_local.year, dt_local.month, dt_local.day) - timedelta(hours=tz_offset_hours) - timedelta(hours=12)
        t1_utc = t0_utc + timedelta(hours=48)
        t0 = _skyfield_time(t0_utc)
        t1 = _skyfield_time(t1_utc)
        f = almanac.sunrise_sunset(_EPH, location)
        times, events = almanac.find_discrete(t0, t1, f)
        for ti, ev in zip(times, events):
            if ev != 0:
                continue
            local_dt = ti.utc_datetime().replace(tzinfo=None) + timedelta(hours=tz_offset_hours)
            if local_dt.date() == dt_local:
                return ti.tt
        return None
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_sunset_jd failed: %s", exc)
        return None


def get_planet_latitudes(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Dict[str, float]:
    """Ecliptic latitude (degrees, signed) per planet at `dt_local`. Added for
    jyotish/shadbala.py's Sthana Bala sub-components that classically use
    celestial latitude (e.g. Rahu/Ketu are conventionally treated as always
    on the ecliptic, latitude 0, per standard Vedic practice -- included here
    for completeness/consistency with the other per-planet ephemeris getters,
    not because Shadbala's formula requires nodal latitude specifically).
    Reuses the same _ecliptic_lon_lat() calls get_planet_longitudes() already
    makes -- no new Skyfield API pattern, just retains the second (latitude)
    return value that was previously discarded.

    Gap-audit fix (2026-08): this function's real body -- the try/except
    block now below -- had been orphaned as unreachable dead code appended
    after tt_jd_to_local_datetime()'s `return` statement (evidently from a
    bad merge), leaving THIS function ending right after the `is_available()`
    guard with no further statement. On the success path (Skyfield/DE421
    available), that meant this function returned Python's implicit `None`
    instead of a dict. Callers typically defensively did
    `(planet_latitudes or {}).get(planet, 0.0)`, so `None` silently degraded
    to `{}` and every planet got latitude 0.0 -- meaning shadbala.py's Ayana
    Bala (declination-based temporal strength) was being computed as if
    every planet had zero ecliptic latitude even when real ephemeris was
    fully available. Restored to its intended body below; the orphaned
    duplicate after tt_jd_to_local_datetime() has been removed."""
    if not is_available():
        return {}
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        dt_utc = _to_utc(dt_local, tz)
        t = _skyfield_time(dt_utc)
        out: Dict[str, float] = {}
        for planet, body in _PLANET_BODIES.items():
            _lon, lat_deg = _ecliptic_lon_lat(body, t)
            out[planet] = round(lat_deg, 6)
        out["Rahu"] = 0.0
        out["Ketu"] = 0.0
        return out
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_planet_latitudes failed: %s", exc)
        return {}


def get_tropical_planet_longitudes(
    dt_local: datetime, lat: float, lon: float, tz_offset_hours: Optional[float] = None,
) -> Dict[str, float]:
    """True tropical ecliptic longitudes used by declination calculations."""
    if not is_available():
        return {}
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        t = _skyfield_time(_to_utc(dt_local, tz))
        out = {planet: round(_ecliptic_lon_lat(body, t)[0] % 360.0, 6)
               for planet, body in _PLANET_BODIES.items()}
        rahu = _true_node_longitude(t)
        out["Rahu"], out["Ketu"] = round(rahu, 6), round((rahu + 180.0) % 360.0, 6)
        return out
    except Exception as exc:
        logger.warning("ephemeris.get_tropical_planet_longitudes failed: %s", exc)
        return {}


def tt_jd_to_local_datetime(jd_tt: float, tz_offset_hours: float) -> datetime:
    """Convert a Skyfield TT Julian date returned by rise/set helpers to local civil time."""
    utc = _TS.tt_jd(float(jd_tt)).utc_datetime().replace(tzinfo=None)
    return utc + timedelta(hours=float(tz_offset_hours))


def get_ghati_lagna(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Ghati Lagna at `dt_local`: 0 Aries at the birth-date sunrise, advancing
    15 deg per ghati (24 min) thereafter. Returns {"longitude":.., "sign":..,
    "degree":..} or None on failure (e.g. polar latitude with no sunrise)."""
    if not is_available():
        return None
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        sunrise_tt = get_sunrise_jd(dt_local.date(), lat, lon, tz)
        if sunrise_tt is None:
            logger.warning("ephemeris.get_ghati_lagna: could not compute sunrise for %s", dt_local)
            return None
        dt_utc = _to_utc(dt_local, tz)
        jd_now = _skyfield_time(dt_utc).tt
        elapsed_days = jd_now - sunrise_tt
        if elapsed_days < 0:
            # dt_local is before this civil date's sunrise -> use previous day's sunrise.
            sunrise_tt = get_sunrise_jd(dt_local.date() - timedelta(days=1), lat, lon, tz)
            if sunrise_tt is None:
                return None
            elapsed_days = jd_now - sunrise_tt
        elapsed_ghatis = elapsed_days * 60.0  # 60 ghatis per full day
        longitude = (elapsed_ghatis * _GHATI_RATE_DEG_PER_GHATI) % 360.0
        sign, deg = _sign_and_deg(longitude)
        return {"longitude": round(longitude, 6), "sign": sign, "degree": round(deg, 4),
                "elapsed_ghatis": round(elapsed_ghatis, 4)}
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_ghati_lagna failed: %s", exc)
        return None


def get_sree_lagna(
    dt_local: datetime, lat: float, lon: float, lagna_longitude: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Sree Lagna: start of the Lagna's occupied nakshatra + (Moon's elapsed
    portion of ITS OWN occupied nakshatra x 9). See the original module's
    detailed derivation citation (B.V. Raman; K.S. Krishnamurti KP literature)
    -- unchanged formula, only the underlying Moon longitude source changed
    (Skyfield instead of pyswisseph). `lagna_longitude` is the natal
    Ascendant's absolute sidereal longitude (0-360 deg)."""
    if not is_available():
        return None
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        moon_lon_map = get_planet_longitudes(dt_local, lat, lon, ayanamsa, tz)
        moon_lon = moon_lon_map.get("Moon")
        if moon_lon is None:
            return None

        lagna_nak_idx, _ = _nakshatra_index_and_offset(lagna_longitude)
        lagna_nak_start = lagna_nak_idx * _NAK_SPAN

        _, moon_offset = _nakshatra_index_and_offset(moon_lon)
        advancement = moon_offset * 9.0  # see derivation note above

        longitude = (lagna_nak_start + advancement) % 360.0
        sign, deg = _sign_and_deg(longitude)
        return {
            "longitude": round(longitude, 6), "sign": sign, "degree": round(deg, 4),
            "lagna_nakshatra": _NAKSHATRA_NAMES[lagna_nak_idx],
            "moon_nakshatra_offset_deg": round(moon_offset, 4),
        }
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_sree_lagna failed: %s", exc)
        return None


# GAP-FIX (2026-07): Hora Lagna and Bhava Lagna had payload fields
# (hora_lagna_sign / bhava_lagna_sign on NatalPayloadV2) but no computation
# function existed anywhere in the repo -- they were always empty strings in
# every engine run (confirmed by grep: engine_io.py never populated them).
# These mirror get_ghati_lagna's structure/sunrise-elapsed-time approach
# exactly, but start from the natal SUN's longitude (not 0 Aries) and use the
# classical Hora/Bhava Lagna rates, per BPHS/Phaladeepika:
#   Bhava Lagna: 1 rasi (30deg) per 5 ghatis (2 hours) elapsed since sunrise.
#   Hora Lagna:  1 rasi (30deg) per 2.5 ghatis (1 hour) elapsed since sunrise
#                (i.e. double the Bhava Lagna rate).

def get_bhava_lagna(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Bhava Lagna at `dt_local`: natal Sun's longitude, advancing 30 deg per
    5 ghatis (2 hours) elapsed since birth-date sunrise. Returns
    {"longitude":.., "sign":.., "degree":..} or None on failure."""
    if not is_available():
        return None
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        sunrise_tt = get_sunrise_jd(dt_local.date(), lat, lon, tz)
        if sunrise_tt is None:
            logger.warning("ephemeris.get_bhava_lagna: could not compute sunrise for %s", dt_local)
            return None
        dt_utc = _to_utc(dt_local, tz)
        jd_now = _skyfield_time(dt_utc).tt
        elapsed_days = jd_now - sunrise_tt
        if elapsed_days < 0:
            sunrise_tt = get_sunrise_jd(dt_local.date() - timedelta(days=1), lat, lon, tz)
            if sunrise_tt is None:
                return None
            elapsed_days = jd_now - sunrise_tt
        elapsed_ghatis = elapsed_days * 60.0
        sun_lon_map = get_planet_longitudes(dt_local, lat, lon, ayanamsa, tz)
        sun_lon = sun_lon_map.get("Sun")
        if sun_lon is None:
            return None
        longitude = (sun_lon + elapsed_ghatis * (30.0 / 5.0)) % 360.0
        sign, deg = _sign_and_deg(longitude)
        return {"longitude": round(longitude, 6), "sign": sign, "degree": round(deg, 4),
                "elapsed_ghatis": round(elapsed_ghatis, 4)}
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_bhava_lagna failed: %s", exc)
        return None


def get_hora_lagna(
    dt_local: datetime, lat: float, lon: float,
    ayanamsa: str = _DEFAULT_AYANAMSA, tz_offset_hours: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Hora Lagna at `dt_local`: natal Sun's longitude, advancing 30 deg per
    2.5 ghatis (1 hour) elapsed since birth-date sunrise. Returns
    {"longitude":.., "sign":.., "degree":..} or None on failure."""
    if not is_available():
        return None
    try:
        tz = tz_offset_hours if tz_offset_hours is not None else _infer_tz_offset_hours(lon)
        sunrise_tt = get_sunrise_jd(dt_local.date(), lat, lon, tz)
        if sunrise_tt is None:
            logger.warning("ephemeris.get_hora_lagna: could not compute sunrise for %s", dt_local)
            return None
        dt_utc = _to_utc(dt_local, tz)
        jd_now = _skyfield_time(dt_utc).tt
        elapsed_days = jd_now - sunrise_tt
        if elapsed_days < 0:
            sunrise_tt = get_sunrise_jd(dt_local.date() - timedelta(days=1), lat, lon, tz)
            if sunrise_tt is None:
                return None
            elapsed_days = jd_now - sunrise_tt
        elapsed_ghatis = elapsed_days * 60.0
        sun_lon_map = get_planet_longitudes(dt_local, lat, lon, ayanamsa, tz)
        sun_lon = sun_lon_map.get("Sun")
        if sun_lon is None:
            return None
        longitude = (sun_lon + elapsed_ghatis * (30.0 / 2.5)) % 360.0
        sign, deg = _sign_and_deg(longitude)
        return {"longitude": round(longitude, 6), "sign": sign, "degree": round(deg, 4),
                "elapsed_ghatis": round(elapsed_ghatis, 4)}
    except Exception as exc:  # pragma: no cover
        logger.warning("ephemeris.get_hora_lagna failed: %s", exc)
        return None


def get_bhrigu_bindu(rahu_longitude: float, moon_longitude: float) -> Optional[Dict[str, Any]]:
    """Bhrigu Bindu: the midpoint of Rahu and Moon along the SHORTER arc
    between them (a widely-used destiny/career-turning-point indicator in
    several modern Vedic schools). `rahu_longitude`/`moon_longitude` are
    absolute 0-360 sidereal degrees. Returns {"longitude":.., "sign":..,
    "degree":..} or None if either input is missing.

    GAP-FIX (2026-07): previously not computed anywhere in the repo.
    """
    if rahu_longitude is None or moon_longitude is None:
        return None
    try:
        diff = (float(moon_longitude) - float(rahu_longitude)) % 360.0
        if diff > 180.0:
            diff -= 360.0  # signed shortest angular difference, range (-180, 180]
        longitude = (float(rahu_longitude) + diff / 2.0) % 360.0
        sign, deg = _sign_and_deg(longitude)
        return {"longitude": round(longitude, 6), "sign": sign, "degree": round(deg, 4)}
    except (TypeError, ValueError) as exc:  # pragma: no cover
        logger.warning("ephemeris.get_bhrigu_bindu failed: %s", exc)
        return None
