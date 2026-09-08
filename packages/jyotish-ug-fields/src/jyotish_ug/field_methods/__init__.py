"""Separated astrology scoring bundle for field determination."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping
from jyotish.evidence_integrity import build_signal_lineage
from jyotish.rule_registry import signal_class

from .knrao import score_knrao
from .kp import score_kp
from .jaimini import score_jaimini, compute_jaimini_field_timing  # Phase-4c: Chara Dasha forward timing
from .parashara import score_parashara
from .dashamsha import score_dashamsha, _d10_house_lord
from .confidence_dimensions import compute_confidence_dimensions
from .career_archetype import discover_career_archetype  # Stage 3: chart-level, additive-only
from .chart_synthesis import (  # 2026-08 architecture-audit gap-fix: chart-level, additive-only
    build_structural_graph,
    build_planet_pattern_graph,
    build_d24_learning_profile,
)
from .purpose_chain import (  # 2026-08 architecture-audit gap-fix (Gaps 9/11/12): deterministic, non-LLM
    build_purpose_chain,
    build_career_expression_chain,
)
from .sudarshana import score_sudarshana
from .siddhamsha import score_siddhamsha  # Phase-1 remediation: D24 as 7th voting method
from .shashtiamsha import score_d60_vote  # Phase-2 remediation: D60 as 8th voting method (small weight)
from .structural_patterns import score_structural_patterns  # Stage 1: D1 house-occupancy clustering as 9th voting method
from .navamsha import score_navamsha_adjustment  # Phase-2 remediation: D9 as bounded post-blend multiplier
from .yogini_dasha import score_yogini_dasha_adjustment  # GAP FIX (2026-08-17): Yogini Dasha as bounded post-blend multiplier (Step 7)
from .gochara import score_gochara  # GAP FIX (2026-08-18, audit item A): Gochara transit timing as 10th voting method
from jyotish.dasha_longevity import score_dasha_longevity  # GAP FIX (2026-08-17): Vimshottari longevity filter (Step 7)
from jyotish.step9_convergence import score_convergence  # GAP FIX (2026-08-17): Step 9 multi-method convergence
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

# gap fix 2026-08-18 (E): why classical Vimshopaka Bala weighting (jyotish/
# vimshopaka.py, plus the reduced 7-varga jyotish/boosts.py::
# _vimsopaka_bala_coefficient consumed inside dashamsha.py/navamsha.py/
# siddhamsha.py/shashtiamsha.py-adjacent D-chart tiers) and METHOD_WEIGHTS
# below are NOT redundant -- they operate at two different levels of the same
# decision:
#   * Vimshopaka Bala weights how STRONG a given planet is, WITHIN one varga's
#     own scoring (a dignity-aggregation technique, BPHS Ch.6) -- it nudges a
#     single tier's own score up/down based on that tier's chosen planets'
#     cross-varga strength.
#   * METHOD_WEIGHTS (below) weights how much that tier's OVERALL VERDICT
#     counts relative to the other seven-plus voting methods in the blended
#     bundle -- a question of classical authority-per-question-type (see the
#     comment immediately below), not of any individual planet's strength.
# A varga tier can therefore have a strong internal Vimshopaka Bala nudge
# while still carrying a small METHOD_WEIGHTS share (e.g. gochara), or vice
# versa -- the two numbers answer different questions and are applied at
# different points in the pipeline (inside one method's own score, vs across
# the bundle of method scores), so both are required and neither subsumes
# the other.
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
    "knrao":      0.1678,
    # §9 remediation (2026-08-19): per spec, KP is a CROSS-VERIFICATION
    # layer -- it must act only as a modest confirmation bonus (5-10%) on
    # planets already supported by other evidence, never generate
    # independent score or introduce an otherwise-unsupported planet. At
    # 0.0629 it was still a full independent voting share driving a ~20-
    # component sub-scoring engine (H10 branch, sublord, sub-sub-lord,
    # nakshatra, ruling planets, clusters) with no cap tying it to a
    # confirmation role. Reduced to near-zero here so it no longer carries
    # meaningful independent voting weight; its real role is now the
    # bounded kp_confirmation post-blend multiplier below (mirrors the D9/
    # Yogini/longevity confirmation-layer pattern), which only ever nudges
    # a field already supported by the primary methods.
    "kp":         0.015,
    "jaimini":    0.1538,
    "parashara":  0.1049,
    "dashamsha":  0.1538,
    # Architecture fix (audit): Sudarshana Chakra (K.N. Rao's triple-ascendant
    # Lagna+Surya+Chandra H10 confirmation technique) used to sit entirely
    # outside this bundle -- computed only inside engine.py as a separate,
    # differently-weighted "convergence layer" multiplier with no vote here
    # and no representation in method_agreement/method_conflict. It is a
    # confirmatory/cross-check technique rather than a primary field-
    # determination method (the same reasoning that keeps KP's prior low),
    # so it receives a comparably modest prior.
    # §9 remediation (2026-08-19): still too high a prior for a technique
    # the spec explicitly scopes to a bounded 5-10% confirmation bonus --
    # at 0.0559 Sudarshana ran as a standalone 0-100 point scorer (with
    # convergence/triple-lock bonuses stacking past 100 before clamping)
    # and independently voted on the blend. Reduced to near-zero; its real
    # role is now the bounded sudarshan_confirmation post-blend multiplier
    # below, computed with the unmatched-affinity floor OFF (see
    # sudarshana.py's apply_unmatched_floor param) so it can never assign
    # non-zero score to a planet with zero other karaka support -- the
    # exact behavior §9 prohibits.
    "sudarshana": 0.01,
    # Phase-1 remediation (2026-08 gap-audit): Siddhamsha (D24) -- BPHS's
    # dedicated vidya varga -- promoted from a non-voting confirmation helper
    # to a first-class 7th method. Given 0.19, the highest single prior in
    # the bundle: for an EDUCATION-field question specifically (as opposed to
    # the vocation/career question this bundle originally answered), D24 is
    # the single most classically authoritative technique available, ahead
    # of even Dashamsha (D10, the career varga) and Jaimini karakamsha.
    # §6 remediation (2026-08): per spec, Siddhamsha (D24) is a study-capacity/
    # aptitude confirmation layer, not a primary career-field determinant --
    # BPHS treats it as the vidya varga (learning/education), one step removed
    # from vocation itself. At its previous 0.1748 prior it was the single
    # LARGEST voting share in the entire blend, which let a strong D24 signal
    # (e.g. "can study this field") directly inflate final_score/hard_lockout
    # eligibility for a field the person may never build a durable career in
    # (D10/Dashamsha says otherwise). Reduced to a near-zero prior so D24 no
    # longer meaningfully swings the blend or the eligibility gate; its
    # classical value is preserved instead as an explicit divergence flag
    # (see method_entries["siddhamsha"]["d24_d10_divergence"] below) rather
    # than as blend voting power. combine_weighted_scores() self-normalizes
    # (total_weight = sum(weights.values())), so this redistributes its old
    # share proportionally across the other methods automatically.
    "siddhamsha": 0.02,
    # Phase-2 remediation (2026-08 gap-audit): Shashtiamsha (D60) -- the
    # finest-grained classical confirmation varga -- added as an 8th voting
    # method at a deliberately small prior (0.05). D60 is a fine-grained
    # tiebreaker by classical convention, not a primary determination
    # technique, so it should never out-vote D24/Dashamsha/Jaimini; its role
    # is to nudge close rankings using subtle deity-quality evidence the
    # grosser charts don't carry. All eight priors above are rescaled
    # proportionally (x0.95) from their previous values (which summed to 1.0
    # on their own) to make room for it while preserving relative ordering.
    # §6 remediation (2026-08): per spec, Shashtiamsha (D60) is a fine-grained
    # TIE-BREAKER only, classically applied to distinguish between otherwise-
    # close candidates -- never a primary voting method with a standing share
    # of the main blend. At 0.046 it still contributed directly to
    # final_score/hard_lockout eligibility for every field, not just close
    # ties. Reduced to a near-zero prior here so D60 stops acting as a
    # permanent weight in the main blend/eligibility gate; its real tie-break
    # role is preserved in jyotish/tiered_ranking.py's Tier-3
    # (TIER3_METHODS), which already exists specifically to apply D60 (and
    # structural_patterns) only when Tier-1/Tier-2 leave a near-tie
    # (NEAR_TIE_BAND). combine_weighted_scores() self-normalizes, so this
    # redistributes its old share proportionally across the other methods.
    "shashtiamsha": 0.01,
    # Stage 1 (Astro-OS v3 gap-audit implementation plan, 2026-08):
    # Structural Pattern Analysis (D1 house-occupancy clustering --
    # kendra/trikona dominance + stellium concentration) added as a 9th
    # voting method. Conservative starting prior (0.08) -- NOT the source
    # proposal's suggested 35-40%, since no validated benchmark exists for
    # that number (see Stage 0's harness). All nine priors above are
    # rescaled proportionally (x0.92) from their previous values (which
    # summed to 1.0 on their own) to make room for it while preserving
    # relative ordering. Like every other method here, its effective weight
    # is still adjusted per-chart by the data-quality/clarity/outlier gating
    # below, so a chart with an unusually decisive structural pattern can
    # still push this method's effective weight well above this base prior.
    "structural_patterns": 0.08,
    # GAP FIX (2026-08-18, audit item A): Gochara (transit) timing tier added
    # as a 10th voting method, at an even more conservative prior (0.05) than
    # structural_patterns' 0.08. Rationale: gochara is a TIMING technique
    # classically used to refine WHEN a field's supporting yogas activate,
    # not a primary technique for determining WHICH field fits (the same
    # reasoning that keeps KP's prior low) -- and unlike the other nine
    # methods it reads only two planets over one house/sign locus, a narrow
    # evidence surface. Not rescaled from the other nine priors (unlike
    # earlier additions) since the blend renormalizes _qa_weights to sum=1
    # after quality/clarity/outlier adjustment (see _qa_total below) --
    # adding this key is purely additive and does not require rebalancing
    # the others to preserve their relative ordering.
    "gochara": 0.05,
}

# 2026-08-18 fix (audit item #12): the priors above mix two very different
# kinds of evidence -- some (knrao/kp/jaimini/parashara/dashamsha/sudarshana/
# siddhamsha/shashtiamsha) are grounded in explicit classical-authority
# reasoning about which technique BPHS/Jaimini-sutra/KP doctrine treats as
# primary for a vocation question (see the comments above each). Others
# (structural_patterns, and any future method added the same conservative
# way) are provisional/placeholder priors explicitly chosen because no
# validated benchmark exists yet -- structural_patterns' own comment above
# says so directly ("NOT the source proposal's suggested 35-40%"). That
# distinction previously lived only in source comments, invisible to anyone
# consuming the bundle's output. METHOD_PRIOR_BASIS makes it queryable data:
# "classical" = doctrine-grounded authority prior, "provisional" = a
# conservative placeholder pending empirical validation. Surfaced below as
# `method_prior_basis` in the returned bundle. Purely additive -- does not
# change any weight, score, or existing output key.
METHOD_PRIOR_BASIS: Dict[str, str] = {
    "knrao":        "classical",
    "kp":           "classical",
    "jaimini":      "classical",
    "parashara":    "classical",
    "dashamsha":    "classical",
    "sudarshana":   "classical",
    "siddhamsha":   "classical",
    "shashtiamsha": "classical",
    "structural_patterns": "provisional",
    "gochara": "provisional",
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
    "siddhamsha": {
        "weight": METHOD_WEIGHTS["siddhamsha"],
        "score_cap": _METHOD_SCORE_CAPS["siddhamsha"],
        "coverage": [
            "d24_lagna_lord_strength", "vidya_karaka_strength",
            "vidya_house_lord_support", "curriculum_fit", "combustion_penalty",
        ],
        "notes": "Phase-1 remediation: standalone D24 Siddhamsha scorer. BPHS's "
                 "dedicated vidya varga, evaluated as a self-contained chart with "
                 "its own lagna/lords anchored to the 4th/5th/9th education houses "
                 "and Mercury/Jupiter/Venus as vidya karakas -- previously computed "
                 "but never voted (independent_vote: False).",
    },
    "shashtiamsha": {
        "weight": METHOD_WEIGHTS["shashtiamsha"],
        "score_cap": _METHOD_SCORE_CAPS["shashtiamsha"],
        "coverage": ["d60_deity_quality"],
        "notes": "Phase-2 remediation: D60 deity-quality confirmation wired in as an "
                 "8th voting method at a deliberately small prior -- a fine-grained "
                 "tiebreaker per classical convention, not a co-equal vote with "
                 "D24/Dashamsha/Jaimini.",
    },
}


class FieldDeterminationInputError(ValueError):
    """Raised by compute_field_method_bundle() for a genuinely required
    input that is missing/malformed, in place of an unguarded AttributeError/
    TypeError surfacing much later deep inside an arbitrary method file.

    GAP FIX (2026-08-18, audit item J): before this fix, compute_field_
    method_bundle() had NO input validation at its own entry point. Its
    `payload_data` param is already accessed defensively everywhere
    (getattr(payload_data, "...", default) throughout _input_snapshot() and
    every method scorer -- confirmed by grep across knrao/kp/jaimini/
    parashara/dashamsha/sudarshana/siddhamsha/shashtiamsha/structural_
    patterns/gochara), so payload_data itself is deliberately left
    unvalidated here: it is genuinely optional-ish today (even None
    round-trips through every getattr() call without raising), and adding a
    new requirement for it would be inventing a restriction that doesn't
    exist today, not tightening an existing implicit one.

    `field_affinity`, by contrast, is NOT accessed defensively: grep across
    every method file (`field_affinity.get(...)`, `.items()`, `.values()`)
    shows over 100 unconditional attribute accesses that already assume
    field_affinity is a real Mapping. Passing None (or a list/str) today
    already crashes -- just late, inside an arbitrary sub-method, with a
    confusing "NoneType has no attribute get" traceback that gives no hint
    which of the ten method files it happened in or that the actual mistake
    was at the call site. This validates that ALREADY-IMPLICIT requirement
    at the one place a caller can fix it, converting a late unguarded crash
    into an immediate, clear one. No new requirement is added: every real
    caller (jyotish/engine.py's two call sites, tests/
    test_career_track_regressions.py) already always passes a real dict.
    """


def _validate_bundle_inputs(
    payload_data: Any, domain: str, field_affinity: Any, field_id: str,
) -> None:
    if field_affinity is None or not isinstance(field_affinity, Mapping):
        raise FieldDeterminationInputError(
            "compute_field_method_bundle(): field_affinity must be a dict-like "
            f"Mapping of planet -> affinity weight, got {type(field_affinity).__name__!r}. "
            "Every method scorer in this bundle calls field_affinity.get(...)/.items() "
            "unconditionally, so this would otherwise fail later with a confusing "
            "AttributeError deep inside an arbitrary method file instead of here."
        )
    if domain is None:
        raise FieldDeterminationInputError(
            "compute_field_method_bundle(): domain must not be None (pass '' for "
            "'no domain' -- domain is used as a plain string throughout the bundle's "
            "keyword-gate and house-signification cross-checks)."
        )
    if field_id is None:
        raise FieldDeterminationInputError(
            "compute_field_method_bundle(): field_id must not be None (pass '' for "
            "'no field_id' -- field_id is used as a plain string/dict key throughout)."
        )


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
    # GAP FIX (2026-08-18, audit item J): validate the genuinely
    # already-implicit-required inputs before any getattr/access below.
    # See FieldDeterminationInputError's own docstring for the full
    # rationale on why only field_affinity/domain/field_id are checked
    # (payload_data is deliberately left unvalidated -- it is already
    # accessed defensively everywhere via getattr(..., default)).
    _validate_bundle_inputs(payload_data, domain, field_affinity, field_id)
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
        # 2026-08-18 bug fix (real-chart wiring of tiered_selection.py): these
        # five entries dropped the method's signed accumulator, unlike the five
        # built below (sudarshana/siddhamsha/shashtiamsha/structural_patterns/
        # gochara) which already thread it through. `score` is clamp_score()d at
        # 0, so a net-CONTRAINDICATED method was indistinguishable from a
        # neutral one for any consumer reading method_log -- which silently
        # disabled tiered_selection.py's sign-based corroboration gate on
        # exactly the three authorities it gates (dashamsha/jaimini/kp).
        # Additive only: no existing consumer reads these keys off method_log.
        "raw_signed_score": knrao.get("raw_signed_score", round(knrao["score"], 2)),
        "is_net_negative": bool(knrao.get("is_net_negative", False)),
        "components": knrao.get("components", {}),
        "trace": knrao.get("trace", []),
        "score_rubric": knrao.get("score_rubric", {}),
        # Phase B (shadow-score migration, audit item A): additive passthrough
        # of score_knrao()'s metadata dict (now includes confirming_planets)
        # -- no existing consumer reads this key off method_log.
        "metadata": knrao.get("metadata", {}),
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
        # 2026-08-18 bug fix (real-chart wiring of tiered_selection.py): these
        # five entries dropped the method's signed accumulator, unlike the five
        # built below (sudarshana/siddhamsha/shashtiamsha/structural_patterns/
        # gochara) which already thread it through. `score` is clamp_score()d at
        # 0, so a net-CONTRAINDICATED method was indistinguishable from a
        # neutral one for any consumer reading method_log -- which silently
        # disabled tiered_selection.py's sign-based corroboration gate on
        # exactly the three authorities it gates (dashamsha/jaimini/kp).
        # Additive only: no existing consumer reads these keys off method_log.
        "raw_signed_score": kp.get("raw_signed_score", round(kp["score"], 2)),
        "is_net_negative": bool(kp.get("is_net_negative", False)),
        "components": kp.get("components", {}),
        "trace": kp.get("trace", []),
        "score_rubric": kp.get("score_rubric", {}),
        # Phase B (shadow-score migration, audit item A): additive passthrough
        # of score_kp()'s metadata dict (now includes confirming_planets) --
        # no existing consumer reads this key off method_log.
        "metadata": kp.get("metadata", {}),
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
        # 2026-08-18 bug fix (real-chart wiring of tiered_selection.py): these
        # five entries dropped the method's signed accumulator, unlike the five
        # built below (sudarshana/siddhamsha/shashtiamsha/structural_patterns/
        # gochara) which already thread it through. `score` is clamp_score()d at
        # 0, so a net-CONTRAINDICATED method was indistinguishable from a
        # neutral one for any consumer reading method_log -- which silently
        # disabled tiered_selection.py's sign-based corroboration gate on
        # exactly the three authorities it gates (dashamsha/jaimini/kp).
        # Additive only: no existing consumer reads these keys off method_log.
        "raw_signed_score": jaimini.get("raw_signed_score", round(jaimini["score"], 2)),
        "is_net_negative": bool(jaimini.get("is_net_negative", False)),
        "components": jaimini.get("components", {}),
        "trace": jaimini.get("trace", []),
        "score_rubric": jaimini.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),  # Gap-6 fix: exec time, not strength
    }

    # Phase-4c remediation (2026-08 gap-audit): Jaimini Chara Dasha forward
    # timing -- "when this field becomes favorable," not just "is it
    # favorable now." Auxiliary output only; does not feed final_score (see
    # compute_jaimini_field_timing's own docstring for why).
    _jaimini_timing = compute_jaimini_field_timing(payload_data, field_affinity, field_id, domain)

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
        # 2026-08-18 bug fix (real-chart wiring of tiered_selection.py): these
        # five entries dropped the method's signed accumulator, unlike the five
        # built below (sudarshana/siddhamsha/shashtiamsha/structural_patterns/
        # gochara) which already thread it through. `score` is clamp_score()d at
        # 0, so a net-CONTRAINDICATED method was indistinguishable from a
        # neutral one for any consumer reading method_log -- which silently
        # disabled tiered_selection.py's sign-based corroboration gate on
        # exactly the three authorities it gates (dashamsha/jaimini/kp).
        # Additive only: no existing consumer reads these keys off method_log.
        "raw_signed_score": parashara.get("raw_signed_score", round(parashara["score"], 2)),
        "is_net_negative": bool(parashara.get("is_net_negative", False)),
        "components": parashara.get("components", {}),
        "trace": parashara.get("trace", []),
        "score_rubric": parashara.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),  # Gap-6 fix: exec time, not strength
    }

    # T1-A: Dashamsha (D10) — 5th method: BPHS primary career varga
    t0 = time.perf_counter()
    dashamsha = score_dashamsha(payload_data, domain, field_affinity, field_id, field_entry)
    _d10_lagna = ((getattr(payload_data, "divisional_charts", {}) or {}).get("D10_dashamsha", {}) or {}).get("Lagna", "")
    # Gap-audit fix (2026-08, round 4, real-data validation on Swastik's
    # chart): this display used the shared D1 10th-house lord
    # (`inputs["h10_lord"]`, D1 house_lords["10"]) under the dashamsha
    # method's own "h10_lord" label, even though dashamsha.py internally
    # derives and scores D10's OWN 10th lord (from D10's own lagna, not
    # D1's) -- a different planet on a real chart. Confirmed: for Swastik's
    # chart this showed inputs.h10_lord == "Moon" (D1's H10 lord) while the
    # method's own trace correctly described "D10 H10 lord Mars ... OWN --
    # primary dashamsha career yoga" (D10's own H10 lord, from D10 lagna
    # Cancer). Scoring was unaffected (dashamsha.py always used its own
    # internally-derived D10 H10 lord correctly) -- this was a display-only
    # mismatch. Now derives D10's own H10 lord for the label, mirroring
    # dashamsha.py's own whole-sign derivation.
    _d10_h10_lord = _d10_house_lord(_d10_lagna, 10) if _d10_lagna else ""
    method_entries["dashamsha"] = {
        "name": "Dashamsha D10 (BPHS Career Varga)",
        "weight": METHOD_WEIGHTS["dashamsha"],
        "score_cap": _METHOD_SCORE_CAPS["dashamsha"],
        "inputs": {
            "d10_lagna": _d10_lagna,
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
            "h10_lord": _d10_h10_lord,
        },
        "score": round(dashamsha["score"], 2),
        "normalized_score": round(dashamsha.get("normalized_score", 0.0), 2),
        # 2026-08-18 bug fix (real-chart wiring of tiered_selection.py): these
        # five entries dropped the method's signed accumulator, unlike the five
        # built below (sudarshana/siddhamsha/shashtiamsha/structural_patterns/
        # gochara) which already thread it through. `score` is clamp_score()d at
        # 0, so a net-CONTRAINDICATED method was indistinguishable from a
        # neutral one for any consumer reading method_log -- which silently
        # disabled tiered_selection.py's sign-based corroboration gate on
        # exactly the three authorities it gates (dashamsha/jaimini/kp).
        # Additive only: no existing consumer reads these keys off method_log.
        "raw_signed_score": dashamsha.get("raw_signed_score", round(dashamsha["score"], 2)),
        "is_net_negative": bool(dashamsha.get("is_net_negative", False)),
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

    # Phase-1 remediation (2026-08 gap-audit): Siddhamsha (D24) -- 7th voting
    # method. BPHS's dedicated vidya varga; previously computed in
    # siddhamsha.py but marked independent_vote=False and never reached
    # final_score. Signature/contract now matches the other six scorers.
    t0 = time.perf_counter()
    siddhamsha = score_siddhamsha(payload_data, domain, field_affinity, field_id, field_entry)
    # Gap-audit fix (2026-08, round 3): this display-only fallback was missing
    # the lowercase "lagna" key check that siddhamsha.py's own internal
    # d24_lagna derivation already has, so the audit's method_log.siddhamsha.
    # inputs.d24_lagna showed "" even when the real score computation
    # succeeded with a resolved lagna (confirmed on a live Midhula-chart run,
    # 2026-08-14: inputs.d24_lagna == "" while the score itself was 19.92,
    # i.e. computed correctly against a real D24 lagna). Now mirrors
    # siddhamsha.py's fallback chain exactly.
    _d24_chart_for_display = (getattr(payload_data, "divisional_charts", {}) or {}).get("D24_siddhamsam", {}) or {}
    _d24_lagna = (
        _d24_chart_for_display.get("Lagna", "") or _d24_chart_for_display.get("lagna", "")
        or getattr(payload_data, "d24_lagna_sign", "") or ""
    )  # Phase-6 fix: compute_d24_chart's flat dict has no "Lagna" key; see siddhamsha.py note.
    method_entries["siddhamsha"] = {
        "name": "Siddhamsha D24 (BPHS Vidya Varga)",
        "weight": METHOD_WEIGHTS["siddhamsha"],
        "score_cap": _METHOD_SCORE_CAPS["siddhamsha"],
        "inputs": {
            "d24_lagna": _d24_lagna,
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
        },
        "score": round(siddhamsha["score"], 2),
        "normalized_score": round(siddhamsha.get("normalized_score", 0.0), 2),
        "raw_signed_score": siddhamsha.get("raw_signed_score", siddhamsha["score"]),
        "is_net_negative": siddhamsha.get("is_net_negative", False),
        "components": siddhamsha.get("components", {}),
        "trace": siddhamsha.get("trace", []),
        "score_rubric": siddhamsha.get("score_rubric", {}),
        # 2026-08 architecture-audit gap-fix: same allow-list-drop bug class
        # documented elsewhere in this file (d9_navamsha_confirmation's own
        # comment, structural_graph/purpose_chain's own comment below) --
        # curriculum_fit_breakdown (Gap 4 transparency) and d24_missing_planets
        # were added to siddhamsha.py's own return dict but silently dropped
        # here since this block only ever copied a fixed key set.
        "curriculum_fit_breakdown": siddhamsha.get("curriculum_fit_breakdown", {}),
        "d24_missing_planets": siddhamsha.get("d24_missing_planets", []),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    # §6 remediation (2026-08): explicit D24-vs-D10 divergence flag. Per spec,
    # a strong D24 (aptitude/capacity to study or learn the field) alongside a
    # weak D10 (Dashamsha, the dedicated career/livelihood varga) means "can
    # study this field, may not build a durable career in it" -- a real,
    # classically meaningful signal that was previously invisible once D24's
    # blend weight was reduced to near-zero above. Surfaced here rather than
    # folded back into the score, so it stays a transparent flag, not a vote.
    _d24_norm = float(siddhamsha.get("normalized_score", siddhamsha.get("score", 0.0)) or 0.0)
    _d10_norm = float(method_entries.get("dashamsha", {}).get("normalized_score", 0.0) or 0.0)
    _d24_d10_gap = round(_d24_norm - _d10_norm, 2)
    method_entries["siddhamsha"]["d24_d10_divergence"] = {
        "d24_normalized_score": round(_d24_norm, 2),
        "d10_normalized_score": round(_d10_norm, 2),
        "gap": _d24_d10_gap,
        "flag": bool(_d24_norm >= 65.0 and _d10_norm <= 40.0),
        "finding": (
            "Strong aptitude/capacity signal (D24) but weak career/livelihood "
            "signal (D10/Dashamsha) for this field -- may indicate the person "
            "can study or excel academically in this field without it "
            "becoming a durable, income-sustaining career."
            if (_d24_norm >= 65.0 and _d10_norm <= 40.0)
            else ""
        ),
    }

    # Phase-2 remediation (2026-08 gap-audit): Shashtiamsha (D60) -- 8th
    # voting method, small prior. score_d60_vote() already returns a native
    # 0-100 score, so it slots in like sudarshana with no extra normalization.
    t0 = time.perf_counter()
    shashtiamsha = score_d60_vote(payload_data, domain, field_affinity, field_id, field_entry)
    method_entries["shashtiamsha"] = {
        "name": "Shashtiamsha D60 (Finest-Grade Confirmation)",
        "weight": METHOD_WEIGHTS["shashtiamsha"],
        "score_cap": _METHOD_SCORE_CAPS["shashtiamsha"],
        "inputs": {
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
        },
        "score": round(shashtiamsha["score"], 2),
        "normalized_score": round(shashtiamsha.get("normalized_score", 0.0), 2),
        "raw_signed_score": shashtiamsha.get("raw_signed_score", shashtiamsha["score"]),
        "is_net_negative": shashtiamsha.get("is_net_negative", False),
        "components": shashtiamsha.get("components", {}),
        "trace": shashtiamsha.get("trace", []),
        "score_rubric": shashtiamsha.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

    # Stage 1 (Astro-OS v3 gap-audit implementation plan, 2026-08):
    # Structural Pattern Analysis (D1 house-occupancy clustering) -- 9th
    # voting method, conservative starting prior. See structural_patterns.py
    # module docstring for the full design rationale.
    t0 = time.perf_counter()
    structural_patterns = score_structural_patterns(payload_data, domain, field_affinity, field_id, field_entry)
    method_entries["structural_patterns"] = {
        "name": "Structural Pattern Analysis (D1 House Clustering)",
        "weight": METHOD_WEIGHTS["structural_patterns"],
        "score_cap": _METHOD_SCORE_CAPS["structural_patterns"],
        "inputs": {
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
        },
        "score": round(structural_patterns["score"], 2),
        "normalized_score": round(structural_patterns.get("normalized_score", 0.0), 2),
        "raw_signed_score": structural_patterns.get("raw_signed_score", structural_patterns["score"]),
        "is_net_negative": structural_patterns.get("is_net_negative", False),
        "components": structural_patterns.get("components", {}),
        "trace": structural_patterns.get("trace", []),
        "score_rubric": structural_patterns.get("score_rubric", {}),
        "exec_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

    # GAP FIX (2026-08-18, audit item A): Gochara (transit) timing tier --
    # 10th voting method. See gochara.py module docstring for full design
    # rationale (voting-tier pattern chosen over yogini_dasha.py's
    # post-blend-multiplier pattern, which the audit flagged as
    # architecturally inconsistent).
    t0 = time.perf_counter()
    gochara = score_gochara(payload_data, domain, field_affinity, field_id, field_entry)
    method_entries["gochara"] = {
        "name": "Gochara (Jupiter/Saturn Transit over Natal 10th)",
        "weight": METHOD_WEIGHTS["gochara"],
        "score_cap": _METHOD_SCORE_CAPS["gochara"],
        "inputs": {
            "domain": domain,
            "top_affinity": inputs["top_affinity"],
            "h10_lord": inputs["h10_lord"],
        },
        "score": round(gochara["score"], 2),
        "normalized_score": round(gochara.get("normalized_score", 0.0), 2),
        "raw_signed_score": gochara.get("raw_signed_score", gochara["score"]),
        "is_net_negative": gochara.get("is_net_negative", False),
        "components": gochara.get("components", {}),
        "trace": gochara.get("trace", []),
        "score_rubric": gochara.get("score_rubric", {}),
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
        "siddhamsha": 1.0,  # Phase-1: gates on D24 chart presence below
        "shashtiamsha": 1.0,  # Phase-2: score_d60_vote already self-gates via its own MISSING status
        # Stage 1 fix (2026-08): structural_patterns was added to
        # METHOD_WEIGHTS/method_entries but this hardcoded per-method dict
        # (copy-pasted per new method the same way _data_quality/_clarity_mult/
        # _outlier_mult are each separately keyed by method name) was never
        # updated, so the `for k in METHOD_WEIGHTS: ... _data_quality[k]`
        # loop below KeyError'd the moment a real chart reached this line --
        # confirmed via a live run (swastik_chart_details.json, 2026-08-14)
        # that crashed exactly here. score_structural_patterns() already
        # self-gates on D1 house-occupancy presence internally (see its own
        # early-exit branches), so -- same convention as sudarshana just
        # above -- no additional external data-quality gate is needed here.
        "structural_patterns": 1.0,
        # GAP FIX (2026-08-18, audit item A): score_gochara() already
        # self-gates on transit-snapshot availability internally (returns
        # MISSING/score 0 when no transit data can be resolved, live-computed
        # or otherwise) -- same convention as sudarshana/structural_patterns
        # above, no additional external data-quality gate needed here.
        "gochara": 1.0,
    }
    _d24_present = bool(getattr(payload_data, "divisional_charts", {}).get("D24_siddhamsam"))
    _kp_cusps_present = bool(getattr(payload_data, "kp_cusps", {}))
    _karam_present = bool(getattr(payload_data, "karakamsha", ""))
    _d10_present = bool(_d10_lagna)  # T1-A: gate D10 method on chart availability
    # Phase-1 remediation: D24 absence used to only ever cost knrao a 0.75x
    # discount (its D24-gating multiplier), even though D24 missing means
    # THIS chart's education-specific evidence is genuinely absent, not just
    # one career-method's secondary check. Now siddhamsha itself is zeroed
    # out (it IS the D24 method — no D24 data, no vote, same convention as
    # dashamsha/_d10_present below) and knrao's own discount is removed so
    # the same missing fact isn't penalized twice across two methods.
    if not _d24_present:      _data_quality["siddhamsha"] *= 0.00  # D24 chart absent → skip
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

    # §8 remediation (2026-08-19): AK/AmK/Yogakaraka double-counting risk,
    # flagged as a live cross-cutting risk during the §7/§8 audit -- the
    # same karaka status (e.g. a planet that is simultaneously Atmakaraka
    # AND Yogakaraka AND the field's dominant-affinity planet) is
    # independently rewarded by knrao's role-weight multiplier, jaimini's
    # karaka-weight matrix, boosts.py's _yogakaraka_bonus(), and Vimshopaka
    # Bala applied inside both methods -- with no shared ledger stopping
    # the same underlying chart fact from being counted repeatedly across
    # the blend. Rebuilding four separate scorers to share one ledger is
    # out of scope for a contained fix (see "adapt existing architecture"
    # decision); instead, when the SAME planet is confirmed to be both this
    # chart's Atmakaraka and its Yogakaraka (the strongest, rarest overlap
    # case, where the double-reward risk is most acute), knrao and jaimini
    # -- the two methods whose karaka-role logic most directly reads this
    # overlap -- get the same weaker-member dampening the d1_synthesis
    # group above already applies for a different double-counting risk.
    _ak_for_dampen = getattr(payload_data, "atmakaraka", "") or ""
    _lagna_for_dampen = getattr(payload_data, "lagna_sign", "") or ""
    try:
        from jyotish.boosts import _YOGAKARAKA_PLANET as _YK_TABLE_DAMPEN
        _yk_for_dampen = _YK_TABLE_DAMPEN.get(_lagna_for_dampen, "")
    except Exception:
        _yk_for_dampen = ""
    if _ak_for_dampen and _ak_for_dampen == _yk_for_dampen:
        _karaka_group = [m for m in ("knrao", "jaimini") if m in _qa_weights]
        if len(_karaka_group) == 2:
            _strongest_k = max(_karaka_group, key=lambda m: _qa_weights[m])
            for _m in _karaka_group:
                if _m != _strongest_k:
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

    # Gap-audit fix (2026-08, diagnostic-only — does NOT change _sav_conf_mult
    # or combined/final_score below): the classically-correct, Trikona+
    # Ekadhipatya-shodhana-reduced SAV total (jyotish/ashtakavarga.py::
    # compute_sav_points_shodhita) is deliberately NOT used for the
    # confidence gate above, because the >=360/>=340/<=300/<=280 thresholds
    # were empirically set against the RAW (unreduced) total; swapping the
    # input without recalibrating those thresholds would silently
    # miscalibrate every chart's confidence multiplier. That remains true
    # here — the gate above is untouched. What's new is visibility: compute
    # what the shodhita total is and what confidence tier it WOULD fall
    # into under the same thresholds, so a chart where the two totals
    # disagree enough to flip tiers is surfaced (e.g. in reports/QA) instead
    # of being an invisible, uninvestigated possibility.
    _sav_total_shodhita_p4 = sum(
        (getattr(payload_data, "sav_points_houses_shodhita", {}) or {}).values()
    )

    def _sav_tier(total: float) -> str:
        if total <= 0:
            return "unknown"
        if total >= 360:
            return "strong"
        if total >= 340:
            return "above_average"
        if total <= 280:
            return "weak"
        if total <= 300:
            return "below_average"
        return "average"

    _sav_raw_tier = _sav_tier(_sav_total_p4)
    _sav_shodhita_tier = _sav_tier(_sav_total_shodhita_p4)
    _sav_shodhita_diagnostic = {
        "raw_total": _sav_total_p4,
        "shodhita_total": _sav_total_shodhita_p4,
        "raw_confidence_tier": _sav_raw_tier,
        "shodhita_confidence_tier": _sav_shodhita_tier,
        "live_confidence_multiplier_uses": "raw_total",
        "tiers_agree": (
            _sav_shodhita_tier in ("unknown", _sav_raw_tier)
            or _sav_raw_tier == "unknown"
        ),
    }

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

    # §9 remediation (2026-08-19): KP and Sudarshana Chakra converted from
    # near-independent voting methods (see the reduced-to-near-zero
    # METHOD_WEIGHTS["kp"]/["sudarshana"] priors above) into bounded
    # post-blend CONFIRMATION multipliers, matching the D9/Yogini/longevity
    # pattern immediately below. Per spec §9: "modest confirmation bonus
    # (5-10%) on planets already supported by other evidence... never
    # generate independent score or introduce an otherwise-unsupported
    # planet." Both multipliers are therefore GATED on the field already
    # having real support from the primary blend (`combined` at this point,
    # after the primary/D24/D10/etc. voting methods but before any
    # confirmation layer) -- below the gate threshold, neither KP nor
    # Sudarshana can move the score at all, so they can never introduce an
    # otherwise-unsupported field/planet into contention.
    _CROSS_VERIFY_SUPPORT_GATE = 45.0   # combined must already be at/above this to receive any confirmation nudge
    _CROSS_VERIFY_MULT_MIN = 0.95
    _CROSS_VERIFY_MULT_MAX = 1.08       # within spec's 5-10% ceiling

    _kp_normalized = method_normalized_scores.get("kp", 0.0)
    if combined >= _CROSS_VERIFY_SUPPORT_GATE:
        # Map 0-100 KP normalized score to a bounded +/-8% nudge around 1.0
        # (50 = neutral), rather than letting KP's own ~20-component
        # sub-engine move the score by its full raw magnitude.
        _kp_confirmation_multiplier = round(
            min(_CROSS_VERIFY_MULT_MAX, max(_CROSS_VERIFY_MULT_MIN,
                1.0 + (_kp_normalized - 50.0) / 50.0 * 0.08)),
            4,
        )
    else:
        _kp_confirmation_multiplier = 1.0
    combined = round(combined * _kp_confirmation_multiplier, 2)
    raw_combined = round(raw_combined * _kp_confirmation_multiplier, 2)

    # Sudarshana: recomputed here with apply_unmatched_floor=False so the
    # confirmation-bonus version can never assign non-zero score to a
    # planet with zero other karaka support (the method_entries["sudarshana"]
    # display/audit score above keeps the floor ON for its own, separate,
    # documented purpose -- see sudarshana.py's apply_unmatched_floor note).
    _sud_confirmation_raw = score_sudarshana(
        _sud_label, field_affinity, payload_data, apply_unmatched_floor=False,
    )
    _sud_confirmation_normalized = min(100.0, float(_sud_confirmation_raw.get("score", 0.0) or 0.0))
    if combined >= _CROSS_VERIFY_SUPPORT_GATE:
        _sudarshan_confirmation_multiplier = round(
            min(_CROSS_VERIFY_MULT_MAX, max(_CROSS_VERIFY_MULT_MIN,
                1.0 + (_sud_confirmation_normalized - 50.0) / 50.0 * 0.08)),
            4,
        )
    else:
        _sudarshan_confirmation_multiplier = 1.0
    combined = round(combined * _sudarshan_confirmation_multiplier, 2)
    raw_combined = round(raw_combined * _sudarshan_confirmation_multiplier, 2)

    # Phase-2 remediation (2026-08 gap-audit): D9 (Navamsha) applied as a
    # bounded post-blend confirmation multiplier, not a 9th weighted vote --
    # classically D9 confirms whether a D1/D24 promise "comes true" rather
    # than independently determining the field, so it acts on the already-
    # blended combined score instead of diluting the primary methods' weight.
    _d9_result = score_navamsha_adjustment(payload_data, domain, field_affinity, field_id, field_entry)
    _d9_multiplier = _d9_result.get("multiplier", 1.0)
    combined = round(combined * _d9_multiplier, 2)
    raw_combined = round(raw_combined * _d9_multiplier, 2)

    # GAP FIX (2026-08-17): Yogini Dasha as a bounded post-blend confirmation
    # multiplier -- same architectural pattern as D9 immediately above (a
    # secondary/alternative dasha system used classically to confirm or add
    # timing nuance, not to independently determine the field). Framework
    # Step 7 explicitly names Yogini Dasha alongside Vimshottari; this was
    # previously absent from the whole Field_Determination engine.
    _yogini_result = score_yogini_dasha_adjustment(payload_data, field_affinity)
    _yogini_multiplier = _yogini_result.get("multiplier", 1.0)
    combined = round(combined * _yogini_multiplier, 2)
    raw_combined = round(raw_combined * _yogini_multiplier, 2)

    # GAP FIX (2026-08-17): Vimshottari-based dasha-longevity filter — the
    # harder half of framework Step 7 that neither engine previously
    # implemented at all. Rewards fields whose significators have long,
    # stable dasha support ahead; mildly (bounded, never exclusionary)
    # dampens fields resting only on a soon-ending strong-affinity lord.
    # Bounded, applied as the same kind of post-blend confirmation
    # multiplier as D9 and Yogini Dasha above.
    # §8 remediation (2026-08-19): now also passes Atmakaraka/Amatyakaraka/
    # Yogakaraka/strongest-planet so score_dasha_longevity() can apply the
    # §8.3 special-weight criteria -- previously none of these four
    # criteria were referenced anywhere in the longevity filter.
    _dasha_seq = getattr(payload_data, "dasha_sequence", []) or []
    _current_age = getattr(payload_data, "current_age", None)
    _ak_for_longevity = getattr(payload_data, "atmakaraka", "") or ""
    _amk_for_longevity = getattr(payload_data, "amatyakaraka", "") or ""
    _lagna_sign_for_yk = getattr(payload_data, "lagna_sign", "") or ""
    try:
        from jyotish.boosts import _YOGAKARAKA_PLANET as _YK_TABLE
        _yk_for_longevity = _YK_TABLE.get(_lagna_sign_for_yk, "")
    except Exception:
        _yk_for_longevity = ""
    _eff_for_longevity = getattr(payload_data, "eff_strengths", {}) or {}
    _strongest_for_longevity = (
        max(_eff_for_longevity, key=_eff_for_longevity.get) if _eff_for_longevity else ""
    )
    _longevity_result = score_dasha_longevity(
        _dasha_seq, _current_age, field_affinity,
        atmakaraka=_ak_for_longevity,
        amatyakaraka=_amk_for_longevity,
        yogakaraka=_yk_for_longevity,
        strongest_planet=_strongest_for_longevity,
    )
    _longevity_multiplier = _longevity_result.get("multiplier", 1.0)
    combined = round(combined * _longevity_multiplier, 2)
    raw_combined = round(raw_combined * _longevity_multiplier, 2)

    # GAP FIX (2026-08-17): Step 9 -- literal multi-method convergence.
    # Groups the nine methods by shared evidentiary root (via
    # jyotish.evidence_integrity.METHOD_DEPENDENCY_GROUPS, the same map
    # build_signal_lineage() already uses) so D1-correlated methods
    # (parashara/knrao/structural_patterns) count as ONE vote, not three.
    # A field's convergence_count/tier is surfaced in full below
    # (see "step9_convergence" in the returned dict) for a caller that
    # wants Phase B "strict framework mode" (jyotish.step9_convergence.
    # rank_by_strict_convergence) to re-sort a full candidate list by
    # convergence first; by default here it only applies as a small bounded
    # multiplier (Phase A, matches the D9/Yogini/longevity pattern above),
    # never a penalty -- a field short on confirming groups is still fully
    # included, per the framework's own "still included for completeness".
    _convergence_result = score_convergence(method_normalized_scores)
    _convergence_multiplier = _convergence_result.get("multiplier", 1.0)
    combined = round(combined * _convergence_multiplier, 2)
    raw_combined = round(raw_combined * _convergence_multiplier, 2)

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
    # 2026-08 architecture-audit gap-fix: method_breakdown is built fresh
    # above from a fixed 4-key set (score/normalized_score/weight/
    # weighted_contribution), NOT copied from method_entries -- so setting
    # method_entries["siddhamsha"]["curriculum_fit_breakdown"] alone (done
    # where that entry is built, above) never actually reached this dict.
    # Confirmed by direct test: method_breakdown["siddhamsha"] lacked the
    # key even though method_entries["siddhamsha"] had it. Merge the extra
    # per-method transparency fields in explicitly, here, where the real
    # export dict is assembled.
    if "siddhamsha" in method_breakdown and "siddhamsha" in method_entries:
        method_breakdown["siddhamsha"]["curriculum_fit_breakdown"] = (
            method_entries["siddhamsha"].get("curriculum_fit_breakdown", {})
        )
        method_breakdown["siddhamsha"]["d24_missing_planets"] = (
            method_entries["siddhamsha"].get("d24_missing_planets", [])
        )

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

    # GAP-FIX (P0-5, factual/doctrine/heuristic signal separation): tag every
    # emitted component with its rule_registry classification so a consumer
    # (UI, report, LLM explanation prompt) can distinguish a raw calculated
    # fact / classical-doctrine signal from a modern engineering heuristic
    # without a full data-model rewrite. Computed once per unique component
    # key (the same key can appear under multiple methods) rather than the
    # much larger per-method breakdown, to keep this cheap.
    _all_component_keys = {ck for m in components.values() for ck in m}
    signal_provenance = {ck: signal_class(ck) for ck in _all_component_keys}

    _signal_lineage = build_signal_lineage(method_scores)
    # Stage 4 (Astro-OS v3 gap-audit implementation plan, 2026-08):
    # multi-dimensional confidence decomposition, additive -- does not touch
    # final_score or any existing method's output. See
    # confidence_dimensions.py's module docstring for the full rationale.
    _confidence_dimensions = compute_confidence_dimensions(
        payload_data, domain, field_affinity, field_id,
        {k: round(v, 2) for k, v in method_normalized_scores.items()},
    )
    # Stage 3 (Astro-OS v3 gap-audit implementation plan, 2026-08): career
    # archetype discovery, additive/read-only -- a CHART-level (not
    # field-level) descriptive output. Computed once per call like the other
    # additive dimensions above; does not touch final_score, method_scores,
    # or field ranking in any way. See career_archetype.py's module
    # docstring for why this stays a separate narrative signal rather than
    # gating/replacing the validated per-field affinity blend.
    _career_archetype = discover_career_archetype(payload_data)

    # 2026-08 architecture-audit gap-fix (Gaps 2/3/5/7): chart-level,
    # additive-only, same pattern/rationale as _career_archetype above --
    # computed once per chart (not per field), never touches final_score,
    # method_scores, or ranking. See chart_synthesis.py's module docstring.
    _structural_graph = build_structural_graph(payload_data)
    _planet_pattern_graph = build_planet_pattern_graph(payload_data)
    _d24_learning_profile = build_d24_learning_profile(payload_data)

    # 2026-08 architecture-audit gap-fix (Gaps 9/11/12): deterministic,
    # non-LLM Purpose -> Motivation -> Mechanism -> Expression reasoning
    # chain. Stage 1/2 (soul_purpose/vocational_motivation) are chart-level;
    # Stage 4 (career_expression) is assembled per-field here since it
    # terminates at THIS candidate field's label -- cheap, pure assembly,
    # reuses _planet_pattern_graph computed just above rather than
    # recomputing Stage 3. See purpose_chain.py's module docstring.
    _purpose_chain = build_purpose_chain(payload_data)
    _career_reasoning_chain = build_career_expression_chain(
        _purpose_chain, _planet_pattern_graph,
        (field_entry or {}).get("label", field_id), domain,
    )

    return {
        "d9_navamsha_confirmation": _d9_result,
        "yogini_dasha_confirmation": _yogini_result,  # GAP FIX (2026-08-17)
        "vimshottari_longevity_filter": _longevity_result,  # GAP FIX (2026-08-17)
        "step9_convergence": _convergence_result,  # GAP FIX (2026-08-17)
        "jaimini_chara_dasha_timing": _jaimini_timing,
        "confidence_dimensions": _confidence_dimensions,
        "career_archetype": _career_archetype,
        "structural_graph": _structural_graph,
        "planet_pattern_graph": _planet_pattern_graph,
        "d24_learning_profile": _d24_learning_profile,
        "purpose_chain": _purpose_chain,
        "career_reasoning_chain": _career_reasoning_chain,
        "method_scores": method_scores,
        "method_normalized_scores": {k: round(v, 2) for k, v in method_normalized_scores.items()},
        "method_weighted_contributions": method_weighted_contributions,
        "method_weights": {k: round(effective_weights.get(k, METHOD_WEIGHTS[k]), 4) for k in method_scores},
        "method_authority_priors": {k: METHOD_WEIGHTS[k] for k in method_scores},
        # 2026-08-18 fix (audit item #12): see METHOD_PRIOR_BASIS above.
        "method_prior_basis": {k: METHOD_PRIOR_BASIS.get(k, "provisional") for k in method_scores},
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
        "signal_provenance": signal_provenance,
        "method_conflict": _method_conflict,
        "net_contraindication_index": net_contraindication_index,
        "net_negative_methods": [k for k, v in _net_negative_flags.items() if v],
        "sav_shodhita_diagnostic": _sav_shodhita_diagnostic,
        "method_signal_clarity": {k: round(v, 3) for k, v in _clarity.items()},
        "method_clarity_multiplier": {k: round(v, 3) for k, v in _clarity_mult.items()},
        "method_outlier_multiplier": {k: round(v, 3) for k, v in _outlier_mult.items()},
        "priority_groups": FIELD_PRIORITY_GROUPS,
        "method_log": method_entries,
        "trace": trace,
        "method_components": components,
        "inputs_snapshot": inputs,
    }
