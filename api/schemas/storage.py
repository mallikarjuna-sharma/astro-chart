"""Request/response models for persisted birth charts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.schemas.chart import BirthChartBody, DivisionalChartsResponse


class StudentPreferenceInfo(BaseModel):
    interested_in: list[str] = Field(default_factory=list)
    already_excel_at: list[str] = Field(default_factory=list)
    financial_constraints: bool = False
    risk_appetite: Literal["LOW", "MODERATE", "HIGH"] = "MODERATE"


class UserInfo(BaseModel):
    display_name: str = Field(..., max_length=120)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=40)
    location_query: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=500)
    gender: Literal["M", "F"] | None = None
    education_system: str | None = Field(None, max_length=80)
    student_preference: StudentPreferenceInfo | None = None


class SaveChartRequest(BaseModel):
    user_info: UserInfo
    birth_input: BirthChartBody


class SavedChartSummary(BaseModel):
    chart_id: str
    user_id: str
    user_info: UserInfo
    birth_local: str
    place_label: str
    created_at: str
    updated_at: str


class SavedChartListResponse(BaseModel):
    charts: list[SavedChartSummary]


class SavedChartResponse(BaseModel):
    chart_id: str
    user_id: str
    user_info: UserInfo
    birth_input: BirthChartBody
    meta: dict[str, Any]
    d1_table: dict[str, Any]
    divisional_charts: DivisionalChartsResponse
    created_at: str
    updated_at: str
