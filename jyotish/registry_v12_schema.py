"""JyotishAI registry v12 schema + enrichment utilities.

Drop this file at: jyotish/registry_v12_schema.py

Purpose
-------
Convert the existing v11 course registry into a production-grade v12 registry
without changing deterministic astrological scoring. The enriched registry adds:

* classic_core vs modern_extensions
* native ontology metadata, including secondary weighted families
* education_realism
* normalized institution availability
* canonical admission exams
* curriculum/skill intensity
* market/risk metadata
* safe/ambitious/backup route maps
* deterministic avoid_primary_when flags
* split career outcomes: core / aspirational / research / government / startup

Design principles
-----------------
1. No astrology scoring here. This module only improves field metadata.
2. Fully deterministic. No LLM or web dependency.
3. Strict validation hooks so registry/affinity/ontology drift is caught early.
4. Backward compatible: existing v11 keys are preserved on each branch.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Set, Tuple
import copy
import re

# ---------------------------------------------------------------------------
# Canonical exams
# ---------------------------------------------------------------------------

CANONICAL_EXAM_ALIASES: Dict[str, str] = {
    "JEE_Advanced": "JEE_ADVANCED",
    "JEE_ADVANCED": "JEE_ADVANCED",
    "JEE_Main": "JEE_MAIN",
    "JEE_MAIN": "JEE_MAIN",
    "BITSAT": "BITSAT",
    "NEET_UG": "NEET_UG",
    "NEET": "NEET_UG",
    "CLAT": "CLAT",
    "AILET": "AILET",
    "LSAT_India": "LSAT_INDIA",
    "LSAT_INDIA": "LSAT_INDIA",
    "CUET": "CUET_UG",
    "CUET_UG": "CUET_UG",
    "DU_Entrance": "CUET_UG",
    "BHU_UET": "CUET_UG",
    "IAT": "IAT",
    "NEST": "NEST",
    "JAM": "IIT_JAM",
    "IIT_JAM": "IIT_JAM",
    "GATE": "GATE",
    "CSIR_NET": "CSIR_NET",
    "UGC_NET": "UGC_NET",
    "JEST": "JEST",
    "ISI_Exam": "ISI_EXAM",
    "CMI_Exam": "CMI_EXAM",
    "NBHM": "NBHM",
    "ICAR_AIEEA": "ICAR_AIEEA",
    "NATA": "NATA",
    "UCEED": "UCEED",
    "NID_Entrance": "NID_ENTRANCE",
    "NIFT_Entrance": "NIFT_ENTRANCE",
    "IMU_CET": "IMU_CET",
    "NCHMCT_JEE": "NCHMCT_JEE",
    "CA_Foundation": "CA_FOUNDATION",
    "CAT": "CAT",
    "XAT": "XAT",
    "DSE_Entrance": "DSE_ENTRANCE",
    "IIMC_Entrance": "IIMC_ENTRANCE",
    "ACJ_Entrance": "ACJ_ENTRANCE",
    "FTII_Entrance": "FTII_ENTRANCE",
    "SRFTI_Entrance": "SRFTI_ENTRANCE",
    "Audition_Based": "AUDITION_BASED",
    "CTET": "CTET",
    "State_Entrance": "STATE_ENTRANCE",
    "State_PSC": "STATE_PSC",
    "State_BEd_Entrance": "STATE_BED_ENTRANCE",
    "State_Ag_Entrance": "STATE_AG_ENTRANCE",
    "UPSC_CSE": "UPSC_CSE",
    "NDA_NA": "NDA_NA",
    "CDS": "CDS",
    "AFCAT": "AFCAT",
    "Technical_Entry_Scheme": "TECHNICAL_ENTRY_SCHEME",
    "TISS_NET": "TISS_NET",
    "IPM_Entrance": "IPM_ENTRANCE",
}

VALID_EXAMS: Set[str] = set(CANONICAL_EXAM_ALIASES.values())


def canonicalize_exam(exam: Any) -> str:
    raw = str(exam or "").strip()
    if not raw:
        return ""
    return CANONICAL_EXAM_ALIASES.get(raw, raw.upper().replace(" ", "_"))


def canonicalize_exams(exams: Iterable[Any]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for e in exams or []:
        c = canonicalize_exam(e)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Institution availability normalization
# ---------------------------------------------------------------------------

def _availability_score(value: Any) -> float:
    if isinstance(value, list):
        if not value:
            return 0.0
        if any(str(x).lower().startswith("all_") for x in value):
            return 1.0
        return min(1.0, 0.25 + 0.15 * len(value))
    if isinstance(value, bool):
        return 0.65 if value else 0.0
    if isinstance(value, str):
        return 0.45 if value else 0.0
    return 0.0


def normalize_available_at(available_at: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Normalize v11's mixed bool/list/string availability into one schema."""
    normalized: Dict[str, Dict[str, Any]] = {}
    for inst_type, raw in (available_at or {}).items():
        campuses: List[str] = []
        available = False
        confidence = "unknown"
        note = ""
        if isinstance(raw, list):
            campuses = [str(x) for x in raw]
            available = bool(campuses)
            confidence = "representative" if campuses and not any(x.startswith("All_") for x in campuses) else ("broad" if campuses else "none")
        elif isinstance(raw, bool):
            available = raw
            confidence = "generic" if raw else "none"
            note = "Registry v11 supplied boolean availability; campus list not curated."
        elif isinstance(raw, str):
            available = bool(raw)
            campuses = [raw] if raw else []
            confidence = "textual" if raw else "none"
        else:
            available = False
            confidence = "none"
        normalized[inst_type] = {
            "available": available,
            "campuses": campuses,
            "availability_score": round(_availability_score(raw), 3),
            "confidence": confidence,
            "notes": note,
            "raw_v11_value": raw,
        }
    return normalized


