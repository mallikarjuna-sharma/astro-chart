"""JyotishAI — Core Vedic astrological calculations.

Covers: dignity, Bhava Chalit, Graha Drishti (with Drishti Bala),
Neecha Bhanga, yoga detection, combustion, Shadbala-derived effective strengths.
"""
import logging as _logging
import math as _math
from datetime import date
from typing import Dict, List, Tuple, Set, Any, Optional

_logger = _logging.getLogger("jyotish_engine_v11_0")

# Gap-audit fix (2026-08, diagnostic-only): the architecture docs describe
# effective strength as an informal "0-3" scale, but _compute_eff_strengths
# below is a product of ~13 independently-tuned multipliers with a floor
# (0.05) and NO enforced ceiling -- affinity.py's own docstring already
# notes "values above 2.0 are observed". This constant is used ONLY to flag
# outliers in the trace/output below for visibility; it does NOT clamp or
# otherwise change `eff` itself, so no score/ranking is affected.
_EFF_STRENGTH_OUTLIER_THRESHOLD = 3.0

from .constants import (
    _EXALT_SIGN, _DEBIL_SIGN, _OWN_SIGN, _DIGNITY_MOD, _RETRO_EXALTED_DAMPENED,
    _KENDRA_HOUSES, _KT_HOUSES, _COMBUST_ORB,
    _NODAL_DEFAULT_VIRUPAS, _PLANET_MIN_SHADBALA,
    _NAKSHATRA_LORD, _FAVORABLE_NAKSHATRA_BASE,
    _NEECHA_BHANGA_DATA, _SIGN_NUM, _SIGN_LORD,
    _EXALT_DEGREE, _DEBIL_DEGREE, _MOOLATRIKONA,
)

# Gap-3 fix: node (Rahu/Ketu) 0-1 sign+house strength heuristic. shadbala.py
# does not import astro.py, so this top-level import is cycle-free (unlike
# boosts.py, which imports FROM astro.py -- any astro.py -> boosts.py
# reference must therefore be a deferred/local import inside the function
# that needs it, see _compute_eff_strengths below).
from .shadbala import estimate_node_strength as _estimate_node_strength



_SIGN_ABS: Dict[str, float] = {
    "Aries": 0, "Taurus": 30, "Gemini": 60, "Cancer": 90,
    "Leo": 120, "Virgo": 150, "Libra": 180, "Scorpio": 210,
    "Sagittarius": 240, "Capricorn": 270, "Aquarius": 300, "Pisces": 330,
}

def compute_dignity(planet: str, sign: str, planets_d1: Dict = None,
                     degree: Optional[float] = None) -> str:
    """
    ASTRO-7: Sanivad Rahu, Kujavad Ketu. Nodes act as their dispositor.

    `degree` (0-30, position within `sign`) is optional. When supplied it
    enables classically correct degree-level dignity:
      - Moolatrikona is checked as its own dignity tier (sign match alone
        is NOT sufficient — BPHS gives an explicit degree range within the
        MT sign; outside that range the same sign is just OWN).
      - EXALTED/DEBILITATED sign-boundary cases (e.g. a planet at 0.1°
        into its exaltation sign) are still returned as EXALTED/DEBILITATED
        for backward compatibility (dignity is a sign-level classification
        classically), but callers that want graded strength should use
        `dignity_strength()` alongside this, which factors in exact
        proximity to the exaltation/debilitation point.
    When `degree` is omitted, behaviour is unchanged from the legacy
    sign-only implementation (Moolatrikona can never be emitted).
    """
    if planet in ("Rahu", "Ketu") and planets_d1:
        # Node adopts the dignity of the lord of the sign it sits in
        dispositor = _SIGN_LORD.get(sign, "")
        if dispositor:
            disp_data = planets_d1.get(dispositor, {})
            disp_sign = disp_data.get("sign", "")
            if disp_sign:
                return compute_dignity(dispositor, disp_sign, degree=disp_data.get("degree"))

    if degree is not None and planet in _MOOLATRIKONA:
        mt_sign, mt_start, mt_end = _MOOLATRIKONA[planet]
        if sign == mt_sign and mt_start <= degree <= mt_end:
            return "MOOLATRIKONA"

    if _EXALT_SIGN.get(planet) == sign: return "EXALTED"
    if _DEBIL_SIGN.get(planet)  == sign: return "DEBILITATED"
    if sign in _OWN_SIGN.get(planet, []): return "OWN"
    return ""


def dignity_strength(planet: str, sign: str, degree: float) -> float:
    """Graded 0.0-1.0 dignity strength based on exact proximity to the
    exaltation/debilitation point, per classical Saptavargaja/Shadbala
    doctrine (strength tapers linearly across the sign, peaking at the
    exaltation degree and bottoming at the debilitation degree — these
    are always 180 deg apart, i.e. same degree-number in opposite signs).

    Returns 1.0 at exact exaltation degree, 0.0 at exact debilitation
    degree, ~0.5 at a sign boundary/neutral point. Independent of
    compute_dignity()'s categorical label — meant to be used alongside it
    so e.g. Sun at 0.5 deg Aries (just past debilitation-exit) doesn't get
    the full EXALTED multiplier that Sun at 10 deg Aries earns.
    """
    exalt_sign = _EXALT_SIGN.get(planet)
    debil_sign = _DEBIL_SIGN.get(planet)
    peak_deg = _EXALT_DEGREE.get(planet)
    if peak_deg is None or exalt_sign is None or debil_sign is None:
        return 0.5

    if sign == exalt_sign:
        # 1.0 at the peak degree, tapering to 0.5 at 180 deg away (sign edges)
        dist = abs(degree - peak_deg)
        dist = min(dist, 30.0 - dist + 30.0) if dist > 30 else dist
        return max(0.5, 1.0 - (dist / 30.0) * 0.5)
    if sign == debil_sign:
        dist = abs(degree - peak_deg)
        return min(0.5, (dist / 30.0) * 0.5)
    return 0.5


_SIGN_ORDER = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
               "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]

_D9_MOVABLE_SIGNS = frozenset({"Aries", "Cancer", "Libra", "Capricorn"})
_D9_FIXED_SIGNS = frozenset({"Taurus", "Leo", "Scorpio", "Aquarius"})
_D9_DUAL_SIGNS = frozenset({"Gemini", "Virgo", "Sagittarius", "Pisces"})


def compute_d9_navamsha_sign(sign: str, degree: float) -> str:
    """Classical Navamsha (D9) sign for a single planet/point, per BPHS.
    Unlike D60/D11 elsewhere in this file, D9's construction rule is
    UNCONTESTED core Parashari doctrine, not a disputed convention -- every
    classical and modern source agrees on this rule, so no majority-vs-
    minority disclosure is needed here the way D24/D60 require one.

    Each sign is divided into 9 equal parts of 3deg20' (10/3 deg) each.
    Starting sign of the 9-part count depends on the D1 sign's modality:
      - Movable (Chara: Aries/Cancer/Libra/Capricorn) -- count starts from
        the SAME sign.
      - Fixed (Sthira: Taurus/Leo/Scorpio/Aquarius) -- count starts from
        the 9th sign FROM that sign.
      - Dual (Dwiswabhava: Gemini/Virgo/Sagittarius/Pisces) -- count starts
        from the 5th sign FROM that sign.
    The navamsa segment index (0-8) within the 30deg sign then advances
    that starting sign by the same number of signs (cycling the zodiac,
    same modulo-12 pattern as compute_d10_sign/compute_d24_sign/
    compute_d60_shashtiamsha_sign elsewhere in this file).

    GAP-FIX (2026-08-01, real gap found via a production WARNING: "D9 sign
    is required for classical Saptavargaja Bala" -- jyotish/shadbala.py's
    compute_classical_saptavargaja_bala() raises when a planet has no
    resolvable D9 sign, which previously happened for ANY chart whose
    upstream JSON didn't populate div_charts.D9_navamsha, silently
    disabling the entire six-fold Shadbala computation for that chart, not
    just the Saptavargaja Bala component. There was no in-house D9
    fallback anywhere in this codebase before this function -- D9 was the
    single most consequential divisional chart (feeds dignity checks,
    Saptavargaja Bala, and this engine's D9/D10 confirm-deny timing tier)
    with NO independent verification or fallback path, unlike D10/D24/D60
    which all already have one."""
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(degree, 29.999999))
    segment_size = 30.0 / 9.0
    segment_index = int(deg // segment_size)  # 0..8
    sign_num = _SIGN_NUM[sign]
    if sign in _D9_MOVABLE_SIGNS:
        start_num = sign_num
    elif sign in _D9_FIXED_SIGNS:
        start_num = ((sign_num - 1 + 8) % 12) + 1  # 9th sign from itself
    else:  # dual
        start_num = ((sign_num - 1 + 4) % 12) + 1  # 5th sign from itself
    result_num = ((start_num - 1 + segment_index) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d9_navamsha_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D9 (Navamsha) chart in-house from D1 longitudes,
    mirroring compute_d10_chart()'s shape exactly: {"Lagna": {"sign": ...},
    "Sun": {"sign": ...}, ...}. Planets missing `degree` in `planets_d1`
    are skipped (caller should fall back to any upstream value for those,
    if present). See compute_d9_navamsha_sign()'s docstring -- unlike
    D60/D24, this rule carries no minority-convention caveat."""
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d9_navamsha_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d9_navamsha_sign(sign, float(degree))}
    return chart


def compute_d10_sign(sign: str, degree: float) -> str:
    """Classical Dashamsha (D10) sign for a single planet/point, per Parashara
    (BPHS Ch.6). Each sign is divided into 10 equal parts of exactly 3 deg.

    Rule (Parashari, the standard used by essentially every panchanga/software):
      - ODD sign (movable-numbered: Aries=1, Gemini=3, Leo=5, Libra=7,
        Sagittarius=9, Aquarius=11): the 10 divisions are counted starting
        FROM THE SAME SIGN.
      - EVEN sign (Taurus=2, Cancer=4, Virgo=6, Scorpio=8, Capricorn=10,
        Pisces=12): the 10 divisions are counted starting from the 9th sign
        counted inclusively from that sign (e.g. even sign Taurus -> starts
        counting from Capricorn, the 9th sign from Taurus inclusive).

    This was previously NOT implemented anywhere in the repo — D10 was read
    verbatim from an upstream JSON with no way to verify the odd/even
    boundary logic. Boundary cases (degree exactly 0, exactly 3, 29.999...,
    30) are the classic source of off-by-one segment errors and are covered
    by jyotish/tests/test_d10_construction.py.
    """
    if sign not in _SIGN_NUM:
        return ""
    # Clamp degree into [0, 30). A degree of exactly 30.0 (should not occur in
    # well-formed input, but defensively) belongs to segment 9 (the last).
    deg = max(0.0, min(degree, 29.999999))
    segment_index = int(deg // 3.0)  # 0..9

    sign_num = _SIGN_NUM[sign]
    is_odd = (sign_num % 2) == 1
    if is_odd:
        start_num = sign_num
    else:
        # 9th sign counted inclusively from `sign` == offset of +8 (0-indexed)
        start_num = ((sign_num - 1 + 8) % 12) + 1

    result_num = ((start_num - 1 + segment_index) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d10_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D10 (Dashamsha) chart in-house from D1 longitudes.

    Previously the pipeline consumed a pre-computed D10 chart from an
    upstream JSON source with no in-repo way to verify its odd/even
    sign-counting was correct — a critical audit gap since Dashamsha
    carries the largest single weight (24%) of the five field-determination
    methods. This function makes D10 construction auditable and testable.

    Returns {"Lagna": {"sign": ...}, "Sun": {"sign": ...}, ...} — a
    dict-of-dict shape. NOTE (2026-07 correction): the real upstream pyhora
    JSON at `divisional_charts["D10_dashamsha"]` is actually FLAT
    {"Lagna": "Virgo", "Sun": "Scorpio", ...} (plain sign strings per planet),
    not dict-of-dict as this docstring previously claimed — verified against
    a real chart export. The two shapes do NOT match. Callers merging this
    function's output with the raw upstream dict (as `engine_io.py` does)
    must normalize both to one shape before consuming per-planet values, or
    entries will silently mix plain strings and `{"sign": ...}` dicts and
    blow up `_SIGN_NUM.get(planet_sign)`-style lookups downstream (this is
    exactly what happened in production — see the normalization step in
    `parse_json_payload`). This function's own dict-of-dict return shape is
    pinned by `tests/test_d10_construction.py` and kept as-is; fix at the
    call site, not here.
    Planets missing `degree` in `planets_d1` are skipped (caller should fall
    back to the upstream value for those, if present).
    """
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d10_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d10_sign(sign, float(degree))}
    return chart


