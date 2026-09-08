"""Chart Synthesis Layer -- Planet Pattern Graph + Structural Axis Nodes +
D24 Learning Profile (2026-08 architecture-audit gap-fix, additive-only).

Gap being closed: an external architecture review of this engine (2026-08)
correctly identified that:
  - individual planet weights are summed per field but classical PAIR
    combinations (Mercury+Mars, Saturn+Mars, Mercury+Saturn, Jupiter+Mercury,
    Moon+Mercury, ...) are never scored as first-class vocational signatures
    ("Gap 2" / "Gap 7" of that review),
  - the engine has no persistent, chart-level structural representation
    (a 9th-house stellium should produce a reusable "Knowledge Axis" node
    that every downstream consumer can read, not be rediscovered separately
    by each field scorer) ("Gap 5"),
  - D24/Siddhamsha functions only as a per-field confirmation score, never
    surfacing what it classically also indicates: preferred learning style,
    research inclination, and postgraduate/specialization suitability
    ("Gap 3").

This module is READ-ONLY / ADDITIVE, following the exact precedent already
established for career_archetype.py and confidence_dimensions.py this same
session: it does not touch final_score, method_scores, field ranking, or
any existing method's output. It computes two chart-level structures (once
per chart, not per field) and one field-level enrichment, all built purely
from already-validated payload primitives (eff_strengths, planet_house,
house_lords, true_planet_dignities/planet_dignities, d24_planet_dignities) --
no new astrological rules, only recombination of signals every other method
file in this package already trusts.

Why additive rather than a score-changing rewrite: exactly the same
reasoning career_archetype.py's own docstring already gives -- promoting an
unvalidated synergy/structural layer to something that GATES or REWEIGHTS
the 205-field affinity table (validated across 25 real charts) would risk
regressing real, working signal for a plausible-sounding but unbenchmarked
one. This stays a parallel, explanatory output a report/UI layer can narrate
alongside the existing ranked list.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

CONTRACT_VERSION = "chart-synthesis.v1"

_ALL_HOUSES = set(range(1, 13))

# ── Planet Pattern Graph: classical two-planet vocational signatures ───────
# Each entry: (planet_a, planet_b) -> label + description. This is a
# DECLARATIVE table (same pattern as career_archetype.py's ontology and
# Stage 2's _YOGA_ONTOLOGY) rather than hand-coded detector functions, so it
# stays auditable and easy to extend without touching scoring logic. Pairs
# drawn directly from the architecture review's own "Gap 7" list plus the
# same karakatwa pairings already implicit in boosts.py's domain bonuses.
_SYNERGY_ONTOLOGY: List[Dict[str, Any]] = [
    {"pair": ("Mercury", "Mars"), "name": "engineering_logic",
     "label": "Engineering Logic (Mercury-Mars)",
     "description": "Analytical intellect fused with execution drive -- "
                     "technical problem-solving that gets built, not just theorized."},
    {"pair": ("Saturn", "Mars"), "name": "structural_engineering",
     "label": "Structural Engineering (Saturn-Mars)",
     "description": "Disciplined, load-bearing execution -- suited to "
                     "structural, civil, and heavy-systems engineering."},
    {"pair": ("Mercury", "Saturn"), "name": "systems_architecture",
     "label": "Systems Architecture (Mercury-Saturn)",
     "description": "Methodical, structured intellect -- suited to systems "
                     "design, process engineering, and long-horizon planning."},
    {"pair": ("Jupiter", "Mercury"), "name": "research_and_teaching",
     "label": "Research & Teaching (Jupiter-Mercury)",
     "description": "Wisdom paired with articulation -- suited to research, "
                     "academia, and knowledge-transmission roles."},
    {"pair": ("Moon", "Mercury"), "name": "communication_technical",
     "label": "Communication-Oriented Technical Roles (Moon-Mercury)",
     "description": "Emotionally attuned articulation -- suited to technical "
                     "communication, UX, teaching-adjacent technical roles."},
    {"pair": ("Sun", "Mars"), "name": "command_execution",
     "label": "Command & Execution (Sun-Mars)",
     "description": "Authority fused with drive -- suited to leadership "
                     "roles requiring direct, visible execution."},
    {"pair": ("Saturn", "Mercury"), "name": "analytical_endurance",
     "label": "Analytical Endurance (Saturn-Mercury)",
     "description": "Patient, detail-sustained analysis -- suited to data "
                     "analysis, auditing, and long-cycle technical work."},
    {"pair": ("Rahu", "Mercury"), "name": "unconventional_technical",
     "label": "Unconventional Technical Innovation (Rahu-Mercury)",
     "description": "Non-traditional, boundary-pushing intellect -- suited "
                     "to emerging tech, frontier research, disruptive fields."},
    {"pair": ("Venus", "Mercury"), "name": "design_communication",
     "label": "Design & Communication (Venus-Mercury)",
     "description": "Aesthetic sense fused with articulation -- suited to "
                     "design, media, and creative-technical roles."},
    {"pair": ("Jupiter", "Saturn"), "name": "institutional_expertise",
     "label": "Institutional Expertise (Jupiter-Saturn)",
     "description": "Wisdom disciplined by structure -- suited to law, "
                     "policy, institutional and regulatory roles."},
]

# ── Structural Axis Nodes: reusable, house-cluster-derived chart features ──
# Mirrors career_archetype.py's declarative ontology pattern. Each axis is a
# named, persistent structural feature keyed to specific houses -- the same
# houses structural_patterns.py (Stage 1's 9th voting method) already scores
# per-field, recombined here as a single CHART-level (not per-field)
# descriptive node, computed once and available to every downstream reader
# instead of being re-derived independently by each consumer.
_AXIS_ONTOLOGY: List[Dict[str, Any]] = [
    {"name": "knowledge_axis", "label": "Knowledge Axis", "houses": (4, 5, 9),
     "description": "Learning, higher education, and dharmic/philosophical orientation."},
    {"name": "technical_axis", "label": "Technical Reasoning Axis", "houses": (3, 6, 10),
     "description": "Applied skill, execution, and sustained technical labor."},
    {"name": "research_axis", "label": "Research & Depth Axis", "houses": (8, 9, 12),
     "description": "Investigative depth, occult/hidden knowledge, specialization."},
    {"name": "leadership_axis", "label": "Leadership & Authority Axis", "houses": (1, 10, 11),
     "description": "Visibility, authority, gains from public-facing execution."},
    {"name": "communication_axis", "label": "Communication & Exchange Axis", "houses": (2, 3, 7),
     "description": "Articulation, negotiation, and relationship-facing exchange."},
]

_STELLIUM_THRESHOLD = 3  # same convention as structural_patterns.py


def _normalize_eff_strength(raw: float) -> float:
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


def build_structural_graph(payload_data: Any) -> Dict[str, Any]:
    """Chart-level (computed once per chart, not per field): score every
    axis in _AXIS_ONTOLOGY from D1 house occupancy, and flag any house that
    meets the stellium threshold as a persistent, reusable node.
    """
    planet_house: Dict[str, int] = getattr(payload_data, "planet_house", {}) or {}
    occupancy = _house_occupancy(planet_house)
    total_placed = sum(len(v) for v in occupancy.values())

    stelliums = {
        f"H{h}": occupants
        for h, occupants in occupancy.items()
        if len(occupants) >= _STELLIUM_THRESHOLD
    }

    axes: Dict[str, Any] = {}
    for entry in _AXIS_ONTOLOGY:
        occupants_in_axis = sorted({p for h in entry["houses"] for p in occupancy.get(h, [])})
        count = sum(len(occupancy.get(h, [])) for h in entry["houses"])
        concentration_pct = round((count / total_placed * 100.0), 2) if total_placed else 0.0
        axes[entry["name"]] = {
            "label": entry["label"],
            "description": entry["description"],
            "houses": list(entry["houses"]),
            "occupants": occupants_in_axis,
            "concentration_pct": concentration_pct,
            "dominant": concentration_pct >= 30.0,
        }

    ranked = sorted(axes.items(), key=lambda kv: -kv[1]["concentration_pct"])
    dominant_axis = {"name": ranked[0][0], **ranked[0][1]} if ranked else {}

    return {
        "contract_version": CONTRACT_VERSION,
        "dominant_axis": dominant_axis,
        "axes": axes,
        "stelliums": stelliums,
    }


def build_planet_pattern_graph(payload_data: Any) -> Dict[str, Any]:
    """Chart-level: score every declared two-planet synergy signature from
    combined Vimshopaka-weighted eff_strengths of both planets in the pair
    (same normalization career_archetype.py already uses for its own
    planet-strength component -- reused, not reinvented).
    """
    eff_strengths = getattr(payload_data, "eff_strengths", {}) or {}

    signatures: Dict[str, Any] = {}
    for entry in _SYNERGY_ONTOLOGY:
        p1, p2 = entry["pair"]
        vals = [
            _normalize_eff_strength(eff_strengths.get(p, 0.0))
            for p in (p1, p2) if p in eff_strengths
        ]
        # Both planets must be individually resolvable for the pair to be a
        # meaningful "combination" rather than a half-known guess; a
        # combination score built from only one known planet would silently
        # misrepresent it as a real synergy read.
        if len(vals) < 2:
            continue
        synergy_score = round(sum(vals) / len(vals), 2)
        signatures[entry["name"]] = {
            "label": entry["label"],
            "planets": list((p1, p2)),
            "description": entry["description"],
            "synergy_score": synergy_score,
        }

    ranked = sorted(signatures.items(), key=lambda kv: -kv[1]["synergy_score"])
    top_signatures = [{"name": n, **d} for n, d in ranked[:3]]

    return {
        "contract_version": CONTRACT_VERSION,
        "top_signatures": top_signatures,
        "all_signatures": signatures,
    }


# ── D24 Learning Profile: D24 as more than a confirmation score ────────────
_LEARNING_STYLE_KARAKAS: Dict[str, str] = {
    "Mercury": "Analytical / logic-driven learner -- absorbs structured, "
               "sequential material best.",
    "Jupiter": "Conceptual / principle-driven learner -- absorbs broad "
               "frameworks and theory before detail.",
    "Venus": "Aesthetic / example-driven learner -- absorbs applied, "
             "visually or creatively presented material best.",
    "Saturn": "Methodical / repetition-driven learner -- absorbs material "
              "through disciplined, incremental practice.",
    "Moon": "Intuitive / experience-driven learner -- absorbs material "
            "best through emotional/contextual engagement.",
    "Mars": "Hands-on / execution-driven learner -- absorbs material best "
            "through direct practice and application, not passive study.",
    "Sun": "Authority-driven learner -- absorbs material best from a "
           "single trusted source/mentor rather than diffuse inputs.",
    "Rahu": "Unconventional / self-directed learner -- absorbs material "
            "best outside standard curricula (self-study, niche sources).",
}

_STRONG_DIGNITIES = {"EXALTED", "MOOLATRIKONA", "OWN"}
_WEAK_DIGNITIES = {"DEBILITATED"}


def build_d24_learning_profile(payload_data: Any) -> Dict[str, Any]:
    """Chart-level: surface what D24/Siddhamsha classically also indicates
    beyond a single confirmation score -- preferred learning style (from the
    strongest-by-dignity D24 karaka among the classical vidya karakas),
    research inclination (Mercury+Jupiter D24 dignity blend), and
    postgraduate/specialization-depth suitability (Saturn's D24 dignity,
    the classical karaka for sustained, specialized effort).

    Uses only payload_data.d24_planet_dignities -- the same, already-
    validated D24 dignity map siddhamsha.py's score_siddhamsha() itself
    reads -- no new divisional-chart computation.
    """
    d24_dig = getattr(payload_data, "d24_planet_dignities", {}) or {}
    if not d24_dig:
        return {
            "contract_version": CONTRACT_VERSION,
            "available": False,
            "reason": "d24_planet_dignities not present on this payload",
        }

    def _dig(planet: str) -> str:
        return str(d24_dig.get(planet, "") or "").strip().upper()

    _vidya_karakas = ("Mercury", "Jupiter", "Venus", "Saturn", "Moon", "Mars", "Sun", "Rahu")
    _rank = {"EXALTED": 4, "MOOLATRIKONA": 3, "OWN": 2, "NEECHA_BHANGA": 1,
             "NEUTRAL": 0, "": 0, "DEBILITATED": -2}
    best_planet, best_rank = "", -999
    for p in _vidya_karakas:
        r = _rank.get(_dig(p), 0)
        if r > best_rank:
            best_planet, best_rank = p, r

    learning_style = _LEARNING_STYLE_KARAKAS.get(
        best_planet,
        "No single D24 karaka is distinctly dominant -- learning style reads as balanced/mixed.",
    )

    merc_strong = _dig("Mercury") in _STRONG_DIGNITIES
    jup_strong = _dig("Jupiter") in _STRONG_DIGNITIES
    merc_weak = _dig("Mercury") in _WEAK_DIGNITIES
    jup_weak = _dig("Jupiter") in _WEAK_DIGNITIES
    if merc_strong and jup_strong:
        research_inclination = "HIGH -- both Mercury and Jupiter well-dignified in D24, " \
                                "a classical signature for genuine research aptitude."
    elif merc_strong or jup_strong:
        research_inclination = "MODERATE -- one of Mercury/Jupiter well-dignified in D24."
    elif merc_weak or jup_weak:
        research_inclination = "LOW -- Mercury and/or Jupiter weakly placed in D24; applied/" \
                                "practical tracks likely fit better than pure research."
    else:
        research_inclination = "NEUTRAL -- no strong or weak signal from Mercury/Jupiter in D24."

    saturn_dig = _dig("Saturn")
    if saturn_dig in _STRONG_DIGNITIES:
        pg_suitability = "SUPPORTIVE -- Saturn (karaka for sustained, specialized effort) is " \
                          "well-dignified in D24; long-cycle postgraduate/specialization tracks " \
                          "are classically well-supported."
    elif saturn_dig in _WEAK_DIGNITIES:
        pg_suitability = "STRAINED -- Saturn weakly placed in D24; sustained multi-year " \
                          "specialization may be harder-won than a direct-entry route."
    else:
        pg_suitability = "NEUTRAL -- no strong or weak Saturn signal in D24 for postgraduate depth."

    return {
        "contract_version": CONTRACT_VERSION,
        "available": True,
        "dominant_d24_karaka": best_planet,
        "learning_style": learning_style,
        "research_inclination": research_inclination,
        "postgraduate_specialization_suitability": pg_suitability,
        "basis": {p: _dig(p) for p in _vidya_karakas if _dig(p)},
    }
