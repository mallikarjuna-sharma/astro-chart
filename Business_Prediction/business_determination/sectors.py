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


"""business_determination.sectors

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .constants import _load_business_registry
from .house_evidence import _house_lord_strength, _house_lord_strength_fine, _lords_connected, _planet_strength, _planet_strength_fine, _retrograde_status, capital_strategy_lean_for_payload
from .foreign_business import foreign_business_viability_evidence


def _archetype_raw_totals(payload: Any) -> Dict[str, float]:
    """Chart-native archetype support totals from D1 placements (general
    aptitude signature, sector-agnostic input to the blend below)."""
    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_dig = getattr(payload, "planet_dignities", {}) or {}

    _CORE_HOUSE_WEIGHT = {2: 0.7, 3: 0.6, 7: 1.0, 9: 0.5, 10: 0.9, 11: 0.8}

    totals: Dict[str, float] = {}
    for planet, house in planet_house.items():
        weight = _CORE_HOUSE_WEIGHT.get(house)
        if not weight or planet not in PLANET_ARCHETYPES:
            continue
        mult = DIGNITY.get(str(planet_dig.get(planet, "NEUTRAL")).upper(), 0.90)
        for archetype, affinity in PLANET_ARCHETYPES[planet].items():
            totals[archetype] = totals.get(archetype, 0.0) + weight * mult * affinity
    return totals

# v27 audit fix: spec section 9's 12-row sector table explicitly says
# "these combinations should generate candidate business families" -- i.e.
# they are meant to bias WHICH sector wins, not just add generic strength
# points. Until now, the 6 rows implemented in
# _extended_house_combination_evidence() (house_evidence.py) fed only
# score_business_significators' generic business-strength ledger, with
# that function's own docstring explicitly noting "does not itself
# reclassify the winning sector" -- a real, previously-undetected gap
# against this specific spec sentence, not merely unfinished detail. This
# maps each of the (now all 12, after v27 added the remaining 6) sector-
# table rows to the specific registry sector id(s) its "likely business
# orientation" describes, and reuses the exact same connection tests
# _extended_house_combination_evidence() already performs (via the shared
# _lords_connected() helper) rather than re-deriving them, so a combo only
# biases a sector when it's a genuine chart-verified relationship, not a
# guess from the sector's generic archetype/house/planet blend alone.
# v29 audit fix: the 7 sectors added to the registry alongside the
# original 12 (education_institutions, logistics_transportation, retail,
# legal_services, entertainment_sports, energy_utilities, pharma_biotech)
# were previously absent from this table entirely -- they could be top-
# ranked by rank_business_sectors() but could never receive a section-9
# combo bonus, an inconsistency with every other registered sector. Each
# addition below is justified directly by that row's own spec wording
# (e.g. "2-7-11: Trade, retail, commercial income" literally names
# retail; "9-10-11: Law, consulting, education, publishing" literally
# names law and education), not a fresh interpretation.
_SECTOR_TABLE_ROW_TO_SECTORS: Dict[str, List[str]] = {
    "2-7-11": ["trading_commerce", "retail"],
    "3-7-11": ["trading_commerce", "media_creative_business", "retail"],
    "3-10-11": ["tech_startup", "media_creative_business"],
    "4-10-11": ["real_estate_construction", "manufacturing_industrial", "energy_utilities", "logistics_transportation", "agriculture_commodities"],
    "5-10-11": ["consulting_professional_services", "media_creative_business", "education_institutions", "entertainment_sports"],
    "5-8-11": ["finance_investment"],
    "6-7-10-11": ["consulting_professional_services", "logistics_transportation"],
    "7-9-12": ["import_export_foreign_trade", "consulting_professional_services", "legal_services"],
    "8-10-11": ["finance_investment", "pharma_biotech"],
    "9-10-11": ["consulting_professional_services", "legal_services", "education_institutions"],
    "4-7-12": ["hospitality_lifestyle"],
    "3-7-10-12": ["import_export_foreign_trade", "tech_startup", "logistics_transportation"],
    "6-8-12": ["pharma_biotech", "healthcare_wellness_venture"],
    "2-4-11": ["family_business_continuation"],
}


def _sector_house_combination_bias(payload: Any) -> Dict[str, List[str]]:
    """Returns {sector_id: [citing combo notes]} for every spec section-9
    sector-table row that is ACTUALLY present on this chart (all named
    houses pairwise-connected through their lords, per the same
    _lords_connected() dignity-gated test used elsewhere). A sector may
    receive citations from more than one row; a row with no lord data or
    no connection contributes nothing (absence of the pattern is not
    itself evidence)."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = getattr(payload, "planet_dignities", {}) or {}

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _conn(a: int, b: int) -> bool:
        return _lords_connected(house_lords, planet_house, a, b, dignities=dignities)

    def _all_present(houses: Tuple[int, ...]) -> bool:
        return all(_h(h) for h in houses)

    def _chain_connected(houses: Tuple[int, ...]) -> bool:
        return all(_conn(houses[i], houses[i + 1]) for i in range(len(houses) - 1))

    _ROW_HOUSES: Dict[str, Tuple[int, ...]] = {
        "2-7-11": (2, 7, 11), "3-7-11": (3, 7, 11), "3-10-11": (3, 10, 11),
        "4-10-11": (4, 10, 11), "5-10-11": (5, 10, 11), "5-8-11": (5, 8, 11),
        "6-7-10-11": (6, 7, 10, 11), "7-9-12": (7, 9, 12), "8-10-11": (8, 10, 11),
        "9-10-11": (9, 10, 11), "4-7-12": (4, 7, 12), "3-7-10-12": (3, 7, 10, 12),
        "6-8-12": (6, 8, 12), "2-4-11": (2, 4, 11),
    }

    matches: Dict[str, List[str]] = {}
    for row, houses in _ROW_HOUSES.items():
        if not _all_present(houses) or not _chain_connected(houses):
            continue
        note = f"{row} house-combination present (spec section 9) -> candidate business family bias"
        for sector_id in _SECTOR_TABLE_ROW_TO_SECTORS.get(row, []):
            matches.setdefault(sector_id, []).append(note)
    return matches


