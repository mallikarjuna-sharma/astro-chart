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


"""business_determination.kp

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""


# v-audit fix (item 5, independent KP-chain verification): this module used
# to trust payload.kp_cusps' occupant/star_lord/sub_lord/sign_lord fields
# entirely as supplied by the upstream chart-generation pipeline, with no
# in-repo check that the sub-lord chain was actually derived correctly (or
# that the underlying cusps were genuine Placidus KP cusps at all, rather
# than an equal-house/whole-sign approximation mislabeled as KP data).
# jyotish/kp_audit.py already implements exactly this verification --
# independently re-deriving star_lord/sub_lord/sub_sub_lord from each cusp's
# stored sign+degree via the classical 249-segment Vimshottari subdivision,
# and flagging non-Placidus/equal-cusp patterns -- and is already used
# elsewhere in the codebase (jyotish/canonical_facts.py,
# Field_Determination/field_methods/__init__.py) to gate a KP-authority
# factor to 0.0 when unverified. Reused here rather than reimplemented, to
# avoid a second, potentially-diverging KP-verification implementation.
try:
    from jyotish.kp_audit import audit_kp_cusps as _audit_kp_cusps
except Exception:  # pragma: no cover -- defensive; see _verify_kp_cusp_chain
    _audit_kp_cusps = None


def _independent_placidus_cross_check(payload: Any, kp_cusps: Dict[str, Any]) -> Dict[str, Any]:
    """v-audit fix (item 7): jyotish/kp_audit.py's audit_kp_cusps() above
    only checks (a) whether payload.house_system LABELS itself "placidus"
    and (b) whether the supplied sign/degree per cusp produces an
    internally-consistent Vimshottari star/sub/sub-sub chain -- it never
    independently recomputes the cusp longitudes themselves, so a KP
    reading could still be "chain_verified" while resting on cusps that
    were never real Placidus geometry at all (e.g. a whole-sign chart
    mislabeled "placidus" with an internally-consistent-but-wrong chain).

    check_placidus_cusps.py (repo root) confirmed jyotish/ephemeris.py's
    get_house_cusps_placidus() is a genuine iterative semi-arc Placidus
    solver (Newton-refined hour-angle equation per cusp 11/12/2/3, closed-
    form MC/Asc for 10/1/4/7 -- not a stub or equal-house approximation),
    so this cross-checks the SUPPLIED payload.kp_cusps sign+degree against
    an INDEPENDENTLY, in-repo recomputed Placidus cusp set for the same
    birth moment/location, rather than trusting the upstream label.

    Requires payload.dob/tob/latitude/longitude (the same birth-moment
    fields d10_rectification.py uses) and a working Skyfield/DE421 backend.
    Degrades to status="SKIPPED" (not a failure -- just "could not
    independently check") when any of those are unavailable; never raises.
    """
    try:
        from jyotish import ephemeris
        try:
            from jyotish.llm_policy import AYANAMSHA
        except Exception:
            AYANAMSHA = "LAHIRI"

        dob = str(getattr(payload, "dob", "") or "")
        tob = str(getattr(payload, "tob", "") or "")
        lat = getattr(payload, "latitude", None)
        lon = getattr(payload, "longitude", None)
        if not dob or not tob or lat is None or lon is None:
            return {"status": "SKIPPED", "reason": "BIRTH_DATETIME_OR_LOCATION_UNAVAILABLE"}
        if not ephemeris.is_available():
            return {"status": "SKIPPED", "reason": "EPHEMERIS_UNAVAILABLE"}

        from datetime import datetime as _dt
        base_dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                base_dt = _dt.strptime(f"{dob} {tob}", fmt)
                break
            except ValueError:
                continue
        if base_dt is None:
            return {"status": "SKIPPED", "reason": "UNPARSEABLE_BIRTH_DATETIME"}

        recomputed = ephemeris.get_house_cusps_placidus(base_dt, float(lat), float(lon), AYANAMSHA)
        if not recomputed or len(recomputed) != 12:
            return {"status": "SKIPPED", "reason": "PLACIDUS_RECOMPUTE_UNAVAILABLE"}

        _SIGN_ORDER = [
            "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
            "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
        ]

        def _sign_deg(lon_deg: float):
            lon_deg = lon_deg % 360.0
            idx = int(lon_deg // 30)
            return _SIGN_ORDER[idx], lon_deg - idx * 30.0

        # Tolerance: 2 degrees of absolute longitude (well inside a single
        # 30-degree sign, tight enough to catch a genuinely wrong house
        # system but loose enough to absorb small ayanamsha/ephemeris-
        # rounding differences between this recompute and whatever produced
        # the upstream payload.kp_cusps).
        _TOLERANCE_DEG = 2.0
        mismatches = []
        checked = 0
        for h in range(1, 13):
            key = f"H{h}"
            cusp = kp_cusps.get(key)
            if not isinstance(cusp, dict):
                continue
            sign = cusp.get("sign")
            degree = cusp.get("degree")
            if sign not in _SIGN_ORDER or degree is None:
                continue
            checked += 1
            supplied_lon = _SIGN_ORDER.index(sign) * 30.0 + float(degree)
            recomputed_lon = recomputed.get(h)
            if recomputed_lon is None:
                continue
            delta = min(abs(supplied_lon - recomputed_lon), 360.0 - abs(supplied_lon - recomputed_lon))
            if delta > _TOLERANCE_DEG:
                recomputed_sign, recomputed_deg = _sign_deg(recomputed_lon)
                mismatches.append({
                    "cusp": key, "supplied_sign": sign, "supplied_degree": round(float(degree), 3),
                    "recomputed_sign": recomputed_sign, "recomputed_degree": round(recomputed_deg, 3),
                    "delta_deg": round(delta, 3),
                })

        status = "MATCH" if checked and not mismatches else ("MISMATCH" if mismatches else "SKIPPED")
        reason = "NO_COMPARABLE_CUSPS" if not checked else None
        out = {
            "status": status, "checked_cusp_count": checked,
            "tolerance_deg": _TOLERANCE_DEG, "mismatches": mismatches,
        }
        if reason:
            out["reason"] = reason
        return out
    except Exception as exc:  # pragma: no cover -- defensive
        return {"status": "SKIPPED", "reason": f"EXCEPTION:{type(exc).__name__}"}


_KP_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
_KP_SIGN_LORD = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}


def _recompute_genuine_placidus_kp_cusps(payload: Any) -> Dict[str, Any]:
    """v-audit fix (item 4/genuine Placidus KP cusps): when the upstream
    payload.kp_cusps cannot be verified as real Placidus data (see
    _verify_kp_cusp_chain -> jyotish.kp_audit.audit_kp_cusps, which flags
    HOUSE_SYSTEM_NOT_EXPLICITLY_PLACIDUS / EQUAL_OR_WHOLE_SIGN_CUSP_PATTERN
    whenever the supplied cusps look like an equal-house/whole-sign chart
    mislabeled as KP), this function independently RECOMPUTES a genuine
    Placidus cusp set in-house instead of merely flagging the upstream data
    as untrustworthy.

    Building blocks, both already validated elsewhere in this repo (reused,
    not reimplemented):
      - jyotish.ephemeris.get_house_cusps_placidus() -- the same
        Newton-iteration semi-arc Placidus solver check_placidus_cusps.py
        (repo root) confirmed produces a monotonic, astronomically sane
        12-cusp sequence (verified by rerunning it against the reference
        Chennai/13N moment in that script: no backward jumps, cusps match
        whole-sign expectation at this near-equatorial latitude where
        Placidus distortion is expected to be mild).
      - jyotish.kp_audit.kp_chain(longitude) -- the same from-scratch
        249-segment Vimshottari star/sub/sub-sub-lord subdivision
        audit_kp_cusps() already uses to VERIFY a chain; called directly
        here to DERIVE one from a genuine, independently-recomputed cusp
        longitude instead of merely checking someone else's.

    Sign lord is a direct sign->lord lookup (not ephemeris-derived).
    Occupant (which planet, if any, sits within this house's own cusp
    span) is derived from payload.planets_d1, using the recomputed cusp
    longitudes as house boundaries (cusp[h] .. cusp[h+1], wrapping at 360)
    -- the correct definition of "occupant" under Placidus (unequal house
    spans), not a whole-sign approximation.

    Returns {"status": "OK", "kp_cusps": {...}} on success (a kp_cusps-
    shaped dict, same shape as payload.kp_cusps, drop-in compatible with
    _kp_10th_cusp_job_vs_business/_kp_business_cusp_score), or
    {"status": <reason>} when dob/tob/lat/lon or the ephemeris backend are
    unavailable. Never raises.
    """
    try:
        from jyotish import ephemeris
        try:
            from jyotish.kp_audit import kp_chain as _kp_chain_fn
        except Exception:
            return {"status": "KP_AUDIT_MODULE_UNAVAILABLE"}
        try:
            from jyotish.llm_policy import AYANAMSHA
        except Exception:
            AYANAMSHA = "LAHIRI"

        dob = str(getattr(payload, "dob", "") or "")
        tob = str(getattr(payload, "tob", "") or "")
        lat = getattr(payload, "latitude", None)
        lon = getattr(payload, "longitude", None)
        if not dob or not tob or lat is None or lon is None:
            return {"status": "BIRTH_DATETIME_OR_LOCATION_UNAVAILABLE"}
        if not ephemeris.is_available():
            return {"status": "EPHEMERIS_UNAVAILABLE"}

        from datetime import datetime as _dt
        base_dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                base_dt = _dt.strptime(f"{dob} {tob}", fmt)
                break
            except ValueError:
                continue
        if base_dt is None:
            return {"status": "UNPARSEABLE_BIRTH_DATETIME"}

        cusp_lons = ephemeris.get_house_cusps_placidus(base_dt, float(lat), float(lon), AYANAMSHA)
        if not cusp_lons or len(cusp_lons) != 12:
            return {"status": "PLACIDUS_RECOMPUTE_UNAVAILABLE"}

        def _sign_deg(lon_deg: float):
            lon_deg = float(lon_deg) % 360.0
            idx = int(lon_deg // 30)
            return _KP_SIGN_ORDER[idx], lon_deg - idx * 30.0

        planets_d1 = getattr(payload, "planets_d1", {}) or {}
        planet_abs_lon: Dict[str, float] = {}
        for planet, pdata in planets_d1.items():
            sign = pdata.get("sign") if isinstance(pdata, dict) else None
            degree = pdata.get("degree") if isinstance(pdata, dict) else None
            if sign in _KP_SIGN_ORDER and degree is not None:
                planet_abs_lon[planet] = _KP_SIGN_ORDER.index(sign) * 30.0 + float(degree)

        def _in_span(x: float, start: float, end: float) -> bool:
            x, start, end = x % 360.0, start % 360.0, end % 360.0
            if start <= end:
                return start <= x < end
            return x >= start or x < end  # span wraps past 360/0

        kp_cusps: Dict[str, Any] = {}
        for h in range(1, 13):
            cusp_lon = cusp_lons.get(h)
            if cusp_lon is None:
                continue
            next_lon = cusp_lons.get(h + 1 if h < 12 else 1)
            sign, degree = _sign_deg(cusp_lon)
            chain = _kp_chain_fn(cusp_lon)
            occupant = None
            if next_lon is not None:
                for planet, plon in planet_abs_lon.items():
                    if _in_span(plon, cusp_lon, next_lon):
                        occupant = planet
                        break
            kp_cusps[f"H{h}"] = {
                "sign": sign,
                "degree": round(degree, 4),
                "occupant": occupant,
                "star_lord": chain["star_lord"],
                "sub_lord": chain["sub_lord"],
                "sub_sub_lord": chain["sub_sub_lord"],
                "sign_lord": _KP_SIGN_LORD.get(sign, ""),
            }
        return {
            "status": "OK",
            "house_system": "placidus",
            "ayanamsha": AYANAMSHA,
            "kp_cusps": kp_cusps,
            "note": (
                "Genuinely recomputed, in-house Placidus KP cusp set (Newton-iteration "
                "semi-arc solver + from-scratch 249-segment Vimshottari star/sub/sub-sub "
                "derivation) -- independent of, and used in place of, the upstream "
                "payload.kp_cusps because that upstream data failed cusp-authenticity "
                "verification (see _verify_kp_cusp_chain)."
            ),
        }
    except Exception as exc:  # pragma: no cover -- defensive
        return {"status": f"EXCEPTION:{type(exc).__name__}:{exc}"}


def _verify_kp_cusp_chain(payload: Any) -> Dict[str, Any]:
    """Independently verify payload.kp_cusps' star/sub/sub-sub-lord chains
    against jyotish/kp_audit.py's from-scratch Vimshottari-segment
    derivation, instead of trusting the upstream chain fields as-is. Returns
    the raw audit_kp_cusps() report plus a simple `chain_verified` bool for
    callers that just need a pass/fail gate. Never raises -- an import
    failure or malformed payload degrades to an explicit UNVERIFIABLE
    status rather than crashing KP scoring.

    v-audit fix (item 7): additionally attaches `placidus_cross_check` --
    an independent recompute of real Placidus cusp longitudes (see
    _independent_placidus_cross_check above) compared against the supplied
    payload.kp_cusps sign/degree, rather than only trusting kp_audit.py's
    label+internal-consistency check. `chain_verified` is tightened to also
    require the cross-check did not find a MISMATCH (a SKIPPED cross-check,
    e.g. because birth lat/lon/ephemeris weren't available, does not itself
    fail verification -- it just means this extra check could not run)."""
    kp_cusps = getattr(payload, "kp_cusps", None) or {}
    if _audit_kp_cusps is None:
        return {
            "contract_version": "kp-cusp-audit.v1", "status": "UNVERIFIABLE",
            "verified_cusp_count": 0, "reasons": ["KP_AUDIT_MODULE_UNAVAILABLE"],
            "mismatches": [], "kp_authority_factor": 0.0, "chain_verified": False,
            "placidus_cross_check": {"status": "SKIPPED", "reason": "KP_AUDIT_MODULE_UNAVAILABLE"},
        }
    if not kp_cusps:
        return {
            "contract_version": "kp-cusp-audit.v1", "status": "UNVERIFIABLE",
            "verified_cusp_count": 0, "reasons": ["KP_CUSPS_NOT_SUPPLIED"],
            "mismatches": [], "kp_authority_factor": 0.0, "chain_verified": False,
            "placidus_cross_check": {"status": "SKIPPED", "reason": "KP_CUSPS_NOT_SUPPLIED"},
        }
    try:
        house_system = getattr(payload, "house_system", "") or ""
        report = dict(_audit_kp_cusps(kp_cusps, house_system))
    except Exception as exc:  # pragma: no cover -- defensive
        return {
            "contract_version": "kp-cusp-audit.v1", "status": "UNVERIFIABLE",
            "verified_cusp_count": 0, "reasons": [f"AUDIT_EXCEPTION:{type(exc).__name__}"],
            "mismatches": [], "kp_authority_factor": 0.0, "chain_verified": False,
            "placidus_cross_check": {"status": "SKIPPED", "reason": f"AUDIT_EXCEPTION:{type(exc).__name__}"},
        }
    cross_check = _independent_placidus_cross_check(payload, kp_cusps)
    report["placidus_cross_check"] = cross_check
    report["chain_verified"] = (
        report.get("status") == "VERIFIED" and cross_check.get("status") != "MISMATCH"
    )
    return report


def _kp_significator_weighted_houses(planet: str, payload: Any) -> Dict[int, float]:
    """Level-weighted (1.00/0.55/0.30/0.15) house-signification set for a
    planet, shared helper for any KP house-vs-house-set comparison. Factored
    out of _kp_sublord_signification_bias's internals so the 10th-cusp
    job-vs-business comparison below (v17) can reuse the same weighting
    discipline without duplicating/diverging from it."""
    kp_sigs = getattr(payload, "kp_significators", {}) or {}
    entry = kp_sigs.get(planet, {}) or {}
    if not isinstance(entry, dict):
        return {}
    weighted: Dict[int, float] = {}
    for level_key, level_weight in _KP_LEVEL_WEIGHTS.items():
        for h in entry.get(level_key, []) or []:
            try:
                house_num = int(h)
            except (TypeError, ValueError):
                continue
            weighted[house_num] = weighted.get(house_num, 0.0) + level_weight
    return weighted

_KP_JOB_HOUSES = frozenset({2, 6, 10, 11})

_KP_BUSINESS_HOUSES = frozenset({2, 7, 10, 11})

_KP_ENTREPRENEUR_HOUSES = frozenset({1, 3})

# ISSUE-1 audit fix: the business/job 0-100 "kp" scoring layer (scoring.py)
# used to convert job_weight/business_weight straight into a ratio
# business_weight / max(0.001, job_weight + business_weight) * 100 -- a
# degenerate-denominator pattern. When job_weight is legitimately 0 (no job
# houses signified at all) and business_weight is a tiny, weak number
# (e.g. 0.225, coming entirely from the half-weight 1st/3rd
# "entrepreneur boost", with NO genuine business core house {2,7,10,11}
# actually significated), the ratio still divides out to exactly 1.0 and
# saturates the score to 100 -- reading "no real evidence either way" as
# "maximum confidence business". This directly conflates DIRECTION (which
# side the weak signal leans) with STRENGTH (how much genuine evidence
# backs that lean). _kp_directional_confidence_score() below separates
# the two: `ratio` still captures direction, but a `magnitude` factor
# (scaled by the *absolute* total weight, saturating only once there is
# substantial underlying signal) and a genuine-core-house-count gate (at
# least 2 of the classical business houses {2,7,10,11} / job houses
# {2,6,10,11} actually significated) together prevent a near-zero-weight
# reading from ever reaching full-confidence saturation.
_KP_SCORE_SATURATION_WEIGHT = 1.5
_KP_MIN_CORE_HOUSES_FOR_FULL_CONFIDENCE = 2
_KP_WEAK_EVIDENCE_CONFIDENCE_CAP = 0.5


def _kp_directional_confidence_score(lean_weight: float, other_weight: float, core_house_count: int) -> float:
    """0..100 score expressing how strongly the evidence leans toward
    `lean_weight`'s side vs `other_weight`'s side, deliberately NOT prone
    to saturating to 0/100 off a near-zero total (see module note above).

    - `ratio` (0..1) is pure DIRECTION: which side the weight leans.
    - `magnitude` (0..1) is STRENGTH: how much total weight actually backs
      that direction, scaled against _KP_SCORE_SATURATION_WEIGHT rather
      than assumed to be "full" just because one side is exactly 0.
    - Evidence resting on fewer than _KP_MIN_CORE_HOUSES_FOR_FULL_CONFIDENCE
      genuine core houses (2/7/10/11 business, 2/6/10/11 job -- NOT the
      half-weight entrepreneur-boost houses 1/3) is additionally capped at
      _KP_WEAK_EVIDENCE_CONFIDENCE_CAP magnitude, so a lean built entirely
      off boost houses can never reach saturation regardless of the raw
      ratio.
    """
    total = lean_weight + other_weight
    if total <= 0:
        return 50.0
    ratio = lean_weight / total
    magnitude = min(1.0, total / _KP_SCORE_SATURATION_WEIGHT)
    if core_house_count < _KP_MIN_CORE_HOUSES_FOR_FULL_CONFIDENCE:
        magnitude = min(magnitude, _KP_WEAK_EVIDENCE_CONFIDENCE_CAP)
    score = 50.0 + (ratio - 0.5) * 100.0 * magnitude
    return round(max(0.0, min(100.0, score)), 2)


def _kp_10th_cusp_job_vs_business(payload: Any) -> Dict[str, Any]:
    """v17 audit fix: the spec's KP section compares the 10th cusp
    SUB-LORD's own house-signification set against a job set {2,6,10,11}
    vs a business set {2,7,10,11} (extended to {1,3,2,7,10,11} for a
    stronger entrepreneurship read) -- this module previously had NO
    10th-cusp-specific check at all; the only existing KP logic biases the
    7th cusp sub-lord toward a generic result/loss split. This is a
    genuinely different question (which career MODE does the 10th cusp's
    own activation favor, not just whether it looks favorable/unfavorable)
    and needs its own comparison."""
    kp_cusps = getattr(payload, "kp_cusps", {}) or {}

    # v-audit fix (item 4): if the upstream kp_cusps cannot be verified as
    # genuine Placidus data, recompute a genuine, independently-derived
    # Placidus KP cusp set in-house (see _recompute_genuine_placidus_kp_
    # cusps) and use THAT for the rest of this function, instead of either
    # (a) trusting unverified upstream data at full confidence, or (b) only
    # ever labeling the reading "NOT VALIDLY APPLIED" without attempting a
    # real fix. Falls back to the (unverified) upstream cusps unchanged
    # when the recompute itself is not possible (no ephemeris/dob/tob/
    # lat/lon available) -- same behavior as before in that case.
    genuine_recompute_used = False
    preliminary_audit = _verify_kp_cusp_chain(payload)
    if not preliminary_audit.get("chain_verified"):
        recompute = _recompute_genuine_placidus_kp_cusps(payload)
        if recompute.get("status") == "OK" and recompute.get("kp_cusps"):
            kp_cusps = recompute["kp_cusps"]
            genuine_recompute_used = True

    h10_cusp = kp_cusps.get("H10", kp_cusps.get("10", kp_cusps.get(10, {}))) or {}
    sub_lord = h10_cusp.get("sub_lord", "") if isinstance(h10_cusp, dict) else ""
    # v34 audit fix: an astrologer auditing this output previously had no
    # way to independently verify the sub_lord derivation without the raw
    # ephemeris -- only the final sub_lord and its resulting weighted
    # significations were shown, not the intermediate occupant/star-lord/
    # sign-lord chain the payload already carries per cusp. This exposes
    # that chain (whatever subset of it the payload actually has) so the
    # full occupant -> star_lord -> sub_lord -> sign_lord (ownership) path
    # is inspectable, not just the end result.
    kp_chain = {
        "occupant": h10_cusp.get("occupant") if isinstance(h10_cusp, dict) else None,
        "star_lord": h10_cusp.get("star_lord") if isinstance(h10_cusp, dict) else None,
        "sub_lord": sub_lord or None,
        "sign_lord": h10_cusp.get("sign_lord") if isinstance(h10_cusp, dict) else None,
    }
    if not sub_lord:
        return {"status": "NO_DATA", "leaning": "UNKNOWN", "job_weight": 0.0, "business_weight": 0.0, "business_confidence_score": 50.0, "job_confidence_score": 50.0, "business_core_houses": [], "job_core_houses": [], "kp_chain": kp_chain, "note": "No 10th-cusp sub-lord data on payload"}

    weighted = _kp_significator_weighted_houses(sub_lord, payload)
    if not weighted:
        return {"status": "NO_DATA", "leaning": "UNKNOWN", "job_weight": 0.0, "business_weight": 0.0, "business_confidence_score": 50.0, "job_confidence_score": 50.0, "business_core_houses": [], "job_core_houses": [], "kp_chain": kp_chain, "note": f"10th-cusp sub-lord ({sub_lord}) has no recorded KP significations"}

    job_weight = sum(weighted.get(h, 0.0) for h in _KP_JOB_HOUSES)
    business_weight = sum(weighted.get(h, 0.0) for h in _KP_BUSINESS_HOUSES)
    entrepreneur_weight = sum(weighted.get(h, 0.0) for h in _KP_ENTREPRENEUR_HOUSES)
    # 1/3 add self-direction credit to the business side only, at half
    # weight (they are not themselves in the base business set, they
    # STRENGTHEN a business read per the spec's "especially strong business
    # sequence: 1/3, 2, 7, 10, 11").
    business_weight_boosted = business_weight + 0.5 * entrepreneur_weight

    # ISSUE-1 audit fix: genuine core-house counts (2/7/10/11 for business,
    # 2/6/10/11 for job) computed from the RAW significated-house set, not
    # the entrepreneur-boosted business_weight_boosted number -- a chart
    # whose only significations are 1/3 (entrepreneur-boost houses) has
    # ZERO genuine business core houses even though business_weight_boosted
    # is nonzero, and must not be treated as strong business evidence (see
    # _kp_directional_confidence_score above).
    business_core_houses = sorted(h for h in weighted if h in _KP_BUSINESS_HOUSES and weighted.get(h, 0.0) > 0)
    job_core_houses = sorted(h for h in weighted if h in _KP_JOB_HOUSES and weighted.get(h, 0.0) > 0)
    business_confidence_score = _kp_directional_confidence_score(
        business_weight_boosted, job_weight, len(business_core_houses)
    )
    job_confidence_score = _kp_directional_confidence_score(
        job_weight, business_weight_boosted, len(job_core_houses)
    )

    if job_weight <= 0 and business_weight_boosted <= 0:
        leaning = "NEUTRAL"
    elif business_weight_boosted >= job_weight * _KP_BIAS_MARGIN:
        leaning = "BUSINESS"
    elif job_weight >= business_weight_boosted * _KP_BIAS_MARGIN:
        leaning = "JOB"
    else:
        leaning = "NEUTRAL"

    sig_houses = sorted(weighted)

    # v34 audit fix: expose a per-house significator GRADE (not just the
    # raw weight number) so a reader doesn't need to know this module's
    # internal weighting scale to tell a strong signification from a weak
    # one -- part of the same "full KP chain" transparency fix as kp_chain.
    def _grade(w: float) -> str:
        if w >= 0.75:
            return "STRONG"
        if w >= 0.4:
            return "MODERATE"
        return "WEAK"
    significator_grades = {f"H{h}": {"weight": round(weighted[h], 3), "grade": _grade(weighted[h])} for h in sig_houses}

    # v23 audit fix: spec section 6 lists "business-specific KP modifiers"
    # for H4/H5/H6/H8/H9/H12 -- descriptive FIELD interpretations of what
    # KIND of business the 10th-cusp sub-lord's significations point
    # toward, distinct from the job-vs-business DIRECTIONAL leaning above.
    # These were previously entirely absent from this function. Scope
    # note: this reads the already-computed sig_houses (level-weighted
    # occupant/star/sign-lord significations already resolved by
    # _kp_significator_weighted_houses via payload.kp_significators) and
    # attaches the spec's own interpretive labels when a modifier house is
    # significated at non-trivial weight -- it does NOT locally reconstruct
    # the raw occupant->star-lord->sub-lord derivation chain from
    # ephemeris longitudes (that remains out of scope, since this engine
    # trusts the upstream payload.kp_significators the same way every
    # other KP check in this module already does).
    _KP_FIELD_MODIFIERS = {
        4: "property, vehicles, education, or fixed-asset business",
        5: "speculation, creativity, or investment-oriented business",
        6: "staff/operations, competition, loans, or service-delivery-heavy business",
        8: "insurance, tax, research, or investor-funded business",
        9: "consulting, law, education, or international-expansion business",
        12: "foreign trade, hospitals, hospitality, or overseas-work business",
    }
    field_modifiers = [
        {"house": f"H{h}", "weight": round(weighted[h], 3), "interpretation": label}
        for h, label in _KP_FIELD_MODIFIERS.items()
        if weighted.get(h, 0.0) > 0
    ]

    # v41 audit fix (#15, user-caught): this exposed only ONE job-vs-
    # business weight for the whole 10th cusp, but a KP reading is really
    # answering several distinct event-level questions (does this cusp
    # support REGISTERING a new venture vs BORROWING capital vs FORMING a
    # partnership vs staying employed) -- these can point different
    # directions even at the same sub-lord. Bucketing the SAME already-
    # computed per-house significator weights (no new KP derivation) by
    # event-relevant house groups gives a per-event-type read instead of
    # one collapsed job-vs-business number.
    _KP_EVENT_TYPE_HOUSES = {
        "registering_or_launching_business": (1, 3),
        "partnership_formation": (7,),
        "capital_deployment_or_borrowing": (2, 8),
        "expansion_or_scaling": (11,),
        "remaining_employed": (6,),
        "foreign_or_exit_linked": (9, 12),
    }
    event_type_signals = {
        event: round(sum(weighted.get(h, 0.0) for h in houses), 3)
        for event, houses in _KP_EVENT_TYPE_HOUSES.items()
        if sum(weighted.get(h, 0.0) for h in houses) > 0
    }

    # v-audit fix (item 5): independently verify the cusp chain this whole
    # function has been trusting (see _verify_kp_cusp_chain above) rather
    # than silently assuming it's correct because sub_lord/significations
    # were present. `status` is left as "OK" (unchanged meaning: a KP
    # reading was computed at all -- existing callers like mode_gate.py/
    # contradictions.py that only gate on "was there a reading" keep working
    # unmodified). The NEW `chain_verified` bool + `cusp_audit` diagnostic
    # are additive fields: scoring.py's kp/kp_2_6_10_11 layers (the ones
    # that actually convert this into a numeric confidence-bearing score)
    # now consult chain_verified specifically to discount an unverified
    # chain toward neutral, without changing what "status" itself means.
    if genuine_recompute_used:
        # The cusps now in use were derived by THIS function's own
        # in-house Placidus solver + from-scratch Vimshottari subdivision
        # (see _recompute_genuine_placidus_kp_cusps) -- by construction
        # they satisfy audit_kp_cusps()'s own VERIFIED criteria (explicit
        # Placidus house system, internally-consistent chain, 12 distinct
        # cusp degrees), so re-running the same audit against them (rather
        # than fabricating a "VERIFIED" label) confirms that honestly.
        cusp_audit = dict(_audit_kp_cusps(kp_cusps, "placidus")) if _audit_kp_cusps else {
            "contract_version": "kp-cusp-audit.v1", "status": "UNVERIFIABLE",
            "verified_cusp_count": 0, "reasons": ["KP_AUDIT_MODULE_UNAVAILABLE"],
            "mismatches": [], "kp_authority_factor": 0.0,
        }
        cusp_audit["chain_verified"] = cusp_audit.get("status") == "VERIFIED"
        cusp_audit["genuine_placidus_recompute"] = True
        cusp_audit["recompute_note"] = (
            "Upstream payload.kp_cusps failed authenticity verification, so this reading "
            "was recomputed in-house from a genuine Placidus solver + independent "
            "Vimshottari sub-lord derivation (see business_determination/kp.py::"
            "_recompute_genuine_placidus_kp_cusps) rather than left unverified."
        )
    else:
        cusp_audit = preliminary_audit

    return {
        "status": "OK",
        "chain_verified": cusp_audit.get("chain_verified", False),
        "sub_lord": sub_lord,
        "kp_chain": kp_chain,
        "cusp_audit": cusp_audit,
        "leaning": leaning,
        "job_weight": round(job_weight, 3),
        "business_weight": round(business_weight_boosted, 3),
        # ISSUE-1 audit fix: business_weight/job_weight above kept
        # unchanged for backward compatibility, but a caller that
        # converts this into a 0-100 confidence score should use these two
        # new fields instead of re-deriving business_weight/(job_weight +
        # business_weight)*100 itself -- that raw ratio is exactly the
        # degenerate-denominator pattern this audit fix removes (see
        # _kp_directional_confidence_score's docstring above).
        "business_confidence_score": business_confidence_score,
        "job_confidence_score": job_confidence_score,
        "business_core_houses": [f"H{h}" for h in business_core_houses],
        "job_core_houses": [f"H{h}" for h in job_core_houses],
        "significated_houses": sig_houses,
        "significator_grades": significator_grades,
        "field_modifiers": field_modifiers,
        "event_type_signals": event_type_signals,
        "genuine_placidus_recompute": genuine_recompute_used,
        "note": (
            f"10th cusp sub-lord ({sub_lord}) significates houses {sig_houses} "
            f"-> job-weight={round(job_weight, 2)} vs business-weight={round(business_weight_boosted, 2)} "
            f"(entrepreneur-boosted) -> {leaning}"
            + (f"; field modifiers: {', '.join(m['house'] for m in field_modifiers)}" if field_modifiers else "")
            + (
                (
                    "; NOTE: upstream KP cusps were unverified, so this reading uses a "
                    "genuinely recomputed in-house Placidus cusp set (real Newton-iteration "
                    "solver + independent Vimshottari sub-lord chain), not the upstream data"
                ) if genuine_recompute_used else ""
            )
            + (
                "" if cusp_audit.get("chain_verified")
                else f"; CAUTION: KP cusp chain NOT independently verified ({', '.join(cusp_audit.get('reasons', []) or ['UNKNOWN'])}) -- this reading is discounted toward neutral in scoring, not used at full confidence"
            )
        ),
    }

_BUSINESS_CUSP_WEIGHTS = {"H7": 1.00, "H11": 0.85, "H2": 0.70, "H10": 0.45}

def _kp_business_cusp_score(md_lord: str, ad_lord: str, kp_cusps: Dict[str, Any]) -> float:
    """0..1 KP score: does this dasha lord rule the sub-lord/star-lord/
    sign-lord of the business-relevant house cusps (H7/H11/H2/H10)?"""
    max_possible = sum(_BUSINESS_CUSP_WEIGHTS.values())
    raw = 0.0
    for cusp_key, weight in _BUSINESS_CUSP_WEIGHTS.items():
        cusp = kp_cusps.get(cusp_key, {})
        if not isinstance(cusp, dict):
            continue
        sub, star, sign = cusp.get("sub_lord", ""), cusp.get("star_lord", ""), cusp.get("sign_lord", "")
        if sub in (md_lord, ad_lord):
            raw += weight * 1.00
        elif star in (md_lord, ad_lord):
            raw += weight * 0.55
        elif sign in (md_lord, ad_lord):
            raw += weight * 0.25
    return min(1.0, raw / max_possible) if max_possible else 0.0

_KP_POSITIVE_HOUSES = frozenset({2, 7, 10, 11})

_KP_NEGATIVE_HOUSES = frozenset({6, 8, 12})

_KP_SOFT_NEGATIVE_HOUSES = frozenset({6})

_KP_LEVEL_WEIGHTS = {"level_1": 1.00, "level_2": 0.55, "level_3": 0.30, "level_4": 0.15}

_KP_BIAS_MARGIN = 1.15

def _kp_sublord_signification_bias(planet: str, payload: Any) -> Tuple[str, List[int], List[int]]:
    """Whether a planet's own KP house-signification set (from
    payload.kp_significators[planet], levels 1-4) leans toward
    result-producing houses (2/7/10/11) or dispute/loss houses (6/8/12) --
    weighted by level priority, not a flat count across levels.

    Being the H7 cusp sub-lord only means this planet ACTIVATES H7 events
    during its period -- KP doctrine does not say that activation is
    automatically favorable. A sub-lord that itself strongly signifies
    H6/H8/H12 (its own placement, conjunctions, aspects, or ownership tie
    it to dispute/debt/loss houses) activates H7 events in a
    dispute/rupture/loss direction, not a success direction. This function
    lets the Tier-2 KP override in _business_ad_windows() distinguish the
    two cases instead of treating every H7 sub-lord match as favorable.

    Level weighting matters: one level_1 negative house is a much stronger
    signal than three level_4 positive houses -- a flat set-count comparison
    (the earlier version of this function) would have let low-priority
    positive houses outvote a single high-priority negative one. Weighted
    sums fix that; ties within _KP_BIAS_MARGIN of each other resolve to
    NEUTRAL rather than an arbitrary direction.
    """
    kp_sigs = getattr(payload, "kp_significators", {}) or {}
    entry = kp_sigs.get(planet, {}) or {}
    if not isinstance(entry, dict):
        return "UNKNOWN", [], []

    positive_houses: set = set()
    negative_houses: set = set()
    positive_weight = 0.0
    negative_weight = 0.0

    # First pass: collect all negative houses across all levels so soft-vs-
    # full weighting for H6 can check for 8/12 co-presence anywhere in the
    # set, not just within the same level.
    all_negative_houses: set = set()
    for level_key in _KP_LEVEL_WEIGHTS:
        for h in entry.get(level_key, []) or []:
            try:
                house_num = int(h)
            except (TypeError, ValueError):
                continue
            if house_num in _KP_NEGATIVE_HOUSES:
                all_negative_houses.add(house_num)
    hard_dusthana_present = bool(all_negative_houses & {8, 12})

    for level_key, level_weight in _KP_LEVEL_WEIGHTS.items():
        for h in entry.get(level_key, []) or []:
            try:
                house_num = int(h)
            except (TypeError, ValueError):
                continue
            if house_num in _KP_POSITIVE_HOUSES:
                positive_houses.add(house_num)
                positive_weight += level_weight
            elif house_num in _KP_NEGATIVE_HOUSES:
                negative_houses.add(house_num)
                effective_weight = level_weight
                if house_num in _KP_SOFT_NEGATIVE_HOUSES and not hard_dusthana_present:
                    effective_weight *= 0.5
                negative_weight += effective_weight

    if not positive_houses and not negative_houses:
        return "UNKNOWN", [], []

    positive = sorted(positive_houses)
    negative = sorted(negative_houses)

    if positive_weight <= 0 and negative_weight <= 0:
        return "NEUTRAL", positive, negative
    if negative_weight <= 0 or positive_weight >= negative_weight * _KP_BIAS_MARGIN:
        return "POSITIVE", positive, negative
    if positive_weight <= 0 or negative_weight >= positive_weight * _KP_BIAS_MARGIN:
        return "NEGATIVE", positive, negative
    return "NEUTRAL", positive, negative