# ---------------------------------------------------------------------------
# Field categories and heuristics
# ---------------------------------------------------------------------------

LICENSED_PROFESSIONAL_FIELDS: Set[str] = {
    "medicine_mbbs", "dentistry", "ayurveda", "homeopathy", "unani_medicine",
    "yoga_naturopathy", "nursing", "pharmacy", "law_llb", "corporate_law",
    "criminal_law", "international_law", "environmental_law", "intellectual_property_law",
    "architecture", "commerce_accounting", "chartered_accountancy", "company_secretary",
}

RESEARCH_HEAVY_FIELDS: Set[str] = {
    "research_academia", "physics", "chemistry", "mathematics", "biological_sciences",
    "astronomy_astrophysics", "planetary_science", "neuroscience", "medical_research",
    "molecular_biology_genetics", "biochemistry", "nanotechnology_engineering",
    "materials_science_engineering", "engineering_physics", "medical_physics",
}

DIRECT_JOB_FRIENDLY_DOMAINS: Set[str] = {"engineering", "technology", "medicine", "law", "commerce", "public"}
GENERIC_BROAD_FIELDS: Set[str] = {
    "liberal_arts_interdisciplinary", "business_management", "mass_communication",
    "visual_communication", "research_academia", "real_estate_management",
    "development_studies", "tourism_management", "entrepreneurship",
    "commerce_accounting", "environmental_studies_interdisciplinary", "psychology",
}
HIGH_RISK_NICHE_FIELDS: Set[str] = {
    "game_design_technology", "visual_communication", "photography", "animation_multimedia",
    "fashion_design", "fine_arts", "tourism_management", "hotel_hospitality_management",
    "printing_packaging_technology", "leather_technology", "textile_design",
}

ASPIRATIONAL_KEYWORDS = re.compile(r"tesla|google|microsoft|amazon|faang|blackrock|mayo|binance|startup|startups|global tech|space startups", re.I)
GOV_KEYWORDS = re.compile(r"isro|drdo|hal|nal|psu|upsc|state|government|public sector|aiims|icar|barc|csir|nha[iy]|pwd|railway|defence|defense", re.I)
RESEARCH_KEYWORDS = re.compile(r"research|r&d|lab|labs|csir|isro|drdo|aiims|iit|phd|academia", re.I)
STARTUP_KEYWORDS = re.compile(r"startup|startups|venture|entrepreneur", re.I)

