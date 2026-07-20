"""JyotishAI — BRANCH_PLANET_AFFINITY data and affinity scorer."""
from typing import Dict, List, Tuple, Set, Any, Optional

BRANCH_PLANET_AFFINITY: Dict[str, Dict[str, float]] = {
    # ── ENGINEERING (hardware/structural) ────────────────────────────────────
    # Taxonomy consolidation fix (audit): aerospace_engineering, aeronautical_engineering,
    # and space_systems_engineering were byte-identical vectors (Rahu.35/Mars.30/Saturn.20/
    # Mercury.15) -- three distinct course IDs the engine could not actually distinguish
    # astrologically despite presenting them as independently-ranked results. Differentiated
    # on real doctrinal grounds: aerospace_engineering keeps the broad umbrella signature;
    # aeronautical_engineering narrows to ATMOSPHERIC flight specifically (Sun = altitude/
    # aviation karaka, already used this way for defence_military/physical_education below,
    # vs Rahu's frontier/space-specific signature); space_systems_engineering leans Saturn
    # co-primary to reflect its own registry description ("systems integration / spacecraft
    # design" -- a structural/organizational discipline, not pure space-frontier novelty).
    "aerospace_engineering":               {"Rahu":0.35,"Mars":0.30,"Saturn":0.20,"Mercury":0.15},
    "aeronautical_engineering":            {"Mars":0.35,"Sun":0.25,"Saturn":0.25,"Mercury":0.15},
    "agricultural_food_engineering":       {"Moon":0.35,"Saturn":0.25,"Mars":0.20,"Mercury":0.20},
    # Taxonomy consolidation fix (audit): was byte-identical to "chemistry" below
    # (Mercury.30/Mars.30/Saturn.25/Sun.15). Differentiated: applied_chemistry is the
    # industrial/process-application discipline (Sun raised for tangible technological
    # output, matching chemical_engineering's Mars/Saturn process emphasis), while pure
    # "chemistry" below is re-weighted Mercury-primary for theoretical/analytical science.
    "applied_chemistry":                   {"Mars":0.30,"Mercury":0.25,"Saturn":0.25,"Sun":0.20},
    "architecture":                        {"Saturn":0.40,"Venus":0.30,"Mercury":0.20,"Mars":0.10},  # audit: Mercury raised for spatial geometry; Mars reduced
    "automotive_engineering":              {"Mars":0.35,"Saturn":0.30,"Venus":0.20,"Mercury":0.15},  # audit C-3: Venus reflects vehicles-as-consumer/luxury-product design (styling, comfort); mechanical_engineering is process/structure-focused and has no consumer-product karaka
    "biomedical_engineering":              {"Mars":0.30,"Mercury":0.25,"Moon":0.25,"Jupiter":0.20},
    "biotechnology_biochemical_engineering":{"Moon":0.30,"Mercury":0.25,"Mars":0.25,"Jupiter":0.20},
    "biotechnology_bsc":                   {"Moon":0.30,"Mercury":0.30,"Ketu":0.25,"Rahu":0.15},
    "blockchain_web3":                     {"Rahu":0.40,"Mercury":0.35,"Saturn":0.15,"Mars":0.10},
    "ceramic_engineering":                 {"Mars":0.40,"Sun":0.25,"Saturn":0.25,"Mercury":0.10},
    "chemical_engineering":                {"Mars":0.30,"Saturn":0.30,"Mercury":0.25,"Sun":0.15},
    "chemical_engineering_data_science":   {"Mercury":0.35,"Mars":0.25,"Saturn":0.25,"Rahu":0.15},
    "civil_engineering":                   {"Saturn":0.40,"Mars":0.30,"Mercury":0.20,"Sun":0.10},
    "cloud_devops":                        {"Mercury":0.35,"Rahu":0.30,"Saturn":0.25,"Mars":0.10},
    # audit C-3: Ketu doctrine harmonized with artificial_intelligence (0.10 — "dissolution
    # ≠ ML") and data_science_engineering (no Ketu); CS is broader than AI/DS so keeps a
    # small Ketu presence but no longer treats it as a co-primary driver.
    "computer_science_engineering":        {"Mercury":0.35,"Mars":0.25,"Rahu":0.25,"Ketu":0.15},
    "construction_engineering_management": {"Saturn":0.35,"Mars":0.30,"Jupiter":0.20,"Mercury":0.15},
    "cybersecurity":                       {"Rahu":0.35,"Mars":0.30,"Mercury":0.25,"Ketu":0.10},
    "data_science_engineering":            {"Mercury":0.35,"Rahu":0.25,"Saturn":0.20,"Mars":0.20},
    "electrical_engineering":              {"Sun":0.30,"Mars":0.30,"Mercury":0.25,"Saturn":0.15},  # audit C-3: Sun-top = power/light karaka (current, generation, illumination); contrast electronics_communication_engineering below, which is signal/information-karaka (Mercury-top)
    "electronics_communication_engineering":{"Mercury":0.35,"Mars":0.25,"Rahu":0.25,"Sun":0.15},
    "energy_engineering":                  {"Sun":0.35,"Mars":0.25,"Saturn":0.25,"Mercury":0.15},
    "engineering_physics":                 {"Sun":0.30,"Mercury":0.30,"Mars":0.25,"Saturn":0.15},
    "environmental_engineering":           {"Moon":0.30,"Saturn":0.30,"Mars":0.20,"Mercury":0.20},
    "fire_safety_engineering":             {"Mars":0.40,"Saturn":0.25,"Mercury":0.20,"Sun":0.15},
    "geographic_information_systems":      {"Mercury":0.35,"Saturn":0.30,"Moon":0.20,"Mars":0.15},
    "geological_engineering":              {"Saturn":0.40,"Mars":0.30,"Mercury":0.20,"Moon":0.10},
    "geophysics":                          {"Saturn":0.35,"Mars":0.25,"Mercury":0.25,"Moon":0.15},
    "industrial_engineering":              {"Saturn":0.35,"Mars":0.30,"Mercury":0.25,"Jupiter":0.10},
    "infrastructure_planning_engineering": {"Saturn":0.40,"Mars":0.25,"Jupiter":0.20,"Mercury":0.15},
    "instrumentation_engineering":         {"Mercury":0.35,"Mars":0.30,"Saturn":0.20,"Sun":0.15},
    "internet_of_things":                  {"Mercury":0.40,"Rahu":0.25,"Mars":0.20,"Moon":0.15},
    "leather_technology":                  {"Saturn":0.40,"Mars":0.25,"Mercury":0.20,"Venus":0.15},
    # Taxonomy consolidation fix (audit): was byte-identical to "naval_architecture" below.
    # marine_engineering (propulsion/machinery aboard ships) is Mars-mechanical-primary;
    # naval_architecture (hull/vessel design) is re-weighted toward this file's own
    # "architecture" doctrine (Saturn+Venus, see line above) blended with Moon for the
    # marine environment.
    "marine_engineering":                  {"Mars":0.35,"Saturn":0.30,"Moon":0.20,"Mercury":0.15},
    "materials_science_engineering":       {"Saturn":0.35,"Mars":0.30,"Rahu":0.20,"Ketu":0.15},
    "mechanical_engineering":              {"Mars":0.40,"Saturn":0.30,"Mercury":0.20,"Sun":0.10},
    "mechatronics_engineering":            {"Mars":0.35,"Mercury":0.30,"Saturn":0.20,"Rahu":0.15},
    "metallurgical_engineering":           {"Saturn":0.40,"Mars":0.35,"Sun":0.15,"Mercury":0.10},
    "microelectronics_vlsi":               {"Mercury":0.35,"Rahu":0.30,"Mars":0.20,"Saturn":0.15},
    "mining_engineering":                  {"Saturn":0.40,"Mars":0.30,"Rahu":0.20,"Mercury":0.10},
    "nanotechnology_engineering":          {"Rahu":0.35,"Mercury":0.30,"Mars":0.20,"Ketu":0.15},
    "naval_architecture":                  {"Saturn":0.30,"Moon":0.30,"Venus":0.20,"Mars":0.20},
    # Taxonomy consolidation fix (audit): nuclear_engineering was byte-identical to
    # "power_systems_engineering" below. Differentiated: nuclear gets Ketu (classical
    # karaka for radioactive/subtle-transformative energy, consistent with this file's
    # existing Ketu-for-occult/hidden-forces doctrine elsewhere, e.g. ayurveda/research_academia)
    # in place of generic Saturn; power_systems keeps the Sun/Saturn grid-infrastructure signature.
    "nuclear_engineering":                 {"Sun":0.35,"Mars":0.25,"Ketu":0.20,"Saturn":0.20},
    "optical_photonics_engineering":       {"Sun":0.35,"Mercury":0.30,"Mars":0.20,"Rahu":0.15},
    "petroleum_engineering":               {"Saturn":0.40,"Mars":0.25,"Rahu":0.20,"Mercury":0.15},
    "polymer_plastics_engineering":        {"Saturn":0.35,"Mars":0.25,"Mercury":0.25,"Rahu":0.15},
    "power_systems_engineering":           {"Sun":0.30,"Saturn":0.30,"Mars":0.25,"Mercury":0.15},
    "printing_packaging_technology":       {"Mercury":0.30,"Mars":0.25,"Saturn":0.25,"Venus":0.20},
    "production_manufacturing_engineering":{"Saturn":0.40,"Mars":0.35,"Mercury":0.15,"Jupiter":0.10},
    "refrigeration_airconditioning":       {"Mars":0.35,"Saturn":0.30,"Mercury":0.20,"Moon":0.15},
    "robotics_automation":                 {"Mars":0.35,"Mercury":0.30,"Rahu":0.25,"Saturn":0.10},
    "rubber_technology":                   {"Saturn":0.35,"Venus":0.25,"Mercury":0.25,"Mars":0.15},
    "semiconductor_nanoelectronics":       {"Rahu":0.35,"Saturn":0.30,"Mercury":0.25,"Ketu":0.10},
    "space_sciences_engineering":          {"Rahu":0.35,"Mars":0.25,"Sun":0.25,"Mercury":0.15},
    "space_systems_engineering":           {"Saturn":0.30,"Rahu":0.30,"Mars":0.25,"Mercury":0.15},
    "astronautical_engineering":           {"Rahu":0.40,"Mars":0.30,"Sun":0.20,"Mercury":0.10},
    "rocket_propulsion":                   {"Rahu":0.35,"Mars":0.35,"Sun":0.20,"Saturn":0.10},
    # R4 fix: add missing space-cluster ids (were in FIELD_PRIORITY_GROUPS but absent here)
    # Taxonomy consolidation fix (audit): these two were byte-identical. satellite_engineering
    # (bus/platform/structural) keeps Rahu-primary frontier-space signature; satellite_
    # communication_engineering is fundamentally a signal/communications discipline and is
    # re-weighted Mercury-primary to match this file's own electronics_communication_engineering
    # / telecommunication_engineering doctrine (Mercury-top = signal/information karaka).
    "satellite_engineering":               {"Rahu":0.40,"Mars":0.25,"Saturn":0.20,"Mercury":0.15},
    "satellite_communication_engineering": {"Mercury":0.35,"Rahu":0.30,"Mars":0.20,"Saturn":0.15},
    "space_materials":                     {"Saturn":0.35,"Rahu":0.25,"Mars":0.25,"Mercury":0.15},
    "earth_observation_remote_sensing":    {"Saturn":0.30,"Rahu":0.30,"Mercury":0.25,"Mars":0.15},
    "planetary_science":                   {"Ketu":0.30,"Jupiter":0.30,"Saturn":0.25,"Rahu":0.15},
    # life_science group had psychiatry as ghost id; add vector here
    # audit A-2/C-2: differentiated from botany_plant_science (was an identical vector,
    # astrologically indefensible — psychiatry needs Moon-affliction/Ketu/Saturn signature,
    # not the Moon/Venus vegetation signature of botany).
    "psychiatry":                          {"Moon":0.35,"Ketu":0.25,"Mercury":0.20,"Saturn":0.20},
    "telecommunication_engineering":       {"Mercury":0.35,"Rahu":0.30,"Mars":0.20,"Saturn":0.15},
    "transportation_engineering":          {"Saturn":0.35,"Mars":0.30,"Mercury":0.20,"Jupiter":0.15},
    "urban_informatics":                   {"Mercury":0.35,"Saturn":0.25,"Rahu":0.20,"Jupiter":0.20},
    "urban_regional_planning":             {"Saturn":0.35,"Jupiter":0.25,"Mercury":0.25,"Mars":0.15},
    "water_resources_engineering":         {"Moon":0.35,"Saturn":0.30,"Mars":0.20,"Mercury":0.15},
    # ── SCIENCE ──────────────────────────────────────────────────────────────
    "actuarial_science":                   {"Mercury":0.40,"Saturn":0.30,"Jupiter":0.20,"Mars":0.10},
    "applied_linguistics":                 {"Mercury":0.40,"Jupiter":0.30,"Moon":0.20,"Venus":0.10},
    "astronomy_astrophysics":              {"Sun":0.35,"Rahu":0.30,"Mercury":0.25,"Saturn":0.10},
    "atmospheric_climate_science":         {"Moon":0.35,"Mercury":0.25,"Saturn":0.25,"Mars":0.15},
    "biochemistry":                        {"Moon":0.30,"Mercury":0.30,"Mars":0.25,"Ketu":0.15},
    "bioinformatics":                      {"Mercury":0.35,"Moon":0.25,"Mars":0.25,"Ketu":0.15},
    "biological_sciences":                 {"Moon":0.35,"Mercury":0.25,"Jupiter":0.25,"Mars":0.15},
    "biology":                             {"Moon":0.40,"Mercury":0.25,"Jupiter":0.20,"Mars":0.15},
    "botany_plant_science":                {"Moon":0.40,"Mercury":0.25,"Jupiter":0.20,"Saturn":0.15},
    "chemistry":                           {"Mercury":0.35,"Saturn":0.30,"Mars":0.20,"Sun":0.15},
    "cognitive_science":                   {"Mercury":0.30,"Rahu":0.25,"Moon":0.20,"Ketu":0.15,"Jupiter":0.10},  # audit: Ketu added (subconscious/consciousness); Jupiter trimmed
    "computational_finance":               {"Mercury":0.40,"Saturn":0.25,"Jupiter":0.20,"Mars":0.15},
    "computational_social_science":        {"Mercury":0.35,"Saturn":0.25,"Jupiter":0.25,"Rahu":0.15},
    "earth_sciences":                      {"Saturn":0.35,"Moon":0.25,"Mercury":0.25,"Mars":0.15},
    "ecology_evolution":                   {"Moon":0.35,"Saturn":0.25,"Mercury":0.25,"Jupiter":0.15},
    "economics":                           {"Mercury":0.30,"Jupiter":0.30,"Saturn":0.25,"Mars":0.15},
    "economics_data_science":              {"Mercury":0.40,"Saturn":0.25,"Jupiter":0.20,"Rahu":0.15},
    "fisheries_science":                   {"Moon":0.40,"Saturn":0.25,"Mars":0.20,"Mercury":0.15},
    "forestry_wildlife":                   {"Moon":0.35,"Saturn":0.30,"Jupiter":0.20,"Mars":0.15},
    "geography":                           {"Saturn":0.30,"Mercury":0.30,"Moon":0.25,"Mars":0.15},
    "geology_applied":                     {"Saturn":0.40,"Mars":0.25,"Mercury":0.20,"Moon":0.15},
    "horticulture":                        {"Moon":0.35,"Saturn":0.25,"Mars":0.20,"Mercury":0.20},
    "marine_oceanography":                 {"Moon":0.40,"Mercury":0.25,"Saturn":0.20,"Mars":0.15},
    "mathematics":                         {"Mercury":0.40,"Saturn":0.25,"Mars":0.20,"Sun":0.15},
    "mathematics_computing":               {"Mercury":0.40,"Saturn":0.20,"Mars":0.20,"Ketu":0.20},
    # Taxonomy consolidation fix (audit): these two were byte-identical. microbiology
    # (infection/pathogen focus) keeps Mars raised (invasive/combative disease-agent
    # signature); molecular_biology_genetics (heredity/DNA-level "hidden code of life")
    # is re-weighted Ketu co-primary -- a stronger, more specific classical signature for
    # inherited/hidden information than the generic Mars weight it shared with microbiology.
    "microbiology":                        {"Moon":0.30,"Mars":0.30,"Mercury":0.25,"Ketu":0.15},
    "molecular_biology_genetics":          {"Moon":0.30,"Ketu":0.25,"Mercury":0.25,"Mars":0.20},
    "physics":                             {"Sun":0.35,"Mercury":0.30,"Mars":0.20,"Saturn":0.15},
    "quantum_computing":                   {"Mercury":0.40,"Rahu":0.30,"Ketu":0.15,"Mars":0.15},  # audit: Mercury primary for mathematical logic; Ketu reduced
    "research_academia":                   {"Jupiter":0.25,"Mercury":0.30,"Saturn":0.20,"Ketu":0.25},  # T3-B: Ketu 0.15→0.25 (deep investigation/past-life mastery); Saturn 0.25→0.20
    "soil_science_agronomy":               {"Saturn":0.35,"Moon":0.30,"Mars":0.20,"Mercury":0.15},
    "statistics_data_science":             {"Mercury":0.40,"Saturn":0.25,"Mars":0.20,"Jupiter":0.15},
    "zoology_animal_science":              {"Moon":0.40,"Mars":0.25,"Jupiter":0.20,"Saturn":0.15},
    # ── MEDICINE / HEALTH ─────────────────────────────────────────────────────
    "ayurveda":                            {"Ketu":0.35,"Moon":0.30,"Jupiter":0.25,"Sun":0.10},
    "cardiac_technology":                  {"Sun":0.35,"Mars":0.25,"Mercury":0.25,"Moon":0.15},
    "clinical_psychology":                 {"Venus":0.25,"Moon":0.30,"Mercury":0.30,"Jupiter":0.15},  # T3-B: Mercury up (diagnostic/analytical); Venus down (therapeutic but not dominant)
    "dentistry":                           {"Mars":0.40,"Mercury":0.25,"Moon":0.20,"Saturn":0.15},
    "health_informatics":                  {"Mercury":0.35,"Moon":0.25,"Jupiter":0.25,"Rahu":0.15},
    # Taxonomy consolidation fix (audit): was byte-identical to "unani_medicine" below.
    # homeopathy (subtle-dose/vibrational medicine) raises Ketu, its strongest classical
    # signature (subtle/occult); unani_medicine below is re-weighted Jupiter co-primary
    # for its classical-text/humoral-tradition (Yunani) knowledge lineage.
    "homeopathy":                          {"Ketu":0.35,"Moon":0.30,"Mercury":0.20,"Jupiter":0.15},
    "medicine_mbbs":                       {"Sun":0.30,"Mars":0.25,"Jupiter":0.20,"Moon":0.15,"Ketu":0.10},  # T3-B: Ketu added (surgical precision, healer karma); Jupiter/Moon trimmed
    # audit C-4: regridded to 0.05 steps; Venus dropped (audit note: no classical basis for
    # a research field) and redistributed to the remaining karakas.
    "medical_research":                    {"Mercury":0.35,"Mars":0.25,"Jupiter":0.20,"Moon":0.20},
    "public_health":                       {"Jupiter":0.35,"Moon":0.30,"Saturn":0.20,"Mercury":0.15},
    "medical_laboratory_technology":       {"Mars":0.30,"Mercury":0.30,"Moon":0.25,"Saturn":0.15},
    "medical_physics":                     {"Sun":0.35,"Mercury":0.25,"Mars":0.20,"Jupiter":0.20},
    "neuroscience":                        {"Mercury":0.30,"Moon":0.30,"Mars":0.20,"Ketu":0.20},
    "nursing":                             {"Moon":0.35,"Jupiter":0.25,"Mars":0.25,"Mercury":0.15},
    "nutrition_dietetics":                 {"Moon":0.35,"Mercury":0.25,"Jupiter":0.25,"Venus":0.15},
    "occupational_therapy":                {"Mars":0.30,"Moon":0.30,"Mercury":0.20,"Jupiter":0.20},
    "optometry":                           {"Sun":0.35,"Mercury":0.30,"Mars":0.20,"Moon":0.15},
    "paramedics_emergency_medicine":       {"Mars":0.40,"Moon":0.25,"Mercury":0.20,"Sun":0.15},
    "pharmacy":                            {"Mercury":0.35,"Moon":0.25,"Mars":0.25,"Jupiter":0.15},
    "physiotherapy":                       {"Mars":0.35,"Moon":0.25,"Sun":0.25,"Mercury":0.15},
    "prosthetics_orthotics":               {"Mars":0.35,"Saturn":0.25,"Mercury":0.25,"Moon":0.15},
    "psychology":                          {"Moon":0.40,"Mercury":0.30,"Jupiter":0.15,"Ketu":0.15},
    "radiography_imaging":                 {"Sun":0.35,"Mars":0.25,"Mercury":0.25,"Rahu":0.15},
    "unani_medicine":                      {"Jupiter":0.30,"Moon":0.30,"Ketu":0.25,"Mercury":0.15},
    "veterinary_science":                  {"Moon":0.35,"Mars":0.25,"Jupiter":0.25,"Saturn":0.15},
    "yoga_naturopathy":                    {"Ketu":0.35,"Moon":0.25,"Jupiter":0.25,"Sun":0.15},
    # ── TECHNOLOGY / IT ───────────────────────────────────────────────────────
    "artificial_intelligence":             {"Mercury":0.30,"Rahu":0.35,"Saturn":0.15,"Ketu":0.10,"Jupiter":0.10},  # T3-B: Rahu dominant (disruption/machines); Saturn added (training loops/rules); Ketu 0.25→0.10 (dissolution ≠ ML)
    "information_technology":              {"Mercury":0.35,"Rahu":0.25,"Mars":0.25,"Ketu":0.15},
    # ── COMMERCE / MANAGEMENT ─────────────────────────────────────────────────
    "agribusiness_management":             {"Jupiter":0.30,"Saturn":0.25,"Moon":0.25,"Mercury":0.20},
    "business_management":                 {"Jupiter":0.35,"Mercury":0.30,"Saturn":0.20,"Mars":0.15},
    "ca_cma_cs_professional":              {"Mercury":0.40,"Saturn":0.30,"Jupiter":0.20,"Mars":0.10},
    # Taxonomy consolidation fix (audit): was byte-identical to "finance_banking" below.
    # commerce_accounting (bookkeeping/compliance/records) raises Saturn co-primary
    # (discipline/record-keeping karaka); finance_banking below keeps Jupiter co-primary
    # (wealth-expansion/capital-flow karaka).
    "commerce_accounting":                 {"Mercury":0.35,"Saturn":0.30,"Jupiter":0.25,"Mars":0.10},
    "digital_marketing":                   {"Mercury":0.35,"Rahu":0.30,"Venus":0.20,"Mars":0.15},
    "econometrics":                        {"Mercury":0.40,"Saturn":0.25,"Jupiter":0.20,"Rahu":0.15},
    "educational_technology":              {"Mercury":0.35,"Jupiter":0.30,"Rahu":0.20,"Moon":0.15},
    "entrepreneurship":                    {"Mars":0.30,"Jupiter":0.30,"Mercury":0.25,"Rahu":0.15},
    "finance_banking":                     {"Jupiter":0.35,"Mercury":0.30,"Saturn":0.25,"Mars":0.10},
    "fintech":                             {"Mercury":0.35,"Rahu":0.30,"Jupiter":0.20,"Mars":0.15},
    "food_science_technology":             {"Moon":0.35,"Mercury":0.25,"Mars":0.20,"Venus":0.20},
    "game_design_technology":              {"Mercury":0.30,"Rahu":0.25,"Venus":0.20,"Moon":0.15,"Mars":0.10},  # audit: Moon added for emotional engagement/player psychology
    # audit C-3/C-4: regridded to 0.05 steps and Mars (odd #2 for an administrative field)
    # replaced with Mercury (analytical/administrative karaka).
    "healthcare_management":               {"Jupiter":0.35,"Mercury":0.25,"Saturn":0.25,"Moon":0.15},
    "hotel_hospitality_management":        {"Moon":0.30,"Venus":0.30,"Jupiter":0.25,"Mercury":0.15},
    "library_information_science":         {"Mercury":0.35,"Jupiter":0.30,"Saturn":0.25,"Moon":0.10},
    "organisational_psychology":           {"Mercury":0.30,"Jupiter":0.30,"Moon":0.25,"Mars":0.15},
    "real_estate_management":              {"Saturn":0.35,"Mars":0.25,"Jupiter":0.25,"Mercury":0.15},
    "rural_management":                    {"Saturn":0.30,"Moon":0.30,"Jupiter":0.25,"Mercury":0.15},
    "social_work":                         {"Moon":0.35,"Jupiter":0.30,"Saturn":0.20,"Mars":0.15},
    "supply_chain_logistics":              {"Saturn":0.35,"Mercury":0.30,"Mars":0.20,"Jupiter":0.15},
    "tourism_management":                  {"Moon":0.30,"Venus":0.30,"Mercury":0.25,"Jupiter":0.15},
    # ── LAW / HUMANITIES / SOCIAL ─────────────────────────────────────────────
    "corporate_law":                       {"Jupiter":0.35,"Mercury":0.35,"Saturn":0.20,"Mars":0.10},
    "criminal_law":                        {"Mars":0.35,"Saturn":0.25,"Jupiter":0.25,"Mercury":0.15},
    "criminology_penology":                {"Mars":0.35,"Saturn":0.30,"Jupiter":0.20,"Mercury":0.15},
    "defence_military":                    {"Mars":0.40,"Sun":0.30,"Saturn":0.20,"Mercury":0.10},
    "defence_strategic_studies":           {"Mars":0.30,"Sun":0.30,"Jupiter":0.25,"Saturn":0.15},
    "development_studies":                 {"Jupiter":0.40,"Mercury":0.25,"Moon":0.20,"Saturn":0.15},
    "education_teaching":                  {"Jupiter":0.35,"Mercury":0.30,"Moon":0.20,"Sun":0.15},
    "environmental_law":                   {"Jupiter":0.30,"Saturn":0.25,"Mercury":0.25,"Moon":0.20},
    "environmental_science":               {"Moon":0.30,"Saturn":0.25,"Mercury":0.25,"Jupiter":0.20},
    "environmental_studies_interdisciplinary":{"Moon":0.30,"Saturn":0.25,"Jupiter":0.25,"Mercury":0.20},
    "forensic_science":                    {"Mars":0.35,"Saturn":0.25,"Mercury":0.25,"Ketu":0.15},
    "gender_studies":                      {"Moon":0.30,"Jupiter":0.30,"Mercury":0.25,"Venus":0.15},
    "history_archaeology":                 {"Ketu":0.35,"Saturn":0.25,"Jupiter":0.25,"Sun":0.15},
    "intellectual_property_law":           {"Mercury":0.35,"Jupiter":0.30,"Saturn":0.20,"Mars":0.15},
    "intelligence_security_studies":       {"Mars":0.35,"Saturn":0.25,"Rahu":0.25,"Mercury":0.15},
    "international_law":                   {"Jupiter":0.40,"Saturn":0.30,"Mercury":0.20,"Sun":0.10},
    "international_relations":             {"Jupiter":0.35,"Mercury":0.25,"Sun":0.25,"Saturn":0.15},
    "law_llb":                             {"Jupiter":0.35,"Mercury":0.30,"Saturn":0.25,"Mars":0.10},
    "liberal_arts_interdisciplinary":      {"Jupiter":0.30,"Mercury":0.25,"Moon":0.25,"Venus":0.20},
    "museum_heritage_studies":             {"Ketu":0.35,"Saturn":0.25,"Jupiter":0.25,"Moon":0.15},
    "peace_conflict_studies":              {"Jupiter":0.35,"Saturn":0.25,"Mercury":0.25,"Moon":0.15},
    "philosophy":                          {"Jupiter":0.35,"Mercury":0.25,"Ketu":0.25,"Saturn":0.15},
    "political_science":                   {"Sun":0.30,"Jupiter":0.25,"Mercury":0.25,"Saturn":0.20},
    "public_policy":                       {"Sun":0.30,"Jupiter":0.25,"Mercury":0.25,"Saturn":0.20},  # audit: harmonized with civil_services (Sun-primary governance domain)
    "sanskrit_classical_studies":          {"Jupiter":0.35,"Ketu":0.30,"Mercury":0.25,"Saturn":0.10},
    "sociology_anthropology":              {"Moon":0.30,"Jupiter":0.30,"Mercury":0.25,"Saturn":0.15},
    "speech_language_pathology":           {"Mercury":0.40,"Moon":0.25,"Mars":0.20,"Jupiter":0.15},
    # ── ARTS / DESIGN / MEDIA ─────────────────────────────────────────────────
    # Taxonomy consolidation fix (audit): these two were byte-identical. animation_multimedia
    # raises Mars (animation is fundamentally about motion/kinetics -- a strong Mars
    # signature) alongside Rahu (screen/frontier-media); design_ux_product swaps Rahu for
    # Saturn (structured systems-thinking is closer to UX/product design's discipline than
    # Rahu's novelty-frontier signature).
    "animation_multimedia":                {"Venus":0.30,"Mercury":0.25,"Rahu":0.25,"Mars":0.20},
    "design_ux_product":                   {"Venus":0.35,"Mercury":0.30,"Saturn":0.20,"Rahu":0.15},
    "fashion_design":                      {"Venus":0.40,"Mercury":0.25,"Moon":0.20,"Rahu":0.15},
    "film_television_production":          {"Venus":0.35,"Rahu":0.25,"Mercury":0.25,"Moon":0.15},
    "fine_arts":                           {"Venus":0.40,"Moon":0.25,"Mercury":0.20,"Jupiter":0.15},
    "interior_design":                     {"Venus":0.35,"Mercury":0.25,"Moon":0.25,"Saturn":0.15},
    "journalism_media":                    {"Mercury":0.35,"Rahu":0.25,"Moon":0.25,"Venus":0.15},
    "landscape_architecture":              {"Venus":0.30,"Saturn":0.30,"Moon":0.25,"Mercury":0.15},
    "linguistics":                         {"Mercury":0.40,"Jupiter":0.30,"Moon":0.20,"Venus":0.10},
    "literature_languages":                {"Mercury":0.35,"Venus":0.25,"Jupiter":0.25,"Moon":0.15},
    "mass_communication":                  {"Moon":0.35,"Mercury":0.30,"Venus":0.20,"Rahu":0.15},
    # audit C-4: regridded to 0.05 steps (Mars retained for rhythm/percussion/dexterity)
    "music":                               {"Venus":0.35,"Moon":0.30,"Mercury":0.15,"Jupiter":0.10,"Mars":0.10},
    "performing_arts":                     {"Venus":0.35,"Moon":0.30,"Mercury":0.20,"Jupiter":0.15},
    "photography":                         {"Venus":0.30,"Mercury":0.25,"Rahu":0.25,"Moon":0.20},
    "textile_design":                      {"Venus":0.40,"Mercury":0.25,"Moon":0.20,"Saturn":0.15},
    "textile_technology":                  {"Venus":0.30,"Saturn":0.30,"Mars":0.25,"Mercury":0.15},
    "theatre_drama":                       {"Venus":0.35,"Moon":0.30,"Mercury":0.20,"Jupiter":0.15},
    "visual_communication":                {"Venus":0.35,"Mercury":0.30,"Rahu":0.20,"Moon":0.15},
    # ── PHYSICAL / SPORT ─────────────────────────────────────────────────────
    "physical_education":                  {"Mars":0.30,"Sun":0.30,"Jupiter":0.25,"Moon":0.15},  # audit: Mars raised to co-primary with Sun
    "sports_science_management":           {"Mars":0.30,"Sun":0.30,"Mercury":0.25,"Jupiter":0.15},  # audit: Mars raised (primary karaka for sports/competition)
    # ── AGRICULTURE / ENVIRONMENT ─────────────────────────────────────────────
    "agriculture_forestry":                {"Moon":0.35,"Saturn":0.30,"Mars":0.20,"Mercury":0.15},
    # ── GOVERNANCE / PUBLIC ───────────────────────────────────────────────────
    "civil_services":                      {"Sun":0.35,"Saturn":0.25,"Jupiter":0.25,"Mercury":0.15},
    # ── INTERDISCIPLINARY / BEHAVIOURAL ──────────────────────────────────────
    "behavioural_science":                 {"Moon":0.30,"Mercury":0.30,"Jupiter":0.25,"Mars":0.15},
}

