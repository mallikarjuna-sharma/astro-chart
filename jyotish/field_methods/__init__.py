"""Separated astrology scoring bundle for field determination."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from .knrao import score_knrao
from .kp import score_kp
from .jaimini import score_jaimini
from .parashara import score_parashara
from .common import (
    FIELD_PRIORITY_GROUPS,
    METHOD_SCORE_CAP,
    combine_weighted_scores,
    normalize_method_score,
)

# M1: Per-method normalization caps reflecting each method's natural raw score range.
# KNRao/Jaimini naturally top out ~30; Parashara reaches 50+ when multiple yogas fire.
# Gap-1 fix: KP cap lowered 80→60.  The H10 cusp branch alone can hit 40+ but achieving
# 80+ requires simultaneous triple-cusp signification which is extremely rare in practice.
# A cap of 60 keeps ~10-20 raw KP points as headroom for genuinely exceptional charts
# without compressing the 0-40 range (where most charts live) too aggressively.
_METHOD_SCORE_CAPS: Dict[str, float] = {
    "knrao":    30.0,
    "kp":       60.0,   # was 80.0 — Gap-1 fix
    "jaimini":  30.0,
    "parashara": 55.0,
}

logger = logging.getLogger(__name__)

METHOD_WEIGHTS: Dict[str, float] = {
    "knrao": 0.35,
    "kp": 0.25,
    "jaimini": 0.20,
    "parashara": 0.20,
}

METHOD_PROFILES: Dict[str, Dict[str, Any]] = {
    "knrao": {
        "weight": METHOD_WEIGHTS["knrao"],
        "score_cap": _METHOD_SCORE_CAPS["knrao"],
        "coverage": [
            "whole_sign_lords", "ak_amk", "arudha_lagna", "rajya_pada",
            "d9_validation", "d10_validation", "career_house_lordship", "career_yogas",
        ],
        "notes": "Classical career adjudication using whole-sign, karakas, arudha, and varga cross-checks.",
    },
    "kp": {
        "weight": METHOD_WEIGHTS["kp"],
        "score_cap": _METHOD_SCORE_CAPS["kp"],
        "coverage": [
            "h10_cusp", "h11_cusp", "h6_cusp", "h2_cusp",
            "sub_lord", "star_lord", "significator_chains",
        ],
        "notes": "KP event-fructification logic built around cusp sub-lords and significators.",
    },
    "jaimini": {
        "weight": METHOD_WEIGHTS["jaimini"],
        "score_cap": _METHOD_SCORE_CAPS["jaimini"],
        "coverage": [
            "amatyakaraka", "atmakaraka", "karakamsha", "argala",
            "brahma_lord", "maheshwara_lord", "dharma_karma",
        ],
        "notes": "Jaimini vocational and soul-purpose activation layer.",
    },
    "parashara": {
        "weight": METHOD_WEIGHTS["parashara"],
        "score_cap": _METHOD_SCORE_CAPS["parashara"],
        "coverage": [
            "yogakaraka", "h10_lord_strength", "h10_trikona", "aspect_h10",
            "yogas", "stellium", "dusthana_penalty", "dharma_karma",
        ],
        "notes": "Parashari strength and aspect model with yoga and structural penalties.",
    },
}


def _input_snapshot(payload_data: Any, domain: str, field_affinity: Dict[str, float], field_id: str) -> Dict:
    """Capture key inputs for the method log."""
    ak = getattr(payload_data, "atmakaraka", "")
    amk = getattr(payload_data, "amatyakaraka", "")
    hl = getattr(payload_data, "house_lords", {}) or {}
    digs = getattr(payload_data, "planet_dignities", {}) or {}
    eff = getattr(payload_data, "eff_strengths", {}) or {}
    ph = getattr(payload_data, "planet_house", {}) or {}
    top_aff = sorted(field_affinity.items(), key=lambda x: -x[1])[:5] if field_affinity else []
    return {
        "field_id": field_id,
        "domain": domain,
        "ak": ak,
        "amk": amk,
        "h10_lord": hl.get("10", ""),
        "h9_lord": hl.get("9", ""),
        "top_affinity": [(p, round(w, 3)) for p, w in top_aff],
        "eff_top3": sorted(eff.items(), key=lambda x: -x[1])[:3] if eff else [],
        "ak_dignity": digs.get(ak, "neutral") if ak else "—",
        "amk_dignity": digs.get(amk, "neutral") if amk else "—",
        "ak_house": ph.get(ak, 0) if ak else 0,
        "amk_house": ph.get(amk, 0) if amk else 0,
    }


def compute_field_method_bundle(
    payload_data: Any,
    domain: str,
    field_affinity: Dict[str, float],
    field_id: str = "",
) -> Dict[str, Any]:
    """Compute four isolated astrology method scores and combine with fixed weights.

    The raw method scores remain available for auditability, but the weighted blend
    is computed from the normalized 0-100 scores so every method contributes on the
    same scale.
    """
    inputs = _input_snapshot(payload_data, domain, field_affinity, field_id)

    method_entries: Dict[str, Dict[str, Any]] = {}

    t0 = time.perf_counter()
    knrao = score_knrao(payload_data, domain, field_affinity, field_id)
    method_entries["knrao"] = {
        "name": "K.N. Rao (Whole-Sign + Karakas)",
        "weight": METHOD_WEIGHTS["knrao"],
        "score_cap": _METHOD_SCORE_CAPS["knrao"],
        "inputs": {
            "ak": inputs["ak"],
            "amk": inputs["amk"],
            "h10_lord": inputs["h10_lord"],
            "top_affinity": inputs["top_affinity"],
            "ak_dignity": inputs["ak_dignity"],
            "ak_house": inputs["ak_house"],
        },
        "score": round(knrao["score"], 2),
        "normalized_score": round(knrao.get("normalized_score", 0.0), 2),
        "components": knrao.get("components", {}),
        "trace": knrao.get("trace", []),
        "score_rubric": knrao.get("score_rubric", {}),
        # Gap-6 fix: renamed from "ms" to "exec_ms" — this is wall-clock execution time in
        # milliseconds (perf_counter delta), NOT a method strength or confidence metric.
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

    t0 = time.perf_counter()
    kp = score_kp(payload_data, domain, field_affinity, field_id)
    method_entries["kp"] = {
        "name": "KP (Cusp Sub-Lords)",
        "weight": METHOD_WEIGHTS["kp"],
        "score_cap": _METHOD_SCORE_CAPS["kp"],
        "inputs": {
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
            "amk": inputs["amk"],
            "amk_dignity": inputs["amk_dignity"],
        },
        "score": round(kp["score"], 2),
        "normalized_score": round(kp.get("normalized_score", 0.0), 2),
        "components": kp.get("components", {}),
        "trace": kp.get("trace", []),
        "score_rubric": kp.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),  # Gap-6 fix: exec time, not strength
    }

    t0 = time.perf_counter()
    jaimini = score_jaimini(payload_data, domain, field_affinity, field_id)
    method_entries["jaimini"] = {
        "name": "Jaimini (Karakamsha + Argala)",
        "weight": METHOD_WEIGHTS["jaimini"],
        "score_cap": _METHOD_SCORE_CAPS["jaimini"],
        "inputs": {
            "ak": inputs["ak"],
            "amk": inputs["amk"],
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
        },
        "score": round(jaimini["score"], 2),
        "normalized_score": round(jaimini.get("normalized_score", 0.0), 2),
        "components": jaimini.get("components", {}),
        "trace": jaimini.get("trace", []),
        "score_rubric": jaimini.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),  # Gap-6 fix: exec time, not strength
    }

    t0 = time.perf_counter()
    parashara = score_parashara(payload_data, domain, field_affinity, field_id)
    method_entries["parashara"] = {
        "name": "Parashara (Yogas + H10 Strength)",
        "weight": METHOD_WEIGHTS["parashara"],
        "score_cap": _METHOD_SCORE_CAPS["parashara"],
        "inputs": {
            "h10_lord": inputs["h10_lord"],
            "h9_lord": inputs["h9_lord"],
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
            "eff_top3": inputs["eff_top3"],
        },
        "score": round(parashara["score"], 2),
        "normalized_score": round(parashara.get("normalized_score", 0.0), 2),
        "components": parashara.get("components", {}),
        "trace": parashara.get("trace", []),
        "score_rubric": parashara.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),  # Gap-6 fix: exec time, not strength
    }

    method_scores = {k: entry["score"] for k, entry in method_entries.items()}

    # M1: Normalize each method against its own cap (not a shared cap=30).
    method_normalized_scores = {
        k: normalize_method_score(v, _METHOD_SCORE_CAPS.get(k, METHOD_SCORE_CAP))
        for k, v in method_scores.items()
    }

    # M2: Redistribute weights when a method's data is missing (score==0 AND no components).
    # This prevents a zero-data method from absorbing weight and pulling the total down.
    _active_weights: Dict[str, float] = {}
    _inactive_weight = 0.0
    for k in method_scores:
        _entry_comps = method_entries[k].get("components", {})
        _has_data = method_scores[k] > 0 or bool(_entry_comps)
        if _has_data:
            _active_weights[k] = METHOD_WEIGHTS[k]
        else:
            _inactive_weight += METHOD_WEIGHTS[k]
    # Redistribute inactive weight proportionally to active methods
    if _inactive_weight > 0 and _active_weights:
        _active_total = sum(_active_weights.values()) or 1.0
        _active_weights = {
            k: w + w / _active_total * _inactive_weight
            for k, w in _active_weights.items()
        }
    effective_weights = _active_weights if _active_weights else dict(METHOD_WEIGHTS)

    method_weighted_contributions = {
        k: round(method_normalized_scores[k] * effective_weights.get(k, METHOD_WEIGHTS[k]), 2)
        for k in method_scores
    }
    combined = round(sum(method_weighted_contributions.values()), 2)
    raw_combined = round(combine_weighted_scores(method_scores, effective_weights), 2)
    multiplier = 0.80 + (combined / 100.0) * 0.40

    for key, entry in method_entries.items():
        entry["normalized_score"] = round(method_normalized_scores[key], 2)
        entry["weighted_contribution"] = method_weighted_contributions[key]

    method_breakdown = {
        key: {
            "score": method_scores[key],
            "normalized_score": round(method_normalized_scores[key], 2),
            "weight": round(effective_weights.get(key, METHOD_WEIGHTS[key]), 2),
            "weighted_contribution": method_weighted_contributions[key],
        }
        for key in method_scores
    }
    method_breakdown["weighted_total"] = combined

    _max_s = max(method_scores.values()) if method_scores else 0
    agreement = round(
        len([s for s in method_scores.values() if s >= _max_s - 12.0]) / 4.0,
        2,
    )

    # Aggregate trace and components from all method entries
    trace = {k: entry.get("trace", []) for k, entry in method_entries.items()}
    components = {k: entry.get("components", {}) for k, entry in method_entries.items()}

    return {
        "method_scores": method_scores,
        "method_normalized_scores": {k: round(v, 2) for k, v in method_normalized_scores.items()},
        "method_weighted_contributions": method_weighted_contributions,
        "method_weights": {k: METHOD_WEIGHTS[k] for k in method_scores},
        "method_profiles": {
            k: {
                "score": round(method_scores[k], 2),
                "normalized_score": round(method_normalized_scores[k], 2),
                "weighted_contribution": method_weighted_contributions[k],
            }
            for k in method_scores
        },
        "method_breakdown": method_breakdown,
        "raw_combined_score": raw_combined,
        "combined_score": combined,
        "method_total_score": combined,
        "weighted_method_score": combined,
        "astro_multiplier": multiplier,
        "method_agreement": agreement,
        "priority_groups": FIELD_PRIORITY_GROUPS,
        "method_log": method_entries,
        "inputs_snapshot": inputs,
    }
