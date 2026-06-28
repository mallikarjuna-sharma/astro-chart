"""
foreign_opportunities.py
========================
Standalone HTML report for the Foreign Opportunity Module.

Keeps the same dark-ocean card visual as the main Career Timeline report
but adds full per-window explanations:

  • Scoring breakdown table  (factor | contribution | why)
  • Planetary story paragraph
  • Geo-affinity explanation
  • Action steps (numbered, actionable)
  • Risk factors
  • Confidence indicator
  • Legend / glossary panel

Public API
----------
    generate_foreign_report(
        foreign_opps: list[dict],
        output_path: str | Path,
        name: str = "Chart",
        dob: str = "",
        lagna: str = "",
    ) -> Path
"""
from __future__ import annotations

import html
import os
from datetime import date
from pathlib import Path
from typing import List, Dict

# ── HTML escape shorthand ─────────────────────────────────────────────────────
def esc(t: object) -> str:
    return html.escape(str(t or ""), quote=True)


# ── Date formatter ────────────────────────────────────────────────────────────
def _fmt_date(raw: str) -> str:
    if not raw or len(raw) < 7:
        return raw or ""
    try:
        y, m = int(raw[:4]), int(raw[5:7])
        _MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        d_part = f" {int(raw[8:10])}" if len(raw) >= 10 else ""
        return f"{_MN[m-1]}{d_part}, {y}"
    except Exception:
        return raw[:7]


