"""Deterministic hashes for release-critical policy and rule artifacts."""
from hashlib import sha256
from pathlib import Path
from typing import Dict

_PACKAGE = Path(__file__).resolve().parent
_ARTIFACTS = (
    _PACKAGE / "constants.py",
    _PACKAGE / "policy.py",
    _PACKAGE / "result_schema.py",
    _PACKAGE.parent / "business_domain_registry_v1.json",
)


def build_release_manifest() -> Dict[str, object]:
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in _ARTIFACTS}
    combined = sha256("".join(f"{name}:{hashes[name]}" for name in sorted(hashes)).encode()).hexdigest()
    return {"algorithm": "sha256", "artifact_hashes": hashes, "combined_hash": combined}


__all__ = ["build_release_manifest"]
