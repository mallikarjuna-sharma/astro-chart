"""Career-timeline analysis — JyotishAI deterministic engine + optional LLM enrichment.

Mirrors the CLI's ``--mode career`` pipeline from
``LLMbased/field_deterministic_engine_v1_llm.py``: parse chart → build deterministic
timeline → (optional) LLM-enrich narrative HTML → aggregate outcome / trajectory /
calendar / md-arcs / foreign / micro-timing into a single JSON response.
"""
from __future__ import annotations

import copy
import logging
import os
from datetime import datetime, timezone
from typing import Any

from jyotish.astro import _get_active_dasha_lord
from jyotish.engine_io import parse_json_payload
from jyotish.payload import ENGINE_VERSION, NatalPayloadV2
from api.llm_policy import prepare_chart_for_api_llm

logger = logging.getLogger("api.career_timeline")


class CareerTimelineError(RuntimeError):
    """Raised when career-timeline analysis cannot complete."""


# ─── Helpers ──────────────────────────────────────────────────────────────────

_EVENT_COLOR: dict[str, str] = {
    "BREAKTHROUGH":              "#C9A84C",
    "PROMOTION":                 "#1E7B50",
    "LEADERSHIP_EXPANSION":      "#1E7B50",
    "INCOME_INFLECTION":         "#2563EB",
    "SALARY_HIKE":               "#2563EB",
    "JOB_CHANGE":                "#7C3AED",
    "FOREIGN_POSTING":           "#7C3AED",
    "GROWTH":                    "#059669",
    "SKILL_UPGRADE_PHASE":       "#0891B2",
    "AUTHORITY_SHIFT":           "#D97706",
    "RISK_PERIOD":               "#DC2626",
    "STABILITY":                 "#94A3B8",
    "TRANSITION":                "#6B7280",
    "RE_ENTRY":                  "#6B7280",
    "FIRST_JOB":                 "#059669",
    "CALIBRATION":               "#9CA3AF",
    "ENTREPRENEURSHIP_WINDOW":   "#B45309",
    "EQUITY_EVENT":              "#0369A1",
    "LATERAL_MOVE":              "#6D28D9",
    "SANDHI_PERIOD":             "#991B1B",
    "CAREER_PLATEAU":            "#B45309",
    "STAGNATION":                "#6B7280",
    "CAREER_THROUGH_PARTNERSHIP": "#0369A1",
}


def _narrative_llm_configured() -> bool:
    """Narrative builder only supports OpenAI/Anthropic (see jyotish.llm_narrative_builder)."""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if (os.getenv(var) or "").strip():
            return True
    return False


def _student_summary(payload: NatalPayloadV2) -> dict[str, Any]:
    return {
        "name": payload.name,
        "dob": payload.dob,
        "birth_place": payload.birth_place,
        "gender": payload.gender,
        "current_age": payload.current_age,
        "lagna_sign": payload.lagna_sign,
        "lagna_lord": payload.lagna_lord,
        "atmakaraka": payload.atmakaraka,
        "amatyakaraka": payload.amatyakaraka,
        "h10_lord": payload.h10_lord,
        "karakamsha": payload.karakamsha,
        "yogas": payload.detected_yogas,
        "school_board": payload.school_board,
        "risk_appetite": payload.risk_appetite,
        "active_dasha_lord": _get_active_dasha_lord(
            getattr(payload, "dasha_sequence", []),
            float(getattr(payload, "current_age", 0)),
        ) or "",
    }


def _compute_outcome(career_context: dict[str, Any], timeline: list[dict]) -> dict[str, str]:
    """Mirror of the inline `_compute_outcome_bar` in jyotish/web_report.py."""
    primary_opp = (career_context.get("primary_opportunity") or "").strip()
    peak_md     = (career_context.get("peak_md_lord")        or "").strip()
    peak_years  = str(career_context.get("peak_years", "")).strip()
    growth_arc  = (career_context.get("growth_arc")          or "").strip()

    if timeline:
        best = max(timeline, key=lambda b: b.get("career_score", 0))
        best_et = (best.get("event_type") or "Growth").replace("_", " ").title()
        if not primary_opp:
            primary_opp = best_et
        if not peak_md:
            peak_md = best.get("md_lord", "—")
        if not peak_years:
            ys = (best.get("start_date") or "")[:4]
            ye = (best.get("end_date")   or "")[:4]
            peak_years = f"{ys}–{ye}" if ys and ye and ys != ye else ys
        if not growth_arc:
            scores = [b.get("career_score", 0) for b in timeline]
            avg = sum(scores) / len(scores) if scores else 0
            mx  = max(scores) if scores else 0
            growth_arc = (
                "Strong Upward"   if mx  >= 0.75 else
                "Moderate Growth" if avg >= 0.55 else
                "Steady"          if avg >= 0.45 else
                "Developing"
            )
    return {
        "primary_opportunity": primary_opp or "—",
        "peak_md_lord":        peak_md     or "—",
        "peak_years":          peak_years  or "—",
        "growth_arc":          growth_arc  or "—",
    }


