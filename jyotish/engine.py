"""JyotishAI — Main scoring engine (run_engine) and QA helpers."""
import math as _math
import random as _random
from typing import Dict, List, Tuple, Set, Any, Optional

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
from .ranking_policy import apply_publication_ranking_policy
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
# Competency-first ontology layer (2026-07 architecture audit G1-G18, G23-G30):
# adds Competency -> Career Family grouping, confidence bands, explanation
# chains, and a bounded family-cohesion adjustment on top of the existing
# 199-branch deterministic scoring. See jyotish/competency_ontology.py.
from Field_Determination.competency_ontology import apply_competency_ontology_layer
from Field_Determination.competency_ontology import build_cluster_report
from Field_Determination.competency_ontology import confidence_band
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
                notes_list.append(f"FATAL: Primary karaka {planet} defeated in war in {domain} — "
                                   "core field competency completely devastated.")
            # Fatal condition 2: Primary karaka is combust (except Mercury)
            elif is_primary and is_combust and planet != "Mercury":
                is_fatal = True
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
                notes_list.append(f"FATAL: {planet} {reason} in {domain} — "
                                   "structural/technical architecture severely disrupted.")
            # Fatal condition 3b: Primary karaka combust in non-STEM domain (symmetry with STEM)
            elif (is_combust and is_primary
                  and planet in _DOMAIN_STRUCTURAL_PLANETS.get(domain, ())
                  and domain not in _ENG_SCI
                  and ak not in _DOMAIN_AK_GUARD.get(domain, ())):
                is_fatal = True
                notes_list.append(f"FATAL: {planet} combust in {domain} — "
                                   "primary domain karaka expression severely suppressed.")
            # Fatal condition 3c: Structural planet war-loss in non-STEM domains
            elif (is_war_loser
                  and planet in _DOMAIN_STRUCTURAL_PLANETS.get(domain, ())
                  and domain not in _ENG_SCI
                  and ak not in _DOMAIN_AK_GUARD.get(domain, ())):
                is_fatal = True
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
    if friction > 0 and not is_fatal and primary_karaka:
        pk_d10 = d10_digs.get(primary_karaka, "") if d10_digs else ""
        pk_d24 = d24_digs.get(primary_karaka, "")

        varga_offset = 0
        if pk_d10 in ("EXALTED", "OWN"):
            varga_offset = min(friction, 20)
            notes_list.append(f"D10 {primary_karaka} {pk_d10} (Dashamsha): career architecture offsets {varga_offset} friction pts.")
        elif pk_d24 in ("EXALTED", "OWN"):
            varga_offset = min(friction, 15)
            notes_list.append(f"D24 {primary_karaka} {pk_d24} (Siddhamsha): academic mastery offsets {varga_offset} friction pts.")

        friction -= varga_offset

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
    valid = [r for r in rows if not r.get("hard_lockout", False)]
    locked = [r for r in rows if r.get("hard_lockout", False)]
    ordered = valid + locked
    for idx, row in enumerate(ordered, 1):
        row["rank"] = idx
        row["publication_score"] = float(row.get("final_score", 0.0) or 0.0)
    return ordered


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


def _top3_planets(affinity_planets: Dict[str, float]) -> List[str]:
    """Return top-3 planet names sorted by affinity weight descending."""
    if not affinity_planets:
        return []
    return [p for p, _ in sorted(affinity_planets.items(), key=lambda x: -x[1])[:3]]


