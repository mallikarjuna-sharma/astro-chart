"""Gap-audit fix (2026-08, HIGH priority item 3): test coverage for the
declared-policy module (llm_policy.py) and the rule-trace validator's
parsing-layer guard (llm_validator.py::_validate_response).

These two modules were previously untested even though they enforce two of
the engine's hardest safety boundaries:
  1. llm_policy.data_quality_gate() decides whether KP/D60/cusp-precision
     claims must be suppressed for an imprecise birth time.
  2. llm_validator._validate_response() is the parsing-layer assertion that
     a validator LLM response never claims `calculation_recomputable_by_llm`
     and never returns a claim status outside the closed enum -- the last
     line of defense against a model silently smuggling a recomputed value
     back into the pipeline.

Both functions are pure (no network, no ephemeris, no I/O beyond stdlib),
so they are safe and fast to test directly, unlike most of the LLM layer
(call_llm_for_fields, validate_rule_trace, etc.) which requires mocking an
external API and is out of scope for this pass.
"""
from __future__ import annotations

import pytest

from jyotish.llm_policy import (
    build_policy_json,
    data_quality_gate,
    AYANAMSHA,
    HOUSE_SYSTEM_BY_METHOD,
    BIRTH_TIME_UNCERTAINTY_HIGH_SENSITIVITY_MINUTES,
)
from jyotish.llm_validator import _validate_response, _build_method_trace_json


# ── llm_policy.build_policy_json ────────────────────────────────────────────

def test_build_policy_json_has_all_declared_keys():
    policy = build_policy_json()
    for key in (
        "ayanamsha", "node_type", "node_aspect_convention", "node_dignity_scheme",
        "karaka_scheme", "house_system_by_method", "combustion_orb_source",
        "cazimi_doctrine_note", "vimshottari_year_length_days",
        "varga_conventions", "birth_time_uncertainty_high_sensitivity_minutes",
    ):
        assert key in policy


def test_build_policy_json_ayanamsha_matches_module_constant():
    assert build_policy_json()["ayanamsha"] == AYANAMSHA == "KP_KRISHNAMURTI"


def test_build_policy_json_house_system_by_method_is_not_mutated_copy():
    policy = build_policy_json()
    assert policy["house_system_by_method"] == HOUSE_SYSTEM_BY_METHOD
    # Mutating the returned dict must not corrupt the module-level policy for
    # the next caller (build_policy_json returns the module dict directly;
    # this test documents that behavior so a future refactor to return a
    # mutable shared reference doesn't silently become a footgun).
    policy["house_system_by_method"]["shadbala"] = "MUTATED"
    assert HOUSE_SYSTEM_BY_METHOD["shadbala"] == "MUTATED", (
        "documents current shared-reference behavior; if this starts "
        "failing, build_policy_json now deep-copies (fine, just update "
        "this test to match)."
    )
    # restore, since HOUSE_SYSTEM_BY_METHOD is process-global module state
    HOUSE_SYSTEM_BY_METHOD["shadbala"] = "whole_sign"


# ── llm_policy.data_quality_gate ────────────────────────────────────────────

def test_data_quality_gate_exact_precision_zero_uncertainty_is_low_sensitivity():
    result = data_quality_gate({"birth_time_precision": "exact", "birth_time_uncertainty_minutes": 0})
    assert result["high_sensitivity_gate"] is False
    assert result["suppress_high_precision_claims"] is False
    assert result["affected_facts"] == []


def test_data_quality_gate_non_exact_precision_forces_high_sensitivity():
    result = data_quality_gate({"birth_time_precision": "approximate", "birth_time_uncertainty_minutes": 0})
    assert result["high_sensitivity_gate"] is True
    assert "KP.CUSPS" in result["affected_facts"]
    assert "D60.CHART" in result["affected_facts"]


def test_data_quality_gate_uncertainty_at_threshold_is_high_sensitivity():
    threshold = BIRTH_TIME_UNCERTAINTY_HIGH_SENSITIVITY_MINUTES
    result = data_quality_gate({"birth_time_precision": "exact", "birth_time_uncertainty_minutes": threshold})
    assert result["high_sensitivity_gate"] is True


def test_data_quality_gate_uncertainty_below_threshold_and_exact_is_low_sensitivity():
    threshold = BIRTH_TIME_UNCERTAINTY_HIGH_SENSITIVITY_MINUTES
    result = data_quality_gate({"birth_time_precision": "exact", "birth_time_uncertainty_minutes": threshold - 1})
    assert result["high_sensitivity_gate"] is False