# ═══════════════════════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════════════════════
_FOP_CSS = """
:root {
  --bg:        #0f172a;
  --bg2:       #1e293b;
  --bg3:       #0d1b2a;
  --card:      #1a2744;
  --card2:     #162035;
  --accent:    #C9A84C;
  --accent2:   #e8c76a;
  --ocean:     #0ea5e9;
  --ocean2:    #38bdf8;
  --green:     #22c55e;
  --amber:     #f59e0b;
  --red:       #ef4444;
  --purple:    #a78bfa;
  --border:    #2d3f5f;
  --border2:   #1e3050;
  --text:      #e2e8f0;
  --text2:     #94a3b8;
  --text3:     #64748b;
  --radius:    14px;
  --radius-sm: 8px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  min-height: 100vh;
}

/* ── HEADER ─────────────────────────────────────────────────────────────── */
.fop-header {
  background: linear-gradient(135deg, #0a1628 0%, #0d2040 50%, #071520 100%);
  border-bottom: 2px solid var(--accent);
  padding: 28px 40px 20px;
}
.fop-brand {
  font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 6px;
}
.fop-title {
  font-size: 26px; font-weight: 700; color: #fff; letter-spacing: -0.02em;
}
.fop-subtitle { color: var(--text2); font-size: 13px; margin-top: 4px; }
.fop-meta-row {
  display: flex; gap: 28px; margin-top: 18px; flex-wrap: wrap;
}
.fop-meta-item {
  background: rgba(255,255,255,.05); border: 1px solid var(--border2);
  border-radius: 8px; padding: 8px 16px; min-width: 120px;
}
.fop-meta-label {
  font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--text3); margin-bottom: 2px;
}
.fop-meta-val {
  font-size: 15px; font-weight: 600; color: var(--accent2);
}

/* ── SUMMARY STRIP ──────────────────────────────────────────────────────── */
.fop-summary-strip {
  background: var(--bg2); border-bottom: 1px solid var(--border);
  padding: 14px 40px; display: flex; gap: 32px; align-items: center;
  flex-wrap: wrap;
}
.fop-summary-pill {
  display: inline-flex; align-items: center; gap: 7px;
  background: rgba(255,255,255,.04); border: 1px solid var(--border);
  border-radius: 20px; padding: 4px 14px; font-size: 12px; color: var(--text2);
}
.fop-summary-pill .dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-strong  { background: var(--green); }
.dot-mod     { background: var(--amber); }
.dot-mild    { background: var(--purple); }
.dot-peak    { background: var(--accent); }

/* ── CONTENT WRAPPER ─────────────────────────────────────────────────────── */
.fop-content { max-width: 960px; margin: 0 auto; padding: 36px 24px; }

/* ── HOW TO READ ─────────────────────────────────────────────────────────── */
.how-to-read {
  background: var(--card2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 24px; margin-bottom: 32px;
}
.how-to-read h3 {
  font-size: 13px; font-weight: 600; color: var(--ocean2);
  letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 12px;
}
.how-to-read p { font-size: 12.5px; color: var(--text2); line-height: 1.7; }
.how-to-read p + p { margin-top: 8px; }

/* ── WINDOW CARD ─────────────────────────────────────────────────────────── */
.fop-window {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 28px;
  overflow: hidden; transition: box-shadow .2s;
}
.fop-window:hover { box-shadow: 0 4px 32px rgba(14,165,233,.12); }
.fop-window.fop-past  { border-color: #334155; opacity: .88; }
.fop-window.fop-active {
  border-color: var(--green); box-shadow: 0 0 0 1px rgba(34,197,94,.25);
}

/* Card top band */
.fop-window-band {
  height: 4px;
}
.fop-band-strong { background: linear-gradient(90deg, #22c55e, #16a34a); }
.fop-band-mod    { background: linear-gradient(90deg, #f59e0b, #d97706); }
.fop-band-mild   { background: linear-gradient(90deg, #a78bfa, #7c3aed); }

/* Card header row */
.fop-window-header {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  padding: 16px 20px 12px; border-bottom: 1px solid var(--border2);
}
.fop-lords {
  font-size: 18px; font-weight: 700; color: #fff; letter-spacing: -0.01em;
}
.fop-lords .md { color: var(--accent2); }
.fop-lords .ad { color: var(--ocean2); }
.fop-lords .sep { color: var(--text3); margin: 0 4px; }
.fop-dates { font-size: 12px; color: var(--text2); margin-left: auto; }
.fop-tag {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; padding: 3px 10px; border-radius: 20px;
}
.tag-past    { background: rgba(100,116,139,.2); color: var(--text3); }
.tag-active  { background: rgba(34,197,94,.18);  color: var(--green); }
.tag-upcoming{ background: rgba(14,165,233,.18); color: var(--ocean2); }

/* Score bar row */
.fop-score-row {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 20px; background: rgba(0,0,0,.18);
}
.fop-score-bar-wrap {
  flex: 1; background: rgba(255,255,255,.07);
  border-radius: 4px; height: 8px; overflow: hidden;
}
.fop-score-bar-fill { height: 100%; border-radius: 4px; transition: width .5s; }
.fop-score-num {
  font-size: 15px; font-weight: 700; color: #fff; min-width: 42px; text-align: right;
}
.fop-conf-badge {
  font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
  text-transform: uppercase; padding: 3px 10px; border-radius: 20px;
}
.conf-high { background: rgba(34,197,94,.18); color: var(--green); }
.conf-mod  { background: rgba(245,158,11,.18); color: var(--amber); }
.conf-mild { background: rgba(167,139,250,.18); color: var(--purple); }
.fop-dur-badge {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; padding: 3px 10px; border-radius: 20px;
}
.dur-trip     { background: rgba(14,165,233,.18); color: var(--ocean2); }
.dur-assign   { background: rgba(245,158,11,.18); color: var(--amber); }
.dur-relocate { background: rgba(239,68,68,.18);  color: var(--red); }

/* Card body tabs / sections */
.fop-body { padding: 0 20px 20px; }
.fop-section-head {
  font-size: 10px; font-weight: 700; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--text3);
  margin: 18px 0 8px; display: flex; align-items: center; gap: 8px;
}
.fop-section-head::after {
  content: ''; flex: 1; height: 1px; background: var(--border2);
}

/* Story paragraph */
.fop-story {
  font-size: 13px; color: var(--text); line-height: 1.75;
  background: rgba(14,165,233,.05); border-left: 3px solid var(--ocean);
  border-radius: 0 8px 8px 0; padding: 12px 16px;
}

/* Geo block */
.fop-geo-block {
  display: flex; gap: 14px;
  background: rgba(201,168,76,.06); border: 1px solid rgba(201,168,76,.2);
  border-radius: 10px; padding: 12px 16px;
}
.fop-geo-icon { font-size: 24px; flex-shrink: 0; margin-top: 2px; }
.fop-geo-dir  { font-size: 13px; font-weight: 600; color: var(--accent2); margin-bottom: 4px; }
.fop-geo-why  { font-size: 12px; color: var(--text2); line-height: 1.65; }

/* Scoring breakdown table */
.fop-breakdown-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.fop-breakdown-table th {
  text-align: left; font-size: 9.5px; font-weight: 600;
  letter-spacing: 0.12em; text-transform: uppercase; color: var(--text3);
  padding: 6px 8px; border-bottom: 1px solid var(--border2);
}
.fop-breakdown-table td {
  padding: 7px 8px; border-bottom: 1px solid rgba(45,63,95,.5);
  vertical-align: top;
}
.fop-breakdown-table tr:last-child td { border-bottom: none; }
.fop-breakdown-table td.f-label { color: var(--text); font-weight: 500; }
.fop-breakdown-table td.f-score {
  color: var(--green); font-weight: 700; white-space: nowrap;
  min-width: 58px; text-align: right;
}
.fop-breakdown-table td.f-why  {
  color: var(--text2); font-size: 11.5px; line-height: 1.6;
}
.f-mini-bar {
  height: 5px; background: var(--border2);
  border-radius: 3px; overflow: hidden; margin-top: 4px;
}
.f-mini-fill { height: 100%; border-radius: 3px; background: var(--ocean); }
.f-group-chip {
  font-size: 9px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; padding: 1px 7px; border-radius: 10px;
  display: inline-block; white-space: nowrap;
}
.grp-house   { background: rgba(168,85,247,.2);  color: #d8b4fe; }
.grp-lordship{ background: rgba(14,165,233,.18); color: var(--ocean2); }
.grp-affinity{ background: rgba(201,168,76,.18); color: var(--accent2); }
.grp-transit { background: rgba(34,197,94,.18);  color: var(--green); }
.grp-event   { background: rgba(239,68,68,.18);  color: var(--red); }
.grp-natal   { background: rgba(245,158,11,.18); color: var(--amber); }
.grp-bonus   { background: rgba(100,116,139,.2); color: var(--text2); }

/* Action steps */
.fop-actions ol {
  list-style: none; counter-reset: action-counter; padding: 0;
}
.fop-actions li {
  counter-increment: action-counter;
  display: flex; gap: 12px; align-items: flex-start;
  padding: 8px 0; border-bottom: 1px solid var(--border2);
  font-size: 12.5px; color: var(--text); line-height: 1.6;
}
.fop-actions li:last-child { border-bottom: none; }
.fop-actions li::before {
  content: counter(action-counter);
  min-width: 22px; height: 22px;
  background: var(--ocean); color: #fff;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; flex-shrink: 0; margin-top: 1px;
}

/* Risk factors */
.fop-risks ul { list-style: none; padding: 0; }
.fop-risks li {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 7px 0; border-bottom: 1px solid var(--border2);
  font-size: 12.5px; color: var(--text2); line-height: 1.6;
}
.fop-risks li:last-child { border-bottom: none; }
.fop-risks li::before {
  content: '⚠';
  color: var(--amber); flex-shrink: 0; margin-top: 1px;
}

/* Confidence block */
.fop-conf-block {
  background: rgba(0,0,0,.2); border: 1px solid var(--border2);
  border-radius: 10px; padding: 12px 16px; display: flex; gap: 12px;
}
.fop-conf-icon { font-size: 20px; flex-shrink: 0; }
.fop-conf-text { font-size: 12.5px; color: var(--text2); line-height: 1.65; }
.fop-conf-level {
  font-weight: 700; font-size: 13px; margin-bottom: 3px;
}

/* Trigger window */
.fop-trigger-block {
  background: rgba(201,168,76,.08); border: 1px solid rgba(201,168,76,.3);
  border-radius: 10px; padding: 12px 16px;
}
.fop-trigger-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--accent); margin-bottom: 4px;
}
.fop-trigger-dates { font-size: 13px; font-weight: 600; color: var(--accent2); }
.fop-trigger-note  { font-size: 12px; color: var(--text2); margin-top: 4px; }

/* ── GLOSSARY ─────────────────────────────────────────────────────────────── */
.fop-glossary {
  background: var(--card2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 24px; margin-top: 40px;
}
.fop-glossary h2 {
  font-size: 14px; font-weight: 700; color: var(--ocean2);
  letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 18px;
  display: flex; align-items: center; gap: 8px;
}
.fop-gloss-grid {
  display: grid; grid-template-columns: repeat(auto-fill,minmax(280px,1fr));
  gap: 16px;
}
.fop-gloss-item {
  background: rgba(0,0,0,.2); border: 1px solid var(--border2);
  border-radius: 10px; padding: 12px 14px;
}
.fop-gloss-term {
  font-size: 12px; font-weight: 700; color: var(--accent2); margin-bottom: 5px;
}
.fop-gloss-def {
  font-size: 11.5px; color: var(--text2); line-height: 1.65;
}

/* ── SCORE LEGEND ─────────────────────────────────────────────────────────── */
.fop-legend {
  background: var(--card2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 24px; margin-top: 24px;
}
.fop-legend h3 {
  font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--text3); margin-bottom: 14px;
}
.fop-legend-rows { display: flex; flex-direction: column; gap: 8px; }
.fop-legend-row  {
  display: flex; align-items: flex-start; gap: 12px;
  font-size: 12px; color: var(--text2);
}
.fop-legend-color {
  min-width: 12px; height: 12px; border-radius: 3px; margin-top: 2px; flex-shrink: 0;
}
.fop-legend-row strong { color: var(--text); }

/* ── FOOTER ───────────────────────────────────────────────────────────────── */
.fop-footer {
  text-align: center; font-size: 10.5px; color: var(--text3);
  padding: 24px; margin-top: 32px;
  border-top: 1px solid var(--border2);
}

/* ── PRINT ────────────────────────────────────────────────────────────────── */
@media print {
  body { background: #fff; color: #000; }
  .fop-header {
    background: #0a1628 !important;
    -webkit-print-color-adjust: exact; color-adjust: exact;
  }
  .fop-window {
    break-inside: avoid; page-break-inside: avoid;
    box-shadow: none; border: 1px solid #ccc;
  }
  @page { margin: 16mm 14mm; }
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# GLOSSARY DATA
# ═══════════════════════════════════════════════════════════════════════════════
_GLOSSARY = [
    ("MD Lord (Mahadasha Lord)",
     "The planet ruling the major 6-20 year Vimshottari time period. The MD lord sets "
     "the overarching theme of the entire phase — its natural and functional nature "
     "determines whether the era is generally expansive, transformative, or challenging."),
    ("AD Lord (Antardasha Lord)",
     "The planet ruling the sub-period within the MD (roughly 1–3 years each). "
     "The AD lord colours the specific events and timing within the MD theme. Foreign "
     "opportunity scoring is computed at the MD-AD intersection level."),
    ("H12 — 12th House",
     "Primary bhava for foreign lands, exile, loss of homeland, and spiritual retreat. "
     "Its activation by the current dasha lord is the strongest single indicator of "
     "a genuine foreign relocation or extended stay abroad."),
    ("H9 — 9th House",
     "Long-distance journeys, higher fortune, international expansion, and dharma. "
     "H9 activation favours fate-driven, auspicious international opportunities — "
     "often arriving naturally rather than through deliberate pursuit."),
    ("H3 — 3rd House",
     "Short trips, neighbouring countries, and communication-based travel. "
     "H3 activation suggests frequent regional travel or multi-country presence "
     "within a geographically compact assignment."),
    ("H8 — 8th House",
     "Sudden transformation, hidden resources, and crisis-driven change. "
     "Foreign connections via H8 tend to be unexpected — a sudden offer, "
     "a crisis-driven relocation, or gains through a foreign partner's assets."),
    ("Rahu — North Node",
     "Primary karaka (natural signifier) of foreign lands in Vedic astrology. "
     "Running a Rahu dasha is the single strongest indicator of crossing borders "
     "and thriving in foreign environments. Rahu amplifies ambition for the unfamiliar."),
    ("Karaka",
     "Sanskrit for 'significator' — a planet that naturally represents a given domain "
     "of life regardless of its house placement. Rahu is the karaka of foreign lands, "
     "Jupiter of H9 and wisdom, Saturn of discipline and longevity."),
    ("Foreign Score",
     "A composite 0–1 score computed from seven independent astrological factors: "
     "active house weights, natal lordship, planetary affinity, transit support, "
     "event classification, natal compounding, and bonus flags. "
     "≥0.65 = High confidence; 0.45–0.64 = Moderate; 0.35–0.44 = Mild."),
    ("Transit Flags",
     "Per-period projected transit positions of Jupiter, Saturn, and Rahu/Ketu "
     "computed for each AD window's midpoint date. Unlike a snapshot of today's sky, "
     "these flags accurately represent where the planets will actually be during "
     "the period — giving more reliable future-period scoring."),
    ("Geo Affinity",
     "The geographic direction and country types most resonant with the dominant "
     "dasha lord's elemental and directional rulership in Vedic astrology. "
     "This is a general affinity, not a precise prediction — it highlights "
     "where the native's energy will be most naturally received."),
    ("Confidence Level",
     "High: multiple independent astrological layers agree (natal, dasha, transit). "
     "Moderate: 2-3 layers active; opportunity exists but needs proactive effort. "
     "Mild: 1-2 latent factors; the foreign thread needs active cultivation to manifest."),
    ("Duration Type",
     "Short Trip (<3 months), Assignment (3-18 months), Relocation (18+ months), "
     "or Extended Stint (MD-level, multi-year). Determined by the raw score level "
     "and which foreign house is most activated."),
    ("Trigger Window",
     "The narrowest sub-sub-period (Pratyantardasha) within the AD window when "
     "the transiting trigger planet aligns with the natal promise. This is the "
     "best date range for submitting applications, accepting offers, or departing."),
]


# ═══════════════════════════════════════════════════════════════════════════════
# CARD BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def _group_chip(group: str) -> str:
    cls_map = {
        "HOUSE_ACTIVE":     "grp-house",
        "NATAL_LORDSHIP":   "grp-lordship",
        "PLANET_AFFINITY":  "grp-affinity",
        "TRANSIT":          "grp-transit",
        "EVENT_CLASSIFIER": "grp-event",
        "NATAL_COMPOUNDING":"grp-natal",
        "BONUS":            "grp-bonus",
    }
    label_map = {
        "HOUSE_ACTIVE":     "House",
        "NATAL_LORDSHIP":   "Lordship",
        "PLANET_AFFINITY":  "Affinity",
        "TRANSIT":          "Transit",
        "EVENT_CLASSIFIER": "Event",
        "NATAL_COMPOUNDING":"Compounding",
        "BONUS":            "Bonus",
    }
    cls = cls_map.get(group, "grp-bonus")
    lbl = label_map.get(group, group)
    return f'<span class="f-group-chip {cls}">{lbl}</span>'


def _breakdown_table(breakdown: List[Dict]) -> str:
    if not breakdown:
        return "<p style='font-size:12px;color:var(--text3)'>No detailed breakdown available.</p>"
    # Compute bar widths relative to the max contribution in this breakdown (not raw pct field)
    # This prevents any bar overflowing to 100% when pct data is miscalibrated
    _max_cont = max((abs(b.get("contribution", 0)) for b in breakdown), default=0.001)
    rows = ""
    for b in breakdown:
        cont = b.get("contribution", 0)
        # Visual bar: scale contribution relative to max, cap at 100
        bar_w = min(100, round(abs(cont) / _max_cont * 70))  # scale to 70% max so it looks calibrated
        chip = _group_chip(b.get("factor_group", ""))
        rows += f"""
