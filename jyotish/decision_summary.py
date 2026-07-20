"""Renderer-safe decision summary containing only deterministic claims."""
from __future__ import annotations

SUMMARY_VERSION = "decision-summary.r10.v1"


def attach_decision_summaries(rows: list[dict]) -> list[dict]:
    for row in rows:
        structural = row.get("structural_vocational_fit") or {}
        hierarchy = row.get("hierarchical_shadow") or {}
        defensibility = row.get("defensibility") or {}
        exact = row.get("exact_field_contract") or {}
        margin = row.get("meaningful_margin") or {}
        row["decision_summary"] = {
            "contract_version": SUMMARY_VERSION,
            "display_score_authoritative": row.get("final_score"),
            "permanent_shadow_score": structural.get("score"),
            "archetype": hierarchy.get("archetype_id"),
            "family": hierarchy.get("family_id"),
            "margin_tier": margin.get("tier"),
            "sensitivity": (structural.get("sensitivity") or {}).get("status"),
            "defensibility": defensibility.get("tier"),
            "exact_field_status": exact.get("status"),
            "limitations": sorted(set(
                list(defensibility.get("advisory_codes") or [])
                + list(exact.get("failure_codes") or [])
                + (["SHADOW_SCORE_NOT_PROMOTED"] if structural.get("authoritative") is False else [])
            )),
            "llm_may_reorder": False,
        }
    return rows

