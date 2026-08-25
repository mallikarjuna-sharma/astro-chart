"""JyotishAI — D4 (Chaturthamsha) construction correctness tests.

v-audit fix (business realism, item 35 -- "foreign-business analysis lacks
complete D4/location arbitration"): D4 was previously not computed
anywhere in this repo (see astro.py::compute_d4_chaturthamsha_sign's own
docstring -- Vimshopaka Bala's weight table even lists a D4 coefficient
that was explicitly never applied). Unlike D3/D7/D10/D24 (which key off
odd/even sign parity), D4's starting point depends on the sign's MODALITY
(movable/fixed/dual), so its correctness needs its own dedicated test file
rather than reusing the D10/D24 odd/even test pattern verbatim.

Run with:
    pytest jyotish/tests/test_d4_construction.py -v
"""
from jyotish.astro import compute_d4_chaturthamsha_sign, compute_d4_chaturthamsha_chart
from jyotish.constants import _SIGN_NUM

_SIGNS_IN_ORDER = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda x: x[1])]


class TestMovableSignCounting:
    """Movable/Chara signs (Aries, Cancer, Libra, Capricorn): the 4 parts
    count same-sign, 4th, 7th, 10th from itself, in that order."""

    def test_aries_segment_1_is_aries(self):
        assert compute_d4_chaturthamsha_sign("Aries", 0.0) == "Aries"
        assert compute_d4_chaturthamsha_sign("Aries", 7.4) == "Aries"

    def test_aries_segment_2_is_cancer(self):
        assert compute_d4_chaturthamsha_sign("Aries", 7.5) == "Cancer"

    def test_aries_segment_3_is_libra(self):
        assert compute_d4_chaturthamsha_sign("Aries", 15.0) == "Libra"

    def test_aries_segment_4_is_capricorn(self):
        assert compute_d4_chaturthamsha_sign("Aries", 22.5) == "Capricorn"
        assert compute_d4_chaturthamsha_sign("Aries", 29.9) == "Capricorn"


class TestFixedSignCounting:
    """Fixed/Sthira signs (Taurus, Leo, Scorpio, Aquarius): the 4 parts
    count 10th, same-sign, 4th, 7th from itself, in that order."""

    def test_taurus_segment_1_is_aquarius(self):
        # 10th sign from Taurus (counted inclusively) = Aquarius
        assert compute_d4_chaturthamsha_sign("Taurus", 0.0) == "Aquarius"

    def test_taurus_segment_2_is_taurus(self):
        assert compute_d4_chaturthamsha_sign("Taurus", 7.5) == "Taurus"

    def test_taurus_segment_3_is_leo(self):
        assert compute_d4_chaturthamsha_sign("Taurus", 15.0) == "Leo"

    def test_taurus_segment_4_is_scorpio(self):
        assert compute_d4_chaturthamsha_sign("Taurus", 22.5) == "Scorpio"


class TestDualSignCounting:
    """Dual/Dwiswabhava signs (Gemini, Virgo, Sagittarius, Pisces): the 4
    parts count 7th, 10th, same-sign, 4th from itself, in that order."""

    def test_gemini_segment_1_is_sagittarius(self):
        assert compute_d4_chaturthamsha_sign("Gemini", 0.0) == "Sagittarius"

    def test_gemini_segment_2_is_pisces(self):
        assert compute_d4_chaturthamsha_sign("Gemini", 7.5) == "Pisces"

    def test_gemini_segment_3_is_gemini(self):
        assert compute_d4_chaturthamsha_sign("Gemini", 15.0) == "Gemini"

    def test_gemini_segment_4_is_virgo(self):
        assert compute_d4_chaturthamsha_sign("Gemini", 22.5) == "Virgo"


class TestInvariants:
    """Structural invariant that must hold regardless of modality: all 4
    D4 segments for any sign must land exactly on that sign's own 4 kendra
    (1st/4th/7th/10th) positions -- only the ORDER differs by modality,
    never the SET of candidate signs."""

    def test_every_sign_maps_to_exactly_its_own_kendra_set(self):
        for sign in _SIGNS_IN_ORDER:
            idx = _SIGN_NUM[sign] - 1
            expected_kendra_set = {_SIGNS_IN_ORDER[(idx + off) % 12] for off in (0, 3, 6, 9)}
            actual = {compute_d4_chaturthamsha_sign(sign, d) for d in (0.0, 7.5, 15.0, 22.5)}
            assert actual == expected_kendra_set, (sign, actual, expected_kendra_set)

    def test_unknown_sign_returns_empty_string(self):
        assert compute_d4_chaturthamsha_sign("NotASign", 5.0) == ""

    def test_degree_out_of_range_is_clamped_not_raised(self):
        # Defensive clamping, matching compute_d10_sign/compute_d24_sign's
        # own boundary-safety convention.
        assert compute_d4_chaturthamsha_sign("Aries", -5.0) == "Aries"
        assert compute_d4_chaturthamsha_sign("Aries", 30.0) == "Capricorn"


class TestChartConstruction:
    def test_chart_builds_lagna_and_planet_entries(self):
        planets_d1 = {
            "Sun": {"sign": "Aries", "degree": 10.0},
            "Moon": {"sign": "Taurus", "degree": 20.0},
        }
        chart = compute_d4_chaturthamsha_chart(planets_d1, lagna_sign="Aries", lagna_degree=0.0)
        assert chart["Lagna"]["sign"] == "Aries"
        assert chart["Sun"]["sign"] == compute_d4_chaturthamsha_sign("Aries", 10.0)
        assert chart["Moon"]["sign"] == compute_d4_chaturthamsha_sign("Taurus", 20.0)

    def test_chart_omits_lagna_when_not_supplied(self):
        chart = compute_d4_chaturthamsha_chart({"Sun": {"sign": "Aries", "degree": 5.0}})
        assert "Lagna" not in chart
        assert "Sun" in chart

    def test_chart_skips_planets_missing_degree(self):
        chart = compute_d4_chaturthamsha_chart({"Sun": {"sign": "Aries"}})
        assert "Sun" not in chart
