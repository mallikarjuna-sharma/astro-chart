"""Shared birth-chart request/response models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BirthChartBody(BaseModel):
    """Local civil date/time at `timezone_offset_hours` east of UTC (e.g. India 5.5)."""

    year: int = Field(..., examples=[2008])
    month: int = Field(..., ge=1, le=12, examples=[11])
    day: int = Field(..., ge=1, le=31, examples=[16])
    hour: int = Field(0, ge=0, le=23, examples=[6])
    minute: int = Field(0, ge=0, le=59, examples=[1])
    second: int = Field(0, ge=0, le=59, examples=[0])
    place_label: str = Field("Srirangam, Tiruchirappalli, Tamil Nadu, India", description="Display name only")
    latitude: float = Field(..., ge=-90, le=90, examples=[10.8655])
    longitude: float = Field(..., ge=-180, le=180, examples=[78.6882])
    timezone_offset_hours: float = Field(
        ...,
        description="Hours east of UTC (IST = 5.5; US Eastern = -5)",
        examples=[5.5],
    )
    ayanamsa: str | None = Field(
        None,
        description="Swiss sidereal mode name, e.g. LAHIRI, TRUE_PUSHYA. Default: package default.",
    )
    use_true_nodes: bool = Field(
        False,
        description="If true, needs full Swiss ephemeris files (sepl*.se1) under jhora/data/ephe.",
    )
    include_outer_planets: bool = Field(
        False,
        description="Uranus/Neptune/Pluto in graha list (not shown in default Vedic nine-graha table).",
    )


class BirthRequest(BirthChartBody):
    response_format: Literal["json", "html", "html_json"] = Field(
        "json",
        description=(
            "`json` — table as JSON. "
            "`html` — full HTML document as response body (`text/html`; open in browser or use as `srcdoc`). "
            "`html_json` — JSON object `{ \"html\": \"<!DOCTYPE html>...\" }` for SPAs."
        ),
    )


class TableResponse(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[Any]]
    meta: dict[str, Any]


class HtmlDocumentJson(BaseModel):
    """Complete HTML page as one string (render in browser via iframe srcdoc or new tab)."""

    html: str


class DivisionalChart(BaseModel):
    factor: int = Field(..., description="Divisional factor: 1..9")
    name: str = Field(..., description="Human-readable chart name")
    houses: list[dict[str, Any]] = Field(
        ...,
        description=(
            "12 rasi houses (Aries..Pisces). Each item: "
            "`{rasi: 0..11, rasi_name: str, bodies: ['La','Su',...]}`."
        ),
    )


class DivisionalChartsResponse(BaseModel):
    charts: list[DivisionalChart]
    meta: dict[str, Any]


class StudentPreference(BaseModel):
    interested_in: list[str] = Field(default_factory=list)
    already_excel_at: list[str] = Field(default_factory=list)
    financial_constraints: bool = False
    risk_appetite: str = "MODERATE"


class StudentContext(BaseModel):
    pob: str | None = None
    gender: str = "O"
    education_system: str = "India_CBSE"
    student_preference: StudentPreference = Field(default_factory=StudentPreference)


class ConsolidatedRequest(BaseModel):
    """Birth data plus optional student metadata for the consolidated export JSON."""

    birth_input: BirthChartBody
    student_context: StudentContext | None = None
