"""Phase A unit tests for jyotish/composite_v2.py -- the per-planet primitive
functions behind the refined §10 composite formula (see
SPEC_LITERAL_ARCHITECTURE_MIGRATION_PLAN.md, Phase A).

These tests exercise the NEW module in isolation. Nothing here touches the
live scoring pipeline (Field_Determination/field_methods/__init__.py or
jyotish/tiered_ranking.py), which remains the shipped scoring path until
Phase C. Per the migration plan's Phase A checkpoint: the full existing
suite must stay green (nothing wired in), and these new tests specifically
verify the refinement mechanics called out in the plan.
"""
import math

from jyotish.composite_v2 import (
    dignity_mult,
    compute_graha_yuddha_dual_criteria,
    compute_tier1_strength,
    compute_tier2_adjustment,
    compute_adjusted_strength,
    compute_d10_strength,
    compute_d9_sustainability_mult,
    compute_d9_gate,
    compute_wealth_bonus_per_planet,
    compute_dasha_continuity_bonus_per_planet,
    cap_node_base_strength,
    dominant_significator_is_node,
    compute_birth_time_confidence_factor,
    compute_field_score,
)


class TestTier1Strength:
    def test_dignity_mult_known_labels(self):
        assert dignity_mult("EXALTED") == 1.40
        assert dignity_mult("DEBILITATED") == 0.65
        assert dignity_mult("") == 1.00
        assert dignity_mult("garbage") == 1.00

    def test_tier1_strength_combines_base_dignity_and_war(self):
        base = {"Mars": 0.8, "Jupiter": 0.6}
        dignities = {"Mars": "EXALTED", "Jupiter": "NEUTRAL"}
        war_mult = {"Mars": 1.05, "Jupiter": 1.0}
        out = compute_tier1_strength(base, dignities, war_mult)
        assert out["Mars"] == round(0.8 * 1.40 * 1.05, 6)
        assert out["Jupiter"] == round(0.6 * 1.00 * 1.0, 6)


class TestGrahaYuddhaDualCriteria:
    def test_no_war_when_far_apart(self):
        result = compute_graha_yuddha_dual_criteria({"Mars": 10.0, "Saturn": 200.0})
        assert result["in_graha_yuddha"] is False
        assert result["graha_yuddha_mult"]["Mars"] == 1.0

    def test_war_with_criteria_agreement_declares_winner(self):
        # Venus (larger apparent size) vs Mercury (smaller) within 1 degree,
        # AND Venus has the lower longitude -- both criteria agree on Venus.
        result = compute_graha_yuddha_dual_criteria({"Venus": 100.0, "Mercury": 100.5})
        assert result["in_graha_yuddha"] is True
        war = result["wars"][0]
        assert war["criteria_agree"] is True
        assert war["winner"] == "Venus"
        assert result["graha_yuddha_mult"]["Venus"] > 1.0
        assert result["graha_yuddha_mult"]["Mercury"] < 1.0

    def test_war_with_criteria_disagreement_is_symmetric(self):
        # Mercury has the SMALLER apparent size but the LOWER longitude --
        # size says Venus wins, longitude says Mercury wins -- disagreement.
        result = compute_graha_yuddha_dual_criteria({"Mercury": 100.0, "Venus": 100.5})
        war = result["wars"][0]
        assert war["criteria_agree"] is False
        assert war["winner"] is None
        # Both planets take the same, smaller, symmetric penalty.
        assert result["graha_yuddha_mult"]["Mercury"] == result["graha_yuddha_mult"]["Venus"]
        assert 0.90 < result["graha_yuddha_mult"]["Mercury"] < 1.0

    def test_cross_sign_boundary_war_detected(self):
        # 29.7 Pisces (~359.7) and 0.3 Aries (~0.3): 0.6 degrees apart across
        # the 0/360 wraparound -- must still be detected as a war.
        result = compute_graha_yuddha_dual_criteria({"Jupiter": 359.7, "Mars": 0.3})
        assert result["in_graha_yuddha"] is True


