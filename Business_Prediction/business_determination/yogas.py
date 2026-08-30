"""Business_Prediction/business_determination/yogas.py
========================================================
Discrete NAMED classical yoga detection layer.

Everything upstream (house_evidence.py, significators.py) already computes
house-lord strength/dignity and folds it into a single signed evidence
ledger and a 0..100 score. That is enough to say "this chart scores well
for business" but not enough to say "this chart has Raja Yoga" -- reports
and astrologers reasonably expect classical combinations to be named as
discrete, individually-citable results, not dissolved into an aggregate
number. This module is purely a PACKAGING layer: it does not introduce new
astrological primitives beyond what significators.py's `_vry_check`
already does (dusthana-lord exchange qualification) -- it reuses the same
conjunction/mutual-aspect/exchange (parivartana) tests, generalized to
house-lord pairs, to detect and NAME:

  - Parivartana Yoga   (generic reusable helper -- mutual house-lord exchange)
  - Dhana Yoga         (2nd/11th lord combination with each other or 5th/9th)
  - Raja Yoga          (kendra lord + trikona lord combination)
  - Mercury-Saturn-Rahu business combination (an explicit, informally-named
    modern trading/technology/scalable-platform combination -- NOT a
    classical BPHS yoga; already partially scored, unlabeled, inside
    operating_models.py's scalable_platform archetype)

MATURITY: same status as every other module in this package -- see
MODEL_STATUS / CALIBRATION_STATUS / MATURITY_STATEMENT in constants.py.
Detected yogas are rule-based pattern matches on the D1 chart (conjunction
= same house; mutual aspect = classical 7th-house mutual aspect, i.e.
houses six apart, the same test significators.py already uses for
Mercury+Venus; exchange = parivartana, each lord sitting in the other's
house), dignity-adjusted for confidence tier -- not a claim of unique
classical authority on cancellation/contamination conditions beyond what
is implemented.

Public API
----------
    detect_business_yogas(payload) -> List[Dict[str, Any]]
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .constants import _STRONG_DIGNITY, _record_diagnostic
from .house_evidence import _dig_name, _dig_factor, _house_lord_strength, _rich_planet_dignities, _neecha_bhanga_status
from jyotish.constants import _EXALT_SIGN as _JYOTISH_EXALT_SIGN
from jyotish.constants import _DEBIL_SIGN as _JYOTISH_DEBIL_SIGN
from jyotish.constants import _OWN_SIGN as _JYOTISH_OWN_SIGN



def _conjunction_or_mutual_aspect(
    house_a: int,
    house_b: int,
    sign_a: Optional[str] = None,
    sign_b: Optional[str] = None,
) -> Optional[str]:
    """Returns 'CONJUNCTION' if two planets/lords are genuinely conjunct,
    'MUTUAL_ASPECT' if they are in the classical mutual-7th-house
    relationship (six houses apart -- the same test significators.py's
    Mercury+Venus check uses), else None. Houses must be valid (1..12),
    0/falsy treated as unknown.

    CONJUNCTION (yuti) classically requires the two planets to share the
    same RASHI (zodiac sign), not merely the same house number. `house_a`/
    `house_b` here come from payload.planet_house, which -- per
    jyotish/engine_io.py -- defaults to the Bhava Chalit (cuspal) house
    system when the upstream provider supplies cuspal house positions,
    NOT whole-sign houses. Two planets can share a Bhava-Chalit house
    number while sitting in two different signs (a cuspal boundary
    artifact), which is not a real yuti and must not be labeled
    CONJUNCTION -- doing so previously let mutually-exclusive per-sign
    dignity tags (e.g. Mercury OWN, which requires Gemini/Virgo, and Sun
    DEBILITATED, which requires Libra) appear together on the same
    "conjunct" citation, an internal impossibility caught by a real-chart
    audit (Mallikarjun Sharma, Sagittarius lagna).

    When sign_a/sign_b are supplied (the normal case for a real chart --
    see payload.planet_signs), CONJUNCTION requires sign_a == sign_b;
    a shared house number with differing signs is treated as no relation
    at all (not a weaker/renamed relation -- BPHS does not recognize
    "same bhava, different rashi" as a yuti of any strength). When
    sign_a/sign_b are not supplied (e.g. lightweight synthetic test
    payloads that only set .planet_house), this falls back to the legacy
    house-number-equality behavior so existing tests are unaffected.
    """
    if not house_a or not house_b:
        return None
    if house_a == house_b:
        if sign_a and sign_b:
            return "CONJUNCTION" if sign_a == sign_b else None
        return "CONJUNCTION"
    if abs(house_a - house_b) == 6:
        return "MUTUAL_ASPECT"
    return None


def _dignity_implies_conflicting_sign(planet_a: str, dig_a: str, planet_b: str, dig_b: str) -> bool:
    """Safety invariant: given two planets claimed to be in CONJUNCTION
    (same sign) with the given (possibly independently-sourced) dignity
    labels, return True if those two dignity labels are mutually
    exclusive for a same-sign placement -- i.e. the sign required by
    planet_a's dignity (when it is a sign-specific one: OWN/EXALTED/
    DEBILITATED) is provably different from the sign required by
    planet_b's dignity. This should never fire when the CONJUNCTION
    relation was derived from a genuine sign_a == sign_b match; it exists
    as defense-in-depth against a future regression (stale/mismatched
    dignity lookup, wrong-planet-index bug, etc.) reproducing the exact
    class of internal inconsistency this module was audited for."""

    def _required_signs(planet: str, dig: str) -> Optional[set]:
        if dig == "EXALTED":
            s = _JYOTISH_EXALT_SIGN.get(planet)
            return {s} if s else None
        if dig == "DEBILITATED":
            s = _JYOTISH_DEBIL_SIGN.get(planet)
            return {s} if s else None
        if dig == "OWN":
            signs = _JYOTISH_OWN_SIGN.get(planet)
            return set(signs) if signs else None
        return None  # MOOLATRIKONA/NEUTRAL/friend-enemy tiers aren't single-sign-specific here

    signs_a = _required_signs(planet_a, dig_a)
    signs_b = _required_signs(planet_b, dig_b)
    if not signs_a or not signs_b:
        return False
    return signs_a.isdisjoint(signs_b)


def _parivartana_between_lords(
    payload: Any,
    house_x: int,
    house_y: int,
) -> Optional[Dict[str, Any]]:
    """Generic, reusable Parivartana (mutual sign/house exchange) check
    between the lords of two given D1 houses: true when house_x's lord sits
    in house_y AND house_y's lord sits in house_x (a genuine house swap --
    not merely two lords conjunct in the same house, mirroring the
    distinction significators.py's `_vry_check` already draws for dusthana
    lords). Returns None if no exchange, else a dict describing it.
    """
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    lord_x, lord_y = _h(house_x), _h(house_y)
    if not lord_x or not lord_y or lord_x == lord_y:
        return None
    if _ph(lord_x) == house_y and _ph(lord_y) == house_x:
        return {
            "house_x": house_x,
            "house_y": house_y,
            "lord_x": lord_x,
            "lord_y": lord_y,
            "dignity_x": _dig_name(lord_x, dignities),
            "dignity_y": _dig_name(lord_y, dignities),
        }
    return None


def _tier_from_dignities(payload: Any, *planets_and_dignities: Tuple[str, str]) -> str:
    """STRONG/MODERATE/WEAK tiering, mirroring the deterministic-threshold
    convention used elsewhere in this package (timing.py's _label_for_net
    is a deterministic threshold on a net score, not a statistical
    confidence -- same spirit here, thresholded on dignity instead).

    Astrologer-reviewed fix: a DEBILITATED planet used to force this
    yoga's tier to WEAK unconditionally, even when that debilitation is
    classically CANCELLED (Neecha Bhanga -- see house_evidence.py's
    _neecha_bhanga_status(), added for the significator ledger but never
    wired into yoga tiering). A real chart surfaced this exact gap: a
    Raja Yoga via Parivartana with a debilitated exchange partner was
    tiered WEAK, while the significator evidence for the SAME planet's
    SAME debilitation elsewhere in the same report already read it as
    cancelled and classically strengthened -- two subsystems disagreeing
    about one underlying fact. Now checks cancellation first and, if
    cancelled, treats that planet as NEUTRAL (not DEBILITATED, not
    promoted to a full _STRONG_DIGNITY credit either -- cancellation
    removes the affliction, it doesn't itself confer a fresh dignity
    upgrade) for tiering purposes only.

    Follow-up fix (same chart, still visible after the above): removing
    the forced-WEAK path is not enough on its own when the OTHER planet in
    the pair is merely NEUTRAL (not itself in _STRONG_DIGNITY) -- with
    zero "strong" dignities counted on either side, the tier fell through
    to this function's own WEAK default anyway, so the fix was
    mathematically correct but practically invisible: the same WEAK label
    came out either way, just via a different code path, with no visible
    sign the cancellation was ever considered. A cancelled debilitation is
    "no longer afflicted," which is a genuinely different, better reading
    than "never had a chance" -- it should land at MODERATE (the same
    tier a single _STRONG_DIGNITY planet gets), not silently re-collapse
    into the same WEAK bucket as an uncancelled debilitation.
    """
    debilitated = 0
    strong = 0
    cancelled = 0
    for planet, d in planets_and_dignities:
        if d in _STRONG_DIGNITY:
            strong += 1
        elif d == "DEBILITATED":
            nb = _neecha_bhanga_status(payload, planet)
            if nb.get("cancelled"):
                cancelled += 1
            else:
                debilitated += 1
    if debilitated:
        return "WEAK"
    if strong >= 2:
        return "STRONG"
    if strong == 1 or cancelled:
        return "MODERATE"
    return "WEAK"


def _dignity_display(payload: Any, planet: str, dig: str) -> str:
    """Human-readable dignity label for yoga detail/effect text -- plain
    `dig` unless it's a cancelled (Neecha Bhanga) debilitation, in which
    case it's annotated so the citation doesn't read as a flat, afflicted
    "DEBILITATED" when the engine itself already knows the debilitation is
    classically cancelled (see _tier_from_dignities' docstring -- the same
    real-chart gap: significators.py's evidence ledger celebrated this
    exact cancellation elsewhere in the same report while this module's
    yoga citation said nothing about it)."""
    if dig != "DEBILITATED":
        return dig
    nb = _neecha_bhanga_status(payload, planet)
    if nb.get("cancelled"):
        return "DEBILITATED, but Neecha Bhanga cancels this"
    return dig


def _yoga_record(
    name: str,
    sanskrit_name: Optional[str],
    houses: List[int],
    planets: List[str],
    relation: str,
    tier: str,
    effect: str,
    detail: str,
    dignity_consistency_flag: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "yoga_name": name,
        "sanskrit_name": sanskrit_name,
        "houses_involved": houses,
        "planets_involved": planets,
        "relation": relation,  # CONJUNCTION / MUTUAL_ASPECT / PARIVARTANA
        "confidence_tier": tier,  # STRONG / MODERATE / WEAK
        "effect": effect,  # plain-language, one line, narrative-safe
        "detail": detail,  # technical citation for astrologer edition
        # None in the normal case. Set to a short diagnostic code (see
        # _dignity_implies_conflicting_sign) if this record's two
        # dignity tags are provably mutually exclusive for a genuine
        # same-sign conjunction -- an honest "should never happen" flag
        # rather than a silently-wrong contradictory citation, following
        # this codebase's status/diagnostic field convention (see e.g.
        # scoring.py's chart_data_quality, ashtakavarga_timing.py's
        # status != "OK" degraded-diagnostic pattern).
        "dignity_consistency_flag": dignity_consistency_flag,
    }


def _detect_dhana_yogas(payload: Any) -> List[Dict[str, Any]]:
    """Dhana Yoga (wealth combination): 2nd and/or 11th lord in
    conjunction / mutual aspect / exchange with each other or with the
    5th/9th (trikona) lords. Classical rule (Phaladeepika/BPHS wealth
    chapters): 2nd (accumulated wealth) and 11th (gains) lords connecting
    with each other or with a trikona (fortune) lord is a core Dhana Yoga
    signature; this reuses the same conjunction/mutual-aspect/exchange
    tests as the rest of this module rather than re-deriving them."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    dignities = _rich_planet_dignities(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    def _ps(planet: str) -> Optional[str]:
        return planet_signs.get(planet) or None

    out: List[Dict[str, Any]] = []
    wealth_houses = [2, 11]
    trikona_partner_houses = [2, 11, 5, 9]
    checked_pairs = set()

    for wh in wealth_houses:
        w_lord = _h(wh)
        if not w_lord:
            continue
        for ph in trikona_partner_houses:
            if ph == wh:
                continue
            pair_key = tuple(sorted((wh, ph)))
            if pair_key in checked_pairs:
                continue
            p_lord = _h(ph)
            if not p_lord or p_lord == w_lord:
                continue

            relation = None
            exch = _parivartana_between_lords(payload, wh, ph)
            if exch:
                relation = "PARIVARTANA"
            else:
                rel = _conjunction_or_mutual_aspect(
                    _ph(w_lord), _ph(p_lord), _ps(w_lord), _ps(p_lord)
                )
                if rel:
                    relation = rel

            if not relation:
                continue

            checked_pairs.add(pair_key)

            dig_w, dig_p = _dig_name(w_lord, dignities), _dig_name(p_lord, dignities)
            # Safety invariant (see _dignity_implies_conflicting_sign):
            # should never fire for a CONJUNCTION derived from a genuine
            # sign_a == sign_b match -- if it does anyway (e.g. a future
            # stale/mismatched dignity lookup), flag it honestly instead
            # of silently publishing a contradictory citation.
            consistency_flag = None
            if relation == "CONJUNCTION" and _dignity_implies_conflicting_sign(w_lord, dig_w, p_lord, dig_p):
                consistency_flag = "DIGNITY_SIGN_REQUIREMENTS_CONFLICT"

            tier = _tier_from_dignities(payload, (w_lord, dig_w), (p_lord, dig_p))
            relation_text = {
                "CONJUNCTION": "conjunct",
                "MUTUAL_ASPECT": "in mutual (7th house) aspect",
                "PARIVARTANA": "in Parivartana (mutual sign/house exchange)",
            }[relation]
            out.append(_yoga_record(
                name="Dhana Yoga",
                sanskrit_name="Dhana Yoga",
                houses=sorted({wh, ph}),
                planets=sorted({w_lord, p_lord}),
                relation=relation,
                tier=tier,
                dignity_consistency_flag=consistency_flag,
                effect="Wealth-combination present: capital accumulation and gains houses reinforce each other, supporting sustained wealth building.",
                detail=(
                    f"H{wh} lord ({w_lord}, {_dignity_display(payload, w_lord, dig_w)}) {relation_text} H{ph} lord "
                    f"({p_lord}, {_dignity_display(payload, p_lord, dig_p)}) -> classical Dhana Yoga (2nd/11th "
                    f"wealth-house lord connecting with a trikona/gains lord)."
                ),
            ))
    return out


