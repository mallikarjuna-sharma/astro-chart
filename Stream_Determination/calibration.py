"""Governed calibration metadata and dataset validation for stream scoring.

This module deliberately never invents labels or silently tunes weights. A
calibration is publishable only when the input contains consent/provenance,
birth-time quality, an outcome measured after the stream decision, and enough
independent cases per stream. Until then the scorer must remain labelled
ENGINEERED_PROVISIONAL.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any, Dict, Iterable, List

STREAMS = ("science", "commerce", "humanities")
MIN_CASES_PER_STREAM = 30
MIN_TOTAL_CASES = 120
CALIBRATION_SCHEMA_VERSION = "stream-calibration.v1"


def validate_outcomes(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    errors: List[str] = []
    valid: List[Dict[str, Any]] = []
    seen_ids = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {i}: must be an object")
            continue
        case_id = row.get("case_id")
        if not case_id or case_id in seen_ids:
            errors.append(f"row {i}: case_id is missing or duplicated")
            continue
        seen_ids.add(case_id)
        stream = row.get("observed_stream")
        if stream not in STREAMS:
            errors.append(f"row {i}: observed_stream must be one of {STREAMS}")
            continue
        if row.get("consent_status") != "DE_IDENTIFIED_CONSENTED":
            errors.append(f"row {i}: consent_status must be DE_IDENTIFIED_CONSENTED")
            continue
        try:
            window = float(row.get("outcome_window_months"))
        except (TypeError, ValueError):
            window = float("nan")
        if not math.isfinite(window) or window <= 0:
            errors.append(f"row {i}: outcome_window_months must be positive")
            continue
        if row.get("outcome_confirmed") is not True:
            errors.append(f"row {i}: outcome_confirmed must be true")
            continue
        if row.get("birth_time_quality") not in {"EXACT_RECORDED", "RECTIFIED_VALIDATED"}:
            errors.append(f"row {i}: birth_time_quality is not calibration-grade")
            continue
        valid.append(row)
    counts = Counter(r["observed_stream"] for r in valid)
    sufficient = len(valid) >= MIN_TOTAL_CASES and all(
        counts[s] >= MIN_CASES_PER_STREAM for s in STREAMS
    )
    if not sufficient:
        errors.append(
            f"insufficient independent cases: total={len(valid)}, counts={dict(counts)}; "
            f"need total>={MIN_TOTAL_CASES} and each stream>={MIN_CASES_PER_STREAM}"
        )
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "valid_rows": len(valid),
        "stream_counts": dict(counts),
        "errors": errors,
        "promotion_authorized": not errors,
    }


def calibration_state(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    config = config or {}
    status = config.get("status", "ENGINEERED_PROVISIONAL")
    if status == "VALIDATED_CALIBRATED" and not config.get("validation_report"):
        status = "ENGINEERED_PROVISIONAL"
    return {
        "status": status,
        "version": config.get("version", "unvalidated"),
        "dataset_id": config.get("dataset_id"),
        "validation_report": config.get("validation_report"),
        "note": (
            "Weights are outcome-calibrated only when status is "
            "VALIDATED_CALIBRATED and a passing validation report is attached."
        ),
    }
