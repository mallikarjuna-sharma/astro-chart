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
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from jyotish.d10_archetypes import (
    PLANET_ARCHETYPES,
    ARCHETYPE_NAMES,
    DIGNITY,
    scale_raw_support,
)
from jyotish.dignity import graha_yuddha as _jyotish_graha_yuddha
from jyotish.dignity import dignity_state as _jyotish_dignity_state
from jyotish.constants import _SIGN_LORD as _JYOTISH_SIGN_LORD
from jyotish.constants import _EXALT_SIGN as _EXALT_SIGN_HE


"""business_determination.house_evidence

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .constants import _DUSTHANA, _KT, _STRONG_DIGNITY, _UPACHAYA, _load_business_registry, _record_diagnostic, sav_lookup
from .policy import DECISION_POLICY


# v29 audit fix (Panchadha Maitri wiring): compute_dignity() in jyotish/
# astro.py -- the function that historically populated payload.planet_
# dignities for the whole D1 pipeline -- only ever returns EXALTED /
# DEBILITATED / MOOLATRIKONA / OWN / "" (blank, read downstream as
# NEUTRAL). It has NO concept of natural/temporal friendship (Panchadha
# Maitri), so e.g. Saturn sitting in Leo (Sun's own sign, and Saturn is a
# natural ENEMY of the Sun) was reported as bare "dignity=NEUTRAL" --
# indistinguishable from a planet in a truly neutral sign. jyotish/
# dignity.py's dignity_state() already implements the full five-fold
# (Great Friend/Friend/Neutral/Enemy/Great Enemy) classification plus
# Neecha Bhanga cancellation, but before this fix it was only wired into
# graha_yuddha() (imported above) and synastry.py -- not the main
# business-evidence pipeline below.
#
# compute_dignity()'s signature/behavior is a shared cross-domain contract
# (Job_Career, Stream_Determination, Field_Determination, Prashna_Charts,
# and every other divisional-chart dignity map in engine_io.py all depend
# on its exact current return values) and is deliberately left untouched.
# Instead, _rich_planet_dignities() below is a business_determination-local
# recomputation: it re-derives the richer friend/enemy-aware label from the
# same natal facts the payload already carries (payload.planets_d1 sign/
# degree data, payload.planet_house placements) by calling dignity_state()
# directly, and every dignity-label-producing call site in this module (via
# _dig_name/_dig_factor), plus significators.py and mode_gate.py, now builds
# its `dignities` dict from this function instead of the coarse
# payload.planet_dignities. "OWN_SIGN" is normalized to "OWN" here so every
# existing `== "OWN"` / `_STRONG_DIGNITY` string check elsewhere in this
# codebase keeps working unchanged; the five new tiers (GREAT_FRIEND/
# FRIEND/NEUTRAL/ENEMY/GREAT_ENEMY) and NEECHA_BHANGA are additive.
def _rich_planet_dignities(payload: Any) -> Dict[str, str]:
    """Business-determination-local Panchadha-Maitri-aware dignity map.

    Falls back to payload.planet_dignities (compute_dignity()'s coarse
    output) whenever payload.planets_d1 is unavailable (e.g. lightweight
    synthetic test payloads that set .planet_dignities directly without a
    full planets_d1/planet_house chart graph) so existing callers/tests
    that don't supply that raw chart data are unaffected.
    """
    planets_d1 = getattr(payload, "planets_d1", None) or {}
    coarse = getattr(payload, "planet_dignities", {}) or {}
    if not planets_d1:
        return dict(coarse)

    planet_house = getattr(payload, "planet_house", {}) or {}
    planet_signs = {
        p: str(info.get("sign", ""))
        for p, info in planets_d1.items()
        if isinstance(info, dict) and info.get("sign")
    }
    moon_sign = planet_signs.get("Moon", "")
    moon_house_num = _SIGN_ORDER_HE.index(moon_sign) + 1 if moon_sign in _SIGN_ORDER_HE else None

    result: Dict[str, str] = dict(coarse)
    for planet, sign in planet_signs.items():
        if planet == "Lagna":
            continue
        info = planets_d1.get(planet, {}) or {}
        degree = info.get("degree")

        dispositor = _JYOTISH_SIGN_LORD.get(sign, "")
        dispositor_house = planet_house.get(dispositor) if dispositor else None
        dispositor_sign = planet_signs.get(dispositor) if dispositor else None

        planet_house_from_moon = None
        if moon_house_num is not None and sign in _SIGN_ORDER_HE:
            pidx = _SIGN_ORDER_HE.index(sign)
            midx = moon_house_num - 1
            planet_house_from_moon = ((pidx - midx) % 12) + 1

        state = _jyotish_dignity_state(
            planet, sign, degree,
            dispositor_house=dispositor_house,
            dispositor_sign=dispositor_sign,
            planet_house_from_moon=planet_house_from_moon,
            planet_signs=planet_signs,
        )
        result[planet] = "OWN" if state == "OWN_SIGN" else state
    return result


_SIGN_ORDER_HE = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


# Ordering per dignity_state()'s own classical priority (EXALTED >
# MOOLATRIKONA > OWN > GREAT_FRIEND > FRIEND > NEUTRAL > ENEMY >
# GREAT_ENEMY > DEBILITATED, with NEECHA_BHANGA as cancelled-but-still-
# weaker-than-neutral debilitation). EXALTED/OWN/MOOLATRIKONA/DEBILITATED
# values are unchanged from the pre-existing table (many existing tests/
# thresholds assume those exact multipliers); the remaining tiers are new.
def _dig_factor(planet: str, dignities: Dict[str, str]) -> float:
    """0.55..1.40 multiplier. DEBILITATED is penalized, not just under-weighted,
    because a debilitated significator materially undermines the claim it's
    attached to (this was previously only applied inconsistently)."""
    return {
        "EXALTED": 1.40,
        "MOOLATRIKONA": 1.25,
        "OWN": 1.15,
        "GREAT_FRIEND": 1.08,
        "FRIEND": 1.03,
        "NEUTRAL": 1.00,
        "ENEMY": 0.90,
        "GREAT_ENEMY": 0.80,
        "NEECHA_BHANGA": 1.05,
        "DEBILITATED": 0.55,
    }.get(dignities.get(planet, ""), 1.0)

def _dig_name(planet: str, dignities: Dict[str, str]) -> str:
    return str(dignities.get(planet, "NEUTRAL") or "NEUTRAL").upper()

def _dig_disclosure(planet: str, dignities: Dict[str, str], payload: Any) -> str:
    """Dignity label for citation text, disclosing Parivartana Yoga exchanges.

    Scoring (payload.planet_dignities) shows "OWN" for BOTH planets in a
    mutual sign-exchange yoga, not their natal dignity -- per engine_io.py's
    documented Parivartana Dignity Upgrade, this is classically correct for
    strength purposes (an exchange grants own-sign-equivalent strength). But
    a bare "dignity=OWN" citation next to e.g. a Pisces placement for
    Mercury reads as a data error to an astrologer, since Mercury is
    actually debilitated there natally. Disclose the exchange + natal
    dignity inline so the citation is self-explanatory instead of silently
    correct-but-confusing (found via ground-truth audit against a real
    chart with an active Guru-Budha Parivartana).
    """
    dig = _dig_name(planet, dignities)
    if dig != "OWN":
        return dig
    true_dig = getattr(payload, "true_planet_dignities", {}) or {}
    natal = str(true_dig.get(planet, "") or "").upper() or "NEUTRAL"
    if natal == "OWN":
        return dig
    partner = None
    for yoga in getattr(payload, "detected_yogas", []) or []:
        if yoga.startswith("Parivartana_"):
            parts = yoga.split("_")
            if len(parts) == 3 and planet in (parts[1], parts[2]):
                partner = parts[2] if parts[1] == planet else parts[1]
                break
    if partner:
        return f"OWN (via Parivartana exchange with {partner}; natal dignity={natal})"
    return dig

def _retrograde_status(payload: Any, planet: str) -> Optional[bool]:
    """True/False if retrograde data is available for `planet`, else None
    (data unavailable -- callers MUST degrade to the pre-existing
    non-retrograde-aware behavior, not crash or silently assume direct).

    Reads payload.planet_retrograde (Dict[str, bool], set by engine_io.py
    at build time from planets_d1[p]["is_retrograde"]) first, falling back
    to payload.retrograde_planets (Set[str] of only the retrograde names,
    also set by engine_io.py) for older/partial payloads that carry one
    but not the other. Sun/Moon/Rahu/Ketu are never treated as retrograde
    for this purpose -- same exclusion the general engine's Shadbala layer
    uses (jyotish/astro.py's `is_retro = planet_retrograde.get(p, False)
    and p not in ("Sun","Moon","Rahu","Ketu")`), since Rahu/Ketu are
    always-retrograde nodes (the flag is not meaningful signification-wise)
    and Sun/Moon are never actually retrograde.
    """
    if planet in ("Sun", "Moon", "Rahu", "Ketu"):
        return False
    planet_retro = getattr(payload, "planet_retrograde", None)
    if isinstance(planet_retro, dict) and planet in planet_retro:
        return bool(planet_retro[planet])
    retro_set = getattr(payload, "retrograde_planets", None)
    if isinstance(retro_set, (set, frozenset, list, tuple)):
        return planet in retro_set
    return None


def _retro_adjusted_dig_factor(payload: Any, planet: str, dignities: Dict[str, str]) -> float:
    """_dig_factor(), nuanced for retrograde status when that data is
    available -- additive, backward compatible (falls back to the plain
    _dig_factor() when retrograde data is absent from payload).

    RETROGRADE-1 fix (gap audit): _planet_strength()/_planet_strength_fine()
    never checked retrograde status at all, despite the general engine's
    Shadbala layer (jyotish/astro.py's "Retrograde Asymmetry" dignity
    modifier, SHADBALA-FIX-1 in jyotish/constants.py) already encoding a
    specific, non-uniform classical stance on this exact question. To stay
    internally consistent with that established precedent rather than
    inventing a contradictory rule here, this mirrors it exactly using
    this module's own dignity-tier constants (see _dig_factor() above):

      - Retrograde + DEBILITATED -> treated as EXALTED-strength (1.40).
        This is "vakra neecha bhanga": classical Jyotish (per the same
        reasoning astro.py cites) holds that a debilitated planet
        retrograding back toward -- or having just left -- a stronger
        sign is not weak the way a direct debilitated planet is; its
        Cheshta Bala (motional strength) is at or near its maximum when
        retrograde, which is the single most robust, broadly-attested
        classical retrograde effect.
      - Retrograde + EXALTED -> only mildly dampened, to this module's
        OWN-tier value (1.15), NOT swapped down to DEBILITATED (0.55).
        astro.py's own comment explains why: a full symmetric swap is
        "not a broadly attested classical rule" -- retrograde exaltation
        carries a classical instability/caution note (results arrive with
        more revision/reconsideration), but the planet is still
        fundamentally strong, so a mild dampening (not an inversion) is
        the internally-consistent choice here too.
      - Any other dignity, or retrograde data unavailable -> unchanged
        (plain _dig_factor()), matching astro.py's own neutral branch and
        this module's graceful-degradation convention elsewhere (D2/D7/D9
        native-evidence helpers all no-op rather than penalize when their
        upstream data is missing).
    """
    base = _dig_factor(planet, dignities)
    is_retro = _retrograde_status(payload, planet)
    if not is_retro:  # False or None (unavailable) -> no adjustment
        return base
    dig_name = _dig_name(planet, dignities)
    if dig_name == "DEBILITATED":
        return 1.40  # vakra neecha bhanga -> EXALTED-equivalent (see docstring)
    if dig_name == "EXALTED":
        return 1.15  # retro caution: dampened, not inverted (see docstring)
    return base


def _graha_yuddha_loss_factor(payload: Any, planet: str) -> float:
    """Multiplier (<=1.0) applied on top of the dignity factor when
    `planet` is a Graha Yuddha (planetary war) LOSER -- 1.0 (no-op) in
    every other case: not a war participant at all (the normal case for
    almost every chart, since graha_yuddha() requires two of the five
    eligible planets -- Mars/Mercury/Jupiter/Venus/Saturn, Sun/Moon/Rahu/
    Ketu never participate -- within 1 degree of each other in the same
    sign), a war winner, or `payload.planet_longitudes` missing entirely
    (graceful degradation: no error, just no adjustment).

    GYUDDHA-1 fix (gap audit): _lagnesh_affliction_and_karaka_connection_
    evidence() already reused jyotish.dignity.graha_yuddha() to cite a
    war-losing LAGNESH, but that citation was never folded into the
    Lagnesh's actual _planet_strength()/_planet_strength_fine() score --
    and no other business-critical planet (2nd/6th/7th/10th/11th lord,
    or Mercury as the primary trade/commerce karaka) was checked for war
    at all. This closes both gaps: the factor computed here is consumed
    by _planet_strength()/_planet_strength_fine() for EVERY planet (not
    just Lagnesh), so a war-losing planet's strength genuinely drops in
    every downstream computation that reads planet strength (significators,
    sectors, contradictions, yogas, mode_gate) -- not just an isolated
    evidence citation.

    Severity scaling: graha_yuddha() itself only reports separation_
    degrees (0..1) for a war, not an independent "how badly defeated"
    magnitude -- so rather than inventing an unrelated severity metric,
    tighter separation (closer conjunction, the more classically decisive
    a war) is scaled to the more severe end of this module's existing
    ENEMY..GREAT_ENEMY dignity-tier band (0.90 at 1 degree separation,
    tapering linearly to 0.80 at an exact/0-degree conjunction), so the
    penalty stays inside the same tier scale already used for ordinary
    planetary-relationship dignity (_dig_factor()) rather than a
    freestanding flat number.
    """
    lon_map = getattr(payload, "planet_longitudes", None)
    if not lon_map:
        return 1.0  # no longitude data at all -> cannot check -> no-op
    try:
        yuddha = _jyotish_graha_yuddha(dict(lon_map))
    except Exception as exc:
        _record_diagnostic("house_evidence._graha_yuddha_strength_factor", exc)
        return 1.0  # graceful degradation -- never raise from a strength helper
    for war in yuddha.get("wars", []) or []:
        if war.get("loser") == planet:
            sep = war.get("separation_degrees", 1.0)
            try:
                sep = max(0.0, min(1.0, float(sep)))
            except (TypeError, ValueError):
                sep = 1.0
            return round(0.90 - (0.10 * (1.0 - sep)), 4)  # 0.90 (loose) .. 0.80 (tight)
    return 1.0


_COMBUST_ORB_HE = {"Moon": 12.0, "Mars": 17.0, "Mercury": 14.0, "Jupiter": 11.0, "Venus": 10.0, "Saturn": 15.0}
_COMBUST_ORB_RETRO_HE = {"Mercury": 12.0, "Venus": 8.0}
COMBUST_STRENGTH_PENALTY_HE = 0.85  # matches jyotish.dignity.COMBUST_STRENGTH_PENALTY

# Astrologer-reviewed refinement: classical texts do NOT treat combustion as
# a flat on/off penalty applied identically at 0.1 deg and at 13.9 deg
# separation from the Sun. Two widely-practiced distinctions were missing
# from the first pass and produced an over-correction on a real chart (an
# exalted Mercury only 5.1 deg from the Sun, well outside the tight "deep
# combustion" band most references use, was getting the SAME 0.85 penalty
# as a planet 0.1 deg from the Sun):
#
#   1. Depth-graduated severity. Most references distinguish "deep"/"asta"
#      combustion (within a few degrees, treated as a serious affliction)
#      from merely being inside the wider classical orb (treated as a much
#      milder dimming). This tapers the penalty linearly from full severity
#      at/inside the deep-combustion band to zero severity at the outer
#      orb edge, instead of a step function.
#   2. Dignity leniency. A planet that is EXALTED, in OWN sign, or in
#      MOOLATRIKONA is widely held (though not universally -- this is
#      explicitly one engineered reading among several classical opinions,
#      consistent with this engine's existing MATURITY_CAVEATS disclosure)
#      to resist combustion damage much better than a planet in a weak or
#      neutral sign. This halves the discount for such planets.
#
# The deep-combustion band is derived as a fraction of each planet's own
# classical orb (roughly matching the commonly-cited standalone "deep
# combustion" degrees -- Mercury ~4 deg, Venus ~4 deg, etc. -- without
# hardcoding a second parallel table) rather than an independently sourced
# figure, since this codebase has no verified independent citation for
# exact deep-combustion degrees per planet.
_DEEP_COMBUST_FRACTION_HE = 0.3
_DIGNITY_LENIENT_HE = {"EXALTED", "OWN", "MOOLATRIKONA"}


def _combustion_status(payload: Any, planet: str) -> Dict[str, Any]:
    """Checks whether `planet` is combust (too close to the Sun) using
    exact longitudes when the payload provides them (same
    payload.planet_longitudes field _graha_yuddha_loss_factor()/
    _jyotish_graha_yuddha() already read), classical BPHS orbs (Moon 12,
    Mars 17, Mercury 14 [12 if retrograde], Jupiter 11, Venus 10 [8 if
    retrograde], Saturn 15). Sun/Rahu/Ketu are never combust.

    Returns {"checked": bool, "combust": bool, "reason": str|None,
    "severity": float in [0,1]}. "severity" is 1.0 at exact conjunction,
    tapering to 0.0 at the orb edge with a flat 1.0 plateau inside the
    deep-combustion band (see _DEEP_COMBUST_FRACTION_HE) -- used by
    _combustion_strength_factor() to graduate the strength penalty instead
    of applying it as a step function.

    "checked" is False when longitude data is unavailable -- callers MUST
    treat that as "cannot determine", not "not combust" (this module's
    established graceful-degradation convention: an honest
    INSUFFICIENT_EVIDENCE-style skip beats a silently-wrong assumption).
    Falls back to payload.combust_planets (a pre-existing coarse flag
    already trusted by _lagnesh_affliction_and_karaka_connection_evidence())
    only when longitudes are absent, so this degrades gracefully across
    payloads of differing richness rather than going fully blind.
    """
    out: Dict[str, Any] = {"checked": False, "combust": False, "reason": None, "severity": 0.0}
    if planet in ("Sun", "Rahu", "Ketu"):
        return out
    if planet not in _COMBUST_ORB_HE:
        return out

    lon_map = getattr(payload, "planet_longitudes", None) or {}
    sun_lon = lon_map.get("Sun")
    planet_lon = lon_map.get(planet)
    if sun_lon is not None and planet_lon is not None:
        try:
            diff = abs(float(planet_lon) - float(sun_lon)) % 360.0
            diff = min(diff, 360.0 - diff)
        except (TypeError, ValueError):
            diff = None
        if diff is not None:
            is_retro = _retrograde_status(payload, planet)
            orb = _COMBUST_ORB_RETRO_HE.get(planet, _COMBUST_ORB_HE[planet]) if is_retro else _COMBUST_ORB_HE[planet]
            out["checked"] = True
            out["combust"] = diff <= orb
            if out["combust"]:
                deep_orb = orb * _DEEP_COMBUST_FRACTION_HE
                if diff <= deep_orb:
                    severity = 1.0
                    depth_label = "deep combustion"
                else:
                    severity = max(0.0, 1.0 - (diff - deep_orb) / (orb - deep_orb))
                    depth_label = "light combustion"
                out["severity"] = round(severity, 3)
                out["reason"] = f"separation from Sun={round(diff, 2)}° (orb={orb}°, {depth_label})"
            else:
                out["reason"] = f"separation from Sun={round(diff, 2)}° (orb={orb}°)"
            return out

    # No usable longitude data -- fall back to the coarse pre-existing
    # combust_planets flag (may itself be empty/absent on sparse payloads).
    # No depth information available from a boolean flag, so treat it as
    # full severity (the conservative, pre-refinement behavior) rather than
    # guessing a taper we cannot support with data.
    combust_planets = set(getattr(payload, "combust_planets", []) or [])
    if combust_planets:
        out["checked"] = True
        out["combust"] = planet in combust_planets
        out["severity"] = 1.0 if out["combust"] else 0.0
        out["reason"] = "from payload.combust_planets (exact longitude unavailable)"
    return out


def _combustion_strength_factor(payload: Any, planet: str) -> float:
    """Multiplier (<=1.0) for _planet_strength()/_planet_strength_fine():
    graduated by combustion depth (see _combustion_status's "severity"),
    halved further when the planet is EXALTED/OWN/MOOLATRIKONA (dignity
    leniency, an engineered reading -- see module comment above), 1.0 when
    not combust or when combustion cannot be checked (never penalize on
    missing data)."""
    status = _combustion_status(payload, planet)
    if not (status.get("checked") and status.get("combust")):
        return 1.0
    severity = status.get("severity", 1.0)
    max_discount = 1.0 - COMBUST_STRENGTH_PENALTY_HE  # 0.15
    dignities = _rich_planet_dignities(payload)
    if _dig_name(planet, dignities) in _DIGNITY_LENIENT_HE:
        severity *= 0.5
    return 1.0 - max_discount * severity


def _shadbala_sav_strength_modifier(payload: Any, planet: str) -> float:
    """Bounded secondary multiplier (0.85..1.15) blending Shadbala
    (payload.eff_strengths, the same field _shadbala_corroboration() in
    timing.py already reads for timing arbitration) and Ashtakavarga SAV
    bindus (payload.sav_points_houses via constants.sav_lookup(), the
    same shared helper significators.py's `_sav_h`/ashtakavarga_timing.py
    already use) for `planet`.

    This is deliberately a SECONDARY, bounded adjustment on top of the
    existing dignity/placement-based strength calculation, not a
    replacement -- its purpose is only to discriminate between two
    planets that happen to share the same dignity label (e.g. both
    NEUTRAL) but have materially different Shadbala/SAV support, which
    the base calculation cannot see at all. Missing data degrades
    gracefully: an unavailable component simply contributes no
    adjustment (1.0), rather than guessing.
    """
    modifier = 1.0

    eff = getattr(payload, "eff_strengths", {}) or {}
    ratio = eff.get(planet)
    if isinstance(ratio, (int, float)):
        # ratio 1.0 = meets classical minimum; scale linearly, capped at
        # +/-8% from this component alone (0.5..1.5 ratio -> -8%..+8%).
        delta = max(-0.08, min(0.08, (float(ratio) - 1.0) * 0.16))
        modifier += delta

    sav = getattr(payload, "sav_points_houses", None)
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_num = planet_house.get(planet)
    if sav and house_num:
        try:
            bindus = sav_lookup(sav, house_num)
            # 28 bindus = neutral baseline (see constants.sav_lookup());
            # capped at +/-8% from this component alone.
            delta = max(-0.08, min(0.08, (bindus - 28) / 28.0 * 0.16))
            modifier += delta
        except Exception as exc:
            _record_diagnostic("house_evidence._shadbala_sav_strength_modifier", exc)

    return round(max(0.85, min(1.15, modifier)), 4)


_NEECHA_KENDRA = frozenset({1, 4, 7, 10})


def _kendra_from(house_lords: Dict[Any, str], planet_house: Dict[str, int], base_house: Optional[int], target: str) -> Optional[bool]:
    """True/False if `target`'s house-position-from-`base_house` is a
    kendra (1/4/7/10 counted from base_house), None if the data needed
    (target's house, or base_house itself) is unavailable -- callers must
    skip the condition rather than guess, per the conservative-degradation
    convention used throughout this module (_retrograde_status, D9/D10
    native-evidence helpers, etc.)."""
    if base_house is None:
        return None
    th = planet_house.get(target)
    if not th:
        return None
    offset = ((th - base_house) % 12) + 1
    return offset in _NEECHA_KENDRA


def _simple_aspect(from_house: Optional[int], to_house: Optional[int], planet: str) -> bool:
    """Minimal graha-drishti (special aspect) check: every planet aspects
    the 7th house from itself; Mars additionally aspects 4th/8th, Jupiter
    5th/9th, Saturn 3rd/10th (the three classical special-aspect planets).
    Counts houses-from-itself, 1-indexed inclusive (matches this module's
    existing kendra-counting convention). Conjunction (from_house==to_house)
    is handled separately by callers, not treated as an aspect here."""
    if from_house is None or to_house is None:
        return False
    offset = ((to_house - from_house) % 12) + 1
    special = {"Mars": (4, 8), "Jupiter": (5, 9), "Saturn": (3, 10)}.get(planet, ())
    return offset == 7 or offset in special


def _neecha_bhanga_status(payload: Any, planet: str) -> Dict[str, Any]:
    """Checks whether `planet`'s DEBILITATED dignity is classically
    cancelled (Neecha Bhanga) under any of the commonly-cited conditions
    this payload's data can actually support. Returns
    {"cancelled": bool, "reason": str|None} -- conservative by design:
    any condition whose required data is missing from the payload
    (e.g. Moon's house, a dispositor's house) is simply skipped rather
    than guessed, so a chart with sparse data never gets a false
    cancellation. Reuses the same payload access patterns as
    _rich_planet_dignities()/_house_lord_strength() (house_lords,
    planet_house, planet_signs) rather than inventing new ones.

    Conditions checked (simple/common cases only, per spec):
      1. Dispositor of the debilitation sign is in a kendra from
         Lagna or from Moon.
      2. Lord of the planet's own exaltation sign is in a kendra from
         Lagna or from Moon.
      3. The debilitated planet is conjunct, or receives a graha-drishti
         aspect from, its own dispositor or its exaltation-sign lord.
      4. Mutual sign exchange (parivartana) between the debilitated
         planet's dispositor and another planet, read off
         payload.detected_yogas' "Parivartana_X_Y" entries (same field
         _dig_disclosure() already reads) -- the common/simple case only.
    """
    out: Dict[str, Any] = {"cancelled": False, "reason": None}
    dignities = _rich_planet_dignities(payload)
    if _dig_name(planet, dignities) != "DEBILITATED":
        return out

    planet_signs = getattr(payload, "planet_signs", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}

    sign = planet_signs.get(planet)
    dispositor = _JYOTISH_SIGN_LORD.get(sign) if sign else None
    exalt_sign = _EXALT_SIGN_HE.get(planet)
    exalt_lord = _JYOTISH_SIGN_LORD.get(exalt_sign) if exalt_sign else None

    moon_house = planet_house.get("Moon")

    # Condition 1: dispositor in kendra from Lagna (house 1) or Moon, AND
    # the dispositor itself is well-dignified there (EXALTED/OWN/
    # MOOLATRIKONA/GREAT_FRIEND). The dignity requirement matches the
    # stricter, pre-existing standard already used by
    # jyotish.dignity._neecha_bhanga_cancels() (which is wired into
    # _rich_planet_dignities() above via dignity_state()) -- a merely
    # kendra-placed-but-weak dispositor does not classically cancel a
    # debilitation, and this function must not disagree with the
    # authoritative source on the same underlying condition.
    if dispositor:
        dispositor_sign = planet_signs.get(dispositor)
        dispositor_dig = _dig_name(dispositor, dignities) if dispositor_sign else "NEUTRAL"
        dispositor_well_dignified = dispositor_dig in {"EXALTED", "OWN", "MOOLATRIKONA", "GREAT_FRIEND"}
        if dispositor_well_dignified:
            from_lagna = _kendra_from(house_lords, planet_house, 1, dispositor)
            from_moon = _kendra_from(house_lords, planet_house, moon_house, dispositor)
            if from_lagna or from_moon:
                out["cancelled"] = True
                out["reason"] = (f"dispositor of debilitation sign ({dispositor}, {dispositor_dig}) is in a kendra from "
                                  f"{'Lagna' if from_lagna else 'Moon'}")
                return out

    # Condition 2: exaltation-sign lord in kendra from Lagna or Moon, AND
    # itself well-dignified there. Guard against exalt_lord == planet
    # (Mercury is the one planet whose exaltation sign, Virgo, it also
    # owns -- so "the lord of Mercury's exaltation sign" is always Mercury
    # itself). Without this guard, a genuinely-debilitated Mercury sitting
    # in ANY kendra house (1/4/7/10) would always spuriously self-cancel
    # here, regardless of any other planet's placement -- the condition is
    # meant to test a DIFFERENT planet's strength corroborating the
    # debilitated one, not the debilitated planet's own placement.
    # Condition 3 below already carries this exact guard (`helper ==
    # planet: continue`); this closes the same gap in condition 2.
    #
    # Gap-hunt fix (astrological-validation-caught): this condition used
    # to cancel on kendra PLACEMENT alone, with no dignity requirement on
    # the exaltation-sign lord itself -- inconsistent with Condition 1
    # just above, which was deliberately tightened to require the
    # dispositor be well-dignified (EXALTED/OWN/MOOLATRIKONA/GREAT_FRIEND)
    # before it's allowed to cancel a debilitation, matching the stricter,
    # pre-existing standard elsewhere in this codebase
    # (jyotish.dignity._neecha_bhanga_cancels). A debilitated or
    # enemy-dignitied exaltation-lord merely occupying a kendra house
    # would previously cancel just as validly as a strong one -- the exact
    # over-cancellation risk Condition 1 was tightened to prevent, left
    # open here. Now requires the same well-dignified bar.
    if exalt_lord and exalt_lord != planet:
        exalt_lord_sign = planet_signs.get(exalt_lord)
        exalt_lord_dig = _dig_name(exalt_lord, dignities) if exalt_lord_sign else "NEUTRAL"
        exalt_lord_well_dignified = exalt_lord_dig in {"EXALTED", "OWN", "MOOLATRIKONA", "GREAT_FRIEND"}
        if exalt_lord_well_dignified:
            from_lagna = _kendra_from(house_lords, planet_house, 1, exalt_lord)
            from_moon = _kendra_from(house_lords, planet_house, moon_house, exalt_lord)
            if from_lagna or from_moon:
                out["cancelled"] = True
                out["reason"] = (f"lord of {planet}'s exaltation sign ({exalt_lord}, {exalt_lord_dig}) is in a kendra from "
                                  f"{'Lagna' if from_lagna else 'Moon'}")
                return out

    # Condition 3: conjunction with, or aspect from, dispositor/exalt lord,
    # AND that helper itself well-dignified.
    #
    # Gap-hunt fix (astrological-validation-caught, real-chart-surfaced):
    # this condition used to cancel on conjunction/aspect alone, with no
    # dignity requirement on the dispositor/exalt-lord doing the aspecting
    # -- the same gap Conditions 1 and 2 above were each tightened to
    # close (a weak or afflicted helper merely touching the debilitated
    # planet is not, by itself, a classical cancellation; the helper's own
    # strength is what lends the debilitated planet support). Closing this
    # third instance the same way: the aspecting/conjunct dispositor or
    # exaltation-sign lord must itself be well-dignified.
    planet_h = planet_house.get(planet)
    for helper, label in ((dispositor, "dispositor"), (exalt_lord, "exaltation-sign lord")):
        if not helper or helper == planet:
            continue
        helper_sign = planet_signs.get(helper)
        helper_dig = _dig_name(helper, dignities) if helper_sign else "NEUTRAL"
        if helper_dig not in {"EXALTED", "OWN", "MOOLATRIKONA", "GREAT_FRIEND"}:
            continue
        helper_h = planet_house.get(helper)
        if helper_h is None or planet_h is None:
            continue
        if helper_h == planet_h:
            out["cancelled"] = True
            out["reason"] = f"{helper} ({label}, {helper_dig}) is conjunct the debilitated planet"
            return out
        if _simple_aspect(helper_h, planet_h, helper):
            out["cancelled"] = True
            out["reason"] = f"{helper} ({label}, {helper_dig}) aspects the debilitated planet"
            return out

    # Condition 4: simple parivartana (mutual exchange) between the
    # dispositor and another planet whose own debilitation is also being
    # cancelled by the exchange itself (the exchange lifts both planets
    # to own-sign-equivalent strength, which classically cancels a
    # debilitation for either side of the exchange).
    if dispositor:
        yogas = getattr(payload, "detected_yogas", []) or []
        for yoga in yogas:
            if not isinstance(yoga, str) or not yoga.startswith("Parivartana_"):
                continue
            parts = yoga.split("_")
            if len(parts) == 3 and dispositor in (parts[1], parts[2]):
                partner = parts[2] if parts[1] == dispositor else parts[1]
                out["cancelled"] = True
                out["reason"] = f"dispositor ({dispositor}) is in mutual exchange (Parivartana) with {partner}"
                return out

    return out


def lagnesh_neecha_bhanga_adjudication(payload: Any) -> Dict[str, Any]:
    """Consolidated, report-facing Neecha Bhanga (debilitation-cancellation)
    adjudication for the Lagna lord (Lagnesh), reusing the existing, real
    _neecha_bhanga_status() check (already invoked internally by
    _lagnesh_affliction_and_karaka_connection_evidence() for the
    significator ledger) rather than re-deriving it -- this function's only
    job is to expose that already-computed result as an explicit,
    dedicated, top-level report field with real dispositor/reasoning
    citations, since prior report renders only ever surfaced it buried
    inside free-form significator evidence notes, never as its own status
    field a reader could inspect directly.

    Returns status=NOT_APPLICABLE when Lagnesh is not DEBILITATED at all
    (nothing to adjudicate); otherwise status=OK with the real cancelled/
    not-cancelled verdict, citing the actual dispositor and sign, and a
    scope-honest note distinguishing which KIND of agency a weakened (not
    cancelled) Lagnesh affects: classically, a debilitated Lagna lord most
    directly dampens PERSONAL financial risk-confidence and speculative/
    independent-venture initiative -- it does not, by itself, equally
    dampen intellectual or advisory capacity (teaching, consulting,
    institutional/professional roles), which draw more on the 2nd/5th/9th/
    10th houses and their own lords than on Lagna strength alone. This
    avoids the flat, overly-generalized "weakened entrepreneurial agency"
    framing for every use of this field."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    dignities = _rich_planet_dignities(payload)

    h1_lord = house_lords.get("1", house_lords.get(1, ""))
    if not h1_lord:
        return {"status": "NOT_AVAILABLE", "note": "house_lords data unavailable -- Lagnesh could not be identified."}

    dig1 = _dig_name(h1_lord, dignities)
    if dig1 != "DEBILITATED":
        return {
            "status": "NOT_APPLICABLE",
            "lagnesh": h1_lord,
            "dignity": dig1,
            "note": f"Lagnesh ({h1_lord}) is not debilitated (dignity={dig1}) -- Neecha Bhanga is not a relevant question for this chart.",
        }

    sign = planet_signs.get(h1_lord)
    dispositor = _JYOTISH_SIGN_LORD.get(sign) if sign else None
    nb = _neecha_bhanga_status(payload, h1_lord)

    if nb.get("cancelled"):
        note = (
            f"Lagnesh ({h1_lord}) is debilitated in {sign or 'unknown sign'} (dispositor: {dispositor or 'unknown'}), "
            f"but classical Neecha Bhanga (debilitation-cancellation) applies: {nb.get('reason')}. "
            "The debilitation is classically read as cancelled -- entrepreneurial/independent agency is not "
            "structurally weakened on this specific ground."
        )
    else:
        note = (
            f"Lagnesh ({h1_lord}) is debilitated in {sign or 'unknown sign'} (dispositor: {dispositor or 'unknown'}). "
            "No valid classical Neecha Bhanga condition was found on this chart (checked: dispositor-in-kendra, "
            "exaltation-lord-in-kendra, conjunction/aspect from a well-dignified dispositor or exaltation lord, and "
            "dispositor-in-Parivartana) -- the debilitation stands uncancelled. Nuance: this primarily affects "
            "PERSONAL financial risk-confidence and speculative/independent-venture initiative (the Lagna's own "
            "domain); it does not by itself equally weaken intellectual or advisory capacity (teaching, consulting, "
            "institutional/professional roles), which depend more on the relevant house lords (2nd/5th/9th/10th) "
            "than on Lagna strength alone -- read as 'weakened venture risk-confidence', not a flat 'weakened "
            "entrepreneurial agency' across every context."
        )

    return {
        "status": "OK",
        "lagnesh": h1_lord,
        "dignity": dig1,
        "sign": sign,
        "dispositor": dispositor,
        "cancelled": bool(nb.get("cancelled")),
        "cancellation_reason": nb.get("reason"),
        "note": note,
    }


def _house_lord_strength(payload: Any, house_num: int) -> float:
    """0..1 strength for the lord of a given D1 house: placement bucket
    (kendra/trikona > upachaya > dusthana) scaled by dignity, with a
    Viparita-Raja-Yoga-style exception (own/exalted dusthana lord in a
    dusthana is NOT penalized down to the dusthana floor)."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    lord = house_lords.get(str(house_num), house_lords.get(house_num, ""))
    if not lord:
        return 0.35  # unknown -> neutral, not zero (don't punish missing data)

    placed_house = planet_house.get(lord, 0)
    dig = _dig_name(lord, dignities)

    if placed_house in _KT:
        base = 1.0
    elif placed_house in _UPACHAYA:
        base = 0.65
    elif placed_house in _DUSTHANA:
        # VRY-style exception: an own/exalted lord placed in a dusthana is
        # not weak just because the house label is inauspicious.
        base = 0.60 if dig in _STRONG_DIGNITY else 0.25
    else:
        base = 0.45

    return round(min(1.0, base * _dig_factor(lord, dignities) * _shadbala_sav_strength_modifier(payload, lord)), 4)


def capital_strategy_lean_for_payload(
    payload: Any,
    bootstrap_capacity: Optional[float] = None,
    external_capital_raising_capacity: Optional[float] = None,
    debt_management_score: Optional[float] = None,
    capital_readiness_status: Optional[str] = None,
) -> str:
    """Standalone bootstrap-vs-external-capital lean label, computed from
    D1 house-lord strength alone (2nd house = self-funding capacity; 11th
    house weighted 0.7 + 8th house weighted 0.3 = external-capital-raising
    capacity), so callers that need just this one label don't have to run
    the full significators/named-promise-fields pipeline first.

    Lives here (not in scoring.py, where the original bootstrap_capacity/
    capital_strategy_lean computation was first introduced) specifically so
    business_determination/sectors.py's capital-feasibility check (v-audit
    fix, business realism item 33: "sector capital intensity is not
    formally matched to capital capacity") can call it directly during
    sector ranking -- sectors.py already imports house_evidence.py, but
    importing scoring.py from sectors.py would be circular (scoring.py
    itself imports sectors.py).

    If the caller already has bootstrap_capacity/external_capital_raising_
    capacity computed (as scoring.py's _compute_named_promise_fields does),
    pass them in directly so the two call sites can never silently diverge
    on the underlying math -- otherwise both are derived here from
    _house_lord_strength() using the exact same 0.7/0.3 weighting and
    0..100 clamp scoring.py's original computation used.

    Threshold convention (>=3 clearly favors bootstrap, <=-2 clearly favors
    external, otherwise BALANCED) is scoring.py's own pre-existing,
    disclosed engineered choice, reproduced here verbatim -- not a new
    threshold invented for this function."""
    if bootstrap_capacity is None or external_capital_raising_capacity is None:
        h2_strength = _house_lord_strength(payload, 2)
        h11_strength = _house_lord_strength(payload, 11)
        h8_strength = _house_lord_strength(payload, 8)
        bootstrap_capacity = round(min(100.0, max(0.0, h2_strength * 100.0)), 1)
        external_capital_raising_capacity = round(min(100.0, max(0.0, (0.7 * h11_strength + 0.3 * h8_strength) * 100.0)), 1)

    if not getattr(payload, "house_lords", None):
        return "INSUFFICIENT_DATA"
    _capital_margin = bootstrap_capacity - external_capital_raising_capacity
    if _capital_margin >= 3:
        return "BOOTSTRAP_FAVORED"
    elif _capital_margin <= -2:
        # Issue 9 safety gate: never surface a bare "raise external capital"
        # recommendation when the chart's own debt-management sub-score is
        # zero or the (separately computed, non-astrological-evidence-gated)
        # capital_readiness verdict is NOT_SUPPORTED -- a comparative lean
        # between two D1 house-lord strengths says nothing about whether
        # taking on external capital/debt is actually advisable right now,
        # and EXTERNAL_CAPITAL_FAVORED read in isolation can be misread as
        # "go raise money" even when other evidence says the venture isn't
        # ready to responsibly deploy or service it.
        if (debt_management_score is not None and debt_management_score <= 0) or (
            capital_readiness_status == "NOT_SUPPORTED"
        ):
            return "EXTERNAL_CAPITAL_ACCESSIBLE_BUT_NOT_ADVISABLE"
        return "EXTERNAL_CAPITAL_FAVORED"
    return "BALANCED"


def _planet_strength(payload: Any, planet: str) -> float:
    """0..1 strength for a specific planet's own placement + dignity.

    RETROGRADE-1: uses _retro_adjusted_dig_factor() instead of the plain
    _dig_factor() so retrograde status (when the payload carries it) is
    folded in via the same classical stance already established by the
    general engine's Shadbala "Retrograde Asymmetry" modifier -- see that
    helper's docstring for the exact rule and citation. Additive/backward
    compatible: identical to the pre-existing behavior whenever retrograde
    data is absent from payload.

    GYUDDHA-1: also multiplies in _graha_yuddha_loss_factor() so a planet
    that LOSES a Graha Yuddha (planetary war) is measurably weakened here
    too, not just in the Lagnesh-only evidence citation -- see that
    helper's docstring. No-op (1.0) for war winners, non-participants, or
    when longitude data is unavailable."""
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    house = planet_house.get(planet, 0)
    if not house:
        return 0.35
    dig = _dig_name(planet, dignities)

    if house in _KT:
        base = 1.0
    elif house in _UPACHAYA:
        base = 0.6
    elif house in _DUSTHANA:
        base = 0.55 if dig in _STRONG_DIGNITY else 0.25
    else:
        base = 0.45

    factor = (_retro_adjusted_dig_factor(payload, planet, dignities)
              * _graha_yuddha_loss_factor(payload, planet)
              * _combustion_strength_factor(payload, planet)
              * _shadbala_sav_strength_modifier(payload, planet))
    return round(min(1.0, base * factor), 4)

# v28 audit fix: _house_lord_strength()/_planet_strength() are used
# pervasively across this codebase (dignity-gated evidence weighting,
# threshold checks like >=0.6/<0.35, contradiction controls) as a 0..1
# scale, so they are deliberately left UNCHANGED above -- many existing
# tests and callers assume that exact 0..1 range and semantics. But a
# targeted audit of the "Top Business Sectors" output (rank_business_
# sectors_with_status -> sector_score) found a real ceiling-compression
# bug specific to that consumer: sector_score() blends house_component/
# planet_component at 60% combined weight (0.35 + 0.25) against the
# archetype_component (0.40), and because min(1.0, base * dig_factor)
# clips at exactly 1.0 while ANY kendra/trikona placement already sets
# base=1.0, an EXALTED lord (dig_factor=1.40) and a NEUTRAL-dignity lord
# (dig_factor=1.0) in the same kendra/trikona house both round to the
# identical 1.0 -- the dignity upside is thrown away exactly when the
# placement is already good, which is exactly the case for the strongest,
# most business-relevant charts. Verified on Karthick_chart_details.json:
# ranks 1-3 of the Top Business Sectors table (Import/Export 83.9, Tech
# Startup 79.6, Hospitality 72.8) all showed house_component_0_1=1.0 AND
# planet_component_0_1=1.0 simultaneously -- 60% of the blend weight
# contributing ZERO differentiation between three structurally different
# sectors, with 100% of their score separation coming from the remaining
# 40% (archetype_component) alone.
#
# Fix: these two "_fine" variants are used ONLY by sector_score() (not by
# any of the pre-existing 0..1-scale callers elsewhere in this codebase,
# so nothing else changes behavior) -- same placement-bucket logic, but
# WITHOUT the premature min(1.0, ...) clip, so dignity differentiates
# planets/lords even when the placement floor is already at its maximum
# (1.0 * 1.40 for EXALTED in kendra/trikona, 1.0 * 1.15 for OWN/
# MOOLATRIKONA, 1.0 * 1.0 for NEUTRAL, 1.0 * 0.55 for DEBILITATED-in-KT --
# note DEBILITATED can't actually reach a KT "base=1.0" placement bucket
# under most chart configurations, but the formula handles it correctly
# regardless). sector_score() divides the mean by 1.40 (the maximum
# attainable per-item value) to keep the component back in a 0..1 range
# consistent with the existing blend weights, rather than changing the
# 0.40/0.35/0.25 architecture itself.
def _house_lord_strength_fine(payload: Any, house_num: int) -> float:
    """Uncapped counterpart to _house_lord_strength(), for sector_score()
    only -- see the v28 audit-fix note above for why this exists as a
    separate function rather than modifying _house_lord_strength() itself."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    lord = house_lords.get(str(house_num), house_lords.get(house_num, ""))
    if not lord:
        return 0.35

    placed_house = planet_house.get(lord, 0)
    dig = _dig_name(lord, dignities)

    if placed_house in _KT:
        base = 1.0
    elif placed_house in _UPACHAYA:
        base = 0.65
    elif placed_house in _DUSTHANA:
        base = 0.60 if dig in _STRONG_DIGNITY else 0.25
    else:
        base = 0.45

    return round(base * _dig_factor(lord, dignities) * _shadbala_sav_strength_modifier(payload, lord), 4)

def _planet_strength_fine(payload: Any, planet: str) -> float:
    """Uncapped counterpart to _planet_strength(), for sector_score() only
    -- see the v28 audit-fix note above _house_lord_strength_fine().

    RETROGRADE-1: mirrors _planet_strength()'s retrograde-aware dignity
    factor (via _retro_adjusted_dig_factor()) for the same reason -- see
    that helper's docstring.

    GYUDDHA-1: also mirrors _planet_strength()'s Graha Yuddha loss factor
    -- see _graha_yuddha_loss_factor()'s docstring."""
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    house = planet_house.get(planet, 0)
    if not house:
        return 0.35
    dig = _dig_name(planet, dignities)

    if house in _KT:
        base = 1.0
    elif house in _UPACHAYA:
        base = 0.6
    elif house in _DUSTHANA:
        base = 0.55 if dig in _STRONG_DIGNITY else 0.25
    else:
        base = 0.45

    factor = (_retro_adjusted_dig_factor(payload, planet, dignities)
              * _graha_yuddha_loss_factor(payload, planet)
              * _combustion_strength_factor(payload, planet)
              * _shadbala_sav_strength_modifier(payload, planet))
    return round(base * factor, 4)

_NATURAL_BENEFICS = frozenset({"Jupiter", "Venus", "Moon", "Mercury"})

_NATURAL_MALEFICS = frozenset({"Saturn", "Mars", "Rahu", "Ketu", "Sun"})

def _moon_contextual_nature(payload: Any) -> Tuple[str, str]:
    """Moon is a natural benefic only when waxing (Shukla Paksha) --
    classically malefic-leaning when waning (Krishna Paksha), per BPHS
    ch.2's natural-benefic/malefic classification with the paksha-
    conditioned exception for Moon. Every rasi-drishti/argala/D10-
    occupancy check in this module previously treated Moon as an
    unconditional natural benefic; birth_tithi_num (1-30, already computed
    from Sun/Moon longitudes by engine_io.py and carried on the payload)
    now provides the real per-chart waxing/waning state.

    Simplification note: some classical texts sub-divide further (e.g.
    treating Krishna Paksha as fully malefic only from Krishna Ashtami/
    tithi ~23 onward, with the days just after Purnima still mild). This
    uses the coarser, more commonly cited Shukla=benefic / Krishna=malefic
    split at tithi 15 rather than picking a specific sub-threshold
    convention without an astrologer's guidance -- see module docstring.
    """
    tithi = int(getattr(payload, "birth_tithi_num", 0) or 0)
    if not tithi or not (1 <= tithi <= 30):
        return "BENEFIC", "no birth_tithi_num on payload -- defaulting to unconditional natural-benefic treatment"
    if tithi <= 15:
        return "BENEFIC", f"Shukla Paksha (waxing), tithi {tithi}/15 -> natural benefic"
    return "MALEFIC", f"Krishna Paksha (waning), tithi {tithi} -> malefic-leaning per BPHS paksha rule"

def _mercury_contextual_nature(payload: Any) -> Tuple[str, str]:
    """Mercury classically takes the nature of whatever planet(s) it
    associates with by conjunction (BPHS ch.2) -- it has no fixed nature of
    its own. Every rasi-drishti/argala/D10-occupancy check in this module
    previously treated Mercury as an unconditional natural benefic; this
    checks D1 house co-tenancy for natural benefic/malefic association
    instead. Mercury alone (no conjunction) retains its own default
    benefic nature, matching classical convention for an unassociated
    Mercury.
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    mercury_house = planet_house.get("Mercury", 0)
    if not mercury_house:
        return "BENEFIC", "Mercury house unknown -- defaulting to natural benefic"

    co_tenants = [p for p, h in planet_house.items() if h == mercury_house and p != "Mercury"]
    benefic_assoc = [p for p in co_tenants if p in _NATURAL_BENEFICS - {"Mercury"}]
    malefic_assoc = [p for p in co_tenants if p in _NATURAL_MALEFICS]

    if malefic_assoc and not benefic_assoc:
        return "MALEFIC", f"Mercury conjunct {', '.join(sorted(malefic_assoc))} (malefic association) -> takes malefic nature"
    if benefic_assoc and not malefic_assoc:
        return "BENEFIC", f"Mercury conjunct {', '.join(sorted(benefic_assoc))} (benefic association) -> confirms benefic nature"
    if benefic_assoc and malefic_assoc:
        return "MIXED", f"Mercury conjunct both benefic ({', '.join(sorted(benefic_assoc))}) and malefic ({', '.join(sorted(malefic_assoc))}) -> mixed nature, treated as neutral"
    return "BENEFIC", "Mercury unconjunct (alone in house) -> retains its own default benefic nature"

def _functional_kendra_trikona_lords(payload: Any) -> frozenset:
    """Classical functional-lordship principle (audit finding: Sun/Mars/
    Saturn were being treated as unconditional natural malefics even when
    they hold kendra/trikona lordship for THIS ascendant, discarding a
    bedrock Parashari rule -- a natural malefic that owns a kendra (1/4/7/
    10) or trikona (1/5/9) sign for the chart's own Lagna is at minimum
    NOT to be read as afflictive there, and if it owns BOTH a kendra and a
    trikona it becomes a yoga-karaka, one of the strongest possible
    benefics for that chart. Example: for a Sagittarius lagna, Sun rules
    Leo (H9, trikona) -- Sun there is a fortune/dharma significator, not a
    blanket malefic, and penalizing its rasi-drishti/argala/conjunction
    effects as unqualified 'malefic pressure' is doctrinally crude.

    Scope: only Sun/Mars/Saturn are checked (classical planets that hold
    sign lordship). Rahu/Ketu are nodes and do not rule signs in most
    systems this repo uses, so they are excluded and remain fixed
    malefics -- a separate, still-open simplification.
    """
    house_lords = getattr(payload, "house_lords", {}) or {}

    def _h(n: int) -> str:
        return house_lords.get(str(n), house_lords.get(n, ""))

    kendra_trikona_houses = (1, 4, 5, 7, 9, 10)
    ruling = {_h(h) for h in kendra_trikona_houses} - {""}
    return frozenset(p for p in ("Sun", "Mars", "Saturn") if p in ruling)

def _effective_benefic_malefic_sets(payload: Any) -> Tuple[frozenset, frozenset]:
    """Natural-benefic/malefic planet sets with Moon and Mercury's
    CONTEXTUAL (per-chart) nature substituted for the fixed classification
    _NATURAL_BENEFICS/_NATURAL_MALEFICS previously used unconditionally,
    PLUS functional-lordship neutralization for Sun/Mars/Saturn (see
    _functional_kendra_trikona_lords): a naturally-malefic planet that
    rules a kendra/trikona house for this Lagna is excluded from the
    malefic set (treated as neutral, not benefic by default -- a
    conservative reading; classical yoga-karaka promotion to full benefic
    status is not claimed here). Jupiter/Venus (always benefic) and Rahu/
    Ketu (always malefic, nodes don't hold sign lordship in this repo's
    systems) are unaffected. If Mercury's association is MIXED, it is
    excluded from both sets (neutral -- does not count as either benefic
    or malefic support/pressure).
    """
    benefics = set(_NATURAL_BENEFICS) - {"Moon", "Mercury"}
    malefics = set(_NATURAL_MALEFICS)

    moon_nature, _moon_note = _moon_contextual_nature(payload)
    (benefics if moon_nature == "BENEFIC" else malefics).add("Moon")

    merc_nature, _merc_note = _mercury_contextual_nature(payload)
    if merc_nature == "BENEFIC":
        benefics.add("Mercury")
    elif merc_nature == "MALEFIC":
        malefics.add("Mercury")
    # MIXED -> Mercury excluded from both sets.

    functional_neutral = _functional_kendra_trikona_lords(payload)
    malefics -= functional_neutral

    return frozenset(benefics), frozenset(malefics)

def _house_sign(lagna_sign: str, house_num: int) -> str:
    """D1 sign occupying a given house, whole-sign from lagna."""
    from Stream_Determination.stream_scoring import _RASI_SIGNS
    if lagna_sign not in _RASI_SIGNS:
        return ""
    idx = _RASI_SIGNS.index(lagna_sign)
    return _RASI_SIGNS[(idx + house_num - 1) % 12]

def _d9_house_occupancy_from_divisional_charts(payload: Any) -> Tuple[str, Dict[int, List[str]]]:
    """Builds a real D9 (Navamsha) house-occupancy graph from
    payload.divisional_charts["D9_navamsha"] (a flat {planet: sign, "Lagna":
    sign} dict engine_io.py already parses from the source chart JSON --
    the same divisional_charts container jyotish/d10_archetypes.py already
    reads D10 sign data from). This was previously assumed unavailable
    because NatalPayloadV2 has no dedicated d9_house_occupancy field, but
    the raw sign data needed to derive one was already on the payload the
    whole time -- it just needed the same sign-to-house arithmetic
    d10_archetypes.py uses for D10 (house = ((sign_index - lagna_index) %
    12) + 1), applied here to D9 instead.

    Returns (resolved_lagna_sign, occupancy) as a single canonical pair --
    callers MUST use the returned lagna_sign (not payload.d9_lagna_sign
    independently) for any lordship/reference-house math on this occupancy,
    so occupancy and lordship can never be computed against two different
    ascendants if divisional_charts["D9_navamsha"]["Lagna"] and
    payload.d9_lagna_sign ever disagree.
    """
    from jyotish.d10_archetypes import SIGNS

    dc = getattr(payload, "divisional_charts", {}) or {}
    d9_chart = dc.get("D9_navamsha", {}) or {}
    if not isinstance(d9_chart, dict) or not d9_chart:
        return "", {}

    lagna_sign = d9_chart.get("Lagna") or getattr(payload, "d9_lagna_sign", "") or ""
    if lagna_sign not in SIGNS:
        return "", {}
    lagna_idx = SIGNS.index(lagna_sign)

    occupancy: Dict[int, List[str]] = {}
    for planet, sign in d9_chart.items():
        if planet == "Lagna" or sign not in SIGNS:
            continue
        house = ((SIGNS.index(sign) - lagna_idx) % 12) + 1
        occupancy.setdefault(house, []).append(planet)
    return lagna_sign, occupancy

def _d9_native_house_evidence(payload: Any) -> List[Tuple[float, str]]:
    """Full Navamsha-NATIVE house-graph reconstruction, mirroring
    _d10_native_house_evidence() below exactly, now that
    _d9_house_occupancy_from_divisional_charts() provides real D9
    occupancy: does the D9-H7/H1/H11 lord itself sit in a D9
    kendra/trikona (D9's own house graph), and do natural benefics/
    malefics occupy D9-H2/H7/H11 vs D9-H6/H8/H12? H1 (not H10) is checked
    here instead of H10, since D9 is classically read for partnership/
    marriage/dharma strength (Lagna-centric), not livelihood -- H10's
    Navamsha role is weaker than H7/H1/H9 for this module's purposes.
    """
    d9_lagna, occupancy = _d9_house_occupancy_from_divisional_charts(payload)
    if not occupancy or not d9_lagna:
        return []

    def _occ(h: int) -> List[str]:
        return occupancy.get(h, []) or []

    def _lord(h: int) -> str:
        return _house_from_reference_lord(d9_lagna, h)

    def _native_house_of(planet: str) -> int:
        for h in range(1, 13):
            if planet in _occ(h):
                return h
        return 0

    results: List[Tuple[float, str]] = []

    for house_num, label in ((7, "H7 (partnership)"), (1, "H1 (own strength)"), (11, "H11 (gains)")):
        lord = _lord(house_num)
        if not lord:
            continue
        lord_native_house = _native_house_of(lord)
        if lord_native_house in _KT:
            results.append((5.0, f"D9-native: D9-{label} lord ({lord}) sits in D9-kendra/trikona (D9-H{lord_native_house}) -> Navamsha house graph confirms"))
        elif lord_native_house in _DUSTHANA:
            results.append((-4.0, f"D9-native: D9-{label} lord ({lord}) sits in D9-dusthana (D9-H{lord_native_house}) -> Navamsha house graph weakens promise"))

    benefics, malefics = _effective_benefic_malefic_sets(payload)
    benefics_h2711 = [p for h in (2, 7, 11) for p in _occ(h) if p in benefics]
    malefics_h2711 = [p for h in (2, 7, 11) for p in _occ(h) if p in malefics]
    if benefics_h2711:
        results.append((3.0, f"D9-native: benefic(s) {', '.join(sorted(set(benefics_h2711)))} occupy D9-H2/H7/H11 -> direct Navamsha support"))
    malefics_h6812 = [p for h in (6, 8, 12) for p in _occ(h) if p in malefics]
    if malefics_h6812:
        results.append((-3.0, f"D9-native: malefic(s) {', '.join(sorted(set(malefics_h6812)))} occupy D9-H6/H8/H12 -> Navamsha risk exposure"))

    return results

def _d7_saptamsha_house_occupancy_from_divisional_charts(payload: Any) -> Tuple[str, Dict[int, List[str]]]:
    """Builds a real D7 (Saptamsha) house-occupancy graph, mirroring
    _d9_house_occupancy_from_divisional_charts() exactly: reads
    payload.divisional_charts["D7_saptamsha"] (a flat {planet: sign,
    "Lagna": sign} dict, same divisional_charts container D9/D10/D2 already
    read from) and derives house = ((sign_index - lagna_index) % 12) + 1.

    Unlike D9/D10 (which have dedicated payload.d9_lagna_sign/
    d10_house_occupancy fields as an upstream fallback), NatalPayloadV2 has
    no d7_lagna_sign field and no lagna_degree field (the same documented
    limitation compute_d24_chart() already has for D24) -- so the D7 Lagna
    can ONLY come from an upstream-supplied divisional_charts["D7_saptamsha"]
    ["Lagna"] value here; it cannot be independently re-derived in-house.
    Returns ("", {}) gracefully (not a penalty) when no upstream D7 Lagna is
    present, exactly like D9's graceful-empty behavior when its dict is
    missing/malformed.

    Returns (resolved_lagna_sign, occupancy) as a single canonical pair --
    same "one source of truth for lordship+occupancy" contract as D9's
    function.
    """
    from jyotish.d10_archetypes import SIGNS

    dc = getattr(payload, "divisional_charts", {}) or {}
    d7_chart = dc.get("D7_saptamsha", {}) or {}
    if not isinstance(d7_chart, dict) or not d7_chart:
        return "", {}

    lagna_sign = d7_chart.get("Lagna") or getattr(payload, "d7_lagna_sign", "") or ""
    if lagna_sign not in SIGNS:
        return "", {}
    lagna_idx = SIGNS.index(lagna_sign)

    occupancy: Dict[int, List[str]] = {}
    for planet, sign in d7_chart.items():
        if planet == "Lagna" or sign not in SIGNS:
            continue
        house = ((SIGNS.index(sign) - lagna_idx) % 12) + 1
        occupancy.setdefault(house, []).append(planet)
    return lagna_sign, occupancy


def _d7_native_house_evidence(payload: Any) -> List[Tuple[float, str]]:
    """D7 (Saptamsha) corroboration of a SINGLE native's own 7th-house/
    partnership-capacity promise -- deliberately scoped NARROWLY to H7
    (the partnership house) and the H7 lord's D7 placement/dignity, unlike
    _d9_native_house_evidence()/_d10_native_house_evidence() above (which
    check H1/H7/H10/H11/H3/H5 broadly). This is because D7's classical
    remit is progeny/partnership-through-alliance specifically, and this
    module's use of it here is narrowly to confirm/deny the D1 7th-house
    (partnership) promise -- not a general-purpose life-area corroboration
    layer the way D9/D10 are used elsewhere in this file.

    Two components, mirroring D9/D10's "lord's own house-graph placement"
    + "benefic/malefic occupancy" structure exactly:
      (1) does the D1-H7 lord, located inside the D7 chart's OWN house
          graph (D7-native house, not D1 house), sit in a D7-kendra/
          trikona vs D7-dusthana?
      (2) what is that same D1-H7 lord's D7 dignity (via the same
          _rich_planet_dignities() five-fold dignity map already used by
          this module's D1-level checks, applied here to the D7 SIGN the
          lord occupies)?

    Gracefully degrades to [] (no evidence, not a penalty) when D7 occupancy
    can't be resolved (no upstream divisional_charts["D7_saptamsha"], see
    _d7_saptamsha_house_occupancy_from_divisional_charts()'s documented
    Lagna-availability limitation) or house_lords/H7 lord is missing.
    """
    d7_lagna, occupancy = _d7_saptamsha_house_occupancy_from_divisional_charts(payload)
    house_lords = getattr(payload, "house_lords", {}) or {}
    if not occupancy or not d7_lagna or not house_lords:
        return []

    h7_lord = house_lords.get("7", house_lords.get(7, ""))
    if not h7_lord:
        return []

    def _occ(h: int) -> List[str]:
        return occupancy.get(h, []) or []

    def _native_house_of(planet: str) -> int:
        for h in range(1, 13):
            if planet in _occ(h):
                return h
        return 0

    results: List[Tuple[float, str]] = []

    lord_native_house = _native_house_of(h7_lord)
    if lord_native_house in _KT:
        results.append((5.0, f"D7-native: D1-H7 (partnership) lord ({h7_lord}) sits in D7-kendra/trikona (D7-H{lord_native_house}) -> Saptamsha confirms partnership capacity"))
    elif lord_native_house in _DUSTHANA:
        results.append((-4.0, f"D7-native: D1-H7 (partnership) lord ({h7_lord}) sits in D7-dusthana (D7-H{lord_native_house}) -> Saptamsha weakens partnership-capacity promise"))

    d7_sign = ""
    for h in range(1, 13):
        if h7_lord in _occ(h):
            # Reconstruct the D7 sign the lord occupies from house+lagna,
            # so its D7 dignity can be read via the same dignity tables
            # used for D1 (dignity depends only on planet+sign, not chart).
            from jyotish.d10_archetypes import SIGNS
            lagna_idx = SIGNS.index(d7_lagna)
            d7_sign = SIGNS[(lagna_idx + h - 1) % 12]
            break
    if d7_sign:
        # Dignity is planet+sign dependent, so it must be recomputed for
        # the D7 sign specifically via jyotish.dignity.dignity_state()
        # (the same five-fold dignity primitive _rich_planet_dignities()
        # itself is built on) rather than reusing the D1 rich-dignity map,
        # which is keyed to D1 sign placements.
        try:
            from jyotish.dignity import dignity_state as _jyotish_dignity_state
            d7_dignity = _jyotish_dignity_state(h7_lord, d7_sign)
        except Exception as exc:
            _record_diagnostic("house_evidence._d7_native_house_evidence", exc)
            d7_dignity = "NEUTRAL"
        if d7_dignity in ("EXALTED", "OWN_SIGN", "MOOLATRIKONA", "GREAT_FRIEND"):
            results.append((3.0, f"D7-native: D1-H7 lord ({h7_lord}) is {d7_dignity} in its D7 sign ({d7_sign}) -> strong Saptamsha dignity supports partnership capacity"))
        elif d7_dignity in ("DEBILITATED", "GREAT_ENEMY"):
            results.append((-3.0, f"D7-native: D1-H7 lord ({h7_lord}) is {d7_dignity} in its D7 sign ({d7_sign}) -> Saptamsha dignity weakens partnership capacity"))

    return results


def _d3_drekkana_house_occupancy_from_divisional_charts(payload: Any) -> Tuple[str, Dict[int, List[str]]]:
    """Builds a real D3 (Drekkana) house-occupancy graph, mirroring
    _d7_saptamsha_house_occupancy_from_divisional_charts() exactly: reads
    payload.divisional_charts["D3_drekkana"] (a flat {planet: sign,
    "Lagna": sign} dict, same divisional_charts container D9/D10/D2/D7
    already read from) and derives house = ((sign_index - lagna_index) %
    12) + 1.

    Unlike D9/D10 (which have dedicated payload.d9_lagna_sign/
    d10_house_occupancy fields as an upstream fallback), NatalPayloadV2 has
    no d3_lagna_sign field and no lagna_degree field -- the same
    documented limitation compute_d7_saptamsha_chart()/
    _d7_saptamsha_house_occupancy_from_divisional_charts() already have
    for D7 -- so the D3 Lagna can ONLY come from an upstream-supplied
    divisional_charts["D3_drekkana"]["Lagna"] value here; it cannot be
    independently re-derived in-house (jyotish.astro.compute_d3_drekkana_chart
    exists for callers that DO have a lagna_degree, but this module's
    payload never does). Returns ("", {}) gracefully (not a penalty) when
    no upstream D3 Lagna is present, exactly like D7's graceful-empty
    behavior when its dict is missing/malformed.

    Returns (resolved_lagna_sign, occupancy) as a single canonical pair --
    same "one source of truth for lordship+occupancy" contract as D9/D7's
    functions.
    """
    from jyotish.d10_archetypes import SIGNS

    dc = getattr(payload, "divisional_charts", {}) or {}
    d3_chart = dc.get("D3_drekkana", {}) or {}
    if not isinstance(d3_chart, dict) or not d3_chart:
        return "", {}

    lagna_sign = d3_chart.get("Lagna") or getattr(payload, "d3_lagna_sign", "") or ""
    if lagna_sign not in SIGNS:
        return "", {}
    lagna_idx = SIGNS.index(lagna_sign)

    occupancy: Dict[int, List[str]] = {}
    for planet, sign in d3_chart.items():
        if planet == "Lagna" or sign not in SIGNS:
            continue
        house = ((SIGNS.index(sign) - lagna_idx) % 12) + 1
        occupancy.setdefault(house, []).append(planet)
    return lagna_sign, occupancy


def _d3_native_house_evidence(payload: Any) -> List[Tuple[float, str]]:
    """D3 (Drekkana) corroboration of a SINGLE native's own 3rd-house/
    self-effort-and-courage promise -- deliberately scoped NARROWLY to H3
    (the self-effort/initiative/courage house), mirroring
    _d7_native_house_evidence()'s structure and status-diagnostic
    conventions exactly (which is itself narrowly scoped to H7). This is
    because D3's classical remit is siblings/courage/self-effort
    specifically, and this module's use of it here is narrowly to
    confirm/deny the D1 3rd-house (self-effort) promise already checked by
    significators.py's H3-lord evidence and contradictions.py's "strong H3
    weak H2" caution check -- not a general-purpose life-area
    corroboration layer the way D9/D10 are used elsewhere in this file.

    Two components, mirroring D7's "lord's own house-graph placement" +
    "dignity in that varga sign" structure exactly:
      (1) does the D1-H3 lord, located inside the D3 chart's OWN house
          graph (D3-native house, not D1 house), sit in a D3-kendra/
          trikona vs D3-dusthana?
      (2) what is that same D1-H3 lord's D3 dignity (via
          jyotish.dignity.dignity_state(), the same five-fold dignity
          primitive _rich_planet_dignities() is built on, applied here to
          the D3 SIGN the lord occupies)?

    Gracefully degrades to [] (no evidence, not a penalty) when D3
    occupancy can't be resolved (no upstream divisional_charts
    ["D3_drekkana"], see _d3_drekkana_house_occupancy_from_divisional_charts()'s
    documented Lagna-availability limitation) or house_lords/H3 lord is
    missing -- callers (significators.py/contradictions.py) MUST fall back
    to their existing D1-only H3 evidence in that case, not silently treat
    an empty list as a contradiction signal.
    """
    d3_lagna, occupancy = _d3_drekkana_house_occupancy_from_divisional_charts(payload)
    house_lords = getattr(payload, "house_lords", {}) or {}
    if not occupancy or not d3_lagna or not house_lords:
        return []

    h3_lord = house_lords.get("3", house_lords.get(3, ""))
    if not h3_lord:
        return []

    def _occ(h: int) -> List[str]:
        return occupancy.get(h, []) or []

    def _native_house_of(planet: str) -> int:
        for h in range(1, 13):
            if planet in _occ(h):
                return h
        return 0

    results: List[Tuple[float, str]] = []

    lord_native_house = _native_house_of(h3_lord)
    if lord_native_house in _KT:
        results.append((5.0, f"D3-native: D1-H3 (self-effort/courage) lord ({h3_lord}) sits in D3-kendra/trikona (D3-H{lord_native_house}) -> Drekkana confirms self-effort/courage capacity"))
    elif lord_native_house in _DUSTHANA:
        results.append((-4.0, f"D3-native: D1-H3 (self-effort/courage) lord ({h3_lord}) sits in D3-dusthana (D3-H{lord_native_house}) -> Drekkana weakens self-effort/courage promise"))

    d3_sign = ""
    for h in range(1, 13):
        if h3_lord in _occ(h):
            # Reconstruct the D3 sign the lord occupies from house+lagna,
            # so its D3 dignity can be read via the same dignity tables
            # used for D1 (dignity depends only on planet+sign, not chart).
            from jyotish.d10_archetypes import SIGNS
            lagna_idx = SIGNS.index(d3_lagna)
            d3_sign = SIGNS[(lagna_idx + h - 1) % 12]
            break
    if d3_sign:
        try:
            from jyotish.dignity import dignity_state as _jyotish_dignity_state
            d3_dignity = _jyotish_dignity_state(h3_lord, d3_sign)
        except Exception as exc:
            _record_diagnostic("house_evidence._d3_native_house_evidence", exc)
            d3_dignity = "NEUTRAL"
        if d3_dignity in ("EXALTED", "OWN_SIGN", "MOOLATRIKONA", "GREAT_FRIEND"):
            results.append((3.0, f"D3-native: D1-H3 lord ({h3_lord}) is {d3_dignity} in its D3 sign ({d3_sign}) -> strong Drekkana dignity supports self-effort/courage"))
        elif d3_dignity in ("DEBILITATED", "GREAT_ENEMY"):
            results.append((-3.0, f"D3-native: D1-H3 lord ({h3_lord}) is {d3_dignity} in its D3 sign ({d3_sign}) -> Drekkana dignity weakens self-effort/courage"))

    return results


def _d10_native_house_evidence(payload: Any) -> List[Tuple[float, str]]:
    """Full Dashamsha-NATIVE house-graph reconstruction: does the D10 lord
    of D10-H7/H10/H11 itself sit in a D10 kendra/trikona (evaluated inside
    the D10 chart's own house graph via d10_house_occupancy/d10_house_lords
    -- i.e. which D10 house that lord occupies within D10, not which D1
    house it occupies), and do natural benefics/malefics occupy D10-H2/H7/
    H11/H6/H8/H12? This is distinct from, and a real upgrade over, the
    earlier _multi_varga_lagna_precedence_evidence(), which only checked a
    varga-Lagna-derived lord's D1 placement (varga-native LORDSHIP
    projected onto D1, not a native varga HOUSE GRAPH). See
    _d9_native_house_evidence() above for the D9 (Navamsha) equivalent.
    """
    occupancy = getattr(payload, "d10_house_occupancy", {}) or {}
    house_lords = getattr(payload, "d10_house_lords", {}) or {}
    if not occupancy or not house_lords:
        return []

    def _occ(h: int) -> List[str]:
        return occupancy.get(str(h), occupancy.get(h, [])) or []

    def _lord(h: int) -> str:
        return house_lords.get(str(h), house_lords.get(h, ""))

    def _native_house_of(planet: str) -> int:
        for h in range(1, 13):
            if planet in _occ(h):
                return h
        return 0

    results: List[Tuple[float, str]] = []
    benefics, malefics = _effective_benefic_malefic_sets(payload)

    # v20 audit fix: D10's own Lagna (D10-H1) -- the execution-chart's
    # equivalent of self-agency/entrepreneurial capacity -- was never
    # separately scored; only H7/H10/H11 (and, since v18, H3/H5) lord
    # placement was checked. Mirrors the same lord-placement pattern used
    # for the other D10-native houses, plus benefic/malefic occupancy of
    # D10-H1 itself (the same asymmetry-fix pattern already applied to D1
    # Lagna occupancy in compute_business_mode_gate).
    d10_lagna_lord = _lord(1)
    if d10_lagna_lord:
        lagna_lord_native_house = _native_house_of(d10_lagna_lord)
        if lagna_lord_native_house in _KT:
            results.append((5.0, f"D10-native: D10-Lagna lord ({d10_lagna_lord}) sits in D10-kendra/trikona (D10-H{lagna_lord_native_house}) -> Dashamsha self-agency confirms"))
        elif lagna_lord_native_house in _DUSTHANA:
            results.append((-4.0, f"D10-native: D10-Lagna lord ({d10_lagna_lord}) sits in D10-dusthana (D10-H{lagna_lord_native_house}) -> Dashamsha self-agency weakened"))
    benefics_h1_d10 = [p for p in _occ(1) if p in benefics]
    malefics_h1_d10 = [p for p in _occ(1) if p in malefics]
    if benefics_h1_d10:
        results.append((3.0, f"D10-native: benefic(s) {', '.join(sorted(set(benefics_h1_d10)))} occupy D10-Lagna (D10-H1) -> execution temperament directly supported"))
    if malefics_h1_d10:
        results.append((-2.0, f"D10-native: malefic(s) {', '.join(sorted(set(malefics_h1_d10)))} occupy D10-Lagna (D10-H1) -> execution temperament under strain"))

    for house_num, label in ((7, "H7 (venture)"), (10, "H10 (livelihood)"), (11, "H11 (gains)")):
        lord = _lord(house_num)
        if not lord:
            continue
        lord_native_house = _native_house_of(lord)
        if lord_native_house in _KT:
            results.append((5.0, f"D10-native: D10-{label} lord ({lord}) sits in D10-kendra/trikona (D10-H{lord_native_house}) -> Dashamsha house graph confirms"))
        elif lord_native_house in _DUSTHANA:
            results.append((-4.0, f"D10-native: D10-{label} lord ({lord}) sits in D10-dusthana (D10-H{lord_native_house}) -> Dashamsha house graph weakens promise"))

    # v18 audit fix: D10-H3 (entrepreneurial initiative WITHIN the
    # execution/operating chart) and D10-H5 (strategic/creative
    # intelligence WITHIN execution) were never checked -- only H7/H10/H11
    # were. Weighted slightly lighter than the core triad since H3/H5 are
    # secondary execution signals, not the primary livelihood/venture/gains
    # houses.
    for house_num, label in ((3, "H3 (execution initiative)"), (5, "H5 (execution strategy/creativity)")):
        lord = _lord(house_num)
        if not lord:
            continue
        lord_native_house = _native_house_of(lord)
        if lord_native_house in _KT:
            results.append((3.5, f"D10-native: D10-{label} lord ({lord}) sits in D10-kendra/trikona (D10-H{lord_native_house}) -> Dashamsha execution graph confirms"))
        elif lord_native_house in _DUSTHANA:
            results.append((-2.5, f"D10-native: D10-{label} lord ({lord}) sits in D10-dusthana (D10-H{lord_native_house}) -> Dashamsha execution graph weakens this signal"))

    # Moon/Mercury use their CONTEXTUAL nature (paksha for Moon, D1
    # conjunction-association for Mercury) here too -- paksha is a fixed
    # natal fact independent of which varga is being read, and D1
    # association is the best available proxy for Mercury's nature absent
    # D10-native conjunction data.
    # Audit finding: the positive occupancy scan previously only checked
    # D10-H2/H7/H11, giving no credit for benefics occupying D10-H10
    # itself (the livelihood house) -- an asymmetry against the negative
    # scan, which covers the full dusthana set. Benefics in D10-H10 are
    # scored as their own, slightly lighter finding (livelihood support,
    # not the core wealth-house triad).
    benefics_h2711 = [p for h in (2, 7, 11) for p in _occ(h) if p in benefics]
    malefics_h2711 = [p for h in (2, 7, 11) for p in _occ(h) if p in malefics]
    if benefics_h2711:
        results.append((3.0, f"D10-native: benefic(s) {', '.join(sorted(set(benefics_h2711)))} occupy D10-H2/H7/H11 -> direct Dashamsha support"))
    benefics_h10 = [p for p in _occ(10) if p in benefics]
    if benefics_h10:
        results.append((2.0, f"D10-native: benefic(s) {', '.join(sorted(set(benefics_h10)))} occupy D10-H10 -> livelihood house directly supported"))

    # Audit finding: H6/H8/H12 were treated identically as generic "risk
    # exposure", but H6 is an UPACHAYA -- malefics there classically
    # support competition, overcoming opponents, and organizational
    # command, not pure loss the way H8 (transformation/crisis) or H12
    # (isolation/expenditure) are. Standalone H6 occupancy (no H8/H12
    # co-presence) is now scored as a softer, direction-neutral finding
    # rather than unqualified risk -- mirroring the same H6-softening
    # already applied to KP significations (_KP_SOFT_NEGATIVE_HOUSES).
    malefics_h6 = [p for p in _occ(6) if p in malefics]
    malefics_h812 = [p for h in (8, 12) for p in _occ(h) if p in malefics]
    if malefics_h812:
        results.append((-3.0, f"D10-native: malefic(s) {', '.join(sorted(set(malefics_h812)))} occupy D10-H8/H12 -> Dashamsha risk exposure"))
    if malefics_h6 and not malefics_h812:
        results.append((-1.0, f"D10-native: malefic(s) {', '.join(sorted(set(malefics_h6)))} occupy D10-H6 (upachaya) -> competitive/service pressure, not pure loss (softened, no H8/H12 co-presence)"))
    elif malefics_h6 and malefics_h812:
        results.append((-3.0, f"D10-native: malefic(s) {', '.join(sorted(set(malefics_h6)))} also occupy D10-H6 alongside H8/H12 -> compounds risk exposure"))

    return results


def _d10_native_job_house_evidence(payload: Any) -> List[Tuple[float, str]]:
    """Independent Dashamsha-NATIVE house-graph reconstruction for the JOB/
    SERVICE/HIERARCHY reading, addressing audit finding #5: this engine's
    job-side D10 execution layer (scoring.py's `d10_service_execution`)
    previously did not compute a dedicated service/institutional D10 graph
    at all -- it derived the job reading purely by taking the BUSINESS-side
    D10-native net (see _d10_native_house_evidence above, built from D10-H1/
    H3/H5/H7/H10/H11) and multiplying it by -0.4, i.e. treating "not
    ownership-favorable" as a proxy for "service-favorable". Classically
    those are not required to be exact opposites: a chart's D10 graph can
    read weak on BOTH ownership execution (H7/H10/H11-as-venture) and
    service/institutional execution (H6/H2/H10-as-position/H11-as-employment-
    gains) at once, or strong on both (a chart suited to either path
    equally well).

    This function evaluates D10's own house graph independently, anchored
    to the job/service-specific houses instead of reusing the ownership
    triad:
      - D10-H6 (service, subordination, competitive/organizational
        placement -- the direct service-execution house, mirroring D10-H7's
        role for ownership in the business-side function above)
      - D10-H10 (livelihood/position/authority within an institution --
        shared with the business reading, since the 10th house is the
        career-outcome house in EITHER mode, but evaluated here purely for
        its own D10-native placement, not reused from the business
        computation)
      - D10-H2 (salary/fixed income -- the service-mode analogue of H2/H11
        as commercial gains)
      - D10-H11 (gains-through-employment -- shared label with the business
        reading's H11, but a DIFFERENT classical referent: steady
        incremental income from a position, not venture profit)
    Malefic/benefic occupancy of D10-H6/H10/H2/H11 is scored the same way
    _d10_native_house_evidence() scores D10-H2/H7/H11 -- direct support/
    strain on the execution graph, not a reversal of any other layer's net.

    Never raises; returns [] when d10_house_occupancy/d10_house_lords are
    unavailable (same graceful-empty behavior as the business-side function).
    """
    occupancy = getattr(payload, "d10_house_occupancy", {}) or {}
    house_lords = getattr(payload, "d10_house_lords", {}) or {}
    if not occupancy or not house_lords:
        return []

    def _occ(h: int) -> List[str]:
        return occupancy.get(str(h), occupancy.get(h, [])) or []

    def _lord(h: int) -> str:
        return house_lords.get(str(h), house_lords.get(h, ""))

    def _native_house_of(planet: str) -> int:
        for h in range(1, 13):
            if planet in _occ(h):
                return h
        return 0

    results: List[Tuple[float, str]] = []
    benefics, malefics = _effective_benefic_malefic_sets(payload)

    # D10-H6 is the primary service-execution house for this reading (the
    # job-side mirror of D10-H7's role for ownership above): its lord
    # landing in a D10 kendra/trikona reads as strong service/subordinate-
    # role execution capacity; landing in a D10 dusthana reads as
    # instability/friction WITHIN that service role.
    for house_num, label, kt_weight, dusthana_weight in (
        (6, "H6 (service execution)", 5.0, -4.0),
        (10, "H10 (institutional livelihood)", 5.0, -4.0),
        (2, "H2 (salary/fixed income)", 4.0, -3.0),
        (11, "H11 (employment gains)", 4.0, -3.0),
    ):
        lord = _lord(house_num)
        if not lord:
            continue
        lord_native_house = _native_house_of(lord)
        if lord_native_house in _KT:
            results.append((kt_weight, f"D10-native (job): D10-{label} lord ({lord}) sits in D10-kendra/trikona (D10-H{lord_native_house}) -> Dashamsha service/institutional graph confirms"))
        elif lord_native_house in _DUSTHANA:
            results.append((dusthana_weight, f"D10-native (job): D10-{label} lord ({lord}) sits in D10-dusthana (D10-H{lord_native_house}) -> Dashamsha service/institutional graph weakens this signal"))

    benefics_h26_10_11 = [p for h in (2, 6, 10, 11) for p in _occ(h) if p in benefics]
    malefics_h26_10_11 = [p for h in (2, 6, 10, 11) for p in _occ(h) if p in malefics]
    if benefics_h26_10_11:
        results.append((3.0, f"D10-native (job): benefic(s) {', '.join(sorted(set(benefics_h26_10_11)))} occupy D10-H2/H6/H10/H11 -> direct service/institutional-execution support"))

    # Same H6-is-upachaya softening logic as the business-side function
    # (malefics in H6 alone read as competitive pressure, not pure loss;
    # only escalate when H8/H12 also afflicted), applied symmetrically here
    # since this function scores H6 as its PRIMARY house rather than a
    # secondary one.
    malefics_h6 = [p for p in _occ(6) if p in malefics]
    malefics_h812 = [p for h in (8, 12) for p in _occ(h) if p in malefics]
    if malefics_h812:
        results.append((-3.0, f"D10-native (job): malefic(s) {', '.join(sorted(set(malefics_h812)))} occupy D10-H8/H12 -> service/institutional risk exposure"))
    if malefics_h6 and not malefics_h812:
        results.append((-1.0, f"D10-native (job): malefic(s) {', '.join(sorted(set(malefics_h6)))} occupy D10-H6 (upachaya, primary service house here) -> competitive pressure within the role, not pure loss (softened, no H8/H12 co-presence)"))
    elif malefics_h6 and malefics_h812:
        results.append((-3.0, f"D10-native (job): malefic(s) {', '.join(sorted(set(malefics_h6)))} also occupy D10-H6 alongside H8/H12 -> compounds service/institutional risk exposure"))

    # D10-H2 malefic occupancy specifically (salary stability) -- kept
    # separate from the H2/H6/H10/H11 benefic bundle above since a
    # malefic-only H2 (no compensating H6/H10/H11 benefic) is a distinct,
    # narrower caution (income-specific instability) rather than a general
    # service-execution finding.
    malefics_h2 = [p for p in _occ(2) if p in malefics]
    if malefics_h2 and not benefics_h26_10_11:
        results.append((-2.0, f"D10-native (job): malefic(s) {', '.join(sorted(set(malefics_h2)))} occupy D10-H2 with no offsetting benefic in D10-H2/H6/H10/H11 -> salary/fixed-income stability specifically under strain"))

    return results


def _d2_hora_positions_from_payload(payload: Any) -> Dict[str, str]:
    """Flat {planet: "Leo"|"Cancer"} Hora (D2) sign map for this chart.

    Prefers an upstream-supplied D2 chart at
    payload.divisional_charts["D2_hora"] (same divisional_charts container
    D9/D10/D24 already read from, keyed following that container's own
    "D{n}_{name}" convention). Falls back to computing D2 in-house via
    jyotish.astro.compute_d2_hora_chart(payload.planets_d1) when no
    upstream D2 is present -- mirroring compute_d24_chart's fallback role
    for D24 (a cross-checkable in-house derivation, not a blind trust of
    upstream data). No independent D2-Lagna can be derived here, the same
    documented limitation compute_d24_chart already has (no lagna_degree
    field on NatalPayloadV2) -- so this returns PLANET positions only,
    never a "Lagna" key.
    """
    dc = getattr(payload, "divisional_charts", {}) or {}
    d2_chart = dc.get("D2_hora", {}) or {}
    positions: Dict[str, str] = {}
    if isinstance(d2_chart, dict) and d2_chart:
        # Upstream D2_hora entries have been observed in two shapes:
        #   (a) flat {"Sun": {"sign": "Leo"}, ...} (the "expected" shape), or
        #   (b) nested {"factor": 2, "name": "Hora (D2)", "lagna": "Leo",
        #       "lagna_degree": ..., "planets": {"Sun": {"sign": ...}, ...}}
        # Unwrap (b) to its "planets" sub-dict before iterating.
        candidate = d2_chart.get("planets") if isinstance(d2_chart.get("planets"), dict) else d2_chart
        for planet, val in candidate.items():
            if planet in ("Lagna", "lagna", "lagna_degree", "factor", "name", "planets"):
                continue
            sign = val.get("sign") if isinstance(val, dict) else val
            # A genuine D2 Hora sign is ALWAYS either Leo (Sun's Hora) or
            # Cancer (Moon's Hora) -- any other sign value here means the
            # upstream data is not actually a Hora chart (e.g. mislabeled/
            # miscomputed divisional data), so it must NOT be trusted; fall
            # through to the in-house computation below instead.
            if sign in ("Leo", "Cancer"):
                positions[planet] = sign
            elif sign:
                positions = {}
                break
        if positions:
            return positions

    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    if not planets_d1:
        return {}
    from jyotish.astro import compute_d2_hora_chart
    computed = compute_d2_hora_chart(planets_d1)
    return {p: v.get("sign", "") for p, v in computed.items() if v.get("sign") in ("Leo", "Cancer")}


def _d2_native_house_evidence(payload: Any) -> List[Tuple[float, str]]:
    """D2 (Hora) wealth-flow corroboration for the 2nd/11th house lords and
    the classical wealth significators (Jupiter, Venus, Moon).

    Classical basis (Parashara, BPHS ch.6/Phaladeepika's wealth-yoga
    discussion of Hora): a planet placed in the Sun's Hora (Leo half) vs
    the Moon's Hora (Cancer half) of its sign is read as a coarse polarity
    for wealth ACCUMULATION vs EXPENDITURE/instability -- Moon's Hora
    (watery, retentive) is the more commonly cited favorable placement for
    durable wealth, Sun's Hora (fiery, expending) the more cautionary one.
    This is a widely repeated classical heuristic, NOT a precise or
    universally-agreed-upon rule the way D9/D10 house-graph corroboration
    is -- D2 only ever distinguishes two states (Sun-Hora / Moon-Hora) per
    planet, so this function deliberately stays a light corroboration
    layer (small weights) rather than a primary wealth determinant, and is
    scoped ONLY to the houses/planets classically tied to wealth flow
    (H2 capital base, H11 realized gains, Jupiter/Venus/Moon as wealth
    karakas) -- not applied to unrelated houses, mirroring
    _d9_native_house_evidence()/_d10_native_house_evidence()'s structure
    and status-diagnostic conventions but intentionally narrower in scope.

    Gracefully degrades to [] (no evidence, not a penalty) when no D2 data
    is available (upstream or in-house-computable) or no house_lords are
    on the payload.
    """
    positions = _d2_hora_positions_from_payload(payload)
    house_lords = getattr(payload, "house_lords", {}) or {}
    if not positions or not house_lords:
        return []

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    results: List[Tuple[float, str]] = []

    for house_num, label in ((2, "H2 (capital base)"), (11, "H11 (realized gains)")):
        lord = _h(house_num)
        if not lord or lord not in positions:
            continue
        hora = positions[lord]
        if hora == "Cancer":
            results.append((2.5, f"D2-Hora: {label} lord ({lord}) is in Moon's Hora (Cancer half) -> classically favorable for wealth accumulation/retention"))
        else:
            results.append((-2.0, f"D2-Hora: {label} lord ({lord}) is in Sun's Hora (Leo half) -> classical caution for accumulated wealth (expending tendency), a corroborating signal only, not a standalone contradiction"))

    for planet in ("Jupiter", "Venus", "Moon"):
        hora = positions.get(planet)
        if not hora:
            continue
        if hora == "Cancer":
            results.append((1.5, f"D2-Hora: {planet} (wealth significator) is in Moon's Hora (Cancer half) -> supports durable wealth flow"))
        else:
            results.append((-1.0, f"D2-Hora: {planet} (wealth significator) is in Sun's Hora (Leo half) -> mild wealth-flow caution"))

    return results


_HORA_LORD = {"Leo": "Sun", "Cancer": "Moon"}
_HORA_OWN_PLANET = {"Leo": "Sun", "Cancer": "Moon"}


def _d2_hora_deep_evidence(payload: Any) -> Dict[str, Any]:
    """Deeper D2 (Hora) structural read, extending the flat wealth-flow
    corroboration list in `_d2_native_house_evidence()` above (which is
    left unchanged for backward compatibility -- existing callers/tests/
    report sections keep reading `d2_hora_evidence` exactly as before).

    Audit gap (item 5): the flat list only ever classifies individual
    planets into Sun's-Hora/Moon's-Hora and emits one flat polarity note
    per planet -- it never derives a D2 LAGNA, never names the Hora Lagna
    LORD or judges that lord's own D1 dignity, never separately reads the
    condition of Sun and Moon THEMSELVES within D2 (each planet's own
    Hora is trivially "Leo" or "Cancer" so the interesting question is
    whether Sun sits in its OWN Hora (Leo) / Moon in its OWN Hora
    (Cancer), the D2 analogue of dignity for a chart that only ever has
    two possible signs), and collapses earning vs. accumulation vs.
    expenditure into one flat "wealth retention" read.

    This function adds exactly those four things, reusing
    `_d2_hora_positions_from_payload()` (same upstream-preferred/in-house-
    fallback positions used above) and `jyotish.astro.compute_d2_hora_chart`
    for the Lagna (passing `payload.lagna_sign`/`payload.lagna_degree`,
    when available, the same fields d24_d60_sign.py already reads for its
    own in-house divisional Lagna derivation) plus `_rich_planet_dignities`/
    `_dig_name` (the same D1 dignity lookup every other evidence function
    in this module uses) for the Hora Lagna lord's own D1 dignity:

      - d2_lagna_hora: "Leo"/"Cancer" (D2 Lagna's Hora, i.e. the D2 sign
        itself under the 2-sign Parashari Hora scheme), or "" if no
        lagna_sign/lagna_degree is available on the payload (same
        documented no-D2-Lagna limitation `_d2_hora_positions_from_payload`
        already notes for the flat function).
      - hora_lagna_lord: "Sun" or "Moon" (whichever rules the D2 Lagna's
        Hora sign).
      - hora_lagna_lord_d1_dignity: that lord's own D1 dignity tag (reused
        from `_rich_planet_dignities`/`_dig_name`), since a Hora Lagna
        ruled by a well-placed D1 Sun/Moon is read as a stronger overall
        wealth-flow structure than one ruled by an afflicted D1 Sun/Moon.
      - sun_hora / sun_condition, moon_hora / moon_condition: each
        planet's own D2 Hora sign, and whether that is the planet's OWN
        Hora ("OWN_HORA": Sun-in-Leo or Moon-in-Cancer -- the D2 analogue
        of a dignified placement in a 2-sign system) or the other
        luminary's Hora ("OTHER_HORA").
      - h2_lord_hora / h11_lord_hora: the D2 Hora of the D1 2nd-house and
        11th-house lords (same lords `_d2_native_house_evidence` already
        scores), surfaced individually here (rather than only as a signed
        weight) so the three sub-conclusions below can cite them plainly.
      - h2_lord_co_hora_with_lagna / h11_lord_co_hora_with_lagna: True
        when that house lord shares the SAME D2 Hora sign as the D2 Lagna
        itself -- the closest D2-native analogue of a "conjunction with
        the Lagna" relationship this 2-sign chart can express (a genuine
        Bhava/Rashi house-count is not meaningful here since D2 only ever
        has two possible signs total, so a shared Hora sign is the
        strongest connection this varga can show).
      - earning_conclusion: reads the 11th lord (realized gains) Hora +
        Sun's own condition (Sun classically governs active
        income-generating effort) -- a sub-conclusion about ACTIVE
        EARNING capacity, distinct from accumulation.
      - accumulation_conclusion: reads the 2nd lord (capital base) Hora +
        Moon's own condition (Moon classically governs retention/
        reserves) -- a sub-conclusion about whether earned wealth is
        RETAINED/SAVED, distinct from earning capacity.
      - expenditure_conclusion: reads whether BOTH the 2nd and 11th lords
        (when available) sit in Sun's Hora (the classically "expending"
        half) with no Moon's-Hora offset among Sun/Moon/Jupiter/Venus --
        a sub-conclusion specifically about outflow/expenditure pressure,
        kept separate from the accumulation read above so a chart that
        earns well but retains poorly (or vice versa) is not flattened
        into one "wealth retention" verdict.

    Gracefully degrades to {"status": "NO_DATA", ...} (never raises, no
    penalty) when no D2 positions are available at all -- matching this
    module's diagnostic conventions.
    """
    try:
        positions = _d2_hora_positions_from_payload(payload)
        if not positions:
            return {
                "status": "NO_DATA",
                "note": "D2-Hora deep evidence skipped: no upstream or in-house-computable D2 (Hora) chart available for this payload.",
            }

        house_lords = getattr(payload, "house_lords", {}) or {}
        dignities = _rich_planet_dignities(payload)

        def _h(num: int) -> str:
            return house_lords.get(str(num), house_lords.get(num, ""))

        # D2 Lagna, reusing jyotish.astro.compute_d2_hora_chart with
        # payload.lagna_sign/lagna_degree when both are available (the
        # same fields d24_d60_sign.py already reads for its own in-house
        # divisional-Lagna derivation) -- "" (no Lagna finding) otherwise,
        # matching the documented no-D2-Lagna limitation elsewhere in this
        # module when those fields are absent.
        d2_lagna_hora = ""
        lagna_sign = getattr(payload, "lagna_sign", "") or ""
        lagna_degree = getattr(payload, "lagna_degree", None)
        if lagna_sign and lagna_degree is not None:
            from jyotish.astro import compute_d2_hora_chart
            lagna_chart = compute_d2_hora_chart({}, lagna_sign, float(lagna_degree))
            d2_lagna_hora = (lagna_chart.get("Lagna") or {}).get("sign", "") or ""

        hora_lagna_lord = _HORA_LORD.get(d2_lagna_hora, "")
        hora_lagna_lord_d1_dignity = _dig_name(hora_lagna_lord, dignities) if hora_lagna_lord else ""

        sun_hora = positions.get("Sun", "")
        moon_hora = positions.get("Moon", "")
        sun_condition = ("OWN_HORA" if sun_hora == "Leo" else "OTHER_HORA") if sun_hora else ""
        moon_condition = ("OWN_HORA" if moon_hora == "Cancer" else "OTHER_HORA") if moon_hora else ""

        h2_lord = _h(2)
        h11_lord = _h(11)
        h2_lord_hora = positions.get(h2_lord, "") if h2_lord else ""
        h11_lord_hora = positions.get(h11_lord, "") if h11_lord else ""
        h2_lord_co_hora_with_lagna = bool(d2_lagna_hora and h2_lord_hora and h2_lord_hora == d2_lagna_hora)
        h11_lord_co_hora_with_lagna = bool(d2_lagna_hora and h11_lord_hora and h11_lord_hora == d2_lagna_hora)

        # Earning sub-conclusion: 11th lord (realized gains) Hora + Sun's
        # own condition -- active income-generating capacity.
        earning_signals = []
        if h11_lord_hora:
            earning_signals.append(h11_lord_hora == "Cancer")
        if sun_condition:
            earning_signals.append(sun_condition == "OWN_HORA")
        if not earning_signals:
            earning_conclusion = "D2-Hora: insufficient data (no H11 lord or Sun Hora placement) for an earning-capacity sub-conclusion."
        elif all(earning_signals):
            earning_conclusion = f"D2-Hora earning capacity: favorable -- H11 lord ({h11_lord or 'n/a'}) Hora={h11_lord_hora or 'n/a'}, Sun own-Hora={sun_condition == 'OWN_HORA'} -> active income-generating effort well supported."
        elif any(earning_signals):
            earning_conclusion = f"D2-Hora earning capacity: mixed -- H11 lord ({h11_lord or 'n/a'}) Hora={h11_lord_hora or 'n/a'}, Sun own-Hora={sun_condition == 'OWN_HORA'} -> some earning support, not unanimous."
        else:
            earning_conclusion = f"D2-Hora earning capacity: cautionary -- H11 lord ({h11_lord or 'n/a'}) Hora={h11_lord_hora or 'n/a'}, Sun own-Hora={sun_condition == 'OWN_HORA'} -> active income-generating effort not strongly supported by D2."

        # Accumulation sub-conclusion: 2nd lord (capital base) Hora +
        # Moon's own condition -- retention/savings capacity.
        accumulation_signals = []
        if h2_lord_hora:
            accumulation_signals.append(h2_lord_hora == "Cancer")
        if moon_condition:
            accumulation_signals.append(moon_condition == "OWN_HORA")
        if not accumulation_signals:
            accumulation_conclusion = "D2-Hora: insufficient data (no H2 lord or Moon Hora placement) for an accumulation sub-conclusion."
        elif all(accumulation_signals):
            accumulation_conclusion = f"D2-Hora accumulation: favorable -- H2 lord ({h2_lord or 'n/a'}) Hora={h2_lord_hora or 'n/a'}, Moon own-Hora={moon_condition == 'OWN_HORA'} -> earned wealth is retained/saved rather than dissipated."
        elif any(accumulation_signals):
            accumulation_conclusion = f"D2-Hora accumulation: mixed -- H2 lord ({h2_lord or 'n/a'}) Hora={h2_lord_hora or 'n/a'}, Moon own-Hora={moon_condition == 'OWN_HORA'} -> retention support is partial."
        else:
            accumulation_conclusion = f"D2-Hora accumulation: cautionary -- H2 lord ({h2_lord or 'n/a'}) Hora={h2_lord_hora or 'n/a'}, Moon own-Hora={moon_condition == 'OWN_HORA'} -> retention of earned wealth not strongly supported by D2."

        # Expenditure sub-conclusion: kept deliberately separate from
        # accumulation -- reads whether the wealth-lords AND the wealth
        # significators concentrate in Sun's (expending) Hora with no
        # Moon's-Hora offset anywhere among Sun/Moon/Jupiter/Venus.
        expend_planets = {p: positions.get(p, "") for p in ("Sun", "Moon", "Jupiter", "Venus") if positions.get(p)}
        wealth_lord_horas = [h for h in (h2_lord_hora, h11_lord_hora) if h]
        all_checked = list(expend_planets.values()) + wealth_lord_horas
        if not all_checked:
            expenditure_conclusion = "D2-Hora: insufficient data for an expenditure-pressure sub-conclusion."
        elif all(h == "Leo" for h in all_checked):
            expenditure_conclusion = "D2-Hora expenditure pressure: elevated -- every checked wealth-lord/significator (H2/H11 lords, Sun, Moon, Jupiter, Venus, whichever are available) sits in Sun's (expending) Hora with no Moon's-Hora offset -> outflow tendency is the dominant D2 signal for this chart."
        elif any(h == "Leo" for h in all_checked) and any(h == "Cancer" for h in all_checked):
            expenditure_conclusion = "D2-Hora expenditure pressure: mixed -- some wealth-lords/significators sit in Sun's Hora, others in Moon's Hora -> no single dominant outflow/retention pull from D2 alone."
        else:
            expenditure_conclusion = "D2-Hora expenditure pressure: contained -- wealth-lords/significators concentrate in Moon's (retentive) Hora rather than Sun's -> no elevated D2-native outflow signal."

        return {
            "status": "OK",
            "d2_lagna_hora": d2_lagna_hora,
            "hora_lagna_lord": hora_lagna_lord,
            "hora_lagna_lord_d1_dignity": hora_lagna_lord_d1_dignity,
            "sun_hora": sun_hora,
            "sun_condition": sun_condition,
            "moon_hora": moon_hora,
            "moon_condition": moon_condition,
            "h2_lord": h2_lord,
            "h2_lord_hora": h2_lord_hora,
            "h2_lord_co_hora_with_lagna": h2_lord_co_hora_with_lagna,
            "h11_lord": h11_lord,
            "h11_lord_hora": h11_lord_hora,
            "h11_lord_co_hora_with_lagna": h11_lord_co_hora_with_lagna,
            "earning_conclusion": earning_conclusion,
            "accumulation_conclusion": accumulation_conclusion,
            "expenditure_conclusion": expenditure_conclusion,
            "note": (
                "D2-Hora deep structural read: D2 Lagna + Hora Lagna lord's own D1 dignity, "
                "Sun's/Moon's own condition within D2 (own-Hora vs other-Hora), and separate "
                "earning/accumulation/expenditure sub-conclusions -- extends the flat "
                "Sun-Hora/Moon-Hora polarity list in d2_hora_evidence, does not replace it."
            ),
        }
    except Exception as exc:  # pragma: no cover - defensive
        _record_diagnostic("house_evidence._d2_hora_deep_evidence", exc)
        return {
            "status": "ERROR",
            "note": f"D2-Hora deep evidence failed: {exc}",
        }


def _house_from_reference_lord(reference_sign: str, house_num: int) -> str:
    """Lord of the Nth house counted from an arbitrary reference sign
    (Lagna, Chandra Lagna/Moon sign, Surya Lagna/Sun sign, or a varga
    Lagna sign). Generalizes
    Field_Determination.field_methods.common.chandra_lagna_h10_lord (which
    hardcodes Moon+H10) to any reference sign/house pair, since Phaladeepika
    ch.5's profession method and the D9/D10-Lagna precedence check below
    both need the same arithmetic against different reference points.
    """
    from jyotish.constants import _SIGN_LORD, _SIGN_NUM
    if reference_sign not in _SIGN_NUM:
        return ""
    signs = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda x: x[1])]
    return _SIGN_LORD.get(signs[(_SIGN_NUM[reference_sign] - 1 + house_num - 1) % 12], "")

def _phaladeepika_multi_lagna_evidence(payload: Any) -> List[Tuple[float, str]]:
    """Phaladeepika ch.5's profession method, implementing its fuller chain:
    (1) all three references -- Lagna, Moon (Chandra Lagna), Sun (Surya
    Lagna) -- are evaluated, not just Moon/Sun; (2) the STRONGEST reference
    is identified by the strength of the REFERENCE POINT ITSELF (Lagna
    lord's D1 strength for Lagna, Moon's own placement+dignity for Chandra
    Lagna, Sun's own placement+dignity for Surya Lagna) -- not a bucket
    derived from each reference's 10th lord, which conflated "which 10th
    lord looks best" with "which reference is strongest", the two separate
    questions Phaladeepika actually asks in sequence; (3) the strongest
    reference actually has precedence: its 10th-lord finding is scored at
    FULL weight, while the other two references' findings are scored at a
    reduced (secondary-corroboration) weight -- previously all three
    references contributed equally regardless of which one Phaladeepika's
    own comparison step identified as primary; (4) for each reference, the
    Navamsha (D9) sign OCCUPIED by that reference's D1 10th-lord is located
    (via divisional_charts["D9_navamsha"]), and the LORD OF THAT NAVAMSHA
    SIGN's own D1 strength is judged as the classical profession-
    confirmation step.
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    dignities = _rich_planet_dignities(payload)
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    d9_chart = ((getattr(payload, "divisional_charts", {}) or {}).get("D9_navamsha", {}) or {})

    moon_sign = planet_signs.get("Moon", "")
    sun_sign = planet_signs.get("Sun", "")

    # Reference-point-own-strength (not the 10th lord's): Lagna's strength
    # is its own lord's D1 placement strength; Moon/Sun's strength is their
    # own placement+dignity via _planet_strength.
    def _lagna_lord_strength() -> float:
        h1_lord = house_lords.get("1", house_lords.get(1, ""))
        if not h1_lord:
            return 0.0
        return _house_lord_strength(payload, 1)

    ref_own_strength = {
        "Lagna": _lagna_lord_strength() if lagna_sign else 0.0,
        "Moon (Chandra Lagna)": _planet_strength(payload, "Moon") if moon_sign else 0.0,
        "Sun (Surya Lagna)": _planet_strength(payload, "Sun") if sun_sign else 0.0,
    }

    references = (
        ("Lagna", lagna_sign),
        ("Moon (Chandra Lagna)", moon_sign),
        ("Sun (Surya Lagna)", sun_sign),
    )

    # Determine the strongest reference FIRST (Phaladeepika's own ordering:
    # compare the references, then read the 10th from the winner) so its
    # findings can be scored at full weight and the others dampened.
    valid_refs = [(label, ref_own_strength[label]) for label, sign in references if sign]
    strongest_label = max(valid_refs, key=lambda x: x[1])[0] if valid_refs else None

    results: List[Tuple[float, str]] = []

    for label, ref_sign in references:
        if not ref_sign:
            continue
        precedence_factor = 1.0 if label == strongest_label else 0.5
        h10_lord = _house_from_reference_lord(ref_sign, 10)
        if not h10_lord:
            continue
        placed_house = planet_house.get(h10_lord, 0)
        dig = _dig_name(h10_lord, dignities)

        if placed_house in _KT and dig != "DEBILITATED":
            weight = 5 * _dig_factor(h10_lord, dignities) * precedence_factor
            tag = "PRIMARY" if precedence_factor == 1.0 else "secondary"
            results.append((weight, f"Phaladeepika[{tag}]: 10th-from-{label} lord ({h10_lord}) in kendra/trikona, dignity={_dig_disclosure(h10_lord, dignities, payload)} -> livelihood direction confirmed (+{weight:.1f})"))
        elif dig == "DEBILITATED":
            tag = "PRIMARY" if precedence_factor == 1.0 else "secondary"
            # Gap-hunt fix (real-chart-caught, same underlying issue as the
            # Lagnesh Neecha Bhanga check in
            # _lagnesh_affliction_and_karaka_connection_evidence()): this
            # branch used to flatly penalize ANY debilitated 10th-from-
            # reference lord, even when that exact planet's exact
            # debilitation was independently found classically cancelled
            # elsewhere in this same evidence ledger -- producing two
            # contradictory statements about one underlying fact (e.g.
            # "Lagnesh debilitated but Neecha Bhanga applies, not
            # weakened" alongside "10th-from-Moon lord debilitated,
            # livelihood weakened" for the SAME planet's SAME debilitation).
            # Now consults the same cancellation check before penalizing.
            nb = _neecha_bhanga_status(payload, h10_lord)
            if nb.get("cancelled"):
                weight = 2.0 * precedence_factor
                results.append((weight, f"Phaladeepika[{tag}]: 10th-from-{label} lord ({h10_lord}) is DEBILITATED but Neecha Bhanga applies -- {nb.get('reason')} -> livelihood direction NOT weakened, treated as classically cancelled (+{weight:.1f})"))
            else:
                weight = -3.0 * precedence_factor
                results.append((weight, f"Phaladeepika[{tag}]: 10th-from-{label} lord ({h10_lord}) debilitated -> livelihood direction weakened"))

        # Step 4: Navamsha occupied by this 10th-lord, and that Navamsha
        # sign's own lord's D1 strength -- the profession-confirmation step.
        if d9_chart:
            d9_sign = d9_chart.get(h10_lord, "")
            if d9_sign:
                navamsha_lord = _house_from_reference_lord(d9_sign, 1)  # lord of d9_sign itself
                if navamsha_lord and navamsha_lord != h10_lord:
                    nl_house = planet_house.get(navamsha_lord, 0)
                    nl_dig = _dig_name(navamsha_lord, dignities)
                    if nl_house in _KT and nl_dig != "DEBILITATED":
                        results.append((3.0 * precedence_factor, f"Phaladeepika: 10th-from-{label} lord ({h10_lord}) occupies Navamsha {d9_sign}, whose lord ({navamsha_lord}) is well placed in D1 -> profession confirmed by Navamsha lord"))
                    elif nl_dig == "DEBILITATED":
                        nb_nl = _neecha_bhanga_status(payload, navamsha_lord)
                        if nb_nl.get("cancelled"):
                            results.append((1.5 * precedence_factor, f"Phaladeepika: 10th-from-{label} lord ({h10_lord}) occupies Navamsha {d9_sign}, whose lord ({navamsha_lord}) is DEBILITATED but Neecha Bhanga applies -- {nb_nl.get('reason')} -> profession confirmation NOT weakened, treated as classically cancelled"))
                        else:
                            results.append((-2.0 * precedence_factor, f"Phaladeepika: 10th-from-{label} lord ({h10_lord}) occupies Navamsha {d9_sign}, whose lord ({navamsha_lord}) is debilitated in D1 -> profession confirmation weakened"))

    # Strongest-reference flag, now computed from the reference points'
    # OWN strength (not their 10th lords') and with a real precedence
    # effect on the findings above, not just a cosmetic note.
    if strongest_label is not None:
        results.append((0.0, f"Phaladeepika: strongest reference for livelihood direction is {strongest_label} (own strength={ref_own_strength[strongest_label]:.2f}) -- its 10th-lord finding scored at full weight, others at half weight"))

    return results

def _multi_varga_lagna_precedence_evidence(payload: Any) -> List[Tuple[float, str]]:
    """D9-Lagna and D10-Lagna precedence corroboration: beyond checking the
    D1 house-7/11 lords' D9/D10 PLANET dignity (already done elsewhere in
    this module), this checks whether the D9 Lagna's own 7th-house lord and
    the D10 Lagna's own 11th-house lord (i.e. varga-native house lordship,
    computed from each varga's own ascendant rather than mapped back onto
    D1 houses) are themselves well-placed IN D1 -- the standard way a D1
    engine can read varga-lagna-relative strength without a full separate
    D9/D10 house-placement graph. This is a second, independent varga
    cross-check (varga-native lordship) layered on top of the D9/D10
    planet-dignity check already present, not a duplicate of it.
    """
    d9_lagna = getattr(payload, "d9_lagna_sign", "") or ""
    d10_lagna = getattr(payload, "d10_lagna_sign", "") or ""
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    results: List[Tuple[float, str]] = []

    if d9_lagna:
        d9_h7_lord = _house_from_reference_lord(d9_lagna, 7)
        if d9_h7_lord:
            placed = planet_house.get(d9_h7_lord, 0)
            dig = _dig_name(d9_h7_lord, dignities)
            if placed in _KT and dig != "DEBILITATED":
                weight = 4 * _dig_factor(d9_h7_lord, dignities)
                results.append((weight, f"D9-Lagna H7 lord ({d9_h7_lord}) well placed in D1 -> Navamsha-native partnership house corroborates (+{weight:.1f})"))
            elif dig == "DEBILITATED":
                nb = _neecha_bhanga_status(payload, d9_h7_lord)
                if nb.get("cancelled"):
                    results.append((2.0, f"D9-Lagna H7 lord ({d9_h7_lord}) is DEBILITATED but Neecha Bhanga applies -- {nb.get('reason')} -> Navamsha-native partnership house NOT undermined, treated as classically cancelled"))
                else:
                    results.append((-3.0, f"D9-Lagna H7 lord ({d9_h7_lord}) debilitated -> Navamsha-native partnership house undermined"))

    if d10_lagna:
        d10_h11_lord = _house_from_reference_lord(d10_lagna, 11)
        if d10_h11_lord:
            placed = planet_house.get(d10_h11_lord, 0)
            dig = _dig_name(d10_h11_lord, dignities)
            if placed in _KT and dig != "DEBILITATED":
                weight = 4 * _dig_factor(d10_h11_lord, dignities)
                results.append((weight, f"D10-Lagna H11 lord ({d10_h11_lord}) well placed in D1 -> Dashamsha-native gains house corroborates (+{weight:.1f})"))
            elif dig == "DEBILITATED":
                nb = _neecha_bhanga_status(payload, d10_h11_lord)
                if nb.get("cancelled"):
                    results.append((2.0, f"D10-Lagna H11 lord ({d10_h11_lord}) is DEBILITATED but Neecha Bhanga applies -- {nb.get('reason')} -> Dashamsha-native gains house NOT undermined, treated as classically cancelled"))
                else:
                    results.append((-3.0, f"D10-Lagna H11 lord ({d10_h11_lord}) debilitated -> Dashamsha-native gains house undermined"))

    return results

def _d1_tenth_lord_direct_evidence(payload: Any) -> List[Tuple[float, str]]:
    """Direct D1 10th-lord (H10 lord) judgment -- BPHS treats the 10th
    lord's own strength and condition as central to work/status/business
    results, and this module previously only ever loaded h10_lord as a
    downstream input to OTHER checks (H11-in-H10/H7, Phaladeepika 10th-
    from-Moon/Sun, D10-native evidence) without ever judging the D1 10th
    lord's own condition as its own primary evidence source. This adds
    that missing primary check: 10th-lord's own placement strength,
    H7-H10 connection, H10-H11 connection, H2-H10 connection, conjunction
    with natural benefics/malefics, and D9/D10 dignity of the 10th lord
    itself (distinct from the H7/H11/H2-lord D9 checks already present).
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    dignities = _rich_planet_dignities(payload)
    d9_dig = getattr(payload, "d9_planet_dignities", {}) or {}
    d10_dig = getattr(payload, "d10_planet_dignities", {}) or {}
    benefics, malefics = _effective_benefic_malefic_sets(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    h2_lord, h7_lord, h10_lord, h11_lord = _h(2), _h(7), _h(10), _h(11)
    results: List[Tuple[float, str]] = []

    if not h10_lord:
        return results

    # 1. Direct strength of the 10th lord's own D1 placement.
    strength = _house_lord_strength(payload, 10)
    dig10 = _dig_name(h10_lord, dignities)
    if strength >= DECISION_POLICY.house_strength_strong_cutoff:
        weight = 12 * strength
        results.append((weight, f"D1 10th lord ({h10_lord}) directly well placed (strength={strength}) -> livelihood/status foundation is strong (+{weight:.1f})"))
    elif strength < DECISION_POLICY.house_strength_moderate_cutoff:
        results.append((-6.0, f"D1 10th lord ({h10_lord}) directly weak (strength={strength}) -> livelihood/status foundation under-supported"))
    # Audit fix: the strength bucket above has a 0.35-0.6 dead zone that
    # produces ZERO evidence. A debilitated 10th lord placed in a
    # kendra/trikona computes to exactly base(1.0)*dig_factor(0.55)=0.55,
    # which falls in that dead zone -- the debilitation was silently
    # absorbed with no caution recorded, even though rules 6/7 below only
    # check the D9/D10 (varga) dignity, never the D1 dignity itself. This
    # branch is independent of the strength bucket so the D1 debilitation
    # of the 10th lord is never lost, regardless of where it lands.
    if dig10 == "DEBILITATED" and strength >= DECISION_POLICY.house_strength_moderate_cutoff:
        nb10 = _neecha_bhanga_status(payload, h10_lord)
        if nb10.get("cancelled"):
            results.append((1.5, f"D1 10th lord ({h10_lord}) is DEBILITATED but Neecha Bhanga applies -- {nb10.get('reason')} -> livelihood/status foundation NOT dignity-cautioned, treated as classically cancelled"))
        else:
            results.append((-4.0, f"D1 10th lord ({h10_lord}) is DEBILITATED in D1 (placement strength={strength}) -> livelihood/status foundation carries a dignity caution despite house placement"))

    # 2. H7-H10 connection (partnership feeding livelihood).
    #
    # v41 audit fix (#6, user-caught): when h7_lord == h10_lord, this is
    # purely the SAME-LORD structural fact of certain ascendants
    # (Sagittarius/Gemini/Virgo/Pisces etc. always have one planet ruling
    # both 7th and 10th -- an ascendant-inherent condition, not a
    # distinguishing feature of this individual chart) -- yet it was cited
    # at the SAME full weight and with the SAME "partnerships directly
    # feed livelihood" language as a genuine cross-house OCCUPANCY
    # connection (a real, chart-specific fact: the 7th lord actually
    # sitting in the 10th, or vice versa). Same-lord-only is now weighted
    # lower and worded to disclose it's structural background, not an
    # independent yoga; a genuine occupancy connection (present regardless
    # of same-lord-ness) keeps the original full weight and wording.
    _h7_h10_same_lord_only = bool(h7_lord) and h7_lord == h10_lord and _ph(h7_lord) != 10 and _ph(h10_lord) != 7
    _h7_h10_occupancy_connection = bool(h7_lord) and (_ph(h7_lord) == 10 or _ph(h10_lord) == 7)
    if _h7_h10_occupancy_connection:
        results.append((6.0, f"H7-H10 connection (H7 lord {h7_lord} / H10 lord {h10_lord}) -> partnerships directly feed livelihood/venture"))
    elif _h7_h10_same_lord_only:
        results.append((2.5, f"H7/H10 share the same lord ({h7_lord}) -- a structural fact of this ascendant, not a distinguishing cross-house connection for this individual chart; that planet's own dignity/placement still matters, but this is background context, not an independent partnership-feeds-livelihood yoga"))

    # 3. H10-H11 connection (livelihood converting to realized gains).
    if h11_lord and (h11_lord == h10_lord or _ph(h11_lord) == 10 or _ph(h10_lord) == 11):
        results.append((6.0, f"H10-H11 connection (H10 lord {h10_lord} / H11 lord {h11_lord}) -> livelihood converts to realized gains"))

    # 4. H2-H10 connection (livelihood building capital/family resources).
    if h2_lord and (h2_lord == h10_lord or _ph(h2_lord) == 10 or _ph(h10_lord) == 2):
        results.append((5.0, f"H2-H10 connection (H2 lord {h2_lord} / H10 lord {h10_lord}) -> livelihood builds capital base"))

    # 5. 10th lord's conjunctions -- natural benefic/malefic co-tenancy.
    h10_house = _ph(h10_lord)
    if h10_house:
        co_tenants = [p for p, h in planet_house.items() if h == h10_house and p != h10_lord]
        benefic_co = [p for p in co_tenants if p in benefics]
        malefic_co = [p for p in co_tenants if p in malefics]
        if benefic_co and not malefic_co:
            results.append((4.0, f"D1 10th lord ({h10_lord}) conjunct benefic(s) {', '.join(sorted(set(benefic_co)))} -> livelihood supported by benefic association"))
        elif malefic_co and not benefic_co:
            results.append((-3.0, f"D1 10th lord ({h10_lord}) conjunct malefic(s) {', '.join(sorted(set(malefic_co)))} -> livelihood exposed to malefic influence"))

    # 6. 10th lord's OWN D9/D10 dignity (distinct from the H2/H7/H11-lord
    # D9 checks already present elsewhere -- this judges H10's own lord).
    d9 = str(d9_dig.get(h10_lord, "") or "").upper()
    d10 = str(d10_dig.get(h10_lord, "") or "").upper()
    if d9 == "DEBILITATED" and d10 == "DEBILITATED":
        results.append((-6.0, f"D1 10th lord ({h10_lord}) debilitated in BOTH D9 and D10 -> livelihood promise denied by varga corroboration"))
    elif d9 in _STRONG_DIGNITY or d10 in _STRONG_DIGNITY:
        results.append((4.0, f"D1 10th lord ({h10_lord}) strong in D9/D10 -> livelihood promise confirmed by varga corroboration"))
    elif d9 == "DEBILITATED" or d10 == "DEBILITATED":
        results.append((-3.0, f"D1 10th lord ({h10_lord}) debilitated in D9/D10 -> livelihood promise weakened by varga corroboration"))

    return results

def _fifth_house_business_evidence(payload: Any) -> List[Tuple[float, str]]:
    """v17 audit fix: the 5th house had ZERO references anywhere in this
    module despite being central to the independent-professional group
    (1-2-5-9-10-11) and several business-sector combinations (5-10-11
    innovation, 2-5-11 investment/scalable-IP, 5-7 creative commerce). This
    adds the primary 5th-house checks: 5th lord in H10 (strategy/creativity
    becomes profession), 5th lord in H11 (innovation creates gains), a
    2-5-11 three-way connection (investment/IP wealth-building), a 5-7
    connection (creative/advisory commerce), and a GATED 5-8-Rahu
    speculative-risk flag (heavy 5-8-Rahu gives speculative appetite but
    also excessive risk per the spec -- scored as a caution, not a plain
    positive, unlike a naive "Rahu touches 5th" rule would)."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    h2_lord, h5_lord, h7_lord = _h(2), _h(5), _h(7)
    h10_lord, h11_lord = _h(10), _h(11)
    results: List[Tuple[float, str]] = []

    if not h5_lord:
        return results

    dig5 = _dig_name(h5_lord, dignities)
    # Gap-hunt fix: a debilitated-but-classically-cancelled H5 lord in H10/
    # H11 previously earned NO credit at all (silently treated the same as
    # an uncancelled debilitation), while the same planet's same
    # cancellation might already be celebrated elsewhere in this report
    # (e.g. the Lagnesh check). Consulting the cancellation here too keeps
    # this function from being the one place that still under-reads a
    # cancelled debilitation as if it were a live affliction.
    _h5_nb = _neecha_bhanga_status(payload, h5_lord) if dig5 == "DEBILITATED" else {"cancelled": False, "reason": None}
    _h5_ok = dig5 != "DEBILITATED" or _h5_nb.get("cancelled")
    if _ph(h5_lord) == 10 and _h5_ok:
        if dig5 == "DEBILITATED":
            results.append((4.0, f"H5 lord ({h5_lord}) in H10, DEBILITATED but Neecha Bhanga applies -- {_h5_nb.get('reason')} -> strategy/innovation/knowledge still becomes the profession, treated as classically cancelled"))
        else:
            results.append((8.0 * _dig_factor(h5_lord, dignities),
                             f"H5 lord ({h5_lord}) in H10, dignity={dig5} -> strategy/innovation/knowledge becomes the profession"))
    if _ph(h5_lord) == 11 and _h5_ok:
        if dig5 == "DEBILITATED":
            results.append((4.0, f"H5 lord ({h5_lord}) in H11, DEBILITATED but Neecha Bhanga applies -- {_h5_nb.get('reason')} -> innovation/creative intelligence still converts to gains, treated as classically cancelled"))
        else:
            results.append((8.0 * _dig_factor(h5_lord, dignities),
                             f"H5 lord ({h5_lord}) in H11, dignity={dig5} -> innovation/creative intelligence converts to gains"))

    if h2_lord and h11_lord and (h5_lord == h2_lord or h5_lord == h11_lord or _ph(h2_lord) == 5 or _ph(h11_lord) == 5):
        results.append((6.0, "2-5-11 connection -> investment, speculation, or scalable intellectual-property wealth-building"))

    if h7_lord and (h5_lord == h7_lord or _ph(h5_lord) == 7 or _ph(h7_lord) == 5):
        results.append((5.0, f"H5-H7 connection (H5 lord {h5_lord} / H7 lord {h7_lord}) -> creative/advisory commerce, market-facing products"))

    # Speculative-risk caution (5-8-Rahu): NOT a plain positive per the
    # spec's own warning ("heavy 5th-8th-Rahu combinations may give
    # speculative appetite but also excessive risk") -- scored net-negative
    # unless the 5th lord itself is strongly dignified, in which case the
    # risk is judged as MANAGED speculation rather than pure exposure.
    h8_lord = _h(8)
    rahu_h = _ph("Rahu")
    if (h5_lord == h8_lord or _ph(h5_lord) == 8 or _ph(h8_lord) == 5) and rahu_h in (5, 8):
        if dig5 in _STRONG_DIGNITY:
            results.append((2.0, f"5-8-Rahu speculative combination but H5 lord ({h5_lord}) strongly dignified -> managed speculative/venture-capital appetite, not pure exposure"))
        else:
            results.append((-5.0, "5-8-Rahu speculative combination, H5 lord not strongly dignified -> speculative appetite carries excessive, poorly-managed risk"))

    return results


def _lords_connected(house_lords: Dict[str, Any], planet_house: Dict[str, int], a: int, b: int,
                      dignities: Optional[Dict[str, str]] = None) -> bool:
    """Shared relationship test used by _extended_house_combination_evidence:
    houses A and B are "connected" if they share the same lord, or if
    either lord occupies the other house -- the same connection test the
    rest of this module already uses inline (e.g. _d1_tenth_lord_direct_evidence,
    the 2-5-11/H5-H7 checks above), factored out so the new spec
    combinations below don't each re-derive it.

    Dignity gate (bug found via test_maximal_plausible_chart_scores_near_ceiling_not_compressed
    on a degenerate all-houses-same-debilitated-lord fixture): when the
    SAME planet rules both houses (the same-lord case, as opposed to an
    occupancy connection), a debilitated ruler mechanically "connects"
    every house it owns without that meaning anything positive -- a
    single badly afflicted planet ruling many houses is a WEAK chart, not
    one riddled with strong multi-house combinations. Same-lord
    connections are therefore only counted when that shared lord isn't
    DEBILITATED; occupancy-based connections (lord of A sitting in house
    B) are unaffected by this gate since they involve two independently-
    assessed lords, not one afflicted planet manufacturing many "links"."""
    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))
    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)
    lord_a, lord_b = _h(a), _h(b)
    if not lord_a or not lord_b:
        return False
    if lord_a == lord_b:
        dig = str((dignities or {}).get(lord_a, "") or "").upper()
        return dig != "DEBILITATED"
    return bool(_ph(lord_a) == b or _ph(lord_b) == a)


