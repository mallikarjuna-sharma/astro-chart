"""JyotishAI — Main scoring engine (run_engine) and QA helpers."""
import math as _math
from typing import Dict, List, Tuple, Set, Any, Optional

from .payload import NatalPayloadV2, ENGINE_VERSION, logger
from .constants import (
    _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES,
    _SIGN_LORD, _STREAM_MAP, _VALID_PLANETS, DOMAIN_STRATEGIES,
)
from .astro import (
    compute_dignity, _compute_eff_strengths, _get_planetary_aspects,
    _detect_yogas, _detect_neecha_bhanga, _is_vargottama,
    _get_active_dasha_lord, _planet_abs_degree, _detect_planetary_war,
    _get_nakshatra_dignity,
)
from .affinity import BRANCH_PLANET_AFFINITY, compute_branch_affinity_score_llm
from .engine_io import compute_aptitude_by_domain, _load_course_registry
from .boosts import (
    _kp_h10_branch_strength, _h10_sublord_bonus, _kp_edu_starlord_bonus,
    _dasha_bonus, _karakamsha_bonus, _ak_combustion_penalty,
    _d24_ak_delta, _lagna_lord_bonus, _risk_appetite_bonus,
    _yogakaraka_bonus, _h10_lord_strength_bonus, _ul_lord_bonus,
    _d9_ak_delta, _yoga_bonus, _h5_lord_bonus, _amk_house_bonus,
    _ak_house_bonus, _planet_combustion_penalty, _dusthana_lord_penalty,
    _peak_career_dasha, _peak_career_dasha_boost, _dasha_active_affinity_boost,
    _d10_consistency_penalty, _pratyantar_dasha_bonus, _karakamsha_occupant_bonus,
    _bhavesha_phala_edu_bonus, _d9_h10_bonus, _dharma_karma_bonus,
    _d10_h10_bonus, _gender_field_modifier, _aspect_h10_bonus,
    _maheshwara_lord_bonus, _interest_preference_boost, _brahma_lord_bonus,
    _chart_specific_aptitude_supplement, _ak_planet_domain_boost,
    _karakamsha_domain_boost, _h3_lord_communication_boost,
    _h12_stellium_penalty, _build_critical_warnings,
    _apply_domain_deduplication, _d10_lagna_lord_bonus, _stellium_bonus,
    _classify_parivartana,
    _h10_lord_trikona_bonus,
    _YOGAKARAKA_PLANET,
    _modernize_karakas_modifier,
    _exalted_planet_domain_bonus,
)
from .llm import call_llm_for_fields, _build_chart_summary_for_llm

import math as _math

_COMPOSITE_SOFT_CAP = 200.0
_AFFINITY_SOFT_CAP  = 180.0

from .constants import _PLANET_MIN_SHADBALA, _VALID_DOMAINS
from .astro import _paksha_bala
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

# Gap 3: Physical engineering / material-mastery fields eligible for the Saturn-AK
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


