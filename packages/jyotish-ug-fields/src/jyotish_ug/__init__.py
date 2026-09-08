"""UG career-field determination — 199-branch vocational ranking."""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "EducationAnalysisError",
    "jsonable_copy",
    "run_education_analysis",
    "run_ug_analysis",
    "__version__",
]

_RUNNER_EXPORTS = frozenset(__all__) - {"__version__"}


def __getattr__(name: str):
    if name in _RUNNER_EXPORTS:
        from jyotish_ug.runner import (
            EducationAnalysisError,
            jsonable_copy,
            run_education_analysis,
            run_ug_analysis,
        )

        return {
            "EducationAnalysisError": EducationAnalysisError,
            "jsonable_copy": jsonable_copy,
            "run_education_analysis": run_education_analysis,
            "run_ug_analysis": run_ug_analysis,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
