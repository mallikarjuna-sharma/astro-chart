"""Education / career analysis — UG field determination + PUC stream routing."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from Job_Career.career_field_report_v2 import build_career_field_report_from_chart
from api.ai_status import ai_status_from_ug_report
from api.llm_policy import prepare_chart_for_api_llm
from api.puc_analysis import default_education_tab
from jyotish.payload import ENGINE_VERSION, NatalPayloadV2


class EducationAnalysisError(RuntimeError):
    """Raised when education analysis cannot complete."""


def jsonable_copy(value: Any) -> Any:
    """Return a JSON-tree copy with no shared object identities.

    Pydantic v2 ``dump_json`` raises ``Circular reference detected (id repeated)``
    when the same dict/list appears twice in the response (e.g. ``results`` and
    ``fields`` aliasing one list). ``json.dumps`` allows that aliasing; round-
    tripping produces distinct objects so FastAPI can serialize the response.
    """

    def _default(obj: Any) -> Any:
        if hasattr(obj, "model_dump") and callable(obj.model_dump):
            return obj.model_dump()
        if hasattr(obj, "item") and callable(obj.item) and not isinstance(obj, (bytes, str)):
            try:
                return obj.item()
            except Exception:  # noqa: BLE001
                pass
        if hasattr(obj, "tolist") and callable(obj.tolist):
            return obj.tolist()
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        return str(obj)

    return json.loads(json.dumps(value, default=_default, ensure_ascii=False))


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
    if not match_fields:
        match_fields = [r for r in sorted_results if r.get("llm_group") != "soul"][:5]
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
        # Full NatalPayload dump is multi-MB and reuses nested objects that
        # Pydantic then refuses to serialize. Keep only what the UG report UI reads.
        "payload": {
            "corporate_entrepreneurial": getattr(payload, "corporate_entrepreneurial", None),
            "chart_type": getattr(payload, "chart_type", None),
        },
        "career_field_report": career_field_report,
    }


def run_ug_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Parse chart JSON, run the UG career-field engine, return JSON report payloads."""
    chart = prepare_chart_for_api_llm(chart)
    bundle = build_career_field_report_from_chart(chart, render_html=False, force_llm_report=True)
    payload = bundle["payload"]
    results = bundle.get("results") or []
    if not results:
        raise EducationAnalysisError("Engine returned no career field results.")

    narrative = bundle.get("report") or {}
    generated_at = datetime.now(timezone.utc).isoformat()
    llm_meta = bundle.get("llm_meta") or {}

    career_field_report = {
        "narrative": narrative,
        "macro_clusters": bundle.get("macro_clusters", []),
        "chart_facts": bundle.get("chart_facts", {}),
        "career_phase": bundle.get("career_phase", ""),
        "active_lord": bundle.get("active_lord", ""),
        "peak_lord": bundle.get("peak_lord", ""),
    }

    report_bundle = _report_payload(results, payload, narrative, bundle)

    return jsonable_copy(
        {
            "analysis_type": "ug",
            "engine_version": ENGINE_VERSION,
            "generated_at": generated_at,
            "default_tab": default_education_tab(payload.current_age),
            "student": _student_summary(payload),
            "summary": _summary_from_report(narrative, bundle),
            "results": results,
            "macro_clusters": bundle.get("macro_clusters", []),
            "report": narrative,
            "chart_facts": bundle.get("chart_facts", {}),
            "fields": results,
            "report_bundle": report_bundle,
            "career_field_report": career_field_report,
            "AI": ai_status_from_ug_report(
                llm_attempted=bool(llm_meta.get("attempted")),
                llm_succeeded=bool(llm_meta.get("succeeded")),
                provider=str(llm_meta.get("provider") or ""),
                model=str(llm_meta.get("model") or ""),
                error_message=str(llm_meta.get("error_message") or ""),
            ),
        }
    )


def run_education_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Back-compat alias for UG career-field analysis."""
    return run_ug_analysis(chart)
