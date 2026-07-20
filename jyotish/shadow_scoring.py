"""Release 2/3 non-authoritative score axes and permanent shadow score."""
from __future__ import annotations

from typing import Any, Mapping

from .evidence_integrity import reduce_method_evidence
from .score_scope import ScoreScope, scope_for

SHADOW_SCORE_VERSION = "shadow-score.r3.v1"
_GROUP_WEIGHTS = {
    "d1_synthesis": 0.30,
    "d10_vocation": 0.30,
    "kp_corroboration": 0.15,
    "jaimini_identity": 0.15,
    "sudarshana_confirmation": 0.10,
}


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _axis_from_deltas(items: Mapping[str, float], baseline: float = 50.0) -> float:
    # Legacy gap items are fractional multipliers. Shadow axes expose their
    # direction on a bounded diagnostic scale without affecting rank.
    return round(_clamp(baseline + 100.0 * sum(float(v) for v in items.values())), 4)


def partition_gap_signals(gap_breakdown: Mapping[str, Any]) -> dict:
    buckets = {scope.value: {} for scope in ScoreScope}
    undeclared: list[str] = []
    for signal_id, value in (gap_breakdown or {}).items():
        if not isinstance(value, (int, float)) or signal_id.startswith("_"):
            continue
        try:
            scope = scope_for(signal_id)
        except KeyError:
            undeclared.append(signal_id)
            continue
        buckets[scope.value][signal_id] = float(value)
    return {"buckets": buckets, "undeclared_signals": sorted(undeclared)}


def build_shadow_scores(row: Mapping[str, Any]) -> dict:
    methods = {
        str(key): float(value)
        for key, value in (
            row.get("method_normalized_scores")
            or row.get("method_scores_normalized_0_100")
            or row.get("method_scores_normalized")
            or {}
        ).items()
        if isinstance(value, (int, float))
    }
    reduction = reduce_method_evidence(methods)
    groups = reduction["groups"]
    permanent = sum(
        groups[group_id]["score"] * weight
        for group_id, weight in _GROUP_WEIGHTS.items()
    )
    partition = partition_gap_signals(row.get("gap_breakdown") or {})
    buckets = partition["buckets"]
    axes = {
        "permanent_astro_fit_shadow": round(_clamp(permanent), 4),
        "current_activation_score": _axis_from_deltas(buckets[ScoreScope.TIMING.value]),
        "educational_suitability_shadow": _axis_from_deltas(buckets[ScoreScope.EDUCATION.value]),
        "preference_alignment_shadow": _axis_from_deltas(buckets[ScoreScope.PREFERENCE.value]),
        "practical_feasibility_shadow": _axis_from_deltas(buckets[ScoreScope.PRACTICAL.value]),
    }
    return {
        "contract_version": SHADOW_SCORE_VERSION,
        "authoritative": False,
        "ranking_effect": "NONE",
        "axes": axes,
        "dependency_reduction": reduction,
        "scope_partition": partition,
        "permanent_group_weights": dict(_GROUP_WEIGHTS),
    }


def attach_shadow_scores(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["shadow_score_audit"] = build_shadow_scores(row)
    return rows
