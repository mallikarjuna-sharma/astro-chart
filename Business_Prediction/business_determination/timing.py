"""
Business_Prediction/business_engine.py
=======================================
Business/entrepreneurship prediction engine for JyotishAI.

MATURITY STATEMENT (read this before treating any output as authoritative):

    Architecturally mature and internally validated: implementation rules,
    invariants, regression behavior, and end-to-end execution are tested.
    Real-world predictive validity has NOT been established, because no
    prospective labeled outcome corpus has been evaluated. Astrological
    precedence and conflict resolution remain explicit engineered
    interpretations, not uniquely authoritative classical doctrine.

Concretely, keep these distinctions in mind whenever reading this module's
output or test suite:

  - Tests validate implementation -- not predictions. A green test suite
    proves the code executes its own intended rules; it does not prove
    those rules are astrologically complete or empirically accurate.
  - Synthetic data (Business_Prediction/synthetic_calibration_seed.py)
    validates the CALIBRATION PIPELINE -- not the model. It proves
    validate_outcomes()/score_calibration() work end-to-end on fabricated
    rows; it says nothing about this engine's real predictive accuracy.
  - Classical coverage does not imply classical consensus. Where this
    module cites a classical method (Phaladeepika ch.5, Viparita Raja
    Yoga, KP significators, Jaimini karakas), it implements ONE documented
    reading of that method, not the only one a traditional astrologer
    would accept, and it does not yet handle every rare yoga, cancellation
    condition, or conflicting-yoga interaction a full classical review
    would consider.
  - "Heuristic tier" (HIGH/MODERATE/LOW) is not statistical confidence.
    It is a deterministic threshold on two already-computed scores, not a
    measured probability or a claim backed by a labeled outcome corpus.
  - Outputs are decision-support narratives, not financial forecasts. They
    exist to prompt further astrological review and human judgment, not to
    be acted on as investment or career advice.

This module has NOT been empirically calibrated against dated business
outcomes (see CALIBRATION_STATUS / Business_Prediction/calibration.py).
Every score below is a rule-weighted, dignity-gated, multi-varga-
corroborated heuristic -- extensively tested for internal consistency, not
validated against real-world outcomes. See `model_status` /
`evidence_basis` / `calibration_status` / `maturity_statement` in every
returned dict for a machine-readable statement of these limits.

Mirrors the layered pipeline used across the engine (Stream_Determination /
Field_Determination / Job_Career): a shared NatalPayloadV2 chart object is
scored by domain-specific layers that reuse, wherever possible, primitives
that already exist elsewhere in the repo rather than re-deriving them:

  Layer 1 — Viability gate
      compute_business_mode_gate(payload) (this module) computes signed,
      dignity-gated, D9/D10-corroborated employment/business/independent/
      family_business scores -- the same evidence policy as Layer 2 below,
      not the older jyotish.employment_mode.compute_employment_mode(),
      which used several unconditional/ungated rules (Rahu-in-H7, DK in
      any kendra/trikona, independent Mercury+Venus placement, empty-H7 as
      positive evidence) and had no negative ledger or varga corroboration.
      Its business_score / independent_score / family_biz_score gate
      whether business-track analysis should be surfaced for this chart,
      and compute_business_prediction() additionally requires the
      venture-type score to beat employment_score by a minimum margin
      before "proceed" is set (comparative advantage, not just absolute
      viability).

  Layer 2 — House/planet business-strength significators
      Business-specific (H2/H3/H6/H7/H9/H10/H11/H12 + planetary roles),
      now with dignity-gated exceptions (Viparita Raja Yoga case for
      dusthana lords, debilitation checks before "fortune supports"
      claims) instead of unconditional signal-sum rules. Produces a
      positive/negative evidence ledger, not a single opaque number.

  Layer 3 — Sector/domain scoring
      Blends three components per sector, all three actually reading the
      registry's declared `core_houses` / `core_planets` (previously only
      the generic archetype vector was used and core_houses/core_planets
      were declared but dead):
        (a) generic archetype vector (jyotish.d10_archetypes math, general
            aptitude signature, not sector-specific)
        (b) core_houses strength: lordship placement + dignity of each
            house the registry declares for that sector
        (c) core_planets strength: dignity + placement of each planet the
            registry declares as a driver for that sector

  Layer 4 — Timed windows, bounded forecast horizon
      Reuses Job_Career.timeline._dasha_calendar (MD/AD calendar
      expansion), bounded to an explicit forecast window (default: today
      .. +years_ahead) instead of the chart owner's full lifetime. Each AD
      window gets a signed net evidence score (dignity, dusthana
      lordship/VRY exception, corroboration between MD and AD) and a
      single dominant label instead of independently-fireable, possibly
      contradictory tags.

Public API
----------
    compute_business_prediction(payload, venture_type="business",
                                 years_ahead=15) -> dict
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from jyotish.d10_archetypes import (
    PLANET_ARCHETYPES,
    ARCHETYPE_NAMES,
    DIGNITY,
    scale_raw_support,
)


"""business_determination.timing

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .house_evidence import _record_diagnostic
from .jaimini import _jaimini_business_score
from .kp import _kp_business_cusp_score, _kp_sublord_signification_bias, _verify_kp_cusp_chain
from .significators import _DUSTHANA, _STRONG_DIGNITY, _dig_factor, _dig_name


def _d9_d10_corroboration(ad_lord: str, payload: Any) -> Tuple[float, List[str]]:
    """Net evidence delta from the AD lord's D9 (Navamsha -- partnership/
    marriage-adjacent strength, used classically to confirm whether a D1
    promise actually fructifies) and D10 (Dashamsha -- livelihood/karma)
    dignity. EXALTED/OWN corroborates the D1 read; DEBILITATED contradicts
    it and should pull the window down even if D1 alone looked favorable."""
    d9 = getattr(payload, "d9_planet_dignities", {}) or {}
    d10 = getattr(payload, "d10_planet_dignities", {}) or {}
    notes: List[str] = []
    net = 0.0

    d9_dig = str(d9.get(ad_lord, "") or "").upper()
    if d9_dig in _STRONG_DIGNITY:
        net += 4
        notes.append(f"D9 dignity of AD lord {ad_lord} is {d9_dig} -> Navamsha confirms D1 promise")
    elif d9_dig == "DEBILITATED":
        net -= 4
        notes.append(f"D9 dignity of AD lord {ad_lord} is DEBILITATED -> Navamsha contradicts D1 promise")

    d10_dig = str(d10.get(ad_lord, "") or "").upper()
    if d10_dig in _STRONG_DIGNITY:
        net += 4
        notes.append(f"D10 dignity of AD lord {ad_lord} is {d10_dig} -> Dashamsha confirms livelihood strength")
    elif d10_dig == "DEBILITATED":
        net -= 4
        notes.append(f"D10 dignity of AD lord {ad_lord} is DEBILITATED -> Dashamsha undermines livelihood strength")

    return net, notes

def _shadbala_corroboration(ad_lord: str, payload: Any) -> Tuple[float, List[str]]:
    """eff_strengths is shadbala/minimum-shadbala-required ratio (1.0 =
    bare minimum, >1 = stronger). A dasha lord below its own minimum
    functional strength should not be read as favorable regardless of
    house lordship, and a strongly above-minimum lord corroborates it."""
    eff = getattr(payload, "eff_strengths", {}) or {}
    ratio = eff.get(ad_lord)
    if ratio is None:
        return 0.0, []
    if ratio >= DECISION_POLICY.shadbala_strong_ratio:
        return 3.0, [f"AD lord {ad_lord} Shadbala eff_strength={ratio:.2f} (well above minimum) -> corroborates"]
    if ratio < DECISION_POLICY.shadbala_weak_ratio:
        return -5.0, [f"AD lord {ad_lord} Shadbala eff_strength={ratio:.2f} (below minimum) -> weak execution capacity"]
    return 0.0, []

_TRANSIT_STATUS_APPLIED = "APPLIED"           # ran, produced >=1 scorable flag

_TRANSIT_STATUS_NO_FLAGS = "NO_FLAGS"         # ran successfully, nothing to report this window

_TRANSIT_STATUS_MISSING_DATA = "MISSING_DATA"  # no lagna_sign on payload -- can't even attempt

_TRANSIT_STATUS_IMPORT_FAILED = "IMPORT_FAILED"      # Job_Career.timeline unavailable

_TRANSIT_STATUS_COMPUTATION_FAILED = "COMPUTATION_FAILED"  # ran and raised

