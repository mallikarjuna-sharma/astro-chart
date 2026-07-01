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

from .affinity import BRANCH_PLANET_AFFINITY, compute_branch_affinity_score_llm, apply_vargottama_affinity_uplift
from .engine_io import compute_aptitude_by_domain, _load_course_registry
from .field_methods import compute_field_method_bundle
from .field_methods.common import (
    FIELD_PRIORITY_GROUPS,
    METHOD_SCORE_CAP,
    normalize_method_score,
    prioritize_rows,
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
from .boosts import _ALL_PLANETS


def _log_norm_score(x: float, soft_cap: float) -> float:
    if x <= soft_cap:
        return (x / soft_cap) * 100.0
    excess = (x - soft_cap) / soft_cap
    extension = 15.0 * _math.log1p(excess)
    return 100.0 + extension

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
    war_losers     = set(p for p, s in war_result.items() if s == "loser")
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
            # Fatal condition 3: Structural planet in domain afflicted (war only for non-STEM)
            # STEM (engineering/science): both war-loss AND combustion can be fatal (structural precision required)
            # Arts/law/medicine: only WAR LOSS triggers fatal — combustion of arts/healing planets is
            # a diminishment but not necessarily catastrophic (creativity/wisdom can persist through suppression)
            elif planet in ("Saturn", "Ketu") and domain in _ENG_SCI and (is_war_loser or is_combust):
                is_fatal = True
                reason = "defeated in war" if is_war_loser else "combust"
                notes_list.append(f"FATAL: {planet} {reason} in {domain} — "
                                   "structural/technical architecture severely disrupted.")
            # Fatal condition 3b: Structural planet war-loss in non-STEM domains (symmetry fix)
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
        or (ak == "Venus" and "Venus" in nb_set)        # NB Venus: structural arts soul even if combust
        or (ak == "Moon"  and planet_dignities.get("Moon",  "") in ("EXALTED", "OWN"))
        or (amk == "Venus" and planet_dignities.get("Venus", "") in ("EXALTED", "OWN"))
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

    methods = ("knrao", "kp", "jaimini", "parashara")
    from .field_methods import METHOD_WEIGHTS

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
        r["explainability_matrix"] = _build_explainability_matrix(
            r.get("field_id", ""),
            {m: round(norm_scores.get(m, 0.0), 2) for m in methods}
        )
    return results


def _build_verified_factors(gap_detail: Dict[str, float], threshold_pct: float = 2.0) -> str:
    """XAI-B: Return only gap-boost components above threshold for LLM token grounding.

    Converts proportion values to percentage points; excludes internal keys (prefix _).
    Returns pipe-separated 'key:+val%' string or empty string.
    """
    parts = []
    for key, val in sorted(gap_detail.items(), key=lambda x: -abs(x[1])):
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
    """P1: Auto-resolve career phase from age/experience or explicit payload field."""
    explicit = getattr(payload_data, "career_phase", "auto")
    if explicit and explicit.lower() != "auto":
        return explicit.lower()
    age = float(getattr(payload_data, "current_age", 0) or 0)
    yoe = float((getattr(payload_data, "career_context", {}) or {}).get("years_experience", 0) or 0)
    if age >= 40 or yoe >= 15:
        return "senior"
    elif age >= 28:
        return "mid"
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
) -> Dict[str, Any]:
    """Compute BVB paradigm-ensemble career score for a single field.

    Delegates to compute_field_method_bundle and returns the full evaluation dict
    including method_scores, combined_score, and astro_multiplier.
    """
    from .field_methods import compute_field_method_bundle
    return compute_field_method_bundle(payload_data, domain, hard_affinity, field_id)



