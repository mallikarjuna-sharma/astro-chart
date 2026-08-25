"""Step 9 convergence scoring — shared by both career engines.

GAP FIX (2026-08-17): implements the framework's literal Step 9 rule ---
"Cross-reference all layers (D1 houses + D10 + Jaimini AmK + KP sub-lords)
-- fields appearing consistently across 3+ methods rank highest;
single-method hits rank lower but still included for completeness" --
which neither engine previously implemented. Both engines instead blended
their methods continuously by weight, with disagreement-only diagnostics
(`method_agreement`/`method_conflict` in Field_Determination) but no
convergence-count signal reaching the ranked output.

Design (Phase A, per the design doc reviewed before implementation):
  - Group methods by shared evidentiary root using the EXISTING
    jyotish.evidence_integrity.METHOD_DEPENDENCY_GROUPS map, not raw method
    count -- this avoids over-counting D1-correlated methods (parashara,
    knrao, structural_patterns all share D1 lineage) as if they were
    independent confirmations, which a naive "9 methods, count how many
    exceed a bar" implementation would do.
  - A group "votes" for a field if its strongest constituent method's
    normalized (0-100) score clears a threshold. Uses the SAME 0-100
    normalization already produced by compute_field_method_bundle's
    method_normalized_scores, so no new normalization logic is introduced.
  - Convergence is surfaced as bounded post-blend multiplier (same pattern
    as D9/Yogini/dasha-longevity already wired into
    Field_Determination/field_methods/__init__.py) PLUS a structured,
    inspectable result object -- not a silent re-sort -- so the literal
    "rank fields by convergence, weighted score as tiebreak" behavior
    (Phase B / "strict mode") can be applied by a caller that has the full
    candidate list, without this module needing to know about all fields
    at once.
  - Job_Career's career_field_report_v2.py only tracks three named methods
    (K.N. Rao, KP, D10) rather than nine -- each is already an independent
    evidentiary layer, so `score_convergence_simple()` below handles that
    case directly without needing the dependency-group machinery.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from jyotish.evidence_integrity import METHOD_DEPENDENCY_GROUPS

_HIT_THRESHOLD_DEFAULT = 60.0  # normalized 0-100 scale; see module docstring
                                # re: this needs calibration against real
                                # chart output before being trusted blindly.

_CONVERGENCE_MULT_MIN = 1.00   # convergence only ever helps, never penalizes
                                # a field for having fewer confirming layers
                                # available (e.g. missing D60 due to birth-
                                # time uncertainty is not the field's fault).
_CONVERGENCE_MULT_MAX = 1.08

_TIER_BY_COUNT = {
    0: "NO_CONVERGENCE",
    1: "SINGLE_METHOD",
    2: "MODERATE_CONVERGENCE",
    3: "STRONG_CONVERGENCE",
}
_TIER_DEFAULT_4PLUS = "EXCEPTIONAL_CONVERGENCE"


def _tier_for_count(count: int) -> str:
    return _TIER_BY_COUNT.get(count, _TIER_DEFAULT_4PLUS if count >= 4 else "NO_CONVERGENCE")


def score_convergence(
    method_normalized_scores: Mapping[str, float],
    hit_threshold: float = _HIT_THRESHOLD_DEFAULT,
    dependency_groups: Mapping[str, Sequence[str]] | None = None,
) -> Dict[str, Any]:
    """Field_Determination path: group-based convergence over an arbitrary
    number of methods, using METHOD_DEPENDENCY_GROUPS (or a caller-supplied
    override) to collapse correlated methods into one vote per evidentiary
    layer.

    Returns:
        {
            "groups_hit": [...], "groups_evaluated": [...],
            "convergence_count": int, "convergence_tier": str,
            "multiplier": float in [1.00, 1.08],
            "group_scores": {group_id: strongest_normalized_score_in_group},
            "trace": [str],
        }
    """
    groups = dependency_groups if dependency_groups is not None else METHOD_DEPENDENCY_GROUPS

    groups_evaluated: List[str] = []
    groups_hit: List[str] = []
    group_scores: Dict[str, float] = {}

    for group_id, methods in groups.items():
        present_scores = [
            method_normalized_scores[m] for m in methods
            if m in method_normalized_scores and method_normalized_scores[m] is not None
        ]
        if not present_scores:
            continue  # method(s) for this group weren't computed for this chart/field
        groups_evaluated.append(group_id)
        strongest = max(present_scores)
        group_scores[group_id] = round(strongest, 2)
        if strongest >= hit_threshold:
            groups_hit.append(group_id)

    count = len(groups_hit)
    tier = _tier_for_count(count)

    # Multiplier: 0 or 1 hits -> neutral (1.00); each additional hit beyond
    # the first adds a bounded increment, capped at _CONVERGENCE_MULT_MAX.
    # This rewards "3+ methods agree" without ever penalizing a field for
    # having fewer available/qualifying groups -- consistent with the
    # framework's "still included for completeness" instruction for
    # single-method hits (they get 1.00x, not a penalty multiplier).
    bonus_per_extra_hit = 0.02
    multiplier = round(
        min(_CONVERGENCE_MULT_MAX, 1.00 + max(0, count - 1) * bonus_per_extra_hit), 4
    )

    trace = [
        f"{count}/{len(groups_evaluated)} evidentiary groups cleared the "
        f"{hit_threshold:.0f}/100 convergence bar "
        f"({', '.join(groups_hit) if groups_hit else 'none'}) -> {tier}, {multiplier}x."
    ]

    return {
        "groups_hit": groups_hit,
        "groups_evaluated": groups_evaluated,
        "convergence_count": count,
        "convergence_tier": tier,
        "multiplier": multiplier,
        "group_scores": group_scores,
        "trace": trace,
    }


def score_convergence_simple(
    method_scores: Mapping[str, float],
    hit_threshold: float = _HIT_THRESHOLD_DEFAULT,
) -> Dict[str, Any]:
    """Job_Career path: each supplied method (e.g. {"knrao": .., "kp": ..,
    "dashamsha": .., "jaimini": ..}) is already an independent evidentiary
    layer (no dependency-group collapsing needed, unlike Field_Determination's
    nine methods) -- so this is a direct threshold count over whatever
    methods are supplied, expecting normalized 0-100 scores.
    """
    groups_evaluated = [m for m, s in method_scores.items() if s is not None]
    groups_hit = [m for m in groups_evaluated if method_scores[m] >= hit_threshold]
    count = len(groups_hit)
    tier = _tier_for_count(count)
    bonus_per_extra_hit = 0.02
    multiplier = round(
        min(_CONVERGENCE_MULT_MAX, 1.00 + max(0, count - 1) * bonus_per_extra_hit), 4
    )
    trace = [
        f"{count}/{len(groups_evaluated)} methods cleared the {hit_threshold:.0f}/100 "
        f"convergence bar ({', '.join(groups_hit) if groups_hit else 'none'}) -> {tier}, {multiplier}x."
    ]
    return {
        "groups_hit": groups_hit,
        "groups_evaluated": groups_evaluated,
        "convergence_count": count,
        "convergence_tier": tier,
        "multiplier": multiplier,
        "group_scores": {m: round(method_scores[m], 2) for m in groups_evaluated},
        "trace": trace,
    }


def rank_by_strict_convergence(
    field_results: Sequence[Mapping[str, Any]],
    convergence_key: str = "convergence_count",
    score_key: str = "combined_score",
) -> List[Mapping[str, Any]]:
    """Phase B / 'strict framework mode': re-sort an already-scored candidate
    list so convergence_count is the PRIMARY sort key and the existing
    weighted-blend score is only the tiebreaker within each convergence
    tier -- the literal reading of "fields hit by 3+ methods rank highest."

    This is intentionally a separate, opt-in function rather than the
    default behavior wired into compute_field_method_bundle/
    _macro_cluster_ranking: it can materially reorder results relative to
    the existing (already-tuned) weighted blend, so per the design review
    it should be an explicit caller choice, not silently forced on.

    `field_results` must each be a mapping containing at least
    `convergence_key` and `score_key`. Does not mutate inputs; returns a new
    sorted list.
    """
    return sorted(
        field_results,
        key=lambda r: (-(r.get(convergence_key) or 0), -(r.get(score_key) or 0.0)),
    )
