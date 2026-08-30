"""Business_Prediction/business_determination/nakshatra_business.py
=====================================================================
Janma Nakshatra (native's own BIRTH star -- the nakshatra the Moon
occupied at birth) business-aptitude corroboration.

This is deliberately SEPARATE from, and does not read or write, anything
in muhurta.py. muhurta.py's `_EVENT_FAVORABLE_NAKSHATRAS` table judges
candidate EVENT DATES (which nakshatra the Moon transits on a scanned
day, for choosing an auspicious launch/signing/opening date). This module
instead judges the native's own fixed NATAL chart: does this person's
Moon nakshatra at birth carry a classically-cited business/trade
aptitude reputation, independent of house placement, dasha, or any other
already-scored natal factor?

Classical basis (curated, NOT exhaustive -- see MATURITY_STATEMENT
elsewhere in this package for the same "one documented reading, not the
only one a traditional astrologer would accept" caveat). Only nakshatras
with a well-established, commonly-cited classical trade/business/
craft/leadership association are included below; nakshatras without a
clear, broadly-attested classical business reading are deliberately
OMITTED rather than guessed at (e.g. no attempt is made to force an
association for Krittika, Ardra, Jyeshtha, etc. -- omission here means
"no citation", not "unfavorable").

Weight scale
------------
This is a SECONDARY/supporting classical technique (nakshatra-phala
general-aptitude reputation), not a primary house-lord or dasha-level
determinant. Weights are deliberately modest (+1.0 to +2.0), well below
the +5.0-or-more range used for primary house-lord/dignity evidence in
house_evidence.py/significators.py, so this single technique cannot
disproportionately swing the overall business-promise score.

Payload field
-------------
Reads `payload.moon_nakshatra` (a plain string, e.g. "Pushya" -- see
jyotish/payload.py's NatalPayloadV2.moon_nakshatra field and
jyotish/engine_io.py's derivation of it from the Moon's natal sidereal
longitude). This is the NATAL Moon nakshatra, distinct from the
transit-date nakshatra muhurta.py computes per candidate day via
jyotish/panchang.py's compute_panchang().

Degrades gracefully (returns []) when moon_nakshatra is missing/blank or
not present in the curated table below -- never raises, never penalizes,
matching the diagnostic conventions used throughout this package (see
_d3_native_house_evidence()/_d7_native_house_evidence() in
house_evidence.py for the same "no evidence, not a penalty" contract).

Public API
----------
    janma_nakshatra_business_evidence(payload) -> List[Dict[str, Any]]
"""
from __future__ import annotations

from typing import Any, Dict, List
from .constants import _record_diagnostic

__all__ = [
    "janma_nakshatra_business_evidence", "NAKSHATRA_BUSINESS_TABLE",
    "janma_nakshatra_full_chain_evidence",
]