class TestTier2Adjustment:
    def test_no_factors_returns_neutral(self):
        assert compute_tier2_adjustment([]) == 1.0

    def test_single_mild_penalty_close_to_face_value(self):
        # One factor at 0.90 should land close to 0.90 (well within the cap).
        result = compute_tier2_adjustment([0.90])
        assert 0.89 <= result <= 0.91

    def test_three_mild_penalties_do_not_compound_past_the_cap(self):
        # Migration plan §1a.1's specific claim: three ~10% dings (0.90 *
        # 0.93 * 0.88 = ~0.7376 if naively multiplied) should land around
        # 0.85-0.88, NOT ~0.74, once combined via the capped log-average.
        naive_product = 0.90 * 0.93 * 0.88
        result = compute_tier2_adjustment([0.90, 0.93, 0.88])
        assert result > naive_product
        assert 0.85 <= result <= 0.91

    def test_severe_single_factor_still_bounded_by_cap(self):
        # A single very severe factor (e.g. 0.5) should be clamped, not
        # applied at full face value -- the cap protects both directions.
        result = compute_tier2_adjustment([0.5])
        assert result >= math.exp(-0.25) - 1e-6

    def test_bonus_factors_capped_on_upside_too(self):
        result = compute_tier2_adjustment([1.5, 1.4, 1.3])
        assert result <= math.exp(0.20) + 1e-6


class TestAdjustedStrength:
    def test_yogakaraka_applied_outside_capped_layer(self):
        tier1 = {"Saturn": 1.0}
        # Tier-2 factors alone would cap around exp(0.20) =~ 1.221 upside.
        tier2 = {"Saturn": [1.3, 1.3, 1.3]}
        yk = {"Saturn": 1.25}  # spec's own Yogakaraka ceiling
        out = compute_adjusted_strength(tier1, tier2, yk)
        # Yogakaraka's 1.25 must show up in full, multiplied on top of the
        # (already-capped) Tier-2 adjustment -- not itself squashed by the cap.
        tier2_adj = compute_tier2_adjustment([1.3, 1.3, 1.3])
        assert out["Saturn"] == round(1.0 * tier2_adj * 1.25, 6)


class TestD10Strength:
    def test_kendra_trikona_placement_stronger_than_dusthana(self):
        d10_chart = {"Lagna": "Aries", "Mars": "Cancer", "Saturn": "Virgo"}
        # Cancer is H4 from Aries (kendra); Virgo is H6 from Aries (dusthana).
        out = compute_d10_strength(d10_chart, {"Mars": "NEUTRAL", "Saturn": "NEUTRAL"})
        assert out["Mars"] > out["Saturn"]

    def test_bounded_to_documented_band(self):
        d10_chart = {"Lagna": "Aries", "Jupiter": "Aries"}  # H1, kendra+trikona, exalted-ish dignity input
        out = compute_d10_strength(d10_chart, {"Jupiter": "EXALTED"})
        assert 0.7 <= out["Jupiter"] <= 1.3


class TestD9Gate:
    def test_per_planet_dignity_mapping_bounded(self):
        assert compute_d9_sustainability_mult("EXALTED") == 1.15
        assert compute_d9_sustainability_mult("DEBILITATED") <= 0.88  # near the 0.85 floor
        assert compute_d9_sustainability_mult("") == 1.0  # neutral/no-data default

    def test_field_gate_is_weighted_average_not_additive_term(self):
        field_affinity = {"Mars": 0.6, "Saturn": 0.4}
        d9_dig = {"Mars": "EXALTED", "Saturn": "DEBILITATED"}
        gate = compute_d9_gate(field_affinity, d9_dig)
        # Should sit between the two bounds, weighted toward Mars (0.6 share).
        assert 0.85 <= gate <= 1.15
        assert gate > 1.0  # Mars's exaltation (weight 0.6) should tip it positive

    def test_missing_affinity_returns_neutral(self):
        assert compute_d9_gate({}, {}) == 1.0


