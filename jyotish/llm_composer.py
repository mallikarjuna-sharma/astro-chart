"""Narrative composer LLM call.

GAP-FIX (2026-07, "Use an LLM for" policy, implemented per user spec):
implements "translating deterministic evidence into cautious, readable
prose" as its OWN step, downstream of and gated by jyotish/llm_validator.py
-- distinct from jyotish/llm.py's existing call_llm_for_fields, which
generates prose directly from raw chart facts with no validation step and no
enforced uncertainty/disclaimer language.

Hard boundary: this function is given ONLY the validator's already-checked
claims (`validated_claims`), the deterministic scores (read-only, never
recomputed or restated as a probability), and non-astrological practical
profile facts. It has no access to raw ephemeris data, so it cannot recompute
or contradict a calculation even if it wanted to -- the boundary is enforced
structurally, not just by instruction.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .llm import _LLM_PROVIDERS, _ProviderClientWrapper, _run_llm_with_retry

logger = logging.getLogger(__name__)

COMPOSER_VERSION = "narrative-composer.v1"

_COMPOSER_SYSTEM_PROMPT = """Compose a cautious Jyotisha interpretation using only the supplied validated claims.
Do not add placements, yogas, dates, causal statements, remedies, probabilities or career
recommendations. Preserve uncertainty and school-dependence. Never describe a model score
as a probability. If evidence conflicts, state the conflict. Separate traditional symbolism
from practical, non-astrological career advice. Output JSON only."""

_COMPOSER_RESPONSE_SCHEMA = {
    "name": "narrative_composer",
    "schema": {
        "type": "object",
        "properties": {
            "traditional_interpretation": {"type": "string"},
            "supporting_claim_ids": {"type": "array", "items": {"type": "string"}},
            "contradictions": {"type": "array", "items": {"type": "string"}},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
            "practical_recommendations": {"type": "array", "items": {"type": "string"}},
            "disclaimer": {"type": "string"},
        },
        "required": ["traditional_interpretation", "supporting_claim_ids", "contradictions",
                      "uncertainties", "practical_recommendations", "disclaimer"],
        "additionalProperties": False,
    },
    "strict": True,
}

_REQUIRED_DISCLAIMER = (
    "Traditional interpretive guidance; not scientifically validated or a substitute "
    "for professional career, financial, legal, or medical advice."
)


def _validate_composer_response(data: Dict[str, Any]) -> None:
    text_fields = " ".join([
        str(data.get("traditional_interpretation", "")),
        " ".join(data.get("practical_recommendations", []) or []),
    ]).lower()
    # Cheap, non-exhaustive guardrail: catch the most obvious probability-language
    # violation before it reaches a user. This is a backstop, not a substitute for
    # the prompt instruction -- genuine enforcement is upstream (validator gating
    # what facts even reach this step).
    for banned in ("% chance", "percent chance", "probability of", "guaranteed", "certain to"):
        if banned in text_fields:
            raise ValueError(f"Composer output used probability/certainty language: {banned!r}")
    if not data.get("disclaimer"):
        raise ValueError("disclaimer is required and must not be empty.")


def compose_narrative(
    validated_claims: List[Dict[str, Any]],
    scores: Dict[str, Any],
    practical_profile: Optional[Dict[str, Any]] = None,
    max_retries: int = 2,
) -> Optional[Dict[str, Any]]:
    """Compose a cautious narrative from already-validated claims only.

    `validated_claims`: the `claims` array from one or more
        jyotish/llm_validator.py::validate_rule_trace() calls -- claims that
        failed validation (status="unsupported"/"contradicted") should
        generally be excluded or explicitly passed through so the composer
        can state the conflict, per its own instruction to "state the
        conflict" rather than silently drop it.
    `scores`: deterministic scores ONLY (e.g. {"final_score": 82.4,
        "score_confidence": "MODERATE"}) -- read-only, must not be
        recomputed or reframed as a probability (enforced by
        _validate_composer_response above as a backstop).
    `practical_profile`: non-astrological facts (interests, prior
        achievements) the composer may use for practical_recommendations
        WITHOUT presenting them as astrological evidence.
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
        logger.info("compose_narrative: no API key (%s) -- skipping composition.", env_var)
        return None

    client = _ProviderClientWrapper(call_fn, api_key, model)

    user_prompt = (
        f"VALIDATED CLAIMS: {json.dumps(validated_claims, indent=2, default=str)}\n\n"
        f"DETERMINISTIC SCORES: {json.dumps(scores, indent=2, default=str)}\n\n"
        f"PRACTICAL PROFILE FACTS: {json.dumps(practical_profile or {}, indent=2, default=str)}"
    )

    messages = [
        {"role": "system", "content": _COMPOSER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = _run_llm_with_retry(
        client, messages, _COMPOSER_RESPONSE_SCHEMA, _validate_composer_response, max_retries
    )
    if result:
        # Belt-and-suspenders: force the exact required disclaimer text even if
        # the model paraphrased it, since this is a compliance-sensitive field.
        result["disclaimer"] = _REQUIRED_DISCLAIMER
        result["_composer_version"] = COMPOSER_VERSION
    return result
