"""Load consolidated chart JSON and career context from a stored birth profile."""
from __future__ import annotations

import logging
from typing import Any

from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.db import profiles_repository
from api.db.dynamo import DynamoDBNotConfiguredError
from api.db.profiles_repository import CHUNK_CONSOLIDATED
from api.schemas.chart import BirthChartBody

logger = logging.getLogger(__name__)


def resolve_consolidated_chart(
    user_id: str,
    profile_id: str,
    user_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prefer stored profile consolidated JSON; fall back to client payload or recompute."""
    if user_json:
        return user_json

    try:
        profile = profiles_repository.get_profile(user_id, profile_id)
    except DynamoDBNotConfiguredError:
        profile = None
    except ClientError as exc:
        logger.warning("[profile_chart] profile read failed for %s: %s", profile_id, exc)
        profile = None

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    consolidated = profile.get("consolidated")
    if isinstance(consolidated, dict) and consolidated:
        return consolidated

    from api.profile_compute import compute_profile_sections

    birth_input = BirthChartBody.model_validate(profile["birth_input"])
    _, _, sections = compute_profile_sections(
        birth_input,
        profile.get("student_context"),
        profile.get("career_context") or {},
    )
    rebuilt = (sections.get(CHUNK_CONSOLIDATED) or {}).get("consolidated")
    if isinstance(rebuilt, dict) and rebuilt:
        return rebuilt

    raise HTTPException(
        status_code=400,
        detail="Consolidated chart data could not be loaded for this profile.",
    )


def resolve_career_context(
    user_id: str,
    profile_id: str,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return profile career_context merged with an optional request override."""
    try:
        profile = profiles_repository.get_profile(user_id, profile_id)
    except (DynamoDBNotConfiguredError, ClientError):
        profile = None

    base: dict[str, Any] = {}
    if profile:
        base = dict(profile.get("career_context") or {})
    if override:
        base.update(override)
    return base