def _canonical_sector(sector: str, sectors: Dict[str, Any]) -> str:
    value = str(sector or "").strip().lower()
    if value not in sectors:
        raise ValueError(f"unsupported business sector: {sector!r}")
    return value

# Engineering audit fix #5: these two adjustments (foreign-trade domestic
# discount, operating-model alignment bonus) used to be applied by engine.py
# AFTER calling rank_business_sectors_with_status()/sector_score(), directly
# mutating each row's `score` and then re-sorting -- meaning sector_score()
# and the actual top_sectors ranking were NOT the same function; a caller
# invoking sector_score()/rank_business_sectors_with_status() directly (as
# other code and tests can) would silently get a DIFFERENT, un-adjusted
# score than what compute_business_prediction()'s top_sectors showed for the
# same chart. Both adjustments now live inside sector_score() itself (and
# are threaded through rank_business_sectors_with_status()), so there is
# exactly one ranking function and no separate orchestration-layer rule
# application/re-sort step.
_OPERATING_MODEL_TO_COMPATIBLE_SECTORS: Dict[str, "set[str]"] = {
    "trading_brokerage": {
        "trading_commerce", "import_export_foreign_trade", "retail",
        "ecommerce_digital_retail", "real_estate_development_brokerage",
    },
    "scalable_platform": {
        "tech_startup", "media_creative_business", "it_services_outsourcing",
        "ecommerce_digital_retail", "telecommunications",
    },
    "professional_practice": {
        "consulting_professional_services", "legal_services", "education_institutions",
        "publishing_content_creation", "insurance_risk_underwriting",
    },
    "sole_owner": {
        "retail", "hospitality_lifestyle", "beauty_personal_care", "textiles_fashion_apparel",
    },
    "partnership": {
        "consulting_professional_services", "hospitality_lifestyle", "banking_lending_credit",
        "performing_arts_entertainment",
    },
    "family_business": {
        "family_business_continuation", "agriculture_commodities", "fmcg_consumer_goods",
        "construction_contracting", "food_beverage_restaurants",
    },
}


# v47 audit fix ("sector-strength calibration" -- user-directed, follow-up
# to declining a full recalibration for lack of real outcome data): the
# module docstring and sector_score()'s own docstring already disclosed,
# in prose, that the 0.40/0.35/0.25 blend weights are "a modeling choice,
# not a calibrated fit." This constant makes that disclosure structured
# and complete -- covering every weight/cap/discount this function applies,
# not just the top-level blend -- and states plainly that NONE of them
# were fit to outcome data (there is none to fit to; see CALIBRATION_STATUS
# / Business_Prediction/calibration.py at the module level for why). This
# is a TRANSPARENCY fix, not a recalibration: none of the actual numeric
# values below are changed by adding this constant, only their basis is
# now explicitly named in one place instead of scattered across several
# inline comments a reader would have to hunt for individually.
SECTOR_CALIBRATION_BASIS = {
    "basis_version": "v47",
    "calibrated_against_outcome_data": False,
    "reason_not_calibrated": (
        "No labeled historical chart/business-outcome dataset exists in this "
        "repo to calibrate against -- see the top-level empirical-validation "
        "gap (audit/readiness_10_10_validation.json: labelled_outcome_benchmark, "
        "golden_calculator_fixtures both ok=false). Every weight/cap below is "
        "an expert-judgment modeling choice, not a statistically fit parameter."
    ),
    "components": [
        {"name": "archetype_component_blend_weight", "value": 0.40, "basis": "Modeling choice: archetype/aptitude-vector fit given roughly equal-to-slightly-higher priority than raw house/planet placement strength, on the reasoning that a sector needs both temperamental fit and chart support -- not independently varied/tested against alternatives."},
        {"name": "house_component_blend_weight", "value": 0.35, "basis": "Modeling choice: core_houses lord-strength weighted second-highest, reflecting the classical primacy of house-lord strength in Parashari sector/profession reads -- not independently varied/tested."},
        {"name": "planet_component_blend_weight", "value": 0.25, "basis": "Modeling choice: core_planets strength weighted lowest of the three, since a sector's core planets are typically also its house lords or close significators (partial redundancy with house_component by design) -- not independently varied/tested."},
        {"name": "sector_table_combo_bonus_per_match", "value": 3, "cap": 9, "basis": "Modeling choice (v27 audit fix): kept deliberately small/capped so a spec-table combo match can only break close ties or add modest support, never overturn a sector with materially stronger core-house/core-planet fundamentals."},
        {"name": "dignity_precision_bonus_cap", "value": 6, "basis": "Modeling choice: bounded so fine-grained dignity precision refines, not dominates, the coarser capped house/planet components."},
        {"name": "foreign_business_bonus_range", "value": "±6", "basis": "Modeling choice, import_export_foreign_trade only: symmetric small adjustment for foreign-house (9/12) corroboration or contradiction."},
        {"name": "geographic_preference_discount_multiplier", "value": 0.85, "basis": "Modeling choice (v40 audit fix): a flat 15% discount when the chart's own geographic_preference reads domestic but the sector is foreign-oriented -- not derived from any distribution of real outcomes, chosen as a moderate (not disqualifying) penalty."},
        {"name": "operating_model_alignment_bonus", "value": 4, "basis": "Modeling choice (v40 audit fix): small fixed bonus when D10's best-fit operating model structurally matches the sector, via a hand-authored _OPERATING_MODEL_TO_COMPATIBLE_SECTORS mapping -- the mapping itself is expert-judgment categorization, not derived from data."},
        {"name": "per_sector_archetype_weights", "value": "see registry", "basis": "Defined per-sector in business_domain_registry_v1.json's `weights` dict (each sector's own archetype-name -> coefficient mapping, validated to sum to 1.0). These per-sector weights are the single LARGEST source of sector-to-sector scoring variation and have NO individual documented justification beyond the registry authors' domain judgment at authoring time -- this is the specific gap the audit's 'needs deeper field-specific evidence' language points at, and it remains open pending either outcome data or a documented per-sector rationale being supplied."},
    ],
}