<tr>
  <td class="f-label">
    {chip}<br><span style="font-size:12px">{esc(b.get('label',''))}</span>
  </td>
  <td class="f-score">+{cont:.3f}</td>
  <td class="f-why">
    {esc(b.get('why',''))}
    <div class="f-mini-bar"><div class="f-mini-fill" style="width:{bar_w}%"></div></div>
  </td>
</tr>"""
    return f"""
<table class="fop-breakdown-table">
<thead>
  <tr>
    <th style="width:30%">Factor</th>
    <th style="width:10%;text-align:right">Score</th>
    <th>Explanation</th>
  </tr>
</thead>
<tbody>{rows}</tbody>
</table>"""


def _window_card(opp: Dict, idx: int) -> str:
    sc      = opp.get("foreign_score", 0)
    bar_w   = int(sc * 100)
    bar_col = "#22c55e" if sc >= 0.65 else ("#f59e0b" if sc >= 0.45 else "#a78bfa")
    band_cl = "fop-band-strong" if sc >= 0.65 else ("fop-band-mod" if sc >= 0.45 else "fop-band-mild")

    # Tags
    is_past    = opp.get("is_past", False)
    is_current = opp.get("is_current", False)
    if is_past:
        tag_cls, tag_lbl = "tag-past",     "🕐 Past"
        card_cls = "fop-past"
    elif is_current:
        tag_cls, tag_lbl = "tag-active",   "🔴 Active Now"
        card_cls = "fop-active"
    else:
        tag_cls, tag_lbl = "tag-upcoming", "🔵 Upcoming"
        card_cls = "fop-upcoming"  # was "" — missing class

    # Duration badge
    dur_type = opp.get("duration_type", "SHORT_TRIP")
    dur_cls  = {"SHORT_TRIP":"dur-trip","ASSIGNMENT":"dur-assign"}.get(dur_type, "dur-relocate")
    dur_lbl  = esc(opp.get("duration_label", ""))

    # Confidence — derive from score to avoid mismatch (engine sometimes labels Moderate at 38%)
    if sc >= 0.65:
        conf = "High"
    elif sc >= 0.45:
        conf = "Moderate"
    else:
        conf = "Mild"
    conf_cls = {"High": "conf-high", "Moderate": "conf-mod", "Mild": "conf-mild"}.get(conf, "conf-mild")

    # Planets
    md  = esc(opp.get("md_lord", ""))
    ad  = esc(opp.get("ad_lord", ""))
    sd  = esc(_fmt_date(str(opp.get("start_date",""))[:10]))
    ed  = esc(_fmt_date(str(opp.get("end_date",""))[:10]))

    # Story
    story = esc(opp.get("planetary_story", ""))

    # Geo block
    # geo_affinity can be a comma-separated list — show only the primary (first) region
    _geo_raw = opp.get("geo_affinity", "") or ""
    geo      = esc(_geo_raw.split(",")[0].strip())  # first region only
    geo_why  = esc(opp.get("geo_why", ""))

    # Breakdown table
    breakdown_html = _breakdown_table(opp.get("scoring_breakdown", []))

    # Action steps
    steps = opp.get("action_steps", [])
    steps_html = "".join(f"<li>{esc(s)}</li>" for s in steps)

    # Risk factors
    risks = opp.get("risk_factors", [])
    risks_html = "".join(f"<li>{esc(r)}</li>" for r in risks)

    # Confidence block
    conf_rationale = esc(opp.get("confidence_rationale", ""))

    # Trigger window
    tw = opp.get("trigger_window") or {}
    trigger_html = ""
    if tw.get("trigger_planet") and tw.get("trigger_start"):
        t_start = esc(_fmt_date(tw.get("trigger_start", "")))
        t_end   = esc(_fmt_date(tw.get("trigger_end", "")))
        t_note  = esc(tw.get("trigger_note", ""))
        trigger_html = f"""
