"""Canonical, provenance-bearing chart facts used for validation and audit.

The initial contract is observational: it records the engine's existing facts
and contradictions but deliberately does not replace values used by scoring.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from .kp_audit import audit_kp_cusps
from .provenance import build_provenance_bundle

CANONICAL_FACTS_VERSION = "canonical-facts.v1-observational"


def _get(payload: Any, name: str, default: Any = None) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _stable_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def build_canonical_facts(payload: Any) -> dict:
    facts = {
        "lagna_sign": _get(payload, "lagna_sign", ""),
        "lagna_lord": _get(payload, "lagna_lord", ""),
        "house_lords": dict(_get(payload, "house_lords", {}) or {}),
        "planet_house": dict(_get(payload, "planet_house", {}) or {}),
        "planet_signs": dict(_get(payload, "planet_signs", {}) or {}),
        "planet_longitudes": dict(_get(payload, "planet_longitudes", {}) or {}),
        "planet_dignities": dict(_get(payload, "planet_dignities", {}) or {}),
        "true_planet_dignities": dict(_get(payload, "true_planet_dignities", {}) or {}),
        "atmakaraka": _get(payload, "atmakaraka", ""),
        "amatyakaraka": _get(payload, "amatyakaraka", ""),
        "karakamsha_sign": _get(payload, "karakamsha_sign", "") or _get(payload, "karakamsha", ""),
        "d9_lagna_sign": _get(payload, "d9_lagna_sign", ""),
        "d10_lagna_sign": _get(payload, "d10_lagna_sign", ""),
        "d10_house_lords": dict(_get(payload, "d10_house_lords", {}) or {}),
        "d10_house_occupancy": dict(_get(payload, "d10_house_occupancy", {}) or {}),
        "d24_lagna_sign": _get(payload, "d24_lagna_sign", ""),
        "d24_house_lords": dict(_get(payload, "d24_house_lords", {}) or {}),
        "kp_cusps": dict(_get(payload, "kp_cusps", {}) or {}),
        "kp_significators": dict(_get(payload, "kp_significators", {}) or {}),
        "birth_time_precision": _get(payload, "birth_time_precision", "unknown"),
        "birth_time_uncertainty_minutes": _get(payload, "birth_time_uncertainty_minutes", 0),
    }
    warnings: list[dict] = []
    errors: list[dict] = []

    supplied_h10 = str(facts["house_lords"].get("10", "") or "")
    payload_h10 = str(_get(payload, "h10_lord", "") or _get(payload, "h10_lord_planet", "") or "")
    if supplied_h10 and payload_h10 and supplied_h10 != payload_h10:
        errors.append({
            "code": "D1_H10_LORD_CONTRADICTION",
            "house_lords_10": supplied_h10,
            "payload_h10_lord": payload_h10,
        })

    if facts["birth_time_precision"] != "exact":
        warnings.append({"code": "BIRTH_TIME_PRECISION_NOT_EXACT"})
    if int(facts["birth_time_uncertainty_minutes"] or 0) >= 5:
        warnings.append({"code": "HIGH_VARGA_TIME_SENSITIVITY"})
    if not facts["d10_lagna_sign"]:
        warnings.append({"code": "D10_LAGNA_NOT_SUPPLIED"})
    kp_audit = audit_kp_cusps(facts["kp_cusps"], _get(payload, "house_system", ""))
    if not facts["kp_cusps"]:
        warnings.append({"code": "KP_CUSPS_NOT_SUPPLIED"})
    elif kp_audit["status"] != "VERIFIED":
        warnings.append({"code": "KP_CUSPS_UNVERIFIED", "reasons": kp_audit["reasons"]})

    report = {
        "contract_version": CANONICAL_FACTS_VERSION,
        "facts": facts,
        "facts_sha256": _stable_hash(facts),
        "errors": errors,
        "warnings": warnings,
        "kp_cusp_audit": kp_audit,
        "ok": not errors,
        "scoring_authority": False,
    }
    report["provenance_bundle"] = build_provenance_bundle(payload, kp_audit)
    return report