def compute_d11_sign(sign: str, degree: float, convention: str = "HARMONIC_11") -> str:
    """D11/Ekadasamsa sign under an explicit 11th-harmonic convention.

    D11 is outside BPHS Shodashavarga and its application is not universally
    accepted.  This implementation therefore requires/names the convention
    instead of presenting it as unique doctrine: multiply absolute sidereal
    longitude by 11 and reduce modulo 360.  Each part is 30/11 degrees.
    """
    if convention != "HARMONIC_11" or sign not in _SIGN_NUM:
        return ""
    try:
        deg = float(degree)
    except (TypeError, ValueError):
        return ""
    if not _math.isfinite(deg):
        return ""
    deg = max(0.0, min(deg, 29.999999))
    absolute = (_SIGN_NUM[sign] - 1) * 30.0 + deg
    result_index = int(((absolute * 11.0) % 360.0) // 30.0)
    return _SIGN_ORDER[result_index]


def compute_d11_chart(
    planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0,
    convention: str = "HARMONIC_11",
) -> Dict[str, str]:
    """Flat D11 chart with an explicit construction-policy marker."""
    chart: Dict[str, str] = {}
    if lagna_sign:
        chart["Lagna"] = compute_d11_sign(lagna_sign, lagna_degree, convention)
    for planet, pdata in (planets_d1 or {}).items():
        sign, degree = pdata.get("sign", ""), pdata.get("degree")
        if sign and degree is not None:
            chart[planet] = compute_d11_sign(sign, float(degree), convention)
    return chart


def compute_d60_shashtiamsha_sign(sign: str, degree: float) -> str:
    """Classical Shashtiamsha (D60) for a single planet/point, per Parashara
    (BPHS ch.6) -- the finest of the classical divisional charts, read for
    deep karmic/past-life confirmation of a promise already established
    elsewhere in the chart. Each sign is divided into 60 equal parts of
    exactly 0.5 deg.

    Rule (the majority convention used by most panchanga/Jyotish software --
    Jagannatha Hora, Parashara's Light, and most Shashtiamsha calculators
    default to this): ODD sign -- the 60 divisions are counted starting
    FROM THE SAME SIGN. EVEN sign -- counted starting from the 7th sign
    (i.e. the opposite sign). In both cases the count cycles through the
    12-sign zodiac 5 times over (60/12 = 5) -- this falls out naturally
    from the same modulo-12 arithmetic compute_d10_sign()/compute_d24_sign()
    already use, just with a smaller segment size, rather than needing any
    special-cased "cycling" logic.

    This was previously NOT implemented anywhere in the repo -- see
    business_determination/d24_d60_sign.py's own `blocked_reason":
    "D60_NOT_IMPLEMENTED_CONTESTED_CONVENTION"` disclosure, which is why
    this function exists as a deliberate, disclosed choice rather than a
    silent gap-fill.

    CAVEAT (same disclosure pattern as compute_d24_sign()/compute_d2_hora_
    sign()): D60's exact sign-assignment rule is MORE contested across
    classical/software sources than D10 or D24 -- some texts describe
    different starting-sign conventions, and Shashtiamsha traditionally
    also carries 60 named devata (deity) labels per division in addition
    to a sign, which this function does not attempt to assign at all (sign-
    level dignity only). This is the majority convention several widely-
    used software packages default to, NOT a claim of singular classical
    authority the way BPHS's own D1/D9/D10 core rules are treated. Any
    caller surfacing D60 output to a reader must carry this same caveat
    forward, not present it with D9/D10-level confidence.
    """
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(degree, 29.999999))
    segment_index = int(deg // 0.5)  # 0..59

    sign_num = _SIGN_NUM[sign]
    is_odd = (sign_num % 2) == 1
    if is_odd:
        start_num = sign_num
    else:
        # 7th sign counted inclusively from `sign` == offset of +6 (0-indexed)
        start_num = ((sign_num - 1 + 6) % 12) + 1

    result_num = ((start_num - 1 + segment_index) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d60_shashtiamsha_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D60 (Shashtiamsha) chart in-house from D1 longitudes,
    mirroring compute_d10_chart()'s shape exactly: {"Lagna": {"sign": ...},
    "Sun": {"sign": ...}, ...} -- dict-of-dict. Planets missing `degree` in
    `planets_d1` are skipped (caller should fall back to any upstream value
    for those, if present). See compute_d60_shashtiamsha_sign()'s docstring
    for the full contested-convention caveat this chart inherits."""
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d60_shashtiamsha_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d60_shashtiamsha_sign(sign, float(degree))}
    return chart


def _chara_dasha_sign_period_years(sign: str, planets_d1: Dict) -> int:
    """Mahadasha length (in years) for a single sign under Jaimini Chara
    Dasha, per the "Standard Jaimini (Parashara-compatible)" convention --
    the version most widely cited in modern Jyotish software and the one
    the user explicitly selected (2026-07-30 decision) over declining to
    implement Chara Dasha at all.

    Rule: count the signs from `sign` to the sign occupied by `sign`'s own
    lord (inclusive of both ends), counting in `sign`'s own direction --
    ODD signs (Aries/Gemini/Leo/Libra/Sagittarius/Aquarius) count FORWARD
    (zodiacal order); EVEN signs count BACKWARD. A raw count of 1 (lord
    sits in its own sign) is treated as 12, not 1 -- the standard
    exception cited alongside this rule (a sign whose lord occupies it
    gets the maximal, not minimal, period).

    This function deliberately does NOT implement any sub-school variant
    (e.g. rules for exchange/aspect-based adjustments some texts add) --
    disclosed as the plain, unmodified count-based rule only."""
    if sign not in _SIGN_NUM:
        return 0
    lord = _SIGN_LORD.get(sign)
    lord_data = (planets_d1 or {}).get(lord) if lord else None
    lord_sign = lord_data.get("sign") if isinstance(lord_data, dict) else None
    if not lord_sign or lord_sign not in _SIGN_NUM:
        return 0
    start_num = _SIGN_NUM[sign]
    end_num = _SIGN_NUM[lord_sign]
    is_odd = (start_num % 2) == 1
    if is_odd:
        count = ((end_num - start_num) % 12) + 1
    else:
        count = ((start_num - end_num) % 12) + 1
    return 12 if count == 1 else count


def compute_chara_dasha_sequence(lagna_sign: str, planets_d1: Dict) -> List[Dict[str, Any]]:
    """Build the Jaimini Chara Dasha mahadasha sequence, per the "Standard
    Jaimini (Parashara-compatible)" convention (see
    _chara_dasha_sign_period_years for the per-sign period rule).

    Sequence direction: starts at the Lagna sign; if Lagna is in an ODD
    sign, the 12 mahadashas proceed in normal zodiacal order (Aries ->
    Taurus -> ...); if Lagna is in an EVEN sign, they proceed in REVERSE
    zodiacal order. This is the standard direction rule paired with the
    standard period-length rule above.

    Returns a list of 12 dicts (one mahadasha per sign, in sequence order),
    each: {"sign": str, "years": int, "sequence_index": int (0-11)}. This
    is MAHADASHA-LEVEL ONLY -- antardasha (sub-period) subdivision is
    explicitly out of scope for this pass, the same "bounded, not the full
    system" disclosure already used for D24's one-hop-only dispositor
    chain. Caller is responsible for converting these relative year-lengths
    into absolute dates anchored to the native's birth date; this function
    is pure sign/period-length computation, no date arithmetic.

    Returns [] if lagna_sign is unrecognized or planets_d1 lacks enough
    data to resolve any sign's lord placement (i.e. every period would be
    0) -- callers should treat an empty result as NOT_IMPLEMENTED-for-this-
    chart, not a zero-length dasha."""
    if lagna_sign not in _SIGN_NUM:
        return []
    start_num = _SIGN_NUM[lagna_sign]
    is_odd = (start_num % 2) == 1
    sign_by_num = {v: k for k, v in _SIGN_NUM.items()}
    sequence: List[Dict[str, Any]] = []
    for i in range(12):
        if is_odd:
            num = ((start_num - 1 + i) % 12) + 1
        else:
            num = ((start_num - 1 - i) % 12) + 1
        sign = sign_by_num[num]
        years = _chara_dasha_sign_period_years(sign, planets_d1)
        sequence.append({"sign": sign, "years": years, "sequence_index": i})
    if all(entry["years"] == 0 for entry in sequence):
        return []
    return sequence


def compute_chara_dasha_calendar(lagna_sign: str, planets_d1: Dict, dob: date) -> List[Dict[str, Any]]:
    """Convert compute_chara_dasha_sequence()'s relative sign/year sequence
    into absolute start/end dates anchored to `dob`, mirroring the shape
    Job_Career/timeline.py::_dasha_calendar() already uses for Vimshottari
    windows ({"lord"/"sign", "start", "end", ...}) so downstream timing.py
    code can consume it with a familiar shape. Uses a flat 360-day
    Jyotish year (matching _mudda's own convention elsewhere in this
    codebase) for the year-to-days conversion -- not a calendar/Gregorian
    year -- since the whole rest of this codebase's dasha-day arithmetic
    already uses that convention (see CHANGELOG v46 disclosure).

    Returns [] if compute_chara_dasha_sequence() itself returns []
    (unresolvable chart)."""
    from datetime import timedelta
    sequence = compute_chara_dasha_sequence(lagna_sign, planets_d1)
    if not sequence:
        return []
    is_forward = (_SIGN_NUM[lagna_sign] % 2) == 1
    calendar: List[Dict[str, Any]] = []
    cursor = dob
    for entry in sequence:
        days = entry["years"] * 360
        end = cursor + timedelta(days=days)
        antardashas = compute_chara_antardasha_sequence(
            entry["sign"], entry["years"], is_forward, planets_d1, start_date=cursor,
        )
        calendar.append({
            "sign": entry["sign"],
            "years": entry["years"],
            "sequence_index": entry["sequence_index"],
            "start": cursor.isoformat(),
            "end": end.isoformat(),
            "antardashas": antardashas,
        })
        cursor = end
    return calendar


def compute_chara_antardasha_sequence(
    mahadasha_sign: str,
    mahadasha_years: float,
    is_forward: bool,
    planets_d1: Dict,
    start_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Jaimini Chara Dasha ANTARDASHA (sub-period) subdivision -- v-audit
    fix (bounded-limitation follow-up, user-directed: "tackle all bounded
    limitations"). Previously explicitly out of scope (see
    compute_chara_dasha_sequence()'s own docstring: "MAHADASHA-LEVEL ONLY").

    Declared convention (a reasonable, disclosed choice among several found
    in different Jaimini sources -- NOT the only convention, flagged here
    rather than presented as singularly authoritative): the 12 antardashas
    within a Mahadasha run in the SAME direction as the overall Mahadasha
    sequence (inherited from Lagna parity, not recomputed per-Mahadasha-
    sign), starting from the Mahadasha's own sign, and each antardasha's
    share of the Mahadasha's total duration is WEIGHTED proportionally by
    that antardasha sign's own period-length (via
    _chara_dasha_sign_period_years -- the same count-to-own-lord's-sign
    rule used at the Mahadasha level), analogous to how this codebase's
    existing Vimshottari antardasha proportional-splitting already works
    (Job_Career/timeline.py). An alternative convention some sources use
    -- a flat, unweighted 1/12 split per antardasha -- is NOT implemented
    here; this weighted version was chosen for internal consistency with
    the Mahadasha-level rule already built, not because it is more
    classically authoritative.

    Returns [] if the Mahadasha sign is unresolvable, years <= 0, or every
    antardasha sign's own period-length resolves to 0 (nothing to weight
    the split by). Each entry: {"sign", "years" (float, proportional),
    "sequence_index" (0-11)} plus "start"/"end" ISO dates if `start_date`
    is supplied (dates omitted, sign/years-only, when it is not)."""
    if mahadasha_sign not in _SIGN_NUM or mahadasha_years <= 0:
        return []
    sign_by_num = {v: k for k, v in _SIGN_NUM.items()}
    start_num = _SIGN_NUM[mahadasha_sign]
    raw: List[Tuple[str, float]] = []
    for i in range(12):
        if is_forward:
            num = ((start_num - 1 + i) % 12) + 1
        else:
            num = ((start_num - 1 - i) % 12) + 1
        sign = sign_by_num[num]
        weight = _chara_dasha_sign_period_years(sign, planets_d1)
        raw.append((sign, float(weight)))
    total_weight = sum(w for _, w in raw)
    if total_weight <= 0:
        return []
    result: List[Dict[str, Any]] = []
    cursor = start_date
    for i, (sign, weight) in enumerate(raw):
        years = mahadasha_years * weight / total_weight
        entry: Dict[str, Any] = {"sign": sign, "years": round(years, 4), "sequence_index": i}
        if cursor is not None:
            from datetime import timedelta
            end = cursor + timedelta(days=round(years * 360))
            entry["start"] = cursor.isoformat()
            entry["end"] = end.isoformat()
            cursor = end
        result.append(entry)
    return result


def compute_d24_sign(sign: str, degree: float) -> str:
    """Classical Chaturvimshamsha (D24) sign for a single planet/point, per
    BPHS Ch.7. Each sign is divided into 24 equal parts of exactly 1.25 deg.

    Rule (the majority BPHS-derived convention, matched by most panchanga/
    Jyotish software): ODD sign -- the 24 divisions are counted starting
    from Leo. EVEN sign -- counted starting from Cancer.

    GAP-FIX (2026-07-22i, audit gaps 4/5, CONFIRMED real gap): before this,
    D24 (d24_house_lords/d24_house_occupancy/d24_planet_dignities) was
    consumed VERBATIM from whatever upstream JSON supplied it, with no
    in-repo way to verify it, exactly the same blind-trust gap
    compute_d10_sign()/compute_d10_chart() above already closed for D10.
    This function is a CROSS-CHECK, not an authoritative override: it lets
    Stream_Determination/stream_scoring.py's D24 section flag
    D24_CONSTRUCTION_MISMATCH when the upstream-supplied D24 sign for a
    planet disagrees with what this in-house Parashari-standard formula
    derives from the same D1 longitude, rather than silently trusting
    upstream data that may have used a different convention, a stale
    calculation, or simply disagree with a second manually-audited source
    (the exact failure mode the audit caught on a real chart).
    CAVEAT: unlike D10 (where multiple schools agree D10 has no serious
    variant-convention dispute), a small minority of Jaimini sub-schools use
    a different D24 starting-sign rule -- this is the majority convention,
    not a claim of singular classical authority. A mismatch means "this
    formula and the upstream source disagree," not automatically "the
    upstream source is wrong."
    """
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(degree, 29.999999))
    segment_index = int(deg // 1.25)  # 0..23

    sign_num = _SIGN_NUM[sign]
    is_odd = (sign_num % 2) == 1
    start_num = 5 if is_odd else 4  # Leo (5) for odd signs, Cancer (4) for even signs

    result_num = ((start_num - 1 + segment_index) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d24_chart(planets_d1: Dict) -> Dict[str, str]:
    """Build the in-house D24 (Chaturvimshamsha) PLANET signs from D1
    longitudes, for cross-checking against an upstream-supplied D24 chart.

    Returns a FLAT {"Sun": "Scorpio", "Mercury": "Pisces", ...} dict -- no
    "Lagna" key, because unlike D10 (compute_d10_chart, which receives
    lagna_degree explicitly), no lagna_degree field is currently exposed
    anywhere on NatalPayloadV2 (confirmed: jyotish/payload.py has no such
    field) -- so the D24 LAGNA cannot be independently re-derived from
    available data at all. Callers must treat D24 Lagna as UNVERIFIABLE
    from this function, distinct from "verified matching," and should say so
    explicitly rather than silently treating an unverifiable field as
    confirmed.
    """
    chart: Dict[str, str] = {}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = compute_d24_sign(sign, float(degree))
    return chart


def compute_d2_hora_sign(sign: str, degree: float) -> str:
    """Classical Hora (D2) for a single planet/point, per Parashara (BPHS
    ch.6) -- the wealth-flow varga. Each sign is split into exactly TWO
    15-degree halves, each half assigned to one of only two possible
    Hora-signs (Leo = Sun's Hora, Cancer = Moon's Hora), NOT a finer
    N-way sign multiplication the way D9/D10/D24/D60 are (this is a
    deliberate binary split, distinct in kind from those functions).

    Rule (Parashari, the majority convention used by most panchanga/
    Jyotish software):
      - ODD sign (movable-numbered: Aries=1, Gemini=3, Leo=5, Libra=7,
        Sagittarius=9, Aquarius=11): first half (0-15 deg) = Sun's Hora
        (Leo); second half (15-30 deg) = Moon's Hora (Cancer).
      - EVEN sign (Taurus=2, Cancer=4, Virgo=6, Scorpio=8, Capricorn=10,
        Pisces=12): first half (0-15 deg) = Moon's Hora (Cancer); second
        half (15-30 deg) = Sun's Hora (Leo) -- i.e. reversed relative to
        odd signs.

    CAVEAT: like D24 (see compute_d24_sign docstring), this is the
    majority convention, not a claim of singular classical authority --
    a minority of sources compute Hora boundaries slightly differently.
    This was previously NOT implemented anywhere in the repo -- D2/Hora
    was never referenced anywhere in jyotish/ or Business_Prediction/,
    despite being a classical wealth-indicating divisional chart alongside
    D9/D10/D24/D60, which already have in-house compute_dXX_sign()
    functions following this exact naming/shape convention.
    """
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(degree, 29.999999))
    is_odd = (_SIGN_NUM[sign] % 2) == 1
    first_half = deg < 15.0
    if is_odd:
        return "Leo" if first_half else "Cancer"
    return "Cancer" if first_half else "Leo"


def compute_d2_hora_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D2 (Hora) chart in-house from D1 longitudes, mirroring
    compute_d10_chart()'s shape exactly: {"Lagna": {"sign": ...}, "Sun":
    {"sign": ...}, ...} -- dict-of-dict, each value only ever "Leo" or
    "Cancer" (see compute_d2_hora_sign). Planets missing `degree` in
    `planets_d1` are skipped (caller should fall back to any upstream
    value for those, if present)."""
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d2_hora_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d2_hora_sign(sign, float(degree))}
    return chart


def compute_d7_saptamsha_sign(sign: str, degree: float) -> str:
    """Classical Saptamsha (D7) for a single planet/point, per Parashara
    (BPHS ch.6) -- the divisional chart classically governing children/
    progeny AND, by extension, partnership/business-co-founder
    corroboration when read alongside the D1 7th house (the 7th house
    itself signifies partnerships broadly, and Saptamsha is the varga tied
    to that house's deeper significations). Each sign is divided into 7
    equal parts of 30/7 = ~4.2857 deg.

    Rule (Parashari, the majority convention used by most panchanga/
    Jyotish software):
      - ODD sign (movable-numbered: Aries=1, Gemini=3, Leo=5, Libra=7,
        Sagittarius=9, Aquarius=11): the 7 divisions are counted starting
        FROM THE SAME SIGN.
      - EVEN sign (Taurus=2, Cancer=4, Virgo=6, Scorpio=8, Capricorn=10,
        Pisces=12): the 7 divisions are counted starting from the 7th sign
        counted inclusively from that sign (e.g. even sign Taurus -> starts
        counting from Scorpio, the 7th sign from Taurus inclusive) -- i.e.
        the sign 7 houses away (offset of +6, 0-indexed).

    This was previously NOT implemented anywhere in the repo -- D7 was
    never referenced anywhere in jyotish/ or Business_Prediction/ (only
    Saptavargaja Bala in jyotish/shadbala.py/vimshopaka.py touches D7
    indirectly via a pre-supplied upstream chart, never computing D7 sign
    boundaries itself), despite D7 being a classical divisional chart
    alongside D9/D10/D24/D60/D2, which already have in-house
    compute_dXX_sign() functions following this exact naming/shape
    convention. Mirrors compute_d10_sign()/compute_d2_hora_sign() exactly.
    """
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(degree, 29.999999))
    segment_size = 30.0 / 7.0
    segment_index = int(deg // segment_size)  # 0..6

    sign_num = _SIGN_NUM[sign]
    is_odd = (sign_num % 2) == 1
    if is_odd:
        start_num = sign_num
    else:
        # 7th sign counted inclusively from `sign` == offset of +6 (0-indexed)
        start_num = ((sign_num - 1 + 6) % 12) + 1

    result_num = ((start_num - 1 + segment_index) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d7_saptamsha_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D7 (Saptamsha) chart in-house from D1 longitudes,
    mirroring compute_d10_chart()'s shape exactly: {"Lagna": {"sign": ...},
    "Sun": {"sign": ...}, ...} -- dict-of-dict. Planets missing `degree` in
    `planets_d1` are skipped (caller should fall back to any upstream value
    for those, if present)."""
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d7_saptamsha_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d7_saptamsha_sign(sign, float(degree))}
    return chart


