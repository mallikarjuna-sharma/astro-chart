"""Temporary AI call diagnostics for API responses (deprecated in future)."""
from __future__ import annotations

from typing import Any


def ai_status(*, success: str = "", error: str = "") -> dict[str, str]:
    """Build the ``AI`` field attached to education analysis API responses."""
    return {"success": success or "", "error": error or ""}


def ai_status_from_stream_narrative(narrative: dict[str, Any] | None) -> dict[str, str]:
    """Map Stream_Determination narrative outcome to ``AI`` diagnostics."""
    if not narrative:
        return ai_status(error="Stream narrative was not produced")

    status = str(narrative.get("status") or "").upper()
    provider = str(narrative.get("provider") or "")
    model = narrative.get("model")
    reason = str(narrative.get("reason") or "")

    if status == "GENERATED":
        detail = f"Stream narrative generated via {provider}"
        if model:
            detail += f" ({model})"
        return ai_status(success=detail)

    if status in {"SKIPPED_DISABLED", "SKIPPED_NO_CONSENT"}:
        return ai_status(error=reason or f"Narrative skipped: {status}")

    if status == "FALLBACK":
        return ai_status(error=reason or "LLM narrative failed; deterministic fallback used")

    return ai_status(error=reason or f"Unknown narrative status: {status or 'missing'}")


def ai_status_from_ug_report(
    *,
    llm_attempted: bool,
    llm_succeeded: bool,
    provider: str = "",
    model: str = "",
    error_message: str = "",
) -> dict[str, str]:
    """Map UG career-field report LLM outcome to ``AI`` diagnostics."""
    if not llm_attempted:
        return ai_status(error=error_message or "LLM report not attempted (consent or API key missing)")

    if llm_succeeded:
        detail = "UG career-field narrative generated"
        if provider:
            detail += f" via {provider}"
        if model:
            detail += f" ({model})"
        return ai_status(success=detail)

    return ai_status(error=error_message or "LLM report generation failed; deterministic fallback used")
