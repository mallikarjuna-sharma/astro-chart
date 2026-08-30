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
from typing import Any, Dict, List, Mapping, Optional, Tuple

from jyotish.d10_archetypes import (
    PLANET_ARCHETYPES,
    ARCHETYPE_NAMES,
    DIGNITY,
    scale_raw_support,
)


"""business_determination.d24_d60_sign

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .constants import _DUSTHANA, _KT, _STRONG_DIGNITY, _record_diagnostic
from .house_evidence import _effective_benefic_malefic_sets, _house_sign

def _d24_competency_status(payload: Any) -> Dict[str, Any]:
    """v17 audit fix: D24 (Siddhamsha, the competency/education-feasibility
    chart) was entirely absent. Per the spec, D24 should answer "can the
    native acquire and sustain the competencies required?", NOT "will the
    native become a business owner?" -- so this is intentionally scoped to
    a single question (10th lord's D24 dignity, as a competency proxy for
    the primary profession) and returned as a multiplicative FACTOR (not a
    promise score of its own), consumed only by business_execution_capacity
    below. Gracefully degrades to NO_DATA/factor=1.0 (neutral, not a
    penalty) when the payload carries no D24 data, since most charts in
    this repo do not currently have Siddhamsha computed."""
    d24_dig = getattr(payload, "d24_planet_dignities", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    h10_lord = house_lords.get("10", house_lords.get(10, ""))
    if not d24_dig or not h10_lord:
        return {
            "status": "NO_DATA", "factor": 1.0,
            "note": "D24 (Siddhamsha) competency data not available on this payload -- competency feasibility not independently verified; treated as neutral (factor=1.0), not as a block on business_execution_capacity.",
        }
    dig = str(d24_dig.get(h10_lord, "") or "").upper()
    if dig in _STRONG_DIGNITY:
        return {"status": "OK", "factor": 1.15, "dignity": dig,
                "note": f"D24: 10th lord ({h10_lord}) strong ({dig}) -> competency/training capacity supports the primary profession"}
    if dig == "DEBILITATED":
        return {"status": "OK", "factor": 0.55, "dignity": dig,
                "note": f"D24: 10th lord ({h10_lord}) DEBILITATED -> competency/training readiness for the primary profession is constrained; execution capacity should be discounted regardless of the D1/D10 promise"}
    return {"status": "OK", "factor": 1.0, "dignity": dig or "NEUTRAL",
            "note": f"D24: 10th lord ({h10_lord}) dignity={dig or 'NEUTRAL'} -> competency readiness unremarkable"}


def _d24_full_analysis(payload: Any) -> Dict[str, Any]:
    """v-audit fix (item 6, D24 full rebuild -- see
    Business_Prediction/docs/scope_d24_full_rebuild.md for the scoping that
    preceded this): _d24_competency_status() above answers exactly one
    question (D1 10th lord's D24 dignity) and was the engine's ENTIRE D24
    treatment. jyotish/engine_io.py has, since before this fix, already
    computed and exposed payload.d24_lagna_sign / d24_house_lords /
    d24_house_occupancy -- none of which business_determination read at
    all. This is a genuinely fuller D24 (Siddhamsha, competency/education)
    analysis built from that already-available data, NOT a replacement for
    _d24_competency_status() (kept unchanged, still feeds
    business_execution_capacity, for backward compatibility -- multiple
    existing tests depend on its exact shape).

    Covers, per the scope doc's recommended first-pass cut:
      (1) D24 Lagnesh (D24-1st-lord) strength within D24's own house graph
          -- the D24-native mirror of Lagnesh-strength checks already done
          for D1/D10 elsewhere in this package.
      (2) D24 H4/H5/H9/H10 lord strength -- foundation/education (H4),
          aptitude/intelligence (H5), higher-learning/mentorship (H9), and
          the competency house itself (H10), evaluated within D24's own
          house graph (native placement), mirroring
          _d10_native_house_evidence()'s exact pattern.
      (3) Occupants of those same houses -- benefic/malefic presence,
          reusing the same _effective_benefic_malefic_sets() classification
          every other varga-native check in this package already uses.
      (5) A simple one-step dispositor check for each of those lords: is
          the SIGN LORD of the sign that lord occupies (within D24) itself
          well or poorly dignified? (Recursive multi-step dispositor CHAINS
          -- item 13 in the audit -- remain explicitly out of scope; this is
          one hop, disclosed as such, not a claim of full chain analysis.)
      (6) D1/D10/D24 coherence -- does this D24 read agree or disagree with
          the existing D1-anchored business_promise/D10-native execution
          read, surfaced as an explicit note rather than silently folded in.

    NOT covered (see scope doc): Vidya yogas (item 4 -- needs an explicit,
    disclosed classical-combination list, deliberately deferred to its own
    pass rather than risking the same "over-claimed coverage" problem this
    whole audit has been finding elsewhere) and skill-type/business-type
    matching (item 7 -- a registry-authoring project, not a scoring
    extension; no "skill category" concept exists anywhere in this repo).

    Gracefully degrades to NO_DATA when d24_lagna_sign/d24_house_lords/
    d24_house_occupancy aren't populated (most charts in this repo do not
    currently have full D24 house-graph data, only D24 planet dignities)."""
    d24_lagna_sign = getattr(payload, "d24_lagna_sign", "") or ""
    house_lords = getattr(payload, "d24_house_lords", {}) or {}
    occupancy = getattr(payload, "d24_house_occupancy", {}) or {}
    dignities = getattr(payload, "d24_planet_dignities", {}) or {}
    if not d24_lagna_sign or not house_lords or not occupancy:
        return {
            "status": "NO_DATA",
            "note": "D24 house-graph data (d24_lagna_sign/d24_house_lords/d24_house_occupancy) not available on this payload -- full D24 analysis not possible; falls back to _d24_competency_status()'s narrower single-planet-dignity read only.",
            "house_findings": [], "dispositor_findings": [], "coherence_note": "",
        }

    def _occ(h: int) -> List[str]:
        return occupancy.get(str(h), occupancy.get(h, [])) or []

    def _lord(h: int) -> str:
        return house_lords.get(str(h), house_lords.get(h, ""))

    def _native_house_of(planet: str) -> int:
        for h in range(1, 13):
            if planet in _occ(h):
                return h
        return 0

    def _dig(planet: str) -> str:
        return str(dignities.get(planet, "") or "").upper()

    benefics, malefics = _effective_benefic_malefic_sets(payload)
    house_findings: List[Tuple[float, str]] = []
    dispositor_findings: List[Tuple[float, str]] = []

    _D24_HOUSE_LABELS = (
        (1, "D24-Lagna (self-directed competency)"),
        (4, "D24-H4 (educational foundation)"),
        (5, "D24-H5 (aptitude/intelligence)"),
        (9, "D24-H9 (higher learning/mentorship)"),
        (10, "D24-H10 (primary-profession competency)"),
    )
    for house_num, label in _D24_HOUSE_LABELS:
        lord = _lord(house_num)
        if not lord:
            continue
        lord_native_house = _native_house_of(lord)
        lord_dig = _dig(lord)
        if lord_native_house in _KT:
            house_findings.append((4.0, f"D24-native: {label} lord ({lord}) sits in D24-kendra/trikona (D24-H{lord_native_house}) -> competency house graph confirms"))
        elif lord_native_house in _DUSTHANA:
            weight = -3.0 if lord_dig not in _STRONG_DIGNITY else -1.0
            house_findings.append((weight, f"D24-native: {label} lord ({lord}) sits in D24-dusthana (D24-H{lord_native_house}), dignity={lord_dig or 'NEUTRAL'} -> competency house graph weakens this signal"))
        benefics_here = [p for p in _occ(house_num) if p in benefics]
        malefics_here = [p for p in _occ(house_num) if p in malefics]
        if benefics_here:
            house_findings.append((2.0, f"D24-native: benefic(s) {', '.join(sorted(set(benefics_here)))} occupy {label} -> directly supported"))
        if malefics_here:
            house_findings.append((-1.5, f"D24-native: malefic(s) {', '.join(sorted(set(malefics_here)))} occupy {label} -> under strain"))

        # (5) one-hop dispositor: house_lords already maps D24-house ->
        # sign-lord for the D24 Lagna-relative house graph, so the
        # dispositor of `lord` (the sign lord of whatever sign `lord`
        # itself occupies within D24) is simply the lord of the D24 house
        # `lord` occupies -- _lord(lord_native_house). NOT a recursive
        # multi-step chain -- see docstring caveat above.
        dispositor = _lord(lord_native_house) if lord_native_house else ""
        if dispositor and dispositor != lord:
            dispositor_dig = _dig(dispositor)
            if dispositor_dig in _STRONG_DIGNITY:
                dispositor_findings.append((1.5, f"D24 dispositor: {label} lord ({lord})'s own dispositor ({dispositor}) is well-dignified ({dispositor_dig}) -> {lord}'s placement rests on a strong foundation, not a borrowed weak one"))
            elif dispositor_dig == "DEBILITATED":
                dispositor_findings.append((-1.5, f"D24 dispositor: {label} lord ({lord})'s own dispositor ({dispositor}) is DEBILITATED -> {lord}'s apparent placement strength may rest on a weak foundation"))

    d24_net = round(sum(w for w, _ in house_findings) + sum(w for w, _ in dispositor_findings), 2)

    # (6) D1/D10/D24 coherence -- compares this D24 read's DIRECTION (not
    # magnitude, since the scales differ) against the existing D1/D10-
    # anchored business_execution_capacity's competency factor, reusing
    # _d24_competency_status() (already computed independently above) as
    # the D1-anchored baseline rather than re-deriving a second one.
    d1_baseline = _d24_competency_status(payload)
    d1_factor = d1_baseline.get("factor", 1.0)
    if d24_net > 2.0 and d1_factor < 1.0:
        coherence_note = f"D24-native house-graph analysis reads SUPPORTIVE (net={d24_net}) while the D1-anchored 10th-lord dignity check reads WEAK (factor={d1_factor}) -- these two D24 readings disagree on direction; treat as genuinely mixed evidence, not a confirmed competency signal."
    elif d24_net < -2.0 and d1_factor > 1.0:
        coherence_note = f"D24-native house-graph analysis reads WEAK (net={d24_net}) while the D1-anchored 10th-lord dignity check reads SUPPORTIVE (factor={d1_factor}) -- these two D24 readings disagree on direction; treat as genuinely mixed evidence, not a confirmed competency signal."
    else:
        coherence_note = f"D24-native house-graph analysis (net={d24_net}) and the D1-anchored 10th-lord dignity check (factor={d1_factor}) point the same direction -- mutually corroborating within D24 itself."

    return {
        "status": "OK",
        "d24_lagna_sign": d24_lagna_sign,
        "net_score": d24_net,
        "house_findings": [{"weight": w, "note": n} for w, n in house_findings],
        "dispositor_findings": [{"weight": w, "note": n} for w, n in dispositor_findings],
        "coherence_note": coherence_note,
        "scope_note": (
            "Covers D24 Lagnesh + H4/H5/H9/H10 native house-graph strength, occupant "
            "benefic/malefic presence, and one-hop dispositor strength -- NOT Vidya "
            "yogas (a disclosed classical-combination list, not yet built) and NOT "
            "skill-type/business-type matching (a registry-authoring project, not a "
            "scoring extension). See Business_Prediction/docs/scope_d24_full_rebuild.md."
        ),
    }


_D60_RELIABLE_STATES = frozenset({"HIGH", "VERIFIED", "RECTIFIED", "CONFIRMED"})

def _d60_dignities_from_planets_d1(payload: Any) -> Dict[str, str]:
    """v-audit fix (D60 doctrinal choice, 2026-07-29 -- user-authorized):
    in-house D60 (Shashtiamsha) dignity derivation via jyotish.astro.
    compute_d60_shashtiamsha_sign(), the same majority odd(same-sign)/
    even(7th-sign) convention D24/D2 already disclose as "majority, not
    singular classical authority" rather than an invented rule. Mirrors
    house_evidence.py's D2/D3/D7 in-house-fallback pattern exactly: reads
    payload.planets_d1 (sign+degree per planet), computes each planet's D60
    sign, then its dignity in that sign via jyotish.dignity.dignity_state
    (the same five-fold dignity primitive used throughout this package).

    Returns {} gracefully when planets_d1 is unavailable -- this is a
    fallback ONLY when no upstream payload.d60_planet_dignities is present
    (checked by the caller first), not a replacement for genuine upstream
    data if a future chart source ever supplies it."""
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    if not isinstance(planets_d1, dict) or not planets_d1:
        return {}
    try:
        from jyotish.astro import compute_d60_shashtiamsha_sign
        from jyotish.dignity import dignity_state
    except Exception as exc:
        _record_diagnostic("d24_d60_sign._d60_dignities_from_planets_d1", exc)
        return {}

    out: Dict[str, str] = {}
    for planet, pdata in planets_d1.items():
        if not isinstance(pdata, dict):
            continue
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        try:
            d60_sign = compute_d60_shashtiamsha_sign(sign, float(degree))
        except (TypeError, ValueError):
            continue
        if not d60_sign:
            continue
        # dignity_state() returns "OWN_SIGN"; this package's own convention
        # (_STRONG_DIGNITY, _dig_name, every other dignity map in this
        # module) uses "OWN" -- normalized here so the in-house-computed
        # path is checked against _STRONG_DIGNITY exactly the same way an
        # upstream-supplied dignity string already is, not silently missing
        # the OWN-sign case due to a vocabulary mismatch.
        raw_dig = dignity_state(planet, d60_sign)
        out[planet] = "OWN" if raw_dig == "OWN_SIGN" else raw_dig
    return out


def _d60_confirmation_status(payload: Any) -> Dict[str, Any]:
    """v17 audit fix: D60 (Shashtiamsha) was entirely absent. Per the spec,
    D60 must be (a) gated on birth-time reliability -- zero weight unless
    the payload explicitly reports a reliable/rectified birth time -- and
    (b) capped at roughly 3-5% of the final judgment, never able to
    override a weak D1 promise or manufacture a business combination. This
    returns a MODIFIER (typically ±0.04, i.e. ±4%) rather than its own
    promise score, applied only inside business_stability below.

    2026-07-29 update (user-authorized doctrinal choice): D60 now has a
    real in-house construction path (jyotish.astro.compute_d60_
    shashtiamsha_sign(), see that function's own docstring for the
    disclosed majority-convention caveat) used as a fallback when no
    upstream payload.d60_planet_dignities is present -- which, per the
    prior investigation this docstring itself documents, is EVERY chart in
    this codebase today. `dignity_source` distinguishes "UPSTREAM" (a
    future chart source that actually supplies d60_planet_dignities
    directly) from "IN_HOUSE_COMPUTED" (derived here from planets_d1) so a
    reader always knows which confidence tier produced a given D60 read;
    the modifier math and birth-time-reliability gate are identical either
    way.
    """
    d60_dig = getattr(payload, "d60_planet_dignities", {}) or {}
    dignity_source = "UPSTREAM"
    if not d60_dig:
        d60_dig = _d60_dignities_from_planets_d1(payload)
        dignity_source = "IN_HOUSE_COMPUTED"

    uncertainty = getattr(payload, "birth_time_uncertainty_minutes", None)
    reliability = str(getattr(payload, "birth_time_reliability", "") or "").upper()
    try:
        uncertainty_minutes = abs(float(uncertainty)) if uncertainty is not None else None
    except (TypeError, ValueError):
        uncertainty_minutes = None
    # D60 segments are only 30 arc-minutes wide, so use the same canonical
    # uncertainty input as the confidence engine and apply a deliberately
    # strict gate.  The legacy string is consulted only when canonical
    # uncertainty was not supplied.
    reliability_source = "birth_time_uncertainty_minutes" if uncertainty_minutes is not None else "legacy_birth_time_reliability"
    from .policy import DECISION_POLICY
    d60_reliable = uncertainty_minutes <= DECISION_POLICY.d60_max_uncertainty_minutes if uncertainty_minutes is not None else reliability in _D60_RELIABLE_STATES
    house_lords = getattr(payload, "house_lords", {}) or {}
    h10_lord = house_lords.get("10", house_lords.get(10, ""))
    if not d60_dig or not h10_lord:
        # v-audit fix (item 7, D60 gap made explicit rather than silent):
        # this branch now only fires when planets_d1 is ALSO unavailable
        # (no upstream data AND no in-house fallback possible) -- e.g. this
        # codebase's own synthetic/fixture payloads that carry house_lords
        # but no raw degree data. blocked_reason is kept (not just NO_DATA)
        # so a reader can still tell "D60 genuinely could not be computed
        # for this chart" apart from an ordinary missing-field NO_DATA.
        return {"status": "NO_DATA", "modifier": 0.0,
                "blocked_reason": "D60_NO_UPSTREAM_OR_PLANETS_D1_DATA",
                "note": (
                    "D60 (Shashtiamsha) has no upstream payload.d60_planet_dignities AND no "
                    "payload.planets_d1 (sign+degree) to derive it in-house via jyotish.astro."
                    "compute_d60_shashtiamsha_sign() -- not used for this chart. See that "
                    "function's docstring for the disclosed majority-convention caveat this "
                    "engine now applies when planets_d1 IS available."
                )}
    if not d60_reliable:
        return {"status": "NOT_APPLIED_LOW_RELIABILITY", "modifier": 0.0, "dignity_source": dignity_source,
                "reliability_source": reliability_source, "birth_time_uncertainty_minutes": uncertainty_minutes,
                "note": f"D60 data present but birth-time reliability is insufficient ({reliability_source}={uncertainty_minutes if uncertainty_minutes is not None else reliability or 'UNKNOWN'}) -- D60 carries ZERO weight unless uncertainty is <=1 minute or, when canonical uncertainty is absent, the legacy status is reliably rectified."}
    dig = str(d60_dig.get(h10_lord, "") or "").upper()
    if dig in _STRONG_DIGNITY:
        modifier, note = 0.04, f"D60: 10th lord ({h10_lord}) strong ({dig}), birth time reliable -> small (+4%) deep-karmic confirmation [{dignity_source}]"
    elif dig == "DEBILITATED":
        modifier, note = -0.04, f"D60: 10th lord ({h10_lord}) DEBILITATED, birth time reliable -> small (-4%) deep-karmic caution [{dignity_source}]"
    else:
        modifier, note = 0.0, f"D60: 10th lord ({h10_lord}) dignity={dig or 'NEUTRAL'} -> no material modifier [{dignity_source}]"
    return {"status": "OK", "modifier": modifier, "dignity": dig or "NEUTRAL", "dignity_source": dignity_source,
            "reliability_source": reliability_source, "birth_time_uncertainty_minutes": uncertainty_minutes, "note": note}


def _d11_gains_status(payload: Any) -> Dict[str, Any]:
    """Optional D11 gains corroboration using named HARMONIC_11 policy."""
    try:
        from jyotish.astro import compute_d11_chart
        from jyotish.constants import _SIGN_LORD
        planets = getattr(payload, "planets_d1", {}) or {}
        lagna = getattr(payload, "lagna_sign", "") or ""
        lagna_degree = float(getattr(payload, "lagna_degree", 0.0) or 0.0)
        if not planets or not lagna:
            return {"status": "NO_DATA", "construction_policy": "HARMONIC_11", "note": "D1 longitudes/Lagna unavailable."}
        chart = compute_d11_chart(planets, lagna, lagna_degree, "HARMONIC_11")
        d11_lagna = chart.get("Lagna", "")
        if not d11_lagna:
            return {"status": "NO_DATA", "construction_policy": "HARMONIC_11"}
        signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        li = signs.index(d11_lagna)
        house_of = {p: ((signs.index(s) - li) % 12) + 1 for p, s in chart.items() if p != "Lagna" and s in signs}
        h2_lord = _SIGN_LORD[signs[(li + 1) % 12]]
        h11_lord = _SIGN_LORD[signs[(li + 10) % 12]]
        score = 50.0
        reasons = []
        for lord, label in ((h2_lord, "D11 H2 lord"), (h11_lord, "D11 H11 lord")):
            h = house_of.get(lord)
            if h in _KT or h in {2, 11}:
                score += 12.0; reasons.append(f"{label} {lord} well placed in H{h}")
            elif h in _DUSTHANA:
                score -= 12.0; reasons.append(f"{label} {lord} placed in H{h}")
        benefics, malefics = _effective_benefic_malefic_sets(payload)
        score += 4.0 * sum(house_of.get(p) in {2, 11} for p in benefics)
        score -= 4.0 * sum(house_of.get(p) in {2, 11} for p in malefics)
        score = round(max(0.0, min(100.0, score)), 1)
        return {
            "status": "APPLIED", "construction_policy": "HARMONIC_11",
            "doctrinal_status": "OPTIONAL_NON_SHODASHAVARGA_CORROBORATION",
            "gains_score_0_100": score, "capital_support": score >= 50.0,
            "chart": chart, "reasons": reasons,
            "note": "D11 is optional corroboration only; D1/D2/H11 promise remains primary.",
        }
    except Exception as exc:
        _record_diagnostic("d24_d60_sign._d11_gains_status", exc)
        return {"status": "COMPUTATION_FAILED", "construction_policy": "HARMONIC_11"}


_FIRE_SIGNS = frozenset({"Aries", "Leo", "Sagittarius"})

_EARTH_SIGNS = frozenset({"Taurus", "Virgo", "Capricorn"})

_AIR_SIGNS = frozenset({"Gemini", "Libra", "Aquarius"})

_WATER_SIGNS = frozenset({"Cancer", "Scorpio", "Pisces"})

_MOVABLE_SIGNS = frozenset({"Aries", "Cancer", "Libra", "Capricorn"})

_FIXED_SIGNS = frozenset({"Taurus", "Leo", "Scorpio", "Aquarius"})

_DUAL_SIGNS = frozenset({"Gemini", "Virgo", "Sagittarius", "Pisces"})

_ELEMENT_FIELD_AFFINITY = {
    "FIRE": ("leadership/entrepreneurship", "sports/defence", "education", "energy"),
    "EARTH": ("finance", "agriculture", "manufacturing", "real estate", "construction"),
    "AIR": ("trade", "technology", "consulting", "media", "digital platforms"),
    "WATER": ("hospitality", "food", "healthcare", "research", "shipping"),
}

_MODALITY_OPERATING_HINT = {
    "MOVABLE": "favours starting/expanding new ventures into new markets",
    "FIXED": "favours capital-intensive, brand-consolidating, long-term-asset businesses",
    "DUAL": "favours consulting, trading, brokerage, multi-product/advisory models",
}

def _sign_modality_profile(payload: Any) -> Dict[str, Any]:
    """v17 audit fix: fire/earth/air/water and movable/fixed/dual sign
    interpretation was entirely absent from business-field determination.
    Uses the Lagna sign and the 10th-house sign (the two most field-
    relevant reference points already used elsewhere in this module) to
    produce a candidate field-affinity list and an operating-model hint --
    feeding business_field_fit as a small, transparent bias, never as a
    standalone field/industry determination on its own (per the spec: this
    should bias sector families, not directly produce exact business
    names)."""
    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    if not lagna_sign:
        return {"status": "NO_DATA", "field_affinities": [], "note": "No lagna_sign on payload"}
    tenth_sign = _house_sign(lagna_sign, 10)

    def _elem(sign: str) -> str:
        if sign in _FIRE_SIGNS:
            return "FIRE"
        if sign in _EARTH_SIGNS:
            return "EARTH"
        if sign in _AIR_SIGNS:
            return "AIR"
        if sign in _WATER_SIGNS:
            return "WATER"
        return ""

    def _mod(sign: str) -> str:
        if sign in _MOVABLE_SIGNS:
            return "MOVABLE"
        if sign in _FIXED_SIGNS:
            return "FIXED"
        if sign in _DUAL_SIGNS:
            return "DUAL"
        return ""

    lagna_elem, lagna_mod = _elem(lagna_sign), _mod(lagna_sign)
    tenth_elem, tenth_mod = _elem(tenth_sign), _mod(tenth_sign)
    affinities = sorted(set(_ELEMENT_FIELD_AFFINITY.get(lagna_elem, ()) + _ELEMENT_FIELD_AFFINITY.get(tenth_elem, ())))
    return {
        "status": "OK",
        "lagna_sign": lagna_sign, "lagna_element": lagna_elem, "lagna_modality": lagna_mod,
        "tenth_house_sign": tenth_sign, "tenth_house_element": tenth_elem, "tenth_house_modality": tenth_mod,
        "field_affinities": affinities,
        "operating_model_hint": _MODALITY_OPERATING_HINT.get(tenth_mod, ""),
        "note": f"Lagna={lagna_sign} ({lagna_elem}/{lagna_mod}), 10th-house sign={tenth_sign} ({tenth_elem}/{tenth_mod}) -> candidate field affinities: {', '.join(affinities) or 'none'}",
    }

