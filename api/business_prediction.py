"""Business-prediction analysis — JyotishAI Business_Prediction engine."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from jyotish.astro import _get_active_dasha_lord
from jyotish.engine_io import parse_json_payload
from jyotish.payload import ENGINE_VERSION, NatalPayloadV2
from api.llm_policy import prepare_chart_for_api_llm

logger = logging.getLogger("api.business_prediction")


class BusinessPredictionError(RuntimeError):
    """Raised when business-prediction analysis cannot complete."""


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
        "risk_appetite": payload.risk_appetite,
        "active_dasha_lord": _get_active_dasha_lord(
            getattr(payload, "dasha_sequence", []),
            float(getattr(payload, "current_age", 0)),
        ) or "",
    }


def run_business_prediction(
    chart: dict[str, Any],
    *,
    venture_type: str = "business",
    years_ahead: int = 15,
) -> dict[str, Any]:
    """Parse chart JSON, run the business engine, and return a structured response."""
    from Business_Prediction.business_engine import compute_business_prediction
    from Business_Prediction.generate_business_report import _load_business_registry
    from Business_Prediction.generate_react_report import _build_report_data

    chart = prepare_chart_for_api_llm(chart)
    payload = parse_json_payload(chart, build_timeline=False)

    all_sector_count = len(_load_business_registry().get("sectors", {}))
    try:
        prediction = compute_business_prediction(
            payload,
            top_n_sectors=all_sector_count,
            venture_type=venture_type,
            years_ahead=years_ahead,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("compute_business_prediction failed")
        raise BusinessPredictionError(str(exc)) from exc

    decision_status = prediction.get("decision_status")
    if decision_status == "ABSTAIN_INSUFFICIENT_D1_DATA":
        reason = (
            prediction.get("quarantine_reason")
            or "Insufficient D1 chart data for a scored business prediction."
        )
        raise BusinessPredictionError(reason)

    name = getattr(payload, "name", "") or prediction.get("name") or "Chart Subject"
    prediction = dict(prediction)
    prediction.setdefault("name", name)

    # Supplementary scans (same defaults as generate_business_report HTML path).
    from Business_Prediction.generate_business_report import (
        _default_ashtakavarga_years_result,
        _default_business_muhurta_result,
    )

    muhurta_result = _default_business_muhurta_result(payload)
    ashtakavarga_result = _default_ashtakavarga_years_result(
        payload,
        timed_windows=prediction.get("timed_windows") or [],
        years_ahead=6,
    )

    auth = dict(prediction.get("authoritative_recommendation") or {})
    if auth.get("muhurta_check") is None:
        auth["muhurta_check"] = muhurta_result
    if auth.get("ashtakavarga_year_check") is None:
        auth["ashtakavarga_year_check"] = ashtakavarga_result
    prediction["authoritative_recommendation"] = auth
    prediction["supplementary_muhurta"] = muhurta_result
    prediction["supplementary_ashtakavarga"] = ashtakavarga_result

    report = _build_report_data(prediction, name_override=name)

    return {
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "student": _student_summary(payload),
        "prediction": prediction,
        "report": report,
        "model_status": str(prediction.get("model_status") or ""),
        "calibration_status": str(prediction.get("calibration_status") or ""),
        "rule_pack_version": str(prediction.get("rule_pack_version") or ""),
    }