<div class="fop-section-head">Best Action Window</div>
<div class="fop-trigger-block">
  <div class="fop-trigger-label">🎯 Peak Sub-Period</div>
  <div class="fop-trigger-dates">{esc(tw['trigger_planet'])} trigger &nbsp;·&nbsp; {t_start} → {t_end}</div>
  {f'<div class="fop-trigger-note">{t_note}</div>' if t_note else ''}
  <div class="fop-trigger-note" style="margin-top:6px;font-size:11.5px;color:var(--text3)">
    This is the narrowest high-precision window within the AD period. Submit applications,
    accept offers, or plan departures to coincide with these dates for best results.
  </div>
</div>"""
    else:
        # Fallback: derive from AD period itself
        trigger_html = f"""
<div class="fop-section-head">Best Action Window</div>
<div class="fop-trigger-block">
  <div class="fop-trigger-label">🎯 Activation Window</div>
  <div class="fop-trigger-dates">{md}–{ad} period &nbsp;·&nbsp; {sd} → {ed}</div>
  <div class="fop-trigger-note">Precise PD trigger data not available for this window.
    Begin preparation 3–4 months before window start; peak activation typically occurs in the
    first half of the AD period.</div>
</div>"""

    return f"""
<div class="fop-window {card_cls}">
  <div class="fop-window-band {band_cl}"></div>

  <!-- Header -->
  <div class="fop-window-header">
    <div class="fop-lords">
      <span class="md">{md}</span>
      <span class="sep">–</span>
      <span class="ad">{ad}</span>
    </div>
    <span class="fop-dates">{sd} → {ed}</span>
    <span class="fop-tag {tag_cls}">{tag_lbl}</span>
  </div>

  <!-- Score bar -->
  <div class="fop-score-row">
    <div class="fop-score-bar-wrap">
      <div class="fop-score-bar-fill" style="width:{bar_w}%;background:{bar_col}"></div>
    </div>
    <span class="fop-score-num">{bar_w}%</span>
    <span class="fop-conf-badge {conf_cls}">{conf}</span>
    <span class="fop-dur-badge {dur_cls}">{dur_lbl}</span>
  </div>

  <!-- Body -->
  <div class="fop-body">

    <!-- 1. Planetary Story -->
    <div class="fop-section-head">Planetary Story</div>
    <div class="fop-story">{story}</div>

    <!-- 2. Geo Affinity -->
    <div class="fop-section-head">Geographic Affinity</div>
    <div class="fop-geo-block">
      <div class="fop-geo-icon">🌍</div>
      <div>
        <div class="fop-geo-dir">{geo}</div>
        <div class="fop-geo-why">{geo_why}</div>
      </div>
    </div>

    <!-- 3. Scoring Breakdown -->
    <div class="fop-section-head">How This Score Was Calculated</div>
    <div style="overflow-x:auto">{breakdown_html}</div>

    <!-- 4. Trigger Window -->
    {trigger_html}

    <!-- 5. Confidence -->
    <div class="fop-section-head">Confidence Assessment</div>
    <div class="fop-conf-block">
      <div class="fop-conf-icon">{'✅' if conf=='High' else ('⚡' if conf=='Moderate' else '🔅')}</div>
      <div class="fop-conf-text">
        <div class="fop-conf-level" style="color:{'var(--green)' if conf=='High' else ('var(--amber)' if conf=='Moderate' else 'var(--purple)')}">{conf} Confidence</div>
        {conf_rationale}
      </div>
    </div>

    <!-- 6. Action Steps -->
    <div class="fop-section-head">Action Steps for This Window</div>
    <div class="fop-actions"><ol>{steps_html}</ol></div>

    <!-- 7. Risk Factors -->
    <div class="fop-section-head">Risk Factors to Watch</div>
    <div class="fop-risks"><ul>{risks_html}</ul></div>

  </div><!-- /body -->
