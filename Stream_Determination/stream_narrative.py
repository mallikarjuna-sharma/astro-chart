"""Consent-gated, explanation-only student and astrology narratives.

The deterministic stream decision is immutable here.  The LLM receives a
minimized evidence packet and may only explain that decision.  Every failure
falls back to a local narrative, so report generation never depends on an
external provider.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict


# "gpt-5.6-sol" (this constant's prior value) is not a real model in this
# project -- every other OpenAI call site (jyotish/llm.py DEFAULT_MODELS,
# career_validation_prompt.py, llm_narrative_builder.py) uses "gpt-5.4-mini"
# as the known-working default, which is almost certainly why live calls
# were returning HTTP 400 Bad Request (unrecognized model). Aligned here.
DEFAULT_OPENAI_NARRATIVE_MODEL = "gpt-5.4-mini"
NARRATIVE_CONTRACT = "stream-narrative.v1"
_STREAMS = {"science", "commerce", "humanities"}
_PLANETS = {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"}
_SIGNS = {"Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio",
          "Sagittarius", "Capricorn", "Aquarius", "Pisces"}
_DIGNITIES = {"exalted", "debilitated", "moolatrikona", "own sign", "great friend",
              "friend", "neutral", "enemy", "great enemy", "neecha bhanga"}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def runtime_consent_default() -> bool:
    """Environment default; CLI/API callers may explicitly override it."""
    return _bool_env("LLM_REPORT_CONSENT", False)


def narrative_enabled_default() -> bool:
    """Environment default for the --llm-narrative switch itself.

    Previously `include_llm_narrative` had no env-driven default -- every
    caller (CLI and programmatic, including batch drivers like
    run_full_audit.py) had to opt in per-call with `--llm-narrative` /
    `include_llm_narrative=True`, so turning the feature on for an entire
    environment meant editing every call site. LLM_NARRATIVE_ENABLED in
    .env now controls the switch itself, mirroring LLM_REPORT_CONSENT's
    existing per-environment consent default. Explicit CLI/API args still
    override this (e.g. `--llm-narrative=false` on one run even when the
    env default is on).
    """
    return _bool_env("LLM_NARRATIVE_ENABLED", False)


def build_stream_narrative_evidence(payload: Any, determination: Dict[str, Any]) -> Dict[str, Any]:
    """Return the minimized, calculated-only packet permitted to leave process."""
    streams = determination.get("streams") or []
    return {
        "student_label": (getattr(payload, "name", "") or "the student").split()[0],
        "current_age": getattr(payload, "current_age", None),
        "decision": {
            "top_ranked_stream": determination.get("top_ranked_stream"),
            "dominant_stream": determination.get("dominant_stream"),
            "recommendation_status": determination.get("recommendation_status"),
            "tied_streams": determination.get("tied_streams") or [],
            "resolution_stage": determination.get("precedence_chain_resolution_stage"),
        },
        "precedence_chain": determination.get("precedence_chain_detail") or {},
        "planet_strengths": determination.get("planet_strengths") or {},
        "streams": [
            {
                "stream_id": stream.get("stream_id"),
                "label": stream.get("label"),
                "normalized_score": stream.get("normalized_score"),
                "sub_archetype": stream.get("sub_archetype"),
                "sections": [
                    {
                        "section": section.get("section"),
                        "display": section.get("display"),
                        "note": section.get("note"),
                    }
                    for section in ((stream.get("score_rubric") or {}).get("sections") or [])
                ],
                "subjects": [
                    {"label": subject.get("label"), "score": subject.get("score"),
                     "core": bool(subject.get("core"))}
                    for subject in (stream.get("subjects") or [])[:5]
                ],
                # Round 4 addition: names only (no scores/strengths -- keeps
                # this packet minimal, consistent with the rest of this
                # function's "minimized, calculated-only" evidence
                # convention) of any classically-detected yoga relevant to
                # this stream, so the LLM prompt/fallback narrative MAY
                # mention one if present. Empty list is the normal case and
                # must not change narrative generation.
                "yogas_present": [
                    y.get("yoga_name") for y in (stream.get("yoga_detection", {}) or {}).get("contributing_yogas", [])
                    if y.get("relevant_to_this_stream")
                ],
            }
            for stream in streams
        ],
        "limitations": {
            "input_quality": determination.get("input_quality") or {},
            "evidence_completeness": determination.get("evidence_completeness"),
            "age_routing_note": determination.get("age_routing_note"),
            "scores_are_probabilities": False,
        },
    }


# GAP FIX (2026-08-21, remediation plan item 2.6; source:
# audit/CURRENT_ASTROLOGICAL_LOGIC_AND_LLM_VALIDATION_AUDIT_2026-07-17.md,
# "Best production prompt: rule-trace validator" section). That section
# specs a fuller validator design: per-claim OBSERVED/DERIVED/TRADITIONAL/
# HEURISTIC/CONCLUSION classification, source-support checking, and
# birth-time-sensitivity tagging. jyotish/llm_validator.py already
# implements the full per-claim version of that design for the rule-trace
# validator pipeline (see VALIDATOR_VERSION there). This module's
# `validation` block, however, is a different, narrower validator (schema_
# valid/facts_grounded/decision_unchanged/unsupported_claims only) that
# runs on the free-form 3-4 paragraph student/astrological narratives
# produced here -- there is no per-claim list in this module's LLM output
# schema to classify individually without a breaking prompt/schema change,
# which is too large a change to make safely in this pass (untested
# Phase 1 changes still pending pytest verification).
#
# Implemented here as an ADDITIVE, deterministic (non-LLM) partial version:
# - birth_time_sensitivity: reuses the exact none/low/medium/high/unknown
#   vocabulary llm_validator.py's schema already uses for the same concept,
#   computed from the evidence packet's own input_quality/age_routing_note
#   fields (no new LLM call, no schema risk).
# - claim_classification: a coarse, SECTION-level (not per-claim) tag using
#   the same observed/derived/traditional/heuristic/conclusion vocabulary --
#   student_narrative is a conclusion restating the locked decision;
#   astrological_narrative is derived/traditional reasoning presented from
#   the calculated evidence. This is explicitly labeled as section-level,
#   not per-sentence, to avoid overstating precision.
# Deferred: true per-claim classification and source_support checking would
# require restructuring the LLM output into an itemized claims list (like
# llm_validator.py's schema) -- left for a future, non-conservative pass.
def _birth_time_sensitivity(evidence: Dict[str, Any]) -> str:
    """Deterministic birth-time-sensitivity classification for this
    narrative's underlying evidence, using the same vocabulary as
    llm_validator.py's per-claim `birth_time_sensitivity` field.

    D24/dasha-window facts (referenced in the astrological_narrative
    paragraphs built by _fallback_narrative and expected of the LLM prompt)
    are birth-time sensitive; the exact sensitivity band depends on how
    precise/uncertain the input birth time was.
    """
    quality = (evidence.get("limitations") or {}).get("input_quality") or {}
    if not isinstance(quality, dict) or not quality:
        return "unknown"
    precision = str(quality.get("birth_time_precision", "") or "").lower()
    try:
        uncertainty = int(quality.get("birth_time_uncertainty_minutes", 0) or 0)
    except (TypeError, ValueError):
        uncertainty = 0
    if precision == "exact" and uncertainty <= 2:
        return "low"
    if precision in ("", "unknown"):
        return "unknown"
    if uncertainty <= 5:
        return "low"
    if uncertainty <= 30:
        return "medium"
    return "high"


def _claim_classification() -> Dict[str, str]:
    """Coarse, section-level (not per-sentence) claim-type tagging -- see
    the GAP FIX comment above this function for why per-claim tagging is
    deferred."""
    return {
        "student_narrative": "conclusion",
        "astrological_narrative": "derived_and_traditional",
        "granularity": "section_level_not_per_claim",
    }


def _fallback_narrative(evidence: Dict[str, Any], *, status: str, reason: str) -> Dict[str, Any]:
    decision = evidence["decision"]
    name = evidence.get("student_label") or "The student"
    top = decision.get("top_ranked_stream") or "no single stream"
    tied = decision.get("tied_streams") or []
    streams = {row["stream_id"]: row for row in evidence.get("streams", [])}
    top_row = streams.get(top, {})
    subjects = [s.get("label") for s in top_row.get("subjects", []) if s.get("label")][:3]
    subject_text = ", ".join(subjects) or "the strongest-scoring subjects"
    stage = decision.get("resolution_stage") or "not available"
    d1_scores = (evidence.get("precedence_chain") or {}).get("d1_promise_scores") or {}

    if tied:
        recommendation = (
            f"The chart does not justify forcing one stream for {name}. "
            f"{' and '.join(tied)} remain genuine alternatives after the full classical precedence chain."
        )
        practical = (
            "Compare the core subjects in both streams through school performance, sustained interest, "
            "teacher feedback and a short aptitude exercise before choosing."
        )
    else:
        recommendation = (
            f"The recommended stream for {name} is {str(top).title()}. "
            "This is the engine's locked deterministic conclusion, not a choice made by the narrative model."
        )
        practical = (
            f"The most relevant subjects to explore first are {subject_text}. "
            "Use current grades, interest and school availability as practical confirmation before enrolment."
        )

    student = [
        recommendation,
        ("This direction reflects the chart's relative pattern of learning capacity, educational support "
         "and subject fit. The scores are internal support indices, not probabilities or guarantees."),
        practical,
    ]
    astrology = [
        (f"The rāśi/D1 promise was evaluated first, with D1-only stream values recorded as {d1_scores}. "
         "D24 was treated as the fruit and refinement of that promise, never as a peer vote capable of creating it."),
        (f"The precedence chain reached the stage '{stage}'. Same-sign D1→D24 persistence was checked first, "
         "followed by computed effective strength with dignity used only as fallback."),
        ("Where required, the engine then examined Amatyakaraka and Atmakaraka relative to Karakamsha, "
         "followed by active mahadasha, antardasha/bhukti, Chara dasha and the imminent mahadasha window."),
        ("Only calculated facts present in the report are asserted. Missing evidence remains missing, and an "
         "unresolved tie is reported as a tie rather than converted into a recommendation."),
    ]
    # Round 4 addition: conservative, optional mention of any classical
    # yoga(s) detected as relevant to the top-ranked (or, when tied, first
    # tied) stream -- purely additive, only appended when the list is
    # non-empty, so a chart with no detected yoga produces byte-identical
    # narrative output to before this change.
    _yoga_row = streams.get(top if not tied else (tied[0] if tied else top), {})
    _yogas = _yoga_row.get("yogas_present") or []
    if _yogas:
        astrology.append(
            f"The chart also shows {', '.join(_yogas)} relevant to this stream -- a supplementary "
            "classical pattern, not an independent source of the recommendation above."
        )
    return {
        "contract": NARRATIVE_CONTRACT,
        "status": status,
        "provider": "deterministic",
        "model": None,
        "decision_locked": True,
        "reason": reason,
        "student_narrative": {"paragraphs": student, "recommended_stream": None if tied else top,
                              "secondary_streams": tied},
        "astrological_narrative": {"paragraphs": astrology, "resolution_stage": stage},
        # GAP FIX (2026-08-21, item 2.6): birth_time_sensitivity and
        # claim_classification are ADDITIVE fields -- the four original
        # keys are unchanged so any existing reader of this block still
        # works. See the GAP FIX comment above _birth_time_sensitivity.
        "validation": {"schema_valid": True, "facts_grounded": True,
                       "decision_unchanged": True, "unsupported_claims": [],
                       "birth_time_sensitivity": _birth_time_sensitivity(evidence),
                       "claim_classification": _claim_classification()},
    }


def _prompt(evidence: Dict[str, Any]) -> str:
    return """Role: Write a student-friendly educational-stream explanation from the supplied calculated evidence.

