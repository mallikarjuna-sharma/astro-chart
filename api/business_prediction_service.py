"""Cache-or-compute orchestration for profile-scoped business prediction."""
from __future__ import annotations

import logging
from typing import Any

from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.auth_service import get_current_user
from api.business_prediction import BusinessPredictionError, run_business_prediction
from api.db import profiles_repository
from api.db.dynamo import DynamoDBNotConfiguredError
from api.db.profiles_repository import CHUNK_BUSINESS, ProfilesRepositoryError
from api.profile_chart import resolve_consolidated_chart

logger = logging.getLogger(__name__)


def _require_user_id(authorization: str | None) -> str:
    return get_current_user(authorization).user.user_id


def _persist(user_id: str, profile_id: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        profiles_repository.upsert_profile_section(
            user_id,
            profile_id,
            CHUNK_BUSINESS,
            {
                "business_prediction": result,
                "business_prediction_error": None,
            },
        )
    except DynamoDBNotConfiguredError:
        logger.info("[business_prediction_service] DynamoDB not configured — returning uncached result.")
        result["cached"] = False
        return result
    except (ProfilesRepositoryError, ClientError) as exc:
        logger.warning("[business_prediction_service] cache write failed for %s: %s", profile_id, exc)
        result["cached"] = False
        return result

    out = dict(result)
    out["profile_id"] = profile_id
    out["user_id"] = user_id
    out["cached"] = False
    return out


def get_or_create_business_prediction(
    authorization: str | None,
    profile_id: str,
    *,
    venture_type: str = "business",
    years_ahead: int = 15,
    refresh: bool = False,
    user_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return stored business prediction for a profile, computing on first use or refresh."""
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
            cached = profile.get("business_prediction")
            if isinstance(cached, dict) and cached:
                out = dict(cached)
                out.setdefault("profile_id", profile_id)
                out.setdefault("user_id", user_id)
                out["cached"] = True
                return out

    chart = resolve_consolidated_chart(user_id, profile_id, user_json)

    try:
        result = run_business_prediction(
            chart,
            venture_type=venture_type,
            years_ahead=years_ahead,
        )
    except BusinessPredictionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Business prediction analysis failed: {exc}") from exc

    return _persist(user_id, profile_id, result)
