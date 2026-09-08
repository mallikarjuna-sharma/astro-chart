"""Education / career analysis — UG field determination + PUC stream routing."""
from __future__ import annotations

from typing import Any

from api.ai_status import ai_status_from_ug_report
from api.llm_policy import prepare_chart_for_api_llm
from api.puc_analysis import default_education_tab
from jyotish_ug import (
    EducationAnalysisError,
    jsonable_copy,
    run_education_analysis as _run_education_analysis,
    run_ug_analysis as _run_ug_analysis,
)

__all__ = [
    "EducationAnalysisError",
    "default_education_tab",
    "jsonable_copy",
    "run_education_analysis",
    "run_ug_analysis",
]


def run_ug_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Apply API LLM prep, then delegate to the jyotish-ug-fields package."""
    chart = prepare_chart_for_api_llm(chart)
    result = _run_ug_analysis(chart)
    llm_meta = result.pop("llm_meta", {}) or {}
    result["AI"] = ai_status_from_ug_report(
        llm_attempted=bool(llm_meta.get("attempted")),
        llm_succeeded=bool(llm_meta.get("succeeded")),
        provider=str(llm_meta.get("provider") or ""),
        model=str(llm_meta.get("model") or ""),
        error_message=str(llm_meta.get("error_message") or ""),
    )
    return result


def run_education_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Back-compat alias for UG career-field analysis."""
    return run_ug_analysis(chart)
