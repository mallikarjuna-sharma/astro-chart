"""Schemas for POST /api/career-timeline."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CareerTimelineRequest(BaseModel):
    user_json: dict[str, Any] = Field(
        ...,
        description=(
            "Consolidated chart JSON (system_config, student_context, "
            "pyhora_calculations, …) — typically the response of /api/consolidated."
        ),
    )
    career_context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional career-context override (employment_status, designation, "
            "years_experience, industry_sector, desired_outcome, etc.). If omitted, "
            "the engine reads the `career_context` block embedded in user_json."
        ),
    )
    enrich_llm: bool = Field(
        default=True,
        description=(
            "When true and an LLM API key is configured, enriches each AD block "
            "with `llm_html` narratives (Executive Summary / Astrological Dynamics / "
            "Strategic Action Plan). Adds 20-60s to the request. Disable to get the "
            "deterministic-only timeline quickly."
        ),
    )


class OutcomeBar(BaseModel):
    primary_opportunity: str = "—"
    peak_md_lord: str = "—"
    peak_years: str = "—"
    growth_arc: str = "—"


class TrajectoryPoint(BaseModel):
    label: str
    score: float
    color: str
    event_type: str


class CalendarEntry(BaseModel):
    year: int
    event_type: str
    ad_lord: str
    score: int
    color: str


class MDArc(BaseModel):
    md_lord: str
    start_date: str
    end_date: str
    narrative: str


class ForeignMeta(BaseModel):
    total: int = 0
    high: int = 0
    moderate: int = 0
    mild: int = 0
    peak_score: float = 0.0
    peak_period: str = ""
    geo_summary: str = ""


class CareerTimelineResponse(BaseModel):
    engine_version: str
    generated_at: str = Field(..., description="ISO-8601 timestamp (UTC).")
    student: dict[str, Any] = Field(..., description="Student/chart summary for the report header.")
    career_context: dict[str, Any] = Field(
        ...,
        description="Normalised career-context echo (including any validation warnings).",
    )
    outcome: OutcomeBar
    trajectory: list[TrajectoryPoint] = Field(default_factory=list)
    calendar: list[CalendarEntry] = Field(default_factory=list)
    md_arcs: list[MDArc] = Field(default_factory=list)
    blocks: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Raw Antardasha blocks from the engine. Each block may carry a nested "
            "`foreign_opportunity` dict and (if enrich_llm=True) an `llm_html` narrative."
        ),
    )
    foreign_opportunities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Flat list of foreign-window dicts extracted from blocks.",
    )
    foreign_meta: ForeignMeta = Field(default_factory=ForeignMeta)
    micro_timing: dict[str, Any] = Field(
        default_factory=dict,
        description="Micro-timing dashboard: hora_timing, negotiation_heatmap, stakeholder_radar, whatif_scenarios.",
    )
    llm_enriched: bool = Field(
        default=False,
        description="True when AD blocks carry LLM-generated `llm_html` narratives.",
    )
    chart_insights: dict[str, Any] = Field(
        default_factory=dict,
        description="Sidebar snapshot: Shadbala, D10, KP, KN Rao, Parashara, Jaimini panels.",
    )
    report_meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Confidence banners, retro-validation summary, outcome-strength table.",
    )
