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
        "lagna_degree": _get(payload, "lagna_degree", None),
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

    # GAP-FIX (P0-2, CalculationPolicy threading): defer to the single declared
    # policy's precise_cusps_allowed where available, instead of a local
    # == "exact" re-derivation that ignored birth_time_uncertainty_minutes.
    _policy = _get(payload, "calculation_policy", None)
    _precise_ok = (
        bool(_policy.precise_cusps_allowed)
        if _policy is not None and hasattr(_policy, "precise_cusps_allowed")
        else facts["birth_time_precision"] == "exact"
    )
    if not _precise_ok:
        warnings.append({"code": "BIRTH_TIME_PRECISION_NOT_EXACT"})
    if int(facts["birth_time_uncertainty_minutes"] or 0) >= 5:
        warnings.append({"code": "HIGH_VARGA_TIME_SENSITIVITY"})
    if not facts["d10_lagna_sign"]:
        warnings.append({"code": "D10_LAGNA_NOT_SUPPLIED"})
    # Gap-audit fix (2026-08, chat cross-chart review): 6 of 25 charts reviewed
    # had a natal lagna within ~2 degrees of a sign boundary (hemant 0.90,
    # vaagesh 1.21, Sai_Havish 1.57, ananyaa 27.97, swastik 28.05, siddarth
    # 28.30). At that degree, a birth-time error of only a few minutes can
    # flip the lagna into the neighbouring sign, which changes every whole-
    # sign house-lordship in the chart -- and therefore the entire field
    # ranking. This was previously silent; surfaced here so a report reader
    # knows to treat rank order as provisional pending time confirmation.
    _lagna_deg = facts["lagna_degree"]
    _BOUNDARY_MARGIN_DEG = 2.0
    if _lagna_deg is not None:
        try:
            _lagna_deg_f = float(_lagna_deg)
        except (TypeError, ValueError):
            _lagna_deg_f = None
        if _lagna_deg_f is not None and (
            _lagna_deg_f < _BOUNDARY_MARGIN_DEG or _lagna_deg_f > (30.0 - _BOUNDARY_MARGIN_DEG)
        ):
            warnings.append({
                "code": "LAGNA_BOUNDARY_SENSITIVE",
                "lagna_degree": round(_lagna_deg_f, 4),
                "margin_deg": _BOUNDARY_MARGIN_DEG,
                "note": (
                    "Natal lagna is within "
                    f"{_BOUNDARY_MARGIN_DEG:g} degrees of a sign boundary; a small "
                    "birth-time correction could shift the lagna sign and change "
                    "every whole-sign house lordship. Treat the field ranking as "
                    "provisional pending birth-time confirmation."
                ),
            })
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
