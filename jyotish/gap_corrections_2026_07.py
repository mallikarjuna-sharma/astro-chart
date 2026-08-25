"""JyotishAI — 2026-07 engine-gap corrections (Ketu mode, student MD weighting,
Mrita-consistency, Venus branching, interest-prior tie-breaker).

Added in response to a user-supplied 6-item gap audit on the field-determination
engine (Ketu over-mapped to history/archaeology, active-MD under-weighted for
students, Mrita Avastha applied inconsistently, Venus over-mapped to
fashion/design, computational_social_science under-ranked, no interest-prior
tie-breaker). Each fix here is a BOUNDED, CAPPED, score-baked adjustment
applied directly to `final_score` — never a reorder-only change — because a
reorder-only fix silently gets erased by the engine's later
`results.sort(key=lambda r: -r["final_score"])` calls (confirmed root cause of
a prior 14-item stress-test gap list; see `apply_domain_deduplication` in
boosts.py for the same lesson learned the hard way).

Design choice: gap 2 ("UG field score = 45% active MD + 25% D24 + 20% D10 +
10% peak MD") is implemented as a bounded corrective multiplier on top of the
existing `final_score`, NOT a wholesale replacement of the core scoring
formula. Replacing the formula outright would discard every other signal the
199-field engine already computes (aptitude thresholds, mismatch penalties,
gap boosts, BVB method ensemble, family-cohesion, tie-break cascade) and would
almost certainly break the locked regression suite
(tests/test_regression_locked.py, tests/test_career_track_regressions.py).
Instead, the 45/25/20/10 weighting is used to build a 0-1 "student MD-alignment
score" per field, and a field's deviation from the batch average of that score
becomes a bounded (+/-12%) push on its final_score — the same "bounded,
capped, additive" pattern already used elsewhere in this engine (tie-break
cascade +/-0.45pts, family-cohesion +/-4%, yoga-alignment +0-5%).

All five corrections are computed as independent percentage deltas per row,
SUMMED (not chained multiplicatively, to avoid compounding blowups when
several gaps agree on the same field), then the sum is clamped to
+/-`_TOTAL_PCT_CAP` and applied as a single multiplication. This keeps the
combined effect predictable even when e.g. Ketu-analytical-mode, student
MD-alignment, and the interest-prior all point the same direction for one
field.
"""

from typing import Any, Dict, List, Set

_TOTAL_PCT_CAP = 0.35  # hard ceiling on the combined effect of all 5 gaps, either direction

# ── Gap 1: Ketu Classic vs Analytical mode ──────────────────────────────────
# "Classic" = history/archaeology/philosophy/Sanskrit/religion/metaphysics.
# "Analytical" = pattern detection/abstraction/modelling/research/diagnostics/
# cyber/data/AI. Only fields where Ketu is a co-primary affinity driver
# (weight >= 0.10 in BRANCH_PLANET_AFFINITY) are touched.
KETU_CLASSIC_FIELDS: Set[str] = {
    "history_archaeology", "philosophy", "sanskrit_classical_studies",
    "museum_heritage_studies",
}
KETU_ANALYTICAL_FIELDS: Set[str] = {
    "data_science_engineering", "computer_science_engineering", "cybersecurity",
    "artificial_intelligence", "quantum_computing", "cognitive_science",
    "bioinformatics", "biochemistry", "molecular_biology_genetics",
    "forensic_science", "mathematics_computing", "nanotechnology_engineering",
    "materials_science_engineering", "semiconductor_nanoelectronics",
    "research_academia",
}

# ── Gap 3: Mrita Avastha consistency ────────────────────────────────────────
MERCURY_MRITA_PENALIZE_FIELDS: Set[str] = {
    "literature_languages", "linguistics", "applied_linguistics",
    "journalism_media", "mass_communication", "law_llb",
}
MERCURY_MRITA_PRESERVE_FIELDS: Set[str] = {
    "data_science_engineering", "computer_science_engineering",
    "artificial_intelligence", "cybersecurity", "economics_data_science",
    "computational_social_science", "econometrics", "business_management",
    "information_technology", "quantum_computing", "bioinformatics",
    "mathematics_computing", "fintech", "commerce_accounting",
    "finance_banking", "computational_finance",
}
JUPITER_MRITA_PENALIZE_FIELDS: Set[str] = {
    "philosophy", "education_teaching", "sanskrit_classical_studies",
    "unani_medicine", "ayurveda", "homeopathy", "yoga_naturopathy",
}
JUPITER_MRITA_PRESERVE_FIELDS: Set[str] = {
    "economics", "economics_data_science", "public_policy", "finance_banking",
    "computational_finance", "international_relations", "international_law",
    "civil_services", "fintech", "commerce_accounting",
}

# ── Gap 4: Venus branch-by-companion ────────────────────────────────────────
VENUS_FINANCE_FIELDS: Set[str] = {
    "finance_banking", "economics_data_science", "computational_finance",
    "business_management", "computational_social_science", "econometrics",
    "commerce_accounting",
}
VENUS_POLICY_FIELDS: Set[str] = {"economics", "public_policy", "international_relations"}
VENUS_FINTECH_FIELDS: Set[str] = {
    "fintech", "digital_marketing", "information_technology", "data_science_engineering",
}
VENUS_DESIGN_FIELDS: Set[str] = {
    "fashion_design", "textile_design", "textile_technology", "interior_design",
    "fine_arts", "animation_multimedia", "photography",
    "hotel_hospitality_management", "tourism_management", "design_ux_product",
    "visual_communication",
}
VENUS_ARCHITECTURE_FIELDS: Set[str] = {
    "architecture", "automotive_engineering", "naval_architecture", "landscape_architecture",
}

# Mirrors engine.py::_edu_stream_slot_allocation's _STREAM_DOMAINS. Duplicated
# (not imported) to avoid a circular import — this module is imported BY
# engine.py.
_DOMAIN_TO_STREAM = {
    "engineering": "technical", "technology": "technical", "medicine": "technical",
    "science": "technical", "agriculture": "technical",
    "law": "humanities", "commerce": "humanities", "education": "humanities",
    "humanities": "humanities", "public": "humanities",
    "arts": "arts", "media": "arts", "interdisciplinary": "arts",
}

_D10_DIG_BASE = {"EXALTED": 1.0, "OWN": 0.8, "NEECHA_BHANGA": 0.6, "DEBILITATED": 0.1}


_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
    "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


def _sign_distance(a: str, b: str) -> int:
    """Whole-sign distance from a to b, 1-12 (1 = conjunction, 7 = opposition)."""
    if a not in _SIGN_ORDER or b not in _SIGN_ORDER:
        return 0
    return ((_SIGN_ORDER.index(b) - _SIGN_ORDER.index(a)) % 12) + 1