def _run_normalization_stage(payload_data: NatalPayloadV2) -> tuple:
    """Pipeline Stage 1 — deterministic scoring and normalisation.

    Runs the full field-scoring loop over all registered fields, then applies
    per-method Min-Max normalisation (Arch-B) and inter-domain soft-max
    normalisation (S2).  Returns the top-35 pre-scored payload ready for LLM
    dispatch, plus the context vars the LLM stage needs:

        (top35_for_llm, eff_strengths, lagna_sign, ak)
    """

    results    = []
    shadbala   = getattr(payload_data, "shadbala", {})
    sav        = getattr(payload_data, "sav_points_houses", {})
    digs       = getattr(payload_data, "planet_dignities", {})
    planets_d1 = getattr(payload_data, "planets_d1", {})  # moved up: needed by combust detection
    combust    = getattr(payload_data, "combust_planets", []) or []
    # A3 fix: compute combustion from planets_d1 when payload field is empty
    if not combust and planets_d1:
        _det_c, _det_caz = _det_combust(planets_d1)
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
    payload_data.planet_modifier_flags = _extract_modifier_flags(planet_trace)

    # Career Timeline
    _cc = getattr(payload_data, "career_context", {}) or {}
    if _cc and not _cc.get("_block_reason"):
        try:
            from .timeline_inputs import validate_career_context
            from .timeline import build_career_timeline, TimelineChartInput
            _, _, _tl_mode = validate_career_context(
                _cc, current_age, lagna_sign=lagna_sign)
            if _tl_mode:
                payload_data.career_timeline = build_career_timeline(
                    TimelineChartInput.from_payload(payload_data),
                    eff_strengths, _cc, mode=_tl_mode)
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
    edu_ranked        = [(p, round(v, 3)) for p, v in sorted_planets]
    edu_planet_reasons = {
        p: f"Core astrological driver for academic alignment (Effective Strength: {round(v, 2)})"
        for p, v in sorted_planets[:3]
    }
    logger.info(f"Top planets by effective strength: {[(p, round(v,3)) for p,v in sorted_planets[:5]]}")

    _DEFAULT_AFFINITY: Dict[str, float] = {"Mercury": 0.30, "Jupiter": 0.25, "Saturn": 0.25, "Sun": 0.20}
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
        if hard_affinity:
            max_vector_weight = max(hard_affinity.values())
            is_advanced_tech_node = (hard_affinity.get("Rahu", 0.0) + hard_affinity.get("Mercury", 0.0)) > 0.45
            if max_vector_weight >= 0.35 or is_advanced_tech_node:
                current_affinity_blend = 0.55
                current_domain_blend   = 0.45
            else:
                current_affinity_blend = 0.40
                current_domain_blend   = 0.60
        else:
            current_affinity_blend = 0.40
            current_domain_blend   = 0.60

        blended = (current_domain_blend * composite_norm) + (current_affinity_blend * affinity_norm)


        gap_boost, gap_detail = 0.0, {}
        gap_penalty = 0.0
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
        b = min(_stellium_bonus(label, ph), _PCC); gap_boost += b; gap_detail["stellium"] = round(b, 3)
        # AC1 fix: Argala H10 career activation
        _top_aff_planet = max(hard_affinity.items(), key=lambda x: x[1])[0] if hard_affinity else ""
        if _top_aff_planet and _top_aff_planet in _argala_h10:
            _argala_b = min(0.06 * aff.get(_top_aff_planet, 0.1) * 5, 0.06)
            gap_boost += _argala_b; gap_detail["argala_h10"] = round(_argala_b, 3)
        elif _top_aff_planet:
            # Virodha Argala (12th/10th/3rd from H10) — counteracts career support
            _virodha = {(10 - 1) % 12 + 1, (10 + 1) % 12 + 1, (10 + 2) % 12 + 1}  # 9, 11(skip argala), 12
            if ph.get(_top_aff_planet, 0) == (10 - 2) % 12 + 1:  # 12th from H10 = H9
                gap_penalty += 0.03; gap_detail["virodha_argala"] = -0.03
        b = min(_dasha_bonus(label, payload_data), _PCC); gap_boost += b; gap_detail["dasha"] = round(b, 3)
        b = min(_karakamsha_bonus(aff, karakamsha), _PCC); gap_boost += b; gap_detail["karakamsha"] = round(b, 3)
        b = min(_d24_ak_delta(label, payload_data), _PCC); gap_boost += b; gap_detail["d24_ak"] = round(b, 3)
        b = min(_d24_full_chart_bonus(aff, payload_data), _PCC); gap_boost += b; gap_detail["d24_full"] = round(b, 3)
        b = min(_lagna_lord_bonus(label, payload_data), _PCC); gap_boost += b; gap_detail["lagna_lord"] = round(b, 3)
        gap_detail["risk_appetite"] = 0.0
        b = _modernize_karakas_modifier(_fid, risk, amk, _kp_h10_star_lord, planets_d1)
        gap_boost += b; gap_detail["modernize_karakas"] = round(b, 3)
        b = min(_yogakaraka_bonus(aff, lagna_sign, shadbala, digs), _PCC)
        gap_boost += b; gap_detail["yogakaraka"] = round(b, 3)
        # LS3 fix: debilitated yogakaraka penalty → gap_penalty (not negative gap_boost)
        _yk_pen = _yogakaraka_debilitation_penalty(aff, lagna_sign, shadbala, digs)
        if _yk_pen > 0: gap_penalty += _yk_pen; gap_detail["yogakaraka_deb_pen"] = round(-_yk_pen, 3)
        b = min(_h10_lord_strength_bonus(aff, h10_lp, shadbala, digs), _PCC); gap_boost += b; gap_detail["h10_lord_str"] = round(b, 3)
        b = min(_h10_lord_trikona_bonus(aff, h10_lp, ph, digs), _PCC); gap_boost += b; gap_detail["h10_lord_trikona"] = round(b, 3)
        b = min(_exalted_planet_domain_bonus(aff, digs, label, lagna_sign), _PCC); gap_boost += b; gap_detail["exalted_domain"] = round(b, 3)
        b = min(_ul_lord_bonus(aff, ul), _PCC); gap_boost += b; gap_detail["ul_lord"] = round(b, 3)
        b = min(_d9_ak_delta(label, payload_data), _PCC); gap_boost += b; gap_detail["d9_ak"] = round(b, 3)
        b = min(_yoga_bonus(label, yogas, house_lords, digs), _PCC); gap_boost += b; gap_detail["yoga"] = round(b, 3)
        b = min(_h5_lord_bonus(aff, h5_lord), _PCC); gap_boost += b; gap_detail["h5_lord"] = round(b, 3)
        b = min(_amk_house_bonus(label, amk_house), _PCC); gap_boost += b; gap_detail["amk_house"] = round(b, 3)
        b = min(_ak_house_bonus(ak, ph.get(ak, 0), label), _PCC); gap_boost += b; gap_detail["ak_house"] = round(b, 3)

        # LS13 fix: soul-stack cap = 0.26 → max soul-domain gap_boost contribution.
        # Rationale: on a 75-blended field, 0.26 × 0.76 _base_weight ≈ +20 display pts.
        # Prevents AK/yogakaraka pile-on from overriding multi-method scoring.
        _soul_stack = gap_detail.get("ak_amk", 0) + gap_detail.get("yogakaraka", 0) + gap_detail.get("ak_house", 0)
        if _soul_stack > 0.26:
            _ss_excess = _soul_stack - 0.26
            gap_boost -= _ss_excess
            gap_detail["yogakaraka"] = round(gap_detail.get("yogakaraka", 0) - _ss_excess, 3)
            gap_detail["_soul_stack_cap"] = round(-_ss_excess, 3)

        b = min(_dasha_active_affinity_boost(aff, prime_career_lord, digs), _PCC); gap_boost += b; gap_detail["prime_dasha_affinity"] = round(b, 3)
        b = min(_peak_career_dasha_boost(aff, peak_lord, prime_career_lord, digs), _PCC); gap_boost += b; gap_detail["peak_md_boost"] = round(b, 3)
        _dasha_total = gap_detail.get("dasha", 0) + gap_detail.get("prime_dasha_affinity", 0) + gap_detail.get("peak_md_boost", 0)
        if _dasha_total > 0.22:
            _excess = _dasha_total - 0.22
            gap_boost -= _excess
            gap_detail["peak_md_boost"] = round(gap_detail.get("peak_md_boost", 0) - _excess, 3)

        b = min(_pratyantar_dasha_bonus(label, prd_lord, prd_houses), _PCC); gap_boost += b; gap_detail["prd_boost"] = round(b, 3)
        # AC2 fix: antardasha lord domain boost (half weight of main dasha)
        if _antardasha_lord and _antardasha_lord in aff and _antardasha_lord != prime_career_lord:
            _ad_w   = aff.get(_antardasha_lord, 0.0)
            _ad_dig = digs.get(_antardasha_lord, "")
            _ad_dig_scale = {"EXALTED": 1.40, "OWN": 1.15, "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.60}.get(_ad_dig, 1.0)
            _ad_b = min(_ad_w * _ad_dig_scale * 0.06, _PCC * 0.5)   # half of _PCC ceiling
            if _ad_b > 0:
                gap_boost += _ad_b; gap_detail["antardasha_affinity"] = round(_ad_b, 3)
        # AC5 fix: Rahu career signal — H10/H6 (upachaya) placement with strong STEM affinity
        _rahu_h = ph.get("Rahu", 0)
        if _rahu_h in (10, 6) and aff.get("Rahu", 0) >= 0.25:
            _rahu_b = min(0.06, aff["Rahu"] * 0.20)
            gap_boost += _rahu_b; gap_detail["rahu_career_h10h6"] = round(_rahu_b, 3)
        # AC5 fix: Ketu career signal — H9/H5 placement with research/mystical affinity
        _ketu_h = ph.get("Ketu", 0)
        _ketu_research_lbl = any(kw in label.lower() for kw in
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

        # AC7 fix: Vara (weekday) lord boost
        # The weekday lord at birth is a persistent temporal activator for its domain.
        # Classic vara lords: Sun=Sunday, Moon=Monday, Mars=Tuesday, Mercury=Wednesday,
        # Jupiter=Thursday, Venus=Friday, Saturn=Saturday
        _VARA_LORDS = {0:'Monday', 1:'Tuesday', 2:'Wednesday', 3:'Thursday',
                       4:'Friday', 5:'Saturday', 6:'Sunday'}
        _DAY_TO_PLANET = {'Monday':'Moon','Tuesday':'Mars','Wednesday':'Mercury',
                          'Thursday':'Jupiter','Friday':'Venus','Saturday':'Saturn','Sunday':'Sun'}
        _birth_weekday = getattr(payload_data, 'birth_weekday', '') or ''
        if not _birth_weekday:
            try:
                import datetime as _dt
                _bdate = getattr(payload_data, 'birth_date', '') or ''
                if _bdate:
                    _bd = _dt.date.fromisoformat(str(_bdate)[:10])
                    _birth_weekday = list(_VARA_LORDS.values())[_bd.weekday()]
            except Exception:
                _birth_weekday = ''
        _vara_planet = _DAY_TO_PLANET.get(_birth_weekday, '')
        if _vara_planet and _vara_planet in aff:
            _vara_aff = aff.get(_vara_planet, 0.0)
            _vara_top = max(aff.items(), key=lambda x: x[1])[0] if aff else ''
            if _vara_planet == _vara_top and _vara_aff >= 0.25:
                _vara_b = min(0.03, _vara_aff * 0.10)
                gap_boost += _vara_b; gap_detail['vara_lord'] = round(_vara_b, 3)

        b = min(_karakamsha_occupant_bonus(label, kara_occ, shadbala), _PCC); gap_boost += b; gap_detail["karakamsha_occ"] = round(b, 3)
        b = min(_d9_h10_bonus(aff, d9_chart, d9_lagna), _PCC); gap_boost += b; gap_detail["d9_h10"] = round(b, 3)
        b = min(_dharma_karma_bonus(aff, house_lords, ph), _PCC); gap_boost += b; gap_detail["dharma_karma"] = round(b, 3)
        b = min(_interest_preference_boost(label, interested_in, already_excel), _PCC); gap_boost += b; gap_detail["interest_pref"] = round(b, 3)
        b = min(_brahma_lord_bonus(label, brahma_lord, aff), _PCC); gap_boost += b; gap_detail["brahma_lord"] = round(b, 3)
        b = min(_d10_h10_bonus(aff, d10_chart, d10_lagna, d10_digs), _PCC); gap_boost += b; gap_detail["d10_h10"] = round(b, 3)
        b = min(_d10_lagna_lord_bonus(aff, d10_chart, d10_lagna, d10_digs), _PCC); gap_boost += b; gap_detail["d10_lagna_lord"] = round(b, 3)
        b = _gender_field_modifier(label, gender_val, aff, house_lords); gap_boost += b; gap_detail["gender_field"] = round(b, 3)
        b = min(_aspect_h10_bonus(aff, ph, digs, planets_d1=getattr(payload_data, "planets_d1", None)), _PCC)
        gap_boost += b; gap_detail["aspect_h10"] = round(b, 3)
        b = min(_maheshwara_lord_bonus(label, maheshwara_lord, aff), _PCC); gap_boost += b; gap_detail["maheshwara"] = round(b, 3)
        b = min(_bhavesha_phala_edu_bonus(label, aff, house_lords, ph), _PCC); gap_boost += b; gap_detail["bhavesha_phala"] = round(b, 3)
        b = min(_ak_planet_domain_boost(label, ak, digs.get(ak, ""), ph, amk, digs.get(amk, "")), 0.20); gap_boost += b; gap_detail["ak_planet_domain"] = round(b, 3)
        b = min(_karakamsha_domain_boost(label, domain, karakamsha), _PCC); gap_boost += b; gap_detail["karakamsha_domain"] = round(b, 3)
        b = min(_h3_lord_communication_boost(label, domain, house_lords, eff_strengths, ph), _PCC); gap_boost += b; gap_detail["h3_comm"] = round(b, 3)
        b = _h12_stellium_penalty(label, domain, ph); gap_boost += b; gap_detail["h12_stellium_pen"] = round(b, 3)

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
        _cluster_b = _priority_cluster_field_bonus(branch_name, label, eff_strengths)
        if _cluster_b > 0:
            gap_boost += min(_cluster_b, _PCC); gap_detail['cluster_bonus'] = round(min(_cluster_b, _PCC), 3)
        _space_cw  = _space_extractive_counterweight(branch_name, label, eff_strengths)
        _life_cw   = _life_science_space_counterweight(branch_name, label, eff_strengths)
        _eng_cw    = _life_science_engineering_counterweight(branch_name, label, eff_strengths)
        _total_cw  = _space_cw + _life_cw + _eng_cw
        if _total_cw > 0:
            gap_penalty += _total_cw; gap_detail['cluster_counterweight'] = round(-_total_cw, 3)

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
        _DOMAIN_THRESHOLD = {
            'medicine': 50.0, 'engineering': 48.0, 'law': 46.0,
            'technology': 44.0, 'science': 44.0,
            'arts': 36.0, 'music': 36.0, 'sports': 38.0,
            'commerce': 40.0, 'management': 40.0,
        }
        _domain_threshold = _DOMAIN_THRESHOLD.get(domain, 45.0)
        if blended < _domain_threshold and not _has_nb_support and not _has_yoga_support:
            _cap = 0.28 if _domain_threshold >= 48.0 else 0.30
            gap_boost = min(gap_boost, _cap)
        gap_boost = max(-0.20, min(gap_boost, 0.65))

        _yk_planet    = _YOGAKARAKA_PLANET.get(lagna_sign, "")
        _ak_is_arts   = ak in ("Venus", "Moon", "Jupiter", "Mercury", "Ketu")
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
            elif "Venus" in nb_set:
                _jup_dig_vaf = digs.get("Jupiter", "")
                _jup_h_vaf   = ph.get("Jupiter", 0)
                _strong_nb   = _jup_dig_vaf in ("EXALTED", "OWN") and _jup_h_vaf in (1, 4, 7, 10)
                _b_vaf = 0.30 if _strong_nb else 0.20
            elif _ven_dig not in ("DEBILITATED",) and not _ven_combust: _b_vaf = 0.07
            else:                                                         _b_vaf = 0.0
            if _b_vaf > 0:
                gap_boost += _b_vaf; gap_detail["venus_arts_force"] = round(_b_vaf, 3)

        if domain == "arts" and amk == "Venus" and digs.get("Venus", "") in ("EXALTED", "OWN"):
            gap_boost += 0.08; gap_detail["venus_arts_force_amk"] = 0.08

        if domain == "design" and ak == "Venus":
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

        # Arts placement guard: Venus must be arts-placed, not just career-strong.
        # When AK ≠ Venus and AmK ≠ Venus and Venus is in a career/dharma house (H9/H10)
        # rather than a creative house (H1/H5) or own sign (Taurus/Libra),
        # the chart lacks a genuine arts-soul indicator → apply a guard penalty.
        if domain == "arts" and ak != "Venus" and amk != "Venus":
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

        if (domain in ("law", "interdisciplinary", "science")
                and ak == "Sun" and digs.get("Sun", "") in ("EXALTED", "OWN") and amk != "Jupiter"):
            gap_boost += 0.20; gap_detail["sun_leadership_force"] = 0.20

        if (domain == "engineering" and ak == "Mars"
                and digs.get("Mars", "") in ("EXALTED", "OWN")
                and "Mars" not in (set(combust) | cazimi_set)
                and _top_karaka in ("Mars", "Saturn")):
            gap_boost += 0.12; gap_detail["mars_engineering_force"] = 0.12

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

        _ll_house = ph.get(lagna_lord, 0)
        if (_ll_house == 10 and lagna_lord == ak
                and digs.get(lagna_lord, "") in ("EXALTED", "OWN")
                and _top_karaka == lagna_lord):
            gap_boost += 0.15; gap_detail["lagna_lord_h10_domain_force"] = 0.15

        if ak == "Venus" and lagna_sign == "Leo" and domain == "engineering":
            gap_boost -= 0.08; gap_detail["leo_venus_ak_engineering_guard"] = -0.08

        p_ak_comb = min(_ak_combustion_penalty(aff, ak, combust, digs, planets_d1=planets_d1), 0.15)
        gap_penalty += p_ak_comb; gap_detail["ak_combustion_penalty"] = round(-p_ak_comb, 3)
        p_dust = _dusthana_lord_penalty(aff, lagna_sign, house_lords, lagna_lord, label, eff_strengths)
        gap_penalty += p_dust; gap_detail["dusthana_penalty"] = round(-p_dust, 3)
        p_d10 = _d10_consistency_penalty(aff, getattr(payload_data, "d10_house_occupancy", {}))
        gap_penalty += p_d10; gap_detail["d10_dusthana_penalty"] = round(-p_d10, 3)

        # F: Ashtakavarga Sarvashtakavarga Bindu house-capability filter (Round 6)
        _sav_house   = ph.get(_top_karaka, 0)
        _sav_bindus  = (sav.get(str(_sav_house), sav.get(_sav_house, 28))
                        if sav and _sav_house else 28)
        _sav_factor  = max(0.80, min(1.20, 1.0 + (_sav_bindus - 28) * 0.01))
        blended      = blended * _sav_factor
        gap_detail["sav_bindu_factor"] = round(_sav_factor, 3)

        # LS5 fix: _base_weight should reflect dignity quality only, not blended score
        # (blended already incorporates eff_strength which embeds shadbala + dignity;
        #  using blended again here double-counted strength signal).
        _ak_dig = digs.get(ak, "")
        _base_weight = {"EXALTED": 1.00, "OWN": 0.90, "NEECHA_BHANGA": 0.85,
                        "NEUTRAL": 0.75, "DEBILITATED": 0.55}.get(_ak_dig, 0.75)
        gap_boost    = gap_boost * _base_weight

        score = blended * (1.0 + gap_boost) * (1.0 - gap_penalty)

        bvb_eval = compute_field_method_bundle(payload_data, domain, hard_affinity, branch_name)
        score = (score * bvb_eval["astro_multiplier"]
                 + (bvb_eval.get("combined_score", 50.0) / 100.0) * 1.5)
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
            for m in ("knrao", "kp", "jaimini", "parashara")
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

        # AK/AmK domain flat supplement — applied after all multipliers so
        # soul-domain fields enter top-35 even when AK planet is Mrita/weak
        _ak_flat = _ak_domain_flat_supplement(label, ak, amk, digs)
        if _ak_flat > 0:
            # LS2 fix: scale by blended/100 so weak-base fields (blended=40) get
            # 40% of supplement vs strong-base (blended=100) fields getting full value.
            _ak_flat_scaled = round(_ak_flat * max(0.4, min(blended, 100.0) / 100.0), 2)
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
        _bvb_mult       = bvb_eval["astro_multiplier"]
        _combined_addend = round((bvb_eval.get("combined_score", 50.0) / 100.0) * 1.5, 4)
        _after_bvb      = round(_after_gap * _bvb_mult + _combined_addend, 4)
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
            "gap_boosts":       {k: v for k, v in gap_detail.items() if v > 0.0},
            "gap_penalties":    {k: v for k, v in gap_detail.items() if v < 0.0},
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
                "bvb_combined_addend":  _combined_addend,
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
            "affinity_planets": aff,
            "affinity_source": affinity_result.get("affinity_source", "default"),
            "top_affinity_planets": dict(
                sorted(affinity_result.get("planet_contributions", affinity_result.get("affinity_planets", {})).items(),
                       key=lambda x: x[1], reverse=True)[:3]),
            "aptitude_profile":  aptitudes,
            "structural_audit":  audit,
            "conflict_report":   conflict,
            "is_afflicted":      not audit["passed_qa_gate"],
            "war_losers":        [p for p, s in war_result.items() if s == "loser"],
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
            "knrao_score":       round(float(_method_scores.get("knrao", 0.0)), 2),
            "kp_score":          round(float(_method_scores.get("kp", 0.0)), 2),
            "jaimini_score":     round(float(_method_scores.get("jaimini", 0.0)), 2),
            "parashara_score":   round(float(_method_scores.get("parashara", 0.0)), 2),
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

    # LS6 fix: apply domain deduplication BEFORE LLM field selection so the
    # candidate list already reflects domain diversity (avoids wasting LLM calls
    # on fields that will be culled post-selection).
    _all_deduped = apply_domain_deduplication(_all_pre_results)
    top_35 = _all_deduped[:35]

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
        })

    # ── 360° Profile: chart-level scores ─────────────────────────────────────
    _corp_entrep = compute_corporate_entrepreneurial_score(
        ph, house_lords, eff_strengths, atmakaraka=ak
    )
    _geo = compute_geo_suitability(ph, house_lords, eff_strengths, lagna_sign)
    payload_data.corporate_entrepreneurial = _corp_entrep
    payload_data.geo_suitability            = _geo

    # ── GAP 1: Academic path + GAP 2: Institutional tier (MD-AD + transits) ─
    _academic_path      = compute_academic_path(house_lords, eff_strengths, ph)
    _transit_planets    = getattr(payload_data, "transit_planets", None) or {}
    _institutional_tier = compute_institutional_tier(
        ph, house_lords, eff_strengths, lagna_sign,
        md_lord=active_lord,
        ad_lord=_antardasha_lord,
        transit_planets=_transit_planets,
    )
    payload_data.academic_path      = _academic_path
    payload_data.institutional_tier = _institutional_tier

    # ── Per-field: wealth potential and burnout risk ───────────────────────────
    _combust_list = list(getattr(payload_data, "combust_planets", []) or [])
    _field_insights: Dict[str, Dict] = {}
    for _item in _top35_for_llm:
        _wp = compute_wealth_potential(_item, house_lords, ph, eff_strengths)
        _br = compute_burnout_risk(_item, ph, house_lords, eff_strengths, _combust_list)
        _nakshatra_data = {p: getattr(payload_data, 'nakshatra_data', {}).get(p, "")
                           for p in ph.keys()}
        _amk = getattr(payload_data, 'amatyakaraka', '') or ''
        _mn  = compute_micro_niches(_item, ph, house_lords, _amk, _nakshatra_data)
        _cm  = build_confidence_matrix(_item)
        _item["wealth_potential"]  = _wp
        _item["burnout_risk"]      = _br
        _item["geo_suitability"]   = _geo
        _item["micro_niches"]      = _mn
        _item["confidence_matrix"] = _cm
        # Stamp chart-level keys onto item so build_field_summary_json can read them
        _item["academic_path"]      = _academic_path
        _item["institutional_tier"] = _institutional_tier
        _fsj = build_field_summary_json(_item)
        _item["field_summary_json"] = _fsj
        # Promote execution_path to top-level so web_report / output.py can read it directly
        _item["execution_path"] = _fsj.get("execution_path", {})
        # Also cache by field_id so post-LLM stage can merge them back
        _field_insights[_item.get("field_id", "")] = {
            "wealth_potential":   _wp,
            "burnout_risk":       _br,
            "geo_suitability":    _geo,
            "micro_niches":       _mn,
            "confidence_matrix":  _cm,
            # Chart-level (same for all fields, stored here for convenience)
            "academic_path":      _academic_path,
            "institutional_tier": _institutional_tier,
            # Clean schema JSON
            "field_summary_json": _fsj,
            # Promoted for direct access
            "execution_path":     _fsj.get("execution_path", {}),
        }
    payload_data.field_insights = _field_insights

    # Detect cluster vs specialist chart and stamp onto payload + each field insight
    _chart_type = detect_chart_type(_top35_for_llm)
    payload_data.chart_type = _chart_type
    for _fid, _fi in _field_insights.items():
        _fi["chart_type"] = _chart_type

    return _top35_for_llm, eff_strengths, lagna_sign, ak
