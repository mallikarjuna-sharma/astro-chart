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


def _relationship(planet: str, sign_lord: str, planet_signs: Optional[Mapping[str, str]] = None) -> str:
    if planet == sign_lord:
        return "OWN_SIGN"
    friends = _NATURAL_FRIENDS.get(planet, set())
    enemies = _NATURAL_ENEMIES.get(planet, set())
    natural = 1 if sign_lord in friends else -1 if sign_lord in enemies else 0
    if not planet_signs or not planet_signs.get(planet) or not planet_signs.get(sign_lord):
        return "FRIEND" if natural > 0 else "ENEMY" if natural < 0 else "NEUTRAL"
    signs = ("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces")
    if planet_signs[planet] not in signs or planet_signs[sign_lord] not in signs:
        return "FRIEND" if natural > 0 else "ENEMY" if natural < 0 else "NEUTRAL"
    pidx, lidx = signs.index(planet_signs[planet]), signs.index(planet_signs[sign_lord])
    house = ((lidx - pidx) % 12) + 1
    temporal = 1 if house in (2,3,4,10,11,12) else -1
    compound = natural + temporal
    return "GREAT_FRIEND" if compound == 2 else "FRIEND" if compound == 1 else "NEUTRAL" if compound == 0 else "ENEMY" if compound == -1 else "GREAT_ENEMY"


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


def is_combust(planet: str, planet_longitude: Optional[float], sun_longitude: Optional[float]) -> bool:
    """True if planet is within its classical combustion orb of the Sun.

    Orb values from jyotish/constants.py._COMBUST_ORB (BPHS). Sun itself is
    never combust. Rahu/Ketu are never combust (excluded from _COMBUST_ORB
    per the 2026-07 merge decision -- see module docstring). Longitudes are
    absolute 0-360 sidereal degrees.
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
    return diff <= _COMBUST_ORB[planet]


def graha_yuddha(planet_longitudes: Mapping[str, float]) -> Dict[str, Any]:
    """Detect Graha Yuddha (planetary war): two non-luminary planets within
    ~1 degree of each other in the same sign. Winner is classically the
    planet closer to due south / with greater latitude / lower longitude in
    various texts disagree; this implementation uses the simpler and more
    commonly cited rule (lower absolute longitude within the pair wins) and
    flags the result as advisory, not a hard astronomical fact.
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
            if int(lon_a // 30) != int(lon_b // 30):
                continue  # not in the same sign
            diff = abs(lon_a - lon_b)
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
    combust = is_combust(planet, planet_longitude, sun_longitude)
    return {
        "planet": planet,
        "sign": sign,
        "dignity_state": state,
        "retrograde": bool(retrograde),
        "combust": combust,
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


# ── Strength-weighting hook for downstream scoring modules ─────────────────
DIGNITY_STRENGTH_MULTIPLIER: Dict[str, float] = {
    "EXALTED": 1.40, "MOOLATRIKONA": 1.25, "OWN_SIGN": 1.15,
    "GREAT_FRIEND": 1.08, "FRIEND": 1.03, "NEUTRAL": 1.00,
    "ENEMY": 0.90, "GREAT_ENEMY": 0.80,
    # NEECHA_BHANGA: cancelled debilitation is materially stronger than plain
    # DEBILITATED (0.65) but still not neutral/friendly -- matches the 1.05
    # multiplier already used elsewhere in this codebase for NEECHA_BHANGA.
    "NEECHA_BHANGA": 1.05,
    "DEBILITATED": 0.65,
}
COMBUST_STRENGTH_PENALTY = 0.85          # multiplicative, applied on top of dignity
GRAHA_YUDDHA_LOSER_PENALTY = 0.85        # multiplicative, applied on top of dignity


def planet_strength_multiplier(profile: Mapping[str, Any]) -> float:
    """Bounded [~0.44, 1.40] multiplier from a single planet's dignity profile.

    Intended use: downstream planetary-strength assessments multiply a
    planet's raw contribution by this factor so dignity/combustion/graha
    yuddha state is reflected without changing the caller's existing scoring
    contract when this hook is left unused.
    """
    state = str(profile.get("dignity_state", "NEUTRAL"))
    factor = DIGNITY_STRENGTH_MULTIPLIER.get(state, 1.0)
    if profile.get("combust"):
        factor *= COMBUST_STRENGTH_PENALTY
    if profile.get("graha_yuddha_role") == "GRAHA_YUDDHA_LOSER":
        factor *= GRAHA_YUDDHA_LOSER_PENALTY
    return round(factor, 6)
