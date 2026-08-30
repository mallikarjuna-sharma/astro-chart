"""
Business_Prediction/business_engine.py
=======================================
Business/entrepreneurship prediction engine for JyotishAI.

MATURITY STATEMENT (read this before treating any output as authoritative):

    Architecturally mature and internally validated: implementation rules,
    invariants, regression behavior, and end-to-end execution are tested.
    Real-world predictive validity has NOT been established, because no
    prospective labeled outcome corpus has been evaluated. Astrological
    precedence and conflict resolution remain explicit engineered
    interpretations, not uniquely authoritative classical doctrine.

Concretely, keep these distinctions in mind whenever reading this module's
output or test suite:

  - Tests validate implementation -- not predictions. A green test suite
    proves the code executes its own intended rules; it does not prove
    those rules are astrologically complete or empirically accurate.
  - Synthetic data (Business_Prediction/synthetic_calibration_seed.py)
    validates the CALIBRATION PIPELINE -- not the model. It proves
    validate_outcomes()/score_calibration() work end-to-end on fabricated
    rows; it says nothing about this engine's real predictive accuracy.
  - Classical coverage does not imply classical consensus. Where this
    module cites a classical method (Phaladeepika ch.5, Viparita Raja
    Yoga, KP significators, Jaimini karakas), it implements ONE documented
    reading of that method, not the only one a traditional astrologer
    would accept, and it does not yet handle every rare yoga, cancellation
    condition, or conflicting-yoga interaction a full classical review
    would consider.
  - "Heuristic tier" (HIGH/MODERATE/LOW) is not statistical confidence.
    It is a deterministic threshold on two already-computed scores, not a
    measured probability or a claim backed by a labeled outcome corpus.
  - Outputs are decision-support narratives, not financial forecasts. They
    exist to prompt further astrological review and human judgment, not to
    be acted on as investment or career advice.

This module has NOT been empirically calibrated against dated business
outcomes (see CALIBRATION_STATUS / Business_Prediction/calibration.py).
Every score below is a rule-weighted, dignity-gated, multi-varga-
corroborated heuristic -- extensively tested for internal consistency, not
validated against real-world outcomes. See `model_status` /
`evidence_basis` / `calibration_status` / `maturity_statement` in every
returned dict for a machine-readable statement of these limits.

Mirrors the layered pipeline used across the engine (Stream_Determination /
Field_Determination / Job_Career): a shared NatalPayloadV2 chart object is
scored by domain-specific layers that reuse, wherever possible, primitives
that already exist elsewhere in the repo rather than re-deriving them:

  Layer 1 — Viability gate
      compute_business_mode_gate(payload) (this module) computes signed,
      dignity-gated, D9/D10-corroborated employment/business/independent/
      family_business scores -- the same evidence policy as Layer 2 below,
      not the older jyotish.employment_mode.compute_employment_mode(),
      which used several unconditional/ungated rules (Rahu-in-H7, DK in
      any kendra/trikona, independent Mercury+Venus placement, empty-H7 as
      positive evidence) and had no negative ledger or varga corroboration.
      Its business_score / independent_score / family_biz_score gate
      whether business-track analysis should be surfaced for this chart,
      and compute_business_prediction() additionally requires the
      venture-type score to beat employment_score by a minimum margin
      before "proceed" is set (comparative advantage, not just absolute
      viability).

  Layer 2 — House/planet business-strength significators
      Business-specific (H2/H3/H6/H7/H9/H10/H11/H12 + planetary roles),
      now with dignity-gated exceptions (Viparita Raja Yoga case for
      dusthana lords, debilitation checks before "fortune supports"
      claims) instead of unconditional signal-sum rules. Produces a
      positive/negative evidence ledger, not a single opaque number.

  Layer 3 — Sector/domain scoring
      Blends three components per sector, all three actually reading the
      registry's declared `core_houses` / `core_planets` (previously only
      the generic archetype vector was used and core_houses/core_planets
      were declared but dead):
        (a) generic archetype vector (jyotish.d10_archetypes math, general
            aptitude signature, not sector-specific)
        (b) core_houses strength: lordship placement + dignity of each
            house the registry declares for that sector
        (c) core_planets strength: dignity + placement of each planet the
            registry declares as a driver for that sector

  Layer 4 — Timed windows, bounded forecast horizon
      Reuses Job_Career.timeline._dasha_calendar (MD/AD calendar
      expansion), bounded to an explicit forecast window (default: today
      .. +years_ahead) instead of the chart owner's full lifetime. Each AD
      window gets a signed net evidence score (dignity, dusthana
      lordship/VRY exception, corroboration between MD and AD) and a
      single dominant label instead of independently-fireable, possibly
      contradictory tags.

Public API
----------
    compute_business_prediction(payload, venture_type="business",
                                 years_ahead=15) -> dict
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

from jyotish.d10_archetypes import (
    PLANET_ARCHETYPES,
    ARCHETYPE_NAMES,
    DIGNITY,
    scale_raw_support,
)


"""business_determination.operating_models

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .house_evidence import _UPACHAYA, _d10_native_house_evidence, _fifth_house_business_evidence, _house_lord_strength
from .jaimini import _dig_name
from .d24_d60_sign import _DUSTHANA, _KT, _STRONG_DIGNITY, _effective_benefic_malefic_sets


