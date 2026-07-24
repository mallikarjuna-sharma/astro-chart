"""API-layer LLM policy — HTTP endpoints always attempt LLM narratives."""
from __future__ import annotations

import copy
from typing import Any


def prepare_chart_for_api_llm(chart: dict[str, Any]) -> dict[str, Any]:
    """Stamp consent on incoming chart JSON so engine layers allow LLM calls."""
    prepared = copy.deepcopy(chart) if chart else {}
    student_context = dict(prepared.get("student_context") or {})
    student_context["external_llm_consent"] = True
    prepared["student_context"] = student_context
    return prepared


# API routes always enable narrative generation (debug via response ``AI`` field).
API_LLM_NARRATIVE_ENABLED = True
API_LLM_RUNTIME_CONSENT = True
