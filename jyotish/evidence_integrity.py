"""Dependency reduction for Release 3 shadow scoring."""
from __future__ import annotations

from typing import Mapping

EVIDENCE_REDUCTION_VERSION = "evidence-reduction.v1-shadow"
SECONDARY_RESIDUAL_SHARE = 0.25
ADDITIONAL_RESIDUAL_SHARE = 0.10

METHOD_DEPENDENCY_GROUPS: dict[str, tuple[str, ...]] = {
    # 2026-08-18 fix (audit item #10): Jaimini reads chara-karaka placements
    # derived directly from the natal D1 (Rasi) chart -- the same underlying
    # data source Parashara's yoga/strength model and K.N. Rao's whole-sign+
    # karaka-role hierarchy read, and the same one structural_patterns' D1
    # house-occupancy clustering reads. It was previously left out of
    # d1_synthesis in its own "jaimini_identity" singleton group below, which
    # meant it accumulated full independent weight in the primary blend's
    # correlation dampening (_CORRELATION_GROUP_DAMPENING in
    # field_methods/__init__.py) even though it is not truly an independent
    # witness of D1 facts. Folding it into d1_synthesis applies the exact
    # same bounded dampening already used for parashara/knrao/
    # structural_patterns. jaimini_identity below is left in place
    # (now a redundant singleton once jaimini is a d1_synthesis member) so
    # any code keying off that group id by name is unaffected.
    "d1_synthesis": ("parashara", "knrao", "structural_patterns", "jaimini"),
    "d10_vocation": ("dashamsha",),
    "kp_corroboration": ("kp",),
    "jaimini_identity": ("jaimini",),
    "sudarshana_confirmation": ("sudarshana",),
    # GAP FIX (2026-08-17): siddhamsha (D24) and shashtiamsha (D60) were
    # absent from this map entirely -- meaning their votes were invisible to
    # build_signal_lineage()'s effective_independent_method_count AND, more
    # importantly, to the new Step-9 convergence scoring in
    # field_methods/__init__.py's compute_field_convergence(), which groups
    # by this dict. Each is its own distinct varga/technique, not a sibling
    # of any existing group, so each gets its own singleton group (same
    # treatment as d10_vocation/kp_corroboration/jaimini_identity above).
    # structural_patterns joins d1_synthesis above (D1 house-occupancy
    # clustering shares the same D1_PLANETS/D1_LORDSHIPS root as
    # parashara/knrao per METHOD_SIGNAL_ROOTS below).
    "d24_specialization": ("siddhamsha",),
    "d60_confirmation": ("shashtiamsha",),
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
    # GAP FIX (2026-08-17): added so these three methods are visible to
    # build_signal_lineage() and to Step-9 convergence grouping (see
    # METHOD_DEPENDENCY_GROUPS above) -- previously absent entirely.
    "structural_patterns": ("D1_PLANETS", "D1_LORDSHIPS"),
    "siddhamsha": ("D24", "D1_LORDSHIPS", "DIGNITY"),
    "shashtiamsha": ("D60", "D1_LORDSHIPS", "DIGNITY"),
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
