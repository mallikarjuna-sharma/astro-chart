"""Smoke tests for Business_Prediction.calibration -- the governance layer
that must keep the engine at ENGINEERED_PROVISIONAL until a real, passing
outcome dataset is supplied.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.calibration import (
    OUTCOME_TYPES,
    validate_outcomes,
    score_calibration,
    calibration_state,
)


def test_empty_dataset_is_insufficient():
    report = validate_outcomes([])
    assert report["promotion_authorized"] is False
    assert report["valid_rows"] == 0


def test_backfilled_prediction_rejected():
    rows = [{
        "case_id": "c1",
        "outcome_type": "venture_launched_in_favorable_window",
        "consent_status": "DE_IDENTIFIED_CONSENTED",
        "prediction_made_before_outcome": False,  # backfilled -- must be rejected
        "outcome_window_months": 12,
        "outcome_confirmed": True,
        "engine_prediction": "FAVORABLE",
        "actual_outcome": "FAVORABLE",
    }]
    report = validate_outcomes(rows)
    assert report["promotion_authorized"] is False
    assert any("prediction_made_before_outcome" in e for e in report["errors"])


def test_valid_row_passes_row_level_checks_but_not_volume():
    rows = [{
        "case_id": "c1",
        "outcome_type": "venture_launched_in_favorable_window",
        "consent_status": "DE_IDENTIFIED_CONSENTED",
        "prediction_made_before_outcome": True,
        "outcome_window_months": 12,
        "outcome_confirmed": True,
        "engine_prediction": "FAVORABLE",
        "actual_outcome": "FAVORABLE",
    }]
    report = validate_outcomes(rows)
    assert report["valid_rows"] == 1
    assert report["promotion_authorized"] is False  # single case, below MIN_TOTAL_CASES


def test_score_calibration_reports_per_outcome_type_not_blended():
    rows = [
        {"outcome_type": "venture_launched_in_favorable_window", "engine_prediction": "FAVORABLE", "actual_outcome": "FAVORABLE"},
        {"outcome_type": "venture_launched_in_favorable_window", "engine_prediction": "FAVORABLE", "actual_outcome": "MIXED"},
        {"outcome_type": "sector_matched_top_n", "engine_prediction": True, "actual_outcome": True},
    ]
    report = score_calibration(rows)
    assert set(report["by_outcome_type"]) == set(OUTCOME_TYPES)
    assert report["by_outcome_type"]["venture_launched_in_favorable_window"]["hit_rate"] == 0.5
    assert report["by_outcome_type"]["sector_matched_top_n"]["hit_rate"] == 1.0
    assert report["by_outcome_type"]["adverse_event_in_risk_window"]["n"] == 0


def test_calibration_state_cannot_be_forced_to_calibrated_without_report():
    state = calibration_state({"status": "VALIDATED_CALIBRATED"})  # no validation_report attached
    assert state["status"] == "ENGINEERED_PROVISIONAL"

    state_with_bad_report = calibration_state({
        "status": "VALIDATED_CALIBRATED",
        "validation_report": {"promotion_authorized": False},
    })
    assert state_with_bad_report["status"] == "ENGINEERED_PROVISIONAL"

    state_with_good_report = calibration_state({
        "status": "VALIDATED_CALIBRATED",
        "validation_report": {"promotion_authorized": True},
    })
    assert state_with_good_report["status"] == "VALIDATED_CALIBRATED"


def test_default_state_is_provisional():
    assert calibration_state()["status"] == "ENGINEERED_PROVISIONAL"


def test_synthetic_seed_clears_pipeline_but_engine_default_stays_provisional():
    """The synthetic seed dataset must clear validate_outcomes() (proving the
    calibration pipeline itself works end-to-end) while
    compute_business_prediction()'s DEFAULT calibration_state() call --
    which takes no config -- must remain completely unaffected. This is the
    actual safety property: fabricated data clearing volume/schema checks
    must never leak into the engine's real, default-path output.
    """
    from Business_Prediction.synthetic_calibration_seed import run_seed_demo
    from Business_Prediction.business_engine import compute_business_prediction

    seed_report = run_seed_demo()
    assert seed_report["validation_report"]["promotion_authorized"] is True
    assert seed_report["calibration_state_if_misused"]["status"] == "VALIDATED_CALIBRATED"

    class _MinimalPayload:
        dob = "1990-01-01"
        planet_house: dict = {}
        house_lords: dict = {}
        planet_dignities: dict = {}
        sav_points_houses: dict = {}
        darakaraka = ""
        dasha_sequence: list = []
        lagna_sign = ""
        planet_signs: dict = {}

    result = compute_business_prediction(_MinimalPayload())
    assert result["calibration_state"]["status"] == "ENGINEERED_PROVISIONAL"
    assert result["calibration_status"] == "NOT_CALIBRATED_NO_BACKTEST_NO_LABELED_OUTCOMES"


if __name__ == "__main__":
    test_empty_dataset_is_insufficient()
    test_backfilled_prediction_rejected()
    test_valid_row_passes_row_level_checks_but_not_volume()
    test_score_calibration_reports_per_outcome_type_not_blended()
    test_calibration_state_cannot_be_forced_to_calibrated_without_report()
    test_default_state_is_provisional()
    test_synthetic_seed_clears_pipeline_but_engine_default_stays_provisional()
    print("All Business_Prediction calibration tests passed.")
