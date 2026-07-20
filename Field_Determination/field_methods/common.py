"""Shared helpers for separated field-determination astrology modules."""
from __future__ import annotations

import math as _math
from typing import Any, Dict, List


FIELD_PRIORITY_GROUPS: Dict[str, List[str]] = {
    "life_science": [
        "medicine_mbbs",
        "biomedical_engineering",
        "medical_research",
        "clinical_psychology",
        "neuroscience",
        "psychiatry",
        "public_health",
        "bioinformatics",
        "biotechnology_biochemical_engineering",
        "biotechnology_bsc",
        "molecular_biology_genetics",
        "healthcare_management",
        "pharmacy",
        "forensic_science",
    ],
    "governance_service": [
        "public_policy",
        "civil_services",
        "political_science",
        "development_studies",
        "public_health",
        "criminal_law",
        "law_llb",
        "intelligence_security_studies",
        "defence_strategic_studies",
        "environmental_law",
        "environmental_studies_interdisciplinary",
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

# Gap-8 (audit 2026-07): registry of astro facts that are scored in more than
# one place (multiple method files and/or engine.py gap-boosts), so the
# "5-6 independent methods agree" convergence bonus is partly rewarding the
# same underlying fact restated rather than genuinely independent testimony.
#
# Audit follow-up (2nd pass): investigated whether each row is closeable by
# "delete the duplicate scoring, keep one owner" as originally envisioned.
# Conclusion: for career/field determination specifically, most of these ARE
# legitimately multi-method by design -- e.g. a dusthana-lord affliction is a
# real weakness that KP, KNRao, Jaimini, and Parashara each independently
# care about from their own technique's perspective; deleting that check from
# four of five methods would make them astrologically *less* complete, not
# more correct, purely to reduce a statistical redundancy that the
# correlation discount below already exists to compensate for. Verified each
# row's underlying DATA (not just the scoring decision) is drawn from a
# single shared source rather than independently re-derived per method:
#   - dusthana_lord_penalty:  single shared boosts._dusthana_lord_penalty()
#   - chandra_lagna_h10_lord: single shared common.chandra_lagna_h10_lord() (Gap-14)
#   - cluster_bonus:          single shared boosts._life_science_cluster_bonus() /
#                              _space_aerospace_cluster_bonus()
#   - d10_h10_occupancy:      knrao/kp/parashara already read the single shared
#                              payload_data.d10_house_occupancy; engine.gap_boost's
#                              _d10_h10_bonus() used to independently recompute
#                              the same fact from d10_chart in parallel -- fixed
#                              to accept and prefer the shared occupancy dict
#                              (see boosts._d10_h10_bonus's d10_occupancy param).
# So the real drift risk (two code paths silently computing the same fact
# differently) is now closed for all four rows. What remains -- multiple
# methods each applying their OWN weight to the same shared fact -- is by
# design, not a bug, and correlation_discount_factor() below is the correct
# place to account for it (not deletion from individual methods).
SIGNAL_REGISTRY: Dict[str, List[str]] = {
    "d10_h10_occupancy":        ["knrao", "kp", "parashara", "dashamsha", "engine.gap_boost:d10_h10"],
    "dusthana_lord_penalty":    ["knrao", "kp", "jaimini", "parashara", "engine.gap_boost"],
    "chandra_lagna_h10_lord":   ["knrao", "kp", "jaimini", "parashara"],
    "cluster_bonus":            ["knrao", "jaimini", "parashara", "engine.gap_boost"],
}

# Number of "convergence layers" the T3-A grade currently compares (KNRao, KP,
# Jaimini, Parashara, Dashamsha, Sudarshana). Kept as a constant here (rather
# than importing engine.py, which would create a circular import) so the
# discount formula below and engine.py's convergence block stay in lockstep;
# update both if a layer is ever added/removed.
CONVERGENCE_LAYER_COUNT: int = 6


def correlation_discount_factor(total_layers: int = CONVERGENCE_LAYER_COUNT) -> float:
    """Data-derived replacement for the previously hardcoded 0.6 constant.

    Gap-8 close-out (audit 2026-07): the old `_CORRELATION_DISCOUNT = 0.6` in
    engine.py was a fixed magic number, disconnected from SIGNAL_REGISTRY, so
    it could never improve as duplicated facts got collapsed to a single
    owner. This derives the discount directly from the registry: for each
    tracked fact, `(methods_sharing_it - 1) / (total_layers - 1)` estimates
    what fraction of that fact's cross-method "agreement" is structural
    (shared inputs) rather than independent corroboration. Averaging across
    all tracked facts gives an overall duplication estimate; the discount is
    `1 - 0.5 * avg_duplication`, clamped to a sane band.

    As rows are removed from SIGNAL_REGISTRY (i.e. a fact is refactored to
    have exactly one owning method), avg_duplication falls and this discount
    rises toward 1.0 automatically — no manual recalibration needed. With the
    registry's current 4 rows this evaluates to ~0.65, close to the previous
    flat 0.6, so existing calibration/stress-test behaviour is not shocked.
    """
    if not SIGNAL_REGISTRY or total_layers <= 1:
        return 1.0
    fractions = []
    for methods in SIGNAL_REGISTRY.values():
        n = len(methods)
        frac = (n - 1) / float(total_layers - 1)
        fractions.append(min(1.0, max(0.0, frac)))
    avg_duplication = sum(fractions) / len(fractions)
    discount = 1.0 - 0.5 * avg_duplication
    return round(max(0.4, min(0.9, discount)), 4)

METHOD_SCORE_CAP: float = 30.0

# Gap-1 (audit 2026-07) fix: single source of truth for per-method normalization
# caps. Previously __init__.py kept its own _METHOD_SCORE_CAPS while each method
# file passed a *different* cap to method_result (knrao 80 vs 30, kp 80 vs 60,
# jaimini 80 vs 30) — the bundle silently overwrote the method's own normalized
# score with a contradictory one. Both sides now import this dict.
#
# Recalibration (2026-07, "fix all gaps" pass): the caps above were arbitrary
# and sat well below each method's own declared rubric ceiling (sum of its
# core+support+validation rubric_section caps, from build_score_rubric calls
# in each method file). knrao's ceiling is 60+20+20=100 but was capped at 30;
# jaimini's is 60+25+20=105 but was capped at 30. Since raw scores routinely
# approach their rubric ceiling, both methods saturated their normalized_score
# at 100 for the large majority of charts, destroying rank differentiation
# between fields precisely where the bundle needs it most.
#
# Every method now uses its own declared positive-section ceiling as the cap,
# so "100 normalized" means the same thing across methods: this method fired
# every one of its own scoring rubric sections at full strength. This is the
# only self-consistent choice without a curated outcome dataset to calibrate
# against (see WORLDCLASS_GAP_ANALYSIS.md 6.1 / DEEP_AUDIT item 5.1 — no
# backtesting corpus exists yet). Verify each method file's rubric_section
# calls before changing these; they must stay in sync.
METHOD_SCORE_CAPS: Dict[str, float] = {
    "knrao":      100.0,  # core 60 + support 20 + validation 20
    "kp":          85.0,  # core 40 + support 25 + validation 20
    "jaimini":    105.0,  # core 60 + support 25 + validation 20
    "parashara":   85.0,  # core 40 + support 25 + validation 20
    "dashamsha":   85.0,  # core 40 + support 25 + validation 20
    # Architecture fix (audit): Sudarshana Chakra promoted from a bolt-on,
    # unweighted convergence-only layer (previously computed only inside
    # engine.py's separate confidence-convergence step, with no vote in this
    # bundle) to a first-class 6th method here. score_sudarshana() already
    # returns its score on a native 0-100 scale (3 layers x up to 30 pts +
    # up to 40 pts convergence bonus, clamped), so its cap is 100 directly --
    # unlike the other methods it has no separate core/support/validation
    # rubric split to sum.
    "sudarshana": 100.0,
}


# Gap-18b (audit 2026-07, generalized fix): knrao.py, kp.py, jaimini.py,
# parashara.py, and dashamsha.py each independently derived the text that
# every keyword-gate check (_wm(kw, label) calls scattered across boosts.py /
# constants.py / these method files themselves -- nakshatra-career fit,
# Rahu-house career direction, yoga-domain fit, exalted-domain, karakamsha-
# domain bonuses) matches against, using ONLY `field_id.replace("_", " ")`.
# jyotish/tests/test_keyword_coverage.py already measured the consequence:
# ~55 registry fields share zero vocabulary with any keyword list purely
# because their bare field_id doesn't happen to contain the expected
# substring -- e.g. "international_relations" and "political_science" don't
# contain "law", so they silently receive none of these bonuses no matter
# how strong the underlying planetary support is, while a same-strength
# sibling like "international_law" does. This was diagnosed concretely on a
# real chart: international_relations/political_science scored comparably
# on raw affinity-weighted effective strength to international_law but
# never appeared anywhere in the top-35, purely a downstream scoring-gate
# artifact rather than an astrological difference.
#
# Fix: build the gate text from field_id AND the registry's own descriptive
# text (label/field/track/specialization/niche/description) when a registry
# entry is supplied, so a field is reachable by a keyword cluster if EITHER
# its id OR its human-written description shares vocabulary with it. This is
# a one-time, per-field-call enrichment (not a per-field keyword-list edit),
# so every current and future field benefits automatically -- it does not
# special-case international_relations/political_science or any other
# specific field_id. Falls back to the old field_id-only text when no
# registry entry is passed, so existing callers/tests without the new
# optional argument keep their exact prior behaviour.
def build_gate_text(field_id: str, field_entry: Dict[str, Any] = None) -> str:
    """Build the searchable text used by keyword-gate checks for a field.

    Combines the bare field_id (e.g. "international_relations" ->
    "international relations") with the registry's descriptive fields when
    available, so keyword gates hand-curated against one vocabulary (e.g.
    "law", "diplomacy", "foreign policy") can still fire for a field whose
    id alone doesn't contain that word but whose registry description does.
    """
    base = field_id.replace("_", " ").lower()
    if not field_entry:
        return base
    extra_parts = [
        field_entry.get("label", ""),
        field_entry.get("field", ""),
        field_entry.get("track", ""),
        field_entry.get("specialization", ""),
        field_entry.get("niche", ""),
        field_entry.get("description", ""),
    ]
    extra = " ".join(str(p) for p in extra_parts if p).lower()
    return f"{base} {extra}".strip()


def chandra_lagna_h10_lord(planets_d1: Dict) -> str:
    """Lord of the 10th sign counted from the Moon's sign (Chandra Lagna H10).

    Gap-14 (audit 2026-07) fix: this helper was re-implemented with copy-paste
    variations inside knrao.py, kp.py, jaimini.py and parashara.py. Centralised
    here so the four methods cannot drift.
    """
    from jyotish.constants import _SIGN_LORD, _SIGN_NUM
    signs = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda x: x[1])]
    moon_sign = ((planets_d1 or {}).get("Moon") or {}).get("sign", "")
    if not moon_sign or moon_sign not in _SIGN_NUM:
        return ""
    return _SIGN_LORD.get(signs[(_SIGN_NUM[moon_sign] - 1 + 9) % 12], "")
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
    """Package one method's score.

    Contraindication-channel fix ("methods cannot go negative", 2026-07): every
    method file used to pre-clamp its own accumulator with `clamp_score(score)`
    before calling this function, so a chart with heavy contraindications
    (dusthana + combustion + vitality penalties outweighing any positives)
    already arrived here floored at 0 — indistinguishable from a bland neutral
    chart with no signal at all either way. Method files now pass their *raw*
    signed accumulator (which can be negative) so that sign survives here as
    `raw_signed_score`, while `score`/`normalized_score` keep their existing
    0-100-ish contract (still floored at 0) so every existing consumer of
    those two fields is unaffected. `is_net_negative` lets the bundle give a
    real (but bounded) voice to net-contraindicated methods instead of
    silently treating them the same as "no data" — see
    field_methods/__init__.py's `_has_data` / `net_contraindication_index`.
    """
    raw = float(score)
    signal_state = "NEGATIVE" if raw < 0 else "NEUTRAL" if raw == 0 else "POSITIVE"
    return {
        "method": name,
        "score": round(clamp_score(score), 2),
        "normalized_score": normalize_method_score(score, normalization_cap or METHOD_SCORE_CAP),
        "raw_signed_score": round(raw, 2),
        "is_net_negative": raw < 0.0,
        "calculation_status": "COMPUTED",
        "signal_state": signal_state,
        "status_semantics": "NEUTRAL_IS_DISTINCT_FROM_NOT_COMPUTED_OR_FAILED",
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
        "brahma_lord":         getattr(payload_data, "brahma_lord", "") or "",
        "maheshwara_lord":     getattr(payload_data, "maheshwara_lord", "") or "",
        "upapada":             getattr(payload_data, "upapada_lagna", "") or "",
    } | {
        "atmakaraka":          getattr(payload_data, "atmakaraka", "") or "",
        "amatyakaraka":        getattr(payload_data, "amatyakaraka", "") or "",
        "d10_strength":        getattr(payload_data, "d10_strength", {}) or {},
        "sav_points_houses":   getattr(payload_data, "sav_points_houses", {}) or {},
        "d10_house_occupancy": getattr(payload_data, "d10_house_occupancy", {}) or {},
        "detected_yogas":      getattr(payload_data, "detected_yogas", []) or [],
    }


def prioritize_rows(rows: List[Dict], priority_field_ids: List[str]) -> List[Dict]:
    """Bring a priority cluster to the front without dropping any rows."""
    priority_set = {fid: i for i, fid in enumerate(priority_field_ids)}
    front = [row for row in rows if row.get("field_id", "") in priority_set]
    front.sort(key=lambda r: priority_set.get(r.get("field_id", ""), 999))
    rest  = [row for row in rows if row.get("field_id", "") not in priority_set]
    rest.sort(key=lambda r: -r.get("final_score", 0))
    return front + rest
