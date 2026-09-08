"""Shared helpers for separated field-determination astrology modules."""
from __future__ import annotations

import math as _math
from typing import Any, Dict, List


FIELD_PRIORITY_GROUPS: Dict[str, List[str]] = {
    "life_science": [
        "medicine_mbbs",
        "biomedical_engineering",
        "medical_research",
        "clinical_psychology",
        "neuroscience",
        "psychiatry",
        "public_health",
        "bioinformatics",
        "biotechnology_biochemical_engineering",
        "biotechnology_bsc",
        "molecular_biology_genetics",
        "healthcare_management",
        "pharmacy",
        "forensic_science",
    ],
    "governance_service": [
        "public_policy",
        "civil_services",
        "political_science",
        "development_studies",
        "public_health",
        "criminal_law",
        "law_llb",
        "intelligence_security_studies",
        "defence_strategic_studies",
        "environmental_law",
        "environmental_studies_interdisciplinary",
    ],
    "space_aerospace": [
        "aerospace_engineering",
        "space_systems_engineering",
        "rocket_propulsion",
        "satellite_engineering",
        "astronautical_engineering",
        "space_sciences_engineering",
        "space_materials",
        "earth_observation_remote_sensing",
        "planetary_science",
        "astronomy_astrophysics",
    ],
}

# Gap-8 (audit 2026-07): registry of astro facts that are scored in more than
# one place (multiple method files and/or engine.py gap-boosts), so the
# "5-6 independent methods agree" convergence bonus is partly rewarding the
# same underlying fact restated rather than genuinely independent testimony.
#
# Audit follow-up (2nd pass): investigated whether each row is closeable by
# "delete the duplicate scoring, keep one owner" as originally envisioned.
# Conclusion: for career/field determination specifically, most of these ARE
# legitimately multi-method by design -- e.g. a dusthana-lord affliction is a
# real weakness that KP, KNRao, Jaimini, and Parashara each independently
# care about from their own technique's perspective; deleting that check from
# four of five methods would make them astrologically *less* complete, not
# more correct, purely to reduce a statistical redundancy that the
# correlation discount below already exists to compensate for. Verified each
# row's underlying DATA (not just the scoring decision) is drawn from a
# single shared source rather than independently re-derived per method:
#   - dusthana_lord_penalty:  single shared boosts._dusthana_lord_penalty()
#   - chandra_lagna_h10_lord: single shared common.chandra_lagna_h10_lord() (Gap-14)
#   - cluster_bonus:          single shared boosts._life_science_cluster_bonus() /
#                              _space_aerospace_cluster_bonus()
#   - d10_h10_occupancy:      knrao/kp/parashara already read the single shared
#                              payload_data.d10_house_occupancy; engine.gap_boost's
#                              _d10_h10_bonus() used to independently recompute
#                              the same fact from d10_chart in parallel -- fixed
#                              to accept and prefer the shared occupancy dict
#                              (see boosts._d10_h10_bonus's d10_occupancy param).
# So the real drift risk (two code paths silently computing the same fact
# differently) is now closed for all four rows. What remains -- multiple
# methods each applying their OWN weight to the same shared fact -- is by
# design, not a bug, and correlation_discount_factor() below is the correct
# place to account for it (not deletion from individual methods).
#
# house_signification_bonus (audit follow-up, 2026-08-17): jyotish.boosts.
# _house_signification_bonus(domain, field_affinity, house_lords, planet_house,
# planets_d1, payload_data, scale, cap) is called by SIX of the nine voting
# methods -- knrao.py, kp.py, jaimini.py, parashara.py, dashamsha.py, and
# structural_patterns.py (structural_patterns.py's own module docstring
# already flags the dashamsha/kp reuse; audit found knrao/jaimini/parashara
# independently call the identical shared function too). Verified each call
# site passes the SAME effective inputs per chart+field, not independently
# re-derived data: domain and field_affinity are the method's own passed-
# through arguments (same values across all six for a given chart+field
# combination), house_lords is payload_data.house_lords unmodified in every
# caller, and planet_house is payload_data.planet_house unmodified in every
# caller EXCEPT dashamsha (local alias `_ph_d1`, same underlying D1 dict) and
# kp (local alias `_kp_ph_all`, confirmed by reading kp.py to be
# `payload_data.planet_house` verbatim -- KP does NOT substitute its own
# sub-lord-derived house mapping here despite the method's KP framing). Only
# `scale`/`cap` differ per caller (4-5 / 8-20), which changes each method's
# own weighting of the shared fact but not the underlying fact being scored.
# This is exactly the "single shared source, multiple methods each applying
# their own weight" pattern the four rows above already established as the
# correct target for correlation_discount_factor(), not deletion from any
# individual method file.
SIGNAL_REGISTRY: Dict[str, List[str]] = {
    "d10_h10_occupancy":        ["knrao", "kp", "parashara", "dashamsha", "engine.gap_boost:d10_h10"],
    "dusthana_lord_penalty":    ["knrao", "kp", "jaimini", "parashara", "engine.gap_boost"],
    "chandra_lagna_h10_lord":   ["knrao", "kp", "jaimini", "parashara"],
    "cluster_bonus":            ["knrao", "jaimini", "parashara", "engine.gap_boost"],
    "house_signification_bonus": ["knrao", "kp", "jaimini", "parashara", "dashamsha", "structural_patterns"],
}

