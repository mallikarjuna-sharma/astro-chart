"""JyotishAI — competency_ontology.py G22/G27/G28/G31 sanity tests.

Ontology audit follow-up (2026-07-04): these four gaps were previously
deferred ("need real new scoring logic... didn't want to touch the
calibrated astrology engine in the same pass as the ontology
restructuring"). This test file pins the contract of each new function so a
future refactor can't silently break what engine.py now depends on, and
verifies the bounded-adjustment caps that keep G22 safe to run alongside
the regression-locked deterministic score.

Run with:
    pytest jyotish/tests/test_competency_ontology_g22_g31.py -v
"""
import pytest

from Field_Determination import competency_ontology as co


def _field(field_id="design_ux_product", domain="arts", final_score=70.0,
           affinity_planets=None, competency=None):
    aff = affinity_planets or {"Venus": 0.6, "Mercury": 0.4}
    r = {
        "field_id": field_id,
        "domain": domain,
        "final_score": final_score,
        "affinity_planets": aff,
        "top_affinity_planets": aff,
    }
    if competency:
        r["competency"] = competency
    else:
        r["competency"] = co.get_ontology(field_id, domain)["competency"]
    return r


class TestG22YogaAwareFraming:
    def test_no_yogas_gives_zero_bonus(self):
        framing = co.build_yoga_aware_framing(_field(), [])
        assert framing["yoga_alignment_bonus_pct"] == 0.0
        assert framing["matched_yogas"] == []

    def test_major_mahapurusha_yoga_matches_its_planet(self):
        # design_creative competency includes Venus -> Malavya (Venus) should match.
        framing = co.build_yoga_aware_framing(_field(competency="design_creative"), ["Malavya"])
        assert framing["yoga_alignment_bonus_pct"] == 5.0
        assert framing["matched_yogas"][0]["tier"] == "major"
        assert "Venus" in framing["matched_yogas"][0]["planets"]

    def test_unrelated_yoga_does_not_match(self):
        # Ruchaka is Mars-only; design_creative's planets are Venus/Mercury/Moon.
        framing = co.build_yoga_aware_framing(_field(competency="design_creative"), ["Ruchaka"])
        assert framing["yoga_alignment_bonus_pct"] == 0.0

    def test_dynamic_parivartana_yoga_parses_planets(self):
        framing = co.build_yoga_aware_framing(
            _field(competency="design_creative"), ["Parivartana_Venus_Saturn"]
        )
        assert framing["matched_yogas"][0]["tier"] == "minor"
        assert framing["yoga_alignment_bonus_pct"] == 2.0

    def test_bonus_is_hard_capped_regardless_of_match_count(self):
        framing = co.build_yoga_aware_framing(
            _field(competency="design_creative"),
            ["Malavya", "Saraswati", "Parivartana_Venus_Saturn"],
        )
        assert framing["yoga_alignment_bonus_pct"] <= 5.0

    def test_apply_adjustment_never_exceeds_cap_and_resorts(self):
        results = [_field(field_id="a", final_score=70.0, competency="design_creative"),
                   _field(field_id="b", final_score=60.0, competency="design_creative")]
        adjusted = co.apply_yoga_alignment_adjustment(results, ["Malavya"])
        assert adjusted[0]["final_score"] <= round(70.0 * 1.05, 2)
        assert adjusted[0]["final_score"] >= adjusted[1]["final_score"]

    def test_empty_yogas_still_attaches_framing_without_reordering(self):
        results = [_field(field_id="a", final_score=70.0), _field(field_id="b", final_score=60.0)]
        out = co.apply_yoga_alignment_adjustment(results, [])
        assert out[0]["final_score"] == 70.0
        assert "yoga_framing" in out[0]


class TestG27AptitudeExplanation:
    def test_returns_expected_keys(self):
        apt = co.build_aptitude_explanation(_field())
        for key in ("aptitude_dimensions", "top_aptitude_traits", "aptitude_narrative"):
            assert key in apt

    def test_empty_affinity_gives_empty_profile(self):
        apt = co.build_aptitude_explanation({})
        assert apt["top_aptitude_traits"] == []
        assert apt["aptitude_dimensions"] == {}

    def test_mercury_dominant_field_surfaces_analytical_trait(self):
        apt = co.build_aptitude_explanation(_field(affinity_planets={"Mercury": 1.0}))
        assert "analytical reasoning" in apt["top_aptitude_traits"]

    def test_dimensions_are_normalized_0_to_1(self):
        apt = co.build_aptitude_explanation(_field(affinity_planets={"Mercury": 0.6, "Saturn": 0.4}))
        for v in apt["aptitude_dimensions"].values():
            assert 0.0 <= v <= 1.0


