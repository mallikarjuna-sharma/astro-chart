"""Release 6 defensibility annotations; never changes ranking."""
from __future__ import annotations

from typing import Any, Mapping

DEFENSIBILITY_VERSION = "defensibility.r6.annotation.v1"


def evaluate_defensibility(row: Mapping[str, Any], canonical_report: Mapping[str, Any]) -> dict:
    failures: list[str] = []
    advisories: list[str] = []
    hard_stop = not bool(canonical_report.get("ok", True))
    if hard_stop:
        failures.extend(str(item.get("code")) for item in canonical_report.get("errors", []))
    ontology = row.get("ontology_v12") or {}
    specificity = float(ontology.get("specificity_score", 0.0) or 0.0)
    if specificity < 0.55:
        advisories.append("LOW_ONTOLOGY_SPECIFICITY")
    shadow = row.get("shadow_score_audit") or {}
    undeclared = ((shadow.get("scope_partition") or {}).get("undeclared_signals") or [])
    if undeclared:
        advisories.append("UNDECLARED_SCORE_SIGNALS_PRESENT")
    structural = row.get("structural_vocational_fit") or {}
    sensitivity = (structural.get("sensitivity") or {}).get("status", "NOT_ASSESSED")
    if sensitivity in {"MODERATELY_SENSITIVE", "HIGHLY_TIME_SENSITIVE"}:
        advisories.append("BIRTH_TIME_SENSITIVE")
    method_groups = (((shadow.get("dependency_reduction") or {}).get("groups")) or {})
    supported = sum(float((group or {}).get("score", 0.0)) >= 50.0 for group in method_groups.values())
    if supported < 2:
        advisories.append("INSUFFICIENT_INDEPENDENT_METHOD_GROUPS")
    if hard_stop:
        tier = "HARD_STOP"
    elif not advisories and specificity >= 0.70 and supported >= 3:
        tier = "ESTABLISHED"
    elif specificity >= 0.55 and supported >= 2:
        tier = "SUPPORTED_PROVISIONAL"
    else:
        tier = "EXPLORATORY"
    return {
        "contract_version": DEFENSIBILITY_VERSION,
        "ranking_effect": "NONE",
        "tier": tier,
        "hard_stop": hard_stop,
        "failure_codes": failures,
        "advisory_codes": advisories,
        "specificity_score": specificity,
        "independent_supported_groups": supported,
        "sensitivity_status": sensitivity,
    }

