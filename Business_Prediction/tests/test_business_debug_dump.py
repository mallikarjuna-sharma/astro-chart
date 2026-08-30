"""Regression test for _dump_business_debug() surfacing the four fields
compute_business_prediction() unconditionally (or conditionally, for
partnership_synastry) adds to its result dict but that this CLI debug
dump previously omitted via its hardcoded allowlist: detected_yogas,
legal_dispute_risk, d2_hora_evidence, partnership_synastry.
"""
import sys
import pathlib
import json
import tempfile
import os

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_mode_runner import _dump_business_debug


def _minimal_prediction(**extra):
    base = {
        "mode_gate": {},
        "significators": {},
        "top_sectors": [],
        "timed_windows": [],
        "timing_status": {},
        "method_status": {},
        "recommendation": {},
    }
    base.update(extra)
    return base


def test_dump_includes_new_fields_when_present():
    prediction = _minimal_prediction(
        detected_yogas=[{"name": "Dhana Yoga"}],
        legal_dispute_risk=[{"risk_type": "LITIGATION_RISK"}],
        legal_dispute_risk_status="MATCHES_FOUND",
        yoga_detection_status="MATCHES_FOUND",
        d2_hora_evidence=[{"weight": 0.5, "note": "test"}],
        d11_gains_status={"status": "APPLIED", "capital_support": True},
        partnership_synastry={"compatibility_score": 0.7},
        authoritative_recommendation={
            "capital_readiness_status": "ASTROLOGICAL_SUPPORT",
            "capital_readiness_certified": True,
            "financial_readiness": {"certified": True},
            "ashtakavarga_year_check": {"status": "OK"},
            "muhurta_check": {"status": "OK", "candidate_windows_evaluated": 4},
        },
    )
    with tempfile.TemporaryDirectory() as tmp:
        out_path = _dump_business_debug(prediction, "Test Native", tmp)
        with open(out_path, "r", encoding="utf-8") as fh:
            dumped = json.load(fh)

    assert dumped["detected_yogas"] == [{"name": "Dhana Yoga"}]
    assert dumped["legal_dispute_risk"] == [{"risk_type": "LITIGATION_RISK"}]
    assert dumped["legal_dispute_risk_status"] == "MATCHES_FOUND"
    assert dumped["yoga_detection_status"] == "MATCHES_FOUND"
    assert dumped["d2_hora_evidence"] == [{"weight": 0.5, "note": "test"}]
    assert dumped["partnership_synastry"] == {"compatibility_score": 0.7}
    assert dumped["d11_gains_status"]["status"] == "APPLIED"
    assert dumped["capital_readiness_certified"] is True
    assert dumped["financial_readiness"] == {"certified": True}
    assert dumped["muhurta_check"]["candidate_windows_evaluated"] == 4


def test_dump_degrades_gracefully_when_partnership_synastry_absent():
    prediction = _minimal_prediction(
        detected_yogas=[],
        legal_dispute_risk=[],
        d2_hora_evidence=[],
        # no partnership_synastry key at all -- mirrors the engine's
        # behavior when no partner_payload was supplied.
    )
    with tempfile.TemporaryDirectory() as tmp:
        out_path = _dump_business_debug(prediction, "Test Native", tmp)
        with open(out_path, "r", encoding="utf-8") as fh:
            dumped = json.load(fh)

    assert dumped["partnership_synastry"] is None
    assert dumped["detected_yogas"] == []
    assert dumped["legal_dispute_risk"] == []
    assert dumped["legal_dispute_risk_status"] == "NOT_EVALUATED"
    assert dumped["yoga_detection_status"] == "NOT_EVALUATED"
    assert dumped["d2_hora_evidence"] == []
