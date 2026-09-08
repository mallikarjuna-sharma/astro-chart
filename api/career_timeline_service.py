"""Cache-or-compute orchestration for profile-scoped career timeline."""
from __future__ import annotations

import logging
from typing import Any

from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.auth_service import get_current_user
from api.career_timeline import CareerTimelineError, run_career_timeline
from api.db import profiles_repository
from api.db.dynamo import DynamoDBNotConfiguredError
from api.db.profiles_repository import CHUNK_CAREER, ProfilesRepositoryError
from api.profile_chart import resolve_career_context, resolve_consolidated_chart

logger = logging.getLogger(__name__)


def _require_user_id(authorization: str | None) -> str:
    return get_current_user(authorization).user.user_id


def _persist(user_id: str, profile_id: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        profiles_repository.upsert_profile_section(
            user_id,
            profile_id,
            CHUNK_CAREER,
            {
                "career_timeline": result,
                "career_timeline_error": None,
            },
        )
    except DynamoDBNotConfiguredError:
        logger.info("[career_timeline_service] DynamoDB not configured — returning uncached result.")
        result["cached"] = False
        return result
    except (ProfilesRepositoryError, ClientError) as exc:
        logger.warning("[career_timeline_service] cache write failed for %s: %s", profile_id, exc)
        result["cached"] = False
        return result

    out = dict(result)
    out["profile_id"] = profile_id
    out["user_id"] = user_id
    out["cached"] = False
    return out


def get_or_create_career_timeline(
    authorization: str | None,
    profile_id: str,
    *,
    career_context: dict[str, Any] | None = None,
    enrich_llm: bool = True,
    refresh: bool = False,
    user_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return stored career timeline for a profile, computing on first use or refresh."""
    user_id = _require_user_id(authorization)
    profile_id = profile_id.strip()
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")

    if not refresh:
        try:
            profile = profiles_repository.get_profile(user_id, profile_id)
        except (DynamoDBNotConfiguredError, ClientError):
            profile = None
        if profile:
            cached = profile.get("career_timeline")
            if isinstance(cached, dict) and cached:
                out = dict(cached)
                out.setdefault("profile_id", profile_id)
                out.setdefault("user_id", user_id)
                out["cached"] = True
                return out

    chart = resolve_consolidated_chart(user_id, profile_id, user_json)
    merged_context = resolve_career_context(user_id, profile_id, career_context)

    try:
        result = run_career_timeline(chart, merged_context or None, enrich_llm)
    except CareerTimelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Career timeline analysis failed: {exc}") from exc

    return _persist(user_id, profile_id, result)
