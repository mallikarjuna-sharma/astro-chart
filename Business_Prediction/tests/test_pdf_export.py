"""Tests for Business_Prediction.pdf_export.render_report_pdf.

Uses the same minimal duck-typed _FakePayload + compute_business_prediction
approach as test_business_engine.py, so the prediction dict fed to
render_report_pdf is a real (if minimal) engine output, not a hand-rolled
stand-in that could drift from the actual shape render_astrologer_report_html
/ render_client_report_html expect.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_engine import compute_business_prediction
from Business_Prediction.pdf_export import render_report_pdf, _get_pdf_backend


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


def _assert_pdf_or_graceful_fallback(data: bytes):
    """Accepts either a real PDF (starts with %PDF-, per weasyprint/
    xhtml2pdf output) or the graceful HTML fallback (carries the
    UNAVAILABLE_FALLBACK_TO_HTML marker comment) -- never anything else,
    and never an exception."""
    assert isinstance(data, (bytes, bytearray))
    assert len(data) > 0
    if data.lstrip().startswith(b"%PDF"):
        return  # real PDF produced
    assert b"UNAVAILABLE_FALLBACK_TO_HTML" in data, (
        "Non-PDF output must carry the graceful-fallback marker, not silently return unmarked HTML."
    )


def test_astrologer_pdf_bytes_or_graceful_fallback():
    prediction = _prediction()
    data = render_report_pdf(prediction, audience="astrologer", lang="en", name="Test Native")
    _assert_pdf_or_graceful_fallback(data)


def test_client_pdf_bytes_or_graceful_fallback():
    prediction = _prediction()
    data = render_report_pdf(prediction, audience="client", lang="en", name="Test Native")
    _assert_pdf_or_graceful_fallback(data)


def test_invalid_audience_raises_value_error():
    prediction = _prediction()
    try:
        render_report_pdf(prediction, audience="nonsense")
        assert False, "expected ValueError for invalid audience"
    except ValueError:
        pass


def test_output_path_write(tmp_path):
    prediction = _prediction()
    out = tmp_path / "report.pdf"
    result_path = render_report_pdf(prediction, audience="client", output_path=str(out))
    assert result_path == str(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_backend_detected_is_one_of_expected_values():
    # Not asserting a specific backend is installed (sandbox-dependent),
    # just that the probe returns a known value and never raises.
    backend = _get_pdf_backend()
    assert backend in ("weasyprint", "xhtml2pdf", None)
