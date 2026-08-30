"""Business_Prediction/business_determination/ashtakavarga_timing.py
=======================================================================
Year-by-year Ashtakavarga (Sarvashtakavarga/SAV) strength ranking for
business timing.

Prior state (before this module): Ashtakavarga usage across this package
was a single static check -- significators.py and mode_gate.py each had a
local `_sav_h(h)` helper reading `payload.sav_points_houses` (already
computed once, upstream, by `jyotish.engine_io`'s `_sav_normalized` /
`jyotish.ashtakavarga.compute_bav_points` -- see that module's grand-total
self-check, Sun=48..Saturn=39, SAV=337) and fired ONE bonus
("H11 SAV >=30 -> gains house well supported") into the evidence ledger.
There was no year-by-year ranking of strongest years anywhere in the
engine; all timing was driven by timing.py's dasha/bhukti windows
(`_compute_windows_and_status`) plus mean-motion transit corroboration
(`_transit_corroboration`).

This module does NOT recompute SAV from scratch -- it reuses the exact
same `payload.sav_points_houses` field (string house keys "1".."12",
canonical per engine_io.py) that significators.py/mode_gate.py already
read, via the shared `sav_lookup()` helper factored out into constants.py
so all three call sites share one lookup implementation instead of each
re-declaring an identical closure.

2026-07-26 gap-fix (BAV-based transit-strength grading): SAV (used above)
is a GRAND TOTAL across all seven grahas' Bhinnashtakavarga (BAV) contributions
for a house -- it says "this house is generically well-supported" but says
nothing about whether the SPECIFIC transiting planet (Jupiter or Saturn)
is itself strong or weak in the sign it occupies. jyotish/ashtakavarga.py
already computes real per-planet BAV with the two classical shodhana
(reduction) processes applied -- Trikona Shodhana and Ekadhipatya Shodhana
(see that module's `compute_bav_points_shodhita`/`apply_trikona_shodhana`/
`apply_ekadhipatya_shodhana`) -- and engine_io.py already wires the result
onto the payload as `bav_points_shodhita` ({target_planet: {house_str
"1".."12": bindu_count}}, houses counted from Lagna, i.e. the SAME
house-from-Lagna numbering `jup_house`/`sat_house` below already use, so no
sign lookup/conversion is needed to cross-reference it). This module now
ALSO reads that field (preferring the already-computed payload field;
falling back to calling jyotish.ashtakavarga.compute_bav_points_shodhita()
directly if the field is absent but planet_signs/lagna_sign are available)
to add a second, planet-specific tempering component to the composite
score -- see `_bav_lookup()`/`_bav_interpretation()`/`_BAV_WEIGHT` below for
the exact weighting and the classical bindu-count interpretation threshold
(<=4 weak, 5 neutral, 6+ favorable) this module documents and applies.

Note on "Kakshya shodhana": jyotish/ashtakavarga.py implements Trikona
Shodhana and Ekadhipatya Shodhana (BPHS Ch.5's two reduction processes for
BAV/SAV bindus); it does not implement a separate "Kakshya" (sub-division)
reduction, which is a different, narrower classical technique for weighting
bindus by kakshya-lord sub-periods within a sign and is not present anywhere
in this codebase. This module reuses exactly what jyotish/ashtakavarga.py
actually computes (Trikona+Ekadhipatya-reduced BAV), not a Kakshya-reduced
value that does not exist in this repo.

What IS new here: for each calendar year in a caller-given range, this
module obtains transiting Jupiter and Saturn from the real sidereal
ephemeris at each year's midpoint when location data are available. The
older mean-motion projection remains an explicitly labelled fallback for
partial/test payloads. It then cross-references
those projected transit houses against the natal SAV bindu counts for the
five business-relevant houses (2nd=co-investment/liquid capital,
6th=competition/service/debt, 7th=partnership/trade, 10th=
enterprise/authority, 11th=gains/network) to build one composite
"Ashtakavarga strength score" per year, and ranks years strongest-first.

Public API
----------
    rank_business_years(payload, start_year, end_year,
                         timing_windows=None) -> Dict[str, Any]

Never raises. Degrades to a diagnostic dict (status != "OK") for missing
birth data, missing SAV computation, an excessive year span, or an
internal computation failure -- see `_DIAGNOSTIC_NOTES` below.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .constants import MODEL_STATUS, CALIBRATION_STATUS, MATURITY_STATEMENT, sav_lookup, _record_diagnostic

__all__ = [
    "rank_business_years",
    "BUSINESS_SAV_HOUSES",
    "MAX_YEAR_SPAN",
]

# Business-relevant houses for Ashtakavarga cross-referencing (see module
# docstring for the classical rationale behind each).
BUSINESS_SAV_HOUSES: List[int] = [2, 6, 7, 10, 11]

# Sanity cap on the requested year span -- mirrors muhurta.py's
# MAX_SCAN_DAYS pattern (bounded computation, explicit diagnostic instead
# of silently truncating or hanging on an unbounded request).
MAX_YEAR_SPAN = 20

# Same mean-days-per-house projection constants used by
# Job_Career.timeline._get_dynamic_transits for Jupiter/Saturn -- reused
# here rather than re-derived so both modules describe the same transiting
# Jupiter/Saturn position for the same date. Only the two slow-movers are
# projected; faster bodies move too much within a calendar year for a
# year-level (rather than AD-window-level) heuristic to be meaningful.
_DAYS_PER_HOUSE: Dict[str, int] = {"Jupiter": 365, "Saturn": 912}
_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
          "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

# Composite-score tier thresholds. SAV per house averages ~28 (337/12);
# a business-house average plus a supporting transit bonus comfortably
# clears these bands for genuinely strong years. Heuristic engineering
# thresholds, not a claim of unique classical authority -- same status as
# every other numeric threshold in this package (see MATURITY_STATEMENT).
_TIER_THRESHOLDS = (
    (40.0, "EXCELLENT"),
    (32.0, "GOOD"),
    (26.0, "AVERAGE"),
)


def _tier_for_score(score: float) -> str:
    for threshold, tier in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "WEAK"


# ── BAV (Bhinnashtakavarga) transit-strength tempering ─────────────────────
# GAP-FIX (2026-07-26): reuses jyotish.ashtakavarga's real per-planet BAV,
# post Trikona+Ekadhipatya shodhana (see module docstring above) -- NOT a
# "Kakshya shodhana" reduction, which does not exist anywhere in this repo;
# see module docstring for that provenance disclosure.
#
# Classical bindu-count interpretation threshold: jyotish/ashtakavarga.py
# itself documents the provenance of its bindu TABLES and its shodhana
# ALGORITHM, but is silent on how to interpret a resulting bindu count.
# The threshold applied here -- a transiting planet's own (post-shodhana)
# BAV bindu count of 4-or-fewer in its occupied house is weak/adverse for
# that transit, 5 is borderline/neutral, 6-or-more is progressively
# favorable -- is the standard classical Ashtakavarga interpretation rule
# described consistently across secondary Ashtakavarga literature and
# common Jyotish software convention (the same class/tier of source already
# cited for this repo's BAV bindu tables and shodhana algorithm -- see
# jyotish/ashtakavarga.py's own honesty note on that point); it is not a
# verse-pinned BPHS citation, and is disclosed here with that same caveat.
_BAV_NEUTRAL_BINDU = 5

# Weighting: mirrors the existing SAV bonus's 2:1 Jupiter:Saturn emphasis
# (0.5 vs 0.25 per bindu above) since Jupiter is the primary business/wealth
# significator and the slower, more decisively-weighted transit of the two.
# Scaled up from the SAV bonus's per-bindu weight because BAV bindus range
# only 0-8 per house (vs SAV's ~0-56 grand total per house), so a small
# per-bindu weight would make the BAV component negligible next to the SAV
# component -- these constants are sized so a maximally-weak BAV reading
# (0 bindus, i.e. -5 from neutral) can plausibly move a year down one tier,
# without letting BAV alone dominate the SAV-anchored composite.
_BAV_WEIGHT: Dict[str, float] = {"Jupiter": 2.0, "Saturn": 1.0}


def _bav_interpretation(bindus: Optional[int]) -> str:
    """Classical bindu-count interpretation label -- see the threshold note
    above. Returns "BAV_UNAVAILABLE" when bindus is None (graceful
    degradation -- see _bav_lookup())."""
    if bindus is None:
        return "BAV_UNAVAILABLE"
    if bindus <= 4:
        return "WEAK"
    if bindus == _BAV_NEUTRAL_BINDU:
        return "NEUTRAL"
    return "FAVORABLE"


def _bav_lookup(payload: Any, planet: str, house: int) -> Optional[int]:
    """Looks up `planet`'s own Bhinnashtakavarga bindu count (post Trikona+
    Ekadhipatya shodhana) in `house` (numbered from Lagna, matching
    jup_house/sat_house's own convention -- see module docstring).

    Prefers `payload.bav_points_shodhita` (the field jyotish/engine_io.py
    already computes upstream via jyotish.ashtakavarga.compute_bav_points_shodhita
    and wires onto every NatalPayloadV2 -- see jyotish/payload.py), so this
    module does not recompute BAV from scratch when the upstream chart
    pipeline already has. Falls back to calling
    jyotish.ashtakavarga.compute_bav_points_shodhita() directly (using
    payload.planet_signs/payload.lagna_sign) only if that field is absent,
    e.g. an older/partial payload.

    Never raises -- returns None (not 0) on any missing data, malformed
    shape, or import failure, so callers can distinguish "genuinely 0
    bindus" from "BAV unavailable, degrade to SAV-only" (see
    rank_business_years's bav_status handling)."""
    if not house:
        return None
    try:
        bav_shodhita = getattr(payload, "bav_points_shodhita", None) or {}
        planet_houses = bav_shodhita.get(planet) if hasattr(bav_shodhita, "get") else None
        if planet_houses:
            val = planet_houses.get(str(house), planet_houses.get(house))
            if val is not None:
                return int(val)
    except Exception as exc:
        # Engineering audit fix #9: previously silently `pass`ed with no
        # record at all before falling through to the recompute attempt
        # below -- recorded (non-fatal; the recompute fallback still runs).
        _record_diagnostic("ashtakavarga_timing._sav_points_for_house", exc, note="payload.bav_points_shodhita lookup failed")

    try:
        from jyotish.ashtakavarga import compute_bav_points_shodhita
        planet_signs = getattr(payload, "planet_signs", None) or {}
        lagna_sign = getattr(payload, "lagna_sign", "") or ""
        if not planet_signs or not lagna_sign:
            return None
        computed = compute_bav_points_shodhita(planet_signs, lagna_sign)
        return int(computed.get(planet, {}).get(house, 0))
    except Exception as exc:
        _record_diagnostic("ashtakavarga_timing._sav_points_for_house", exc, note="compute_bav_points_shodhita fallback failed")
        return None


def _project_house(planet: str, snapshot_house: int, days_ahead: int) -> int:
    """Mean-motion projection of a slow-moving planet's house-from-Lagna,
    `days_ahead` days after the snapshot date. Prograde-only approximation
    (retrograde loops average out over the ~1-2.5 year period this module
    projects across) -- see module docstring; the AD-window-level transit
    corroboration in timing.py handles the finer retrograde-aware case."""
    days_per_house = _DAYS_PER_HOUSE.get(planet)
    if not days_per_house or not snapshot_house:
        return 0
    houses_moved = round(days_ahead / days_per_house)
    return int(((snapshot_house - 1 + houses_moved) % 12) + 1)


def _ephemeris_slow_mover_houses(payload: Any, year: int, lagna_sign: str) -> Dict[str, int]:
    """Whole-sign houses from real sidereal longitudes at mid-year.

    Returns an empty dict when the ephemeris is unavailable so callers can
    explicitly fall back to the legacy mean-motion projection.
    """
    try:
        from jyotish import ephemeris
        if not ephemeris.is_available() or lagna_sign not in _SIGNS:
            return {}
        if not hasattr(payload, "latitude") or not hasattr(payload, "longitude"):
            return {}
        lat = float(getattr(payload, "latitude"))
        lon = float(getattr(payload, "longitude"))
        tz = getattr(payload, "timezone_offset_hours", None)
        positions = ephemeris.get_planet_longitudes(
            datetime(year, 7, 1, 12, 0), lat, lon, tz_offset_hours=tz
        )
        lagna_index = _SIGNS.index(lagna_sign)
        result: Dict[str, int] = {}
        for planet in ("Jupiter", "Saturn"):
            longitude = positions.get(planet)
            if longitude is not None:
                sign_index = int(float(longitude) % 360.0 // 30.0)
                result[planet] = ((sign_index - lagna_index) % 12) + 1
        return result
    except Exception as exc:
        _record_diagnostic("ashtakavarga_timing._ephemeris_slow_mover_houses", exc)
        return {}


def _dasha_year_adjustment(overlaps: List[Dict[str, Any]]) -> float:
    """Bounded dasha arbitration for a calendar-year suitability score."""
    if not overlaps:
        return 0.0
    label_weight = {
        "STRONG_FAVORABLE": 8.0, "FAVORABLE": 4.0, "MIXED": 0.0,
        "CAUTION": -4.0, "HIGH_RISK": -8.0,
    }
    values = [label_weight.get(str(row.get("label", "")).upper(), 0.0) for row in overlaps]
    return round(sum(values) / len(values), 2)


def _dasha_corroboration_for_year(
    year: int,
    timing_windows: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Cross-references a calendar year against timing.py's already-scored
    dasha/bhukti windows (see timing.py::_compute_windows_and_status /
    _WINDOW_LABELS: STRONG_FAVORABLE/FAVORABLE/MIXED/CAUTION/HIGH_RISK).
    Purely a lookup against caller-supplied window data -- this module does
    not recompute the dasha calendar itself, so a caller who wants
    corroboration must pass in the `windows` list already produced by
    `_compute_windows_and_status(payload, ...)` or
    `compute_business_prediction(payload, ...)['timed_windows']`."""
    if not timing_windows:
        return []
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    overlaps: List[Dict[str, Any]] = []
    for window in timing_windows:
        try:
            w_start = date.fromisoformat(str(window.get("start_date", "")))
            w_end = date.fromisoformat(str(window.get("end_date", "")))
        except (ValueError, TypeError):
            continue
        if w_start <= year_end and w_end >= year_start:
            overlaps.append({
                "md_lord": window.get("md_lord", ""),
                "ad_lord": window.get("ad_lord", ""),
                "label": window.get("label", ""),
                "start_date": window.get("start_date", ""),
                "end_date": window.get("end_date", ""),
            })
    return overlaps


def rank_business_years(
    payload: Any,
    start_year: int,
    end_year: int,
    timing_windows: Optional[List[Dict[str, Any]]] = None,
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Ranks calendar years in [start_year, end_year] by a composite
    Ashtakavarga (SAV) business-strength score, strongest first.

    Args:
        payload: NatalPayloadV2-shaped chart object (or duck-typed
            equivalent) -- must expose `sav_points_houses` (SAV bindus per
            house, string keys "1".."12") and `transit_house_positions`
            (current transiting-planet houses-from-Lagna snapshot), both
            already computed upstream by jyotish/engine_io.py.
        start_year, end_year: inclusive calendar-year range to rank.
            Capped at MAX_YEAR_SPAN years; an excessive span returns a
            RANGE_TOO_LARGE diagnostic instead of computing.
        timing_windows: optional list of dasha/bhukti window dicts from
            timing.py's _compute_windows_and_status()/_business_ad_windows()
            (or compute_business_prediction(...)['timed_windows']), used
            only to annotate each ranked year with overlapping dasha
            corroboration -- never recomputed here.
        as_of_date: override for "today" (the transit snapshot's
            reference date); defaults to date.today(). Exposed mainly for
            deterministic testing, matching timing.py's convention.

    Returns a dict that never raises on its own:
        {"status": "OK", "start_year", "end_year", "business_houses",
         "ranked_years": [ {year, sav_score, bav_bonus, composite_score,
             tier, jupiter_house, saturn_house, houses_supporting,
             bav_bindus_jupiter, bav_bindus_saturn, bav_interpretation
             (per-planet WEAK/NEUTRAL/FAVORABLE/BAV_UNAVAILABLE label),
             bav_status (OK/NOT_APPLICABLE/UNAVAILABLE), dasha_corroboration,
             reasons: {detail, effect}} , ... ]  # sorted composite_score desc
         "model_status", "calibration_status", "maturity_statement"}
    or, on any of the diagnosed failure modes below, {"status": <code>,
    "note": <human-readable reason>, "ranked_years": []}.
    """
    base: Dict[str, Any] = {
        "start_year": start_year,
        "end_year": end_year,
        "business_houses": list(BUSINESS_SAV_HOUSES),
        "ranked_years": [],
        "model_status": MODEL_STATUS,
        "calibration_status": CALIBRATION_STATUS,
        "maturity_statement": MATURITY_STATEMENT,
    }

    try:
        start_year = int(start_year)
        end_year = int(end_year)
    except (TypeError, ValueError):
        return {**base, "status": "INVALID_RANGE", "note": "start_year/end_year must be integers."}

    if end_year < start_year:
        return {**base, "status": "INVALID_RANGE", "note": "end_year must be >= start_year."}

    if (end_year - start_year + 1) > MAX_YEAR_SPAN:
        return {
            **base, "status": "RANGE_TOO_LARGE",
            "note": (
                f"Requested span ({end_year - start_year + 1} years) exceeds "
                f"MAX_YEAR_SPAN={MAX_YEAR_SPAN}. Narrow the range to keep the "
                f"per-year transit projection bounded."
            ),
        }

    lagna_sign = getattr(payload, "lagna_sign", "") or getattr(payload, "d1_lagna", "") or ""
    dob = getattr(payload, "dob", "") or ""
    if not payload or not lagna_sign or not dob:
        return {**base, "status": "MISSING_BIRTH_DATA", "note": "Payload lacks lagna_sign/dob; cannot compute year ranking."}

    sav = getattr(payload, "sav_points_houses", None) or {}
    if not sav:
        return {**base, "status": "SAV_UNAVAILABLE", "note": "payload.sav_points_houses is empty; upstream Ashtakavarga computation did not run for this chart."}

    transit_hp = getattr(payload, "transit_house_positions", None) or {}
    jup_snapshot = transit_hp.get("Jupiter", 0)
    sat_snapshot = transit_hp.get("Saturn", 0)
    # A snapshot is now only the graceful fallback.  Real mid-year
    # ephemeris positions are attempted first for every requested year.

    try:
        today = as_of_date or date.today()
        # Gap-fix: average only over houses actually present in `sav`,
        # rather than letting sav_lookup()'s neutral default (28, the
        # SAV grand-total-per-house mean) silently stand in for missing
        # houses and pull the average toward "average" instead of leaving
        # it undefined. sav_lookup()'s 28-default remains correct for its
        # other call sites (threshold checks / bounded +-8% modifiers in
        # house_evidence.py, significators.py, mode_gate.py) where a
        # missing house failing to clear a threshold, or contributing a
        # zero delta, is the intended neutral-safe behavior -- this is
        # the one site where 28 was silently entering an arithmetic mean.
        _business_sav_present = [h for h in BUSINESS_SAV_HOUSES if str(h) in sav or h in sav]
        if _business_sav_present:
            business_avg = sum(sav_lookup(sav, h) for h in _business_sav_present) / len(_business_sav_present)
        else:
            business_avg = 28.0  # no business houses present at all -- fall back to the documented neutral baseline

        ranked: List[Dict[str, Any]] = []
        for year in range(start_year, end_year + 1):
            mid_year = date(year, 7, 1)
            days_ahead = (mid_year - today).days

            ephemeris_houses = _ephemeris_slow_mover_houses(payload, year, lagna_sign)
            jup_house = ephemeris_houses.get("Jupiter") or (_project_house("Jupiter", jup_snapshot, days_ahead) if jup_snapshot else 0)
            sat_house = ephemeris_houses.get("Saturn") or (_project_house("Saturn", sat_snapshot, days_ahead) if sat_snapshot else 0)
            transit_position_source = "REAL_EPHEMERIS_MIDYEAR" if ephemeris_houses else "MEAN_MOTION_FALLBACK"

            bonus = 0.0
            houses_supporting: List[str] = []
            # planet -> (bindus|None, weighted bonus contributed) for the
            # BAV-tempering component below; only populated for a planet
            # whose transiting house is itself business-relevant (same
            # gating as the SAV bonus above), since BAV here is meant to
            # TEMPER/reinforce that specific SAV signal, not act as an
            # independent house-agnostic score.
            bav_bindus: Dict[str, Optional[int]] = {"Jupiter": None, "Saturn": None}
            bav_bonus = 0.0
            bav_detail_parts: List[str] = []
            bav_unavailable = False

            if jup_house in BUSINESS_SAV_HOUSES:
                jup_bindus = sav_lookup(sav, jup_house)
                bonus += jup_bindus * 0.5
                houses_supporting.append(f"H{jup_house} (transiting Jupiter, natal SAV={jup_bindus})")

                jup_bav = _bav_lookup(payload, "Jupiter", jup_house)
                bav_bindus["Jupiter"] = jup_bav
                if jup_bav is not None:
                    bav_bonus += (jup_bav - _BAV_NEUTRAL_BINDU) * _BAV_WEIGHT["Jupiter"]
                    bav_detail_parts.append(
                        f"Jupiter BAV(H{jup_house})={jup_bav} bindus ({_bav_interpretation(jup_bav)})"
                    )
                else:
                    bav_unavailable = True

            if sat_house in BUSINESS_SAV_HOUSES:
                sat_bindus = sav_lookup(sav, sat_house)
                bonus += sat_bindus * 0.25
                houses_supporting.append(f"H{sat_house} (transiting Saturn, natal SAV={sat_bindus})")

                sat_bav = _bav_lookup(payload, "Saturn", sat_house)
                bav_bindus["Saturn"] = sat_bav
                if sat_bav is not None:
                    bav_bonus += (sat_bav - _BAV_NEUTRAL_BINDU) * _BAV_WEIGHT["Saturn"]
                    bav_detail_parts.append(
                        f"Saturn BAV(H{sat_house})={sat_bav} bindus ({_bav_interpretation(sat_bav)})"
                    )
                else:
                    bav_unavailable = True

            sav_score = round(business_avg + bonus, 2)
            bav_bonus = round(bav_bonus, 2)
            dasha_corr = _dasha_corroboration_for_year(year, timing_windows)
            dasha_adjustment = _dasha_year_adjustment(dasha_corr)
            composite_score = round(sav_score + bav_bonus + dasha_adjustment, 2)
            tier = _tier_for_score(composite_score)
            bav_status = "UNAVAILABLE" if bav_unavailable else ("OK" if bav_detail_parts else "NOT_APPLICABLE")

            bav_interpretation = {
                "Jupiter": _bav_interpretation(bav_bindus["Jupiter"]),
                "Saturn": _bav_interpretation(bav_bindus["Saturn"]),
            }

            # Weight breakdown (documented for audit): composite_score =
            # sav_score (business-house natal SAV average + SAV transit
            # bonus, Jupiter x0.5/bindu, Saturn x0.25/bindu -- unchanged from
            # the pre-BAV scoring) + bav_bonus ((planet's own post-shodhana
            # BAV bindu count in its transited business house minus the
            # neutral bindu=5) x Jupiter-weight 2.0 / Saturn-weight 1.0).
            # sav_score is kept as its own field for backward compatibility
            # (pre-BAV callers/tests reading sav_score directly); tier/sort
            # order now use composite_score, which equals sav_score exactly
            # whenever BAV is unavailable or not applicable (graceful
            # degradation -- see bav_status).
            detail = (
                f"Business-house (H{'/'.join(str(h) for h in BUSINESS_SAV_HOUSES)}) "
                f"natal SAV average={business_avg:.1f}"
                + (f"; +{', '.join(houses_supporting)}" if houses_supporting else "; no slow-mover transit through a business house this year")
                + f" -> SAV score {sav_score:.1f}."
                + (
                    f" BAV tempering: {'; '.join(bav_detail_parts)} -> BAV bonus {bav_bonus:+.1f}."
                    if bav_detail_parts
                    else (" BAV tempering unavailable this call -- degraded to SAV-only scoring." if bav_unavailable else "")
                )
                + f" Composite score {composite_score:.1f} ({tier})."
                + (f" Dasha arbitration {dasha_adjustment:+.1f}." if dasha_corr else " Dasha arbitration unavailable.")
            )
            effect = {
                "EXCELLENT": "A strong Ashtakavarga-supported year for business decisions.",
                "GOOD": "A favorable Ashtakavarga year for business decisions.",
                "AVERAGE": "An ordinary Ashtakavarga year -- neither especially supportive nor unsupportive.",
                "WEAK": "A weaker Ashtakavarga year -- exercise more caution with major business decisions.",
            }[tier]

            ranked.append({
                "year": year,
                "sav_score": sav_score,
                "bav_bonus": bav_bonus,
                "composite_score": composite_score,
                "dasha_adjustment": dasha_adjustment,
                "tier": tier,
                "transit_position_source": transit_position_source,
                "jupiter_house": jup_house or None,
                "saturn_house": sat_house or None,
                "houses_supporting": houses_supporting,
                "bav_bindus_jupiter": bav_bindus["Jupiter"],
                "bav_bindus_saturn": bav_bindus["Saturn"],
                "bav_interpretation": bav_interpretation,
                "bav_status": bav_status,
                "dasha_corroboration": dasha_corr,
                "reasons": {"detail": detail, "effect": effect},
            })

        ranked.sort(key=lambda r: r["composite_score"], reverse=True)
        return {**base, "status": "OK", "ranked_years": ranked}
    except Exception as exc:
        return {**base, "status": "COMPUTATION_FAILED", "note": f"{type(exc).__name__}: {exc}"}
