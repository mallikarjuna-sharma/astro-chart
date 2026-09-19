"""jyotish/competency_ontology.py — Competency-First Hierarchical Ontology Layer.

Implements the architectural gap raised in the 2026-07-04 ontology audit (G1-G18,
G22, G23-G31): the engine previously went straight from astrology to a flat, 199-branch
field leaderboard with no intermediate structure. This module adds the missing
middle layers:

    Astrology (planets/houses/yogas)
        -> Competency            (~15 broad ability clusters, e.g. "Physical &
                                   Mechanical Systems", "Computational Intelligence")
        -> Career Family         (~55 cohesive groupings, e.g. "Built Environment",
                                   "Electronics & Embedded Systems")
        -> Field / Specialization (the existing 199 registry branches — unchanged)

Design decisions (see COMPETENCY_ONTOLOGY_UPGRADE_2026-07.md for full rationale):

  * This module is ADDITIVE. It does not touch BRANCH_PLANET_AFFINITY (which
    already carries a great deal of doctrinal differentiation per branch — see
    the "Taxonomy consolidation fix (audit)" comments throughout affinity.py).
    It groups the *existing* 199 well-differentiated leaves into a real tree and
    exposes aggregate/explanatory signals on top of them.
  * The per-field `final_score` used by the deterministic engine and pinned by
    tests/test_regression_locked.py and tests/test_career_track_regressions.py
    is preserved. Two small, bounded, additive adjustments are applied on top:
    "family cohesion" (+/-4% cap, apply_family_cohesion_adjustment) and
    "yoga alignment" (+0-5% cap, apply_yoga_alignment_adjustment, G22) —
    following the same bounded-nudge pattern already used elsewhere in
    engine.py (tie-break cascade: +/-0.45pts; medical governance rebalance:
    0.90x cap).
  * G27 (aptitude explanation) and G28 (life-stage evolution) are pure
    explanatory additions — they never touch final_score.
  * G31 (cross-chart normalization) is an explicitly-caveated PROXY signal
    only (see Section 12) — it does not touch final_score either.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger("jyotish_engine_v11_0")

# =============================================================================
# SECTION 1 — COMPETENCY NODES  (G1, G5-G9, G13, G14)
# =============================================================================
# Each competency carries a short planetary signature used for explanation
# chains (G23) — NOT a new scoring weight table. The real per-branch affinity
# vectors in affinity.py remain authoritative; this is the human-readable
# "why" that sits above them.

COMPETENCY_META: Dict[str, Dict[str, Any]] = {
    "systems_electronics": {
        "label": "Systems Engineering & Electronics",
        "planets": ["Mercury", "Mars", "Saturn"],
        "description": "Signal, circuit, and embedded-systems reasoning — precision + structure + execution.",
    },
    "physical_mechanical": {
        "label": "Physical & Mechanical Systems",
        "planets": ["Mars", "Saturn"],
        "description": "Force, material, and process mastery — building and moving physical things.",
    },
    "computational_intelligence": {
        "label": "Computational Intelligence",
        "planets": ["Mercury", "Rahu", "Saturn"],
        "description": "Abstraction, algorithmic reasoning, and data-driven pattern discovery.",
    },
    "built_environment": {
        "label": "Built Environment & Infrastructure",
        "planets": ["Saturn", "Venus", "Mars"],
        "description": "Structural discipline (Saturn) fused with proportion/aesthetics (Venus) at scale.",
    },
    "frontier_space": {
        "label": "Frontier & Space Technology",
        "planets": ["Rahu", "Mars", "Sun"],
        "description": "Novelty-frontier drive (Rahu) plus execution (Mars) and authority/altitude (Sun).",
    },
    "design_creative": {
        "label": "Design & Creative Expression",
        "planets": ["Venus", "Mercury", "Moon"],
        "description": "Aesthetic sensibility (Venus) directed through craft/technique (Mercury).",
    },
    "media_performance": {
        "label": "Media, Communication & Performance",
        "planets": ["Mercury", "Moon", "Venus", "Rahu"],
        "description": "Expression and reach — telling stories to an audience.",
    },
    "medical_health": {
        "label": "Medical & Health Sciences",
        "planets": ["Sun", "Mars", "Moon", "Jupiter"],
        "description": "Healing competency — clinical execution (Mars/Sun) guided by care and wisdom (Moon/Jupiter).",
    },
    "life_earth_sciences": {
        "label": "Life & Earth Sciences",
        "planets": ["Moon", "Mercury", "Jupiter", "Saturn"],
        "description": "Systematic study of living systems and the natural world.",
    },
    "governance_institutions": {
        "label": "Governance, Law & Public Institutions",
        "planets": ["Sun", "Jupiter", "Saturn"],
        "description": "Authority (Sun) exercised through dharma/doctrine (Jupiter) and structure (Saturn).",
    },
    "knowledge_scholarship": {
        "label": "Knowledge, Scholarship & Humanities",
        "planets": ["Jupiter", "Mercury", "Ketu"],
        "description": "Jupiter's core domain: wisdom-transmission, texts, and intellectual lineage.",
    },
    "commerce_enterprise": {
        "label": "Commerce, Finance & Enterprise",
        "planets": ["Jupiter", "Mercury", "Saturn"],
        "description": "Value creation, exchange, and organisational growth.",
    },
    "behavioural_social": {
        "label": "Behavioural & Social Sciences",
        "planets": ["Moon", "Jupiter", "Mercury"],
        "description": "Understanding mind, motivation, and social systems.",
    },
    "agri_environment": {
        "label": "Agriculture & Environmental Systems",
        "planets": ["Moon", "Saturn"],
        "description": "Cultivation, ecology, and sustainable resource stewardship.",
    },
    "defence_security": {
        "label": "Defence, Security & Strategic Studies",
        "planets": ["Mars", "Sun", "Saturn"],
        "description": "Sun/Mars command signature applied to protection and strategic competition.",
    },
}

# =============================================================================
# SECTION 2 — CAREER FAMILIES  (G2, G12-G14)
# =============================================================================
# family_id -> {label, competency, description}
# Families are the "no cannibalization" unit: siblings within a family are
# expected to co-activate, not compete, per G2/G16.

FAMILY_META: Dict[str, Dict[str, str]] = {
    # ---- systems_electronics ----
    "electronics_embedded":      {"label": "Electronics & Embedded Systems", "competency": "systems_electronics"},
    "semiconductor_vlsi":        {"label": "Semiconductor & VLSI",           "competency": "systems_electronics"},
    "telecom_signal":            {"label": "Telecom & Signal Systems",       "competency": "systems_electronics"},
    "power_energy_systems":      {"label": "Power & Energy Systems",         "competency": "systems_electronics"},

    # ---- physical_mechanical ----
    "mechanical_manufacturing":  {"label": "Mechanical & Manufacturing Systems", "competency": "physical_mechanical"},
    "materials_extractive":      {"label": "Materials & Extractive Engineering", "competency": "physical_mechanical"},
    "process_chemical":          {"label": "Process & Chemical Engineering",     "competency": "physical_mechanical"},
    "marine_ocean":              {"label": "Marine & Ocean Engineering",         "competency": "physical_mechanical"},
    "safety_industrial_risk":    {"label": "Safety, Fire & Industrial Risk",     "competency": "physical_mechanical"},
    "nuclear_engineering_fam":   {"label": "Nuclear & Radiation Engineering",    "competency": "physical_mechanical"},

    # ---- computational_intelligence ----
    "software_cs":               {"label": "Software & Computer Science",       "competency": "computational_intelligence"},
    "ai_ml":                      {"label": "AI & Machine Learning",             "competency": "computational_intelligence"},
    "data_quant_analytics":       {"label": "Data, Statistics & Quant Analytics","competency": "computational_intelligence"},
    "cyber_distributed":          {"label": "Cybersecurity & Distributed Systems","competency": "computational_intelligence"},
    "applied_computational":      {"label": "Applied Computational Science",     "competency": "computational_intelligence"},

    # ---- built_environment ----
    "architecture_spatial":      {"label": "Architecture & Spatial Design",     "competency": "built_environment"},
    "civil_structural":          {"label": "Civil & Structural Engineering",    "competency": "built_environment"},
    "urban_infra_planning":      {"label": "Urban & Infrastructure Planning",   "competency": "built_environment"},
    "real_estate_property":      {"label": "Real Estate & Property",           "competency": "built_environment"},

    # ---- frontier_space ----
    "aerospace_aeronautics":     {"label": "Aerospace & Aeronautics",           "competency": "frontier_space"},
    "space_systems_propulsion":  {"label": "Space Systems & Propulsion",        "competency": "frontier_space"},
    "space_science_exploration": {"label": "Space Science & Exploration",       "competency": "frontier_space"},

    # ---- design_creative ----
    "design_thinking":           {"label": "Design Thinking — UX/Product/Industrial", "competency": "design_creative"},
    "visual_craft_arts":         {"label": "Visual & Craft Arts",               "competency": "design_creative"},
    "interactive_game_design":   {"label": "Interactive & Game Design",         "competency": "design_creative"},

    # ---- media_performance ----
    "performing_arts_fam":       {"label": "Performing Arts",                   "competency": "media_performance"},
    "film_screen_media":         {"label": "Film & Screen Media",               "competency": "media_performance"},
    "journalism_public_comm":    {"label": "Journalism & Public Communication", "competency": "media_performance"},

    # ---- medical_health ----
    "clinical_medicine":         {"label": "Clinical Medicine",                 "competency": "medical_health"},
    "alternative_holistic_med":  {"label": "Alternative & Holistic Medicine",   "competency": "medical_health"},
    "nursing_allied_health":     {"label": "Nursing & Allied Health Care",      "competency": "medical_health"},
    "medical_technology_diag":   {"label": "Medical Technology & Diagnostics",  "competency": "medical_health"},
    "medical_research_fam":      {"label": "Medical Research & Biomedical Science", "competency": "medical_health"},
    "pharma_sciences":           {"label": "Pharmaceutical Sciences",           "competency": "medical_health"},
    "mental_behavioural_health": {"label": "Mental & Behavioural Health",       "competency": "medical_health"},
    "public_health_fam":         {"label": "Public Health & Population Medicine", "competency": "medical_health"},

    # ---- life_earth_sciences ----
    "physical_chemical_sci":     {"label": "Physical & Chemical Sciences",      "competency": "life_earth_sciences"},
    "mathematical_sciences":     {"label": "Mathematical Sciences",             "competency": "life_earth_sciences"},
    "biological_life_sci":       {"label": "Biological & Life Sciences",        "competency": "life_earth_sciences"},
    "earth_environmental_sci":   {"label": "Earth & Environmental Sciences",    "competency": "life_earth_sciences"},
    "astronomy_planetary_sci":   {"label": "Astronomy & Planetary Science",     "competency": "life_earth_sciences"},
    "forensic_investigative":    {"label": "Forensic & Investigative Science",  "competency": "life_earth_sciences"},

    # ---- governance_institutions ----
    "civil_admin_services":      {"label": "Civil & Administrative Services",   "competency": "governance_institutions"},
    "defence_security_services": {"label": "Defence & Security Services",       "competency": "defence_security"},
    "corporate_commercial_law":  {"label": "Corporate & Commercial Law",        "competency": "governance_institutions"},
    "criminal_public_law":       {"label": "Criminal & Public Law",             "competency": "governance_institutions"},
    "intl_constitutional_law":   {"label": "International & Constitutional Law","competency": "governance_institutions"},
    "diplomacy_intl_relations":  {"label": "Diplomacy & International Relations", "competency": "governance_institutions"},
    "strategic_studies":         {"label": "Strategic & Conflict Studies",      "competency": "defence_security"},

    # ---- knowledge_scholarship ----
    "humanities_scholarship":    {"label": "Humanities & Classical Scholarship", "competency": "knowledge_scholarship"},
    "teaching_pedagogy":         {"label": "Teaching & Pedagogy",               "competency": "knowledge_scholarship"},
    "research_academia_fam":     {"label": "Research & Academia",              "competency": "knowledge_scholarship"},
    "sports_physical_ed":        {"label": "Sports & Physical Sciences",       "competency": "knowledge_scholarship"},
    "linguistics_language":      {"label": "Linguistics & Language Studies",   "competency": "knowledge_scholarship"},

    # ---- commerce_enterprise ----
    "finance_quant_risk":        {"label": "Finance & Quantitative Risk",       "competency": "commerce_enterprise"},
    "management_enterprise":     {"label": "Management & Enterprise",           "competency": "commerce_enterprise"},
    "marketing_consumer_biz":    {"label": "Marketing & Consumer Business",     "competency": "commerce_enterprise"},
    "economics_policy_analysis": {"label": "Economics & Policy Analysis",       "competency": "commerce_enterprise"},
    "healthcare_institutional_mgmt": {"label": "Healthcare & Institutional Management", "competency": "commerce_enterprise"},
    "rural_dev_management":      {"label": "Rural & Development Management",    "competency": "commerce_enterprise"},

    # ---- behavioural_social ----
    "psychology_behavioural":    {"label": "Psychology & Applied Behaviour",    "competency": "behavioural_social"},
    "sociology_social_work":     {"label": "Sociology & Social Work",          "competency": "behavioural_social"},
    "cognitive_neuro_sci":       {"label": "Cognitive & Neuro Sciences",        "competency": "behavioural_social"},
    "gender_dev_studies":        {"label": "Gender & Development Studies",      "competency": "behavioural_social"},

    # ---- agri_environment ----
    "agronomy_crop_sci":         {"label": "Agronomy & Crop Sciences",          "competency": "agri_environment"},
    "agribusiness_rural_econ":   {"label": "Agribusiness & Rural Economy",      "competency": "agri_environment"},
    "environmental_ecological":  {"label": "Environmental & Ecological Systems","competency": "agri_environment"},
    "environmental_engineering_fam": {"label": "Environmental Engineering & Water Systems", "competency": "agri_environment"},
}

# =============================================================================
# SECTION 3 — FIELD -> FAMILY MAPPING  (all registry branch ids)
# =============================================================================
# Every branch_id from india_course_registry_v11.json + affinity.py's
# extension dicts is mapped exactly once to a primary career_family. (Some
# branches are legitimately cross-competency in classical terms — e.g.
# architecture sits at the intersection of Design/Venus and Built
# Environment/Saturn — a single primary home is chosen per G2's own worked
# example, and the competency description notes the secondary linkage.)

FIELD_TO_FAMILY: Dict[str, str] = {
    # ---- Engineering: Electronics & Embedded ----
    "electronics_communication_engineering": "electronics_embedded",
    "instrumentation_engineering":           "electronics_embedded",
    "internet_of_things":                    "electronics_embedded",
    "electrical_engineering":                "electronics_embedded",
    "mechatronics_engineering":              "electronics_embedded",
    "robotics_automation":                   "electronics_embedded",

    "microelectronics_vlsi":                 "semiconductor_vlsi",
    "semiconductor_nanoelectronics":         "semiconductor_vlsi",
    "nanotechnology_engineering":            "semiconductor_vlsi",

    "telecommunication_engineering":         "telecom_signal",
    "satellite_communication_engineering":   "telecom_signal",
    "optical_photonics_engineering":         "telecom_signal",

    "power_systems_engineering":             "power_energy_systems",
    "energy_engineering":                    "power_energy_systems",

    # ---- Engineering: Physical / Mechanical ----
    "mechanical_engineering":                "mechanical_manufacturing",
    "automotive_engineering":                "mechanical_manufacturing",
    "industrial_engineering":                "mechanical_manufacturing",
    "production_manufacturing_engineering":  "mechanical_manufacturing",
    "refrigeration_airconditioning":         "mechanical_manufacturing",

    "metallurgical_engineering":             "materials_extractive",
    "materials_science_engineering":         "materials_extractive",
    "mining_engineering":                    "materials_extractive",
    "petroleum_engineering":                 "materials_extractive",
    "ceramic_engineering":                   "materials_extractive",
    "polymer_plastics_engineering":          "materials_extractive",
    "rubber_technology":                     "materials_extractive",
    "leather_technology":                    "materials_extractive",
    "textile_technology":                    "materials_extractive",
    "space_materials":                       "materials_extractive",
    "geological_engineering":                "materials_extractive",

    "chemical_engineering":                  "process_chemical",
    "chemical_engineering_data_science":     "process_chemical",
    "agricultural_food_engineering":         "process_chemical",
    "printing_packaging_technology":         "process_chemical",
    "applied_chemistry":                     "process_chemical",

    "marine_engineering":                    "marine_ocean",
    "naval_architecture":                    "marine_ocean",

    "fire_safety_engineering":               "safety_industrial_risk",

    "nuclear_engineering":                   "nuclear_engineering_fam",

    # ---- Technology / Computational Intelligence ----
    "computer_science_engineering":          "software_cs",
    "information_technology":                "software_cs",
    "cloud_devops":                          "software_cs",
    "information_systems":                   "software_cs",
    "it_systems_planning":               "software_cs",
    "software_infrastructure_engineering":                  "software_cs",
    "operations_research":                   "data_quant_analytics",
    "engineering_management":                "management_enterprise",
    "it_business_advisory":                 "management_enterprise",
    "it_governance":                         "cyber_distributed",

    "artificial_intelligence":               "ai_ml",
    "data_science_engineering":              "ai_ml",
    "quantum_computing":                     "ai_ml",

    "statistics_data_science":               "data_quant_analytics",
    "mathematics_computing":                 "data_quant_analytics",
    "computational_finance":                 "data_quant_analytics",
    "econometrics":                          "data_quant_analytics",
    "economics_data_science":                "data_quant_analytics",

    "cybersecurity":                         "cyber_distributed",
    "blockchain_web3":                       "cyber_distributed",

    "bioinformatics":                        "applied_computational",
    "geographic_information_systems":        "applied_computational",
    "health_informatics":                    "applied_computational",
    "game_design_technology":                "applied_computational",
    "fintech":                               "applied_computational",
    "urban_informatics":                     "applied_computational",

    # ---- Built Environment ----
    "architecture":                          "architecture_spatial",
    "landscape_architecture":                "architecture_spatial",

    "civil_engineering":                     "civil_structural",
    "construction_engineering_management":   "civil_structural",

    "urban_regional_planning":               "urban_infra_planning",
    "infrastructure_planning_engineering":   "urban_infra_planning",
    "transportation_engineering":            "urban_infra_planning",

    "real_estate_management":                "real_estate_property",

    # ---- Frontier & Space ----
    "aerospace_engineering":                 "aerospace_aeronautics",
    "aeronautical_engineering":              "aerospace_aeronautics",

    "astronautical_engineering":             "space_systems_propulsion",
    "rocket_propulsion":                     "space_systems_propulsion",
    "space_systems_engineering":             "space_systems_propulsion",
    "satellite_engineering":                 "space_systems_propulsion",

    "space_sciences_engineering":            "space_science_exploration",
    "earth_observation_remote_sensing":      "space_science_exploration",
    "planetary_science":                     "space_science_exploration",
    "astronomy_astrophysics":                "astronomy_planetary_sci",  # science-domain sibling, see life_earth_sciences

    # ---- Design & Creative ----
    "design_ux_product":                     "design_thinking",
    "fashion_design":                        "design_thinking",
    "interior_design":                       "design_thinking",

    "fine_arts":                             "visual_craft_arts",
    "visual_communication":                  "visual_craft_arts",
    "photography":                           "visual_craft_arts",
    "textile_design":                        "visual_craft_arts",
    "animation_multimedia":                  "visual_craft_arts",

    "game_design_technology_dup":            "interactive_game_design",  # placeholder guard, see applied_computational

    # ---- Media & Performance ----
    "music":                                 "performing_arts_fam",
    "performing_arts":                       "performing_arts_fam",
    "theatre_drama":                         "performing_arts_fam",

    "film_television_production":            "film_screen_media",

    "journalism_media":                      "journalism_public_comm",
    "mass_communication":                    "journalism_public_comm",

    # ---- Medicine ----
    "medicine_mbbs":                         "clinical_medicine",
    "dentistry":                             "clinical_medicine",
    "veterinary_science":                    "clinical_medicine",

    "ayurveda":                              "alternative_holistic_med",
    "homeopathy":                            "alternative_holistic_med",
    "unani_medicine":                        "alternative_holistic_med",
    "yoga_naturopathy":                      "alternative_holistic_med",

    "nursing":                               "nursing_allied_health",
    "physiotherapy":                         "nursing_allied_health",
    "occupational_therapy":                  "nursing_allied_health",
    "paramedics_emergency_medicine":         "nursing_allied_health",
    "speech_language_pathology":             "nursing_allied_health",
    "optometry":                             "nursing_allied_health",
    "prosthetics_orthotics":                 "nursing_allied_health",

    "medical_laboratory_technology":         "medical_technology_diag",
    "radiography_imaging":                   "medical_technology_diag",
    "cardiac_technology":                    "medical_technology_diag",
    "medical_physics":                       "medical_technology_diag",

    "medical_research":                      "medical_research_fam",
    "biomedical_engineering":                "medical_research_fam",
    "biotechnology_biochemical_engineering": "medical_research_fam",
    "biotechnology_bsc":                     "medical_research_fam",

    "pharmacy":                              "pharma_sciences",

    "psychiatry":                            "mental_behavioural_health",
    "clinical_psychology":                   "mental_behavioural_health",

    "public_health":                         "public_health_fam",
    "healthcare_management":                 "healthcare_institutional_mgmt",
    "health_informatics_dup":                "public_health_fam",  # placeholder guard, see applied_computational

    # ---- Science: Life & Earth ----
    "physics":                               "physical_chemical_sci",
    "chemistry":                             "physical_chemical_sci",
    "engineering_physics":                   "physical_chemical_sci",

    "mathematics":                           "mathematical_sciences",

    "biology":                               "biological_life_sci",
    "biological_sciences":                   "biological_life_sci",
    "botany_plant_science":                  "biological_life_sci",
    "zoology_animal_science":                "biological_life_sci",
    "microbiology":                          "biological_life_sci",
    "molecular_biology_genetics":            "biological_life_sci",
    "biochemistry":                          "biological_life_sci",
    "ecology_evolution":                     "biological_life_sci",
    "nutrition_dietetics":                   "biological_life_sci",

    "earth_sciences":                        "earth_environmental_sci",
    "geology_applied":                       "earth_environmental_sci",
    "geophysics":                            "earth_environmental_sci",
    "atmospheric_climate_science":           "earth_environmental_sci",
    "marine_oceanography":                   "earth_environmental_sci",

    "planetary_science_dup":                 "astronomy_planetary_sci",  # placeholder guard, see space_science_exploration

    "forensic_science":                      "forensic_investigative",

    # ---- Governance / Public / Law / Defence ----
    # civil_services re-added (2026-08-18, explicit user request): restored as
    # a career_route branch, same family as public_policy below. Re-added to
    # jyotish/affinity.py + jyotish/india_course_registry_v12.json together to
    # keep registry/affinity/ontology coverage consistent.
    "civil_services":                        "civil_admin_services",
    "public_policy":                         "civil_admin_services",

    "defence_military":                      "defence_security_services",
    "intelligence_security_studies":         "defence_security_services",

    "corporate_law":                         "corporate_commercial_law",
    "intellectual_property_law":             "corporate_commercial_law",

    "criminal_law":                          "criminal_public_law",
    "criminology_penology":                  "criminal_public_law",

    # GAP-FIX (2026-07-18, audit P2 taxonomy mismatch): environmental_law
    # used to sit under criminal_public_law (grouped with criminal_law/
    # criminology_penology) purely because it's "public law adjacent" --
    # but its actual practice is regulatory/statutory/constitutional
    # (environmental statutes, compliance, constitutional environmental
    # rights), not criminal prosecution. intl_constitutional_law (already
    # home to international_law/law_llb) is the better-fitting family.
    "environmental_law":                     "intl_constitutional_law",

    "international_law":                     "intl_constitutional_law",
    "law_llb":                               "intl_constitutional_law",

    "international_relations":               "diplomacy_intl_relations",
    "development_studies":                   "diplomacy_intl_relations",
    "political_science":                     "diplomacy_intl_relations",

    "defence_strategic_studies":             "strategic_studies",
    "peace_conflict_studies":                "strategic_studies",

    # ---- Knowledge / Humanities / Education ----
    "philosophy":                            "humanities_scholarship",
    "history_archaeology":                   "humanities_scholarship",
    "museum_heritage_studies":               "humanities_scholarship",
    "sanskrit_classical_studies":            "humanities_scholarship",
    "literature_languages":                  "humanities_scholarship",
    "liberal_arts_interdisciplinary":        "humanities_scholarship",
    "geography":                             "humanities_scholarship",

    "education_teaching":                    "teaching_pedagogy",
    "educational_technology":                "teaching_pedagogy",
    "library_information_science":           "teaching_pedagogy",

    "research_academia":                     "research_academia_fam",

    "physical_education":                    "sports_physical_ed",
    "sports_science_management":             "sports_physical_ed",

    "linguistics":                           "linguistics_language",
    "applied_linguistics":                   "linguistics_language",

    # ---- Commerce / Finance / Enterprise ----
    "actuarial_science":                     "finance_quant_risk",
    "finance_banking":                       "finance_quant_risk",
    "ca_cma_cs_professional":                "finance_quant_risk",
    "commerce_accounting":                   "finance_quant_risk",

    "business_management":                   "management_enterprise",
    "entrepreneurship":                      "management_enterprise",
    "supply_chain_logistics":                "management_enterprise",

    "digital_marketing":                     "marketing_consumer_biz",
    "tourism_management":                    "marketing_consumer_biz",
    "hotel_hospitality_management":          "marketing_consumer_biz",

    "economics":                             "economics_policy_analysis",

    "rural_management":                      "rural_dev_management",
    "agribusiness_management":               "agribusiness_rural_econ",

    # ---- Behavioural & Social ----
    "psychology":                            "psychology_behavioural",
    "organisational_psychology":             "psychology_behavioural",
    "behavioural_science":                   "psychology_behavioural",

    "social_work":                           "sociology_social_work",
    "sociology_anthropology":                "sociology_social_work",
    "gender_studies":                        "gender_dev_studies",

    "cognitive_science":                     "cognitive_neuro_sci",
    "neuroscience":                          "cognitive_neuro_sci",

    # GAP-FIX (2026-07-18, audit P2 taxonomy mismatch): computational_social
    # _science used to sit under cognitive_neuro_sci (with cognitive_science/
    # neuroscience) purely on the "computational + science of mind/society"
    # word association -- but its actual method is applying data/quant
    # techniques (network analysis, large-scale text/behavioral data,
    # statistical modeling) to social phenomena, not neuroscience or
    # cognition research. data_quant_analytics (home to statistics_data_
    # science/mathematics_computing/econometrics) is the better-fitting
    # family.
    "computational_social_science":          "data_quant_analytics",

    # ---- Agriculture & Environment ----
    "agriculture_forestry":                  "agronomy_crop_sci",
    "horticulture":                          "agronomy_crop_sci",
    "soil_science_agronomy":                 "agronomy_crop_sci",

    "environmental_science":                 "environmental_ecological",
    "environmental_studies_interdisciplinary": "environmental_ecological",
    "forestry_wildlife":                     "environmental_ecological",
    "fisheries_science":                     "environmental_ecological",
    "food_science_technology":               "environmental_ecological",

    "environmental_engineering":             "environmental_engineering_fam",
    "water_resources_engineering":           "environmental_engineering_fam",

    # GAP-FIX (2026-08-17, registry coverage regression): 7 fields added to
    # india_course_registry_v12.json + jyotish/affinity.py earlier today were
    # never mapped here, tripping registry_coverage_validator's
    # registry_not_in_ontology / affinity_not_in_ontology checks. Mapped to
    # the closest classical/domain-analog family, mirroring the sibling
    # field noted per entry.
    "aviation_pilot_training":               "aerospace_aeronautics",  # sibling: aerospace_engineering
    "dairy_technology":                      "environmental_ecological",  # sibling: food_science_technology
    "industrial_product_design":             "design_thinking",  # sibling: design_ux_product
    "jyotish_vedic_astrology":               "humanities_scholarship",  # sibling: sanskrit_classical_studies
    "nautical_science":                      "marine_ocean",  # sibling: marine_engineering
    "siddha_medicine":                       "alternative_holistic_med",  # sibling: ayurveda/unani_medicine
    "transportation_automotive_design":      "design_thinking",  # sibling: design_ux_product
}

# Remove placeholder guard duplicates (kept above only to document the
# cross-family relationship in comments; real assignment lives elsewhere).
for _dup_key in (
    "game_design_technology_dup", "health_informatics_dup",
    "planetary_science_dup",
):
    FIELD_TO_FAMILY.pop(_dup_key, None)

# Fallback: any branch_id encountered at runtime that isn't in the explicit
# map above gets a deterministic per-domain default family so the pipeline
# never KeyErrors on a registry that grows over time (new fields added
# without an ontology-team review). validate_coverage() (below) should be
# run whenever the registry changes so these fallbacks stay rare.
_DOMAIN_DEFAULT_FAMILY: Dict[str, str] = {
    "engineering": "mechanical_manufacturing",
    "science": "physical_chemical_sci",
    "medicine": "clinical_medicine",
    "technology": "software_cs",
    "commerce": "management_enterprise",
    "humanities": "humanities_scholarship",
    "law": "intl_constitutional_law",
    "arts": "visual_craft_arts",
    "media": "journalism_public_comm",
    "public": "civil_admin_services",
    "education": "teaching_pedagogy",
    "agriculture": "agronomy_crop_sci",
    "interdisciplinary": "applied_computational",
}


def get_family_id(field_id: str, domain: str = "") -> str:
    """Return the career_family id for a branch, with a domain-based fallback."""
    fam = FIELD_TO_FAMILY.get(field_id)
    if fam:
        return fam
    return _DOMAIN_DEFAULT_FAMILY.get((domain or "").lower(), "applied_computational")


def get_competency_id(family_id: str) -> str:
    return FAMILY_META.get(family_id, {}).get("competency", "knowledge_scholarship")


def get_ontology(field_id: str, domain: str = "") -> Dict[str, str]:
    """Return {competency, competency_label, career_family, career_family_label}."""
    fam_id = get_family_id(field_id, domain)
    fam_meta = FAMILY_META.get(fam_id, {"label": fam_id.replace("_", " ").title(), "competency": "knowledge_scholarship"})
    comp_id = fam_meta.get("competency", "knowledge_scholarship")
    comp_meta = COMPETENCY_META.get(comp_id, {"label": comp_id.replace("_", " ").title(), "planets": []})
    return {
        "competency": comp_id,
        "competency_label": comp_meta.get("label", comp_id),
        "career_family": fam_id,
        "career_family_label": fam_meta.get("label", fam_id),
    }


# =============================================================================
# SECTION 4 — CONFIDENCE BANDS  (G24)
# =============================================================================

# GAP-FIX (2026-07-18, audit P1 "'Very High confidence' is misleading"):
# these labels used to read as plain "Very High"/"High"/etc, which a reader
# naturally parses as statistical confidence -- but this is a same-chart
# relative score tier (where does this field rank among this chart's other
# candidates), not a confidence interval. 33/35 fields on a typical chart
# carry score_confidence: SPECULATIVE (see score_confidence_note below) and
# the engine is explicitly statistical_calibration: NOT_CALIBRATED, so a
# bare "Very High" label sitting next to those facts is contradictory. The
# "(relative)" qualifier is kept on every band, including the top one, so
# there is no unqualified "confidence" word left anywhere this function's
# output is displayed.
_CONFIDENCE_BANDS: List[Tuple[float, str]] = [
    (85.0, "Very High (relative)"),
    (70.0, "High (relative)"),
    (50.0, "Moderate (relative)"),
    (0.0,  "Weak (relative)"),
]

CONFIDENCE_BAND_CAVEAT = (
    "This is a same-chart relative score tier, not a statistical confidence "
    "level -- it says how this field ranks among this chart's other "
    "candidates, not how certain the engine is that the score is correct. "
    "See score_confidence/score_confidence_note for cross-method agreement, "
    "and statistical_calibration (always NOT_CALIBRATED currently) for why "
    "no true confidence interval is available."
)


def confidence_band(score_pct: float, top_score: float = None) -> str:
    """Map a score to a qualitative, same-chart-relative score tier. NOT a
    statistical confidence level -- see CONFIDENCE_BAND_CAVEAT.

    SCALE FIX (2026-08-18, tiered-ranking rollout): despite the "(relative)"
    labels and the docstring above always having claimed this is a
    same-chart RELATIVE tier, the original implementation applied the
    _CONFIDENCE_BANDS cutoffs directly to the raw score -- which only
    behaved relatively by coincidence, because the old flat 9-method blend
    happened to produce final_score in a ~45-100 range where the #1 field
    usually did clear 70-85. jyotish/tiered_ranking.py can now produce a
    much lower/tighter absolute range (e.g. ~13-27 on a real chart), where
    every field -- #1 and #20 alike -- fell into "Weak (relative)"
    regardless of actual rank, silently breaking the relative promise the
    label makes.

    `top_score` (when supplied by the caller -- this chart's own top
    final_score/family_score among the population being compared) makes
    this genuinely relative: `score_pct` is expressed as a percentage OF
    that leader before the band lookup, so the #1 field is always at or
    near 100% regardless of what absolute scale final_score happens to be
    on. Callers that don't yet pass `top_score` fall back to the old
    absolute-cutoff behavior (still correct for anything already on a
    0-100 scale) rather than raising, so this stays backward compatible.
    """
    try:
        s = float(score_pct)
    except (TypeError, ValueError):
        return "Weak (relative)"
    if top_score:
        try:
            top = float(top_score)
        except (TypeError, ValueError):
            top = 0.0
        if top > 0:
            s = max(0.0, min(100.0, (s / top) * 100.0))
    for threshold, label in _CONFIDENCE_BANDS:
        if s >= threshold:
            return label
    return "Weak (relative)"


# =============================================================================
# SECTION 5 — DEMAND-AWARE ANNOTATION  (G18, G32 — display-only, never
# touches the astrological score)
# =============================================================================
# Static, coarse "current/near-term hiring demand" tags per career family.
# This is explicitly cosmetic/informational: it is surfaced only in the
# cluster report as a secondary annotation, never blended into final_score.

_HIGH_DEMAND_FAMILIES = {
    "ai_ml", "semiconductor_vlsi", "cyber_distributed", "data_quant_analytics",
    "space_systems_propulsion", "clinical_medicine", "electronics_embedded",
    "software_cs",
}
_EMERGING_DEMAND_FAMILIES = {
    "applied_computational", "medical_research_fam", "environmental_engineering_fam",
    "aerospace_aeronautics",
}


def demand_tag(family_id: str) -> str:
    if family_id in _HIGH_DEMAND_FAMILIES:
        return "High current demand"
    if family_id in _EMERGING_DEMAND_FAMILIES:
        return "Emerging / growing demand"
    return "Stable demand"


# =============================================================================
# SECTION 6 — EXPLANATION CHAIN  (G23)
# =============================================================================

def build_explanation_chain(result: Dict[str, Any]) -> List[str]:
    """Build a planet -> competency -> career family -> field chain for one result.

    Example: ["Mars (strong, top affinity planet)", "-> Physical & Mechanical
    Systems", "-> Materials & Extractive Engineering", "-> Metallurgical
    Engineering"].
    """
    field_id = result.get("field_id", "")
    domain = result.get("domain", "")
    onto = get_ontology(field_id, domain)
    aff_planets = result.get("affinity_planets", {}) or {}
    top_planet = ""
    if aff_planets:
        top_planet = max(aff_planets.items(), key=lambda kv: kv[1])[0]
    elif result.get("top_affinity_planets"):
        _tap = result["top_affinity_planets"]
        if isinstance(_tap, dict) and _tap:
            top_planet = next(iter(_tap))

    chain: List[str] = []
    if top_planet:
        chain.append(f"{top_planet} (leading karaka)")
    chain.append(f"-> {onto['competency_label']}")
    chain.append(f"-> {onto['career_family_label']}")
    chain.append(f"-> {result.get('field_label', field_id)}")
    niche = (result.get("registry") or {}).get("specialization") or (result.get("registry") or {}).get("niche")
    if niche and niche != result.get("field_label"):
        chain.append(f"-> {niche}")
    return chain


# =============================================================================
# SECTION 7 — CONTRADICTORY EVIDENCE SUMMARY  (G25)
# =============================================================================

def build_evidence_summary(result: Dict[str, Any], top_score: float = None) -> Dict[str, Any]:
    """Summarize supporting vs contradicting planetary evidence for one field.

    Uses the already-computed per-planet contribution and any structural
    penalties already present in the result (gap_breakdown, structural_audit)
    -- no new astrological computation, just a legible +/- rollup (G25).
    """
    contributions: Dict[str, float] = (
        result.get("method_components", {}).get("knrao", {})
        if isinstance(result.get("method_components"), dict) else {}
    ) or {}
    top_planets = result.get("top_affinity_planets", {}) or {}
    supporting = [f"+{p}" for p in list(top_planets.keys())[:3]]

    contradicting: List[str] = []
    gap_breakdown = result.get("gap_breakdown", {}) or {}
    for key, val in gap_breakdown.items():
        try:
            if float(val) < 0:
                contradicting.append(f"-{key}")
        except (TypeError, ValueError):
            continue
    war_losers = result.get("war_losers", []) or []
    contradicting.extend(f"-{p} (planetary war loss)" for p in war_losers)

    # 2026-08 architecture-audit gap-fix (Gap 8): the review's own worked
    # example named "Limited KP authority" and "D24 combustion penalty" as
    # exactly the kind of conflicting-evidence entries a legible audit trail
    # should surface. Both signals already exist on `result` by the time
    # this function runs (score_confidence_note from engine.py's KP-
    # authority gate; confidence_dimensions.educational_fit's combustion
    # note from this session's earlier gap-fix) -- pull them in rather than
    # recomputing anything new. Defensive .get() chains throughout: this
    # function must degrade gracefully (skip the note) if either upstream
    # field isn't present yet, rather than assume a fixed call order.
    score_confidence_note = str(result.get("score_confidence_note", "") or "")
    if "could NOT be independently verified" in score_confidence_note or "little or no authority" in score_confidence_note:
        contradicting.append("-KP (cusp/sub-lord chain not independently verified -- little or no authority weight)")

    conf_dims = result.get("confidence_dimensions", {}) or {}
    edu_basis = ((conf_dims.get("educational_fit") or {}).get("basis") or [])
    for note in edu_basis:
        if isinstance(note, str) and note.startswith("NOTE:") and "combust" in note.lower():
            contradicting.append("-D24 education-signal karaka(s) combust in D1 (chart-wide, not field-specific)")
            break
    timing_basis = ((conf_dims.get("timing_fit") or {}).get("basis") or [])
    for note in timing_basis:
        if isinstance(note, str) and note.startswith("NOTE:") and "not in this field's affinity table" in note:
            contradicting.append("-active dasha lord not in this field's affinity table (generic strength credited instead)")
            break

    return {
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting[:8],
        "final_score": result.get("final_score", 0.0),
        "confidence_band": confidence_band(result.get("final_score", 0.0), top_score),
    }


# =============================================================================
# SECTION 8 — FAMILY AGGREGATION + CLUSTER REPORT  (G15, G16, G26, G29, G30, G31)
# =============================================================================

def compute_family_aggregates(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """For each family present in `results`, compute member list + an
    aggregate 'family_score' using a diminishing-weight top-3 blend so a
    family with several strong siblings scores higher than a family with
    one isolated spike (this is the concrete fix for G16's cannibalization
    complaint — convergence across siblings becomes a visible, additive
    signal instead of just fragmenting the leaderboard).
    """
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        fam = r.get("career_family") or get_family_id(r.get("field_id", ""), r.get("domain", ""))
        by_family.setdefault(fam, []).append(r)

    aggregates: Dict[str, Dict[str, Any]] = {}
    for fam, members in by_family.items():
        members_sorted = sorted(members, key=lambda x: -x.get("final_score", 0.0))
        scores = [m.get("final_score", 0.0) for m in members_sorted]
        weights = [0.55, 0.30, 0.15]
        fam_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights[: len(scores)] or [1.0])
        # GAP-FIX (2026-07-18, audit P1 "cluster formula does not genuinely
        # reward convergence for single-member families"): the weighted
        # average above renormalizes by the weights actually used, so a
        # 1-member family gets scores[0]*0.55/0.55 == scores[0] -- its
        # member's entire raw score, with no discount at all relative to a
        # family with several genuinely-converging strong siblings. That let
        # one isolated field's score beat several jointly-strong siblings in
        # a different family, even though the whole point of this function
        # (per its own docstring above) is that convergence across siblings
        # should be a visible signal. Apply a bounded breadth multiplier so
        # "one lucky field" and "three siblings independently pointing the
        # same direction" are no longer scored identically. Capped at 15%
        # for a true isolated singleton, tapering to no discount at 3+
        # members (already the formula's own natural convergence ceiling --
        # weights only defined for 3 slots).
        _breadth_mult = {1: 0.85, 2: 0.93}.get(len(scores), 1.0)
        fam_score = fam_score * _breadth_mult
        fam_meta = FAMILY_META.get(fam, {"label": fam.replace("_", " ").title(), "competency": "knowledge_scholarship"})
        aggregates[fam] = {
            "family_id": fam,
            "label": fam_meta.get("label", fam),
            "competency": fam_meta.get("competency", ""),
            "competency_label": COMPETENCY_META.get(fam_meta.get("competency", ""), {}).get("label", ""),
            "member_ids": [m.get("field_id") for m in members_sorted],
            "member_count": len(members_sorted),
            "top_member": members_sorted[0].get("field_id") if members_sorted else None,
            "family_score": round(fam_score, 2),
            "demand_tag": demand_tag(fam),
        }
    return aggregates


def apply_family_cohesion_adjustment(
    results: List[Dict[str, Any]],
    max_adjust_pct: float = 0.04,
) -> List[Dict[str, Any]]:
    """Bounded (+/-4% default) adjustment to final_score that rewards fields
    whose career family shows multi-sibling convergence and mildly discounts
    isolated single-field spikes with no family support (G1/G16/G30).

    This mirrors existing bounded-nudge patterns in engine.py (tie-break
    cascade capped at 0.45pts, medical governance 0.90x cap) and is applied
    strictly AFTER the deterministic score + existing tie-break cascade, so
    it changes ordering only at the margins, not headline rankings.
    """
    if not results:
        return results

    aggregates = compute_family_aggregates(results)
    all_scores = [r.get("final_score", 0.0) for r in results]
    score_span = (max(all_scores) - min(all_scores)) or 1.0

    for r in results:
        fam = r.get("career_family") or get_family_id(r.get("field_id", ""), r.get("domain", ""))
        agg = aggregates.get(fam, {})
        sibling_count = max(agg.get("member_count", 1) - 1, 0)
        own_score = r.get("final_score", 0.0)
        fam_score = agg.get("family_score", own_score)

        # Convergence ratio: how close this field's siblings collectively are
        # to this field's own score. >0 means siblings are pulling the family
        # average close to (or above) this field — i.e. real family support.
        convergence = (fam_score - own_score) / score_span

        if sibling_count >= 1 and convergence > -0.05:
            # Family support present: small reward, more siblings -> more reward.
            adj = min(max_adjust_pct, 0.015 * min(sibling_count, 3) + max(convergence, 0) * 0.5)
        elif sibling_count == 0:
            # Genuinely isolated field (no other registry sibling in this run's
            # results at all) — leave untouched; isolation is often just
            # domain-deduplication, not a real red flag.
            adj = 0.0
        else:
            # Has siblings but they scored far below it (an outlier spike) —
            # mild discount, capped.
            adj = max(-max_adjust_pct, convergence * 0.3)

        r["family_cohesion_adjustment_pct"] = round(adj * 100, 2)
        r["final_score"] = round(own_score * (1.0 + adj), 2)

    results.sort(key=lambda x: -x.get("final_score", 0.0))
    return results


def build_cluster_report(
    results: List[Dict[str, Any]],
    top_n_families: int = 6,
    top_n_population: int = 20,
) -> Dict[str, Any]:
    """Build the 'career cluster' summary (G26) + macro career identity (G29).

    Groups the top results into named macro clusters (career families ranked
    by aggregate family_score) instead of a flat top-20 list, and names the
    single dominant competency+family as the chart's macro career identity.

    GAP-FIX (2026-07-18, audit P1 "cluster aggregation population (35 vs
    top-20) inconsistency"): `clusters`/family aggregates used to be
    computed from the FULL `results` list passed in (35 rows at every real
    call site in engine.py), while `macro_identity` was always computed from
    only the top 20 of that same list. A rank 21-35 field could therefore
    change a family's score in a report that markets itself as covering the
    "Top 20" -- the two sections of the same report used two different,
    silently-inconsistent populations. Both sections now derive from the
    same explicit `top_n_population` (default 20) slice.
    """
    if not results:
        return {"clusters": [], "macro_identity": None}

    population = sorted(results, key=lambda r: -r.get("final_score", 0.0))[:top_n_population]

    aggregates = compute_family_aggregates(population)
    ranked_families = sorted(aggregates.values(), key=lambda a: -a["family_score"])[:top_n_families]
    # Scale fix (2026-08-18, tiered-ranking rollout): see confidence_band()'s
    # docstring -- this run's own top family_score/final_score makes the
    # confidence_band() calls below genuinely relative regardless of
    # whichever ranking authority produced final_score.
    _pop_top_score = float(population[0].get("final_score", 0.0) or 0.0) if population else 0.0
    _fam_top_score = float(ranked_families[0]["family_score"]) if ranked_families else 0.0

    result_by_id = {r.get("field_id"): r for r in population}
    clusters = []
    for i, fam in enumerate(ranked_families, 1):
        members = [result_by_id[mid] for mid in fam["member_ids"] if mid in result_by_id]
        clusters.append({
            "cluster_rank": i,
            "career_family": fam["label"],
            "competency": fam["competency_label"],
            "family_score": fam["family_score"],
            "confidence_band": confidence_band(fam["family_score"], _fam_top_score),
            "demand_tag": fam["demand_tag"],
            "members": [
                {
                    "field_id": m.get("field_id"),
                    "field_label": m.get("field_label"),
                    "final_score": m.get("final_score"),
                    "confidence_band": confidence_band(m.get("final_score", 0.0), _pop_top_score),
                }
                for m in members[:6]
            ],
        })

    top_family = ranked_families[0] if ranked_families else None
    macro_identity = None
    top20 = population
    competency_dist: Dict[str, float] = {}
    family_dist: Dict[str, float] = {}
    for idx, r in enumerate(top20):
        rank_weight = max(1.0, 20.0 - idx)
        score_weight = max(0.0, float(r.get("final_score", 0.0) or 0.0)) / 100.0
        w = rank_weight * score_weight
        comp_label = r.get("competency_label") or r.get("competency") or ""
        fam_label = r.get("career_family_label") or r.get("career_family") or ""
        if comp_label:
            competency_dist[comp_label] = competency_dist.get(comp_label, 0.0) + w
        if fam_label:
            family_dist[fam_label] = family_dist.get(fam_label, 0.0) + w

    ranked_competencies = sorted(competency_dist.items(), key=lambda kv: -kv[1])
    ranked_family_labels = sorted(family_dist.items(), key=lambda kv: -kv[1])

    if top_family:
        identity_comp = ranked_competencies[0][0] if ranked_competencies else top_family["competency_label"]
        identity_family = ranked_family_labels[0][0] if ranked_family_labels else top_family["label"]
        # GAP-FIX (2026-07-18, audit "Contradictory macro identity"): anchor_field
        # and family_score used to come unconditionally from top_family (the #1
        # family by raw family_score), while career_family came from
        # ranked_family_labels[0] -- a *different* ranking (top-20 rank+score
        # weighted distribution). Those two rankings can disagree, which
        # produced statements naming one family as the identity while quoting
        # another family's anchor field and score. Resolve anchor_field and
        # family_score from the aggregate that actually matches the declared
        # identity_family so the three are never contradictory. Falls back to
        # top_family only if no aggregate's label matches (should not happen
        # since identity_family is itself drawn from a family present in
        # `aggregates` whenever ranked_family_labels is non-empty).
        identity_agg = next(
            (agg for agg in aggregates.values() if agg["label"] == identity_family),
            top_family,
        )
        anchor_field = (
            result_by_id.get(identity_agg["top_member"])
            if identity_agg.get("top_member") else None
        )
        secondary = [c for c, _ in ranked_competencies[1:3]]
        identity_phrase = identity_comp
        if secondary:
            identity_phrase += " with secondary strength in " + ", ".join(secondary)
        macro_identity = {
            "statement": (
                f"This chart's dominant career identity is fundamentally shaped by "
                f"{identity_phrase}, expressed most strongly through "
                f"{identity_family}"
                + (f", most concretely as {anchor_field.get('field_label')}" if anchor_field else "")
                + ". This identity is derived from the full top-20 distribution, "
                  "so repeated law/governance, research, economics, and public-welfare "
                  "signals can outweigh a single over-amplified field family."
            ),
            "competency": identity_comp,
            "career_family": identity_family,
            "anchor_field": anchor_field.get("field_label") if anchor_field else None,
            "family_score": identity_agg["family_score"],
            "competency_distribution": {k: round(v, 2) for k, v in ranked_competencies[:5]},
            "family_distribution": {k: round(v, 2) for k, v in ranked_family_labels[:5]},
        }

    return {"clusters": clusters, "macro_identity": macro_identity}


# =============================================================================
# SECTION 9 — G22: YOGA-AWARE COMPETENCY FRAMING
# =============================================================================
# 2026-07-04 ontology audit follow-up. Previously deferred because it needs
# yogas are driving a given competency), not just grouping/display. Reuses
# `_detect_yogas()` (astro.py, via payload.detected_yogas) — does not
# re-derive yogas. Bounded, additive adjustment only (same pattern as the
# G1/G16/G30 family-cohesion nudge): capped so it can shift ranking only at
# the margins, never override the deterministic astrology score.

# Static (non-parametrized) yoga -> planet-set map.
_YOGA_STATIC_PLANETS: Dict[str, Tuple[str, ...]] = {
    "Saraswati":      ("Mercury", "Jupiter", "Venus"),
    "GajaKesari":     ("Moon", "Jupiter"),
    "BudhaAditya":    ("Sun", "Mercury"),
    "Shasha":         ("Saturn",),
    "Hamsa":          ("Jupiter",),
    "Ruchaka":        ("Mars",),
    "Bhadra":         ("Mercury",),
    "Malavya":        ("Venus",),
    "ChandraMangala": ("Moon", "Mars"),
}
# Human-readable labels / one-line classical descriptions for framing text.
_YOGA_LABELS: Dict[str, str] = {
    "Saraswati":      "Saraswati Yoga (Mercury-Jupiter-Venus in kendras/trikonas — scholarship & fine skill)",
    "GajaKesari":     "Gajakesari Yoga (Moon-Jupiter mutual reinforcement — breadth of judgment)",
    "BudhaAditya":    "Budha-Aditya Yoga (Sun-Mercury conjunction — sharp, articulate intellect)",
    "Shasha":         "Shasha Mahapurusha Yoga (Saturn exalted/own in a kendra — disciplined authority)",
    "Hamsa":          "Hamsa Mahapurusha Yoga (Jupiter exalted/own in a kendra — wisdom & teaching)",
    "Ruchaka":        "Ruchaka Mahapurusha Yoga (Mars exalted/own in a kendra — command & execution)",
    "Bhadra":         "Bhadra Mahapurusha Yoga (Mercury exalted/own in a kendra — precision & analysis)",
    "Malavya":        "Malavya Mahapurusha Yoga (Venus exalted/own in a kendra — aesthetic mastery)",
    "ChandraMangala": "Chandra-Mangala Yoga (Moon-Mars combination — driven, enterprising energy)",
}
_MAJOR_YOGA_BONUS_PCT = 0.05   # Mahapurusha / Gajakesari / Saraswati / RajaYoga / DhanaYoga
_MINOR_YOGA_BONUS_PCT = 0.02   # Parivartana / NakParivartana / Amala / ChandraMangala


def _yoga_planets(yoga_name: str) -> Tuple[str, ...]:
    """Return the planet(s) a detected_yogas entry is actually about,
    covering both static names (Ruchaka, GajaKesari, ...) and the
    dynamically-named ones astro.py emits (Parivartana_Mars_Saturn,
    RajaYoga_Sun_Jupiter, Amala_Venus, NakParivartana_Moon_Mercury,
    DhanaYoga_Mercury_Venus, DhanaYogaParivartana_Mercury_Venus).

    Fix (2026-08-20): DhanaYoga_/DhanaYogaParivartana_ (astro.py's 2nd/11th
    -lord wealth-yoga family, added 2026-08-17 specifically for career/
    wealth support) were never added to this prefix list when they were
    introduced, so they always fell through to the `return ()` below --
    zero planet overlap with any competency, zero yoga_alignment_bonus_pct,
    forever, for the entire yoga family. Added here so they get the same
    bounded alignment nudge every other dynamically-named yoga already gets.
    """
    if yoga_name in _YOGA_STATIC_PLANETS:
        return _YOGA_STATIC_PLANETS[yoga_name]
    for prefix in ("Parivartana_", "NakParivartana_", "RajaYoga_",
                   "DhanaYogaParivartana_", "DhanaYoga_"):
        if yoga_name.startswith(prefix):
            return tuple(yoga_name[len(prefix):].split("_"))
    if yoga_name.startswith("Amala_"):
        # Afflicted/partial variant: "Amala_<planet>_Partial_<afflictor(s)>"
        # (2026-07-05 gap fix, engine_io.py's _relabel_afflicted_amala) — the
        # benefic is still the first token after "Amala_", before "_Partial_".
        _rest = yoga_name[len("Amala_"):]
        if "_Partial_" in _rest:
            _rest = _rest.split("_Partial_", 1)[0]
        return (_rest,)
    return ()


def _yoga_label(yoga_name: str) -> str:
    if yoga_name in _YOGA_LABELS:
        return _YOGA_LABELS[yoga_name]
    if yoga_name.startswith("Parivartana_"):
        p1, p2 = (yoga_name[len("Parivartana_"):].split("_") + ["", ""])[:2]
        return f"Parivartana (Rasi exchange) Yoga between {p1} and {p2}"
    if yoga_name.startswith("NakParivartana_"):
        p1, p2 = (yoga_name[len("NakParivartana_"):].split("_") + ["", ""])[:2]
        return f"Nakshatra-lord exchange between {p1} and {p2} (KP star-level reinforcement)"
    if yoga_name.startswith("RajaYoga_"):
        p1, p2 = (yoga_name[len("RajaYoga_"):].split("_") + ["", ""])[:2]
        return f"Raja Yoga ({p1}-{p2} kendra-trikona lord conjunction — status & authority)"
    if yoga_name.startswith("DhanaYogaParivartana_"):
        p1, p2 = (yoga_name[len("DhanaYogaParivartana_"):].split("_") + ["", ""])[:2]
        return f"Dhana Yoga Parivartana ({p1}-{p2} 2nd/11th-lord sign exchange — wealth-career mutual reinforcement)"
    if yoga_name.startswith("DhanaYoga_"):
        p1, p2 = (yoga_name[len("DhanaYoga_"):].split("_") + ["", ""])[:2]
        return f"Dhana Yoga ({p1}-{p2} wealth-lord conjunction — material support for career results)"
    if yoga_name.startswith("Amala_"):
        _rest = yoga_name[len("Amala_"):]
        if "_Partial_" in _rest:
            p, _afflictor_tail = _rest.split("_Partial_", 1)
            _afflictors = _afflictor_tail.replace("_", ", ")
            return (
                f"Amala Yoga ({p} in the 10th, partial — conjunct {_afflictors}, conditional): "
                f"the classical unblemished-reputation result is qualified, not fully unafflicted"
            )
        p = _rest
        return f"Amala Yoga ({p} unafflicted in/aspecting the 10th — spotless professional reputation)"
    return yoga_name


def _is_major_yoga(yoga_name: str) -> bool:
    return (
        yoga_name in ("Saraswati", "GajaKesari", "Shasha", "Hamsa", "Ruchaka", "Bhadra", "Malavya")
        or yoga_name.startswith("RajaYoga_")
        # Fix (2026-08-20): Dhana Yoga (2nd/11th/10th/9th wealth-lord family)
        # is a career-support yoga of comparable classical significance to
        # Raja Yoga -- previously it wasn't even reachable here (see
        # _yoga_planets' fix note above), so this tier assignment was moot;
        # now that it can match, treat it as major rather than defaulting to
        # the minor tier.
        or yoga_name.startswith("DhanaYoga_")
        or yoga_name.startswith("DhanaYogaParivartana_")
    )


def build_yoga_aware_framing(result: Dict[str, Any], detected_yogas: List[str]) -> Dict[str, Any]:
    """G22: identify which of the native's actual detected_yogas reinforce
    this result's competency, and produce a bounded alignment signal +
    human-readable framing sentence. Returns a dict with:
        matched_yogas          : list of {yoga, label, planets, tier}
        yoga_alignment_bonus_pct: float (already capped, 0 if no match)
        framing_sentence        : str
    """
    competency = result.get("competency", "")
    comp_planets = set(COMPETENCY_META.get(competency, {}).get("planets", []))
    matches: List[Dict[str, Any]] = []
    bonus = 0.0

    for yoga in detected_yogas or []:
        yp = set(_yoga_planets(yoga))
        overlap = yp & comp_planets
        if not overlap:
            continue
        major = _is_major_yoga(yoga)
        matches.append({
            "yoga": yoga,
            "label": _yoga_label(yoga),
            "planets": sorted(overlap),
            "tier": "major" if major else "minor",
        })
        bonus += _MAJOR_YOGA_BONUS_PCT if major else _MINOR_YOGA_BONUS_PCT

    bonus = min(bonus, _MAJOR_YOGA_BONUS_PCT)  # single hard cap regardless of match count

    if matches:
        lead = matches[0]
        framing = (
            f"This chart's {lead['label']} directly reinforces the "
            f"{COMPETENCY_META.get(competency, {}).get('label', competency)} competency "
            f"through {', '.join(lead['planets'])}."
        )
        if len(matches) > 1:
            framing += f" ({len(matches) - 1} additional supporting yoga(s) also matched.)"
    else:
        framing = (
            f"No specific classical yoga in this chart directly names the "
            f"{COMPETENCY_META.get(competency, {}).get('label', competency)} competency's "
            f"planets — this result rests on the base astrological score alone."
        )

    return {
        "matched_yogas": matches,
        "yoga_alignment_bonus_pct": round(bonus * 100, 2),
        "framing_sentence": framing,
    }


_ARCHETYPE_ALIGN_BONUS_PCT = 0.05    # matches yoga-alignment's own +5% cap
_ARCHETYPE_MISALIGN_PENALTY_PCT = 0.05  # symmetric, same magnitude as the bonus


def apply_archetype_alignment_adjustment(
    results: List[Dict[str, Any]],
    max_adjust_pct: float = _ARCHETYPE_ALIGN_BONUS_PCT,
) -> List[Dict[str, Any]]:
    """2026-08 architecture-audit gap-fix (Gap 1): bounded (+/-5%, hard-capped)
    score nudge based on whether a field's domain is covered by the chart's
    own dominant career archetype (career_archetype.py, Stage 3 -- discovered
    from D1 planetary strength + house concentration, chart-level not
    field-level).

    This is the "soft re-rank" version of the review's Gap-1 recommendation
    ("add an explicit Career Archetype Layer before field scoring"), NOT a
    hard gate. career_archetype.py's own module docstring explicitly
    rejected letting the (unvalidated, no labeled benchmark) 8-archetype
    classification REPLACE or filter the 205-field affinity table that has
    been validated end-to-end across 25 real charts -- that risk assessment
    still holds. What changes here is that the archetype layer stops being
    purely descriptive and starts exerting a small, bounded, transparent
    influence on ranking, using the exact same bounded-nudge convention
    already proven safe by apply_family_cohesion_adjustment (+/-4%) and
    apply_yoga_alignment_adjustment (+0-5%) just above -- capped so it can
    only move rankings at the margin, never substitute for or dominate the
    deterministic 9-method astrology blend.

    Rule (symmetric, deterministic, no new astrology):
      - field's `domain` in top_archetype's `domains` list        -> +5%
      - field's `domain` in runner-up (top_2[1]) archetype's list  -> +2.5%
      - field's `domain` in NEITHER of the top-2 archetypes' lists
        AND the chart's archetype pick is CLEAR/LEANING (not BLENDED,
        i.e. the chart has a genuinely dominant archetype, this isn't a
        coin-flip call) -> -5%
      - otherwise (BLENDED chart, or domain matches nothing meaningfully) -> 0%
    """
    if not results:
        return results

    for r in results:
        archetype = r.get("career_archetype") or {}
        top_2 = archetype.get("top_2_archetypes") or []
        distinctness = archetype.get("distinctness", "")
        field_domain = r.get("domain", "")

        adj = 0.0
        note = ""
        if top_2 and field_domain and field_domain in (top_2[0].get("domains") or []):
            adj = max_adjust_pct
            note = f"domain '{field_domain}' matches dominant archetype " \
                   f"'{top_2[0].get('label','')}' (+{adj*100:.1f}%)"
        elif len(top_2) > 1 and field_domain and field_domain in (top_2[1].get("domains") or []):
            adj = max_adjust_pct * 0.5
            note = f"domain '{field_domain}' matches runner-up archetype " \
                   f"'{top_2[1].get('label','')}' (+{adj*100:.1f}%)"
        elif (
            top_2 and field_domain and distinctness in ("CLEAR", "LEANING")
            and field_domain not in (top_2[0].get("domains") or [])
            and field_domain not in ((top_2[1].get("domains") if len(top_2) > 1 else []) or [])
        ):
            adj = -_ARCHETYPE_MISALIGN_PENALTY_PCT
            note = f"domain '{field_domain}' outside this chart's dominant/runner-up " \
                   f"archetype domains ({adj*100:.1f}%)"

        if adj:
            r["final_score"] = round(r.get("final_score", 0.0) * (1.0 + adj), 2)
        r["archetype_alignment_adjustment_pct"] = round(adj, 4)
        r["archetype_alignment_note"] = note

    results.sort(key=lambda x: -x.get("final_score", 0.0))
    return results


# =============================================================================
# SECTION 8b — GAP 6: ARCHETYPE-FIRST HIERARCHICAL VIEW
# =============================================================================

def build_archetype_hierarchy(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """2026-08 architecture-audit gap-fix (Gap 6): a derived, read-only
    Career Archetype -> Industry/Domain -> Career Family -> Field hierarchy
    for explainability, built purely by regrouping the existing 205-field
    flat results -- NOT a registry rewrite. The review's own recommendation
    ("organize hierarchically ... improves explainability and reduces
    overfitting to narrowly defined fields") is about presentation/framing;
    physically re-indexing india_course_registry_v12.json (205 hand-curated
    field records, each independently validated) around an 8-archetype
    ontology would be a genuine, high-risk data-migration project with no
    established benchmark for whether the archetype boundaries are even
    correct -- exactly the same risk career_archetype.py's own docstring
    already flagged for Gap 1. This function gets the explainability benefit
    without that risk: every field keeps its existing field_id/domain/
    career_family, this just adds one more read-only view over the same data.
    """
    if not results:
        return {"archetypes": {}}

    archetype = (results[0].get("career_archetype") or {})
    all_archetypes = archetype.get("all_archetypes") or {}

    domain_to_archetypes: Dict[str, List[str]] = {}
    for name, entry in all_archetypes.items():
        for d in entry.get("domains", []):
            domain_to_archetypes.setdefault(d, []).append(name)

    hierarchy: Dict[str, Any] = {
        name: {
            "label": entry.get("label", name),
            "match_score": entry.get("match_score", 0.0),
            "description": entry.get("description", ""),
            "industries": {},
        }
        for name, entry in all_archetypes.items()
    }
    unmapped: List[Dict[str, Any]] = []

    for r in results:
        domain = r.get("domain", "")
        matches = domain_to_archetypes.get(domain, [])
        if not matches:
            unmapped.append({
                "field_id": r.get("field_id", ""),
                "field_label": r.get("field_label", ""),
                "domain": domain,
            })
            continue
        for arch_name in matches:
            industry_bucket = hierarchy[arch_name]["industries"].setdefault(domain, {
                "career_families": {},
            })
            fam = r.get("career_family") or "unclassified"
            fam_bucket = industry_bucket["career_families"].setdefault(fam, {
                "label": r.get("career_family_label", fam),
                "fields": [],
            })
            fam_bucket["fields"].append({
                "field_id": r.get("field_id", ""),
                "field_label": r.get("field_label", ""),
                "final_score": r.get("final_score", 0.0),
            })

    for arch in hierarchy.values():
        for industry in arch["industries"].values():
            for fam in industry["career_families"].values():
                fam["fields"].sort(key=lambda f: -f.get("final_score", 0.0))

    return {
        "contract_version": "archetype-hierarchy.v1",
        "dominant_archetype": archetype.get("top_archetype", {}).get("name", ""),
        "archetypes": hierarchy,
        "unmapped_domains": sorted({u["domain"] for u in unmapped}),
        "unmapped_field_count": len(unmapped),
    }


def apply_yoga_alignment_adjustment(
    results: List[Dict[str, Any]],
    detected_yogas: List[str],
    max_adjust_pct: float = _MAJOR_YOGA_BONUS_PCT,
) -> List[Dict[str, Any]]:
    """Bounded (+0-5% default, hard-capped) score nudge for results whose
    competency is directly reinforced by one of the chart's own detected
    yogas. Applied AFTER the family-cohesion adjustment, same bounded-nudge
    philosophy as engine.py's tie-break cascade / medical governance cap —
    this can only move rankings at the margin, never substitute for the
    deterministic astrology score.

    AUDIT NOTE + FIX (2026-08-22): `results[i]["final_score"]` entering this
    function already reflects `jyotish/boosts.py::_yoga_bonus`, which folds a
    domain-matched bonus for these SAME classical yogas (GajaKesari, Ruchaka,
    Shasha, Malavya, Bhadra, Hamsa, Saraswati, BudhaAditya, etc. via
    `_YOGA_DOMAIN_KW`) directly into final_score during the base engine pass.
    This function re-matches the same `detected_yogas` against the field's
    competency planet-set (a coarser generalization of the same domains) and
    was applying a further bonus on top with no awareness the fact had
    already been counted once. Rather than drop this signal (competency-level
    matching is a genuinely distinct, coarser lens worth keeping), the
    resulting adjustment is halved -- the same correlation-discount pattern
    used throughout this audit pass -- so the double-counted portion is
    reduced rather than fully doubled.
    """
    if not results or not detected_yogas:
        for r in results:
            r["yoga_framing"] = build_yoga_aware_framing(r, [])
        return results

    for r in results:
        framing = build_yoga_aware_framing(r, detected_yogas)
        r["yoga_framing"] = framing
        adj = min(framing["yoga_alignment_bonus_pct"] / 100.0, max_adjust_pct)
        adj *= 0.5  # correlation discount: already partially counted via boosts.py::_yoga_bonus
        if adj > 0:
            r["final_score"] = round(r.get("final_score", 0.0) * (1.0 + adj), 2)

    results.sort(key=lambda x: -x.get("final_score", 0.0))
    return results


# =============================================================================
# SECTION 10 — G27: APTITUDE EXPLANATION
# =============================================================================
# 2026-07-04 ontology audit follow-up. Distinct from G23's explanation_chain
# (a karaka -> competency -> family -> field *lineage*): this is a genuine
# cognitive/aptitude-style narrative — what KIND of thinking a field draws
# on, translated from the same per-field top_affinity_planets that already
# exist on every result (no new astrological computation, new *signal
# framing* only).

_PLANET_APTITUDE: Dict[str, Dict[str, float]] = {
    "Sun":     {"leadership": 1.0, "decisiveness": 0.8, "authority": 0.7},
    "Moon":    {"intuitive": 1.0, "adaptive": 0.8, "empathetic": 0.7},
    "Mars":    {"kinesthetic": 1.0, "action_oriented": 0.9, "competitive": 0.7},
    "Mercury": {"analytical": 1.0, "verbal_logical": 0.9, "quick_processing": 0.8},
    "Jupiter": {"conceptual": 1.0, "big_picture": 0.9, "mentoring": 0.7},
    "Venus":   {"aesthetic": 1.0, "relational": 0.8, "design_sense": 0.8},
    "Saturn":  {"methodical": 1.0, "disciplined": 0.9, "long_horizon": 0.8},
    "Rahu":    {"unconventional": 1.0, "ambitious": 0.8, "novelty_seeking": 0.9},
    "Ketu":    {"focused_specialist": 1.0, "detached": 0.7, "research_oriented": 0.9},
}

_APTITUDE_DIM_LABEL: Dict[str, str] = {
    "leadership": "leadership", "decisiveness": "decisiveness", "authority": "command presence",
    "intuitive": "intuitive judgment", "adaptive": "adaptability", "empathetic": "people-sensitivity",
    "kinesthetic": "hands-on/kinesthetic", "action_oriented": "action-orientation", "competitive": "competitive drive",
    "analytical": "analytical reasoning", "verbal_logical": "verbal/logical precision", "quick_processing": "fast processing",
    "conceptual": "conceptual/big-picture thinking", "big_picture": "big-picture synthesis", "mentoring": "mentoring instinct",
    "aesthetic": "aesthetic sensibility", "relational": "relational instinct", "design_sense": "design sense",
    "methodical": "methodical discipline", "disciplined": "sustained discipline", "long_horizon": "long-horizon patience",
    "unconventional": "unconventional thinking", "ambitious": "ambition", "novelty_seeking": "novelty-seeking",
    "focused_specialist": "deep-focus specialism", "detached": "detached objectivity", "research_oriented": "research orientation",
}


def build_aptitude_explanation(result: Dict[str, Any]) -> Dict[str, Any]:
    """G27: translate a result's top affinity planets into an aptitude-style
    narrative distinct from the G23 karaka explanation chain.

    Returns dict: aptitude_dimensions (0-1 normalized), top_aptitude_traits
    (top 3 labels), aptitude_narrative (str).
    """
    top_planets: Dict[str, float] = result.get("affinity_planets") or result.get("top_affinity_planets") or {}
    if not top_planets:
        return {
            "aptitude_dimensions": {},
            "top_aptitude_traits": [],
            "aptitude_narrative": "Insufficient planetary-contribution data to build an aptitude profile.",
        }

    total_w = sum(top_planets.values()) or 1.0
    dims: Dict[str, float] = {}
    for planet, weight in top_planets.items():
        for dim, val in _PLANET_APTITUDE.get(planet, {}).items():
            dims[dim] = dims.get(dim, 0.0) + val * (weight / total_w)

    if dims:
        top_val = max(dims.values()) or 1.0
        dims = {k: round(v / top_val, 3) for k, v in dims.items()}

    ranked = sorted(dims.items(), key=lambda kv: -kv[1])[:3]
    top_traits = [_APTITUDE_DIM_LABEL.get(d, d) for d, _ in ranked]

    if top_traits:
        narrative = (
            f"This field draws primarily on {top_traits[0]}"
            + (f", supported by {top_traits[1]}" if len(top_traits) > 1 else "")
            + (f" and {top_traits[2]}" if len(top_traits) > 2 else "")
            + "."
        )
    else:
        narrative = "No clear aptitude signature could be derived from this field's planetary contributions."

    return {
        "aptitude_dimensions": dims,
        "top_aptitude_traits": top_traits,
        "aptitude_narrative": narrative,
    }


# =============================================================================
# SECTION 11 — G28: LIFE-STAGE COMPETENCY EVOLUTION
# =============================================================================
# 2026-07-04 ontology audit follow-up. Reuses the dasha sequence already
# computed elsewhere (payload.dasha_sequence, as consumed by
# timeline.py/_peak_career_dasha in engine.py) — does NOT recompute dasha
# timing. Purely a re-framing: for each Mahadasha period, which competencies
# (by their existing planetary signature in COMPETENCY_META) does that
# period's lord emphasize.

# Standard 120-year Vimshottari dasha cycle, per-lord duration in years.
# Same values as jyotish/kp_audit.py's YEARS table; duplicated here (rather
# than imported) to keep this ontology module free of a dependency on the
# KP-cusp-audit module for an unrelated purpose.
_VIMSHOTTARI_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}


def compute_life_stage_competency_evolution(
    dasha_sequence: List[Dict[str, Any]],
    current_age: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """G28: map each Mahadasha period to the competencies its lord
    emphasizes, producing a life-stage timeline.

    Args:
        dasha_sequence: list of {lord|md_planet, start_age|start, end_age|end}
        current_age: if given, flags the currently-active stage.

    Returns: list of stage dicts, chronological, each with dasha_lord,
        start_age, end_age, emphasized_competencies (labels), is_current.
    """
    stages: List[Dict[str, Any]] = []
    for d in dasha_sequence or []:
        lord = d.get("lord") or d.get("md_planet") or ""
        if not lord:
            continue
        try:
            start_age = float(d.get("start_age", d.get("start", 0)) or 0)
        except (TypeError, ValueError):
            start_age = 0.0
        _end_raw = d.get("end_age", d.get("end"))
        if _end_raw is None:
            # GAP-FIX (2026-07-18, audit P2 "invalid terminal age"): the last
            # dasha in a sequence is often open-ended (no recorded end_age --
            # a lifetime rarely spans a full Vimshottari cycle from birth).
            # `float(None or 0)` silently turned that missing value into
            # 0.0, producing a stage that displayed as starting at e.g. 109.9
            # and ending at 0.0. Fall back to this lord's own full
            # Vimshottari dasha span (the standard 120-year cycle's per-lord
            # duration table, same values used in jyotish/kp_audit.py) added
            # to start_age, which is a defensible estimate rather than a
            # nonsensical negative-duration stage.
            end_age = start_age + _VIMSHOTTARI_YEARS.get(lord, 20.0)
        else:
            try:
                end_age = float(_end_raw)
            except (TypeError, ValueError):
                end_age = start_age + _VIMSHOTTARI_YEARS.get(lord, 20.0)

        # Prefer competencies where this lord is the PRIMARY (first-listed)
        # planet — with ~15 competencies sharing a 9-planet palette, most
        # planets appear in several planet lists as a secondary contributor;
        # without this preference the emphasis list balloons to 6-9
        # competencies per stage and says nothing distinctive. Fall back to
        # secondary matches (capped) only if the lord is nobody's primary.
        primary_ids = [cid for cid, meta in COMPETENCY_META.items() if (meta.get("planets") or [None])[0] == lord]
        if primary_ids:
            emphasized_ids = primary_ids
        else:
            emphasized_ids = [cid for cid, meta in COMPETENCY_META.items() if lord in meta.get("planets", [])][:3]
        is_current = current_age is not None and start_age <= float(current_age) < end_age

        stages.append({
            "dasha_lord": lord,
            "start_age": start_age,
            "end_age": end_age,
            "emphasized_competency_ids": emphasized_ids,
            "emphasized_competencies": [COMPETENCY_META[c]["label"] for c in emphasized_ids],
            "is_current": is_current,
        })

    stages.sort(key=lambda s: s["start_age"])
    return stages


def build_life_stage_narrative(stages: List[Dict[str, Any]], current_age: Optional[float] = None) -> str:
    """G28: human-readable summary of the life-stage competency arc —
    what's emphasized now, and what shifts next."""
    if not stages:
        return "No dasha sequence available to build a life-stage competency arc."

    current = next((s for s in stages if s.get("is_current")), None)
    parts: List[str] = []
    if current and current["emphasized_competencies"]:
        parts.append(
            f"Current life stage ({current['dasha_lord']} Mahadasha, age "
            f"{round(current['start_age'])}-{round(current['end_age'])}) emphasizes "
            f"{', '.join(current['emphasized_competencies'])}."
        )
    elif current:
        parts.append(
            f"Current life stage ({current['dasha_lord']} Mahadasha, age "
            f"{round(current['start_age'])}-{round(current['end_age'])}) does not map to "
            f"a distinct competency emphasis in this taxonomy."
        )

    if current_age is not None:
        upcoming = [s for s in stages if s["start_age"] > float(current_age) and s["emphasized_competencies"]]
        if upcoming:
            nxt = upcoming[0]
            parts.append(
                f"Next shift: {nxt['dasha_lord']} Mahadasha from age {round(nxt['start_age'])} "
                f"brings emphasis toward {', '.join(nxt['emphasized_competencies'])}."
            )

    if not parts:
        parts.append(
            "Dasha sequence available, but no stage in range maps cleanly to a "
            "single dominant competency emphasis."
        )
    return " ".join(parts)


# =============================================================================
# SECTION 12 — G31: CROSS-CHART NORMALIZATION (proxy calibration)
# =============================================================================
# 2026-07-04 ontology audit follow-up. A true calibration needs an
# expert-labeled multi-chart corpus, which does not exist. As an explicitly
# caveated PROXY, this uses the empirical distribution of the engine's own
# family_score output across the 500-scenario stress-test corpus already in
# the repo (stress_audit_500/top20_by_scenario.json) — see
# jyotish/data/family_score_reference_2026-07.json (generated once from
# that corpus via compute_family_aggregates, not hand-labeled). This gives
# a genuine *relative* cross-chart position ("this family_score is in the
# 85th percentile of what this engine typically outputs for this family"),
# not a validated absolute-accuracy calibration.

_FAMILY_SCORE_REFERENCE_PATH = os.path.join(
    os.path.dirname(__file__), "data", "family_score_reference_2026-07.json"
)
_family_score_reference_cache: Optional[Dict[str, Any]] = None


def _load_family_score_reference() -> Dict[str, Any]:
    global _family_score_reference_cache
    if _family_score_reference_cache is not None:
        return _family_score_reference_cache
    try:
        with open(_FAMILY_SCORE_REFERENCE_PATH, "r", encoding="utf-8") as f:
            _family_score_reference_cache = json.load(f)
    except FileNotFoundError as exc:
        # This reference file is an optional, explicitly-caveated PROXY
        # calibration artifact (see SECTION 12 docstring above) generated
        # once from a 500-scenario stress-test corpus. Most deployments of
        # this codebase (this one included) do not ship that corpus or a
        # pre-generated reference file, so its absence is an expected,
        # already-safe degraded mode, not a defect: normalize_family_score_cross_chart()
        # returns cross_chart_percentile=None / band="insufficient_reference_data"
        # for every family when the reference is empty, so no field's score
        # or ranking is affected -- only the optional cross-chart-percentile
        # annotation is unavailable. Logged at INFO (once, cached) rather
        # than WARNING so it doesn't read as an actionable error.
        _logger.info(
            "competency_ontology._load_family_score_reference: no reference "
            "file at %s -- this deployment has not generated the optional "
            "500-scenario cross-chart percentile corpus, so cross-chart "
            "percentile annotations will be omitted (scores/ranks are "
            "unaffected). To enable this feature, generate the corpus and "
            "run compute_family_aggregates() to produce this file.",
            _FAMILY_SCORE_REFERENCE_PATH,
        )
        _family_score_reference_cache = {"families": {}, "meta": {}}
    except Exception as exc:
        # A file that DOES exist but fails to parse is a real bug (corrupted
        # or malformed JSON), not an expected missing-corpus case -- keep
        # this loud.
        _logger.warning(
            "competency_ontology._load_family_score_reference: failed to "
            "load %s (%s); percentile interpolation will use an empty "
            "reference (all family percentiles unavailable).",
            _FAMILY_SCORE_REFERENCE_PATH, exc,
        )
        _family_score_reference_cache = {"families": {}, "meta": {}}
    return _family_score_reference_cache


def _interp_percentile(score: float, fam_ref: Dict[str, float]) -> float:
    points = [
        (fam_ref["min"], 0.0), (fam_ref["p10"], 10.0), (fam_ref["p25"], 25.0),
        (fam_ref["p50"], 50.0), (fam_ref["p75"], 75.0), (fam_ref["p90"], 90.0),
        (fam_ref["max"], 100.0),
    ]
    if score <= points[0][0]:
        return 0.0
    if score >= points[-1][0]:
        return 100.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= score <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (score - x0) / (x1 - x0)
    return 50.0


def normalize_family_score_cross_chart(family_id: str, family_score: float) -> Dict[str, Any]:
    """G31: map a family_score to its percentile position within the
    500-scenario proxy reference corpus for that family.

    Returns dict: cross_chart_percentile (0-100 or None), cross_chart_band,
    reference_n, reference_mean, is_proxy_calibration=True.
    """
    ref = _load_family_score_reference()
    fam_ref = ref.get("families", {}).get(family_id)
    if not fam_ref or fam_ref.get("n", 0) < 5:
        return {
            "cross_chart_percentile": None,
            "cross_chart_band": "insufficient_reference_data",
            "reference_n": fam_ref.get("n", 0) if fam_ref else 0,
            "reference_mean": None,
            "is_proxy_calibration": True,
        }

    pct = _interp_percentile(family_score, fam_ref)
    band = (
        "Exceptional" if pct >= 90 else
        "Strong" if pct >= 75 else
        "Typical" if pct >= 25 else
        "Below-typical"
    )
    return {
        "cross_chart_percentile": round(pct, 1),
        "cross_chart_band": band,
        "reference_n": fam_ref["n"],
        "reference_mean": fam_ref["mean"],
        "is_proxy_calibration": True,
    }


# =============================================================================
# SECTION 13 — MAIN INTEGRATION ENTRY POINT
# =============================================================================

def apply_competency_ontology_layer(
    results: List[Dict[str, Any]],
    enable_cohesion_adjustment: bool = True,
    detected_yogas: Optional[List[str]] = None,
    dasha_sequence: Optional[List[Dict[str, Any]]] = None,
    current_age: Optional[float] = None,
    enable_yoga_framing: bool = True,
    enable_cross_chart_norm: bool = True,
    enable_archetype_alignment: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Single entry point called by engine.py right after the deterministic
    score + tie-break cascade are finalized.

    1. Attaches competency/career_family metadata + explanation chain +
       confidence band + evidence summary to every result (G1-G14, G23-G25).
    2. Optionally applies the bounded family-cohesion adjustment (G1/G16/G30).
    3. Optionally applies the bounded yoga-alignment adjustment + framing
       sentence, using the chart's actual detected_yogas (G22).
    4. Attaches the G27 aptitude explanation to every result.
    5. Builds and returns the cluster report + macro career identity
       (G26/G29), attached to every row under `_cluster_report`, and
       attaches G31's cross-chart percentile to each family in that report.
    6. If dasha_sequence is provided, builds the G28 life-stage competency
       evolution + narrative and returns it in the cluster report under
       `life_stage_evolution` (chart-level, not per-field).
    """
    for r in results:
        onto = get_ontology(r.get("field_id", ""), r.get("domain", ""))
        r["competency"] = onto["competency"]
        r["competency_label"] = onto["competency_label"]
        r["career_family"] = onto["career_family"]
        r["career_family_label"] = onto["career_family_label"]

    # AUDIT NOTE (2026-08-22): each of the three bounded nudges below
    # (family-cohesion +/-4%, yoga-alignment +0-5%, archetype-alignment
    # +/-5%) is individually capped and individually documented as "safe" --
    # but chained multiplicatively with no combined check, their worst-case
    # stack is roughly 1.04*1.05*1.05 ~= +14.7% (or symmetric negative
    # combinations down to roughly -8.8%), well beyond what any single
    # docstring promises as "the margin." Snapshot final_score before the
    # cascade so a combined cap can be enforced once, after all three have
    # run, rather than trusting each one's individual bound to compose safely.
    _pre_cascade_scores = {
        r.get("field_id", i): float(r.get("final_score", 0.0) or 0.0)
        for i, r in enumerate(results)
    }

    if enable_cohesion_adjustment:
        results = apply_family_cohesion_adjustment(results)

    if enable_yoga_framing:
        results = apply_yoga_alignment_adjustment(results, detected_yogas or [])

    # 2026-08 architecture-audit gap-fix (Gap 1): bounded archetype-alignment
    # nudge, applied last in the adjustment cascade (same ordering convention
    # -- each bounded adjustment sees the already-adjusted score from the
    # previous one, exactly like cohesion -> yoga above), so it's a small
    # correction on top of everything else rather than compounding blindly.
    if enable_archetype_alignment:
        results = apply_archetype_alignment_adjustment(results)

    # AUDIT FIX (2026-08-22): enforce the combined cap the comment above
    # promises but the individual per-function bounds don't actually
    # guarantee once chained. Clamp the NET multiplicative change across all
    # three nudges to +/-10% of the pre-cascade final_score (tighter than the
    # ~14.7%/~-8.8% theoretical worst case, but roomier than any single
    # nudge's own bound, so a genuine multi-signal convergence still counts
    # for more than one nudge alone would).
    _CASCADE_NET_CAP = 0.10
    for i, r in enumerate(results):
        _pre = _pre_cascade_scores.get(r.get("field_id", i), 0.0)
        _post = float(r.get("final_score", 0.0) or 0.0)
        if _pre > 0:
            _net_ratio = _post / _pre
            _lo, _hi = 1.0 - _CASCADE_NET_CAP, 1.0 + _CASCADE_NET_CAP
            if _net_ratio > _hi:
                r["final_score"] = round(_pre * _hi, 2)
                r["competency_cascade_capped"] = "high"
            elif _net_ratio < _lo:
                r["final_score"] = round(_pre * _lo, 2)
                r["competency_cascade_capped"] = "low"

    # Scale fix (2026-08-18, tiered-ranking rollout): see confidence_band()'s
    # docstring. This run's own top final_score makes every confidence_band
    # call below genuinely relative to this chart's own candidates.
    _results_top_score = max((float(r.get("final_score", 0.0) or 0.0) for r in results), default=0.0)

    for r in results:
        r["explanation_chain"] = build_explanation_chain(r)
        r["confidence_band"] = confidence_band(r.get("final_score", 0.0), _results_top_score)
        r["evidence_summary"] = build_evidence_summary(r, _results_top_score)
        r["aptitude_explanation"] = build_aptitude_explanation(r)

    cluster_report = build_cluster_report(results)

    if enable_cross_chart_norm:
        # Cluster dicts in cluster_report are keyed by label, not family_id —
        # recompute the aggregates once here to recover family_id per cluster.
        aggregates = compute_family_aggregates(results)
        agg_by_label = {a["label"]: a for a in aggregates.values()}
        for cluster in cluster_report.get("clusters", []):
            agg = agg_by_label.get(cluster.get("career_family"))
            if agg:
                cluster["cross_chart_normalization"] = normalize_family_score_cross_chart(
                    agg["family_id"], cluster.get("family_score", 0.0)
                )

    if dasha_sequence:
        stages = compute_life_stage_competency_evolution(dasha_sequence, current_age)
        cluster_report["life_stage_evolution"] = {
            "stages": stages,
            "narrative": build_life_stage_narrative(stages, current_age),
        }

    # 2026-08 architecture-audit gap-fix (Gap 6): archetype-first hierarchical
    # view, read-only, built once per chart from the already-final `results`
    # (post archetype-alignment adjustment, so final_score is the same value
    # every other consumer sees). See build_archetype_hierarchy()'s own
    # docstring for why this stays a derived view rather than a registry
    # rewrite.
    cluster_report["archetype_hierarchy"] = build_archetype_hierarchy(results)

    for r in results:
        r["career_cluster_report"] = cluster_report

    return results, cluster_report


# =============================================================================
# SECTION 14 — COVERAGE VALIDATION (dev/test helper)
# =============================================================================

def validate_coverage(registry_branch_ids: List[str]) -> List[str]:
    """Return the list of branch ids that would fall back to a domain default
    (i.e. are NOT explicitly curated in FIELD_TO_FAMILY). Used by tests /
    manual audits when the registry grows."""
    return [bid for bid in registry_branch_ids if bid not in FIELD_TO_FAMILY]
