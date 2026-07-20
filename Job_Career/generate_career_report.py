#!/usr/bin/env python3
"""
Career Trajectory Atlas — HTML generator.

Reads the raw dump produced by the career-timeline pipeline
(the same format as `lakshman_Json.txt`) and emits a single,
self-contained editorial HTML report.

Usage
-----
    python3 generate_career_report.py \
        --input  path/to/dump.txt \
        --output path/to/report.html

The dump is expected to contain one CAREER TIMELINE INPUT block
followed by a CAREER TIMELINE OUTPUT block with N top-level JSON
period objects, each starting with `{` on its own line and closing
with `}` on its own line (this is how the pipeline pretty-prints).
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


# ─────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────

def _extract_json_blocks(text: str, header_marker: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if header_marker in l)
    except StopIteration:
        return []
    blocks, buf, depth = [], [], 0
    for l in lines[start:]:
        if l.strip() == "{" and depth == 0:
            buf = [l]
            depth = 1
        elif depth > 0:
            buf.append(l)
            depth += l.count("{") - l.count("}")
            if depth == 0:
                blocks.append("\n".join(buf))
                buf = []
    return blocks


def parse_dump(path: Path) -> tuple[dict, list[dict]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    inputs = _extract_json_blocks(text, "CAREER TIMELINE INPUT")
    outputs = _extract_json_blocks(text, "CAREER TIMELINE OUTPUT")

    ctx: dict = {}
    for b in inputs:
        try:
            obj = json.loads(b)
            if "employment_status" in obj or "dob" in obj:
                ctx.update(obj)
        except json.JSONDecodeError:
            continue

    periods = [json.loads(b) for b in outputs]
    return ctx, periods


# ─────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────

def esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))

def pct(x: float) -> str:
    return f"{x * 100:.0f}%" if isinstance(x, (int, float)) else "—"

def fmt_month(s: str | None) -> str:
    if not s:
        return "—"
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(s, fmt).strftime("%b %Y")
        except ValueError:
            pass
    return s

def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

def duration_months(a: str | None, b: str | None) -> int:
    da, db = parse_date(a), parse_date(b)
    if not da or not db:
        return 0
    return max(1, (db.year - da.year) * 12 + (db.month - da.month))


EVENT_META = {
    "PROMOTION":                       ("#1E7B50", "Promotion window"),
    "LEADERSHIP_EXPANSION":            ("#6B5B8E", "Leadership expansion"),
    "PRESSURE_GAIN_WINDOW":            ("#B8720A", "Pressure / gain"),
    "DISRUPTIVE_GLOBAL_TRANSFORMATION":("#B33A2E", "Disruptive transformation"),
    "JOB_CHANGE":                      ("#3C6E9C", "Job change"),
    "PLATEAU":                         ("#6E6E80", "Plateau"),
}

def event_color(ev: str | None) -> str:
    return EVENT_META.get(ev or "", ("#C9A84C", ""))[0]

def event_label(ev: str | None) -> str:
    if not ev:
        return "—"
    meta = EVENT_META.get(ev)
    return meta[1] if meta else ev.replace("_", " ").title()

def sentiment(x: float, hi=0.65, lo=0.4) -> str:
    if x >= hi:
        return "pos"
    if x <= lo:
        return "neg"
    return "mid"


# ─────────────────────────────────────────────────────────────
# HTML fragments
# ─────────────────────────────────────────────────────────────

CSS = r"""
:root{
  --bg:#0e1017; --bg-2:#141824; --surface:#1a1f2e; --surface-2:#232a3d;
  --line:#2b3244; --line-soft:#1f2536;
  --ink:#f2ede1; --ink-dim:#b3aa96; --ink-mute:#7c7666;
  --gold:#d4b062; --gold-soft:rgba(212,176,98,.14);
  --green:#4fb87a; --amber:#e3a24a; --red:#e26a5c; --purple:#a58bd4; --blue:#7fb8e6;
  --radius:14px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:'Inter',-apple-system,'Segoe UI',sans-serif;
  background:radial-gradient(ellipse at top,#181d2b 0%,var(--bg) 60%);
  color:var(--ink); line-height:1.65; min-height:100vh;
  -webkit-font-smoothing:antialiased;
}
.serif{font-family:'Fraunces','Cormorant Garamond',Georgia,serif;font-weight:400;letter-spacing:-.01em}
a{color:var(--gold);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1240px;margin:0 auto;padding:32px 40px 96px}

/* ── Sticky nav ─────────────────────────────────────────── */
nav.top{
  position:sticky;top:0;z-index:50;
  background:rgba(14,16,23,.86);backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line);
}
nav.top .inner{
  max-width:1240px;margin:0 auto;padding:14px 40px;
  display:flex;align-items:center;gap:24px;flex-wrap:wrap;
}
nav.top .brand{font-family:'Fraunces',serif;font-size:18px;letter-spacing:.02em;color:var(--gold)}
nav.top .brand small{color:var(--ink-mute);font-family:'Inter',sans-serif;font-weight:400;font-size:11px;letter-spacing:.14em;text-transform:uppercase;margin-left:10px}
nav.top .jumps{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}
nav.top .jumps a{
  font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-dim);
  padding:6px 10px;border-radius:6px;border:1px solid transparent;
}
nav.top .jumps a:hover{color:var(--ink);border-color:var(--line);text-decoration:none}

