"""Schemas for POST /api/prashna and GET /api/prashna/categories."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from jyotish.prashna_engine import PrashnaRequest, PrashnaResponse

__all__ = [
    "PrashnaCategoryMeta",
    "PrashnaCategoriesResponse",
    "PrashnaRequest",
    "PrashnaResponse",
]


class PrashnaCategoryMeta(BaseModel):
    key: str
    label: str
    primary_house: int
    example: str


class PrashnaCategoriesResponse(BaseModel):
    categories: list[PrashnaCategoryMeta] = Field(default_factory=list)


class PrashnaBatchRequest(BaseModel):
    question: str
    categories: list[str] = Field(..., min_length=1)
    moment: str | None = None
    city: str = "Delhi"
    lat: float | None = None
    lon: float | None = None


class PrashnaBatchResponse(BaseModel):
    results: dict[str, Any] = Field(default_factory=dict)