def _ketu_mode_and_strength(payload_data: Any, eff_strengths: Dict[str, float],
                             d10_digs: Dict[str, str], d10_planet_house: Dict[str, int]):
    """Decide whether Ketu is acting in Classic or Analytical mode for this chart.

    Calibration note: the first version of this function pitted whole-chart
    effective strength of Mercury/Rahu/Saturn against Jupiter/Moon/Sun,
    independent of whether those planets have any actual relationship to
    Ketu. That's wrong — a strong Jupiter or Sun elsewhere in the chart is not
    evidence about how KETU SPECIFICALLY behaves. Re-derived to weight actual
    conjunction/opposition TO KETU (same sign = conjunction, 7th sign =
    opposition, both real Vedic aspect relationships) as the primary signal,
    modulated by that planet's own effective strength. Sign placement of Ketu
    itself (Virgo/Aquarius = analytical-leaning; Sagittarius/Pisces/Cancer =
    classic-leaning) and D24/D10 support are secondary signals.
    """
    planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    ketu_sign = (planets_d1.get("Ketu", {}) or {}).get("sign", "")
    edu_stream = getattr(payload_data, "edu_stream", {}) or {}

    def _sign_of(p: str) -> str:
        return (planets_d1.get(p, {}) or {}).get("sign", "")

    analytical_score = 0.0
    classic_score = 0.0

    for planet, weight in (("Mercury", 0.35), ("Rahu", 0.20), ("Saturn", 0.30)):
        dist = _sign_distance(ketu_sign, _sign_of(planet))
        strength = max(eff_strengths.get(planet, 0.5), 0.5)
        if dist == 1:
            analytical_score += weight * strength
        elif dist == 7:
            analytical_score += weight * 0.6 * strength

    for planet, weight in (("Jupiter", 0.30), ("Moon", 0.20), ("Sun", 0.15)):
        dist = _sign_distance(ketu_sign, _sign_of(planet))
        strength = max(eff_strengths.get(planet, 0.5), 0.5)
        if dist == 1:
            classic_score += weight * strength
        elif dist == 7:
            classic_score += weight * 0.6 * strength

    if ketu_sign in ("Virgo", "Aquarius", "Gemini"):
        analytical_score += 0.30
    if ketu_sign in ("Sagittarius", "Pisces", "Cancer"):
        classic_score += 0.30

    analytical_score += float(edu_stream.get("technical", 0.0)) * 0.20
    classic_score += float(edu_stream.get("humanities", 0.0)) * 0.20

    ketu_d10_dig = d10_digs.get("Ketu", "")
    ketu_d10_house = d10_planet_house.get("Ketu", 0)
    if ketu_d10_dig in ("EXALTED", "OWN") or ketu_d10_house in (3, 6, 10, 11):
        analytical_score += 0.15

    total = analytical_score + classic_score
    if total <= 0:
        return "classic", 0.0
    mode = "analytical" if analytical_score >= classic_score else "classic"
    strength = min(1.0, abs(analytical_score - classic_score) / total)
    return mode, strength


def _venus_companion_mode(eff_strengths: Dict[str, float]):
    """Which planet is Venus's strongest companion in this chart, and how dominant."""
    companions = {
        "finance": eff_strengths.get("Mercury", 0.0),
        "policy": eff_strengths.get("Jupiter", 0.0),
        "fintech": eff_strengths.get("Rahu", 0.0),
        "design": eff_strengths.get("Moon", 0.0),
        "architecture": eff_strengths.get("Mars", 0.0),
    }
    total = sum(companions.values()) or 1.0
    mode = max(companions, key=companions.get)
    strength = companions[mode] / total
    return mode, strength


def _has_h10_support(row: Dict, support_planets: Set[str], house_lords: Dict) -> bool:
    calc = row.get("calc_trace", {}) or {}
    h10_aspects = set(calc.get("aspects_on_h10", []) or [])
    h10_lord = house_lords.get("10", "") or house_lords.get(10, "")
    return bool(support_planets & h10_aspects) or (h10_lord in support_planets)


def _md_alignment_component(row: Dict, active_lord: str, peak_lord: str,
                             edu_stream: Dict, d10_planet_house: Dict, d10_digs: Dict) -> float:
    """0-1 'student UG alignment' score = 45% active MD + 25% D24 + 20% D10 + 10% peak MD."""
    aff = row.get("affinity_planets", {}) or {}
    active_c = aff.get(active_lord, 0.0) if active_lord else 0.0
    peak_c = aff.get(peak_lord, 0.0) if peak_lord else 0.0

    stream = _DOMAIN_TO_STREAM.get((row.get("domain") or "").lower())
    d24_c = float(edu_stream.get(stream, 0.33)) if stream else 0.33

    d10_c = 0.4
    if aff:
        top_planet = max(aff.items(), key=lambda kv: kv[1])[0]
        dig = d10_digs.get(top_planet, "")
        h = d10_planet_house.get(top_planet, 0)
        d10_c = _D10_DIG_BASE.get(dig, 0.4)
        if h in (1, 4, 5, 7, 9, 10):
            d10_c = min(1.0, d10_c + 0.15)
        elif h in (6, 8, 12):
            d10_c = max(0.0, d10_c - 0.15)

    return 0.45 * active_c + 0.25 * d24_c + 0.20 * d10_c + 0.10 * peak_c


