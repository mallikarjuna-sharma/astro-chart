"""Education / career analysis — JyotishAI deterministic engine + career field report v2."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from jyotish.career_field_report_v2 import build_career_field_report_from_chart
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


def _summary_from_report(report: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    fi = report.get("final_identity", {}) or {}
    return {
        "parent_overview": report.get("parent_summary", ""),
        "astro_overview": fi.get("one_line_summary", ""),
        "active_dasha_lord": bundle.get("active_lord", ""),
        "peak_career_dasha": bundle.get("peak_lord", ""),
        "macro_identity": fi.get("macro_identity", ""),
        "confidence": fi.get("confidence", ""),
        "career_phase": bundle.get("career_phase", ""),
    }


def _report_payload(
    results: list[dict[str, Any]],
    payload: NatalPayloadV2,
    narrative: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """JSON bundle sufficient to display the career field report (no HTML)."""
    sorted_results = sorted(results, key=lambda x: (-x["final_score"], x["field_id"]))
    match_fields = [
        r for r in sorted_results
        if r.get("llm_group", "match") != "soul" and 1 <= r.get("llm_rank", 99) <= 5
    ]
    soul_fields = [r for r in sorted_results if r.get("llm_group") == "soul"]
    career_field_report = {
        "narrative": narrative,
        "macro_clusters": bundle.get("macro_clusters", []),
        "chart_facts": bundle.get("chart_facts", {}),
        "career_phase": bundle.get("career_phase", ""),
        "active_lord": bundle.get("active_lord", ""),
        "peak_lord": bundle.get("peak_lord", ""),
    }
    return {
        "student": _student_summary(payload),
        "summary": _summary_from_report(narrative, bundle),
        "top_match_field_ids": [r["field_id"] for r in match_fields],
        "soul_field_id": soul_fields[0]["field_id"] if soul_fields else None,
        "fields": sorted_results,
        "payload": payload.model_dump(),
        "career_field_report": career_field_report,
    }


def run_education_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Parse chart JSON, run the career engine, and return the JSON report payloads.

    No HTML is produced or returned — the client renders the report from the four
    JSON payloads (results / macro_clusters / report / chart_facts) with React
    components.
    """
    if not _llm_configured():
        raise EducationAnalysisError(
            "No LLM API key configured. Set GEMINI_API_KEY (or OPENAI_API_KEY / "
            "ANTHROPIC_API_KEY) in .env before calling /api/education-analysis."
        )

    bundle = build_career_field_report_from_chart(chart, render_html=False)
    payload = bundle["payload"]
    results = bundle.get("results") or []
    if not results:
        raise EducationAnalysisError("Engine returned no career field results.")

    narrative = bundle.get("report") or {}
    generated_at = datetime.now(timezone.utc).isoformat()

    career_field_report = {
        "narrative": narrative,
        "macro_clusters": bundle.get("macro_clusters", []),
        "chart_facts": bundle.get("chart_facts", {}),
        "career_phase": bundle.get("career_phase", ""),
        "active_lord": bundle.get("active_lord", ""),
        "peak_lord": bundle.get("peak_lord", ""),
    }

    report_bundle = _report_payload(results, payload, narrative, bundle)

    return {
        "engine_version": ENGINE_VERSION,
        "generated_at": generated_at,
        "student": _student_summary(payload),
        "summary": _summary_from_report(narrative, bundle),
        # --- frozen html-payload-contract v1: the four LLM/report payloads,
        # exposed as top-level keys with their contract names (see
        # Job_Career/html_payload_contract.py in the LLM engine repo). ---
        "results": results,                                # payload 1
        "macro_clusters": bundle.get("macro_clusters", []),  # payload 2
        "report": narrative,                               # payload 3 (14-section narrative)
        "chart_facts": bundle.get("chart_facts", {}),      # payload 4
        # --- back-compat / convenience ---
        "fields": results,                                 # alias of `results`
        "report_bundle": report_bundle,                    # structured bundle (prev. `report`)
        "career_field_report": career_field_report,
    }