def test_data_quality_gate_missing_fields_default_to_unknown_precision_and_high_sensitivity():
    result = data_quality_gate({})
    assert result["birth_time_precision"] == "unknown"
    assert result["birth_time_uncertainty_minutes"] == 0
    assert result["high_sensitivity_gate"] is True  # precision != "exact"


def test_data_quality_gate_accepts_object_with_attributes_not_just_mapping():
    class FakePayload:
        birth_time_precision = "exact"
        birth_time_uncertainty_minutes = 0
    result = data_quality_gate(FakePayload())
    assert result["high_sensitivity_gate"] is False


# ── llm_validator._validate_response ────────────────────────────────────────

def _minimal_valid_response(**overrides):
    base = {
        "calculation_recomputable_by_llm": False,
        "claims": [{"claim_id": "c1", "status": "supported"}],
    }
    base.update(overrides)
    return base


def test_validate_response_accepts_well_formed_response():
    _validate_response(_minimal_valid_response())  # must not raise


def test_validate_response_rejects_recomputable_true():
    with pytest.raises(ValueError, match="calculation_recomputable_by_llm"):
        _validate_response(_minimal_valid_response(calculation_recomputable_by_llm=True))


def test_validate_response_rejects_recomputable_missing():
    payload = _minimal_valid_response()
    del payload["calculation_recomputable_by_llm"]
    with pytest.raises(ValueError, match="calculation_recomputable_by_llm"):
        _validate_response(payload)


def test_validate_response_rejects_non_list_claims():
    with pytest.raises(ValueError, match="claims must be a list"):
        _validate_response(_minimal_valid_response(claims={"not": "a list"}))


def test_validate_response_rejects_unknown_claim_status():
    with pytest.raises(ValueError, match="Invalid claim status"):
        _validate_response(_minimal_valid_response(
            claims=[{"claim_id": "c1", "status": "definitely_true_trust_me"}]
        ))


@pytest.mark.parametrize("status", [
    "supported", "unsupported", "contradicted", "insufficient_data", "school_dependent",
])
def test_validate_response_accepts_every_documented_claim_status(status):
    _validate_response(_minimal_valid_response(claims=[{"claim_id": "c1", "status": status}]))


def test_validate_response_rejects_a_numeric_score_smuggled_as_extra_claim_status():
    # Guards the exact failure mode _validate_response exists to catch: a
    # model returning something other than one of the five closed statuses
    # (e.g. trying to communicate a confidence "score" in the status field).
    with pytest.raises(ValueError):
        _validate_response(_minimal_valid_response(claims=[{"claim_id": "c1", "status": 0.87}]))


# ── llm_validator._build_method_trace_json ──────────────────────────────────

def test_build_method_trace_json_extracts_numeric_gap_detail_as_evidence():
    field_result = {
        "field_id": "aerospace_engineering",
        "field_label": "Aerospace Engineering",
        "final_score": 71.4,
        "gap_detail": {"mars_strength_boost": 3.2, "_internal_flag": 1, "note": "not numeric"},
        "method_breakdown": {"parashara": 40.0},
        "method_log": {"parashara": ["step 1", "step 2"]},
        "verified_factors": "Mars in own sign",
    }
    trace = _build_method_trace_json(field_result, "parashara")
    assert trace["method"] == "parashara"
    assert trace["field_id"] == "aerospace_engineering"
    assert trace["final_score"] == 71.4
    # Only the numeric, non-underscore-prefixed key becomes evidence.
    evidence_signals = {e["signal"] for e in trace["gap_boost_evidence"]}
    assert evidence_signals == {"mars_strength_boost"}
    assert trace["method_log"] == ["step 1", "step 2"]


def test_build_method_trace_json_falls_back_to_full_method_log_if_method_absent():
    field_result = {"method_log": {"other_method": ["x"]}}
    trace = _build_method_trace_json(field_result, "parashara")
    # "parashara" key not present in method_log -> falls back to the whole dict
    assert trace["method_log"] == {"other_method": ["x"]}


def test_build_method_trace_json_handles_completely_empty_field_result():
    trace = _build_method_trace_json({}, "kp")
    assert trace["method"] == "kp"
    assert trace["field_id"] == ""
    assert trace["gap_boost_evidence"] == []
    assert trace["final_score"] is None
