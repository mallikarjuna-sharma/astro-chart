"""CRUD for education / career-field analyses in JyotishEducationAnalysis.

One item per birth profile (partition key = ``profile_id``). The four LLM
report payloads are stored as gzip+base64 strings so the ~660 KB ``results``
payload fits inside DynamoDB's 400 KB per-item limit:

  results_gz         payload 1 — ranked career-field rows
  macro_clusters_gz  payload 2 — named macro clusters
  report_gz          payload 3 — 14-section narrative report
  chart_facts_gz     payload 4 — chart-signature facts

No HTML is stored — the client renders the report from these four JSON payloads
with React components. ``user_id`` is the logged-in auth user (also a GSI hash
key for listing a user's analyses). Small scalar fields (student, summary,
engine_version, timestamps) are stored plainly for cheap projections.
"""
from __future__ import annotations

import base64
import gzip
import json
import numbers
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

_COMPRESSION = "gzip+base64"


class EducationRepositoryError(RuntimeError):
    """Domain error for education-analysis persistence."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_decimal(value: Any) -> Any:
    """Convert floats to Decimal recursively (DynamoDB resource API rejects floats)."""
    if value is None or isinstance(value, (bool, Decimal, int, str)):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, numbers.Real):
        return Decimal(str(float(value)))
    if isinstance(value, (list, tuple)):
        return [_to_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    return str(value)


def _from_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_from_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_decimal(v) for k, v in value.items()}
    return value


def _pack(value: Any) -> str:
    """gzip+base64 encode any JSON-serialisable value into a DynamoDB string."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def _unpack(blob: Any) -> Any:
    """Reverse :func:`_pack`. Returns ``None`` for missing/empty blobs."""
    if not blob:
        return None
    if not isinstance(blob, str):
        return blob
    raw = gzip.decompress(base64.b64decode(blob.encode("ascii")))
    return json.loads(raw.decode("utf-8"))


def _match_and_soul(fields: list[dict[str, Any]]) -> tuple[list[str], str | None]:
    sorted_results = sorted(fields, key=lambda x: (-x.get("final_score", 0), x.get("field_id", "")))
    match_ids = [
        r["field_id"]
        for r in sorted_results
        if r.get("llm_group", "match") != "soul" and 1 <= r.get("llm_rank", 99) <= 5
    ]
    soul = next((r["field_id"] for r in sorted_results if r.get("llm_group") == "soul"), None)
    return match_ids, soul


def response_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the ``EducationAnalysisResponse`` shape from a stored item."""
    fields = _unpack(item.get("results_gz")) or []
    macro_clusters = _unpack(item.get("macro_clusters_gz")) or []
    narrative = _unpack(item.get("report_gz")) or {}
    chart_facts = _unpack(item.get("chart_facts_gz")) or {}
    student = _from_decimal(item.get("student") or {})
    summary = _from_decimal(item.get("summary") or {})
    career_phase = item.get("career_phase", "")
    active_lord = item.get("active_lord", "")
    peak_lord = item.get("peak_lord", "")

    career_field_report = {
        "narrative": narrative,
        "macro_clusters": macro_clusters,
        "chart_facts": chart_facts,
        "career_phase": career_phase,
        "active_lord": active_lord,
        "peak_lord": peak_lord,
    }
    match_ids, soul = _match_and_soul(fields)
    report_bundle = {
        "student": student,
        "summary": summary,
        "top_match_field_ids": match_ids,
        "soul_field_id": soul,
        "fields": fields,
        "career_field_report": career_field_report,
    }
    return {
        "engine_version": item.get("engine_version", ""),
        "generated_at": item.get("generated_at", ""),
        "student": student,
        "summary": summary,
        # --- frozen html-payload-contract v1: four payloads as top-level keys ---
        "results": fields,               # payload 1
        "macro_clusters": macro_clusters,  # payload 2
        "report": narrative,             # payload 3 (14-section narrative)
        "chart_facts": chart_facts,      # payload 4
        # --- back-compat / convenience ---
        "fields": fields,                # alias of `results`
        "report_bundle": report_bundle,
        "career_field_report": career_field_report,
        "profile_id": item.get("profile_id"),
        "user_id": item.get("user_id"),
        "cached": True,
    }


def get_education_analysis(profile_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    """Return the stored analysis for ``profile_id`` (owner-scoped when ``user_id`` given)."""
    from api.db.education_dynamo import get_education_table

    resp = get_education_table().get_item(Key={"profile_id": profile_id})
    item = resp.get("Item")
    if not item:
        return None
    if user_id and item.get("user_id") not in (None, user_id):
        # Profile id collision across users — treat as not-found for this caller.
        return None
    return response_from_item(item)


def save_education_analysis(
    profile_id: str,
    user_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Persist the four JSON payloads for a freshly computed analysis (no HTML).

    ``result`` is the dict returned by ``run_education_analysis`` (engine_version,
    generated_at, student, summary, results, macro_clusters, report, chart_facts,
    career_field_report...). Returns the rebuilt response (with ``cached`` False).
    """
    from api.db.education_dynamo import get_education_table

    cfr = result.get("career_field_report") or {}
    fields = result.get("results") or result.get("fields") or []
    macro_clusters = result.get("macro_clusters") or cfr.get("macro_clusters") or []
    narrative = result.get("report") or cfr.get("narrative") or {}
    chart_facts = result.get("chart_facts") or cfr.get("chart_facts") or {}
    now = _utc_now()

    item = {
        "profile_id": profile_id,
        "user_id": user_id,
        "compression": _COMPRESSION,
        "engine_version": result.get("engine_version", ""),
        "generated_at": result.get("generated_at", now),
        "career_phase": cfr.get("career_phase", ""),
        "active_lord": cfr.get("active_lord", ""),
        "peak_lord": cfr.get("peak_lord", ""),
        "student": _to_decimal(result.get("student") or {}),
        "summary": _to_decimal(result.get("summary") or {}),
        # The four frozen LLM payloads (see Job_Career/html_payload_contract.py):
        "results_gz": _pack(fields),
        "macro_clusters_gz": _pack(macro_clusters),
        "report_gz": _pack(narrative),
        "chart_facts_gz": _pack(chart_facts),
        "created_at": now,
        "updated_at": now,
    }
    get_education_table().put_item(Item=item)

    out = response_from_item(item)
    out["cached"] = False
    return out


def delete_education_analysis(profile_id: str, user_id: str | None = None) -> bool:
    from api.db.education_dynamo import get_education_table

    table = get_education_table()
    resp = table.get_item(Key={"profile_id": profile_id})
    item = resp.get("Item")
    if not item:
        return False
    if user_id and item.get("user_id") not in (None, user_id):
        return False
    table.delete_item(Key={"profile_id": profile_id})
    return True
