"""Create and load birth profiles (charts + context, write-once).

Career field and job analysis are not persisted on the profile; use the
dedicated analysis endpoints when viewing those pages.
"""
from __future__ import annotations

from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.db import profiles_repository
from api.db.profiles_repository import ProfilesRepositoryError, build_profile_key
from api.db.chart_attach import attach_d1_table
from api.db.dynamo_common import DynamoDBNotConfiguredError
from api.schemas.profiles import (
    CreateProfileRequest,
    ProfileListResponse,
    ProfileResponse,
    ProfileSummary,
)
from api.auth_service import get_current_user


def _require_user_id(authorization: str | None) -> str:
    me = get_current_user(authorization)
    return me.user.user_id


def _profile_http_error(exc: ProfilesRepositoryError) -> HTTPException:
    message = str(exc)
    if "already exists" in message.lower():
        return HTTPException(status_code=409, detail=message)
    if "maximum" in message.lower():
        return HTTPException(status_code=403, detail=message)
    return HTTPException(status_code=400, detail=message)


def list_user_profiles(authorization: str | None) -> ProfileListResponse:
    user_id = _require_user_id(authorization)
    try:
        profiles = profiles_repository.list_profiles(user_id)
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ProfileListResponse(
        profiles=[ProfileSummary.model_validate(p) for p in profiles],
        count=len(profiles),
        max_profiles=profiles_repository.MAX_PROFILES_PER_USER,
    )


def get_user_profile(authorization: str | None, profile_id: str) -> ProfileResponse:
    user_id = _require_user_id(authorization)
    profile_id = profile_id.strip()
    try:
        item = profiles_repository.get_profile(user_id, profile_id)
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return ProfileResponse.model_validate(attach_d1_table(item))


def create_user_profile(
    authorization: str | None,
    body: CreateProfileRequest,
) -> ProfileResponse:
    me = get_current_user(authorization)
    user_id = me.user.user_id
    profile_key = build_profile_key(body.profile_name, body.birth_input)

    try:
        existing = profiles_repository.find_by_profile_key(profile_key)
        if existing and existing.get("user_id") == user_id:
            return ProfileResponse.model_validate(attach_d1_table(existing))
        if existing:
            raise ProfilesRepositoryError(
                "A profile with this name, date of birth, and location already exists."
            )
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    from api.main import _compute_birth_chart, _compute_divisional_charts

    d1 = _compute_birth_chart(body.birth_input)
    divisional = _compute_divisional_charts(body.birth_input, factors=[1, 2, 3, 4, 5, 6, 7, 8, 9])

    user_info = dict(body.user_info)
    user_info.setdefault("display_name", body.profile_name)

    try:
        item = profiles_repository.save_profile(
            auth_user_id=user_id,
            auth_username=me.user.username,
            profile_name=body.profile_name,
            profile_key=profile_key,
            birth_input=body.birth_input,
            user_info=user_info,
            student_context=body.student_context,
            career_context=body.career_context,
            d1=d1,
            divisional=divisional,
        )
    except ProfilesRepositoryError as exc:
        raise _profile_http_error(exc) from exc
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ProfileResponse.model_validate(attach_d1_table(item))


def delete_user_profile(authorization: str | None, profile_id: str) -> dict[str, str]:
    user_id = _require_user_id(authorization)
    profile_id = profile_id.strip()
    try:
        deleted = profiles_repository.delete_profile(user_id, profile_id)
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {"status": "deleted", "profile_id": profile_id}