def _extended_house_combination_evidence(payload: Any) -> List[Tuple[float, str]]:
    """v23 audit fix: the spec's section-1 house write-ups and section-9
    twelve-row sector table name a number of specific multi-house
    combinations that, prior to this, were represented only by generic
    single-house-strength proxies (each house scored on its own lord's
    placement, never tested for connection to the SPECIFIC other houses
    the spec names). This adds direct connection tests -- same lord, or
    either lord occupying the other's house -- for the combinations that
    were previously entirely absent, using the shared _lords_connected()
    helper above. Each entry is a genuine relationship test, not another
    strength proxy: it fires only when the named houses are actually
    linked through their lords, matching how _d1_tenth_lord_direct_evidence
    already tests H7-H10/H2-H10/H10-H11 elsewhere in this file.

    Scope note: this covers the combinations that are cleanly expressible
    as pairwise/three-way lord connections (spec sections 1 and 9). It
    does NOT attempt the sign/nakshatra/aspect-level detail the spec's
    prose additionally describes for each house (e.g. "Mercury/Jupiter
    influence on H5", combustion, planetary war) -- those remain a
    separate, larger undertaking documented as open scope in
    EVIDENCE_BASIS, not silently claimed as done here.
    """
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    def _conn(a: int, b: int) -> bool:
        return _lords_connected(house_lords, planet_house, a, b, dignities=dignities)

    results: List[Tuple[float, str]] = []
    h1_lord, h2_lord, h3_lord = _h(1), _h(2), _h(3)
    h4_lord, h5_lord, h6_lord, h7_lord = _h(4), _h(5), _h(6), _h(7)
    h8_lord, h9_lord = _h(8), _h(9)
    h10_lord, h11_lord, h12_lord = _h(10), _h(11), _h(12)

    # ── Section 1, 2nd house: "2nd lord connected with 7th, 10th or 11th
    # lord" -- H2-H7 and H2-H10 already exist elsewhere (mode_gate.py); H2-H11
    # and H2-H8 (joint capital/loans/investor money/insurance) were absent.
    if h2_lord and h11_lord and _conn(2, 11):
        results.append((6.0, f"2-11 connection (H2 lord {h2_lord} / H11 lord {h11_lord}) -> income accumulates into profit"))
    if h2_lord and h8_lord and _conn(2, 8):
        results.append((3.0, f"2-8 connection (H2 lord {h2_lord} / H8 lord {h8_lord}) -> joint capital, loans, investor money, insurance, or family assets"))

    # ── Section 1, 3rd house: "3rd lord connected with 7th, 10th and
    # 11th", "10th lord in the 3rd", "Lagnesh connected with the 3rd lord".
    if h3_lord and h7_lord and _conn(3, 7):
        results.append((5.0, f"3-7 connection (H3 lord {h3_lord} / H7 lord {h7_lord}) -> enterprise/initiative meets the commercial interface"))
    if h3_lord and h11_lord and _conn(3, 11):
        results.append((5.0, f"3-11 connection (H3 lord {h3_lord} / H11 lord {h11_lord}) -> self-effort converts to gains"))
    if h10_lord and _ph(h10_lord) == 3:
        results.append((6.0, f"10th lord ({h10_lord}) in H3 -> profession is directly built on self-driven initiative/sales"))
    if h1_lord and h3_lord and _conn(1, 3):
        results.append((5.0, f"Lagnesh ({h1_lord}) connected with H3 lord ({h3_lord}) -> entrepreneurial agency reinforced by initiative/risk-taking"))

    # ── Section 1, 4th house: "4th-8th: inherited property, mortgages or
    # redevelopment" (previously entirely absent per audit), plus
    # 4-10-11/4-7/4-12.
    if h4_lord and h8_lord and _conn(4, 8):
        results.append((4.0, f"4-8 connection (H4 lord {h4_lord} / H8 lord {h8_lord}) -> inherited property, mortgage-leveraged, or redevelopment-based asset business"))
    if h4_lord and h10_lord and h11_lord and (_conn(4, 10) and _conn(4, 11)):
        results.append((6.0, f"4-10-11 connection (H4 lord {h4_lord}) -> asset-based profession (real estate/vehicles/materials) with commercial gains"))
    if h4_lord and h7_lord and _conn(4, 7):
        results.append((4.0, f"4-7 connection (H4 lord {h4_lord} / H7 lord {h7_lord}) -> real-estate dealing, vehicles, hospitality, or domestic trade"))
    if h4_lord and h12_lord and _conn(4, 12):
        results.append((3.0, f"4-12 connection (H4 lord {h4_lord} / H12 lord {h12_lord}) -> hotels, resorts, foreign property, or institutional premises"))

    # ── Section 1, 9th house: "9-10: knowledge/dharma becomes profession",
    # "9-11: institutional networks and large gains", "2-9-10: advisory,
    # legal, teaching, or financial knowledge monetisation".
    if h9_lord and h10_lord and _conn(9, 10):
        results.append((5.0, f"9-10 connection (H9 lord {h9_lord} / H10 lord {h10_lord}) -> knowledge/dharma/higher-learning becomes the profession"))
    if h9_lord and h11_lord and _conn(9, 11):
        results.append((5.0, f"9-11 connection (H9 lord {h9_lord} / H11 lord {h11_lord}) -> institutional networks and large gains"))
    if h2_lord and h9_lord and h10_lord and (_conn(2, 9) and _conn(9, 10)):
        results.append((5.0, f"2-9-10 connection (H2/H9/H10 lords {h2_lord}/{h9_lord}/{h10_lord}) -> advisory, legal, teaching, or financial-knowledge monetisation"))

    # ── Section 9 sector-combination rows not otherwise covered as direct
    # tests elsewhere: 3-7-11, 3-10-11, 8-10-11, 9-10-11, 4-7-12. Each
    # fires only when ALL the named houses are mutually connected through
    # their lords -- not merely each house being independently strong --
    # so these are genuine multi-lord relationship tests, matching the
    # spec's "these combinations should generate candidate business
    # families" framing (contributes to business_promise's structural
    # evidence; does not itself reclassify the winning sector).
    if h3_lord and h7_lord and h11_lord and _conn(3, 7) and _conn(7, 11):
        results.append((5.0, "3-7-11 connection -> sales, distribution, marketing, or e-commerce orientation"))
    if h3_lord and h10_lord and h11_lord and _conn(3, 10) and _conn(10, 11):
        results.append((5.0, "3-10-11 connection -> self-made professional expansion / start-up orientation"))
    if h8_lord and h10_lord and h11_lord and _conn(8, 10) and _conn(10, 11):
        results.append((4.0, "8-10-11 connection -> insurance, taxation, audit, research, or restructuring orientation"))
    if h9_lord and h10_lord and h11_lord and _conn(9, 10) and _conn(10, 11):
        results.append((4.0, "9-10-11 connection -> law, consulting, education, publishing, or institutional-enterprise orientation"))
    if h4_lord and h7_lord and h12_lord and _conn(4, 7) and _conn(7, 12):
        results.append((3.0, "4-7-12 connection -> hotels, resorts, property, or hospitality orientation"))

    # v27 audit fix: the remaining 6 of the 12 spec section-9 sector-table
    # rows that had no direct connection test at all (2-7-11, 5-10-11,
    # 5-8-11, 6-7-10-11, 7-9-12, 3-7-10-12) -- previously only the 6 rows
    # above (3-7-11/3-10-11/8-10-11/9-10-11/4-7-12, plus 4-10-11 elsewhere
    # in this function) had been implemented; these close the table. Same
    # pairwise-lord-connection methodology as above.
    if h2_lord and h7_lord and h11_lord and _conn(2, 7) and _conn(7, 11):
        results.append((5.0, "2-7-11 connection -> trade, retail, or commercial-income orientation"))
    if h5_lord and h10_lord and h11_lord and _conn(5, 10) and _conn(10, 11):
        results.append((5.0, "5-10-11 connection -> innovation, education, advisory, or creative/IP orientation"))
    if h5_lord and h8_lord and h11_lord and _conn(5, 8) and _conn(8, 11):
        results.append((4.0, "5-8-11 connection -> markets, venture finance, or speculative-capital orientation"))
    if h6_lord and h7_lord and h10_lord and h11_lord and _conn(6, 7) and _conn(7, 10) and _conn(10, 11):
        results.append((5.0, "6-7-10-11 connection -> service business, outsourcing, operations, or consulting-firm orientation"))
    if h7_lord and h9_lord and h12_lord and _conn(7, 9) and _conn(9, 12):
        results.append((4.0, "7-9-12 connection -> international trade, global consulting, or foreign-client orientation"))
    if h3_lord and h7_lord and h10_lord and h12_lord and _conn(3, 7) and _conn(7, 10) and _conn(10, 12):
        results.append((4.0, "3-7-10-12 connection -> digital exports, remote services, or overseas-commerce orientation"))

    return results


