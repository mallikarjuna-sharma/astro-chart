"""D10 verification and sensitivity readiness contract."""
from __future__ import annotations
from typing import Any, Mapping

def assess_d10_verification(payload:Any,canonical_report:Mapping[str,Any])->dict:
    provenance=canonical_report.get("provenance_bundle") or {}
    fact=(provenance.get("facts") or {}).get("D10.CHART") or {}
    uncertainty=max(0,int(getattr(payload,"birth_time_uncertainty_minutes",0) or 0))
    status=fact.get("status","MISSING")
    return {"contract_version":"d10-verification.v1","fact_status":status,
            "calculation_source":fact.get("source"),"conflicts":provenance.get("conflicts",[]),
            "birth_time_uncertainty_minutes":uncertainty,
            "sensitivity_status":"REQUIRED_NOT_RUN" if uncertainty or getattr(payload,"birth_time_precision","unknown")!="exact" else "NOT_REQUIRED_EXACT_DECLARED",
            "authority_eligible":status=="CALCULATED" and not provenance.get("conflicts"),
            "golden_fixture_status":"NOT_AVAILABLE",
            "note":"Authority remains shadow-only until golden fixtures and real perturbation reruns pass."}
