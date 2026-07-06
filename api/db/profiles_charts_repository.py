"""Chart snapshots in JyotishProfilesCharts — one row per birth profile (or legacy chart)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from api.db.profiles_charts_dynamo import get_profiles_charts_table
from api.schemas.chart import DivisionalChartsResponse


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pk(auth_user_id: str) -> str:
    return f"USER#{auth_user_id}"


def _sk_chart(chart_or_profile_id: str) -> str:
    return f"CHART#{chart_or_profile_id}"


def _to_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    return value


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


def save_profile_charts(
    auth_user_id: str,
    profile_id: str,
    profile_name: str,
    auth_username: str,
    divisional: DivisionalChartsResponse,
    meta: dict[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Persist divisional charts only (D1 table derived on read from birth_input)."""
    now = _utc_now()
    item = {
        "PK": _pk(auth_user_id),
        "SK": _sk_chart(profile_id),
        "entity_type": "profile_charts",
        "user_id": auth_user_id,
        "profile_id": profile_id,
        "profile_name": profile_name,
        "auth_username": auth_username,
        "divisional_charts": divisional.model_dump(),
        "meta": meta,
        "created_at": created_at or now,
        "updated_at": now,
    }
    get_profiles_charts_table().put_item(Item=_to_decimal(item))
    cleaned = _from_decimal(item)
    for key in ("PK", "SK", "entity_type"):
        cleaned.pop(key, None)
    return cleaned


def get_profile_charts(auth_user_id: str, profile_id: str) -> dict[str, Any] | None:
    resp = get_profiles_charts_table().get_item(
        Key={"PK": _pk(auth_user_id), "SK": _sk_chart(profile_id)},
    )
    item = resp.get("Item")
    if not item:
        return None
    cleaned = _from_decimal(item)
    for key in ("PK", "SK", "entity_type"):
        cleaned.pop(key, None)
    return cleaned


def delete_profile_charts(auth_user_id: str, profile_id: str) -> None:
    get_profiles_charts_table().delete_item(
        Key={"PK": _pk(auth_user_id), "SK": _sk_chart(profile_id)},
    )
