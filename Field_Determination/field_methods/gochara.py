"""Gochara (Transit) Timing Tier -- 10th voting method.

GAP FIX (2026-08-18, audit item A): nothing in this bundle previously scored
whether the two "slow" career-relevant transiting planets -- Jupiter
(benefic expansion/opportunity) and Saturn (structural/karmic pressure,
classically the primary career-timing transit -- e.g. Saturn's dig-bala
locus and its 3rd/10th/11th transit aspects on the natal 10th) -- are
CURRENTLY transiting the natal 10th house or the 10th-lord's natal sign.
That is a well-known classical timing signal (gochara phalam) distinct from
anything the other nine (D1/D9/D10/D24/D60/KP/Jaimini/Parashara/
structural_patterns) methods already cover, all of which read the natal
chart only.

Architecture choice: modelled as a FULL VOTING TIER at a conservative
starting prior, following `structural_patterns.py`'s pattern -- NOT as a
post-blend confirmation multiplier the way `yogini_dasha.py` was wired in.
The audit flagged the multiplier pattern as architecturally inconsistent
(it lets one method silently reweight the other methods' already-blended
result outside the transparent METHOD_WEIGHTS/data-quality/clarity/outlier
machinery every voting method goes through). Gochara gets its own vote
instead, subject to that same machinery, tagged "provisional" in
METHOD_PRIOR_BASIS since -- like structural_patterns -- no validated
benchmark exists yet for its correct weight share.

Reuses, rather than reimplements, transit position computation: the actual
sidereal transit snapshot comes from `jyotish/transit_engine.py`'s
`compute_current_transit_snapshot(as_of, lagna_sign)` (already-built
Keplerian/Swiss-Ephemeris transit engine), consumed the same way
`payload_data.transit_house_positions` is already consumed elsewhere in
this codebase (e.g. `Job_Career/timeline.py`, `jyotish/engine_io.py`). If
the payload already carries a populated `transit_house_positions` dict
(upstream-supplied or already computed by the caller), that is used
directly and no new computation is performed; only when it is empty does
this module call `compute_current_transit_snapshot` itself as a fallback,
so this method never silently no-ops on charts where transit data was
already available under a different call path.

Data-quality gating: self-gated (same convention as sudarshana.py /
structural_patterns.py -- no external `_data_quality` entry needed beyond
the default 1.0) -- MISSING status returned whenever no transit snapshot
can be resolved at all.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Any, Dict, List, Mapping

from .common import (
    METHOD_SCORE_CAPS,
    build_score_rubric,
    method_result,
    rubric_section,
)

_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


def _sign_at_house(lagna_sign: str, house_num: int) -> str:
    """Whole-sign zodiac sign occupying house `house_num` counted from
    `lagna_sign`. Used to derive a TRANSITING planet's current sign from its
    already-resolved transit house number, since whole-sign house N from a
    given lagna sign always corresponds to exactly one zodiac sign."""
    if not lagna_sign or lagna_sign not in _SIGN_ORDER:
        return ""
    lagna_idx = _SIGN_ORDER.index(lagna_sign)
    return _SIGN_ORDER[(lagna_idx + house_num - 1) % 12]

# Conservative floor for chart-wide (non-field-specific) transit facts, same
# convention as structural_patterns.py's _MIN_AAF.
_MIN_AAF = 0.35

# Points awarded per "hit" (a slow planet transiting the natal 10th house or
# the 10th-lord's natal sign). Up to 4 possible hits: {Jupiter, Saturn} x
# {10th house, 10th-lord's sign}.
_CORE_PTS_PER_HIT = 10.0
_CORE_CAP = 40.0

# Support: Jupiter+Saturn both confirming the same career locus
# simultaneously is a classically stronger convergence than either alone
# (this module only has whole-sign house-level transit precision available,
# so exact-degree tightness isn't scoreable here -- double-confirmation is
# used as the analogous "how strong is this specific hit" support signal).
_DOUBLE_TRANSIT_BONUS = 15.0

# Validation: a small field-affinity-gated bonus when the transiting
# planet ALSO happens to be a high-affinity karaka for this specific field
# (e.g. Jupiter transiting the 10th matters more for a Jupiter-ruled field
# than a Mars-ruled one), following the same field-affinity-gating
# convention structural_patterns.py uses throughout.
_VALIDATION_CAP = 15.0


def _affinity_mult(field_affinity: Mapping[str, float] | None, planet: str) -> float:
    aff = float((field_affinity or {}).get(planet, 0.0) or 0.0)
    return _MIN_AAF + (1.0 - _MIN_AAF) * max(0.0, min(1.0, aff))


def _resolve_transit_houses(payload_data: Any) -> Dict[str, int]:
    """Return {planet: transit_house_number}, preferring already-populated
    payload data over a fresh live computation. Never raises -- any failure
    in the fallback path returns an empty dict, matching
    transit_engine.py's own documented graceful-degradation contract."""
    existing = getattr(payload_data, "transit_house_positions", {}) or {}
    if existing:
        try:
            return {p: int(h) for p, h in existing.items()}
        except (TypeError, ValueError):
            pass

    lagna_sign = str(getattr(payload_data, "lagna_sign", "") or "")
    if not lagna_sign:
        return {}
    try:
        from jyotish.transit_engine import compute_current_transit_snapshot
        house_positions, _degrees, _retro = compute_current_transit_snapshot(_date.today(), lagna_sign)
        return {p: int(h) for p, h in (house_positions or {}).items()}
    except Exception:
        return {}


