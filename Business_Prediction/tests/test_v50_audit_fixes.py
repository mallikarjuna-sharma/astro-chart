from contextvars import copy_context
from datetime import date
from types import SimpleNamespace

from Business_Prediction.business_determination.constants import (
    RULE_PACK_VERSION,
    _get_diagnostics,
    _record_diagnostic,
    _reset_diagnostics,
)
from Business_Prediction.business_determination.d24_d60_sign import _d60_confirmation_status
from Business_Prediction.business_determination.timing import _chara_dasha_method_status


def test_rule_pack_version_tracks_post_v49_behavior():
    assert RULE_PACK_VERSION == "business-engine.v52"


def test_diagnostics_are_isolated_between_execution_contexts():
    first, second = copy_context(), copy_context()

    def populate(label):
        _reset_diagnostics()
        _record_diagnostic(label, ValueError(label))

    first.run(populate, "first")
    second.run(populate, "second")
    assert first.run(_get_diagnostics)[0]["module"] == "first"
    assert second.run(_get_diagnostics)[0]["module"] == "second"


def test_chara_status_uses_dob_and_reports_integrated_md_ad(monkeypatch):
    captured = {}

    def fake_calendar(lagna, planets, dob):
        captured["dob"] = dob
        return [{"sign": "Aries", "antardashas": [{"sign": "Taurus"}]}]

    monkeypatch.setattr("jyotish.astro.compute_chara_dasha_calendar", fake_calendar)
    payload = SimpleNamespace(dob="1990-02-03", lagna_sign="Aries", planets_d1={"Mars": {"sign": "Aries"}})
    status = _chara_dasha_method_status(payload)

    assert captured["dob"] == date(1990, 2, 3)
    assert status["status"] == "IMPLEMENTED_MD_AD_ADDITIVE_CORROBORATION"
    assert status["timing_window_activation"] == "WIRED_ADDITIVE_ONLY_INTO_VIMSHOTTARI_MD_AD_WINDOWS"


def test_d60_canonical_uncertainty_overrides_optimistic_legacy_string():
    payload = SimpleNamespace(
        d60_planet_dignities={"Saturn": "OWN"},
        house_lords={"10": "Saturn"},
        birth_time_uncertainty_minutes=15,
        birth_time_reliability="HIGH",
    )
    status = _d60_confirmation_status(payload)
    assert status["status"] == "NOT_APPLIED_LOW_RELIABILITY"
    assert status["modifier"] == 0.0
    assert status["reliability_source"] == "birth_time_uncertainty_minutes"


def test_d60_zero_uncertainty_does_not_require_legacy_string():
    payload = SimpleNamespace(
        d60_planet_dignities={"Saturn": "OWN"},
        house_lords={"10": "Saturn"},
        birth_time_uncertainty_minutes=0,
    )
    status = _d60_confirmation_status(payload)
    assert status["status"] == "OK"
    assert status["modifier"] == 0.04
    assert status["reliability_source"] == "birth_time_uncertainty_minutes"
