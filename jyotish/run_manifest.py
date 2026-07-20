"""Reproducible run identity without influencing scoring."""
from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Mapping

from .build_manifest import ROOT, build_manifest, sha256_file
from .payload import ENGINE_VERSION


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return value


def stable_payload_sha256(payload: Any) -> str:
    encoded = json.dumps(
        _jsonable(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_run_manifest(payload: Any, *, enable_llm: bool) -> dict:
    source = build_manifest(ROOT)
    registry = ROOT / "jyotish" / "india_course_registry_no_planets.json"
    return {
        "contract_version": "run-manifest.v1",
        "engine_version": ENGINE_VERSION,
        "source_tree_sha256": source["source_tree_sha256"],
        "source_file_count": source["file_count"],
        "input_sha256": stable_payload_sha256(payload),
        "registry_sha256": sha256_file(registry) if registry.exists() else None,
        "python_version": platform.python_version(),
        "llm_enabled": bool(enable_llm),
        "score_policy_version": "legacy-frozen.v1",
        "score_scope_contract": "score-scope.v1",
    }

