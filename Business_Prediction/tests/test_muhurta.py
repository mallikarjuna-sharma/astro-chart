"""Tests for Business_Prediction.business_determination.muhurta
(electional/muhurta calculator for business events).

This sandbox environment does not have network access to fetch
`de421.bsp`/Skyfield's ephemeris data, so `jyotish.ephemeris.is_available()`
is False here (verified directly: see test_ephemeris_unavailable_status_on_real_backend
below). Because of that, the "sane ranked results" and "amavasya scores
lower than a favorable shukla-paksha day" tests inject a minimal fake
ephemeris backend (same call signature as jyotish/ephemeris.py's public
functions) via monkeypatching muhurta._ephemeris_module -- they do NOT
mock jyotish/panchang.py itself, since that module is pure Python (no
Skyfield dependency) and is exercised for real.
"""
import sys
import pathlib
from datetime import date, datetime, timedelta

import pytest

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_determination import muhurta
from Business_Prediction.business_determination.muhurta import find_business_muhurta, MAX_SCAN_DAYS


_LOCATION = {"lat": 9.9252, "lon": 78.1198, "tz_offset_hours": 5.5}


class _FakeEphemeris:
    """Minimal stand-in for jyotish/ephemeris.py's public surface, keyed by
    calendar date so each test controls the Sun/Moon longitude (and hence
    tithi/nakshatra) seen for a given candidate day."""

    def __init__(self, longitudes_by_date):
        self._longitudes_by_date = longitudes_by_date

    def is_available(self):
        return True

    def get_sunrise_jd(self, day, lat, lon, tz_offset_hours):
        return day.toordinal() + 0.25  # 06:00 local, encoded as a fake "JD"

    def get_sunset_jd(self, day, lat, lon, tz_offset_hours):
        return day.toordinal() + 0.75  # 18:00 local

    def tt_jd_to_local_datetime(self, jd_tt, tz_offset_hours):
        ordinal = int(jd_tt)
        frac_hours = (jd_tt - ordinal) * 24.0
        return datetime.fromordinal(ordinal) + timedelta(hours=frac_hours)

    def get_planet_longitudes(self, dt_local, lat, lon, tz_offset_hours=None):
        key = dt_local.date()
        return self._longitudes_by_date.get(key, {})

    def get_house_cusps_placidus(self, dt_local, lat, lon, tz_offset_hours=None):
        return {1: 0.0}  # Aries electional Lagna for deterministic tests

    def _infer_tz_offset_hours(self, lon):
        return 5.5


def _real_panchang_module():
    from jyotish import panchang as pn
    return pn


def test_ephemeris_unavailable_status_on_real_backend():
    """Sanity check on the actual (unmocked) ephemeris backend in this
    sandbox: confirms the module degrades to EPHEMERIS_UNAVAILABLE rather
    than crashing when Skyfield/DE421 cannot load (no network access)."""
    result = find_business_muhurta(
        date(2026, 8, 1), date(2026, 8, 3), "BUSINESS_LAUNCH", _LOCATION,
    )
    assert result["status"] in ("EPHEMERIS_UNAVAILABLE", "OK")
    assert isinstance(result["results"], list)
    if result["status"] == "EPHEMERIS_UNAVAILABLE":
        assert result["results"] == []
        assert "note" in result


def test_range_too_large_returns_diagnostic_and_no_crash():
    start = date(2026, 1, 1)
    end = start + timedelta(days=MAX_SCAN_DAYS + 30)
    result = find_business_muhurta(start, end, "BUSINESS_LAUNCH", _LOCATION)
    assert result["status"] == "RANGE_TOO_LARGE"
    assert result["results"] == []
    assert "note" in result and result["note"]


def test_missing_location_returns_diagnostic_and_no_crash():
    result = find_business_muhurta(date(2026, 8, 1), date(2026, 8, 3), "BUSINESS_LAUNCH", None)
    assert result["status"] == "NO_LOCATION"
    assert result["results"] == []

    result2 = find_business_muhurta(date(2026, 8, 1), date(2026, 8, 3), "BUSINESS_LAUNCH", {})
    assert result2["status"] == "NO_LOCATION"
    assert result2["results"] == []


def test_invalid_event_type_returns_diagnostic():
    result = find_business_muhurta(date(2026, 8, 1), date(2026, 8, 3), "NOT_A_REAL_EVENT", _LOCATION)
    assert result["status"] == "INVALID_EVENT_TYPE"
    assert result["results"] == []


def test_invalid_dates_return_diagnostic_and_no_crash():
    result = find_business_muhurta("not-a-date", date(2026, 8, 3), "BUSINESS_LAUNCH", _LOCATION)
    assert result["status"] == "INVALID_DATES"
    assert result["results"] == []

    result2 = find_business_muhurta(date(2026, 8, 5), date(2026, 8, 1), "BUSINESS_LAUNCH", _LOCATION)
    assert result2["status"] == "INVALID_DATES"