class TestWealthBonusPerPlanet:
    def test_primary_axis_planet_gets_primary_magnitude(self):
        house_lords = {"2": "Venus", "11": "Jupiter"}
        planet_house = {"Venus": 2, "Jupiter": 11}
        out = compute_wealth_bonus_per_planet(house_lords, planet_house)
        # Venus rules 2nd and sits in 2nd (own sign placement) -- primary axis.
        assert out.get("Venus") == 0.115

    def test_no_yoga_planet_absent_from_dict(self):
        house_lords = {"2": "Venus", "11": "Jupiter"}
        planet_house = {"Venus": 7, "Jupiter": 3}
        out = compute_wealth_bonus_per_planet(house_lords, planet_house)
        assert "Mars" not in out


class TestDashaContinuityBonusPerPlanet:
    def test_karaka_lord_in_window_gets_bonus(self):
        seq = [
            {"lord": "Sun", "start_age": 0, "end_age": 10},
            {"lord": "Mars", "start_age": 10, "end_age": 20},
            {"lord": "Rahu", "start_age": 20, "end_age": 38},
        ]
        out = compute_dasha_continuity_bonus_per_planet(seq, atmakaraka="Mars")
        assert out.get("Mars", 0.0) > 0.0
        assert "Sun" not in out or out.get("Sun", 0.0) == 0.0

    def test_no_dasha_data_returns_empty(self):
        assert compute_dasha_continuity_bonus_per_planet([]) == {}


class TestNodeStrengthCap:
    def test_capped_band(self):
        assert cap_node_base_strength(0.0) == 0.6
        assert cap_node_base_strength(1.0) == 0.9
        mid = cap_node_base_strength(0.5)
        assert 0.6 < mid < 0.9

    def test_node_never_reads_as_strongest(self):
        # Even at raw strength 1.0, the capped node strength (0.9) must stay
        # below a plausible strong classical planet's base_strength (up to 1.0
        # by construction, per shadbala.py's own normalization to the
        # chart's strongest planet).
        assert cap_node_base_strength(1.0) < 1.0

    def test_dominant_significator_is_node_flag(self):
        assert dominant_significator_is_node({"Rahu": 0.6, "Jupiter": 0.4}) is True
        assert dominant_significator_is_node({"Jupiter": 0.6, "Rahu": 0.4}) is False
        assert dominant_significator_is_node({}) is False


class TestBirthTimeConfidenceFactor:
    def test_exact_is_full_confidence(self):
        assert compute_birth_time_confidence_factor("exact") == 1.0

    def test_approximate_and_unknown_compress_score(self):
        assert compute_birth_time_confidence_factor("approximate") < 1.0
        assert compute_birth_time_confidence_factor("unknown") < compute_birth_time_confidence_factor("approximate")

    def test_unrecognized_defaults_to_exact(self):
        assert compute_birth_time_confidence_factor("") == 1.0
        assert compute_birth_time_confidence_factor(None) == 1.0


class TestComputeFieldScore:
    def test_end_to_end_shape(self):
        field_affinity = {"Mars": 0.6, "Jupiter": 0.4}
        adjusted_strength = {"Mars": 1.1, "Jupiter": 0.9}
        d10_strength = {"Mars": 1.1, "Jupiter": 1.0}
        wealth_bonus = {"Mars": 0.08}
        dasha_bonus = {"Jupiter": 0.1}
        result = compute_field_score(
            field_affinity, adjusted_strength, d10_strength, 1.0,
            wealth_bonus, dasha_bonus, birth_time_confidence_factor=1.0,
        )
        assert result["field_score"] > 0
        assert "d1d10_component" in result and "wealth_component" in result and "dasha_component" in result

    def test_empty_affinity_returns_zero(self):
        result = compute_field_score({}, {}, {}, 1.0, {}, {})
        assert result["field_score"] == 0.0

    def test_birth_time_confidence_scales_final_score(self):
        field_affinity = {"Mars": 1.0}
        adjusted_strength = {"Mars": 1.0}
        d10_strength = {"Mars": 1.0}
        full = compute_field_score(field_affinity, adjusted_strength, d10_strength, 1.0, {}, {}, 1.0)
        reduced = compute_field_score(field_affinity, adjusted_strength, d10_strength, 1.0, {}, {}, 0.75)
        assert reduced["field_score"] < full["field_score"]
        assert reduced["field_score"] == round(full["field_score"] * 0.75, 2)
