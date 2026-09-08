"""PUC stream analysis entry point for API and CLI callers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jyotish.engine_io import parse_json_payload
from jyotish.payload import ENGINE_VERSION

from .cross_validate import safe_cross_validate
from .early_age_stream_engine import DEFAULT_INCLUDE_CROSS_VALIDATION
from .stream_narrative import generate_stream_narrative
from .stream_report import build_report_payload
from .stream_scoring import AGE_THRESHOLD_YEARS, compute_stream_determination


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


def puc_age_error_message(current_age: Any) -> str:
    """User-facing message when a chart is outside the PUC age window."""
    try:
        age_years = int(round(float(current_age)))
    except (TypeError, ValueError):
        return "PUC stream analysis is only available for students aged 15–17."
    return (
        "PUC stream analysis is only available for students aged 15–17. "
        f"This profile is {age_years} years old — use the UG career analysis instead."
    )


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


def run_puc_analysis(
    chart: dict[str, Any],
    *,
    llm_enabled: bool = False,
    llm_runtime_consent: bool = False,
) -> dict[str, Any]:
    """Score PUC stream direction from consolidated chart JSON.

    Always uses ``forced_override=False`` — charts outside the normal under-15
    scope are rejected rather than scored as test-only overrides.
    """
    payload = parse_json_payload(chart)
    current_age = getattr(payload, "current_age", None)

    if not is_puc_eligible(current_age):
        raise PucAnalysisError(puc_age_error_message(current_age))

    determination = compute_stream_determination(payload)

    cross_validation = None
    if DEFAULT_INCLUDE_CROSS_VALIDATION:
        cross_validation = safe_cross_validate(payload, precomputed_determination=determination)

    stream_narrative = generate_stream_narrative(
        payload,
        determination,
        enabled=llm_enabled,
        runtime_consent=llm_runtime_consent,
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

    return {
        "analysis_type": "puc",
        "engine_version": report.get("engine_version") or ENGINE_VERSION,
        "generated_at": generated_at,
        "default_tab": default_education_tab(current_age),
        "student": _student_summary(payload),
        "report": report,
        "stream_narrative": stream_narrative,
    }
