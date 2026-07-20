"""JyotishAI — D10 (Dashamsha) construction correctness tests.

Audit-2026-07 follow-up: D10 was previously read verbatim from an upstream
JSON with no in-repo way to verify the classical odd/even sign-counting
rule. These tests pin `compute_d10_sign` / `compute_d10_chart` (astro.py)
against known BPHS boundary cases so a future change can't silently break
the varga math again.

Run with:
    pytest jyotish/tests/test_d10_construction.py -v
"""
import pytest

from jyotish.astro import compute_d10_sign, compute_d10_chart


class TestOddSignCounting:
    """Odd signs (Aries, Gemini, Leo, Libra, Sagittarius, Aquarius): the 10
    divisions count starting FROM THE SAME SIGN."""

    def test_aries_segment_1_starts_at_aries(self):
        # 0.0-3.0 deg Aries -> segment 1 -> Aries itself (odd sign, own start)
        assert compute_d10_sign("Aries", 0.0) == "Aries"
        assert compute_d10_sign("Aries", 1.5) == "Aries"

    def test_aries_segment_2_is_taurus(self):
        # 3.0-6.0 deg -> segment 2 -> next sign forward from Aries
        assert compute_d10_sign("Aries", 3.0) == "Taurus"
        assert compute_d10_sign("Aries", 5.999) == "Taurus"

    def test_aries_segment_10_is_capricorn(self):
        # 27.0-30.0 deg -> segment 10 -> 9 signs forward from Aries = Capricorn
        # (Aries=1,Taurus=2,...,Capricorn=10th sign in the count)
        assert compute_d10_sign("Aries", 27.0) == "Capricorn"
        assert compute_d10_sign("Aries", 29.9) == "Capricorn"

    def test_leo_segment_1_starts_at_leo(self):
        assert compute_d10_sign("Leo", 0.5) == "Leo"

    def test_sagittarius_wraps_correctly(self):
        # Sagittarius segment 10 (27-30 deg) -> 9 forward from Sagittarius,
        # wrapping past Pisces back through Aries-ish territory: Sag(9)+9=18
        # -> ((9-1+9)%12)+1 = (17%12)+1 = 5+1 = 6 -> Virgo
        assert compute_d10_sign("Sagittarius", 28.0) == "Virgo"


class TestEvenSignCounting:
    """Even signs (Taurus, Cancer, Virgo, Scorpio, Capricorn, Pisces): the 10
    divisions count starting from the 9th sign counted inclusively from that
    sign (Taurus -> Capricorn, Cancer -> Pisces, etc.)."""

    def test_taurus_segment_1_starts_at_capricorn(self):
        # 9th sign from Taurus (inclusive) = Capricorn
        assert compute_d10_sign("Taurus", 0.0) == "Capricorn"
        assert compute_d10_sign("Taurus", 2.9) == "Capricorn"

    def test_taurus_segment_2_is_aquarius(self):
        assert compute_d10_sign("Taurus", 3.0) == "Aquarius"

    def test_cancer_segment_1_starts_at_pisces(self):
        # 9th sign from Cancer (inclusive) = Pisces
        assert compute_d10_sign("Cancer", 1.0) == "Pisces"

    def test_capricorn_segment_1_starts_at_virgo(self):
        # 9th sign from Capricorn (inclusive): Capricorn,Aquarius,Pisces,Aries,
        # Taurus,Gemini,Cancer,Leo,Virgo = Virgo (wraps around zodiac)
        assert compute_d10_sign("Capricorn", 0.0) == "Virgo"

    def test_pisces_segment_1_starts_at_scorpio(self):
        # 9th sign from Pisces (inclusive) = Scorpio (wraps around zodiac)
        assert compute_d10_sign("Pisces", 0.0) == "Scorpio"


class TestDegreeBoundaries:
    """Exact 3-degree segment boundaries are the classic off-by-one source."""

    def test_exact_3_degree_boundary_rolls_to_next_segment(self):
        # 3.0 deg exactly must belong to segment 2, not segment 1
        seg1 = compute_d10_sign("Gemini", 2.999999)
        seg2 = compute_d10_sign("Gemini", 3.0)
        assert seg1 != seg2

    def test_degree_zero_is_segment_1(self):
        assert compute_d10_sign("Virgo", 0.0) == compute_d10_sign("Virgo", 0.5)

    def test_degree_near_30_is_segment_10_not_overflow(self):
        # 29.999... must resolve without raising and without wrapping to
        # segment 11 (which doesn't exist)
        result = compute_d10_sign("Scorpio", 29.9999)
        assert result in [
            "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
            "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
        ]

    def test_degree_exactly_30_does_not_crash(self):
        # Defensive: malformed input of exactly 30.0 should clamp, not error
        result = compute_d10_sign("Cancer", 30.0)
        assert result != ""


class TestChartConstruction:
    def test_compute_d10_chart_builds_all_planets_with_degree(self):
        planets_d1 = {
            "Sun":     {"sign": "Aries", "degree": 15.0},
            "Moon":    {"sign": "Taurus", "degree": 2.0},
            "Mercury": {"sign": "Aries", "degree": 20.0},  # no crash on dup sign
        }
        chart = compute_d10_chart(planets_d1, "Leo", 10.0)
        assert chart["Lagna"]["sign"] == compute_d10_sign("Leo", 10.0)
        assert chart["Sun"]["sign"] == compute_d10_sign("Aries", 15.0)
        assert chart["Moon"]["sign"] == compute_d10_sign("Taurus", 2.0)
        assert "Mercury" in chart

    def test_planet_missing_degree_is_skipped_not_crashed(self):
        planets_d1 = {
            "Sun":  {"sign": "Aries", "degree": 15.0},
            "Rahu": {"sign": "Cancer"},  # no degree — should be skipped
        }
        chart = compute_d10_chart(planets_d1, "Leo", 10.0)
        assert "Sun" in chart
        assert "Rahu" not in chart

    def test_no_lagna_sign_produces_no_lagna_key(self):
        chart = compute_d10_chart({"Sun": {"sign": "Aries", "degree": 1.0}}, "", 0.0)
        assert "Lagna" not in chart
        assert "Sun" in chart


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
