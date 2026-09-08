"""PUC stream determination — Science / Commerce / Humanities for school-age charts."""
from __future__ import annotations

from typing import Any

from api.ai_status import ai_status_from_stream_narrative
from api.llm_policy import API_LLM_NARRATIVE_ENABLED, API_LLM_RUNTIME_CONSENT, prepare_chart_for_api_llm
from jyotish_puc import (
    PUC_DEFAULT_AGE_FLOORS,
    PUC_MAX_AGE_EXCLUSIVE,
    PucAnalysisError,
    default_education_tab,
    is_puc_eligible,
    puc_age_error_message,
    run_puc_analysis as _run_puc_analysis,
)

__all__ = [
    "PUC_DEFAULT_AGE_FLOORS",
    "PUC_MAX_AGE_EXCLUSIVE",
    "PucAnalysisError",
    "default_education_tab",
    "is_puc_eligible",
    "puc_age_error_message",
    "run_puc_analysis",
]


def run_puc_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Apply API LLM policy, then delegate to the jyotish-puc-streams package."""
    chart = prepare_chart_for_api_llm(chart)
    result = _run_puc_analysis(
        chart,
        llm_enabled=API_LLM_NARRATIVE_ENABLED,
        llm_runtime_consent=API_LLM_RUNTIME_CONSENT,
    )
    result["AI"] = ai_status_from_stream_narrative(result.get("stream_narrative"))
    return result
