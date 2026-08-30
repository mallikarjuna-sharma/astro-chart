"""Business_Prediction/business_determination/legal_risk.py
============================================================
Discrete NAMED legal-dispute / litigation-risk detection layer.

Existing risk logic (contradictions.py's 14 named checks, timing.py's
RAHU_KETU_AXIS_MAJOR_CHANGE transit flag, significators.py/mode_gate.py's
generic H6/H8/H12 "loss/liability exposure" language) already captures
loss/instability risk in general terms, but nothing in the package NAMES
litigation/legal-dispute risk as a discrete, individually-citable finding
the way yogas.py names classical combinations. This module is the risk-side
mirror of yogas.py: it is a PACKAGING + light-extension layer that reuses
primitives already available (house_lords/planet_house/planet_dignities
accessors, _dig_name/_dig_factor, _effective_benefic_malefic_sets,
_conjunction_or_mutual_aspect from yogas.py) and adds four discrete,
classically-grounded litigation/dispute checks:

  1. Rahu-Ketu axis stress on 6th/7th/12th houses (natal placement or
     lordship) -- dispute, litigation, partnership breakdown, hidden
     enemies. Distinct from timing.py's RAHU_KETU_AXIS_MAJOR_CHANGE, which
     is a direction-neutral TRANSIT volatility flag; this check is natal
     (D1 placement/lordship), and only optionally cites the transit flag
     (if the caller has already computed it and attached it to the payload,
     e.g. as `payload.active_transit_flags`) as corroboration, never as the
     primary trigger.
  2. Mars-Saturn combination (conjunction or mutual aspect) touching
     6th/7th/8th house -- classical litigation/dispute significators
     (Mars=aggression/conflict, Saturn=delay/legal process, 6th=disputes,
     7th=the other party/contracts, 8th=court cases/hidden liability).
  3. 7th house lord afflicted by malefic(s) (Mars/Saturn/Rahu/Ketu) via
     conjunction, framed specifically as CONTRACT_DISPUTE_RISK -- separate
     from significators.py's generic H7 partnership-capacity scoring and
     contradictions.py's check #5 (which flags "partner/customer
     instability" broadly, not litigation specifically).
  4. 6th lord in 7th OR 7th lord in 6th -- classical "litigation with
     partners" combination (disputes house and partnership house directly
     exchanging/occupying each other).

MATURITY: same status as every other module in this package -- see
MODEL_STATUS / CALIBRATION_STATUS / MATURITY_STATEMENT in constants.py.
This is a rule-based pattern match on the D1 chart, dignity-adjusted for
confidence tier -- not a claim of unique classical authority on
cancellation/mitigation conditions beyond what is implemented, and NOT
legal advice of any kind.

Public API
----------
    detect_legal_dispute_risk(payload) -> List[Dict[str, Any]]
"""
from __future__ import annotations

from typing import Any, Dict, List

from .constants import _STRONG_DIGNITY, _record_diagnostic
from .house_evidence import _dig_name, _NATURAL_MALEFICS, _rich_planet_dignities
from .yogas import _conjunction_or_mutual_aspect, _tier_from_dignities


_LITIGATION_MALEFICS = frozenset({"Mars", "Saturn", "Rahu", "Ketu"})


def _risk_record(
    risk_type: str,
    houses: List[int],
    planets: List[str],
    tier: str,
    effect: str,
    detail: str,
) -> Dict[str, Any]:
    return {
        "risk_type": risk_type,
        "houses_involved": sorted(set(houses)),
        "planets_involved": sorted(set(planets)),
        "confidence_tier": tier,  # STRONG / MODERATE / WEAK
        "effect": effect,  # plain-language, one line, narrative-safe (client edition)
        "detail": detail,  # technical citation for astrologer edition
    }


def _house_lords_and_planet_house(payload: Any):
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    return house_lords, planet_house, _h, _ph


