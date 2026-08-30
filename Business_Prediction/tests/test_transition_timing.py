"""Tests for Business_Prediction.business_determination.transition_timing
(compute_transition_timing_recommendation) -- cross-wires mode_gate's static
recommended_mode/margin against timing's current/upcoming favorable-window
calendar to answer "act now, or wait for a specific window?"

Uses direct dict/list fixtures for mode_gate_result/timed_windows (the
function's own contract only requires business_score/employment_score/
recommended_mode on the former and start_date/end_date/label on each window
of the latter), plus one full end-to-end test against
compute_business_prediction()'s actual result dict to confirm wiring.
"""
import sys
import pathlib
from datetime import date

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_determination.transition_timing import (
    compute_transition_timing_recommendation,
)
from Business_Prediction.business_engine import compute_business_prediction


def _mode_gate(business_score, employment_score, recommended_mode="business"):
    return {
        "business_score": business_score,
        "employment_score": employment_score,
        "recommended_mode": recommended_mode,
    }


def test_act_now_when_business_favored_and_currently_in_favorable_window():
    mode_gate = _mode_gate(business_score=70, employment_score=50)  # margin=20, HIGH
    as_of = date(2026, 7, 26)
    windows = [
        {
            "md_lord": "Venus", "ad_lord": "Mercury",
            "start_date": "2026-01-01", "end_date": "2027-01-01",
            "label": "FAVORABLE",
        },
    ]
    result = compute_transition_timing_recommendation(mode_gate, windows, as_of_date=as_of)
    assert result["verdict"] == "ACT_NOW"
    assert result["current_window"]["label"] == "FAVORABLE"
    assert result["mode_gate_basis"]["margin"] == 20
    assert result["mode_gate_basis"]["margin_tier"] == "HIGH"
    assert "model_status" in result and "calibration_status" in result
    assert result["disclaimer"]


def test_wait_for_window_when_business_favored_but_current_window_unfavorable():
    mode_gate = _mode_gate(business_score=65, employment_score=50)  # margin=15, MODERATE
    as_of = date(2026, 7, 26)
    windows = [
        {
            "md_lord": "Saturn", "ad_lord": "Rahu",
            "start_date": "2026-01-01", "end_date": "2026-12-31",
            "label": "CAUTION",
        },
        {
            "md_lord": "Saturn", "ad_lord": "Jupiter",
            "start_date": "2027-01-01", "end_date": "2028-06-30",
            "label": "STRONG_FAVORABLE",
        },
    ]
    result = compute_transition_timing_recommendation(mode_gate, windows, as_of_date=as_of)
    assert result["verdict"] == "WAIT_FOR_WINDOW"
    assert result["current_window"]["label"] == "CAUTION"
    assert result["next_favorable_window"]["start_date"] == "2027-01-01"
    assert result["next_favorable_window"]["label"] == "STRONG_FAVORABLE"
    assert "wait" in result["client_message"].lower() or "2027" in result["client_message"]


def test_wait_for_window_graceful_when_no_favorable_window_found_in_horizon():
    mode_gate = _mode_gate(business_score=65, employment_score=50)
    as_of = date(2026, 7, 26)
    windows = [
        {
            "md_lord": "Saturn", "ad_lord": "Rahu",
            "start_date": "2026-01-01", "end_date": "2030-12-31",
            "label": "MIXED",
        },
    ]
    result = compute_transition_timing_recommendation(mode_gate, windows, as_of_date=as_of)
    assert result["verdict"] == "WAIT_FOR_WINDOW"
    assert result["next_favorable_window"] is None
    assert "reason" in result and result["reason"]


