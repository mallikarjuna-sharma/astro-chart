"""Fail-fast registry loader for JyotishAI v12.

Drop this file at: jyotish/registry_loader_v12.py
Then patch engine_io._load_course_registry() to call load_course_registry_v12().
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_course_registry_v12(*, prefer_v12: bool = True, validate: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load v12 if present, else v11, and fail if the registry is empty.

    Returns the flat {field_id: branch_metadata} dict expected by the existing
    engine. Existing v11 keys are preserved in v12, so downstream code remains
    compatible.
    """
    base = Path(__file__).resolve().parent
    candidates = []
    if prefer_v12:
        candidates.append(base / "india_course_registry_v12.json")
    candidates.append(base / "india_course_registry_v11.json")
    candidates.append(base.parent / "india_course_registry_v12.json")
    candidates.append(base.parent / "india_course_registry_v11.json")

    last_error = None
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = path.read_bytes().replace(b"\x00", b"").replace(b"\r", b"")
            data = json.loads(raw)
            branches = data.get("branches", {}) or {}
            if not branches:
                raise RuntimeError(f"Registry loaded empty: {path}")
            if validate and path.name.endswith("v12.json"):
                try:
                    from .registry_coverage_validator import validate_all_coverage
                    validate_all_coverage(path, fail_fast=True)
                except Exception as exc:
                    raise RuntimeError(f"Registry coverage validation failed for {path}: {exc}") from exc
            return branches
        except Exception as exc:
            last_error = exc
    raise FileNotFoundError(f"No usable course registry found. Tried: {[str(p) for p in candidates]}. Last error: {last_error}")
