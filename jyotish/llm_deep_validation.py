"""Orchestrates the rule-trace validator -> narrative composer pipeline for
the top-N fields of an engine run.

GAP-FIX (2026-07, "Use an LLM for" policy): wires jyotish/llm_validator.py
and jyotish/llm_composer.py into the actual pipeline (engine.py). Distinct
from -- and layered ON TOP OF -- jyotish/llm.py's existing call_llm_for_fields,
which remains the default lightweight explanation generator for all top-20
fields. This deep-validation step is opt-in (env-gated) because it roughly
doubles LLM call volume for the fields it covers (one validator call + one
composer call per field, versus one batched generator call for all 20), so
it defaults to a small N rather than replacing the existing step outright.

Enable with: JYOTISH_DEEP_VALIDATION=1 (optionally JYOTISH_DEEP_VALIDATION_TOP_N=<int>,
default 5).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from .llm_validator import validate_rule_trace
from .llm_composer import compose_narrative

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 5


def deep_validation_enabled() -> bool:
    return str(os.getenv("JYOTISH_DEEP_VALIDATION", "")).strip().lower() in ("1", "true", "yes")


def _top_n(env_default: int = DEFAULT_TOP_N) -> int:
    try:
        return max(0, int(os.getenv("JYOTISH_DEEP_VALIDATION_TOP_N", str(env_default))))
    except (TypeError, ValueError):
        return env_default


def _other_method_findings(field_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the cross-method comparison input from the field's own already-
    computed per-method scores -- read-only, no recomputation."""
    keys = ("knrao_score", "kp_score", "jaimini_score", "parashara_score",
            "dashamsha_score", "sudarshana_score")
    return [
        {"method": k.replace("_score", ""), "score": field_result.get(k)}
        for k in keys if field_result.get(k) is not None
    ]


def enrich_top_n_with_validation(
    payload: Any,
    results: List[Dict[str, Any]],
    n: int = None,
) -> List[Dict[str, Any]]:
    """For the top N fields (by existing order -- this function NEVER
    reorders or rescoves `results`), run the rule-trace validator and, if
    validation succeeds, the narrative composer. Attaches
    `rule_trace_validation` and `validated_narrative` to each covered field's
    dict in place. Fields beyond N, or any field where the LLM is
    unavailable/fails, are left completely untouched -- this function
    degrades to a no-op per field, never to an error that blocks the run.
    """
    if not deep_validation_enabled():
        return results

    n = n if n is not None else _top_n()
    if n <= 0:
        return results

    covered = 0
    for field_result in results:
        if covered >= n:
            break
        try:
            validation = validate_rule_trace(
                payload, field_result, method="engine_synthesis",
                other_method_findings=_other_method_findings(field_result),
                rule_ids=[
                    "DIGNITY.EXALTATION_DEBILITATION_DEGREES",
                    "DIGNITY.MOOLATRIKONA",
                    "DIGNITY.NAISARGIKA_FRIENDSHIP",
                    "RETROGRADE.VAKRA_NEECHA_BHANGA",
                    "COMBUSTION.PER_PLANET_ORBS",
                    "COMBUSTION.CAZIMI",
                    "NAKSHATRA.RAHU_KETU_ASPECT",
                    "VARGOTTAMA.SAME_SIGN_D1_D9",
                    "VIMSHOPAKA.DASAVARGA_WEIGHTS",
                    "CONFLUENCE.THREE_SOURCE_MINIMUM",
                    "DASHA.VIMSHOTTARI_YEAR_LENGTH",
                    "KARAKA.SYSTEMATIC_FIELD_TABLE",
                    "BHAVA.COMPOSITE_HOUSE_STRENGTH",
                    "GRAHA_YUDDHA.DEGREE_WINNER",
                    "TAJIKA.APPLYING_SEPARATING_ORB",
                    "ASHTAKAVARGA.SAV_BINDU_SCALING",
                    "GOCHAR.SATURN_HOUSE_TRANSIT",
                ],
            )
        except Exception as exc:
            logger.warning("Deep validation failed for %s: %s", field_result.get("field_id"), exc)
            validation = None

        if not validation:
            covered += 1
            continue

        field_result["rule_trace_validation"] = validation

        try:
            narrative = compose_narrative(
                validated_claims=validation.get("claims", []),
                scores={
                    "final_score": field_result.get("final_score"),
                    "score_confidence": field_result.get("score_confidence", ""),
                },
                practical_profile={
                    "field_label": field_result.get("field_label", ""),
                    "domain": field_result.get("domain", ""),
                },
            )
        except Exception as exc:
            logger.warning("Narrative composition failed for %s: %s", field_result.get("field_id"), exc)
            narrative = None

        if narrative:
            field_result["validated_narrative"] = narrative

        covered += 1

    return results