def _business_operating_model(payload: Any) -> Dict[str, Any]:
    """v17 audit fix: the engine determined MODE (employment/business/
    independent/family) and SECTOR (industry), but never operating
    STRUCTURE -- sole owner vs partnership vs family business vs
    professional practice vs trading/brokerage vs manufacturing vs
    scalable platform, per the spec's section 11 needs-lists. Builds one
    score per model from the same house-lord-strength primitives already
    used throughout this module, then returns a RELATIVE ranking (each
    model normalized against this chart's own top scorer) -- this is a
    within-chart comparison, not a cross-chart absolute scale."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = getattr(payload, "planet_dignities", {}) or {}

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    h2_lord, h4_lord = _h(2), _h(4)
    h7_lord, h9_lord = _h(7), _h(9)
    h10_lord, h11_lord = _h(10), _h(11)
    h12_lord = _h(12)

    lagna_strength = _house_lord_strength(payload, 1)
    h2_strength = _house_lord_strength(payload, 2) if h2_lord else 0.0
    h3_strength = _house_lord_strength(payload, 3)
    h4_strength = _house_lord_strength(payload, 4) if h4_lord else 0.0
    h7_strength = _house_lord_strength(payload, 7) if h7_lord else 0.0
    h9_strength = _house_lord_strength(payload, 9) if h9_lord else 0.0
    h10_strength = _house_lord_strength(payload, 10) if h10_lord else 0.0
    h11_strength = _house_lord_strength(payload, 11) if h11_lord else 0.0
    h12_strength = _house_lord_strength(payload, 12) if h12_lord else 0.0

    h7_afflicted = False
    if h7_lord:
        h7_house = _ph(h7_lord)
        co = [p for p, h in planet_house.items() if h == h7_house and p != h7_lord]
        _, malefics = _effective_benefic_malefic_sets(payload)
        h7_afflicted = bool(set(co) & malefics)

    mercury_dig = _dig_name("Mercury", dignities)
    moon_dig = _dig_name("Moon", dignities)
    mars_dig = _dig_name("Mars", dignities)
    sat_dig = _dig_name("Saturn", dignities)
    mercury_h, sat_h, rahu_h = _ph("Mercury"), _ph("Saturn"), _ph("Rahu")

    h5_net = sum(w for w, _ in _fifth_house_business_evidence(payload))

    scores: Dict[str, float] = {
        "sole_owner": 20 * lagna_strength + 15 * h3_strength + 15 * h10_strength - 10 * max(0.0, h7_strength - lagna_strength),
        "partnership": 25 * h7_strength + 10 * h2_strength + 10 * h11_strength - (10 if h7_afflicted else 0),
        "family_business": 20 * h2_strength + 15 * h4_strength + 10 * (1 if (h4_lord and (h4_lord == h2_lord or _ph(h4_lord) == 2 or _ph(h2_lord) == 4)) else 0),
        # v21 audit fix: this term had a double-multiplication bug -- the
        # trailing "* 10" after already normalizing h5_net into a 0-10
        # scale via "/ 15 * 10" meant the term could reach ~100 by itself
        # (h5_net=3.5 -> ~23.3) instead of the intended ~10-point max
        # contribution matching its sibling terms' 15/15/5-point scales.
        "professional_practice": 15 * lagna_strength + 10 * max(0.0, min(15.0, h5_net)) / 15 + 15 * h9_strength + 15 * h10_strength - 5 * max(0.0, h7_strength - 0.6),
        "trading_brokerage": 15 * (1.0 if mercury_dig in _STRONG_DIGNITY else 0.5) + 10 * h3_strength + 10 * h7_strength + 10 * h11_strength + 8 * (1 if (moon_dig in _STRONG_DIGNITY or rahu_h in (3, 7, 11)) else 0) + 8 * h2_strength,
        "manufacturing": 12 * (1.0 if mars_dig in _STRONG_DIGNITY else 0.5) + 10 * (1.0 if sat_dig in _STRONG_DIGNITY else 0.5) + 8 * h3_strength + 8 * h4_strength + 8 * h10_strength,
        "scalable_platform": 12 * (1.0 if (rahu_h and (mercury_h == rahu_h or sat_h == rahu_h)) else 0.3) + 8 * h3_strength + 10 * h7_strength + 10 * h10_strength + 10 * h11_strength + 6 * h12_strength,
    }

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    max_score = ranked[0][1] if ranked else 0.0
    normalized = {k: round(min(100.0, max(0.0, v / max_score * 100.0)) if max_score > 0 else 0.0, 1) for k, v in scores.items()}
    return {
        "best_fit": ranked[0][0] if ranked else None,
        "ranked": [(k, round(v, 2)) for k, v in ranked],
        "normalized_0_100": normalized,
        "note": "Operating-model fit is a RELATIVE, within-chart ranking (each model normalized against this chart's own top scorer), not an absolute cross-chart scale -- do not compare these numbers across different charts.",
    }

def _d10_house_lord_strength(payload: Any, house_num: int) -> float:
    """D10-native analog of _house_lord_strength(): placement bucket
    (kendra/trikona > upachaya > dusthana) for a D10 house's lord, judged
    by where that lord sits WITHIN the D10 chart's own house graph
    (d10_house_occupancy), not the lord's D1 dignity -- there is no
    reliably-populated D10-wide dignity table in this repo's payloads, so
    this stays placement-only, consistent with _d10_native_house_evidence's
    own approach."""
    house_lords = getattr(payload, "d10_house_lords", {}) or {}
    occupancy = getattr(payload, "d10_house_occupancy", {}) or {}
    if not house_lords or not occupancy:
        return 0.35
    lord = house_lords.get(str(house_num), house_lords.get(house_num, ""))
    if not lord:
        return 0.35

    def _occ(h: int) -> List[str]:
        return occupancy.get(str(h), occupancy.get(h, [])) or []

    native_house = 0
    for h in range(1, 13):
        if lord in _occ(h):
            native_house = h
            break
    if native_house in _KT:
        return 1.0
    if native_house in _UPACHAYA:
        return 0.65
    if native_house in _DUSTHANA:
        return 0.25
    return 0.45

def _business_operating_model_d10(payload: Any) -> Dict[str, Any]:
    """v20 audit fix: the D1-vs-D10 contradiction check previously only
    compared coarse ownership-house-family (H7/H10/H11) vs operational-
    house-family (H6/H8/H12) evidence nets, not the actual NAMED operating
    model D10 itself points to. This mirrors _business_operating_model()'s
    7-model scoring structure exactly, but built entirely from D10-native
    house-lord strengths (_d10_house_lord_strength) instead of D1 -- so the
    two functions' best_fit outputs are now directly comparable model
    names, not just directional house-family sums. Returns {} (no
    comparison possible) when the payload has no D10-native data."""
    house_lords = getattr(payload, "d10_house_lords", {}) or {}
    occupancy = getattr(payload, "d10_house_occupancy", {}) or {}
    if not house_lords or not occupancy:
        return {}

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _occ(h: int) -> List[str]:
        return occupancy.get(str(h), occupancy.get(h, [])) or []

    h2_lord, h4_lord = _h(2), _h(4)
    h7_lord = _h(7)

    lagna_strength = _d10_house_lord_strength(payload, 1)
    h2_strength = _d10_house_lord_strength(payload, 2) if h2_lord else 0.0
    h3_strength = _d10_house_lord_strength(payload, 3)
    h4_strength = _d10_house_lord_strength(payload, 4) if h4_lord else 0.0
    h7_strength = _d10_house_lord_strength(payload, 7) if h7_lord else 0.0
    h9_strength = _d10_house_lord_strength(payload, 9)
    h10_strength = _d10_house_lord_strength(payload, 10)
    h11_strength = _d10_house_lord_strength(payload, 11)
    h12_strength = _d10_house_lord_strength(payload, 12)

    benefics, malefics = _effective_benefic_malefic_sets(payload)
    h7_afflicted = bool(h7_lord and set(p for p in _occ(_native_house_helper(occupancy, h7_lord)) if p != h7_lord) & malefics) if h7_lord else False
    h5_net = sum(w for w, n in _d10_native_house_evidence(payload) if "H5" in n)

    # v21 audit fix, tightened per follow-up audit: Mercury/Moon/Mars/
    # Saturn/Rahu D10-native placement strength, replacing the fixed proxy
    # constants (0.5/0.3) that were standing in for real D10 evidence in
    # trading_brokerage/manufacturing/scalable_platform below. There is no
    # reliable D10-wide dignity table in this repo's payloads (per
    # _d10_house_lord_strength's own docstring), so this reuses the same
    # placement-bucket approach: a planet's D10-native house (via
    # _native_house_helper) mapped through kendra/trikona/upachaya/
    # dusthana buckets, exactly like _d10_house_lord_strength does for
    # house lords -- just applied to a specific karaka planet instead of a
    # house's lord.
    #
    # Follow-up audit fix: a planet genuinely absent from d10_house_
    # occupancy (native_house == 0) is an absence of evidence, not
    # moderate evidence -- returning the same 0.35 that
    # _d10_house_lord_strength uses for whole-chart-missing-data is wrong
    # here (that 0.35 guards a different case: no occupancy data AT ALL).
    # When the occupancy dict IS present but a specific planet just isn't
    # in it, that planet contributes zero, not a synthetic mid-strength.
    def _d10_planet_strength(planet: str) -> float:
        h = _native_house_helper(occupancy, planet)
        if not h:
            return 0.0
        if h in _KT:
            return 1.0
        if h in _UPACHAYA:
            return 0.65
        if h in _DUSTHANA:
            return 0.25
        return 0.45

    d10_mercury_strength = _d10_planet_strength("Mercury")
    d10_moon_strength = _d10_planet_strength("Moon")
    d10_mars_strength = _d10_planet_strength("Mars")
    d10_saturn_strength = _d10_planet_strength("Saturn")
    d10_rahu_strength = _d10_planet_strength("Rahu")
    d10_rahu_h, d10_mercury_h, d10_saturn_h = (
        _native_house_helper(occupancy, "Rahu"),
        _native_house_helper(occupancy, "Mercury"),
        _native_house_helper(occupancy, "Saturn"),
    )

    scores: Dict[str, float] = {
        "sole_owner": 20 * lagna_strength + 15 * h3_strength + 15 * h10_strength - 10 * max(0.0, h7_strength - lagna_strength),
        "partnership": 25 * h7_strength + 10 * h2_strength + 10 * h11_strength - (10 if h7_afflicted else 0),
        "family_business": 20 * h2_strength + 15 * h4_strength,
        # v21 audit fix: same double-multiplication bug as the D1 version
        # above -- removed the erroneous trailing "* 10".
        "professional_practice": 15 * lagna_strength + 10 * max(0.0, min(15.0, h5_net)) / 15 + 15 * h9_strength + 15 * h10_strength - 5 * max(0.0, h7_strength - 0.6),
        # Follow-up audit fix: the Moon/Rahu conjunction bonus used a fixed
        # 1.0/0.5 binary instead of real placement strength -- now takes
        # the better of (a) Moon's own D10 placement strength or (b) Rahu's
        # D10 placement strength when Rahu sits in a trade-favorable house
        # (3/7/11), so a weakly-placed Moon and a weakly-placed Rahu no
        # longer draw the same flat 0.5 credit as a well-placed one.
        "trading_brokerage": 15 * d10_mercury_strength + 10 * h3_strength + 10 * h7_strength + 10 * h11_strength + 8 * max(d10_moon_strength, d10_rahu_strength if d10_rahu_h in (3, 7, 11) else 0.0) + 8 * h2_strength,
        "manufacturing": 12 * d10_mars_strength + 10 * d10_saturn_strength + 8 * h3_strength + 8 * h4_strength + 8 * h10_strength,
        # Follow-up audit fix: the conjunction-bonus fallback used a fixed
        # 0.3 constant instead of Rahu's own real D10 placement strength;
        # now scales the fallback by Rahu's actual _d10_planet_strength
        # (still capped below the full conjunction bonus of 1.0, since a
        # bare well-placed Rahu without the Mercury/Saturn conjunction is
        # weaker evidence than the conjunction itself).
        "scalable_platform": 12 * (1.0 if (d10_rahu_h and (d10_mercury_h == d10_rahu_h or d10_saturn_h == d10_rahu_h)) else 0.3 * d10_rahu_strength) + 8 * h3_strength + 10 * h7_strength + 10 * h10_strength + 10 * h11_strength + 6 * h12_strength,
    }
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    max_score = ranked[0][1] if ranked else 0.0
    normalized = {k: round(min(100.0, max(0.0, v / max_score * 100.0)) if max_score > 0 else 0.0, 1) for k, v in scores.items()}
    return {
        "best_fit": ranked[0][0] if ranked else None,
        "ranked": [(k, round(v, 2)) for k, v in ranked],
        "normalized_0_100": normalized,
        "note": "D10-native operating-model fit, mirroring _business_operating_model()'s D1 structure so best_fit values are directly comparable across the two.",
    }

# Item 7 audit fix: D1's best_fit ("aspirational structure") and D10's
# best_fit ("actual execution manifestation") were previously surfaced as
# two independent rankings with no synthesis -- a reader had to manually
# reconcile "scalable_platform" (D1) vs "trading_brokerage" (D10) with no
# guidance on which should govern near-term decisions. This mirrors
# contradictions.py's own compatibility matrix (kept in sync manually,
# since importing contradictions.py here would be circular -- contradictions
# imports this module) so the synthesis and the contradiction-penalty
# softening agree on which pairs are genuinely one commercial family.
_OPERATING_MODEL_COMPATIBLE_PAIRS = frozenset({
    frozenset({"scalable_platform", "trading_brokerage"}),
})
_OPERATING_MODEL_PARTIALLY_COMPATIBLE_PAIRS = frozenset({
    frozenset({"partnership", "professional_practice"}),
    frozenset({"sole_owner", "professional_practice"}),
    frozenset({"sole_owner", "trading_brokerage"}),
})
# Domain-logic combined labels for the one pairing that already gets a full
# pass (COMPATIBLE) in the matrix above -- both models routinely co-occur as
# the #1/#2 ranked model for the same chart (see contradictions.py v38 note),
# so a genuine hybrid label can be stated with confidence rather than merely
# suppressing the penalty.
_OPERATING_MODEL_HYBRID_LABELS = {
    frozenset({"scalable_platform", "trading_brokerage"}): "technology-enabled marketplace / brokerage platform",
}


def _operating_model_synthesis(payload: Any) -> Dict[str, Any]:
    """Synthesizes D1's best-fit operating model (aspirational structure)
    against D10's best-fit operating model (actual execution manifestation)
    into a single governing recommendation, instead of leaving the two
    rankings to disagree silently side by side.

    Policy (per item 7 of the follow-up audit):
      - Same best_fit on both charts -> full-confidence synthesized label,
        no precedence question.
      - COMPATIBLE pair (see _OPERATING_MODEL_COMPATIBLE_PAIRS, matching
        contradictions.py's own matrix) -> a principled combined/hybrid
        label exists (_OPERATING_MODEL_HYBRID_LABELS); confidence stays
        HIGH since the two charts are describing one coherent commercial
        family, not disagreeing.
      - PARTIALLY_COMPATIBLE pair -> no single combined label invented (that
        would overstate the synthesis); confidence downgraded to MODERATE,
        and D10 is stated to take precedence for NEAR-TERM execution
        (D10 = actual manifestation) while D1 is framed as the LONGER-TERM
        structural aspiration -- this precedence rule (D10 governs real-
        world operating model) is the same reasoning contradictions.py's
        D1-vs-D10 magnitude-disagreement check already uses ("D1 promise
        likely under-delivers" when D10 reads weaker), applied here to
        operating-model LABEL choice rather than magnitude.
      - Otherwise (no principled relationship) -> confidence LOW, same
        D10-near-term/D1-long-term precedence framing, explicitly flagged
        as having no combined label.
    """
    d1_model = _business_operating_model(payload)
    d10_model = _business_operating_model_d10(payload)
    d1_fit = d1_model.get("best_fit")
    d10_fit = d10_model.get("best_fit")

    if not d1_fit or not d10_fit:
        return {
            "status": "INSUFFICIENT_DATA",
            "d1_best_fit": d1_fit,
            "d10_best_fit": d10_fit,
            "synthesized_label": d1_fit or d10_fit,
            "confidence": "LOW",
            "precedence": None,
            "note": "One of D1/D10 operating-model rankings is unavailable; no synthesis possible.",
        }

    if d1_fit == d10_fit:
        return {
            "status": "AGREEMENT",
            "d1_best_fit": d1_fit,
            "d10_best_fit": d10_fit,
            "synthesized_label": d1_fit,
            "confidence": "HIGH",
            "precedence": "AGREED",
            "note": "D1 (aspirational structure) and D10 (execution manifestation) name the SAME best-fit operating model -- no reconciliation needed.",
        }

    pair = frozenset({d1_fit, d10_fit})
    if pair in _OPERATING_MODEL_COMPATIBLE_PAIRS:
        hybrid_label = _OPERATING_MODEL_HYBRID_LABELS.get(pair, f"{d1_fit} / {d10_fit} (compatible hybrid)")
        return {
            "status": "COMPATIBLE_HYBRID",
            "d1_best_fit": d1_fit,
            "d10_best_fit": d10_fit,
            "synthesized_label": hybrid_label,
            "confidence": "HIGH",
            "precedence": "D10_NEAR_TERM_D1_LONG_TERM",
            "note": (
                f"D1 ({d1_fit}) and D10 ({d10_fit}) are one coherent commercial "
                f"family, not opposing structures -> combined label '{hybrid_label}'. "
                "D10 (actual execution manifestation) governs the near-term "
                "operating reality; D1 (aspirational structure) represents the "
                "longer-term structural direction the venture can grow into."
            ),
        }

    if pair in _OPERATING_MODEL_PARTIALLY_COMPATIBLE_PAIRS:
        return {
            "status": "PARTIALLY_COMPATIBLE_NO_SYNTHESIS",
            "d1_best_fit": d1_fit,
            "d10_best_fit": d10_fit,
            "synthesized_label": None,
            "confidence": "MODERATE",
            "precedence": "D10_NEAR_TERM_D1_LONG_TERM",
            "note": (
                f"D1 ({d1_fit}) and D10 ({d10_fit}) are related but not the same "
                "commercial family -> no principled combined label is stated (that "
                "would overstate agreement). D10 takes precedence for NEAR-TERM "
                f"execution -- expect the venture to actually run as '{d10_fit}' -- "
                f"while D1's '{d1_fit}' represents a longer-term structural "
                "aspiration the chart also supports."
            ),
        }

    return {
        "status": "NO_PRINCIPLED_SYNTHESIS",
        "d1_best_fit": d1_fit,
        "d10_best_fit": d10_fit,
        "synthesized_label": None,
        "confidence": "LOW",
        "precedence": "D10_NEAR_TERM_D1_LONG_TERM",
        "note": (
            f"D1 ({d1_fit}) and D10 ({d10_fit}) point to different operating "
            "structures with no principled combined label available -> "
            "operating-model confidence is reduced. D10 takes precedence for "
            f"NEAR-TERM execution -- expect the venture to actually run as "
            f"'{d10_fit}' -- while D1's '{d1_fit}' is retained only as a "
            "longer-term structural aspiration, not a near-term operating plan."
        ),
    }


def _native_house_helper(occupancy: Dict[str, Any], planet: str) -> int:
    """Shared tiny helper: which D10-native house a planet occupies, given
    a raw d10_house_occupancy dict. Used by _business_operating_model_d10
    for its own H7-affliction check without duplicating
    _d10_native_house_evidence's internal closure."""
    for h in range(1, 13):
        occ = occupancy.get(str(h), occupancy.get(h, [])) or []
        if planet in occ:
            return h
    return 0