# Nakshatra -> {weight, effect (client-safe one-liner), detail (technical
# citation)}. Weight range intentionally kept to +1.0..+2.0 (see module
# docstring "Weight scale").
NAKSHATRA_BUSINESS_TABLE: Dict[str, Dict[str, Any]] = {
    "Pushya": {
        "weight": 2.0,
        "effect": "Your birth star (Pushya) is classically associated with strong trade/commerce aptitude.",
        "detail": (
            "Janma Nakshatra = Pushya. Widely regarded in classical nakshatra-phala "
            "literature as the most auspicious of the 27 nakshatras for nourishment "
            "and prosperity, and commonly cited as excellent for trade/commerce "
            "(consistent with Pushya's presence in muhurta.py's own favorable-"
            "nakshatra lists for business launches and contract signing)."
        ),
    },
    "Ashwini": {
        "weight": 1.5,
        "effect": "Your birth star (Ashwini) favors quick, pioneering, enterprising action in business.",
        "detail": (
            "Janma Nakshatra = Ashwini, ruled by the Ashwini Kumaras (swift healer/"
            "pioneer devatas). Classically associated with speed, initiative and "
            "pioneering new undertakings -- a commonly cited reading for quick, "
            "enterprising business action."
        ),
    },
    "Hasta": {
        "weight": 1.5,
        "effect": "Your birth star (Hasta) supports skilled craft/trade dexterity in business.",
        "detail": (
            "Janma Nakshatra = Hasta ('hand'), ruled by Savitar. Classically "
            "associated with manual/craft skill and dexterity, commonly cited for "
            "trade requiring precision and skilled handiwork (also present in "
            "muhurta.py's favorable-nakshatra lists for business events)."
        ),
    },
    "Swati": {
        "weight": 1.5,
        "effect": "Your birth star (Swati) is classically linked to independent trade and merchant activity.",
        "detail": (
            "Janma Nakshatra = Swati, ruled by Vayu (wind). Classically associated "
            "with independence and, in commonly cited nakshatra-phala readings, with "
            "merchant/trading activity (the 'trade winds' symbolism attached to this "
            "nakshatra in several published sources)."
        ),
    },
    "Chitra": {
        "weight": 1.0,
        "effect": "Your birth star (Chitra) supports design/creative business aptitude.",
        "detail": (
            "Janma Nakshatra = Chitra, ruled by Tvashtar/Vishwakarma (the celestial "
            "architect/craftsman). Classically associated with design, craftsmanship "
            "and creative-commercial aptitude."
        ),
    },
    "Vishakha": {
        "weight": 1.0,
        "effect": "Your birth star (Vishakha) supports determined, goal-driven effort in business.",
        "detail": (
            "Janma Nakshatra = Vishakha, ruled by Indra-Agni. Classically associated "
            "with focused, determined pursuit of goals -- commonly read as favoring "
            "sustained, goal-driven business effort."
        ),
    },
    "Magha": {
        "weight": 1.5,
        "effect": "Your birth star (Magha) favors an authority/leadership-oriented approach to business.",
        "detail": (
            "Janma Nakshatra = Magha, ruled by the Pitris (ancestors). Classically "
            "associated with authority, position, and leadership -- commonly read as "
            "favoring leadership-oriented business/enterprise roles."
        ),
    },
    "Anuradha": {
        "weight": 1.0,
        "effect": "Your birth star (Anuradha) supports partnership-oriented, organizational business skill.",
        "detail": (
            "Janma Nakshatra = Anuradha, ruled by Mitra (friendship/alliance). "
            "Classically associated with cooperative, organizational and "
            "partnership-building skill -- consistent with this nakshatra's "
            "inclusion among muhurta.py's favorable nakshatras for business "
            "launches and partnership registration (internal consistency, not "
            "independent corroboration)."
        ),
    },
}


def janma_nakshatra_business_evidence(payload: Any) -> List[Dict[str, Any]]:
    """Look up the native's Janma Nakshatra (birth Moon nakshatra) and
    return a modest-weighted evidence citation if it appears in the
    curated classical business/trade-aptitude table above.

    Returns a list of at most one dict:
        {"polarity": "POSITIVE", "weight": float, "note": str,
         "effect": str, "detail": str, "source": "janma_nakshatra_business"}

    "note"/"detail" are the same technical citation (kept both for
    convenience -- "note" matches significators.py's evidence-ledger key,
    "detail" matches this module's own effect/detail split); "effect" is
    the client-safe one-liner for report rendering.

    Gracefully returns [] (no crash, no evidence -- not a penalty) if:
      - payload has no moon_nakshatra attribute, or it is blank/None, or
      - the birth nakshatra is not in the curated table above (a
        deliberately narrow, well-established-only list; absence here
        means "no classical business citation on file", not
        "unfavorable").
    """
    try:
        moon_nak = getattr(payload, "moon_nakshatra", "") or ""
        if not isinstance(moon_nak, str):
            moon_nak = str(moon_nak)
        moon_nak = moon_nak.strip()
    except Exception as exc:
        _record_diagnostic("nakshatra_business.janma_nakshatra_business_evidence", exc)
        return []

    if not moon_nak:
        return []

    entry = NAKSHATRA_BUSINESS_TABLE.get(moon_nak)
    if not entry:
        return []

    weight = float(entry["weight"])
    return [{
        "polarity": "POSITIVE" if weight >= 0 else "NEGATIVE",
        "weight": round(weight, 3),
        "note": entry["detail"],
        "effect": entry["effect"],
        "detail": entry["detail"],
        "nakshatra": moon_nak,
        "source": "janma_nakshatra_business",
    }]


# ---------------------------------------------------------------------------
# Full nakshatra-vocational chain (audit item 6): extends the single Janma
# Nakshatra table-lookup above with the fuller classical nakshatra-lord
# chain a real reading would trace -- 10th-lord's nakshatra lord, the
# Amatyakaraka's (Jaimini professional-action karaka) nakshatra, the
# currently-running dasha lord's nakshatra/nakshatra-lord/house
# significations, and whether any of those chains terminates in a
# business-relevant house (2/3/6/7/10/11).
#
# Deliberately a SEPARATE function from janma_nakshatra_business_evidence()
# above (which stays exactly as-is, table-lookup-only, to keep its existing
# pinned test contract in test_nakshatra_business.py unchanged) -- this is
# additive, structural chain data, not another weighted evidence citation.
# Never raises; degrades field-by-field when a required payload attribute
# (house_lords, amatyakaraka, planet_nakshatras, planet_house, dasha_sequence,
# current_age) is missing, rather than failing the whole result.
# ---------------------------------------------------------------------------
from .constants import _record_diagnostic as _record_diag_chain  # noqa: F401 (reuse same helper)