def compute_d3_drekkana_sign(sign: str, degree: float) -> str:
    """Classical Drekkana (D3) for a single planet/point, per Parashara
    (BPHS ch.6) -- the divisional chart classically governing siblings,
    courage, and self-effort/initiative (the same significations as the D1
    3rd house, read at finer resolution). Each sign is divided into 3
    equal parts (decanates) of exactly 10 degrees each.

    Rule (Parashari, the majority convention used by most panchanga/
    Jyotish software):
      - 1st decanate (0-10 deg): same sign.
      - 2nd decanate (10-20 deg): 5th sign counted inclusively from that
        sign (offset of +4, 0-indexed).
      - 3rd decanate (20-30 deg): 9th sign counted inclusively from that
        sign (offset of +8, 0-indexed).

    This was previously NOT implemented anywhere in the repo as a
    reusable chart-position function -- jyotish/boosts.py's
    _d3_drekkana_skills_bonus() only ever consumes an upstream-supplied
    payload.d3_planet_dignities dict (itself never computed in-house
    anywhere), and business_determination/house_evidence.py's D9/D10/D2/
    D7 corroboration functions had no D3 equivalent. Mirrors
    compute_d10_sign()/compute_d2_hora_sign()/compute_d7_saptamsha_sign()
    exactly in naming/shape convention.
    """
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(degree, 29.999999))
    decanate_index = int(deg // 10.0)  # 0, 1, or 2

    sign_num = _SIGN_NUM[sign]
    # offset of +4 per decanate (0-indexed): decanate 0 -> +0 (same sign),
    # decanate 1 -> +4 (5th sign inclusive), decanate 2 -> +8 (9th sign
    # inclusive) -- the classical trikona (1st/5th/9th) progression.
    result_num = ((sign_num - 1 + 4 * decanate_index) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d3_drekkana_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D3 (Drekkana) chart in-house from D1 longitudes,
    mirroring compute_d10_chart()'s shape exactly: {"Lagna": {"sign": ...},
    "Sun": {"sign": ...}, ...} -- dict-of-dict. Planets missing `degree` in
    `planets_d1` are skipped (caller should fall back to any upstream value
    for those, if present). Like compute_d7_saptamsha_chart(), NatalPayloadV2
    has no dedicated d3_lagna_degree field, so a caller-supplied
    lagna_degree (0.0 default) is required to derive a D3 Lagna in-house;
    absent that, only planet positions are populated (no "Lagna" key),
    consistent with compute_d2_hora_chart()'s Lagna-less fallback.
    """
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d3_drekkana_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d3_drekkana_sign(sign, float(degree))}
    return chart


def compute_d4_chaturthamsha_sign(sign: str, degree: float) -> str:
    """Classical Chaturthamsha (D4) for a single planet/point, per Parashara
    (BPHS ch.6) -- the divisional chart classically governing fortune,
    fixed assets/property, and (by the extension several modern Jyotish
    authors and software packages apply, see CAVEAT below) domicile/roots.
    Each sign is divided into 4 equal parts of exactly 7.5 deg.

    Rule (Parashari, the majority convention used by most panchanga/Jyotish
    software -- e.g. Jagannatha Hora/Parashara's Light): unlike D3/D7/D10/
    D24 above (which key off odd/even sign parity), D4's starting point
    depends on the sign's MODALITY (Chara/movable, Sthira/fixed,
    Dwiswabhava/dual):
      - Movable sign (Aries/Cancer/Libra/Capricorn): the 4 parts start
        counting FROM THE SAME SIGN (offsets 0, +3, +6, +9 -- i.e. the
        kendra/quadrant signs 1st-4th-7th-10th from itself, in that order).
      - Fixed sign (Taurus/Leo/Scorpio/Aquarius): the 4 parts start
        counting from the 10th sign from itself (offsets +9, 0, +3, +6 --
        i.e. 10th-1st-4th-7th, in that order).
      - Dual sign (Gemini/Virgo/Sagittarius/Pisces): the 4 parts start
        counting from the 7th sign from itself (offsets +6, +9, 0, +3 --
        i.e. 7th-10th-1st-4th, in that order).
    All three cases always land on one of the same sign's 4 kendra
    positions (1st/4th/7th/10th from it) -- only the ORDER differs by
    modality, which is why this rule cannot be reduced to a simple odd/
    even split the way D3/D7/D10/D24 can.

    This was previously NOT implemented anywhere in the repo -- D4 was
    never referenced anywhere in jyotish/ (only Vimshopaka Bala's weight
    table in constants.py lists a D4 coefficient, explicitly never applied
    because "this pipeline only actually computes D1/D3/D9/D10/D20/D24/D30"
    per that table's own comment), despite D4 being a classical divisional
    chart alongside D2/D3/D7/D9/D10/D24/D60, which already have in-house
    compute_dXX_sign() functions following this exact naming/shape
    convention. Mirrors compute_d3_drekkana_sign()/compute_d7_saptamsha_sign()
    exactly in shape.

    CAVEAT (same disclosure pattern as compute_d24_sign()): D4's use for
    fortune/fixed-assets/property is broad classical consensus; its
    extension to "domicile/place of residence/foreign vs. domestic
    business siting" (the reading business_determination/foreign_business.py
    uses this for) is a MODERN EXTENSION some Jyotish authors and software
    make from the property/fixed-assets signification, not a universally
    agreed-upon classical reading in its own right -- disclosed wherever
    this function's output feeds into that specific business-siting
    corroboration, not presented as settled classical doctrine.
    """
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(degree, 29.999999))
    segment_index = int(deg // 7.5)  # 0..3

    sign_num = _SIGN_NUM[sign]
    modality = (sign_num - 1) % 3  # 0=movable, 1=fixed, 2=dual
    base_offset = {0: 0, 1: 9, 2: 6}[modality]
    offset = (base_offset + 3 * segment_index) % 12
    result_num = ((sign_num - 1 + offset) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d4_chaturthamsha_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D4 (Chaturthamsha) chart in-house from D1 longitudes,
    mirroring compute_d3_drekkana_chart()'s shape exactly: {"Lagna":
    {"sign": ...}, "Sun": {"sign": ...}, ...} -- dict-of-dict. Planets
    missing `degree` in `planets_d1` are skipped (caller should fall back
    to any upstream value for those, if present). Like
    compute_d3_drekkana_chart(), NatalPayloadV2 has no dedicated
    d4_lagna_degree field, so a caller-supplied lagna_degree (0.0 default)
    is required to derive a D4 Lagna in-house; absent that, only planet
    positions are populated (no "Lagna" key)."""
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d4_chaturthamsha_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d4_chaturthamsha_sign(sign, float(degree))}
    return chart


def _planet_abs_degree(sign, degree):
    return (_SIGN_NUM.get(sign, 1) - 1) * 30 + degree

def _compute_whole_sign_houses(planets_d1: Dict, lagna_sign: str) -> Dict[str, int]:
    """
    BVB Standard: Strict Whole Sign Houses (Rasi Chart).
    Replaces Bhava Chalit. 1st house is strictly the Lagna sign.
    """
    houses = {}
    if not lagna_sign: return houses
    lagna_idx = _SIGN_NUM.get(lagna_sign, 1)
    
    for p, pdata in planets_d1.items():
        sign = pdata.get("sign")
        if not sign: 
            houses[p] = 0
            continue
        p_idx = _SIGN_NUM.get(sign, 1)
        
        # Whole sign math: (Planet Sign - Lagna Sign) % 12 + 1
        house = (p_idx - lagna_idx) % 12 + 1
        houses[p] = house
        
    return houses
def _compute_jaimini_chara_dasha_lengths(planets_d1: Dict) -> Dict[str, int]:
    """Calculates Jaimini Chara Dasha sign lengths per K.N. Rao method.

    AC13 doc: Implements K.N. Rao's Scorpio exception:
      Ketu is Scorpio's Chara Dasha lord only when Ketu is placed in Scorpio;
      otherwise Mars is used. This differs from Sanjay Rath's school (always Mars).
    Length formula: for odd signs, count forward from sign to lord's sign;
      for even signs, count backward. If count == 0, length = 12 years.
    Unit test: For Saturn in Aquarius, Aquarius Chara Dasha = |Aquarius - Saturn_sign| forward.
    """
    lengths = {}
    for sign, num in _SIGN_NUM.items():
        lord = _SIGN_LORD.get(sign)
        # Scorpio/Aquarius dual-lord exception (KN Rao rule):
        #   Ketu is Scorpio's lord only when Ketu is physically in Scorpio; else Mars.
        #   Rahu is Aquarius's lord only when Rahu is physically in Aquarius; else Saturn.
        if sign == "Scorpio":
            lord = "Ketu" if planets_d1.get("Ketu", {}).get("sign") == "Scorpio" else "Mars"
        if sign == "Aquarius":
            lord = "Rahu" if planets_d1.get("Rahu", {}).get("sign") == "Aquarius" else "Saturn"

        lord_sign = planets_d1.get(lord, {}).get("sign", "Aries")
        lord_num = _SIGN_NUM.get(lord_sign, 1)

        # K.N. Rao Direct/Indirect counting: odd signs (1,3,5,7,9,11) count forward;
        # even signs (2,4,6,8,10,12) count backward. C1/C2 fix.
        if num in (1, 3, 5, 7, 9, 11):  # Odd signs → forward (lord_num - sign_num)
            diff = (lord_num - num)
        else:                            # Even signs → backward (sign_num - lord_num)
            diff = (num - lord_num)
            
        if diff < 0: diff += 12
        length = diff if diff != 0 else 12
        lengths[sign] = length
    return lengths

def _get_active_chara_dasha_sign(lagna_sign: str, current_age: float, planets_d1: Dict) -> str:
    """Returns the currently active Jaimini Chara Dasha Sign.

    AC6 fix + AC13 doc: Implements K.N. Rao's directional rule:
      - Odd signs (Aries=1, Gemini=3, Leo=5, Libra=7, Sagittarius=9, Aquarius=11):
        sequence proceeds FORWARD zodiacally from lagna sign.
      - Even signs (Taurus=2, Cancer=4, Virgo=6, Scorpio=8, Capricorn=10, Pisces=12):
        sequence proceeds BACKWARD (reverse zodiacal order) from lagna sign.
    Prior code used forward-only, giving wrong active sign for all even-sign lagnas.
    Reference: K.N. Rao, 'Ups and Downs in Career', Chapter 3 (Chara Dasha).
    Unit test: For Scorpio lagna, sequence should go Scorpio→Libra→Virgo→...
    """
    if not lagna_sign: return ""
    lengths = _compute_jaimini_chara_dasha_lengths(planets_d1)
    all_signs = list(_SIGN_NUM.keys())  # canonical zodiacal order Aries→Pisces
    start_idx = all_signs.index(lagna_sign)
    lagna_num = _SIGN_NUM.get(lagna_sign, 1)
    # AC6 fix: odd lagna → forward; even lagna → backward (K.N. Rao direction rule)
    _is_odd_lagna = (lagna_num % 2 == 1)
    if _is_odd_lagna:
        seq = [all_signs[(start_idx + i) % 12] for i in range(12)]
    else:
        seq = [all_signs[(start_idx - i) % 12] for i in range(12)]
    accumulated_age = 0.0
    for sign in seq:
        dasha_len = lengths.get(sign, 0)
        accumulated_age += dasha_len
        if current_age < accumulated_age:
            return sign
    return seq[0]  # Fallback: first sign in sequence

