"""CRUD for birth profiles in JyotishProfiles (max 4 per auth user).

One logical profile spans multiple DynamoDB items (same table, different SK):
  PROFILE#{id}              — header + birth/student/career inputs
  PROFILE#{id}#CHARTS       — d1_table, divisional_charts, meta
  PROFILE#{id}#ANALYSIS#*   — KP, Jaimini, extended, consolidated
  PROFILE#{id}#CONTEXT#*    — career timeline outputs
                              (education analysis lives in its own table,
                               JyotishEducationAnalysis, keyed by profile_id)

All calculations run once at profile create; reads merge chunks without recomputing.
"""
from __future__ import annotations

import json
import numbers
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from api.db.profiles_dynamo import get_profiles_table
from api.db.chart_payload import d1_table_payload
from api.schemas.chart import BirthChartBody, DivisionalChartsResponse, TableResponse

MAX_PROFILES_PER_USER = 4
_DYNAMO_MAX_BYTES = 400 * 1024

# Lazy-persist chunk sort-key suffixes (after PROFILE#{profile_id}#).
CHUNK_CHARTS = "CHARTS"
CHUNK_KP = "ANALYSIS#KP"
CHUNK_JAIMINI = "ANALYSIS#JAIMINI"
CHUNK_EXTENDED = "ANALYSIS#EXTENDED"
CHUNK_CONSOLIDATED = "ANALYSIS#CONSOLIDATED"
CHUNK_CAREER = "CONTEXT#CAREER"

_CHUNK_STRIP_KEYS = frozenset(
    {"PK", "SK", "entity_type", "chunk", "profile_id", "user_id", "updated_at"}
)


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
    for key in ("PK", "SK", "entity_type", "chunk", "sections"):
        cleaned.pop(key, None)
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


def _put_item(item: dict[str, Any], *, part: str = "profile", condition: str | None = None) -> None:
    payload = _to_decimal(item)
    size = _json_bytes(payload)
    if size > _DYNAMO_MAX_BYTES:
        raise ProfilesRepositoryError(
            f"{part}: data exceeds DynamoDB size limit ({size // 1024} KB, max 400 KB)."
        )
    kwargs: dict[str, Any] = {"Item": payload}
    if condition:
        kwargs["ConditionExpression"] = condition
    get_profiles_table().put_item(**kwargs)


def _query_profile_items(auth_user_id: str, profile_id: str) -> list[dict[str, Any]]:
    table = get_profiles_table()
    items: list[dict[str, Any]] = []
    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": "PK = :pk AND begins_with(SK, :sk)",
        "ExpressionAttributeValues": {
            ":pk": _pk(auth_user_id),
            ":sk": _sk_header(profile_id),
        },
    }
    while True:
        resp = table.query(**query_kwargs)
        items.extend(resp.get("Items", []))
        if not resp.get("LastEvaluatedKey"):
            break
        query_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def _merge_profile_chunks(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    header: dict[str, Any] | None = None
    merged: dict[str, Any] = {}
    for raw in items:
        item = _from_decimal(raw)
        sk = item.get("SK", "")
        if _is_profile_header(sk):
            header = item
            continue
        for key, value in item.items():
            if key in _CHUNK_STRIP_KEYS:
                continue
            merged[key] = value
    if not header:
        return None
    out = dict(header)
    out.update(merged)
    return out


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
    items = _query_profile_items(auth_user_id, profile_id)
    merged = _merge_profile_chunks(items)
    if not merged:
        return None
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
    extra_sections: dict[str, dict[str, Any]] | None = None,
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

    sections_manifest: dict[str, Any] = {CHUNK_CHARTS: {"saved_at": now}}
    for part in extra_sections or {}:
        sections_manifest[part] = {"saved_at": now}

    header = {
        "PK": _pk(auth_user_id),
        "SK": _sk_header(profile_id),
        "entity_type": "profile",
        "chunk": "header",
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
        "sections": sections_manifest,
        "created_at": now,
        "updated_at": now,
    }

    charts_item = {
        "PK": _pk(auth_user_id),
        "SK": _sk_part(profile_id, CHUNK_CHARTS),
        "entity_type": "profile_chunk",
        "chunk": CHUNK_CHARTS,
        "profile_id": profile_id,
        "user_id": auth_user_id,
        "meta": meta,
        "d1_table": d1_table_payload(d1),
        "divisional_charts": divisional.model_dump(),
        "updated_at": now,
    }

    chunk_items: list[dict[str, Any]] = [header, charts_item]
    _put_item(header, part="header")
    _put_item(charts_item, part=CHUNK_CHARTS)

    for part, payload in (extra_sections or {}).items():
        if not payload:
            continue
        chunk_item = {
            "PK": _pk(auth_user_id),
            "SK": _sk_part(profile_id, part),
            "entity_type": "profile_chunk",
            "chunk": part,
            "profile_id": profile_id,
            "user_id": auth_user_id,
            **payload,
            "updated_at": now,
        }
        _put_item(chunk_item, part=part)
        chunk_items.append(chunk_item)

    merged = _merge_profile_chunks(chunk_items)
    assert merged is not None
    return _public_profile(merged)


def save_profile_sections(
    auth_user_id: str,
    profile_id: str,
    sections: dict[str, dict[str, Any]],
) -> list[str]:
    """Write analysis/context chunks once (skip if chunk SK already exists)."""
    items = _query_profile_items(auth_user_id, profile_id)
    merged = _merge_profile_chunks(items)
    if not merged:
        raise ProfilesRepositoryError("Profile not found.")

    saved: list[str] = []
    now = _utc_now()
    for part, payload in sections.items():
        if not payload:
            continue
        sk = _sk_part(profile_id, part)
        if any(item.get("SK") == sk for item in items):
            continue
        chunk_item = {
            "PK": _pk(auth_user_id),
            "SK": sk,
            "entity_type": "profile_chunk",
            "chunk": part,
            "profile_id": profile_id,
            "user_id": auth_user_id,
            **payload,
            "updated_at": now,
        }
        try:
            _put_item(chunk_item, part=part, condition="attribute_not_exists(SK)")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                continue
            raise
        saved.append(part)

    if saved:
        header_item = next(item for item in items if _is_profile_header(item["SK"]))
        sections_map = dict(_from_decimal(header_item.get("sections") or {}))
        for part in saved:
            sections_map[part] = {"saved_at": now}
        get_profiles_table().update_item(
            Key={"PK": _pk(auth_user_id), "SK": _sk_header(profile_id)},
            UpdateExpression="SET sections = :s, updated_at = :u",
            ExpressionAttributeValues={
                ":s": _to_decimal(sections_map),
                ":u": now,
            },
        )

    return saved


def delete_profile(auth_user_id: str, profile_id: str) -> bool:
    """Delete profile header and all chunks."""
    table = get_profiles_table()
    items = _query_profile_items(auth_user_id, profile_id)
    if not any(_is_profile_header(item["SK"]) for item in items):
        return False
    for item in items:
        table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
    return True
