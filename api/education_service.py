"""Cache-or-compute orchestration for the /education-analysis page.

A single logged-in user owns up to a handful of birth profiles. For each
profile we compute the JyotishAI career-field report exactly once (an LLM call
that takes 30-60s) and persist the four report payloads in the
JyotishEducationAnalysis DynamoDB table keyed by ``profile_id``. Subsequent
requests are served straight from the table.
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.auth_service import get_current_user
from api.db import education_repository
from api.db.dynamo import DynamoDBNotConfiguredError
from api.education_analysis import EducationAnalysisError, run_education_analysis

logger = logging.getLogger(__name__)


def _require_user_id(authorization: str | None) -> str:
    return get_current_user(authorization).user.user_id


def _cached(profile_id: str, user_id: str) -> dict[str, Any] | None:
    try:
        return education_repository.get_education_analysis(profile_id, user_id)
    except DynamoDBNotConfiguredError:
        return None
    except ClientError as exc:
        logger.warning("[education_service] cache read failed for %s: %s", profile_id, exc)
        return None


def _persist(profile_id: str, user_id: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        return education_repository.save_education_analysis(profile_id, user_id, result)
    except DynamoDBNotConfiguredError:
        logger.info("[education_service] DynamoDB not configured — returning uncached result.")
        result.setdefault("profile_id", profile_id)
        result.setdefault("user_id", user_id)
        result["cached"] = False
        return result
    except ClientError as exc:
        logger.warning("[education_service] cache write failed for %s: %s", profile_id, exc)
        result.setdefault("profile_id", profile_id)
        result.setdefault("user_id", user_id)
        result["cached"] = False
        return result


def get_or_create_education_analysis(
    authorization: str | None,
    profile_id: str,
    user_json: dict[str, Any],
    refresh: bool = False,
) -> dict[str, Any]:
    """Return the stored analysis for a profile, computing + persisting on first use.

    - ``refresh=True`` forces a recompute and overwrites the stored payloads.
    - Requires a valid bearer token (owner scoping via ``user_id``).
    """
    user_id = _require_user_id(authorization)
    profile_id = profile_id.strip()
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")

    if not refresh:
        hit = _cached(profile_id, user_id)
        if hit is not None:
            return hit

    if not user_json:
        raise HTTPException(
            status_code=400,
            detail="No cached analysis found; user_json (consolidated chart) is required to compute one.",
        )

    try:
        result = run_education_analysis(user_json)
    except EducationAnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Education analysis failed: {exc}") from exc

    return _persist(profile_id, user_id, result)


def delete_education_analysis(authorization: str | None, profile_id: str) -> dict[str, str]:
    user_id = _require_user_id(authorization)
    profile_id = profile_id.strip()
    try:
        deleted = education_repository.delete_education_analysis(profile_id, user_id)
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="No stored education analysis for this profile.")
    return {"status": "deleted", "profile_id": profile_id}
