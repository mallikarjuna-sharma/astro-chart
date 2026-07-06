"""Persist and load birth chart snapshots in DynamoDB."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from api.db.dynamo import get_table
from api.schemas.chart import BirthChartBody, DivisionalChartsResponse, TableResponse


def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _sk(chart_id: str) -> str:
    return f"CHART#{chart_id}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _d1_table_payload(d1: TableResponse) -> dict[str, Any]:
    return {
        "title": d1.title,
        "columns": d1.columns,
        "rows": [dict(zip(d1.columns, row)) for row in d1.rows],
    }


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = _from_decimal(item)
    for key in ("PK", "SK", "entity_type"):
        cleaned.pop(key, None)
    return cleaned


def save_birth_chart(
    user_id: str,
    user_info: dict[str, Any],
    birth_input: BirthChartBody,
    d1: TableResponse,
    divisional: DivisionalChartsResponse,
) -> dict[str, Any]:
    chart_id = str(uuid4())
    now = _utc_now()
    meta = dict(d1.meta)
    meta["computed_at"] = now

    item = {
        "PK": _pk(user_id),
        "SK": _sk(chart_id),
        "entity_type": "birth_chart",
        "user_id": user_id,
        "chart_id": chart_id,
        "user_info": user_info,
        "birth_input": birth_input.model_dump(),
        "meta": meta,
        "d1_table": _d1_table_payload(d1),
        "divisional_charts": divisional.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    get_table().put_item(Item=_to_decimal(item))
    return _public_item(item)


def list_user_charts(user_id: str) -> list[dict[str, Any]]:
    resp = get_table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": _pk(user_id),
            ":sk_prefix": "CHART#",
        },
        ScanIndexForward=False,
    )
    summaries: list[dict[str, Any]] = []
    for raw in resp.get("Items", []):
        item = _from_decimal(raw)
        birth_input = item.get("birth_input", {})
        meta = item.get("meta", {})
        summaries.append(
            {
                "chart_id": item["chart_id"],
                "user_id": item["user_id"],
                "user_info": item.get("user_info", {}),
                "birth_local": meta.get("birth_local")
                or birth_input.get("place_label", ""),
                "place_label": birth_input.get("place_label", ""),
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
            }
        )
    return summaries


def get_birth_chart(user_id: str, chart_id: str) -> dict[str, Any] | None:
    resp = get_table().get_item(
        Key={"PK": _pk(user_id), "SK": _sk(chart_id)},
    )
    item = resp.get("Item")
    if not item:
        return None
    return _public_item(item)


def delete_birth_chart(user_id: str, chart_id: str) -> bool:
    try:
        resp = get_table().delete_item(
            Key={"PK": _pk(user_id), "SK": _sk(chart_id)},
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_OLD",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return bool(resp.get("Attributes"))
