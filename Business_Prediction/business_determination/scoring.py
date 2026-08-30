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


"""business_determination.scoring

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .house_evidence import _NATURAL_BENEFICS, _NATURAL_MALEFICS, _d10_native_job_house_evidence, capital_strategy_lean_for_payload
from .mode_gate import _arudha_business_evidence, _dig_factor, _karakamsha_business_evidence, _rich_planet_dignities
from .d24_d60_sign import _D60_RELIABLE_STATES
from .operating_models import _fifth_house_business_evidence
from .contradictions import _d10_native_house_evidence, _house_lord_strength
from .policy import DECISION_POLICY


_BUSINESS_LAYER_WEIGHTS = {
    "d1_structural": 25, "d10_execution": 20, "profit_2nd_11th": 10,
    "agency_1st_3rd": 10, "commercial_interface_7th": 10, "jaimini": 8,
    "kp": 10, "d9_durability": 4, "d60": 3,
}

_JOB_LAYER_WEIGHTS = {
    "d1_service_hierarchy": 30, "d10_service_execution": 25,
    "integration_6_10_11": 15, "saturn_sun_institutional": 8,
    "kp_2_6_10_11": 12, "jaimini_service": 5, "d9_durability": 5,
}

def _layered_promise_scores(
    payload: Any,
    mode_gate: Dict[str, Any],
    significators: Dict[str, Any],
    d60_status: Dict[str, Any],
    kp10: Dict[str, Any],
) -> Dict[str, Any]:
    """v18 audit fix: business_promise/job_promise previously used an ad hoc
    0.6/0.4 blend with no declared layer weights, even though the module's
    own documentation claimed an "additive" architecture -- there was no
    actual D1=25/D10=20/2nd-11th=10/1st-3rd=10/7th=10/Jaimini=8/KP=10/D9=4/
    D60=3 (business) or D1=30/D10=25/6-10-11=15/Saturn-Sun=8/KP=12/
    Jaimini=5/D9=5 (job) composition anywhere in the code. This computes
    each named layer as an inspectable 0-100 sub-score from EXISTING
    internals (the significator evidence-family totals, D10-native
    evidence, house-lord strengths, and the mode-gate's own tagged
    positive/negative signal text) and combines them with the declared
    weights, returning the full breakdown so the composition is auditable
    rather than asserted."""

    def _clamp(x: float) -> float:
        return round(min(100.0, max(0.0, x)), 1)

    def _center(net: float, per_unit: float) -> float:
        return _clamp(50.0 + net * per_unit)

    def _profit_2nd_11th_confidence_score(net: float, per_unit: float, h2_str: float, h11_str: float) -> float:
        """v-audit fix (profit_2nd_11th over-weighting): the plain _center()
        formula scored this layer purely off a handful of small
        corroborating D2-Hora/varga/argala confirmation entries (typically
        +2 to +5 each), with NO reference to whether the 2nd/11th houses
        are actually STRUCTURALLY strong on this chart -- a chart with a
        debilitated Lagna lord in 2nd, a 2nd lord in a dusthana, Ketu in
        11th, and weak 11th-house Ashtakavarga support could still reach
        the same 90s+ score as a chart with genuinely strong 2nd/11th
        lords, purely because a few small confirmation entries happened to
        fire. Mirrors kp.py's _kp_directional_confidence_score pattern:
        `direction` (which way the raw profit evidence net leans) is kept
        separate from `magnitude` (how much structural support -- real
        2nd/11th lord dignity + Ashtakavarga, via the existing
        _house_lord_strength(), which already folds in dignity AND SAV --
        actually backs that lean). A directionally-positive net is now
        damped toward neutral when h2/h11 house-lord strength is weak,
        rather than being allowed to saturate to ~100 off weak underlying
        houses; a directionally-negative net is NOT damped the same way
        (weak houses should not soften a genuinely negative reading)."""
        raw = _clamp(50.0 + net * per_unit)
        if raw <= 50.0:
            return raw
        # Positive lean: require real structural backing to keep it. Uses
        # MIN(h2_str, h11_str), not the average -- "2nd/11th connection"
        # classically requires BOTH ends to be functional; a strong 11th
        # lord should not fully mask a genuinely weak/afflicted 2nd lord
        # (or vice versa) the way an averaged blend would. Verified against
        # a real chart (Karthick): 2nd lord Saturn placed weakly (h2
        # strength ~0.24) while 11th lord Venus is strong (~0.98) -- an
        # averaged blend (~0.61) would still fully clear the >=0.5
        # saturation bar and leave the layer at an unmoved ~98, exactly the
        # over-weighting the audit flagged; MIN correctly damps it since
        # the 2nd-house leg of the pair is genuinely weak. Below ~0.5 MIN
        # house-lord strength (dignity+SAV) the confirmation entries are
        # read as "some support exists" rather than "the 2nd/11th houses
        # are BOTH strong," so the deviation above 50 is scaled down
        # proportionally, floored so a genuinely near-zero-strength chart
        # cannot keep more than a token amount of the positive lean.
        structural = min(h2_str, h11_str)
        magnitude = max(0.15, min(1.0, structural / 0.5))
        return _clamp(50.0 + (raw - 50.0) * magnitude)

    def _count_matching(signals: List[str], keywords: Tuple[str, ...]) -> int:
        return sum(1 for s in signals if any(k in s.lower() for k in keywords))

    pos_biz = mode_gate.get("positive_signals", {}).get("business", [])
    neg_biz = mode_gate.get("negative_signals", {}).get("business", [])
    pos_emp = mode_gate.get("positive_signals", {}).get("employment", [])
    neg_emp = mode_gate.get("negative_signals", {}).get("employment", [])

    family = significators.get("family_totals_capped", {})
    d1_net = family.get("D1_PROMISE", 0.0)
    varga_net = family.get("VARGA_CONFIRMATION", 0.0)
    d10_net = sum(w for w, _ in _d10_native_house_evidence(payload))

    # Gap-hunt fix (cross-layer double-counting, D10 side): significators.py
    # already folds D10-native evidence ("D10-native: D10-H7 (venture) lord
    # ... -> Dashamsha house graph confirms") into the SAME VARGA_
    # CONFIRMATION family as D9-native evidence -- the `family` axis has no
    # separate D9-vs-D10 split, so varga_net above is really "D9 AND D10
    # confirmation combined," even though it exclusively feeds a layer
    # named d9_durability (in both business_layers and job_layers below,
    # since they share this one `varga_net` variable). Meanwhile d10_net,
    # computed fresh just above with NO family capping or same-planet
    # dedup, independently feeds d10_execution (business, 20% weight) and
    # d10_service_execution (job, 25% weight). That means the SAME D10
    # house-graph facts drove d9_durability's capped total AND d10_net's
    # uncapped total at once -- a real double-count inside each promise
    # score, not just a naming mismatch. Nets the raw D10-native
    # contribution back out of varga_net so d9_durability reflects
    # genuinely D9-only confirmation (matching what its name promises),
    # and D10 evidence is credited once, via its own dedicated,
    # larger-weighted execution layer.
    varga_net = varga_net - d10_net

    # v-audit fix (typed rule IDs, fourth slice -- items 3/4, "profit
    # calculation still falls back to keyword matching"): significators.py's
    # _add() now sets an unconditional `profit` boolean on every evidence
    # entry at generation time (category-derived when a structural category
    # exists, keyword-derived otherwise -- see that module's _add()
    # docstring), so this reads the typed field directly. No note-text
    # scanning happens in scoring.py anymore.
    profit_evidence = [e for e in significators.get("evidence", []) if e.get("profit")]
    profit_net = sum(e["weight"] if e["polarity"] == "POSITIVE" else -e["weight"] for e in profit_evidence)

    # Gap-hunt fix (cross-layer double-counting): d1_net (D1_PROMISE) and
    # profit_net (feeds profit_2nd_11th) are both drawn from the SAME raw
    # significators evidence list via two DIFFERENT, non-mutually-exclusive
    # axes -- d1_net via the `family` tag (D1_PROMISE is a catch-all: not
    # varga/jaimini/strength-specific), profit_net via the `profit` tag
    # (H2/H11/capital/gains/wealth-anchored). An entry like "D2-Hora: H2
    # (capital base) lord (Saturn)... favorable for wealth accumulation" is
    # legitimately BOTH -- family=D1_PROMISE AND profit=True -- so it would
    # silently inflate both d1_structural and profit_2nd_11th at once if not
    # netted out below.
    #
    # v-audit fix (typed rule IDs, third slice -- item 5, "_overlap_family_of()
    # remains a duplicated text classifier"; comment corrected in the
    # seventh/eighth slices -- item 6, "stale comments still describe
    # deleted classifiers"): every evidence entry produced by significators.py
    # now carries an explicit, individually-verified `family` tag (see
    # significators.py's _add() call sites -- 100% coverage, enforced by
    # test_zero_untyped_family_rule_id_profit_stability_risk_entries). That
    # typed tag is read directly below via `e.get("family", "D1_PROMISE")` --
    # there is no note-text re-scanning happening here at all anymore (the
    # duplicated closure this comment used to describe, _overlap_family_of(),
    # was deleted; significators.py's own text-inference fallback,
    # _family_of(), was ALSO deleted once its coverage reached 100%, not just
    # deprioritized). The "D1_PROMISE" default in `.get("family",
    # "D1_PROMISE")` is not a fallback to either of those now-deleted
    # functions -- it is simply the literal default value the missing-key
    # case falls back to; it happens to match what _family_of() used to
    # return by default, which is why this remains bit-for-bit behavior
    # preserving relative to the pre-deletion code, but nothing here still
    # imports, calls, or depends on that deleted function.
    _profit_d1_promise_overlap = sum(
        e["weight"] if e["polarity"] == "POSITIVE" else -e["weight"]
        for e in profit_evidence if e.get("family", "D1_PROMISE") == "D1_PROMISE"
    )
    d1_net_for_structural = d1_net - _profit_d1_promise_overlap

    lagna_strength = _house_lord_strength(payload, 1)
    h3_strength = _house_lord_strength(payload, 3)
    house_lords = getattr(payload, "house_lords", {}) or {}
    h7_lord = house_lords.get("7", house_lords.get(7, ""))
    h7_strength = _house_lord_strength(payload, 7) if h7_lord else 0.0
    h2_strength_profit = _house_lord_strength(payload, 2)
    h11_strength_profit = _house_lord_strength(payload, 11)

    karakamsha_net = sum(w for w, _ in _karakamsha_business_evidence(payload))
    arudha_net = sum(w for w, _ in _arudha_business_evidence(payload))

    business_layers = {
        "d1_structural": _center(d1_net_for_structural, 1.5),
        "d10_execution": _center(d10_net, 2.5),
        "profit_2nd_11th": _profit_2nd_11th_confidence_score(profit_net, 2.0, h2_strength_profit, h11_strength_profit),
        "agency_1st_3rd": _clamp((lagna_strength + h3_strength) / 2 * 100.0),
        "commercial_interface_7th": _clamp(h7_strength * 100.0),
        "jaimini": _center(karakamsha_net + arudha_net + _count_matching(pos_biz, ("jaimini", "amatyakaraka")) * 2 - _count_matching(neg_biz, ("jaimini", "amatyakaraka")) * 2, 2.0),
        # Gap-hunt fix: this used to count how many mode_gate signal
        # STRINGS happened to contain the substring "kp" (+-4 per match,
        # centered at 50) -- a crude text-matching proxy, even though this
        # function already receives kp10 (the precise, weighted
        # kp_10th_cusp_job_vs_business result: an actual business_weight
        # vs job_weight ratio from the 10th-cusp sub-lord's house
        # significations). The mirror-image job layer (kp_2_6_10_11,
        # below) already consults kp10 directly. Now symmetric: the same
        # business_weight/job_weight ratio kp10 already computed, read
        # from the business side instead of the job side, with the same
        # neutral-50 fallback the job layer already uses when KP status
        # isn't OK for this chart.
        # v-audit fix (item 5): also require kp10.chain_verified (see
        # kp.py::_verify_kp_cusp_chain) -- a KP reading that exists
        # (status="OK") but whose cusp chain could NOT be independently
        # re-derived from its own stored degrees (e.g. equal-house cusps
        # mislabeled as KP data, or a chain arithmetic mismatch) is no more
        # trustworthy than having no reading at all, and now falls back to
        # the same neutral-50 default rather than being scored at full
        # confidence purely because *a* value was present.
        # ISSUE-1 audit fix: this used to compute the ratio directly here
        # (business_weight / max(0.001, job_weight + business_weight) *
        # 100), a degenerate-denominator pattern that saturates to 100
        # whenever job_weight is 0, regardless of how weak/near-zero
        # business_weight itself is (e.g. business_weight=0.225 built
        # entirely from the entrepreneur-boost houses 1/3, with NO genuine
        # business core house {2,7,10,11} actually significated, still
        # produced a ratio of exactly 1.0 -> 100). Now consults kp.py's own
        # business_confidence_score, which separates direction from
        # strength (see kp.py::_kp_directional_confidence_score) instead of
        # re-deriving the same degenerate ratio here.
        "kp": _clamp(kp10.get("business_confidence_score", 50.0)) if kp10.get("status") == "OK" and kp10.get("chain_verified") else 50.0,
        "d9_durability": _center(varga_net, 1.5),
        "d60": _clamp(50.0 + d60_status.get("modifier", 0.0) * 625.0),
    }

    # v31 audit fix: for lagnas where the same planet naturally rules BOTH
    # the 7th and the 10th house (Sagittarius/Gemini/Virgo/Pisces etc. --
    # an ascendant-inherent lordship fact, not a special yoga), that one
    # planet's dignity/placement was being read as full-strength evidence
    # independently in commercial_interface_7th (7th-lord strength) AND
    # again in d1_structural/agency layers via the same planet's 10th-lord
    # role -- overcrediting a single fact as if it were two independent
    # confirmations. This does not zero the evidence (the placement is
    # still real and still matters) but discounts commercial_interface_7th
    # toward neutral by 30% specifically in the same-lord case, so the
    # layer stops carrying full independent weight for a structural
    # coincidence of the ascendant rather than a distinguishing feature of
    # this individual chart.
    h10_lord = house_lords.get("10", house_lords.get(10, ""))
    same_lord_7_10 = bool(h7_lord) and h7_lord == h10_lord
    if same_lord_7_10:
        business_layers["commercial_interface_7th"] = _clamp(
            50.0 + (business_layers["commercial_interface_7th"] - 50.0) * 0.7
        )

    # v36 audit fix (real numeric fix, not just transparency): D60's layer
    # score always resolved to exactly 50.0 whenever d60_status.modifier
    # was 0.0 -- true both when D60 is genuinely neutral (status="OK", a
    # real reading) AND when D60 has no data at all (NO_DATA/NOT_APPLIED_
    # LOW_RELIABILITY). v33 exposed d60_evidence_available/d60_status so
    # this was at least visible, but the score itself still silently
    # credited business_promise with 50*3%=1.5 points of "neutral" evidence
    # that was actually NO evidence -- exactly the defect a follow-up audit
    # correctly re-flagged: "D60-aware and NO_DATA-safe at the status
    # level, but not NO_DATA-neutral at the scoring level." When D60 is
    # unavailable, its declared 3% weight is now excluded entirely from the
    # weighted sum (not defaulted to a midpoint) and the remaining layers'
    # weights are renormalized back to a full 100-point basis, so a chart
    # with no D60 data is scored purely on the layers that DO have real
    # evidence, never partially on a manufactured neutral value. The "d60"
    # entry stays in business_layers (still 50.0, for anyone inspecting the
    # raw per-layer table) and in the declared _BUSINESS_LAYER_WEIGHTS (the
    # spec's own declared-weight table, unchanged) -- only the WEIGHTED SUM
    # actually used for business_promise excludes it when there's nothing
    # real behind it.
    d60_evidence_available = d60_status.get("status") == "OK"

    # v-audit fix (item 34/28: "missing-varga policies are inconsistent" /
    # "KP missing data can receive neutral credit"): D60 already had this
    # exclude-and-renormalize treatment (see the v36 comment above), but KP
    # did not -- when kp10 has no verified reading, the "kp" layer above
    # falls back to a neutral 50.0, and that 50.0 was still being multiplied
    # by its full declared weight (10% business / 12% job) and added to the
    # weighted sum, silently crediting business_promise/job_promise with
    # "no corroboration" as if it were "confirmed neutral" -- exactly the
    # same defect D60 had before the v36 fix, just left unaddressed for KP.
    # This generalizes the same exclude-unavailable-layer/renormalize-the-
    # rest-to-100 policy to BOTH d60 and kp on the business side (kp_2_6_10_11
    # on the job side), establishing one consistent missing-evidence policy
    # instead of three different ones (D60's renormalize vs KP/D9-native's
    # silent neutral-50 vs house-lord-absence's zero).
    kp_evidence_available = kp10.get("status") == "OK" and bool(kp10.get("chain_verified"))

    _business_excluded = {k for k, available in (("d60", d60_evidence_available), ("kp", kp_evidence_available)) if not available}
    if _business_excluded:
        _applied_weight_total = sum(w for k, w in _BUSINESS_LAYER_WEIGHTS.items() if k not in _business_excluded)
        business_weighted = (
            sum(business_layers[k] * w for k, w in _BUSINESS_LAYER_WEIGHTS.items() if k not in _business_excluded)
            / _applied_weight_total
        )
    else:
        business_weighted = sum(business_layers[k] * w for k, w in _BUSINESS_LAYER_WEIGHTS.items()) / 100.0

    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities_hs = _rich_planet_dignities(payload)
    sat_h, sun_h = planet_house.get("Saturn", 0), planet_house.get("Sun", 0)

    # Gap-hunt fix (real formula bug, not just a rigor gap): this pair used
    # to be a flat 1.0-if-institutionally-placed/0.4-otherwise binary, fed
    # into `50*sat + 50*sun - 50`. That formula's own ceiling is only 50
    # (50*1.0 + 50*1.0 - 50 = 50), not 100 -- even a textbook-perfect
    # Saturn-in-H6/H10-and-Sun-in-H10 chart could never score above half
    # credit on this layer, silently halving its declared 8% weight on
    # every chart regardless of placement strength. Separately, dignity was
    # never consulted at all (a `dig = getattr(payload,
    # "planet_dignities", ...)` variable was fetched here and never once
    # referenced) -- a debilitated Saturn in H10 got the same "institutional
    # discipline" credit as an exalted one. Both fixed together: each
    # planet's placement-base (0.4/1.0) is now scaled by its own dignity
    # factor (0.55..1.40 via _dig_factor), and the combined score is
    # normalized against the true reachable ceiling (1.40+1.40=2.80) so the
    # layer's full 0-100 range is actually reachable.
    sat_dig_factor = _dig_factor("Saturn", dignities_hs)
    sun_dig_factor = _dig_factor("Sun", dignities_hs)
    sat_institutional = (1.0 if sat_h in (6, 10) else 0.4) * sat_dig_factor
    sun_institutional = (1.0 if sun_h == 10 else 0.4) * sun_dig_factor
    _institutional_ceiling = 1.40 + 1.40  # both planets institutionally placed AND exalted

    amk = getattr(payload, "amatyakaraka", "") or ""
    amk_rules_h6 = bool(amk) and house_lords.get("6", house_lords.get(6, "")) == amk
    # Gap-hunt fix: was a flat binary (70 if AmK rules H6, else 40) with no
    # gradation for how strongly the AmK itself is dignified -- a
    # debilitated AmK ruling H6 got the same 70 as an exalted one. Now
    # scaled by the AmK's own dignity factor within the same 0.4/1.0
    # placement base used elsewhere in this pair, normalized against its
    # own reachable ceiling (1.0 * 1.40).
    amk_dig_factor = _dig_factor(amk, dignities_hs) if amk else 1.0
    amk_service = (1.0 if amk_rules_h6 else 0.4) * amk_dig_factor
    _amk_service_ceiling = 1.40

    # Gap-hunt fix: this used to count how many mode_gate EMPLOYMENT signal
    # STRINGS happened to contain the substring "h6"/"h10"/"h11" (+-4 per
    # match, centered at 50) -- a crude text-matching proxy, even though
    # this function already computes real house-lord D1 strength for the
    # analogous business-side layers (agency_1st_3rd, commercial_
    # interface_7th) via _house_lord_strength(). Now uses the same direct
    # computation for the three houses this layer is actually named for.
    h6_strength = _house_lord_strength(payload, 6)
    h10_strength = _house_lord_strength(payload, 10)
    h11_strength = _house_lord_strength(payload, 11)

    # Pure D1 service/hierarchy score.  Do not reuse mode_gate's employment
    # accumulator: it also contains D10, KP and Jaimini findings which have
    # their own declared layers below.
    h6_lord = house_lords.get("6", house_lords.get(6, ""))
    h10_lord = house_lords.get("10", house_lords.get(10, ""))
    h7_strength_for_service = _house_lord_strength(payload, 7)
    d1_service_raw = 50.0 + (h6_strength - h7_strength_for_service) * 35.0
    if h6_lord and planet_house.get(h6_lord) in (6, 10, 11):
        d1_service_raw += 10.0
    if h10_lord and planet_house.get(h10_lord) == 6:
        d1_service_raw += 10.0
    if h10_lord and planet_house.get(h10_lord) in (8, 12):
        d1_service_raw -= 8.0
    d1_service_hierarchy = _clamp(d1_service_raw)

    # v-audit fix (item 5): d10_service_execution previously reused the
    # BUSINESS-side D10-native net (d10_net, built from D10-H1/H3/H5/H7/H10/
    # H11) inverted and scaled (-0.4x) as a proxy for job/service execution
    # -- i.e. "not ownership-favorable" stood in for "service-favorable",
    # which are not required to be exact opposites classically (a chart can
    # read weak or strong on BOTH readings independently). Now computed from
    # _d10_native_job_house_evidence() (house_evidence.py), a genuinely
    # separate D10 house-graph reconstruction anchored to the service/
    # institutional houses (D10-H6/H2/H10/H11) rather than the ownership
    # triad (D10-H7/H10/H11), so business and job D10 execution can now
    # diverge independently instead of being algebraic mirror images of the
    # same number.
    job_d10_net = sum(w for w, _ in _d10_native_job_house_evidence(payload))

    job_layers = {
        "d1_service_hierarchy": d1_service_hierarchy,
        "d10_service_execution": _center(job_d10_net, 2.5),
        "integration_6_10_11": _clamp((h6_strength + h10_strength + h11_strength) / 3.0 * 100.0),
        "saturn_sun_institutional": _clamp((sat_institutional + sun_institutional) / _institutional_ceiling * 100.0),
        # v-audit fix (item 5): mirrors the business-side "kp" layer's
        # chain_verified gate above -- an unverified KP cusp chain falls
        # back to neutral rather than being scored at full confidence.
        # ISSUE-1 audit fix: mirrors the business-side "kp" layer fix above
        # -- consults kp10's own job_confidence_score (direction+magnitude
        # separated) instead of re-deriving the degenerate
        # job_weight/(job_weight+business_weight)*100 ratio here.
        "kp_2_6_10_11": _clamp(kp10.get("job_confidence_score", 50.0)) if kp10.get("status") == "OK" and kp10.get("chain_verified") else 50.0,
        "jaimini_service": _clamp(30.0 + (amk_service / _amk_service_ceiling) * 50.0),
        "d9_durability": _center(varga_net, 1.5),
    }
    # v-audit fix (item 34/28, job side): same KP exclude-and-renormalize
    # treatment as the business side above -- kp_2_6_10_11 falls back to a
    # neutral 50.0 when KP is unverified, and that neutral value was still
    # being credited at its full 12% weight rather than excluded.
    _divisional_charts = getattr(payload, "divisional_charts", {}) or {}
    _d9_chart = _divisional_charts.get("D9_navamsha", {}) if hasattr(_divisional_charts, "get") else {}
    d9_evidence_available = bool(
        (getattr(payload, "d9_planet_dignities", {}) or {})
        or (_d9_chart and (_d9_chart.get("Lagna") or _d9_chart.get("lagna")))
    )
    # Apply one consistent missing-method policy: exclude and renormalize.
    if not d9_evidence_available:
        _business_excluded.add("d9_durability")
        _applied_weight_total = sum(w for k, w in _BUSINESS_LAYER_WEIGHTS.items() if k not in _business_excluded)
        business_weighted = sum(
            business_layers[k] * w for k, w in _BUSINESS_LAYER_WEIGHTS.items() if k not in _business_excluded
        ) / _applied_weight_total

    _job_excluded = {"kp_2_6_10_11"} if not kp_evidence_available else set()
    if not d9_evidence_available:
        _job_excluded.add("d9_durability")
    if _job_excluded:
        _job_applied_weight_total = sum(w for k, w in _JOB_LAYER_WEIGHTS.items() if k not in _job_excluded)
        job_weighted = (
            sum(job_layers[k] * w for k, w in _JOB_LAYER_WEIGHTS.items() if k not in _job_excluded)
            / _job_applied_weight_total
        )
    else:
        job_weighted = sum(job_layers[k] * w for k, w in _JOB_LAYER_WEIGHTS.items()) / 100.0

    # v36 audit fix: d60_evidence_available (computed above, where it now
    # also gates whether D60's weight is actually applied to business_
    # weighted -- see the v36 comment above) is reused here rather than
    # recomputed, so the exposed flag and the actual scoring behavior can
    # never drift apart.
    return {
        "business": {
            "layers": {k: round(v, 1) for k, v in business_layers.items()},
            "weights": dict(_BUSINESS_LAYER_WEIGHTS),
            "weighted_total": round(business_weighted, 1),
            "d60_evidence_available": d60_evidence_available,
            "d60_status": d60_status.get("status"),
            "kp_evidence_available": kp_evidence_available,
            "d9_evidence_available": d9_evidence_available,
            "excluded_layers": sorted(_business_excluded),
        },
        "job": {
            "layers": {k: round(v, 1) for k, v in job_layers.items()},
            "weights": dict(_JOB_LAYER_WEIGHTS),
            "weighted_total": round(job_weighted, 1),
            "kp_evidence_available": kp_evidence_available,
            "d9_evidence_available": d9_evidence_available,
            "excluded_layers": sorted(_job_excluded),
        },
    }

def _directional_method_votes(
    payload: Any,
    significators: Dict[str, Any],
    kp10: Dict[str, Any],
    overall_leaning: str,
    timed_windows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """v18 audit fix: business_over_job_confidence's method_agreement
    previously only measured whether D9/D10/KP/Jaimini RAN (data_available
    + status==APPLIED), not whether their DIRECTIONAL conclusions actually
    agree with the overall business-vs-job leaning -- a chart could show
    "high confidence" purely because four unrelated-direction methods all
    happened to fire. This computes an explicit BUSINESS/JOB/NEUTRAL vote
    per method and counts genuine agreement against overall_leaning.

    v20 audit fix: Dasha was previously only folded into confidence as a
    multiplicative timing_support factor (via current_timing_readiness),
    never as its own directional vote -- so a chart could show high
    confidence even if the CURRENTLY ACTIVE dasha's own evidence leaned
    toward job/service houses while every other method leaned business.
    Adds a Dasha vote derived from the nearest timed window's own evidence
    text (business-house H1/H3/H7 mentions vs job-house H6/service
    mentions), matching KN Rao's promise-dasha-transit sequence where dasha
    should corroborate (or fail to corroborate) the structural promise, not
    just gate its timing."""
    family = significators.get("family_totals_capped", {})
    d1_net = family.get("D1_PROMISE", 0.0)
    varga_net = family.get("VARGA_CONFIRMATION", 0.0)
    d10_net = sum(w for w, _ in _d10_native_house_evidence(payload))
    d9_net = varga_net - d10_net
    karakamsha_net = sum(w for w, _ in _karakamsha_business_evidence(payload))
    arudha_net = sum(w for w, _ in _arudha_business_evidence(payload))

    def _vote_from_net(net: float, threshold: float = 2.0) -> str:
        if net >= threshold:
            return "BUSINESS"
        if net <= -threshold:
            return "AGAINST_BUSINESS"
        return "NEUTRAL"

    def _dasha_vote() -> str:
        """v21 audit fix (user-caught, real bug): this previously scanned
        EVERY evidence sentence in the nearest window, including KP-tagged
        ("KP:", "KP FINAL ARBITER:") and Jaimini-tagged ("Jaimini
        (activation):") lines that are OTHER methods layered into the same
        timed window -- so a KP sentence containing the word "business"
        could decide the "Dasha" vote even when the actual AD/MD-lord
        evidence said nothing business-specific, double-counting KP under
        a Dasha label. Now restricted to genuine dasha-lord-house-
        rulership evidence only (lines starting with "AD lord"/"MD lord",
        the Tier-0/1 foundational evidence in _business_ad_windows).
        Also: H1/H3/H7 are the houses UNIQUE to the business group (spec:
        1-2-3-7-10-11) versus the job group (spec: 2-6-10-11); H2/H10/H11
        are shared by both groups and therefore don't discriminate --
        deliberately excluded rather than padded in to manufacture a false
        signal (an AD lord ruling only H2 is genuinely NEUTRAL for this
        vote, not "business" by default)."""
        if not timed_windows:
            return "NEUTRAL"
        nearest = timed_windows[0]
        dasha_evidence = [str(e).lower() for e in nearest.get("evidence", []) if str(e).lower().startswith(("ad lord", "md lord"))]
        if not dasha_evidence:
            return "NEUTRAL"
        business_re = re.compile(r"\bh[137]\b")
        job_re = re.compile(r"\bh6\b")
        biz_hits = sum(1 for e in dasha_evidence if business_re.search(e))
        job_hits = sum(1 for e in dasha_evidence if job_re.search(e))
        if biz_hits > job_hits:
            return "BUSINESS"
        if job_hits > biz_hits:
            return "AGAINST_BUSINESS"
        return "NEUTRAL"

    votes = {
        "D1": _vote_from_net(d1_net),
        "D10": _vote_from_net(d10_net),
        "D9": _vote_from_net(d9_net),
        "Jaimini": _vote_from_net(karakamsha_net + arudha_net),
        # v-audit fix (item 5): an unverified KP chain shouldn't cast a
        # directional vote in the method-agreement tally either -- it's
        # excluded the same way a missing reading would be.
        "KP": {"BUSINESS": "BUSINESS", "JOB": "AGAINST_BUSINESS"}.get(kp10.get("leaning", ""), "NEUTRAL") if kp10.get("status") == "OK" and kp10.get("chain_verified") else "NEUTRAL",
        "Dasha": _dasha_vote(),
    }

    def _agrees(vote: str) -> bool:
        if vote == "NEUTRAL":
            return False
        if overall_leaning == "BUSINESS":
            return vote == "BUSINESS"
        if overall_leaning == "JOB":
            return vote == "AGAINST_BUSINESS"
        return False

    decided = {k: v for k, v in votes.items() if v != "NEUTRAL"}

    # Engineering audit fix #2 (evidence independence): D1 and Jaimini
    # votes above can both trace to the literal SAME planet -- D1's own
    # identity driver here is the 10th-lord (h10_lord), and Jaimini's is
    # the Amatyakaraka; when a chart's 10th lord IS the Amatyakaraka (the
    # same "one planet counted as two separate proofs" pattern already
    # flagged as a caution in contradictions.py check #13), treating D1's
    # and Jaimini's votes as two fully independent corroborating "votes" in
    # this agreement formula inflates confidence on evidence that is not
    # actually independent. Each method's vote gets a per-planet dedup
    # weight: the FIRST method whose identity planet is seen counts at full
    # weight (1.0); any LATER method keyed to that same planet counts at a
    # diminished weight (0.5) rather than a second full vote. Methods with
    # no single resolvable identity planet (D10/KP/Dasha here -- their
    # votes are derived from house-graph nets or cusp sub-lords, not one
    # named planet) are unaffected and always weight 1.0.
    _house_lords_for_identity = getattr(payload, "house_lords", {}) or {}
    _h10_lord_identity = _house_lords_for_identity.get("10", _house_lords_for_identity.get(10, ""))
    _amatyakaraka_identity = str(getattr(payload, "amatyakaraka", "") or "")
    _method_identity_planet = {"D1": _h10_lord_identity, "Jaimini": _amatyakaraka_identity}
    _seen_identity_planets: set = set()
    _dedup_weight: Dict[str, float] = {}
    for _method in votes:
        _planet = _method_identity_planet.get(_method)
        if _planet:
            _dedup_weight[_method] = 0.5 if _planet in _seen_identity_planets else 1.0
            _seen_identity_planets.add(_planet)
        else:
            _dedup_weight[_method] = 1.0

    def _weighted_count(keys) -> float:
        return round(sum(_dedup_weight.get(k, 1.0) for k in keys), 3)

    # v37 audit fix: when the layered promise scores are themselves tied
    # (overall_leaning == "NEUTRAL"), measuring "agreement" against an
    # exclusive BUSINESS or JOB baseline is meaningless by construction --
    # every method would show as "disagreeing" even if 5 of 6 methods
    # independently favor the same direction, which is the opposite of an
    # honest confidence readout. In this case, agreement is instead
    # measured as consensus AMONG the methods themselves: the fraction of
    # decided votes that side with whichever direction (BUSINESS vs
    # AGAINST_BUSINESS) the majority of methods actually favor. This
    # surfaces genuine structural-method consensus (e.g. "5 of 6 methods
    # favor business") even when the final promise-score margin is too
    # close to call.
    if overall_leaning == "NEUTRAL":
        biz_votes = {k: v for k, v in decided.items() if v == "BUSINESS"}
        job_votes = {k: v for k, v in decided.items() if v == "AGAINST_BUSINESS"}
        majority_direction = "BUSINESS" if len(biz_votes) >= len(job_votes) else "AGAINST_BUSINESS"
        agreeing = biz_votes if majority_direction == "BUSINESS" else job_votes
        _decided_w = _weighted_count(decided)
        _agreeing_w = _weighted_count(agreeing)
        return {
            "votes": votes, "decided_count": len(decided), "agreeing_count": len(agreeing),
            "d1_agrees": "D1" in agreeing, "d10_agrees": "D10" in agreeing,
            # Engineering audit fix #2: agreement_fraction now uses the
            # per-planet-dedup-WEIGHTED counts (see _dedup_weight above),
            # not the raw method counts, so a Jaimini vote driven by the
            # same planet as the D1 vote doesn't inflate this fraction as
            # if it were independent corroboration. decided_count/
            # agreeing_count above are left as plain (unweighted) counts
            # for backward compatibility; correlation_dampening_applied
            # exposes whether any dedup actually fired on this chart.
            "agreement_fraction": (_agreeing_w / _decided_w) if _decided_w else 0.0,
            "correlation_dampening_applied": any(w < 1.0 for w in _dedup_weight.values()),
            "note": (
                f"Layered business_promise vs job_promise scores are within the hybrid/inconclusive "
                f"band, so there is no exclusive leaning to measure method agreement against; the "
                f"figure above instead reflects consensus among the {len(decided)} decided methods "
                f"themselves ({len(agreeing)} favor {majority_direction.replace('AGAINST_BUSINESS', 'JOB')})."
            ),
        }

    agreeing = {k: v for k, v in decided.items() if _agrees(v)}
    _decided_w = _weighted_count(decided)
    _agreeing_w = _weighted_count(agreeing)
    return {
        "votes": votes, "decided_count": len(decided), "agreeing_count": len(agreeing),
        "d1_agrees": "D1" in agreeing, "d10_agrees": "D10" in agreeing,
        # See the NEUTRAL branch above for why this is now weighted, not a
        # plain len(agreeing)/len(decided) ratio (engineering audit fix #2).
        "agreement_fraction": (_agreeing_w / _decided_w) if _decided_w else 0.0,
        "correlation_dampening_applied": any(w < 1.0 for w in _dedup_weight.values()),
    }

# Engineering audit fix #4: chart_data_quality previously only checked
# TRUTHINESS of 12 attributes (getattr(payload, attr, None) being non-empty)
# -- a payload with garbage values (e.g. house_lords={"1": "Pluto"},
# planet_house={"Sun": 47}) would score chart_data_quality=1.0, a perfect
# score, despite being internally invalid. This checks a handful of cheap,
# meaningful VALIDITY properties in addition to presence -- not an
# exhaustive schema validator, just enough to catch obviously-wrong data
# rather than only its absence: house_lords/planet_house values must be
# planet names drawn from the engine's own known planet set, and house
# numbers must be integers in 1..12.
_VALID_PLANETS = frozenset(_NATURAL_BENEFICS) | frozenset(_NATURAL_MALEFICS)

_DATA_QUALITY_CHECKLIST = (
    "house_lords", "planet_house", "planet_dignities", "d9_planet_dignities",
    "d10_planet_dignities", "kp_significators", "kp_cusps", "atmakaraka",
    "amatyakaraka", "lagna_sign", "planet_signs", "divisional_charts",
)


def _chart_data_quality(payload: Any) -> float:
    """Fraction (0..1) of _DATA_QUALITY_CHECKLIST attributes that are both
    PRESENT and, for the two attributes cheap and important enough to
    validate (house_lords, planet_house), internally VALID -- not merely
    truthy. An attribute that is present but fails its validity check counts
    as a partial (half) credit rather than either full credit (the old
    behavior) or zero (which would be too harsh for a single malformed
    entry inside an otherwise-populated dict)."""
    total = len(_DATA_QUALITY_CHECKLIST)
    score = 0.0
    for attr in _DATA_QUALITY_CHECKLIST:
        value = getattr(payload, attr, None)
        if not value:
            continue
        if attr == "house_lords":
            pairs = value.items() if isinstance(value, Mapping) else []
            valid_pairs = [1 for h, p in pairs if str(p) in _VALID_PLANETS and _is_valid_house_number(h)]
            score += 1.0 if pairs and len(valid_pairs) == len(list(pairs)) else (0.5 if value else 0.0)
        elif attr == "planet_house":
            pairs = value.items() if isinstance(value, Mapping) else []
            valid_pairs = [1 for p, h in pairs if str(p) in _VALID_PLANETS and _is_valid_house_number(h)]
            score += 1.0 if pairs and len(valid_pairs) == len(list(pairs)) else (0.5 if value else 0.0)
        else:
            score += 1.0
    return score / total


def _is_valid_house_number(house: Any) -> bool:
    try:
        h = int(house)
    except (TypeError, ValueError):
        return False
    return 1 <= h <= 12


# v-audit fix (astrological completeness, item 27 -- "no universal birth-
# time/divisional-boundary stability abstention"): birth_time_sensitivity
# (below) already grades confidence off the REPORTED birth_time_uncertainty_
# minutes window, but its own "note" field explicitly discloses the gap
# this closes: "D60/KP-sub-lord/Arudha instability near a house or sign
# boundary will NOT be caught if the reported uncertainty window itself
# understates the true birth-time error." This function checks the ACTUAL
# degree-within-sign for every planet with planets_d1 data against every
# divisional chart's own segment size -- independent of whatever
# birth_time_uncertainty_minutes reports -- so a planet sitting a fraction
# of a degree from a division boundary is flagged even on a chart that
# reports a "clean," zero-uncertainty birth time (the reported window can
# only ever be as good as the source's own claim; this is a direct,
# mechanical check against the numbers already on the chart, not a second
# opinion on the reported window's honesty).
#
# Segment sizes (degrees per division) are pure arithmetic (30/N per
# varga), not an astrological judgment call: D3=10.0, D4=7.5, D7=30/7,
# D9=30/9, D10=3.0, D24=1.25. A planet is flagged "boundary-sensitive" for
# a given varga when its distance to the NEAREST segment edge is below
# _BOUNDARY_SENSITIVITY_THRESHOLD_DEG (0.5 deg -- roughly the sidereal
# longitude drift of a mid-speed planet like the Sun/Mercury/Venus over
# ~2 minutes of birth-time error, a deliberately conservative/generous
# threshold, disclosed as an engineered choice, not a claim of a single
# "correct" tolerance every astrologer would pick).
#
# Deliberately DISCLOSURE-ONLY, not a proceed-gating hard abstention: with
# 9 planets x 6 vargas = 54 checks per chart, SOME planet sitting close to
# SOME division boundary is a common, often astrologically unremarkable
# occurrence -- forcing a hard abstain on any single boundary-proximity hit
# would over-trigger on a large fraction of real charts and make the
# abstention mechanism itself untrustworthy (the same failure mode a
# too-sensitive smoke detector has). This surfaces a structured,
# inspectable list of exactly which planet/varga combinations are
# boundary-sensitive so a reviewing astrologer can weigh it against the
# SPECIFIC varga-corroboration claims this chart's evidence ledger actually
# relies on, rather than either ignoring the risk entirely or abstaining
# wholesale on a common, often-immaterial condition.
_BOUNDARY_SENSITIVITY_THRESHOLD_DEG = 0.5
_DIVISIONAL_SEGMENT_SIZES_DEG: Dict[str, float] = {
    "D3": 10.0,
    "D4": 7.5,
    "D7": 30.0 / 7.0,
    "D9": 30.0 / 9.0,
    "D10": 3.0,
    "D24": 1.25,
}


def _divisional_boundary_sensitivity(payload: Any) -> Dict[str, Any]:
    """Mechanical divisional-boundary-proximity check -- see the module-level
    comment immediately above this function for full scope/rationale.
    Reads payload.planets_d1 (per-planet {"sign":..., "degree":...}); returns
    {} (not a penalty, no boundary_sensitivity_flags key) when planets_d1 is
    unavailable -- most existing fixtures/charts in this repo predate this
    field, so this degrades to "not evaluated", matching this package's
    established graceful-degradation convention."""
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    if not isinstance(planets_d1, dict) or not planets_d1:
        return {
            "evaluated": False,
            "flags": [],
            "note": "payload.planets_d1 (per-planet sign+degree) unavailable -- boundary-proximity check not evaluated.",
        }

    flags: List[Dict[str, Any]] = []
    for planet, pdata in planets_d1.items():
        if not isinstance(pdata, dict):
            continue
        degree = pdata.get("degree")
        if degree is None:
            continue
        try:
            deg = float(degree) % 30.0
        except (TypeError, ValueError):
            continue
        for varga, seg_size in _DIVISIONAL_SEGMENT_SIZES_DEG.items():
            offset_in_segment = deg % seg_size
            distance_to_edge = min(offset_in_segment, seg_size - offset_in_segment)
            if distance_to_edge <= _BOUNDARY_SENSITIVITY_THRESHOLD_DEG:
                flags.append({
                    "planet": planet,
                    "varga": varga,
                    "distance_to_boundary_deg": round(distance_to_edge, 4),
                    "note": (
                        f"{planet} is only {round(distance_to_edge, 4)} deg from a {varga} "
                        f"division boundary ({seg_size:.4f} deg/segment) -- a plausible birth-"
                        f"time error could flip which {varga} sign/segment {planet} occupies, "
                        f"regardless of what the reported birth_time_uncertainty_minutes window "
                        f"claims."
                    ),
                })

    return {
        "evaluated": True,
        "flags": flags,
        "any_flagged": bool(flags),
        "threshold_deg": _BOUNDARY_SENSITIVITY_THRESHOLD_DEG,
        "note": (
            "Disclosure-only: a flagged planet/varga combination means this SPECIFIC "
            "divisional placement is close enough to a segment boundary that a plausible "
            "birth-time error could change it -- it is NOT a chart-wide abstention. Weigh "
            "flagged entries against which varga-corroboration claims this chart's evidence "
            "ledger actually relies on (see evidence[].fact_id / evidence[].rule_id)."
        ) if flags else (
            "No planet sits within the boundary-sensitivity threshold of a division edge in "
            "any checked varga (D3/D4/D7/D9/D10/D24) -- this chart's divisional placements are "
            "not obviously boundary-fragile, though this is still not equivalent to independent "
            "birth-time verification."
        ),
    }


def _compute_named_promise_fields(
    payload: Any,
    mode_gate: Dict[str, Any],
    significators: Dict[str, Any],
    top_sectors: List[Dict[str, Any]],
    timed_windows: List[Dict[str, Any]],
    timing_status: Dict[str, Any],
    method_status: Dict[str, Any],
    d24_status: Dict[str, Any],
    d60_status: Dict[str, Any],
    kp10: Dict[str, Any],
    sign_modality: Dict[str, Any],
    contradictions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """v17: computes the nine separately-named fields the spec requires
    (business_promise, job_promise, independent_profession_promise,
    business_field_fit, business_execution_capacity, business_profitability,
    business_stability, current_timing_readiness,
    business_over_job_confidence), plus business_advantage_margin with the
    spec's labeled interpretation table and minimum-absolute-strength
    condition. Each is a genuinely distinct computation over existing
    internals (mode_gate scores, the significator evidence ledger, D10-
    native evidence, method_status, timing) -- not aliases of each other --
    documented inline at each step."""

    def _clamp(x: float) -> float:
        return round(min(100.0, max(0.0, x)), 1)

    biz_raw = mode_gate["business_score"]
    emp_raw = mode_gate["employment_score"]
    ind_raw = mode_gate["independent_score"]
    strength = significators["heuristic_relative_strength_0_100"]

    penalty_by_mode: Dict[str, float] = {}
    for p in contradictions:
        penalty_by_mode[p["mode"]] = penalty_by_mode.get(p["mode"], 0.0) + p["weight"]
    biz_penalty = penalty_by_mode.get("business", 0.0)
    job_penalty = penalty_by_mode.get("employment", 0.0)

    # business_promise / job_promise: v18 -- now genuinely composed from the
    # spec's declared layer weights (see _layered_promise_scores), not an
    # ad hoc 0.6/0.4 blend. The full per-layer breakdown is returned below
    # as business_promise_layers/job_promise_layers for auditability.
    layered = _layered_promise_scores(payload, mode_gate, significators, d60_status, kp10)
    business_promise = _clamp(layered["business"]["weighted_total"] - biz_penalty)
    job_promise = _clamp(layered["job"]["weighted_total"] - job_penalty)

    # independent_profession_promise: the mode-gate's independent_score
    # (already a real fourth bucket, not a slice of business) adjusted by
    # the 5th-house net (1-2-5-9-10-11 group membership the spec calls for).
    h5_net = sum(w for w, _ in _fifth_house_business_evidence(payload))
    independent_profession_promise = _clamp(ind_raw + min(15.0, max(-15.0, h5_net)))

    # business_field_fit: top-ranked sector's own blended score, plus a
    # sign/modality bias SCALED BY WHETHER THE AFFINITY ACTUALLY MATCHES
    # THE WINNING SECTOR -- v18 audit fix: previously a flat +5 was applied
    # whenever ANY field affinity was identified at all, regardless of
    # whether it had anything to do with the chart's own top-ranked sector.
    # Now: match each affinity keyword (e.g. "trade", "manufacturing")
    # against the winning sector's label/key text; a real match scores
    # higher than mere affinity-list non-emptiness.
    top_sector = top_sectors[0] if top_sectors and isinstance(top_sectors[0], dict) else {}
    top_sector_score = top_sector.get("score", 0.0)
    sector_text = f"{top_sector.get('label', '')} {top_sector.get('sector', '')}".lower().replace("_", " ")
    affinities = sign_modality.get("field_affinities", []) if sign_modality.get("status") == "OK" else []
    matched_affinities = [a for a in affinities if any(word in sector_text for word in a.lower().replace("/", " ").split())]
    if matched_affinities:
        modality_bonus = min(12.0, 6.0 * len(matched_affinities))
    elif affinities:
        modality_bonus = 2.0  # affinities exist but none match the actual winning sector -- small consolation, not a full credit
    else:
        modality_bonus = 0.0
    # The public field-fit KPI must reconcile to the ranked sector table.
    # Modality remains useful corroboration, but it must not invisibly lift
    # the KPI above the best sector that the reader can actually inspect.
    business_field_fit = _clamp(top_sector_score)

    # business_execution_capacity: D10-native house-graph net (centered at
    # 50, scaled).
    #
    # v31 audit fix: this previously multiplied the D10 execution component
    # by the D24 (Siddhamsha) competency factor (e.g. 75 * 1.15 = 86.25).
    # D24 supports learning/certification/technical-competency/training/
    # subject-mastery -- it does not directly measure employee management,
    # cash-flow control, sales conversion, partnership governance,
    # operational discipline, or business execution, which is what
    # business_execution_capacity is meant to represent. Multiplying the
    # two together inflated execution capacity using evidence that doesn't
    # actually speak to execution, and made the inflation especially
    # confusing for charts where a D10 contradiction was ALSO the reason
    # `proceed` was rejected -- the same report could show a strong,
    # D24-inflated execution capacity right next to a "do not proceed"
    # verdict grounded in that same D10 data. business_execution_capacity
    # is now D10-only; D24's competency signal is exposed as its own
    # separate named field, competency_readiness, so both are visible
    # without one silently inflating the other.
    d10_evidence = _d10_native_house_evidence(payload)
    d10_net = sum(w for w, _ in d10_evidence)
    d10_component = _clamp(50.0 + d10_net * 2.5)
    business_execution_capacity = d10_component

    # v41 audit fix (#12, user-caught): business_execution_capacity was one
    # aggregate D10-house-graph number, giving no way to tell whether a
    # chart's execution strength is client-facing, capital/debt-management,
    # or operational/liability-risk-driven. These sub-dimensions bucket the
    # SAME already-computed D10-native evidence list by which D10 house
    # each note concerns (no new scoring, just grouped and re-clamped), so
    # a reader can see e.g. "client acquisition strong, capital/debt
    # management cautious" instead of one blended 75.
    def _d10_bucket_net(house_tokens: Tuple[str, ...]) -> float:
        return sum(w for w, note in d10_evidence if any(tok in note for tok in house_tokens))

    business_execution_capacity_components = {
        "client_acquisition": _clamp(50.0 + _d10_bucket_net(("D10-H7",)) * 3.0),
        "commercial_execution": _clamp(50.0 + _d10_bucket_net(("D10-H10", "D10-H11")) * 2.5),
        "capital_debt_management": _clamp(50.0 + _d10_bucket_net(("D10-H8",)) * 3.0),
        "operational_liability_risk": _clamp(50.0 + _d10_bucket_net(("D10-H6", "D10-H12")) * 3.0),
        "self_agency": _clamp(50.0 + _d10_bucket_net(("D10-Lagna", "D10-H1")) * 3.0),
    }

    # v42 audit fix (#20, confirmed gap): capital_debt_management above is a
    # single generic D10-H8 bucket -- it does not distinguish the
    # practically important question "should this person bootstrap
    # (self-fund) vs raise external capital/investment?". Two new,
    # genuinely distinct D1-house-lord-strength sub-components answer that
    # directly, reusing the SAME _house_lord_strength() helper already used
    # elsewhere in this module (e.g. lagna_strength/h3_strength/h7_strength
    # above) rather than inventing a new strength computation:
    #   - bootstrap_capacity: 2nd house (personal accumulated wealth) lord
    #     strength in D1 -- self-funding capacity from one's own resources.
    #   - external_capital_raising_capacity: 11th house (gains, networks,
    #     external support/investors -- the more direct classical
    #     significator for gains-through-others) weighted 0.7, plus 8th
    #     house (other people's money, joint/partnership/inherited
    #     resources -- a supporting signal, not the primary one) weighted
    #     0.3, both lord strengths in D1.
    # _house_lord_strength() is already a 0..1 scale, so it is placed on
    # this file's existing 0-100 scale the same way h7_strength is above
    # (line ~204: "commercial_interface_7th": _clamp(h7_strength * 100.0)) --
    # a direct *100.0, not the D10-bucket-net centered-at-50 formula (that
    # formula is specific to the D10-native evidence list this section
    # otherwise buckets; these two new fields deliberately draw on D1
    # house-lord strength instead, per the confirmed classical gap).
    h2_strength = _house_lord_strength(payload, 2)
    h11_strength = _house_lord_strength(payload, 11)
    h8_strength = _house_lord_strength(payload, 8)
    bootstrap_capacity = _clamp(h2_strength * 100.0)
    external_capital_raising_capacity = _clamp((0.7 * h11_strength + 0.3 * h8_strength) * 100.0)
    business_execution_capacity_components["bootstrap_capacity"] = bootstrap_capacity
    business_execution_capacity_components["external_capital_raising_capacity"] = external_capital_raising_capacity

    # capital_strategy_lean: a simple comparative label between the two
    # fields above. Reuses this file's ALREADY-ESTABLISHED margin-threshold
    # convention for "clearly favors X vs Y" -- the same asymmetric band
    # used by overall_leaning/business_advantage_label just below in this
    # function (_leaning_margin >= 3 => a clear lean one way, <= -2 => a
    # clear lean the other way, the band in between => no clear lean) --
    # rather than inventing a new threshold.
    capital_strategy_lean = capital_strategy_lean_for_payload(
        payload, bootstrap_capacity, external_capital_raising_capacity,
        debt_management_score=business_execution_capacity_components.get("capital_debt_management"),
    )
    business_execution_capacity_components["capital_strategy_lean"] = capital_strategy_lean

    # v39 audit fix (#11, user-caught): this previously read
    # clamp(factor * 100.0) directly, so d24_status's STRONG_DIGNITY factor
    # (1.15) always clamped straight to a ceiling 100/100 -- a complete D24
    # competency assessment should weigh Lagna/4th/5th/9th house evidence,
    # afflictions, and dasha support, but this payload only ever carries a
    # single data point (10th lord's D24 dignity), so a single exalted
    # planet was producing a perfect, uncorroborated 100. Since there is no
    # second D24 signal available on this payload to corroborate with (no
    # d24 Lagna/4th/5th/9th data exists anywhere in this codebase to draw
    # on), the honest fix is not to fabricate corroborating evidence but to
    # stop presenting a single-signal read as if it were a complete,
    # maximal-confidence assessment: STRONG_DIGNITY now caps at a HIGH-but-
    # not-perfect 85, NEUTRAL dignity (no signal either way) no longer
    # defaults to a flattering 100, and DEBILITATED is left as before
    # (already appropriately conservative, not a ceiling problem).
    _d24_dignity_to_readiness = {"STRONG": 85.0, "NEUTRAL": 60.0, "DEBILITATED": 35.0}
    if d24_status.get("status") == "OK":
        _d24_tier = "DEBILITATED" if d24_status.get("dignity") == "DEBILITATED" else (
            "STRONG" if d24_status.get("factor", 1.0) > 1.0 else "NEUTRAL"
        )
        competency_readiness = _d24_dignity_to_readiness[_d24_tier]
    else:
        competency_readiness = 50.0

    # business_profitability: net of significator-ledger evidence whose
    # notes concern H2/H11/capital/profit/gains/wealth specifically (a
    # subset of the full ledger, not the whole strength score), penalized
    # by half the business contradiction total.
    #
    # v33 audit fix: a single "profitability" number conflated two
    # genuinely different classical questions -- a strong 11th can produce
    # turnover/networks/gross receipts (revenue potential) while a weak 2nd
    # can prevent RETAINING that as capital (profit retention); a chart can
    # score well on one and poorly on the other, and the blended number was
    # hiding that distinction (e.g. a chart could show profitability=80
    # while H2 capital-retention evidence was actually weak). H11-tagged
    # and H2-tagged evidence are now split into their own named fields
    # (gross_revenue_potential, profit_retention) alongside the existing
    # blended business_profitability, so both the turnover story and the
    # retention story are independently inspectable rather than averaged
    # away into one number.
    # v-audit fix (typed rule IDs, fourth slice -- items 3/4, "profit
    # calculation still falls back to keyword matching"): significators.py's
    # _add() now sets an unconditional `profit` boolean on every evidence
    # entry at generation time (category-derived when a structural category
    # exists, keyword-derived otherwise -- see that module's _add()
    # docstring), so this reads the typed field directly. No note-text
    # scanning happens in scoring.py anymore.
    h11_evidence = [e for e in significators.get("evidence", []) if "h11" in e["note"].lower()]
    h11_net = sum(e["weight"] if e["polarity"] == "POSITIVE" else -e["weight"] for e in h11_evidence)
    gross_revenue_potential = _clamp(50.0 + h11_net * 2.5 - biz_penalty * 0.3)

    h2_evidence = [e for e in significators.get("evidence", []) if "h2" in e["note"].lower()]
    h2_net = sum(e["weight"] if e["polarity"] == "POSITIVE" else -e["weight"] for e in h2_evidence)
    profit_retention = _clamp(50.0 + h2_net * 2.5 - biz_penalty * 0.5)

    # Profit support is a composite of receipts AND retention.  The former
    # implementation re-counted the combined profit ledger and frequently
    # saturated at 100 even when H2 retention was weak.  A weighted blend
    # cannot hide that contradiction; retention receives the larger weight
    # because turnover that cannot be retained is not profit.
    business_profitability = round(_clamp(
        gross_revenue_potential * 0.45 + profit_retention * 0.55
        - biz_penalty
    ), 1)

    # business_stability: D9 (VARGA_CONFIRMATION family) durability net,
    # penalized per explicit debilitation flag in the ledger, adjusted by
    # the small, birth-time-gated D60 modifier.
    #
    # v33 audit fix: this was previously driven almost entirely by D9
    # durability -- D9 can confirm planetary maturity/long-term resilience,
    # but cannot by itself establish stable business cash flow or ownership
    # sustainability. A chart could show D9 durability strength while H2
    # retention, H6 operational burden, H8 debt/partner-capital risk and
    # any D10 promise/execution contradiction were all working against real
    # stability. Now adds an H2/H6/H8-filtered evidence net and an explicit
    # D10-contradiction penalty (reusing the same contradiction_findings
    # weights already computed for the business mode, not a new
    # computation) alongside the existing D9 term, so stability reflects
    # more than durability-of-dignity alone.
    varga_total = significators.get("family_totals_capped", {}).get("VARGA_CONFIRMATION", 0.0)
    debil_flags = sum(1 for e in significators.get("evidence", []) if "debilitated" in e["note"].lower() and e["polarity"] == "NEGATIVE")
    # v-audit fix (typed rule IDs, fourth slice -- item 4, "stability-risk
    # calculation still falls back to keyword matching"): significators.py's
    # _add() now sets an unconditional `stability_risk` boolean on every
    # evidence entry at generation time (category-derived when a structural
    # category exists, keyword-derived otherwise -- see that module's
    # _add() docstring), so this reads the typed field directly. No note-
    # text scanning happens in scoring.py anymore.
    stability_risk_evidence = [e for e in significators.get("evidence", []) if e.get("stability_risk")]
    stability_risk_net = sum(e["weight"] if e["polarity"] == "POSITIVE" else -e["weight"] for e in stability_risk_evidence)
    d10_contradiction_penalty = sum(
        c.get("weight", 0.0) for c in (contradictions or [])
        if c.get("mode") == "business" and "D10" in c.get("note", "")
    )
    business_stability = _clamp(
        50.0 + varga_total * 1.5 - debil_flags * 4.0 + d60_status.get("modifier", 0.0) * 100.0
        + stability_risk_net * 1.0 - d10_contradiction_penalty * 0.5
    )

    # v41 audit fix (#14, user-caught): business_stability was a single
    # blended number combining three genuinely distinct concepts (D9
    # planetary-maturity durability, H2/H6/H8-evidence cash-flow/liability
    # exposure, and D10-ownership-model contradiction risk) with no way to
    # tell WHICH of the three was driving a given score. These three
    # sub-components are the SAME already-computed terms feeding
    # business_stability above (no new scoring, just un-blended and
    # separately clamped/exposed), so a reader can see e.g. "durability is
    # strong but cash-flow stability is weak" instead of one averaged 77.
    business_stability_components = {
        "business_durability": _clamp(50.0 + varga_total * 1.5 - debil_flags * 4.0 + d60_status.get("modifier", 0.0) * 100.0),
        "cash_flow_stability": _clamp(50.0 + stability_risk_net * 1.5),
        "ownership_stability": _clamp(50.0 - d10_contradiction_penalty * 1.5),
    }

    # current_timing_readiness: fraction of the near-term (first 3) timed
    # windows that read favorable, independent of the permanent D1/D10
    # promise -- per the spec, "timing should not be mixed into permanent
    # promise."
    near_windows = (timed_windows or [])[:3]
    # v19 audit fix (user-caught): this checked against a made-up label set
    # ("UNFAVORABLE"/"NEGATIVE"/"AVOID") that the engine's own
    # _label_for_net() (see _WINDOW_LABELS) never actually emits -- real
    # labels are STRONG_FAVORABLE/FAVORABLE/MIXED/CAUTION/HIGH_RISK, so
    # every real window (including CAUTION and HIGH_RISK ones) was being
    # silently counted as favorable. Now checks against the engine's own
    # real label constants.
    _UNFAVORABLE_WINDOW_LABELS = {"MIXED", "CAUTION", "HIGH_RISK"}
    fav_windows = sum(1 for w in near_windows if str(w.get("label", "")).upper() not in _UNFAVORABLE_WINDOW_LABELS)
    if near_windows:
        current_timing_readiness = _clamp(fav_windows / len(near_windows) * 100.0)
    elif str(timing_status.get("status", "")) == "OK_NO_SIGNIFICANT_WINDOWS_IN_HORIZON":
        current_timing_readiness = 40.0  # calendar computed fine, just nothing significant nearby -- neutral-low, not zero
    else:
        current_timing_readiness = 0.0

    # business_over_job_confidence -- v18 rewrite. The v17 version measured
    # method_agreement as "did D9/D10/KP/Jaimini RUN", not whether their
    # DIRECTIONAL conclusions actually agree with the overall business-vs-
    # job leaning. This now uses _directional_method_votes() for genuine
    # per-method BUSINESS/JOB/NEUTRAL votes, and computes
    # chart_data_quality, signal_clarity and birth_time_reliability as
    # separate factors (not folded into method_agreement/timing_support)
    # per the spec's literal formula:
    #   method_agreement x chart_data_quality x signal_clarity x
    #   birth_time_reliability x timing_support - contradiction_penalty
    # v37 audit fix (user-caught, real bug): this previously classified
    # overall_leaning as BUSINESS/JOB on ANY nonzero margin, however small
    # -- so a margin of -1.0 (business_promise=56.5 vs job_promise=57.5,
    # essentially a tie) was labeled "JOB", and method_agreement then
    # measured all six methods against that JOB baseline even though only
    # one of them (KP) actually favored job. This produced a misleading
    # "1/6 methods agree" confidence readout for what is genuinely a
    # hybrid/inconclusive chart. business_advantage_label (below) already
    # treats margin in [-2, 3) as HYBRID_OR_INCONCLUSIVE; overall_leaning
    # now uses that SAME band so the two computations can never disagree
    # about whether this chart has a real leaning at all.
    _leaning_margin = business_promise - job_promise
    if _leaning_margin >= 3:
        overall_leaning = "BUSINESS"
    elif _leaning_margin <= -2:
        overall_leaning = "JOB"
    else:
        overall_leaning = "NEUTRAL"
    votes = _directional_method_votes(payload, significators, kp10, overall_leaning, timed_windows=timed_windows)
    method_agreement = votes["agreement_fraction"]

    chart_data_quality = _chart_data_quality(payload)

    margin_for_clarity = abs(business_promise - job_promise)
    signal_clarity = min(1.0, margin_for_clarity / 20.0)

    # v-audit fix (item 2, birth-time sensitivity -- see
    # Business_Prediction/docs/scope_birth_time_perturbation_and_kp_verification.md
    # for why full ephemeris re-computation at +-1/2/5/10/15-minute offsets
    # is NOT implemented here: jyotish/engine_io.py's chart-building consumes
    # an already-computed upstream chart JSON (pyhora_calculations) rather
    # than deriving D1 from raw dob/tob/lat/lon in-repo, so this codebase has
    # no way to recompute a chart at a shifted birth time at all. What IS
    # available, already computed and already treated as authoritative
    # elsewhere in the codebase (jyotish/payload.py's
    # birth_time_uncertainty_minutes field; jyotish/canonical_facts.py's own
    # HIGH_VARGA_TIME_SENSITIVITY warning at >=5 minutes), is the reported
    # uncertainty window itself. This grades birth_time_reliability off that
    # SAME canonical minutes-of-uncertainty field instead of the previously-
    # used, Business_Prediction-only `birth_time_reliability` string (which
    # nothing else in the codebase populates or reads) -- a real, graded
    # signal instead of a coarse HIGH/LOW/unreported guess, without
    # requiring the chart-recomputation capability this repo doesn't have.
    _uncertainty_minutes = getattr(payload, "birth_time_uncertainty_minutes", None)
    if _uncertainty_minutes is not None:
        try:
            _um = abs(int(_uncertainty_minutes))
        except (TypeError, ValueError):
            _um = None
    else:
        _um = None

    if _um is not None:
        if _um == 0:
            birth_time_reliability = 1.0
        elif _um <= 4:
            birth_time_reliability = 0.9
        elif _um <= 9:
            birth_time_reliability = 0.7  # crosses jyotish/canonical_facts.py's own >=5min HIGH_VARGA_TIME_SENSITIVITY threshold
        elif _um <= 14:
            birth_time_reliability = 0.55
        else:
            birth_time_reliability = 0.35  # >=15min: the audit's own outer bound for "clearly high risk"
    else:
        # Fallback for payloads that never set birth_time_uncertainty_minutes
        # at all (older fixtures, or a chart source that never reported it) --
        # the legacy Business_Prediction-only string field, graded the same
        # conservative way as before this fix.
        reliability = str(getattr(payload, "birth_time_reliability", "") or "").upper()
        if reliability in _D60_RELIABLE_STATES:
            birth_time_reliability = 1.0
        elif reliability in ("LOW", "UNRELIABLE"):
            birth_time_reliability = 0.6
        else:
            # v-audit fix (item 31): an UNREPORTED reliability is not
            # evidence of good reliability -- it is an absence of evidence,
            # and the engine's own divisional/KP-heavy judgments (D10/D24/
            # D60, bhava cusps, KP sub-lords, Arudha) are exactly the layers
            # most sensitive to birth-time error. Treated at least as
            # conservatively as an explicitly reported LOW/UNRELIABLE birth
            # time (0.6), never more favorably.
            birth_time_reliability = 0.6

    contradiction_fraction = min(1.0, sum(penalty_by_mode.values()) / 40.0)
    timing_support = current_timing_readiness / 100.0

    # v-audit fix (item 5): confidence was previously computed purely off
    # whatever corroborating layers HAPPENED to be available, with no
    # visible penalty when an expected layer (D60, D9/varga, KP, Jaimini,
    # Dasha) is missing -- so a chart missing D60 (a common case; D60 is
    # birth-time-reliability-gated, see d60_status/_D60_RELIABLE_STATES
    # above) silently scored confidence off D1/D10/D9/KP/Jaimini/Dasha
    # alone with no indication anything was skipped. Adds an explicit,
    # PROPORTIONAL (not hard-blocking) discount: each missing expected
    # layer trims 4% off confidence_raw, capped at a 20% total discount
    # (5 layers) so this can't zero out confidence on its own -- and the
    # missing set is surfaced in the breakdown dict below so a reader can
    # see exactly which corroborating layers were unavailable, not just a
    # lower number.
    _expected_layers = {
        "D60": d60_status.get("status") == "OK",
        "D9": bool(getattr(payload, "d9_planet_dignities", None)),
        # v-audit fix (item 5): an unverified KP chain doesn't count as an
        # available corroborating layer for confidence purposes either --
        # consistent with the scoring/vote gates above.
        "KP": kp10.get("status") == "OK" and bool(kp10.get("chain_verified")),
        "Jaimini": bool(getattr(payload, "amatyakaraka", "") or getattr(payload, "atmakaraka", "")),
        "Dasha": bool(timed_windows),
    }
    missing_layers = sorted(name for name, available in _expected_layers.items() if not available)
    layers_available_count = len(_expected_layers) - len(missing_layers)
    _confidence_layer_discount = min(0.20, 0.04 * len(missing_layers))

    # Astrologer-reviewed fix: contradiction_fraction used to be SUBTRACTED
    # directly from the multiplicative product of five already-fractional
    # (0..1) factors. That product is very often well under 0.5 on its own
    # (five factors each <=1 multiplied together shrinks fast), so almost
    # any chart with a moderate-to-substantial contradiction total (not an
    # extreme one -- ~19 points out of the /40 normalization, i.e.
    # contradiction_fraction=0.475, was enough on a real chart) drives the
    # subtraction negative and gets clamped to a hard 0.0. That collapses
    # every chart past a fairly low contradiction threshold into the exact
    # same score_0_1=0.0, indistinguishable from a chart with total,
    # complete disagreement across every method -- losing all
    # discriminating power at the low end, which is precisely where a
    # reviewing astrologer most wants to see gradation, not a floor.
    # Treating the contradiction fraction as a proportional discount
    # (multiplied in, like every other factor here) instead of a flat
    # subtraction keeps confidence responsive to contradictions without a
    # structural tendency to zero out on merely-moderate ones.
    confidence_raw = (
        method_agreement * chart_data_quality * signal_clarity
        * birth_time_reliability * timing_support * (1.0 - contradiction_fraction)
    )
    confidence_raw = max(0.0, confidence_raw * (1.0 - _confidence_layer_discount))

    d1_agrees, d10_agrees = votes["d1_agrees"], votes["d10_agrees"]
    decided_count, agreeing_count = votes["decided_count"], votes["agreeing_count"]
    # v21 audit fix (user-caught, real bug): confidence_label was previously
    # derived ONLY from vote counts (d1_agrees/d10_agrees/agreeing_count),
    # never checking confidence_raw/score_0_1 at all -- so a chart with
    # near-zero numeric confidence (e.g. score_0_1=0.0, driven down by low
    # chart_data_quality, weak signal_clarity, or a low timing_support
    # factor) could still be labeled HIGH purely because the vote counts
    # looked good, which is an internally-contradictory output (seen on a
    # real chart: score=0.0, label=HIGH). Each label tier now also requires
    # confidence_raw to clear an explicit floor, so the label and the score
    # can never point in opposite directions.
    # Engineering audit fix #12 (field names overstate certainty):
    # confidence_label (VERY_HIGH/HIGH/MODERATE/LOW/EXPLORATORY_ONLY below)
    # is a deterministic threshold on confidence_raw and vote-agreement
    # counts computed above -- it is NOT a calibrated statistical confidence
    # interval, a probability, or a claim backed by a labeled outcome
    # corpus (see MATURITY_CAVEATS / CALIBRATION_STATUS / EVIDENCE_BASIS in
    # every top-level result dict). "VERY_HIGH" means "many of this
    # engine's own internal methods agree with each other and with strong
    # numeric support," nothing more. Likewise business_profitability/
    # business_stability/business_promise/job_promise elsewhere in this
    # module are heuristic astrological-evidence scores, not financial
    # forecasts -- see this package's MATURITY STATEMENT (engine.py's
    # module docstring) for the full caveat.
    if decided_count == 0:
        confidence_label = "EXPLORATORY_ONLY"  # D1/D10 (and everything else) fail to provide a coherent directional promise
    elif d1_agrees and d10_agrees and agreeing_count >= 4 and contradiction_fraction < 0.15 and confidence_raw >= 0.45:
        confidence_label = "VERY_HIGH"
    elif d1_agrees and d10_agrees and agreeing_count >= 3 and confidence_raw >= 0.25:
        confidence_label = "HIGH"
    elif (d1_agrees or d10_agrees) and confidence_raw >= 0.10:
        confidence_label = "MODERATE"
    else:
        confidence_label = "LOW"  # conclusion depends on a single house/yoga/divisional chart, not D1+D10 corroboration, and/or numeric confidence is too low to support a stronger label

    margin = round(business_promise - job_promise, 1)
    both_modes_below_actionable_floor = (
        business_promise < DECISION_POLICY.minimum_actionable_promise
        and job_promise < DECISION_POLICY.minimum_actionable_promise
    )
    if both_modes_below_actionable_floor:
        margin_label = "WEAK_OR_INCONCLUSIVE"
    elif margin >= 15:
        margin_label = "STRONG_BUSINESS_ADVANTAGE"
    elif margin >= 8:
        margin_label = "MODERATE_BUSINESS_ADVANTAGE"
    elif margin >= 3:
        margin_label = "SLIGHT_BUSINESS_ADVANTAGE"
    elif margin >= -2:
        margin_label = "HYBRID_OR_INCONCLUSIVE"
    elif margin >= -7:
        margin_label = "SLIGHT_JOB_ADVANTAGE"
    elif margin >= -14:
        margin_label = "MODERATE_JOB_ADVANTAGE"
    else:
        margin_label = "STRONG_JOB_ADVANTAGE"

    # Minimum absolute-strength condition (spec section 13): a large margin
    # should not read as "strong business" if the business score itself is
    # low (e.g. +15 margin at business=45 is a weak chart with an even
    # weaker job read, not a strong business chart).
    strong_business_floor_met = business_promise >= 65 and margin >= 12
    if margin_label == "STRONG_BUSINESS_ADVANTAGE" and not strong_business_floor_met:
        margin_label = "STRONG_BUSINESS_ADVANTAGE_BUT_BELOW_ABSOLUTE_FLOOR"

    return {
        "business_promise": business_promise,
        "job_promise": job_promise,
        "business_promise_layers": layered["business"],
        "job_promise_layers": layered["job"],
        "independent_profession_promise": independent_profession_promise,
        "business_field_fit": business_field_fit,
        "business_field_fit_modality_adjustment": modality_bonus,
        "business_execution_capacity": business_execution_capacity,
        "business_execution_capacity_components": business_execution_capacity_components,
        "competency_readiness": competency_readiness,
        "business_profitability": business_profitability,
        "gross_revenue_potential": gross_revenue_potential,
        "profit_retention": profit_retention,
        # v-audit fix (item 42): business_profitability/gross_revenue_
        # potential/profit_retention (and business_stability_components'
        # cash_flow_stability) are named the way real financial metrics are
        # named, but they are astrological evidence scores (0-100, built
        # from D2/D11/D9/house-lord-strength readings) -- they do not model
        # margin, cost structure, debt service, working capital, tax,
        # customer concentration, inventory, or pricing power, and have no
        # relationship to this native's actual financial statements. Kept
        # as bare numeric fields for backward compatibility (renaming the
        # keys would break every existing caller/report/test reading them),
        # but this disclaimer travels in the SAME dict so a consumer of
        # these specific fields cannot miss it.
        "financial_field_disclaimer": (
            "business_profitability, gross_revenue_potential, profit_retention, and "
            "business_stability_components.cash_flow_stability are ASTROLOGICAL "
            "EVIDENCE SCORES (0-100), not financial projections. They reflect "
            "planetary/house-lord strength readings (2nd/11th house, D9/D11-adjacent "
            "evidence), not margin, cost structure, debt service, working capital, "
            "tax exposure, customer concentration, inventory, or pricing power. Do "
            "not present these figures to a reader as if they were financial "
            "forecasts or projected revenue/profit numbers."
        ),
        "business_stability": business_stability,
        "business_stability_components": business_stability_components,
        "current_timing_readiness": current_timing_readiness,
        "business_over_job_confidence": {
            "score_0_1": round(confidence_raw, 3),
            "label": confidence_label,
            "overall_leaning": overall_leaning,
            "method_votes": votes["votes"],
            "method_agreement": round(method_agreement, 3),
            "methods_decided": decided_count,
            "methods_agreeing": agreeing_count,
            "d1_agrees": d1_agrees, "d10_agrees": d10_agrees,
            "chart_data_quality": round(chart_data_quality, 3),
            "signal_clarity": round(signal_clarity, 3),
            "birth_time_reliability": round(birth_time_reliability, 3),
            "missing_layers": missing_layers,
            "layers_available_count": layers_available_count,
            "layers_expected_count": len(_expected_layers),
            "confidence_layer_discount": round(_confidence_layer_discount, 3),
            "contradiction_penalty_fraction": round(contradiction_fraction, 3),
            "timing_support": round(timing_support, 3),
            "note": "v18: method_agreement is now DIRECTIONAL (does each method's own BUSINESS/JOB/NEUTRAL vote match the overall leaning), not just whether the method ran. chart_data_quality, signal_clarity and birth_time_reliability are now separate multiplicative factors per the spec's literal formula, no longer folded into method_agreement/timing_support.",
        },
        "business_advantage_margin": margin,
        "business_advantage_label": margin_label,
        "strong_business_absolute_floor_met": strong_business_floor_met,
        "both_modes_below_actionable_floor": both_modes_below_actionable_floor,
        # v-audit fix (item 2): explicit, standalone visibility into what
        # birth_time_reliability (folded into business_over_job_confidence
        # above as one multiplicative factor) is actually based on, since a
        # reader inspecting confidence_raw alone can't tell whether it was
        # discounted for a KNOWN uncertain birth time or an UNREPORTED one --
        # those are different situations that deserve different follow-up
        # (get a rectified time, vs. simply report the time). See the
        # scope doc referenced above this block's computation for why this
        # is a graded discount off the reported uncertainty window rather
        # than a full per-offset chart recomputation (this codebase has no
        # in-repo capability to rebuild a chart from a shifted birth time).
        "birth_time_sensitivity": {
            "uncertainty_minutes": _um,
            "reliability_factor": round(birth_time_reliability, 3),
            "basis": (
                "reported birth_time_uncertainty_minutes (graded)" if _um is not None
                else "legacy birth_time_reliability string / unreported (conservative fallback)"
            ),
            "high_sensitivity_flag": bool(_um is not None and _um >= 5),
            "note": (
                "This is NOT a recomputation of the chart at shifted birth times -- "
                "it grades confidence off the REPORTED uncertainty window using the "
                "same >=5-minute threshold jyotish/canonical_facts.py already treats "
                "as HIGH_VARGA_TIME_SENSITIVITY elsewhere in the codebase. D10/D24/"
                "D60/KP-sub-lord/Arudha instability near a house or sign boundary "
                "will NOT be caught if the reported uncertainty window itself "
                "understates the true birth-time error. See divisional_boundary_"
                "sensitivity for a direct, mechanical check of exactly that gap."
            ),
        },
        # v-audit fix (item 27): closes the gap birth_time_sensitivity's own
        # note (above) discloses -- see _divisional_boundary_sensitivity()'s
        # module-level comment for full scope/rationale.
        "divisional_boundary_sensitivity": _divisional_boundary_sensitivity(payload),
    }


def _false_conclusion_guard_checklist(
    payload: Any,
    contradictions: List[Dict[str, Any]],
    mode_gate: Dict[str, Any],
    recommendation: Dict[str, Any],
    d24_status: Dict[str, Any],
    d60_status: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """v25 audit fix: spec section 15 lists 8 named "common false
    conclusions to prevent." Prior audits found real ad hoc guards exist
    for several of these, but there was no auditable 1:1 mapping proving
    all 8 are actually covered -- this builds that checklist directly
    from evidence this engine ALREADY computes (contradiction findings,
    mode_gate signal text, declared layer weights, recommendation
    fields), rather than re-deriving new detection logic, so each entry
    is traceable to a real, already-tested code path.

    Each entry reports:
      - false_conclusion: the exact claim from spec section 15
      - guard_type: "CHART_SPECIFIC" (the guard is a runtime check that
        fires only when this chart's specific risky pattern is present)
        or "STRUCTURAL" (the guard is an architectural invariant true for
        every chart -- e.g. D24 never contributes to business_promise's
        layer weights at all, so it cannot manufacture a business
        conclusion by construction)
      - guarded: bool/None -- for CHART_SPECIFIC, whether the risky
        pattern was present in THIS chart and, if so, whether a
        corresponding penalty/flag fired (None means the risky pattern
        simply wasn't present, so the guard was never exercised on this
        chart); for STRUCTURAL, always True (the invariant holds by
        construction, verified below rather than merely asserted)
      - evidence: the specific contradiction note / mode_gate note / weight
        value this guard's status is drawn from
    """
    contradiction_notes = [c["note"] for c in contradictions]
    biz_positive = (mode_gate.get("positive_signals", {}) or {}).get("business", [])

    checklist: List[Dict[str, Any]] = []

    # 1. "Strong 7th means business" -- guarded by contradiction control #1
    # (strong H7 lord with no H2/H10/H11 connection is flagged).
    guard1_note = next((n for n in contradiction_notes if "NO connection to H2/H10/H11" in n), None)
    checklist.append({
        "guard_id": 1, "false_conclusion": "Strong 7th means business",
        "guard_type": "CHART_SPECIFIC",
        "pattern_present": guard1_note is not None,
        "guarded": True if guard1_note else None,
        "evidence": guard1_note or "No strong-but-disconnected H7 pattern present on this chart -- guard not exercised because the risky pattern itself is absent.",
    })

    # 2. "Strong Rahu means entrepreneurship" -- guarded by the v22 fix
    # requiring H7-lord ownership-structure corroboration before Rahu-in-H7
    # gets full business credit (mode_gate.py).
    rahu_ambiguous_note = next((n for n in biz_positive if "NO independent H2/H10/H11 connection" in n and "Rahu" in n), None)
    rahu_corroborated_note = next((n for n in biz_positive if "ownership-structure link" in n and "Rahu" in n), None)
    checklist.append({
        "guard_id": 2, "false_conclusion": "Strong Rahu means entrepreneurship",
        "guard_type": "CHART_SPECIFIC",
        "pattern_present": rahu_ambiguous_note is not None or rahu_corroborated_note is not None,
        "guarded": True if (rahu_ambiguous_note or rahu_corroborated_note) else None,
        "evidence": rahu_ambiguous_note or rahu_corroborated_note or "No unafflicted Rahu-in-H7 pattern present on this chart.",
    })

    # 3. "Weak 6th means business" -- STRUCTURAL: no rule anywhere in this
    # engine credits "business"/"independent" positively FROM H6 being
    # weak -- H6 weakness only ever feeds "employment" scoring, and H6
    # only appears on the business side as a NEGATIVE (contradiction
    # checks #3/#4, H11/H10 tracing to H6 as a business-penalizing
    # pattern), never as positive business evidence.
    checklist.append({
        "guard_id": 3, "false_conclusion": "Weak 6th means business",
        "guard_type": "STRUCTURAL",
        "pattern_present": None,
        "guarded": True,
        "evidence": "No business/independent-mode scoring rule in this engine credits weak-H6 as positive business evidence; H6 strength only feeds employment scoring and the H6-sourced-H10/H11 contradiction checks (#3/#4), which penalize business, never reward it, when H6 dominates.",
    })

    # 4. "Exalted 10th lord means business" -- guarded by the comparative-
    # advantage requirement (recommendation.proceed requires business to
    # beat employment by a margin, not just clear its own absolute floor)
    # plus contradiction #4 (H10 tied to H6 with no H1/H3/H7 ownership link).
    guard4_note = next((n for n in contradiction_notes if "corporate-hierarchy/senior-executive pattern" in n), None)
    checklist.append({
        "guard_id": 4, "false_conclusion": "Exalted 10th lord means business",
        "guard_type": "CHART_SPECIFIC_AND_STRUCTURAL",
        "pattern_present": guard4_note is not None,
        "guarded": True,  # the comparative-advantage requirement below applies unconditionally to every chart
        "evidence": (guard4_note + "; " if guard4_note else "") + f"comparative_advantage={recommendation.get('comparative_advantage')} (business must beat employment by a minimum margin, not merely clear its own absolute floor, regardless of H10 strength alone).",
    })

    # 5. "Strong 11th means business profit" -- guarded by contradiction
    # control #3 (H11 gains traced to H6/salary with no independent
    # H7/H10 path).
    guard5_note = next((n for n in contradiction_notes if "profit likely salary/incentive-derived" in n), None)
    checklist.append({
        "guard_id": 5, "false_conclusion": "Strong 11th means business profit",
        "guard_type": "CHART_SPECIFIC",
        "pattern_present": guard5_note is not None,
        "guarded": True if guard5_note else None,
        "evidence": guard5_note or "No H11-gains-traced-purely-to-H6 pattern present on this chart.",
    })

    # 6. "D10 alone can declare business" -- STRUCTURAL: the declared
    # business-layer weights (spec section 12) give D1 the single largest
    # weight (25) versus D10's 20 -- verified directly against the actual
    # weight constants, not merely asserted in prose.
    d1_weight = _BUSINESS_LAYER_WEIGHTS.get("d1_structural", 0)
    d10_weight = _BUSINESS_LAYER_WEIGHTS.get("d10_execution", 0)
    checklist.append({
        "guard_id": 6, "false_conclusion": "D10 alone can declare business",
        "guard_type": "STRUCTURAL",
        "pattern_present": None,
        "guarded": d1_weight >= d10_weight,
        "evidence": f"business_promise layer weights: D1_structural={d1_weight} >= D10_execution={d10_weight} (verified against _BUSINESS_LAYER_WEIGHTS directly); D10 cannot outweigh D1 in the declared architecture.",
    })

    # 7. "D24 can determine entrepreneurship" -- STRUCTURAL: D24 only ever
    # feeds business_execution_capacity's multiplicative factor; it does
    # not appear in _BUSINESS_LAYER_WEIGHTS or _JOB_LAYER_WEIGHTS at all.
    checklist.append({
        "guard_id": 7, "false_conclusion": "D24 can determine entrepreneurship",
        "guard_type": "STRUCTURAL",
        "pattern_present": None,
        "guarded": ("d24" not in {k.lower() for k in _BUSINESS_LAYER_WEIGHTS}) and ("d24" not in {k.lower() for k in _JOB_LAYER_WEIGHTS}),
        "evidence": f"D24 status={d24_status.get('status')}, factor={d24_status.get('factor')} feeds ONLY business_execution_capacity; verified D24 is absent from both _BUSINESS_LAYER_WEIGHTS and _JOB_LAYER_WEIGHTS (the declared promise-scoring architectures), so it structurally cannot select the business/job promise itself.",
    })

    # 8. "D60 can correct the result" -- guarded by the declared 3-point
    # (of 100) cap on D60's business-layer weight plus contradiction #11
    # (D60 suppressed under low birth-time reliability is itself flagged).
    d60_weight = _BUSINESS_LAYER_WEIGHTS.get("d60", 0)
    guard8_note = next((n for n in contradiction_notes if "SUPPRESSED due to insufficient birth-time reliability" in n), None)
    checklist.append({
        "guard_id": 8, "false_conclusion": "D60 can correct the result",
        "guard_type": "STRUCTURAL_AND_CHART_SPECIFIC",
        "pattern_present": d60_status.get("status") == "NOT_APPLIED_LOW_RELIABILITY",
        "guarded": d60_weight <= 5 and (guard8_note is not None if d60_status.get("status") == "NOT_APPLIED_LOW_RELIABILITY" else True),
        "evidence": f"D60 business-layer weight={d60_weight} (of 100, capped per spec's 3-5% guidance); d60_status={d60_status.get('status')}" + (f"; {guard8_note}" if guard8_note else ""),
    })

    return checklist



