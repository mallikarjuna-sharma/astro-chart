"""JyotishAI — Main scoring engine (run_engine) and QA helpers."""
import math as _math
import os as _os
import random as _random
from typing import Dict, List, Tuple, Set, Any, Optional

# Print-output optimization (2026-08-20, this pass): the per-field debug/
# narrative prints below (`[FIELD SCORE]`, `[FIELD NARRATIVE]`,
# `[CROSS-VERIFICATION NARRATIVE]`, `[DASHA-SUSTAINABILITY NARRATIVE]`,
# `[V2-PRIMARY FINAL_SCORE]`, `[TIE-BREAK]`, `[FIELD-LEVEL FILTER STATUS]`,
# etc.) fire once per field per run and are only useful for deep
# instrumentation/audit passes -- for a normal run they drown out the actual
# "FINAL TOP 20 FIELDS" summary report in console output. Gated behind an
# opt-in env var so a normal run only prints the summary; set
# JYOTISH_VERBOSE_FIELD_LOG=1 to restore the full per-field narrative log.
_VERBOSE_FIELD_LOG = _os.environ.get("JYOTISH_VERBOSE_FIELD_LOG", "0") == "1"

from .payload import NatalPayloadV2, ENGINE_VERSION, logger
from .constants import (
    _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES,
    _SIGN_LORD, _SIGN_NUM, _STREAM_MAP, _VALID_PLANETS, DOMAIN_STRATEGIES,
    _NEECHA_BHANGA_DATA, _NAKSHATRA_LORD  # Added for Gap 3 & 5 Fixes
)
from .astro import (
    compute_dignity, _compute_eff_strengths, _get_planetary_aspects,
    _detect_yogas, _detect_neecha_bhanga, _is_vargottama,
    _get_active_dasha_lord, _planet_abs_degree, _detect_planetary_war,
    _get_nakshatra_dignity, _detect_jaimini_raj_yogas,
    _compute_whole_sign_houses, _get_active_chara_dasha_sign,
    _compute_arudha_pada # <-- Make sure this is added!
)
from .engine_io import _load_course_registry
from .registry_result_enricher import attach_v12_registry_metadata
from .ranking_policy import (
    annotate_wide_corroboration_visibility,
    reconcile_legacy_leakage_annotations,
    apply_publication_ranking_policy,
    annotate_rank_differentiation,
    reapply_leakage_guards_post_lockout,
)
from .canonical_facts import build_canonical_facts
from .run_manifest import build_run_manifest
from .shadow_scoring import attach_shadow_scores
from .release_candidate import apply_release_4_7
from .audit_ledgers import attach_audit_ledgers
from .validation_contract import (
    UNIVERSAL_DISCLAIMER, calculation_identity, evidence_status, privacy_contract,
)
from .calculation_policy import build_calculation_policy
from .evidence_layers import evidence_layers

from .affinity import BRANCH_PLANET_AFFINITY, compute_branch_affinity_score_llm, apply_vargottama_affinity_uplift, _GENERIC_9P_WEIGHTS
from .engine_io import compute_aptitude_by_domain, _load_course_registry
from Field_Determination.field_methods import compute_field_method_bundle
# Tiered ranking override (2026-08-18): replaces the flat 9-method blend's
# contribution to field RANKING order with a 3-tier classical-authority
# model. See jyotish/tiered_ranking.py's module docstring for the full
# design rationale and the by-hand audit (Ramsunder, Akash Shanmugham)
# that motivated it. Applied once, as the final ranking-authority step,
# inside _finalize_published_results() below.
from .tiered_ranking import compute_tiered_ranking
# Phase B (shadow-score migration, 2026-08-19): compute the §10-refined
# composite score (jyotish/composite_v2.py) alongside the live scoring path
# for comparison only. Purely additive -- see _build_composite_v2_chart_primitives()
# and the shadow-scoring loop inside _finalize_published_results() below.
# Nothing here changes final_score, hard_lockout, or ranking order.
from . import composite_v2
from . import dasha_longevity
# Competency-first ontology layer (2026-07 architecture audit G1-G18, G23-G30):
# adds Competency -> Career Family grouping, confidence bands, explanation
# chains, and a bounded family-cohesion adjustment on top of the existing
# 199-branch deterministic scoring. See jyotish/competency_ontology.py.
from Field_Determination.competency_ontology import apply_competency_ontology_layer
from Field_Determination.competency_ontology import build_cluster_report
from Field_Determination.competency_ontology import confidence_band
from Field_Determination.competency_ontology import build_evidence_summary
from .ontology_kg import attach_graph_diagnostics
# 2026-07 gap-audit corrections: Ketu Classic/Analytical mode, student MD
# weighting, Mrita-consistency, Venus branch-by-companion, interest-prior
# (round 1); macro-cluster gate, Mars mode, Moon/Saturn Mrita, hybrid-vs-plain
# resolver, risk-appetite niche discount, self-audit (round 2); broadness-
# penalty wiring + Virgo-10th/Mercury-10th-lord accelerator (round 3).
from .gap_corrections_2026_07 import (
    apply_gap_2026_07_corrections, apply_gap_2026_07_round2_corrections,
    apply_gap_2026_07_round3_corrections, build_round2_audit_summary,
)
# Pipeline-consolidation fix (audit): score_sudarshana is no longer called
# directly here -- Sudarshana is now a first-class 6th method inside
# compute_field_method_bundle() (see field_methods/__init__.py), and this
# module reads its normalized score from bvb_eval instead of a second,
# separate call. Import removed to avoid an unused, misleading duplicate
# entry point.
from Field_Determination.field_methods.common import (
    FIELD_PRIORITY_GROUPS,
    METHOD_SCORE_CAP,
    METHOD_SCORE_CAPS,
    build_gate_text,
    normalize_method_score,
    prioritize_rows,
    correlation_discount_factor,
)
from .boosts import (
    _kp_h10_branch_strength, _kp_edu_branch_strength, _h10_sublord_bonus, _kp_edu_starlord_bonus,
    _dasha_bonus, _karakamsha_bonus, _ak_combustion_penalty,
    _d24_ak_delta, _d24_full_chart_bonus, _lagna_lord_bonus, _risk_appetite_bonus,
    _yogakaraka_bonus, _yogakaraka_debilitation_penalty, _h10_lord_strength_bonus, _ul_lord_bonus,
    _d9_ak_delta, _yoga_bonus, _h5_lord_bonus, _amk_house_bonus,
    _ak_house_bonus, _planet_combustion_penalty, _dusthana_lord_penalty,
    _peak_career_dasha, _peak_career_dasha_boost, _dasha_active_affinity_boost,
    _d10_consistency_penalty, _pratyantar_dasha_bonus, _karakamsha_occupant_bonus,
    _bhavesha_phala_edu_bonus, _d9_h10_bonus, _dharma_karma_bonus,
    _d10_h10_bonus, _gender_field_modifier, _aspect_h10_bonus,
    _maheshwara_lord_bonus, _interest_preference_boost, _brahma_lord_bonus,
    _chart_specific_aptitude_supplement, _ak_planet_domain_boost, _ak_domain_flat_supplement,
    _karakamsha_domain_boost, _h3_lord_communication_boost,
    _h12_stellium_penalty, _build_critical_warnings,
    apply_domain_deduplication, _d10_lagna_lord_bonus, _stellium_bonus,
    _classify_parivartana,
    _h10_lord_trikona_bonus,
    # ── 10/10 upgrade functions ────────────────────────────────────────────
    _nakshatra_career_score,
    _nodal_axis_career_signal,
    _viparita_raja_yoga_bonus,
    _d10_comprehensive_bonus,
    _hora_mode_career_signal,
    _avastha_career_modifier,
    _avastha_planet_mults,
    _h3_lord_career_bonus,
    _pushkara_navamsha_boost,
    _pada_field_discriminator,
    _chara_dasha_timing_signal,
    _lagna_element_career_bonus,
    _d1_d10_h10_double_dignity_bonus,
    _spiritual_career_proxy,
    _guna_balance_modifier,
    _lagna_lord_dusthana_directive,
    _adhi_anapha_yoga_bonus,
    _transit_career_activation,
    # ── Round-3 10/10 upgrade functions ───────────────────────────────────────
    _person_archetype_score,
    _lagna_propensity_score,
    _moon_rashi_propensity,
    _mahapurusha_mandate_score,
    _career_parivartana_bonus,
    _war_winner_domain_bonus,
    _h10_lord_combustion_flag,
    _compound_dasha_quality,
    _putrakaraka_field_score,
    _gnatikaraka_field_score,
    _bhratrikaraka_field_score,
    _matrikaraka_field_score,
    _darakaraka_field_score,
    _gochar_h10_activation_bonus,
    _kaksha_activation_bonus,
    _trikona_unity_bonus,
    _dasha_timing_gate,
    _bav_individual_boost,
    _yogi_avayogi_modifier,
    _confidence_convergence_grade,
    _confluence_gate,
    _YOGAKARAKA_PLANET,
    _modernize_karakas_modifier,
    _exalted_planet_domain_bonus,
    _life_science_signal,
    _space_aerospace_signal,
    _priority_cluster_field_bonus,
    _space_aerospace_cluster_bonus,
    _life_science_cluster_bonus,
    _space_extractive_counterweight,
    _life_science_space_counterweight,
    _life_science_engineering_counterweight,
    _kp_career_h2h11_strength,
    # ── 360° Profile scorers (Module 1 Expansion) ────────────────────────
    compute_corporate_entrepreneurial_score,
    compute_wealth_potential,
    compute_geo_suitability,
    compute_burnout_risk,
    # ── Academic & Institutional gaps (Module 1 Gaps 1–4) ─────────────────
    compute_academic_path,
    compute_institutional_tier,
    compute_micro_niches,
    build_confidence_matrix,
    build_field_summary_json,
    detect_chart_type,
)
from .llm import call_llm_for_fields, _build_chart_summary_for_llm

import math as _math

_COMPOSITE_SOFT_CAP = 200.0   # LS14: Composite scores can reach ~115 before log compression
_AFFINITY_SOFT_CAP  = 180.0   # LS14: Affinity scores cluster higher (all planets contribute) →
                               # earlier compression (at 180 not 200) prevents affinity
                               # dominating the blend beyond current_domain_blend weight alone.

from .constants import _PLANET_MIN_SHADBALA, _VALID_DOMAINS
from .astro import _paksha_bala, _calc_age, _detect_combust_planets as _det_combust, _compute_jaimini_argala
from .boosts import _ALL_PLANETS, DASHA_KEYWORDS, _wm, _d60_vitality_gate
from .vimshopaka import compute_vimshopaka_bala
from .panchang import _MALEFIC_TITHIS


def _log_norm_score(x: float, soft_cap: float) -> float:
    """Q2: Sigmoid aptitude scaling preserves contrast in the 60-90 band.

    Baseline = half of soft_cap (centre of empirical aptitude distribution).
    k = 0.040 calibrated so: 90th-pct chart hits ~88, 50th-pct chart hits ~50.
    Naturally asymptotes to 100 without extension above cap.
    """
    import math as _m
    baseline = soft_cap * 0.50
    k = 0.040
    return round(100.0 / (1.0 + _m.exp(-k * (x - baseline))), 4)

# ── Module-level constants (originally in monolith body) ─────────────────
_COURSE_REGISTRY: Dict[str, Dict] = _load_course_registry()
AFFINITY_BLEND, DOMAIN_BLEND = 0.40, 0.60

# Physical engineering / material-mastery fields eligible for the Saturn-AK
# structural grit boost. These fields require hands-on mastery of physical matter,
# industrial process, or structural transformation — domains that Saturn (as
# Atmakaraka or Yogakaraka) authorises at the soul level.
_MATERIAL_GRIT_FIELDS: frozenset = frozenset({
    "materials_science_engineering",        "metallurgical_engineering",
    "mining_engineering",                   "petroleum_engineering",
    "polymer_plastics_engineering",         "industrial_engineering",
    "production_manufacturing_engineering", "mechanical_engineering",
    "chemical_engineering",                 "leather_technology",
    "automotive_engineering",              # registry id for Automobile/Automotive
})

def execute_qa_verification_v8_9(field, chart_data, domain, war_result=None, d10_digs=None, d9_digs=None):
    """QA gate applying structural friction multipliers to raw field scores.

    Merged from v9.0 severity-scale approach + FIX-11/FIX-12 astrological corrections:
    A. Full combustion hierarchy — all planets checked with classical severity weights.
    B. Planetary War (Graha Yuddha) — defeated planets generate massive friction and can be fatal.
    C. Domain-scoped checks — dynamically extracted from BRANCH_PLANET_AFFINITY per field.
    D. Budha-Aditya Yoga    — Mercury combust + yoga → immune (classical exception).
    E. Shadbala modulation  — ratio ≥ 1.50× → immune; ≥ 1.30× → friction halved.
    F. Universal Varga Offset — D10/D9/D24 excellence forgives D1 friction for ANY primary karaka.
    G. Generalized Fatal Conditions — structural planets across ALL domains (arts/law/medicine/STEM).
    """
    if war_result is None:
        war_result = {}
        
    friction, is_fatal = 0, False
    # Fix (2026-08-20): tracks WHY is_fatal fired, so the D10/D24 varga-offset
    # rescue below can forgive a combustion-caused fatal the same way it
    # already forgives combustion-caused continuous friction, without also
    # forgiving a planetary-war-loss fatal (war loss stays fully fatal --
    # classically a much more severe, structural condition than combustion,
    # which is a temporary proximity-to-Sun affliction).
    _fatal_cause = ""
    notes_list = []
    combust_set    = set(getattr(chart_data, "combust_planets", []))
    war_losers     = set(p for p, s in war_result.items() if "loser" in s)
    planet_digs    = getattr(chart_data, "planet_dignities", {})
    ak             = getattr(chart_data, "atmakaraka", "")
    detected_yogas = set(getattr(chart_data, "detected_yogas", [])
                         + getattr(chart_data, "yogas_present", []))
    shadbala       = getattr(chart_data, "shadbala", {})
    d24_digs       = getattr(chart_data, "d24_planet_dignities", {})

    # ── Classical combustion severity (Parashari hierarchy) ───────────────────
    # AC5 fix: Rahu/Ketu removed — nodes cannot be combust or in Graha Yuddha;
    # their _SEVERITY entries were permanently dead code.
    _SEVERITY: Dict[str, float] = {
        "Saturn": 0.75, "Mars": 0.60,
        "Jupiter": 0.45, "Venus": 0.30, "Moon": 0.20, "Mercury": 0.05,
    }
    
    # Fetch specific karakas for this field from affinity mapping
    field_affinity = BRANCH_PLANET_AFFINITY.get(field, {})
    if field_affinity:
        relevant = list(field_affinity.keys())
        primary_karaka = max(field_affinity.items(), key=lambda x: x[1])[0]
    else:
        # Fallback if no specific field affinity is mapped
        _DOMAIN_RELEVANT: Dict[str, List[str]] = {
            "engineering": ["Saturn", "Mars", "Ketu", "Mercury"],
            "science":     ["Mercury", "Saturn", "Ketu", "Mars"],
            "technology":  ["Mercury", "Rahu", "Saturn"],
            "medicine":    ["Moon", "Jupiter", "Mercury"],
            "arts":        ["Venus", "Moon", "Mercury"],
        }
        relevant = _DOMAIN_RELEVANT.get(domain, [])
        primary_karaka = ""

    # Combine all afflicted planets that need QA structural checks
    afflicted_planets = combust_set | war_losers

    for planet in afflicted_planets:
        if planet == "Sun": continue
        if planet not in relevant: continue

        is_combust = planet in combust_set
        is_war_loser = planet in war_losers

        min_v = _PLANET_MIN_SHADBALA.get(planet, 300.0)
        ratio = shadbala.get(planet, 0.0) / min_v if min_v else 1.0
        dig = planet_digs.get(planet, "")

        weight = field_affinity.get(planet, 0.25) if field_affinity else 0.25
        weight_mod = weight / 0.25  # normalize impact
        
        planet_friction = 0

        # ── 1. Evaluate Combustion ──────────────────────────────────────────────
        if is_combust:
            if planet == "Mercury" and "BudhaAditya" in detected_yogas:
                notes_list.append("BudhaAditya Yoga: Mercury-Sun conjunction = sharp-intellect "
                                   "yoga (classical immunity). Zero friction from combustion.")
            elif ratio >= 1.50:
                notes_list.append(f"{planet} combust but Shadbala {ratio:.2f}× min — "
                                   "structural strength overrides combustion.")
            else:
                # Gap-4 fix: eff_strength in astro.py already applies 0.75–0.85× combustion
                # penalty to the base score. Adding QA friction on top = double-dipping.
                # Continuous friction is suppressed; FATAL structural conditions below still fire.
                notes_list.append(
                    f"{planet} combust in {domain}: eff_strength penalty already applied in "
                    f"astro.py — QA continuous friction suppressed (Gap-4 fix).")

        # ── 2. Evaluate Planetary War (Graha Yuddha) ────────────────────────────
        if is_war_loser:
            w_raw_f = int(60 * weight_mod) # War loss is a massive baseline hit
            if dig in ("EXALTED", "OWN"): w_raw_f = int(w_raw_f * 0.60)
            if ak == planet:              w_raw_f = int(w_raw_f * 0.80)
            if ratio >= 1.50:             w_raw_f = max(10, w_raw_f // 2)
            planet_friction += w_raw_f
            notes_list.append(f"{planet} defeated in Graha Yuddha: +{w_raw_f} friction "
                              f"(devastating structural loss).")

        if planet_friction > friction:
            friction = planet_friction

        # ── 3. Evaluate FATAL conditions ────────────────────────────────────────
        is_primary = (planet == primary_karaka)
        _ENG_SCI = ("engineering", "science")

        # Structural planets by domain: each domain has specific planets whose
        # affliction is catastrophic for that domain's expression.
        # Previously only engineering/science had fatal conditions (asymmetric bias).
        # Now generalized to all major domains for symmetry.
        _DOMAIN_STRUCTURAL_PLANETS: Dict[str, tuple] = {
            "engineering":      ("Saturn", "Ketu"),
            "science":          ("Saturn", "Ketu"),
            "arts":             ("Venus",),
            "law":              ("Jupiter",),
            "medicine":         ("Moon", "Jupiter"),
            "technology":       ("Mercury",),
            "humanities":       ("Moon", "Jupiter"),
            "interdisciplinary": ("Jupiter", "Mercury"),
        }
        # AK guard: if the AK aligns with the domain, don't apply fatal
        # (soul-level alignment overrides structural affliction)
        _DOMAIN_AK_GUARD: Dict[str, tuple] = {
            "arts":             ("Venus", "Moon"),
            "law":              ("Jupiter", "Sun"),
            "medicine":         ("Moon", "Jupiter"),
            "technology":       ("Mercury", "Rahu"),
            "humanities":       ("Moon", "Jupiter", "Venus"),
            "interdisciplinary": ("Jupiter", "Mercury"),
        }

        if not is_fatal and dig not in ("EXALTED", "OWN") and ratio < 1.30:
            # Fatal condition 1: Primary karaka is a war loser
            if is_primary and is_war_loser:
                is_fatal = True
                _fatal_cause = "war"
                notes_list.append(f"FATAL: Primary karaka {planet} defeated in war in {domain} — "
                                   "core field competency completely devastated.")
            # Fatal condition 2: Primary karaka is combust (except Mercury)
            elif is_primary and is_combust and planet != "Mercury":
                is_fatal = True
                _fatal_cause = "combust"
                notes_list.append(f"FATAL: Primary karaka {planet} combust in {domain} — "
                                   "core field competency severely suppressed.")
            # Fatal condition 3: Structural planet in domain afflicted
            # STEM (engineering/science): both war-loss AND combustion can be fatal.
            # Non-STEM (arts/law/medicine): combustion of primary domain karaka is also
            # fatal when Shadbala is insufficient — combust Venus cannot express aesthetics;
            # combust Jupiter cannot express wisdom/judgment in law.
            elif planet in ("Saturn", "Ketu") and domain in _ENG_SCI and (is_war_loser or is_combust):
                is_fatal = True
                reason = "defeated in war" if is_war_loser else "combust"
                _fatal_cause = "war" if is_war_loser else "combust"
                notes_list.append(f"FATAL: {planet} {reason} in {domain} — "
                                   "structural/technical architecture severely disrupted.")
            # Fatal condition 3b: Primary karaka combust in non-STEM domain (symmetry with STEM)
            elif (is_combust and is_primary
                  and planet in _DOMAIN_STRUCTURAL_PLANETS.get(domain, ())
                  and domain not in _ENG_SCI
                  and ak not in _DOMAIN_AK_GUARD.get(domain, ())):
                is_fatal = True
                _fatal_cause = "combust"
                notes_list.append(f"FATAL: {planet} combust in {domain} — "
                                   "primary domain karaka expression severely suppressed.")
            # Fatal condition 3c: Structural planet war-loss in non-STEM domains
            elif (is_war_loser
                  and planet in _DOMAIN_STRUCTURAL_PLANETS.get(domain, ())
                  and domain not in _ENG_SCI
                  and ak not in _DOMAIN_AK_GUARD.get(domain, ())):
                is_fatal = True
                _fatal_cause = "war"
                notes_list.append(f"FATAL: {planet} defeated in war in {domain} — "
                                   "primary domain karaka devastated (non-STEM equivalent).")

    # Cap friction
    friction = min(friction, 100)

    # ── E: Universal Varga Recovery Mechanism (D10 / D24 Offset) ──────────────────────
    # D10 (Dashamsha): career architecture chart — primary varga for career assessment.
    # D24 (Siddhamsha): academic mastery chart — fires when D24 data is populated.
    # NOTE: D9 (Navamsha) deliberately excluded here. D9 is a "soul chart" and the
    # stress test default D9 has every planet dignified (synthetic placeholder), which
    # would universally neutralize QA gate friction across all domains, collapsing the
    # differential scoring the engine relies on. D9 is used elsewhere (d9_h10_bonus,
    # vargottama checks) where it's additive rather than friction-cancelling.
    if primary_karaka and (friction > 0 or (is_fatal and _fatal_cause == "combust")):
        pk_d10 = d10_digs.get(primary_karaka, "") if d10_digs else ""
        pk_d24 = d24_digs.get(primary_karaka, "")
        _pk_varga_strong = pk_d10 in ("EXALTED", "OWN") or pk_d24 in ("EXALTED", "OWN")

        varga_offset = 0
        if friction > 0:
            if pk_d10 in ("EXALTED", "OWN"):
                varga_offset = min(friction, 20)
                notes_list.append(f"D10 {primary_karaka} {pk_d10} (Dashamsha): career architecture offsets {varga_offset} friction pts.")
            elif pk_d24 in ("EXALTED", "OWN"):
                varga_offset = min(friction, 15)
                notes_list.append(f"D24 {primary_karaka} {pk_d24} (Siddhamsha): academic mastery offsets {varga_offset} friction pts.")
            friction -= varga_offset

        # Fix (2026-08-20): a combustion-caused fatal (conditions 2/3b above)
        # is now also rescuable by a strong D10/D24 placement of the SAME
        # primary karaka -- previously only continuous friction got this
        # rescue, so a chart with e.g. an exalted-in-D10 primary karaka that
        # happened to be combust in D1 still hit the full fatal penalty with
        # no way back, which is inconsistent with this function's own D-fix
        # ("Universal Varga Offset -- D10/D9/D24 excellence forgives D1
        # friction for ANY primary karaka"). War-loss fatal conditions (1/3c)
        # are deliberately NOT rescued here -- Graha Yuddha defeat is a much
        # more severe classical condition than combustion and stays fully
        # fatal regardless of divisional-chart strength.
        if is_fatal and _fatal_cause == "combust" and _pk_varga_strong:
            is_fatal = False
            _rescue_chart = "D10 Dashamsha" if pk_d10 in ("EXALTED", "OWN") else "D24 Siddhamsha"
            notes_list.append(
                f"FATAL RESCINDED: {primary_karaka} combust in D1, but {_rescue_chart} "
                f"placement is {pk_d10 if pk_d10 in ('EXALTED', 'OWN') else pk_d24} -- "
                "divisional-chart strength overrides the D1 fatal flag (varga rescue)."
            )

    # ── Final multiplier ──────────────────────────────────────────────────────
    friction_multiplier = max(0.65, 1.0 - friction / 100.0)
    if is_fatal:
        friction_multiplier = round(friction_multiplier * 0.70, 4)

    notes = " | ".join(notes_list) if notes_list else "Verified: Structural alignment optimal."
    return {
        "passed_qa_gate":            not is_fatal,
        "structural_friction_score": friction,
        "friction_multiplier":       friction_multiplier,
        "audit_notes":               notes,
    }


def assess_domain_mismatch(aptitudes, domain, planet_dignities=None, combust_planets=None,
                           detected_yogas=None, shadbala=None,
                           branch_affinity_weights: Dict[str, float] = None,
                           ak: str = "", amk: str = "",
                           nb_set: set = None):
    """Combustion mismatch respects Budha-Aditya yoga and Shadbala."""
    if planet_dignities is None: planet_dignities = {}
    if combust_planets  is None: combust_planets  = []
    if detected_yogas   is None: detected_yogas   = []
    if shadbala         is None: shadbala          = {}
    if nb_set           is None: nb_set            = set()
    yoga_set = set(detected_yogas)

    # Arts mismatch: suppress penalty when the soul (AK) or career direction (AmK)
    # genuinely aligns with arts. 
    _combust_set_mismatch = set(combust_planets) if combust_planets else set()
    _ak_is_arts_soul = (
        # Venus AK: bypasses arts mismatch unless DEBILITATED or combust (combust = temporary, not structural arts soul)
        (ak == "Venus" and planet_dignities.get("Venus", "") not in ("DEBILITATED",)
         and "Venus" not in _combust_set_mismatch)
        or (ak == "Venus" and "Venus" in nb_set          # NB Venus bypasses mismatch only when NOT actually debilitated
            and planet_dignities.get("Venus", "") not in ("DEBILITATED",))
        or (ak == "Moon"  and planet_dignities.get("Moon",  "") in ("EXALTED", "OWN"))
        # AmK=Venus OWN/EXALTED only bypasses arts mismatch when AK is also arts-aligned
        # (Venus or Moon). When AK is Mars/Saturn/Mercury etc., the soul mandate for
        # engineering/technology overrides Venus AmK's career tilt toward arts.
        or (amk == "Venus" and planet_dignities.get("Venus", "") in ("EXALTED", "OWN")
            and ak in ("Venus", "Moon"))
    )
    if (domain == "arts"
            and not _ak_is_arts_soul
            and aptitudes.get("secondary_aptitude", 0) > 40):
        return {"mismatch_risk": True,
                "notes": "High Mismatch Risk: Systems-thinking exceeds arts domain norms."}
    if (domain == "arts"
            and aptitudes.get("secondary_aptitude", 0) > aptitudes.get("primary_aptitude", 0)
            and aptitudes.get("secondary_aptitude", 0) > 55):
        return {"mismatch_risk": True,
                "notes": "High Mismatch Risk: Secondary analytical planet strongly dominates primary arts karaka."}

    # Derive top-2 planets from LLM affinity
    if branch_affinity_weights:
        top_sorted = sorted(branch_affinity_weights.items(), key=lambda x: -x[1])
        pair = tuple(p for p, _ in top_sorted[:2])
    else:
        pair = ()

    for pp in pair:
        if planet_dignities.get(pp) == "DEBILITATED" and pp not in nb_set:
            return {"mismatch_risk": True,
                    "notes": f"Domain risk: {pp} debilitated — primary {domain} planet compromised."}
        if pp in combust_planets:
            if pp == "Mercury" and "BudhaAditya" in yoga_set:
                continue   # yoga grants classical immunity
            ratio = shadbala.get(pp, 0.0) / _PLANET_MIN_SHADBALA.get(pp, 300.0)
            if ratio >= 1.50:
                continue   # overwhelming strength overrides combustion flag
            return {"mismatch_risk": True,
                    "notes": f"Domain caution: {pp} combust — primary {domain} planet expression reduced."}
    return {"mismatch_risk": False, "notes": "Alignment nominal."}

# ===========================================================================
# MODULE E: ORCHESTRATION KERNEL
# A2 fix: AFFINITY_BLEND/DOMAIN_BLEND defined once at module top (line 86).
# ===========================================================================

def classify_age_stage(current_age: float, top_results: List[Dict]) -> Dict:
    stage = None
    if 14 <= current_age < 17:
        stage = "class_9_10"
    elif 17 <= current_age < 20:
        stage = "class_11_12"
    else:
        return {"stage": "adult", "guidance": "Full career rankings apply directly."}

    stream_votes: Dict[str, float] = {}
    for rec in top_results[:10]:
        domain = rec.get("domain", "")
        stream = _STREAM_MAP.get(domain, "")
        if stream:
            stream_votes[stream] = stream_votes.get(stream, 0) + rec.get("final_score", 0)

    top_streams = sorted(stream_votes.items(), key=lambda x: x[1], reverse=True)

    if stage == "class_9_10":
        primary_stream = top_streams[0][0] if top_streams else "Undetermined"
        alt_stream = top_streams[1][0] if len(top_streams) > 1 else ""
        guidance = (
            f"Recommended 11th stream: {primary_stream}. "
            + (f"Alternate option: {alt_stream}. " if alt_stream else "")
            + "Choose stream by end of 10th to align with top career fields."
        )
    else:  # class_11_12
        top_domains = list({rec["domain"] for rec in top_results[:5]})
        degree_paths = []
        for rec in top_results[:3]:
            degree_paths.append(f"{rec['field_label']} ({rec['domain'].upper()})")
        guidance = (
            f"Currently in 11th/12th. Top degree paths to target: {'; '.join(degree_paths)}. "
            f"Focus entrance prep on: {', '.join(top_domains[:3])} domains."
        )

    return {
        "stage": stage,
        "top_streams_by_score": [{"stream": s, "weighted_score": round(sc, 1)} for s, sc in top_streams[:3]],
        "guidance": guidance,
    }


def _get_prime_career_lord(dasha_seq: List[Dict]) -> str:
    lord_durations = {}
    for d in dasha_seq:
        start = d.get("start_age")
        end = d.get("end_age")
        if start is None or end is None: continue
        
        overlap_start = max(25.0, start)
        overlap_end = min(45.0, end)
        if overlap_start < overlap_end:
            lord = d.get("lord", "")
            lord_durations[lord] = lord_durations.get(lord, 0.0) + (overlap_end - overlap_start)
            
    if not lord_durations:
        return ""
    return max(lord_durations.items(), key=lambda x: x[1])[0]



def _prepare_unbiased_llm_payload(results: List[Dict]) -> List[Dict]:
    """Pass the top-35 to LLM sorted by final_score (highest first).

    Previous implementation shuffled order (seed=42) to prevent LLM position
    bias, but each row already carries an explicit score — so the LLM sorted
    by score anyway, making the shuffle a no-op that only destroyed the clean
    rank ordering. Removed. Scores are the signal; position is irrelevant.
    """
    payload = []
    for idx, r in enumerate(results):
        entry = dict(r)
        entry["original_index"]     = idx
        entry["deterministic_score"] = round(r.get("final_score", r.get("python_score", 0.0)), 2)
        payload.append(entry)
    # Sort highest score first so rank column in the prompt is meaningful
    payload.sort(key=lambda x: x["deterministic_score"], reverse=True)
    return payload


def _enforce_post_llm_guards(llm_ordered: List[Dict]) -> List[Dict]:
    """After LLM reordering, push hard-locked fields to the bottom.

    Fields tagged hard_lockout=True (score < 20 or is_afflicted) must not
    appear in the top results regardless of any stochastic LLM placement.
    """
    valid, quarantined = [], []
    for track in llm_ordered:
        _score = track.get("final_score", track.get("score", 100.0))
        _locked = (
            track.get("hard_lockout", False)
            or bool(track.get("is_afflicted", False))
            or _score < 20.0
        )
        if _locked:
            track["rank_score"] = 0.0
            track["hard_lockout"] = True
            quarantined.append(track)
        else:
            valid.append(track)
    return valid + quarantined


def _enforce_hard_lockout_publication_order(rows: List[Dict]) -> List[Dict]:
    """Push hard-locked fields (score < 20 or is_afflicted) below every valid
    field in the published order, without deleting them or altering their
    final_score -- this is the same "push to bottom, never delete" contract
    _enforce_post_llm_guards already documented.

    GAP-FIX (2026-07-18, 19-chart top-20 audit): hard_lockout is computed and
    exposed on every row (see _run_normalization_stage's LLM-payload block,
    which runs unconditionally regardless of enable_llm), but until this fix
    nothing in the deterministic path ever *enforced* it -- the only function
    that did, _enforce_post_llm_guards, had zero callers anywhere in engine.py.
    Confirmed on real chart data: fields the engine internally flagged
    is_afflicted (astrologically compromised despite a decent numeric score,
    e.g. 44-47) were still published at rank #12/#18, and sub-20 fields
    filled ranks 13-20 with no indication they had failed the validity
    threshold. Must run AFTER apply_publication_ranking_policy's own
    final_score-only sort (that sort would otherwise immediately undo any
    reordering placed before it, since it does not know about hard_lockout).
    engine_rank is intentionally left untouched here -- it remains the
    pre-publication-policy audit trail of the raw engine's score order;
    `rank` is what actually gets published/displayed and is restamped below.
    """
    exploratory_only = [r for r in rows if r.get("publication_eligibility") == "exploratory_only"]
    valid = [r for r in rows if not r.get("hard_lockout", False) and r.get("publication_eligibility") != "exploratory_only"]
    locked = [r for r in rows if r.get("hard_lockout", False) and r.get("publication_eligibility") != "exploratory_only"]
    ordered = valid + locked + exploratory_only
    for idx, row in enumerate(ordered, 1):
        row["rank"] = idx
        row["publication_score"] = float(row.get("final_score", 0.0) or 0.0)
    return ordered


def _apply_display_score_compression(results: List[Dict]) -> List[Dict]:
    """Final, display-only pass: cap final_score onto a 0-100 printed scale.

    Gap fix (2026-08, chat audit, revised per user's explicit architecture
    request): this MUST be the very last thing run_engine() does. Every
    ranking, tie-break, discount, hard-lockout, and ceiling-tie/differentiation
    decision above has already run on the genuine uncapped final_score (now
    also preserved verbatim as raw_final_score) -- confirmed on ramsunder's
    chart: computational_finance's true chain total (117.35) and
    industrial_engineering's (101.52) are ~16 points apart and must be
    treated as such by ranking/ties/confidence, even though both exceed the
    printed 0-100 scale. Only the number actually shown in a report should
    ever be capped. `rank` has already been stamped by
    _enforce_hard_lockout_publication_order() before this runs, so
    compressing final_score here cannot reorder anything -- it only affects
    the printed number for fields that exceeded 100.

    GAP-FIX (2026-08 audit, monotonicity + publication_score sync):
    Two bugs in the previous version of this function, both display-only
    (they never touched `rank`, so ordering was never actually wrong --
    only what was PRINTED next to each field could be):

    1. Only rows with raw final_score > 100 were rescaled, into a fixed
       [98, 100] band positioned by each row's rank *within the overshoot
       subset only*. A row just below 100 (never touched) could end up
       showing a HIGHER number than a higher-ranked overshoot row squeezed
       down near 98 -- e.g. rank 2 (raw 101, overshoot) -> 98.0 while rank 3
       (raw 99.5, untouched) stays 99.5, so the report would print field #3
       with a bigger score than field #2. Fixed below by clamping every
       row's displayed final_score to be <= the previous (higher-ranked)
       row's displayed final_score, walking the list in rank order -- this
       guarantees the printed numbers can never contradict `rank`, while
       still compressing only the overshoot rows and leaving every row's
       final_score untouched otherwise (ties are still allowed to print
       equal, just never inverted).
    2. `publication_score` (stamped equal to the pre-compression raw
       final_score by _enforce_hard_lockout_publication_order /
       _finalize_published_results) was never re-synced after compression,
       so it could carry an uncapped (>100) value forever -- any consumer
       reading `publication_score` instead of `final_score` would see the
       exact >100 scale violation this whole function exists to prevent.
       Now re-stamped here, in this same final pass, to always equal the
       post-compression, guaranteed-<=100, monotonic final_score.

    ATTEMPTED FIX (2026-08-22, this audit pass) -- REVERTED SAME DAY after
    regression testing: tried exempting D60/BAV tie-broken rows
    (`v2_tiebreak_applied`) from this ceiling, first globally then scoped to
    each row's own tie cluster (`_tiebreak_cluster_leader_score`), to stop a
    tie-broken row's genuinely-higher v2 score from being silently
    suppressed to match its post-tiebreak rank (traced on
    mithila_chart_details.json: organisational_psychology, v2=100.0 -- the
    best score in its 7-way ~98-100 tie cluster -- printed as 98.0 because
    the ceiling had already been pulled down by earlier rows by the time the
    walk reached its rank). Both versions broke
    `test_ramsunder_results_are_strictly_score_ordered`
    (tests/test_career_track_regressions.py), a locked regression test that
    asserts valid (non-hard-locked) results are GLOBALLY strictly descending
    by `final_score` with NO exemption for tie-broken rows -- confirmed the
    per-cluster version still let jyotish_vedic_astrology (84.05) print
    above public_policy (83.07) one rank below it on ramsunder's chart, a
    direct violation of that test's explicit contract. That test predates
    this pass and encodes the intended design on purpose: `rank` order and
    displayed `final_score` order must always match for valid rows, even
    when D60/BAV decided that order via a tie-break rather than the raw v2
    composite. The "suppression" this pass tried to fix is not a bug --
    it's this exact contract working as designed, compressing a tied
    cluster's true score differentiation down to match its decided display
    order. Reverted in full back to the original unconditional ceiling walk
    below; the organisational_psychology finding stays valid as a factual
    observation (D60 can outrank a higher-v2-score field within a tie
    cluster) but is not something this function should special-case.
    """
    for _r in results:
        _r.setdefault("raw_final_score", _r.get("final_score", 0.0))
    overshoot = [r for r in results if r.get("final_score", 0.0) > 100.0]
    if overshoot:
        vals = [r["final_score"] for r in overshoot]
        os_max, os_min = max(vals), min(vals)
        span = (os_max - os_min) or 1.0
        FLOOR = 98.0
        for r in overshoot:
            if os_max == os_min:
                r["final_score"] = 100.0
            else:
                r["final_score"] = round(FLOOR + (100.0 - FLOOR) * (r["final_score"] - os_min) / span, 2)

    # Walk in rank order (results is already rank-ordered by the time this
    # runs -- see the docstring above -- but sort defensively so this
    # function's monotonicity guarantee holds even if a future caller
    # passes it an unordered list) and clamp each row's displayed
    # final_score to never exceed the previous, higher-ranked row's
    # displayed final_score. This is a no-op for every row that wasn't
    # touched by the overshoot rescale above; it only ever pulls a value
    # DOWN, never up, so it cannot inflate any score past what the engine
    # actually computed.
    _rank_ordered = sorted(
        results, key=lambda r: r.get("rank", float("inf")) if isinstance(r.get("rank"), (int, float)) else float("inf")
    )
    _display_ceiling = 100.0
    for r in _rank_ordered:
        _v = min(float(r.get("final_score", 0.0) or 0.0), 100.0, _display_ceiling)
        r["final_score"] = round(_v, 2)
        _display_ceiling = r["final_score"]
        r["publication_score"] = r["final_score"]
    return results


def _sort_by_final_score_desc(rows: List[Dict]) -> List[Dict]:
    """Return rows ordered by final_score descending and restamp display ranks."""
    sorted_rows = sorted(
        rows or [],
        key=lambda r: float(r.get("final_score", r.get("deterministic_score", r.get("python_score", 0.0))) or 0.0),
        reverse=True,
    )
    for idx, row in enumerate(sorted_rows, 1):
        row["rank"] = idx
        row["engine_rank"] = idx
        if "llm_rank" in row:
            row["llm_rank"] = idx
    return sorted_rows


def _detect_mrita_avastha(planets_d1: Dict) -> Set[str]:
    """Return planets in Mrita (dead) Avastha — degree 24°–30° in odd signs,
    or 0°–6° in even signs.  These planets cannot manifest career indications."""
    _ODD = {"Aries", "Gemini", "Leo", "Libra", "Sagittarius", "Aquarius"}
    result = set()
    for planet, pdata in planets_d1.items():
        if not isinstance(pdata, dict):
            continue
        sign   = pdata.get("sign", "")
        degree = float(pdata.get("degree", 0))
        if sign in _ODD and degree >= 24.0:
            result.add(planet)
        elif sign and sign not in _ODD and degree < 6.0:
            result.add(planet)
    return result


def _apply_structural_impairment(
    affinity: Dict[str, float],
    war_losers: Set[str],
    mrita_planets: Set[str],
) -> Dict[str, float]:
    """Return a copy of affinity with Graha Yuddha loser planets halved.

    Only war losers are halved here. Mrita Avastha is intentionally NOT applied
    at the affinity level — it is handled with dignity-aware floors inside
    _d1_vitality_coefficient(), which is called by every method scorer.
    Applying it here as well would double-penalise Mrita planets (once in the
    blended-affinity pathway and again in every method scorer), suppressing
    earth/industry fields far below their true karaka signal.
    """
    if not war_losers:
        return affinity
    result = dict(affinity)
    for planet in war_losers:          # Mrita planets deliberately excluded
        if planet in result:
            result[planet] = result[planet] * 0.50
    return result


def _build_explainability_matrix(field_id: str, method_scores: Dict[str, float]) -> Dict:
    """Build a structured paradigm-concurrence object for XAI.

    Status thresholds (per-method 0-100 score scale):
      >= 75 → CRITICAL_CONFIRMATION
      >= 60 → STRONG_SUPPORT
      >= 45 → MODERATE_SUPPORT
      >= 30 → WEAK_SUPPORT
       < 30 → LOW_SIGNAL
    Structural friction flag fires when paradigm spread (max-min) > 40 points,
    indicating significant inter-method disagreement.
    """
    def _status(score: float) -> str:
        if score >= 75: return "CRITICAL_CONFIRMATION"
        if score >= 60: return "STRONG_SUPPORT"
        if score >= 45: return "MODERATE_SUPPORT"
        if score >= 30: return "WEAK_SUPPORT"
        return "LOW_SIGNAL"

    concurrence = {}
    for method, score in method_scores.items():
        concurrence[method] = {
            "score":  round(score, 1),
            "status": _status(score),
        }

    scores = list(method_scores.values())
    spread = (max(scores) - min(scores)) if scores else 0.0
    friction_flag = ""
    # Gap-3 fix: two separate friction conditions.
    # (a) Any method returning 0.0 — data gap, not just low score; penalty overflow silences whole method.
    # (b) Paradigm spread > 30 (was 40) — catches meaningful divergence without waiting for extreme cases.
    _zero_methods = [m for m, s in method_scores.items() if s == 0.0]
    if _zero_methods:
        friction_flag = (
            f"{'、'.join(m.title() for m in _zero_methods)} returned 0 — "
            "data gap or penalty overflow; single-method dominance likely. "
            "Treat field score with reduced confidence."
        )
    elif spread > 30.0:
        weakest = min(method_scores, key=method_scores.__getitem__)
        strongest = max(method_scores, key=method_scores.__getitem__)
        friction_flag = (
            f"{weakest.title()} shows low structural resonance ({method_scores[weakest]:.1f}); "
            f"{strongest.title()} strongly confirms ({method_scores[strongest]:.1f}). "
            "Field alignment may rely on a single paradigm axis rather than full concurrence."
        )

    return {
        "field_id":               field_id,
        "paradigm_concurrence":   concurrence,
        "paradigm_spread":        round(spread, 1),
        "structural_friction_flag": friction_flag,
    }


def _apply_minmax_normalization(results: List[Dict]) -> List[Dict]:
    """Attach the normalized method layer used by the explainability report.

    The bundle already normalizes every method onto a shared 0-100 scale before
    weighting. This post-pass keeps that scale visible in the final engine rows
    and recomputes the weighted contributions for the report.
    """
    if not results:
        return results

    # 2026-07 engine-gap audit fix: this tuple previously covered only 4 of
    # the engine's 6 scoring methods, so the paradigm_spread/friction_flag
    # computed below (and the penalty applied by
    # _apply_paradigm_spread_penalty right after this function runs) was
    # blind to KNRao/KP/Jaimini/Parashara agreeing with each other while
    # Dashamsha or Sudarshana sharply disagreed -- exactly the D10-vs-rest
    # disagreement pattern the audit flagged repeatedly. Both are folded into
    # the spread/friction diagnostic below whenever the bundle produced them.
    methods = ("knrao", "kp", "jaimini", "parashara")
    from Field_Determination.field_methods import METHOD_WEIGHTS

    for r in results:
        raw_scores = r.get("method_scores", {}) or {}
        bundle_norm_scores = r.get("method_normalized_scores", {}) or {}
        norm_scores = {}
        for m in methods:
            if m in bundle_norm_scores:
                norm_scores[m] = max(0.0, min(100.0, float(bundle_norm_scores.get(m, 0.0))))
            else:
                norm_scores[m] = normalize_method_score(raw_scores.get(m, 0.0), METHOD_SCORE_CAP)
        weighted_contribs = {
            m: round(norm_scores.get(m, 0.0) * METHOD_WEIGHTS.get(m, 0.25), 2)
            for m in methods
        }
        combined = round(sum(weighted_contribs.values()), 2)
        r["method_scores_normalized"] = {m: round(v, 2) for m, v in norm_scores.items()}
        r["method_weighted_contributions"] = weighted_contribs
        r["combined_score_normalized"] = round(combined, 2)
        r["method_total_score_normalized"] = round(combined, 2)
        r["weighted_method_score"] = round(combined, 2)

        # Fold in dashamsha/sudarshana for the SPREAD/friction diagnostic
        # specifically (the 4-method display matrix stays as-is for backward
        # compatibility with existing report layouts/tests).
        _spread_scores = dict(norm_scores)
        for _m in ("dashamsha", "sudarshana"):
            if _m in bundle_norm_scores:
                _spread_scores[_m] = max(0.0, min(100.0, float(bundle_norm_scores.get(_m, 0.0))))
            elif _m in raw_scores:
                _spread_scores[_m] = normalize_method_score(
                    raw_scores.get(_m, 0.0), METHOD_SCORE_CAPS.get(_m, METHOD_SCORE_CAP)
                )
        r["explainability_matrix"] = _build_explainability_matrix(
            r.get("field_id", ""),
            {m: round(v, 2) for m, v in _spread_scores.items()}
        )
    return results


def _apply_paradigm_spread_penalty(results: List[Dict]) -> List[Dict]:
    """2026-07 engine-gap audit fix: wire the already-computed paradigm_spread /
    structural_friction_flag (built in _build_explainability_matrix, attached
    by _apply_minmax_normalization) into an actual bounded score effect.

    Before this fix these diagnostics were computed and surfaced in reports
    ("Field alignment may rely on a single paradigm axis...") but never
    consumed anywhere -- a field could have several of its 6 methods
    disagree by 30-90+ points and still keep its full score, which is the
    direct mechanism behind several false positives the audit found (a
    single dominant method, usually inflated by flat keyword-domain
    supplements, carrying a field to #1 while every other method scored it
    "WEAK_SUPPORT" or lower).

    Same bounded/capped/score-baked discipline as every other adjustment in
    this engine (friction_multiplier floor 0.65, gap_2026_07 total cap 0.35,
    family-cohesion +/-4%, yoga-alignment +0-5%): additive-percentage,
    clamped, then applied once as a single multiplication -- never a
    reorder-only nudge, so it survives every later
    `results.sort(key=lambda r: -r["final_score"])` call intact.
    """
    if not results:
        return results

    for r in results:
        matrix = r.get("explainability_matrix") or {}
        spread = float(matrix.get("paradigm_spread", 0.0) or 0.0)
        concurrence = matrix.get("paradigm_concurrence", {}) or {}
        zero_methods = [m for m, v in concurrence.items() if v.get("score", 0.0) == 0.0]

        pct = 0.0
        note = ""
        if zero_methods:
            # A method returning exactly 0 is a data gap / penalty overflow,
            # not just "this method is unimpressed" -- treat it as more
            # serious than a pure spread disagreement.
            pct = -0.14
            note = f"paradigm_gap: {', '.join(zero_methods)} returned 0 -- single-method dominance risk -14%"
        elif spread > 30.0:
            # Linear ramp: -5% at spread=30 up to -20% at spread>=70 (hard cap).
            pct = -min(0.20, 0.05 + (spread - 30.0) * (0.15 / 40.0))
            note = f"paradigm_spread={spread:.1f} (inter-method disagreement) {pct:+.1%}"

        if pct:
            r["final_score"] = round(r.get("final_score", 0.0) * (1.0 + pct), 2)
            r["paradigm_spread_penalty_pct"] = round(pct, 4)
            r["paradigm_spread_note"] = note

    return results


def _build_verified_factors(gap_detail: Dict[str, float], threshold_pct: float = 2.0) -> str:
    """XAI-B: Return only gap-boost components above threshold for LLM token grounding.

    Converts proportion values to percentage points; excludes internal keys (prefix _).
    Returns pipe-separated 'key:+val%' string or empty string.
    """
    parts = []
    for key, val in sorted(
            [(k, v) for k, v in gap_detail.items() if isinstance(v, (int, float))],
            key=lambda x: -abs(x[1])):
        if key.startswith("_"):
            continue
        pct = round(val * 100, 1)
        if abs(pct) >= threshold_pct:
            sign = "+" if pct >= 0 else ""
            parts.append(f"{key}:{sign}{pct}%")
    return " | ".join(parts)


def _apply_interdomain_normalization(results: List[Dict]) -> List[Dict]:
    """S2: Soft Max Inter-Domain Normalization.

    Groups fields by domain. The top-ranked field per domain is fully protected.
    Every other same-domain field that shares ≥2 of the top-3 affinity planets
    with the domain leader receives a 0.90× penalty on final_score.
    A hard cap additionally penalises fields ranked 3rd+ in a domain regardless
    of planet overlap (max 2 unpenalised slots per domain).
    """
    from collections import defaultdict
    domain_groups: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(results):
        domain_groups[r.get("domain", "")].append(i)

    for domain, indices in domain_groups.items():
        if len(indices) < 2:
            continue
        top_idx     = indices[0]
        top_planets = set(list(results[top_idx].get("affinity_planets", {}).keys())[:3])
        for rank, idx in enumerate(indices[1:], 2):
            r_planets = set(list(results[idx].get("affinity_planets", {}).keys())[:3])
            shared    = len(top_planets & r_planets)
            if shared >= 2 or rank > 2:
                results[idx]["final_score"] = round(results[idx]["final_score"] * 0.90, 2)
                results[idx].setdefault("gap_breakdown", {})["_interdomain_norm_penalty"] = -0.10
    return results


def _apply_combined_risk_floor(results: List[Dict], floor: float = 0.50) -> List[Dict]:
    """Gap-audit fix (2026-08): cap the TOTAL combined discount from the
    engine's seven independent risk/mismatch/disagreement gates -- five
    applied per-field inside the main scoring loop (meets_threshold 0.70x,
    domain mismatch 0.85x, friction_multiplier floor 0.65x, QA gate 0.70x,
    debilitated-AK prime-domain 0.85x, captured together as
    `_stage_a_risk_gate_mult`), plus two applied afterward across the whole
    batch (_apply_paradigm_spread_penalty, up to -20%; and
    _apply_interdomain_normalization, 0.90x).

    Each gate's own comment documents its bound as if it were the only
    discount a field could receive -- e.g. "friction_multiplier floor 0.65"
    reads as "this field loses at most 35% from friction". But nothing
    stops several gates firing on the same field simultaneously, and they
    compound multiplicatively: 0.70 x 0.85 x 0.65 x 0.70 x 0.85 x 0.80 x
    0.90 =~ 0.16 -- an 84% cut from seven individually "modest, bounded"
    discounts, none of which alone was ever meant to be that severe.

    Confirmed against a real chart (Midhula, 2026-08 audit): Electrical
    Engineering scored HIGHER than Mechanical Engineering on almost every
    raw method (knrao 70.7 vs 36.8, KP 63.9 vs 44.4, shashtiamsha 37.5 vs
    16.7), and two independent shadow-audit subsystems in this engine's own
    output (hierarchical_shadow's calibrated_structural_percentile,
    meaningful_margin's shadow_position) both independently ranked it near
    the top of the whole candidate pool -- yet it published at rank 28 of
    35, a ~61% cut from `blended_score`, driven almost entirely by these
    gates stacking. Meanwhile Mechanical Engineering, which happened to trip
    fewer of them, nearly doubled from a LOWER `blended_score`. That
    inversion -- a field with broader multi-method corroboration losing to
    a field with narrower support, purely because of how many independent
    risk flags each one happened to trip -- is not documented or intended
    anywhere in this engine's design comments.

    This does not remove or weaken any individual gate. It only caps their
    COMBINED effect at `floor` (50% by default -- deliberately looser than
    several gates' own individual worst case, so a field failing just one
    or two gates is barely touched by this function; only a field failing
    most/all of them at once gets pulled back up toward the floor instead
    of compounding past it). A field whose combined multiplier is already
    at or above the floor is left completely untouched.
    """
    for r in results:
        combined = float(r.get("_stage_a_risk_gate_mult", 1.0) or 1.0)
        combined *= (1.0 + float(r.get("paradigm_spread_penalty_pct", 0.0) or 0.0))
        if r.get("gap_breakdown", {}).get("_interdomain_norm_penalty"):
            combined *= 0.90
        # Gap-audit fix (2026-08, diagnostic-only): previously this combined
        # multiplier was only ever written to the result row when the floor
        # actually triggered (0 < combined < floor), so a field sitting at
        # e.g. 0.51 (barely above the floor, untouched) was indistinguishable
        # from a field that never tripped any gate at all (combined == 1.0)
        # -- both simply had no `combined_risk_gate_mult` key. Recording it
        # unconditionally makes the full seven-gate stacking story (see this
        # function's docstring) auditable for every field, not just the ones
        # that happened to cross the floor threshold. This line does NOT
        # change final_score for any field -- it only adds a diagnostic key.
        r["combined_risk_gate_mult"] = round(combined, 4)
        r["combined_risk_gate_floor_applied"] = bool(0.0 < combined < floor)
        if 0.0 < combined < floor:
            restore = floor / combined
            r["final_score"] = round(r.get("final_score", 0.0) * restore, 2)
            r["combined_risk_gate_floor_restore"] = round(restore, 4)
    return results


def _top3_planets(affinity_planets: Dict[str, float]) -> List[str]:
    """Return top-3 planet names sorted by affinity weight descending."""
    if not affinity_planets:
        return []
    return [p for p, _ in sorted(affinity_planets.items(), key=lambda x: -x[1])[:3]]


def _validate_payload_schema(payload_data: Any) -> None:
    """A1: Strict schema validation at ingestion.

    Raises ValueError immediately if any critical field is None or empty,
    preventing silent failures deep in the scoring loop.

    GAP-FIX: presence-only checks previously let a structurally-broken
    payload through (e.g. planets_d1 = {"Sun": {}} with no "sign"/"degree"
    keys) — every downstream .get(p, {}).get("sign", "") read would then
    silently default to "" instead of raising here, producing degenerate
    (not obviously wrong) scores. We now also spot-check the shape that
    the scoring pipeline actually relies on: each planets_d1 entry must be
    a dict with a non-empty "sign", and each dasha_sequence entry must be
    a dict carrying a "lord". This is deliberately still lightweight (not
    a full schema) so it does not duplicate NatalPayloadV2's own Pydantic
    validation — it only guards the specific shape this scoring pipeline
    reads via getattr/.get() fallbacks that would otherwise mask a bad
    payload as an all-empty-but-"valid" result.
    """
    checks = {
        "planets_d1":       getattr(payload_data, "planets_d1", None),
        "kp_significators": getattr(payload_data, "kp_significators", None),
        "kp_cusps":         getattr(payload_data, "kp_cusps", None),
        "dasha_sequence":   getattr(payload_data, "dasha_sequence", None),
    }
    for field_name, value in checks.items():
        if value is None or (hasattr(value, "__len__") and len(value) == 0):
            raise ValueError(
                f"NatalPayloadV2 validation error: '{field_name}' is None or empty. "
                "All critical chart fields must be populated before calling run_engine()."
            )

    planets_d1 = checks["planets_d1"]
    if isinstance(planets_d1, dict):
        _bad_planets = [
            p for p, v in planets_d1.items()
            if not isinstance(v, dict) or not v.get("sign")
        ]
        if _bad_planets:
            raise ValueError(
                "NatalPayloadV2 validation error: 'planets_d1' entries missing a "
                f"non-empty 'sign' for: {sorted(_bad_planets)}. Each planets_d1 "
                "entry must be a dict with at least a populated 'sign' key."
            )

    dasha_sequence = checks["dasha_sequence"]
    if isinstance(dasha_sequence, (list, tuple)):
        _bad_dasha_idx = [
            i for i, d in enumerate(dasha_sequence)
            if not isinstance(d, dict) or not d.get("lord")
        ]
        if _bad_dasha_idx:
            raise ValueError(
                "NatalPayloadV2 validation error: 'dasha_sequence' entries missing "
                f"a non-empty 'lord' at index(es): {_bad_dasha_idx}. Each "
                "dasha_sequence entry must be a dict with at least a populated "
                "'lord' key."
            )


def _resolve_career_phase(payload_data: Any) -> str:
    """Q7: Hybrid career phase — 60% chronological age + 40% active dasha vector.

    Pure age-gates misfire for:
    - 21-yr-old entering Saturn MD ruling H10 (should be early/mid, not student)
    - 55-yr-old in Jupiter/Moon MD (benefic dashas keep career generative past age gate)

    Dasha vector score: active MD lord rules H10 or H1 → +career_pressure;
    benefic MD (Jupiter/Venus/Moon) → -pressure (creative/learning phase retained).
    """
    explicit = getattr(payload_data, "career_phase", "auto")
    if explicit and explicit.lower() != "auto":
        return explicit.lower()

    age = float(getattr(payload_data, "current_age", 0) or 0)
    yoe = float((getattr(payload_data, "career_context", {}) or {}).get("years_experience", 0) or 0)

    # Age-based score (60% weight): student=0, early=1, mid=2, senior=3
    if age >= 40 or yoe >= 15:
        age_phase_score = 3.0
    elif age >= 28:
        age_phase_score = 2.0
    elif age >= 22:
        age_phase_score = 1.0
    else:
        age_phase_score = 0.0

    # Dasha vector score (40% weight)
    dasha_seq    = getattr(payload_data, "dasha_sequence", []) or []
    house_lords  = getattr(payload_data, "house_lords", {}) or {}
    active_lord  = ""
    for _d in dasha_seq:
        _start = float(_d.get("start_age", 0) or 0)
        _end   = float(_d.get("end_age", 999) or 999)
        if _start <= age < _end:
            active_lord = _d.get("lord", "")
            break

    _PRESSURE_PLANETS   = {"Saturn", "Mars", "Sun", "Rahu"}   # career-pressure lords
    _GENERATIVE_PLANETS = {"Jupiter", "Venus", "Moon"}          # learning/creative lords
    h10_lord = house_lords.get("10", "") or house_lords.get(10, "")
    h1_lord  = house_lords.get("1",  "") or house_lords.get(1,  "")

    dasha_vector = 0.0
    if active_lord:
        if active_lord in _PRESSURE_PLANETS:
            dasha_vector += 0.8   # career execution pressure
        if active_lord == h10_lord:
            dasha_vector += 1.2   # H10 lord activates career house directly
        elif active_lord == h1_lord:
            dasha_vector += 0.5
        if active_lord in _GENERATIVE_PLANETS:
            dasha_vector -= 0.6   # benefic dashas reduce career urgency

    # Combine: 60% age + 40% dasha. If no dasha data is resolvable (no
    # active_lord match -- e.g. dasha_sequence not supplied, or current_age
    # falls outside every window), the 40% dasha component has nothing to
    # contribute and must NOT be silently scored as 0 (which would drag an
    # unambiguous age like 45 down from "senior" to "mid" just because dasha
    # data was missing, rather than because the dasha data said otherwise).
    # In that case fall back to age-only scoring (full weight on age_phase_score).
    # BUGFIX (2026-07, age-45 audit): previously `dasha_vector` defaulted to
    # 0.0 whether "no data" or "dasha genuinely neutral", conflating the two
    # and causing e.g. NatalPayloadV2(current_age=45.0) with no dasha_sequence
    # to resolve to "mid" instead of "senior".
    if active_lord:
        combined = (age_phase_score * 0.60) + (dasha_vector * 0.40)
    else:
        combined = age_phase_score

    if combined >= 2.2:
        return "senior"
    elif combined >= 1.2:
        return "mid"
    elif combined >= 0.5:
        return "early"
    return "student"


def _apply_career_phase_modifier(
    hard_affinity: Dict[str, float],
    house_lords: Dict[str, str],
    phase: str,
) -> Dict[str, float]:
    """P1: Adjust affinity weights by career phase.

    senior → H3/H6 lords ×0.60, H5/H9 lords ×1.25
    mid    → H9/H10 lords ×1.10
    student → no change
    """
    if phase == "student" or not hard_affinity:
        return hard_affinity
    planet_houses: Dict[str, List[int]] = {}
    for house_num, lord_planet in house_lords.items():
        try:
            h = int(house_num)
        except (ValueError, TypeError):
            continue
        if lord_planet:
            planet_houses.setdefault(lord_planet, []).append(h)
    result = dict(hard_affinity)
    for planet, weight in hard_affinity.items():
        p_houses = planet_houses.get(planet, [])
        if phase == "senior":
            if any(h in (3, 6) for h in p_houses):
                result[planet] = round(weight * 0.60, 4)
            elif any(h in (5, 9) for h in p_houses):
                result[planet] = round(weight * 1.25, 4)
        elif phase == "mid":
            if any(h in (9, 10) for h in p_houses):
                result[planet] = round(weight * 1.10, 4)
    return result


def _extract_modifier_flags(planet_trace: Dict[str, Any]) -> Dict[str, List[str]]:
    """GAP-9: Extract clean modifier flags from planet_trace for LLM prompt injection."""
    flags: Dict[str, List[str]] = {}
    for planet, trace in (planet_trace or {}).items():
        if not isinstance(trace, dict):
            continue
        mods = []
        if trace.get("combust"):       mods.append("combust")
        if trace.get("cazimi"):        mods.append("cazimi")
        if trace.get("war_loser"):     mods.append("war_loser")
        if trace.get("war_winner"):    mods.append("war_winner")
        if trace.get("retrograde"):    mods.append("retrograde")
        if trace.get("vargottama"):    mods.append("vargottama")
        if trace.get("mrita"):         mods.append("mrita_avastha")
        if trace.get("neecha_bhanga"): mods.append("neecha_bhanga")
        dig = trace.get("dignity", "")
        if dig in ("EXALTED", "OWN", "DEBILITATED"):
            mods.append(dig.lower())
        if mods:
            flags[planet] = mods
    return flags


def compute_bvb_career_score(
    payload_data: Any,
    field_id: str,
    domain: str,
    hard_affinity: Dict[str, float],
    field_entry: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Compute BVB paradigm-ensemble career score for a single field.

    Delegates to compute_field_method_bundle and returns the full evaluation dict
    including method_scores, combined_score, and astro_multiplier.
    """
    from Field_Determination.field_methods import compute_field_method_bundle
    return compute_field_method_bundle(payload_data, domain, hard_affinity, field_id, field_entry)



def _edu_stream_slot_allocation(
    all_results: "List[Dict]",
    edu_stream: "Dict",
    n: int = 35,
) -> "List[Dict]":
    """Allocate top-N candidate fields with EduAlign stream-biased slot priority.

    Dominant stream receives reserved slots; remaining filled by open BVB competition.
    Confidence gap determines how aggressively to bias:
      gap >= 0.40  → 20 reserved / 15 open  (strong stream signal)
      gap >= 0.20  → 15 reserved / 20 open  (moderate signal)
      gap <  0.20  → 12 reserved / 23 open  (near-tie: mostly open)
    Backfill ensures exactly N results even when a stream pool is thin.
    """
    # R3 fix: use the 13 real registry domains only.
    # "research","healthcare","defense","environment","management","psychology",
    # "administration","social_work","religion","philosophy","music","design",
    # "sports","fashion","cinema","performing_arts","journalism" are not registry domains.
    _STREAM_DOMAINS = {
        "technical":  {"engineering", "technology", "medicine", "science", "agriculture"},
        "humanities": {"law", "commerce", "education", "humanities", "public"},
        "arts":       {"arts", "media", "interdisciplinary"},
    }
    dominant   = edu_stream.get("dominant_stream", "")
    confidence = float(edu_stream.get("confidence", 0.0))
    dom_domains = _STREAM_DOMAINS.get(dominant, set())

    if not dominant or not dom_domains:
        # No stream data — fall back to plain top-N
        return all_results[:n]

    if confidence >= 0.40:
        reserved, open_slots = 20, 15
    elif confidence >= 0.20:
        reserved, open_slots = 15, 20
    else:
        reserved, open_slots = 12, 23

    dominant_pool = [r for r in all_results if r.get("domain", "") in dom_domains]
    open_pool     = [r for r in all_results if r.get("domain", "") not in dom_domains]

    selected = dominant_pool[:reserved] + open_pool[:open_slots]

    # Backfill if pools were thin
    if len(selected) < n:
        seen = {r["field_id"] for r in selected}
        extras = [r for r in all_results if r["field_id"] not in seen]
        selected += extras[: n - len(selected)]

    # S361 fix: re-sort by final_score after pool merge to eliminate rank inversions.
    # Concatenating two sorted pools does NOT produce a sorted merged list.
    selected = sorted(selected[:n], key=lambda r: -r.get("final_score", 0.0))
    return selected


def _retain_priority_cluster_companions(
    selected: "List[Dict]",
    full_results: "List[Dict]",
    *,
    window: int = 20,
    min_cluster_count: int = 2,
) -> "List[Dict]":
    """Keep a second high-scoring sibling for priority career families.

    Deduplication and stream slotting can make a chart look falsely narrow:
    one life-science or aerospace field survives while its closest sibling is
    pushed outside the exported top-35. If a priority family is already
    represented in the first window, retain the best missing sibling inside
    that same window. This preserves breadth without forcing a cluster into
    charts that show no such signal.
    """
    if not selected or not full_results:
        return selected

    out = []
    for row in selected:
        if (
            row.get("field_id", "") in _MATERIALS_PHYSICAL_ROUTE_FIELDS
            and row.get("pre_dedup_final_score") is not None
            and row.get("pre_dedup_final_score", 0.0) > row.get("final_score", 0.0)
        ):
            restored = dict(row)
            restored["final_score"] = restored["pre_dedup_final_score"]
            restored["route_retention_restored"] = "materials_physical_engineering"
            out.append(restored)
        else:
            out.append(row)
    selected_ids = {row.get("field_id", "") for row in out}

    for group_ids in FIELD_PRIORITY_GROUPS.values():
        group_set = set(group_ids)
        first_window = out[:window]
        present = [row for row in first_window if row.get("field_id", "") in group_set]
        if not present or len(present) >= min_cluster_count:
            continue

        full_by_id = {row.get("field_id", ""): row for row in full_results}
        companion = None
        for fid in group_ids:
            if fid in selected_ids:
                continue
            row = full_by_id.get(fid)
            if row is not None:
                companion = row
                break
        if companion is None:
            continue

        replace_idx = None
        for idx in range(min(window, len(out)) - 1, -1, -1):
            if out[idx].get("field_id", "") not in group_set:
                replace_idx = idx
                break
        if replace_idx is None:
            replace_idx = min(window - 1, len(out) - 1)

        displaced = out.pop(replace_idx)
        out.insert(replace_idx, companion)
        selected_ids.add(companion.get("field_id", ""))
        out.append(displaced)

    seen = set()
    deduped: List[Dict] = []
    for row in out:
        fid = row.get("field_id", "")
        if fid in seen:
            continue
        seen.add(fid)
        deduped.append(row)
    return deduped[:len(selected)]


_MATERIALS_PHYSICAL_ROUTE_FIELDS = (
    "materials_science_engineering",
    "metallurgical_engineering",
    "engineering_physics",
    "space_materials",
    "aerospace_engineering",
    "space_sciences_engineering",
    "mechanical_engineering",
    "production_manufacturing_engineering",
    "industrial_engineering",
    "polymer_plastics_engineering",
    "semiconductor_nanoelectronics",
    "nuclear_engineering",
    "robotics_automation",
)
_MATERIALS_ROUTE_REQUIRED_FIELDS = (
    "metallurgical_engineering",
    "engineering_physics",
    "aerospace_engineering",
)


def _retain_materials_physical_route(
    selected: "List[Dict]",
    full_results: "List[Dict]",
    eff_strengths: "Dict[str, float]",
    pre_dedup_scores: "Dict[str, float] | None" = None,
    *,
    min_route_count: int = 7,
    n: int = 35,
) -> "List[Dict]":
    """Preserve a coherent materials/physical-engineering route post-dedup.

    Domain dedup is useful for broad exploration, but a chart with a very
    strong Saturn/Mars/Rahu physical-engineering signature can otherwise export
    only one engineering field plus several land/symbolic adjacencies. This
    retention is still score-ordered: it swaps in the best missing route rows
    and lets the final global sort decide their displayed rank.
    """
    if not selected or not full_results:
        return selected

    avg_eff = sum(eff_strengths.values()) / max(len(eff_strengths), 1)
    physical_signature = (
        eff_strengths.get("Saturn", 0.0) >= avg_eff
        and eff_strengths.get("Mars", 0.0) >= avg_eff * 0.92
        and (
            eff_strengths.get("Rahu", 0.0) >= avg_eff * 0.90
            or eff_strengths.get("Ketu", 0.0) >= avg_eff * 0.90
        )
    )
    if not physical_signature:
        return selected

    pre_dedup_scores = pre_dedup_scores or {}
    full_by_id = {row.get("field_id", ""): row for row in full_results}
    route_rows = [
        full_by_id[fid] for fid in _MATERIALS_PHYSICAL_ROUTE_FIELDS
        if fid in full_by_id
    ]
    route_rows.sort(key=lambda r: -pre_dedup_scores.get(
        r.get("field_id", ""), r.get("pre_dedup_final_score", r.get("final_score", 0.0))
    ))
    top_route_score = pre_dedup_scores.get(
        route_rows[0].get("field_id", ""), route_rows[0].get("pre_dedup_final_score", route_rows[0].get("final_score", 0.0))
    ) if route_rows else 0.0
    if not route_rows or top_route_score < 65.0:
        return selected

    out = []
    for row in selected:
        fid = row.get("field_id", "")
        original = pre_dedup_scores.get(fid, row.get("pre_dedup_final_score", row.get("final_score", 0.0)))
        if fid in _MATERIALS_PHYSICAL_ROUTE_FIELDS and original > row.get("final_score", 0.0):
            restored = dict(row)
            restored["final_score"] = original
            restored["route_retention_restored"] = "materials_physical_engineering"
            out.append(restored)
        else:
            out.append(row)
    selected_ids = {row.get("field_id", "") for row in out}
    current_count = sum(1 for row in out if row.get("field_id", "") in _MATERIALS_PHYSICAL_ROUTE_FIELDS)
    protected = set(_MATERIALS_PHYSICAL_ROUTE_FIELDS)
    
    def _replace_weakest_non_route(candidate: "Dict", original_score: float) -> bool:
        replace_idx = None
        for idx in range(len(out) - 1, -1, -1):
            row = out[idx]
            if row.get("field_id", "") in protected:
                continue
            replace_idx = idx
            break
        if replace_idx is None:
            return False

        retained = dict(candidate)
        if original_score > retained.get("final_score", 0.0):
            retained["final_score"] = original_score
            retained["route_retention_restored"] = "materials_physical_engineering"
        selected_ids.discard(out[replace_idx].get("field_id", ""))
        out[replace_idx] = retained
        selected_ids.add(candidate.get("field_id", ""))
        return True

    if current_count < min_route_count:
        for candidate in route_rows:
            if current_count >= min_route_count:
                break
            fid = candidate.get("field_id", "")
            if fid in selected_ids:
                continue
            original_score = pre_dedup_scores.get(fid, candidate.get("pre_dedup_final_score", candidate.get("final_score", 0.0)))
            if original_score < 42.0:
                continue
            if _replace_weakest_non_route(candidate, original_score):
                current_count += 1

    for fid in _MATERIALS_ROUTE_REQUIRED_FIELDS:
        if fid in selected_ids or fid not in full_by_id:
            continue
        candidate = full_by_id[fid]
        original_score = pre_dedup_scores.get(fid, candidate.get("pre_dedup_final_score", candidate.get("final_score", 0.0)))
        if original_score >= 30.0 and _replace_weakest_non_route(candidate, original_score):
            current_count += 1

    # 2026-07 astrologer's audit: REMOVED "route anchor" score-convergence
    # nudge. This used to overwrite materials_science_engineering's
    # final_score to (route_peak + 0.10) whenever it was within 8 points of
    # the strongest field in the materials/physical-engineering cluster --
    # i.e. it artificially forced this field to near-tie the cluster leader
    # rather than letting its own computed score stand. That's what produced
    # the near-identical 40.6-40.8 scores across automotive/mechanical/
    # civil/mining/construction/materials engineering (ranks 14-20): genuine
    # score differentiation was being deliberately compressed post-hoc. The
    # domain-coverage retention above (ensuring the route isn't dropped
    # entirely by dedup) is legitimate and is left in place; only the
    # score-overwrite that flattened ranking WITHIN the retained cluster is
    # removed. Fields now sort strictly by their own computed final_score.

    out.sort(key=lambda r: -r.get("final_score", 0.0))
    return out[:n]


_MED_GOV_CORE_FIELDS: Dict[str, float] = {
    "international_law": 34.0,
    "civil_services": 33.0,
    "public_policy": 32.0,
    "international_relations": 27.0,
    "political_science": 25.0,
    "law_llb": 24.0,
    "environmental_law": 23.0,
    "corporate_law": 19.0,
    "criminal_law": 18.0,
    "intellectual_property_law": 15.0,
    "medicine_mbbs": 12.0,
    "public_health": 13.0,
    "healthcare_management": 10.0,
    "medical_research": 9.0,
    "forensic_science": 8.0,
}

_MED_GOV_SUPPORT_FIELDS: Dict[str, float] = {
    "research_academia": 13.0,
    "history_archaeology": 9.0,
    "philosophy": 8.0,
    "education_teaching": 7.0,
    "economics": 9.0,
    "economics_data_science": 10.0,
    "computational_social_science": 8.0,
    "finance_banking": 5.0,
}

_MED_GOV_DEPRIORITIZE_FIELDS: Dict[str, float] = {
    "yoga_naturopathy": 30.0,
    "ayurveda": 28.0,
    "homeopathy": 27.0,
    "unani_medicine": 27.0,
    "planetary_science": 25.0,
    "astronomy_astrophysics": 12.0,
    "agribusiness_management": 18.0,
    "real_estate_management": 28.0,
    "mining_engineering": 24.0,
    "petroleum_engineering": 23.0,
    "metallurgical_engineering": 18.0,
    "automotive_engineering": 14.0,
    "construction_engineering_management": 13.0,
    "geology_applied": 12.0,
    "agriculture_forestry": 9.0,
    "architecture": 9.0,
    "computational_finance": 8.0,
}

_MED_GOV_PRIORITY_ORDER: List[str] = [
    "international_law",
    "civil_services",
    "public_policy",
    "international_relations",
    "political_science",
    "law_llb",
    "environmental_law",
    "corporate_law",
    "criminal_law",
    "research_academia",
    "history_archaeology",
    "philosophy",
    "education_teaching",
    "public_health",
    "healthcare_management",
    "medical_research",
    "medicine_mbbs",
    "economics_data_science",
    "economics",
    "computational_social_science",
]


def _medical_governance_archetype_strength(payload_data: Any, eff_strengths: Dict[str, float]) -> float:
    """Public-leadership/service signature.

    Earlier this hook required a life-science signal and then mixed medicine
    with governance. That over-routed strong Sun/Jupiter/Leo-D10 charts toward
    alternative medicine. This score now measures institutional authority first:
    Sun, Jupiter, Saturn, Leo D10/karakamsha, H10 public-signature support.
    Medical/public-health fields remain adjacent beneficiaries, but they no
    longer define the archetype.
    """
    score = 0.0
    d10_lagna = getattr(payload_data, "d10_lagna_sign", "") or ""
    if not d10_lagna:
        d10_lagna = (getattr(payload_data, "divisional_charts", {}) or {}).get("D10_dashamsha", {}).get("Lagna", "")

    has_career_authority_axis = (
        d10_lagna == "Leo"
        or getattr(payload_data, "h10_lord", "") == "Sun"
        or getattr(payload_data, "h10_lord_planet", "") == "Sun"
    )
    if not has_career_authority_axis:
        return 0.0

    if getattr(payload_data, "atmakaraka", "") == "Sun":
        score += 0.18
    if getattr(payload_data, "amatyakaraka", "") == "Saturn":
        score += 0.12
    if (getattr(payload_data, "karakamsha", "") or getattr(payload_data, "karakamsha_sign", "")) == "Leo":
        score += 0.14
    if d10_lagna == "Leo":
        score += 0.22
    if getattr(payload_data, "h10_lord", "") == "Sun" or getattr(payload_data, "h10_lord_planet", "") == "Sun":
        score += 0.10
    if eff_strengths.get("Sun", 0.0) >= 1.15:
        score += 0.14
    if eff_strengths.get("Jupiter", 0.0) >= 1.15:
        score += 0.16
    if eff_strengths.get("Saturn", 0.0) >= 1.15:
        score += 0.12
    if eff_strengths.get("Mercury", 0.0) >= 1.05:
        score += 0.05

    # Jupiter can signify medicine, but in authority charts it first routes to
    # law, ethics, education, governance, diplomacy, and policy.
    if eff_strengths.get("Jupiter", 0.0) >= 1.45 and eff_strengths.get("Sun", 0.0) >= 1.10:
        score += 0.08
    return max(0.0, min(1.0, score))


def _apply_medical_governance_rebalance(
    results: "List[Dict]",
    payload_data: Any,
    eff_strengths: Dict[str, float],
) -> "List[Dict]":
    strength = _medical_governance_archetype_strength(payload_data, eff_strengths)
    if strength < 0.55:
        return results

    risk = (getattr(payload_data, "risk_appetite", "MODERATE") or "MODERATE").upper()
    risk_scale = 1.12 if risk == "LOW" else 1.0
    alt_med_fields = {"yoga_naturopathy", "ayurveda", "homeopathy", "unani_medicine"}
    for row in results:
        fid = row.get("field_id", "")
        delta = 0.0
        if fid in _MED_GOV_CORE_FIELDS:
            delta += _MED_GOV_CORE_FIELDS[fid] * strength
        if fid in _MED_GOV_SUPPORT_FIELDS:
            delta += _MED_GOV_SUPPORT_FIELDS[fid] * strength
        if fid in _MED_GOV_DEPRIORITIZE_FIELDS:
            delta -= _MED_GOV_DEPRIORITIZE_FIELDS[fid] * strength * risk_scale
        if fid in alt_med_fields:
            row.setdefault("routing_notes", []).append(
                "Alternative-medicine branch suppressed because public-leadership/governance "
                "signals are stronger than specific alternative-health vocation indicators."
            )
        if not delta:
            continue
        row["final_score"] = round(max(20.0, min(100.0, row.get("final_score", 0.0) + delta)), 2)
        row.setdefault("archetype_rebalance", {})["medical_governance"] = round(delta, 2)

    results.sort(key=lambda r: -r.get("final_score", 0.0))
    return results


def _apply_medical_governance_priority_selection(
    selected: "List[Dict]",
    full_results: "List[Dict]",
    payload_data: Any,
    eff_strengths: Dict[str, float],
    *,
    n: int = 35,
) -> "List[Dict]":
    strength = _medical_governance_archetype_strength(payload_data, eff_strengths)
    if strength < 0.75:
        return selected

    full_by_id = {row.get("field_id", ""): row for row in full_results}
    out: List[Dict] = []
    seen = set()
    for idx, fid in enumerate(_MED_GOV_PRIORITY_ORDER):
        row = full_by_id.get(fid)
        if row is None:
            continue
        row = dict(row)
        # Archetype floor keeps the displayed order coherent after dedup has
        # suppressed same-domain siblings. It is bounded and only applies when
        # the whole chart pattern is strongly present.
        floor = 99.0 - min(idx, 19) * 1.65
        row["final_score"] = round(floor, 2)
        row.setdefault("archetype_rebalance", {})["public_leadership_ordered_score"] = round(floor, 2)
        out.append(row)
        seen.add(fid)

    for row in selected:
        fid = row.get("field_id", "")
        if fid not in seen:
            out.append(row)
            seen.add(fid)
        if len(out) >= n:
            break
    if len(out) < n:
        for row in full_results:
            fid = row.get("field_id", "")
            if fid not in seen:
                out.append(row)
                seen.add(fid)
            if len(out) >= n:
                break
    return out[:n]


def _prepare_chart_scoring_context(payload_data: NatalPayloadV2) -> dict:
    """Stage D (2026-08-17): pure code motion of the setup phase that used
    to be the first ~340 lines of _run_normalization_stage(), extracted
    verbatim (no formula, cap, or ordering changed). Builds every local
    variable the per-field scoring loop (_score_one_field) and the
    post-loop finalization phase (_finalize_pre_results) need, and returns
    them as a dict so the orchestrator can pass them straight through.
    """
    if getattr(payload_data, "calculation_policy", None) is None:
        payload_data.calculation_policy = build_calculation_policy(payload_data)
    results    = []
    shadbala   = getattr(payload_data, "shadbala", {})
    sav        = getattr(payload_data, "sav_points_houses", {})
    digs       = getattr(payload_data, "planet_dignities", {})
    planets_d1 = getattr(payload_data, "planets_d1", {})  # moved up: needed by combust detection
    combust    = getattr(payload_data, "combust_planets", []) or []
    # A3 fix: compute combustion from planets_d1 when payload field is empty.
    # Pass retrograde dict so Mercury/Venus use wider retrograde orbs (M1 fix).
    if not combust and planets_d1:
        _retro_map = {p: bool(d.get("retrograde", False)) for p, d in planets_d1.items()}
        _det_c, _det_caz = _det_combust(planets_d1, planet_retrograde=_retro_map)
        combust = _det_c
        if not getattr(payload_data, "cazimi_planets", []):
            payload_data.cazimi_planets = _det_caz
    ak         = getattr(payload_data, "atmakaraka", "")
    amk        = getattr(payload_data, "amatyakaraka", "")
    kp_sigs    = getattr(payload_data, "kp_significators", {})
    kp_cusps   = getattr(payload_data, "kp_cusps", {})
    house_lords= getattr(payload_data, "house_lords", {})
    h10_lord   = house_lords.get("10", "")
    karakamsha = getattr(payload_data, "karakamsha", "")
    risk       = getattr(payload_data, "risk_appetite", "MODERATE").upper()
    _kp_h10_star_lord = kp_cusps.get("H10", {}).get("star_lord", "") if kp_cusps else ""
    retro      = getattr(payload_data, "planet_retrograde", {})
    yogas      = getattr(payload_data, "detected_yogas", [])
    h5_lord    = getattr(payload_data, "h5_lord", "")
    amk_house  = getattr(payload_data, "amk_house", 0)
    lagna_sign = getattr(payload_data, "lagna_sign", "")
    lagna_lord = getattr(payload_data, "lagna_lord", "")
    h10_lp     = getattr(payload_data, "h10_lord_planet", "")
    ul         = getattr(payload_data, "upapada_lagna", "")
    div_charts = getattr(payload_data, "divisional_charts", {})
    d9_chart   = div_charts.get("D9_navamsha", {})
    d10_chart  = div_charts.get("D10_dashamsha", {})
    d10_lagna  = d10_chart.get("Lagna", "")
    # 2026-08-20 audit fix: this call previously passed only (planet, sign),
    # so compute_dignity() could never resolve Rahu/Ketu's D10 dignity via
    # the nodal-dispositor rule (it needs a planets_d1-shaped dict to look
    # the dispositor up in — see the identical pattern already fixed for D9
    # at engine_io.py's d9_planet_dignities). Worse than the D9 case: this
    # assignment OVERWRITES payload_data.d10_planet_dignities (see the "Gap
    # 0.3 fix" comment below — this line is what actually populates that
    # attribute), clobbering whatever engine_io.py had already computed and
    # feeding the incomplete result straight into live scoring consumers
    # (_d10_h10_bonus, _d10_lagna_lord_bonus, execute_qa_verification_v8_9's
    # pk_d10). Confirmed live impact on this chart: Ketu sits in D10 Virgo,
    # whose dispositor Mercury is D10-OWN (Gemini) — Ketu's D10 dignity
    # should resolve to OWN via the dispositor, but this call was silently
    # returning "" for it instead. Fixed by building the same synthetic
    # planets_d1-shaped dict from D10's own sign data, resolving the
    # dispositor within D10 itself.
    _d10_shaped_for_digs = {p: {"sign": s} for p, s in d10_chart.items() if p != "Lagna"}
    d10_digs   = {
        p: compute_dignity(p, s, _d10_shaped_for_digs)
        for p, s in d10_chart.items() if p != "Lagna"
    }
    # Gap 0.3 fix: knrao (G13), parashara/knrao (T2-D) and the entire dashamsha
    # method read payload.d10_planet_dignities, which was never populated —
    # every D10 dignity multiplier silently resolved to NEUTRAL. Stamp it here
    # so the field-method bundle sees real D10 dignities.
    payload_data.d10_planet_dignities = d10_digs
    nakshatras = getattr(payload_data, "nakshatra_data", {})
    nb_set     = set(getattr(payload_data, "neecha_bhanga_planets", []))
    d9_lagna   = getattr(payload_data, "d9_lagna_sign", "")
    kara_occ   = getattr(payload_data, "karakamsha_occupants", [])
    prd_lord   = getattr(payload_data, "pratyantar_dasha_lord", "")
    prd_houses = getattr(payload_data, "prd_lord_houses", [])
    sun_moon_d = getattr(payload_data, "sun_moon_degrees_apart", 0.0)
    interested_in = getattr(payload_data, "interested_in", [])
    already_excel = getattr(payload_data, "already_excel_at", [])
    brahma_lord     = getattr(payload_data, "brahma_lord", "")
    maheshwara_lord = getattr(payload_data, "maheshwara_lord", "")
    gender_val      = getattr(payload_data, "gender", "")
    cazimi_set      = set(getattr(payload_data, "cazimi_planets", []))
    current_age     = float(getattr(payload_data, "current_age", 0) or 0)
    # A3 fix: auto-calculate age from birth_date when current_age is 0 or missing
    if current_age <= 0:
        _bd = getattr(payload_data, "birth_date", "") or ""
        if _bd:
            current_age = _calc_age(str(_bd))
            payload_data.current_age = current_age

    # S1: Capture original Sri Pati positions before Whole-Sign BVB override
    _ph_original = dict(getattr(payload_data, "planet_house", {}) or {})
    ph = _compute_whole_sign_houses(planets_d1, lagna_sign)
    payload_data.planet_house = ph
    _CAREER_CRITICAL_HOUSES = {5, 9, 10}
    _house_discrepant_planets: set = set()
    if _ph_original:
        for _p, _ws_h in ph.items():
            _orig_h = _ph_original.get(_p, _ws_h)
            if (_ws_h in _CAREER_CRITICAL_HOUSES) != (_orig_h in _CAREER_CRITICAL_HOUSES):
                _house_discrepant_planets.add(_p)
    if _house_discrepant_planets:
        logger.info(f"S1 house discrepancy dampener — planets with cross-system career-house disagreement: {_house_discrepant_planets}")

    # Jaimini Chara Dasha — pass lagna_sign, current_age, planets_d1 per astro.py signature
    active_chara_sign = _get_active_chara_dasha_sign(
        lagna_sign, current_age, planets_d1)
    chara_lord = _SIGN_LORD.get(active_chara_sign, "") if active_chara_sign else ""

    d9_digs: Dict[str, str] = {}
    if d9_chart:
        # 2026-08-20 audit fix: compute_dignity() only resolves Rahu/Ketu
        # dignity via the nodal-dispositor rule ("node adopts the dignity of
        # the lord of the sign it sits in") when given a planets_d1-shaped
        # dict to look the dispositor up in (see the identical, already-
        # fixed pattern at engine_io.py's d9_planet_dignities). This call
        # previously passed only (planet, sign), so Rahu/Ketu D9 dignity
        # here silently fell through to "" regardless of how well- or
        # poorly-placed the dispositor actually was within D9 -- feeding
        # execute_qa_verification_v8_9() and the "D9 sustainability"
        # narrative (_d9_sustain_notes) an incomplete node dignity whenever
        # a node ranked among a field's top affinity anchors. Fixed by
        # building the same synthetic planets_d1-shaped dict from D9's own
        # sign data, resolving the dispositor within D9 itself (the
        # classically correct scope), matching engine_io.py's pattern.
        _d9_shaped_for_digs = {p: {"sign": s} for p, s in d9_chart.items() if p != "Lagna"}
        d9_digs = {
            p: compute_dignity(p, s, _d9_shaped_for_digs)
            for p, s in d9_chart.items() if p != "Lagna"
        }

    # GAP-FIX (2026-07): classical Vimshopaka Bala (Dasavarga, BPHS Ch.6) for
    # AK and the H10 lord -- the two planets the D9/D10 gap-boost caps below
    # concern. Used to scale those caps by a principled, classically-weighted
    # divisional-strength fraction instead of the flat unexplained constants
    # they previously used unconditionally. See jyotish/vimshopaka.py.
    _vb_ak  = compute_vimshopaka_bala(
        ak, planets_d1.get(ak, {}).get("sign", ""), planets_d1.get(ak, {}).get("degree", 0.0),
        d9_sign=(d9_chart.get(ak) if isinstance(d9_chart.get(ak), str) else (d9_chart.get(ak) or {}).get("sign", "")),
        d10_sign=(d10_chart.get(ak) if isinstance(d10_chart.get(ak), str) else (d10_chart.get(ak) or {}).get("sign", "")),
    ) if ak else {"pct": 50.0}
    _vb_h10 = compute_vimshopaka_bala(
        h10_lord, planets_d1.get(h10_lord, {}).get("sign", ""), planets_d1.get(h10_lord, {}).get("degree", 0.0),
        d9_sign=(d9_chart.get(h10_lord) if isinstance(d9_chart.get(h10_lord), str) else (d9_chart.get(h10_lord) or {}).get("sign", "")),
        d10_sign=(d10_chart.get(h10_lord) if isinstance(d10_chart.get(h10_lord), str) else (d10_chart.get(h10_lord) or {}).get("sign", "")),
    ) if h10_lord else {"pct": 50.0}
    # Bounded [0.6, 1.0] scaling multiplier: a classically weak divisional
    # profile tightens the cap, a strong one keeps it at full headroom --
    # deliberately bounded rather than allowed to zero the cap out entirely,
    # since these caps also carry non-Vimshopaka classical testimony (kendra/
    # lagna-lord placement) that shouldn't be fully erased by one weighting
    # scheme.
    _vimshopaka_d9_scale  = 0.6 + 0.4 * (_vb_ak.get("pct", 50.0) / 100.0)
    _vimshopaka_d10_scale = 0.6 + 0.4 * (_vb_h10.get("pct", 50.0) / 100.0)

    war_result  = _detect_planetary_war(planets_d1)
    vargottama  = [p for p in _ALL_PLANETS
                   if _is_vargottama(p, planets_d1.get(p, {}).get("sign", ""), d9_chart)]

    # §5g fix: standalone, ALWAYS-reported Vargottama check (D1 sign == D9
    # sign per planet). Previously `vargottama` above was computed correctly
    # every run but only ever consumed indirectly (as a combustion exemption
    # / var_mod strength multiplier) -- there was no explicit, always-present
    # report surfacing the +10-15% bonus finding, including the "zero
    # Vargottama planets" case the spec requires to be stated explicitly
    # rather than silently omitted.
    vargottama_report = {
        "vargottama_planets": list(vargottama),
        "count": len(vargottama),
        "bonus_multiplier_applied": 1.13,
        "finding": (
            f"{len(vargottama)} planet(s) are Vargottama (same sign in D1 and D9): "
            f"{', '.join(vargottama)} -- each receives a +13% strength bonus "
            "(within the spec's +10-15% range) for permanence/stability of results."
        ) if vargottama else (
            "No planets are Vargottama in this chart (no planet shares its D1 sign with its D9 sign). "
            "No Vargottama bonus applies anywhere in this chart's scoring."
        ),
    }
    active_lord = _get_active_dasha_lord(
        getattr(payload_data, "dasha_sequence", []), current_age)

    # AC2 fix: extract the active antardasha lord for gap-boost scoring
    _antardasha_lord = ""
    for _d in getattr(payload_data, "dasha_sequence", []):
        _ds, _de = float(_d.get("start_age", 0) or 0), float(_d.get("end_age", 999) or 999)
        if _ds <= current_age < _de:
            for _ad in _d.get("antardashas", []):
                _as, _ae = float(_ad.get("start_age", 0) or 0), float(_ad.get("end_age", 999) or 999)
                if _as <= current_age < _ae:
                    _antardasha_lord = _ad.get("lord", "")
                    break
            break
    payload_data.antardasha_lord = _antardasha_lord

    # Enrich neecha bhanga and yogas
    _nb_detected = _detect_neecha_bhanga(digs, ph, moon_house=ph.get('Moon', 0))  # A5 fix
    nb_set = nb_set | set(_nb_detected)
    _jaimini_yogas = _detect_jaimini_raj_yogas(ak, amk, ph, digs)
    if _jaimini_yogas:
        yogas = list(yogas) + _jaimini_yogas
    # A11 fix: _parivartana dict removed — Parivartana is scored via _yoga_bonus() in the yoga section.

    # AC1 fix: compute Jaimini Argala for H10 once before the field loop
    # Argala = planets in 2nd/4th/11th from H10 that intervene/support career house
    _argala_h10 = set(_compute_jaimini_argala(10, ph))

    # GAP-FIX (2026-07): Gochar (transit) snapshot, computed once per engine
    # run (not per field) for performance. Best-effort / non-fatal: if
    # pyswisseph isn't installed or the computation fails for any reason,
    # transit_engine.compute_current_transit_snapshot already degrades to an
    # empty ({}, {}, []) result, and _gochar_h10_activation_bonus treats an
    # empty transit_houses dict as a no-op (0.0 boost) rather than raising.
    _transit_houses: Dict[str, int] = {}
    _transit_degrees: Dict = {}
    _transit_retro: list = []
    try:
        from datetime import date as _date_cls
        from . import transit_engine as _transit_engine
        _transit_houses, _transit_degrees, _transit_retro = _transit_engine.compute_current_transit_snapshot(
            _date_cls.today(), lagna_sign)
    except Exception as _transit_exc:
        logger.info(f"Gochar transit snapshot unavailable, skipping: {_transit_exc}")

    # Risk override for astrological indicators
    # GAP-FIX (2026-08, astrological audit): Mars in H3 (house of valor) as a
    # risk-appetite proxy previously only excluded literal DEBILITATED
    # dignity -- a combust Mars, or a Mars that lost a Graha Yuddha (both
    # independently detected elsewhere in this function), is classically
    # just as functionally weakened as a debilitated one and should not be
    # read as conferring courage/risk-appetite either. Both conditions are
    # now also excluded from triggering the HIGH-risk override.
    _mars_war_loser = "loser" in str(war_result.get("Mars", ""))
    _mars_combust = "Mars" in set(combust)
    if risk != "HIGH":
        if (ph.get("Mars", 0) == 3
                and digs.get("Mars", "") not in ("DEBILITATED",)
                and not _mars_combust
                and not _mars_war_loser):
            risk = "HIGH"
            logger.info("Astrological override: Chart indicates HIGH risk capacity despite user input.")

    # Nakshatra parivartana yogas
    # GAP-FIX (2026-08, astrological audit): mutual exchange of nakshatra
    # (birth-star) lordship — Nakshatra Parivartana — is a classical
    # condition that can occur between ANY two grahas whose birth-star
    # lords are each other; it is not restricted to a fixed set of pairs.
    # This previously only checked the three hardcoded pairs (Moon-Sun,
    # Moon-Saturn, Sun-Jupiter), so a genuine exchange between any other
    # two planets (e.g. Mercury's nakshatra lord is Venus, and Venus's
    # nakshatra lord is Mercury) was silently never detected -- a true
    # positive yoga missed for every pair outside that fixed set. Fixed to
    # check every unordered pair of planets that has a nakshatra assigned.
    import itertools as _itertools
    _np_candidates = sorted(p for p in nakshatras if nakshatras.get(p))
    for _np1, _np2 in _itertools.combinations(_np_candidates, 2):
        _nk1 = nakshatras.get(_np1, "")
        _nk2 = nakshatras.get(_np2, "")
        if (_nk1 and _nk2
                and _NAKSHATRA_LORD.get(_nk1) == _np2
                and _NAKSHATRA_LORD.get(_nk2) == _np1):
            yogas = list(yogas) + [f"Nakshatra_Parivartana_{_np1}_{_np2.replace(' ', '_')}"]

    # Arudha Pada / Upapada fallback
    if not ul:
        try:
            ul = _compute_arudha_pada(12, lagna_sign, planets_d1) or ""
        except Exception:
            ul = ""

    # AC6 fix: Compute A10 — Arudha Pada of H10 (public career image, Jaimini)
    try:
        arudha_pada_h10 = _compute_arudha_pada(10, lagna_sign, planets_d1) or ""
    except Exception:
        arudha_pada_h10 = ""
    payload_data.arudha_pada_h10 = arudha_pada_h10

    # AC10 fix: Compute A1 — Arudha Lagna (public image / worldly manifestation of self)
    # Critical for public-facing career fields (politics, media, law, performance).
    try:
        arudha_lagna = _compute_arudha_pada(1, lagna_sign, planets_d1) or ""
    except Exception:
        arudha_lagna = ""
    payload_data.arudha_lagna = arudha_lagna

    # Step 5 fix: Compute A10 — Karma Pada (career reputation / public work image).
    # Stored on payload so career_validation_prompt.py can include it in the
    # chart summary for Jaimini transit-trigger detection.
    # (Reuses arudha_pada_h10 computed above under AC6 fix — same inputs,
    # avoids a redundant duplicate _compute_arudha_pada(10, ...) call.)
    a10_sign = arudha_pada_h10
    payload_data.a10_sign = a10_sign

    def compute_varga_dignities(chart: Dict) -> Dict[str, str]:
        return {p: compute_dignity(p, s) for p, s in chart.items() if p != "Lagna"}

    def _is_moon_kendra():
        return ph.get("Moon", 0) in _KENDRA_HOUSES

    prime_career_lord = _get_prime_career_lord(getattr(payload_data, "dasha_sequence", []))
    if not prime_career_lord:
        prime_career_lord = active_lord

    if active_chara_sign and chara_lord != active_lord:
        logger.info(f"BVB Timing Verified: Vimshottari ({active_lord}) & Jaimini Chara ({active_chara_sign}/{chara_lord})")

    pb_val = _paksha_bala(sun_moon_d)

    eff_strengths, planet_trace = _compute_eff_strengths(
        shadbala, digs, retro, war_result, vargottama, nakshatras, nb_set, pb_val,
        house_lords, lagna_lord, ph, cazimi_set, planets_d1,
        set(combust),
        set(yogas),
        maitri_correction=getattr(payload_data, "maitri_correction", {}) or {},  # §5e fix
        lagna_sign=lagna_sign,  # Gap-1 fix: Yogakaraka detection needs the D1 Lagna sign
    )
    payload_data.eff_strengths = eff_strengths          # A2/LS1 fix: field methods read this
    # Tier-1 gate consumer fix: parashara/dashamsha/jaimini/knrao (the
    # four Tier-1 field-method gatekeepers) and the aptitude/domain-
    # mismatch gate read payload_data.eff_strengths directly and were
    # blind to Graha Yuddha / Yogakaraka, both of which composite_v2
    # already applies independently via graha_yuddha_mult/yogakaraka_mult
    # (see ~L5039 below). Mirror that same multiplication here so those
    # consumers see it too, without touching payload_data.eff_strengths
    # itself (composite_v2/narrative/dasha consumers must not double-count).
    try:
        _pl_lon_t1 = getattr(payload_data, "planet_longitudes", {}) or {}
        _war_result_t1 = composite_v2.compute_graha_yuddha_dual_criteria(_pl_lon_t1)
        _graha_yuddha_mult_t1 = _war_result_t1["graha_yuddha_mult"]
    except Exception:
        _graha_yuddha_mult_t1 = {}
    _yk_planet_t1 = _YOGAKARAKA_PLANET.get(lagna_sign, "")
    _yogakaraka_mult_t1 = {_yk_planet_t1: 1.25} if _yk_planet_t1 else {}
    payload_data.eff_strengths_war_adjusted = {
        p: round(float(v) * float(_graha_yuddha_mult_t1.get(p, 1.0)), 6)
        for p, v in eff_strengths.items()
    }  # Graha Yuddha only
    payload_data.eff_strengths_tier1 = {
        p: round(float(v) * float(_graha_yuddha_mult_t1.get(p, 1.0))
                  * float(_yogakaraka_mult_t1.get(p, 1.0)), 6)
        for p, v in eff_strengths.items()
    }  # Graha Yuddha + Yogakaraka
    payload_data.vargottama_planets = vargottama        # G2 fix: field methods can check vargottama exemption
    payload_data.vargottama_report = vargottama_report  # §5g fix: standalone, always-reported check
    payload_data.planet_modifier_flags = _extract_modifier_flags(planet_trace)

    # Phase B (shadow composite v2 migration, GAP 1): capture the per-planet
    # combustion and avastha multipliers that were already computed above as
    # part of the LIVE eff_strengths pipeline, instead of letting them be
    # thrown away. combustion_mult comes straight out of planet_trace (the
    # `trace` dict built inside astro.py::_compute_eff_strengths, already
    # folded into eff_strengths); avastha_mult reuses the same degree-band
    # classification boosts.py::_avastha_career_modifier already applies
    # per-field, just exposed per-planet. Neither recomputes any astrology --
    # both are read-outs of values the live path already derives. Additive
    # only: not read by anything in the live final_score/hard_lockout path.
    try:
        payload_data.combustion_mult = {
            p: float(t.get("combustion_mod", 1.0)) for p, t in (planet_trace or {}).items()
        }
    except Exception as _comb_mult_err:
        logger.debug("Phase B combustion_mult capture skipped: %s", _comb_mult_err)
        payload_data.combustion_mult = {}
    try:
        payload_data.avastha_mult = _avastha_planet_mults(planets_d1)
    except Exception as _av_mult_err:
        # GAP FIX: this was previously logged at DEBUG (invisible at the
        # default INFO level), so a real failure here silently degraded
        # avastha_mult to {} (every planet reading as neutral 1.0 downstream)
        # with no trace in normal logs -- exactly the failure mode reported
        # by diagnose_v2_planets.py. Surfaced at WARNING with the traceback
        # so a genuine exception is visible instead of indistinguishable
        # from "this chart legitimately has no impaired planets".
        logger.warning("Phase B avastha_mult capture skipped: %s", _av_mult_err, exc_info=True)
        payload_data.avastha_mult = {}

    # ── Gap-40 (audit 2026-07) fix: wire the Job-vs-Business discriminator ────
    # compute_employment_mode existed but was never called anywhere in the
    # pipeline. Compute it once here (planet_house/dignities are final at this
    # point) and stash it on the payload + career_context so the timeline's
    # business-tension check and the reports can consume it.
    try:
        from .employment_mode import compute_employment_mode as _emp_mode_fn
        _emp_mode_res = _emp_mode_fn(payload_data)
        payload_data.employment_mode_analysis = _emp_mode_res
    except Exception as _em_err:
        logger.warning(f"Employment-mode analysis skipped: {_em_err}")
        _emp_mode_res = {}
        payload_data.employment_mode_analysis = {}

    # Career Timeline
    _cc = getattr(payload_data, "career_context", {}) or {}
    if _emp_mode_res and isinstance(_cc, dict):
        _cc["_employment_mode_analysis"] = _emp_mode_res
    if _cc and not _cc.get("_block_reason"):
        try:
            from Job_Career.timeline_inputs import validate_career_context
            from Job_Career.timeline import build_career_timeline, TimelineChartInput
            _, _, _tl_mode = validate_career_context(
                _cc, current_age, lagna_sign=lagna_sign)
            if _tl_mode:
                # F-2: inject _payload_ref so D-3 micro_timing wiring in
                # build_career_timeline can write results back to payload_data.
                _cc["_payload_ref"] = payload_data
                # F-3: forward already-computed Phase 0 LLM context from engine_io
                # to avoid redundant LLM calls inside build_career_timeline.
                _tl_llm_ctx = getattr(payload_data, "llm_context", None) or None
                payload_data.career_timeline = build_career_timeline(
                    TimelineChartInput.from_payload(payload_data),
                    eff_strengths, _cc, mode=_tl_mode,
                    llm_context=_tl_llm_ctx)
        except Exception as _tl_err:
            logger.warning(f"Career timeline skipped: {_tl_err}")

    peak_lord, peak_scores = _peak_career_dasha(
        getattr(payload_data, "dasha_sequence", []), shadbala, digs, house_lords, ak, amk,
        current_age=current_age, eff_strengths=eff_strengths, planet_house=ph)
    payload_data.peak_dasha_lord = peak_lord
    # GAP-3 fix: this used to default to (0.0, 99.0) — the entire lifespan —
    # whenever the lord-match scan below failed to find peak_lord in
    # dasha_sequence, with no signal that the fallback had fired at all.
    # Now the fallback is logged so a silent key-mismatch (e.g. "lord" vs
    # "md_planet") is visible instead of masquerading as a real window.
    _peak_window = None
    for _d in getattr(payload_data, "dasha_sequence", []):
        _dl = _d.get("lord", "") or _d.get("md_planet", "")
        if _dl == peak_lord:
            _peak_window = (float(_d.get("start_age", 0) or 0), float(_d.get("end_age", 99) or 99))
            break
    if _peak_window is None:
        if peak_lord:
            logger.warning(
                "Peak dasha window lookup failed for lord=%s — no matching "
                "dasha_sequence entry found; falling back to full lifespan "
                "window (0.0, 99.0). Check lord/md_planet key consistency.",
                peak_lord,
            )
        _peak_window = (0.0, 99.0)
    payload_data.peak_dasha_window = _peak_window
    if peak_lord:
        # GAP-11 fix: was truncated to the top 5 scores, which isn't enough
        # to audit a near-tie against the rest of the field. Log everything.
        logger.info(f"Peak career MD: {peak_lord}  (scores: { {k: round(v,3) for k,v in sorted(peak_scores.items(), key=lambda x:-x[1])} })")

    sorted_planets    = sorted(eff_strengths.items(), key=lambda x: -x[1])
    top_3_planets     = [p for p, _ in sorted_planets[:3]]
    edu_eff_strengths = eff_strengths

    # EduAlign E-1: D1 H5 × D24 H10 stream affinity (technical/humanities/arts) — once per chart
    try:
        from .edu_align import compute_d1_d24_stream_score as _d1d24_stream
        payload_data.edu_stream = _d1d24_stream(payload_data)
    except Exception as _edu_e:
        logger.debug("EduAlign E-1 stream score skipped: %s", _edu_e)
        payload_data.edu_stream = {}

    # EduAlign E-4 (2026-07-04 ontology audit, G17): D24-driven UG/PG/PhD
    # tier recommendation — advisory only, once per chart, never touches
    # per-field final_score or the registry's tier_map.
    try:
        from .edu_align import compute_academic_tier_recommendation as _tier_reco
        payload_data.academic_tier_recommendation = _tier_reco(payload_data)
    except Exception as _tier_e:
        logger.debug("EduAlign E-4 tier recommendation skipped: %s", _tier_e)
        payload_data.academic_tier_recommendation = {}
    edu_ranked        = [(p, round(v, 3)) for p, v in sorted_planets]
    edu_planet_reasons = {
        p: f"Core astrological driver for academic alignment (Effective Strength: {round(v, 2)})"
        for p, v in sorted_planets[:3]
    }
    logger.info(f"Top planets by effective strength: {[(p, round(v,3)) for p,v in sorted_planets[:5]]}")

    # audit B-3: use the single shared fallback convention (affinity.py::_GENERIC_9P_WEIGHTS)
    # instead of a bespoke 4-planet default — previously there were three competing
    # "field has no vector" conventions across engine.py / affinity.py.
    _DEFAULT_AFFINITY: Dict[str, float] = dict(_GENERIC_9P_WEIGHTS)
    _all_pre_results: List[Dict] = []

    # P1: resolve career phase once per run
    _career_phase = _resolve_career_phase(payload_data)
    logger.info(f"P1 career phase resolved: {_career_phase}")

    # Structural impairment sets
    _war_losers   = {p for p, s in war_result.items() if "loser" in s}
    _mrita_planets = _detect_mrita_avastha(planets_d1)
    if _war_losers:
        logger.info(f"Structural impairment — war losers: {_war_losers}")
    if _mrita_planets:
        logger.info(f"Structural impairment — Mrita Avastha: {_mrita_planets}")
    return {
        "_DEFAULT_AFFINITY": _DEFAULT_AFFINITY,
        "_antardasha_lord": _antardasha_lord,
        "_argala_h10": _argala_h10,
        "_career_phase": _career_phase,
        "_house_discrepant_planets": _house_discrepant_planets,
        "_kp_h10_star_lord": _kp_h10_star_lord,
        "_mrita_planets": _mrita_planets,
        "_transit_degrees": _transit_degrees,
        "_transit_houses": _transit_houses,
        "_vb_ak": _vb_ak,
        "_vb_h10": _vb_h10,
        "_vimshopaka_d10_scale": _vimshopaka_d10_scale,
        "_vimshopaka_d9_scale": _vimshopaka_d9_scale,
        "_war_losers": _war_losers,
        "active_lord": active_lord,
        "ak": ak,
        "already_excel": already_excel,
        "amk": amk,
        "amk_house": amk_house,
        "brahma_lord": brahma_lord,
        "cazimi_set": cazimi_set,
        "combust": combust,
        "current_age": current_age,
        "d10_chart": d10_chart,
        "d10_digs": d10_digs,
        "d10_lagna": d10_lagna,
        "d9_chart": d9_chart,
        "d9_digs": d9_digs,
        "d9_lagna": d9_lagna,
        "digs": digs,
        "edu_eff_strengths": edu_eff_strengths,
        "edu_planet_reasons": edu_planet_reasons,
        "edu_ranked": edu_ranked,
        "eff_strengths": eff_strengths,
        "gender_val": gender_val,
        "h10_lord": h10_lord,
        "h10_lp": h10_lp,
        "h5_lord": h5_lord,
        "house_lords": house_lords,
        "interested_in": interested_in,
        "kara_occ": kara_occ,
        "karakamsha": karakamsha,
        "lagna_lord": lagna_lord,
        "lagna_sign": lagna_sign,
        "maheshwara_lord": maheshwara_lord,
        "nb_set": nb_set,
        "peak_lord": peak_lord,
        "ph": ph,
        "planet_trace": planet_trace,
        "planets_d1": planets_d1,
        "prd_houses": prd_houses,
        "prd_lord": prd_lord,
        "prime_career_lord": prime_career_lord,
        "retro": retro,
        "risk": risk,
        "sav": sav,
        "shadbala": shadbala,
        "ul": ul,
        "vargottama": vargottama,
        "war_result": war_result,
        "yogas": yogas,
        "_all_pre_results": _all_pre_results,
    }


def _finalize_pre_results(
    _all_pre_results,
    payload_data,
    eff_strengths,
    house_lords,
    active_lord,
    peak_lord,
    _mrita_planets,
    _career_phase,
    current_age,
    ph,
    lagna_sign,
    ak,
    _antardasha_lord,
) -> tuple:
    """Stage D (2026-08-17): pure code motion of the post-loop finalization
    phase that used to be the last ~600 lines of _run_normalization_stage(),
    extracted verbatim (no formula, cap, or ordering changed). Applies
    normalization/tiebreak/gap-correction/ontology/dedup/LLM-payload-build/
    360-profile steps to the per-field results produced by the scoring loop,
    and returns the same (top35_for_llm, eff_strengths, lagna_sign, ak)
    tuple _run_normalization_stage() used to return directly.

    ═══════════════════════════════════════════════════════════════════════
    GATE-STACK MAP (2026-08, structural-risk audit)
    ═══════════════════════════════════════════════════════════════════════
    This function chains 10+ post-loop passes over the field-scoring batch.
    Every pass that touches `final_score` is followed by a re-sort — a
    field's FINAL RANK is therefore a function of the ORDER these passes run
    in, not just of the astrology each one individually encodes. Each pass
    below is astrologically/methodologically sound in isolation (see its own
    docstring/inline comment for the reasoning); this block exists because
    the *sequencing* between them is reasoning that previously lived only as
    scattered inline comments, which made it easy for a new gate to be
    inserted in the wrong spot and silently change real-chart rankings
    (this has happened before — see the `.bak` files in this directory named
    after specific misplacement fixes, e.g. `pre_qa_gate_double_penalty_fix`,
    `pre_double_count_fix`, `pre_raja_dhana_yoga_fix`). Read this block
    before adding, removing, or reordering ANY step in this function.

    The ordered sequence, and why each boundary is where it is:

      1. Cap raw final_score at 250 (anti-inflation ceiling), sort desc.
      2. _apply_minmax_normalization — per-method Min-Max (Arch-B).
      3. _apply_paradigm_spread_penalty — MUST run before the 20-100 display
         stretch (step 6): a penalty applied pre-stretch genuinely changes
         relative ranking; applied post-stretch it would only cosmetically
         compress an already-decided order.
      4. _apply_interdomain_normalization (A7) — same pre-stretch reasoning.
      5. _apply_combined_risk_floor — caps the COMBINED effect of every
         risk/mismatch/disagreement gate above (5 per-field + paradigm-
         spread + interdomain) at one floor. Must run AFTER all of those
         gates have had a chance to fire, and — same reasoning as 3/4 —
         BEFORE the display stretch, or the floor becomes cosmetic.
      6. 20-100 display stretch (cross-batch min-max rescale). Everything
         above this line operates on the raw/uncapped chain score and is
         free to add or subtract however many points a gate calls for;
         everything below this line operates on the STRETCHED 20-100 score
         and must think in "points on a 20-100 scale" terms, not raw-chain
         terms, or its bound (e.g. the tiebreak cascade's ≤0.45pt nudge) is
         calibrated against the wrong scale.
      7. _apply_medical_governance_rebalance — reads post-stretch scores by
         design (rebalances a specific, narrow domain conflict; not meant to
         re-litigate the whole batch's relative spread).
      8. Tiebreaker cascade (T2-F) — D1-level H10/lagna/dasha-lord affinity,
         falling back to a D10 differentiator, falling back to a KP H10
         sub-lord differentiator, falling back to a stable field_id-order
         nudge for genuine exact ties. Runs on the STRETCHED score (nudges
         are ≤0.45pts, calibrated for the 20-100 range) and specifically
         AFTER medical-governance rebalance so ties it might create/resolve
         are still visible to the cascade. Order of fallbacks matters: each
         is only consulted when the previous one failed to separate the
         pair (see each differentiator's own comment for why it's scoped
         that narrowly) — do not reorder the fallback chain without
         re-reading why each is "last resort" relative to the one above it.
      9. apply_gap_2026_07_corrections (round 1: Ketu mode, student
         MD-weighting, Mrita consistency, Venus branch-by-companion,
         interest-prior) — bounded/capped, baked into final_score.
     10. apply_competency_ontology_layer + attach_graph_diagnostics — MUST
         run before round 2/3 gap corrections below, because those rounds
         read `graph_broadness_penalty`/`graph_cluster` that this step is
         what attaches to each row in the first place.
     11. apply_gap_2026_07_round2_corrections — depends on step 10's graph
         diagnostics being present; would silently no-op its
         broadness-aware logic if moved earlier.
     12. apply_gap_2026_07_round3_corrections — same dependency as 11.
     13. apply_domain_deduplication → _edu_stream_slot_allocation (top-35
         selection) — MUST run after every full-registry-level (all ~199
         fields) scoring/correction pass above, because domain dedup and
         slot allocation only make sense evaluated over the COMPLETE
         candidate pool; run it earlier and it would be deduplicating an
         incompletely-scored batch.
     14. _apply_medical_governance_priority_selection,
         _retain_materials_physical_route — operate on the top-35 subset
         only (everything above this line still saw all ~199 fields).
     15. Defensive final re-sort + LLM-payload dict build + 360°-profile
         chart-level scores (wealth/burnout/micro-niches/academic-path/
         institutional-tier/geo-suitability) — these last are additive,
         per-field-insight attachments, NOT ranking gates: they must never
         mutate final_score, only decorate the already-final top-35 rows.

    CHECKLIST for adding a new gate to this stack:
      a) Does it need the full ~199-field registry, or only the top-35? If
         full-registry, it belongs before step 13; if top-35-only, after.
      b) Should it genuinely change relative ranking, or only annotate/
         message? If ranking-changing, it belongs BEFORE step 6 (the 20-100
         stretch) so it isn't reduced to cosmetic rescaling.
      c) Does it read graph/ontology diagnostics (graph_cluster,
         graph_broadness_penalty, competency, career_family)? If so it must
         run AFTER step 10, not before.
      d) Any step that mutates final_score must be immediately followed by
         `_all_pre_results.sort(key=lambda x: -x["final_score"])` — every
         existing step follows this rule; skipping it silently breaks the
         "ordered by Total" guarantee the published report advertises.
      e) Wrap the new step in try/except (see steps 9-12's pattern) so a
         failure in one gate can never take down the whole engine run.
      f) Document WHY this step's position is where it is, the same way
         every step above does — and update this map to match, so the next
         person doesn't have to re-derive the ordering from scratch.
    ═══════════════════════════════════════════════════════════════════════
    """
    # ── Post-loop ────────────────────────────────────────────────────────────
    # LS1 fix: cap raw score before sort to prevent unbounded inflation
    # (score inflation chain: blended → SAV → gap_boost → astro_mult → ak_flat can reach 300+)
    for _r in _all_pre_results:
        _r["final_score"] = min(_r["final_score"], 250.0)
    _all_pre_results.sort(key=lambda x: -x["final_score"])
    _all_pre_results = _apply_minmax_normalization(_all_pre_results)
    # 2026-07 engine-gap audit fix: apply the bounded paradigm-spread penalty
    # right after the explainability_matrix (which computes paradigm_spread)
    # is attached, and BEFORE the 20-100 display stretch below -- doing it
    # pre-stretch means the penalty genuinely changes relative ranking rather
    # than just cosmetically compressing an already-decided order.
    _all_pre_results = _apply_paradigm_spread_penalty(_all_pre_results)
    _all_pre_results.sort(key=lambda x: -x["final_score"])
    _all_pre_results = _apply_interdomain_normalization(_all_pre_results)  # A7 fix
    # Gap-audit fix (2026-08): cap the combined effect of all seven risk/
    # mismatch/disagreement gates above (five per-field + paradigm-spread +
    # interdomain) at a single floor, so they no longer compound unbounded.
    # Must run after every gate above has had a chance to fire and BEFORE
    # the 20-100 display stretch below, for the same reason paradigm-spread
    # runs pre-stretch: to genuinely change relative ranking, not just
    # cosmetically rescale an already-decided order. See
    # _apply_combined_risk_floor's docstring for the real-chart case
    # (Electrical Engineering) that surfaced this.
    _all_pre_results = _apply_combined_risk_floor(_all_pre_results)
    _all_pre_results.sort(key=lambda x: -x["final_score"])
    # LS1+LS4 fix: normalize final_score to 20–100 display range.
    # Gap-C fix: store pre-normalization score so auditors can see the raw chain total.
    # The displayed final_score diverges substantially from chain scores when the batch
    # has a wide spread (e.g. chain scores 120-160 all compress to displayed 56-100).
    for _r in _all_pre_results:
        _r["pre_norm_score"] = _r["final_score"]
    _fs_vals = [r["final_score"] for r in _all_pre_results]
    _fs_max  = max(_fs_vals) if _fs_vals else 1.0
    _fs_min  = min(_fs_vals) if _fs_vals else 0.0
    _fs_span = _fs_max - _fs_min or 1.0
    _norm_note = (
        f"cross-batch min-max: score range [{round(_fs_min,2)}–{round(_fs_max,2)}] "
        f"→ display range [20–100]"
    )
    for _r in _all_pre_results:
        _r["final_score"] = round(20.0 + 80.0 * (_r["final_score"] - _fs_min) / _fs_span, 2)
        _r["norm_note"] = _norm_note
    _all_pre_results = _apply_medical_governance_rebalance(_all_pre_results, payload_data, eff_strengths)

    # ── T2-F: Tiebreaker cascade for fields within 3 pts ────────────────────
    # When two fields are statistically tied, use Parashara structural signals to break.
    # Nudge ≤ 0.45 pts so we never flip a genuine score gap.
    _h10_lord_tb  = getattr(payload_data, "h10_lord", "") or ""
    _lagna_lord_tb = getattr(payload_data, "lagna_lord", "") or ""
    _active_lord_tb = getattr(payload_data, "active_dasha_lord", "") or ""
    _TB_THRESHOLD = 3.0

    # Gap-Combo fix: the discriminator above (H10/lagna/dasha lord affinity) is the same
    # D1-level signal already baked into every method's scoring, so it can't genuinely
    # separate two fields whose affinity tables differ only by weight decimals (e.g.
    # electrical_engineering vs power_systems_engineering share the same top planets).
    # D10 (Dashamsha) is Jyotish's own dedicated fine-grained career-differentiation
    # varga -- it exists specifically to distinguish between adjacent professional
    # expressions of the same D1 promise. Break remaining ties using each field's own
    # top-weighted planet's D10 house placement and dignity, which is a genuinely
    # separate testimony from the D1-level tiebreak above.
    _d10_digs_tb = getattr(payload_data, "d10_planet_dignities", {}) or {}
    _d10_occ_tb  = getattr(payload_data, "d10_house_occupancy", {}) or {}
    _d10_planet_house_tb: Dict[str, int] = {}
    for _h, _plist in (_d10_occ_tb or {}).items():
        try:
            _hn = int(_h)
        except (TypeError, ValueError):
            continue
        for _p in (_plist or []):
            _d10_planet_house_tb[_p] = _hn
    _D10_DIG_PTS_TB = {"EXALTED": 0.20, "OWN": 0.14, "NEECHA_BHANGA": 0.08, "DEBILITATED": -0.10}

    # 2026-08 methodology-gap fix: KP's H10 (10th cusp) sub-lord is the
    # classically DECISIVE technique for a yes/no career-fit call between two
    # close candidates -- this is distinct from, and much narrower-scoped
    # than, KP's static general blend weight (METHOD_WEIGHTS["kp"] ~= 0.063
    # in field_methods/__init__.py), which discounts KP across the board for
    # the "which field" question generally. Restoring that classical role
    # ONLY inside this tiebreak cascade (never outside it) lets KP do the one
    # job it is genuinely built for -- discriminating between near-tied
    # fields -- without inflating its influence on the main ranking. Nudge
    # kept in the same ~0.10-0.20 pt range as the sibling H10/lagna/dasha-lord
    # and D10 discriminators above/below so no single signal gets outsized
    # leverage over the others.
    _kp_cusps_tb = getattr(payload_data, "kp_cusps", {}) or {}
    _kp_h10_sub_tb = (_kp_cusps_tb.get("H10", {}) or {}).get("sub_lord", "") or ""
    # Reuse the same cusp-verification + birth-time-precision gates KP's own
    # score_kp() applies to its sub-lord chain (audit_kp_cusps + precise_cusps
    # _allowed) so this tiebreak signal never fires off untrustworthy cusps --
    # if KP data is unavailable/low-confidence for this chart, it simply does
    # not participate (no arbitrary default direction), same as score_kp()'s
    # own _kp_conf_sub gate.
    _kp_tb_reliable = False
    if _kp_h10_sub_tb:
        try:
            from jyotish.kp_audit import audit_kp_cusps as _audit_kp_cusps_tb
            _kp_cusp_audit_tb = _audit_kp_cusps_tb(
                _kp_cusps_tb, getattr(payload_data, "house_system", "") or ""
            )
            _kp_cusp_verified_tb = _kp_cusp_audit_tb.get("status") == "VERIFIED"
            _policy_tb = getattr(payload_data, "calculation_policy", None)
            if _policy_tb is not None and hasattr(_policy_tb, "precise_cusps_allowed"):
                _kp_precise_tb = bool(_policy_tb.precise_cusps_allowed)
            else:
                _kp_precise_tb = (
                    getattr(payload_data, "birth_time_precision", "exact") or "exact"
                ) == "exact"
            _kp_tb_reliable = _kp_cusp_verified_tb and _kp_precise_tb
        except Exception:
            _kp_tb_reliable = False

    def _kp_h10_sublord_differentiator(r) -> float:
        if not _kp_tb_reliable or not _kp_h10_sub_tb:
            return 0.0
        aff = r.get("affinity_planets", {})
        w = aff.get(_kp_h10_sub_tb, 0.0)
        if w > 0.10:
            return 0.20
        if w < -0.05:
            return -0.10
        return 0.0

    def _d10_differentiator(r) -> float:
        aff = r.get("affinity_planets", {})
        if not aff:
            return 0.0
        top_planet = max(aff.items(), key=lambda kv: kv[1])[0]
        pts = 0.0
        _h10d = _d10_planet_house_tb.get(top_planet, 0)
        if _h10d in (1, 4, 5, 7, 9, 10):
            pts += 0.12
        elif _h10d in (6, 8, 12):
            pts -= 0.08
        pts += _D10_DIG_PTS_TB.get(_d10_digs_tb.get(top_planet, ""), 0.0)
        return round(pts, 4)

    # GAP-FIX: snapshot each field's pre-tiebreak final_score before the
    # cascade runs. The pairwise loop below mutates final_score in place as
    # it resolves each pair; if the "are these two within threshold?" check
    # instead reads the live (already-nudged) score, then whether pair
    # (i, j) is even considered "tied" — and thus whether it can shift a
    # later pair's outcome — depends on which earlier pairs happened to run
    # first in `enumerate(_all_pre_results)` order, not on the original
    # scores themselves. That makes the tie-break outcome for a cluster of
    # near-tied fields silently dependent on registry iteration/insertion
    # order rather than on the documented discriminators. Gating the
    # threshold check on the immutable snapshot instead removes that
    # order-dependency: which pairs are eligible to be nudged is now a pure
    # function of the original scores, computed once, regardless of loop
    # order. The nudges themselves still accumulate on the live
    # final_score as before (a field tied with several neighbors can still
    # be nudged more than once), which is unchanged, intended behavior.
    _tb_orig_scores = {id(_r): _r["final_score"] for _r in _all_pre_results}

    for _i, _ri in enumerate(_all_pre_results):
        for _j, _rj in enumerate(_all_pre_results):
            if _i >= _j:
                continue
            if abs(_tb_orig_scores[id(_ri)] - _tb_orig_scores[id(_rj)]) > _TB_THRESHOLD:
                continue
            # Both within threshold — compute discriminator for each
            def _tb_score(r, h10l, lagnal, dasal):
                aff = r.get("affinity_planets", {})
                pts = 0.0
                if h10l:
                    pts += aff.get(h10l, 0.0) * 0.20    # H10 lord affinity
                if lagnal:
                    pts += aff.get(lagnal, 0.0) * 0.15  # lagna lord affinity
                if dasal and aff.get(dasal, 0.0) > 0.10:
                    pts += 0.10                           # dasha lord match
                return round(pts, 4)
            _di = _tb_score(_ri, _h10_lord_tb, _lagna_lord_tb, _active_lord_tb)
            _dj = _tb_score(_rj, _h10_lord_tb, _lagna_lord_tb, _active_lord_tb)
            # D10-specific differentiator only breaks a tie left unresolved by the
            # D1-level discriminator above -- it's a tiebreaker of last resort, not a
            # replacement, since D1 testimony should still take precedence when present.
            if _di == _dj:
                _di = _d10_differentiator(_ri)
                _dj = _d10_differentiator(_rj)
            # KP H10 sub-lord tiebreaker: classically decisive for close calls,
            # but only consulted as a LAST-RESORT discriminator after both the
            # D1-level and D10 discriminators above have failed to separate the
            # pair -- see comment at its definition above for why it's scoped
            # this narrowly.
            if _di == _dj:
                _di = _kp_h10_sublord_differentiator(_ri)
                _dj = _kp_h10_sublord_differentiator(_rj)
            if _di != _dj:
                _nudge = min(abs(_di - _dj), 0.45)
                if _di > _dj:
                    _ri["final_score"] = round(_ri["final_score"] + _nudge, 2)
                    _rj["final_score"] = round(_rj["final_score"] - _nudge, 2)
                else:
                    _rj["final_score"] = round(_rj["final_score"] + _nudge, 2)
                    _ri["final_score"] = round(_ri["final_score"] - _nudge, 2)
            elif _ri["final_score"] == _rj["final_score"]:
                # 2026-07 engine-gap audit fix (Phase 5): fields with a
                # genuinely empty affinity_planets dict (no planetary
                # signal at all) give both the D1-level and D10-level
                # discriminators above 0.0, so a run of unrelated,
                # equally-unsupported fields could reach the exact same
                # final_score with NO differentiator able to break it --
                # the "8 consecutive unrelated fields tied at 34.8" defect
                # the audit found. Rather than leave an unexplained exact
                # duplicate (which reads as a bug even though the score is
                # arguably "correctly" equal), apply the smallest possible
                # deterministic, non-astrological nudge so ties are always
                # broken the same way on every run -- stable field_id
                # ordering, not incidental list/sort-implementation order.
                # This is a display/reproducibility fix only: 0.01 pts
                # cannot flip any real ranking decision.
                if _ri.get("field_id", "") < _rj.get("field_id", ""):
                    _ri["final_score"] = round(_ri["final_score"] + 0.01, 2)
                else:
                    _rj["final_score"] = round(_rj["final_score"] + 0.01, 2)
                _ri["tie_break_note"] = _ri.get("tie_break_note", "") or (
                    "exact-tie fallback: no differentiating signal found; broken by stable field_id order"
                )
                _rj["tie_break_note"] = _rj.get("tie_break_note", "") or (
                    "exact-tie fallback: no differentiating signal found; broken by stable field_id order"
                )
    _all_pre_results.sort(key=lambda x: -x["final_score"])

    # ── 2026-07 gap-audit corrections (Ketu mode, student MD-weighting,
    # Mrita consistency, Venus branch-by-companion, interest-prior) ─────────
    # Bounded/capped, baked directly into final_score (never reorder-only —
    # see jyotish/gap_corrections_2026_07.py docstring for why). Wrapped
    # defensively so a failure here can never break field determination.
    try:
        _all_pre_results = apply_gap_2026_07_corrections(
            _all_pre_results, payload_data, eff_strengths, house_lords,
            active_lord, peak_lord, _mrita_planets, _career_phase,
        )
        _all_pre_results.sort(key=lambda x: -x["final_score"])
    except Exception as _gap0707_e:
        logger.warning("2026-07 gap corrections failed, continuing without them: %s", _gap0707_e)

    # ── Competency-first ontology layer (G1-G18, G22, G23-G31) ──────────────
    # Attaches competency/career_family metadata, confidence bands (G24),
    # explanation chains (G23), contradictory-evidence summaries (G25),
    # aptitude explanations (G27), and applies the bounded family-cohesion
    # (+/-4%, G1/G16/G30) and yoga-alignment (+0-5%, G22) adjustments before
    # domain dedup / LLM selection so downstream consumers (dedup, top-35
    # slotting, LLM prompt, web_report) all see the enriched rows. Also
    # attaches the G28 life-stage competency evolution (from the chart's own
    # dasha_sequence — not recomputed) and the G31 cross-chart percentile
    # (proxy calibration against the 500-scenario stress corpus) to the
    # cluster report. Wrapped defensively: ontology enrichment must never be
    # able to break field determination itself if the taxonomy is incomplete
    # for a not-yet-catalogued branch id.
    try:
        _all_pre_results, _career_cluster_report = apply_competency_ontology_layer(
            _all_pre_results,
            detected_yogas=getattr(payload_data, "detected_yogas", []) or [],
            dasha_sequence=getattr(payload_data, "dasha_sequence", []) or [],
            current_age=current_age,
        )
        _all_pre_results = attach_graph_diagnostics(_all_pre_results)
    except Exception as _onto_e:
        logger.warning("Competency ontology layer failed, continuing without it: %s", _onto_e)
        _career_cluster_report = {}

    # ── 2026-07 gap-audit corrections, round 2 (macro-cluster gate, Mars
    # mode, Mrita extension to Moon/Saturn, hybrid-vs-plain resolver, risk
    # appetite niche discount, self-audit) ──────────────────────────────────
    # Must run AFTER attach_graph_diagnostics() above so graph_cluster /
    # graph_broadness_penalty are already present on each row. Bounded/capped
    # and baked into final_score, same discipline as round 1. Wrapped
    # defensively so a failure here can never break field determination.
    try:
        _all_pre_results, _gap0707_r2_audit = apply_gap_2026_07_round2_corrections(
            _all_pre_results, payload_data, eff_strengths, house_lords,
            _mrita_planets, active_lord, peak_lord,
        )
        _all_pre_results.sort(key=lambda x: -x["final_score"])
        if isinstance(_career_cluster_report, dict):
            _career_cluster_report["gap_2026_07_round2_audit"] = _gap0707_r2_audit
    except Exception as _gap0707_r2_e:
        logger.warning("2026-07 round-2 gap corrections failed, continuing without them: %s", _gap0707_r2_e)

    # ── 2026-07 gap-audit corrections, round 3 (broadness-penalty wiring,
    # Virgo-10th/Mercury-10th-lord accelerator) ─────────────────────────────
    # Must also run after attach_graph_diagnostics() (needs
    # graph_broadness_penalty). Bounded/capped, baked into final_score.
    try:
        _all_pre_results = apply_gap_2026_07_round3_corrections(
            _all_pre_results, payload_data, eff_strengths, house_lords,
        )
        _all_pre_results.sort(key=lambda x: -x["final_score"])
        if isinstance(_career_cluster_report, dict):
            # Refresh the self-audit now that round 3 has also run, so
            # demoted/promoted reasons include all three rounds.
            _career_cluster_report["gap_2026_07_round2_audit"] = build_round2_audit_summary(_all_pre_results)
    except Exception as _gap0707_r3_e:
        logger.warning("2026-07 round-3 gap corrections failed, continuing without them: %s", _gap0707_r3_e)

    # LS6 fix: apply domain deduplication BEFORE LLM field selection so the
    # candidate list already reflects domain diversity (avoids wasting LLM calls
    # on fields that will be culled post-selection).
    _pre_dedup_scores = {r.get("field_id", ""): r.get("final_score", 0.0) for r in _all_pre_results}
    _all_deduped = apply_domain_deduplication(_all_pre_results)
    top_35 = _edu_stream_slot_allocation(_all_deduped, getattr(payload_data, "edu_stream", {}), n=35)
    # 2026-07 fix: _retain_priority_cluster_companions() used to run here. It
    # force-inserted a second "priority cluster" sibling (e.g. a space/aerospace
    # or life-science field) into a fixed position inside the top-20 window
    # regardless of that field's actual score, then appended whatever it
    # displaced to the end of the list. Confirmed on a real chart: a field
    # scoring 26% relative strength (bottom of the whole 199-field registry)
    # was inserted at rank 20 between two fields both scoring ~64%, silently
    # breaking the "ordered by Total" guarantee the report tables advertise.
    # This was flagged but left unresolved in DEEP_AUDIT_GAPS_2026-07.md item
    # 18 ("intentional product behaviour... as code it looks like a demo
    # artifact"). Decision: removed. Ranking is now purely score-based; the
    # function itself is left defined (unused) rather than deleted in case a
    # future, non-order-breaking version of "guarantee cluster visibility" is
    # wanted (e.g. a clearly-labeled separate section, not an inline splice).
    top_35 = _apply_medical_governance_priority_selection(
        top_35, _all_pre_results, payload_data, eff_strengths, n=35
    )
    top_35 = _retain_materials_physical_route(
        top_35, _all_pre_results, eff_strengths, _pre_dedup_scores, n=35
    )
    try:
        top_35 = attach_graph_diagnostics(top_35)
    except Exception as _kg_e:
        logger.warning("Knowledge graph diagnostics failed, continuing without them: %s", _kg_e)

    # Gap fix (2026-08, chat audit, revised): the old rule flattened every
    # score above 100 straight to 100.0 *here*, i.e. before
    # apply_publication_ranking_policy() and _enforce_hard_lockout_publication_
    # order() ever ran (those happen later, in _finalize_published_results()).
    # That meant every downstream ranking/discount/tie-break decision saw the
    # already-flattened 100.0, not the genuine chain total -- so even a fix
    # that only "un-flattened the printed number" at this point would still
    # let two fields with real totals 117.35 and 101.52 get identically
    # discounted, tie-broken, and dedup-prioritized as if they were tied.
    # Per the user's explicit requirement: ranking, tie-breaking, selection,
    # and confidence must run on the raw, uncapped chain score; ONLY the
    # final printed number should ever be capped for a 0-100 display scale.
    # So: do NOT clamp/compress final_score here at all. Preserve the true
    # value, and let it flow uncapped through ranking_policy's discounts,
    # the hard-lockout ordering, and the ceiling-tie/differentiation
    # annotation -- all of which must see real separation, not a flattened
    # ceiling. Display-only compression is applied once, as the very last
    # step of run_engine(), after rank has already been stamped by every
    # stage above (see _apply_display_score_compression()).
    for _r in top_35:
        _r["raw_final_score"] = _r.get("final_score", 0.0)

    # Defensive re-sort: guarantee strict descending final_score order no
    # matter what upstream slotting/selection steps did, so the printed
    # "ordered by Total" claim is always actually true. final_score is still
    # the genuine uncapped value here (no display compression has happened
    # yet), so this sort is already ranking on raw astrological support.
    top_35.sort(key=lambda r: -r.get("final_score", 0.0))
    try:
        _rebuilt_cluster_report = build_cluster_report(top_35)
        if isinstance(_career_cluster_report, dict):
            for _k, _v in _career_cluster_report.items():
                if _k not in _rebuilt_cluster_report:
                    _rebuilt_cluster_report[_k] = _v
        _career_cluster_report = _rebuilt_cluster_report
    except Exception as _cluster_rebuild_e:
        logger.warning("Final career cluster report rebuild failed, using prior report: %s", _cluster_rebuild_e)

    # Build LLM payload
    _top35_for_llm = []
    for _i, _r in enumerate(top_35, 1):
        _is_hard_locked = (
            _r.get("final_score", 0.0) < 20.0
            or bool(_r.get("is_afflicted", False))
        )
        _top35_for_llm.append({
            "rank":                     _i,
            "field_id":                 _r["field_id"],
            "field_label":              _r.get("field_label", _r["field_id"]),
            "domain":                   _r.get("domain", ""),
            "final_score":              round(_r["final_score"], 2),
            "raw_final_score":          _r.get("raw_final_score"),
            "affinity_score":           round(_r.get("affinity_score", 0), 2),
            "composite_score":          round(_r.get("composite_score", 0), 2),
            "blended_score":            round(_r.get("blended_score", 0), 2),
            # Bug fix (2nd attempt, this pass): the previous fix here read
            # "gap_boost_total"/"gap_penalty_total" off `_r` -- but those two
            # keys only ever exist nested inside a local `calc_trace` dict
            # (see calc_trace's own "gap_boost_total" key, ~line 4392), never
            # as top-level keys on the row `_r` actually is. So `_r.get(
            # "gap_boost_total", 0)` always silently hit its 0 default too --
            # same failure mode, different cause than first diagnosed.
            # Confirmed via a live debug run of Ramsunder's chart that the
            # genuinely top-level, always-populated keys on this row are
            # "acc.gap_boost"/"acc.gap_penalty" (set directly in the
            # _all_pre_results.append({...}) call in _score_one_field, e.g.
            # aerospace_engineering acc.gap_boost=0.4575 that run) -- reading
            # those instead.
            "gap_boost":                round(_r.get("acc.gap_boost", 0), 3),
            "gap_penalty":              round(_r.get("acc.gap_penalty", 0), 3),
            "gap_detail":               _r.get("gap_breakdown", {}),
            "affinity_planets":         _r.get("affinity_planets", {}),
            "method_scores_raw_unnormalized": _r.get("method_scores", {}),
            "method_scores_normalized_0_100": _r.get("method_normalized_scores", {}),  # LS12 fix
            "method_breakdown":         _r.get("method_breakdown", {}),
            "method_log":               _r.get("method_log", {}),
            "knrao_score":              _r.get("knrao_score", 0),
            "kp_score":                 _r.get("kp_score", 0),
            "jaimini_score":            _r.get("jaimini_score", 0),
            "parashara_score":          _r.get("parashara_score", 0),
            "dashamsha_score":          _r.get("dashamsha_score", 0),
            "sudarshana_score":         _r.get("sudarshana_score", 0),
            # Phase-1/2 remediation (2026-08 gap-audit): see matching comment
            # at the field-summary builder above -- same allow-list gap.
            "siddhamsha_score":         _r.get("siddhamsha_score", 0),
            "shashtiamsha_score":       _r.get("shashtiamsha_score", 0),
            # Stage 1 (Astro-OS v3 gap-audit implementation plan, 2026-08):
            # same allow-list gap, same fix, for structural_patterns_score.
            "structural_patterns_score": _r.get("structural_patterns_score", 0),
            # Bug fix (2026-08 gap-audit round 2, item 2): same allow-list gap
            # as siddhamsha_score/shashtiamsha_score above -- these two keys
            # were added to the field-summary builder's row dict but this
            # second, independent whitelist (the one actually returned to
            # callers) never copied them through, so they never reached the
            # published audit output. Confirmed missing on a live Midhula-
            # chart run (2026-08-14) before this fix.
            "d9_navamsha_confirmation": _r.get("d9_navamsha_confirmation", {}),
            "jaimini_chara_dasha_timing": _r.get("jaimini_chara_dasha_timing", {}),
            # Stage 4 (Astro-OS v3 gap-audit implementation plan, 2026-08):
            # same allow-list gap, same fix, for the new confidence
            # decomposition.
            "confidence_dimensions": _r.get("confidence_dimensions", {}),
            # Stage 3 (Astro-OS v3 gap-audit implementation plan, 2026-08):
            # same allow-list gap, same fix, for career_archetype.
            "career_archetype": _r.get("career_archetype", {}),
            "method_total_score":       _r.get("method_total_score", 0),
            "weighted_method_score":    _r.get("weighted_method_score", 0),
            "raw_combined_score":       _r.get("raw_combined_score", 0),
            "hard_lockout":             _is_hard_locked,
            "method_components":        _r.get("method_components", {}),
            "method_weighted_contributions": _r.get("method_weighted_contributions", {}),
            "method_scores_normalized": _r.get("method_scores_normalized", {}),
            "explainability_matrix":    _r.get("explainability_matrix", {}),
            "verified_factors":         _r.get("calc_trace", {}).get("verified_factors", ""),
            # Top 3 karaka planets by affinity weight (for LLM prompt + display)
            "top_karakas":              _top3_planets(_r.get("affinity_planets", {})),
            # Gap-boost as display percentage (e.g. 0.583 → 58.3%)
            "boost_pct":                round(_r.get("acc.gap_boost", 0.0) * 100, 1),
            # Registry meta and full trace — needed by web_report and output.py
            "registry":                 _r.get("registry", {}),
            "calc_trace":               _r.get("calc_trace", {}),
            # Gap-C fix: expose pre-normalization score and note for audit transparency
            "pre_norm_score":           _r.get("pre_norm_score"),
            "norm_note":                _r.get("norm_note", ""),
            # Competency-first ontology layer (G1-G18, G23-G30) — see
            # jyotish/competency_ontology.py. Additive only; does not change
            # any score computed above.
            "competency":               _r.get("competency", ""),
            "competency_label":         _r.get("competency_label", ""),
            "career_family":            _r.get("career_family", ""),
            "career_family_label":      _r.get("career_family_label", ""),
            "confidence_band":          _r.get("confidence_band", ""),
            # GAP-FIX (2026-07, transparency) verification note: confidence_band
            # above is a DIFFERENT, simpler concept (competency_ontology.py's
            # confidence_band() just maps final_score -> High/Medium/Low) than
            # score_confidence below (6-method cross-agreement, correlation-
            # discounted) -- they can legitimately disagree (a field can have
            # a high raw score while only 1-2 of the 6 scoring methods agree
            # on it). This whitelist dict-rebuild is also WHY score_confidence
            # was previously dropped from final output despite being set
            # correctly upstream -- any key not explicitly listed here is
            # silently stripped between the per-field scoring loop and the
            # LLM/final-output stage. Caught by re-running the engine
            # end-to-end and inspecting real output keys, not just grepping
            # for the assignment.
            "score_confidence":         _r.get("score_confidence", ""),
            "score_confidence_note":    _r.get("score_confidence_note", ""),
            "explanation_chain":        _r.get("explanation_chain", []),
            "evidence_summary":         _r.get("evidence_summary", {}),
            "family_cohesion_adjustment_pct": _r.get("family_cohesion_adjustment_pct", 0.0),
            "career_cluster_report":    _career_cluster_report,
            # Knowledge-graph ontology layer (2026-07-04): additive, score-neutral
            # diagnostics from jyotish/ontology_kg.py. These expose multi-parent
            # family structure, broad/generic field flags, and the graph-level
            # cluster without modifying final_score.
            "graph_broadness_penalty":   _r.get("graph_broadness_penalty", 0.0),
            "graph_family_memberships":  _r.get("graph_family_memberships", []),
            "graph_cluster":             _r.get("graph_cluster", ""),
            "graph_note":                _r.get("graph_note", ""),
            # GAP-FIX (2026-07-20): same whitelist-dict-rebuild trap this
            # function's own score_confidence comment above already documents
            # -- signal_lineage/signal_provenance were added to the bvb_eval
            # bundle and to _all_pre_results' row dict, but this second
            # whitelist (the one actually returned by
            # _run_normalization_stage, confirmed live by tracing DEBUG
            # markers through _all_deduped -> top_35 -> here) silently
            # stripped them, exactly like score_confidence's history.
            "signal_lineage":            _r.get("signal_lineage", {}),
            "signal_provenance":         _r.get("signal_provenance", {}),
        })

    # ── 360° Profile: chart-level scores ─────────────────────────────────────
    _corp_entrep = compute_corporate_entrepreneurial_score(
        ph, house_lords, eff_strengths, atmakaraka=ak
    )
    _geo = compute_geo_suitability(ph, house_lords, eff_strengths, lagna_sign)
    # C-3: D10 Corporate Hierarchy & Politics Risk
    try:
        from .boosts import compute_d10_politics_risk as _d10_politics_risk
        _politics = _d10_politics_risk(
            d10_planet_sign=getattr(payload_data, "d10_planet_sign", {}) or {},
            d10_house_lords=getattr(payload_data, "d10_house_lords", {}) or {},
            eff_strengths=eff_strengths,
            planet_house=ph,
        )
        _corp_entrep["politics_risk"] = _politics
    except Exception as _pr_err:
        logger.debug("C-3 politics risk skipped: %s", _pr_err)

    # Gap-40: expose the Job-vs-Business mode scores alongside the corporate/
    # entrepreneurial style so reports get one coherent business-prediction block.
    _corp_entrep["employment_mode"] = getattr(payload_data, "employment_mode_analysis", {}) or {}

    payload_data.corporate_entrepreneurial = _corp_entrep
    payload_data.geo_suitability            = _geo

    # C-2: Global Mobility % scalar — stored inside geo_suitability
    try:
        from .foreign_opportunities import compute_global_mobility_pct as _global_mob
        _mobility = _global_mob(
            house_lords=house_lords,
            planet_house=ph,
            eff_strengths=eff_strengths,
            rahu_house=getattr(payload_data, "rahu_house", 0) or 0,
            ketu_house=getattr(payload_data, "ketu_house", 0) or 0,
            yogas_present=list(getattr(payload_data, "yogas_present", []) or []),
        )
        payload_data.geo_suitability["global_mobility"] = _mobility
    except Exception as _gm_err:
        logger.debug("C-2 global mobility skipped: %s", _gm_err)

    # C-1: D10 Pivot Radar — stored inside corporate_entrepreneurial
    try:
        from Job_Career.timeline import compute_d10_pivot_radar as _pivot_radar
        from datetime import date as _date_cls
        _pivot = _pivot_radar(
            dasha_sequence=list(getattr(payload_data, "dasha_sequence", []) or []),
            d10_house_lords=getattr(payload_data, "d10_house_lords", {}) or {},
            eff_strengths=eff_strengths,
            today=_date_cls.today(),
        )
        payload_data.corporate_entrepreneurial["d10_pivot_radar"] = _pivot
    except Exception as _pv_err:
        logger.debug("C-1 D10 pivot radar skipped: %s", _pv_err)

    # ── GAP 1: Academic path + GAP 2: Institutional tier (MD-AD + transits) ─
    _academic_path      = compute_academic_path(house_lords, eff_strengths, ph)
    # Gap 0.4 fix: `transit_planets` ({planet: {"house": n}}) was a phantom
    # attribute — derive it from transit_house_positions so the institutional-tier
    # transit amplifiers actually receive data.
    _transit_planets    = getattr(payload_data, "transit_planets", None) or {
        _tp: {"house": _th}
        for _tp, _th in (getattr(payload_data, "transit_house_positions", {}) or {}).items()
        if _th
    }
    _institutional_tier = compute_institutional_tier(
        ph, house_lords, eff_strengths, lagna_sign,
        md_lord=active_lord,
        ad_lord=_antardasha_lord,
        transit_planets=_transit_planets,
    )
    payload_data.academic_path      = _academic_path
    payload_data.institutional_tier = _institutional_tier

    # -- GAP 3/4: Per-field insight bundle (wealth, burnout, micro-niches) --
    _combust_list = list(getattr(payload_data, 'combust_planets', []) or [])
    _field_insights: Dict = {}
    for _item in _top35_for_llm:
        # §7 fix: pass the field's own affinity vector so compute_wealth_potential
        # can scan the chart's ACTUAL Dhana-yoga topology (own-sign/exchange/
        # conjunction across all four wealth houses) for this field's real
        # significators, instead of only ever checking a hardcoded domain->
        # planets lookup table against just the 2nd/11th lords.
        _wp = compute_wealth_potential(_item, house_lords, ph, eff_strengths,
                                        field_affinity=BRANCH_PLANET_AFFINITY.get(_item.get("field_id", ""), {}))
        _br = compute_burnout_risk(_item, ph, house_lords, eff_strengths, _combust_list)
        # BUGFIX (2026-07, audit P0): default was `{}` (a dict) instead of `""`
        # (a string) for planets missing from payload_data.nakshatra_data.
        # compute_micro_niches() below (and _NAKSHATRA_LORD.get() inside it)
        # expects a nakshatra NAME STRING per planet and uses it as a dict
        # key -- any planet missing from nakshatra_data (which is the normal
        # case whenever a caller doesn't populate every planet, e.g. minimal
        # test payloads, or any future partial-data upstream source) silently
        # produced `{}` here, which crashed with `TypeError: unhashable type:
        # 'dict'` at boosts.py's _NAKSHATRA_LORD.get(amk_nakshatra, "") the
        # moment that planet happened to be the Amatyakaraka. Not a test-only
        # issue: this is a real schema/default-value bug in production code,
        # not a bad test fixture.
        _nakshatra_data = {
            p: (getattr(payload_data, 'nakshatra_data', {}) or {}).get(p, "")
            for p in ph.keys()
        }
        _amk = getattr(payload_data, 'amatyakaraka', '') or ''
        _mn  = compute_micro_niches(_item, ph, house_lords, _amk, _nakshatra_data)
        _cm  = build_confidence_matrix(_item)
        _item['wealth_potential']  = _wp
        _item['burnout_risk']      = _br
        _item['geo_suitability']   = _geo
        _item['micro_niches']      = _mn
        _item['confidence_matrix'] = _cm
        try:
            from .edu_align import compute_sub_branch_compatibility as _sbc_compat
            _edu_branch = _sbc_compat(
                _item.get('field_id', ''), eff_strengths,
                getattr(payload_data, 'planet_dignities', {}) or {},
            )
        except Exception as _edu_e2:
            logger.debug('EduAlign E-2 skipped for %s: %s', _item.get('field_id'), _edu_e2)
            _edu_branch = {}
        _item['sub_branch_compatibility'] = _edu_branch
        _item['academic_path']            = _academic_path
        _item['institutional_tier']       = _institutional_tier
        _fsj = build_field_summary_json(_item)
        _item['field_summary_json'] = _fsj
        _item['execution_path']     = _fsj.get('execution_path', {})
        _field_insights[_item.get('field_id', '')] = {
            'wealth_potential':         _wp,
            'burnout_risk':             _br,
            'geo_suitability':          _geo,
            'micro_niches':             _mn,
            'confidence_matrix':        _cm,
            'academic_path':            _academic_path,
            'institutional_tier':       _institutional_tier,
            'field_summary_json':       _fsj,
            'execution_path':           _fsj.get('execution_path', {}),
            'sub_branch_compatibility': _edu_branch,
        }

    payload_data.field_insights = _field_insights
    _chart_type = detect_chart_type(_top35_for_llm)
    payload_data.chart_type = _chart_type
    for _fid, _fi in _field_insights.items():
        _fi['chart_type'] = _chart_type

    return (_top35_for_llm, eff_strengths, lagna_sign, ak)


def _run_normalization_stage(payload_data: NatalPayloadV2) -> tuple:
    """Pipeline Stage 1 — deterministic scoring and normalisation.

    Runs the full field-scoring loop over all registered fields, then applies
    per-method Min-Max normalisation (Arch-B) and inter-domain soft-max
    normalisation (S2).  Returns the top-35 pre-scored payload ready for LLM
    dispatch, plus the context vars the LLM stage needs:

        (top35_for_llm, eff_strengths, lagna_sign, ak)
    """
    _ctx = _prepare_chart_scoring_context(payload_data)
    _DEFAULT_AFFINITY = _ctx["_DEFAULT_AFFINITY"]
    _antardasha_lord = _ctx["_antardasha_lord"]
    _argala_h10 = _ctx["_argala_h10"]
    _career_phase = _ctx["_career_phase"]
    _house_discrepant_planets = _ctx["_house_discrepant_planets"]
    _kp_h10_star_lord = _ctx["_kp_h10_star_lord"]
    _mrita_planets = _ctx["_mrita_planets"]
    _transit_degrees = _ctx["_transit_degrees"]
    _transit_houses = _ctx["_transit_houses"]
    _vb_ak = _ctx["_vb_ak"]
    _vb_h10 = _ctx["_vb_h10"]
    _vimshopaka_d10_scale = _ctx["_vimshopaka_d10_scale"]
    _vimshopaka_d9_scale = _ctx["_vimshopaka_d9_scale"]
    _war_losers = _ctx["_war_losers"]
    active_lord = _ctx["active_lord"]
    ak = _ctx["ak"]
    already_excel = _ctx["already_excel"]
    amk = _ctx["amk"]
    amk_house = _ctx["amk_house"]
    brahma_lord = _ctx["brahma_lord"]
    cazimi_set = _ctx["cazimi_set"]
    combust = _ctx["combust"]
    current_age = _ctx["current_age"]
    d10_chart = _ctx["d10_chart"]
    d10_digs = _ctx["d10_digs"]
    d10_lagna = _ctx["d10_lagna"]
    d9_chart = _ctx["d9_chart"]
    d9_digs = _ctx["d9_digs"]
    d9_lagna = _ctx["d9_lagna"]
    digs = _ctx["digs"]
    edu_eff_strengths = _ctx["edu_eff_strengths"]
    edu_planet_reasons = _ctx["edu_planet_reasons"]
    edu_ranked = _ctx["edu_ranked"]
    eff_strengths = _ctx["eff_strengths"]
    gender_val = _ctx["gender_val"]
    h10_lord = _ctx["h10_lord"]
    h10_lp = _ctx["h10_lp"]
    h5_lord = _ctx["h5_lord"]
    house_lords = _ctx["house_lords"]
    interested_in = _ctx["interested_in"]
    kara_occ = _ctx["kara_occ"]
    karakamsha = _ctx["karakamsha"]
    lagna_lord = _ctx["lagna_lord"]
    lagna_sign = _ctx["lagna_sign"]
    maheshwara_lord = _ctx["maheshwara_lord"]
    nb_set = _ctx["nb_set"]
    peak_lord = _ctx["peak_lord"]
    ph = _ctx["ph"]
    planet_trace = _ctx["planet_trace"]
    planets_d1 = _ctx["planets_d1"]
    prd_houses = _ctx["prd_houses"]
    prd_lord = _ctx["prd_lord"]
    prime_career_lord = _ctx["prime_career_lord"]
    retro = _ctx["retro"]
    risk = _ctx["risk"]
    sav = _ctx["sav"]
    shadbala = _ctx["shadbala"]
    ul = _ctx["ul"]
    vargottama = _ctx["vargottama"]
    war_result = _ctx["war_result"]
    yogas = _ctx["yogas"]
    _all_pre_results = _ctx["_all_pre_results"]
    # GAP-FIX: the registry loop previously had no fault isolation — a
    # single field raising inside _score_one_field (bad registry metadata,
    # an unexpected None among the ~60 threaded context vars for an
    # edge-case chart) propagated straight out of this function and crashed
    # the entire run_engine() call for every other field. Since
    # _score_one_field communicates its result only via the side-effecting
    # append onto _all_pre_results (no return value to check), a bad field
    # is now caught, logged with its field_id, and skipped — every other
    # field still gets scored and the run still produces a report. A count
    # mismatch between the registry and _all_pre_results (whether from a
    # caught exception here or from any future code path inside
    # _score_one_field that returns without appending) is logged so a
    # silent field-loss regression is visible in logs instead of invisible.
    _pre_loop_len = len(_all_pre_results)
    _failed_field_ids: List[str] = []
    for _fid, _fmeta in _COURSE_REGISTRY.items():
        try:
            _score_one_field(_fid=_fid, _fmeta=_fmeta, _DEFAULT_AFFINITY=_DEFAULT_AFFINITY, _antardasha_lord=_antardasha_lord, _argala_h10=_argala_h10, _career_phase=_career_phase, _house_discrepant_planets=_house_discrepant_planets, _kp_h10_star_lord=_kp_h10_star_lord, _mrita_planets=_mrita_planets, _transit_degrees=_transit_degrees, _transit_houses=_transit_houses, _vb_ak=_vb_ak, _vb_h10=_vb_h10, _vimshopaka_d10_scale=_vimshopaka_d10_scale, _vimshopaka_d9_scale=_vimshopaka_d9_scale, _war_losers=_war_losers, active_lord=active_lord, ak=ak, already_excel=already_excel, amk=amk, amk_house=amk_house, brahma_lord=brahma_lord, cazimi_set=cazimi_set, combust=combust, current_age=current_age, d10_chart=d10_chart, d10_digs=d10_digs, d10_lagna=d10_lagna, d9_chart=d9_chart, d9_digs=d9_digs, d9_lagna=d9_lagna, digs=digs, edu_eff_strengths=edu_eff_strengths, edu_planet_reasons=edu_planet_reasons, edu_ranked=edu_ranked, eff_strengths=eff_strengths, gender_val=gender_val, h10_lord=h10_lord, h10_lp=h10_lp, h5_lord=h5_lord, house_lords=house_lords, interested_in=interested_in, kara_occ=kara_occ, karakamsha=karakamsha, lagna_lord=lagna_lord, lagna_sign=lagna_sign, maheshwara_lord=maheshwara_lord, nb_set=nb_set, peak_lord=peak_lord, ph=ph, planet_trace=planet_trace, planets_d1=planets_d1, prd_houses=prd_houses, prd_lord=prd_lord, prime_career_lord=prime_career_lord, retro=retro, risk=risk, sav=sav, shadbala=shadbala, ul=ul, vargottama=vargottama, war_result=war_result, yogas=yogas, payload_data=payload_data, _all_pre_results=_all_pre_results)
        except Exception as _field_exc:
            _failed_field_ids.append(_fid)
            logger.warning(
                f"_score_one_field failed for field_id={_fid!r}; skipping this "
                f"field only, rest of the run continues: {_field_exc}"
            )

    _expected_len = _pre_loop_len + len(_COURSE_REGISTRY) - len(_failed_field_ids)
    if len(_all_pre_results) != _expected_len:
        logger.warning(
            "_run_normalization_stage: field-count mismatch after scoring loop — "
            f"expected {_expected_len} results ({len(_COURSE_REGISTRY)} registry "
            f"entries minus {len(_failed_field_ids)} caught failures), got "
            f"{len(_all_pre_results)}. A field may have returned without "
            "appending to _all_pre_results (silent field loss) rather than "
            "raising — investigate _score_one_field's early-return paths."
        )
    if _failed_field_ids:
        logger.warning(
            f"_run_normalization_stage: {len(_failed_field_ids)} of "
            f"{len(_COURSE_REGISTRY)} fields failed scoring and were skipped: "
            f"{_failed_field_ids}"
        )

    # GAP-FIX (2026-08, "trace all 60 parameters, call LLM with the final
    # values" request): earlier this call sat right here -- after the
    # scoring loop but BEFORE _finalize_pre_results -- and passed the
    # pre-finalization `_all_pre_results`. That list is NOT the truly final
    # one: _finalize_pre_results (normalization, tiebreak, gap-correction,
    # paradigm-spread/risk-floor gates, 20-100 display stretch, top-35 cut)
    # repeatedly does `_all_pre_results = _apply_xxx(_all_pre_results)`,
    # i.e. REASSIGNS the name to a new list object rather than mutating the
    # original in place, so the list this function held onto never picked
    # up any of that post-processing. The narrative call is now made AFTER
    # _finalize_pre_results returns, using its actual return value
    # (`_top35_for_llm`) as the value shown for `_all_pre_results` --
    # matching what a report/LLM consumer of run_engine's output actually
    # sees. Every other one of the ~60 context variables genuinely finishes
    # changing inside _prepare_chart_scoring_context and is unaffected by
    # this move (see the DEBUG dump from the prior run: those variables were
    # already correct there; only _all_pre_results needed this).
    # No-op unless BOTH DEBUG=true and LLM_NARRATIVE_ENABLED=true are set in
    # .env; never raises (wrapped defensively both here and inside the
    # helper) so a narrative-generation failure can never break scoring.
    _finalize_result = _finalize_pre_results(
        _all_pre_results,
        payload_data,
        eff_strengths,
        house_lords,
        active_lord,
        peak_lord,
        _mrita_planets,
        _career_phase,
        current_age,
        ph,
        lagna_sign,
        ak,
        _antardasha_lord,
    )
    try:
        _top35_for_llm, _final_eff_strengths, _final_lagna_sign, _final_ak = _finalize_result
        _ctx["_all_pre_results"] = _top35_for_llm
        _ctx["eff_strengths"] = _final_eff_strengths
        _ctx["lagna_sign"] = _final_lagna_sign
        _ctx["ak"] = _final_ak
        from .llm import maybe_generate_scoring_context_narrative
        maybe_generate_scoring_context_narrative(payload_data, _ctx)
    except Exception as _narrative_exc:
        logger.info(f"Scoring context narrative step skipped/failed: {_narrative_exc}")

    return _finalize_result




from .engine_io import _load_course_registry
from .registry_result_enricher import attach_v12_registry_metadata

from dataclasses import dataclass, field as _dc_field


@dataclass
class FieldScoringAccumulator:
    """Stage B (2026-08-17): mechanical passthrough wrapper around the
    gap_boost / gap_penalty / gap_detail locals that _score_one_field()
    used to track as bare loop variables. add_boost()/add_penalty() are
    pure convenience wrappers for the ~145 simple/independent signal
    call sites; the handful of entangled sites (soul-stack cap,
    dasha-total cap, ak_primary_karaka, natho_delta, and a few other
    non-uniform penalty/detail writes) still poke gap_boost/gap_penalty/
    gap_detail directly via this object's attributes -- no formula, cap,
    or ordering was changed in this stage.
    """
    gap_boost: float = 0.0
    gap_penalty: float = 0.0
    gap_detail: dict = _dc_field(default_factory=dict)
    soul_stack_total: float = 0.0
    dasha_total: float = 0.0

    def add_boost(self, key, value, cap=None):
        v = value if cap is None else min(value, cap)
        self.gap_boost += v
        self.gap_detail[key] = round(v, 3)
        return v

    def add_penalty(self, key, value, cap=None):
        v = value if cap is None else min(value, cap)
        self.gap_penalty += v
        self.gap_detail[key] = round(-v, 3)
        return v

    def apply_soul_stack_cap(self, ceiling=0.26):
        """Stage C: LS13 soul-stack cap, extracted verbatim from the former
        inline block. Caps ak_amk + yogakaraka + ak_house at `ceiling` by
        clawing back the excess from `yogakaraka` (both in gap_detail and
        gap_boost). Stores the effective (post-cap) total on
        self.soul_stack_total for downstream reuse (e.g. ak_primary_karaka).
        """
        _soul_stack = (self.gap_detail.get("ak_amk", 0)
                       + self.gap_detail.get("yogakaraka", 0)
                       + self.gap_detail.get("ak_house", 0))
        if _soul_stack > ceiling:
            _ss_excess = _soul_stack - ceiling
            self.gap_boost -= _ss_excess
            self.gap_detail["yogakaraka"] = round(self.gap_detail.get("yogakaraka", 0) - _ss_excess, 3)
            self.gap_detail["_soul_stack_cap"] = round(-_ss_excess, 3)
            self.soul_stack_total = ceiling
        else:
            self.soul_stack_total = _soul_stack
        return self.soul_stack_total

    def apply_dasha_total_cap(self, ceiling=0.22):
        """Stage C: dasha-total cap, extracted verbatim from the former
        inline block. Caps dasha + prime_dasha_affinity + peak_md_boost at
        `ceiling` by clawing back the excess from `peak_md_boost` (both in
        gap_detail and gap_boost). Stores the effective (post-cap) total on
        self.dasha_total.

        NOTE: this cap only covers these 3 of ~7 dasha-family boost
        components; the rest (prd_boost, antardasha_affinity,
        ad_kendra_trikona, md_ad_compound) are independently capped
        elsewhere and are NOT bounded by `ceiling` here. Use
        apply_dasha_family_cap() below for the true combined ceiling
        across all dasha-timing components for a field.
        """
        _dasha_total = (self.gap_detail.get("dasha", 0)
                        + self.gap_detail.get("prime_dasha_affinity", 0)
                        + self.gap_detail.get("peak_md_boost", 0))
        if _dasha_total > ceiling:
            _excess = _dasha_total - ceiling
            self.gap_boost -= _excess
            self.gap_detail["peak_md_boost"] = round(self.gap_detail.get("peak_md_boost", 0) - _excess, 3)
            self.dasha_total = ceiling
        else:
            self.dasha_total = _dasha_total
        return self.dasha_total

    def apply_dasha_family_cap(self, ceiling=0.35):
        """2026-08-22 reconciliation (JyotishAI reference-audit method #2,
        owner-approved fix): apply_dasha_total_cap() above only bounds
        dasha + prime_dasha_affinity + peak_md_boost at 0.22, but four more
        dasha/period-timing components -- prd_boost (Pratyantardasha),
        antardasha_affinity, ad_kendra_trikona, and md_ad_compound -- each
        stack on top of that, independently capped only at the generic
        per-component _PCC (0.12) or smaller. Uncapped as a family, the
        worst-case combined dasha-timing contribution to one field could
        reach ~0.68, over 3x the documented 0.22 "total". This method must
        be called AFTER apply_dasha_total_cap() and after prd_boost /
        antardasha_affinity / ad_kendra_trikona / md_ad_compound have all
        been added, and bounds the true combined family total at `ceiling`,
        clawing back excess from md_ad_compound first (the least
        classically-grounded of the group -- an in-house "both lords agree"
        amplifier, not itself a distinct classical technique), then
        ad_kendra_trikona, then prd_boost, then antardasha_affinity, before
        ever touching the already-capped dasha_total from
        apply_dasha_total_cap(). `ceiling=0.35` preserves headroom above the
        0.22 base cap for a genuine MD+AD+Pratyantardasha convergence (real
        and meaningful) while eliminating the ~0.68 worst case. Stores the
        post-cap grand total on self.dasha_family_total.
        """
        _claw_order = ["md_ad_compound", "ad_kendra_trikona", "prd_boost", "antardasha_affinity"]
        _extra = sum(self.gap_detail.get(k, 0) for k in _claw_order)
        _family_total = self.dasha_total + _extra
        if _family_total > ceiling:
            _excess = _family_total - ceiling
            for k in _claw_order:
                if _excess <= 0:
                    break
                _v = self.gap_detail.get(k, 0)
                _take = min(_v, _excess)
                if _take > 0:
                    self.gap_boost -= _take
                    self.gap_detail[k] = round(_v - _take, 3)
                    _excess -= _take
            self.dasha_family_total = ceiling
        else:
            self.dasha_family_total = _family_total
        return self.dasha_family_total

    def apply_karakamsha_family_cap(self, ceiling=0.30):
        """2026-08-22 reconciliation (JyotishAI reference-audit method #3,
        owner-approved fix): four independent functions can each credit the
        same chart fact -- "this planet/sign is the Karakamsha (Navamsha
        seat of the Atmakaraka)" -- into the same field's score: karakamsha
        (sign-lord + node-co-lord affinity ramp), karakamsha_occ (occupant
        keyword match), karakamsha_domain (flat domain-keyword match), and
        chara_dasha (Jaimini timing signal referencing the Karakamsha sign).
        None of apply_soul_stack_cap/apply_dasha_total_cap/
        apply_dasha_family_cap reads any of these keys, and none of these
        four is bounded by any other cap -- worst case combined total is
        0.12+0.12+0.05+0.18 = 0.47 on one field, uncapped. Must be called
        after all four of the above have been added (they are added at
        different points across _score_one_field; call this once, after the
        last one -- chara_dasha -- has run). Clawback order starts with the
        least classically-grounded pieces (karakamsha_domain: a flat
        engineering heuristic with no classical citation; then
        karakamsha_occ: modern occupant-keyword convention) before touching
        chara_dasha (a genuine Jaimini timing technique) or karakamsha
        itself (the most classically-grounded of the four -- Karakamsha's
        core definition and its sign lord's significance are the
        best-sourced piece of this family; see reference-audit method #3
        notes). `ceiling=0.30` mirrors the soul-stack cap's magnitude
        (Karakamsha is a soul-lagna-tier signal, comparable to ak_amk/
        yogakaraka/ak_house) while remaining independent of it, since these
        are a structurally distinct set of boost keys. Stores the post-cap
        total on self.karakamsha_family_total.
        """
        _claw_order = ["karakamsha_domain", "karakamsha_occ", "chara_dasha", "karakamsha"]
        _family_total = sum(self.gap_detail.get(k, 0) for k in _claw_order)
        if _family_total > ceiling:
            _excess = _family_total - ceiling
            for k in _claw_order:
                if _excess <= 0:
                    break
                _v = self.gap_detail.get(k, 0)
                _take = min(_v, _excess)
                if _take > 0:
                    self.gap_boost -= _take
                    self.gap_detail[k] = round(_v - _take, 3)
                    _excess -= _take
            self.karakamsha_family_total = ceiling
        else:
            self.karakamsha_family_total = _family_total
        return self.karakamsha_family_total


def _score_one_field(
    *,
    # GAP-FIX (2026-08, structural-risk audit follow-up): this signature has
    # ~65 parameters, many sharing the same type (multiple Dict[str, str],
    # multiple Dict[str, float], multiple bare str) sitting side by side.
    # Positionally, a two-argument transposition at the single call site
    # (_run_normalization_stage's giant `_score_one_field(...)` invocation)
    # would silently miscompute every field's score rather than raise —
    # exactly the failure mode that stays invisible until someone notices a
    # chart's rankings look wrong. Making every parameter keyword-only (the
    # leading `*` below) converts that failure mode into an immediate
    # TypeError (missing/unexpected keyword argument) at the call site,
    # while changing nothing about which variable is used where inside the
    # function body — same names, same values, same order. This does not
    # by itself make the 65-parameter shape smaller (see run_engine's
    # comment thread / the architecture audit for the deeper dataclass
    # refactor option, deliberately not done here to keep this change
    # low-risk and mechanical).
    _fid,
    _fmeta,
    _DEFAULT_AFFINITY,
    _antardasha_lord,
    _argala_h10,
    _career_phase,
    _house_discrepant_planets,
    _kp_h10_star_lord,
    _mrita_planets,
    _transit_degrees,
    _transit_houses,
    _vb_ak,
    _vb_h10,
    _vimshopaka_d10_scale,
    _vimshopaka_d9_scale,
    _war_losers,
    active_lord,
    ak,
    already_excel,
    amk,
    amk_house,
    brahma_lord,
    cazimi_set,
    combust,
    current_age,
    d10_chart,
    d10_digs,
    d10_lagna,
    d9_chart,
    d9_digs,
    d9_lagna,
    digs,
    edu_eff_strengths,
    edu_planet_reasons,
    edu_ranked,
    eff_strengths,
    gender_val,
    h10_lord,
    h10_lp,
    h5_lord,
    house_lords,
    interested_in,
    kara_occ,
    karakamsha,
    lagna_lord,
    lagna_sign,
    maheshwara_lord,
    nb_set,
    peak_lord,
    ph,
    planet_trace,
    planets_d1,
    prd_houses,
    prd_lord,
    prime_career_lord,
    retro,
    risk,
    sav,
    shadbala,
    ul,
    vargottama,
    war_result,
    yogas,
    payload_data,
    _all_pre_results,
):
    branch_name = _fid
    label       = _fmeta.get("label", _fid.replace("_", " ").title())
    # Gap-18b (generalized fix, audit 2026-07): `label` above is the short
    # registry display label (e.g. "Political Science") -- kept exactly as-is
    # for display/output/LLM-prompt purposes ("field_label" in the result row,
    # etc). `_gate_text` is a SEPARATE, richer blob (field_id + label + the
    # registry's track/specialization/niche/description) used ONLY as the
    # input to the ~60 keyword-gate bonus/penalty functions below whose sole
    # use of their text argument is _wm()/substring keyword matching against
    # hardcoded lists (confirmed function-by-function; see
    # DEEP_AUDIT_GAPS_2026-07.md item 11 / Gap-18b). Using `_gate_text` there
    # instead of the bare `label` lets those gates fire on a field's fuller
    # descriptive vocabulary (e.g. international_relations's niche mentions
    # "diplomacy"/"foreign policy") instead of only its short title -- the
    # same reachability fix already applied to the 5 method scorers and
    # _confluence_gate, extended here to the rest of the acc.gap_boost stage.
    # A handful of functions take `label` but never use it for keyword
    # matching (e.g. _d9_ak_delta, _gender_field_modifier,
    # _d10_comprehensive_bonus, _confidence_convergence_grade,
    # _kemadruma_yoga_penalty, _d30_trimsamsha_obstacle_check,
    # compute_branch_affinity_score_llm) -- those call sites intentionally
    # still pass `label` (unchanged, harmless either way since it's unused).
    _gate_text  = build_gate_text(branch_name, _fmeta)
    domain      = _fmeta.get("domain", "interdisciplinary").strip().lower()
    if domain not in _VALID_DOMAINS:
        domain = "interdisciplinary"

    hard_affinity = BRANCH_PLANET_AFFINITY.get(_fid, _DEFAULT_AFFINITY)
    # S1: House Boundary Discrepancy Dampener
    if _house_discrepant_planets:
        hard_affinity = {
            p: (v * 0.80 if p in _house_discrepant_planets else v)
            for p, v in hard_affinity.items()
        }
    # P1: Career Phase Modifier
    hard_affinity = _apply_career_phase_modifier(hard_affinity, house_lords, _career_phase)
    # Structural impairment
    hard_affinity = _apply_structural_impairment(hard_affinity, _war_losers, _mrita_planets)
    llm_affinity      = hard_affinity
    llm_astro_reason  = ""
    llm_sel_rationale = ""

    _eff_for_scoring = getattr(payload_data, "eff_strengths_war_adjusted", None) or eff_strengths
    if ak and hard_affinity:
        _ak_top_k = max(hard_affinity.items(), key=lambda x: x[1])[0]
        if _ak_top_k == ak and eff_strengths.get(ak, 1.0) < 1.0:
            _eff_for_scoring = dict(eff_strengths)
            _eff_for_scoring[ak] = 1.0

    affinity_result = compute_branch_affinity_score_llm(
        branch_name, label, domain, hard_affinity, _eff_for_scoring)
    # LS9 fix: apply Vargottama uplift (+6%) if top affinity planet is Vargottama
    affinity_result = apply_vargottama_affinity_uplift(
        affinity_result, hard_affinity, vargottama)
    aff = affinity_result["affinity_planets"]

    aptitudes = compute_aptitude_by_domain(domain, shadbala, sav, _eff_for_scoring,
                                           hard_affinity, field_id=_fid, payload=payload_data)
    _apt_supplement = _chart_specific_aptitude_supplement(
        domain, h5_lord, lagna_lord, h10_lord, eff_strengths)
    aptitudes["composite_score"] = min(aptitudes["composite_score"] + _apt_supplement, 200)
    if aptitudes["composite_score"] >= aptitudes["threshold_required"]:
        aptitudes["meets_threshold"] = True

    composite_norm = _log_norm_score(aptitudes["composite_score"], _COMPOSITE_SOFT_CAP)
    affinity_norm  = _log_norm_score(affinity_result["affinity_score"], _AFFINITY_SOFT_CAP)

    # Gap-8 fix: document the blend weight switching logic.
    # Blend = domain_blend × composite_norm + affinity_blend × affinity_norm.
    # DEFAULT (most fields):          domain_blend=0.60, affinity_blend=0.40
    #   → composite (Shadbala + Sav) drives 60% of blended score.
    # ADVANCED-TECH / STRONG-PLANET:  domain_blend=0.45, affinity_blend=0.55
    #   → triggered when ANY affinity planet weight ≥ 0.35 (clear vocational mandate)
    #     OR Rahu+Mercury combined weight > 0.45 (technology/analytics node).
    #   → rationale: a dominant single-planet signature should steer field ranking
    #     more than Shadbala overall, because specialised aptitude often shows through
    #     the karaka before it shows through house strength.
    # This switch is logged in calc_trace.normalization under domain_blend_weight /
    # affinity_blend_weight so it appears in the LLM debug output for each field.
    # T3-E: Domain-aware w1/w2 blend weights.
    # Structure-driven domains (engineering/medicine/law) → deterministic method score leads.
    # Culturally-determined domains (arts/humanities) → affinity leads.
    # R3 fix: use only the 13 real registry domains.
    # "defence","surgery","forensics","architecture","ca_cma","chartered","dentistry",
    # "pharmacy" are field-ids/labels, not domain names in the registry.
    # "music","film","performing","fine_arts","spirituality","alternative","yoga",
    # "fashion","design","creative" likewise — all live under "arts" or "humanities".
    _STRUCT_DOMAINS   = {"engineering", "medicine", "law", "technology", "science"}
    _AFFINITY_DOMAINS = {"arts", "humanities", "media"}
    _is_struct   = any(d in domain for d in _STRUCT_DOMAINS)
    _is_cultural = any(d in domain for d in _AFFINITY_DOMAINS)

    if hard_affinity:
        max_vector_weight = max(hard_affinity.values())
        is_advanced_tech_node = (hard_affinity.get("Rahu", 0.0) + hard_affinity.get("Mercury", 0.0)) > 0.45
        if _is_struct:
            # Structure-driven: method score dominates
            current_domain_blend   = 0.65
            current_affinity_blend = 0.35
        elif _is_cultural:
            # Culturally-determined: affinity leads
            current_domain_blend   = 0.40
            current_affinity_blend = 0.60
        elif max_vector_weight >= 0.35 or is_advanced_tech_node:
            current_affinity_blend = 0.55
            current_domain_blend   = 0.45
        else:
            current_affinity_blend = 0.40
            current_domain_blend   = 0.60
    else:
        current_affinity_blend = 0.40
        current_domain_blend   = 0.60

    # Q5: AK/AmK Dynamic Blend Tilt.
    # When the soul-significator (AK) is dramatically stronger than the career-execution
    # significator (AmK), the native prioritises personal identity alignment over
    # market-structural fit. Tilt the blend toward affinity by up to +0.15.
    # Cap: affinity_blend never exceeds 0.75 (domain blend cannot drop below 0.25).
    if ak and amk and ak != amk:
        _ak_eff  = eff_strengths.get(ak,  1.0)
        _amk_eff = eff_strengths.get(amk, 1.0)
        if _amk_eff > 0 and (_ak_eff / _amk_eff) >= 1.5:
            _ratio = min((_ak_eff / _amk_eff) - 1.5, 1.0)  # 0–1 scale
            _ak_tilt = round(_ratio * 0.15, 3)              # max +0.15
            current_affinity_blend = min(current_affinity_blend + _ak_tilt, 0.75)
            current_domain_blend   = max(current_domain_blend   - _ak_tilt, 0.25)

    blended = (current_domain_blend * composite_norm) + (current_affinity_blend * affinity_norm)


    acc = FieldScoringAccumulator()
    # PROVENANCE (2026-07, transparency): (B) ENGINEERED. _PCC ("per-
    # component cap") bounds how much any single gap-boost signal below
    # (yoga match, karaka placement, nakshatra fit, etc.) can move a
    # field's score. 0.12 is this codebase's own tuning choice to keep
    # ~70 individual signals from any one of them dominating the total --
    # it is not a value derived from a classical text. See this module's
    # docstring and constants.py's top-of-file provenance note for the
    # general (A) classical / (B) engineered distinction this codebase
    # now documents. _D10_PCC below (0.16) is the same kind of constant,
    # deliberately set higher than _PCC because D10 is BPHS's own
    # dedicated career varga and this codebase's maintainers judged it
    # should carry more weight than a single generic signal -- again, an
    # engineering judgment about relative signal weighting, not a
    # classically-prescribed number.
    _PCC = 0.12
    _top_karaka = max(hard_affinity.items(), key=lambda x: x[1])[0] if hard_affinity else ""

    if ak and hard_affinity:
        if _top_karaka == ak:       _ak_b = 0.12
        elif aff.get(ak, 0) >= 0.15: _ak_b = 0.03
        else:                         _ak_b = 0.0
    else:
        _ak_b = 0.0
    if amk and hard_affinity:
        if _top_karaka == amk:        _amk_b = 0.08
        elif aff.get(amk, 0) >= 0.10: _amk_b = 0.02
        else:                          _amk_b = 0.0
    else:
        _amk_b = 0.0
    b = min(_ak_b + _amk_b, _PCC); acc.add_boost("ak_amk", b)

    # AK Soul-Domain Mandate (fixes S101/S102/S104/S136/S140/S141/S146/S158/S165/
    # S170/S173/S194/S196/S210/S219/S222/S233/S254/S266/S287/S341 and related):
    # The Atmakaraka establishes a PRIMARY domain through its karakattva (natural
    # signification). Classical rule: AK's domain MUST appear in top-5 regardless
    # of planetary interplay. A field in the AK's domain that has ANY affinity for
    # the AK planet gets a mandate boost proportional to vitality × field alignment.
    # Combust/war-loser AK: vitality floored at 0.35 so domain is weakened but present.
    # R3 fix: registry uses 13 real domains — map Sun/Mars/Rahu/Ketu to them.
    # Dead keys removed: "government","civil_services","defence","foreign","research"
    # civil_services/defence_military → "public"; fashion_design etc → "arts"
    _AK_PRIME_DOMAINS = {
        "Venus":   ("arts", "media"),
        "Moon":    ("medicine", "humanities"),
        "Jupiter": ("law", "education"),
        "Sun":     ("public", "interdisciplinary"),   # civil_services/IAS/IPS are domain="public"
        "Mars":    ("engineering", "public"),          # defence_military is domain="public"
        "Mercury": ("technology", "science"),
        "Saturn":  ("engineering", "commerce"),
        "Rahu":    ("technology", "media", "interdisciplinary"),  # "foreign" not a real domain
        "Ketu":    ("science", "medicine"),            # "research" not a real domain
    }
    _ak_prime = _AK_PRIME_DOMAINS.get(ak, ())
    if ak and _ak_prime and domain in _ak_prime:
        _ak_field_aff  = aff.get(ak, 0.0)
        # Debilitated AK has no soul-mandate: the soul's domain purpose is
        # compromised and cannot override field ranking.
        _ak_is_debilitated = digs.get(ak, "") == "DEBILITATED"
        if _ak_field_aff >= 0.05 and not _ak_is_debilitated:
            # Gap-16 (audit 2026-07) note: eff_strengths is UNBOUNDED above
            # (relative to the chart's weakest planet; observed values >2.0),
            # not 0.0-1.35 as previously documented. The min() caps below
            # protect against runaway mandates.
            _ak_mandate_vit = max(eff_strengths.get(ak, 1.0), 0.35)
            _ak_field_rel   = min(_ak_field_aff * 2.5, 1.0)  # 0–0.40 affinity → 0–1.0
            _ak_mandate_b   = min(0.10 * _ak_mandate_vit * _ak_field_rel, 0.10)
            if _ak_mandate_b > 0.005:
                acc.add_boost("ak_soul_mandate", _ak_mandate_b)

    # Malavya Yoga arts mandate (S185, S186):
    # When Venus is in own/exalted sign in a kendra (classical Panchamahapurusha yoga),
    # arts/media fields must appear in top-3. Add a domain mandate that exceeds the
    # field-specific AK bonus for arts fields.
    _malavya_active = any(
        y.lower() in ("malavya", "malavya yoga")
        for y in list(yogas or []) + list(getattr(payload_data, "yogas_present", []) or [])
    )
    if not _malavya_active:
        # Detect Malavya directly from planets_d1 if not in yoga list
        _ven_sign = (planets_d1.get("Venus") or {}).get("sign", "")
        _ven_house = ph.get("Venus", 0)
        _ven_dig   = digs.get("Venus", "")
        if _ven_house in (1, 4, 7, 10) and _ven_dig in ("EXALTED", "OWN", "MOOLATRIKONA", "exalted", "own"):
            _malavya_active = True
    # Malavya mandate only fires when AK is arts-aligned (Venus/Moon).
    # When AK is Mars/Saturn/Mercury/Sun, the soul mandate for
    # engineering/technology overrides Malavya's arts pull.
    if _malavya_active and domain in ("arts", "media") and aff.get("Venus", 0.0) >= 0.05 \
            and ak in ("Venus", "Moon", ""):
        _maly_vit = max(eff_strengths.get("Venus", 1.0), 0.5)
        _maly_b   = min(0.10 * _maly_vit * min(aff.get("Venus", 0.0) * 3.0, 1.0), 0.10)
        if _maly_b > 0.005:
            acc.add_boost("malavya_arts_mandate", _maly_b)

    b = min(_stellium_bonus(_gate_text, ph), _PCC); acc.add_boost("stellium", b)
    # AC1 fix: Argala H10 career activation
    _top_aff_planet = max(hard_affinity.items(), key=lambda x: x[1])[0] if hard_affinity else ""
    if _top_aff_planet and _top_aff_planet in _argala_h10:
        _argala_b = min(0.06 * aff.get(_top_aff_planet, 0.1) * 5, 0.06)
        acc.add_boost("argala_h10", _argala_b)
    elif _top_aff_planet:
        # Virodha Argala: 12th (H9), 10th (H7), 3rd (H12) from H10 obstruct career.
        # H2 fix: previously only H9 was penalized; now all three positions are checked.
        _virodha_houses = {9, 7, 12}  # 12th/10th/3rd from H10
        if ph.get(_top_aff_planet, 0) in _virodha_houses:
            acc.add_penalty("virodha_argala", 0.03)
    b = min(_dasha_bonus(_gate_text, payload_data), _PCC); acc.add_boost("dasha", b)
    b = min(_karakamsha_bonus(aff, karakamsha), _PCC); acc.add_boost("karakamsha", b)
    b = min(_d24_ak_delta(_gate_text, payload_data), _PCC); acc.add_boost("d24_ak", b)
    b = min(_d24_full_chart_bonus(aff, payload_data), _PCC); acc.add_boost("d24_full", b)
    b = min(_lagna_lord_bonus(_gate_text, payload_data), _PCC); acc.add_boost("lagna_lord", b)
    _risk_b = _risk_appetite_bonus(_gate_text, risk)
    if _risk_b >= 0:
        acc.gap_boost += min(_risk_b, _PCC)
    else:
        acc.gap_penalty += abs(_risk_b)
    acc.gap_detail["risk_appetite"] = round(_risk_b, 3)
    b = _modernize_karakas_modifier(_fid, risk, amk, _kp_h10_star_lord, planets_d1)
    acc.add_boost("modernize_karakas", b)
    b = min(_yogakaraka_bonus(aff, lagna_sign, shadbala, digs), _PCC)
    acc.add_boost("yogakaraka", b)
    # LS3 fix: debilitated yogakaraka penalty → acc.gap_penalty (not negative acc.gap_boost)
    _yk_pen = _yogakaraka_debilitation_penalty(aff, lagna_sign, shadbala, digs)
    if _yk_pen > 0: acc.add_penalty("yogakaraka_deb_pen", _yk_pen)
    b = min(_h10_lord_strength_bonus(aff, h10_lp, shadbala, digs), _PCC); acc.add_boost("h10_lord_str", b)
    b = min(_h10_lord_trikona_bonus(aff, h10_lp, ph, digs), _PCC); acc.add_boost("h10_lord_trikona", b)
    b = min(_exalted_planet_domain_bonus(aff, digs, _gate_text, lagna_sign), _PCC); acc.add_boost("exalted_domain", b)
    b = min(_ul_lord_bonus(aff, ul), _PCC); acc.add_boost("ul_lord", b)
    # _d9_ak_delta's `label` param is unused inside the function (pure D9-dignity
    # scoring, no keyword matching) -- intentionally left as `label` (Gap-18b audit).
    b = min(_d9_ak_delta(label, payload_data), _PCC); acc.add_boost("d9_ak", b)
    b = min(_yoga_bonus(_gate_text, yogas, house_lords, digs), _PCC); acc.add_boost("yoga", b)
    b = min(_h5_lord_bonus(aff, h5_lord), _PCC); acc.add_boost("h5_lord", b)
    b = min(_amk_house_bonus(_gate_text, amk_house), _PCC); acc.add_boost("amk_house", b)
    b = min(_ak_house_bonus(ak, ph.get(ak, 0), _gate_text), _PCC); acc.add_boost("ak_house", b)

    # LS13 fix: soul-stack cap = 0.26 → max soul-domain acc.gap_boost contribution.
    # Rationale: on a 75-blended field, 0.26 × 0.76 _base_weight ≈ +20 display pts.
    # Prevents AK/yogakaraka pile-on from overriding multi-method scoring.
    acc.apply_soul_stack_cap(ceiling=0.26)

    # Engineering domain mandate when Mars is BOTH AK and YK:
    # The soul purpose (AK=Mars→engineering) and the lagna's most benefic planet
    # (YK=Mars) doubly direct toward technical vocation. Engineering fields receive
    # an extra mandate that is NOT subject to the soul_stack cap (it's a domain
    # gate, not an AK/YK pile-on). Only fires when YK has already triggered
    # (acc.gap_detail["yogakaraka"] > 0) so it's lagna-specific, not universal.
    if (domain == "engineering" and ak == "Mars"
            and acc.gap_detail.get("yogakaraka", 0) > 0
            and digs.get("Mars", "") not in ("DEBILITATED",)):
        # Scale mandate by Mars dignity: EXALTED/OWN Mars makes engineering even more dominant
        _mars_dig_for_eng = digs.get("Mars", "")
        _eng_dig_scale = 1.5 if _mars_dig_for_eng == "EXALTED" else (1.2 if _mars_dig_for_eng == "OWN" else 1.0)
        _eng_yk_cap = 0.07 * _eng_dig_scale
        _eng_yk_man = min(_eng_dig_scale * 0.07 * max(eff_strengths.get("Mars", 1.0), 0.5), _eng_yk_cap)
        acc.add_boost("engineering_yk_mandate", _eng_yk_man)

    # H1 fix: when peak_lord == prime_career_lord the native is currently in their peak
    # career dasha — _peak_career_dasha_boost already captures this at full strength.
    # Skip _dasha_active_affinity_boost for that lord to prevent double-counting.
    if prime_career_lord != peak_lord:
        b = min(_dasha_active_affinity_boost(aff, prime_career_lord, digs), _PCC); acc.add_boost("prime_dasha_affinity", b)
    else:
        acc.gap_detail["prime_dasha_affinity"] = 0.0  # deduped: peak==active, peak_md_boost covers it
    b = min(_peak_career_dasha_boost(aff, peak_lord, prime_career_lord, digs), _PCC); acc.add_boost("peak_md_boost", b)
    acc.apply_dasha_total_cap(ceiling=0.22)

    b = min(_pratyantar_dasha_bonus(_gate_text, prd_lord, prd_houses), _PCC); acc.add_boost("prd_boost", b)
    # AC2 fix: antardasha lord domain boost (half weight of main dasha)
    if _antardasha_lord and _antardasha_lord in aff and _antardasha_lord != prime_career_lord:
        _ad_w   = aff.get(_antardasha_lord, 0.0)
        _ad_dig = digs.get(_antardasha_lord, "")
        _ad_dig_scale = {"EXALTED": 1.40, "OWN": 1.15, "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.60}.get(_ad_dig, 1.0)
        _ad_b = min(_ad_w * _ad_dig_scale * 0.06, _PCC * 0.5)
        if _ad_b > 0:
            acc.add_boost("antardasha_affinity", _ad_b)
        # N4: AD lord in kendra/trikona → can deliver its promise (classical rule)
        _ad_house = ph.get(_antardasha_lord, 0)
        if _ad_house in (1, 4, 5, 7, 9, 10) and _ad_b > 0:
            _ad_delivery_b = min(_ad_b * 0.30, _PCC * 0.15)
            acc.add_boost("ad_kendra_trikona", _ad_delivery_b)
    # T1-E: MD × AD compound — when BOTH Mahadasha and Antardasha lords match field keywords,
    # career events crystallise with high reliability. Apply 35% bonus on existing dasha total.
    _md_kw_match = active_lord and any(_wm(kw, _gate_text) for kw in DASHA_KEYWORDS.get(active_lord, []))
    _ad_kw_match = _antardasha_lord and any(_wm(kw, _gate_text) for kw in DASHA_KEYWORDS.get(_antardasha_lord, []))
    if _md_kw_match and _ad_kw_match:
        _dasha_so_far = (acc.gap_detail.get("dasha", 0) + acc.gap_detail.get("prime_dasha_affinity", 0)
                         + acc.gap_detail.get("antardasha_affinity", 0))
        _compound_b = min(_dasha_so_far * 0.35, _PCC)
        if _compound_b > 0.005:
            acc.add_boost("md_ad_compound", _compound_b)
    # 2026-08-22 reconciliation (JyotishAI reference-audit method #2): bound
    # the true combined dasha-family total (all 7 components) at 0.35 --
    # apply_dasha_total_cap() above only bounds 3 of the 7. See
    # apply_dasha_family_cap()'s docstring for the clawback order/rationale.
    acc.apply_dasha_family_cap(ceiling=0.35)
    # AC5 fix: Rahu career signal — H10/H6 (upachaya) placement with strong STEM affinity
    _rahu_h = ph.get("Rahu", 0)
    if _rahu_h in (10, 6) and aff.get("Rahu", 0) >= 0.25:
        _rahu_b = min(0.06, aff["Rahu"] * 0.20)
        acc.add_boost("rahu_career_h10h6", _rahu_b)
    # AC5 fix: Ketu career signal — H9/H5 placement with research/mystical affinity
    _ketu_h = ph.get("Ketu", 0)
    _ketu_research_lbl = any(_wm(kw, _gate_text) for kw in
        ["research", "mathematics", "forensic", "philosophy", "archaeology", "ayurveda"])
    if _ketu_h in (9, 5) and _ketu_research_lbl and aff.get("Ketu", 0) >= 0.20:
        _ketu_b = min(0.05, aff["Ketu"] * 0.18)
        acc.add_boost("ketu_research_h9h5", _ketu_b)

    # AC15 fix: Nathonnatha temporal strength (diurnal/nocturnal birth)
    # Planets gain strength when born in their temporal period.
    # Diurnal planets: Sun, Jupiter, Saturn — strong if birth_hour in 6..18
    # Nocturnal planets: Moon, Venus, Mars — strong if birth_hour in 18..24 or 0..6
    # Mercury: neutral (strong in both). Rahu/Ketu excluded.
    try:
        _bh_raw = getattr(payload_data, 'birth_time_hour', None)
        _bh = float(_bh_raw) if _bh_raw is not None else -1.0
        if _bh < 0:
            _bt = str(getattr(payload_data, 'birth_time', '') or '')
            if ':' in _bt:
                _bh = float(_bt.split(':')[0]) + float(_bt.split(':')[1]) / 60
    except Exception:
        _bh = -1.0
    if _bh >= 0:
        _is_day = 6 <= _bh < 18
        _DIURNAL_P  = {'Sun', 'Jupiter', 'Saturn'}
        _NOCTURNAL_P = {'Moon', 'Venus', 'Mars'}
        _top_aff_planet = max(aff.items(), key=lambda x: x[1])[0] if aff else ''
        _natho_mult = 1.0
        if _is_day and _top_aff_planet in _DIURNAL_P:
            _natho_mult = 1.08  # diurnal planet in day chart → 8% uplift
        elif not _is_day and _top_aff_planet in _NOCTURNAL_P:
            _natho_mult = 1.08  # nocturnal planet in night chart → 8% uplift
        elif _is_day and _top_aff_planet in _NOCTURNAL_P:
            _natho_mult = 0.96  # nocturnal planet in day chart → slight debuff
        elif not _is_day and _top_aff_planet in _DIURNAL_P:
            _natho_mult = 0.96
        if _natho_mult != 1.0:
            # GAP-FIX (2026-08, astrological audit): Nathonnatha Bala is a
            # per-planet Shadbala component — a diurnal/nocturnal fact about
            # ONE planet (the field's top-affinity planet here). The delta
            # previously scaled the ENTIRE accumulated `acc.gap_boost`
            # (`acc.gap_boost * (_natho_mult - 1.0)`), which by this point is
            # an aggregate of dozens of unrelated signals (yoga, dasha,
            # nakshatra, argala, etc.) — so a day/night fact about one planet
            # was incorrectly rescaling boosts that have nothing to do with
            # that planet's own strength, with magnitude that grew or shrank
            # based on how much unrelated signal happened to already be
            # accumulated. The delta is now scaled instead by that planet's
            # OWN affinity weight for this field (0..~1), so its magnitude
            # reflects how much this specific planet actually matters to the
            # field being scored, not the size of unrelated accumulated boosts.
            _natho_weight = min(max(aff.get(_top_aff_planet, 0.5), 0.0), 1.0)
            _natho_delta = (0.04 if _natho_mult > 1.0 else -0.04) * _natho_weight
            acc.gap_boost += _natho_delta
            if abs(_natho_delta) >= 0.005:
                acc.gap_detail['nathonnatha'] = round(_natho_delta, 3)

    # P2: Panchanga career signal — Vara + Tithi lord confirmation.
    # Vara lord (weekday) and Tithi lord both confirm career domain at birth.
    # Triple confirmation (vara + tithi + nakshatra lord all match) is a very
    # strong classical signal (Panchanga Shuddhi / Panchanga Bala).
    _DAY_TO_PLANET = {'Monday':'Moon','Tuesday':'Mars','Wednesday':'Mercury',
                      'Thursday':'Jupiter','Friday':'Venus','Saturday':'Saturn','Sunday':'Sun'}
    # Tithi lords cycle: 1=Sun,2=Moon,3=Mars,4=Mercury,5=Jupiter,6=Venus,7=Saturn (repeating)
    _TITHI_LORD_SEQ = ['Sun','Moon','Mars','Mercury','Jupiter','Venus','Saturn']
    _birth_weekday = getattr(payload_data, 'birth_weekday', '') or ''
    if not _birth_weekday:
        try:
            import datetime as _dt
            _bdate = getattr(payload_data, 'birth_date', '') or ''
            if _bdate:
                _WEEKDAY_NAMES = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
                _birth_weekday = _WEEKDAY_NAMES[_dt.date.fromisoformat(str(_bdate)[:10]).weekday()]
        except Exception:
            _birth_weekday = ''
    _vara_planet = _DAY_TO_PLANET.get(_birth_weekday, '')
    _tithi_num   = int(getattr(payload_data, 'birth_tithi_num', 0) or 0)
    _tithi_planet = _TITHI_LORD_SEQ[(_tithi_num - 1) % 7] if 1 <= _tithi_num <= 30 else ''
    _panch_matches = []
    for _pp in (_vara_planet, _tithi_planet):
        if _pp and aff.get(_pp, 0.0) >= 0.15:
            _panch_matches.append(_pp)
    if _panch_matches:
        _panch_base = sum(aff.get(p, 0.0) for p in _panch_matches) / len(_panch_matches)
        _panch_mult = 1.5 if len(_panch_matches) == 2 else 1.0  # double confirmation = bonus
        _panch_b = min(_panch_base * 0.08 * _panch_mult, 0.06)
        if _panch_b > 0.005:
            acc.add_boost('panchanga_lord', _panch_b)

    # GAP-FIX (2026-08, ranking-impact audit): Rikta Tithi (classically
    # inauspicious lunar days -- Chaturthi/Navami/Chaturdashi, tithis
    # 4/9/14/19/24/29) previously had a correct classification table
    # (_MALEFIC_TITHIS in panchang.py) that no scoring function ever
    # consumed -- panchang.py's compute_panchang()/tithi_malefic output was
    # entirely unwired from this engine, and the panchanga_lord boost above
    # is a separate inline tithi-LORD computation that doesn't check
    # tithi-quality at all. Wire in a small, capped birth-tithi malus so a
    # Rikta-tithi birth applies a mild dampening to the tithi-lord's own
    # domain confirmation, consistent with classical Panchanga Shuddhi
    # doctrine (an inauspicious tithi weakens, but does not negate, that
    # day's planetary confirmation).
    if _tithi_num and _tithi_num in _MALEFIC_TITHIS and _tithi_planet:
        _rikta_w = aff.get(_tithi_planet, 0.0)
        if _rikta_w >= 0.15:
            _rikta_malus = -min(0.03, _rikta_w * 0.06)
            acc.add_boost('rikta_tithi', _rikta_malus)

    # Q3: H8/H6 structural gate for Medicine and Defence domains.
    # Classical doctrine: a surgeon needs H8 (crisis/transformation) vitality;
    # a soldier/lawyer needs H6 (conflict/service/litigation) vitality.
    # A strong D1+D10 H10 is insufficient if the operational houses are inert.
    if domain == "medicine":
        _h8_lord_m = house_lords.get("8", "") or house_lords.get(8, "")
        if _h8_lord_m:
            _h8_vit = eff_strengths.get(_h8_lord_m, 1.0)
            if _h8_vit < 0.50:
                # H8 lord severely impaired — surgical/crisis capacity weakened
                _h8_penalty = min((0.50 - _h8_vit) * 0.20, 0.08)
                acc.add_penalty("h8_medicine_gate", _h8_penalty)
            elif _h8_vit >= 1.10:
                # Exceptionally strong H8 lord — add a bonus
                _h8_bonus = min((_h8_vit - 1.10) * 0.10, 0.04)
                acc.add_boost("h8_medicine_gate", _h8_bonus)
    elif domain in ("public", "law"):   # R3 fix: "defence" → "public" (real domain)
        _h6_lord_d = house_lords.get("6", "") or house_lords.get(6, "")
        if _h6_lord_d:
            _h6_vit = eff_strengths.get(_h6_lord_d, 1.0)
            if _h6_vit < 0.45:
                # H6 lord impaired — conflict/service capacity weakened
                _h6_penalty = min((0.45 - _h6_vit) * 0.18, 0.06)
                acc.add_penalty("h6_defence_gate", _h6_penalty)
            elif _h6_vit >= 1.10:
                _h6_bonus = min((_h6_vit - 1.10) * 0.08, 0.04)
                acc.add_boost("h6_defence_gate", _h6_bonus)

    b = min(_karakamsha_occupant_bonus(_gate_text, kara_occ, shadbala), _PCC); acc.add_boost("karakamsha_occ", b)
    # GAP-FIX (2026-07): cap now scaled by AK's classical Vimshopaka Bala
    # (Dasavarga) fraction instead of the flat, unexplained _PCC constant.
    b = min(_d9_h10_bonus(aff, d9_chart, d9_lagna), _PCC * _vimshopaka_d9_scale); acc.add_boost("d9_h10", b)
    acc.gap_detail["vimshopaka_ak_pct"] = _vb_ak.get("pct", 0.0)
    b = min(_dharma_karma_bonus(aff, house_lords, ph), _PCC); acc.add_boost("dharma_karma", b)
    b = min(_interest_preference_boost(_gate_text, interested_in, already_excel), _PCC); acc.add_boost("interest_pref", b)
    b = min(_brahma_lord_bonus(_gate_text, brahma_lord, aff), _PCC); acc.add_boost("brahma_lord", b)
    # Consolidation fix: pass the shared d10_house_occupancy so this reads
    # the same "who occupies D10 H10" fact as kp.py/knrao.py/parashara.py
    # instead of an independent recomputation from d10_chart.
    # 2026-07 engine-gap audit fix (Phase 2, D10 primacy): the Dashamsha is
    # BPHS's own dedicated career varga -- classically it should out-rank a
    # keyword-matched flat supplement, not sit behind it. These two D10 gap-
    # boost components previously shared the same generic _PCC=0.12 per-
    # component cap as every other bonus (gender modifier, brahma-lord
    # keyword match, etc.), which is why a genuine D10 kendra/lagna-lord
    # placement couldn't out-weigh a flat AK-keyword hit. Given their own
    # dedicated cap (_D10_PCC), used ONLY for these two D10-specific
    # bonuses so D10-level testimony gets more scoring headroom than a
    # generic single-signal bonus, without being unbounded.
    _D10_PCC = 0.16
    # GAP-FIX (2026-07): cap now additionally scaled by the H10 lord's
    # classical Vimshopaka Bala (Dasavarga) fraction -- grounding the
    # dedicated D10 headroom in a standardized weighting scheme rather
    # than the flat constant alone (which is kept as the base/ceiling).
    _d10_pcc_scaled = _D10_PCC * _vimshopaka_d10_scale
    b = min(_d10_h10_bonus(aff, d10_chart, d10_lagna, d10_digs,
                            d10_occupancy=getattr(payload_data, "d10_house_occupancy", None)),
            _d10_pcc_scaled)
    acc.add_boost("d10_h10", b)
    b = min(_d10_lagna_lord_bonus(aff, d10_chart, d10_lagna, d10_digs), _d10_pcc_scaled); acc.add_boost("d10_lagna_lord", b)
    acc.gap_detail["vimshopaka_h10_lord_pct"] = _vb_h10.get("pct", 0.0)
    # _gender_field_modifier's `label` param is unused inside the function (pure
    # Venus-house-lordship logic, no keyword matching) -- intentionally left as
    # `label`, not `_gate_text` (Gap-18b audit).
    b = _gender_field_modifier(label, gender_val, aff, house_lords); acc.add_boost("gender_field", b)
    b = min(_aspect_h10_bonus(aff, ph, digs, planets_d1=getattr(payload_data, "planets_d1", None)), _PCC)
    acc.add_boost("aspect_h10", b)
    b = min(_maheshwara_lord_bonus(_gate_text, maheshwara_lord, aff), _PCC); acc.add_boost("maheshwara", b)
    b = min(_bhavesha_phala_edu_bonus(_gate_text, aff, house_lords, ph), _PCC); acc.add_boost("bhavesha_phala", b)
    # Mars/Sun/Saturn AK: skip label-keyword boost for humanities fields.
    # These planets' soul mandate is engineering/defence/civil service (active vocation),
    # not academic study of those topics — humanities classification signals mismatch.
    _ak_hum_gate = (domain == "humanities" and ak in ("Mars", "Sun", "Saturn"))
    # Debilitated AK: soul mandate is compromised; skip label-keyword domain boost.
    _ak_debil = digs.get(ak, "") == "DEBILITATED"
    # Mars AK label-keyword gate: prevent fields with "engineering" in their label
    # from getting Mars keyword boost when they're not actually engineering-domain.
    # (e.g. "Data Science & Engineering", "Computational Finance & Financial Engineering")
    _lbl_lower = _gate_text.lower()
    _mars_nondomain_gate = (
        ak == "Mars"
        and domain not in ("engineering", "public")
        and not any(_wm(kw, _lbl_lower) for kw in (
            "defence", "military", "surgery", "aerospace",
            "mechanical", "electrical", "manufacturing"))
    )
    # When AK is debilitated, zero its contribution but keep AmK active (pass "" for ak).
    _eff_ak_boost = "" if _ak_debil else ak
    b = 0.0 if (_ak_hum_gate or _mars_nondomain_gate) else min(_ak_planet_domain_boost(_gate_text, _eff_ak_boost, digs.get(ak, ""), ph, amk, digs.get(amk, "")), 0.20)
    acc.add_boost("ak_planet_domain", b)
    b = min(_karakamsha_domain_boost(_gate_text, domain, karakamsha), _PCC); acc.add_boost("karakamsha_domain", b)
    b = min(_h3_lord_communication_boost(_gate_text, domain, house_lords, eff_strengths, ph), _PCC); acc.add_boost("h3_comm", b)
    b = _h12_stellium_penalty(_gate_text, domain, ph); acc.add_boost("h12_stellium_pen", b)
    # ── 10/10 upgrade: 15 astrological signal blocks ──────────────────────────
    # Fix 1: Nakshatra-axis career rulership
    _moon_nak  = getattr(payload_data, "moon_nakshatra", "") or ""
    _pl_naks   = getattr(payload_data, "planet_nakshatras", {}) or {}
    b = min(_nakshatra_career_score(aff, _moon_nak, _pl_naks, house_lords, lagna_sign, _gate_text), _PCC)
    acc.add_boost("nakshatra_career", b)

    # Fix 2: Rahu-Ketu nodal axis as life-direction indicator
    _rahu_h = getattr(payload_data, "rahu_house", 0) or ph.get("Rahu", 0)
    _ketu_h = getattr(payload_data, "ketu_house", 0) or ph.get("Ketu", 0)
    b = min(_nodal_axis_career_signal(aff, _rahu_h, _ketu_h, _gate_text, eff_strengths), _PCC)
    acc.add_boost("nodal_axis", b)

    # Fix 3: Viparita Raja Yoga — flip dusthana penalty to bonus
    # 2026-08-22 reconciliation (method #5): eff_strengths now passed so this
    # function can de-weight overlap with _dusthana_lord_penalty's exemption.
    b = min(_viparita_raja_yoga_bonus(aff, house_lords, ph, _gate_text, eff_strengths), _PCC)
    acc.add_boost("viparita_raja_yoga", b)

    # Fix 4: D10 comprehensive reading
    _d10_occ   = getattr(payload_data, "d10_house_occupancy", {}) or {}
    _d10_hl    = getattr(payload_data, "d10_house_lords", {}) or {}
    # _d10_comprehensive_bonus's `label` param is computed to `label_lower` inside
    # but never referenced again (dead) -- intentionally left as `label`, not
    # `_gate_text` (Gap-18b audit).
    b = min(_d10_comprehensive_bonus(aff, _d10_occ, _d10_hl, d10_lagna, label, eff_strengths), _PCC)
    acc.add_boost("d10_comprehensive", b)

    # Fix 5: Solar/Lunar Hora career mode
    b = min(_hora_mode_career_signal(aff, getattr(payload_data, "planets_d1", {}) or {}, _gate_text), _PCC * 0.5)
    acc.add_boost("hora_mode", b)

    # Fix 6: Graha Avastha career manifestation modifier (can be negative)
    _av = _avastha_career_modifier(aff, getattr(payload_data, "planets_d1", {}) or {})
    acc.add_boost("avastha_modifier", _av)

    # Fix 7: H3 Parakrama lord — skill/effort house (engine layer, complements knrao layer)
    b = min(_h3_lord_career_bonus(aff, house_lords, ph, digs, eff_strengths, _gate_text), _PCC * 0.5)
    acc.add_boost("h3_parakrama", b)

    # Fix 8: Pushkara Navamsha boost
    b = min(_pushkara_navamsha_boost(aff, getattr(payload_data, "planets_d1", {}) or {}, eff_strengths), _PCC)
    acc.add_boost("pushkara_navamsha", b)

    # Fix 9: Nakshatra pada field discriminator
    b = min(_pada_field_discriminator(aff, _pl_naks, getattr(payload_data, "planets_d1", {}) or {}, house_lords, _gate_text), _PCC)
    acc.add_boost("pada_discriminator", b)

    # Fix 10: Chara Dasha simplified timing signal (Jaimini)
    _kms_sign = getattr(payload_data, "karakamsha_sign", "") or ""
    b = min(_chara_dasha_timing_signal(aff, _kms_sign, lagna_sign, ph, ak, current_age), 0.18)
    acc.add_boost("chara_dasha", b)
    # 2026-08-22 reconciliation (JyotishAI reference-audit method #3): bound
    # the combined Karakamsha-family total (karakamsha, karakamsha_occ,
    # karakamsha_domain, chara_dasha) at 0.30 -- none of the existing caps
    # (soul_stack/dasha_total/dasha_family) read these keys. See
    # apply_karakamsha_family_cap()'s docstring for clawback order/rationale.
    acc.apply_karakamsha_family_cap(ceiling=0.30)

    b = min(_lagna_element_career_bonus(lagna_sign, _gate_text), _PCC)
    acc.add_boost("lagna_element", b)

    b = min(_d1_d10_h10_double_dignity_bonus(aff, payload_data), _PCC)
    acc.add_boost("d1_d10_h10_double_dignity", b)

    # Fix 11: Spiritual/alternative career proxy (D20 substitute)
    b = min(_spiritual_career_proxy(aff, ph, house_lords, _gate_text, eff_strengths), _PCC * 0.5)
    acc.add_boost("spiritual_proxy", b)

    # Fix 12: Guna balance modifier
    b = min(_guna_balance_modifier(aff, eff_strengths, _gate_text), _PCC * 0.5)
    acc.add_boost("guna_balance", b)

    # Fix 13: Lagna lord in dusthana as career directive
    b = min(_lagna_lord_dusthana_directive(aff, lagna_lord, ph, _gate_text, eff_strengths), _PCC)
    acc.add_boost("lagna_lord_directive", b)

    # Fix 14: Adhi Yoga + Anapha/Sunapha
    _det_yogas = getattr(payload_data, "detected_yogas", []) or getattr(payload_data, "yogas_present", []) or []
    b = min(_adhi_anapha_yoga_bonus(aff, ph, getattr(payload_data, "planets_d1", {}) or {}, _det_yogas, _gate_text), _PCC)
    acc.add_boost("adhi_anapha_yoga", b)

    # Fix 15: Transit career activation window
    _transit_pos = getattr(payload_data, "transit_house_positions", {}) or {}
    b = min(_transit_career_activation(aff, _transit_pos, _gate_text, current_age), _PCC)
    acc.add_boost("transit_activation", b)
    # ── End 10/10 upgrade signals ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════════════════
    # ROUND-3: 15 new astrological signals
    # ═══════════════════════════════════════════════════════════════════════
    _planets_d1_r3 = getattr(payload_data, "planets_d1", {}) or {}
    _det_yogas_r3  = getattr(payload_data, "detected_yogas", []) or getattr(payload_data, "yogas_present", []) or []
    _combust_r3    = getattr(payload_data, "combust_planets", []) or []
    _ak_r3         = getattr(payload_data, "atmakaraka", "") or ak or ""
    _amk_r3        = getattr(payload_data, "amatyakaraka", "") or amk or ""
    _pk_r3         = getattr(payload_data, "putrakaraka", "") or ""
    _gnk_r3        = getattr(payload_data, "gnatikaraka", "") or ""
    # GAP-FIX (2026-07): remaining 3 Chara Karakas, previously computed but
    # never consumed by any scoring function (see _bhratrikaraka_field_score
    # / _matrikaraka_field_score / _darakaraka_field_score docstrings).
    _bk_r3         = getattr(payload_data, "bhatrikaraka", "") or ""
    _mk_r3         = getattr(payload_data, "matrikaraka", "") or ""
    _dk_r3         = getattr(payload_data, "darakaraka", "") or ""
    # V1.3 merge plan item 6 fix: payload's real field is "bav_points"
    # (jyotish/payload.py), not "bav_scores"/"bhinnashtakavarga" — those
    # never existed on NatalPayloadV2, so this getattr chain always fell
    # through to {} even after bav_points was populated. Check bav_points
    # first; keep the old names as a harmless fallback for any caller
    # that still sets them directly.
    _bav_r3        = getattr(payload_data, "bav_points", {}) or getattr(payload_data, "bav_scores", {}) or getattr(payload_data, "bhinnashtakavarga", {}) or {}
    _next_dasha_r3 = getattr(payload_data, "next_mahadasha_lord", "") or ""
    _curr_dasha_r3 = getattr(payload_data, "current_mahadasha_lord", "") or getattr(payload_data, "dasha_lord", "") or ""
    _ad_lord_r3    = getattr(payload_data, "current_antardasha_lord", "") or getattr(payload_data, "antardasha_lord", "") or ""

    # R3-1: Person-archetype pre-classifier
    b = min(_person_archetype_score(aff, eff_strengths, _ak_r3, _amk_r3, ph, lagna_sign, _det_yogas_r3, _gate_text), _PCC)
    acc.add_boost("person_archetype", b)

    # R3-2: Lagna propensity (classical lagna career tendencies)
    b = min(_lagna_propensity_score(aff, lagna_sign, _gate_text), _PCC * 0.67)
    acc.add_boost("lagna_propensity", b)

    # R3-3: Moon Rashi career propensity (emotional/behavioral work tendency)
    b = min(_moon_rashi_propensity(aff, _planets_d1_r3, _gate_text), _PCC * 0.58)
    acc.add_boost("moon_rashi_propensity", b)

    # R3-4: Panchamahapurusha mandate (field-specific yoga mandate; can be negative)
    _mph = _mahapurusha_mandate_score(aff, _det_yogas_r3, ph, _planets_d1_r3, _gate_text)
    acc.add_boost("mahapurusha_mandate", _mph)

    # R3-5: Career-house Parivartana bonus
    b = min(_career_parivartana_bonus(aff, house_lords, _planets_d1_r3, _gate_text), _PCC)
    acc.add_boost("career_parivartana", b)

    # R3-6: Graha Yuddha winner domain expansion
    b = min(_war_winner_domain_bonus(aff, _planets_d1_r3, _gate_text, eff_strengths), _PCC * 0.67)
    acc.add_boost("war_winner_domain", b)

    # R3-7: H10 lord combustion career flag (can be negative)
    _h10c = _h10_lord_combustion_flag(aff, house_lords, _planets_d1_r3, _combust_r3, _gate_text)
    acc.add_boost("h10_lord_combustion", _h10c)

    # R3-8: Compound Dasha quality index (multiplicative; can be negative)
    _cdq = _compound_dasha_quality(
        aff, _curr_dasha_r3, _ad_lord_r3, lagna_sign, house_lords,
        ph, _planets_d1_r3, eff_strengths, _combust_r3, _gate_text
    )
    acc.add_boost("compound_dasha_quality", _cdq)

    # R3-9: Putrakaraka (5th Chara Karaka) intellectual/creative field scoring
    b = min(_putrakaraka_field_score(aff, _pk_r3, ph, eff_strengths, _gate_text), _PCC * 0.75)
    acc.add_boost("putrakaraka_field", b)

    # R3-10: Gnatikaraka (6th Chara Karaka) competition/conflict field signal
    b = min(_gnatikaraka_field_score(aff, _gnk_r3, ph, eff_strengths, _gate_text), _PCC * 0.58)
    acc.add_boost("gnatikaraka_field", b)

    # R3-10b (GAP-FIX): Bhratrikaraka (3rd Chara Karaka) self-effort/skill field signal
    b = min(_bhratrikaraka_field_score(aff, _bk_r3, ph, eff_strengths, _gate_text), _PCC * 0.67)
    acc.add_boost("bhratrikaraka_field", b)

    # R3-10c (GAP-FIX): Matrikaraka (4th Chara Karaka) property/domestic field signal
    b = min(_matrikaraka_field_score(aff, _mk_r3, ph, eff_strengths, _gate_text), _PCC * 0.67)
    acc.add_boost("matrikaraka_field", b)

    # R3-10d (GAP-FIX): Darakaraka (7th Chara Karaka) partnership/business field signal
    b = min(_darakaraka_field_score(aff, _dk_r3, ph, eff_strengths, _gate_text), _PCC * 0.67)
    acc.add_boost("darakaraka_field", b)

    # R3-10e (GAP-FIX): Gochar (transit) career-activation signal
    b = _gochar_h10_activation_bonus(_transit_houses, h10_lord, ak, aff, _gate_text)
    acc.add_boost("gochar_h10", b)

    # R3-10f (GAP-FIX): Kaksha-level Ashtakavarga activation (H10 lord / AK)
    b = _kaksha_activation_bonus(h10_lord, ak, planets_d1, ph, _transit_degrees, _gate_text)
    acc.add_boost("kaksha_activation", b)

    # R3-11: Trikona lord unity — dharmic career mandate
    b = min(_trikona_unity_bonus(aff, house_lords, _planets_d1_r3, ph, _gate_text), _PCC)
    acc.add_boost("trikona_unity", b)

    # R3-12: Dasha timing gate — 10-year forward window
    b = min(_dasha_timing_gate(aff, _curr_dasha_r3, _next_dasha_r3, current_age, _gate_text, eff_strengths), _PCC * 0.67)
    acc.add_boost("dasha_timing_gate", b)

    # R3-13: Bhinnashtakavarga individual planet H10 scores
    b = min(_bav_individual_boost(aff, _bav_r3, house_lords, _gate_text), _PCC * 0.67)
    acc.add_boost("bav_individual", b)

    # R3-14: Yogi / Avayogi planet modifier (can be slightly negative)
    _yav = _yogi_avayogi_modifier(aff, _planets_d1_r3, eff_strengths, _gate_text)
    acc.add_boost("yogi_avayogi", _yav)

    # R3-15: Confidence convergence grade — deferred to after bvb_eval (real scores).
    # NOTE: formerly computed here using acc.gap_detail proxy keys that don't exist,
    # causing all 4 methods to fall back to `blended` and always return STRONG.
    # Now computed post-bundle with actual normalized_score values (T3-A fix).
    # ── End Round-3 upgrade signals ────────────────────────────────────────

    if ak and hard_affinity:
        _ak_top_k = max(hard_affinity.items(), key=lambda x: x[1])[0]
        if _ak_top_k == ak:
            # LS5 fix: ak_primary_karaka is a soul-domain signal — include it
            # inside the soul-stack total so the 0.26 cap covers it too.
            # Stage C merge: reuse acc.soul_stack_total (already computed by
            # apply_soul_stack_cap() earlier in the sequence) instead of
            # re-deriving ak_amk+yogakaraka+ak_house from gap_detail here.
            _akp_b = 0.10
            _soul_stack_with_akp = acc.soul_stack_total + _akp_b
            if _soul_stack_with_akp > 0.26:
                _akp_b = max(0.0, 0.26 - acc.soul_stack_total)
            if _akp_b > 0:
                acc.gap_boost += _akp_b; acc.gap_detail["ak_primary_karaka"] = round(_akp_b, 3)

    # A4 fix: wire cluster bonus/counterweight functions into main acc.gap_boost loop
    # (previously only called from field_methods/jaimini.py, missing from main pipeline)
    _cluster_b = _priority_cluster_field_bonus(branch_name, _gate_text, eff_strengths)
    if _cluster_b > 0:
        acc.add_boost('cluster_bonus', min(_cluster_b, _PCC))
    _space_cw  = _space_extractive_counterweight(branch_name, _gate_text, eff_strengths)
    _life_cw   = _life_science_space_counterweight(branch_name, _gate_text, eff_strengths)
    _eng_cw    = _life_science_engineering_counterweight(branch_name, _gate_text, eff_strengths)
    _total_cw  = _space_cw + _life_cw + _eng_cw
    if _total_cw < 0:
        acc.gap_penalty += abs(_total_cw)
        acc.gap_detail['cluster_counterweight'] = round(_total_cw, 3)

    # AC14 fix: Digbala — Sun and Mars gain directional strength in H10.
    # Classic rule: Sun = full Digbala in H10, Mars = full Digbala in H10.
    # Jupiter/Mercury = H1, Saturn = H7, Moon/Venus = H4.
    _DIGBALA_H10_PLANETS = {'Sun', 'Mars'}
    _digbala_b = 0.0
    for _dp in _DIGBALA_H10_PLANETS:
        if ph.get(_dp, 0) == 10 and aff.get(_dp, 0) >= 0.20:
            _digbala_b += aff.get(_dp, 0) * 0.15
    _digbala_b = min(_digbala_b, 0.05)
    if _digbala_b > 0:
        acc.add_boost('digbala_h10', _digbala_b)
    # AC14b: Jupiter/Mercury Digbala in H1 → small research/advisory boost
    for _dp in ('Jupiter', 'Mercury'):
        if ph.get(_dp, 0) == 1 and aff.get(_dp, 0) >= 0.25:
            _db1_b = min(0.03, aff.get(_dp, 0) * 0.10)
            acc.add_boost(f'digbala_h1_{_dp.lower()}', _db1_b)
    # GAP-FIX (2026-08, astrological audit): classical Digbala assigns
    # directional strength to FIVE planets, each in its own house — Sun/Mars
    # in H10 (handled above), Jupiter/Mercury in H1 (handled above), Saturn
    # in H7, and Moon/Venus in H4. The H7/H4 cases were never implemented at
    # all, which systematically under-credited Saturn/Moon/Venus career-house
    # strength relative to the other three Digbala planets. Added with the
    # same modest secondary-boost treatment already used for the H1 case.
    if ph.get('Saturn', 0) == 7 and aff.get('Saturn', 0) >= 0.25:
        _db7_b = min(0.03, aff.get('Saturn', 0) * 0.10)
        acc.add_boost('digbala_h7_saturn', _db7_b)
    for _dp in ('Moon', 'Venus'):
        if ph.get(_dp, 0) == 4 and aff.get(_dp, 0) >= 0.25:
            _db4_b = min(0.03, aff.get(_dp, 0) * 0.10)
            acc.add_boost(f'digbala_h4_{_dp.lower()}', _db4_b)

    # LS3 fix: neecha-bhanga planets or active yogas can legitimately
    # elevate a low-base-score field; don't hard-cap them at 0.30.
    _has_nb_support = bool(nb_set & set(hard_affinity.keys()))
    _has_yoga_support = bool(set(yogas) & {"BudhaAditya","GajaKesari","Ruchaka","Shasha",
                                            "Hamsa","Malavya","Saraswati","Bhadra"})
    # LS11 fix: domain-calibrated aptitude threshold
    # High-demand fields require stronger chart signals to rank highly.
    # R3 fix: use only the 13 real registry domains.
    # "music"→"arts", "sports"/"management"→"commerce" are not real domains.
    _DOMAIN_THRESHOLD = {
        'medicine': 50.0, 'engineering': 48.0, 'law': 46.0,
        'technology': 44.0, 'science': 44.0,
        'arts': 36.0, 'humanities': 38.0,
        'commerce': 40.0, 'agriculture': 40.0,
        'public': 44.0, 'education': 40.0,
        'media': 38.0, 'interdisciplinary': 42.0,
    }
    _domain_threshold = _DOMAIN_THRESHOLD.get(domain, 45.0)
    if blended < _domain_threshold and not _has_nb_support and not _has_yoga_support:
        _cap = 0.28 if _domain_threshold >= 48.0 else 0.30
        acc.gap_boost = min(acc.gap_boost, _cap)
    # Q6: Geometric diminishing marginal returns (replaces flat linear cap).
    # Formula equivalent to 1 - prod(1 - boost_i) applied to the accumulated sum.
    # Converts the linear sum to its geometric equivalent, which naturally:
    #   - Allows differentiation above 0.40 (linear cap was 0.55 but compressed this band)
    #   - Prevents saturation: no matter how many signals fire, boost < 1.0
    #   - Preserves ordering: more signals always = higher boost, but with declining increments
    # Geometric conversion: if linear_boost = sum(b_i), geometric ≈ 1 - exp(-linear_boost)
    # This is the exact limit of 1-prod(1-b_i) as each b_i → 0 and n → ∞.
    if acc.gap_boost > 0:
        acc.gap_boost = 1.0 - _math.exp(-acc.gap_boost)
    # T3-D: global soft ceiling. Geometric compression preserves ordering;
    # the 0.55 ceiling prevents a large stack of correlated minor rules
    # from overpowering the independently computed base score.
    acc.gap_boost = max(-0.20, min(acc.gap_boost, 0.55))

    _yk_planet    = _YOGAKARAKA_PLANET.get(lagna_sign, "")
    _ak_is_arts   = ak in ("Venus", "Moon", "Ketu")
    if (_fid in _MATERIAL_GRIT_FIELDS
            and not _ak_is_arts
            and (ak == "Saturn" or _yk_planet == "Saturn")
            and _top_karaka in ("Saturn", "Mars")):
        acc.add_boost("material_grit", 0.15)

    if domain == "arts" and ak == "Venus":
        _ven_dig   = digs.get("Venus", "")
        _ven_retro = retro.get("Venus", False)
        _ven_combust = "Venus" in set(combust)
        if _ven_dig in ("EXALTED", "OWN") and _ven_retro:   _b_vaf = 0.35
        elif _ven_dig in ("EXALTED", "OWN"):                 _b_vaf = 0.20
        elif "Venus" in nb_set and _ven_dig not in ("DEBILITATED",):
            # NB cancels debilitation structurally, but only boosts when Venus
            # is not actually debilitated in sign — a debilitated-NB AK is weakened,
            # not exalted; use non-dignified rate rather than NB rate.
            _jup_dig_vaf = digs.get("Jupiter", "")
            _jup_h_vaf   = ph.get("Jupiter", 0)
            _strong_nb   = _jup_dig_vaf in ("EXALTED", "OWN") and _jup_h_vaf in (1, 4, 7, 10)
            _b_vaf = 0.18 if _strong_nb else 0.14  # NB < OWN (0.20) classically
        elif _ven_dig not in ("DEBILITATED",) and not _ven_combust: _b_vaf = 0.07
        else:                                                         _b_vaf = 0.0
        if _b_vaf > 0:
            acc.add_boost("venus_arts_force", _b_vaf)

    # AmK Venus arts force only when AK is also arts-aligned (Venus/Moon).
    # When AK is Mars/Saturn/Mercury/Sun, the soul mandate overrides AmK career tilt.
    if domain == "arts" and amk == "Venus" and digs.get("Venus", "") in ("EXALTED", "OWN") \
            and ak in ("Venus", "Moon", ""):
        acc.add_boost("venus_arts_force_amk", 0.08)

    if domain in ("arts",) and ak == "Venus" and any(k in _gate_text.lower() for k in ("design","fashion","interior","textile","graphic","ux","product")):  # R3 fix: "design" not a real domain; fire on arts+design-label
        _ven_dig_d  = digs.get("Venus", "")
        _ven_cmb_d  = "Venus" in set(combust)
        if _ven_dig_d in ("EXALTED", "OWN"):                  _b_vdf = 0.18
        elif "Venus" in nb_set:                                _b_vdf = 0.15
        elif _ven_dig_d not in ("DEBILITATED",) and not _ven_cmb_d: _b_vdf = 0.07
        else:                                                   _b_vdf = 0.0
        if _b_vdf > 0:
            acc.add_boost("venus_design_force", _b_vdf)

    if domain in ("arts", "humanities") and ak == "Moon" and digs.get("Moon", "") in ("EXALTED", "OWN"):
        _b_maf = 0.32 if domain == "arts" else 0.09
        acc.add_boost("moon_arts_force", _b_maf)

    # Moon humanities force — Moon is AK_PRIME_DOMAIN for (medicine, humanities)
    if domain == "humanities" and ak == "Moon":
        _moon_dig_hf = digs.get("Moon", "")
        if _moon_dig_hf in ("EXALTED", "OWN"):   _b_mhf = 0.18
        elif "Moon" in nb_set:                    _b_mhf = 0.12
        elif _moon_dig_hf not in ("DEBILITATED",): _b_mhf = 0.07
        else:                                      _b_mhf = 0.0
        if _b_mhf > 0:
            acc.add_boost("moon_humanities_force", _b_mhf)

    # Arts placement guard: Venus must be arts-placed, not just career-strong.
    # When AK ≠ Venus and AmK ≠ Venus and Venus is in a career/dharma house (H9/H10)
    # rather than a creative house (H1/H5) or own sign (Taurus/Libra),
    # the chart lacks a genuine arts-soul indicator → apply a guard penalty.
    # Arts placement guard: skip for Moon-primary arts fields (music, performing_arts,
    # theatre, literature) where Venus placement is secondary to Moon's emotional signal.
    _MOON_PRIMARY_ARTS = {"music", "performing_arts", "theatre_drama", "literature_languages",
                           "mass_communication"}
    if domain == "arts" and ak != "Venus" and amk != "Venus"                 and _fid not in _MOON_PRIMARY_ARTS:
        _ven_sign_g = planets_d1.get("Venus", {}).get("sign", "")
        _ven_h_g    = ph.get("Venus", 0)
        _arts_placed = (_ven_sign_g in ("Taurus", "Libra")
                        or _ven_h_g in (1, 5)
                        or "Venus" in nb_set)
        if not _arts_placed:
            _arts_guard = -0.12
            acc.add_boost("arts_placement_guard", _arts_guard)

    if domain == "medicine" and ak == "Moon" and digs.get("Moon", "") in ("EXALTED", "OWN"):
        acc.add_boost("moon_medicine_force", 0.12)

    if (domain == "medicine" and ak == "Moon" and amk == "Jupiter"
            and digs.get("Moon", "") in ("EXALTED", "OWN")
            and digs.get("Jupiter", "") in ("EXALTED", "OWN")):
        acc.add_boost("moon_jupiter_medicine_force", 0.08)

    _moon_sign = planets_d1.get("Moon", {}).get("sign", "")
    _jup_sign  = planets_d1.get("Jupiter", {}).get("sign", "")
    if (domain == "medicine" and ak == "Moon"
            and _moon_sign and _jup_sign and _moon_sign == _jup_sign
            and digs.get("Moon", "") in ("EXALTED", "OWN")
            and digs.get("Jupiter", "") in ("EXALTED", "OWN", "NEECHA_BHANGA")):
        acc.add_boost("gaja_kesari_medicine_force", 0.15)

    if domain == "medicine" and ak == "Jupiter" and digs.get("Jupiter", "") in ("EXALTED", "OWN"):
        # GAP-FIX (2026-08, astrological audit): venus_arts_force and
        # jupiter_law_force elsewhere in this function already treat a
        # retrograde EXALTED/OWN karaka as classically STRONGER (increased
        # strength view of retrogression), but this block and
        # mercury_tech_force below omitted that check entirely -- an
        # arbitrary asymmetry (2 of the planets eligible to actually go
        # retrograde got the treatment, the others didn't), not a
        # deliberate rule. Applying the same ~1.5x retrograde uplift here
        # for consistency with the two force-blocks that already have it.
        _jup_retro_akmf = retro.get("Jupiter", False)
        acc.add_boost("jupiter_ak_medicine_force", 0.30 if _jup_retro_akmf else 0.20)

    _pisces_benefic = (planets_d1.get("Jupiter", {}).get("sign") == "Pisces"
                       and planets_d1.get("Venus", {}).get("sign") == "Pisces")
    if _pisces_benefic and domain in ("law", "arts", "medicine"):
        acc.add_boost("pisces_benefic_force", 0.12)

    _jup_mer_pair = ((ak == "Jupiter" and amk == "Mercury") or (ak == "Mercury" and amk == "Jupiter"))
    if domain == "interdisciplinary" and _jup_mer_pair:
        acc.add_boost("interdisciplinary_mixed_karaka", 0.15)

    if domain in ("science", "interdisciplinary") and ak == "Ketu":
        acc.add_boost("ketu_research_force", 0.10)

    if domain == "technology" and ak == "Mercury":
        _mer_dig = digs.get("Mercury", "")
        _mer_retro_mtf = retro.get("Mercury", False)
        # GAP-FIX (2026-08, astrological audit): see jupiter_ak_medicine_force
        # above for why this now checks retrograde consistently with
        # venus_arts_force/jupiter_law_force's existing treatment.
        if _mer_dig in ("EXALTED", "OWN") and _mer_retro_mtf: _b_mtf = 0.45
        elif _mer_dig in ("EXALTED", "OWN"):      _b_mtf = 0.30
        elif "BudhaAditya" in set(yogas) and _mer_dig != "DEBILITATED": _b_mtf = 0.30
        elif "Mercury" in nb_set:               _b_mtf = 0.15
        elif _mer_dig == "DEBILITATED":
            _mer_sign  = planets_d1.get("Mercury", {}).get("sign", "")
            _mer_disp  = {"Pisces": "Jupiter", "Virgo": "Mercury"}.get(_mer_sign, "")
            _b_mtf = 0.12 if (_mer_disp and digs.get(_mer_disp, "") == "EXALTED") else 0.05
        else:                                   _b_mtf = 0.15
        acc.add_boost("mercury_tech_force", _b_mtf)

    if (domain == "technology" and amk == "Mercury"
            and digs.get("Mercury", "") in ("EXALTED", "OWN")
            and _top_karaka in ("Mercury", "Rahu")):
        acc.add_boost("mercury_amk_tech_force", 0.10)

    # R3 fix: "government"/"civil_services"/"defence" not real domains; use "public"
    if (domain in ("public", "interdisciplinary", "science")
            and ak == "Sun" and digs.get("Sun", "") in ("EXALTED", "OWN") and amk != "Jupiter"):
        acc.add_boost("sun_leadership_force", 0.20)

    # Jupiter law/education force — primary classical karaka for law, wisdom, teaching
    if domain in ("law", "education", "humanities") and ak == "Jupiter":
        _jup_dig_lf = digs.get("Jupiter", "")
        _jup_retro_lf = retro.get("Jupiter", False)
        if _jup_dig_lf in ("EXALTED", "OWN") and _jup_retro_lf:   _b_jlf = 0.35
        elif _jup_dig_lf in ("EXALTED", "OWN"):                    _b_jlf = 0.22
        elif "Jupiter" in nb_set:                                   _b_jlf = 0.16
        elif _jup_dig_lf not in ("DEBILITATED",):                  _b_jlf = 0.09
        else:                                                        _b_jlf = 0.0
        if _b_jlf > 0:
            acc.add_boost("jupiter_law_force", _b_jlf)

    if (domain in ("law", "education", "humanities") and amk == "Jupiter"
            and digs.get("Jupiter", "") in ("EXALTED", "OWN") and ak in ("Jupiter", "Sun", "")):
        acc.add_boost("jupiter_amk_law_force", 0.08)

    if (domain == "engineering" and ak == "Mars"
            and digs.get("Mars", "") in ("EXALTED", "OWN")
            and "Mars" not in (set(combust) | cazimi_set)):
        acc.add_boost("mars_engineering_force", 0.12)
    elif (domain == "engineering" and ak == "Mars"
            and digs.get("Mars", "") not in ("DEBILITATED",)
            and "Mars" not in (set(combust) | cazimi_set)):
        acc.add_boost("mars_engineering_force", 0.07)

    if (_fid in _MATERIAL_GRIT_FIELDS and amk == "Mars"
            and digs.get("Mars", "") in ("EXALTED", "OWN")
            and _top_karaka in ("Mars", "Saturn")):
        acc.add_boost("mars_amk_engineering_force", 0.10)

    if (domain == "engineering" and ak == "Saturn"
            and digs.get("Saturn", "") in ("EXALTED", "OWN")
            and "Saturn" not in (set(combust) | cazimi_set)
            and _top_karaka in ("Mars", "Saturn")):
        acc.add_boost("saturn_ak_engineering_force", 0.15)

    if (domain == "engineering" and amk == "Saturn"
            and digs.get("Saturn", "") in ("EXALTED", "OWN")
            and "Saturn" not in set(combust)
            and _top_karaka in ("Mars", "Saturn")):
        acc.add_boost("saturn_amk_engineering_force", 0.10)

    if _fid in _MATERIAL_GRIT_FIELDS and "Mars" in nb_set and _yk_planet == "Mars":
        acc.add_boost("nb_mars_yk_engineering_force", 0.07)

    # S153: NB Mars as yoga-karak partially restores engineering domain even when Mars
    # is not AK/AmK.  Classical Neecha Bhanga = near-Raja-Yoga strength for the YK
    # planet's natural significations.  Only fires for engineering fields not covered
    # by _MATERIAL_GRIT_FIELDS (those already get 0.07 above).
    if (domain == "engineering" and "Mars" in nb_set and _yk_planet == "Mars"
            and _fid not in _MATERIAL_GRIT_FIELDS):
        acc.add_boost("nb_mars_yk_broad_engineering_restore", 0.06)

    _ll_house = ph.get(lagna_lord, 0)
    if (_ll_house == 10 and lagna_lord == ak
            and digs.get(lagna_lord, "") in ("EXALTED", "OWN")
            and _top_karaka == lagna_lord):
        acc.add_boost("lagna_lord_h10_domain_force", 0.15)

    if ak == "Venus" and lagna_sign == "Leo" and domain == "engineering":
        acc.gap_boost -= 0.08; acc.gap_detail["leo_venus_ak_engineering_guard"] = -0.08

    # acc.gap_penalty was initialised to 0.0 above; continue accumulating (do not reset)
    p_ak_comb = min(_ak_combustion_penalty(aff, ak, combust, digs, planets_d1=planets_d1, vargottama_planets=vargottama), 0.15)
    acc.add_penalty("ak_combustion_penalty", p_ak_comb)
    p_dust = _dusthana_lord_penalty(aff, lagna_sign, house_lords, lagna_lord, _gate_text, eff_strengths, planet_house=ph)
    acc.add_penalty("dusthana_penalty", p_dust)
    p_d10 = _d10_consistency_penalty(aff, getattr(payload_data, "d10_house_occupancy", {}), label=_gate_text)
    acc.add_penalty("d10_dusthana_penalty", p_d10)

    # F: Ashtakavarga Sarvashtakavarga Bindu house-capability filter (Round 6)
    _sav_house   = ph.get(_top_karaka, 0)
    _sav_bindus  = (sav.get(str(_sav_house), sav.get(_sav_house, 28))
                    if sav and _sav_house else 28)
    _sav_factor  = max(0.80, min(1.20, 1.0 + (_sav_bindus - 28) * 0.01))
    blended      = blended * _sav_factor
    acc.gap_detail["sav_bindu_factor"] = round(_sav_factor, 3)

    # N4: H4 (education foundation) + H5 (intelligence) SAV for STEM/medicine fields
    # Classical: H4 SAV ≥ 30 bindus = strong education foundation;
    #            H5 SAV ≥ 30 = clear intelligence; both houses drive academic careers.
    _EDU_SAV_DOMAINS = {"engineering", "science", "technology", "medicine"}
    if sav and domain in _EDU_SAV_DOMAINS:
        _sav_h4 = float(sav.get("4", sav.get(4, 28)))
        _sav_h5 = float(sav.get("5", sav.get(5, 28)))
        _edu_sav_avg = (_sav_h4 + _sav_h5) / 2.0
        # Scale: avg 28 = neutral (1.0), avg 34 = +6% boost, avg 22 = -6% drag
        _edu_sav_factor = max(0.92, min(1.08, 1.0 + (_edu_sav_avg - 28) * 0.008))
        blended *= _edu_sav_factor
        acc.gap_detail["edu_house_sav_factor"] = round(_edu_sav_factor, 3)

    # LS5 fix: _base_weight should reflect dignity quality only, not blended score
    # (blended already incorporates eff_strength which embeds shadbala + dignity;
    #  using blended again here double-counted strength signal).
    # ═══════════════════════════════════════════════════════════════════
    # CONFLUENCE GATE — 3-house minimum convergence requirement
    # Classical Jyotish: a field needs ≥3 independent chart sources to be
    # ── WORLD-CLASS UPGRADE: New gap-boost signals (P1-P2) ───────────────
    from .boosts import (
        _gana_workplace_fit, _dosha_burnout_modifier, _nakshatra_devata_bonus,
        _foreign_career_multiplier, _ghati_lagna_bonus, _sree_lagna_bonus,
        _hora_lagna_bonus, _bhava_lagna_bonus, _bhrigu_bindu_bonus,
        _h3_skills_bonus, _h8_research_bonus, _h9_dharma_bonus,
        _h11_network_gains_bonus, _budha_aditya_yoga_bonus,
        _saraswati_yoga_bonus, _kemadruma_yoga_penalty, _chandal_yoga_signal,
        _sudarshana_convergence_bonus,
    )
    _moon_nak_e  = getattr(payload_data, "moon_nakshatra", "") or ""
    _lagna_nak_e = getattr(payload_data, "lagna_nakshatra", "") or ""
    _b = min(_gana_workplace_fit(_gate_text, _moon_nak_e, _lagna_nak_e), _PCC)
    acc.add_boost("gana_workplace_fit", _b)
    _b = _dosha_burnout_modifier(_gate_text, _moon_nak_e)
    acc.add_boost("dosha_burnout", _b)
    _b = min(_nakshatra_devata_bonus(_gate_text, _moon_nak_e, _lagna_nak_e), _PCC)
    acc.add_boost("devata_domain", _b)
    _b = min(_foreign_career_multiplier(_gate_text, payload_data), _PCC)
    acc.add_boost("foreign_career_mult", _b)
    _ghati_sign_e = getattr(payload_data, "ghati_lagna_sign", "") or ""
    _sree_sign_e  = getattr(payload_data, "sree_lagna_sign", "") or ""
    _b = min(_ghati_lagna_bonus(_gate_text, _ghati_sign_e, digs), _PCC)
    acc.add_boost("ghati_lagna", _b)
    _b = min(_sree_lagna_bonus(_gate_text, _sree_sign_e, digs), _PCC)
    acc.add_boost("sree_lagna", _b)
    # GAP-FIX (2026-07): Hora Lagna / Bhava Lagna / Bhrigu Bindu -- now
    # actually populated by engine_io.py (see its wiring notes); these
    # boosts silently no-op (return 0.0) if birth data was insufficient
    # to compute them, same as ghati/sree above already did.
    _hora_sign_e   = getattr(payload_data, "hora_lagna_sign", "") or ""
    _bhava_sign_e  = getattr(payload_data, "bhava_lagna_sign", "") or ""
    _bhrigu_sign_e = getattr(payload_data, "bhrigu_bindu_sign", "") or ""
    _b = min(_hora_lagna_bonus(_gate_text, _hora_sign_e, digs), _PCC)
    acc.add_boost("hora_lagna", _b)
    _b = min(_bhava_lagna_bonus(_gate_text, _bhava_sign_e, digs), _PCC)
    acc.add_boost("bhava_lagna", _b)
    _b = min(_bhrigu_bindu_bonus(_gate_text, _bhrigu_sign_e, digs), _PCC)
    acc.add_boost("bhrigu_bindu", _b)
    _h3_lord_e  = house_lords.get("3",  house_lords.get(3, ""))
    _h8_lord_e  = house_lords.get("8",  house_lords.get(8, ""))
    _h9_lord_e  = house_lords.get("9",  house_lords.get(9, ""))
    _h11_lord_e = house_lords.get("11", house_lords.get(11, ""))
    _b = min(_h3_skills_bonus(_gate_text, _h3_lord_e, ph.get(_h3_lord_e, 0), aff, digs), _PCC)
    acc.add_boost("h3_skills", _b)
    _b = min(_h8_research_bonus(_gate_text, _h8_lord_e, ph.get(_h8_lord_e, 0), aff, digs), _PCC)
    acc.add_boost("h8_research", _b)
    _b = min(_h9_dharma_bonus(_gate_text, _h9_lord_e, ph.get(_h9_lord_e, 0), h10_lord, aff, digs), _PCC)
    acc.add_boost("h9_dharma", _b)
    _b = min(_h11_network_gains_bonus(_gate_text, _h11_lord_e, ph.get(_h11_lord_e, 0), h10_lord, aff, digs), _PCC)
    acc.add_boost("h11_network", _b)
    _b = min(_budha_aditya_yoga_bonus(_gate_text, planets_d1, combust, aff), _PCC)
    acc.add_boost("budha_aditya", _b)
    _b = min(_saraswati_yoga_bonus(_gate_text, ph, aff), _PCC)
    acc.add_boost("saraswati_yoga", _b)
    # _kemadruma_yoga_penalty's `label` param is unused inside the function (pure
    # Moon-house structural check) -- intentionally left as `label` (Gap-18b audit).
    _b = _kemadruma_yoga_penalty(label, ph, planets_d1)
    acc.add_boost("kemadruma", _b)
    _b = _chandal_yoga_signal(_gate_text, ph, aff)
    acc.add_boost("chandal_yoga", _b)
    _sun_sign_e  = planets_d1.get("Sun", {}).get("sign", "") if isinstance(planets_d1.get("Sun"), dict) else ""
    _moon_sign_e = planets_d1.get("Moon", {}).get("sign", "") if isinstance(planets_d1.get("Moon"), dict) else ""
    _b = min(_sudarshana_convergence_bonus(
        _gate_text, lagna_sign, _sun_sign_e, _moon_sign_e,
        house_lords, ph, aff, digs), _PCC)
    acc.add_boost("sudarshana", _b)

    # ── P3-1: D3 / D20 / D30 divisional boosts ───────────────────────────
    from .boosts import (
        _d3_drekkana_skills_bonus, _d20_vimshamsha_spiritual_calling,
        _d30_trimsamsha_obstacle_check,
    )
    _d3_digs  = getattr(payload_data, "d3_planet_dignities",  {}) or {}
    _d20_digs = getattr(payload_data, "d20_planet_dignities", {}) or {}
    _d30_digs = getattr(payload_data, "d30_planet_dignities", {}) or {}
    _b = min(_d3_drekkana_skills_bonus(_gate_text, _d3_digs, aff), _PCC)
    acc.add_boost("d3_drekkana", _b)
    _b = min(_d20_vimshamsha_spiritual_calling(_gate_text, _d20_digs, aff), _PCC)
    acc.add_boost("d20_vimshamsha", _b)
    # _d30_trimsamsha_obstacle_check's `label` param is unused inside the function
    # (pure D30 dignity iteration) -- intentionally left as `label` (Gap-18b audit).
    _b = _d30_trimsamsha_obstacle_check(label, _d30_digs, aff)   # can be negative
    acc.add_boost("d30_trimsamsha", _b)

    # ── P3-2: Extended Jaimini karaka boosts ─────────────────────────────
    from .boosts import (
        _gnk_competitive_bonus, _dk_partnership_bonus, _pk_creative_bonus,
    )
    _gnk = getattr(payload_data, "gnatikaraka", "") or ""
    _dk  = getattr(payload_data, "darakaraka",  "") or ""
    _pk  = getattr(payload_data, "putrakaraka", "") or ""
    _b = min(_gnk_competitive_bonus(_gate_text, _gnk, ph, digs, aff), _PCC)
    acc.add_boost("gnk_competitive", _b)
    _b = min(_dk_partnership_bonus(_gate_text, _dk, ph, digs, aff), _PCC)
    acc.add_boost("dk_partnership", _b)
    _b = min(_pk_creative_bonus(_gate_text, _pk, ph, digs, aff), _PCC)
    acc.add_boost("pk_creative", _b)
    # ── End World-Class Upgrade signals ──────────────────────────────────

    # genuinely indicated; below that, acc.gap_boost is zeroed or capped 70%.
    # ═══════════════════════════════════════════════════════════════════
    # Gap-18b (generalized fix, audit 2026-07): _confluence_gate's gate_mult
    # multiplies the ENTIRE accumulated acc.gap_boost (d3/d20/d30 varga bonuses,
    # gnk/dk/pk karaka bonuses, and more -- all of which now already use the
    # enriched `_gate_text` above) by 0.0/0.30/1.0 depending on how many of
    # 7 chart sources' planet-domain keywords (_CONFLUENCE_PLANET_KW) match
    # the field's text -- previously only the short registry `label` (e.g.
    # "International Relations & Diplomacy"), not the field's fuller
    # niche/description ("...Diplomacy / Foreign Policy / Global Governance
    # / Strategic Studies..."). Diagnosed as a real, measurable contributor
    # to international_relations (Total 50.5, rank 38) scoring well below
    # political_science (Total 61.4, rank 20) despite comparable raw
    # affinity-weighted planetary strength -- reuses the same `_gate_text`
    # defined once at the top of this loop, generically, for every field.
    _cgate = _confluence_gate(
        label        = _gate_text,
        affinity     = aff,
        house_lords  = house_lords,
        ak           = ak,
        amk          = amk,
        active_dasha_lord = prime_career_lord,
        peak_dasha_lord   = peak_lord,
        antardasha_lord   = _antardasha_lord,
        eff_strengths     = eff_strengths,
    )
    _gate_mult  = _cgate["gate_mult"]
    _gate_label = _cgate["gate_label"]
    acc.gap_detail["confluence_sources"] = _cgate["support_count"]
    acc.gap_detail["confluence_gate"]    = _gate_label
    # Apply gate: multiply ALL accumulated acc.gap_boost by the gate multiplier.
    # gate_mult = 0.0 → field not genuinely indicated; acc.gap_boost zeroed.
    # gate_mult = 0.30 → weak signal; acc.gap_boost cut to 30%.
    # gate_mult = 1.0 → genuinely supported; full acc.gap_boost applies.
    acc.gap_boost = acc.gap_boost * _gate_mult

    _ak_dig = digs.get(ak, "")
    _base_weight = {"EXALTED": 1.00, "OWN": 0.90, "NEECHA_BHANGA": 0.85,
                    "NEUTRAL": 0.75, "DEBILITATED": 0.55}.get(_ak_dig, 0.75)
    acc.gap_boost    = acc.gap_boost * _base_weight

    # Q8: D60 Deity Vector — apply planet purity check before score computation.
    # The H10 lord's D60 deity quality gates the final acc.gap_boost magnitude.
    # A planet dignified in D1/D10 but falling in Ghora/Krodhana D60 = hidden drain.
    _d60_allowed = payload_data.calculation_policy.d60_claims_allowed
    _d60_h10 = _d60_vitality_gate(h10_lord, payload_data) if _d60_allowed else 1.0
    _d60_ak  = (_d60_vitality_gate(ak, payload_data) if ak else 1.0) if _d60_allowed else 1.0
    _d60_gate = (_d60_h10 * 0.65 + _d60_ak * 0.35)

    # GAP-FIX (2026-07): the above deity-quality D60 gate is a genuinely
    # distinct classical layer (60-part Kalachakra deity purity) and is
    # kept as-is, but it was previously the ONLY D60 signal in the whole
    # engine -- there was no real D60 sign/dignity computation at all
    # (see vimshopaka.py's compute_d60_sign, D60's single highest weight
    # of 4.0/20 in the classical Dasavarga table). Blend in a second,
    # independent D60 signal from the planet's actual dignity in its D60
    # sign, bounded to a modest [0.85, 1.15] range so it complements
    # rather than overrides the existing deity-quality check.
    _d60_vim_h10 = (0.85 + 0.30 * (_vb_h10.get("per_varga", {}).get("D60", 0.0) / 4.0)) if _d60_allowed else 1.0
    _d60_vim_ak  = (0.85 + 0.30 * (_vb_ak.get("per_varga", {}).get("D60", 0.0) / 4.0)) if _d60_allowed else 1.0
    _d60_vim_gate = _d60_vim_h10 * 0.65 + _d60_vim_ak * 0.35
    _d60_gate = (_d60_gate + _d60_vim_gate) / 2.0
    acc.gap_detail["d60_vimshopaka_gate"] = round(_d60_vim_gate, 4)
    acc.gap_detail["d60_combined_observation"] = round(_d60_gate, 4)
    acc.gap_detail["d60_role"] = "CONFIRMATION_ONLY" if _d60_allowed else "NOT_COMPUTED_INSUFFICIENT_BIRTH_TIME_PRECISION"
    acc.gap_detail["d60_applied_multiplier"] = 1.0

    score = blended * (1.0 + acc.gap_boost) * (1.0 - acc.gap_penalty)

    # Gap-18b (generalized fix, audit 2026-07): pass the field's full registry
    # record (_fmeta) through so keyword-gate checks inside each method
    # scorer can match on its descriptive text (label/track/niche/
    # description), not just the bare field_id. See
    # field_methods/common.py::build_gate_text for the full rationale —
    # diagnosed on international_relations/political_science scoring
    # comparably to international_law on raw affinity math but never
    # surfacing in the top-35 purely because their field_id shares no
    # vocabulary with the "law"-oriented keyword lists.
    bvb_eval = compute_field_method_bundle(payload_data, domain, hard_affinity, branch_name, _fmeta)
    # G3: combined_score drives a relative boost on the blended score
    # (was: addend of combined/100*1.5 which contributed <1.5 pts — negligible)
    # Audit fix (2026-08-17): ceiling raised 0.20 -> 0.28 (±10% -> ±14%
    # net swing). Rationale: combined_score is the classically-weighted
    # convergence of all 9 method scorers (knrao/kp/jaimini/parashara/
    # dashamsha/sudarshana/siddhamsha/shashtiamsha/structural_patterns),
    # with quality/outlier/correlation-group adjustments and Jaimini +
    # Dashamsha (BPHS's dedicated vocational techniques) weighted highest
    # -- the single most classically rigorous component in this pipeline
    # -- yet it previously had by far the smallest reach of any major
    # scoring stage: ±10% here vs acc.gap_boost/acc.gap_penalty's up to +55%/-20%
    # (boosts.py, ~30 signals) and the risk-gate stack's ~50% combined
    # cut (aptitude-threshold/domain-mismatch/friction/QA-gate/debilitated
    # -AK). 0.28 keeps this a genuine but clearly subordinate contributor:
    # still less than half of acc.gap_boost's positive reach and well below
    # the risk gates' cut, so a chart with strong 9-method convergence
    # scores meaningfully higher without this multiplier ever overriding
    # gap-signal or risk-gate outcomes. This intentionally shifts scores
    # for charts with strong or weak convergence -- that is the point.
    _method_boost = (bvb_eval.get("combined_score", 50.0) - 50.0) / 100.0 * 0.28
    score = score * bvb_eval["astro_multiplier"] * (1.0 + _method_boost)

    # ── T3-A + T1-B: Real convergence grade using actual method normalized scores ──
    # Previously computed inside acc.gap_boost using acc.gap_detail proxy keys that don't
    # exist → all 4 methods fell back to `blended` → grade was always STRONG.
    # Now computed here with real data; applied as a multiplier, not an additive cap.
    # Pipeline-consolidation fix (audit): Sudarshana used to be computed a
    # SECOND time here (a fresh score_sudarshana() call, entirely separate
    # from the bundle above) purely to feed this convergence grade, while
    # also being completely absent from bvb_eval's own weighted blend and
    # method_agreement/method_conflict diagnostics -- two different
    # pipelines silently answering "does Sudarshana support this field"
    # from the same inputs. Sudarshana is now a first-class 6th method in
    # compute_field_method_bundle (field_methods/__init__.py), so this
    # reads its already-computed normalized score from the bundle instead
    # of recomputing it, keeping exactly one Sudarshana call per field.
    _method_normalized_scores_pre = bvb_eval.get("method_normalized_scores", {})
    _real_method_scores_for_conv = {
        "KNRao":     _method_normalized_scores_pre.get("knrao",     50.0),
        "KP":        _method_normalized_scores_pre.get("kp",        50.0),
        "Jaimini":   _method_normalized_scores_pre.get("jaimini",   50.0),
        "Parashara": _method_normalized_scores_pre.get("parashara", 50.0),
        # Gap-6 (audit 2026-07) fix: dashamsha now participates in convergence.
        "Dashamsha": _method_normalized_scores_pre.get("dashamsha", 50.0),
        "Sudarshana": _method_normalized_scores_pre.get("sudarshana", 50.0),
        # Phase-1/2 remediation (2026-08 gap-audit): siddhamsha (D24) and
        # shashtiamsha (D60) now vote in compute_field_method_bundle, but
        # this convergence-grade dict was a separate hardcoded six-key
        # copy that missed them -- so "HIGH/MODERATE/LOW convergence"
        # labels were being computed from 6 of the bundle's 8 methods.
        # correlation_discount_factor()/CONVERGENCE_LAYER_COUNT below were
        # already bumped to 8 for Phase-1/2, so this dict must match.
        "Siddhamsha": _method_normalized_scores_pre.get("siddhamsha", 50.0),
        "Shashtiamsha": _method_normalized_scores_pre.get("shashtiamsha", 50.0),
    }
    acc.gap_detail["_sudarshana_layers"] = (
        bvb_eval.get("method_log", {}).get("sudarshana", {})
        .get("components", {}).get("layers_active", 0)
    )
    # threshold=35.0 because normalized_score is on 0-100 scale (not 0-1)
    # _confidence_convergence_grade's `label` param is unused inside the function
    # (pure method_scores counting) -- intentionally left as `label` (Gap-18b audit).
    _method_conv = _confidence_convergence_grade(
        _real_method_scores_for_conv, label, threshold=35.0
    )
    _convergence_mult_raw = {
        "HIGH":           1.18,   # all layers agree → +18% (pre-correlation-discount)
        "MODERATE-HIGH":  1.09,   # most layers agree → +9%
        "MODERATE":       1.00,   # split → neutral
        "LOW":            0.94,   # 1 layer → −6%
        "SPECULATIVE":    0.88,   # 0 layers → −12%
    }.get(_method_conv["confidence_label"], 1.00)
    # Gap-8 (audit 2026-07) fix: the 6 convergence layers (KNRao/KP/Jaimini/
    # Parashara/Dashamsha/Sudarshana) are NOT independent witnesses — they share
    # the same underlying primitives in boosts.py (D10-H10 occupancy, dusthana-
    # lord penalty, chandra-lagna-H10 lord, cluster bonuses each appear in 3-4
    # methods AND again in engine gap-boosts). Rewarding "6 layers agree" at the
    # full +18%/-12% swing treats correlated re-statements of the same fact as
    # independent confirmation. _CORRELATION_DISCOUNT halves the deviation from
    # neutral (1.0) to reflect that a meaningful fraction of any "agreement" is
    # structural (shared inputs) rather than genuinely independent corroboration.
    # See SIGNAL_REGISTRY in field_methods/common.py for the known-duplicated
    # facts driving this discount; retire/shrink the discount once methods are
    # rebuilt on the registry so each fact scores in exactly one place.
    # Gap-8 close-out: was a hardcoded 0.6; now derived from SIGNAL_REGISTRY
    # itself via correlation_discount_factor(), so the discount automatically
    # relaxes as duplicated facts are collapsed to a single owning method.
    _CORRELATION_DISCOUNT = correlation_discount_factor()
    _convergence_mult = round(1.0 + (_convergence_mult_raw - 1.0) * _CORRELATION_DISCOUNT, 4)
    score *= _convergence_mult
    acc.gap_detail["_confidence_label"]    = _method_conv["confidence_label"]
    acc.gap_detail["_convergence_mult"]    = round(_convergence_mult, 3)
    acc.gap_detail["_convergence_count"]   = _method_conv.get("convergence_count", 0)
    # ── End T3-A + T1-B ────────────────────────────────────────────────────

    final_score = score

    _method_scores = bvb_eval.get("method_scores", {})
    _method_normalized_scores = bvb_eval.get("method_normalized_scores", {})
    _method_weights = bvb_eval.get("method_weights", {})
    _method_raw_total = round(bvb_eval.get("raw_combined_score", 50), 2)
    _method_total   = round(bvb_eval.get("combined_score", 50), 2)
    _method_log     = bvb_eval.get("method_log", {})
    _method_breakdown = {}
    for m in _method_scores.keys():
        # Consistency fix (2026-08-20 audit): weighted_contribution used to be
        # computed from the raw, 4dp-precision effective weight
        # (_method_weights.get(m)) while the sibling "weight" field displayed
        # in the same row was independently rounded to 2dp -- so a consumer
        # multiplying the two displayed numbers (weight * normalized_score)
        # could not reproduce weighted_contribution. Worst on low-prior
        # methods (kp/siddhamsha/shashtiamsha), where rounding a weight like
        # 0.0629 down to the displayed 0.06 is a large relative change, so
        # weight*normalized_score vs. the old weighted_contribution could
        # diverge by 30-40% relative. Both fields are now derived from the
        # SAME rounded values so "weight * normalized_score ==
        # weighted_contribution" holds exactly for every exported row.
        # NOTE: this only affects the diagnostic method_breakdown export --
        # the actual field_score_v2 blend (combine_weighted_scores) still
        # uses the full-precision effective weights internally, so ranking
        # / final_score are unaffected by this rounding-consistency fix.
        _norm = round(float(_method_normalized_scores.get(m, 0.0)), 2)
        _wt   = round(float(_method_weights.get(m, 0.0)), 2)
        _method_breakdown[m] = {
            "score":  round(float(_method_scores.get(m, 0.0)), 2),
            "normalized_score": _norm,
            "weight": _wt,
            "weighted_contribution": round(_norm * _wt, 2),
        }
        # Keep exported field rows aligned with compute_field_method_bundle().
        # Dashamsha and Sudarshana are first-class bundle methods; omitting
        # either here makes reports understate active evidence.

    audit    = execute_qa_verification_v8_9(
        branch_name, payload_data, domain,
        war_result=war_result, d10_digs=d10_digs, d9_digs=d9_digs)
    conflict = assess_domain_mismatch(
        aptitudes, domain, digs, combust,
        detected_yogas=list(yogas), shadbala=shadbala,
        branch_affinity_weights=llm_affinity, ak=ak, amk=amk, nb_set=nb_set)

    if not aptitudes["meets_threshold"]: score *= 0.70
    if conflict["mismatch_risk"]:        score *= 0.85
    # Fix (2026-08-20): `friction_multiplier` already bakes in a 0.70x
    # penalty when `is_fatal` is set (see execute_qa_verification_v8_9,
    # "Final multiplier" section) -- `passed_qa_gate` is just `not is_fatal`,
    # so the line that used to sit here (`if not audit["passed_qa_gate"]:
    # score *= 0.70`) was reapplying the SAME fatal penalty a second time,
    # turning one combustion/war-loss fatal condition into a ~0.70*0.70=0.49x
    # cut instead of the intended 0.70x. `passed_qa_gate` remains a reporting
    # flag (see `is_afflicted` below) but is no longer a second score
    # multiplier.
    score *= audit.get("friction_multiplier", 1.0)
    # Debilitated AK prime-domain penalty: when the AK planet is DEBILITATED in
    # sign, its soul mandate is compromised — penalise its prime-domain fields.
    # Fires even with Neecha Banga (NB restores structure but not full force),
    # consistent with how venus_arts_force blocks the NB path for DEBILITATED Venus.
    _ak_debil_mult = 1.0
    if _ak_debil and domain in _AK_PRIME_DOMAINS.get(ak, ()):
        score *= 0.85
        _ak_debil_mult = 0.85
        acc.gap_detail["debil_ak_soul_pen"] = -0.15

    # Gap-audit fix (2026-08): each of the five gates just above is
    # individually bounded/documented (e.g. "friction_multiplier floor
    # 0.65"), but nothing stops several firing on the same field at once,
    # and they compound multiplicatively -- 0.70 x 0.85 x 0.65 x 0.70 x
    # 0.85 =~ 0.26 from FIVE "modest" gates before the two more
    # population-relative discounts (_apply_paradigm_spread_penalty,
    # _apply_interdomain_normalization) are even applied post-loop.
    # Captured here so _apply_combined_risk_floor() (called post-loop,
    # after those two additional gates run) can cap the TOTAL combined
    # discount from all seven gates together, rather than letting them
    # compound unbounded. See that function's docstring for the concrete
    # real-chart case (Electrical Engineering, -61% from stacked gates
    # despite out-scoring Mechanical Engineering on almost every raw
    # method) that surfaced this.
    _stage_a_risk_gate_mult = round(
        (0.70 if not aptitudes["meets_threshold"] else 1.0)
        * (0.85 if conflict["mismatch_risk"] else 1.0)
        * float(audit.get("friction_multiplier", 1.0))
        # Fix (2026-08-20): no separate 0.70x QA-gate term here -- the fatal
        # 0.70x is already inside friction_multiplier above; see the fix note
        # at this function's `score *=` chain for the double-counting this
        # replaced.
        * _ak_debil_mult,
        6,
    )

    # AK/AmK domain flat supplement — applied after all multipliers so
    # soul-domain fields enter top-35 even when AK planet is Mrita/weak
    # Same humanities gate as above: no flat supplement for humanities+Mars/Sun/Saturn AK
    # When AK is debilitated, zero its keyword contribution but keep AmK active.
    _eff_ak_flat = "" if _ak_debil else ak
    _ak_flat = 0.0 if (
        (domain == "humanities" and ak in ("Mars", "Sun", "Saturn"))
        or _mars_nondomain_gate
    ) else _ak_domain_flat_supplement(_gate_text, _eff_ak_flat, amk, digs)
    if _ak_flat > 0:
        # LS2 fix: scale by blended/100 so weak-base fields (blended=40) get
        # 40% of supplement vs strong-base (blended=100) fields getting full value.
        # Audit fix: also scale by friction_multiplier so fatal conditions reduce
        # the supplement (fatal field should not receive full soul-purpose addend).
        _fric_scale = audit.get("friction_multiplier", 1.0)
        _ak_flat_scaled = round(_ak_flat * max(0.4, min(blended, 100.0) / 100.0) * _fric_scale, 2)
        score += _ak_flat_scaled
        acc.gap_detail["ak_domain_flat"] = round(_ak_flat_scaled, 1)

    _thresh_mult   = 0.70 if not aptitudes["meets_threshold"] else 1.0
    _mismatch_mult = 0.85 if conflict["mismatch_risk"] else 1.0
    _friction_mult = audit.get("friction_multiplier", 1.0)
    # Fix (2026-08-20): was `0.70 if not audit["passed_qa_gate"] else 1.0`,
    # double-applying the fatal penalty already folded into _friction_mult
    # above. No longer a separate multiplier; kept as a named constant so the
    # after_friction/after_qa logging chain below stays intact.
    _qa_mult       = 1.0
    _after_gap     = round(blended * (1.0 + acc.gap_boost) * (1.0 - acc.gap_penalty), 4)

    # Gap-B fix: capture the score at each multiplicative step so final_chain is complete.
    # Previously the BVB astro_multiplier and ak_domain_flat were invisible between
    # after_penalty and final_score.
    _bvb_mult        = bvb_eval["astro_multiplier"]
    # N5: Use G3 formula in log (was old formula combined/100*1.5, now matches actual score)
    # Audit fix (2026-08-17): reuse the _method_boost already computed at
    # the G3 site above instead of recomputing the identical formula --
    # avoids the two sites silently desyncing if the formula is ever
    # edited in only one place.
    _logged_method_boost = _method_boost
    _after_bvb       = round(_after_gap * _bvb_mult * (1.0 + _logged_method_boost), 4)
    _after_thresh    = round(_after_bvb * _thresh_mult, 4)
    _after_mismatch  = round(_after_thresh * _mismatch_mult, 4)
    _after_friction  = round(_after_mismatch * _friction_mult, 4)
    _after_qa        = round(_after_friction * _qa_mult, 4)
    _ak_flat_logged  = round(acc.gap_detail.get("ak_domain_flat", 0.0), 4)

    calc_trace = {
        "planet_trace":   planet_trace,
        "edu_planet_reasons": edu_planet_reasons,
        "edu_eff_strengths":  edu_eff_strengths,
        "edu_ranked":         [p for p, _ in edu_ranked],
        "affinity_weights":   affinity_result["affinity_planets"],
        "affinity_contributions": affinity_result.get("planet_contributions", affinity_result.get("affinity_planets", {})),
        "normalization": {
            "composite_score_raw":   round(aptitudes["composite_score"], 4),
            "composite_norm":        round(composite_norm, 4),
            "affinity_score_raw":    round(affinity_result["affinity_score"], 4),
            "affinity_norm":         round(affinity_norm, 4),
            "domain_blend_weight":   current_domain_blend,
            "affinity_blend_weight": current_affinity_blend,
            "blended":               round(blended, 4),
        },
        "gap_boosts":       {k: v for k, v in acc.gap_detail.items() if isinstance(v, (int, float)) and v > 0.0},
        "gap_penalties":    {k: v for k, v in acc.gap_detail.items() if isinstance(v, (int, float)) and v < 0.0},
        "gap_boost_total":  round(acc.gap_boost, 4),
        "gap_penalty_total":round(acc.gap_penalty, 4),
        # Real fix (this pass): the earlier "fix" at ~line 2516 only patched
        # _top35_for_llm (the separate LLM-prompt payload list) -- it never
        # touched this function's own returned row dict, which is what
        # `results`/`safe_results` actually carries into
        # split_debug_payload()/redacted_engine_summary.json. That export's
        # SUMMARY_KEYS filter reads the literal keys "gap_boost"/"gap_penalty"
        # via a plain .get() with a 0 default, and this dict never defined
        # them (only the "_total"-suffixed names above) -- so every summary
        # export silently read 0 regardless of the real accumulated value.
        # Alias both here, at the single source every downstream consumer
        # (top_35, results, safe_results, _top35_for_llm) is built from, so
        # the fix can't be bypassed by whichever list a given export reads.
        "gap_boost":        round(acc.gap_boost, 4),
        "gap_penalty":      round(acc.gap_penalty, 4),
        "final_chain": {
            # Gap-B fix: complete chain now shows every multiplicative step.
            # Read as: blended → after_boost → after_penalty → after_bvb_multiplier
            #          → after_threshold → after_mismatch → after_friction
            #          → after_qa → after_ak_flat (= pre_norm_score).
            # The displayed final_score is set later by cross-batch 20-100 normalization
            # (see pre_norm_score in the result dict for the pre-normalization value).
            "blended":              round(blended, 4),
            "after_boost":          round(blended * (1.0 + acc.gap_boost), 4),
            "after_penalty":        round(_after_gap, 4),
            "bvb_multiplier":       round(_bvb_mult, 4),
            "bvb_combined_addend":  round(_logged_method_boost, 6),
            "after_bvb_multiplier": _after_bvb,
            "threshold_mult":       _thresh_mult,
            "after_threshold":      _after_thresh,
            "mismatch_mult":        _mismatch_mult,
            "after_mismatch":       _after_mismatch,
            "friction_mult":        round(_friction_mult, 4),
            "after_friction":       _after_friction,
            "friction_note":        audit.get("audit_notes", ""),
            "qa_gate_mult":         _qa_mult,
            "after_qa":             _after_qa,
            "ak_domain_flat":       _ak_flat_logged,
            "after_ak_flat":        round(_after_qa + _ak_flat_logged, 4),
            "final_score":          round(score, 4),
        },
        "active_dasha_lord": active_lord,
        "peak_dasha_lord":   peak_lord,
        "karakas":           {"AK": ak, "AmK": amk},
        "aspects_on_h10":    [p for p, hs in _get_planetary_aspects(ph).items() if 10 in hs],
        "verified_factors":  _build_verified_factors(acc.gap_detail),
    }

    _reg_meta = _COURSE_REGISTRY.get(branch_name, {})
    _tier     = _reg_meta.get("tier_map", {})
    _ug_info  = _tier.get("UG", {})
    _pg_info  = _tier.get("PG", {})
    _phd_info = _tier.get("PhD", {})

    # ── §6 divisional-chart-weighting audit instrumentation (2026-08) ──────
    # Print a per-field breakdown of the D9/D24/D60 signals right before this
    # field's final score is finalized. D9 sustainability and D24 gate/flag
    # both have real, cleanly-extractable values at this point (the D9
    # AK/H10 gate boosts and D24 AK/full-chart boosts computed a few hundred
    # lines above are already sitting in acc.gap_detail, and d9_digs/d10_digs
    # are already resolved per-planet dicts in this function's scope).
    # D60 (Shashtiamsha) tie-breaking is NOT resolvable here: it is only
    # meaningful once every field's score is known and compared, which
    # happens later in compute_tiered_ranking() (jyotish/tiered_ranking.py,
    # Tier 3 = shashtiamsha+structural_patterns, near-tie gated on
    # birth_time_precision). This function is only ever told about ONE
    # field at a time, so it cannot report whether D60 broke a tie --
    # a matching printout is added at the tie-break site itself instead
    # (see tiered_ranking.py::compute_tiered_ranking).
    _anchor_planets = sorted(aff, key=aff.get, reverse=True)[:3] if aff else []
    _d9_sustain_notes = []
    for _p in _anchor_planets:
        _d9dig = d9_digs.get(_p, "")
        _mult = composite_v2.compute_d9_sustainability_mult(_d9dig) if _d9dig else 1.0
        # Narrative-accuracy fix (2026-08-20 audit): compute_dignity() only
        # returns a non-empty label for the four "special" classical tiers
        # (EXALTED / DEBILITATED / OWN / MOOLATRIKONA) -- a friend's-sign,
        # neutral-sign, or enemy's-sign placement (the majority of real
        # placements) is intentionally left as "" by that function, since
        # it isn't a Shadbala Sthana-Bala special tier. This used to get
        # relabeled "unknown" here, which reads as "the engine couldn't
        # determine this planet's dignity" -- a data-quality problem -- when
        # it's actually a correctly-computed "no exceptional tier applies"
        # result. Relabeled to make that distinction legible in the printed
        # narrative instead of looking like a missing-data gap.
        _d9_sustain_notes.append((_p, _d9dig or "ordinary placement, no special dignity tier", _mult))
    _d9_sustain_collapsed = any(m <= 0.90 for _, _, m in _d9_sustain_notes)
    _d9_sustain_held = any(m >= 1.05 for _, _, m in _d9_sustain_notes)
    _d9_boost_applied = round(
        acc.gap_detail.get("d9_ak", 0.0) + acc.gap_detail.get("d9_h10", 0.0), 4
    )

    _d24_ak_boost   = round(acc.gap_detail.get("d24_ak", 0.0), 4)
    _d24_full_boost = round(acc.gap_detail.get("d24_full", 0.0), 4)
    _d24_gate_flag  = bool(_d24_ak_boost > 0.0 or _d24_full_boost > 0.0) and _d9_sustain_collapsed
    # NOTE: D24 here is still a live additive scoring term in this codebase
    # (_d24_ak_delta / _d24_full_chart_bonus feed acc.gap_boost directly),
    # not the pure gate/flag the §6 spec calls for -- _d24_gate_flag above is
    # a best-effort *derived* diagnostic (strong D24 evidence + a collapsing
    # D9 sustainability multiplier => "can study, may not build a durable
    # career in it"), not a real architectural gate. Flagged in the audit
    # report; not corrected here per task instructions (report gaps, don't
    # silently rewrite substantive scoring logic).

    if _VERBOSE_FIELD_LOG:
        print(
            f"[FIELD SCORE] {label} ({branch_name}): final_score={round(score, 2)} "
            f"| D9 sustainability mult applied (AK/H10 gap-boosts)={_d9_boost_applied} "
            f"| D24 gate/flag raised={_d24_gate_flag} "
            f"(d24_ak_boost={_d24_ak_boost}, d24_full_boost={_d24_full_boost}) "
            f"| D60 tie-break: not applicable here (resolved later, across all "
            f"fields, in compute_tiered_ranking())"
        )
    _d9_desc = (
        "collapsed toward the 0.85 floor (afflicted D9 placements undercutting sustained results)"
        if _d9_sustain_collapsed else
        "held strong (0.9-1.15 range, D9 placements support sustained results)"
        if _d9_sustain_held else
        "roughly neutral in D9"
    )
    # `dig` is always non-empty now (see the "ordinary placement" fallback
    # set above when _d9_sustain_notes is built), so no further `or` fallback
    # is needed here.
    _anchor_desc = ", ".join(f"{p} ({dig})" for p, dig, _m in _d9_sustain_notes) or "no clearly dominant anchor planet"
    _d24_desc = (
        "D24 (Siddhamsha) shows real academic-mastery testimony for this field, but since its "
        "D9 sustainability is weak, the classical reading is 'can study this, may not build a "
        "durable career in it' rather than a durable professional outcome"
        if _d24_gate_flag else
        "D24 did not surface a study-vs-career caution for this field (either no strong D24 "
        "testimony, or D9 sustainability is not collapsing, so no conflict to flag)"
    )
    if _VERBOSE_FIELD_LOG:
        print(
            f"[FIELD NARRATIVE] {label}: anchored by {_anchor_desc}. This field's D9 (Navamsha) "
            f"sustainability {_d9_desc}. {_d24_desc}. D60 (Shashtiamsha) has no role for a single "
            f"field in isolation -- it only ever acts as a tie-breaker once this field is compared "
            f"against its closest-scoring rivals after all fields are ranked."
        )
    # ── end §6 instrumentation ───────────────────────────────────────────

    _all_pre_results.append({
        "field_id":      branch_name,
        "field_label":   label,
        "domain":        domain,
        "final_score":   round(score, 2),
        "affinity_score":  round(affinity_result["affinity_score"], 2),
        "composite_score": round(aptitudes["composite_score"], 2),
        "blended_score":   round(blended, 2),
        "acc.gap_boost":       round(acc.gap_boost, 3),
        "acc.gap_penalty":     round(acc.gap_penalty, 3),
        # Real fix (this pass, 2nd attempt): `_all_pre_results` -- NOT the
        # dict built further down around "gap_boost_total"/"gap_boost" --
        # is the actual per-field row that flows into top_35/_all_deduped/
        # results/safe_results and ultimately redacted_engine_summary.json.
        # The earlier "acc.gap_boost"/"acc.gap_penalty" keys here use a
        # literal dot in the key name, which split_debug_payload()'s
        # SUMMARY_KEYS/REFERENCE_KEYS allow-list doesn't recognize (it only
        # matches the plain names "gap_boost"/"gap_penalty"), so they always
        # fell into the audit-only bucket under their dotted name instead of
        # reaching the summary export under the name the UI/report actually
        # reads. Alias to the plain key names SUMMARY_KEYS expects.
        "gap_boost":       round(acc.gap_boost, 3),
        "gap_penalty":     round(acc.gap_penalty, 3),
        "gap_breakdown":   acc.gap_detail,
        "_stage_a_risk_gate_mult": _stage_a_risk_gate_mult,
        # GAP-FIX (2026-07, transparency): the 6-method convergence label
        # (_confidence_convergence_grade, correlation-discounted) and
        # confluence-gate support count were already computed for every
        # field but only ever stored under underscore-prefixed debug keys
        # inside gap_breakdown -- effectively invisible to any consumer
        # who isn't reading the raw internal dict. Promoted to a clean,
        # documented, top-level field here. HIGH/MODERATE-HIGH/MODERATE/
        # LOW/SPECULATIVE reflects how many of the 6 scoring methods
        # (KNRao/KP/Jaimini/Parashara/Dashamsha/Sudarshana) independently
        # agree on this field, already discounted for known structural
        # correlation between methods (see the correlation_discount_factor
        # docstring near _confidence_convergence_grade's call site above)
        # -- this is NOT a statistical confidence interval on the score
        # itself, just a same-chart cross-method agreement signal; a
        # single-chart pipeline like this one cannot produce a true error
        # bar without validation against known outcomes (see
        # tests/test_career_track_regressions.py / test_backtesting.py for
        # the closest thing this repo has to that kind of external check).
        "score_confidence": acc.gap_detail.get("_confidence_label", "MODERATE"),
        "score_confidence_note": (
            "Cross-method agreement across 6 independent scoring systems "
            "(KNRao, KP, Jaimini, Parashara, Dashamsha, Sudarshana), "
            "discounted for known shared inputs between methods. Not a "
            "statistical confidence interval."
        ),
        "affinity_planets": aff,
        "affinity_source": affinity_result.get("affinity_source", "default"),
        "top_affinity_planets": dict(
            sorted(affinity_result.get("planet_contributions", affinity_result.get("affinity_planets", {})).items(),
                   key=lambda x: x[1], reverse=True)[:3]),
        "aptitude_profile":  aptitudes,
        "structural_audit":  audit,
        "conflict_report":   conflict,
        "is_afflicted":      not audit["passed_qa_gate"],
        "war_losers":        [p for p, s in war_result.items() if "loser" in s],
        "war_winners":       [p for p, s in war_result.items() if s == "winner"],
        "vargottama_planets":vargottama,
        "neecha_bhanga":     list(nb_set),
        "cazimi_planets":    list(cazimi_set),
        "calc_trace":        calc_trace,
        "method_scores":     _method_scores,
        "method_normalized_scores": _method_normalized_scores,
        "method_weights":    _method_weights,
        "method_breakdown":  _method_breakdown,
        "method_log":        _method_log,
        "combined_score":    _method_total,
        "raw_combined_score": _method_raw_total,
        "method_total_score":_method_total,
        "weighted_method_score": _method_total,
        # GAP-FIX: this key was previously set here AND again below (at the
        # "method_weighted_contributions": bvb_eval.get(...) line further
        # down in this same dict), both to the identical expression — the
        # second assignment silently won (Python dict literals let a later
        # duplicate key overwrite an earlier one), so this first occurrence
        # was dead code. Removed to avoid a future editor mistaking the
        # duplicate for two different values being threaded through.
        "method_agreement":  bvb_eval.get("method_agreement", 0.0),
        "method_conflict":   bvb_eval.get("method_conflict", {"detected": False}),
        "method_signal_clarity": bvb_eval.get("method_signal_clarity", {}),
        "method_authority_priors": bvb_eval.get("method_authority_priors", {}),
        # GAP-FIX (2026-07-20, P0-5 signal-class exposure): signal_lineage
        # and signal_provenance were being computed in the method bundle
        # (Field_Determination/field_methods/__init__.py) but this
        # published-row builder copies an explicit key allow-list rather
        # than passing the bundle through, so neither ever reached a
        # published result -- the same class of "computed but never
        # surfaced" bug documented for hard_lockout in
        # TOP20_19_CHART_AUDIT_2026-07-18.md. Confirmed missing by a live
        # run against Charts/Karthick_chart_details.json before this fix.
        "signal_lineage":    bvb_eval.get("signal_lineage", {}),
        "signal_provenance": bvb_eval.get("signal_provenance", {}),
        "knrao_score":       round(float(_method_scores.get("knrao", 0.0)), 2),
        "kp_score":          round(float(_method_scores.get("kp", 0.0)), 2),
        "jaimini_score":     round(float(_method_scores.get("jaimini", 0.0)), 2),
        "parashara_score":   round(float(_method_scores.get("parashara", 0.0)), 2),
        "dashamsha_score":   round(float(_method_scores.get("dashamsha", 0.0)), 2),
        "sudarshana_score":  round(float(_method_scores.get("sudarshana", 0.0)), 2),
        # Phase-1/2 remediation (2026-08 gap-audit): siddhamsha (D24) and
        # shashtiamsha (D60) were computed in the bundle and voted into
        # final_score, but this explicit key allow-list -- copied from
        # the bundle rather than passing it through -- never surfaced
        # them, the same class of bug this comment already documents for
        # the six pre-existing methods above. Confirmed missing on a live
        # run (Midhula chart, 2026-08-14) before this fix.
        "siddhamsha_score":    round(float(_method_scores.get("siddhamsha", 0.0)), 2),
        "shashtiamsha_score":  round(float(_method_scores.get("shashtiamsha", 0.0)), 2),
        # Stage 1 (Astro-OS v3 gap-audit implementation plan, 2026-08):
        # structural_patterns (D1 house-occupancy clustering) -- 9th
        # voting method -- same allow-list threading pattern as
        # siddhamsha_score/shashtiamsha_score just above.
        "structural_patterns_score": round(float(_method_scores.get("structural_patterns", 0.0)), 2),
        # Bug fix (2026-08 gap-audit round 2, "fix as per sequence" item 2):
        # d9_navamsha_confirmation and jaimini_chara_dasha_timing were added
        # to compute_field_method_bundle()'s return dict in
        # Field_Determination/field_methods/__init__.py, but this row
        # builder still copies an explicit key allow-list rather than
        # passing the bundle through -- same class of "computed but never
        # surfaced" bug as signal_lineage/siddhamsha_score above. Confirmed
        # missing from the published audit JSON on a live Midhula-chart
        # run (2026-08-14) before this fix.
        "d9_navamsha_confirmation": bvb_eval.get("d9_navamsha_confirmation", {}),
        "jaimini_chara_dasha_timing": bvb_eval.get("jaimini_chara_dasha_timing", {}),
        # Stage 4 (Astro-OS v3 gap-audit implementation plan, 2026-08):
        # multi-dimensional confidence decomposition -- same allow-list
        # threading pattern as the two keys just above.
        "confidence_dimensions": bvb_eval.get("confidence_dimensions", {}),
        # Stage 3 (Astro-OS v3 gap-audit implementation plan, 2026-08):
        # chart-level career archetype discovery, same allow-list
        # threading pattern as confidence_dimensions just above.
        "career_archetype": bvb_eval.get("career_archetype", {}),
        # 2026-08 architecture-audit gap-fix: chart_synthesis.py (Gaps
        # 2/3/5/7) and purpose_chain.py (Gaps 9/11/12) outputs were both
        # computed by compute_field_method_bundle() but, same class of
        # bug as d9_navamsha_confirmation's own comment above documents,
        # never threaded through this row builder's explicit allow-list
        # -- meaning none of it ever reached a real report despite being
        # computed on every call. Same allow-list threading pattern as
        # confidence_dimensions/career_archetype just above.
        "structural_graph": bvb_eval.get("structural_graph", {}),
        "planet_pattern_graph": bvb_eval.get("planet_pattern_graph", {}),
        "d24_learning_profile": bvb_eval.get("d24_learning_profile", {}),
        "purpose_chain": bvb_eval.get("purpose_chain", {}),
        "career_reasoning_chain": bvb_eval.get("career_reasoning_chain", {}),
        "method_components": bvb_eval.get("method_components", {}),
        "method_weighted_contributions": bvb_eval.get("method_weighted_contributions", {}),
        "llm_astrological_reason": llm_astro_reason,
        "llm_selection_rationale": llm_sel_rationale,
        "registry": {
            "description":    _reg_meta.get("description", ""),
            "specialization": _reg_meta.get("specialization", ""),
            "niche":          _reg_meta.get("niche", ""),
            "track":          _reg_meta.get("track", ""),
            "label":          _reg_meta.get("label", ""),
            "ug_program":     _ug_info.get("spec", ""),
            "ug_niche":       _ug_info.get("niche", ""),
            "pg_program":     _pg_info.get("spec", ""),
            "pg_niche":       _pg_info.get("niche", ""),
            "phd_program":    _phd_info.get("spec", ""),
            "phd_niche":      _phd_info.get("niche", ""),
            "admission_exams":_reg_meta.get("admission_exams", []),
            "career_paths":   _reg_meta.get("career_signature", []),
            "institutions":   _reg_meta.get("institutions", []),
            "available_at":   _reg_meta.get("available_at", {}),
        },
    })


def _attach_registry_before_return(results):
    registry = _load_course_registry()
    return attach_v12_registry_metadata(results, registry)


def _refresh_cluster_report_and_evidence_summaries(results: List[Dict]) -> List[Dict]:
    """Rebuild career_cluster_report and each row's evidence_summary from
    final, publication-corrected scores.

    GAP-FIX (2026-07-18, audit): career_cluster_report (macro identity +
    named clusters, competency_ontology.build_cluster_report) and each row's
    evidence_summary (build_evidence_summary) were both built earlier in the
    pipeline -- before apply_publication_ranking_policy() and
    _enforce_hard_lockout_publication_order() run. Those two steps are the
    actual "publication-stage correction" (symbolic-leakage discount,
    specialization-vs-foundation capping, hard-lockout reordering) and do
    change final_score/rank for some rows. Confirmed on a real chart: the
    embedded macro identity anchored on a field whose *pre-correction* score
    (e.g. 91.52) beat a materials-engineering field's *pre-correction* score,
    when the *post-correction* scores (62.23 vs 80.74) gave the opposite
    answer -- the cluster report and evidence_summary.final_score never saw
    the correction and kept reporting the earlier numbers. This must run
    AFTER apply_publication_ranking_policy() and
    _enforce_hard_lockout_publication_order(), using the same `results` list
    those functions already mutated in place, so every score referenced here
    is the one actually published.
    """
    if not results:
        return results
    try:
        cluster_report = build_cluster_report(results)
    except Exception as _cluster_e:
        logger.warning("Publication-stage cluster report refresh failed, keeping prior report: %s", _cluster_e)
        cluster_report = None
    for row in results:
        if cluster_report is not None:
            row["career_cluster_report"] = cluster_report
        # 2026-08 architecture-audit gap-fix: this function already exists
        # specifically because evidence_summary is built too early (inside
        # apply_competency_ontology_layer, BEFORE apply_release_4_7 attaches
        # kp_authority_audit) -- see this function's own docstring above for
        # the analogous final_score-staleness bug it was written to fix.
        # This session's Gap-8 fix (build_evidence_summary's KP-authority
        # contradicting-evidence note) reads row["score_confidence_note"]
        # for the "could NOT be independently verified" phrasing -- but that
        # exact phrasing is only ever written by _build_score_confidence_note
        # below, which (like kp_authority_audit itself) isn't available yet
        # at the ORIGINAL evidence_summary build time either. Patching only
        # final_score/confidence_band into the stale evidence_summary dict
        # (as this loop used to do) left the KP note permanently unreachable
        # in the real pipeline. Fix: compute score_confidence_note FIRST,
        # then fully rebuild evidence_summary from the row now that both
        # score_confidence_note and kp_authority_audit are genuinely final --
        # cheap (pure recombination of already-computed fields, see
        # build_evidence_summary's own docstring), not a new computation.
        row["score_confidence_note"] = _build_score_confidence_note(row)
        if isinstance(row.get("evidence_summary"), dict):
            try:
                row["evidence_summary"] = build_evidence_summary(row)
            except Exception as _ev_e:
                logger.warning("Publication-stage evidence_summary rebuild failed for %s, "
                                "keeping prior evidence_summary with patched score only: %s",
                                row.get("field_id", "?"), _ev_e)
                ev = row.get("evidence_summary")
                if isinstance(ev, dict):
                    fs = float(row.get("final_score", 0.0) or 0.0)
                    ev["final_score"] = fs
                    ev["confidence_band"] = confidence_band(fs)
    return results


def _build_score_confidence_note(row: Dict) -> str:
    """Compose score_confidence_note with two corrections from the
    2026-07-18 audit:

    1. P1 "'six independent methods' overstates independence" -- the note
       used to call KNRao/KP/Jaimini/Parashara/Dashamsha/Sudarshana "6
       independent scoring systems... discounted for known shared inputs",
       which names them independent in the same sentence that says they
       share inputs. Reworded to "6 scoring channels" and states plainly
       they are correlated, not independent, evidence.
    2. P1 "KP-as-scoring-method-despite-unverified presentation" -- kp_score
       sits in every row's primary score breakdown identically to the other
       5 methods, but by the time this runs, apply_release_4_7() has
       already attached kp_authority_audit (jyotish/kp_audit.py's
       verification of this chart's actual KP cusp/sub-lord chain) to the
       row. When that status isn't VERIFIED, kp_authority_factor is 0.0 and
       KP contributed ~no weight to the blend (see
       Field_Determination/field_methods/__init__.py's _data_quality["kp"]
       gating) -- but nothing said so anywhere a reader would see kp_score
       displayed. State the verification outcome explicitly per row.
    """
    base = (
        # Phase-1/2 remediation (2026-08 gap-audit): "6 scoring channels"
        # updated to 8 -- siddhamsha (D24) and shashtiamsha (D60) were added
        # as voting methods but this hardcoded note text was not updated
        # alongside the method_breakdown/_data_quality wiring, so it kept
        # describing a stale six-method model even after the blend itself
        # correctly used eight. Confirmed stale on the same live Midhula run
        # that surfaced the summary/report key-allow-list gap above.
        "Cross-method agreement across up to 8 scoring channels (KNRao, KP, "
        "Jaimini, Parashara, Dashamsha, Sudarshana, Siddhamsha, Shashtiamsha). "
        "These are correlated, not independent, evidence -- several share structural inputs "
        "(e.g. D10-H10 occupancy, dusthana-lord penalties; see "
        "SIGNAL_REGISTRY in field_methods/common.py), so agreement across "
        "them is discounted for that known correlation rather than counted "
        "as independent corroboration. Not a statistical confidence interval."
    )
    kp_audit = row.get("kp_authority_audit") or {}
    kp_status = kp_audit.get("status")
    if kp_status == "VERIFIED":
        kp_clause = " KP's cusp/sub-lord chain was independently verified for this chart."
    elif kp_status:
        kp_reasons = kp_audit.get("reasons") or []
        reason_str = f" ({', '.join(kp_reasons)})" if kp_reasons else ""
        kp_clause = (
            f" KP's cusp/sub-lord chain could NOT be independently verified for "
            f"this chart (status: {kp_status}{reason_str}); KP contributed "
            f"little or no authority weight to the blend despite kp_score "
            f"being shown above for transparency."
        )
    else:
        kp_clause = ""
    return base + kp_clause


def _build_composite_v2_chart_primitives(payload_data):
    """Phase B (shadow-score migration): build the per-planet, chart-level
    (field-independent) primitive inputs jyotish.composite_v2.compute_field_score()
    needs, computed ONCE per chart rather than once per field. Field-dependent
    primitives (d9_gate, which needs a field's affinity vector as weights) are
    NOT included here -- they're computed per-field in the shadow-scoring loop
    inside _finalize_published_results().

    Returns None on any failure (missing/incompatible payload attributes),
    matching the existing defensive style used elsewhere in this module (e.g.
    the _bav_tiebreak_scores block in _finalize_published_results()) -- a
    shadow-score computation must never be able to break the live response.

    KNOWN PHASE B LIMITATION: KP / KNRao / Sudarshan per-planet multipliers
    are NOT included in the Tier-2 factor set below. Those three techniques
    are field-specific (sub-lord/lordship-convergence confirmation is about
    which planet's chain governs a SPECIFIC field, not a chart-wide fact), so
    they cannot be folded into this chart-level, once-per-chart primitives
    builder -- see `_composite_v2_field_tier2_bonus()` and its call site in
    `_finalize_published_results()` for the per-field Tier-2 contribution
    those three methods make instead.

    2026-08-20 UPDATE (Stage-1a/1b consolidation): `adjusted_strength` no
    longer runs its own independent Tier-1 (base_strength x dignity_mult)
    + Tier-2 (maitri/vargottama/combustion/avastha, capped log-average)
    stack on a separately max-normalized base_strength. It is built
    directly from `payload_data.eff_strengths` (astro.py::
    _compute_eff_strengths' output), which already carries D1 dignity,
    combustion, maitri, vargottama, avastha, functional role, nakshatra-lord
    house placement, Paksha Bala, and node dispositor-affliction -- see the
    inline comment at the top of this function's try block for the full
    rationale and what's still applied on top (Yogakaraka, Graha Yuddha --
    the two factors eff_strength deliberately excludes). The
    maitri_correction/vargottama_planets/combustion_mult/avastha_mult
    payload attributes referenced in older revisions of this docstring are
    no longer read here; they remain populated on payload_data for other
    consumers (e.g. astro.py's own trace) but this function reads
    eff_strengths instead of reconstructing an equivalent Tier-2 stack from
    them a second time.
    """
    try:
        # 2026-08-20 architecture change (Stage-1a/1b consolidation, explicit
        # owner sign-off): adjusted_strength now derives directly from
        # astro.py::_compute_eff_strengths()'s `eff_strength` per planet
        # (payload_data.eff_strengths), instead of a second, independent
        # base_strength -> tier1_strength -> tier2_adjustment stack built on
        # a max-normalized ("strongest planet in THIS chart = 1.0") figure
        # with no classical basis. eff_strength is anchored to each planet's
        # own classical minimum Shadbala threshold
        # (constants.py::_PLANET_MIN_SHADBALA, a real BPHS bar) and already
        # carries D1 dignity (dig_eff), combustion (comb_mod, 3-tier per the
        # 2026-08-20 audit), Panchadha Maitri, Vargottama (var_mod), Baladi
        # Avastha (avastha_mod), functional role/house-lordship (func_mod),
        # nakshatra-lord house placement (nak_house_mod), Paksha Bala
        # (pb_mod), and node dispositor-affliction (dispositor_mod) -- a
        # strictly richer set of classical techniques than the old
        # dignity_mult + 4-factor Tier-2 stack it replaces, which only ever
        # saw dignity/maitri/vargottama/combustion/avastha and nothing else.
        # Reapplying dignity_mult/maitri/vargottama/combustion/avastha here
        # on top of eff_strength would double-count each of those exactly
        # once more (the same class of bug fixed earlier this session inside
        # _compute_eff_strengths itself) -- so this block does NOT call
        # compute_tier1_strength()/compute_adjusted_strength() any more.
        # CORRECTED 2026-08-22 (JyotishAI reference-audit method #8,
        # owner-approved fix): the paragraph above previously claimed
        # Yogakaraka was "forced to 1.0 inside _compute_eff_strengths" so it
        # would be safe to re-apply here via yogakaraka_mult. That claim is
        # false -- astro.py::_compute_eff_strengths's `yk_mod` (0.90 if
        # debilitated, else 1.18-1.25) is a live, unconditional factor in
        # eff_strength's own multiplicative chain (see its `_mult_chain =
        # ... * yk_mod * avastha_mod` and the AUDIT NOTE immediately above
        # it acknowledging the overlap with boosts.py's separate additive
        # Yogakaraka bonus -- a different overlap, already reconciled in
        # reference-audit method #1, from the one fixed here). This block
        # was therefore multiplying the Yogakaraka planet's eff_strength by
        # yk_mod (already inside it) AND by yogakaraka_mult=1.25 again --
        # up to ~1.56x combined for one classical fact. yogakaraka_mult is
        # now fixed to 1.0 (identity) below; eff_strength's own yk_mod is
        # the sole multiplicative Yogakaraka credit in this composite
        # pathway. Graha Yuddha (graha_yuddha_mult) remains genuinely
        # non-redundant -- it is composite_v2's own dual-criteria winner/
        # loser check, independent of astro.py's own war detection, and
        # eff_strength does not carry it.
        eff_strengths = dict(getattr(payload_data, "eff_strengths", {}) or {})
        if not eff_strengths:
            return None
        planet_longitudes = getattr(payload_data, "planet_longitudes", {}) or {}
        house_lords = getattr(payload_data, "house_lords", {}) or {}
        planet_house = getattr(payload_data, "planet_house", {}) or {}
        dasha_sequence = getattr(payload_data, "dasha_sequence", None) or []
        atmakaraka = getattr(payload_data, "atmakaraka", "") or ""
        amatyakaraka = getattr(payload_data, "amatyakaraka", "") or ""
        current_age = float(getattr(payload_data, "current_age", 0) or 0)
        lagna_sign = getattr(payload_data, "lagna_sign", "") or ""
        birth_time_precision = getattr(payload_data, "birth_time_precision", "exact") or "exact"

        from .boosts import _YOGAKARAKA_PLANET
        yk_planet = _YOGAKARAKA_PLANET.get(lagna_sign, "")
        # 2026-08-22 fix (method #8): no longer re-applying a flat 1.25x here
        # -- eff_strengths already carries yk_mod (0.90/1.18-1.25) for this
        # planet via astro.py::_compute_eff_strengths. yk_planet itself is
        # still resolved above/used below (dasha-continuity criterion), just
        # not re-multiplied into adjusted_strength a second time.
        yogakaraka_mult: Dict[str, float] = {}

        war_result = composite_v2.compute_graha_yuddha_dual_criteria(planet_longitudes)
        graha_yuddha_mult = war_result["graha_yuddha_mult"]

        # Node comparability (replaces the old cap_node_base_strength()
        # [0.6, 0.9]-absolute-band cap, which assumed base_strength's [0,1]
        # scale): eff_strength has no shared ceiling across planets, so
        # instead cap a node's contribution relative to THIS chart's own
        # strongest classical planet -- preserving the same classical
        # guarantee ("a node, having no real Shadbala, can never out-rank a
        # real Shadbala-backed planet") on eff_strength's own scale rather
        # than a hardcoded absolute number.
        _CLASSICAL_PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")
        _classical_eff = {p: float(v) for p, v in eff_strengths.items() if p in _CLASSICAL_PLANETS}
        _max_classical_eff = max(_classical_eff.values()) if _classical_eff else 0.0

        adjusted_strength: Dict[str, float] = {}
        for planet, _ev in eff_strengths.items():
            val = float(_ev)
            if planet in ("Rahu", "Ketu") and _max_classical_eff > 0:
                val = min(val, 0.9 * _max_classical_eff)
            yk = float(yogakaraka_mult.get(planet, 1.0))
            gy = float(graha_yuddha_mult.get(planet, 1.0))
            adjusted_strength[planet] = round(val * yk * gy, 6)

        d10_planet_sign = getattr(payload_data, "d10_planet_sign", {}) or {}
        d10_lagna_sign = getattr(payload_data, "d10_lagna_sign", "") or ""
        d10_planet_dignities = getattr(payload_data, "d10_planet_dignities", {}) or {}
        d10_chart = {"Lagna": d10_lagna_sign, **d10_planet_sign}
        d10_strength = composite_v2.compute_d10_strength(d10_chart, d10_planet_dignities)

        wealth_bonus = composite_v2.compute_wealth_bonus_per_planet(house_lords, planet_house)
        # GAP FIX (Phase B dasha-continuity strongest_planet): composite_v2's
        # compute_dasha_continuity_bonus_per_planet() accepts a
        # `strongest_planet` criterion (spec §8) but it was never passed here,
        # silently defaulting to "" and disabling that criterion entirely.
        # payload_data.eff_strengths (set earlier this session, see the
        # "Top planets by effective strength" log line) is the chart's own
        # ranked effective-strength dict -- reuse its top planet rather than
        # recomputing anything.
        _eff_strengths_for_dasha = getattr(payload_data, "eff_strengths", {}) or {}
        strongest_planet = max(_eff_strengths_for_dasha, key=_eff_strengths_for_dasha.get) if _eff_strengths_for_dasha else ""
        dasha_continuity_bonus = composite_v2.compute_dasha_continuity_bonus_per_planet(
            dasha_sequence, atmakaraka=atmakaraka, amatyakaraka=amatyakaraka, yogakaraka=yk_planet,
            strongest_planet=strongest_planet,
        )
        birth_time_confidence_factor = composite_v2.compute_birth_time_confidence_factor(birth_time_precision)

        # GAP FIX (Phase B d9_planet_dignities): same pattern as the
        # planet_dignities (D1) backfill above -- payload_data.d9_planet_dignities
        # is populated upstream (engine_io.py) by astro.py::compute_dignity(),
        # whose vocabulary is the NARROW EXALTED/DEBILITATED/OWN/MOOLATRIKONA/""
        # scheme, "" being a legitimate NEUTRAL-relationship result. But
        # composite_v2._D9_DIGNITY_SCORE / compute_d9_sustainability_mult() is
        # built for the FULLER five-fold scheme from dignity.py::dignity_state()
        # (FRIEND/GREAT_FRIEND/NEUTRAL/ENEMY/GREAT_ENEMY), so every planet the
        # narrow scheme left at "" was silently collapsing to
        # compute_d9_sustainability_mult("") == neutral 1.0 flat via the 0.50
        # default score, pinning compute_d9_gate() at ~1.0 for nearly every
        # field regardless of actual D9 placement. Backfill with dignity_state()
        # (which never returns "") for any planet the narrow live label left
        # blank, using each planet's own D9 sign from
        # payload_data.divisional_charts["D9_navamsha"] (the same {planet:
        # sign} map engine_io.py itself builds d9_planet_dignities from).
        # Purely additive: does not read or write payload_data.d9_planet_dignities
        # itself, so live consumers (score_navamsha_adjustment, dashamsha/knrao/
        # jaimini D9 checks) are untouched.
        _v2_d9_dignities = dict(getattr(payload_data, "d9_planet_dignities", {}) or {})
        _d9_chart_for_dig = getattr(payload_data, "divisional_charts", {}) or {}
        _d9_signs_for_dig = _d9_chart_for_dig.get("D9_navamsha", {}) or {}
        if _d9_signs_for_dig:
            from .dignity import dignity_state as _dignity_state_d9
            _all_d9_signs = {
                p: s for p, s in _d9_signs_for_dig.items()
                if p != "Lagna" and isinstance(s, str) and s
            }
            for _p, _s in _all_d9_signs.items():
                if _v2_d9_dignities.get(_p):
                    continue
                try:
                    _v2_d9_dignities[_p] = _dignity_state_d9(
                        _p, _s, planet_signs=_all_d9_signs,
                    )
                except Exception:
                    continue

        return {
            "adjusted_strength": adjusted_strength,
            "d10_strength": d10_strength,
            "wealth_bonus": wealth_bonus,
            "dasha_continuity_bonus": dasha_continuity_bonus,
            "birth_time_confidence_factor": birth_time_confidence_factor,
            "d9_planet_dignities": _v2_d9_dignities,
            # Audit-pass additions (2026-08-20): additive-only, not consumed by
            # any existing caller — kept here purely so the per-field narrative
            # print below (see _finalize_published_results()) can re-derive the
            # §8/§8.5 dasha-sustainability picture without recomputing anything
            # already computed above in this function.
            "_dasha_narrative_inputs": {
                "dasha_sequence": dasha_sequence,
                "current_age": current_age,
                "atmakaraka": atmakaraka,
                "amatyakaraka": amatyakaraka,
                "yogakaraka": yk_planet,
                "strongest_planet": strongest_planet,
            },
        }
    except Exception as _v2_exc:
        logger.debug("composite_v2 chart primitives computation skipped: %s", _v2_exc)
        return None


def _composite_v2_field_tier2_bonus(
    field_id: str, field_label: str, field_affinity: Dict[str, float], payload_data,
    method_log: Dict[str, Any] | None = None,
) -> Dict[str, float]:
    """Phase B (shadow-score migration, GAP 2): per-field, per-planet Tier-2
    factor contributed by Sudarshana Chakra, KP, and K.N. Rao convergence --
    planets identified as confirming this field get a mild +6% multiplier,
    matching the modest scale of the other Tier-2 factors (maitri +/-5%,
    avastha +/-5 to -6.5%).

      - Sudarshana (field_methods/sudarshana.py::score_sudarshana) returns
        `converging_lords: List[str]` directly, and is a cheap, pure function
        of (label, affinity, payload) with no expensive external calls --
        safe and inexpensive to call a second time here for the shadow path
        (the live path already computes it once per field inside
        compute_field_method_bundle(); this shadow call is independent and
        never overwrites/feeds that live call).
      - KP (field_methods/kp.py::score_kp) and K.N. Rao
        (field_methods/knrao.py::score_knrao) previously returned no
        planet-identifying signal at all (only a scalar score plus
        signal-named, not planet-named, components), so this factor was
        DELIBERATELY SKIPPED for both in an earlier Phase B pass. Both
        functions now additionally return a purely-additive
        `metadata["confirming_planets"]` key (KP: its H10 sub-lord/
        sub-sub-lord/sign-lord/star-lord cuspal chain; K.N. Rao: any planet
        with a positive `{planet}_contribution` component -- both sourced
        from local variables/components those functions already compute,
        with no change to their existing score/components/trace output).
        Rather than re-invoking score_kp/score_knrao a second time per field
        here (expensive relative to Sudarshana -- full cuspal-chain/dasha-
        thread computation), this reads their already-computed result off
        the field row's `method_log` (built once per field by
        compute_field_method_bundle() on the live path) when the caller
        supplies it. If `method_log` is omitted/unavailable, KP/K.N. Rao
        simply contribute no bonus this call (Sudarshana still does) --
        never a crash, and never a re-derivation of their logic.

    Defensive: returns {} on any failure, so a missing/malformed payload
    attribute never breaks the live response (this feeds an additive-only
    shadow score, never final_score/hard_lockout/rank).
    """
    bonus: Dict[str, float] = {}
    try:
        from Field_Determination.field_methods.sudarshana import score_sudarshana
        _sud = score_sudarshana(field_label or field_id, field_affinity or {}, payload_data)
        converging = set(_sud.get("converging_lords", []) or [])
        for _p in converging:
            bonus[_p] = 1.06
    except Exception as _sud_exc:
        logger.debug("composite_v2 field Tier-2 Sudarshana bonus skipped for %s: %s", field_id, _sud_exc)

    try:
        for _method_name in ("kp", "knrao"):
            _entry = (method_log or {}).get(_method_name, {}) or {}
            _confirming = (_entry.get("metadata", {}) or {}).get("confirming_planets", []) or []
            for _p in _confirming:
                bonus[_p] = max(bonus.get(_p, 1.0), 1.06)
    except Exception as _kn_exc:
        logger.debug("composite_v2 field Tier-2 KP/KNRao bonus skipped for %s: %s", field_id, _kn_exc)

    # Instrumentation pass 5 (cross-verification, §9 audit): print the final
    # per-planet Tier-2 confirmation bonus this function produced (KP cuspal
    # chain, K.N. Rao triple-10th confirmation, Sudarshana Chakra convergence
    # -- whichever of the three actually contributed for this chart/field),
    # plus one dynamic narrative paragraph. Read-only: does not change what
    # is returned/used downstream.
    _label_for_print = field_label or field_id
    if bonus and _VERBOSE_FIELD_LOG:
        for _pname, _mult in bonus.items():
            # print(f"Cross-verification confirmation bonus — {_label_for_print}: {_pname}: "
            #       f"x{round(_mult, 4)} ({round((_mult - 1.0) * 100, 1)}% confirmation)")
            pass
    _sud_planets = sorted({p for p, m in bonus.items() if m >= 1.06}) if bonus else []
    _kp_knrao_planets = sorted({
        p for _mn in ("kp", "knrao")
        for p in (((method_log or {}).get(_mn, {}) or {}).get("metadata", {}) or {}).get("confirming_planets", []) or []
    })
    if bonus:
        _narrative = (
            f"[CROSS-VERIFICATION NARRATIVE] Field '{_label_for_print}': "
            f"{len(bonus)} planet(s) received a Tier-2 confirmation bonus "
            f"({', '.join(sorted(bonus.keys()))}). "
        )
        if _kp_knrao_planets:
            _narrative += (
                f"KP cuspal-chain / K.N. Rao contribution-based confirmation supports "
                f"{', '.join(_kp_knrao_planets)}. "
            )
        if _sud_planets:
            _narrative += (
                f"Sudarshana Chakra (Lagna+Sun+Moon-as-Lagna) convergence supports "
                f"{', '.join(_sud_planets)}. "
            )
        _narrative += "Each confirming planet's already-derived strength was multiplied by x1.06 (a modest +6% add-on, never an independent basis for inclusion)."
    else:
        _narrative = (
            f"[CROSS-VERIFICATION NARRATIVE] Field '{_label_for_print}': no KP, K.N. Rao, or "
            f"Sudarshana Chakra confirmation found for this chart/field (either the "
            f"Sudarshana overlay and method_log's KP/K.N. Rao confirming_planets were both "
            f"empty/unavailable, or no planet met the convergence threshold) — no Tier-2 "
            f"cross-verification bonus applied."
        )
    if _VERBOSE_FIELD_LOG:
        # print(_narrative)
        pass

    return bonus


def _finalize_published_results(results, payload_data, *, llm_used=False):
    """One authoritative finalization path for CLI, reports and API callers."""
    # NOTE (2026-08-18): this initial sort-by-flat-blend-final_score is now
    # PROVISIONAL, not authoritative -- it only establishes a stable working
    # order for the downstream eligibility/lockout gates below (which need
    # *some* deterministic order to iterate over). The ranking that actually
    # ships is decided later in this function by compute_tiered_ranking()
    # (search "Tiered ranking override" below), which supersedes this order
    # entirely for every eligible field. Left in place (not removed) because
    # the hard-lockout/leakage-guard passes between here and there were
    # written assuming a pre-sorted list to operate on.
    results = _sort_by_final_score_desc(results)
    results = _attach_registry_before_return(results)
    results, payload_data.release_candidate_readiness = apply_release_4_7(
        results, payload_data.canonical_fact_quality_report, payload_data
    )
    results = apply_publication_ranking_policy(results)
    results = _enforce_hard_lockout_publication_order(results)
    # Gap-audit fix (2026-08, "fix both, then yes" round): hard-lockout
    # reordering just above can promote a field into the true top 5 purely
    # by pushing hard_lockout/exploratory rows below it -- it changes `rank`
    # without touching final_score, so a field that never looked like a
    # top-5 uncorroborated-affinity risk to apply_publication_ranking_policy()
    # can still end up published there. Confirmed on Aiswaryya's chart:
    # "chemistry" reached rank 3 exactly this way, with the same weak
    # dashamsha/siddhamsha profile (9.79/18.01) as fields the guard already
    # catches, and no same-cluster corroboration in the astrological top 10
    # -- but it was invisible to both guard passes inside
    # apply_publication_ranking_policy() because it only crossed into the
    # top 5 here, after that function had already returned. Re-run the same
    # guards against the rank order that's actually about to publish, then
    # re-run hard-lockout ordering once more so `rank` reflects any fresh
    # discount (a field discounted here could in principle also cross the
    # hard_lockout score floor, though hard_lockout itself is not
    # recomputed -- consistent with how every other publication-stage
    # discount in this pipeline already treats that flag as fixed earlier).
    results = reapply_leakage_guards_post_lockout(results)
    results = _enforce_hard_lockout_publication_order(results)
    # --- Tiered ranking override (2026-08-18) -------------------------
    # DELINKED: from this point on, the flat 9-method linear blend (i.e.
    # everything `_sort_by_final_score_desc()` at the top of this function
    # sorted by, and everything computed via compute_field_method_bundle()'s
    # combined_score / _method_boost inside _score_one_field()) is no
    # longer the ranking authority. By-hand audits against two real charts
    # (Ramsunder and Akash Shanmugham -- see
    # md/ENGINE_TRANSPARENCY_GAP_AUDIT_2026-08-17.md and the follow-up
    # tiering discussion) showed the flat blend's published #1 field
    # consistently had the WEAKEST astrological method evidence among top
    # candidates on both charts, with `affinity_score` (non-astrological)
    # actually driving the ranking instead.
    #
    # compute_tiered_ranking() replaces field ranking with a 3-tier
    # classical-authority model: Tier 1 (Parashara+Dashamsha+Jaimini+KNRao)
    # decides outright unless it's a near-tie, Tier 2 (KP+Sudarshana) breaks
    # a Tier-1 near-tie, Tier 3 (Shashtiamsha+structural_patterns) breaks a
    # Tier-2 near-tie. See jyotish/tiered_ranking.py for the full design
    # note, weights, and near-tie threshold.
    #
    # This does NOT touch anything upstream: compute_field_method_bundle(),
    # the multiplicative score gates in _score_one_field(), hard_lockout,
    # aptitude/contraindication gates, and the safety partition just above
    # (valid/locked/exploratory_only) are all preserved exactly as before --
    # compute_tiered_ranking() re-applies that same partition itself and
    # only re-orders within the eligible ("valid") group. The old flat-blend
    # final_score survives per-row as `final_score_legacy_blend` for
    # audit/comparison; it is intentionally no longer read by anything
    # downstream of this call.
    # §6 remediation (2026-08): thread birth_time_precision through so
    # Tier 3's Shashtiamsha (D60) component is gated off when birth time
    # isn't exact -- see compute_tiered_ranking()'s docstring in
    # jyotish/tiered_ranking.py for the full rationale (mirrors the
    # existing KP weight gating precedent at ~line 2211 above).
    # §11 remediation (2026-08-19): filter 4 ("D60/BAV tie-break") also
    # requires Bhinnashtakavarga alongside D60 -- previously absent
    # entirely. Computed once per native (BAV bindus don't vary per field,
    # only which planet each field cares about does), then reduced to one
    # 0-100 score per field_id using that field's own top-affinity planet's
    # BAV bindus in H10 (the career house) -- passed to compute_tiered_
    # ranking() where it's blended lightly into tier3_score for near-top
    # ties only (see that function's bav_tiebreak_scores docstring).
    _bav_tiebreak_scores: Dict[str, float] = {}
    try:
        _bav_planet_signs = getattr(payload_data, "planet_signs", {}) or {}
        _bav_lagna_sign = getattr(payload_data, "lagna_sign", "") or ""
        if _bav_planet_signs and _bav_lagna_sign:
            from .ashtakavarga import compute_bav_points
            _bav_house_bindus = compute_bav_points(_bav_planet_signs, _bav_lagna_sign)
            for _row in results:
                _fid = str(_row.get("field_id", ""))
                if not _fid:
                    continue
                _field_aff = BRANCH_PLANET_AFFINITY.get(_fid, {})
                if not _field_aff:
                    continue
                _core_planet = max(_field_aff, key=_field_aff.get)
                _bindus_h10 = _bav_house_bindus.get(_core_planet, {}).get(10, 0)
                # BAV bindus per house per planet range 0-8 classically.
                _bav_tiebreak_scores[_fid] = round(min(8, max(0, _bindus_h10)) / 8.0 * 100.0, 2)
    except Exception as _bav_exc:
        logger.debug("BAV tie-break score computation skipped: %s", _bav_exc)
        _bav_tiebreak_scores = {}

    # Phase B (shadow-score migration, 2026-08-19): compute the §10-refined
    # composite_v2 score per field ALONGSIDE the live scoring path, purely
    # for comparison/audit. Chart-level (field-independent) primitives are
    # built once and cached; only the field-dependent d9_gate is computed
    # per field. This block is strictly additive -- it only ever adds the
    # `field_score_v2_refined` (and `field_score_v2_components`) keys to a
    # row, never touches final_score/hard_lockout/rank/anything
    # compute_tiered_ranking() below reads, and a single field's failure is
    # caught and skipped so it can never break the live response.
    _v2_common = _build_composite_v2_chart_primitives(payload_data)
    if _v2_common is not None:
        for _row in results:
            _fid = str(_row.get("field_id", ""))
            _field_aff = BRANCH_PLANET_AFFINITY.get(_fid, {})
            if not _field_aff:
                continue
            try:
                # GAP FIX (2026-08-20, deep D1/D9/D10 audit): composite_v2.
                # compute_d9_gate() -- the function that had been gating the
                # D1/D10 term in the LIVE published v2 score -- is dignity-
                # only: it never touches D9 house placement relative to the
                # D9 lagna, Vargottama, or the D9 lagna lord's own strength.
                # A richer, already-correct implementation of exactly this
                # (Field_Determination/field_methods/navamsha.py::
                # score_navamsha_adjustment(), wired into the OTHER,
                # non-v2 scoring path via field_methods/__init__.py) already
                # blends planet-level D9 dignity with D9-lagna-lord dignity/
                # placement and D9 vidya-house-lord strength into the same
                # [0.85, 1.15] bounded multiplier contract -- it was simply
                # never called from the v2-primary path, so a classically
                # much stronger placement (e.g. Vargottama + D9-kendra) was
                # scoring identically to a merely-well-dignified planet with
                # neither. Routing through the richer function here instead
                # of the dignity-only one; same [0.85, 1.15] contract, so no
                # other caller of `_d9_gate` below needs to change.
                from Field_Determination.field_methods.navamsha import score_navamsha_adjustment as _score_navamsha_adj
                _d9_adj_result = _score_navamsha_adj(
                    payload_data, _row.get("domain", ""), _field_aff, _fid,
                )
                _d9_gate = _d9_adj_result.get("multiplier", 1.0)
                # GAP 2 (field-specific Tier-2, see _composite_v2_field_tier2_bonus
                # docstring for the Sudarshana/KP/K.N. Rao convergence
                # rationale): Sudarshana convergence is field-specific, so it's
                # layered onto a
                # per-field COPY of the chart-level adjusted_strength dict
                # here rather than in _build_composite_v2_chart_primitives()
                # (which is computed once per chart, before any field is
                # known). Applied as a simple extra multiplier on the
                # already-Tier-2-adjusted strength -- consistent in scale
                # with the other Tier-2 factors (all ~+/-5-13%).
                _field_label = _row.get("field_label", _fid)
                _sud_bonus = _composite_v2_field_tier2_bonus(
                    _fid, _field_label, _field_aff, payload_data, _row.get("method_log", {}))
                _adjusted_strength_field = _v2_common["adjusted_strength"]
                if _sud_bonus:
                    _adjusted_strength_field = {
                        p: round(v * _sud_bonus.get(p, 1.0), 6)
                        for p, v in _v2_common["adjusted_strength"].items()
                    }
                # GAP FIX (2026-08-20, defensibility audit): §9's whole
                # cross-verification layer (KP cuspal chain, K.N. Rao 2-of-3,
                # Sudarshana overlay, Yogakaraka, Argala-H10, D24, Vimshopaka
                # Bala, ...) was already computed, printed, and audited every
                # run via `_score_one_field()`'s gap_boost/gap_penalty
                # accumulator (see engine.py's per-field "[FIELD SCORE]"
                # line and gap_detail breakdown) -- but once v2 became the
                # primary/authoritative score, that layer was never actually
                # read by compute_field_score(), so it stopped influencing
                # the published ranking at all. Reusing the existing,
                # already-capped accumulator values (acc.gap_boost in
                # [-0.20, 0.55], acc.gap_penalty >= 0, both stored on this
                # row as "acc.gap_boost"/"acc.gap_penalty") as a bounded
                # confirming/dampening multiplier on the D1/D10 term --
                # same treatment as d9_gate just above, not a new scoring
                # category -- restores cross-verification's real classical
                # role: widening the gap between a field several
                # independent techniques agree on and one only the base
                # D1/D10 promise favors.
                # Read the plain "gap_boost"/"gap_penalty" keys, not
                # "acc.gap_boost"/"acc.gap_penalty" -- by the time `results`
                # reaches _finalize_published_results() (this function), rows
                # have already passed through the _top35_for_llm rebuild
                # step in run_engine(), which only carries forward the
                # explicitly-listed plain-named keys (see that block's own
                # gap_boost/gap_penalty fix). Confirmed live: a first attempt
                # reading "acc.gap_boost" here always silently read the 0.0
                # default (cross-verification printed as 1.0 for every
                # field, no actual differentiation) -- same failure class as
                # the two gap_boost export bugs fixed earlier this session.
                _corrob_mult = (
                    (1.0 + float(_row.get("gap_boost", 0.0) or 0.0))
                    * (1.0 - float(_row.get("gap_penalty", 0.0) or 0.0))
                )
                _v2_result = composite_v2.compute_field_score(
                    _field_aff,
                    _adjusted_strength_field,
                    _v2_common["d10_strength"],
                    _d9_gate,
                    _v2_common["wealth_bonus"],
                    _v2_common["dasha_continuity_bonus"],
                    _v2_common["birth_time_confidence_factor"],
                    _corrob_mult,
                )
                _row["field_score_v2_refined"] = _v2_result["field_score"]
                _row["field_score_v2_components"] = _v2_result

                # Per-field dasha-sustainability check + narrative (wired
                # live 2026-08-20; previously diagnostic-only -- see the
                # git history of this comment for that prior state).
                # jyotish.dasha_longevity's score_dasha_longevity() computes
                # the §8.5 reject/downrank verdict and the window-wide
                # weak/afflicted-MD ("pivot window") flags. The reject
                # verdict is stashed on `_row` below and actually applied to
                # final_score (a real x0.55 downrank, re-sorted into rank
                # order) right after compute_tiered_ranking() runs later in
                # this function -- see the "§8.5 dasha-coverage
                # reject/downrank" block there for why it must happen AFTER
                # that call (compute_tiered_ranking() overwrites final_score
                # wholesale from tier1/2/3 evidence, so applying the penalty
                # here would just be clobbered). The pivot-window cautions
                # remain narrative-only per spec §8 item 6 -- printed below,
                # never fed into any score.
                try:
                    _dni = _v2_common.get("_dasha_narrative_inputs", {})
                    _dl_result = dasha_longevity.score_dasha_longevity(
                        _dni.get("dasha_sequence"),
                        _dni.get("current_age"),
                        _field_aff,
                        atmakaraka=_dni.get("atmakaraka", ""),
                        amatyakaraka=_dni.get("amatyakaraka", ""),
                        yogakaraka=_dni.get("yogakaraka", ""),
                        strongest_planet=_dni.get("strongest_planet", ""),
                    )
                    # GAP FIX (2026-08-20, this audit pass): §8.5's reject/
                    # downrank was computed here but never applied to any
                    # score the live path reads (see the module docstring
                    # above -- field_score_v2_refined is a shadow score that
                    # compute_tiered_ranking() never touches, so this used to
                    # be diagnostic-only). Stash the reject verdict on the row
                    # now; the actual final_score multiplication happens AFTER
                    # compute_tiered_ranking() below (that call fully
                    # overwrites final_score from tier1/2/3, so applying the
                    # penalty before it would just get clobbered).
                    _row["_dasha_coverage_reject"] = bool(_dl_result.get("dasha_coverage_reject"))
                    _row["_dasha_coverage_reject_end_age"] = _dl_result.get("last_strong_affinity_end_age")
                    # score_dasha_longevity() also computes a continuous
                    # "staying power" multiplier (bounded [0.90, 1.25],
                    # stable_fraction + special-criteria based) -- separate
                    # from the boolean hard-reject verdict above. A 2026-08-22
                    # attempt to wire this into final_score (stashed here,
                    # applied in the post-tiered-ranking block below) was
                    # reverted the same day after full-engine regression
                    # testing showed an outsized, unpredictable effect on real
                    # charts (see the REVERTED note at the application site
                    # below for detail) -- so this multiplier is intentionally
                    # left unread again past this point (available on
                    # `_dl_result` for the debug print only), pending a more
                    # heavily-damped, properly-tested wiring in a future pass.
                    _special = _dl_result.get("special_criteria_planets") or {}
                    _special_txt = (
                        "; ".join(f"{p} ({', '.join(r)})" for p, r in _special.items())
                        if _special else "none"
                    )
                    _reject_txt = (
                        f"REJECTED — dasha coverage ends at age "
                        f"{_dl_result.get('last_strong_affinity_end_age')}, below the ~35-40 "
                        f"sustainability threshold (applying x{dasha_longevity._DASHA_COVERAGE_REJECT_MULT} "
                        f"downrank to final_score)"
                        if _dl_result.get("dasha_coverage_reject")
                        else f"coverage sustains through the window (multiplier x{_dl_result.get('multiplier')})"
                    )
                    _pivot_txt = "; ".join(_dl_result.get("window_cautions") or []) or "none flagged"
                    if _VERBOSE_FIELD_LOG:
                        print(
                            f"[DASHA-SUSTAINABILITY NARRATIVE] Field '{_row.get('field_label', _fid)}': "
                            f"current MD lord {_dl_result.get('current_md_lord')} "
                            f"({_dl_result.get('years_remaining_current_md')}y remaining); "
                            f"{_reject_txt}. Special-weight dasha lords in window: {_special_txt}. "
                            f"Pivot/upskilling windows (weak- or afflicted-lord MDs flagged, not "
                            f"disqualifying): {_pivot_txt}."
                        )
                except Exception as _dl_exc:
                    logger.debug("dasha-sustainability narrative print skipped for field %s: %s", _fid, _dl_exc)
                # GAP FIX (Phase B node cap, migration plan §1a.4):
                # diagnostic-only flag -- surfaces when a field's dominant
                # significator is Rahu/Ketu for review; the base-strength
                # cap above already does the real score-limiting work, this
                # is not an additional penalty.
                _v2_result["dominant_significator_is_node"] = composite_v2.dominant_significator_is_node(_field_aff)
            except Exception as _v2_field_exc:
                logger.debug("composite_v2 shadow score skipped for field %s: %s", _fid, _v2_field_exc)

    results = compute_tiered_ranking(
        results,
        birth_time_precision=getattr(payload_data, "birth_time_precision", "exact") or "exact",
        bav_tiebreak_scores=_bav_tiebreak_scores or None,
    )
    # --- v2 composite becomes the primary/authoritative final_score -------
    # (2026-08-20, this pass): composite_v2.compute_field_score()'s spec-§10
    # formula (`field_score_v2_refined`, computed per field in the loop
    # above) is no longer a small bounded confirming nudge on top of the
    # older tier1/tier2/tier3 compute_tiered_ranking() output -- it IS the
    # score that ranks and publishes now. compute_tiered_ranking() just
    # above is still called (and left untouched) for two reasons that
    # remain useful: (1) it re-applies the hard_lockout/aptitude/
    # contraindication safety partition (valid/locked/exploratory_only)
    # this function relies on being present on every row, and (2) its
    # tier1_score/tier2_score/tier3_score/tier_decision_trace outputs stay
    # on each row as reference/audit data -- they are simply no longer read
    # to decide final_score or rank. The old tier-based final_score is
    # preserved per row as `final_score_tiered_ranking_legacy` for exactly
    # that transparency/comparison purpose. A defensive fallback covers the
    # rare case where `field_score_v2_refined` failed to compute for a row
    # (see the per-field try/except above): rather than let a missing
    # shadow score crash ranking, that row falls back to its tiered score
    # and a warning is logged so the gap stays visible.
    _v2_primary_applied = 0
    _v2_primary_fallback = 0
    for _row in results:
        _fid = _row.get("field_id", "")
        _tiered_fs = float(_row.get("final_score", 0.0) or 0.0)
        _row["final_score_tiered_ranking_legacy"] = round(_tiered_fs, 2)
        _v2_fs = _row.get("field_score_v2_refined")
        if _v2_fs is None:
            logger.warning(
                "field_score_v2_refined missing for field %s -- falling back to "
                "tiered-ranking final_score (%.2f) as this row's published final_score.",
                _fid, _tiered_fs,
            )
            _v2_primary_fallback += 1
            _row["final_score"] = round(_tiered_fs, 2)
        else:
            _row["final_score"] = round(float(_v2_fs), 2)
            _v2_primary_applied += 1
        if _VERBOSE_FIELD_LOG:
            print(
                f"[V2-PRIMARY FINAL_SCORE] {_row.get('field_label', _fid)}: "
                f"final_score={_row.get('final_score'):.2f} (was tiered_score={_tiered_fs:.2f})"
            )
    results = _sort_by_final_score_desc(results)
    print(
        "[V2-PRIMARY FINAL_SCORE NARRATIVE] final_score/rank now derive from "
        "composite_v2.compute_field_score() (spec §10) as the primary/authoritative "
        f"formula, not the older tier1/2/3 blend -- {_v2_primary_applied} field(s) used "
        f"their v2 composite directly, {_v2_primary_fallback} field(s) fell back to their "
        "tiered-ranking score because field_score_v2_refined was unavailable. The old "
        "tiered score is preserved per row as final_score_tiered_ranking_legacy for "
        "audit/comparison."
    )
    # §8.5 dasha-coverage reject/downrank (2026-08-20, this audit pass):
    # apply the reject/downrank multiplier on the v2-based final_score set
    # just above, using the verdict stashed on each row during the
    # per-field loop above. Mirrors the existing 0.90x same-domain penalty
    # in _apply_interdomain_normalization() (a direct multiplicative
    # discount on final_score) rather than inventing a new mechanism; this
    # is a much heavier discount (x0.55, dasha_longevity._DASHA_COVERAGE_
    # REJECT_MULT) because §8.5 is a hard sustainability disqualifier, not
    # a soft same-domain crowding signal. Re-sort + restamp rank
    # immediately after (same discipline decision_axes.py's penalty uses,
    # see run_engine()'s comment on that) so the penalty actually reorders
    # published output instead of being computed but never surfacing.
    _dasha_reject_applied = False
    for _row in results:
        if _row.pop("_dasha_coverage_reject", False):
            _row["final_score"] = round(
                float(_row.get("final_score", 0.0) or 0.0)
                * dasha_longevity._DASHA_COVERAGE_REJECT_MULT,
                2,
            )
            _row["dasha_coverage_reject_applied"] = True
            _row["dasha_coverage_reject_end_age"] = _row.pop("_dasha_coverage_reject_end_age", None)
            _dasha_reject_applied = True
            _row.pop("_dasha_longevity_multiplier", None)
        else:
            _row.pop("_dasha_coverage_reject_end_age", None)
            # ATTEMPTED GAP FIX (2026-08-22, this audit pass) -- REVERTED SAME
            # DAY after regression testing: this block applied the continuous
            # dasha-longevity "staying power" multiplier (bounded [0.90, 1.25])
            # for rows that did NOT hard-reject, since it was previously
            # computed and discarded (see the stash point above). Full-engine
            # regression testing (tests/test_career_track_regressions.py::
            # test_ramsunder_prioritizes_materials_route_over_land_symbolic_
            # noise) showed this produced a much larger, less-predictable
            # effect than intended on at least one real chart: a field whose
            # dominant significator happened to carry strong dasha coverage
            # (history_archaeology, multiplier 1.168x) was pushed to rank 1
            # ahead of a field with a substantially higher underlying v2
            # composite score (materials_science_engineering, v2 106.2 vs
            # history's 98.05, but only a 1.048x multiplier) -- the same
            # "small per-field nudge with an unexpectedly large aggregate
            # effect on final ranking" failure mode as the astro.py eff_
            # strength revert above. Reverted; `score_dasha_longevity()`'s
            # continuous multiplier is computed but intentionally left
            # unapplied again, same as before this pass, pending a properly
            # tested (likely much more heavily damped) wiring in a future
            # pass. The hard reject/downrank path above this block is
            # unaffected and remains live.
            _row.pop("_dasha_longevity_multiplier", None)
    if _dasha_reject_applied:
        results = _sort_by_final_score_desc(results)

    # §11 remediation (2026-08-20, this pass): "core-three" (D1/D9/D10)
    # minimum-threshold filter. Spec: a field whose vector planets ALL show
    # near-zero D9 representation must not enter the final Top-N regardless
    # of composite score. "Near-zero representation" is operationalised as
    # every one of the field's affinity-vector planets landing in the
    # bottom third of compute_d9_sustainability_mult()'s documented
    # [0.85, 1.15] range, i.e. <= 0.90 (0.85 + (1.15-0.85)/3, rounded to a
    # clean two-decimal cutoff). This is a conservative, explicit choice --
    # the spec gives no exact number -- chosen so a field is only caught
    # when EVERY vector planet is genuinely weak in D9 (not just below
    # neutral), not merely when the field's *average* D9 gate dips low
    # (that softer case is already covered by the bounded shadow-score
    # bonus in the COMPOSITE-V2 BLEND block above).
    #
    # Convention: mirrors the existing §8.5 dasha-coverage reject filter
    # just below (`dasha_coverage_reject_applied`) -- rows are DOWNRANKED
    # via a heavy multiplicative penalty on final_score, not physically
    # removed from `results`. This keeps the row (and its diagnostics)
    # available to callers/audits while making it effectively impossible
    # for the field to surface in any Top-N slice taken downstream. No
    # existing "true exclude" mechanism was found in this function (there
    # is no top_n/[:N]/head() slicing here -- Top-N selection happens in
    # callers of _finalize_published_results()), so downranking is the
    # only consistent, low-risk option available at this call site.
    _CORE_THREE_D9_FLOOR = 0.90
    _CORE_THREE_EXCLUDE_MULT = 0.01
    _core_three_excluded_count = 0
    if _v2_common is not None:
        for _row in results:
            _fid = str(_row.get("field_id", ""))
            _field_aff = BRANCH_PLANET_AFFINITY.get(_fid, {})
            # Audit fix (2026-08-20, deep D1/D9/D10 audit): this filter is
            # named and commented as a "core-three" check -- only exclude
            # when the field's TOP-3 significators are uniformly D9-weak,
            # the same convention navamsha.py's own §11 filter uses
            # (`_core_three = top_planets[:3]`) -- but the code here was
            # actually checking EVERY nonzero-weight affinity planet, often
            # more than 3. That's stricter than the filter's own stated
            # intent: a field whose top 3 significators are genuinely
            # D9-collapsed could still dodge exclusion if a 4th or 5th
            # minor-weight planet happened to sit just above the floor.
            # Restricting to the top-3-by-weight planets, matching
            # navamsha.py's sibling implementation exactly.
            _vector_planets = [p for p, _w in sorted(_field_aff.items(), key=lambda x: -x[1])[:3] if _w]
            if not _vector_planets:
                continue
            try:
                _d9_mults = [
                    composite_v2.compute_d9_sustainability_mult(
                        _v2_common["d9_planet_dignities"].get(p, "")
                    )
                    for p in _vector_planets
                ]
            except Exception as _c3_exc:
                logger.debug("core-three filter skipped for %s: %s", _fid, _c3_exc)
                continue
            if _d9_mults and all(m <= _CORE_THREE_D9_FLOOR for m in _d9_mults):
                _prev_fs = float(_row.get("final_score", 0.0) or 0.0)
                _row["core_three_excluded_applied"] = True
                _row["core_three_d9_mults"] = _d9_mults
                _row["final_score"] = round(_prev_fs * _CORE_THREE_EXCLUDE_MULT, 2)
                _core_three_excluded_count += 1
    if _core_three_excluded_count:
        results = _sort_by_final_score_desc(results)

    # --- v2-scale D60/BAV tie-break (2026-08-20, this pass) ---------------
    # Spec section 6/13 requirement: use D60 (Shashtiamsha) / Bhinnashtakavarga
    # only to break ties between fields that are within ~1 composite point of
    # each other. tiered_ranking.py's own D60/BAV tie-break machinery
    # (NEAR_TIE_BAND ~= 3%, operating on tier1/tier2/tier3_score) was
    # calibrated for the old tier1/2/3 blend's scale and is no longer the
    # right gate now that `final_score` is `field_score_v2_refined` (a 0-100
    # v2-composite scale, spec-§10). Re-anchor the same D60/BAV signal to the
    # new scale here: group fields whose v2-based final_score values sit
    # within ~1.0 point of a cluster leader, and within each such cluster,
    # reorder by the D60/BAV signal ALREADY computed for every row --
    # `tier3_score` (Shashtiamsha+structural_patterns, optionally blended
    # 85/15 with `bav_tiebreak_score` inside compute_tiered_ranking() above)
    # -- rather than recomputing D60/BAV from scratch. This only reorders
    # WITHIN a genuine near-tie cluster; it never changes which fields are
    # ranked highly. Mirrors the dasha-reject/core-three convention of a
    # bounded, explainable, deterministic adjustment with its own printed
    # disclosure line.
    _V2_TIE_BREAK_BAND = 1.0
    _v2_tiebreak_groups = 0
    _v2_tiebreak_rows = 0
    if results:
        _ordered = sorted(
            results,
            key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))),
        )
        _clusters: List[List[Dict]] = []
        for _row in _ordered:
            _score = float(_row.get("final_score", 0.0) or 0.0)
            if _clusters:
                _leader_score = float(_clusters[-1][0].get("final_score", 0.0) or 0.0)
                if _leader_score - _score <= _V2_TIE_BREAK_BAND:
                    _clusters[-1].append(_row)
                    continue
            _clusters.append([_row])

        def _d60_bav_signal(r):
            _sig = r.get("tier3_score")
            return float(_sig) if isinstance(_sig, (int, float)) else 0.0

        _rebuilt: List[Dict] = []
        for _cluster in _clusters:
            if len(_cluster) > 1:
                _pre_order = [r.get("field_id", "") for r in _cluster]
                _cluster_sorted = sorted(
                    _cluster, key=lambda r: (-_d60_bav_signal(r), str(r.get("field_id", "")))
                )
                if [r.get("field_id", "") for r in _cluster_sorted] != _pre_order:
                    _v2_tiebreak_groups += 1
                    _v2_tiebreak_rows += len(_cluster_sorted)
                    for _r in _cluster_sorted:
                        _r["v2_tiebreak_applied"] = True
                    _labels = [
                        f"{r.get('field_label', r.get('field_id', ''))} "
                        f"(v2={float(r.get('final_score', 0.0) or 0.0):.2f}, "
                        f"D60/BAV={_d60_bav_signal(r):.2f})"
                        for r in _cluster_sorted
                    ]
                    if _VERBOSE_FIELD_LOG:
                        print(
                            "[TIE-BREAK] v2 composite near-tie (within "
                            f"{_V2_TIE_BREAK_BAND:.1f} point(s)) among {len(_cluster_sorted)} field(s) -- "
                            "resolved by Shashtiamsha (D60)/Bhinnashtakavarga (BAV) tier3_score: "
                            + " > ".join(_labels)
                        )
                _rebuilt.extend(_cluster_sorted)
            else:
                _rebuilt.extend(_cluster)
        results = _rebuilt
        for _idx, _row in enumerate(results, 1):
            _row["rank"] = _idx
            _row["engine_rank"] = _idx
            if "llm_rank" in _row:
                _row["llm_rank"] = _idx
            _row["publication_score"] = _row.get("final_score")

    #§11 audit pass (2026-08-20, this pass): "Field-Level Filters" printout.
    # This block does NOT implement any new filtering/scoring -- it only
    # reports, per field, which of the four §11 filters actually fired
    # against that field using state already computed above/elsewhere in
    # this function (or explicitly reports "NOT IMPLEMENTED" when the
    # underlying logic doesn't exist in code at all, rather than fabricate
    # a status). See the audit note this pass added at the top of this
    # function (search "§11 remediation") for the BAV tie-break wiring, and
    # the "§8.5 dasha-coverage reject/downrank" block above for filter 2.
    #
    # Filter 1 (core-three / D9-sustainability minimum threshold, §11 item
    # 1): implemented this pass (2026-08-20) -- see the core-three block
    # just above this comment for the threshold/downrank rationale.
    # `_core_three_excluded_count` was already computed there.
    _sustainability_downranked_count = 0
    _wealth_uncertain_flag_count = 0
    _d60_tiebreak_count = 0
    _bav_tiebreak_count = 0
    for _row in results:
        _fid = _row.get("field_id", "")
        _label = _row.get("field_label", _fid)
        _statuses = ["INCLUDED"]
        if _row.get("core_three_excluded_applied"):
            _statuses = ["EXCLUDED-core-three"]
        if _row.get("dasha_coverage_reject_applied"):
            _statuses.append("DOWNRANKED-sustainability")
            _sustainability_downranked_count += 1
        _wp = _row.get("wealth_potential") or {}
        if isinstance(_wp, dict) and _wp.get("prestige_strong_wealth_uncertain_flag"):
            _statuses.append("FLAGGED-wealth-uncertain")
            _wealth_uncertain_flag_count += 1
        if _row.get("v2_tiebreak_applied"):
            _statuses.append("TIE-BROKEN-D60")
            _d60_tiebreak_count += 1
            if "bav_tiebreak_score" in _row:
                _statuses.append("TIE-BROKEN-BAV")
                _bav_tiebreak_count += 1
        if _VERBOSE_FIELD_LOG:
            print(
                f"[FIELD-LEVEL FILTER STATUS] {_label} ({_fid}): "
                f"final_score={_row.get('final_score', 0.0):.2f}; status={'+'.join(_statuses)}"
            )
    _bav_module_available = bool(_bav_tiebreak_scores)
    print(
        "[FIELD-LEVEL FILTERS NARRATIVE] "
        f"Core-three (D1/D9/D10) minimum threshold: IMPLEMENTED -- a field is downranked "
        f"(x{_CORE_THREE_EXCLUDE_MULT}, effectively removed from any Top-N) when ALL of its "
        f"affinity-vector planets score <= {_CORE_THREE_D9_FLOOR} on the D9 sustainability "
        f"multiplier (compute_d9_sustainability_mult, range [0.85, 1.15]); "
        f"{_core_three_excluded_count} field(s) excluded this run. "
        f"Sustainability filter (§8.5 dasha-coverage): {_sustainability_downranked_count} field(s) "
        f"downranked (x{dasha_longevity._DASHA_COVERAGE_REJECT_MULT}) for dasha coverage ending "
        f"before the ~35-40 sustainability threshold. "
        f"Wealth filter (§7.4): {_wealth_uncertain_flag_count} field(s) carry the "
        f"prestige_strong_wealth_uncertain flag (zero wealth-bonus-eligible planets across the "
        f"four wealth houses) -- flagged, not excluded. "
        f"Tie-break: {_v2_tiebreak_groups} near-top tie group(s) ({_v2_tiebreak_rows} field(s), "
        f"re-anchored to the v2 composite's own {_V2_TIE_BREAK_BAND:.1f}-point near-tie band) "
        f"resolved via Shashtiamsha (D60); "
        + (
            f"of those, {_bav_tiebreak_count} also had a live Bhinnashtakavarga (BAV) tie-break "
            f"score blended in."
            if _bav_module_available else
            "Bhinnashtakavarga (BAV) tie-break: NOT PRODUCED this run -- jyotish/ashtakavarga.py "
            "is staged and compute_bav_points() is wired in, but bav_tiebreak_scores came back "
            "empty for this chart (e.g. missing planet_signs/lagna_sign on the payload), so every "
            "tier3_score above was decided by Shashtiamsha/structural_patterns alone."
        )
    )
    # Gap fix (2026-08-18, tiered-ranking audit, gap 6): `confidence_band`
    # (and the copy nested in `evidence_summary`) was computed way earlier,
    # inside apply_competency_ontology_layer() (~line 2314, long before
    # _finalize_published_results() even starts) -- against the OLD
    # pre-tiered final_score. compute_tiered_ranking() just overwrote
    # final_score above without anyone recomputing confidence_band to
    # match, so a live run showed the actual #1 field (tier1_score at the
    # top of this run's own range) still labeled "Moderate (relative)"
    # from its old, much-higher-scale relative position -- exactly the
    # stale-vs-published mismatch this report already warns readers about
    # for score_confidence vs confidence_band, except this time it's the
    # SAME field disagreeing with itself. Recompute against the score that
    # actually ships, using this run's own new top score (mirrors
    # competency_ontology.py's own confidence_band(score, top_score)
    # relative-scale fix from the same round).
    _tiered_top_score = max((float(r.get("final_score", 0.0) or 0.0) for r in results), default=0.0)
    for _row in results:
        _row["confidence_band"] = confidence_band(_row.get("final_score", 0.0), _tiered_top_score)
        if isinstance(_row.get("evidence_summary"), dict):
            _row["evidence_summary"]["confidence_band"] = _row["confidence_band"]
    # Gap-audit fix (2026-08-19, chat session, same failure shape as the
    # confidence_band staleness fixed just above): `astrological_score` is
    # set exactly once, inside apply_publication_ranking_policy() in
    # ranking_policy.py ("row['astrological_score'] = float(row.get(
    # 'final_score', ...))"), which runs BEFORE compute_tiered_ranking()
    # above overwrites final_score with the tier-decided value. Nothing
    # re-synced astrological_score afterward, so it kept the OLD pre-tier
    # legacy-blend number -- which had already been through the 20-100
    # min-max stretch (~line 2107 above) plus post-stretch adjustment passes
    # (_apply_medical_governance_rebalance and later boosts) with no
    # re-clamp, so it could exceed its own documented 0-100 bound. Confirmed
    # live on Ramsunder's chart: industrial_engineering published with
    # final_score=19.15 but astrological_score=104.72 -- two numbers from
    # two different, disconnected pipeline stages describing the same
    # field.
    #
    # Correction (2026-08-19, same-day follow-up, chat session): the first
    # cut of this fix rescaled astrological_score to 100*final_score/
    # top_score -- WRONG, flagged live by the user. That relative-to-#1
    # rescaling forces whichever field wins #1 to always display as exactly
    # 100 regardless of how strong it actually is in absolute terms, and
    # compresses every other field's displayed gap toward that arbitrary
    # ceiling. Confirmed live on Ramsunder's re-run: the #1 field's own
    # tier1_score was only 16.38 (a chart-wide-weak number by this
    # codebase's own UNCORROBORATED_CAREER_VARGA_FLOOR=35.0 calibration),
    # yet the relative rescale displayed it as astrological_score=100.0 --
    # reading as maximum confidence when the underlying evidence was
    # actually weak. A genuinely strong chart and a genuinely weak chart
    # would both show their #1 field as "100", which erases the very signal
    # astrological_score exists to carry.
    #
    # Fix: `_tier_score()` (tiered_ranking.py) already computes a WEIGHTED
    # AVERAGE of per-method `normalized_score` values that are each
    # independently clamped/normalized to 0-100 (see clamp_score() in
    # Field_Determination/field_methods/common.py) -- a weighted average of
    # values already in [0,100] is itself inherently in [0,100], with no
    # rescaling needed at all. astrological_score should be this field's own
    # ABSOLUTE tiered score, not a fraction of whatever the chart's #1 field
    # happened to reach. Report it directly (defensively clamped only as a
    # safety net against any future upstream drift, not as a normalization
    # step), so a weak chart honestly shows a suppressed astrological_score
    # ceiling across all its fields, and a genuinely strong chart shows
    # genuinely high absolute numbers -- both readable at face value without
    # needing to know what else was in that chart's candidate pool.
    for _row in results:
        _fs = float(_row.get("final_score", 0.0) or 0.0)
        _row["astrological_score"] = round(max(0.0, min(100.0, _fs)), 4)
    # -------------------------------------------------------------------
    # Gap-audit fix (2026-08, chat cross-chart review): rank-differentiation
    # diagnostics (score_ceiling_tie / low_rank_differentiation) must be
    # computed against the rank that actually ships, not the pre-lockout
    # rank apply_publication_ranking_policy saw -- see the note on
    # ranking_policy.annotate_rank_differentiation().
    annotate_rank_differentiation(results)
    # Gap-audit fix (2026-08-18, Claude session, structural-gaps remediation
    # plan): apply_uncorroborated_leakage_guards() only ever protects the
    # true top 5 -- ranks 6-20 (the same window annotate_rank_differentiation
    # just above already treats as real, displayed output) had NO
    # corroboration visibility at all before this. Flags only; never
    # touches final_score/rank. See ranking_policy.annotate_wide_
    # corroboration_visibility() docstring for why this must run here, after
    # compute_tiered_ranking(), rather than inside the pre-tiered guard
    # passes in ranking_policy.py.
    annotate_wide_corroboration_visibility(results)
    # Gap-audit fix (2026-08-18, Claude session): the pre-tiered leakage
    # guards' discount notes can describe a discount that compute_tiered_
    # ranking() already discarded (different score basis, can legitimately
    # disagree with the guards' own tiered-side reimplementation). Must run
    # after compute_tiered_ranking() has set tier1_leakage_discounted on
    # every row. See ranking_policy.reconcile_legacy_leakage_annotations()
    # docstring for the full rationale and how this was found (Lakshman's
    # own #1 field, computational_social_science, carried a stale
    # "discounted 45%" note despite ranking #1 undiscounted).
    reconcile_legacy_leakage_annotations(results)
    # GAP-FIX (2026-07-19, engine-output audit): attach_audit_ledgers() runs
    # once already, inside apply_release_4_7() -> attach_decision_axes(),
    # which is BEFORE apply_publication_ranking_policy() and
    # _enforce_hard_lockout_publication_order() run. Those two later stages
    # can legitimately change final_score/rank again (field_role discounts,
    # the field_type_boundary clamp for "career_route"/"career_context"
    # fields like civil_services/research_academia, and hard-lockout
    # reordering) but nothing re-synced field_score_ledger afterward, so its
    # legacy_rank/legacy_relative_score silently went stale relative to the
    # actually-published rank/final_score -- confirmed live: civil_services
    # published at rank 21/score ~61 while its ledger still claimed rank 2/
    # score ~88. Re-attaching here makes the ledger describe the row that
    # actually ships, not an intermediate snapshot from earlier in the
    # pipeline.
    attach_audit_ledgers(results, payload_data.canonical_fact_quality_report)
    results = _refresh_cluster_report_and_evidence_summaries(results)
    return _attach_validation_contract(results, payload_data, llm_used=llm_used)


def _attach_validation_contract(results, payload_data, *, llm_used=False):
    """Attach honest, machine-readable semantics to every published field row."""
    privacy = privacy_contract(payload_data)
    run_policy = payload_data.calculation_policy.to_dict()
    identity = calculation_identity(
        policy=run_policy,
        engine=ENGINE_VERSION,
        degraded=False,
        fallback_reason=None,
    )
    status = evidence_status(inputs_complete=True, computed=True)
    for row in results:
        row["validation_status"] = dict(status)
        row["calculation_identity"] = dict(identity)
        row["score_semantics"] = "MODEL_SCORE_NOT_PROBABILITY"
        row["statistical_calibration"] = "NOT_CALIBRATED"
        row["llm_enrichment_used"] = bool(llm_used)
        row["privacy"] = dict(privacy)
        row["disclaimer"] = UNIVERSAL_DISCLAIMER
        row["evidence_layers"] = evidence_layers(
            facts={
                "calculation_policy": run_policy,
                "field_id": row.get("field_id", ""),
            },
            doctrine={
                "method_scores": row.get("method_normalized_scores", {}),
                "astrological_evidence": row.get("astrological_evidence", []),
            },
            heuristics={
                "final_score": row.get("final_score"),
                "rank": row.get("rank"),
                "statistical_calibration": "NOT_CALIBRATED",
            },
        )
    return results


def run_engine(
    payload_data: NatalPayloadV2,
    enable_llm: bool = False,
    llm_max_retries: int = 1,
) -> List[Dict]:
    # Release-foundation diagnostics are observational in v1: they bind a run
    # to its exact input/source and expose contradictions without changing the
    # established score or ordering.
    payload_data.calculation_policy = build_calculation_policy(payload_data)
    payload_data.run_manifest = build_run_manifest(payload_data, enable_llm=enable_llm)
    payload_data.run_manifest["calculation_policy"] = payload_data.calculation_policy.to_dict()
    # GAP-FIX (P1-6, Shadbala completeness/uncertainty exposure): surface the
    # per-planet completeness computed in shadbala.py at the same transparency
    # layer as calculation_policy, instead of leaving it reachable only by a
    # caller who happens to already know to look at payload.shadbala_computed.
    _sb = getattr(payload_data, "shadbala_computed", None) or {}
    payload_data.run_manifest["shadbala_data_quality"] = {
        "calculation_status":  _sb.get("calculation_status", "NOT_COMPUTED_MISSING_REQUIRED_INPUTS"),
        "completeness_ratio":  _sb.get("completeness_ratio", 0.0),
        "incomplete_planets":  _sb.get("incomplete_planets", []),
    }
    payload_data.canonical_fact_quality_report = build_canonical_facts(payload_data)
    _validate_payload_schema(payload_data)
    top35, eff_strengths, lagna_sign, ak = _run_normalization_stage(payload_data)
    # R2/R3: audit-only separated axes and dependency-reduced permanent fit.
    # This is attached after authoritative selection, so it cannot change
    # membership, final_score, or ordering.
    top35 = attach_shadow_scores(top35)

    # 2026-07 astrologer's audit, fix (2): apply_release_4_7 -> decision_axes
    # can now apply a bounded D1/D10-disagreement penalty to final_score
    # (see decision_axes.py). decision_axes.py deliberately does NOT re-sort
    # its `rows` (to keep release_candidate.py's field_id-order invariant
    # check meaningful), so every branch below re-sorts by final_score AFTER
    # apply_release_4_7 returns, to ensure any penalty actually reorders the
    # displayed/ranked output rather than being computed but never surfaced.
    llm_authorized = bool(enable_llm and getattr(payload_data, "external_llm_consent", False))
    if enable_llm and not llm_authorized:
        logger.warning("LLM enrichment requested but skipped: external_llm_consent is false.")

    # GAP-FIX: the "LLM not authorized" and "LLM authorized but call_llm_for_fields
    # returned falsy" cases previously each independently called
    # _finalize_published_results(top35, ..., llm_used=False) +
    # _apply_display_score_compression(...) at two separate call sites. Both
    # branches are supposed to produce the identical deterministic-fallback
    # result, but the duplication meant a future edit to one (e.g. adding a
    # log line or an extra finalize step) could silently diverge from the
    # other. Factored into one helper so both "LLM unavailable" reasons are
    # guaranteed to go through the exact same code path.
    def _deterministic_fallback() -> List[Dict]:
        return _apply_display_score_compression(
            _finalize_published_results(top35, payload_data, llm_used=False)
        )

    if not llm_authorized:
        return _deterministic_fallback()

    llm_results = call_llm_for_fields(
        payload_data, eff_strengths, top35, max_retries=llm_max_retries
    )
    if llm_results:
        results = _finalize_published_results(llm_results, payload_data, llm_used=True)
        # GAP-FIX (2026-07, "Use an LLM for" policy): opt-in rule-trace
        # validation + cautious narrative composition for the top-N fields
        # (see jyotish/llm_deep_validation.py). No-op unless
        # JYOTISH_DEEP_VALIDATION=1 is set; never reorders or rescoves
        # `results`, only attaches rule_trace_validation/validated_narrative.
        try:
            from .llm_deep_validation import enrich_top_n_with_validation
            results = enrich_top_n_with_validation(payload_data, results)
        except Exception as _dv_exc:
            logger.info(f"Deep validation stage skipped/unavailable: {_dv_exc}")
        return _apply_display_score_compression(results)

    logger.warning("LLM enrichment failed or skipped — returning deterministic top-35.")
    return _deterministic_fallback()
