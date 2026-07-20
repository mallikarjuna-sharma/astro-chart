"""jyotish/view_model.py

Phase 2 of the career-report refactor: a presentation-agnostic view model
sitting between the raw engine/timeline output and the HTML templates.

Uses ONLY real field names produced by jyotish/timeline.py,
jyotish/timeline_inputs.py, and jyotish/engine.py — see the field-name
inventory in the refactor spec. Never invents data: any field not present
in the raw payload is simply omitted from the view model rather than
defaulted to a fabricated value.

`stability_score` and `visibility_score` do NOT exist anywhere in the real
pipeline output and are intentionally never referenced here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from Job_Career.timeline_inputs import compute_confidence_tier


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EvidenceChip:
    """One line of evidence in the 'evidence ladder' for a period — a single
    traceable claim (e.g. 'KP: Promotion houses supported') tagged with a
    verdict tier so the reader can see at a glance how strong the support is.
    """
    label: str
    verdict: str                 # "supporting" | "mixed" | "caution" | "verdict"
    detail: str = ""
    source_field: str = ""       # e.g. "kp_cusp_score", "d10_structural_score"


@dataclass
class ScoreStack:
    """A small bundle of the real sub_scores used to justify a period's
    headline verdict. Every attribute maps 1:1 to a real sub_scores key —
    nothing here is computed or invented beyond simple rounding."""
    career_activation: Optional[float] = None
    strength_product: Optional[float] = None
    d10_alignment: Optional[float] = None
    sav_support: Optional[float] = None
    kp_cusp_score: Optional[float] = None
    jaimini_score: Optional[float] = None
    yoga_bonus: Optional[float] = None
    d9_modifier: Optional[float] = None
    promotion_score: Optional[float] = None
    job_change_score: Optional[float] = None
    risk_score: Optional[float] = None
    gandanta_penalty: Optional[float] = None
    career_score: Optional[float] = None

    @classmethod
    def from_sub_scores(cls, sub_scores: Optional[Dict[str, Any]]) -> "ScoreStack":
        sub_scores = sub_scores or {}
        kwargs = {}
        for f in cls.__dataclass_fields__:
            if f in sub_scores and sub_scores[f] is not None:
                try:
                    kwargs[f] = round(float(sub_scores[f]), 3)
                except (TypeError, ValueError):
                    pass
        return cls(**kwargs)


@dataclass
class CareerPeriodView:
    period_id: str
    year_label: str
    md_lord: str = ""
    ad_lord: str = ""
    date_range: str = ""
    event_type: str = ""
    confidence_label: str = ""

    # Reader-facing (dual-lens: parent/student tone)
    parent_narrative_html: str = ""
    student_narrative_html: str = ""

    # Astro-lens content
    executive_summary_html: str = ""
    astrological_basis_html: str = ""
    kp_basis_html: str = ""
    d10_basis_html: str = ""
    jaimini_basis_html: str = ""
    transit_basis_html: str = ""

    evidence_chips: List[EvidenceChip] = field(default_factory=list)
    score_stack: Optional[ScoreStack] = None
    risk_flags: List[str] = field(default_factory=list)
    action_plan: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _fmt_date(d: Any) -> str:
    s = str(d or "")
    return s[:10] if s else ""


def _year_label(period: Dict[str, Any]) -> str:
    sd = _fmt_date(period.get("start_date"))
    ed = _fmt_date(period.get("end_date"))
    sy = sd[:4] if sd else ""
    ey = ed[:4] if ed else ""
    if sy and ey and sy != ey:
        return f"{sy}–{ey}"
    return sy or ey or ""


def build_period_view(period: Dict[str, Any], chart: Optional[Dict[str, Any]] = None,
                       context: Optional[Dict[str, Any]] = None) -> CareerPeriodView:
    """Build a CareerPeriodView from one real timeline period dict.

    `period` is one antardasha-period dict as produced by jyotish/timeline.py
    (fields: md_lord, ad_lord, pd_lord, sk_lord, pratyantar_dasha_lord,
    start_date, end_date, event_type, secondary_event_type, base_event_type,
    near_miss, event_hints, sub_scores{...}, plus whatever varga/KP/Jaimini/
    transit fields the timeline attached to this period).
    """
    period = period or {}
    chart = chart or {}
    context = context or {}

    md_lord = str(period.get("md_lord", "") or "")
    ad_lord = str(period.get("ad_lord", "") or "")
    sd = _fmt_date(period.get("start_date"))
    ed = _fmt_date(period.get("end_date"))
    date_range = f"{sd} → {ed}" if sd or ed else ""

    period_id = f"{md_lord}-{ad_lord}-{sd}".strip("-") or "period"

    # Canonicalize event_type at the point of view-model construction: this
    # is the actual finalization point for period output (enrich_timeline_sync
    # / resolve_uncertain_events in llm_narrative_builder.py is currently
    # unwired into the production pipeline, so `period` here is whatever
    # build_career_timeline() in timeline.py wrote). Prefer an explicit
    # resolved value if present, fall back to the deterministic event_type,
    # so downstream consumers always see one unambiguous, correctly-sourced
    # value regardless of which upstream stage last touched this dict.
    period["event_type"] = period.get("final_event_type", period.get("event_type"))
    period["raw_event_type"] = period.get("deterministic_event_type", period.get("event_type"))
    period["llm_suggested_event_type"] = period.get("llm_suggested_event_type", "")
    period["event_source"] = period.get("final_event_source", "deterministic")

    event_type = str(period.get("event_type", "") or "")

    # Confidence: caller supplies career_ctx/birth_time_known/retro_matches
    # via `context` (context["confidence"] if already computed, else we
    # leave confidence_label blank rather than guessing).
    confidence = context.get("confidence") or period.get("confidence")
    confidence_label = ""
    if isinstance(confidence, dict):
        confidence_label = str(confidence.get("label", "") or confidence.get("tier", ""))
    elif isinstance(confidence, str):
        confidence_label = confidence

    sub_scores = period.get("sub_scores") or {}
    score_stack = ScoreStack.from_sub_scores(sub_scores)

    risk_flags = []
    if period.get("near_miss"):
        risk_flags.append("Near-miss event window — signal present but below full threshold.")
    for tag in (period.get("event_hints") or []):
        if tag in ("JOB_LOSS", "FORCED_EXIT", "CAREER_PLATEAU"):
            risk_flags.append(tag.replace("_", " ").title())

    view = CareerPeriodView(
        period_id=period_id,
        year_label=_year_label(period),
        md_lord=md_lord,
        ad_lord=ad_lord,
        date_range=date_range,
        event_type=event_type,
        confidence_label=confidence_label,
        score_stack=score_stack,
        risk_flags=risk_flags,
    )
    return view


def build_sidebar_snapshot(context: Optional[Dict[str, Any]], chart: Optional[Dict[str, Any]],
                            periods: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Build the sidebar data structure: native snapshot, active dasha
    snapshot, D10 career signature, KP career promise, Jaimini career
    signal, transit pressure map, risk & opportunity radar.

    Every value here traces to a real field on `chart`/`context`/`periods`;
    stability_score and visibility_score are never referenced (they do not
    exist in the real pipeline output).
    """
    context = context or {}
    chart = chart or {}
    periods = periods or []

    current = next((p for p in periods if p.get("is_current")), None) or (periods[0] if periods else {})

    native_snapshot = {
        "employment_status": context.get("employment_status", ""),
        "designation": context.get("designation") or context.get("current_designation", ""),
        "years_experience": context.get("years_experience"),
        "birth_time_precision": context.get("birth_time_precision", ""),
    }

    active_dasha_snapshot = {
        "md_lord": current.get("md_lord", ""),
        "ad_lord": current.get("ad_lord", ""),
        "pd_lord": current.get("pd_lord", ""),
        "sk_lord": current.get("sk_lord", ""),
        "pratyantar_dasha_lord": current.get("pratyantar_dasha_lord", ""),
    }

    d10_signature = {
        "d10_lagna_sign": chart.get("d10_lagna_sign", ""),
        "d10_strength": chart.get("d10_strength"),
        "d10_structural_score": chart.get("d10_structural_score"),
        "d10_full_score": chart.get("d10_full_score"),
        "d10_house_lords": chart.get("d10_house_lords", {}),
        "d10_lagna_lord": chart.get("d10_lagna_lord", ""),
        "d10_h10_lord": chart.get("d10_h10_lord", ""),
    }

    kp_promise = {
        "kp_cusp_score": current.get("sub_scores", {}).get("kp_cusp_score") if current.get("sub_scores") else None,
        "kp_cusp_alignment": chart.get("kp_cusp_alignment", ""),
        "kp_ssl_score": chart.get("kp_ssl_score"),
        "kp_ruling_planets_score": chart.get("kp_ruling_planets_score"),
        "lagna_star_lord": chart.get("lagna_star_lord", ""),
        "moon_star_lord": chart.get("moon_star_lord", ""),
    }

    jaimini_signal = {
        "atmakaraka": chart.get("atmakaraka", ""),
        "amatyakaraka": chart.get("amatyakaraka", ""),
        "chara_karakas": chart.get("chara_karakas", {}),
        "arudha_lagna": chart.get("arudha_lagna", ""),
        "a10_sign": chart.get("a10_sign", ""),
        "karakamsha_sign": chart.get("karakamsha_sign", ""),
        "jaimini_score": current.get("sub_scores", {}).get("jaimini_score") if current.get("sub_scores") else None,
        "yogini_name": chart.get("yogini_name", ""),
    }

    transit_pressure = {
        "transit_flags": chart.get("transit_flags", []),
        "retrograde_planets": chart.get("retrograde_planets", []),
        "jupiter_house": chart.get("jupiter_house"),
        "saturn_theme": chart.get("saturn_theme", ""),
        "sade_sati_phase": chart.get("sade_sati_phase", ""),
        "workplace_friction_flags": (chart.get("workplace_dynamics", {}) or {}).get("friction_flags", []),
        "workplace_friction_score": (chart.get("workplace_dynamics", {}) or {}).get("friction_score"),
    }

    cur_scores = current.get("sub_scores", {}) or {}
    risk_radar = {
        "promotion_score": cur_scores.get("promotion_score"),
        "job_change_score": cur_scores.get("job_change_score"),
        "risk_score": cur_scores.get("risk_score"),
        "career_score": cur_scores.get("career_score"),
    }

    return {
        "native_snapshot": native_snapshot,
        "active_dasha_snapshot": active_dasha_snapshot,
        "d10_career_signature": d10_signature,
        "kp_career_promise": kp_promise,
        "jaimini_career_signal": jaimini_signal,
        "transit_pressure_map": transit_pressure,
        "risk_opportunity_radar": risk_radar,
    }


def build_report_view_model(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Top-level entry point: build the full view model for a report from
    the raw engine/timeline output dict.

    Expected raw shape (defensive — every key optional):
      {
        "context": {...parse_career_context() output...},
        "chart": {...natal/varga/KP/Jaimini/transit fields...},
        "periods": [...timeline antardasha period dicts...],
        "confidence": {...compute_confidence_tier() output...},
      }
    """
    raw = raw or {}
    context = raw.get("context", {}) or {}
    chart = raw.get("chart", {}) or {}
    periods = raw.get("periods", []) or []
    confidence = raw.get("confidence")

    if confidence and "confidence" not in context:
        context = dict(context)
        context["confidence"] = confidence

    period_views = [build_period_view(p, chart, context) for p in periods]
    sidebar = build_sidebar_snapshot(context, chart, periods)

    return {
        "sidebar": sidebar,
        "periods": period_views,
        "context": context,
        "chart": chart,
    }