# v-audit fix (astrological completeness, item 28 -- "transits remain
# mean-motion approximations"): jyotish/ephemeris.py already has a genuine
# Skyfield/DE421-backed get_transit_house_positions() (real sidereal
# ephemeris longitudes, not mean-motion projection from a natal snapshot)
# that was previously never wired into Business_Prediction at all. It is an
# OPTIONAL capability -- gated behind the `skyfield` package plus a one-time
# ~17MB DE421 ephemeris file download (see that module's own docstring) --
# so this is a preference, not a replacement: when real ephemeris is
# available (skyfield installed AND de421.bsp already cached/downloadable),
# _transit_corroboration() below uses genuine planetary longitudes for the
# period midpoint instead of Job_Career.timeline's mean-motion projection;
# when it is not available (as in this repo's own sandboxed test/dev
# environment, which has no `skyfield` installed and no network access to
# fetch the ephemeris file), this degrades to EXACTLY the pre-existing
# mean-motion path, unchanged. Every note is tagged with which source
# produced it, so a reader can always tell precision-graded transits from
# mean-motion-approximated ones.
def _real_ephemeris_transit_flags(mid_date: date, payload: Any, lagna_sign: str) -> Optional[List[str]]:
    """Returns the same flag vocabulary Job_Career.timeline._get_dynamic_
    transits() emits for the 4 flag families _transit_corroboration()
    actually consumes (JUPITER_H{n}_EXPANSION/_STRESS, SATURN_H{n}_
    DISRUPTION, RAHU_KETU_AXIS_MAJOR_CHANGE), computed from REAL sidereal
    longitudes at `mid_date` (noon local, an engineered simplification --
    exact time-of-day makes negligible difference to Jupiter/Saturn/Rahu's
    house position over the course of one day) via jyotish.ephemeris.
    get_transit_house_positions(), rather than projected mean motion.

    Returns None (not [] -- these are genuinely different states) when the
    real-ephemeris path cannot be used at all (skyfield/DE421 unavailable,
    or payload lacks latitude/longitude) -- callers must fall back to the
    mean-motion path in that case, exactly as before this fix existed."""
    try:
        from jyotish import ephemeris as _ephemeris
    except Exception as exc:
        _record_diagnostic("timing._real_ephemeris_transit_flags", exc, note="ephemeris import failed")
        return None
    if not _ephemeris.is_available():
        return None

    lat = getattr(payload, "latitude", None)
    lon = getattr(payload, "longitude", None)
    if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
        return None

    try:
        mid_dt = datetime(mid_date.year, mid_date.month, mid_date.day, 12, 0, 0)
        house_positions, _degrees, _retro = _ephemeris.get_transit_house_positions(mid_dt, float(lat), float(lon), lagna_sign)
    except Exception as exc:
        _record_diagnostic("timing._real_ephemeris_transit_flags", exc, note="real-ephemeris transit computation failed")
        return None
    if not house_positions:
        return None

    flags: List[str] = []
    jup_h = house_positions.get("Jupiter", 0)
    if jup_h in (2, 5, 9, 10, 11):
        flags.append(f"JUPITER_H{jup_h}_EXPANSION")
    elif jup_h in (6, 8, 12):
        flags.append(f"JUPITER_H{jup_h}_STRESS")

    sat_h = house_positions.get("Saturn", 0)
    if sat_h in (6, 8):
        flags.append(f"SATURN_H{sat_h}_DISRUPTION")

    rahu_h = house_positions.get("Rahu", 0)
    if rahu_h in (1, 4, 7, 10):
        flags.append("RAHU_KETU_AXIS_MAJOR_CHANGE")

    return flags


def _flags_to_net_and_notes(flags: List[str], source_tag: str) -> Tuple[float, List[str]]:
    """Shared flag -> (net, notes) translation for both the real-ephemeris
    and mean-motion transit paths, so the two can never silently diverge on
    what a given flag is worth -- only WHICH flags get computed (from real
    longitudes vs. projected ones) differs between the two callers.
    `source_tag` (e.g. "[REAL EPHEMERIS]" / "[MEAN-MOTION APPROX]") is
    prefixed onto every note so a reader can always tell which precision
    tier produced a given citation."""
    net = 0.0
    notes: List[str] = []
    for flag in flags:
        if flag in ("JUPITER_H2_EXPANSION", "JUPITER_H11_EXPANSION"):
            net += 5
            notes.append(f"{source_tag} Transit: {flag} -> capital/gains house activated by Jupiter")
        elif flag.startswith("JUPITER_H") and flag.endswith("_STRESS"):
            net -= 3
            notes.append(f"{source_tag} Transit: {flag} -> Jupiter transiting a dusthana, muted expansion")
        elif flag.startswith("SATURN_H") and flag.endswith("_DISRUPTION"):
            net -= 4
            notes.append(f"{source_tag} Transit: {flag} -> Saturn transiting H6/H8, obstruction/delay likely")
        elif flag == "RAHU_KETU_AXIS_MAJOR_CHANGE":
            notes.append(f"{source_tag} Transit: RAHU_KETU_AXIS_MAJOR_CHANGE -> elevated volatility, direction-neutral")
    return net, notes


def _transit_corroboration(
    period_start: date,
    period_end: date,
    payload: Any,
    today: date,
) -> Tuple[float, List[str], str]:
    """Prefers genuine Skyfield/DE421 ephemeris longitudes for the period
    midpoint (see _real_ephemeris_transit_flags() above) when that optional
    capability is available; otherwise falls back to Job_Career.timeline.
    _get_dynamic_transits (mean-motion projection of Jupiter/Saturn/Rahu/
    Mars/etc. from the natal snapshot, the same projection the career
    timeline uses) -- exactly the pre-existing behavior when real ephemeris
    isn't available. Reads the business-relevant flags: JUPITER_H{2,11}_
    EXPANSION (capital/gains) is positive, JUPITER_H{6,8,12}_STRESS and
    SATURN_H{6,8}_DISRUPTION are negative, RAHU_KETU_AXIS_MAJOR_CHANGE is
    flagged as elevated volatility (not scored, since Rahu-Ketu axis change
    can favor unconventional business as easily as disrupt it).

    Returns (net, notes, status) -- status distinguishes "ran fine, nothing
    to report" (NO_FLAGS) from "couldn't even attempt" (MISSING_DATA) from
    an actual import/runtime failure (IMPORT_FAILED/COMPUTATION_FAILED).
    Previously all four cases collapsed to (0.0, []), which is why
    method_status could report PRESENT_NOT_TRIGGERED for a window where
    transit computation had actually raised an exception.
    """
    lagna_sign = getattr(payload, "lagna_sign", "") or getattr(payload, "d1_lagna", "") or ""
    if not lagna_sign:
        return 0.0, [], _TRANSIT_STATUS_MISSING_DATA

    mid = period_start + (period_end - period_start) // 2
    real_flags = _real_ephemeris_transit_flags(mid, payload, lagna_sign)
    if real_flags is not None:
        net, notes = _flags_to_net_and_notes(real_flags, "[REAL EPHEMERIS]")
        return net, notes, (_TRANSIT_STATUS_APPLIED if notes else _TRANSIT_STATUS_NO_FLAGS)

    try:
        from Job_Career.timeline import TimelineChartInput, get_dynamic_transits
    except Exception as exc:
        # Engineering audit fix #9: this used to swallow the import failure
        # entirely (no exception detail captured anywhere) -- a genuine bug
        # (e.g. a renamed symbol in Job_Career.timeline) was indistinguishable
        # from Job_Career simply not being installed. Now recorded, without
        # changing the graceful IMPORT_FAILED fallback itself.
        _record_diagnostic("timing._transit_corroboration", exc, note="Job_Career.timeline import failed")
        return 0.0, [], _TRANSIT_STATUS_IMPORT_FAILED

    try:
        chart = TimelineChartInput.from_payload(payload)
        flags = get_dynamic_transits(period_start, period_end, chart, lagna_sign, today)
    except Exception as exc:
        _record_diagnostic("timing._transit_corroboration", exc, note="dynamic transit computation failed")
        return 0.0, [f"Transit computation failed: {type(exc).__name__}: {exc}"], _TRANSIT_STATUS_COMPUTATION_FAILED

    net, notes = _flags_to_net_and_notes(flags, "[MEAN-MOTION APPROX]")
    return net, notes, (_TRANSIT_STATUS_APPLIED if notes else _TRANSIT_STATUS_NO_FLAGS)

from .policy import DECISION_POLICY

_WINDOW_LABELS = DECISION_POLICY.timing_labels

def _label_for_net(net: float) -> str:
    for threshold, label in _WINDOW_LABELS:
        if net >= threshold:
            return label
    return "HIGH_RISK"

# v46 audit fix (item 4, "KP weighting" -- user-directed): this repo's
# actual weighting policy for verified KP cusp evidence versus D1/D9/D10
# evidence already EXISTS in code (the tiered arbitration_ledger structure
# built inside _compute_windows_and_status below), but was never stated as
# a single, named, top-level policy a reader could find without
# reverse-engineering it from five separate tier blocks and their inline
# comments. This constant is that explicit statement -- describing the
# already-implemented behavior, not changing it -- and is attached to the
# returned `status` dict (see "kp_weighting_policy" below) so it's directly
# visible to any caller/report, not just discoverable by reading source.
KP_WEIGHTING_POLICY = {
    "policy_version": "v46",
    "tiers": [
        {"tier": "0_D1_FOUNDATIONAL", "role": "BASE", "note": "D1 house-lordship/dignity evidence sets the starting net score for every window."},
        {"tier": "1_D9_D10_CONFIRM_DENY", "role": "CAP_OR_FLOOR", "note": "D9 (Navamsha) and D10 (Dashamsha) dignity of the AD lord caps promise downward (debilitation denies/limits fructification) or adds a confirmation bonus (both strong) -- does not by itself override direction, only bounds magnitude."},
        {"tier": "2_KP_FINAL_ARBITER", "role": "CONDITIONAL_OVERRIDE", "note": "Verified KP (chain_verified=True) H7-cusp-sublord evidence, when the sub-lord matches the window's own MD/AD lord AND D9 is not debilitated, can override net toward a floor of +10 (positive signification bias) or ceiling of -8 (negative bias) -- the ONLY tier permitted to override rather than merely bound. Unverified KP chains fall back to additive-only weight, never override."},
        {"tier": "3_JAIMINI", "role": "ADDITIVE", "note": "Rasi drishti / argala evidence adds/subtracts from net; never overrides Tier 0-2's direction on its own."},
        {"tier": "3B_CHARA_DASHA", "role": "ADDITIVE", "note": "Chara Dasha (Standard Jaimini sign-based period system) overlap corroboration: the dignity of the overlapping Chara antardasha/mahadasha sign's lord adds a small (+/-3) additive nudge -- the smallest single weight in this table, since this is a second, independent period system read as corroboration, never as a primary or overriding signal."},
        {"tier": "4_TRANSIT_SHADBALA", "role": "ADDITIVE", "note": "Real-ephemeris transit flags and Shadbala-derived strength modifiers are the final additive layer, smallest individual weight."},
    ],
    "summary": (
        "D1 sets the base; D9/D10 bound it; verified KP can override it (unverified KP cannot); "
        "Jaimini and transit/Shadbala are additive refinements on top. KP's authority over D1/D9/D10 "
        "is therefore CONDITIONAL, not absolute -- it requires independent chain verification "
        "(jyotish.kp_audit) AND a specific H7-cusp-sublord/dasha-lord match to override at all."
    ),
}

