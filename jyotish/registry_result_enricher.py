"""Attach v12 registry metadata to engine result rows.

This module is intentionally small and side-effect-free:
- It does not change scores.
- It does not change ranks.
- It only enriches result rows for JSON/debug/report output.
"""

from __future__ import annotations

from typing import Any, Dict, List


V12_KEYS = (
    "classic_core",
    "modern_extensions",
    "education_realism",
    "curriculum",
    "market",
    "risk",
    "routes",
    "career_outcomes",
    "ontology",
    "admission_exams_canonical",
    "available_at_normalized",
)


def _field_id(row: Dict[str, Any]) -> str:
    return str(
        row.get("field_id")
        or row.get("branch_id")
        or row.get("id")
        or row.get("key")
        or ""
    )


def attach_v12_registry_metadata(
    results: List[Dict[str, Any]],
    registry: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Attach full v12 metadata to each result row without touching score/order."""
    for row in results:
        fid = _field_id(row)
        meta = registry.get(fid, {}) if fid else {}

        # Preserve legacy registry in row["registry"] for older renderers.
        legacy = row.get("registry", {}) or {}
        row["registry_legacy"] = legacy

        # Canonical v12 block for all new output/report code.
        row["registry_v12"] = {k: meta.get(k, {} if k != "admission_exams_canonical" else []) for k in V12_KEYS}

        # Convenience flattened aliases for report/JSON visibility.
        row["education_realism"] = meta.get("education_realism", {})
        row["curriculum"] = meta.get("curriculum", {})
        row["market"] = meta.get("market", {})
        row["risk"] = meta.get("risk", {})
        row["routes"] = meta.get("routes", {})
        row["career_outcomes"] = meta.get("career_outcomes", {})
        row["ontology_v12"] = meta.get("ontology", {})
        row["admission_exams_canonical"] = meta.get("admission_exams_canonical", [])
        row["available_at_normalized"] = meta.get("available_at_normalized", {})

    return results