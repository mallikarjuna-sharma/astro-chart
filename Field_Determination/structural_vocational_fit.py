"""Release 4 structural-vocation and analytical sensitivity diagnostics."""
from __future__ import annotations

from typing import Any, Mapping

STRUCTURAL_FIT_VERSION = "structural-vocational-fit.r4.shadow.v1"


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def compute_structural_fit(row: Mapping[str, Any], canonical_report: Mapping[str, Any]) -> dict:
    shadow = row.get("shadow_score_audit") or {}
    groups = ((shadow.get("dependency_reduction") or {}).get("groups") or {})
    group_scores = {key: float((value or {}).get("score", 0.0)) for key, value in groups.items()}
    contextual = _clamp(float(row.get("affinity_score", 0.0)))
    weights = {
        "d1_synthesis": 0.25,
        "d10_vocation": 0.30,
        "jaimini_identity": 0.15,
        "kp_corroboration": 0.10,
        "sudarshana_confirmation": 0.05,
        "contextual_affinity": 0.15,
    }
    values = {**group_scores, "contextual_affinity": contextual}
    score = _clamp(sum(values.get(key, 0.0) * weight for key, weight in weights.items()))

    facts = canonical_report.get("facts") or {}
    uncertainty = max(0, int(facts.get("birth_time_uncertainty_minutes", 0) or 0))
    precision = str(facts.get("birth_time_precision", "unknown"))
    high_varga_share = weights["d10_vocation"] + weights["kp_corroboration"]
    time_factor = min(1.0, uncertainty / 10.0)
    if precision != "exact":
        time_factor = max(time_factor, 0.35)
    interval = min(25.0, 100.0 * high_varga_share * time_factor * 0.35)
    stability = (
        "ROBUST_EXACT_FIELD" if interval <= 3
        else "ROBUST_FAMILY_ONLY" if interval <= 7
        else "MODERATELY_SENSITIVE" if interval <= 12
        else "HIGHLY_TIME_SENSITIVE"
    )
    return {
        "contract_version": STRUCTURAL_FIT_VERSION,
        "authoritative": False,
        "score": round(score, 4),
        "group_values": {key: round(values.get(key, 0.0), 4) for key in weights},
        "group_weights": weights,
        "sensitivity": {
            "method": "analytical-proxy-not-chart-rerun",
            "birth_time_uncertainty_minutes": uncertainty,
            "score_interval": [round(_clamp(score - interval), 4), round(_clamp(score + interval), 4)],
            "interval_half_width": round(interval, 4),
            "status": stability,
        },
    }

