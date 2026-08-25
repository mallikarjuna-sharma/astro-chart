"""JyotishAI — BRANCH_PLANET_AFFINITY data and affinity scorer.

PROVENANCE NOTE (2026-08-20, registry-level astrological audit): Field_Affinity.json
was rebuilt as a hand-curated, chart-agnostic intrinsic planetary-signature registry
(213 fields, each vector summing to 1.00) and audited against BPHS's karakatwa
doctrine (Ch. 3) plus Phaladeepika/Saravali as secondary references. Two entries were
adjusted for defensibility during that audit:
  - "physics": changed from Sun-primary to Jupiter-primary. Sun-as-physics rested on a
    loose "Sun = fundamental energy" symbolic reading with no real BPHS anchor (Sun's
    actual karakatwa is soul/authority/government, not literally energy); physics as a
    theoretical/wisdom-oriented discipline sits closer to Jupiter (wisdom, higher
    truths) with Sun retained as a strong secondary. Contrast with "astronomy_astrophysics",
    which correctly keeps Sun primary -- Sun genuinely does mean "the heavenly bodies"
    in classical usage, so Sun-for-astronomy is well-grounded in a way Sun-for-physics
    was not.
  - "architecture": swapped Saturn ahead of Venus (was Venus-primary/Saturn-secondary).
    Architecture retains a strong structural-engineering component (Saturn = structure,
    durability, masonry) alongside its aesthetic-design layer (Venus = arts, beauty);
    since it sits adjacent to civil_engineering in this registry rather than to the pure
    fine-arts fields, Saturn-primary better reflects that. Venus remains a strong
    secondary weight (0.30) and Mars is retained (0.15) for the construction/land
    component -- this is a judgment call, not a hard classical requirement, and either
    ordering is defensible depending on whether "architecture" is being scored as a
    design discipline or a construction-engineering one.

Systemic disclosure (applies across ~40 frontier-tech/aerospace/semiconductor fields --
e.g. aerospace_engineering, astronautical_engineering, satellite_engineering,
blockchain_web3, cybersecurity, quantum_computing, artificial_intelligence, and similar):
these vectors lean on Rahu = aviation/technology/foreign-fields and Ketu =
miniaturization/subtlety/electronics. BPHS itself (predating flight and electronics by
well over a millennium) has no karakatwa chapter entry for either node in this sense --
BPHS's Rahu/Ketu significations are narrower (poison, foreigners, deception, sudden
events for Rahu; moksha, the occult, isolation, hidden knowledge for Ketu). The
tech-sector usage is a 20th-century interpretive extension (the K.N. Rao / B.V. Raman-
era convention), applied consistently across this registry, and near-universal in
contemporary Vedic career-astrology practice -- but it is a different tier of evidence
than, say, "Jupiter = law" (BPHS-exact) or "Venus = arts" (BPHS-exact), and any report
surfacing these fields' astrological rationale to an end user should say so explicitly
rather than presenting all planetary attributions as equally classically settled.
"""
from typing import Dict, List, Tuple, Set, Any, Optional

from pathlib import Path

def _load_branch_planet_affinity() -> Dict[str, Dict[str, float]]:
    """Load BRANCH_PLANET_AFFINITY from Field_Affinity.json, resolved relative to this
    file's own location (not the current working directory), so it works regardless of
    where the engine is invoked from.

    Raises a clear, actionable error if the JSON file is missing or malformed — silently
    falling back to an empty dict would break affinity scoring for every field without
    any visible signal.
    """
    import json

    json_path = Path(__file__).parent / "Field_Affinity.json"
    if not json_path.exists():
        raise FileNotFoundError(
            f"BRANCH_PLANET_AFFINITY data file not found: {json_path}. "
            "This file is required for affinity scoring; restore it from version control "
            "or re-export it from the original BRANCH_PLANET_AFFINITY dict literal."
        )
    try:
        with open(json_path, "r", encoding="utf-8") as _f:
            data = json.load(_f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"BRANCH_PLANET_AFFINITY data file is malformed JSON: {json_path} "
            f"(line {exc.lineno}, col {exc.colno}): {exc.msg}"
        ) from exc

    if not isinstance(data, dict) or not data:
        raise ValueError(
            f"BRANCH_PLANET_AFFINITY data file {json_path} did not contain a non-empty "
            f"JSON object; got {type(data).__name__}."
        )

    # "_schema" is a metadata block (planet_order, normalization, field_count, ...), not a
    # field's planetary-affinity vector -- it must not be treated as one of the 213 field
    # entries. Its values are a mix of a list, a string, an int, and bools, so leaving it in
    # here would make _validate_affinity_weights() try to sum() over that mix and blow up
    # with "TypeError: unsupported operand type(s) for +: 'int' and 'list'".
    data = {key: value for key, value in data.items() if key != "_schema"}
    if not data:
        raise ValueError(
            f"BRANCH_PLANET_AFFINITY data file {json_path} contained only a '_schema' key "
            "and no actual field affinity vectors."
        )
    return data