def get_nakshatra_from_longitude(abs_degree: float) -> str:
    nakshatras = [
        "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
        "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni",
        "Uttara Phalguni","Hasta","Chitra","Swati","Vishakha",
        "Anuradha","Jyeshtha","Mula","Purva Ashadha","Uttara Ashadha",
        "Shravana","Dhanishta","Shatabhisha","Purva Bhadrapada",
        "Uttara Bhadrapada","Revati",
    ]
    index = int(abs_degree / 13.333333333333334)
    return nakshatras[min(index, 26)]


# ===========================================================================
# GRAHA DRISHTI (PLANETARY ASPECTS) — with Drishti Bala orb weighting
# ===========================================================================
def _drishti_bala(planet_degree: float) -> float:
    """Drishti Bala strength modifier based on position within house.

    Classical Drishti Bala gives maximum aspect strength at the house midpoint
    (15° within sign) and diminishes toward the cusps (0° or 30°).
    Returns a multiplier in [0.5, 1.0].
    """
    within_house = planet_degree % 30.0
    centrality   = 1.0 - abs(within_house - 15.0) / 15.0   # 0 at cusps, 1 at midpoint
    return round(0.5 + 0.5 * centrality, 4)


def _get_planetary_aspects(planet_house: Dict[str, int]) -> Dict[str, List[int]]:
    """
    BVB Standard: Strict Whole Sign Parashari Aspects.
    A planet aspects the entire sign, regardless of degrees.
    """
    aspects = {p: [] for p in planet_house}
    for p, h in planet_house.items():
        if h == 0: continue
        # Universal 7th house aspect
        aspects[p].append((h + 6 - 1) % 12 + 1)
        # Special outer planet aspects
        if p == "Mars":
            aspects[p].extend([(h + 4 - 2) % 12 + 1, (h + 8 - 2) % 12 + 1])
        elif p == "Jupiter":
            aspects[p].extend([(h + 5 - 2) % 12 + 1, (h + 9 - 2) % 12 + 1])
        elif p in ("Rahu", "Ketu"):
            # AC12 fix: configurable Rahu/Ketu aspect convention
            # RAHU_KETU_ASPECT_MODE env var: "5th_9th" (default, KP/Parashara),
            # "7th_only" (some Jaimini scholars), "none" (strict nodes = no aspect)
            import os as _os_ac12
            _rk_mode = _os_ac12.getenv("RAHU_KETU_ASPECT_MODE", "5th_9th").lower()
            if _rk_mode == "5th_9th":
                aspects[p].extend([(h + 5 - 2) % 12 + 1, (h + 9 - 2) % 12 + 1])
            elif _rk_mode == "7th_only":
                pass  # universal 7th already added above
            # "none" → only universal 7th; strip it
            elif _rk_mode == "none":
                aspects[p] = []  # nodes cast no aspect in this mode
        elif p == "Saturn":
            aspects[p].extend([(h + 3 - 2) % 12 + 1, (h + 10 - 2) % 12 + 1])
            
    return {p: list(set(v)) for p, v in aspects.items()}


def _get_planetary_aspects_weighted(
    planet_house: Dict[str, int],
    planets_d1: Dict,
) -> Dict[str, Dict[int, float]]:
    """Drishti Bala orb-weighted aspects.

    Returns {planet: {aspected_house: strength}} where strength ∈ [0.5, 1.0].
    Strength = 1.0 at house midpoint, 0.5 at house cusp — classical Drishti Bala.
    """
    binary = _get_planetary_aspects(planet_house)
    weighted: Dict[str, Dict[int, float]] = {}
    for p, houses in binary.items():
        p_deg    = planets_d1.get(p, {}).get("degree", 15.0)
        strength = _drishti_bala(p_deg)
        weighted[p] = {h: strength for h in houses}
    return weighted


def _detect_neecha_bhanga(planet_dignities: Dict[str, str],
                           planet_house: Dict[str, int],
                           moon_house: int = 0) -> Set[str]:
    """Parashari Neecha Bhanga: dispositor/exalt-lord in kendra from Lagna OR from Moon (Chandra Lagna).
    Gap-3 fix: classical rules require both Lagna-kendra AND Moon-kendra checks.
    moon_house: the house number of Moon from Lagna (used to compute Chandra Lagna kendras).
    """
    cancelled: Set[str] = set()
    # Kendras from Moon (Chandra Lagna): houses that are 1,4,7,10 relative to Moon's house.
    if moon_house:
        _moon_kendra = frozenset(((moon_house - 1 + k) % 12 + 1) for k in (0, 3, 6, 9))
    else:
        _moon_kendra = frozenset()

    for planet, dignity in planet_dignities.items():
        if dignity != "DEBILITATED": continue
        nb = _NEECHA_BHANGA_DATA.get(planet, {})
        if not nb: continue
        sl, el = nb.get("debil_sign_lord", ""), nb.get("exalt_lord", "")
        sl_h  = planet_house.get(sl, 0)
        el_h  = planet_house.get(el, 0) if el and el != planet else 0
        # Lagna-kendra check (existing rule)
        if sl and sl_h in _KENDRA_HOUSES:
            cancelled.add(planet)
        elif el and el != planet and el_h in _KENDRA_HOUSES:
            cancelled.add(planet)
        # Audit fix (2026-08-20): this rule previously fired on house
        # geometry alone (debilitated planet in a kendra from lagna, its
        # dispositor anywhere in a kendra/trikona) with NO requirement that
        # the dispositor itself be well-placed by DIGNITY -- so a debilitated
        # planet's own dispositor could itself be weak/afflicted at that
        # kendra/trikona placement and still "rescue" the debilitation. The
        # parallel rule in dignity.py::_neecha_bhanga_cancels() (Rule 1)
        # correctly requires the dispositor to be EXALTED/OWN_SIGN/
        # MOOLATRIKONA/GREAT_FRIEND at its kendra placement before granting
        # cancellation -- tightened here to match, using planet_dignities
        # (already computed per-planet at this point) as the dispositor
        # strength check.
        elif (planet_house.get(planet, 0) in _KENDRA_HOUSES and sl_h in _KT_HOUSES
              and planet_dignities.get(sl, "") in ("EXALTED", "OWN", "MOOLATRIKONA")):
            cancelled.add(planet)
        # Chandra Lagna kendra check (Gap-3: Moon-based kendra)
        elif _moon_kendra and sl and sl_h in _moon_kendra:
            cancelled.add(planet)
        elif _moon_kendra and el and el != planet and el_h in _moon_kendra:
            cancelled.add(planet)
        # AC3 fix rule (a): exaltation lord aspects the debilitated planet
        elif el and el != planet:
            _el_aspects = set(_get_planetary_aspects({p: h for p, h in planet_house.items()}).get(el, []))
            if planet_house.get(planet, 0) in _el_aspects:
                cancelled.add(planet)

    # AC3 fix rule (b): mutual debilitation cancellation
    # If planet A is debilitated in B's exaltation sign AND B is debilitated in A's exaltation sign simultaneously
    _deb_planets = [p for p, d in planet_dignities.items() if d == 'DEBILITATED']
    for i, p1 in enumerate(_deb_planets):
        for p2 in _deb_planets[i+1:]:
            nb1 = _NEECHA_BHANGA_DATA.get(p1, {})
            nb2 = _NEECHA_BHANGA_DATA.get(p2, {})
            # Check if p1's exaltation lord is p2 AND p2's exaltation lord is p1
            if nb1.get('exalt_lord') == p2 and nb2.get('exalt_lord') == p1:
                cancelled.add(p1)
                cancelled.add(p2)
    return cancelled


def _detect_yogas(planets_d1: Dict, planet_house: Dict,
                  planet_dignities: Dict = None,
                  combust_set: Set[str] = None,
                  house_lords: Dict = None) -> List[str]:
    if planet_dignities is None: planet_dignities = {}
    if combust_set is None: combust_set = set()
    yogas: List[str] = []
    
    jup_h, ven_h, mer_h = planet_house.get("Jupiter", 0), planet_house.get("Venus", 0), planet_house.get("Mercury", 0)
    sat_h, mar_h, moon_h = planet_house.get("Saturn", 0), planet_house.get("Mars", 0), planet_house.get("Moon", 0)
    
    jup_sign = planets_d1.get("Jupiter", {}).get("sign","")
    sat_sign = planets_d1.get("Saturn", {}).get("sign","")
    sun_sign = planets_d1.get("Sun", {}).get("sign","")
    mer_sign = planets_d1.get("Mercury", {}).get("sign","")
    moon_sign = planets_d1.get("Moon", {}).get("sign","")
    ven_sign = planets_d1.get("Venus", {}).get("sign","")
    mar_sign = planets_d1.get("Mars", {}).get("sign","")

    aspects = _get_planetary_aspects(planet_house)

    if jup_h in _KT_HOUSES and ven_h in _KT_HOUSES and mer_h in _KT_HOUSES: yogas.append("Saraswati")
    if moon_sign and jup_sign and (moon_h in aspects.get("Jupiter", []) or jup_h in aspects.get("Moon", [])):
        yogas.append("GajaKesari")
        
    _sun_d1  = planets_d1.get("Sun", {})
    _mer_d1  = planets_d1.get("Mercury", {})
    _sun_abs = _planet_abs_degree(_sun_d1.get("sign","Aries"), _sun_d1.get("degree",0))
    _mer_abs = _planet_abs_degree(_mer_d1.get("sign","Aries"), _mer_d1.get("degree",0))
    _sm_diff = abs(_sun_abs - _mer_abs)
    if _sm_diff > 180: _sm_diff = 360 - _sm_diff
    
    # ASTRO-9 FIX: BudhaAditya requires same-sign conjunction (classical Parasara rule).
    # Cross-sign proximity (< 15°) is NOT sufficient — different rashis = different lords.
    if sun_sign and mer_sign and sun_sign == mer_sign:
        yogas.append("BudhaAditya")
        # Nipuna Yoga is the same Sun-Mercury conjunction doctrine under a
        # distinct classical name.  Preserve the alias explicitly so reports
        # and rule traces do not claim the corpus omitted it.
        yogas.append("Nipuna")
    
    if sat_sign and compute_dignity("Saturn", sat_sign) in ("OWN","EXALTED") and sat_h in _KENDRA_HOUSES: yogas.append("Shasha")
    if jup_sign and compute_dignity("Jupiter", jup_sign) in ("OWN","EXALTED") and jup_h in _KENDRA_HOUSES: yogas.append("Hamsa")
    if mar_sign and compute_dignity("Mars", mar_sign) in ("OWN","EXALTED") and mar_h in _KENDRA_HOUSES: yogas.append("Ruchaka")
    if mer_sign and compute_dignity("Mercury", mer_sign) in ("OWN","EXALTED") and mer_h in _KENDRA_HOUSES: yogas.append("Bhadra")
    if ven_sign and compute_dignity("Venus", ven_sign) in ("OWN","EXALTED") and ven_h in _KENDRA_HOUSES: yogas.append("Malavya")
    
    if moon_h and mar_h:
        if moon_h == mar_h or moon_h in aspects.get("Mars", []) or mar_h in aspects.get("Moon", []):
            yogas.append("ChandraMangala")
            
    checked_pairs: Set[Tuple] = set()
    for p1, pd1 in planets_d1.items():
        for p2, pd2 in planets_d1.items():
            if p1 >= p2: continue
            pair = (p1, p2)
            if pair in checked_pairs: continue
            checked_pairs.add(pair)
            s1, s2 = pd1.get("sign",""), pd2.get("sign","")
            if not s1 or not s2: continue
            # Rasi Parivartana (sign exchange)
            if s2 in _OWN_SIGN.get(p1,[]) and s1 in _OWN_SIGN.get(p2,[]):
                yogas.append(f"Parivartana_{p1}_{p2}")

    # Gap-5: Nakshatra Parivartana (KP star-lord exchange)
    # Planet A in nakshatra whose lord is Planet B, AND Planet B in nakshatra whose lord is Planet A.
    _planet_naks: Dict[str, str] = {}
    for p, pd in planets_d1.items():
        sign, deg = pd.get("sign", ""), pd.get("degree", 0)
        if sign:
            abs_deg = _planet_abs_degree(sign, deg)
            _planet_naks[p] = get_nakshatra_from_longitude(abs_deg)

    _checked_nak: Set[Tuple] = set()
    for p1, nak1 in _planet_naks.items():
        lord1 = _NAKSHATRA_LORD.get(nak1, "")
        if not lord1 or lord1 == p1: continue
        for p2, nak2 in _planet_naks.items():
            if p2 == p1: continue
            pair_n = tuple(sorted([p1, p2]))
            if pair_n in _checked_nak: continue
            lord2 = _NAKSHATRA_LORD.get(nak2, "")
            # Exchange: lord of p1's star = p2, lord of p2's star = p1
            if lord1 == p2 and lord2 == p1:
                _checked_nak.add(pair_n)
                yogas.append(f"NakParivartana_{p1}_{p2}")

    # --- BVB Fix: Amala Yoga (Spotless Career) ---
    # Benefic (Jup, Ven, strong Moon, Mercury) in the 10th from Lagna or Moon
    moon_h10 = (planet_house.get("Moon", 1) + 9 - 1) % 12 + 1
    benefics = ["Jupiter", "Venus", "Mercury"]
    for b in benefics:
        b_h = planet_house.get(b, 0)
        if b_h == 10 or b_h == moon_h10:
            if b not in combust_set: # Must not be combust to give Amala results
                yogas.append(f"Amala_{b}")

    # Vasumati Yoga: natural benefics occupying Upachaya houses (3/6/10/11)
    # from Lagna or Moon.  We require at least two qualifying benefics to avoid
    # turning a single ordinary placement into a named yoga.
    _upachaya = {3, 6, 10, 11}
    _vasumati_planets = []
    for b in benefics:
        b_h = planet_house.get(b, 0)
        if not b_h or b in combust_set:
            continue
        from_moon = ((b_h - moon_h) % 12) + 1 if moon_h else 0
        if b_h in _upachaya or from_moon in _upachaya:
            _vasumati_planets.append(b)
    if len(_vasumati_planets) >= 2:
        yogas.append("Vasumati_" + "_".join(sorted(_vasumati_planets)))

    # --- BVB Fix: Generalized Raja Yogas (Dharma-Karma Adhipati) ---
    # Conjunction of a Kendra Lord (1,4,7,10) and a Trikona Lord (1,5,9)
    if house_lords:
        kendra_lords = {house_lords.get(str(h)) for h in (1,4,7,10) if house_lords.get(str(h))}
        trikona_lords = {house_lords.get(str(h)) for h in (1,5,9) if house_lords.get(str(h))}
        
        for p1 in kendra_lords:
            for p2 in trikona_lords:
                if p1 == p2: continue # Exclude planets that own both (e.g., Yogakarakas)
                if planets_d1.get(p1, {}).get("sign") == planets_d1.get(p2, {}).get("sign"):
                    yogas.append(f"RajaYoga_{p1}_{p2}")

    # GAP FIX (2026-08-17): Dhana Yoga — classical wealth/career-support yogas
    # from 2nd-lord and 11th-lord conjunction or mutual exchange (Parivartana),
    # and either lord's conjunction with the 10th/9th lord (career+fortune
    # feeding wealth). Previously undetected anywhere in the codebase despite
    # being an explicit framework requirement (Step 8).
    if house_lords:
        dhana_lord_2 = house_lords.get("2", "")
        dhana_lord_11 = house_lords.get("11", "")
        dhana_lord_10 = house_lords.get("10", "")
        dhana_lord_9 = house_lords.get("9", "")

        def _same_sign(pa: str, pb: str) -> bool:
            if not pa or not pb or pa == pb:
                return False
            return planets_d1.get(pa, {}).get("sign") == planets_d1.get(pb, {}).get("sign")

        # 2nd-lord + 11th-lord conjunction (classic Dhana Yoga)
        if _same_sign(dhana_lord_2, dhana_lord_11):
            yogas.append(f"DhanaYoga_{dhana_lord_2}_{dhana_lord_11}")

        # 2nd-lord or 11th-lord conjunct 10th-lord (wealth reinforcing career)
        for wealth_lord in {dhana_lord_2, dhana_lord_11}:
            if _same_sign(wealth_lord, dhana_lord_10):
                yogas.append(f"DhanaYoga_{wealth_lord}_{dhana_lord_10}")
            if _same_sign(wealth_lord, dhana_lord_9):
                yogas.append(f"DhanaYoga_{wealth_lord}_{dhana_lord_9}")

        # Parivartana (mutual sign exchange) between 2nd and 11th lords: the
        # 2nd lord sits in a sign owned by the 11th lord and vice versa.
        # Reuses _SIGN_LORD already imported from .constants above.
        if dhana_lord_2 and dhana_lord_11 and dhana_lord_2 != dhana_lord_11:
            sign_2 = planets_d1.get(dhana_lord_2, {}).get("sign", "")
            sign_11 = planets_d1.get(dhana_lord_11, {}).get("sign", "")
            if (sign_2 and sign_11
                    and _SIGN_LORD.get(sign_2) == dhana_lord_11
                    and _SIGN_LORD.get(sign_11) == dhana_lord_2):
                yogas.append(f"DhanaYogaParivartana_{dhana_lord_2}_{dhana_lord_11}")

    return yogas


