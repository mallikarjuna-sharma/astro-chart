"""Purpose -> Motivation -> Mechanism -> Expression reasoning chain
(2026-08 architecture-audit gap-fix, Gaps 9/11/12) -- deterministic,
non-LLM, additive-only.

Gap being closed: a second external architecture review argued the engine's
biggest remaining flaw is SEQUENCING, not missing signal -- it still asks
"which field fits" as one flat blend rather than first asking, in order,
"who is this person" (Atmakaraka/Lagna/Moon), "why do they work" (10th
lord/Moon/Jupiter/D9), "how do they solve problems" (Mercury/Mars/Saturn/
Rahu), and only then "which field expresses that." The review's own
proposal used a 7-agent LLM pipeline to build this sequencing. This module
builds the same 4-stage separation (Soul Purpose -> Vocational Motivation ->
Execution Mechanism -> Career Expression) DETERMINISTICALLY instead --
per this session's explicit direction, LLM non-determinism should not enter
the ranking/reasoning path; LLM use stays where it already lives in this
codebase (jyotish/llm.py -- post-hoc narrative dressing on an already-final
deterministic result), not as the reasoning mechanism itself.

Why this closes Gap 11 (Atmakaraka treated as same-kind-different-weight,
not different-kind) specifically: everywhere else in this codebase
(jaimini.py, knrao.py, shashtiamsha.py) Atmakaraka is one scored component
among many, contributing points to a blend. Here it is instead the sole
determinant of `soul_purpose` -- a categorical label, not a score --
establishing WHO the chart is before any field-specific scoring is
consulted. That is the categorical-vs-additive distinction the review
correctly identified as missing.

Why this closes Gap 12 (same field, different archetype path should be
distinguishable): `build_career_expression_chain()` assembles a per-field
narrative that threads the chart-level purpose/motivation through the
already-computed execution-mechanism signature (chart_synthesis.py's
planet_pattern_graph, built earlier this session) into that specific
field's label -- so two different charts landing on the same field produce
two different, honestly different, reasoning chains, exactly the "Moon-
Mercury Knowledge Creator vs Saturn-Mars Systems Builder both reach Software
Architecture" example the review used.

Design, consistent with every other module built this session:
  - Declarative lookup tables (same pattern as career_archetype.py's
    ontology and chart_synthesis.py's synergy/axis tables), not hand-coded
    per-planet branching logic.
  - Reuses already-validated primitives only: atmakaraka, house_lords,
    true_planet_dignities/planet_dignities, eff_strengths (all already
    consumed by confidence_dimensions.py/career_archetype.py this session)
    plus chart_synthesis.py's own planet_pattern_graph output for the
    execution-mechanism stage -- no new astrological computation, purely a
    new SEQUENCING/labeling layer over existing signal.
  - Additive-only / read-only: attaches a new `career_reasoning_chain` key
    to compute_field_method_bundle()'s return dict. Never touches
    final_score, method_scores, or field ranking.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

CONTRACT_VERSION = "purpose-chain.v1"

_DIGNITY_PCT: Dict[str, float] = {
    "EXALTED": 100.0, "MOOLATRIKONA": 90.0, "OWN": 80.0,
    "NEECHA_BHANGA": 60.0, "NEUTRAL": 50.0, "": 50.0, "DEBILITATED": 15.0,
}


def _dignity_pct(dignity_map: Mapping[str, str], planet: str) -> float:
    if not planet:
        return 50.0
    return _DIGNITY_PCT.get(str(dignity_map.get(planet, "") or "").strip().upper(), 50.0)


def _eff_strength_pct(eff_strengths: Mapping[str, float], planet: str) -> float:
    if not planet or planet not in eff_strengths:
        return 50.0
    return max(0.0, min(2.5, float(eff_strengths.get(planet, 0.0) or 0.0))) / 2.5 * 100.0


# ── Stage 1: Soul Purpose -- Atmakaraka ALONE determines this, categorically ─
# Not a blend: classical Jaimini treats Atmakaraka as different IN KIND from
# the other karakas (the soul's own significator), not merely the highest-
# weighted one. This table is intentionally driven by a single planet.
_SOUL_PURPOSE: Dict[str, Dict[str, str]] = {
    "Sun":     {"label": "Authority & Individuation",
                "description": "Purpose expressed through individual authority, visibility, and self-direction."},
    "Moon":    {"label": "Nurture & Public Connection",
                "description": "Purpose expressed through care, emotional resonance, and public-facing service."},
    "Mars":    {"label": "Courage & Direct Action",
                "description": "Purpose expressed through decisive action, competition, and defended ground."},
    "Mercury": {"label": "Knowledge & Communication",
                "description": "Purpose expressed through learning, articulation, and the transmission of ideas."},
    "Jupiter": {"label": "Wisdom & Expansion",
                "description": "Purpose expressed through teaching, principled growth, and meaning-making."},
    "Venus":   {"label": "Harmony & Creative Value",
                "description": "Purpose expressed through beauty, relationship, and creative/aesthetic value."},
    "Saturn":  {"label": "Discipline & Endurance",
                "description": "Purpose expressed through sustained duty, structure, and long-horizon responsibility."},
    "Rahu":    {"label": "Ambition & Boundary-Breaking",
                "description": "Purpose expressed through unconventional ambition and pioneering new ground."},
    "Ketu":    {"label": "Mastery & Detachment",
                "description": "Purpose expressed through deep specialization and release from convention."},
}

# ── Stage 2: Vocational Motivation -- "why do they work" ───────────────────
# Same planet-label vocabulary as Stage 1 (deliberately -- these are the
# same classical significators wearing a different question), but the
# INPUT here is different in kind from Stage 1: not Atmakaraka alone, but
# whichever of {10th-lord, Moon, Jupiter} -- the three classical career-
# motivation significators the review itself named -- is most strongly
# placed on THIS chart (dignity + Shadbala blend). This is where the
# review's "why do they work" question gets its own, separately-derived
# answer rather than reusing Stage 1's planet.
_MOTIVATION: Dict[str, Dict[str, str]] = {
    "Sun":     {"label": "Authority & Recognition",
                "description": "Motivated by visible responsibility, recognition, and standing."},
    "Moon":    {"label": "Public Service & Emotional Resonance",
                "description": "Motivated by caretaking, public trust, and emotionally meaningful work."},
    "Mars":    {"label": "Impact Through Action",
                "description": "Motivated by tangible results, competition, and decisive execution."},
    "Mercury": {"label": "Knowledge & Problem-Solving",
                "description": "Motivated by intellectual challenge, analysis, and articulate expertise."},
    "Jupiter": {"label": "Growth, Teaching & Meaning",
                "description": "Motivated by principled growth, mentorship, and long-run significance."},
    "Venus":   {"label": "Harmony, Design & Value Creation",
                "description": "Motivated by aesthetic quality, relationship, and value creation."},
    "Saturn":  {"label": "Structure, Duty & Long-Term Security",
                "description": "Motivated by stability, sustained responsibility, and earned security."},
    "Rahu":    {"label": "Ambition & Breaking New Ground",
                "description": "Motivated by novelty, scale, and unconventional advancement."},
    "Ketu":    {"label": "Mastery & Specialization",
                "description": "Motivated by depth, focus, and specialist expertise."},
}

_MOTIVATION_CANDIDATES = ("Moon", "Jupiter")  # + 10th lord, resolved dynamically


def build_purpose_chain(payload_data: Any) -> Dict[str, Any]:
    """Chart-level (computed once, not per field): resolves Stage 1 (Soul
    Purpose, from Atmakaraka alone) and Stage 2 (Vocational Motivation,
    from the strongest of 10th-lord/Moon/Jupiter on this specific chart).

    Stage 3 (Execution Mechanism) is intentionally NOT computed here --
    chart_synthesis.py's build_planet_pattern_graph() already computes it
    (the top-scored two-planet synergy signature IS the execution-mechanism
    answer -- "how do they solve problems" is exactly what that function's
    own docstring already describes). Reusing it here rather than
    recomputing keeps this module honest about not duplicating logic.
    """
    ak = getattr(payload_data, "atmakaraka", "") or ""
    house_lords = getattr(payload_data, "house_lords", {}) or {}
    planet_dignities = (
        getattr(payload_data, "true_planet_dignities", {})
        or getattr(payload_data, "planet_dignities", {})
        or {}
    )
    eff_strengths = getattr(payload_data, "eff_strengths", {}) or {}

    soul_purpose_entry = _SOUL_PURPOSE.get(ak)
    soul_purpose = {
        "name": ak or "",
        "label": soul_purpose_entry["label"] if soul_purpose_entry else "Undetermined",
        "description": soul_purpose_entry["description"] if soul_purpose_entry
        else "Atmakaraka not resolved on this chart -- soul-purpose stage unavailable.",
        "basis": f"Atmakaraka = {ak or '(unresolved)'}",
    }

    h10_lord = house_lords.get("10", "")
    motivation_candidates = [p for p in (h10_lord, *_MOTIVATION_CANDIDATES) if p]
    best_planet, best_score = "", -1.0
    scored = {}
    for p in motivation_candidates:
        s = 0.6 * _dignity_pct(planet_dignities, p) + 0.4 * _eff_strength_pct(eff_strengths, p)
        scored[p] = round(s, 2)
        if s > best_score:
            best_planet, best_score = p, s

    motivation_entry = _MOTIVATION.get(best_planet)
    vocational_motivation = {
        "name": best_planet or "",
        "label": motivation_entry["label"] if motivation_entry else "Undetermined",
        "description": motivation_entry["description"] if motivation_entry
        else "10th lord/Moon/Jupiter not resolved on this chart -- motivation stage unavailable.",
        "basis": (
            f"strongest of 10th-lord({h10_lord or '?'})/Moon/Jupiter by dignity+strength: "
            f"{best_planet or '(unresolved)'}"
        ),
        "candidate_scores": scored,
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "soul_purpose": soul_purpose,
        "vocational_motivation": vocational_motivation,
    }


def build_career_expression_chain(
    purpose_chain: Mapping[str, Any],
    planet_pattern_graph: Mapping[str, Any],
    field_label: str,
    domain: str,
) -> Dict[str, Any]:
    """Per-field (cheap -- pure assembly, no recomputation): Stage 4, the
    final "Career Expression" link. Threads the chart-level Stage 1/2
    (soul_purpose/vocational_motivation, from build_purpose_chain) and
    Stage 3 (execution_mechanism, from chart_synthesis.py's already-
    computed planet_pattern_graph -- its single top-scored signature is
    this chart's dominant "how do they solve problems" answer) into one
    ordered narrative ending at THIS specific field.

    This is what makes two different charts landing on the same field
    produce two different, honestly different chains (the review's
    "Moon-Mercury Knowledge Creator vs Saturn-Mars Systems Builder both
    reach Software Architecture" example) -- Stage 1-3 vary per chart,
    Stage 4 is just where they terminate for this candidate field.
    """
    soul = purpose_chain.get("soul_purpose", {}) or {}
    motivation = purpose_chain.get("vocational_motivation", {}) or {}
    top_sigs = planet_pattern_graph.get("top_signatures") or []
    mechanism = top_sigs[0] if top_sigs else {}

    stages = [
        {"stage": "soul_purpose", "label": soul.get("label", "Undetermined"),
         "planets": [soul.get("name", "")] if soul.get("name") else []},
        {"stage": "vocational_motivation", "label": motivation.get("label", "Undetermined"),
         "planets": [motivation.get("name", "")] if motivation.get("name") else []},
        {"stage": "execution_mechanism", "label": mechanism.get("label", "Undetermined"),
         "planets": mechanism.get("planets", [])},
        {"stage": "career_expression", "label": field_label, "domain": domain},
    ]

    narrative = (
        f"{soul.get('label', 'Undetermined')} "
        f"-> {motivation.get('label', 'Undetermined')} "
        f"-> {mechanism.get('label', 'Undetermined')} "
        f"-> {field_label}"
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "stages": stages,
        "narrative": narrative,
    }