FUTURE_NOISE_PATTERNS = [
    (re.compile(r"Next-generation application of (.*?), focusing on .*? to solve complex modern challenges\.?", re.I), r"Study and professional application of \1."),
    (re.compile(r"AI Integration\s*/\s*Global Strategy\s*/\s*Digital Transformation", re.I), "Digital media strategy / communication planning / content systems"),
    (re.compile(r"Quantum Sensing\s*/\s*Modern Mechanical", re.I), "Design / Thermal / Manufacturing / Mechanics"),
    (re.compile(r"High-Frequency Trading\s*/\s*Predictive Analytics\s*/\s*ESG Risk Modeling", re.I), "Accounting / audit / taxation / finance operations"),
    (re.compile(r"Robotic Surgery\s*/\s*Personalized Genomics\s*/\s*Neural Interfaces", re.I), "Assistive devices / rehabilitation technology / clinical prosthetics"),
]


def clean_futuristic_text(text: Any, fallback: str = "") -> str:
    t = str(text or fallback or "").strip()
    for rx, repl in FUTURE_NOISE_PATTERNS:
        t = rx.sub(repl, t)
    # conservative cleanup only; do not erase real modern extensions globally
    t = t.replace("Next-generation ", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def compute_specificity_score(field_id: str, branch: Mapping[str, Any], broadness_penalty: float = 0.0) -> float:
    score = 0.74
    label_blob = " ".join(str(branch.get(k, "")) for k in ("label", "field", "track", "specialization", "niche")).lower()
    if field_id in LICENSED_PROFESSIONAL_FIELDS:
        score += 0.12
    if field_id in GENERIC_BROAD_FIELDS or broadness_penalty >= 0.10:
        score -= 0.18
    if "interdisciplinary" in label_blob or "management" in label_blob or "liberal arts" in label_blob:
        score -= 0.08
    if "engineering" in label_blob or "medicine" in label_blob or "law" in label_blob or "science" in label_blob:
        score += 0.05
    return round(min(max(score, 0.25), 0.98), 3)


def build_classic_and_modern(branch: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    label = branch.get("label", "")
    field = branch.get("field", label)
    track = branch.get("track", field)
    specialization = branch.get("specialization", label)
    niche = branch.get("niche", "")
    desc = branch.get("description", "")
    classic_desc = clean_futuristic_text(desc, fallback=f"Study and professional practice of {label}.")
    classic_niche = clean_futuristic_text(niche, fallback=specialization)
    modern_terms: List[str] = []
    blob = " ".join(str(branch.get(k, "")) for k in ("description", "niche", "career_signature"))
    for term in ["AI", "Data", "Robotics", "EV", "Semiconductor", "Space", "Digital", "Sustainability", "Genomics", "Cybersecurity", "Remote Sensing"]:
        if term.lower() in blob.lower() and term not in modern_terms:
            modern_terms.append(term)
    if not modern_terms:
        modern_terms = ["Digital tools", "Applied analytics", "Interdisciplinary specialization"]
    return {
        "classic_core": {
            "field": field,
            "track": track,
            "specialization": clean_futuristic_text(specialization, fallback=label),
            "description": classic_desc,
            "niche": classic_niche,
        },
        "modern_extensions": {
            "extensions": modern_terms[:6],
            "description": f"Modern extensions of {label} may include {', '.join(modern_terms[:4]).lower()} depending on institute, projects and PG specialization.",
            "caution": "Do not treat modern extensions as guaranteed UG outcomes; they usually require electives, projects, internships or PG/upskilling.",
        },
    }


def compute_education_realism(field_id: str, branch: Mapping[str, Any], normalized_available_at: Mapping[str, Any]) -> Dict[str, Any]:
    domain = str(branch.get("domain", "")).lower()
    degree_types = set(str(x) for x in branch.get("degree_types", []) or [])
    exams = canonicalize_exams(branch.get("admission_exams", []) or [])
    avail_scores = [v.get("availability_score", 0.0) for v in normalized_available_at.values()]
    top_inst_score = max((normalized_available_at.get(k, {}).get("availability_score", 0.0) for k in ("IIT", "NIT", "AIIMS", "IISER", "NISER", "ISI", "BITS", "IIIT")), default=0.0)
    broad_avail = max(avail_scores) if avail_scores else 0.0

    ug_available = bool(degree_types & {"BTech", "BE", "BSc", "BA", "BCom", "BBA", "LLB", "BA_LLB", "MBBS", "BAMS", "BHMS", "BUMS", "BNYS", "BDes", "BArch", "Diploma"})
    pg_required = (field_id in RESEARCH_HEAVY_FIELDS or domain in {"science", "humanities", "interdisciplinary"}) and field_id not in LICENSED_PROFESSIONAL_FIELDS
    professional_license = field_id in LICENSED_PROFESSIONAL_FIELDS or bool({"NEET_UG", "CLAT", "AILET", "NATA", "CA_FOUNDATION"} & set(exams))

    direct_job = 0.55
    if domain in DIRECT_JOB_FRIENDLY_DOMAINS:
        direct_job += 0.16
    if pg_required:
        direct_job -= 0.18
    if field_id in HIGH_RISK_NICHE_FIELDS:
        direct_job -= 0.10
    if professional_license:
        direct_job += 0.08

    risk = "Medium"
    if field_id in HIGH_RISK_NICHE_FIELDS or (pg_required and broad_avail < 0.55):
        risk = "Medium-High"
    if professional_license and broad_avail >= 0.55:
        risk = "Medium"
    if domain in {"engineering", "technology"} and broad_avail >= 0.65:
        risk = "Low-Medium"

    return {
        "ug_availability_score": round(0.75 if ug_available else 0.25, 3),
        "top_institute_availability_score": round(top_inst_score, 3),
        "overall_availability_score": round(broad_avail, 3),
        "direct_job_after_ug_score": round(min(max(direct_job, 0.10), 0.95), 3),
        "pg_required_for_good_outcome": bool(pg_required),
        "professional_license_required": bool(professional_license),
        "credential_barrier": "high" if professional_license or top_inst_score >= 0.8 else ("medium" if exams else "low-medium"),
        "parent_safe_route": bool((domain in {"engineering", "medicine", "law", "commerce", "technology"}) and risk in {"Low", "Low-Medium", "Medium"}),
        "risk_level": risk,
    }


def compute_curriculum(branch: Mapping[str, Any]) -> Dict[str, Any]:
    domain = str(branch.get("domain", "")).lower()
    text = " ".join(str(branch.get(k, "")) for k in ("label", "field", "track", "specialization", "niche", "description")).lower()
    scores = {
        "math_intensity": 2,
        "coding_intensity": 1,
        "physics_intensity": 1,
        "chemistry_intensity": 1,
        "biology_intensity": 1,
        "writing_intensity": 2,
        "fieldwork_intensity": 1,
        "people_interaction": 2,
    }
    if domain in {"engineering", "technology", "science"}:
        scores.update(math_intensity=4, physics_intensity=3)
    if any(k in text for k in ("computer", "data", "ai", "cyber", "software", "analytics", "quant", "computational")):
        scores["coding_intensity"] = 5
        scores["math_intensity"] = max(scores["math_intensity"], 4)
    if any(k in text for k in ("chemical", "chemistry", "materials", "metall", "ceramic", "polymer")):
        scores["chemistry_intensity"] = 4
        scores["physics_intensity"] = max(scores["physics_intensity"], 3)
    if domain == "medicine" or any(k in text for k in ("bio", "medical", "neuro", "pharma", "health", "nursing")):
        scores["biology_intensity"] = 5
        scores["people_interaction"] = max(scores["people_interaction"], 4)
    if domain in {"law", "humanities", "public", "media", "arts", "education"}:
        scores["writing_intensity"] = 5
        scores["people_interaction"] = max(scores["people_interaction"], 4)
    if any(k in text for k in ("agri", "geology", "mining", "civil", "architecture", "environment", "field")):
        scores["fieldwork_intensity"] = 4
    core_subjects = []
    if scores["math_intensity"] >= 4: core_subjects.append("Mathematics")
    if scores["physics_intensity"] >= 3: core_subjects.append("Physics")
    if scores["chemistry_intensity"] >= 3: core_subjects.append("Chemistry")
    if scores["biology_intensity"] >= 4: core_subjects.append("Biology")
    if scores["coding_intensity"] >= 4: core_subjects.append("Programming / Data")
    if scores["writing_intensity"] >= 4: core_subjects.append("Reading, writing and argumentation")
    if not core_subjects: core_subjects = ["Core subjects aligned to the degree"]
    return {**scores, "core_subjects_ug": core_subjects}


def compute_market(field_id: str, branch: Mapping[str, Any]) -> Dict[str, Any]:
    domain = str(branch.get("domain", "")).lower()
    text = " ".join(str(branch.get(k, "")) for k in ("label", "field", "track", "specialization", "niche")).lower()
    high = any(k in text for k in ("data", "ai", "semiconductor", "cyber", "space", "materials", "medical", "health", "electronics", "energy"))
    market_depth = "deep" if domain in {"engineering", "technology", "medicine", "commerce"} else "medium"
    if field_id in HIGH_RISK_NICHE_FIELDS:
        market_depth = "niche"
    automation_risk = "medium"
    if domain in {"arts", "media", "commerce"} and not any(k in text for k in ("data", "analytics", "law", "health")):
        automation_risk = "medium-high"
    if any(k in text for k in ("medicine", "nursing", "public health", "civil", "mechanical", "materials")):
        automation_risk = "low-medium"
    return {
        "india_2026_demand": "high" if high else "stable",
        "india_2035_demand": "high" if high or domain in {"engineering", "technology", "medicine"} else "stable",
        "global_2035_demand": "high" if high else "medium",
        "market_depth": market_depth,
        "freshers_market": "medium" if market_depth != "niche" else "low-medium",
        "automation_risk": automation_risk,
        "credential_barrier": "high" if field_id in LICENSED_PROFESSIONAL_FIELDS else "medium",
    }


def split_career_outcomes(signature: Iterable[Any]) -> Dict[str, List[str]]:
    buckets = {"core": [], "aspirational": [], "research": [], "government_psu": [], "startup": []}
    for item in signature or []:
        s = str(item)
        if STARTUP_KEYWORDS.search(s):
            buckets["startup"].append(s)
        elif GOV_KEYWORDS.search(s):
            buckets["government_psu"].append(s)
        elif RESEARCH_KEYWORDS.search(s):
            buckets["research"].append(s)
        elif ASPIRATIONAL_KEYWORDS.search(s):
            buckets["aspirational"].append(s)
        else:
            buckets["core"].append(s)
    return buckets


def build_routes(field_id: str, branch: Mapping[str, Any], edu: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    label = branch.get("label", field_id.replace("_", " ").title())
    tier = branch.get("tier_map", {}) or {}
    domain = str(branch.get("domain", "")).lower()
    ug = (tier.get("UG") or {}).get("spec") or "/".join(branch.get("degree_types", []) or []) or f"UG aligned to {label}"
    pg = (tier.get("PG") or {}).get("spec") or f"PG specialization in/around {label}"
    phd = (tier.get("PhD") or {}).get("spec") or f"Research/PhD option in {label} if research fit is strong"
    exams = canonicalize_exams(branch.get("admission_exams", []) or [])
    safe = ug
    if edu.get("pg_required_for_good_outcome"):
        safe = f"Broad UG foundation → {pg}"
    if domain == "engineering" and field_id not in {"computer_science_engineering", "electrical_engineering", "mechanical_engineering"}:
        backup = "Mechanical / Electrical / Chemical / broader engineering UG → later specialization"
    elif domain == "medicine":
        backup = "Allied health / life-science UG backup → clinical/public-health PG route"
    elif domain in {"law", "public", "humanities"}:
        backup = "BA Economics / Political Science / Sociology / English → policy/law/UPSC route"
    elif domain == "commerce":
        backup = "BCom / BBA / Economics → analytics/finance/management specialization"
    else:
        backup = f"Broad UG in {domain or 'related domain'} → specialization after performance clarity"
    return {
        "ambitious_route": {
            "label": "High-end specialized route",
            "ug": ug,
            "pg": pg,
            "phd_or_research": phd,
            "entrance_exams": exams,
        },
        "safe_route": {
            "label": "Parent-safe practical route",
            "path": safe,
            "why": "Keeps options broad while preserving alignment with this field.",
        },
        "backup_route": {
            "label": "Backup / adjacent route",
            "path": backup,
            "why": "Useful if entrance rank, interest, or market conditions make the direct route less practical.",
        },
    }


def build_avoid_primary_when(field_id: str, branch: Mapping[str, Any], edu: Mapping[str, Any], curriculum: Mapping[str, Any]) -> Dict[str, bool]:
    return {
        "low_math": curriculum.get("math_intensity", 0) >= 4,
        "low_biology": curriculum.get("biology_intensity", 0) >= 4,
        "low_writing_or_reading": curriculum.get("writing_intensity", 0) >= 4,
        "low_risk_appetite": field_id in HIGH_RISK_NICHE_FIELDS or edu.get("risk_level") in {"Medium-High", "High"},
        "requires_high_rank": bool({"JEE_ADVANCED", "NEET_UG", "CLAT", "NATA"} & set(canonicalize_exams(branch.get("admission_exams", []) or []))),
        "poor_direct_ug_outcome": edu.get("direct_job_after_ug_score", 0.0) < 0.45,
        "needs_pg_for_good_outcome": bool(edu.get("pg_required_for_good_outcome")),
    }


def enrich_branch_v12(
    field_id: str,
    branch: Mapping[str, Any],
    *,
    field_to_family: Mapping[str, str],
    family_meta: Mapping[str, Mapping[str, Any]],
    secondary_edges: Iterable[Tuple[str, str, float]] = (),
    broadness_penalty_map: Mapping[str, float] = None,
) -> Dict[str, Any]:
    """Return a v12-enriched branch while preserving all existing v11 keys."""
    broadness_penalty_map = broadness_penalty_map or {}
    out = copy.deepcopy(dict(branch))
    normalized_available = normalize_available_at(branch.get("available_at", {}) or {})
    canonical_exams = canonicalize_exams(branch.get("admission_exams", []) or [])
    broadness = float(broadness_penalty_map.get(field_id, 0.0) or 0.0)
    primary_family = field_to_family.get(field_id, "")
    family = family_meta.get(primary_family, {}) if primary_family else {}
    primary_comp = family.get("competency", "")
    secondary = {fam: float(w) for fid, fam, w in secondary_edges if fid == field_id}
    specificity = compute_specificity_score(field_id, branch, broadness)
    classic_modern = build_classic_and_modern(branch)
    edu = compute_education_realism(field_id, branch, normalized_available)
    curriculum = compute_curriculum(branch)
    market = compute_market(field_id, branch)
    out.update(classic_modern)
    out["admission_exams_canonical"] = canonical_exams
    out["available_at_normalized"] = normalized_available
    out["ontology"] = {
        "primary_competency": primary_comp,
        "primary_family": primary_family,
        "primary_family_label": family.get("label", primary_family.replace("_", " ").title()) if primary_family else "",
        "secondary_families": secondary,
        "specificity_score": specificity,
        "broadness_score": round(broadness, 3),
        "ontology_policy": {
            "primary_family": "display_and_grouping",
            "secondary_families": "graph_diagnostics_and_explanation",
            "specificity_score": "confidence_and_practicality",
            "broadness_score": "bounded_score_modifier_only_if_enabled",
        },
    }
    out["education_realism"] = edu
    out["curriculum"] = curriculum
    out["market"] = market
    out["risk"] = {
        "risk_level": edu.get("risk_level", "Medium"),
        "parent_safe_route": edu.get("parent_safe_route", False),
        "avoid_primary_when": build_avoid_primary_when(field_id, branch, edu, curriculum),
    }
    out["routes"] = build_routes(field_id, branch, edu)
    out["career_outcomes"] = split_career_outcomes(branch.get("career_signature", []) or [])
    out["schema_version"] = "v12.0_enriched_registry"
    return out