def sector_score(
    payload: Any,
    vector: Mapping[str, float],
    sector: str,
    combo_bonus_notes: Optional[List[str]] = None,
    geographic_preference: Optional[str] = None,
    d10_operating_model_best_fit: Optional[str] = None,
    capital_strategy_lean: Optional[str] = None,
) -> Dict[str, Any]:
    """Blend three components for a sector, all reading the registry's
    declared fields:
      (a) archetype_component (0..1): generic aptitude vector projected
          through the sector's declared archetype `weights`.
      (b) house_component (0..1): mean lord-strength across the sector's
          declared `core_houses` (previously declared but never read).
      (c) planet_component (0..1): mean planet-strength across the
          sector's declared `core_planets` (previously declared but never
          read).
    Blend weights (0.40 / 0.35 / 0.25) are a modeling choice, not a
    calibrated fit -- flagged in calibration_status.

    v27 audit fix: a fourth, small, additive (not blended-in-ratio) bonus
    -- +3 per matched spec section-9 sector-table row for THIS sector,
    capped at +9 (3 rows) -- so a chart with a genuine, lord-connection-
    verified "candidate business family" match for this sector (per
    _sector_house_combination_bias()) actually nudges that sector's own
    score, honoring the spec's literal "these combinations should generate
    candidate business families" sentence. Deliberately additive and
    capped rather than blended into the 0.40/0.35/0.25 ratio above, so it
    cannot on its own overturn a sector with materially stronger core-
    house/core-planet fundamentals -- it can only break close ties or add
    modest support, matching how the sign-modality bonus (compute_named_
    promise_fields) is similarly capped and winner-adjacent rather than
    dominant.
    """
    registry = _load_business_registry()
    sectors = registry.get("sectors", {})
    normalized = _canonical_sector(sector, sectors)
    meta = sectors[normalized]
    weights = meta["weights"]

    archetype_component = sum(float(vector.get(name, 0.0)) / 100.0 * w for name, w in weights.items())

    core_houses = meta.get("core_houses", []) or []
    house_component_capped = (
        sum(_house_lord_strength(payload, int(h)) for h in core_houses) / len(core_houses)
        if core_houses else 0.5
    )

    core_planets = meta.get("core_planets", []) or []
    planet_component_capped = (
        sum(_planet_strength(payload, p) for p in core_planets) / len(core_planets)
        if core_planets else 0.5
    )

    # v28 audit fix: _house_lord_strength()/_planet_strength() themselves
    # (the CAPPED functions) are deliberately left untouched -- changing
    # their baseline would shift every chart's result everywhere they're
    # used elsewhere (dignity-gated evidence weighting, >=0.6/<0.35
    # threshold checks) with an established 0..1 semantics many existing
    # tests assume. dignity_precision_bonus recovers lost differentiation
    # as a small, capped, ADDITIVE bonus using the uncapped "_fine"
    # variants: for each core house/planet where the fine value exceeds
    # the capped value -- i.e. a genuinely exalted/own/moolatrikona
    # placement the cap flattened -- add credit proportional to the
    # excess, capped overall at +6.
    house_component_fine = (
        sum(_house_lord_strength_fine(payload, int(h)) for h in core_houses) / len(core_houses)
        if core_houses else 0.5
    )
    planet_component_fine = (
        sum(_planet_strength_fine(payload, p) for p in core_planets) / len(core_planets)
        if core_planets else 0.5
    )
    _dignity_excess = 0.0
    for h in core_houses:
        _dignity_excess += max(0.0, _house_lord_strength_fine(payload, int(h)) - _house_lord_strength(payload, int(h)))
    for p in core_planets:
        _dignity_excess += max(0.0, _planet_strength_fine(payload, p) - _planet_strength(payload, p))
    dignity_precision_bonus = round(min(6.0, _dignity_excess * 15.0), 2)

    # v35 audit fix (#13): the CAPPED components above saturate at 1.0 for
    # ANY kendra/trikona placement regardless of dignity -- v28/v34
    # mitigated this with a small additive bonus and transparency fields,
    # but the actual BLENDED SCORE used for ranking still relied almost
    # entirely on the capped, saturating values (dignity_precision_bonus
    # capped at +6 on a 0-100 score is a small nudge, not real
    # differentiation). This graduates house_component/planet_component
    # themselves for the BLEND ONLY (the shared _house_lord_strength/
    # _planet_strength functions and their 0.6/0.35 threshold semantics
    # elsewhere in the engine are still untouched) by blending the capped
    # value with a softly-normalized fine value: fine scores are divided
    # by 1.2 before capping at 1.0, so a genuinely exalted/own placement
    # (fine > capped) pulls the blend meaningfully above a merely-kendra
    # placement (fine == capped) rather than both reading identically.
    # 55% weight stays on the capped, well-tested value; 45% goes to the
    # normalized fine value, so this differentiates ranking without letting
    # dignity alone dominate over the archetype/house-family match itself.
    def _graduate(capped: float, fine: float) -> float:
        fine_normalized = max(0.0, min(1.0, fine / 1.2))
        return max(0.0, min(1.0, 0.55 * capped + 0.45 * fine_normalized))

    house_component = _graduate(house_component_capped, house_component_fine)
    planet_component = _graduate(planet_component_capped, planet_component_fine)

    blended = 100.0 * (0.40 * archetype_component + 0.35 * house_component + 0.25 * planet_component)

    notes = combo_bonus_notes or []
    combo_bonus = min(9.0, 3.0 * len(notes))

    # Dedicated foreign/cross-border business viability bundle (see
    # foreign_business.py) -- distinct from the generic core_houses=
    # [7,9,12]/core_planets=[Rahu,Mercury] affinity math above, which only
    # averages lord/planet strength without ever checking the specific
    # classical foreign-business signals (12th-lord videsha strength, 9th-
    # lord secondary corroboration, Rahu's foreign-house placement/
    # conjunction-aspect to the 9th/12th lord). Scoped to sectors whose
    # registry id literally names foreign/import-export trade (no
    # registry row currently declares a "foreign" archetype_family, so the
    # id-substring check below is the honest, currently-correct scope
    # test -- see foreign_business.py's module docstring for why this
    # bundle is kept narrow rather than folded into every sector's blend).
    # Additive and modestly capped (+/-6), matching how combo_bonus/
    # dignity_precision_bonus are similarly small, capped, non-dominant
    # nudges rather than a re-weighting of the 0.40/0.35/0.25 blend.
    foreign_business_notes: List[str] = []
    foreign_business_bonus = 0.0
    if "foreign" in normalized or normalized == "import_export_foreign_trade":
        for rec in foreign_business_viability_evidence(payload):
            foreign_business_notes.append(rec["note"])
            foreign_business_bonus += rec["weight"] if rec["polarity"] == "POSITIVE" else -abs(rec["weight"])
        foreign_business_bonus = round(max(-6.0, min(6.0, foreign_business_bonus)), 2)

    pre_adjustment_score = max(0.0, min(100.0, blended + combo_bonus + dignity_precision_bonus + foreign_business_bonus))

    # Foreign-trade / domestic-geographic-preference discount (formerly
    # applied post-hoc in engine.py). A modest, transparent discount (not a
    # veto) applied specifically to import_export_foreign_trade when the
    # chart's own mode_gate geographic_preference reads "domestic" -- so a
    # domestic-leaning chart doesn't present pure foreign trade as its top
    # field without at least disclosing the tension with its own geographic
    # signal. "international"/"both"/unset are unaffected.
    geographic_preference_discount_applied = False
    if normalized == "import_export_foreign_trade" and geographic_preference == "domestic":
        pre_adjustment_score = round(pre_adjustment_score * 0.85, 1)
        geographic_preference_discount_applied = True

    # Operating-model alignment bonus (formerly applied post-hoc in
    # engine.py). A small, transparent bonus to sectors that plausibly
    # correspond to the chart's own D10-native best-fit operating model, via
    # a narrow, explicit mapping (not a fuzzy label match) -- so a sector
    # actually supported by the chart's own preferred way of doing business
    # gets some credit for that alignment, without overriding the
    # underlying archetype/house/planet evidence.
    operating_model_alignment_bonus_applied: Optional[str] = None
    if (
        d10_operating_model_best_fit
        and d10_operating_model_best_fit in _OPERATING_MODEL_TO_COMPATIBLE_SECTORS
        and normalized in _OPERATING_MODEL_TO_COMPATIBLE_SECTORS[d10_operating_model_best_fit]
    ):
        pre_adjustment_score = round(min(100.0, pre_adjustment_score + 4.0), 1)
        operating_model_alignment_bonus_applied = d10_operating_model_best_fit

    final_score = max(0.0, min(100.0, pre_adjustment_score))

    # v-audit fix (business realism, item 33 -- "sector capital intensity is
    # not formally matched to capital capacity"): purely additive/
    # disclosure-only flag comparing this sector's registry-declared
    # capital_intensity (LOW/MODERATE/HIGH -- a standard, disclosed
    # business/economics classification, NOT an astrological claim; see the
    # registry JSON's capital_intensity_note) against the chart's own
    # capital_strategy_lean (BOOTSTRAP_FAVORED/EXTERNAL_CAPITAL_FAVORED/
    # BALANCED/INSUFFICIENT_DATA, from scoring.py's D1 H2-vs-H11/H8
    # house-lord-strength comparison). Deliberately does NOT touch `score`
    # -- matching how retrograde_notes/foreign_business_notes are citation-
    # only where the underlying signal is already priced in elsewhere, or
    # simply out of scope for the score itself: this flag is a feasibility
    # CAVEAT for the reader, not a re-scoring of astrological fit, since
    # capital availability is a financial-planning question the chart's
    # astrological promise for a sector doesn't answer on its own.
    # capital_strategy_lean is None (the default) when the caller doesn't
    # supply it -- degrades gracefully to INSUFFICIENT_DATA, same as when
    # the chart itself lacks house_lords data.
    capital_intensity = meta.get("capital_intensity")
    _lean = capital_strategy_lean if capital_strategy_lean is not None else "INSUFFICIENT_DATA"
    if not capital_intensity or _lean == "INSUFFICIENT_DATA":
        capital_feasibility_flag = "INSUFFICIENT_DATA"
        capital_feasibility_note = ""
    elif capital_intensity == "HIGH" and _lean == "BOOTSTRAP_FAVORED":
        capital_feasibility_flag = "CAPITAL_MISMATCH_RISK"
        capital_feasibility_note = (
            f"{meta.get('label', normalized)} is typically a HIGH capital-intensity sector "
            f"({meta.get('capital_intensity_basis', '')}), but this chart's own capital-strategy "
            "read leans BOOTSTRAP_FAVORED (self-funding capacity outweighs external-capital-raising "
            "capacity) -- worth planning for a funding gap, a phased/lower-capex entry point, or "
            "seeking external capital deliberately rather than assuming self-funding will suffice."
        )
    elif capital_intensity == "LOW" and _lean == "EXTERNAL_CAPITAL_FAVORED":
        capital_feasibility_flag = "CAPITAL_UNDERMATCH"
        capital_feasibility_note = (
            f"{meta.get('label', normalized)} is typically a LOW capital-intensity sector "
            f"({meta.get('capital_intensity_basis', '')}), while this chart's own capital-strategy "
            "read leans EXTERNAL_CAPITAL_FAVORED -- the chart's external-capital-raising capacity "
            "may be underused here; not a risk to entering this sector, just a note that this sector "
            "alone may not need the capital-raising strength the chart shows."
        )
    else:
        capital_feasibility_flag = "ALIGNED"
        capital_feasibility_note = ""

    # v31 audit fix: a sector could rank highly (score in the 75-90 range)
    # purely from broad archetype/house/planet-component matching while
    # NONE of the spec's own section-9 classical house-combination table
    # actually corroborated it (sector_table_combo_bonus == 0 -- no exact
    # combination match at all). Presenting that as an equally "confirmed"
    # top result as a sector that DOES have an exact classical combination
    # match overstates the certainty of a purely archetype-driven read.
    # match_confidence now makes this distinction explicit and inspectable
    # per-sector, rather than requiring the reader to notice
    # sector_table_combo_bonus==0 themselves in a 19-row table.
    match_confidence = "CONFIRMED_SECTOR_MATCH" if combo_bonus > 0 else "EXPLORATORY_SECTOR_MATCH"

    # RETROGRADE-1 (gap audit): Mercury-anchored sectors (trading_commerce,
    # retail, media_creative_business, consulting_professional_services,
    # finance_investment, education_institutions -- any sector that
    # declares Mercury as a core_planet) never surfaced Mercury's
    # retrograde status at all. Kept as a transparent citation-only note
    # (not folded into `score`) because _planet_strength()/_
    # planet_strength_fine() ALREADY apply the nuanced retrograde-aware
    # dignity modifier feeding planet_component/planet_component_fine
    # above (house_evidence._retro_adjusted_dig_factor) -- adding a second
    # score adjustment here would double-count the same signal. This note
    # exists purely so a reader can see WHY a Mercury-core sector's
    # planet_component moved, and to satisfy the audit's ask for a
    # transparent citation even where the model choice is "already
    # priced in, cite don't re-score." Degrades gracefully to an empty
    # list when retrograde data isn't in payload (_retrograde_status()
    # returns None, which is falsy).
    retrograde_notes: List[str] = []
    if "Mercury" in core_planets and _retrograde_status(payload, "Mercury"):
        retrograde_notes.append(
            "Mercury retrograde: core planet for this sector -- classical "
            "vakra-Budha reading is revisited/renegotiated trade decisions "
            "and delayed-but-not-blocked commercial timing, not a block on "
            "the sector fit itself (already reflected in planet_component "
            "via the retrograde-aware dignity modifier; see "
            "house_evidence._retro_adjusted_dig_factor)."
        )

    # component_saturated still reports on the underlying CAPPED values
    # (whether the raw placement-tier formula hit its ceiling), since that
    # is the diagnostic signal this flag is meant to carry -- the graduated
    # house_component/planet_component above no longer saturate at exactly
    # 1.0 themselves, by design, so checking them here would always read
    # False and lose the diagnostic value entirely.
    component_saturated = round(house_component_capped, 4) >= 0.999 or round(planet_component_capped, 4) >= 0.999

    return {
        "sector": normalized,
        "label": meta.get("label", normalized),
        # v42 audit fix: expose the registry's declared archetype_family on
        # every scored row so diversify_sector_ranking() (below) can group
        # near-duplicate sectors by their shared planetary signature
        # without having to re-open the registry itself.
        "archetype_family": meta.get("archetype_family"),
        "score": round(final_score, 2),
        "components": {
            "archetype_component_0_1": round(archetype_component, 4),
            "house_component_0_1": round(house_component, 4),
            "planet_component_0_1": round(planet_component, 4),
            "house_component_fine_0_1": round(house_component_fine, 4),
            "planet_component_fine_0_1": round(planet_component_fine, 4),
            "component_saturated": component_saturated,
        },
        "core_houses_used": core_houses,
        "core_planets_used": core_planets,
        "mapping_weights": dict(weights),
        "sector_table_combo_bonus": round(combo_bonus, 2),
        "sector_table_combo_matches": list(notes),
        "dignity_precision_bonus": dignity_precision_bonus,
        "match_confidence": match_confidence,
        "retrograde_notes": retrograde_notes,
        "foreign_business_bonus": foreign_business_bonus,
        "foreign_business_notes": foreign_business_notes,
        "geographic_preference_discount_applied": geographic_preference_discount_applied,
        "operating_model_alignment_bonus_applied": operating_model_alignment_bonus_applied,
        "capital_intensity": capital_intensity,
        "capital_feasibility_flag": capital_feasibility_flag,
        "capital_feasibility_note": capital_feasibility_note,
        "calibration_basis": SECTOR_CALIBRATION_BASIS,
    }

