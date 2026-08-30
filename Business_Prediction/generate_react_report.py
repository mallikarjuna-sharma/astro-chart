"""Standalone React report generator.

Reads a business_debug.json (the same "prediction" dict
generate_business_report.py consumes) and produces ONE self-contained
.html file: React 18 + Babel Standalone loaded from CDN, the report data
embedded as a plain JS object (no fetch, no build step, no server --
opens directly in any browser, offline included except for the two CDN
<script> tags), and a full component tree covering the same ground as
the existing Python-rendered report (cover, KPI grid with score bars,
at-a-glance, sector leaderboard, timed windows, recommendation,
detected yogas, significator evidence, financial readiness, confidence,
glossary) behind a Client/Astrologer view toggle mirroring the existing
combined report's UX.

Deliberately does NOT replace generate_business_report.py -- that script
keeps producing its own HTML report unchanged. This is a second, parallel
renderer over the same debug JSON for users who want a more app-like,
component-based UI.

Usage:
    python generate_react_report.py <business_debug.json> [--out FILE] [--name NAME]
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def _fmt_pct(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return round(float(v), 1)
    return None


def _tier(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return "unknown"
    if v >= 70:
        return "strong"
    if v >= 50:
        return "moderate"
    return "weak"


def _build_report_data(
    prediction: Dict[str, Any],
    name_override: Optional[str] = None,
    dual_narrative: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rec = prediction.get("recommendation", {}) or {}
    authoritative = prediction.get("authoritative_recommendation", {}) or {}
    confidence = prediction.get("business_over_job_confidence", {}) or {}
    sig = prediction.get("significators", {}) or {}
    top_sectors = prediction.get("top_sectors", []) or []
    timed_windows = prediction.get("timed_windows", []) or []
    yogas = prediction.get("detected_yogas", []) or []
    financial = (authoritative.get("financial_readiness") or prediction.get("financial_readiness") or {})
    contradictions = prediction.get("contradiction_findings", []) or []

    kpi_defs = [
        ("business_promise", "Business Promise", "Strength of an independent-enterprise path", prediction.get("business_promise")),
        ("job_promise", "Job Promise", "Strength of a salaried-employment path", prediction.get("job_promise")),
        ("independent_profession_promise", "Independent-Profession Promise", "Solo practice or consulting without a full business structure", prediction.get("independent_profession_promise")),
        ("business_field_fit", "Business Sector Fit", "How well the top sector matches this chart", prediction.get("business_field_fit")),
        ("business_execution_capacity", "Execution Capacity", "Day-to-day ability to run it (D10-confirmed)", prediction.get("business_execution_capacity")),
        ("business_profitability", "Profitability", "Support for turning activity into real profit", prediction.get("business_profitability")),
        ("business_stability", "Stability", "How sustainable this path looks over time", prediction.get("business_stability")),
        ("current_timing_readiness", "Timing Readiness", "Whether the current dasha activates business houses", prediction.get("current_timing_readiness")),
    ]
    kpis = [
        {"key": k, "label": label, "hint": hint, "value": _fmt_pct(v), "tier": _tier(v)}
        for k, label, hint, v in kpi_defs
    ]

    top_sector = top_sectors[0] if top_sectors else None
    favorable_windows = [w for w in timed_windows if str(w.get("label", "")).upper() in ("FAVORABLE", "STRONG_FAVORABLE")]
    top_window = favorable_windows[0] if favorable_windows else (timed_windows[0] if timed_windows else None)

    evidence = sig.get("evidence", []) or []
    positive = sorted(
        [e for e in evidence if str(e.get("polarity", "")).upper() == "POSITIVE"],
        key=lambda e: e.get("weight", 0), reverse=True,
    )[:12]
    negative = sorted(
        [e for e in evidence if str(e.get("polarity", "")).upper() == "NEGATIVE"],
        key=lambda e: e.get("weight", 0), reverse=True,
    )[:12]
    top_risk = negative[0]["note"] if negative else None

    sectors_out = [
        {
            "rank": i + 1,
            "sector": s.get("sector"),
            "label": s.get("label"),
            "score": _fmt_pct(s.get("score")),
            "archetype_family": s.get("archetype_family"),
            "match_confidence": s.get("match_confidence"),
            "capital_intensity": s.get("capital_intensity"),
            "core_houses_used": s.get("core_houses_used", []),
            "core_planets_used": s.get("core_planets_used", []),
        }
        for i, s in enumerate(top_sectors)
    ]

    windows_out = [
        {
            "start_date": w.get("start_date"),
            "end_date": w.get("end_date"),
            "md_lord": w.get("md_lord"),
            "ad_lord": w.get("ad_lord"),
            "label": w.get("label"),
            "net_score": _fmt_pct(w.get("net_score")),
            "evidence": (w.get("evidence") or [])[:4],
        }
        for w in timed_windows
    ]

    yogas_out = [
        {
            "yoga_name": y.get("yoga_name"),
            "sanskrit_name": y.get("sanskrit_name"),
            "confidence_tier": y.get("confidence_tier"),
            "effect": y.get("effect"),
            "detail": y.get("detail"),
        }
        for y in yogas
    ]

    def _ev_out(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {"note": e.get("note"), "weight": e.get("weight"), "family": e.get("family")}
            for e in items
        ]

    verdict = {
        "final_category": authoritative.get("final_category") or rec.get("venture_type", "").upper(),
        "action_level": authoritative.get("action_level"),
        "business_promise": _fmt_pct(prediction.get("business_promise")),
        "job_promise": _fmt_pct(prediction.get("job_promise")),
        "comparative_advantage": bool(rec.get("comparative_advantage")),
        "hybrid_suggested": bool(rec.get("hybrid_suggested")),
        "proceed": bool(rec.get("proceed")),
        "reasoning": rec.get("reasoning", ""),
    }

    return {
        "name": name_override or prediction.get("name") or "Chart Subject",
        "generated": datetime.now().strftime("%d %b %Y"),
        "rule_pack_version": prediction.get("rule_pack_version", "—"),
        "verdict": verdict,
        "kpis": kpis,
        "top_sector": ({"label": top_sector.get("label"), "score": _fmt_pct(top_sector.get("score"))} if top_sector else None),
        "top_window": ({
            "start_date": top_window.get("start_date"), "end_date": top_window.get("end_date"),
            "md_lord": top_window.get("md_lord"), "ad_lord": top_window.get("ad_lord"),
            "label": top_window.get("label"),
        } if top_window else None),
        "top_risk": top_risk,
        "sectors": sectors_out,
        "timed_windows": windows_out,
        "yogas": yogas_out,
        "significators": {"positive": _ev_out(positive), "negative": _ev_out(negative)},
        "financial_readiness": {
            "status": financial.get("status"),
            "certified": bool(financial.get("certified") or authoritative.get("capital_readiness_certified")),
            "missing_fields": financial.get("missing_fields", []),
            "note": financial.get("note", ""),
        },
        "confidence": {
            "label": confidence.get("label"),
            "score_0_1": confidence.get("score_0_1"),
            "method_agreement": confidence.get("method_agreement"),
            "overall_leaning": confidence.get("overall_leaning"),
        },
        "contradictions": [
            {"note": c.get("note"), "weight": c.get("weight"), "mode": c.get("mode")}
            for c in contradictions
        ],
        # Same consent-gated dual_narrative dict generate_business_report.py's
        # combined_html already renders (_generate_dual_audience_narratives()
        # in generate_business_report.py) -- passed straight through here
        # rather than re-derived, so the React edition can never show a
        # narrative the caller didn't actually get real LLM consent+output
        # for. None when narrative generation was skipped/unavailable; the
        # UI hides the Narrative nav entry entirely in that case rather
        # than showing an empty section.
        "narrative": ({
            "astrologer_paragraphs": dual_narrative.get("astrologer_narrative_paragraphs", []),
            "client_paragraphs": dual_narrative.get("client_narrative_paragraphs", []),
            "disclaimer": dual_narrative.get("disclaimer", ""),
        } if dual_narrative else None),
    }


_GLOSSARY_TERMS = [
    ("Lagna (Ascendant)", "The sign rising on the eastern horizon at birth. Anchors the whole chart -- every house is counted from it."),
    ("House (Bhava)", "One of 12 life-domain divisions -- e.g. 2nd house is wealth, 7th is partnership/trade, 10th is career/status."),
    ("House Lord", "The planet ruling the sign in a given house. A house's strength is read largely through its lord's placement and dignity."),
    ("Kendra / Trikona / Dusthana", "Kendras (1/4/7/10) are pillars of strength. Trikonas (1/5/9) are fortune/merit. Dusthanas (6/8/12) are struggle/debt/loss."),
    ("Dignity", "How empowered a planet is in its sign: Exalted (strongest) to Debilitated (weakest), with Own Sign/Moolatrikona in between."),
    ("Yoga", "A named planetary combination classical texts link to a specific outcome, e.g. Raja Yoga (status) or Dhana Yoga (wealth)."),
    ("Dasha (Mahadasha / Antardasha)", "The classical timing system dividing a lifetime into planetary periods used to flag favorable/cautionary windows."),
    ("Varga (D9 / D10)", "Charts derived from the birth chart for finer confirmation: D9 for durability/fortune, D10 for career execution specifically."),
    ("KP Sub-Lord", "A modern house-cusp refinement used here only when the chart's house system is confirmed Placidus."),
    ("Jaimini Karakas", "Atmakaraka (soul significator) and Amatyakaraka (career significator) -- a separate corroborating system based on degree, not house lordship."),
    ("Combustion", "A planet's proximity to the Sun weakening its standalone visibility/strength, discounted here by degree of separation."),
    ("Argala", "A Jaimini-system planetary intervention on a house that can support or obstruct that house's promise depending on which planets cause it."),
]


def _safe_script_embed(text: str) -> str:
    """Makes `text` safe to place verbatim inside a <script> element's raw
    text content (whether type="application/json" or type="text/plain").

    Per the HTML5 spec, a browser's HTML parser reads everything inside
    <script>...</script> as raw text -- it does NOT decode HTML entities
    there (an earlier version of this generator used html.escape() on the
    JSX source under the mistaken assumption it would, which produced a
    JSX file full of literal "&#x27;" text that failed to parse; this was
    only found by executing the actual generated file with a real parser
    rather than eyeballing the HTML). The only thing that genuinely breaks
    <script> parsing is the literal case-insensitive substring "</script"
    appearing inside it, which the parser treats as the closing tag no
    matter what type attribute is set -- so that's the only substitution
    needed, applied to every script payload this file embeds (JSON data
    blocks and the JSX source block alike).
    """
    return text.replace("</script", "<\\/script").replace("</SCRIPT", "<\\/SCRIPT")


def render_html(report_data: Dict[str, Any]) -> str:
    data_json = _safe_script_embed(json.dumps(report_data, ensure_ascii=False, default=str))
    glossary_json = _safe_script_embed(json.dumps(_GLOSSARY_TERMS, ensure_ascii=False))
    title = _html.escape(f"Business Prediction Analysis — {report_data.get('name', '')}")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone@7/babel.min.js"></script>
<style>
{_shared_css()}
</style>
</head>
<body>
<div id="root"></div>
<script id="report-data" type="application/json">{data_json}</script>
<script id="glossary-data" type="application/json">{glossary_json}</script>
<script id="app-source" type="text/plain">{_safe_script_embed(_app_jsx())}</script>
<script>
// Manual Babel transform instead of Babel Standalone's automatic
// type="text/babel" script scanning: the bundled preset-react in current
// babel-standalone defaults to the "automatic" JSX runtime, which injects
// `import {{ jsx as _jsx }} from "react/jsx-runtime"` -- an ES module
// import that throws "Cannot use import statement outside a module" the
// moment it runs as a plain classic <script>, since there is no bundler
// or <script type="module"> here to resolve it. Forcing runtime:"classic"
// explicitly (React.createElement calls only, no import) is what actually
// works in a script loaded straight off the filesystem/CDN with no build
// step.
(function() {{
  var src = document.getElementById('app-source').textContent;
  var out = Babel.transform(src, {{ presets: [["react", {{ runtime: "classic" }}]] }});
  (0, eval)(out.code);
}})();
</script>
</body>
</html>
"""


