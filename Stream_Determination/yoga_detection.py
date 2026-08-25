"""yoga_detection.py -- Round 4 addition (2026-08-22): classical yoga-pattern
detection, flagged as absent across all four audit rounds.

Detects five classical yoga patterns from chart_data (the same `payload`
object threaded through stream_scoring.py -- see that module's own
`getattr(payload, ...)` usage for the attribute names this module reuses:
`planet_house`, `house_lords`, `planets_d1`, `true_planet_dignities`,
`combust_planets`, `eff_strengths`, `lagna_sign`).

Every detector returns a structured dict:
    {
        "yoga_name": str,
        "present": bool,
        "strength": float,          # 0.0-1.0
        "contributing_planets": List[str],
        "classical_citation": str,
        "precision": "precise" | "coarse",
        "notes": str,                # human-readable detail, informational
    }

Design principles (matching this codebase's existing disclosure discipline --
see subject_registry.py / stream_scoring.py's own provenance comments):

- Every result is computed from real chart_data fields actually present on
  the payload; nothing here is stubbed, randomized, or hardcoded to "present".
  A detector whose required data is missing returns present=False, strength
  0.0, and a note saying data was unavailable -- never a fabricated result.
- "precision" states plainly whether the classical formulation was checked at
  degree-level tightness (precise) or only at whole-sign/whole-house
  resolution (coarse) -- see each detector's own docstring for why.
- This module does NOT re-implement dignity/aspect/house-lordship logic --
  it reuses jyotish.astro's `_get_planetary_aspects` (same whole-sign
  Parashari aspect convention already used by
  `_naisargika_karaka_strength_bonus` in stream_scoring.py) and this
  package's own STREAM_META house/planet conventions. Sign-lord lookups use
  `jyotish.constants._SIGN_LORD`, the same table stream_scoring.py already
  imports.
- This module does NOT decide how much a detected yoga should move a
  stream's score -- that bounded, capped, exclusivity-routed integration
  lives in stream_scoring.py (see `_YOGA_STREAM_WEIGHTS` /
  `_yoga_pattern_bonus` there), following the same separation-of-concerns
  already used for `_naisargika_karaka_strength_bonus`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from jyotish.astro import _get_planetary_aspects
from jyotish.constants import _SIGN_LORD

from .subject_registry import STREAM_SCIENCE, STREAM_COMMERCE, STREAM_HUMANITIES

_KENDRA_HOUSES = (1, 4, 7, 10)
_TRIKONA_HOUSES = (1, 5, 9)

# Classical natural-friendship table (Naisargika Maitri), mirrored from
# jyotish/astro.py's `_detect_planetary_war._NATURAL_FRIENDS` -- that table
# is defined local to a function there (not importable), so it is reproduced
# here verbatim rather than re-derived, to avoid a second, possibly-drifting
# copy of the *rules* while still keeping this module import-independent of
# that function's internals. Sun/Moon/Rahu/Ketu are naturally friend/neutral/
# enemy per BPHS Ch 4 but are not needed by the yoga checks below (which only
# ever test Jupiter's friendliness toward a sign's lord), so only the five
# classical grahas relevant here are included.
_NATURAL_FRIENDS: Dict[str, List[str]] = {
    "Mars": ["Sun", "Moon", "Jupiter"],
    "Mercury": ["Sun", "Venus"],
    "Jupiter": ["Sun", "Moon", "Mars"],
    "Venus": ["Mercury", "Saturn"],
    "Saturn": ["Mercury", "Venus"],
}

_OWN_OR_BETTER_DIGNITIES = ("EXALTED", "MOOLATRIKONA", "OWN", "OWN_SIGN")


def _planet_house(chart_data: Any) -> Dict[str, int]:
    return getattr(chart_data, "planet_house", {}) or {}


def _house_lords(chart_data: Any) -> Dict[str, str]:
    return getattr(chart_data, "house_lords", {}) or {}


def _planets_d1(chart_data: Any) -> Dict[str, Any]:
    return getattr(chart_data, "planets_d1", {}) or {}


def _true_dignities(chart_data: Any) -> Dict[str, str]:
    return getattr(chart_data, "true_planet_dignities", {}) or {}


def _combust(chart_data: Any) -> set:
    return set(getattr(chart_data, "combust_planets", []) or [])


def _sign_of(chart_data: Any, planet: str) -> Optional[str]:
    info = _planets_d1(chart_data).get(planet)
    if not info:
        return None
    return info.get("sign")


def _degree_of(chart_data: Any, planet: str) -> Optional[float]:
    info = _planets_d1(chart_data).get(planet)
    if not info:
        return None
    deg = info.get("degree")
    try:
        return float(deg) if deg is not None else None
    except (TypeError, ValueError):
        return None


def _mutually_aspecting(chart_data: Any, a: str, b: str) -> bool:
    """Whole-sign Parashari aspect check, either direction -- reuses the
    same `_get_planetary_aspects` helper `_naisargika_karaka_strength_bonus`
    already uses in stream_scoring.py, not a re-derivation."""
    ph = _planet_house(chart_data)
    if a not in ph or b not in ph:
        return False
    try:
        aspects = _get_planetary_aspects(ph)
    except Exception:
        return False
    return ph[b] in aspects.get(a, []) or ph[a] in aspects.get(b, [])


def _is_own_exalt_or_friendly_sign(planet: str, sign: Optional[str]) -> bool:
    """Own/exaltation sign is read from _SIGN_LORD (planet rules its own
    sign) plus a direct check; friendly-sign is via the classical natural-
    friendship table above (planet is friendly toward the occupied sign's
    lord). This is a coarse, sign-only friendliness check (Naisargika
    Maitri only) -- it deliberately does not compute the fuller five-fold
    (Panchadha Maitri) temporal+natural relationship, which needs a
    house-position-at-birth model this module does not have independent
    access to."""
    if not sign:
        return False
    sign_lord = _SIGN_LORD.get(sign)
    if sign_lord == planet:
        return True  # own sign
    if sign_lord and sign_lord in _NATURAL_FRIENDS.get(planet, []):
        return True  # friendly sign
    return False


def _empty_result(name: str, citation: str, precision: str, note: str) -> Dict[str, Any]:
    return {
        "yoga_name": name,
        "present": False,
        "strength": 0.0,
        "contributing_planets": [],
        "classical_citation": citation,
        "precision": precision,
        "notes": note,
    }


# ---------------------------------------------------------------------------
# 1. Budha-Aditya Yoga
# ---------------------------------------------------------------------------

_BUDHA_ADITYA_CITATION = (
    "BPHS Ch. 36 (Rajayoga Adhyaya) / Phaladeepika Ch. 6 -- Mercury-Sun "
    "conjunction: sharp intellect, analytical ability, scholarly aptitude."
)


def detect_budha_aditya_yoga(chart_data: Any) -> Dict[str, Any]:
    """Mercury and Sun conjunct in the same house/sign.

    Strength scales with tightness of conjunction (tighter degree separation
    = stronger) when both planets' degrees are available (precision=
    "precise"); otherwise falls back to a flat, conservative boolean-derived
    strength (precision="coarse") -- same house/sign occupancy only, no
    tightness information.

    Does NOT re-penalize combustion (already handled by
    `_naisargika_karaka_strength_bonus` in stream_scoring.py) -- a tight
    conjunction that would classically also imply Mercury combustion is
    only NOTED (informational), not double-penalized here.
    """
    ph = _planet_house(chart_data)
    merc_house = ph.get("Mercury")
    sun_house = ph.get("Sun")
    if merc_house is None or sun_house is None or merc_house != sun_house:
        return _empty_result(
            "Budha-Aditya Yoga", _BUDHA_ADITYA_CITATION, "coarse",
            "Mercury/Sun house data unavailable or not conjunct -- yoga not present.",
        )

    merc_deg = _degree_of(chart_data, "Mercury")
    sun_deg = _degree_of(chart_data, "Sun")
    tight_combust_note = ""
    if merc_deg is not None and sun_deg is not None:
        orb = abs(merc_deg - sun_deg)
        orb = min(orb, 30.0 - orb) if orb > 15.0 else orb  # same-sign only, so no wraparound beyond 30
        # Tighter orb -> stronger yoga. 0deg orb -> strength 1.0; >=12deg orb
        # (loose but still same-sign conjunction) -> floor of 0.4.
        strength = max(0.4, 1.0 - (orb / 12.0) * 0.6)
        precision = "precise"
        if orb < 14.0:  # commonly-cited Mercury combustion orb (non-retrograde)
            tight_combust_note = (
                f" This conjunction (orb {orb:.1f} deg) is tight enough to also imply "
                "Mercury combustion classically -- that affliction is scored separately "
                "by stream_scoring.py's _naisargika_karaka_strength_bonus; this yoga "
                "detector does not apply that penalty again (informational only)."
            )
    else:
        strength = 0.7
        precision = "coarse"
        tight_combust_note = " (No degree data available -- tightness/combustion implication cannot be assessed.)"

    return {
        "yoga_name": "Budha-Aditya Yoga",
        "present": True,
        "strength": round(strength, 3),
        "contributing_planets": ["Mercury", "Sun"],
        "classical_citation": _BUDHA_ADITYA_CITATION,
        "precision": precision,
        "notes": f"Mercury and Sun conjunct in house {merc_house}." + tight_combust_note,
    }


# ---------------------------------------------------------------------------
# 2. Saraswati Yoga
# ---------------------------------------------------------------------------

_SARASWATI_CITATION = (
    "Compiled classical formulation (Phaladeepika/Saravali-adjacent): "
    "Jupiter own/exalted/friendly sign, associated with Mercury and Venus, "
    "with kendra/trikona placement -- eloquence, learning, arts, wisdom."
)


def detect_saraswati_yoga(chart_data: Any) -> Dict[str, Any]:
    """Jupiter in own/exaltation/friendly sign, associated (conjunct or
    mutually aspecting) with BOTH Mercury and Venus, AND at least one of
    Jupiter/Mercury/Venus in a kendra (1/4/7/10) or trikona (1/5/9) from
    lagna.

    This is a compiled, commonly-cited popular formulation rather than a
    single-verse BPHS citation (documented explicitly, per this codebase's
    disclosure convention -- see subject_registry.py's own (A) CLASSICAL /
    (B) ENGINEERED provenance note). precision is "coarse": association is
    checked at whole-sign conjunction/aspect resolution, not degree-level
    orb tightness.
    """
    ph = _planet_house(chart_data)
    dignities = _true_dignities(chart_data)
    jup_house = ph.get("Jupiter")
    if jup_house is None:
        return _empty_result(
            "Saraswati Yoga", _SARASWATI_CITATION, "coarse",
            "Jupiter house placement unavailable -- yoga not present.",
        )

    jup_sign = _sign_of(chart_data, "Jupiter")
    jup_dignity_ok = dignities.get("Jupiter") in _OWN_OR_BETTER_DIGNITIES or _is_own_exalt_or_friendly_sign(
        "Jupiter", jup_sign
    )

    def _associated(other: str) -> bool:
        other_house = ph.get(other)
        if other_house is None:
            return False
        if other_house == jup_house:
            return True
        return _mutually_aspecting(chart_data, "Jupiter", other)

    merc_assoc = _associated("Mercury")
    ven_assoc = _associated("Venus")

    kendra_trikona_hit = None
    for p in ("Jupiter", "Mercury", "Venus"):
        h = ph.get(p)
        if h in _KENDRA_HOUSES or h in _TRIKONA_HOUSES:
            kendra_trikona_hit = p
            break

    present = jup_dignity_ok and merc_assoc and ven_assoc and kendra_trikona_hit is not None
    if not present:
        missing = []
        if not jup_dignity_ok:
            missing.append("Jupiter not in own/exaltation/friendly sign")
        if not merc_assoc:
            missing.append("Mercury not conjunct/aspecting Jupiter")
        if not ven_assoc:
            missing.append("Venus not conjunct/aspecting Jupiter")
        if kendra_trikona_hit is None:
            missing.append("none of Jupiter/Mercury/Venus in kendra/trikona from lagna")
        return _empty_result(
            "Saraswati Yoga", _SARASWATI_CITATION, "coarse",
            "Conditions not met: " + "; ".join(missing) + ".",
        )

    # Strength: three roughly equal sub-conditions (dignity, dual
    # association, kendra/trikona placement) each contribute up to 1/3;
    # dual association itself scales slightly by whether it's conjunction
    # (stronger) vs. aspect-only for each of Mercury/Venus.
    assoc_quality = 0.0
    for other in ("Mercury", "Venus"):
        assoc_quality += 0.5 if ph.get(other) == jup_house else 0.35
    strength = min(1.0, (1.0 / 3.0) + (assoc_quality / 2.0) * (1.0 / 3.0) * 2 + (1.0 / 3.0))
    strength = round(min(1.0, max(0.5, strength)), 3)

    return {
        "yoga_name": "Saraswati Yoga",
        "present": True,
        "strength": strength,
        "contributing_planets": ["Jupiter", "Mercury", "Venus"],
        "classical_citation": _SARASWATI_CITATION,
        "precision": "coarse",
        "notes": (
            f"Jupiter dignified/friendly in {jup_sign or 'unknown sign'}, associated with "
            f"Mercury and Venus, with {kendra_trikona_hit} in kendra/trikona from lagna."
        ),
    }


# ---------------------------------------------------------------------------
# 3. Dharma-Karmadhipati Yoga
# ---------------------------------------------------------------------------

_DHARMA_KARMADHIPATI_CITATION = (
    "BPHS Ch. 39 (Raja Yoga Adhyaya) -- 9th (dharma) and 10th (karma) lords "
    "in conjunction/mutual aspect/parivartana: fortune combining with vocation."
)

# Weight of relevance per stream, used only by stream_scoring.py's
# integration (kept here as the natural home for this yoga's own mapping
# since it directly follows from which lord's significations align with
# which stream -- 10th (career/vocation) is most Commerce-relevant, 9th
# (dharma/higher learning) is most Humanities-relevant per STREAM_META's own
# H9 weight of 1.00 there, and Science gets a modest share since 9th/10th
# both sit in its own house list too (at lower weight than Humanities/
# Commerce -- see subject_registry.py's STREAM_META).
DHARMA_KARMADHIPATI_STREAM_WEIGHTS: Dict[str, float] = {
    STREAM_HUMANITIES: 1.0,
    STREAM_COMMERCE: 0.8,
    STREAM_SCIENCE: 0.4,
}


def _parivartana(chart_data: Any, planet_a: str, planet_b: str) -> bool:
    """Sign exchange: planet_a sits in a sign planet_b rules, and vice versa."""
    sign_a = _sign_of(chart_data, planet_a)
    sign_b = _sign_of(chart_data, planet_b)
    if not sign_a or not sign_b:
        return False
    return _SIGN_LORD.get(sign_a) == planet_b and _SIGN_LORD.get(sign_b) == planet_a


def _lord_yoga(
    chart_data: Any, house_a: str, house_b: str, yoga_name: str, citation: str,
) -> Dict[str, Any]:
    """Shared conjunction/aspect/parivartana check between two house lords
    (used by both Dharma-Karmadhipati (9th/10th) and Dhana Yoga (2nd/11th) --
    same classical pattern, different houses)."""
    lords = _house_lords(chart_data)
    lord_a = lords.get(house_a)
    lord_b = lords.get(house_b)
    if not lord_a or not lord_b:
        return _empty_result(
            yoga_name, citation, "coarse",
            f"House {house_a}/{house_b} lord data unavailable -- yoga not present.",
        )
    if lord_a == lord_b:
        # Same planet rules both houses -- classically this is itself a
        # strong (if degenerate) form of the yoga: one planet directly
        # controls both significations.
        return {
            "yoga_name": yoga_name,
            "present": True,
            "strength": 0.85,
            "contributing_planets": [lord_a],
            "classical_citation": citation,
            "precision": "coarse",
            "notes": f"Single planet ({lord_a}) rules both house {house_a} and house {house_b}.",
        }

    ph = _planet_house(chart_data)
    house_a_num = ph.get(lord_a)
    house_b_num = ph.get(lord_b)
    conjunct = house_a_num is not None and house_a_num == house_b_num
    exchange = _parivartana(chart_data, lord_a, lord_b)
    aspecting = _mutually_aspecting(chart_data, lord_a, lord_b)

    if not (conjunct or exchange or aspecting):
        return _empty_result(
            yoga_name, citation, "coarse",
            f"House {house_a} lord ({lord_a}) and house {house_b} lord ({lord_b}) "
            "are neither conjunct, exchanged, nor mutually aspecting -- yoga not present.",
        )

    if exchange:
        strength, kind = 0.9, "sign-exchange (parivartana)"
    elif conjunct:
        strength, kind = 1.0, "conjunction"
    else:
        strength, kind = 0.6, "mutual aspect"

    return {
        "yoga_name": yoga_name,
        "present": True,
        "strength": strength,
        "contributing_planets": [lord_a, lord_b],
        "classical_citation": citation,
        "precision": "coarse",
        "notes": (
            f"House {house_a} lord ({lord_a}) and house {house_b} lord ({lord_b}) "
            f"connected via {kind}."
        ),
    }


def detect_dharma_karmadhipati_yoga(chart_data: Any) -> Dict[str, Any]:
    """9th lord and 10th lord: conjunction, mutual aspect, or parivartana."""
    return _lord_yoga(chart_data, "9", "10", "Dharma-Karmadhipati Yoga", _DHARMA_KARMADHIPATI_CITATION)


# ---------------------------------------------------------------------------
# 4. Gaja-Kesari Yoga
# ---------------------------------------------------------------------------

_GAJA_KESARI_CITATION = (
    "BPHS Ch. 36 -- Moon and Jupiter in mutual kendra (1/4/7/10 from each "
    "other): wisdom, respect, good fortune in learning."
)


def detect_gaja_kesari_yoga(chart_data: Any) -> Dict[str, Any]:
    """Moon and Jupiter in mutual kendra from each other.

    The classical criterion itself is house-distance-based (not a degree-
    orb concept), so this detector is genuinely precision="precise" once
    house placements are known -- unlike Budha-Aditya/Saraswati, there is no
    finer-grained classical version this is a coarse stand-in for.
    Strength is reduced (not zeroed -- the yoga's placement condition is
    still classically satisfied) when either planet is combust/uncancelled-
    debilitated, since an afflicted karaka weakens the yoga's practical
    expression even though the positional yoga itself still holds.
    """
    ph = _planet_house(chart_data)
    moon_house = ph.get("Moon")
    jup_house = ph.get("Jupiter")
    if moon_house is None or jup_house is None:
        return _empty_result(
            "Gaja-Kesari Yoga", _GAJA_KESARI_CITATION, "precise",
            "Moon/Jupiter house data unavailable -- yoga not present.",
        )

    distance = (jup_house - moon_house) % 12
    is_kendra = distance in (0, 3, 6, 9)  # 1st/4th/7th/10th from each other
    if not is_kendra:
        return _empty_result(
            "Gaja-Kesari Yoga", _GAJA_KESARI_CITATION, "precise",
            f"Moon (house {moon_house}) and Jupiter (house {jup_house}) are not in "
            "mutual kendra -- yoga not present.",
        )

    strength = 1.0
    dignities = _true_dignities(chart_data)
    combust = _combust(chart_data)
    eff_strengths = getattr(chart_data, "eff_strengths", {}) or {}
    affliction_notes = []
    for p in ("Moon", "Jupiter"):
        afflicted = False
        if p in combust:
            afflicted = True
            affliction_notes.append(f"{p} combust")
        eff = eff_strengths.get(p)
        deb = dignities.get(p) == "DEBILITATED"
        try:
            eff_ok = eff is not None and float(eff) <= 1.0
        except (TypeError, ValueError):
            eff_ok = False
        if deb and (eff_ok or eff is None):
            afflicted = True
            affliction_notes.append(f"{p} debilitated (uncancelled)")
        if afflicted:
            strength -= 0.25

    strength = round(max(0.3, strength), 3)

    return {
        "yoga_name": "Gaja-Kesari Yoga",
        "present": True,
        "strength": strength,
        "contributing_planets": ["Moon", "Jupiter"],
        "classical_citation": _GAJA_KESARI_CITATION,
        "precision": "precise",
        "notes": (
            f"Moon (house {moon_house}) and Jupiter (house {jup_house}) in mutual kendra."
            + (f" Affliction reduces expression strength: {', '.join(affliction_notes)}."
               if affliction_notes else "")
        ),
    }


# ---------------------------------------------------------------------------
# 5. Dhana Yoga (commerce-relevant)
# ---------------------------------------------------------------------------

_DHANA_YOGA_CITATION = (
    "BPHS Ch. 39 -- 2nd (dhana) and 11th (labha) lords in conjunction/"
    "mutual aspect/parivartana: wealth-accumulation aptitude."
)


def detect_dhana_yoga(chart_data: Any) -> Dict[str, Any]:
    """2nd lord and 11th lord: conjunction, mutual aspect, or parivartana."""
    return _lord_yoga(chart_data, "2", "11", "Dhana Yoga", _DHANA_YOGA_CITATION)


# ---------------------------------------------------------------------------
# Aggregate entry point
# ---------------------------------------------------------------------------

_ALL_DETECTORS = (
    detect_budha_aditya_yoga,
    detect_saraswati_yoga,
    detect_dharma_karmadhipati_yoga,
    detect_gaja_kesari_yoga,
    detect_dhana_yoga,
)


def detect_all_yogas(chart_data: Any) -> Dict[str, Dict[str, Any]]:
    """Run every detector against chart_data, keyed by yoga_name.

    Never raises: an individual detector's failure (e.g. an unexpected
    chart_data shape) degrades to a not-present result for that yoga only,
    rather than aborting the whole scoring pass -- consistent with this
    codebase's "missing data degrades gracefully" convention (see
    `_naisargika_karaka_strength_bonus`'s own docstring).
    """
    results: Dict[str, Dict[str, Any]] = {}
    for detector in _ALL_DETECTORS:
        try:
            result = detector(chart_data)
        except Exception as exc:  # pragma: no cover -- defensive only
            result = {
                "yoga_name": detector.__name__,
                "present": False,
                "strength": 0.0,
                "contributing_planets": [],
                "classical_citation": "",
                "precision": "coarse",
                "notes": f"Detection failed on this chart_data shape ({exc!r}) -- treated as not present.",
            }
        results[result["yoga_name"]] = result
    return results


# Which stream(s) each yoga is relevant to, and at what relative weight
# (1.0 = full relevance). Used by stream_scoring.py's integration; kept
# here alongside the detectors themselves since the mapping follows directly
# from each yoga's own classical significations (see each detector's
# docstring/citation).
YOGA_STREAM_RELEVANCE: Dict[str, Dict[str, float]] = {
    "Budha-Aditya Yoga": {
        STREAM_SCIENCE: 1.0,
        STREAM_COMMERCE: 0.7,
        STREAM_HUMANITIES: 0.3,
    },
    "Saraswati Yoga": {
        STREAM_HUMANITIES: 1.0,
        STREAM_SCIENCE: 0.2,
        STREAM_COMMERCE: 0.1,
    },
    "Dharma-Karmadhipati Yoga": DHARMA_KARMADHIPATI_STREAM_WEIGHTS,
    "Gaja-Kesari Yoga": {
        STREAM_HUMANITIES: 1.0,
        STREAM_SCIENCE: 0.3,
        STREAM_COMMERCE: 0.2,
    },
    "Dhana Yoga": {
        STREAM_COMMERCE: 1.0,
    },
}