def _lagnesh_affliction_and_karaka_connection_evidence(payload: Any) -> List[Tuple[float, str]]:
    """v24 audit fix: spec section 1's 1st-house write-up names two checks
    that had no matching code anywhere in the module: (a) "whether Lagnesh
    is heavily combust, debilitated, defeated, or afflicted" -- debilitation
    was already gated elsewhere (e.g. mode_gate.py's H1-lord-in-H1/H10
    rule), but COMBUSTION specifically was never read at all, despite
    payload.combust_planets being a real, populated field (see
    jyotish/payload.py); and (b) "Lagnesh connected with Mercury, Mars,
    Sun or Rahu" -- a specific karaka-conjunction/mutual-placement test
    distinct from the house-lord-to-house-lord connections tested
    elsewhere in this file.

    v25 audit fix: (c) "defeated" (graha yuddha / planetary war) -- this
    engine's own v24 docstring had deferred it as requiring longitude
    comparison "left as documented open scope"; on closer look the repo
    ALREADY HAS a tested, real longitude-based implementation
    (jyotish.dignity.graha_yuddha, reading payload.planet_longitudes,
    same field this module already treats as authoritative elsewhere) --
    reused directly rather than re-derived, consistent with this module's
    own stated policy of reusing existing primitives instead of
    re-deriving them (see the file header's Layer 3 note).

    v30 audit fix: the v24 claim that "debilitation was already gated
    elsewhere" was only TRUE for a narrow case -- mode_gate.py's
    independent-mode scoring only reads Lagnesh dignity when the lord
    physically occupies H1 or H10. A debilitated Lagnesh sitting anywhere
    else was numerically discounted (via _house_lord_strength(payload, 1)
    inside sector_score()'s agency_1st_3rd layer) but never cited as
    evidence anywhere a reader could see. This function now also emits an
    unconditional debilitation citation (independent of house placement),
    closing that specific gap without duplicating the combustion check
    above or the placement-conditional independent-mode score already in
    mode_gate.py."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = _rich_planet_dignities(payload)
    combust_planets = set(getattr(payload, "combust_planets", []) or [])
    planet_longitudes = getattr(payload, "planet_longitudes", {}) or {}

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    results: List[Tuple[float, str]] = []
    h1_lord = _h(1)
    if not h1_lord:
        return results

    # (a) Combustion -- distinct from debilitation (already handled
    # elsewhere): a combust Lagnesh loses independent visibility/agency
    # even if otherwise well-dignified, so this fires regardless of the
    # lord's own dignity.
    if h1_lord in combust_planets:
        results.append((-6.0, f"Lagnesh ({h1_lord}) is COMBUST (too close to the Sun) -> entrepreneurial agency/visibility undermined regardless of underlying dignity"))

    dig1 = str(dignities.get(h1_lord, "") or "").upper()

    # v30 audit fix: "already handled elsewhere" (comment above, and this
    # function's original v24 docstring) turned out to mean ONLY
    # mode_gate.py's `if h1_lord and _ph(h1_lord) in {1, 10}` branch --
    # which scores Lagnesh dignity solely for the independent_score, and
    # ONLY when Lagnesh physically occupies H1 or H10. A debilitated
    # Lagnesh sitting in any OTHER house (e.g. H2, H5, H8...) was never
    # cited anywhere in the significators evidence ledger at all, even
    # though its debilitation was already being silently discounted via
    # _house_lord_strength(payload, 1) inside sector_score()'s
    # agency_1st_3rd layer -- the score moved, but no reader-facing
    # evidence entry explained why. Spec section 1 names Lagnesh
    # debilitation as an unconditional check ("whether Lagnesh is heavily
    # combust, debilitated, defeated or afflicted"), not one gated on
    # where the lord happens to sit. This closes that citation gap
    # directly -- weighted lighter than combustion (-6.0) since a
    # debilitated-but-otherwise-placed Lagnesh is a narrower caution than
    # active combustion, and skipped when combustion already fired above
    # to avoid double-citing the same underlying weakness twice.
    if dig1 == "DEBILITATED" and h1_lord not in combust_planets:
        nb = _neecha_bhanga_status(payload, h1_lord)
        if nb.get("cancelled"):
            results.append((2.5, f"Lagnesh ({h1_lord}) is DEBILITATED but Neecha Bhanga (debilitation-cancellation) applies -- {nb.get('reason')} -> entrepreneurial agency is NOT structurally weakened by this debilitation; treat as classically strengthened"))
        else:
            results.append((-4.0, f"Lagnesh ({h1_lord}) is DEBILITATED -> entrepreneurial agency/independent decision-making is structurally weakened regardless of house placement; a strong 7th/10th/11th on its own should not be read as full entrepreneurship for this chart"))

    _, malefics = _effective_benefic_malefic_sets(payload)
    lagnesh_house = _ph(h1_lord)
    co_tenants = [p for p, h in planet_house.items() if h == lagnesh_house and p != h1_lord] if lagnesh_house else []
    afflicting_malefics = [p for p in co_tenants if p in malefics]
    if afflicting_malefics and dig1 != "DEBILITATED":
        results.append((-3.0, f"Lagnesh ({h1_lord}) afflicted by malefic co-tenant(s) {', '.join(sorted(afflicting_malefics))} in H{lagnesh_house} -> entrepreneurial agency strained"))

    # (c) v25 addition: "defeated" = graha yuddha (planetary war). Reuses
    # jyotish.dignity.graha_yuddha rather than re-deriving the longitude
    # comparison -- flags Lagnesh specifically as winner or loser when
    # it's a war participant (only Mars/Mercury/Jupiter/Venus/Saturn are
    # eligible per that function's _YUDDHA_ELIGIBLE set; Sun/Moon/Rahu/Ketu
    # never participate, so a Lagnesh ruled by those never fires here).
    if planet_longitudes:
        yuddha = _jyotish_graha_yuddha(planet_longitudes)
        for war in yuddha.get("wars", []):
            if h1_lord == war["loser"]:
                results.append((-5.0, f"Lagnesh ({h1_lord}) DEFEATED in graha yuddha (planetary war) against {war['winner']} (separation={war['separation_degrees']}°) -> agency/self-direction significantly weakened"))
            elif h1_lord == war["winner"]:
                results.append((2.0, f"Lagnesh ({h1_lord}) WINS graha yuddha (planetary war) against {war['loser']} (separation={war['separation_degrees']}°) -> agency reinforced, though this is an advisory/contested classical rule, not treated as strongly as a clean dignity"))

    # (b) "Lagnesh connected with Mercury, Mars, Sun or Rahu" -- the spec
    # names these four specifically (commercial intellect/Mercury,
    # initiative/Mars, authority/Sun, unconventional drive/Rahu) as
    # karakas that, when linked to Lagnesh via conjunction or mutual
    # placement, reinforce entrepreneurial agency. Distinct from the
    # house-lord-to-house-lord tests in _extended_house_combination_evidence.
    for karaka, label in (("Mercury", "commercial intellect"), ("Mars", "initiative/drive"), ("Sun", "authority/visibility"), ("Rahu", "unconventional ambition")):
        if karaka == h1_lord:
            continue  # Lagnesh IS this karaka -- not a separate "connection"
        karaka_h = _ph(karaka)
        if not karaka_h or not lagnesh_house:
            continue
        conjunct = karaka_h == lagnesh_house
        karaka_in_lagna = karaka_h == 1
        if conjunct or karaka_in_lagna:
            karaka_dig = str(dignities.get(karaka, "") or "").upper()
            if karaka_dig != "DEBILITATED":
                results.append((3.0, f"Lagnesh ({h1_lord}) connected with {karaka} ({label}) -> entrepreneurial agency reinforced"))
            else:
                karaka_nb = _neecha_bhanga_status(payload, karaka)
                if karaka_nb.get("cancelled"):
                    results.append((1.5, f"Lagnesh ({h1_lord}) connected with {karaka} ({label}), DEBILITATED but Neecha Bhanga applies -- {karaka_nb.get('reason')} -> entrepreneurial agency still reinforced, treated as classically cancelled"))

    return results


def _business_significator_graha_yuddha_evidence(payload: Any) -> List[Tuple[float, str]]:
    """GYUDDHA-1 fix (gap audit): _lagnesh_affliction_and_karaka_connection_
    evidence() already reused jyotish.dignity.graha_yuddha() for the 1st
    lord ONLY. The 2nd/6th/7th/10th/11th house lords (wealth, service/
    competition, partnership, career/status, gains) and Mercury (the
    primary trade/commerce karaka in every classical business reading,
    checked here even when it does not happen to hold one of those five
    lordships) were never checked for planetary war at all -- meaning a
    combat-losing planet in a business-critical role went completely
    undetected. This closes that gap directly, mirroring the Lagnesh
    check's exact call pattern to graha_yuddha() (same eligibility rule:
    only Mars/Mercury/Jupiter/Venus/Saturn ever participate; Sun/Moon/
    Rahu/Ketu never do, so a 2/6/7/10/11 lord that happens to be one of
    those four never fires here, same as the Lagnesh case).

    Additive/backward compatible: this is a new, separate evidence
    function (does not replace or duplicate the Lagnesh-only check), and
    is also consumed by _planet_strength()/_planet_strength_fine() via
    _graha_yuddha_loss_factor() so the numeric strength score for these
    planets is genuinely reduced, not just cited here in isolation.

    Graceful degradation: if payload.planet_longitudes is missing/empty,
    this returns [] silently (no error) -- the overwhelmingly normal case
    for most charts is simply "no war in progress" (graha_yuddha requires
    two eligible planets within ~1 degree of each other in the same
    sign), which is indistinguishable from "couldn't check" at this
    call site and is deliberately treated the same way (no citation),
    per this module's existing missing-data convention elsewhere (D2/D7/
    D9 native-evidence helpers all no-op rather than penalize)."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_longitudes = getattr(payload, "planet_longitudes", {}) or {}
    if not planet_longitudes:
        return []

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    # Business-relevant lordships: 2nd (wealth/accumulation), 6th (service/
    # competition/debt), 7th (partnership/trade), 10th (career/status/
    # authority), 11th (gains/networks) -- plus Mercury specifically as
    # the primary trade/commerce karaka, checked unconditionally since
    # commerce signification does not require it to hold a lordship.
    candidates: Dict[str, str] = {}
    for house_num, label in ((2, "wealth/accumulation"), (6, "service/competition"), (7, "partnership/trade"), (10, "career/authority"), (11, "gains/networks")):
        lord = _h(house_num)
        if lord:
            candidates.setdefault(lord, f"H{house_num} lord ({label})")
    candidates.setdefault("Mercury", "primary trade/commerce karaka")

    try:
        yuddha = _jyotish_graha_yuddha(dict(planet_longitudes))
    except Exception as exc:
        _record_diagnostic("house_evidence._graha_yuddha_evidence", exc)
        return []  # graceful degradation -- never raise from an evidence helper

    results: List[Tuple[float, str]] = []
    for planet, role in candidates.items():
        for war in yuddha.get("wars", []) or []:
            if war.get("loser") == planet:
                results.append((-5.0, f"{planet} ({role}) DEFEATED in graha yuddha (planetary war) against {war['winner']} (separation={war.get('separation_degrees')}°) -> this business-critical significator's effective strength/dignity is meaningfully weakened, not just its Lagnesh-agency reading"))
            elif war.get("winner") == planet:
                results.append((2.0, f"{planet} ({role}) WINS graha yuddha (planetary war) against {war.get('loser')} (separation={war.get('separation_degrees')}°) -> significator reinforced, though this is an advisory/contested classical rule"))

    return results


