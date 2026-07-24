"""Schemas for education analysis APIs (UG career field + PUC stream)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EducationAnalysisRequest(BaseModel):
    user_json: dict[str, Any] = Field(
        ...,
        description=(
            "Consolidated chart JSON (system_config, student_context, "
            "pyhora_calculations, …) — consolidated chart from /api/consolidated."
        ),
    )


class ProfileEducationAnalysisRequest(BaseModel):
    user_json: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Consolidated chart JSON used to compute the analysis on a cache miss. "
            "Optional: omit it when you expect a cached result to already exist."
        ),
    )


class AiDiagnostics(BaseModel):
    """Temporary LLM diagnostics — for operator verification only."""

    success: str = Field(default="", description="Success explanation when LLM narrative ran.")
    error: str = Field(default="", description="Error explanation when LLM narrative failed or was skipped.")


class EducationAnalysisResponse(BaseModel):
    analysis_type: str = Field(default="ug", description="``ug`` for undergraduate career-field analysis.")
    engine_version: str = Field(..., description="Jyotish career engine version.")
    generated_at: str = Field(..., description="ISO-8601 timestamp (UTC).")
    default_tab: str | None = Field(
        default=None,
        description="Suggested UI tab based on student age: ``puc`` for ages 15–17, else ``ug``.",
    )
    student: dict[str, Any] = Field(..., description="Student/chart summary for the report header.")
    summary: dict[str, Any] = Field(
        ...,
        description="Parent and astrologer overview text from the LLM selection step.",
    )
    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Payload 1 — ranked career-field rows (scores, LLM reasons, registry metadata).",
    )
    macro_clusters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Payload 2 — named macro clusters with strength percentages.",
    )
    report: dict[str, Any] = Field(
        ...,
        description="Payload 3 — the 14-section narrative report (final_identity, snapshot, routes, …).",
    )
    chart_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Payload 4 — chart-signature facts (lagna, dasha lords, tier recommendation, edu stream).",
    )
    fields: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Back-compat alias of `results`.",
    )
    report_bundle: dict[str, Any] | None = Field(
        default=None,
        description="Structured convenience bundle (student, summary, top matches, fields, payload).",
    )
    career_field_report: dict[str, Any] | None = Field(
        default=None,
        description="Macro clusters, chart facts, and LLM narrative sections for the v2 report.",
    )
    profile_id: str | None = Field(
        default=None,
        description="Birth profile this analysis belongs to (set for the persisted, profile-scoped endpoint).",
    )
    user_id: str | None = Field(
        default=None,
        description="Logged-in user who owns this analysis.",
    )
    cached: bool | None = Field(
        default=None,
        description="True when served from DynamoDB; False when freshly computed by the engine.",
    )
    AI: AiDiagnostics | None = Field(
        default=None,
        description="Temporary operator diagnostics for LLM/OpenAI/Gemini call status.",
    )


class PucAnalysisResponse(BaseModel):
    analysis_type: str = Field(default="puc", description="PUC stream determination analysis.")
    engine_version: str = Field(..., description="Stream determination engine version.")
    generated_at: str = Field(..., description="ISO-8601 timestamp (UTC).")
    default_tab: str | None = Field(
        default=None,
        description="Suggested UI tab based on student age: ``puc`` for ages 15–17, else ``ug``.",
    )
    student: dict[str, Any] = Field(..., description="Student/chart summary.")
    report: dict[str, Any] = Field(..., description="Full stream-determination report JSON.")
    stream_narrative: dict[str, Any] | None = Field(
        default=None,
        description="LLM or fallback narrative explaining the locked stream decision.",
    )
    AI: AiDiagnostics | None = Field(
        default=None,
        description="Temporary operator diagnostics for LLM/OpenAI/Gemini call status.",
    )