_SECTOR_TO_SBC_DOMAIN = {
    "trading_commerce": "commerce",
    "manufacturing_industrial": "engineering",
    "real_estate_construction": "engineering",
    "consulting_professional_services": "management",
    "finance_investment": "commerce",
    "hospitality_lifestyle": "arts",
    "tech_startup": "technology",
    "import_export_foreign_trade": "commerce",
    "agriculture_commodities": "agriculture",
    "media_creative_business": "arts",
    "healthcare_wellness_venture": "medicine",
    "family_business_continuation": "management",
    "education_institutions": "education",
    "logistics_transportation": "commerce",
    "retail": "commerce",
    "legal_services": "law",
    "entertainment_sports": "sports",
    "energy_utilities": "engineering",
    "pharma_biotech": "research",
    # v48 sector-expansion additions (new sectors + logical sub-sector splits)
    "banking_lending_credit": "commerce",
    "insurance_risk_underwriting": "commerce",
    "it_services_outsourcing": "technology",
    "ecommerce_digital_retail": "commerce",
    "fmcg_consumer_goods": "commerce",
    "textiles_fashion_apparel": "commerce",
    "telecommunications": "technology",
    "mining_metals_extraction": "engineering",
    "automotive_transport_manufacturing": "engineering",
    "beauty_personal_care": "arts",
    "publishing_content_creation": "arts",
    "nonprofit_social_enterprise": "management",
    "sports_athletics_business": "sports",
    "performing_arts_entertainment": "arts",
    "energy_production_extraction": "engineering",
    "utilities_distribution_infrastructure": "engineering",
    "real_estate_development_brokerage": "engineering",
    "construction_contracting": "engineering",
    # v49 gap-audit additions
    "spiritual_religious_occult_services": "_default",
    "cybersecurity_it_security": "technology",
    "waste_management_recycling": "engineering",
    "government_contracting_public_sector": "management",
    "food_beverage_restaurants": "commerce",
    "aviation_aerospace": "engineering",
    "defense_security_services": "engineering",
    # v50 gap-audit additions (2nd pass)
    "maritime_shipping_ports": "commerce",
    "jewelry_gems_precious_metals": "commerce",
    "renewable_clean_energy": "engineering",
    "advertising_marketing_agencies": "arts",
    "hr_staffing_recruitment": "management",
    "fintech": "technology",
    "edtech": "technology",
    "gaming_esports": "technology",
    "interior_design_architecture": "arts",
    "chemicals_industrial_materials": "engineering",
    "event_management_hospitality_services": "arts",
    "real_estate_investment_rental_income": "commerce",
}