# v-audit fix (astrological completeness -- "No unified D1-D9-D10
# dispositor-chain subsystem"): a genuine multi-hop dispositor chain, not
# just the one-hop dispositor check already present elsewhere (see
# d24_d60_sign.py's _d24_full_analysis, item (5), which explicitly disclaims
# multi-hop chains as out of scope). Following WHICH SIGN/HOUSE a planet
# occupies and WHO rules it is purely mechanical house-graph arithmetic
# (house_lords already gives the same information the other direction) --
# not a matter of astrological interpretation controversy the way VRY
# cancellation conditions or Jaimini karaka disputes are, so this is safe to
# implement without needing to verify a specific classical citation for the
# MECHANISM. What IS an engineered choice (disclosed below, same as every
# other rule in this package) is the WEIGHT assigned to each chain outcome.
#
# _dispositor_chain_walk() below is the single shared core, used by the D1,
# D9, and D10 wrapper functions further down -- each supplies its own
# (occupancy, house-lordship) data source (D1: house_lords + planet_house +
# lagna_sign, via sign arithmetic; D9: derived from
# _d9_house_occupancy_from_divisional_charts' resolved lagna + the same
# sign arithmetic; D10: payload.d10_house_lords/d10_house_occupancy
# directly, already house-indexed, no sign arithmetic needed), so there is
# exactly one walk/classification implementation instead of three
# independently-maintained copies that could silently drift apart. Scoped
# to H7 and H10 lords only (the two most central business significators
# already judged directly elsewhere in this package) in each varga, bounded
# to a maximum of 4 hops to guarantee termination even if this repo's
# lordship data ever contained a cycle that would otherwise loop forever.
_DISPOSITOR_CHAIN_MAX_HOPS = 4


