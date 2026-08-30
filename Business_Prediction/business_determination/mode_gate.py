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


"""business_determination.mode_gate

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .constants import RULE_PACK_VERSION, _TRIKONA
from .house_evidence import _d10_native_house_evidence, _fifth_house_business_evidence, _functional_kendra_trikona_lords, _house_lord_strength, _neecha_bhanga_status, _rich_planet_dignities, sav_lookup
from .jaimini import _DUSTHANA, _KT, _STRONG_DIGNITY, _arudha_business_evidence, _dig_disclosure, _dig_factor, _dig_name, _effective_benefic_malefic_sets, _karakamsha_business_evidence
from .kp import _kp_10th_cusp_job_vs_business, _kp_sublord_signification_bias, _verify_kp_cusp_chain
from .timing import _transit_corroboration
from .policy import DECISION_POLICY


def _calibration_state() -> Dict[str, Any]:
    """Live governed calibration status (see Business_Prediction.calibration).
    No dataset has ever cleared validate_outcomes(), so this always resolves
    to ENGINEERED_PROVISIONAL today -- it is computed, not hardcoded, so it
    will automatically report VALIDATED_CALIBRATED once (and only once) a
    real passing validation_report is wired in.
    """
    try:
        from Business_Prediction.calibration import calibration_state
        return calibration_state()
    except Exception:
        return {"status": "ENGINEERED_PROVISIONAL", "note": "calibration module unavailable"}

def _attach_provenance(payload: Any, enable_llm: bool) -> Dict[str, Any]:
    """Reuses jyotish.run_manifest.build_run_manifest and
    jyotish.calculation_policy.build_calculation_policy verbatim (the same
    reproducibility stamp run_engine() attaches to every Field_Determination
    run) so a saved Business_Prediction output records exactly what engine
    version/source-tree/input hash produced it. Degrades to a minimal
    stamp (no source-tree hash) if either helper can't run for this
    payload -- never blocks the prediction itself.
    """
    try:
        from jyotish.run_manifest import build_run_manifest
        from jyotish.calculation_policy import build_calculation_policy
        manifest = build_run_manifest(payload, enable_llm=enable_llm)
        policy = build_calculation_policy(payload)
        return {
            "run_manifest": manifest,
            "calculation_policy": policy.to_dict() if hasattr(policy, "to_dict") else str(policy),
        }
    except Exception as exc:
        return {"run_manifest": None, "calculation_policy": None, "provenance_error": str(exc)}

def _compose_business_narrative(
    payload: Any,
    significators: Dict[str, Any],
    top_sectors: List[Dict[str, Any]],
    recommendation: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Opt-in, consent-gated LLM narrative layer, reusing
    jyotish.llm_composer.compose_narrative verbatim -- same consent contract
    already used by Job_Career/career_field_report_v2.py
    (student_context.external_llm_consent on the chart, or the blanket
    LLM_REPORT_CONSENT env var). Returns None (never raises) if consent
    isn't granted, no API key is configured, or the call fails -- callers
    must treat this as pure narrative sugar over the deterministic
    evidence above, never a second source of truth.

    compose_narrative()'s own contract expects `validated_claims` from
    jyotish.llm_validator.validate_rule_trace() (LLM-generated claims
    checked against evidence). This module has no LLM-generated claims to
    validate -- instead it passes its OWN deterministic significator
    evidence ledger, reformatted as claim dicts with status="deterministic"
    (not "supported"/"llm_generated"), so the composer is asked only to
    phrase existing, already-computed evidence in plain language, not to
    introduce or validate new astrological claims of its own.
    """
    env_consent = str(os.getenv("LLM_REPORT_CONSENT", "")).strip().lower() in {"1", "true", "yes", "on"}
    has_consent = bool(getattr(payload, "external_llm_consent", False)) or env_consent
    if not has_consent:
        return None

    try:
        from jyotish.llm_composer import compose_narrative
    except Exception:
        return None

    claims = [
        {"claim": e["note"], "status": "deterministic", "polarity": e["polarity"], "source": "Business_Prediction.significators"}
        for e in significators.get("evidence", [])
    ]
    scores = {
        "significator_strength_0_100": significators.get("heuristic_relative_strength_0_100"),
        "top_sector": top_sectors[0]["label"] if top_sectors else None,
        "top_sector_score": top_sectors[0]["score"] if top_sectors else None,
        "heuristic_tier": recommendation.get("heuristic_tier"),
    }
    try:
        return compose_narrative(claims, scores)
    except Exception:
        return None

