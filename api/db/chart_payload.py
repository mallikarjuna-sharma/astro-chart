"""Shared chart serialization helpers."""
from __future__ import annotations

from typing import Any

from api.schemas.chart import TableResponse


def d1_table_payload(d1: TableResponse) -> dict[str, Any]:
    return {
        "title": d1.title,
        "columns": d1.columns,
        "rows": [dict(zip(d1.columns, row)) for row in d1.rows],
    }
