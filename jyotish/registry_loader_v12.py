"""Fail-fast registry loader for JyotishAI v12.

Drop this file at: jyotish/registry_loader_v12.py
Then patch engine_io._load_course_registry() to call load_course_registry_v12().
"""
from __future__ import annotations

import json
import copy
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
            # §4 remediation (2026-08-19): this used to run the coverage
            # validator ONLY for a v12 file (`path.name.endswith("v12.json")`)
            # -- if the v12 file was missing/corrupted and the loader fell
            # back to a legacy v11 file, the integrity check was silently
            # skipped entirely, letting a scoring run proceed with orphaned
            # registry/affinity/ontology ids on either side. Spec §4 requires
            # this check to run before EVERY scoring run, unconditionally.
            # Now always runs; `check_v12_schema` (defaulted from the actual
            # filename inside validate_all_coverage) keeps the genuinely
            # v12-only schema-section check from misfiring against a
            # legitimate v11 fallback, while the registry/affinity/ontology
            # ID-orphan check -- the actual integrity guarantee §4 asks
            # for -- now runs against BOTH v11 and v12 unconditionally.
            if validate:
                try:
                    from .registry_coverage_validator import validate_all_coverage
                    validate_all_coverage(path, fail_fast=True)
                except Exception as exc:
                    raise RuntimeError(f"Registry coverage validation failed for {path}: {exc}") from exc
            # First-class modern systems/operations vocabulary. These leaves
            # inherit audited route metadata from the nearest established
            # foundation while retaining their own identity and affinity.
            aliases = {
                "operations_research": ("statistics_data_science", "Operations Research & Decision Systems"),
                "information_systems": ("information_technology", "Information Systems"),
                "it_systems_planning": ("information_technology", "IT Systems Planning"),
                "software_infrastructure_engineering": ("cloud_devops", "Software Infrastructure Engineering"),
                "engineering_management": ("construction_engineering_management", "Engineering Management"),
                "it_business_advisory": ("business_management", "IT Business Advisory"),
                "it_governance": ("cybersecurity", "IT Governance & Technology Risk"),
            }
            branches = dict(branches)
            for field_id, (parent_id, label) in aliases.items():
                if field_id in branches or parent_id not in branches:
                    continue
                meta = copy.deepcopy(branches[parent_id])
                meta.update({"label": label, "field": label, "description": f"{label}; derived from the audited {parent_id} foundation metadata."})
                meta["ontology_parent"] = parent_id
                # Gap-audit fix (2026-08): these 7 fields are a full deep-copy
                # of the parent branch's metadata (routes, career_outcomes,
                # curriculum, education_realism, market, risk, etc.) relabeled
                # under a distinct name -- e.g. "Platform Engineering" is
                # today literally "Cloud DevOps" metadata with a new label.
                # `ontology_parent` above already recorded this, but nothing
                # previously marked the record as an alias in an
                # unambiguous, machine-checkable way, so a report/consumer
                # that doesn't specifically look for `ontology_parent` could
                # present course/college/career-outcome details as if they
                # were independently curated for this exact field. These two
                # explicit flags let any downstream renderer/report detect
                # and disclose that (e.g. "course & outcome details shown are
                # inherited from <parent_id>, not independently curated for
                # this specific field") without changing which branches
                # exist, their ranking, or any scoring behavior.
                meta["is_registry_alias"] = True
                meta["alias_of"] = parent_id
                branches[field_id] = meta
            return branches
        except Exception as exc:
            last_error = exc
    raise FileNotFoundError(f"No usable course registry found. Tried: {[str(p) for p in candidates]}. Last error: {last_error}")
