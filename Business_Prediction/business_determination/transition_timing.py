"""Business_Prediction/business_determination/transition_timing.py
===================================================================
Cross-wires the two subsystems that have, until now, sat side-by-side in
compute_business_prediction()'s result dict WITHOUT ever answering the single
most commercially useful client question this engine could address:

    "Should I transition from job to business NOW, or wait for a specific
    upcoming favorable window?"

  - mode_gate.py::compute_business_mode_gate() answers a STATIC, snapshot
    question: which mode (employment/business/independent/family) does this
    chart structurally support, and by how much (recommended_mode, plus the
    business_score vs employment_score gap that mode_gate's own confidence
    tier -- HIGH >=20 / MODERATE >=10 / LOW below that -- is built on; see
    compute_business_mode_gate()'s "gap = sorted_scores[0] - sorted_scores[1];
    confidence = HIGH if gap>=20 else MODERATE if gap>=10 else LOW").
  - timing.py::_compute_windows_and_status() / _business_ad_windows() answer
    a TIME-BOUND question: which forecast-horizon dasha/bhukti windows
    (now PD-refined) are astrologically favorable, using the SAME five-tier
    labelling scale (_WINDOW_LABELS: STRONG_FAVORABLE >=25, FAVORABLE >=10,
    MIXED >=-10, CAUTION >=-25, else HIGH_RISK).

Neither one alone answers the transition-timing question: mode_gate can say
"business is favored" with no view of WHEN; timing can say "this window is
favorable" with no view of whether business is even the structurally
favored mode over employment for this chart. This module is a thin,
NO-NEW-SCORING composition layer over both -- it reuses mode_gate's own
confidence-gap thresholds (20/10) verbatim (see _MARGIN_HIGH/_MARGIN_MODERATE
below) and timing.py's own favorable-label set (STRONG_FAVORABLE/FAVORABLE)
verbatim; it introduces no new cutoff numbers of its own.

MATURITY: same status as every other module in this package -- see
MODEL_STATUS / CALIBRATION_STATUS / MATURITY_STATEMENT in constants.py. This
composition is exactly as uncalibrated/heuristic as the two systems it
reads from; it does not add and cannot subtract from their evidentiary
weight. Never treat any verdict below as more than a decision-support
narrative echoing already-computed, already-disclaimed scores.

Public API
----------
    compute_transition_timing_recommendation(
        mode_gate_result, timed_windows, timing_status=None, as_of_date=None,
    ) -> Dict[str, Any]
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .constants import MODEL_STATUS, CALIBRATION_STATUS
from .policy import DECISION_POLICY

__all__ = ["compute_transition_timing_recommendation"]

# Reused verbatim from mode_gate.py::compute_business_mode_gate -- the exact
# same gap thresholds it uses to label its own recommended_mode confidence
# ("confidence = HIGH if gap >= 20 else MODERATE if gap >= 10 else LOW").
# NOT a new cutoff invented for this module.
_MARGIN_HIGH = DECISION_POLICY.high_margin
_MARGIN_MODERATE = 10

# Reused verbatim from timing.py::_WINDOW_LABELS -- the two tiers timing.py
# itself treats as favorable (STRONG_FAVORABLE >= 25, FAVORABLE >= 10).
_FAVORABLE_LABELS = frozenset({"STRONG_FAVORABLE", "FAVORABLE"})

_UNFAVORABLE_TIMING_STATUSES = frozenset({
    "NO_DOB", "NO_DASHA_SEQUENCE", "CALENDAR_COMPUTATION_FAILED", "CALENDAR_EMPTY",
})

_VERDICT_ACT_NOW = "ACT_NOW"
_VERDICT_WAIT_FOR_WINDOW = "WAIT_FOR_WINDOW"
_VERDICT_RECONSIDER_MODE = "RECONSIDER_MODE"
_VERDICT_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _window_covering(windows: Sequence[Mapping[str, Any]], as_of: date) -> Optional[Dict[str, Any]]:
    for w in windows:
        start = _parse_date(w.get("start_date"))
        end = _parse_date(w.get("end_date"))
        if start and end and start <= as_of <= end:
            return dict(w)
    return None


def _next_favorable_window(windows: Sequence[Mapping[str, Any]], as_of: date) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for w in windows:
        if w.get("label") not in _FAVORABLE_LABELS:
            continue
        start = _parse_date(w.get("start_date"))
        if start and start > as_of:
            candidates.append(dict(w))
    if not candidates:
        return None
    candidates.sort(key=lambda w: _parse_date(w.get("start_date")) or date.max)
    return candidates[0]


def _base_result(
    verdict: str,
    as_of: date,
    *,
    reason: Optional[str] = None,
    mode_gate_basis: Optional[Dict[str, Any]] = None,
    current_window: Optional[Dict[str, Any]] = None,
    next_favorable_window: Optional[Dict[str, Any]] = None,
    client_message: str = "",
    astrologer_detail: str = "",
) -> Dict[str, Any]:
    return {
        "verdict": verdict,
        "as_of_date": str(as_of),
        "reason": reason,
        "mode_gate_basis": mode_gate_basis,
        "current_window": current_window,
        "next_favorable_window": next_favorable_window,
        "client_message": client_message,
        "astrologer_detail": astrologer_detail,
        "margin_thresholds_reused_from": (
            "business_determination.mode_gate.compute_business_mode_gate's own "
            "recommended_mode confidence-gap thresholds (gap>=20 -> HIGH, "
            "gap>=10 -> MODERATE, else LOW) -- not a new cutoff invented here."
        ),
        "timing_labels_reused_from": (
            "business_determination.timing._WINDOW_LABELS's STRONG_FAVORABLE/"
            "FAVORABLE tiers (net>=25 / net>=10) -- not a new cutoff invented here."
        ),
        "model_status": MODEL_STATUS,
        "calibration_status": CALIBRATION_STATUS,
        "disclaimer": (
            "This is a composed reading of two already-provisional, uncalibrated "
            "heuristic subsystems (mode_gate's static viability scores and "
            "timing's dasha/bhukti/Pratyantardasha window labels), not a new "
            "independent forecast. It carries the SAME ENGINEERED_PROVISIONAL "
            "status as every other output of this engine -- see calibration_status "
            "/ model_status above -- and is decision-support narrative, not "
            "financial, legal, or career advice. Confirm with a qualified "
            "astrologer before acting on any transition-timing suggestion."
        ),
    }


_AUTHORITATIVE_JOB_LEANING_VERDICTS = frozenset({"HYBRID_LEANING_JOB", "STAY_EMPLOYED", "HYBRID"})


def compute_transition_timing_recommendation(
    mode_gate_result: Optional[Mapping[str, Any]],
    timed_windows: Optional[Sequence[Mapping[str, Any]]],
    timing_status: Optional[Mapping[str, Any]] = None,
    as_of_date: Optional[date] = None,
    authoritative_recommendation: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Cross-wires mode_gate's static recommended_mode/margin against
    timing's current-window/upcoming-window calendar to answer: "act now, or
    wait for a specific window?"

    Parameters
    ----------
    mode_gate_result : compute_business_mode_gate(payload) output (or the
        `mode_gate` key of compute_business_prediction()'s result dict).
        Needs at least "business_score", "employment_score",
        "recommended_mode".
    timed_windows : the `timed_windows` list from compute_business_prediction()
        (or _business_ad_windows()/_compute_windows_and_status() output) --
        each window a dict with start_date/end_date/label.
    timing_status : optional `timing_status` dict from the same call, used
        only to detect calendar-computation failure modes
        (NO_DOB/NO_DASHA_SEQUENCE/CALENDAR_COMPUTATION_FAILED/CALENDAR_EMPTY)
        that mean the timing dimension cannot be assessed at all.
    as_of_date : reference "today" for both the margin snapshot and the
        window lookup (defaults to date.today()). Exposed for deterministic
        testing.

    Returns
    -------
    Dict with "verdict" one of ACT_NOW / WAIT_FOR_WINDOW / RECONSIDER_MODE /
    INSUFFICIENT_DATA, plus mode_gate_basis / current_window /
    next_favorable_window / client_message / astrologer_detail and the same
    provisional-status disclaimer fields carried by every other output of
    this engine (model_status/calibration_status/disclaimer).
    """
    as_of = as_of_date or date.today()

    # ── Graceful degradation: never fabricate a verdict from incomplete data ──
    if not isinstance(mode_gate_result, Mapping):
        return _base_result(
            _VERDICT_INSUFFICIENT_DATA, as_of,
            reason="mode_gate_result missing or not a dict -- cannot assess the structural (business-vs-job) dimension.",
            client_message="We don't have enough chart data yet to compare business against staying employed, so no timing call can be made either.",
            astrologer_detail="mode_gate_result absent/malformed; compute_business_mode_gate() output required.",
        )

    # v-audit fix (correction-order item 1, real loophole caught on re-audit):
    # authoritative_recommendation.verdict/action_level are derived from
    # business_promise/job_promise, which are still computed off neutral-
    # default evidence during ABSTAIN_INSUFFICIENT_D1_DATA (engine.py forces
    # action_level/proceed to reflect abstention, but -- before this fix --
    # left `verdict` itself as whatever the layered system happened to
    # compute from those neutral defaults). This function only ever checked
    # `verdict` against _AUTHORITATIVE_JOB_LEANING_VERDICTS to decide whether
    # to downgrade ACT_NOW -- an abstaining chart whose neutral-default
    # verdict happened to read PURSUE_BUSINESS (not job-leaning) could still
    # reach an unqualified ACT_NOW here if the current window looked
    # favorable, directly contradicting the engine's own abstention. This is
    # checked FIRST, independent of engine.py's own verdict override, so
    # this function is safe even if called directly with a raw
    # authoritative_recommendation dict that hasn't had that override applied.
    if isinstance(authoritative_recommendation, Mapping):
        _decision_status = authoritative_recommendation.get("decision_status")
        if _decision_status is not None and _decision_status != "OK":
            return _base_result(
                _VERDICT_INSUFFICIENT_DATA, as_of,
                reason=(
                    f"authoritative_recommendation.decision_status={_decision_status!r} -- mandatory D1 "
                    f"structural inputs are missing/insufficient on this payload, so business_promise/"
                    f"job_promise/verdict/timing are all running on neutral-default evidence and cannot "
                    f"support ANY transition-timing call, including ACT_NOW."
                ),
                client_message=(
                    "We don't have enough reliable chart data yet to make a business-vs-employment "
                    "timing call -- this chart is in an abstention state, not a low-confidence read."
                ),
                astrologer_detail=(
                    f"decision_status={_decision_status!r} on authoritative_recommendation -- see "
                    f"engine.py's evidence_sufficiency.structural_recommendation / decision_status_note "
                    f"for which mandatory D1 inputs (house_lords/planet_house/planet_dignities) are "
                    f"missing. No ACT_NOW/WAIT_FOR_WINDOW/RECONSIDER_MODE verdict is meaningful while "
                    f"this holds, regardless of what the underlying (neutral-default-driven) margin or "
                    f"window computation below would otherwise produce."
                ),
            )

    business_score = mode_gate_result.get("business_score")
    employment_score = mode_gate_result.get("employment_score")
    if not isinstance(business_score, (int, float)) or not isinstance(employment_score, (int, float)):
        return _base_result(
            _VERDICT_INSUFFICIENT_DATA, as_of,
            reason="mode_gate_result missing business_score/employment_score.",
            mode_gate_basis={"business_score": business_score, "employment_score": employment_score},
            client_message="We don't have enough chart data yet to compare business against staying employed, so no timing call can be made either.",
            astrologer_detail="business_score/employment_score not numeric on mode_gate_result.",
        )

    if timed_windows is None:
        return _base_result(
            _VERDICT_INSUFFICIENT_DATA, as_of,
            reason="timed_windows not provided -- cannot assess the timing dimension.",
            mode_gate_basis={"business_score": business_score, "employment_score": employment_score},
            client_message="Your chart's mode strength was available, but the timing calendar was not, so we can't yet say whether now is the right moment.",
            astrologer_detail="timed_windows argument was None.",
        )

    if isinstance(timing_status, Mapping) and timing_status.get("status") in _UNFAVORABLE_TIMING_STATUSES:
        return _base_result(
            _VERDICT_INSUFFICIENT_DATA, as_of,
            reason=f"timing_status={timing_status.get('status')} -- dasha calendar could not be computed for this chart.",
            mode_gate_basis={"business_score": business_score, "employment_score": employment_score},
            client_message="Your chart's mode strength was available, but we could not compute your planetary-period calendar, so no timing call can be made yet.",
            astrologer_detail=f"timing_status.status={timing_status.get('status')!r}; see timing_status.error.",
        )

    margin = business_score - employment_score
    recommended_mode = mode_gate_result.get("recommended_mode")
    margin_tier = "HIGH" if margin >= _MARGIN_HIGH else ("MODERATE" if margin >= _MARGIN_MODERATE else "LOW")
    mode_gate_basis = {
        "business_score": business_score,
        "employment_score": employment_score,
        "recommended_mode": recommended_mode,
        "margin": round(margin, 2),
        "margin_tier": margin_tier,
    }

    # ── Structural gate: business must be BOTH the recommended mode AND at
    # least MODERATE-margin ahead of employment, using mode_gate's own
    # confidence-gap thresholds -- otherwise timing is moot: a favorable
    # window cannot manufacture chart-level business viability the static
    # gate itself does not support.
    business_favored = recommended_mode == "business" and margin >= _MARGIN_MODERATE
    if not business_favored:
        return _base_result(
            _VERDICT_RECONSIDER_MODE, as_of,
            reason=(
                f"mode_gate does not favor business over employment with adequate margin "
                f"(recommended_mode={recommended_mode!r}, margin={margin:.1f}, required>={_MARGIN_MODERATE})."
            ),
            mode_gate_basis=mode_gate_basis,
            # Audit fix (item 8): a favorable dasha window genuinely cannot
            # manufacture a full employment-exit case the structural gate
            # doesn't support -- but that does NOT mean timing is "moot".
            # A favorable window can still meaningfully support smaller,
            # reversible, controlled experimentation (consulting on the
            # side, client acquisition, a pilot project, a side practice)
            # while remaining employed, which is a real and actionable
            # reading rather than "nothing to say about timing".
            client_message=(
                "Your chart shows more support for staying employed right now -- the underlying "
                "structural signals don't yet clearly favor a full business over a salaried role, "
                "so no timing window can manufacture that on its own. That does not mean timing has "
                "nothing to offer: a favorable planetary period can still support controlled, "
                "reversible experimentation alongside your job -- consulting on the side, acquiring "
                "a first client, a pilot project, or a side practice -- rather than a full employment exit."
            ),
            astrologer_detail=(
                f"business_score={business_score} employment_score={employment_score} margin={margin:.1f} "
                f"(required>={_MARGIN_MODERATE}, reused from mode_gate.py's own confidence-gap thresholds); "
                f"recommended_mode={recommended_mode!r}. Structural gate not cleared for a full employment-exit "
                f"read; timing is NOT moot -- see client_message for the controlled-experimentation framing that "
                f"still applies to favorable windows even when the exit-level structural gate is not cleared."
            ),
        )

    # v-audit fix (item 6): the legacy margin/tier computed above (from
    # mode_gate's business_score vs employment_score) can disagree with
    # this engine's own AUTHORITATIVE verdict (business_promise vs
    # job_promise, contradiction-penalized -- see engine.py's
    # authoritative_recommendation, which recommendation.proceed/
    # heuristic_tier are themselves now driven by). Before this fix,
    # ACT_NOW was decided purely off the legacy margin/window, so a chart
    # whose authoritative headline verdict is HYBRID_LEANING_JOB (or
    # weaker) could still surface an unqualified "Act Now, your chart
    # favors business" -- exactly the contradiction the Karthick report
    # audit caught (headline HYBRID_LEANING_JOB vs an unqualified Act Now
    # box built on legacy margin=35/HIGH tier). When the authoritative
    # verdict is available and disagrees (leans job/hybrid rather than
    # business), the verdict is downgraded to a qualified caution rather
    # than a bare ACT_NOW, using the SAME action_level language
    # authoritative_recommendation already exposes so the two boxes read
    # consistently instead of contradicting each other.
    _authoritative_verdict = None
    _authoritative_disagrees = False
    if isinstance(authoritative_recommendation, Mapping):
        _authoritative_verdict = authoritative_recommendation.get("verdict")
        _authoritative_disagrees = _authoritative_verdict in _AUTHORITATIVE_JOB_LEANING_VERDICTS

    current_window = _window_covering(timed_windows, as_of)
    if current_window and current_window.get("label") in _FAVORABLE_LABELS:
        if _authoritative_disagrees:
            _action_level = authoritative_recommendation.get("action_level") if isinstance(authoritative_recommendation, Mapping) else None
            return _base_result(
                _VERDICT_RECONSIDER_MODE, as_of,
                reason=(
                    f"Timing favorable (current window label={current_window.get('label')}), but the "
                    f"authoritative business_promise/job_promise verdict is {_authoritative_verdict!r} "
                    f"(action_level={_action_level!r}), which disagrees with the legacy margin-based "
                    f"business_favored gate (margin={margin:.1f}, tier={margin_tier}) -- structural case "
                    f"is mixed, so an unqualified Act Now would contradict this report's own headline verdict."
                ),
                mode_gate_basis=mode_gate_basis,
                current_window=current_window,
                client_message=(
                    "Timing Favorable, But Structural Case Is Mixed -- Validate Before Committing. "
                    "The planetary period looks favorable, but the fuller structural read of your chart "
                    "(which weighs more evidence than the quick mode comparison) is not a clear win for "
                    "business over staying employed right now -- treat this as a signal to validate "
                    "further, not a green light to leave employment."
                ),
                astrologer_detail=(
                    f"margin={margin:.1f} (tier={margin_tier}) favored business via the legacy mode_gate "
                    f"comparison, and current window is favorable, but authoritative_recommendation.verdict="
                    f"{_authoritative_verdict!r} (action_level={_action_level!r}) disagrees -- downgraded from "
                    f"ACT_NOW to RECONSIDER_MODE per the v-audit reconciliation gate (item 6)."
                ),
            )
        return _base_result(
            _VERDICT_ACT_NOW, as_of,
            mode_gate_basis=mode_gate_basis,
            current_window=current_window,
            client_message=(
                "Now looks like a good time to move toward business -- your chart favors business over "
                "staying employed, and you're currently in a favorable planetary period for it too."
            ),
            astrologer_detail=(
                f"margin={margin:.1f} (tier={margin_tier}); current window {current_window.get('start_date')}"
                f"..{current_window.get('end_date')} (MD {current_window.get('md_lord')} / AD {current_window.get('ad_lord')}) "
                f"label={current_window.get('label')}."
            ),
        )

    next_window = _next_favorable_window(timed_windows, as_of)
    if next_window:
        return _base_result(
            _VERDICT_WAIT_FOR_WINDOW, as_of,
            mode_gate_basis=mode_gate_basis,
            current_window=current_window,
            next_favorable_window=next_window,
            client_message=(
                f"Consider waiting until {next_window.get('start_date')} to {next_window.get('end_date')}, "
                "when your chart's timing turns more favorable for business -- the structural signals already "
                "favor business over staying employed, it's the timing that suggests patience right now."
            ),
            astrologer_detail=(
                f"margin={margin:.1f} (tier={margin_tier}); current window label="
                f"{(current_window or {}).get('label', 'NONE_COVERING_AS_OF')}; next favorable window "
                f"{next_window.get('start_date')}..{next_window.get('end_date')} (MD {next_window.get('md_lord')} / "
                f"AD {next_window.get('ad_lord')}) label={next_window.get('label')}."
            ),
        )

    # Business favored structurally, current window not favorable, and no
    # favorable window found anywhere in the scored forecast horizon --
    # honest about the limit rather than fabricating a target date.
    return _base_result(
        _VERDICT_WAIT_FOR_WINDOW, as_of,
        reason="No STRONG_FAVORABLE/FAVORABLE window found within the scored forecast horizon.",
        mode_gate_basis=mode_gate_basis,
        current_window=current_window,
        client_message=(
            "Your chart shows more support for business than for staying employed, but we could not find a "
            "clearly favorable timing window within the period this report covers -- worth revisiting with a "
            "longer forecast horizon or a closer astrologer review before setting a specific date."
        ),
        astrologer_detail=(
            f"margin={margin:.1f} (tier={margin_tier}); current window label="
            f"{(current_window or {}).get('label', 'NONE_COVERING_AS_OF')}; no STRONG_FAVORABLE/FAVORABLE window "
            f"found among {len(timed_windows)} scored windows within the requested forecast horizon."
        ),
    )