def _detect_planetary_war(planets_d1: Dict) -> Dict[str, str]:
    """
    Detects Planetary War (Graha Yuddha) within a 1-degree orb boundary.
    Differentiates between friendly defeats and enemy structural strikes.
    """
    # Classical Natural Relationships Map (Friends list for each planet)
    _NATURAL_FRIENDS = {
        "Mars": ["Sun", "Moon", "Jupiter"],
        "Mercury": ["Sun", "Venus"],
        "Jupiter": ["Sun", "Moon", "Mars"],
        "Venus": ["Mercury", "Saturn"],
        "Saturn": ["Mercury", "Venus"]
    }
    
    result: Dict[str, str] = {}
    p_list = [p for p in planets_d1 if p not in ("Sun", "Moon", "Rahu", "Ketu")]
    
    for i in range(len(p_list)):
        for j in range(i + 1, len(p_list)):
            p1, p2 = p_list[i], p_list[j]
            d1, d2 = planets_d1[p1], planets_d1[p2]
            deg1 = _planet_abs_degree(d1.get("sign", "Aries"), d1.get("degree", 0))
            deg2 = _planet_abs_degree(d2.get("sign", "Aries"), d2.get("degree", 0))
            
            diff = abs(deg1 - deg2)
            if diff > 180: diff = 360 - diff
            
            if diff < 1.0:
                # GAP-FIX (2026-08, astrological audit): "Venus always wins"
                # was not a real classical Graha Yuddha rule -- no attested
                # text singles Venus out for an unconditional win regardless
                # of position. The classical tiebreak (BPHS) is that the
                # planet with the LESSER celestial latitude (closer to the
                # ecliptic) wins. `planets_d1` entries carry a "latitude"
                # field elsewhere in this codebase, so use it when present;
                # fall back to the pre-existing lower-longitude tiebreak
                # only when latitude data is unavailable for either planet.
                _lat1 = d1.get("latitude")
                _lat2 = d2.get("latitude")
                if _lat1 is not None and _lat2 is not None:
                    winner, loser = (p1, p2) if abs(float(_lat1)) <= abs(float(_lat2)) else (p2, p1)
                else:
                    winner, loser = (p1, p2) if deg1 <= deg2 else (p2, p1)
                
                # Context-Aware Relationship Grading: Check if conqueror is an enemy
                is_friendly_conquest = winner in _NATURAL_FRIENDS.get(loser, [])
                
                # P3: Graded war intensity — <0.5° is severe, 0.5–1° is standard
                if diff < 0.5:
                    result[winner] = "winner_severe"
                    result[loser] = "loser_severe" if not is_friendly_conquest else "loser_friendly"
                else:
                    result[winner] = "winner"
                    result[loser] = "loser_friendly" if is_friendly_conquest else "loser_bitter"
                
    return result


def _get_nakshatra_dignity(planet: str, nakshatra: str,
                            planet_dignities: Dict[str, str]) -> float:
    base = _FAVORABLE_NAKSHATRA_BASE.get(nakshatra, 1.0)
    if base == 1.0: return 1.0
    lord = _NAKSHATRA_LORD.get(nakshatra, "")
    if not lord: return base
    lord_dig = planet_dignities.get(lord, "")
    if lord_dig == "DEBILITATED": return 1.0
    if lord_dig == "EXALTED": return min(base + 0.10, 1.35)
    if lord_dig == "OWN": return min(base + 0.05, 1.30)
    return base


def _functional_role_modifier(planet: str, house_lords: Dict[str, str], lagna_lord: str, planets_d1: Dict = None) -> float:
    """ASTRO-3, 7 & 10: Lagna Lord Exception, Node Sign Lord mapping, and Moolatrikona mixed-lordship resolution."""
    if planet == lagna_lord:
        return 1.20 
        
    if planet in ("Rahu", "Ketu") and planets_d1:
        node_sign = planets_d1.get(planet, {}).get("sign", "")
        if node_sign:
            planet = _SIGN_LORD.get(node_sign, planet)

    kendra   = sum(1 for h in ("1","4","7","10")  if house_lords.get(h) == planet)
    trikona  = sum(1 for h in ("1","5","9")       if house_lords.get(h) == planet)
    dusthana = sum(1 for h in ("6","8","12")      if house_lords.get(h) == planet)
    
    if kendra > 0 and trikona > 0: return 1.20
    if trikona > 0 and dusthana == 0: return 1.10
    if kendra > 0 and dusthana == 0: return 1.05
    
    # ── MIXED LORDSHIP: Moolatrikona Dominance (Gap 5 Fix) ───────────────────
    # If a planet rules both an auspicious house and a dusthana, resolve its functional
    # benefic/malefic status by finding exactly which house its Moolatrikona sign occupies.
    if (trikona > 0 and dusthana > 0) or (kendra > 0 and dusthana > 0):
        # 1. Deduce Lagna sign mathematically from house_lords to avoid breaking upstream signatures
        l1, l2 = house_lords.get("1"), house_lords.get("2")
        lagna_sign = ""
        if l1 == "Mars" and l2 == "Venus": lagna_sign = "Aries"
        elif l1 == "Venus" and l2 == "Mercury": lagna_sign = "Taurus"
        elif l1 == "Mercury" and l2 == "Moon": lagna_sign = "Gemini"
        elif l1 == "Moon" and l2 == "Sun": lagna_sign = "Cancer"
        elif l1 == "Sun" and l2 == "Mercury": lagna_sign = "Leo"
        elif l1 == "Mercury" and l2 == "Venus": lagna_sign = "Virgo"
        elif l1 == "Venus" and l2 == "Mars": lagna_sign = "Libra"
        elif l1 == "Mars" and l2 == "Jupiter": lagna_sign = "Scorpio"
        elif l1 == "Jupiter" and l2 == "Saturn": lagna_sign = "Sagittarius"
        elif l1 == "Saturn" and l2 == "Saturn": lagna_sign = "Capricorn"
        elif l1 == "Saturn" and l2 == "Jupiter": lagna_sign = "Aquarius"
        elif l1 == "Jupiter" and l2 == "Mars": lagna_sign = "Pisces"

        _MOOLATRIKONA_SIGN = {
            "Sun": "Leo", "Moon": "Taurus", "Mars": "Aries",
            "Mercury": "Virgo", "Jupiter": "Sagittarius",
            "Venus": "Libra", "Saturn": "Aquarius"
        }

        mt_sign = _MOOLATRIKONA_SIGN.get(planet)
        # M5 fix: log when lagna deduction fails so callers can surface the fallback.
        if not lagna_sign:
            import logging as _log
            _log.debug(
                "_functional_role_modifier: lagna deduction failed for H1=%s H2=%s "
                "(planet=%s) — using Parashari fallback (may be over-generous).",
                l1, l2, planet,
            )
        if lagna_sign and mt_sign:
            lagna_idx = _SIGN_NUM.get(lagna_sign, 1)
            mt_idx = _SIGN_NUM.get(mt_sign, 1)
            mt_house = (mt_idx - lagna_idx) % 12 + 1
            
            # Moolatrikona rules apply:
            if mt_house in (1, 5, 9):
                return 1.05  # MT is Trikona -> Retains positive functional benefic status
            elif mt_house in (1, 4, 7, 10):
                return 1.02  # MT is Kendra -> Marginally positive despite dusthana
            elif mt_house in (6, 8, 12):
                return 0.90  # MT is Dusthana -> Dusthana dominates, planet acts as functional malefic
    
    # Standard Parashari fallback if MT dominance resolution fails to trigger
    if trikona > 0 and dusthana > 0: return 1.05 
    if kendra > 0 and dusthana > 0: return 0.95  
    
    if dusthana >= 2 and kendra == 0 and trikona == 0: return 0.80
    if dusthana == 1 and kendra == 0 and trikona == 0: return 0.90
    return 1.0


def _paksha_bala(sun_moon_degrees_apart: float) -> float:
    phase = min(abs(sun_moon_degrees_apart), 360 - abs(sun_moon_degrees_apart))
    return round(0.333 + (min(phase, 180.0) / 180.0) * 0.667, 4)  # FIX-2: classical min=60/180=0.333

def _get_digbala_multiplier(planet: str, house: int) -> float:
    """ASTRO-5: Directional Strength proxy."""
    digbala_map = {"Sun": 10, "Mars": 10, "Moon": 4, "Venus": 4, "Jupiter": 1, "Mercury": 1, "Saturn": 7}
    return 1.15 if digbala_map.get(planet) == house else 1.0


def _rasi_sandhi_mod(degree: float, sign: str) -> float:
    """Avastha degrees reverse based on Even/Odd sign polarity."""
    is_even = _SIGN_NUM.get(sign, 1) % 2 == 0
    if degree < 0:  degree = 0.0
    if degree > 30: degree = 30.0
    
    # Reverse degrees for even signs (Taurus, Cancer, Virgo, etc.)
    check_deg = (30.0 - degree) if is_even else degree
    
    if check_deg < 1.0:   return 0.65  # Mrita / Sandhi
    if check_deg < 3.0:   return 0.80  # Bala
    if check_deg < 6.0:   return 0.90  # Kumara
    if check_deg >= 27.0: return 0.75  # Vriddha
    if check_deg >= 24.0: return 0.95  # Yuva tail-end
    return 1.00 # Peak Yuva