def apply_gap_2026_07_corrections(
    results: List[Dict],
    payload_data: Any,
    eff_strengths: Dict[str, float],
    house_lords: Dict,
    active_lord: str,
    peak_lord: str,
    mrita_planets: Set[str],
    career_phase: str,
) -> List[Dict]:
    """Apply the 6-item 2026-07 gap audit as bounded, score-baked adjustments.

    Mutates `final_score` in place on each row and returns the (still-sorted-
    by-caller) list. Every adjustment here is additive-percentage and summed
    per row before being clamped and applied once, so combined effects stay
    predictable. Wrapped defensively by the caller (engine.py) so a failure
    here can never break field determination itself.
    """
    if not results:
        return results

    d10_digs = getattr(payload_data, "d10_planet_dignities", {}) or {}
    d10_occ = getattr(payload_data, "d10_house_occupancy", {}) or {}
    d10_planet_house: Dict[str, int] = {}
    for h, plist in (d10_occ or {}).items():
        try:
            hn = int(h)
        except (TypeError, ValueError):
            continue
        for p in (plist or []):
            d10_planet_house[p] = hn

    edu_stream = getattr(payload_data, "edu_stream", {}) or {}
    interested_in = [s.lower() for s in (getattr(payload_data, "interested_in", []) or []) if s]

    # Gap 1 precompute: Ketu mode is chart-wide, computed once.
    ketu_mode, ketu_strength = _ketu_mode_and_strength(payload_data, eff_strengths, d10_digs, d10_planet_house)

    # Gap 4 precompute: Venus companion mode is chart-wide, computed once.
    # Only meaningful when Venus itself is a genuinely strong chart driver —
    # otherwise "which planet keeps Venus company" is not a strong-enough
    # signal to redirect fields away from their base affinity doctrine.
    venus_eff = eff_strengths.get("Venus", 0.0)
    all_effs = list(eff_strengths.values()) or [0.0]
    venus_is_strong = venus_eff >= (sum(all_effs) / len(all_effs))
    venus_mode, venus_strength = _venus_companion_mode(eff_strengths) if venus_is_strong else ("design", 0.0)
    venus_boost_pct = min(0.15, 0.08 + 0.10 * venus_strength) if venus_is_strong else 0.0
    venus_reduce_pct = min(0.10, 0.05 + 0.08 * venus_strength) if venus_is_strong else 0.0
    _VENUS_TARGET_MAP = {
        "finance": VENUS_FINANCE_FIELDS, "policy": VENUS_POLICY_FIELDS,
        "fintech": VENUS_FINTECH_FIELDS, "design": VENUS_DESIGN_FIELDS,
        "architecture": VENUS_ARCHITECTURE_FIELDS,
    }

    # Gap 2 precompute: batch-average MD-alignment score (student phase only).
    md_alignment_avg = 0.0
    md_alignment_by_id: Dict[str, float] = {}
    if career_phase == "student":
        for row in results:
            c = _md_alignment_component(row, active_lord, peak_lord, edu_stream, d10_planet_house, d10_digs)
            md_alignment_by_id[row.get("field_id", "")] = c
        if md_alignment_by_id:
            md_alignment_avg = sum(md_alignment_by_id.values()) / len(md_alignment_by_id)

    # Gap 6 precompute: batch-median final_score as the "medium astrological
    # evidence" bar for the interest-prior tie-breaker.
    sorted_scores = sorted(r.get("final_score", 0.0) for r in results)
    median_score = sorted_scores[len(sorted_scores) // 2] if sorted_scores else 0.0

    mercury_mrita = "Mercury" in mrita_planets
    jupiter_mrita = "Jupiter" in mrita_planets

    for row in results:
        fid = row.get("field_id", "")
        label = (row.get("field_label") or "").lower()
        aff = row.get("affinity_planets", {}) or {}
        pct_terms: List[float] = []
        notes: List[str] = []

        # ── Gap 1: Ketu mode ────────────────────────────────────────────
        ketu_w = aff.get("Ketu", 0.0)
        if ketu_w >= 0.10:
            if fid in KETU_ANALYTICAL_FIELDS:
                p = (0.12 if ketu_mode == "analytical" else -0.08) * max(ketu_strength, 0.3)
                pct_terms.append(p)
                notes.append(f"ketu_mode={ketu_mode} analytical-field {p:+.1%}")
            elif fid in KETU_CLASSIC_FIELDS:
                p = (0.12 if ketu_mode == "classic" else -0.10) * max(ketu_strength, 0.3)
                pct_terms.append(p)
                notes.append(f"ketu_mode={ketu_mode} classic-field {p:+.1%}")

        # ── Gap 2: student MD-alignment (active MD 45% / D24 25% / D10 20% / peak MD 10%) ──
        if career_phase == "student" and fid in md_alignment_by_id:
            delta = md_alignment_by_id[fid] - md_alignment_avg
            p = max(-0.12, min(0.12, delta * 0.6))
            if abs(p) >= 0.01:
                pct_terms.append(p)
                notes.append(f"student_md_alignment {p:+.1%}")

        # ── Gap 3: Mrita Avastha consistency ────────────────────────────
        if mercury_mrita:
            if fid in MERCURY_MRITA_PENALIZE_FIELDS:
                pct_terms.append(-0.12)
                notes.append("mercury_mrita: pure-verbal field penalized -12%")
            elif fid in MERCURY_MRITA_PRESERVE_FIELDS and not _has_h10_support(row, {"Rahu", "Saturn"}, house_lords):
                pct_terms.append(-0.05)
                notes.append("mercury_mrita: applied-analytics field, no Rahu/Saturn H10 support -5%")

        if jupiter_mrita:
            if fid in JUPITER_MRITA_PENALIZE_FIELDS:
                pct_terms.append(-0.12)
                notes.append("jupiter_mrita: pure-classical field penalized -12%")
            elif fid in JUPITER_MRITA_PRESERVE_FIELDS and not _has_h10_support(row, {"Sun", "Venus", "Mercury"}, house_lords):
                pct_terms.append(-0.05)
                notes.append("jupiter_mrita: economics/policy field, no Sun/Venus/Mercury H10 support -5%")

        # ── Gap 4: Venus branch-by-companion ────────────────────────────
        if venus_is_strong:
            target_fields = _VENUS_TARGET_MAP.get(venus_mode, set())
            if fid in target_fields:
                pct_terms.append(venus_boost_pct)
                notes.append(f"venus_companion={venus_mode} {venus_boost_pct:+.1%}")
            elif venus_mode != "design" and fid in VENUS_DESIGN_FIELDS:
                pct_terms.append(-venus_reduce_pct)
                notes.append(f"venus_companion={venus_mode} (not design) design-field {-venus_reduce_pct:+.1%}")

        # ── Gap 6: interest-prior tie-breaker ───────────────────────────
        if interested_in and any(kw in fid or kw in label for kw in interested_in):
            if row.get("final_score", 0.0) >= median_score:
                pct_terms.append(0.12)
                notes.append("interest_prior: stated interest, medium+ astro support +12%")
            else:
                notes.append("interest_prior: stated interest noted as exploration, no astro support — no score change")

        if pct_terms:
            total_pct = max(-_TOTAL_PCT_CAP, min(_TOTAL_PCT_CAP, sum(pct_terms)))
            row["final_score"] = round(row.get("final_score", 0.0) * (1.0 + total_pct), 2)
            row["gap_2026_07_adjustment"] = round(total_pct, 4)
            row["gap_2026_07_notes"] = notes

    return results


# =============================================================================
# ROUND 2 (2026-07 second pass) — macro-cluster gate, specificity/contradiction
# gate, Mars expression mode, Mrita extension to Moon/Saturn, hybrid-vs-plain
# resolver, risk-appetite niche discount, self-audit summary.
#
# Added in response to a second user audit (16 items) after seeing Sai
# Havish's run: the macro identity ("Computational Intelligence + Data,
# Statistics & Quant Analytics + Economics & Data Science") was correct, but
# the top-20 field list still let weakly-clustered specialized fields through
# (Printing & Packaging #4, Visual Communication #7, Game Design #8,
# Dentistry #9, Food Science #13).
#
# Validation verdicts (checked against the actual codebase before writing any
# of this, per the user's request to "validate if they are actual gaps"):
#   - Macro-cluster gate / parent-child inheritance / specificity threshold
#     (their gaps 1, 9, 10): VALID, and partially pre-built. ontology_kg.py
#     already computes `broadness_penalty` and `graph_cluster` per field via
#     attach_graph_diagnostics(), but its own docstring says plainly: "Nothing
#     in this module mutates final_score... wiring a new bounded score nudge
#     from this graph into engine.py is a deliberate follow-up decision left
#     to the user." That follow-up was never done — this is the fix.
#   - Venus contextual mapping (gap 2): mostly ALREADY FIXED in round 1
#     (`_venus_companion_mode` above). Added the missing Venus+Saturn ->
#     audit/compliance/structured-finance branch this round.
#   - Plain B.Com over-ranked / hybrid-vs-plain (gaps 3, 14): VALID, not
#     previously implemented. Fixed below (`_apply_hybrid_vs_plain`).
#   - Mars expression mode (gap 4): VALID, same pattern as Ketu/Venus mode.
#     Fixed below (`_mars_mode_and_targets`).
#   - Mrita depth for Moon/Saturn (gap 5): VALID — round 1 only handled
#     Mercury/Jupiter Mrita. Extended below.
#   - Separate UG/PG/Career scoring (gap 6): valid in principle, but a full
#     three-formula rearchitecture is large-scope/high-regression-risk for an
#     engine with a locked regression suite. NOT implemented this round —
#     round 1's student-phase MD-alignment already covers the UG case: it's
#     the one that matters most for a current student. Flagging as
#     deliberately deferred, not silently skipped.
#   - Planet expression modes generally (gap 7): VALID as a principle. Built
#     concretely for Ketu, Venus (round 1) and Mars (this round). Did NOT
#     also build fully separate Mercury/Moon/Saturn branching machinery,
#     because their requested behaviors are already substantially covered by
#     the Venus-mode + Mars-mode + Mrita-extension + risk-appetite mechanisms
#     below — a 4th/5th/6th parallel branching system risks compounding
#     adjustments on the same fields rather than adding real signal.
#   - Contradiction/negative-evidence engine (gap 8): VALID, and it is the
#     direct mechanism-level explanation for the Dentistry/Printing noise.
#     Implemented as a scoped minimum-evidence check on a curated set of
#     historically-noisy specialized fields (NOT a full 199-field
#     FIELD_REQUIREMENTS registry — that's a much larger, separate task).
#   - Education realism layer (gap 11): valid in spirit but the full 5-metric
#     registry (course_availability, career_flexibility, market_strength,
#     pg_upgrade_potential, risk_level) needs curated values per field across
#     all 199 fields — out of scope this round. Folded the actionable part
#     (niche/narrow UG choices should be discounted under low risk appetite)
#     into the risk-appetite fix below, since that's where the user's own
#     examples (Printing, Game Design, Visual Communication) overlap 100%
#     with gap 12's examples.
#   - Risk appetite (gap 12): PARTIALLY VALID. `_risk_appetite_bonus()` in
#     boosts.py already exists and is wired into the main loop, but it's
#     keyword-classified (_FRONTIER_KW/_TRADITIONAL_KW in boosts.py) and its
#     swing is small (+/-0.06 to 0.08 as an additive gap_boost term, not a
#     final_score percentage) — it doesn't clearly cover Printing/Game
#     Design/Visual Communication/Food Science by name. Added a
#     supplementary, explicitly-named penalty for LOW risk appetite on the
#     same curated niche-field set as the contradiction gate.
#   - Route-based output (gap 13): the top-20 is ALREADY grouped by cluster
#     in field_deterministic_engine_v1_llm.py (fixed in the previous session,
#     `_top20_as_four_cluster_groups`). That substantially satisfies the
#     intent ("don't hand parents a flat mixed list"). Not building a second,
#     parallel "Route N" renderer on top of the existing cluster grouping —
#     that would be duplicative UI for the same underlying grouping.
#   - Self-audit / demoted-fields explanation (gap 15): VALID and cheap since
#     round 1 already collects per-row notes. Implemented below
#     (`build_round2_audit_summary`).
#   - Deterministic locking / LLM-explanation-only (gap 16): INVALID — this
#     is already true. `jyotish/llm.py::call_llm_for_fields`'s own docstring
#     says: "The ranking is FIXED by the deterministic engine... NOTE:
#     LLM-as-reranker (the old Step 1 selector) is intentionally removed."
#     No change needed; not a real gap.
# =============================================================================

# ── Gap 4/7: Mars expression mode ───────────────────────────────────────────
MARS_TECH_ANALYTICS_FIELDS: Set[str] = {
    "computer_science_engineering", "data_science_engineering",
    "artificial_intelligence", "cybersecurity",
    "electronics_communication_engineering", "industrial_engineering",
    "fintech", "semiconductor_nanoelectronics",
}
MARS_MECHANICAL_FIELDS: Set[str] = {
    "mechanical_engineering", "production_manufacturing_engineering",
    "civil_engineering", "mining_engineering",
}
MARS_DEFENCE_FIELDS: Set[str] = {
    "defence_military", "defence_strategic_studies", "sports_science_management",
}


def _mars_mode_and_targets(eff_strengths: Dict[str, float]):
    """Mars companion mode, same eff-strength-dominance pattern as Venus's.

    tech_analytics when Mercury+Rahu (averaged) outweigh Saturn; mechanical
    when Saturn dominates; defence/base otherwise. Companion strength (not
    conjunction) is used deliberately here, mirroring `_venus_companion_mode`
    — the question being asked is "who does Mars keep company with in this
    chart's overall strength profile," not "who aspects Mars specifically."
    """
    mercury_rahu = (eff_strengths.get("Mercury", 0.0) + eff_strengths.get("Rahu", 0.0)) / 2.0
    saturn = eff_strengths.get("Saturn", 0.0)
    if mercury_rahu >= saturn and mercury_rahu > 0:
        return "tech_analytics", MARS_TECH_ANALYTICS_FIELDS
    if saturn > mercury_rahu:
        return "mechanical", MARS_MECHANICAL_FIELDS
    return "defence", MARS_DEFENCE_FIELDS


# ── Gap 2 extension: Venus + Saturn -> audit/compliance/structured finance ──
VENUS_AUDIT_FIELDS: Set[str] = {"actuarial_science"}

# ── Gap 5 extension: Moon/Saturn Mrita ──────────────────────────────────────
MOON_MRITA_PENALIZE_FIELDS: Set[str] = {
    "psychology", "clinical_psychology", "organisational_psychology",
    "hotel_hospitality_management", "nutrition_dietetics", "nursing",
}
SATURN_MRITA_PENALIZE_FIELDS: Set[str] = {
    "civil_services", "commerce_accounting", "production_manufacturing_engineering",
    "mining_engineering", "civil_engineering",
}
SATURN_MRITA_PRESERVE_FIELDS: Set[str] = {
    "industrial_engineering", "actuarial_science", "computational_finance", "econometrics",
}

# ── Gaps 3/14: hybrid-vs-plain resolver ─────────────────────────────────────
# plain field -> its hybrid upgrades, only promoted if present in the batch.
PLAIN_TO_HYBRID_UPGRADES: Dict[str, List[str]] = {
    "commerce_accounting": ["economics_data_science", "computational_finance", "econometrics", "fintech"],
    "economics": ["economics_data_science", "econometrics"],
    "law_llb": ["corporate_law"],
}

# ── Gaps 1/8/9/10: macro-cluster gate + specificity/contradiction gate ──────
# Curated set of fields that have repeatedly shown up as symbolic
# false-positives in stress testing (hyper-specific/niche courses that a
# loose keyword or single-planet match can push into the top 20 even when
# their broader career cluster has no real support in the chart). NOT an
# attempt at a full 199-field FIELD_REQUIREMENTS registry — that is a
# separate, much larger undertaking.
NICHE_SPECIALIZED_FIELDS: Set[str] = {
    "printing_packaging_technology", "game_design_technology", "visual_communication",
    "food_science_technology", "dentistry", "textile_technology", "animation_multimedia",
    "photography", "leather_technology",
}
STABLE_PROFESSIONAL_FIELDS: Set[str] = {
    "data_science_engineering", "economics", "economics_data_science",
    "computer_science_engineering", "electronics_communication_engineering",
    "business_management", "corporate_law", "civil_services", "actuarial_science",
}

# 2026-07 Ramsunder audit: Saturn + Mars + Rahu/Ketu/Jupiter should resolve to
# advanced physical/materials engineering before land/property/agriculture.
ADVANCED_PHYSICAL_ENGINEERING_FIELDS: Set[str] = {
    "materials_science_engineering", "metallurgical_engineering",
    "engineering_physics", "space_materials", "aerospace_engineering",
    "space_sciences_engineering", "space_systems_engineering",
    "mechanical_engineering", "production_manufacturing_engineering",
    "industrial_engineering", "automotive_engineering",
    "polymer_plastics_engineering", "chemical_engineering",
    "chemical_engineering_data_science", "semiconductor_nanoelectronics",
    "nuclear_engineering", "robotics_automation", "ceramic_engineering",
    # Gap-audit fix (2026-08): electrical_engineering, power_systems_engineering,
    # energy_engineering, and aeronautical_engineering were absent from this
    # whitelist despite being the same astrological category this mode exists
    # to capture -- hard technical/structural engineering under a chart-wide
    # strong-Saturn + Mars/Rahu/Ketu/Jupiter signature (Saturn/Rahu are the
    # classical significators of electricity, power systems, and unconventional
    # technology; Mars is the engineering/execution karaka). There is no
    # documented rationale anywhere in this module for excluding them while
    # including their closest siblings (chemical_engineering,
    # automotive_engineering, semiconductor_nanoelectronics, aerospace_engineering
    # are all present). Confirmed on a real chart (Midhula, 2026-08 audit):
    # with this mode active, siblings inside the whitelist received +18-24%
    # while electrical_engineering/power_systems_engineering/energy_engineering/
    # aeronautical_engineering received 0% here -- and that gap then compounded
    # through every later RELATIVE mechanism (interdomain normalization compares
    # against the domain leader; the cross-batch 20-100 min-max stretch is
    # skewed by whichever fields this mode inflated), producing a 59-64% final
    # score collapse for fields that scored as strong or stronger than the
    # boosted siblings on every raw method (electrical_engineering out-scored
    # mechanical_engineering on K.N. Rao, KP, and Shashtiamsha in that same
    # run). This was an incomplete whitelist, not an intentional exclusion.
    "electrical_engineering", "power_systems_engineering",
    "energy_engineering", "aeronautical_engineering",
}
SATURN_LAND_FALSE_POSITIVE_FIELDS: Set[str] = {
    "agriculture_forestry", "soil_science_agronomy", "horticulture",
    "forestry_wildlife", "agribusiness_management",
    "real_estate_management", "urban_regional_planning",
    "infrastructure_planning_engineering", "construction_engineering_management",
    "transportation_engineering", "rural_management", "landscape_architecture",
}
SATURN_SYMBOLIC_FALSE_POSITIVE_FIELDS: Set[str] = {
    "criminal_law", "criminology_penology", "prosthetics_orthotics",
    "organisational_psychology", "blockchain_web3", "journalism_media",
    "mass_communication", "naval_architecture", "design_ux_product",
}


def _saturn_expression_mode(eff_strengths: Dict[str, float], active_lord: str, peak_lord: str) -> str:
    avg = sum(eff_strengths.values()) / max(len(eff_strengths), 1)
    saturn = eff_strengths.get("Saturn", 0.0)
    engineering_support = sum(
        1 for p in ("Mars", "Rahu", "Ketu", "Jupiter")
        if eff_strengths.get(p, 0.0) >= avg * 0.92
    )
    nodal_frontier_support = (
        eff_strengths.get("Rahu", 0.0) >= avg * 0.92
        or eff_strengths.get("Ketu", 0.0) >= avg * 0.92
    )
    land_support = sum(
        1 for p in ("Moon", "Venus")
        if eff_strengths.get(p, 0.0) >= avg * 1.05
    )
    if (
        (saturn >= avg or peak_lord == "Saturn" or active_lord == "Saturn")
        and engineering_support >= 2
        and (nodal_frontier_support or peak_lord == "Saturn" or active_lord == "Saturn")
    ):
        return "advanced_physical_engineering"
    if saturn >= avg and land_support >= 2:
        return "land_real_estate_agriculture"
    return "general_structure"


def _cluster_scores_for_batch(results: List[Dict], eff_strengths: Dict[str, float]) -> Dict[str, float]:
    """Batch-relative 0-1 cluster strength.

    IMPORTANT calibration note: the first version of this function computed
    cluster strength from the fields' own `final_score` (mean of each
    cluster's top-3 final_scores). That is circular — final_score is exactly
    the thing the gate is supposed to sanity-check, so a cluster stuffed with
    several individually-inflated false-positive fields could validate
    itself as "strong" (confirmed in testing: a synthetic Design/Media
    cluster containing 3 noise fields scored the same or higher than the
    genuinely-supported Commerce/Finance cluster). Re-derived to use each
    field's raw affinity-planets dotted with the chart's real effective
    strengths (`sum(weight * eff_strengths[planet])`) — a measure of the
    actual astrological signal behind the cluster, independent of every
    downstream multiplier/penalty/normalization step that produced
    final_score.

    Still imperfect: in a chart where several planets are simultaneously
    strong (common — 5 of 9 planets were above-average in the validating
    chart), almost any field can find SOME strong companion, so this signal
    alone won't cleanly separate a well-supported cluster from an
    overlapping one. It is one input among several (see the specificity gate
    below, which is the primary defense for the specific fields flagged as
    recurring false positives).
    """
    by_cluster: Dict[str, List[float]] = {}
    for row in results:
        cluster_label = row.get("graph_cluster", "")
        if not cluster_label:
            continue
        aff = row.get("affinity_planets", {}) or {}
        if not aff:
            continue
        raw_astro_strength = sum(w * eff_strengths.get(p, 0.0) for p, w in aff.items())
        by_cluster.setdefault(cluster_label, []).append(raw_astro_strength)

    raw: Dict[str, float] = {}
    for cluster, scores in by_cluster.items():
        top3 = sorted(scores, reverse=True)[:3]
        raw[cluster] = sum(top3) / len(top3) if top3 else 0.0
    max_v = max(raw.values()) if raw else 1.0
    return {c: (v / max_v if max_v else 0.0) for c, v in raw.items()}


def _macro_cluster_gate_pct(cluster_score: float) -> float:
    """User-specified thresholds, expressed as percentage deltas for the
    additive-then-cap framework (0.55x multiplier == -45%, 0.75x == -25%)."""
    if cluster_score < 0.55:
        return -0.45
    if cluster_score < 0.65:
        return -0.25
    return 0.0


def apply_gap_2026_07_round2_corrections(
    results: List[Dict],
    payload_data: Any,
    eff_strengths: Dict[str, float],
    house_lords: Dict,
    mrita_planets: Set[str],
    active_lord: str,
    peak_lord: str,
):
    """Round 2 of the 2026-07 gap corrections. Same bounded/summed/capped
    discipline as round 1, but run AFTER attach_graph_diagnostics() so
    `graph_cluster`/`graph_broadness_penalty` are already present on each row
    (round 1 runs before the ontology/graph layers; this one must run after).

    Returns (results, audit_summary) — audit_summary is the gap-15 self-audit
    (top demoted/promoted fields with reasons), not attached to any single
    row since it's a batch-level summary.
    """
    if not results:
        return results, {}

    cluster_scores = _cluster_scores_for_batch(results, eff_strengths)
    edu_stream = getattr(payload_data, "edu_stream", {}) or {}
    dominant_stream = edu_stream.get("dominant_stream", "")
    interested_in = [s.lower() for s in (getattr(payload_data, "interested_in", []) or []) if s]
    risk_appetite = (getattr(payload_data, "risk_appetite", "") or
                      (getattr(payload_data, "career_context", {}) or {}).get("risk_appetite", "") or "").upper()

    mars_mode, mars_targets = _mars_mode_and_targets(eff_strengths)
    mars_is_relevant = (
        eff_strengths.get("Mars", 0.0) >= (sum(eff_strengths.values()) / max(len(eff_strengths), 1))
        or active_lord == "Mars" or peak_lord == "Mars"
    )

    venus_eff = eff_strengths.get("Venus", 0.0)
    all_effs = list(eff_strengths.values()) or [0.0]
    venus_is_strong = venus_eff >= (sum(all_effs) / len(all_effs))
    saturn_is_venus_companion = (
        venus_is_strong and eff_strengths.get("Saturn", 0.0) > max(
            eff_strengths.get("Mercury", 0.0), eff_strengths.get("Jupiter", 0.0),
            eff_strengths.get("Rahu", 0.0), eff_strengths.get("Moon", 0.0))
    )

    moon_mrita = "Moon" in mrita_planets
    saturn_mrita = "Saturn" in mrita_planets

    mercury_rahu_strong = (
        eff_strengths.get("Mercury", 0.0) >= (sum(all_effs) / len(all_effs))
        and eff_strengths.get("Rahu", 0.0) >= (sum(all_effs) / len(all_effs))
    )
    saturn_mode = _saturn_expression_mode(eff_strengths, active_lord, peak_lord)

    by_id = {r.get("field_id", ""): r for r in results}

    for row in results:
        fid = row.get("field_id", "")
        domain = (row.get("domain") or "").lower()
        pct_terms: List[float] = []
        notes: List[str] = []

        # ── Gap 4/7: Mars expression mode ───────────────────────────────
        if mars_is_relevant:
            if fid in mars_targets:
                pct_terms.append(0.10)
                notes.append(f"mars_mode={mars_mode} +10%")
            elif fid in (MARS_TECH_ANALYTICS_FIELDS | MARS_MECHANICAL_FIELDS | MARS_DEFENCE_FIELDS) - mars_targets:
                pct_terms.append(-0.06)
                notes.append(f"mars_mode={mars_mode} (not this field's Mars category) -6%")

        # ── Gap 2 extension: Venus + Saturn audit/compliance ────────────
        if saturn_is_venus_companion and fid in VENUS_AUDIT_FIELDS:
            pct_terms.append(0.10)
            notes.append("venus_companion=audit (Saturn) +10%")

        # ── Gap 5 extension: Moon/Saturn Mrita ──────────────────────────
        if moon_mrita and fid in MOON_MRITA_PENALIZE_FIELDS:
            pct_terms.append(-0.22)  # 1 - 0.78 from the user's own spec
            notes.append("moon_mrita: soft-care/service field penalized -22%")
        if saturn_mrita:
            if fid in SATURN_MRITA_PENALIZE_FIELDS:
                pct_terms.append(-0.18)  # 1 - 0.82 from the user's own spec
                notes.append("saturn_mrita: rigid/repetitive field penalized -18%")
            elif fid in SATURN_MRITA_PRESERVE_FIELDS and not _has_h10_support(row, {"Mercury", "Rahu"}, house_lords):
                pct_terms.append(-0.05)
                notes.append("saturn_mrita: structured-analytics field, no Mercury/Rahu H10 support -5%")

        # ── Gaps 3/14: hybrid vs plain ───────────────────────────────────
        if mercury_rahu_strong and fid in PLAIN_TO_HYBRID_UPGRADES:
            pct_terms.append(-0.15)
            notes.append("hybrid_resolver: plain field demoted -15% (chart supports computation)")
        if mercury_rahu_strong:
            for plain_fid, upgrades in PLAIN_TO_HYBRID_UPGRADES.items():
                if fid in upgrades and fid in by_id:
                    pct_terms.append(0.12)
                    notes.append(f"hybrid_resolver: promoted as {plain_fid}'s hybrid upgrade +12%")
                    break

        # ── Gaps 1/8/9/10: macro-cluster gate + specificity/contradiction ─
        cluster_label = row.get("graph_cluster", "")
        cluster_score = cluster_scores.get(cluster_label, 1.0) if cluster_label else 1.0
        gate_pct = _macro_cluster_gate_pct(cluster_score)
        if gate_pct:
            pct_terms.append(gate_pct)
            notes.append(f"macro_cluster_gate: '{cluster_label}' cluster_score={cluster_score:.2f} {gate_pct:+.0%}")

        if fid in NICHE_SPECIALIZED_FIELDS:
            # Baseline-discount-with-override. Testing went through two
            # earlier, WRONG designs before landing here: (1) a multi-signal
            # "evidence count" using "raw score in top quartile" as one
            # signal — circular, since the inflated score IS the thing in
            # question. (2) narrowing that to "top-3 raw score" as a
            # stricter override — still circular, it just moved the cliff
            # edge (confirmed: it let Printing/Visual-Communication mostly
            # off the hook specifically BECAUSE their score was inflated,
            # while fields one rank lower got the full penalty for no
            # principled reason). Any override derived from final_score
            # itself will have this problem. The only genuinely independent,
            # non-circular signal available here is a stated interest — so
            # that's the only override. Blunter, but honest about what can
            # actually be verified without a labeled corpus or a real
            # per-field evidence registry (gap 8's fuller vision, deferred).
            pct_terms.append(-0.15)
            notes.append("specificity_gate: specialized/niche field baseline -15%")
            override = False
            if interested_in and any(kw in fid or kw in (row.get("field_label") or "").lower() for kw in interested_in):
                pct_terms.append(0.15)
                notes.append("specificity_gate override: stated interest, discount reversed")
                override = True

            # ── Gap 12 (+ folded-in gap 11): risk appetite on niche fields ──
            if risk_appetite == "LOW" and not override:
                pct_terms.append(-0.10)
                notes.append("risk_appetite=LOW: niche/narrow UG choice, no override -10%")

        if risk_appetite == "LOW" and fid in STABLE_PROFESSIONAL_FIELDS:
            pct_terms.append(0.05)
            notes.append("risk_appetite=LOW: stable professional field +5%")

        # Ramsunder/materials audit: strong Saturn with Mars/Rahu/Ketu/Jupiter
        # is hard physical engineering, not automatically land/property.
        if saturn_mode == "advanced_physical_engineering":
            if fid in ADVANCED_PHYSICAL_ENGINEERING_FIELDS:
                boost = 0.18
                if fid in {
                    "materials_science_engineering", "metallurgical_engineering",
                    "engineering_physics", "space_materials", "aerospace_engineering",
                    "space_sciences_engineering",
                }:
                    boost = 0.24
                pct_terms.append(boost)
                notes.append(f"saturn_mode={saturn_mode}: materials/physical-engineering route +{boost:.0%}")
            elif fid in SATURN_LAND_FALSE_POSITIVE_FIELDS:
                pct_terms.append(-0.35)
                notes.append(f"saturn_mode={saturn_mode}: land/agri/property expression capped -35%")
            elif fid in SATURN_SYMBOLIC_FALSE_POSITIVE_FIELDS:
                pct_terms.append(-0.28)
                notes.append(f"saturn_mode={saturn_mode}: symbolic/hyper-specific false positive -28%")

        if pct_terms:
            total_pct = max(-0.55, min(0.45, sum(pct_terms)))
            row["final_score"] = round(row.get("final_score", 0.0) * (1.0 + total_pct), 2)
            existing_adj = row.get("gap_2026_07_round2_adjustment", 0.0)
            row["gap_2026_07_round2_adjustment"] = round(existing_adj + total_pct, 4)
            row["gap_2026_07_round2_notes"] = notes

    audit_summary = build_round2_audit_summary(results)
    return results, audit_summary


# =============================================================================
# ROUND 3 (2026-07 third pass) — broadness-penalty wiring, Virgo-10th /
# Mercury-10th-lord accelerator, adult/mature-career output framing.
#
# Added after a third user audit (Karthick's chart): education_teaching #1,
# public_policy #2, liberal_arts_interdisciplinary #3, with AI at #13 and
# computational_finance at #12 despite a Virgo 10th house, Mercury as 10th
# lord sitting in its own sign IN the 10th house, and an active Venus MD
# conjunct Mars in the 9th. Also: Karthick is 41 (DOB 1985-09-29, confirmed
# from the chart file), so the CLI's "UG: BA Political Science / LLB" framing
# is nonsensical for an adult career chart — a genuine, separate bug.
#
# Validation: pulled Karthick's real chart facts before writing anything.
# Confirmed: d1_lagna=Sagittarius -> 10th house = Virgo (10th from
# Sagittarius, whole-sign) with 10th lord Mercury; Mercury itself sits IN
# Virgo (own sign) in that 10th house, conjunct Sun (possible combustion —
# not assumed away, see the eff_strength gate below); Venus MD (2011-2031,
# active) is conjunct Mars in Leo/9th house; Jupiter is in Capricorn
# (classically debilitated). This is real, independent structural support
# for the user's claim — not just accepted on their say-so.
#
# What was ALREADY covered by rounds 1-2 and did NOT need re-fixing:
#   - Venus contextual mapping: `_venus_companion_mode` already exists and
#     would route Venus through whichever of Mercury/Jupiter/Rahu/Moon/Mars
#     has the highest effective strength — no new mechanism needed, though
#     note it may pick "architecture" mode if Mars's eff_strength edges out
#     Mercury's, since Venus is literally conjunct Mars here. That's a
#     legitimate astrological reading (Venus-Mars in the 9th can express as
#     driven, ambitious pursuit of higher-status goals), not obviously wrong
#     — left as-is rather than hand-tuning it toward the user's preferred
#     outcome without real evidence Mars ISN'T the dominant companion.
#   - Hyper-specific field suppression (Engineering Physics, Medical
#     Physics, Medicine): already handled by round 2's specificity gate IF
#     these field_ids are added to NICHE_SPECIALIZED_FIELDS (done below —
#     they were validated as real, narrow field ids not previously in that
#     set, so this is a genuine extension, not a duplicate fix).
#   - Round 1's Jupiter-Mrita penalty does NOT apply here: Mrita Avastha is
#     specifically a DEGREE condition (24-30 deg in odd signs, 0-6 deg in
#     even signs), and Jupiter's 13.59 deg in Capricorn (even sign) does not
#     qualify — Jupiter is debilitated by SIGN, a different, already-handled
#     condition (compute_dignity/_mrita_alpha's own-sign path), not
#     something this module should duplicate. This is exactly why a Virgo
#     10th / Mercury accelerator was still needed as a NEW mechanism.
# =============================================================================

NICHE_SPECIALIZED_FIELDS |= {"engineering_physics", "medical_physics"}

ANALYTICS_FINANCE_CONSULTING_FIELDS: Set[str] = {
    "data_science_engineering", "artificial_intelligence", "computer_science_engineering",
    "computational_finance", "finance_banking", "economics_data_science",
    "business_management", "fintech", "econometrics", "computational_social_science",
    "computational_finance", "actuarial_science",
}
PURE_HUMANITIES_BUREAUCRATIC_FIELDS: Set[str] = {
    "education_teaching", "public_policy", "civil_services", "political_science",
    "liberal_arts_interdisciplinary", "philosophy", "sanskrit_classical_studies",
    "history_archaeology", "literature_languages", "international_relations",
    "development_studies", "geography", "library_information_science",
    "museum_heritage_studies",
}


def _nth_house_sign(lagna_sign: str, n: int) -> str:
    """Whole-sign nth house sign counted from the lagna (n=1 is the lagna
    sign itself, n=10 is the 10th house, etc.)."""
    if lagna_sign not in _SIGN_ORDER:
        return ""
    return _SIGN_ORDER[(_SIGN_ORDER.index(lagna_sign) + n - 1) % 12]


def apply_gap_2026_07_round3_corrections(
    results: List[Dict],
    payload_data: Any,
    eff_strengths: Dict[str, float],
    house_lords: Dict,
) -> List[Dict]:
    """Round 3: broadness-penalty wiring + Virgo-10th/Mercury-10th-lord
    accelerator. Same bounded/summed/capped discipline as rounds 1-2. Must
    run after attach_graph_diagnostics() (needs `graph_broadness_penalty`).
    """
    if not results:
        return results

    lagna_sign = getattr(payload_data, "lagna_sign", "") or ""
    tenth_sign = _nth_house_sign(lagna_sign, 10)
    tenth_lord = house_lords.get("10", "") or house_lords.get(10, "")
    all_effs = list(eff_strengths.values()) or [0.0]
    avg_eff = sum(all_effs) / len(all_effs)
    mercury_eff_ok = eff_strengths.get("Mercury", 0.0) >= avg_eff
    virgo_tenth_accelerator = (tenth_sign == "Virgo" or tenth_lord == "Mercury") and mercury_eff_ok

    for row in results:
        fid = row.get("field_id", "")
        pct_terms: List[float] = []
        notes: List[str] = []

        # ── Wire the (previously computed-but-unused) graph broadness
        # penalty directly into score. This was built in the 2026-07-04
        # ontology_kg.py pass specifically for generic/catch-all fields
        # (liberal_arts_interdisciplinary=0.18, mass_communication=0.12,
        # business_management=0.10, research_academia=0.15,
        # real_estate_management=0.20, unani_medicine=0.25, etc.) but its own
        # docstring flagged wiring it into score as a deliberate future
        # decision that was never made. It's a non-circular, already-curated
        # signal — safe to apply directly.
        bp = row.get("graph_broadness_penalty", 0.0) or 0.0
        if bp > 0:
            pct_terms.append(-bp)
            notes.append(f"graph_broadness_penalty: generic/catch-all field -{bp:.0%}")

        # ── Virgo-10th / Mercury-10th-lord accelerator ──────────────────
        # +/-22% rather than the more usual +/-15% used elsewhere in this
        # module: the exact 10th-house-sign + 10th-lord-in-own-sign-in-the-
        # 10th combination is one of the more textbook-strong career
        # significators in classical Jyotish (not a fuzzy inference), so it
        # earns a larger bounded swing. Still deliberately NOT a hard
        # override/forced-rank mechanism — this codebase already tried and
        # removed that pattern once (`_retain_priority_cluster_companions`,
        # see engine.py's own comment: "intentional product behaviour... as
        # code it looks like a demo artifact"). A single pass will move
        # affected fields meaningfully but will not guarantee an exact
        # target rank on its own.
        if virgo_tenth_accelerator:
            if fid in ANALYTICS_FINANCE_CONSULTING_FIELDS:
                pct_terms.append(0.22)
                notes.append("virgo_10th_mercury_accelerator: analytics/finance/consulting +22%")
            elif fid in PURE_HUMANITIES_BUREAUCRATIC_FIELDS:
                pct_terms.append(-0.22)
                notes.append("virgo_10th_mercury_accelerator: pure humanities/bureaucratic -22%")

        if pct_terms:
            total_pct = max(-0.45, min(0.40, sum(pct_terms)))
            row["final_score"] = round(row.get("final_score", 0.0) * (1.0 + total_pct), 2)
            existing_adj = row.get("gap_2026_07_round3_adjustment", 0.0)
            row["gap_2026_07_round3_adjustment"] = round(existing_adj + total_pct, 4)
            row["gap_2026_07_round3_notes"] = notes

    return results


def build_round2_audit_summary(results: List[Dict], top_n: int = 6) -> Dict[str, List[Dict]]:
    """Gap 15: self-audit — which fields were most demoted/promoted and why.

    Reads the notes round 1 and round 2 already attached per row; does not
    recompute anything. Intended to be surfaced in the report/CLI output so
    a parent/counsellor can see *why* e.g. Dentistry or Printing dropped.
    """
    demoted, promoted = [], []
    for row in results:
        adj = (row.get("gap_2026_07_adjustment", 0.0)
               + row.get("gap_2026_07_round2_adjustment", 0.0)
               + row.get("gap_2026_07_round3_adjustment", 0.0))
        if abs(adj) < 0.05:
            continue
        notes = ((row.get("gap_2026_07_notes", []) or [])
                 + (row.get("gap_2026_07_round2_notes", []) or [])
                 + (row.get("gap_2026_07_round3_notes", []) or []))
        entry = {"field_id": row.get("field_id", ""), "field_label": row.get("field_label", ""),
                 "net_adjustment": round(adj, 3), "reasons": notes}
        (demoted if adj < 0 else promoted).append(entry)
    demoted.sort(key=lambda e: e["net_adjustment"])
    promoted.sort(key=lambda e: -e["net_adjustment"])
    return {"demoted_fields": demoted[:top_n], "promoted_fields": promoted[:top_n]}