def _dispositor_chain_walk(
    start_planet: str,
    dispositor_of: "Callable[[str], str]",
    dig_of: "Callable[[str], str]",
    max_hops: int = _DISPOSITOR_CHAIN_MAX_HOPS,
) -> Optional[Tuple[str, List[str], bool]]:
    """Shared walk/classification core for the D1/D9/D10 dispositor-chain
    wrappers below. `dispositor_of(planet)` must return the ruling planet of
    whatever sign/house-graph position `planet` occupies in the varga being
    analyzed (or "" if unresolvable); `dig_of(planet)` returns that planet's
    dignity string in the same varga.

    Returns None if the starting planet is already in its own sign/house
    (0 hops -- not this subsystem's concern, already covered by each
    varga's existing "well placed"/dignity checks elsewhere in this
    package). Otherwise returns (outcome, chain, chain_has_debilitated)
    where outcome is one of GROUNDED / EXCHANGE / LOOP /
    UNRESOLVED_MAX_HOPS / UNRESOLVED_NO_DATA -- see
    _d1_dispositor_chain_evidence's docstring for what each means; identical
    semantics apply to D9/D10."""
    first_dispositor = dispositor_of(start_planet)
    if not first_dispositor or first_dispositor == start_planet:
        return None

    chain = [start_planet]
    current = start_planet
    chain_has_debilitated = dig_of(start_planet) == "DEBILITATED"
    outcome = None
    for _hop in range(1, max_hops + 1):
        nxt = dispositor_of(current)
        if not nxt:
            outcome = "UNRESOLVED_NO_DATA"
            break
        chain.append(nxt)
        if dig_of(nxt) == "DEBILITATED":
            chain_has_debilitated = True
        if nxt == current:
            outcome = "GROUNDED"
            break
        if nxt in chain[:-1]:
            outcome = "EXCHANGE" if len(chain) == 3 and chain[0] == chain[2] else "LOOP"
            break
        own_sign_dispositor = dispositor_of(nxt)
        if own_sign_dispositor == nxt:
            chain.append(nxt)
            outcome = "GROUNDED"
            break
        current = nxt
    else:
        outcome = "UNRESOLVED_MAX_HOPS"

    return outcome, chain, chain_has_debilitated