</div>"""


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY + LEGEND BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_summary_strip(opps: List[Dict]) -> str:
    strong   = sum(1 for o in opps if o["foreign_score"] >= 0.65)
    moderate = sum(1 for o in opps if 0.45 <= o["foreign_score"] < 0.65)
    mild     = sum(1 for o in opps if o["foreign_score"] < 0.45)
    best     = max(opps, key=lambda o: o["foreign_score"])
    best_lbl = f"{best['md_lord']}–{best['ad_lord']} ({_fmt_date(str(best.get('start_date',''))[:7])})"
    pills = []
    if strong:
        pills.append(f'<span class="fop-summary-pill"><span class="dot dot-strong"></span>{strong} High-confidence window{"s" if strong>1 else ""}</span>')
    if moderate:
        pills.append(f'<span class="fop-summary-pill"><span class="dot dot-mod"></span>{moderate} Moderate window{"s" if moderate>1 else ""}</span>')
    if mild:
        pills.append(f'<span class="fop-summary-pill"><span class="dot dot-mild"></span>{mild} Mild window{"s" if mild>1 else ""}</span>')
    pills.append(f'<span class="fop-summary-pill"><span class="dot dot-peak"></span>Peak: {esc(best_lbl)} ({int(best["foreign_score"]*100)}%)</span>')
    return f'<div class="fop-summary-strip">{"".join(pills)}</div>'


def _build_glossary() -> str:
    items = ""
    for term, defn in _GLOSSARY:
        items += f"""
