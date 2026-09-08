"""Schemas for POST /api/business-prediction."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BusinessPredictionRequest(BaseModel):
    user_json: dict[str, Any] = Field(
        ...,
        description=(
            "Consolidated chart JSON (system_config, student_context, "
            "pyhora_calculations, …) — typically the response of /api/consolidated."
        ),
    )
    venture_type: str = Field(
        default="business",
        description='One of "business", "independent", or "family_business".',
    )
    years_ahead: int = Field(
        default=15,
        ge=1,
        le=40,
        description="How many years ahead to score timed windows.",
    )


class ProfileBusinessPredictionRequest(BaseModel):
    venture_type: str = Field(
        default="business",
        description='One of "business", "independent", or "family_business".',
    )
    years_ahead: int = Field(default=15, ge=1, le=40)
    user_json: dict[str, Any] | None = Field(
        default=None,
        description="Legacy fallback — omit to load consolidated chart data from the profile.",
    )


class BusinessPredictionResponse(BaseModel):
    engine_version: str
    generated_at: str = Field(..., description="ISO-8601 timestamp (UTC).")
    profile_id: str | None = Field(
        default=None,
        description="Birth profile this prediction belongs to (profile-scoped endpoint).",
    )
    user_id: str | None = Field(
        default=None,
        description="Logged-in user who owns this prediction.",
    )
    cached: bool | None = Field(
        default=None,
        description="True when served from the profile record; False when freshly computed.",
    )
    student: dict[str, Any] = Field(..., description="Student/chart summary for the report header.")
    prediction: dict[str, Any] = Field(
        ...,
        description="Full compute_business_prediction() output.",
    )
    report: dict[str, Any] = Field(
        ...,
        description="UI-oriented view model (KPIs, sectors, windows, verdict, etc.).",
    )
    model_status: str = ""
    calibration_status: str = ""
    rule_pack_version: str = ""
