"""Machine-readable certification blockers and bounded method limitations."""
from copy import deepcopy

_CAPABILITY_STATUS = {
    "certification_status": "NOT_CERTIFIED_EXPERIMENTAL_DECISION_SUPPORT",
    "external_blockers": [
        {"id": "INDEPENDENT_GOLDEN_CALCULATOR_CORPUS", "status": "BLOCKED_NO_EXTERNAL_FIXTURES"},
        {"id": "REAL_LABELED_BUSINESS_OUTCOMES", "status": "BLOCKED_NO_CONSENTED_CORPUS"},
        {"id": "SECTOR_OUTCOME_CALIBRATION", "status": "BLOCKED_NO_LABELED_SECTOR_OUTCOMES"},
        {"id": "SOURCE_EDITION_RULE_CITATIONS", "status": "BLOCKED_NO_VERIFIED_SOURCE_CORPUS"},
    ],
    "doctrine_decisions_required": [
        {"id": "ALTERNATIVE_CHARA_DASHA_SCHOOLS", "status": "ONE_ENGINEERED_CONVENTION_ONLY"},
        {"id": "KP_RETROGRADE_AND_EVENT_PRECEDENCE", "status": "ENGINEERED_POLICY_ONLY"},
    ],
    "implemented_with_bounded_scope": [
        {"id": "D11", "scope": "HARMONIC_11_OPTIONAL_GAINS_CORROBORATION_NON_SHODASHAVARGA"},
        {"id": "D60", "scope": "D1_TENTH_LORD_DIGNITY_CORROBORATION_ONLY"},
        {"id": "D24", "scope": "HOUSE_GRAPH_ONE_HOP_DISPOSITORS_NO_VIDYA_YOGA_REGISTRY"},
        {"id": "CHARA_TIMING", "scope": "MD_AD_OVERLAP_SMALL_DIGNITY_CORROBORATION"},
        {"id": "KP", "scope": "CUSP_CHAIN_VERIFIED_UPSTREAM_SIGNIFICATORS_NOT_FULLY_REBUILT"},
        {"id": "BIRTH_TIME_SENSITIVITY", "scope": "METADATA_AND_BOUNDARY_PROXY_NO_CHART_REGENERATION"},
        {"id": "TRANSITS", "scope": "MIDPOINT_WHOLE_SIGN_WITH_MEAN_MOTION_FALLBACK"},
        {"id": "EVENT_TIMING", "scope": "LORDSHIP_DIGNITY_OVERLAY_NOT_FULL_EVENT_SYNTHESIS"},
        {"id": "MUHURTA_ASHTAKAVARGA", "scope": "OPTIONAL_ADVISORY_NOT_MANDATORY_GATE"},
        {"id": "LEGAL_RISK", "scope": "HEURISTIC_SCREEN_NOT_LEGAL_PREDICTION"},
        {"id": "PARTNERSHIP", "scope": "ASTROLOGICAL_COMPATIBILITY_NOT_GOVERNANCE_DUE_DILIGENCE"},
    ],
}


def capability_status():
    return deepcopy(_CAPABILITY_STATUS)


__all__ = ["capability_status"]
