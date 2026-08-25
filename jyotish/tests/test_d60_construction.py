"""JyotishAI — D60 (Shashtiamsha) construction correctness tests.

v-audit fix (user-authorized doctrinal choice, 2026-07-29): D60 was
previously blocked everywhere with D60_NOT_IMPLEMENTED_CONTESTED_CONVENTION
because no in-house construction existed and the sign-assignment rule is
genuinely more disputed across sources than D10/D24. Per an explicit user
decision to accept the citation risk of a disclosed MAJORITY convention
(odd sign starts from itself, even sign starts from the 7th sign, cycling
the 12-sign zodiac 5 times over 60 divisions of 0.5 deg each -- the same
posture already applied to compute_d24_sign()/compute_d2_hora_sign()), these
tests pin compute_d60_shashtiamsha_sign()/compute_d60_shashtiamsha_chart()
(astro.py) against that convention.

Run with:
    pytest jyotish/tests/test_d60_construction.py -v
"""
from jyotish.astro import compute_d60_shashtiamsha_sign, compute_d60_shashtiamsha_chart
from jyotish.constants import _SIGN_NUM

_SIGNS_IN_ORDER = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda x: x[1])]


class TestOddSignCounting:
    """Odd signs: the 60 divisions count starting FROM THE SAME SIGN."""

    def test_aries_segment_1_is_aries(self):
        assert compute_d60_shashtiamsha_sign("Aries", 0.0) == "Aries"
        assert compute_d60_shashtiamsha_sign("Aries", 0.49) == "Aries"

    def test_aries_segment_2_is_taurus(self):
        assert compute_d60_shashtiamsha_sign("Aries", 0.5) == "Taurus"

    def test_aries_second_cycle_returns_to_aries(self):
        # Segment 13 (12 signs later, 2nd cycle) -> back to Aries.
        assert compute_d60_shashtiamsha_sign("Aries", 6.0) == "Aries"

    def test_aries_last_segment(self):
        # Segment 60 (index 59): offset 59 % 12 = 11 -> Pisces (12th sign
        # from Aries).
        assert compute_d60_shashtiamsha_sign("Aries", 29.9) == "Pisces"


class TestEvenSignCounting:
    """Even signs: the 60 divisions count starting from the 7th sign
    (the opposite sign), cycling the same way."""

    def test_taurus_segment_1_is_scorpio(self):
        # 7th sign from Taurus (inclusive) = Scorpio.
        assert compute_d60_shashtiamsha_sign("Taurus", 0.0) == "Scorpio"

    def test_taurus_segment_2_is_sagittarius(self):
        assert compute_d60_shashtiamsha_sign("Taurus", 0.5) == "Sagittarius"

    def test_taurus_second_cycle_returns_to_scorpio(self):
        assert compute_d60_shashtiamsha_sign("Taurus", 6.0) == "Scorpio"


class TestInvariants:
    def test_every_sign_cycles_through_all_12_signs_exactly_5_times(self):
        """Structural invariant: regardless of modality/parity, the 60
        segments for any sign must visit each of the 12 signs exactly 5
        times (60/12), never more, never less -- proves the modulo-12
        arithmetic wraps correctly across the full 0-30 deg range."""
        from collections import Counter
        for sign in _SIGNS_IN_ORDER:
            counts = Counter(
                compute_d60_shashtiamsha_sign(sign, seg * 0.5 + 0.01)
                for seg in range(60)
            )
            assert set(counts.values()) == {5}, (sign, counts)

    def test_unknown_sign_returns_empty_string(self):
        assert compute_d60_shashtiamsha_sign("NotASign", 5.0) == ""

    def test_degree_out_of_range_is_clamped_not_raised(self):
        assert compute_d60_shashtiamsha_sign("Aries", -5.0) == "Aries"
        assert compute_d60_shashtiamsha_sign("Aries", 30.0) == "Pisces"


class TestChartConstruction:
    def test_chart_builds_lagna_and_planet_entries(self):
        planets_d1 = {
            "Sun": {"sign": "Aries", "degree": 10.0},
            "Moon": {"sign": "Taurus", "degree": 20.0},
        }
        chart = compute_d60_shashtiamsha_chart(planets_d1, lagna_sign="Aries", lagna_degree=0.0)
        assert chart["Lagna"]["sign"] == "Aries"
        assert chart["Sun"]["sign"] == compute_d60_shashtiamsha_sign("Aries", 10.0)
        assert chart["Moon"]["sign"] == compute_d60_shashtiamsha_sign("Taurus", 20.0)

    def test_chart_omits_lagna_when_not_supplied(self):
        chart = compute_d60_shashtiamsha_chart({"Sun": {"sign": "Aries", "degree": 5.0}})
        assert "Lagna" not in chart
        assert "Sun" in chart

    def test_chart_skips_planets_missing_degree(self):
        chart = compute_d60_shashtiamsha_chart({"Sun": {"sign": "Aries"}})
        assert "Sun" not in chart
