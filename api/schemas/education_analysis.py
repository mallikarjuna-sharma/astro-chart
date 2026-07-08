"""Schemas for POST /api/education-analysis."""
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


class EducationAnalysisResponse(BaseModel):
    engine_version: str = Field(..., description="Jyotish career engine version.")
    generated_at: str = Field(..., description="ISO-8601 timestamp (UTC).")
    student: dict[str, Any] = Field(..., description="Student/chart summary for the report header.")
    summary: dict[str, Any] = Field(
        ...,
        description="Parent and astrologer overview text from the LLM selection step.",
    )
    fields: list[dict[str, Any]] = Field(
        ...,
        description="Ranked career-field results (scores, LLM reasons, registry metadata).",
    )
    report: dict[str, Any] = Field(
        ...,
        description="Structured report payload (includes payload + fields for client-side HTML rendering).",
    )
    report_html: str | None = Field(
        default=None,
        description="Full career field recommendation report HTML (v2 rich layout).",
    )
    career_field_report: dict[str, Any] | None = Field(
        default=None,
        description="Macro clusters, chart facts, and LLM narrative sections for the v2 report.",
    )
