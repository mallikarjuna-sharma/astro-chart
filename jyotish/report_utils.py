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
# Gap-audit fix (2026-08-19, chat session cluster-scoring audit): the
# original _CLUSTER_RANK_DECAY scheme decayed a member's vote by
# 0.8**(overall_rank-1) -- i.e. by how many OTHER clusters' fields happened
# to outrank it globally, not by how strong the field itself is. Because
# decay^0 == 1.0 always goes to whichever single field is #1 overall, any
# cluster that happens to own the #1 slot got a one-time multiplier no other
# cluster could match, even against a cluster with several members close
# behind it in score. Confirmed live on Ramsunder's chart
# (career_field_report_ramsunder_20260819_171712): Agriculture, Environment
# & Sustainability (2 members, best at rank 1) scored raw_strength=32.54 and
# "won" the macro-cluster board, while Engineering, Space & Physical Systems
# (6 members at ranks 3/7/8/9/11/14, each individually stronger on
# astrological_score -- 91.56/87.28/84.36 vs the agriculture cluster
# leader's 66.82) scored only 23.76 (73%) purely because its best member sat
# at rank 3, not rank 1, so it started at 0.8**2=0.64 before any other
# penalty. That is a presentation-layer artifact of vote-decay-by-rank, not
# an astrological finding.
#
# Fix: decay a member's vote by its OWN score relative to the batch's top
# score (self-referential, "how close is this field to the best field
# overall"), not by its ordinal rank among other clusters' fields. A field's
# vote no longer depends on which cluster its competitors happen to belong
# to. _CLUSTER_MEMBER_CAP is raised from 3 to 5 so clusters with genuine
# depth (several strong, non-#1 members) are no longer truncated as hard as
# a shallow 2-3 member cluster that happens to include the single top field.
_CLUSTER_SCORE_DECAY_EXPONENT = 1.0   # vote = score * (score/top_score) ** exponent
_CLUSTER_MEMBER_CAP  = 5     # a cluster's top-5 members vote (was 3; breadth vs depth)
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
    # `rank` (overall rank among the returned top-20) is intentionally UNUSED
    # in the vote weight itself now -- see the 2026-08-19 fix note above.
    # It's kept only as a tiebreaker for cluster display order in
    # top20_as_four_cluster_groups() below, not as a scoring input.
    votes = []
    for _rank, row in rank_row_pairs:
        score = float(row.get("final_score", 0.0) or 0.0)
        if top_score > 0 and score < top_score * _CLUSTER_FLOOR_RATIO:
            continue
        relative = (score / top_score) if top_score > 0 else 0.0
        votes.append((relative ** _CLUSTER_SCORE_DECAY_EXPONENT) * score)
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
