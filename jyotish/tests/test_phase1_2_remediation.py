"""Phase-1/2 remediation (2026-08 gap-audit) scoring tests.

Covers the new/changed field-determination scorers introduced while wiring
D24 (Siddhamsha), D9 (Navamsha), and D60 (Shashtiamsha) into the education
field-method bundle as real (or bounded-adjustment) voting methods, and the
H4/vidya-karaka additions to Parashara/K.N. Rao/Jaimini.

Run with:
    pytest Field_Determination/field_methods/../../jyotish/tests/test_phase1_2_remediation.py -v

(placed under jyotish/tests to match this repo's existing test discovery
convention -- see test_academic_tier_recommendation.py, test_d24_construction.py.)
"""
from types import SimpleNamespace

import pytest

from Field_Determination.field_methods.siddhamsha import score_siddhamsha
from Field_Determination.field_methods.navamsha import score_navamsha_adjustment
from Field_Determination.field_methods.shashtiamsha import score_d60_vote


def _mock_payload(**overrides):
    base = dict(
        divisional_charts={
            "D24_siddhamsam": {
                "Sun": "Leo", "Moon": "Cancer", "Mercury": "Virgo",
                "Jupiter": "Sagittarius", "Venus": "Libra", "Mars": "Aries",
                "Saturn": "Capricorn",
            },
        },
        d24_lagna_sign="Virgo",  # matches edu_align.py's attribute path
        d24_planet_dignities={
            "Mercury": "OWN", "Jupiter": "OWN", "Venus": "OWN", "Sun": "FRIEND",
        },
        d9_planet_dignities={"Mercury": "EXALTED", "Jupiter": "OWN"},
        planets_d1={
            "Mercury": {"sign": "Virgo", "degree": 10.0},
            "Jupiter": {"sign": "Sagittarius", "degree": 5.0},
        },
        h10_lord="Mercury",
        atmakaraka="Jupiter",
        amatyakaraka="Mercury",
        combust_planets=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestSiddhamshaD24:
    def test_returns_independent_vote_capable_contract(self):
        """Phase-1: the new scorer must return the same shape as the other
        six method scorers (method_result contract), not the old
        independent_vote:False stub."""
        payload = _mock_payload()
        result = score_siddhamsha(payload, "engineering", {"Mercury": 0.8, "Jupiter": 0.6}, "computer_science", {})
        assert "score" in result and "normalized_score" in result
        assert "raw_signed_score" in result
        assert "independent_vote" not in result  # old stub key must be gone
        assert result["score"] >= 0

    def test_missing_d24_chart_returns_zero_not_crash(self):
        payload = _mock_payload(divisional_charts={}, d24_lagna_sign="")
        result = score_siddhamsha(payload, "engineering", {"Mercury": 0.8}, "computer_science", {})
        assert result["score"] == 0.0

    def test_falls_back_to_d24_lagna_sign_attribute(self):
        """Phase-6 fix: compute_d24_chart's flat dict has no 'Lagna' key on
        real charts -- must fall back to payload.d24_lagna_sign."""
        payload = _mock_payload()
        assert "Lagna" not in payload.divisional_charts["D24_siddhamsam"]
        result = score_siddhamsha(payload, "engineering", {"Mercury": 0.8, "Jupiter": 0.6}, "computer_science", {})
        assert result["score"] > 0  # would be 0 if the Lagna fallback failed

    def test_strong_vidya_karaka_dignity_scores_higher_than_weak(self):
        strong = _mock_payload(d24_planet_dignities={"Mercury": "EXALTED", "Jupiter": "OWN", "Venus": "OWN"})
        weak = _mock_payload(d24_planet_dignities={"Mercury": "DEBILITATED", "Jupiter": "ENEMY", "Venus": "ENEMY"})
        aff = {"Mercury": 0.8, "Jupiter": 0.6, "Venus": 0.3}
        r_strong = score_siddhamsha(strong, "engineering", aff, "computer_science", {})
        r_weak = score_siddhamsha(weak, "engineering", aff, "computer_science", {})
        assert r_strong["score"] > r_weak["score"]


class TestNavamshaD9Adjustment:
    def test_multiplier_bounded(self):
        payload = _mock_payload()
        result = score_navamsha_adjustment(payload, "engineering", {"Mercury": 0.9, "Jupiter": 0.5}, "computer_science", {})
        # §6 remediation (2026-08): bounds widened from 0.92-1.08 to 0.85-1.15
        # to restore the spec's guarantee that a D1 signal collapsing in D9
        # can drop meaningfully (see Field_Determination/field_methods/
        # navamsha.py's _D9_MULT_MIN/_D9_MULT_MAX).
        assert 0.85 <= result["multiplier"] <= 1.15

    def test_missing_data_returns_neutral_multiplier(self):
        payload = _mock_payload(d9_planet_dignities={})
        result = score_navamsha_adjustment(payload, "engineering", {"Mercury": 0.9}, "computer_science", {})
        assert result["multiplier"] == 1.0
        assert result["status"] == "MISSING"


class TestShashtiamshaD60Vote:
    def test_returns_native_0_100_score(self):
        payload = _mock_payload(planets_d1={
            "Mercury": {"sign": "Virgo", "degree": 10.0},
        })
        result = score_d60_vote(payload, "engineering", {"Mercury": 0.8}, "computer_science", {})
        assert 0.0 <= result["score"] <= 100.0
        assert result["normalized_score"] == result["score"]

    def test_no_candidates_returns_neutral_50(self):
        payload = _mock_payload(planets_d1={}, h10_lord="", atmakaraka="", amatyakaraka="")
        result = score_d60_vote(payload, "engineering", {}, "computer_science", {})
        assert result["score"] == 50.0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