def _apply_sbc_advisory_layer(payload: Any, ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attaches SBC (Sarvatobhadra Chakra) advisory timing metadata to each
    ranked sector, reusing Job_Career.sbc.SarvatobhadraEngine as-is. Per
    that module's own architecture: SBC answers "how easily / when", not
    "which sector" -- it must NOT re-rank the sectors (same guarantee the
    career-field report gives), only annotate smi/timing_band/sbc_detail.

    Returns (rows, method_status) instead of degrading SILENTLY on failure
    -- callers can now tell "SBC ran and annotated every row" (APPLIED)
    apart from "SBC couldn't run for this chart" (FAILED/UNAVAILABLE),
    rather than both cases looking identical (sectors with no sbc_* keys).
    """
    try:
        from Job_Career.sbc import SarvatobhadraEngine
    except Exception as exc:
        return ranked, {"status": "UNAVAILABLE", "error": f"import failed: {exc}"}

    try:
        engine = SarvatobhadraEngine(payload)
    except Exception as exc:
        return ranked, {"status": "FAILED", "error": f"SarvatobhadraEngine init failed: {exc}"}

    rows = []
    for row in ranked:
        domain = _SECTOR_TO_SBC_DOMAIN.get(row["sector"], "_default")
        affinity_planets = {p: 1.0 for p in row.get("core_planets_used", [])}
        rows.append({**row, "domain": domain, "final_score": row["score"], "affinity_planets": affinity_planets})

    try:
        enriched = engine.apply_to_ranking(rows)
    except Exception as exc:
        return ranked, {"status": "FAILED", "error": f"apply_to_ranking failed: {exc}"}

    out = []
    for original, sbc_row in zip(ranked, enriched):
        merged = dict(original)
        merged["sbc_smi"] = sbc_row.get("smi")
        merged["sbc_timing_band"] = sbc_row.get("timing_band")
        merged["sbc_detail"] = sbc_row.get("sbc_detail")
        out.append(merged)
    return out, {"status": "APPLIED", "error": None, "rows_annotated": len(out)}

def diversify_sector_ranking(
    ranked_sectors: List[Dict[str, Any]],
    max_per_family: int = 1,
    top_n: int = 8,
) -> Dict[str, Any]:
    """Diversity-aware ADDITIVE view over an already-ranked sector list.

    rank_business_sectors_with_status() (above) intentionally does a flat
    score-descending sort with no clustering -- that raw ranking must keep
    existing shape/values for the astrologer edition's full-transparency
    audit trail (every one of the 19 sectors, independently scored, in
    order). But for a chart with one strong underlying planetary signature
    (e.g. Jupiter+Mercury), that flat sort can surface 4-5 near-paraphrases
    of the SAME signature in the top 7 (consulting/finance/education/legal,
    all `jupiter_mercury_scholarship_commerce`) -- presenting synonyms as if
    they were independently discovered distinct recommendations, which is
    especially misleading when (as is common) none of them carry an exact
    classical combo match (match_confidence == CONFIRMED_SECTOR_MATCH) to
    differentiate them either.

    This function does NOT replace or re-sort the input; it derives a
    second, additive view from it:

      "diversified_top_sectors": walks the ranked list top-down and greedily
          takes the single highest-scoring sector from each archetype_family
          first (so the chart's genuinely distinct signatures surface
          before any near-duplicate), then -- only once every family
          present in the ranked list has contributed its first
          representative -- allows a second (then third, ...) entry per
          family if `top_n` still has room. This is a stable two-pass
          selection, not a hack:
            pass 1: single sweep down `ranked_sectors`, take the first
                (= highest-scoring, since input is already sorted)
                occurrence of each family, stop contributing once a family
                has `max_per_family` picks.
            pass 2: only entered if pass 1 filled every distinct family and
                `top_n` slots remain -- sweep down `ranked_sectors` again in
                score order and fill remaining slots with whatever hasn't
                been picked yet, still respecting `max_per_family` as a
                soft cap per round (family caps loosen by +1 each
                additional pass rather than being abandoned outright, so
                one family still can't flood the list before every other
                family gets a second look).
      "family_groups": every archetype_family actually present in
          `ranked_sectors`, each listing its member sectors (already-ranked
          order) plus a one-line human-readable note naming the family and
          how many sectors in it were NOT surfaced in
          diversified_top_sectors (0 for singleton families) -- so a
          client-facing reader sees one representative per family plus an
          honest count of how many similar options exist elsewhere in the
          full ranking, instead of reading 4 near-synonyms as 4
          independent discoveries.

    Never raises. If `archetype_family` is missing from a legacy registry
    entry (pre-dating this field), that sector is degraded gracefully into
    its own singleton family (keyed by its own sector id, flagged
    `"legacy_singleton": True`) rather than crashing or being silently
    dropped.
    """
    if not ranked_sectors:
        return {
            "diversified_top_sectors": [],
            "family_groups": [],
            "status": "EMPTY_INPUT",
        }

    # ------------------------------------------------------------------
    # Step 1: resolve each row's family, degrading gracefully (not
    # crashing) when archetype_family is absent -- e.g. a legacy registry
    # entry from before this field existed. Such a row becomes its own
    # singleton family so it is never silently merged into an unrelated
    # bucket.
    # ------------------------------------------------------------------
    legacy_singletons: List[str] = []
    row_family: Dict[int, str] = {}
    for i, row in enumerate(ranked_sectors):
        family = row.get("archetype_family")
        if not family:
            family = f"__legacy_singleton__{row.get('sector', i)}"
            legacy_singletons.append(row.get("sector", str(i)))
        row_family[i] = family

    # Group row indices by family, preserving the input's score-descending
    # order within each family (ranked_sectors is already sorted, so the
    # first index encountered per family is that family's best match).
    family_to_indices: Dict[str, List[int]] = {}
    for i, family in row_family.items():
        family_to_indices.setdefault(family, []).append(i)

    # ------------------------------------------------------------------
    # Step 2: greedy round-robin selection. Round 0 gives every family its
    # single best (highest-scoring) representative, in the order those
    # representatives appear in the original ranking (so the overall
    # relative ordering of families still reflects chart strength). Only
    # once round 0 has offered a pick to every family does round 1 begin
    # (a second entry per family, again in score order), and so on, until
    # top_n slots are filled or every sector has been placed.
    # ------------------------------------------------------------------
    picked: List[int] = []
    picked_set = set()
    round_num = 0
    while len(picked) < top_n and len(picked_set) < len(ranked_sectors):
        cap_this_round = max_per_family * (round_num + 1)
        made_progress = False
        # Iterate families in the order their next-best candidate appears
        # in the original ranking, so stronger families still get first
        # dibs within a round.
        candidates = []
        for family, indices in family_to_indices.items():
            already_from_family = sum(1 for j in picked if row_family[j] == family)
            if already_from_family >= cap_this_round:
                continue
            for idx in indices:
                if idx not in picked_set:
                    candidates.append((idx, family))
                    break
        candidates.sort(key=lambda pair: pair[0])  # original rank order == score order
        for idx, family in candidates:
            if len(picked) >= top_n:
                break
            picked.append(idx)
            picked_set.add(idx)
            made_progress = True
        round_num += 1
        if not made_progress:
            break

    diversified_top_sectors = [ranked_sectors[i] for i in picked]

    # ------------------------------------------------------------------
    # Step 3: family_groups -- every family present in the input, its
    # members in ranked order, and an honest one-line note of how many of
    # its members were NOT surfaced in diversified_top_sectors above.
    # ------------------------------------------------------------------
    family_groups: List[Dict[str, Any]] = []
    for family, indices in family_to_indices.items():
        members = [ranked_sectors[i] for i in indices]
        surfaced = sum(1 for i in indices if i in picked_set)
        hidden = len(indices) - surfaced
        is_legacy = family.startswith("__legacy_singleton__")
        if is_legacy:
            note = (
                f"{members[0]['label']} has no archetype_family declared in the "
                "registry (legacy entry) -- shown as its own singleton family "
                "rather than merged with any other sector."
            )
        elif hidden > 0:
            note = (
                f"{len(indices)} sectors share a similar {family.replace('_', '-')} "
                f"signature -- showing the strongest match "
                f"({members[0]['label']}); {hidden} other similar option"
                f"{'s' if hidden != 1 else ''} available in the full ranking."
            )
        else:
            note = f"{members[0]['label']} is the only sector in the {family.replace('_', '-')} signature group."
        family_groups.append({
            "archetype_family": family,
            "is_legacy_singleton": is_legacy,
            "member_sectors": [m["sector"] for m in members],
            "member_count": len(indices),
            "surfaced_count": surfaced,
            "hidden_count": hidden,
            "note": note,
        })

    return {
        "diversified_top_sectors": diversified_top_sectors,
        "family_groups": family_groups,
        "status": "OK",
        "legacy_singleton_sectors": legacy_singletons,
        "max_per_family": max_per_family,
        "top_n": top_n,
    }


def rank_business_sectors(payload: Any, apply_sbc: bool = True) -> List[Dict[str, Any]]:
    """Score every registered sector for this chart and return them ranked
    high-to-low. Backward-compatible: returns just the list. Use
    rank_business_sectors_with_status() if the SBC method_status is needed."""
    ranked, _sbc_status = rank_business_sectors_with_status(payload, apply_sbc=apply_sbc)
    return ranked

def rank_business_sectors_with_status(
    payload: Any,
    top_n_sectors: Optional[int] = None,
    apply_sbc: bool = True,
    geographic_preference: Optional[str] = None,
    d10_operating_model_best_fit: Optional[str] = None,
    capital_strategy_lean: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Score every registered sector for this chart and return them ranked
    high-to-low, plus the SBC method_status. Two charts with different
    core-house/core-planet strength for a sector now produce different
    scores for that sector even if their generic archetype vectors are
    similar (previously they would not, since core_houses/core_planets
    were unused). Deterministic ranking is computed first and is NEVER
    re-ordered by the SBC layer, matching the guarantee
    Job_Career/career_field_report_v2.py already makes.

    geographic_preference / d10_operating_model_best_fit (engineering audit
    fix #5): optional cross-chart signals (mode_gate's geographic_preference,
    _business_operating_model_d10()'s best_fit) that, when supplied, are
    forwarded straight into sector_score() for every sector so the foreign-
    trade discount and operating-model alignment bonus are applied ONCE,
    inside the canonical scoring function, before the single sort below --
    not as a second, separate re-ranking pass in the caller. Omitting them
    (the default) simply skips those two optional adjustments; the rest of
    the ranking is unaffected.

    capital_strategy_lean (v-audit fix, business realism item 33): optional
    third cross-chart signal, forwarded the same way, for the capital-
    feasibility flag described in sector_score()'s own docstring. If not
    supplied, this function derives it itself via
    capital_strategy_lean_for_payload(payload) so the flag is populated
    by default rather than requiring every caller to remember to compute
    and pass it in.
    """
    raw_totals = _archetype_raw_totals(payload)
    vector = {name: scale_raw_support(raw_totals.get(name, 0.0)) for name in ARCHETYPE_NAMES}
    registry = _load_business_registry()
    combo_bias = _sector_house_combination_bias(payload)
    _capital_strategy_lean = capital_strategy_lean if capital_strategy_lean is not None else capital_strategy_lean_for_payload(payload)
    ranked = [
        sector_score(
            payload, vector, sector, combo_bonus_notes=combo_bias.get(sector),
            geographic_preference=geographic_preference,
            d10_operating_model_best_fit=d10_operating_model_best_fit,
            capital_strategy_lean=_capital_strategy_lean,
        )
        for sector in registry.get("sectors", {})
    ]
    ranked.sort(key=lambda row: row["score"], reverse=True)
    for idx, row in enumerate(ranked, 1):
        row["rank"] = idx

    sbc_status: Dict[str, Any] = {"status": "NOT_REQUESTED", "error": None}
    if apply_sbc:
        ranked, sbc_status = _apply_sbc_advisory_layer(payload, ranked)

    if top_n_sectors is not None:
        ranked = ranked[:top_n_sectors]
    return ranked, sbc_status

