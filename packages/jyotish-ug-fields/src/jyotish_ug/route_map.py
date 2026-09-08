"""Field_Determination/route_map.py — deterministic Education Route Map
(overall summary / Route A-B-C cards / "avoid as primary") for the CLI's
Summary JSON output.

Ported (2026-09) from Job_Career/career_field_report_v2.py's deterministic
route-selection pipeline (`_select_headline_routes` / `_fallback_report_json`
/ `_apply_deterministic_suitability_to_report`'s avoid-as-primary logic) --
that module lives in a different checkout and is not available here (see
education_engine.py's own "Job_Career package not present in this checkout"
handling). This is a narrow, LLM-free port: only the pieces needed to
reproduce the "Summary" box + "Education route map" (Route A/B/C) +
"Avoid as primary" card the parent/student-facing HTML report shows are
brought over -- not the full 14-section report (astrological signature,
macro-cluster interpretations, engine gap audit, parent/student prose, etc.),
which stay out of scope for this JSON.

Every signal this module reads (`recommendation_assessment`,
`validated_recommendation_rank`, `registry_v12`/`education_realism`/`routes`/
`market`/`career_outcomes`) is produced by the same `annotate_field_suitability`
(Field_Determination/field_suitability.py) and course-registry helpers this
checkout already has -- this module just runs that same preprocessing step
that career_field_report_v2.py used to run before calling it, since
education_engine.py's plain run_engine() output never attaches it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from Field_Determination.field_suitability import (
    annotate_field_suitability,
    STATUS_PG,
    STATUS_EXPLORATORY,
    STATUS_NOT_PRIMARY,
    STATUS_REQUIRES_VALIDATION,
)
from jyotish.report_utils import field_display_name as _field_display_name
from jyotish.engine_io import _load_course_registry


# ── small helpers (ported verbatim from career_field_report_v2.py) ────────

def _row_field_id(row: Dict[str, Any]) -> str:
    return str(
        row.get("field_id") or row.get("branch_id") or row.get("id") or row.get("key") or ""
    )


def _v12_registry_slice(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "classic_core": meta.get("classic_core", {}),
        "modern_extensions": meta.get("modern_extensions", {}),
        "education_realism": meta.get("education_realism", {}),
        "curriculum": meta.get("curriculum", {}),
        "market": meta.get("market", {}),
        "risk": meta.get("risk", {}),
        "routes": meta.get("routes", {}),
        "career_outcomes": meta.get("career_outcomes", {}),
        "ontology": meta.get("ontology", {}),
        "admission_exams_canonical": meta.get("admission_exams_canonical", []),
        "available_at_normalized": meta.get("available_at_normalized", {}),
    }


def _row_section(row: Dict[str, Any], key: str) -> Dict[str, Any]:
    if not row:
        return {}
    rv12 = row.get("registry_v12", {}) or {}
    value = row.get(key) or rv12.get(key) or {}
    return value if isinstance(value, dict) else {}


def _registry_pg_program_label(row: Dict[str, Any]) -> str:
    routes = _row_section(row, "routes")
    ambitious = routes.get("ambitious_route") if isinstance(routes, dict) else {}
    pg_name = (ambitious or {}).get("pg") if isinstance(ambitious, dict) else ""
    if pg_name:
        return str(pg_name)
    label = _field_display_name(row)
    return f"{label} (PG specialization)" if label else ""


def _validated_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [r for r in rows if r.get("validated_recommendation_rank") is not None],
        key=lambda r: r["validated_recommendation_rank"],
    )


def _route_path(section: Dict[str, Any]) -> str:
    if isinstance(section.get("safe_route"), dict):
        return section["safe_route"].get("path", "")
    if isinstance(section.get("safe_route"), str):
        return section.get("safe_route", "")
    return ""


# ── headline UG/PG/backup/alt-backup selection (ported) ───────────────────

def _select_headline_routes(top20: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministically choose the UG / PG / backup / alternate-backup rows.
    Same rules as career_field_report_v2.py's _select_headline_routes(),
    minus the D24-divergence-alert bookkeeping (report-only diagnostic, not
    needed for the route map itself)."""
    top20 = top20 or []
    validated = _validated_rows(top20)

    def _status(row):
        return (row.get("recommendation_assessment") or {}).get("recommendation_status", "")

    def _label(r):
        return _field_display_name(r) if r else ""

    ug_row: Dict[str, Any] = {}
    for row in validated:
        if _status(row) != STATUS_NOT_PRIMARY:
            ug_row = row
            break
    if not ug_row:
        ug_row = validated[0] if validated else (top20[0] if top20 else {})
    primary_resolved = bool(validated)
    pg_row = ug_row
    excluded = {_label(ug_row)}

    backup_row: Dict[str, Any] = {}
    for row in validated[1:]:
        if _label(row) in excluded or _status(row) == STATUS_NOT_PRIMARY:
            continue
        backup_row = row
        break
    if not backup_row:
        for row in top20[1:]:
            if _label(row) in excluded:
                continue
            backup_row = row
            break
    excluded.add(_label(backup_row))

    _ALT_BACKUP_ASTRO_FLOOR = 35.0

    def _astro_alignment(row: Dict[str, Any]) -> float:
        try:
            return float(
                (row.get("recommendation_assessment") or {}).get("astrological_alignment", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            return 0.0

    alt_backup_row: Dict[str, Any] = {}
    for row in top20:
        if _label(row) in excluded or _status(row) == STATUS_NOT_PRIMARY:
            continue
        risk = str(_row_section(row, "education_realism").get("risk_level", "")).lower()
        if risk in {"low", "low-medium"} and _astro_alignment(row) >= _ALT_BACKUP_ASTRO_FLOOR:
            alt_backup_row = row
            break
    if not alt_backup_row:
        for row in top20:
            if _label(row) in excluded or _status(row) == STATUS_NOT_PRIMARY:
                continue
            risk = str(_row_section(row, "education_realism").get("risk_level", "")).lower()
            if risk in {"low", "low-medium"}:
                alt_backup_row = row
                break
    if not alt_backup_row:
        for row in top20:
            if _label(row) in excluded or _status(row) == STATUS_NOT_PRIMARY:
                continue
            alt_backup_row = row
            break

    return {
        "ug_row": ug_row,
        "pg_row": pg_row,
        "backup_row": backup_row,
        "alt_backup_row": alt_backup_row,
        "primary_resolved": primary_resolved,
        "ug_label": _label(ug_row),
        "pg_label": _registry_pg_program_label(ug_row),
        "backup_label": _label(backup_row),
        "alt_backup_label": _label(alt_backup_row),
    }


# ── education_routes (Route A/B/C cards) + snapshot + final_recommendation ─

def _build_education_routes(locked: Dict[str, Any]) -> List[Dict[str, Any]]:
    top1 = locked["ug_row"]
    top2 = locked["backup_row"] or {}
    pg_row = locked["pg_row"]
    alt_row = locked.get("alt_backup_row") or {}

    def label(r):
        return _field_display_name(r) if r else ""

    def sec(r, key):
        rv12 = r.get("registry_v12", {}) if r else {}
        return r.get(key) or rv12.get(key) or {}

    edu = sec(top1, "education_realism")
    routes = sec(top1, "routes")
    market = sec(top1, "market")
    outcomes = sec(top1, "career_outcomes")
    pg_routes = sec(pg_row, "routes")

    safe_route = _route_path(routes)
    pg_safe_route = _route_path(pg_routes) or safe_route
    pg_program = locked.get("pg_label") or _registry_pg_program_label(pg_row)

    backup_edu = sec(top2, "education_realism") if top2 else {}
    backup_market = sec(top2, "market") if top2 else {}
    backup_outcomes = sec(top2, "career_outcomes") if top2 else {}
    backup_outcome_core = backup_outcomes.get("core", []) if isinstance(backup_outcomes, dict) else []
    backup_routes = sec(top2, "routes") if top2 else {}
    backup_safe_route = _route_path(backup_routes)
    backup_pg_program = _registry_pg_program_label(top2) if top2 else ""

    alt_edu = sec(alt_row, "education_realism") if alt_row else {}
    alt_market = sec(alt_row, "market") if alt_row else {}
    alt_outcomes = sec(alt_row, "career_outcomes") if alt_row else {}
    alt_outcome_core = alt_outcomes.get("core", []) if isinstance(alt_outcomes, dict) else []
    alt_routes = sec(alt_row, "routes") if alt_row else {}
    alt_safe_route = _route_path(alt_routes)

    outcome_core = outcomes.get("core", []) if isinstance(outcomes, dict) else []

    return [
        {
            "route_name": "Route A - Next Education/Career Route",
            "title": label(top1),
            "ug_options": label(top1),
            "pg_options": f"{pg_program}: {pg_safe_route}" if pg_safe_route else pg_program,
            "phd_options": (
                f"Optional PhD extension of {pg_program} only if research orientation becomes strong."
                if pg_row else "Optional only if research orientation becomes strong."
            ),
            "careers": ", ".join(outcome_core[:5]),
            "best_for": "Students comfortable with physics, chemistry, mathematics, lab work, and engineering systems.",
            "risk_level": edu.get("risk_level", "Medium"),
            "long_term_value": market.get("india_2035_demand", "Medium") if isinstance(market, dict) else "Medium",
        },
        {
            "route_name": "Route B - Backup Route",
            "title": label(top2) or "",
            "ug_options": label(top2) or "",
            "pg_options": (
                f"{backup_pg_program}: {backup_safe_route}" if backup_pg_program and backup_safe_route
                else backup_pg_program
            ),
            "phd_options": (
                f"Optional PhD extension of {backup_pg_program} only if research orientation becomes strong."
                if backup_pg_program else "Optional only if research orientation becomes strong."
            ),
            "careers": ", ".join(backup_outcome_core[:5]),
            "best_for": (
                "Students who want a genuinely different, strongly-scoring alternative to the primary "
                "field — worth keeping seriously in view, not just a fallback."
            ),
            "risk_level": backup_edu.get("risk_level", "Medium"),
            "long_term_value": backup_market.get("india_2035_demand", "Medium") if isinstance(backup_market, dict) else "Medium",
        },
        {
            "route_name": "Route C - Safe Practical Backup",
            "title": label(alt_row) or label(top2) or "",
            "ug_options": label(alt_row) or label(top2) or "Broad UG foundation, decide specialization later",
            "pg_options": (
                f"{_registry_pg_program_label(alt_row)}: {alt_safe_route}" if alt_row and alt_safe_route
                else (_registry_pg_program_label(alt_row) if alt_row else "")
            ),
            "phd_options": "Optional only if research orientation becomes strong.",
            "careers": ", ".join(alt_outcome_core[:5]),
            "best_for": (
                "Students who want a lower-risk, well-trodden fallback distinct from the primary "
                "field, in case entrance rank, interest, or market conditions make Route A/B less practical."
            ),
            "risk_level": alt_edu.get("risk_level", "Low-Medium"),
            "long_term_value": alt_market.get("india_2035_demand", "Medium") if isinstance(alt_market, dict) else "Medium",
        },
    ]


def build_route_map_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the Summary JSON payload: overall summary + Route A/B/C map +
    avoid-as-primary, from the CLI's own already-scored `results` (ranks
    1..N, as published to the console table).

    This is a pure function -- it deep-copies nothing and mutates rows in
    place (attaching registry_v12/recommendation_assessment/
    validated_recommendation_rank, same as career_field_report_v2.py does),
    same as the rest of this CLI's *_summary/_reference/_audit.json export
    step already expects to run against enriched rows.
    """
    top20 = list(results[:20])

    registry_v12 = _load_course_registry()
    for row in top20:
        fid = _row_field_id(row)
        meta = registry_v12.get(fid, {}) if fid else {}
        row["registry_v12"] = _v12_registry_slice(meta)
        for key in ("education_realism", "curriculum", "market", "risk", "routes"):
            if not row.get(key) and isinstance(meta.get(key), dict):
                row[key] = meta[key]

    top20 = annotate_field_suitability(top20)

    locked = _select_headline_routes(top20)
    top1 = locked["ug_row"]
    top2 = locked["backup_row"] or {}
    primary_resolved = locked["primary_resolved"]
    pg_program = locked.get("pg_label") or _registry_pg_program_label(locked["pg_row"])

    def label(r):
        return _field_display_name(r) if r else ""

    final_recommendation = (
        f"Choose {label(top1)} as the validated main route, keep {label(top2)} as a practical backup, "
        f"and pursue {pg_program} as the PG/specialization direction."
        if primary_resolved else
        f"Treat {label(top1)} only as provisional astrological potential until the listed mandatory "
        "academic evidence is supplied."
    )

    true_avoid = [
        row for row in top20
        if (row.get("recommendation_assessment") or {}).get("recommendation_status") == STATUS_NOT_PRIMARY
    ]
    if true_avoid:
        avoid_names = ", ".join(label(r) for r in true_avoid)
        avoid_as_primary = (
            f"{avoid_names} — not recommended as a primary route (independent adverse evidence in "
            f"two or more suitability dimensions). PG-dependent and exploratory fields are listed "
            f"separately and are not avoided."
        )
    else:
        avoid_as_primary = (
            "No field in the top 20 shows multi-dimensional adverse evidence; "
            "PG-dependent and exploratory routes are listed separately below."
        )

    return {
        "summary": final_recommendation,
        "education_routes": _build_education_routes(locked),
        "avoid_as_primary": avoid_as_primary,
    }
