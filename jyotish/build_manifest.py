"""Deterministic source-tree and registry identity helpers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
_EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".uv-cache", ".uv-python", "outputs"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_files(root: Path = ROOT) -> Iterable[Path]:
    for path in sorted((root / "jyotish").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json"}:
            if not any(part in _EXCLUDED_PARTS for part in path.parts):
                yield path
    for path in sorted((root / "tests").glob("test_*.py")):
        yield path


def build_manifest(root: Path = ROOT) -> dict:
    files = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in source_files(root)
    }
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "contract_version": "build-manifest.v1",
        "source_tree_sha256": hashlib.sha256(canonical).hexdigest(),
        "file_count": len(files),
        "files": files,
    }