def _compute_eff_strengths(raw_shadbala: Dict, planet_dignities: Dict,
                            planet_retrograde: Dict, war_result: Dict[str, str],
                            vargottama_list: List[str], nakshatras: Dict[str, str],
                            neecha_bhanga_set: Set[str], paksha_bala_val: float,
                            house_lords: Dict[str, str], lagna_lord: str,
                            planet_house: Dict[str, int], cazimi_set: Set[str],
                            planets_d1: Dict,
                            combust_set: Set[str] = None,
                            yoga_set: Set[str] = None,
                            d9_chart: Dict = None,
                            maitri_correction: Dict[str, float] = None,
                            lagna_sign: str = "") -> Tuple[Dict[str, float], Dict[str, Dict]]:
    """Compute planet effective strengths in a single pass with Nodal Structural Patches.

    Updates (v10.1):
      PATCH-NODAL-1: Eclipse Pen (Grahana Dosha) applied if node is within 10° of Sun.
      PATCH-NODAL-2: Dispositor affliction brake dampens echo inflation; symmetric uplift
                      when the dispositor is instead strong (exalted/own-sign/war-winner).
      PATCH 3 (nakshatra-lord house placement — all planets): applies a 15% penalty if the
                      nakshatra lord is in H6/8/12, or an 8% bonus if in a kendra (H1/4/7/10).
                      This is NOT node-specific; it fires for every planet in the loop.

    §5e fix: `maitri_correction` (optional, from jyotish.engine_io -- computed
    via jyotish.dignity.panchadha_maitri_correction) is a small +/-5%
    multiplier per planet, layered on top of the base dignity modifier
    below, separate from and much smaller than the dignity swing itself --
    per spec, this must not be folded into one wide dignity table.
    """
    if combust_set is None:
        combust_set = set()
    _ALL_PLANETS = ("Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu")
    _DIGBALA_HOUSE = {"Sun":10,"Mars":10,"Moon":4,"Venus":4,"Jupiter":1,"Mercury":1,"Saturn":7}
    result: Dict[str, float] = {}
    trace:  Dict[str, Dict]  = {}

    # Pre-compute Sun absolute longitude for eclipse proximity math
    sun_data = planets_d1.get("Sun", {})
    sun_abs = _planet_abs_degree(sun_data.get("sign", "Aries"), sun_data.get("degree", 0)) if sun_data else 0.0

    for p in _ALL_PLANETS:
        min_v        = _PLANET_MIN_SHADBALA.get(p, 300.0)
        raw          = raw_shadbala.get(p, 0.0)
        actual_dig   = planet_dignities.get(p, "")
        is_retro     = planet_retrograde.get(p, False) and p not in ("Sun", "Moon", "Rahu", "Ketu")
        in_nb        = p in neecha_bhanga_set
        in_cazimi    = p in cazimi_set
        # Moon's Sun-proximity is already modelled by Paksha Bala; don't double-penalize
        # via combustion as well. H1 fix.
        in_combust   = p in combust_set and p not in cazimi_set and p not in ("Sun", "Moon", "Rahu", "Ketu")
        in_vargottama= p in vargottama_list
        war_status   = war_result.get(p, "")
        nak          = nakshatras.get(p, "")
        house        = planet_house.get(p, 0)

        # ── Dignity modifier (Retrograde Asymmetry — SHADBALA-FIX-1) ─────────
        # AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass):
        # this `dig` modifier (EXALTED=1.40 ... DEBILITATED=0.60/0.65) is layered
        # multiplicatively on top of `base` = raw_shadbala_ratio a few lines below,
        # and raw_shadbala already contains Uccha Bala (shadbala.py::compute_uccha_bala,
        # a 0-60 point Sthana Bala sub-limb whose whole purpose is to score
        # exaltation/debilitation by exact degree from the exaltation point).
        # So a planet's exalted/debilitated state is counted TWICE in the final
        # eff_strength: once inside raw_shadbala's own ratio, once again here.
        # This is the same class of issue already caught and fixed once in this
        # function for Moon/Paksha Bala (see "H1 fix" comment below on
        # `in_combust`) and again at the LS5 fix further down in engine.py's
        # `_base_weight` ("blended already incorporates eff_strength which embeds
        # shadbala + dignity; using blended again here double-counted strength
        # signal"). Left unchanged here pending explicit owner sign-off, since
        # removing/rescaling it changes live scores for every chart (same policy
        # as md/ENGINE_SIMPLIFICATION_2026-08-17_combustion_unify.md) -- flagging
        # for a future pass, not fixing silently.
        # Spec fix (Full Methodology Spec §5i): retrograde is a narrative
        # caveat about the TIMING/MANNER of a planet's results ("delayed,
        # unconventional, return to an earlier interest"), never a numeric
        # strength adjustment for retrogression alone. The previous behavior
        # numerically dampened a retrograde-exalted planet from the full 1.40
        # exaltation multiplier down to 1.15 -- a real, if softened, numeric
        # penalty applied purely because the planet was retrograde, which the
        # spec explicitly forbids. Retrograde-exalted now keeps the full
        # EXALTED multiplier, same as a direct-motion exalted planet; the
        # retrograde state should be surfaced only as a narrative caveat by
        # the reporting layer, not folded into this scoring multiplier.
        # Retrograde-debilitated ("vakra neecha bhanga") is a real, distinct,
        # well-attested classical dignity-cancellation yoga -- kept, not
        # removed. Audit fix (2026-08-20): the magnitude was wrong, not the
        # principle. This branch previously jumped straight to the full
        # EXALTED multiplier (1.40x) -- the SAME numeric treatment as a
        # planet genuinely exalted by sign -- for every retrograde
        # debilitated planet unconditionally, with no reference to whatever
        # structural cancellation strength actually applies. That's a
        # category error: "vakra neecha bhanga" cancels the affliction of
        # debilitation (bringing the planet back toward functional/neutral
        # strength), it does not promote the planet to genuine exaltation.
        # The codebase already has the right-sized value for exactly this
        # kind of dignity-cancellation for the direct-motion case just below
        # (_DIGNITY_MOD["NEECHA_BHANGA"] = 1.05, vs. DEBILITATED's 0.60) --
        # using that same, more conservative value here keeps the classical
        # principle (retrograde debilitation is genuinely cancelled/
        # strengthened, still true) while fixing the magnitude and removing
        # the double-inflation this caused downstream in the Vargottama
        # branch (a retrograde-debilitated-Vargottama planet no longer gets
        # scored as strongly as a genuinely exalted-Vargottama planet).
        if is_retro:
            if actual_dig == "EXALTED":
                dig, dig_note = _DIGNITY_MOD["EXALTED"], "retro: exalted stays 1.40 (no numeric retro penalty, §5i)"
            elif actual_dig == "DEBILITATED":
                dig, dig_note = _DIGNITY_MOD["NEECHA_BHANGA"], "retro vakra-neecha-bhanga: debil cancellation→1.05 (not full exaltation)"
            else:
                dig = _DIGNITY_MOD.get(actual_dig, 1.0)
                dig_note = f"retro neutral: {actual_dig or 'nil'}→{dig}"
        else:
            if actual_dig == "DEBILITATED" and in_nb:
                dig, dig_note = _DIGNITY_MOD["NEECHA_BHANGA"], "neecha bhanga applied"
            else:
                dig = _DIGNITY_MOD.get(actual_dig, 1.0)
                dig_note = f"{actual_dig or 'neutral'}→{dig}"

        # §5e: apply the small +/-5% Panchadha Maitri correction on top of
        # the base dignity modifier above (separate layer, not folded in).
        _maitri_mult = (maitri_correction or {}).get(p, 1.0)
        if _maitri_mult != 1.0:
            dig = round(dig * _maitri_mult, 6)
            dig_note = f"{dig_note}; maitri correction x{_maitri_mult}"

        # ── Cazimi boost ─────────────────────────────────────────────────────
        caz_mod = 1.30 if in_cazimi else 1.0

        # ── Combustion modifier ──────────────────────────────────────────────
        _ys = yoga_set or set()
        if in_combust and p == "Mercury" and "BudhaAditya" in _ys:
            # BudhaAditya (same-sign only) grants classical combustion immunity
            comb_mod, comb_note = 1.00, "BudhaAditya yoga: classical immunity→1.0"
        elif in_combust:
            # GAP-3 FIX: Gradient combustion — linear ease-out over outer 30% of orb.
            # A planet just inside the orb edge gets a much milder penalty than one
            # deep inside the orb, eliminating the binary scoring cliff.
            _orb      = _COMBUST_ORB.get(p, 12)
            _sun_abs  = sun_abs  # already in scope from caller
            _pdata    = planets_d1.get(p, {})
            _p_abs    = _planet_abs_degree(_pdata.get("sign","Aries"), _pdata.get("degree",0))
            _dist     = abs(_p_abs - _sun_abs)
            if _dist > 180: _dist = 360 - _dist
            # Full penalty zone: dist < 70% of orb; gradient zone: 70%–100% of orb
            _full_zone = 0.70 * _orb
            # 3-tier severity by sign dignity (2026-08-20 audit fix): a plain
            # neutral/friend/enemy combust planet (dignity "") was previously
            # lumped into the same penalty bucket as a DEBILITATED combust
            # planet, which is classically too harsh for the former and too
            # lenient for the latter. Debilitation-while-combust is the most
            # severe classical combination; mild tier is unchanged.
            if actual_dig in ("OWN", "EXALTED", "MOOLATRIKONA"):
                _full_pen, _edge_pen = 0.85, 0.92
            elif actual_dig == "DEBILITATED":
                _full_pen, _edge_pen = 0.75, 0.80
            else:
                _full_pen, _edge_pen = 0.80, 0.85
            if _dist <= _full_zone:
                comb_mod = _full_pen
            else:
                # Linear interpolation: _full_pen at _full_zone → _edge_pen at _orb
                _t = (_dist - _full_zone) / (0.30 * _orb)
                comb_mod = _full_pen + _t * (_edge_pen - _full_pen)
            comb_note = f"combust_gradient dist={_dist:.1f} orb={_orb}→{comb_mod:.3f}"
        else:
            comb_mod, comb_note = 1.0, "not combust"

        # ── Digbala ──────────────────────────────────────────────────────────
        # AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass): a
        # third instance of the same pattern as `dig` and `war_mod` above --
        # Dig Bala (directional strength by house) is one of the six classical
        # Shadbala limbs and is already summed into raw_shadbala's total by
        # shadbala.py::compute_shadbala_all() (`dig = compute_dig_bala(...)`,
        # added alongside sthana/kala/cheshta/naisargika/drik). `digbala_mod`
        # below is then applied a second time, multiplicatively, on `base` =
        # raw_shadbala_ratio in the `_mult_chain` further down. Flagged, not
        # changed -- same owner-sign-off policy as the two notes above.
        digbala_house = _DIGBALA_HOUSE.get(p, 0)
        digbala_mod   = _get_digbala_multiplier(p, house)

        # ── War modifier ─────────────────────────────────────────────────────
        # AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass):
        # like the `dig` modifier above, this `war_mod` is layered multiplicatively
        # on top of `base` = raw_shadbala_ratio, and raw_shadbala ALREADY includes
        # Graha Yuddha as a classical Shadbala sub-limb: shadbala.py::compute_kala_bala()
        # sums nathonnata + paksha + tribhaga + abda + masa + vara + hora + ayana
        # + yuddha, where `yuddha` is shadbala.py::compute_yuddha_bala_adjustment()
        # (BPHS Yuddha Bala: winner gains shashtiamsas, loser loses them). So a
        # planet's war win/loss is counted TWICE here too -- once inside
        # raw_shadbala's own Kala Bala total, once again via this war_mod
        # multiplier. Same "flag, don't silently fix" policy as the dig-modifier
        # note above -- this changes live scores for every chart with a Graha
        # Yuddha, so it needs explicit owner sign-off before removing/folding in.
        # Context-aware war status evaluation.
        # §5h fix: spec magnitudes are winner ~+5%, loser ~-10% -- these were
        # previously as severe as a 65% cut (0.35) for a loser, far beyond
        # the spec's ~-10%. Tightened toward the spec's range while keeping a
        # graduated tail for the genuinely severe (<0.5 deg) case.
        if war_status in ("winner_severe", "winner"):
            war_mod = 1.05  # M1 fix retired: spec caps winner bonus at ~+5% regardless of severity tier
        elif war_status == "loser_friendly":
            war_mod = 0.95  # Mild structural friction if defeated by a natural friend
        elif war_status == "loser_bitter":
            war_mod = 0.90  # Spec-aligned ~-10% if defeated by an enemy
        elif war_status == "loser_severe":
            war_mod = 0.85  # Graduated tail for a very close war loss (<0.5 deg)
        else:
            war_mod = 1.0

        # ── Vargottama ───────────────────────────────────────────────────────
        # H2 fix (updated for SHADBALA-FIX-1; magnitude corrected 2026-08-20):
        # use effective post-retrograde dignity, not actual_dig. Retrograde
        # debilitated has its debility cancelled (vakra neecha bhanga -- now
        # scored at the NEECHA_BHANGA modifier above, not full exaltation),
        # so it takes the strong (non-debilitated) vargottama branch rather
        # than the compounded-debilitation penalty branch. Retrograde
        # exalted is only mildly dampened (not swapped to DEBILITATED), so
        # it also keeps the strong branch rather than being misread as a
        # debilitated vargottama.
        _eff_dig_for_var = actual_dig
        if is_retro and actual_dig == "DEBILITATED":
            _eff_dig_for_var = "EXALTED"
        # §5g fix: spec bonus range is +10-15% (was +20%); 1.13 sits at the
        # midpoint. The debilitated-vargottama penalty (0.75) is outside the
        # spec's scope (spec only discusses the positive-bonus case) but is
        # kept as a documented, pre-existing classical refinement (Neecha-
        # Vargottama = compounded debilitation) rather than removed.
        if in_vargottama and _eff_dig_for_var != "DEBILITATED": var_mod = 1.13
        elif in_vargottama and _eff_dig_for_var == "DEBILITATED": var_mod = 0.75
        # A1 fix: Neecha-Vargottama (debil in both D1 and D9, same sign locked).
        # Classical: profound early obstacles with unconventional breakthroughs
        # only after sustained effort.  0.75 (was 0.85) better reflects the
        # compounded debilitation — vs. a mere neutral-sign vargottama (1.2).
        else: var_mod = 1.0

        # ── Nakshatra modifier ───────────────────────────────────────────────
        nak_mod  = _get_nakshatra_dignity(p, nak, planet_dignities)

        # ── Paksha bala (Moon only) ──────────────────────────────────────────
        pb_mod   = paksha_bala_val if p == "Moon" else 1.0

        # ── Functional role modifier ─────────────────────────────────────────
        func_mod = _functional_role_modifier(p, house_lords, lagna_lord, planets_d1)

        # ── NODAL PATCH 1: Eclipse Proximity Loop (Grahana Dosha) ───────────
        eclipse_mod = 1.0
        eclipse_note = "clear of solar eclipse boundaries"
        if p in ("Rahu", "Ketu"):
            p_data = planets_d1.get(p, {})
            if p_data:
                p_abs = _planet_abs_degree(p_data.get("sign", "Aries"), p_data.get("degree", 0))
                diff = abs(p_abs - sun_abs)
                if diff > 180: diff = 360 - diff
                if diff <= 10.0:  # Critical 10-degree eclipse orb
                    eclipse_mod = round(max(0.65, 1.0 - (10.0 - diff) * 0.035), 4)
                    eclipse_note = f"Grahana Dosha applied: proximity to Sun is {diff:.2f}°"

        # ── NODAL PATCH 2: Dispositor Affliction Validation ─────────────────
        # Nodes (Rahu/Ketu) have no dignity table of their own, so `dig` above
        # is unconditionally 1.0 for them — they get no exaltation/own-sign
        # uplift analogous to classical planets. To avoid a systematic
        # downward skew (penalty on affliction, but nothing on strength),
        # this patch is symmetric: an afflicted dispositor dampens by 0.82x
        # (18% brake) and a strong dispositor (exalted/own-sign/war-winner)
        # uplifts by 1.18x (18% boost) — equidistant from 1.0 in relative
        # terms (0.82 = 1/1.2195 vs 1.18, both ~18% off unity) so neither
        # side is arbitrarily more generous or stingy than the other. The
        # two conditions are mutually exclusive; anything else is neutral.
        dispositor_mod = 1.0
        dispositor_note = "dispositor dignity functional"
        if p in ("Rahu", "Ketu"):
            node_sign = planets_d1.get(p, {}).get("sign", "")
            disp = _SIGN_LORD.get(node_sign, "")
            if disp:
                disp_dig     = planet_dignities.get(disp, "")
                disp_comb    = disp in combust_set
                disp_loser   = "loser" in war_result.get(disp, "")
                disp_winner  = "winner" in war_result.get(disp, "")
                disp_afflicted = disp_dig == "DEBILITATED" or disp_comb or disp_loser
                disp_strong    = (not disp_afflicted) and (
                    disp_dig in ("EXALTED", "OWN") or disp_winner
                )
                if disp_afflicted:
                    dispositor_mod = 0.82  # Apply 18% damping brake to control dispositor echo
                    dispositor_note = f"Dispositor ({disp}) afflicted: structural layout weakened"
                elif disp_strong:
                    dispositor_mod = 1.18  # Symmetric 18% uplift for a strong dispositor
                    dispositor_note = f"Dispositor ({disp}) strong: structural layout reinforced"

        # ── PATCH 3 (nakshatra-lord house placement — all planets) ──────────
        nak_house_mod = 1.0
        nak_house_note = "nakshatra lord house: neutral"
        if nak:
            from .constants import _NAKSHATRA_LORD as _NL
            nak_lord = _NL.get(nak, "")
            if nak_lord:
                nak_lord_house = planet_house.get(nak_lord, 0)
                if nak_lord_house in (6, 8, 12):
                    nak_house_mod = 0.85  # 15% penalty — dusthana positioning weakens channel
                    nak_house_note = f"Nak lord {nak_lord} in H{nak_lord_house} (dusthana: -15%)"
                elif nak_lord_house in (1, 4, 7, 10):
                    nak_house_mod = 1.08  # 8% kendra bonus — angular positioning strengthens
                    nak_house_note = f"Nak lord {nak_lord} in H{nak_lord_house} (kendra: +8%)"

        # ── GAP-3 fix: Rahu/Ketu have no classical Shadbala, so `raw` above
        # (whatever raw_shadbala carries for a node) is not a meaningful base
        # for the generic dignity path. Replace the base ratio for nodes with
        # shadbala.py::estimate_node_strength's 0-1 sign+house heuristic
        # (scaled around 1.0 so it composes with the other multipliers below
        # the same way `base` does for classical planets: 0.5 -- neutral
        # heuristic strength -- maps to 1.0, i.e. no change). Combustion,
        # vargottama and graha yuddha remain excluded for nodes above (see
        # `in_combust`, `war_status` derivation and the vargottama section --
        # none apply special node handling, all default to their neutral
        # values for Rahu/Ketu since war_result/vargottama_list are never
        # populated with node entries upstream), so those exclusions are
        # preserved unchanged.
        node_note = ""
        if p in ("Rahu", "Ketu"):
            _node_data = planets_d1.get(p, {})
            _node_res  = _estimate_node_strength(p, _node_data.get("sign", ""), house)
            base = 0.5 + _node_res["strength"]  # 0-1 heuristic -> ~0.5-1.5 base range
            node_note = f"node heuristic strength={_node_res['strength']:.3f} (sign={_node_res['sign_component']}, house={_node_res['house_component']})"
        else:
            base = (raw / min_v) if min_v > 0 else 1.0

        # ── GAP-1 fix: Yogakaraka bonus/penalty ─────────────────────────────
        # AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass):
        # this is a THIRD, independently-parameterized Yogakaraka implementation
        # alongside boosts.py::_yogakaraka_bonus() (continuous additive
        # 0.04-0.16, x shadbala ratio x dignity mod 1.0-1.3, fed into a
        # specific field's gap_boost) and boosts.py::_functional_status_factor()
        # (flat 1.15x, but only applied inside _exalted_planet_domain_bonus,
        # gating a different, narrower bonus). This one is multiplicative on
        # `base` here (0.90 debilitated / 1.18-1.25 by house) and feeds
        # eff_strength, which is itself later blended into the same per-field
        # score that _yogakaraka_bonus's additive term also feeds (see
        # engine.py's LS5-fix comment near `_base_weight` for the general
        # "blended already embeds eff_strength" pattern) -- so a chart's
        # Yogakaraka fact can currently contribute through two or three of
        # these paths to the same field's final score, each with its own,
        # never-cross-checked magnitude. None of the three is wrong on its
        # own (each is individually plausible and separately tested), but
        # they were never reconciled into one canonical source the way
        # combustion partially was in md/ENGINE_SIMPLIFICATION_2026-08-17_
        # combustion_unify.md. Recommend a similar unification pass here --
        # not done in this pass, since it changes live scores and needs
        # owner sign-off first.
        # Detection reuses the existing chart-level Yogakaraka mapping
        # (boosts.py::_YOGAKARAKA_PLANET / constants.py, same table
        # boosts.py::_yogakaraka_bonus and engine.py's career accumulator
        # already key off of) rather than re-deriving kendra/trikona
        # dual-lordship from scratch. Deferred import: boosts.py imports
        # FROM astro.py at module scope, so a module-level `from .boosts
        # import ...` here would be circular.
        from .boosts import _YOGAKARAKA_PLANET as _YK_MAP
        yk_mod = 1.0
        yk_note = "not the chart's Yogakaraka"
        if _YK_MAP.get(lagna_sign, "") == p:
            if actual_dig == "DEBILITATED":
                # Mirrors boosts.py::_yogakaraka_debilitation_penalty: a
                # debilitated Yogakaraka forfeits the bonus and takes a
                # structural penalty instead of the usual +18-25% uplift.
                yk_mod = 0.90
                yk_note = f"Yogakaraka ({p}) is debilitated: penalty applied"
            else:
                # Spec: +18-25%, amplified toward the high end in upachaya
                # houses (3/6/10/11, growth-through-effort placements) and
                # tempered toward the low end in dusthana houses (6/8/12).
                # House 6 is listed in both bands by spec; upachaya is
                # checked first so it wins the overlap.
                if house in (3, 6, 10, 11):
                    yk_mod = 1.25
                elif house in (8, 12):
                    yk_mod = 1.18
                else:
                    yk_mod = 1.20
                yk_note = f"Yogakaraka ({p}) for {lagna_sign} Lagna in H{house}: +{(yk_mod - 1) * 100:.0f}%"

        # ── GAP-2 fix: Baladi Avastha (degree-band life-stage) modifier ─────
        # Reuses boosts.py::_avastha_planet_mults' per-planet multiplier
        # directly (same degree-band table _avastha_career_modifier draws
        # on for its field-level scalar) instead of recomputing the bands.
        from .boosts import _avastha_planet_mults as _avastha_mults_fn
        _avastha_mults = _avastha_mults_fn(planets_d1)
        avastha_mod = _avastha_mults.get(p, 1.0)

        # ── Final effective strength ──────────────────────────────────────────
        # Audit fix (2026-08-20, spec §10 "bound on compounded multipliers"):
        # the 14 dignity/bonus/penalty multipliers below (dig through
        # avastha_mod) are each individually bounded, but their PRODUCT
        # previously was not -- only diagnostically logged as an "outlier,
        # not clamped" (see the info-log block just below). These techniques
        # are correlated, not independent evidence (a planet that is
        # Yogakaraka AND Vargottama AND a war-winner AND digbala-strong is
        # not nine separate strengths -- several of these read the same
        # underlying placement from different angles), so an unclamped
        # product can silently drift a single planet's strength far past
        # what any individual classical technique justifies. Clamp the
        # combined bonus/penalty chain (everything multiplying `base`,
        # i.e. excluding `base` itself, which is the actual Shadbala-
        # derived strength ratio, not a bonus/penalty) to [0.35, 1.55] --
        # wide enough to preserve headroom for a genuinely exceptional
        # convergence (Yogakaraka + Vargottama + strong cross-verification
        # is real and meaningful), but tight enough that the worst-case
        # theoretical stack (independently reproduced at ~1.7-1.8x with
        # these factors' individual ranges) can never be reached in
        # practice. `eff_strength_outlier` logging below is retained
        # unchanged as an additional visibility signal on top of this cap.
        # AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass):
        # of the factors below, three (dig, digbala_mod, war_mod) score a
        # classical fact that is ALSO already inside `base` = raw_shadbala_ratio
        # (Uccha Bala, Dig Bala, and Yuddha Bala respectively are Shadbala
        # sub-limbs -- see the per-factor notes above each one). comb_mod
        # (combustion) and avastha_mod (Baladi Avastha) are NOT double-counted
        # -- neither is a Shadbala limb in BPHS (confirmed against BPHS Ch.27's
        # own six-limb definition and Kala Bala's eight sub-factors); classical
        # practice always treats combustion/Avastha as separate checks layered
        # on top of Shadbala, which is exactly what this chain does for those
        # two. yk_mod (Yogakaraka) is also not a Shadbala limb, but overlaps
        # partially with boosts.py::_yogakaraka_bonus, a separate additive
        # Yogakaraka bonus applied later in engine.py's per-field gap_boost
        # accumulator on top of whatever eff_strength (computed here) already
        # feeds into that field's blended score -- see the Yogakaraka audit
        # note in boosts.py::_yogakaraka_bonus for detail. None of this is
        # changed here; flagged for a future pass pending owner sign-off,
        # same policy as md/ENGINE_SIMPLIFICATION_2026-08-17_combustion_unify.md.
        # ATTEMPTED FIX (2026-08-22, this audit pass) -- REVERTED SAME PASS
        # after regression testing: a first version of this fix halved each
        # of dig/digbala_mod/war_mod's deviation from 1.0 (a correlation
        # discount, same pattern as boosts.py::_yogakaraka_bonus etc.) to
        # partially offset the confirmed double-count with Shadbala's Uccha/
        # Dig/Yuddha Bala sub-limbs described in the AUDIT NOTEs above. Full
        # regression testing (tests/test_career_track_regressions.py) showed
        # this produced a much larger, less predictable ranking shift than
        # intended for a "partial discount" -- including a life-science
        # category being pushed out of one chart's top-22 entirely and an
        # unrelated field topping another chart's ranking -- consistent with
        # this factor's outlier clamp (`_mult_chain_clamped` below) reacting
        # non-linearly to a flat 50% discount applied across three factors at
        # once, rather than the smaller, contained effect a single targeted
        # discount has elsewhere in this codebase. Reverted to the original,
        # undiscounted three-factor chain pending a properly-tested rescale --
        # same "flag, don't silently fix" policy the AUDIT NOTEs above already
        # called for; this remains open for a future pass.
        _mult_chain = (dig * caz_mod * comb_mod * digbala_mod * war_mod
                       * var_mod * nak_mod * pb_mod * func_mod
                       * eclipse_mod * dispositor_mod * nak_house_mod
                       * yk_mod * avastha_mod)
        _mult_chain_clamped = max(0.35, min(1.55, _mult_chain))
        eff = base * _mult_chain_clamped
        eff = max(0.05, round(eff, 4))  # floor at 0.05 (no planet is fully inert)

        # Gap-audit fix (2026-08, diagnostic-only): flag (do not clamp) when
        # 13 compounding multipliers push a planet's effective strength past
        # the informal "0-3" range the architecture docs describe. `eff`
        # above is unchanged -- this only adds visibility for outlier charts
        # (e.g. multiple retrograde/exalted/vargottama/digbala/war-winner
        # modifiers stacking on one planet) so they can be reviewed rather
        # than silently drift further than intended.
        is_outlier = eff > _EFF_STRENGTH_OUTLIER_THRESHOLD
        if is_outlier:
            _logger.info(
                "eff_strength outlier: %s eff_strength=%.4f exceeds informal "
                "0-3 range (threshold=%.1f); dignity=%s, not clamped.",
                p, eff, _EFF_STRENGTH_OUTLIER_THRESHOLD, actual_dig,
            )

        result[p] = eff
        trace[p] = {
            "base_shadbala_ratio": round(base, 4),
            "dignity_mod":         round(dig, 4),
            "cazimi_mod":          round(caz_mod, 4),
            "combustion_mod":      round(comb_mod, 4),
            "digbala_mod":         round(digbala_mod, 4),
            "war_mod":             round(war_mod, 4),
            "vargottama_mod":      round(var_mod, 4),
            "nakshatra_mod":       round(nak_mod, 4),
            "paksha_bala_mod":     round(pb_mod, 4),
            "functional_role_mod": round(func_mod, 4),
            "eclipse_mod":         round(eclipse_mod, 4),
            "dispositor_mod":      round(dispositor_mod, 4),
            "nak_house_mod":       round(nak_house_mod, 4),
            "yogakaraka_mod":      round(yk_mod, 4),
            "avastha_mod":         round(avastha_mod, 4),
            "eff_strength":        eff,
            "dignity":             actual_dig,
            # Pre-existing gap fix: output.py::_planet_trace_html reads several
            # raw/flag keys (is_retro, in_nb, cazimi, combust, vargottama, sign,
            # house, raw_shadbala, min_v, raw_ratio, nakshatra, dig_mod, dig_note,
            # war_mod, war_status, var_mod, nak_mod, paksha_bala, func_mod,
            # digbala_house, caz_mod, comb_mod, comb_note) to render the planet
            # trace table, but this dict never carried most of them (KeyError at
            # report-build time). All of these already exist as local variables
            # in this function -- just weren't threaded into the trace dict
            # until now. Purely additive: existing keys/consumers are unchanged.
            "is_retro":            bool(is_retro),
            "in_nb":               bool(in_nb),
            "cazimi":              bool(in_cazimi),
            "combust":             bool(in_combust),
            "vargottama":          bool(in_vargottama),
            "sign":                planets_d1.get(p, {}).get("sign", ""),
            "house":               house,
            "raw_shadbala":        raw,
            "min_v":               min_v,
            "raw_ratio":           round((raw / min_v) if min_v > 0 else 0.0, 4),
            "nakshatra":           nak,
            "dig_mod":             round(dig, 4),
            "dig_note":            dig_note,
            "war_mod":             round(war_mod, 4),
            "war_status":          war_status,
            "var_mod":             round(var_mod, 4),
            "nak_mod":             round(nak_mod, 4),
            "paksha_bala":         round(pb_mod, 4),
            "func_mod":            round(func_mod, 4),
            "digbala_house":       _DIGBALA_HOUSE.get(p, 0),
            "caz_mod":             round(caz_mod, 4),
            "comb_mod":            round(comb_mod, 4),
            "comb_note":           comb_note,
            # Gap-audit fix (2026-08): diagnostic-only, see comment above.
            "eff_strength_outlier": is_outlier,
            "eff_strength_outlier_threshold": _EFF_STRENGTH_OUTLIER_THRESHOLD,
            "notes": {
                "dignity":         dig_note,
                "combustion":      comb_note,
                "eclipse":         eclipse_note,
                "dispositor":      dispositor_note,
                "nak_house":       nak_house_note,
                "yogakaraka":      yk_note,
                "node_heuristic":  node_note,
            },
        }

    # ── CLI reporting: final per-planet strength table + narrative paragraph ──
    # Printed unconditionally (this codebase has no established verbose/debug
    # flag convention to gate on -- print() usage elsewhere in the pipeline,
    # e.g. engine_io.py's career-timeline error path, is likewise unconditional).
    print("\nFinal planetary strengths (eff_strength, post all §5a-§5i modifiers):")
    for _p in _ALL_PLANETS:
        print(f"  Final strength — {_p}: {result.get(_p, 0.0):.2f}")

    _strong = sorted(result, key=lambda k: -result[k])[:2]
    _weak = sorted(result, key=lambda k: result[k])[:2]
    _cazimi_here = sorted(p for p in cazimi_set if p in result)
    _combust_here = sorted(p for p in _ALL_PLANETS
                            if p in combust_set and p not in cazimi_set
                            and p not in ("Sun", "Moon", "Rahu", "Ketu"))
    _vargot_here = sorted(p for p in vargottama_list if p in result)
    _war_winners = sorted(p for p, s in war_result.items() if "winner" in (s or ""))
    _war_losers = sorted(p for p, s in war_result.items() if "loser" in (s or ""))
    from .boosts import _YOGAKARAKA_PLANET as _YK_MAP_NARR
    _yk_planet = _YK_MAP_NARR.get(lagna_sign, "") if lagna_sign else ""

    _combust_clause = (
        f"{', '.join(_combust_here)} suffered combustion (Ravi Yuti/Asta), "
        f"dimming {'its' if len(_combust_here) == 1 else 'their'} results"
        if _combust_here else "no planet was combust in this chart"
    )
    _cazimi_clause = (
        f", while {', '.join(_cazimi_here)} sat in cazimi and drew unusual strength directly from proximity to the Sun"
        if _cazimi_here else ""
    )
    _vargot_clause = (
        f" {', '.join(_vargot_here)} {'is' if len(_vargot_here) == 1 else 'are'} Vargottama, "
        f"repeating sign in D1 and D9 for added stability and force"
        if _vargot_here else " no planet was found to be Vargottama in this chart"
    )
    _war_clause = (
        f" Graha Yuddha (planetary war) was in effect, with {', '.join(_war_winners) or 'the winner'} "
        f"prevailing over {', '.join(_war_losers) or 'the loser'}"
        if (_war_winners or _war_losers) else " no Graha Yuddha (planetary war) was found among the eligible planets"
    )
    _yk_clause = (
        f" {_yk_planet} is this {lagna_sign} Lagna's Yogakaraka, ruling both a kendra and a "
        f"trikona from Lagna, and its dignity/house placement was folded into its eff_strength above"
        if _yk_planet else ""
    )
    _paragraph = (
        f"In this chart's effective-strength pass, {_combust_clause}{_cazimi_clause}, and{_vargot_clause}."
        f"{_war_clause}.{_yk_clause} Overall, {_strong[0]} emerged as the strongest placement at "
        f"{result.get(_strong[0], 0.0):.2f} while {_weak[0]} was the weakest at "
        f"{result.get(_weak[0], 0.0):.2f}, reflecting the combined pull of dignity, digbala, "
        f"nakshatra lordship, and the structural (dispositor/eclipse) patches applied above."
    )
    print(_paragraph)

    return result, trace


