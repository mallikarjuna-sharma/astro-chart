import ast
from pathlib import Path
from types import SimpleNamespace

import Business_Prediction.business_determination as package
from Business_Prediction.business_engine import compute_business_prediction
from Business_Prediction.business_determination.policy import DECISION_POLICY
from Business_Prediction.business_determination.result_schema import (
    OUTPUT_CONTRACT_VERSION,
    validate_result_contract,
)


ROOT = Path(__file__).parents[2]


def test_public_api_does_not_advertise_private_helpers():
    assert package.__all__
    assert not [name for name in package.__all__ if name.startswith("_")]


def test_business_code_does_not_import_private_job_timeline_helpers():
    base = ROOT / "Business_Prediction" / "business_determination"
    violations = []
    for path in base.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "Job_Career.timeline":
                violations.extend((path.name, alias.name) for alias in node.names if alias.name.startswith("_"))
    assert violations == []


def test_policy_manifest_is_mutation_isolated():
    first = DECISION_POLICY.manifest()
    first["comparative_margin"] = 999
    assert DECISION_POLICY.manifest()["comparative_margin"] == 8.0


def test_abstention_quarantines_authoritative_subordinate_conclusions():
    result = compute_business_prediction(SimpleNamespace())
    assert result["decision_status"] == "ABSTAIN_INSUFFICIENT_D1_DATA"
    assert result["conclusions_quarantined"] is True
    assert result["business_promise"] is None
    assert result["business_stability"] is None
    assert result["operating_model"] is None
    assert result["top_sectors"] == []
    assert result["timed_windows"] == []


def test_result_contract_is_versioned_and_runtime_validated():
    result = compute_business_prediction(SimpleNamespace())
    assert result["output_contract_version"] == OUTPUT_CONTRACT_VERSION
    assert result["decision_policy"]["version"] == "business-decision-policy.v3"
    validate_result_contract(result)