SPACE_AEROSPACE_REGISTRY_EXTENSIONS: Dict[str, Dict[str, Any]] = {
    "astronautical_engineering": {
        "label": "Astronautical Engineering",
        "domain": "engineering",
        "field": "Space & Aerospace",
        "track": "Space Engineering",
        "specialization": "Astronautical Engineering / Orbital Systems",
        "niche": "Launch Vehicles / Orbital Mechanics / Spacecraft Design",
        "description": "Spacecraft, orbital systems, launch vehicle design, and mission architecture",
        "career_signature": ["Space startups", "ISRO", "Rocket propulsion labs", "Mission control"],
    },
    "rocket_propulsion": {
        "label": "Rocket Propulsion",
        "domain": "engineering",
        "field": "Space & Aerospace",
        "track": "Propulsion Systems",
        "specialization": "Rocket Propulsion / Propellant Systems",
        "niche": "Liquid propulsion / Solid propulsion / Engine performance / Nozzle design",
        "description": "Rocket propulsion systems design, propellant chemistry, and engine performance",
        "career_signature": ["ISRO", "DRDO", "Rocket Labs", "Aerojet", "L3Harris", "Space startups"],
    },
    "satellite_communication_engineering": {
        "label": "Satellite Communication Engineering",
        "domain": "engineering",
        "field": "Space & Aerospace",
        "track": "Communication Systems",
        "specialization": "Satellite Communication / Ground Stations",
        "niche": "RF systems / Antenna design / Satellite orbit / Ground control",
        "description": "Satellite systems, ground stations, RF communication, and orbital operations",
        "career_signature": ["ISRO", "DRDO", "Hughes", "Intelsat", "Airbus Defense"],
    },
    "space_sciences_engineering": {
        "label": "Space Sciences & Technology",
        "domain": "engineering",
        "field": "Space & Aerospace",
        "track": "Space Research",
        "specialization": "Space Sciences / Astrophysics / Mission Design",
        "niche": "Space physics / Planetary science / Mission architecture / Ground systems",
        "description": "Scientific exploration of space including astrophysics, planetary science, and mission design",
        "career_signature": ["NASA", "ISRO", "ESA", "Universities", "Research labs"],
    },
    "space_systems_engineering": {
        "label": "Space Systems Engineering",
        "domain": "engineering",
        "field": "Space & Aerospace",
        "track": "Space Systems",
        "specialization": "Space Systems Engineering / Spacecraft Integration",
        "niche": "Systems integration / Spacecraft design / Mission systems / GNC / Flight dynamics",
        "description": "End-to-end spacecraft systems engineering covering design, integration, testing, and operations",
        "career_signature": ["ISRO", "NASA", "ESA", "SpaceX", "Boeing Defense", "Space startups"],
    },
}