# Number of "convergence layers" the T3-A grade currently compares (KNRao, KP,
# Jaimini, Parashara, Dashamsha, Sudarshana). Kept as a constant here (rather
# than importing engine.py, which would create a circular import) so the
# discount formula below and engine.py's convergence block stay in lockstep;
# update both if a layer is ever added/removed.
# Phase-1 remediation (2026-08): bumped 6->7 with the addition of siddhamsha
# (D24) as a first-class voting method. Kept in lockstep with
# METHOD_WEIGHTS/METHOD_SCORE_CAPS in field_methods/__init__.py and common.py.
# Phase-2 remediation (2026-08): bumped 7->8 with the addition of
# shashtiamsha (D60) as a voting method (navamsha/D9 remains a post-blend
# multiplier, not a counted "layer", per its confirmatory role).
# Stage 1 (2026-08): bumped 8->9 with the addition of structural_patterns
# (D1 house-occupancy clustering) as a voting method.
CONVERGENCE_LAYER_COUNT: int = 9


def correlation_discount_factor(total_layers: int = CONVERGENCE_LAYER_COUNT) -> float:
    """Data-derived replacement for the previously hardcoded 0.6 constant.

    Gap-8 close-out (audit 2026-07): the old `_CORRELATION_DISCOUNT = 0.6` in
    engine.py was a fixed magic number, disconnected from SIGNAL_REGISTRY, so
    it could never improve as duplicated facts got collapsed to a single
    owner. This derives the discount directly from the registry: for each
    tracked fact, `(methods_sharing_it - 1) / (total_layers - 1)` estimates
    what fraction of that fact's cross-method "agreement" is structural
    (shared inputs) rather than independent corroboration. Averaging across
    all tracked facts gives an overall duplication estimate; the discount is
    `1 - 0.5 * avg_duplication`, clamped to a sane band.

    As rows are removed from SIGNAL_REGISTRY (i.e. a fact is refactored to
    have exactly one owning method), avg_duplication falls and this discount
    rises toward 1.0 automatically — no manual recalibration needed. With the
    registry's current 5 rows (house_signification_bonus added 2026-08-17)
    this evaluates to ~0.76, up from ~0.65 with 4 rows because the newly-
    added row is shared by 6 of 9 methods -- the widest reuse of any tracked
    fact. This is an intentional strengthening of the discount to reflect
    genuinely higher cross-method redundancy that was previously entirely
    uncompensated, not a recalibration for its own sake.
    """
    if not SIGNAL_REGISTRY or total_layers <= 1:
        return 1.0
    fractions = []
    for methods in SIGNAL_REGISTRY.values():
        n = len(methods)
        frac = (n - 1) / float(total_layers - 1)
        fractions.append(min(1.0, max(0.0, frac)))
    avg_duplication = sum(fractions) / len(fractions)
    discount = 1.0 - 0.5 * avg_duplication
    return round(max(0.4, min(0.9, discount)), 4)

METHOD_SCORE_CAP: float = 30.0

# Gap-1 (audit 2026-07) fix: single source of truth for per-method normalization
# caps. Previously __init__.py kept its own _METHOD_SCORE_CAPS while each method
# file passed a *different* cap to method_result (knrao 80 vs 30, kp 80 vs 60,
# jaimini 80 vs 30) — the bundle silently overwrote the method's own normalized
# score with a contradictory one. Both sides now import this dict.
#
# Recalibration (2026-07, "fix all gaps" pass): the caps above were arbitrary
# and sat well below each method's own declared rubric ceiling (sum of its
# core+support+validation rubric_section caps, from build_score_rubric calls
# in each method file). knrao's ceiling is 60+20+20=100 but was capped at 30;
# jaimini's is 60+25+20=105 but was capped at 30. Since raw scores routinely
# approach their rubric ceiling, both methods saturated their normalized_score
# at 100 for the large majority of charts, destroying rank differentiation
# between fields precisely where the bundle needs it most.
#
# Every method now uses its own declared positive-section ceiling as the cap,
# so "100 normalized" means the same thing across methods: this method fired
# every one of its own scoring rubric sections at full strength. This is the
# only self-consistent choice without a curated outcome dataset to calibrate
# against (see WORLDCLASS_GAP_ANALYSIS.md 6.1 / DEEP_AUDIT item 5.1 — no
# backtesting corpus exists yet). Verify each method file's rubric_section
# calls before changing these; they must stay in sync.
METHOD_SCORE_CAPS: Dict[str, float] = {
    "knrao":      100.0,  # core 60 + support 20 + validation 20
    "kp":          85.0,  # core 40 + support 25 + validation 20
    "jaimini":    105.0,  # core 60 + support 25 + validation 20
    "parashara":   85.0,  # core 40 + support 25 + validation 20
    "dashamsha":   85.0,  # core 40 + support 25 + validation 20
    # Architecture fix (audit): Sudarshana Chakra promoted from a bolt-on,
    # unweighted convergence-only layer (previously computed only inside
    # engine.py's separate confidence-convergence step, with no vote in this
    # bundle) to a first-class 6th method here. score_sudarshana() already
    # returns its score on a native 0-100 scale (3 layers x up to 30 pts +
    # up to 40 pts convergence bonus, clamped), so its cap is 100 directly --
    # unlike the other methods it has no separate core/support/validation
    # rubric split to sum.
    "sudarshana": 100.0,
    # Phase-1 remediation (2026-08 gap-audit): Siddhamsha (D24) promoted from
    # a confirmation-only helper (independent_vote: False, never reaching
    # final_score) to a 7th first-class method. BPHS's dedicated vidya varga
    # — core 40 + support 25 + validation 20 = 85, matching kp/parashara/
    # dashamsha's convention (rubric ceiling sum, not an arbitrary pick).
    "siddhamsha": 85.0,
    # Phase-2 remediation (2026-08 gap-audit): Shashtiamsha (D60) added as an
    # 8th voting method. score_d60_vote() already returns its score on a
    # native 0-100 scale (deity-quality weighted average), so its cap is 100
    # directly -- same convention as sudarshana.
    "shashtiamsha": 100.0,
    # Stage 1 (Astro-OS v3 gap-audit implementation plan, 2026-08):
    # Structural Pattern Analysis (D1 house-occupancy clustering:
    # kendra/trikona dominance + stellium concentration) added as a 9th
    # voting method. Cap = its own declared rubric ceiling, same convention
    # as knrao/kp/jaimini/parashara/dashamsha/siddhamsha: core 40 + support
    # 25 + validation 20 = 85.
    "structural_patterns": 85.0,
    # GAP FIX (2026-08-18, audit item A): Gochara (transit) timing tier added
    # as a 10th voting method. Cap = its own declared rubric ceiling: core 40
    # + support 15 + validation 15 = 70; capped lower than knrao/jaimini's
    # 100-105 -- this method only ever contributes house-level (whole-sign)
    # transit hits for two planets over one house/sign locus, a much
    # narrower evidence surface than the full-chart methods.
    "gochara": 70.0,
}

