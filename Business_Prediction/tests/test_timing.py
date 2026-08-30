"""Tests for Business_Prediction.business_determination.timing's
Pratyantardasha (PD) sub-window expansion, added on top of the existing
AD-level windows (_compute_windows_and_status / _business_ad_windows).

Covers:
  - normal case: PD sub-windows correctly nested under an AD window, with
    each PD's date range contained within its parent AD's date range
    (explicit invariant assertion).
  - missing-data case: degrades gracefully to AD-only windows (no crash),
    with the original ANTARDASHA-level disclosure intact.
  - disclosure logic: timing_precision reflects PRATYANTARDASHA when PD
    expansion succeeded, and falls back to ANTARDASHA with a machine-
    readable pd_expansion_status otherwise.
"""
import sys
import pathlib
from datetime import date

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_determination.timing import (
    _compute_windows_and_status,
    _business_pd_subwindows,
    _timing_precision_disclosure,
    _compute_method_status,
    _PD_STATUS_OK,
    _PD_STATUS_NO_LORDS,
)


class _FakePayload:
    """Duck-typed stand-in for NatalPayloadV2, same pattern used across
    this test suite (see test_business_engine.py's _FakePayload)."""

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
        self.darakaraka = "Saturn"
        self.lagna_sign = "Sagittarius"
        # Long-running Venus AD/MD span so the PD expansion has a
        # comfortably wide window to sub-divide.
        self.dasha_sequence = [
            {"lord": "Mercury", "start_age": 0, "end_age": 17},
            {"lord": "Ketu", "start_age": 17, "end_age": 24},
            {"lord": "Venus", "start_age": 24, "end_age": 44},
            {"lord": "Sun", "start_age": 44, "end_age": 50},
        ]


def _iso(s):
    return date.fromisoformat(str(s)[:10])


def test_pd_subwindows_nested_and_date_contained():
    payload = _FakePayload()
    windows, status = _compute_windows_and_status(payload, years_ahead=40, as_of_date=date(1995, 1, 1))
    assert status["status"] == "OK"
    assert windows, "expected at least one AD window in a 40-year horizon"

    found_pd = False
    for w in windows:
        assert "pd_subwindows" in w
        assert "pd_status" in w
        ad_start = _iso(w["start_date"])
        ad_end = _iso(w["end_date"])
        for pd in w["pd_subwindows"]:
            found_pd = True
            pd_start = _iso(pd["start_date"])
            pd_end = _iso(pd["end_date"])
            # Explicit date-range containment invariant.
            assert ad_start <= pd_start <= ad_end, (w, pd)
            assert ad_start <= pd_end <= ad_end, (w, pd)
            assert pd_start <= pd_end
            # Sub-window carries its own lord, tier label, and citation --
            # existing AD-level keys must remain unchanged (checked below).
            assert pd["pd_lord"]
            assert pd["label"] in (
                "STRONG_FAVORABLE", "FAVORABLE", "MIXED", "CAUTION", "HIGH_RISK",
            )
            assert pd["detail"]

    assert found_pd, "expected at least one window with successfully expanded PD sub-windows"

    # Backward compatibility: existing AD-level keys/shape unchanged.
    for w in windows:
        for key in ("md_lord", "ad_lord", "start_date", "end_date", "net_score", "label", "evidence", "arbitration_ledger", "tags"):
            assert key in w


def test_pd_subwindows_missing_house_lords_degrades_gracefully():
    # Isolate the PD-expansion degradation path directly: with no
    # house_lords, _business_pd_subwindows() must not crash and must
    # report NO_LORDS rather than raising or silently fabricating data.
    # (Note: house_lords is ALSO required for AD-level evidence itself, so
    # _compute_windows_and_status() with an empty house_lords payload would
    # legitimately produce zero AD windows too -- that is a separate,
    # upstream degradation this test does not conflate with PD-level
    # degradation.)
    payload = _FakePayload()
    payload.house_lords = {}
    window = {
        "md_lord": "Venus", "ad_lord": "Sun",
        "start_date": "2020-01-01", "end_date": "2021-01-01",
        "net_score": 5.0,
    }
    subs, pd_status = _business_pd_subwindows(window, payload)
    assert subs == []
    assert pd_status == _PD_STATUS_NO_LORDS

    # And confirm the full pipeline still runs without crashing when
    # house_lords is missing (status stays OK; it may simply find no
    # scorable AD windows since AD-level evidence also needs house_lords).
    windows, status = _compute_windows_and_status(payload, years_ahead=40, as_of_date=date(1995, 1, 1))
    assert status["status"] == "OK"
    assert windows == []


def test_pd_subwindows_import_failure_does_not_crash():
    window = {
        "md_lord": "Venus", "ad_lord": "Sun",
        "start_date": "2020-01-01", "end_date": "2021-01-01",
        "net_score": 5.0,
    }
    payload = _FakePayload()

    import builtins
    real_import = builtins.__import__

    def _broken_import(name, *args, **kwargs):
        if name == "Job_Career.timeline":
            raise ImportError("simulated import failure")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = _broken_import
    try:
        subs, pd_status = _business_pd_subwindows(window, payload)
    finally:
        builtins.__import__ = real_import

    assert subs == []
    assert pd_status == "IMPORT_FAILED"


def test_disclosure_reflects_pd_success():
    disclosure = _timing_precision_disclosure({"pd_status_summary": _PD_STATUS_OK})
    assert disclosure["level"] == "PRATYANTARDASHA"
    assert "Pratyantardasha" in disclosure["note"]


def test_disclosure_falls_back_when_pd_unavailable():
    disclosure = _timing_precision_disclosure({"pd_status_summary": _PD_STATUS_NO_LORDS})
    assert disclosure["level"] == "ANTARDASHA"
    assert disclosure["pd_expansion_status"] == _PD_STATUS_NO_LORDS
    assert "NOT computed here" in disclosure["note"]


def test_method_status_uses_conditional_disclosure():
    payload = _FakePayload()
    windows, timing_status = _compute_windows_and_status(payload, years_ahead=40, as_of_date=date(1995, 1, 1))
    method_status = _compute_method_status(payload, windows, timing_status, {"status": "NOT_APPLICABLE"})
    precision = method_status["timing_precision"]
    assert precision["status"] == "INFORMATIONAL"
    assert precision["level"] in ("ANTARDASHA", "PRATYANTARDASHA")
