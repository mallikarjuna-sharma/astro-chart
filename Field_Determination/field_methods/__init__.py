"""Separated astrology scoring bundle for field determination."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List
from jyotish.evidence_integrity import build_signal_lineage

from .knrao import score_knrao
from .kp import score_kp
from .jaimini import score_jaimini
from .parashara import score_parashara
from .dashamsha import score_dashamsha
from .sudarshana import score_sudarshana
from .common import (
    FIELD_PRIORITY_GROUPS,
    METHOD_SCORE_CAP,
    METHOD_SCORE_CAPS,
    combine_weighted_scores,
    normalize_method_score,
)
from jyotish.kp_audit import audit_kp_cusps  # 2026-07 astrologer's audit fix (3)
from jyotish.evidence_integrity import METHOD_DEPENDENCY_GROUPS

# M1: Per-method normalization caps reflecting each method's natural raw score range.
# Audit-2026-07 Gap-1 fix: caps now live in common.METHOD_SCORE_CAPS (single source
# of truth shared with each method file's method_result call). Values unchanged.
_METHOD_SCORE_CAPS: Dict[str, float] = METHOD_SCORE_CAPS

logger = logging.getLogger(__name__)

METHOD_WEIGHTS: Dict[str, float] = {
    # Gap-Combo fix (audit 2026-07): these are no longer treated as fixed voting shares.
    # They are now the *classical authority priors for a vocation/field-determination
    # question specifically* -- not a generic "average opinion" blend.
    #
    # Traditional Jyotish gives near-total authority to different methods depending on
    # the *type* of question: KP dominates event-timing questions (cusp sub-lords), while
    # Jaimini (karakamsha/soul purpose) and the Dashamsha (BPHS's own dedicated career
    # varga) are the classically authoritative techniques for "which field/vocation."
    # Parashara's yoga/strength model speaks to general life-pattern strength, which is
    # relevant but one step removed from vocation specifically. Since this bundle answers
    # "which field," KP's prior is intentionally the lowest of the five -- its classical
    # strength (cusp timing) is largely orthogonal to the vocation question itself.
    #
    # These priors are then modulated per-chart by _method_signal_clarity() below, so a
    # method showing a clean, decisive, concentrated testimony can rise well above its
    # prior and dominate the blend, while a diffuse/ambiguous method is discounted --
    # instead of always being averaged in at a fixed share regardless of what it's saying.
    "knrao":      0.24,
    "kp":         0.09,
    "jaimini":    0.22,
    "parashara":  0.15,
    "dashamsha":  0.22,
    # Architecture fix (audit): Sudarshana Chakra (K.N. Rao's triple-ascendant
    # Lagna+Surya+Chandra H10 confirmation technique) used to sit entirely
    # outside this bundle -- computed only inside engine.py as a separate,
    # differently-weighted "convergence layer" multiplier with no vote here
    # and no representation in method_agreement/method_conflict. It is a
    # confirmatory/cross-check technique rather than a primary field-
    # determination method (the same reasoning that keeps KP's prior low),
    # so it receives a comparably modest prior. The other five priors above
    # are rescaled proportionally from their previous values (which summed
    # to 1.0 on their own) to make room for it while preserving their
    # relative ordering.
    "sudarshana": 0.08,
}

# Bounds on the per-chart clarity multiplier applied to the base authority prior above.
# A method whose signal is maximally clean/decisive can reach 1.15x its prior; a method
# whose signal is diffuse/ambiguous (near its own neutral midpoint, no dominant testimony)
# is discounted to 0.70x. This is what lets a classically-authoritative-but-noisy method
# get out-voted by a lower-prior method that happens to be unusually clean on this chart.
# Audit-2026-07 friction fix: the max was previously 1.30x, which combined with zero
# outlier control meant a single method concentrated on one component (e.g. one strong
# Jaimini yoga) could swing from a 24% prior to ~31% effective weight untouched by how
# much it disagreed with the other four methods. Capped tighter here; the actual
# disagreement control now lives in `_outlier_discount()` below, which is a corrective
# force in the opposite direction of clarity (clean AND agreeing is trusted most; clean
# but lone-wolf disagreeing is reined back in).
_CLARITY_MIN_MULT = 0.70
_CLARITY_MAX_MULT = 1.15

# GAP-FIX (2026-07, correlated-method-evidence audit): Parashara and KN Rao
# both read the same D1 (Rasi) chart independently (yogas/strength vs.
# whole-sign+karaka role hierarchy) and were previously voted as two fully
# independent witnesses in the primary blend, even though a real astrologer
# would recognise them as two lenses on ONE underlying data source (natal D1),
# not two separate confirmations. jyotish/evidence_integrity.py already names
# this exact pairing as the "d1_synthesis" dependency group but that module
# was only ever wired in as a non-authoritative shadow diagnostic
# (shadow_scoring.py), never applied to the actual final_score. This constant
# is a deliberately modest, bounded correlation dampener applied directly in
# the primary blend below: the weaker of two co-dependent methods has its
# quality-adjusted weight reduced by this factor before renormalization, so
# the pair can no longer accumulate full independent weight for restating the
# same D1 facts. 0.75 (25% dampening) is intentionally conservative relative
# to evidence_integrity.py's own SECONDARY_RESIDUAL_SHARE (0.25 kept, 75%
# discounted) -- that harsher reduction remains in the shadow layer; this is
# a bounded first step into the authoritative score, not a full adoption of
# the shadow model's aggressive reduction.
_CORRELATION_GROUP_DAMPENING = 0.75

# Bounds on the per-chart outlier discount applied when a method's normalized score
# diverges sharply from the consensus (median) of the other methods. This is the
# mechanism the structural_friction_flag (engine.py `_build_explainability_matrix`)
# used to only *report* — it never actually changed the blend. Now it does.
_OUTLIER_MILD_DEV   = 20.0   # points from median before any discount applies
_OUTLIER_SEVERE_DEV = 35.0   # points from median for the maximum discount
_OUTLIER_MIN_MULT    = 0.55  # floor applied to a severely-diverging method
_OUTLIER_MILD_MULT   = 0.80  # applied at/above the mild threshold


def _outlier_discount(normalized_scores: Dict[str, float]) -> Dict[str, float]:
    """Down-weight methods whose score is a statistical outlier vs the group median.

    A method landing far from where the other methods converge is either catching a
    real, unusually specific testimony the others miss (rare) or is malfunctioning /
    picking up noise on this chart (more common in practice, per the audit). Rather
    than let the clarity multiplier alone reward such a method for looking "decisive",
    this discounts it proportionally to how far it sits from consensus — so an outlier
    method's effective weight shrinks instead of merely being flagged after the fact.

    Needs >=3 methods to define a meaningful median; with fewer, returns no discount
    (2 methods disagreeing has no "consensus" to be an outlier against).
    """
    vals = list(normalized_scores.values())
    if len(vals) < 3:
        return {k: 1.0 for k in normalized_scores}

    sorted_vals = sorted(vals)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2:
        median = sorted_vals[mid]
    else:
        median = (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0

    out: Dict[str, float] = {}
    for k, v in normalized_scores.items():
        dev = abs(v - median)
        if dev <= _OUTLIER_MILD_DEV:
            out[k] = 1.0
        elif dev >= _OUTLIER_SEVERE_DEV:
            out[k] = _OUTLIER_MIN_MULT
        else:
            # Linear interpolation between mild and severe thresholds
            frac = (dev - _OUTLIER_MILD_DEV) / (_OUTLIER_SEVERE_DEV - _OUTLIER_MILD_DEV)
            out[k] = round(1.0 - frac * (1.0 - _OUTLIER_MILD_MULT), 4)
    return out


def _method_signal_clarity(normalized_score: float, components: Dict[str, float]) -> float:
    """Estimate how 'clean' vs 'noisy' a method's testimony is on this specific chart.

    Two complementary signals feed the estimate:
      1. Score extremity — a method landing far from its own neutral midpoint (50 on the
         normalized 0-100 scale) is making a decisive statement (strongly for, or strongly
         against). A method sitting near 50 is not really saying much either way.
      2. Component concentration — when a method's score is dominated by one or two large
         classical testimonies (a strong yoga, a clean karakamsha hit) rather than many
         small scattered contributions, that is the "one clear signal" a real astrologer
         would trust over an accumulation of minor, possibly-coincidental points.

    Returns a 0..1 clarity score (0 = diffuse/ambiguous, 1 = clean/decisive).
    """
    extremity = min(1.0, abs(normalized_score - 50.0) / 50.0)

    concentration = 0.0
    if components:
        vals = [abs(v) for v in components.values() if isinstance(v, (int, float))]
        total = sum(vals)
        if total > 0:
            top = max(vals)
            concentration = min(1.0, top / total)

    return round(0.5 * extremity + 0.5 * concentration, 4)


def _clarity_multiplier(clarity: float) -> float:
    return round(_CLARITY_MIN_MULT + (_CLARITY_MAX_MULT - _CLARITY_MIN_MULT) * clarity, 4)

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
    "dashamsha": {
        "weight": METHOD_WEIGHTS["dashamsha"],
        "score_cap": _METHOD_SCORE_CAPS["dashamsha"],
        "coverage": [
            "d10_lagna_lord", "d10_h10_lord", "d10_raj_yoga", "d10_yogakaraka",
            "d10_h10_occupants", "d10_h10_stellium", "d10_lagna_affinity",
            "d10_h9_dharma", "d1_h10_lord_in_d10",
        ],
        "notes": "T1-A: Standalone D10 Dashamsha scorer. BPHS primary career varga, "
                 "evaluated as a self-contained chart with its own lagna, lords, and yogas.",
    },
    "sudarshana": {
        "weight": METHOD_WEIGHTS["sudarshana"],
        "score_cap": _METHOD_SCORE_CAPS["sudarshana"],
        "coverage": [
            "lagna_h10_lord", "surya_lagna_h10_lord", "chandra_lagna_h10_lord",
            "triple_lord_agreement", "triple_sign_lock",
        ],
        "notes": "Architecture fix: promoted to a first-class 6th method. K.N. Rao's "
                 "Sudarshana Chakra -- H10 examined from Lagna, Surya, and Chandra "
                 "simultaneously; scores true convergence (same lord confirmed from "
                 "all three) above mere independent, non-agreeing support.",
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
    field_entry: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Compute four isolated astrology method scores and combine with fixed weights.

    The raw method scores remain available for auditability, but the weighted blend
    is computed from the normalized 0-100 scores so every method contributes on the
    same scale.

    Gap-18b (generalized fix, audit 2026-07): `field_entry` is the field's full
    registry record (label/track/specialization/niche/description), threaded
    through to every method scorer so their internal keyword-gate checks can
    match on that descriptive text, not just the bare field_id. Optional and
    defaulted to None so existing callers are unaffected. See
    field_methods/common.py::build_gate_text for the full rationale.
    """
    inputs = _input_snapshot(payload_data, domain, field_affinity, field_id)

    method_entries: Dict[str, Dict[str, Any]] = {}

    t0 = time.perf_counter()
    knrao = score_knrao(payload_data, domain, field_affinity, field_id, field_entry)
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
    kp = score_kp(payload_data, domain, field_affinity, field_id, field_entry)
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
    jaimini = score_jaimini(payload_data, domain, field_affinity, field_id, field_entry)
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
    parashara = score_parashara(payload_data, domain, field_affinity, field_id, field_entry)
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

    # T1-A: Dashamsha (D10) — 5th method: BPHS primary career varga
    t0 = time.perf_counter()
    dashamsha = score_dashamsha(payload_data, domain, field_affinity, field_id, field_entry)
    _d10_lagna = ((getattr(payload_data, "divisional_charts", {}) or {}).get("D10_dashamsha", {}) or {}).get("Lagna", "")
    method_entries["dashamsha"] = {
        "name": "Dashamsha D10 (BPHS Career Varga)",
        "weight": METHOD_WEIGHTS["dashamsha"],
        "score_cap": _METHOD_SCORE_CAPS["dashamsha"],
        "inputs": {
            "d10_lagna": _d10_lagna,
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
            "h10_lord": inputs["h10_lord"],
        },
        "score": round(dashamsha["score"], 2),
        "normalized_score": round(dashamsha.get("normalized_score", 0.0), 2),
        "components": dashamsha.get("components", {}),
        "trace": dashamsha.get("trace", []),
        "score_rubric": dashamsha.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

    # Architecture fix (audit): Sudarshana Chakra -- 6th voting method.
    # Previously computed only inside engine.py as a separate, unweighted
    # convergence-only layer (no vote here, absent from method_agreement/
    # method_conflict). score_sudarshana() already returns a native 0-100
    # score, so it slots into the same method_entries/method_scores pipeline
    # as the other five with no extra normalization step.
    t0 = time.perf_counter()
    _sud_label = field_id.replace("_", " ") if field_id else domain
    sudarshana = score_sudarshana(_sud_label, field_affinity, payload_data)
    _sud_score = round(float(sudarshana.get("score", 0.0)), 2)
    method_entries["sudarshana"] = {
        "name": "Sudarshana Chakra (Lagna+Surya+Chandra Triple Ascendant)",
        "weight": METHOD_WEIGHTS["sudarshana"],
        "score_cap": _METHOD_SCORE_CAPS["sudarshana"],
        "inputs": {
            "lagna_h10": sudarshana.get("lagna_h10", ""),
            "sun_h10": sudarshana.get("sun_h10", ""),
            "moon_h10": sudarshana.get("moon_h10", ""),
            "top_affinity": inputs["top_affinity"],
        },
        "score": _sud_score,
        "normalized_score": _sud_score,  # already native 0-100; overwritten below for consistency
        "raw_signed_score": _sud_score,  # Sudarshana has no penalty channel -- never negative
        "is_net_negative": False,
        "components": {
            "layers_active": float(sudarshana.get("layers_active", 0)),
        },
        "trace": list(sudarshana.get("trace", [])),
        "score_rubric": {},
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

    method_scores = {k: entry["score"] for k, entry in method_entries.items()}

    # M1: Normalize each method against its own cap (not a shared cap=30).
    method_normalized_scores = {
        k: normalize_method_score(v, _METHOD_SCORE_CAPS.get(k, METHOD_SCORE_CAP))
        for k, v in method_scores.items()
    }

    # G20: Pre-reduce method weight when key data structures are absent
    _data_quality: Dict[str, float] = {
        "knrao": 1.0, "kp": 1.0, "jaimini": 1.0, "parashara": 1.0, "dashamsha": 1.0,
        "sudarshana": 1.0,  # gates on lagna/Sun/Moon sign, which are base-chart data (always present)
    }
    _d24_present = bool(getattr(payload_data, "divisional_charts", {}).get("D24_siddhamsam"))
    _kp_cusps_present = bool(getattr(payload_data, "kp_cusps", {}))
    _karam_present = bool(getattr(payload_data, "karakamsha", ""))
    _d10_present = bool(_d10_lagna)  # T1-A: gate D10 method on chart availability
    if not _d24_present:      _data_quality["knrao"]     *= 0.75  # D24 gating missing
    if not _karam_present:    _data_quality["jaimini"]    *= 0.60  # karakamsha absent
    if not _d10_present:      _data_quality["dashamsha"]  *= 0.00  # D10 chart absent → skip

    # 2026-07 astrologer's audit, fix (3): the KP discount used to be a
    # boolean "are cusps present at all" check (_kp_cusps_present), which
    # only catches missing data -- it stays 1.0 (no discount) even when
    # cusps ARE present but the KP sub-lord chain failed independent
    # verification (kp_audit.status != "VERIFIED", e.g. wrong house system,
    # equal/whole-sign cusp pattern, or a Vimshottari-chain mismatch -- see
    # jyotish/kp_audit.py::audit_kp_cusps). A broken-but-present KP method
    # could therefore keep near-full weight while silently voting on wrong
    # information, distorting order among top candidates without the field
    # SET looking wrong. This now runs the real verification check and uses
    # its kp_authority_factor (1.0 VERIFIED / 0.0 UNVERIFIED) as the primary
    # gate; cusp presence alone is kept as a secondary, coarser fallback
    # discount for the (rare) case cusps are entirely absent.
    # House system defaults to "placidus" since this engine's own
    # get_house_cusps_placidus() is the only cusp-computation path in this
    # codebase (jyotish/ephemeris.py) -- audit_kp_cusps() still independently
    # catches chain-mismatch/equal-pattern failures regardless of this flag,
    # so this default cannot manufacture a false VERIFIED result on its own.
    if not _kp_cusps_present:
        _data_quality["kp"] *= 0.50  # KP cusp data absent entirely
    else:
        _kp_audit_result = audit_kp_cusps(
            getattr(payload_data, "kp_cusps", {}) or {},
            getattr(payload_data, "house_system", "") or "placidus",
        )
        _data_quality["kp"] *= _kp_audit_result.get("kp_authority_factor", 0.0)
    # T3-C: KP sublord reliability degrades sharply with imprecise birth time.
    # Sublords shift every 4-12 min; approximate times render cusp-based signals unreliable.
    _birth_prec_init = getattr(payload_data, "birth_time_precision", "exact") or "exact"
    if _birth_prec_init == "approximate":
        _data_quality["kp"] *= 0.65   # approximate: sublords questionable
    elif _birth_prec_init == "unknown":
        # Q4: Sub-lord stripped in kp.py; only star-lord chain contributes.
        # Target effective KP weight = 0.10 (from 0.22 base). Multiplier = 0.10/0.22 ≈ 0.455.
        _data_quality["kp"] *= (0.10 / 0.22)
    # Gap-Combo fix: per-chart signal-clarity multiplier on top of the classical
    # authority prior. A method that is clean/decisive on THIS chart is trusted more
    # than its fixed prior; a method that is diffuse/ambiguous here is trusted less --
    # so disagreement between methods can shift real authority rather than being
    # smoothed into an even split.
    _clarity: Dict[str, float] = {}
    _clarity_mult: Dict[str, float] = {}
    for k in METHOD_WEIGHTS:
        _ns = method_normalized_scores.get(k, 0.0)
        _comps = method_entries[k].get("components", {})
        _clarity[k] = _method_signal_clarity(_ns, _comps)
        _clarity_mult[k] = _clarity_multiplier(_clarity[k])

    # Friction fix: discount methods that are statistical outliers vs the other methods'
    # consensus, so a single disagreeing method (however "clean" its own signal looks)
    # can't hijack the blend. This is the actual weight-side counterpart to the
    # structural_friction_flag shown in the XAI matrix, which previously only reported
    # disagreement without doing anything about it.
    _outlier_mult = _outlier_discount(method_normalized_scores)

    # Apply quality-adjusted, clarity-adjusted, outlier-discounted base weights
    # before M2 redistribution
    _qa_weights = {
        k: METHOD_WEIGHTS[k] * _data_quality[k] * _clarity_mult[k] * _outlier_mult.get(k, 1.0)
        for k in METHOD_WEIGHTS
    }

    # GAP-FIX (2026-07, correlated-method-evidence audit): dampen the weaker
    # member of each correlated-method group (currently only d1_synthesis:
    # parashara+knrao) so two witnesses reading the same underlying chart
    # source don't both count at full independent weight. The stronger
    # (higher quality-adjusted weight) member of the group is left untouched
    # -- only the weaker/redundant one is discounted -- so a genuinely
    # decisive, clean signal from either method still dominates; this only
    # prevents the pair from *jointly* out-voting the other four methods by
    # restating the same D1 facts twice.
    for _group_methods in METHOD_DEPENDENCY_GROUPS.values():
        _present = [m for m in _group_methods if m in _qa_weights]
        if len(_present) < 2:
            continue
        _strongest = max(_present, key=lambda m: _qa_weights[m])
        for _m in _present:
            if _m != _strongest:
                _qa_weights[_m] *= _CORRELATION_GROUP_DAMPENING

    _qa_total   = sum(_qa_weights.values()) or 1.0
    _qa_weights = {k: v / _qa_total for k, v in _qa_weights.items()}  # renormalize to sum=1

    # M2: Redistribute weights when a method's data is missing (score==0 AND no components).
    # This prevents a zero-data method from absorbing weight and pulling the total down.
    #
    # Gap-3/4/9 fix: `method_scores[k]` is the *clamped, floored-at-0* display
    # score, so a method that fired real contraindications (net penalties >
    # positives, raw signed score < 0) looked identical here to a method that
    # never fired anything at all — both were `score==0`. If such a method also
    # happened to have no populated components (e.g. penalties applied inline
    # without recording a component), it was wrongly bucketed as "no data" and
    # its weight got redistributed away, silently discarding a real
    # contraindication signal instead of letting it pull the score down.
    # `raw_signed_score` (now threaded through from each method file) lets us
    # tell the two cases apart: a genuinely negative raw score IS data.
    _active_weights: Dict[str, float] = {}
    _inactive_weight = 0.0
    _net_negative_flags: Dict[str, bool] = {}
    for k in method_scores:
        _entry_comps = method_entries[k].get("components", {})
        _raw_signed = method_entries[k].get("raw_signed_score", method_scores[k])
        _net_negative_flags[k] = bool(method_entries[k].get("is_net_negative", _raw_signed < 0))
        _has_data = method_scores[k] > 0 or bool(_entry_comps) or _net_negative_flags[k]
        if _has_data:
            _active_weights[k] = _qa_weights[k]  # G20: quality-adjusted
        else:
            _inactive_weight += _qa_weights[k]  # G20
    # Redistribute inactive weight proportionally to active methods
    if _inactive_weight > 0 and _active_weights:
        _active_total = sum(_active_weights.values()) or 1.0
        _active_weights = {
            k: w + w / _active_total * _inactive_weight
            for k, w in _active_weights.items()
        }
    effective_weights = _active_weights if _active_weights else dict(_qa_weights)  # G20

    # Contraindication channel: give net-negative methods a real (but bounded)
    # voice instead of letting clamp-to-0 erase them. Each net-negative,
    # data-carrying method contributes a small weighted penalty proportional to
    # how negative its raw score is relative to its own cap, capped overall at
    # -12% of combined_score so no single or even majority-negative method can
    # dominate without calibration data to justify a larger swing (see
    # DEEP_AUDIT item 3 — full recalibration needs the 250-chart stress set).
    _contra_terms = []
    for k in method_scores:
        if not _net_negative_flags.get(k):
            continue
        _raw_signed = method_entries[k].get("raw_signed_score", 0.0)
        _cap_k = _METHOD_SCORE_CAPS.get(k, METHOD_SCORE_CAP) or METHOD_SCORE_CAP
        _severity = max(0.0, min(1.0, abs(_raw_signed) / _cap_k))
        _contra_terms.append(_severity * effective_weights.get(k, 0.0))
    net_contraindication_index = round(min(1.0, sum(_contra_terms)), 4)

    # P4: SAV total chart-strength confidence gate.
    # Sarvashtakavarga total (sum of all 12 house bindus) reflects holistic chart quality.
    # Average house = 28 bindus → total ≈ 337. Strong chart ≥ 360, weak ≤ 280.
    # Apply a global confidence multiplier to the combined score.
    _sav_total_p4 = sum((getattr(payload_data, "sav_points_houses", {}) or {}).values())
    if _sav_total_p4 >= 360:
        _sav_conf_mult = 1.08
    elif _sav_total_p4 >= 340:
        _sav_conf_mult = 1.04
    elif _sav_total_p4 > 0 and _sav_total_p4 <= 280:
        _sav_conf_mult = 0.93
    elif _sav_total_p4 > 0 and _sav_total_p4 <= 300:
        _sav_conf_mult = 0.97
    else:
        _sav_conf_mult = 1.0   # unknown or average — no adjustment

    method_weighted_contributions = {
        # Compute from the same displayed precision exported in method_log so
        # the audit equation can be reproduced exactly (avoids hidden-float
        # one-cent discrepancies such as 12.37 vs 12.38).
        k: round(round(method_normalized_scores[k], 2) *
                 round(effective_weights.get(k, METHOD_WEIGHTS[k]), 4), 2)
        for k in method_scores
    }
    combined = round(sum(method_weighted_contributions.values()) * _sav_conf_mult, 2)
    raw_combined = round(combine_weighted_scores(method_scores, effective_weights) * _sav_conf_mult, 2)
    # Contraindication channel (Gap-3/9): net-negative methods now pull combined
    # down directly, capped at -12% so a single or majority-negative method
    # can't dominate un-calibrated. Previously invisible (clamped to 0 upstream).
    _contra_mult = round(1.0 - 0.12 * net_contraindication_index, 4)
    combined = round(combined * _contra_mult, 2)
    raw_combined = round(raw_combined * _contra_mult, 2)
    multiplier = 0.80 + (combined / 100.0) * 0.40

    for key, entry in method_entries.items():
        entry["normalized_score"] = round(method_normalized_scores[key], 2)
        entry["weight"] = round(effective_weights.get(key, METHOD_WEIGHTS[key]), 4)
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

    # Gap-5 (audit 2026-07) fix: agreement was computed on RAW scores, which are
    # not comparable across methods with different caps (KP raw 45 ≈ KNRao raw 22).
    # Use the normalized 0-100 scores so "within 15 points of the best method"
    # means the same thing for every method.
    _norm_vals = list(method_normalized_scores.values())
    _max_ns = max(_norm_vals) if _norm_vals else 0.0
    _n_methods = max(len(_norm_vals), 1)
    agreement = round(
        len([s for s in _norm_vals if s >= _max_ns - 15.0]) / _n_methods,
        2,
    )

    # Gap-Combo fix: genuine method conflict is diagnostic, not just noise to average
    # away. When the classically-authoritative methods for this chart (top-2 by the
    # dynamic, clarity-adjusted weight) land far apart on the same field, a real
    # astrologer investigates *why* rather than silently blending. Surface that here
    # instead of hiding it inside a single combined number.
    _ranked_by_weight = sorted(effective_weights.items(), key=lambda kv: -kv[1])
    _method_conflict: Dict[str, Any] = {"detected": False}
    if len(_ranked_by_weight) >= 2:
        _top_k, _top_w = _ranked_by_weight[0]
        _second_k, _second_w = _ranked_by_weight[1]
        _top_ns = method_normalized_scores.get(_top_k, 0.0)
        _second_ns = method_normalized_scores.get(_second_k, 0.0)
        _spread = max(_norm_vals) - min(_norm_vals) if _norm_vals else 0.0
        _authority_gap = abs(_top_ns - _second_ns)
        # Conflict = the two most-authoritative methods on this chart substantially
        # disagree on this field (not just minor noise), AND the overall spread across
        # all five methods is wide enough that averaging would be masking a real split.
        if _authority_gap >= 30.0 and _spread >= 35.0:
            _method_conflict = {
                "detected": True,
                "top_method": _top_k,
                "top_method_score": round(_top_ns, 2),
                "second_method": _second_k,
                "second_method_score": round(_second_ns, 2),
                "authority_gap": round(_authority_gap, 2),
                "normalized_spread": round(_spread, 2),
                "recommendation": (
                    f"{_top_k} and {_second_k} substantially disagree on this field "
                    f"({round(_top_ns,1)} vs {round(_second_ns,1)}). Rather than trusting "
                    "the blended average, verify birth-time precision (KP sub-lords are "
                    "highly time-sensitive) and consider a Prashna (horary) cross-check "
                    "before treating this field's combined score as reliable."
                ),
            }

    # Aggregate trace and components from all method entries
    trace = {k: entry.get("trace", []) for k, entry in method_entries.items()}
    components = {k: entry.get("components", {}) for k, entry in method_entries.items()}

    _signal_lineage = build_signal_lineage(method_scores)
    return {
        "method_scores": method_scores,
        "method_normalized_scores": {k: round(v, 2) for k, v in method_normalized_scores.items()},
        "method_weighted_contributions": method_weighted_contributions,
        "method_weights": {k: round(effective_weights.get(k, METHOD_WEIGHTS[k]), 4) for k in method_scores},
        "method_authority_priors": {k: METHOD_WEIGHTS[k] for k in method_scores},
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
        "method_independence": {
            "independence_claim_allowed": False,
            "reason": "Methods reuse natal planets, dignity, strength, house and dasha facts.",
            "agreement_label": "CORRELATED_CONVERGENCE",
            "effective_independent_method_count": _signal_lineage["effective_independent_method_count"],
            "status": "ESTIMATED_FROM_DECLARED_SIGNAL_LINEAGE_NOT_STATISTICALLY_CALIBRATED",
        },
        "signal_lineage": _signal_lineage,
        "method_conflict": _method_conflict,
        "net_contraindication_index": net_contraindication_index,
        "net_negative_methods": [k for k, v in _net_negative_flags.items() if v],
        "method_signal_clarity": {k: round(v, 3) for k, v in _clarity.items()},
        "method_clarity_multiplier": {k: round(v, 3) for k, v in _clarity_mult.items()},
        "method_outlier_multiplier": {k: round(v, 3) for k, v in _outlier_mult.items()},
        "priority_groups": FIELD_PRIORITY_GROUPS,
        "method_log": method_entries,
        "trace": trace,
        "method_components": components,
        "inputs_snapshot": inputs,
    }