def _detect_rahu_ketu_dispute_axis(payload: Any) -> List[Dict[str, Any]]:
    """Rahu-Ketu axis stress specifically on 6th/7th/12th houses: natal
    placement (Rahu/Ketu occupying H6/H7/H12) or lordship (a sign whose
    natural/assigned lordship touches those houses is not applicable to
    nodes in most house-lord schemes, so this checks placement and, where
    house_lords maps a node as a dispositor/assigned lord -- some divisional
    or KP-style payloads do -- lordship too). Optionally corroborated by an
    already-computed transit flag on the payload (never required)."""
    _, planet_house, _h, _ph = _house_lords_and_planet_house(payload)
    dignities = _rich_planet_dignities(payload)
    dispute_houses = {6, 7, 12}

    out: List[Dict[str, Any]] = []
    for node in ("Rahu", "Ketu"):
        node_house = _ph(node)
        touched = set()
        if node_house in dispute_houses:
            touched.add(node_house)
        for dh in dispute_houses:
            if _h(dh) == node:
                touched.add(dh)
        if not touched:
            continue

        dig = _dig_name(node, dignities)
        tier = _tier_from_dignities(payload, (node, dig))
        # Nodes are never "strong dignity" per _STRONG_DIGNITY in most
        # payload conventions, so this tier will usually read MODERATE/WEAK
        # from _tier_from_dignities alone; escalate to MODERATE by default
        # since node placement in a dispute house is evidence regardless of
        # dignity (dignity here refines rather than gates the signal).
        if tier == "WEAK" and dig != "DEBILITATED":
            tier = "MODERATE"

        notes = []
        active_flags = getattr(payload, "active_transit_flags", None) or []
        if "RAHU_KETU_AXIS_MAJOR_CHANGE" in active_flags:
            notes.append(
                "corroborated by currently active RAHU_KETU_AXIS_MAJOR_CHANGE transit "
                "(direction-neutral volatility flag; here read as directional toward "
                "dispute risk because it lands on a natal 6/7/12 node placement)"
            )

        house_word = {6: "6th (disputes/litigation)", 7: "7th (partners/contracts)",
                      12: "12th (hidden losses/isolation)"}
        houses_text = ", ".join(house_word[h] for h in sorted(touched))
        detail = (
            f"{node} ({dig}) occupies/lords the {houses_text} house(s) -> Rahu-Ketu "
            f"axis stress landing directly on dispute/partnership/hidden-loss houses, "
            f"read as elevated litigation and partnership-breakdown potential."
        )
        if notes:
            detail += " " + "; ".join(notes) + "."

        out.append(_risk_record(
            risk_type="LITIGATION_RISK",
            houses=sorted(touched),
            planets=[node],
            tier=tier,
            effect="Rahu-Ketu axis stress on a dispute/partnership house present: elevated potential for disputes, litigation, or breakdown of partnerships/hidden liabilities -- warrants careful contract review and conflict-avoidance planning.",
            detail=detail,
        ))
    return out


def _detect_mars_saturn_dispute_combination(payload: Any) -> List[Dict[str, Any]]:
    """Mars-Saturn combination (conjunction or mutual aspect) touching
    6th/7th/8th house -- classical litigation/dispute significators."""
    _, planet_house, _h, _ph = _house_lords_and_planet_house(payload)
    dignities = _rich_planet_dignities(payload)
    dispute_houses = {6, 7, 8}

    mars_h, sat_h = _ph("Mars"), _ph("Saturn")
    relation = _conjunction_or_mutual_aspect(mars_h, sat_h)
    if not relation:
        return []
    involved_houses = {h for h in (mars_h, sat_h) if h} & dispute_houses
    if not involved_houses:
        return []

    dig_m, dig_s = _dig_name("Mars", dignities), _dig_name("Saturn", dignities)
    tier = _tier_from_dignities(payload, ("Mars", dig_m), ("Saturn", dig_s))
    relation_text = "conjunct" if relation == "CONJUNCTION" else "in mutual (7th house) aspect"

    house_word = {6: "6th (disputes)", 7: "7th (contracts/other party)", 8: "8th (court cases/hidden liability)"}
    houses_text = ", ".join(house_word[h] for h in sorted(involved_houses))

    return [_risk_record(
        risk_type="LITIGATION_RISK",
        houses=sorted(involved_houses),
        planets=["Mars", "Saturn"],
        tier=tier,
        effect="Mars-Saturn dispute combination present in a litigation-relevant house: classical signature for conflict escalating into a prolonged, delay-heavy legal or contractual process.",
        detail=(
            f"Mars ({dig_m}) {relation_text} Saturn ({dig_s}) involving the {houses_text} "
            f"house(s) -> classical Mars(conflict)-Saturn(delay/legal process) dispute "
            f"combination on a litigation-relevant house."
        ),
    )]