def _is_vargottama(planet: str, d1_sign: str, d9_chart: Dict) -> bool:
    """A planet is Vargottama if it occupies the same sign in D1 and D9."""
    d9_sign = d9_chart.get(planet, "")
    return bool(d1_sign) and d1_sign == d9_sign


def _get_active_dasha_lord(dasha_sequence: List[Dict], current_age: float) -> str:
    """Return the current Mahadasha lord based on the native's age."""
    for d in dasha_sequence:
        start = float(d.get("start_age", 0) or 0)
        end   = float(d.get("end_age",   99) or 99)
        if start <= current_age < end:
            return d.get("lord", "") or d.get("md_planet", "")
    return ""


def _detect_combust_planets(
    planets_d1: Dict,
    sun_abs: float = None,
    planet_retrograde: Dict = None,
) -> tuple:
    """Detect planets within combustion orb of the Sun (classical Diptamsha).

    Returns (combust_list, cazimi_list).  Cazimi = within 1 degree of Sun.
    Retrograde Mercury and Venus use narrower limits (12° and 8°)
    than the direct-motion limits in ``_COMBUST_ORB``.
    All other planets use fixed orbs from _COMBUST_ORB.
    """
    from .constants import _COMBUST_ORB
    # Retrograde-adjusted orbs for Mercury and Venus (Saravali / Hora Makaranda)
    # Retrograde Mercury/Venus have narrower classical combustion limits.
    _COMBUST_ORB_RETRO = {"Mercury": 12, "Venus": 8}
    if planet_retrograde is None:
        planet_retrograde = {}
    combust: List[str] = []
    cazimi: List[str]  = []
    sun_data = planets_d1.get("Sun", {})
    if not sun_data:
        return combust, cazimi
    if sun_abs is None:
        sun_abs = _planet_abs_degree(sun_data.get("sign", "Aries"), sun_data.get("degree", 0))
    for planet, orb in _COMBUST_ORB.items():
        p_data = planets_d1.get(planet, {})
        if not p_data:
            continue
        # Use narrower orb when planet is retrograde (Mercury/Venus only)
        if planet_retrograde.get(planet, False) and planet in _COMBUST_ORB_RETRO:
            orb = _COMBUST_ORB_RETRO[planet]
        p_abs = _planet_abs_degree(p_data.get("sign", "Aries"), p_data.get("degree", 0))
        diff  = abs(p_abs - sun_abs)
        if diff > 180: diff = 360 - diff
        if diff <= 1.0:
            cazimi.append(planet)
        elif diff <= orb:
            combust.append(planet)
    return combust, cazimi


