"""Deterministic publication policy for coherent career-field rankings.

The astrological engine scores every registry branch independently.  That is
useful for discovery, but a published Top 20 also needs two invariants that an
independent scorer cannot provide by itself:

* a narrow specialization must not outrank its supported broad foundation;
* isolated symbolic matches must not overwhelm a clearly dominant career
  cluster.

This module applies bounded, auditable score adjustments only.  It never
splices a field into a fixed rank and always returns true score order.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


FIELD_ROLES = {
    "civil_services": "career_route",
    "research_academia": "career_context",
}

# Narrow branch -> broad educational foundation.  Only pairs present in the
# same candidate set are compared, so this cannot manufacture a recommendation.
SPECIALIZATION_PARENTS = {
    "space_materials": "materials_science_engineering",
    "space_systems_engineering": "aerospace_engineering",
    "space_sciences_engineering": "aerospace_engineering",
    "chemical_engineering_data_science": "chemical_engineering",
}

PHYSICAL_CLUSTERS = {
    "Advanced Engineering & Physical Systems",
    "Natural & Physical Sciences",
}

# Recurrent symbolic leakage when the chart is already anchored by several
# independent physical/materials branches.  These are not globally rejected;
# the discount activates only under the dominant-physical-profile gate.
PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE = {
    "history_archaeology",
    "computational_social_science",
    "healthcare_management",
    "environmental_law",
    "civil_services",
    "fisheries_science",
    "public_health",
    "journalism_media",
    "mass_communication",
    "gender_studies",
    "rural_management",
    "visual_communication",
    "hotel_hospitality_management",
}


def _cluster(row: Dict[str, Any]) -> str:
    return str(row.get("graph_cluster") or row.get("competency_label") or "")


def _dominant_physical_profile(rows: List[Dict[str, Any]]) -> bool:
    """Require breadth, score share and rank strength--not one lucky field."""
    head = rows[:10]
    physical = [r for r in head if _cluster(r) in PHYSICAL_CLUSTERS]
    if len(physical) < 3:
        return False
    total = sum(max(0.0, float(r.get("final_score", 0.0) or 0.0)) for r in head)
    physical_total = sum(max(0.0, float(r.get("final_score", 0.0) or 0.0)) for r in physical)
    return bool(total and physical_total / total >= 0.32 and any(r in physical for r in head[:3]))


def _append_adjustment(row: Dict[str, Any], note: str) -> None:
    row.setdefault("publication_ranking_adjustments", []).append(note)


_SHADOW_TOP_N = 20


def _shadow_position(row: Dict[str, Any]) -> int | None:
    margin = row.get("meaningful_margin") or {}
    pos = margin.get("shadow_position")
    try:
        return int(pos) if pos is not None else None
    except (TypeError, ValueError):
        return None


def _shadow_supports_top20(row: Dict[str, Any]) -> bool:
    """True when the engine's own independent shadow/meaningful-margin audit
    (attach_meaningful_margin_tiers, run earlier in apply_release_4_7 --
    before this function -- so it's already attached by the time this runs)
    places this field within the top-N band on its own, method-robustness
    evidence rather than the blended publication score.

    2026-07-19 audit gap fix: civil_services/research_academia were both
    blanket-discounted 0.90x and clamped below the Top 20 purely because of
    their field_role, with no check on whether the underlying chart evidence
    actually supported that demotion. Cross-checking a real chart found the
    two fields diverge sharply: civil_services' shadow_position was 4 (the
    independent audit thinks it's one of the strongest fields in the whole
    run) while research_academia's was 26 (the independent audit agrees it
    belongs outside the top 20). Blanket-discounting both identically was
    wrong for civil_services specifically. This exemption lets a field_role
    discount be skipped when the field's own shadow ranking already argues
    for a high placement, while still applying the discount by default when
    shadow evidence is missing, inconclusive, or itself agrees with the
    demotion (i.e. no exemption unless the evidence explicitly earns it).
    """
    pos = _shadow_position(row)
    return pos is not None and pos <= _SHADOW_TOP_N


def apply_publication_ranking_policy(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return annotated rows in honest descending publication-score order."""
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))))

    for row in out:
        fid = str(row.get("field_id", ""))
        row["field_role"] = FIELD_ROLES.get(fid, "educational_field")
        row["astrological_score"] = float(row.get("final_score", 0.0) or 0.0)

    if _dominant_physical_profile(out):
        for row in out:
            fid = str(row.get("field_id", ""))
            old = float(row.get("final_score", 0.0) or 0.0)
            if fid in PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE:
                factor = 0.48 if fid in {
                    "journalism_media", "mass_communication", "public_health",
                    "fisheries_science", "healthcare_management",
                } else 0.68
                row["final_score"] = round(old * factor, 4)
                _append_adjustment(
                    row,
                    "dominant_physical_profile: isolated cross-cluster symbolic match "
                    f"discounted {1.0-factor:.0%}",
                )

        # Re-evaluate the boundary after leakage is removed.  Otherwise a
        # strong physical field temporarily displaced by symbolic noise can
        # receive a preservation boost and leapfrog its natural peers.
        provisional = sorted(
            out,
            key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))),
        )
        for index, row in enumerate(provisional):
            old = float(row.get("final_score", 0.0) or 0.0)
            if index >= 10 and _cluster(row) in PHYSICAL_CLUSTERS and old >= 30:
                row["final_score"] = round(old * 1.05, 4)
                _append_adjustment(
                    row,
                    "dominant_physical_profile: supported lower-ranked physical/technical branch +5%",
                )

    by_id = {str(r.get("field_id", "")): r for r in out}
    for child_id, parent_id in SPECIALIZATION_PARENTS.items():
        child, parent = by_id.get(child_id), by_id.get(parent_id)
        if not child:
            continue
        child["field_role"] = "specialization"
        child["foundation_field_id"] = parent_id
        if not parent:
            _append_adjustment(
                child,
                f"taxonomy: specialization mapped to broad foundation {parent_id}",
            )
            continue
        child_score = float(child.get("final_score", 0.0) or 0.0)
        parent_score = float(parent.get("final_score", 0.0) or 0.0)
        if child_score >= parent_score and parent_score > 0:
            child["final_score"] = round(parent_score * 0.97, 4)
            _append_adjustment(
                child,
                f"broad_foundation_first: capped below {parent_id}; retain as specialization",
            )

    # Career routes and work contexts remain visible but cannot masquerade as
    # undergraduate fields.  A small bounded discount resolves close calls;
    # the role annotation is the primary semantic fix. Skip the discount when
    # the field's own shadow/meaningful-margin audit independently supports a
    # top-20 placement -- see _shadow_supports_top20 for why.
    for row in out:
        role = row.get("field_role")
        if role not in {"career_route", "career_context"}:
            continue
        if _shadow_supports_top20(row):
            _append_adjustment(
                row,
                f"field_role={role}: publication discount waived -- shadow audit "
                f"position {_shadow_position(row)} independently supports top-{_SHADOW_TOP_N} placement",
            )
            continue
        old = float(row.get("final_score", 0.0) or 0.0)
        row["final_score"] = round(old * 0.90, 4)
        _append_adjustment(row, f"field_role={role}: separated from degree-field ranking")

    # If the registry supplies at least twenty actual fields/specializations,
    # keep career routes and work contexts in the full result set but below
    # the published Top 20 boundary.  This fixes taxonomy without deletion.
    educational_scores = sorted(
        (
            float(r.get("final_score", 0.0) or 0.0)
            for r in out
            if r.get("field_role") in {"educational_field", "specialization"}
        ),
        reverse=True,
    )
    if len(educational_scores) >= 20:
        boundary = educational_scores[19]
        for row in out:
            if row.get("field_role") not in {"career_route", "career_context"}:
                continue
            if _shadow_supports_top20(row):
                continue
            score = float(row.get("final_score", 0.0) or 0.0)
            if score >= boundary:
                row["final_score"] = round(boundary * 0.97, 4)
                _append_adjustment(
                    row,
                    "field_type_boundary: retained outside degree-field Top 20",
                )

    out.sort(key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))))
    for rank, row in enumerate(out, 1):
        row["rank"] = rank
        row["publication_score"] = float(row.get("final_score", 0.0) or 0.0)
    return out
