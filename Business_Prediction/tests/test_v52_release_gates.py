from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import pytest

from Business_Prediction.business_engine import compute_business_prediction
from Business_Prediction.business_determination.constants import ARCHITECTURE_VERSION
from Business_Prediction.business_determination.policy import DECISION_POLICY
from Business_Prediction.business_determination.result_schema import validate_result_contract
from Business_Prediction.business_determination.runtime_models import CalculationContext, MethodResult


def test_nested_schema_rejects_corrupt_authoritative_boolean():
    result = compute_business_prediction(SimpleNamespace())
    broken = deepcopy(result)
    broken["authoritative_recommendation"]["final_proceed"] = "yes"
    with pytest.raises(ValueError, match="final_proceed"):
        validate_result_contract(broken)


def test_quarantine_invariants_are_runtime_enforced():
    result = compute_business_prediction(SimpleNamespace())
    broken = deepcopy(result)
    broken["business_promise"] = 50.0
    with pytest.raises(ValueError, match="business_promise"):
        validate_result_contract(broken)


def test_release_identity_and_hash_manifest_are_exposed():
    result = compute_business_prediction(SimpleNamespace())
    assert result["architecture_version"] == ARCHITECTURE_VERSION == "business-architecture.v53"
    assert len(result["release_manifest"]["combined_hash"]) == 64
    assert set(result["release_manifest"]["artifact_hashes"]) == {
        "constants.py", "policy.py", "result_schema.py", "business_domain_registry_v1.json"
    }


def test_policy_contains_audited_headline_thresholds():
    manifest = DECISION_POLICY.manifest()
    required = {
        "absolute_proceed_gate_floor", "absolute_proceed_strength_floor",
        "high_tier_gate_floor", "high_tier_strength_floor", "high_tier_margin_floor",
        "d24_competency_factor_floor", "contradiction_transition_floor",
        "birth_time_transition_downgrade_minutes", "d2_capital_net_floor",
        "kp_positive_override_floor", "kp_negative_override_ceiling",
        "shadbala_strong_ratio", "shadbala_weak_ratio",
    }
    assert required <= manifest.keys()


def test_calculation_context_returns_mutation_isolated_cached_facts():
    calls = []
    context = CalculationContext(SimpleNamespace())
    first = context.fact("x", lambda: calls.append(1) or {"items": []})
    first["items"].append("mutated")
    second = context.fact("x", lambda: calls.append(2) or {})
    assert second == {"items": []}
    assert calls == [1]


def test_common_method_result_has_normalized_status_shape():
    assert MethodResult(status="NO_DATA", reason="missing").to_dict() == {
        "status": "NO_DATA", "value": None, "reason": "missing", "degraded": False
    }


def test_repeated_and_multithreaded_abstentions_are_deterministic_and_isolated():
    def run():
        result = compute_business_prediction(SimpleNamespace())
        return {
            "decision_status": result["decision_status"],
            "diagnostics": result["diagnostics"],
            "release_hash": result["release_manifest"]["combined_hash"],
            "policy": result["decision_policy"],
        }

    expected = run()
    assert run() == expected
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: run(), range(8))) == [expected] * 8
