"""Create and load birth profiles (chunked in JyotishProfiles, write-once)."""
from __future__ import annotations

from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.db import profiles_repository
from api.db.chart_attach import attach_d1_table
from api.db.profiles_repository import ProfilesRepositoryError, build_profile_key
from api.db.dynamo import DynamoDBNotConfiguredError
from api.schemas.profiles import (
    CreateProfileRequest,
    PersistProfileSectionsRequest,
    PersistProfileSectionsResponse,
    ProfileListResponse,
    ProfileResponse,
    ProfileSummary,
)
from api.auth_service import get_current_user


def _require_user(authorization: str | None):
    return get_current_user(authorization)


def _profile_http_error(exc: ProfilesRepositoryError) -> HTTPException:
    message = str(exc)
    if "already exists" in message.lower():
        return HTTPException(status_code=409, detail=message)
    if "maximum" in message.lower():
        return HTTPException(status_code=403, detail=message)
    if "not found" in message.lower():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


def _to_profile_response(item: dict) -> ProfileResponse:
    return ProfileResponse.model_validate(attach_d1_table(item))


def list_user_profiles(authorization: str | None) -> ProfileListResponse:
    user_id = _require_user(authorization).user.user_id
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
    user_id = _require_user(authorization).user.user_id
    profile_id = profile_id.strip()
    try:
        item = profiles_repository.get_profile(user_id, profile_id)
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return _to_profile_response(item)


def create_user_profile(
    authorization: str | None,
    body: CreateProfileRequest,
) -> ProfileResponse:
    me = _require_user(authorization)
    user_id = me.user.user_id
    profile_key = build_profile_key(body.profile_name, body.birth_input)

    try:
        existing = profiles_repository.find_by_profile_key(profile_key)
        if existing and existing.get("user_id") == user_id:
            return _to_profile_response(existing)
        if existing:
            raise _profile_http_error(
                ProfilesRepositoryError(
                    "A profile with this name, date of birth, and location already exists."
                )
            )
    except ProfilesRepositoryError as exc:
        raise _profile_http_error(exc) from exc
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    from api.profile_compute import compute_profile_sections

    user_info = dict(body.user_info)
    user_info.setdefault("display_name", body.profile_name)

    try:
        d1, divisional, analysis_sections = compute_profile_sections(
            body.birth_input,
            body.student_context,
            body.career_context,
        )
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
            extra_sections=analysis_sections,
        )
    except ProfilesRepositoryError as exc:
        raise _profile_http_error(exc) from exc
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _to_profile_response(item)


def persist_user_profile_sections(
    authorization: str | None,
    profile_id: str,
    body: PersistProfileSectionsRequest,
) -> PersistProfileSectionsResponse:
    user_id = _require_user(authorization).user.user_id
    profile_id = profile_id.strip()
    if not body.sections:
        return PersistProfileSectionsResponse(profile_id=profile_id, saved_sections=[])
    try:
        saved = profiles_repository.save_profile_sections(
            user_id, profile_id, body.sections
        )
    except ProfilesRepositoryError as exc:
        raise _profile_http_error(exc) from exc
    except DynamoDBNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PersistProfileSectionsResponse(profile_id=profile_id, saved_sections=saved)


def delete_user_profile(authorization: str | None, profile_id: str) -> dict[str, str]:
    user_id = _require_user(authorization).user.user_id
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
