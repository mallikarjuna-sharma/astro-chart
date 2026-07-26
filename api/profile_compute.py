"""Compute chart payloads at profile creation (not education/career LLM engines)."""
from __future__ import annotations

from typing import Any

from api.db.chart_payload import d1_table_payload
from api.db.profiles_repository import (
    CHUNK_CONSOLIDATED,
    CHUNK_EXTENDED,
    CHUNK_JAIMINI,
    CHUNK_KP,
)
from jyotish.pyhora_schema import normalize_consolidated
from api import extended
from api.schemas.chart import BirthChartBody, DivisionalChartsResponse, TableResponse

_HTML_DROP_KEYS = frozenset(
    {
        "html",
        "html_narrative",
        "narrative_html",
        "llm_ad_narrative_html",
        "llm_narrative_html",
    }
)


def _strip_html_fields(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key in _HTML_DROP_KEYS:
                continue
            if key.endswith("_html") and isinstance(value, str) and len(value) > 500:
                continue
            out[key] = _strip_html_fields(value)
        return out
    if isinstance(obj, list):
        return [_strip_html_fields(v) for v in obj]
    return obj


def _compact_consolidated(consolidated: dict[str, Any]) -> dict[str, Any]:
    """Strip HTML-only fields; normalize divisional_charts for education/career engines."""
    return normalize_consolidated(_strip_html_fields(consolidated))


def compute_profile_sections(
    birth_input: BirthChartBody,
    student_context: dict[str, Any] | None,
    career_context: dict[str, Any],
) -> tuple[TableResponse, DivisionalChartsResponse, dict[str, dict[str, Any]]]:
    """Compute chart data from birth_input. User inputs live on the profile header."""
    from api.main import _compute_birth_chart, _compute_divisional_charts

    d1 = _compute_birth_chart(birth_input)
    divisional = _compute_divisional_charts(
        birth_input, factors=[1, 2, 3, 4, 5, 6, 7, 8, 9]
    )
    divisional_extended = _compute_divisional_charts(
        birth_input, factors=[10, 16, 24, 60, 81]
    )

    sc = student_context or {}
    consolidated = _compact_consolidated(extended.compute_consolidated(birth_input, sc))
    if career_context:
        consolidated = {**consolidated, "career_context": career_context}

    sections: dict[str, dict[str, Any]] = {
        CHUNK_KP: {"kp": extended.compute_kp(birth_input)},
        CHUNK_JAIMINI: {"jaimini": extended.compute_jaimini(birth_input)},
        CHUNK_EXTENDED: _strip_html_fields(
            {
                "panchanga": extended.compute_panchanga(birth_input),
                "ashtakavarga": extended.compute_ashtakavarga(birth_input),
                "shadbala": extended.compute_shadbala(birth_input),
                "vimshottari": extended.compute_vimshottari(birth_input),
                "divisional_extended": divisional_extended.model_dump(),
            }
        ),
        CHUNK_CONSOLIDATED: {"consolidated": consolidated},
    }

    return d1, divisional, sections


def d1_payload_from_table(d1: TableResponse) -> dict[str, Any]:
    return d1_table_payload(d1)