<div class="fop-gloss-item">
  <div class="fop-gloss-term">{esc(term)}</div>
  <div class="fop-gloss-def">{esc(defn)}</div>
</div>"""
    return f"""
<div class="fop-glossary">
  <h2>📖 Glossary — How to Read This Report</h2>
  <div class="fop-gloss-grid">{items}</div>
</div>"""


def _build_legend() -> str:
    rows = [
        ("#22c55e", "High confidence (≥65%)", "Multiple independent factors active — natal promise, dasha activation, and transit all agree. Pursue actively."),
        ("#f59e0b", "Moderate confidence (45–64%)", "2–3 factors active. The window is real but requires proactive effort to materialise."),
        ("#a78bfa", "Mild signal (35–44%)", "1–2 latent factors. A foreign thread exists but needs deliberate cultivation."),
        ("#C9A84C", "Trigger Window",   "Narrowest sub-sub-period when the foreign promise peaks. Best date range for key decisions."),
    ]
    rows_html = "".join(
        f'<div class="fop-legend-row">'
        f'<div class="fop-legend-color" style="background:{c}"></div>'
        f'<div><strong>{esc(lbl)}</strong> — {esc(desc)}</div>'
        f'</div>'
        for c, lbl, desc in rows
    )
    return f"""
<div class="fop-legend">
  <h3>Score Legend</h3>
  <div class="fop-legend-rows">{rows_html}</div>
