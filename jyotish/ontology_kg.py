"""jyotish/ontology_kg.py — Knowledge-Graph Ontology Layer (2026-07-04).

Upgrades the flat, single-parent hierarchy in `competency_ontology.py`
(Competency -[FK]-> Career Family -[FK]-> Field, each field owned by exactly
one family, each family by exactly one competency) into a real weighted
knowledge graph:

    Astro Evidence (real per-chart planet strength)
        -> Trait            (~26 cognitive/ability dimensions)
        -> Competency        (15 nodes, unchanged ids/labels)
        -> Cluster           (8 nodes, new — thematic super-groups)
        -> Career Family      (68 nodes, unchanged ids/labels)
        -> Field              (199 nodes, unchanged ids/labels)

Why this exists (see COMPETENCY_ONTOLOGY_UPGRADE_2026-07.md +
project_jyotishai_ontology_upgrade memory): the 2026-07-04 audit's core
complaint (G1) was that a flat leaderboard with only single-parent FK
grouping still lets structurally weak/overly-broad fields (Real Estate
Management, Mass Communication, Liberal Arts, Visual Communication, ...)
surface unrealistically high, because there's no way to (a) express that a
field is *inherently* broad/generic vs a sharply-defined specialization,
(b) let a field legitimately belong to more than one family (the existing
file already documents several of these — architecture, game_design_technology,
health_informatics, planetary_science — as single-homed only because the
flat-dict model couldn't do otherwise), or (c) mildly discount lower-ranked
siblings so five members of the same family don't all independently spike to
the top of a leaderboard. (Unani Medicine was in this list originally too,
but a 2026-07-04 follow-up audit found no data basis for penalizing it
specifically — see FIELD_BROADNESS_PENALTY's comment.)

Design constraints (do not violate these — see engine.py's call site and
tests/test_regression_locked.py / tests/test_career_track_regressions.py):

  * SINGLE SOURCE OF TRUTH. This module does NOT redefine competencies,
    families, or the field->family assignment. It imports COMPETENCY_META,
    FAMILY_META, and FIELD_TO_FAMILY from competency_ontology.py verbatim
    and builds the graph FROM them, so there is zero drift risk and zero
    chance of silently changing what get_ontology()/apply_family_cohesion_
    adjustment() return (those are exercised by the regression-locked
    engine.py call site and by test_competency_ontology_g22_g31.py).
  * ADDITIVE / READ-ONLY. Nothing in this module mutates final_score. It is
    a parallel, explanatory + diagnostic graph you can query independently
    (rank_fields_via_graph) or use to attach non-score-affecting diagnostics
    to already-computed engine results (attach_graph_diagnostics). Wiring a
    new bounded score nudge from this graph into engine.py is a deliberate
    follow-up decision left to the user — see the module docstring's final
    section "INTEGRATION NOTE".
  * REAL DATA, NOT INVENTED WEIGHTS. Trait<->Competency and Astro<->Trait
    edge weights are derived mechanically from the *already-curated*
    `_PLANET_APTITUDE` table (competency_ontology.py Section 10, used
    today for G27's aptitude explanation) and each competency's existing
    `planets` signature list — not hand-picked numbers. Astro Evidence
    values come from real `shadbala_virupas` in the chart JSON
    (`pyhora_calculations.planets_d1.<Planet>.shadbala_virupas`), normalized
    against the same `_PLANET_MIN_SHADBALA` table engine.py itself uses for
    every other strength ratio in the codebase.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from Field_Determination.competency_ontology import (
    COMPETENCY_META,
    FAMILY_META,
    FIELD_TO_FAMILY,
    _PLANET_APTITUDE,
    _APTITUDE_DIM_LABEL,
    get_family_id,
    get_competency_id,
    confidence_band,
)

try:
    from .constants import _PLANET_MIN_SHADBALA
except Exception:  # pragma: no cover - defensive fallback if constants shape changes
    _PLANET_MIN_SHADBALA = {
        "Sun": 390.0, "Moon": 360.0, "Mars": 300.0, "Mercury": 420.0,
        "Jupiter": 390.0, "Venus": 330.0, "Saturn": 300.0, "Rahu": 300.0, "Ketu": 300.0,
    }


# =============================================================================
# SECTION 1 — NODE TYPES
# =============================================================================

class NodeType(str, Enum):
    ASTRO_EVIDENCE = "astro_evidence"
    TRAIT = "trait"
    COMPETENCY = "competency"
    CLUSTER = "cluster"
    CAREER_FAMILY = "career_family"
    FIELD = "field"
    SPECIALIZATION = "specialization"   # reserved: registry tier_map niches (UG/PG/PhD)
    EDUCATION_PATH = "education_path"   # reserved: degree_types / admission_exams


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    type: NodeType
    description: str = ""
    broadness_penalty: float = 0.0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    weight: float = 1.0
    relation: str = "supports"


# =============================================================================
# SECTION 2 — KNOWLEDGE GRAPH ENGINE
# =============================================================================

class OntologyKG:
    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.out_edges: Dict[str, List[Edge]] = defaultdict(list)
        self.in_edges: Dict[str, List[Edge]] = defaultdict(list)

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node id: {node.id}")
        self.nodes[node.id] = node

    def add_edge(self, source: str, target: str, weight: float = 1.0, relation: str = "supports") -> None:
        if source not in self.nodes:
            raise ValueError(f"Unknown source node: {source}")
        if target not in self.nodes:
            raise ValueError(f"Unknown target node: {target}")
        if not 0 <= weight <= 1.5:
            raise ValueError(f"Invalid edge weight: {weight}")

        edge = Edge(source, target, weight, relation)
        self.out_edges[source].append(edge)
        self.in_edges[target].append(edge)

    def validate(self) -> None:
        for edge_list in self.out_edges.values():
            for edge in edge_list:
                if edge.source not in self.nodes or edge.target not in self.nodes:
                    raise ValueError(f"Broken edge: {edge}")

    def propagate_scores(
        self,
        evidence_scores: Dict[str, float],
        decay: float = 0.88,
        max_depth: int = 7,
    ) -> Dict[str, float]:
        """Propagates astrology evidence through:
        Astro Evidence -> Trait -> Competency -> Cluster -> Career Family -> Field.
        """
        scores: Dict[str, float] = defaultdict(float)
        frontier: List[Tuple[str, float, int]] = []

        for node_id, score in evidence_scores.items():
            if node_id not in self.nodes:
                continue
            scores[node_id] += score
            frontier.append((node_id, score, 0))

        while frontier:
            current, current_score, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for edge in self.out_edges[current]:
                propagated = current_score * edge.weight * (decay ** depth)
                scores[edge.target] += propagated
                frontier.append((edge.target, propagated, depth + 1))

        return dict(scores)

    def ranked_fields(
        self,
        raw_scores: Dict[str, float],
        top_n: int = 20,
        sibling_suppression: bool = True,
    ) -> List[Tuple[str, str, float]]:
        field_scores = {}
        for node_id, score in raw_scores.items():
            node = self.nodes.get(node_id)
            if node is not None and node.type == NodeType.FIELD:
                adjusted = score * (1.0 - node.broadness_penalty)
                field_scores[node_id] = adjusted

        if sibling_suppression:
            field_scores = self._apply_sibling_suppression(field_scores)

        ranked = sorted(field_scores.items(), key=lambda x: x[1], reverse=True)
        if not ranked:
            return []

        max_score = ranked[0][1] or 1.0
        return [
            (field_id, self.nodes[field_id].label, round((score / max_score) * 100, 1))
            for field_id, score in ranked[:top_n]
        ]

    def _apply_sibling_suppression(self, field_scores: Dict[str, float]) -> Dict[str, float]:
        """Prevents sibling fields within the same career family from all
        independently flooding the top-N. Keeps them, but mildly discounts
        lower-ranked siblings (G1/G16's 'cannibalization' complaint).

        2026-07-04 audit fix: this used to group a field into EVERY
        CAREER_FAMILY it has an edge to (primary + any secondary
        multi-parent edges), so a dual-natured field like `architecture`
        (design_thinking secondary edge alongside its architecture_spatial
        primary) could get the demotion penalty applied once per group it
        wasn't top-scorer in — i.e. compounded. That's backwards: a field
        with genuine cross-family support should be suppressed less than a
        single-homed one, not more. Fixed by grouping each field under only
        its PRIMARY family (relation == "primary") for suppression purposes;
        secondary edges remain fully visible elsewhere (parents_of,
        attach_graph_diagnostics' graph_family_memberships) — they just
        don't multiply this specific penalty.
        """
        family_to_fields: Dict[str, List[str]] = defaultdict(list)
        for field_id in field_scores:
            primary_parents = [
                e.source for e in self.in_edges[field_id]
                if self.nodes[e.source].type == NodeType.CAREER_FAMILY and e.relation == "primary"
            ]
            if not primary_parents:
                # Robustness fallback for any future field with only
                # secondary-relation family edges (shouldn't happen today,
                # since every field gets exactly one primary edge in
                # Section 7.11) — use its single strongest family parent.
                any_parents = [
                    e.source for e in self.in_edges[field_id]
                    if self.nodes[e.source].type == NodeType.CAREER_FAMILY
                ]
                primary_parents = any_parents[:1]
            for parent in primary_parents:
                family_to_fields[parent].append(field_id)

        adjusted = dict(field_scores)
        for _, fields in family_to_fields.items():
            sorted_fields = sorted(set(fields), key=lambda f: field_scores[f], reverse=True)
            for idx, field_id in enumerate(sorted_fields):
                if idx == 0:
                    continue
                penalty = min(0.08 * idx, 0.32)
                adjusted[field_id] *= (1.0 - penalty)
        return adjusted

    # -- diagnostics -----------------------------------------------------
    def parents_of(self, node_id: str, parent_type: Optional[NodeType] = None) -> List[Tuple[str, float]]:
        """Return [(parent_id, edge_weight)] for a node, optionally filtered
        to a single parent NodeType. Field nodes may legitimately have more
        than one CAREER_FAMILY parent (primary weight 1.0 + secondary
        cross-family edges) — this is the multi-parent capability the flat
        FIELD_TO_FAMILY dict could not express."""
        out = []
        for e in self.in_edges[node_id]:
            src = self.nodes.get(e.source)
            if src is None:
                continue
            if parent_type is None or src.type == parent_type:
                out.append((e.source, e.weight))
        return sorted(out, key=lambda x: -x[1])


# =============================================================================
# SECTION 3 — CLUSTER LAYER (new — 8 thematic super-groups over the 15
# existing competencies; introduced by this module, not present upstream)
# =============================================================================

CLUSTER_META: Dict[str, Dict[str, Any]] = {
    "cluster_engineering_physical": {
        "label": "Advanced Engineering & Physical Systems",
        "competencies": ["systems_electronics", "physical_mechanical", "frontier_space", "built_environment"],
    },
    "cluster_computation_data": {
        "label": "Computation, Data & Digital Intelligence",
        "competencies": ["computational_intelligence"],
    },
    "cluster_medical_life_sciences": {
        "label": "Medicine, Health & Life Sciences",
        "competencies": ["medical_health", "life_earth_sciences"],
    },
    "cluster_governance_law_defence": {
        "label": "Governance, Law & Strategic/Defence Institutions",
        "competencies": ["governance_institutions", "defence_security"],
    },
    "cluster_knowledge_behaviour": {
        "label": "Knowledge, Humanities & Behavioural Sciences",
        "competencies": ["knowledge_scholarship", "behavioural_social"],
    },
    "cluster_commerce_enterprise": {
        "label": "Commerce, Finance & Enterprise",
        "competencies": ["commerce_enterprise"],
    },
    "cluster_design_media": {
        "label": "Design, Media & Creative Expression",
        "competencies": ["design_creative", "media_performance"],
    },
    "cluster_agri_environment": {
        "label": "Agriculture & Environmental Systems",
        "competencies": ["agri_environment"],
    },
    "cluster_natural_physical_sciences": {
        "label": "Natural & Physical Sciences",
        # 2026-07-04 audit fix: no competency maps here by DEFAULT — this
        # cluster exists purely to receive families redirected out of
        # cluster_medical_life_sciences via FAMILY_CLUSTER_OVERRIDE below
        # (physical_chemical_sci, mathematical_sciences, earth_environmental_sci,
        # astronomy_planetary_sci, forensic_investigative all sit under the
        # life_earth_sciences competency, which bundles hard/physical/math
        # sciences together with biology under one label — without the
        # override, Mathematics/Physics/Astronomy would inherit a "Medicine,
        # Health & Life Sciences" cluster label, which reads wrong). See
        # _clusters_for_competency()/_cluster_for_family() for how the
        # competency -> cluster connectivity is preserved despite this
        # cluster having no *default* competency of its own.
        "competencies": [],
    },
}

# Reverse index: competency_id -> cluster_id (every one of the 15 existing
# competencies is covered exactly once — enforced by _validate_cluster_coverage).
_COMPETENCY_TO_CLUSTER: Dict[str, str] = {
    comp_id: cluster_id
    for cluster_id, meta in CLUSTER_META.items()
    for comp_id in meta["competencies"]
}


def _validate_cluster_coverage() -> None:
    missing = [c for c in COMPETENCY_META if c not in _COMPETENCY_TO_CLUSTER]
    if missing:
        raise ValueError(f"Competencies not assigned to any cluster: {missing}")


# =============================================================================
# SECTION 3b — FAMILY-LEVEL CLUSTER OVERRIDES  (2026-07-04 audit fix)
# =============================================================================
# Cluster is normally derived purely from a family's competency
# (Family -> Competency -> Cluster). That's right most of the time, but a
# handful of families sit under a competency whose *label* doesn't fit them
# individually — competency_ontology.py's own groupings are unchanged
# (single source of truth), so this expresses the exception only at the
# graph layer, without touching that file.
FAMILY_CLUSTER_OVERRIDE: Dict[str, str] = {
    # life_earth_sciences bundles Physics/Chemistry/Math/Astronomy/Forensics
    # together with Biology under one competency label. Keep biology in the
    # medical/life cluster; move the non-biological families out so
    # Mathematics/Physics/Astronomy don't inherit a "Medicine, Health & Life
    # Sciences" cluster label.
    "physical_chemical_sci":   "cluster_natural_physical_sciences",
    "mathematical_sciences":   "cluster_natural_physical_sciences",
    "earth_environmental_sci": "cluster_natural_physical_sciences",
    "astronomy_planetary_sci": "cluster_natural_physical_sciences",
    "forensic_investigative":  "cluster_natural_physical_sciences",
    # real_estate_property sits under built_environment (correctly adjacent
    # to architecture/civil/urban planning competency-wise) but is
    # fundamentally a commerce/asset-management field, not engineering.
    "real_estate_property":    "cluster_commerce_enterprise",
    # sports_physical_ed sits under knowledge_scholarship (grouped with
    # teaching/research/linguistics) but sports science/coaching is a
    # physical/applied-physiology field — closer to health sciences than
    # humanities.
    "sports_physical_ed":      "cluster_medical_life_sciences",
}


def _cluster_for_family(fam_id: str) -> str:
    """The cluster a career family belongs to, honoring FAMILY_CLUSTER_OVERRIDE
    before falling back to its competency's default cluster."""
    override = FAMILY_CLUSTER_OVERRIDE.get(fam_id)
    if override:
        return override
    comp_id = FAMILY_META.get(fam_id, {}).get("competency", "")
    return _COMPETENCY_TO_CLUSTER.get(comp_id, "")


def _clusters_for_competency(comp_id: str) -> List[str]:
    """All clusters a competency needs a Competency->Cluster edge to, so
    propagate_scores() can still reach every family reachable from this
    competency — including families redirected to a non-default cluster by
    FAMILY_CLUSTER_OVERRIDE (e.g. life_earth_sciences must reach BOTH
    cluster_medical_life_sciences, for biological_life_sci, AND
    cluster_natural_physical_sciences, for its four redirected families)."""
    clusters: List[str] = []
    default = _COMPETENCY_TO_CLUSTER.get(comp_id)
    if default:
        clusters.append(default)
    for fam_id, meta in FAMILY_META.items():
        if meta.get("competency") != comp_id:
            continue
        override = FAMILY_CLUSTER_OVERRIDE.get(fam_id)
        if override and override not in clusters:
            clusters.append(override)
    return clusters


# =============================================================================
# SECTION 4 — BROADNESS PENALTIES  (curated, not blanket)
# =============================================================================
# Most of the 199 registry fields are sharply-defined professional
# specializations and get 0.0 (no penalty — a precise field should not be
# punished just for being small). Penalties are reserved for fields that are
# structurally broad/generic/catch-all *by their own registry definition*
# (interdisciplinary umbrellas, generalist management tracks, "study of
# everything in X" domains) — these are exactly the categories the
# 2026-07-04 audit flagged as producing odd top-20 rankings.

FIELD_BROADNESS_PENALTY: Dict[str, float] = {
    # Explicitly interdisciplinary / generalist umbrellas
    "real_estate_management":                0.20,
    "liberal_arts_interdisciplinary":         0.18,
    "research_academia":                      0.15,  # "any research career" is not a specific field
    "mass_communication":                     0.12,
    "environmental_studies_interdisciplinary": 0.10,
    "visual_communication":                   0.10,
    "business_management":                    0.10,  # BBA/MBA — broadest commerce catch-all
    "development_studies":                    0.08,
    "tourism_management":                     0.08,
    "entrepreneurship":                       0.08,
    "hotel_hospitality_management":           0.06,
    "rural_management":                       0.06,
    "commerce_accounting":                    0.06,
    "literature_languages":                   0.06,
    "behavioural_science":                    0.05,
    "cognitive_science":                      0.05,
    "geography":                              0.05,
    "public_policy":                          0.05,
    "environmental_science":                  0.05,  # broad umbrella, one notch below its explicitly-"interdisciplinary" sibling above
    "agribusiness_management":                0.05,  # same broad commerce+agri hybrid tier as rural_management
    "psychology":                             0.04,  # general BSc/MA Psychology is one of the broadest single-word degree umbrellas
    "supply_chain_logistics":                 0.04,
    "digital_marketing":                      0.04,
    "computational_social_science":           0.03,
    "economics":                              0.03,
    "international_relations":                0.03,
    "political_science":                      0.03,
    "philosophy":                             0.03,
    "sociology_anthropology":                 0.03,
    "social_work":                            0.03,
    "healthcare_management":                  0.02,
    "history_archaeology":                    0.02,
    # 2026-07-04 audit fix: "urban_informatics" is a real technology
    # specialization (urban data/GIS/smart-cities systems), not a generic
    # catch-all — it was previously penalized here purely by analogy to its
    # neighbors, which conflated "cross-disciplinary" with "generic". It now
    # gets a SECONDARY_FIELD_FAMILY_EDGES entry to urban_infra_planning
    # instead (the correct way to express real cross-domain breadth without
    # penalizing the field for being specific).
    #
    # 2026-07-04 audit fix: unani_medicine (was 0.25) and yoga_naturopathy
    # (was 0.10) have been REMOVED from this table. Both are narrow, licensed
    # clinical degree tracks (BUMS / BNYS) exactly like ayurveda and
    # homeopathy (both 0.0 here, and always were) — checking the registry's
    # own institutional-availability data shows all four alternative-medicine
    # siblings have comparable footprints (state + deemed-private + some
    # central-university seats), so there was no data basis for penalizing
    # two of the four and not the other two. The original 0.25/0.10 values
    # were carried over uncritically from an illustrative sample rather than
    # independently justified from this project's own data. FIELD_BROADNESS_
    # PENALTY is specifically for structural genericity/catch-all breadth,
    # not "this field happens to rank higher than expected in some charts" —
    # if a specific niche field like unani_medicine still over-ranks in real
    # output after this removal, that points to an affinity/demand
    # calibration issue elsewhere, not genericity, and shouldn't be papered
    # over with a penalty that doesn't conceptually fit the field.
}


# =============================================================================
# SECTION 5 — SECONDARY CROSS-FAMILY EDGES  (multi-parent fields)
# =============================================================================
# The flat FIELD_TO_FAMILY dict forces exactly one family per field. Several
# fields are documented *in that file's own comments* as legitimately
# cross-competency (architecture; the three "_dup" placeholder guards that
# were popped out because the dict model couldn't keep them). The graph
# model can express these properly as a lower-weight secondary edge
# alongside the primary (weight 1.0) edge, without changing which family
# "owns" the field for reporting purposes (career_family / career_family_label
# in engine.py output stay exactly as competency_ontology.py computes them).

SECONDARY_FIELD_FAMILY_EDGES: List[Tuple[str, str, float]] = [
    # Documented in competency_ontology.py comments (Section 3):
    ("architecture", "design_thinking", 0.35),
    ("game_design_technology", "interactive_game_design", 0.40),
    ("health_informatics", "public_health_fam", 0.35),
    ("planetary_science", "astronomy_planetary_sci", 0.40),
    # Additional classically-justified cross-links (computational/quant
    # hybrids and applied-science fields that genuinely straddle two
    # families in the existing registry's own descriptions):
    ("bioinformatics", "medical_research_fam", 0.30),
    ("biomedical_engineering", "electronics_embedded", 0.30),
    ("computational_finance", "finance_quant_risk", 0.35),
    ("econometrics", "economics_policy_analysis", 0.35),
    ("economics_data_science", "economics_policy_analysis", 0.30),
    ("medical_physics", "physical_chemical_sci", 0.30),
    ("engineering_physics", "space_systems_propulsion", 0.30),
    ("geographic_information_systems", "earth_environmental_sci", 0.30),
    ("computational_social_science", "psychology_behavioural", 0.30),
    ("environmental_engineering", "environmental_ecological", 0.35),
    ("water_resources_engineering", "civil_structural", 0.30),
    ("chemical_engineering_data_science", "data_quant_analytics", 0.30),
    # 2026-07-04 audit follow-up — same "documented single-home only because
    # the flat dict couldn't do otherwise" pattern, found by auditing every
    # field against its real registry label/description:
    ("environmental_law", "environmental_ecological", 0.35),   # law <-> environmental science, as dual-natured as architecture
    ("fintech", "finance_quant_risk", 0.35),                    # literally finance+tech; computational_finance already gets this treatment
    ("educational_technology", "applied_computational", 0.30),  # ed-tech is fundamentally a technology field
    ("urban_informatics", "urban_infra_planning", 0.30),        # "urban" in the name — data layer over real infrastructure planning
    ("forensic_science", "criminal_public_law", 0.30),          # forensic science's primary application is criminal justice
    ("criminology_penology", "sociology_social_work", 0.30),    # criminology is classically a social/behavioural discipline, not just law
    ("neuroscience", "biological_life_sci", 0.30),               # neuroscience is a life science, not only a behavioural one
    ("actuarial_science", "data_quant_analytics", 0.30),         # actuarial science is applied statistics
    ("nutrition_dietetics", "public_health_fam", 0.25),          # clinical/public-health nutrition angle
    ("space_materials", "space_systems_propulsion", 0.30),       # materials science applied specifically to spacecraft
    ("geography", "earth_environmental_sci", 0.30),              # physical geography is an earth science
    ("agricultural_food_engineering", "agronomy_crop_sci", 0.30), # explicitly agricultural application
]


# =============================================================================
# SECTION 6 — REGISTRY LABEL LOOKUP (field_id -> real label/domain)
# =============================================================================

_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "india_course_registry_v11.json")
_registry_cache: Optional[Dict[str, Any]] = None


def _load_registry_branches() -> Dict[str, Any]:
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            _registry_cache = json.load(f).get("branches", {})
    except Exception:
        _registry_cache = {}
    return _registry_cache


def _field_label(field_id: str) -> str:
    branch = _load_registry_branches().get(field_id)
    if branch and branch.get("label"):
        return branch["label"]
    return field_id.replace("_", " ").title()


def _field_domain(field_id: str) -> str:
    branch = _load_registry_branches().get(field_id)
    return (branch or {}).get("domain", "")


# =============================================================================
# SECTION 7 — BUILD THE JYOTISHAI ONTOLOGY GRAPH
# =============================================================================

def build_jyotish_ontology_kg() -> OntologyKG:
    _validate_cluster_coverage()
    kg = OntologyKG()

    # ---- 7.1 Astro Evidence nodes (9 grahas; real shadbala-backed) ----
    for planet in _PLANET_MIN_SHADBALA:
        kg.add_node(Node(
            id=f"astro_{planet.lower()}",
            label=f"{planet} Strength",
            type=NodeType.ASTRO_EVIDENCE,
            description=f"Functional strength of {planet} (shadbala_virupas / _PLANET_MIN_SHADBALA ratio).",
        ))

    # ---- 7.2 Trait nodes (26 aptitude dimensions, reused from G27) ----
    for dim_id, dim_label in _APTITUDE_DIM_LABEL.items():
        kg.add_node(Node(
            id=f"trait_{dim_id}",
            label=dim_label.title(),
            type=NodeType.TRAIT,
        ))

    # ---- 7.3 Astro Evidence -> Trait edges (from _PLANET_APTITUDE) ----
    for planet, dims in _PLANET_APTITUDE.items():
        astro_id = f"astro_{planet.lower()}"
        if astro_id not in kg.nodes:
            continue
        for dim_id, weight in dims.items():
            trait_id = f"trait_{dim_id}"
            if trait_id not in kg.nodes:
                continue
            kg.add_edge(astro_id, trait_id, weight=round(min(weight, 1.5), 3))

    # ---- 7.4 Competency nodes (15, verbatim from competency_ontology.py) ----
    for comp_id, meta in COMPETENCY_META.items():
        kg.add_node(Node(
            id=f"comp_{comp_id}",
            label=meta["label"],
            type=NodeType.COMPETENCY,
            description=meta.get("description", ""),
            metadata={"planets": ",".join(meta.get("planets", []))},
        ))

    # ---- 7.5 Trait -> Competency edges (derived, not hand-picked) ----
    # Positional decay: first-listed planet in a competency's signature is
    # its primary karaka, later ones secondary/tertiary contributors.
    _POSITION_WEIGHTS = [1.0, 0.75, 0.55, 0.40]
    for comp_id, meta in COMPETENCY_META.items():
        planets = meta.get("planets", [])
        accum: Dict[str, float] = defaultdict(float)
        for i, planet in enumerate(planets):
            pos_w = _POSITION_WEIGHTS[min(i, len(_POSITION_WEIGHTS) - 1)]
            for dim_id, dim_w in _PLANET_APTITUDE.get(planet, {}).items():
                accum[dim_id] += pos_w * dim_w * 0.6
        for dim_id, w in accum.items():
            trait_id = f"trait_{dim_id}"
            if trait_id not in kg.nodes:
                continue
            kg.add_edge(trait_id, f"comp_{comp_id}", weight=round(min(w, 1.5), 3))

    # ---- 7.6 Cluster nodes (8, new) ----
    for cluster_id, meta in CLUSTER_META.items():
        kg.add_node(Node(
            id=cluster_id,
            label=meta["label"],
            type=NodeType.CLUSTER,
        ))

    # ---- 7.7 Competency -> Cluster edges ----
    # 2026-07-04 audit fix: a competency may need edges to MORE than one
    # cluster when FAMILY_CLUSTER_OVERRIDE redirects some of its families
    # elsewhere (see _clusters_for_competency) — otherwise propagate_scores()
    # could never reach the overridden families at all.
    for comp_id in COMPETENCY_META:
        for cluster_id in _clusters_for_competency(comp_id):
            kg.add_edge(f"comp_{comp_id}", cluster_id, weight=1.0)

    # ---- 7.8 Career Family nodes (68, verbatim from competency_ontology.py) ----
    for fam_id, meta in FAMILY_META.items():
        kg.add_node(Node(
            id=f"fam_{fam_id}",
            label=meta["label"],
            type=NodeType.CAREER_FAMILY,
            metadata={"competency": meta.get("competency", "")},
        ))

    # ---- 7.9 Cluster -> Career Family edges (via competency, honoring
    # FAMILY_CLUSTER_OVERRIDE — see _cluster_for_family) ----
    for fam_id in FAMILY_META:
        cluster_id = _cluster_for_family(fam_id)
        if cluster_id:
            kg.add_edge(cluster_id, f"fam_{fam_id}", weight=1.0)

    # ---- 7.10 Field nodes (199, verbatim ids; labels from real registry) ----
    for field_id in FIELD_TO_FAMILY:
        kg.add_node(Node(
            id=field_id,
            label=_field_label(field_id),
            type=NodeType.FIELD,
            broadness_penalty=FIELD_BROADNESS_PENALTY.get(field_id, 0.0),
            metadata={"domain": _field_domain(field_id)},
        ))

    # ---- 7.11 Career Family -> Field edges: primary (weight 1.0) ----
    for field_id, fam_id in FIELD_TO_FAMILY.items():
        kg.add_edge(f"fam_{fam_id}", field_id, weight=1.0, relation="primary")

    # ---- 7.12 Career Family -> Field edges: secondary (multi-parent) ----
    for field_id, fam_id, weight in SECONDARY_FIELD_FAMILY_EDGES:
        if field_id not in kg.nodes:
            continue
        fam_node_id = f"fam_{fam_id}"
        if fam_node_id not in kg.nodes:
            continue
        kg.add_edge(fam_node_id, field_id, weight=weight, relation="secondary")

    kg.validate()
    return kg


# =============================================================================
# SECTION 8 — CHART -> ASTRO EVIDENCE ADAPTER
# =============================================================================

def evidence_from_shadbala(shadbala: Dict[str, float]) -> Dict[str, float]:
    """Real per-chart planet strength -> Astro Evidence node scores.

    Uses the same normalization convention already used everywhere else in
    the engine (engine.py, engine_io.py, boosts.py): ratio = shadbala /
    _PLANET_MIN_SHADBALA[planet], capped at 2.5. A ratio of 1.0 means the
    planet is exactly at its classical minimum required strength.
    """
    evidence: Dict[str, float] = {}
    for planet, min_v in _PLANET_MIN_SHADBALA.items():
        sv = shadbala.get(planet)
        if sv is None:
            continue
        ratio = min(float(sv) / min_v, 2.5) if min_v else 1.0
        evidence[f"astro_{planet.lower()}"] = round(ratio, 4)
    return evidence


def evidence_from_chart(chart: Dict[str, Any]) -> Dict[str, float]:
    """Convenience wrapper: pull shadbala_virupas from D1 in pyhora_calculations."""
    pyh = chart.get("pyhora_calculations", {})
    d1 = (pyh.get("divisional_charts") or {}).get("D1_rashi") or {}
    d1 = d1 if isinstance(d1, dict) else {}
    planets = d1.get("planets") or pyh.get("planets_d1") or {}
    shadbala = {planet: pdata.get("shadbala_virupas") for planet, pdata in planets.items()
                if isinstance(pdata, dict) and pdata.get("shadbala_virupas") is not None}
    return evidence_from_shadbala(shadbala)


# =============================================================================
# SECTION 9 — MAIN ENTRY POINTS
# =============================================================================

_kg_singleton: Optional[OntologyKG] = None


def get_ontology_kg() -> OntologyKG:
    """Lazily-built, process-wide singleton (the graph is static — it does
    not depend on any single chart)."""
    global _kg_singleton
    if _kg_singleton is None:
        _kg_singleton = build_jyotish_ontology_kg()
    return _kg_singleton


def rank_fields_via_graph(
    shadbala: Dict[str, float],
    top_n: int = 20,
    sibling_suppression: bool = True,
) -> List[Tuple[str, str, float]]:
    """Standalone graph-based leaderboard from real per-chart planet
    strength alone (no yogas/dashas/houses — this is a coarser signal than
    the full deterministic engine and is meant as a diagnostic cross-check,
    NOT a replacement for engine.py's final_score)."""
    kg = get_ontology_kg()
    evidence = evidence_from_shadbala(shadbala)
    raw_scores = kg.propagate_scores(evidence)
    return kg.ranked_fields(raw_scores, top_n=top_n, sibling_suppression=sibling_suppression)


def attach_graph_diagnostics(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """SAFE, additive, engine-agnostic enrichment: attaches graph structural
    metadata to already-scored engine results WITHOUT touching final_score.
    Call this after apply_competency_ontology_layer() in engine.py if/when
    you want the richer multi-parent + broadness-penalty context surfaced
    in the report; it is not wired into engine.py automatically by this
    module (see the file docstring's ADDITIVE / READ-ONLY constraint).

    Attaches per-result:
        graph_broadness_penalty : float (0-0.25, the field's own genericity discount)
        graph_family_memberships: [(family_label, edge_weight, "primary"|"secondary"), ...]
        graph_cluster           : the field's cluster label (via its primary family)
        graph_note              : one-line human explanation
    """
    kg = get_ontology_kg()
    for r in results:
        field_id = r.get("field_id", "")
        node = kg.nodes.get(field_id)
        if node is None:
            continue
        memberships = []
        cluster_label = ""
        for fam_node_id, weight in kg.parents_of(field_id, NodeType.CAREER_FAMILY):
            fam_meta = kg.nodes[fam_node_id]
            edges = [e for e in kg.in_edges[field_id] if e.source == fam_node_id]
            relation = edges[0].relation if edges else "primary"
            memberships.append((fam_meta.label, weight, relation))
            if relation == "primary":
                fam_id = fam_node_id[len("fam_"):]
                # 2026-07-04 audit fix: use the same override-aware lookup
                # as the graph build (_cluster_for_family) instead of a raw
                # competency lookup, so diagnostics always agree with the
                # graph's real Cluster->Family edges (e.g. real_estate_property
                # reports "Commerce, Finance & Enterprise", not "Advanced
                # Engineering & Physical Systems").
                cluster_id = _cluster_for_family(fam_id)
                if cluster_id:
                    cluster_label = kg.nodes[cluster_id].label

        r["graph_broadness_penalty"] = node.broadness_penalty
        r["graph_family_memberships"] = memberships
        r["graph_cluster"] = cluster_label
        if node.broadness_penalty > 0:
            note = (
                f"{node.label} is treated as a structurally broad/generic field "
                f"(-{round(node.broadness_penalty * 100)}% genericity discount in the "
                f"graph diagnostic) — its ranking here should be read with that in mind."
            )
        elif len(memberships) > 1:
            note = (
                f"{node.label} genuinely spans multiple career families "
                f"({', '.join(m[0] for m in memberships)}) rather than belonging to just one."
            )
        else:
            note = f"{node.label} is a sharply-defined specialization with no genericity discount."
        r["graph_note"] = note
    return results


# =============================================================================
# SECTION 10 — COVERAGE VALIDATION (dev/test helper)
# =============================================================================

def validate_full_coverage() -> Dict[str, List[str]]:
    """Sanity-check every field/family/competency from competency_ontology.py
    made it into the graph with at least one path to an Astro Evidence node.
    Returns dict of problem lists (empty lists = fully healthy)."""
    kg = get_ontology_kg()
    problems: Dict[str, List[str]] = {
        "fields_missing_from_graph": [],
        "families_missing_from_graph": [],
        "competencies_missing_from_graph": [],
        "fields_with_no_family_parent": [],
    }
    for field_id in FIELD_TO_FAMILY:
        if field_id not in kg.nodes:
            problems["fields_missing_from_graph"].append(field_id)
        elif not kg.parents_of(field_id, NodeType.CAREER_FAMILY):
            problems["fields_with_no_family_parent"].append(field_id)
    for fam_id in FAMILY_META:
        if f"fam_{fam_id}" not in kg.nodes:
            problems["families_missing_from_graph"].append(fam_id)
    for comp_id in COMPETENCY_META:
        if f"comp_{comp_id}" not in kg.nodes:
            problems["competencies_missing_from_graph"].append(comp_id)
    return problems


# =============================================================================
# INTEGRATION NOTE (read before wiring into engine.py)
# =============================================================================
# This module is deliberately NOT imported by engine.py. To use it:
#
#   from .ontology_kg import attach_graph_diagnostics
#   top_35 = attach_graph_diagnostics(top_35)   # after apply_competency_ontology_layer
#
# This only adds new keys (graph_broadness_penalty, graph_family_memberships,
# graph_cluster, graph_note) to each result dict — it never touches
# final_score, so it carries zero regression risk against
# tests/test_regression_locked.py or tests/test_career_track_regressions.py.
#
# If a future pass wants the graph to actively influence ranking (e.g. a
# bounded +/-3% "graph_confidence_adjustment_pct" nudge, same pattern as the
# existing family-cohesion/yoga-alignment adjustments), that is a separate,
# explicit decision — start from rank_fields_via_graph()'s sibling
# suppression + broadness-penalty output and follow the same bounded-nudge
# cap pattern already used in apply_family_cohesion_adjustment().


if __name__ == "__main__":
    import glob

    problems = validate_full_coverage()
    print("Coverage check:", {k: len(v) for k, v in problems.items()})
    for k, v in problems.items():
        if v:
            print(f"  {k}: {v}")

    chart_files = glob.glob(os.path.join(os.path.dirname(__file__), "..", "Charts", "*_chart_details.json"))
    if chart_files:
        with open(chart_files[0], "r", encoding="utf-8") as f:
            chart = json.load(f)
        results = rank_fields_via_graph(
            {p: pdata.get("shadbala_virupas") for p, pdata in
             chart.get("pyhora_calculations", {}).get("planets_d1", {}).items()},
            top_n=20,
        )
        print(f"\nGraph-based top 20 for {os.path.basename(chart_files[0])}")
        print("-" * 60)
        for rank, (_, label, score) in enumerate(results, 1):
            print(f"{rank:02d}. {label:<45} {score:>5.1f}%")