# Correlation-group bookkeeping: siddhamsha (D24) is its own chart source,
# independent of the D1-derived methods (knrao/parashara) and of D10
# (dashamsha), so it intentionally does NOT join METHOD_DEPENDENCY_GROUPS'
# "d1_synthesis" pairing — see jyotish/evidence_integrity.py.


# Gap-18b (audit 2026-07, generalized fix): knrao.py, kp.py, jaimini.py,
# parashara.py, and dashamsha.py each independently derived the text that
# every keyword-gate check (_wm(kw, label) calls scattered across boosts.py /
# constants.py / these method files themselves -- nakshatra-career fit,
# Rahu-house career direction, yoga-domain fit, exalted-domain, karakamsha-
# domain bonuses) matches against, using ONLY `field_id.replace("_", " ")`.
# jyotish/tests/test_keyword_coverage.py already measured the consequence:
# ~55 registry fields share zero vocabulary with any keyword list purely
# because their bare field_id doesn't happen to contain the expected
# substring -- e.g. "international_relations" and "political_science" don't
# contain "law", so they silently receive none of these bonuses no matter
# how strong the underlying planetary support is, while a same-strength
# sibling like "international_law" does. This was diagnosed concretely on a
# real chart: international_relations/political_science scored comparably
# on raw affinity-weighted effective strength to international_law but
# never appeared anywhere in the top-35, purely a downstream scoring-gate
# artifact rather than an astrological difference.
#
# Fix: build the gate text from field_id AND the registry's own descriptive
# text (label/field/track/specialization/niche/description) when a registry
# entry is supplied, so a field is reachable by a keyword cluster if EITHER
# its id OR its human-written description shares vocabulary with it. This is
# a one-time, per-field-call enrichment (not a per-field keyword-list edit),
# so every current and future field benefits automatically -- it does not
# special-case international_relations/political_science or any other
# specific field_id. Falls back to the old field_id-only text when no
# registry entry is passed, so existing callers/tests without the new
# optional argument keep their exact prior behaviour.
def build_gate_text(field_id: str, field_entry: Dict[str, Any] = None) -> str:
    """Build the searchable text used by keyword-gate checks for a field.

    Combines the bare field_id (e.g. "international_relations" ->
    "international relations") with the registry's descriptive fields when
    available, so keyword gates hand-curated against one vocabulary (e.g.
    "law", "diplomacy", "foreign policy") can still fire for a field whose
    id alone doesn't contain that word but whose registry description does.
    """
    base = field_id.replace("_", " ").lower()
    if not field_entry:
        return base
    extra_parts = [
        field_entry.get("label", ""),
        field_entry.get("field", ""),
        field_entry.get("track", ""),
        field_entry.get("specialization", ""),
        field_entry.get("niche", ""),
        field_entry.get("description", ""),
    ]
    extra = " ".join(str(p) for p in extra_parts if p).lower()
    return f"{base} {extra}".strip()