def _validate_payload_schema(payload_data: Any) -> None:
    """A1: Strict schema validation at ingestion.

    Raises ValueError immediately if any critical field is None or empty,
    preventing silent failures deep in the scoring loop.
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


def _run_normalization_stage(payload_data: NatalPayloadV2) -> tuple:
    """Pipeline Stage 1 — deterministic scoring and normalisation.

    Runs the full field-scoring loop over all registered fields, then applies
    per-method Min-Max normalisation (Arch-B) and inter-domain soft-max
    normalisation (S2).  Returns the top-35 pre-scored payload ready for LLM
    dispatch, plus the context vars the LLM stage needs:

        (top35_for_llm, eff_strengths, lagna_sign, ak)
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
    d10_digs   = {p: compute_dignity(p, s) for p, s in d10_chart.items() if p != "Lagna"}
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
        d9_digs = {p: compute_dignity(p, s) for p, s in d9_chart.items() if p != "Lagna"}

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
    active_lord = _get_active_dasha_lord(
        getattr(payload_data, "dasha_sequence", []), current_age)

    # AC2 fix: extract the active antardasha lord for gap-boost scoring
    _antardasha_lord = ""
    for _d in getattr(payload_data, "dasha_sequence", []):
        _ds, _de = float(_d.get("start_age", 0)), float(_d.get("end_age", 999))
        if _ds <= current_age < _de:
            for _ad in _d.get("antardashas", []):
                _as, _ae = float(_ad.get("start_age", 0)), float(_ad.get("end_age", 999))
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
    try:
        from datetime import date as _date_cls
        from . import transit_engine as _transit_engine
        _transit_houses, _transit_degrees, _transit_retro = _transit_engine.compute_current_transit_snapshot(
            _date_cls.today(), lagna_sign)
    except Exception as _transit_exc:
        logger.info(f"Gochar transit snapshot unavailable, skipping: {_transit_exc}")

    # Risk override for astrological indicators
    if risk != "HIGH":
        if ph.get("Mars", 0) == 3 and digs.get("Mars", "") not in ("DEBILITATED",):
            risk = "HIGH"
            logger.info("Astrological override: Chart indicates HIGH risk capacity despite user input.")

    # Nakshatra parivartana yogas
    for _np1, _np2 in [("Moon", "Sun"), ("Moon", "Saturn"), ("Sun", "Jupiter")]:
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
    try:
        a10_sign = _compute_arudha_pada(10, lagna_sign, planets_d1) or ""
    except Exception:
        a10_sign = ""
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
        set(yogas)
    )
    payload_data.eff_strengths = eff_strengths          # A2/LS1 fix: field methods read this
    payload_data.vargottama_planets = vargottama        # G2 fix: field methods can check vargottama exemption
    payload_data.planet_modifier_flags = _extract_modifier_flags(planet_trace)

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
    _peak_window = (0.0, 99.0)
    for _d in getattr(payload_data, "dasha_sequence", []):
        _dl = _d.get("lord", "") or _d.get("md_planet", "")
        if _dl == peak_lord:
            _peak_window = (float(_d.get("start_age", 0)), float(_d.get("end_age", 99)))
            break
    payload_data.peak_dasha_window = _peak_window
    if peak_lord:
        logger.info(f"Peak career MD: {peak_lord}  (scores: { {k: round(v,3) for k,v in sorted(peak_scores.items(), key=lambda x:-x[1])[:5]} })")

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

    for _fid, _fmeta in _COURSE_REGISTRY.items():
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
        # _confluence_gate, extended here to the rest of the gap_boost stage.
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

        _eff_for_scoring = eff_strengths
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


        gap_boost, gap_detail = 0.0, {}
        gap_penalty = 0.0   # reset each field iteration
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
        b = min(_ak_b + _amk_b, _PCC); gap_boost += b; gap_detail["ak_amk"] = round(b, 3)

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
                    gap_boost += _ak_mandate_b
                    gap_detail["ak_soul_mandate"] = round(_ak_mandate_b, 3)

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
                gap_boost += _maly_b
                gap_detail["malavya_arts_mandate"] = round(_maly_b, 3)

        b = min(_stellium_bonus(_gate_text, ph), _PCC); gap_boost += b; gap_detail["stellium"] = round(b, 3)
        # AC1 fix: Argala H10 career activation
        _top_aff_planet = max(hard_affinity.items(), key=lambda x: x[1])[0] if hard_affinity else ""
        if _top_aff_planet and _top_aff_planet in _argala_h10:
            _argala_b = min(0.06 * aff.get(_top_aff_planet, 0.1) * 5, 0.06)
            gap_boost += _argala_b; gap_detail["argala_h10"] = round(_argala_b, 3)
        elif _top_aff_planet:
            # Virodha Argala: 12th (H9), 10th (H7), 3rd (H12) from H10 obstruct career.
            # H2 fix: previously only H9 was penalized; now all three positions are checked.
            _virodha_houses = {9, 7, 12}  # 12th/10th/3rd from H10
            if ph.get(_top_aff_planet, 0) in _virodha_houses:
                gap_penalty += 0.03; gap_detail["virodha_argala"] = -0.03
        b = min(_dasha_bonus(_gate_text, payload_data), _PCC); gap_boost += b; gap_detail["dasha"] = round(b, 3)
        b = min(_karakamsha_bonus(aff, karakamsha), _PCC); gap_boost += b; gap_detail["karakamsha"] = round(b, 3)
        b = min(_d24_ak_delta(_gate_text, payload_data), _PCC); gap_boost += b; gap_detail["d24_ak"] = round(b, 3)
        b = min(_d24_full_chart_bonus(aff, payload_data), _PCC); gap_boost += b; gap_detail["d24_full"] = round(b, 3)
        b = min(_lagna_lord_bonus(_gate_text, payload_data), _PCC); gap_boost += b; gap_detail["lagna_lord"] = round(b, 3)
        _risk_b = _risk_appetite_bonus(_gate_text, risk)
        if _risk_b >= 0:
            gap_boost += min(_risk_b, _PCC)
        else:
            gap_penalty += abs(_risk_b)
        gap_detail["risk_appetite"] = round(_risk_b, 3)
        b = _modernize_karakas_modifier(_fid, risk, amk, _kp_h10_star_lord, planets_d1)
        gap_boost += b; gap_detail["modernize_karakas"] = round(b, 3)
        b = min(_yogakaraka_bonus(aff, lagna_sign, shadbala, digs), _PCC)
        gap_boost += b; gap_detail["yogakaraka"] = round(b, 3)
        # LS3 fix: debilitated yogakaraka penalty → gap_penalty (not negative gap_boost)
        _yk_pen = _yogakaraka_debilitation_penalty(aff, lagna_sign, shadbala, digs)
        if _yk_pen > 0: gap_penalty += _yk_pen; gap_detail["yogakaraka_deb_pen"] = round(-_yk_pen, 3)
        b = min(_h10_lord_strength_bonus(aff, h10_lp, shadbala, digs), _PCC); gap_boost += b; gap_detail["h10_lord_str"] = round(b, 3)
        b = min(_h10_lord_trikona_bonus(aff, h10_lp, ph, digs), _PCC); gap_boost += b; gap_detail["h10_lord_trikona"] = round(b, 3)
        b = min(_exalted_planet_domain_bonus(aff, digs, _gate_text, lagna_sign), _PCC); gap_boost += b; gap_detail["exalted_domain"] = round(b, 3)
        b = min(_ul_lord_bonus(aff, ul), _PCC); gap_boost += b; gap_detail["ul_lord"] = round(b, 3)
        # _d9_ak_delta's `label` param is unused inside the function (pure D9-dignity
        # scoring, no keyword matching) -- intentionally left as `label` (Gap-18b audit).
        b = min(_d9_ak_delta(label, payload_data), _PCC); gap_boost += b; gap_detail["d9_ak"] = round(b, 3)
        b = min(_yoga_bonus(_gate_text, yogas, house_lords, digs), _PCC); gap_boost += b; gap_detail["yoga"] = round(b, 3)
        b = min(_h5_lord_bonus(aff, h5_lord), _PCC); gap_boost += b; gap_detail["h5_lord"] = round(b, 3)
        b = min(_amk_house_bonus(_gate_text, amk_house), _PCC); gap_boost += b; gap_detail["amk_house"] = round(b, 3)
        b = min(_ak_house_bonus(ak, ph.get(ak, 0), _gate_text), _PCC); gap_boost += b; gap_detail["ak_house"] = round(b, 3)

        # LS13 fix: soul-stack cap = 0.26 → max soul-domain gap_boost contribution.
        # Rationale: on a 75-blended field, 0.26 × 0.76 _base_weight ≈ +20 display pts.
        # Prevents AK/yogakaraka pile-on from overriding multi-method scoring.
        _soul_stack = gap_detail.get("ak_amk", 0) + gap_detail.get("yogakaraka", 0) + gap_detail.get("ak_house", 0)
        if _soul_stack > 0.26:
            _ss_excess = _soul_stack - 0.26
            gap_boost -= _ss_excess
            gap_detail["yogakaraka"] = round(gap_detail.get("yogakaraka", 0) - _ss_excess, 3)
            gap_detail["_soul_stack_cap"] = round(-_ss_excess, 3)

        # Engineering domain mandate when Mars is BOTH AK and YK:
        # The soul purpose (AK=Mars→engineering) and the lagna's most benefic planet
        # (YK=Mars) doubly direct toward technical vocation. Engineering fields receive
        # an extra mandate that is NOT subject to the soul_stack cap (it's a domain
        # gate, not an AK/YK pile-on). Only fires when YK has already triggered
        # (gap_detail["yogakaraka"] > 0) so it's lagna-specific, not universal.
        if (domain == "engineering" and ak == "Mars"
                and gap_detail.get("yogakaraka", 0) > 0
                and digs.get("Mars", "") not in ("DEBILITATED",)):
            # Scale mandate by Mars dignity: EXALTED/OWN Mars makes engineering even more dominant
            _mars_dig_for_eng = digs.get("Mars", "")
            _eng_dig_scale = 1.5 if _mars_dig_for_eng == "EXALTED" else (1.2 if _mars_dig_for_eng == "OWN" else 1.0)
            _eng_yk_cap = 0.07 * _eng_dig_scale
            _eng_yk_man = min(_eng_dig_scale * 0.07 * max(eff_strengths.get("Mars", 1.0), 0.5), _eng_yk_cap)
            gap_boost += _eng_yk_man
            gap_detail["engineering_yk_mandate"] = round(_eng_yk_man, 3)

        # H1 fix: when peak_lord == prime_career_lord the native is currently in their peak
        # career dasha — _peak_career_dasha_boost already captures this at full strength.
        # Skip _dasha_active_affinity_boost for that lord to prevent double-counting.
        if prime_career_lord != peak_lord:
            b = min(_dasha_active_affinity_boost(aff, prime_career_lord, digs), _PCC); gap_boost += b; gap_detail["prime_dasha_affinity"] = round(b, 3)
        else:
            gap_detail["prime_dasha_affinity"] = 0.0  # deduped: peak==active, peak_md_boost covers it
        b = min(_peak_career_dasha_boost(aff, peak_lord, prime_career_lord, digs), _PCC); gap_boost += b; gap_detail["peak_md_boost"] = round(b, 3)
        _dasha_total = gap_detail.get("dasha", 0) + gap_detail.get("prime_dasha_affinity", 0) + gap_detail.get("peak_md_boost", 0)
        if _dasha_total > 0.22:
            _excess = _dasha_total - 0.22
            gap_boost -= _excess
            gap_detail["peak_md_boost"] = round(gap_detail.get("peak_md_boost", 0) - _excess, 3)

        b = min(_pratyantar_dasha_bonus(_gate_text, prd_lord, prd_houses), _PCC); gap_boost += b; gap_detail["prd_boost"] = round(b, 3)
        # AC2 fix: antardasha lord domain boost (half weight of main dasha)
        if _antardasha_lord and _antardasha_lord in aff and _antardasha_lord != prime_career_lord:
            _ad_w   = aff.get(_antardasha_lord, 0.0)
            _ad_dig = digs.get(_antardasha_lord, "")
            _ad_dig_scale = {"EXALTED": 1.40, "OWN": 1.15, "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.60}.get(_ad_dig, 1.0)
            _ad_b = min(_ad_w * _ad_dig_scale * 0.06, _PCC * 0.5)
            if _ad_b > 0:
                gap_boost += _ad_b; gap_detail["antardasha_affinity"] = round(_ad_b, 3)
            # N4: AD lord in kendra/trikona → can deliver its promise (classical rule)
            _ad_house = ph.get(_antardasha_lord, 0)
            if _ad_house in (1, 4, 5, 7, 9, 10) and _ad_b > 0:
                _ad_delivery_b = min(_ad_b * 0.30, _PCC * 0.15)
                gap_boost += _ad_delivery_b
                gap_detail["ad_kendra_trikona"] = round(_ad_delivery_b, 3)
        # T1-E: MD × AD compound — when BOTH Mahadasha and Antardasha lords match field keywords,
        # career events crystallise with high reliability. Apply 35% bonus on existing dasha total.
        _md_kw_match = active_lord and any(_wm(kw, _gate_text) for kw in DASHA_KEYWORDS.get(active_lord, []))
        _ad_kw_match = _antardasha_lord and any(_wm(kw, _gate_text) for kw in DASHA_KEYWORDS.get(_antardasha_lord, []))
        if _md_kw_match and _ad_kw_match:
            _dasha_so_far = (gap_detail.get("dasha", 0) + gap_detail.get("prime_dasha_affinity", 0)
                             + gap_detail.get("antardasha_affinity", 0))
            _compound_b = min(_dasha_so_far * 0.35, _PCC)
            if _compound_b > 0.005:
                gap_boost += _compound_b
                gap_detail["md_ad_compound"] = round(_compound_b, 3)
        # AC5 fix: Rahu career signal — H10/H6 (upachaya) placement with strong STEM affinity
        _rahu_h = ph.get("Rahu", 0)
        if _rahu_h in (10, 6) and aff.get("Rahu", 0) >= 0.25:
            _rahu_b = min(0.06, aff["Rahu"] * 0.20)
            gap_boost += _rahu_b; gap_detail["rahu_career_h10h6"] = round(_rahu_b, 3)
        # AC5 fix: Ketu career signal — H9/H5 placement with research/mystical affinity
        _ketu_h = ph.get("Ketu", 0)
        _ketu_research_lbl = any(_wm(kw, _gate_text) for kw in
            ["research", "mathematics", "forensic", "philosophy", "archaeology", "ayurveda"])
        if _ketu_h in (9, 5) and _ketu_research_lbl and aff.get("Ketu", 0) >= 0.20:
            _ketu_b = min(0.05, aff["Ketu"] * 0.18)
            gap_boost += _ketu_b; gap_detail["ketu_research_h9h5"] = round(_ketu_b, 3)

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
                _natho_delta = gap_boost * (_natho_mult - 1.0)
                _natho_delta = max(-0.04, min(_natho_delta, 0.04))
                gap_boost += _natho_delta
                if abs(_natho_delta) >= 0.005:
                    gap_detail['nathonnatha'] = round(_natho_delta, 3)

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
                gap_boost += _panch_b; gap_detail['panchanga_lord'] = round(_panch_b, 3)

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
                    gap_penalty += _h8_penalty
                    gap_detail["h8_medicine_gate"] = round(-_h8_penalty, 3)
                elif _h8_vit >= 1.10:
                    # Exceptionally strong H8 lord — add a bonus
                    _h8_bonus = min((_h8_vit - 1.10) * 0.10, 0.04)
                    gap_boost += _h8_bonus
                    gap_detail["h8_medicine_gate"] = round(_h8_bonus, 3)
        elif domain in ("public", "law"):   # R3 fix: "defence" → "public" (real domain)
            _h6_lord_d = house_lords.get("6", "") or house_lords.get(6, "")
            if _h6_lord_d:
                _h6_vit = eff_strengths.get(_h6_lord_d, 1.0)
                if _h6_vit < 0.45:
                    # H6 lord impaired — conflict/service capacity weakened
                    _h6_penalty = min((0.45 - _h6_vit) * 0.18, 0.06)
                    gap_penalty += _h6_penalty
                    gap_detail["h6_defence_gate"] = round(-_h6_penalty, 3)
                elif _h6_vit >= 1.10:
                    _h6_bonus = min((_h6_vit - 1.10) * 0.08, 0.04)
                    gap_boost += _h6_bonus
                    gap_detail["h6_defence_gate"] = round(_h6_bonus, 3)

        b = min(_karakamsha_occupant_bonus(_gate_text, kara_occ, shadbala), _PCC); gap_boost += b; gap_detail["karakamsha_occ"] = round(b, 3)
        # GAP-FIX (2026-07): cap now scaled by AK's classical Vimshopaka Bala
        # (Dasavarga) fraction instead of the flat, unexplained _PCC constant.
        b = min(_d9_h10_bonus(aff, d9_chart, d9_lagna), _PCC * _vimshopaka_d9_scale); gap_boost += b; gap_detail["d9_h10"] = round(b, 3)
        gap_detail["vimshopaka_ak_pct"] = _vb_ak.get("pct", 0.0)
        b = min(_dharma_karma_bonus(aff, house_lords, ph), _PCC); gap_boost += b; gap_detail["dharma_karma"] = round(b, 3)
        b = min(_interest_preference_boost(_gate_text, interested_in, already_excel), _PCC); gap_boost += b; gap_detail["interest_pref"] = round(b, 3)
        b = min(_brahma_lord_bonus(_gate_text, brahma_lord, aff), _PCC); gap_boost += b; gap_detail["brahma_lord"] = round(b, 3)
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
        gap_boost += b; gap_detail["d10_h10"] = round(b, 3)
        b = min(_d10_lagna_lord_bonus(aff, d10_chart, d10_lagna, d10_digs), _d10_pcc_scaled); gap_boost += b; gap_detail["d10_lagna_lord"] = round(b, 3)
        gap_detail["vimshopaka_h10_lord_pct"] = _vb_h10.get("pct", 0.0)
        # _gender_field_modifier's `label` param is unused inside the function (pure
        # Venus-house-lordship logic, no keyword matching) -- intentionally left as
        # `label`, not `_gate_text` (Gap-18b audit).
        b = _gender_field_modifier(label, gender_val, aff, house_lords); gap_boost += b; gap_detail["gender_field"] = round(b, 3)
        b = min(_aspect_h10_bonus(aff, ph, digs, planets_d1=getattr(payload_data, "planets_d1", None)), _PCC)
        gap_boost += b; gap_detail["aspect_h10"] = round(b, 3)
        b = min(_maheshwara_lord_bonus(_gate_text, maheshwara_lord, aff), _PCC); gap_boost += b; gap_detail["maheshwara"] = round(b, 3)
        b = min(_bhavesha_phala_edu_bonus(_gate_text, aff, house_lords, ph), _PCC); gap_boost += b; gap_detail["bhavesha_phala"] = round(b, 3)
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
        gap_boost += b; gap_detail["ak_planet_domain"] = round(b, 3)
        b = min(_karakamsha_domain_boost(_gate_text, domain, karakamsha), _PCC); gap_boost += b; gap_detail["karakamsha_domain"] = round(b, 3)
        b = min(_h3_lord_communication_boost(_gate_text, domain, house_lords, eff_strengths, ph), _PCC); gap_boost += b; gap_detail["h3_comm"] = round(b, 3)
        b = _h12_stellium_penalty(_gate_text, domain, ph); gap_boost += b; gap_detail["h12_stellium_pen"] = round(b, 3)
        # ── 10/10 upgrade: 15 astrological signal blocks ──────────────────────────
        # Fix 1: Nakshatra-axis career rulership
        _moon_nak  = getattr(payload_data, "moon_nakshatra", "") or ""
        _pl_naks   = getattr(payload_data, "planet_nakshatras", {}) or {}
        b = min(_nakshatra_career_score(aff, _moon_nak, _pl_naks, house_lords, lagna_sign, _gate_text), _PCC)
        gap_boost += b; gap_detail["nakshatra_career"] = round(b, 3)

        # Fix 2: Rahu-Ketu nodal axis as life-direction indicator
        _rahu_h = getattr(payload_data, "rahu_house", 0) or ph.get("Rahu", 0)
        _ketu_h = getattr(payload_data, "ketu_house", 0) or ph.get("Ketu", 0)
        b = min(_nodal_axis_career_signal(aff, _rahu_h, _ketu_h, _gate_text, eff_strengths), _PCC)
        gap_boost += b; gap_detail["nodal_axis"] = round(b, 3)

        # Fix 3: Viparita Raja Yoga — flip dusthana penalty to bonus
        b = min(_viparita_raja_yoga_bonus(aff, house_lords, ph, _gate_text), _PCC)
        gap_boost += b; gap_detail["viparita_raja_yoga"] = round(b, 3)

        # Fix 4: D10 comprehensive reading
        _d10_occ   = getattr(payload_data, "d10_house_occupancy", {}) or {}
        _d10_hl    = getattr(payload_data, "d10_house_lords", {}) or {}
        # _d10_comprehensive_bonus's `label` param is computed to `label_lower` inside
        # but never referenced again (dead) -- intentionally left as `label`, not
        # `_gate_text` (Gap-18b audit).
        b = min(_d10_comprehensive_bonus(aff, _d10_occ, _d10_hl, d10_lagna, label, eff_strengths), _PCC)
        gap_boost += b; gap_detail["d10_comprehensive"] = round(b, 3)

        # Fix 5: Solar/Lunar Hora career mode
        b = min(_hora_mode_career_signal(aff, getattr(payload_data, "planets_d1", {}) or {}, _gate_text), _PCC * 0.5)
        gap_boost += b; gap_detail["hora_mode"] = round(b, 3)

        # Fix 6: Graha Avastha career manifestation modifier (can be negative)
        _av = _avastha_career_modifier(aff, getattr(payload_data, "planets_d1", {}) or {})
        gap_boost += _av; gap_detail["avastha_modifier"] = round(_av, 3)

        # Fix 7: H3 Parakrama lord — skill/effort house (engine layer, complements knrao layer)
        b = min(_h3_lord_career_bonus(aff, house_lords, ph, digs, eff_strengths, _gate_text), _PCC * 0.5)
        gap_boost += b; gap_detail["h3_parakrama"] = round(b, 3)

        # Fix 8: Pushkara Navamsha boost
        b = min(_pushkara_navamsha_boost(aff, getattr(payload_data, "planets_d1", {}) or {}, eff_strengths), _PCC)
        gap_boost += b; gap_detail["pushkara_navamsha"] = round(b, 3)

        # Fix 9: Nakshatra pada field discriminator
        b = min(_pada_field_discriminator(aff, _pl_naks, getattr(payload_data, "planets_d1", {}) or {}, house_lords, _gate_text), _PCC)
        gap_boost += b; gap_detail["pada_discriminator"] = round(b, 3)

        # Fix 10: Chara Dasha simplified timing signal (Jaimini)
        _kms_sign = getattr(payload_data, "karakamsha_sign", "") or ""
        b = min(_chara_dasha_timing_signal(aff, _kms_sign, lagna_sign, ph, ak, current_age), 0.18)
        gap_boost += b; gap_detail["chara_dasha"] = round(b, 3)

        b = min(_lagna_element_career_bonus(lagna_sign, _gate_text), _PCC)
        gap_boost += b; gap_detail["lagna_element"] = round(b, 3)

        b = min(_d1_d10_h10_double_dignity_bonus(aff, payload_data), _PCC)
        gap_boost += b; gap_detail["d1_d10_h10_double_dignity"] = round(b, 3)

        # Fix 11: Spiritual/alternative career proxy (D20 substitute)
        b = min(_spiritual_career_proxy(aff, ph, house_lords, _gate_text, eff_strengths), _PCC * 0.5)
        gap_boost += b; gap_detail["spiritual_proxy"] = round(b, 3)

        # Fix 12: Guna balance modifier
        b = min(_guna_balance_modifier(aff, eff_strengths, _gate_text), _PCC * 0.5)
        gap_boost += b; gap_detail["guna_balance"] = round(b, 3)

        # Fix 13: Lagna lord in dusthana as career directive
        b = min(_lagna_lord_dusthana_directive(aff, lagna_lord, ph, _gate_text, eff_strengths), _PCC)
        gap_boost += b; gap_detail["lagna_lord_directive"] = round(b, 3)

        # Fix 14: Adhi Yoga + Anapha/Sunapha
        _det_yogas = getattr(payload_data, "detected_yogas", []) or getattr(payload_data, "yogas_present", []) or []
        b = min(_adhi_anapha_yoga_bonus(aff, ph, getattr(payload_data, "planets_d1", {}) or {}, _det_yogas, _gate_text), _PCC)
        gap_boost += b; gap_detail["adhi_anapha_yoga"] = round(b, 3)

        # Fix 15: Transit career activation window
        _transit_pos = getattr(payload_data, "transit_house_positions", {}) or {}
        b = min(_transit_career_activation(aff, _transit_pos, _gate_text, current_age), _PCC)
        gap_boost += b; gap_detail["transit_activation"] = round(b, 3)
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
        gap_boost += b; gap_detail["person_archetype"] = round(b, 3)

        # R3-2: Lagna propensity (classical lagna career tendencies)
        b = min(_lagna_propensity_score(aff, lagna_sign, _gate_text), _PCC * 0.67)
        gap_boost += b; gap_detail["lagna_propensity"] = round(b, 3)

        # R3-3: Moon Rashi career propensity (emotional/behavioral work tendency)
        b = min(_moon_rashi_propensity(aff, _planets_d1_r3, _gate_text), _PCC * 0.58)
        gap_boost += b; gap_detail["moon_rashi_propensity"] = round(b, 3)

        # R3-4: Panchamahapurusha mandate (field-specific yoga mandate; can be negative)
        _mph = _mahapurusha_mandate_score(aff, _det_yogas_r3, ph, _planets_d1_r3, _gate_text)
        gap_boost += _mph; gap_detail["mahapurusha_mandate"] = round(_mph, 3)

        # R3-5: Career-house Parivartana bonus
        b = min(_career_parivartana_bonus(aff, house_lords, _planets_d1_r3, _gate_text), _PCC)
        gap_boost += b; gap_detail["career_parivartana"] = round(b, 3)

        # R3-6: Graha Yuddha winner domain expansion
        b = min(_war_winner_domain_bonus(aff, _planets_d1_r3, _gate_text, eff_strengths), _PCC * 0.67)
        gap_boost += b; gap_detail["war_winner_domain"] = round(b, 3)

        # R3-7: H10 lord combustion career flag (can be negative)
        _h10c = _h10_lord_combustion_flag(aff, house_lords, _planets_d1_r3, _combust_r3, _gate_text)
        gap_boost += _h10c; gap_detail["h10_lord_combustion"] = round(_h10c, 3)

        # R3-8: Compound Dasha quality index (multiplicative; can be negative)
        _cdq = _compound_dasha_quality(
            aff, _curr_dasha_r3, _ad_lord_r3, lagna_sign, house_lords,
            ph, _planets_d1_r3, eff_strengths, _combust_r3, _gate_text
        )
        gap_boost += _cdq; gap_detail["compound_dasha_quality"] = round(_cdq, 3)

        # R3-9: Putrakaraka (5th Chara Karaka) intellectual/creative field scoring
        b = min(_putrakaraka_field_score(aff, _pk_r3, ph, eff_strengths, _gate_text), _PCC * 0.75)
        gap_boost += b; gap_detail["putrakaraka_field"] = round(b, 3)

        # R3-10: Gnatikaraka (6th Chara Karaka) competition/conflict field signal
        b = min(_gnatikaraka_field_score(aff, _gnk_r3, ph, eff_strengths, _gate_text), _PCC * 0.58)
        gap_boost += b; gap_detail["gnatikaraka_field"] = round(b, 3)

        # R3-10b (GAP-FIX): Bhratrikaraka (3rd Chara Karaka) self-effort/skill field signal
        b = min(_bhratrikaraka_field_score(aff, _bk_r3, ph, eff_strengths, _gate_text), _PCC * 0.67)
        gap_boost += b; gap_detail["bhratrikaraka_field"] = round(b, 3)

        # R3-10c (GAP-FIX): Matrikaraka (4th Chara Karaka) property/domestic field signal
        b = min(_matrikaraka_field_score(aff, _mk_r3, ph, eff_strengths, _gate_text), _PCC * 0.67)
        gap_boost += b; gap_detail["matrikaraka_field"] = round(b, 3)

        # R3-10d (GAP-FIX): Darakaraka (7th Chara Karaka) partnership/business field signal
        b = min(_darakaraka_field_score(aff, _dk_r3, ph, eff_strengths, _gate_text), _PCC * 0.67)
        gap_boost += b; gap_detail["darakaraka_field"] = round(b, 3)

        # R3-10e (GAP-FIX): Gochar (transit) career-activation signal
        b = _gochar_h10_activation_bonus(_transit_houses, h10_lord, ak, aff, _gate_text)
        gap_boost += b; gap_detail["gochar_h10"] = round(b, 3)

        # R3-10f (GAP-FIX): Kaksha-level Ashtakavarga activation (H10 lord / AK)
        b = _kaksha_activation_bonus(h10_lord, ak, planets_d1, ph, _transit_degrees, _gate_text)
        gap_boost += b; gap_detail["kaksha_activation"] = round(b, 3)

        # R3-11: Trikona lord unity — dharmic career mandate
        b = min(_trikona_unity_bonus(aff, house_lords, _planets_d1_r3, ph, _gate_text), _PCC)
        gap_boost += b; gap_detail["trikona_unity"] = round(b, 3)

        # R3-12: Dasha timing gate — 10-year forward window
        b = min(_dasha_timing_gate(aff, _curr_dasha_r3, _next_dasha_r3, current_age, _gate_text, eff_strengths), _PCC * 0.67)
        gap_boost += b; gap_detail["dasha_timing_gate"] = round(b, 3)

        # R3-13: Bhinnashtakavarga individual planet H10 scores
        b = min(_bav_individual_boost(aff, _bav_r3, house_lords, _gate_text), _PCC * 0.67)
        gap_boost += b; gap_detail["bav_individual"] = round(b, 3)

        # R3-14: Yogi / Avayogi planet modifier (can be slightly negative)
        _yav = _yogi_avayogi_modifier(aff, _planets_d1_r3, eff_strengths, _gate_text)
        gap_boost += _yav; gap_detail["yogi_avayogi"] = round(_yav, 3)

        # R3-15: Confidence convergence grade — deferred to after bvb_eval (real scores).
        # NOTE: formerly computed here using gap_detail proxy keys that don't exist,
        # causing all 4 methods to fall back to `blended` and always return STRONG.
        # Now computed post-bundle with actual normalized_score values (T3-A fix).
        # ── End Round-3 upgrade signals ────────────────────────────────────────

        if ak and hard_affinity:
            _ak_top_k = max(hard_affinity.items(), key=lambda x: x[1])[0]
            if _ak_top_k == ak:
                # LS5 fix: ak_primary_karaka is a soul-domain signal — include it
                # inside the soul-stack total so the 0.26 cap covers it too.
                _akp_b = 0.10
                _soul_stack_with_akp = (gap_detail.get("ak_amk", 0)
                                        + gap_detail.get("yogakaraka", 0)
                                        + gap_detail.get("ak_house", 0)
                                        + _akp_b)
                if _soul_stack_with_akp > 0.26:
                    _akp_b = max(0.0, 0.26 - (gap_detail.get("ak_amk", 0)
                                               + gap_detail.get("yogakaraka", 0)
                                               + gap_detail.get("ak_house", 0)))
                if _akp_b > 0:
                    gap_boost += _akp_b; gap_detail["ak_primary_karaka"] = round(_akp_b, 3)

        # A4 fix: wire cluster bonus/counterweight functions into main gap_boost loop
        # (previously only called from field_methods/jaimini.py, missing from main pipeline)
        _cluster_b = _priority_cluster_field_bonus(branch_name, _gate_text, eff_strengths)
        if _cluster_b > 0:
            gap_boost += min(_cluster_b, _PCC); gap_detail['cluster_bonus'] = round(min(_cluster_b, _PCC), 3)
        _space_cw  = _space_extractive_counterweight(branch_name, _gate_text, eff_strengths)
        _life_cw   = _life_science_space_counterweight(branch_name, _gate_text, eff_strengths)
        _eng_cw    = _life_science_engineering_counterweight(branch_name, _gate_text, eff_strengths)
        _total_cw  = _space_cw + _life_cw + _eng_cw
        if _total_cw < 0:
            gap_penalty += abs(_total_cw)
            gap_detail['cluster_counterweight'] = round(_total_cw, 3)

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
            gap_boost += _digbala_b; gap_detail['digbala_h10'] = round(_digbala_b, 3)
        # AC14b: Jupiter/Mercury Digbala in H1 → small research/advisory boost
        for _dp in ('Jupiter', 'Mercury'):
            if ph.get(_dp, 0) == 1 and aff.get(_dp, 0) >= 0.25:
                _db1_b = min(0.03, aff.get(_dp, 0) * 0.10)
                gap_boost += _db1_b; gap_detail[f'digbala_h1_{_dp.lower()}'] = round(_db1_b, 3)

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
            gap_boost = min(gap_boost, _cap)
        # Q6: Geometric diminishing marginal returns (replaces flat linear cap).
        # Formula equivalent to 1 - prod(1 - boost_i) applied to the accumulated sum.
        # Converts the linear sum to its geometric equivalent, which naturally:
        #   - Allows differentiation above 0.40 (linear cap was 0.55 but compressed this band)
        #   - Prevents saturation: no matter how many signals fire, boost < 1.0
        #   - Preserves ordering: more signals always = higher boost, but with declining increments
        # Geometric conversion: if linear_boost = sum(b_i), geometric ≈ 1 - exp(-linear_boost)
        # This is the exact limit of 1-prod(1-b_i) as each b_i → 0 and n → ∞.
        if gap_boost > 0:
            gap_boost = 1.0 - _math.exp(-gap_boost)
        # T3-D: global soft ceiling. Geometric compression preserves ordering;
        # the 0.55 ceiling prevents a large stack of correlated minor rules
        # from overpowering the independently computed base score.
        gap_boost = max(-0.20, min(gap_boost, 0.55))

        _yk_planet    = _YOGAKARAKA_PLANET.get(lagna_sign, "")
        _ak_is_arts   = ak in ("Venus", "Moon", "Ketu")
        if (_fid in _MATERIAL_GRIT_FIELDS
                and not _ak_is_arts
                and (ak == "Saturn" or _yk_planet == "Saturn")
                and _top_karaka in ("Saturn", "Mars")):
            gap_boost += 0.15; gap_detail["material_grit"] = 0.15

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
                gap_boost += _b_vaf; gap_detail["venus_arts_force"] = round(_b_vaf, 3)

        # AmK Venus arts force only when AK is also arts-aligned (Venus/Moon).
        # When AK is Mars/Saturn/Mercury/Sun, the soul mandate overrides AmK career tilt.
        if domain == "arts" and amk == "Venus" and digs.get("Venus", "") in ("EXALTED", "OWN") \
                and ak in ("Venus", "Moon", ""):
            gap_boost += 0.08; gap_detail["venus_arts_force_amk"] = 0.08

        if domain in ("arts",) and ak == "Venus" and any(k in _gate_text.lower() for k in ("design","fashion","interior","textile","graphic","ux","product")):  # R3 fix: "design" not a real domain; fire on arts+design-label
            _ven_dig_d  = digs.get("Venus", "")
            _ven_cmb_d  = "Venus" in set(combust)
            if _ven_dig_d in ("EXALTED", "OWN"):                  _b_vdf = 0.18
            elif "Venus" in nb_set:                                _b_vdf = 0.15
            elif _ven_dig_d not in ("DEBILITATED",) and not _ven_cmb_d: _b_vdf = 0.07
            else:                                                   _b_vdf = 0.0
            if _b_vdf > 0:
                gap_boost += _b_vdf; gap_detail["venus_design_force"] = round(_b_vdf, 3)

        if domain in ("arts", "humanities") and ak == "Moon" and digs.get("Moon", "") in ("EXALTED", "OWN"):
            _b_maf = 0.32 if domain == "arts" else 0.09
            gap_boost += _b_maf; gap_detail["moon_arts_force"] = round(_b_maf, 3)

        # Moon humanities force — Moon is AK_PRIME_DOMAIN for (medicine, humanities)
        if domain == "humanities" and ak == "Moon":
            _moon_dig_hf = digs.get("Moon", "")
            if _moon_dig_hf in ("EXALTED", "OWN"):   _b_mhf = 0.18
            elif "Moon" in nb_set:                    _b_mhf = 0.12
            elif _moon_dig_hf not in ("DEBILITATED",): _b_mhf = 0.07
            else:                                      _b_mhf = 0.0
            if _b_mhf > 0:
                gap_boost += _b_mhf; gap_detail["moon_humanities_force"] = round(_b_mhf, 3)

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
                gap_boost += _arts_guard
                gap_detail["arts_placement_guard"] = round(_arts_guard, 3)

        if domain == "medicine" and ak == "Moon" and digs.get("Moon", "") in ("EXALTED", "OWN"):
            gap_boost += 0.12; gap_detail["moon_medicine_force"] = 0.12

        if (domain == "medicine" and ak == "Moon" and amk == "Jupiter"
                and digs.get("Moon", "") in ("EXALTED", "OWN")
                and digs.get("Jupiter", "") in ("EXALTED", "OWN")):
            gap_boost += 0.08; gap_detail["moon_jupiter_medicine_force"] = 0.08

        _moon_sign = planets_d1.get("Moon", {}).get("sign", "")
        _jup_sign  = planets_d1.get("Jupiter", {}).get("sign", "")
        if (domain == "medicine" and ak == "Moon"
                and _moon_sign and _jup_sign and _moon_sign == _jup_sign
                and digs.get("Moon", "") in ("EXALTED", "OWN")
                and digs.get("Jupiter", "") in ("EXALTED", "OWN", "NEECHA_BHANGA")):
            gap_boost += 0.15; gap_detail["gaja_kesari_medicine_force"] = 0.15

        if domain == "medicine" and ak == "Jupiter" and digs.get("Jupiter", "") in ("EXALTED", "OWN"):
            gap_boost += 0.20; gap_detail["jupiter_ak_medicine_force"] = 0.20

        _pisces_benefic = (planets_d1.get("Jupiter", {}).get("sign") == "Pisces"
                           and planets_d1.get("Venus", {}).get("sign") == "Pisces")
        if _pisces_benefic and domain in ("law", "arts", "medicine"):
            gap_boost += 0.12; gap_detail["pisces_benefic_force"] = 0.12

        _jup_mer_pair = ((ak == "Jupiter" and amk == "Mercury") or (ak == "Mercury" and amk == "Jupiter"))
        if domain == "interdisciplinary" and _jup_mer_pair:
            gap_boost += 0.15; gap_detail["interdisciplinary_mixed_karaka"] = 0.15

        if domain in ("science", "interdisciplinary") and ak == "Ketu":
            gap_boost += 0.10; gap_detail["ketu_research_force"] = 0.10

        if domain == "technology" and ak == "Mercury":
            _mer_dig = digs.get("Mercury", "")
            if _mer_dig in ("EXALTED", "OWN"):      _b_mtf = 0.30
            elif "BudhaAditya" in set(yogas) and _mer_dig != "DEBILITATED": _b_mtf = 0.30
            elif "Mercury" in nb_set:               _b_mtf = 0.15
            elif _mer_dig == "DEBILITATED":
                _mer_sign  = planets_d1.get("Mercury", {}).get("sign", "")
                _mer_disp  = {"Pisces": "Jupiter", "Virgo": "Mercury"}.get(_mer_sign, "")
                _b_mtf = 0.12 if (_mer_disp and digs.get(_mer_disp, "") == "EXALTED") else 0.05
            else:                                   _b_mtf = 0.15
            gap_boost += _b_mtf; gap_detail["mercury_tech_force"] = round(_b_mtf, 3)

        if (domain == "technology" and amk == "Mercury"
                and digs.get("Mercury", "") in ("EXALTED", "OWN")
                and _top_karaka in ("Mercury", "Rahu")):
            gap_boost += 0.10; gap_detail["mercury_amk_tech_force"] = 0.10

        # R3 fix: "government"/"civil_services"/"defence" not real domains; use "public"
        if (domain in ("public", "interdisciplinary", "science")
                and ak == "Sun" and digs.get("Sun", "") in ("EXALTED", "OWN") and amk != "Jupiter"):
            gap_boost += 0.20; gap_detail["sun_leadership_force"] = 0.20

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
                gap_boost += _b_jlf; gap_detail["jupiter_law_force"] = round(_b_jlf, 3)

        if (domain in ("law", "education", "humanities") and amk == "Jupiter"
                and digs.get("Jupiter", "") in ("EXALTED", "OWN") and ak in ("Jupiter", "Sun", "")):
            gap_boost += 0.08; gap_detail["jupiter_amk_law_force"] = 0.08

        if (domain == "engineering" and ak == "Mars"
                and digs.get("Mars", "") in ("EXALTED", "OWN")
                and "Mars" not in (set(combust) | cazimi_set)):
            gap_boost += 0.12; gap_detail["mars_engineering_force"] = 0.12
        elif (domain == "engineering" and ak == "Mars"
                and digs.get("Mars", "") not in ("DEBILITATED",)
                and "Mars" not in (set(combust) | cazimi_set)):
            gap_boost += 0.07; gap_detail["mars_engineering_force"] = 0.07

        if (_fid in _MATERIAL_GRIT_FIELDS and amk == "Mars"
                and digs.get("Mars", "") in ("EXALTED", "OWN")
                and _top_karaka in ("Mars", "Saturn")):
            gap_boost += 0.10; gap_detail["mars_amk_engineering_force"] = 0.10

        if (domain == "engineering" and ak == "Saturn"
                and digs.get("Saturn", "") in ("EXALTED", "OWN")
                and "Saturn" not in (set(combust) | cazimi_set)
                and _top_karaka in ("Mars", "Saturn")):
            gap_boost += 0.15; gap_detail["saturn_ak_engineering_force"] = 0.15

        if (domain == "engineering" and amk == "Saturn"
                and digs.get("Saturn", "") in ("EXALTED", "OWN")
                and "Saturn" not in set(combust)
                and _top_karaka in ("Mars", "Saturn")):
            gap_boost += 0.10; gap_detail["saturn_amk_engineering_force"] = 0.10

        if _fid in _MATERIAL_GRIT_FIELDS and "Mars" in nb_set and _yk_planet == "Mars":
            gap_boost += 0.07; gap_detail["nb_mars_yk_engineering_force"] = 0.07

        # S153: NB Mars as yoga-karak partially restores engineering domain even when Mars
        # is not AK/AmK.  Classical Neecha Bhanga = near-Raja-Yoga strength for the YK
        # planet's natural significations.  Only fires for engineering fields not covered
        # by _MATERIAL_GRIT_FIELDS (those already get 0.07 above).
        if (domain == "engineering" and "Mars" in nb_set and _yk_planet == "Mars"
                and _fid not in _MATERIAL_GRIT_FIELDS):
            gap_boost += 0.06; gap_detail["nb_mars_yk_broad_engineering_restore"] = 0.06

        _ll_house = ph.get(lagna_lord, 0)
        if (_ll_house == 10 and lagna_lord == ak
                and digs.get(lagna_lord, "") in ("EXALTED", "OWN")
                and _top_karaka == lagna_lord):
            gap_boost += 0.15; gap_detail["lagna_lord_h10_domain_force"] = 0.15

        if ak == "Venus" and lagna_sign == "Leo" and domain == "engineering":
            gap_boost -= 0.08; gap_detail["leo_venus_ak_engineering_guard"] = -0.08

        # gap_penalty was initialised to 0.0 above; continue accumulating (do not reset)
        p_ak_comb = min(_ak_combustion_penalty(aff, ak, combust, digs, planets_d1=planets_d1, vargottama_planets=vargottama), 0.15)
        gap_penalty += p_ak_comb; gap_detail["ak_combustion_penalty"] = round(-p_ak_comb, 3)
        p_dust = _dusthana_lord_penalty(aff, lagna_sign, house_lords, lagna_lord, _gate_text, eff_strengths, planet_house=ph)
        gap_penalty += p_dust; gap_detail["dusthana_penalty"] = round(-p_dust, 3)
        p_d10 = _d10_consistency_penalty(aff, getattr(payload_data, "d10_house_occupancy", {}), label=_gate_text)
        gap_penalty += p_d10; gap_detail["d10_dusthana_penalty"] = round(-p_d10, 3)

        # F: Ashtakavarga Sarvashtakavarga Bindu house-capability filter (Round 6)
        _sav_house   = ph.get(_top_karaka, 0)
        _sav_bindus  = (sav.get(str(_sav_house), sav.get(_sav_house, 28))
                        if sav and _sav_house else 28)
        _sav_factor  = max(0.80, min(1.20, 1.0 + (_sav_bindus - 28) * 0.01))
        blended      = blended * _sav_factor
        gap_detail["sav_bindu_factor"] = round(_sav_factor, 3)

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
            gap_detail["edu_house_sav_factor"] = round(_edu_sav_factor, 3)

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
        gap_boost += _b; gap_detail["gana_workplace_fit"] = round(_b, 3)
        _b = _dosha_burnout_modifier(_gate_text, _moon_nak_e)
        gap_boost += _b; gap_detail["dosha_burnout"] = round(_b, 3)
        _b = min(_nakshatra_devata_bonus(_gate_text, _moon_nak_e, _lagna_nak_e), _PCC)
        gap_boost += _b; gap_detail["devata_domain"] = round(_b, 3)
        _b = min(_foreign_career_multiplier(_gate_text, payload_data), _PCC)
        gap_boost += _b; gap_detail["foreign_career_mult"] = round(_b, 3)
        _ghati_sign_e = getattr(payload_data, "ghati_lagna_sign", "") or ""
        _sree_sign_e  = getattr(payload_data, "sree_lagna_sign", "") or ""
        _b = min(_ghati_lagna_bonus(_gate_text, _ghati_sign_e, digs), _PCC)
        gap_boost += _b; gap_detail["ghati_lagna"] = round(_b, 3)
        _b = min(_sree_lagna_bonus(_gate_text, _sree_sign_e, digs), _PCC)
        gap_boost += _b; gap_detail["sree_lagna"] = round(_b, 3)
        # GAP-FIX (2026-07): Hora Lagna / Bhava Lagna / Bhrigu Bindu -- now
        # actually populated by engine_io.py (see its wiring notes); these
        # boosts silently no-op (return 0.0) if birth data was insufficient
        # to compute them, same as ghati/sree above already did.
        _hora_sign_e   = getattr(payload_data, "hora_lagna_sign", "") or ""
        _bhava_sign_e  = getattr(payload_data, "bhava_lagna_sign", "") or ""
        _bhrigu_sign_e = getattr(payload_data, "bhrigu_bindu_sign", "") or ""
        _b = min(_hora_lagna_bonus(_gate_text, _hora_sign_e, digs), _PCC)
        gap_boost += _b; gap_detail["hora_lagna"] = round(_b, 3)
        _b = min(_bhava_lagna_bonus(_gate_text, _bhava_sign_e, digs), _PCC)
        gap_boost += _b; gap_detail["bhava_lagna"] = round(_b, 3)
        _b = min(_bhrigu_bindu_bonus(_gate_text, _bhrigu_sign_e, digs), _PCC)
        gap_boost += _b; gap_detail["bhrigu_bindu"] = round(_b, 3)
        _h3_lord_e  = house_lords.get("3",  house_lords.get(3, ""))
        _h8_lord_e  = house_lords.get("8",  house_lords.get(8, ""))
        _h9_lord_e  = house_lords.get("9",  house_lords.get(9, ""))
        _h11_lord_e = house_lords.get("11", house_lords.get(11, ""))
        _b = min(_h3_skills_bonus(_gate_text, _h3_lord_e, ph.get(_h3_lord_e, 0), aff, digs), _PCC)
        gap_boost += _b; gap_detail["h3_skills"] = round(_b, 3)
        _b = min(_h8_research_bonus(_gate_text, _h8_lord_e, ph.get(_h8_lord_e, 0), aff, digs), _PCC)
        gap_boost += _b; gap_detail["h8_research"] = round(_b, 3)
        _b = min(_h9_dharma_bonus(_gate_text, _h9_lord_e, ph.get(_h9_lord_e, 0), h10_lord, aff, digs), _PCC)
        gap_boost += _b; gap_detail["h9_dharma"] = round(_b, 3)
        _b = min(_h11_network_gains_bonus(_gate_text, _h11_lord_e, ph.get(_h11_lord_e, 0), h10_lord, aff, digs), _PCC)
        gap_boost += _b; gap_detail["h11_network"] = round(_b, 3)
        _b = min(_budha_aditya_yoga_bonus(_gate_text, planets_d1, combust, aff), _PCC)
        gap_boost += _b; gap_detail["budha_aditya"] = round(_b, 3)
        _b = min(_saraswati_yoga_bonus(_gate_text, ph, aff), _PCC)
        gap_boost += _b; gap_detail["saraswati_yoga"] = round(_b, 3)
        # _kemadruma_yoga_penalty's `label` param is unused inside the function (pure
        # Moon-house structural check) -- intentionally left as `label` (Gap-18b audit).
        _b = _kemadruma_yoga_penalty(label, ph, planets_d1)
        gap_boost += _b; gap_detail["kemadruma"] = round(_b, 3)
        _b = _chandal_yoga_signal(_gate_text, ph, aff)
        gap_boost += _b; gap_detail["chandal_yoga"] = round(_b, 3)
        _sun_sign_e  = planets_d1.get("Sun", {}).get("sign", "") if isinstance(planets_d1.get("Sun"), dict) else ""
        _moon_sign_e = planets_d1.get("Moon", {}).get("sign", "") if isinstance(planets_d1.get("Moon"), dict) else ""
        _b = min(_sudarshana_convergence_bonus(
            _gate_text, lagna_sign, _sun_sign_e, _moon_sign_e,
            house_lords, ph, aff, digs), _PCC)
        gap_boost += _b; gap_detail["sudarshana"] = round(_b, 3)

        # ── P3-1: D3 / D20 / D30 divisional boosts ───────────────────────────
        from .boosts import (
            _d3_drekkana_skills_bonus, _d20_vimshamsha_spiritual_calling,
            _d30_trimsamsha_obstacle_check,
        )
        _d3_digs  = getattr(payload_data, "d3_planet_dignities",  {}) or {}
        _d20_digs = getattr(payload_data, "d20_planet_dignities", {}) or {}
        _d30_digs = getattr(payload_data, "d30_planet_dignities", {}) or {}
        _b = min(_d3_drekkana_skills_bonus(_gate_text, _d3_digs, aff), _PCC)
        gap_boost += _b; gap_detail["d3_drekkana"] = round(_b, 3)
        _b = min(_d20_vimshamsha_spiritual_calling(_gate_text, _d20_digs, aff), _PCC)
        gap_boost += _b; gap_detail["d20_vimshamsha"] = round(_b, 3)
        # _d30_trimsamsha_obstacle_check's `label` param is unused inside the function
        # (pure D30 dignity iteration) -- intentionally left as `label` (Gap-18b audit).
        _b = _d30_trimsamsha_obstacle_check(label, _d30_digs, aff)   # can be negative
        gap_boost += _b; gap_detail["d30_trimsamsha"] = round(_b, 3)

        # ── P3-2: Extended Jaimini karaka boosts ─────────────────────────────
        from .boosts import (
            _gnk_competitive_bonus, _dk_partnership_bonus, _pk_creative_bonus,
        )
        _gnk = getattr(payload_data, "gnatikaraka", "") or ""
        _dk  = getattr(payload_data, "darakaraka",  "") or ""
        _pk  = getattr(payload_data, "putrakaraka", "") or ""
        _b = min(_gnk_competitive_bonus(_gate_text, _gnk, ph, digs, aff), _PCC)
        gap_boost += _b; gap_detail["gnk_competitive"] = round(_b, 3)
        _b = min(_dk_partnership_bonus(_gate_text, _dk, ph, digs, aff), _PCC)
        gap_boost += _b; gap_detail["dk_partnership"] = round(_b, 3)
        _b = min(_pk_creative_bonus(_gate_text, _pk, ph, digs, aff), _PCC)
        gap_boost += _b; gap_detail["pk_creative"] = round(_b, 3)
        # ── End World-Class Upgrade signals ──────────────────────────────────

        # genuinely indicated; below that, gap_boost is zeroed or capped 70%.
        # ═══════════════════════════════════════════════════════════════════
        # Gap-18b (generalized fix, audit 2026-07): _confluence_gate's gate_mult
        # multiplies the ENTIRE accumulated gap_boost (d3/d20/d30 varga bonuses,
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
        gap_detail["confluence_sources"] = _cgate["support_count"]
        gap_detail["confluence_gate"]    = _gate_label
        # Apply gate: multiply ALL accumulated gap_boost by the gate multiplier.
        # gate_mult = 0.0 → field not genuinely indicated; gap_boost zeroed.
        # gate_mult = 0.30 → weak signal; gap_boost cut to 30%.
        # gate_mult = 1.0 → genuinely supported; full gap_boost applies.
        gap_boost = gap_boost * _gate_mult

        _ak_dig = digs.get(ak, "")
        _base_weight = {"EXALTED": 1.00, "OWN": 0.90, "NEECHA_BHANGA": 0.85,
                        "NEUTRAL": 0.75, "DEBILITATED": 0.55}.get(_ak_dig, 0.75)
        gap_boost    = gap_boost * _base_weight

        # Q8: D60 Deity Vector — apply planet purity check before score computation.
        # The H10 lord's D60 deity quality gates the final gap_boost magnitude.
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
        gap_detail["d60_vimshopaka_gate"] = round(_d60_vim_gate, 4)
        gap_detail["d60_combined_observation"] = round(_d60_gate, 4)
        gap_detail["d60_role"] = "CONFIRMATION_ONLY" if _d60_allowed else "NOT_COMPUTED_INSUFFICIENT_BIRTH_TIME_PRECISION"
        gap_detail["d60_applied_multiplier"] = 1.0

        score = blended * (1.0 + gap_boost) * (1.0 - gap_penalty)

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
        # G3: combined_score drives a ±10% relative boost on the blended score
        # (was: addend of combined/100*1.5 which contributed <1.5 pts — negligible)
        _method_boost = (bvb_eval.get("combined_score", 50.0) - 50.0) / 100.0 * 0.20
        score = score * bvb_eval["astro_multiplier"] * (1.0 + _method_boost)

        # ── T3-A + T1-B: Real convergence grade using actual method normalized scores ──
        # Previously computed inside gap_boost using gap_detail proxy keys that don't
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
        }
        gap_detail["_sudarshana_layers"] = (
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
        gap_detail["_confidence_label"]    = _method_conv["confidence_label"]
        gap_detail["_convergence_mult"]    = round(_convergence_mult, 3)
        gap_detail["_convergence_count"]   = _method_conv.get("convergence_count", 0)
        # ── End T3-A + T1-B ────────────────────────────────────────────────────

        final_score = score

        _method_scores = bvb_eval.get("method_scores", {})
        _method_normalized_scores = bvb_eval.get("method_normalized_scores", {})
        _method_weights = bvb_eval.get("method_weights", {})
        _method_raw_total = round(bvb_eval.get("raw_combined_score", 50), 2)
        _method_total   = round(bvb_eval.get("combined_score", 50), 2)
        _method_log     = bvb_eval.get("method_log", {})
        _method_breakdown = {
            m: {
                "score":  round(float(_method_scores.get(m, 0.0)), 2),
                "normalized_score": round(float(_method_normalized_scores.get(m, 0.0)), 2),
                "weight": round(float(_method_weights.get(m, 0.0)), 2),
                "weighted_contribution": round(
                    float(_method_normalized_scores.get(m, 0.0)) * float(_method_weights.get(m, 0.0)),
                    2,
                ),
            }
            # Keep exported field rows aligned with compute_field_method_bundle().
            # Dashamsha and Sudarshana are first-class bundle methods; omitting
            # either here makes reports understate active evidence.
            for m in _method_scores.keys()
        }

        audit    = execute_qa_verification_v8_9(
            branch_name, payload_data, domain,
            war_result=war_result, d10_digs=d10_digs, d9_digs=d9_digs)
        conflict = assess_domain_mismatch(
            aptitudes, domain, digs, combust,
            detected_yogas=list(yogas), shadbala=shadbala,
            branch_affinity_weights=llm_affinity, ak=ak, amk=amk, nb_set=nb_set)

        if not aptitudes["meets_threshold"]: score *= 0.70
        if conflict["mismatch_risk"]:        score *= 0.85
        score *= audit.get("friction_multiplier", 1.0)
        if not audit["passed_qa_gate"]:      score *= 0.70
        # Debilitated AK prime-domain penalty: when the AK planet is DEBILITATED in
        # sign, its soul mandate is compromised — penalise its prime-domain fields.
        # Fires even with Neecha Banga (NB restores structure but not full force),
        # consistent with how venus_arts_force blocks the NB path for DEBILITATED Venus.
        if _ak_debil and domain in _AK_PRIME_DOMAINS.get(ak, ()):
            score *= 0.85
            gap_detail["debil_ak_soul_pen"] = -0.15

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
            gap_detail["ak_domain_flat"] = round(_ak_flat_scaled, 1)

        _thresh_mult   = 0.70 if not aptitudes["meets_threshold"] else 1.0
        _mismatch_mult = 0.85 if conflict["mismatch_risk"] else 1.0
        _friction_mult = audit.get("friction_multiplier", 1.0)
        _qa_mult       = 0.70 if not audit["passed_qa_gate"] else 1.0
        _after_gap     = round(blended * (1.0 + gap_boost) * (1.0 - gap_penalty), 4)

        # Gap-B fix: capture the score at each multiplicative step so final_chain is complete.
        # Previously the BVB astro_multiplier and ak_domain_flat were invisible between
        # after_penalty and final_score.
        _bvb_mult        = bvb_eval["astro_multiplier"]
        # N5: Use G3 formula in log (was old formula combined/100*1.5, now matches actual score)
        _logged_method_boost = (bvb_eval.get("combined_score", 50.0) - 50.0) / 100.0 * 0.20
        _after_bvb       = round(_after_gap * _bvb_mult * (1.0 + _logged_method_boost), 4)
        _after_thresh    = round(_after_bvb * _thresh_mult, 4)
        _after_mismatch  = round(_after_thresh * _mismatch_mult, 4)
        _after_friction  = round(_after_mismatch * _friction_mult, 4)
        _after_qa        = round(_after_friction * _qa_mult, 4)
        _ak_flat_logged  = round(gap_detail.get("ak_domain_flat", 0.0), 4)

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
            "gap_boosts":       {k: v for k, v in gap_detail.items() if isinstance(v, (int, float)) and v > 0.0},
            "gap_penalties":    {k: v for k, v in gap_detail.items() if isinstance(v, (int, float)) and v < 0.0},
            "gap_boost_total":  round(gap_boost, 4),
            "gap_penalty_total":round(gap_penalty, 4),
            "final_chain": {
                # Gap-B fix: complete chain now shows every multiplicative step.
                # Read as: blended → after_boost → after_penalty → after_bvb_multiplier
                #          → after_threshold → after_mismatch → after_friction
                #          → after_qa → after_ak_flat (= pre_norm_score).
                # The displayed final_score is set later by cross-batch 20-100 normalization
                # (see pre_norm_score in the result dict for the pre-normalization value).
                "blended":              round(blended, 4),
                "after_boost":          round(blended * (1.0 + gap_boost), 4),
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
            "verified_factors":  _build_verified_factors(gap_detail),
        }

        _reg_meta = _COURSE_REGISTRY.get(branch_name, {})
        _tier     = _reg_meta.get("tier_map", {})
        _ug_info  = _tier.get("UG", {})
        _pg_info  = _tier.get("PG", {})
        _phd_info = _tier.get("PhD", {})

        _all_pre_results.append({
            "field_id":      branch_name,
            "field_label":   label,
            "domain":        domain,
            "final_score":   round(score, 2),
            "affinity_score":  round(affinity_result["affinity_score"], 2),
            "composite_score": round(aptitudes["composite_score"], 2),
            "blended_score":   round(blended, 2),
            "gap_boost":       round(gap_boost, 3),
            "gap_penalty":     round(gap_penalty, 3),
            "gap_breakdown":   gap_detail,
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
            "score_confidence": gap_detail.get("_confidence_label", "MODERATE"),
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
            "method_weighted_contributions": bvb_eval.get("method_weighted_contributions", {}),
            "method_agreement":  bvb_eval.get("method_agreement", 0.0),
            "method_conflict":   bvb_eval.get("method_conflict", {"detected": False}),
            "method_signal_clarity": bvb_eval.get("method_signal_clarity", {}),
            "method_authority_priors": bvb_eval.get("method_authority_priors", {}),
            "knrao_score":       round(float(_method_scores.get("knrao", 0.0)), 2),
            "kp_score":          round(float(_method_scores.get("kp", 0.0)), 2),
            "jaimini_score":     round(float(_method_scores.get("jaimini", 0.0)), 2),
            "parashara_score":   round(float(_method_scores.get("parashara", 0.0)), 2),
            "dashamsha_score":   round(float(_method_scores.get("dashamsha", 0.0)), 2),
            "sudarshana_score":  round(float(_method_scores.get("sudarshana", 0.0)), 2),
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

    for _i, _ri in enumerate(_all_pre_results):
        for _j, _rj in enumerate(_all_pre_results):
            if _i >= _j:
                continue
            if abs(_ri["final_score"] - _rj["final_score"]) > _TB_THRESHOLD:
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

    for _r in top_35:
        if _r.get("final_score", 0.0) > 100.0:
            _r["final_score"] = 100.0

    # Defensive re-sort: guarantee strict descending final_score order no
    # matter what upstream slotting/selection steps did, so the printed
    # "ordered by Total" claim is always actually true.
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
            "affinity_score":           round(_r.get("affinity_score", 0), 2),
            "composite_score":          round(_r.get("composite_score", 0), 2),
            "blended_score":            round(_r.get("blended_score", 0), 2),
            "gap_boost":                round(_r.get("gap_boost", 0), 3),
            "gap_penalty":              round(_r.get("gap_penalty", 0), 3),
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
            "boost_pct":                round(_r.get("gap_boost", 0.0) * 100, 1),
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
        _wp = compute_wealth_potential(_item, house_lords, ph, eff_strengths)
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


from .engine_io import _load_course_registry
from .registry_result_enricher import attach_v12_registry_metadata


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
        ev = row.get("evidence_summary")
        if isinstance(ev, dict):
            fs = float(row.get("final_score", 0.0) or 0.0)
            ev["final_score"] = fs
            ev["confidence_band"] = confidence_band(fs)
        row["score_confidence_note"] = _build_score_confidence_note(row)
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
        "Cross-method agreement across up to 6 scoring channels (KNRao, KP, "
        "Jaimini, Parashara, Dashamsha, Sudarshana). These are correlated, "
        "not independent, evidence -- several share structural inputs "
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


def _finalize_published_results(results, payload_data, *, llm_used=False):
    """One authoritative finalization path for CLI, reports and API callers."""
    results = _sort_by_final_score_desc(results)
    results = _attach_registry_before_return(results)
    results, payload_data.release_candidate_readiness = apply_release_4_7(
        results, payload_data.canonical_fact_quality_report, payload_data
    )
    results = apply_publication_ranking_policy(results)
    results = _enforce_hard_lockout_publication_order(results)
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

    if not llm_authorized:
        return _finalize_published_results(top35, payload_data, llm_used=False)

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
        return results

    logger.warning("LLM enrichment failed or skipped — returning deterministic top-35.")
    return _finalize_published_results(top35, payload_data, llm_used=False)