def _calc_age(birth_date_str: str, current_date_str: str = "") -> float:
    """Calculate age in years from birth date string (ISO format: YYYY-MM-DD)."""
    from datetime import date
    try:
        bd = date.fromisoformat(str(birth_date_str)[:10])
        if current_date_str:
            today = date.fromisoformat(str(current_date_str)[:10])
        else:
            today = date.today()
        return round((today - bd).days / 365.25, 2)
    except Exception:
        return 0.0


def _detect_jaimini_raj_yogas(
    ak: str,
    amk: str,
    planet_house_or_d1: object,
    planet_dignities: Dict[str, str] = None,
) -> List[str]:
    """Detect Jaimini Raj Yogas based on AK/AmK positions and dignities.

    Key Jaimini Raj Yogas:
    • AK and AmK in kendra to each other → Raja Yoga
    • AK in its own sign/exaltation in Karakamsha → strong dharmic mandate
    • Exalted AmK → career raja yoga
    """
    yogas: List[str] = []
    # planet_house_or_d1 can be:
    #   (a) Dict[str,int]  — maps planet → house number  (legacy callers)
    #   (b) Dict[str,dict] — raw planets_d1              (field_methods callers)
    _ph_arg = planet_house_or_d1 or {}
    _sample = next(iter(_ph_arg.values()), None) if _ph_arg else None
    if isinstance(_sample, dict):
        # planets_d1: extract house by sign position would require lagna; fall back gracefully
        planet_house_map: Dict[str, int] = {
            p: v.get("house", 0) for p, v in _ph_arg.items() if isinstance(v, dict)
        }
    else:
        planet_house_map = _ph_arg  # type: ignore[assignment]

    ak_h  = planet_house_map.get(ak, 0)
    amk_h = planet_house_map.get(amk, 0)

    if ak_h and amk_h:
        diff = abs(ak_h - amk_h) % 12
        if diff in (0, 3, 6, 9):
            yogas.append("Jaimini_AK_AMK_Kendra_Raja_Yoga")
        if diff in (0, 4, 8):
            yogas.append("Jaimini_AK_AMK_Trikona_Dharma_Yoga")

    _digs = planet_dignities or {}
    if ak and _digs.get(ak, "") in ("EXALTED", "OWN"):
        yogas.append(f"Jaimini_Exalted_AK_{ak}")
    if amk and _digs.get(amk, "") in ("EXALTED", "OWN"):
        yogas.append(f"Jaimini_Exalted_AMK_{amk}")

    return yogas


def _compute_arudha_pada(
    house_num: int,
    lagna_sign: str,
    planets_d1: Dict,
) -> str:
    """Compute the Arudha Pada sign of a given house using classical Parashara method.

    Args:
        house_num:   House number (1-12) whose Arudha is needed.
        lagna_sign:  Lagna (Ascendant) sign name, e.g. "Aries".
        planets_d1:  D1 planet dict {planet: {"sign": ..., "degree": ...}}.

    Returns:
        The sign name of the Arudha Pada (e.g. "Gemini"), or "" on failure.

    Classical method:
    1. Find the lord of the target house (sign lord of Lagna + house_num - 1).
    2. Count houses from target house to lord's house.
    3. Count same distance from lord's house → Arudha house.
    4. If Arudha == target house or its 7th, shift by +10 signs.
    """
    from .constants import _SIGN_LORD, _SIGN_NUM
    # Signs in zodiacal order (derived from _SIGN_NUM)
    _SIGNS = sorted(_SIGN_NUM, key=_SIGN_NUM.__getitem__)

    # House sign = lagna_sign rotated by (house_num - 1)
    try:
        lagna_idx = _SIGNS.index(lagna_sign)
    except ValueError:
        return ""
    house_sign = _SIGNS[(lagna_idx + house_num - 1) % 12]
    lord = _SIGN_LORD.get(house_sign, "")
    if not lord:
        return ""

    # Find lord's house from D1 data
    lord_data = planets_d1.get(lord, {})
    lord_sign = lord_data.get("sign", "") if isinstance(lord_data, dict) else ""
    if not lord_sign:
        return ""
    try:
        lord_sign_idx = _SIGNS.index(lord_sign)
    except ValueError:
        return ""
    # House number of lord (1-based, relative to lagna)
    lord_house = (lord_sign_idx - lagna_idx) % 12 + 1

    steps  = (lord_house - house_num) % 12
    arudha_house = (lord_house + steps - 1) % 12 + 1

    # Classical correction (iterative): Arudha cannot be the house itself or its 7th.
    # Loop covers the rare second-order case where the +10 shift itself lands on
    # house_num or its 7th again (BV Raman / Parashara school).
    for _ in range(2):
        seventh = (house_num + 5) % 12 + 1
        if arudha_house == house_num:
            arudha_house = (house_num + 9) % 12 + 1
        elif arudha_house == seventh:
            arudha_house = (seventh + 9) % 12 + 1
        else:
            break

    return _SIGNS[(lagna_idx + arudha_house - 1) % 12]


def _compute_bvb_7_karakas(planets_d1: Dict) -> tuple:
    """Compute the top-2 Chara Karakas (AK and AmK) from D1 longitudes.

    Classical rule: sort the 7 planets (excluding Rahu/Ketu) by their degree
    within the sign in descending order. Highest degree = AK, next = AmK.
    Retrograde planets use (30 - degree) for the sorting — classical exception.

    METHODOLOGY DISCLOSURE (7-karaka vs 8-karaka Chara Karaka scheme):
    This engine uses the classical Sapta (7) Chara Karaka scheme — Sun, Moon,
    Mars, Mercury, Jupiter, Venus, Saturn only — which is the scheme taught by
    Parashara/BV Raman and the majority of the Jaimini tradition. Rahu is
    deliberately EXCLUDED from the karaka-degree sort.

    This is a legitimate but non-universal school choice. A minority but
    non-trivial branch of Jaimini practitioners uses the Ashtaka (8) Chara
    Karaka scheme, which includes Rahu (using its reverse/retrograde degree)
    as an eighth candidate. Because the karakas are assigned by strict
    ordinal rank of degree-within-sign, adding Rahu as an 8th candidate can
    shift which planet receives each karaka label — most consequentially,
    it can change which planet is Atmakaraka (AK) on charts where Rahu's
    effective degree would rank higher than the current AK's degree.

    Practical implication: any downstream Jaimini analysis in this engine
    (karakamsha, AK-based career signification, argala/virodhargala relative
    to karaka houses, etc.) is conditioned on the 7-karaka reading. Charts
    near this AK/Rahu-rank boundary should be flagged for cross-check against
    the 8-karaka scheme before treating the AK-derived field recommendation
    as final. No end-user-facing disclosure of this caveat currently exists
    in jyotish/report_renderer.py or jyotish/web_report.py — consider
    surfacing it there if AK-driven conclusions are presented to end users.
    """
    _KARAKA_PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")
    degrees: Dict[str, float] = {}
    for p in _KARAKA_PLANETS:
        d = planets_d1.get(p, {})
        if not d:
            continue
        deg = float(d.get("degree", 0) or 0)
        if d.get("retrograde", False):
            deg = 30.0 - deg  # retro paradox for karaka ordering
        degrees[p] = deg

    if not degrees:
        return "", ""
    sorted_p = sorted(degrees.items(), key=lambda x: -x[1])
    # AC2 fix: return all 7 karakas (AK through DK)
    # GAP-FIX (2026-08, astrological audit): the classical Sapta (7) Chara
    # Karaka scheme this function documents itself as using has exactly
    # SEVEN names -- Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka,
    # Putrakaraka, Gnatikaraka, Darakaraka -- but this list had EIGHT
    # entries (Putrakaraka duplicated/typo'd as both "PiK" and "PuK"),
    # so zipping it against the 7 sorted planets consumed
    # AK,AmK,BK,MK,PiK,PuK,GK for all 7 planets and "DK" (index 7) was
    # never reached -- the lowest-degree planet (classically Darakaraka,
    # the spouse significator) was mislabeled "GK" (Gnatikaraka) instead,
    # and no planet was ever assigned to "DK" at all. Corrected to the
    # standard 7-name list.
    _KARAKA_NAMES = ["AK", "AmK", "BK", "MK", "PK", "GK", "DK"]
    all_karakas = {_KARAKA_NAMES[i]: p for i, (p, _) in enumerate(sorted_p) if i < len(_KARAKA_NAMES)}
    ak  = all_karakas.get("AK", "")
    amk = all_karakas.get("AmK", "")
    # Store full karaka dict as module-level for callers that need it
    _compute_bvb_7_karakas._last_all_karakas = all_karakas
    return ak, amk


def _compute_jaimini_argala(reference_house: int, planet_house: Dict[str, int]) -> List[str]:
    """Compute Argala (interference/support) planets for a reference house.

    Argala houses: 2nd, 4th, 11th from reference -> support.
    Obstruction: 12th, 10th, 3rd from reference -> virodha argala.
    Returns list of planets causing argala.
    """
    argala: List[str] = []
    _ARGALA_OFFSETS = frozenset({1, 3, 10, 4})  # 2nd, 4th, 11th, and minor-school 5th from reference (0-indexed offset)
    for planet, house in planet_house.items():
        if house:
            offset = (house - reference_house) % 12
            if offset in _ARGALA_OFFSETS:
                argala.append(planet)
    return argala


# Argala offset (0-indexed, from reference) -> Virodhargala (obstruction) offset.
# Classical rule: argala from the 2nd is countered by planets in the 12th (offset 11),
# argala from the 4th is countered by planets in the 10th (offset 9),
# argala from the 11th is countered by planets in the 3rd (offset 2).
# A minor school also obstructs the 5th-house argala from the 9th (offset 8);
# included here since jaimini.py's docstring already names 5th-house argala as
# part of the raw computation window used elsewhere.
_VIRODHARGALA_MAP: Dict[int, int] = {
    1: 11,   # 2nd house argala <- obstructed by 12th house occupants
    3: 9,    # 4th house argala <- obstructed by 10th house occupants
    10: 2,   # 11th house argala <- obstructed by 3rd house occupants
    4: 8,    # 5th house argala <- obstructed by 9th house occupants (minor school)
}


def _compute_jaimini_virodhargala(reference_house: int, planet_house: Dict[str, int]) -> List[str]:
    """Compute Argala planets that SURVIVE Virodhargala (obstruction) cancellation.

    Classical rule: argala raised from a given house is cancelled when the
    corresponding obstruction house holds an equal or greater number of
    planets. This function groups raw argala planets by their argala offset,
    counts planets in the paired obstruction house, and drops any argala
    group whose count is cancelled out.

    Returns the filtered list of planets whose argala is NOT cancelled.
    """
    groups: Dict[int, List[str]] = {}
    for planet, house in planet_house.items():
        if house:
            offset = (house - reference_house) % 12
            if offset in _VIRODHARGALA_MAP:
                groups.setdefault(offset, []).append(planet)

    surviving: List[str] = []
    for offset, planets in groups.items():
        obstruct_offset = _VIRODHARGALA_MAP[offset]
        obstructors = [
            p for p, h in planet_house.items()
            if h and (h - reference_house) % 12 == obstruct_offset
        ]
        if len(obstructors) >= len(planets):
            # Virodhargala cancels this argala group entirely.
            continue
        surviving.extend(planets)
    return surviving
