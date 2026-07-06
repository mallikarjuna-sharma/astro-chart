"""Derive D1 table JSON from birth_input when not stored in DynamoDB."""
from __future__ import annotations

from typing import Any

from api.db.chart_payload import d1_table_payload
from api.schemas.chart import BirthChartBody


def attach_d1_table(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("d1_table"):
        return item
    birth_raw = item.get("birth_input")
    if not birth_raw:
        return item
    from api.main import _compute_birth_chart

    birth = BirthChartBody.model_validate(birth_raw)
    d1 = _compute_birth_chart(birth)
    out = dict(item)
    out["d1_table"] = d1_table_payload(d1)
    return out
