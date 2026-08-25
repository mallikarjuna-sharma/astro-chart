"""JyotishAI — EduAlign: Education Alignment Engine.

Implements three gap-fill modules for the student cohort:

  E-1  compute_d1_d24_stream_score(payload)
       Cross-maps D1 H5 (intelligence house) × D24 H9 (higher learning/guru)
       to produce technical / humanities / arts affinity scores.

  E-2  compute_sub_branch_compatibility(field_id, eff_strengths, planet_dignities)
       Planet-cluster → sub-branch weight matrix giving a 0-100 branch fit score.

  E-3  compute_exam_day_scores(dob, lagna_sign, dasha_seq, exam_dates, today)
       Per-exam-date "Exam Day Success Score" crossing Dasha quality ×
       Moon nakshatra × active transit on that specific date.

  E-4  compute_academic_tier_recommendation(payload)
       [2026-07-04 ontology audit, G17] D24-driven UG vs PG vs PhD/Research
       tier recommendation. The registry's tier_map (UG/PG/PhD degree data
       per field) is complete and is now surfaced via the competency
       hierarchy panel, but nothing previously used the native's own D24
       (Chaturvimshamsha) chart to recommend which tier of study the chart
       itself favours. This is that missing recommender — advisory only,
       does not alter any per-field final_score.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger("jyotish_engine_v11_0")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_SIGN_LORD = {
    "Aries": "Mars",   "Taurus": "Venus",  "Gemini": "Mercury",
    "Cancer": "Moon",  "Leo": "Sun",       "Virgo": "Mercury",
    "Libra": "Venus",  "Scorpio": "Mars",  "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

_SIGN_IDX = {s: i for i, s in enumerate(_SIGNS)}

# Classical dignities
_EXALTATION = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces",
    "Saturn": "Libra", "Rahu": "Gemini", "Ketu": "Sagittarius",
}
_DEBILITATION = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo",
    "Saturn": "Aries", "Rahu": "Sagittarius", "Ketu": "Gemini",
}
_OWN_SIGN = {
    "Sun": {"Leo"}, "Moon": {"Cancer"}, "Mars": {"Aries", "Scorpio"},
    "Mercury": {"Gemini", "Virgo"}, "Jupiter": {"Sagittarius", "Pisces"},
    "Venus": {"Taurus", "Libra"}, "Saturn": {"Capricorn", "Aquarius"},
}


def _nth_sign_from(lagna_sign: str, n: int) -> str:
    """Return the sign occupying the Nth house from lagna (1-indexed)."""
    if lagna_sign not in _SIGN_IDX:
        return ""
    idx = (_SIGN_IDX[lagna_sign] + n - 1) % 12
    return _SIGNS[idx]


def _house_distance(from_sign: str, to_sign: str) -> int:
    """1-indexed house distance of to_sign counted from from_sign as lagna.

    Same convention as field_methods/jaimini.py::_house_distance (kept as a
    local copy to avoid a cross-package import for one small helper).
    """
    if not from_sign or not to_sign or from_sign not in _SIGN_IDX or to_sign not in _SIGN_IDX:
        return 0
    return ((_SIGN_IDX[to_sign] - _SIGN_IDX[from_sign]) % 12) + 1


def _sign_lord(sign: str) -> str:
    return _SIGN_LORD.get(sign, "")


def _dignity_weight(planet: str, sign: str) -> float:
    """Return a 0-1 dignity weight for planet in sign."""
    if not sign or not planet:
        return 0.5
    if sign == _EXALTATION.get(planet):
        return 1.0
    if sign == _DEBILITATION.get(planet):
        return 0.1
    if sign in _OWN_SIGN.get(planet, set()):
        return 0.85
    return 0.5


# ---------------------------------------------------------------------------
# E-1 · D1 × D24 Stream Score
# ---------------------------------------------------------------------------

# Technical fields map to: Mars, Saturn, Rahu (engineering/science)
# Humanities/Social: Jupiter, Mercury, Moon (law, arts, management)
# Arts/Design/Fine arts: Venus, Moon, Rahu
_STREAM_PLANET_WEIGHTS: Dict[str, Dict[str, float]] = {
    "technical": {
        "Mars": 1.0, "Saturn": 0.9, "Rahu": 0.7,
        "Mercury": 0.6, "Sun": 0.5,
        "Jupiter": 0.3, "Venus": 0.2, "Moon": 0.2, "Ketu": 0.4,
    },
    "humanities": {
        "Jupiter": 1.0, "Mercury": 0.9, "Moon": 0.7,
        "Venus": 0.6, "Sun": 0.5,
        "Saturn": 0.3, "Mars": 0.2, "Rahu": 0.3, "Ketu": 0.3,
    },
    "arts": {
        "Venus": 1.0, "Moon": 0.9, "Rahu": 0.6,
        "Mercury": 0.6, "Jupiter": 0.5,
        "Mars": 0.3, "Saturn": 0.2, "Sun": 0.3, "Ketu": 0.5,
    },
}


def _check_d24_lagna_consistency(payload: Any) -> Dict[str, Any]:
    """Gap-audit fix (2026-08, safe/non-scoring): detect drift between the
    two independent D24-lagna read paths documented in the docstring below
    (`payload.d24_lagna_sign` here vs.
    `payload.divisional_charts["D24_siddhamsam"]["Lagna"]` in
    Field_Determination/field_methods/siddhamsha.py::score_siddhamsha).

    This is deliberately observation-only: it does not alter d1_d24 stream
    scoring, siddhamsha scoring, or final_score in any way. It exists so a
    real disagreement -- which the original docstring flagged as "a genuine
    upstream payload-construction bug" that should be fixed at the source --
    becomes a visible, loggable fact instead of silently going unnoticed
    (the two paths were previously "intentionally not merged" with no way
    to know if/when they actually diverge on a real chart).

    Returns {"checked": bool, "consistent": bool, "d24_lagna_sign": str,
    "divisional_charts_lagna": str} so callers can surface this in
    diagnostics/reports without it affecting any score.
    """
    d24_lagna_field = getattr(payload, "d24_lagna_sign", "") or ""
    divisional_charts = getattr(payload, "divisional_charts", {}) or {}
    d24_chart = divisional_charts.get("D24_siddhamsam", {}) or {}
    d24_lagna_chart = (
        d24_chart.get("Lagna") if isinstance(d24_chart, dict) else None
    ) or ""

    if not d24_lagna_field or not d24_lagna_chart:
        # One or both sources absent -- nothing to compare, not a disagreement.
        return {
            "checked": False,
            "consistent": True,
            "d24_lagna_sign": d24_lagna_field,
            "divisional_charts_lagna": d24_lagna_chart,
        }

    consistent = str(d24_lagna_field).strip().lower() == str(d24_lagna_chart).strip().lower()
    if not consistent:
        _logger.warning(
            "D24 lagna-sign disagreement between payload.d24_lagna_sign=%r "
            "and payload.divisional_charts['D24_siddhamsam']['Lagna']=%r -- "
            "compute_d1_d24_stream_score (edu_align.py) and score_siddhamsha "
            "(Field_Determination/field_methods/siddhamsha.py) are reading "
            "different D24 lagna values for the same chart. This indicates "
            "an upstream payload-construction inconsistency (payload.py / "
            "engine_io.py) and should be investigated at the source.",
            d24_lagna_field, d24_lagna_chart,
        )
    return {
        "checked": True,
        "consistent": consistent,
        "d24_lagna_sign": d24_lagna_field,
        "divisional_charts_lagna": d24_lagna_chart,
    }


def compute_d1_d24_stream_score(payload: Any) -> Dict[str, Any]:
    """E-1: Cross-map D1 H5 × D24 H9 into stream affinity scores.

    Phase-5 remediation note (2026-08 gap-audit): this function and
    Field_Determination/field_methods/siddhamsha.py::score_siddhamsha both
    read D24 data from `payload`, but via different attribute paths --
    this reads `payload.d24_lagna_sign` / `payload.d24_house_lords` while
    score_siddhamsha reads `payload.divisional_charts["D24_siddhamsam"]`.
    Both already share `payload.d24_planet_dignities` as a single source, so
    dignity readings cannot drift between the two, but the *lagna sign* and
    *house-lord* derivations are two independent code paths against
    (presumably) the same underlying D24 chart object. These are
    intentionally NOT merged here: this function answers a coarser question
    ("technical vs. humanities vs. arts stream") while score_siddhamsha
    answers a finer one ("how well does D24 support THIS specific field"),
    and collapsing them risks silently changing either's calibration
    without a real chart to validate against. If `payload.d24_lagna_sign`
    and `payload.divisional_charts["D24_siddhamsam"]["Lagna"]` are ever
    observed to disagree on a real chart, that is a genuine upstream
    payload-construction bug (jyotish/payload.py / engine_io.py) and should
    be fixed at the source, not patched around in either consumer.

    Args:
        payload: NatalPayloadV2 instance (or any object with required attrs).

    Returns dict:
        h5_d1_lord    : planet ruling H5 in D1
        h9_d24_lord  : planet ruling H9 in D24
        technical     : float 0-1
        humanities    : float 0-1
        arts          : float 0-1
        dominant_stream: "technical" | "humanities" | "arts"
        confidence    : float 0-1 (gap between top-2 scores)
        interpretation: str
    """
    lagna_sign    = getattr(payload, "lagna_sign", "") or ""
    d24_lagna     = getattr(payload, "d24_lagna_sign", "") or ""
    eff_strengths = getattr(payload, "eff_strengths", {}) or {}
    house_lords   = getattr(payload, "house_lords", {}) or {}
    d24_dignities = getattr(payload, "d24_planet_dignities", {}) or {}

    # D1 H5 lord
    h5_sign_d1   = _nth_sign_from(lagna_sign, 5)
    h5_lord_d1   = house_lords.get("5") or house_lords.get("H5") or _sign_lord(h5_sign_d1)

    # D24 H9 lord
    # GAP-FIX (2026-08, astrological audit): this previously read the D24
    # 10TH house (career/karma in every standard bhava scheme) while this
    # function's own docstring, and this same module's E-4 function
    # (compute_academic_tier_recommendation, which correctly uses the D24
    # 9th house), both frame D24 as the classical divisional chart for
    # LEARNING specifically -- whose diagnostic houses are the lagna
    # (baseline learning capacity) and the 9th (higher learning/guru), not
    # the 10th. Using the 10th house here mixed a career-house signal into
    # what was meant to be an education-alignment score, and did so
    # inconsistently with E-4's correct convention for the same underlying
    # "does D24 support deep learning" question. Changed to the 9th house
    # to match the classical rule and this module's own E-4 usage.
    h9_sign_d24 = _nth_sign_from(d24_lagna, 9) if d24_lagna else ""
    h9_lord_d24 = getattr(payload, "d24_house_lords", {}).get("9") or _sign_lord(h9_sign_d24)

    # Dignity of D1 H5 lord in D24
    d24_dignity_of_h5_lord = d24_dignities.get(h5_lord_d1, "neutral")

    def _dignity_to_w(dign: str) -> float:
        _map = {"exalted": 1.0, "own": 0.85, "friendly": 0.65,
                "neutral": 0.5, "enemy": 0.3, "debilitated": 0.1}
        return _map.get(str(dign).lower(), 0.5)

    h5_d1_weight  = _dignity_to_w(d24_dignity_of_h5_lord)
    h9_d24_weight = _dignity_weight(h9_lord_d24, h9_sign_d24)

    # G21: detect D24 data availability; reduce confidence when absent
    d24_available = bool(d24_lagna and h9_lord_d24)
    cross_factor = (h5_d1_weight + h9_d24_weight) / 2.0
    if not d24_available:
        cross_factor *= 0.50  # halve cross-factor — D24 not verified

    scores: Dict[str, float] = {}
    for stream, weights in _STREAM_PLANET_WEIGHTS.items():
        # Weighted sum of eff_strengths scaled by stream planet weights
        total_w  = sum(weights.values())
        raw      = sum(
            eff_strengths.get(p, 0.5) * w
            for p, w in weights.items()
        ) / total_w
        # Cross-factor biases the score: H5×D24-H9 alignment
        h5_bias  = weights.get(h5_lord_d1, 0.5) / max(weights.values())
        h9_bias = weights.get(h9_lord_d24, 0.5) / max(weights.values())
        cross_boost = cross_factor * (h5_bias + h9_bias) / 2.0 * 0.15
        scores[stream] = min(1.0, raw * 0.85 + cross_boost)

    # Normalise so highest = 1.0
    top = max(scores.values()) or 1.0
    scores = {k: round(v / top, 3) for k, v in scores.items()}

    sorted_streams = sorted(scores, key=lambda k: -scores[k])
    dominant       = sorted_streams[0]
    confidence = round(scores[sorted_streams[0]] - scores[sorted_streams[1]], 3)
    if not d24_available:
        confidence = round(confidence * 0.60, 3)  # G21: reduced confidence without D24

    interp_parts = [
        f"H5(D1) lord is {h5_lord_d1 or '?'} "
        f"(dignity in D24: {d24_dignity_of_h5_lord}); "
        f"H9(D24) lord is {h9_lord_d24 or '?'} in {h9_sign_d24 or '?'}.",
        f"Cross-axis strength: {round(cross_factor * 100)}%.",
        f"Dominant stream: {dominant.capitalize()} "
        f"(confidence gap {round(confidence * 100)}%).",
    ]

    return {
        "h5_d1_lord":      h5_lord_d1,
        "h9_d24_lord":    h9_lord_d24,
        "h9_d24_sign":    h9_sign_d24,
        "d24_dignity":     d24_dignity_of_h5_lord,
        "technical":       scores.get("technical", 0.5),
        "humanities":      scores.get("humanities", 0.5),
        "arts":            scores.get("arts", 0.5),
        "dominant_stream": dominant,
        "confidence":      confidence,
        "interpretation":  " ".join(interp_parts),
        "d24_available":   d24_available,  # G21
        # Gap-audit fix (2026-08): diagnostic-only cross-check against the
        # independent D24-lagna read path used by siddhamsha.py. Does not
        # affect any score above; see _check_d24_lagna_consistency().
        "d24_lagna_consistency": _check_d24_lagna_consistency(payload),
    }


# ---------------------------------------------------------------------------
# E-2 · Sub-Branch Compatibility Matrix
# ---------------------------------------------------------------------------

# Format: {sub_branch_key: {planet: weight (0-3), ...}}
# Higher weight = more importance of that planet for the branch.
#
# Gap-audit fix (2026-08): the 8 entries below marked "RECONCILED" were
# previously drifting from jyotish/affinity.py::BRANCH_PLANET_AFFINITY's
# vector for the same real-world field (surfaced by
# check_affinity_table_drift(), above -- e.g. this table named Venus as
# artificial_intelligence's/chemical's/biomedical's/entrepreneurship's
# dominant planet, a karaka that didn't appear in affinity.py's vector for
# those fields at all). Resolution: affinity.py is the primary, live
# scoring table (drives field_methods' actual final_score/ranking) and
# several of its entries carry explicit in-line audit rationale (e.g.
# artificial_intelligence: "T3-B: Rahu dominant (disruption/machines);
# Saturn added (training loops/rules); Ketu 0.25->0.10 (dissolution != ML)";
# architecture: "Mercury raised for spatial geometry; Mars reduced") --
# documented reasoning this table's original entries lacked. Each
# reconciled entry below is affinity.py's own weight vector for the
# matching key, rescaled onto this table's 0-3 display convention
# (multiplied so the top planet lands at 3.0; compute_sub_branch_
# compatibility() normalizes by total_weight, so the rescale changes
# nothing structurally -- only the ABSOLUTE numbers look different,
# relative proportions and therefore ranking/dominant-planet order are
# identical to affinity.py's). This changes E-2 sub-branch tie-break output
# for these 8 fields; it does NOT touch affinity.py or final_score/primary
# ranking in any way. Re-run check_affinity_table_drift() after any future
# edit to either table to confirm no new drift was introduced.
_SUB_BRANCH_CLUSTERS: Dict[str, Dict[str, float]] = {
    # ── Engineering ──────────────────────────────────────────────────────────
    "computer_science":      {"Mercury": 3.0, "Rahu": 2.5, "Moon": 1.0, "Mars": 1.0},
    # RECONCILED (was Mercury/Rahu tie -> Mercury dominant; affinity.py's
    # artificial_intelligence vector is Rahu-dominant, see banner above).
    "artificial_intelligence":{"Rahu":3.0, "Mercury":2.57, "Saturn":1.29, "Ketu":0.86, "Jupiter":0.86},
    "electronics_comm":      {"Mercury": 3.0, "Rahu": 2.0, "Mars": 1.5, "Sun": 1.0},
    "electrical":            {"Sun": 2.5,    "Mars": 2.0, "Mercury": 1.5, "Saturn": 1.0},
    "mechanical":            {"Mars": 3.0,   "Saturn": 2.5, "Sun": 1.5},
    "civil":                 {"Saturn": 3.0, "Mars": 2.0, "Venus": 1.5},
    # RECONCILED (2026-08, updated again after domain review): Venus added
    # back into affinity.py::chemical_engineering as a secondary planet
    # (rasa/formulation signification) -- Mars/Saturn remain tied dominant
    # for the engineering discipline specifically. Mirrors affinity.py's
    # current chemical_engineering vector exactly (rescaled to this file's
    # 0-3 convention); see affinity.py's in-line comment for the full
    # domain-review rationale.
    "chemical":              {"Mars":3.0, "Saturn":3.0, "Mercury":2.54, "Sun":1.5, "Venus":1.5},
    "metallurgy":            {"Mars": 3.0,   "Saturn": 3.0, "Ketu": 2.0},
    # RECONCILED (was Mars/Saturn tie -> Mars dominant; affinity.py's
    # materials_science_engineering vector is clearly Saturn-dominant).
    "materials_science":     {"Saturn":3.0, "Mars":2.57, "Rahu":1.71, "Ketu":1.29},
    # RECONCILED (was Mars-dominant, which does agree with affinity.py's
    # #2 planet, but affinity.py's aerospace_engineering vector is
    # Rahu-dominant, not Mars).
    "aerospace":             {"Rahu":3.0, "Mars":2.57, "Saturn":1.71, "Mercury":1.29},
    # RECONCILED (was Moon-dominant; Venus is absent from affinity.py's
    # biomedical_engineering vector entirely -- Mars is dominant there).
    "biomedical":            {"Mars":3.0, "Mercury":2.5, "Moon":2.5, "Jupiter":2.0},
    "environmental":         {"Moon": 2.5,   "Venus": 2.0, "Saturn": 1.5, "Mercury": 1.0},
    # ── Medical ──────────────────────────────────────────────────────────────
    "surgery":               {"Mars": 3.0,   "Sun": 2.0,  "Saturn": 1.5, "Ketu": 1.0},
    "psychiatry":            {"Moon": 3.0,   "Mercury": 2.5, "Ketu": 1.5, "Saturn": 1.0},
    "pediatrics":            {"Moon": 3.0,   "Jupiter": 2.5, "Venus": 1.5},
    "pharmacology":          {"Mercury": 2.5,"Venus": 2.0,  "Ketu": 1.5, "Moon": 1.0},
    "radiology":             {"Sun": 2.5,    "Mars": 2.0,   "Rahu": 1.5, "Mercury": 1.0},
    "dermatology":           {"Venus": 2.5,  "Moon": 2.0,   "Mercury": 1.5},
    # ── Commerce / Management ────────────────────────────────────────────────
    "finance":               {"Jupiter": 3.0,"Mercury": 2.5, "Venus": 1.5, "Saturn": 1.0},
    # RECONCILED (was Venus/Mercury tie -> Venus dominant; affinity.py's
    # digital_marketing vector is clearly Mercury-dominant, Venus 3rd not 1st).
    "marketing":             {"Mercury":3.0, "Rahu":2.57, "Venus":1.71, "Mars":1.29},
    "hr_management":         {"Venus": 2.5,  "Moon": 2.0,   "Jupiter": 2.0, "Mercury": 1.5},
    "operations_logistics":  {"Saturn": 2.5, "Mars": 2.0,   "Mercury": 1.5},
    # RECONCILED (2026-08, updated again after domain review): Sun added
    # back into affinity.py::entrepreneurship as a secondary planet
    # (self-made-authority signification) -- Mars/Jupiter remain tied
    # dominant. Mirrors affinity.py's current entrepreneurship vector
    # exactly (rescaled to this file's 0-3 convention); see affinity.py's
    # in-line comment for the full domain-review rationale.
    "entrepreneurship":      {"Mars":3.0, "Jupiter":3.0, "Mercury":2.54, "Rahu":1.5, "Sun":1.5},
    # ── Sciences ─────────────────────────────────────────────────────────────
    "physics":               {"Sun": 2.5,    "Saturn": 2.0, "Mercury": 2.0, "Ketu": 1.5},
    "mathematics":           {"Mercury": 3.0,"Saturn": 2.5, "Moon": 1.5,  "Ketu": 1.0},
    "chemistry":             {"Mercury": 2.5,"Venus": 2.0,  "Mars": 1.5,  "Moon": 1.0},
    "biology":               {"Moon": 2.5,   "Jupiter": 2.0,"Venus": 2.0, "Mercury": 1.5},
    "astronomy":             {"Sun": 2.5,    "Rahu": 2.0,   "Saturn": 1.5,"Mercury": 1.5},
    # ── Arts / Design / Humanities ───────────────────────────────────────────
    "law":                   {"Jupiter": 3.0,"Saturn": 2.0, "Sun": 2.0,  "Mercury": 1.5},
    "journalism":            {"Mercury": 3.0,"Rahu": 2.0,   "Moon": 2.0, "Mars": 1.0},
    "psychology":            {"Moon": 3.0,   "Mercury": 2.5,"Ketu": 1.5, "Venus": 1.0},
    "fine_arts":             {"Venus": 3.0,  "Moon": 2.5,   "Rahu": 1.5, "Mercury": 1.0},
    # RECONCILED (was Venus-dominant; affinity.py's architecture vector is
    # Saturn-dominant, per its own in-line audit note "Mercury raised for
    # spatial geometry; Mars reduced" -- Venus is present but 2nd, not 1st).
    "architecture":          {"Saturn":3.0, "Venus":2.25, "Mercury":1.5, "Mars":0.75},
    "education_teaching":    {"Jupiter": 3.0,"Moon": 2.0,   "Mercury": 2.0,"Venus": 1.0},
    "sports":                {"Mars": 3.0,   "Sun": 2.5,    "Rahu": 1.5,  "Saturn": 1.0},
}

# Human-readable labels
_SUB_BRANCH_LABELS: Dict[str, str] = {
    "computer_science": "Computer Science & IT",
    "artificial_intelligence": "AI / Machine Learning",
    "electronics_comm": "Electronics & Communication",
    "electrical": "Electrical Engineering",
    "mechanical": "Mechanical Engineering",
    "civil": "Civil Engineering",
    "chemical": "Chemical Engineering",
    "metallurgy": "Metallurgy & Mining",
    "materials_science": "Materials Science",
    "aerospace": "Aerospace Engineering",
    "biomedical": "Biomedical Engineering",
    "environmental": "Environmental Engineering",
    "surgery": "Surgery",
    "psychiatry": "Psychiatry",
    "pediatrics": "Pediatrics",
    "pharmacology": "Pharmacology",
    "radiology": "Radiology",
    "dermatology": "Dermatology",
    "finance": "Finance & Banking",
    "marketing": "Marketing & Brand",
    "hr_management": "HR & People Management",
    "operations_logistics": "Operations & Logistics",
    "entrepreneurship": "Entrepreneurship",
    "physics": "Physics",
    "mathematics": "Mathematics & Statistics",
    "chemistry": "Chemistry",
    "biology": "Biology & Life Sciences",
    "astronomy": "Astronomy & Astrophysics",
    "law": "Law & Legal",
    "journalism": "Journalism & Media",
    "psychology": "Psychology",
    "fine_arts": "Fine Arts & Design",
    "architecture": "Architecture",
    "education_teaching": "Education & Teaching",
    "sports": "Sports Science",
}


# ---------------------------------------------------------------------------
# Gap-audit fix (2026-08, diagnostic-only, non-scoring): _SUB_BRANCH_CLUSTERS
# above and jyotish/affinity.py::BRANCH_PLANET_AFFINITY are two independently
# -maintained planet-weight tables that cover overlapping ground -- e.g. this
# module's "civil" cluster and affinity.py's "civil_engineering" branch are
# both meant to describe the same real-world field's planetary signature,
# but nothing keeps the two in sync, and compute_sub_branch_compatibility()
# (E-2, below) and affinity.py's compute_branch_affinity_score_llm() are two
# separate scoring paths that could silently drift apart on the same field
# without anyone noticing.
#
# This is intentionally NOT a merge: the two tables serve different
# purposes (_SUB_BRANCH_CLUSTERS is a coarser 0-3 "sub-branch flavor" scale
# used for advisory tie-breaking; BRANCH_PLANET_AFFINITY is the primary,
# validated 0-1-normalized weight vector that field_methods/ actually scores
# against) and merging them would change compute_sub_branch_compatibility's
# and/or the primary affinity score's calibration with no real-chart
# validation behind that change. Instead, only the KEY OVERLAP is curated
# here (pairs where the two modules are unambiguously describing the same
# field -- not guessed via fuzzy string matching, which would risk false
# positives), and a checker flags any pair whose *dominant* (highest-weight)
# planet disagrees, so a human can review real drift without either table
# being auto-corrected.
_SUB_BRANCH_TO_AFFINITY_KEY: Dict[str, str] = {
    "computer_science":     "computer_science_engineering",
    "artificial_intelligence": "artificial_intelligence",
    "electronics_comm":      "electronics_communication_engineering",
    "electrical":            "electrical_engineering",
    "mechanical":            "mechanical_engineering",
    "civil":                 "civil_engineering",
    "chemical":              "chemical_engineering",
    "materials_science":     "materials_science_engineering",
    "aerospace":             "aerospace_engineering",
    "biomedical":            "biomedical_engineering",
    "environmental":         "environmental_engineering",
    "psychiatry":            "psychiatry",
    "finance":               "finance_banking",
    "marketing":             "digital_marketing",
    "entrepreneurship":      "entrepreneurship",
    "physics":               "physics",
    "mathematics":           "mathematics",
    "chemistry":             "chemistry",
    "biology":               "biology",
    "astronomy":             "astronomy_astrophysics",
    "law":                   "law_llb",
    "journalism":            "journalism_media",
    "psychology":            "psychology",
    "fine_arts":             "fine_arts",
    "architecture":          "architecture",
    "education_teaching":    "education_teaching",
    "sports":                "sports_science_management",
    # Deliberately NOT mapped (no unambiguous 1:1 counterpart found in
    # BRANCH_PLANET_AFFINITY -- these are medical specialties / management
    # sub-fields the affinity table does not carry at this granularity):
    # "metallurgy", "surgery", "pediatrics", "pharmacology", "radiology",
    # "dermatology", "hr_management", "operations_logistics".
}


def check_affinity_table_drift() -> List[Dict[str, Any]]:
    """Diagnostic-only (no score/ranking effect): for every curated key pair
    in _SUB_BRANCH_TO_AFFINITY_KEY, compare the dominant (highest-weight)
    planet in this module's _SUB_BRANCH_CLUSTERS entry against the dominant
    planet in jyotish.affinity.BRANCH_PLANET_AFFINITY's entry for the same
    real-world field. Returns a list of disagreement records (empty list =
    no drift detected among the curated pairs).

    Import of jyotish.affinity is deferred to call time (not module level)
    to avoid any import-order fragility, even though affinity.py does not
    currently import edu_align.py (verified: no circular dependency).

    Each disagreement record:
        {sub_branch_key, affinity_key, sub_branch_dominant_planet,
         affinity_dominant_planet, sub_branch_weights, affinity_weights}

    Intended use: call this from a test or a one-off diagnostic script, not
    from the live scoring path -- it does not affect final_score, rank, or
    any per-field output.
    """
    try:
        from .affinity import BRANCH_PLANET_AFFINITY
    except ImportError:
        # Should not happen in a normal install; fail soft since this is a
        # diagnostic utility, not part of the scoring critical path.
        return []

    def _dominant(weights: Dict[str, float]) -> str:
        if not weights:
            return ""
        return max(weights.items(), key=lambda kv: kv[1])[0]

    drift: List[Dict[str, Any]] = []
    for sub_key, affinity_key in _SUB_BRANCH_TO_AFFINITY_KEY.items():
        sub_weights = _SUB_BRANCH_CLUSTERS.get(sub_key, {})
        aff_weights = BRANCH_PLANET_AFFINITY.get(affinity_key, {})
        if not sub_weights or not aff_weights:
            continue  # one side missing the key -- not a drift, a coverage gap
        sub_dom = _dominant(sub_weights)
        aff_dom = _dominant(aff_weights)
        if sub_dom != aff_dom:
            drift.append({
                "sub_branch_key": sub_key,
                "affinity_key": affinity_key,
                "sub_branch_dominant_planet": sub_dom,
                "affinity_dominant_planet": aff_dom,
                "sub_branch_weights": dict(sub_weights),
                "affinity_weights": dict(aff_weights),
            })
    return drift


def compute_sub_branch_compatibility(
    field_id:         str,
    eff_strengths:    Dict[str, float],
    planet_dignities: Dict[str, str],
) -> Dict[str, Any]:
    """E-2: Compute sub-branch compatibility score for a specific branch.

    Args:
        field_id        : Branch key from _SUB_BRANCH_CLUSTERS.
        eff_strengths   : {planet: float} effective strengths from engine.
        planet_dignities: {planet: dignity_str} from D1 chart.

    Returns dict:
        score      : float 0-100
        label      : str  human-readable branch name
        top_planets: list of (planet, contribution) sorted by contribution
        insight    : str
    """
    cluster = _SUB_BRANCH_CLUSTERS.get(field_id)
    if not cluster:
        return {"score": 50.0, "label": field_id, "top_planets": [], "insight": ""}

    total_weight = sum(cluster.values())
    raw_score    = 0.0
    contributions: List[Tuple[str, float]] = []

    for planet, weight in cluster.items():
        eff   = eff_strengths.get(planet, 0.5)
        dign  = planet_dignities.get(planet, "neutral")
        dign_m = {"exalted": 1.3, "own": 1.15, "friendly": 1.05,
                  "neutral": 1.0, "enemy": 0.85, "debilitated": 0.6
                  }.get(str(dign).lower(), 1.0)
        contrib = eff * dign_m * weight / total_weight
        raw_score += contrib
        contributions.append((planet, round(contrib * 100, 1)))

    # Map to 0-100 scale (raw ~0-1.3 range)
    score = min(100.0, max(0.0, raw_score * 77.0))
    contributions.sort(key=lambda x: -x[1])

    top_planet = contributions[0][0] if contributions else ""
    label      = _SUB_BRANCH_LABELS.get(field_id, field_id)
    insight    = (
        f"{label}: dominant driver is {top_planet} "
        f"(contributes {contributions[0][1] if contributions else 0}%). "
        f"Overall branch fit: {round(score)}/100."
    )

    return {
        "score":       round(score, 1),
        "label":       label,
        "top_planets": contributions[:3],
        "insight":     insight,
    }


def rank_sub_branches(
    eff_strengths:    Dict[str, float],
    planet_dignities: Dict[str, str],
    top_n:            int = 10,
) -> List[Dict[str, Any]]:
    """Rank ALL sub-branches by compatibility and return top N."""
    results = []
    for fid in _SUB_BRANCH_CLUSTERS:
        res = compute_sub_branch_compatibility(fid, eff_strengths, planet_dignities)
        res["field_id"] = fid
        results.append(res)
    results.sort(key=lambda r: -r["score"])
    return results[:top_n]


# ---------------------------------------------------------------------------
# E-3 · Per-Exam-Date Transit Success Score
# ---------------------------------------------------------------------------

# Moon nakshatra lords that are broadly auspicious for exam-taking
_EXAM_GOOD_NK_LORDS = {"Jupiter", "Mercury", "Venus", "Moon"}
_EXAM_BAD_NK_LORDS  = {"Saturn", "Rahu", "Ketu", "Mars"}

# Transit houses that boost exam success (from natal lagna)
_EXAM_GOOD_TRANSIT_HOUSES = {1, 3, 5, 9, 10, 11}
_EXAM_BAD_TRANSIT_HOUSES  = {6, 8, 12}


def _legacy_approx_moon_lon(dt: date) -> float:
    """Very rough Moon longitude for a date (±3° error).

    Uses: Moon moves ~13.2°/day from a fixed epoch.
    Epoch 2000-01-01 Moon sidereal ~283° (Lahiri).
    """
    epoch = date(2000, 1, 1)
    days  = (dt - epoch).days
    return (283.0 + 13.176396 * days) % 360


def _legacy_approx_planet_transit_house(planet: str, dt: date, lagna_sign: str) -> int:
    """Return approximate transit house of planet on dt from lagna_sign."""
    try:
        from Job_Career.micro_timing import _get_all_planet_positions  # type: ignore
        dt_obj   = datetime(dt.year, dt.month, dt.day, 6, 0, 0)
        transits = _get_all_planet_positions(dt_obj, lagna_sign)
        house    = transits.get(planet, {})
        if isinstance(house, dict):
            return int(house.get("house", 0) or 0)
        return int(house or 0)
    except Exception:
        return 0


def _canonical_moon_lon(dt: date) -> Optional[float]:
    try:
        from .ephemeris import get_planet_longitudes
        from .llm_policy import AYANAMSHA
        values = get_planet_longitudes(datetime(dt.year, dt.month, dt.day, 12), 0.0, 0.0, AYANAMSHA, 0.0)
        return float(values["Moon"]) if "Moon" in values else None
    except Exception:
        return None


def _canonical_planet_transit_house(planet: str, dt: date, lagna_sign: str) -> int:
    try:
        from .ephemeris import get_transit_house_positions
        from .llm_policy import AYANAMSHA
        houses, _, _ = get_transit_house_positions(
            datetime(dt.year, dt.month, dt.day, 12), 0.0, 0.0,
            lagna_sign, AYANAMSHA, 0.0,
        )
        return int(houses.get(planet, 0) or 0)
    except Exception:
        return 0


def _active_dasha_lord(dasha_seq: List[Dict], target_date: date) -> str:
    """Return the Mahadasha lord active on target_date."""
    for d in dasha_seq:
        try:
            start = _parse_dasha_date(d.get("start_date") or d.get("start", ""))
            end   = _parse_dasha_date(d.get("end_date") or d.get("end", ""))
            if start and end and start <= target_date < end:
                return d.get("lord") or d.get("md_planet") or ""
        except Exception:
            pass
    return ""


def _parse_dasha_date(raw: Any) -> Optional[date]:
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%Y-%m"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _dasha_quality_score(lord: str, eff_strengths: Dict[str, float]) -> float:
    """Return 0-1 quality for a dasha lord based on effective strength."""
    if not lord:
        return 0.5
    raw = eff_strengths.get(lord, 0.5)
    return min(1.0, max(0.0, raw))


# NK lookup (imported from panchang locally to avoid circular import)
_NK_PER_DEG = 360 / 27
_NAKSHATRAS_LIST = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
    "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni",
    "Uttara Phalguni","Hasta","Chitra","Swati","Vishakha",
    "Anuradha","Jyeshtha","Moola","Purva Ashadha","Uttara Ashadha",
    "Shravana","Dhanishtha","Shatabhisha","Purva Bhadrapada",
    "Uttara Bhadrapada","Revati",
]
_NK_LORDS_LIST = ["Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury"]


def compute_exam_day_scores(
    dob:         str,
    lagna_sign:  str,
    dasha_seq:   List[Dict],
    eff_strengths: Dict[str, float],
    exam_dates:  List[Dict[str, Any]],
    today:       Optional[date] = None,
) -> List[Dict[str, Any]]:
    """E-3: Score each exam date on Dasha quality × Moon nakshatra × transit.

    Args:
        dob          : Date of birth string (YYYY-MM-DD or YYYY-MM).
        lagna_sign   : Natal lagna sign string.
        dasha_seq    : List of dasha dicts with {lord, start_date/start, end_date/end}.
        eff_strengths: Effective planetary strengths {planet: float}.
        exam_dates   : List of {"name": str, "date": str|date} dicts.
        today        : Reference date (defaults to date.today()).

    Returns:
        List of scored dicts sorted by score descending.
    """
    today = today or date.today()
    results = []

    for entry in exam_dates:
        exam_name = entry.get("name", "Exam")
        raw_date  = entry.get("date", "")

        # Parse exam date
        exam_date: Optional[date] = None
        if isinstance(raw_date, date):
            exam_date = raw_date
        else:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    exam_date = datetime.strptime(str(raw_date), fmt).date()
                    break
                except ValueError:
                    pass

        if not exam_date:
            continue

        # 1. Dasha quality on exam date
        md_lord      = _active_dasha_lord(dasha_seq, exam_date)
        dasha_score  = _dasha_quality_score(md_lord, eff_strengths)

        # 2. Moon nakshatra on exam date (approximate)
        moon_lon = _canonical_moon_lon(exam_date)
        if moon_lon is None:
            results.append({"exam": exam_name, "date": exam_date.isoformat(),
                            "status": "NOT_COMPUTED", "reason": "EPHEMERIS_UNAVAILABLE"})
            continue
        nk_idx       = int(moon_lon / _NK_PER_DEG) % 27
        nk_name      = _NAKSHATRAS_LIST[nk_idx]
        nk_lord      = _NK_LORDS_LIST[nk_idx % 9]
        nk_score     = (
            0.85 if nk_lord in _EXAM_GOOD_NK_LORDS else
            0.30 if nk_lord in _EXAM_BAD_NK_LORDS  else 0.55
        )

        # 3. Jupiter and Mercury transit quality (key academic planets)
        jup_house  = _canonical_planet_transit_house("Jupiter", exam_date, lagna_sign)
        merc_house = _canonical_planet_transit_house("Mercury", exam_date, lagna_sign)

        def _house_score(h: int) -> float:
            if h in _EXAM_GOOD_TRANSIT_HOUSES:
                return 0.80
            if h in _EXAM_BAD_TRANSIT_HOUSES:
                return 0.25
            return 0.50

        transit_score = (_house_score(jup_house) * 0.6 + _house_score(merc_house) * 0.4)

        # 4. Days from today
        days_away = (exam_date - today).days
        past_flag = days_away < 0

        # Composite score  (weights: dasha 40%, nakshatra 30%, transit 30%)
        composite = round(
            dasha_score * 0.40 + nk_score * 0.30 + transit_score * 0.30,
            3,
        )
        score_100 = round(composite * 100, 1)

        recommendation = (
            "Strong window — prioritise this date" if score_100 >= 72 else
            "Moderate window — adequate with preparation" if score_100 >= 55 else
            "Challenging window — intensive focus required"
        )

        results.append({
            "exam_name":       exam_name,
            "exam_date":       str(exam_date),
            "days_away":       days_away,
            "past":            past_flag,
            "dasha_lord":      md_lord or "Unknown",
            "dasha_score":     round(dasha_score * 100, 1),
            "moon_nakshatra":  nk_name,
            "nakshatra_lord":  nk_lord,
            "nakshatra_score": round(nk_score * 100, 1),
            "jupiter_house":   jup_house,
            "mercury_house":   merc_house,
            "transit_score":   round(transit_score * 100, 1),
            "score":           score_100,
            "recommendation":  recommendation,
        })

    results.sort(key=lambda r: -r["score"])
    return results


# ---------------------------------------------------------------------------
# E-4 · G17 — D24-Driven UG / PG / PhD Tier Recommendation
# ---------------------------------------------------------------------------
# Classical basis: the D24 (Chaturvimshamsha / Siddhamsha) governs formal
# learning and academic destiny (BPHS). Its lagna and lagna lord show the
# native's baseline capacity for structured schooling (-> UG). The 9th house
# of D24 (guru / higher wisdom / advanced specialization) and Jupiter's
# dignity there indicate depth of specialization the native can sustain
# (-> PG). Atmakaraka's placement in D24 H5/H9/H10 — already used in
# field_methods/jaimini.py's per-field "AK in D24" confirmation check — is
# the classical marker of a chart oriented toward advanced academic/
# professional depth; combined with Saturn (multi-year sustained discipline)
# and Ketu (moksha-karaka; the classical significator of research,
# specialization, and solitary deep focus) this indicates aptitude for
# doctoral-level, self-directed research (-> PhD / Research).
#
# This is a standalone advisory signal, same status as compute_d1_d24_
# stream_score (E-1): it does not alter any per-field final_score or the
# registry's tier_map (which already fully describes what UG/PG/PhD options
# exist per field). It answers a different question — not "what tiers does
# this field offer" but "which tier of study does this native's own chart
# favour."

def compute_academic_tier_recommendation(payload: Any) -> Dict[str, Any]:
    """G17: D24-driven UG vs PG vs PhD/Research tier recommendation.

    Args:
        payload: NatalPayloadV2 instance (or any object with the relevant
            d24_lagna_sign / d24_house_lords / d24_planet_dignities /
            eff_strengths / atmakaraka / divisional_charts attributes).

    Returns dict:
        ug_score, pg_score, phd_score : float 0-1
        recommended_tier               : "UG" | "PG" | "PhD / Research"
        confidence                     : float 0-1 (gap between top-2 tiers)
        signals                        : dict of the raw sub-signals used
        interpretation                 : str
        d24_available                  : bool
    """
    d24_lagna       = getattr(payload, "d24_lagna_sign", "") or ""
    d24_house_lords = getattr(payload, "d24_house_lords", {}) or {}
    d24_dignities   = getattr(payload, "d24_planet_dignities", {}) or {}
    eff_strengths   = getattr(payload, "eff_strengths", {}) or {}
    ak              = getattr(payload, "atmakaraka", "") or ""
    d24_chart       = (getattr(payload, "divisional_charts", {}) or {}).get("D24_siddhamsam", {}) or {}

    d24_available = bool(d24_lagna and d24_house_lords)

    def _dw(planet: str) -> float:
        """0-1 dignity weight from d24_planet_dignities, tolerant of casing
        and of dignity strings this build of compute_dignity() may not emit."""
        if not planet:
            return 0.5
        dign = str(d24_dignities.get(planet, "")).upper()
        if dign == "EXALTED":
            return 1.0
        if dign in ("OWN", "MOOLATRIKONA"):
            return 0.85
        if dign == "DEBILITATED":
            return 0.15
        return 0.5

    def _es(planet: str) -> float:
        return float(eff_strengths.get(planet, 1.0)) if planet else 1.0

    # --- UG: D24 lagna lord + Mercury (baseline structured-learning capacity) ---
    lagna_lord_d24 = d24_house_lords.get("1") or _sign_lord(d24_lagna)
    ug_raw = (
        0.50 * _dw(lagna_lord_d24)
        + 0.30 * _dw("Mercury")
        + 0.20 * min(_es(lagna_lord_d24) / 1.3, 1.0)
    )
    ug_score = round(min(1.0, ug_raw), 3)

    # --- PG: D24 9th-house (higher learning) lord + Jupiter dignity ---
    h9_sign_d24 = _nth_sign_from(d24_lagna, 9) if d24_lagna else ""
    h9_lord_d24 = d24_house_lords.get("9") or _sign_lord(h9_sign_d24)
    pg_raw = (
        0.45 * _dw(h9_lord_d24)
        + 0.35 * _dw("Jupiter")
        + 0.20 * min(_es(h9_lord_d24) / 1.3, 1.0)
    )
    pg_score = round(min(1.0, pg_raw), 3)

    # --- PhD/Research: AK in D24 H5/H9/H10, + Saturn discipline, + Ketu depth ---
    ak_bonus = 0.0
    ak_house_note = ""
    if ak and d24_chart:
        d24_lagna_chart = d24_chart.get("Lagna", "") or d24_lagna
        ak_sign_d24 = d24_chart.get(ak, "")
        if ak_sign_d24 and d24_lagna_chart:
            ak_house = _house_distance(d24_lagna_chart, ak_sign_d24)
            if ak_house in (5, 9, 10):
                ak_bonus = 0.30
                ak_house_note = f"Atmakaraka ({ak}) in D24 H{ak_house}"
    phd_raw = (
        ak_bonus
        + 0.30 * _dw("Saturn")
        + 0.25 * _dw("Ketu")
        + 0.15 * min(_es("Saturn") / 1.3, 1.0)
    )
    phd_score = round(min(1.0, phd_raw), 3)

    scores = {"UG": ug_score, "PG": pg_score, "PhD / Research": phd_score}
    if not d24_available:
        # Without a real D24 chart every sub-signal above fell back to
        # neutral defaults (0.5 dignity, 1.0 eff, no AK bonus) — mirror the
        # E-1 pattern (G21) and openly discount the whole recommendation
        # rather than present neutral-driven scores as if they were signal.
        scores = {k: round(v * 0.6, 3) for k, v in scores.items()}

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    recommended_tier = ranked[0][0]
    confidence = round(ranked[0][1] - ranked[1][1], 3)
    if not d24_available:
        confidence = round(confidence * 0.6, 3)

    interpretation = (
        f"D24 lagna lord {lagna_lord_d24 or '?'} shapes UG baseline "
        f"({round(ug_score * 100)}%). 9th-house lord {h9_lord_d24 or '?'} + "
        f"Jupiter shape PG depth ({round(pg_score * 100)}%). "
        f"{ak_house_note or 'Atmakaraka not confirmed in D24 H5/H9/H10'} + "
        f"Saturn/Ketu shape PhD/research aptitude ({round(phd_score * 100)}%). "
        f"Recommended tier: {recommended_tier} (confidence gap {round(confidence * 100)}%)."
        + ("" if d24_available else " [D24 chart data unavailable — scores discounted.]")
    )

    return {
        "ug_score":          ug_score,
        "pg_score":          pg_score,
        "phd_score":         phd_score,
        "recommended_tier":  recommended_tier,
        "confidence":        confidence,
        "interpretation":    interpretation,
        "signals": {
            "d24_lagna_lord":        lagna_lord_d24,
            "d24_h9_lord":           h9_lord_d24,
            "ak_in_d24_5_9_10":      bool(ak_bonus),
            "saturn_d24_dignity":    d24_dignities.get("Saturn", ""),
            "ketu_d24_dignity":      d24_dignities.get("Ketu", ""),
        },
        "d24_available": d24_available,
    }
