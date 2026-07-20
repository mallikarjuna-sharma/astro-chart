"""Schemas that keep astronomy, doctrine and engineered scoring distinct."""
from __future__ import annotations

from typing import Any, Mapping


VALID_STATUSES = {"COMPUTED", "NOT_COMPUTED", "FAILED", "DEGRADED"}


def evidence_layers(*, facts: Mapping[str, Any] | None = None,
                    doctrine: Mapping[str, Any] | None = None,
                    heuristics: Mapping[str, Any] | None = None,
                    status: str = "COMPUTED", reason: str = "") -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid evidence status: {status}")
    return {
        "status": status,
        "reason": reason,
        "factual_calculations": dict(facts or {}),
        "derived_doctrine": dict(doctrine or {}),
        "modern_heuristics": dict(heuristics or {}),
        "neutral_is_not_missing": True,
    }
