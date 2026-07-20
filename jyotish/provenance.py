"""Strict, score-neutral provenance boundary for astrological chart facts."""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Mapping

from .astro import compute_d10_chart

SIGNS = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces")
SIGN_INDEX = {sign: index for index, sign in enumerate(SIGNS)}


class FactStatus(str, Enum):
    OBSERVED = "OBSERVED"
    CALCULATED = "CALCULATED"
    DERIVED = "DERIVED"
    SYNTHETIC_FALLBACK = "SYNTHETIC_FALLBACK"
    CONFLICTED = "CONFLICTED"
    MISSING = "MISSING"


def _get(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, Mapping) else getattr(obj, key, default)


def _flat(chart: Mapping[str, Any] | None) -> dict[str, str]:
    out = {}
    for body, value in (chart or {}).items():
        sign = value.get("sign", "") if isinstance(value, Mapping) else value
        if sign in SIGN_INDEX:
            out[str(body)] = str(sign)
    return out


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _fact(fact_id: str, value: Any, status: FactStatus, source: str,
          calculator_version: str, inputs: list[str] | None = None,
          uncertainty: float = 0.0, **metadata: Any) -> dict:
    return {
        "fact_id": fact_id,
        "value": value,
        "status": status.value,
        "source": source,
        "calculator_version": calculator_version,
        "input_fact_ids": inputs or [],
        "uncertainty": max(0.0, min(1.0, float(uncertainty))),
        "sensitivity_status": "NOT_RUN",
        "metadata": metadata,
    }


def _conflicts(upstream: Mapping[str, Any], calculated: Mapping[str, Any], chart_id: str) -> list[dict]:
    left, right = _flat(upstream), _flat(calculated)
    return [
        {"fact_id": f"{chart_id}.{body}.SIGN", "upstream": left[body], "calculated": right[body]}
        for body in sorted(left.keys() & right.keys()) if left[body] != right[body]
    ]


def build_provenance_bundle(payload: Any, kp_audit: Mapping[str, Any]) -> dict:
    planets = _get(payload, "planets_d1", {}) or {}
    lagna = str(_get(payload, "lagna_sign", "") or "")
    lagna_degree = float(_get(payload, "lagna_degree", 0.0) or 0.0)
    divisions = _get(payload, "divisional_charts", {}) or {}
    supplied_d10 = divisions.get("D10_dashamsha", {}) or {}
    calculated_d10 = compute_d10_chart(planets, lagna, lagna_degree) if planets and lagna else {}
    d10_conflicts = _conflicts(supplied_d10, calculated_d10, "D10")
    uncertainty_minutes = max(0, int(_get(payload, "birth_time_uncertainty_minutes", 0) or 0))
    varga_uncertainty = min(1.0, uncertainty_minutes / 10.0)
    identity = dict(_get(payload, "calculation_identity", {}) or {})
    house_system = str(identity.get("house_system") or _get(payload, "house_system", "") or "")

    d10_status = FactStatus.CONFLICTED if d10_conflicts else (
        FactStatus.CALCULATED if calculated_d10 else FactStatus.MISSING
    )
    facts = {
        "D1.CHART": _fact("D1.CHART", planets, FactStatus.OBSERVED if planets else FactStatus.MISSING,
                           "pyhora_calculations.planets_d1", "upstream"),
        "D10.CHART": _fact("D10.CHART", _flat(calculated_d10) or _flat(supplied_d10), d10_status,
                            "astro.compute_d10_chart;upstream_compared", "d10.inrepo.v1",
                            ["D1.CHART", "D1.LAGNA"], varga_uncertainty,
                            upstream=_flat(supplied_d10), conflict_count=len(d10_conflicts)),
        "D9.CHART": _fact("D9.CHART", _flat(divisions.get("D9_navamsha", {})),
                           FactStatus.OBSERVED if divisions.get("D9_navamsha") else FactStatus.MISSING,
                           "pyhora_calculations.divisional_charts.D9_navamsha", "upstream",
                           ["D1.CHART"], varga_uncertainty),
        "D24.CHART": _fact("D24.CHART", _flat(divisions.get("D24_siddhamsam", {})),
                            FactStatus.OBSERVED if divisions.get("D24_siddhamsam") else FactStatus.MISSING,
                            "pyhora_calculations.divisional_charts.D24_siddhamsam", "upstream",
                            ["D1.CHART"], varga_uncertainty),
        "KP.CUSPS": _fact("KP.CUSPS", _get(payload, "kp_cusps", {}) or {},
                           FactStatus.OBSERVED if kp_audit.get("status") == "VERIFIED" else FactStatus.CONFLICTED,
                           "pyhora_calculations.kp_cusp_data", "kp-audit.v1", uncertainty=varga_uncertainty,
                           house_system=house_system, audit=dict(kp_audit)),
        "KP.SIGNIFICATORS": _fact("KP.SIGNIFICATORS", _get(payload, "kp_significators", {}) or {},
                                   FactStatus.OBSERVED if _get(payload, "kp_significators", {}) else FactStatus.MISSING,
                                   "pyhora_or_explicit_fallback", "upstream", ["KP.CUSPS"]),
        "JAIMINI.CHARA_KARAKAS": _fact(
            "JAIMINI.CHARA_KARAKAS",
            {"AK": _get(payload, "atmakaraka", ""), "AmK": _get(payload, "amatyakaraka", "")},
            FactStatus.OBSERVED if _get(payload, "atmakaraka", "") else FactStatus.MISSING,
            "kn_rao_jaimini_data", "7-karaka.v1", ["D1.CHART"], convention="7-karaka-no-nodes"),
    }
    critical = ("D1.CHART", "D10.CHART", "KP.CUSPS", "JAIMINI.CHARA_KARAKAS")
    errors = [f"{fid}:{facts[fid]['status']}" for fid in critical
              if facts[fid]["status"] in {FactStatus.MISSING.value, FactStatus.CONFLICTED.value}]
    source_identity = _get(payload, "source_identity", {}) or {}
    return {
        "contract_version": "canonical-provenance.v2-shadow",
        "calculation_identity": {**identity, "house_system": house_system},
        "source_sha256": str(source_identity.get("source_sha256") or _hash({"planets": planets, "divisions": divisions})),
        "facts": facts,
        "chart_sources": {"D1": "upstream", "D10": "inhouse+compared", "D9": "upstream", "D24": "upstream", "KP": "upstream+audited"},
        "conflicts": d10_conflicts,
        "errors": errors,
        "warnings": (["BIRTH_TIME_SENSITIVITY_NOT_RUN"] if uncertainty_minutes or _get(payload, "birth_time_precision", "unknown") != "exact" else []),
        "ok": not errors,
        "scoring_authority": False,
    }
