"""Education / career analysis — JyotishAI deterministic engine + LLM field selection."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from jyotish.astro import _get_active_dasha_lord
from jyotish.engine import run_engine
from jyotish.engine_io import parse_json_payload
from jyotish.payload import ENGINE_VERSION, NatalPayloadV2


class EducationAnalysisError(RuntimeError):
    """Raised when education analysis cannot complete."""


def _llm_configured() -> bool:
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if (os.getenv(var) or "").strip():
            return True
    return False


def _student_summary(payload: NatalPayloadV2) -> dict[str, Any]:
    return {
        "name": payload.name,
        "dob": payload.dob,
        "birth_place": payload.birth_place,
        "gender": payload.gender,
        "current_age": payload.current_age,
        "lagna_sign": payload.lagna_sign,
        "lagna_lord": payload.lagna_lord,
        "atmakaraka": payload.atmakaraka,
        "amatyakaraka": payload.amatyakaraka,
        "h10_lord": payload.h10_lord,
        "karakamsha": payload.karakamsha,
        "yogas": payload.detected_yogas,
        "school_board": payload.school_board,
        "risk_appetite": payload.risk_appetite,
    }


def _summary_from_results(results: list[dict[str, Any]], payload: NatalPayloadV2) -> dict[str, Any]:
    first = results[0] if results else {}
    active_lord = _get_active_dasha_lord(
        getattr(payload, "dasha_sequence", []),
        float(getattr(payload, "current_age", 0)),
    )
    return {
        "parent_overview": first.get("llm_parent_summary", ""),
        "astro_overview": first.get("llm_selection_rationale", ""),
        "active_dasha_lord": active_lord or "",
    }


def _report_payload(
    results: list[dict[str, Any]],
    payload: NatalPayloadV2,
) -> dict[str, Any]:
    """JSON bundle sufficient to rebuild the HTML report."""
    sorted_results = sorted(results, key=lambda x: (-x["final_score"], x["field_id"]))
    match_fields = [
        r for r in sorted_results
        if r.get("llm_group", "match") != "soul" and 1 <= r.get("llm_rank", 99) <= 5
    ]
    soul_fields = [r for r in sorted_results if r.get("llm_group") == "soul"]
    return {
        "student": _student_summary(payload),
        "summary": _summary_from_results(results, payload),
        "top_match_field_ids": [r["field_id"] for r in match_fields],
        "soul_field_id": soul_fields[0]["field_id"] if soul_fields else None,
        "fields": sorted_results,
        "payload": payload.model_dump(),
    }


def run_education_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Parse chart JSON, run the career engine, and return structured report JSON."""
    if not _llm_configured():
        raise EducationAnalysisError(
            "No LLM API key configured. Set GEMINI_API_KEY (or OPENAI_API_KEY / "
            "ANTHROPIC_API_KEY) in .env before calling /api/education-analysis."
        )

    payload = parse_json_payload(chart)
    results = run_engine(payload)
    if not results:
        raise EducationAnalysisError("Engine returned no career field results.")

    generated_at = datetime.now(timezone.utc).isoformat()
    report = _report_payload(results, payload)

    return {
        "engine_version": ENGINE_VERSION,
        "generated_at": generated_at,
        "student": _student_summary(payload),
        "summary": _summary_from_results(results, payload),
        "fields": results,
        "report": report,
    }