_CANONICAL_PLANETS: Set[str] = {
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
}


def _check_duplicate_literal_keys() -> List[str]:
    """audit A-1: detect duplicate dict-literal keys inside BRANCH_PLANET_AFFINITY.

    Python silently keeps the last occurrence of a repeated literal key, so this can't be
    detected by inspecting the resulting dict — it has to be found by parsing the source AST.
    """
    import ast

    dupes: List[str] = []
    try:
        with open(__file__, "r", encoding="utf-8") as _f:
            tree = ast.parse(_f.read(), filename=__file__)
    except OSError:
        return dupes

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "BRANCH_PLANET_AFFINITY" not in targets:
                continue
            seen: Set[str] = set()
            for key_node in node.value.keys:
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    if key_node.value in seen:
                        dupes.append(key_node.value)
                    seen.add(key_node.value)
    return dupes


# ── LS8 fix / audit A-3: raising validator (was: sum-only, warnings.warn only) ────────────
def _validate_affinity_weights() -> None:
    """Called at module load; validates BRANCH_PLANET_AFFINITY structurally and raises on any
    violation rather than silently warning. Checks:
      - no duplicate dict-literal keys (A-1)
      - every vector sums to 1.0 (±0.005)
      - every vector is non-empty
      - every planet name is one of the 9 canonical planets
      - every weight is in (0, 1]
    """
    errors: List[str] = []

    dupes = _check_duplicate_literal_keys()
    if dupes:
        errors.append(f"duplicate dict-literal key(s): {sorted(set(dupes))}")

    for fid, weights in BRANCH_PLANET_AFFINITY.items():
        if not weights:
            errors.append(f"{fid}: empty affinity vector")
            continue
        total = sum(weights.values())
        if abs(total - 1.0) > 0.005:
            errors.append(f"{fid}: sum={total:.4f} (expected 1.0 ± 0.005)")
        for planet, weight in weights.items():
            if planet not in _CANONICAL_PLANETS:
                errors.append(f"{fid}: unknown planet {planet!r}")
            if not (0.0 < weight <= 1.0):
                errors.append(f"{fid}: weight for {planet} out of (0,1] range: {weight}")

    if errors:
        raise ValueError("BRANCH_PLANET_AFFINITY validation failed:\n" + "\n".join(errors))