class TestG28LifeStageEvolution:
    _DASHA_SEQ = [
        {"lord": "Saturn", "start_age": 0, "end_age": 19},
        {"lord": "Mercury", "start_age": 19, "end_age": 36},
        {"lord": "Ketu", "start_age": 36, "end_age": 43},
    ]

    def test_empty_sequence_returns_empty_stages(self):
        assert co.compute_life_stage_competency_evolution([]) == []

    def test_stages_are_chronological(self):
        stages = co.compute_life_stage_competency_evolution(self._DASHA_SEQ)
        starts = [s["start_age"] for s in stages]
        assert starts == sorted(starts)

    def test_current_age_flags_exactly_one_stage(self):
        stages = co.compute_life_stage_competency_evolution(self._DASHA_SEQ, current_age=25)
        current_flags = [s["is_current"] for s in stages]
        assert sum(current_flags) == 1
        assert stages[1]["is_current"] is True

    def test_narrative_mentions_current_lord_and_next_shift(self):
        stages = co.compute_life_stage_competency_evolution(self._DASHA_SEQ, current_age=25)
        narrative = co.build_life_stage_narrative(stages, current_age=25)
        assert "Mercury" in narrative
        assert "Next shift" in narrative
        assert "Ketu" in narrative

    def test_no_stages_gives_graceful_message(self):
        narrative = co.build_life_stage_narrative([], current_age=25)
        assert "No dasha sequence" in narrative


class TestG31CrossChartNormalization:
    def test_unknown_family_reports_insufficient_data(self):
        result = co.normalize_family_score_cross_chart("totally_unknown_family_xyz", 70.0)
        assert result["cross_chart_band"] == "insufficient_reference_data"
        assert result["cross_chart_percentile"] is None
        assert result["is_proxy_calibration"] is True

    def test_known_family_median_score_lands_near_50th_percentile(self):
        ref = co._load_family_score_reference()
        fams = ref.get("families", {})
        if "design_thinking" not in fams:
            pytest.skip("reference corpus not present in this environment")
        median = fams["design_thinking"]["p50"]
        result = co.normalize_family_score_cross_chart("design_thinking", median)
        assert abs(result["cross_chart_percentile"] - 50.0) < 2.0

    def test_percentile_is_monotonic_in_score(self):
        ref = co._load_family_score_reference()
        if "design_thinking" not in ref.get("families", {}):
            pytest.skip("reference corpus not present in this environment")
        low = co.normalize_family_score_cross_chart("design_thinking", 55.0)
        high = co.normalize_family_score_cross_chart("design_thinking", 95.0)
        assert low["cross_chart_percentile"] < high["cross_chart_percentile"]


class TestFullIntegrationEntryPoint:
    def test_apply_competency_ontology_layer_attaches_all_new_signals(self):
        results = [
            _field(field_id="design_ux_product", final_score=70.0),
            _field(field_id="textile_design", final_score=65.0,
                    affinity_planets={"Venus": 0.5, "Moon": 0.5}),
        ]
        dasha_seq = [{"lord": "Venus", "start_age": 20, "end_age": 40}]

        out_results, cluster_report = co.apply_competency_ontology_layer(
            results,
            detected_yogas=["Malavya"],
            dasha_sequence=dasha_seq,
            current_age=25,
        )
        for r in out_results:
            assert "yoga_framing" in r
            assert "aptitude_explanation" in r
        assert "life_stage_evolution" in cluster_report
        assert cluster_report["life_stage_evolution"]["stages"]

    def test_disabling_new_layers_still_returns_valid_report(self):
        results = [_field()]
        out_results, cluster_report = co.apply_competency_ontology_layer(
            results, enable_yoga_framing=False, enable_cross_chart_norm=False,
        )
        assert out_results
        assert "clusters" in cluster_report
