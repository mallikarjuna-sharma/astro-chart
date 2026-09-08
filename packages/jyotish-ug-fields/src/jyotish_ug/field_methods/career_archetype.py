"""Career Archetype Discovery (Stage 3 of the Astro-OS v3 gap-audit
implementation plan, 2026-08) -- the largest, riskiest layer in the plan,
deliberately implemented LAST and ADDITIVE-ONLY, after Stages 0/1/2/4/5 were
each independently validated against all 25 real charts in Charts/.

Gap being closed: this engine has always answered "which of ~200 registry
fields fits best" via direct per-field affinity scoring (BRANCH_PLANET_AFFINITY
+ the 9 voting methods). It has never asked the prior, more holistic
question a real astrologer forms an intuition about first -- "what KIND of
career suits this person" (a builder? a connector? a strategist? a healer?)
-- before ever consulting a specific field list. The source proposal's
Phase 5 ("Career Archetype Discovery") argued for building that layer.

Why additive-only, not a replacement: the proposal's own framing (Phase 5
onward) implicitly suggested archetype-matching could REPLACE or gate the
per-field affinity blend. That is exactly the highest-risk move in the whole
plan -- BRANCH_PLANET_AFFINITY (205 fields, hand-curated against BPHS/Jataka
Parijata karakatwa) and the 9-method voting bundle have now been validated
end-to-end across 25 real charts through Stages 0/1/2/4/5. Subordinating
that to a brand-new, UNvalidated 8-archetype classification (no labeled
benchmark exists for archetype accuracy, same caveat Stage 1's module
docstring already raised for its own weight prior) would risk regressing
real, working signal for a plausible-sounding but unproven one. This module
therefore never touches final_score, method_scores, or field ranking. It is
a NEW, separate, chart-level (not per-field) descriptive output -- "here is
the dominant career archetype this chart's own D1 structure and Vimshopaka-
weighted planetary strength suggest" -- that a report/UI layer (Stage 6) can
choose to narrate alongside the existing ranked list, and that a future,
carefully-evaluated stage could eventually use as a soft re-rank signal once
it has its own validation record. Until then it is read-only.

Design, consistent with every other Stage-1/2 module this session:
  - Declarative ontology table (same pattern as Stage 2's _YOGA_ONTOLOGY),
    not 8 hand-coded detector functions that would drift out of sync.
  - Reuses already-validated primitives rather than reinventing them:
    eff_strengths (Vimshopaka-weighted planetary strength, already computed
    by payload.py and consumed by every method file) for "which planets are
    strong," and the same D1 house-occupancy histogram Stage 1's
    structural_patterns.py already builds for "where is the chart's energy
    concentrated" -- not a third independent implementation of either.
  - Confidence-scored, not a forced single label: every archetype in the
    ontology gets a 0-100 match score computed the same way for all eight,
    so a chart that genuinely straddles two archetypes (common -- most real
    charts are not a pure single type) shows that honestly via `top_2` and
    the full `all_archetypes` breakdown, rather than an overconfident single
    label with no visibility into how close the runner-up was.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

CONTRACT_VERSION = "career-archetype.v1"

# Same kendra/trikona convention already established in structural_patterns.py
# and common.py's _KENDRA_HOUSES_Y/_TRIKONA_HOUSES_Y -- imported locally to
# avoid a hard dependency on structural_patterns.py (this module should stay
# independently loadable/testable, matching the pattern every other method
# file in this package already follows).
_ALL_HOUSES = set(range(1, 13))

_ARCHETYPE_ONTOLOGY: List[Dict[str, Any]] = [
    {
        "name": "builder_engineer",
        "label": "Builder / Engineer",
        "planets": ("Mars", "Saturn"),
        "houses": (3, 6, 10),
        # "technology" (2026-08 gap-fix): added to close a coverage gap --
        # india_course_registry_v12.json's actual `domain` field uses a
        # small closed vocabulary (13 values) that only partially overlaps
        # this ontology's original finer-grained domain words (see
        # apply_archetype_alignment_adjustment's own gap-fix note). Applied
        # technology fields (most of this registry's "technology"-domain
        # entries) are execution-oriented builds, the same classical
        # Mars/Saturn signature as engineering.
        "domains": ["engineering", "construction", "manufacturing", "defense", "surgery", "technology"],
        "description": "Disciplined, sustained application of raw execution drive -- "
                        "suited to building, fixing, and operating real systems.",
    },
    {
        "name": "communicator_connector",
        "label": "Communicator / Connector",
        "planets": ("Mercury", "Venus"),
        "houses": (2, 3, 7),
        "domains": ["communication", "media", "commerce", "arts", "public_relations"],
        "description": "Articulate, relationship-oriented, aesthetically aware -- "
                        "suited to media, commerce, design, and any client-facing role.",
    },
    {
        "name": "strategist_leader",
        "label": "Strategist / Leader",
        "planets": ("Sun", "Mars"),
        "houses": (1, 10, 11),
        # "public" (2026-08 gap-fix): registry's "public" domain covers
        # public administration/civil services/public policy fields -- the
        # same authority+execution signature this archetype already scores
        # for administration/politics/management.
        "domains": ["leadership", "administration", "politics", "management", "military", "public"],
        "description": "Authority paired with command/execution -- suited to leadership, "
                        "governance, and high-visibility executive roles.",
    },
    {
        "name": "healer_nurturer",
        "label": "Healer / Nurturer",
        "planets": ("Moon", "Jupiter"),
        "houses": (4, 6, 12),
        # "agriculture" (2026-08 gap-fix): classically a Moon (nourishment,
        # land fertility)/Jupiter (growth, sustenance) domain -- the same
        # growth-and-care signature this archetype already scores for
        # medicine/healthcare, not a Mars/Saturn execution-only domain.
        "domains": ["medicine", "healthcare", "counseling", "hospitality", "social_work", "agriculture"],
        "description": "Emotionally attuned, growth-oriented -- suited to medicine, "
                        "care-giving, counseling, and service professions.",
    },
    {
        "name": "analyst_researcher",
        "label": "Analyst / Researcher",
        "planets": ("Saturn", "Mercury"),
        "houses": (6, 8, 12),
        # "interdisciplinary" (2026-08 gap-fix): registry's catch-all for
        # fields that deliberately span multiple domains -- doesn't belong
        # to any single archetype by nature, but the patient, cross-domain
        # synthesis this archetype's Saturn/Mercury signature already
        # describes is the closest single fit; also added to guide_teacher
        # below so an interdisciplinary field can match either.
        "domains": ["research", "analytics", "data_science", "science", "actuarial", "interdisciplinary"],
        "description": "Patient, detail-oriented, systems-thinking -- suited to research, "
                        "data analysis, and deep technical specialization.",
    },
    {
        "name": "explorer_entrepreneur",
        "label": "Explorer / Entrepreneur",
        "planets": ("Rahu", "Mars"),
        "houses": (3, 7, 11),
        "domains": ["entrepreneurship", "trading", "startups", "sales", "adventure"],
        "description": "Unconventional, risk-tolerant, opportunistic -- suited to "
                        "entrepreneurship, trading, and pioneering new ground.",
    },
    {
        "name": "guide_teacher",
        "label": "Guide / Teacher",
        "planets": ("Jupiter", "Sun"),
        "houses": (5, 9, 12),
        # "humanities" (2026-08 gap-fix): direct classical fit alongside the
        # existing philosophy/spirituality/academia entries -- the wisdom/
        # Jupiter-Sun signature this archetype already scores.
        # "interdisciplinary": see analyst_researcher's note above -- listed
        # under both so a genuinely cross-domain field can match either of
        # the two archetypes closest to open-ended synthesis, rather than
        # being forced into one.
        "domains": ["education", "philosophy", "law", "spirituality", "academia", "humanities", "interdisciplinary"],
        "description": "Wisdom-oriented, principled -- suited to teaching, law, "
                        "academia, and roles built on guiding others.",
    },
    {
        "name": "creative_artist",
        "label": "Creative / Artist",
        "planets": ("Venus", "Moon"),
        "houses": (3, 5, 12),
        "domains": ["arts", "design", "music", "film", "creative_writing"],
        "description": "Imaginative, emotionally expressive -- suited to the arts, "
                        "design, and any field where original expression is the product.",
    },
]

# Weighting between the two component signals in each archetype's match
# score. Planetary-strength is primary (a chart's Vimshopaka-weighted
# eff_strengths is the most classically fundamental "which planets are this
# person's real strengths" signal); house-concentration is a secondary
# confirmation (does the chart's own energy-clustering, independent of the
# archetype's named planets, land in houses this archetype would predict).
_PLANET_STRENGTH_WEIGHT = 0.70
_HOUSE_CONCENTRATION_WEIGHT = 0.30


def _normalize_eff_strength(raw: float) -> float:
    """eff_strengths values in this codebase are Shadbala-derived ratios
    typically in the 0-2.5 range (see confidence_dimensions.py's own
    identical clamp for Sun/Mars) -- not already a 0-100 percentage. Clamp
    and rescale the same way every other module in this package already
    does, rather than assuming a different range here.
    """
    return max(0.0, min(2.5, float(raw or 0.0))) / 2.5 * 100.0


def _house_occupancy(planet_house: Mapping[str, int]) -> Dict[int, List[str]]:
    occupancy: Dict[int, List[str]] = {}
    for planet, house_num in (planet_house or {}).items():
        try:
            h = int(house_num)
        except (TypeError, ValueError):
            continue
        if h in _ALL_HOUSES:
            occupancy.setdefault(h, []).append(planet)
    return occupancy


def discover_career_archetype(payload_data: Any) -> Dict[str, Any]:
    """Score all 8 ontology archetypes against this chart's D1 planetary
    strength and house-occupancy pattern, and return every archetype's
    match score plus the top 1-2 for narrative use.

    Chart-level, not field-level -- takes only `payload_data` (no domain/
    field_affinity/field_id), matching the fact that "what kind of career
    suits this person" is a property of the chart, computed once, not a
    per-candidate-field question like the 9 voting methods. Callers that
    need it alongside a per-field bundle (compute_field_method_bundle) can
    call this once per chart and thread the same result into every field's
    output, rather than recomputing it per field.
    """
    eff_strengths = getattr(payload_data, "eff_strengths", {}) or {}
    planet_house = getattr(payload_data, "planet_house", {}) or {}

    occupancy = _house_occupancy(planet_house)
    total_placed = sum(len(v) for v in occupancy.values())

    all_archetypes: Dict[str, Any] = {}
    for entry in _ARCHETYPE_ONTOLOGY:
        p1, p2 = entry["planets"]
        strength_vals = [
            _normalize_eff_strength(eff_strengths.get(p, 0.0))
            for p in (p1, p2) if p in eff_strengths
        ]
        strength_score = sum(strength_vals) / len(strength_vals) if strength_vals else 50.0

        houses_matched = sum(len(occupancy.get(h, [])) for h in entry["houses"])
        house_concentration_pct = (houses_matched / total_placed * 100.0) if total_placed else 0.0

        match_score = round(
            _PLANET_STRENGTH_WEIGHT * strength_score
            + _HOUSE_CONCENTRATION_WEIGHT * min(100.0, house_concentration_pct * 2.0),
            2,
        )
        all_archetypes[entry["name"]] = {
            "label": entry["label"],
            "match_score": match_score,
            "domains": entry["domains"],
            "description": entry["description"],
            "basis": {
                "planet_strength_pct": round(strength_score, 2),
                "planets": list((p1, p2)),
                "house_concentration_pct": round(house_concentration_pct, 2),
                "houses": list(entry["houses"]),
            },
        }

    ranked = sorted(all_archetypes.items(), key=lambda kv: -kv[1]["match_score"])
    top_1 = {"name": ranked[0][0], **ranked[0][1]} if ranked else {}
    top_2 = [{"name": n, **d} for n, d in ranked[:2]]

    # Confidence in the top pick specifically -- how far ahead is it of the
    # runner-up. A chart where the top two archetypes are within a few
    # points of each other is genuinely dual-natured, not miscalibrated;
    # this makes that visible rather than hiding it behind a single label.
    margin = (ranked[0][1]["match_score"] - ranked[1][1]["match_score"]) if len(ranked) > 1 else 0.0
    if margin >= 15.0:
        distinctness = "CLEAR"
    elif margin >= 5.0:
        distinctness = "LEANING"
    else:
        distinctness = "BLENDED"

    return {
        "contract_version": CONTRACT_VERSION,
        "top_archetype": top_1,
        "top_2_archetypes": top_2,
        "distinctness": distinctness,
        "margin": round(margin, 2),
        "all_archetypes": all_archetypes,
    }
