"""Population-aware exact-field and sibling distinction contract.

Gap-audit fix (2026-08, documentation-only cross-reference): see
field_suitability.py's module docstring for how this module relates to the
other two similarly-named modules in this package (field_suitability.py,
structural_vocational_fit.py). This module (EXACT_FIELD_CONTRACT_VERSION
below) is non-authoritative -- it does not feed the user-facing
route-suitability label, which lives in field_suitability.py.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping

EXACT_FIELD_CONTRACT_VERSION = "exact-field-defensibility.r9.v1"


def _signature(row: Mapping[str, Any]) -> str:
    curriculum = row.get("curriculum") or {}
    ontology = row.get("ontology_v12") or {}
    value = {
        "curriculum": curriculum,
        "family": ontology.get("primary_family"),
        "specificity": ontology.get("specificity_score"),
        "field_id": row.get("field_id"),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def attach_exact_field_contract(rows: list[dict]) -> list[dict]:
    families: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        family = str((row.get("ontology_v12") or {}).get("primary_family") or row.get("domain") or "unclassified")
        families[family].append(row)
    for family, siblings in families.items():
        signatures = {_signature(row) for row in siblings}
        unique = len(signatures) == len(siblings)
        for row in siblings:
            base = row.get("defensibility") or {}
            margin = row.get("meaningful_margin") or {}
            failures = []
            if not unique and len(siblings) > 1:
                failures.append("SIBLING_IDENTITY_NOT_UNIQUE")
            if not margin.get("exact_ordering_claimed", False) and len(siblings) > 1:
                failures.append("SIBLING_MARGIN_NOT_MEANINGFUL")
            if base.get("tier") not in {"ESTABLISHED", "SUPPORTED_PROVISIONAL"}:
                failures.append("BASE_DEFENSIBILITY_INSUFFICIENT")
            row["exact_field_contract"] = {
                "contract_version": EXACT_FIELD_CONTRACT_VERSION,
                "family_id": family,
                "sibling_count": len(siblings),
                "identity_signature_sha256": _signature(row),
                "sibling_signatures_unique": unique,
                "exact_field_established": not failures and base.get("tier") == "ESTABLISHED",
                "status": "ESTABLISHED" if not failures and base.get("tier") == "ESTABLISHED" else "PROVISIONAL" if not failures else "EXPLORATORY",
                "failure_codes": failures,
                "external_review_status": "NOT_SUPPLIED",
            }
    return rows

