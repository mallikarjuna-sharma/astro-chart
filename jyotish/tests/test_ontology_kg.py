"""Knowledge-graph ontology contract tests.

The KG layer is intentionally score-neutral: it enriches engine rows with
structure that the flat competency ontology cannot express, especially
multi-parent family membership and genericity flags.
"""
from __future__ import annotations

from jyotish import ontology_kg as kg


def test_kg_has_full_flat_ontology_coverage():
    problems = kg.validate_full_coverage()
    assert problems == {
        "fields_missing_from_graph": [],
        "families_missing_from_graph": [],
        "competencies_missing_from_graph": [],
        "fields_with_no_family_parent": [],
    }


def test_attach_graph_diagnostics_is_score_neutral_and_additive():
    rows = [
        {"field_id": "architecture", "field_label": "Architecture", "final_score": 77.7},
        {"field_id": "real_estate_management", "field_label": "Real Estate Management", "final_score": 66.6},
    ]

    out = kg.attach_graph_diagnostics(rows)

    assert out is rows
    assert out[0]["final_score"] == 77.7
    assert out[1]["final_score"] == 66.6

    arch_memberships = out[0]["graph_family_memberships"]
    assert len(arch_memberships) >= 2
    assert any(m[2] == "secondary" for m in arch_memberships)
    assert out[0]["graph_cluster"]
    assert "spans multiple career families" in out[0]["graph_note"]

    assert out[1]["graph_broadness_penalty"] > 0
    assert "genericity discount" in out[1]["graph_note"]


def test_graph_ranker_uses_real_shadbala_evidence():
    ranked = kg.rank_fields_via_graph(
        {
            "Mercury": 520.0,
            "Saturn": 430.0,
            "Rahu": 420.0,
            "Venus": 300.0,
        },
        top_n=5,
    )

    assert len(ranked) == 5
    assert all(len(row) == 3 for row in ranked)
    assert ranked[0][2] == 100.0
