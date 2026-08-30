"""business_engine.py: public API facade.

As of v22, the actual implementation lives in the business_determination/
package (constants.py, house_evidence.py, jaimini.py, kp.py,
significators.py, sectors.py, timing.py, mode_gate.py, d24_d60_sign.py,
operating_models.py, contradictions.py, scoring.py, engine.py) -- split
out of what was previously a single ~4650-line file, for maintainability.

This module still imports every name (public and underscore-prefixed
internal) from that package into its own namespace with `import *`, so any
EXISTING caller doing an EXPLICIT import -- e.g.
`from Business_Prediction.business_engine import _business_operating_model`,
which is how business_mode_runner.py/generate_business_report.py/the test
suite reach several internal helpers directly -- keeps working exactly as
before; Python does not consult `__all__` for explicit `from module import
name` imports, only for wildcard `from module import *`.

Engineering audit fix #7 ("public API too broad"): `__all__` below,
however, is now a short, curated, documented list of the genuinely public,
intended entry points -- not the ~150-entry union of every internal helper
across all thirteen business_determination submodules that
`from .engine import __all__` used to re-export wholesale. That wholesale
re-export made every underscore-prefixed internal (evidence-weight
constants, house-lord helpers, contradiction-check internals, etc.) look
like part of this module's supported public surface to any caller or
tooling that does `from Business_Prediction.business_engine import *` or
introspects `business_engine.__all__`. If you need one of those internals
for a legitimate reason, import it explicitly by name (as the existing
callers above already do) rather than relying on it being in `__all__`.
"""
from Business_Prediction.business_determination import *  # noqa: F401,F403


def __getattr__(name):
    """Compatibility bridge for explicit legacy imports of private helpers."""
    from importlib import import_module
    modules = (
        "constants", "house_evidence", "jaimini", "kp", "significators", "sectors",
        "timing", "mode_gate", "d24_d60_sign", "operating_models", "contradictions",
        "scoring", "synastry", "yogas", "legal_risk", "transition_timing", "muhurta",
        "ashtakavarga_timing", "engine",
    )
    for module_name in modules:
        module = import_module(f"Business_Prediction.business_determination.{module_name}")
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(name)

__all__ = [
    # Primary entry point.
    "compute_business_prediction",
    # Layer-level entry points a caller may reasonably want standalone
    # (documented, stable result shapes -- see each function's own
    # docstring in business_determination/ for its return schema).
    "compute_business_mode_gate",
    "score_business_significators",
    "rank_business_sectors",
    "rank_business_sectors_with_status",
    "diversify_sector_ranking",
    "sector_score",
    "compute_partnership_synastry",
    "detect_business_yogas",
    "detect_legal_dispute_risk",
    "compute_transition_timing_recommendation",
    "find_business_muhurta",
    "rank_business_years",
    "validate_business_rule_pack",
    # Machine-readable model-maturity/versioning metadata (see MATURITY
    # STATEMENT in engine.py's module docstring for what these mean).
    "MODEL_STATUS",
    "CALIBRATION_STATUS",
    "MATURITY_STATEMENT",
    "MATURITY_CAVEATS",
    "EVIDENCE_BASIS",
    "RULE_PACK_VERSION",
]