def execute_qa_verification_v8_9(field, chart_data, domain, war_result=None):
    """QA gate applying structural friction multipliers to raw field scores.

    Merged from v9.0 severity-scale approach + FIX-11/FIX-12 astrological corrections:
    A. Full combustion hierarchy — all planets checked with classical severity weights.
    B. Planetary War (Graha Yuddha) — defeated planets generate massive friction and can be fatal.
    C. Domain-scoped checks — dynamically extracted from BRANCH_PLANET_AFFINITY per field.
    D. Budha-Aditya Yoga    — Mercury combust + yoga → immune (classical exception).
    E. Shadbala modulation  — ratio ≥ 1.50× → immune; ≥ 1.30× → friction halved.
    F. D24 offset           — Mars own/exalted in D24 offsets engineering friction.
    G. Mercury never fatal  — classical immunity; other high-severity planets can be fatal.
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
    _SEVERITY: Dict[str, float] = {
        "Ketu": 1.00, "Rahu": 0.90, "Saturn": 0.75, "Mars": 0.60,
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
                sev = _SEVERITY.get(planet, 0.50)
                raw_f = int(50 * sev * weight_mod)
                if dig in ("EXALTED", "OWN"): raw_f = int(raw_f * 0.50)
                if ak == planet:              raw_f = int(raw_f * 0.80)
                if ratio >= 1.30:             raw_f = max(5, raw_f // 2)
                planet_friction += raw_f
                notes_list.append(
                    f"{planet} combust in {domain}: +{raw_f} friction "
                    f"(severity {sev:.2f}, dig={dig or 'neutral'}, shadbala={ratio:.2f}×).")

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
            # Fatal condition 3: Critical structural planet in structural domain afflicted
            elif planet in ("Saturn", "Ketu") and domain in _ENG_SCI and (is_war_loser or is_combust):
                is_fatal = True
                reason = "defeated in war" if is_war_loser else "combust"
                notes_list.append(f"FATAL: {planet} {reason} in {domain} — "
                                   "structural/technical architecture severely disrupted.")

    # Cap friction
    friction = min(friction, 100)

    # ── E: D24 Mars offset for engineering ────────────────────────────────────
    if domain in ("engineering", "science") and friction > 0 and not is_fatal:
        if d24_digs.get("Mars", "") in ("OWN", "EXALTED"):
            offset = min(friction, 15)
            friction = max(0, friction - offset)
            notes_list.append(f"D24 Mars {d24_digs['Mars']} (Siddhamsha): engineering "
                               f"signature offsets {offset} pts → residual {friction}.")

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
    """FIX-10 + FIX-11: combustion mismatch respects Budha-Aditya yoga and Shadbala.

    Uses LLM-provided branch_affinity_weights to derive the top-2 aptitude planets
    for this specific field (replaces hardcoded DOMAIN_APTITUDE_PLANETS).
    """
    if planet_dignities is None: planet_dignities = {}
    if combust_planets  is None: combust_planets  = []
    if detected_yogas   is None: detected_yogas   = []
    if shadbala         is None: shadbala          = {}
    if nb_set           is None: nb_set            = set()
    yoga_set = set(detected_yogas)

    # Arts mismatch: suppress penalty when the soul (AK) or career direction (AmK)
    # genuinely aligns with arts. Conditions:
    #   1. AK=Venus + Venus exalted/own
    #   2. AK=Venus + Venus in NB (debilitated but cancelled — arts soul restored)
    #   3. AK=Moon  + Moon exalted/own (Moon = creativity, aesthetics, emotional arts)
    #   4. AmK=Venus + Venus exalted/own (career directed toward arts even if AK ≠ Venus)
    _ak_is_arts_soul = (
        (ak == "Venus" and planet_dignities.get("Venus", "") not in ("DEBILITATED",))
        or (ak == "Venus" and "Venus" in nb_set)
        or (ak == "Moon"  and planet_dignities.get("Moon",  "") in ("EXALTED", "OWN"))
        or (amk == "Venus" and planet_dignities.get("Venus", "") in ("EXALTED", "OWN"))
    )
    if (domain == "arts"
            and not _ak_is_arts_soul
            and aptitudes.get("secondary_aptitude", 0) > 40):
        return {"mismatch_risk": True,
                "notes": "High Mismatch Risk: Systems-thinking exceeds arts domain norms."}
    # Extra guard: even for arts-soul charts, flag if secondary strongly DOMINATES primary.
    if (domain == "arts"
            and aptitudes.get("secondary_aptitude", 0) > aptitudes.get("primary_aptitude", 0)
            and aptitudes.get("secondary_aptitude", 0) > 55):
        return {"mismatch_risk": True,
                "notes": "High Mismatch Risk: Secondary analytical planet strongly dominates primary arts karaka."}

    # Derive top-2 planets from LLM affinity (replaces DOMAIN_APTITUDE_PLANETS)
    if branch_affinity_weights:
        top_sorted = sorted(branch_affinity_weights.items(), key=lambda x: -x[1])
        pair = tuple(p for p, _ in top_sorted[:2])
    else:
        pair = ()

    for pp in pair:
        if planet_dignities.get(pp) == "DEBILITATED" and pp not in nb_set:
            # NB planets retain functional dignity — skip the DEBILITATED mismatch flag
            return {"mismatch_risk": True,
                    "notes": f"Domain risk: {pp} debilitated — primary {domain} planet compromised."}
        if pp in combust_planets:
            if pp == "Mercury" and "BudhaAditya" in yoga_set:
                continue   # FIX-11B: yoga grants classical immunity
            ratio = shadbala.get(pp, 0.0) / _PLANET_MIN_SHADBALA.get(pp, 300.0)
            if ratio >= 1.50:
                continue   # FIX-11C: overwhelming strength overrides combustion flag
            return {"mismatch_risk": True,
                    "notes": f"Domain caution: {pp} combust — primary {domain} planet expression reduced."}
    return {"mismatch_risk": False, "notes": "Alignment nominal."}

# ===========================================================================
# MODULE E: ORCHESTRATION KERNEL
# ===========================================================================
AFFINITY_BLEND, DOMAIN_BLEND = 0.40, 0.60

# ===========================================================================
# DESIGN-5: AGE-STAGE STREAM CLASSIFIER
# Outputs stream/path guidance for 10th/12th students alongside full rankings

def classify_age_stage(current_age: float, top_results: List[Dict]) -> Dict:
    """DESIGN-5: Return stream and path recommendations based on student age.

    Age 14–17 (class 9/10): recommend stream choice for 11th.
    Age 17–19 (class 11/12): recommend degree path alongside rankings.
    """
    stage = None
    if 14 <= current_age < 17:
        stage = "class_9_10"
    elif 17 <= current_age < 20:
        stage = "class_11_12"
    else:
        return {"stage": "adult", "guidance": "Full career rankings apply directly."}

    # Tally stream votes from top-10 results
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

def run_engine(payload_data: NatalPayloadV2) -> List[Dict]:
    results    = []
    shadbala   = getattr(payload_data, "shadbala", {})
    sav        = getattr(payload_data, "sav_points_houses", {})
    digs       = getattr(payload_data, "planet_dignities", {})
    combust    = getattr(payload_data, "combust_planets", [])
    ak         = getattr(payload_data, "atmakaraka", "")
    amk        = getattr(payload_data, "amatyakaraka", "")
    kp_sigs    = getattr(payload_data, "kp_significators", {})
    kp_cusps   = getattr(payload_data, "kp_cusps", {})
    ph         = getattr(payload_data, "planet_house", {})
    house_lords= getattr(payload_data, "house_lords", {})
    h10_lord   = house_lords.get("10", "")  # FIX-23: for chart-specific aptitude supplement
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
    planets_d1 = getattr(payload_data, "planets_d1", {})
    div_charts = getattr(payload_data, "divisional_charts", {})
    d9_chart   = div_charts.get("D9_navamsha", {})
    d10_chart  = div_charts.get("D10_dashamsha", {})                   # FIX-3
    d10_lagna  = d10_chart.get("Lagna", "")                            # FIX-3
    d10_digs   = {p: compute_dignity(p, s) for p, s in d10_chart.items() if p != "Lagna"}  # FIX-3
    nakshatras = getattr(payload_data, "nakshatra_data", {})
    nb_set     = set(getattr(payload_data, "neecha_bhanga_planets", []))
    d9_lagna   = getattr(payload_data, "d9_lagna_sign", "")
    kara_occ   = getattr(payload_data, "karakamsha_occupants", [])
    prd_lord   = getattr(payload_data, "pratyantar_dasha_lord", "")
    prd_houses = getattr(payload_data, "prd_lord_houses", [])
    sun_moon_d = getattr(payload_data, "sun_moon_degrees_apart", 0.0)
    interested_in = getattr(payload_data, "interested_in", [])
    already_excel = getattr(payload_data, "already_excel_at", [])
    brahma_lord      = getattr(payload_data, "brahma_lord", "")
    maheshwara_lord  = getattr(payload_data, "maheshwara_lord", "")   # FIX-6
    gender_val       = getattr(payload_data, "gender", "")             # FIX-4
    cazimi_set       = set(getattr(payload_data, "cazimi_planets", []))

    war_result   = _detect_planetary_war(planets_d1)
    vargottama   = [p for p in _ALL_PLANETS if _is_vargottama(p, planets_d1.get(p,{}).get("sign",""), d9_chart)]
    active_lord  = _get_active_dasha_lord(getattr(payload_data,"dasha_sequence",[]), float(getattr(payload_data,"current_age",0)))
    pb_val = _paksha_bala(sun_moon_d)

    # FIX-6b: compute eff_strengths FIRST so peak dasha can use it
    # Trace is a free byproduct of the same loop — no second pass needed.
    eff_strengths, planet_trace = _compute_eff_strengths(
        shadbala, digs, retro, war_result, vargottama, nakshatras, nb_set, pb_val,
        house_lords, lagna_lord, ph, cazimi_set, planets_d1,
        set(combust),           # DESIGN-1 fix: combust reduces eff strength
        set(yogas)               # FIX-11a: BudhaAditya yoga exempts Mercury combustion
    )

    peak_lord, peak_scores = _peak_career_dasha(
        getattr(payload_data, "dasha_sequence", []), shadbala, digs, house_lords, ak, amk,
        current_age=float(getattr(payload_data, "current_age", 0)),
        eff_strengths=eff_strengths, planet_house=ph)  # FIX-6: pass effective strengths
    if peak_lord:
        logger.info(f"Peak career MD: {peak_lord}  (scores: { {k: round(v,3) for k,v in sorted(peak_scores.items(), key=lambda x:-x[1])[:5]} })")
    

    # ── Phase 1b: Educational planet set — REMOVED ───────────────────────────
    # _get_educational_planet_set / _compute_edu_strengths drove the OLD keyword-based
    # field selection pipeline. Field selection is now done by the LLM.
    # eff_strengths (all 9 planets, dignity×war×vargottama×nakshatra×digbala etc.)
    # is passed directly to compute_branch_affinity_score_llm() instead of the
    # narrower Kendradi-adjusted edu_eff. Stub values keep ExplainabilityEngine happy.
    #
    # edu_planet_reasons_base = _get_educational_planet_set(...)  # REMOVED
    # edu_eff_strengths, edu_ranked = _compute_edu_strengths(...)  # REMOVED
    edu_planet_reasons = {}      # empty — ExplainabilityEngine still references this key
    edu_eff_strengths  = {}      # empty — ditto
    edu_ranked         = []      # empty — ditto

    # top_3 from eff_strengths (replaces old edu_ranked top-3 for any remaining gap helpers)
    sorted_planets = sorted(eff_strengths.items(), key=lambda x: -x[1])
    top_3_planets  = [p for p, _ in sorted_planets[:3]]

    logger.info(f"Top planets by effective strength (replaces edu_ranked): "
                f"{ [(p, round(v,3)) for p,v in sorted_planets[:5]] }")

    # ── Pipeline Inversion (Task#3): score ALL 188 fields first, LLM selects top-20 ─────────────
    # Phase 1: Python pre-scores all 188 deterministically with BRANCH_PLANET_AFFINITY.
    # Phase 2: LLM receives pre-ranked top-35 and selects final 20 + writes rationale.
    # Phase 3: Merge LLM reasons into pre-computed results.
    _DEFAULT_AFFINITY: Dict[str, float] = {"Mercury":0.30,"Jupiter":0.25,"Saturn":0.25,"Sun":0.20}
    _all_pre_results: List[Dict] = []

    for _fid, _fmeta in _COURSE_REGISTRY.items():
        branch_name = _fid
        label       = _fmeta.get("label", _fid.replace("_"," ").title())
        domain      = _fmeta.get("domain", "interdisciplinary").strip().lower()
        if domain not in _VALID_DOMAINS:
            domain = "interdisciplinary"

        # Task#1: hardcoded multi-karaka affinity (no LLM hallucination)
        hard_affinity = BRANCH_PLANET_AFFINITY.get(_fid, _DEFAULT_AFFINITY)
        llm_affinity  = hard_affinity   # alias preserved for gap helpers below
        llm_astro_reason  = ""          # filled from LLM selection in Phase 2
        llm_sel_rationale = ""          # filled from LLM selection in Phase 2

        # AK soul-direction immunity: when AK planet is the TOP-WEIGHT karaka for this field,
        # apply eff_strength floor of 1.0 for scoring. Astrological rationale: the AK defines
        # the soul's karmic direction regardless of dignity — enemy/debilitated sign reduces
        # HOW EASILY the native pursues that path, not WHICH PATH the soul is directed toward.
        _eff_for_scoring = eff_strengths  # default: use shared eff_strengths directly
        if ak and hard_affinity:
            _ak_top_k = max(hard_affinity.items(), key=lambda x: x[1])[0]
            if _ak_top_k == ak and eff_strengths.get(ak, 1.0) < 1.0:
                _eff_for_scoring = dict(eff_strengths)
                _eff_for_scoring[ak] = 1.0  # soul-direction floor

        affinity_result = compute_branch_affinity_score_llm(
            branch_name, label, domain, hard_affinity, _eff_for_scoring)
        aff = affinity_result["affinity_planets"]

        # Task#2: pass field_id so BRANCH_PLANET_AFFINITY used for aptitude karakas
        aptitudes = compute_aptitude_by_domain(domain, shadbala, sav, _eff_for_scoring,
                                               hard_affinity, field_id=_fid)
        # FIX-23: chart-specific lord supplement corrects global domain hardcoding
        _apt_supplement = _chart_specific_aptitude_supplement(
            domain, h5_lord, lagna_lord, h10_lord, eff_strengths)
        aptitudes["composite_score"] = min(aptitudes["composite_score"] + _apt_supplement, 200)
        if aptitudes["composite_score"] >= aptitudes["threshold_required"]:
            aptitudes["meets_threshold"] = True

        # FIX-7: Normalize to 0-100 before blend; bias_multiplier removed (double-counted affinity)
        composite_norm = _log_norm_score(aptitudes["composite_score"], _COMPOSITE_SOFT_CAP)
        affinity_norm  = _log_norm_score(affinity_result["affinity_score"], _AFFINITY_SOFT_CAP)
        blended = DOMAIN_BLEND * composite_norm + AFFINITY_BLEND * affinity_norm

        gap_boost, gap_detail = 0.0, {}
        _PCC = 0.12  # Task#5: per-category cap — no single boost source exceeds +0.12

        # Gap 1 — Affinity Anchor: resolve PRIMARY karaka ONCE; reused by multiple boosts.
        # Full soul-level bonuses (AK, AmK) only fire when that planet is the TOP-weight
        # karaka of THIS field. Secondary/tertiary presence yields a reduced ambient signal.
        _top_karaka = max(hard_affinity.items(), key=lambda x: x[1])[0] if hard_affinity else ""

        # Accumulate gap boosts (each positive boost capped at _PCC before accumulation)
        # AK bonus — full +0.12 only when AK is the primary karaka; +0.03 ambient otherwise.
        if ak and hard_affinity:
            if _top_karaka == ak:
                _ak_b = 0.12
            elif aff.get(ak, 0) >= 0.15:
                _ak_b = 0.03   # secondary/tertiary presence — ambient background reflection
            else:
                _ak_b = 0.0
        else:
            _ak_b = 0.0
        # AmK bonus — full +0.08 only when AmK is the primary karaka; +0.02 ambient otherwise.
        if amk and hard_affinity:
            if _top_karaka == amk:
                _amk_b = 0.08
            elif aff.get(amk, 0) >= 0.10:
                _amk_b = 0.02
            else:
                _amk_b = 0.0
        else:
            _amk_b = 0.0
        b = min(_ak_b + _amk_b, _PCC)
        gap_boost += b; gap_detail["ak_amk"] = round(b, 3)
        b = min(_kp_h10_branch_strength(aff, kp_sigs) * 0.10, _PCC); gap_boost += b; gap_detail["kp_h10_sig"] = round(b,3)
        b = min(_stellium_bonus(label, ph), _PCC); gap_boost += b; gap_detail["stellium"] = round(b,3)
        b = min(_h10_sublord_bonus(aff, kp_cusps), _PCC); gap_boost += b; gap_detail["h10_sublord"] = round(b,3)
        b = min(_dasha_bonus(label, payload_data), _PCC); gap_boost += b; gap_detail["dasha"] = round(b,3)
        b = min(_karakamsha_bonus(aff, karakamsha), _PCC); gap_boost += b; gap_detail["karakamsha"] = round(b,3)
        b = min(_d24_ak_delta(label, payload_data), _PCC); gap_boost += b; gap_detail["d24_ak"] = round(b,3)
        b = min(_lagna_lord_bonus(label, payload_data), _PCC); gap_boost += b; gap_detail["lagna_lord"] = round(b,3)
        b = min(_risk_appetite_bonus(label, risk), _PCC); gap_boost += b; gap_detail["risk_appetite"] = round(b,3)
        # modernize_karakas: bidirectional — can be negative (penalty) or positive (cyber boost).
        # NOT wrapped in min(_PCC) so negative values pass through unchanged.
        b = _modernize_karakas_modifier(_fid, risk, amk, _kp_h10_star_lord, planets_d1)
        gap_boost += b; gap_detail["modernize_karakas"] = round(b, 3)
        b = min(_yogakaraka_bonus(aff, lagna_sign, shadbala, digs), _PCC); gap_boost += b; gap_detail["yogakaraka"] = round(b,3)
        b = min(_h10_lord_strength_bonus(aff, h10_lp, shadbala, digs), _PCC); gap_boost += b; gap_detail["h10_lord_str"] = round(b,3)
        b = min(_h10_lord_trikona_bonus(aff, h10_lp, ph, digs), _PCC); gap_boost += b; gap_detail["h10_lord_trikona"] = round(b,3)
        b = min(_exalted_planet_domain_bonus(aff, digs, label), _PCC); gap_boost += b; gap_detail["exalted_domain"] = round(b,3)
        b = min(_ul_lord_bonus(aff, ul), _PCC); gap_boost += b; gap_detail["ul_lord"] = round(b,3)
        b = min(_kp_edu_starlord_bonus(aff, kp_cusps), _PCC); gap_boost += b; gap_detail["kp_edu_star"] = round(b,3)
        b = min(_d9_ak_delta(label, payload_data), _PCC); gap_boost += b; gap_detail["d9_ak"] = round(b,3)
        b = min(_yoga_bonus(label, yogas, house_lords), _PCC); gap_boost += b; gap_detail["yoga"] = round(b,3)
        b = min(_h5_lord_bonus(aff, h5_lord), _PCC); gap_boost += b; gap_detail["h5_lord"] = round(b,3)
        b = min(_amk_house_bonus(label, amk_house), _PCC); gap_boost += b; gap_detail["amk_house"] = round(b,3)
        b = min(_ak_house_bonus(ak, ph.get(ak,0), label), _PCC); gap_boost += b; gap_detail["ak_house"] = round(b,3)

        # Gap 4 — Soul-stack family cap: ak_amk + yogakaraka + ak_house all originate
        # from the same planetary placement. Cap their combined total at 0.26 to prevent
        # a single planet (e.g. Saturn as AK + Yogakaraka + H11 lord) from creating an
        # echo-chamber that inflates every field containing even a trace of that planet.
        _soul_stack = gap_detail.get("ak_amk", 0) + gap_detail.get("yogakaraka", 0) + gap_detail.get("ak_house", 0)
        if _soul_stack > 0.26:
            _ss_excess = _soul_stack - 0.26
            gap_boost -= _ss_excess
            gap_detail["yogakaraka"] = round(gap_detail.get("yogakaraka", 0) - _ss_excess, 3)
            gap_detail["_soul_stack_cap"] = round(-_ss_excess, 3)

        b = min(_dasha_active_affinity_boost(aff, active_lord, digs), _PCC); gap_boost += b; gap_detail["dasha_affinity_boost"] = round(b,3)
        b = min(_peak_career_dasha_boost(aff, peak_lord, active_lord, digs), _PCC); gap_boost += b; gap_detail["peak_md_boost"] = round(b,3)
        # Triple-stacking guard: dasha + dasha_affinity + peak_md <= 0.22
        _dasha_total = gap_detail.get("dasha",0) + gap_detail.get("dasha_affinity_boost",0) + gap_detail.get("peak_md_boost",0)
        if _dasha_total > 0.22:
            _excess = _dasha_total - 0.22
            gap_boost -= _excess
            gap_detail["peak_md_boost"] = round(gap_detail.get("peak_md_boost",0) - _excess, 3)
        b = min(_pratyantar_dasha_bonus(label, prd_lord, prd_houses), _PCC); gap_boost += b; gap_detail["prd_boost"] = round(b,3)
        b = min(_karakamsha_occupant_bonus(label, kara_occ, shadbala), _PCC); gap_boost += b; gap_detail["karakamsha_occ"] = round(b,3)
        b = min(_d9_h10_bonus(aff, d9_chart, d9_lagna), _PCC); gap_boost += b; gap_detail["d9_h10"] = round(b,3)
        b = min(_dharma_karma_bonus(aff, house_lords, ph), _PCC); gap_boost += b; gap_detail["dharma_karma"] = round(b,3)
        b = min(_interest_preference_boost(label, interested_in, already_excel), _PCC); gap_boost += b; gap_detail["interest_pref"] = round(b,3)
        b = min(_brahma_lord_bonus(label, brahma_lord, aff), _PCC); gap_boost += b; gap_detail["brahma_lord"] = round(b,3)
        # FIX-3: D10 H10 bonus
        b = min(_d10_h10_bonus(aff, d10_chart, d10_lagna, d10_digs), _PCC); gap_boost += b; gap_detail["d10_h10"] = round(b, 3)

        # FIX: D10 Lagna Lord bonus
        b = min(_d10_lagna_lord_bonus(aff, d10_chart, d10_lagna, d10_digs), _PCC); gap_boost += b; gap_detail["d10_lagna_lord"] = round(b, 3)
        # FIX-4: Gender field modifier (can be negative — not capped)
        b = _gender_field_modifier(label, gender_val, aff, house_lords); gap_boost += b; gap_detail["gender_field"] = round(b, 3)
        # FIX-5: Aspect on H10 bonus
        b = min(_aspect_h10_bonus(aff, ph, digs,
                                      planets_d1=getattr(payload_data,"planets_d1",None)), _PCC)
        gap_boost += b; gap_detail["aspect_h10"] = round(b, 3)
        # FIX-6: Maheshwara lord bonus
        b = min(_maheshwara_lord_bonus(label, maheshwara_lord, aff), _PCC); gap_boost += b; gap_detail["maheshwara"] = round(b, 3)
        # NEW: Bhavesha Phala bonus
        b = min(_bhavesha_phala_edu_bonus(label, aff, house_lords, ph), _PCC); gap_boost += b; gap_detail["bhavesha_phala"] = round(b, 3)
        # v9.4/v9.5 gap fixes
        b = min(_ak_planet_domain_boost(label, ak, digs.get(ak,''), ph), _PCC); gap_boost += b; gap_detail["ak_planet_domain"] = round(b, 3)
        b = min(_karakamsha_domain_boost(label, domain, karakamsha), _PCC); gap_boost += b; gap_detail["karakamsha_domain"] = round(b, 3)
        b = min(_h3_lord_communication_boost(label, domain, house_lords, eff_strengths, ph), _PCC); gap_boost += b; gap_detail["h3_comm"] = round(b, 3)
        b = _h12_stellium_penalty(label, domain, ph); gap_boost += b; gap_detail["h12_stellium_pen"] = round(b, 3)  # can be negative

        # AK primary-karaka structural bonus — NOT subject to _PCC cap (soul-direction signal,
        # not a minor house modifier). Applied after all _PCC-capped boosts.
        # Fires when BRANCH_PLANET_AFFINITY top-weight karaka for this field == AK planet.
        if ak and hard_affinity:
            _ak_top_k = max(hard_affinity.items(), key=lambda x: x[1])[0]
            if _ak_top_k == ak:
                _b_akp = 0.10
                gap_boost += _b_akp
                gap_detail["ak_primary_karaka"] = round(_b_akp, 3)

        # Base-score resurrection guard: a field with genuinely weak planetary support
        # (blended < 45) should not be able to reach top-35 purely by accumulating minor boosts.
        if blended < 45.0:
            gap_boost = min(gap_boost, 0.30)

        gap_boost = max(-0.20, min(gap_boost, 0.65))

        # Gap 3 — Material Grit boost (UNCAPPED — bypasses 0.65 ceiling deliberately).
        # Fires when Saturn is AK (or Yogakaraka for Libra/Cancer lagnas) AND the field
        # demands physical mastery of matter, structure, or industrial transformation.
        # The top karaka of the field must be Saturn OR Mars (physical, not digital).
        # This corrects the engine's Mercury-bias that buries hands-on engineering under
        # data-science fields when Mercury+Saturn are both strong.
        # GUARD: does NOT fire when the AK is an arts/intellectual planet (Venus/Moon/Jupiter/
        # Mercury/Ketu) — the soul's direction overrides the YK's structural preference.
        _yk_planet = _YOGAKARAKA_PLANET.get(lagna_sign, "")
        _ak_is_arts_soul = ak in ("Venus", "Moon", "Jupiter", "Mercury", "Ketu")
        if (_fid in _MATERIAL_GRIT_FIELDS
                and not _ak_is_arts_soul
                and (ak == "Saturn" or _yk_planet == "Saturn")
                and _top_karaka in ("Saturn", "Mars")):
            _b_mat = 0.15
            gap_boost += _b_mat
            gap_detail["material_grit"] = round(_b_mat, 3)

        # Venus Arts Force (UNCAPPED — mirrors material_grit for Venus-AK arts charts).
        # Fires when Venus is AK AND the field is arts AND top karaka is Venus.
        # Strength scales by Venus condition:
        #   retrograde + exalted → 0.35 (intensified inward soul-direction — classic retrograde paradox)
        #   exalted / own        → 0.12 (normal dignified force)
        #   NB Venus (debil cancelled) → 0.20 (partial arts force restored by cancellation)
        #   neutral Venus AK     → 0.07 (soul direction present even without special dignity)
        if (domain == "arts"
                and ak == "Venus"
                and _top_karaka == "Venus"):
            _ven_dig   = digs.get("Venus", "")
            _ven_retro = retro.get("Venus", False)
            if _ven_dig in ("EXALTED", "OWN") and _ven_retro:
                _b_vaf = 0.35   # retrograde exalted: maximally intensified arts soul
            elif _ven_dig in ("EXALTED", "OWN"):
                _b_vaf = 0.12
            elif "Venus" in nb_set:
                _b_vaf = 0.20   # NB Venus: arts soul substantially restored by cancellation
            elif _ven_dig not in ("DEBILITATED",):
                _b_vaf = 0.07   # neutral Venus AK: modest but real arts soul signal
            else:
                _b_vaf = 0.0
            if _b_vaf > 0:
                gap_boost += _b_vaf
                gap_detail["venus_arts_force"] = round(_b_vaf, 3)

        # ── Soul/Career direction force boosts (UNCAPPED — parallel to material_grit) ──────

        # Venus AmK arts force: career direction through Venus AmK → arts even when AK ≠ Venus.
        if (domain == "arts"
                and amk == "Venus"
                and digs.get("Venus", "") in ("EXALTED", "OWN")):
            _b_vaf_amk = 0.08
            gap_boost += _b_vaf_amk
            gap_detail["venus_arts_force_amk"] = round(_b_vaf_amk, 3)

        # Moon AK arts/humanities force: Moon soul seeks expression through creative/social fields.
        # Classical: Moon = creativity, emotional intelligence, public connection, aesthetics.
        if (domain in ("arts", "humanities")
                and ak == "Moon"
                and digs.get("Moon", "") in ("EXALTED", "OWN")):
            _b_maf = 0.32 if domain == "arts" else 0.09
            gap_boost += _b_maf
            gap_detail["moon_arts_force"] = round(_b_maf, 3)

        # Moon AK medicine force: Moon AK + dignified Moon → care-oriented soul; nursing/medicine.
        if (domain == "medicine"
                and ak == "Moon"
                and digs.get("Moon", "") in ("EXALTED", "OWN")):
            _b_mmf = 0.20
            gap_boost += _b_mmf
            gap_detail["moon_medicine_force"] = round(_b_mmf, 3)

        # Moon+Jupiter medicine force: Moon AK + Jupiter AmK, both dignified → medical vocation.
        # Jupiter rules healers/physicians; when paired with Moon AK, medicine field is strongly
        # favoured. Extra push so medicine stays above arts (which also gets Moon AK arts boost).
        if (domain == "medicine"
                and ak == "Moon"
                and amk == "Jupiter"
                and digs.get("Moon", "") in ("EXALTED", "OWN")
                and digs.get("Jupiter", "") in ("EXALTED", "OWN")):
            _b_mjmf = 0.12
            gap_boost += _b_mjmf
            gap_detail["moon_jupiter_medicine_force"] = round(_b_mjmf, 3)

        # Jupiter AK medicine force: Jupiter AK + exalted/own → healer-philosopher soul.
        # Classical: Jupiter (Guru) as AK in own dignity = native's soul directed toward wisdom,
        # healing, and dharmic service — strongly signals medicine/healthcare vocation.
        if (domain == "medicine"
                and ak == "Jupiter"
                and digs.get("Jupiter", "") in ("EXALTED", "OWN")):
            _b_jmf = 0.20
            gap_boost += _b_jmf
            gap_detail["jupiter_ak_medicine_force"] = round(_b_jmf, 3)

        # Pisces benefic force: Jupiter + Venus both in Pisces → law/arts/medicine orientation.
        # Classical: Pisces (Jupiter's own sign) hosts both the largest natural benefic (Jupiter)
        # and the planet of beauty/harmony (Venus) → dharmic creativity and healing, NOT commerce.
        _pisces_benefic = (
            planets_d1.get("Jupiter", {}).get("sign") == "Pisces"
            and planets_d1.get("Venus", {}).get("sign") == "Pisces"
        )
        if _pisces_benefic and domain in ("law", "arts", "medicine"):
            _b_pbf = 0.12
            gap_boost += _b_pbf
            gap_detail["pisces_benefic_force"] = round(_b_pbf, 3)

        # Interdisciplinary mixed-karaka force: Jupiter AK + Mercury AmK (or vice versa).
        # Classical: Jupiter×Mercury pairing = scholar-scientist archetype, bridging philosophy
        # with data/analytics. Signals career paths that span domains (interdisciplinary).
        _jup_mer_pair = (
            (ak == "Jupiter" and amk == "Mercury") or (ak == "Mercury" and amk == "Jupiter")
        )
        if domain == "interdisciplinary" and _jup_mer_pair:
            _b_imf = 0.15
            gap_boost += _b_imf
            gap_detail["interdisciplinary_mixed_karaka"] = round(_b_imf, 3)

        # Ketu AK research/science force: Ketu soul seeks transcendence through deep enquiry.
        # Classical: Ketu = liberation through knowledge, past-life research aptitude, detachment.
        if (domain in ("science", "interdisciplinary")
                and ak == "Ketu"):
            _b_krf = 0.10
            gap_boost += _b_krf
            gap_detail["ketu_research_force"] = round(_b_krf, 3)

        # Mercury AK tech force: Mercury AK soul seeks mastery through intellect and computation.
        # Classical: Mercury = Buddhi, analytics, data, computation, language of machines.
        # Strength scales by Mercury's dignity:
        #   EXALTED/OWN → 0.30 (peak Mercurial expression)
        #   NB Mercury   → 0.15 (debilitation cancelled — tech soul restored at reduced power)
        #   DEBILITATED  → 0.05 (soul direction intact but expression impaired; minimal signal)
        #   neutral      → 0.15 (Mercury in non-special sign — moderate soul-direction signal)
        if domain == "technology" and ak == "Mercury":
            _mer_dig = digs.get("Mercury", "")
            if _mer_dig in ("EXALTED", "OWN"):
                _b_mtf = 0.30
            elif "BudhaAditya" in set(yogas) and _mer_dig != "DEBILITATED":
                _b_mtf = 0.30   # BudhaAditya yoga elevates Mercury to exalted-level tech force
            elif "Mercury" in nb_set:
                _b_mtf = 0.15   # NB cancels debilitation — tech soul partially restored
            elif _mer_dig == "DEBILITATED":
                # Check if Mercury's sign dispositor is exalted (NB-like restoration)
                _mer_sign = planets_d1.get("Mercury", {}).get("sign", "")
                _mer_disp = {"Pisces": "Jupiter", "Virgo": "Mercury"}.get(_mer_sign, "")
                if _mer_disp and digs.get(_mer_disp, "") == "EXALTED":
                    _b_mtf = 0.12  # exalted dispositor = significant NB-like restoration
                else:
                    _b_mtf = 0.05  # impaired but soul direction present
            else:
                _b_mtf = 0.15   # neutral sign: moderate tech soul force
            gap_boost += _b_mtf
            gap_detail["mercury_tech_force"] = round(_b_mtf, 3)

        # Sun AK leadership force: Sun AK + EXALTED/OWN → governance, law, public policy.
        # Guard: skip when Jupiter is AmK (Jupiter as career lord already dominates law heavily;
        # stacking Sun leadership causes law to sweep all 5 slots, breaking domain diversity).
        if (domain in ("law", "interdisciplinary", "science")
                and ak == "Sun"
                and digs.get("Sun", "") in ("EXALTED", "OWN")
                and amk != "Jupiter"):
            _b_slf = 0.20
            gap_boost += _b_slf
            gap_detail["sun_leadership_force"] = round(_b_slf, 3)

        # Mars AK engineering force: Mars AK + EXALTED/OWN → engineering mastery.
        # Parallel to material_grit but fires for Mars AK (not Saturn AK).
        # Key for Cancer/Leo lagnas where Mars is YK AND AK simultaneously.
        # Guard: skip when Mars is combust (combustion already penalised in eff_strengths).
        if (domain == "engineering"
                and ak == "Mars"
                and digs.get("Mars", "") in ("EXALTED", "OWN")
                and "Mars" not in (set(combust) | cazimi_set)
                and _top_karaka in ("Mars", "Saturn")):
            _b_mef = 0.12
            gap_boost += _b_mef
            gap_detail["mars_engineering_force"] = round(_b_mef, 3)

        # Mars AMK engineering force: career direction through Mars AMK + EXALTED/OWN → engineering.
        # Fires when Mars is AmK (not AK) — covers NB/debilitated AK scenarios where AmK dominates.
        if (_fid in _MATERIAL_GRIT_FIELDS
                and amk == "Mars"
                and digs.get("Mars", "") in ("EXALTED", "OWN")
                and _top_karaka in ("Mars", "Saturn")):
            _b_mef_amk = 0.10
            gap_boost += _b_mef_amk
            gap_detail["mars_amk_engineering_force"] = round(_b_mef_amk, 3)

        # NB Mars YK engineering force: Mars is Yogakaraka but debilitated with Neecha Bhanga.
        # NB restores partial engineering potential (Mars YK soul direction intact despite debilitation).
        # Fires only when Mars is in nb_set (NB confirmed) + Mars is YK for lagna + engineering field.
        if (_fid in _MATERIAL_GRIT_FIELDS
                and "Mars" in nb_set
                and _yk_planet == "Mars"):
            _b_nb_mars = 0.07
            gap_boost += _b_nb_mars
            gap_detail["nb_mars_yk_engineering_force"] = round(_b_nb_mars, 3)

        # Lagna lord H10 domain force: lagna lord exalted/own in H10 + AK = lagna lord + field
        # top-karaka = lagna lord → strong Rajayoga delivering domain-specific results.
        # Classical: lagna lord in H10 in uccha (exaltation) = Rajayoga — career eminence in
        # the field ruled by that planet. When AK also = lagna lord, soul aligns with career.
        _ll_house = ph.get(lagna_lord, 0)
        if (_ll_house == 10
                and lagna_lord == ak
                and digs.get(lagna_lord, "") in ("EXALTED", "OWN")
                and _top_karaka == lagna_lord):
            _b_llh10 = 0.15
            gap_boost += _b_llh10
            gap_detail["lagna_lord_h10_domain_force"] = round(_b_llh10, 3)

        # Accumulate penalties
        gap_penalty = 0.0
        # FIX-1: _planet_combustion_penalty removed — combustion is already in eff_strengths.
        p_ak_comb = min(_ak_combustion_penalty(aff, ak, combust, digs), 0.15); gap_penalty += p_ak_comb; gap_detail["ak_combustion_penalty"] = round(-p_ak_comb, 3)
        p_dust = _dusthana_lord_penalty(aff, lagna_sign, house_lords, lagna_lord, label); gap_penalty += p_dust; gap_detail["dusthana_penalty"] = round(-p_dust, 3)
        p_d10 = _d10_consistency_penalty(aff, getattr(payload_data,"d10_house_occupancy",{})); gap_penalty += p_d10; gap_detail["d10_dusthana_penalty"] = round(-p_d10, 3)

        score = blended * (1.0 + gap_boost) * (1.0 - gap_penalty)  # FIX-7: bias_multiplier removed

        audit    = execute_qa_verification_v8_9(branch_name, payload_data, domain, war_result)  # FIX-2 + FIX-12 (Graha Yuddha in QA)
        conflict = assess_domain_mismatch(                                           # FIX-10+11
            aptitudes, domain, digs, combust,
            detected_yogas=getattr(payload_data, 'detected_yogas', []),
            shadbala=getattr(payload_data, 'shadbala', {}),
            branch_affinity_weights=llm_affinity,
            ak=ak, amk=amk, nb_set=nb_set)
        if not aptitudes["meets_threshold"]:  score *= 0.70
        if conflict["mismatch_risk"]:         score *= 0.85
        # FIX-2: use friction_multiplier for proportional penalty (replaces binary 0.70× gate)
        score *= audit.get("friction_multiplier", 1.0)
        if not audit["passed_qa_gate"]:       score *= 0.70

        # Build per-field final-chain trace for explainability
        _thresh_mult   = 0.70 if not aptitudes["meets_threshold"] else 1.0
        _mismatch_mult = 0.85 if conflict["mismatch_risk"] else 1.0
        _friction_mult = audit.get("friction_multiplier", 1.0)
        _qa_mult       = 0.70 if not audit["passed_qa_gate"] else 1.0
        _after_gap     = round(blended * (1.0 + gap_boost) * (1.0 - gap_penalty), 4)

        calc_trace = {
            "planet_trace": planet_trace,      # full per-planet breakdown (all 9)
            # Educational planet set — REMOVED (old keyword pipeline, now {} / [] stubs)
            "edu_planet_reasons": edu_planet_reasons,   # {} — edu pipeline removed
            "edu_eff_strengths":  edu_eff_strengths,    # {} — edu pipeline removed
            "edu_ranked":         [p for p, _ in edu_ranked],  # [] — edu pipeline removed
            "affinity_weights": affinity_result["affinity_planets"],
            "affinity_contributions": affinity_result["planet_contributions"],
            "normalization": {
                "composite_score_raw":  round(aptitudes["composite_score"], 4),
                "composite_norm":       round(_log_norm_score(aptitudes["composite_score"], _COMPOSITE_SOFT_CAP), 4),
                "affinity_score_raw":   round(affinity_result["affinity_score"], 4),
                "affinity_norm":        round(_log_norm_score(affinity_result["affinity_score"], _AFFINITY_SOFT_CAP), 4),
                "domain_blend_weight":  DOMAIN_BLEND,
                "affinity_blend_weight":AFFINITY_BLEND,
                "blended":              round(blended, 4),
            },
            "gap_boosts": {k: v for k, v in gap_detail.items() if v > 0.0},
            "gap_penalties": {k: v for k, v in gap_detail.items() if v < 0.0},
            "gap_boost_total": round(gap_boost, 4),
            "gap_penalty_total": round(gap_penalty, 4),
            "final_chain": {
                "blended":             round(blended, 4),
                "after_boost":         round(blended * (1.0 + gap_boost), 4),
                "after_penalty":       round(_after_gap, 4),
                "threshold_mult":      _thresh_mult,
                "threshold_note":      "meets_threshold=False → ×0.70" if _thresh_mult < 1 else "threshold OK",
                "mismatch_mult":       _mismatch_mult,
                "mismatch_note":       "domain mismatch detected → ×0.85" if _mismatch_mult < 1 else "no mismatch",
                "friction_mult":       round(_friction_mult, 4),
                "friction_note":       audit.get("audit_notes",""),
                "qa_gate_mult":        _qa_mult,
                "qa_gate_note":        "QA gate FAILED → ×0.70" if _qa_mult < 1 else "QA gate passed",
                "final_score":         round(score, 4),
            },
            "active_dasha_lord":  active_lord,
            "peak_dasha_lord":    peak_lord,
            "karakas":            {"AK": ak, "AmK": amk},
            "aspects_on_h10":     [p for p, hs in _get_planetary_aspects(ph).items() if 10 in hs],
        }

        # ── Registry enrichment (UG/PG/PhD/exams/career) ────────────────────
        _reg_meta = _COURSE_REGISTRY.get(branch_name, {})
        _tier     = _reg_meta.get("tier_map", {})
        _ug_info  = _tier.get("UG",  {})
        _pg_info  = _tier.get("PG",  {})
        _phd_info = _tier.get("PhD", {})

        _all_pre_results.append({
            "field_id":     branch_name,
            "field_label":  label,
            "domain":       domain,
            "final_score":  round(score, 2),
            "score_components": {
                "domain_score":    round(aptitudes["composite_score"], 2),
                "affinity_score":  affinity_result["affinity_score"],
                "blended":         round(blended, 2),
                "gap_boost_pct":   round(gap_boost * 100, 1),
                "gap_penalty_pct": round(gap_penalty * 100, 1),
                "bias_multiplier": 1.0,
                "paksha_bala":     round(pb_val, 3),
            },
            "gap_breakdown":      gap_detail,
            "affinity_source":    affinity_result["affinity_source"],
            "top_affinity_planets": dict(sorted(affinity_result["planet_contributions"].items(), key=lambda x: x[1], reverse=True)[:3]),
            "aptitude_profile":   aptitudes,
            "structural_audit":   audit,
            "conflict_report":    conflict,
            "war_losers":         [p for p,s in war_result.items() if s=="loser"],
            "war_winners":        [p for p,s in war_result.items() if s=="winner"],
            "vargottama_planets": vargottama,
            "neecha_bhanga":      list(nb_set),
            "cazimi_planets":     list(cazimi_set),
            "calc_trace":         calc_trace,
            "llm_astrological_reason": llm_astro_reason,
            "llm_selection_rationale": llm_sel_rationale,
            # ── Registry metadata for report rendering ────────────────────────
            "registry": {
                "description":     _reg_meta.get("description", ""),
                "specialization":  _reg_meta.get("specialization", ""),
                "niche":           _reg_meta.get("niche", ""),
                "ug_program":      _ug_info.get("spec", ""),
                "ug_niche":        _ug_info.get("niche", ""),
                "pg_program":      _pg_info.get("spec", ""),
                "pg_niche":        _pg_info.get("niche", ""),
                "phd_program":     _phd_info.get("spec", ""),
                "phd_niche":       _phd_info.get("niche", ""),
                "admission_exams": _reg_meta.get("admission_exams", []),
                "career_paths":    _reg_meta.get("career_signature", []),
                "institutions":    _reg_meta.get("institutions", []),
            },
        })

    _all_pre_results.sort(key=lambda x: -x["final_score"])

    _all_deduped = _apply_domain_deduplication(_all_pre_results, payload_data)
    _top_35 = _all_deduped[:35]

    _top_35_for_prompt = [
        {"rank": i+1, "field_id": r["field_id"], "field_label": r["field_label"],
         "domain": r["domain"], "python_score": r["final_score"], "domain": r["domain"],
         "top_karakas": list(r.get("top_affinity_planets", {}).keys())[:2]}
        for i, r in enumerate(_top_35)
    ]
    llm_selection: List[Dict] = call_llm_for_fields(
        payload_data, eff_strengths,
        top_35_fields=_top_35_for_prompt,
    )
    logger.info(f"LLM selected {len(llm_selection)} fields from top-35 for {getattr(payload_data,'name','?')}")

    # ── Phase 3: merge LLM reasons into pre-computed results ─────────────────
    _pre_score_map = {r["field_id"]: r for r in _all_pre_results}
    results = []
    _llm_sel_rationale_global = (llm_selection[0].get("llm_selection_rationale", "")
                                 if llm_selection else "")
    _llm_parent_summary_global = (llm_selection[0].get("llm_parent_summary", "")
                                  if llm_selection else "")

    for sel in llm_selection:
        fid = sel.get("field_id", "")
        is_soul = sel.get("llm_group", "match") == "soul"
        if fid not in _pre_score_map:
            if not is_soul:
                continue
            # Soul field chosen by LLM may sit outside top-35 pool.
            # Build a minimal scored entry from registry so it is never silently dropped.
            reg = _COURSE_REGISTRY.get(fid, {})
            if not reg:
                logger.warning(f"LLM soul field '{fid}' not in registry — skipping soul.")
                continue
            logger.info(f"LLM soul field '{fid}' not in pre-score pool — adding from registry.")
            _pre_score_map[fid] = {
                "field_id":    fid,
                "field_label": reg.get("label", fid.replace("_", " ").title()),
                "domain":      reg.get("domain", "interdisciplinary"),
                "final_score": 0.0,   # score unknown; soul card shown without score bar
                "gap_breakdown": {}, "gap_boosts": {}, "gap_boost_pct": 0,
                "score_components": {}, "top_affinity_planets": {},
                "registry": reg,
            }
        r = dict(_pre_score_map[fid])
        r["llm_astrological_reason"] = sel.get("llm_astrological_reason", "")
        r["llm_parent_reason"]       = sel.get("llm_parent_reason", "")
        r["llm_selection_rationale"] = _llm_sel_rationale_global
        r["llm_parent_summary"]      = _llm_parent_summary_global
        r["llm_group"]               = sel.get("llm_group", "match")
        r["llm_rank"]                = sel.get("llm_rank", len(results) + 1)
        results.append(r)

    # Fallback: if LLM returned nothing (empty or noop), use domain-deduped results directly
    # Use _all_deduped (not _all_pre_results) so cluster caps are respected in fallback path.
    if not results:
        for i, r in enumerate(_all_deduped[:25], 1):
            r2 = dict(r)
            r2["llm_astrological_reason"] = ""
            r2["llm_parent_reason"]       = ""
            r2["llm_selection_rationale"] = ""
            r2["llm_parent_summary"]      = ""
            r2["llm_rank"]                = i
            results.append(r2)
        sorted_results = sorted(results, key=lambda x: -x["final_score"])
        return sorted_results

    # Sort: match fields first (by rank), soul field last
    sorted_results = sorted(results, key=lambda x: (x.get("llm_group","match") == "soul", x.get("llm_rank", 99)))
    return sorted_results