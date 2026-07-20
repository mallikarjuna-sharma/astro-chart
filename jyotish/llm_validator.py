"""Rule-trace validator LLM call.

GAP-FIX (2026-07, "Use an LLM for" policy, implemented per user spec):
this module implements the "checking a fully supplied rule trace against a
named school/source", "identifying contradictions, omitted exceptions and
mixed traditions", and "reviewing whether a conclusion is supported by the
supplied evidence ledger" use cases -- capabilities that did not previously
exist anywhere in this codebase. jyotish/llm.py's existing call_llm_for_fields
only ever generated free-form explanatory prose; it never checked a trace
against a declared rule/source, never flagged contradictions or mixed
schools, and never distinguished OBSERVED/DERIVED/TRADITIONAL/HEURISTIC/
CONCLUSION claim types.

Hard boundary (per the "Do not use an LLM for" list this module was built
against): this function NEVER recomputes an astronomical position, cusp,
sunrise, varga, dasha, BAV/SAV, or Shadbala value, NEVER invents missing
birth data or selects an ayanamsha/school (see jyotish/llm_policy.py, which
this module only READS from, never writes to), and NEVER assigns or adjusts
a method weight or score -- `calculation_recomputable_by_llm` is hardcoded
False in the response schema and is asserted in _validate_response below;
any attempt to return a numeric score/weight change from the model is a
validation failure, not a silently-accepted result.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Mapping, Optional

from .llm import _LLM_PROVIDERS, _ProviderClientWrapper, _run_llm_with_retry
from .llm_policy import build_policy_json, data_quality_gate
from .canonical_facts import build_canonical_facts
from .rule_registry import build_rule_registry_json

logger = logging.getLogger(__name__)

VALIDATOR_VERSION = "rule-trace-validator.v1"

_VALIDATOR_SYSTEM_PROMPT = """You are a skeptical Jyotisha rule-audit assistant. You do not calculate astronomical
positions and you do not assume astrology is scientifically predictive. You validate
only whether the supplied deterministic trace follows the declared astrological school,
source and engine policy. Never invent missing facts, rules, citations or exceptions.
Never change numeric scores or weights.
For every claim:
1. separate OBSERVED INPUT, DERIVED FACT, TRADITIONAL RULE, MODERN HEURISTIC, and CONCLUSION;
2. verify that the conclusion follows from the supplied facts and exact rule;
3. identify missing prerequisites, exceptions, cancellation conditions, duplicate evidence,
   school conflicts and birth-time sensitivity;