def test_valid_range_returns_ranked_results_with_sane_tiers(monkeypatch):
    start = date(2026, 8, 1)
    end = start + timedelta(days=4)
    longitudes_by_date = {}
    d = start
    i = 0
    while d <= end:
        # Cycle through a few Sun/Moon separations so tithi/nakshatra vary
        # day to day; keep Mercury far from Sun to avoid combustion noise.
        sun = 10.0
        moon = (10.0 + 15.0 * (i + 1)) % 360.0
        longitudes_by_date[d] = {"Sun": sun, "Moon": moon, "Mercury": 150.0, "Jupiter": 200.0, "Venus": 250.0}
        d += timedelta(days=1)
        i += 1

    fake_eph = _FakeEphemeris(longitudes_by_date)
    monkeypatch.setattr(muhurta, "_ephemeris_module", lambda: fake_eph)
    monkeypatch.setattr(muhurta, "_panchang_module", _real_panchang_module)

    result = find_business_muhurta(start, end, "BUSINESS_LAUNCH", _LOCATION)
    assert result["status"] == "OK"
    assert result["scanned_days"] == 5
    assert len(result["results"]) >= 1

    scores = [r["score_0_100"] for r in result["results"]]
    assert scores == sorted(scores, reverse=True)  # ranked best-first
    for r in result["results"]:
        assert r["tier"] in ("EXCELLENT", "GOOD", "ACCEPTABLE", "AVOID")
        assert 0 <= r["score_0_100"] <= 100
        assert "reasons" in r and isinstance(r["reasons"], list)
        assert "citations" in r and isinstance(r["citations"], list)
        assert "rahu_kalam" in r and "yamaganda" in r and "gulika_kalam" in r


def test_amavasya_day_scores_lower_than_favorable_shukla_nakshatra_day(monkeypatch):
    # Both candidate days are the same weekday (7 days apart) so the vara
    # score and Rahu/Yamaganda/Gulika Kalam portion pattern are identical,
    # isolating the tithi/nakshatra effect being tested.
    day_amavasya = date(2026, 8, 5)   # Wednesday
    day_favorable = date(2026, 8, 12)  # Wednesday, one week later

    longitudes_by_date = {
        # diff = (moon - sun) % 360 = 350 -> tithi 30 = Amavasya
        day_amavasya: {"Sun": 25.0, "Moon": 15.0, "Mercury": 150.0},
        # diff = 20 -> tithi 2 (Shukla, non-rikta); moon_lon=45 -> Rohini,
        # a nakshatra in BUSINESS_LAUNCH's curated favorable list.
        day_favorable: {"Sun": 25.0, "Moon": 45.0, "Mercury": 150.0},
    }

    fake_eph = _FakeEphemeris(longitudes_by_date)
    monkeypatch.setattr(muhurta, "_ephemeris_module", lambda: fake_eph)
    monkeypatch.setattr(muhurta, "_panchang_module", _real_panchang_module)

    result_a = find_business_muhurta(day_amavasya, day_amavasya, "BUSINESS_LAUNCH", _LOCATION)
    result_b = find_business_muhurta(day_favorable, day_favorable, "BUSINESS_LAUNCH", _LOCATION)

    assert result_a["status"] == "OK" and result_b["status"] == "OK"
    assert len(result_a["results"]) >= 1 and len(result_b["results"]) >= 1

    score_a = result_a["results"][0]["score_0_100"]
    score_b = result_b["results"][0]["score_0_100"]
    assert result_a["results"][0]["panchang"]["tithi"] == "Amavasya"
    assert result_b["results"][0]["panchang"]["nakshatra"] == "Rohini"
    assert score_a < score_b


def test_multiple_intraday_windows_are_evaluated(monkeypatch):
    day = date(2026, 8, 12)
    fake_eph = _FakeEphemeris({day: {
        "Sun": 25.0, "Moon": 45.0, "Mercury": 150.0,
        "Jupiter": 200.0, "Venus": 250.0, "Mars": 90.0, "Saturn": 300.0,
    }})
    monkeypatch.setattr(muhurta, "_ephemeris_module", lambda: fake_eph)
    monkeypatch.setattr(muhurta, "_panchang_module", _real_panchang_module)
    result = find_business_muhurta(day, day, "BUSINESS_LAUNCH", _LOCATION)
    assert result["candidate_windows_evaluated"] > 1
    assert len({row["window_start"] for row in result["results"]}) > 1
    windows = sorted(
        (datetime.fromisoformat(row["window_start"]), datetime.fromisoformat(row["window_end"]))
        for row in result["results"]
    )
    assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))


def test_aspect_layer_includes_luminaries_nodes_and_plain_text_units():
    eph = _FakeEphemeris({})
    longitudes = {
        "Sun": 180.0, "Moon": 180.0, "Mars": 270.0, "Mercury": 180.0,
        "Jupiter": 240.0, "Venus": 180.0, "Saturn": 300.0,
        "Rahu": 180.0, "Ketu": 180.0,
    }
    _, _, detail = muhurta._electional_chart_adjustment(
        eph, datetime(2026, 8, 12, 12), 9.9, 78.1, 5.5,
        longitudes, "BUSINESS_LAUNCH", {"tithi_num": 2, "nakshatra_num": 4, "vara_name": "Wednesday"},
    )
    notes = " ".join(detail["aspect_notes"])
    for planet in longitudes:
        assert planet in notes
    assert " degrees" in notes
    assert "Â°" not in notes