def _shared_css() -> str:
    # Dashboard-shell redesign: a persistent left sidebar (subject/verdict
    # summary, view switch, section nav) plus a wide main content area,
    # replacing the earlier top-tabs-over-a-1180px-single-column layout.
    # The previous layout put every section in a ~1180px centered column
    # no matter how wide the browser was -- on any real monitor that left
    # 30-40% of the viewport as dead margin either side. This shell scales
    # main-content to the available width (up to a 1600px cap so lines of
    # prose don't get uncomfortably long) and lets content-dense sections
    # (KPI grid, sector leaderboard, timed windows) lay out in genuine
    # multi-column grids instead of one narrow stacked list.
    return """
:root {
  --navy:#122347; --navy-2:#1c3566; --gold:#c9a227; --gold-light:#e6c65c;
  --green:#1a9c5f; --green-bg:#e6f6ee; --amber:#b8790a; --amber-bg:#fdf2e0;
  --red:#c23a3a; --red-bg:#fbe9e9; --ink:#1b2436; --ink-soft:#5a6478;
  --line:#e4e8f0; --gray-bg:#eef1f6; --card-bg:#fff; --sidebar-w:272px;
}
* { box-sizing: border-box; }
html, body { margin:0; height:100%; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: var(--ink); background:#f3f5fa; }
a { color: var(--navy-2); }
h1,h2,h3 { color: var(--navy); font-weight: 700; letter-spacing:-.01em; margin: 0 0 8px; }
h2 { font-size: 19px; }
h3 { font-size: 14.5px; margin-top: 16px; }
p { color: var(--ink-soft); font-size: 13.5px; line-height: 1.55; }
.card { background: var(--card-bg); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(20,30,60,.03); }

/* ---- shell: sidebar + main ---- */
.app-shell { display:flex; align-items:stretch; min-height:100vh; }
.sidebar {
  width: var(--sidebar-w); flex-shrink:0; background: linear-gradient(180deg, var(--navy) 0%, #0d1a33 100%);
  color:#fff; padding: 22px 18px 18px; position:sticky; top:0; height:100vh; overflow-y:auto;
  display:flex; flex-direction:column; gap:16px;
}
.sidebar-kicker { font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color: var(--gold-light); font-weight:700; }
.sidebar-name { font-size:19px; font-weight:800; color:#fff; margin-top:2px; line-height:1.25; }
.sidebar-meta { font-size:11px; color:#9fb0d6; margin-top:4px; }
.sidebar-verdict { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius:10px; padding:12px 14px; }
.sidebar-verdict-label { font-size:10px; letter-spacing:.08em; text-transform:uppercase; color:#9fb0d6; font-weight:700; }
.sidebar-verdict-value { font-size:16.5px; font-weight:800; margin-top:3px; line-height:1.3; }
.sidebar-verdict-value.job { color:#f5c56b; } .sidebar-verdict-value.business { color:#7be3ab; } .sidebar-verdict-value.hybrid { color:#f5c56b; }
.sidebar-verdict-meta { font-size:11px; color:#9fb0d6; margin-top:4px; }
.viewswitch { display:flex; gap:4px; background: rgba(255,255,255,.06); border-radius:10px; padding:4px; }
.vs-btn { flex:1; border:none; background:none; padding: 8px 6px; border-radius: 7px; font-size:12.5px; font-weight:600; color:#b9c4de; cursor:pointer; }
.vs-btn.active { background:#fff; color: var(--navy); }
.sidebar-nav { display:flex; flex-direction:column; gap:2px; flex:1; overflow-y:auto; }
.sidebar-nav button {
  display:flex; align-items:center; gap:9px; text-align:left; border:none; background:none; color:#c4cee6;
  padding: 9px 10px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer;
}
.sidebar-nav button .nav-dot { width:6px; height:6px; border-radius:50%; background:#4c5c85; flex-shrink:0; }
.sidebar-nav button:hover { background: rgba(255,255,255,.06); color:#fff; }
.sidebar-nav button.active { background: rgba(230,198,92,.14); color:#fff; }
.sidebar-nav button.active .nav-dot { background: var(--gold-light); }
.sidebar-foot { font-size:10.5px; color:#7e8db4; line-height:1.5; border-top:1px solid rgba(255,255,255,.1); padding-top:12px; }
.sidebar-foot button { width:100%; margin-top:10px; background: var(--gold); color: var(--navy); border:none; padding:9px; border-radius:8px; font-weight:800; font-size:12.5px; cursor:pointer; }

.main-content { flex:1; min-width:0; max-width:1600px; padding: 26px 34px 60px; }
.content-head { margin-bottom:16px; }
.content-head h2 { font-size:22px; margin-bottom:2px; }
.content-head p { margin-top:0; max-width:760px; }

/* ---- dashboard grid (Overview) ---- */
.dash-grid { display:grid; grid-template-columns: repeat(12, 1fr); gap:16px; }
.dash-grid .span-12 { grid-column: span 12; }
.dash-grid .span-8 { grid-column: span 8; }
.dash-grid .span-4 { grid-column: span 4; }
.dash-grid .span-6 { grid-column: span 6; }
@media (max-width: 1100px) {
  .dash-grid .span-8, .dash-grid .span-4, .dash-grid .span-6 { grid-column: span 12; }
}

.kpi-grid { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; }
@media (max-width: 1400px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
.kpi-card { background:#fff; border:1px solid var(--line); border-left: 4px solid var(--line); border-radius:10px; padding:13px 15px; }
.kpi-card.strong { border-left-color: var(--green); } .kpi-card.moderate { border-left-color: var(--amber); } .kpi-card.weak { border-left-color: var(--red); }
.kpi-label { font-size:11px; font-weight:700; color: var(--ink-soft); text-transform:uppercase; letter-spacing:.02em; }
.kpi-value { font-size:23px; font-weight:800; color: var(--navy); margin: 3px 0; }
.kpi-bar-track { height:5px; border-radius:3px; background: var(--gray-bg); overflow:hidden; margin: 2px 0 6px; }
.kpi-bar-fill { height:100%; border-radius:3px; }
.kpi-bar-fill.strong { background: var(--green); } .kpi-bar-fill.moderate { background: var(--amber); } .kpi-bar-fill.weak { background: var(--red); }
.kpi-hint { font-size:11px; color: var(--ink-soft); }

.glance-card .glance-label { font-size:11px; font-weight:700; text-transform:uppercase; color: var(--ink-soft); }
.glance-card .glance-value { font-size:16px; font-weight:700; color: var(--navy); margin-top:4px; }
.glance-card p { margin:4px 0 0; }

/* ---- sector leaderboard: multi-column card grid on wide screens ---- */
.sector-grid { display:grid; grid-template-columns: repeat(2, 1fr); gap:10px; }
@media (max-width: 1200px) { .sector-grid { grid-template-columns: 1fr; } }
.sector-card { border:1px solid var(--line); border-radius:10px; padding:12px 14px; background:#fbfcfe; display:grid; grid-template-columns: 28px 1fr; gap:10px; align-items:start; }
.sector-card.top { background: linear-gradient(90deg, #fffaf0, #fbfcfe); border-color:#eddca8; }
.sector-rank { font-weight:800; color: var(--navy); text-align:center; padding-top:1px; }
.sector-card.top .sector-rank { color: var(--gold); }
.sector-label-row { display:flex; justify-content:space-between; gap:8px; }
.sector-label { font-weight:600; font-size:13.5px; }
.sector-score { font-weight:800; color: var(--navy); white-space:nowrap; }
.sector-bar-track { height:5px; background: var(--gray-bg); border-radius:4px; margin-top:6px; overflow:hidden; }
.sector-bar-fill { height:100%; background: linear-gradient(90deg, var(--gold), var(--navy-2)); border-radius:4px; }
.sector-meta-row { display:flex; gap:6px; margin-top:8px; flex-wrap:wrap; }

.chip { display:inline-block; font-size:10px; font-weight:700; padding:3px 9px; border-radius:20px; background: var(--gray-bg); color: var(--ink-soft); white-space:nowrap; }
.chip.favorable, .chip.strong_favorable { background: var(--green-bg); color: var(--green); }
.chip.positive { background: var(--green-bg); color: var(--green); }
.chip.negative { background: var(--red-bg); color: var(--red); }

/* ---- timed windows: card grid instead of a stacked list ---- */
.window-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap:12px; }
.window-card { border:1px solid var(--line); border-radius:10px; padding:13px 15px; background:#fbfcfe; }
.window-card-head { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
.window-dates { font-weight:700; font-size:13.5px; color: var(--navy); }
.window-lords { font-size:11.5px; color: var(--ink-soft); margin-top:2px; }
.evidence-list { list-style:none; margin:8px 0 0; padding:0; }
.evidence-list li { font-size:11.5px; color: var(--ink-soft); padding: 2px 0; }

.sig-columns { display:grid; grid-template-columns: 1fr 1fr; gap:20px; }
@media (max-width: 900px) { .sig-columns { grid-template-columns: 1fr; } }
.sig-row { padding:9px 0; border-bottom:1px solid var(--line); font-size:12.5px; }
.sig-row:last-child { border-bottom:none; }
.sig-weight { font-weight:800; margin-right:8px; }

.narrative-card p { font-size:14px; line-height:1.75; color: var(--ink); }
.narrative-card p:first-child { margin-top:0; }
.narrative-card { max-width:840px; }

.glossary-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap: 14px 22px; margin-top:12px; }
@media (max-width: 1300px) { .glossary-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 800px) { .glossary-grid { grid-template-columns: 1fr; } }
.glossary-term dt { font-weight:700; color: var(--navy); font-size:12.5px; margin-bottom:3px; }
.glossary-term dd { margin:0; font-size:12px; color: var(--ink-soft); line-height:1.5; }

.print-btn { position: fixed; bottom: 22px; right: 22px; background: var(--navy); color:#fff; border:none; padding:12px 18px; border-radius:30px; font-weight:700; font-size:13px; cursor:pointer; box-shadow: 0 4px 14px rgba(20,30,60,.25); z-index:40; }
footer { text-align:center; font-size:12px; color: var(--ink-soft); padding: 24px 0 6px; }
.disclaimer { font-size:11px; color: var(--ink-soft); font-style: italic; margin-top: 14px; }

.mobile-topbar { display:none; }

@media print {
  .sidebar, .print-btn, .mobile-topbar { display:none !important; }
  .app-shell { display:block; }
  .main-content { max-width:none; padding:0; }
  body { background:#fff; }
  .card { box-shadow:none; border:1px solid #ccc; break-inside: avoid; }
}

@media (max-width: 900px) {
  .app-shell { flex-direction:column; }
  .sidebar { position:static; width:auto; height:auto; flex-direction:column; }
  .main-content { padding: 18px 16px 50px; }
  .sig-columns { grid-template-columns: 1fr; }
}
"""