# ── Pipeline stage functions (Gap 1: isolated, independently testable) ────────

def _run_llm_stage(
    payload_data: "NatalPayloadV2",
    top35_for_llm: List[Dict],
    eff_strengths: Dict,
    lagna_sign: str,
    ak: str,
) -> List[Dict]:
    """Pipeline Stage 2 — LLM field selection.

    Accepts the pre-scored, shuffled top-35 and dispatches to the configured
    LLM provider.  Returns llm_results (list of selected field dicts).
    Falls back to    deterministic pre-score ranking when LLM is unavailable.
    """
    from .llm import _llm_fallback_from_top35
    shuffled = _prepare_unbiased_llm_payload(top35_for_llm)
    llm_results = call_llm_for_fields(
        payload_data,
        eff_strengths,
        shuffled,
    )
    if not llm_results:
        llm_results = _llm_fallback_from_top35(top35_for_llm)
    return llm_results


def _run_output_stage(llm_results: List[Dict]) -> List[Dict]:
    """Pipeline Stage 3 — post-LLM guards and domain deduplication."""
    validated = _enforce_post_llm_guards(llm_results)
    return apply_domain_deduplication(validated)


def run_engine(payload_data: "NatalPayloadV2") -> List[Dict]:
    """Public entry-point — thin orchestrator over four named pipeline stages.

    Stage 1 — Deterministic:  BVB scoring, gap-boost, normalization → top-35 for LLM.
    Stage 2 — LLM Selection:  shuffle + dispatch → ranked field list.
    Stage 3 — Output Guards:  post-LLM guard rails + domain deduplication.
    Stage 4 — Enrichment:     merge field_insights back onto each result.
    """
    _validate_payload_schema(payload_data)

    # Stage 1
    top35_for_llm, eff_strengths, lagna_sign, ak = _run_normalization_stage(payload_data)

    # Stage 2
    llm_results = _run_llm_stage(payload_data, top35_for_llm, eff_strengths, lagna_sign, ak)

    # Wire field-selection analytical_breakdown onto the payload as llm_selection_rationale.
    # This lets llm_narrative_builder.py inject the chart analysis into timeline narratives.
    if llm_results:
        _rationale = llm_results[0].get("llm_selection_rationale", "") or ""
        if _rationale and hasattr(payload_data, "llm_selection_rationale"):
            payload_data.llm_selection_rationale = _rationale
        elif _rationale:
            try:
                payload_data.llm_selection_rationale = _rationale   # type: ignore[attr-defined]
            except Exception:
                pass

    # Stage 3
    final = _run_output_stage(llm_results)

    # Stage 4 — merge field_insights (wealth, burnout, micro_niches, etc.) onto each result
    _insights   = getattr(payload_data, "field_insights", {})
    _chart_type = getattr(payload_data, "chart_type", {})
    for _r in final:
        _fid = _r.get("field_id", "")
        if _fid in _insights:
            _r.update(_insights[_fid])
        # Stamp chart_type on every result for renderer access
        if _chart_type:
            _r["chart_type"] = _chart_type

    # Optional SBC manifestation scoring (enabled via ENABLE_SBC env var)
    import os as _os_sbc
    if _os_sbc.getenv("ENABLE_SBC", "true").lower() not in ("false", "0", "no"):
        from .sbc import apply_sbc_manifestation
        from .micro_timing import compute_class12_transits

        # Use Class-12 board exam transits (March 15 of their 12th year) rather
        # than today's sky — SBC answers "will this manifest at exam time?" not "now"
        _dob        = getattr(payload_data, "dob", "") or ""
        _lagna_sign = getattr(payload_data, "lagna_sign", "Aries") or "Aries"
        try:
            _sbc_transit, _sbc_exam_date = compute_class12_transits(_dob, _lagna_sign)
            logger.info("SBC: using Class-12 transit date %s", _sbc_exam_date)
        except Exception as _sbc_te:
            logger.warning("SBC: class12 transit failed (%s) — falling back to today", _sbc_te)
            _sbc_transit   = getattr(payload_data, "transit_planets", None) or {}
            _sbc_exam_date = None

        final = apply_sbc_manifestation(final, payload_data, transit_planets=_sbc_transit)

        # Stamp exam date on every result for display in report
        if _sbc_exam_date:
            _exam_label = _sbc_exam_date.strftime("March %Y")
            for _r in final:
                _r["sbc_exam_date"] = _exam_label

    # Backfill sbc_pct into confidence_matrix now that sbc_event_score is set.
    for _r in final:
        _sbc_raw = float(_r.get("sbc_event_score", 0) or 0)
        _sbc_pct = min(int(round(_sbc_raw * 0.92 + 5)), 99) if _sbc_raw > 5 else int(round(_sbc_raw))
        _cm = _r.get("confidence_matrix")
        if isinstance(_cm, dict):
            _cm["sbc_pct"] = _sbc_pct
        _fsj = _r.get("field_summary_json")
        if isinstance(_fsj, dict):
            _fsj_cm = _fsj.get("confidence_matrix")
            if isinstance(_fsj_cm, dict):
                _fsj_cm["sbc_timing"] = f"{_sbc_pct}%"

    return final