Goal: Return JSON containing student_narrative and astrological_narrative. Explain the locked deterministic decision; never choose, rescore, reorder or override it.

Success criteria:
- student_narrative.paragraphs contains exactly 3 or 4 concise paragraphs
- astrological_narrative.paragraphs contains exactly 3 or 4 concise paragraphs
- recommended_stream exactly equals decision.dominant_stream; use null when it is null
- for a genuine tie, explain both candidates and do not manufacture a winner
- explain D1 as the tree/promise and D24 as its education-specific fruit/refinement
- present the actual vargottama, computed-strength/dignity, AK/AmK-Karakamsha and dasha facts supplied

Constraints:
- use only the evidence JSON; invent no sign, house, dignity, yoga, aspect, planet strength or dasha
- scores are internal indices, never probabilities
- do not expose DOB, location or birth time
- avoid fatalism and guarantees

Output exactly this JSON shape:
{"student_narrative":{"paragraphs":["..."],"recommended_stream":null,"secondary_streams":[]},"astrological_narrative":{"paragraphs":["..."],"resolution_stage":"..."}}

EVIDENCE_JSON:
""" + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))


def _clean_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("narrative response must be a JSON object")
    return parsed


def _validate(parsed: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    student = parsed.get("student_narrative") or {}
    astrology = parsed.get("astrological_narrative") or {}
    sp = student.get("paragraphs") or []
    ap = astrology.get("paragraphs") or []
    if not (3 <= len(sp) <= 4 and all(isinstance(p, str) and p.strip() for p in sp)):
        raise ValueError("student narrative must contain 3-4 non-empty paragraphs")
    if not (3 <= len(ap) <= 4 and all(isinstance(p, str) and p.strip() for p in ap)):
        raise ValueError("astrological narrative must contain 3-4 non-empty paragraphs")
    locked = evidence["decision"].get("dominant_stream")
    recommended = student.get("recommended_stream")
    if recommended != locked:
        raise ValueError(f"LLM attempted decision change: expected {locked!r}, got {recommended!r}")
    if recommended is not None and recommended not in _STREAMS:
        raise ValueError("unknown recommended stream")
    if astrology.get("resolution_stage") != evidence["decision"].get("resolution_stage"):
        raise ValueError("resolution stage changed")
    evidence_text = json.dumps(evidence, ensure_ascii=False).lower()
    narrative_text = " ".join(ap)
    unsupported = []
    for entity in sorted(_PLANETS | _SIGNS):
        if re.search(rf"\b{re.escape(entity)}\b", narrative_text, flags=re.I) and entity.lower() not in evidence_text:
            unsupported.append(entity)
    for dignity in sorted(_DIGNITIES):
        if dignity in narrative_text.lower() and dignity not in evidence_text:
            unsupported.append(dignity)
    for house in set(re.findall(r"\bH(?:ouse\s*)?(\d{1,2})\b", narrative_text, flags=re.I)):
        if not re.search(rf"(?:\bH|house\s*){re.escape(house)}\b", evidence_text, flags=re.I):
            unsupported.append(f"house {house}")
    if "yoga" in narrative_text.lower() and "yoga" not in evidence_text:
        unsupported.append("unsupported yoga")
    if unsupported:
        raise ValueError("unsupported astrological claims: " + ", ".join(sorted(set(unsupported))))

    # 2026-08-22 audit fix (gap 8): the checks above only confirm an entity
    # (planet/sign/dignity/house) is MENTIONED somewhere in the evidence
    # packet -- they never check it is CHARACTERIZED correctly, e.g. the
    # narrative could claim "Jupiter supports Science" when the evidence
    # packet's own per-stream section notes attribute Jupiter's contribution
    # to Humanities instead. Conservative, regex/string-matching level
    # (consistent with the entity-mention checks above, not a full NLU
    # rewrite): scan for a "<Planet> ... <supports/favors/etc> ... <Stream>"
    # pattern in the astrological narrative, and reject it if that planet
    # does not actually appear in THAT stream's own section notes in the
    # evidence packet (i.e. scoring never attributed that planet's
    # contribution to the claimed stream).
    _stream_section_text = {
        row.get("stream_id"): " ".join(
            str(sec.get("note") or "") for sec in (row.get("sections") or [])
        ).lower()
        for row in evidence.get("streams", [])
        if row.get("stream_id")
    }
    _support_verbs = r"(?:support[s]?|favor[s]?|favour[s]?|indicat(?:es|ing|e)?|point[s]?\s+toward|strengthen[s]?|back[s]?|driv(?:es|ing|e)?)"
    _stream_words = r"(Science|Commerce|Humanities)"
    misattributed = []
    for match in re.finditer(
        rf"\b({'|'.join(sorted(_PLANETS))})\b[^.]{{0,60}}?{_support_verbs}[^.]{{0,40}}?\b{_stream_words}\b",
        narrative_text, flags=re.I,
    ):
        claimed_planet, claimed_stream = match.group(1), match.group(2)
        stream_id = claimed_stream.lower()
        stream_text = _stream_section_text.get(stream_id, "")
        if claimed_planet.lower() not in stream_text:
            misattributed.append(f"{claimed_planet}->{claimed_stream}")
    if misattributed:
        raise ValueError(
            "narrative attributes planet support to a stream the evidence packet's own "
            "scoring does not: " + ", ".join(sorted(set(misattributed)))
        )
    return {"student_narrative": student, "astrological_narrative": astrology}


def generate_stream_narrative(
    payload: Any,
    determination: Dict[str, Any],
    *,
    enabled: bool = False,
    runtime_consent: bool = False,
    model: str | None = None,
    caller: Callable[[str, str, str], str] | None = None,
) -> Dict[str, Any]:
    """Generate an OpenAI narrative when both consent gates are true."""
    evidence = build_stream_narrative_evidence(payload, determination)
    if not enabled:
        return _fallback_narrative(evidence, status="SKIPPED_DISABLED", reason="llm narrative switch is off")
    chart_consent = bool(getattr(payload, "external_llm_consent", False))
    if not runtime_consent or not chart_consent:
        missing = []
        if not runtime_consent:
            missing.append("runtime --llm-consent/LLM_REPORT_CONSENT")
        if not chart_consent:
            missing.append("chart external_llm_consent")
        return _fallback_narrative(evidence, status="SKIPPED_NO_CONSENT", reason="missing: " + ", ".join(missing))
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _fallback_narrative(evidence, status="FALLBACK", reason="OPENAI_API_KEY is not configured")
    model = model or os.getenv("OPENAI_NARRATIVE_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_OPENAI_NARRATIVE_MODEL
    if caller is None:
        from jyotish.llm import _call_openai
        caller = _call_openai
    try:
        parsed = _clean_json(caller(_prompt(evidence), api_key, model))
        validated = _validate(parsed, evidence)
        return {
            "contract": NARRATIVE_CONTRACT,
            "status": "GENERATED",
            "provider": "openai",
            "model": model,
            "decision_locked": True,
            **validated,
            # GAP FIX (2026-08-21, item 2.6): additive fields, see
            # _fallback_narrative's identical addition above for rationale.
            "validation": {"schema_valid": True, "facts_grounded": True,
                           "decision_unchanged": True, "unsupported_claims": [],
                           "birth_time_sensitivity": _birth_time_sensitivity(evidence),
                           "claim_classification": _claim_classification()},
        }
    except Exception as exc:
        return _fallback_narrative(evidence, status="FALLBACK", reason=f"OpenAI narrative failed: {type(exc).__name__}: {exc}")