def score_gochara(
    payload_data: Any,
    domain: str = "",
    field_affinity: Mapping[str, float] | None = None,
    field_id: str = "",
    field_entry: Mapping | None = None,
) -> Dict[str, Any]:
    """Score whether Jupiter and/or Saturn are currently transiting the
    natal 10th house or the natal 10th-lord's sign, as an independent
    voting method. Signature mirrors the other method scorers so it wires
    into compute_field_method_bundle uniformly."""
    trace: List[str] = []
    components: Dict[str, float] = {}

    house_lords: Dict[str, str] = getattr(payload_data, "house_lords", {}) or {}
    planet_signs: Dict[str, str] = (
        getattr(payload_data, "planet_sign", {}) or getattr(payload_data, "planet_signs", {}) or {}
    )

    h10_lord = house_lords.get("10") or house_lords.get(10) or str(getattr(payload_data, "h10_lord", "") or "")
    h10_lord_natal_sign = planet_signs.get(h10_lord, "") if h10_lord else ""

    transit_houses = _resolve_transit_houses(payload_data)

    if not transit_houses:
        rubric = build_score_rubric("gochara", [
            rubric_section("core", 0, _CORE_CAP, note="No transit snapshot available"),
        ])
        return method_result(
            "gochara", 0.0,
            ["Transit (gochara) data unavailable -- method skipped."],
            {}, rubric=rubric, normalization_cap=METHOD_SCORE_CAPS.get("gochara", 55.0),
        )

    score = 0.0
    hit_planets: List[str] = []
    per_planet_hit: Dict[str, bool] = {}

    for planet in ("Jupiter", "Saturn"):
        t_house = transit_houses.get(planet)
        if t_house is None:
            per_planet_hit[planet] = False
            continue

        on_10th_house = int(t_house) == 10
        planet_aff = _affinity_mult(field_affinity, planet)

        hit = on_10th_house
        if hit:
            score += _CORE_PTS_PER_HIT * planet_aff
            components[f"{planet.lower()}_transit_10th_house"] = round(_CORE_PTS_PER_HIT * planet_aff, 2)
            trace.append(
                f"{planet} is currently transiting the natal 10th house -- field-affinity "
                f"x{round(planet_aff,2)} -> {round(_CORE_PTS_PER_HIT * planet_aff,2)} pts"
            )
            hit_planets.append(planet)
        per_planet_hit[planet] = hit

    core_total = min(_CORE_CAP, score)
    score = core_total

    # ── Support: both slow career-relevant planets confirming simultaneously ──
    support = 0.0
    if len(hit_planets) >= 2:
        avg_aff = sum(_affinity_mult(field_affinity, p) for p in hit_planets) / len(hit_planets)
        support = min(_DOUBLE_TRANSIT_BONUS, _DOUBLE_TRANSIT_BONUS * avg_aff)
        components["double_transit_convergence"] = round(support, 2)
        trace.append(
            f"Jupiter AND Saturn both confirming the same career locus (natal 10th house) "
            f"simultaneously -- convergence bonus {round(support,2)} pts"
        )
    score += support

    # ── Validation: 10th-lord's natal sign currently tenanted by a
    # transiting Jupiter/Saturn -- a secondary, sign-based (not house-based)
    # confirmation of the same theme. ─────────────────────────────────────
    validation = 0.0
    val_hits: List[str] = []
    lagna_sign = str(getattr(payload_data, "lagna_sign", "") or "")
    if h10_lord_natal_sign:
        # GAP-FIX (2026-08, astrological audit): this previously read
        # `planet_signs`, which is the chart's NATAL planet-sign dict (the
        # same one `h10_lord_natal_sign` above is built from) -- so this
        # "transiting sign" check was actually comparing Jupiter/Saturn's
        # NATAL sign against the 10th lord's NATAL sign, a static fact with
        # nothing to do with a live transit or "this cycle"'s timing. That
        # silently defeated the entire point of a TIMING method (gochara):
        # the bonus fired identically regardless of the actual transit date,
        # and the trace text ("X transiting 10th-lord's natal sign") was
        # actively misleading about what had been checked. Whole-sign house N
        # from a given lagna sign always maps to exactly one zodiac sign, so
        # the genuinely-transiting sign is derivable directly from the
        # already-resolved `transit_houses` (used for the core/support
        # sections above) and `lagna_sign` -- no natal data involved.
        transiting_planet_signs = {
            p: _sign_at_house(lagna_sign, transit_houses[p])
            for p in ("Jupiter", "Saturn")
            if p in transit_houses
        }
        for planet in ("Jupiter", "Saturn"):
            cur_sign = transiting_planet_signs.get(planet, "")
            # Only meaningful when a transit house was actually resolved for
            # this planet; guarded to no-op otherwise.
            if not cur_sign:
                continue
            if cur_sign == h10_lord_natal_sign:
                planet_aff = _affinity_mult(field_affinity, planet)
                bonus = min(_VALIDATION_CAP, 7.5 * planet_aff)
                validation += bonus
                val_hits.append(f"{planet} transiting 10th-lord {h10_lord}'s natal sign ({h10_lord_natal_sign})")
    validation = min(_VALIDATION_CAP, validation)
    if val_hits:
        components["h10_lord_sign_transit"] = round(validation, 2)
        trace.extend(val_hits)
    score += validation

    if not hit_planets and not val_hits:
        trace.append(
            "Neither Jupiter nor Saturn is currently transiting the natal 10th house "
            "or the 10th-lord's natal sign -- no gochara timing support this cycle."
        )

    rubric = build_score_rubric("gochara", [
        rubric_section("core", core_total, _CORE_CAP, note="Jupiter/Saturn transiting natal 10th house",
                        items=[k for k in components if k.endswith("_transit_10th_house")]),
        rubric_section("support", support, _DOUBLE_TRANSIT_BONUS, note="Double transit convergence",
                        items=["double_transit_convergence"] if support else []),
        rubric_section("validation", validation, _VALIDATION_CAP, note="10th-lord natal-sign transit confirmation",
                        items=["h10_lord_sign_transit"] if validation else []),
    ])

    return method_result(
        "gochara", score, trace, components, rubric=rubric,
        normalization_cap=METHOD_SCORE_CAPS.get("gochara", 55.0),
    )