</div>"""


def _build_how_to_read() -> str:
    return """
<div class="how-to-read">
  <h3>How to Read This Report</h3>
  <p>Each card below represents one Antardasha (sub-period, typically 1–3 years) within your
  Vimshottari Dasha sequence that has been identified as carrying significant foreign opportunity
  energy. Cards are ordered chronologically. The <strong>Foreign Score</strong> (0–100%) is a
  composite of seven independent astrological factors — the higher the score, the more the chart's
  natal promise, current dasha lords, and projected transits all align toward a foreign opportunity.</p>
  <p>The <strong>Scoring Breakdown</strong> table inside each card explains exactly which factors
  contributed and why — so you understand not just <em>when</em> but <em>why</em> this window is
  active. The <strong>Action Steps</strong> are concrete, practical tasks calibrated to the duration
  type and the dominant dasha lord. The <strong>Trigger Window</strong> (where shown) is the
  narrowest high-precision date range within the period — use it for final decisions and departures.</p>
  <p><strong>Important:</strong> Jyotish reveals the cosmic weather — your free will determines
  how you sail in it. A High-confidence window that is not acted upon remains just a window.
  A Mild window that is vigorously pursued can still yield substantial results.</p>
</div>"""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_foreign_report(
    foreign_opps: List[Dict],
    output_path: "str | Path",
    name: str = "Chart",
    dob: str = "",
    lagna: str = "",
) -> Path:
    """
    Generate a standalone HTML report for the Foreign Opportunity Module.

    Parameters
    ----------
    foreign_opps  : list of dicts as returned by _score_foreign_period (timeline.py)
    output_path   : full path for the output .html file
    name          : native's name for the report header
    dob           : date-of-birth string
    lagna         : lagna sign string

    Returns
    -------
    Path to the generated HTML file.
    """
    output_path = Path(output_path)
    gen_date    = date.today().strftime("%d %b %Y")

    if not foreign_opps:
        html_out = (
            "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
            f"<title>Foreign Opportunities — {html.escape(name)}</title>"
            f"<style>body{{background:#0f172a;color:#94a3b8;font-family:system-ui;padding:60px;text-align:center}}"
            f"</style></head><body>"
            f"<h1 style='color:#e2e8f0'>No Foreign Opportunity Windows Found</h1>"
            f"<p>The foreign opportunity engine found no periods above the minimum threshold "
            f"in the ± 5-year window from today. This typically means the current Vimshottari "
            f"dasha sequence is not activating H9, H12, or the key foreign planets sufficiently. "
            f"Check again after the next Antardasha change.</p>"
            f"<p style='font-size:11px;margin-top:32px;color:#475569'>Generated {html.escape(gen_date)} · JyotishAI</p>"
            f"</body></html>"
        )
        output_path.write_text(html_out, encoding="utf-8")
        return output_path

    # Summary meta
    total   = len(foreign_opps)
    strong  = sum(1 for o in foreign_opps if o["foreign_score"] >= 0.65)
    mod     = sum(1 for o in foreign_opps if 0.45 <= o["foreign_score"] < 0.65)
    mild    = sum(1 for o in foreign_opps if o["foreign_score"] < 0.45)
    best    = max(foreign_opps, key=lambda o: o["foreign_score"])
    geo_set = {o.get("geo_affinity","") for o in foreign_opps if o.get("geo_affinity")}
    geo_summary = " / ".join(sorted(geo_set)[:3]) if geo_set else "Various"

    # Header meta chips
    meta_html = f"""
