"""JyotishAI — Jaimini Chara Dasha (Standard/Parashara-compatible convention)
construction tests.

v46 audit fix (user-directed: "Standard Jaimini (Parashara-compatible)"):
pins compute_chara_dasha_sequence()/compute_chara_dasha_calendar() (astro.py)
against the disclosed rule -- period length by count-to-own-lord's-sign
(odd sign forward, even sign backward, a raw count of 1 treated as 12),
sequence direction by Lagna sign parity (odd Lagna -> forward zodiacal
order, even Lagna -> reverse).

Run with:
    pytest jyotish/tests/test_chara_dasha.py -v
"""
from datetime import date

from jyotish.astro import (
    _chara_dasha_sign_period_years,
    compute_chara_dasha_sequence,
    compute_chara_dasha_calendar,
    compute_chara_antardasha_sequence,
)


def _planets(**sign_by_planet):
    return {planet: {"sign": sign} for planet, sign in sign_by_planet.items()}


class TestPeriodLength:
    def test_lord_in_own_sign_gives_12_years(self):
        # Aries' lord is Mars; Mars sitting in Aries itself -> count=1 -> 12.
        assert _chara_dasha_sign_period_years("Aries", _planets(Mars="Aries")) == 12

    def test_odd_sign_counts_forward(self):
        # Aries (odd) -> Mars in Cancer (4th sign forward from Aries) -> count=4.
        assert _chara_dasha_sign_period_years("Aries", _planets(Mars="Cancer")) == 4

    def test_even_sign_counts_backward(self):
        # Taurus (even) lord Venus; Venus in Aries is 1 sign backward from
        # Taurus -> count=2 (Taurus, Aries inclusive).
        assert _chara_dasha_sign_period_years("Taurus", _planets(Venus="Aries")) == 2

    def test_unresolvable_lord_placement_returns_zero(self):
        assert _chara_dasha_sign_period_years("Aries", {}) == 0

    def test_unknown_sign_returns_zero(self):
        assert _chara_dasha_sign_period_years("NotASign", _planets(Mars="Aries")) == 0


class TestSequenceDirection:
    def test_odd_lagna_proceeds_forward(self):
        planets = _planets(
            Mars="Aries", Venus="Aries", Mercury="Aries", Moon="Aries",
            Sun="Aries", Jupiter="Aries", Saturn="Aries",
        )
        seq = compute_chara_dasha_sequence("Aries", planets)
        signs = [e["sign"] for e in seq]
        assert signs[:4] == ["Aries", "Taurus", "Gemini", "Cancer"]

    def test_even_lagna_proceeds_backward(self):
        planets = _planets(
            Mars="Aries", Venus="Aries", Mercury="Aries", Moon="Aries",
            Sun="Aries", Jupiter="Aries", Saturn="Aries",
        )
        seq = compute_chara_dasha_sequence("Taurus", planets)
        signs = [e["sign"] for e in seq]
        assert signs[:4] == ["Taurus", "Aries", "Pisces", "Aquarius"]

    def test_sequence_has_12_entries(self):
        planets = _planets(Mars="Aries")
        seq = compute_chara_dasha_sequence("Aries", planets)
        assert len(seq) == 12
        assert [e["sequence_index"] for e in seq] == list(range(12))

    def test_unresolvable_chart_returns_empty(self):
        assert compute_chara_dasha_sequence("Aries", {}) == []

    def test_unknown_lagna_returns_empty(self):
        assert compute_chara_dasha_sequence("NotASign", _planets(Mars="Aries")) == []


class TestCalendar:
    def test_calendar_dates_accumulate_from_dob(self):
        planets = _planets(Mars="Aries")  # every sign's lord-lookup will
        # mostly fail except Aries/Scorpio (Mars-owned) -- fine, we only
        # check date arithmetic on entries that DO resolve.
        cal = compute_chara_dasha_calendar("Aries", planets, date(2000, 1, 1))
        assert cal, "expected a non-empty calendar for Aries lagna with Mars data"
        first = cal[0]
        assert first["sign"] == "Aries"
        assert first["start"] == "2000-01-01"
        # Aries' own lord Mars sits in Aries -> 12-year period -> 4320 days.
        assert first["years"] == 12
        expected_end = date(2000, 1, 1)
        from datetime import timedelta
        expected_end = expected_end + timedelta(days=12 * 360)
        assert first["end"] == expected_end.isoformat()
        # Second entry's start must equal first entry's end (contiguous).
        assert cal[1]["start"] == first["end"]

    def test_empty_sequence_gives_empty_calendar(self):
        assert compute_chara_dasha_calendar("Aries", {}, date(2000, 1, 1)) == []

    def test_calendar_entries_carry_antardashas(self):
        planets = _planets(Mars="Aries")
        cal = compute_chara_dasha_calendar("Aries", planets, date(2000, 1, 1))
        assert cal[0]["antardashas"], "expected non-empty antardasha list on the first MD entry"
        assert len(cal[0]["antardashas"]) == 12


class TestAntardashaSubdivision:
    def test_twelve_antardashas_sum_to_mahadasha_years(self):
        planets = _planets(Mars="Aries")
        ad = compute_chara_antardasha_sequence("Aries", 12.0, True, planets)
        assert len(ad) == 12
        assert abs(sum(e["years"] for e in ad) - 12.0) < 1e-6

    def test_forward_direction_starts_at_mahadasha_sign(self):
        planets = _planets(Mars="Aries")
        ad = compute_chara_antardasha_sequence("Aries", 12.0, True, planets)
        assert ad[0]["sign"] == "Aries"
        assert ad[1]["sign"] == "Taurus"

    def test_backward_direction_starts_at_mahadasha_sign(self):
        planets = _planets(Mars="Aries")
        ad = compute_chara_antardasha_sequence("Taurus", 12.0, False, planets)
        assert ad[0]["sign"] == "Taurus"
        assert ad[1]["sign"] == "Aries"

    def test_own_antardasha_gets_largest_share_when_lord_in_own_sign(self):
        # Aries' own lord Mars sits in Aries -> 12-year weight (the max
        # possible), so Aries' own antardasha within an Aries Mahadasha
        # should be the single largest of the 12 shares.
        planets = _planets(Mars="Aries")
        ad = compute_chara_antardasha_sequence("Aries", 12.0, True, planets)
        own = next(e for e in ad if e["sign"] == "Aries")
        assert own["years"] == max(e["years"] for e in ad)

    def test_dates_attached_and_contiguous_when_start_date_supplied(self):
        planets = _planets(Mars="Aries")
        ad = compute_chara_antardasha_sequence("Aries", 12.0, True, planets, start_date=date(2000, 1, 1))
        assert ad[0]["start"] == "2000-01-01"
        assert ad[1]["start"] == ad[0]["end"]

    def test_no_dates_when_start_date_omitted(self):
        planets = _planets(Mars="Aries")
        ad = compute_chara_antardasha_sequence("Aries", 12.0, True, planets)
        assert "start" not in ad[0] and "end" not in ad[0]

    def test_zero_years_returns_empty(self):
        assert compute_chara_antardasha_sequence("Aries", 0.0, True, _planets(Mars="Aries")) == []

    def test_unknown_sign_returns_empty(self):
        assert compute_chara_antardasha_sequence("NotASign", 12.0, True, _planets(Mars="Aries")) == []