def surya_lagna_h10_lord(planets_d1: Dict) -> str:
    """Lord of the 10th sign counted from the Sun's sign (Surya Lagna H10).

    §9 remediation (2026-08-19): the spec's named K.N. Rao technique is a
    TRIPLE confirmation -- 10th house counted from Lagna, Moon (Chandra
    Lagna), AND Sun (Surya Lagna) together. Only the Lagna/Moon halves lived
    in knrao.py; the Sun-based version existed only inside sudarshana.py's
    own internal H10-from-Sun-sign logic, with no shared helper -- so the
    single spec technique was split across two files and knrao.py itself
    never performed the full triple check. Mirrors chandra_lagna_h10_lord()
    immediately below exactly, just anchored on the Sun instead of the Moon.
    """
    from jyotish.constants import _SIGN_LORD, _SIGN_NUM
    signs = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda x: x[1])]
    sun_sign = ((planets_d1 or {}).get("Sun") or {}).get("sign", "")
    if not sun_sign or sun_sign not in _SIGN_NUM:
        return ""
    return _SIGN_LORD.get(signs[(_SIGN_NUM[sun_sign] - 1 + 9) % 12], "")


def chandra_lagna_h10_lord(planets_d1: Dict) -> str:
    """Lord of the 10th sign counted from the Moon's sign (Chandra Lagna H10).

    Gap-14 (audit 2026-07) fix: this helper was re-implemented with copy-paste
    variations inside knrao.py, kp.py, jaimini.py and parashara.py. Centralised
    here so the four methods cannot drift.
    """
    from jyotish.constants import _SIGN_LORD, _SIGN_NUM
    signs = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda x: x[1])]
    moon_sign = ((planets_d1 or {}).get("Moon") or {}).get("sign", "")
    if not moon_sign or moon_sign not in _SIGN_NUM:
        return ""
    return _SIGN_LORD.get(signs[(_SIGN_NUM[moon_sign] - 1 + 9) % 12], "")


# Phase-4 remediation (2026-08 gap-audit): intelligence/education-specific
# yoga detection, previously absent from every method file (only generic
# `detected_yogas` passed through from jyotish.astro were consulted, and
# that list is not education-specific). Centralised here so Parashara and
# Jaimini can both reference it without duplicating the sign/house logic.
_KENDRA_HOUSES_Y = {1, 4, 7, 10}
_TRIKONA_HOUSES_Y = {1, 5, 9}
_STRONG_DIGNITIES_Y = {"EXALTED", "OWN", "OWN_SIGN", "MOOLATRIKONA"}


def detect_vidya_yogas(
    planets_d1: Dict[str, Dict[str, Any]],
    planet_house: Dict[str, int],
    planet_dignities: Dict[str, str],
) -> Dict[str, Any]:
    """Detect classical intelligence/education yogas from the D1 chart.

    Returns {"saraswati_yoga": bool, "budh_aditya_yoga": bool, "notes": [...]}.

    Saraswati Yoga (simplified, commonly-cited form): Mercury, Jupiter and
    Venus are either conjunct in one house or mutually in kendra/trikona
    from each other, with at least one of the three in a strong dignity
    (own/exalted/moolatrikona) — classically bestows learning, eloquence,
    and scholarly aptitude.

    Budh-Aditya Yoga: Sun and Mercury conjunct in the same house (not
    counting deep combustion as disqualifying here, since even a combust
    Budh-Aditya is still classically read as sharpening intellect, just
    with reduced material visibility) — bestows intelligence and analytical
    capacity.
    """
    notes: List[str] = []
    mercury_h = planet_house.get("Mercury", 0)
    jupiter_h = planet_house.get("Jupiter", 0)
    venus_h = planet_house.get("Venus", 0)
    sun_h = planet_house.get("Sun", 0)

    saraswati = False
    if mercury_h and jupiter_h and venus_h:
        houses = {mercury_h, jupiter_h, venus_h}
        conjunct = len(houses) == 1
        mutual_kendra_trikona = all(
            ((b - a) % 12) + 1 in _KENDRA_HOUSES_Y | _TRIKONA_HOUSES_Y
            for a in houses for b in houses if a != b
        ) if len(houses) > 1 else True
        any_strong = any(
            str(planet_dignities.get(p, "")).upper() in _STRONG_DIGNITIES_Y
            for p in ("Mercury", "Jupiter", "Venus")
        )
        if (conjunct or mutual_kendra_trikona) and any_strong:
            saraswati = True
            notes.append(
                f"Saraswati Yoga: Mercury/Jupiter/Venus "
                f"{'conjunct' if conjunct else 'in mutual kendra/trikona'} "
                f"with at least one in strong dignity — supports scholarship/eloquence."
            )

    budh_aditya = bool(mercury_h and sun_h and mercury_h == sun_h)
    if budh_aditya:
        notes.append("Budh-Aditya Yoga: Sun-Mercury conjunction — sharpens intellect/analytical capacity.")

    return {"saraswati_yoga": saraswati, "budh_aditya_yoga": budh_aditya, "notes": notes}


