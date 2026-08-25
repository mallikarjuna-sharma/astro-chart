"""Release 4 structural-vocation and analytical sensitivity diagnostics.

Gap-audit fix (2026-08, documentation-only cross-reference): see
field_suitability.py's module docstring for how this module relates to the
other two similarly-named modules in this package (field_suitability.py,
exact_field_defensibility.py). This module (STRUCTURAL_FIT_VERSION below)
is explicitly non-authoritative ("shadow") -- it does not feed the
user-facing route-suitability label, which lives in field_suitability.py.
"""
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
    time_interval = min(25.0, 100.0 * high_varga_share * time_factor * 0.35)

    # Fix B (2026-08 gap-audit, "fix all identified gaps" round): the interval
    # above only ever measures birth-time-precision sensitivity. Confirmed on
    # a live Ramsunder run that birth_time_uncertainty_minutes=0 and
    # precision="exact" collapses time_factor to 0.0, so every field reports
    # score_interval=[score, score] (ROBUST_EXACT_FIELD) regardless of how
    # much D1/D10/D24 actually disagree on that field -- meaningful_margins.py
    # then reads that zero-width interval and claims exact_ordering_claimed
    # even when the underlying methods disagree. broad_domain_promise.py
    # already computes exactly this disagreement (max-min across D1/D10/D24,
    # 0-100 scale) earlier in release_candidate.apply_release_4_7(), before
    # compute_structural_fit() runs, so it's available on the row here.
    # Folding it in widens the interval when methods disagree even with an
    # exact birth time, without touching final_score or rank (this function
    # only ever fed the shadow/non-authoritative sensitivity block).
    varga_disagreement = float((row.get("broad_domain_promise") or {}).get("disagreement", 0.0) or 0.0)
    disagreement_factor = min(1.0, varga_disagreement / 40.0)
    disagreement_interval = 100.0 * high_varga_share * disagreement_factor * 0.35
    # gap fix 2026-08-18 (item 11): using max(time_interval, disagreement_interval)
    # let a saturated cross-varga disagreement (disagreement_factor==1.0, i.e.
    # disagreement_interval already at its 14.0 ceiling for this weight config)
    # silently swallow ALL birth-time-uncertainty signal -- both 0-minute and
    # 10-minute uncertainty collapsed to the exact same interval_half_width
    # (14.0), violating this module's own documented contract that the interval
    # must widen with birth-time uncertainty (test_sensitivity_widens_with_
    # birth_time_uncertainty). Combining the two factors additively (still
    # capped at 25.0) preserves Fix B's intent -- disagreement alone still
    # widens the interval even with an exact birth time -- while restoring
    # monotonic widening as uncertainty grows on top of any disagreement.
    interval = min(25.0, time_interval + disagreement_interval)
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
            "cross_varga_disagreement": round(varga_disagreement, 4),
            "score_interval": [round(_clamp(score - interval), 4), round(_clamp(score + interval), 4)],
            "interval_half_width": round(interval, 4),
            "status": stability,
        },
    }

