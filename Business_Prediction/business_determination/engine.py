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


"""business_determination.engine

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .constants import CALIBRATION_STATUS, EVIDENCE_BASIS, MATURITY_CAVEATS, MATURITY_STATEMENT, MODEL_STATUS, RULE_PACK_VERSION, _get_diagnostics, _reset_diagnostics
from .house_evidence import _d2_native_house_evidence, _d2_hora_deep_evidence, lagnesh_neecha_bhanga_adjudication, _house_lord_strength, _dig_name, _rich_planet_dignities
from .kp import _kp_10th_cusp_job_vs_business
from .significators import score_business_significators, _mercury_full_adjudication
from .nakshatra_business import janma_nakshatra_business_evidence, janma_nakshatra_full_chain_evidence  # noqa: F401
from .d10_rectification import d10_rectification_sensitivity  # noqa: F401
from .foreign_business import foreign_business_viability_evidence  # noqa: F401
from .sectors import diversify_sector_ranking, rank_business_sectors_with_status
from .timing import _VENTURE_TYPE_TO_GATE_KEY, _compute_method_status, _compute_windows_and_status
from .mode_gate import _attach_provenance, _calibration_state, _compose_business_narrative, compute_business_mode_gate
from .d24_d60_sign import _d11_gains_status, _d24_competency_status, _d24_full_analysis, _d60_confirmation_status, _sign_modality_profile
from .financial_readiness import evaluate_financial_readiness
from .operating_models import _business_operating_model, _business_operating_model_d10, _operating_model_synthesis
from .contradictions import _contradiction_penalties
from .scoring import _compute_named_promise_fields, _false_conclusion_guard_checklist
from .synastry import compute_partnership_synastry
from .yogas import detect_business_yogas, yoga_detection_status
from .legal_risk import detect_legal_dispute_risk, legal_dispute_risk_status
from .transition_timing import compute_transition_timing_recommendation
# muhurta.py is intentionally NOT re-exported via `*` here and its
# find_business_muhurta() is intentionally NOT called anywhere inside
# compute_business_prediction() below: it is a separate date-RANGE scan
# (electional/muhurta selection) distinct from this function's fixed-
# birth-chart analysis. It is exported directly from __init__.py and
# business_engine.py's facade instead -- see muhurta.py's module docstring.
from .muhurta import find_business_muhurta  # noqa: F401

# ashtakavarga_timing.py is intentionally NOT re-exported via `*` here and
# its rank_business_years() is intentionally NOT called anywhere inside
# compute_business_prediction() below: like muhurta.py above, it has a
# different natural calling shape (a caller-chosen YEAR RANGE, not this
# function's fixed-birth-chart snapshot). It reuses payload.sav_points_houses
# (already computed by jyotish/engine_io.py) rather than recomputing SAV,
# and can optionally be cross-referenced against this function's own
# timed_windows output (pass timed_windows as its timing_windows= arg) for
# dasha corroboration -- see ashtakavarga_timing.py's module docstring for
# the combined-report calling pattern. Exported directly from __init__.py
# and business_engine.py's facade, same as find_business_muhurta.
from .ashtakavarga_timing import rank_business_years  # noqa: F401
from .policy import DECISION_POLICY
from .result_schema import OUTPUT_CONTRACT_VERSION, validate_result_contract
from .constants import ARCHITECTURE_VERSION
from .runtime_models import CalculationContext
from .release_manifest import build_release_manifest
from .capability_status import capability_status
from .orchestration_services import assess_evidence_sufficiency, finalize_result, validate_request


def _kn_rao_validation_sequence(
    payload: Any,
    mode_gate: Dict[str, Any],
    significators: Dict[str, Any],
    d24_status: Dict[str, Any],
    d60_status: Dict[str, Any],
    timed_windows: List[Dict[str, Any]],
    timing_status: Dict[str, Any],
    method_status: Dict[str, Any],
    named_fields: Dict[str, Any],
    rejected_by_main_chart: bool,
    veto_note: Optional[str],
) -> List[Dict[str, Any]]:
    """v25 audit fix: spec section 7's 10-step KN Rao-style validation
    sequence was previously only a documented architectural intent ("merge-
    at-the-end", per this module's own docstrings) -- every step's
    underlying computation already existed somewhere in the pipeline, but
    nothing walked them in the spec's literal numbered order or exposed
    that order as an inspectable trace. This function does NOT re-derive
    any astrology; it cites the exact already-computed value(s) each step
    corresponds to, in the spec's order, so the sequencing itself becomes
    auditable rather than merely asserted. Step 10 ("reject conclusions
    contradicted by the main chart") is the one step that is also a real
    gate (see rejected_by_main_chart on recommendation, wired in v25)."""
    evidence = significators.get("evidence", [])

    def _notes_containing(*fragments: str) -> List[str]:
        return [e["note"] for e in evidence if any(f in e["note"] for f in fragments)]

    h10_notes = _notes_containing("H10", "10th")
    h2_h11_notes = _notes_containing("H2 ", "H11", "2nd", "11th")
    h3_notes = _notes_containing("H3 ", "3rd")
    business_positive = (mode_gate.get("positive_signals", {}) or {}).get("business", [])
    employment_positive = (mode_gate.get("positive_signals", {}) or {}).get("employment", [])
    confidence = named_fields.get("business_over_job_confidence", {}) or {}
    dynamic_transit = (method_status or {}).get("dynamic_transit", {}) or {}

    return [
        {
            "step": 1, "name": "Establish the D1 promise.",
            "evidence": f"business_promise={named_fields.get('business_promise')}, job_promise={named_fields.get('job_promise')} "
                        f"(D1-anchored mode_gate: business_score={mode_gate.get('business_score')}, employment_score={mode_gate.get('employment_score')})",
        },
        {
            "step": 2, "name": "Examine the 10th house and 10th lord.",
            "evidence": "; ".join(h10_notes) or "No H10-specific evidence entry fired for this chart (10th lord not independently flagged by score_business_significators).",
        },
        {
            "step": 3, "name": "Compare the 6th house of service with the 7th house of business.",
            "evidence": f"mode_gate.employment_score={mode_gate.get('employment_score')} (service/H6-weighted) vs mode_gate.business_score={mode_gate.get('business_score')} (venture/H7-weighted); "
                        f"business positive signals: {business_positive or 'none'}; employment positive signals: {employment_positive or 'none'}",
        },
        {
            "step": 4, "name": "Examine the 2nd and 11th for financial outcome.",
            "evidence": "; ".join(h2_h11_notes) or "No H2/H11-specific evidence entry fired for this chart.",
        },
        {
            "step": 5, "name": "Examine the 3rd for initiative.",
            "evidence": "; ".join(h3_notes) or "No H3-specific evidence entry fired for this chart.",
        },
        {
            "step": 6, "name": "Confirm through D10.",
            "evidence": f"D10 (Dashamsha) method_status={method_status.get('d10_dashamsha', {}).get('status', 'UNKNOWN')}; "
                        f"D24 competency_status={d24_status.get('status')} (factor={d24_status.get('factor')})",
        },
        {
            "step": 7, "name": "Examine the relevant dasha sequence.",
            "evidence": f"timing_status={timing_status.get('status')}; {len(timed_windows)} timed window(s) in the requested forecast horizon.",
        },
        {
            "step": 8, "name": "Check Jupiter and Saturn transit activation.",
            "evidence": (f"dynamic_transit status={dynamic_transit.get('status', 'UNKNOWN')}"
                         + (f" -- {dynamic_transit.get('note')}" if dynamic_transit.get("note") else "")
                         + " (mean-motion-approximate; see method_status.dynamic_transit for the full disclosure)"),
        },
        {
            "step": 9, "name": "Require repeated confirmation rather than isolated yogas.",
            "evidence": f"method_agreement={confidence.get('method_agreement')}, chart_data_quality={confidence.get('chart_data_quality')}, "
                        f"signal_clarity={confidence.get('signal_clarity')} (business_over_job_confidence composite -- see that field for the full multiplicative formula)",
        },
        {
            "step": 10, "name": "Reject conclusions contradicted by the main chart.",
            "evidence": (f"REJECTED -- {veto_note}" if rejected_by_main_chart
                         else "No D1-vs-D10 direct opposing-operating-models contradiction (check 8b) present on this chart -- veto not exercised."),
            "gated": rejected_by_main_chart,
        },
    ]


def _final_decision_hierarchy_trace(
    payload: Any,
    mode_gate: Dict[str, Any],
    significators: Dict[str, Any],
    top_sectors: List[Dict[str, Any]],
    timed_windows: List[Dict[str, Any]],
    timing_status: Dict[str, Any],
    method_status: Dict[str, Any],
    d24_status: Dict[str, Any],
    d60_status: Dict[str, Any],
    kp10: Dict[str, Any],
    sign_modality: Dict[str, Any],
    operating_model: Dict[str, Any],
    contradictions: List[Dict[str, Any]],
    named_fields: Dict[str, Any],
    recommendation: Dict[str, Any],
    operating_model_d10: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """v25 audit fix: spec section 16's 20-step "final engine decision
    hierarchy" -- same treatment as _kn_rao_validation_sequence() above:
    an auditable, literally-ordered trace citing the real already-computed
    value for each named step, not a re-implementation of the pipeline as
    20 sequential imperative gates (which already exists as the pipeline
    itself, just not previously exposed in this literal order)."""
    confidence = named_fields.get("business_over_job_confidence", {}) or {}
    top_sector_label = top_sectors[0]["label"] if top_sectors else "N/A"
    jaimini_evidence = [e["note"] for e in significators.get("evidence", []) if any(k in e["note"] for k in ("Jaimini", "Arudha", "Karakamsha", "Atmakaraka", "Amatyakaraka", "Argala", "rasi drishti"))]
    kp_evidence = [e["note"] for e in significators.get("evidence", []) if "KP" in e["note"] or "cusp" in e["note"].lower() or "sub-lord" in e["note"].lower()]

    return [
        {"step": 1, "name": "Confirm birth-data quality.",
         "evidence": f"chart_data_quality={confidence.get('chart_data_quality')}, birth_time_reliability={confidence.get('birth_time_reliability')}"},
        {"step": 2, "name": "Calculate canonical D1 planetary and house facts.",
         "evidence": f"significators strength_0_100={significators.get('strength_0_100')} (from {len(significators.get('evidence', []))} evidence entries against payload.house_lords/planet_house/planet_dignities)"},
        {"step": 3, "name": "Establish D1 job, business and independent-profession promises separately.",
         "evidence": f"job_promise={named_fields.get('job_promise')}, business_promise={named_fields.get('business_promise')}, independent_profession_promise={named_fields.get('independent_profession_promise')}"},
        {"step": 4, "name": "Evaluate Lagna and entrepreneurial agency.",
         "evidence": "; ".join(e["note"] for e in significators.get("evidence", []) if "Lagnesh" in e["note"]) or "No Lagnesh-specific evidence entry fired for this chart."},
        {"step": 5, "name": "Compare the 6th and 7th without treating them as mutually exclusive.",
         "evidence": f"mode_gate.employment_score={mode_gate.get('employment_score')}, mode_gate.business_score={mode_gate.get('business_score')}, hybrid_suggested={recommendation.get('hybrid_suggested')}"},
        {"step": 6, "name": "Trace income through the 2nd and 11th.",
         "evidence": "; ".join(e["note"] for e in significators.get("evidence", []) if "H2 " in e["note"] or "H11" in e["note"]) or "No H2/H11-specific evidence entry fired for this chart."},
        {"step": 7, "name": "Determine the professional field through planets, signs, houses and lords.",
         "evidence": f"top_sector={top_sector_label}, sign_modality field_affinities={sign_modality.get('field_affinities')}"},
        {"step": 8, "name": "Confirm the operating model through D10.",
         # Audit fix: this step's own name says "through D10" but previously
         # only cited operating_model (the D1-side best_fit) -- the D10-side
         # confirmation (operating_model_d10.best_fit) was never actually
         # surfaced in the trace, so the step didn't prove D10 was consulted
         # at all. Now cites both, plus whether they agree.
         "evidence": (
             f"D1 operating_model best_fit={operating_model.get('best_fit')}, "
             f"D10-native operating_model best_fit={(operating_model_d10 or {}).get('best_fit')}, "
             f"D1/D10 agree={operating_model.get('best_fit') == (operating_model_d10 or {}).get('best_fit') if operating_model_d10 else 'D10_NOT_PROVIDED'}"
         )},
        {"step": 9, "name": "Validate lord durability through D9.",
         "evidence": f"D9 (Navamsha) method_status={method_status.get('d9_navamsha', {}).get('status', 'UNKNOWN')}"},
        {"step": 10, "name": "Validate competency feasibility through D24.",
         "evidence": f"d24_competency_status={d24_status.get('status')} (factor={d24_status.get('factor')})"},
        {"step": 11, "name": "Add Jaimini AK, AmK, Karakamsha, A7, A10, Argala and Rasi drishti.",
         "evidence": "; ".join(jaimini_evidence) or "No Jaimini-family evidence entry fired for this chart."},
        {"step": 12, "name": (
            "Add KP cusp-level job/business promise."
            if kp10.get("chain_verified") else
            "KP cusp-level job/business promise NOT VALIDLY APPLIED "
            "(house system not confirmed Placidus / sub-lord chain unverified) "
            "-- excluded from weighted scoring, shown for reference only."
         ),
         "evidence": (
             f"kp_10th_cusp_job_vs_business={kp10.get('note', kp10)}; "
             f"chain_verified={kp10.get('chain_verified')}; "
             f"cusp_audit.status={(kp10.get('cusp_audit') or {}).get('status')}; "
             f"cusp_audit.reasons={(kp10.get('cusp_audit') or {}).get('reasons')}; "
             f"kp_authority_factor={(kp10.get('cusp_audit') or {}).get('kp_authority_factor')}"
         )},
        {"step": 13, "name": "Add the KN Rao-style promise-dasha-transit sequence.",
         "evidence": "See kn_rao_validation_sequence output field for the full 10-step trace."},
        {"step": 14, "name": "Use D60 only as a low-weight reliability modifier.",
         "evidence": f"d60_confirmation_status={d60_status.get('status')} (business-layer weight capped at 3, per _BUSINESS_LAYER_WEIGHTS['d60'])"},
        {"step": 15, "name": "Calculate job and business scores independently.",
         "evidence": f"business_promise_layers.weighted_total={named_fields.get('business_promise_layers', {}).get('weighted_total')}, job_promise_layers.weighted_total={named_fields.get('job_promise_layers', {}).get('weighted_total')}"},
        {"step": 16, "name": "Apply contradiction and dependency penalties.",
         "evidence": f"{len(contradictions)} contradiction finding(s) applied; penalty_applied={recommendation.get('contradiction_penalty_applied')}"},
        {"step": 17, "name": "Calculate the business advantage margin.",
         "evidence": f"business_advantage_margin={named_fields.get('business_advantage_margin')} ({named_fields.get('business_advantage_label')})"},
        {"step": 18, "name": "Evaluate timing readiness separately.",
         "evidence": f"current_timing_readiness={named_fields.get('current_timing_readiness')}, timing_status={timing_status.get('status')}"},
        {"step": 19, "name": "Determine the business sector and operating model.",
         "evidence": f"top_sector={top_sector_label}, operating_model.best_fit={operating_model.get('best_fit')}, operating_model_d10.best_fit={(operating_model_d10 or {}).get('best_fit')}"},
        {"step": 20, "name": "Produce a confidence label with supporting and opposing evidence.",
         "evidence": f"business_over_job_confidence.label={confidence.get('label')}, score_0_1={confidence.get('score_0_1')}, heuristic_tier={recommendation.get('heuristic_tier')}, rejected_by_main_chart={recommendation.get('rejected_by_main_chart')}"},
    ]


# v34 audit fix: house-family classification used to tag each timed
# window's evidence with a business-relevance/activity read, addressing
# audit items #16/#19 (a window should not be labeled favorable for
# BUSINESS purely because it activates houses that are just as favorable
# for employment -- H1/H3/H7/H10/H11 discriminate toward business/
# ownership, H2/H9/H5 alone do not) and #17 (break a broad "favorable
# window" into which specific business activity it actually supports).
#
# Deliberately implemented as a POST-HOC ANNOTATION over the already-
# computed window evidence text, not a change to timing.py's shared
# _label_for_net()/_compute_windows_and_status() -- that function has no
# venture_type parameter and is used identically for job and business
# windows; rewriting its labeling logic risked silently changing job-mode
# window counts/labels too, and the window evidence is unstructured prose
# (house references embedded in f-strings), not a clean per-note house
# tag, so a full pipeline restructure would be needed to gate the LABEL
# itself safely. This instead adds NEW fields alongside the existing,
# unchanged `label`/`net_score` -- nothing already tested is altered,
# but the additional field now lets a reader see whether a "FAVORABLE"
# window is actually business-discriminating or only riding on houses
# job and business would read identically.
_BUSINESS_DISCRIMINATING_HOUSES = {"1", "3", "7", "10", "11"}
_HOUSE_TOKEN_RE = re.compile(r"H(\d{1,2})")

_BUSINESS_ACTIVITY_HOUSE_MAP = (
    ("business_registration_or_launch", {"1", "10"}),
    ("client_or_partner_acquisition", {"3", "7", "11"}),
    ("partnership_formation", {"7"}),
    ("capital_deployment_or_investment", {"2", "8"}),
    ("expansion_or_scaling", {"11"}),
    ("foreign_or_exit_linked", {"9", "12"}),
    ("operational_or_liability_risk", {"6", "8", "12"}),
)


def _annotate_window_business_relevance(window: Dict[str, Any]) -> Dict[str, Any]:
    """Scans a timed window's evidence text for house-number mentions
    (H1, H7, H10, ... as they already appear in timing.py's evidence
    strings) and adds business_relevance/suggested_business_activities
    fields without touching the window's existing label/net_score. See
    the module-level comment above _BUSINESS_DISCRIMINATING_HOUSES for
    why this is a post-hoc annotation rather than a change to the shared
    labeling function itself.

    v38 audit fix (#25, user-caught, real logic defect): this previously
    scanned the FULL evidence text of the window -- including KP FINAL
    ARBITER, Jaimini activation, and transit/trigger lines that are OTHER
    methods layered into the same window, not the actual dasha lord's own
    house rulership. A generic KP sentence mentioning "business cusp
    H7/H11/H2/H10" (which fires for almost any KP-active window, favorable
    or not) could make an otherwise weak or even negative window look
    BUSINESS_DISCRIMINATING and generate launch/partnership/expansion
    activity suggestions the dasha lord's own evidence never supported --
    e.g. a negative-net Venus-Ketu window still got launch/partnership
    suggestions purely from a co-present KP line. Restricted now to the
    SAME genuine dasha-lord-house-rulership evidence lines already used by
    _dasha_vote() (lines starting with "AD lord"/"MD lord"), so business
    relevance and activity suggestions reflect what the active dasha/
    antardasha LORD itself rules, not any house number appearing anywhere
    in the window's combined evidence."""
    dasha_lord_evidence = [
        str(e) for e in window.get("evidence", [])
        if str(e).lower().startswith(("ad lord", "md lord"))
    ]
    evidence_text = " ".join(dasha_lord_evidence)
    houses_mentioned = set(_HOUSE_TOKEN_RE.findall(evidence_text))
    discriminating_present = bool(houses_mentioned & _BUSINESS_DISCRIMINATING_HOUSES)

    if not houses_mentioned:
        relevance = "NO_HOUSE_EVIDENCE"
    elif discriminating_present:
        relevance = "BUSINESS_DISCRIMINATING"
    else:
        relevance = "SHARED_HOUSE_ONLY"  # e.g. H2/H9-only evidence -- as favorable for employment as for business, not a business-specific signal

    activities = [
        name for name, houses in _BUSINESS_ACTIVITY_HOUSE_MAP
        if houses & houses_mentioned
    ]

    return {
        **window,
        "business_houses_mentioned": sorted(houses_mentioned, key=int),
        "business_relevance": relevance,
        "suggested_business_activities": activities,
    }


_GAIN_HOUSES = {"6", "11"}
_EXPANSION_HOUSES = {"9"}
_OBLIGATION_HOUSES = {"12"}


def _annotate_window_gain_expenditure_tension(window: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    """Additive-only window annotation (audit item 8): timing.py's shared
    _label_for_net() labels a window STRONG_FAVORABLE/FAVORABLE/MIXED/
    CAUTION/HIGH_RISK from a single net score -- prior passes (v33, v38)
    deliberately declined to touch that shared threshold function itself
    since job and business modes both depend on it. This instead mirrors
    _annotate_window_business_relevance()'s pattern: a SEPARATE, purely
    additive per-window flag computed from the window's own MD/AD lords'
    real house rulership and D1 strength, layered on top of the existing
    label rather than replacing it.

    Detects a genuine "gains WITH obligations" tension when one dasha lord
    (MD or AD) rules a gains house (6th/11th) and is placed in an
    expansion house (9th -- institutional/growth reach), while the OTHER
    dasha lord rules a capital/initiative-relevant house and is placed in
    an obligation house (12th -- expenditure/loss/foreign) with WEAK D1
    strength. This is a real, chart-computed structural tension (gains
    likely accompany real cost/obligation/delayed-collection during this
    specific period), distinct from -- and not a replacement for -- the
    window's own STRONG_FAVORABLE/FAVORABLE/MIXED/CAUTION/HIGH_RISK label.
    """
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}

    def _lord_houses(planet: str) -> set:
        return {h for h in ("1","2","3","4","5","6","7","8","9","10","11","12")
                if house_lords.get(h, house_lords.get(int(h), "")) == planet}

    md_lord, ad_lord = window.get("md_lord", ""), window.get("ad_lord", "")
    tension_flag = False
    detail = None
    for gain_lord, other_lord in ((md_lord, ad_lord), (ad_lord, md_lord)):
        if not gain_lord or not other_lord or gain_lord == other_lord:
            continue
        gain_lord_rules = _lord_houses(gain_lord)
        other_lord_rules = _lord_houses(other_lord)
        gain_lord_house = planet_house.get(gain_lord, 0)
        other_lord_house = planet_house.get(other_lord, 0)
        if not (gain_lord_rules & _GAIN_HOUSES):
            continue
        if str(gain_lord_house) not in _EXPANSION_HOUSES:
            continue
        if not (other_lord_rules & {"1", "2", "10", "11"}):
            # "capital/initiative significator" heuristic: the other lord
            # must rule a house genuinely tied to capital/initiative/status
            # to be a meaningful countervailing signal, not any lord at all.
            continue
        if str(other_lord_house) not in _OBLIGATION_HOUSES:
            continue
        other_lord_strength = _house_lord_strength(payload, int(sorted(other_lord_rules)[0]))
        if other_lord_strength >= 0.5:
            continue  # other lord isn't actually weak here -- no tension
        tension_flag = True
        detail = (
            f"{gain_lord} (rules H{'/H'.join(sorted(gain_lord_rules & _GAIN_HOUSES))}) sits in H{gain_lord_house} "
            f"(institutional reach/expansion), while {other_lord} (rules H{'/H'.join(sorted(other_lord_rules))}, "
            f"capital/initiative significator) occupies H{other_lord_house} (expenditure/obligations) with weak "
            f"D1 strength ({round(other_lord_strength, 2)}) -> gains during this period likely come WITH "
            "expenditure/obligations/delayed collection/heavy operational responsibility, not cleanly free gains."
        )
        break

    return {
        **window,
        "gain_expenditure_tension": tension_flag,
        "gain_expenditure_tension_detail": detail,
    }


def compute_business_prediction(
    payload: Any,
    top_n_sectors: int = 5,
    venture_type: str = "business",
    years_ahead: int = 15,
    as_of_date: Optional[date] = None,
    attach_provenance: bool = True,
    enable_llm_narrative: bool = False,
    partner_payload: Optional[Any] = None,
    candidate_year_range: Optional[Tuple[int, int]] = None,
    candidate_muhurta_window: Optional[Tuple[Any, Any, str, Dict[str, Any]]] = None,
    financial_readiness_inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full business-prediction pipeline for a chart payload.

    Parameters
    ----------
    venture_type : one of "business" (own venture/partnership),
        "independent" (solo practice/consulting), "family_business".
        Determines which compute_business_mode_gate() score gates the
        recommendation -- these are different prediction targets and
        should not be collapsed into a single max() as the v1 module did.
    years_ahead, as_of_date : bound the timed-window forecast period
        (default: today .. +15y) instead of scoring the full dasha
        lifetime.

    Returns
    -------
    {
      "mode_gate": <compute_business_mode_gate(payload) output -- v8-consistent
          dignity-gated/D9-D10-corroborated replacement for the legacy
          jyotish.employment_mode.compute_employment_mode()>,
      "significators": <score_business_significators(payload) output>,
      "top_sectors": [ up to top_n_sectors ranked sector dicts ],
      "timed_windows": [ AD windows with net_score/label/evidence ],
      "recommendation": {
          "venture_type": str,
          "proceed": bool,
          "heuristic_tier": str,       # was "confidence" -- renamed to avoid
                                        # implying statistical confidence
          "confidence": str,           # backward-compatible alias of heuristic_tier
          "comparative_advantage": bool,  # gate_score exceeds employment_score
                                           # by the required margin (see below)
          "hybrid_suggested": bool,    # business/employment scores are close
                                        # enough that a pure "proceed"/"deny"
                                        # binary would overstate the read
          "reasoning": str,
      },
      "model_status": "EXPERIMENTAL_HEURISTIC",
      "calibration_status": ...,
      "rule_pack_version": ...,
    }
    """
    validate_request(venture_type, _VENTURE_TYPE_TO_GATE_KEY, years_ahead, top_n_sectors, as_of_date)

    # Engineering audit fix #10: top-level parameter validation. Previously
    # years_ahead/top_n_sectors/as_of_date were passed straight through with
    # no sanity checks -- a negative/zero/absurdly-large years_ahead, a
    # negative top_n_sectors, or a wrong-typed as_of_date (e.g. a string)
    # would either silently produce a nonsensical forecast window or fail
    # deep inside the pipeline with a confusing traceback far from the
    # actual mistake. Matches the style of the existing venture_type check
    # immediately above (raise clear, actionable errors right at entry).
    evidence_sufficiency, decision_status = assess_evidence_sufficiency(payload)

    # Engineering audit fix #3 (silent neutral fallbacks on missing data):
    # a lightweight, top-level input-contract check. Several downstream
    # computations degrade to a silent neutral midpoint (e.g.
    # chart_data_quality's own "not reported" 0.85 discount, current_
    # timing_readiness's 40.0 neutral-low default, synastry's score_0_20=10
    # "neutral midpoint assigned" fallback) when mandatory inputs for that
    # output FAMILY are missing -- which is the right degrade-gracefully
    # behavior for a single missing field deep in one helper, but gives no
    # top-level, honest signal that an entire output family (e.g. "timing")
    # is running on insufficient evidence for THIS chart. This does not
    # remove any of those existing fallbacks (too invasive/risky to rip out
    # for a bounded engineering pass, per instructions); it only adds an
    # explicit, inspectable `evidence_sufficiency` section to the result so
    # a reader can tell which output families are well-supported vs running
    # on a neutral default, instead of having to infer it from individual
    # midpoint-looking numbers.

    # v-audit fix (item 4, hard ABSTAIN): evidence_sufficiency (above) has
    # always been able to tell a reader that "structural_recommendation" is
    # running on INSUFFICIENT_EVIDENCE, but the pipeline still computed and
    # returned a full-looking recommendation regardless -- exactly the
    # failure mode a real chart hit this session (a chart JSON whose D1
    # data landed under a schema variant the parser didn't yet handle
    # produced house_lords/planet_house/planet_dignities that were all
    # effectively empty, and the engine still emitted a confident
    # business_promise=43.1/job_promise=32.9/action_level=
    # PILOT_WHILE_RETAINING_INCOME built almost entirely off neutral
    # defaults). This does not change any scoring internals or remove the
    # existing graceful-degradation behavior (still needed for the many
    # OTHER, narrower evidence families the sufficiency table tracks) -- it
    # adds one explicit top-level decision_status field, and downstream
    # (once action_level is computed) that field is used to hard-override
    # action_level to an unambiguous ABSTAIN value when the core D1
    # structural inputs -- house_lords, planet_house, planet_dignities,
    # the three things nearly EVERY significator/scoring function in this
    # package reads first -- are missing, rather than letting a reader
    # mistake a neutral-default-driven number for a real read.
    # Engineering audit fix #9: clear the module-level diagnostics
    # collector at the very start of each call so degrade-gracefully
    # `except Exception` blocks elsewhere in the pipeline (timing.py,
    # synastry.py, yogas.py, ashtakavarga_timing.py, ...) that record a
    # structured diagnostic entry (see constants.py's _record_diagnostic)
    # start from a clean slate; drained into result["diagnostics"] below.
    _reset_diagnostics()

    calculation_context = CalculationContext(payload)
    mode_gate = calculation_context.fact(
        "mode_gate", lambda: compute_business_mode_gate(payload, as_of_date=as_of_date)
    )
    significators = calculation_context.fact(
        "significators", lambda: score_business_significators(payload)
    )

    # Engineering audit fix #5 (sector ranking post-hoc rules): the
    # foreign-trade domestic-geographic discount and the D10 operating-
    # model alignment bonus used to be applied by THIS function, AFTER
    # calling rank_business_sectors_with_status(), by directly mutating
    # each row's score and re-sorting -- meaning sector_score()/
    # rank_business_sectors_with_status() and the actual top_sectors
    # ranking were two different computations that happened to agree only
    # because engine.py re-derived the same adjustment logic a second time.
    # Both adjustments now live inside sector_score() itself (see
    # sectors.py); this just computes the two chart-level inputs they need
    # (mode_gate's own geographic_preference, D10-native's own best-fit
    # operating model) and forwards them straight into the single ranking
    # call below, so sector_score() and top_sectors are always the same
    # function with no separate orchestration-layer rule application.
    _geo_pref = mode_gate.get("geographic_preference", "")
    _d10_model = _business_operating_model_d10(payload)
    _d10_best_fit = _d10_model.get("best_fit") if _d10_model else None
    top_sectors, sbc_status = rank_business_sectors_with_status(
        payload, top_n_sectors=None,
        geographic_preference=_geo_pref,
        d10_operating_model_best_fit=_d10_best_fit,
    )

    # v42 audit fix: capture the full, already-bonus-applied ranked list
    # BEFORE truncating to top_n_sectors, so diversify_sector_ranking()
    # below sees every sector (needed to build accurate family_groups /
    # hidden-count notes) even when the caller asked for a small
    # top_n_sectors. This is purely additive -- top_sectors itself is
    # still truncated exactly as before, unchanged in shape/values, for
    # backward compatibility with existing callers/tests.
    _full_ranked_sectors = list(top_sectors)
    diversified_sectors = diversify_sector_ranking(_full_ranked_sectors, max_per_family=1, top_n=8)

    top_sectors = top_sectors[:top_n_sectors]
    # Single calendar computation shared by both timing_status and
    # timed_windows -- fixes the earlier duplicate-computation risk where
    # _timing_computation_status() and _business_ad_windows() each called
    # _dasha_calendar() independently and could disagree if one failed and
    # the other didn't.
    timed_windows, timing_status = _compute_windows_and_status(payload, years_ahead=years_ahead, as_of_date=as_of_date)
    # v34 audit fix: annotate (not relabel) each window with whether its
    # supporting evidence actually mentions a business-discriminating
    # house (H1/H3/H7/H10/H11) vs only houses shared identically with
    # employment (H2/H9/H5 alone) -- see _annotate_window_business_relevance.
    timed_windows = [_annotate_window_business_relevance(w) for w in timed_windows]
    timed_windows = [_annotate_window_gain_expenditure_tension(w, payload) for w in timed_windows]
    if timing_status["status"] == "OK" and not timed_windows:
        # Calendar computed fine, just no window cleared the "has evidence"
        # bar within the requested horizon -- a real astrological finding,
        # distinct from every failure mode above it.
        timing_status = {**timing_status, "status": "OK_NO_SIGNIFICANT_WINDOWS_IN_HORIZON"}

    gate_score = mode_gate.get(_VENTURE_TYPE_TO_GATE_KEY[venture_type], 0)
    employment_score = mode_gate.get("employment_score", 0)
    strength = significators["heuristic_relative_strength_0_100"]

    # v22 audit fix (real bug, not a scope narrowing): contradictions used
    # to be computed AFTER `recommendation`/`proceed` were already
    # finalized (originally ~36 lines further down), so a chart the engine
    # itself flags with a real contradiction -- e.g. "H7 strong but no
    # H2/H10/H11 connection" -- could still return proceed=True, because
    # the contradiction layer only ever fed `contradiction_findings` and
    # the named-fields confidence math, never the headline recommendation.
    # D24/kp10 (both cheap, pure-function computations) and the
    # contradiction penalties now run BEFORE the proceed decision, and the
    # business/employment penalty totals are subtracted from gate_score/
    # employment_score before they're used for the proceed/margin/tier
    # calculation -- so a chart with a flagged contradiction now has a
    # strictly harder time reaching "proceed".
    d24_status = _d24_competency_status(payload)
    # v-audit fix (item 6): the fuller D24 house-graph analysis (Lagnesh +
    # H4/H5/H9/H10 + occupants + one-hop dispositor + D1/D10 coherence) --
    # additive, does not replace or feed into d24_status/
    # business_execution_capacity in this pass (see docstring on
    # _d24_full_analysis for why: kept isolated as a citable diagnostic
    # first, so it can be spot-checked against real charts before anything
    # downstream depends on its numbers).
    d24_full = _d24_full_analysis(payload)
    kp10 = _kp_10th_cusp_job_vs_business(payload)
    d60_status = _d60_confirmation_status(payload)
    d11_status = _d11_gains_status(payload)
    contradictions = _contradiction_penalties(payload, significators, d24_status, kp10, mode_gate=mode_gate, d60_status=d60_status, timed_windows=timed_windows)
    penalty_by_mode: Dict[str, float] = {}
    for p in contradictions:
        penalty_by_mode[p["mode"]] = penalty_by_mode.get(p["mode"], 0.0) + p["weight"]
    business_contradiction_penalty = penalty_by_mode.get("business", 0.0)
    employment_contradiction_penalty = penalty_by_mode.get("employment", 0.0)
    penalized_gate_score = max(0.0, gate_score - business_contradiction_penalty)
    penalized_employment_score = max(0.0, employment_score - employment_contradiction_penalty)

    # These cutoffs are an explicit, documented, UNCALIBRATED heuristic --
    # not derived from a labeled dataset, backtest, or classical citation.
    # See CALIBRATION_STATUS. They exist to produce a decodable tier from
    # two already-computed scores, nothing more.
    #
    # Comparative business-vs-employment margin (audit finding #2): absolute
    # business viability (gate_score/strength) is a different question from
    # whether business is the BETTER mode versus employment for this chart.
    # A chart can clear the absolute bar while employment is still dominant
    # by a wide margin -- "proceed" must require the venture-type gate score
    # to beat employment by a minimum margin, not merely clear its own floor.
    _COMPARATIVE_MARGIN = DECISION_POLICY.comparative_margin
    margin = penalized_gate_score - penalized_employment_score
    comparative_advantage = margin >= _COMPARATIVE_MARGIN
    hybrid_suggested = (
        abs(margin) < _COMPARATIVE_MARGIN
        and penalized_gate_score >= DECISION_POLICY.hybrid_min_score
        and penalized_employment_score >= DECISION_POLICY.hybrid_min_score
    )

    absolute_proceed = (
        penalized_gate_score >= DECISION_POLICY.absolute_proceed_gate_floor
        and strength >= DECISION_POLICY.absolute_proceed_strength_floor
    )
    proceed = absolute_proceed and comparative_advantage

    # v25 audit fix: spec section 7's KN Rao-style validation sequence
    # closes with an explicit, separately-named principle -- "reject
    # conclusions contradicted by the main chart" -- distinct from every
    # other contradiction control, which only ever SUBTRACTS points.
    # Previously even the strongest possible contradiction (D1 structurally
    # promising business ownership while D10's own execution graph reads
    # net OPERATIONAL/SERVICE, i.e. the promise chart and the execution
    # chart actively disagree on the operating structure) could still be
    # outvoted by a large enough raw score and return proceed=True. That
    # specific pattern -- contradiction check #8b in _contradiction_penalties,
    # "D1 and D10 give OPPOSING operating models" on the business side --
    # is the one case in this engine's whole contradiction set that is a
    # direct chart-vs-chart CONTRADICTION (not merely under-supported
    # evidence), so it now hard-vetoes proceed for ownership-track venture
    # types (business/family_business) regardless of score, rather than
    # only subtracting its fixed 7-point weight.
    # Engineering audit fix #11: this used to substring-search the
    # human-readable `note` text for three separate fragile phrase
    # fragments ("OPPOSING operating models", "D1: ownership", "D1 leans
    # BUSINESS") to detect this one specific contradiction -- any future
    # wording edit to that note in contradictions.py would silently break
    # the veto with no import-time or type error. contradictions.py now
    # attaches a stable, machine-readable `id` to every contradiction
    # record; this matches on that id instead.
    # Primary match: stable id set by contradictions.py. Fallback: legacy
    # substring match on the note text, kept ONLY so that callers/tests that
    # construct a contradiction dict by hand (without an `id` key, e.g. by
    # mocking _contradiction_penalties) still trigger the veto -- this is a
    # compatibility shim, not the source of truth; contradictions.py should
    # always set `id` going forward.
    def _is_operating_model_conflict(c: Dict[str, Any]) -> bool:
        if c.get("id") == "D1_D10_OPERATING_MODEL_CONFLICT":
            return True
        if "id" in c:
            return False
        note = c.get("note", "")
        return "OPPOSING operating models" in note and "D1 leans BUSINESS" in note

    veto_note = next(
        (c["note"] for c in contradictions
         if c["mode"] == "business" and _is_operating_model_conflict(c)),
        None,
    )
    rejected_by_main_chart = bool(veto_note) and venture_type in ("business", "family_business")
    if rejected_by_main_chart:
        proceed = False

    if (
        proceed
        and penalized_gate_score >= DECISION_POLICY.high_tier_gate_floor
        and strength >= DECISION_POLICY.high_tier_strength_floor
        and margin >= DECISION_POLICY.high_tier_margin_floor
    ):
        tier = "HIGH"
    elif proceed:
        tier = "MODERATE"
    else:
        tier = "LOW"

    reasoning = (
        f"venture_type={venture_type} gate_score={gate_score} employment_score={employment_score} "
        f"contradiction_penalty(business={business_contradiction_penalty}, employment={employment_contradiction_penalty}) "
        f"penalized_gate_score={penalized_gate_score} penalized_employment_score={penalized_employment_score} "
        f"margin={margin} (required>={_COMPARATIVE_MARGIN}) "
        f"significator_strength={strength} thresholds(uncalibrated)=40/35, tier_thresholds=60/55/margin>=20. "
        + (f"REJECTED BY MAIN CHART (KN Rao principle: reject conclusions contradicted by the main chart) -- {veto_note}. " if rejected_by_main_chart else "")
        + f"{CALIBRATION_STATUS}"
    )

    recommendation = {
        "venture_type": venture_type,
        "proceed": proceed,
        "heuristic_tier": tier,
        "confidence": tier,  # backward-compatible alias
        "comparative_advantage": comparative_advantage,
        "hybrid_suggested": hybrid_suggested,
        "reasoning": reasoning,
        "gate_score": gate_score,
        "employment_score": employment_score,
        "penalized_gate_score": penalized_gate_score,
        "penalized_employment_score": penalized_employment_score,
        "contradiction_penalty_applied": {"business": business_contradiction_penalty, "employment": employment_contradiction_penalty},
        "rejected_by_main_chart": rejected_by_main_chart,
        "rejected_by_main_chart_reason": veto_note,
    }

    method_status = _compute_method_status(payload, timed_windows, timing_status, sbc_status, significators=significators, mode_gate=mode_gate)

    # v17: sign-modality/operating-model layers, then the nine
    # separately-named promise/fit/confidence fields the spec requires,
    # computed from all of the above plus the existing mode_gate/
    # significators. (d24_status/kp10/d60_status/contradictions were moved
    # above, to run before the recommendation decision -- see the v22 fix
    # note.)
    sign_modality = _sign_modality_profile(payload)
    operating_model = _business_operating_model(payload)
    operating_model_d10 = _business_operating_model_d10(payload)
    # Item 7 audit fix: D1 (aspirational structure) and D10 (execution
    # manifestation) best_fit rankings previously had no reconciliation --
    # see operating_models.py::_operating_model_synthesis for the full
    # policy (agreement / compatible-hybrid label / D10-precedence framing
    # when no principled label exists).
    operating_model_synthesis = _operating_model_synthesis(payload)
    named_fields = _compute_named_promise_fields(
        payload, mode_gate, significators, top_sectors, timed_windows, timing_status,
        method_status, d24_status, d60_status, kp10, sign_modality, contradictions,
    )

    # v31 audit fix: hybrid_suggested (above) was computed purely from the
    # legacy gate_score/employment_score margin, entirely independent of
    # business_advantage_label (which is derived from business_promise/
    # job_promise -- a separately-computed, later system). A chart could
    # therefore show business_advantage_label=HYBRID_OR_INCONCLUSIVE (a
    # 2-3 point margin) in the headline output while hybrid_suggested was
    # still False, because the legacy margin check disagreed -- a real,
    # user-identified output defect (two unrelated margin computations
    # producing contradictory guidance on whether to suggest a hybrid
    # path). Any inconclusive/slight-advantage label now also forces
    # hybrid_suggested=True, regardless of what the legacy margin said.
    _HYBRID_ADVISORY_LABELS = {
        "HYBRID_OR_INCONCLUSIVE", "SLIGHT_BUSINESS_ADVANTAGE", "SLIGHT_JOB_ADVANTAGE",
    }
    if named_fields.get("business_advantage_label") in _HYBRID_ADVISORY_LABELS and not recommendation["hybrid_suggested"]:
        recommendation["hybrid_suggested"] = True
        recommendation["reasoning"] += (
            f" | hybrid_suggested overridden to True: business_advantage_label="
            f"{named_fields.get('business_advantage_label')} (margin={named_fields.get('business_advantage_margin')}) "
            f"indicates the layered promise scores are too close to call, even though the legacy "
            f"gate_score/employment_score margin alone did not."
        )

    # v34 audit fix (#1 -- "three competing decision systems"): this engine
    # genuinely has two separate scoring tracks -- the legacy mode_gate
    # accumulation (gate_score/employment_score, e.g. 100 vs 65) that
    # actually drives recommendation.proceed/heuristic_tier, and the
    # declared-layer-weight system (business_promise/job_promise, e.g.
    # 60.1 vs 57.5) that drives business_advantage_label. A full merge into
    # one hierarchy was assessed as too large and too test-invasive to make
    # safely (recommendation.proceed/tier are load-bearing for dozens of
    # existing tests against the legacy scores specifically) and is NOT
    # done here. Instead, authoritative_recommendation adds a single,
    # clearly-labeled THIRD field -- not a third competing system, but an
    # explicit, inspectable RECONCILIATION -- that states which of the two
    # tracks a reader should trust as primary (the layered business_promise/
    # job_promise system, since it's the one this engine's own newer
    # calibration/contradiction-penalty work targets) and flags when the
    # two tracks actually disagree on direction, so that disagreement is
    # surfaced explicitly rather than left for the reader to notice by
    # comparing two differently-named fields themselves.
    _ADVANTAGE_LABEL_TO_VERDICT = {
        "STRONG_BUSINESS_ADVANTAGE": "PURSUE_BUSINESS",
        "STRONG_BUSINESS_ADVANTAGE_BUT_BELOW_ABSOLUTE_FLOOR": "PURSUE_BUSINESS_CAUTIOUSLY",
        "MODERATE_BUSINESS_ADVANTAGE": "PURSUE_BUSINESS",
        "SLIGHT_BUSINESS_ADVANTAGE": "HYBRID_LEANING_BUSINESS",
        "HYBRID_OR_INCONCLUSIVE": "HYBRID",
        "SLIGHT_JOB_ADVANTAGE": "HYBRID_LEANING_JOB",
        "MODERATE_JOB_ADVANTAGE": "STAY_EMPLOYED",
        "STRONG_JOB_ADVANTAGE": "STAY_EMPLOYED",
        "WEAK_OR_INCONCLUSIVE": "HYBRID",
    }
    _advantage_label = named_fields.get("business_advantage_label")
    _layered_verdict = _ADVANTAGE_LABEL_TO_VERDICT.get(_advantage_label, "HYBRID")
    _layered_favors_business = _layered_verdict in ("PURSUE_BUSINESS", "PURSUE_BUSINESS_CAUTIOUSLY", "HYBRID_LEANING_BUSINESS")
    _legacy_favors_business = bool(recommendation["proceed"])
    _tracks_agree = _layered_favors_business == _legacy_favors_business

    # v46 audit fix (item 4, user-directed: "make layered promise score
    # authoritative"): supersedes the v35 narrow gate below. Previously only
    # the single sharpest disagreement direction (legacy proceed=True vs
    # layered STAY_EMPLOYED) could override recommendation.proceed/tier --
    # every other disagreement (HYBRID, HYBRID_LEANING_JOB, or the reverse
    # direction where legacy says False but layered favors business) was
    # left unreconciled, silently leaving two different verdicts live in the
    # same output. Per the explicit user decision to make the layered
    # business_promise/job_promise track authoritative, ANY disagreement
    # between the two tracks now has recommendation.proceed/heuristic_tier/
    # confidence set FROM the layered verdict, not the legacy gate_score/
    # employment_score track. The legacy track's own numbers
    # (gate_score/employment_score/original proceed) are preserved
    # unmodified in authoritative_recommendation's legacy_track_* fields
    # below, so nothing about the legacy computation itself is lost or
    # silently discarded -- only which track WINS when they disagree has
    # changed. The D10 hard veto (rejected_by_main_chart) still takes
    # precedence over both tracks, unchanged.
    _LAYERED_VERDICT_TO_TIER = {
        "PURSUE_BUSINESS": "HIGH",
        "PURSUE_BUSINESS_CAUTIOUSLY": "MODERATE",
        "HYBRID_LEANING_BUSINESS": "MODERATE",
        "HYBRID": "LOW",
        "HYBRID_LEANING_JOB": "LOW",
        "STAY_EMPLOYED": "LOW",
    }
    _legacy_proceed_before_layered_gate = recommendation["proceed"]
    _downgraded_by_layered_system = (
        not _tracks_agree and not rejected_by_main_chart
    )
    if _downgraded_by_layered_system:
        recommendation["proceed"] = _layered_favors_business
        recommendation["heuristic_tier"] = _LAYERED_VERDICT_TO_TIER.get(_layered_verdict, "LOW")
        recommendation["confidence"] = recommendation["heuristic_tier"]
        recommendation["reasoning"] += (
            f" | RECONCILED BY LAYERED SYSTEM (v46: layered track is authoritative "
            f"on disagreement): legacy mode_gate read proceed="
            f"{_legacy_proceed_before_layered_gate} (gate_score={gate_score} vs "
            f"employment_score={employment_score}) but the declared-layer-weight "
            f"system's own verdict is {_layered_verdict} (business_promise="
            f"{named_fields.get('business_promise')} vs job_promise="
            f"{named_fields.get('job_promise')}, label={_advantage_label}) -- "
            f"proceed/tier set from the layered verdict "
            f"(proceed={recommendation['proceed']}, tier={recommendation['heuristic_tier']})."
        )

    # v38 audit fix (#2, user-caught): authoritative_recommendation exposed
    # a Boolean final_proceed even for a HYBRID verdict, which a reader
    # could reasonably (and wrongly) read as "approved to leave employment
    # and start a business" -- a Boolean is too coarse for a verdict that
    # is explicitly NOT a clear win either way. This adds a graded
    # action_level derived from the SAME already-computed verdict/label/
    # floor fields (no new scoring), so HYBRID verdicts get an explicit
    # "pilot only, don't exit employment yet" action rather than a bare
    # True/False that looks identical to a strong, unambiguous PROCEED.
    _strong_floor_met = bool(named_fields.get("strong_business_absolute_floor_met"))

    # P0 fix (audit finding #3): FULL_TRANSITION_SUPPORTED used to be
    # derived purely from the structural layered verdict + absolute floor,
    # with no requirement that CURRENT timing actually be favorable --
    # so a chart could be told to leave employment during an astrologically
    # unfavorable/unestablished window. current_timing_readiness (0-100,
    # the fraction of near-term timed windows this engine itself scored
    # favorable) is now a hard gate on the single most consequential action
    # level. A chart that structurally qualifies but whose near-term timing
    # is not established still gets a real answer (PILOT_WHILE_RETAINING_INCOME),
    # just not the "go now" tier.
    _TIMING_READINESS_FLOOR_FOR_TRANSITION = DECISION_POLICY.transition_readiness_floor
    _timing_readiness = named_fields.get("current_timing_readiness")
    _timing_blocks_transition = (
        _timing_readiness is None or _timing_readiness < _TIMING_READINESS_FLOOR_FOR_TRANSITION
    )

    # v-audit fix (item 6 continuation): D24 competency previously affected
    # only business_execution_capacity's multiplicative factor and never
    # touched the business-vs-job promise or the transition action_level --
    # a chart could be told a debilitated D24 10th lord ("competency/
    # training readiness ... constrained") and still receive
    # FULL_TRANSITION_SUPPORTED. d24_status.factor < 1.0 only fires on an
    # actual DEBILITATED reading (see _d24_competency_status -- NO_DATA and
    # ordinary dignity both return factor 1.0), so this gate only blocks the
    # sharpest, most concrete competency red flag, not routine missing data.
    _D24_COMPETENCY_FACTOR_FLOOR = DECISION_POLICY.d24_competency_factor_floor
    _d24_factor = d24_status.get("factor", 1.0)
    _competency_blocks_transition = _d24_factor < _D24_COMPETENCY_FACTOR_FLOOR

    # v-audit fix (item 12): previously only ONE specific pattern -- the
    # D1/D10 operating-model conflict (check_id D1_D10_OPERATING_MODEL_
    # CONFLICT) -- could hard-veto anything; every other contradiction this
    # engine detects (weak Lagna, poor H2 retention, D9 durability cautions,
    # unverified KP, D24 constraints, etc.) only ever subtracted fixed
    # points from the score, meaning a chart could accumulate several
    # serious, specifically-flagged business contradictions and still reach
    # FULL_TRANSITION_SUPPORTED as long as its raw score cleared the floor.
    # Rather than hand-picking new bespoke thresholds per contradiction type
    # (risking under- or over-fitting rules this pass has no calibration
    # basis for), this gates on the AGGREGATE business contradiction penalty
    # already computed above (business_contradiction_penalty) -- a chart
    # whose flagged contradictions add up to a large total penalty has, by
    # this engine's own evidence, several independent reasons for caution,
    # not just a low raw score. Uncalibrated threshold, documented like the
    # other cutoffs in this function.
    _CONTRADICTION_SEVERITY_FLOOR_FOR_TRANSITION = DECISION_POLICY.contradiction_transition_floor
    _contradictions_block_transition = business_contradiction_penalty >= _CONTRADICTION_SEVERITY_FLOOR_FOR_TRANSITION

    if (
        _layered_verdict in ("PURSUE_BUSINESS",) and _strong_floor_met
        and not _timing_blocks_transition and not _competency_blocks_transition
        and not _contradictions_block_transition
    ):
        _action_level = "FULL_TRANSITION_SUPPORTED"
    elif _layered_verdict in ("PURSUE_BUSINESS",) and _strong_floor_met:
        # Structurally qualified but timing, D24 competency readiness, or
        # the aggregate contradiction severity does not clear its floor --
        # downgraded rather than silently approved.
        _action_level = "PILOT_WHILE_RETAINING_INCOME"
    elif _layered_verdict in ("PURSUE_BUSINESS", "PURSUE_BUSINESS_CAUTIOUSLY", "HYBRID_LEANING_BUSINESS"):
        _action_level = "PILOT_WHILE_RETAINING_INCOME"
    elif _layered_verdict == "HYBRID":
        _action_level = "PILOT_OR_SIDE_VENTURE"
    elif _layered_verdict == "HYBRID_LEANING_JOB":
        _action_level = "VALIDATE_BEFORE_COMMITTING"
    else:
        _action_level = "EMPLOYMENT_EXIT_NOT_SUPPORTED"

    # v-audit fix (item 2, abstention half of birth-time sensitivity): a
    # KNOWN birth-time uncertainty of >=10 minutes is large enough to move
    # D10/D24/D60 house placements and KP sub-lords across a boundary (see
    # named_fields["birth_time_sensitivity"], computed in scoring.py) -- a
    # verdict this sensitive to inputs the engine cannot verify should never
    # reach the single most actionable tier (FULL_TRANSITION_SUPPORTED,
    # "leave your job") without qualification. This downgrades that one
    # tier specifically, rather than blocking the recommendation outright,
    # since the underlying verdict computation is otherwise unaffected --
    # a chart this uncertain can still clearly favor business, just not
    # with the confidence FULL_TRANSITION_SUPPORTED implies.
    _bts = named_fields.get("birth_time_sensitivity") or {}
    _birth_time_downgrade = bool(
        _bts.get("uncertainty_minutes") is not None
        and _bts.get("uncertainty_minutes", 0) >= DECISION_POLICY.birth_time_transition_downgrade_minutes
    )

    # v-audit fix (astrological completeness, item 27 -- "no universal
    # birth-time/divisional-boundary stability abstention"): the downgrade
    # above only catches a KNOWN, REPORTED uncertainty window >=10 minutes.
    # named_fields["divisional_boundary_sensitivity"] (scoring.py) catches
    # the disclosed gap in that check itself: a planet sitting a fraction
    # of a degree from a D3/D4/D7/D9/D10/D24 division boundary is fragile
    # to birth-time error REGARDLESS of what the reported uncertainty
    # window claims (including a chart that reports zero uncertainty).
    # Applies the exact same narrow, non-destructive downgrade -- only the
    # single most-actionable tier is affected, never a hard abstention --
    # so this cannot over-trigger into blocking a recommendation outright
    # even though boundary-proximity flags are a common, often-immaterial
    # occurrence across real charts (9 planets x 6 vargas per chart).
    _dbs = named_fields.get("divisional_boundary_sensitivity") or {}
    _boundary_downgrade = bool(_dbs.get("any_flagged"))
    if (_birth_time_downgrade or _boundary_downgrade) and _action_level == "FULL_TRANSITION_SUPPORTED":
        _action_level = "PILOT_WHILE_RETAINING_INCOME"

    # v-audit fix (item 4, hard ABSTAIN): overrides action_level LAST, after
    # every other adjustment above, so a chart with insufficient D1 data can
    # never present as anything but an explicit abstention regardless of
    # what verdict/floor/birth-time logic computed off its neutral defaults.
    if decision_status == "ABSTAIN_INSUFFICIENT_D1_DATA":
        _action_level = "ABSTAIN_INSUFFICIENT_DATA"

    _employment_exit_supported = _action_level == "FULL_TRANSITION_SUPPORTED"

    # P0 fix (audit finding #4): capital_intensive_launch_supported used to
    # be derived from the same structural transition Boolean + absolute
    # floor -- effectively no capital model at all. It is now additionally
    # gated on the wealth/profitability/stability/legal-risk evidence this
    # engine already computes elsewhere (profit_retention, business_
    # stability, d24 competency, legal_dispute_risk), rather than approving
    # a capital-intensive launch purely off the general business-vs-job
    # promise comparison. The optional HARMONIC_11 D11 corroboration is
    # applied when sufficient D1 longitude data exists and blocks the gate
    # when its gains score does not support capital deployment. Missing D11
    # data is disclosed rather than silently treated as affirmative evidence.
    _CAPITAL_PROFIT_RETENTION_FLOOR = DECISION_POLICY.profit_retention_floor
    _CAPITAL_STABILITY_FLOOR = DECISION_POLICY.stability_floor
    _profit_retention = named_fields.get("profit_retention")
    _business_stability = named_fields.get("business_stability")
    _legal_risk_flags = calculation_context.fact(
        "legal_dispute_risk", lambda: detect_legal_dispute_risk(payload)
    )
    _strong_legal_risk = any(r.get("confidence_tier") == "STRONG" for r in _legal_risk_flags)
    # v-audit fix (item 23): D2 (Hora) wealth-flow evidence was already
    # computed and folded into significators/contradictions, but never
    # independently gated capital_intensive_launch_supported -- a chart
    # could clear the H2-based profit_retention floor while D2 net reads
    # strongly negative (Sun-Hora dominance on the wealth significators)
    # and still get capital-launch approval. D2 net is now a dedicated,
    # narrower floor alongside profit_retention/business_stability.
    _D2_NET_FLOOR = DECISION_POLICY.d2_capital_net_floor
    _d2_evidence_for_gate = _d2_native_house_evidence(payload)
    _d2_net_for_gate = sum(w for w, _ in _d2_evidence_for_gate) if _d2_evidence_for_gate else 0.0
    _d2_blocks_capital = bool(_d2_evidence_for_gate) and _d2_net_for_gate < _D2_NET_FLOOR
    # Reuses the same D24 competency-factor floor as the transition gate
    # above (_competency_blocks_transition) -- a debilitated D24 10th lord
    # should block a capital-intensive launch at least as strongly as it
    # blocks a plain employment exit.
    _capital_wealth_model_supported = (
        (_profit_retention is not None and _profit_retention >= _CAPITAL_PROFIT_RETENTION_FLOOR)
        and (_business_stability is not None and _business_stability >= _CAPITAL_STABILITY_FLOOR)
        and not _strong_legal_risk
        and not _competency_blocks_transition
        and not _d2_blocks_capital
        and (d11_status.get("status") != "APPLIED" or bool(d11_status.get("capital_support")))
    )
    _capital_intensive_launch_supported = (
        _employment_exit_supported and _strong_floor_met and _capital_wealth_model_supported
    )
    _capital_readiness_status = (
        "PRELIMINARY_ASTROLOGICAL_SUPPORT_D11_UNAVAILABLE"
        if _capital_intensive_launch_supported and d11_status.get("status") != "APPLIED"
        else "ASTROLOGICAL_SUPPORT"
        if _capital_intensive_launch_supported
        else "NOT_SUPPORTED"
    )
    # Access to investors/other people's money is not an endorsement to
    # accept it.  Once the authoritative capital-readiness gate is known,
    # suppress the bare comparative label even when debt management is
    # above zero; this is especially important for charts with high
    # fundraising capacity but borderline stability/cash flow.
    _exec_components_authoritative = named_fields.get("business_execution_capacity_components", {}) or {}
    if (
        _exec_components_authoritative.get("capital_strategy_lean") == "EXTERNAL_CAPITAL_FAVORED"
        and _capital_readiness_status == "NOT_SUPPORTED"
    ):
        _exec_components_authoritative["capital_strategy_lean"] = "EXTERNAL_CAPITAL_ACCESSIBLE_BUT_NOT_ADVISABLE"
        _exec_components_authoritative["capital_strategy_safety_reason"] = (
            "External-capital access exceeds bootstrap capacity, but the authoritative capital-readiness gate is "
            "NOT_SUPPORTED; do not interpret fundraising accessibility as approval to borrow or accept investment."
        )
    _financial_readiness = evaluate_financial_readiness(
        financial_readiness_inputs, _capital_intensive_launch_supported
    )
    # Issue 9 note: the primary safety gate lives in scoring.py's
    # capital_strategy_lean_for_payload() call, which already downgrades
    # EXTERNAL_CAPITAL_FAVORED to EXTERNAL_CAPITAL_ACCESSIBLE_BUT_NOT_
    # ADVISABLE whenever the chart's own capital_debt_management sub-score
    # is <= 0 (the concrete failure mode this issue was raised against).
    # A broader engine-level cross-check against capital_readiness_status
    # == NOT_SUPPORTED was deliberately NOT layered on top here: that
    # status fails on many otherwise-fine charts for reasons unrelated to
    # debt-management readiness (timing/D24/legal-risk/D2 floors below),
    # and gating on it here would downgrade EXTERNAL_CAPITAL_FAVORED far
    # more often than the specific unsafe pattern this issue describes.
    _capital_model_note = (
        f"capital_intensive_launch_supported requires: employment_exit_supported={_employment_exit_supported}, "
        f"strong_business_absolute_floor_met={_strong_floor_met}, profit_retention={_profit_retention} "
        f"(floor {_CAPITAL_PROFIT_RETENTION_FLOOR}), business_stability={_business_stability} "
        f"(floor {_CAPITAL_STABILITY_FLOOR}), d24_competency_factor={_d24_factor} "
        f"(floor {_D24_COMPETENCY_FACTOR_FLOOR}), d2_hora_net={round(_d2_net_for_gate, 2)} "
        f"(floor {_D2_NET_FLOOR}, only applied when D2 evidence exists), "
        f"strong_legal_dispute_risk_flag={_strong_legal_risk}. "
        f"d11_status={d11_status.get('status')}, d11_construction_policy="
        f"{d11_status.get('construction_policy', 'UNAVAILABLE')}, d11_capital_support="
        f"{d11_status.get('capital_support')}. When APPLIED, the optional HARMONIC_11 D11 gains "
        f"corroboration is a required positive gate; when unavailable, the readiness status explicitly "
        f"remains preliminary. This astrological gate is not financing-readiness certification."
    )

    # v-audit fix (items 8/9): rank_business_years() (Ashtakavarga SAV/BAV
    # year suitability) and find_business_muhurta() (electional date scan)
    # are both real, already-implemented methods in this package that this
    # function has never called -- by design, since both need caller-
    # supplied parameters compute_business_prediction() does not have
    # (start_year/end_year for the former, a start/end date range + lat/lon
    # location for the latter) and fabricating placeholder values for those
    # would be worse than not calling them at all. Previously that
    # architectural choice was undocumented at the point where it matters
    # most -- a chart can reach FULL_TRANSITION_SUPPORTED or
    # capital_intensive_launch_supported=True without either check ever
    # having run, and nothing said so. This adds an explicit, action-
    # level-aware disclosure so a reader (or calling application) is told,
    # every time an actionable launch/transition tier is reached, that year-
    # level and date-level timing confirmation are separate calls that have
    # NOT yet been made.
    # v-audit fix (astrological completeness -- item 31, "Ashtakavarga and
    # Muhurta remain optional rather than mandatory launch arbitration"):
    # both checks were previously NEVER invoked automatically, full stop --
    # this function had no way to receive the year-range/date-range+location
    # parameters they need, so the advisory below could only ever say "not
    # consulted." compute_business_prediction() now accepts optional
    # candidate_year_range=(start_year, end_year) and candidate_muhurta_
    # window=(start_date, end_date, event_type, location); WHEN a caller
    # supplies either, the corresponding check is actually run here (reusing
    # this function's own already-computed timed_windows for dasha
    # corroboration in the year-ranking case) and its full result is
    # attached to authoritative_recommendation, not just disclosed as
    # missing. This does not make either check unconditionally mandatory --
    # that would mean fabricating a timeframe/location the caller never
    # provided, which would be worse than not checking at all -- but it
    # closes the "optional PARALLEL workflow" gap for any caller that DOES
    # supply a candidate timeframe: the check becomes part of THIS result,
    # not a separate call the caller has to remember to make and manually
    # reconcile.
    _ashtakavarga_year_check: Optional[Dict[str, Any]] = None
    if candidate_year_range is not None:
        _cy0, _cy1 = candidate_year_range
        _ashtakavarga_year_check = rank_business_years(payload, _cy0, _cy1, timing_windows=timed_windows, as_of_date=as_of_date)

    _muhurta_check: Optional[Dict[str, Any]] = None
    if candidate_muhurta_window is not None:
        _md_start, _md_end, _md_event_type, _md_location = candidate_muhurta_window
        _muhurta_check = find_business_muhurta(_md_start, _md_end, _md_event_type, _md_location, native_payload=payload)

    _advisory_parts = []
    if _ashtakavarga_year_check is not None:
        _advisory_parts.append(
            f"rank_business_years WAS consulted for {candidate_year_range} -> "
            f"status={_ashtakavarga_year_check.get('status')} (see ashtakavarga_year_check for the full ranked-year result)."
        )
    else:
        _advisory_parts.append(
            "rank_business_years(payload, start_year, end_year) (Ashtakavarga SAV/BAV year-suitability "
            "ranking) NOT consulted -- pass candidate_year_range=(start_year, end_year) to "
            "compute_business_prediction() to have this run and attached as ashtakavarga_year_check."
        )
    if _muhurta_check is not None:
        _advisory_parts.append(
            f"find_business_muhurta WAS consulted -> status={_muhurta_check.get('status')} "
            f"(see muhurta_check for the full ranked-date result)."
        )
    else:
        _advisory_parts.append(
            "find_business_muhurta(start_date, end_date, event_type, location, native_payload=payload) "
            "(electional launch-date scan) NOT consulted -- pass candidate_muhurta_window=(start_date, "
            "end_date, event_type, location) to compute_business_prediction() to have this run and "
            "attached as muhurta_check."
        )
    _advisory_parts.append(
        f"action_level={_action_level} should NOT be read as having confirmed a specific favorable "
        f"YEAR or DATE unless BOTH checks above show status=OK for a candidate timeframe/location "
        f"the native actually intends to use -- neither check being consulted (or either returning a "
        f"non-OK status) means year/date-level timing confirmation is still outstanding before acting "
        f"on FULL_TRANSITION_SUPPORTED or capital_intensive_launch_supported."
    )
    _ashtakavarga_muhurta_advisory = " ".join(_advisory_parts)

    # v-audit fix (correction-order item 1, real loophole caught on
    # re-audit): action_level/final_proceed were already forced to reflect
    # ABSTAIN_INSUFFICIENT_D1_DATA, but `verdict` itself (the field
    # transition_timing.py and any external caller would most naturally
    # check) was left as whatever business_promise/job_promise happened to
    # compute off neutral-default evidence -- which could easily still read
    # PURSUE_BUSINESS even while abstaining, since nothing about the
    # abstention gate touched the layered-verdict computation itself. A
    # caller checking only `verdict` (not action_level/decision_status)
    # could see a real-looking "PURSUE_BUSINESS" during abstention. `verdict`
    # is now forced to the same explicit abstention sentinel as
    # `action_level`, with the original (neutral-default-driven) verdict
    # preserved separately for diagnostic inspection only.
    # Keep structural suitability distinct from present actionability.  A
    # structurally strong chart whose timing/competency/contradictions only
    # permit a pilot must not headline as an unrestricted Pursue Business.
    _structural_verdict = _layered_verdict
    _operational_floor_failed = (
        named_fields.get("business_execution_capacity", 0) < DECISION_POLICY.minimum_operational_execution
        or named_fields.get("business_stability", 0) < DECISION_POLICY.minimum_business_stability
    )
    if _layered_verdict in ("PURSUE_BUSINESS", "PURSUE_BUSINESS_CAUTIOUSLY") and _operational_floor_failed:
        _layered_verdict = "HYBRID_LEANING_BUSINESS"
    if _layered_verdict == "PURSUE_BUSINESS" and _action_level != "FULL_TRANSITION_SUPPORTED":
        _layered_verdict = "PURSUE_BUSINESS_CAUTIOUSLY"
    _verdict_before_abstention_override = _structural_verdict
    _exposed_verdict = "ABSTAIN_INSUFFICIENT_DATA" if decision_status != "OK" else _layered_verdict

    # Issue 8 fix: independent professional practice (self-directed
    # consulting/practice -- not a scalable/capital-intensive business, not
    # salaried employment) can be the coherent astrological middle path.
    # Previously the legacy mode_gate "independent, HIGH confidence" signal
    # and the authoritative layered verdict were only ever surfaced as two
    # SEPARATE mentions (see the Signal Reconciliation section of the
    # report), leaving the reader to reconcile a binary job/business
    # headline with a third, unheadlined signal themselves. This adds an
    # explicit, additive final category -- EMPLOYMENT_SUPPORTED_INDEPENDENT_
    # PRACTICE -- computed purely from already-existing fields (no new
    # scoring), fired only when ALL of: (a) mode_gate's independent_score is
    # moderate-to-strong, (b) business execution/capital capacity is weak
    # (a full scalable business is not well-supported), and (c) there is
    # some employment-side support in the layered verdict (not a clean
    # PURSUE_BUSINESS case). Does not touch action_level/verdict/
    # final_proceed themselves (additive only); the report uses this as the
    # headline framing when it fires, instead of defaulting to a binary
    # job-vs-business narrative.
    _indep_score = mode_gate.get("independent_score", 0) or 0
    _indep_confidence = mode_gate.get("confidence")
    _exec_capacity_for_indep = named_fields.get("business_execution_capacity", 0) or 0
    _exec_components_for_indep = named_fields.get("business_execution_capacity_components", {}) or {}
    _weak_capital_or_execution = (
        _exec_capacity_for_indep < DECISION_POLICY.minimum_operational_execution
        or (_exec_components_for_indep.get("capital_debt_management", 100) or 0) <= 10
    )
    _some_employment_support = _layered_verdict in (
        "HYBRID", "HYBRID_LEANING_JOB", "STAY_EMPLOYED",
    ) or (mode_gate.get("employment_score", 0) or 0) >= 30
    _independent_practice_is_coherent_middle_path = (
        decision_status == "OK"
        and 30 <= _indep_score < 70
        and _weak_capital_or_execution
        and _some_employment_support
        and not rejected_by_main_chart
    )
    _final_category = (
        "EMPLOYMENT_SUPPORTED_INDEPENDENT_PRACTICE"
        if _independent_practice_is_coherent_middle_path
        else _exposed_verdict
    )
    _final_category_note = (
        (
            f"Fires because independent_score={_indep_score} (mode_gate confidence={_indep_confidence}) is a "
            f"moderate-to-strong legacy signal for independent professional practice, while "
            f"business_execution_capacity={_exec_capacity_for_indep} / capital_debt_management="
            f"{_exec_components_for_indep.get('capital_debt_management')} are weak (full-business execution/"
            f"capital not well-supported) and the layered verdict ({_layered_verdict}) shows some employment-side "
            f"support -- the coherent middle path is self-directed independent practice alongside (or instead of) "
            f"a full business launch, not a binary job-vs-business choice."
        )
        if _independent_practice_is_coherent_middle_path
        else (
            "Independent-practice middle-path conditions not met for this chart (see independent_score, "
            "business_execution_capacity, and layered verdict) -- final_category mirrors the binary verdict."
        )
    )
    _mode_vs_comparative_confidence_note = (
        f"mode_gate.confidence={_indep_confidence} (HIGH/MODERATE/LOW is a threshold on the GAP between "
        f"mode_gate's own employment/business/independent/family scores -- a diagnostic-only legacy signal, "
        f"not decision-driving) and business_over_job_confidence (separately reported, often LOW) answer "
        f"DIFFERENT QUESTIONS from DIFFERENT SUBSYSTEMS: mode_gate.confidence asks 'how clearly does the "
        f"legacy accumulation separate its own four mode scores from each other', while business_over_job_"
        f"confidence asks 'how much do the independent method-agreement checks corroborate the authoritative "
        f"business_promise-over-job_promise margin'. A HIGH mode_gate.confidence and a LOW business_over_job_"
        f"confidence appearing together is not a contradiction -- they are not measuring the same thing."
    )

    authoritative_recommendation = {
        "final_category": _final_category,
        "final_category_note": _final_category_note,
        "mode_confidence_vs_comparative_confidence_note": _mode_vs_comparative_confidence_note,
        "verdict": _exposed_verdict,
        "verdict_before_abstention_override": _verdict_before_abstention_override,
        "structural_verdict": _structural_verdict,
        "downgraded_by_operational_floor": _operational_floor_failed,
        "operational_floor_note": (
            f"execution={named_fields.get('business_execution_capacity')} (floor {DECISION_POLICY.minimum_operational_execution}), "
            f"stability={named_fields.get('business_stability')} (floor {DECISION_POLICY.minimum_business_stability})"
        ),
        "action_level": _action_level,
        "decision_status": decision_status,
        "decision_status_note": (
            "ABSTAINING: mandatory D1 structural inputs (house_lords, planet_house, "
            "planet_dignities) are missing or empty on this payload -- see "
            "evidence_sufficiency.structural_recommendation for which fields. Every "
            "score below this point (business_promise, job_promise, action_level, "
            "sector rankings) was still computed for internal-pipeline consistency, "
            "but is running on this pipeline's neutral-default/graceful-degradation "
            "behavior rather than a real chart read -- treat it as NOT MEANINGFUL, "
            "not as a low-confidence answer. This most commonly means the chart's D1 "
            "data arrived under a schema variant this parser doesn't yet recognize "
            "(see jyotish/engine_io.py::parse_json_payload), not that the native's "
            "chart genuinely lacks D1 data."
            if decision_status == "ABSTAIN_INSUFFICIENT_D1_DATA" else
            "D1 structural inputs are present; this is a normal, evidenced read."
        ),
        "employment_exit_supported": _employment_exit_supported,
        "capital_intensive_launch_supported": _capital_intensive_launch_supported,
        # Astrological support and externally attested financial readiness
        # are separate fields. D11 is optional HARMONIC_11 corroboration.
        "capital_readiness_status": _capital_readiness_status,
        "capital_readiness_certified": bool(_financial_readiness.get("certified")),
        "financial_readiness": _financial_readiness,
        "capital_intensive_launch_note": _capital_model_note,
        "ashtakavarga_and_muhurta_advisory": _ashtakavarga_muhurta_advisory,
        "ashtakavarga_year_check": _ashtakavarga_year_check,
        "muhurta_check": _muhurta_check,
        "client_validation_supported": (
            _action_level in ("PILOT_WHILE_RETAINING_INCOME", "PILOT_OR_SIDE_VENTURE", "VALIDATE_BEFORE_COMMITTING")
            or (
                decision_status == "OK"
                and not rejected_by_main_chart
                and (named_fields.get("business_execution_capacity", 0) or 0) >= 60
                and (named_fields.get("business_field_fit", 0) or 0) >= 60
                and (named_fields.get("current_timing_readiness", 0) or 0) >= 50
            )
        ),
        "client_validation_basis": (
            "Validation/pilot support does not imply employment-exit support. It is allowed when the action level "
            "already permits a pilot, or when execution, field fit, and timing are each at least moderate while "
            "the main chart has not rejected business."
        ),
        "basis": "business_promise vs job_promise (declared-layer-weight system, contradiction-penalized), not the legacy mode_gate shared-ceiling accumulation",
        "birth_time_sensitivity": _bts,
        "downgraded_by_birth_time_sensitivity": _birth_time_downgrade,
        "divisional_boundary_sensitivity": _dbs,
        "downgraded_by_divisional_boundary_sensitivity": _boundary_downgrade,
        "business_promise": named_fields.get("business_promise"),
        "job_promise": named_fields.get("job_promise"),
        "business_advantage_margin": named_fields.get("business_advantage_margin"),
        "business_advantage_label": _advantage_label,
        "hybrid_suggested": _exposed_verdict in ("HYBRID", "HYBRID_LEANING_BUSINESS", "HYBRID_LEANING_JOB"),
        "legacy_track_agrees": _tracks_agree,
        "legacy_track_proceed_before_gate": _legacy_favors_business,
        "final_proceed": recommendation["proceed"],
        "downgraded_by_layered_system": _downgraded_by_layered_system,
        "legacy_track_gate_score": recommendation.get("gate_score"),
        "legacy_track_employment_score": recommendation.get("employment_score"),
        "note": (
            "Both scoring tracks agree on direction."
            if _tracks_agree else
            f"DISAGREEMENT: the layered system reads {_layered_verdict} "
            f"(business_promise={named_fields.get('business_promise')} vs "
            f"job_promise={named_fields.get('job_promise')}, margin="
            f"{named_fields.get('business_advantage_margin')}) while the "
            f"legacy mode_gate track originally read proceed={_legacy_favors_business} "
            f"(gate_score={recommendation.get('gate_score')} vs "
            f"employment_score={recommendation.get('employment_score')}) -- "
            + (
                "the legacy track was downgraded to False by this disagreement (final_proceed=False)."
                if _downgraded_by_layered_system else
                "the disagreement was not sharp enough (verdict != STAY_EMPLOYED) to override "
                "the legacy track automatically; treat authoritative_recommendation.verdict as "
                "primary and legacy_track fields as secondary audit context."
            )
        ),
    }

    # Engineering audit fix #1 (dual decision systems): recommendation.proceed
    # / heuristic_tier / confidence are now driven SOLELY by the layered
    # business_promise/job_promise + authoritative_recommendation system
    # (verdict/action_level, computed above), not by the legacy mode_gate
    # score accumulation (gate_score vs employment_score). Previously the
    # legacy track was the one actually setting recommendation.proceed, and
    # authoritative_recommendation only overrode it on the single sharpest
    # disagreement (legacy proceed=True while layered verdict==STAY_EMPLOYED).
    # That made the "authoritative" system authoritative in name only. The
    # legacy mode_gate-derived proceed/tier computed earlier in this function
    # is retained below ONLY as a diagnostic, explicitly non-authoritative
    # field (`legacy_mode_gate_score`) for backward-compatibility/debugging;
    # it no longer drives the headline recommendation. The D10 hard veto
    # (rejected_by_main_chart) still applies on top of the layered verdict,
    # same as before.
    _legacy_mode_gate_proceed = recommendation["proceed"]
    _legacy_mode_gate_tier = recommendation["heuristic_tier"]

    # P0 fix (audit finding #1): recommendation.proceed/authoritative_
    # recommendation.final_proceed used to be computed only from the
    # layered verdict + D10 veto, with NO requirement that decision_status
    # == "OK" -- so a chart that had already been flagged
    # ABSTAIN_INSUFFICIENT_D1_DATA (missing house_lords/planet_house/
    # planet_dignities) could still return proceed=True, with action_level
    # simultaneously saying "abstain" and proceed simultaneously saying
    # "yes." decision_status is now a hard gate on proceed, same as it
    # already was on action_level above.
    _authoritative_proceed = (
        _layered_favors_business and not rejected_by_main_chart and decision_status == "OK"
    )
    if _authoritative_proceed and _strong_floor_met and _layered_verdict == "PURSUE_BUSINESS":
        _authoritative_tier = "HIGH"
    elif _authoritative_proceed:
        _authoritative_tier = "MODERATE"
    else:
        _authoritative_tier = "LOW"

    recommendation["proceed"] = _authoritative_proceed
    recommendation["heuristic_tier"] = _authoritative_tier
    recommendation["confidence"] = _authoritative_tier
    # Public comparison flags use the same authoritative layered scores as
    # the headline.  Legacy mode-gate flags previously produced impossible
    # combinations such as business 48 < job 70 with comparative=True.
    recommendation["comparative_advantage"] = (
        named_fields.get("business_advantage_margin", 0) >= DECISION_POLICY.comparative_margin
        and named_fields.get("business_promise", 0) >= DECISION_POLICY.minimum_actionable_promise
    )
    recommendation["hybrid_suggested"] = authoritative_recommendation["hybrid_suggested"]
    recommendation["legacy_mode_gate_score"] = {
        "note": (
            "DIAGNOSTIC ONLY -- NOT authoritative. This is the OLD legacy "
            "mode_gate-accumulation read (gate_score vs employment_score) "
            "that used to drive recommendation.proceed/heuristic_tier before "
            "engineering fix #1. Retained for backward-compatibility/"
            "debugging only. See authoritative_recommendation for the single "
            "source of truth behind proceed/heuristic_tier/confidence."
        ),
        "proceed": _legacy_mode_gate_proceed,
        "heuristic_tier": _legacy_mode_gate_tier,
        "gate_score": gate_score,
        "employment_score": employment_score,
        "penalized_gate_score": penalized_gate_score,
        "penalized_employment_score": penalized_employment_score,
        "margin": margin,
    }
    recommendation["reasoning"] += (
        f" | AUTHORITATIVE DECISION (engineering fix #1): proceed/heuristic_tier "
        f"now driven solely by the layered business_promise/job_promise system "
        f"(verdict={_layered_verdict}, action_level={_action_level}); the legacy "
        f"mode_gate-based read (proceed={_legacy_mode_gate_proceed}, "
        f"tier={_legacy_mode_gate_tier}) is preserved as diagnostic-only in "
        f"recommendation.legacy_mode_gate_score and no longer drives this decision."
    )
    if decision_status != "OK":
        recommendation["reasoning"] += (
            f" | P0 FIX: proceed forced to False -- decision_status={decision_status} "
            f"(mandatory D1 structural inputs missing/insufficient). action_level and "
            f"proceed can no longer disagree on abstention."
        )
    authoritative_recommendation["final_proceed"] = recommendation["proceed"]
    authoritative_recommendation["basis"] = (
        "business_promise vs job_promise (declared-layer-weight system, "
        "contradiction-penalized) is the SOLE source of truth for "
        "recommendation.proceed/heuristic_tier as of engineering fix #1. The "
        "legacy mode_gate shared-ceiling accumulation is retained only as "
        "recommendation.legacy_mode_gate_score, a non-authoritative diagnostic."
    )

    # v-audit fix (item 22): recommendation.proceed is a bare Boolean and a
    # downstream client that reads only this one key -- without also
    # consulting action_level, calibration_status, or birth_time_reliability
    # -- could misread True as "approved to resign/invest/borrow." proceed is
    # kept (removing it would break the documented public contract and every
    # caller keying off it), but it is never emitted alone: these caveat
    # fields live in the SAME dict, so any consumer that unpacks
    # `recommendation` for the "proceed" key necessarily also receives them.
    recommendation["proceed_is_not_financial_advice"] = True
    recommendation["proceed_requires_context"] = (
        "recommendation.proceed is a coarse Boolean derived from an "
        f"{MODEL_STATUS} engine ({CALIBRATION_STATUS}). It must not be read "
        "as standalone authorization to resign, invest, borrow, incorporate, "
        "or sign a partnership. Before acting, also consult: "
        "authoritative_recommendation.action_level (graded guidance -- "
        "FULL_TRANSITION_SUPPORTED is the only tier consistent with a bare "
        "'yes'), birth_time_reliability (astrological inputs upstream of "
        "this decision degrade under an uncertain birth time), and "
        "independent real-world business-feasibility factors (capital, "
        "market, partner governance, jurisdiction) that this engine does "
        "not model at all."
    )

    # v20 audit fix: mode_gate.business_score/employment_score still use
    # the legacy shared-ceiling rule accumulation (_MODE_FIXED_MAX), not
    # the spec's declared layer weights -- only business_promise/job_promise
    # used them. The legacy accumulation is deliberately left untouched
    # (it's load-bearing for _SHARED_MODE_CEILING/_MODE_FIXED_MAX and the
    # dozens of existing tests that assert against it), but the declared-
    # weight equivalents are now ALSO exposed directly on mode_gate, pre-
    # contradiction-penalty, so callers who want the spec-literal
    # composition don't have to reach into business_promise_layers.
    mode_gate = {
        **mode_gate,
        "business_score_layered": named_fields["business_promise_layers"]["weighted_total"],
        "job_score_layered": named_fields["job_promise_layers"]["weighted_total"],
    }

    # v-audit fix (item 32): sector ranking previously stayed fully
    # populated with real-looking scores/labels even while decision_status
    # was ABSTAIN_INSUFFICIENT_D1_DATA -- the abstention note said rankings
    # were "not meaningful", but the numeric ranked list itself was still
    # returned unchanged, inviting a caller to publish/act on it without
    # ever reading that disclaimer. Sector ranking is house_lords/planet_
    # house-driven (see _MANDATORY_INPUTS_BY_FAMILY["sector_ranking"]
    # above), i.e. it depends on exactly the same structural D1 inputs
    # decision_status is already gating -- so it's suppressed to an empty
    # list alongside action_level, not left populated on its own.
    if decision_status != "OK":
        _suppressed_sector_note = (
            f"SUPPRESSED: sector ranking depends on the same structural D1 inputs "
            f"(house_lords, planet_house) that are missing/insufficient on this payload "
            f"(decision_status={decision_status}) -- returned empty rather than as a "
            f"numeric-looking ranking that is not actually meaningful. See "
            f"evidence_sufficiency.sector_ranking / decision_status_note for detail."
        )
        top_sectors = []
        diversified_sectors = {**diversify_sector_ranking([], max_per_family=1, top_n=8), "note": _suppressed_sector_note}

    result: Dict[str, Any] = {
        "architecture_version": ARCHITECTURE_VERSION,
        "release_manifest": build_release_manifest(),
        "capability_status": capability_status(),
        "calculation_context": {
            "cache_policy": "PER_RUN_DEEP_COPY_ISOLATION",
            "computed_fact_keys": list(calculation_context.computed_keys()),
        },
        "output_contract_version": OUTPUT_CONTRACT_VERSION,
        "decision_policy": DECISION_POLICY.manifest(),
        "conclusions_quarantined": decision_status != "OK",
        "quarantine_reason": None if decision_status == "OK" else decision_status,
        "mode_gate": mode_gate,
        "significators": significators,
        "top_sectors": top_sectors,
        # Additive, backward-compatible: diversity-clustered view derived
        # from the same full ranked list as top_sectors above (never a
        # re-ranking of it -- see diversify_sector_ranking() docstring in
        # business_determination/sectors.py). "top_sectors" keeps its
        # existing shape/values unchanged for any caller relying on the
        # raw ranking. Suppressed to empty (see above) when decision_status
        # != OK.
        "diversified_sectors": diversified_sectors,
        "timed_windows": timed_windows,
        "timing_status": timing_status,
        "method_status": method_status,
        "recommendation": recommendation,
        "authoritative_recommendation": authoritative_recommendation,
        # v17 additions -- see task list item "Compute 9 named output fields".
        "business_promise": named_fields["business_promise"],
        "job_promise": named_fields["job_promise"],
        "business_promise_layers": named_fields["business_promise_layers"],
        "job_promise_layers": named_fields["job_promise_layers"],
        "independent_profession_promise": named_fields["independent_profession_promise"],
        "business_field_fit": named_fields["business_field_fit"],
        "business_execution_capacity": named_fields["business_execution_capacity"],
        "business_execution_capacity_components": named_fields["business_execution_capacity_components"],
        "competency_readiness": named_fields["competency_readiness"],
        "business_profitability": named_fields["business_profitability"],
        "gross_revenue_potential": named_fields["gross_revenue_potential"],
        "profit_retention": named_fields["profit_retention"],
        "business_stability": named_fields["business_stability"],
        "business_stability_components": named_fields["business_stability_components"],
        "current_timing_readiness": named_fields["current_timing_readiness"],
        "business_over_job_confidence": named_fields["business_over_job_confidence"],
        "business_advantage_margin": named_fields["business_advantage_margin"],
        "business_advantage_label": named_fields["business_advantage_label"],
        "strong_business_absolute_floor_met": named_fields["strong_business_absolute_floor_met"],
        "operating_model": operating_model,
        "operating_model_d10": operating_model_d10,
        "operating_model_synthesis": operating_model_synthesis,
        "contradiction_findings": contradictions,
        "d24_competency_status": d24_status,
        "d24_full_analysis": d24_full,
        "d60_confirmation_status": d60_status,
        "d11_gains_status": d11_status,
        # Discrete D2 (Hora) wealth-flow evidence layer (see
        # house_evidence._d2_native_house_evidence): purely additive,
        # already folded into score_business_significators() above and
        # into the contradiction layer's wealth-flow-caution check, but
        # also exposed separately here (same pattern as detected_yogas/
        # legal_dispute_risk) so it can be rendered as its own list.
        # Never raises; returns [] when no D2 data is available.
        "d2_hora_evidence": [
            {"weight": round(w, 3), "note": n} for w, n in _d2_native_house_evidence(payload)
        ],
        # Deep D2-Hora structural read (audit item 5): D2 Lagna, Hora
        # Lagna lord + its own D1 dignity, Sun's/Moon's own condition
        # within D2, and separate earning/accumulation/expenditure
        # sub-conclusions -- see house_evidence._d2_hora_deep_evidence.
        # Purely additive/informational, NOT folded into any score --
        # extends d2_hora_evidence above, does not replace or duplicate
        # its (already-scored) flat weight list. Never raises.
        "d2_hora_deep_evidence": _d2_hora_deep_evidence(payload),
        # Consolidated Mercury adjudication (audit item 11): combustion
        # distance/verdict, retrograde, D1/D9/D10 dignity, strength metric
        # (real Shadbala when available), nakshatra/sub-lord, and a final
        # H7-vs-H10 synthesized verdict -- see significators.py::
        # _mercury_full_adjudication. Purely additive/informational, not
        # folded into any score. Never raises.
        "mercury_adjudication": _mercury_full_adjudication(payload),
        # Explicit Lagnesh Neecha Bhanga (debilitation-cancellation)
        # adjudication (audit item, house_evidence.py::
        # lagnesh_neecha_bhanga_adjudication) -- reuses the existing, real
        # _neecha_bhanga_status() check (already invoked internally for the
        # significator ledger) and exposes it as its own top-level,
        # explicitly-stated field with real dispositor/reasoning, rather
        # than leaving the verdict buried inside free-form evidence notes.
        # Purely additive/informational, not folded into any score.
        "lagnesh_neecha_bhanga": lagnesh_neecha_bhanga_adjudication(payload),
        # Discrete Janma Nakshatra (birth-star) business-aptitude
        # corroboration layer (see nakshatra_business.py): purely
        # additive, already folded into score_business_significators()
        # above via _add(), but also exposed separately here (same
        # pattern as d2_hora_evidence/detected_yogas/legal_dispute_risk)
        # so it can be rendered as its own citation. Never raises;
        # returns [] when payload.moon_nakshatra is missing/blank or not
        # in the curated classical table.
        "janma_nakshatra_evidence": janma_nakshatra_business_evidence(payload),
        # Fuller nakshatra-vocational chain (audit item: 10th-lord's
        # nakshatra-lord, Amatyakaraka's nakshatra, current dasha-lord's
        # nakshatra linkage, and whether that chain terminates in a
        # business-relevant house 2/3/6/7/10/11) -- see nakshatra_business.
        # py::janma_nakshatra_full_chain_evidence. Structural chain data
        # (dict), distinct from the single weighted table-lookup citation
        # in janma_nakshatra_evidence above. Never raises.
        "janma_nakshatra_full_chain": janma_nakshatra_full_chain_evidence(payload),
        # D10 birth-time rectification sensitivity test: recomputes D10
        # lagna + decisive D10-native house-lord findings (10th/11th/3rd/
        # 5th lords, 8th-house connections) at +/-1/2/5-minute birth-time
        # offsets and flags STABLE/FRAGILE -- see business_determination/
        # d10_rectification.py. Degrades gracefully (status != OK,
        # stability="UNKNOWN") when ephemeris/dob/tob/lat/lon are
        # unavailable. Never raises.
        "d10_rectification_sensitivity": d10_rectification_sensitivity(payload),
        # Discrete dedicated foreign/cross-border business viability check
        # bundle (see foreign_business.py): 12th-lord (primary) / 9th-lord
        # (secondary) strength-dignity + Rahu foreign-house placement/
        # conjunction-aspect checks, distinct from sectors.py's generic
        # core_houses/core_planets affinity averaging for
        # import_export_foreign_trade (that sector's own row already
        # folds a scoped bonus/citation from this same evidence in via
        # sector_score()'s foreign_business_bonus/foreign_business_notes
        # fields -- this key exposes the same evidence independent of
        # sector scoring, same pattern as d2_hora_evidence/janma_
        # nakshatra_evidence above). Never raises; returns [] when no
        # notable foreign indicator is present or house_lords/planet_
        # house data is unavailable.
        "foreign_business_evidence": foreign_business_viability_evidence(payload),
        "sign_modality_profile": sign_modality,
        "kp_10th_cusp_job_vs_business": kp10,
        # Discrete named-yoga detection layer (see yogas.py): purely
        # additive -- packages house-lord evidence already computed above
        # into classically-named, individually-citable combinations
        # (Raja Yoga, Dhana Yoga, Mercury-Saturn-Rahu business combination)
        # instead of leaving them dissolved into the aggregate score.
        # Never raises; returns [] when the chart has none detected.
        "detected_yogas": detect_business_yogas(payload),
        "yoga_detection_status": yoga_detection_status(payload),
        # Discrete named legal-dispute/litigation-risk detection layer (see
        # legal_risk.py): purely additive, distinct from the generic
        # H6/H8/H12 "loss/liability exposure" language already present in
        # significators.py/mode_gate.py and from timing.py's
        # direction-neutral RAHU_KETU_AXIS_MAJOR_CHANGE transit flag.
        # Never raises; returns [] when the chart has none detected.
        "legal_dispute_risk": calculation_context.fact(
            "legal_dispute_risk", lambda: detect_legal_dispute_risk(payload)
        ),
        # Issue 15 fix: explicit status distinguishing NOT_EVALUATED
        # (missing house_lords/planet_house) from EVALUATED_NO_MATCH (data
        # present, none of the 4 named patterns matched) from MATCHES_FOUND
        # -- see legal_risk.legal_dispute_risk_status docstring. A bare
        # empty legal_dispute_risk list alone cannot tell a reader which of
        # the first two happened.
        "legal_dispute_risk_status": calculation_context.fact(
            "legal_dispute_risk_status", lambda: legal_dispute_risk_status(payload)
        ),
        # Cross-wires mode_gate's static recommended_mode/margin against
        # timing's current/upcoming favorable-window calendar (see
        # transition_timing.py) to answer the "act now or wait for a
        # specific window" question neither subsystem answers alone. Purely
        # additive/backward-compatible (same pattern as detected_yogas/
        # legal_dispute_risk/d2_hora_evidence above) -- never raises; the
        # module itself degrades to INSUFFICIENT_DATA rather than throwing.
        "transition_timing_recommendation": compute_transition_timing_recommendation(
            mode_gate, timed_windows, timing_status=timing_status, as_of_date=as_of_date,
            authoritative_recommendation=authoritative_recommendation,
        ),
        "false_conclusion_guard_checklist": _false_conclusion_guard_checklist(
            payload, contradictions, mode_gate, recommendation, d24_status, d60_status,
        ),
        "kn_rao_validation_sequence": _kn_rao_validation_sequence(
            payload, mode_gate, significators, d24_status, d60_status, timed_windows,
            timing_status, method_status, named_fields, rejected_by_main_chart, veto_note,
        ),
        "final_decision_hierarchy_trace": _final_decision_hierarchy_trace(
            payload, mode_gate, significators, top_sectors, timed_windows, timing_status,
            method_status, d24_status, d60_status, kp10, sign_modality, operating_model,
            contradictions, named_fields, recommendation, operating_model_d10=operating_model_d10,
        ),
        "model_status": MODEL_STATUS,
        "calibration_status": CALIBRATION_STATUS,
        "calibration_state": _calibration_state(),
        "evidence_basis": EVIDENCE_BASIS,
        "maturity_statement": MATURITY_STATEMENT,
        "maturity_caveats": list(MATURITY_CAVEATS),
        "rule_pack_version": RULE_PACK_VERSION,
        "forecast_window": {
            "as_of": str(as_of_date or date.today()),
            "years_ahead": years_ahead,
        },
        # Engineering audit fix #9: structured record of every degrade-
        # gracefully-swallowed exception encountered while computing this
        # result (see constants.py's _record_diagnostic/_DIAGNOSTICS). Empty
        # list on the common case where nothing failed. This does NOT
        # change any fallback behavior -- it only makes previously-silent
        # failures visible.
        "diagnostics": _get_diagnostics(),
        "evidence_sufficiency": evidence_sufficiency,
        # v-audit fix (item 4): top-level mirror of
        # authoritative_recommendation.decision_status, for any caller that
        # only reads compute_business_prediction()'s outer dict and never
        # descends into authoritative_recommendation.
        "decision_status": decision_status,
    }

    # Partnership/co-founder synastry (see synastry.py): fully optional and
    # backward-compatible -- existing single-native callers that never pass
    # partner_payload get exactly the same result dict as before (no new
    # key added at all when partner_payload is None), so this cannot break
    # any existing caller/test asserting on result's exact key set.
    if partner_payload is not None:
        _synastry = compute_partnership_synastry(payload, partner_payload)
        result["partnership_synastry"] = _synastry

        # v-audit fix (business realism, item 36 -- "partner analysis remains
        # optional and does not fully recompute the operating verdict"):
        # partnership_synastry was previously attached as a pure side-
        # channel -- its compatibility_label never fed back into
        # authoritative_recommendation at all, so a client reading only
        # authoritative_recommendation (the documented single source of
        # truth for proceed/heuristic_tier) would never learn that a
        # co-founder chart materially changes the picture. This computes an
        # explicit, disclosed, capped recomputation -- NOT a silent mutation
        # of recommendation.proceed/heuristic_tier itself (those must stay
        # exactly as they were for solo-native callers and every existing
        # test asserting on them; see "engineering fix #1" comment above for
        # why authoritative_recommendation's base fields are load-bearing).
        # The rule is deliberately narrow and mechanical:
        #   - A base verdict of "do not proceed" is NEVER upgraded by a
        #     compatible partner -- partnership fit cannot rescue a chart
        #     that fails its own solo D1 gate (decision_status/contradiction
        #     checks already establish that independently of any partner).
        #   - Otherwise, the base tier is nudged by exactly one step (never
        #     more) in the direction the partner's compatibility_label
        #     supports: STRONG_FIT can raise LOW->MODERATE or
        #     MODERATE->HIGH; CAUTION lowers HIGH->MODERATE or
        #     MODERATE->LOW; POOR_FIT always forces LOW regardless of the
        #     base tier (a genuinely poor-fit partner is treated as a hard
        #     caution, not a one-step nudge); WORKABLE_FIT leaves the tier
        #     unchanged. This one-step-only cap matches how every other
        #     cross-signal adjustment in this engine (operating_model_
        #     alignment_bonus, geographic_preference_discount, dignity_
        #     precision_bonus) is similarly small and capped rather than
        #     capable of overturning the underlying verdict on its own.
        _tier_order = ["LOW", "MODERATE", "HIGH"]
        # recommendation["heuristic_tier"] is already forced to "LOW"
        # whenever proceed is False (see the _authoritative_tier assignment
        # above), so it's already the correct base_tier in both cases.
        _base_tier = recommendation.get("heuristic_tier", "LOW")
        _base_proceed = bool(authoritative_recommendation.get("final_proceed"))
        _label = _synastry.get("compatibility_label") if _synastry.get("status") == "OK" else None

        if not _base_proceed:
            _partner_tier = _base_tier
            _partner_note = (
                "Base recommendation is already NOT to proceed (decision_status/"
                "contradiction checks independent of any partner) -- a compatible "
                "co-founder chart cannot rescue a chart that fails its own solo gate, "
                "so no partner-driven upgrade is applied."
            )
        elif _label is None:
            _partner_tier = _base_tier
            _partner_note = (
                "No partner compatibility data available "
                f"(partnership_synastry.status={_synastry.get('status')!r}) -- "
                "operating verdict is unchanged from the solo-native read."
            )
        else:
            _idx = _tier_order.index(_base_tier) if _base_tier in _tier_order else 0
            if _label == "STRONG_FIT":
                _idx = min(_idx + 1, len(_tier_order) - 1)
            elif _label == "CAUTION":
                _idx = max(_idx - 1, 0)
            elif _label == "POOR_FIT":
                _idx = 0
            # WORKABLE_FIT: no change.
            _partner_tier = _tier_order[_idx]
            _partner_note = (
                f"Partner compatibility_label={_label!r} applied as a single-step, "
                f"capped adjustment to the base tier ({_base_tier}) -- see this field's "
                "own docstring-equivalent comment in engine.py for the exact rule. This "
                "is a disclosed engineered heuristic, not a claim that partnership fit "
                "is astrologically equivalent in weight to the underlying business promise."
            )

        authoritative_recommendation["partner_verdict_recomputation"] = {
            "base_tier": _base_tier,
            "base_proceed": _base_proceed,
            "partner_compatibility_label": _label,
            "partner_adjusted_tier": _partner_tier,
            "tier_changed": _partner_tier != _base_tier,
            "note": _partner_note,
        }

    if attach_provenance:
        result["provenance"] = _attach_provenance(payload, enable_llm=enable_llm_narrative)

    if enable_llm_narrative:
        result["llm_narrative"] = _compose_business_narrative(payload, significators, top_sectors, recommendation)

    # Explicitly quarantine the older shared-ceiling track beneath a named,
    # non-authoritative namespace. Top-level compatibility fields remain for
    # one contract generation, but consumers have one unambiguous home for
    # audit-only legacy values.
    result["legacy_non_authoritative"] = {
        "mode_gate": result["mode_gate"],
        "recommendation": {
            "gate_score": recommendation.get("gate_score"),
            "employment_score": recommendation.get("employment_score"),
            "legacy_mode_gate_score": recommendation.get("legacy_mode_gate_score"),
            "legacy_employment_score": recommendation.get("legacy_employment_score"),
        },
        "status": "NON_AUTHORITATIVE_COMPATIBILITY_ONLY",
    }

    diagnostics = result["diagnostics"]
    severity_counts = {
        severity: sum(d.get("severity") == severity for d in diagnostics)
        for severity in ("INFORMATIONAL_FALLBACK", "DEGRADED_METHOD", "RECOMMENDATION_BLOCKING")
    }
    result["diagnostic_summary"] = {
        "severity_counts": severity_counts,
        "recommendation_capped": False,
        "policy": (
            "RECOMMENDATION_BLOCKING disables proceed; DEGRADED_METHOD caps "
            "FULL_TRANSITION_SUPPORTED; INFORMATIONAL_FALLBACK is disclosure-only."
        ),
    }
    auth = result["authoritative_recommendation"]
    rec = result["recommendation"]
    if severity_counts["RECOMMENDATION_BLOCKING"]:
        auth["action_level"] = "ABSTAIN_INTERNAL_METHOD_FAILURE"
        auth["final_proceed"] = False
        auth["employment_exit_supported"] = False
        auth["capital_intensive_launch_supported"] = False
        rec["proceed"] = False
        rec["heuristic_tier"] = rec["confidence"] = "LOW"
        result["diagnostic_summary"]["recommendation_capped"] = True
    elif severity_counts["DEGRADED_METHOD"] and auth.get("action_level") == "FULL_TRANSITION_SUPPORTED":
        auth["action_level"] = DECISION_POLICY.diagnostic_strong_recommendation_cap
        auth["employment_exit_supported"] = False
        auth["capital_intensive_launch_supported"] = False
        result["diagnostic_summary"]["recommendation_capped"] = True

    if decision_status != "OK":
        # Contract-level quarantine: neutral-default subordinate values are
        # unavailable, not merely accompanied by an easy-to-miss warning.
        for key in (
            "business_promise", "job_promise", "business_promise_layers", "job_promise_layers",
            "independent_profession_promise", "business_field_fit", "business_execution_capacity",
            "competency_readiness", "business_profitability",
            "gross_revenue_potential", "profit_retention", "business_stability",
            "business_stability_components", "current_timing_readiness", "business_over_job_confidence",
            "business_advantage_margin", "business_advantage_label", "strong_business_absolute_floor_met",
            "operating_model", "operating_model_d10", "transition_timing_recommendation",
        ):
            result[key] = None
        for key in (
            "top_sectors", "timed_windows", "d2_hora_evidence", "janma_nakshatra_evidence",
            "foreign_business_evidence", "detected_yogas", "legal_dispute_risk",
            "janma_nakshatra_full_chain", "d10_rectification_sensitivity",
        ):
            result[key] = []
        result["d2_hora_deep_evidence"] = {"status": "SUPPRESSED", "note": "D2-Hora deep evidence suppressed: decision_status != OK."}
        result["mercury_adjudication"] = {"status": "SUPPRESSED", "note": "Mercury adjudication suppressed: decision_status != OK."}
        result["lagnesh_neecha_bhanga"] = {"status": "SUPPRESSED", "note": "Lagnesh Neecha Bhanga adjudication suppressed: decision_status != OK."}

    result = finalize_result(result, decision_status)
    validate_result_contract(result)

    return result
