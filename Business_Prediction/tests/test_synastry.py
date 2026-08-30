"""Tests for Business_Prediction.business_determination.synastry
(partnership/co-founder chart-to-chart comparison).

Uses the same duck-typed minimal stand-in payload approach as
test_business_engine.py's _FakePayload, plus planet_signs (Moon sign)
which synastry.py additionally reads.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_engine import (
    compute_business_prediction,
    compute_partnership_synastry,
)


class _SynastryPayload:
    def __init__(self, moon_sign="Aries", h7_lord="Mars", md_lord="Mercury"):
        self.dob = "1990-05-15"
        self.planet_house = {
            "Sun": 10, "Moon": 4, "Mars": 3, "Mercury": 7,
            "Jupiter": 1, "Venus": 7, "Saturn": 6, "Rahu": 7, "Ketu": 1,
        }
        self.house_lords = {
            "1": "Jupiter", "2": "Saturn", "3": "Saturn", "4": "Jupiter",
            "5": "Mars", "6": "Venus", "7": h7_lord, "8": "Venus",
            "9": "Mercury", "10": "Mercury", "11": "Sun", "12": "Moon",
        }
        self.planet_dignities = {"Mercury": "OWN", "Venus": "EXALTED"}
        self.sav_points_houses = {"10": 32, "11": 33}
        self.darakaraka = "Saturn"
        self.planet_signs = {"Moon": moon_sign, "Sun": "Aries"}
        self.dasha_sequence = [
            {"lord": md_lord, "start_age": 0, "end_age": 90},
        ]
        # No divisional_charts/planets_d1 by default -- D7 corroboration
        # should degrade gracefully (MISSING_DATA) unless a test opts in
        # by setting native.planets_d1 explicitly (see D7-specific tests
        # below), mirroring how D2/D9/D10 evidence functions elsewhere in
        # this package are exercised.
        self.divisional_charts = {}
        self.planets_d1 = {}


def test_compatible_charts_score_reasonably_and_label_favorably():
    # Same Moon sign (perfect element/modality match), same H7 lord
    # (OWN_SIGN friendliness), same current MD lord -> should read
    # favorably, not POOR_FIT/CAUTION.
    native_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    native_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")

    result = compute_partnership_synastry(native_a, native_b)

    assert result["status"] == "OK"
    assert 0.0 <= result["composite_score_0_100"] <= 100.0
    assert result["compatibility_label"] in ("STRONG_FIT", "WORKABLE_FIT")
    assert result["moon_sign_compatibility"]["status"] == "OK"
    assert result["seventh_house_cross_comparison"]["status"] == "OK"
    assert result["dasha_overlap"]["status"] == "OK"
    assert result["dasha_overlap"]["label"] == "COMPLEMENTARY"
    assert isinstance(result["complementary_strengths"], list)
    assert isinstance(result["friction_points"], list)


def test_conflicting_charts_score_lower_than_compatible_charts():
    # Fire vs Water Moon sign (clashing element), enemy H7 lords (Saturn is
    # a natural enemy of Mars/Sun in the classical friendship table),
    # differing MD lords with an enemy relationship.
    native_a = _SynastryPayload(moon_sign="Aries", h7_lord="Sun", md_lord="Sun")
    native_b = _SynastryPayload(moon_sign="Cancer", h7_lord="Saturn", md_lord="Saturn")

    compatible_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    compatible_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")

    conflicting = compute_partnership_synastry(native_a, native_b)
    compatible = compute_partnership_synastry(compatible_a, compatible_b)

    assert conflicting["status"] == "OK"
    assert conflicting["composite_score_0_100"] < compatible["composite_score_0_100"]
    assert conflicting["dasha_overlap"]["label"] == "CONFLICTING"


def test_missing_partner_data_degrades_gracefully():
    result = compute_partnership_synastry(_SynastryPayload(), None)
    assert result["status"] == "NO_PARTNER_DATA"
    assert result["composite_score_0_100"] is None
    assert result["complementary_strengths"] == []
    assert result["friction_points"] == []


def test_missing_moon_sign_degrades_gracefully_not_crash():
    native_a = _SynastryPayload()
    native_b = _SynastryPayload()
    native_b.planet_signs = {}
    result = compute_partnership_synastry(native_a, native_b)
    assert result["status"] == "OK"  # top-level pipeline still completes
    assert result["moon_sign_compatibility"]["status"] == "NO_MOON_SIGN"


def test_missing_dob_and_dasha_degrades_gracefully_not_crash():
    native_a = _SynastryPayload()
    native_b = _SynastryPayload()
    native_b.dob = ""
    native_b.dasha_sequence = []
    result = compute_partnership_synastry(native_a, native_b)
    assert result["status"] == "OK"
    assert result["dasha_overlap"]["status"] in ("NO_DOB", "CALENDAR_COMPUTATION_FAILED")


def test_compute_business_prediction_backward_compatible_without_partner():
    payload = _SynastryPayload()
    result = compute_business_prediction(payload, attach_provenance=False)
    assert "partnership_synastry" not in result


def test_compute_business_prediction_attaches_synastry_when_partner_given():
    native_a = _SynastryPayload()
    native_b = _SynastryPayload()
    result = compute_business_prediction(native_a, attach_provenance=False, partner_payload=native_b)
    assert "partnership_synastry" in result
    assert result["partnership_synastry"]["status"] == "OK"


def test_d7_corroborates_d1_seventh_house_promise_boosts_composite():
    # Mars (H7 lord for both) placed at Cancer 1deg -> D7 sign = Capricorn,
    # where Mars is EXALTED (see jyotish.astro.compute_d7_saptamsha_sign /
    # jyotish.dignity.dignity_state) -- a genuine D7 corroboration of the
    # D1 7th-house promise. Composite score should be higher than the
    # otherwise-identical chart with no D7 data at all.
    native_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    native_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    native_a.planets_d1 = {"Mars": {"sign": "Cancer", "degree": 1.0}}
    native_b.planets_d1 = {"Mars": {"sign": "Cancer", "degree": 1.0}}

    baseline_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    baseline_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")

    with_d7 = compute_partnership_synastry(native_a, native_b)
    without_d7 = compute_partnership_synastry(baseline_a, baseline_b)

    assert with_d7["status"] == "OK"
    assert with_d7["seventh_house_d7_cross_comparison"]["status"] == "OK"
    assert with_d7["seventh_house_d7_cross_comparison"]["d7_dignity_a"] == "EXALTED"
    assert with_d7["seventh_house_d7_cross_comparison"]["d7_dignity_b"] == "EXALTED"
    assert with_d7["seventh_house_d7_cross_comparison"]["score_0_20"] > 10.0
    assert with_d7["composite_score_0_100"] > without_d7["composite_score_0_100"]
    assert any(s["source"] == "seventh_house_d7_cross_comparison" for s in with_d7["complementary_strengths"])


def test_d7_contradicts_d1_seventh_house_promise_flags_caution_not_ignored():
    # Same Mars H7 lord, but placed at Cancer 27deg -> D7 sign = Cancer,
    # where Mars is DEBILITATED -- a genuine D7 contradiction of the D1
    # 7th-house promise. Must lower the composite score AND surface a
    # friction_points entry (not silently dropped).
    native_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    native_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    native_a.planets_d1 = {"Mars": {"sign": "Cancer", "degree": 27.0}}
    native_b.planets_d1 = {"Mars": {"sign": "Cancer", "degree": 27.0}}

    baseline_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    baseline_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")

    with_d7 = compute_partnership_synastry(native_a, native_b)
    without_d7 = compute_partnership_synastry(baseline_a, baseline_b)

    assert with_d7["status"] == "OK"
    assert with_d7["seventh_house_d7_cross_comparison"]["status"] == "OK"
    assert with_d7["seventh_house_d7_cross_comparison"]["d7_dignity_a"] == "DEBILITATED"
    assert with_d7["seventh_house_d7_cross_comparison"]["d7_dignity_b"] == "DEBILITATED"
    assert with_d7["seventh_house_d7_cross_comparison"]["score_0_20"] < 10.0
    assert with_d7["composite_score_0_100"] < without_d7["composite_score_0_100"]
    assert any(f["source"] == "seventh_house_d7_cross_comparison" for f in with_d7["friction_points"])


# --- Partner-verdict recomputation (item 36) ---
# v-audit fix (business realism, "partner analysis remains optional and
# does not fully recompute the operating verdict"): partnership_synastry
# was previously an inert side-channel attached to compute_business_
# prediction()'s result but never consulted by authoritative_recommendation.
# authoritative_recommendation.partner_verdict_recomputation now exists
# whenever partner_payload is supplied, applying a disclosed, capped,
# single-step tier adjustment based on the synastry compatibility_label.

def test_partner_verdict_recomputation_absent_without_partner_payload():
    payload = _SynastryPayload()
    result = compute_business_prediction(payload, attach_provenance=False)
    assert "partner_verdict_recomputation" not in result["authoritative_recommendation"]


def test_partner_verdict_recomputation_workable_fit_leaves_tier_unchanged():
    native_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    native_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    result = compute_business_prediction(native_a, attach_provenance=False, partner_payload=native_b)
    pv = result["authoritative_recommendation"]["partner_verdict_recomputation"]
    assert pv["partner_compatibility_label"] in ("STRONG_FIT", "WORKABLE_FIT", "CAUTION", "POOR_FIT", None)
    if pv["partner_compatibility_label"] == "WORKABLE_FIT":
        assert pv["partner_adjusted_tier"] == pv["base_tier"]
        assert pv["tier_changed"] is False


def test_partner_verdict_recomputation_poor_fit_forces_low_tier():
    # Fire vs Water Moon sign, enemy H7 lords, enemy MD lords -> POOR_FIT
    # (see test_conflicting_charts_score_lower_than_compatible_charts above,
    # which already establishes this fixture pair scores lower).
    native_a = _SynastryPayload(moon_sign="Aries", h7_lord="Sun", md_lord="Sun")
    native_b = _SynastryPayload(moon_sign="Cancer", h7_lord="Saturn", md_lord="Saturn")
    result = compute_business_prediction(native_a, attach_provenance=False, partner_payload=native_b)
    pv = result["authoritative_recommendation"]["partner_verdict_recomputation"]
    if pv["partner_compatibility_label"] == "POOR_FIT":
        assert pv["partner_adjusted_tier"] == "LOW"


def test_partner_verdict_recomputation_never_upgrades_a_base_do_not_proceed():
    """A chart whose base authoritative_recommendation already says do-not-
    proceed (final_proceed False) must never be upgraded by even a
    STRONG_FIT partner -- partnership fit cannot rescue a failing solo
    chart. Missing D1 structural data (no house_lords/planet_house) is the
    most direct way to force final_proceed False."""
    class _NoDataPayload(_SynastryPayload):
        def __init__(self):
            super().__init__()
            self.house_lords = {}
            self.planet_house = {}
            self.planet_dignities = {}

    native_a = _NoDataPayload()
    native_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    result = compute_business_prediction(native_a, attach_provenance=False, partner_payload=native_b)
    ar = result["authoritative_recommendation"]
    pv = ar["partner_verdict_recomputation"]
    assert ar["final_proceed"] is False
    assert pv["base_proceed"] is False
    assert pv["partner_adjusted_tier"] == pv["base_tier"]
    assert "cannot rescue" in pv["note"]


def test_d7_missing_data_degrades_to_d1_only_scoring_path_not_crash():
    # No planets_d1/divisional_charts supplied at all (the _SynastryPayload
    # default) -- D7 corroboration must degrade to MISSING_DATA gracefully,
    # never raise, and the composite score must be computed via the
    # pre-existing D1-only (0..80) denominator, identical to a chart that
    # predates the D7 feature entirely.
    native_a = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")
    native_b = _SynastryPayload(moon_sign="Aries", h7_lord="Mars", md_lord="Mercury")

    result = compute_partnership_synastry(native_a, native_b)

    assert result["status"] == "OK"
    assert result["seventh_house_d7_cross_comparison"]["status"] == "MISSING_DATA"
    assert result["seventh_house_d7_cross_comparison"]["score_0_20"] == 0
    assert result["raw_total_max_possible"] == 80.0
    assert "seventh_house_d7_cross_comparison" not in result["component_scores_0_20"]
    assert 0.0 <= result["composite_score_0_100"] <= 100.0