def _detect_raja_yogas(payload: Any) -> List[Dict[str, Any]]:
    """Raja Yoga (status/power combination): a kendra lord (1/4/7/10) in
    conjunction / mutual aspect / exchange with a trikona lord (1/5/9).
    Classical BPHS rule -- the single most cited Raja Yoga formation.
    Lagna (house 1) lord counts in both sets per classical convention, but
    is not paired with itself."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    dignities = _rich_planet_dignities(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    def _ps(planet: str) -> Optional[str]:
        return planet_signs.get(planet) or None

    out: List[Dict[str, Any]] = []
    kendra_houses = [1, 4, 7, 10]
    trikona_houses = [1, 5, 9]
    checked_pairs = set()
    # Consolidation guard: the SAME two planets can be lords of more than
    # one kendra/trikona house pair (a planet often rules two houses at
    # once), which would otherwise emit multiple "Raja Yoga" records for
    # what is, physically, one planetary relationship (e.g. Jupiter-Sun
    # counted once for H9/H10 and again for H1/H10). Track already-emitted
    # records by the underlying (unordered) planet pair and merge the
    # additional house-pair citation into the first record's houses/detail
    # instead of appending a duplicate record, so the final count reflects
    # unique planetary facts, not lordship-pair permutations.
    seen_planet_pairs: Dict[frozenset, Dict[str, Any]] = {}

    for kh in kendra_houses:
        k_lord = _h(kh)
        if not k_lord:
            continue
        for th in trikona_houses:
            if kh == th:
                continue
            pair_key = tuple(sorted((kh, th)))
            if pair_key in checked_pairs:
                continue
            t_lord = _h(th)
            if not t_lord or t_lord == k_lord:
                continue

            relation = None
            exch = _parivartana_between_lords(payload, kh, th)
            if exch:
                relation = "PARIVARTANA"
            else:
                rel = _conjunction_or_mutual_aspect(
                    _ph(k_lord), _ph(t_lord), _ps(k_lord), _ps(t_lord)
                )
                if rel:
                    relation = rel

            if not relation:
                continue

            checked_pairs.add(pair_key)

            dig_k, dig_t = _dig_name(k_lord, dignities), _dig_name(t_lord, dignities)
            # Safety invariant -- see _dignity_implies_conflicting_sign.
            # Should never fire for a CONJUNCTION derived from a genuine
            # sign_a == sign_b match; flags rather than silently emits the
            # exact class of bug an audit found: "H7 lord Mercury, OWN
            # conjunct H9 lord Sun, DEBILITATED" is impossible since
            # Mercury-OWN requires Gemini/Virgo and Sun-DEBILITATED
            # requires Libra.
            consistency_flag = None
            if relation == "CONJUNCTION" and _dignity_implies_conflicting_sign(k_lord, dig_k, t_lord, dig_t):
                consistency_flag = "DIGNITY_SIGN_REQUIREMENTS_CONFLICT"

            tier = _tier_from_dignities(payload, (k_lord, dig_k), (t_lord, dig_t))
            relation_text = {
                "CONJUNCTION": "conjunct",
                "MUTUAL_ASPECT": "in mutual (7th house) aspect",
                "PARIVARTANA": "in Parivartana (mutual sign/house exchange)",
            }[relation]
            detail_line = (
                f"H{kh} (kendra) lord ({k_lord}, {_dignity_display(payload, k_lord, dig_k)}) {relation_text} "
                f"H{th} (trikona) lord ({t_lord}, {_dignity_display(payload, t_lord, dig_t)}) -> classical "
                f"Raja Yoga (kendra-trikona lord combination)."
            )

            planet_pair_key = frozenset({k_lord, t_lord})
            existing = seen_planet_pairs.get(planet_pair_key)
            if existing is not None:
                # Same two planets already recorded as a Raja Yoga via a
                # different kendra/trikona house-pair -- this is the same
                # underlying planetary relationship, not a second yoga.
                # Merge the additional house-pair citation instead of
                # appending a duplicate record.
                existing["houses_involved"] = sorted(set(existing["houses_involved"]) | {kh, th})
                existing.setdefault("additional_house_pair_citations", []).append(
                    {"houses": [kh, th], "relation": relation, "detail": detail_line}
                )
                existing["detail"] = (
                    existing["detail"]
                    + f" [Also lord-pair-confirmed via H{kh}/H{th}: {detail_line}]"
                )
                continue

            record = _yoga_record(
                name="Raja Yoga",
                sanskrit_name="Raja Yoga",
                houses=sorted({kh, th}),
                planets=sorted({k_lord, t_lord}),
                relation=relation,
                tier=tier,
                dignity_consistency_flag=consistency_flag,
                effect="Status/power combination present: house of action and house of fortune are linked, supporting authority, recognition, and rise in standing.",
                detail=detail_line,
            )
            seen_planet_pairs[planet_pair_key] = record
            out.append(record)
    return out


def _detect_mercury_saturn_rahu_yoga(payload: Any) -> List[Dict[str, Any]]:
    """Explicit, discretely-named "Mercury-Saturn-Rahu business combination"
    -- an informally-named modern trading/technology/scalable-platform
    signature already partially scored, unlabeled, inside
    operating_models.py's scalable_platform archetype
    (`rahu_h and (mercury_h == rahu_h or sat_h == rahu_h)`). This function
    packages the same underlying conjunction test as a discrete, named
    yoga result and extends it to also check mutual aspect (not just
    conjunction) and require the combination to involve a business-
    relevant house (2/6/7/10/11), matching the requirement text. NOT a
    classical BPHS/Jaimini yoga -- an explicit engineered pattern name for
    a recognizable modern signature (Mercury=trade/communication,
    Saturn=structure/discipline/scale, Rahu=technology/unconventional
    amplification)."""
    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    dignities = _rich_planet_dignities(payload)
    business_houses = {2, 6, 7, 10, 11}

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    def _ps(planet: str) -> Optional[str]:
        return planet_signs.get(planet) or None

    mer_h, sat_h, rahu_h = _ph("Mercury"), _ph("Saturn"), _ph("Rahu")
    pairs = [("Mercury", "Rahu", mer_h, rahu_h),
             ("Saturn", "Rahu", sat_h, rahu_h),
             ("Mercury", "Saturn", mer_h, sat_h)]

    out: List[Dict[str, Any]] = []
    seen_relation_houses = set()
    for p1, p2, h1, h2 in pairs:
        relation = _conjunction_or_mutual_aspect(h1, h2, _ps(p1), _ps(p2))
        if not relation:
            continue
        involved_houses = {h for h in (h1, h2) if h}
        if not (involved_houses & business_houses):
            continue
        dedup_key = (p1, p2, relation, tuple(sorted(involved_houses)))
        if dedup_key in seen_relation_houses:
            continue

        seen_relation_houses.add(dedup_key)

        dig1, dig2 = _dig_name(p1, dignities), _dig_name(p2, dignities)
        # Safety invariant -- see _dignity_implies_conflicting_sign.
        consistency_flag = None
        if relation == "CONJUNCTION" and _dignity_implies_conflicting_sign(p1, dig1, p2, dig2):
            consistency_flag = "DIGNITY_SIGN_REQUIREMENTS_CONFLICT"

        tier = _tier_from_dignities(payload, (p1, dig1), (p2, dig2))
        relation_text = "conjunct" if relation == "CONJUNCTION" else "in mutual (7th house) aspect"
        out.append(_yoga_record(
            name="Mercury-Saturn-Rahu Business Combination",
            sanskrit_name=None,
            houses=sorted(involved_houses),
            planets=sorted({p1, p2}),
            relation=relation,
            tier=tier,
            dignity_consistency_flag=consistency_flag,
            effect="Modern trading/technology/scalable-platform signature present: communication, structure, and unconventional amplification are linked in a business-relevant house.",
            detail=(
                f"{p1} ({_dignity_display(payload, p1, dig1)}) {relation_text} {p2} ({_dignity_display(payload, p2, dig2)}) involving "
                f"H{sorted(involved_houses)} -> engineered Mercury-Saturn-Rahu "
                f"business combination (not a classical named yoga; extends "
                f"operating_models.py's scalable_platform Rahu+Mercury/Saturn "
                f"conjunction check to mutual aspect and explicit naming)."
            ),
        ))
    return out


_KENDRA_HOUSES = {1, 4, 7, 10}


def _detect_bhadra_mahapurusha_yoga(payload: Any) -> List[Dict[str, Any]]:
    """Bhadra Mahapurusha Yoga (one of the five classical Pancha
    Mahapurusha Yogas): Mercury placed in a kendra (1/4/7/10) from the
    Lagna while in its own sign (Gemini/Virgo) or exaltation (Virgo).
    Classical BPHS combination distinct from the generic Raja/Dhana
    detectors above -- a single-planet dignity-in-kendra yoga, not a
    two-lord relationship."""
    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    dignities = _rich_planet_dignities(payload)
    combust_planets = set(getattr(payload, "combust_planets", []) or [])

    merc_house = planet_house.get("Mercury", 0)
    merc_sign = planet_signs.get("Mercury")
    dig = _dig_name("Mercury", dignities)

    if not merc_house or merc_house not in _KENDRA_HOUSES:
        return []
    if dig not in ("OWN", "EXALTED", "MOOLATRIKONA"):
        return []

    is_combust = "Mercury" in combust_planets
    tier = "STRONG" if not is_combust else "MODERATE"
    combustion_note = ""
    if is_combust:
        # Classical view: combustion diminishes a yoga's outward
        # expression but does NOT cancel it when the planet is exalted or
        # in its own sign -- Mercury in Virgo (own sign) here -- unlike a
        # combust NEUTRAL/debilitated planet, which loses more ground.
        combustion_note = (
            " Mercury is combust (within ~5deg of the Sun); classically this "
            "diminishes -- but, because Mercury is in dignity (OWN/EXALTED) here, "
            "does not cancel -- the yoga's outward expression."
        )
    return [_yoga_record(
        name="Bhadra Mahapurusha Yoga",
        sanskrit_name="Bhadra Yoga",
        houses=[merc_house],
        planets=["Mercury"],
        relation="DIGNITY_IN_KENDRA",
        tier=tier,
        effect=(
            "One of the five Pancha Mahapurusha Yogas: sharp intellect, business/analytical "
            "acumen, communication skill, and commercial success supported by a strong, "
            "well-placed Mercury."
        ),
        detail=(
            f"Mercury ({_dignity_display(payload, 'Mercury', dig)}, sign {merc_sign or 'unknown'}) "
            f"occupies kendra H{merc_house} from Lagna -> classical Bhadra Mahapurusha Yoga."
            + combustion_note
        ),
    )]


def _detect_budha_aditya_yoga(payload: Any) -> List[Dict[str, Any]]:
    """Budha-Aditya Yoga: Sun and Mercury conjunct in the same house/sign.
    Classical combination for intellect, analytical skill, and
    administrative/advisory capability -- distinct from the generic
    conjunction tests above since it is specifically named for this one
    planetary pair regardless of which houses Sun/Mercury happen to lord."""
    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    dignities = _rich_planet_dignities(payload)
    combust_planets = set(getattr(payload, "combust_planets", []) or [])

    sun_h, merc_h = planet_house.get("Sun", 0), planet_house.get("Mercury", 0)
    sun_s, merc_s = planet_signs.get("Sun"), planet_signs.get("Mercury")
    relation = _conjunction_or_mutual_aspect(sun_h, merc_h, sun_s, merc_s)
    if relation != "CONJUNCTION":
        return []

    dig_sun, dig_merc = _dig_name("Sun", dignities), _dig_name("Mercury", dignities)
    consistency_flag = None
    if _dignity_implies_conflicting_sign("Sun", dig_sun, "Mercury", dig_merc):
        consistency_flag = "DIGNITY_SIGN_REQUIREMENTS_CONFLICT"

    tier = _tier_from_dignities(payload, ("Sun", dig_sun), ("Mercury", dig_merc))
    is_combust = "Mercury" in combust_planets
    combustion_note = ""
    if is_combust:
        combustion_note = (
            " Mercury is combust (within ~5deg of the Sun) -- expected here since this is "
            "the same conjunction that causes the combustion; classically this diminishes "
            "but does not cancel the yoga when Mercury holds dignity (OWN/EXALTED)."
        )
        if dig_merc in ("OWN", "EXALTED", "MOOLATRIKONA"):
            tier = "MODERATE" if tier == "WEAK" else tier
    return [_yoga_record(
        name="Budha-Aditya Yoga",
        sanskrit_name="Budha-Aditya Yoga",
        houses=sorted({h for h in (sun_h, merc_h) if h}),
        planets=["Mercury", "Sun"],
        relation=relation,
        tier=tier,
        dignity_consistency_flag=consistency_flag,
        effect=(
            "Sun-Mercury combination present: intellect, analytical reasoning, and "
            "administrative/advisory capability are reinforced -- classically associated with "
            "sharp decision-making and leadership-through-expertise."
        ),
        detail=(
            f"Sun ({_dignity_display(payload, 'Sun', dig_sun)}) conjunct Mercury "
            f"({_dignity_display(payload, 'Mercury', dig_merc)}) in H{sorted({h for h in (sun_h, merc_h) if h})} "
            f"-> classical Budha-Aditya Yoga." + combustion_note
        ),
    )]


def _detect_dharma_karmadhipati_yoga(payload: Any) -> List[Dict[str, Any]]:
    """Dharma-Karmadhipati Yoga: the 9th lord (Dharma -- fortune/ethics)
    and 10th lord (Karma -- action/career) connected by conjunction,
    mutual aspect, or Parivartana. One of the most emphasized classical
    combinations for career success/public standing (BPHS, Phaladeepika)
    -- distinct from the generic kendra-trikona Raja Yoga test since it
    names this SPECIFIC 9th/10th pairing regardless of whether 9 or 10 is
    also functioning as a kendra/trikona house for some other reason."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    dignities = _rich_planet_dignities(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    lord9, lord10 = _h(9), _h(10)
    if not lord9 or not lord10 or lord9 == lord10:
        return []

    relation = None
    exch = _parivartana_between_lords(payload, 9, 10)
    if exch:
        relation = "PARIVARTANA"
    else:
        relation = _conjunction_or_mutual_aspect(
            planet_house.get(lord9, 0), planet_house.get(lord10, 0),
            planet_signs.get(lord9), planet_signs.get(lord10),
        )
    if not relation:
        return []

    dig9, dig10 = _dig_name(lord9, dignities), _dig_name(lord10, dignities)
    consistency_flag = None
    if relation == "CONJUNCTION" and _dignity_implies_conflicting_sign(lord9, dig9, lord10, dig10):
        consistency_flag = "DIGNITY_SIGN_REQUIREMENTS_CONFLICT"

    tier = _tier_from_dignities(payload, (lord9, dig9), (lord10, dig10))
    relation_text = {
        "CONJUNCTION": "conjunct",
        "MUTUAL_ASPECT": "in mutual (7th house) aspect",
        "PARIVARTANA": "in Parivartana (mutual sign/house exchange)",
    }[relation]
    return [_yoga_record(
        name="Dharma-Karmadhipati Yoga",
        sanskrit_name="Dharma-Karmadhipati Yoga",
        houses=[9, 10],
        planets=sorted({lord9, lord10}),
        relation=relation,
        tier=tier,
        dignity_consistency_flag=consistency_flag,
        effect=(
            "One of the most powerful classical combinations for career and public standing: "
            "the houses of fortune/ethics (9th) and action/career (10th) reinforce each other, "
            "supporting sustained professional success, reputation, and right-livelihood alignment."
        ),
        detail=(
            f"H9 (Dharma) lord ({lord9}, {_dignity_display(payload, lord9, dig9)}) {relation_text} "
            f"H10 (Karma) lord ({lord10}, {_dignity_display(payload, lord10, dig10)}) -> classical "
            f"Dharma-Karmadhipati Yoga."
        ),
    )]


