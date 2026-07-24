"""PUC stream determination — Science / Commerce / Humanities for school-age charts."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from api.ai_status import ai_status_from_stream_narrative
from api.llm_policy import prepare_chart_for_api_llm
from jyotish.engine_io import parse_json_payload
from jyotish.payload import ENGINE_VERSION
from Stream_Determination.cross_validate import safe_cross_validate
from Stream_Determination.early_age_stream_engine import DEFAULT_INCLUDE_CROSS_VALIDATION
from Stream_Determination.stream_narrative import generate_stream_narrative
from Stream_Determination.stream_report import build_report_payload
from Stream_Determination.stream_scoring import AGE_THRESHOLD_YEARS, compute_stream_determination


class PucAnalysisError(RuntimeError):
    """Raised when PUC stream analysis cannot complete."""


PUC_DEFAULT_AGE_FLOORS = {15, 16, 17}
PUC_MAX_AGE_EXCLUSIVE = 18.0


def _floor_age(current_age: Any) -> int | None:
    try:
        return int(float(current_age))
    except (TypeError, ValueError):
        return None


def default_education_tab(current_age: Any) -> str:
    """Return ``puc`` for ages 15–17, otherwise ``ug``."""
    floor = _floor_age(current_age)
    if floor in PUC_DEFAULT_AGE_FLOORS:
        return "puc"
    return "ug"


def is_puc_eligible(current_age: Any) -> bool:
    """PUC API accepts charts under 18 or with integer age 15/16/17."""
    try:
        age = float(current_age)
    except (TypeError, ValueError):
        return False
    if age <= 0:
        return False
    floor = int(age)
    if floor in PUC_DEFAULT_AGE_FLOORS:
        return True
    return age < AGE_THRESHOLD_YEARS


def _student_summary(payload: Any) -> dict[str, Any]:
    return {
        "name": getattr(payload, "name", None),
        "dob": getattr(payload, "dob", None),
        "birth_place": getattr(payload, "birth_place", None),
        "gender": getattr(payload, "gender", None),
        "current_age": getattr(payload, "current_age", None),
        "lagna_sign": getattr(payload, "lagna_sign", None),
        "lagna_lord": getattr(payload, "lagna_lord", None),
        "atmakaraka": getattr(payload, "atmakaraka", None),
        "amatyakaraka": getattr(payload, "amatyakaraka", None),
        "school_board": getattr(payload, "school_board", None),
    }


def run_puc_analysis(chart: dict[str, Any]) -> dict[str, Any]:
    """Score PUC stream direction from consolidated chart JSON.

    Always uses ``forced_override=False`` — charts outside the normal under-15
    scope are rejected rather than scored as test-only overrides.
    """
    chart = prepare_chart_for_api_llm(chart)
    payload = parse_json_payload(chart)
    current_age = getattr(payload, "current_age", None)

    if not is_puc_eligible(current_age):
        raise PucAnalysisError(
            f"PUC stream analysis is for students under {int(PUC_MAX_AGE_EXCLUSIVE)} "
            f"(or ages 15–17). This chart's current_age is {current_age!r}."
        )

    determination = compute_stream_determination(payload)

    cross_validation = None
    if DEFAULT_INCLUDE_CROSS_VALIDATION:
        cross_validation = safe_cross_validate(payload, precomputed_determination=determination)

    stream_narrative = generate_stream_narrative(
        payload,
        determination,
        api_mode=True,
    )

    report = build_report_payload(
        payload,
        determination,
        forced_override=False,
        eligibility_status="NORMAL",
        cross_validation=cross_validation,
        stream_narrative=stream_narrative,
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    ai = ai_status_from_stream_narrative(stream_narrative)

    return {
        "analysis_type": "puc",
        "engine_version": report.get("engine_version") or ENGINE_VERSION,
        "generated_at": generated_at,
        "default_tab": default_education_tab(current_age),
        "student": _student_summary(payload),
        "report": report,
        "stream_narrative": stream_narrative,
        "AI": ai,
    }
