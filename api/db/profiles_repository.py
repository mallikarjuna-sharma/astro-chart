"""CRUD for birth profiles in JyotishProfiles (max 4 per auth user).

JyotishProfiles — profile metadata (header rows only):
  PK USER#{auth_user_id}  SK PROFILE#{profile_id}

JyotishProfilesCharts — divisional chart snapshots (see profiles_charts_repository):
  PK USER#{auth_user_id}  SK CHART#{profile_id}

d1_table is not stored; it is derived on read from birth_input.
"""
from __future__ import annotations

import json
import numbers
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from api.db import profiles_charts_repository
from api.db.profiles_dynamo import get_profiles_table
from api.schemas.chart import BirthChartBody, DivisionalChartsResponse, TableResponse

MAX_PROFILES_PER_USER = 4
_DYNAMO_MAX_BYTES = 400 * 1024


class ProfilesRepositoryError(RuntimeError):
    """Domain error for profile persistence."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pk(auth_user_id: str) -> str:
    return f"USER#{auth_user_id}"


def _sk_header(profile_id: str) -> str:
    return f"PROFILE#{profile_id}"


def _sk_part(profile_id: str, part: str) -> str:
    return f"PROFILE#{profile_id}#{part}"


def _is_profile_header(sk: str) -> bool:
    if not sk.startswith("PROFILE#"):
        return False
    return "#" not in sk[len("PROFILE#") :]


def _normalize_profile_name(name: str) -> str:
    return " ".join(name.strip().split())


def build_profile_key(profile_name: str, birth_input: BirthChartBody) -> str:
    name = _normalize_profile_name(profile_name).lower()
    lat = round(float(birth_input.latitude), 4)
    lng = round(float(birth_input.longitude), 4)
    dob = (
        f"{birth_input.year:04d}-{birth_input.month:02d}-{birth_input.day:02d}"
        f"T{birth_input.hour:02d}:{birth_input.minute:02d}:{birth_input.second:02d}"
    )
    return f"{name}#{dob}#{lat}#{lng}"


def _to_decimal(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return Decimal(str(float(value)))
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if hasattr(value, "item"):
        try:
            return _to_decimal(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, list):
        return [_to_decimal(v) for v in value]
    if isinstance(value, tuple):
        return [_to_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    return str(value)


def _from_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, list):
        return [_from_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_decimal(v) for k, v in value.items()}
    return value


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, default=str, separators=(",", ":")).encode("utf-8"))


def _public_profile(merged: dict[str, Any]) -> dict[str, Any]:
    cleaned = _from_decimal(merged)
    for key in ("PK", "SK", "entity_type", "chunk", "auth_username"):
        cleaned.pop(key, None)
    cleaned.pop("d1_table", None)
    cleaned["read_only"] = True
    return cleaned


def _public_summary(header: dict[str, Any]) -> dict[str, Any]:
    item = _from_decimal(header)
    birth_input = item.get("birth_input", {})
    meta = item.get("meta", {})
    return {
        "profile_id": item["profile_id"],
        "profile_name": item["profile_name"],
        "place_label": birth_input.get("place_label", ""),
        "birth_local": meta.get("birth_local", ""),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
    }


def _put_header(item: dict[str, Any]) -> None:
    payload = _to_decimal(item)
    if _json_bytes(payload) > _DYNAMO_MAX_BYTES:
        raise ProfilesRepositoryError(
            "Profile data exceeds DynamoDB size limit. Contact support or reduce chart scope."
        )
    get_profiles_table().put_item(Item=payload)


def _get_legacy_charts_chunk(auth_user_id: str, profile_id: str) -> dict[str, Any] | None:
    """Pre-migration charts stored under JyotishProfiles PROFILE#{id}#CHARTS."""
    resp = get_profiles_table().get_item(
        Key={"PK": _pk(auth_user_id), "SK": _sk_part(profile_id, "CHARTS")},
    )
    item = resp.get("Item")
    return _from_decimal(item) if item else None


def _load_charts(auth_user_id: str, profile_id: str) -> dict[str, Any] | None:
    charts = profiles_charts_repository.get_profile_charts(auth_user_id, profile_id)
    if charts:
        return charts
    legacy = _get_legacy_charts_chunk(auth_user_id, profile_id)
    if not legacy:
        return None
    legacy.pop("d1_table", None)
    return legacy