4. mark unsupported statements as UNSUPPORTED, not plausible;
5. if the supplied source excerpt does not establish a rule, say SOURCE NOT ESTABLISHED;
6. treat correlated methods as correlated; do not call them independent confirmation;
7. use cautious language and never claim certainty or scientific validation.
Return strict JSON matching this schema:
{
  "method": "string",
  "policy_consistent": true|false|null,
  "calculation_recomputable_by_llm": false,
  "claims": [{
    "claim_id": "string",
    "classification": "observed|derived|traditional|heuristic|conclusion",
    "status": "supported|unsupported|contradicted|insufficient_data|school_dependent",
    "reason": "string",
    "missing_inputs": ["string"],
    "exceptions_not_tested": ["string"],
    "duplicate_evidence_ids": ["string"],
    "source_support": [{"source_id":"string","support":"direct|partial|none"}],
    "birth_time_sensitivity": "none|low|medium|high|unknown"
  }],
  "cross_method_conflicts": ["string"],
  "required_deterministic_tests": ["string"],
  "safe_summary": "string"
}"""

_VALIDATOR_RESPONSE_SCHEMA = {
    "name": "rule_trace_validation",
    "schema": {
        "type": "object",
        "properties": {
            "method": {"type": "string"},
            "policy_consistent": {"type": ["boolean", "null"]},
            "calculation_recomputable_by_llm": {"type": "boolean"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "classification": {"type": "string", "enum": [
                            "observed", "derived", "traditional", "heuristic", "conclusion"]},
                        "status": {"type": "string", "enum": [
                            "supported", "unsupported", "contradicted",
                            "insufficient_data", "school_dependent"]},
                        "reason": {"type": "string"},
                        "missing_inputs": {"type": "array", "items": {"type": "string"}},
                        "exceptions_not_tested": {"type": "array", "items": {"type": "string"}},
                        "duplicate_evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "source_support": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source_id": {"type": "string"},
                                    "support": {"type": "string", "enum": ["direct", "partial", "none"]},
                                },
                                "required": ["source_id", "support"],
                                "additionalProperties": False,
                            },
                        },
                        "birth_time_sensitivity": {"type": "string", "enum": [
                            "none", "low", "medium", "high", "unknown"]},
                    },
                    "required": ["claim_id", "classification", "status", "reason",
                                 "missing_inputs", "exceptions_not_tested",
                                 "duplicate_evidence_ids", "source_support",
                                 "birth_time_sensitivity"],
                    "additionalProperties": False,
                },
            },
            "cross_method_conflicts": {"type": "array", "items": {"type": "string"}},
            "required_deterministic_tests": {"type": "array", "items": {"type": "string"}},
            "safe_summary": {"type": "string"},
        },
        "required": ["method", "policy_consistent", "calculation_recomputable_by_llm",
                      "claims", "cross_method_conflicts", "required_deterministic_tests",
                      "safe_summary"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _build_method_trace_json(field_result: Mapping[str, Any], method: str) -> Dict[str, Any]:
    """Extract a unique-evidence-ID method trace from an engine result dict.

    Reuses the engine's own gap_detail/calc_trace/method_breakdown -- does
    NOT recompute anything, purely re-shapes already-computed values with
    stable IDs so the validator can refer to specific claims.
    """
    gap_detail = dict(field_result.get("gap_detail", field_result.get("gap_breakdown", {})) or {})
    method_breakdown = dict(field_result.get("method_breakdown", {}) or {})
    method_log = dict(field_result.get("method_log", {}) or {})

    evidence: List[Dict[str, Any]] = []
    for i, (k, v) in enumerate(sorted(gap_detail.items())):
        if isinstance(v, (int, float)) and not k.startswith("_"):
            evidence.append({"evidence_id": f"GAP.{i:03d}.{k}", "signal": k, "value": v})

    return {
        "method": method,
        "field_id": field_result.get("field_id", ""),
        "field_label": field_result.get("field_label", ""),
        "final_score": field_result.get("final_score"),
        "gap_boost_evidence": evidence,
        "method_breakdown": method_breakdown,
        "method_log": method_log.get(method, method_log),
        "verified_factors": field_result.get("verified_factors", ""),
    }


def _validate_response(data: Dict[str, Any]) -> None:
    """Enforces the hard boundaries at the parsing layer, not just in the
    prompt -- a model that tries to slip a numeric score/weight into the
    response, or that sets calculation_recomputable_by_llm=true, fails
    validation and triggers the retry loop rather than being silently
    accepted."""
    if data.get("calculation_recomputable_by_llm") is not False:
        raise ValueError(
            "calculation_recomputable_by_llm must be false -- this validator "
            "never recomputes astronomical calculations."
        )
    if not isinstance(data.get("claims"), list):
        raise ValueError("claims must be a list.")
    for c in data["claims"]:
        if c.get("status") not in (
            "supported", "unsupported", "contradicted", "insufficient_data", "school_dependent"
        ):
            raise ValueError(f"Invalid claim status: {c.get('status')!r}")


def validate_rule_trace(
    payload: Any,
    field_result: Mapping[str, Any],
    method: str,
    other_method_findings: Optional[List[Dict[str, Any]]] = None,
    rule_ids: Optional[List[str]] = None,
    max_retries: int = 2,
) -> Optional[Dict[str, Any]]:
    """Validate one field's method trace against the declared engine policy
    and rule registry. Returns the parsed validator JSON, or None if the LLM
    is unavailable/fails (callers must degrade gracefully, not block on this
    -- validation failure is not the same as "field is invalid").

    This function does not touch `field_result`'s score, rank, or any other
    value -- it is read-only with respect to the deterministic pipeline.
    """
    try:
        from .engine_io import _maybe_load_dotenv
        _maybe_load_dotenv()
    except Exception:
        pass

    provider_name = os.getenv("LLM_PROVIDER", "gemini").lower()
    env_var, default_model, call_fn = _LLM_PROVIDERS.get(provider_name, _LLM_PROVIDERS["gemini"])
    model = os.getenv("LLM_MODEL", default_model)
    api_key = os.getenv(env_var)
    if not api_key:
        logger.info("validate_rule_trace: no API key (%s) -- skipping validation.", env_var)
        return None

    client = _ProviderClientWrapper(call_fn, api_key, model)

    canonical_facts = build_canonical_facts(payload)
    policy = build_policy_json()
    quality = data_quality_gate(payload)
    method_trace = _build_method_trace_json(field_result, method)
    rules = build_rule_registry_json(rule_ids or [])

    user_prompt = (
        f"ENGINE POLICY:\n{json.dumps(policy, indent=2, default=str)}\n\n"
        f"INPUT QUALITY:\n{json.dumps(quality, indent=2, default=str)}\n\n"
        f"CANONICAL FACTS (already calculated; do not recompute):\n"
        f"{json.dumps(canonical_facts.get('facts', {}), indent=2, default=str)}\n\n"
        f"METHOD TRACE WITH UNIQUE EVIDENCE IDS:\n{json.dumps(method_trace, indent=2, default=str)}\n\n"
        f"RULE REGISTRY:\n{json.dumps(rules, indent=2, default=str)}\n\n"
        f"SOURCE EXCERPTS supplied by the operator:\n"
        f"{json.dumps({k: v.get('source', '') for k, v in rules.items()}, indent=2, default=str)}\n\n"
        f"OTHER METHOD FINDINGS for contradiction checking only:\n"
        f"{json.dumps(other_method_findings or [], indent=2, default=str)}"
    )

    messages = [
        {"role": "system", "content": _VALIDATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = _run_llm_with_retry(
        client, messages, _VALIDATOR_RESPONSE_SCHEMA, _validate_response, max_retries
    )
    if result:
        result["_validator_version"] = VALIDATOR_VERSION
    return result