<div class="fop-meta-row">
  <div class="fop-meta-item">
    <div class="fop-meta-label">Windows Detected</div>
    <div class="fop-meta-val">{total}</div>
  </div>
  <div class="fop-meta-item">
    <div class="fop-meta-label">High Confidence</div>
    <div class="fop-meta-val">{strong}</div>
  </div>
  <div class="fop-meta-item">
    <div class="fop-meta-label">Peak Score</div>
    <div class="fop-meta-val">{int(best['foreign_score']*100)}%</div>
  </div>
  <div class="fop-meta-item">
    <div class="fop-meta-label">Peak Period</div>
    <div class="fop-meta-val">{html.escape(best.get('md_lord',''))}–{html.escape(best.get('ad_lord',''))}</div>
  </div>
  <div class="fop-meta-item">
    <div class="fop-meta-label">Geo Affinity</div>
    <div class="fop-meta-val" style="font-size:11px">{html.escape(geo_summary)}</div>
  </div>
</div>"""

    # Build all window cards
    cards_html = "\n".join(_window_card(opp, i+1) for i, opp in enumerate(foreign_opps))

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Foreign Opportunities — {html.escape(name)}</title>
<style>{_FOP_CSS}</style>
</head>
<body>

<!-- ── HEADER ──────────────────────────────────────────────────── -->
<div class="fop-header">
  <div class="fop-brand">JyotishAI · Career Module</div>
  <div class="fop-title">🌐 Foreign Opportunity Windows</div>
  <div class="fop-subtitle">
    {html.escape(name)}
    {f' &nbsp;·&nbsp; DOB {html.escape(dob)}' if dob else ''}
    {f' &nbsp;·&nbsp; Lagna {html.escape(lagna)}' if lagna else ''}
    &nbsp;·&nbsp; Generated {html.escape(gen_date)}
  </div>
  {meta_html}
</div>

<!-- ── SUMMARY STRIP ────────────────────────────────────────── -->
{_build_summary_strip(foreign_opps)}

<!-- ── MAIN CONTENT ───────────────────────────────── -->
<div class="fop-content">

  {_build_how_to_read()}

  {cards_html}

  {_build_legend()}
  {_build_glossary()}

  <div class="fop-footer">
    Generated {html.escape(gen_date)} · JyotishAI Foreign Opportunity Engine ·
    {total} window{'s' if total != 1 else ''} analysed ·
    {strong} high / {mod} moderate / {mild} mild
  </div>

</div>
</body>
</html>"""

    output_path.write_text(html_out, encoding="utf-8")
    return output_path


# ── Convenience entry-point for engine_io / main report ───────────────────────────────
def generate_foreign_report_beside(
    foreign_opps: List[Dict],
    main_report_path: "str | Path",
    name: str = "Chart",
    dob: str = "",
    lagna: str = "",
) -> Path:
    """
    Save the foreign report next to the main career-timeline HTML.

    e.g. if main = /out/career_timeline_Lakshman.html
         then sister = /out/foreign_opportunities_Lakshman.html
    """
    main_path = Path(main_report_path)
    stem = main_path.stem.replace("career_timeline", "foreign_opportunities")
    if "foreign_opportunities" not in stem:
        stem = "foreign_opportunities_" + stem
    sister = main_path.parent / (stem + ".html")
    return generate_foreign_report(foreign_opps, sister, name=name, dob=dob, lagna=lagna)
