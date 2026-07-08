"""Macro-cluster and field display helpers for career field reports."""
from __future__ import annotations

from typing import Any, Dict

_CLUSTER_DISPLAY_LABELS = {
    "Advanced Engineering & Physical Systems": "Engineering, Space & Physical Systems",
    "Computation, Data & Digital Intelligence": "Economics, Analytics & Digital Intelligence",
    "Medicine, Health & Life Sciences": "Medical, Health & Public Welfare",
    "Governance, Law & Strategic/Defence Institutions": "Law, Governance & Public Leadership",
    "Knowledge, Humanities & Behavioural Sciences": "Research, Academia & Knowledge Systems",
    "Commerce, Finance & Enterprise": "Economics, Finance & Enterprise",
    "Design, Media & Creative Expression": "Design, Media & Creative Expression",
    "Agriculture & Environmental Systems": "Agriculture, Environment & Sustainability",
}


def _field_display_name(row: Dict[str, Any]) -> str:
    return row.get("field_label") or row.get("field_id", "Unknown").replace("_", " ").title()


def _cluster_display_name(cluster: str) -> str:
    return _CLUSTER_DISPLAY_LABELS.get(cluster, cluster)


def _print_macro_cluster(row: Dict[str, Any]) -> str:
    fid = row.get("field_id", "")
    family = (row.get("career_family_label") or row.get("career_family") or "").lower()
    label = _field_display_name(row).lower()
    domain = (row.get("domain") or "").lower()

    if fid in {
        "international_law", "civil_services", "public_policy", "international_relations",
        "political_science", "law_llb", "environmental_law", "corporate_law",
        "criminal_law", "intellectual_property_law",
    } or "law" in label or "governance" in label or "civil" in label or "diplomacy" in label:
        return "Law, Governance & Public Leadership"
    if fid in {
        "research_academia", "history_archaeology", "philosophy", "education_teaching",
        "organisational_psychology", "gender_studies", "sociology_anthropology",
        "planetary_science",
    } or "research" in label or "academia" in label or "psychology" in label:
        return "Research, Academia & Knowledge Systems"
    if fid in {
        "medicine_mbbs", "public_health", "healthcare_management", "medical_research",
        "ayurveda", "homeopathy", "unani_medicine", "yoga_naturopathy",
    } or "health" in label or "medicine" in label or "hospital" in label:
        return "Medical, Public Health & Welfare"
    if fid in {
        "economics_data_science", "economics", "computational_finance", "finance_banking",
        "computational_social_science", "econometrics",
    } or domain in {"commerce", "finance", "economics"}:
        return "Economics, Policy Analytics & Social Sciences"
    if "agri" in family or "agri" in label:
        return "Agriculture, Environment & Sustainability"
    return _cluster_display_name(
        row.get("graph_cluster")
        or row.get("competency_label")
        or row.get("career_family_label")
        or row.get("domain")
        or "Other"
    )
