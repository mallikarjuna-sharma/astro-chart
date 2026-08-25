"""Gap-audit fix (2026-08, HIGH priority item 3): test coverage for
registry_v12_builder.py -- the driver module created earlier in this same
audit pass (HIGH item 2) to close the gap where the README documented a
`python -m jyotish.registry_v12_builder` build command that had no
implementation anywhere in the codebase.

These tests exercise the pure, offline-testable surface: _read_v11_registry's
defensive parsing/validation, and build_registry_v12's per-branch error
aggregation contract (a branch that fails to enrich must be reported, never
silently dropped). They do not exercise the full real-registry build (that
was already verified manually against the live 205-branch registry and the
real registry_coverage_validator -- see the module's own docstring / the
audit notes) because a full run needs Field_Determination.competency_ontology,
which this test suite does not assume is importable in every environment.
"""
from __future__ import annotations

import json

import pytest

from jyotish.registry_v12_builder import (
    RegistryBuildError,
    _read_v11_registry,
    build_registry_v12,
)


# ── _read_v11_registry ──────────────────────────────────────────────────────

def test_read_v11_registry_missing_file_raises_build_error(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(RegistryBuildError, match="not found"):
        _read_v11_registry(missing)


def test_read_v11_registry_invalid_json_raises_build_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(RegistryBuildError, match="not valid JSON"):
        _read_v11_registry(bad)


def test_read_v11_registry_empty_branches_raises_build_error(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"branches": {}}), encoding="utf-8")
    with pytest.raises(RegistryBuildError, match="no branches"):
        _read_v11_registry(empty)


def test_read_v11_registry_strips_stray_nul_and_cr_bytes(tmp_path):
    # Mirrors registry_loader_v12.py's own defensive read, per this module's
    # docstring -- a file with stray NUL/CR bytes (observed historically from
    # editor/encoding issues in this project) must still parse.
    dirty = tmp_path / "dirty.json"
    payload = json.dumps({"branches": {"x": {"field_id": "x"}}}).encode("utf-8")
    dirty.write_bytes(payload.replace(b"{", b"\x00{", 1).replace(b'"branches"', b'"branches"\r'))
    data = _read_v11_registry(dirty)
    assert "x" in data["branches"]


def test_read_v11_registry_valid_file_roundtrips(tmp_path):
    src = tmp_path / "v11.json"
    payload = {"branches": {"aerospace_engineering": {"field_id": "aerospace_engineering"}}, "version": "11.0"}
    src.write_text(json.dumps(payload), encoding="utf-8")
    data = _read_v11_registry(src)
    assert data["version"] == "11.0"
    assert "aerospace_engineering" in data["branches"]


# ── build_registry_v12 error aggregation ────────────────────────────────────

def test_build_registry_v12_reports_all_failing_branches_not_just_first(tmp_path):
    src = tmp_path / "v11.json"
    # Branches deliberately malformed (a non-mapping branch value, which
    # enrich_branch_v12 cannot even dict()-copy) so every one fails -- this
    # test only cares that ALL failures are collected and named in the
    # raised error, not silently dropped after the first one.
    payload = {"branches": {
        "bad_branch_one": "not a mapping",
        "bad_branch_two": ["also", "not", "a", "mapping"],
    }}
    src.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RegistryBuildError) as excinfo:
        build_registry_v12(
            src,
            field_to_family={},
            family_meta={},
        )
    message = str(excinfo.value)
    assert "bad_branch_one" in message
    assert "bad_branch_two" in message


def test_build_registry_v12_succeeds_with_well_formed_branch_and_minimal_ontology(tmp_path):
    src = tmp_path / "v11.json"
    payload = {"branches": {
        "sample_field": {
            "field_id": "sample_field",
            "field_label": "Sample Field",
            "track": "engineering",
        },
    }}
    src.write_text(json.dumps(payload), encoding="utf-8")

    result = build_registry_v12(
        src,
        field_to_family={"sample_field": "engineering_family"},
        family_meta={"engineering_family": {"label": "Engineering"}},
    )
    assert result["schema_version"] == "v12.0_enriched_registry"
    assert result["source_branch_count"] == 1
    assert result["built_branch_count"] == 1
    assert "sample_field" in result["branches"]
