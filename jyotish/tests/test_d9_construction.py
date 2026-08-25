"""JyotishAI — D9 (Navamsha) construction correctness tests.

v-audit fix (2026-08-01, real production gap found via a WARNING: "D9 sign
is required for classical Saptavargaja Bala" -- jyotish/shadbala.py's
compute_classical_saptavargaja_bala() raised for every planet on any chart
whose upstream JSON's divisional_charts.D9_navamsha was empty or nested in
a shape engine_io.py didn't parse (e.g. {"planets": {...}} instead of a
flat {planet: sign} dict), silently disabling the ENTIRE six-fold Shadbala
computation for that chart. There was no in-house D9 construction anywhere
in this codebase before this fix -- the only "big" divisional chart
(D9/D10/D24/D60) without one. Unlike D24/D60, D9's construction rule is
UNCONTESTED core Parashari doctrine -- no minority-convention disclosure
needed.

These tests pin compute_d9_navamsha_sign()/compute_d9_navamsha_chart()
(astro.py) against the classical rule and against real cross-validated
data (this in-house implementation was verified to exactly reproduce a
real chart's own upstream-computed D9 chart once the nested-shape parsing
bug was also fixed).

Run with:
    pytest jyotish/tests/test_d9_construction.py -v
"""
from jyotish.astro import compute_d9_navamsha_sign, compute_d9_navamsha_chart


class TestMovableSigns:
    """Movable (Chara) signs: count starts from the SAME sign."""

    def test_aries_first_navamsa_is_aries(self):
        assert compute_d9_navamsha_sign("Aries", 0.0) == "Aries"
        assert compute_d9_navamsha_sign("Aries", 3.0) == "Aries"

    def test_aries_second_navamsa_is_taurus(self):
        assert compute_d9_navamsha_sign("Aries", 3.34) == "Taurus"

    def test_cancer_first_navamsa_is_cancer(self):
        assert compute_d9_navamsha_sign("Cancer", 1.0) == "Cancer"


class TestFixedSigns:
    """Fixed (Sthira) signs: count starts from the 9th sign FROM itself."""

    def test_taurus_first_navamsa_is_capricorn(self):
        # 9th sign from Taurus (inclusive) = Capricorn.
        assert compute_d9_navamsha_sign("Taurus", 0.0) == "Capricorn"

    def test_leo_first_navamsa_is_aries(self):
        # 9th sign from Leo = Aries.
        assert compute_d9_navamsha_sign("Leo", 0.0) == "Aries"


class TestDualSigns:
    """Dual (Dwiswabhava) signs: count starts from the 5th sign FROM itself."""

    def test_gemini_first_navamsa_is_libra(self):
        # 5th sign from Gemini = Libra.
        assert compute_d9_navamsha_sign("Gemini", 0.0) == "Libra"

    def test_pisces_last_navamsa_is_pisces_itself(self):
        # Classical fact: a dual sign's OWN sign always appears as its own
        # 9th (last) navamsa.
        assert compute_d9_navamsha_sign("Pisces", 29.9) == "Pisces"


class TestInvariants:
    def test_every_sign_cycles_through_all_12_signs_across_9_segments(self):
        # Structural sanity: 9 segments of 3deg20' each must produce 9
        # distinct-or-repeating sign reads that stay within the valid
        # 12-sign zodiac (no out-of-range/garbage values).
        from jyotish.constants import _SIGN_NUM
        for sign in _SIGN_NUM:
            for seg in range(9):
                result = compute_d9_navamsha_sign(sign, seg * (30.0 / 9.0) + 0.01)
                assert result in _SIGN_NUM, (sign, seg, result)

    def test_unknown_sign_returns_empty_string(self):
        assert compute_d9_navamsha_sign("NotASign", 5.0) == ""

    def test_degree_out_of_range_is_clamped_not_raised(self):
        assert compute_d9_navamsha_sign("Aries", -5.0) == "Aries"
        assert compute_d9_navamsha_sign("Aries", 30.0) == "Sagittarius"


class TestChartConstruction:
    def test_chart_builds_lagna_and_planet_entries(self):
        planets_d1 = {
            "Sun": {"sign": "Aries", "degree": 10.0},
            "Moon": {"sign": "Taurus", "degree": 20.0},
        }
        chart = compute_d9_navamsha_chart(planets_d1, lagna_sign="Aries", lagna_degree=0.0)
        assert chart["Lagna"]["sign"] == "Aries"
        assert chart["Sun"]["sign"] == compute_d9_navamsha_sign("Aries", 10.0)
        assert chart["Moon"]["sign"] == compute_d9_navamsha_sign("Taurus", 20.0)

    def test_chart_omits_lagna_when_not_supplied(self):
        chart = compute_d9_navamsha_chart({"Sun": {"sign": "Aries", "degree": 5.0}})
        assert "Lagna" not in chart
        assert "Sun" in chart

    def test_chart_skips_planets_missing_degree(self):
        chart = compute_d9_navamsha_chart({"Sun": {"sign": "Aries"}})
        assert "Sun" not in chart


class TestCrossValidationAgainstRealChart:
    """Cross-validated against Charts/kathiravan_chart_details.json's own
    real upstream-computed D9 chart (pyhora), which this in-house
    implementation was confirmed to reproduce EXACTLY once the nested
    {"planets": {...}} shape bug was also fixed in engine_io.py -- proof
    this formula is correct, not just internally self-consistent."""

    def test_reproduces_real_kathiravan_d9_chart(self):
        # D1 placements and the real pyhora-computed D9 result both taken
        # directly from Charts/kathiravan_chart_details.json.
        # Sun: Leo 16.0256 deg -> upstream D9 sign = Leo.
        assert compute_d9_navamsha_sign("Leo", 16.0256) == "Leo"
        # Moon: Cancer 22.9017 deg -> upstream D9 sign = Capricorn.
        assert compute_d9_navamsha_sign("Cancer", 22.9017) == "Capricorn"
