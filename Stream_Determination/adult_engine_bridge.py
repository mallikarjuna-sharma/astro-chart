"""adult_engine_bridge.py — single owner of "run Field_Determination's adult
engine against a Stream_Determination payload" for BOTH consumers that need
it: cross_validate.py (report-only comparison) and field_derived_stream.py
(an optional, capped, score-affecting rubric section).

Why this exists as its own module rather than each caller invoking
jyotish.engine.run_engine() itself: two independent adult-engine call sites
drifting apart (different LLM-suppression handling, different payload
mutation risk, different field-extraction shape) is exactly the kind of
silent inconsistency this codebase's own audits have repeatedly caught
elsewhere (see stream_scoring.py's SCORING_CONTRACT_VERSION history). One
bridge, one contract, both callers share it.

Age-router note: the under-15 diversion to Stream_Determination lives ONLY
in Field_Determination/education_engine.py's __main__ block -- confirmed by
inspection, jyotish.engine.run_engine() itself contains no reference to
Stream_Determination or an age check. Calling run_engine() directly (as this
bridge does) therefore does NOT re-trigger the age gate and cannot recurse
back into Stream_Determination. This is safe specifically because both of
this bridge's callers are only ever invoked from within Stream_Determination
itself, on a payload that has already been confirmed <15 by the caller's own
is_eligible() check upstream -- this bridge does not perform or rely on any
age check of its own.

LLM determinism: identical pattern to what cross_validate.py used before
this bridge existed -- payload.external_llm_consent is forced to False for
the duration of the call and restored (or removed, if it wasn't set before)
in a `finally` block, so a failure mid-call never leaves the payload's
consent flag altered for any other caller.

Payload safety: the payload is deep-copied before being handed to
run_engine() so this bridge can never mutate the caller's own chart object,
regardless of what run_engine() does internally.

2026-08-22 audit fix (gap 10, KNOWN ACCEPTED LIMITATION, documentation only):
the under-15/adult engine choice is a hard age cutoff (see
early_age_stream_engine.py::is_eligible's own matching note) with no
smoothing across the boundary -- a chart at current_age just below
AGE_THRESHOLD_YEARS is scored entirely by Stream_Determination, and the same
chart just at/above it is scored entirely by Field_Determination's adult
engine, two independently-tuned engines that can disagree. This bridge
module only fetches SUPPLEMENTARY adult-engine evidence for an
already-under-15 chart (cross_validate.py's report-only comparison,
field_derived_stream.py's optional capped section) -- it never runs as an
alternative full determination for a boundary chart, so it has no natural
place to blend two determinations even if that were otherwise safe. The
actual dispatch decision lives in Field_Determination/education_engine.py's
__main__ block, outside this directory, so a same-run blend is out of scope
for a bounded fix here; documenting the discontinuity is the safe choice.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class FieldEngineSnapshot:
    """Small, stable read-only view over one adult-engine run's per-field
    results -- only the keys field_derived_stream.py/cross_validate.py
    actually need, not the full internal engine.py row (which carries dozens
    of internal-scoring keys that are not appropriate as external contract
    surface)."""
    engine_version: str
    scoring_contract_version: str
    fields: Tuple[Dict[str, Any], ...]
    career_cluster_report: Dict[str, Any]
    warnings: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.warnings and bool(self.fields)


_FIELD_KEYS = (
    "field_id", "field_label", "domain", "career_family", "career_family_label",
    "competency", "competency_label", "confidence_band", "score_confidence",
    "final_score", "pre_norm_score",
)


def _normalize_field_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Whitelist down to the small, stable subset of engine.py's per-field
    row this bridge exposes -- deliberately excludes route/timing/dasha
    internals (gap_boost, method_*, calc_trace, explanation_chain, etc.):
    those are legitimate inputs to the ADULT vocational recommendation but
    are not being re-derived here, only the field's overall computed
    strength (pre_norm_score) and its stable identity/family/domain tags."""
    return {k: row.get(k) for k in _FIELD_KEYS}


def get_field_engine_snapshot(payload: Any) -> FieldEngineSnapshot:
    """Run Field_Determination's adult engine on a deep copy of `payload` and
    return a small, stable snapshot of its per-field results.

    Raises on failure -- callers that must not let this take down a primary
    report should use safe_get_field_engine_snapshot() instead.
    """
    from jyotish.engine import run_engine

    payload_copy = copy.deepcopy(payload)

    _had_attr = hasattr(payload_copy, "external_llm_consent")
    _orig_consent = getattr(payload_copy, "external_llm_consent", None)
    payload_copy.external_llm_consent = False
    try:
        results = run_engine(payload_copy, enable_llm=False)
    finally:
        if _had_attr:
            payload_copy.external_llm_consent = _orig_consent
        elif hasattr(payload_copy, "external_llm_consent"):
            delattr(payload_copy, "external_llm_consent")

    if not results:
        return FieldEngineSnapshot(
            engine_version="", scoring_contract_version="", fields=(),
            career_cluster_report={}, warnings=("run_engine() returned no results",),
        )

    cluster_report = results[0].get("career_cluster_report", {}) or {}
    fields = tuple(_normalize_field_row(r) for r in results)
    return FieldEngineSnapshot(
        engine_version=str(results[0].get("engine_version", "")),
        scoring_contract_version=str(results[0].get("scoring_contract_version", "")),
        fields=fields,
        career_cluster_report=cluster_report,
        warnings=(),
    )


def safe_get_field_engine_snapshot(payload: Any) -> FieldEngineSnapshot:
    """Error-safe wrapper -- returns an empty, warnings-populated snapshot on
    any failure instead of raising, for callers that must not let this
    OPTIONAL adult-engine bridge take down a primary Stream_Determination
    report or score."""
    try:
        return get_field_engine_snapshot(payload)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
        return FieldEngineSnapshot(
            engine_version="", scoring_contract_version="", fields=(),
            career_cluster_report={},
            warnings=(f"{type(exc).__name__}: {exc}",),
        )