# ── Stage 2 (Astro-OS v3 gap-audit implementation plan, 2026-08): Pattern
# Ontology Layer ────────────────────────────────────────────────────────────
# Gap being closed: detect_vidya_yogas() above hard-codes exactly two
# classical combinations (Saraswati, Budh-Aditya), both education-specific.
# Every other classically-recognised planetary-pair combination relevant to
# career/field determination (Guru-Mangal for engineering/strategy/law,
# Shukra-Budha for arts/design/commerce, Shani-Mangal for engineering/
# defense/manufacturing, Chandra-Mangal for business/entrepreneurship,
# Guru-Shukra for finance/teaching/creative sectors) was entirely absent --
# not a scoring bug, a genuine missing signal class. Rather than hand-coding
# five more near-duplicate detection functions (the same copy-paste-drift
# problem chandra_lagna_h10_lord's docstring above already names), this is a
# single declarative ontology table plus one generic detector, so adding a
# 6th/7th/8th combination in future is a data-table edit, not new code.
#
# Design: each entry is DOMAIN-TAGGED. The detector reports every yoga that
# is structurally PRESENT on the chart regardless of the field being scored
# (methods want to see "what combinations exist" for the trace/audit trail),
# but a yoga's bonus is only applied by the caller when field_affinity
# concretely supports at least one of the yoga's constituent planets --
# using the SAME field-affinity-gate convention structural_patterns.py/
# siddhamsha.py already established, not a flat domain-keyword string match
# (keyword gates are the exact class of bug documented above build_gate_text
# -- ~55 registry fields sharing zero vocabulary with a hand-picked keyword
# list). This keeps the ontology backward-compatible with existing callers:
# detect_vidya_yogas() is untouched, still used exactly as before.
_YOGA_ONTOLOGY: List[Dict[str, Any]] = [
    {
        "name": "guru_mangal_yoga",
        "planets": ("Jupiter", "Mars"),
        "mode": "conjunct_or_kendra",
        "bonus": 6.0,
        "label": "Guru-Mangal Yoga",
        "meaning": "Jupiter-Mars combination -- supports engineering, strategy, "
                   "law/litigation, sports/defense: disciplined execution of expansive vision.",
    },
    {
        "name": "shukra_budha_yoga",
        "planets": ("Venus", "Mercury"),
        "mode": "conjunct",
        "bonus": 6.0,
        "label": "Shukra-Budha Yoga",
        "meaning": "Venus-Mercury conjunction -- supports arts, design, commerce, "
                   "communication/media: aesthetic sense paired with analytical articulation.",
    },
    {
        "name": "shani_mangal_yoga",
        "planets": ("Saturn", "Mars"),
        "mode": "conjunct",
        "bonus": 6.0,
        "label": "Shani-Mangal Yoga",
        "meaning": "Saturn-Mars conjunction -- supports engineering, manufacturing, "
                   "surgery, defense: disciplined, sustained application of raw drive.",
    },
    {
        "name": "chandra_mangal_yoga",
        "planets": ("Moon", "Mars"),
        "mode": "conjunct",
        "bonus": 6.0,
        "label": "Chandra-Mangal Yoga",
        "meaning": "Moon-Mars conjunction -- classically a wealth/business-acumen "
                   "combination: supports entrepreneurship, real estate, trading, finance.",
    },
    {
        "name": "guru_shukra_yoga",
        "planets": ("Jupiter", "Venus"),
        "mode": "conjunct_or_kendra_trikona",
        "bonus": 7.0,
        "label": "Guru-Shukra Yoga",
        "meaning": "Jupiter-Venus combination -- supports finance, teaching/academia, "
                   "luxury/creative sectors, counseling: wisdom paired with refinement.",
    },
]


def _yoga_houses_related(mode: str, house_a: int, house_b: int) -> bool:
    """Positional test shared by every ontology entry: conjunct (same house),
    kendra (1/4/7/10 apart), or kendra-or-trikona (1/4/5/7/9/10 apart) from
    each other. Mirrors the same house-distance convention detect_vidya_yogas
    already uses for Saraswati Yoga above.
    """
    if house_a <= 0 or house_b <= 0:
        return False
    if mode == "conjunct":
        return house_a == house_b
    distance = ((house_b - house_a) % 12) + 1
    if mode == "conjunct_or_kendra":
        return house_a == house_b or distance in _KENDRA_HOUSES_Y
    if mode == "conjunct_or_kendra_trikona":
        return house_a == house_b or distance in (_KENDRA_HOUSES_Y | _TRIKONA_HOUSES_Y)
    return False


def detect_career_yogas(
    planet_house: Dict[str, int],
    field_affinity: Dict[str, float] = None,
    field_affinity_gate: float = 0.10,
) -> Dict[str, Any]:
    """Generic detector over `_YOGA_ONTOLOGY`: reports which classical
    planetary-pair combinations are structurally present on this D1 chart,
    and -- separately -- which of those are relevant to the field currently
    being scored (at least one constituent planet has field_affinity >=
    field_affinity_gate for this field, the same 0.10 threshold Parashara's
    own vidya-karaka loop already uses just above this function's call site).

    Returns:
        {
          "active": {yoga_name: {"label":..., "meaning":..., "relevant": bool,
                                  "bonus": float (0.0 if not relevant)}},
          "total_bonus": float,   # sum of bonuses for chart-present AND field-relevant yogas only
          "notes": [str, ...],    # only for yogas that are both present and relevant
        }

    A yoga being structurally present but not field-relevant still appears
    under "active" (bonus 0.0) so audit/trace consumers can see the full
    chart picture, but never contributes to score -- this is what keeps the
    layer from becoming a second flat "combination exists" bonus applied
    identically regardless of what field is being asked about.
    """
    field_affinity = field_affinity or {}
    active: Dict[str, Any] = {}
    notes: List[str] = []
    total_bonus = 0.0

    for entry in _YOGA_ONTOLOGY:
        p1, p2 = entry["planets"]
        h1 = planet_house.get(p1, 0)
        h2 = planet_house.get(p2, 0)
        present = _yoga_houses_related(entry["mode"], h1, h2)
        if not present:
            continue
        relevant = any(field_affinity.get(p, 0.0) >= field_affinity_gate for p in (p1, p2))
        bonus = entry["bonus"] if relevant else 0.0
        active[entry["name"]] = {
            "label": entry["label"],
            "meaning": entry["meaning"],
            "relevant": relevant,
            "bonus": round(bonus, 2),
        }
        if relevant:
            total_bonus += bonus
            notes.append(f"{entry['label']}: {entry['meaning']}")

    return {"active": active, "total_bonus": round(total_bonus, 2), "notes": notes}