# Short business-relevant house-signification blurbs, used only to label
# WHICH significations the terminal nakshatra-lord's house carries -- not a
# new scoring input, purely descriptive context for the chain output.
_HOUSE_SIGNIFICATIONS: Dict[int, str] = {
    1: "self, personality, physical vitality, overall life direction",
    2: "accumulated wealth, capital, family resources, speech/valuation",
    3: "self-effort, initiative, courage, marketing/communication, siblings",
    4: "fixed assets, property, vehicles, emotional foundation, education base",
    5: "strategy, creativity, speculation, intelligence, investments",
    6: "competition, service, debt, litigation, daily operations/staff",
    7: "partnerships, clients, contracts, public-facing trade/business",
    8: "transformation, crisis, hidden liabilities, insurance, research",
    9: "fortune, higher learning, long-distance/foreign trade, mentors",
    10: "livelihood, career, public standing, authority, execution",
    11: "gains, income, networks, fulfillment of goals, elder siblings",
    12: "expenditure, foreign connections, isolation, overseas operations",
}

# Houses this technique treats as "business-relevant" for the terminal-house
# flag -- mirrors the same 2/3/6/7/10/11 set used elsewhere in this package
# (capital, initiative, competition/operations, partnerships, livelihood,
# gains).
_RELEVANT_TERMINAL_HOUSES = frozenset({2, 3, 6, 7, 10, 11})

_NAKSHATRA_LORD_TABLE: Dict[str, str] = {
    "Ashwini": "Ketu", "Bharani": "Venus", "Krittika": "Sun", "Rohini": "Moon",
    "Mrigashira": "Mars", "Ardra": "Rahu", "Punarvasu": "Jupiter", "Pushya": "Saturn",
    "Ashlesha": "Mercury", "Magha": "Ketu", "Purva Phalguni": "Venus",
    "Uttara Phalguni": "Sun", "Hasta": "Moon", "Chitra": "Mars", "Swati": "Rahu",
    "Vishakha": "Jupiter", "Anuradha": "Saturn", "Jyeshtha": "Mercury", "Mula": "Ketu",
    "Purva Ashadha": "Venus", "Uttara Ashadha": "Sun", "Shravana": "Moon",
    "Dhanishta": "Mars", "Shatabhisha": "Rahu", "Purva Bhadrapada": "Jupiter",
    "Uttara Bhadrapada": "Saturn", "Revati": "Mercury",
}


def _nakshatra_lord_of(nakshatra: str) -> str:
    return _NAKSHATRA_LORD_TABLE.get(str(nakshatra or "").strip(), "")


def _house_of_planet(payload: Any, planet: str) -> int:
    if not planet:
        return 0
    planet_house = getattr(payload, "planet_house", {}) or {}
    try:
        h = planet_house.get(planet)
        return int(h) if h else 0
    except (TypeError, ValueError):
        return 0


def _current_dasha_lord(payload: Any) -> str:
    """Best-effort current Mahadasha lord: the dasha_sequence entry whose
    [start_age, end_age) window contains payload.current_age, falling back
    to the first sequence entry if no window matches (e.g. current_age
    missing/zero) or to payload.pratyantar_dasha_lord as a last resort."""
    dasha_sequence = getattr(payload, "dasha_sequence", None) or []
    current_age = getattr(payload, "current_age", None)
    if dasha_sequence and current_age is not None:
        try:
            current_age = float(current_age)
            for entry in dasha_sequence:
                start = entry.get("start_age")
                end = entry.get("end_age")
                if start is None:
                    continue
                start = float(start)
                if end is None or (start <= current_age < float(end)):
                    if end is None or current_age < float(end):
                        return str(entry.get("lord", "") or "")
        except (TypeError, ValueError):
            pass
    if dasha_sequence:
        return str(dasha_sequence[0].get("lord", "") or "")
    return str(getattr(payload, "pratyantar_dasha_lord", "") or "")


