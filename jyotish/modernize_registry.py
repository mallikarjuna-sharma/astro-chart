import json
import random

# ==============================================================================
# MODERNIZATION VOCABULARY BY DOMAIN
# ==============================================================================
MODERN_LEXICON = {
    "engineering": {
        "track_prefixes": ["Autonomous", "Sustainable", "Next-Gen", "Smart", "Advanced"],
        "niches": ["Edge AI", "Digital Twins", "IoT Integration", "Quantum Sensing", "Sustainable Materials", "Robotic Automation"],
        "careers": ["DeepTech Startups", "Global R&D Labs", "Tesla", "NVIDIA", "SpaceX", "Sustainable Infra Corps"]
    },
    "technology": {
        "track_prefixes": ["Decentralized", "Cognitive", "Quantum-Safe", "Generative"],
        "niches": ["LLM Architecture", "Zero-Knowledge Proofs", "Cloud-Native Infrastructure", "Post-Quantum Cryptography", "Web3 Systems"],
        "careers": ["OpenAI", "Anthropic", "Google DeepMind", "Palantir", "Cloudflare", "Web3 Foundations"]
    },
    "commerce": {
        "track_prefixes": ["FinTech &", "Algorithmic", "ESG-Driven", "Data-Driven"],
        "niches": ["High-Frequency Trading", "Blockchain Accounting", "ESG Risk Modeling", "DeFi Architecture", "Predictive Analytics"],
        "careers": ["Stripe", "BlackRock Quant", "Binance", "Big 4 Tech Consulting", "FinTech Unicorns"]
    },
    "science": {
        "track_prefixes": ["Computational", "Applied", "Synthetic", "Translational"],
        "niches": ["CRISPR Genomics", "Bioinformatics", "Materials Informatics", "Astro-statistics", "Climate Modeling"],
        "careers": ["ISRO", "CERN", "DeepMind Science", "Biotech Startups", "Global Climate Consortia"]
    },
    "medicine": {
        "track_prefixes": ["Precision", "Digital", "Translational", "Robotic"],
        "niches": ["Telehealth Architecture", "Neural Interfaces", "Robotic Surgery", "Personalized Genomics", "AI Diagnostics"],
        "careers": ["Neuralink", "Intuitive Surgical", "Mayo Clinic AI", "Digital Health Startups", "WHO Tech Taskforce"]
    },
    "law": {
        "track_prefixes": ["Cyber &", "Tech-Policy", "Corporate Tech", "Algorithmic"],
        "niches": ["AI Governance", "Smart Contract Jurisprudence", "Data Privacy Law", "Space Law", "IP in Generative AI"],
        "careers": ["Tech Policy Think Tanks", "EFF", "Corporate AI Counsel", "Cybercrime Tribunals"]
    },
    "arts": {
        "track_prefixes": ["Immersive", "Algorithmic", "Interactive", "Digital"],
        "niches": ["AR/VR Experience Design", "Generative Art Prompting", "UI/UX Micro-interactions", "Spatial Computing"],
        "careers": ["Meta Reality Labs", "Epic Games", "Creative AI Agencies", "Global UX Studios"]
    },
    "humanities": {
        "track_prefixes": ["Digital", "Computational", "Cognitive", "Applied"],
        "niches": ["AI Ethics & Alignment", "Computational Linguistics", "Behavioral Data Science", "Societal Tech Impacts"],
        "careers": ["AI Safety Institutes", "UX Research", "Tech Policy Boards", "Global NGOs"]
    },
    "agriculture": {
        "track_prefixes": ["Precision", "Agri-Tech &", "Climate-Resilient"],
        "niches": ["Drone Crop Surveying", "Hydroponic Automation", "Synthetic Biology", "IoT Soil Monitoring"],
        "careers": ["Agri-Tech Unicorns", "Climate Action Orgs", "Vertical Farming Startups", "FAO Tech Wing"]
    }
}

# Fallback for domains not explicitly mapped (e.g., media, public, interdisciplinary)
FALLBACK_LEXICON = {
    "track_prefixes": ["Modern", "Data-Informed", "Tech-Enabled", "Next-Gen"],
    "niches": ["Digital Transformation", "AI Integration", "Predictive Modeling", "Global Strategy"],
    "careers": ["Global Tech Firms", "Innovative Startups", "Policy Think Tanks", "Strategy Consulting"]
}

def modernize_branch(branch_id: str, data: dict) -> dict:
    """Overhauls a single branch dictionary with modern terminology."""
    domain = data.get("domain", "interdisciplinary")
    lexicon = MODERN_LEXICON.get(domain, FALLBACK_LEXICON)
    
    original_label = data.get("label", branch_id.replace("_", " ").title())
    original_field = data.get("field", "Specialized Field")
    
    # 1. Modernize Track
    prefix = random.choice(lexicon["track_prefixes"])
    data["track"] = f"{prefix} {original_field}"
    
    # 2. Modernize Specialization
    data["specialization"] = f"Advanced {original_label} & {random.choice(lexicon['niches'])}"
    
    # 3. Modernize Niche (Pick 3 unique niches)
    selected_niches = random.sample(lexicon["niches"], min(3, len(lexicon["niches"])))
    data["niche"] = " / ".join(selected_niches)
    
    # 4. Modernize Description
    data["description"] = (
        f"Next-generation application of {original_label.lower()}, focusing on "
        f"{selected_niches[0].lower()} and {selected_niches[1].lower()} to solve complex modern challenges."
    )
    
    # 5. Modernize Career Signatures
    base_careers = random.sample(lexicon["careers"], min(3, len(lexicon["careers"])))
    if "career_signature" in data and isinstance(data["career_signature"], list):
        # Keep 1 or 2 legacy top-tier employers, add modern ones
        legacy_top = data["career_signature"][:2]
        data["career_signature"] = legacy_top + base_careers + ["High-Growth Tech Startups"]
    else:
        data["career_signature"] = base_careers
        
    # 6. Modernize Tier Map (UG, PG, PhD)
    if "tier_map" in data:
        for level in ["UG", "PG", "PhD"]:
            if level in data["tier_map"]:
                data["tier_map"][level]["niche"] = f"{random.choice(lexicon['niches'])} / Modern {original_field}"

    # 7. Strip planet_affinity to match v11.0 schema
    if "planet_affinity" in data:
        del data["planet_affinity"]

    return data

def main():
    input_file = "india_course_registry_no_planets.json"
    output_file = "india_course_registry_v11.json"
    
    print(f"Loading legacy registry from {input_file}...")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            registry = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {input_file}.")
        return

    # Update metadata
    print("Upgrading metadata to v11.0_engine_aligned...")
    if "_registry_meta" in registry:
        registry["_registry_meta"]["version"] = "v11.0_engine_aligned"
        registry["_registry_meta"]["generated_year"] = "2026"
    
    branches = registry.get("branches", {})
    total = len(branches)
    
    print(f"Found {total} branches. Applying modern lexicons by domain...")
    
    # Modernize each branch
    for branch_id, branch_data in branches.items():
        branches[branch_id] = modernize_branch(branch_id, branch_data)
        
    registry["branches"] = branches

    # Save output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccess! Modernized {total} branches.")
    print(f"Saved highly-optimized v11.0 registry to: {output_file}")

if __name__ == "__main__":
    main()