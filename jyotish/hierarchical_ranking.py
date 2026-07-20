"""Release 5 population calibration and hierarchical shadow ranking."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

HIERARCHY_VERSION = "hierarchical-ranking.r5.shadow.v1"

DOMAIN_ARCHETYPE = {
    "engineering": "material_physical_systems",
    "technology": "analytical_quantitative_systems",
    "science": "research_natural_systems",
    "medicine": "biological_care_healing",
    "law": "governance_law_public_authority",
    "public": "governance_law_public_authority",
    "commerce": "commerce_enterprise",
    "humanities": "communication_society_humanities",
    "media": "communication_media",
    "arts": "arts_design",
    "education": "education_scholarship",
    "agriculture": "agriculture_natural_systems",
    "interdisciplinary": "interdisciplinary_systems",
}


def _percentiles(values: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    n = len(ordered)
    if n <= 1:
        return {key: 50.0 for key, _ in ordered}
    return {key: round(index * 100.0 / (n - 1), 4) for index, (key, _) in enumerate(ordered)}


def attach_hierarchy(rows: list[dict]) -> list[dict]:
    source = [(str(row.get("field_id")), float((row.get("structural_vocational_fit") or {}).get("score", 0.0))) for row in rows]
    percentiles = _percentiles(source)
    family_scores: dict[str, list[float]] = defaultdict(list)
    archetype_scores: dict[str, list[float]] = defaultdict(list)
    identities = {}
    for row in rows:
        fid = str(row.get("field_id"))
        ontology = row.get("ontology_v12") or {}
        family = str(ontology.get("primary_family") or row.get("domain") or "unclassified")
        archetype = DOMAIN_ARCHETYPE.get(str(row.get("domain") or ""), "unclassified")
        score = percentiles[fid]
        identities[fid] = (family, archetype, score)
        family_scores[family].append(score)
        archetype_scores[archetype].append(score)
    family_mean = {key: sum(vals) / len(vals) for key, vals in family_scores.items()}
    archetype_mean = {key: sum(vals) / len(vals) for key, vals in archetype_scores.items()}
    family_rank = {key: idx + 1 for idx, (key, _) in enumerate(sorted(family_mean.items(), key=lambda x: (-x[1], x[0])))}
    archetype_rank = {key: idx + 1 for idx, (key, _) in enumerate(sorted(archetype_mean.items(), key=lambda x: (-x[1], x[0])))}
    for row in rows:
        fid = str(row.get("field_id")); family, archetype, score = identities[fid]
        row["hierarchical_shadow"] = {
            "contract_version": HIERARCHY_VERSION,
            "authoritative": False,
            "population_scope": "returned-candidate-pool",
            "calibrated_structural_percentile": score,
            "family_id": family,
            "family_score": round(family_mean[family], 4),
            "family_rank": family_rank[family],
            "archetype_id": archetype,
            "archetype_score": round(archetype_mean[archetype], 4),
            "archetype_rank": archetype_rank[archetype],
        }
    return rows

