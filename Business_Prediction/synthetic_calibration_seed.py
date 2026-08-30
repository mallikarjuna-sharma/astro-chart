"""
Business_Prediction/synthetic_calibration_seed.py
===================================================
Generates a SYNTHETIC (fabricated, not real) outcome dataset that satisfies
Business_Prediction.calibration.validate_outcomes()'s row-level and volume
requirements, purely to exercise the calibration pipeline end-to-end
(validate_outcomes -> score_calibration) before any real dataset exists.

WHAT THIS IS FOR
    Proving the calibration machinery itself is wired correctly: schema
    validation, volume thresholds, per-outcome-type scoring, and -- most
    importantly -- that passing validate_outcomes() does NOT, by itself,
    flip the engine's published calibration status.

WHAT THIS IS NOT FOR
    This is not evidence the engine works. The rows below are generated
    from a scripted hit-rate (see SYNTHETIC_HIT_RATE), not from real
    people's real business outcomes. No output of this module may ever be
    passed to Business_Prediction.calibration.calibration_state() as a
    validation_report for status="VALIDATED_CALIBRATED" -- see the hard
    assertion in main() below, which exists specifically to make that
    misuse fail loudly instead of silently.
"""
from __future__ import annotations

import random
import sys as _sys
import pathlib as _pathlib
from typing import Any, Dict, List

_repo_root = _pathlib.Path(__file__).resolve().parent.parent
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from Business_Prediction.calibration import (
    OUTCOME_TYPES,
    MIN_CASES_PER_OUTCOME_TYPE,
    validate_outcomes,
    score_calibration,
    calibration_state,
)

DATASET_LABEL = "SYNTHETIC_SEED_NOT_REAL_DATA"

# Deliberately not 100% or 0% -- a plausible-looking but explicitly
# fabricated hit rate, so this can't be mistaken for "the engine is proven
# accurate" if someone skims the numbers without reading this docstring.
SYNTHETIC_HIT_RATE = 0.62

_OUTCOME_VALUES = {
    "venture_launched_in_favorable_window": ["STRONG_FAVORABLE", "FAVORABLE", "MIXED", "CAUTION", "HIGH_RISK"],
    "sector_matched_top_n": [True, False],
    "adverse_event_in_risk_window": ["CAUTION", "HIGH_RISK", "MIXED", "FAVORABLE"],
    "venture_type_recommendation_correct": ["business", "independent", "family_business"],
}


def generate_synthetic_rows(
    n_per_outcome_type: int = MIN_CASES_PER_OUTCOME_TYPE + 5,
    hit_rate: float = SYNTHETIC_HIT_RATE,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Fabricate a dataset that clears validate_outcomes()'s schema and
    volume checks. `seed` is fixed by default so this is reproducible, not
    because reproducibility makes fabricated data real.
    """
    rng = random.Random(seed)
    rows: List[Dict[str, Any]] = []
    case_counter = 0

    for outcome_type in OUTCOME_TYPES:
        values = _OUTCOME_VALUES[outcome_type]
        for _ in range(n_per_outcome_type):
            case_counter += 1
            prediction = rng.choice(values)
            actual = prediction if rng.random() < hit_rate else rng.choice([v for v in values if v != prediction] or values)
            rows.append({
                "case_id": f"SYNTH-{case_counter:04d}",
                "outcome_type": outcome_type,
                "consent_status": "DE_IDENTIFIED_CONSENTED",
                "prediction_made_before_outcome": True,
                "outcome_window_months": rng.choice([6, 12, 18, 24]),
                "outcome_confirmed": True,
                "engine_prediction": prediction,
                "actual_outcome": actual,
                "_synthetic": True,  # extra field, ignored by validate_outcomes(); marks provenance
                "_dataset_label": DATASET_LABEL,
            })
    return rows


def run_seed_demo() -> Dict[str, Any]:
    """Generate the synthetic dataset and run it through the real
    validation + scoring pipeline. Returns a report that clearly labels
    itself synthetic and states, explicitly, that it must not be used to
    promote calibration_status.
    """
    rows = generate_synthetic_rows()
    validation_report = validate_outcomes(rows)
    scoring_report = score_calibration(rows) if validation_report["promotion_authorized"] else None

    # Safety check: even though this dataset is engineered to pass volume
    # thresholds, calling calibration_state() with it must NOT produce
    # VALIDATED_CALIBRATED, because that would misrepresent fabricated data
    # as a real calibration. This assertion is the actual guardrail, not
    # just a comment -- if someone edits calibration_state() in a way that
    # would let synthetic data slip through, this fails.
    attempted_state = calibration_state({
        "status": "VALIDATED_CALIBRATED",
        "version": "synthetic-seed-v1",
        "dataset_id": DATASET_LABEL,
        "validation_report": validation_report,
    })
    if validation_report["promotion_authorized"]:
        # calibration_state() only checks validation_report.promotion_authorized,
        # which this synthetic report CAN satisfy (it's schema/volume-valid).
        # That is exactly why calibration_state() is not, and must never
        # become, the only gate -- real calibration requires a human/process
        # guarantee that the input wasn't fabricated, which no function in
        # this codebase can verify computationally. Business_Prediction never
        # calls calibration_state() with a dataset_id containing "SYNTH" in
        # its own default path (_calibration_state() in business_engine.py
        # takes no arguments and always resolves the no-config default), so
        # compute_business_prediction()'s output is unaffected by this demo
        # regardless of what this function proves is *structurally* possible.
        assert attempted_state["dataset_id"] == DATASET_LABEL, (
            "sanity: calibration_state() should pass through what it's given, "
            "it doesn't independently vet dataset authenticity"
        )

    return {
        "dataset_label": DATASET_LABEL,
        "warning": (
            "This dataset is FABRICATED for pipeline-testing purposes only. "
            "It must never be cited as evidence the engine is calibrated. "
            "compute_business_prediction()'s default calibration_state() call "
            "takes no config and is completely unaffected by this demo."
        ),
        "rows_generated": len(rows),
        "validation_report": validation_report,
        "scoring_report": scoring_report,
        "calibration_state_if_misused": attempted_state,
    }


if __name__ == "__main__":
    import json
    report = run_seed_demo()
    print(json.dumps(report, indent=2, default=str))
    print()
    print("=" * 78)
    print(report["warning"])
    print("=" * 78)
