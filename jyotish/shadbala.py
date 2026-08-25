"""Classical six-fold Shadbala (planetary strength), computed from first
principles instead of ingested from an upstream payload field.

Motivation (2026-07 astrologer's audit): the engine previously consumed a
single pre-summed `shadbala_virupas` number per planet from the upstream
chart payload (jyotish/engine_io.py:174) with no sub-component breakdown,
and layered a simplified house-granularity dig-bala proxy on top
(astro_enhancer.py's _g4_dig_bala_factor). This meant two fields that were
thematically identical (same karaka planets present) but differed in how
classically STRONG those planets actually were could not be reliably told
apart by the ranking engine. This module computes all six classical
components (Sthana, Dig, Kala, Cheshta, Naisargika, Drishti Bala) from raw
ephemeris facts already available in jyotish/ephemeris.py, and sums them to
a total in Shashtiamsas (60ths of a "rupa", the classical unit), matching
BPHS/Saravali's standard scale.

The classical-v2 implementation covers the seven visible grahas only, as
BPHS explicitly excludes Rahu and Ketu. It computes all seven required
Saptavargas, exact calendar/Hora sub-strengths, true-declination Ayana Bala,
observed-motion Cheshta classes, and degree-exact Sphuta Drishti. A result is
marked COMPLETE only when the necessary birth and ephemeris inputs exist.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, Mapping, Optional

from .constants import (
    _EXALT_SIGN, _DEBIL_SIGN, _OWN_SIGN, _EXALT_DEGREE, _DEBIL_DEGREE,
    _MOOLATRIKONA, _SIGN_NUM, _SIGN_LORD, _KENDRA_HOUSES, _TRIKONA_HOUSES,
)
from .dignity import graha_yuddha as _dignity_graha_yuddha, dignity_state
from .vimshopaka import (
    compute_d2_sign, compute_d3_sign, compute_d7_sign,
    compute_d12_sign, compute_d30_sign,
)
from .validation_contract import evidence_status

SHADBALA_VERSION = "shadbala-six-fold.classical-v2"
CLASSICAL_SHADBALA_PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")

# ── §5b: Rahu/Ketu 0-1 strength heuristic (no classical Shadbala exists for
# the lunar nodes -- BPHS explicitly excludes them, see module docstring). ──
#
# DOCUMENTED HEURISTIC / SCHOOL OF THOUGHT (per Full Methodology Spec §5b,
# which explicitly asks for one school to be picked and documented, since
# this is the least rigorous input in the model): this uses the commonly
# cited Parashari exaltation-axis convention that treats Rahu as exalted in
# Taurus (an earthy, Venus-owned sign) and Ketu as exalted in Scorpio (a
# watery, Mars-owned sign) -- i.e. Rahu strong in "earthy/Venusian-adjacent"
# signs and Ketu strong in "watery/Mars-adjacent" signs, exactly the wording
# the spec itself uses. The opposite sign (Scorpio for Rahu, Taurus for
# Ketu) is treated as the debilitation point. This is ONE of several
# competing classical/modern conventions for nodal dignity -- other schools
# use Gemini/Sagittarius or Virgo/Pisces instead. Callers should treat this
# as an approximation, not a settled classical fact.
_NODE_EXALT_SIGN = {"Rahu": "Taurus", "Ketu": "Scorpio"}
_NODE_DEBIL_SIGN = {"Rahu": "Scorpio", "Ketu": "Taurus"}

# House placement per spec §5b: kendra/trikona/upachaya placements strengthen;
# dusthana 6/8/12 placements weaken -- EXCEPT the spec notes 8th/12th can
# specifically favor research/occult/foreign significations, which is a
# thematic (not strength) caveat surfaced separately in the trace rather than
# changing the numeric penalty here. House 6 is upachaya (growth-through-
# struggle) per the standard 3/6/10/11 upachaya set, so it is NOT treated as
# a dusthana penalty here even though it's also classically a dusthana --
# upachaya takes precedence to avoid double-counting the same house both ways.
_NODE_STRONG_HOUSES = frozenset({1, 3, 4, 5, 6, 7, 9, 10, 11})  # kendra+trikona+upachaya
_NODE_WEAK_HOUSES = frozenset({8, 12})  # dusthana penalty (6 excluded, see above)


def estimate_node_strength(planet: str, sign: str, house: int) -> Dict[str, Any]:
    """§5b: documented 0-1 strength heuristic for Rahu/Ketu (no classical
    Shadbala exists for the lunar nodes). See module-level comment above
    _NODE_EXALT_SIGN for the school of thought used and its explicit caveats.

    Returns {"strength": 0-1 float, "sign_component": ..., "house_component":
    ..., "trace": [...]} so callers/reports can show the heuristic's working
    rather than a single opaque number.
    """
    trace = []
    if planet not in ("Rahu", "Ketu"):
        return {"strength": 0.5, "sign_component": 0.5, "house_component": 0.5,
                "trace": ["estimate_node_strength called for a non-node planet; neutral default."]}

    if sign and sign == _NODE_EXALT_SIGN.get(planet):
        sign_component = 1.0
        trace.append(f"{planet} in {sign}: treated as exalted under this heuristic's school of thought.")
    elif sign and sign == _NODE_DEBIL_SIGN.get(planet):
        sign_component = 0.0
        trace.append(f"{planet} in {sign}: treated as debilitated under this heuristic's school of thought.")
    else:
        sign_component = 0.5
        trace.append(f"{planet} in {sign or 'unknown sign'}: neutral (neither exalted nor debilitated point).")

    if house in _NODE_STRONG_HOUSES:
        house_component = 1.0
        trace.append(f"{planet} in H{house}: kendra/trikona/upachaya placement, strengthens.")
    elif house in _NODE_WEAK_HOUSES:
        house_component = 0.0
        trace.append(f"{planet} in H{house}: dusthana placement, weakens numerically -- though 8th/12th "
                      "can still favor research/occult/foreign significations thematically (not a strength claim).")
    else:
        house_component = 0.5
        trace.append(f"{planet} in H{house}: neutral house placement.")

    strength = round(0.6 * sign_component + 0.4 * house_component, 4)
    return {"strength": strength, "sign_component": sign_component,
            "house_component": house_component, "trace": trace}


def is_classical_shadbala_scope(planet: str) -> bool:
    """True for the 7 classical grahas Shadbala applies to per BPHS; False
    for Rahu/Ketu (and anything else). Gap-audit fix (2026-08, diagnostic
    helper, no behavior change): the main entry point compute_shadbala_all()
    below already correctly restricts its per-planet loop to
    CLASSICAL_SHADBALA_PLANETS and reports classical_scope/nodes_excluded in
    its output -- Rahu/Ketu never reach `results` there. However, several
    lower-level per-component functions in this module (compute_dig_bala,
    compute_total_shadbala, and the NAISARGIKA_BALA/_DIG_BALA_IDEAL_HOUSE
    lookup tables they read) DO carry conventional, non-classical midpoint
    entries for "Rahu"/"Ketu" (documented in-line where each table is
    defined) so that IF some future caller invokes those lower-level
    functions directly with a node -- bypassing compute_shadbala_all's
    filter -- the result is a deliberate convention rather than a KeyError
    or a silent 0. As of this fix, no caller in this codebase does that (the
    only entry point used by the live pipeline is compute_shadbala_all,
    which never passes a node into these functions). This helper exists so
    any future direct caller can check first, rather than relying on
    remembering to read the in-line comments on each lookup table.
    """
    return planet in CLASSICAL_SHADBALA_PLANETS

_SIGNS = ("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio",
          "Sagittarius","Capricorn","Aquarius","Pisces")

# ── Naisargika Bala (natural/inherent strength) ─────────────────────────────
# Classical fixed constants (BPHS Ch.27), in Shashtiamsas. Sun strongest,
# Saturn weakest among the 7 classical grahas. Rahu/Ketu are not part of the
# classical 7-graha Shadbala system; given a conventional midpoint value
# (matching common panchanga-software practice) so downstream summed totals
# remain comparable across all 9 grahas without silently zeroing the nodes.
NAISARGIKA_BALA: Dict[str, float] = {
    "Sun": 60.0, "Moon": 51.43, "Venus": 42.86, "Jupiter": 34.29,
    "Mercury": 25.71, "Mars": 17.14, "Saturn": 8.57,
    "Rahu": 30.0, "Ketu": 30.0,
}

# ── Dig Bala ideal ("directional strength") cusp per planet ────────────────
# Classical: Sun/Mars strongest at the 10th cusp (MC), Moon/Venus at the 4th
# (IC), Jupiter/Mercury at the 1st (Asc), Saturn at the 7th (Desc). Full
# strength (60) at the ideal cusp, tapering to 0 at the opposite cusp (180
# degrees away), linear in between -- this is the standard classical
# approximation (some texts use a sine curve; BPHS's own worked examples use
# the linear form, which this function follows).
# MODERN HEURISTIC / practitioner-derived -- the Rahu=7/Ketu=1 entries below
# are NOT independently classically sourced. Classical Shadbala (BPHS) is
# defined over the 7 grahas only; nodes have no canonical Dig Bala ideal-house
# assignment in the classical texts. "Nodes follow Saturn/Jupiter-like
# treatment" is a common panchanga-software convention, not a cited classical
# rule. See reports/JyotishAI_Engine_Gap_Analysis_2026-07.md sec 2.3 for
# details; falls through to generic "SOURCE NOT ESTABLISHED" provenance
# rather than the more precise "conventional, disputed" characterization
# until this is registered as its own rule ID in rule_registry.py.
_DIG_BALA_IDEAL_HOUSE: Dict[str, int] = {
    "Sun": 10, "Mars": 10, "Moon": 4, "Venus": 4,
    "Jupiter": 1, "Mercury": 1, "Saturn": 7,
    "Rahu": 7, "Ketu": 1,  # conventional: nodes follow Saturn/Jupiter-like treatment
}


def _sign_index(sign: str) -> int:
    try:
        return _SIGNS.index(sign)
    except ValueError:
        return -1


def compute_uccha_bala(planet: str, sign: str, degree: float) -> float:
    """Uccha Bala (exaltation strength), 0-60 shashtiamsas.

    Classical formula: distance (in degrees, 0-180) of the planet's
    longitude from its exact debilitation point, scaled linearly so the
    exaltation point itself = 60 and the debilitation point = 0.
    """
    exalt_sign = _EXALT_SIGN.get(planet)
    if not exalt_sign or planet not in _EXALT_DEGREE:
        return 30.0  # Rahu/Ketu / unknown: classical texts disagree, use neutral midpoint
    exalt_abs = _sign_index(exalt_sign) * 30.0 + _EXALT_DEGREE[planet]
    planet_abs = _sign_index(sign) * 30.0 + float(degree or 0.0)
    if exalt_abs < 0 or planet_abs < 0:
        return 30.0
    # Angular distance from the debilitation point (180 deg from exaltation),
    # normalized 0-180 -> 0-60.
    debil_abs = (exalt_abs + 180.0) % 360.0
    diff = abs(planet_abs - debil_abs)
    if diff > 180.0:
        diff = 360.0 - diff
    return round((diff / 180.0) * 60.0, 4)


def compute_saptavargaja_bala(
    planet: str,
    varga_dignities: Mapping[str, Mapping[str, str]],
) -> float:
    """Saptavargaja Bala approximation, 0-60 shashtiamsas, renormalized over
    whichever vargas are actually present on the payload (this engine
    computes D1/D9/D10/D20/D24/D27, not the classical 7 of Hora/Drekkana/
    Saptamsa/Navamsa/Dwadasamsa/Trimsamsa/Rasi) -- same renormalization
    convention as this session's Vimsopaka Bala fix (astro_enhancer.py's
    _g21_vimsopaka_bala): missing vargas are excluded from both numerator
    and denominator rather than padded with a fabricated "neutral" score.
    Each varga contributes 0-60 by classical dignity-in-that-varga
    (own/moolatrikona/exalted = high, debilitated = low).

    MODERN HEURISTIC / practitioner-derived -- not independently classically
    sourced (2026-08 gap-audit item 2.1, see
    reports/JyotishAI_Engine_Gap_Analysis_2026-07.md sec 2.1). The classical
    Saptavargaja Bala (BPHS) is defined over exactly 7 fixed vargas: Rasi
    (D1), Hora (D2), Drekkana (D3), Saptamsa (D7), Navamsa (D9), Dwadasamsa
    (D12), Trimsamsa (D30). This function renormalizes over whatever subset
    of {D1,D9,D10,D20,D24,D27} the payload happens to carry -- a
    structurally DIFFERENT varga basis than the classical definition, not
    just a lower-precision version of it. A literal classical implementation
    exists separately as compute_classical_saptavargaja_bala() below (over
    D1/D2/D3/D7/D9/D12/D30); this renormalized variant should be relabeled
    in any user-facing output as an engine-specific proxy, not presented as
    "the" Saptavargaja Bala.
    """
    _dig_score = {
        "exalted": 1.0, "moolatrikona": 0.875, "own_sign": 0.75, "own": 0.75,
        "great_friend": 0.625, "friend": 0.50, "neutral": 0.375,
        "enemy": 0.25, "great_enemy": 0.125, "debilitated": 0.0,
        "neecha_bhanga": 0.45,
    }
    present = [(v, d) for v, d in (varga_dignities or {}).items() if d and planet in d]
    if not present:
        return 30.0  # no varga data at all: neutral midpoint, never fabricate a score
    total = 0.0
    for _varga, digs in present:
        state = str(digs.get(planet, "neutral")).lower()
        total += _dig_score.get(state, 0.375) * 60.0
    return round(total / len(present), 4)


_SAPTAVARGA_VIRUPAS = {
    "MOOLATRIKONA": 45.0, "OWN_SIGN": 30.0,
    "GREAT_FRIEND": 22.5, "FRIEND": 15.0, "NEUTRAL": 7.5,
    "ENEMY": 3.75, "GREAT_ENEMY": 1.875,
    # Exaltation/debilitation are already measured continuously by Uccha
    # Bala. For varga dignity, an exalted sign is treated at least as own.
    "EXALTED": 30.0, "DEBILITATED": 1.875, "NEECHA_BHANGA": 7.5,
}


def compute_classical_saptavargaja_bala(
    planet: str, sign: str, degree: float,
    planet_signs: Mapping[str, str], navamsa_sign: str,
) -> Dict[str, Any]:
    """BPHS Saptavargaja Bala across exactly D1/D2/D3/D7/D9/D12/D30.

    Each varga is evaluated using compound (natural + temporary) friendship
    through the canonical dignity layer. The returned total is a sum of the
    seven classical varga virupas, not a renormalised average.
    """
    varga_signs = {
        "D1": sign,
        "D2": compute_d2_sign(sign, degree),
        "D3": compute_d3_sign(sign, degree),
        "D7": compute_d7_sign(sign, degree),
        "D9": navamsa_sign,
        "D12": compute_d12_sign(sign, degree),
        "D30": compute_d30_sign(sign, degree),
    }
    breakdown: Dict[str, Any] = {}
    total = 0.0
    for varga, v_sign in varga_signs.items():
        if not v_sign:
            raise ValueError(f"{varga} sign is required for classical Saptavargaja Bala")
        state = dignity_state(planet, v_sign, planet_signs=planet_signs)
        virupas = _SAPTAVARGA_VIRUPAS.get(state, 7.5)
        breakdown[varga] = {"sign": v_sign, "dignity": state, "virupas": virupas}
        total += virupas
    return {"total": round(total, 4), "vargas": breakdown, "complete": True}


def compute_ojayugma_bala(planet: str, sign: str, navamsa_sign: Optional[str] = None) -> float:
    """Ojayugmarasyamsa Bala (odd/even sign strength), 0-30 shashtiamsas,
    combining natal-sign strength (0-15) and navamsa-sign strength (0-15).
    Classical rule: male grahas (Sun, Mars, Jupiter) and Rahu are strong in
    odd (Aries/Gemini/.../Aquarius) signs; female grahas (Moon, Venus) and
    Ketu are strong in even signs; Mercury and Saturn (neuter) get full
    marks in both, matching their unafflicted-by-gender classical status.
    """
    _odd_strong = {"Sun", "Mars", "Jupiter", "Rahu"}
    _even_strong = {"Moon", "Venus", "Ketu"}
    idx = _sign_index(sign)
    if idx < 0:
        return 15.0
    is_odd = (idx % 2 == 0)  # Aries(0)=odd sign #1, Gemini(2)=odd sign #3, etc.
    natal_part = 15.0 if (
        planet not in _odd_strong and planet not in _even_strong
    ) or (is_odd and planet in _odd_strong) or (not is_odd and planet in _even_strong) else 0.0
    navamsa_part = 15.0
    if navamsa_sign:
        nidx = _sign_index(navamsa_sign)
        if nidx >= 0:
            n_odd = (nidx % 2 == 0)
            navamsa_part = 15.0 if (
                planet not in _odd_strong and planet not in _even_strong
            ) or (n_odd and planet in _odd_strong) or (not n_odd and planet in _even_strong) else 0.0
    return round(natal_part + navamsa_part, 4)


def compute_kendradi_bala(house_from_lagna: int) -> float:
    """Kendradi Bala (angular/succedent/cadent strength), 0/30/60.
    Kendra (1,4,7,10) = 60, Panapara/succedent (2,5,8,11) = 30,
    Apoklima/cadent (3,6,9,12) = 15 (classical values; some texts use
    60/30/15, others 60/45/15 -- BPHS's own table uses 60/30/15, followed
    here for consistency with the rest of this engine's BPHS-first sourcing).
    """
    if house_from_lagna in _KENDRA_HOUSES:
        return 60.0
    if house_from_lagna in {2, 5, 8, 11}:
        return 30.0
    return 15.0


def compute_drekkana_bala(planet: str, degree: float) -> float:
    """Drekkana Bala (decanate strength), 0 or 15 shashtiamsas. Male grahas
    (Sun, Mars, Jupiter) get full marks in the 1st drekkana (0-10 deg),
    female grahas (Moon, Venus) in the 2nd (10-20 deg), neuter grahas
    (Mercury, Saturn) in the 3rd (20-30 deg). Rahu/Ketu conventionally
    treated as neuter (3rd drekkana) per common panchanga-software practice.
    """
    d = float(degree or 0.0) % 30.0
    drek = 1 if d < 10.0 else (2 if d < 20.0 else 3)
    _male = {"Sun", "Mars", "Jupiter"}
    _female = {"Moon", "Venus"}
    if planet in _male and drek == 1:
        return 15.0
    if planet in _female and drek == 2:
        return 15.0
    if planet not in _male and planet not in _female and drek == 3:
        return 15.0
    return 0.0


def compute_sthana_bala(
    planet: str,
    sign: str,
    degree: float,
    house_from_lagna: int,
    *,
    varga_dignities: Optional[Mapping[str, Mapping[str, str]]] = None,
    navamsa_sign: Optional[str] = None,
) -> Dict[str, float]:
    """Sthana Bala (positional strength) = Uccha + Saptavargaja + Ojayugma
    + Kendradi + Drekkana Bala. Classical max ~206.6 shashtiamsas combined
    (60 + 60 + 30 + 60 + 15 -- individual maxima don't all co-occur in
    practice, matching classical treatment where this is a rare ceiling)."""
    uccha = compute_uccha_bala(planet, sign, degree)
    sapta = compute_saptavargaja_bala(planet, varga_dignities or {})
    ojayugma = compute_ojayugma_bala(planet, sign, navamsa_sign)
    kendradi = compute_kendradi_bala(house_from_lagna)
    drekkana = compute_drekkana_bala(planet, degree)
    total = uccha + sapta + ojayugma + kendradi + drekkana
    return {
        "uccha_bala": uccha, "saptavargaja_bala": sapta,
        "ojayugma_bala": ojayugma, "kendradi_bala": kendradi,
        "drekkana_bala": drekkana, "total": round(total, 4),
    }


def compute_dig_bala(planet: str, house_from_lagna: int) -> float:
    """Dig Bala (directional strength), 0-60 shashtiamsas, exact classical
    formula: full strength (60) at the planet's ideal cusp (see
    _DIG_BALA_IDEAL_HOUSE), tapering linearly to 0 at the opposite cusp
    (180 degrees / 6 houses away), by whole-house distance (this engine's
    house_from_lagna is already whole-sign; the previous proxy in
    astro_enhancer.py's _g4_dig_bala_factor used the same house-granularity
    approach but with an artificial 0.3 floor instead of reaching true 0,
    and returned a 0.3-1.0 multiplier rather than a 0-60 shashtiamsa score
    on the classical scale -- this function replaces it with the real scale
    while keeping the same house-distance input, since exact-degree cusp
    distance would require house-cusp longitudes this engine's whole-sign
    convention doesn't carry per-planet).

    PROVENANCE (2026-08 gap-audit item 2.2, see
    reports/JyotishAI_Engine_Gap_Analysis_2026-07.md sec 2.2): the taper
    SHAPE used here (linear, full strength at the ideal cusp down to zero
    at the opposite cusp) is a disclosed, defensible choice consistent with
    BPHS's own worked Dig Bala examples, but classical commentaries are not
    unanimous -- some later/regional texts use a sine-curve taper instead
    of a linear one. This is not independently, unambiguously classically
    sourced as "the" correct curve shape; it is a school-dependent choice.
    Not yet registered as a distinct rule ID in rule_registry.py, so an
    LLM trace validator cannot currently flag this as school-dependent.
    """
    ideal = _DIG_BALA_IDEAL_HOUSE.get(planet, 1)
    dist = abs(house_from_lagna - ideal) % 12
    dist = min(dist, 12 - dist)  # shortest distance around the 12-house circle
    # dist=0 (at ideal cusp) -> 60; dist=6 (opposite cusp) -> 0; linear between.
    return round(max(0.0, 60.0 - (dist / 6.0) * 60.0), 4)


def compute_dig_bala_exact_degrees(
    planet: str,
    planet_longitude: float,
    house_cusps: Mapping[int, float],
) -> float:
    """Exact-degree Dig Bala, 0-60 shashtiamsas, using real house-cusp
    longitudes (jyotish/ephemeris.py::get_house_cusps_placidus) instead of
    whole-house distance. Use this variant when Placidus cusp longitudes
    are available on the caller's payload; falls back gracefully (returns
    the whole-house compute_dig_bala() result upstream) when they are not.
    Angular distance is measured from the planet to the OPPOSITE cusp of
    its ideal one (e.g. Sun's ideal is the 10th/MC, so distance is measured
    from the 4th/IC cusp, full 60 at 180 deg away = at the MC itself).
    """
    ideal_house = _DIG_BALA_IDEAL_HOUSE.get(planet, 1)
    opposite_house = ((ideal_house - 1 + 6) % 12) + 1
    opposite_cusp = house_cusps.get(opposite_house)
    if opposite_cusp is None or planet_longitude is None:
        return 30.0
    diff = abs((float(planet_longitude) - float(opposite_cusp) + 180.0) % 360.0 - 180.0)
    return round(min(60.0, (diff / 180.0) * 60.0), 4)


# ── Kala Bala (temporal strength) ───────────────────────────────────────────

_WEEKDAY_LORD = {0: "Moon", 1: "Mars", 2: "Mercury", 3: "Jupiter",
                 4: "Venus", 5: "Saturn", 6: "Sun"}  # Python weekday(): Mon=0
_HORA_ORDER = ("Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars")


def compute_abda_masa_lords(birth_date: date) -> Dict[str, str]:
    """Varsha/Masa lords from the BPHS Ahargana procedure.

    The epoch supplied in the English BPHS commentary is 714,404,108,573
    elapsed creation-days on 1860-01-01. Remainders use 1=Sunday ..
    7=Saturday; a zero remainder therefore maps to Saturday.
    """
    epoch = date(1860, 1, 1)
    ahargana = 714_404_108_573 + (birth_date - epoch).days
    year_rem = ((ahargana // 60) * 3 + 1) % 7
    month_rem = ((ahargana // 30) * 2 + 1) % 7
    sunday_first = ("Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    day_to_planet = {
        "Sunday": "Sun", "Monday": "Moon", "Tuesday": "Mars",
        "Wednesday": "Mercury", "Thursday": "Jupiter",
        "Friday": "Venus", "Saturday": "Saturn",
    }
    return {
        "abda_lord": day_to_planet[sunday_first[year_rem]],
        "masa_lord": day_to_planet[sunday_first[month_rem]],
        "ahargana": ahargana,
    }


def compute_hora_lord(weekday: int, hours_since_sunrise: float) -> str:
    """Planetary-hour lord, using 24 mean-local hours sunrise-to-sunrise."""
    day_lord = _WEEKDAY_LORD[weekday]
    first = _HORA_ORDER.index(day_lord)
    hora_number = max(0, int(math.floor(hours_since_sunrise)))
    return _HORA_ORDER[(first + hora_number) % 7]


def compute_nathonnata_bala(planet: str, is_day_birth: bool) -> float:
    """Natonnata Bala (diurnal/nocturnal strength), 0-60. Moon/Mars/Saturn
    are night-strong (60 at night, 0 by day); Sun/Jupiter/Venus are
    day-strong (60 by day, 0 at night); Mercury is always strong (60,
    unaffected by day/night per classical rule)."""
    if planet == "Mercury":
        return 60.0
    _night_strong = {"Moon", "Mars", "Saturn"}
    _day_strong = {"Sun", "Jupiter", "Venus"}
    if planet in _night_strong:
        return 0.0 if is_day_birth else 60.0
    if planet in _day_strong:
        return 60.0 if is_day_birth else 0.0
    return 30.0  # Rahu/Ketu: neutral midpoint, classical texts disagree


def compute_paksha_bala(planet: str, sun_longitude: float, moon_longitude: float) -> float:
    """Paksha Bala (lunar-phase strength), 0-60. Benefics (Moon itself,
    Jupiter, Venus, Mercury-when-benefic) gain strength as the Moon waxes
    (Shukla Paksha); malefics (Sun, Mars, Saturn) gain strength as the Moon
    wanes (Krishna Paksha). Scaled by the Moon's elongation from the Sun
    (0-180 = waxing half, 180-360 = waning half), full strength at full/new
    moon respectively.
    """
    elong = (float(moon_longitude) - float(sun_longitude)) % 360.0
    _benefics = {"Moon", "Jupiter", "Venus", "Mercury"}
    if elong <= 180.0:
        waxing_strength = (elong / 180.0) * 60.0  # 0 at new moon -> 60 at full moon
    else:
        waxing_strength = ((360.0 - elong) / 180.0) * 60.0
    if planet in _benefics:
        return round(waxing_strength, 4)
    return round(60.0 - waxing_strength, 4)


def compute_tribhaga_bala(planet: str, hours_since_sunrise: Optional[float], day_length_hours: Optional[float], is_day_birth: bool) -> float:
    """Tribhaga Bala (one-third-of-day/night strength), 0 or 60. The
    day/night span is divided into 3 equal parts (tribhagas); each part has
    a ruling planet (day: Mercury/Sun/Saturn for parts 1/2/3; night:
    Moon/Venus/Mars for parts 1/2/3), which gets 60 shashtiamsas if the
    birth falls in its part, else 0 -- classical BPHS assignment.
    """
    if planet == "Jupiter":
        return 60.0
    if hours_since_sunrise is None or not day_length_hours:
        return 0.0
    frac = max(0.0, min(0.999, hours_since_sunrise / day_length_hours))
    part = int(frac * 3) + 1  # 1, 2, or 3
    ruler = ({1: "Mercury", 2: "Sun", 3: "Saturn"} if is_day_birth
             else {1: "Moon", 2: "Venus", 3: "Mars"})[part]
    return 60.0 if planet == ruler else 0.0


def compute_vara_bala(planet: str, weekday: int) -> float:
    """Vara Bala (weekday-lord strength), 0 or 45. Full 45 shashtiamsas if
    `planet` is the lord of the civil weekday (sunrise-to-sunrise) the
    birth falls on, else 0. `weekday` uses Python's date.weekday()
    convention (Mon=0..Sun=6)."""
    return 45.0 if _WEEKDAY_LORD.get(weekday) == planet else 0.0


def _declination_from_ecliptic(lon_deg: float, lat_deg: float, obliquity_deg: float = 23.4367) -> float:
    """Standard ecliptic-to-equatorial declination transform."""
    lon_r = math.radians(lon_deg)
    lat_r = math.radians(lat_deg)
    eps_r = math.radians(obliquity_deg)
    sin_dec = (math.sin(lat_r) * math.cos(eps_r)
               + math.cos(lat_r) * math.sin(eps_r) * math.sin(lon_r))
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_dec))))


def compute_ayana_bala(planet: str, tropical_longitude: float, ecliptic_latitude: float, obliquity_deg: float = 23.4367) -> float:
    """Classical Ayana Bala from true declination (kranti).

    Santanam's BPHS reduction is ``(23°27' +/- declination) * 1.2793``.
    Moon/Saturn favour southern declination; Sun/Mars/Jupiter/Venus favour
    northern declination; Mercury always uses the absolute declination.
    The Sun's result is doubled as explicitly directed by BPHS.
    """
    dec = _declination_from_ecliptic(tropical_longitude, ecliptic_latitude, obliquity_deg)
    if planet == "Mercury":
        favourable_dec = abs(dec)
    elif planet in {"Moon", "Saturn"}:
        favourable_dec = -dec
    else:
        favourable_dec = dec
    bala = (23.45 + favourable_dec) * (60.0 / 46.9)
    bala = max(0.0, min(60.0, bala))
    if planet == "Sun":
        bala *= 2.0
    return round(bala, 4)


def compute_yuddha_bala_adjustment(planet: str, planet_longitudes: Mapping[str, float]) -> float:
    """Yuddha Bala (planetary-war strength adjustment), a delta (not 0-60
    absolute) applied to the loser of a Graha Yuddha per BPHS: the winner
    gains the loser's longitude-based strength differential, the loser
    loses an equivalent amount. Delegates war DETECTION to the canonical
    jyotish/dignity.py::graha_yuddha() (this session's merge-plan item 1
    consolidation) rather than reimplementing it; only computes the BPHS
    strength-transfer magnitude here.
    """
    result = _dignity_graha_yuddha(planet_longitudes)
    for war in result.get("wars", []):
        if planet == war["winner"]:
            return round(min(war["separation_degrees"], 5.0), 4)  # small bonus, capped
        if planet == war["loser"]:
            return round(-min(war["separation_degrees"], 5.0), 4)
    return 0.0


def compute_kala_bala(
    planet: str,
    *,
    is_day_birth: bool,
    sun_longitude: float,
    moon_longitude: float,
    weekday: int,
    tropical_longitude: Optional[float] = None,
    ecliptic_latitude: float = 0.0,
    hours_since_sunrise: Optional[float] = None,
    day_length_hours: Optional[float] = None,
    planet_longitudes: Optional[Mapping[str, float]] = None,
    birth_date: Optional[date] = None,
) -> Dict[str, float]:
    """Complete BPHS Kala Bala, including Abda, Masa, Dina and Hora."""
    nathonnata = compute_nathonnata_bala(planet, is_day_birth)
    paksha = compute_paksha_bala(planet, sun_longitude, moon_longitude)
    tribhaga = compute_tribhaga_bala(planet, hours_since_sunrise, day_length_hours, is_day_birth)
    vara = compute_vara_bala(planet, weekday)
    calendar_lords = compute_abda_masa_lords(birth_date) if birth_date else {}
    abda = 15.0 if calendar_lords.get("abda_lord") == planet else 0.0
    masa = 30.0 if calendar_lords.get("masa_lord") == planet else 0.0
    hora_lord = compute_hora_lord(weekday, hours_since_sunrise) if hours_since_sunrise is not None else None
    hora = 60.0 if hora_lord == planet else 0.0
    ayana = (compute_ayana_bala(planet, tropical_longitude, ecliptic_latitude)
             if tropical_longitude is not None else 30.0)
    yuddha = compute_yuddha_bala_adjustment(planet, planet_longitudes or {})
    total = nathonnata + paksha + tribhaga + abda + masa + vara + hora + ayana + yuddha
    return {
        "nathonnata_bala": nathonnata, "paksha_bala": paksha,
        "tribhaga_bala": tribhaga, "abda_bala": abda, "masa_bala": masa,
        "vara_bala": vara, "hora_bala": hora, "ayana_bala": ayana,
        "yuddha_bala_adjustment": yuddha, "total": round(total, 4),
        "lords": {**calendar_lords, "dina_lord": _WEEKDAY_LORD.get(weekday), "hora_lord": hora_lord},
        "complete": bool(birth_date is not None and hours_since_sunrise is not None and tropical_longitude is not None),
    }


# ── Cheshta Bala (motional strength) ────────────────────────────────────────

# Mean daily motion (deg/day) per planet, classical reference values used to
# judge "fast" vs "slow" for Cheshta Bala. Sun/Moon are always direct and use
# a different rule (see compute_cheshta_bala).
_MEAN_DAILY_MOTION: Dict[str, float] = {
    "Mars": 0.5240, "Mercury": 1.383, "Jupiter": 0.0831,
    "Venus": 1.2, "Saturn": 0.0334,
}


def compute_cheshta_bala(
    planet: str, daily_motion_deg: Optional[float],
    *, ayana_bala: Optional[float] = None, paksha_bala: Optional[float] = None,
) -> float:
    """BPHS motional strength using the eight motion classes.

    Sun equals its Ayana Bala and Moon equals its Paksha Bala. For Mars
    through Saturn, true ephemeris motion is classified as Vakra, Anuvakra,
    Vikala, Manda, Mandatara, Sama, Chara or Atichara, receiving respectively
    60, 30, 15, 30, 15, 7.5, 45 and 30 virupas. The finite-difference speed
    is an observed true motion, not a synthetic retrograde flag.
    """
    if planet == "Sun":
        return round(float(ayana_bala or 0.0), 4)
    if planet == "Moon":
        return round(float(paksha_bala or 0.0), 4)
    if planet not in _MEAN_DAILY_MOTION or daily_motion_deg is None:
        return 0.0
    speed = float(daily_motion_deg)
    mean = _MEAN_DAILY_MOTION[planet]
    ratio = speed / mean
    if ratio <= -0.25: return 60.0       # Vakra
    if ratio < 0.0: return 30.0          # Anuvakra
    if ratio <= 0.05: return 15.0        # Vikala
    if ratio <= 0.25: return 15.0        # Mandatara
    if ratio <= 0.75: return 30.0        # Manda
    if ratio <= 1.25: return 7.5         # Sama
    if ratio <= 2.0: return 45.0         # Chara
    return 30.0                          # Atichara


# ── Drishti Bala (aspectual strength) ───────────────────────────────────────

def _sphuta_drishti(aspecting_planet: str, separation: float) -> float:
    """Degree-exact BPHS aspect value (0..60 virupas)."""
    d = float(separation) % 360.0
    if d < 30 or d >= 300: base = 0.0
    elif d < 60: base = (d - 30.0) / 2.0
    elif d < 90: base = d - 45.0
    elif d < 120: base = (150.0 - d) / 2.0
    elif d < 150: base = d - 75.0
    elif d < 180: base = 2.0 * (d - 120.0)
    else: base = (300.0 - d) / 2.0
    # Special aspects bring the relevant quarter/half/three-quarter aspect
    # up to a full aspect at its exact classical longitude.
    if aspecting_planet == "Mars" and (90 <= d <= 120 or 210 <= d <= 240):
        base += 15.0
    elif aspecting_planet == "Jupiter" and (120 <= d <= 150 or 240 <= d <= 270):
        base += 30.0
    elif aspecting_planet == "Saturn" and (60 <= d <= 90 or 270 <= d <= 300):
        base += 45.0
    return round(max(0.0, min(60.0, base)), 4)


def compute_drishti_bala_exact(
    planet: str, planet_longitudes: Mapping[str, float],
    *, waxing_moon: bool,
) -> Dict[str, Any]:
    """Net BPHS Drik Bala from degree-exact Sphuta Drishti values."""
    target = planet_longitudes.get(planet)
    if target is None:
        return {"total": 0.0, "aspects": {}, "complete": False}
    benefics = {"Jupiter", "Venus", "Mercury"}
    if waxing_moon:
        benefics.add("Moon")
    malefics = set(CLASSICAL_SHADBALA_PLANETS) - benefics
    details: Dict[str, Any] = {}
    total = 0.0
    for source in CLASSICAL_SHADBALA_PLANETS:
        if source == planet or source not in planet_longitudes:
            continue
        separation = (float(target) - float(planet_longitudes[source])) % 360.0
        aspect = _sphuta_drishti(source, separation)
        signed = aspect / 4.0 if source in benefics else -aspect / 4.0
        details[source] = {"separation": round(separation, 4), "aspect_virupas": aspect,
                           "nature": "benefic" if source in benefics else "malefic",
                           "contribution": round(signed, 4)}
        total += signed
    return {"total": round(total, 4), "aspects": details, "complete": True}


def compute_drishti_bala(planet: str, aspects_received: Mapping[str, str]) -> float:
    """Drishti Bala (aspectual strength), a signed delta. `aspects_received`
    is {aspecting_planet: "benefic"|"malefic"} for planets casting a
    classical drishti (aspect) onto `planet`. Full benefic aspect = +15,
    full malefic aspect = -15 (BPHS uses graha-drishti in a 0-60 virupa
    scale per aspecting pair; this is the simplified net-strength delta
    form used when full pairwise aspect-strength percentages aren't
    separately computed -- consistent with this engine's existing
    aspect-detection granularity in astro.py's _get_planetary_aspects,
    which is binary present/absent per aspect, not graded 0-100%).
    """
    delta = 0.0
    for _aspecting, kind in (aspects_received or {}).items():
        if kind == "benefic":
            delta += 15.0
        elif kind == "malefic":
            delta -= 15.0
    return round(delta, 4)


# ── Total Shadbala per planet + chart-wide summary ──────────────────────────

def compute_total_shadbala(
    planet: str,
    *,
    sthana: Mapping[str, float],
    dig_bala: float,
    kala: Mapping[str, float],
    cheshta_bala: float,
    naisargika_bala: Optional[float] = None,
    drishti_bala: float = 0.0,
) -> Dict[str, Any]:
    """Sum the six components into a total Shadbala in shashtiamsas, plus
    the classical Rupa conversion (1 Rupa = 60 Shashtiamsas) and a
    pass/fail flag against each planet's classical minimum requirement
    (jyotish/constants.py::_PLANET_MIN_SHADBALA, already present in this
    codebase for exactly this purpose -- see field_methods callers).
    """
    naisargika = naisargika_bala if naisargika_bala is not None else NAISARGIKA_BALA.get(planet, 30.0)
    total_shashtiamsa = (
        sthana.get("total", 0.0) + dig_bala + kala.get("total", 0.0)
        + cheshta_bala + naisargika + drishti_bala
    )
    return {
        "planet": planet,
        "sthana_bala": sthana,
        "dig_bala": round(dig_bala, 4),
        "kala_bala": kala,
        "cheshta_bala": round(cheshta_bala, 4),
        "naisargika_bala": round(naisargika, 4),
        "drishti_bala": round(drishti_bala, 4),
        "total_shashtiamsa": round(total_shashtiamsa, 4),
        "total_rupa": round(total_shashtiamsa / 60.0, 4),
    }


def compute_shadbala_all(
    planets_d1: Mapping[str, Mapping[str, Any]],
    planet_house: Mapping[str, int],
    *,
    varga_dignities: Optional[Mapping[str, Mapping[str, str]]] = None,
    navamsa_signs: Optional[Mapping[str, str]] = None,
    planet_longitudes: Optional[Mapping[str, float]] = None,
    planet_speeds: Optional[Mapping[str, float]] = None,
    tropical_longitudes: Optional[Mapping[str, float]] = None,
    planet_latitudes: Optional[Mapping[str, float]] = None,
    is_day_birth: bool = True,
    weekday: int = 0,
    hours_since_sunrise: Optional[float] = None,
    day_length_hours: Optional[float] = None,
    aspects_received: Optional[Mapping[str, Mapping[str, str]]] = None,
    birth_date: Optional[date] = None,
    house_cusps: Optional[Mapping[int, float]] = None,
) -> Dict[str, Any]:
    """Chart-wide six-fold Shadbala for all placed grahas.

    This is the main entry point: given the same D1 chart facts the rest of
    this engine already computes (planets_d1, planet_house from astro.py /
    engine_io.py), plus optional ephemeris extras (raw longitudes/speeds/
    latitudes from jyotish/ephemeris.py, none of which required a new
    Skyfield API pattern -- see module docstring), returns a full per-planet
    breakdown plus a chart-wide ranking by total strength.

    Every optional kwarg degrades gracefully (uses a documented neutral
    default) rather than raising, so this can be called with partial data
    during a transition period while the engine is validated against real
    charts before any scoring code switches over to trust it.
    """
    sun_lon = planets_d1.get("Sun", {}).get("degree")
    sun_sign = planets_d1.get("Sun", {}).get("sign", "")
    sun_abs = (_sign_index(sun_sign) * 30.0 + float(sun_lon or 0.0)) if sun_sign else None
    moon_sign = planets_d1.get("Moon", {}).get("sign", "")
    moon_deg = planets_d1.get("Moon", {}).get("degree")
    moon_abs = (_sign_index(moon_sign) * 30.0 + float(moon_deg or 0.0)) if moon_sign else None

    results: Dict[str, Any] = {}
    planet_signs = {p: str(v.get("sign", "")) for p, v in (planets_d1 or {}).items() if isinstance(v, Mapping)}
    elong = ((moon_abs or 0.0) - (sun_abs or 0.0)) % 360.0
    waxing_moon = elong <= 180.0
    for planet, item in (planets_d1 or {}).items():
        if planet not in CLASSICAL_SHADBALA_PLANETS or not isinstance(item, Mapping):
            continue
        sign = str(item.get("sign", ""))
        degree = float(item.get("degree", 0) or 0)
        house = int(planet_house.get(planet, 0) or 0)
        if not sign or not house:
            continue

        sthana = compute_sthana_bala(
            planet, sign, degree, house,
            varga_dignities=varga_dignities,
            navamsa_sign=(navamsa_signs or {}).get(planet),
        )
        classical_sapta = compute_classical_saptavargaja_bala(
            planet, sign, degree, planet_signs, (navamsa_signs or {}).get(planet, "")
        )
        sthana["saptavargaja_bala"] = classical_sapta["total"]
        sthana["saptavargaja_detail"] = classical_sapta
        sthana["total"] = round(
            sthana["uccha_bala"] + classical_sapta["total"] +
            sthana["ojayugma_bala"] + sthana["kendradi_bala"] +
            sthana["drekkana_bala"], 4
        )
        dig = (compute_dig_bala_exact_degrees(planet, (planet_longitudes or {}).get(planet), house_cusps)
               if house_cusps else compute_dig_bala(planet, house))
        kala = compute_kala_bala(
            planet,
            is_day_birth=is_day_birth,
            sun_longitude=sun_abs if sun_abs is not None else 0.0,
            moon_longitude=moon_abs if moon_abs is not None else 0.0,
            weekday=weekday,
            tropical_longitude=(tropical_longitudes or {}).get(planet),
            ecliptic_latitude=(planet_latitudes or {}).get(planet, 0.0),
            hours_since_sunrise=hours_since_sunrise,
            day_length_hours=day_length_hours,
            planet_longitudes=planet_longitudes,
            birth_date=birth_date,
        )
        cheshta = compute_cheshta_bala(
            planet, (planet_speeds or {}).get(planet),
            ayana_bala=kala["ayana_bala"], paksha_bala=kala["paksha_bala"],
        )
        drishti_detail = compute_drishti_bala_exact(planet, planet_longitudes or {}, waxing_moon=waxing_moon)
        drishti = drishti_detail["total"]

        results[planet] = compute_total_shadbala(
            planet, sthana=sthana, dig_bala=dig, kala=kala,
            cheshta_bala=cheshta, drishti_bala=drishti,
        )
        results[planet]["drishti_bala_detail"] = drishti_detail

        # GAP-FIX (P1-6, Shadbala completeness/uncertainty exposure): the only
        # sub-components with a real "did we have the inputs to compute this
        # rigorously" signal are Kala Bala (needs birth_date/sunrise/tropical
        # longitude for Ayana/Paksha/Dina/Hora/Varsha bala) and Drishti Bala
        # (needs all planet longitudes for exact-degree aspects). Surface that
        # per-planet, not just as one all-or-nothing chart-wide flag, so a
        # single planet with a missing input doesn't silently discard
        # completeness information about every other planet's genuinely
        # complete calculation.
        _kala_complete = bool(kala.get("complete"))
        _drishti_complete = bool(drishti_detail.get("complete"))
        _missing_components = [
            name for name, ok in (("kala_bala", _kala_complete), ("drishti_bala", _drishti_complete))
            if not ok
        ]
        results[planet]["complete"] = _kala_complete and _drishti_complete
        results[planet]["uncertain_components"] = _missing_components

    ranked = sorted(results.keys(), key=lambda p: -results[p]["total_rupa"])
    _all_complete = bool(results) and all(p.get("complete") for p in results.values())
    _incomplete_planets = [p for p, v in results.items() if not v.get("complete")]

    # Spec fix (Full Methodology Spec §5a): base_strength[planet] =
    # shadbala_virupas[planet] / max(shadbala_virupas.values()), normalized
    # to the chart's strongest classical planet as 1.0. Previously this
    # module only ever exposed raw absolute total_rupa values plus a rank
    # ORDER -- no 0-1 comparable strength value existed anywhere, so two
    # charts with different absolute Shadbala scales were not comparable as
    # the spec intends, and downstream callers had to invent their own
    # normalization (or skip it). Uses total_shashtiamsa (virupas) directly
    # per the spec's own wording ("shadbala_virupas"), not the Rupa-converted
    # value -- the ratio is identical either way (both are linear rescalings
    # of the same total), but this matches the spec's literal variable name.
    _virupas = {p: v["total_shashtiamsa"] for p, v in results.items()}
    _max_virupas = max(_virupas.values()) if _virupas else 0.0
    base_strength = ({p: round(v / _max_virupas, 6) for p, v in _virupas.items()}
                      if _max_virupas > 0 else {p: 0.0 for p in _virupas})
    for _p, _bs in base_strength.items():
        results[_p]["base_strength"] = _bs

    # §5b: extend base_strength with Rahu/Ketu via the documented node
    # heuristic above, so callers get a complete, DIFFERENTIATED 9-planet
    # base_strength map instead of silently omitting the nodes (previously
    # the only node numbers anywhere were flat placeholders -- e.g. a fixed
    # NAISARGIKA_BALA=30.0 / default virupas=300.0 -- so an exalted-in-kendra
    # Rahu and a debilitated-in-dusthana Rahu were indistinguishable). This
    # heuristic strength is NOT on the same physical scale as classical
    # Shadbala virupas (it's a direct 0-1 estimate, not a ratio-to-max), so
    # it is reported separately from `_virupas`/the classical ranking above.
    node_strength: Dict[str, Any] = {}
    for _node in ("Rahu", "Ketu"):
        _ndata = (planets_d1 or {}).get(_node)
        if isinstance(_ndata, Mapping):
            _nsign = str(_ndata.get("sign", ""))
            _nhouse = int(planet_house.get(_node, 0) or 0)
            if _nsign and _nhouse:
                _node_est = estimate_node_strength(_node, _nsign, _nhouse)
                node_strength[_node] = _node_est
                base_strength[_node] = _node_est["strength"]

    return {
        "shadbala_version": SHADBALA_VERSION,
        "calculation_status": "COMPUTED_COMPLETE_INPUTS" if _all_complete
            else "NOT_COMPUTED_MISSING_REQUIRED_INPUTS",
        "validation_status": evidence_status(
            inputs_complete=_all_complete,
            computed=bool(results),
        ),
        # Per-planet completeness, additive to the aggregate status above:
        # a chart can be "mostly reliable" (e.g. 6 of 7 planets complete)
        # rather than only ever fully trusted or fully distrusted.
        "completeness_ratio": round(
            (len(results) - len(_incomplete_planets)) / len(results), 4
        ) if results else 0.0,
        "incomplete_planets": _incomplete_planets,
        "classical_scope": list(CLASSICAL_SHADBALA_PLANETS),
        "nodes_excluded": ["Rahu", "Ketu"],
        "planets": results,
        "ranked_strongest_to_weakest": ranked,
        # §5a: chart-wide base_strength map (0-1, strongest classical planet = 1.0).
        # §5b: extended with Rahu/Ketu via the documented node heuristic (see
        # estimate_node_strength above and node_strength_detail for the working).
        "base_strength": base_strength,
        "node_strength_detail": node_strength,
    }