# v46 audit fix (item 6, "timing-window granularity" -- user-directed):
# reuses the exact house-to-event mapping already established in
# kp.py::_KP_EVENT_TYPE_HOUSES (v41) so the same six business-event
# categories are used consistently across this engine, rather than
# inventing a second, differently-named taxonomy for window-level scoring.
_WINDOW_EVENT_TYPE_HOUSES = {
    "starting_or_launching": (1, 3),
    "investing_or_capital_deployment": (2, 8),
    "partnering": (7,),
    "expanding_or_scaling": (11,),
    "borrowing": (8, 6),
    "exiting_or_closing": (12, 8),
}

def _chara_dasha_window_corroboration(
    chara_calendar: List[Dict[str, Any]],
    window_start: date,
    window_end: date,
    house_lords: Dict[str, Any],
    dignities: Dict[str, Any],
) -> Tuple[float, List[str]]:
    """v-audit fix (bounded-limitation follow-up, user-directed): the
    additive-only Chara Dasha <-> Vimshottari-window corroboration
    described above _chara_calendar's computation. Finds the Chara Dasha
    antardasha (or mahadasha, if no antardasha entries) with the GREATEST
    date-range overlap against [window_start, window_end], then reads that
    sign's own lord's D1 dignity as a small (+/-3, capped, never override)
    corroboration/caution -- deliberately the smallest single additive
    weight in this function (compare Jaimini's up to +8, Tier1 D9/D10's up
    to +/-8) since this is a SECOND, independent sign-based period system
    being read as corroborating evidence for a Vimshottari (nakshatra-
    based) window, not a primary signal for it."""
    from jyotish.constants import _SIGN_LORD
    best_overlap_days = 0
    best_sign = ""
    for md_entry in chara_calendar:
        sub_entries = md_entry.get("antardashas") or [md_entry]
        for sub in sub_entries:
            try:
                s = date.fromisoformat(sub["start"])
                e = date.fromisoformat(sub["end"])
            except (KeyError, ValueError):
                continue
            overlap = (min(e, window_end) - max(s, window_start)).days
            if overlap > best_overlap_days:
                best_overlap_days = overlap
                best_sign = sub.get("sign", "")
    if not best_sign or best_overlap_days <= 0:
        return 0.0, []
    lord = _SIGN_LORD.get(best_sign, "")
    if not lord:
        return 0.0, []
    dig = _dig_name(lord, dignities)
    if dig in _STRONG_DIGNITY:
        return 3.0, [f"Chara Dasha (additive corroboration): overlapping period is {best_sign} (lord {lord}, {dig}) -- supportive (+3)"]
    if dig == "DEBILITATED":
        return -3.0, [f"Chara Dasha (additive caution): overlapping period is {best_sign} (lord {lord}, DEBILITATED) -- mild caution (-3)"]
    return 0.0, []


def _window_event_type_signals(ruled_houses: Set[int]) -> Dict[str, bool]:
    """Coarse structural overlay on a timed window: for each business event
    type, whether this window's dasha lords (MD or AD) structurally rule at
    least one of that event's associated houses. Deliberately boolean/coarse
    (touches vs doesn't), not a re-scored net -- a full per-event favorable/
    unfavorable score would need its own dignity/aspect evaluation per event,
    which is a larger, separately-scoped extension beyond this pass. Only
    events with at least one ruled house are included (sparse dict), same
    convention as kp.py's event_type_signals."""
    return {
        event: True
        for event, houses in _WINDOW_EVENT_TYPE_HOUSES.items()
        if ruled_houses & set(houses)
    }


def _window_event_type_scores(
    ad_lord: str,
    md_lord: str,
    ad_houses: Set[int],
    md_houses: Set[int],
    dignities: Dict[str, Any],
) -> Dict[str, float]:
    """v-audit fix (bounded-limitation follow-up, user-directed): per-event
    SIGNED score, closing the "coarse Boolean signals, not separate
    per-event scores" gap explicitly named in this pass. Rule (a modeling
    choice, disclosed as such, not a re-derivation of the window's own
    D1/D9/D10/KP/Jaimini net_score): for each event type, look at whichever
    of AD lord / MD lord structurally rules at least one of that event's
    associated houses; each such lord contributes +6 if STRONG_DIGNITY,
    -6 if DEBILITATED, 0 otherwise (own dignity, per _dig_name/
    _STRONG_DIGNITY -- the same dignity vocabulary used everywhere else in
    this file). If both AD and MD lord touch the same event, their
    contributions sum (so a doubly-corroborated event can reach +/-12).
    Only events with at least one touching lord are included (sparse dict,
    matching event_type_signals' convention) -- an event with NO touching
    lord is absent, not scored 0, so a caller can distinguish "not
    applicable this window" from "applicable but dignity-neutral"."""
    scores: Dict[str, float] = {}
    for event, houses in _WINDOW_EVENT_TYPE_HOUSES.items():
        event_houses = set(houses)
        touches_ad = bool(ad_houses & event_houses)
        touches_md = bool(md_houses & event_houses)
        if not touches_ad and not touches_md:
            continue
        score = 0.0
        if touches_ad:
            dig = _dig_name(ad_lord, dignities)
            if dig in _STRONG_DIGNITY:
                score += 6.0
            elif dig == "DEBILITATED":
                score -= 6.0
        if touches_md:
            dig = _dig_name(md_lord, dignities)
            if dig in _STRONG_DIGNITY:
                score += 6.0
            elif dig == "DEBILITATED":
                score -= 6.0
        scores[event] = score
    return scores

