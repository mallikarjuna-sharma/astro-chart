"""Request/response models for persisted birth charts."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.schemas.chart import BirthChartBody, DivisionalChartsResponse


class UserInfo(BaseModel):
    display_name: str = Field(..., max_length=120)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=40)
    location_query: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=500)


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
