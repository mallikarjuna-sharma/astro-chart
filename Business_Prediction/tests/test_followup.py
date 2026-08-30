"""Tests for Business_Prediction.followup (grounded Q&A + reforecast alert
status checks). Uses the same _FakePayload / compute_business_prediction
approach as test_business_engine.py / test_pdf_export.py for a real
prediction dict, plus a synthetic partnership_synastry dict merged in for
the routing test (compute_partnership_synastry needs two payloads and
isn't part of the base compute_business_prediction() output).
"""
import sys
import pathlib
from datetime import date, timedelta

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_engine import compute_business_prediction
from Business_Prediction.followup import answer_followup_question, check_reforecast_needed


class _FakePayload:
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


def _prediction():
    return compute_business_prediction(_FakePayload())


# ── answer_followup_question ───────────────────────────────────────────

def test_partnership_question_routes_grounded():
    prediction = _prediction()
    prediction["partnership_synastry"] = {
        "status": "OK",
        "composite_score_0_100": 71.5,
        "compatibility_label": "WORKABLE_FIT",
    }
    result = answer_followup_question(prediction, "How compatible is my business partner with me?")
    assert result["confidence"] == "GROUNDED"
    assert "partnership_synastry" in result["matched_sections"]
    assert "partnership_synastry" in result["evidence"]
    assert result["evidence"]["partnership_synastry"]["compatibility_label"] == "WORKABLE_FIT"


def test_unrelated_question_returns_no_match_honestly():
    prediction = _prediction()
    result = answer_followup_question(prediction, "What is the capital of France?")
    assert result["confidence"] == "NO_MATCH"
    assert result["matched_sections"] == []
    assert result["evidence"] == {}
    assert "not" in result["message"].lower() or "no answer" in result["message"].lower() or "isn't addressed" in result["message"].lower()


def test_matched_keyword_but_no_data_still_no_match():
    prediction = _prediction()
    # legal_dispute_risk key deliberately absent/empty on this prediction.
    prediction.pop("legal_dispute_risk", None)
    result = answer_followup_question(prediction, "Is there any legal dispute risk for me?")
    assert result["confidence"] == "NO_MATCH"


def test_default_no_llm_call(monkeypatch):
    # Default use_llm_narrative=False must never touch the LLM path even
    # if consent env vars happen to be set -- verified by not patching
    # anything and confirming narrative stays None.
    prediction = _prediction()
    prediction["detected_yogas"] = [{"yoga_name": "Dhana Yoga", "effect": "supports steady income"}]
    result = answer_followup_question(prediction, "What yogas are detected in my chart?")
    assert result["confidence"] == "GROUNDED"
    assert result["narrative"] is None


# ── check_reforecast_needed ────────────────────────────────────────────

def _windows(start: date, end: date, md_lord="Venus", ad_lord="Mercury"):
    return [{
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "md_lord": md_lord,
        "ad_lord": ad_lord,
        "label": "FAVORABLE",
        "net_score": 3.0,
        "evidence": [],
    }]


def test_as_of_date_inside_original_window_no_reforecast():
    today = date.today()
    prediction = {"timed_windows": _windows(today - timedelta(days=30), today + timedelta(days=365))}
    result = check_reforecast_needed(prediction, as_of_date=today.isoformat())
    assert result["reforecast_recommended"] is False
    assert "next_check_date" in result


def test_as_of_date_past_window_end_triggers_reforecast():
    start = date(2020, 1, 1)
    end = date(2020, 12, 31)
    prediction = {"timed_windows": _windows(start, end)}
    future_date = (end + timedelta(days=400)).isoformat()
    result = check_reforecast_needed(prediction, as_of_date=future_date)
    assert result["reforecast_recommended"] is True
    assert result["reason"]


def test_missing_timed_windows_recommends_reforecast():
    result = check_reforecast_needed({"timed_windows": []}, as_of_date=date.today().isoformat())
    assert result["reforecast_recommended"] is True