_validate_affinity_weights()

import logging as _logging
_logger = _logging.getLogger(__name__)
_MISSING_PLANET_WARNED: Set[str] = set()


def compute_branch_affinity_score_llm(
    field_id: str,
    label: str,
    domain: str,
    affinity_weights: Dict[str, float],
    eff_strengths: Dict[str, float],
) -> Dict[str, Any]:
    """Compute branch affinity score from hardcoded planet weight vector × effective strengths.

    The affinity score is a weighted dot product:
        affinity_score = sum(eff_strengths[p] * w for p, w in affinity_weights.items()) * 100

    Effective strength (eff_str) is UNBOUNDED — it is `raw / min_v` where `min_v` is the
    chart's weakest planet, so 1.0 does not represent "minimum required Shadbala" and values
    above 2.0 are observed in charts with one very weak planet. Consequently the raw score
    here is also unbounded before the downstream soft-cap (_log_norm_score,
    _AFFINITY_SOFT_CAP=180) is applied by the caller.

    Dignity (exaltation/own-sign/combustion/war/paksha-bala/vargottama) is intentionally
    NOT re-applied here — it is already folded into `eff_strengths` by
    `_compute_eff_strengths`, and the Vargottama-specific uplift is applied once, downstream,
    by `apply_vargottama_affinity_uplift`. Re-deriving a second "exalted-ish" bonus from
    eff-strength thresholds here would double-count the same classical signal (see audit D-1/D-2).

    Returns:
        dict with:
          affinity_score    : float   — raw score (unbounded until downstream soft-cap)
          affinity_planets  : dict    — copy of affinity_weights (used by gap-boost routines)
          top_planet        : str     — planet with highest weight
          domain            : str     — field domain
    """
    if not affinity_weights:
        # Graceful fallback: no affinity data for this field → use the same generic
        # 9-planet weighted-dot-product convention as everywhere else (audit B-3: previously
        # this path used a bespoke avg*70 formula on a different scale than the main branch).
        affinity_weights = dict(_GENERIC_9P_WEIGHTS)

    # Weighted dot product
    score = 0.0
    contributions: Dict[str, float] = {}
    for planet, weight in affinity_weights.items():
        if planet not in eff_strengths and planet not in _MISSING_PLANET_WARNED:
            _MISSING_PLANET_WARNED.add(planet)
            _logger.warning(
                "compute_branch_affinity_score_llm: planet %r missing from eff_strengths "
                "for field %r — defaulting to 0.5 (this will only be logged once per planet)",
                planet, field_id,
            )
        eff = eff_strengths.get(planet, 0.5)  # default 0.5 if planet data missing
        contributions[planet] = round(eff * weight * 100.0, 2)
        score += eff * weight * 100.0

    top_planet = max(affinity_weights.items(), key=lambda x: x[1])[0]

    return {
        "affinity_score": round(score, 2),
        "affinity_planets": dict(affinity_weights),
        "top_planet": top_planet,
        "domain": domain,
        "planet_contributions": contributions,
    }