def _detect_h7_lord_affliction_contract_risk(payload: Any) -> List[Dict[str, Any]]:
    """7th house lord conjunct malefic(s) (Mars/Saturn/Rahu/Ketu), framed
    specifically as CONTRACT_DISPUTE_RISK -- distinct from significators.py's
    generic H7 partnership-capacity scoring and contradictions.py's broader
    "partner/customer instability" contradiction (#5)."""
    house_lords, planet_house, _h, _ph = _house_lords_and_planet_house(payload)
    dignities = _rich_planet_dignities(payload)

    h7_lord = _h(7)
    if not h7_lord:
        return []
    h7_lord_house = _ph(h7_lord)
    if not h7_lord_house:
        return []

    co_tenants = [p for p, h in planet_house.items() if h == h7_lord_house and p != h7_lord]
    mal_co = sorted(set(p for p in co_tenants if p in _LITIGATION_MALEFICS))
    if not mal_co:
        return []

    dig_lord = _dig_name(h7_lord, dignities)
    tier_pairs = [(h7_lord, dig_lord)] + [(p, _dig_name(p, dignities)) for p in mal_co]
    tier = _tier_from_dignities(payload, *tier_pairs)
    # Affliction is negative evidence -- more/stronger afflicting malefics
    # should not read as a WEAKER risk just because _tier_from_dignities
    # (built for positive combinations) sees "strong" dignified malefics;
    # invert the reading here: a well-dignified afflicting malefic is a
    # STRONGER dispute risk, not a weaker one.
    strong_malefics = sum(1 for p in mal_co if _dig_name(p, dignities) in _STRONG_DIGNITY)
    if strong_malefics >= 1 or len(mal_co) >= 2:
        tier = "STRONG"
    elif dig_lord == "DEBILITATED":
        tier = "MODERATE"
    else:
        tier = "MODERATE" if tier == "WEAK" else tier

    return [_risk_record(
        risk_type="CONTRACT_DISPUTE_RISK",
        houses=[7],
        planets=[h7_lord] + mal_co,
        tier=tier,
        effect="7th house lord (partnerships/contracts/the other party) is afflicted by malefic influence: elevated risk of contract disputes, partner conflict, or adversarial counterparties -- review agreements and partnership terms carefully.",
        detail=(
            f"H7 lord ({h7_lord}, {dig_lord}) conjunct malefic(s) {', '.join(mal_co)} "
            f"-> 7th house (contracts, the other party, open enemies in some schools) "
            f"afflicted, read as contract and partner dispute risk (distinct from "
            f"significators.py's generic H7 partnership-capacity scoring)."
        ),
    )]


