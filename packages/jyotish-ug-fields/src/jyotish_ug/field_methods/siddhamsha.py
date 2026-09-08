"""Siddhamsha (D24) field-determination module.

BPHS designates D24 as the dedicated varga for vidya (learning, education,
scholarship). Historically this module only produced a curriculum-intensity
"confirmation" score (`independent_vote: False`) that never reached the
method bundle's final_score. Phase-1 remediation (2026-08): D24 is promoted
to a full, independently-voting 7th method — mirroring the D10/Dashamsha
pattern (self-contained divisional chart, own lagna, own house lords, own
functional-status table) but anchored to the houses and karakas classical
authors use for vidya rather than career:

  - D24 Lagna lord dignity/strength     (self, capacity to absorb learning)
  - D24 4th-lord placement & dignity    (foundational/early education)
  - D24 5th-lord placement & dignity    (intelligence, purva-punya, higher study)
  - D24 9th-lord placement & dignity    (higher wisdom, guru, advanced study)
  - Mercury/Jupiter/Venus (vidya karakas) dignity + house placement in D24
  - Curriculum-intensity match (legacy component, preserved as "validation")
  - Penalty: vidya-house lords in dusthana or combust in D24

Scoring rubric (raw section caps sum to METHOD_SCORE_CAPS["siddhamsha"] = 85.0
-- core 40 + support 25 + validation 20, same convention as kp/parashara/
dashamsha.py; the runtime `normalization_cap=35.0` passed to method_result()
below is a separate, deliberately smaller per-method normalization ceiling
used when blending this method into the bundle's final_score, NOT the raw
score's own cap -- this docstring previously said "raw cap ~35, normalization
cap 35", which conflated the two and never matched the actual 85-point raw
rubric below; corrected 2026-08-17):
  Core       (~40 pts) — D24 lagna lord dignity/strength, karaka strength
  Support    (~25 pts) — D24 4th/5th/9th lord placement & dignity, plus
                          vidya-house occupants (correlation-discounted
                          against the same planet's lord-placement credit
                          when it coincides with occupying a vidya house)
  Validation (~20 pts) — curriculum-intensity match, karaka-in-own-house bonus
  Penalty    (up to -15) — vidya-house lords in dusthana / combust in D24

2026-08-17 audit fix (support-vs-occupant duplication): the vidya-house-
lord "support" component and the vidya-house "occupants" component (added
in the Phase-5/gap-audit "addition 3 of 3" pass) could both score the exact
same planet-in-the-exact-same-house fact whenever a vidya-house lord
happened to physically occupy one of the _VIDYA_HOUSES -- e.g. the D24 5th
lord sitting in D24's own 9th house got its dignity/placement credited
once as "lord of H5 landing in H9" and again as "occupant of H9", with no
correlation discount, mirroring the already-fixed dashamsha.py C1/V1 issue.
A 0.5 correlation discount (same magnitude as dashamsha's
_V1_CORRELATION_DISCOUNT) is now applied to the occupant-loop contribution
specifically in that coincidence case; genuinely distinct lord/occupant
facts (different planets) are unaffected.

Phase-3b remediation (2026-08, real-data validation finding): a live run
(Midhula chart) showed this method's raw score identical across every field
(34.6 for ceramic/mechanical/nuclear engineering alike), because core+support
never referenced `field_affinity` — 65 of 85 raw points were pure chart
facts. Fixed: every core/support component is now scaled by an
affinity-derived multiplier in [0.35, 1.0] (floored, not zeroed, so general
D24 learning-capacity still counts for fields the lagna lord/karakas don't
specifically rule) — see `_affinity_mult()` below.

2026-08-20 score-calibration fixes (Claude session, real-chart audit
following the KNRao artha-house fix on the same chart): a live run
(Ramsunder) showed siddhamsha's whole raw-score distribution compressed
into a ~2.6-point range across 35 very different candidate fields, with
materials/space/aerospace engineering landing at or near the literal
bottom of the chart's own D24 ranking. Two contributing causes:
  - `curriculum_fit` (up to 20 raw pts, the single largest realized
    component) took only 4 distinct values across all 35 fields -- see
    `_curriculum_match()`'s own docstring for the fix (a hard capacity
    threshold rarely cleared by realistic affinity weights, replaced with
    a continuous floor-to-ceiling scale).
  - `vidya_karaka_strength` (up to 25 raw pts) was scaled by each field's
    own affinity for Mercury/Jupiter/Venus specifically -- which
    systematically favored law/teaching/commerce/arts (naturally ruled by
    those three) over Mars/Saturn/Rahu/Ketu-ruled fields like engineering,
    regardless of actual D24 structural support. Floor raised from 0.35 to
    0.65 for this component only (see the _KARAKA_MIN_AAF comment above
    the vidya-karaka loop) so it stays closer to the general-capacity
    signal it classically represents.

Phase-5 remediation note (2026-08 gap-audit): jyotish/edu_align.py's
compute_d1_d24_stream_score() also reads D24 data from the payload, via a
different attribute path (payload.d24_lagna_sign / payload.d24_house_lords
vs. this module's payload.divisional_charts["D24_siddhamsam"]). Both share
payload.d24_planet_dignities as a single source, so dignity readings cannot
drift, but see edu_align.py's docstring for the full reconciliation note —
the two are deliberately kept separate (coarse stream classification vs.
fine-grained per-field score), not merged.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from jyotish.constants import _SIGN_LORD, _SIGN_NUM, _DUSTHANA_HOUSES, _KT_HOUSES
from jyotish.boosts import _vimsopaka_bala_coefficient
from .common import (
    build_gate_text,
    build_score_rubric,
    clamp_score,
    method_result,
    rubric_section,
    top_weighted_planets,
)

# ── Legacy curriculum-intensity match (preserved from the original module) ──
PLANET_DIM = {
    "Mercury": ("math_intensity", "coding_intensity", "writing_intensity"),
    "Mars":    ("physics_intensity", "fieldwork_intensity"),
    "Jupiter": ("writing_intensity", "people_interaction"),
    "Venus":   ("people_interaction", "writing_intensity"),
    "Moon":    ("biology_intensity", "people_interaction"),
    "Saturn":  ("math_intensity", "fieldwork_intensity"),
    "Rahu":    ("coding_intensity", "physics_intensity"),
    "Ketu":    ("math_intensity", "physics_intensity"),
}
STRONG = {
    "EXALTED": 1.0, "OWN": .85, "OWN_SIGN": .85, "MOOLATRIKONA": .9,
    "FRIEND": .65, "NEUTRAL": .5, "ENEMY": .3, "DEBILITATED": .1,
}

# Vidya karakas per classical doctrine (Mercury=learning/intellect,
# Jupiter=wisdom/higher knowledge, Venus=arts/refined learning).
_VIDYA_KARAKAS = ("Mercury", "Jupiter", "Venus")

# Houses relevant to education per Parashara/K.N. Rao: 4th (early/formal
# education), 5th (intelligence, purva-punya, higher learning), 9th (higher
# wisdom, guru, advanced/foreign study).
_VIDYA_HOUSES = (4, 5, 9)

_DIGNITY_STRENGTH = {
    "EXALTED": 10.0, "OWN": 8.0, "OWN_SIGN": 8.0, "MOOLATRIKONA": 8.5,
    "FRIEND": 5.5, "NEUTRAL": 4.0, "ENEMY": 2.0, "DEBILITATED": 0.5,
}

_LAGNA_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


def _d24_house_lord(d24_lagna: str, house_num: int) -> str:
    """Lord of the Nth house in D24 using whole-sign house system."""
    if not d24_lagna or d24_lagna not in _SIGN_NUM:
        return ""
    lagna_idx = _SIGN_NUM[d24_lagna] - 1
    target_idx = (lagna_idx + house_num - 1) % 12
    target_sign = _LAGNA_SIGN_ORDER[target_idx]
    return _SIGN_LORD.get(target_sign, "")


def _d24_planet_house(planet: str, d24_chart: Dict, d24_lagna: str) -> int:
    """Whole-sign house of a planet within D24, given D24 lagna sign."""
    if not d24_lagna or d24_lagna not in _SIGN_NUM:
        return 0
    planet_sign = (d24_chart or {}).get(planet, "")
    if not planet_sign or planet_sign not in _SIGN_NUM:
        return 0
    lagna_num = _SIGN_NUM[d24_lagna]
    planet_num = _SIGN_NUM[planet_sign]
    return ((planet_num - lagna_num) % 12) + 1


_CURRICULUM_CAP_FLOOR = 0.35  # matches _MIN_AAF's floor convention elsewhere in this module
_CURRICULUM_CAP_SCALE = 2.5


def _curriculum_match(payload: Any, field_entry: Mapping, field_affinity: Mapping[str, float] | None) -> tuple[float, Dict]:
    """Legacy intensity-fit score, preserved as the 'validation' rubric section.

    Score-calibration fix (2026-08-20, Claude session, real-chart audit): the
    old formula started every requirement dimension at a flat 0.5 "capacity"
    and only raised it via `max(capacity[dim], strength * weight * 2.0)`. With
    this codebase's typical field-affinity weights (a field's top planet is
    usually ~0.15-0.4) and neutral dignity (strength 0.5), that product tops
    out around 0.3-0.4 -- it almost never cleared the 0.5 floor unless a
    planet was BOTH exalted/own-dignity AND unusually high-affinity. The
    result, confirmed on a real chart (Ramsunder): `curriculum_fit` (up to 20
    of this method's 85 raw points -- the single largest realized component)
    took only 4 distinct values across all 35 candidate fields, clustered in
    a 1-point band, regardless of whether the field was law, medicine, or
    materials engineering -- the exact "identical across every field" failure
    this module's own Phase-3b docstring already diagnosed and fixed for the
    core/support sections, just missed here.

    Replaced with a continuous floor-to-ceiling scale: capacity for a
    dimension starts at _CURRICULUM_CAP_FLOOR (no signal at all) and rises
    smoothly toward 1.0 as the best-matching planet's dignity x affinity
    signal strengthens, instead of needing to clear a fixed threshold before
    any credit shows up at all. _CURRICULUM_CAP_SCALE is calibrated so a
    strong real signal (an exalted top planet at affinity ~0.4) reaches close
    to the 1.0 ceiling, while a typical modest signal (neutral dignity,
    affinity ~0.2-0.3) still produces a clearly visible rise above the floor
    -- restoring this section's ability to differentiate fields instead of
    behaving as a near-constant ~50% match for the large majority of charts.
    """
    digs = getattr(payload, "d24_planet_dignities", {}) or {}
    curriculum = (field_entry or {}).get("curriculum", {}) or {}
    if not digs:
        return 0.0, {}
    requirements = {
        k: max(0.0, min(1.0, float(v or 0) / 5.0))
        for k, v in curriculum.items()
        if k.endswith("_intensity") or k == "people_interaction"
    }
    if not requirements:
        return 0.0, {}
    capacity = {k: _CURRICULUM_CAP_FLOOR for k in requirements}
    for planet, weight in (field_affinity or {}).items():
        strength = STRONG.get(str(digs.get(planet, "NEUTRAL")).upper(), .5)
        raw_signal = min(1.0, strength * float(weight) * _CURRICULUM_CAP_SCALE)
        scaled = _CURRICULUM_CAP_FLOOR + (1.0 - _CURRICULUM_CAP_FLOOR) * raw_signal
        for dim in PLANET_DIM.get(planet, ()):
            if dim in capacity:
                capacity[dim] = max(capacity[dim], scaled)
    denom = sum(requirements.values())
    match = 50.0 if denom <= 0 else 100 * sum(requirements[k] * min(1, capacity[k]) for k in requirements) / denom
    return match, {"requirements": requirements, "capacity": capacity}


def score_siddhamsha(
    payload: Any,
    domain: str = "",
    field_affinity: Mapping[str, float] | None = None,
    field_id: str = "",
    field_entry: Mapping = None,
) -> Dict[str, Any]:
    """Score a candidate field from the D24 Siddhamsha chart as an independent
    voting method (Phase-1 remediation — previously confirmation-only).

    Signature intentionally mirrors the other six method scorers
    (score_knrao, score_kp, score_jaimini, score_parashara, score_dashamsha,
    score_sudarshana) so it wires into compute_field_method_bundle uniformly.
    """
    trace: List[str] = []
    components: Dict[str, float] = {}
    score = 0.0

    divisional_charts = getattr(payload, "divisional_charts", {}) or {}
    d24_chart = divisional_charts.get("D24_siddhamsam", {}) or {}
    # Phase-6 validation finding: jyotish/tests/test_d24_construction.py pins
    # compute_d24_chart() as producing a FLAT planet-sign dict with NO
    # "Lagna" key ("D24 lagna cannot be independently re-derived -- no
    # lagna_degree field on NatalPayloadV2"). A naive d24_chart.get("Lagna")
    # lookup would therefore silently return "" on real charts even when
    # D24 planet data is present. jyotish/edu_align.py's
    # compute_d1_d24_stream_score() already solves this by reading a
    # separately-populated `payload.d24_lagna_sign` attribute (set upstream
    # in engine_io.py/payload.py, outside compute_d24_chart itself) — reuse
    # that same attribute here rather than re-deriving or guessing.
    d24_lagna = (
        d24_chart.get("Lagna", "") or d24_chart.get("lagna", "")
        or getattr(payload, "d24_lagna_sign", "") or ""
    )
    # Gap-audit fix (2026-08, round 4): same cosmetic issue fixed in
    # dashamsha.py's d10_digs -- compute_dignity() legitimately returns ""
    # (not "NEUTRAL") for a resolved sign that isn't exalted/debilitated/
    # own, so every `.get(planet, "NEUTRAL")` below only applied its default
    # when the key was absent, letting a present-but-""-valued dignity
    # render as a blank in trace text (e.g. "dignity= (field-affinity
    # x0.35)"). Coalescing here fixes every downstream lookup at once.
    d24_dignities = {
        p: (d or "NEUTRAL") for p, d in (getattr(payload, "d24_planet_dignities", {}) or {}).items()
    }
    # Gap-audit fix (2026-08, D24 data-quality investigation): before this
    # fix, d24_dignities.get(planet, "NEUTRAL") could not distinguish a
    # planet the upstream D24_siddhamsam response genuinely left unresolved
    # (empty sign string -- pyhora returned partial data) from a planet
    # whose sign WAS resolved and simply isn't exalted/debilitated/own
    # (the classically correct, and statistically most common, outcome --
    # neutral is the default state for ~9 of 12 possible sign placements).
    # engine_io.py's d24_planet_dignities builder now only emits an entry
    # for planets with an actual resolved sign, and separately records
    # unresolved ones in d24_missing_planets, so this trace can report
    # which "NEUTRAL" readings below are chart-confirmed vs. data gaps.
    d24_missing = list(getattr(payload, "d24_missing_planets", []) or [])
    if d24_missing:
        trace.append(
            f"D24 data-quality: no resolvable D24 sign for {', '.join(d24_missing)} "
            "(upstream D24 chart incomplete for this planet) -- dignity for these "
            "planets falls back to a NEUTRAL default rather than a chart-confirmed "
            "reading, and their D24 house cannot be resolved."
        )

    if not d24_chart or not d24_lagna:
        rubric = build_score_rubric("siddhamsha", [
            rubric_section("core", 0, 40, note="D24 chart unavailable"),
        ])
        _early_result = method_result(
            "siddhamsha", 0.0, ["D24 (Siddhamsha) chart data unavailable — method skipped."],
            {}, rubric=rubric, normalization_cap=35.0,
        )
        # gap fix 2026-08-18 (item 12): D24/Siddhamsha is a contributing voting
        # tier within the method-bundle blend (see METHOD_WEIGHTS), never a
        # method that gets to unconditionally/"permanently" force a
        # suitability verdict on its own regardless of other methods' votes.
        # `permanent_vote` makes that explicit in the returned contract so a
        # downstream consumer can assert D24 never short-circuits the blend.
        _early_result["permanent_vote"] = False
        # gap fix 2026-08-18 (item 12): `educational_suitability` is the
        # public-contract alias for this method's score (mirrored from
        # score_siddhamsha_legacy's contract below) -- it was never populated
        # on the non-legacy scorer's early-return path, leaving downstream
        # consumers of that contract key with a KeyError-adjacent None.
        _early_result["educational_suitability"] = _early_result.get("score", 0.0)
        return _early_result

    # Phase-3b remediation (2026-08, real-data validation finding): on a live
    # run (Midhula chart, 2026-08-14) siddhamsha's raw score came out
    # IDENTICAL (34.6) across ceramic/mechanical/nuclear engineering, because
    # the core (lagna-lord + karaka dignity) and support (4th/5th/9th lord
    # placement) sections below were pure chart facts with no dependence on
    # `field_affinity` -- 65 of D24's 85 raw points were field-invariant,
    # defeating its purpose as a per-field ranking signal even though it now
    # correctly holds a 20% vote. Every other method (Parashara/KNRao/KP)
    # weights its core signals by field_affinity.get(planet); this module did
    # not. Fixed by scaling each planet's contribution by an affinity-derived
    # multiplier in [_MIN_AAF, 1.0] -- floored (not zeroed) so a chart's
    # general D24 capacity to absorb learning still counts for fields the
    # lagna lord/karakas don't specifically rule, matching how Parashara's
    # vidya-karaka block (added in the same audit pass) already behaves.
    _MIN_AAF = 0.35  # floor: even zero-affinity fields still see general D24 capacity

    def _affinity_mult(planet: str) -> float:
        aff = float((field_affinity or {}).get(planet, 0.0) or 0.0)
        return _MIN_AAF + (1.0 - _MIN_AAF) * max(0.0, min(1.0, aff))

    # Score-calibration fix (2026-08-20, Claude session, real-chart audit):
    # the vidya-karaka dignity block below (up to 25 of this method's 40 core
    # points -- the largest single component) previously used the same
    # _MIN_AAF=0.35 floor as everything else, scaled by THAT field's own
    # affinity for Mercury/Jupiter/Venus specifically. But the vidya karakas
    # classically represent GENERAL learning capacity/intellect, not a
    # field-specific rulership the way a D10-style structural house-lord
    # placement is -- and Mercury/Jupiter/Venus happen to be the natural
    # significators of exactly the fields (law, teaching, commerce, arts)
    # that also cleared this floor easily, while fields naturally ruled by
    # Mars/Saturn/Rahu/Ketu (materials/space/aerospace engineering, etc.)
    # floored at 0.35 on all three karakas almost by construction, regardless
    # of their actual D24 structural support. Confirmed on a real chart
    # (Ramsunder): international_law's vidya_karaka_strength (3.49) vs.
    # materials_science_engineering's (2.55) tracked Jupiter/Mercury being
    # law's own top affinities, not any difference in D24 educational fit.
    # Raised specifically for this component to 0.65 -- keeping the karaka
    # dignity block closer to the field-invariant "general capacity" signal
    # it classically should be, while still allowing some field-relevant
    # lift. Per-field differentiation now leans more on the house-lord
    # support section (already field-relevant via variable, chart-specific
    # 4th/5th/9th lords) and the newly-recalibrated curriculum_fit validation
    # section (see _curriculum_match) rather than this component alone.
    _KARAKA_MIN_AAF = 0.65

    def _karaka_affinity_mult(planet: str) -> float:
        aff = float((field_affinity or {}).get(planet, 0.0) or 0.0)
        return _KARAKA_MIN_AAF + (1.0 - _KARAKA_MIN_AAF) * max(0.0, min(1.0, aff))

    # D24 gap-audit fix (2026-08), addition 1 of 3: birth-time boundary risk.
    # dashamsha.py already built this exact pattern for D10 (3-degree
    # segments) earlier this session, but it was never ported here even
    # though D24 divides each sign into 24 segments of 1.25 degrees each --
    # FOUR TIMES finer than D10's 3-degree segments, making D24 sign
    # (therefore dignity and house) MORE vulnerable to plausible birth-time
    # error, not less. Same bounded [0.85, 1.0] multiplier, only applied to
    # planets actually near a 1.25-degree segment boundary, only when birth
    # time isn't exact.
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    _birth_prec_d24 = (
        getattr(getattr(payload, "calculation_policy", None), "birth_time_precision", None)
        or getattr(payload, "birth_time_precision", "exact") or "exact"
    )
    _d24_margin_deg = {"approximate": 0.15, "unknown": 0.40}.get(_birth_prec_d24, 0.0)

    def _d24_boundary_mult(planet: str) -> float:
        if not planet or _d24_margin_deg <= 0.0:
            return 1.0
        pdata = planets_d1.get(planet, {}) or {}
        try:
            deg = float(pdata.get("degree"))
        except (TypeError, ValueError):
            return 1.0
        deg_in_segment = deg % 1.25
        near_boundary = deg_in_segment <= _d24_margin_deg or deg_in_segment >= (1.25 - _d24_margin_deg)
        return 0.85 if near_boundary else 1.0

    # D24 gap-audit fix (2026-08), addition 2 of 3: Shadbala/eff_strengths
    # multiplier. dashamsha.py's own docstring flags this exact blind spot
    # ("the one method that ignored planetary Shadbala entirely") and fixed
    # it for D10 -- siddhamsha never got the same fix, so a classically weak
    # (low Shadbala) lagna lord/karaka still scores identically here to a
    # strong one at the same sign dignity. Same bounded [0.85, 1.20] range,
    # narrower than dignity's own multiplier since the two signals correlate.
    _eff_strengths_d24 = getattr(payload, "eff_strengths", {}) or {}

    def _str_mult_d24(planet: str) -> float:
        if not planet:
            return 1.0
        ratio = _eff_strengths_d24.get(planet)
        if ratio is None:
            return 1.0
        return round(max(0.85, min(1.20, 0.85 + (ratio / 2.5) * 0.35)), 4)

    # ── Core (~40 pts): D24 lagna lord strength + vidya-karaka dignity ──────
    lagna_lord = _SIGN_LORD.get(d24_lagna, "")
    lagna_lord_dig = str(d24_dignities.get(lagna_lord, "NEUTRAL")).upper()
    lagna_lord_strength = _DIGNITY_STRENGTH.get(lagna_lord_dig, 4.0)
    _lagna_aaf = _affinity_mult(lagna_lord) if lagna_lord else _MIN_AAF
    _lagna_bmult = _d24_boundary_mult(lagna_lord) if lagna_lord else 1.0
    _lagna_smult = _str_mult_d24(lagna_lord) if lagna_lord else 1.0
    core = lagna_lord_strength * 1.5 * _lagna_aaf * _lagna_bmult * _lagna_smult  # up to 15
    components["d24_lagna_lord_strength"] = round(core, 2)
    trace.append(
        f"D24 lagna {d24_lagna}, lord {lagna_lord or '—'} dignity={lagna_lord_dig} "
        f"(field-affinity x{round(_lagna_aaf,2)}, Shadbala x{round(_lagna_smult,2)}) -> {round(core,2)} pts"
    )
    if lagna_lord and _lagna_bmult < 1.0:
        trace.append(f"D24 boundary risk: lagna lord {lagna_lord} sits within {_d24_margin_deg} deg "
                      f"of a 1.25-degree D24 segment boundary -- contribution discounted.")

    karaka_total = 0.0
    _d24_boundary_flagged = []
    for karaka in _VIDYA_KARAKAS:
        dig = str(d24_dignities.get(karaka, "NEUTRAL")).upper()
        strength = _DIGNITY_STRENGTH.get(dig, 4.0)
        _k_aaf = _karaka_affinity_mult(karaka)
        _k_bmult = _d24_boundary_mult(karaka)
        _k_smult = _str_mult_d24(karaka)
        if _k_bmult < 1.0:
            _d24_boundary_flagged.append(karaka)
        _karaka_pts = strength * _k_aaf * _k_bmult * _k_smult
        # 2026-08-22 reconciliation (JyotishAI reference-audit, siddhamsha.py):
        # when a vidya-karaka IS the D24 lagna lord (e.g. Mercury-ruled D24
        # lagna), this loop re-scores that SAME planet's SAME D24 dignity a
        # second time on top of the "core" lagna-lord-strength component
        # above -- the identical overlap this file's own occupant-loop
        # comment already names and mitigates for a different pair of
        # components (_OCCUPANT_CORRELATION_DISCOUNT), left unmitigated
        # here. Same 0.5 discount applied for consistency.
        if karaka == lagna_lord:
            _karaka_pts *= 0.5
        karaka_total += _karaka_pts
        trace.append(f"D24 karaka {karaka} dignity={dig} (field-affinity x{round(_k_aaf,2)}, "
                     f"Shadbala x{round(_k_smult,2)}) -> {round(_karaka_pts,2)}"
                     f"{' (correlation-discounted: same planet as D24 lagna lord)' if karaka == lagna_lord else ' raw'}")
    karaka_component = min(25.0, karaka_total * 0.85)  # up to 25
    components["vidya_karaka_strength"] = round(karaka_component, 2)
    core_total = min(40.0, core + karaka_component)
    score += core_total

    # ── Support (~25 pts): 4th/5th/9th lord placement + dignity in D24 ──────
    support = 0.0
    house_notes = []
    # 2026-08-17 audit fix: track which planets were already credited here as
    # a vidya-house LORD (and which house they physically occupy), so the
    # occupant loop below can detect -- and discount -- the case where it
    # would otherwise re-score the identical planet-in-house fact.
    _support_lord_house: Dict[str, int] = {}
    for h in _VIDYA_HOUSES:
        lord = _d24_house_lord(d24_lagna, h)
        if not lord:
            continue
        lord_house = _d24_planet_house(lord, d24_chart, d24_lagna)
        lord_dig = str(d24_dignities.get(lord, "NEUTRAL")).upper()
        lord_strength = _DIGNITY_STRENGTH.get(lord_dig, 4.0)
        pts = lord_strength * 0.7 * _affinity_mult(lord) * _d24_boundary_mult(lord) * _str_mult_d24(lord)
        if lord_house in (1, 4, 5, 9, 10):  # kendra/trikona/vidya-supportive placement
            pts *= 1.2
        elif lord_house in _DUSTHANA_HOUSES:
            pts *= 0.5
        support += pts
        if _d24_boundary_mult(lord) < 1.0:
            _d24_boundary_flagged.append(lord)
        house_notes.append(f"H{h} lord {lord} dignity={lord_dig} in D24-H{lord_house or '?'} (field-affinity x{round(_affinity_mult(lord),2)})")
        if lord_house:
            _support_lord_house[lord] = lord_house

    # D24 gap-audit fix (2026-08), addition 3 of 3: vidya-house OCCUPANTS.
    # Previously only the house LORD's own placement/dignity was checked --
    # a planet with real field affinity physically SITTING in D24's 4th/5th/
    # 9th house contributed nothing, unlike dashamsha.py's D10-H10-occupant
    # scoring (C3), which has no D24 analog until now.
    #
    # 2026-08-17 audit fix (support-vs-occupant duplication): when a vidya-
    # house LORD (scored above) also happens to physically occupy one of the
    # _VIDYA_HOUSES, this loop independently re-scores that SAME planet's
    # SAME dignity for SAME-house occupancy -- the support loop already
    # credited this planet's dignity (plus a placement bonus keyed off this
    # exact house) via `_support_lord_house[lord] == h`. That is not
    # independent corroboration, it is the identical chart fact counted
    # twice, exactly analogous to dashamsha.py's C1/V1 duplication (same
    # planet, same D1 vitality/dignity, re-scored under a different rubric
    # label). Genuinely distinct facts -- a different planet occupying house
    # h while some other planet lords it -- are NOT discounted, since those
    # are two separate placements. A 0.5 discount (same magnitude as
    # dashamsha's _V1_CORRELATION_DISCOUNT) is applied only to the
    # occupant-loop contribution in the coincidence case, leaving the
    # support-loop credit (computed first, above) at full value.
    _OCCUPANT_CORRELATION_DISCOUNT = 0.5
    occupant_notes = []
    occupant_pts = 0.0
    for h in _VIDYA_HOUSES:
        for planet, sign in d24_chart.items():
            if planet in ("Lagna", "lagna"):
                continue
            if _d24_planet_house(planet, d24_chart, d24_lagna) != h:
                continue
            occ_aff = float((field_affinity or {}).get(planet, 0.0) or 0.0)
            if occ_aff < 0.10:
                continue
            occ_dig = str(d24_dignities.get(planet, "NEUTRAL")).upper()
            occ_strength = _DIGNITY_STRENGTH.get(occ_dig, 4.0)
            occ_pts = occ_aff * occ_strength * 0.6 * _d24_boundary_mult(planet) * _str_mult_d24(planet)
            _is_dup_fact = _support_lord_house.get(planet) == h
            if _is_dup_fact:
                occ_pts *= _OCCUPANT_CORRELATION_DISCOUNT
            occupant_pts += occ_pts
            if occ_pts > 0.5:
                note = f"{planet} occupies D24 H{h} ({occ_dig}, affinity {occ_aff:.2f})"
                if _is_dup_fact:
                    note += " (correlation-discounted: same planet already credited as vidya-house lord above)"
                occupant_notes.append(note)
    occupant_pts = min(8.0, occupant_pts)
    if occupant_pts > 0:
        support += occupant_pts
        components["vidya_house_occupants"] = round(occupant_pts, 2)
        trace.extend(occupant_notes)

    support = min(25.0, support)
    components["vidya_house_lord_support"] = round(support, 2)
    trace.extend(house_notes)
    score += support

    # ── Validation (~20 pts): curriculum-intensity match + karaka placement ─
    curriculum_pct, curriculum_detail = _curriculum_match(payload, field_entry or {}, field_affinity)
    validation = min(20.0, (curriculum_pct / 100.0) * 20.0)
    components["curriculum_fit"] = round(validation, 2)
    if curriculum_detail:
        trace.append(f"Curriculum-intensity match: {round(curriculum_pct,1)}%")
    score += validation

    # ── Penalty (up to -15): vidya-house lords combust or in dusthana ──────
    penalty = 0.0
    combustion_notes = []
    combust_set = set(getattr(payload, "combust_planets", []) or [])
    for h in _VIDYA_HOUSES:
        lord = _d24_house_lord(d24_lagna, h)
        if lord and lord in combust_set:
            penalty += 5.0
            combustion_notes.append(f"D24 H{h} lord {lord} combust")
    penalty = min(15.0, penalty)
    if penalty:
        components["combustion_penalty"] = round(-penalty, 2)
        trace.extend(combustion_notes)
    score -= penalty

    # D24 gap-audit fix: Vimshopaka Bala nudge, same shared coefficient every
    # other divisional method (knrao/parashara/dashamsha) already folds in --
    # siddhamsha was the one method that never called it at all.
    # 2026-08-22 reconciliation (JyotishAI reference-audit, siddhamsha.py):
    # unlike the vidya-house occupant loop above (which discounts 0.5x when
    # a planet is scored twice as both house lord and occupant, via
    # _OCCUPANT_CORRELATION_DISCOUNT), this Vimshopaka nudge reuses
    # lagna_lord/Mercury/Jupiter with NO discount even though lagna_lord's
    # sign-dignity is already scored in the core section above, and
    # Mercury/Jupiter are frequently ALSO vidya-house lords scored in the
    # support loop above (same class of overlap this file's own comment at
    # _OCCUPANT_CORRELATION_DISCOUNT already names and mitigates elsewhere,
    # left unmitigated here). Applying the same 0.5 correlation-discount
    # magnitude used for the occupant/lord coincidence case, for consistency.
    _VIM_D24_CORRELATION_DISCOUNT = 0.5
    _vim_planets_d24 = [p for p in (lagna_lord, "Mercury", "Jupiter") if p]
    _vim_adj_d24 = 0.0
    if _vim_planets_d24:
        _vim_avg_d24 = sum(_vimsopaka_bala_coefficient(p, payload) for p in _vim_planets_d24) / len(_vim_planets_d24)
        _vim_adj_d24 = (_vim_avg_d24 - 1.0) * 8.0 * _VIM_D24_CORRELATION_DISCOUNT
        if abs(_vim_adj_d24) > 0.05:
            score += _vim_adj_d24
            components["vimsopaka_bala"] = round(_vim_adj_d24, 2)
            trace.append(
                f"Vimshopaka Bala for {', '.join(_vim_planets_d24)}: avg coefficient {_vim_avg_d24:.2f} "
                f"-- unified divisional strength {'supports' if _vim_adj_d24 > 0 else 'weakens'} this field."
            )

    rubric = build_score_rubric("siddhamsha", [
        rubric_section("core", core_total, 40, note="D24 lagna lord + vidya-karaka dignity, Shadbala- and "
                        "boundary-risk-adjusted",
                        items=[f"lagna_lord={lagna_lord}", f"karakas={','.join(_VIDYA_KARAKAS)}"]),
        rubric_section("support", support, 25, note="4th/5th/9th lord placement & dignity in D24, "
                        "plus vidya-house occupants",
                        items=house_notes + ["vidya_house_occupants"]),
        rubric_section("validation", validation + _vim_adj_d24, 20, note="Curriculum-intensity fit, Vimshopaka Bala",
                        items=["vimsopaka_bala"]),
        rubric_section("penalty", -penalty, 15, kind="penalty", note="Vidya-house lords combust in D24",
                        items=combustion_notes),
    ])

    # D24 gap-audit fix: surface boundary-risk status the same way dashamsha.py
    # (D10) and kp.py (KP cusps) do -- a consumer should be able to tell
    # whether the lagna lord/vidya karakas/vidya-house lords were discounted
    # for sitting near a 1.25-degree D24 segment boundary under imprecise
    # birth time.
    _d24_boundary_flagged = sorted(set(_d24_boundary_flagged))
    components["birth_time_precision"] = _birth_prec_d24
    components["d24_boundary_risk_planets"] = ",".join(_d24_boundary_flagged)
    if _d24_boundary_flagged:
        trace.append(
            f"D24 boundary risk: {', '.join(_d24_boundary_flagged)} sit within "
            f"{_d24_margin_deg} deg of a 1.25-degree D24 segment boundary under "
            f"'{_birth_prec_d24}' birth-time precision -- their D24 sign/dignity could "
            "plausibly flip under realistic birth-time error; contribution discounted."
        )

    result = method_result(
        "siddhamsha", score, trace, components, rubric=rubric, normalization_cap=35.0,
    )
    # Gap-audit fix (2026-08, D24 data-quality investigation): surface which
    # planets (if any) had no resolvable D24 sign, so a report/audit
    # consumer can tell a genuine data gap apart from a chart-confirmed
    # NEUTRAL dignity without re-deriving it from d24_planet_dignities.
    result["d24_missing_planets"] = d24_missing
    # 2026-08 architecture-audit gap-fix (Gap 4): curriculum-intensity fit is
    # non-astrological reference-data comparison (curriculum requirements
    # vs. D24-derived "capacity"), blended into `components["curriculum_fit"]`
    # above and worth up to 20 of this method's 35-point normalization cap.
    # Leaving that blend in place is a deliberate choice, not an oversight --
    # this scoring path is already validated across 25 real charts, and
    # separating it out of the score itself would be a scoring-behavior
    # change, not a transparency one. What WAS missing, and is added here, is
    # a clearly-labeled, isolated breakdown so a report/UI/consumer can see
    # exactly how much of this method's score came from curriculum-intensity
    # matching (non-astrological) versus D24 dignity/placement (astrological)
    # without having to re-derive it from `components` and `trace`.
    result["curriculum_fit_breakdown"] = {
        "note": "Curriculum-intensity fit is reference-data comparison, not "
                "astrological signal -- isolated here for transparency. It "
                "contributes up to 20 of this method's 35-point cap "
                "(components['curriculum_fit'], already included in `score`).",
        "curriculum_match_pct": round(curriculum_pct, 2),
        "points_contributed": round(validation, 2),
        "points_cap": 20.0,
        "requirements": curriculum_detail.get("requirements", {}),
        "capacity": curriculum_detail.get("capacity", {}),
    }
    # gap fix 2026-08-18 (item 12): see comment on the early-return path above
    # -- D24 never casts an unconditional/"permanent" vote on suitability.
    result["permanent_vote"] = False
    # gap fix 2026-08-18 (item 12): see comment on the early-return path above.
    result["educational_suitability"] = result.get("score", 0.0)
    return result


# Backward-compatible alias: some callers/tests may still import the old name.
def score_siddhamsha_legacy(payload: Any, field_entry: Mapping, field_affinity: Mapping[str, float] | None = None) -> dict:
    """Deprecated confirmation-only entry point, kept for callers not yet
    migrated to the new independent-vote signature."""
    match, detail = _curriculum_match(payload, field_entry, field_affinity)
    if not detail:
        return {"contract_version": "d24-education.v1", "status": "MISSING", "educational_suitability": None, "permanent_vote": False}
    return {
        "contract_version": "d24-education.v1", "status": "OBSERVED",
        "educational_suitability": round(match, 2), "permanent_vote": False, **detail,
    }