def _app_jsx() -> str:
    # NOTE: plain JS-flavored JSX, transpiled in-browser via a manual
    # Babel.transform call (see render_html()) with runtime:"classic".
    # Deliberately dependency-free beyond React itself -- no router, no
    # state library -- since this whole file has to work by
    # double-clicking it: no npm install, no server.
    return r"""
const { useState } = React;
const REPORT = JSON.parse(document.getElementById('report-data').textContent);
const GLOSSARY = JSON.parse(document.getElementById('glossary-data').textContent);

function fmtPct(v) { return (v === null || v === undefined) ? '—' : v.toFixed(1) + '%'; }
function yesNo(v) { return v ? 'Yes' : 'No'; }
function verdictClass(cat) {
  const c = (cat || '').toUpperCase();
  if (c.includes('HYBRID')) return 'hybrid';
  if (c.includes('JOB')) return 'job';
  return 'business';
}
function verdictLabel(cat) {
  const map = {
    HYBRID_LEANING_JOB: 'Hybrid, Leaning Employment',
    HYBRID_LEANING_BUSINESS: 'Hybrid, Leaning Business',
    STRONG_BUSINESS: 'Strong Business Case',
    STRONG_JOB: 'Strong Employment Case',
  };
  return map[cat] || (cat || '—').replace(/_/g, ' ');
}

function KpiGrid() {
  return (
    <div className="kpi-grid">
      {REPORT.kpis.map(k => (
        <div className={"kpi-card " + k.tier} key={k.key}>
          <div className="kpi-label">{k.label}</div>
          <div className="kpi-value">{fmtPct(k.value)}</div>
          {k.value !== null && (
            <div className="kpi-bar-track"><div className={"kpi-bar-fill " + k.tier} style={{width: Math.max(0, Math.min(100, k.value)) + '%'}}></div></div>
          )}
          <div className="kpi-hint">{k.hint}</div>
        </div>
      ))}
    </div>
  );
}

function AtAGlanceCards() {
  const w = REPORT.top_window;
  return (
    <div className="dash-grid" style={{marginTop:12}}>
      <div className="card glance-card span-4">
        <div className="glance-label">Top-Fit Sector</div>
        <div className="glance-value">{REPORT.top_sector ? `${REPORT.top_sector.label} (${fmtPct(REPORT.top_sector.score)})` : '—'}</div>
      </div>
      <div className="card glance-card span-4">
        <div className="glance-label">Nearest Favorable Window</div>
        <div className="glance-value">{w ? `${w.start_date} → ${w.end_date}` : '—'}</div>
        {w && <p style={{fontSize:12, marginTop:2}}>{w.md_lord}/{w.ad_lord}</p>}
      </div>
      <div className="card glance-card span-4">
        <div className="glance-label">Biggest Risk Flag</div>
        <p style={{fontSize:12.5, fontWeight:600, color:'var(--ink)', marginTop:4}}>{REPORT.top_risk ? REPORT.top_risk.slice(0, 130) + (REPORT.top_risk.length > 130 ? '…' : '') : 'None flagged'}</p>
      </div>
    </div>
  );
}

function Recommendation({ audience }) {
  const v = REPORT.verdict;
  return (
    <div className="card">
      <h2>{audience === 'astrologer' ? 'Recommendation' : 'In Summary'}</h2>
      {audience === 'astrologer' ? (
        <>
          <p style={{fontSize:14, color:'var(--ink)'}}>Verdict: <strong>{verdictLabel(v.final_category)}</strong> (action level: {v.action_level || '—'}) &mdash; business_promise ({fmtPct(v.business_promise)}) vs job_promise ({fmtPct(v.job_promise)}).</p>
          <p style={{marginBottom:0}}>Actionable business advantage over employment: <strong>{yesNo(v.comparative_advantage)}</strong>
          &nbsp;&middot;&nbsp; Hybrid suggested: <strong>{yesNo(v.hybrid_suggested)}</strong></p>
        </>
      ) : (
        <p style={{fontSize:14.5, color:'var(--ink)', marginTop:0}}>
          {v.final_category && v.final_category.includes('JOB')
            ? 'Your chart shows some commercial strength, but the numbers lean toward staying employed rather than starting a business right now -- worth validating carefully before committing to a full transition.'
            : 'Your chart shows meaningful support for an independent business path -- validate the specific sector and timing before committing capital.'}
        </p>
      )}
    </div>
  );
}

function Overview({ audience }) {
  return (
    <div className="dash-grid">
      <div className="span-12"><KpiGrid /></div>
      <div className="span-12"><AtAGlanceCards /></div>
      <div className="span-12"><Recommendation audience={audience} /></div>
    </div>
  );
}

function SectorLeaderboard() {
  const [showAll, setShowAll] = useState(false);
  const sectors = REPORT.sectors || [];
  const shown = showAll ? sectors : sectors.slice(0, 12);
  const maxScore = sectors.length ? sectors[0].score : 100;
  return (
    <div className="card">
      <p style={{marginTop:0}}>Ranked by matching classical planetary significators against each field's traditional associations. A fit score, not a business-viability guarantee.</p>
      <div className="sector-grid">
        {shown.map(s => (
          <div className={"sector-card" + (s.rank === 1 ? ' top' : '')} key={s.sector || s.rank}>
            <div className="sector-rank">{s.rank}</div>
            <div>
              <div className="sector-label-row">
                <span className="sector-label">{s.label}</span>
                <span className="sector-score">{fmtPct(s.score)}</span>
              </div>
              <div className="sector-bar-track"><div className="sector-bar-fill" style={{width: (maxScore ? (s.score / maxScore * 100) : 0) + '%'}}></div></div>
              <div className="sector-meta-row">
                <span className="chip">{(s.match_confidence || '').replace(/_/g, ' ')}</span>
                {s.capital_intensity && <span className="chip">{s.capital_intensity} capital</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
      {sectors.length > 12 && (
        <button className="vs-btn" style={{marginTop:14, display:'inline-block', width:'auto', padding:'8px 16px', background:'var(--gray-bg)', color:'var(--navy)'}} onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Show top 12 only' : `Show all ${sectors.length} sectors`}
        </button>
      )}
    </div>
  );
}

function TimedWindows() {
  const windows = REPORT.timed_windows || [];
  return (
    <div className="card">
      <p style={{marginTop:0}}>Dasha/bhukti (planetary period) windows ranked by business-supportiveness.</p>
      <div className="window-grid">
        {windows.map((w, i) => (
          <div className="window-card" key={i}>
            <div className="window-card-head">
              <div>
                <div className="window-dates">{w.start_date} &rarr; {w.end_date}</div>
                <div className="window-lords">{w.md_lord} / {w.ad_lord}</div>
              </div>
              <span className={"chip " + (w.label || '').toLowerCase()}>{(w.label || '').replace(/_/g, ' ')}</span>
            </div>
            {w.evidence && w.evidence.length > 0 && (
              <ul className="evidence-list">{w.evidence.map((e, j) => <li key={j}>{e}</li>)}</ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Yogas() {
  const yogas = REPORT.yogas || [];
  if (!yogas.length) return <div className="card"><p style={{margin:0}}>No named yogas detected on this chart.</p></div>;
  return (
    <div className="dash-grid">
      {yogas.map((y, i) => (
        <div className="card span-6" key={i}>
          <div style={{fontWeight:700, fontSize:13.5, color:'var(--navy)'}}>{y.yoga_name} {y.sanskrit_name && y.sanskrit_name !== y.yoga_name ? `(${y.sanskrit_name})` : ''} <span className="chip">{y.confidence_tier}</span></div>
          <p style={{marginTop:6, marginBottom:0}}>{y.effect}</p>
        </div>
      ))}
    </div>
  );
}

function Significators() {
  const s = REPORT.significators || { positive: [], negative: [] };
  return (
    <div className="card sig-columns">
      <div>
        <h3 style={{marginTop:0}}>Positive Signals</h3>
        {s.positive.length ? s.positive.map((e, i) => (
          <div className="sig-row" key={i}><span className="sig-weight chip positive">+{e.weight}</span>{e.note}</div>
        )) : <p>No positive signals found.</p>}
      </div>
      <div>
        <h3 style={{marginTop:0}}>Risk Signals</h3>
        {s.negative.length ? s.negative.map((e, i) => (
          <div className="sig-row" key={i}><span className="sig-weight chip negative">-{e.weight}</span>{e.note}</div>
        )) : <p>No risk signals found.</p>}
      </div>
    </div>
  );
}

function FinancialReadiness() {
  const f = REPORT.financial_readiness || {};
  return (
    <div className="card">
      <p style={{marginTop:0}}><strong style={{color:'var(--ink)'}}>Certification status:</strong> {f.certified ? 'CERTIFIED' : 'NOT CERTIFIED'} &middot; {f.status || '—'}</p>
      <p><strong style={{color:'var(--ink)'}}>Missing evidence fields:</strong> {(f.missing_fields && f.missing_fields.length) ? f.missing_fields.join(', ') : 'None recorded'}</p>
      <p style={{marginBottom:0}}>{f.note}</p>
    </div>
  );
}

function Confidence() {
  const c = REPORT.confidence || {};
  return (
    <div className="card">
      <p style={{marginTop:0}}><strong style={{color:'var(--ink)'}}>Confidence:</strong> {c.label || '—'} &middot; <strong style={{color:'var(--ink)'}}>Leaning:</strong> {c.overall_leaning || '—'}</p>
      <p style={{marginBottom:0}}>Method agreement: {c.method_agreement !== null && c.method_agreement !== undefined ? (c.method_agreement * 100).toFixed(1) + '%' : '—'}</p>
    </div>
  );
}

function Narrative({ audience }) {
  const n = REPORT.narrative;
  if (!n) return null;
  const paras = audience === 'astrologer' ? n.astrologer_paragraphs : n.client_paragraphs;
  return (
    <div className="card narrative-card">
      {(paras || []).map((p, i) => <p key={i}>{p}</p>)}
      {n.disclaimer && <p className="disclaimer" style={{marginTop:14}}>{n.disclaimer}</p>}
    </div>
  );
}

function Glossary() {
  return (
    <div className="card">
      <p style={{marginTop:0}}>Classical Vedic-astrology terms used throughout, defined once here.</p>
      <dl className="glossary-grid">
        {GLOSSARY.map(([term, def], i) => (
          <div className="glossary-term" key={i}><dt>{term}</dt><dd>{def}</dd></div>
        ))}
      </dl>
    </div>
  );
}

const CLIENT_SECTIONS = [
  { id: 'overview', label: 'Overview' },
  { id: 'narrative', label: 'Your Reading' },
  { id: 'sectors', label: 'Best-Fit Sectors' },
  { id: 'windows', label: 'Favorable Periods' },
];
const ASTRO_SECTIONS = [
  { id: 'overview', label: 'Overview' },
  { id: 'narrative', label: 'Astrological Reading' },
  { id: 'sectors', label: 'Sectors' },
  { id: 'windows', label: 'Timed Windows' },
  { id: 'yogas', label: 'Yogas' },
  { id: 'significators', label: 'Significators' },
  { id: 'financial', label: 'Financial Readiness' },
  { id: 'confidence', label: 'Confidence' },
  { id: 'appendix', label: 'Glossary' },
];
const SECTION_META = {
  overview: { title: 'Overview', intro: 'Every headline number and finding from this chart, on one screen.' },
  narrative: { title: 'Astrological Reading', intro: 'A long-form narrative phrasing the deterministic evidence in this report -- not a new astrological claim.' },
  sectors: { title: 'Sectors That Fit Best', intro: null },
  windows: { title: 'Timed Windows', intro: null },
  yogas: { title: 'Detected Yogas', intro: 'Named planetary combinations classical texts link to specific outcomes.' },
  significators: { title: 'Business-Strength Significators', intro: 'Every piece of astrological evidence this chart’s promise scores are built from.' },
  financial: { title: 'Financial Readiness Evidence', intro: 'External, independently-reviewable evidence -- separate from the astrological read.' },
  confidence: { title: 'Method-Agreement Confidence', intro: 'How much independent methods (D1/D10/D9/Jaimini/KP/Dasha) agree on the overall leaning.' },
  appendix: { title: 'How to Read This Report', intro: null },
};

function Sidebar({ view, setView, sections, activeId, setActiveId }) {
  const v = REPORT.verdict;
  return (
    <aside className="sidebar">
      <div>
        <div className="sidebar-kicker">JyotishAI</div>
        <div className="sidebar-name">{REPORT.name}</div>
        <div className="sidebar-meta">Generated {REPORT.generated} &middot; Rule pack {REPORT.rule_pack_version}</div>
      </div>
      <div className="sidebar-verdict">
        <div className="sidebar-verdict-label">Final Verdict</div>
        <div className={"sidebar-verdict-value " + verdictClass(v.final_category)}>{verdictLabel(v.final_category)}</div>
        <div className="sidebar-verdict-meta">Business {fmtPct(v.business_promise)} &middot; Job {fmtPct(v.job_promise)}</div>
      </div>
      <nav className="viewswitch">
        <button className={"vs-btn" + (view === 'client' ? ' active' : '')} onClick={() => setView('client')}>Chart Profile</button>
        <button className={"vs-btn" + (view === 'astrologer' ? ' active' : '')} onClick={() => setView('astrologer')}>Astrologer View</button>
      </nav>
      <nav className="sidebar-nav">
        {sections.map(s => (
          <button key={s.id} className={activeId === s.id ? 'active' : ''} onClick={() => setActiveId(s.id)}>
            <span className="nav-dot"></span>{s.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">
        Traditional Jyotish heuristics -- a decision-support reading for further reflection, not financial, legal, or medical advice.
        <button onClick={() => window.print()}>Print / Save as PDF</button>
      </div>
    </aside>
  );
}

function App() {
  const [view, setView] = useState('client');
  const [activeId, setActiveId] = useState('overview');
  const hasNarrative = !!REPORT.narrative;
  const rawSections = view === 'client' ? CLIENT_SECTIONS : ASTRO_SECTIONS;
  // 'narrative' is only ever a real, non-empty section when this chart
  // actually got LLM consent + a successful narrative call
  // (_generate_dual_audience_narratives() in generate_business_report.py) --
  // hiding the nav entry entirely when it's absent, rather than showing an
  // empty tab, keeps this section honest about what was actually generated.
  const sections = rawSections.filter(s => s.id !== 'narrative' || hasNarrative);
  const validIds = sections.map(s => s.id);
  const id = validIds.includes(activeId) ? activeId : 'overview';
  const meta = SECTION_META[id];

  const switchView = (v) => { setView(v); setActiveId('overview'); };

  return (
    <div className="app-shell">
      <Sidebar view={view} setView={switchView} sections={sections} activeId={id} setActiveId={setActiveId} />
      <main className="main-content">
        <div className="content-head">
          <h2>{meta.title}</h2>
          {meta.intro && <p>{meta.intro}</p>}
        </div>
        {id === 'overview' && <Overview audience={view} />}
        {id === 'narrative' && <Narrative audience={view} />}
        {id === 'sectors' && <SectorLeaderboard />}
        {id === 'windows' && <TimedWindows />}
        {view === 'astrologer' && id === 'yogas' && <Yogas />}
        {view === 'astrologer' && id === 'significators' && <Significators />}
        {view === 'astrologer' && id === 'financial' && <FinancialReadiness />}
        {view === 'astrologer' && id === 'confidence' && <Confidence />}
        {id === 'appendix' && <Glossary />}
        <footer>JyotishAI &middot; Business Astrology Report</footer>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a standalone React HTML report from a business_debug.json")
    ap.add_argument("chart", help="Path to business_debug.json")
    ap.add_argument("--out", default=None, help="Output HTML file path")
    ap.add_argument("--name", default=None, help="Override subject name")
    args = ap.parse_args()

    with open(args.chart, "r", encoding="utf-8") as fh:
        prediction = json.load(fh)

    report_data = _build_report_data(prediction, name_override=args.name)
    html_out = render_html(report_data)

    out_path = args.out
    if not out_path:
        safe_name = str(report_data["name"]).lower().replace(" ", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"business_prediction_react_{safe_name}_{ts}.html"

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_out)
    print(out_path)


if __name__ == "__main__":
    main()
