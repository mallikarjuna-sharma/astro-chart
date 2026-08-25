"""Gap-audit fix (2026-08, HIGH-priority): build/refresh the v12 course
registry from a v11 registry file.

This file was referenced by jyotish/ONTOLOGY_REGISTRY_V12_README.md's "Build
/ refresh the v12 registry" section and by its "Files to add" list, but did
not exist anywhere in the codebase -- the enrichment LOGIC it was meant to
invoke (registry_v12_schema.py::enrich_branch_v12 and its helpers) was fully
implemented and unit-testable, but there was no runnable entry point to
actually call it over a whole v11 registry file. Without this file, the v12
registry could only be produced by hand-editing the v12 JSON directly, which
is exactly the error-prone process the v12 upgrade was meant to replace.

Drop this file at: jyotish/registry_v12_builder.py (already at that path).

Usage (matches the README's documented command exactly):
    python -m jyotish.registry_v12_builder \
        --input jyotish/india_course_registry_v11.json \
        --output jyotish/india_course_registry_v12.json

Design principles (matching registry_v12_schema.py's own, since this module
is purely a driver over that one):
1. No astrology scoring here. This module only builds enriched metadata.
2. Fully deterministic. No LLM or web dependency.
3. Every output branch is validated (via registry_coverage_validator) before
   being written, so a broken build fails loudly at build time rather than
   producing a v12 file that fails validation only when the engine loads it.
4. Backward compatible: existing v11 keys are preserved on each branch
   (enrich_branch_v12 already guarantees this; this module does not touch
   branch contents beyond what that function does).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

from .registry_v12_schema import enrich_branch_v12


class RegistryBuildError(RuntimeError):
    pass


def _read_v11_registry(input_path: str | Path) -> Dict[str, Any]:
    """Load a v11 registry JSON file. Mirrors registry_loader_v12.py's own
    defensive read (strips stray NUL bytes / CR characters that have been
    observed in this project's JSON files from past editor/encoding issues)
    so the builder and the loader treat the same file the same way.
    """
    path = Path(input_path)
    if not path.exists():
        raise RegistryBuildError(f"Input v11 registry not found: {path}")
    raw = path.read_bytes().replace(b"\x00", b"").replace(b"\r", b"")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegistryBuildError(f"Input v11 registry is not valid JSON: {path}: {exc}") from exc
    branches = data.get("branches", {}) or {}
    if not branches:
        raise RegistryBuildError(f"Input v11 registry has no branches: {path}")
    return data


def build_registry_v12(
    input_path: str | Path,
    *,
    field_to_family: Mapping[str, str] = None,
    family_meta: Mapping[str, Mapping[str, Any]] = None,
    secondary_edges: Iterable[Tuple[str, str, float]] = (),
    broadness_penalty_map: Mapping[str, float] = None,
) -> Dict[str, Any]:
    """Build the full v12 registry dict (not yet written to disk) from a v11
    registry file. Exposed as a plain function (not just the CLI) so it can
    be called directly from a test or another script without going through
    subprocess/argparse.

    field_to_family/family_meta default to
    Field_Determination.competency_ontology's FIELD_TO_FAMILY/FAMILY_META --
    the same source registry_coverage_validator.py already treats as
    authoritative for ontology coverage -- so a plain `build_registry_v12(path)`
    call with no ontology kwargs produces a registry consistent with what
    the coverage validator will check it against afterward.

    secondary_edges/broadness_penalty_map have no first-class data source
    anywhere in this codebase today (enrich_branch_v12's own defaults are
    empty/None), so they default to empty here too -- callers that later add
    a real secondary-family-edge or broadness-penalty dataset can pass it in
    without any change to this function's signature.
    """
    if field_to_family is None or family_meta is None:
        from Field_Determination.competency_ontology import FIELD_TO_FAMILY, FAMILY_META
        field_to_family = field_to_family if field_to_family is not None else FIELD_TO_FAMILY
        family_meta = family_meta if family_meta is not None else FAMILY_META

    v11 = _read_v11_registry(input_path)
    v11_branches: Dict[str, Any] = v11.get("branches", {}) or {}

    v12_branches: Dict[str, Any] = {}
    build_errors: Dict[str, str] = {}
    for field_id, branch in v11_branches.items():
        try:
            v12_branches[field_id] = enrich_branch_v12(
                field_id, branch,
                field_to_family=field_to_family,
                family_meta=family_meta,
                secondary_edges=secondary_edges,
                broadness_penalty_map=broadness_penalty_map,
            )
        except Exception as exc:  # noqa: BLE001 - reported per-branch, not swallowed
            # Deliberately NOT skipped-silently: a branch that fails to
            # enrich is a real build defect (malformed v11 data, or a bug in
            # enrich_branch_v12 itself) and must be visible in the build
            # output, not silently dropped from the v12 registry.
            build_errors[field_id] = f"{type(exc).__name__}: {exc}"

    if build_errors:
        raise RegistryBuildError(
            "Failed to enrich "
            f"{len(build_errors)} of {len(v11_branches)} branches:\n"
            + "\n".join(f"  {fid}: {msg}" for fid, msg in sorted(build_errors.items()))
        )

    out = dict(v11)  # preserve any top-level v11 metadata keys (e.g. a version stamp)
    out["branches"] = v12_branches
    out["schema_version"] = "v12.0_enriched_registry"
    out["source_branch_count"] = len(v11_branches)
    out["built_branch_count"] = len(v12_branches)
    return out


def build_and_write(
    input_path: str | Path,
    output_path: str | Path,
    *,
    validate: bool = True,
) -> Dict[str, Any]:
    """Build the v12 registry and write it to `output_path`. If `validate`
    is True (default, matches the README's documented workflow of building
    then separately validating), runs registry_coverage_validator against
    the freshly-built file before returning -- a build that produces an
    internally-inconsistent registry (e.g. missing ontology coverage for a
    branch) fails here, at build time, rather than only being discovered
    later when the engine tries to load it.
    """
    result = build_registry_v12(input_path)
    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    if validate:
        from .registry_coverage_validator import validate_all_coverage, RegistryCoverageError
        try:
            report = validate_all_coverage(output_path, fail_fast=True)
        except RegistryCoverageError as exc:
            raise RegistryBuildError(
                f"Built {output_path} but it FAILED coverage validation:\n{exc}"
            ) from exc
        return report
    return {"ok": None, "note": "validation skipped (validate=False)"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the v12 course registry from a v11 registry file.",
    )
    parser.add_argument("--input", required=True, help="Path to the v11 registry JSON file.")
    parser.add_argument("--output", required=True, help="Path to write the built v12 registry JSON file.")
    parser.add_argument(
        "--no-validate", action="store_true",
        help="Skip running registry_coverage_validator after building (not recommended).",
    )
    args = parser.parse_args(argv)

    try:
        report = build_and_write(args.input, args.output, validate=not args.no_validate)
    except RegistryBuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output}")
    if report.get("ok") is not None:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if not report.get("ok"):
            print("WARNING: built registry failed coverage validation (see above).", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
