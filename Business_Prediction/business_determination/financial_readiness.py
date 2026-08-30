"""Non-astrological capital-readiness evidence contract."""
from __future__ import annotations

from datetime import date
import math
import re
from typing import Any, Dict, Mapping, Optional

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def evaluate_financial_readiness(
    inputs: Optional[Mapping[str, Any]], astrological_support: bool,
) -> Dict[str, Any]:
    required = {
        "market_validation_completed", "unit_economics_validated",
        "runway_months", "liquidity_buffer_ratio", "funding_committed_ratio",
        "legal_review_completed", "tax_accounting_review_completed",
        "attestation_source", "as_of_date", "legal_reviewer_id",
        "accounting_reviewer_id", "evidence_bundle_sha256",
    }
    if not inputs:
        return {
            "status": "MISSING_EXTERNAL_FINANCIAL_EVIDENCE", "certified": False,
            "missing_fields": sorted(required),
            "note": "Supply independently reviewed market, liquidity, legal and accounting evidence.",
        }
    missing = sorted(required - set(inputs))
    def _number(name: str) -> float:
        try:
            value = float(inputs.get(name, 0) or 0)
            return value if math.isfinite(value) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _text(name: str) -> str:
        return str(inputs.get(name, "") or "").strip()

    evidence_date_valid = False
    evidence_date_not_future = False
    try:
        evidence_date = date.fromisoformat(_text("as_of_date"))
        evidence_date_valid = True
        evidence_date_not_future = evidence_date <= date.today()
    except ValueError:
        evidence_date = None

    checks = {
        "astrological_support": bool(astrological_support),
        "market_validation": inputs.get("market_validation_completed") is True,
        "unit_economics": inputs.get("unit_economics_validated") is True,
        "runway_6_months": _number("runway_months") >= 6.0,
        "liquidity_buffer": _number("liquidity_buffer_ratio") >= 1.0,
        "funding_80_percent": _number("funding_committed_ratio") >= 0.8,
        "legal_review": inputs.get("legal_review_completed") is True,
        "tax_accounting_review": inputs.get("tax_accounting_review_completed") is True,
        "attestation_source_identified": bool(_text("attestation_source")),
        "legal_reviewer_identified": bool(_text("legal_reviewer_id")),
        "accounting_reviewer_identified": bool(_text("accounting_reviewer_id")),
        "evidence_date_valid": evidence_date_valid,
        "evidence_date_not_future": evidence_date_not_future,
        "evidence_bundle_hashed": bool(_SHA256_RE.fullmatch(_text("evidence_bundle_sha256"))),
    }
    certified = not missing and all(checks.values())
    return {
        "status": "EVIDENCE_GATE_PASSED" if certified else "EVIDENCE_GATE_FAILED",
        "certified": certified, "checks": checks, "missing_fields": missing,
        "failed_checks": sorted(k for k, ok in checks.items() if not ok),
        "attestation_source": inputs.get("attestation_source", "UNSPECIFIED"),
        "as_of_date": evidence_date.isoformat() if evidence_date else inputs.get("as_of_date"),
        "legal_reviewer_id": inputs.get("legal_reviewer_id"),
        "accounting_reviewer_id": inputs.get("accounting_reviewer_id"),
        "note": "Certification is based on caller attestations; retain underlying professional review documents.",
    }


__all__ = ["evaluate_financial_readiness"]
