"""Versioned operational thresholds for the business engine.

This module is the single release artifact for decision cutoffs.  The values
remain engineered and uncalibrated; centralization makes drift inspectable.
"""
from dataclasses import asdict, dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class DecisionPolicy:
    version: str = "business-decision-policy.v3"
    max_forecast_years: int = 50
    comparative_margin: float = 8.0
    hybrid_min_score: float = 30.0
    minimum_actionable_promise: float = 40.0
    minimum_operational_execution: float = 35.0
    minimum_business_stability: float = 35.0
    absolute_proceed_gate_floor: float = 40.0
    absolute_proceed_strength_floor: float = 35.0
    high_tier_gate_floor: float = 60.0
    high_tier_strength_floor: float = 55.0
    high_tier_margin_floor: float = 20.0
    high_margin: float = 20.0
    strong_business_margin: float = 15.0
    moderate_business_margin: float = 8.0
    slight_business_margin: float = 3.0
    hybrid_job_boundary: float = -2.0
    slight_job_boundary: float = -7.0
    moderate_job_boundary: float = -14.0
    strong_business_absolute_floor: float = 65.0
    strong_business_floor_margin: float = 12.0
    transition_readiness_floor: float = 50.0
    d24_competency_factor_floor: float = 0.9
    contradiction_transition_floor: float = 15.0
    birth_time_transition_downgrade_minutes: float = 10.0
    profit_retention_floor: float = 45.0
    stability_floor: float = 45.0
    d2_capital_net_floor: float = -2.0
    d60_max_uncertainty_minutes: float = 1.0
    house_strength_strong_cutoff: float = 0.60
    house_strength_moderate_cutoff: float = 0.35
    kp_positive_override_floor: float = 10.0
    kp_negative_override_ceiling: float = -8.0
    shadbala_strong_ratio: float = 1.15
    shadbala_weak_ratio: float = 0.85
    diagnostic_strong_recommendation_cap: str = "PILOT_WHILE_RETAINING_INCOME"
    timing_labels: Tuple[Tuple[float, str], ...] = (
        (25.0, "STRONG_FAVORABLE"),
        (10.0, "FAVORABLE"),
        (-10.0, "MIXED"),
        (-25.0, "CAUTION"),
    )

    def manifest(self) -> Dict[str, object]:
        return asdict(self)


DECISION_POLICY = DecisionPolicy()

__all__ = ["DecisionPolicy", "DECISION_POLICY"]