def janma_nakshatra_full_chain_evidence(payload: Any) -> Dict[str, Any]:
    """Extends the single Janma Nakshatra table-lookup with the fuller
    classical nakshatra-vocational chain:

      (a) tenth_lord_nakshatra_lord: the 10th house lord's own birth-star
          nakshatra, and that nakshatra's ruling planet.
      (b) amatyakaraka_nakshatra: the Jaimini Amatyakaraka's (professional-
          action karaka -- see jaimini.py) birth-star nakshatra.
      (c) dasha_lord_nakshatra_linkage: the currently-running Mahadasha
          lord's nakshatra, that nakshatra's ruling planet, and the house
          that ruling planet occupies (with a short signification blurb).
      (d) terminates_in_relevant_house: True if ANY of the three chains
          above resolves to a nakshatra-lord occupying a business-relevant
          house (2/3/6/7/10/11).

    Returns a dict (never a list -- this is structural chain data, not a
    weighted citation ledger entry). Never raises; missing payload
    attributes degrade individual sub-fields to "" / 0 / False rather than
    failing the whole result.
    """
    result: Dict[str, Any] = {
        "tenth_lord_nakshatra_lord": {},
        "amatyakaraka_nakshatra": {},
        "dasha_lord_nakshatra_linkage": {},
        "terminates_in_relevant_house": False,
        "terminal_houses_checked": sorted(_RELEVANT_TERMINAL_HOUSES),
    }
    try:
        house_lords = getattr(payload, "house_lords", {}) or {}
        planet_nakshatras = getattr(payload, "planet_nakshatras", {}) or {}
        terminal_hits: List[int] = []

        # (a) 10th lord's nakshatra lord.
        tenth_lord = house_lords.get("10", house_lords.get(10, ""))
        if tenth_lord:
            tenth_nak = planet_nakshatras.get(tenth_lord, "")
            tenth_nak_lord = _nakshatra_lord_of(tenth_nak)
            tenth_nak_lord_house = _house_of_planet(payload, tenth_nak_lord)
            result["tenth_lord_nakshatra_lord"] = {
                "tenth_lord": tenth_lord,
                "nakshatra": tenth_nak,
                "nakshatra_lord": tenth_nak_lord,
                "nakshatra_lord_house": tenth_nak_lord_house,
            }
            if tenth_nak_lord_house in _RELEVANT_TERMINAL_HOUSES:
                terminal_hits.append(tenth_nak_lord_house)

        # (b) Amatyakaraka's nakshatra (reused from payload.amatyakaraka /
        # jaimini.py -- not recomputed here).
        amatyakaraka = str(getattr(payload, "amatyakaraka", "") or "")
        if amatyakaraka:
            amk_nak = planet_nakshatras.get(amatyakaraka, "")
            amk_nak_lord = _nakshatra_lord_of(amk_nak)
            amk_nak_lord_house = _house_of_planet(payload, amk_nak_lord)
            result["amatyakaraka_nakshatra"] = {
                "amatyakaraka": amatyakaraka,
                "nakshatra": amk_nak,
                "nakshatra_lord": amk_nak_lord,
                "nakshatra_lord_house": amk_nak_lord_house,
            }
            if amk_nak_lord_house in _RELEVANT_TERMINAL_HOUSES:
                terminal_hits.append(amk_nak_lord_house)

        # (c) Dasha-lord/nakshatra linkage: currently-running dasha lord's
        # nakshatra, that nakshatra's lord, and that lord's house
        # significations.
        dasha_lord = _current_dasha_lord(payload)
        if dasha_lord:
            dasha_nak = planet_nakshatras.get(dasha_lord, "")
            dasha_nak_lord = _nakshatra_lord_of(dasha_nak)
            dasha_nak_lord_house = _house_of_planet(payload, dasha_nak_lord)
            result["dasha_lord_nakshatra_linkage"] = {
                "dasha_lord": dasha_lord,
                "dasha_lord_nakshatra": dasha_nak,
                "nakshatra_lord": dasha_nak_lord,
                "nakshatra_lord_house": dasha_nak_lord_house,
                "nakshatra_lord_house_significations": _HOUSE_SIGNIFICATIONS.get(dasha_nak_lord_house, ""),
            }
            if dasha_nak_lord_house in _RELEVANT_TERMINAL_HOUSES:
                terminal_hits.append(dasha_nak_lord_house)

        result["terminates_in_relevant_house"] = bool(terminal_hits)
        result["terminal_house_hits"] = sorted(set(terminal_hits))
        return result
    except Exception as exc:  # pragma: no cover - defensive
        _record_diag_chain("nakshatra_business.janma_nakshatra_full_chain_evidence", exc)
        return result
