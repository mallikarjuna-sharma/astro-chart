"""PUC stream determination — Science / Commerce / Humanities."""

from jyotish_puc.runner import (
    PUC_DEFAULT_AGE_FLOORS,
    PUC_MAX_AGE_EXCLUSIVE,
    PucAnalysisError,
    default_education_tab,
    is_puc_eligible,
    puc_age_error_message,
    run_puc_analysis,
)

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
