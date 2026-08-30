"""Governed calibration metadata and dataset validation for the Business
Prediction engine.

Mirrors Stream_Determination/calibration.py's governance model: this module
deliberately never invents labels, silently tunes weights, or lets the
engine claim calibration without a passing validation report. A calibration
is publishable only when the input contains consent/provenance, an outcome
type, an outcome measured after the prediction was made (not backfilled),
and enough independent cases per outcome type.

Until a real dataset clears validate_outcomes(), Business_Prediction must
remain status="ENGINEERED_PROVISIONAL" — this is enforced by
calibration_state(), not just documented. See business_engine.py's
CALIBRATION_STATUS constant, which every prediction output carries.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List

# Outcome types a labeled case can be scored against. Each maps to one of
# the engine's four output surfaces (mode gate, sector ranking, timed
# window, recommendation tier) so calibration can be measured per surface
# rather than as one undifferentiated "was it right" number.
OUTCOME_TYPES = (
    "venture_launched_in_favorable_window",   # did a real venture launch fall inside a FAVORABLE/STRONG_FAVORABLE window?
    "sector_matched_top_n",                   # did the person's actual business sector appear in top_sectors?
    "adverse_event_in_risk_window",            # did a documented loss/partnership-breakdown event fall inside a CAUTION/HIGH_RISK window?
    "venture_type_recommendation_correct",     # did the recommended venture_type (business/independent/family_business) match what the person actually pursued?
)

MIN_CASES_PER_OUTCOME_TYPE = 30
MIN_TOTAL_CASES = 100
CALIBRATION_SCHEMA_VERSION = "business-calibration.v1"


def validate_outcomes(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a candidate outcome dataset. Returns a report; never mutates
    engine behavior itself -- calibration_state() is the only thing that
    can flip the engine's published status, and only when handed a
    passing report explicitly.
    """
    rows = list(rows)
    errors: List[str] = []
    valid: List[Dict[str, Any]] = []
    seen_ids = set()

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {i}: must be an object")
            continue
        case_id = row.get("case_id")
        if not case_id or case_id in seen_ids:
            errors.append(f"row {i}: case_id is missing or duplicated")
            continue
        seen_ids.add(case_id)

        outcome_type = row.get("outcome_type")
        if outcome_type not in OUTCOME_TYPES:
            errors.append(f"row {i}: outcome_type must be one of {OUTCOME_TYPES}")
            continue

        if row.get("consent_status") != "DE_IDENTIFIED_CONSENTED":
            errors.append(f"row {i}: consent_status must be DE_IDENTIFIED_CONSENTED")
            continue

        if row.get("prediction_made_before_outcome") is not True:
            # Calibration on backfilled/after-the-fact predictions is not
            # calibration -- it's curve-fitting to known answers. The engine
            # must have produced its prediction (recorded with a timestamp
            # or run_manifest id) strictly before the outcome was known.
            errors.append(f"row {i}: prediction_made_before_outcome must be true (no backfilled predictions)")
            continue

        try:
            window = float(row.get("outcome_window_months"))
        except (TypeError, ValueError):
            window = float("nan")
        if not math.isfinite(window) or window <= 0:
            errors.append(f"row {i}: outcome_window_months must be positive")
            continue

        if row.get("outcome_confirmed") is not True:
            errors.append(f"row {i}: outcome_confirmed must be true")
            continue

        if "engine_prediction" not in row or "actual_outcome" not in row:
            errors.append(f"row {i}: must carry both engine_prediction and actual_outcome for scoring")
            continue

        valid.append(row)

    counts = Counter(r["outcome_type"] for r in valid)
    sufficient = len(valid) >= MIN_TOTAL_CASES and all(
        counts.get(t, 0) >= MIN_CASES_PER_OUTCOME_TYPE for t in OUTCOME_TYPES
    )
    if not sufficient:
        errors.append(
            f"insufficient independent cases: total={len(valid)}, counts={dict(counts)}; "
            f"need total>={MIN_TOTAL_CASES} and each outcome_type>={MIN_CASES_PER_OUTCOME_TYPE}"
        )

    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "valid_rows": len(valid),
        "outcome_type_counts": dict(counts),
        "errors": errors,
        "promotion_authorized": not errors,
    }


def score_calibration(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute accuracy/precision per outcome_type over an already-validated
    dataset (call validate_outcomes() first and only proceed if
    promotion_authorized). Returns per-type hit-rate; does NOT compute a
    single blended "accuracy" number, since the four outcome types measure
    different engine surfaces and blending them would hide which surface
    (mode gate vs sector ranking vs timing vs recommendation) is actually
    working.
    """
    rows = list(rows)
    by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in OUTCOME_TYPES}
    for row in rows:
        t = row.get("outcome_type")
        if t in by_type:
            by_type[t].append(row)

    report: Dict[str, Any] = {"schema_version": CALIBRATION_SCHEMA_VERSION, "by_outcome_type": {}}
    for outcome_type, cases in by_type.items():
        if not cases:
            report["by_outcome_type"][outcome_type] = {"n": 0, "hit_rate": None}
            continue
        hits = sum(1 for c in cases if c.get("engine_prediction") == c.get("actual_outcome"))
        report["by_outcome_type"][outcome_type] = {
            "n": len(cases),
            "hits": hits,
            "hit_rate": round(hits / len(cases), 4),
        }
    return report


def calibration_state(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """The single source of truth for whether Business_Prediction is allowed
    to describe itself as calibrated. Mirrors
    Stream_Determination.calibration.calibration_state(): status can only
    read VALIDATED_CALIBRATED if a passing validation_report is attached --
    any other combination is force-downgraded to ENGINEERED_PROVISIONAL.

    No config has ever been passed with a passing validation_report as of
    this writing (rule_pack business-engine.v4), so
    business_engine.CALIBRATION_STATUS remains
    NOT_CALIBRATED_NO_BACKTEST_NO_LABELED_OUTCOMES until real outcome data
    clears validate_outcomes() and score_calibration() is reviewed.

    KNOWN LIMITATION: this function trusts the validation_report it is
    given -- it checks promotion_authorized, not whether the underlying
    rows were fabricated. validate_outcomes() enforces schema/consent/
    volume, not authenticity of the outcomes themselves; nothing in this
    module can computationally distinguish a real de-identified outcome
    from a synthetic one shaped to pass the same checks (see
    Business_Prediction/synthetic_calibration_seed.py, which deliberately
    demonstrates this and explains why it therefore never wires its own
    output into a live calibration_state() call). The actual safety
    boundary is procedural: nothing in business_engine.py's default
    _calibration_state() call ever passes a config, so real promotion can
    only happen via a deliberate, reviewable code change -- not silently.
    """
    config = config or {}
    status = config.get("status", "ENGINEERED_PROVISIONAL")
    validation_report = config.get("validation_report")
    if status == "VALIDATED_CALIBRATED" and not (validation_report and validation_report.get("promotion_authorized")):
        status = "ENGINEERED_PROVISIONAL"
    return {
        "status": status,
        "version": config.get("version", "unvalidated"),
        "dataset_id": config.get("dataset_id"),
        "validation_report": validation_report,
        "note": (
            "Weights are outcome-calibrated only when status is "
            "VALIDATED_CALIBRATED and a passing validation_report (from "
            "validate_outcomes()) is attached."
        ),
    }