def _timing_computation_status(
    payload: Any,
    years_ahead: int = 15,
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Diagnoses WHY _business_ad_windows() may have returned few or zero
    windows, so callers can distinguish "no astrologically significant
    periods in this forecast horizon" (a real finding) from "the dasha
    calendar failed to compute" (a data/engine failure) or "no dasha data
    was available at all" -- previously all three cases produced an
    identical empty list with no way to tell them apart from the outside.

    True wrapper around _compute_windows_and_status() (defined below) --
    this used to independently reconstruct the calendar with its own
    try/except, which meant a caller could get a status here that
    disagreed with what the production window-scoring pass actually
    experienced if the two computations diverged for any reason. Now there
    is exactly one code path that ever calls _dasha_calendar() for a given
    (payload, years_ahead, as_of_date): _compute_windows_and_status().
    compute_business_prediction() already calls that function directly
    (not this one) for exactly this reason; this wrapper remains for
    standalone diagnostic callers who want just the status without paying
    to also compute+discard the full windows list -- it still does that
    work internally (Python's cost model doesn't allow avoiding it while
    guaranteeing single-source-of-truth status), but no caller can ever see
    a status that isn't byte-identical to what window-scoring itself saw.
    """
    _windows, status = _compute_windows_and_status(payload, years_ahead=years_ahead, as_of_date=as_of_date)
    return status

def _compute_windows_and_status(
    payload: Any,
    years_ahead: int = 15,
    as_of_date: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Score each AD window that overlaps [as_of, as_of + years_ahead]
    (default: today .. +15y), instead of the chart owner's entire dasha
    lifetime. Reuses Job_Career.timeline._dasha_calendar for MD/AD dates.

    Each window gets ONE signed net-evidence score and ONE dominant label,
    replacing the earlier independently-fireable boolean tags that could
    contradict each other (e.g. VENTURE_FAVORABLE and LOSS_LIABILITY_RISK
    on the same window with no resolution).

    The net score is produced by TIERED PRECEDENCE ARBITRATION (D1
    foundational -> D9/D10 confirm/deny -> KP sub-lord final arbiter ->
    Jaimini activation -> transit/Shadbala trigger), not a flat sum of every
    method's evidence -- see the arbitration_ledger on each returned window
    and the docstring inline in this function's body. See EVIDENCE_BASIS.

    Returns (windows, status) computing the dasha calendar exactly ONCE --
    the status dict has the same shape as _timing_computation_status()'s
    return value, but is derived from the SAME calendar object the window
    loop below actually consumes, instead of a second independent
    computation. compute_business_prediction() uses this function (not
    _timing_computation_status() + _business_ad_windows() separately) so
    the two can never disagree if the calendar computation fails on one
    pass but not the other.
    """
    from Job_Career.timeline import build_dasha_calendar
    from Job_Career.timeline_inputs import parse_iso_date

    dob_str = getattr(payload, "dob", "") or ""
    dob = parse_iso_date(dob_str)
    dasha_seq = getattr(payload, "dasha_sequence", []) or []
    if not dob:
        return [], {"status": "NO_DOB", "error": None, "calendar_periods_found": 0}
    if not dasha_seq:
        return [], {"status": "NO_DASHA_SEQUENCE", "error": None, "calendar_periods_found": 0}

    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = getattr(payload, "planet_dignities", {}) or {}
    kp_cusps = getattr(payload, "kp_cusps", {}) or {}
    # v-audit fix (item 5, follow-on): computed ONCE here (not per MD/AD
    # window) and consulted by the Tier-2 "KP FINAL ARBITER" block below --
    # that block can hard-override a window's net score to a floor of +10
    # or a ceiling of -8 purely off the H7 cusp sub-lord's own signification
    # bias, which is exactly the mechanism kp.py::_verify_kp_cusp_chain
    # exists to validate. An unverified chain no longer overrides anything;
    # it falls through to the pre-existing weaker "ADDITIVE" cusp-match path
    # instead, same as when there's no H7-sub-lord dasha-lord match at all.
    _kp_chain_verified = bool(_verify_kp_cusp_chain(payload).get("chain_verified"))

    # v-audit fix (bounded-limitation follow-up, user-directed: "tackle all
    # bounded limitations" -- Chara Dasha recommendation integration):
    # computed ONCE here, same pattern as _kp_chain_verified above. Gated
    # to ADDITIVE-ONLY use inside the window loop below (new Tier
    # "3B_CHARA_DASHA") -- deliberately never an override tier like KP's
    # Tier 2, since merging a sign-based period system's own internal
    # confidence with the Vimshottari-anchored net score is the doctrinal
    # question the v46 entry declined to resolve unilaterally; additive-
    # only corroboration sidesteps that question by construction (it can
    # only nudge, never flip, a window's direction).
    _chara_lagna_sign = getattr(payload, "lagna_sign", "") or getattr(payload, "d1_lagna", "") or ""
    _chara_planets_d1 = getattr(payload, "planets_d1", {}) or {}
    try:
        from jyotish.astro import compute_chara_dasha_calendar as _compute_chara_dasha_calendar
        _chara_calendar = (
            _compute_chara_dasha_calendar(_chara_lagna_sign, _chara_planets_d1, dob)
            if _chara_lagna_sign and _chara_planets_d1 else []
        )
    except Exception as exc:
        _record_diagnostic("timing._compute_windows_and_status", exc, note="Chara calendar computation failed")
        _chara_calendar = []

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    h2_lord, h6_lord, h7_lord = _h(2), _h(6), _h(7)
    h8_lord, h9_lord, h11_lord, h12_lord = _h(8), _h(9), _h(11), _h(12)

    # v-audit fix (typed rule IDs -- "dasha directional voting still
    # interprets evidence strings"): scoring.py's _dasha_vote() currently
    # determines whether the nearest timed window's dasha lords favor
    # business or job houses by regex-scanning this window's own prose
    # evidence lines ("AD lord"/"MD lord"-prefixed strings) for H1/H3/H7 vs
    # H6 tokens -- structured lordship results converted into a vote by
    # matching house tokens in text, exactly the brittleness pattern
    # already fixed for significators.py's evidence ledger. This computes
    # the SAME underlying fact directly from house_lords (never from
    # prose) and attaches it to each window as new, additive fields, so a
    # future consumer (or this same vote, once verified equivalent against
    # every evidence-line template that currently feeds the regex) can
    # switch to reading structured house numbers instead of parsing text.
    # Deliberately NOT yet wired into _dasha_vote() itself in this pass --
    # that function's regex counts PER-LINE hits across several
    # differently-worded evidence templates (own-house lordship, dusthana
    # exception, MD+AD corroboration, ...), and swapping its mechanism
    # without individually verifying every template would risk silently
    # changing vote outcomes on charts where those templates diverge from
    # a simple "which houses does this lord rule" lookup. This is staged
    # as the safe, verified-independently first half of that migration.
    def _houses_ruled_by(planet: str) -> List[int]:
        if not planet:
            return []
        return sorted(h for h in range(1, 13) if _h(h) == planet)

    try:
        calendar = build_dasha_calendar(dasha_seq, dob)
    except Exception as exc:
        return [], {
            "status": "CALENDAR_COMPUTATION_FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "calendar_periods_found": 0,
        }

    if not calendar:
        return [], {"status": "CALENDAR_EMPTY", "error": None, "calendar_periods_found": 0}

    status: Dict[str, Any] = {"status": "OK", "error": None, "calendar_periods_found": len(calendar)}

    today = as_of_date or date.today()
    try:
        horizon_end = today.replace(year=today.year + years_ahead)
    except ValueError:
        horizon_end = today.replace(year=today.year + years_ahead, day=28)

    windows: List[Dict[str, Any]] = []
    transit_statuses: List[str] = []
    pd_statuses: List[str] = []
    for period in calendar:
        start_date = period.get("start_date")
        end_date = period.get("end_date")
        if not start_date or not end_date:
            continue
        if end_date < today or start_date > horizon_end:
            continue  # outside the requested forecast period

        md_lord = period.get("md_lord", "")
        ad_lord = period.get("ad_lord", "")

        # ═══════════════════════════════════════════════════════════════
        # TIERED PRECEDENCE ARBITRATION
        #
        # Earlier versions of this function summed every method's evidence
        # into one number -- KP, Jaimini, D9/D10, transit, and Shadbala all
        # had equal, purely additive weight. That understates classical
        # doctrine: D9 is a CONFIRM/DENY chart (a debilitated D9 lord can
        # deny a D1 promise outright, not just subtract a few points from
        # it), and KP treats the cusp sub-lord as the FINAL ARBITER of
        # fructification (a sub-lord match can force a window favorable
        # even against a lukewarm D1 read). Jaimini karaka periods and
        # transits are activation/trigger layers -- they can support or
        # caution, but classically do not create or deny the underlying
        # promise the way D9/D10/KP do.
        #
        # This is this module's own operationalization of that doctrine
        # ordering (the classical texts describe the roles, not numeric
        # override thresholds) -- an explicit, inspectable interpretive
        # choice, not a claim of unique classical authority. The
        # arbitration_ledger below records exactly which tier fired and
        # what it did, so the choice stays auditable rather than a black
        # box.
        #
        # Tier 0 (FOUNDATIONAL, D1 lordship)  -> base_net, uncapped
        # Tier 1 (CONFIRM/DENY, D9+D10)        -> can CAP base_net's ceiling
        #                                          or floor, not just add
        # Tier 2 (FINAL ARBITER, KP sub-lord)  -> can OVERRIDE the capped
        #                                          net upward if H7 sub-lord
        #                                          match (strongest KP signal)
        # Tier 3 (ACTIVATION, Jaimini AK/AmK)  -> additive only
        # Tier 4 (TRIGGER, transit + Shadbala) -> additive only
        # ═══════════════════════════════════════════════════════════════

        arbitration_ledger: List[Dict[str, Any]] = []

        # ── Tier 0: foundational D1 lordship evidence ──────────────────
        base_evidence: List[str] = []
        base_net = 0.0

        if ad_lord in (h2_lord, h7_lord, h11_lord):
            # Audit fix: this fires when ad_lord matches ANY ONE of
            # H2/H7/H11 (not necessarily all three) but previously always
            # said "rules H2/H7/H11", implying triple lordship even when
            # only one house matched. Report the specific house(s) this
            # planet actually rules among the wealth/gains triad.
            ruled = [h for h, lord in (("H2", h2_lord), ("H7", h7_lord), ("H11", h11_lord)) if lord == ad_lord]
            weight = 12 * _dig_factor(ad_lord, dignities)
            base_net += weight
            base_evidence.append(f"AD lord {ad_lord} rules {'/'.join(ruled)} (dignity-weighted +{weight:.1f})")

        if ad_lord == h7_lord and _ph(ad_lord) in _DUSTHANA:
            dig = _dig_name(ad_lord, dignities)
            if dig in _STRONG_DIGNITY:
                base_net += 3
                base_evidence.append(f"AD lord {ad_lord} (H7 lord) own/exalted despite dusthana placement -> resilience, not risk")
            else:
                base_net -= 10
                base_evidence.append(f"AD lord {ad_lord} (H7 lord) weak in dusthana -> partnership/contract risk")

        if ad_lord in (h6_lord, h8_lord, h12_lord):
            dig = _dig_name(ad_lord, dignities)
            if dig in _STRONG_DIGNITY:
                base_net += 2
                base_evidence.append(f"AD lord {ad_lord} rules H6/H8/H12 but is own/exalted -> muted risk")
            else:
                base_net -= 10
                base_evidence.append(f"AD lord {ad_lord} rules H6/H8/H12 -> loss/liability exposure window")

        if ad_lord == h9_lord and _dig_name(ad_lord, dignities) != "DEBILITATED":
            base_net += 6
            base_evidence.append(f"AD lord {ad_lord} rules H9 (undebilitated) -> fortune-supported window")

        if ad_lord in (h2_lord, h11_lord) and ad_lord == "Jupiter":
            base_net += 5
            base_evidence.append("Jupiter AD tied to H2/H11 -> capital/expansion window")

        if md_lord in (h2_lord, h7_lord, h11_lord) and ad_lord in (h2_lord, h7_lord, h11_lord):
            base_net += 4
            base_evidence.append(f"MD lord {md_lord} and AD lord {ad_lord} both support H2/H7/H11 -> corroborated")
        elif md_lord in (h6_lord, h8_lord, h12_lord) and ad_lord in (h6_lord, h8_lord, h12_lord):
            base_net -= 4
            base_evidence.append(f"MD lord {md_lord} and AD lord {ad_lord} both tied to H6/H8/H12 -> corroborated risk")

        evidence: List[str] = list(base_evidence)
        arbitration_ledger.append({"tier": "0_D1_FOUNDATIONAL", "net_before": 0.0, "net_after": round(base_net, 2), "action": "BASE"})
        net = base_net

        # ── Tier 1: D9/D10 confirm/deny -- caps or floors, doesn't just add ──
        d9 = getattr(payload, "d9_planet_dignities", {}) or {}
        d10 = getattr(payload, "d10_planet_dignities", {}) or {}
        d9_dig = str(d9.get(ad_lord, "") or "").upper()
        d10_dig = str(d10.get(ad_lord, "") or "").upper()
        pre_tier1_net = net

        if d9_dig == "DEBILITATED" and d10_dig == "DEBILITATED":
            capped = min(net, -8.0)
            if capped != net:
                evidence.append(f"D9+D10: AD lord {ad_lord} debilitated in BOTH Navamsha and Dashamsha -> denies fructification, overriding D1 promise")
            net = capped
            arbitration_ledger.append({"tier": "1_D9_D10_CONFIRM_DENY", "net_before": round(pre_tier1_net, 2), "net_after": round(net, 2), "action": "DENY_OVERRIDE (both debilitated)"})
        elif d9_dig == "DEBILITATED" or d10_dig == "DEBILITATED":
            capped = min(net, 5.0)
            if capped != net:
                which = "D9 (Navamsha)" if d9_dig == "DEBILITATED" else "D10 (Dashamsha)"
                evidence.append(f"{which}: AD lord {ad_lord} debilitated -> caps window below STRONG_FAVORABLE regardless of D1 strength")
            net = capped
            arbitration_ledger.append({"tier": "1_D9_D10_CONFIRM_DENY", "net_before": round(pre_tier1_net, 2), "net_after": round(net, 2), "action": "SOFT_CAP (one debilitated)"})
        elif d9_dig in _STRONG_DIGNITY and d10_dig in _STRONG_DIGNITY:
            net += 8
            evidence.append(f"D9+D10: AD lord {ad_lord} strong in BOTH Navamsha and Dashamsha -> confirms D1 promise fructifies")
            arbitration_ledger.append({"tier": "1_D9_D10_CONFIRM_DENY", "net_before": round(pre_tier1_net, 2), "net_after": round(net, 2), "action": "CONFIRM_BONUS (both strong)"})
        else:
            d9d10_net, d9d10_notes = _d9_d10_corroboration(ad_lord, payload)
            net += d9d10_net
            evidence.extend(d9d10_notes)
            if d9d10_net:
                arbitration_ledger.append({"tier": "1_D9_D10_CONFIRM_DENY", "net_before": round(pre_tier1_net, 2), "net_after": round(net, 2), "action": "ADDITIVE (mixed/neutral dignity)"})

        # ── Tier 2: KP sub-lord as final arbiter for WHETHER H7 activates,
        # NOT for whether that activation is favorable -- the sub-lord's own
        # house-signification set (2/7/10/11 vs 6/8/12) decides the
        # direction. Being the H7 cusp sub-lord means this planet's period
        # brings H7 (partnership/venture) EVENTS; a sub-lord whose own
        # significations skew toward H6/H8/H12 brings those events in a
        # dispute/rupture/loss direction, not a success direction. Treating
        # "is the sub-lord" alone as automatically favorable conflates
        # activation with favorability -- fixed here.
        kp_h7_cusp = kp_cusps.get("H7", {}) if isinstance(kp_cusps.get("H7", {}), dict) else {}
        kp_h7_sublord = kp_h7_cusp.get("sub_lord", "")
        pre_tier2_net = net

        if kp_h7_sublord and kp_h7_sublord in (md_lord, ad_lord) and d9_dig != "DEBILITATED" and _kp_chain_verified:
            bias, pos_houses, neg_houses = _kp_sublord_signification_bias(kp_h7_sublord, payload)

            if bias == "NEGATIVE":
                # H7 activates, but this sub-lord's own signification set
                # leans toward dispute/loss houses -- override DOWN, not up.
                capped = min(net, DECISION_POLICY.kp_negative_override_ceiling)
                if capped != net:
                    evidence.append(
                        f"KP FINAL ARBITER (caution): {kp_h7_sublord} is H7 cusp sub-lord (activates partnership/"
                        f"venture events) but signifies H6/H8/H12 ({neg_houses}) more than H2/H7/H10/H11 ({pos_houses}) "
                        f"-> activation without favorable outcome, overrides toward risk"
                    )
                net = capped
                arbitration_ledger.append({"tier": "2_KP_FINAL_ARBITER", "net_before": round(pre_tier2_net, 2), "net_after": round(net, 2), "action": f"OVERRIDE_DOWN (H7 sub-lord signifies dispute houses {neg_houses})"})
            elif bias == "POSITIVE":
                # Strongest KP signal AND its own signification set favors
                # result-producing houses -- doctrine supports forcing at
                # least a FAVORABLE read even if D1/D9/D10 alone were tepid.
                if net < DECISION_POLICY.kp_positive_override_floor:
                    net = DECISION_POLICY.kp_positive_override_floor
                    evidence.append(f"KP FINAL ARBITER: {kp_h7_sublord} is H7 cusp sub-lord, signifies H2/H7/H10/H11 ({pos_houses}) -> overrides to at least FAVORABLE")
                    arbitration_ledger.append({"tier": "2_KP_FINAL_ARBITER", "net_before": round(pre_tier2_net, 2), "net_after": round(net, 2), "action": "OVERRIDE_UP (H7 sub-lord, positive signification bias)"})
                else:
                    evidence.append(f"KP FINAL ARBITER: {kp_h7_sublord} is H7 cusp sub-lord, signifies H2/H7/H10/H11 ({pos_houses}) -> confirms already-favorable window")
                    arbitration_ledger.append({"tier": "2_KP_FINAL_ARBITER", "net_before": round(pre_tier2_net, 2), "net_after": round(net, 2), "action": "CONFIRM (H7 sub-lord, positive signification bias)"})
            else:
                # NEUTRAL or UNKNOWN signification bias (no kp_significators
                # data for this planet, or an even split) -- sub-lord match
                # is still evidence of H7 activation, but NOT strong enough
                # on its own to override the net toward either pole without
                # knowing which direction that activation runs. Additive
                # only, same weight as a weaker cusp match.
                weight = 6.0
                net += weight
                evidence.append(f"KP: {kp_h7_sublord} is H7 cusp sub-lord (activates H7 events) but signification bias is {bias} -- not overriding, treated as additive-only (+{weight})")
                arbitration_ledger.append({"tier": "2_KP_FINAL_ARBITER", "net_before": round(pre_tier2_net, 2), "net_after": round(net, 2), "action": f"ADDITIVE_ONLY (signification bias {bias}, cannot safely override)"})
        elif _kp_chain_verified:
            # v-audit fix (item 5, follow-on): same unverified-chain gate as
            # the H7 sub-lord branch above -- this weaker, additive-only KP
            # credit still reads the same unverified kp_cusps data.
            kp_score = _kp_business_cusp_score(md_lord, ad_lord, kp_cusps)
            if kp_score > 0:
                weight = round(8 * kp_score, 2)
                net += weight
                evidence.append(f"KP: AD/MD lord rules business-cusp (H7/H11/H2/H10) sub/star/sign-lord, score={kp_score:.2f} (+{weight})")
                arbitration_ledger.append({"tier": "2_KP_FINAL_ARBITER", "net_before": round(pre_tier2_net, 2), "net_after": round(net, 2), "action": "ADDITIVE (weaker cusp match, not H7 sub-lord)"})

        # ── Tier 3: Jaimini activation -- additive/supportive only ──────
        jaimini_score, jaimini_label = _jaimini_business_score(md_lord, ad_lord, payload)
        if jaimini_score > 0:
            weight = round(8 * jaimini_score, 2)
            net += weight
            evidence.append(f"Jaimini (activation): {jaimini_label or 'karaka period active'} (score={jaimini_score:.2f}, +{weight})")

        # ── Tier 3B: Chara Dasha overlap corroboration -- additive/
        # supportive only, NEVER an override (see comment above
        # `_chara_calendar`'s computation for why). Finds whichever Chara
        # Dasha antardasha (falling back to mahadasha-level if no
        # antardasha data) overlaps this Vimshottari window's date range
        # the most, and reads that overlapping sign's own lord's dignity
        # as a small additive corroboration/caution -- the same "strong
        # dignity -> small bonus, debilitated -> small penalty" pattern
        # already used for other additive tiers in this function, just
        # sourced from a second, independent (sign-based, not nakshatra-
        # based) period system instead of D9/D10/Jaimini/transit.
        if _chara_calendar:
            chara_net, chara_notes = _chara_dasha_window_corroboration(
                _chara_calendar, start_date, end_date, house_lords, dignities,
            )
            net += chara_net
            evidence.extend(chara_notes)

        # ── Tier 4: transit + Shadbala trigger -- additive/supportive only ──
        shadbala_net, shadbala_notes = _shadbala_corroboration(ad_lord, payload)
        net += shadbala_net
        evidence.extend(f"(trigger) {n}" for n in shadbala_notes)

        transit_net, transit_notes, transit_status = _transit_corroboration(start_date, end_date, payload, today)
        net += transit_net
        evidence.extend(f"(trigger) {n}" for n in transit_notes)
        transit_statuses.append(transit_status)

        if not evidence:
            continue

        window = {
            "md_lord": md_lord,
            "ad_lord": ad_lord,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "net_score": round(net, 2),
            "label": _label_for_net(net),
            "evidence": evidence,
            "arbitration_ledger": arbitration_ledger,
            "transit_status": transit_status,
            # Backward-compatible alias: single-element list carrying the
            # dominant label, so older report code reading w["tags"] still works.
            "tags": [_label_for_net(net)],
            # v-audit fix (typed rule IDs -- structured dasha-lordship
            # coordinates, see _houses_ruled_by()'s comment above): the
            # houses each dasha lord structurally rules, computed directly
            # from house_lords, not parsed from `evidence` prose. Purely
            # additive/informational in this pass -- see the comment above
            # _houses_ruled_by for why _dasha_vote() itself is not yet
            # switched to consume these.
            "ad_lord_ruled_houses": _houses_ruled_by(ad_lord),
            "md_lord_ruled_houses": _houses_ruled_by(md_lord),
            # v46 audit fix (item 6, "timing-window granularity" --
            # user-directed): reuses the exact event-house mapping already
            # established for kp.py::_kp_10th_cusp_job_vs_business's
            # event_type_signals (v41), applied here structurally (from
            # md_lord/ad_lord house-rulership, not KP-cusp-gated) so it's
            # available on every window regardless of KP chain-verification
            # status. This is a COARSE structural overlay, not a
            # re-derivation of net_score/label per event -- it flags which
            # specific business events (starting, investing, partnering,
            # expanding, borrowing, exiting) this window's dasha lords
            # structurally touch, alongside the existing single general
            # favorable/unfavorable label, not instead of it.
            "event_type_signals": _window_event_type_signals(set(_houses_ruled_by(ad_lord)) | set(_houses_ruled_by(md_lord))),
            # v-audit fix (bounded-limitation follow-up, user-directed:
            # "tackle all bounded limitations" -- "event timing provides
            # coarse Boolean signals, not separate per-event scores"):
            # event_type_signals above only says WHICH events this window
            # touches, not whether that touch is favorable or unfavorable.
            # event_type_scores adds a real per-event signed score (see
            # _window_event_type_scores docstring for the exact rule),
            # additive to, not a replacement for, event_type_signals --
            # a caller that only wants the coarse boolean overlay is
            # unaffected; a caller that wants direction per event now has it.
            "event_type_scores": _window_event_type_scores(
                ad_lord, md_lord, set(_houses_ruled_by(ad_lord)), set(_houses_ruled_by(md_lord)), dignities,
            ),
        }

        # Additive PD (Pratyantardasha) expansion -- see _business_pd_subwindows
        # above. Never allowed to crash window scoring: any failure degrades
        # to pd_subwindows=[] with a status the caller/report can surface,
        # and the existing AD-only keys above are completely unaffected.
        pd_subwindows, pd_status = _business_pd_subwindows(window, payload)
        window["pd_subwindows"] = pd_subwindows
        window["pd_status"] = pd_status
        pd_statuses.append(pd_status)

        windows.append(window)

    # Aggregate per-window transit status into one summary the caller can
    # use for method_status. Priority: any real failure wins (so a single
    # failed window can't be masked by others succeeding), then APPLIED if
    # at least one window had scorable flags, then the weakest non-failure
    # status found.
    if any(s == _TRANSIT_STATUS_COMPUTATION_FAILED for s in transit_statuses):
        transit_summary = _TRANSIT_STATUS_COMPUTATION_FAILED
    elif any(s == _TRANSIT_STATUS_IMPORT_FAILED for s in transit_statuses):
        transit_summary = _TRANSIT_STATUS_IMPORT_FAILED
    elif any(s == _TRANSIT_STATUS_APPLIED for s in transit_statuses):
        transit_summary = _TRANSIT_STATUS_APPLIED
    elif any(s == _TRANSIT_STATUS_MISSING_DATA for s in transit_statuses):
        transit_summary = _TRANSIT_STATUS_MISSING_DATA
    elif transit_statuses:
        transit_summary = _TRANSIT_STATUS_NO_FLAGS
    else:
        transit_summary = "NOT_REQUESTED"  # no windows were scored at all
    status["transit_status_summary"] = transit_summary

    # Aggregate PD-expansion status the same way transit status is
    # aggregated above: any real failure wins, then OK if at least one
    # window's PD expansion succeeded, then the weakest degradation status
    # found. Used by _compute_method_status()'s timing_precision disclosure
    # to decide whether to claim PD-level precision or fall back to the
    # original AD-only disclosure.
    if any(s == _PD_STATUS_COMPUTATION_FAILED for s in pd_statuses):
        pd_summary = _PD_STATUS_COMPUTATION_FAILED
    elif any(s == _PD_STATUS_IMPORT_FAILED for s in pd_statuses):
        pd_summary = _PD_STATUS_IMPORT_FAILED
    elif any(s == _PD_STATUS_OK for s in pd_statuses):
        pd_summary = _PD_STATUS_OK
    elif any(s == _PD_STATUS_NO_LORDS for s in pd_statuses):
        pd_summary = _PD_STATUS_NO_LORDS
    elif pd_statuses:
        pd_summary = _PD_STATUS_NO_SUBPERIODS
    else:
        pd_summary = "NOT_REQUESTED"  # no windows were scored at all
    status["pd_status_summary"] = pd_summary
    status["kp_weighting_policy"] = KP_WEIGHTING_POLICY

    return windows, status

def _business_ad_windows(
    payload: Any,
    years_ahead: int = 15,
    as_of_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper around _compute_windows_and_status()
    returning just the windows list, for callers/tests that only need the
    windows and not the calendar-computation status."""
    windows, _status = _compute_windows_and_status(payload, years_ahead=years_ahead, as_of_date=as_of_date)
    return windows

# ─────────────────────────────────────────────────────────────────────────────────
# Pratyantardasha (PD, 3rd-level dasha) expansion
#
# Reuses Job_Career.timeline._expand_pratyantardashas -- the same
# cross-package reuse pattern already established by this file's use of
# Job_Career.timeline._dasha_calendar for the MD/AD calendar above. That
# function independently expands one AD span into its 9 constituent PD
# sub-periods via the standard Vimshottari proportional-fraction method; it
# needs only (md_lord, ad_lord, ad_start, ad_end) -- not the full calendar --
# so it can be called per-window after the AD loop above without
# recomputing anything upstream.
#
# PD-LEVEL SCORING CHOICE: this file's AD-level scoring
# (_compute_windows_and_status Tier 0) is fundamentally lord-house-
# significance based -- does the AD lord rule H2/H6/H7/H8/H9/H11/H12, and
# with what dignity. That same test trivially extends to the PD lord: the
# classical technique of "a dasha lord's own house-lordship refines the
# promise of the period it falls inside" doesn't stop at the 2nd level. So
# PD scoring below re-runs a SCALED-DOWN version of the exact same
# house-lordship+dignity test used for the AD lord (not Job_Career's
# separate 0-1 pd_score formula, which blends KP-significator/D10-occupancy/
# eff_strength/trigger-window signals tuned for career events -- a
# different domain with different weights). Using the SAME test as the
# parent AD keeps the PD tier label an intelligible refinement of the AD's
# own label instead of an incommensurable second scoring system, and it
# means the household-lordship data this file already has on hand
# (house_lords, dignities) is sufficient -- no new payload fields needed.
_PD_STATUS_OK = "OK"
_PD_STATUS_NO_LORDS = "NO_HOUSE_LORDS"          # payload has no house_lords to score PD lord against
_PD_STATUS_IMPORT_FAILED = "IMPORT_FAILED"      # Job_Career.timeline unavailable
_PD_STATUS_COMPUTATION_FAILED = "COMPUTATION_FAILED"  # ran and raised
_PD_STATUS_NO_SUBPERIODS = "NO_SUBPERIODS"      # ran fine, expansion returned nothing (degenerate/zero-length AD span)


def _pd_lord_house_delta(pd_lord: str, house_lords: Mapping[str, str], dignities: Mapping[str, str]) -> Tuple[float, List[str]]:
    """Scaled-down replay of the AD-level Tier-0 house-lordship test (see
    _compute_windows_and_status above), applied to a single PD lord instead
    of the AD lord. Weights are roughly 1/3 of the AD-level weights, since a
    PD lord's own lordship is a finer-grained refinement layered ON TOP of
    (not a replacement for) the parent AD's already-scored promise -- it
    should be able to nudge a window's tier up or down by one notch, not
    override the AD-level read entirely."""

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    h2, h6, h7, h8, h9, h11, h12 = _h(2), _h(6), _h(7), _h(8), _h(9), _h(11), _h(12)
    net = 0.0
    notes: List[str] = []

    if pd_lord in (h2, h7, h11):
        ruled = [h for h, lord in (("H2", h2), ("H7", h7), ("H11", h11)) if lord == pd_lord]
        weight = 4 * _dig_factor(pd_lord, dignities)
        net += weight
        notes.append(f"PD lord {pd_lord} rules {'/'.join(ruled)} (dignity-weighted +{weight:.1f})")

    if pd_lord in (h6, h8, h12):
        dig = _dig_name(pd_lord, dignities)
        if dig in _STRONG_DIGNITY:
            net += 1
            notes.append(f"PD lord {pd_lord} rules H6/H8/H12 but is own/exalted -> muted risk at PD level")
        else:
            net -= 3
            notes.append(f"PD lord {pd_lord} rules H6/H8/H12 -> localized loss/liability risk within this AD window")

    if pd_lord == h9 and _dig_name(pd_lord, dignities) != "DEBILITATED":
        net += 2
        notes.append(f"PD lord {pd_lord} rules H9 (undebilitated) -> fortune-supported sub-window")

    return net, notes


def _business_pd_subwindows(
    window: Mapping[str, Any],
    payload: Any,
) -> Tuple[List[Dict[str, Any]], str]:
    """Expand one already-scored AD window into its Pratyantardasha (PD)
    sub-windows via Job_Career.timeline._expand_pratyantardashas, and label
    each sub-window with a tier derived from (parent AD net_score + this
    PD lord's own house-lordship delta) using the same _label_for_net
    thresholds the AD level uses -- so a PD sub-window's label is legible
    as "the parent AD's read, refined" rather than a second unrelated scale.

    Returns (pd_subwindows, status). Never raises: any import/computation
    failure or missing data degrades to ([], <status>) so the caller can
    fall back to AD-only windows with the original disclosure intact."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    dignities = getattr(payload, "planet_dignities", {}) or {}
    if not house_lords:
        return [], _PD_STATUS_NO_LORDS

    try:
        from Job_Career.timeline import expand_pratyantardashas
        from Job_Career.timeline_inputs import parse_iso_date
    except Exception as exc:
        _record_diagnostic("timing._pd_subwindows", exc, note="Job_Career.timeline import failed")
        return [], _PD_STATUS_IMPORT_FAILED

    try:
        ad_start = parse_iso_date(str(window.get("start_date", ""))[:10])
        ad_end = parse_iso_date(str(window.get("end_date", ""))[:10])
        if not ad_start or not ad_end:
            return [], _PD_STATUS_NO_SUBPERIODS
        pd_periods = expand_pratyantardashas(
            window.get("md_lord", ""), window.get("ad_lord", ""), ad_start, ad_end
        )
    except Exception as exc:
        _record_diagnostic("timing._pd_subwindows", exc, note="Pratyantardasha expansion failed")
        return [], _PD_STATUS_COMPUTATION_FAILED

    if not pd_periods:
        return [], _PD_STATUS_NO_SUBPERIODS

    parent_net = float(window.get("net_score", 0.0))
    subwindows: List[Dict[str, Any]] = []
    for pd in pd_periods:
        pd_lord = pd.get("pd_lord", "")
        delta, notes = _pd_lord_house_delta(pd_lord, house_lords, dignities)
        sub_net = round(parent_net + delta, 2)
        citation = (
            (notes[0] if notes else f"PD lord {pd_lord} within AD {window.get('ad_lord', '')}: no additional house-lordship refinement, inherits parent AD read")
            + f" (Vimshottari Pratyantardasha, proportional-fraction expansion of AD {window.get('ad_lord', '')})"
        )
        subwindows.append({
            "pd_lord": pd_lord,
            "md_lord": window.get("md_lord", ""),
            "ad_lord": window.get("ad_lord", ""),
            "start_date": str(pd.get("start_date", "")),
            "end_date": str(pd.get("end_date", "")),
            "parent_net_score": round(parent_net, 2),
            "pd_delta": round(delta, 2),
            "net_score": sub_net,
            "label": _label_for_net(sub_net),
            "detail": citation,
        })

    return subwindows, _PD_STATUS_OK

_VENTURE_TYPE_TO_GATE_KEY = {
    "business": "business_score",
    "independent": "independent_score",
    "family_business": "family_biz_score",
}

def _timing_precision_disclosure(timing_status: Dict[str, Any]) -> Dict[str, Any]:
    """Conditional timing_precision disclosure.

    PD (Pratyantardasha) expansion (_business_pd_subwindows, added on top of
    _compute_windows_and_status's AD windows) means each AD window now
    additionally carries `pd_subwindows` -- so the original blanket claim
    that "Pratyantardasha ... are NOT computed here" is no longer accurate
    when PD expansion actually ran. Honesty-first per this codebase's
    convention (never overclaim precision that wasn't achieved): only
    soften the disclosure to PD-level when pd_status_summary confirms PD
    expansion succeeded for at least one window; any degradation
    (missing house_lords, Job_Career.timeline import failure, computation
    exception, or no windows scored at all) falls back to the ORIGINAL
    ANTARDASHA-level disclosure unchanged, so a reader never sees a claim
    of precision the run didn't actually achieve.

    Job_Career's own PD engine (_expand_pratyantardashas) is itself a
    proportional-fraction approximation, not an ephemeris-grade Sookshma/
    exact-event-date model -- that caveat is carried forward into the
    PD-level note below rather than implying false additional precision.
    """
    pd_summary = timing_status.get("pd_status_summary", "NOT_REQUESTED")

    if pd_summary == _PD_STATUS_OK:
        return {
            "status": "INFORMATIONAL",
            "level": "PRATYANTARDASHA",
            "note": (
                "Timed windows are Mahadasha/Antardasha (MD/AD) period-level, "
                "each additionally expanded into Pratyantardasha (PD, 3rd-level "
                "dasha) sub-windows via the same Vimshottari proportional-"
                "fraction method used by Job_Career.timeline -- see each "
                "window's `pd_subwindows`. This is still NOT muhurta-grade: "
                "Sookshma (4th-level), exact event-date transit contacts, "
                "dasha-lord/sub-lord mutual relationship at the Sookshma level, "
                "and separate launch/investment/partnership/exit event models "
                "are NOT computed here, and the PD expansion itself is a "
                "proportional-fraction approximation, not an ephemeris-grade "
                "computation. Use PD sub-windows to narrow to a season within "
                "an AD window, and investigate further at finer resolution "
                "before committing to a specific launch date."
            ),
        }

    # Degraded/unavailable: keep the ORIGINAL antardasha-only disclosure
    # verbatim, plus a machine-readable reason so callers can tell "PD was
    # never attempted here" apart from "PD was attempted and failed".
    return {
        "status": "INFORMATIONAL",
        "level": "ANTARDASHA",
        "pd_expansion_status": pd_summary,
        "note": (
            "Timed windows are Mahadasha/Antardasha (MD/AD) period-level, "
            "not muhurta-grade. Pratyantardasha (PD), Sookshma, exact "
            "event-date transit contacts, dasha-lord/sub-lord mutual "
            "relationship at the PD level, and separate launch/investment/"
            "partnership/exit event models are NOT computed here. Use "
            "these windows as strategic multi-month/multi-year periods to "
            "investigate further at finer resolution before committing to "
            "a specific launch date."
            f" (PD expansion status: {pd_summary} -- {TIMING_IS_ANTARDASHA_LEVEL_REASON.get(pd_summary, 'PD expansion not available for this run.')})"
        ),
    }


TIMING_IS_ANTARDASHA_LEVEL_REASON = {
    _PD_STATUS_NO_LORDS: "chart payload has no house_lords data to score PD lords against.",
    _PD_STATUS_IMPORT_FAILED: "Job_Career.timeline._expand_pratyantardashas was unavailable (import failed).",
    _PD_STATUS_COMPUTATION_FAILED: "PD expansion raised an exception for at least one window.",
    _PD_STATUS_NO_SUBPERIODS: "PD expansion ran but produced no sub-periods (degenerate AD span).",
    "NOT_REQUESTED": "no AD windows were scored in this run.",
}


def _chara_dasha_method_status(payload: Any) -> Dict[str, Any]:
    """v46 audit fix (item 3, user-directed: implement Standard Jaimini
    Chara Dasha): supersedes the previous hardcoded NOT_IMPLEMENTED entry.
    jyotish.astro.compute_chara_dasha_calendar() now exists (Standard
    Jaimini / Parashara-compatible convention, mahadasha-level only, no
    antardasha sub-period logic -- see that function's own docstring for
    the full disclosed rule and scope limits). This computes the sequence
    for whatever chart data is on `payload` and reports IMPLEMENTED only
    when it can actually be built; falls back to NOT_IMPLEMENTED-style
    NO_DATA when the chart lacks lagna_sign or enough planets_d1 lord-
    placement data to resolve any period (the same honest-degradation
    pattern used everywhere else in this file, e.g. transit_status_map)."""
    lagna_sign = getattr(payload, "lagna_sign", "") or getattr(payload, "d1_lagna", "") or ""
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    dob_str = getattr(payload, "dob", "") or ""
    try:
        from jyotish.astro import compute_chara_dasha_calendar
        from Job_Career.timeline_inputs import parse_iso_date
        dob = parse_iso_date(dob_str)
        calendar = compute_chara_dasha_calendar(lagna_sign, planets_d1, dob) if lagna_sign and planets_d1 and dob else []
    except Exception as exc:
        _record_diagnostic("timing._chara_dasha_method_status", exc, note="Chara status calendar computation failed")
        calendar = []
    if not calendar:
        return {
            "status": "NO_DATA",
            "data_available": False,
            "static_natal_use": "NOT_APPLICABLE",
            "timing_window_activation": "NO_DATA",
            "note": (
                "Chara Dasha (Standard Jaimini convention) is implemented "
                "(jyotish.astro.compute_chara_dasha_calendar), but this chart's payload "
                "lacks a resolvable lagna_sign and/or enough planets_d1 sign-lord placement "
                "data to compute it -- reported as NO_DATA for this specific chart, not as "
                "an unimplemented method."
            ),
        }
    return {
        "status": "IMPLEMENTED_MD_AD_ADDITIVE_CORROBORATION",
        "data_available": True,
        "static_natal_use": "NOT_APPLICABLE",
        "timing_window_activation": "WIRED_ADDITIVE_ONLY_INTO_VIMSHOTTARI_MD_AD_WINDOWS",
        "sequence": calendar,
        "note": (
            "Chara Dasha computed per the Standard Jaimini (Parashara-compatible) "
            "convention, anchored to the native's DOB. Mahadasha and Antardasha periods "
            "are computed and the greatest-overlap Chara period is wired into each "
            "Vimshottari MD/AD window as additive-only corroboration (small +/-3 cap); "
            "it cannot override or flip the base window direction. Alternative Jaimini "
            "school conventions remain outside this rule pack."
        ),
    }


def _compute_method_status(
    payload: Any,
    timed_windows: List[Dict[str, Any]],
    timing_status: Dict[str, Any],
    sbc_status: Dict[str, Any],
    significators: Optional[Dict[str, Any]] = None,
    mode_gate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-method status, reported along THREE separate dimensions instead
    of one collapsed "status" field -- audit finding (reviewer-caught
    provenance/reporting defect): the previous single-status model only
    ever searched TIMED-WINDOW evidence for a marker string (e.g. "D10" in
    window evidence text) to decide APPLIED vs PRESENT_NOT_TRIGGERED. That
    made D10 report PRESENT_NOT_TRIGGERED even when D10 evidence had
    materially driven the static significator ledger AND the mode gate
    (D10-native house-graph findings, D10-Lagna precedence, D10 dignity
    corroboration) -- D10 simply never happened to also fire a DIFFERENT
    D10-dignity rule inside a timed window on that particular chart. That
    is not "not triggered"; it is "triggered statically, not (also) in a
    timed window", a materially different and less alarming statement.

    Each method now reports:
      - "data_available": bool -- is the relevant payload field present.
      - "static_natal_use": APPLIED / NOT_APPLICABLE / NO_DATA -- did this
        method contribute evidence to score_business_significators() (the
        static natal ledger) or compute_business_mode_gate() (the static
        viability gate)? NOT_APPLICABLE means this method is architecturally
        scoped to timing only (e.g. Shadbala, dynamic transit) -- that is a
        design boundary, not a defect, and is now stated as such instead of
        silently reading as "not triggered".
      - "timing_window_activation": APPLIED / PRESENT_NOT_TRIGGERED /
        NO_DATA / FAILED / NOT_REQUESTED -- did this method fire inside at
        least one timed AD window.
      - "status": a single backward-compatible summary field (existing
        callers/tests read this key), now computed as APPLIED if EITHER
        static_natal_use OR timing_window_activation is APPLIED, so a
        method used statically is never misreported as unused.
    """
    def _fired_in_windows(marker: str) -> bool:
        return any(marker in e for w in timed_windows for e in w.get("evidence", []))

    def _fired_statically(marker: str) -> bool:
        if significators:
            if any(marker in e.get("note", "") for e in significators.get("evidence", [])):
                return True
        if mode_gate:
            all_signals = (
                [s for signals in mode_gate.get("positive_signals", {}).values() for s in signals]
                + [s for signals in mode_gate.get("negative_signals", {}).values() for s in signals]
            )
            if any(marker in s for s in all_signals):
                return True
        return False

    d9 = getattr(payload, "d9_planet_dignities", {}) or {}
    d10_occ = getattr(payload, "d10_house_occupancy", {}) or {}
    kp_cusps = getattr(payload, "kp_cusps", {}) or {}
    jaimini = getattr(payload, "kn_rao_jaimini", {}) or getattr(payload, "atmakaraka", "")
    eff_strengths = getattr(payload, "eff_strengths", {}) or {}

    def _method_entry(
        data: Any, static_marker: Optional[str], window_marker: str,
        static_scope: str = "APPLICABLE",
    ) -> Dict[str, Any]:
        data_available = bool(data)
        if static_scope == "NOT_APPLICABLE":
            static_use = "NOT_APPLICABLE"
        elif not data_available:
            static_use = "NO_DATA"
        elif static_marker and _fired_statically(static_marker):
            static_use = "APPLIED"
        else:
            # data is available but either there's no inline substring
            # marker to check (caller determines static use separately,
            # e.g. Jaimini below) or the marker didn't fire -- either way
            # this is "present but not (yet) confirmed used statically",
            # not "no data".
            static_use = "PRESENT_NOT_TRIGGERED"

        if not data_available:
            window_use = "NO_DATA"
        elif _fired_in_windows(window_marker):
            window_use = "APPLIED"
        else:
            window_use = "PRESENT_NOT_TRIGGERED"

        overall = "APPLIED" if ("APPLIED" in (static_use, window_use)) else (
            "MISSING_DATA" if not data_available else "PRESENT_NOT_TRIGGERED"
        )
        return {
            "status": overall,
            "data_available": data_available,
            "static_natal_use": static_use,
            "timing_window_activation": window_use,
        }

    transit_summary = timing_status.get("transit_status_summary", "NOT_REQUESTED")
    transit_status_map = {
        "COMPUTATION_FAILED": {"status": "FAILED", "error": "transit computation raised an exception mid-loop"},
        "IMPORT_FAILED": {"status": "FAILED", "error": "Job_Career.timeline import failed"},
        "APPLIED": {"status": "APPLIED"},
        "MISSING_DATA": {"status": "MISSING_DATA", "error": "no lagna_sign on payload"},
        # Audit fix: "NO_FLAGS" previously mapped to "PRESENT_NOT_TRIGGERED",
        # which reads as though the computation didn't run. It DID run
        # (mean-motion projection executed successfully) and simply found
        # no business-relevant flags in the scored windows -- a real,
        # positive computational result, not an absence.
        "NO_FLAGS": {"status": "COMPUTED_NO_FLAGS"},
        "NOT_REQUESTED": {"status": "NOT_REQUESTED"},
    }

    jaimini_static_applied = bool(jaimini) and (
        _fired_statically("Jaimini") or _fired_statically("rasi drishti") or _fired_statically("argala")
    )
    jaimini_entry = _method_entry(jaimini, None, "Jaimini")
    if jaimini_static_applied:
        jaimini_entry = {**jaimini_entry, "static_natal_use": "APPLIED", "status": "APPLIED"}

    return {
        "d9_navamsha": _method_entry(d9, "D9", "D9"),
        "d10_dashamsha": _method_entry(d10_occ, "D10", "D10"),
        "kp_significators": _method_entry(
            kp_cusps, "KP", "KP",
        ),
        "jaimini_karakas": jaimini_entry,
        # Audit fix (2026-07-29): static_scope was hardcoded NOT_APPLICABLE,
        # which is factually wrong -- Shadbala DOES feed the static natal
        # ledger via house_evidence.py::_shadbala_sav_strength_modifier
        # (an SAV-strength modifier applied to house-lord scoring, not just
        # a timing input). Scoped APPLICABLE so static_natal_use is derived
        # normally instead of being force-labeled as architecturally
        # timing-only.
        "shadbala": _method_entry(eff_strengths, "Shadbala", "Shadbala"),
        "chara_dasha": _chara_dasha_method_status(payload),
        "dynamic_transit": {
            **transit_status_map.get(transit_summary, {"status": transit_summary}),
            "data_available": transit_summary not in ("MISSING_DATA", "IMPORT_FAILED"),
            "static_natal_use": "NOT_APPLICABLE",
            "timing_window_activation": transit_status_map.get(transit_summary, {}).get("status", transit_summary),
            "precision_note": (
                "MEAN_MOTION_APPROXIMATE -- reuses Job_Career.timeline's mean-"
                "motion transit projection, not ephemeris-grade. Retrogression, "
                "station dates, exact ingress, and real longitude-based aspect "
                "contacts are NOT modeled. Treat flagged periods as broad "
                "approximate windows, not precise transit-contact dates."
            ),
        },
        "sbc_advisory": sbc_status,
        "timing_precision": _timing_precision_disclosure(timing_status),
    }