def _format_dispositor_chain_finding(
    varga_label: str,
    role: str,
    start_planet: str,
    outcome: str,
    chain: List[str],
    chain_has_debilitated: bool,
    dig_of: "Callable[[str], str]",
    max_hops: int = _DISPOSITOR_CHAIN_MAX_HOPS,
) -> Tuple[float, str]:
    """Shared note/weight formatter for the D1/D9/D10 wrappers -- identical
    weight scheme and wording pattern across all three vargas, just with
    the varga name substituted, so the same finding in D1 vs D9 vs D10 is
    directly comparable rather than independently-worded."""
    chain_str = " -> ".join(chain)
    if outcome == "EXCHANGE":
        return (4.0, f"{varga_label} dispositor chain: {role} ({start_planet}) forms a mutual dispositor exchange (parivartana) with {chain[1]} ({chain_str}) -> genuine classical strengthening configuration, not a borrowed-strength weakness")
    if outcome == "GROUNDED" and chain_has_debilitated:
        return (-2.0, f"{varga_label} dispositor chain: {role} ({start_planet}) ultimately grounds in {chain[-1]}'s own sign/house ({chain_str}), but the chain passes through a DEBILITATED planet along the way -> foundation is grounded but compromised")
    if outcome == "GROUNDED":
        grounding_dig = dig_of(chain[-1])
        if grounding_dig in _STRONG_DIGNITY:
            return (3.0, f"{varga_label} dispositor chain: {role} ({start_planet}) grounds in {chain[-1]}, itself strongly dignified ({grounding_dig}) in its own sign/house ({chain_str}) -> solid foundation, not borrowed strength")
        return (1.0, f"{varga_label} dispositor chain: {role} ({start_planet}) grounds in {chain[-1]}'s own sign/house ({chain_str}) -> foundation resolved, though the grounding planet itself is only neutrally dignified")
    if outcome == "LOOP" and chain_has_debilitated:
        return (-2.5, f"{varga_label} dispositor chain: {role} ({start_planet}) forms a closed dispositor loop ({chain_str}) that includes a DEBILITATED planet -> mutually-dependent placements with a weak link, foundation compromised")
    if chain_has_debilitated:
        return (-1.5, f"{varga_label} dispositor chain: {role} ({start_planet})'s dispositor chain ({chain_str}) passes through a DEBILITATED planet before resolving -> foundation partially compromised")
    if outcome == "LOOP":
        return (0.5, f"{varga_label} dispositor chain: {role} ({start_planet}) forms a closed dispositor loop ({chain_str}) -> mutually-dependent placements, foundation never grounds independently but no debilitated link found")
    # UNRESOLVED_MAX_HOPS / UNRESOLVED_NO_DATA
    return (0.5, f"{varga_label} dispositor chain: {role} ({start_planet})'s dispositor chain ({chain_str}) did not resolve to a clean own-sign/house grounding or exchange within {max_hops} hops -> foundation inconclusive, not claimed weak")