def _detect_h6_h7_lord_exchange_risk(payload: Any) -> List[Dict[str, Any]]:
    """6th lord in 7th OR 7th lord in 6th -- classical "litigation with
    partners" combination (not necessarily a full Parivartana; either
    single-direction placement or the mutual exchange both qualify, since
    the classical rule is stated as either lord being posited in the
    other's house)."""
    house_lords, planet_house, _h, _ph = _house_lords_and_planet_house(payload)
    dignities = _rich_planet_dignities(payload)

    h6_lord, h7_lord = _h(6), _h(7)
    if not h6_lord or not h7_lord or h6_lord == h7_lord:
        return []

    h6_in_7 = _ph(h6_lord) == 7
    h7_in_6 = _ph(h7_lord) == 6
    if not (h6_in_7 or h7_in_6):
        return []

    is_exchange = h6_in_7 and h7_in_6
    dig6, dig7 = _dig_name(h6_lord, dignities), _dig_name(h7_lord, dignities)
    tier = _tier_from_dignities(payload, (h6_lord, dig6), (h7_lord, dig7))
    if is_exchange:
        tier = "STRONG" if tier != "WEAK" else "MODERATE"
        placement_text = f"H6 lord ({h6_lord}, {dig6}) and H7 lord ({h7_lord}, {dig7}) mutually exchange (Parivartana)"
    elif h6_in_7:
        placement_text = f"H6 lord ({h6_lord}, {dig6}) is placed in H7"
    else:
        placement_text = f"H7 lord ({h7_lord}, {dig7}) is placed in H6"

    return [_risk_record(
        risk_type="PARTNER_CONFLICT_RISK",
        houses=[6, 7],
        planets=sorted({h6_lord, h7_lord}),
        tier=tier,
        effect="Disputes house (6th) and partnership house (7th) are directly linked through lordship placement: classical signature for litigation arising specifically from a business partnership or contractual relationship.",
        detail=(
            f"{placement_text} -> classical 6th-lord/7th-lord placement "
            f"combination read as litigation-with-partners risk."
        ),
    )]


def detect_legal_dispute_risk(payload: Any) -> List[Dict[str, Any]]:
    """Detects and names discrete legal-dispute/litigation-risk patterns on
    the given chart payload. Returns an empty list (never raises) when the
    chart has none of the currently-detected patterns or lacks the
    required data (house_lords/planet_house), so callers can always safely
    iterate the result.

    Each returned dict has keys: risk_type (LITIGATION_RISK /
    CONTRACT_DISPUTE_RISK / PARTNER_CONFLICT_RISK), houses_involved,
    planets_involved, confidence_tier (STRONG/MODERATE/WEAK), effect
    (plain-language one-liner for narrative rendering, client-safe caution
    framing), detail (technical citation for the astrologer edition).

    NOT legal advice -- an astrological indication of dispute-prone
    combinations only. See MATURITY_CAVEATS / MATURITY_STATEMENT for the
    same interpretive-limits framing that applies to every module in this
    package.
    """
    if not getattr(payload, "house_lords", None) or not getattr(payload, "planet_house", None):
        return []

    results: List[Dict[str, Any]] = []
    for fn in (
        _detect_rahu_ketu_dispute_axis,
        _detect_mars_saturn_dispute_combination,
        _detect_h7_lord_affliction_contract_risk,
        _detect_h6_h7_lord_exchange_risk,
    ):
        try:
            results.extend(fn(payload))
        except Exception as exc:
            _record_diagnostic(f"legal_risk.{fn.__name__}", exc)
    return results


def legal_dispute_risk_status(payload: Any) -> str:
    """Issue 15 fix: detect_legal_dispute_risk() returns a bare empty list
    both when the required D1 data is missing (genuinely NOT_EVALUATED)
    and when the data IS present but none of the four named patterns
    matched (EVALUATED_NO_MATCH -- a real, meaningful "checked, nothing
    found" result, not the absence of a check). Reports that only ever
    render when the list is non-empty collapse both cases into silence,
    which reads as "no risk" rather than distinguishing "not checked" from
    "checked, clear". This status label makes that distinction explicit
    and consistent, and (like the ashtakavarga/muhurta prior-round fix
    referenced in generate_business_report.py's not-evaluated-disclosure
    class) uses the same NOT_EVALUATED sentinel string for the genuinely-
    unchecked case rather than a bare empty/"no risk found" reading."""
    if not getattr(payload, "house_lords", None) or not getattr(payload, "planet_house", None):
        return "NOT_EVALUATED"
    return "EVALUATED_NO_MATCH" if not detect_legal_dispute_risk(payload) else "MATCHES_FOUND"
