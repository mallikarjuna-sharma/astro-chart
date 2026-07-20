"""Shared report/CLI helpers for field labels and macro cluster grouping.

Drop this file at: jyotish/report_utils.py
Then import from here in both field_deterministic_engine_v1_llm.py and
career_field_report_v2.py instead of importing the CLI shim from the report.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

# PROVENANCE (2026-07, transparency): (B) ENGINEERED -- see
# jyotish/constants.py's top-of-file docstring for the (A) classical / (B)
# engineered distinction this codebase documents. All three constants below
# are this codebase's own tuning choices for the macro-cluster weighted-vote
# system (Stage 6 of the pipeline, "Cluster Aggregation & Final Macro
# Identity" in the engine's own docs), not values taken from a classical
# text -- Jaimini/Parashari sources describe career SIGNIFICATION (which
# houses/karakas point to which domains) but not a numeric vote-decay/cap
# scheme for aggregating ~20 ranked fields into 3-4 clusters, which is an
# information-retrieval-style ranking problem this codebase had to design
# its own solution for.
_CLUSTER_RANK_DECAY  = 0.8   # rank-1 counts fully; rank N counts 0.8^(N-1)
_CLUSTER_MEMBER_CAP  = 3     # only a cluster's top-3 members vote (breadth vs depth)
_CLUSTER_FLOOR_RATIO = 0.5   # a field scoring <50% of the top field's score doesn't vote

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


def field_display_name(row: Dict[str, Any]) -> str:
    return row.get("field_label") or row.get("field_id", "Unknown").replace("_", " ").title()


def cluster_display_name(cluster: str) -> str:
    return _CLUSTER_DISPLAY_LABELS.get(cluster, cluster)


def print_macro_cluster(row: Dict[str, Any]) -> str:
    fid = row.get("field_id", "")
    family = (row.get("career_family_label") or row.get("career_family") or "").lower()
    label = field_display_name(row).lower()
    domain = (row.get("domain") or "").lower()

    if fid in {
        "international_law", "civil_services", "public_policy", "international_relations",
        "political_science", "law_llb", "environmental_law", "corporate_law",
        "criminal_law", "intellectual_property_law",
    } or "law" in label or "governance" in label or "civil service" in label or "diplomacy" in label:
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
    } or domain in {"finance", "economics"}:
        return "Economics, Policy Analytics & Social Sciences"
    if "agri" in family or "agri" in label:
        return "Agriculture, Environment & Sustainability"
    return cluster_display_name(row.get("graph_cluster") or row.get("competency_label") or row.get("career_family_label") or row.get("domain") or "Other")


def cluster_strength_weighted(rank_row_pairs: List[Tuple[int, Dict[str, Any]]], top_score: float) -> float:
    votes = []
    for rank, row in rank_row_pairs:
        score = float(row.get("final_score", 0.0) or 0.0)
        if top_score > 0 and score < top_score * _CLUSTER_FLOOR_RATIO:
            continue
        votes.append((_CLUSTER_RANK_DECAY ** (rank - 1)) * score)
    votes.sort(reverse=True)
    return sum(votes[:_CLUSTER_MEMBER_CAP])


def top20_as_four_cluster_groups(results: List[Dict[str, Any]]) -> List[Tuple[str, List[Tuple[int, Dict[str, Any]]]]]:
    grouped: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    order: List[str] = []
    for rank, row in enumerate(results[:20], 1):
        cluster = print_macro_cluster(row)
        if cluster not in grouped:
            grouped[cluster] = []
            order.append(cluster)
        grouped[cluster].append((rank, row))
    top_score = float(results[0].get("final_score", 0.0) or 0.0) if results else 0.0
    ranked_groups = sorted(
        [(cluster, grouped[cluster]) for cluster in order],
        key=lambda item: (-cluster_strength_weighted(item[1], top_score), min(rank for rank, _ in item[1])),
    )
    if len(ranked_groups) <= 4:
        return ranked_groups
    groups = ranked_groups[:3]
    remainder: List[Tuple[int, Dict[str, Any]]] = []
    for _, rows in ranked_groups[3:]:
        remainder.extend(rows)
    remainder.sort(key=lambda item: item[0])
    groups.append(("Additional Top-20 Branches", remainder))
    return groups
