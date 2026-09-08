"""field_stream_mapping.py — fractional field/family/domain -> CBSE stream
affinity, replacing a single hard DOMAIN_TO_STREAM bucket (still used as-is
by cross_validate.py, which is a report-only comparison and deliberately
kept simple) with a graded map for field_derived_stream.py's score-affecting
use, where a wrong hard bucket has real consequences.

Rationale (per review): several real fields are genuinely stream-ambiguous
in Indian CBSE admissions practice -- Economics is a legitimate Commerce OR
Humanities subject depending on board/school; Psychology sits in Humanities
in most CBSE schools but is bio-adjacent; Architecture draws from technical
(Science/PCM) and design/creative (Humanities) foundations; Data
Science/Environmental Studies/Public Health span two streams routinely. A
single hard bucket forces a false binary on exactly these cases.

Each affinity vector should sum to ~1.0 across science/commerce/humanities.
Resolution order: exact field_id -> career_family_label (lowercased) ->
domain fallback -> UNMAPPED (never silently defaulted to a stream).

NOT THE PRIMARY RULE SOURCE (documentation/discoverability note, added
2026-07-24 audit): despite this module's name/docstring reading like "the"
astrological Science/Commerce/Humanities rule set, it is NOT what drives
planetary_strength/house_support (or any other rubric section) in a normal
report. The actual planet/house weight tables that score every real report
live in Stream_Determination/subject_registry.py's STREAM_META dict -- read
that file first if you're trying to understand or change what makes a chart
score toward a given stream.

This module (FIELD_STREAM_AFFINITY / DOMAIN_STREAM_AFFINITY) has exactly
two consumers, both optional and both explicitly off/simple by default:
  1. field_derived_stream.py's 8th rubric section, which DOES affect the
     score but is gated behind DEFAULT_INCLUDE_FIELD_DERIVED_EVIDENCE=False
     in early_age_stream_engine.py (experimental, opt-in only).
  2. cross_validate.py's report-only adult-engine comparison (via
     DOMAIN_TO_STREAM, a simplification of this module's own graded
     affinities down to a single hard bucket) -- informational, never
     folded into the score.
If you intend for this module's rules to actually matter for every report,
wire it into STREAM_META's role instead of assuming it already is; if it is
meant to stay experimental/deprecated, this note is the flag that it is.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

Affinity = Dict[str, float]

STREAM_IDS = ("science", "commerce", "humanities")

# 2026-08-22 audit fix (gap 9): DISCLOSURE -- every affinity number in this
# module (FIELD_STREAM_AFFINITY below and DOMAIN_STREAM_AFFINITY further
# down) is this codebase's own ENGINEERED ESTIMATE of real-world field/
# domain-to-stream affinity. None of these fractions are derived from
# classical Jyotish texts (this is not an astrological rubric -- see the
# NOT-THE-PRIMARY-RULE-SOURCE note above) and none are sourced from an
# official CBSE table or published statistic -- they are this project's own
# reasonable-effort judgment calls, written down so a future reader does not
# mistake a number like {"science": 0.55, "humanities": 0.45} for cited or
# authoritative data.

# --- Field-level overrides (exact field_id from india_course_registry_v12.json) ---
# Deliberately small and conservative: only fields with a well-known,
# genuinely split real-world stream pathway are listed here. Everything else
# falls through to the domain-level map below.
FIELD_STREAM_AFFINITY: Dict[str, Affinity] = {
    "economics": {"science": 0.10, "commerce": 0.45, "humanities": 0.45},
    "psychology": {"science": 0.30, "commerce": 0.0, "humanities": 0.70},
    "architecture": {"science": 0.55, "commerce": 0.0, "humanities": 0.45},
    "data_science": {"science": 0.55, "commerce": 0.35, "humanities": 0.10},
    "environmental_science": {"science": 0.65, "commerce": 0.0, "humanities": 0.35},
    "public_health": {"science": 0.55, "commerce": 0.0, "humanities": 0.45},
    "public_policy": {"science": 0.0, "commerce": 0.20, "humanities": 0.80},
    "design": {"science": 0.15, "commerce": 0.30, "humanities": 0.55},
    "actuarial_science": {"science": 0.30, "commerce": 0.65, "humanities": 0.05},
    "law": {"science": 0.0, "commerce": 0.30, "humanities": 0.70},
}

# --- Domain-level fallback (jyotish/india_course_registry_v12.json's 13
# branches[*].domain values) -- same 13 keys cross_validate.py's
# DOMAIN_TO_STREAM already covers, expressed as fractional vectors instead
# of a hard single-stream bucket. Mostly still near-hard (1.0) for
# genuinely single-stream domains; only "law"/"public"/"education" get a
# real split, matching real CBSE admissions practice.
DOMAIN_STREAM_AFFINITY: Dict[str, Affinity] = {
    "engineering":       {"science": 1.0,  "commerce": 0.0,  "humanities": 0.0},
    "technology":        {"science": 1.0,  "commerce": 0.0,  "humanities": 0.0},
    "science":           {"science": 1.0,  "commerce": 0.0,  "humanities": 0.0},
    "medicine":          {"science": 1.0,  "commerce": 0.0,  "humanities": 0.0},
    "agriculture":       {"science": 0.85, "commerce": 0.0,  "humanities": 0.15},
    "commerce":          {"science": 0.0,  "commerce": 1.0,  "humanities": 0.0},
    "law":               {"science": 0.0,  "commerce": 0.30, "humanities": 0.70},
    "humanities":        {"science": 0.0,  "commerce": 0.0,  "humanities": 1.0},
    "arts":              {"science": 0.0,  "commerce": 0.0,  "humanities": 1.0},
    "media":             {"science": 0.0,  "commerce": 0.10, "humanities": 0.90},
    "education":         {"science": 0.0,  "commerce": 0.0,  "humanities": 1.0},
    "public":            {"science": 0.0,  "commerce": 0.20, "humanities": 0.80},
    # "interdisciplinary" deliberately left UNMAPPED (None) -- forcing a
    # split here would be a guess with no domain-level basis at all.
}


def get_affinity(field_id: str, career_family_label: str, domain: str) -> Optional[Affinity]:
    """Resolve a field's stream-affinity vector: exact field_id override,
    else domain fallback, else None (UNMAPPED -- caller must not silently
    default this to any one stream)."""
    if field_id and field_id in FIELD_STREAM_AFFINITY:
        return FIELD_STREAM_AFFINITY[field_id]
    if domain and domain in DOMAIN_STREAM_AFFINITY:
        return DOMAIN_STREAM_AFFINITY[domain]
    return None


def exclusivity(affinity: Affinity, floor: float = 0.35) -> float:
    """Entropy-based exclusivity: 1.0 for a pure single-stream field, near 0
    for an evenly-split field, with a floor so genuinely interdisciplinary
    fields still contribute something rather than being multiplied away to
    near-zero (per review point 5)."""
    probs = [p for p in affinity.values() if p > 0]
    if not probs:
        return floor
    max_entropy = math.log(len(STREAM_IDS))
    entropy = -sum(p * math.log(p) for p in probs)
    raw_exclusivity = 1.0 - (entropy / max_entropy if max_entropy else 0.0)
    return floor + (1.0 - floor) * max(0.0, min(1.0, raw_exclusivity))
