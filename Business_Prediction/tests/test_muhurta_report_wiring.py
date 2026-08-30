"""Tests that the generated HTML reports (astrologer + client editions)
now auto-include a Muhurta Recommendations section by default, without
the caller having to invoke find_business_muhurta()/stitch it in
manually -- see generate_business_report.py::_default_business_muhurta_result()
and its use inside render_astrologer_report_html()/render_client_report_html().
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_engine import compute_business_prediction, _load_business_registry
from Business_Prediction.generate_business_report import (
    render_astrologer_report_html,
    render_client_report_html,
    _default_business_muhurta_result,
)
from Business_Prediction.tests.test_business_engine import _FakePayload


def _prediction():
    payload = _FakePayload()
    all_sector_count = len(_load_business_registry().get("sectors", {}))
    return payload, compute_business_prediction(payload, top_n_sectors=all_sector_count)


def test_astrologer_report_includes_muhurta_section_by_default():
    payload, prediction = _prediction()
    html = render_astrologer_report_html("Test Native", prediction, lang="en", payload=payload)
    assert 'id="muhurta-recommendations"' in html
    # _FakePayload has no lat/lon in this schema -> honest NO_LOCATION note,
    # not a crash and not a silently-empty section.
    assert "NO_LOCATION" in html or "Auspicious" in html


def test_client_report_includes_muhurta_section_by_default():
    payload, prediction = _prediction()
    html = render_client_report_html("Test Native", prediction, lang="en", payload=payload)
    assert 'id="muhurta-recommendations"' in html


def test_missing_location_degrades_gracefully_not_a_crash():
    payload, prediction = _prediction()
    result = _default_business_muhurta_result(payload)
    assert result["status"] in ("NO_LOCATION", "EPHEMERIS_UNAVAILABLE")
    assert result["results"] == []
    # Rendering with this diagnostic result must not raise.
    html = render_astrologer_report_html(
        "Test Native", prediction, lang="en", payload=payload, muhurta_result=result,
    )
    assert 'id="muhurta-recommendations"' in html


def test_explicit_location_is_honored_when_present():
    payload, prediction = _prediction()
    location = {"lat": 13.0827, "lon": 80.2707, "tz_offset_hours": 5.5}
    result = _default_business_muhurta_result(payload, location=location)
    # In this sandbox the Skyfield/DE421 ephemeris is unavailable (no
    # network access to fetch de421.bsp), so even with a valid location
    # this degrades to EPHEMERIS_UNAVAILABLE rather than NO_LOCATION --
    # confirming location was actually consumed, not silently ignored.
    assert result["status"] != "NO_LOCATION"


def test_caller_can_override_event_type():
    payload, prediction = _prediction()
    result = _default_business_muhurta_result(payload, event_type="PARTNERSHIP_SIGNING")
    assert result["event_type"] == "PARTNERSHIP_SIGNING"
