from datetime import date
from types import SimpleNamespace

from jyotish.astro import compute_d11_chart, compute_d11_sign
from Business_Prediction.business_determination.d24_d60_sign import _d11_gains_status
from Business_Prediction.business_determination.financial_readiness import evaluate_financial_readiness
from Business_Prediction.business_determination.capability_status import capability_status
from Business_Prediction.generate_business_report import _section_financial_readiness_html


def test_d11_harmonic_boundaries_and_chart():
    assert compute_d11_sign("Aries", 0.0) == "Aries"
    assert compute_d11_sign("Taurus", 0.0) == "Pisces"
    assert compute_d11_sign("Aries", float("nan")) == ""
    assert compute_d11_sign("Aries", float("inf")) == ""
    chart = compute_d11_chart({"Jupiter": {"sign": "Aries", "degree": 1.0}}, "Aries", 0.0)
    assert chart["Lagna"] == "Aries"
    assert chart["Jupiter"]


def test_d11_status_is_applied_but_explicitly_optional():
    payload = SimpleNamespace(
        lagna_sign="Aries", lagna_degree=0.0,
        planets_d1={
            "Mars": {"sign": "Aries", "degree": 1.0},
            "Venus": {"sign": "Taurus", "degree": 1.0},
            "Jupiter": {"sign": "Cancer", "degree": 5.0},
            "Saturn": {"sign": "Aquarius", "degree": 5.0},
        },
        house_lords={}, planet_house={}, planet_dignities={}, birth_tithi_num=10,
    )
    result = _d11_gains_status(payload)
    assert result["status"] == "APPLIED"
    assert result["construction_policy"] == "HARMONIC_11"
    assert result["doctrinal_status"] == "OPTIONAL_NON_SHODASHAVARGA_CORROBORATION"


def test_capability_registry_matches_implemented_d11_policy():
    status = capability_status()
    assert all(item["id"] != "D11_CONSTRUCTION_AND_ROLE" for item in status["doctrine_decisions_required"])
    assert {
        "id": "D11",
        "scope": "HARMONIC_11_OPTIONAL_GAINS_CORROBORATION_NON_SHODASHAVARGA",
    } in status["implemented_with_bounded_scope"]


def test_financial_certification_requires_every_external_gate():
    assert evaluate_financial_readiness(None, True)["certified"] is False
    inputs = {
        "market_validation_completed": True, "unit_economics_validated": True,
        "runway_months": 9, "liquidity_buffer_ratio": 1.2,
        "funding_committed_ratio": 0.9, "legal_review_completed": True,
        "tax_accounting_review_completed": True, "attestation_source": "CFO_AND_COUNSEL",
        "as_of_date": date.today().isoformat(), "legal_reviewer_id": "counsel-001",
        "accounting_reviewer_id": "ca-001", "evidence_bundle_sha256": "a" * 64,
    }
    assert evaluate_financial_readiness(inputs, True)["certified"] is True
    assert evaluate_financial_readiness(inputs, False)["certified"] is False
    assert evaluate_financial_readiness({**inputs, "legal_reviewer_id": ""}, True)["certified"] is False
    assert evaluate_financial_readiness({**inputs, "evidence_bundle_sha256": "abc123"}, True)["certified"] is False
    assert evaluate_financial_readiness({**inputs, "runway_months": float("inf")}, True)["certified"] is False


def test_financial_readiness_is_visible_in_html():
    html = _section_financial_readiness_html({
        "authoritative_recommendation": {
            "capital_readiness_status": "ASTROLOGICAL_SUPPORT",
            "capital_readiness_certified": False,
            "financial_readiness": {
                "status": "EVIDENCE_GATE_FAILED",
                "failed_checks": ["legal_review"],
                "missing_fields": [],
                "note": "Professional review required.",
            },
        },
    })
    assert "Financial Readiness Evidence" in html
    assert "NOT CERTIFIED" in html
    assert "legal_review" in html