DEFAULT_RUBRIC_CAPS: Dict[str, float] = {
    "core": 40.0,
    "support": 25.0,
    "validation": 20.0,
    "penalty": 20.0,
}


def clamp_score(value: float) -> float:
    """Soft-clamp using tanh compression above 80.

    Below 80 the function is identity (rank order fully preserved).
    Above 80 it uses tanh to smoothly compress toward 100 without hard-ceiling,
    so five fields that all 'score 100' retain their relative rank differences.
    Mapping reference: 80->80, 100->95.2, 120->99.3, inf->100.
    """
    try:
        x = float(value)
        if x <= 0.0:
            return 0.0
        if x <= 80.0:
            return x
        return 80.0 + 20.0 * _math.tanh((x - 80.0) / 20.0)
    except (TypeError, ValueError):
        return 0.0


def normalize_method_score(value: float, cap: float = METHOD_SCORE_CAP) -> float:
    """Map a raw method score onto a shared 0-100 scale.

    The shared cap keeps KNRao, KP, Jaimini, and Parashara comparable before
    weights are applied. Scores above the cap saturate at 100.
    """
    try:
        raw = clamp_score(value)
        cap_v = float(cap) if cap and cap > 0 else METHOD_SCORE_CAP
        return round(max(0.0, min(100.0, (raw / cap_v) * 100.0)), 2)
    except (TypeError, ValueError):
        return 0.0


# gap fix 2026-08-18 (F): Bhavat Bhavam ("house from house") -- classical
# chained-house technique: the significations of house N are corroborated by
# examining house N counted again FROM house N itself (BPHS/Phaladeepika;
# the standard worked example is the 7th-from-7th, which returns to the 1st/
# Lagna -- a marriage-house-of-the-marriage-house circles back to the self).
# Formula (whole-sign, inclusive counting, matching every other house-
# counting helper already in this codebase, e.g. astro.py's D9/D10 house-lord
# counting): counting N houses forward from house N, inclusively, lands on
# house ((N-1)+(N-1)) mod 12 + 1. Verified against the classical worked
# examples before wiring into any scoring:
#   7th-from-7th  -> 1st   ((7-1)+(7-1))%12+1 = 12%12+1 = 1   (matches BPHS)
#   10th-from-10th-> 7th   ((10-1)+(10-1))%12+1 = 18%12+1 = 7
#   2nd-from-2nd  -> 3rd   ((2-1)+(2-1))%12+1 = 2%12+1 = 3
#   6th-from-6th  -> 11th  ((6-1)+(6-1))%12+1 = 10%12+1 = 11
#   11th-from-11th-> 9th   ((11-1)+(11-1))%12+1 = 20%12+1 = 9
def bhavat_bhavam(house_n: int) -> int:
    """Nth-from-Nth house (Bhavat Bhavam), whole-sign inclusive counting.
    `house_n` and the return value are both 1-12 house numbers."""
    return ((house_n - 1) + (house_n - 1)) % 12 + 1


def top_weighted_planets(field_affinity: Dict[str, float], limit: int = 3) -> List[str]:
    if not field_affinity:
        return []
    return [p for p, _ in sorted(field_affinity.items(), key=lambda x: -x[1])[:limit]]


def rubric_section(
    section: str,
    actual: float,
    cap: float,
    *,
    kind: str = "positive",
    note: str = "",
    items: List[str] | None = None,
) -> Dict[str, Any]:
    """Create a standardized display band for side-by-side method comparison."""
    cap_v = max(0.0, float(cap))
    actual_v = round(float(actual), 2)
    if kind == "penalty":
        display_v = -min(cap_v, abs(actual_v)) if actual_v < 0 else 0.0
    else:
        display_v = min(cap_v, max(0.0, actual_v))
    return {
        "section": section,
        "kind": kind,
        "actual": actual_v,
        "display": round(display_v, 2),
        "cap": round(cap_v, 2),
        "note": note,
        "items": items or [],
    }


