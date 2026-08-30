"""Nested typed and runtime-validated public result contract."""
from typing import Any, Dict, List, Literal, Mapping, TypedDict

OUTPUT_CONTRACT_VERSION = "business-prediction-result.v2"
DecisionStatus = Literal["OK", "ABSTAIN_INSUFFICIENT_D1_DATA"]


class DiagnosticRecord(TypedDict):
    module: str
    error: str
    type: str
    severity: Literal["INFORMATIONAL_FALLBACK", "DEGRADED_METHOD", "RECOMMENDATION_BLOCKING"]


class RecommendationRecord(TypedDict):
    venture_type: str
    proceed: bool
    heuristic_tier: str
    confidence: str
    comparative_advantage: bool
    hybrid_suggested: bool
    reasoning: str


class AuthoritativeRecommendationRecord(TypedDict):
    verdict: str
    action_level: str
    decision_status: DecisionStatus
    employment_exit_supported: bool
    capital_intensive_launch_supported: bool
    final_proceed: bool


class TimedWindowRecord(TypedDict, total=False):
    md_lord: str
    ad_lord: str
    start_date: str
    end_date: str
    net_score: float
    label: str


class SectorRecord(TypedDict, total=False):
    sector: str
    score: float


class BusinessPredictionResult(TypedDict):
    output_contract_version: str
    architecture_version: str
    rule_pack_version: str
    decision_policy: Dict[str, object]
    decision_status: DecisionStatus
    conclusions_quarantined: bool
    quarantine_reason: str | None
    mode_gate: Dict[str, Any]
    significators: Dict[str, Any]
    top_sectors: List[SectorRecord]
    timed_windows: List[TimedWindowRecord]
    recommendation: RecommendationRecord
    authoritative_recommendation: AuthoritativeRecommendationRecord
    diagnostics: List[DiagnosticRecord]


def _require(mapping: Mapping[str, Any], path: str, spec: Mapping[str, type], errors: List[str]) -> None:
    for field, expected in spec.items():
        value = mapping.get(field)
        if field not in mapping:
            errors.append(f"{path}.{field}: missing")
        elif not isinstance(value, expected):
            errors.append(f"{path}.{field}: expected {expected.__name__}, got {type(value).__name__}")


def validate_result_contract(result: Mapping[str, Any]) -> None:
    errors: List[str] = []
    _require(result, "result", {
        "output_contract_version": str, "architecture_version": str,
        "rule_pack_version": str, "decision_policy": dict, "decision_status": str,
        "conclusions_quarantined": bool, "mode_gate": dict, "significators": dict,
        "top_sectors": list, "timed_windows": list, "recommendation": dict,
        "authoritative_recommendation": dict, "diagnostics": list,
    }, errors)
    if result.get("output_contract_version") != OUTPUT_CONTRACT_VERSION:
        errors.append("result.output_contract_version: unsupported")
    status = result.get("decision_status")
    if status not in {"OK", "ABSTAIN_INSUFFICIENT_D1_DATA"}:
        errors.append("result.decision_status: invalid discriminator")

    rec = result.get("recommendation")
    if isinstance(rec, Mapping):
        _require(rec, "recommendation", {
            "venture_type": str, "proceed": bool, "heuristic_tier": str,
            "confidence": str, "comparative_advantage": bool,
            "hybrid_suggested": bool, "reasoning": str,
        }, errors)
    auth = result.get("authoritative_recommendation")
    if isinstance(auth, Mapping):
        _require(auth, "authoritative_recommendation", {
            "verdict": str, "action_level": str, "decision_status": str,
            "employment_exit_supported": bool,
            "capital_intensive_launch_supported": bool, "final_proceed": bool,
        }, errors)
        if auth.get("decision_status") != status:
            errors.append("authoritative_recommendation.decision_status: differs from result")

    for index, diagnostic in enumerate(result.get("diagnostics", [])):
        if not isinstance(diagnostic, Mapping):
            errors.append(f"diagnostics[{index}]: expected mapping")
            continue
        _require(diagnostic, f"diagnostics[{index}]", {
            "module": str, "error": str, "type": str, "severity": str,
        }, errors)
        if diagnostic.get("severity") not in {
            "INFORMATIONAL_FALLBACK", "DEGRADED_METHOD", "RECOMMENDATION_BLOCKING"
        }:
            errors.append(f"diagnostics[{index}].severity: invalid")

    for index, row in enumerate(result.get("top_sectors", [])):
        if not isinstance(row, Mapping):
            errors.append(f"top_sectors[{index}]: expected mapping")
    for index, window in enumerate(result.get("timed_windows", [])):
        if not isinstance(window, Mapping):
            errors.append(f"timed_windows[{index}]: expected mapping")
        elif "label" not in window or not isinstance(window.get("label"), str):
            errors.append(f"timed_windows[{index}].label: missing or not str")

    quarantined = result.get("conclusions_quarantined")
    if status == "OK" and quarantined:
        errors.append("quarantine invariant: OK result cannot be quarantined")
    if status != "OK":
        if quarantined is not True:
            errors.append("quarantine invariant: abstention must be quarantined")
        for field in ("business_promise", "business_stability", "operating_model"):
            if result.get(field) is not None:
                errors.append(f"quarantine invariant: {field} must be null")
        if result.get("top_sectors") or result.get("timed_windows"):
            errors.append("quarantine invariant: sectors/windows must be empty")

    if errors:
        raise ValueError("invalid BusinessPredictionResult: " + "; ".join(errors))


__all__ = [
    "BusinessPredictionResult", "RecommendationRecord", "AuthoritativeRecommendationRecord",
    "DiagnosticRecord", "TimedWindowRecord", "SectorRecord", "DecisionStatus",
    "OUTPUT_CONTRACT_VERSION", "validate_result_contract",
]
