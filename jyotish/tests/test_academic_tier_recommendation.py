"""JyotishAI — EduAlign E-4 (G17) sanity tests.

Ontology audit follow-up (2026-07-04, G17): compute_academic_tier_
recommendation() is a new, standalone D24-driven UG/PG/PhD advisory signal.
These tests pin its output contract (keys, ranges, monotonic response to a
strengthened D24 signal) and its graceful-degradation behaviour when D24
data is missing, so a future refactor can't silently break the schema that
engine.py depends on.

Run with:
    pytest jyotish/tests/test_academic_tier_recommendation.py -v
"""
from types import SimpleNamespace

import pytest

from jyotish.edu_align import compute_academic_tier_recommendation


def _make_payload(**overrides):
    base = dict(
        d24_lagna_sign="Virgo",
        d24_house_lords={"1": "Mercury", "9": "Saturn"},
        d24_planet_dignities={},
        eff_strengths={},
        atmakaraka="",
        divisional_charts={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestOutputContract:
    def test_returns_expected_keys(self):
        result = compute_academic_tier_recommendation(_make_payload())
        for key in (
            "ug_score", "pg_score", "phd_score", "recommended_tier",
            "confidence", "interpretation", "signals", "d24_available",
        ):
            assert key in result

    def test_scores_are_bounded_0_1(self):
        result = compute_academic_tier_recommendation(_make_payload(
            d24_planet_dignities={"Mercury": "EXALTED", "Jupiter": "EXALTED",
                                   "Saturn": "EXALTED", "Ketu": "EXALTED"},
            atmakaraka="Sun",
            divisional_charts={"D24_siddhamsam": {"Lagna": "Virgo", "Sun": "Sagittarius"}},
        ))
        for key in ("ug_score", "pg_score", "phd_score"):
            assert 0.0 <= result[key] <= 1.0

    def test_recommended_tier_is_one_of_three(self):
        result = compute_academic_tier_recommendation(_make_payload())
        assert result["recommended_tier"] in ("UG", "PG", "PhD / Research")

    def test_d24_available_false_without_lagna(self):
        result = compute_academic_tier_recommendation(_make_payload(
            d24_lagna_sign="", d24_house_lords={},
        ))
        assert result["d24_available"] is False
        # discounted, but still well-formed and bounded
        for key in ("ug_score", "pg_score", "phd_score"):
            assert 0.0 <= result[key] <= 1.0


class TestSignalDirection:
    def test_ak_in_d24_house9_boosts_phd_score(self):
        without_ak = compute_academic_tier_recommendation(_make_payload())
        with_ak = compute_academic_tier_recommendation(_make_payload(
            atmakaraka="Sun",
            # Virgo lagna in D24; 9th from Virgo is Gemini -> AK Sun placed in Gemini
            divisional_charts={"D24_siddhamsam": {"Lagna": "Virgo", "Sun": "Gemini"}},
        ))
        assert with_ak["phd_score"] > without_ak["phd_score"]
        assert with_ak["signals"]["ak_in_d24_5_9_10"] is True

    def test_exalted_saturn_and_ketu_boost_phd_score(self):
        baseline = compute_academic_tier_recommendation(_make_payload())
        boosted = compute_academic_tier_recommendation(_make_payload(
            d24_planet_dignities={"Saturn": "EXALTED", "Ketu": "EXALTED"},
        ))
        assert boosted["phd_score"] > baseline["phd_score"]

    def test_exalted_jupiter_boosts_pg_score(self):
        baseline = compute_academic_tier_recommendation(_make_payload())
        boosted = compute_academic_tier_recommendation(_make_payload(
            d24_planet_dignities={"Jupiter": "EXALTED"},
        ))
        assert boosted["pg_score"] > baseline["pg_score"]

    def test_debilitated_d24_lagna_lord_lowers_ug_score(self):
        baseline = compute_academic_tier_recommendation(_make_payload())
        weakened = compute_academic_tier_recommendation(_make_payload(
            d24_planet_dignities={"Mercury": "DEBILITATED"},
        ))
        assert weakened["ug_score"] < baseline["ug_score"]


class TestDoesNotTouchOtherState:
    def test_does_not_mutate_input_payload(self):
        payload = _make_payload()
        before = dict(vars(payload))
        compute_academic_tier_recommendation(payload)
        assert vars(payload) == before
