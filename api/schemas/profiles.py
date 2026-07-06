"""Schemas for JyotishProfiles — up to 4 birth profiles per authenticated user."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from api.schemas.chart import BirthChartBody


class CreateProfileRequest(BaseModel):
    profile_name: str = Field(min_length=2, max_length=64)
    birth_input: BirthChartBody
    user_info: dict[str, Any] = Field(default_factory=dict)
    student_context: dict[str, Any] | None = None
    career_context: dict[str, Any] = Field(default_factory=dict)
    enrich_llm_career: bool = True

    @field_validator("profile_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class ProfileSummary(BaseModel):
    profile_id: str
    profile_name: str
    place_label: str = ""
    birth_local: str = ""
    created_at: str
    updated_at: str


class ProfileListResponse(BaseModel):
    profiles: list[ProfileSummary]
    count: int
    max_profiles: int = 4


class DeleteProfileResponse(BaseModel):
    status: str = "deleted"
    profile_id: str


class ProfileResponse(BaseModel):
    profile_id: str
    profile_name: str
    profile_key: str
    user_id: str
    birth_input: dict[str, Any]
    user_info: dict[str, Any]
    student_context: dict[str, Any] | None = None
    career_context: dict[str, Any] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    d1_table: dict[str, Any] = Field(default_factory=dict)
    divisional_charts: dict[str, Any] = Field(default_factory=dict)
    consolidated: dict[str, Any] | None = None
    education_analysis: dict[str, Any] | None = None
    education_analysis_error: str | None = None
    career_timeline: dict[str, Any] | None = None
    career_timeline_error: str | None = None
    created_at: str
    updated_at: str
    read_only: bool = True