def test_reconsider_mode_when_margin_thin_regardless_of_favorable_timing():
    # margin=5, below mode_gate's own MODERATE threshold of 10 -- timing is
    # moot even though the current window is STRONG_FAVORABLE.
    mode_gate = _mode_gate(business_score=55, employment_score=50)
    as_of = date(2026, 7, 26)
    windows = [
        {
            "md_lord": "Jupiter", "ad_lord": "Venus",
            "start_date": "2026-01-01", "end_date": "2027-01-01",
            "label": "STRONG_FAVORABLE",
        },
    ]
    result = compute_transition_timing_recommendation(mode_gate, windows, as_of_date=as_of)
    assert result["verdict"] == "RECONSIDER_MODE"
    assert "staying employed" in result["client_message"].lower()


def test_reconsider_mode_when_recommended_mode_is_not_business():
    mode_gate = _mode_gate(business_score=80, employment_score=40, recommended_mode="employment")
    as_of = date(2026, 7, 26)
    result = compute_transition_timing_recommendation(mode_gate, [], as_of_date=as_of)
    assert result["verdict"] == "RECONSIDER_MODE"


def test_insufficient_data_when_mode_gate_missing_scores():
    result = compute_transition_timing_recommendation({}, [], as_of_date=date(2026, 7, 26))
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_insufficient_data_when_mode_gate_result_not_a_dict():
    result = compute_transition_timing_recommendation(None, [], as_of_date=date(2026, 7, 26))
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_insufficient_data_when_timed_windows_none():
    mode_gate = _mode_gate(business_score=70, employment_score=50)
    result = compute_transition_timing_recommendation(mode_gate, None, as_of_date=date(2026, 7, 26))
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_insufficient_data_when_timing_status_reports_calendar_failure():
    mode_gate = _mode_gate(business_score=70, employment_score=50)
    result = compute_transition_timing_recommendation(
        mode_gate, [], timing_status={"status": "NO_DASHA_SEQUENCE"}, as_of_date=date(2026, 7, 26),
    )
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_never_raises_and_never_fabricates_verdict_from_malformed_window():
    mode_gate = _mode_gate(business_score=70, employment_score=50)
    windows = [{"start_date": "not-a-date", "end_date": "also-not-a-date", "label": "FAVORABLE"}]
    result = compute_transition_timing_recommendation(mode_gate, windows, as_of_date=date(2026, 7, 26))
    assert result["verdict"] in ("WAIT_FOR_WINDOW",)  # malformed window ignored, no current window found


class _EndToEndPayload:
    """Minimal-but-complete chart payload, same shape as
    test_business_engine.py's _FakePayload, for an end-to-end wiring check
    against the real compute_business_prediction() pipeline."""

    def __init__(self):
        self.dob = "1990-05-15"
        self.planet_house = {
            "Sun": 10, "Moon": 4, "Mars": 3, "Mercury": 7,
            "Jupiter": 1, "Venus": 7, "Saturn": 6, "Rahu": 7, "Ketu": 1,
        }
        self.house_lords = {
            "1": "Jupiter", "2": "Saturn", "3": "Saturn", "4": "Jupiter",
            "5": "Mars", "6": "Venus", "7": "Mars", "8": "Venus",
            "9": "Mercury", "10": "Mercury", "11": "Sun", "12": "Moon",
        }
        self.planet_dignities = {"Mercury": "OWN", "Venus": "EXALTED"}
        self.sav_points_houses = {"10": 32, "11": 33}
        self.darakaraka = "Saturn"
        self.dasha_sequence = [
            {"lord": "Mercury", "start_age": 0, "end_age": 17},
            {"lord": "Ketu", "start_age": 17, "end_age": 24},
            {"lord": "Venus", "start_age": 24, "end_age": 44},
        ]


def test_compute_business_prediction_wires_transition_timing_recommendation():
    result = compute_business_prediction(_EndToEndPayload())
    assert "transition_timing_recommendation" in result
    tt = result["transition_timing_recommendation"]
    assert tt["verdict"] in ("ACT_NOW", "WAIT_FOR_WINDOW", "RECONSIDER_MODE", "INSUFFICIENT_DATA")
    assert "mode_gate_basis" in tt
    assert "disclaimer" in tt and tt["disclaimer"]
    assert tt["model_status"] == result["model_status"]
    assert tt["calibration_status"] == result["calibration_status"]
