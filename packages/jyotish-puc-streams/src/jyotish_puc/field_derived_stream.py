"""field_derived_stream.py — OPTIONAL, capped, score-affecting rubric input
that reverse-derives a Science/Commerce/Humanities distribution from
Field_Determination's adult engine, for the SAME chart, and folds it into
Stream_Determination's own score_stream() as an 8th evidence section.

This is NOT cross_validate.py (which only compares, never scores) and NOT
"an eighth independent astrological method" -- it reuses the same D1/D24/
Jaimini/planetary-strength chart facts already scored elsewhere in this
engine, filtered through a different (adult-engine, vocational-branch)
lens. It is explicitly labelled DERIVED_CORRELATED evidence, default-off,
and capped small (see FIELD_DERIVED_EVIDENCE_CAP) specifically because it is
correlated with, not independent of, the other 7 sections.

Known, documented limitation (do not remove this caveat without re-deriving
it): the base quantity used here, pre_norm_score, is the adult engine's raw
chain-total score BEFORE its per-chart 20-100 min-max display stretch (see
jyotish/engine.py -- final_score IS that population-relative stretch, which
would make an 80 in one chart incomparable to an 80 in another, so it is
deliberately NOT used here). However pre_norm_score is not a purely
permanent/natal number either -- dasha/timing-readiness boosts (peak-career
dasha, chara-dasha timing, antardasha affinity, etc.) are summed into the
same running total before the pre_norm_score/final_score split ever
happens, and the engine does not expose a separately-reported timing-free
component. So this section's evidence is best described as "adult-engine
overall fit, including some dasha-timing contribution" rather than a purely
permanent astrological signal -- stated explicitly in this section's output
note rather than claimed away.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .adult_engine_bridge import FieldEngineSnapshot, safe_get_field_engine_snapshot
from .field_stream_mapping import STREAM_IDS, exclusivity, get_affinity

FIELD_DERIVED_EVIDENCE_CAP = 6.0

# A field below this pre_norm_score is treated as too weak to be defensible
# corroborating evidence at all (this is NOT the adult engine's own
# hard_lockout threshold -- it's a separate, more conservative floor for
# this supplementary section specifically).
MIN_PRE_NORM_SCORE = 15.0

# Minimum usable-field count / mapping coverage below which this section
# declines to contribute any score at all rather than extrapolate from too
# little evidence.
MIN_USABLE_FIELDS = 5
MIN_MAPPING_COVERAGE = 0.40

# Diminishing-return weights for up to 3 sibling fields within one family,
# so (e.g.) seven near-identical aerospace-adjacent leaves don't outvote a
# family with fewer, more distinct members.
_FAMILY_MEMBER_WEIGHTS = (1.0, 0.35, 0.15)


def _family_key(field_row: Dict[str, Any]) -> str:
    """Reuse the SAME family identity Field_Determination's own
    competency_ontology.py::compute_family_aggregates()/get_family_id()
    already assigns (career_family_label), rather than inventing a second,
    parallel family taxonomy that could silently drift from the first."""
    return field_row.get("career_family_label") or field_row.get("career_family") or field_row.get("field_id", "")


def _group_by_family(fields: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for f in fields:
        groups.setdefault(_family_key(f), []).append(f)
    return groups


def _family_contribution(members: List[Dict[str, Any]]) -> float:
    ranked = sorted(members, key=lambda m: -(m.get("pre_norm_score") or 0.0))
    total = 0.0
    for weight, member in zip(_FAMILY_MEMBER_WEIGHTS, ranked):
        total += weight * (member.get("pre_norm_score") or 0.0)
    return total


def derive_stream_marks_from_field_determination(
    payload: Any, *, snapshot: Optional[FieldEngineSnapshot] = None,
) -> Dict[str, Any]:
    """Compute the field-derived stream-evidence section for one chart.
    Never raises internally beyond what safe_get_field_engine_snapshot()
    already guards; returns a data_status-tagged dict either way.

    OPTIMIZATION: pass `snapshot=` an already-fetched FieldEngineSnapshot
    (e.g. one early_age_stream_engine.py already fetched for
    cross_validate.py in the same CLI run) to avoid running the adult
    engine a second time for the same chart. If omitted, fetches its own."""
    snapshot: FieldEngineSnapshot = snapshot if snapshot is not None else safe_get_field_engine_snapshot(payload)

    base_result = {
        "enabled": True,
        "independence_class": "DERIVED_CORRELATED",
        "primary_signal": False,
        "source_engine": "Field_Determination",
        "source_engine_version": snapshot.engine_version,
        "source_scoring_contract_version": snapshot.scoring_contract_version,
        "age_appropriateness": "SUPPLEMENTARY_ONLY",
        "excluded_components": [
            "route_feasibility", "preference_alignment", "recommendation_score",
            "market_or_college_practicality",
        ],
        "note": (
            "Supplementary cross-engine evidence: reverse-derives a Science/"
            "Commerce/Humanities distribution from Field_Determination's adult "
            "engine run on this SAME chart, using pre_norm_score (pre-display-"
            "normalization chain total, NOT the population-relative final_score) "
            "aggregated by career-family and mapped to streams via a fractional "
            "affinity table (see field_stream_mapping.py). This section is "
            "DERIVED_CORRELATED, not independent, evidence -- it reuses the same "
            "underlying D1/D24/Jaimini/planetary-strength chart facts scored "
            "elsewhere in this engine, filtered through the adult vocational-"
            "branch lens. pre_norm_score also still carries some dasha/timing-"
            "readiness contribution (the adult engine does not report a purely "
            "permanent/natal component separately) -- treat this section as "
            "'adult-engine overall fit', not a purely permanent astrological signal."
        ),
    }

    if snapshot.warnings or not snapshot.fields:
        return {
            **base_result,
            "data_status": "UNAVAILABLE",
            "marks": {s: 0.0 for s in STREAM_IDS},
            "warnings": list(snapshot.warnings) or ["No field-engine results available"],
        }

    usable = [f for f in snapshot.fields if (f.get("pre_norm_score") or 0.0) >= MIN_PRE_NORM_SCORE]
    if len(usable) < MIN_USABLE_FIELDS:
        return {
            **base_result,
            "data_status": "INSUFFICIENT_FIELD_EVIDENCE",
            "marks": {s: 0.0 for s in STREAM_IDS},
            "usable_field_count": len(usable),
            "warnings": [f"Only {len(usable)} usable fields (< {MIN_USABLE_FIELDS} minimum)"],
        }

    families = _group_by_family(usable)
    raw_stream_totals = {s: 0.0 for s in STREAM_IDS}
    mapped_family_count = 0
    unmapped_families: List[str] = []

    for family_label, members in families.items():
        top_member = max(members, key=lambda m: (m.get("pre_norm_score") or 0.0))
        affinity = get_affinity(
            top_member.get("field_id", ""), family_label, top_member.get("domain", ""),
        )
        if affinity is None:
            unmapped_families.append(family_label)
            continue
        mapped_family_count += 1
        family_score = _family_contribution(members)
        excl = exclusivity(affinity)
        for stream_id in STREAM_IDS:
            raw_stream_totals[stream_id] += family_score * affinity.get(stream_id, 0.0) * excl

    family_count = len(families)
    mapping_coverage = (mapped_family_count / family_count) if family_count else 0.0

    total = sum(raw_stream_totals.values())
    if total <= 0.0 or mapping_coverage < MIN_MAPPING_COVERAGE:
        return {
            **base_result,
            "data_status": "INSUFFICIENT_FIELD_EVIDENCE",
            "marks": {s: 0.0 for s in STREAM_IDS},
            "usable_field_count": len(usable),
            "family_count": family_count,
            "mapped_family_count": mapped_family_count,
            "mapping_coverage": round(mapping_coverage, 3),
            "warnings": (
                ["No positively-mapped stream evidence"] if total <= 0.0 else
                [f"Mapping coverage {mapping_coverage:.0%} below {MIN_MAPPING_COVERAGE:.0%} minimum"]
            ),
        }

    raw_distribution = {s: raw_stream_totals[s] / total for s in STREAM_IDS}

    # Reliability: usable-field count, mapping coverage, and family breadth
    # all discount how far this section's distribution is allowed to pull
    # away from a neutral 1/3-each split -- thin or poorly-mapped evidence
    # shrinks toward neutral rather than asserting a strong opinion.
    # NOTE (engineered, not classically derived): the 20/8 denominators below
    # and the 0.5/0.3/0.2 blend weights are tuned constants, not sourced
    # values -- same disclosure as stream_scoring.py's weighted_strength
    # scale-constant note (~L2226-2239): "nothing in the astrological
    # literature specifies" these particular thresholds/weights; they were
    # picked so reliability behaves reasonably across typical inputs, not
    # derived from any formal mapping. Treat as unvalidated tuning.
    field_count_factor = min(1.0, len(usable) / 20.0)
    family_breadth_factor = min(1.0, family_count / 8.0)
    reliability = max(0.0, min(1.0, mapping_coverage * 0.5 + field_count_factor * 0.3 + family_breadth_factor * 0.2))

    neutral = 1.0 / len(STREAM_IDS)
    shrunk = {s: neutral + reliability * (raw_distribution[s] - neutral) for s in STREAM_IDS}
    shrunk_total = sum(shrunk.values()) or 1.0
    adjusted_distribution = {s: shrunk[s] / shrunk_total for s in STREAM_IDS}

    marks = {s: round(FIELD_DERIVED_EVIDENCE_CAP * adjusted_distribution[s], 3) for s in STREAM_IDS}

    return {
        **base_result,
        "data_status": "COMPUTED",
        "population_scope": "ADULT_ENGINE_TOP_35_FAMILY_AGGREGATED",
        "usable_field_count": len(usable),
        "family_count": family_count,
        "mapped_family_count": mapped_family_count,
        "mapping_coverage": round(mapping_coverage, 3),
        "unmapped_families": unmapped_families,
        "reliability": round(reliability, 3),
        "raw_distribution": {s: round(v, 3) for s, v in raw_distribution.items()},
        "adjusted_distribution": {s: round(v, 3) for s, v in adjusted_distribution.items()},
        "marks": marks,
        "warnings": [],
    }


def safe_derive_stream_marks(
    payload: Any, *, snapshot: Optional[FieldEngineSnapshot] = None,
) -> Dict[str, Any]:
    """Error-safe wrapper -- guarantees a zero-contribution, UNAVAILABLE
    result instead of raising, for callers (score_stream() via
    compute_stream_determination()) that must never let this optional
    section take down the primary stream score.

    Pass `snapshot=` a pre-fetched FieldEngineSnapshot to reuse an adult-
    engine run already done elsewhere in the same CLI invocation (see
    early_age_stream_engine.py's run_for_payload(), which fetches one
    shared snapshot for both this and cross_validate.py when both features
    are enabled)."""
    try:
        return derive_stream_marks_from_field_determination(payload, snapshot=snapshot)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see module docstring
        return {
            "enabled": True,
            "data_status": "UNAVAILABLE",
            "independence_class": "DERIVED_CORRELATED",
            "primary_signal": False,
            "source_engine": "Field_Determination",
            "age_appropriateness": "SUPPLEMENTARY_ONLY",
            "marks": {s: 0.0 for s in STREAM_IDS},
            "warnings": [f"{type(exc).__name__}: {exc}"],
            "note": (
                "Field-derived evidence could not be computed for this chart -- this "
                "is optional supplementary evidence; the primary stream score is "
                "computed and reported independently of this section's availability."
            ),
        }