/* ── Hero ───────────────────────────────────────────────── */
header.hero{padding:64px 0 40px;border-bottom:1px solid var(--line)}
.hero .kicker{font-size:11px;letter-spacing:.24em;color:var(--gold);text-transform:uppercase;margin-bottom:20px}
.hero h1{font-family:'Fraunces',serif;font-weight:400;font-size:clamp(38px,5vw,64px);line-height:1.05;letter-spacing:-.02em}
.hero h1 em{color:var(--gold);font-style:italic}
.hero .lede{color:var(--ink-dim);font-size:17px;max-width:720px;margin-top:22px}
.meta-row{display:flex;flex-wrap:wrap;gap:36px;margin-top:34px;padding-top:26px;border-top:1px dashed var(--line)}
.meta-row .m{display:flex;flex-direction:column}
.meta-row .m .lbl{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--ink-mute)}
.meta-row .m .val{font-family:'Fraunces',serif;font-size:22px;color:var(--ink);margin-top:4px}

/* ── KPI wall ───────────────────────────────────────────── */
.kpi-wall{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin:44px 0 24px}
.kpi{background:var(--surface);padding:22px 24px;display:flex;flex-direction:column;gap:6px;min-height:120px}
.kpi .n{font-family:'Fraunces',serif;font-size:38px;line-height:1;color:var(--gold)}
.kpi .n.neg{color:var(--red)} .kpi .n.pos{color:var(--green)} .kpi .n.mid{color:var(--amber)}
.kpi .k{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink-mute)}
.kpi .sub{font-size:12px;color:var(--ink-dim);margin-top:2px}
@media (max-width:900px){.kpi-wall{grid-template-columns:repeat(2,1fr)}}

/* ── Timeline strip ─────────────────────────────────────── */
.strip{margin:24px 0 60px}
.strip .track{position:relative;height:96px;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:14px}
.strip .bar{position:absolute;top:14px;bottom:14px;border-radius:6px;padding:8px 10px;color:#0e1017;font-size:11px;font-weight:600;overflow:hidden;cursor:pointer;transition:transform .15s}
.strip .bar:hover{transform:translateY(-2px);z-index:5;box-shadow:0 8px 20px rgba(0,0,0,.35)}
.strip .bar .t{font-family:'Fraunces',serif;font-size:13px;font-weight:500;line-height:1.1;display:block}
.strip .bar .d{font-size:9px;opacity:.7;letter-spacing:.06em;text-transform:uppercase;margin-top:3px;display:block}
.strip .axis{display:flex;justify-content:space-between;color:var(--ink-mute);font-size:10px;letter-spacing:.14em;margin-top:8px;padding:0 4px;text-transform:uppercase}
.strip .now{position:absolute;top:0;bottom:0;width:2px;background:var(--gold);z-index:4}
.strip .now::before{content:'NOW';position:absolute;top:-16px;left:50%;transform:translateX(-50%);color:var(--gold);font-size:9px;letter-spacing:.18em}

/* ── Section headers ────────────────────────────────────── */
section.block{margin-top:64px;scroll-margin-top:80px}
.section-h{display:flex;align-items:baseline;gap:16px;margin-bottom:28px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.section-h .num{font-family:'Fraunces',serif;color:var(--gold);font-size:14px;letter-spacing:.1em}
.section-h h2{font-family:'Fraunces',serif;font-weight:400;font-size:32px;letter-spacing:-.01em}
.section-h .tag{margin-left:auto;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink-mute)}

/* ── Period card ────────────────────────────────────────── */
.period{background:linear-gradient(180deg,var(--surface) 0%,var(--bg-2) 100%);
  border:1px solid var(--line);border-radius:var(--radius);
  margin-bottom:40px;overflow:hidden;position:relative}
.period::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--acc,var(--gold))}
.period-head{padding:28px 32px 20px;display:grid;grid-template-columns:1fr auto;gap:20px;border-bottom:1px solid var(--line-soft)}
.period-head .idx{font-family:'Fraunces',serif;color:var(--gold);font-size:12px;letter-spacing:.18em;text-transform:uppercase}
.period-head h3{font-family:'Fraunces',serif;font-weight:400;font-size:26px;margin-top:6px;letter-spacing:-.01em}
.period-head h3 .event{color:var(--acc,var(--gold));font-style:italic}
.period-head .dates{color:var(--ink-dim);font-size:13px;margin-top:8px;letter-spacing:.02em}
.period-head .badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.badge{font-size:10px;letter-spacing:.14em;text-transform:uppercase;padding:4px 10px;border-radius:99px;
  background:var(--surface-2);color:var(--ink-dim);border:1px solid var(--line)}
