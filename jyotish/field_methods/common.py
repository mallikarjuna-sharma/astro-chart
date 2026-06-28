"""Shared helpers for separated field-determination astrology modules."""
from __future__ import annotations

import math as _math
from typing import Any, Dict, List


FIELD_PRIORITY_GROUPS: Dict[str, List[str]] = {
    "life_science": [
        "medicine_mbbs",
        "medical_research",
        "clinical_psychology",
        "neuroscience",
        "psychiatry",
        "public_health",
        "bioinformatics",
        "biotechnology_bsc",
        "molecular_biology_genetics",
        "healthcare_management",
        "pharmacy",
    ],
    "space_aerospace": [
        "aerospace_engineering",
        "space_systems_engineering",
        "rocket_propulsion",
        "satellite_engineering",
        "astronautical_engineering",
        "space_sciences_engineering",
        "space_materials",
        "earth_observation_remote_sensing",
        "planetary_science",
        "astronomy_astrophysics",
    ],
}

METHOD_SCORE_CAP: float = 30.0
DEFAULT_RUBRIC_CAPS: Dict[str, float] = {
    "core": 40.0,
    "support": 25.0,
    "validation": 20.0,
    "penalty": 20.0,
}


def clamp_score(value: float) -> float:
    """Soft-clamp using tanh compression above 80.

    Below 80 the function is identity (rank order fully preserved).
    Above 80 it uses tanh to smoothly compress toward 100 without hard-ceiling,
    so five fields that all 'score 100' retain their relative rank differences.
    Mapping reference: 80->80, 100->95.2, 120->99.3, inf->100.
    """
    try:
        x = float(value)
        if x <= 0.0:
            return 0.0
        if x <= 80.0:
            return x
        return 80.0 + 20.0 * _math.tanh((x - 80.0) / 20.0)
    except (TypeError, ValueError):
        return 0.0


def normalize_method_score(value: float, cap: float = METHOD_SCORE_CAP) -> float:
    """Map a raw method score onto a shared 0-100 scale.

    The shared cap keeps KNRao, KP, Jaimini, and Parashara comparable before
    weights are applied. Scores above the cap saturate at 100.
    """
    try:
        raw = clamp_score(value)
        cap_v = float(cap) if cap and cap > 0 else METHOD_SCORE_CAP
        return round(max(0.0, min(100.0, (raw / cap_v) * 100.0)), 2)
    except (TypeError, ValueError):
        return 0.0


def top_weighted_planets(field_affinity: Dict[str, float], limit: int = 3) -> List[str]:
    if not field_affinity:
        return []
    return [p for p, _ in sorted(field_affinity.items(), key=lambda x: -x[1])[:limit]]


def rubric_section(
    section: str,
    actual: float,
    cap: float,
    *,
    kind: str = "positive",
    note: str = "",
    items: List[str] | None = None,
) -> Dict[str, Any]:
    """Create a standardized display band for side-by-side method comparison."""
    cap_v = max(0.0, float(cap))
    actual_v = round(float(actual), 2)
    if kind == "penalty":
        display_v = -min(cap_v, abs(actual_v)) if actual_v < 0 else 0.0
    else:
        display_v = min(cap_v, max(0.0, actual_v))
    return {
        "section": section,
        "kind": kind,
        "actual": actual_v,
        "display": round(display_v, 2),
        "cap": round(cap_v, 2),
        "note": note,
        "items": items or [],
    }


def build_score_rubric(method: str, sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Package a comparable rubric for each scoring method."""
    actual_total = round(sum(float(s.get("actual", 0.0)) for s in sections), 2)
    display_total = round(sum(float(s.get("display", 0.0)) for s in sections), 2)
    return {
        "method": method,
        "sections": sections,
        "actual_total": actual_total,
        "display_total": display_total,
    }


def method_result(
    name: str,
    score: float,
    trace: List[str],
    components: Dict[str, float] | None = None,
    *,
    rubric: Dict[str, Any] | None = None,
    normalization_cap: float | None = None,
) -> Dict[str, Any]:
    return {
        "method": name,
        "score": round(clamp_score(score), 2),
        "normalized_score": normalize_method_score(score, normalization_cap or METHOD_SCORE_CAP),
        "trace": trace,
        "components": components or {},
        "score_rubric": rubric or {},
    }


def combine_weighted_scores(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    """Return the weighted average of already comparable scores."""
    total_weight = sum(weights.values()) or 1.0
    return sum(float(scores.get(k, 0.0)) * w for k, w in weights.items()) / total_weight


def build_method_context(payload_data: Any) -> Dict[str, Any]:
    """Normalize the payload once so each astrology method can stay isolated."""
    return {
        "planets_d1": getattr(payload_data, "planets_d1", {}) or {},
        "house_lords": getattr(payload_data, "house_lords", {}) or {},
        "d9_chart": getattr(getattr(payload_data, "divisional_charts", {}), "get", lambda *_: {})("D9_navamsha", {}) or {},
        "d10_chart": getattr(getattr(payload_data, "divisional_charts", {}), "get", lambda *_: {})("D10_dashamsha", {}) or {},
        "eff_strengths": getattr(payload_data, "eff_strengths", {}) or {},
        "kp_cusps": getattr(payload_data, "kp_cusps", {}) or {},
        "shadbala": getattr(payload_data, "shadbala", {}) or {},
        "planet_dignities": getattr(payload_data, "planet_dignities", {}) or {},
        "planet_house": getattr(payload_data, "planet_house", {}) or {},
        "lagna_sign": getattr(payload_data, "lagna_sign", "") or "",
        "lagna_lord": getattr(payload_data, "lagna_lord", "") or "",
        "h10_lord": getattr(payload_data, "h10_lord", "") or "",
        "karakamsha": getattr(payload_data, "karakamsha", "") or "",
        "brahma_lord": getattr(payload_data, "brahma_lord", "") or "",
        "maheshwara_lord": getattr(payload_data, "maheshwara_lord", "") or "",
        "upapada": getattr(payload_data, "upapada", "") or "",
        "upapada_lagna": getattr(payload_data, "upapada_lagna", "") or "",
        "atmakaraka": getattr(payload_data, "atmakaraka", "") or "",
        "amatyakaraka": getattr(payload_data, "amatyakaraka", "") or "",
        "d10_strength": getattr(payload_data, "d10_strength", {}) or {},
        "sav_points_houses": getattr(payload_data, "sav_points_houses", {}) or {},
        "d10_house_occupancy": getattr(payload_data, "d10_house_occupancy", {}) or {},
        "detected_yogas": getattr(payload_data, "detected_yogas", []) or [],
    }

def prioritize_rows(rows: List[Dict], priority_field_ids: List[str]) -> List[Dict]:
    """Bring a priority cluster to the front without dropping any rows."""
    priority_set = {fid: i for i, fid in enumerate(priority_field_ids)}
    front = [r for r in rows if r.get("field_id", "") in priority_set]
    front.sort(key=lambda r: priority_set.get(r.get("field_id", ""), 9999))
    rest = [r for r in rows if r.get("field_id", "") not in priority_set]
    rest.sort(key=lambda r: -float(r.get("final_score", 0.0)))
    return front + rest
