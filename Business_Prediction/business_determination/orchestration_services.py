"""Small orchestration services extracted from the prediction engine."""
from datetime import date
from typing import Any, Dict, Iterable

from .policy import DECISION_POLICY

MANDATORY_INPUTS_BY_FAMILY = {
    "structural_recommendation": ("house_lords", "planet_house", "planet_dignities"),
    "sector_ranking": ("house_lords", "planet_house"),
    "timing": ("dob", "dasha_sequence"),
    "partnership_synastry": ("house_lords", "planet_dignities"),
    "profitability_stability": ("house_lords", "planet_dignities"),
    "high_confidence": ("house_lords", "planet_house", "planet_dignities", "kp_significators", "amatyakaraka"),
}


def validate_request(venture_type: str, supported: Iterable[str], years_ahead: int, top_n: int, as_of: Any) -> None:
    supported = tuple(supported)
    if venture_type not in supported:
        raise ValueError(f"unsupported venture_type: {venture_type!r}, expected one of {sorted(supported)}")
    if not isinstance(years_ahead, int) or isinstance(years_ahead, bool):
        raise TypeError(f"years_ahead must be an int, got {type(years_ahead).__name__}")
    if not 0 < years_ahead <= DECISION_POLICY.max_forecast_years:
        raise ValueError(f"years_ahead must be > 0 and <= {DECISION_POLICY.max_forecast_years}, got {years_ahead}")
    if not isinstance(top_n, int) or isinstance(top_n, bool):
        raise TypeError(f"top_n_sectors must be an int, got {type(top_n).__name__}")
    if top_n < 0:
        raise ValueError(f"top_n_sectors must be >= 0, got {top_n}")
    if as_of is not None and not isinstance(as_of, date):
        raise TypeError(f"as_of_date must be a datetime.date (or None), got {type(as_of).__name__}")


def assess_evidence_sufficiency(payload: Any):
    result: Dict[str, Any] = {}
    for family, required in MANDATORY_INPUTS_BY_FAMILY.items():
        missing = [attr for attr in required if not getattr(payload, attr, None)]
        result[family] = {
            "status": "INSUFFICIENT_EVIDENCE" if missing else "OK",
            "missing_inputs": missing,
            "note": (
                f"Mandatory input(s) {', '.join(missing)} unavailable; {family} is not fully evidenced."
                if missing else f"All mandatory inputs for {family} are present."
            ),
        }
    decision = (
        "ABSTAIN_INSUFFICIENT_D1_DATA"
        if result["structural_recommendation"]["status"] == "INSUFFICIENT_EVIDENCE" else "OK"
    )
    return result, decision


def finalize_result(result: Dict[str, Any], decision_status: str) -> Dict[str, Any]:
    result["legacy_non_authoritative"] = {
        "mode_gate": result["mode_gate"],
        "recommendation": {
            key: result["recommendation"].get(key) for key in (
                "gate_score", "employment_score", "legacy_mode_gate_score", "legacy_employment_score"
            )
        },
        "status": "NON_AUTHORITATIVE_COMPATIBILITY_ONLY",
    }
    diagnostics = result["diagnostics"]
    counts = {
        severity: sum(d.get("severity") == severity for d in diagnostics)
        for severity in ("INFORMATIONAL_FALLBACK", "DEGRADED_METHOD", "RECOMMENDATION_BLOCKING")
    }
    result["diagnostic_summary"] = {
        "severity_counts": counts, "recommendation_capped": False,
        "policy": "Blocking disables proceed; degraded caps full transition; informational is disclosure-only.",
    }
    auth, rec = result["authoritative_recommendation"], result["recommendation"]
    if counts["RECOMMENDATION_BLOCKING"]:
        auth.update(action_level="ABSTAIN_INTERNAL_METHOD_FAILURE", final_proceed=False,
                    employment_exit_supported=False, capital_intensive_launch_supported=False)
        rec.update(proceed=False, heuristic_tier="LOW", confidence="LOW")
        result["diagnostic_summary"]["recommendation_capped"] = True
    elif counts["DEGRADED_METHOD"] and auth.get("action_level") == "FULL_TRANSITION_SUPPORTED":
        auth.update(action_level=DECISION_POLICY.diagnostic_strong_recommendation_cap,
                    employment_exit_supported=False, capital_intensive_launch_supported=False)
        result["diagnostic_summary"]["recommendation_capped"] = True
    if decision_status != "OK":
        for key in (
            "business_promise", "job_promise", "business_promise_layers", "job_promise_layers",
            "independent_profession_promise", "business_field_fit", "business_execution_capacity",
            "competency_readiness", "business_profitability", "gross_revenue_potential",
            "profit_retention", "business_stability", "business_stability_components",
            "current_timing_readiness", "business_over_job_confidence", "business_advantage_margin",
            "business_advantage_label", "strong_business_absolute_floor_met", "operating_model",
            "operating_model_d10", "transition_timing_recommendation",
        ):
            result[key] = None
        for key in ("top_sectors", "timed_windows", "d2_hora_evidence", "janma_nakshatra_evidence",
                    "foreign_business_evidence", "detected_yogas", "legal_dispute_risk"):
            result[key] = []
        result["d2_hora_deep_evidence"] = {"status": "SUPPRESSED", "note": "D2-Hora deep evidence suppressed: decision_status != OK."}
        result["mercury_adjudication"] = {"status": "SUPPRESSED", "note": "Mercury adjudication suppressed: decision_status != OK."}
    return result


__all__ = ["validate_request", "assess_evidence_sufficiency", "finalize_result", "MANDATORY_INPUTS_BY_FAMILY"]
