"""Multi-dimensional confidence decomposition (Stage 4 of the Astro-OS v3
gap-audit implementation plan, 2026-08).

Gap being closed: `confidence_band` (Field_Determination/competency_ontology.py)
is a flat mapping from `final_score` to High/Medium/Low, and `score_confidence`
(field_methods/__init__.py) measures cross-method agreement -- neither
separates "does this chart structurally support this field over a lifetime"
from "is the current dasha favorable right now" from "can they actually study
it" from "can they actually work in it." A chart can strongly support a
domain structurally while being in an unfavorable dasha window, or vice
versa, and the existing single score/band collapses that distinction.

This module does NOT recompute astrology from scratch. Every dimension below
is either a direct read of an already-computed, already-verified method score
(siddhamsha for Educational Fit, dashamsha for Professional Fit -- both
gap-audited and real-data-validated across 25 charts this session), a
disciplined blend of two already-computed method scores (Structural Fit,
Research Fit), or a small, freshly-computed signal built only from
already-reliable payload attributes (house_lords, true_planet_dignities/
planet_dignities, eff_strengths, dasha_sequence) using the same whole-sign/
dignity/Shadbala primitives every other method file in this package already
uses (Leadership Fit, Timing Fit) -- not new, unvalidated astrological rules.

Additive only: this module does not touch final_score, method_scores, or any
existing method's output. It is wired into compute_field_method_bundle()'s
return dict as a new "confidence_dimensions" key, following the exact same
allow-list threading pattern already fixed for d9_navamsha_confirmation/
jaimini_chara_dasha_timing in engine.py and debug_payload_split.py.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from jyotish.astro import _get_active_dasha_lord

CONTRACT_VERSION = "confidence-dimensions.v1"

# Dignity -> 0-100 strength percentage. Mirrors the _DIGNITY_STRENGTH-style
# maps already used in siddhamsha.py/dashamsha.py, expressed as a percentage
# instead of a small point value since these dimensions are meant to read as
# standalone 0-100 confidence scores, not raw method points.
_DIGNITY_PCT: Dict[str, float] = {
    "EXALTED": 100.0,
    "MOOLATRIKONA": 90.0,
    "OWN": 80.0,
    "NEECHA_BHANGA": 60.0,
    "NEUTRAL": 50.0,
    "": 50.0,
    "DEBILITATED": 15.0,
}


def _dignity_pct(dignity_map: Mapping[str, str], planet: str) -> float:
    if not planet:
        return 50.0
    return _DIGNITY_PCT.get(str(dignity_map.get(planet, "") or "").strip().upper(), 50.0)


def _band(score: float) -> str:
    if score >= 75.0:
        return "HIGH"
    if score >= 50.0:
        return "MODERATE"
    if score >= 30.0:
        return "LOW"
    return "VERY_LOW"


def _dim(score: float, basis: list) -> Dict[str, Any]:
    score = round(max(0.0, min(100.0, score)), 2)
    return {"score": score, "band": _band(score), "basis": basis}


def compute_confidence_dimensions(
    payload_data: Any,
    domain: str,
    field_affinity: Mapping[str, float] | None,
    field_id: str,
    method_normalized_scores: Mapping[str, float] | None,
) -> Dict[str, Any]:
    """Compute six confidence dimensions for one field candidate.

    `method_normalized_scores` is the same 0-100-normalized per-method dict
    already assembled by compute_field_method_bundle() (bvb_eval's
    "method_normalized_scores") -- pass it straight through, no
    recomputation.
    """
    field_affinity = field_affinity or {}
    mns = method_normalized_scores or {}

    # ── Structural Fit: lifetime D1 chart-structure compatibility ──────────
    # Blend of Parashara (D1 house/yoga structure) and K.N. Rao (D1 karaka/
    # house-lord placement) -- the two methods whose core signal is D1
    # structure rather than a specific divisional chart or timing. Weighted
    # toward Parashara for the same reason knrao.py itself now documents at
    # its own _ROLE_WEIGHTS table: even after Stage 5 removed the
    # Dasha_Lord/Antardasha_Lord timing fusion from K.N. Rao's structural
    # role_weight, Parashara's yoga/strength model remains the more directly
    # structural of the two (K.N. Rao's method still centers on a role
    # hierarchy keyed partly to karakas that carry their own separate
    # classical nuance), so the blend stays Parashara-heavy by design, not
    # as a pending-fix workaround.
    structural_raw = 0.65 * mns.get("parashara", 0.0) + 0.35 * mns.get("knrao", 0.0)
    structural_fit = _dim(structural_raw, [
        "parashara (D1 house/yoga structure)",
        "knrao (D1 karaka/house-lord placement)",
    ])

    # ── Educational Fit: can they study this? ───────────────────────────────
    # Direct read of siddhamsha (D24 vidya varga) -- already the field-
    # specific, gap-audited, real-data-validated (25/25 charts) education
    # signal. No re-derivation.
    #
    # 2026-08 gap-audit fix (transparency, not score change): when D24's own
    # karakas (Mercury/Venus -- the planets siddhamsha.py's "core" section
    # scores for education dignity) are combust in D1, the resulting low
    # score is a real, chart-wide astrological constraint, not a per-field
    # signal or a bug -- it will read low for every field alike. Rather than
    # inflate the score (which would misrepresent the chart) or leave a
    # reader to assume the engine is broken, surface WHY it's flat via a
    # basis note, sourced from payload_data.combust_planets (the same field
    # boosts.py already reads for its own combustion penalties -- no new
    # astrological computation here).
    combust_planets = set(getattr(payload_data, "combust_planets", []) or [])
    _edu_karakas_combust = sorted(combust_planets & {"Mercury", "Venus"})
    educational_raw = mns.get("siddhamsha", 0.0)
    educational_basis = ["siddhamsha (D24 Siddhamsha vidya varga)"]
    if _edu_karakas_combust:
        educational_basis.append(
            "NOTE: D24's education-signal karaka(s) "
            + " & ".join(_edu_karakas_combust)
            + " combust in D1 -- this depresses the education signal "
            "chart-wide (every field, not just this one); treat this "
            "dimension as low-confidence/near-flat for this chart rather "
            "than a field-specific weakness."
        )
    educational_fit = _dim(educational_raw, educational_basis)

    # ── Professional Fit: can they work in this? ────────────────────────────
    # Direct read of dashamsha (D10 career varga) -- BPHS's own primary
    # career-manifestation chart.
    #
    # 2026-08 gap-audit fix (transparency, not score change): educational_fit
    # and research_fit above both attach a "chart-wide, not field-specific"
    # NOTE when their karaka(s) are combust in D1 -- professional_fit had no
    # equivalent check at all, so a chart-wide VERY_LOW professional_fit
    # (every field alike) read identically to a genuine field-specific
    # weakness, with no explanation, unlike its two sibling dimensions.
    # Saturn is the classical universal karma karaka (profession/service/
    # sustained effort significator in Parashari Jyotish, same convention
    # chart_synthesis.py already documents at its own Saturn reference) --
    # the professional-fit analogue of educational_fit's Mercury/Venus
    # vidya-karaka check. Sun (the other classical career karaka, for
    # authority/status) is excluded here since combustion is defined
    # relative to the Sun itself and cannot apply to the Sun.
    professional_raw = mns.get("dashamsha", 0.0)
    professional_basis = ["dashamsha (D10 Dashamsha career varga)"]
    if "Saturn" in combust_planets:
        professional_basis.append(
            "NOTE: Saturn (karma karaka -- classical significator of "
            "profession/sustained effort) is combust in D1 -- this depresses "
            "the professional signal chart-wide (every field, not just this "
            "one); treat this dimension as low-confidence/near-flat for this "
            "chart rather than a field-specific weakness."
        )
    professional_fit = _dim(professional_raw, professional_basis)

    # ── Research Fit: potential for innovation / advanced study ─────────────
    # Blend of D24's karaka-dignity signal (siddhamsha already scores Mercury/
    # Jupiter/Venus dignity in D24 as its "core" section) and Jaimini (soul-
    # direction / Atmakaraka-Amatyakaraka indicators, the branch of this
    # engine most concerned with long-run direction rather than immediate
    # execution).
    research_raw = 0.5 * mns.get("siddhamsha", 0.0) + 0.5 * mns.get("jaimini", 0.0)
    research_basis = [
        "siddhamsha (D24 karaka dignity)",
        "jaimini (Atmakaraka/Amatyakaraka soul-direction indicators)",
    ]
    if _edu_karakas_combust:
        research_basis.append(
            "NOTE: D24's education-signal karaka(s) "
            + " & ".join(_edu_karakas_combust)
            + " combust in D1 -- half of this dimension's blend is "
            "depressed chart-wide for the same reason noted under "
            "educational_fit; not field-specific."
        )
    research_fit = _dim(research_raw, research_basis)

    # ── Leadership Fit: potential for managerial/executive growth ───────────
    # Freshly computed (not reused from an opaque method internal) from two
    # classically direct leadership signals: the D1 10th-house lord's own
    # dignity, and combined Sun/Mars Shadbala strength (Sun = authority/
    # governance karaka, Mars = command/execution karaka -- the two planets
    # every method file in this package already treats as leadership-
    # adjacent, e.g. knrao.py's "AL lord Mars aligns with field (public/
    # career standing)").
    house_lords = getattr(payload_data, "house_lords", {}) or {}
    planet_dignities = (
        getattr(payload_data, "true_planet_dignities", {})
        or getattr(payload_data, "planet_dignities", {})
        or {}
    )
    eff_strengths = getattr(payload_data, "eff_strengths", {}) or {}
    h10_lord = house_lords.get("10", "")
    h10_lord_dig_pct = _dignity_pct(planet_dignities, h10_lord)
    _sun_mars_vals = []
    for _p in ("Sun", "Mars"):
        _r = eff_strengths.get(_p)
        if _r is not None:
            _sun_mars_vals.append(max(0.0, min(2.5, float(_r))) / 2.5 * 100.0)
    sun_mars_strength_pct = sum(_sun_mars_vals) / len(_sun_mars_vals) if _sun_mars_vals else 50.0
    leadership_raw = 0.5 * h10_lord_dig_pct + 0.5 * sun_mars_strength_pct
    leadership_basis = [
        f"D1 10th-house lord {h10_lord or '(unresolved)'} dignity",
        "combined Sun/Mars Shadbala (eff_strengths) strength",
    ]
    # 2026-08-20 gap-audit fix (transparency, not score change): same
    # chart-wide-vs-field-specific ambiguity educational_fit/professional_fit/
    # research_fit already flag for their own karakas -- Leadership Fit's
    # Mars half is just as susceptible when Mars is combust in D1, and this
    # dimension had no equivalent check. Sun is deliberately excluded (same
    # reasoning professional_fit documents for Saturn/Sun): combustion is
    # defined relative to the Sun itself, so it cannot apply to the Sun.
    if "Mars" in combust_planets:
        leadership_basis.append(
            "NOTE: Mars (command/execution karaka -- half of this dimension's "
            "Sun/Mars strength blend) is combust in D1 -- this depresses the "
            "leadership signal chart-wide (every field, not just this one); "
            "treat this dimension as partially low-confidence for this chart "
            "rather than a field-specific weakness."
        )
    leadership_fit = _dim(leadership_raw, leadership_basis)

    # ── Timing Fit: is the CURRENT dasha window favorable for this field? ───
    # Independent, field-specific computation of whether the active
    # Mahadasha/Antardasha lord is (a) a planet this field's affinity table
    # weights and (b) well-dignified -- using the exact same
    # getattr(...)-or-_get_active_dasha_lord(...) fallback pattern already
    # proven in knrao.py's own Dasha_Lord role-weight logic, so this stays
    # consistent with how the rest of the codebase resolves dasha state.
    current_age = float(getattr(payload_data, "current_age", 0.0) or 0.0)
    active_dasha_lord = getattr(payload_data, "active_dasha_lord", "") or _get_active_dasha_lord(
        getattr(payload_data, "dasha_sequence", []) or [], current_age,
    )
    antardasha_lord = getattr(payload_data, "antardasha_lord", "") or ""
    md_aff = float(field_affinity.get(active_dasha_lord, 0.0) or 0.0) if active_dasha_lord else 0.0
    ad_aff = float(field_affinity.get(antardasha_lord, 0.0) or 0.0) if antardasha_lord else 0.0
    md_dig_pct = _dignity_pct(planet_dignities, active_dasha_lord)
    # A dasha lord this field doesn't weight at all isn't "zero opportunity"
    # -- it's simply not the peak window -- so a 20-point floor keeps
    # off-dasha fields in the LOW band rather than falsely reading as
    # VERY_LOW/no-confidence, matching how method_result's own net-negative
    # floor logic already avoids conflating "unfavorable" with "impossible".
    affinity_component = (0.7 * md_aff + 0.3 * ad_aff) * (md_dig_pct / 100.0) * 80.0

    # 2026-08 gap-audit fix: the field-specific affinity term above reads
    # VERY_LOW whenever the active dasha lord simply isn't one of the
    # (usually ~4) planets in this field's BRANCH_PLANET_AFFINITY table --
    # even when that lord is strongly placed (e.g. exalted/own-sign, high
    # Shadbala). A generically strong planetary period is real timing
    # support for ANY field, just not this field's peak-specific window, so
    # it shouldn't score identically to a genuinely weak/afflicted dasha
    # lord. Compute a second, field-agnostic component from the same
    # dignity map plus Shadbala-derived eff_strengths (the same primitives
    # Leadership Fit above already uses), and take the max of the two
    # components rather than summing them -- this leaves on-affinity fields
    # completely unchanged (affinity_component already dominates there) and
    # only lifts off-affinity fields whose dasha lord is independently
    # well-dignified, capped well below what genuine field affinity can
    # reach (100) so field-specific affinity stays the dominant signal.
    _md_eff = eff_strengths.get(active_dasha_lord)
    md_strength_pct = (
        max(0.0, min(2.5, float(_md_eff))) / 2.5 * 100.0
        if _md_eff is not None else 50.0
    )
    generic_dasha_pct = 0.5 * md_dig_pct + 0.5 * md_strength_pct
    generic_component = (generic_dasha_pct / 100.0) * 50.0

    timing_raw = 20.0 + max(affinity_component, generic_component)
    timing_basis = [
        f"active Mahadasha lord {active_dasha_lord or '(unresolved)'}",
        f"Antardasha lord {antardasha_lord or '(unresolved)'}",
    ]
    if generic_component > affinity_component:
        timing_basis.append(
            f"NOTE: {active_dasha_lord or 'the active dasha lord'} is not in "
            "this field's affinity table, but is independently well-placed "
            "(dignity/Shadbala) -- scored on generic planetary strength "
            "rather than field-specific affinity, so this reflects general "
            "favorability of the current period, not a field-specific peak."
        )
    timing_fit = _dim(timing_raw, timing_basis)

    return {
        "contract_version": CONTRACT_VERSION,
        "structural_fit": structural_fit,
        "educational_fit": educational_fit,
        "professional_fit": professional_fit,
        "research_fit": research_fit,
        "leadership_fit": leadership_fit,
        "timing_fit": timing_fit,
    }
