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
from contextvars import ContextVar
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

from jyotish.d10_archetypes import (
    PLANET_ARCHETYPES,
    ARCHETYPE_NAMES,
    DIGNITY,
    scale_raw_support,
)


"""business_determination.constants

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""



# Engineering audit fix #9: several modules (timing.py, synastry.py,
# yogas.py, ashtakavarga_timing.py, ...) intentionally degrade gracefully on
# unexpected failures inside a bounded, best-effort evidence helper -- e.g.
# an unusual payload shape, a missing optional dependency, a divide-by-zero
# in a rarely-hit branch -- by catching Exception and returning an empty/
# neutral fallback so the rest of the pipeline still runs. That degrade-
# gracefully BEHAVIOR is intentionally kept as-is (a single missing/odd
# input should not crash the whole business-prediction report). What was
# missing is VISIBILITY: the caught exception used to simply vanish, so a
# real defect (a typo in an attribute name, a genuine bug) looked
# indistinguishable from "this chart legitimately has no data for this
# helper." This tiny module-level collector lets any of those except blocks
# record a structured {"module", "error", "type"} entry without changing
# what they return; compute_business_prediction() drains it once per call
# and attaches the result as result["diagnostics"], so failures are now
# visible in the API output instead of silently swallowed.
#
# Each execution context owns an immutable diagnostic tuple.  ContextVar
# isolates threads and asyncio tasks while tuple replacement prevents a
# copied context from sharing a mutable list with its parent.
_DIAGNOSTICS: ContextVar[Tuple[Dict[str, Any], ...]] = ContextVar(
    "business_prediction_diagnostics", default=()
)


def _reset_diagnostics() -> None:
    _DIAGNOSTICS.set(())


def _record_diagnostic(
    module: str,
    exc: BaseException,
    note: str = "",
    severity: str = "DEGRADED_METHOD",
) -> None:
    if severity not in {"INFORMATIONAL_FALLBACK", "DEGRADED_METHOD", "RECOMMENDATION_BLOCKING"}:
        raise ValueError(f"unknown diagnostic severity: {severity}")
    entry: Dict[str, Any] = {
        "module": module,
        "error": str(exc),
        "type": type(exc).__name__,
        "severity": severity,
    }
    if note:
        entry["note"] = note
    _DIAGNOSTICS.set((*_DIAGNOSTICS.get(), entry))


def _get_diagnostics() -> List[Dict[str, Any]]:
    return [dict(entry) for entry in _DIAGNOSTICS.get()]


MODEL_STATUS = "EXPERIMENTAL_HEURISTIC"

CALIBRATION_STATUS = "NOT_CALIBRATED_NO_BACKTEST_NO_LABELED_OUTCOMES"


def sav_lookup(sav: Mapping[Any, int], house: int, default: int = 28) -> int:
    """Shared Sarvashtakavarga (SAV) bindu-count lookup for a given house
    number, factored out of the near-identical `_sav_h(h)` closures that
    used to be independently declared inside significators.py and
    mode_gate.py (both reading `payload.sav_points_houses`, the canonical
    field already computed once by jyotish/engine_io.py's
    `_sav_normalized`/`jyotish.ashtakavarga.compute_bav_points` -- see that
    module for the underlying bindu-table computation). `default=28` is the
    SAV grand-total-per-house average (337/12 ~= 28.08) used as a neutral
    fallback when a house key is missing, matching the two prior closures'
    behavior exactly. Accepts either str or int house keys in `sav` (some
    callers use "1".."12", others 1..12) without requiring the caller to
    normalize first."""
    return sav.get(str(house), sav.get(house, default))

MATURITY_STATEMENT = (
    "Architecturally mature and internally validated: implementation rules, "
    "invariants, regression behavior, and end-to-end execution are tested. "
    "Real-world predictive validity has NOT been established because no "
    "prospective labeled outcome corpus has been evaluated. Astrological "
    "precedence and conflict resolution remain explicit engineered "
    "interpretations, not uniquely authoritative classical doctrine."
)

MATURITY_CAVEATS = (
    "Tests validate implementation, not predictions.",
    "Synthetic calibration data validates the calibration PIPELINE, not the model.",
    "Classical method coverage does not imply classical consensus.",
    "Heuristic tier is a deterministic threshold, not statistical confidence.",
    "Outputs are decision-support narratives, not financial forecasts.",
    # v39 audit fix (#19, user-caught): Rahu/Ketu dignity and Shadbala-like
    # effective-strength values used in timing/scoring (e.g. eff_strengths,
    # d9_planet_dignities) are read AS PROVIDED on the payload from
    # upstream chart computation -- this engine does not independently
    # declare or compute a node exaltation/dignity scheme or a node
    # Shadbala method of its own. Classical treatment of node
    # dignity/strength varies significantly by school, and classical
    # Shadbala is ordinarily defined only for the seven visible planets, so
    # any node-strength figures a reader sees here should be understood as
    # inherited from the upstream chart-computation module's own declared
    # convention, not as a doctrinally settled value this engine asserts.
    "Rahu/Ketu dignity and strength figures are read as provided by upstream chart computation, not independently declared or computed by this engine; classical treatment of node dignity/strength varies by school and should not be read as doctrinally settled.",
)

EVIDENCE_BASIS = (
    "D1_HOUSE_LORDSHIP_AND_DIGNITY + D1_DIRECT_10TH_LORD_JUDGMENT"
    "(own_strength+H7_H10+H10_H11+H2_H10_connections+conjunctions+D9_D10_dignity) + "
    "D9_D10_DIGNITY_CORROBORATION + "
    "KP_CUSP_SUBLORD_FINAL_ARBITER(H6_soft_negative_unless_hard_dusthana_copresent) + "
    "JAIMINI_AK_AMK + JAIMINI_RASI_DRISHTI + "
    "JAIMINI_ARGALA_VIRODHARGALA + DYNAMIC_TRANSIT_PROJECTION(MEAN_MOTION_APPROXIMATE) + "
    "SHADBALA_EFF_STRENGTH + SBC_ADVISORY_TIMING + "
    "PHALADEEPIKA_FULL_CHAIN(Lagna+Moon+Sun_references compared by the REFERENCE POINT'S "
    "OWN strength, strongest reference scored at full weight and others at half weight, "
    "10th-lord Navamsha-occupied-sign-lord confirmation) + D9_D10_LAGNA_VARGA_NATIVE_PRECEDENCE + "
    "D10_NATIVE_HOUSE_GRAPH(H7_H10_H11_lord_placement+H2_H7_H11_H6_H8_H12_occupancy) + "
    "D9_NATIVE_HOUSE_GRAPH(H7_H1_H11_lord_placement+H2_H7_H11_H6_H8_H12_occupancy, "
    "derived from divisional_charts['D9_navamsha']) + "
    "D9_DIGNITY_ON_H2_H7_H11_LORDS + "
    "QUALIFIED_VIPARITA_RAJA_YOGA(H6_and_H8_lords, VRY_CONFIRMED/exchange-form/"
    "own_house_not_VRY/DUSTHANA_LORD_STRONG_BUT_MIXED) + "
    "EVIDENCE_FAMILY_CAPS(D1_PROMISE/VARGA_CONFIRMATION/ACTIVATION_DIRECTION/STRENGTH, "
    "35pct_of_ceiling_each, prevents correlated double counting) + "
    "COMPARATIVE_BUSINESS_VS_EMPLOYMENT_MARGIN(compute_business_mode_gate replaces legacy "
    "jyotish.employment_mode.compute_employment_mode with FIXED documented per-mode ceilings "
    "-- not a dynamic per-fired-rule denominator -- so sparse-evidence charts cannot be "
    "normalized to 100; proceed requires gate_score to beat employment_score by a minimum "
    "margin, not just clear its own floor) + "
    "MODE_GATE_D10_NATIVE_HOUSE_GRAPH(D10-H7/H10/H11 lord placement + benefic/malefic "
    "H2_H7_H11_H6_H8_H12 occupancy, routed into employment/business/family by which D10 house "
    "each finding concerns -- previously the mode gate only used D9/D10 PLANET-dignity "
    "corroboration on H6/H7 lords, never D10's own house graph) + "
    "MODE_GATE_DYNAMIC_TRANSIT_CLIMATE(current, dampened-weight, 2-year forward window via "
    "the same mean-motion _transit_corroboration used for timed windows -- distinct from the "
    "multi-year timed-windows forecast; a static viability read now also reflects whether the "
    "immediate transit climate supports or strains launching a venture right now) + "
    "TIERED_PRECEDENCE_ARBITRATION(D1<D9D10_CONFIRM_DENY<KP_FINAL_ARBITER<JAIMINI_ACTIVATION<TRANSIT_TRIGGER) + "
    "RUN_MANIFEST_AND_CALCULATION_POLICY_PROVENANCE + OPTIONAL_CONSENT_GATED_LLM_NARRATIVE + "
    "CONTEXTUAL_MOON_MERCURY_NATURE(Moon_paksha_via_birth_tithi+Mercury_conjunction_association) + "
    "FUNCTIONAL_KENDRA_TRIKONA_LORDSHIP_NEUTRALIZATION(Sun/Mars/Saturn excluded from the malefic "
    "set when they rule a kendra/trikona house for this Lagna -- classical yoga-karaka principle; "
    "conservative: neutralized, not promoted to benefic) "
    "-- RAHU_KETU_STILL_FIXED_NATURE(nodes don't hold sign lordship in this repo's systems, no "
    "functional-lordship override modeled for them) "
    "-- TIMING_IS_ANTARDASHA_LEVEL_BASE_PLUS_OPTIONAL_PD_REFINEMENT(each AD window's "
    "net-score/label is still Antardasha-level; each window ADDITIVELY carries "
    "pd_subwindows (Pratyantardasha, reusing Job_Career.timeline._expand_pratyantardashas) "
    "with a PD-lord house-lordship refinement layered on top of the parent AD score, WHEN "
    "house_lords data and the Job_Career import are both available -- see each window's "
    "pd_status/pd_subwindows and method_status.timing_precision for whether PD refinement "
    "actually ran on a given call; Sookshma/ephemeris-grade transit contacts still NOT "
    "computed) "
    "-- D9_USED_BROADLY_AS_GENERAL_CONFIRMATION(not separated into D2/D11-style dedicated "
    "wealth/gains vargas; D9 corroborates partnership/H1/H11/H2 strength here, which risks "
    "some correlated double-counting even with family caps applied) "
    "-- KP_HOUSE_POLARITY_STILL_STRUCTURAL_NOT_FULLY_EVENT_SPECIFIC(H6 softened when standalone, "
    "H8/H12/H7-as-partnership/H10-as-burden/H11-as-overextension nuances not modeled) "
    "-- VRY_STILL_SIMPLIFIED(H12 now folded into the shared VRY qualification check "
    "alongside H6/H8 as of this pass -- aspects still not modeled (only conjunction-based "
    "contamination/exchange detection), dasha-activation-based adversity-to-rise "
    "confirmation not modeled) "
    "-- NOT CALIBRATED "
    "-- Full version-by-version remediation history (FIXED_v13 through the current version) has been moved out of this runtime string and into business_determination/CHANGELOG.md as of engineering audit item #8; see that file for the historical record. "
    "-- MATURITY: ARCHITECTURALLY_MATURE_AND_INTERNALLY_VALIDATED, "
    "REAL_WORLD_PREDICTIVE_VALIDITY_NOT_ESTABLISHED (see maturity_statement/maturity_caveats on "
    "compute_business_prediction()'s return dict for the full statement: tests validate "
    "implementation not predictions; synthetic calibration data validates the pipeline not the "
    "model; classical coverage does not imply classical consensus; heuristic tier is not "
    "statistical confidence; outputs are decision-support narratives, not financial forecasts) "
)

# Engineering audit fix #6: RULE_PACK_VERSION was stuck at v41 while
# in-code "vNN audit fix" comments throughout this package (constants.py,
# engine.py, contradictions.py, etc.) already referenced up to v42, and
# mode_gate.py's gate_policy string was still labeled v28. Bumped to match
# the highest version actually referenced in the codebase's own audit-fix
# comments as of this pass. Bump this value again (and mode_gate.py's
# gate_policy string alongside it) whenever a future change is tagged with
# a higher "vNN audit fix" comment, so the two stay in sync.
# v-audit fix (item 59, 2026-07-29): bumped from v42 -- this session's
# changes (v-audit-fix-tagged, not vNN-numbered, hence not yet reflected
# here per the v42-bump note above) touched independent KP-chain
# verification (kp.py, propagated to mode_gate.py/contradictions.py/
# timing.py), birth-time-uncertainty-graded reliability (scoring.py),
# the D1 divisional_charts.D1_rashi schema fallback (jyotish/engine_io.py),
# and constraints on the standalone proceed Boolean (engine.py) -- all of
# which change real scoring/recommendation output for a given chart, not
# just internal refactoring. See CHANGELOG.md for the itemized entry.
# v-audit fix (item 60, 2026-07-29): bumped from v44 -- made the D60/D11/
# Chara Dasha gaps EXPLICIT structured BLOCKED/NOT_IMPLEMENTED statuses
# (d24_d60_sign.py::_d60_confirmation_status enriched with blocked_reason,
# new _d11_gains_status(), timing.py::_compute_method_status() gained a
# chara_dasha entry) instead of silent NO_DATA/absent fields, plus fixed
# the shadbala static_scope mislabel (was hardcoded NOT_APPLICABLE; it DOES
# feed static scoring via house_evidence.py::_shadbala_sav_strength_modifier).
# These are disclosure fixes, not new astrological computation -- see
# CHANGELOG.md v45 entry for why D60/D11/Chara Dasha were deliberately NOT
# implemented rather than fabricated.
RULE_PACK_VERSION = "business-engine.v52"
ARCHITECTURE_VERSION = "business-architecture.v53"

# v22 modularization note: this module now lives one directory deeper
# (Business_Prediction/business_determination/ instead of
# Business_Prediction/) than the original business_engine.py, so the
# registry JSON path must go up one level to stay pointed at
# Business_Prediction/business_domain_registry_v1.json.
_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "business_domain_registry_v1.json")

_KENDRA = frozenset({1, 4, 7, 10})

_TRIKONA = frozenset({1, 5, 9})

_KT = _KENDRA | _TRIKONA

_DUSTHANA = frozenset({6, 8, 12})

_UPACHAYA = frozenset({3, 6, 10, 11})

_STRONG_DIGNITY = frozenset({"EXALTED", "OWN", "MOOLATRIKONA"})

# v-audit fix (typed rule IDs, first slice -- correction-order item 5): a
# shared, module-level registry of evidence CATEGORY tags, so significators.py
# (which sets `category` on the evidence dicts it generates) and scoring.py
# (which consumes those tags to classify profit/capital/gains evidence
# instead of scanning `note` text for keywords) reference the SAME string
# constants rather than each hardcoding their own copy that could drift out
# of sync. This is intentionally a small, additive first slice -- see
# significators.py::score_business_significators's `_add()` docstring
# comment for why only the H2/H11 profit-family sites are tagged so far,
# not a full retag of every evidence-generating call site in this package.
_EVIDENCE_CATEGORY_H2_CAPITAL = "H2_CAPITAL"
_EVIDENCE_CATEGORY_H11_GAINS = "H11_GAINS"
_PROFIT_FAMILY_CATEGORIES = frozenset({_EVIDENCE_CATEGORY_H2_CAPITAL, _EVIDENCE_CATEGORY_H11_GAINS})

# v-audit fix (typed rule IDs, second slice -- item 4, "stability-risk
# scoring remains keyword-based"): the shared H6/H8/H12 dusthana-lord
# (Viparita Raja Yoga qualification) and H12-loss evidence significators.py
# generates is the exact evidence business_stability_components'
# cash_flow_stability sub-score identifies via a keyword scan
# ("h2"/"h6"/"h8"/"debt"/"dusthana"/"leverage"/"liability" substrings in
# `note`). Tagged at the point of generation, same pattern as the profit
# categories above.
_EVIDENCE_CATEGORY_H6_H8_H12_RISK = "H6_H8_H12_RISK"
_STABILITY_RISK_CATEGORIES = frozenset({_EVIDENCE_CATEGORY_H6_H8_H12_RISK})

# v42 audit fix: each sector's `archetype_family` groups sectors that share a
# genuinely dominant planetary/archetype signature (same top-weighted
# archetype(s) + overlapping core_planets) -- derived directly from the
# registry's own weights/core_planets, NOT an arbitrary taxonomy. This is
# the closed enum every sector's declared archetype_family must belong to;
# used by diversify_sector_ranking() (business_determination/sectors.py) so
# near-duplicate sectors driven by the same underlying chart signature
# don't crowd out genuinely distinct top matches in client-facing sector
# lists. Kept here (not just in the JSON) so a malformed/typo'd family name
# in a future registry edit fails validate_business_rule_pack() loudly
# instead of silently forming its own one-sector "family" that never
# dedupes against anything.
_ARCHETYPE_FAMILIES = frozenset({
    "jupiter_mercury_scholarship_commerce",
    "mars_saturn_engineering_fieldops",
    "venus_mercury_commerce_communication",
    "rahu_mercury_innovation_research",
    "moon_care_compassion",
    "mars_rahu_logistics_mobility",
    "venus_design_experience_lifestyle",
    "mars_saturn_mercury_technical_care",
    # Added for the v48 sector-expansion pass (missing sectors + logical
    # sub-sector splits, per astrologer review): each new family below
    # reflects a genuinely distinct planet-pair signature not covered by
    # any family above -- not a re-labeling of an existing one.
    "jupiter_saturn_capital_discipline",       # banking_lending_credit, insurance_risk_underwriting
    "mercury_saturn_technical_service",        # it_services_outsourcing
    "rahu_venus_mercury_digital_commerce",     # ecommerce_digital_retail
    "venus_moon_consumer_goods",               # fmcg_consumer_goods, beauty_personal_care, food_beverage_restaurants
    "sun_saturn_energy_power",                 # energy_production_extraction
    "saturn_mercury_infrastructure_networks",  # utilities_distribution_infrastructure

    # v49 audit fix (gap-audit pass): "mars_saturn_engineering_fieldops" is
    # retained below (unused by any sector as of v49) only so any external
    # caller that stored/compared against that literal string pre-v49 does
    # not hard-crash on an unrecognized-enum error -- no sector declares it
    # any longer; it was overcrowded (7 members) and, for energy_utilities,
    # actively mislabeled (declared a Mars significator that sector never
    # had). Split into the three narrower, correctly-scoped families below,
    # plus two umbrella/dharma families that also moved off it or off
    # jupiter_mercury_scholarship_commerce for the same reason (a family
    # name must only promise planets the member sectors actually declare).
    "mars_saturn_engineering_fieldops",        # DEPRECATED: no active sector uses this as of v49; see above
    "mars_saturn_heavy_industrial",            # manufacturing_industrial, automotive_transport_manufacturing
    "mars_saturn_land_extraction",             # mining_metals_extraction, construction_contracting
    "mars_saturn_agriculture_fieldops",        # agriculture_commodities
    "mars_saturn_defense_security",            # defense_security_services
    "real_estate_value_chain_umbrella",        # real_estate_construction (umbrella)
    "entertainment_sports_umbrella",           # entertainment_sports (umbrella)
    "energy_utilities_umbrella",               # energy_utilities (umbrella)
    "jupiter_saturn_dharma_authority",         # legal_services
    "sun_mars_competitive_authority_sports",   # sports_athletics_business
    "ketu_jupiter_moksha_dharma",              # spiritual_religious_occult_services
    "ketu_saturn_security_research",           # cybersecurity_it_security
    "ketu_saturn_transformation_fieldops",     # waste_management_recycling
    "sun_saturn_authority_administration",     # government_contracting_public_sector
    "rahu_saturn_aviation_infrastructure",     # aviation_aerospace

    # v50 audit fix (2nd gap-audit pass): 12 further missing sectors.
    "moon_rahu_maritime_foreign_trade",        # maritime_shipping_ports
    "venus_sun_luxury_gems",                   # jewelry_gems_precious_metals
    "sun_rahu_renewable_innovation",           # renewable_clean_energy
    "moon_mercury_saturn_people_placement",    # hr_staffing_recruitment
    "rahu_jupiter_mercury_fintech_innovation", # fintech
    "rahu_jupiter_mercury_edtech_innovation",  # edtech
    "venus_saturn_mercury_design_architecture",# interior_design_architecture
    "mars_ketu_chemical_transformation",       # chemicals_industrial_materials
    "venus_mercury_event_experience_design",   # event_management_hospitality_services
    "moon_saturn_passive_income_holding",      # real_estate_investment_rental_income
})

# v-audit fix (business realism, item 33 -- "sector capital intensity is
# not formally matched to capital capacity"): closed enum for each sector's
# declared `capital_intensity` (a standard, disclosed business/economics
# classification of typical fixed-capital requirement, NOT an astrological
# claim -- see the registry JSON's own capital_intensity_note for full
# disclosure and business_determination/sectors.py's capital-feasibility
# check for how it's used).
_CAPITAL_INTENSITY_TIERS = frozenset({"LOW", "MODERATE", "HIGH"})

_registry_cache: Optional[Dict[str, Any]] = None

def _load_business_registry() -> Dict[str, Any]:
    global _registry_cache
    if _registry_cache is None:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as fh:
            _registry_cache = json.load(fh)
    return _registry_cache

def validate_business_rule_pack() -> Dict[str, Any]:
    """Same validation shape as d10_archetypes.validate_rule_pack(), but for
    the business sector registry: weights must sum to 1.0, reference only
    archetypes already defined in jyotish.d10_archetypes.ARCHETYPE_NAMES,
    and every declared core_house must be in 1..12.
    """
    registry = _load_business_registry()
    sectors = registry.get("sectors", {})
    errors: List[str] = []
    for sector, meta in sectors.items():
        weights = meta.get("weights", {})
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            errors.append(f"{sector}: weights do not sum to 1 (got {total})")
        unknown = sorted(set(weights) - set(ARCHETYPE_NAMES))
        if unknown:
            errors.append(f"{sector}: unknown archetypes {unknown}")
        bad_houses = [h for h in meta.get("core_houses", []) if not (1 <= int(h) <= 12)]
        if bad_houses:
            errors.append(f"{sector}: invalid core_houses {bad_houses}")
        if not meta.get("core_planets"):
            errors.append(f"{sector}: no core_planets declared")
        # v42 audit fix: archetype_family is required (non-empty string)
        # and must be one of the closed _ARCHETYPE_FAMILIES enum above --
        # a malformed/typo'd/missing family now fails validation loudly
        # instead of silently degrading to a singleton family at
        # diversify_sector_ranking() time (which only tolerates that for
        # LEGACY registries that predate this field entirely, not for a
        # registry that is supposed to declare it).
        family = meta.get("archetype_family")
        if not family or not isinstance(family, str):
            errors.append(f"{sector}: missing/empty archetype_family")
        elif family not in _ARCHETYPE_FAMILIES:
            errors.append(f"{sector}: unknown archetype_family {family!r} (expected one of {sorted(_ARCHETYPE_FAMILIES)})")
        # v-audit fix (business realism, item 33): capital_intensity is
        # required and must be one of the closed _CAPITAL_INTENSITY_TIERS
        # enum -- same fail-loudly pattern as archetype_family above.
        intensity = meta.get("capital_intensity")
        if not intensity or not isinstance(intensity, str):
            errors.append(f"{sector}: missing/empty capital_intensity")
        elif intensity not in _CAPITAL_INTENSITY_TIERS:
            errors.append(f"{sector}: unknown capital_intensity {intensity!r} (expected one of {sorted(_CAPITAL_INTENSITY_TIERS)})")
        if not meta.get("capital_intensity_basis"):
            errors.append(f"{sector}: missing capital_intensity_basis")
    return {
        "ok": not errors,
        "errors": errors,
        "registry_version": registry.get("_registry_meta", {}).get("version", ""),
        "sector_count": len(sectors),
    }

__all__ = ['MODEL_STATUS', 'CALIBRATION_STATUS', 'MATURITY_STATEMENT', 'MATURITY_CAVEATS', 'EVIDENCE_BASIS', 'RULE_PACK_VERSION', '_REGISTRY_PATH', '_KENDRA', '_TRIKONA', '_KT', '_DUSTHANA', '_UPACHAYA', '_STRONG_DIGNITY', '_EVIDENCE_CATEGORY_H2_CAPITAL', '_EVIDENCE_CATEGORY_H11_GAINS', '_PROFIT_FAMILY_CATEGORIES', '_EVIDENCE_CATEGORY_H6_H8_H12_RISK', '_STABILITY_RISK_CATEGORIES', '_ARCHETYPE_FAMILIES', '_CAPITAL_INTENSITY_TIERS', '_registry_cache', '_load_business_registry', 'validate_business_rule_pack', 'sav_lookup', '_reset_diagnostics', '_record_diagnostic', '_get_diagnostics']
