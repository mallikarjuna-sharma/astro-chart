"""Structural Pattern Analysis (Stage 1 of the Astro-OS v3 gap-audit
implementation plan, 2026-08) -- 9th voting method.

Gap being closed: nothing in this engine asks "which houses form clusters,"
"which kendras/trikonas dominate," or "where is the chart's energy
concentrated" as a first-class, dedicated, weighted signal. The closest
existing analogs (`_house_signification_bonus`, `_karakatwa_domain_bonus` in
boosts.py) are small, generic add-ons already shared across several methods,
not a dedicated structural layer. This module is that dedicated layer.

Design constraints (deliberate, matching the sequencing agreed in the
implementation plan):
  - Conservative starting weight. The originating design proposal argued for
    35-40% of the total blend; that number is unvalidated (this engine has
    no labeled benchmark -- see Stage 0's harness/fixture set). This method
    is wired in at a modest prior instead, and -- like every other method in
    this bundle -- its EFFECTIVE weight is still adjusted per-chart by the
    existing data-quality/clarity/outlier gating in __init__.py, so a chart
    with a genuinely unusual concentration pattern can still let this method
    rise well above its base prior.
  - Field-affinity-gated, not a flat chart-level constant. A pure "4 planets
    in the 9th house" fact is the same for every field candidate on a given
    chart -- voting it in unmodified would reproduce the exact "flat score
    across all fields" bug D24/siddhamsha.py had before its Phase-3b
    remediation (see that module's own docstring). Every component below is
    scaled by the SAME `_affinity_mult` floor pattern siddhamsha.py already
    uses (floor=0.35: a chart's general structural concentration still
    counts a little for every field, but counts much more for fields whose
    karakas the concentrated house/kendra/trikona group actually rules).
  - Reuses, rather than reinvents, the codebase's own validated
    domain-vs-house primitive (`_house_signification_bonus`, boosts.py --
    already used identically by dashamsha.py and kp.py) for the
    domain-cross-check section, instead of hand-rolling a second house-
    keyword table that would drift out of sync with the existing one.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from jyotish.boosts import _house_signification_bonus, _d1_vitality_coefficient
from jyotish.constants import _KENDRA_HOUSES, _TRIKONA_HOUSES, _DUSTHANA_HOUSES

from .common import (
    METHOD_SCORE_CAPS,
    build_score_rubric,
    method_result,
    rubric_section,
)

_MIN_AAF = 0.35  # same floor convention as siddhamsha.py's _affinity_mult

# A dominant house needs at least this many D1 occupants to count as a
# genuine "cluster"/stellium, not incidental co-tenancy of two planets.
_STELLIUM_THRESHOLD = 3


def _affinity_mult(field_affinity: Mapping[str, float] | None, planet: str) -> float:
    aff = float((field_affinity or {}).get(planet, 0.0) or 0.0)
    return _MIN_AAF + (1.0 - _MIN_AAF) * max(0.0, min(1.0, aff))


def score_structural_patterns(
    payload_data: Any,
    domain: str = "",
    field_affinity: Mapping[str, float] | None = None,
    field_id: str = "",
    field_entry: Mapping | None = None,
) -> Dict[str, Any]:
    """Score a candidate field from D1 house-occupancy clustering --
    kendra/trikona dominance and stellium concentration -- as an independent
    voting method. Signature mirrors the other eight method scorers so it
    wires into compute_field_method_bundle uniformly.
    """
    trace: List[str] = []
    components: Dict[str, float] = {}
    score = 0.0

    planet_house: Dict[str, int] = getattr(payload_data, "planet_house", {}) or {}
    house_lords: Dict[str, str] = getattr(payload_data, "house_lords", {}) or {}
    planets_d1: Dict[str, Any] = getattr(payload_data, "planets_d1", {}) or {}

    if not planet_house:
        rubric = build_score_rubric("structural_patterns", [
            rubric_section("core", 0, 40, note="D1 house occupancy unavailable"),
        ])
        return method_result(
            "structural_patterns", 0.0,
            ["D1 house-occupancy data unavailable -- method skipped."],
            {}, rubric=rubric, normalization_cap=METHOD_SCORE_CAPS.get("structural_patterns", 85.0),
        )

    # ── Build the house-occupancy histogram ──────────────────────────────────
    occupancy: Dict[int, List[str]] = {}
    # 2026-08-20 gap-audit fix: this loop used to skip Rahu/Ketu with a
    # comment claiming they were "counted separately below" -- no such logic
    # existed anywhere else in this file, so both nodes were silently
    # invisible to the entire kendra/trikona-dominance and stellium scan.
    # That is a real gap: a node sitting in a kendra (most classically
    # significant, e.g. Ketu in the 10th/Karma Bhava) went completely
    # unscored by the one method built specifically to detect "where is the
    # chart's energy concentrated." Nodes are now included like any other
    # graha; _affinity_mult already gates their contribution by the SAME
    # per-field affinity weight every other planet here uses, so a field
    # whose vector doesn't weight Rahu/Ketu still isn't overcredited --
    # this only restores visibility for fields that DO carry node affinity.
    for planet, house_num in planet_house.items():
        try:
            h = int(house_num)
        except (TypeError, ValueError):
            continue
        if 1 <= h <= 12:
            occupancy.setdefault(h, []).append(planet)

    total_placed = sum(len(v) for v in occupancy.values())
    if total_placed == 0:
        rubric = build_score_rubric("structural_patterns", [
            rubric_section("core", 0, 40, note="No resolvable D1 house placements"),
        ])
        return method_result(
            "structural_patterns", 0.0,
            ["No resolvable D1 house placements -- method skipped."],
            {}, rubric=rubric, normalization_cap=METHOD_SCORE_CAPS.get("structural_patterns", 85.0),
        )

    dominant_house = max(occupancy, key=lambda h: (len(occupancy[h]), -h))
    dominant_occupants = occupancy[dominant_house]
    concentration = len(dominant_occupants)

    kendra_count = sum(len(occupancy.get(h, [])) for h in _KENDRA_HOUSES)
    trikona_count = sum(len(occupancy.get(h, [])) for h in _TRIKONA_HOUSES)
    kendra_pct = kendra_count / total_placed
    trikona_pct = trikona_count / total_placed

    # ── Core (~40 pts): kendra-dominance + trikona-dominance, each gated by
    # the field-affinity of the planets/lord actually driving the
    # concentration -- not a flat chart-level constant. ─────────────────────
    kendra_lords_aff = [
        _affinity_mult(field_affinity, p)
        for h in _KENDRA_HOUSES for p in occupancy.get(h, [])
    ]
    kendra_aaf = sum(kendra_lords_aff) / len(kendra_lords_aff) if kendra_lords_aff else _MIN_AAF
    kendra_component = min(20.0, kendra_pct * 25.0 * kendra_aaf)
    components["kendra_dominance"] = round(kendra_component, 2)
    trace.append(
        f"Kendra houses (1/4/7/10) hold {kendra_count}/{total_placed} planets "
        f"({round(kendra_pct*100,1)}%), field-affinity x{round(kendra_aaf,2)} -> {round(kendra_component,2)} pts"
    )

    trikona_lords_aff = [
        _affinity_mult(field_affinity, p)
        for h in _TRIKONA_HOUSES for p in occupancy.get(h, [])
    ]
    trikona_aaf = sum(trikona_lords_aff) / len(trikona_lords_aff) if trikona_lords_aff else _MIN_AAF
    trikona_component = min(20.0, trikona_pct * 25.0 * trikona_aaf)
    # PROVENANCE/AUDIT NOTE (2026-08-22): House 1 (Lagna) is a member of BOTH
    # _KENDRA_HOUSES {1,4,7,10} and _TRIKONA_HOUSES {1,5,9}, so a planet placed
    # in H1 was being credited toward kendra_pct AND trikona_pct from the same
    # single placement fact, inflating both components uncapped relative to
    # each other (only the combined core_total=min(40,...) clamp caught the
    # runaway total, not the double-credit itself). Applying a correlation
    # discount to the trikona side proportional to how much of trikona_count
    # is actually the H1 overlap, matching this codebase's established
    # 0.5x-per-duplicated-fact discount pattern (see parashara.py, dashamsha.py).
    _h1_overlap = len(occupancy.get(1, []))
    if _h1_overlap and trikona_count:
        _overlap_frac = min(1.0, _h1_overlap / trikona_count)
        trikona_component *= (1.0 - 0.5 * _overlap_frac)
    components["trikona_dominance"] = round(trikona_component, 2)
    trace.append(
        f"Trikona houses (1/5/9) hold {trikona_count}/{total_placed} planets "
        f"({round(trikona_pct*100,1)}%), field-affinity x{round(trikona_aaf,2)} -> {round(trikona_component,2)} pts"
        + (f" [H1 overlap w/ kendra: {_h1_overlap} planet(s), 0.5x discount applied]" if _h1_overlap and trikona_count else "")
    )

    core_total = min(40.0, kendra_component + trikona_component)
    score += core_total

    # ── Support (~25 pts): stellium/concentration bonus on the dominant
    # house, scaled by the dominant house's own lord's field-affinity and
    # dignity/vitality -- e.g. "4 planets in the 9th" only matters for THIS
    # field if the 9th lord (or the concentrated planets themselves) carry
    # real affinity weight for it. ───────────────────────────────────────────
    support = 0.0
    if concentration >= _STELLIUM_THRESHOLD:
        dominant_lord = house_lords.get(str(dominant_house), house_lords.get(dominant_house, ""))
        occupant_aaf = [_affinity_mult(field_affinity, p) for p in dominant_occupants]
        avg_occupant_aaf = sum(occupant_aaf) / len(occupant_aaf)
        lord_vit = _d1_vitality_coefficient(dominant_lord, payload_data) if dominant_lord else 1.0
        stellium_bonus = min(25.0, (concentration - _STELLIUM_THRESHOLD + 1) * 6.0 * avg_occupant_aaf * lord_vit)
        support += stellium_bonus
        components["stellium_concentration"] = round(stellium_bonus, 2)
        trace.append(
            f"D1 stellium: {concentration} planets ({', '.join(dominant_occupants)}) concentrated in "
            f"H{dominant_house} (lord {dominant_lord or '?'}), field-affinity x{round(avg_occupant_aaf,2)} "
            f"-> {round(stellium_bonus,2)} pts"
        )
    else:
        trace.append(
            f"No stellium: largest house cluster is H{dominant_house} with {concentration} planet(s) "
            f"(threshold is {_STELLIUM_THRESHOLD}+)."
        )
    score += support

    # ── Validation (~20 pts): reuse the codebase's own validated domain<->
    # house cross-check primitive (already used identically by dashamsha.py
    # and kp.py) rather than a second, hand-rolled keyword table. ───────────
    house_dom_bonus, house_dom_hits = _house_signification_bonus(
        domain, field_affinity or {}, house_lords, planet_house, planets_d1, payload_data,
        scale=5.0, cap=20.0,
    )
    components["domain_house_signification"] = round(house_dom_bonus, 2)
    if house_dom_hits:
        trace.append(f"Domain-house cross-check ({domain}): {', '.join(house_dom_hits)}")
    score += house_dom_bonus

    # ── Penalty (up to -15): concentration specifically in a dusthana (6/8/
    # 12) is a genuine classical caution -- energy clustered in houses of
    # loss/obstacle/isolation, not merely "unremarkable." Scoped narrowly
    # (dusthana + genuine stellium only) so an ordinary 1-2-planet 8th/12th
    # placement -- extremely common and not inherently negative -- never
    # triggers this. ──────────────────────────────────────────────────────
    penalty = 0.0
    if dominant_house in _DUSTHANA_HOUSES and concentration >= _STELLIUM_THRESHOLD:
        occupant_aaf = [_affinity_mult(field_affinity, p) for p in dominant_occupants]
        avg_occupant_aaf = sum(occupant_aaf) / len(occupant_aaf)
        penalty = min(15.0, (concentration - _STELLIUM_THRESHOLD + 1) * 4.0 * avg_occupant_aaf)
        components["dusthana_concentration_penalty"] = round(-penalty, 2)
        trace.append(
            f"Caution: {concentration}-planet stellium in dusthana H{dominant_house} -- "
            f"concentrated energy in a house of obstacle/loss for this field's karakas."
        )
    score -= penalty

    rubric = build_score_rubric("structural_patterns", [
        rubric_section("core", core_total, 40, note="Kendra/trikona dominance (field-affinity gated)",
                        items=["kendra_dominance", "trikona_dominance"]),
        rubric_section("support", support, 25, note="Stellium/concentration bonus on the dominant house",
                        items=["stellium_concentration"]),
        rubric_section("validation", house_dom_bonus, 20, note="Domain<->house signification cross-check",
                        items=house_dom_hits),
        rubric_section("penalty", -penalty, 15, kind="penalty",
                        note="Stellium concentrated in a dusthana house",
                        items=["dusthana_concentration_penalty"] if penalty else []),
    ])

    return method_result(
        "structural_patterns", score, trace, components, rubric=rubric,
        normalization_cap=METHOD_SCORE_CAPS.get("structural_patterns", 85.0),
    )
