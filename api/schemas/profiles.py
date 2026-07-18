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
    enrich_llm_career: bool = False

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
    auth_username: str = ""
    birth_input: dict[str, Any]
    user_info: dict[str, Any]
    student_context: dict[str, Any] | None = None
    career_context: dict[str, Any] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    d1_table: dict[str, Any] = Field(default_factory=dict)
    divisional_charts: dict[str, Any] = Field(default_factory=dict)
    kp: dict[str, Any] | None = None
    jaimini: dict[str, Any] | None = None
    panchanga: dict[str, Any] | None = None
    ashtakavarga: dict[str, Any] | None = None
    shadbala: dict[str, Any] | None = None
    vimshottari: dict[str, Any] | None = None
    divisional_extended: dict[str, Any] | None = None
    consolidated: dict[str, Any] | None = None
    # Education analysis is stored in the dedicated JyotishEducationAnalysis
    # table (see api/db/education_repository.py), not on the profile.
    career_timeline: dict[str, Any] | None = None
    career_timeline_error: str | None = None
    created_at: str
    updated_at: str
    read_only: bool = True


class PersistProfileSectionsRequest(BaseModel):
    """Lazy-persist analysis chunks (write-once per section)."""

    sections: dict[str, dict[str, Any]] = Field(default_factory=dict)


class PersistProfileSectionsResponse(BaseModel):
    profile_id: str
    saved_sections: list[str]
