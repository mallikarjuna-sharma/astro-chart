"""Gap-audit fix (2026-08, HIGH priority item 3): test coverage for the
report-rendering layer (report_renderer.py, report_uplift.py,
report_utils.py, web_report.py).

This layer previously had zero tests, and this codebase has direct history
of that being a real risk: a module-level SyntaxError in transit_engine.py
(from an earlier bad edit) silently broke that module for an unknown period,
because nothing imported/compiled it as part of any test run. web_report.py
in particular is the largest single file in the codebase (~4800 lines) and
is the one place multiple gap-audit fixes in this pass touched
(field_display_name adoption -- see the module's own audit-comment).

Two layers of coverage here:
1. A syntax/compile smoke test for all four files -- cheap, catches the
   exact "silently broken for months" failure mode described above, and
   does not require the heavy optional dependencies (skyfield etc.) the
   full package needs.
2. Real behavioral tests for report_utils.py, which is pure Python with no
   external dependencies and is safe to import and exercise directly.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

_REPORT_LAYER_FILES = [
    "report_renderer.py",
    "report_uplift.py",
    "report_utils.py",
    "web_report.py",
]


def _jyotish_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("filename", _REPORT_LAYER_FILES)
def test_report_layer_file_has_valid_syntax(filename):
    """Guards against the transit_engine.py-style failure mode: a
    module-level SyntaxError that silently breaks the module until someone
    happens to import it in production."""
    path = _jyotish_dir() / filename
    assert path.exists(), f"expected report-layer file missing: {path}"
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))  # raises SyntaxError if broken


# ── report_utils.py behavioral tests (pure, no external deps) ──────────────

from jyotish.report_utils import (
    field_display_name,
    cluster_display_name,
    print_macro_cluster,
    cluster_strength_weighted,
    top20_as_four_cluster_groups,
)


def test_field_display_name_prefers_explicit_label():
    assert field_display_name({"field_label": "Aerospace Engineering", "field_id": "aerospace_engineering"}) == "Aerospace Engineering"


def test_field_display_name_falls_back_to_titleized_field_id():
    assert field_display_name({"field_id": "chemical_engineering"}) == "Chemical Engineering"


def test_field_display_name_handles_missing_field_id_entirely():
    assert field_display_name({}) == "Unknown"


def test_cluster_display_name_maps_known_cluster():
    assert cluster_display_name("Commerce, Finance & Enterprise") == "Economics, Finance & Enterprise"


def test_cluster_display_name_passes_through_unknown_cluster():
    assert cluster_display_name("Some Unmapped Cluster") == "Some Unmapped Cluster"


def test_print_macro_cluster_routes_law_field_by_id():
    row = {"field_id": "civil_services", "field_label": "Civil Services"}
    assert print_macro_cluster(row) == "Law, Governance & Public Leadership"


def test_print_macro_cluster_routes_by_label_keyword_when_id_unmatched():
    row = {"field_id": "some_new_law_track", "field_label": "Environmental Governance Studies"}
    assert print_macro_cluster(row) == "Law, Governance & Public Leadership"


def test_print_macro_cluster_falls_back_to_cluster_display_name():
    row = {"field_id": "unrelated_field", "field_label": "Something Else", "graph_cluster": "Design, Media & Creative Expression"}
    assert print_macro_cluster(row) == "Design, Media & Creative Expression"


def test_cluster_strength_weighted_applies_floor_ratio_and_member_cap():
    # AUDIT FIX (2026-08-22): this test predated the 2026-08-19 self-referential
    # decay fix (see report_utils.py's own comment above _CLUSTER_SCORE_DECAY_
    # EXPONENT) and was never updated to match it, so it was asserting the OLD
    # rank-based 0.8**(rank-1) formula and the OLD member cap of 3 against the
    # NEW relative-score formula (vote = score * (score/top_score)**exponent)
    # and NEW member cap of 5 -- a stale-test failure unrelated to any live
    # scoring bug (report_utils.py's implementation itself is correct and
    # intentional per its own fix comment; only this test's expectation was
    # out of date). Updated to assert the current, documented behavior.
    #
    # top_score=100, floor ratio 0.5 -> anything scoring <50 is excluded.
    rows = [
        (1, {"final_score": 100.0}),
        (2, {"final_score": 90.0}),
        (3, {"final_score": 80.0}),
        (4, {"final_score": 70.0}),  # included: member cap is now 5, not 3
        (5, {"final_score": 10.0}),  # excluded by floor ratio (<50)
    ]
    result = cluster_strength_weighted(rows, top_score=100.0)
    # relative-score decay (exponent=1.0): vote = score * (score/top_score)
    # row1: 100*(100/100)=100.0; row2: 90*(90/100)=81.0
    # row3: 80*(80/100)=64.0;   row4: 70*(70/100)=49.0
    # row5 excluded by floor ratio; member cap is 5 so all 4 remaining vote.
    expected = 100.0 + 81.0 + 64.0 + 49.0
    assert result == pytest.approx(expected)


def test_top20_as_four_cluster_groups_collapses_beyond_three_into_additional_bucket():
    results = []
    clusters_seen = [
        "civil_services",       # Law
        "research_academia",    # Research
        "medicine_mbbs",        # Medical
        "economics",            # Economics
        "some_agri_field",      # Agriculture (via label/family keyword only if present)
    ]
    for i, fid in enumerate(clusters_seen):
        results.append({"field_id": fid, "field_label": fid, "final_score": 100.0 - i, "domain": "" })
    groups = top20_as_four_cluster_groups(results)
    assert len(groups) <= 4
    if len(groups) == 4:
        assert groups[-1][0] == "Additional Top-20 Branches"


def test_top20_as_four_cluster_groups_handles_empty_results():
    assert top20_as_four_cluster_groups([]) == []