def _build_trajectory(timeline: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in timeline:
        et    = (b.get("event_type") or "STABILITY").replace("FORECAST_", "")
        label = f"{b.get('ad_lord', '?')} ({(b.get('start_date') or '')[:7]})"
        out.append({
            "label":      label,
            "score":      round(float(b.get("career_score", 0.5)) * 100, 1),
            "color":      _EVENT_COLOR.get(et, "#6B7280"),
            "event_type": et,
        })
    return out


def _build_calendar(timeline: list[dict]) -> list[dict[str, Any]]:
    """Best block per calendar year — used for the Annual Career Calendar grid."""
    by_year: dict[int, dict[str, Any]] = {}
    for b in timeline:
        sd = (b.get("start_date") or "")[:4]
        if not sd.isdigit():
            continue
        yr = int(sd)
        score = float(b.get("career_score", 0))
        prev = by_year.get(yr)
        if prev is None or score > prev["_raw"]:
            et = (b.get("event_type") or "STABILITY").replace("FORECAST_", "")
            by_year[yr] = {
                "year":       yr,
                "event_type": et.replace("_", " ").title(),
                "ad_lord":    b.get("ad_lord", ""),
                "score":      int(round(score * 100)),
                "color":      _EVENT_COLOR.get(et, "#6B7280"),
                "_raw":       score,
            }
    return [
        {k: v for k, v in row.items() if k != "_raw"}
        for row in sorted(by_year.values(), key=lambda r: r["year"])
    ]


def _build_md_arcs(timeline: list[dict]) -> list[dict[str, Any]]:
    """One MD-narrative entry per unique Mahadasha lord encountered in the timeline."""
    seen: dict[str, dict[str, Any]] = {}
    for b in timeline:
        md = b.get("md_lord", "")
        if not md or md in seen:
            continue
        seen[md] = {
            "md_lord":    md,
            "start_date": b.get("md_start_date", "") or b.get("start_date", ""),
            "end_date":   b.get("md_end_date", "")   or b.get("end_date",   ""),
            "narrative":  b.get("md_narrative", "") or b.get("md_arc", ""),
        }
    return list(seen.values())


def _extract_foreign(timeline: list[dict]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pull `foreign_opportunity` off each block into a flat list + summary meta."""
    opps: list[dict[str, Any]] = []
    for b in timeline:
        fo = b.get("foreign_opportunity")
        if isinstance(fo, dict):
            # Avoid leaking nested back-references; copy and tag the parent dates.
            fo_copy = copy.deepcopy(fo)
            fo_copy.setdefault("md_lord",   b.get("md_lord", ""))
            fo_copy.setdefault("ad_lord",   b.get("ad_lord", ""))
            fo_copy.setdefault("start_date", b.get("start_date", ""))
            fo_copy.setdefault("end_date",   b.get("end_date", ""))
            opps.append(fo_copy)

    total = len(opps)
    if not opps:
        return opps, {
            "total": 0, "high": 0, "moderate": 0, "mild": 0,
            "peak_score": 0.0, "peak_period": "", "geo_summary": "",
        }

    high     = sum(1 for o in opps if o.get("foreign_score", 0) >= 0.65)
    moderate = sum(1 for o in opps if 0.45 <= o.get("foreign_score", 0) < 0.65)
    mild     = sum(1 for o in opps if o.get("foreign_score", 0) < 0.45)
    peak     = max(opps, key=lambda o: o.get("foreign_score", 0))
    geo_set  = {o.get("geo_affinity", "") for o in opps if o.get("geo_affinity")}
    geo_summary = " / ".join(sorted(geo_set)[:3]) if geo_set else ""

    return opps, {
        "total":       total,
        "high":        high,
        "moderate":    moderate,
        "mild":        mild,
        "peak_score":  round(float(peak.get("foreign_score", 0)), 3),
        "peak_period": f"{peak.get('md_lord', '')}–{peak.get('ad_lord', '')}",
        "geo_summary": geo_summary,
    }


def _build_chart_insights(
    payload: NatalPayloadV2,
    blocks: list[dict[str, Any]],
    confidence: dict[str, Any],
    display_confidence_label: str,
) -> dict[str, Any]:
    """Sidebar dashboard data — mirrors jyotish/web_report._tl_sidebar_html()."""
    em = "—"
    current = next((b for b in blocks if b.get("is_current")), blocks[0] if blocks else {})
    md_lord = current.get("md_lord", "") or em
    ad_lord = current.get("ad_lord", "") or em

    house_lords = getattr(payload, "house_lords", None) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    true_dignities = (
        getattr(payload, "true_planet_dignities", None)
        or getattr(payload, "planet_dignities", {})
        or {}
    )
    planet_strength = getattr(payload, "planet_strength", {}) or {}
    kp_cusps = getattr(payload, "kp_cusp_data", {}) or {}
    d10_house_lords = getattr(payload, "d10_house_lords", {}) or {}
    d10_house_occupancy = getattr(payload, "d10_house_occupancy", {}) or {}
    ak = getattr(payload, "atmakaraka", "") or ""
    amk = getattr(payload, "amatyakaraka", "") or ""

    md_houses_ruled = sorted(
        (h for h, lord in house_lords.items() if lord == md_lord),
        key=lambda x: int(x) if str(x).isdigit() else 0,
    )
    md_house = planet_house.get(md_lord)
    md_house_str = f"House {md_house}" if md_house else em

    planets: list[dict[str, Any]] = []
    for pname in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"):
        score = planet_strength.get(pname)
        if score is None:
            continue
        tags: list[str] = []
        if pname == ak:
            tags.append("AK")
        if pname == amk:
            tags.append("AmK")
        planets.append({
            "name": pname,
            "score": round(float(score), 2),
            "pct": max(0, min(100, round(float(score) / 2.5 * 100))),
            "dignity": true_dignities.get(pname, "") or "",
            "tags": tags,
        })

    h10_cusp = (kp_cusps or {}).get("H10", {}) or {}
    kp_policy = getattr(payload, "calculation_policy", None)
    kp_precise = bool(getattr(kp_policy, "precise_cusps_allowed", True))

    yogas = getattr(payload, "yogas_present", None) or getattr(payload, "detected_yogas", None) or []

    return {
        "snapshot": {
            "lagna_sign": getattr(payload, "lagna_sign", "") or em,
            "current_dasha": f"{md_lord}–{ad_lord}" if md_lord != em else em,
            "atmakaraka": ak or em,
            "confidence": display_confidence_label or confidence.get("label") or confidence.get("tier") or em,
        },
        "planetary_strength": planets,
        "d10": {
            "lagna": getattr(payload, "d10_lagna_sign", "") or em,
            "h10_lord": d10_house_lords.get("10", "") or em,
            "h10_occupants": (d10_house_occupancy or {}).get("10", []) or [],
            "strength_score": round(float(getattr(payload, "d10_strength", 0) or 0), 2),
        },
        "kp": {
            "sign_lord": h10_cusp.get("sign_lord", "") or em,
            "star_lord": h10_cusp.get("star_lord", "") or em,
            "sub_lord": h10_cusp.get("sub_lord", "") or em,
            "sub_sub_lord": h10_cusp.get("sub_sub_lord", "") or em,
            "birth_time_uncertain": not kp_precise,
        },
        "kn_rao": {
            "md_lord": md_lord,
            "md_lord_house": md_house_str,
            "md_houses_ruled": ", ".join(str(h) for h in md_houses_ruled) if md_houses_ruled else em,
        },
        "parashara": {
            "lagna_lord": getattr(payload, "lagna_lord", "") or em,
            "lagna_lord_dignity": true_dignities.get(getattr(payload, "lagna_lord", ""), "") or em,
            "active_yogas": ", ".join(yogas[:6]) if yogas else em,
        },
        "jaimini": {
            "atmakaraka": ak or em,
            "amatyakaraka": amk or em,
            "arudha_lagna": getattr(payload, "arudha_lagna", "") or em,
            "karma_pada": getattr(payload, "a10_sign", "") or em,
            "karakamsha": getattr(payload, "karakamsha_sign", "") or getattr(payload, "karakamsha", "") or em,
            "darakaraka": getattr(payload, "darakaraka", "") or em,
        },
    }


def _build_report_meta(
    blocks: list[dict[str, Any]],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    """Confidence banners + outcome-strength table for the report header area."""
    from Job_Career.gap_corrections_career_timeline_2026_07 import (
        OUTCOME_STRENGTH_TABLE,
        retro_confidence_label,
    )

    retro_matches = int((blocks[0].get("retro_matches", 0) if blocks else 0) or 0)
    display_label, coverage_note = retro_confidence_label(confidence, retro_matches)
    outcome_rows = [{"outcome": o, "strength": s} for o, s in OUTCOME_STRENGTH_TABLE]
    return {
        "confidence": confidence,
        "display_confidence_label": display_label,
        "confidence_coverage_note": coverage_note,
        "retro_validation": (confidence or {}).get("retro_validation") or {},
        "outcome_strength": outcome_rows,
    }


def _maybe_enrich_llm(payload: NatalPayloadV2) -> bool:
    """Run LLM narrative enrichment on payload.career_timeline in-place.

    Returns True if enrichment ran successfully.
    """
    timeline = payload.career_timeline or []
    if not timeline:
        return False

    try:
        from Job_Career.timeline import TimelineChartInput
        from jyotish.llm_narrative_builder import enrich_timeline_sync

        chart_in = TimelineChartInput.from_payload(payload)
        career_theme = (getattr(payload, "llm_context", {}) or {}).get(
            "career_theme_str", ""
        )
        field_ctx = getattr(payload, "llm_selection_rationale", "") or ""

        enriched = enrich_timeline_sync(
            timeline,
            getattr(payload, "career_context", {}) or {},
            chart_input             = chart_in,
            career_theme_str        = career_theme,
            field_selection_context = field_ctx,
            run_phase2_resolution   = True,
        )
        payload.career_timeline = enriched
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM enrichment skipped: %s", exc)
        return False


# ─── Public entry point ───────────────────────────────────────────────────────


def run_career_timeline(
    chart: dict[str, Any],
    career_context_override: dict[str, Any] | None = None,
    enrich_llm: bool = True,
) -> dict[str, Any]:
    """Parse chart JSON, build the career timeline, and return a structured response.

    Parameters
    ----------
    chart : full consolidated chart JSON (same shape as /api/education-analysis).
            May contain a `career_context` block; the engine pulls it during parse.
    career_context_override : if provided, merged on top of any career_context in `chart`.
    enrich_llm : when True (and an LLM key is configured), runs the per-AD narrative
                 enrichment. Disable for fast, deterministic-only output.

    Returns
    -------
    dict matching CareerTimelineResponse.
    """
    # Apply career_context override (shallow merge) so callers can post a separate
    # career_context body without rebuilding the entire chart JSON.
    if career_context_override:
        chart = dict(chart)
        existing = dict(chart.get("career_context") or {})
        existing.update(career_context_override)
        chart["career_context"] = existing

    chart = prepare_chart_for_api_llm(chart)
    payload = parse_json_payload(chart, build_timeline=True)

    cc = payload.career_context or {}
    blocked = cc.get("_block_reason")
    if blocked:
        raise CareerTimelineError(
            f"Career timeline could not be generated: {blocked}. "
            "Check the career_context block (employment_status, current_age, etc.)."
        )

    timeline = payload.career_timeline or []
    if not timeline:
        raise CareerTimelineError(
            "Engine returned an empty timeline. The career_context may be missing "
            "or out of the supported age/employment range."
        )

    # Even without an OpenAI/Anthropic key, `enrich_timeline_sync` populates each
    # block with deterministic fallback HTML (Executive Summary / Astrological
    # Dynamics / Strategic Action Plan + per-PD micro-prediction). The frontend
    # renders those uniformly. The `llm_enriched` flag tells the client whether
    # the prose was authored by a real LLM or generated from templates.
    llm_ran = False
    if enrich_llm:
        enrichment_ok = _maybe_enrich_llm(payload)
        timeline = payload.career_timeline or timeline
        llm_ran = enrichment_ok

    outcome             = _compute_outcome(cc, timeline)
    trajectory          = _build_trajectory(timeline)
    calendar            = _build_calendar(timeline)
    md_arcs             = _build_md_arcs(timeline)
    foreign_opps, fmeta = _extract_foreign(timeline)

    confidence = (timeline[0].get("confidence") if timeline else None) or {}
    report_meta = _build_report_meta(timeline, confidence if isinstance(confidence, dict) else {})
    chart_insights = _build_chart_insights(
        payload,
        timeline,
        confidence if isinstance(confidence, dict) else {},
        report_meta["display_confidence_label"],
    )

    return {
        "engine_version": ENGINE_VERSION,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "student":        _student_summary(payload),
        "career_context": cc,
        "outcome":        outcome,
        "trajectory":     trajectory,
        "calendar":       calendar,
        "md_arcs":        md_arcs,
        "blocks":         timeline,
        "foreign_opportunities": foreign_opps,
        "foreign_meta":   fmeta,
        "micro_timing":   payload.micro_timing or {},
        "llm_enriched":   llm_ran,
        "chart_insights": chart_insights,
        "report_meta":    report_meta,
    }