def _d1_dispositor_chain_evidence(payload: Any) -> List[Tuple[float, str]]:
    """Multi-hop D1 dispositor chain for the H7 and H10 lords: does this
    planet's placement rest on a strong foundation (the chain of sign-lords
    it depends on), or a weak/borrowed one?

    For a starting planet P in house H: P occupies sign S = house_sign(H).
    S's ruling planet (P's dispositor) is D = sign_lord(S). If D == P, the
    planet is in its OWN sign -- the strongest possible case, terminates
    immediately (0 hops) and is NOT reported here (already covered by this
    package's existing "well placed"/dignity checks elsewhere -- this
    function is specifically about BORROWED strength through a chain of
    OTHER planets, not restating own-sign placement).

    Otherwise, follow D's own placement the same way, up to
    _DISPOSITOR_CHAIN_MAX_HOPS hops, until one of:
      - the chain reaches a planet in its own sign (GROUNDED) -- the
        starting planet's strength ultimately rests on a self-sufficient
        foundation, weighted by how strongly-dignified that grounding
        planet is;
      - the chain forms a mutual 2-planet exchange (dispositor of the
        dispositor is the original planet, i.e. two planets sit in each
        other's signs) -- a genuine parivartana (dispositor exchange),
        already a recognized classical strengthening configuration in its
        own right, reported as a distinct, positive finding;
      - a debilitated planet appears anywhere in the chain -- flagged as a
        risk regardless of where it occurs, since a chain is only as
        strong as its weakest dependency;
      - the max-hop bound is reached with none of the above -- reported as
        an inconclusive long chain (small, deliberately modest weight; this
        is explicitly NOT claiming the placement is weak, only that its
        foundation could not be resolved within a bounded, terminating
        search).

    Gracefully returns [] when payload lacks house_lords/planet_house/
    lagna_sign/dignities data (same NO_DATA-safe pattern as every other
    evidence helper in this module)."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    dignities = _rich_planet_dignities(payload)
    if not house_lords or not planet_house or not lagna_sign:
        return []

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _dispositor_of(planet: str) -> str:
        house = planet_house.get(planet)
        if not house:
            return ""
        sign = _house_sign(lagna_sign, house)
        if not sign:
            return ""
        return _JYOTISH_SIGN_LORD.get(sign, "")

    def _dig(planet: str) -> str:
        return str(dignities.get(planet, "") or "").upper()

    results: List[Tuple[float, str]] = []
    for start_house, role in ((7, "H7 lord"), (10, "H10 lord")):
        start_planet = _h(start_house)
        if not start_planet or start_planet not in planet_house:
            continue
        walk = _dispositor_chain_walk(start_planet, _dispositor_of, _dig)
        if walk is None:
            continue
        outcome, chain, chain_has_debilitated = walk
        results.append(_format_dispositor_chain_finding("D1", role, start_planet, outcome, chain, chain_has_debilitated, _dig))

    return results


def _d9_dispositor_chain_evidence(payload: Any) -> List[Tuple[float, str]]:
    """D9 (Navamsha) analog of _d1_dispositor_chain_evidence -- same
    mechanism and weight scheme, applied to D9's own house-graph (native
    D9 occupancy + D9-Lagna-derived house lordship) instead of D1's.

    Reuses _d9_house_occupancy_from_divisional_charts() for occupancy (the
    same resolved D9 lagna it returns is used for BOTH occupancy and
    lordship math, so the two can never be computed against two different
    ascendants -- see that function's own docstring for why that guarantee
    matters). D9 house lordship is derived the same way D24's
    engine_io.py already derives D24 house lordship from a resolved lagna
    sign: lord of D9-house H = sign_lord(house_sign(d9_lagna, H)).

    Gracefully returns [] when D9 occupancy data isn't available (most
    charts in this repo do not currently have divisional_charts["D9_navamsha"]
    populated for every input path)."""
    d9_lagna, occupancy = _d9_house_occupancy_from_divisional_charts(payload)
    if not d9_lagna or not occupancy:
        return []
    dignities = getattr(payload, "d9_planet_dignities", {}) or {}

    planet_house_d9: Dict[str, int] = {}
    for house_num, planets in occupancy.items():
        for p in planets:
            planet_house_d9[p] = house_num

    def _dispositor_of(planet: str) -> str:
        house = planet_house_d9.get(planet)
        return _house_from_reference_lord(d9_lagna, house) if house else ""

    def _dig(planet: str) -> str:
        return str(dignities.get(planet, "") or "").upper()

    house_lords_d1 = getattr(payload, "house_lords", {}) or {}

    def _h1(num: int) -> str:
        return house_lords_d1.get(str(num), house_lords_d1.get(num, ""))

    results: List[Tuple[float, str]] = []
    for start_house, role in ((7, "H7 lord"), (10, "H10 lord")):
        # The D1 H7/H10 lord is still the significator being judged --
        # D9 only supplies the house-graph/lordship data the chain walks
        # through, mirroring how _d9_native_house_evidence judges D1
        # significators' placement within D9's OWN house graph rather than
        # judging "whoever happens to rule D9's 7th/10th house" (a
        # different, D9-Lagna-centric question this function is not
        # asking).
        start_planet = _h1(start_house)
        if not start_planet or start_planet not in planet_house_d9:
            continue
        walk = _dispositor_chain_walk(start_planet, _dispositor_of, _dig)
        if walk is None:
            continue
        outcome, chain, chain_has_debilitated = walk
        results.append(_format_dispositor_chain_finding("D9", role, start_planet, outcome, chain, chain_has_debilitated, _dig))

    return results


def _d10_dispositor_chain_evidence(payload: Any) -> List[Tuple[float, str]]:
    """D10 (Dashamsha) analog of _d1_dispositor_chain_evidence -- same
    mechanism and weight scheme, applied to D10's own house-graph. Unlike
    D9, D10 house lordship does not need to be derived from sign
    arithmetic: payload.d10_house_lords already maps D10-house-number ->
    ruling planet directly (the same source _d10_native_house_evidence
    already reads), and payload.d10_house_occupancy maps D10-house-number ->
    occupying planets. Gracefully returns [] when either is unavailable."""
    house_lords_d10 = getattr(payload, "d10_house_lords", {}) or {}
    occupancy_d10 = getattr(payload, "d10_house_occupancy", {}) or {}
    if not house_lords_d10 or not occupancy_d10:
        return []
    dignities = getattr(payload, "d10_planet_dignities", {}) or {}

    planet_house_d10: Dict[str, int] = {}
    for house_key, planets in occupancy_d10.items():
        try:
            house_num = int(house_key)
        except (TypeError, ValueError):
            continue
        for p in planets or []:
            planet_house_d10[p] = house_num

    def _house_lord_d10(house_num: int) -> str:
        return house_lords_d10.get(str(house_num), house_lords_d10.get(house_num, ""))

    def _dispositor_of(planet: str) -> str:
        house = planet_house_d10.get(planet)
        return _house_lord_d10(house) if house else ""

    def _dig(planet: str) -> str:
        return str(dignities.get(planet, "") or "").upper()

    house_lords_d1 = getattr(payload, "house_lords", {}) or {}

    def _h1(num: int) -> str:
        return house_lords_d1.get(str(num), house_lords_d1.get(num, ""))

    results: List[Tuple[float, str]] = []
    for start_house, role in ((7, "H7 lord"), (10, "H10 lord")):
        start_planet = _h1(start_house)
        if not start_planet or start_planet not in planet_house_d10:
            continue
        walk = _dispositor_chain_walk(start_planet, _dispositor_of, _dig)
        if walk is None:
            continue
        outcome, chain, chain_has_debilitated = walk
        results.append(_format_dispositor_chain_finding("D10", role, start_planet, outcome, chain, chain_has_debilitated, _dig))

    return results


# Engineering audit fix #7: this module previously defined __all__ TWICE
# (the first, shorter list was silently overwritten by the second at import
# time). Merged into exactly one definition, the union of both (including
# the D7-saptamsha names that only appeared in the first, now-removed list).