def compute_business_mode_gate(payload: Any, as_of_date: Optional[date] = None) -> Dict[str, Any]:
    """Signed, dignity-gated, D9/D10-aware replacement for
    jyotish.employment_mode.compute_employment_mode(). Returns the SAME
    output shape (employment_score, business_score, independent_score,
    family_biz_score, recommended_mode, confidence, key_signals,
    geographic_preference) for drop-in compatibility with existing callers
    and reports, plus additional signed-evidence fields (positive_signals,
    negative_signals per mode) that compute_business_prediction() uses for
    the comparative business-vs-employment margin check.

    Also folds in D10 (Dashamsha)-NATIVE house-graph evidence (D10's own
    house graph, not D1 placement projected onto D10 dignity -- the same
    evidence source score_business_significators() uses via
    _d10_native_house_evidence()) and a current dynamic-transit-climate
    signal (a short, dampened-weight forward window via
    _transit_corroboration(), distinct from the multi-year timed-windows
    forecast in Layer 4) -- both routed into the relevant mode(s) rather
    than only ever considered downstream in the significator ledger.

    as_of_date: reference date for the transit-climate window (defaults to
    today). Exposed mainly for deterministic testing.
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    dignities = _rich_planet_dignities(payload)
    sav = getattr(payload, "sav_points_houses", {}) or {}
    darakaraka = getattr(payload, "darakaraka", "") or ""

    # QA fix (comprehensive gap-audit pass): every DEBILITATED gate/penalty
    # below reads D1 (rasi) dignity from `dignities` and treated it as
    # flatly negative, with no Neecha Bhanga (debilitation-cancellation)
    # check -- unlike significators.py's Lagnesh/H9-lord DEBILITATED notes,
    # yogas.py's yoga tiering, legal_risk.py's four sites, and
    # foreign_business.py's lord-dignity evidence, all of which already
    # call house_evidence._neecha_bhanga_status(). This module's score is
    # diagnostic-only (recommendation.proceed no longer derives from it),
    # but its evidence TEXT is still rendered to astrologer-audience
    # readers, so a chart with a classically-cancelled debilitation could
    # show mode_gate text flatly contradicting significators.py's own
    # "Neecha Bhanga applies" note for the SAME planet in the SAME report
    # -- the same cross-module-contradiction pattern already fixed
    # elsewhere. `_effectively_debilitated` is D1-only (Neecha Bhanga does
    # not apply to D9/D10 divisional dignity -- the two `d9 ==
    # "DEBILITATED"`/`d10 == "DEBILITATED"` checks below are intentionally
    # left as direct comparisons, not routed through this helper).
    def _effectively_debilitated(planet: str, dig: str) -> bool:
        if dig != "DEBILITATED":
            return False
        return not _neecha_bhanga_status(payload, planet).get("cancelled")
    d9_dig = getattr(payload, "d9_planet_dignities", {}) or {}
    d10_dig = getattr(payload, "d10_planet_dignities", {}) or {}
    benefics, malefics = _effective_benefic_malefic_sets(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    def _sav_h(h: int) -> int:
        # Delegates to the shared constants.sav_lookup() helper (factored
        # out so significators.py/mode_gate.py/ashtakavarga_timing.py all
        # share one SAV-lookup implementation instead of three copies).
        return sav_lookup(sav, h)

    def _co_tenants(house: int, exclude: str) -> List[str]:
        return [p for p, h in planet_house.items() if h == house and p != exclude]

    def _varga_corroboration(planet: str, weight: float = 4.0) -> Tuple[float, Optional[str]]:
        """D9/D10-dignity corroboration bonus/penalty for a significator planet,
        the same policy score_business_significators() already applies to H2/H7/H11."""
        d9 = str(d9_dig.get(planet, "") or "").upper()
        d10 = str(d10_dig.get(planet, "") or "").upper()
        if d9 == "DEBILITATED" and d10 == "DEBILITATED":
            return -weight * 1.5, f"{planet} debilitated in BOTH D9 and D10 -> varga denies this mode's promise"
        if d9 in _STRONG_DIGNITY or d10 in _STRONG_DIGNITY:
            return weight, f"{planet} strong in D9/D10 -> varga corroborates this mode"
        if d9 == "DEBILITATED" or d10 == "DEBILITATED":
            return -weight * 0.5, f"{planet} debilitated in D9/D10 -> varga weakens this mode's promise"
        return 0.0, None

    h1_lord, h2_lord, h4_lord = _h(1), _h(2), _h(4)
    h6_lord, h7_lord = _h(6), _h(7)
    h10_lord, h11_lord = _h(10), _h(11)

    # SHARED, documented ceiling across ALL FOUR modes -- NOT accumulated
    # per fired rule, and NOT four separate per-mode ceilings.
    #
    # BUG FIX (audit finding, user-reported wrong recommendation on
    # Karthick_chart): using four DIFFERENT per-mode ceilings and then
    # comparing the resulting percentages (e.g. employment_score vs
    # business_score, or the comparative-advantage margin) is not valid --
    # it compares percentages of two differently-constructed maxima as
    # though they were equivalent probabilities. Concretely: business had
    # MORE raw positive evidence than employment on that chart (35 vs 32),
    # yet scored LOWER (34 vs 44) purely because business's ceiling (104)
    # happened to be larger than employment's (72) -- an artifact of how
    # many rules this module implements for each mode, not a reflection of
    # how astrologically achievable each mode's maximum promise is. A
    # single shared ceiling makes the four modes' raw evidence directly,
    # linearly comparable: recommended_mode = max(scores) and the
    # comparative-advantage margin now reflect which mode has more actual
    # supporting evidence, not which mode's rule-set happens to sum to a
    # bigger number.
    #
    # Legacy diagnostic normalization.  A shared ceiling caused the
    # business accumulator (which has many more rules) to saturate at 100
    # while other modes retained gradation.  Mode-specific reference maxima
    # preserve headroom; this track remains non-authoritative.
    _MODE_FIXED_MAX = {
        "employment": 90.0,
        "business": 125.0,
        "independent": 80.0,
        "family": 70.0,
    }

    modes: Dict[str, Dict[str, Any]] = {
        "employment": {"raw": 0.0, "pos": [], "neg": []},
        "business": {"raw": 0.0, "pos": [], "neg": []},
        "independent": {"raw": 0.0, "pos": [], "neg": []},
        "family": {"raw": 0.0, "pos": [], "neg": []},
    }

    def _score(mode: str, weight: float, cap: float, note: str) -> None:
        # cap is retained as a per-call parameter purely for readability/
        # documentation at each call site (matching _MODE_FIXED_MAX's
        # derivation) -- it no longer affects normalization.
        modes[mode]["raw"] += weight
        modes[mode]["pos"].append(note)

    def _penalize(mode: str, weight: float, note: str) -> None:
        modes[mode]["raw"] -= weight
        modes[mode]["neg"].append(note)

    # ── EMPLOYMENT ──────────────────────────────────────────────────────
    sat_h = _ph("Saturn")
    sat_dig = _dig_name("Saturn", dignities)
    if sat_h == 10 and not _effectively_debilitated("Saturn", sat_dig):
        _score("employment", 20 * _dig_factor("Saturn", dignities), 28,
               f"Saturn in H10 ({sat_dig}) -> structured employment organisation")
    elif sat_h == 10:
        _penalize("employment", 6, "Saturn in H10 but DEBILITATED -> employment structure undermined")
    elif sat_h in (4, 7):
        _score("employment", 12, 12, "Saturn aspects H10 -> disciplined career environment")

    if _ph("Sun") == 10 and not _effectively_debilitated("Sun", _dig_name("Sun", dignities)):
        # Audit finding: Sun in H10 signifies visibility, authority, command
        # and status -- it does NOT distinguish salaried employment from
        # promoter/owner/executive authority. Previously routed exclusively
        # to employment ("government/corporate authority role"), which
        # systematically biased the gate toward employment for any chart
        # with a strong, visible 10th-house Sun regardless of whether that
        # authority manifests as an employee role or as business/executive
        # leadership. Now credited to employment AND independent/business
        # leadership, at reduced weight per mode so it doesn't simply
        # double the old flat bonus.
        _score("employment", 10, 10, "Sun in H10 -> visible authority/status (institutional reading: government/corporate role)")
        _score("independent", 8, 8, "Sun in H10 -> visible authority/status (independent reading: promoter/executive leadership)")
        if _dig_name("Sun", dignities) in _STRONG_DIGNITY or "Sun" in _functional_kendra_trikona_lords(payload):
            _score("business", 6, 6, "Sun in H10, strong/functionally significant for this Lagna -> authority supports business leadership too")

    if h6_lord and _ph(h6_lord) in _KT:
        strength = _house_lord_strength(payload, 6)
        _score("employment", 12 * strength, 12, f"H6 lord ({h6_lord}) in kendra/trikona (strength={strength}) -> service/employment sector")
        v_weight, v_note = _varga_corroboration(h6_lord, 4.0)
        if v_note:
            if v_weight >= 0:
                _score("employment", v_weight, 4.0, v_note)
            else:
                _penalize("employment", abs(v_weight), v_note)

    if _sav_h(10) >= 35:
        _score("employment", 8, 8, "H10 SAV >=35 -> strong institutional career mandate")

    # ── BUSINESS ────────────────────────────────────────────────────────
    if h7_lord:
        strength = _house_lord_strength(payload, 7)
        if strength >= DECISION_POLICY.house_strength_strong_cutoff:
            _score("business", 18 * strength, 18, f"H7 lord ({h7_lord}) in kendra/trikona (strength={strength}) -> business partnerships activated")
        elif strength < DECISION_POLICY.house_strength_moderate_cutoff:
            _penalize("business", 6, f"H7 lord ({h7_lord}) weak (strength={strength}) -> partnership foundation under-supported")
        v_weight, v_note = _varga_corroboration(h7_lord, 5.0)
        if v_note:
            if v_weight >= 0:
                _score("business", v_weight, 5.0, v_note)
            else:
                _penalize("business", abs(v_weight), v_note)

    rahu_h = _ph("Rahu")
    if rahu_h == 7:
        afflicted = bool({"Saturn", "Mars", "Ketu"} & set(_co_tenants(7, "Rahu")))
        if afflicted:
            _penalize("business", 8, "Rahu in H7 conjunct natural malefic -> unstable/contentious partnerships")
        else:
            # v22 audit fix (spec section 15, false-conclusion guard #2:
            # "Strong Rahu means entrepreneurship" -- Rahu in an
            # unafflicted H7 may equally give foreign, digital or
            # unconventional WORK WITHIN EMPLOYMENT, e.g. an MNC role,
            # remote/offshore service delivery, or a corporate
            # cross-border assignment. This previously credited the full
            # +14 unconditionally, auto-coding Rahu-in-H7 as entrepreneurship
            # exactly as the spec warns against. Now requires the same
            # ownership-structure corroboration the rest of this function
            # demands elsewhere (H7 lord actually connected to H2/H10/H11)
            # before granting the full business credit; without that
            # corroboration it's flagged as ambiguous and split at reduced
            # weight between business and employment, reflecting that an
            # unconventional/foreign H7 signature alone doesn't discriminate
            # ownership from employment.
            h7_connects_to_ownership = bool(h7_lord and (h7_lord in (h2_lord, h10_lord, h11_lord) or _ph(h7_lord) in (2, 10, 11)))
            if h7_connects_to_ownership:
                _score("business", 14, 14, "Rahu in H7 (unafflicted), AND H7 lord independently connects to H2/H10/H11 -> unconventional/foreign business partnerships corroborated by an ownership-structure link")
            else:
                _score("business", 5, 14, "Rahu in H7 (unafflicted) but H7 lord shows NO independent H2/H10/H11 connection -> ambiguous: may be foreign/digital business OR foreign/remote employment, not auto-credited as entrepreneurship")
                _score("employment", 5, 14, "Rahu in H7 (unafflicted) without ownership-structure corroboration -> may equally read as an MNC/offshore/remote employment role")

    if h11_lord and _ph(h11_lord) in {10, 7}:
        strength = _house_lord_strength(payload, 11)
        _score("business", 12 * strength, 12, f"H11 lord ({h11_lord}) in H10/H7 (strength={strength}) -> business gains activated")

    # Audit finding: the H7-H10 sambandha (partnership house connected to
    # livelihood house) is the single strongest business/public-dealing
    # configuration on a chart where the same planet rules both -- it was
    # visible in the significator ledger (_d1_tenth_lord_direct_evidence)
    # but never scored in the mode gate itself, so the decision layer
    # never saw the chart's strongest business yoga. Scored here directly,
    # plus a dedicated credit for the H10 lord occupying its OWN house
    # (H10) -- a direct livelihood-authority combination distinct from
    # generic kendra/trikona placement.
    # v42 audit fix (#6 follow-up, user-caught via a real chart -- Lakshman
    # Kumar, where Jupiter rules both H7 and H10): this scored the SAME-LORD
    # structural fact (true for every ascendant where one planet naturally
    # rules both 7th and 10th -- an ascendant-inherent condition, not a
    # distinguishing feature of this individual chart) at the same full
    # weight and "strongest business/public-dealing configuration" wording
    # as a genuine cross-house OCCUPANCY connection (the 7th lord actually
    # sitting in the 10th, or vice versa -- a real, chart-specific fact).
    # house_evidence.py's equivalent check (_d1_tenth_lord_direct_evidence)
    # was already fixed this way in v41; this mode_gate.py check scores the
    # SAME underlying fact independently into the legacy business_score and
    # was missed in that pass. Same-lord-only now scores lower and is
    # worded to disclose it as ascendant-structural background; a genuine
    # occupancy connection keeps the original full weight and wording.
    h7_h10_occupancy_connection = bool(h7_lord) and (_ph(h7_lord) == 10 or _ph(h10_lord) == 7)
    h7_h10_same_lord_only = bool(h7_lord) and h7_lord == h10_lord and not h7_h10_occupancy_connection
    if h7_h10_occupancy_connection:
        _score("business", 10, 10, f"H7-H10 sambandha (H7 lord {h7_lord} / H10 lord {h10_lord}) -> partnership house directly connected to livelihood, strongest business/public-dealing configuration")
        _score("employment", 5, 5, f"H7-H10 sambandha (H7 lord {h7_lord} / H10 lord {h10_lord}) -> also supports professional standing generally")
    elif h7_h10_same_lord_only:
        _score("business", 4, 4, f"H7/H10 share the same lord ({h7_lord}) -- a structural fact of this ascendant, not a distinguishing cross-house connection for this individual chart; that planet's own dignity/placement still matters, but this is background context, not an independent partnership-feeds-livelihood yoga")
        _score("employment", 2, 2, f"H7/H10 share the same lord ({h7_lord}) -- same structural-background caveat applies to the employment reading")
    if h10_lord and _ph(h10_lord) == 10:
        dig = _dig_name(h10_lord, dignities)
        if not _effectively_debilitated(h10_lord, dig):
            _score("business", 8, 8, f"H10 lord ({h10_lord}) occupies its own house (H10), dignity={dig} -> direct livelihood-authority combination")
            _score("employment", 6, 6, f"H10 lord ({h10_lord}) occupies its own house (H10), dignity={dig} -> stable professional standing")

    # Audit finding: employment credits H6-lord-in-kendra/trikona (service/
    # employment sector) but business had no parallel credit for H11 (gains)
    # lord well placed in a trikona (dharma/creative house) -- an enterprise/
    # institution-building signal, not merely "gains activated in H7/H10"
    # (the rule immediately above this one, which requires H7/H10
    # specifically). This is the missing parallel: H11 lord in ANY trikona.
    if h11_lord and _ph(h11_lord) in _TRIKONA:
        strength = _house_lord_strength(payload, 11)
        _score("business", 10 * strength, 10, f"H11 lord ({h11_lord}) in trikona (strength={strength}) -> enterprise/institution-building gains signature")

    if darakaraka:
        dk_house = _ph(darakaraka)
        dig = _dig_name(darakaraka, dignities)
        dk_effectively_debil = _effectively_debilitated(darakaraka, dig)
        if dk_house in _KT and not dk_effectively_debil and (dk_house == 7 or h7_lord == darakaraka):
            _score("business", 10 * _dig_factor(darakaraka, dignities), 14,
                   f"DK ({darakaraka}) strong and H7-linked -> partnership/public karma supports business")
        elif dk_house in _DUSTHANA and dk_effectively_debil:
            _penalize("business", 6, f"DK ({darakaraka}) debilitated in dusthana -> partnership karma strained")

    mer_h, ven_h = _ph("Mercury"), _ph("Venus")
    if mer_h and ven_h:
        conjunct = mer_h == ven_h
        mutual_seventh = abs(mer_h - ven_h) == 6
        if (conjunct or mutual_seventh) and (mer_h in _KT or ven_h in _KT):
            relation = "conjunct" if conjunct else "in mutual 7th aspect"
            _score("business", 10, 10, f"Mercury + Venus {relation}, one in kendra/trikona -> trade/negotiation signature")

    if h2_lord and h7_lord and (h2_lord == h7_lord or _ph(h2_lord) == 7):
        _score("business", 8, 8, "H2-H7 connection -> business wealth accumulation")

    # ── INDEPENDENT ─────────────────────────────────────────────────────
    if h1_lord and _ph(h1_lord) in {1, 10}:
        strength_factor = _dig_factor(h1_lord, dignities)
        if not _effectively_debilitated(h1_lord, _dig_name(h1_lord, dignities)):
            _score("independent", 18 * strength_factor, 25.2, f"Lagna lord ({h1_lord}) in H1/H10 -> independent professional mandate")
        else:
            _penalize("independent", 6, f"Lagna lord ({h1_lord}) in H1/H10 but DEBILITATED -> independent mandate undermined")

    sun_dig = _dig_name("Sun", dignities)
    if sun_dig in _STRONG_DIGNITY and _ph("Sun") in _KT:
        _score("independent", 14, 14, "Sun strong in kendra -> independent leadership practice")

    planets_in_h7 = [p for p, h in planet_house.items() if h == 7]
    if not planets_in_h7:
        _score("independent", 4, 4, "No planet in H7 -> independent work, no partnership compulsion")

    if mer_h in {1, 10} and not _effectively_debilitated("Mercury", _dig_name("Mercury", dignities)):
        _score("independent", 10, 10, "Mercury in H1/H10 -> intellectual independent practice")

    # Audit fix: only the LAGNA LORD's placement was ever scored (via
    # _lagna_lord_strength/h1_lord-in-H1/H10 above); what actually OCCUPIES
    # the lagna house itself -- the classical self/temperament signature --
    # had no parallel evidence, unlike H7 immediately above ("no planet in
    # H7"). Score lagna occupants the same way: a benefic occupant supports
    # a self-driven temperament, a malefic occupant (functional-lordship-
    # aware, via _effective_benefic_malefic_sets) strains it, and an
    # occupant's own D1 debilitation is flagged explicitly and
    # unconditionally -- independent of benefic/malefic classification,
    # since even a naturally benefic but debilitated planet in the lagna
    # weakens the native's core signification.
    planets_in_h1 = [p for p, h in planet_house.items() if h == 1]
    benefic_in_h1 = [p for p in planets_in_h1 if p in benefics]
    malefic_in_h1 = [p for p in planets_in_h1 if p in malefics]
    debilitated_in_h1 = [p for p in planets_in_h1 if _effectively_debilitated(p, _dig_name(p, dignities))]
    if benefic_in_h1:
        _score("independent", 8, 8, f"Benefic(s) {', '.join(sorted(set(benefic_in_h1)))} occupy Lagna (H1) -> self-driven temperament supported")
    if malefic_in_h1:
        _penalize("independent", 5, f"Malefic(s) {', '.join(sorted(set(malefic_in_h1)))} occupy Lagna (H1) -> self-driven temperament under strain")
    if debilitated_in_h1:
        _penalize("independent", 6, f"Planet(s) {', '.join(sorted(set(debilitated_in_h1)))} occupying Lagna (H1) DEBILITATED -> core self-signification weakened regardless of benefic/malefic classification")

    # v18 audit fix: the independent-professional group (spec: 1-2-5-9-10-11)
    # previously only had H1/H5/Mercury/Sun rules -- H2 (monetisation of
    # solo practice/consulting fees) and H9 (fortune/mentorship supporting
    # an independent path) were entirely missing from this bucket, even
    # though both are named members of the spec's independent-professional
    # house group.
    if h2_lord:
        h2_strength_ind = _house_lord_strength(payload, 2)
        if h2_strength_ind >= DECISION_POLICY.house_strength_strong_cutoff:
            _score("independent", 8 * h2_strength_ind, 8, f"H2 lord ({h2_lord}) well placed (strength={h2_strength_ind}) -> solo-practice/consulting revenue retention supported")

    h9_lord_ind = _h(9)
    if h9_lord_ind:
        h9_dig_ind = _dig_name(h9_lord_ind, dignities)
        h9_effectively_debil = _effectively_debilitated(h9_lord_ind, h9_dig_ind)
        if _ph(h9_lord_ind) in _KT and not h9_effectively_debil:
            _score("independent", 8 * _dig_factor(h9_lord_ind, dignities), 8, f"H9 lord ({h9_lord_ind}) in kendra/trikona, dignity={_dig_disclosure(h9_lord_ind, dignities, payload)} -> fortune/mentorship supports an independent professional path")
        elif h9_effectively_debil:
            _penalize("independent", 4, f"H9 lord ({h9_lord_ind}) DEBILITATED -> fortune support for independent practice withheld")

    # v20 audit fix: the independent-professional group (spec: 1-2-5-9-10-
    #11) still had no H11 rule at all -- for a solo practitioner/consultant
    # (as opposed to a scaled business), H11 represents referral networks,
    # repeat clients and professional reputation converting into realized
    # gains, which is a distinct signal from H2 (fee retention) already
    # scored above.
    if h11_lord:
        h11_strength_ind = _house_lord_strength(payload, 11)
        h11_dig_ind = _dig_name(h11_lord, dignities)
        h11_effectively_debil = _effectively_debilitated(h11_lord, h11_dig_ind)
        if h11_strength_ind >= DECISION_POLICY.house_strength_strong_cutoff and not h11_effectively_debil:
            _score("independent", 8 * h11_strength_ind, 8, f"H11 lord ({h11_lord}) well placed (strength={h11_strength_ind}) -> referral network/reputation converts into realized gains for a solo practice")
        elif h11_effectively_debil:
            _penalize("independent", 4, f"H11 lord ({h11_lord}) DEBILITATED -> referral-network gains for independent practice undermined")

    # ── FAMILY BUSINESS ─────────────────────────────────────────────────
    if h4_lord and h2_lord and (h4_lord == h2_lord or _ph(h4_lord) == 2):
        _score("family", 16, 16, "H4-H2 connection -> family wealth/property involvement")

    moon_h, moon_dig = _ph("Moon"), _dig_name("Moon", dignities)
    if moon_h in {4, 10} and moon_dig in _STRONG_DIGNITY:
        _score("family", 14, 14, "Moon strong in H4/H10 -> family business emotional foundation")

    if h4_lord and _ph(h4_lord) == 10:
        _score("family", 12, 12, "H4 lord in H10 -> career rooted in family/homeland")

    if ven_h in {2, 4} and not _effectively_debilitated("Venus", _dig_name("Venus", dignities)):
        _score("family", 8, 8, "Venus in H2/H4 -> family commerce/arts business")

    # ── D10 (DASHAMSHA)-NATIVE HOUSE GRAPH ──────────────────────────────
    # Previously the mode gate only used D9/D10 PLANET-dignity corroboration
    # (_varga_corroboration, on the H6/H7 lords only). This routes the same
    # full D10-native house-graph evidence score_business_significators()
    # already uses (D10's own house graph, not D1 placement projected onto
    # D10 dignity) into the relevant mode(s), based on which D10 house each
    # finding concerns: D10-H7 (venture) -> business; D10-H10 (livelihood)
    # -> both employment and business (career-general); D10-H11 (gains) ->
    # business and family; the combined benefic/malefic H2/H7/H11 vs
    # H6/H8/H12 occupancy notes -> business (the house set this check reads
    # is venture-framed).
    for weight, note in _d10_native_house_evidence(payload):
        target_modes: List[str] = []
        if "H7 (venture)" in note:
            target_modes = ["business"]
        elif "H10 (livelihood)" in note or "occupy D10-H10" in note:
            target_modes = ["employment", "business"]
        elif "H11 (gains)" in note:
            target_modes = ["business", "family"]
        else:
            target_modes = ["business"]
        tagged_note = f"[D10-native] {note}"
        for mode in target_modes:
            if weight >= 0:
                _score(mode, weight, weight, tagged_note)
            else:
                _penalize(mode, abs(weight), tagged_note)

    # ── DYNAMIC TRANSIT CLIMATE (current, bounded window) ───────────────
    # A static viability gate should not average a chart owner's entire
    # lifetime of transits, but it also should not ignore the CURRENT
    # transit climate entirely -- whether the immediate astrological
    # weather actively supports or strains launching a venture right now
    # is a real, distinct signal from natal promise. Reuses the same
    # _transit_corroboration() (mean-motion projection, see its own
    # docstring for the JUPITER_H2/H11_EXPANSION / JUPITER_H6/8/12_STRESS /
    # SATURN_H6/8_DISRUPTION flag policy) already used for timed windows,
    # scoped to a short forward-looking window (today .. +2y). It is
    # exposed for timing/actionability but excluded from natal scores.
    as_of = as_of_date or date.today()
    transit_window_end = as_of.replace(year=as_of.year + 2)
    transit_net, transit_notes, transit_status = _transit_corroboration(as_of, transit_window_end, payload, as_of)
    # Transit is timing evidence, not natal promise.  Earlier releases
    # mutated the structural business score here, so the same chart could
    # receive a different business-vs-job promise solely from as_of_date.
    for note in transit_notes:
        tagged_note = f"[transit-climate, timing-only; excluded from natal score] {note}"
        modes["business"]["pos"].append(tagged_note)
    if isinstance(transit_status, dict):
        transit_status = dict(transit_status)
        transit_status["net_score_timing_only"] = transit_net
        transit_status["included_in_natal_mode_score"] = False

    # ── KP H7-CUSP SUB-LORD SIGNIFICATION + AMATYAKARAKA (static, chart-level) ──
    # Audit finding: KP significator analysis and the Amatyakaraka (Jaimini
    # career/professional karaka) were computed and used for TIMED WINDOWS
    # (which dasha periods look favorable) but never fed into the static
    # viability gate itself, producing exactly the kind of internal
    # contradiction the audit called out: a chart can be told "do not
    # proceed" by the static gate while its KP/Jaimini timing evidence
    # (used elsewhere in the same report) says the business houses are
    # actively, favorably activated. This adds two static, chart-level
    # (not dasha-period-bound) findings: (1) whether the H7 cusp's own
    # sub-lord has a KP signification set that leans toward result-
    # producing houses (2/7/10/11) rather than dispute/loss (6/8/12) --
    # reusing the SAME _kp_sublord_signification_bias() the timed-windows
    # Tier-2 arbiter already uses, just evaluated once at the chart level
    # instead of per dasha lord; (2) whether the Amatyakaraka (the karaka
    # most classically tied to profession/career direction) itself rules
    # a business-relevant house (H2/H7/H10/H11).
    # v-audit fix (item 5, follow-on): both KP checks below (H7 sub-lord
    # bias and the 10th-cusp job/business read) used to credit/penalize
    # business_score/employment_score at full weight regardless of whether
    # the underlying cusp chain was ever independently verified -- the SAME
    # unverified-chain problem already gated in scoring.py's kp/kp_2_6_10_11
    # layers (see kp.py::_verify_kp_cusp_chain), just not yet propagated to
    # this earlier, static mode-gate scoring pass. Verified once here and
    # reused for both checks below, so an unverified chain no longer moves
    # business_score/employment_score at all -- consistent with how the
    # layered promise system already treats the same fact.
    _kp_cusp_audit = _verify_kp_cusp_chain(payload)
    _kp_chain_verified = bool(_kp_cusp_audit.get("chain_verified"))

    kp_cusps = getattr(payload, "kp_cusps", {}) or {}
    h7_cusp = kp_cusps.get("H7", {}) if isinstance(kp_cusps, dict) else {}
    h7_sub_lord = h7_cusp.get("sub_lord", "") if isinstance(h7_cusp, dict) else ""
    if h7_sub_lord and _kp_chain_verified:
        bias, pos_houses, neg_houses = _kp_sublord_signification_bias(h7_sub_lord, payload)
        if bias == "POSITIVE":
            _score("business", 8, 8, f"KP: H7 cusp sub-lord ({h7_sub_lord}) itself significates result-producing houses {pos_houses} -> business activation reads favorable, not just present")
        elif bias == "NEGATIVE":
            _penalize("business", 6, f"KP: H7 cusp sub-lord ({h7_sub_lord}) itself significates dispute/loss houses {neg_houses} -> business activation reads unfavorable")

    amatyakaraka = getattr(payload, "amatyakaraka", "") or ""
    if amatyakaraka:
        # v22 audit fix: spec section 5 explicitly lists "AmK relationship
        # with the 2nd, 3rd, 7th, 10th and 11th" -- H3 (enterprise/
        # initiative) was omitted, checking only 2/7/10/11.
        amk_houses = [h for h in (2, 3, 7, 10, 11) if _h(h) == amatyakaraka]
        if amk_houses:
            label = "/".join(f"H{h}" for h in amk_houses)
            _score("business", 6, 6, f"Jaimini: Amatyakaraka ({amatyakaraka}) rules {label} -> career/professional karaka directly tied to business houses")
            _score("employment", 4, 4, f"Jaimini: Amatyakaraka ({amatyakaraka}) rules {label} -> also supports professional standing generally")

    # v17 audit fix: the spec's central KP question -- does the 10th CUSP's
    # own sub-lord signification set lean toward the job set {2,6,10,11} or
    # the business set {1/3,2,7,10,11}? -- previously had no dedicated
    # check; only a generic H7-sub-lord result/loss bias existed. This is
    # the static, chart-level counterpart to that.
    kp10 = _kp_10th_cusp_job_vs_business(payload)
    if kp10["status"] == "OK" and kp10.get("chain_verified"):
        if kp10["leaning"] == "BUSINESS":
            _score("business", 8, 8, f"KP: {kp10['note']}")
        elif kp10["leaning"] == "JOB":
            _score("employment", 8, 8, f"KP: {kp10['note']}")

    # v17 audit fix: 5th house was entirely absent from the mode gate too --
    # routes into "independent" (its primary group membership per the
    # spec's 1-2-5-9-10-11 independent-professional set) and, at reduced
    # weight, "business" (5-10-11/5-7 combinations also feed enterprise).
    for weight, note in _fifth_house_business_evidence(payload):
        if weight >= 0:
            _score("independent", weight, weight, note)
            _score("business", weight * 0.5, weight * 0.5, note)
        else:
            _penalize("independent", abs(weight), note)
            _penalize("business", abs(weight) * 0.5, note)

    # v17 audit fix: Karakamsha and Arudha (A10/A7/AL) evidence, previously
    # entirely absent, routed into business primarily (A10 = visible
    # professional/business image; Karakamsha corroborates the vocational
    # mode already read from D1/D10).
    for weight, note in _karakamsha_business_evidence(payload):
        if weight >= 0:
            _score("business", weight, weight, note)
        else:
            _penalize("business", abs(weight), note)
    for weight, note in _arudha_business_evidence(payload):
        if weight >= 0:
            _score("business", weight, weight, note)
        else:
            _penalize("business", abs(weight), note)

    # ── NORMALISATION ───────────────────────────────────────────────────
    def _scale(mode: str) -> int:
        cap = _MODE_FIXED_MAX[mode]
        return int(round(min(100.0, max(0.0, modes[mode]["raw"] / cap * 100.0))))

    emp_s = _scale("employment")
    biz_s = _scale("business")
    ind_s = _scale("independent")
    fam_s = _scale("family")

    scores = {"employment": emp_s, "business": biz_s, "independent": ind_s, "family_business": fam_s}
    recommended = max(scores, key=scores.get)
    sorted_scores = sorted(scores.values(), reverse=True)
    gap = sorted_scores[0] - sorted_scores[1]
    confidence = "HIGH" if gap >= 20 else "MODERATE" if gap >= 10 else "LOW"

    # Bug fix: moon_h == rahu_h evaluated 0 == 0 (both unplaced/missing) as a
    # match, falsely classifying charts with no real Rahu/Moon data as
    # "international". Both placements must be genuinely known (nonzero)
    # for the Moon-conjunct-Rahu geographic signal to fire.
    moon_h_for_geo = _ph("Moon")
    geo_pref = "domestic"
    if rahu_h in {9, 12} or (rahu_h and moon_h_for_geo and moon_h_for_geo == rahu_h) or (h7_lord and _ph(h7_lord) == 12):
        geo_pref = "international"
    elif rahu_h == 7:
        geo_pref = "both"

    all_signals = (modes["business"]["pos"] + modes["employment"]["pos"] +
                   modes["independent"]["pos"] + modes["family"]["pos"])

    return {
        "employment_score": emp_s,
        "business_score": biz_s,
        "independent_score": ind_s,
        "family_biz_score": fam_s,
        "recommended_mode": recommended,
        "confidence": confidence,
        "key_signals": all_signals[:8],
        "geographic_preference": geo_pref,
        # Extended, signed fields not present on the legacy employment_mode
        # output -- used for the comparative business-vs-employment margin
        # check in compute_business_prediction().
        "positive_signals": {m: d["pos"] for m, d in modes.items()},
        "negative_signals": {m: d["neg"] for m, d in modes.items()},
        "transit_climate_status": transit_status,
        # Engineering audit fix #6: was stuck at "v28-sector-score-dignity-
        # precision-fix" long after RULE_PACK_VERSION and this package's own
        # "vNN audit fix" comments moved past v28. Bumped to match
        # RULE_PACK_VERSION (see constants.py) -- keep these two in sync.
        "gate_policy": f"{RULE_PACK_VERSION}-explicit-blocked-gaps",
    }