.badge.pos{color:var(--green);border-color:rgba(79,184,122,.35);background:rgba(79,184,122,.08)}
.badge.mid{color:var(--amber);border-color:rgba(227,162,74,.35);background:rgba(227,162,74,.08)}
.badge.neg{color:var(--red);border-color:rgba(226,106,92,.35);background:rgba(226,106,92,.08)}
.badge.gold{color:var(--gold);border-color:rgba(212,176,98,.35);background:var(--gold-soft)}

.gauge-wrap{display:flex;flex-direction:column;align-items:center;gap:6px}
.gauge{position:relative;width:120px;height:120px}
.gauge svg{transform:rotate(-90deg)}
.gauge .num{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gauge .num b{font-family:'Fraunces',serif;font-size:30px;color:var(--ink);font-weight:400}
.gauge .num s{font-size:9px;letter-spacing:.16em;color:var(--ink-mute);text-transform:uppercase;text-decoration:none;margin-top:2px}
.gauge-wrap .lbl{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink-mute)}

.period-body{padding:26px 32px;display:grid;grid-template-columns:1.35fr .95fr;gap:32px}
@media (max-width:900px){.period-body{grid-template-columns:1fr}.period-head{grid-template-columns:1fr}}

.narr h4{font-family:'Fraunces',serif;font-size:18px;font-weight:400;margin:20px 0 8px;color:var(--gold)}
.narr h4:first-child{margin-top:0}
.narr p{color:var(--ink-dim);margin-bottom:12px;font-size:14.5px}
.narr ul{padding-left:18px;color:var(--ink-dim);font-size:14px}
.narr ul li{margin-bottom:6px}
.narr strong{color:var(--ink)}

.side .panel{background:var(--bg-2);border:1px solid var(--line-soft);border-radius:10px;padding:16px 18px;margin-bottom:14px}
.panel h5{font-family:'Fraunces',serif;font-size:12px;font-weight:400;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.panel h5::before{content:"";display:inline-block;width:16px;height:1px;background:var(--gold);opacity:.6}

/* score bars */
.bars{display:flex;flex-direction:column;gap:9px}
.bar-row{display:grid;grid-template-columns:130px 1fr 42px;align-items:center;gap:10px;font-size:12px}
.bar-row .lbl{color:var(--ink-dim);text-transform:capitalize}
.bar-row .track{height:6px;background:var(--surface-2);border-radius:3px;overflow:hidden}
.bar-row .fill{height:100%;border-radius:3px;background:var(--gold)}
.bar-row .fill.pos{background:var(--green)}
.bar-row .fill.mid{background:var(--amber)}
.bar-row .fill.neg{background:var(--red)}
.bar-row .v{text-align:right;color:var(--ink);font-variant-numeric:tabular-nums;font-size:11px}

/* mandate checklist */
.mandate{display:grid;grid-template-columns:1fr 1fr;gap:8px 16px}
.mandate .m-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--line-soft);font-size:12px}
.mandate .m-row .k{color:var(--ink-dim)}
.mandate .m-row .v{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);font-weight:600}
.mandate .m-row .v.watch{color:var(--red)}
.mandate .m-row .v.mod{color:var(--amber)}

