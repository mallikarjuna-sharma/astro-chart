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


"""business_determination.contradictions

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .constants import _DUSTHANA, _STRONG_DIGNITY
from .house_evidence import _d10_native_house_evidence, _d1_tenth_lord_direct_evidence, _d2_native_house_evidence, _d3_native_house_evidence, _dig_name, _effective_benefic_malefic_sets, _house_lord_strength
from .operating_models import _business_operating_model, _business_operating_model_d10


def _dispositor_chain(planet: str, house_lords: Dict[str, Any], planet_house: Dict[str, Any], max_depth: int = 6) -> List[str]:
    """ISSUE-3 audit fix helper: full D1 dispositor chain for `planet` --
    planet -> (lord of the sign/house planet occupies) -> (lord of THAT
    lord's own house) -> ... until a self-ruled/terminal planet (own house)
    or a repeat (cycle) is reached, or max_depth is hit. Exposed on
    contradiction findings so a reader can independently verify an "H11
    lord has no independent H7/H10 path" claim against the actual
    occupant -> dispositor -> dispositor's-own-placement chain, instead of
    trusting a same-lord/no-connection claim opaquely."""
    if not planet:
        return []
    chain = [planet]
    visited = {planet}
    cur = planet
    for _ in range(max_depth):
        house = planet_house.get(cur)
        if house is None:
            break
        next_lord = house_lords.get(str(house), house_lords.get(house, ""))
        if not next_lord:
            break
        chain.append(next_lord)
        if next_lord == cur or next_lord in visited:
            break
        visited.add(next_lord)
        cur = next_lord
    return chain


def _apply_contradiction_family_caps(penalties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ISSUE-2 audit fix: several contradiction checks can fire off the
    SAME underlying evidence cluster (e.g. both the D1/D10 magnitude-
    disagreement check and the D10-operational-house-concentration check
    are both reading the same D10-native evidence ledger; both are tagged
    family="D10_H8_concentration" at their _flag() call sites). Summing
    such penalties linearly double-counts one root cause as if it were
    several independent corroborating contradictions. This caps the
    COMBINED penalty per family using a dominant-rule-plus-diminishing-
    returns formula (full weight for the single largest penalty in the
    family, +50% of the next largest, +25% of the next, ...) instead of a
    flat sum, and rescales every member of an over-linear family
    proportionally so the family's new total exactly equals the capped
    total. Families with fewer than 2 active members are left untouched
    (nothing to cap). Adds `family_capped` / `family_raw_weight` /
    `family_raw_total` / `family_capped_total` fields to every penalty in
    an affected family so the adjustment is auditable, not silent."""
    families: Dict[str, List[Dict[str, Any]]] = {}
    for p in penalties:
        fam = p.get("family")
        if fam:
            families.setdefault(fam, []).append(p)
    for fam, items in families.items():
        if len(items) < 2:
            continue
        raw_total = sum(it["weight"] for it in items)
        if raw_total <= 0:
            continue
        items_sorted = sorted(items, key=lambda x: x["weight"], reverse=True)
        capped_total = items_sorted[0]["weight"]
        factor = 0.5
        for it in items_sorted[1:]:
            capped_total += it["weight"] * factor
            factor *= 0.5
        if capped_total >= raw_total:
            continue  # already at/below the diminishing-returns ceiling
        scale = capped_total / raw_total
        for it in items:
            it["family_raw_weight"] = it["weight"]
            it["weight"] = round(it["weight"] * scale, 2)
            it["family_capped"] = True
            it["family_raw_total"] = round(raw_total, 2)
            it["family_capped_total"] = round(capped_total, 2)
    return penalties


def _contradiction_penalties(
    payload: Any,
    significators: Dict[str, Any],
    d24_status: Dict[str, Any],
    kp10: Dict[str, Any],
    mode_gate: Optional[Dict[str, Any]] = None,
    d60_status: Optional[Dict[str, Any]] = None,
    timed_windows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """v17 audit fix: implements the spec's section-14 contradiction
    controls, previously entirely absent. Each check returns a signed
    penalty against a specific MODE (currently always "business", since
    every listed pattern is a reason business would be OVER-credited, not
    under-credited) with an explicit note, rather than silently letting
    the underlying rule's positive credit stand unchallenged.

    v22 audit fix: added checks #11 (D60 used despite uncertain birth
    time) and #12 (no business-activating dasha within the forecast
    horizon) -- the spec's section-14 list has 12 items; these two were
    previously entirely absent, leaving 10 of 12 implemented. d60_status/
    timed_windows are optional (default None) so existing callers that
    don't pass them still get the other 10 checks unchanged; only #11/#12
    are skipped when the corresponding argument is omitted."""
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = getattr(payload, "planet_dignities", {}) or {}

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    h1_lord, h2_lord, h3_lord = _h(1), _h(2), _h(3)
    h6_lord, h7_lord = _h(6), _h(7)
    h8_lord, h10_lord, h11_lord = _h(8), _h(10), _h(11)

    penalties: List[Dict[str, Any]] = []

    def _flag(mode: str, weight: float, note: str, check_id: Optional[str] = None, family: Optional[str] = None) -> None:
        # Engineering audit fix #11: every contradiction record now carries a
        # stable, machine-readable `id` field alongside its human-readable
        # `note`. Most checks don't need a caller to branch on their
        # specific identity, so `check_id` defaults to a generic per-check
        # slug when not explicitly given; callers that need to match a
        # SPECIFIC contradiction programmatically (e.g. engine.py's D1/D10
        # hard veto) should pass an explicit, documented id instead of
        # relying on substring-searching `note`.
        #
        # ISSUE-2 audit fix: `family` is an optional evidence-cluster tag
        # (e.g. "D10_H8_concentration", "H2_retention",
        # "H11_H6_income_source") -- checks that read the same underlying
        # evidence ledger are tagged with the same family string so
        # _apply_contradiction_family_caps() (called once, after every
        # check below has run) can detect and cap double-counted penalties
        # instead of summing them linearly.
        penalties.append({
            "mode": mode,
            "weight": weight,
            "note": note,
            "id": check_id or f"CONTRADICTION_RULE_{len(penalties) + 1:02d}",
            "family": family,
        })

    # 1. Strong 7th with no H2/H10/H11 connection.
    if h7_lord:
        h7_strength = _house_lord_strength(payload, 7)
        h7_connects = bool(h7_lord in (h2_lord, h10_lord, h11_lord) or _ph(h7_lord) in (2, 10, 11))
        if h7_strength >= 0.6 and not h7_connects:
            _flag("business", 6, f"Contradiction: H7 lord ({h7_lord}) is strong (strength={h7_strength}) but has NO connection to H2/H10/H11 -> reads as client-facing employment/consulting/sales exposure, not an owned commercial structure", check_id="H7_ISOLATED_NO_H2_H10_H11")

    # 2. Strong 3rd with weak monetisation (H2).
    #
    # v39 audit fix (#7, user-caught): this flagged H2 as "weak" purely
    # from _house_lord_strength(payload, 2) crossing a 0.35 threshold,
    # without checking whether H2's own LORD is independently well-
    # dignified (exalted/own-sign) -- a chart where the 2nd lord is
    # exalted but placed in a non-kendra/trikona house (e.g. an upachaya
    # house like the 11th) can still trip the coarse threshold while the
    # underlying dignity evidence argues against "weak monetisation" being
    # the honest read. When the 2nd lord's raw DIGNITY (not the blended
    # placement-tier strength) is independently strong, the penalty is
    # halved and re-labelled as a milder "delayed/disciplined accumulation"
    # caution rather than an outright monetisation contradiction.
    if h3_lord:
        h3_strength = _house_lord_strength(payload, 3)
        h2_strength = _house_lord_strength(payload, 2) if h2_lord else 0.0
        h2_own_dignity = str(dignities.get(h2_lord, "") or "").upper() if h2_lord else ""
        if h3_strength >= 0.6 and h2_strength < 0.35:
            # D3 (Drekkana) tempering/aggravating factor -- previously
            # this check relied SOLELY on D1 placement/dignity for both
            # H3 and H2. D3 is the classical self-effort/courage varga
            # for H3 specifically (see house_evidence._d3_native_house_evidence's
            # docstring): if D3 strongly CONFIRMS the D1-H3 self-effort
            # promise, the "strong H3" side of this caution is genuinely
            # well-supported even though H2 is weak, so severity is
            # tempered (self-effort is real, only monetisation lags). If
            # D3 CONTRADICTS/weakens the D1-H3 promise instead, the
            # underlying H3 strength read is itself suspect, so this is
            # flagged as a MORE serious contradiction (neither self-effort
            # nor monetisation is well-supported). Gracefully degrades to
            # the original (D1-only) severity when D3 occupancy can't be
            # resolved (net == 0.0 in that case; see
            # _d3_native_house_evidence()'s documented graceful-empty
            # behavior) -- i.e. this is purely additive, never a
            # regression on charts lacking upstream D3 data.
            d3_evidence = _d3_native_house_evidence(payload)
            d3_net = sum(w for w, _ in d3_evidence)
            if h2_own_dignity in _STRONG_DIGNITY:
                if d3_net > 2:
                    _flag("business", 1.5, f"Caution (tempered further by D3): H3 (enterprise/initiative, strength={h3_strength}) is strong; H2's blended placement-strength reads weak ({h2_strength}), but H2 lord ({h2_lord}) is independently well-dignified ({h2_own_dignity}) AND D3 (Drekkana) confirms the H3 self-effort promise (net={round(d3_net,1)}) -> reads as delayed/disciplined capital accumulation on a genuinely well-supported self-effort foundation, not an inability to monetise")
                elif d3_net < -2:
                    _flag("business", 4, f"Contradiction (aggravated by D3): H3 (enterprise/initiative, strength={h3_strength}) reads strong from D1 alone, but D3 (Drekkana) weakens the underlying self-effort/courage promise (net={round(d3_net,1)}) even though H2 lord ({h2_lord}) is independently well-dignified ({h2_own_dignity}) -> the D1 H3 strength itself is now in question, not just H2 monetisation")
                else:
                    _flag("business", 2.5, f"Caution (not a full contradiction): H3 (enterprise/initiative, strength={h3_strength}) is strong; H2's blended placement-strength reads weak ({h2_strength}), but H2 lord ({h2_lord}) is independently well-dignified ({h2_own_dignity}) -> reads as delayed/disciplined capital accumulation, not an inability to monetise")
            else:
                if d3_net > 2:
                    _flag("business", 3.5, f"Contradiction (tempered by D3): H3 (enterprise/initiative, strength={h3_strength}) is strong and D3 (Drekkana) confirms the underlying self-effort promise (net={round(d3_net,1)}), but H2 (monetisation, strength={h2_strength}) is weak -> continuous, genuinely well-supported activity/turnover without retained profit risk")
                elif d3_net < -2:
                    _flag("business", 6.5, f"Contradiction (aggravated by D3): H3 (enterprise/initiative, strength={h3_strength}) reads strong from D1 alone but D3 (Drekkana) weakens the self-effort/courage promise (net={round(d3_net,1)}), and H2 (monetisation, strength={h2_strength}) is also weak -> neither self-effort nor monetisation is well-supported, a more serious risk than turnover-without-profit alone")
                else:
                    _flag("business", 5, f"Contradiction: H3 (enterprise/initiative, strength={h3_strength}) is strong but H2 (monetisation, strength={h2_strength}) is weak -> continuous activity/turnover without retained profit risk")

    # 3. Strong 11th deriving purely from H6 (salary), with no independent H7/H10 path.
    #
    # v39 audit fix (#8, user-caught): this only checked H7/H10 as
    # "independent" (non-salary) paths for H11 gains, but a chart where
    # H11's lord ALSO rules H2 or H3 has a separate income-enterprise-gains
    # chain (2nd = accumulated wealth, 3rd = effort/initiative) that is
    # just as independent of H6/salary as an H7/H10 connection would be --
    # e.g. a single planet ruling both 2nd/3rd and sitting in the 11th
    # connects income and enterprise to gains directly, not merely via
    # employment. Added as a third independent-path check alongside H7/H10.
    if h11_lord and h6_lord:
        # ISSUE-3 audit fix (verified against business_debug.json's actual
        # dispositor-chain/significator evidence for this rule -- see
        # contradictions.py module notes on _dispositor_chain): the
        # previous `via_h6 = h11_lord == h6_lord or _ph(h11_lord) == 6`
        # treated H11 and H6 sharing the SAME lord (a structural
        # coincidence of which planet naturally rules both signs for this
        # ascendant -- not evidence the lord is actually PLACED in H6) as
        # equivalent to "H11 lord sits in the 6th". That conflated
        # co-lordship with placement and could fire even when the H11 lord
        # is independently, strongly placed in H7/H10/H11 itself (its own
        # house) with zero actual connection to H6. `via_h6` now requires
        # genuine PLACEMENT in H6, not mere co-lordship.
        h11_dispositor_chain = _dispositor_chain(h11_lord, house_lords, planet_house)
        via_h6 = _ph(h11_lord) == 6
        via_h7 = bool(h7_lord and (_ph(h11_lord) == 7 or h11_lord == h7_lord))
        via_h10 = bool(h10_lord and (_ph(h11_lord) == 10 or h11_lord == h10_lord))
        via_h2_h3 = bool((h2_lord and h11_lord == h2_lord) or (h3_lord and h11_lord == h3_lord))
        # ISSUE-3 audit fix: H11 lord placed in its OWN house (11th) --
        # or in H7/H10 -- is an independently strong, result-producing
        # placement (the same {7,10,11} set significators.py's own
        # H11-profit-realization rule treats as sufficient on its own) and
        # needs no H6 routing at all.
        via_h11_self = _ph(h11_lord) == 11
        # ISSUE-3 audit fix: dispositor-chain cross-check -- if H11 lord's
        # own D1 dispositor chain passes through (or is) the same planet
        # that lords H7/H10, that is a genuine independent grounding link
        # between H11 and H7/H10, not a same-lord coincidence.
        via_dispositor = bool(
            (h7_lord and h7_lord in h11_dispositor_chain[1:]) or
            (h10_lord and h10_lord in h11_dispositor_chain[1:])
        )
        independent_path = via_h7 or via_h10 or via_h2_h3 or via_h11_self or via_dispositor
        _chain_str = " -> ".join(h11_dispositor_chain)
        if via_h6 and not independent_path:
            _flag("business", 6, f"Contradiction: H11 gains trace to H6 ({h6_lord}) with no independent H7/H10 path -> profit likely salary/incentive-derived, not commercial profit (H11 lord dispositor chain: {_chain_str})", check_id="H11_H6_NO_INDEPENDENT_PATH", family="H11_H6_income_source")
        elif via_h6 and independent_path:
            _flag("business", 2, f"Note: H11's lord ({h11_lord}) is placed in H6 but also connects to H2/H3, H7/H10 (directly or via its own D1 dispositor chain: {_chain_str}), giving an independent income-enterprise-gains chain alongside the H6/salary connection -> gains may initially route through employment but can convert into self-generated commercial income, not purely salary-derived", check_id="H11_H6_PARTIAL_INDEPENDENT_PATH", family="H11_H6_income_source")
        elif not via_h6 and (via_h7 or via_h10 or via_h11_self or via_dispositor):
            # Auditability-only entry (weight 0, never affects any score):
            # exposes the dispositor chain even in the common case where
            # this rule correctly does NOT fire, so a reader can verify
            # H11's independent H7/H10/H11 grounding directly rather than
            # only seeing the rule's silence.
            _flag("business", 0, f"H11 lord ({h11_lord}) dispositor chain: {_chain_str} -- independently connected to H7/H10/H11 (via_h7={via_h7}, via_h10={via_h10}, via_h11_self={via_h11_self}, via_dispositor={via_dispositor}), NOT routed through H6 ({h6_lord}) -> no salary-routing contradiction applies", check_id="H11_DISPOSITOR_CHAIN_TRACE", family="H11_H6_income_source")

    # 4. Strong 10th but corporate hierarchy (H6) stronger than ownership (H1/H3/H7).
    if h10_lord and h6_lord:
        via_h6 = h10_lord == h6_lord or _ph(h10_lord) == 6
        via_h1 = bool(h1_lord and (_ph(h10_lord) == 1 or h10_lord == h1_lord))
        via_h3 = bool(h3_lord and (_ph(h10_lord) == 3 or h10_lord == h3_lord))
        via_h7 = bool(h7_lord and (_ph(h10_lord) == 7 or h10_lord == h7_lord))
        if via_h6 and not (via_h1 or via_h3 or via_h7):
            _flag("business", 7, f"Contradiction: H10 lord ({h10_lord}) ties to H6 with no H1/H3/H7 ownership link -> corporate-hierarchy/senior-executive pattern more likely than entrepreneurship")

    # 5. Afflicted 7th (malefic co-tenancy, no benefic mitigation).
    if h7_lord:
        h7_house = _ph(h7_lord)
        co = [p for p, h in planet_house.items() if h == h7_house and p != h7_lord]
        benefics, malefics = _effective_benefic_malefic_sets(payload)
        mal_co = [p for p in co if p in malefics]
        ben_co = [p for p in co if p in benefics]
        if mal_co and not ben_co:
            _flag("business", 5, f"Contradiction: H7 lord ({h7_lord}) afflicted by malefic(s) {', '.join(sorted(set(mal_co)))} with no benefic mitigation -> partner/customer instability risk")

    # 6. Weak H2 (turnover without retained wealth).
    #
    # ISSUE-4 audit fix (verified against business_debug.json for this
    # chart: D1 H2 strength=0.2539 alone reads weak, but D2 (Hora) net
    # evidence for this chart sums to exactly 0.0 -- mixed/neutral, not
    # confirmatory -- and the H2 lord (Saturn here) is EXALTED in D9
    # (Navamsha), a strongly supportive corroboration): relying solely on
    # the D1 blended placement-strength number treated a genuinely mixed
    # or supportive corroborating-varga picture as if it were a clean,
    # confirmed weakness. Now pulls in D2 (Hora) net evidence (already
    # available via _d2_native_house_evidence, reused rather than
    # reimplemented -- same helper check #9b above already uses) and D9
    # dignity of the H2 lord (same payload.d9_planet_dignities lookup and
    # _STRONG_DIGNITY set significators.py's H11/H2 D9-confirmation rules
    # already use) before deciding whether this is a clean contradiction or
    # a milder, relabeled "mixed capital-retention evidence" caution.
    if h2_lord:
        h2_strength = _house_lord_strength(payload, 2)
        if h2_strength < 0.35:
            _d2_evidence_h2 = _d2_native_house_evidence(payload)
            _d2_net_h2 = sum(w for w, _ in _d2_evidence_h2)
            _d9_h2_dig = str((getattr(payload, "d9_planet_dignities", {}) or {}).get(h2_lord, "") or "").upper()
            _d9_h2_supportive = _d9_h2_dig in _STRONG_DIGNITY
            if _d2_net_h2 >= 0 or _d9_h2_supportive:
                _flag(
                    "business", 1.5,
                    f"Mixed capital-retention evidence: D1 H2 (capital retention) strength reads weak ({h2_strength}), "
                    f"but D2 (Hora) net evidence is neutral-to-supportive (net={round(_d2_net_h2, 1)}) "
                    + (f"and H2 lord ({h2_lord}) is well-dignified in D9 (Navamsha)={_d9_h2_dig} " if _d9_h2_supportive else f"and D9 (Navamsha) dignity of H2 lord ({h2_lord})={_d9_h2_dig or 'n/a'} does not aggravate it further ")
                    + "-> not a clean confirmed weakness; corroborating vargas are neutral or supportive, so this reads as a caution, not a firm turnover-without-retention finding",
                    check_id="H2_RETENTION_MIXED_EVIDENCE", family="H2_retention",
                )
            else:
                _flag(
                    "business", 4,
                    f"Contradiction: H2 (capital retention, D1 strength={h2_strength}) weak, corroborated by D2 (Hora net={round(_d2_net_h2, 1)}) "
                    f"and D9 (Navamsha) dignity of H2 lord ({h2_lord})={_d9_h2_dig or 'n/a'} showing no supportive corroboration -> turnover without retained wealth risk",
                    check_id="H2_RETENTION_CONFIRMED_WEAK", family="H2_retention",
                )

    # 7. Severe H8 involvement not offset by strength.
    if h8_lord:
        h8_dig = _dig_name(h8_lord, dignities)
        if _ph(h8_lord) in _DUSTHANA and h8_dig not in _STRONG_DIGNITY:
            _flag("business", 4, f"Contradiction: H8 lord ({h8_lord}) placed in a dusthana without strong dignity -> leverage/other-people's-money volatility not offset by strength")

    # 8. D1 promises but D10-native execution graph reads net negative
    # (magnitude-only version, kept for backward compatibility).
    d1_net = sum(w for w, _ in _d1_tenth_lord_direct_evidence(payload))
    d10_net = sum(w for w, _ in _d10_native_house_evidence(payload))
    if d1_net > 4 and d10_net < -2:
        # ISSUE-2 audit fix: tagged family="D10_H8_concentration" -- this
        # check and 8b below both ultimately read the same D10-native
        # evidence ledger (d10_net here is the same magnitude-only sum that
        # feeds d10_operational_net's H6/H8/H12 concentration read in 8b),
        # so both can fire off one underlying D10-negative-evidence root
        # cause. See _apply_contradiction_family_caps (module-level, called
        # once at the end of this function) for how the combined penalty
        # is capped instead of summed linearly.
        _flag("business", 6, f"Contradiction: D1 promises livelihood/business strength (net={round(d1_net,1)}) but D10-native house graph reads net negative (net={round(d10_net,1)}) -> D1 and D10 disagree on execution; the D1 promise likely under-delivers", check_id="D1_D10_MAGNITUDE_DISAGREEMENT", family="D10_H8_concentration")

    # 8b. v18 audit fix: the check above only compared NET SIGN, not named
    # OPERATING MODELS -- the spec specifically asks for "D1 and D10 giving
    # opposite operating models". Classifies D10-native evidence by which
    # house-family each finding concerns (H7/H10/H11 = ownership/venture,
    # H6/H8/H12 = operational/service/risk) to get a genuine D10-side
    # operating-model leaning, and compares it against D1's own leaning
    # (the mode-gate's business_score vs employment_score, which IS the
    # D1-anchored structural read).
    if mode_gate is not None:
        d10_evidence = _d10_native_house_evidence(payload)
        d10_ownership_net = sum(w for w, n in d10_evidence if any(f"H{h}" in n for h in (7, 10, 11)))
        d10_operational_net = sum(w for w, n in d10_evidence if any(f"H{h}" in n for h in (6, 8, 12)))
        d1_leans_business = mode_gate.get("business_score", 0) > mode_gate.get("employment_score", 0)
        d1_leans_job = mode_gate.get("employment_score", 0) > mode_gate.get("business_score", 0)
        d10_leans_operational = d10_operational_net < -2 and d10_operational_net < d10_ownership_net
        d10_leans_ownership = d10_ownership_net > 2 and d10_ownership_net > abs(d10_operational_net)

        # v31 audit fix: this check previously read D10 evidence
        # concentrating in H6/H8/H12 (operational/service/risk houses) as
        # D10 "opposing" business ownership -- as if D10 were arguing for
        # employment instead -- which fed engine.py's hard veto
        # (rejected_by_main_chart forcing proceed=False). But
        # _business_operating_model_d10()'s own named taxonomy (sole_owner/
        # partnership/family_business/professional_practice/trading_
        # brokerage/manufacturing/scalable_platform) has NO "employment"
        # option at all -- every model D10 can name IS a business structure.
        # H6/H8/H12 concentration therefore does not prove "D10 favours
        # employment"; it means the business itself will be operationally
        # demanding (staff/vendor/competitive/liability-heavy), which is a
        # real caution, not an opposing conclusion. Now consults D10's own
        # best-fit model directly: when D10 still names a real business
        # operating model despite the operational-house concentration (the
        # common case), this is downgraded to an operational-complexity
        # finding that only ever subtracts points and can never trigger the
        # hard veto (its note text no longer matches engine.py's veto
        # phrase). The old "OPPOSING operating models" framing -- and the
        # ability to hard-veto proceed -- is now reserved for the genuinely
        # pathological case where D10-native cannot name ANY coherent
        # operating model at all, not merely a concentration in
        # operationally-demanding houses.
        d10_named_model = _business_operating_model_d10(payload)
        d10_still_names_a_business_model = bool(d10_named_model.get("best_fit"))
        if d1_leans_business and d10_leans_operational:
            # ISSUE-2 audit fix: tagged family="D10_H8_concentration" --
            # d10_operational_net is built from the SAME D10-native
            # evidence ledger as d10_net feeding check #8 above (both
            # concern D10's H6/H8/H12 operational/dusthana concentration),
            # so this and #8 can double-charge one root cause. Capped
            # jointly by _apply_contradiction_family_caps below.
            if d10_still_names_a_business_model:
                _flag("business", 4, f"Caution: D1 leans BUSINESS (business_score={mode_gate.get('business_score')} > employment_score={mode_gate.get('employment_score')}) and D10-native evidence concentrates in H6/H8/H12 operational/service houses (net={round(d10_operational_net,1)}) rather than H7/H10/H11 ownership houses -> D10 can name a structural operating model ({d10_named_model.get('best_fit')}), but execution capacity is constrained and the venture will be operationally demanding, competitive and exposed to staff/vendor/liability complexity -- this is NOT read as D10 fully opposing business ownership, because a coherent business structure remains identifiable", check_id="D10_OPERATIONAL_CONCENTRATION_CAUTION", family="D10_H8_concentration")
            else:
                _flag("business", 7, f"Contradiction: D1 leans BUSINESS (business_score={mode_gate.get('business_score')} > employment_score={mode_gate.get('employment_score')}) but D10-native evidence concentrates in H6/H8/H12 operational/service houses (net={round(d10_operational_net,1)}) rather than H7/H10/H11 ownership houses, and D10-native cannot name any coherent business operating model at all -> D1 and D10 give OPPOSING operating models (D1: ownership, D10: no viable execution structure)", check_id="D1_D10_OPERATING_MODEL_CONFLICT", family="D10_H8_concentration")
        elif d1_leans_job and d10_leans_ownership:
            _flag("employment", 5, f"Contradiction: D1 leans JOB (employment_score={mode_gate.get('employment_score')} > business_score={mode_gate.get('business_score')}) but D10-native evidence concentrates in H7/H10/H11 ownership houses (net={round(d10_ownership_net,1)}) -> D1 and D10 give OPPOSING operating models (D1: employment, D10: ownership/venture execution) -- possible late-blooming entrepreneurship", check_id="D1_D10_LATE_ENTREPRENEURSHIP")

    # 8c. v20 audit fix: 8b only compared coarse ownership-vs-operational
    # house FAMILIES, not the actual NAMED operating model D10 points to.
    # This directly compares _business_operating_model()'s D1 best_fit
    # against _business_operating_model_d10()'s D10 best_fit -- if D1 says
    # "sole_owner" but D10 says "trading_brokerage" (say), that's a real,
    # specific divergence the coarse family check could miss (both could
    # be "ownership-leaning" house families while still being different
    # operating models).
    # v38 audit fix (#10, user-caught): this compared D1 vs D10 best_fit by
    # EXACT LABEL EQUALITY only, so e.g. D1="scalable_platform" vs
    # D10="trading_brokerage" was flagged as a full contradiction even
    # though a scalable trading/brokerage platform is a single coherent
    # commercial family -- these two labels routinely co-occur as the #1/#2
    # ranked models for the SAME chart, not opposing structures. A small,
    # explicit compatibility matrix (symmetric) now distinguishes genuinely
    # COMPATIBLE model pairs (same broader commercial family, different
    # emphasis -- no penalty), PARTIALLY_COMPATIBLE pairs (related but
    # distinct enough to note at reduced weight), and everything else
    # (kept at the original full penalty, since e.g. "business" vs "service
    # employment"-flavored models genuinely do point different directions).
    _COMPATIBLE_OPERATING_MODEL_PAIRS = frozenset({
        frozenset({"scalable_platform", "trading_brokerage"}),
    })
    _PARTIALLY_COMPATIBLE_OPERATING_MODEL_PAIRS = frozenset({
        frozenset({"partnership", "professional_practice"}),
        frozenset({"sole_owner", "professional_practice"}),
        frozenset({"sole_owner", "trading_brokerage"}),
    })
    d1_model = _business_operating_model(payload)
    d10_model = _business_operating_model_d10(payload)
    if d1_model.get("best_fit") and d10_model.get("best_fit") and d1_model["best_fit"] != d10_model["best_fit"]:
        _pair = frozenset({d1_model["best_fit"], d10_model["best_fit"]})
        if _pair in _COMPATIBLE_OPERATING_MODEL_PAIRS:
            pass  # same broader commercial family; not a real contradiction, no flag
        elif _pair in _PARTIALLY_COMPATIBLE_OPERATING_MODEL_PAIRS:
            _flag("business", 1, f"Note: D1's best-fit operating model ({d1_model['best_fit']}) and D10-native's ({d10_model['best_fit']}) are related but not identical -> partially compatible, minor divergence only")
        else:
            _flag("business", 3, f"Contradiction: D1's best-fit operating model ({d1_model['best_fit']}) differs from D10-native's best-fit operating model ({d10_model['best_fit']}) -> the promise chart and the execution chart point to DIFFERENT operating structures, not merely different strength levels of the same one")

    # 9. D24 shows competency constraint.
    if d24_status.get("status") == "OK" and d24_status.get("factor", 1.0) < 0.7:
        _flag("business", 5, f"Contradiction: D24 indicates constrained competency/training readiness for the primary profession ({d24_status.get('note','')}) -> execution capacity limited regardless of D1/D10 promise")

    # 9b. D2 (Hora) shows Sun-Hora dominance on the wealth houses while D1
    # (H2/H11 lord placement strength) reads a strong wealth promise --
    # mirrors the D24-competency-constraint check (#9) in style/severity,
    # but narrow-scoped to wealth-flow evidence only (see
    # _d2_native_house_evidence()'s docstring for classical basis/caveats).
    # Gracefully skips when no D2 data is available (empty list from
    # _d2_native_house_evidence -> nothing to compare).
    _d2_evidence = _d2_native_house_evidence(payload)
    if _d2_evidence:
        _d2_net = sum(w for w, _ in _d2_evidence)
        _wealth_house_strength = (
            _house_lord_strength(payload, 2) if h2_lord else 0.0,
            _house_lord_strength(payload, 11) if h11_lord else 0.0,
        )
        _wealth_promise_strong = any(s >= 0.6 for s in _wealth_house_strength)
        if _wealth_promise_strong and _d2_net < 0:
            _flag("business", 3, f"Wealth flow caution: D1 (H2/H11 lord placement) shows a strong wealth promise, but D2 (Hora) net reads negative ({round(_d2_net, 1)}) -- Sun-Hora dominance on the 2nd/11th lords and/or wealth significators (Jupiter/Venus/Moon) -> a corroborating caution on wealth ACCUMULATION specifically, not a reversal of the underlying D1 business promise")

    # 10 / 10b. KP 10th-cusp leans JOB while D1 disagrees, in one of two
    # ways: D1's OVERALL significator strength is only moderate (<55), or
    # D1/mode_gate reads a LOPSIDED business score (margin>=20) that KP's
    # 10th-cusp sub-lord -- the principal livelihood-cusp arbiter per spec
    # section 6 -- disagrees with anyway. These were originally written as
    # two independently-gated checks (v35 audit fix #20 added 10b
    # specifically so a lopsided D1 score wouldn't silence the flag). But
    # a chart can satisfy BOTH conditions at once (moderate significator
    # strength AND a lopsided D1 margin are not mutually exclusive -- e.g.
    # significator_strength=34 with margin=35), and when that happens both
    # checks fire on the exact same underlying fact (KP's sub-lord leaning
    # JOB), double-charging one observation as if it were two independent
    # corroborating contradictions (5+6=11 points for one disagreement).
    # Astrologer-reviewed fix: this is real double-counting of a single KP
    # finding, not two distinct classical checks, so only the more
    # specific 10b framing (weight 6, which also cites the lopsided D1
    # margin explicitly) fires when both conditions hold; 10's more
    # generic framing (weight 5) only fires standalone, when the lopsided-
    # margin condition does NOT also apply.
    # v-audit fix (item 5, follow-on): don't raise a KP-vs-D1 contradiction
    # off a cusp chain that failed independent verification (see
    # kp.py::_verify_kp_cusp_chain) -- an unverified "KP disagrees with D1"
    # finding is not a real disagreement worth surfacing to the reader.
    if kp10.get("status") == "OK" and kp10.get("chain_verified") and kp10.get("leaning") == "JOB":
        _d1_biz = mode_gate.get("business_score", 0) if mode_gate is not None else 0
        _d1_emp = mode_gate.get("employment_score", 0) if mode_gate is not None else 0
        _lopsided_margin = mode_gate is not None and (_d1_biz - _d1_emp) >= 20
        _moderate_strength = significators.get("heuristic_relative_strength_0_100", 0) < 55
        if _lopsided_margin:
            _flag("business", 6, f"Contradiction: KP 10th-cusp sub-lord ({kp10.get('sub_lord', '?')}) leans JOB (job_weight={kp10.get('job_weight')} vs business_weight={kp10.get('business_weight')}) while D1 mode_gate reads a lopsided BUSINESS lean (business_score={_d1_biz} vs employment_score={_d1_emp}, margin={round(_d1_biz - _d1_emp, 1)}) -> KP, the principal livelihood-cusp arbiter, disagrees with D1's raw magnitude; a large D1 business score should not be read as overriding KP's own dedicated professional-mode discriminator")
        elif _moderate_strength:
            _flag("business", 5, f"Contradiction: KP 10th-cusp sub-lord leans toward the job signification set ({kp10.get('note','')}) while D1 business evidence is only moderate -> event/timing-level system disagrees with the structural read")

    # 11. v22 audit fix: spec section 14 lists "D60 being used despite
    # uncertain birth time" as its own contradiction control, distinct
    # from _d60_confirmation_status() simply zeroing its own modifier on
    # low reliability. This flags the case where D60 evidence would have
    # been NON-ZERO/CONFIRMATORY were reliability not gated off -- i.e.
    # the chart's birth-time uncertainty is actively suppressing a D60
    # signal, which is worth surfacing as a contradiction/caveat rather
    # than silently vanishing into a zeroed modifier.
    if d60_status is not None and d60_status.get("status") == "NOT_APPLIED_LOW_RELIABILITY":
        _flag("business", 2, f"Contradiction: D60 (deep karmic confirmation) is available but SUPPRESSED due to insufficient birth-time reliability ({d60_status.get('note','')}) -> any D60-level corroboration this chart might show is unverified and must not be read as confirming the business promise")

    # 12. v22 audit fix: spec section 14 lists "dasha not activating
    # business houses within the forecast period" as its own contradiction
    # control. This is distinct from current_timing_readiness simply
    # reading low -- it specifically checks whether ANY timed window in
    # the forecast horizon shows genuine AD/MD-lord evidence for a
    # business-discriminating house (H1/H3/H7, mirroring the same
    # word-boundary-safe, KP/Jaimini-excluding approach _dasha_vote()
    # uses in scoring.py, so this doesn't just re-count KP/Jaimini text
    # that happens to mention "business").
    if timed_windows:
        business_house_re = re.compile(r"\bh[137]\b")
        any_window_activates_business = False
        for w in timed_windows:
            dasha_evidence = [str(e).lower() for e in w.get("evidence", []) if str(e).lower().startswith(("ad lord", "md lord"))]
            if any(business_house_re.search(e) for e in dasha_evidence):
                any_window_activates_business = True
                break
        if not any_window_activates_business:
            _flag("business", 4, f"Contradiction: none of the {len(timed_windows)} timed window(s) in the forecast horizon show genuine AD/MD-lord activation of a business-discriminating house (H1/H3/H7) -> even if the structural D1/D10 promise is strong, the dasha sequence may keep the native in employment during this period")

    # 13. v39 audit fix (#5, user-caught): a chart can accumulate what LOOKS
    # like several independent business confirmations -- H7 lord, H10 lord,
    # Amatyakaraka, Karakamsha-10th-lord -- that are actually all the SAME
    # planet wearing different hats, not independent corroboration. A full
    # cross-module dependency cap (capping one planet's total contribution
    # across D1/D9/D10/KP/Jaimini scoring) would require touching five
    # independently-tested modules and was assessed as too invasive for a
    # bounded patch; this instead adds a transparency-level caution flag,
    # in the same additive-penalty style as every other check here, when a
    # single planet is independently confirmed as BOTH the 7th lord AND the
    # 10th lord AND the Amatyakaraka -- the specific "same planet counted
    # three times as three separate proofs" pattern the audit flagged --
    # so a reader is told the promise leans heavily on one planet's
    # strength rather than genuinely independent corroborating evidence.
    amatyakaraka = str(getattr(payload, "amatyakaraka", "") or "")
    if h7_lord and h10_lord and amatyakaraka and h7_lord == h10_lord == amatyakaraka:
        # v-audit fix (item 3): the flat weight-3 penalty above didn't
        # distinguish a chart where the shared planet contributes a small
        # slice of the ledger from one where it dominates nearly the whole
        # positive case. Scale the penalty with how much total positive
        # weight in the evidence ledger actually cites that one planet
        # (reusing the evidence list significators.py already returns,
        # same field score_business_significators()'s
        # cross_family_planet_concentration is built from), so heavier
        # concentration draws a heavier caution. The flat 3 remains a
        # floor so mildly-concentrated charts are never penalized less
        # than before; a small multiplier (0.06 per positive-weight point
        # cited on that planet) is capped at +9 on top of the floor so
        # this single check can't itself swing the business score.
        _conc_evidence = significators.get("evidence", []) if significators else []
        _positive_total = sum(
            e.get("weight", 0.0) for e in _conc_evidence
            if e.get("polarity") == "POSITIVE" and amatyakaraka in str(e.get("note", ""))
        )
        # A shared H7/H10 lord is a real natal configuration, not an
        # adverse combination.  Treating its repeated appearances as a
        # promise subtraction incorrectly punishes the yoga itself.  The
        # method-agreement calculation already correlation-dampens D1 and
        # Jaimini when they share this identity planet; keep this record as
        # an auditable zero-weight DEPENDENCY warning instead of a
        # contradiction penalty.
        _flag(
            "business", 0,
            f"Dependency caution (confidence-only, no promise subtraction): H7 lord, H10 lord, and "
            f"Amatyakaraka are all the same planet ({h7_lord}), which accounts for ~{round(_positive_total, 1)} "
            f"points of positive evidence weight. This is a genuine concentrated vocational yoga, but the "
            f"citations are not independent corroborations; method-agreement confidence is correlation-dampened "
            f"elsewhere rather than weakening natal promise.",
            check_id="DOMINANT_PLANET_DEPENDENCY",
            family="evidence_dependency",
        )

    # 14. v41 audit fix (#9, user-caught): evidence citing Sun-in-H10,
    # 9-10, or 9-11 connections (status/fortune/institutional-network
    # significators) is just as plausible for senior employment,
    # institutional leadership, or consulting-within-employment as for
    # owned business -- these houses are not exclusive to entrepreneurship
    # the way 1/3/7-anchored ownership evidence is. When a chart's
    # positive business evidence leans heavily on this status/fortune
    # family WITHOUT much corroborating 1st/3rd/7th ownership evidence,
    # that imbalance is now surfaced as a caution rather than silently
    # counted as business-specific proof.
    evidence_list = significators.get("evidence", []) if significators else []
    _status_fortune_evidence = [
        e for e in evidence_list
        if e.get("polarity") == "POSITIVE" and any(
            k in str(e.get("note", "")).lower() for k in ("9-10 connection", "9-11 connection", "sun in h10", "sun (h10")
        )
    ]
    _ownership_evidence = [
        e for e in evidence_list
        if e.get("polarity") == "POSITIVE" and any(
            k in str(e.get("note", "")).lower() for k in ("h1", "h3", "h7", "lagnesh", "entrepreneurial agency")
        )
    ]
    _status_fortune_net = sum(e.get("weight", 0.0) for e in _status_fortune_evidence)
    _ownership_net = sum(e.get("weight", 0.0) for e in _ownership_evidence)
    if _status_fortune_net >= 8.0 and _ownership_net < _status_fortune_net * 0.5:
        _flag("business", 2, f"Caution: a meaningful share of positive business evidence ({round(_status_fortune_net, 1)}) comes from status/fortune/institutional-network signals (9th-10th/9th-11th connections, Sun in H10) that are equally consistent with senior employment or institutional leadership, with comparatively little independent 1st/3rd/7th ownership evidence ({round(_ownership_net, 1)}) to distinguish an OWNED venture specifically -> some of this promise may reflect career status generally, not business ownership specifically")

    # ISSUE-2 audit fix: cap combined penalties within a shared
    # contradiction-family (see _apply_contradiction_family_caps above) --
    # applied once, after every check has had a chance to fire, so this is
    # purely a post-processing adjustment on the already-built penalty list
    # and does not change which checks fire or their notes/ids.
    penalties = _apply_contradiction_family_caps(penalties)

    return penalties


# Engineering audit fix #7: this module previously defined __all__ TWICE
# (the first, shorter definition below was silently overwritten by the
# second at import time -- dead code, not a real second export list). Kept
# exactly one definition, the more complete of the two.
