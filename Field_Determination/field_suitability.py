"""Professional route-suitability classification for ranked career fields.

This layer does not change astrological aptitude rank. It separates chart
alignment, academic compatibility, education feasibility and career viability
so a PG-dependent or niche field is not mislabeled as astrologically rejected.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


STATUS_PRIMARY = "Recommended as Primary"
STATUS_CONDITIONAL = "Recommended with Conditions"
STATUS_PG = "Better as a Specialization or PG Route"
STATUS_EXPLORATORY = "Exploratory or Secondary Option"
STATUS_NOT_PRIMARY = "Not Recommended as Primary"
STATUS_REQUIRES_VALIDATION = "Requires Academic Validation"

SUBJECT_REQUIREMENTS = {
    "math_intensity": "mathematics", "physics_intensity": "physics",
    "chemistry_intensity": "chemistry", "biology_intensity": "biology",
    "coding_intensity": "coding", "writing_intensity": "writing",
    "people_interaction": "people_interaction", "fieldwork_intensity": "fieldwork",
}


def _section(row: Mapping[str, Any], key: str) -> Dict[str, Any]:
    direct = row.get(key)
    if isinstance(direct, dict) and direct:
        return direct
    v12 = row.get("registry_v12") or row.get("registry") or {}
    value = v12.get(key, {}) if isinstance(v12, Mapping) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _academic_score(curriculum: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    weighted, weights, missing, contraindications = 0.0, 0.0, [], []
    for intensity_key, profile_key in SUBJECT_REQUIREMENTS.items():
        intensity = float(curriculum.get(intensity_key, 0) or 0)
        if intensity < 4:
            continue
        raw = profile.get(profile_key)
        if raw is None:
            missing.append(f"{profile_key.replace('_', ' ').title()} performance/interest not supplied")
            continue
        try:
            ability = float(raw)
            if ability > 1.0: ability /= 100.0
            ability = max(0.0, min(1.0, ability))
        except (TypeError, ValueError):
            missing.append(f"{profile_key.replace('_', ' ').title()} value is invalid")
            continue
        weight = intensity / 5.0
        weighted += ability * 100.0 * weight; weights += weight
        if ability < 0.40:
            contraindications.append(f"Low validated {profile_key.replace('_', ' ')} fit for a high-intensity curriculum")
    # Unknown academic evidence is neutral and explicitly disclosed, never
    # interpreted as weakness.
    return (round(weighted / weights, 2) if weights else 50.0, missing, contraindications)


def _education_score(edu: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    availability = float(edu.get("overall_availability_score", 0.0) or 0.0)
    ug = float(edu.get("ug_availability_score", 0.0) or 0.0)
    direct = float(edu.get("direct_job_after_ug_score", 0.0) or 0.0)
    score = 100.0 * (0.40 * availability + 0.25 * ug + 0.35 * direct)
    conditions, contra = [], []
    if edu.get("pg_required_for_good_outcome"):
        conditions.append("Plan a broad undergraduate foundation followed by PG specialization")
    if edu.get("professional_license_required"):
        conditions.append("Professional entrance/licensing requirements must be completed")
    if str(edu.get("credential_barrier", "")).lower() == "high":
        conditions.append("High credential or entrance barrier")
    if availability < 0.35:
        contra.append("Limited dependable education availability")
    if direct < 0.35:
        contra.append("Weak direct-employment pathway after undergraduate study")
    return round(max(0.0, min(100.0, score)), 2), conditions, contra


def _career_score(market: Mapping[str, Any], risk: Mapping[str, Any], risk_appetite: str) -> tuple[float, list[str], list[str]]:
    depth = {"deep": 90, "medium": 68, "niche": 42}.get(str(market.get("market_depth", "medium")).lower(), 60)
    fresh = {"high": 90, "medium": 68, "low-medium": 48, "low": 30}.get(str(market.get("freshers_market", "medium")).lower(), 60)
    demand = {"high": 90, "stable": 68, "medium": 60, "low": 35}.get(str(market.get("india_2035_demand", "stable")).lower(), 60)
    score = 0.40 * depth + 0.30 * fresh + 0.30 * demand
    conditions, contra = [], []
    risk_level = str(risk.get("risk_level", "Medium"))
    if risk_level in {"Medium-High", "High"}:
        conditions.append("Use internships, portfolio evidence and a broad backup route to manage market risk")
        if str(risk_appetite).upper() == "LOW":
            score -= 12
            contra.append("Career risk exceeds the supplied low risk appetite")
    if depth == 42:
        conditions.append("Niche market: retain an adjacent broad qualification")
    return round(max(0.0, min(100.0, score)), 2), conditions, contra


def assess_field_suitability(
    row: Mapping[str, Any], *, top_score: float,
    academic_profile: Mapping[str, Any] | None = None,
    risk_appetite: str = "MODERATE",
) -> Dict[str, Any]:
    academic_profile = academic_profile or {}
    raw = float(row.get("final_score", 0.0) or 0.0)
    astro = round(max(0.0, min(100.0, 100.0 * raw / top_score)), 2) if top_score > 0 else 0.0
    curriculum, edu, market, risk = (_section(row, x) for x in ("curriculum", "education_realism", "market", "risk"))
    academic, missing, academic_contra = _academic_score(curriculum, academic_profile)
    education, education_conditions, education_contra = _education_score(edu)
    career, career_conditions, career_contra = _career_score(market, risk, risk_appetite)

    astrological_contra = []
    if row.get("is_afflicted") and astro < 45:
        astrological_contra.append("Structural astrological QA gate is adverse")
    if float(row.get("net_contraindication_index", 0.0) or 0.0) >= 0.60 and astro < 50:
        astrological_contra.append("Multiple astrological methods show material contraindications")

    academic_unknown = bool(missing) and not academic_profile
    if academic_unknown:
        # Do not silently convert absent evidence into average aptitude.  The
        # point estimate uses only known dimensions and the interval shows the
        # full unresolved academic range (0..100 at 25% model weight).
        known_weight = 0.40 + 0.20 + 0.15
        known_total = 0.40 * astro + 0.20 * education + 0.15 * career
        overall = round(known_total / known_weight, 2)
        lower_overall = round(known_total, 2)
        upper_overall = round(known_total + 25.0, 2)
    else:
        overall = round(0.40 * astro + 0.25 * academic + 0.20 * education + 0.15 * career, 2)
        lower_overall = upper_overall = overall
    dimensions_adverse = sum(bool(x) for x in (astrological_contra, academic_contra, education_contra, career_contra))
    conditions = list(dict.fromkeys(education_conditions + career_conditions))
    contraindications = list(dict.fromkeys(astrological_contra + academic_contra + education_contra + career_contra))

    if overall >= 80 and not conditions and dimensions_adverse == 0:
        status = STATUS_PRIMARY
    elif overall >= 65:
        status = STATUS_CONDITIONAL if conditions or missing else STATUS_PRIMARY
    elif overall >= 50:
        status = STATUS_PG if edu.get("pg_required_for_good_outcome") else STATUS_CONDITIONAL
    elif overall >= 35 or dimensions_adverse < 2:
        status = STATUS_EXPLORATORY
    else:
        status = STATUS_NOT_PRIMARY

    # A rejection requires independent adverse evidence in at least two
    # dimensions. Low rank alone can only make a field exploratory.
    if status == STATUS_NOT_PRIMARY and dimensions_adverse < 2:
        status = STATUS_EXPLORATORY

    def band(value: float) -> str:
        if value >= 80: return STATUS_PRIMARY
        if value >= 65: return STATUS_CONDITIONAL
        if value >= 50: return STATUS_PG if edu.get("pg_required_for_good_outcome") else STATUS_CONDITIONAL
        if value >= 35: return STATUS_EXPLORATORY
        return STATUS_NOT_PRIMARY if dimensions_adverse >= 2 else STATUS_EXPLORATORY

    status_range = list(dict.fromkeys((band(lower_overall), band(upper_overall))))
    if academic_unknown and len(status_range) > 1:
        status = STATUS_REQUIRES_VALIDATION

    return {
        "recommendation_status": status,
        "astrological_alignment": astro,
        "academic_fit": academic,
        "academic_evidence_status": "unknown" if academic_unknown else "supplied",
        "education_feasibility": education,
        "career_viability": career,
        "overall_suitability": overall,
        "overall_suitability_interval": [lower_overall, upper_overall],
        "status_range": status_range,
        "decision_resolved": not (academic_unknown and len(status_range) > 1),
        "conditions": conditions,
        "contraindications": contraindications,
        "missing_validations": missing,
        "policy": "route-suitability.v2; unknown academics excluded from point estimate and represented by interval; rank preserved; rejection requires >=2 adverse dimensions",
    }


def annotate_field_suitability(
    rows: Iterable[Dict[str, Any]], *, academic_profile: Mapping[str, Any] | None = None,
    risk_appetite: str = "MODERATE",
) -> list[Dict[str, Any]]:
    rows = list(rows)
    top = max((float(r.get("final_score", 0.0) or 0.0) for r in rows), default=0.0)
    for row in rows:
        row["recommendation_assessment"] = assess_field_suitability(
            row, top_score=top, academic_profile=academic_profile, risk_appetite=risk_appetite,
        )
    return rows
