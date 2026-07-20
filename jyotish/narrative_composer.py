"""jyotish/narrative_composer.py

Phase 3 of the career-report refactor: composes the human-facing narrative
text for a CareerPeriodView, sitting on top of jyotish/view_model.py and
jyotish/astrology_explainer.py.

Traceability rule (hard requirement): every astrological claim rendered here
must trace to a real field on the period/chart view model. In particular, if
d10_structural_score / d10_full_score is low, compose_astrological_basis()
must describe the D10 signal as weak/neutral — it must never upgrade a weak
D10 into language implying a strong D10 promise.

Where a period corresponds to an annual-roadmap year that already has LLM-
generated narrative_html / astro_explanation_html (from
jyotish/llm_narrative_builder.generate_annual_roadmap_narratives), that
existing content is reused directly rather than discarded/regenerated.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .view_model import CareerPeriodView, EvidenceChip, ScoreStack
from .astrology_explainer import _career_weather, _kp_event_verdicts, _explain_yoga_tag


# ---------------------------------------------------------------------------
# Reader-facing narrative (parent / student tone)
# ---------------------------------------------------------------------------

def compose_reader_narrative(period: CareerPeriodView, tone: str,
                              roadmap_narrative: Optional[Dict[str, str]] = None) -> str:
    """Return reader-lens HTML for `tone` ('parent' or 'student').

    If `roadmap_narrative` (the {"narrative_html", "astro_explanation_html"}
    dict for this period's year, from generate_annual_roadmap_narratives) is
    supplied, its narrative_html is reused directly — this function does not
    re-derive plain-language narrative from scratch when the existing
    annual-roadmap layer has already produced one for this period.
    """
    if roadmap_narrative and roadmap_narrative.get("narrative_html"):
        return roadmap_narrative["narrative_html"]

    # Fallback: compose a minimal, strictly field-traceable narrative when no
    # roadmap narrative exists for this period (e.g. sub-annual antardasha
    # granularity not covered by the annual roadmap layer).
    parts: List[str] = []
    who = "your child" if tone == "parent" else "you"
    if period.md_lord and period.ad_lord:
        parts.append(
            f"<p>During this window ({period.date_range or period.year_label}), "
            f"{who} {'is' if tone == 'student' else 'is'} running the {period.md_lord} "
            f"main period with {period.ad_lord} as the active sub-period.</p>"
        )
    if period.event_type:
        parts.append(f"<p>The chart's dominant signal for this stretch is best described as "
                      f"<strong>{period.event_type}</strong>.</p>")
    score = period.score_stack.career_score if period.score_stack else None
    if score is not None:
        weather_emoji, weather_label = _career_weather(score, "Mixed")
        parts.append(f"<p>Overall career weather: {weather_emoji} {weather_label}.</p>")
    if not parts:
        parts.append("<p>No narrative-eligible data available for this period.</p>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Astrological basis (technical, dual-lens white/astro side)
# ---------------------------------------------------------------------------

def _d10_basis_html(period: CareerPeriodView, chart: Dict[str, Any]) -> str:
    structural = chart.get("d10_structural_score")
    full = chart.get("d10_full_score")
    strength = chart.get("d10_strength")
    lagna = chart.get("d10_lagna_sign", "")

    score = None
    for candidate in (full, structural, strength):
        if candidate is not None:
            score = float(candidate)
            break

    if score is None:
        return "<p>D10 (Dashamsha) data is not available for this chart.</p>"

    # Traceability guard: never claim a strong D10 promise when the real
    # score is low.
    if score >= 0.65:
        strength_label = "strong"
    elif score >= 0.4:
        strength_label = "moderate"
    else:
        strength_label = "weak/neutral"

    detail = (
        f"<p>D10 signature: <strong>{strength_label}</strong> "
        f"(score {score:.2f}{', Lagna ' + str(lagna) if lagna else ''}). "
    )
    if strength_label == "weak/neutral":
        detail += (
            "This chart's D10 does not currently support a strong career-elevation "
            "promise on its own — treat career timing conclusions in this period as "
            "resting primarily on dasha/KP/transit factors rather than D10 strength.</p>"
        )
    else:
        detail += "This supports reading D10 as a corroborating factor for career timing in this period.</p>"
    return detail


def _kp_basis_html(period: CareerPeriodView, chart: Dict[str, Any]) -> str:
    kp_house_chain = chart.get("kp_house_chain") or chart.get("kp_cusps")
    if not kp_house_chain:
        return "<p>KP cusp data is not available for this period.</p>"
    verdicts = _kp_event_verdicts(kp_house_chain, period.md_lord, period.ad_lord)
    if not verdicts:
        return "<p>No KP event verdicts could be computed for this period's MD/AD lords.</p>"
    rows = "".join(
        f"<li>{v['name']}: <strong>{v['verdict']}</strong> ({v['detail']})</li>" for v in verdicts
    )
    return f"<ul class='kp-verdict-list'>{rows}</ul>"


def _jaimini_basis_html(period: CareerPeriodView, chart: Dict[str, Any]) -> str:
    ak = chart.get("atmakaraka", "")
    amk = chart.get("amatyakaraka", "")
    if not ak and not amk:
        return "<p>Jaimini karaka data is not available for this chart.</p>"
    bits = []
    if ak:
        bits.append(f"Atmakaraka: <strong>{ak}</strong>")
    if amk:
        bits.append(f"Amatyakaraka: <strong>{amk}</strong>")
    active_lords = {period.md_lord, period.ad_lord}
    tie_in = ""
    if ak in active_lords or amk in active_lords:
        tie_in = " — the running dasha lord matches a chara karaka for this chart, a classical Jaimini timing trigger."
    return f"<p>{', '.join(bits)}{tie_in}.</p>"


def _transit_basis_html(period: CareerPeriodView, chart: Dict[str, Any]) -> str:
    flags = chart.get("transit_flags") or []
    if not flags:
        return "<p>No notable transit flags recorded for this period.</p>"
    items = "".join(f"<li>{f}</li>" for f in flags)
    return f"<ul class='transit-flag-list'>{items}</ul>"


def compose_astrological_basis(period: CareerPeriodView, chart: Optional[Dict[str, Any]] = None,
                                roadmap_narrative: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Assemble kp/d10/jaimini/transit basis blocks + a synthesis paragraph.

    Returns a dict with keys: kp_basis_html, d10_basis_html, jaimini_basis_html,
    transit_basis_html, astrological_basis_html (the synthesis).

    If `roadmap_narrative` has astro_explanation_html for this period's year,
    that is used as the synthesis paragraph directly (reuse, not discard).
    """
    chart = chart or {}
    kp_html = _kp_basis_html(period, chart)
    d10_html = _d10_basis_html(period, chart)
    jaimini_html = _jaimini_basis_html(period, chart)
    transit_html = _transit_basis_html(period, chart)

    if roadmap_narrative and roadmap_narrative.get("astro_explanation_html"):
        synthesis = roadmap_narrative["astro_explanation_html"]
    else:
        synthesis = (
            "<div class='astro-synthesis'>"
            f"{kp_html}{d10_html}{jaimini_html}{transit_html}"
            "</div>"
        )

    return {
        "kp_basis_html": kp_html,
        "d10_basis_html": d10_html,
        "jaimini_basis_html": jaimini_html,
        "transit_basis_html": transit_html,
        "astrological_basis_html": synthesis,
    }


# ---------------------------------------------------------------------------
# Evidence ladder
# ---------------------------------------------------------------------------

def build_evidence_ladder(period: CareerPeriodView, chart: Optional[Dict[str, Any]] = None) -> List[EvidenceChip]:
    """Build the supporting/mixed/caution/verdict evidence chips for a period,
    tracing each chip to a real sub_scores or chart field."""
    chart = chart or {}
    chips: List[EvidenceChip] = []
    ss = period.score_stack

    def _chip(label, value, threshold_support, threshold_caution, source_field):
        if value is None:
            return
        if value >= threshold_support:
            verdict = "supporting"
        elif value >= threshold_caution:
            verdict = "mixed"
        else:
            verdict = "caution"
        chips.append(EvidenceChip(label=label, verdict=verdict,
                                   detail=f"{value:.2f}", source_field=source_field))

    if ss:
        _chip("Career Activation", ss.career_activation, 0.6, 0.4, "career_activation")
        _chip("D10 Alignment", ss.d10_alignment, 0.6, 0.4, "d10_alignment")
        _chip("KP Cusp Score", ss.kp_cusp_score, 0.6, 0.4, "kp_cusp_score")
        _chip("Jaimini Score", ss.jaimini_score, 0.6, 0.4, "jaimini_score")
        _chip("SAV Support", ss.sav_support, 0.6, 0.4, "sav_support")
        if ss.risk_score is not None:
            verdict = "caution" if ss.risk_score >= 0.5 else "supporting"
            chips.append(EvidenceChip(label="Risk Score", verdict=verdict,
                                       detail=f"{ss.risk_score:.2f}", source_field="risk_score"))
        if ss.career_score is not None:
            chips.append(EvidenceChip(label="Overall Career Score", verdict="verdict",
                                       detail=f"{ss.career_score:.2f}", source_field="career_score"))

    for flag in period.risk_flags:
        chips.append(EvidenceChip(label=flag, verdict="caution", source_field="event_hints"))

    return chips


# ---------------------------------------------------------------------------
# Action plan
# ---------------------------------------------------------------------------

def build_action_plan(period: CareerPeriodView, chart: Optional[Dict[str, Any]] = None) -> List[str]:
    """Build a short, field-traceable action-plan list for a period. Kept
    conservative — general guidance tied to the period's real event_type /
    risk flags rather than invented specifics."""
    chart = chart or {}
    actions: List[str] = []
    et = (period.event_type or "").upper()

    if "PROMOTION" in et or "BREAKTHROUGH" in et:
        actions.append("Prepare a case for advancement (achievements, scope expansion) ahead of this window.")
    if "JOB_LOSS" in et or "FORCED_EXIT" in et:
        actions.append("Build a contingency plan (updated resume, network outreach) before this window begins.")
    if "EQUITY_EVENT" in et:
        actions.append("Review equity/compensation structures relevant to this period.")
    if "CAREER_PLATEAU" in et:
        actions.append("Consider skill development or lateral moves to counter a plateau signal.")

    ss = period.score_stack
    if ss and ss.risk_score is not None and ss.risk_score >= 0.5:
        actions.append("Treat this window with caution — risk indicators are elevated; avoid major unforced changes.")

    if period.risk_flags:
        actions.append("Near-miss/adverse signal present — monitor rather than act decisively on a single indicator.")

    if not actions:
        actions.append("No specific action flagged — maintain steady course through this period.")

    return actions