BRANCH_PLANET_AFFINITY: Dict[str, Dict[str, float]] = _load_branch_planet_affinity()


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
    """audit A-1: detect duplicate top-level field-ID keys inside Field_Affinity.json.

    BRANCH_PLANET_AFFINITY now loads from Field_Affinity.json rather than a Python dict
    literal (see _load_branch_planet_affinity below). json.load() silently keeps the last
    occurrence of a repeated key just like Python dict literals do, so duplicates can't be
    detected by inspecting the resulting dict — this re-parses the raw JSON with an
    object_pairs_hook that sees every key occurrence, including repeats, before the
    standard loader collapses them.
    """
    import json

    dupes: List[str] = []
    json_path = Path(__file__).parent / "Field_Affinity.json"
    try:
        with open(json_path, "r", encoding="utf-8") as _f:
            raw_text = _f.read()
    except OSError:
        return dupes

    def _find_dupes_in_pairs(pairs):
        seen: Set[str] = set()
        for key, _value in pairs:
            if key in seen:
                dupes.append(key)
            seen.add(key)
        return dict(pairs)

    try:
        json.loads(raw_text, object_pairs_hook=_find_dupes_in_pairs)
    except json.JSONDecodeError:
        # Malformed JSON is already caught with a clear error by
        # _load_branch_planet_affinity(); nothing further to report here.
        return dupes
    return dupes


# ── LS8 fix / audit A-3: raising validator (was: sum-only, warnings.warn only) ────────────
def _validate_affinity_weights() -> None:
    """Called at module load; validates BRANCH_PLANET_AFFINITY structurally and raises on any
    violation rather than silently warning. Checks:
      - no duplicate dict-literal keys (A-1)
      - every vector sums to 1.0 (±0.005)
      - every vector is non-empty
      - every planet name is one of the 9 canonical planets
      - every weight is in [0, 1] (0.0 is a legitimate "no affinity" weight, not an error --
        many fields in the 213-entry registry intentionally zero out one or more planets)
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
            if not (0.0 <= weight <= 1.0):
                errors.append(f"{fid}: weight for {planet} out of [0,1] range: {weight}")

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
    NOT re-derived here as a fresh "exalted-ish" bonus from eff-strength thresholds — it is
    already folded into `eff_strengths` by `_compute_eff_strengths`, so a second independent
    dignity read at this layer would double-count that signal (audit D-1/D-2).

    CORRECTION (2026-08-22 audit): this docstring previously also claimed the downstream
    `apply_vargottama_affinity_uplift` call was therefore non-duplicative ("applied once,
    downstream"). That was not accurate: `_compute_eff_strengths` already multiplies a
    Vargottama planet's strength by `var_mod` (1.13x) BEFORE it ever reaches this dot
    product, so `eff_strengths` going into `score` above is already Vargottama-inflated for
    that planet. `apply_vargottama_affinity_uplift` then applies its own +6% on top of that
    already-inflated `affinity_score` — the same Vargottama fact credited twice through two
    multiplicative paths. `apply_vargottama_affinity_uplift` now applies a correlation
    discount (halving its uplift's deviation from 1.0, matching this codebase's established
    discount pattern) rather than the full +6% on top of the already-baked-in 1.13x.

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

    CORRECTION (2026-08-22 audit): the `eff_strengths` this uplift's `result`
    was already computed from has itself already been multiplied by
    `var_mod=1.13` for a Vargottama planet (astro.py::_compute_eff_strengths),
    so applying the full +6% here on top double-counts the same Vargottama
    fact. Rather than remove this uplift outright, halve its deviation from
    1.0 (correlation discount, matching this codebase's established pattern)
    so the double-counted portion is reduced rather than fully doubled.
    """
    top = result.get("top_planet", "")
    if top and top in vargottama_planets:
        result = dict(result)
        _discounted_uplift = 1.0 + (1.06 - 1.0) * 0.5
        result["affinity_score"] = round(result["affinity_score"] * _discounted_uplift, 2)
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