/* risk ledger */
.risk{display:grid;grid-template-columns:repeat(2,1fr);gap:8px 20px;margin-bottom:12px}
.risk .r{display:flex;justify-content:space-between;font-size:12px;padding:4px 0;border-bottom:1px dashed var(--line-soft)}
.risk .r .k{color:var(--ink-dim)}
.risk .r .v{font-variant-numeric:tabular-nums;color:var(--ink)}
.evidence{font-size:11px;color:var(--ink-mute);margin-top:6px}
.evidence table{width:100%;border-collapse:collapse;font-size:11px}
.evidence th{text-align:left;padding:6px 4px;color:var(--ink-mute);font-weight:400;letter-spacing:.1em;text-transform:uppercase;font-size:10px;border-bottom:1px solid var(--line-soft)}
.evidence td{padding:5px 4px;color:var(--ink-dim);border-bottom:1px solid var(--line-soft)}

/* chip list */
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:var(--surface-2);border:1px solid var(--line);padding:5px 10px;border-radius:6px;font-size:11px;color:var(--ink-dim);letter-spacing:.02em}
.chip.gold{color:var(--gold);border-color:rgba(212,176,98,.3);background:var(--gold-soft)}

/* PD ladder */
.pd-ladder{margin-top:22px;border-top:1px solid var(--line-soft);padding-top:22px}
.pd-ladder h4{font-family:'Fraunces',serif;font-size:16px;color:var(--gold);font-weight:400;margin-bottom:16px;letter-spacing:.02em}
.pd{background:var(--bg-2);border-left:2px solid var(--acc,var(--gold));border-radius:6px;padding:12px 16px;margin-bottom:10px}
.pd-top{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.pd-top .planets{font-family:'Fraunces',serif;font-size:14px;color:var(--ink)}
.pd-top .dt{color:var(--ink-mute);font-size:11px;letter-spacing:.06em}
.pd-top .sc{margin-left:auto;font-size:11px;color:var(--ink-dim)}
.pd-top .sc b{color:var(--ink);font-variant-numeric:tabular-nums}
.aff-severe{color:var(--red)} .aff-moderate{color:var(--amber)} .aff-mild{color:var(--ink-dim)} .aff-none{color:var(--green)}
.sook{margin-top:8px;display:flex;height:14px;border-radius:3px;overflow:hidden;border:1px solid var(--line-soft)}
.sook span{display:block;color:#0e1017;font-size:9px;font-weight:600;text-align:center;padding-top:1px;overflow:hidden;white-space:nowrap}

/* Confidence pill */
.conf{display:inline-flex;align-items:center;gap:10px;padding:6px 14px;border-radius:99px;background:var(--surface-2);border:1px solid var(--line);font-size:12px}
.conf b{color:var(--gold);font-family:'Fraunces',serif;font-size:14px}

footer{margin-top:80px;padding-top:32px;border-top:1px solid var(--line);color:var(--ink-mute);font-size:12px;text-align:center;letter-spacing:.05em}
"""

PLANET_COLOR = {
    "Sun": "#e3a24a", "Moon": "#c8d0e0", "Mars": "#e26a5c", "Mercury": "#7fb8e6",
    "Jupiter": "#d4b062", "Venus": "#f0b6d5", "Saturn": "#8a8296",
    "Rahu": "#a58bd4", "Ketu": "#b57960",
}


# ─────────────────────────────────────────────────────────────
# Component renderers
# ─────────────────────────────────────────────────────────────

def gauge_svg(score: float, color: str) -> str:
    r = 52
    circ = 2 * 3.14159 * r
    dash = circ * min(max(score, 0), 1)
    return f"""
    <svg width="120" height="120" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="{r}" fill="none" stroke="var(--surface-2)" stroke-width="8"/>
      <circle cx="60" cy="60" r="{r}" fill="none" stroke="{color}" stroke-width="8"
        stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}"/>
    </svg>"""


def render_hero(ctx: dict, periods: list[dict]) -> str:
    total = len(periods)
    now = ctx.get("current_date") or date.today().isoformat()
    dob = ctx.get("dob", "")
    yrs = ctx.get("years_experience", "—")
    desig = (ctx.get("current_designation") or ctx.get("designation") or "").title()
    industry = (ctx.get("industry_sector") or "").title()
    intent = (ctx.get("career_intent") or "").title()

    top = max(periods, key=lambda p: p.get("career_score", 0))
    return f"""
<header class="hero">
  <div class="kicker">Career Trajectory Atlas · Vimshottari Dasha Analysis</div>
  <h1>A window into the <em>next {total}</em> career periods, mapped against the chart.</h1>
  <p class="lede">Each period below fuses classical Jupiter/Mercury dasha logic with modern
  KP transit weighting, D10/D9 structural checks and macro industry signals into a single career score.
  The strongest window in this run is <strong>{esc(top['md_lord'])}–{esc(top['ad_lord'])}</strong>
  ({fmt_month(top['start_date'])} → {fmt_month(top['end_date'])}) with a career score of
  <strong>{top['career_score']:.2f}</strong>.</p>

  <div class="meta-row">
    <div class="m"><span class="lbl">Report Date</span><span class="val serif">{fmt_month(now)}</span></div>
    <div class="m"><span class="lbl">Date of Birth</span><span class="val serif">{fmt_month(dob)}</span></div>
    <div class="m"><span class="lbl">Experience</span><span class="val serif">{esc(yrs)} yrs</span></div>
    <div class="m"><span class="lbl">Designation</span><span class="val serif">{esc(desig or "—")}</span></div>
    <div class="m"><span class="lbl">Industry</span><span class="val serif">{esc(industry or "—")}</span></div>
    <div class="m"><span class="lbl">Intent</span><span class="val serif">{esc(intent or "—")}</span></div>
  </div>
</header>"""


def render_kpi(periods: list[dict]) -> str:
    scores = [p.get("career_score", 0) for p in periods]
    avg = sum(scores) / len(scores) if scores else 0
    top = max(periods, key=lambda p: p.get("career_score", 0))
    peak_risk = max(
        periods,
        key=lambda p: p.get("career_risk", {}).get("job_loss_score", 0),
    )
    promo_count = sum(1 for p in periods if p.get("event_type") == "PROMOTION")

    return f"""
<div class="kpi-wall">
  <div class="kpi">
    <span class="n {sentiment(avg)}">{avg:.2f}</span>
    <span class="k">Mean Career Score</span>
    <span class="sub">Across {len(periods)} tracked periods</span>
  </div>
  <div class="kpi">
    <span class="n pos">{top['career_score']:.2f}</span>
    <span class="k">Peak Window</span>
    <span class="sub">{esc(top['md_lord'])}–{esc(top['ad_lord'])} · {fmt_month(top['start_date'])}</span>
  </div>
  <div class="kpi">
    <span class="n">{promo_count}</span>
    <span class="k">Promotion Windows</span>
    <span class="sub">Elevation-favourable periods</span>
  </div>
  <div class="kpi">
    <span class="n neg">{peak_risk.get('career_risk',{}).get('job_loss_score',0):.0f}</span>
    <span class="k">Peak Risk Score</span>
    <span class="sub">{esc(peak_risk['md_lord'])}–{esc(peak_risk['ad_lord'])} · {fmt_month(peak_risk['start_date'])}</span>
  </div>
</div>"""


def render_strip(periods: list[dict], ctx: dict) -> str:
    starts = [parse_date(p["start_date"]) for p in periods]
    ends   = [parse_date(p["end_date"])   for p in periods]
    lo = min(d for d in starts if d)
    hi = max(d for d in ends   if d)
    span = (hi - lo).days or 1

    bars = []
    for p, s, e in zip(periods, starts, ends):
        if not s or not e: continue
        left  = (s - lo).days / span * 100
        width = max(1.5, (e - s).days / span * 100)
        col = event_color(p.get("event_type"))
        bars.append(f"""
        <a href="#p-{esc(p['start_date'])}" class="bar" style="left:{left:.2f}%;width:{width:.2f}%;background:{col}">
          <span class="t">{esc(p['md_lord'])}–{esc(p['ad_lord'])}</span>
          <span class="d">{event_label(p.get('event_type'))}</span>
        </a>""")

    now = parse_date(ctx.get("current_date")) or date.today()
    now_pct = max(0, min(100, (now - lo).days / span * 100))
    now_marker = f'<div class="now" style="left:{now_pct:.2f}%"></div>' if lo <= now <= hi else ""

    return f"""
<section class="strip block" id="timeline">
  <div class="section-h"><span class="num">01</span><h2>Timeline Atlas</h2><span class="tag">{fmt_month(lo.isoformat())} → {fmt_month(hi.isoformat())}</span></div>
  <div class="track">{now_marker}{"".join(bars)}</div>
  <div class="axis"><span>{fmt_month(lo.isoformat())}</span><span>Present</span><span>{fmt_month(hi.isoformat())}</span></div>
</section>"""


def render_score_bars(sub: dict, keys: Iterable[tuple[str, str]]) -> str:
    rows = []
    for k, lbl in keys:
        v = sub.get(k)
        if v is None: continue
        if not isinstance(v, (int, float)): continue
        vv = max(0, min(1, v)) if -1 <= v <= 1 else min(1, v/100)
        cls = sentiment(vv)
        rows.append(f"""
        <div class="bar-row">
          <span class="lbl">{esc(lbl)}</span>
          <div class="track"><div class="fill {cls}" style="width:{vv*100:.0f}%"></div></div>
          <span class="v">{v:.2f}</span>
        </div>""")
    return f'<div class="bars">{"".join(rows)}</div>'


def render_mandate(m: dict) -> str:
    if not m: return ""
    fields = [
        ("title_clarity","Title clarity"),
        ("budget_control","Budget control"),
        ("team_control","Team control"),
        ("reporting_line","Reporting line"),
        ("executive_sponsorship","Exec sponsorship"),
        ("success_metrics","Success metrics"),
        ("political_risk","Political risk"),
        ("global_visibility","Global visibility"),
    ]
    rows = []
    for k, lbl in fields:
        v = m.get(k)
        if not v: continue
        cls = ""
        if "HIGH" in v or "WATCH" in v: cls = "watch"
        elif "MODERATE" in v: cls = "mod"
        rows.append(f'<div class="m-row"><span class="k">{esc(lbl)}</span><span class="v {cls}">{esc(v.replace("_"," "))}</span></div>')
    narr = m.get("narrative","")
    narr_html = f'<p style="margin-top:12px;font-size:12.5px;color:var(--ink-dim);line-height:1.55">{esc(narr)}</p>' if narr else ""
    return f'<div class="panel"><h5>Mandate quality — accept only if</h5><div class="mandate">{"".join(rows)}</div>{narr_html}</div>'


def render_risk(r: dict) -> str:
    if not r: return ""
    keys = [
        ("job_loss_score","Job-loss"),
        ("job_change_score","Job-change"),
        ("role_restructuring_score","Restructuring"),
        ("career_plateau_score","Plateau"),
        ("continuity_score","Continuity"),
        ("recovery_score","Recovery"),
        ("d10_stability_score","D10 stability"),
        ("d10_break_score","D10 break"),
    ]
    rows = []
    for k, lbl in keys:
        v = r.get(k)
        if v is None: continue
        rows.append(f'<div class="r"><span class="k">{esc(lbl)}</span><span class="v">{v:.1f}</span></div>')

    ev = r.get("evidence") or []
    ev_rows = "".join(
        f"<tr><td>{esc(e.get('event',''))}</td><td>{esc(e.get('rule',''))}</td>"
        f"<td>{esc(e.get('source',''))}</td><td style='text-align:right'>{e.get('impact',0):.2f}</td></tr>"
        for e in ev[:8]
    )
    ev_html = f"""
    <div class="evidence"><table>
      <thead><tr><th>Event</th><th>Rule</th><th>Source</th><th style='text-align:right'>Impact</th></tr></thead>
      <tbody>{ev_rows}</tbody></table></div>""" if ev_rows else ""

    sev = r.get("severity","")
    band = r.get("confidence_band","")
    label = r.get("final_event_type","")
    return f"""
    <div class="panel">
      <h5>Risk ledger — {esc(sev)} · {esc(band)}</h5>
      <div class="risk">{"".join(rows)}</div>
      <div class="chips"><span class="chip gold">{esc(label)}</span></div>
      {ev_html}
    </div>"""


def render_pd_ladder(pds: list[dict]) -> str:
    if not pds: return ""
    rows = []
    for pd in pds:
        aff = pd.get("affliction","")
        acls = f"aff-{aff}" if aff else "aff-none"
        sooks = pd.get("sookshams") or []
        total = duration_months(pd["start_date"], pd["end_date"]) or 1
        segs = []
        for s in sooks:
            w = duration_months(s["start_date"], s["end_date"])
            pct_w = max(4, w / total * 100)
            col = PLANET_COLOR.get(s.get("sk_lord",""), "#7fb8e6")
            segs.append(f'<span style="width:{pct_w:.2f}%;background:{col}" title="{esc(s.get("sk_lord",""))}: {fmt_month(s["start_date"])} → {fmt_month(s["end_date"])}">{esc(s.get("sk_lord","")[:2])}</span>')
        sook_html = f'<div class="sook">{"".join(segs)}</div>' if segs else ""
        rows.append(f"""
        <div class="pd" style="--acc:{PLANET_COLOR.get(pd.get('pd_lord',''),'#d4b062')}">
          <div class="pd-top">
            <span class="planets">{esc(pd['md_lord'])} · {esc(pd['ad_lord'])} · <b>{esc(pd['pd_lord'])}</b></span>
            <span class="dt">{fmt_month(pd['start_date'])} → {fmt_month(pd['end_date'])}</span>
            <span class="sc">score <b>{pd.get('pd_score',0):.2f}</b> · <span class="{acls}">{esc(aff or 'clean')}</span></span>
          </div>
          {sook_html}
        </div>""")
    return f'<div class="pd-ladder"><h4>Pratyantardasha ladder — {len(pds)} sub-windows</h4>{"".join(rows)}</div>'


def render_period(p: dict, idx: int) -> str:
    ev = p.get("event_type") or p.get("final_event_type")
    col = event_color(ev)
    score = p.get("career_score", 0)
    sub = p.get("sub_scores", {}) or p
    conf = p.get("confidence", {}) or {}
    risk = p.get("career_risk", {}) or p
    mand = p.get("mandate_quality", {}) or {}

    narr = p.get("llm_ad_narrative_html") or ""
    # fallback narrative
    if not narr:
        narr = (
            f"<h4>Period Overview</h4><p>{esc(p.get('md_narrative') or p.get('narrative_hint') or '')}</p>"
            f"<h4>Stage Framing</h4><p>{esc(p.get('stage_domain_framing') or '')}</p>"
        )

    badges = []
    if p.get("is_current"): badges.append('<span class="badge gold">Current window</span>')
    if p.get("is_past"):    badges.append('<span class="badge">Past</span>')
    if p.get("is_primary_opportunity"): badges.append('<span class="badge pos">Primary opportunity</span>')
    if p.get("kp_override_applied"):    badges.append('<span class="badge mid">KP override</span>')
    if p.get("domain_tag"): badges.append(f'<span class="badge">{esc(p["domain_tag"])}</span>')
    for tf in (p.get("transit_flags") or [])[:3]:
        badges.append(f'<span class="badge">{esc(tf.replace("_"," ").title())}</span>')

    # sub-score groups
    activation_keys = [
        ("career_activation","Career activation"),
        ("house_activation","House activation"),
        ("strength_product","Strength product"),
        ("functional_nature","Functional nature"),
        ("sav_support","SAV support"),
        ("jaimini_score","Jaimini"),
    ]
    outcome_keys = [
        ("promotion_score","Promotion"),
        ("job_change_score","Job change"),
        ("income_score","Income"),
        ("risk_score","Risk"),
        ("stability_score","Stability"),
        ("visibility_score","Visibility"),
    ]
    structural_keys = [
        ("d10_title_support","D10 title support"),
        ("d10_global_delivery_support","D10 global delivery"),
        ("d10_invisible_authority_support","D10 invisible authority"),
        ("d10_clean_promotion_support","D10 clean promotion"),
        ("d10_alignment","D10 alignment"),
        ("d10_full_score","D10 full score"),
        ("d10_structural_score","D10 structural"),
        ("d9_sustainability_score","D9 sustainability"),
        ("kp_weighted_score","KP weighted"),
        ("vimsopaka_score","Vimsopaka"),
        ("chara_dasha_score","Chara dasha"),
    ]

    yogas = sub.get("active_yogas") or []
    yogas_html = "".join(f'<span class="chip">{esc(y.replace("_"," "))}</span>' for y in yogas) if yogas else ""
    yogas_panel = f'<div class="panel"><h5>Active yogas</h5><div class="chips">{yogas_html}</div></div>' if yogas_html else ""

    skills = p.get("skill_recommendations") or []
    skills_html = "".join(f'<span class="chip gold">{esc(s)}</span>' for s in skills)
    skills_panel = f'<div class="panel"><h5>Skill playbook</h5><div class="chips">{skills_html}</div></div>' if skills_html else ""

    rem = p.get("remedies") or []
    rem_html = "".join(f"<li>{esc(r)}</li>" for r in rem)
    rem_panel = f'<div class="panel"><h5>Remedies</h5><ul style="padding-left:16px;color:var(--ink-dim);font-size:13px">{rem_html}</ul></div>' if rem_html else ""

    sal = p.get("salary_range") or {}
    sal_panel = ""
    if sal:
        sal_panel = f"""
        <div class="panel"><h5>Compensation band</h5>
          <div style="display:flex;align-items:baseline;gap:16px">
            <span style="font-family:'Fraunces',serif;font-size:32px;color:var(--gold)">+{sal.get('low_pct',0)}–{sal.get('high_pct',0)}%</span>
            <span style="font-size:11px;color:var(--ink-mute)">expected hike range</span>
          </div>
          <p style="font-size:11px;color:var(--ink-mute);margin-top:6px;letter-spacing:.02em">basis · {esc(sal.get('basis',''))}</p>
        </div>"""

    conf_html = ""
    if conf:
        conf_html = f"""
        <div style="margin-top:16px">
          <span class="conf">Confidence <b>{conf.get('score','—')}</b> · {esc(conf.get('label',''))}</span>
        </div>"""
    if conf.get("caveats"):
        conf_html += '<p style="font-size:11.5px;color:var(--ink-mute);margin-top:10px;font-style:italic">' + \
                     "; ".join(esc(c) for c in conf["caveats"]) + "</p>"

    return f"""
<article class="period" id="p-{esc(p['start_date'])}" style="--acc:{col}">
  <div class="period-head">
    <div>
      <div class="idx">Period {idx+1:02d} · {esc(p.get('md_lord'))} Mahadasha · {esc(p.get('ad_lord'))} Antardasha</div>
      <h3>{fmt_month(p['start_date'])} – {fmt_month(p['end_date'])}<br><span class="event">{event_label(ev)}</span></h3>
      <div class="dates">Jaimini role · {esc(p.get('jaimini_role','—')[:110])}</div>
      <div class="badges">{"".join(badges)}</div>
      {conf_html}
    </div>
    <div class="gauge-wrap">
      <div class="gauge">
        {gauge_svg(score, col)}
        <div class="num"><b>{score:.2f}</b><s>Career Score</s></div>
      </div>
      <span class="lbl">Macro {p.get('macro_score','—')}</span>
    </div>
  </div>

  <div class="period-body">
    <div class="narr">{narr}</div>
    <div class="side">
      <div class="panel"><h5>Career activation</h5>{render_score_bars(sub, activation_keys)}</div>
      <div class="panel"><h5>Outcome propensity</h5>{render_score_bars(sub, outcome_keys)}</div>
      <div class="panel"><h5>Structural (D10 / D9 / KP)</h5>{render_score_bars(sub, structural_keys)}</div>
      {sal_panel}
      {render_mandate(mand)}
      {render_risk(risk)}
      {yogas_panel}
      {skills_panel}
      {rem_panel}
    </div>
  </div>

  {render_pd_ladder(p.get('pratyantardashas') or [])}
</article>"""


def render_report(ctx: dict, periods: list[dict]) -> str:
    jumps = "".join(
        f'<a href="#p-{esc(p["start_date"])}">{fmt_month(p["start_date"])[:3]} ’{p["start_date"][2:4]}</a>'
        for p in periods
    )
    body_periods = "\n".join(render_period(p, i) for i, p in enumerate(periods))

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Career Trajectory Atlas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,300..700;1,300..700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head><body>
<nav class="top">
  <div class="inner">
    <div class="brand">Career Atlas <small>Vimshottari · KP · D10 fusion</small></div>
    <div class="jumps">
      <a href="#timeline">Timeline</a>
      <a href="#periods">Periods</a>
      {jumps}
    </div>
  </div>
</nav>

<div class="wrap">
  {render_hero(ctx, periods)}
  {render_kpi(periods)}
  {render_strip(periods, ctx)}

  <section class="block" id="periods">
    <div class="section-h"><span class="num">02</span><h2>Period Dossiers</h2><span class="tag">{len(periods)} windows · deep-dive</span></div>
    {body_periods}
  </section>

  <footer>Generated {date.today().isoformat()} · Career Trajectory Atlas · dark editorial edition</footer>
</div>
</body></html>"""


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  "-i", required=True, help="Raw pipeline dump (e.g. lakshman_Json.txt)")
    ap.add_argument("--output", "-o", required=True, help="Destination HTML path")
    args = ap.parse_args()

    ctx, periods = parse_dump(Path(args.input))
    if not periods:
        raise SystemExit("No CAREER TIMELINE OUTPUT periods found in input.")

    html_out = render_report(ctx, periods)
    Path(args.output).write_text(html_out, encoding="utf-8")
    print(f"✓ wrote {args.output}  ({len(periods)} periods, {len(html_out):,} bytes)")


if __name__ == "__main__":
    main()
