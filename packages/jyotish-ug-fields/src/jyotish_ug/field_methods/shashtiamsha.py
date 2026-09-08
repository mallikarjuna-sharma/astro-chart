"""D60 (Shashtiamsha) field-determination module.

D60 is classically the finest-grained confirmation varga -- used for subtle,
final-word confirmation of what the grosser charts (D1/D9/D24/D10) already
indicate, not as a primary determination technique. Phase-2 remediation
(2026-08): `score_shashtiamsha` is wrapped with a standard-signature adapter
(`score_d60_vote`) and wired into the method bundle as an 8th voting method
at a deliberately small weight (0.05 of the total prior mass) -- a
fine-grained tiebreaker rather than a co-equal vote with D24/Dashamsha.
`independent_vote: False` is retained on the legacy function for callers not
yet migrated; the wrapper below is what the bundle actually calls.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from jyotish.boosts import _d60_deity_quality


# D60 gap-audit fix (2026-08): boundary-risk awareness, ported from the same
# pattern already built for KP cusps / D10 (3-degree segments) / D24 (1.25-
# degree segments). D60 divides each sign into 60 segments of 0.5 degrees --
# the FINEST of every varga this engine uses, and therefore classically the
# most exposed to a birth-time-driven segment flip, even though the deity-
# quality signal it produces is only a small (0.05 prior weight) tiebreaker.
# Rather than discount `quality` itself (a discrete +1/0/-1 signal doesn't
# have a natural "0.85x" partial state), a planet within the margin of a
# 0.5-degree boundary has its confirmation WEIGHT (not its score direction)
# reduced -- so an uncertain deity reading corroborates less rather than
# flipping sign under a birth-time nudge it may not deserve.
def _d60_boundary_discount(payload: Any, planet: str) -> float:
    _birth_prec = (
        getattr(getattr(payload, "calculation_policy", None), "birth_time_precision", None)
        or getattr(payload, "birth_time_precision", "exact") or "exact"
    )
    margin = {"approximate": 0.06, "unknown": 0.15}.get(_birth_prec, 0.0)
    if not planet or margin <= 0.0:
        return 1.0
    pdata = (getattr(payload, "planets_d1", {}) or {}).get(planet, {}) or {}
    try:
        deg = float(pdata.get("degree"))
    except (TypeError, ValueError):
        return 1.0
    deg_in_segment = deg % 0.5
    near_boundary = deg_in_segment <= margin or deg_in_segment >= (0.5 - margin)
    return 0.70 if near_boundary else 1.0


def score_shashtiamsha(payload: Any, field_affinity: Mapping[str, float]) -> dict:
    """Legacy entry point, unchanged."""
    planets = getattr(payload, "planets_d1", {}) or {}
    privileged = [getattr(payload, "h10_lord", ""), getattr(payload, "atmakaraka", ""), getattr(payload, "amatyakaraka", "")]
    candidates = list(dict.fromkeys([p for p in privileged if p] + [p for p, _ in sorted((field_affinity or {}).items(), key=lambda x: -x[1])[:3]]))
    total = weighted = 0.0
    evidence = []
    boundary_flagged = []
    for p in candidates:
        data = planets.get(p) or {}
        sign = data.get("sign")
        if not sign:
            continue
        weight = max(float((field_affinity or {}).get(p, 0)), .15 if p in privileged else 0)
        _bdisc = _d60_boundary_discount(payload, p)
        if _bdisc < 1.0:
            boundary_flagged.append(p)
        weight *= _bdisc
        quality = _d60_deity_quality(p, sign, float(data.get("degree", 0) or 0))
        weighted += weight * quality
        total += weight
        evidence.append({"planet": p, "quality": quality, "weight": round(weight, 4), "dependency_group": "d60_deity_vitality", "role": "CONFIRMATION_ONLY"})
    score = 50.0 if total <= 0 else max(0, min(100, 50 + 50 * weighted / total))
    return {
        "contract_version": "d60-confirmation.v1", "status": "OBSERVED" if total else "MISSING",
        "score": round(score, 2), "independent_vote": False, "evidence_items": evidence,
        "boundary_risk_planets": boundary_flagged,
    }


def score_d60_vote(
    payload_data: Any,
    domain: str = "",
    field_affinity: Mapping[str, float] | None = None,
    field_id: str = "",
    field_entry: Mapping = None,
) -> Dict[str, Any]:
    """Phase-2 remediation: standard-signature adapter around
    `score_shashtiamsha` so it slots into `compute_field_method_bundle`'s
    method_entries loop like the other voting methods.

    Returns a method_result-shaped dict (score already 0-100 native, so
    normalization_cap=100 like sudarshana).
    """
    legacy = score_shashtiamsha(payload_data, field_affinity or {})
    score = float(legacy.get("score") or 50.0)
    status = legacy.get("status", "MISSING")
    trace = [f"D60 deity-quality confirmation over {len(legacy.get('evidence_items', []))} candidate planet(s): score={score}"]
    _boundary_flagged = legacy.get("boundary_risk_planets", [])
    if _boundary_flagged:
        trace.append(
            f"D60 boundary risk: {', '.join(_boundary_flagged)} sit within a 0.5-degree D60 "
            "segment boundary under imprecise birth time -- confirmation weight discounted."
        )
    components = {f"d60_{e['planet']}_quality": round(e["quality"] * e["weight"], 3) for e in legacy.get("evidence_items", [])}
    components["d60_boundary_risk_planets"] = ",".join(_boundary_flagged)
    return {
        "method": "shashtiamsha",
        "score": round(score, 2),
        "normalized_score": round(score, 2),  # already native 0-100
        "raw_signed_score": round(score - 50.0, 2),  # centered so "no evidence" (50) reads as neutral, not positive
        "is_net_negative": score < 50.0 and status == "OBSERVED",
        "calculation_status": "COMPUTED" if status == "OBSERVED" else "MISSING_DATA",
        "trace": trace,
        "components": components,
        "score_rubric": {},
    }