def build_score_rubric(method: str, sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Package a comparable rubric for each scoring method."""
    actual_total = round(sum(float(s.get("actual", 0.0)) for s in sections), 2)
    display_total = round(sum(float(s.get("display", 0.0)) for s in sections), 2)
    return {
        "method": method,
        "sections": sections,
        "actual_total": actual_total,
        "display_total": display_total,
    }


def method_result(
    name: str,
    score: float,
    trace: List[str],
    components: Dict[str, float] | None = None,
    *,
    rubric: Dict[str, Any] | None = None,
    normalization_cap: float | None = None,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Package one method's score.

    Contraindication-channel fix ("methods cannot go negative", 2026-07): every
    method file used to pre-clamp its own accumulator with `clamp_score(score)`
    before calling this function, so a chart with heavy contraindications
    (dusthana + combustion + vitality penalties outweighing any positives)
    already arrived here floored at 0 — indistinguishable from a bland neutral
    chart with no signal at all either way. Method files now pass their *raw*
    signed accumulator (which can be negative) so that sign survives here as
    `raw_signed_score`, while `score`/`normalized_score` keep their existing
    0-100-ish contract (still floored at 0) so every existing consumer of
    those two fields is unaffected. `is_net_negative` lets the bundle give a
    real (but bounded) voice to net-contraindicated methods instead of
    silently treating them the same as "no data" — see
    field_methods/__init__.py's `_has_data` / `net_contraindication_index`.
    """
    raw = float(score)
    signal_state = "NEGATIVE" if raw < 0 else "NEUTRAL" if raw == 0 else "POSITIVE"
    result = {
        "method": name,
        "score": round(clamp_score(score), 2),
        "normalized_score": normalize_method_score(score, normalization_cap or METHOD_SCORE_CAP),
        "raw_signed_score": round(raw, 2),
        "is_net_negative": raw < 0.0,
        "calculation_status": "COMPUTED",
        "signal_state": signal_state,
        "status_semantics": "NEUTRAL_IS_DISTINCT_FROM_NOT_COMPUTED_OR_FAILED",
        "trace": trace,
        "components": components or {},
        "score_rubric": rubric or {},
    }
    # 2026-08-18 fix (audit item #9): additive, purely-optional per-method
    # metadata block (e.g. Jaimini's karaka_scheme disclosure below) so a
    # method's key methodological choices are discoverable from the actual
    # output contract, not just source comments. Existing keys/shape above
    # are unchanged; callers that don't pass `metadata` see no difference.
    if metadata:
        result["metadata"] = dict(metadata)
    return result


# GAP FIX (2026-08-18, audit item B): shared "absent data vs. genuinely low
# score" utility. Before this fix, three near-identical implementations of
# the exact same pattern -- "if the whole input section is missing/falsy,
# record a MISSING note distinct from an actually-computed low score" --
# lived independently in Field_Determination/field_suitability.py's
# `_education_score` and `_career_score` (see those functions' own
# "Gap-audit fix (2026-08)" docstrings, which already named this as
# `_academic_score`'s existing contract being copy-pasted forward). This
# formalizes that copy-pasted pattern as one function instead of a third
# (and future fourth, fifth...) hand-rolled copy.
#
# Deliberately narrow in scope: this only covers the "whole section
# present/absent" check (`not edu`, `not market`, `not risk` in
# field_suitability.py). `_academic_score`'s per-subject-key missing-value
# loop is a different, finer-grained pattern (per-field, not per-section)
# and is NOT retrofitted onto this helper -- forcing it to fit here would
# change its behavior/shape, not just its plumbing, which risks the exact
# "silently wrong" regression this whole audit is trying to avoid.
_DIM_STATUS_MISSING = "MISSING"
_DIM_STATUS_SCORED = "SCORED"


def scored_dimension(
    value: Any,
    is_missing: bool,
    missing_placeholder: Any = None,
) -> tuple[Any, str]:
    """Distinguish "no evidence supplied" from "evidence supplied, score is
    genuinely low/zero".

    Args:
        value: the already-computed score/value to return when data IS
            present (unchanged, passed through verbatim -- this function
            never recomputes or clamps it).
        is_missing: True when the underlying input section was absent
            (falsy/None/empty dict), as already determined by the caller
            (e.g. `not edu`, `not market`) -- this function does not
            second-guess that judgment, it only standardizes what happens
            once it's been made.
        missing_placeholder: value to return in place of `value` when
            `is_missing` is True. Defaults to None; callers that need the
            existing "still returns a numeric 0.0/neutral default so
            downstream arithmetic doesn't crash" behavior (both
            `_education_score` and `_career_score` do, via their own
            `edu.get(key, 0.0)`/`market.get(key, "medium")` defaults) should
            pass their function's own equivalent default explicitly rather
            than relying on this function to invent one.

    Returns:
        (returned_value, status) where status is "MISSING" or "SCORED".
        `returned_value` is `missing_placeholder` when `is_missing`, else
        `value` unchanged.
    """
    if is_missing:
        return missing_placeholder, _DIM_STATUS_MISSING
    return value, _DIM_STATUS_SCORED


def combine_weighted_scores(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    """Return the weighted average of already comparable scores."""
    total_weight = sum(weights.values()) or 1.0
    return sum(float(scores.get(k, 0.0)) * w for k, w in weights.items()) / total_weight


def build_method_context(payload_data: Any) -> Dict[str, Any]:
    """Normalize the payload once so each astrology method can stay isolated."""
    return {
        "planets_d1": getattr(payload_data, "planets_d1", {}) or {},
        "house_lords": getattr(payload_data, "house_lords", {}) or {},
        "d9_chart": getattr(getattr(payload_data, "divisional_charts", {}), "get", lambda *_: {})("D9_navamsha", {}) or {},
        "d10_chart": getattr(getattr(payload_data, "divisional_charts", {}), "get", lambda *_: {})("D10_dashamsha", {}) or {},
        "eff_strengths": getattr(payload_data, "eff_strengths", {}) or {},
        "kp_cusps": getattr(payload_data, "kp_cusps", {}) or {},
        "shadbala": getattr(payload_data, "shadbala", {}) or {},
        "planet_dignities": getattr(payload_data, "planet_dignities", {}) or {},
        "planet_house": getattr(payload_data, "planet_house", {}) or {},
        "lagna_sign": getattr(payload_data, "lagna_sign", "") or "",
        "lagna_lord": getattr(payload_data, "lagna_lord", "") or "",
        "h10_lord": getattr(payload_data, "h10_lord", "") or "",
        "karakamsha": getattr(payload_data, "karakamsha", "") or "",
        "brahma_lord":         getattr(payload_data, "brahma_lord", "") or "",
        "maheshwara_lord":     getattr(payload_data, "maheshwara_lord", "") or "",
        "upapada":             getattr(payload_data, "upapada_lagna", "") or "",
    } | {
        "atmakaraka":          getattr(payload_data, "atmakaraka", "") or "",
        "amatyakaraka":        getattr(payload_data, "amatyakaraka", "") or "",
        "d10_strength":        getattr(payload_data, "d10_strength", {}) or {},
        "sav_points_houses":   getattr(payload_data, "sav_points_houses", {}) or {},
        "d10_house_occupancy": getattr(payload_data, "d10_house_occupancy", {}) or {},
        "detected_yogas":      getattr(payload_data, "detected_yogas", []) or [],
    }


# gap fix 2026-08-18 (I): Vargottama/Graha-Yuddha dedup audit. Grepped all six
# field_methods files this item names (parashara, dashamsha, knrao, navamsha,
# jaimini, kp) for their Vargottama and Graha Yuddha detection logic and read
# each hit rather than trusting function names:
#   - Vargottama (same sign in D1 and D9): the actual per-planet boolean check
#     already lives in ONE place, jyotish/astro.py::_is_vargottama, and is
#     imported directly by parashara.py and knrao.py -- not duplicated code,
#     already a shared function pre-dating this session. dashamsha.py,
#     jaimini.py and kp.py never re-derive Vargottama themselves; they only
#     read the precomputed `payload_data.vargottama_planets` list -- no local
#     detection logic to dedupe there either. navamsha.py's
#     `_d9_vargottama_score` is NOT a copy of the boolean check: it's a
#     field-affinity-weighted 0-100 confirmation score aggregated across every
#     field-driving planet, structurally different from `_is_vargottama`'s
#     single-planet boolean. It did, however, inline its own
#     `d1_sign == d9_chart.get(p, "")` equality test instead of calling the
#     shared helper -- that one inlined comparison is what `is_vargottama()`
#     below replaces, so the same-sign rule is asked in exactly one place
#     project-wide. `is_vargottama()` is a thin, behavior-preserving wrapper
#     around `jyotish.astro._is_vargottama` (identical signature and return
#     value) so navamsha.py can call a `field_methods.common` helper without
#     duplicating or altering that logic.
#   - Graha Yuddha (planetary war): within these six files, the ONLY
#     implementation is parashara.py's own T2-F block (2026-08-17 gap-fix,
#     "This file had no graha yuddha detection at all") -- dashamsha.py,
#     knrao.py, navamsha.py, jaimini.py and kp.py contain no Graha Yuddha
#     detection whatsoever (verified via `grep -ni "yuddha"` returning zero
#     hits in each). There is therefore nothing to deduplicate for Graha
#     Yuddha among these six files -- a single implementation cannot be
#     "unified" with itself. (Broader Graha Yuddha logic does also exist
#     outside this file set, in jyotish/astro.py, jyotish/boosts.py and
#     jyotish/dignity.py::graha_yuddha -- the last of which a prior session
#     already introduced as a shared jyotish-layer function per
#     jyotish/shadbala.py's "this session's merge-plan item 1" comment -- but
#     none of those three are among the six field_methods files this item
#     names, so consolidating them is out of scope here and left untouched to
#     avoid a wider, unreviewed-risk change.)
def is_vargottama(planet: str, d1_sign: str, d9_chart: Dict) -> bool:
    """Shared Vargottama check: True if `planet` occupies the same sign in
    D1 (`d1_sign`) and D9 (looked up from `d9_chart`). Thin wrapper around
    jyotish.astro._is_vargottama -- same signature, same return value -- so
    field_methods callers can depend on field_methods.common instead of
    reaching into jyotish.astro directly, without altering the check itself.
    """
    from jyotish.astro import _is_vargottama as _astro_is_vargottama
    return _astro_is_vargottama(planet, d1_sign, d9_chart)


def prioritize_rows(rows: List[Dict], priority_field_ids: List[str]) -> List[Dict]:
    """Bring a priority cluster to the front without dropping any rows."""
    priority_set = {fid: i for i, fid in enumerate(priority_field_ids)}
    front = [row for row in rows if row.get("field_id", "") in priority_set]
    front.sort(key=lambda r: priority_set.get(r.get("field_id", ""), 999))
    rest  = [row for row in rows if row.get("field_id", "") not in priority_set]
    rest.sort(key=lambda r: -r.get("final_score", 0))
    return front + rest