def apply_vargottama_affinity_uplift(
    result: dict,
    affinity_weights: dict,
    vargottama_planets: list,
) -> dict:
    """LS9 fix: Apply Vargottama uplift to affinity score.

    Called by engine.py after compute_branch_affinity_score_llm().
    If the top-affinity planet is Vargottama, add +6% uplift (between
    OWN +4% and EXALTED +8% — classical Vargottama is stronger than own-sign).
    """
    top = result.get("top_planet", "")
    if top and top in vargottama_planets:
        result = dict(result)
        result["affinity_score"] = round(result["affinity_score"] * 1.06, 2)
        result["vargottama_uplift"] = top
    return result


# ── Generic 9-planet equal-weight affinity (fallback for unlisted fields) ────
_GENERIC_9P_WEIGHTS: Dict[str, float] = {
    "Sun": 0.11, "Moon": 0.11, "Mars": 0.11, "Mercury": 0.12,
    "Jupiter": 0.12, "Venus": 0.11, "Saturn": 0.11,
    "Rahu": 0.11, "Ketu": 0.10,
}

# ── Life Science Registry Extensions ─────────────────────────────────────────
# Metadata for medicine/biotech/life-science fields beyond the core BRANCH_PLANET_AFFINITY.
LIFE_SCIENCE_REGISTRY_EXTENSIONS: Dict[str, Dict[str, Any]] = {
    "medicine_mbbs": {
        "label": "Medicine (MBBS)",
        "domain": "medicine",
        "field": "Medical Sciences",
        "track": "Clinical Medicine",
        "specialization": "MBBS / General Medicine",
        "niche": "Clinical diagnosis / Surgery / Patient care / Medical ethics",
        "description": "Full clinical medicine degree covering diagnosis, treatment, and surgery",
        "career_signature": ["Hospitals", "Clinics", "AIIMS", "PGI", "Research medical institutes"],
    },
    # audit B-1: nursing_bsc / pharmacy_bpharm / ayurveda_bams / psychology_bsc skeleton
    # entries were removed — they had no BRANCH_PLANET_AFFINITY vector (scored via the
    # unrelated engine _DEFAULT_AFFINITY fallback) and duplicated the fully-defined
    # canonical branches "nursing", "pharmacy", "ayurveda", and "psychology" /
    # "clinical_psychology" already present in BRANCH_PLANET_AFFINITY + the JSON registry.
    "biotechnology_bsc": {
        "label": "Biotechnology (B.Sc.)",
        "domain": "science",
        "field": "Life Sciences",
        "track": "Biotechnology & Life Sciences",
        "specialization": "B.Sc. Biotechnology",
        "niche": "Genetic engineering / Fermentation / Drug development / Bioinformatics",
        "description": "Applied life sciences covering genetic engineering, fermentation, and drug development",
        "career_signature": ["Biotech firms", "Pharma companies", "Research labs", "Agricultural biotech"],
    },
    "medical_research": {
        "label": "Medical Research (B.Sc. / M.Sc.)",
        "domain": "medicine",
        "field": "Medical Sciences",
        "track": "Clinical & Biomedical Research",
        "specialization": "Medical Research / Biomedical Sciences",
        "niche": "Clinical trials / Drug discovery / Translational research / Genomics / Epidemiology",
        "description": "Scientific investigation into disease mechanisms, treatment development, and clinical application",
        "career_signature": ["AIIMS Research", "ICMR", "Pharma R&D", "Biotech companies", "Global CROs"],
    },
    "public_health": {
        "label": "Public Health (MPH / B.Sc.)",
        "domain": "medicine",
        "field": "Medical Sciences",
        "track": "Preventive & Community Medicine",
        "specialization": "Public Health / Epidemiology",
        "niche": "Epidemiology / Health policy / Community medicine / Global health / Biostatistics",
        "description": "Population-level health sciences covering disease prevention, policy, and community medicine",
        "career_signature": ["WHO", "ICMR", "State health departments", "NGOs", "Global health organizations"],
    },
}
