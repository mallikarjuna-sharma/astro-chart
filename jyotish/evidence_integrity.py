"""Dependency reduction for Release 3 shadow scoring."""
from __future__ import annotations

from typing import Mapping

EVIDENCE_REDUCTION_VERSION = "evidence-reduction.v1-shadow"
SECONDARY_RESIDUAL_SHARE = 0.25
ADDITIONAL_RESIDUAL_SHARE = 0.10

METHOD_DEPENDENCY_GROUPS: dict[str, tuple[str, ...]] = {
    "d1_synthesis": ("parashara", "knrao"),
    "d10_vocation": ("dashamsha",),
    "kp_corroboration": ("kp",),
    "jaimini_identity": ("jaimini",),
    "sudarshana_confirmation": ("sudarshana",),
}


def reduce_correlated_values(values: Mapping[str, float]) -> dict:
    """Keep the strongest witness and only bounded residuals from siblings."""
    ordered = sorted(
        ((str(key), max(0.0, min(100.0, float(value)))) for key, value in values.items()),
        key=lambda item: (-item[1], item[0]),
    )
    if not ordered:
        return {"score": 0.0, "primary": None, "contributions": {}}
    contributions: dict[str, float] = {}
    for index, (key, value) in enumerate(ordered):
        share = 1.0 if index == 0 else SECONDARY_RESIDUAL_SHARE if index == 1 else ADDITIONAL_RESIDUAL_SHARE
        contributions[key] = value * share
    denominator = 1.0 + (SECONDARY_RESIDUAL_SHARE if len(ordered) > 1 else 0.0)
    denominator += ADDITIONAL_RESIDUAL_SHARE * max(0, len(ordered) - 2)
    return {
        "score": round(sum(contributions.values()) / denominator, 4),
        "primary": ordered[0][0],
        "contributions": {key: round(value, 4) for key, value in contributions.items()},
        "raw_values": {key: value for key, value in ordered},
    }


def reduce_method_evidence(method_scores: Mapping[str, float]) -> dict:
    groups = {}
    for group_id, methods in METHOD_DEPENDENCY_GROUPS.items():
        present = {method: method_scores[method] for method in methods if method in method_scores}
        groups[group_id] = reduce_correlated_values(present)
    return {"version": EVIDENCE_REDUCTION_VERSION, "groups": groups}


# Explicit fact lineage: methods sharing any of these roots are corroborating
# views, not independent observations. This graph is intentionally inspectable.
METHOD_SIGNAL_ROOTS: dict[str, tuple[str, ...]] = {
    "knrao": ("D1_PLANETS", "D1_LORDSHIPS", "D9", "D10", "KARAKAS"),
    "parashara": ("D1_PLANETS", "D1_LORDSHIPS", "DIGNITY", "D10", "YOGAS"),
    "dashamsha": ("D10", "D1_LORDSHIPS", "DIGNITY"),
    "jaimini": ("D1_PLANETS", "D9", "KARAKAS"),
    "kp": ("D1_PLANETS", "KP_CUSPS", "NAKSHATRA", "DASHA"),
    "sudarshana": ("D1_PLANETS", "D1_LORDSHIPS", "SUN_MOON_REFERENCE"),
}


def build_signal_lineage(method_scores: Mapping[str, float]) -> dict:
    present = [m for m in method_scores if m in METHOD_SIGNAL_ROOTS]
    roots = {m: list(METHOD_SIGNAL_ROOTS[m]) for m in present}
    edges = []
    for i, left in enumerate(present):
        for right in present[i + 1:]:
            shared = sorted(set(roots[left]) & set(roots[right]))
            if shared:
                edges.append({"from": left, "to": right, "shared_roots": shared})
    unique_roots = sorted({root for method in present for root in roots[method]})
    # Effective count is an audit diagnostic, not a fitted statistical quantity.
    effective = round(len(unique_roots) / max(len(METHOD_SIGNAL_ROOTS["knrao"]), 1), 2)
    return {
        "version": "signal-lineage.2026-07-18.v1",
        "method_roots": roots,
        "dependency_edges": edges,
        "unique_signal_roots": unique_roots,
        "effective_independent_method_count": min(float(len(present)), effective),
        "double_count_prevention": "PRIMARY_BLEND_CORRELATION_DAMPENING_PLUS_LINEAGE_AUDIT",
    }
