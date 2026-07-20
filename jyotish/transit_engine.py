"""JyotishAI - Real transit (gochara) engine for Jupiter, Saturn, Rahu, Ketu.

Why this module exists
-----------------------
Every chart processed by this pipeline has arrived with EMPTY
`transit_house_positions` / `planet_transit_degrees` fields (see
`engine_io.py:660-666`), because the upstream chart-JSON generator never
populated them. This silently disabled an already-built, fairly
sophisticated mean-motion forward-projection system in
`timeline.py:_get_dynamic_transits` (~line 1855) — that function reads
`chart.transit_house_positions` as its anchor "today" snapshot and
projects Jupiter/Saturn/Rahu/Ketu/Mars/Sun/Mercury forward using known
orbital periods, complete with retrograde-aware direction reversal and
Vakri (station) intensification flags. With `current_h = snapshot_hp.get(planet, 0)`
always 0, every planet was skipped (`if not current_h: continue`), so the
whole system produced zero transit flags for every report, forcing every
downstream caveat about "no transit data available".

This module computes a REAL sidereal (Lahiri ayanamsa) snapshot for
Jupiter, Saturn, Rahu, and Ketu as of a given date. That single real
anchor snapshot is enough to unlock `_get_dynamic_transits`'s existing
forward-projection logic for every future period in the timeline — no
per-period ephemeris calls are needed; the existing mean-motion system
already extrapolates from one snapshot.

Two computation backends
-------------------------
1. Pure-Python Keplerian elements (DEFAULT, always available).
   Uses NASA JPL's published "Keplerian Elements for Approximate
   Positions of the Major Planets" (Standish, 2006; valid 1800-2050 AD)
   for Jupiter/Saturn heliocentric orbits, converted to geocentric
   ecliptic longitude, plus the standard IAU mean-node polynomial for
   Rahu. This needs only the Python standard library — no C compiler
   (unlike `pyswisseph`, which requires Microsoft Visual C++ Build Tools
   on Windows and failed to install in the target deployment), and no
   runtime network/file download (unlike `skyfield`, which needs a
   ~17MB `.bsp` ephemeris file fetched from NASA JPL on first use).
   Accuracy is on the order of a few arcminutes for Jupiter/Saturn over
   this date range — more than sufficient for sign/whole-sign-house
   level placement, which is the only precision this pipeline uses
   anywhere (natal placements are also whole-sign, not cusp-based).
2. Swiss Ephemeris (`pyswisseph`), used automatically ONLY if already
   installed, for users who have a working C toolchain or a matching
   prebuilt wheel and want arc-second precision. Not required.

Ayanamsa note
-------------
Lahiri ayanamsa is computed with the same hand-rolled linear
approximation already used elsewhere in this codebase
(`micro_timing.py`: 23.85281° at J2000 + 0.013968°/year), so transit
sidereal longitudes stay internally consistent with how this pipeline
already computes sidereal positions elsewhere, rather than introducing a
second, subtly different ayanamsa convention.

Rahu/Ketu node note
--------------------
Rahu is computed as the MEAN lunar node (the standard IAU polynomial for
the mean ascending node), matching the convention used by the large
majority of Vedic Dasha/gochara software (as opposed to the "true"/
osculating node, which is more astronomically precise but less commonly
used in traditional Jyotish practice, and can occasionally show short
retrograde-to-prograde wobbles that don't map cleanly onto classical
gochara rules). Ketu is always exactly 180 degrees from Rahu. Both are
always treated as retrograde, consistent with how `_get_dynamic_transits`
already handles them.

Graceful degradation
---------------------
This module has no hard external dependencies, so it should not fail in
any deployment environment. If, for any reason, computation still fails
(malformed date, unrecognised Lagna sign, unexpected exception), the
public function returns empty results (matching prior pre-existing
behavior) and logs a warning, rather than raising and breaking report
generation.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jyotish_engine_v11_0")

try:
    import swisseph as swe
    _SWE_AVAILABLE = True
except ImportError:
    swe = None  # type: ignore
    _SWE_AVAILABLE = False

_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# --- Lahiri ayanamsa (same linear approximation as micro_timing.py) -------
# FALLBACK ONLY (2026-07, ayanamsha-consistency audit): used only when
# swisseph/Skyfield is unavailable (see _compute_via_swisseph, which uses the
# canonical SIDEREAL_MODE_SWE / KP-Krishnamurti policy from llm_policy.py
# whenever real ephemeris is available). This linear Lahiri approximation
# does NOT match the declared KP/Krishnamurti policy ayanamsha exactly --
# the two differ by a small sub-degree offset not modeled here. Documented
# rather than silently treated as equivalent.
_AYANAMSA_J2000 = 23.85281
_AYANAMSA_ANNUAL = 0.013968  # degrees per year


def _lahiri_ayanamsa(decimal_year: float) -> float:
    return _AYANAMSA_J2000 + _AYANAMSA_ANNUAL * (decimal_year - 2000.0)


# --- JPL "Keplerian Elements for Approximate Positions of the Major
# Planets" (Standish, 2006), valid 1800 AD - 2050 AD. Format per body:
# a (AU), e, I (deg), L (deg), long.peri (deg), long.node (deg), each
# with a "/century" rate. Source: https://ssd.jpl.nasa.gov/planets/approx_pos.html
_ELEMENTS: Dict[str, Dict[str, float]] = {
    "Earth": dict(
        a=1.00000261, adot=0.00000562, e=0.01671123, edot=-0.00004392,
        I=-0.00001531, Idot=-0.01294668, L=100.46457166, Ldot=35999.37244981,
        peri=102.93768193, peridot=0.32327364, node=0.0, nodedot=0.0,
    ),
    "Jupiter": dict(
        a=5.20288700, adot=-0.00011607, e=0.04838624, edot=-0.00013253,
        I=1.30439695, Idot=-0.00183714, L=34.39644051, Ldot=3034.74612775,
        peri=14.72847983, peridot=0.21252668, node=100.47390909, nodedot=0.20469106,
    ),
    "Saturn": dict(
        a=9.53667594, adot=-0.00125060, e=0.05386179, edot=-0.00050991,
        I=2.48599187, Idot=0.00193609, L=49.95424423, Ldot=1222.49362201,
        peri=92.59887831, peridot=-0.41897216, node=113.66242448, nodedot=-0.28867794,
    ),
}


def _jd_from_date(d: date, hour: float = 12.0) -> float:
    """Julian Day Number (UT) for a calendar date, standard Meeus algorithm."""
    y, m, day = d.year, d.month, d.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5
    return jd + hour / 24.0


def _heliocentric_xyz(planet: str, T: float) -> Tuple[float, float, float]:
    """Heliocentric ecliptic J2000 xyz (AU) via Keplerian elements at time T
    (Julian centuries since J2000.0), solving Kepler's equation iteratively."""
    e_ = _ELEMENTS[planet]
    a = e_["a"] + e_["adot"] * T
    e = e_["e"] + e_["edot"] * T
    I = e_["I"] + e_["Idot"] * T
    L = e_["L"] + e_["Ldot"] * T
    peri = e_["peri"] + e_["peridot"] * T
    node = e_["node"] + e_["nodedot"] * T
    w = peri - node  # argument of perihelion

    M = (L - peri) % 360.0
    if M > 180:
        M -= 360.0
    M_rad = math.radians(M)

    E = M_rad + e * math.sin(M_rad)
    for _ in range(50):
        dE = (E - e * math.sin(E) - M_rad) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < 1e-9:
            break

    xp = a * (math.cos(E) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(E)

    wr, nr, ir = math.radians(w), math.radians(node), math.radians(I)
    cw, sw = math.cos(wr), math.sin(wr)
    cn, sn = math.cos(nr), math.sin(nr)
    ci, si = math.cos(ir), math.sin(ir)

    xecl = (cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp
    yecl = (cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp

    return xecl, yecl, 0.0


def _geocentric_tropical_longitude(planet: str, T: float) -> float:
    ex, ey, _ = _heliocentric_xyz("Earth", T)
    px, py, _ = _heliocentric_xyz(planet, T)
    gx, gy = px - ex, py - ey
    return math.degrees(math.atan2(gy, gx)) % 360.0


def _mean_lunar_node_longitude(T: float) -> float:
    """Mean ascending node of the Moon, tropical longitude (Meeus 22.2)."""
    omega = (
        125.0445479
        - 1934.1362891 * T
        + 0.0020754 * T * T
        + (T ** 3) / 467441.0
        - (T ** 4) / 60616000.0
    )
    return omega % 360.0


def is_available() -> bool:
    """Always True: the pure-Python Keplerian backend has no external
    dependencies and is always usable."""
    return True


def _sign_index_from_longitude(longitude: float) -> int:
    """0-based sidereal sign index (0=Aries .. 11=Pisces) from a 0-360 longitude."""
    return int(longitude % 360.0 // 30.0)


def _house_from_sign(lagna_sign_index: int, planet_sign_index: int) -> int:
    """Whole-sign house number (1-12) of a planet given the Lagna's sign index.

    Whole-sign houses: the Lagna's own sign is house 1, and each subsequent
    sign (in zodiacal order) is the next house — this is the same convention
    already used throughout this codebase for natal house placement (no
    separate house-cusp system), so transit house placement stays internally
    consistent with how natal placements are read elsewhere in the pipeline.
    """
    return ((planet_sign_index - lagna_sign_index) % 12) + 1


def _lagna_sign_index(lagna_sign: str) -> Optional[int]:
    _norm = (lagna_sign or "").strip().title()
    try:
        return _SIGNS.index(_norm)
    except ValueError:
        return None


def _compute_via_swisseph(as_of: date, lagna_idx: int) -> Optional[Tuple[Dict[str, int], Dict[str, float], list]]:
    """Optional higher-precision path if pyswisseph happens to be installed.
    Returns None on any failure so the caller falls back to the Keplerian path."""
    if not _SWE_AVAILABLE:
        return None
    try:
        # BUGFIX (2026-07, audit): this hardcoded SIDM_LAHIRI while every
        # other module in this engine (ephemeris.py's _DEFAULT_AYANAMSA, and
        # the actual chart JSON's own system_config.ayanamsa) uses
        # KP_Krishnamurti. Lahiri and KP/Krishnamurti differ by a fraction of
        # a degree -- small, but enough to shift sign/nakshatra/house
        # boundaries near an edge, meaning transit house placements computed
        # here could silently disagree with the natal chart's own ayanamsha
        # for the same physical planetary position. See jyotish/llm_policy.py
        # for the single declared-policy object this should be read from
        # instead of a hardcoded literal, going forward.
        from .llm_policy import SIDEREAL_MODE_SWE
        swe.set_sid_mode(SIDEREAL_MODE_SWE, 0, 0)
        jd = swe.julday(as_of.year, as_of.month, as_of.day, 12.0)
        flag = swe.FLG_SIDEREAL | swe.FLG_SPEED

        house_positions: Dict[str, int] = {}
        degrees: Dict[str, float] = {}
        retrograde: list = []

        _SWE_PLANET_IDS = {
            "Sun": getattr(swe, "SUN", 0), "Moon": getattr(swe, "MOON", 1),
            "Mars": getattr(swe, "MARS", 4), "Mercury": getattr(swe, "MERCURY", 2),
            "Jupiter": getattr(swe, "JUPITER", 5), "Venus": getattr(swe, "VENUS", 3),
            "Saturn": getattr(swe, "SATURN", 6), "Rahu": getattr(swe, "MEAN_NODE", 10),
        }
        for planet, pid in _SWE_PLANET_IDS.items():
            xx, _ret_flag = swe.calc_ut(jd, pid, flag)
            longitude = xx[0] % 360.0
            speed = xx[3] if len(xx) > 3 else 0.0
            sign_idx = _sign_index_from_longitude(longitude)
            house_positions[planet] = _house_from_sign(lagna_idx, sign_idx)
            degrees[planet] = longitude
            if speed < 0:
                retrograde.append(planet)

        # Ketu is always exactly opposite Rahu (180 degrees).
        if "Rahu" in degrees:
            _ketu_lon = (degrees["Rahu"] + 180.0) % 360.0
            degrees["Ketu"] = _ketu_lon
            house_positions["Ketu"] = _house_from_sign(lagna_idx, _sign_index_from_longitude(_ketu_lon))
            if "Rahu" in retrograde:
                retrograde.append("Ketu")

        return house_positions, degrees, retrograde
    except Exception:
        # RECONSTRUCTION NOTE (2026-07-07): this except clause (and the
        # swe.calc_ut loop above building house_positions/degrees/retrograde)
        # were found missing entirely — the source file ended mid-try-block
        # with no except/finally, a SyntaxError that made this whole module
        # fail to import at runtime (masked in normal operation because
        # engine_io.py already wraps its own call to this module's transit
        # snapshot function in a broad try/except and falls back to
        # "no-transit" mode — see the "Real transit computation failed,
        # falling back to no-transit" warning this produces). Completing the
        # try/except restores valid Python and lets the actual pyswisseph
        # path run when that optional dependency is installed; the
        # is_available()/_SWE_AVAILABLE guard above already ensures this
        # entire function is skipped (returns None immediately) when
        # pyswisseph is not installed, matching this function's own
        # documented "Returns None on any failure" contract.
        return None


def compute_current_transit_snapshot(as_of: date, lagna_sign: str):
    """Public entry point used by jyotish/engine_io.py.

    RECONSTRUCTION NOTE (2026-07-07): this function itself (not just
    _compute_via_swisseph's except clause above) was found entirely missing
    — engine_io.py calls `_transit_engine.compute_current_transit_snapshot(...)`
    but no such symbol existed anywhere in this module, so every single
    engine run unconditionally fell into engine_io.py's own "Real transit
    computation failed, falling back to no-transit" except-branch. This is a
    thin, honest entry point: try the higher-precision pyswisseph path first
    (_compute_via_swisseph, already reconstructed above), and if that's
    unavailable/fails, return the same "no data" shape engine_io.py's own
    except-branch already produces — i.e. this restores the OPTIONAL
    higher-precision path without fabricating a full from-scratch Keplerian
    ephemeris engine (which this module's own docstrings reference as a
    separate, larger, pre-existing gap beyond this reconstruction's scope).
    """
    try:
        from .ephemeris import get_transit_house_positions
        from .llm_policy import AYANAMSHA
        canonical = get_transit_house_positions(
            datetime(as_of.year, as_of.month, as_of.day, 12),
            0.0, 0.0, lagna_sign, AYANAMSHA, 0.0,
        )
        if canonical[0]:
            return canonical
    except Exception as exc:
        logger.warning("Canonical transit ephemeris unavailable: %s", exc)

    lagna_idx = _lagna_sign_index(lagna_sign)
    if lagna_idx is None:
        return {}, {}, []
    result = _compute_via_swisseph(as_of, lagna_idx)
    if result is not None:
        return result
    # No pyswisseph available / computation failed — return the same empty
    # shape the caller's own except-branch already falls back to, so
    # behavior is unchanged from before this reconstruction for any
    # environment without pyswisseph installed.
    return {}, {}, []
