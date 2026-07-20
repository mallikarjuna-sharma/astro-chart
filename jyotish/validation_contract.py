"""Cross-engine validation, calibration, privacy and disclaimer contracts."""
from __future__ import annotations

from typing import Any, Mapping

VALIDATION_CONTRACT_VERSION = "engine-evidence-contract.v1"
UNIVERSAL_DISCLAIMER = (
    "Traditional interpretive guidance; not scientifically validated and not a substitute "
    "for qualified educational, career, financial, legal or medical advice."
)


def evidence_status(*, inputs_complete: bool, computed: bool, degraded: bool = False) -> dict[str, Any]:
    """Keep computation, reference validation and empirical validation separate.

    GAP-FIX (2026-07-18, audit P2 "input completeness is overstated"): the
    key used to be named plain `input_completeness`, and a reader seeing
    "COMPLETE" next to a set of otherwise-unfamiliar validation fields could
    reasonably read it as "this result is fully validated" rather than what
    it actually means -- only the *chart calculation inputs* (birth data,
    ephemeris, divisional charts) were present and complete. The three
    sibling fields (reference_validation, empirical_validation,
    statistical_calibration) already say NOT_RUN/NOT_CALIBRATED, so the
    contradiction was always technically visible, but never made explicit.
    Renamed to `chart_input_completeness` (no other code in this repo reads
    the old key programmatically -- grepped before renaming) and added
    `validation_scope_note` to say outright what COMPLETE does and does not
    cover.
    """
    return {
        "contract_version": VALIDATION_CONTRACT_VERSION,
        "chart_input_completeness": "COMPLETE" if inputs_complete else "INCOMPLETE",
        "validation_scope_note": (
            "chart_input_completeness reflects only whether this chart's own "
            "calculation inputs (birth data, ephemeris, divisional charts) "
            "were present -- it is NOT a claim that the resulting scores "
            "have been scientifically or statistically validated. See "
            "reference_validation, empirical_validation and "
            "statistical_calibration below for that."
        ),
        "calculation_status": "COMPUTED_DEGRADED" if computed and degraded else "COMPUTED" if computed else "NOT_COMPUTED",
        "reference_validation": "NOT_RUN_MISSING_GOLDEN_FIXTURES",
        "empirical_validation": "NOT_RUN_MISSING_LABELLED_BENCHMARK",
        "statistical_calibration": "NOT_CALIBRATED",
        "validated_claim_allowed": False,
    }


def calculation_identity(policy: Mapping[str, Any], *, engine: str, degraded: bool = False,
                         fallback_reason: str = "") -> dict[str, Any]:
    return {
        "engine": engine,
        "ayanamsha": policy.get("ayanamsha"),
        "node_type": policy.get("node_type"),
        "house_system_by_method": policy.get("house_system_by_method", {}),
        "varga_conventions": policy.get("varga_conventions", {}),
        "degraded_mode": bool(degraded),
        "fallback_reason": fallback_reason if degraded else "",
        "precise_date_claims_allowed": not degraded,
    }


def privacy_contract(payload: Any) -> dict[str, Any]:
    consent = bool(getattr(payload, "external_llm_consent", False))
    return {
        "external_llm_consent": consent,
        "external_llm_allowed": consent,
        "debug_redaction_enabled": bool(getattr(payload, "redact_debug_output", True)),
        "retention_policy": str(getattr(payload, "data_retention_policy", "SESSION_ONLY")),
    }
