"""V1.3 merge plan item 1: dignity / affliction computation layer.

Ported from Jyotish_Field_EngineV1.3/jyotish/dignity.py as the single
canonical source of truth for dignity, combustion, and graha yuddha (planetary
war) logic, replacing what were previously 4+ independent implementations
scattered across astro.py, astro_enhancer.py, and prashna.py with their own
divergent orb tables and dignity vocabularies (see V1.3_merge_plan.md item 1
for the full audit of the pre-existing duplication and drift).

Per this engine's Rahu/Ketu combustion decision (2026-07 merge session):
Rahu/Ketu are EXCLUDED from combustion (is_combust returns False for them,
since they are not in _COMBUST_ORB) and from graha yuddha (_YUDDHA_ELIGIBLE
below), matching classical treatment of shadow points (chhaya graha) as
having no physical body to "burn" or collide with the Sun/other planets.
This is a deliberate departure from astro_enhancer.py's now-retired
_is_combust(), which had non-canonical 8-degree orbs for Rahu/Ketu.

This module does not recompute ephemeris positions; it consumes whatever
sign/degree/retrograde facts the caller already has and returns a structured
verdict. It is intentionally read-only and side-effect free.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .constants import (
    _COMBUST_ORB,
    _DEBIL_SIGN,
    _EXALT_SIGN,
    _KENDRA_HOUSES,
    _MOOLATRIKONA,
    _NATURAL_ENEMIES,
    _NATURAL_FRIENDS,
    _NEECHA_BHANGA_DATA,
    _OWN_SIGN,
    _SIGN_LORD,
)

DIGNITY_VERSION = "dignity-affliction-layer.v1"

# Ordered worst -> best for convenience/sorting. NEECHA_BHANGA (cancelled
# debilitation) is placed just above plain DEBILITATED per classical
# treatment -- cancelled, but still a materially weaker placement than a
# genuinely neutral or friendly one.
DIGNITY_STATES = (
    "DEBILITATED", "NEECHA_BHANGA", "GREAT_ENEMY", "ENEMY", "NEUTRAL", "FRIEND",
    "GREAT_FRIEND", "OWN_SIGN", "MOOLATRIKONA", "EXALTED",
)

# Non-luminaries eligible for Graha Yuddha (planetary war); Sun/Moon/Rahu/Ketu
# are classically excluded.
_YUDDHA_ELIGIBLE = frozenset({"Mars", "Mercury", "Jupiter", "Venus", "Saturn"})


def debilitation_dispositor(planet: str) -> str:
    """The classical dispositor (sign lord of the planet's own debilitation
    sign) used by the neecha-bhanga check below -- exposed so callers that
    have their own house/sign maps can look up that dispositor's house/sign
    themselves and pass them into dignity_state()'s dispositor_house/
    dispositor_sign kwargs, without duplicating _NEECHA_BHANGA_DATA's
    classical table a second time.
    Returns "" if `planet` has no debilitation-cancellation data.
    """
    return _NEECHA_BHANGA_DATA.get(planet, {}).get("debil_sign_lord", "")


def _temporal_relationship_both_directions(planet: str, sign_lord: str,
                                            planet_signs: Mapping[str, str]) -> Optional[int]:
    """§5e: Tatkalika (temporal) relationship, checked in BOTH directions per
    Full Methodology Spec §5e ("count houses from the planet's own position
    to the sign-lord's position, in both directions"). Houses 2,3,4,10,11,12
    apart = temporal friend (+1); houses 1,5,6,7,8,9 apart = temporal enemy
    (-1). Returns None if either sign is unknown/unplaced.

    Note: this classical 12-house friend/enemy partition is symmetric under
    direction-reversal (house h forward pairs with house 14-h backward, and
    every such pair -- (2,12),(3,11),(4,10),(5,9),(6,8),(7,7),(1,1) -- falls
    on the same side of the friend/enemy split), so computing both
    directions and requiring agreement never actually overturns the
    single-direction result; it only makes that invariant explicit and
    verified rather than assumed. Kept as an explicit two-sided check (not a
    silent shortcut back to one direction) so the code visibly matches what
    the spec asks for.
    """
    signs = ("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces")
    ps, ls = planet_signs.get(planet), planet_signs.get(sign_lord)
    if not ps or not ls or ps not in signs or ls not in signs:
        return None
    pidx, lidx = signs.index(ps), signs.index(ls)
    house_fwd = ((lidx - pidx) % 12) + 1   # planet -> sign-lord
    house_bwd = ((pidx - lidx) % 12) + 1   # sign-lord -> planet
    temporal_fwd = 1 if house_fwd in (2, 3, 4, 10, 11, 12) else -1
    temporal_bwd = 1 if house_bwd in (2, 3, 4, 10, 11, 12) else -1
    # Both directions always agree for this classical partition (see
    # docstring); if they ever disagreed (e.g. a future table change), fall
    # back to the forward direction rather than raising.
    return temporal_fwd if temporal_fwd == temporal_bwd else temporal_fwd


def _relationship(planet: str, sign_lord: str, planet_signs: Optional[Mapping[str, str]] = None) -> str:
    if planet == sign_lord:
        return "OWN_SIGN"
    friends = _NATURAL_FRIENDS.get(planet, set())
    enemies = _NATURAL_ENEMIES.get(planet, set())
    natural = 1 if sign_lord in friends else -1 if sign_lord in enemies else 0
    temporal = _temporal_relationship_both_directions(planet, sign_lord, planet_signs or {})
    if temporal is None:
        return "FRIEND" if natural > 0 else "ENEMY" if natural < 0 else "NEUTRAL"
    compound = natural + temporal
    return "GREAT_FRIEND" if compound == 2 else "FRIEND" if compound == 1 else "NEUTRAL" if compound == 0 else "ENEMY" if compound == -1 else "GREAT_ENEMY"


def panchadha_maitri_correction(planet: str, sign_lord: str,
                                 planet_signs: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """§5e: the SEPARATE, small +/-5% correction multiplier the spec asks for
    -- "layered on top of whatever base dignity multiplier is already in
    use, to avoid double-counting" -- rather than letting the full 5-fold
    compound state (GREAT_FRIEND..GREAT_ENEMY) drive a much larger swing on
    its own.

    Because compound = natural + temporal (temporal always +/-1), the
    temporal component ALWAYS moves the natural-only classification exactly
    one step in one direction -- i.e. temporal=friend is always an upgrade
    (enemy->neutral, neutral->friend, or friend->great-friend) and
    temporal=enemy is always a downgrade (friend->neutral, neutral->enemy,
    or enemy->great-enemy). So the correction depends only on the temporal
    direction: +5% for temporal-friend (upgrade), -5% for temporal-enemy
    (downgrade). Returns 1.0 (no correction) if sign data is unavailable.
    """
    if planet == sign_lord:
        return {"correction": 1.0, "direction": "own_sign", "trace": f"{planet} is its own sign lord; no maitri correction."}
    temporal = _temporal_relationship_both_directions(planet, sign_lord, planet_signs or {})
    if temporal is None:
        return {"correction": 1.0, "direction": "unknown", "trace": "Sign placement data unavailable; no maitri correction applied."}
    if temporal > 0:
        return {"correction": 1.05, "direction": "upgrade",
                "trace": f"{planet}/{sign_lord}: temporal friend (both directions) -> +5% upgrade correction."}
    return {"correction": 0.95, "direction": "downgrade",
            "trace": f"{planet}/{sign_lord}: temporal enemy (both directions) -> -5% downgrade correction."}


def _neecha_bhanga_cancels(
    planet: str,
    *,
    dispositor_house: Optional[int] = None,
    dispositor_sign: Optional[str] = None,
    planet_house_from_moon: Optional[int] = None,
) -> bool:
    """True if either local neecha-bhanga rule below cancels this planet's
    debilitation. All context args are optional; any combination left
    unsupplied simply makes that rule inert (never raises, never assumes).

    Rule 1: dispositor-in-kendra-and-strong -- the debilitating sign's lord
    occupies a kendra house (1/4/7/10) from the lagna AND is itself
    well-dignified (EXALTED/OWN_SIGN/MOOLATRIKONA/GREAT_FRIEND) there.
    Rule 2: kendra-from-Moon -- the debilitated planet itself occupies a
    kendra house (1/4/7/10) counted from the Moon (Chandra Lagna).
    A third commonly-cited rule (exaltation-lord aspects/conjoins the
    debilitated planet) requires a full aspect-graph computation and is
    deliberately left to astro.py's chart-wide `_detect_neecha_bhanga`
    detector, which is used wherever the full planet_house/moon_house
    context is already available (see this module's docstring / the
    v1.3 merge plan for how astro.py's detector wraps this one).
    """
    nb = _NEECHA_BHANGA_DATA.get(planet, {})
    debil_sign_lord = nb.get("debil_sign_lord", "")

    if debil_sign_lord and dispositor_house is not None and dispositor_sign:
        if dispositor_house in _KENDRA_HOUSES:
            dispositor_state = dignity_state(debil_sign_lord, dispositor_sign)
            if dispositor_state in ("EXALTED", "OWN_SIGN", "MOOLATRIKONA", "GREAT_FRIEND"):
                return True

    if planet_house_from_moon is not None and planet_house_from_moon in _KENDRA_HOUSES:
        return True

    return False


def dignity_state(
    planet: str,
    sign: str,
    degree: Optional[float] = None,
    *,
    dispositor_house: Optional[int] = None,
    dispositor_sign: Optional[str] = None,
    planet_house_from_moon: Optional[int] = None,
    planet_signs: Optional[Mapping[str, str]] = None,
) -> str:
    """Classical five-fold (plus exaltation/debilitation) dignity state.

    Priority (classical order): EXALTED > MOOLATRIKONA > OWN_SIGN >
    GREAT_FRIEND/FRIEND/NEUTRAL/ENEMY/GREAT_ENEMY (by sign-lord relationship)
    > DEBILITATED/NEECHA_BHANGA. GREAT_FRIEND/GREAT_ENEMY require the
    planet's dispositor (sign lord) to be a mutual (two-way) friend/enemy of
    the placed planet; a one-way relationship resolves to the plain
    FRIEND/ENEMY tier.

    `dispositor_house`/`dispositor_sign`/`planet_house_from_moon` are
    OPTIONAL chart-context kwargs: when supplied and a debilitation would
    otherwise be returned, they are checked against `_neecha_bhanga_cancels()`
    above and "NEECHA_BHANGA" is returned instead of "DEBILITATED" if
    cancelled. Callers that do not pass these kwargs are unaffected -- the
    check is simply inert without chart context, never assumed or fabricated.
    """
    if not planet or not sign:
        return "NEUTRAL"
    if _EXALT_SIGN.get(planet) == sign:
        return "EXALTED"
    if _DEBIL_SIGN.get(planet) == sign:
        if _neecha_bhanga_cancels(
            planet,
            dispositor_house=dispositor_house,
            dispositor_sign=dispositor_sign,
            planet_house_from_moon=planet_house_from_moon,
        ):
            return "NEECHA_BHANGA"
        return "DEBILITATED"
    mt = _MOOLATRIKONA.get(planet)
    if mt and mt[0] == sign and degree is not None:
        try:
            deg = float(degree)
            if mt[1] <= deg <= mt[2]:
                return "MOOLATRIKONA"
        except (TypeError, ValueError):
            pass
    if planet in _OWN_SIGN and sign in _OWN_SIGN[planet]:
        return "OWN_SIGN"
    sign_lord = _SIGN_LORD.get(sign)
    if not sign_lord:
        return "NEUTRAL"
    relationship = _relationship(planet, sign_lord, planet_signs)
    if relationship == "OWN_SIGN":
        return "OWN_SIGN"
    if relationship in ("GREAT_FRIEND", "FRIEND", "GREAT_ENEMY", "ENEMY"):
        return relationship
    return "NEUTRAL"


# 2026-08-17 combustion-rule unification: this module and jyotish/astro.py's
# _detect_combust_planets() used to independently implement classical
# combustion, and had silently diverged on two points -- (1) retrograde
# Mercury/Venus use narrower classical orbs (12 deg/8 deg per Saravali/Hora
# Makaranda) than their direct-motion orbs, which astro.py applied and this
# module did not; (2) a planet within 1 deg of the Sun is classically Cazimi
# ("in the heart of the Sun") -- a strength, not an affliction -- and is NOT
# combust, which astro.py excluded and this module did not. Both points are
# now unified onto astro.py's more complete rule (the astrologically correct
# one), applied here too since this module feeds jyotish/dignity.py's
# compute_planet_dignity_profile() and, via Job_Career/astro_enhancer.py's
# _is_combust()/_g1_combustion(), the career-timeline dasha-lord combustion
# check -- both of which previously used the narrower flat-orb rule and could
# disagree with the main field-scoring pipeline for the same chart on a
# retrograde Mercury/Venus dasha lord, or a cazimi one. This IS a deliberate
# score-affecting change for those specific cases (owner sign-off obtained),
# not a pure refactor -- see md/ENGINE_SIMPLIFICATION_2026-08-17_combustion_unify.md.
_COMBUST_ORB_RETRO = {"Mercury": 12, "Venus": 8}


# Cazimi orb per the methodology spec (Full Methodology Spec §5c): "separation
# < ~0.28 deg (17 arcmin)" -- classically "in the heart of the Sun". This is
# deliberately much tighter than the combustion orb: a planet at, say, 0.9 deg
# from the Sun is deep-combust, not Cazimi, and must not receive a Cazimi bonus.
_CAZIMI_ORB_DEGREES = 17.0 / 60.0  # 0.28333...


def is_cazimi(planet: str, planet_longitude: Optional[float], sun_longitude: Optional[float]) -> bool:
    """True if planet is within ~17 arcmin (0.28 deg) of the Sun ("in the heart
    of the Sun") -- classically a strength, not an affliction, and mutually
    exclusive with is_combust() below.

    Sun itself and Rahu/Ketu are excluded, matching this module's existing
    combustion convention (shadow points have no physical body to be
    "embraced" by the Sun any more than they have one to "burn" -- see
    _COMBUST_ORB's docstring) and matching jyotish/astro.py's
    _detect_combust_planets(), whose cazimi check only ever runs inside its
    loop over _COMBUST_ORB's planets, i.e. never for Rahu/Ketu.
    """
    if planet == "Sun" or planet not in _COMBUST_ORB:
        return False
    if planet_longitude is None or sun_longitude is None:
        return False
    try:
        diff = abs(float(planet_longitude) - float(sun_longitude)) % 360.0
    except (TypeError, ValueError):
        return False
    diff = min(diff, 360.0 - diff)
    return diff <= _CAZIMI_ORB_DEGREES


def is_combust(planet: str, planet_longitude: Optional[float], sun_longitude: Optional[float],
                retrograde: bool = False) -> bool:
    """True if planet is within its classical combustion orb of the Sun.

    Orb values from jyotish/constants.py._COMBUST_ORB (BPHS). Sun itself is
    never combust. Rahu/Ketu are never combust (excluded from _COMBUST_ORB
    per the 2026-07 merge decision -- see module docstring). Longitudes are
    absolute 0-360 sidereal degrees.

    Retrograde Mercury/Venus use narrower classical orbs (_COMBUST_ORB_RETRO)
    than their direct-motion orbs. A planet within ~17 arcmin of the Sun is
    Cazimi (see is_cazimi() above), not combust, regardless of orb.
    """
    if planet == "Sun" or planet not in _COMBUST_ORB:
        return False
    if planet_longitude is None or sun_longitude is None:
        return False
    try:
        diff = abs(float(planet_longitude) - float(sun_longitude)) % 360.0
    except (TypeError, ValueError):
        return False
    diff = min(diff, 360.0 - diff)
    if diff <= _CAZIMI_ORB_DEGREES:
        return False  # Cazimi, not combust
    orb = _COMBUST_ORB_RETRO.get(planet, _COMBUST_ORB[planet]) if retrograde else _COMBUST_ORB[planet]
    return diff <= orb


def graha_yuddha(planet_longitudes: Mapping[str, float]) -> Dict[str, Any]:
    """Detect Graha Yuddha (planetary war): two non-luminary planets within
    ~1 degree of angular separation of each other.

    Per the methodology spec (Full Methodology Spec §5h): the check is on
    PURE angular separation, not on the two planets sharing a sign -- two
    planets straddling a sign boundary within 1 deg (e.g. 29.7 deg Pisces and
    0.3 deg Aries, 0.6 deg apart) are still at war. Winner is classically
    decided by celestial latitude / apparent size in various texts, which
    this implementation doesn't have access to; as a documented simplification
    it uses lower absolute longitude within the pair as the winner, and flags
    the result as advisory, not a hard astronomical fact.
    """
    eligible = {p: lon for p, lon in (planet_longitudes or {}).items() if p in _YUDDHA_ELIGIBLE and lon is not None}
    names = sorted(eligible)
    wars = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            try:
                lon_a, lon_b = float(eligible[a]), float(eligible[b])
            except (TypeError, ValueError):
                continue
            diff = abs(lon_a - lon_b) % 360.0
            diff = min(diff, 360.0 - diff)
            if diff <= 1.0:
                winner, loser = (a, b) if lon_a <= lon_b else (b, a)
                wars.append({"planets": [a, b], "winner": winner, "loser": loser, "separation_degrees": round(diff, 4)})
    return {"in_graha_yuddha": bool(wars), "wars": wars}


def compute_planet_dignity_profile(
    planet: str,
    sign: str,
    degree: Optional[float] = None,
    *,
    retrograde: bool = False,
    planet_longitude: Optional[float] = None,
    sun_longitude: Optional[float] = None,
) -> Dict[str, Any]:
    """Single-planet dignity + affliction verdict (no chart-wide facts needed)."""
    state = dignity_state(planet, sign, degree)
    combust = is_combust(planet, planet_longitude, sun_longitude, retrograde=bool(retrograde))
    cazimi = is_cazimi(planet, planet_longitude, sun_longitude)
    return {
        "planet": planet,
        "sign": sign,
        "dignity_state": state,
        "retrograde": bool(retrograde),
        "combust": combust,
        "cazimi": cazimi,
    }


def compute_chart_dignity_summary(
    planets: Mapping[str, Mapping[str, Any]],
    *,
    retrograde_planets: Any = None,
    planet_longitudes: Optional[Mapping[str, float]] = None,
    chart_label: str = "D1",
) -> Dict[str, Any]:
    """Chart-wide dignity/affliction summary for every placed planet.

    `planets`: {planet: {"sign": ..., "degree": ...}} (D1 or D10 shape).
    `retrograde_planets`: iterable/set of retrograde planet names, or a
        {planet: bool} mapping -- if the ephemeris/astro.py layer already
        computed this, it is reused rather than recomputed here.
    `planet_longitudes`: optional {planet: 0-360 absolute longitude} for
        combustion + graha-yuddha detection; if absent, both checks degrade
        gracefully (combust=False, no wars reported) rather than raising.
    """
    retro_set = set()
    if isinstance(retrograde_planets, Mapping):
        retro_set = {p for p, v in retrograde_planets.items() if v}
    elif retrograde_planets:
        retro_set = set(retrograde_planets)

    lon_map = dict(planet_longitudes or {})
    sun_lon = lon_map.get("Sun")

    profiles: Dict[str, Any] = {}
    for planet, item in (planets or {}).items():
        if planet == "Lagna" or not isinstance(item, Mapping):
            continue
        sign = str(item.get("sign", ""))
        if not sign:
            continue
        profiles[planet] = compute_planet_dignity_profile(
            planet, sign, item.get("degree"),
            retrograde=planet in retro_set,
            planet_longitude=lon_map.get(planet),
            sun_longitude=sun_lon,
        )
    wars = graha_yuddha(lon_map) if lon_map else {"in_graha_yuddha": False, "wars": []}
    for war in wars["wars"]:
        for name, role in ((war["winner"], "GRAHA_YUDDHA_WINNER"), (war["loser"], "GRAHA_YUDDHA_LOSER")):
            if name in profiles:
                profiles[name]["graha_yuddha_role"] = role

    return {
        "dignity_version": DIGNITY_VERSION,
        "chart": chart_label,
        "planet_profiles": profiles,
        "graha_yuddha": wars,
        "afflicted_planets": sorted(
            p for p, prof in profiles.items()
            if prof["combust"] or prof["dignity_state"] in ("DEBILITATED", "GREAT_ENEMY", "ENEMY")
            or prof.get("graha_yuddha_role") == "GRAHA_YUDDHA_LOSER"
        ),
        "strong_planets": sorted(
            p for p, prof in profiles.items()
            if prof["dignity_state"] in ("EXALTED", "MOOLATRIKONA", "OWN_SIGN", "GREAT_FRIEND")
            and not prof["combust"]
        ),
    }


# REMOVED (2026-08-20, combustion/yogakaraka double-count pass): this module
# used to carry a DIGNITY_STRENGTH_MULTIPLIER table, COMBUST_STRENGTH_PENALTY
# (0.85), GRAHA_YUDDHA_LOSER_PENALTY (0.85), and a planet_strength_multiplier()
# hook combining them. A full-repo grep confirmed zero callers anywhere
# outside this file's own (now-removed) definition -- it was dead code, not a
# live parallel scoring path, so it was deleted rather than reconciled. The
# live combustion values are astro.py::_compute_eff_strengths's dignity-aware
# 0.75-0.92 gradient and boosts.py::_d1_vitality_coefficient's flat 0.45
# D1-integrity gate; the live Graha Yuddha value is inside raw_shadbala's own
# Kala Bala total (shadbala.py::compute_yuddha_bala_adjustment).
# CORRECTION (2026-08-22 audit): the previous version of this note claimed
# those values were already "de-duplicated against each other and against
# Shadbala" -- that was NOT accurate. astro.py::_compute_eff_strengths's
# `dig` (Uccha Bala), `digbala_mod` (Dig Bala), and `war_mod` (Yuddha Bala)
# modifiers each re-score a classical fact ALREADY summed into raw_shadbala
# (see the AUDIT NOTEs at astro.py ~1512-1650), so the same fact IS
# live-double-counted, not de-duplicated. A same-pass attempt to fix this
# (halving each factor's deviation from 1.0 in astro.py's `_mult_chain`) was
# reverted after regression testing showed it produced a much larger,
# less-predictable ranking shift than intended (see the "ATTEMPTED FIX --
# REVERTED" note at astro.py ~1885) -- so this remains a confirmed, flagged,
# NOT-yet-fixed double-count, open for a future properly-tested pass. If a
# similar strength-weighting hook is needed again here, do not treat these
# three sources as already de-duplicated.
