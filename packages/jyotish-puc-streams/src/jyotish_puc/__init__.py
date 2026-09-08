"""PUC stream determination — Science / Commerce / Humanities."""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "PUC_DEFAULT_AGE_FLOORS",
    "PUC_MAX_AGE_EXCLUSIVE",
    "PucAnalysisError",
    "default_education_tab",
    "is_puc_eligible",
    "puc_age_error_message",
    "run_puc_analysis",
    "__version__",
]

_RUNNER_EXPORTS = frozenset(__all__) - {"__version__"}


def __getattr__(name: str):
    if name in _RUNNER_EXPORTS:
        from jyotish_puc.runner import (
            PUC_DEFAULT_AGE_FLOORS,
            PUC_MAX_AGE_EXCLUSIVE,
            PucAnalysisError,
            default_education_tab,
            is_puc_eligible,
            puc_age_error_message,
            run_puc_analysis,
        )

        return {
            "PUC_DEFAULT_AGE_FLOORS": PUC_DEFAULT_AGE_FLOORS,
            "PUC_MAX_AGE_EXCLUSIVE": PUC_MAX_AGE_EXCLUSIVE,
            "PucAnalysisError": PucAnalysisError,
            "default_education_tab": default_education_tab,
            "is_puc_eligible": is_puc_eligible,
            "puc_age_error_message": puc_age_error_message,
            "run_puc_analysis": run_puc_analysis,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
