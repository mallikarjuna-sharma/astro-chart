"""Tests for Business_Prediction.business_determination.ashtakavarga_timing
(year-by-year Ashtakavarga/SAV business-timing ranking).

Uses the same duck-typed minimal stand-in payload approach as
test_yogas.py's _YogaPayload -- ashtakavarga_timing.py only reads
lagna_sign/dob, sav_points_houses, and transit_house_positions.
"""
import sys
import pathlib
from datetime import date

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_determination.ashtakavarga_timing import (
    rank_business_years,
    BUSINESS_SAV_HOUSES,
    MAX_YEAR_SPAN,
)


class _AVPayload:
    def __init__(self, sav_points_houses, transit_house_positions=None, lagna_sign="Aries", dob="1990-05-15",
                 bav_points_shodhita=None):
        self.dob = dob
        self.lagna_sign = lagna_sign
        self.sav_points_houses = sav_points_houses
        self.transit_house_positions = transit_house_positions or {"Jupiter": 1, "Saturn": 4}
        if bav_points_shodhita is not None:
            self.bav_points_shodhita = bav_points_shodhita


def _flat_sav(value=28):
    return {str(h): value for h in range(1, 13)}


def test_valid_year_range_returns_ranked_years_with_sane_tiers():
    payload = _AVPayload(_flat_sav(30))
    result = rank_business_years(payload, 2026, 2030, as_of_date=date(2026, 1, 1))
    assert result["status"] == "OK"
    ranked = result["ranked_years"]
    assert len(ranked) == 5
    years_seen = sorted(r["year"] for r in ranked)
    assert years_seen == [2026, 2027, 2028, 2029, 2030]
    valid_tiers = {"EXCELLENT", "GOOD", "AVERAGE", "WEAK"}
    for r in ranked:
        assert r["tier"] in valid_tiers
        assert isinstance(r["sav_score"], float)
        assert "reasons" in r and "detail" in r["reasons"] and "effect" in r["reasons"]
    # Sorted strongest-first.
    scores = [r["sav_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_excessive_year_span_returns_diagnostic_without_crashing():
    payload = _AVPayload(_flat_sav(30))
    result = rank_business_years(payload, 2000, 2000 + MAX_YEAR_SPAN + 5, as_of_date=date(2026, 1, 1))
    assert result["status"] == "RANGE_TOO_LARGE"
    assert result["ranked_years"] == []
    assert "note" in result


def test_missing_birth_data_degrades_gracefully():
    class _Empty:
        pass
    result = rank_business_years(_Empty(), 2026, 2028)
    assert result["status"] == "MISSING_BIRTH_DATA"
    assert result["ranked_years"] == []

    # dob present but lagna_sign missing -- still MISSING_BIRTH_DATA.
    class _NoLagna:
        dob = "1990-05-15"
    result2 = rank_business_years(_NoLagna(), 2026, 2028)
    assert result2["status"] == "MISSING_BIRTH_DATA"


def test_missing_sav_degrades_gracefully():
    payload = _AVPayload({})
    result = rank_business_years(payload, 2026, 2028, as_of_date=date(2026, 1, 1))
    assert result["status"] == "SAV_UNAVAILABLE"
    assert result["ranked_years"] == []


def test_invalid_range_degrades_gracefully():
    payload = _AVPayload(_flat_sav(30))
    result = rank_business_years(payload, 2030, 2026, as_of_date=date(2026, 1, 1))
    assert result["status"] == "INVALID_RANGE"


def test_higher_h11_sav_ranks_year_higher_when_jupiter_transits_h11():
    """Sanity check requested by task: a year where transiting Jupiter sits
    in H11 (a business house) with a HIGH natal H11 SAV bindu count should
    score higher than an otherwise-identical chart where H11's natal SAV
    is low -- isolating the natal-SAV contribution to the composite score."""
    sav_high_h11 = _flat_sav(28)
    sav_high_h11["11"] = 40  # strong natal H11 SAV

    sav_low_h11 = _flat_sav(28)
    sav_low_h11["11"] = 20  # weak natal H11 SAV

    # Jupiter natally at house 1 from Lagna; project to land on H11 within
    # the tested year window (Jupiter ~365 days/house -> +10 houses from
    # H1 lands on H11, i.e. ~10*365 days ahead of the snapshot).
    high_payload = _AVPayload(sav_high_h11, transit_house_positions={"Jupiter": 1, "Saturn": 0})
    low_payload = _AVPayload(sav_low_h11, transit_house_positions={"Jupiter": 1, "Saturn": 0})

    snapshot = date(2020, 1, 1)
    # Scan a wide window and find a year where Jupiter's projected house
    # lands on H11 for both payloads (mean-motion projection, ~1yr/house,
    # so search a broad span rather than assuming an exact offset).
    scan_start, scan_end = snapshot.year + 1, snapshot.year + MAX_YEAR_SPAN
    high_result = rank_business_years(high_payload, scan_start, scan_end, as_of_date=snapshot)
    low_result = rank_business_years(low_payload, scan_start, scan_end, as_of_date=snapshot)

    assert high_result["status"] == "OK"
    assert low_result["status"] == "OK"

    high_by_year = {r["year"]: r for r in high_result["ranked_years"]}
    low_by_year = {r["year"]: r for r in low_result["ranked_years"]}
    target_years = [y for y, r in high_by_year.items() if r["jupiter_house"] == 11]
    assert target_years, "expected at least one scanned year with Jupiter projected into H11"
    target_year = target_years[0]

    high_year = high_by_year[target_year]
    low_year = low_by_year[target_year]

    # Confirm Jupiter actually projected into H11 for this setup, so the
    # comparison isolates the natal-SAV effect as intended.
    assert high_year["jupiter_house"] == 11
    assert low_year["jupiter_house"] == 11
    assert high_year["sav_score"] > low_year["sav_score"]


def test_dasha_corroboration_cross_references_timing_windows():
    payload = _AVPayload(_flat_sav(30))
    timing_windows = [
        {"md_lord": "Jupiter", "ad_lord": "Venus", "label": "STRONG_FAVORABLE",
         "start_date": "2026-01-01", "end_date": "2026-12-31"},
        {"md_lord": "Saturn", "ad_lord": "Mars", "label": "CAUTION",
         "start_date": "2029-01-01", "end_date": "2029-12-31"},
    ]
    result = rank_business_years(payload, 2026, 2030, timing_windows=timing_windows, as_of_date=date(2026, 1, 1))
    by_year = {r["year"]: r for r in result["ranked_years"]}
    assert by_year[2026]["dasha_corroboration"][0]["label"] == "STRONG_FAVORABLE"
    assert by_year[2029]["dasha_corroboration"][0]["label"] == "CAUTION"
    assert by_year[2027]["dasha_corroboration"] == []
    assert by_year[2026]["dasha_adjustment"] > 0
    assert by_year[2029]["dasha_adjustment"] < 0


def test_dasha_arbitration_changes_otherwise_equal_year_order():
    payload = _AVPayload(_flat_sav(30), transit_house_positions={"Jupiter": 0, "Saturn": 0})
    windows = [
        {"label": "HIGH_RISK", "start_date": "2026-01-01", "end_date": "2026-12-31"},
        {"label": "STRONG_FAVORABLE", "start_date": "2027-01-01", "end_date": "2027-12-31"},
    ]
    result = rank_business_years(payload, 2026, 2027, timing_windows=windows, as_of_date=date(2026, 1, 1))
    assert result["ranked_years"][0]["year"] == 2027


def test_low_bav_bindus_tempers_a_sav_only_strong_year():
    """A year where SAV alone (transiting Jupiter through H11 with a high
    natal H11 SAV bindu count) would call the year strong, but Jupiter's own
    post-shodhana BAV bindu count in that same H11 is low (<=4, "WEAK" per
    the classical threshold) -- the composite score must be tempered below
    the SAV-only score, not silently equal to it, and bav_status must report
    the BAV component actually ran."""
    snapshot = date(2026, 7, 1)
    sav = _flat_sav(28)
    sav["11"] = 40  # strong natal H11 SAV -> SAV bonus fires
    payload = _AVPayload(
        sav, transit_house_positions={"Jupiter": 11, "Saturn": 0},
        bav_points_shodhita={"Jupiter": {"11": 2}},  # weak BAV (<=4)
    )
    result = rank_business_years(payload, 2026, 2026, as_of_date=snapshot)
    assert result["status"] == "OK"
    year = result["ranked_years"][0]
    assert year["jupiter_house"] == 11
    assert year["bav_bindus_jupiter"] == 2
    assert year["bav_interpretation"]["Jupiter"] == "WEAK"
    assert year["bav_status"] == "OK"
    # Composite must be strictly lower than the SAV-only score -- tempered,
    # not silently overridden/ignored.
    assert year["bav_bonus"] < 0
    assert year["composite_score"] < year["sav_score"]


def test_high_bav_bindus_reinforces_a_sav_strong_year():
    """Mirror of the above: BAV corroborates SAV (both strong) -- the
    composite score should reflect reinforcement (higher than the SAV-only
    score), not be capped back down to it."""
    snapshot = date(2026, 7, 1)
    sav = _flat_sav(28)
    sav["11"] = 40
    payload = _AVPayload(
        sav, transit_house_positions={"Jupiter": 11, "Saturn": 0},
        bav_points_shodhita={"Jupiter": {"11": 8}},  # strong/favorable BAV
    )
    result = rank_business_years(payload, 2026, 2026, as_of_date=snapshot)
    assert result["status"] == "OK"
    year = result["ranked_years"][0]
    assert year["bav_bindus_jupiter"] == 8
    assert year["bav_interpretation"]["Jupiter"] == "FAVORABLE"
    assert year["bav_bonus"] > 0
    assert year["composite_score"] > year["sav_score"]


def test_bav_unavailable_degrades_to_sav_only_without_crashing():
    """Graceful-degradation case: no bav_points_shodhita on the payload at
    all (older/partial payload, or upstream BAV computation failed). The
    function must not crash, must fall back to SAV-only scoring
    (composite_score == sav_score), and must flag the degradation via
    bav_status rather than silently reporting a fabricated bindu count."""
    snapshot = date(2026, 7, 1)
    sav = _flat_sav(28)
    sav["11"] = 40
    payload = _AVPayload(sav, transit_house_positions={"Jupiter": 11, "Saturn": 0})
    assert not hasattr(payload, "bav_points_shodhita")

    result = rank_business_years(payload, 2026, 2026, as_of_date=snapshot)
    assert result["status"] == "OK"
    year = result["ranked_years"][0]
    assert year["bav_bindus_jupiter"] is None
    assert year["bav_interpretation"]["Jupiter"] == "BAV_UNAVAILABLE"
    assert year["bav_status"] == "UNAVAILABLE"
    assert year["bav_bonus"] == 0.0
    assert year["composite_score"] == year["sav_score"]


def test_never_raises_on_malformed_payload():
    class _Weird:
        dob = "1990-05-15"
        lagna_sign = "Aries"
        sav_points_houses = "not-a-dict"  # malformed on purpose
        transit_house_positions = {"Jupiter": 1}

    result = rank_business_years(_Weird(), 2026, 2028)
    assert "status" in result  # did not raise
