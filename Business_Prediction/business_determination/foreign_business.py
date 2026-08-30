"""Business_Prediction/business_determination/foreign_business.py
=====================================================================
Dedicated, technique-specific "is foreign/cross-border business favorable
for this native" check bundle -- distinct from sectors.py's generic
sector-affinity math (archetype vector + mean core_houses/core_planets
strength), which already scores `import_export_foreign_trade` (core_houses
[7, 9, 12], core_planets [Rahu, Mercury]) but only as an averaged,
undifferentiated blend. That generic blend cannot answer -- or cite
separately -- the classical question this module targets: does THIS
chart's 12th house (videsha -- foreign residence/lands/dealings), 9th
house (long-distance travel, foreign higher-learning/dharma ties) and
Rahu's own placement/dignity specifically corroborate cross-border
business viability, as opposed to merely contributing to an averaged
7-9-12/Rahu-Mercury sector score?

Classical basis (curated, NOT exhaustive -- see MATURITY_STATEMENT
elsewhere in this package for the same "one documented reading, not the
only one a traditional astrologer would accept" caveat):

  - 12th house = videsha (foreign lands), foreign residence, cross-border
    dealings and expenditure/investment abroad. A strong, well-dignified
    12th lord is commonly cited as supporting foreign business/residence;
    an afflicted or debilitated 12th lord is read as caution specific to
    OVERSEAS ventures, not a general chart negative (scope-limited: this
    module never claims a debilitated 12th lord means "bad business" in
    general, only "caution for the foreign-business question").
  - 9th house = long-distance travel, foreign connections, dharma/higher
    learning, often linked to overseas study/trade ties in classical
    business-astrology readings. Treated here as a SECONDARY,
    corroborating signal to the 12th lord (roughly half weight), not a
    co-equal primary.
  - Rahu = classical significator of foreign lands, foreign goods,
    unconventional/cross-border dealings (BPHS and later Jyotish
    literature commonly cite Rahu for imports, foreign travel, and
    dealings with foreign people/cultures). Rahu placed in a business-
    relevant house (2/6/7/10/11, the same houses house_evidence.py/
    significators.py already treat as business-significative) AND in one
    of the houses classically tied to foreign connections (7th -- foreign
    partnerships/collaborators, 9th, 12th) is cited as a stronger foreign-
    business indicator than Rahu placed elsewhere. Rahu conjunct (same
    house) or aspecting (simple whole-sign 7th-house graha-drishti, the
    same simplified aspect convention already used informally elsewhere
    in this package) the 9th or 12th lord is an additional, separately
    cited combination.

Weight scale
------------
This is a SECONDARY/supporting technique bundle answering one narrow
question ("is foreign/cross-border business favorable"), not a re-scoring
of the whole chart. Weights are kept in the same modest-to-moderate range
already established for D2/D3/D7 varga corroboration and janma-nakshatra
business-aptitude citations elsewhere in this package (roughly +1.5..+4.0
positive, -1.0..-3.0 caution), well below the +8..+10-or-more range used
for primary house-lord/dasha-level determinants in house_evidence.py/
significators.py, so this bundle cannot on its own overturn the primary
house/dasha analysis or the generic sector-affinity score.

Payload fields read
--------------------
    payload.house_lords        Dict[str|int, str]   house -> ruling planet
    payload.planet_house        Dict[str, int]        planet -> house occupied
    payload.planet_dignities /
    payload.planets_d1          (via house_evidence._rich_planet_dignities,
                                 falls back to the coarser payload.planet_
                                 dignities when raw chart data is absent)

Degrades gracefully (returns []; never raises) whenever house_lords/
planet_house data needed for a given check is missing -- matches the
"no evidence, not a penalty" contract used throughout this package (see
nakshatra_business.py / _d3_native_house_evidence()'s docstrings for the
same convention).

Public API
----------
    foreign_business_viability_evidence(payload) -> List[Dict[str, Any]]
"""
from __future__ import annotations

from typing import Any, Dict, List

from .house_evidence import (
    _rich_planet_dignities,
    _dig_name,
    _dig_factor,
    _house_lord_strength,
    _neecha_bhanga_status,
)
from .constants import _KT, _DUSTHANA, _STRONG_DIGNITY, _record_diagnostic