def yoga_detection_status(payload: Any) -> str:
    """Distinguish an evaluated chart with no named match from a check
    that could not run because the minimum D1 fact set was unavailable."""
    if payload is None:
        return "NOT_EVALUATED"
    if not (getattr(payload, "house_lords", None) and getattr(payload, "planet_house", None)):
        return "NOT_EVALUATED"
    return "MATCHES_FOUND" if detect_business_yogas(payload) else "EVALUATED_NO_MATCH"


def detect_business_yogas(payload: Any) -> List[Dict[str, Any]]:
    """Detects and names discrete classical/engineered business-relevant
    yogas on the given chart payload. Returns an empty list (never raises)
    when the chart has none of the currently-detected patterns or lacks
    the required data (house_lords/planet_house), so callers can always
    safely iterate the result.

    Each returned dict has keys: yoga_name, sanskrit_name, houses_involved,
    planets_involved, relation, confidence_tier (STRONG/MODERATE/WEAK),
    effect (plain-language one-liner for narrative rendering), detail
    (technical citation for the astrologer edition).
    """
    if not getattr(payload, "house_lords", None) or not getattr(payload, "planet_house", None):
        return []

    # Engineering audit fix #9: each of these three detectors previously
    # swallowed its exception with a bare `pass` -- a real defect in one
    # detector (e.g. a KeyError from an unexpected payload shape) was
    # indistinguishable from "this chart has no such yoga." Recorded via
    # _record_diagnostic without changing the graceful "skip this detector,
    # keep the others" behavior.
    results: List[Dict[str, Any]] = []
    try:
        results.extend(_detect_raja_yogas(payload))
    except Exception as exc:
        _record_diagnostic("yogas._detect_raja_yogas", exc)
    try:
        results.extend(_detect_dhana_yogas(payload))
    except Exception as exc:
        _record_diagnostic("yogas._detect_dhana_yogas", exc)
    try:
        results.extend(_detect_mercury_saturn_rahu_yoga(payload))
    except Exception as exc:
        _record_diagnostic("yogas._detect_mercury_saturn_rahu_yoga", exc)
    try:
        results.extend(_detect_bhadra_mahapurusha_yoga(payload))
    except Exception as exc:
        _record_diagnostic("yogas._detect_bhadra_mahapurusha_yoga", exc)
    try:
        results.extend(_detect_budha_aditya_yoga(payload))
    except Exception as exc:
        _record_diagnostic("yogas._detect_budha_aditya_yoga", exc)
    try:
        results.extend(_detect_dharma_karmadhipati_yoga(payload))
    except Exception as exc:
        _record_diagnostic("yogas._detect_dharma_karmadhipati_yoga", exc)
    return results
