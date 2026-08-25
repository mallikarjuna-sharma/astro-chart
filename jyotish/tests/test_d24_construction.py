"""JyotishAI — D24 (Chaturvimshamsha/Siddhamsha) construction correctness tests.

Audit-2026-07 follow-up (gaps 4/5): D24 was previously read verbatim from an
upstream JSON with no in-repo way to verify the classical odd/even
sign-counting rule -- exactly the same blind-trust gap D10 had before
test_d10_construction.py closed it. These tests pin `compute_d24_sign` /
`compute_d24_chart` (astro.py) against the BPHS majority-convention boundary
cases (odd sign -> count from Leo, even sign -> count from Cancer, 1.25 deg
per segment) so a future change can't silently break the varga math, and so
Stream_Determination's D24_CONSTRUCTION_MISMATCH check has a validated
formula to compare upstream data against -- not an unverified guess.

Run with:
    pytest jyotish/tests/test_d24_construction.py -v
"""
import pytest

from jyotish.astro import compute_d24_sign, compute_d24_chart


class TestOddSignCounting:
    """Odd signs (Aries, Gemini, Leo, Libra, Sagittarius, Aquarius): the 24
    divisions count starting FROM LEO."""

    def test_aries_segment_1_starts_at_leo(self):
        # 0.0-1.25 deg Aries -> segment 1 -> Leo (odd sign, starts from Leo)
        assert compute_d24_sign("Aries", 0.0) == "Leo"
        assert compute_d24_sign("Aries", 1.0) == "Leo"

    def test_aries_segment_2_is_virgo(self):
        assert compute_d24_sign("Aries", 1.25) == "Virgo"
        assert compute_d24_sign("Aries", 2.4) == "Virgo"

    def test_leo_segment_1_starts_at_leo(self):
        # Leo is itself odd -> also starts from Leo
        assert compute_d24_sign("Leo", 0.0) == "Leo"

    def test_libra_segment_1_starts_at_leo(self):
        assert compute_d24_sign("Libra", 0.5) == "Leo"

    def test_odd_sign_segment_24_wraps_to_cancer(self):
        # segment 24 (28.75-30.0 deg) is 23 signs forward from Leo ->
        # ((5-1+23)%12)+1 = (27%12)+1 = 3+1 = 4 -> Cancer
        assert compute_d24_sign("Aries", 29.5) == "Cancer"


class TestEvenSignCounting:
    """Even signs (Taurus, Cancer, Virgo, Scorpio, Capricorn, Pisces): the 24
    divisions count starting FROM CANCER."""

    def test_taurus_segment_1_starts_at_cancer(self):
        assert compute_d24_sign("Taurus", 0.0) == "Cancer"
        assert compute_d24_sign("Taurus", 1.0) == "Cancer"

    def test_taurus_segment_2_is_leo(self):
        assert compute_d24_sign("Taurus", 1.25) == "Leo"

    def test_cancer_segment_1_starts_at_cancer(self):
        # Cancer is itself even -> also starts from Cancer
        assert compute_d24_sign("Cancer", 0.5) == "Cancer"

    def test_pisces_segment_1_starts_at_cancer(self):
        assert compute_d24_sign("Pisces", 0.2) == "Cancer"

    def test_even_sign_segment_24_wraps_to_gemini(self):
        # segment 24 is 23 signs forward from Cancer ->
        # ((4-1+23)%12)+1 = (26%12)+1 = 2+1 = 3 -> Gemini
        assert compute_d24_sign("Taurus", 29.5) == "Gemini"


class TestDegreeBoundaries:
    """Exact 1.25-degree segment boundaries are the classic off-by-one source."""

    def test_exact_1_25_degree_boundary_rolls_to_next_segment(self):
        seg1 = compute_d24_sign("Gemini", 1.249999)
        seg2 = compute_d24_sign("Gemini", 1.25)
        assert seg1 != seg2

    def test_degree_zero_is_segment_1(self):
        assert compute_d24_sign("Virgo", 0.0) == compute_d24_sign("Virgo", 0.5)

    def test_degree_near_30_does_not_crash_or_overflow(self):
        result = compute_d24_sign("Scorpio", 29.9999)
        assert result in [
            "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
            "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
        ]

    def test_degree_exactly_30_does_not_crash(self):
        result = compute_d24_sign("Cancer", 30.0)
        assert result != ""

    def test_unknown_sign_returns_empty_not_crash(self):
        assert compute_d24_sign("NotASign", 10.0) == ""


class TestChartConstruction:
    def test_compute_d24_chart_builds_all_planets_with_degree(self):
        planets_d1 = {
            "Sun":     {"sign": "Aries", "degree": 15.0},
            "Moon":    {"sign": "Taurus", "degree": 2.0},
            "Mercury": {"sign": "Aries", "degree": 20.0},  # no crash on dup sign
        }
        chart = compute_d24_chart(planets_d1)
        assert chart["Sun"] == compute_d24_sign("Aries", 15.0)
        assert chart["Moon"] == compute_d24_sign("Taurus", 2.0)
        assert "Mercury" in chart
        # Flat dict, no "Lagna" key -- D24 lagna cannot be independently
        # re-derived (no lagna_degree field on NatalPayloadV2).
        assert "Lagna" not in chart

    def test_planet_missing_degree_is_skipped_not_crashed(self):
        planets_d1 = {
            "Sun":  {"sign": "Aries", "degree": 15.0},
            "Rahu": {"sign": "Cancer"},  # no degree -- should be skipped
        }
        chart = compute_d24_chart(planets_d1)
        assert "Sun" in chart
        assert "Rahu" not in chart

    def test_empty_input_produces_empty_chart(self):
        assert compute_d24_chart({}) == {}


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