__all__ = ["foreign_business_viability_evidence"]

# Houses classically tied to foreign connections (see module docstring).
_FOREIGN_HOUSES = frozenset({7, 9, 12})
# Houses this package already treats as generically business-significative
# (2nd wealth, 6th service/competition, 7th trade/partnership, 10th
# livelihood, 11th gains) -- reused here, not re-derived, so "business-
# relevant" means the same thing it does everywhere else in this codebase.
_BUSINESS_HOUSES = frozenset({2, 6, 7, 10, 11})


def _house_of(house_lords: Dict[str, Any], num: int) -> str:
    return house_lords.get(str(num), house_lords.get(num, "")) or ""


def _lord_placement_evidence(payload: Any, house_num: int, label: str, weight_scale: float) -> List[Dict[str, Any]]:
    """Strength/dignity citation for the lord of `house_num` (9 or 12),
    scaled by `weight_scale` (1.0 for the primary 12th-lord check, 0.5 for
    the secondary 9th-lord corroboration)."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    lord = _house_of(house_lords, house_num)
    if not lord:
        return []

    placed_house = planet_house.get(lord, 0)
    dignities = _rich_planet_dignities(payload)
    dig = _dig_name(lord, dignities)
    strength = _house_lord_strength(payload, house_num)

    out: List[Dict[str, Any]] = []
    nb = _neecha_bhanga_status(payload, lord) if dig == "DEBILITATED" else {"cancelled": False, "reason": None}
    if dig == "DEBILITATED" and nb.get("cancelled"):
        out.append({
            "polarity": "POSITIVE",
            "weight": round(1.0 * weight_scale, 3),
            "note": (
                f"H{house_num} lord ({lord}) is DEBILITATED but Neecha Bhanga (debilitation-"
                f"cancellation) applies -- {nb.get('reason')} -> the foreign/cross-border "
                f"caution otherwise triggered by this debilitation is classically cancelled"
            ),
            "effect": "No foreign-business caution from this debilitation; classically cancelled.",
            "source": "foreign_business",
        })
    elif dig == "DEBILITATED" or (placed_house in _DUSTHANA and dig not in _STRONG_DIGNITY):
        weight = round(-2.0 * weight_scale, 3)
        if dig == "DEBILITATED":
            _reason = f"debilitated (dignity={dig})"
        else:
            _reason = f"placed in a dusthana house (H{placed_house or '?'}), dignity={dig} (not strong enough to offset the placement)"
        out.append({
            "polarity": "NEGATIVE",
            "weight": weight,
            "note": (
                f"H{house_num} lord ({lord}) {_reason} -> "
                f"caution specific to foreign/cross-border business ventures, not a "
                f"general chart negative"
            ),
            "effect": (
                "Caution indicated for cross-border/foreign-facing business specifically."
                if house_num == 12 else
                "Secondary caution note for long-distance/overseas business connections."
            ),
            "source": "foreign_business",
        })
    elif strength >= 0.6:
        weight = round((2.5 if house_num == 12 else 1.5) * weight_scale, 3)
        out.append({
            "polarity": "POSITIVE",
            "weight": weight,
            "note": (
                f"H{house_num} lord ({lord}) well placed/dignified (dignity={dig}, "
                f"placement house={placed_house or 'unknown'}) -> supports foreign/"
                f"cross-border business viability ({label})"
            ),
            "effect": (
                "Your chart shows supportive indications for foreign residence/dealings in business."
                if house_num == 12 else
                "Your chart shows supportive long-distance/overseas business connections."
            ),
            "source": "foreign_business",
        })
    return out


def _rahu_foreign_evidence(payload: Any) -> List[Dict[str, Any]]:
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    rahu_house = planet_house.get("Rahu", 0)
    if not rahu_house:
        return []

    dignities = _rich_planet_dignities(payload)
    dig = _dig_name("Rahu", dignities)
    out: List[Dict[str, Any]] = []

    if rahu_house in _BUSINESS_HOUSES and rahu_house in _FOREIGN_HOUSES:
        weight = round(3.5 * _dig_factor("Rahu", dignities), 3)
        out.append({
            "polarity": "POSITIVE",
            "weight": weight,
            "note": (
                f"Rahu placed in H{rahu_house} (business-relevant AND classically "
                f"foreign-connection house, dignity={dig}) -> a stronger-than-generic "
                f"foreign/cross-border business indicator"
            ),
            "effect": "Your chart shows a notable classical placement supporting foreign/cross-border trade.",
            "source": "foreign_business",
        })
    elif rahu_house in _FOREIGN_HOUSES:
        out.append({
            "polarity": "POSITIVE",
            "weight": 1.5,
            "note": (
                f"Rahu placed in H{rahu_house} (classically a foreign-connection house, "
                f"dignity={dig}) -> a modest foreign-business corroborating signal"
            ),
            "effect": "Your chart shows a mild supportive indication for cross-border dealings.",
            "source": "foreign_business",
        })

    # Rahu conjunct/aspecting the 9th or 12th lord (same-house conjunction,
    # or simple whole-sign 7th-house graha-drishti -- the same simplified
    # aspect convention used informally elsewhere in this package).
    for house_num in (9, 12):
        lord = _house_of(house_lords, house_num)
        if not lord or lord == "Rahu":
            continue
        lord_house = planet_house.get(lord, 0)
        if not lord_house:
            continue
        conjunct = lord_house == rahu_house
        aspecting = (((rahu_house - 1 + 6) % 12) + 1) == lord_house
        if conjunct or aspecting:
            relation = "conjunct" if conjunct else "aspecting (7th-house drishti)"
            out.append({
                "polarity": "POSITIVE",
                "weight": 2.0,
                "note": (
                    f"Rahu {relation} H{house_num} lord ({lord}) -> additional "
                    f"foreign-business combination worth citing"
                ),
                "effect": "Your chart shows an additional supportive combination for overseas business ties.",
                "source": "foreign_business",
            })
    return out


def _d4_house_lord_corroboration(payload: Any) -> List[Dict[str, Any]]:
    """v-audit fix (business realism, item 35 -- "foreign-business analysis
    lacks complete D4/location arbitration"): D4 (Chaturthamsha) sign-level
    corroboration for the D1 12th-house lord's foreign-business read above.

    D4 was previously not computed anywhere in this repo at all (see
    jyotish/astro.py::compute_d4_chaturthamsha_sign's own docstring --
    Vimshopaka Bala's weight table even lists a D4 coefficient that was
    explicitly never applied because D4 was never computed). This function
    is the FIRST D4 consumer in the codebase: it takes the D1 12th-house
    lord (already the primary indicator _lord_placement_evidence(...,12,...)
    above checks), looks up its D4 sign from payload.planets_d1 (sign +
    degree; the same field synastry.py's D7 corroboration reads), and
    checks its classical dignity IN THAT D4 SIGN via jyotish.dignity.
    dignity_state() -- the same five-fold dignity primitive used throughout
    this package, just applied to the D4 sign instead of D1.

    No D4 Lagna/house-occupancy graph is built here (NatalPayloadV2 has no
    lagna_degree field, the same documented limitation D2/D3/D7's in-house
    fallbacks already have -- see house_evidence.py's _d2_hora_positions_
    from_payload docstring) -- this is a single-planet SIGN-level dignity
    check only, not a full D4 house-graph corroboration the way D9/D10
    corroboration checks elsewhere in this package are. That is a real,
    disclosed scope limit, not silently glossed over.

    CAVEAT (disclosed at the call site, not just in this docstring): D4's
    core classical signification is fortune/fixed-assets/property; reading
    it for "foreign business/location arbitration" specifically is a MODERN
    EXTENSION some Jyotish authors and software make, not settled classical
    consensus the way D9/D10 varga-confirmation readings are. This is
    explicitly named a CORROBORATION (a modest supporting signal), never a
    controlling "arbitration" that overrides the D1 12th-lord/9th-lord/Rahu
    checks above -- weighted at HALF the primary 12th-lord check's own
    scale, the same secondary-weighting convention already used for the 9th
    lord above.

    Gracefully returns [] (not a penalty) when planets_d1 data for the 12th
    lord is unavailable -- most charts in this repo's test fixtures don't
    carry planets_d1 at all, so this degrades to "not evaluated" for them,
    exactly like D7's corroboration in synastry.py."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    lord = _house_of(house_lords, 12)
    if not lord:
        return []
    pdata = planets_d1.get(lord)
    if not pdata:
        return []
    sign = pdata.get("sign", "")
    degree = pdata.get("degree")
    if not sign or degree is None:
        return []

    try:
        from jyotish.astro import compute_d4_chaturthamsha_sign
        from jyotish.dignity import dignity_state
        d4_sign = compute_d4_chaturthamsha_sign(sign, float(degree))
        if not d4_sign:
            return []
        d4_dignity = dignity_state(lord, d4_sign)
    except Exception as exc:
        _record_diagnostic("foreign_business._d4_house_lord_corroboration", exc)
        return []

    out: List[Dict[str, Any]] = []
    if d4_dignity in ("EXALTED", "OWN_SIGN", "MOOLATRIKONA", "GREAT_FRIEND"):
        out.append({
            "polarity": "POSITIVE",
            "weight": 1.25,
            "note": (
                f"D4 (Chaturthamsha) corroboration: H12 lord ({lord}) is well-dignified "
                f"({d4_dignity}) in its D4 sign ({d4_sign}) -> a modest supporting signal "
                f"for the foreign-business/location question, on top of the D1 12th-lord "
                f"read above. NOTE: D4's use for foreign-business/location is a modern "
                f"extension of its core fortune/fixed-assets signification, not settled "
                f"classical consensus -- treated here as a secondary corroboration, not "
                f"an authoritative arbitration."
            ),
            "effect": "A secondary D4-level signal modestly supports the foreign-business question.",
            "source": "foreign_business_d4",
        })
    elif d4_dignity in ("DEBILITATED", "GREAT_ENEMY"):
        out.append({
            "polarity": "NEGATIVE",
            "weight": -1.0,
            "note": (
                f"D4 (Chaturthamsha) corroboration: H12 lord ({lord}) is poorly placed "
                f"({d4_dignity}) in its D4 sign ({d4_sign}) -> a modest caution signal "
                f"for the foreign-business/location question, on top of the D1 12th-lord "
                f"read above. NOTE: D4's use for foreign-business/location is a modern "
                f"extension of its core fortune/fixed-assets signification, not settled "
                f"classical consensus -- treated here as a secondary caution, not an "
                f"authoritative veto."
            ),
            "effect": "A secondary D4-level signal modestly cautions on the foreign-business question.",
            "source": "foreign_business_d4",
        })
    return out


def foreign_business_viability_evidence(payload: Any) -> List[Dict[str, Any]]:
    """Dedicated foreign/cross-border business viability check bundle.

    Returns a list of evidence dicts:
        {"polarity": "POSITIVE"|"NEGATIVE", "weight": float, "note": str,
         "effect": str, "source": "foreign_business"}

    Checks (see module docstring for classical basis/scope):
      1. 12th house lord strength/dignity (primary -- foreign residence/
         dealings house).
      2. 9th house lord strength/dignity (secondary, half-weighted --
         long-distance/foreign higher-learning corroboration).
      3. Rahu's house placement + dignity, with a bonus when Rahu sits in
         a house that is BOTH business-relevant and classically tied to
         foreign connections (7th/9th/12th), plus a separate citation
         when Rahu conjoins or aspects the 9th/12th lord.
      4. D4 (Chaturthamsha) sign-level corroboration of the 12th lord (see
         _d4_house_lord_corroboration's own docstring for the full scope/
         caveat disclosure -- a modest, secondary signal, disclosed as a
         modern extension rather than settled classical D4 doctrine, and
         gracefully absent whenever payload.planets_d1 data is unavailable).

    Never raises. Returns [] (not a penalty) when house_lords/planet_house
    data is unavailable or no notable foreign indicator is present --
    absence here means "no citation on file", matching the graceful-
    degradation convention used throughout this package.
    """
    try:
        evidence: List[Dict[str, Any]] = []
        evidence.extend(_lord_placement_evidence(payload, 12, "videsha/foreign residence house", 1.0))
        evidence.extend(_lord_placement_evidence(payload, 9, "long-distance/foreign-learning corroboration", 0.5))
        evidence.extend(_rahu_foreign_evidence(payload))
        evidence.extend(_d4_house_lord_corroboration(payload))
        return evidence
    except Exception as exc:
        _record_diagnostic("foreign_business.foreign_business_viability_evidence", exc)
        return []