def _merge_profile_parts(
    header: dict[str, Any],
    charts: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(_from_decimal(header))
    if charts:
        cleaned = _from_decimal(charts)
        for key in ("PK", "SK", "entity_type", "chunk", "profile_id", "user_id"):
            cleaned.pop(key, None)
        cleaned.pop("d1_table", None)
        merged.update(cleaned)
    return merged


def count_user_profiles(auth_user_id: str) -> int:
    resp = get_profiles_table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": _pk(auth_user_id),
            ":sk_prefix": "PROFILE#",
        },
        ProjectionExpression="SK",
    )
    return sum(1 for item in resp.get("Items", []) if _is_profile_header(item["SK"]))


def find_by_profile_key(profile_key: str) -> dict[str, Any] | None:
    resp = get_profiles_table().query(
        IndexName="by_profile_key",
        KeyConditionExpression="profile_key = :pk",
        ExpressionAttributeValues={":pk": profile_key},
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return None
    header = _from_decimal(items[0])
    user_id = header.get("user_id", "")
    profile_id = header.get("profile_id", "")
    if not user_id or not profile_id:
        return None
    return get_profile(user_id, profile_id)


def list_profiles(auth_user_id: str) -> list[dict[str, Any]]:
    resp = get_profiles_table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": _pk(auth_user_id),
            ":sk_prefix": "PROFILE#",
        },
        ScanIndexForward=False,
    )
    summaries: list[dict[str, Any]] = []
    for raw in resp.get("Items", []):
        if not _is_profile_header(raw["SK"]):
            continue
        summaries.append(_public_summary(raw))
    return summaries


def get_profile(auth_user_id: str, profile_id: str) -> dict[str, Any] | None:
    resp = get_profiles_table().get_item(
        Key={"PK": _pk(auth_user_id), "SK": _sk_header(profile_id)},
    )
    header = resp.get("Item")
    if not header:
        return None
    charts = _load_charts(auth_user_id, profile_id)
    merged = _merge_profile_parts(header, charts)
    return _public_profile(merged)


def save_profile(
    auth_user_id: str,
    auth_username: str,
    profile_name: str,
    profile_key: str,
    birth_input: BirthChartBody,
    user_info: dict[str, Any],
    student_context: dict[str, Any] | None,
    career_context: dict[str, Any],
    d1: TableResponse,
    divisional: DivisionalChartsResponse,
) -> dict[str, Any]:
    if count_user_profiles(auth_user_id) >= MAX_PROFILES_PER_USER:
        raise ProfilesRepositoryError(
            f"Maximum of {MAX_PROFILES_PER_USER} profiles reached. Delete one to add another."
        )

    existing = find_by_profile_key(profile_key)
    if existing:
        raise ProfilesRepositoryError(
            "A profile with this name, date of birth, and location already exists."
        )

    profile_id = str(uuid4())
    now = _utc_now()
    meta = dict(d1.meta)
    meta["computed_at"] = now

    header = {
        "PK": _pk(auth_user_id),
        "SK": _sk_header(profile_id),
        "entity_type": "profile",
        "profile_id": profile_id,
        "profile_name": _normalize_profile_name(profile_name),
        "profile_key": profile_key,
        "user_id": auth_user_id,
        "auth_username": auth_username,
        "birth_input": birth_input.model_dump(),
        "user_info": user_info,
        "student_context": student_context,
        "career_context": career_context,
        "meta": {"birth_local": meta.get("birth_local", ""), "place_label": birth_input.place_label},
        "created_at": now,
        "updated_at": now,
    }

    _put_header(header)
    charts = profiles_charts_repository.save_profile_charts(
        auth_user_id=auth_user_id,
        profile_id=profile_id,
        profile_name=_normalize_profile_name(profile_name),
        auth_username=auth_username,
        divisional=divisional,
        meta=meta,
        created_at=now,
    )

    merged = _merge_profile_parts(header, charts)
    return _public_profile(merged)


def delete_profile(auth_user_id: str, profile_id: str) -> bool:
    """Delete profile header, charts row, and any legacy in-table chunks."""
    table = get_profiles_table()
    pk = _pk(auth_user_id)
    sk_prefix = _sk_header(profile_id)

    items: list[dict[str, Any]] = []
    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": "PK = :pk AND begins_with(SK, :sk)",
        "ExpressionAttributeValues": {":pk": pk, ":sk": sk_prefix},
    }
    while True:
        resp = table.query(**query_kwargs)
        items.extend(resp.get("Items", []))
        if not resp.get("LastEvaluatedKey"):
            break
        query_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    if not any(_is_profile_header(item["SK"]) for item in items):
        return False

    for item in items:
        table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

    profiles_charts_repository.delete_profile_charts(auth_user_id, profile_id)
    return True
