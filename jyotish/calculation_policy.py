"""Immutable calculation conventions shared by every engine stage.

This object is deliberately descriptive: calculations must either use these
conventions or declare a degraded/fallback identity.  It prevents individual
modules from silently choosing incompatible node, house or year-length rules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class CalculationPolicy:
    version: str = "jyotish-calculation-policy.2026-07-18.v1"
    ephemeris: str = "Skyfield DE421"
    ayanamsha: str = "KRISHNAMURTI"
    node_type: str = "TRUE_NODE"
    natal_house_system: str = "WHOLE_SIGN"
    kp_house_system: str = "PLACIDUS"
    tajika_house_system: str = "WHOLE_SIGN"
    aspect_convention: str = "PARASHARI_GRAHA_DRISHTI"
    dasha_year_days: float = 365.2425
    sunrise_rule: str = "LOCAL_APPARENT_SUNRISE"
    varga_boundary_rule: str = "HALF_OPEN_LEFT_CLOSED"
    enable_parashari: bool = True
    enable_jaimini: bool = True
    enable_kp: bool = True
    enable_tajika: bool = True
    enable_modern_heuristics: bool = True
    birth_time_precision: str = "unknown"
    birth_time_uncertainty_minutes: int = 0

    @property
    def precise_cusps_allowed(self) -> bool:
        return self.birth_time_precision == "exact" and self.birth_time_uncertainty_minutes <= 2

    @property
    def d60_claims_allowed(self) -> bool:
        return self.birth_time_precision == "exact" and self.birth_time_uncertainty_minutes <= 2

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["house_system_by_method"] = {
            "natal_parashari": self.natal_house_system,
            "kp": self.kp_house_system,
            "tajika": self.tajika_house_system,
        }
        value["precision_permissions"] = {
            "precise_cusps_allowed": self.precise_cusps_allowed,
            "d60_claims_allowed": self.d60_claims_allowed,
        }
        value["school_toggles"] = {
            "parashari": self.enable_parashari,
            "jaimini": self.enable_jaimini,
            "kp": self.enable_kp,
            "tajika": self.enable_tajika,
            "modern_heuristics": self.enable_modern_heuristics,
        }
        return value


def build_calculation_policy(payload: Any) -> CalculationPolicy:
    """Build exactly one normalized policy for a run."""
    supplied = getattr(payload, "calculation_policy", None)
    base = CalculationPolicy(
        birth_time_precision=str(getattr(payload, "birth_time_precision", "unknown") or "unknown").lower(),
        birth_time_uncertainty_minutes=max(
            0, int(getattr(payload, "birth_time_uncertainty_minutes", 0) or 0)
        ),
    )
    if isinstance(supplied, CalculationPolicy):
        return supplied
    if isinstance(supplied, Mapping):
        allowed = {k: v for k, v in supplied.items() if k in CalculationPolicy.__dataclass_fields__}
        return replace(base, **allowed)
    return base


def policy_for(payload: Any) -> CalculationPolicy:
    policy = getattr(payload, "calculation_policy", None)
    if not isinstance(policy, CalculationPolicy):
        raise RuntimeError("CalculationPolicy was not initialized at the engine boundary")
    return policy
