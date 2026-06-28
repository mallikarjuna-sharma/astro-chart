"""JyotishAI — BRANCH_PLANET_AFFINITY data and affinity scorer."""
from typing import Dict, List, Tuple, Set, Any, Optional

BRANCH_PLANET_AFFINITY: Dict[str, Dict[str, float]] = {
    # ── ENGINEERING (hardware/structural) ────────────────────────────────────
    "aerospace_engineering":               {"Rahu":0.35,"Mars":0.30,"Saturn":0.20,"Mercury":0.15},
    "aeronautical_engineering":            {"Rahu":0.35,"Mars":0.30,"Saturn":0.20,"Mercury":0.15},
    "agricultural_food_engineering":       {"Moon":0.35,"Saturn":0.25,"Mars":0.20,"Mercury":0.20},
    "applied_chemistry":                   {"Mercury":0.30,"Mars":0.30,"Saturn":0.25,"Sun":0.15},
    "architecture":                        {"Saturn":0.40,"Venus":0.30,"Mars":0.20,"Mercury":0.10},
    "automotive_engineering":              {"Mars":0.35,"Saturn":0.30,"Venus":0.20,"Mercury":0.15},
    "biomedical_engineering":              {"Mars":0.30,"Mercury":0.25,"Moon":0.25,"Jupiter":0.20},
    "biotechnology_biochemical_engineering":{"Moon":0.30,"Mercury":0.25,"Mars":0.25,"Jupiter":0.20},
    "biotechnology_bsc":                   {"Moon":0.30,"Mercury":0.30,"Ketu":0.25,"Rahu":0.15},
    "blockchain_web3":                     {"Rahu":0.40,"Mercury":0.35,"Saturn":0.15,"Mars":0.10},
    "ceramic_engineering":                 {"Mars":0.40,"Sun":0.25,"Saturn":0.25,"Mercury":0.10},
    "chemical_engineering":                {"Mars":0.30,"Saturn":0.30,"Mercury":0.25,"Sun":0.15},
    "chemical_engineering_data_science":   {"Mercury":0.35,"Mars":0.25,"Saturn":0.25,"Rahu":0.15},
    "civil_engineering":                   {"Saturn":0.40,"Mars":0.30,"Mercury":0.20,"Sun":0.10},
    "cloud_devops":                        {"Mercury":0.35,"Rahu":0.30,"Saturn":0.25,"Mars":0.10},
    "computer_science_engineering":        {"Mercury":0.30,"Ketu":0.25,"Mars":0.25,"Rahu":0.20},
    "construction_engineering_management": {"Saturn":0.35,"Mars":0.30,"Jupiter":0.20,"Mercury":0.15},
    "cybersecurity":                       {"Rahu":0.35,"Mars":0.30,"Mercury":0.25,"Ketu":0.10},
    "data_science_engineering":            {"Mercury":0.35,"Rahu":0.25,"Saturn":0.20,"Mars":0.20},
    "electrical_engineering":              {"Sun":0.30,"Mars":0.30,"Mercury":0.25,"Saturn":0.15},
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
    "marine_engineering":                  {"Moon":0.30,"Mars":0.30,"Saturn":0.25,"Mercury":0.15},
    "materials_science_engineering":       {"Saturn":0.35,"Mars":0.30,"Rahu":0.20,"Ketu":0.15},
    "mechanical_engineering":              {"Mars":0.40,"Saturn":0.30,"Mercury":0.20,"Sun":0.10},
    "mechatronics_engineering":            {"Mars":0.35,"Mercury":0.30,"Saturn":0.20,"Rahu":0.15},
    "metallurgical_engineering":           {"Saturn":0.40,"Mars":0.35,"Sun":0.15,"Mercury":0.10},
    "microelectronics_vlsi":               {"Mercury":0.35,"Rahu":0.30,"Mars":0.20,"Saturn":0.15},
    "mining_engineering":                  {"Saturn":0.40,"Mars":0.30,"Rahu":0.20,"Mercury":0.10},
    "nanotechnology_engineering":          {"Rahu":0.35,"Mercury":0.30,"Mars":0.20,"Ketu":0.15},
    "naval_architecture":                  {"Moon":0.30,"Mars":0.30,"Saturn":0.25,"Mercury":0.15},
    "nuclear_engineering":                 {"Sun":0.35,"Mars":0.30,"Saturn":0.20,"Mercury":0.15},
    "optical_photonics_engineering":       {"Sun":0.35,"Mercury":0.30,"Mars":0.20,"Rahu":0.15},
    "petroleum_engineering":               {"Saturn":0.40,"Mars":0.25,"Rahu":0.20,"Mercury":0.15},
    "polymer_plastics_engineering":        {"Saturn":0.35,"Mars":0.25,"Mercury":0.25,"Rahu":0.15},
    "power_systems_engineering":           {"Sun":0.35,"Mars":0.30,"Saturn":0.20,"Mercury":0.15},
    "printing_packaging_technology":       {"Mercury":0.30,"Mars":0.25,"Saturn":0.25,"Venus":0.20},
    "production_manufacturing_engineering":{"Saturn":0.40,"Mars":0.35,"Mercury":0.15,"Jupiter":0.10},
    "refrigeration_airconditioning":       {"Mars":0.35,"Saturn":0.30,"Mercury":0.20,"Moon":0.15},
    "robotics_automation":                 {"Mars":0.35,"Mercury":0.30,"Rahu":0.25,"Saturn":0.10},
    "rubber_technology":                   {"Saturn":0.35,"Venus":0.25,"Mercury":0.25,"Mars":0.15},
    "semiconductor_nanoelectronics":       {"Rahu":0.35,"Saturn":0.30,"Mercury":0.25,"Ketu":0.10},
    "space_sciences_engineering":          {"Rahu":0.35,"Mars":0.25,"Sun":0.25,"Mercury":0.15},
    "space_systems_engineering":           {"Rahu":0.35,"Mars":0.30,"Saturn":0.20,"Mercury":0.15},
    "astronautical_engineering":           {"Rahu":0.40,"Mars":0.30,"Sun":0.20,"Mercury":0.10},
    "rocket_propulsion":                   {"Rahu":0.35,"Mars":0.35,"Sun":0.20,"Saturn":0.10},
    "satellite_communication_engineering": {"Rahu":0.40,"Mercury":0.30,"Mars":0.20,"Saturn":0.10},
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
    "chemistry":                           {"Mercury":0.30,"Mars":0.30,"Saturn":0.25,"Sun":0.15},
    "cognitive_science":                   {"Mercury":0.35,"Rahu":0.25,"Moon":0.25,"Jupiter":0.15},
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
    "microbiology":                        {"Moon":0.30,"Mercury":0.25,"Mars":0.25,"Ketu":0.20},
    "molecular_biology_genetics":          {"Moon":0.30,"Mercury":0.25,"Mars":0.25,"Ketu":0.20},
    "physics":                             {"Sun":0.35,"Mercury":0.30,"Mars":0.20,"Saturn":0.15},
    "quantum_computing":                   {"Mercury":0.30,"Rahu":0.30,"Ketu":0.25,"Mars":0.15},
    "research_academia":                   {"Jupiter":0.30,"Mercury":0.30,"Saturn":0.25,"Ketu":0.15},
    "soil_science_agronomy":               {"Saturn":0.35,"Moon":0.30,"Mars":0.20,"Mercury":0.15},
    "statistics_data_science":             {"Mercury":0.40,"Saturn":0.25,"Mars":0.20,"Jupiter":0.15},
    "zoology_animal_science":              {"Moon":0.40,"Mars":0.25,"Jupiter":0.20,"Saturn":0.15},
    # ── MEDICINE / HEALTH ─────────────────────────────────────────────────────
    "ayurveda":                            {"Ketu":0.35,"Moon":0.30,"Jupiter":0.25,"Sun":0.10},
    "cardiac_technology":                  {"Sun":0.35,"Mars":0.25,"Mercury":0.25,"Moon":0.15},
    "clinical_psychology":                 {"Venus":0.35,"Moon":0.25,"Mercury":0.20,"Jupiter":0.20},
    "dentistry":                           {"Mars":0.40,"Mercury":0.25,"Moon":0.20,"Saturn":0.15},
    "health_informatics":                  {"Mercury":0.35,"Moon":0.25,"Jupiter":0.25,"Rahu":0.15},
    "homeopathy":                          {"Ketu":0.30,"Moon":0.30,"Mercury":0.25,"Jupiter":0.15},
    "medicine_mbbs":                       {"Sun":0.30,"Mars":0.25,"Jupiter":0.25,"Moon":0.20},
    "medical_research":                    {"Mars":0.35,"Venus":0.28,"Jupiter":0.22,"Moon":0.15},
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
    "unani_medicine":                      {"Ketu":0.30,"Moon":0.30,"Mercury":0.25,"Jupiter":0.15},
    "veterinary_science":                  {"Moon":0.35,"Mars":0.25,"Jupiter":0.25,"Saturn":0.15},
    "yoga_naturopathy":                    {"Ketu":0.35,"Moon":0.25,"Jupiter":0.25,"Sun":0.15},
    # ── TECHNOLOGY / IT ───────────────────────────────────────────────────────
    "artificial_intelligence":             {"Mercury":0.35,"Rahu":0.25,"Ketu":0.25,"Jupiter":0.15},
    "information_technology":              {"Mercury":0.35,"Rahu":0.25,"Mars":0.25,"Ketu":0.15},
    # ── COMMERCE / MANAGEMENT ─────────────────────────────────────────────────
    "agribusiness_management":             {"Jupiter":0.30,"Saturn":0.25,"Moon":0.25,"Mercury":0.20},
    "business_management":                 {"Jupiter":0.35,"Mercury":0.30,"Saturn":0.20,"Mars":0.15},
    "ca_cma_cs_professional":              {"Mercury":0.40,"Saturn":0.30,"Jupiter":0.20,"Mars":0.10},
    "commerce_accounting":                 {"Mercury":0.35,"Jupiter":0.30,"Saturn":0.25,"Mars":0.10},
    "digital_marketing":                   {"Mercury":0.35,"Rahu":0.30,"Venus":0.20,"Mars":0.15},
    "econometrics":                        {"Mercury":0.40,"Saturn":0.25,"Jupiter":0.20,"Rahu":0.15},
    "educational_technology":              {"Mercury":0.35,"Jupiter":0.30,"Rahu":0.20,"Moon":0.15},
    "entrepreneurship":                    {"Mars":0.30,"Jupiter":0.30,"Mercury":0.25,"Rahu":0.15},
    "finance_banking":                     {"Mercury":0.35,"Jupiter":0.30,"Saturn":0.25,"Mars":0.10},
    "fintech":                             {"Mercury":0.35,"Rahu":0.30,"Jupiter":0.20,"Mars":0.15},
    "food_science_technology":             {"Moon":0.35,"Mercury":0.25,"Mars":0.20,"Venus":0.20},
    "game_design_technology":              {"Mercury":0.30,"Rahu":0.30,"Venus":0.25,"Mars":0.15},
    "healthcare_management":               {"Jupiter":0.30,"Mars":0.26,"Saturn":0.24,"Moon":0.20},
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
    "public_policy":                       {"Jupiter":0.30,"Sun":0.25,"Mercury":0.25,"Saturn":0.20},
    "sanskrit_classical_studies":          {"Jupiter":0.35,"Ketu":0.30,"Mercury":0.25,"Saturn":0.10},
    "sociology_anthropology":              {"Moon":0.30,"Jupiter":0.30,"Mercury":0.25,"Saturn":0.15},
    "speech_language_pathology":           {"Mercury":0.40,"Moon":0.25,"Mars":0.20,"Jupiter":0.15},
    # ── ARTS / DESIGN / MEDIA ─────────────────────────────────────────────────
    "animation_multimedia":                {"Venus":0.35,"Mercury":0.30,"Rahu":0.20,"Mars":0.15},
    "design_ux_product":                   {"Venus":0.35,"Mercury":0.30,"Rahu":0.20,"Mars":0.15},
    "fashion_design":                      {"Venus":0.40,"Mercury":0.25,"Moon":0.20,"Rahu":0.15},
    "film_television_production":          {"Venus":0.35,"Rahu":0.25,"Mercury":0.25,"Moon":0.15},
    "fine_arts":                           {"Venus":0.40,"Moon":0.25,"Mercury":0.20,"Jupiter":0.15},
    "interior_design":                     {"Venus":0.35,"Mercury":0.25,"Moon":0.25,"Saturn":0.15},
    "journalism_media":                    {"Mercury":0.35,"Rahu":0.25,"Moon":0.25,"Venus":0.15},
    "landscape_architecture":              {"Venus":0.30,"Saturn":0.30,"Moon":0.25,"Mercury":0.15},
    "linguistics":                         {"Mercury":0.40,"Jupiter":0.30,"Moon":0.20,"Venus":0.10},
    "literature_languages":                {"Mercury":0.35,"Venus":0.25,"Jupiter":0.25,"Moon":0.15},
    "mass_communication":                  {"Moon":0.35,"Mercury":0.30,"Venus":0.20,"Rahu":0.15},
    "music":                               {"Venus":0.40,"Moon":0.30,"Mercury":0.20,"Jupiter":0.10},
    "performing_arts":                     {"Venus":0.35,"Moon":0.30,"Mercury":0.20,"Jupiter":0.15},
    "photography":                         {"Venus":0.30,"Mercury":0.25,"Rahu":0.25,"Moon":0.20},
    "textile_design":                      {"Venus":0.40,"Mercury":0.25,"Moon":0.20,"Saturn":0.15},
    "textile_technology":                  {"Venus":0.30,"Saturn":0.30,"Mars":0.25,"Mercury":0.15},
    "theatre_drama":                       {"Venus":0.35,"Moon":0.30,"Mercury":0.20,"Jupiter":0.15},
    "visual_communication":                {"Venus":0.35,"Mercury":0.30,"Rahu":0.20,"Moon":0.15},
    # ── PHYSICAL / SPORT ─────────────────────────────────────────────────────
    "physical_education":                  {"Mars":0.40,"Sun":0.30,"Moon":0.20,"Mercury":0.10},
    "sports_science_management":           {"Mars":0.35,"Sun":0.25,"Mercury":0.25,"Jupiter":0.15},
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


# ── LS8 fix: Validate all affinity weight vectors sum to 1.0 ─────────────────
def _validate_affinity_weights() -> None:
    """Called at module load; asserts all BRANCH_PLANET_AFFINITY vectors sum to ~1.0."""
    bad = []
    for fid, weights in BRANCH_PLANET_AFFINITY.items():
        total = sum(weights.values())
        if abs(total - 1.0) > 0.005:
            bad.append(f"{fid}: sum={total:.4f}")
    if bad:
        import warnings
        warnings.warn(f"Affinity weight vectors not summing to 1.0:\n" + "\n".join(bad))

_validate_affinity_weights()

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

    Effective strength (eff_str) is in the range 0.0–2.0+ where 1.0 = minimum required Shadbala.
    With weights summing to 1.0 and eff_str up to ~2.0, the score ranges 0–200.
    Soft-cap is applied downstream by _log_norm_score with _AFFINITY_SOFT_CAP=180.

    Returns:
        dict with:
          affinity_score    : float   — raw score (0–200 range)
          affinity_planets  : dict    — same as affinity_weights (used by gap-boost routines)
          top_planet        : str     — planet with highest weight
          domain            : str     — field domain
    """
    if not affinity_weights:
        # Graceful fallback: no affinity data → use average eff_strength
        avg_eff = (sum(eff_strengths.values()) / len(eff_strengths)) if eff_strengths else 1.0
        score = avg_eff * 70.0
        return {
            "affinity_score": round(score, 2),
            "affinity_planets": {},
            "top_planet": "",
            "domain": domain,
        }

    # Weighted dot product
    score = 0.0
    for planet, weight in affinity_weights.items():
        eff = eff_strengths.get(planet, 0.5)  # default 0.5 if planet data missing
        score += eff * weight * 100.0

    # Dignity-weighted bonus: if the top-affinity planet is at EXALTED/OWN strength
    # (eff_str ≥ 1.40 indicates at-or-near-exaltation level), apply a small multiplier.
    top_planet = max(affinity_weights.items(), key=lambda x: x[1])[0] if affinity_weights else ""
    top_eff = eff_strengths.get(top_planet, 0.5)
    if top_eff >= 1.40:
        score *= 1.08   # 8% uplift for exalted primary karaka
    elif top_eff >= 1.15:
        score *= 1.04   # 4% uplift for own-sign primary karaka

    # LS9 fix: Vargottama top-planet uplift (same sign D1+D9 = doubly strong;
    # classical signal stronger than OWN-sign, nearly as strong as EXALTED).
    vargottama = list(getattr(payload_data, "vargottama_planets", []) or []) if hasattr(compute_branch_affinity_score_llm, "_payload") else []
    # Note: payload_data is not in this function signature — uplift applied by caller
    # via compute_branch_affinity_score_llm_v2 below which receives payload.
    return {
        "affinity_score": round(score, 2),
        "affinity_planets": affinity_weights,
        "top_planet": top_planet,
        "domain": domain,
        "planet_contributions": {p: round(eff_strengths.get(p, 0.5) * w * 100.0, 2)
                                  for p, w in affinity_weights.items()},
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
    "nursing_bsc": {
        "label": "Nursing (B.Sc.)",
        "domain": "medicine",
        "field": "Medical Sciences",
        "track": "Nursing & Patient Care",
        "specialization": "B.Sc. Nursing",
        "niche": "Patient care / ICU / Midwifery / Community health",
        "description": "Nursing practice covering patient care, surgical assistance, and community health",
        "career_signature": ["Hospitals", "Clinics", "Nursing homes", "International healthcare"],
    },
    "pharmacy_bpharm": {
        "label": "Pharmacy (B.Pharm)",
        "domain": "medicine",
        "field": "Medical Sciences",
        "track": "Pharmaceutical Sciences",
        "specialization": "B.Pharm / Pharmaceutical Sciences",
        "niche": "Drug formulation / Clinical trials / Pharmaceutical research / QA",
        "description": "Pharmaceutical sciences covering drug development, formulation, and clinical application",
        "career_signature": ["Pharma companies", "Hospitals", "Research labs", "Drug regulatory bodies"],
    },
    "ayurveda_bams": {
        "label": "Ayurveda (BAMS)",
        "domain": "medicine",
        "field": "Medical Sciences",
        "track": "Traditional Medicine",
        "specialization": "BAMS / Ayurvedic Medicine",
        "niche": "Panchakarma / Herbal medicine / Rasayana / Lifestyle medicine",
        "description": "Classical Ayurvedic medicine covering diagnosis, treatment, and preventive health",
        "career_signature": ["Ayurvedic clinics", "Wellness centers", "Research institutes", "Global wellness sector"],
    },
    "psychology_bsc": {
        "label": "Psychology (B.Sc.)",
        "domain": "medicine",
        "field": "Behavioural Sciences",
        "track": "Mental Health & Behavioural Science",
        "specialization": "B.Sc. Psychology",
        "niche": "Clinical psychology / Counseling / Organizational psychology / Research",
        "description": "Scientific study of human behaviour, cognition, and mental health",
        "career_signature": ["Mental health clinics", "Corporates", "Schools", "Research universities"],
    },
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
        "specialization": "Public Health / Epidemiology / Health Policy",
        "niche": "Epidemiology / Health policy / Biostatistics / Community medicine / Disease prevention",
        "description": "Population-level health management covering epidemiology, health policy, and disease prevention",
        "career_signature": ["WHO", "AIIMS Public Health", "State health departments", "NGOs", "Research institutes"],
    }
}

