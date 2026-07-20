"""JyotishAI web report v4 — dual-audience LLM support, global toggle, DOB."""
import html as _html
import os
import json
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .payload import NatalPayloadV2, logger
from .foreign_opportunities import generate_foreign_report_beside
from .astrology_explainer import (
    _career_weather,
    _KP_CAREER_HOUSES,
    _KP_EVENT_HOUSE_RULES,
    _kp_event_verdicts,
    _explain_yoga_tag,
    _explain_active_yogas,
    _domain_hedge,
    compute_dusthana_flags,
)

esc = _html.escape

# Gap fix (2026-07-05, user-reported): the Jaimini AK (Atmakaraka) / AmK
# (Amatyakaraka) career-domain label ("Intellect · Communication" for
# Mercury, etc.) was previously only defined locally inside the Outcome
# Snapshot cell builder further down this file. The per-year LLM roadmap
# narrative prompt (_build_year_llm_context) had no access to this same
# canonical mapping, so the LLM was free to invent its own phrasing for
# "what AK/AmK means" each year — producing labels that appeared to drift
# year to year even though the underlying karaka (which planet is AK/AmK)
# is fixed for the chart's whole lifetime in real Jaimini technique. Hoisted
# to module level so every consumer (chart-level display AND the per-year
# LLM context) uses the exact same fixed string for the exact same planet.
_AK_ROLE_MAP = {
    "Sun":     "Authority · Leadership",
    "Moon":    "Public Relations · Care",
    "Mars":    "Action · Engineering",
    "Mercury": "Intellect · Communication",
    "Jupiter": "Advisory · Teaching",
    "Venus":   "Creative · Finance",
    "Saturn":  "Structure · Discipline",
    "Rahu":    "Innovation · Technology",
    "Ketu":    "Research · Spirituality",
}

# FIX (2026-07-06): `_CSS` (used by generate_web_report()'s <style>{_CSS}</style>)
# was referenced but never defined anywhere in this module — a NameError on
# every field-report render, same corruption pattern as the missing _DI/_DA
# dicts and the truncated generate_career_timeline_report() body. The exact
# original stylesheet is unrecoverable (no other copy of it exists in the
# repo), so this is a clean reconstruction covering every class name actually
# emitted by _gen_card() and generate_web_report() — structural/layout rules
# for the named classes, plus generic `[class*="..."]` fallback rules for the
# many small pill/badge/box variants so nothing renders unstyled.
_CSS = """
* { box-sizing: border-box; }
body {
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: #f4f6f9; color: #1e293b;
}
.container { max-width: 980px; margin: 0 auto; padding: 24px 20px 60px; }

.header { text-align: center; padding: 24px 0 20px; border-bottom: 2px solid #e2e8f0; margin-bottom: 20px; }
.brand { font-size: 12px; letter-spacing: 1.5px; text-transform: uppercase; color: #6366f1; font-weight: 700; }
.title { font-size: 28px; margin: 6px 0; color: #0f172a; }
.meta { display: flex; flex-wrap: wrap; gap: 14px; justify-content: center; font-size: 12.5px; color: #475569; }
.meta span { background: #eef2ff; padding: 3px 10px; border-radius: 12px; }

.section-label {
    font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px;
    color: #475569; margin: 26px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #e2e8f0;
}

/* Cluster banner */
.cluster-banner { display: flex; flex-direction: column; gap: 10px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
.cluster-banner-left { display: flex; align-items: center; gap: 10px; }
.cluster-banner-icon { font-size: 22px; }
.cluster-banner-title { font-weight: 700; color: #92400e; }
.cluster-banner-sub { font-size: 12.5px; color: #78350f; margin-top: 2px; }
.cluster-domain-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.cluster-domain-pill { background: #fff; border: 1px solid #fde68a; border-radius: 8px; padding: 6px 10px; font-size: 11.5px; }
.cluster-domain-name { font-weight: 600; color: #92400e; margin-right: 6px; }
.cluster-domain-count { color: #a16207; }

/* Corporate/entrepreneur gauge */
.corp-gauge-wrap { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
.corp-gauge-label { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.corp-gauge-bar-wrap { display: flex; align-items: center; gap: 8px; position: relative; }
.corp-gauge-bar { flex: 1; height: 10px; border-radius: 5px; background: linear-gradient(90deg,#3b82f6,#f59e0b); position: relative; overflow: hidden; }
.corp-gauge-bar-inner { position: absolute; right: 0; top: 0; bottom: 0; background: rgba(255,255,255,0.55); }
.corp-gauge-pct { font-size: 11px; color: #475569; white-space: nowrap; }
.corp-gauge-ends { display: flex; justify-content: space-between; font-size: 10.5px; color: #64748b; margin-top: 4px; }
.corp-style-note { font-size: 12px; color: #475569; margin-top: 8px; }

/* Cards */
.card-list { display: flex; flex-direction: column; gap: 14px; }
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.card-title { font-size: 16px; font-weight: 700; color: #0f172a; }
.card-body { font-size: 13px; color: #334155; line-height: 1.5; }
.rank { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; background: #eef2ff; color: #4338ca; font-weight: 700; font-size: 12px; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.badge { display: inline-block; padding: 3px 9px; border-radius: 10px; font-size: 11px; background: #f1f5f9; color: #334155; }
.badge-score { background: #dcfce7; color: #166534; font-weight: 700; }
.explanation-title { font-weight: 600; font-size: 12.5px; margin-top: 10px; color: #475569; }
.astro-box { background: #f8fafc; border-left: 3px solid #6366f1; padding: 8px 12px; border-radius: 6px; margin-top: 6px; }
.astro-text { font-size: 12.5px; color: #334155; }

/* Friction alert */
.friction-alert { display: flex; align-items: center; gap: 6px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 6px 10px; margin: 6px 0; font-size: 12px; color: #991b1b; }

/* Karaka / verified factor pills */
.karaka-row, .vfact-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.karaka-pill { background: #ecfeff; border: 1px solid #a5f3fc; color: #155e75; padding: 3px 9px; border-radius: 10px; font-size: 11px; }
.vfact-pill { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; padding: 3px 9px; border-radius: 10px; font-size: 11px; }
.vfact-pill.neg { background: #fef2f2; border-color: #fecaca; color: #991b1b; }

/* Score chain */
.chain-box { margin-top: 10px; font-size: 12.5px; }
.chain-box summary { cursor: pointer; font-weight: 600; color: #475569; }
.chain-steps { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 8px; }
.chain-step { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 10px; text-align: center; min-width: 64px; }
.chain-step.highlight { background: #eef2ff; border-color: #c7d2fe; }
.chain-step.dimmed { opacity: 0.55; }
.chain-step-name { font-size: 10px; color: #64748b; }
.chain-step-val { font-size: 14px; font-weight: 700; color: #1e293b; }
.chain-step-mult { font-size: 9.5px; color: #94a3b8; }
.chain-arrow { color: #cbd5e1; font-size: 14px; }
.chain-note { font-size: 11.5px; color: #b45309; margin-top: 6px; }

/* Generic fallback coverage for the many small pill/badge/box/row variants
   emitted across the insight, method, mobility, SBC, and competency-hierarchy
   detail panels — keeps them legible even though bespoke per-class rules for
   all ~90 variants would be excessive to hand-reconstruct. */
[class*="-pill"] { display: inline-block; padding: 3px 9px; border-radius: 10px; font-size: 11px; background: #f1f5f9; color: #334155; margin: 2px 3px 2px 0; }
[class*="-badge"] { display: inline-block; padding: 3px 9px; border-radius: 10px; font-size: 11px; background: #eef2ff; color: #3730a3; }
[class*="-box"] { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 12px; margin-top: 6px; }
[class*="-row"] { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 4px 0; }
[class*="-bar-fill"] { height: 100%; border-radius: inherit; background: #6366f1; }
[class*="-bar"] { background: #e2e8f0; border-radius: 6px; overflow: hidden; height: 8px; }
[class*="-label"] { font-size: 10.5px; color: #64748b; font-weight: 600; }
[class*="-value"] { font-size: 12.5px; color: #1e293b; }
[class*="-title"] { font-weight: 600; color: #334155; }
[class*="-detail"] { font-size: 12px; color: #475569; }
.pos { color: #166534; }
.neg { color: #991b1b; }
.level { font-size: 11px; color: #64748b; }
"""

# Gap fix (2026-07-05, user-reported): active yogas (e.g. "NakParivartana_Saturn_Ketu",
# "Parivartana_Jupiter_Mercury") were previously surfaced ONLY as bare name tags in a
# badge/pill — no explanatory text of what the yoga means for the person's career was
# ever generated, in the HTML or in the LLM narrative context. This does not add any
# new yoga-detection logic (astro.py's `_detect_yogas` / timeline.py's
# `_detect_natal_yogas` are unchanged) — it only unpacks the already-detected tag
# strings into plain-English explanations.
def _wealth_badge(wp: dict) -> str:
    """Render wealth potential badge HTML."""
    level = wp.get("wealth_potential", "")
    note  = wp.get("wealth_note", "")
    if not level:
        return ""
    icons = {"High": "&#9650;", "Medium": "&#9654;", "Low": "&#9660;"}
    ic = icons.get(level, "")
    return (
        f'<span class="ins-badge ins-wealth-{level}" title="{note}">'
        f'{ic} Wealth: {level}</span>'
    )


def _geo_badge(geo: dict) -> str:
    """Render geo suitability badge HTML."""
    label = geo.get("geo_suitability", "")
    note  = geo.get("geo_note", "")
    if not label:
        return ""
    if "International" in label:
        cls, ic = "ins-geo-int", "&#9992;"
    elif "Hybrid" in label:
        cls, ic = "ins-geo-hyb", "&#8646;"
    else:
        cls, ic = "ins-geo-dom", "&#8962;"
    short = label.split("/")[0].strip()
    return f'<span class="ins-badge {cls}" title="{note}">{ic} {short}</span>'


def _burnout_badge(br: dict) -> str:
    """Render burnout risk badge HTML."""
    risk = br.get("burnout_risk", "")
    note = br.get("burnout_note", "")
    if not risk:
        return ""
    cls_map = {"High": "ins-burn-High", "Medium": "ins-burn-Med", "Low": "ins-burn-Low"}
    ic_map  = {"High": "&#9888;", "Medium": "&#9679;", "Low": "&#9679;"}
    cls = cls_map.get(risk, "ins-burn-Low")
    ic  = ic_map.get(risk, "")
    return f'<span class="ins-badge {cls}" title="{note}">{ic} Burnout: {risk}</span>'


def _gen_insight_detail(field: dict) -> str:
    """Expanded 360° detail row — wealth connections, geo %, burnout flags."""
    parts = []

    # ── Wealth connections + note ──────────────────────────────────────────
    wp    = field.get("wealth_potential") or {}
    conns = wp.get("wealth_connections") or []
    w_note = wp.get("wealth_note", "")
    if conns or w_note:
        conns_html = " &bull; ".join(esc(c) for c in conns[:4])
        parts.append(
            f'<div class="ins-detail-block">'
            f'<div class="ins-detail-label">Wealth Drivers</div>'
            + (f'<div class="ins-detail-value">{conns_html}</div>' if conns_html else "")
            + (f'<div class="ins-detail-note">{esc(w_note)}</div>' if w_note else "")
            + f'</div>'
        )

    # ── Geo foreign/domestic split + note ─────────────────────────────────
    geo   = field.get("geo_suitability") or {}
    fgn   = geo.get("geo_foreign_pct", 0) or 0
    dom   = geo.get("geo_domestic_pct", 0) or 0
    g_note = geo.get("geo_note", "")
    if fgn or dom or g_note:
        bar_html = (
            f'<div style="display:flex;align-items:center;gap:6px;font-size:9.5px;color:#475569">'
            f'<span style="min-width:55px">🌍 {fgn}% intl</span>'
            f'<div class="ins-geo-bar" style="flex:1">'
            f'<div class="ins-geo-bar-fill" style="width:{fgn}%;background:#3b82f6"></div>'
            f'</div>'
            f'<span>🏠 {dom}%</span>'
            f'</div>'
        ) if (fgn or dom) else ""
        parts.append(
            f'<div class="ins-detail-block">'
            f'<div class="ins-detail-label">Geography Split</div>'
            + bar_html
            + (f'<div class="ins-detail-note">{esc(g_note)}</div>' if g_note else "")
            + f'</div>'
        )

    # ── Burnout stress flags + note ────────────────────────────────────────
    br     = field.get("burnout_risk") or {}
    flags  = br.get("stress_flags") or []
    b_note = br.get("burnout_note", "")
    if flags or b_note:
        flags_html = "".join(
            f'<div class="ins-stress-flag">{esc(f)}</div>' for f in flags[:3]
        )
        parts.append(
            f'<div class="ins-detail-block">'
            f'<div class="ins-detail-label">Stress Flags</div>'
            + flags_html
            + (f'<div class="ins-detail-note" style="color:#92400e">{esc(b_note)}</div>' if b_note else "")
            + f'</div>'
        )

    if not parts:
        return ""
    return f'<div class="ins-detail-row">{"".join(parts)}</div>'


def _gen_sbc_detail(field: dict) -> str:
    """Collapsible SBC timing detail: career nakshatras, protections, obstructions."""
    sbc   = field.get("sbc_detail") or {}
    prots = sbc.get("key_protections") or []
    obsts = sbc.get("key_obstructions") or []
    naks  = sbc.get("career_nakshatras") or []
    if not (prots or obsts or naks):
        return ""
    exam      = esc(field.get("sbc_exam_date", "Boards"))
    naks_html = " &bull; ".join(esc(n) for n in naks)
    prots_html = "".join(f'<div class="sbc-prot">{esc(p)}</div>' for p in prots[:4])
    obsts_html = "".join(f'<div class="sbc-obs">{esc(o)}</div>' for o in obsts[:4])
    return (
        f'<details class="sbc-detail-box">'
        f'<summary>SBC Timing Detail — {exam}</summary>'
        + (f'<div class="sbc-naks">Career Nakshatras: {naks_html}</div>' if naks_html else "")
        + prots_html
        + obsts_html
        + f'</details>'
    )



def _gen_method_detail(field: dict) -> str:
    """Collapsible method-by-method breakdown: score, weight, trace texts, components."""
    ml = field.get("method_log") or {}
    if not ml:
        return ""
    METHOD_META = {
        "knrao":     ("KN Rao",     "#4f46e5"),
        "kp":        ("KP",         "#7c3aed"),
        "jaimini":   ("Jaimini",    "#0891b2"),
        "parashara": ("Parashara",  "#059669"),
        "dashamsha": ("D10",        "#be185d"),
        "sudarshana":("Sudarshana", "#0f766e"),
    }
    cells = []
    method_order = ("knrao", "kp", "jaimini", "parashara", "dashamsha", "sudarshana")
    for key in method_order:
        m = ml.get(key) or {}
        if not m:
            continue
        meta_name, color = METHOD_META.get(key, (key.title(), "#64748b"))
        score   = m.get("normalized_score") or m.get("score") or 0
        weight  = m.get("weight", 0)
        name_lbl = m.get("name") or meta_name
        traces  = m.get("trace") or []
        comps   = m.get("components") or {}
        # Component pills
        comp_pills = ""
        if comps:
            for ck, cv in list(comps.items())[:6]:
                if cv is None: continue
                if cv > 0:
                    cls = "md-comp-pos"
                elif cv < 0:
                    cls = "md-comp-neg"
                else:
                    cls = "md-comp-neu"
                comp_pills += f'<span class="md-comp-pill {cls}">{esc(ck.replace("_"," "))} {cv:+.2f}</span>'
        comp_row = f'<div class="md-comp-row">{comp_pills}</div>' if comp_pills else ""
        # Trace text (first 2 lines)
        trace_html = ""
        for t in traces[:2]:
            trace_html += f'<div>{esc(str(t))}</div>'
        cells.append(
            f'<div class="md-method-cell">'
            f'<div class="md-method-name" style="color:{color}">{esc(name_lbl)}</div>'
            f'<div class="md-method-score" style="color:{color}">{score:.2f}</div>'
            f'<div class="md-method-weight">wt: {weight*100:.0f}%</div>'
            f'<div class="md-method-trace">{trace_html}</div>'
            f'{comp_row}'
            f'</div>'
        )
    if not cells:
        return ""
    dynamic_summary = (
        f'<details class="method-detail-box">'
        f'<summary>&#128202; Method Detail &mdash; {len(cells)} Scoring Systems</summary>'
        f'<div class="md-method-grid">{"".join(cells)}</div>'
        f'</details>'
    )
    return dynamic_summary
    return (
        f'<details class="method-detail-box">'
        f'<summary>&#128202; Method Detail — 5 Scoring Systems</summary>'
        f'<div class="md-method-grid">{"".join(cells)}</div>'
        f'</details>'
    )


def _gen_career_registry(field: dict) -> str:
    """Career paths, admission exams, and specialization niche from registry."""
    reg = field.get("registry") or {}
    paths = reg.get("career_paths") or []
    exams = reg.get("admission_exams") or []
    niche = reg.get("niche") or reg.get("specialization") or ""
    track = reg.get("track") or ""
    if not (paths or exams or niche):
        return ""
    paths_html = "".join(f'<span class="cp-path-pill">{esc(p)}</span>' for p in paths[:7])
    exams_html = "".join(f'<span class="cp-exam-pill">{esc(e.replace("_"," "))}</span>' for e in exams[:4])
    niche_html = f'<div class="cp-niche-text">Specialisation: {esc(niche)}</div>' if niche else ""
    track_html = f' &bull; Track: {esc(track)}' if track else ""
    return (
        f'<div class="career-paths-box">'
        f'<div class="cp-label">&#128188; Career Paths{track_html}</div>'
        + (f'<div class="cp-paths">{paths_html}</div>' if paths_html else "")
        + niche_html
        + (f'<div class="cp-exams">{exams_html}</div>' if exams_html else "")
        + f'</div>'
    )


def _gen_global_mobility(field: dict) -> str:
    """Global mobility breakdown — mobility %, positive and negative factors, insight."""
    geo = field.get("geo_suitability") or {}
    mob = geo.get("global_mobility") or {}
    if not mob:
        return ""
    pct    = mob.get("mobility_pct", 0)
    lbl    = mob.get("mobility_label", "")
    pos_f  = mob.get("positive_factors") or []
    neg_f  = mob.get("negative_factors") or []
    insight = mob.get("insight", "")
    if not (pos_f or neg_f or insight):
        return ""
    pos_html = "".join(f'<div class="mob-factor-item pos">{esc(f)}</div>' for f in pos_f[:4])
    neg_html = "".join(f'<div class="mob-factor-item neg">{esc(f)}</div>' for f in neg_f[:4])
    cols_html = ""
    if pos_html:
        cols_html += f'<div class="mob-factor-col"><div class="mob-factor-title pos">Foreign Anchors</div>{pos_html}</div>'
    if neg_html:
        cols_html += f'<div class="mob-factor-col"><div class="mob-factor-title neg">Root Bindings</div>{neg_html}</div>'
    insight_html = f'<div class="mob-insight">{esc(insight)}</div>' if insight else ""
    return (
        f'<div class="mob-box">'
        f'<div class="mob-header">'
        f'<span class="mob-pct-badge">&#127760; {pct}% mobility</span>'
        f'<span class="mob-label">{esc(lbl)}</span>'
        f'</div>'
        + (f'<div class="mob-factors">{cols_html}</div>' if cols_html else "")
        + insight_html
        + f'</div>'
    )


def _gen_score_chain(field: dict) -> str:
    """Collapsible final_chain scoring pipeline visualization."""
    ct = field.get("calc_trace") or {}
    chain = ct.get("final_chain") or {}
    if not chain:
        return ""
    # Key steps to show (skip intermediate mult values)
    STEPS = [
        ("blended",         "Blended"),
        ("after_boost",     "After Boost"),
        ("after_penalty",   "After Penalty"),
        ("after_bvb_multiplier", "After BVB"),
        ("after_mismatch",  "After Mismatch"),
        ("after_qa",        "After QA"),
        ("after_ak_flat",   "After AK Flat"),
        ("final_score",     "Final"),
    ]
    # Build multiplier labels for key transitions
    MULT_LABELS = {
        "after_boost":     lambda c: f'×{(c.get("after_boost",0) / c.get("blended",1)):.2f}' if c.get("blended") else "",
        "after_bvb_multiplier": lambda c: f'×{c.get("bvb_multiplier",1):.3f}',
        "after_mismatch":  lambda c: f'×{c.get("mismatch_mult",1):.2f}',
        "after_qa":        lambda c: f'×{c.get("qa_gate_mult",1):.2f}',
        "after_ak_flat":   lambda c: f'+{c.get("ak_domain_flat",0):.1f}',
    }
    steps_html = ""
    for key, label in STEPS:
        val = chain.get(key)
        if val is None:
            continue
        mult_fn = MULT_LABELS.get(key)
        mult_lbl = mult_fn(chain) if mult_fn else ""
        is_final = (key == "final_score")
        hl = "highlight" if is_final else ("dimmed" if val == chain.get("blended") else "")
        steps_html += (
            f'<div class="chain-step {hl}">'
            f'<div class="chain-step-name">{label}</div>'
            f'<div class="chain-step-val">{val:.1f}</div>'
            + (f'<div class="chain-step-mult">{mult_lbl}</div>' if mult_lbl else '<div class="chain-step-mult"></div>')
            + f'</div>'
        )
        if key != "final_score":
            steps_html += '<span class="chain-arrow">→</span>'
    friction_note = chain.get("friction_note", "")
    note_html = f'<div class="chain-note">{esc(friction_note)}</div>' if friction_note else ""
    return (
        f'<details class="chain-box">'
        f'<summary>&#128200; Score Chain — Full Pipeline</summary>'
        f'<div class="chain-steps">{steps_html}</div>'
        + note_html
        + f'</details>'
    )


# FIX (2026-07-06): _DI (domain -> icon) and _DA (domain -> accent color)
# were referenced by _gen_card() below but never defined anywhere in this
# module — a NameError on every field-report card render. Reconstructed
# here using the domain keys from competency_ontology._DOMAIN_DEFAULT_FAMILY
# (the canonical top-level domain list), with safe .get(..., default)
# fallbacks at every call site so an unlisted domain never crashes.
_DI: Dict[str, str] = {
    "engineering":       "⚙️",
    "science":           "🔬",
    "medicine":          "⚕️",
    "technology":        "💻",
    "commerce":          "📊",
    "humanities":        "📚",
    "law":               "⚖️",
    "arts":              "🎨",
    "media":             "📰",
    "public":            "🏛️",
    "education":         "🎓",
    "agriculture":       "🌾",
    "interdisciplinary": "🔗",
    "general":           "🔹",
}

_DA: Dict[str, str] = {
    "engineering":       "#2563eb",
    "science":           "#0891b2",
    "medicine":          "#dc2626",
    "technology":        "#7c3aed",
    "commerce":          "#059669",
    "humanities":        "#b45309",
    "law":               "#1e40af",
    "arts":              "#db2777",
    "media":             "#ea580c",
    "public":            "#4338ca",
    "education":         "#0d9488",
    "agriculture":       "#65a30d",
    "interdisciplinary": "#64748b",
    "general":           "#64748b",
}


def _gen_card(field: dict, rank: int) -> str:
    """Generates the HTML card for a single career field."""
    label = esc(field.get("field_label", field.get("field_id", "Unknown")))
    domain = field.get("domain", "general").lower()
    score = field.get("final_score", field.get("_total_score", field.get("parashara_score", 0.0)))
    
    # Safely extract LLM text or fallbacks
    parent_reason = esc(field.get("parent_friendly_explanation", "Selected strongly based on chart alignments."))
    astro_reason = esc(field.get("astrological_reason", "Astrological signature supports this domain."))
    
    # Styling lookups
    icon = _DI.get(domain, "🔹")
    domain_color = _DA.get(domain, "#64748b")

    # Pre-compute badge strings (avoids f-string nested brace issues)
    w_badge = _wealth_badge(field.get("wealth_potential") or {})
    g_badge = _geo_badge(field.get("geo_suitability") or {})
    b_badge = _burnout_badge(field.get("burnout_risk") or {})

    # ── Top karakas (Gap-6 fix: top_karakas now forwarded from engine) ────────
    _top_k = field.get("top_karakas") or []
    karakas_html = (
        '<div class="karaka-row">'
        + "".join(f'<span class="karaka-pill">{esc(str(k))}</span>' for k in _top_k)
        + '</div>'
    ) if _top_k else ""

    # ── Structural friction flag (Gap-3 fix) ──────────────────────────────────
    _em        = field.get("explainability_matrix") or {}
    _fric_flag = _em.get("structural_friction_flag", "")
    _spread    = _em.get("paradigm_spread", 0) or 0
    _spread_tag = (
        f' <span style="color:#b45309;font-size:9.5px;font-weight:600">(paradigm spread {_spread:.1f})</span>'
    ) if _spread else ""
    friction_html = (
        f'<div class="friction-alert">'
        f'<span class="friction-icon">⚠</span>'
        f'<span class="friction-text">{esc(_fric_flag)}{_spread_tag}</span>'
        f'</div>'
    ) if _fric_flag else ""

    # ── Verified factors: top positive boosts from scoring ───────────────────
    _vf_raw   = field.get("verified_factors", "") or ""
    _vf_parts = [p.strip() for p in _vf_raw.split("|") if p.strip()]
    _vf_pos   = [p for p in _vf_parts if ":+" in p][:5]
    _vf_neg   = [p for p in _vf_parts if ":-" in p][:2]
    _vf_pills = (
        "".join(f'<span class="vfact-pill">{esc(p)}</span>' for p in _vf_pos)
        + "".join(f'<span class="vfact-pill neg">{esc(p)}</span>' for p in _vf_neg)
    )
    verified_factors_html = (
        f'<div class="vfact-row">'
        f'<span class="vfact-label">Boosts</span>'
        f'{_vf_pills}'
        f'</div>'
    ) if _vf_pills else ""

    # ── Score breakdown row: D10 eval / total / boost% / normalized ─────────
    _boost_pct     = field.get("boost_pct", 0)
    _pre_norm      = field.get("pre_norm_score")
    _norm_note     = field.get("norm_note", "")
    _norm_score    = field.get("final_score", 0)
    # D10 Dashamsha eval: use method_log.dashamsha.normalized_score (the D10 varga method score)
    _ml            = field.get("method_log") or {}
    _ds_method     = _ml.get("dashamsha") or {}
    _ds_norm_score = _ds_method.get("normalized_score")
    # Fallback: method_scores_normalized_0_100.dashamsha, else None
    if _ds_norm_score is None:
        _ms_norm = field.get("method_scores_normalized_0_100") or {}
        _ds_norm_score = _ms_norm.get("dashamsha")
    _ds_raw_score  = _ds_method.get("score")

    _sb_d10   = f'{_ds_norm_score:.1f}' if _ds_norm_score is not None else "—"
    _sb_d10_title = (f"Raw D10 score: {_ds_raw_score:.3f}" if _ds_raw_score is not None else "")
    _sb_total = f'{_pre_norm:.1f}'     if _pre_norm is not None     else "—"
    _sb_boost = f'+{_boost_pct:.0f}%' if _boost_pct                else "0%"
    _sb_norm  = f'{_norm_score:.1f}'

    score_breakdown_html = (
        f'<div class="score-breakdown">'
        f'<div class="sb-cell sb-d10">'
        f'<span class="sb-label">D10 Dashamsha</span>'
        f'<span class="sb-value" title="{esc(_sb_d10_title)}">{_sb_d10}</span>'
        f'</div>'
        f'<div class="sb-cell sb-total">'
        f'<span class="sb-label">Total Score</span>'
        f'<span class="sb-value" title="{esc(_norm_note)}">{_sb_total}</span>'
        f'</div>'
        f'<div class="sb-cell sb-boost">'
        f'<span class="sb-label">Boost</span>'
        f'<span class="sb-value">{_sb_boost}</span>'
        f'</div>'
        f'<div class="sb-cell sb-norm">'
        f'<span class="sb-label">Normalized</span>'
        f'<span class="sb-value">{_sb_norm}</span>'
        f'</div>'
        f'</div>'
    )

    # ── Secondary meta pills: timing / SBC (kept separate from breakdown row) ─
    _timing     = field.get("timing_band", "")
    _sbc        = field.get("sbc_event_score") or field.get("smi")
    score_meta_parts = []
    if _timing:
        score_meta_parts.append(f'<span class="meta-pill meta-timing">⏱ {esc(_timing)}</span>')
    if _sbc is not None:
        score_meta_parts.append(f'<span class="meta-pill meta-sbc">SBC {_sbc:.0f}</span>')
    score_meta_html = (
        f'<div class="score-meta-row">{"".join(score_meta_parts)}</div>'
    ) if score_meta_parts else ""

    # ── GAP 3: Micro-niches ──────────────────────────────────────────────────
    _mn_data   = field.get("micro_niches") or {}
    _niches    = _mn_data.get("micro_niches", [])
    _driver    = _mn_data.get("niche_driver", "")
    _niche_pills = "".join(
        f'<span class="niche-pill">{n}</span>' for n in _niches
    )
    niche_html = (
        f'<div class="niche-row">{_niche_pills}</div>'
        f'<div class="niche-driver">Sub-specialisation driver: {_driver}</div>'
    ) if _niches else ""

    # ── GAP 4: Confidence matrix ──────────────────────────────────────────────
    _cm     = field.get("confidence_matrix") or {}
    _kn_p   = _cm.get("knrao_pct", 0)
    _kp_p   = _cm.get("kp_pct", 0)
    _ji_p   = _cm.get("jaimini_pct", 0)
    _pa_p   = _cm.get("parashara_pct", 0)
    _sbc_p  = _cm.get("sbc_pct", 0)
    _ov_p   = _cm.get("alignment_confidence", 0)
    _is_cluster_card = (field.get("chart_type") or {}).get("is_cluster", False)
    _conf_label = "Distributed Fit" if _is_cluster_card else "Alignment Confidence"

    def _conf_bar(label, pct, color="var(--primary)"):
        return (
            f'<div class="conf-bar-row">'
            f'<span class="conf-bar-label">{label}</span>'
            f'<div class="conf-bar-track">'
            f'<div class="conf-bar-fill" style="width:{pct}%;background:{color}"></div>'
            f'</div>'
            f'<span class="conf-bar-pct">{pct}%</span>'
            f'</div>'
        )

    # Dashamsha D10 normalized score for 5th bar
    _ds_cm_p = 0
    if not _is_cluster_card:
        _ms_norm_map = field.get("method_scores_normalized_0_100") or {}
        _ds_cm_raw   = _ms_norm_map.get("dashamsha")
        if _ds_cm_raw is not None:
            # Already 0-100 scale; cap at 100
            _ds_cm_p = min(round(float(_ds_cm_raw), 1), 100)
        elif _ml:
            # Fallback: derive from method_log.dashamsha.score (0-1 → ×100)
            _ds_raw = (_ml.get("dashamsha") or {}).get("score")
            if _ds_raw is not None:
                _ds_cm_p = round(float(_ds_raw) * 100, 1)

    conf_html = (
        f'<div class="conf-matrix">'
        f'<div class="conf-overall">{_conf_label}: <span>{_ov_p}%</span></div>'
        f'<div class="conf-bars">'
        + _conf_bar("KN Rao (Classical)",    _kn_p,  "#4f46e5")
        + _conf_bar("KP (Micro-Timing)",     _kp_p,  "#7c3aed")
        + _conf_bar("Jaimini (Aptitude)",    _ji_p,  "#0891b2")
        + _conf_bar("Parashara (Strength)",  _pa_p,  "#059669")
        + _conf_bar("Dashamsha D10 (Varga)", _ds_cm_p, "#be185d")
        + _conf_bar(
            f'SBC ({esc(field.get("sbc_exam_date", "Boards"))})',
            _sbc_p, "#d97706"
          )
        + f'</div></div>'
    ) if _cm else ""

    # ── GAP 1: Academic path ──────────────────────────────────────────────────
    # academic_path gives chart-level UG/PG/PhD depth signals (H4/H9/H8 strengths).
    # registry gives field-specific program names (ug_program, pg_program, phd_program).
    # Merge: show program name from registry as the label, depth/strength from academic_path.
    _ap      = field.get("academic_path") or {}
    _reg     = field.get("registry") or {}
    _stages  = _ap.get("path_stages", [])
    _ap_lbl  = _ap.get("depth_label", "")
    # Field-specific program names from registry
    _prog_map = {
        "UG":  _reg.get("ug_program", ""),
        "PG":  _reg.get("pg_program", ""),
        "PhD": _reg.get("phd_program", ""),
    }
    _niche_map = {
        "UG":  _reg.get("ug_niche", ""),
        "PG":  _reg.get("pg_niche", ""),
        "PhD": _reg.get("phd_niche", ""),
    }

    def _stage_box(s):
        rec  = s.get("recommended", False)
        stg  = s.get("stage", "")
        if stg == "UG":
            cls = "acad-req"
        elif stg == "PG":
            cls = "acad-rec" if rec else "acad-off"
        else:  # PhD
            cls = "acad-opt" if rec else "acad-off"
        flag  = " ✓" if rec else ""
        # Use registry program name if available, otherwise generic label
        prog_name = _prog_map.get(stg, "") or s.get("label", "")
        sub_niche = _niche_map.get(stg, "")
        sub_line  = f'<div class="acad-stage-niche">{esc(sub_niche)}</div>' if sub_niche else ""
        return (
            f'<div class="acad-stage-box {cls}">'
            f'<div class="acad-stage-name">{esc(prog_name)}{flag}</div>'
            f'<small>{s.get("strength_label","")}</small>'
            f'{sub_line}'
            f'</div>'
        )
    stages_html = '<span class="acad-arrow">&#10132;</span>'.join(
        _stage_box(s) for s in _stages
    )
    acad_html = (
        f'<div class="acad-path">'
        f'<div class="acad-path-label">&#127891; Academic Execution Path</div>'
        f'<div class="acad-stages"><div class="acad-stage">{stages_html}</div></div>'
        f'<div class="niche-driver" style="margin-top:5px">{esc(_ap_lbl)}</div>'
        f'</div>'
    ) if _stages else ""

    # ── GAP 2: Institutional tier ─────────────────────────────────────────────
    # tier + archetype are chart-level (same native, same Jupiter/Sun aptitude).
    # target_examples are field-specific — built from registry.available_at.
    _it        = field.get("institutional_tier") or {}
    _tier_lbl  = _it.get("tier", "")
    _archetype = _it.get("archetype", "")
    _reg_av    = (_reg or {}).get("available_at") or {}
    if isinstance(_reg_av, str):
        try:
            import ast as _ast; _reg_av = _ast.literal_eval(_reg_av)
        except Exception: _reg_av = {}

    _tier_key = _it.get("tier_key", "")

    # Tier-based key priority — only show institutions appropriate to native's tier
    # Tier 1 Premier/International: IIT > IISER > ISI > BITS (suppress NIT/State/Deemed)
    # Tier 2 Technical:             NIT > BITS > IIIT > Deemed (suppress IIT/State)
    # Tier 2 Professional:          Central > Liberal Arts > Deemed > State (suppress IIT/NIT)
    _TIER_ALLOW = {
        "Tier1_Premier":     {"IIT", "IISER", "ISI", "BITS", "central_universities", "liberal_arts_private"},
        "Tier1_Foreign":     {"IIT", "IISER", "ISI", "BITS", "central_universities"},
        "Tier2_Technical":   {"NIT", "BITS", "IIIT", "deemed_private", "state_universities"},
        "Tier2_Professional":{"central_universities", "liberal_arts_private", "deemed_private", "state_universities", "BITS"},
    }
    _allowed = _TIER_ALLOW.get(_tier_key, set(_TIER_ALLOW["Tier2_Professional"]))

    def _avail_labels(av: dict) -> list:
        """Convert registry available_at → institution strings filtered by native's tier."""
        _PREFIX_KEYS = {"IIT", "NIT", "BITS", "IISER", "ISI"}
        _BOOL_LABEL  = {
            "IIIT":                "IIITs",
            "state_universities":  "State Universities",
            "deemed_private":      "Deemed / Private",
            "central_universities": None,
            "liberal_arts_private": None,
        }
        out = []
        for key, val in av.items():
            if key not in _allowed: continue          # skip institutions outside native's tier
            if val is False or val is None: continue
            if val is True:
                label = _BOOL_LABEL.get(key, key.replace("_", " ").title())
                if label: out.append(label)
            elif isinstance(val, list) and val:
                if val == ["All_IITs"]: out.append("All IITs"); continue
                if val == ["All_NITs"]: out.append("All NITs"); continue
                clean = [v.replace(f"{key}_", "").replace("_", " ") for v in val[:3]]
                if key in _PREFIX_KEYS:
                    out.append(f"{key} {' / '.join(clean)}")
                else:
                    out.append(" / ".join(clean))
        return out[:4]

    _field_examples = _avail_labels(_reg_av) if _reg_av else _it.get("target_examples", [])
    _ex_text = " &bull; ".join(esc(e) for e in _field_examples[:4])
    inst_html = (
        f'<div class="inst-tier">'
        f'<span class="inst-tier-badge">{esc(_tier_lbl)}</span>'
        f'<div class="inst-tier-detail"><strong>{esc(_archetype)}</strong>'
        f'<br><span class="inst-examples">{_ex_text}</span></div></div>'
    ) if _tier_lbl else ""

    # ── Academic path reasoning text ─────────────────────────────────────
    _ap_reasoning = (_ap or {}).get("reasoning", "")
    _ap_reason_html = (
        f'<div class="niche-driver" style="margin-top:5px;font-size:10px;color:#374151;font-style:normal;">' 
        f'&#128218; {esc(_ap_reasoning)}' 
        f'</div>'
    ) if _ap_reasoning else ""

    # ── Paradigm concurrence badges from explainability_matrix ────────────
    _pc = _em.get("paradigm_concurrence") or {}
    _pc_badges = ""
    if _pc:
        _status_cls = {
            "CRITICAL_CONFIRMATION": "par-critical",
            "MODERATE_SUPPORT":      "par-moderate",
            "LOW_SIGNAL":            "par-low",
        }
        _status_icons = {
            "CRITICAL_CONFIRMATION": "★",
            "MODERATE_SUPPORT":      "◆",
            "LOW_SIGNAL":            "◇",
        }
        _par_parts = []
        for _pm_key in ["knrao","kp","jaimini","parashara"]:
            _pm_data = _pc.get(_pm_key) or {}
            _pm_status = _pm_data.get("status","")
            _pm_score  = _pm_data.get("score")
            _cls = _status_cls.get(_pm_status, "par-low")
            _ic  = _status_icons.get(_pm_status, "◇")
            _pm_short = {"knrao":"KN Rao","kp":"KP","jaimini":"Jaimini","parashara":"Parashara"}.get(_pm_key, _pm_key)
            if _pm_score is not None:
                _par_parts.append(f'<span class="par-badge {_cls}">{_ic} {_pm_short} {_pm_score:.0f}%</span>')
        _pc_badges = (
            f'<div class="paradigm-row">{"".join(_par_parts)}</div>'
        ) if _par_parts else ""

    return f"""
    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <span class="rank">{rank}</span>
                {label}
            </div>
            <div class="badges">
                <span class="badge" style="background: {domain_color}">{icon} {domain.title()}</span>
                <span class="badge badge-score">{score:.1f} pts</span>
                {f'<span class="badge" style="background:#e0e7ff;color:#3730a3;font-size:9.5px">{_ov_p}% Aligned</span>' if _ov_p else ""}
            </div>
        </div>
        
        <div class="card-body">
            <div class="pfe-section">
                <div class="pfe-label">Why this field suits your child</div>
                <div class="pfe-body">{parent_reason}</div>
            </div>
            
            <div class="astro-box">
                <div class="explanation-title" style="color: var(--astro-border);">Astrological Signature:</div>
                <div class="astro-text">{astro_reason}</div>
            </div>
            {verified_factors_html}
            {score_breakdown_html}
            {score_meta_html}
            <div class="insight-row">
                {w_badge}{g_badge}{b_badge}
            </div>
            {_gen_insight_detail(field)}
            {karakas_html}
            {friction_html}
            {niche_html}
            {conf_html}
            {_gen_sbc_detail(field)}
            {acad_html}
            {_ap_reason_html}
            {inst_html}
            {_gen_career_registry(field)}
            {_gen_global_mobility(field)}
            {_pc_badges}
            {_gen_method_detail(field)}
            {_gen_score_chain(field)}
        </div>
    </div>
    """


def _gen_competency_hierarchy_section(results: List[Dict]) -> str:
    """Competency-first hierarchy panel (2026-07 ontology audit G1-G18, G23-G30).

    Renders, above the flat top-20 card list, the missing intermediate
    structure: macro career identity -> ranked career-family clusters ->
    member fields with confidence bands + explanation chains. Purely
    additive — does not alter any score or the existing card list below it.
    Inline-styled so it doesn't depend on/modify the shared _CSS block.
    """
    if not results:
        return ""
    cluster_report = results[0].get("career_cluster_report") or {}
    clusters = cluster_report.get("clusters") or []
    macro = cluster_report.get("macro_identity")
    if not clusters:
        return ""

    # Keys match Field_Determination.competency_ontology.confidence_band()'s
    # output exactly (relabeled 2026-07-18 to "X (relative)" so the UI never
    # shows a bare "confidence" word next to a same-chart relative score
    # tier -- see CONFIDENCE_BAND_CAVEAT in that module).
    _band_color = {
        "Very High (relative)": "#059669", "High (relative)": "#2563eb",
        "Moderate (relative)": "#d97706", "Weak (relative)": "#9ca3af",
    }

    macro_html = ""
    if macro:
        macro_html = f"""
        <div style="background:linear-gradient(135deg,#1e293b,#334155);color:#fff;
                    border-radius:12px;padding:18px 22px;margin-bottom:18px;">
            <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;
                        color:#93c5fd;font-weight:700;">Macro Career Identity</div>
            <div style="font-size:15px;line-height:1.5;margin-top:6px;">{esc(macro.get('statement',''))}</div>
        </div>"""

    graph_rows = []
    for r in results[:20]:
        penalty = float(r.get("graph_broadness_penalty", 0.0) or 0.0)
        memberships = r.get("graph_family_memberships") or []
        if penalty <= 0 and len(memberships) <= 1:
            continue
        member_labels = []
        for m in memberships:
            if isinstance(m, (list, tuple)) and len(m) >= 3:
                member_labels.append(f"{esc(str(m[0]))} ({esc(str(m[2]))}, {float(m[1]):.2f})")
            elif isinstance(m, (list, tuple)) and m:
                member_labels.append(esc(str(m[0])))
            else:
                member_labels.append(esc(str(m)))
        graph_rows.append(f"""
        <div style="border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;background:#f8fafc;">
            <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;">
                <b style="color:#0f172a;">{esc(r.get('field_label', r.get('field_id', '')))}</b>
                <span style="font-size:12px;color:#475569;">KG cluster: {esc(r.get('graph_cluster',''))}</span>
            </div>
            <div style="font-size:12px;color:#475569;margin-top:4px;">
                Genericity discount: {round(penalty * 100)}%
                {(' &middot; Families: ' + ', '.join(member_labels)) if member_labels else ''}
            </div>
            <div style="font-size:12px;color:#64748b;margin-top:4px;">{esc(r.get('graph_note',''))}</div>
        </div>""")

    graph_html = ""
    if graph_rows:
        graph_html = f"""
        <div style="margin-bottom:18px;">
            <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;
                        color:#64748b;font-weight:700;margin-bottom:8px;">
                Knowledge Graph Audit Flags
            </div>
            <div style="display:grid;gap:8px;">{''.join(graph_rows[:6])}</div>
        </div>"""

    cluster_cards = []
    for c in clusters:
        band = c.get("confidence_band", "Moderate (relative)")
        color = _band_color.get(band, "#6b7280")
        members_html = "".join(
            f'<span style="display:inline-block;background:#f1f5f9;border:1px solid #e2e8f0;'
            f'border-radius:6px;padding:3px 9px;margin:2px;font-size:12px;color:#334155;">'
            f'{esc(m.get("field_label",""))} '
            f'<b style="color:{_band_color.get(m.get("confidence_band","Moderate (relative)"),"#6b7280")}">'
            f'{m.get("final_score",0)}</b></span>'
            for m in (c.get("members") or [])
        )
        cluster_cards.append(f"""
        <div style="border:1px solid #e2e8f0;border-left:4px solid {color};border-radius:8px;
                    padding:12px 16px;margin-bottom:10px;background:#fff;">
            <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;">
                <div>
                    <span style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;">
                        {esc(c.get('competency',''))}
                    </span>
                    <div style="font-size:16px;font-weight:700;color:#1e293b;">
                        #{c.get('cluster_rank','')} {esc(c.get('career_family',''))}
                    </div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:13px;font-weight:700;color:{color};">{band}</span>
                    <div style="font-size:11px;color:#94a3b8;">Family score {c.get('family_score','')} ·
                        {esc(c.get('demand_tag',''))}</div>
                </div>
            </div>
            <div style="margin-top:8px;">{members_html}</div>
        </div>""")

    return f"""
    <div class="section-label">Career Cluster Report (Competency &rarr; Career Family &rarr; Field)</div>
    <div style="margin-bottom:20px;">
        {macro_html}
        {graph_html}
        {''.join(cluster_cards)}
    </div>
    """


def generate_web_report(results: List[Dict], payload: NatalPayloadV2, output_dir: str = ".") -> str:
    """
    Generates the interactive HTML report.
    Returns the absolute path to the generated file.
    """
    # 1. Prepare Meta Data
    name = esc(getattr(payload, "name", "Native"))
    dob = esc(getattr(payload, "dob", ""))
    lagna = esc(getattr(payload, "lagna_sign", "Unknown"))
    
    # Extract Jaimini Karakas — fall back to direct payload fields
    _karakas = getattr(payload, "jaimini_karakas", {}) or {}
    ak  = esc(_karakas.get("AK",  "") or getattr(payload, "atmakaraka",  "") or "—")
    amk = esc(_karakas.get("AmK", "") or getattr(payload, "amatyakaraka", "") or "—")
    
    gen_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. Detect chart type — re-run on actual results using method scores
    # (pre-stamped chart_type used LLM-inflated final_score; method scores are stable)
    from .boosts import detect_chart_type as _detect_chart_type
    _ct = _detect_chart_type(results) if results else {}
    _is_cluster      = _ct.get("is_cluster", False)
    _cluster_label   = esc(_ct.get("cluster_label", ""))
    _domain_clusters = _ct.get("domain_clusters", {})

    # Cluster banner — shown only for polymathic charts
    if _is_cluster and _domain_clusters:
        _dc_pills = "".join(
            f'<div class="cluster-domain-pill">'
            f'<span class="cluster-domain-name">{esc(dom)}</span>'
            f'<span class="cluster-domain-count">{len(fids)} fields</span>'
            f'</div>'
            for dom, fids in list(_domain_clusters.items())[:6]
        )
        cluster_banner_html = (
            '<div class="cluster-banner">'
            '<div class="cluster-banner-left">'
            '<div class="cluster-banner-icon">&#127775;</div>'
            '<div>'
            f'<div class="cluster-banner-title">{_cluster_label}</div>'
            '<div class="cluster-banner-sub">Aptitude is distributed across a cluster of fields — '
            'all highlighted fields carry genuine astrological fit. '
            'No single field dominates; strength lies in cross-domain synthesis.</div>'
            '</div></div>'
            f'<div class="cluster-domain-grid">{_dc_pills}</div>'
            '</div>'
        )
    else:
        cluster_banner_html = ""

    # 3. Build Card HTML
    cards_html = []
    for idx, field in enumerate(results, start=1):
        cards_html.append(_gen_card(field, idx))

    cards_block = "\n".join(cards_html)

    # ── Corporate / Entrepreneur gauge HTML ───────────────────────────────────
    _ce = getattr(payload, "corporate_entrepreneurial", {}) or {}
    _corp_pct   = _ce.get("corporate_pct",  50)
    _entrep_pct = _ce.get("entrep_pct",     50)
    _style_lbl  = _ce.get("style_label",    "")
    _style_note = _ce.get("style_note",     "")
    # The bar shows corporate % on the left (gold→blue gradient); the transparent
    # right-side overlay masks the entrepreneurial portion.
    _entrep_mask = 100 - _corp_pct
    _gauge_html = f"""
        <div class="corp-gauge-wrap">
            <div class="corp-gauge-label">Working Style Profile — {_style_lbl}</div>
            <div class="corp-gauge-bar-wrap">
                <div style="font-size:10px;color:#3b82f6;font-weight:700;">Entrepreneur</div>
                <div class="corp-gauge-bar">
                    <div class="corp-gauge-bar-inner" style="width:{_entrep_mask}%;"></div>
                </div>
                <div style="font-size:10px;color:#92400e;font-weight:700;">Corporate</div>
                <span class="corp-gauge-pct">{_corp_pct}% Corp / {_entrep_pct}% Entrep</span>
            </div>
            <div class="corp-gauge-ends">
                <span>Founder · Consulting · Independent</span>
                <span>MNC · Enterprise · Government</span>
            </div>
            <div class="corp-style-note">{_style_note}</div>
        </div>""" if _ce else ""

    # 3. Assemble HTML Document
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JyotishAI Report — {name}</title>
    <style>{_CSS}</style>
</head>
<body>
    <div class="container">

        <div class="header">
            <div class="brand">JyotishAI Career Engine</div>
            <h1 class="title">{name}</h1>
            <div class="meta">
                {f'<span>DOB: {dob}</span>' if dob else ''}
                <span>Lagna: {lagna}</span>
                <span>AK: {ak}</span>
                <span>AmK: {amk}</span>
                <span>Generated: {gen_date}</span>
            </div>
        </div>

        {_gauge_html}

        {_gen_competency_hierarchy_section(results)}

        <div class="section-label">{"Aptitude Cluster" if _is_cluster else "Top 20 Fields"}</div>

        {cluster_banner_html}

        <div class="card-list">
            {cards_block}
        </div>
        
    </div>
</body>
</html>
"""

    # 4. Write to File
    os.makedirs(output_dir, exist_ok=True)
    filename = f"jyotish_report_{name.replace(' ', '_')}.html"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    logger.info(f"Generated Web Report: {filepath}")
    return os.path.abspath(filepath)

    # =============================================================================
# CAREER TIMELINE REPORT ENGINE (Restored)
# =============================================================================

# =============================================================================
# CAREER TIMELINE REPORT ENGINE
# =============================================================================

_TITLE_ACRONYMS = {
    "CEO", "CFO", "CTO", "COO", "CIO", "CMO", "CHRO", "CPO", "CDO", "CISO",
    "VP", "SVP", "EVP", "AVP", "HR", "IT", "QA", "UX", "UI", "AI", "ML",
    "PM", "PMO", "SDE", "SRE", "DBA", "BA", "SME", "MD", "GM", "CA", "CS",
}


def _smart_title(text: str) -> str:
    """Title-case a phrase but keep known acronyms upper-case.

    Fixes the `.title()` artifact that renders 'CEO' as 'Ceo', 'VP of IT' as
    'Vp Of It', etc. Each whitespace/`/`-delimited token is upper-cased if it
    (case-insensitively) matches a known acronym, otherwise title-cased.
    """
    if not text:
        return ""
    import re as _re
    out = []
    for tok in _re.split(r"(\s+|/|-)", str(text)):
        if not tok or tok.isspace() or tok in ("/", "-"):
            out.append(tok)
            continue
        out.append(tok.upper() if tok.upper() in _TITLE_ACRONYMS else tok.capitalize())
    return "".join(out)


# Glossary of the recurring Jyotish abbreviations/terms used throughout the
# report, so a non-specialist reader can decode it. Collapsed by default.
_GLOSSARY_TERMS = [
    ("Dasha (MD / AD / PD)", "Vimshottari planetary periods that time events — Mahadasha (major, years), Antardasha (sub-period), Pratyantardasha (sub-sub-period)."),
    ("KP", "Krishnamurti Paddhati — a precise system that uses each house cusp's sub-lord to judge whether and when an event fructifies."),
    ("Cusp sub-lord", "The decisive KP planet for a house; its house significations settle the outcome for that area of life."),
    ("D1 / D9 / D10 / D24 / D60", "Divisional charts: D1 birth chart, D9 durability/dharma, D10 career, D24 skills & education, D60 fine karmic detail (needs an exact birth time)."),
    ("AK / AmK", "Jaimini chara karakas: Atmakaraka (soul direction / vocation) and Amatyakaraka (career execution & advisors)."),
    ("Arudha Lagna / A10", "The chart's perceived public image (Arudha Lagna) and career/status image (A10, the Karma Pada)."),
    ("Houses (H2/H6/H10/H11 …)", "Life areas: H2 income, H6 service/employment, H10 profession/authority, H11 gains, H5/H8/H12 change, shock and exit."),
    ("Sade Sati", "A ~7.5-year transit of Saturn over the natal Moon — a period of pressure, responsibility and maturation, not automatic misfortune."),
    ("Gandanta · Papa Kartari · Kala Sarpa · Sandhi", "Classical stress/junction conditions that can delay or complicate results; treated here as risk modifiers, not verdicts."),
    ("SAV / Ashtakavarga · Vimsopaka", "Point-based strength measures used to gauge how resilient a house or planet is (SAV ~28 is average; higher is stronger)."),
]
_GLOSSARY_HTML = (
    '<details class="glossary-panel"><summary class="glossary-toggle">'
    '<h2 class="glossary-title">Glossary &mdash; what these terms mean</h2></summary>'
    '<dl class="gloss-grid">'
    + "".join(f'<div class="gloss-item"><dt class="gloss-term">{t}</dt>'
              f'<dd class="gloss-def">{d}</dd></div>' for t, d in _GLOSSARY_TERMS)
    + '</dl></details>'
)


def _fmt_date(d: str) -> str:
    """Convert YYYY-MM or YYYY-MM-DD to dd-Mon-yyyy."""
    if not d or d == "—":
        return d or "—"
    try:
        parts = d.split("-")
        if len(parts) == 2:
            from datetime import datetime as _dt
            return _dt.strptime(d, "%Y-%m").strftime("01-%b-%Y")
        if len(parts) == 3:
            from datetime import datetime as _dt
            return _dt.strptime(d, "%Y-%m-%d").strftime("%d-%b-%Y")
    except Exception:
        pass
    return d

_PD_THEMES: dict = {
    "Sun":     "Solar authority activates — expect recognition from seniors, institutional visibility, or a key decision that cements your position.",
    "Moon":    "Emotional intelligence at the fore — team bonding, stakeholder empathy, and public-facing work define this window.",
    "Mars":    "Execution drive peaks — ideal for project delivery, competitive bids, technical problem-solving, or asserting leadership.",
    "Mercury": "Communication clarity — negotiations, documentation, analytical breakthroughs, and cross-functional coordination.",
    "Jupiter": "Wisdom & expansion — strategic advising, knowledge-transfer, ethical leadership, or an advisory elevation.",
    "Venus":   "Relationship capital — client engagement, creative collaboration, and network-building yield tangible results.",
    "Saturn":  "Disciplined consolidation — process improvements, long-term commitments, and structural upgrades pay off.",
    "Rahu":    "Unconventional leap — disruptive ideas, cross-border exposure, or a tech-driven initiative gains traction.",
    "Ketu":    "Refinement & specialisation — quality focus, letting go of outdated roles, and honing core expertise.",
}

# 4B fix: affliction-aware override text — used when the PD lord is weak
# (debilitated, combust, or low eff_strength).  Swaps "clarity/breakthrough"
# style optimism for "re-calibration/overhead" style caution.
_PD_THEMES_MODERATE: dict = {
    "Sun":     "Partial solar activation — recognition is possible but may come with ego friction or institutional delays; keep expectations calibrated.",
    "Moon":    "Emotionally variable window — empathy remains an asset, but mood fluctuations or stakeholder ambiguity may require extra stabilisation.",
    "Mars":    "Drive is present but prone to over-extension — channel execution energy carefully; avoid aggressive deadlines or conflicts.",
    "Mercury": "Communication overhead likely — analytical re-calibration rather than breakthroughs; double-check documents, messages, and contracts.",
    "Jupiter": "Wisdom is available but may be over-optimistic — strategic advising should be grounded in data; avoid over-committing.",
    "Venus":   "Relationship sensitivity elevated — networking is worthwhile but alliances may need careful nurturing; creative delays possible.",
    "Saturn":  "Structural pressure builds — discipline is necessary but burnout risk is real; prioritise targeted effort over broad commitments.",
    "Rahu":    "Disruption risk is amplified — cross-border or tech initiatives need stronger due diligence; not ideal for speculative leaps.",
    "Ketu":    "Fragmentation and detachment surface — specialisation work continues but lacks momentum; avoid abrupt role exits.",
}

_PD_THEMES_SEVERE: dict = {
    "Sun":     "Solar authority is suppressed — this window carries friction with seniors, institutional blockages, or visibility setbacks; proceed with patience.",
    "Moon":    "Emotional turbulence likely — team dynamics are strained; avoid high-stakes interpersonal decisions and focus on inner stability.",
    "Mars":    "Execution aggravated — high risk of conflict, technical breakdowns, or implementation stalls; conserve energy and avoid forced confrontations.",
    "Mercury": "Communication breakdowns and analytical deadlocks — re-read every contract, expect delays in approvals, and manage miscommunication proactively.",
    "Jupiter": "Expansion is hollow — advice or mentorship may be misapplied; avoid over-leveraging on ethical or legal promises during this window.",
    "Venus":   "Relationship strain and creative stagnation — financial negotiations or artistic pursuits face resistance; defer major commitments.",
    "Saturn":  "Structural strain peaks — systemic delays, increased workload without proportional reward, or karmic friction around authority; endurance is the tool.",
    "Rahu":    "Destabilising disruption — foreign gambles, speculative innovations, or unconventional moves carry elevated downside risk this window.",
    "Ketu":    "Deep detachment and isolation — specialisation turns inward but momentum is absent; not a window for external launches or pivots.",
}

def _pd_narrative(pd_lord: str, md_lord: str = "", affliction: str = "ok") -> str:
    # 4B fix: select text tier based on affliction level stamped by timeline.py
    if affliction == "severe":
        return _PD_THEMES_SEVERE.get(pd_lord, "Challenging sub-period requiring extra groundwork and careful navigation.")
    if affliction == "moderate":
        return _PD_THEMES_MODERATE.get(pd_lord, "Mixed sub-period — positive themes require deliberate effort to manifest.")
    return _PD_THEMES.get(pd_lord, "A focused sub-period that colours the Antardasha energy.")

def _tl_conf_badge(conf: str) -> str:
    css = "conf-strong" if conf == "STRONG" else ("conf-moderate" if conf == "MODERATE" else "conf-mismatch")
    label = conf.replace("_", " ").replace("CALIBRATION MISMATCH", "Calibrating")
    return f'<span class="tl-conf-badge {css}">{esc(label)}</span>'

def _tl_display_event_type(block: Dict[str, Any]) -> str:
    """Display-only event-type string for a block, applying the same
    "Promotion Runway + Executive Visibility" override as
    llm_narrative_builder._promotion_runway_display_label (kept in sync
    manually since the two modules render different surfaces: the LLM
    fallback narrative there vs. the chip/header/exec-summary here).

    User-reported gap (2026-07): the override existed but was only wired
    into the LLM-narrative fallback HTML, never into the actual visible
    period chip/title/exec-summary cells in the live report, so users
    never saw "Promotion Runway" even when the underlying conditions
    (AmK-activated, open promotion cycle, senior designation stage) were
    already true. event_type/final_event_type itself is left untouched —
    this only changes what text a human reads.
    """
    raw = block.get("event_type") or ""
    _sub = block.get("sub_scores", {}) or {}
    _event_type = block.get("final_event_type") or raw
    _amk_activated = bool(_sub.get("amk_activated"))
    _promo_cycle_open = bool(_sub.get("promo_cycle_bonus"))
    _desig_bias = _sub.get("designation_event_bias") or {}
    _senior_stage = bool(_desig_bias)
    if (
        _amk_activated and _promo_cycle_open and _senior_stage
        and _event_type in ("LEADERSHIP_EXPANSION", "GROWTH", "AUTHORITY_SHIFT", "STABILITY")
    ):
        return "PROMOTION RUNWAY + EXECUTIVE VISIBILITY"
    return raw


def _tl_event_badge(et: str) -> str:
    known = {
        "PROMOTION", "LEADERSHIP_EXPANSION", "ROLE_CHANGE", "INCOME_INFLECTION",
        "NETWORKING_OPPORTUNITY", "JOB_CHANGE", "GROWTH", "STABILITY",
        # New event types from 34-gap enhancer (G28-G31)
        "BREAKTHROUGH", "SALARY_HIKE", "AUTHORITY_SHIFT", "RISK_PERIOD",
        "CALIBRATION", "ENTREPRENEURSHIP_WINDOW", "EQUITY_EVENT",
        "LATERAL_MOVE", "SANDHI_PERIOD",
        "CAREER_PLATEAU", "STAGNATION", "CAREER_THROUGH_PARTNERSHIP",
    }
    css = f"et-{et}" if et in known else "et-DEFAULT"
    label = et.replace("_", " ").title()
    return f'<span class="ad-badge {css}">{esc(label)}</span>'

# NOTE (2026-07-07): score-decomposition bars and a "why this event / why not
# another" explanation are already implemented and LIVE in
# _build_career_roadmap_html() below — see `matrix_html` (per-dimension
# promotion/income/job_change/foreign/risk/stability/visibility bars),
# `kp_ev_html` (per-event-type KP verdicts via _kp_event_verdicts()), and
# `cx_html` ("Contradiction Check": supporting vs. blocking factors with a net
# verdict). Those were found already built into the live report while
# implementing the actionability layer below, so they are not duplicated here.
#
# _tl_ad_card (below) is NOT currently called anywhere in the live report
# pipeline — the per-year `roadmap-year-card` built in
# _build_career_roadmap_html() is what actually renders, so no new UI was
# added to _tl_ad_card here.
#
# Gap 4 fix: deterministic actionability layer. Maps event_type -> a short,
# fixed set of recommended actions. This is intentionally a static lookup
# (not LLM-generated) so it is auditable and identical across runs; it is
# tied to event_type + confidence tier per the audit's request. Kept
# conservative/measured in tone per the "no scary language" gap (independently
# verified as already true elsewhere in job_loss.py's narrative strings).
_EVENT_ACTIONS: Dict[str, List[str]] = {
    "PROMOTION":            ["Document recent wins for your review cycle", "Signal readiness to your manager before the window closes"],
    "LEADERSHIP_EXPANSION":  ["Take on visible cross-team responsibility", "Mentor a junior colleague to build leadership evidence"],
    "BREAKTHROUGH":          ["Pursue the highest-visibility project available", "Avoid overcommitting outside your core strength area"],
    "SALARY_HIKE":           ["Prepare a data-backed case for negotiation", "Time the ask near the appraisal cycle, not before it"],
    "INCOME_INFLECTION":     ["Review compensation benchmarks for your role", "Consider a side income or freelance opening if salaried growth is capped"],
    "JOB_CHANGE":            ["Update your resume/profile quietly", "Interview broadly before committing to one offer"],
    "LATERAL_MOVE":          ["Evaluate the move on skill growth, not just title", "Confirm reporting line and scope before accepting"],
    "FOREIGN_POSTING":       ["Get visa/relocation paperwork moving early", "Clarify tax and family-relocation logistics before agreeing"],
    "ENTREPRENEURSHIP_WINDOW": ["Validate the business idea with a small pilot first", "Keep 6+ months of expenses in reserve before leaving employment"],
    "EQUITY_EVENT":          ["Review vesting schedule and tax implications", "Get independent financial advice before acting on equity"],
    "RISK_PERIOD":           ["Do not resign impulsively — strengthen internal visibility", "Keep your resume current as a precaution, not a plan"],
    "SANDHI_PERIOD":         ["Avoid major irreversible decisions this window", "Expect delays; re-confirm plans once the transition settles"],
    "CAREER_PLATEAU":        ["Actively seek a new challenge or lateral project", "Consider a certification to reopen growth options"],
    "STAGNATION":            ["Re-evaluate whether the current role still fits your goals", "Build one new visible skill this period"],
    "SKILL_UPGRADE_PHASE":   ["Enroll in a certification aligned to your target role", "Use this window for learning over job-hunting"],
    "AUTHORITY_SHIFT":       ["Clarify your new scope of authority in writing", "Set expectations with your team early"],
    "STABILITY":             ["Consolidate current responsibilities", "Good window for steady execution rather than big moves"],
    "GROWTH":                ["Take on stretch assignments", "Keep visibility high with stakeholders"],
    # 2026-07-07 fix: business-track and semantic-reclassification tags added
    # (see _EVENT_TONE_CATEGORY comment above for why these were missing).
    "BUSINESS_EXPANSION":       ["Scale gradually — validate capacity before overcommitting", "Reinvest profits into infrastructure before headcount"],
    "BUSINESS_BREAKTHROUGH":    ["Capitalize on the current opening with a focused push", "Document the win — it strengthens future proposals"],
    "REVENUE_GROWTH":           ["Track margins as revenue grows, not just top-line", "Reinvest selectively rather than all at once"],
    "CLIENT_PIPELINE_SHIFT":    ["Diversify the client base rather than relying on one account", "Formalize new client relationships in writing"],
    "MARKET_REPOSITIONING":     ["Pilot the repositioning before a full pivot", "Reassess target market fit before committing resources"],
    "BUSINESS_REENTRY":         ["Re-establish key relationships before scaling up", "Start with a smaller, lower-risk offering"],
    "FIRST_CLIENT_WINDOW":      ["Prioritize delivery quality over volume for the first client", "Ask for a referral once trust is established"],
    "FOREIGN_BASE_REPOSITIONING":     ["Get visa/relocation logistics moving early", "Confirm cost-of-living adjustment before agreeing"],
    "FOREIGN_CLIENT_PLATFORM_GROWTH": ["Invest in remote-delivery infrastructure/tools", "Build repeatable processes for global client work"],
    "DISRUPTIVE_GLOBAL_TRANSFORMATION": ["Stay flexible — this window rewards adaptability over a rigid plan", "Avoid over-committing to one fixed path until it stabilizes"],
    "PRESSURE_GAIN_WINDOW":     ["Pace yourself — this gain comes with real workload", "Set boundaries to avoid burnout while capitalizing on the window"],
    "TRANSITION":               ["Use this window to explore options before committing", "Keep current responsibilities steady while evaluating change"],
    "RE_ENTRY":                 ["Refresh skills/certifications before re-entering", "Lean on your network for a warm re-entry rather than cold applications"],
    "FIRST_JOB":                ["Prioritize learning and mentorship over immediate salary", "Build foundational visibility with early, reliable delivery"],
    "CALIBRATION":              ["Treat this as a data-gathering period — avoid big commitments", "Revisit plans once the next dasha shift clarifies the signal"],
    "CAREER_THROUGH_PARTNERSHIP": ["Formalize the partnership/collaboration terms in writing", "Vet the partner's track record before committing resources"],
}
_DEFAULT_ACTIONS = ["Continue steady performance", "Reassess priorities at the next Antardasha shift"]
# Used live in _build_career_roadmap_html() below (see "Actionability layer"
# comment near `action_html`), not in the currently-uncalled _tl_ad_card.


# ── Gap 1 fix (2026-07-07): Parent / Family Guidance panel ───────────────
# The report already separates Executive/client (`_build_exec_and_audit_panels`
# -> exec_html) and Astrologer/auditor (audit_html + each card's collapsed
# "View evidence & astrological basis" panel) audiences. A third, distinct
# audience — parent/family, "how do I support this person, what should I NOT
# panic about" — did not exist anywhere in the report. This adds it as its
# own visible, deterministic panel per year card, tonally separate from both
# the practical action list and the technical audit trail.
#
# Also folds in Gap 5 (non-scary risk language): when a block's job_loss-style
# risk is real (career_risk.severity present), this panel uses the requested
# Risk Type / Severity / Protection / Recommended posture format instead of
# alarmist wording — reusing job_loss.py's own severity/recovery/continuity
# fields (already computed on the block as `career_risk`), not inventing new
# numbers.
_EVENT_TONE_CATEGORY: Dict[str, str] = {
    "PROMOTION": "growth", "LEADERSHIP_EXPANSION": "growth", "BREAKTHROUGH": "growth",
    "SALARY_HIKE": "growth", "INCOME_INFLECTION": "growth", "GROWTH": "growth",
    "SKILL_UPGRADE_PHASE": "growth", "AUTHORITY_SHIFT": "growth", "EQUITY_EVENT": "growth",
    "ENTREPRENEURSHIP_WINDOW": "growth", "NETWORKING_OPPORTUNITY": "growth",
    "JOB_CHANGE": "transition", "LATERAL_MOVE": "transition", "TRANSITION": "transition",
    "RE_ENTRY": "transition", "FIRST_JOB": "transition", "FOREIGN_POSTING": "transition",
    "CAREER_THROUGH_PARTNERSHIP": "transition",
    "RISK_PERIOD": "risk", "SANDHI_PERIOD": "risk", "CAREER_PLATEAU": "risk",
    "STAGNATION": "risk", "CALIBRATION": "risk",
    "STABILITY": "steady",
    # 2026-07-07 fix: the business-track and semantic-reclassification tags
    # from timeline.py's full _APPROVED_EVENT_TAGS (30 tags total) were
    # missing here entirely — a real chart hit PRESSURE_GAIN_WINDOW and
    # DISRUPTIVE_GLOBAL_TRANSFORMATION and silently fell back to "steady"
    # generic text. Added per timeline.py's own comments on what each tag
    # means (see _all_blocks reclassification pass, ~line 4000-4038, and the
    # business-track scoring in career_field_report_v2.py).
    "BUSINESS_EXPANSION": "growth", "BUSINESS_BREAKTHROUGH": "growth",
    "REVENUE_GROWTH": "growth", "CLIENT_PIPELINE_SHIFT": "growth",
    "FIRST_CLIENT_WINDOW": "growth", "FOREIGN_CLIENT_PLATFORM_GROWTH": "growth",
    # PRESSURE_GAIN_WINDOW: real gain, but via workload/competition/conflict
    # (Mars dual-lordship of a growth + dusthana house) — still "growth" tone,
    # but the headline/body text below acknowledges the added effort.
    "PRESSURE_GAIN_WINDOW": "growth",
    "MARKET_REPOSITIONING": "transition", "BUSINESS_REENTRY": "transition",
    "FOREIGN_BASE_REPOSITIONING": "transition",
    # DISRUPTIVE_GLOBAL_TRANSFORMATION: per timeline.py's own comment, this is
    # a promotion-tier result relabeled for a disruptive/Rahu-driven quality
    # (sudden, unconventional, restructuring-linked) — closer to "transition"
    # than plain "growth" or "risk", since it is not a loss signal.
    "DISRUPTIVE_GLOBAL_TRANSFORMATION": "transition",
}

# ── Gap 2 fix (2026-07-07): "Why this event, why not another" panel ──────
# Maps the engine's event_type taxonomy onto the KP event buckets already
# defined in astrology_explainer._KP_EVENT_HOUSE_RULES (Promotion / Income /
# Job Change / Foreign / Leadership / Risk), so the chosen event and its
# contrasting alternative can both be explained with real KP house numbers
# instead of generic prose.
_EVENT_TO_KP_BUCKET = {
    "PROMOTION": "Promotion", "LEADERSHIP_EXPANSION": "Leadership", "BREAKTHROUGH": "Leadership",
    "AUTHORITY_SHIFT": "Leadership",
    "SALARY_HIKE": "Income", "INCOME_INFLECTION": "Income", "EQUITY_EVENT": "Income",
    "JOB_CHANGE": "Job Change", "LATERAL_MOVE": "Job Change",
    "FOREIGN_POSTING": "Foreign",
    "RISK_PERIOD": "Risk", "SANDHI_PERIOD": "Risk", "CAREER_PLATEAU": "Risk", "STAGNATION": "Risk",
    # 2026-07-07 fix: added so these semantic-reclassification tags (see
    # _EVENT_TONE_CATEGORY comment above) also get a Why panel where the
    # underlying _KP_EVENT_HOUSE_RULES bucket genuinely applies.
    # Foreign-flavored relabels map onto the existing "Foreign" KP rule.
    "FOREIGN_BASE_REPOSITIONING": "Foreign", "FOREIGN_CLIENT_PLATFORM_GROWTH": "Foreign",
    # DISRUPTIVE_GLOBAL_TRANSFORMATION is a promotion-tier score relabeled for
    # Rahu-driven disruptive quality (timeline.py's own comment) — the KP
    # test underneath is still the Promotion houses.
    "DISRUPTIVE_GLOBAL_TRANSFORMATION": "Promotion",
    # Business-track tags (BUSINESS_EXPANSION, REVENUE_GROWTH, etc.) and
    # PRESSURE_GAIN_WINDOW are intentionally NOT mapped here: they come from
    # a Mars dual-lordship / self-employment scoring path that doesn't
    # correspond to any single _KP_EVENT_HOUSE_RULES bucket (those rules are
    # written for salaried-career houses). Forcing a match would be a
    # fabricated analogy, not a real KP test — the Why panel is correctly
    # omitted for these rather than shown with an invented justification.
}


def _tl_why_panel_html(event_type: str, kp_ev: List[Dict[str, Any]], kp_chain: Dict[str, Any],
                        sub_scores: Dict[str, Any], d10_score: Optional[float],
                        transit_flags: Optional[List[str]] = None) -> str:
    """Builds the literal 'Why {event} / Why not {alternative}' two-column
    panel: KP houses (from _KP_EVENT_HOUSE_RULES + the real per-year kp_chain
    lord ties already computed by _kp_event_verdicts), D10 house-link status
    (sub_scores d10_h12_active / d10_structural_score, already computed by
    timeline.py), and transit trigger flags already on the block. No new
    astrological computation — same inputs already feeding kp_ev_html/cx_html,
    reorganized into the requested Why/Why-not comparison shape."""
    if not kp_ev:
        return ""
    et_key = (event_type or "").upper().replace(" ", "_")
    bucket = _EVENT_TO_KP_BUCKET.get(et_key)
    if not bucket:
        return ""
    kp_by_name = {e["name"]: e for e in kp_ev}
    chosen = kp_by_name.get(bucket)
    if not chosen:
        return ""
    # Pick the contrasting alternative: Risk if the chosen event isn't itself
    # risk-flavored (matches the audit's own JOB_CHANGE-vs-JOB_LOSS example);
    # otherwise contrast against whichever non-Risk bucket verdicts strongest.
    if bucket != "Risk" and "Risk" in kp_by_name:
        alt_name = "Risk"
    else:
        _others = [e for e in kp_ev if e["name"] != bucket]
        alt_name = max(_others, key=lambda e: {"Supports": 2, "Mixed": 1, "Denies": 0}[e["verdict"]])["name"] if _others else None
    alt = kp_by_name.get(alt_name) if alt_name else None

    def _houses_str(name: str) -> str:
        support, block = _KP_EVENT_HOUSE_RULES.get(name, ((), ()))
        parts = ["/".join(support)] if support else []
        if block:
            parts.append("not " + "/".join(block))
        return ", ".join(parts)

    why_items = [f"KP houses {esc(_houses_str(bucket))} — {esc(chosen['verdict'].lower())} ({esc(chosen['detail'])})"]
    _d10_links = sub_scores.get("d10_house_links")
    if isinstance(d10_score, (int, float)) and d10_score >= 0.3:
        why_items.append(f"D10 structural link active (score {d10_score:.2f}" + (f", houses {esc(str(_d10_links))}" if _d10_links else "") + ")")
    if transit_flags:
        why_items.append("Transit trigger: " + esc(", ".join(transit_flags[:2])))

    against_items = []
    if alt:
        against_items.append(f"KP houses {esc(_houses_str(alt_name))} — {esc(alt['verdict'].lower())} for {esc(alt_name)} ({esc(alt['detail'])})")
    if sub_scores.get("d10_h12_active"):
        against_items.append("D10 12th-house activation is present (some caution warranted)")
    elif isinstance(d10_score, (int, float)):
        against_items.append("D10 Lagna/10th not severely damaged" if d10_score >= 0.3 else "D10 is weak, but no destructive 8th/12th activation confirmed")

    if not against_items:
        return ""
    why_html_items = "".join(f"<li>{s}</li>" for s in why_items)
    against_html_items = "".join(f"<li>{s}</li>" for s in against_items)
    return (
        '<div class="rmap-why-panel">'
        f'<div class="rmap-why-col"><div class="rmap-why-title">Why {esc(bucket)}</div><ul>{why_html_items}</ul></div>'
        + (f'<div class="rmap-why-col rmap-why-against"><div class="rmap-why-title">Why not {esc(alt_name)}</div><ul>{against_html_items}</ul></div>' if alt_name else '') +
        '</div>'
    )


_PARENT_GUIDANCE_TEXT = {
    "growth": (
        "A supportive window",
        "The signals for this period point toward growth or recognition. "
        "The best support you can offer is encouragement and patience with "
        "the extra hours or focus this often requires — there is nothing "
        "here that needs intervention or worry.",
    ),
    "transition": (
        "A change in progress, not a crisis",
        "This period favors a considered change — a new role, a shift in "
        "direction, or a move that expands options. Change can feel "
        "unsettling from the outside; the most useful support is patience "
        "during the decision process rather than pressure to decide quickly.",
    ),
    "risk": (
        "A period to stay steady, not alarmed",
        "This window carries some instability signals. That does not mean "
        "something bad will happen — it means added patience and emotional "
        "support are more valuable than advice to make a big move. Avoid "
        "amplifying worry; a calm, steady presence is the most helpful thing "
        "a family member can offer right now.",
    ),
    "steady": (
        "A consolidating period",
        "Nothing dramatic is indicated this period — it favors steady, "
        "reliable effort over big decisions. No special support is needed "
        "beyond normal encouragement.",
    ),
}


def _tl_family_panel_html(event_type: str, career_risk: Optional[Dict[str, Any]]) -> str:
    et_key = (event_type or "").upper().replace(" ", "_")
    category = _EVENT_TONE_CATEGORY.get(et_key, "steady")

    risk_block_html = ""
    severity = (career_risk or {}).get("severity") if isinstance(career_risk, dict) else None
    if severity and severity != "mild":
        # Gap 5 format: Risk Type / Severity / Protection / Recommended posture.
        # Reuses job_loss.py's own computed fields; no new numbers invented.
        ledger_label = str((career_risk or {}).get("ledger_label", "") or "role instability").replace("_", " ")
        recovery = (career_risk or {}).get("recovery_window") or {}
        continuity = (career_risk or {}).get("continuity_score")
        protection_word = "Strong" if (recovery.get("present") or (isinstance(continuity, (int, float)) and continuity >= 60)) \
            else ("Moderate" if isinstance(continuity, (int, float)) and continuity >= 35 else "Limited")
        severity_word = {"severe": "High", "high": "Elevated", "moderate": "Medium"}.get(severity, "Low")
        posture = {
            "severe":   "Keep the resume current and strengthen internal visibility; avoid impulsive resignation.",
            "high":     "Do not resign impulsively — strengthen internal visibility and keep options open.",
            "moderate": "Stay attentive but continue normal work; no action needed beyond awareness.",
        }.get(severity, "Continue as normal; this is a minor, low-priority signal.")
        risk_block_html = (
            '<div class="rmap-family-risk">'
            f'<div class="rmap-family-risk-row"><span>Risk Type</span><span>{esc(ledger_label.title())}</span></div>'
            f'<div class="rmap-family-risk-row"><span>Severity</span><span>{esc(severity_word)}</span></div>'
            f'<div class="rmap-family-risk-row"><span>Protection</span><span>{esc(protection_word)}</span></div>'
            f'<div class="rmap-family-risk-row"><span>Recommended posture</span><span>{esc(posture)}</span></div>'
            '</div>'
        )

    headline, body = _PARENT_GUIDANCE_TEXT[category]
    return (
        '<div class="rmap-family-panel">'
        f'<div class="rmap-family-headline">{esc(headline)}</div>'
        f'<p class="rmap-family-body">{esc(body)}</p>'
        + risk_block_html +
        '</div>'
    )


def _tl_ad_card(period: dict, idx: int) -> str:
    md_lord    = period.get("md_lord", "")
    ad         = esc(period.get("ad_lord", ""))
    et         = period.get("event_type", "DEFAULT")
    score      = period.get("career_score", 0.0)
    start      = esc(_fmt_date(period.get("start_date", "")))
    end        = esc(_fmt_date(period.get("end_date", "")))
    # Two segregated narrative layers (2026-07-19, user request): plain-
    # language career prose vs. technical astrological reasoning, rendered as
    # two distinct panels instead of one blended block. Falls back to the
    # legacy combined key for any block enriched before this change.
    llm_plain_html = period.get("llm_plain_language_html", "")
    llm_astro_html = period.get("llm_astro_explanation_html", "")
    llm_html   = period.get("llm_ad_narrative_html", "")
    plain_hint = esc(period.get("narrative_hint", "")).replace("&#x27;", "'")
    houses     = ", ".join(f"H{h}" for h in period.get("active_houses", []))
    kp_score   = period.get("sub_scores", {}).get("kp_cusp_score", 0.0)
    j_role     = esc(period.get("jaimini_role", ""))
    kp_align   = esc(str(period.get("kp_cusp_alignment", "") or ""))
    remedies   = period.get("remedies", [])
    pds        = period.get("pratyantardashas", [])

    is_past    = period.get("is_past", False)
    is_current = period.get("is_current", False)
    is_primary = period.get("is_primary_opportunity", False)
    card_cls   = (
        " is-past" if is_past else
        (" is-current" if is_current else
         (" is-primary-opp" if is_primary else ""))
    )
    crown_html = '<span class="opp-crown">&#9733; Primary Opportunity</span>' if is_primary else ''

    tag_cls    = "tag-past" if is_past else ("tag-current" if is_current else "tag-future")
    tag_txt    = "Past" if is_past else ("Current" if is_current else "Upcoming")

    bar_w   = int(min(score, 1.0) * 100)
    bar_col = "#1E7B50" if score >= 0.7 else ("#C9820A" if score >= 0.5 else "#6B5B8E")

    pills = ""
    if houses:
        pills += f'<span class="pill pill-house">{esc(houses)}</span>'
    if kp_align or kp_score > 0:
        pills += f'<span class="pill pill-kp">KP {kp_align or f"{kp_score:.2f}"}</span>'
    if j_role:
        pills += f'<span class="pill pill-jaimini">{j_role.split("—")[0].strip()[:55]}</span>'
    # NOTE: remedy text is NOT added to pills row — it is shown in the dedicated remedies section below
    # Salary range pill
    _sr = period.get("salary_range") or {}
    if _sr.get("low_pct") and _sr.get("high_pct"):
        pills += (
            '<span class="pill pill-salary" title="Estimated increment range">'
            f'💰 +{_sr["low_pct"]}–{_sr["high_pct"]}%</span>'
        )
    near_miss = period.get("near_miss", "")
    if near_miss:
        pills += f'<span class="pill pill-nearmiss">Near miss: {esc(near_miss)}</span>'

    pd_html = ""
    if pds:
        import re as _re_pd
        chips = ""
        for p in pds:
            pdl      = p.get("pd_lord", "")
            pd_llm   = p.get("llm_narrative_html", "")
            # Strip empty <strong></strong> and "Peak activation around ." from LLM output
            if pd_llm:
                pd_llm = _re_pd.sub(r'<strong>\s*</strong>', '', pd_llm)
                pd_llm = _re_pd.sub(r'Peak activation around\s*\.?\s*', '', pd_llm)
                # Discard generic placeholder text — fall through to planet-specific theme
                _stripped_text = _re_pd.sub(r'<[^>]+>', '', pd_llm).strip()
                _generic_phrases = (
                    "minor activations possible",
                    "activations possible",
                    "sub-period:",
                    "no specific",
                )
                if not _stripped_text or any(g in _stripped_text.lower() for g in _generic_phrases):
                    pd_llm = ""  # will use pd_plain below

            pd_plain = esc(_pd_narrative(pdl, md_lord, affliction=p.get("affliction", "ok")))
            pd_body  = (
                f'<div class="pd-llm">{pd_llm}</div>'
                if pd_llm else
                f'<div class="pd-note">{pd_plain}</div>'
            )
            # Format PD dates — use exact dates; if start == end (very short PD), show just start
            pd_start_raw = p.get("start_date", "")
            pd_end_raw   = p.get("end_date", "")
            pd_start_fmt = _fmt_date(pd_start_raw)
            pd_end_fmt   = _fmt_date(pd_end_raw)
            if pd_start_fmt == pd_end_fmt:
                pd_date_str = pd_start_fmt  # zero-duration: show just one date
            else:
                pd_date_str = f"{pd_start_fmt} — {pd_end_fmt}"
            # Phase 3 (2026-07-05, item #20): surface the PD-level score
            # computed in timeline.py (_HOUSE_CAREER_WEIGHT/KP/D10/eff-strength
            # blend for this specific Pratyantardasha lord) instead of only a
            # narrative note — gives month-level timing a number, not just prose.
            _pd_score = p.get("pd_score")
            _pd_score_chip = (
                f'<span class="pd-score" title="PD-level career signal (house/KP/D10/strength blend)">'
                f'{int(round(_pd_score * 100))}%</span>'
                if isinstance(_pd_score, (int, float)) else ''
            )
            chips += (
                f'<div class="pd-item">'
                f'<div class="pd-header">'
                f'<span class="pd-chip">{esc(pdl)}</span>'
                f'<span class="pd-dates">{esc(pd_date_str)}</span>'
                + _pd_score_chip +
                f'</div><div class="pd-content">{pd_body}</div></div>'
            )
        pd_id  = f"pd-{idx}"
        pd_html = (
            f'<button class="pd-toggle" onclick="togglePD(\'{pd_id}\')" aria-expanded="false" id="btn-{pd_id}">'
            f'<span class="pd-toggle-icon">&#9656;</span> Sub-periods ({len(pds)})</button>'
            f'<div class="pd-list" id="{pd_id}" hidden>{chips}</div>'
        )

    if llm_plain_html or llm_astro_html:
        narrative_section = (
            '<div class="llm-narrative llm-narrative-plain">'
            '<h4 class="llm-layer-title">In Plain Language</h4>'
            f'{llm_plain_html}</div>'
            '<div class="llm-narrative llm-narrative-astro">'
            '<h4 class="llm-layer-title">Astrological Explanation</h4>'
            f'{llm_astro_html}</div>'
        )
    elif llm_html:
        # Legacy combined blob (block enriched before the two-layer split).
        narrative_section = f'<div class="llm-narrative">{llm_html}</div>'
    else:
        narrative_section = f'<div class="ad-insight">{plain_hint}</div>' if plain_hint else ""

    # Event-specific remedies (from llm_narrative_builder or fallback to planet remedies)
    _event_rems = period.get("event_remedies", []) or remedies
    _rem_html = ""
    if _event_rems and not is_past:
        _rem_items = "".join(f"<li>{esc(r)}</li>" for r in _event_rems[:3])
        _rem_html = (
            f'<div class="remedies-section">'
            f'<div class="remedies-title">Planetary Remedies</div>'
            f'<ul class="remedies-list">{_rem_items}</ul>'
            f'</div>'
        )

    # All enhancer + sub-score fields live in sub_scores
    _ss = period.get("sub_scores") or {}

    # Yoga sub-scores badge
    _yogas = _ss.get("active_yogas", [])
    _yoga_badge = ""
    if _yogas:
        # Gap fix (2026-07-05, user-reported): yoga names were shown with a
        # generic "Active natal yogas" tooltip and no explanation of what each
        # named yoga (e.g. NakParivartana_Saturn_Ketu) actually means for
        # career. Use the real per-tag explanation as the tooltip text.
        _yoga_explain_map = _explain_active_yogas(_yogas)
        _yoga_tooltip = " | ".join(f"{t}: {_yoga_explain_map[t]}" for t in _yogas[:2])
        _yoga_badge = (
            f'<span class="pill" style="background:rgba(201,168,76,0.12);color:#7A5E00;'
            f'border-color:rgba(201,168,76,0.35)" title="{esc(_yoga_tooltip)}">'
            f'✦ {", ".join(_yogas[:2])}</span>'
        )

    # ── Per-AD D10 alignment + top G-factor signals ─────────────────────────
    _d10_align = _ss.get("d10_alignment", 0) or _ss.get("d10_full_score", 0) or 0
    _fired = _ss.get("fired_g_factors", []) or []
    _d10_row_html = ""
    if _d10_align and _d10_align > 0.05:
        _d10_pct = round(_d10_align * 100)
        _d10_col = "#15803d" if _d10_align >= 0.55 else ("#92400e" if _d10_align >= 0.30 else "#6b7280")
        _d10_parts = [f'<span class="ad-d10-badge" style="color:{_d10_col};border-color:{_d10_col}22">D10 Align {_d10_pct}%</span>']
        if _fired:
            _pos_factors = [f for f in _fired if not str(f).startswith("-")][:3]
            _neg_factors = [f for f in _fired if str(f).startswith("-")][:1]
            for gf in _pos_factors:
                _d10_parts.append(f'<span class="ad-gfact-pill">{esc(str(gf))}</span>')
            for gf in _neg_factors:
                _d10_parts.append(f'<span class="ad-gfact-pill ad-gfact-neg">{esc(str(gf))}</span>')
        _d10_row_html = f'<div class="ad-d10-row">{"".join(_d10_parts)}</div>'

    # ── Enhancer pills (G1-G34 signals) ─────────────────────────────────────
    _enh_pills = ""

    # Yogini Dasha name
    _yog_name = _ss.get("yogini_name", "")
    if _yog_name:
        _yog_score = _ss.get("yogini_score", 0)
        _yog_col = ("#1E7B50" if _yog_score >= 0.75
                    else "#B8720A" if _yog_score >= 0.55 else "#B33A2E")
        _enh_pills += (
            f'<span class="pill" style="background:rgba(30,123,80,0.08);'
            f'color:{_yog_col};border-color:rgba(30,123,80,0.25)" '
            f'title="Yogini Dasha">◈ {esc(_yog_name)}</span>'
        )

    # Vimsopaka Bala
    _vim = _ss.get("vimsopaka_score", 0)
    if _vim and _vim != 0.5:
        _vim_col = "#1E7B50" if _vim >= 0.65 else ("#B8720A" if _vim >= 0.45 else "#B33A2E")
        _enh_pills += (
            f'<span class="pill" style="background:rgba(107,91,142,0.08);'
            f'color:{_vim_col};border-color:rgba(107,91,142,0.25)" '
            f'title="Vimsopaka Bala (16-varga strength)">Vim {_vim:.2f}</span>'
        )

    # D10 full score
    _d10 = _ss.get("d10_full_score", 0)
    if _d10 and _d10 > 0.3:
        _enh_pills += (
            f'<span class="pill" style="background:rgba(37,99,235,0.08);'
            f'color:#1d4ed8;border-color:rgba(37,99,235,0.25)" '
            f'title="D10 Dashamsha score">D10 {_d10:.2f}</span>'
        )

    # KP Sub-Sub-Lord score
    _ssl = _ss.get("kp_ssl_score", 0)
    if _ssl and _ssl > 0.3:
        _enh_pills += (
            f'<span class="pill" style="background:rgba(8,145,178,0.08);'
            f'color:#0369a1;border-color:rgba(8,145,178,0.25)" '
            f'title="KP Sub-Sub-Lord activation">SSL {_ssl:.2f}</span>'
        )

    # Sandhi / Dasha Chidra warning
    if _ss.get("is_sandhi"):
        _enh_pills += (
            f'<span class="pill" style="background:rgba(179,58,46,0.10);'
            f'color:#B33A2E;border-color:rgba(179,58,46,0.30)" '
            f'title="Dasha Sandhi — transition boundary; events may be delayed or erratic">⚠ Sandhi</span>'
        )

    # Nakshatra triggers
    _nak_trigs = _ss.get("nakshatra_triggers", [])
    if _nak_trigs:
        _enh_pills += (
            f'<span class="pill" style="background:rgba(201,168,76,0.08);'
            f'color:#7A5E00;border-color:rgba(201,168,76,0.30)" '
            f'title="Nakshatra transit triggers: {esc(chr(10).join(_nak_trigs[:2]))}">'
            f'★ Nak trigger</span>'
        )

    # Ashtottari lord (if active)
    if _ss.get("ashtottari_active"):
        _ash_lord = _ss.get("ashtottari_lord", "")
        _enh_pills += (
            f'<span class="pill" style="background:rgba(107,91,142,0.08);'
            f'color:#6B5B8E;border-color:rgba(107,91,142,0.30)" '
            f'title="Ashtottari Dasha active">Ash: {esc(_ash_lord)}</span>'
        )

    # Combustion warning
    _comb = _ss.get("combustion_modifier", 0)
    if _comb and _comb < -0.03:
        _enh_pills += (
            f'<span class="pill" style="background:rgba(179,58,46,0.08);'
            f'color:#B33A2E;border-color:rgba(179,58,46,0.25)" '
            f'title="Combustion penalty ({_comb:+.3f})">☀ Combust</span>'
        )

    # Enhancer yoga notes (from astro_enhancer)
    _enh_yoga_notes = _ss.get("enhancer_yoga_notes", [])
    _enh_timing_notes = _ss.get("enhancer_timing_notes", [])
    _enh_note_html = ""
    if _enh_yoga_notes or _enh_timing_notes:
        combined = list(_enh_yoga_notes[:2]) + list(_enh_timing_notes[:1])
        _items = "".join(f"<li style='font-size:11px;margin:2px 0'>{esc(n)}</li>" for n in combined)
        _enh_note_html = (
            f'<div style="margin-top:8px;padding:8px 10px;background:rgba(201,168,76,0.05);'
            f'border-left:2px solid rgba(201,168,76,0.3);border-radius:0 4px 4px 0">'
            f'<ul style="list-style:none;padding:0;margin:0">{_items}</ul></div>'
        )

    # Business tension note (shows when entrepreneurship goal conflicts with employment signal)
    _biz_tension = period.get("business_tension", "")
    _biz_tension_html = ""
    if _biz_tension:
        _biz_tension_html = (
            f'<div style="margin-top:8px;padding:8px 12px;background:rgba(180,83,9,0.07);'
            f'border-left:3px solid #B45309;border-radius:0 6px 6px 0;'
            f'font-size:12px;color:#92400e">'
            f'<strong>⚡ Business tension:</strong> {esc(_biz_tension)}</div>'
        )

    return f"""
<div class="ad-card{card_cls}">
  <div class="ad-row1">
    {_tl_event_badge(et)}
    {crown_html}
    <span class="ad-date">{start} &ndash; {end}</span>
    <span class="ad-tag {tag_cls}">{tag_txt}</span>
    <div class="score-bar-mini">
      <div class="bar-mini-track"><div class="bar-mini-fill" style="width:{bar_w}%;background:{bar_col}"></div></div>
      <span class="score-num">{int(score*100)}%</span>
    </div>
  </div>
  {narrative_section}
  <div class="ad-pills">{pills}{_yoga_badge}{_enh_pills}</div>
  {_d10_row_html}
  {_enh_note_html}
  {_biz_tension_html}
  {_rem_html}
  {pd_html}
</div>"""


_PLANET_EMOJI = {"Sun":"☀️","Moon":"🌙","Mars":"♂️","Mercury":"☿️","Jupiter":"♃","Venus":"♀️","Saturn":"♄","Rahu":"🐉","Ketu":"🔥"}

_TL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Inter:wght@300;400;500;600&display=swap');

:root {
  --bg:          #F7F4EE;
  --surface:     #FFFFFF;
  --surface-warm:#FAF8F3;
  --gold:        #C9A84C;
  --gold-light:  rgba(201,168,76,0.10);
  --gold-mid:    rgba(201,168,76,0.22);
  --deep:        #1A1A2E;
  --mid:         #3D3D5C;
  --muted:       #5F5F7A;  /* darkened for WCAG-AA contrast on cream bg (was #8A8AA8, ~2.7:1) */
  --border:      #E8E2D4;
  --border-soft: #F0ECE2;
  --purple:      #6B5B8E;
  --purple-light:rgba(107,91,142,0.08);
  --green:       #1E7B50;
  --green-light: rgba(30,123,80,0.09);
  --amber:       #B8720A;
  --amber-light: rgba(184,114,10,0.09);
  --red:         #B33A2E;
  --red-light:   rgba(179,58,46,0.09);

  /* ── Strict color semantics (gap-review Phase 3, Gap 19) ───────────────
     One canonical meaning per color family, used everywhere a *sentiment*
     (not an event-category identity) is being shown, so a reader learns the
     mapping once instead of re-learning it per panel:
       --green (var(--green)/#059669 family) = supportive / favorable / high confidence
       --amber (var(--amber)/#D97706 family)  = mixed / moderate / caution
       --red   (var(--red)/#DC2626 family)    = risk / challenging / low confidence
     This applies to: transit net-signal badges, confidence badges (overall
     + per-layer), schema-validation severities, and the executive-summary
     risk cell. It intentionally does NOT apply to _ROADMAP_EVENT_COLORS —
     those are event-*category* identity colors (PROMOTION=green because
     it's positive, but JOB_CHANGE=purple, SKILL_UPGRADE=teal, etc. are
     identity/category colors, not sentiment, so they keep their own
     palette rather than being forced into the 3-color sentiment scale). */
  --radius-sm:   8px;
  --radius-md:   12px;
  --radius-lg:   18px;
  --radius-xl:   24px;
  --shadow-sm:   0 1px 4px rgba(26,26,46,0.06),0 2px 8px rgba(26,26,46,0.04);
  --shadow-md:   0 4px 16px rgba(26,26,46,0.08),0 2px 6px rgba(26,26,46,0.04);
  --shadow-lg:   0 8px 32px rgba(26,26,46,0.12),0 4px 12px rgba(26,26,46,0.06);
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  background:var(--bg);color:var(--deep);line-height:1.7;
  -webkit-font-smoothing:antialiased;min-height:100vh;
}

/* ── Header ─────────────────────────────────────────────────── */
.tl-header{
  background:var(--deep);
  padding:44px 48px 38px;
  position:relative;overflow:hidden;
}
.tl-header::before{
  content:'';position:absolute;top:-80px;right:-40px;
  width:360px;height:360px;border-radius:50%;
  background:radial-gradient(circle,rgba(201,168,76,0.13) 0%,transparent 70%);
  pointer-events:none;
}
.tl-header::after{
  content:'';position:absolute;bottom:-100px;left:18%;
  width:260px;height:260px;border-radius:50%;
  background:radial-gradient(circle,rgba(107,91,142,0.11) 0%,transparent 70%);
  pointer-events:none;
}
.tl-header-inner{
  display:flex;justify-content:space-between;align-items:flex-start;
  max-width:1680px;margin:0 auto;position:relative;z-index:1;gap:24px;
}
.tl-brand{
  font-size:10px;font-weight:600;letter-spacing:4px;
  color:var(--gold);text-transform:uppercase;margin-bottom:12px;opacity:0.85;
}
.tl-name{
  font-family:'Cormorant Garamond',Georgia,'Times New Roman',serif;
  font-size:40px;font-weight:600;color:#FFF;
  margin-bottom:8px;letter-spacing:-0.4px;line-height:1.15;
}
.tl-meta{font-size:12.5px;color:rgba(255,255,255,0.38);letter-spacing:0.4px;line-height:1.9}
.tl-conf{text-align:right;flex-shrink:0;padding-top:4px}
.tl-conf-badge{
  display:inline-block;padding:5px 18px;border-radius:30px;
  font-size:11px;font-weight:600;letter-spacing:0.6px;margin-bottom:6px;
}
.conf-strong{background:var(--green-light);color:var(--green);border:1px solid rgba(30,123,80,0.28)}
.conf-moderate{background:var(--amber-light);color:var(--amber);border:1px solid rgba(184,114,10,0.28)}
.conf-mismatch{background:rgba(255,255,255,0.07);color:rgba(255,255,255,0.42);border:1px solid rgba(255,255,255,0.12);font-size:10px}
.tl-conf-sub{font-size:10.5px;color:rgba(255,255,255,0.28);letter-spacing:0.5px;text-transform:uppercase}
/* Phase 2 (2026-07-05, item #12): per-layer confidence hierarchy — replaces
   the single "Moderate" badge's implicit claim that every layer of the
   prediction (birth time, dasha math, KP, D10, D9, transit, narrative) is
   equally reliable. Each layer degrades independently (e.g. an unknown birth
   time hurts KP/D10 hard but barely touches the mechanical dasha dates). */
.tl-layer-conf{margin-top:10px;display:flex;flex-direction:column;gap:5px;align-items:flex-end}
.tl-layer-row{display:flex;align-items:center;gap:7px;font-size:10.5px}
.tl-layer-name{color:rgba(255,255,255,0.42);letter-spacing:0.2px;min-width:74px;text-align:right}
.tl-layer-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.tl-layer-dot.high{background:var(--green)}
.tl-layer-dot.moderate{background:var(--amber)}
.tl-layer-dot.moderate-low{background:var(--amber)}
.tl-layer-dot.low{background:var(--red)}
.tl-layer-label{font-weight:600;letter-spacing:0.3px}
.tl-layer-label.high{color:var(--green)}
.tl-layer-label.moderate{color:var(--amber)}
.tl-layer-label.moderate-low{color:var(--amber)}
.tl-layer-label.low{color:var(--red)}
.tl-layer-divider{width:100%;height:1px;background:rgba(255,255,255,0.12);margin:4px 0}
.tl-layer-caption{font-size:9.5px;color:rgba(255,255,255,0.32);max-width:200px;text-align:right;line-height:1.4}

/* Phase 2 (2026-07-05, item #18): executive summary panel — a single
   scannable strip answering "what do I do with this report" before the
   reader has to piece it together from 10+ roadmap cards. */
.tl-exec-panel{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:14px;background:#FFFFFF;border:1px solid var(--border);border-radius:14px;
  padding:18px 20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(15,23,42,0.04);
}
.tl-exec-cell{border-left:3px solid var(--border);padding-left:12px}
.tl-exec-cell.active{border-left-color:var(--green)}
.tl-exec-cell.risk{border-left-color:var(--red)}
.tl-exec-cell.foreign{border-left-color:#7C3AED}
.tl-exec-cell.comp{border-left-color:#2563EB}
.tl-exec-cell.role{border-left-color:#C9A84C}
.tl-exec-label{font-size:10.5px;color:var(--mid);letter-spacing:0.5px;text-transform:uppercase;margin-bottom:4px}
.tl-exec-val{font-size:14.5px;font-weight:600;color:var(--deep);line-height:1.35}
.tl-exec-sub{font-size:11.5px;color:var(--mid);margin-top:2px}

/* Phase 3 (2026-07-05, Gap 20): compact cross-period comparison table. */
.rmap-cmp-wrap{
  background:#FFFFFF;border:1px solid var(--border);border-radius:14px;
  padding:16px 20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(15,23,42,0.04);
  overflow-x:auto;
}
.rmap-cmp-title{font-size:13px;font-weight:600;color:var(--deep);letter-spacing:0.2px;margin-bottom:10px}
.rmap-cmp-table{width:100%;border-collapse:collapse;font-size:12.5px}
.rmap-cmp-table th{
  text-align:left;color:var(--mid);font-weight:600;font-size:10.5px;
  letter-spacing:0.4px;text-transform:uppercase;padding:6px 10px;
  border-bottom:1px solid var(--border);
}
.rmap-cmp-table td{padding:7px 10px;border-bottom:1px solid var(--border-soft);color:var(--deep)}
.rmap-cmp-row-now td{background:var(--gold-light);font-weight:600}
/* Gap-review (4th round, Gaps 11/19): retro-validation collapsible table */
.rmap-cmp-retro{margin-top:14px;}
.rmap-cmp-retro-toggle{cursor:pointer;list-style:none;user-select:none;}
.rmap-cmp-retro-toggle::-webkit-details-marker{display:none;}
.rmap-cmp-retro-toggle::before{content:"▸ ";}
details[open]>.rmap-cmp-retro-toggle::before{content:"▾ ";}
.rmap-cmp-retro table{margin-top:10px;}
.rmap-cmp-note{font-size:12px;color:var(--muted);line-height:1.5;margin:6px 0 2px;font-style:italic;}

/* Gap-review (4th round, Gap 14): visible schema/audit panel */
.tl-audit-panel{
  background:#FFFFFF;border:1px solid var(--border);border-radius:14px;
  padding:16px 20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(15,23,42,0.04);
}
.tl-audit-title{font-size:13px;font-weight:600;color:var(--deep);letter-spacing:0.2px;margin-bottom:10px}
.tl-audit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:6px 20px}
.tl-audit-row{display:flex;justify-content:space-between;font-size:12px;padding:4px 0;border-bottom:1px solid var(--border-soft)}
.tl-audit-name{color:var(--mid)}
.tl-audit-status{font-weight:700}
.tl-audit-detail{margin-top:10px;font-size:11px;color:var(--muted);line-height:1.7}

/* ── Content ─────────────────────────────────────────────────── */
/* GAP FIX (2026-07-05): widened 1360→1680px so the layout uses far more of
   the viewport on standard/wide monitors instead of leaving large empty
   margins either side of a narrow centered column — the reported "left
   hand side lots of white space" issue. The sidebar (Snapshot/Planetary
   Strength/D10) now sits much closer to the true left edge of the window. */
.content{max-width:1680px;margin:0 auto;padding:28px 20px 72px}
.content-footer{max-width:1680px;margin:0 auto;padding:16px 20px 44px}
.tl-footer-line{font-size:12px;font-weight:600;color:var(--muted);text-align:center;letter-spacing:.3px}
.tl-footer-note{font-size:11.5px;color:var(--muted);text-align:center;max-width:720px;margin:6px auto 0;line-height:1.55}
/* ── Glossary ─────────────────────────────────────────────────── */
.glossary-panel{max-width:1680px;margin:8px auto 0;padding:16px 20px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm)}
.glossary-toggle{cursor:pointer;list-style:none;user-select:none;display:flex;align-items:center;gap:8px}
.glossary-toggle::-webkit-details-marker{display:none}
.glossary-toggle::before{content:"▸";color:var(--gold);font-size:13px}
details[open]>.glossary-toggle::before{content:"▾"}
.glossary-title{display:inline;font-family:'Cormorant Garamond',serif;font-size:1.15rem;font-weight:700;color:var(--deep)}
.gloss-grid{margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px 22px}
.gloss-item{border-left:2px solid var(--gold-mid);padding-left:11px}
.gloss-term{font-size:12.5px;font-weight:700;color:var(--deep);margin-bottom:2px}
.gloss-def{font-size:12px;color:var(--mid);line-height:1.5}

/* ── Dashboard layout: sticky sidebar + main column ───────────── */
.content-grid{display:grid;grid-template-columns:380px minmax(0,1fr);gap:26px;align-items:start}
.tl-sidebar{
  position:sticky;top:20px;display:flex;flex-direction:column;gap:20px;
  max-height:calc(100vh - 40px);overflow-y:auto;overflow-x:hidden;
  scrollbar-width:thin;
}
.tl-sidebar::-webkit-scrollbar{width:5px}
.tl-sidebar::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.tl-sidebar>*{margin-bottom:0 !important}
.tl-sidebar-label{
  font-size:10px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;
  color:var(--muted);padding:0 2px;
}
.tl-main{min-width:0}
.tl-main>*:first-child{margin-top:0}

/* Sidebar-specific outcome bar: stack vertically instead of the horizontal strip */
.tl-sidebar .outcome-bar{
  flex-direction:column;align-items:stretch;gap:14px;padding:20px 22px;
}
.tl-sidebar .outcome-bar>div{
  flex:none;padding:0 0 14px;border-right:none;border-bottom:1px solid var(--border-soft);
}
.tl-sidebar .outcome-bar>div:first-child{padding-left:0}
.tl-sidebar .outcome-bar>div:last-child{padding-bottom:0;border-bottom:none}

@media (max-width:1080px){
  .content-grid{grid-template-columns:1fr}
  .tl-sidebar{position:static;max-height:none;overflow:visible}
  .tl-sidebar{flex-direction:row;flex-wrap:wrap}
  .tl-sidebar>*{flex:1 1 260px}
  .tl-sidebar .outcome-bar{flex-direction:row;align-items:stretch}
  .tl-sidebar .outcome-bar>div{flex:1;padding:4px 24px;border-right:1px solid var(--border-soft);border-bottom:none}
  .tl-sidebar .outcome-bar>div:first-child{padding-left:0}
  .tl-sidebar .outcome-bar>div:last-child{padding-right:0;border-right:none}
}
@media (max-width:640px){
  .tl-sidebar{flex-direction:column}
  .tl-sidebar>*{flex:1 1 auto}
}

/* ── Outcome bar ─────────────────────────────────────────────── */
.outcome-bar{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius-lg);padding:20px 28px;
  display:flex;align-items:stretch;margin-bottom:32px;
  box-shadow:var(--shadow-sm);overflow:hidden;
}
.outcome-bar>div{
  flex:1;min-width:0;padding:4px 24px;
  border-right:1px solid var(--border-soft);
}
.outcome-bar>div:first-child{padding-left:0}
.outcome-bar>div:last-child{padding-right:0;border-right:none}
.outcome-label{
  font-size:10px;font-weight:600;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--muted);margin-bottom:4px;
}
.outcome-val{
  font-size:14.5px;font-weight:600;color:var(--deep);
  line-height:1.35;overflow-wrap:break-word;word-break:break-word;
}

/* ── MD group ─────────────────────────────────────────────────── */
.md-group{
  margin-bottom:28px;border-radius:var(--radius-xl);
  overflow:hidden;box-shadow:var(--shadow-md);border:1px solid var(--border);
}
.md-head{
  background:linear-gradient(135deg,var(--deep) 0%,#252540 100%);
  padding:22px 28px;display:flex;align-items:center;gap:18px;
}
.md-planet-badge{
  width:52px;height:52px;border-radius:50%;
  background:rgba(201,168,76,0.14);border:2px solid rgba(201,168,76,0.38);
  display:flex;align-items:center;justify-content:center;
  font-size:22px;flex-shrink:0;
}
.md-title{
  font-family:'Cormorant Garamond',Georgia,serif;
  font-size:21px;font-weight:600;color:#FFF;margin-bottom:2px;
}
.md-dates{font-size:12px;color:rgba(255,255,255,0.40);font-weight:400}
.md-score-pill{
  margin-left:auto;
  background:rgba(201,168,76,0.13);color:var(--gold);
  border:1px solid rgba(201,168,76,0.28);border-radius:30px;
  padding:5px 16px;font-size:12px;font-weight:600;white-space:nowrap;flex-shrink:0;
}
.md-narrative{
  background:var(--surface-warm);border-bottom:1px solid var(--border-soft);
  padding:14px 28px;font-size:13.5px;color:var(--mid);
  line-height:1.75;font-style:italic;
}
.md-narrative p{margin-bottom:6px}
.md-narrative p:last-child{margin-bottom:0}
.ad-list{background:var(--surface)}

/* ── AD card ─────────────────────────────────────────────────── */
.ad-card{
  border-top:1px solid var(--border-soft);
  padding:24px 28px;position:relative;
  transition:background 0.18s ease;
}
.ad-card:first-child{border-top:none}
.ad-card:hover{background:#FEFCF7}
.ad-card.is-past{opacity:0.68}
.ad-card.is-current{
  background:linear-gradient(135deg,rgba(201,168,76,0.05) 0%,rgba(255,255,255,1) 55%);
  border-left:3px solid var(--gold);
}
.ad-card.is-current::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,rgba(201,168,76,0.6),transparent);
}

/* ── AD row 1 ────────────────────────────────────────────────── */
.ad-row1{
  display:flex;align-items:center;gap:10px;
  margin-bottom:16px;flex-wrap:wrap;
}
.ad-date{font-size:13px;color:var(--mid);font-weight:500;margin-left:2px}
.ad-tag{
  font-size:10px;font-weight:700;padding:2px 10px;
  border-radius:4px;letter-spacing:0.5px;flex-shrink:0;
}
.tag-past{background:#EEE9E0;color:var(--muted)}
.tag-current{background:rgba(201,168,76,0.14);color:#7A5E00}
.tag-future{background:var(--purple-light);color:var(--purple)}

/* ── Event badges ────────────────────────────────────────────── */
.ad-badge{
  font-size:10px;font-weight:700;padding:3px 10px;
  border-radius:6px;letter-spacing:0.4px;flex-shrink:0;
}
.et-PROMOTION{background:var(--green-light);color:var(--green);border:1px solid rgba(30,123,80,0.22)}
.et-LEADERSHIP_EXPANSION{background:var(--purple-light);color:var(--purple);border:1px solid rgba(107,91,142,0.25)}
.et-JOB_CHANGE{background:var(--amber-light);color:var(--amber);border:1px solid rgba(184,114,10,0.28)}
.et-INCOME_INFLECTION{background:var(--green-light);color:#1A6B42;border:1px solid rgba(30,123,80,0.18)}
.et-NETWORKING_OPPORTUNITY{background:rgba(0,110,180,0.08);color:#005A8E;border:1px solid rgba(0,110,180,0.18)}
.et-GROWTH{background:var(--purple-light);color:#52438A;border:1px solid rgba(107,91,142,0.22)}
.et-STABILITY{background:var(--border-soft);color:var(--muted);border:1px solid var(--border)}
.et-DEFAULT{background:var(--border-soft);color:var(--muted);border:1px solid var(--border)}
.et-BREAKTHROUGH{background:rgba(201,168,76,0.12);color:#7A5E00;border:1px solid rgba(201,168,76,0.35)}
.et-SALARY_HIKE{background:var(--green-light);color:#1A6B42;border:1px solid rgba(30,123,80,0.22)}
.et-AUTHORITY_SHIFT{background:rgba(184,114,10,0.10);color:#92400e;border:1px solid rgba(184,114,10,0.28)}
.et-RISK_PERIOD{background:var(--red-light);color:var(--red);border:1px solid rgba(179,58,46,0.28)}
.et-CALIBRATION{background:rgba(100,116,139,0.08);color:#475569;border:1px solid rgba(100,116,139,0.22)}
.et-ENTREPRENEURSHIP_WINDOW{background:rgba(180,83,9,0.10);color:#92400e;border:1px solid rgba(180,83,9,0.30)}
.et-EQUITY_EVENT{background:rgba(3,105,161,0.08);color:#075985;border:1px solid rgba(3,105,161,0.25)}
.et-LATERAL_MOVE{background:var(--purple-light);color:#4C1D95;border:1px solid rgba(109,40,217,0.25)}
.et-SANDHI_PERIOD{background:var(--red-light);color:#7f1d1d;border:1px solid rgba(153,27,27,0.30)}
.et-CAREER_PLATEAU{background:rgba(180,130,0,0.09);color:#7A5E00;border:1px solid rgba(180,130,0,0.28)}
.et-STAGNATION{background:rgba(100,100,100,0.09);color:#4B5563;border:1px solid rgba(100,100,100,0.28)}
.et-CAREER_THROUGH_PARTNERSHIP{background:rgba(0,110,180,0.08);color:#005A8E;border:1px solid rgba(0,110,180,0.22)}

/* ── Score bar ───────────────────────────────────────────────── */
.score-bar-mini{display:flex;align-items:center;gap:10px;margin-left:auto;flex-shrink:0}
.bar-mini-track{width:90px;height:5px;background:var(--border-soft);border-radius:3px;overflow:hidden}
.bar-mini-fill{height:100%;border-radius:3px}
.score-num{font-size:12px;font-weight:600;color:var(--mid);min-width:36px;text-align:right}

/* ── LLM Narrative HTML ──────────────────────────────────────── */
.llm-narrative{
  background:var(--surface-warm);border:1px solid var(--border-soft);
  border-radius:var(--radius-md);padding:22px 26px;
  margin-bottom:16px;font-size:14px;line-height:1.78;color:var(--mid);
}
.llm-narrative h3,.llm-narrative h4{
  font-family:'Cormorant Garamond',Georgia,serif;
  font-size:16px;font-weight:600;color:var(--deep);
  margin:18px 0 7px;padding-bottom:5px;
  border-bottom:1px solid var(--border-soft);letter-spacing:0.15px;
}
.llm-narrative h4:first-child,.llm-narrative h3:first-child{margin-top:0}
.llm-narrative p{margin-bottom:10px;color:var(--mid);font-size:14px}
.llm-narrative p:last-child{margin-bottom:0}
.llm-narrative strong{color:var(--deep);font-weight:600}
.llm-narrative ul{margin:8px 0 10px 18px;color:var(--mid)}
.llm-narrative li{margin-bottom:6px;font-size:13.5px;line-height:1.65}
.llm-narrative li::marker{color:var(--gold)}
.llm-layer-title{
  font-family:'Cormorant Garamond',Georgia,serif;font-size:13px;font-weight:700;
  text-transform:uppercase;letter-spacing:0.9px;color:var(--gold);
  margin:0 0 10px;padding-bottom:0;border-bottom:none;
}
.llm-narrative-astro{
  background:var(--surface);border-style:dashed;
}
.llm-narrative-astro .llm-layer-title{color:var(--mid)}

/* Fallback plain hint */
.ad-insight{
  font-size:13.5px;color:var(--muted);margin-bottom:14px;
  font-style:italic;line-height:1.68;
}

/* ── Pills ───────────────────────────────────────────────────── */
.ad-pills{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.pill{
  font-size:11px;padding:3px 10px;border-radius:6px;
  background:var(--surface-warm);border:1px solid var(--border);
  color:var(--muted);font-weight:500;
}
.pill-house{border-color:rgba(107,91,142,0.25);color:var(--purple);background:var(--purple-light)}
.pill-kp{border-color:rgba(201,168,76,0.3);color:var(--amber);background:var(--gold-light)}
.pill-jaimini{border-color:rgba(30,123,80,0.22);color:var(--green);background:var(--green-light)}
.pill-remedy{border-color:var(--border);color:var(--muted)}
.pill-salary{background:#f0fdf4;color:#15803d;border-color:#86efac;font-weight:600}
.pill-nearmiss{border-color:rgba(179,58,46,0.22);color:var(--red);background:var(--red-light)}

/* ── PD toggle & grid ────────────────────────────────────────── */
.pd-toggle{
  display:inline-flex;align-items:center;gap:6px;
  font-size:11.5px;font-weight:600;color:var(--gold);
  cursor:pointer;margin-top:10px;padding:5px 14px;
  border-radius:7px;border:1px solid var(--gold-mid);
  background:var(--gold-light);
  transition:background 0.15s,border-color 0.15s;
  user-select:none;letter-spacing:0.3px;
}
.pd-toggle:hover{background:rgba(201,168,76,0.17);border-color:rgba(201,168,76,0.38)}
.pd-toggle-icon{font-size:10px;transition:transform 0.2s}
.pd-toggle[aria-expanded="true"] .pd-toggle-icon{transform:rotate(90deg)}
.pd-list{margin-top:14px;display:grid;gap:8px}
.pd-item{
  background:var(--surface-warm);border:1px solid var(--border-soft);
  border-radius:var(--radius-sm);padding:12px 16px;
  display:grid;grid-template-columns:100px 1fr;gap:8px 14px;align-items:start;
}
.pd-header{display:flex;flex-direction:column;gap:3px}
.pd-chip{font-weight:700;color:var(--deep);font-size:13px}
.pd-dates{color:var(--muted);font-size:11px;font-family:'SF Mono','Fira Code',Consolas,monospace}
.pd-score{margin-left:auto;font-size:11px;font-weight:700;color:var(--gold,#C9A84C);
  background:var(--gold-light,rgba(201,168,76,0.12));border-radius:10px;padding:2px 8px;}
.pd-llm{font-size:13px;color:var(--mid);line-height:1.62}
.pd-llm p{margin:0}
.pd-llm strong{color:var(--deep)}
.pd-note{font-size:12.5px;color:var(--muted);line-height:1.58;font-style:italic}

/* ── Empty state ─────────────────────────────────────────────── */
.empty-state{text-align:center;padding:72px 24px;color:var(--muted);font-size:15px}

/* ── Primary Opportunity highlight (FIX 8) ──────────────────── */
.ad-card.is-primary-opp{
  background:linear-gradient(135deg,rgba(201,168,76,0.07) 0%,rgba(255,255,255,1) 60%);
  border-left:3px solid var(--gold);
  position:relative;
}
.ad-card.is-primary-opp::after{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,rgba(201,168,76,0.75),transparent 70%);
}
.opp-crown{
  display:inline-flex;align-items:center;gap:5px;
  font-size:10.5px;font-weight:700;color:#7A5E00;
  background:rgba(201,168,76,0.16);border:1px solid rgba(201,168,76,0.38);
  border-radius:6px;padding:2px 10px;flex-shrink:0;letter-spacing:0.35px;
}

/* ── Retro-match badge ──────────────────────────────────────── */
.retro-badge{display:inline-flex;align-items:center;gap:5px;
  font-size:10.5px;font-weight:600;padding:3px 10px;border-radius:20px;
  background:rgba(5,150,105,0.10);color:#065f46;border:1px solid rgba(5,150,105,0.28);}
.retro-badge-warn{background:rgba(217,119,6,0.10);color:#92400e;border-color:rgba(217,119,6,0.28);}

/* ── Empty timeline fallback ────────────────────────────────── */
.tl-empty{text-align:center;padding:64px 32px;color:#94a3b8;
  border:2px dashed var(--border);border-radius:16px;margin:32px 0;}
.tl-empty-icon{font-size:48px;margin-bottom:12px;}
.tl-empty-title{font-size:1.15rem;font-weight:600;color:#475569;margin-bottom:8px;}

/* ── Mahadasha group wrapper ────────────────────────────────── */
.md-group{margin-bottom:32px;}
.md-head{display:flex;align-items:center;gap:12px;padding:10px 16px;
  background:linear-gradient(135deg,#1A1A2E 0%,#2d2d44 100%);
  border-radius:12px 12px 0 0;border:2px solid var(--gold);border-bottom:none;}
.md-planet-badge{width:36px;height:36px;border-radius:50%;background:rgba(196,155,66,.2);
  display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}
.md-title{font-family:'Cormorant Garamond',serif;font-size:1.05rem;font-weight:700;
  color:var(--gold);letter-spacing:0.3px;}
.md-dates{font-size:11.5px;color:rgba(255,255,255,0.45);margin-top:1px;}
.md-score-pill{margin-left:auto;background:rgba(196,155,66,.18);color:var(--gold);
  border:1px solid rgba(196,155,66,.35);border-radius:20px;
  font-size:11px;font-weight:600;padding:3px 10px;white-space:nowrap;}
.ad-list{border:2px solid var(--border);border-top:none;
  border-radius:0 0 12px 12px;overflow:hidden;}
.ad-list .tl-card{border-radius:0;border-bottom:1px solid var(--border);}
.ad-list .tl-card:last-child{border-bottom:none;}

/* ── Annual calendar view ───────────────────────────────────── */
.cal-section{margin:0 0 28px;}
.cal-heading{font-family:'Cormorant Garamond',serif;font-size:1.25rem;font-weight:700;
  color:#1A1A2E;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--gold);}
.cal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:12px;}
.cal-year-card{background:#fff;border:1px solid var(--border);border-radius:10px;
  padding:12px 14px;transition:box-shadow 0.2s;}
.cal-year-card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.08);}

/* ── 3-Year Career Roadmap (merged event + transit, calendar-anchored) ── */
.rmap-section{margin-bottom:32px;}
.rmap-sub{font-size:12.5px;color:var(--muted);line-height:1.6;margin:-6px 0 18px;max-width:640px;}
.rmap-years-list{display:flex;flex-direction:column;gap:28px;}
.rmap-year-block{
  background:#fff;border:1px solid var(--border);border-radius:var(--radius-lg,14px);
  padding:22px 24px;box-shadow:var(--shadow-sm);
}
.rmap-year-divider{height:1px;background:var(--border);margin:20px 0;border:none;}
.rmap-node{position:relative;z-index:1;display:flex;flex-direction:column;align-items:flex-start;width:100%;}
.rmap-node-marker{
  width:40px;height:40px;border-radius:50%;background:#fff;border:3px solid var(--border);
  display:flex;align-items:center;justify-content:center;margin-bottom:14px;
  box-shadow:0 2px 6px rgba(26,26,46,0.10);position:relative;flex-shrink:0;
}
.rmap-node-year{font-size:11px;font-weight:800;color:var(--deep);}
.rmap-node-now-tag{
  position:absolute;top:-10px;right:-14px;background:var(--gold);color:#1A1A2E;
  font-size:8px;font-weight:800;letter-spacing:0.5px;padding:2px 6px;border-radius:8px;
  box-shadow:0 1px 4px rgba(0,0,0,0.15);
}
.rmap-node-now .rmap-node-marker{border-width:3px;box-shadow:0 0 0 4px rgba(201,168,76,0.15);}
.rmap-node-past-tag{
  position:absolute;top:-10px;right:-16px;background:#94a3b8;color:#fff;
  font-size:8px;font-weight:800;letter-spacing:0.5px;padding:2px 6px;border-radius:8px;
  box-shadow:0 1px 4px rgba(0,0,0,0.15);white-space:nowrap;
}
.rmap-node-past .rmap-node-card{opacity:0.78;}
.rmap-node-past .rmap-node-marker{border-style:dashed;}
.rmap-node-card{
  background:#fff;border:1px solid var(--border);border-radius:var(--radius-md);
  padding:16px 18px;width:100%;box-shadow:var(--shadow-sm);
}
.rmap-node-weather{display:flex;align-items:center;gap:6px;margin-bottom:8px;}
.rmap-weather-emoji{font-size:18px;line-height:1;}
.rmap-weather-label{font-size:11px;font-weight:700;color:var(--muted);letter-spacing:0.3px;text-transform:uppercase;}
.rmap-node-event{font-family:'Cormorant Garamond',Georgia,serif;font-size:17px;font-weight:700;margin-bottom:3px;}
.rmap-node-event-secondary{font-size:10.5px;font-weight:600;letter-spacing:0.4px;text-transform:uppercase;color:var(--muted);margin-bottom:6px;}
.rmap-node-dasha{font-size:11px;color:var(--muted);margin-bottom:6px;}
.rmap-node-pd-lord{font-weight:700;color:var(--deep);}
.rmap-node-why{font-size:12px;color:var(--mid);line-height:1.55;margin-bottom:10px;font-style:italic;}
.rmap-node-scorebar{height:6px;border-radius:3px;background:var(--border-soft);overflow:hidden;margin-top:8px;}
.rmap-node-scorefill{height:100%;border-radius:3px;}
.rmap-node-scoreval{font-size:10.5px;color:var(--muted);margin:4px 0 10px;}
/* Gap-review (4th round, Gap 12): multi-score event matrix */
.rmap-matrix{display:flex;flex-direction:column;gap:4px;margin:2px 0 10px;padding:8px 10px;
  background:var(--surface-warm);border-radius:8px;}
.rmap-matrix-row{display:flex;align-items:center;gap:8px;font-size:10.5px;}
.rmap-matrix-name{min-width:66px;color:var(--mid);flex-shrink:0;}
.rmap-matrix-track{flex:1;height:5px;background:var(--border-soft);border-radius:3px;overflow:hidden;}
.rmap-matrix-fill{height:100%;background:linear-gradient(90deg,var(--gold),#8A6D2F);border-radius:3px;}
.rmap-matrix-pct{min-width:30px;text-align:right;color:var(--deep);font-weight:600;}
.rmap-node-foreign{font-size:10.5px;color:var(--ocean2,#38bdf8);margin:0 0 10px;}
.rmap-node-net{
  display:inline-block;font-size:10.5px;font-weight:700;padding:3px 10px;
  border-radius:10px;margin-bottom:12px;
}
.rmap-signals{display:flex;flex-direction:column;gap:9px;padding-top:10px;border-top:1px solid var(--border-soft);}
.rmap-signal{display:flex;align-items:flex-start;gap:7px;}
.rmap-signal-dot{width:8px;height:8px;border-radius:50%;margin-top:4px;flex-shrink:0;}
.rmap-signal-icon{font-size:12px;flex-shrink:0;margin-top:1px;}
.rmap-signal-text{font-size:11.5px;color:var(--mid);line-height:1.5;}
.rmap-signal-text strong{color:var(--deep);font-weight:600;}

/* Gap-review (4th round, Gap 17): PD micro-timing panel */
.rmap-pd-panel{background:var(--surface-warm);border:1px solid var(--border-soft);border-radius:var(--radius-md);padding:12px 18px;}
.rmap-pd-row{display:flex;align-items:center;gap:10px;font-size:11.5px;padding:4px 0;flex-wrap:wrap;}
.rmap-pd-lord{font-weight:700;color:var(--deep);min-width:110px;}
.rmap-pd-range{color:var(--muted);min-width:150px;}
.rmap-pd-pct{font-weight:700;color:var(--gold);min-width:36px;}
.rmap-pd-use{color:var(--mid);flex:1;min-width:180px;}

/* User-reported gap fix (2026-07): within-year transit sub-windows */
.rmap-subwin-panel{background:var(--surface-warm);border:1px solid var(--border-soft);border-radius:var(--radius-md);padding:12px 18px;}
.rmap-subwin-row{display:flex;align-items:center;gap:14px;font-size:11.5px;padding:3px 0;flex-wrap:wrap;}
.rmap-subwin-range{font-weight:600;color:var(--deep);min-width:170px;}
.rmap-subwin-detail{color:var(--mid);}

/* Gap-review (4th round, Gap 10): D24/D60 layer-relevance note */
.rmap-astro-layer-note{font-size:11px;color:var(--muted);line-height:1.6;margin-top:8px;
  padding-top:8px;border-top:1px dashed var(--border);font-style:italic;}

/* ── Career Outlook + Astrological Basis, integrated into each year block ── */
.rmap-year-subhead{
  font-size:10.5px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
  color:var(--muted);margin-bottom:8px;
}
.rmap-year-narrative{
  background:var(--surface-warm);border:1px solid var(--border-soft);border-radius:var(--radius-md);
  padding:18px 22px;margin-bottom:16px;
}
.rmap-year-narrative p{font-size:13.5px;color:var(--mid);line-height:1.78;margin-bottom:10px;}
.rmap-year-narrative p:last-child{margin-bottom:0;}
.rmap-year-narrative strong{color:var(--deep);font-weight:600;}
.rmap-year-astro{
  background:rgba(107,91,142,0.05);border:1px solid rgba(107,91,142,0.18);border-radius:var(--radius-md);
  padding:18px 22px;
}
.rmap-year-astro p{font-size:13px;color:var(--mid);line-height:1.72;margin-bottom:9px;}
.rmap-year-astro p:last-child{margin-bottom:0;}
.rmap-year-astro strong{color:var(--purple);font-weight:600;}
.rmap-year-astro ul{margin:6px 0 10px 18px;}
.rmap-year-astro li{font-size:12.5px;color:var(--mid);line-height:1.6;margin-bottom:5px;}
.rmap-year-astro li::marker{color:var(--purple);}

/* ── Per-period KP cusp chain (Phase-1 fix, 2026-07-05) ────────── */
.rmap-kp-panel{
  background:rgba(30,123,80,0.05);border:1px solid rgba(30,123,80,0.18);border-radius:var(--radius-md);
  padding:16px 22px;
}
.rmap-kp-row{display:flex;align-items:baseline;gap:10px;font-size:12.5px;color:var(--mid);
  line-height:1.7;padding:2px 0;flex-wrap:wrap;}
.rmap-kp-house{font-weight:700;color:var(--green);min-width:32px;}
.rmap-kp-theme{color:var(--muted);font-style:italic;min-width:150px;}
.rmap-kp-chain{color:var(--deep);font-weight:500;}
.rmap-kp-verdict{font-size:12px;font-weight:700;margin-top:10px;padding-top:8px;
  border-top:1px solid rgba(30,123,80,0.18);}
/* Gap-review (4th round, Gap 7): event-specific KP verdicts */
.rmap-kp-event-verdicts{margin-top:10px;padding-top:8px;border-top:1px solid rgba(30,123,80,0.18);}
.rmap-kp-ev-row{display:flex;align-items:center;gap:10px;font-size:12px;padding:3px 0;}
.rmap-kp-ev-name{min-width:90px;color:var(--deep);font-weight:600;}
.rmap-kp-ev-verdict{font-weight:700;min-width:80px;}
.rmap-kp-ev-detail{color:var(--muted);font-size:11px;}

/* ── D10 per-period verdict (gap review, Gap 5) ─────────────────── */
.rmap-d10-verdict{
  background:rgba(201,168,76,0.06);border:1px solid rgba(201,168,76,0.2);border-radius:var(--radius-md);
  padding:14px 20px;
}
.rmap-d10-verdict p{font-size:12.5px;color:var(--mid);line-height:1.7;}
/* Gap-review (4th round, Gap 8): structured D10 factor table */
.rmap-d10-manifestation{font-size:12.5px;color:var(--mid);margin-top:8px;line-height:1.6;}
.rmap-d10-manifestation strong{color:var(--deep);}
.rmap-d10-final-verdict{font-size:12px;font-weight:700;margin-top:8px;padding-top:8px;
  border-top:1px solid rgba(201,168,76,0.2);}

/* ── Contradiction panel (Phase 2, item #17) ───────────────────── */
.rmap-cx-panel{
  background:var(--surface-warm);border:1px solid var(--border-soft);border-radius:var(--radius-md);
  padding:16px 22px;
}
.rmap-cx-row{display:flex;align-items:baseline;gap:10px;font-size:12.5px;line-height:1.65;
  padding:3px 0;flex-wrap:wrap;}
.rmap-cx-label{font-weight:700;min-width:82px;flex-shrink:0;}
.rmap-cx-support .rmap-cx-label{color:var(--green,#1E7B50);}
.rmap-cx-block .rmap-cx-label{color:var(--red,#B33A2E);}
.rmap-cx-items{color:var(--mid);}
.rmap-cx-net{font-size:12.5px;color:var(--deep);font-weight:600;margin-top:8px;
  padding-top:8px;border-top:1px solid var(--border-soft);}
.rmap-cx-confidence{font-size:12px;color:var(--mid);margin-top:6px;line-height:1.6;}
.rmap-cx-confidence strong{color:var(--deep);}

/* ── Actionability layer (HTML uplift, 2026-07-07) ─────────────── */
.rmap-action-layer{
  margin-top:12px;padding:12px 18px;
  background:var(--green-light);border-left:3px solid var(--green);
  border-radius:0 var(--radius-sm,8px) var(--radius-sm,8px) 0;
}
.rmap-action-layer .rmap-year-subhead{color:var(--green,#1E7B50);}
.rmap-action-layer ul{margin:6px 0 0;padding-left:18px;font-size:12.5px;color:var(--deep);line-height:1.6;}
.rmap-action-layer li{margin:2px 0;}

/* ── Parent / Family Guidance panel (Gap 1 + Gap 5, 2026-07-07) ── */
.rmap-family-panel{
  margin-top:12px;padding:12px 18px;
  background:var(--purple-light);border-left:3px solid var(--purple);
  border-radius:0 var(--radius-sm,8px) var(--radius-sm,8px) 0;
}
.rmap-family-panel .rmap-year-subhead{color:var(--purple,#6B5B8E);}
.rmap-family-headline{font-weight:700;font-size:13px;color:var(--deep);margin-top:4px;}
.rmap-family-body{font-size:12.5px;color:var(--mid);line-height:1.6;margin:4px 0 0;}
.rmap-family-risk{margin-top:10px;display:grid;gap:4px;
  background:var(--surface,#fff);border:1px solid var(--border-soft);
  border-radius:6px;padding:8px 12px;}
.rmap-family-risk-row{display:flex;justify-content:space-between;gap:12px;
  font-size:12px;padding:2px 0;}
.rmap-family-risk-row span:first-child{font-weight:700;color:var(--deep);}
.rmap-family-risk-row span:last-child{color:var(--mid);text-align:right;}

/* ── Audience-separation labels (Gap 1, 2026-07-07) ────────────── */
/* Marks the three distinct audiences (A. practical / B. family / C. audit,
   the latter being the .rmap-evidence-toggle summary text) so the reader
   can see at a glance which lens they are reading, per-card. */
.rmap-audience-label{
  font-size:10.5px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;
  color:var(--gold,#C9A84C);margin-top:14px;margin-bottom:2px;
}
.rmap-audience-label-b{color:var(--purple,#6B5B8E);}

/* ── Why this event / why not another (Gap 2, 2026-07-07) ─────────── */
.rmap-why-panel{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.rmap-why-col{background:var(--surface-warm);border:1px solid var(--border-soft);
  border-radius:var(--radius-sm,8px);padding:12px 14px;}
.rmap-why-against{border-left:3px solid var(--purple,#6B5B8E);}
.rmap-why-title{font-size:11.5px;font-weight:700;color:var(--deep);margin-bottom:6px;}
.rmap-why-col ul{margin:0;padding-left:18px;font-size:12px;color:var(--mid);line-height:1.55;}
.rmap-why-col li{margin:3px 0;}
@media (max-width:640px){.rmap-why-panel{grid-template-columns:1fr;}}

/* ── Verdict-first collapsible evidence (Gap-review Phase 3, Gap 17) ──── */
.rmap-evidence{margin-top:14px;}
.rmap-evidence-toggle{
  cursor:pointer;list-style:none;font-size:12.5px;font-weight:600;
  color:var(--mid);letter-spacing:0.2px;padding:6px 0;user-select:none;
}
.rmap-evidence-toggle::-webkit-details-marker{display:none;}
.rmap-evidence-toggle::before{content:"▸ ";display:inline-block;transition:transform 0.15s;}
details[open]>.rmap-evidence-toggle::before{content:"▾ ";}
.rmap-evidence-toggle:hover{color:var(--deep);}
.rmap-evidence-body{margin-top:4px;}

/* ── Senior-career / domain framing (Phase 3, item #18) ────────── */
.rmap-stage-framing{
  background:rgba(107,91,142,0.05);border:1px solid rgba(107,91,142,0.16);border-radius:var(--radius-md);
  padding:14px 20px;
}
.rmap-stage-framing p{font-size:12.5px;color:var(--mid);line-height:1.7;}

/* ── Year-by-year transit outlook (Jupiter/Saturn/Rahu-Ketu) ───── */
.transit-outlook-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;}
.transit-year-card{background:#fff;border:1px solid var(--border);border-radius:10px;
  padding:14px 16px;}
.transit-year-head{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border);}
.transit-year-num{font-family:'Cormorant Garamond',serif;font-size:1.15rem;font-weight:700;color:#1A1A2E;}
.transit-net-pill{font-size:11px;font-weight:700;padding:2px 9px;border-radius:10px;}
.transit-row{margin:7px 0;}
.transit-row-label{font-size:12.5px;font-weight:600;color:#1A1A2E;}
.transit-row-note{font-size:12px;color:#475569;margin-top:2px;line-height:1.4;}
.cal-year-label{font-size:12px;font-weight:700;color:#94a3b8;letter-spacing:0.5px;
  text-transform:uppercase;margin-bottom:6px;}
.cal-year-event{font-size:11.5px;font-weight:600;margin-bottom:2px;}
.cal-year-score{font-size:10.5px;color:#64748b;}
.cal-year-bar{height:3px;border-radius:2px;margin-top:6px;}

/* ── MD arc narrative ───────────────────────────────────────── */
.md-arc-section{margin:0 0 28px;}
.md-arc-card{background:linear-gradient(135deg,rgba(26,26,46,0.03),rgba(201,168,76,0.04));
  border:1px solid rgba(201,168,76,0.20);border-radius:12px;padding:16px 20px;
  margin-bottom:12px;}
.md-arc-card h4{font-family:'Cormorant Garamond',serif;font-size:1.05rem;
  color:#1A1A2E;margin:0 0 6px;}
.md-arc-card p{font-size:13px;color:#374151;line-height:1.65;margin:0;}

/* ── Event remedies ─────────────────────────────────────────── */
.remedies-section{margin-top:10px;padding:10px 14px;background:rgba(201,168,76,0.05);
  border-left:3px solid var(--gold);border-radius:0 6px 6px 0;}
.remedies-title{font-size:10.5px;font-weight:700;color:#7A5E00;
  text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px;}
.remedies-list{list-style:none;padding:0;margin:0;}
.remedies-list li{font-size:11.5px;color:#4b5563;padding:2px 0;}
.remedies-list li::before{content:"🔸 ";}

/* ── Print ───────────────────────────────────────────────────── */
@media print{
  body{background:#FFF}
  .tl-header{background:#1A1A2E;-webkit-print-color-adjust:exact;color-adjust:exact}
  .pd-list{display:grid!important}
  .pd-toggle,.wi-tabs,.mt-block button{display:none}
  .ad-card,.md-group,.cal-year-card,.md-arc-card,
  .rmap-year-block,.rmap-cmp-wrap,.rmap-node,.rmap-pd-panel,.rmap-subwin-panel,
  .planet-panel,.d10-panel,.insight-panel,.tl-exec-cell,.fop-card,
  .rmap-kp-row,.rmap-matrix-row,tr,.glossary-panel{break-inside:avoid;page-break-inside:avoid}
  /* Expand collapsibles so nothing is hidden on paper */
  details[hidden],[hidden]{display:revert!important}
  details>summary{list-style:none}
  details:not([open])>*{display:revert!important}
  .fop-section,.traj-section{break-before:auto}
  .ad-card{box-shadow:none;border:1px solid #e2e8f0}
  .content,.content-footer{max-width:100%;padding:0 8px}
  .content-grid{grid-template-columns:1fr !important}
  .tl-sidebar{position:static !important;max-height:none !important;overflow:visible !important;
    flex-direction:column !important}
  .tl-sidebar>*{flex:none !important}
  @page{margin:18mm 14mm}
}
/* ── Micro-Timing Dashboard ─────────────────────────────────────────── */
.mt-section{margin:0 0 22px;padding:18px 22px;border-radius:14px;
  background:#fff;border:1px solid rgba(0,0,0,0.08);box-shadow:0 2px 8px rgba(0,0,0,0.04);}
.mt-section-title{font-family:'Cormorant Garamond',serif;font-size:1.15rem;font-weight:600;
  color:#1A1A2E;margin-bottom:14px;display:flex;align-items:center;gap:8px;}
.mt-section-title span{font-size:1.2rem;}
.hm-grid{display:flex;flex-wrap:wrap;gap:6px;}
.hm-win{padding:5px 10px;border-radius:8px;font-size:11px;font-weight:600;
  cursor:default;border:1px solid transparent;position:relative;}
.hm-win:hover .hm-tooltip{display:block;}
.hm-tooltip{display:none;position:absolute;z-index:99;bottom:calc(100% + 6px);left:50%;
  transform:translateX(-50%);background:#1A1A2E;color:#fff;border-radius:6px;
  padding:6px 10px;font-size:10.5px;font-weight:400;width:220px;line-height:1.4;
  pointer-events:none;white-space:normal;}
.hm-peak     {background:#d1fae5;color:#065f46;border-color:#6ee7b7;}
.hm-favourable{background:#eff6ff;color:#1e40af;border-color:#93c5fd;}
.hm-neutral  {background:#f1f5f9;color:#475569;border-color:#cbd5e1;}
.hm-avoid    {background:#fff1f2;color:#9f1239;border-color:#fda4af;}
.hm-best-label{font-size:10.5px;color:#065f46;font-weight:700;margin-top:8px;
  background:#ecfdf5;border:1px solid #6ee7b7;border-radius:6px;padding:4px 10px;display:inline-block;}
.radar-card{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;}
.radar-climate{padding:8px 16px;border-radius:20px;font-size:13px;font-weight:700;flex-shrink:0;}
.radar-clear    {background:#ecfdf5;color:#065f46;border:1px solid #6ee7b7;}
.radar-caution  {background:#fffbeb;color:#92400e;border:1px solid #fcd34d;}
.radar-turbulent{background:#fff7ed;color:#9a3412;border:1px solid #fdba74;}
.radar-storm    {background:#fef2f2;color:#991b1b;border:1px solid #fca5a5;}
.radar-advice{font-size:13px;color:#334155;line-height:1.65;flex:1;}
.radar-houses{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;}
.radar-house-pill{font-size:10.5px;padding:2px 8px;border-radius:12px;font-weight:600;}
.radar-house-ok  {background:#f0fdf4;color:#166534;border:1px solid #86efac;}
.radar-house-warn{background:#fef2f2;color:#991b1b;border:1px solid #fca5a5;}
.wi-grid{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;}
.wi-btn{padding:7px 14px;border-radius:20px;border:1px solid rgba(201,168,76,0.4);
  background:#fff;color:#1A1A2E;font-size:12px;font-weight:600;cursor:pointer;}
.wi-btn:hover,.wi-btn.active{background:#C9A84C;color:#fff;border-color:#C9A84C;}
.wi-panel{display:none;padding:12px 14px;border-radius:10px;border:1px solid rgba(0,0,0,0.08);
  background:#fafafa;margin-top:4px;}
.wi-panel.shown{display:block;}
.wi-fav  {border-left:4px solid #22c55e;}
.wi-caut {border-left:4px solid #f59e0b;}
.wi-unad {border-left:4px solid #ef4444;}
.wi-advisability{display:inline-block;font-size:11.5px;font-weight:700;padding:2px 10px;border-radius:12px;margin-bottom:8px;}
.wi-adv-fav {background:#dcfce7;color:#166534;border:1px solid #86efac;}
.wi-adv-caut{background:#fef9c3;color:#854d0e;border:1px solid #fde68a;}
.wi-adv-unad{background:#fef2f2;color:#991b1b;border:1px solid #fca5a5;}
.wi-timing{font-size:12.5px;color:#334155;line-height:1.6;margin-bottom:6px;}
.wi-factors{margin-top:8px;font-size:11.5px;color:#475569;}
.wi-factors li{margin-bottom:3px;}
.ht-weeks{display:flex;flex-direction:column;gap:8px;}
.ht-week{padding:10px 14px;border-radius:10px;border:1px solid rgba(0,0,0,0.07);background:#fafafa;}
.ht-week.current{background:linear-gradient(135deg,rgba(201,168,76,0.07),#fff);border-color:rgba(201,168,76,0.4);}
.ht-week-label{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#7A5E00;margin-bottom:4px;}
.ht-week.current .ht-week-label::after{content:' — ACTIVE THIS WEEK';color:#C9A84C;}
.ht-title{font-size:13px;font-weight:700;color:#1A1A2E;margin-bottom:2px;}
.ht-detail{font-size:12px;color:#475569;line-height:1.55;}
.ht-freq{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  color:#7A5E00;background:rgba(201,168,76,0.12);border-radius:10px;padding:1px 7px;margin-left:6px;}
.ht-pd-note{font-size:11.5px;color:#334155;background:#f0fdf4;border-radius:6px;
  padding:5px 8px;margin-top:5px;border-left:3px solid #22c55e;}

.traj-section{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:22px 26px;margin-bottom:28px;box-shadow:var(--shadow-sm);}
.traj-heading{font-family:'Cormorant Garamond',Georgia,serif;font-size:19px;font-weight:700;color:var(--deep);margin-bottom:16px;}
.traj-kpi-row{display:flex;gap:32px;margin-bottom:18px;padding-bottom:18px;border-bottom:1px solid var(--border-soft);}
.traj-kpi-label{font-size:10px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-bottom:4px;}
.traj-kpi-val{font-size:24px;font-weight:700;color:var(--deep);font-family:'Cormorant Garamond',Georgia,serif;}
.traj-wrap{position:relative;min-height:240px;overflow-x:auto;}
.traj-svg{display:block;width:100%;min-width:640px;height:auto;}
.foreign-link-card{display:flex;align-items:center;justify-content:space-between;gap:16px;background:linear-gradient(135deg,#0f2027 0%,#203a43 55%,#2c5364 100%);border-radius:var(--radius-md);padding:16px 20px;margin-bottom:20px;color:#f0f9ff;border:1px solid rgba(125,211,252,.25);}
.foreign-link-title{font-size:13px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:#e0f2fe;margin-bottom:3px;}
.foreign-link-sub{font-size:11.5px;color:#bae6fd;line-height:1.5;}
.foreign-link-btn{display:inline-flex;align-items:center;justify-content:center;white-space:nowrap;background:#e0f2fe;color:#0f172a;text-decoration:none;border-radius:8px;padding:7px 12px;font-size:11px;font-weight:800;border:1px solid rgba(255,255,255,.35);}
.foreign-link-btn:hover{background:#ffffff;}

/* ── Foreign Opportunity Module ─────────────────────────────── */
.fop-section{background:linear-gradient(135deg,#0f2027 0%,#203a43 50%,#2c5364 100%);border-radius:var(--radius-lg);padding:24px 28px;margin-bottom:28px;color:#f0f9ff;}
.fop-section-header{margin-bottom:18px;}
.fop-section-title{font-size:17px;font-weight:700;color:#e0f2fe;letter-spacing:.01em;margin-bottom:4px;}
.fop-section-sub{font-size:11px;color:#94d2e8;line-height:1.5;}
.fop-cards{display:flex;flex-direction:column;gap:12px;}
.fop-card{background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);border-radius:var(--radius-md);padding:14px 16px;transition:background .2s;}
.fop-card:hover{background:rgba(255,255,255,0.11);}
.fop-card-past{opacity:0.68;}
.fop-card-active{border-color:rgba(201,168,76,0.6);background:rgba(201,168,76,0.08);}
.fop-card-upcoming{border-color:rgba(14,165,233,0.35);}
.fop-card-header{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap;}
.fop-lords{display:flex;align-items:center;gap:4px;}
.fop-md{font-size:14px;font-weight:700;color:#e0f2fe;}
.fop-dash{color:#94d2e8;font-size:12px;}
.fop-ad{font-size:13px;font-weight:600;color:#bae6fd;}
.fop-dates{font-size:10.5px;color:#7dd3fc;margin-left:auto;}
.fop-tag{font-size:9.5px;font-weight:700;padding:2px 8px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);color:#e0f2fe;background:rgba(255,255,255,0.08);}
.fop-score-row{display:flex;align-items:center;gap:8px;margin-bottom:9px;}
.fop-score-bar{flex:1;height:5px;background:rgba(255,255,255,0.12);border-radius:99px;overflow:hidden;}
.fop-score-fill{height:100%;border-radius:99px;transition:width .4s;}
.fop-score-num{font-size:11px;font-weight:700;color:#e0f2fe;min-width:32px;text-align:right;}
.fop-badge{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;padding:2px 9px;border-radius:8px;}
.fop-badge-green{background:#065f46;color:#6ee7b7;border:1px solid #059669;}
.fop-badge-amber{background:#78350f;color:#fcd34d;border:1px solid #d97706;}
.fop-badge-blue{background:#1e3a5f;color:#93c5fd;border:1px solid #3b82f6;}
.fop-badge-red{background:#7f1d1d;color:#fca5a5;border:1px solid #dc2626;}
.fop-geo{font-size:10.5px;color:#7dd3fc;margin-bottom:7px;line-height:1.4;word-break:break-word;overflow-wrap:break-word;}
.fop-indicators{display:flex;flex-wrap:wrap;gap:5px;}
.fop-indicator{font-size:9.5px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);color:#bae6fd;border-radius:6px;padding:2px 8px;line-height:1.5;}
.fop-trigger{margin-top:8px;font-size:10px;color:#fde68a;border-top:1px solid rgba(255,255,255,0.08);padding-top:7px;}
.fop-trigger-label{font-weight:700;text-transform:uppercase;font-size:8.5px;letter-spacing:.06em;margin-right:4px;}
.fop-empty{font-size:12px;color:#94d2e8;text-align:center;padding:16px 0;}

/* ── Condensed inline Foreign Opportunity list (2026-07-05) ───────── */
.fop-condensed-section{margin-bottom:32px;}
.fop-c-list{display:flex;flex-direction:column;gap:8px;}
.fop-c-row{
  display:grid;grid-template-columns:118px 90px minmax(60px,140px) 76px minmax(0,1fr);
  align-items:center;column-gap:14px;
  background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:9px 14px;font-size:12px;
}
.fop-c-dates{color:var(--muted);font-size:11px;white-space:nowrap;}
.fop-c-lords{font-weight:700;color:var(--deep);}
.fop-c-bar{height:5px;background:var(--border-soft);border-radius:3px;overflow:hidden;}
.fop-c-fill{height:100%;border-radius:3px;}
.fop-c-tag{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  padding:2px 8px;border-radius:8px;text-align:center;white-space:nowrap;}
.fop-c-tag-past{background:#f1f5f9;color:#64748b;}
.fop-c-tag-active{background:rgba(201,168,76,0.16);color:#7A5E00;}
.fop-c-tag-upcoming{background:#eff6ff;color:#1d4ed8;}
.fop-c-geo{color:var(--mid);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
@media (max-width:760px){
  .fop-c-row{grid-template-columns:1fr 1fr;row-gap:6px;}
  .fop-c-bar{grid-column:1/-1;}
  .fop-c-geo{grid-column:1/-1;white-space:normal;}
}

/* ── Planet Strength Panel ───────────────────────────────────────── */
.planet-panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md);padding:16px 18px;margin-bottom:20px;box-shadow:var(--shadow-sm);}
.planet-panel-title{font-size:10.5px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);margin-bottom:12px;}
/* GAP FIX (2026-07-05): row-level CSS Grid instead of flex-with-fixed-width-name.
   Flex let long "Planet + AK/AmK/H10 tag" labels wrap onto two lines, which threw
   off vertical alignment between rows (the reported "planets not aligned" bug).
   A shared 3-column grid (name | bar | value) keeps every row's columns locked
   to the same width regardless of label length; overflow truncates with an
   ellipsis instead of wrapping. */
.planet-panel-grid{display:grid;grid-template-columns:1fr;gap:8px;}
.planet-bar-row{
  display:grid;grid-template-columns:92px minmax(0,1fr) 42px;
  align-items:center;column-gap:10px;padding:2px 0;
}
.planet-bar-name{
  font-size:11.5px;font-weight:600;color:var(--deep);
  display:flex;align-items:center;gap:4px;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.planet-bar-karaka{font-size:8px;font-weight:700;padding:1px 4px;border-radius:4px;background:rgba(201,168,76,0.18);color:#7A5E00;border:1px solid rgba(201,168,76,0.3);white-space:nowrap;flex-shrink:0;}
.planet-bar-dignity{font-size:8px;font-weight:700;padding:1px 4px;border-radius:4px;background:transparent;border:1px solid;white-space:nowrap;flex-shrink:0;margin-left:4px;}
.planet-bar-dusthana{font-size:8px;font-weight:600;padding:1px 4px;border-radius:4px;background:rgba(217,119,6,0.12);color:#92400e;border:1px solid rgba(217,119,6,0.35);white-space:nowrap;flex-shrink:0;margin-left:4px;}
.planet-bar-track{height:7px;background:var(--border-soft);border-radius:4px;overflow:hidden;width:100%;}
.planet-bar-fill{height:100%;border-radius:4px;}
.planet-bar-val{font-size:10.5px;font-weight:700;text-align:right;white-space:nowrap;}
.pbar-strong{background:linear-gradient(90deg,#15803d,#22c55e);}
.pbar-mod{background:linear-gradient(90deg,#92400e,#d97706);}
.pbar-weak{background:linear-gradient(90deg,#4b5563,#9ca3af);}
/* ── D10 Insights Banner ─────────────────────────────────────────── */
.d10-panel{background:linear-gradient(135deg,rgba(67,56,202,0.07),rgba(99,102,241,0.04));border:1px solid rgba(99,102,241,0.2);border-radius:var(--radius-md);padding:14px 20px;margin-bottom:20px;}
.d10-panel-title{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#4338ca;margin-bottom:10px;}
.d10-cells{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.d10-cell{background:rgba(255,255,255,0.72);border:1px solid rgba(99,102,241,0.15);border-radius:8px;padding:6px 11px;min-width:0;}
.d10-cell.d10-cell-wide{grid-column:1 / -1;}
.insight-panel{background:linear-gradient(135deg,rgba(15,118,110,0.06),rgba(45,212,191,0.03));border:1px solid rgba(20,184,166,0.2);border-radius:var(--radius-md);padding:14px 20px;margin-bottom:20px;}
.insight-panel-title{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#0f766e;margin-bottom:10px;}
.insight-cells{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.insight-cell{background:rgba(255,255,255,0.72);border:1px solid rgba(20,184,166,0.15);border-radius:8px;padding:6px 11px;min-width:0;}
.insight-cell.insight-cell-wide{grid-column:1 / -1;}
.insight-cell-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#0f766e;margin-bottom:3px;}
.insight-cell-val{font-size:12.5px;font-weight:700;color:#1e293b;line-height:1.35;}
.d10-cell-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#6366f1;margin-bottom:3px;}
.d10-cell-val{font-size:12.5px;font-weight:700;color:#1e293b;}
.d10-occ-pill{font-size:9px;font-weight:600;padding:1px 5px;border-radius:4px;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe;display:inline-block;margin:1px;}
/* ── Per-AD D10 row ──────────────────────────────────────────────── */
.ad-d10-row{display:flex;align-items:center;gap:6px;margin-top:6px;flex-wrap:wrap;}
.ad-d10-badge{font-size:10px;font-weight:700;padding:2px 9px;border-radius:6px;background:#eef2ff;color:#4338ca;border:1px solid #c7d2fe;}
.ad-gfact-pill{font-size:9.5px;font-weight:600;padding:2px 7px;border-radius:5px;background:#f0fdf4;color:#15803d;border:1px solid #86efac;}
.ad-gfact-neg{background:#fef2f2;color:#991b1b;border-color:#fca5a5;}
/* ── Full "roadmap-year-card" (A/B audience card) — was entirely unstyled ──
   User-reported (2026-07-07): narrative font size/color "not good". Root
   cause: `.roadmap-year-card`, `.roadmap-year-header`, `.roadmap-event`,
   and — most visibly — `.roadmap-narrative` (the actual "A. Practical
   Career Reading" text block) had NO CSS rule anywhere in this stylesheet.
   They were falling back to bare browser defaults: ~16px black serif body
   text, clashing with the rest of the report's 12.5-14px muted-gray
   palette. This block gives the whole family real styling, matched to
   the same visual language already used by `.rmap-year-narrative`. ──── */
.roadmap-year-card{
  background:var(--surface,#fff);border:1px solid var(--border,#E8E2D4);
  border-radius:var(--radius-lg,18px);padding:22px 26px;margin-bottom:24px;
  box-shadow:var(--shadow-sm,0 1px 4px rgba(26,26,46,0.06));
}
.roadmap-year-header{display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap}
.roadmap-year-num{font-family:'Cormorant Garamond',Georgia,serif;font-size:20px;font-weight:700;color:var(--deep,#1A1A2E)}
.roadmap-year-badge{font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;
  padding:3px 10px;border-radius:20px;background:var(--border-soft,#F0ECE2);color:var(--muted,#5F5F7A)}
.roadmap-weather{font-size:12.5px;color:var(--muted,#5F5F7A)}
.roadmap-score{margin-left:auto;font-size:14px;font-weight:700;color:var(--gold,#C9A84C)}
.roadmap-event{font-family:'Cormorant Garamond',Georgia,serif;font-size:18px;font-weight:700;
  color:var(--deep,#1A1A2E);margin-bottom:14px}
.roadmap-narrative{
  font-size:14px;line-height:1.78;color:var(--mid,#3D3D5C);
  background:var(--surface-warm,#FAF8F3);border:1px solid var(--border-soft,#F0ECE2);
  border-radius:var(--radius-md,12px);padding:16px 20px;margin-bottom:4px;
}
.roadmap-karaka,.roadmap-natal,.roadmap-saturn{
  font-size:12px;color:var(--muted,#5F5F7A);line-height:1.6;margin-top:10px;
}
.roadmap-yoga{
  font-size:12px;color:var(--mid,#3D3D5C);line-height:1.6;margin-top:8px;
  padding:8px 12px;background:var(--gold-light,rgba(201,168,76,0.08));
  border-left:3px solid var(--gold,#C9A84C);border-radius:0 6px 6px 0;
}
.roadmap-yoga b{color:var(--deep,#1A1A2E)}
"""

# ── Professional report uplift (nav shell + reading guide) ────────────────
# Added 2026-07-07 in response to the user's "professional HTML report"
# request. Presentation-only: no scoring, event-classification, or
# narrative logic is touched here — this only adds a sticky nav bar, a
# "how to read this report" panel, and jump-links to each roadmap period.
# NOTE: keep `.rmap-audience-label` and `.rmap-audience-label-b` as SEPARATE
# rules (not a combined selector). An earlier hand-edited draft of this CSS
# merged them into one `!important` rule that made both the "A. Practical
# Career Reading" and "B. Parent / Family Guidance" labels render as the
# same navy pill, erasing the gold/purple audience distinction those labels
# exist to provide. Keep them distinguishable.
_TL_PRO_CSS = """
.pro-nav-shell{position:sticky;top:0;z-index:50;display:grid;grid-template-columns:auto 1fr;gap:14px 28px;align-items:center;max-width:1760px;margin:-1px auto 0;padding:14px 24px;background:rgba(255,252,245,.92);backdrop-filter:blur(18px);border:1px solid rgba(231,220,200,.85);border-top:none;border-radius:0 0 22px 22px;box-shadow:0 14px 34px rgba(17,24,39,.08)}
.pro-nav-brand{display:flex;flex-direction:column;line-height:1.15}
.pro-nav-brand span{font-size:10px;text-transform:uppercase;letter-spacing:1.4px;color:var(--muted,#667085);font-weight:700}
.pro-nav-brand strong{font-family:'Cormorant Garamond',serif;font-size:20px;color:#111827}
.pro-nav-links,.pro-period-jump{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:flex-end}
.pro-nav-links a,.pro-period-jump a{font-size:12px;font-weight:700;text-decoration:none;color:#334155;background:#fff;border:1px solid #e7dcc8;padding:8px 12px;border-radius:999px;box-shadow:0 1px 3px rgba(17,24,39,.04)}
.pro-nav-links a:hover,.pro-period-jump a:hover{background:#111827;color:#fff;border-color:#111827}
.pro-period-jump{grid-column:1/-1;justify-content:flex-start;border-top:1px solid rgba(231,220,200,.7);padding-top:10px}
.pro-period-jump span{font-size:10px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted,#667085);font-weight:800;margin-right:4px}
.pro-period-jump a{font-weight:600;background:#fbf7ef;color:#475569;padding:6px 10px}
.pro-reading-guide{background:linear-gradient(135deg,#fff 0%,#fffaf0 100%);border:1px solid #e7dcc8;border-radius:26px;padding:28px 30px;margin:0 0 22px;box-shadow:0 18px 48px rgba(17,24,39,.08);position:relative;overflow:hidden}
.pro-reading-guide:after{content:'';position:absolute;right:-80px;top:-100px;width:260px;height:260px;border-radius:50%;background:radial-gradient(circle,rgba(200,162,70,.16),transparent 70%)}
.pro-guide-kicker{font-size:11px;text-transform:uppercase;letter-spacing:2px;color:#c8a246;font-weight:900;margin-bottom:8px}
.pro-reading-guide h2{font-family:'Cormorant Garamond',serif;font-size:32px;line-height:1.1;color:#111827;margin-bottom:8px}
.pro-reading-guide p{max-width:900px;color:#273449;font-size:14px}
.pro-guide-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:18px}
.pro-guide-grid div{background:#fff;border:1px solid #e7dcc8;border-radius:18px;padding:16px;display:grid;grid-template-columns:auto 1fr;gap:2px 12px;align-items:center}
.pro-guide-grid strong{grid-row:1/3;width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#111827;color:#fff}
.pro-guide-grid span{font-weight:800;color:#111827}
.pro-guide-grid em{font-style:normal;font-size:12px;color:var(--muted,#667085)}
.rmap-audience-label{background:#111827;color:#fff;border-radius:999px;padding:5px 10px;font-size:10px;letter-spacing:.8px}
.rmap-audience-label-b{background:#6B5B8E;color:#fff;border-radius:999px;padding:5px 10px;font-size:10px;letter-spacing:.8px}
@media(max-width:1100px){.pro-nav-shell{grid-template-columns:1fr}.pro-nav-links{justify-content:flex-start}.pro-guide-grid{grid-template-columns:1fr}}
@media print{.pro-nav-shell{display:none!important}}
"""

_TL_ELEVATED_HEAD_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;'
    '9..144,500;9..144,600&family=Inter+Tight:wght@300;400;500;600;700&family=JetBrains+Mono:'
    'wght@400;500;600&display=swap" rel="stylesheet">'
)

# ── Elevated editorial/dashboard dark theme (2026-07-07, user-supplied) ────
# Applied directly to the live report rather than as a separate post-process
# script: the user's original approach re-parsed the finished HTML with
# BeautifulSoup and re-shelled it into a second file. That's a disconnected
# extra step that immediately drifts out of sync with every future change to
# this renderer (same problem we hit earlier with the hand-edited
# "professional uplift" HTML that had no backing source file). Since nearly
# every selector below targets class/id names this renderer already emits
# (.tl-header, .tl-exec-panel, .pro-nav-shell, .cal-section, .tl-audit-panel,
# .content-grid, .tl-sidebar, .planet-panel, .traj-section, .fop-c-row,
# [id^="period-"], etc.), it's applied as one more real CSS layer in the
# actual page, so every future regeneration gets it automatically.
_TL_ELEVATED_CSS = """
:root, html, body {
  --bg:          #0F1013 !important;
  --surface:     #16181D !important;
  --surface-warm:#1B1E24 !important;
  --gold:        #E5B84B !important;
  --gold-light:  rgba(229,184,75,0.12) !important;
  --gold-mid:    rgba(229,184,75,0.28) !important;
  --deep:        #F5F2EA !important;
  --mid:         #C9C6BE !important;
  --muted:       #8A8A99 !important;
  --border:      rgba(255,255,255,0.08) !important;
  --border-soft: rgba(255,255,255,0.05) !important;
  --purple:      #A78BFA !important;
  --purple-light:rgba(167,139,250,0.14) !important;
  --green:       #4ADE80 !important;
  --green-light: rgba(74,222,128,0.14) !important;
  --amber:       #FBBF24 !important;
  --amber-light: rgba(251,191,36,0.14) !important;
  --red:         #F87171 !important;
  --red-light:   rgba(248,113,113,0.14) !important;

  --ink:         #F5F2EA;
  --ink-dim:     #C9C6BE;
  --ink-mute:    #8A8A99;
  --line:        rgba(255,255,255,0.08);
  --line-strong: rgba(255,255,255,0.16);

  --font-serif:  'Fraunces','Cormorant Garamond',ui-serif,Georgia,serif;
  --font-sans:   'Inter Tight','Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --font-mono:   'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;

  --grad-gold:   linear-gradient(135deg,#F4D06F 0%,#E5B84B 45%,#B8860B 100%);
  --grad-ink:    linear-gradient(180deg,#1B1E24 0%,#0F1013 100%);
  --grad-halo:   radial-gradient(1200px 600px at 20% -10%,rgba(229,184,75,0.10),transparent 60%),
                 radial-gradient(900px 500px at 90% 10%,rgba(167,139,250,0.08),transparent 60%);
}

html { scroll-behavior:smooth; }
body {
  background: var(--bg) !important;
  background-image: var(--grad-halo);
  background-attachment: fixed;
  color: var(--ink) !important;
  font-family: var(--font-sans) !important;
  font-size: 15px;
  line-height: 1.6;
  letter-spacing: -0.005em;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
body::before, body::after { display:none !important; }
::selection { background: var(--gold); color: #0F1013; }

.tl-header { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; margin: 0 !important; }
.tl-header-inner {
  max-width: 1240px; margin: 0 auto; padding: 64px 40px 40px !important;
  display: grid !important; grid-template-columns: 1fr auto; gap: 48px; align-items: end;
  border-bottom: 1px solid var(--line); position: relative;
}
.tl-header-inner::before {
  content: ""; position: absolute; inset: auto 40px 0 40px; height: 1px;
  background: linear-gradient(90deg,transparent,var(--gold) 20%,var(--gold) 80%,transparent);
  opacity: 0.4;
}
.tl-brand {
  font-family: var(--font-mono) !important; font-size: 11px !important; font-weight: 500 !important;
  letter-spacing: 0.22em !important; text-transform: uppercase; color: var(--gold) !important;
  margin-bottom: 20px !important; display: inline-flex; align-items: center; gap: 10px;
}
.tl-brand::before { content: "\\2726"; color: var(--gold); font-size: 14px; line-height: 1; }
.tl-name {
  font-family: var(--font-serif) !important; font-weight: 500 !important;
  font-size: clamp(48px, 6vw, 84px) !important; line-height: 0.98 !important;
  letter-spacing: -0.03em !important; color: var(--ink) !important; margin: 0 0 18px !important;
  background: linear-gradient(180deg,#F5F2EA 0%,#C9C6BE 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.tl-meta {
  font-family: var(--font-mono) !important; font-size: 12px !important; letter-spacing: 0.05em !important;
  color: var(--ink-mute) !important; text-transform: uppercase; line-height: 1.9 !important;
}
.tl-conf {
  background: linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01)) !important;
  border: 1px solid var(--line) !important; border-radius: 16px !important; padding: 24px 26px !important;
  min-width: 300px; box-shadow: 0 30px 60px -30px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.04);
  backdrop-filter: blur(20px);
}
.tl-conf-badge {
  display: inline-block; font-family: var(--font-mono) !important; font-size: 11px !important;
  font-weight: 600 !important; letter-spacing: 0.2em !important; padding: 6px 14px !important;
  border-radius: 999px !important; background: var(--green-light) !important; color: var(--green) !important;
  border: 1px solid var(--green) !important;
}
.tl-conf-sub {
  color: var(--ink-mute) !important; font-size: 11px !important; text-transform: uppercase;
  letter-spacing: 0.18em; margin: 12px 0 16px !important; font-family: var(--font-mono);
}
.tl-layer-conf { border-top: 1px solid var(--line); padding-top: 14px; }
.tl-layer-row { display: flex; align-items:center; gap: 10px; padding: 5px 0 !important; font-size: 12.5px !important; color: var(--ink-dim) !important; }
.tl-layer-name { flex: 1; }
.tl-layer-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green) !important; box-shadow: 0 0 12px var(--green); }
.tl-layer-label { font-family: var(--font-mono) !important; font-size: 10.5px !important; letter-spacing: 0.14em; text-transform: uppercase; color: var(--green) !important; }
.tl-layer-divider { height:1px; background: var(--line); margin: 10px 0; }
.tl-layer-caption { font-size: 11px !important; color: var(--ink-mute) !important; font-style: italic; margin-top: 8px; }

.pro-nav-shell {
  position: sticky; top: 0; z-index: 40;
  background: rgba(15,16,19,0.85) !important; backdrop-filter: saturate(180%) blur(20px);
  border: none !important; border-bottom: 1px solid var(--line) !important;
  padding: 14px 40px !important; display: flex !important; align-items:center; gap: 40px; max-width: 100%;
}
.pro-nav-brand { display:flex; flex-direction:column; gap: 2px; }
.pro-nav-brand span { font-family: var(--font-mono) !important; font-size: 9.5px !important; letter-spacing: 0.24em !important; text-transform: uppercase; color: var(--ink-mute) !important; }
.pro-nav-brand strong { font-family: var(--font-serif) !important; font-weight: 500 !important; font-size: 15px !important; color: var(--ink) !important; letter-spacing: -0.01em; }
.pro-nav-links { display:flex; gap: 4px !important; margin-left: auto; }
.pro-nav-links a { padding: 8px 14px !important; font-size: 12.5px !important; font-weight: 500 !important; color: var(--ink-dim) !important; text-decoration: none; border-radius: 8px; transition: all .18s ease; background: transparent !important; }
.pro-nav-links a:hover { color: var(--gold) !important; background: var(--gold-light) !important; }
.pro-period-jump { display:flex; gap: 6px; align-items:center; padding-left: 20px; border-left: 1px solid var(--line); overflow-x: auto; }
.pro-period-jump span { font-family: var(--font-mono) !important; font-size: 10px !important; letter-spacing: 0.18em; color: var(--ink-mute) !important; text-transform: uppercase; white-space: nowrap; }
.pro-period-jump a { padding: 4px 10px !important; font-size: 11px !important; color: var(--ink-dim) !important; text-decoration:none; border: 1px solid var(--line); border-radius: 999px; white-space: nowrap; transition: all .18s ease; }
.pro-period-jump a:hover { border-color: var(--gold); color: var(--gold) !important; background: var(--gold-light); }

.content { max-width: 1240px !important; margin: 0 auto !important; padding: 56px 40px !important; }
.content + .content { padding-top: 0 !important; }

.pro-reading-guide { background: transparent !important; border: none !important; padding: 32px 0 56px !important; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
.pro-guide-kicker { font-family: var(--font-mono) !important; font-size: 11px !important; letter-spacing: 0.28em !important; text-transform: uppercase; color: var(--gold) !important; margin-bottom: 20px !important; }
.pro-reading-guide h2 { font-family: var(--font-serif) !important; font-weight: 400 !important; font-size: clamp(28px,3.4vw,44px) !important; line-height: 1.15 !important; letter-spacing: -0.02em !important; color: var(--ink) !important; max-width: 22ch; margin: 0 0 20px !important; }
.pro-reading-guide h2::first-letter { color: var(--gold); }
.pro-reading-guide p { color: var(--ink-dim) !important; font-size: 16px !important; line-height: 1.7 !important; max-width: 62ch; margin: 0 0 32px !important; }
.pro-guide-grid { display: grid !important; grid-template-columns: repeat(3,1fr); gap: 24px !important; }
.pro-guide-grid > div { padding: 22px !important; background: rgba(255,255,255,0.02) !important; border: 1px solid var(--line) !important; border-radius: 14px !important; transition: all .25s ease; position: relative; overflow: hidden; }
.pro-guide-grid > div:hover { border-color: var(--gold-mid); background: rgba(229,184,75,0.04) !important; transform: translateY(-2px); }
.pro-guide-grid strong { font-family: var(--font-serif) !important; font-size: 40px !important; font-weight: 400 !important; color: var(--gold) !important; line-height: 1; display: block; margin-bottom: 10px !important; }
.pro-guide-grid span { display:block; font-weight: 600 !important; font-size: 14px !important; color: var(--ink) !important; margin-bottom: 4px !important; }
.pro-guide-grid em { color: var(--ink-mute) !important; font-style: normal !important; font-size: 12.5px !important; letter-spacing: 0.01em; }

.tl-exec-panel { display: grid !important; grid-template-columns: repeat(3,1fr) !important; gap: 1px !important; background: var(--line) !important; border: 1px solid var(--line) !important; border-radius: 20px !important; overflow: hidden; margin: 40px 0 !important; box-shadow: 0 40px 80px -40px rgba(0,0,0,0.7); }
.tl-exec-cell { background: var(--surface) !important; padding: 28px 26px !important; position: relative; min-height: 140px; transition: background .25s ease; }
.tl-exec-cell:hover { background: var(--surface-warm) !important; }
.tl-exec-cell.active { background: linear-gradient(180deg,rgba(229,184,75,0.10),transparent) !important; }
.tl-exec-cell.active::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--grad-gold); }
.tl-exec-cell.risk::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--red); }
.tl-exec-cell.comp::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--purple); }
.tl-exec-label { font-family: var(--font-mono) !important; font-size: 10.5px !important; letter-spacing: 0.22em !important; text-transform: uppercase; color: var(--ink-mute) !important; margin-bottom: 14px !important; }
.tl-exec-val { font-family: var(--font-serif) !important; font-weight: 500 !important; font-size: 26px !important; line-height: 1.15 !important; letter-spacing: -0.015em !important; color: var(--ink) !important; margin-bottom: 8px !important; }
.tl-exec-sub { color: var(--ink-dim) !important; font-size: 12.5px !important; line-height: 1.5 !important; }

.cal-heading, .tl-audit-title, .planet-panel-title, .traj-heading {
  font-family: var(--font-serif) !important; font-weight: 500 !important; font-size: 28px !important;
  line-height: 1.2 !important; letter-spacing: -0.02em !important; color: var(--ink) !important;
  margin: 0 0 8px !important; padding-bottom: 16px !important; border-bottom: 1px solid var(--line); position: relative;
}
.cal-heading::after, .tl-audit-title::after { content: ""; position: absolute; bottom: -1px; left: 0; width: 60px; height: 2px; background: var(--grad-gold); }
.rmap-sub, .cal-section > .rmap-sub { color: var(--ink-mute) !important; font-size: 14px !important; font-style: italic; margin: 12px 0 28px !important; max-width: 68ch; }

.cal-section, .rmap-section, .tl-audit-panel, .fop-condensed-section, .planet-panel, .traj-section {
  background: var(--surface) !important; border: 1px solid var(--line) !important; border-radius: 20px !important;
  padding: 36px !important; margin: 32px 0 !important; box-shadow: 0 30px 60px -40px rgba(0,0,0,0.6); position: relative;
}

.rmap-cmp-wrap { background: transparent !important; padding: 0 !important; margin-top: 16px !important; }
.rmap-cmp-title { font-family: var(--font-mono) !important; font-size: 11px !important; letter-spacing: 0.22em; text-transform: uppercase; color: var(--gold) !important; margin-bottom: 16px !important; }
.rmap-cmp-table { width: 100%; border-collapse: separate !important; border-spacing: 0 !important; background: rgba(255,255,255,0.02) !important; border-radius: 14px; overflow: hidden; border: 1px solid var(--line) !important; font-size: 13.5px !important; }
.rmap-cmp-table th { background: rgba(255,255,255,0.03) !important; color: var(--ink-mute) !important; font-family: var(--font-mono) !important; font-size: 10.5px !important; letter-spacing: 0.16em; text-transform: uppercase; font-weight: 600 !important; padding: 14px 16px !important; text-align: left; border-bottom: 1px solid var(--line) !important; }
.rmap-cmp-table td { padding: 16px !important; border-bottom: 1px solid var(--line) !important; color: var(--ink-dim) !important; }
.rmap-cmp-table tr:last-child td { border-bottom: none !important; }
.rmap-cmp-row-now td { background: var(--gold-light) !important; color: var(--ink) !important; font-weight: 500 !important; }
.rmap-cmp-row-now td:first-child { border-left: 3px solid var(--gold); }
.rmap-cmp-retro-toggle { cursor: pointer; padding: 12px 16px !important; background: rgba(255,255,255,0.03); border-radius: 10px; margin-top: 20px; }
.rmap-cmp-note { color: var(--ink-mute) !important; font-size: 12.5px; padding: 14px 16px; font-style: italic; }

.tl-audit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 40px; margin-top: 24px; }
.tl-audit-row { display: flex; justify-content: space-between; align-items: center; padding: 14px 0 !important; border-bottom: 1px dashed var(--line); }
.tl-audit-name { color: var(--ink-dim) !important; font-size: 13.5px; }
.tl-audit-status { font-family: var(--font-mono) !important; font-size: 11px !important; letter-spacing: 0.16em; text-transform: uppercase; font-weight: 600 !important; }
.tl-audit-detail { color: var(--ink-mute) !important; font-size: 12.5px; margin-top: 20px; font-style: italic; }

.content-grid { display: grid !important; grid-template-columns: 320px 1fr !important; gap: 32px !important; align-items: start; }
@media (max-width: 1080px) { .content-grid { grid-template-columns: 1fr !important; } }
.tl-sidebar { position: sticky; top: 100px; background: var(--surface) !important; border: 1px solid var(--line) !important; border-radius: 20px !important; padding: 28px !important; box-shadow: 0 30px 60px -40px rgba(0,0,0,0.6); }
.tl-sidebar-label { font-family: var(--font-mono) !important; font-size: 10px !important; letter-spacing: 0.24em !important; text-transform: uppercase; color: var(--gold) !important; margin: 24px 0 12px !important; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.tl-sidebar-label:first-child { margin-top: 0 !important; }

.outcome-bar, .planet-panel-grid { display: grid; gap: 14px; }
.outcome-label { font-family: var(--font-mono) !important; font-size: 9.5px !important; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-mute) !important; margin-bottom: 4px !important; }
.outcome-val { font-family: var(--font-serif) !important; font-size: 16px !important; font-weight: 500 !important; color: var(--ink) !important; letter-spacing: -0.01em; }

.planet-panel { padding: 20px !important; margin: 0 !important; }
.planet-panel-title { font-size: 14px !important; padding-bottom: 12px !important; border: none !important; }
.planet-panel-title::after { display: none !important; }
.planet-bar-row { display: grid !important; grid-template-columns: 90px 1fr 50px 70px !important; gap: 10px; align-items: center; padding: 4px 0 !important; font-size: 12px !important; }
.planet-bar-name { color: var(--ink-dim) !important; }
.planet-bar-karaka { color: var(--gold) !important; font-size: 9px; margin-left: 4px; padding: 1px 5px; border: 1px solid var(--gold); border-radius: 4px; }
.planet-bar-track { background: rgba(255,255,255,0.06) !important; height: 6px; border-radius: 999px; overflow: hidden; }
.planet-bar-fill { height: 100%; background: var(--grad-gold) !important; border-radius: 999px; }
.pbar-strong { background: linear-gradient(90deg,#4ADE80,#22C55E) !important; }
.planet-bar-val { font-family: var(--font-mono) !important; font-size: 11px !important; }
.planet-bar-dignity { font-family: var(--font-mono) !important; font-size: 9.5px !important; letter-spacing: 0.1em; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; border: 1px solid; }

.traj-section { padding: 32px !important; }
.traj-heading { border: none !important; padding-bottom: 8px !important; }
.traj-heading::after { display: none !important; }
.traj-kpi-row { display: flex; gap: 40px; margin: 20px 0 32px; }
.traj-kpi-label { font-family: var(--font-mono) !important; font-size: 10px !important; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink-mute) !important; margin-bottom: 6px; }
.traj-kpi-val { font-family: var(--font-serif) !important; font-size: 32px !important; font-weight: 500 !important; color: var(--ink) !important; letter-spacing: -0.02em; }
.traj-svg { background: rgba(255,255,255,0.02); border-radius: 12px; padding: 14px; }

.fop-c-list { display: grid; gap: 16px; margin-top: 24px; }
.fop-c-row { display: grid !important; grid-template-columns: 200px 140px 1fr auto 220px !important; gap: 16px; align-items: center; padding: 16px 20px !important; background: rgba(255,255,255,0.02) !important; border: 1px solid var(--line) !important; border-radius: 12px !important; transition: all .2s ease; }
.fop-c-row:hover { border-color: var(--gold-mid); background: rgba(229,184,75,0.04) !important; }
.fop-c-dates { font-family: var(--font-mono) !important; font-size: 12px !important; color: var(--ink) !important; letter-spacing: 0.02em; }
.fop-c-lords { font-family: var(--font-serif) !important; font-size: 15px !important; color: var(--gold) !important; }
.fop-c-bar { background: rgba(255,255,255,0.06); height: 6px; border-radius: 999px; overflow: hidden; }
.fop-c-fill { height: 100%; border-radius: 999px; }
.fop-c-tag { font-family: var(--font-mono) !important; font-size: 9.5px !important; letter-spacing: 0.16em; text-transform: uppercase; padding: 4px 10px; border-radius: 999px; }
.fop-c-tag-upcoming { background: var(--purple-light); color: var(--purple); border: 1px solid var(--purple); }
.fop-c-geo { font-size: 12px !important; color: var(--ink-mute) !important; text-align: right; }

[id^="period-"] {
  border-radius: 20px !important; border: 1px solid var(--line) !important; padding: 32px !important;
  margin: 28px 0 !important; box-shadow: 0 30px 60px -40px rgba(0,0,0,0.6);
  background: var(--surface) !important;
}
[id^="period-"] h1, [id^="period-"] h2, [id^="period-"] h3, [id^="period-"] h4 {
  color: var(--ink) !important; font-family: var(--font-serif) !important; font-weight: 500 !important; letter-spacing: -0.015em;
}
[id^="period-"] table { background: rgba(255,255,255,0.02) !important; }
[id^="period-"] td, [id^="period-"] th { color: var(--ink-dim) !important; border-color: var(--line) !important; }

[class*="tl-"], [class*="cal-"], [class*="rmap-"], [class*="pro-"],
[class*="fop-"], [class*="traj-"], [class*="planet-"], [class*="outcome-"] { color: var(--ink-dim); }
h1,h2,h3,h4 { color: var(--ink) !important; }

.tl-footer {
  max-width: 1240px; margin: 40px auto 0 !important; padding: 40px !important;
  border-top: 1px solid var(--line); color: var(--ink-mute) !important; font-size: 12px !important;
  text-align: center; font-family: var(--font-mono) !important; letter-spacing: 0.1em;
}

@keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
.content > *, .cal-section, .tl-exec-panel, .tl-audit-panel, .rmap-section, .pro-reading-guide, .tl-sidebar {
  animation: fadeUp .7s cubic-bezier(.2,.7,.2,1) both;
}

@media print {
  :root, html, body {
    --bg: #ffffff !important; --surface: #ffffff !important;
    --ink: #111 !important; --ink-dim: #333 !important; --ink-mute: #666 !important; --line: #ddd !important;
  }
  body { background: #fff !important; }
  .pro-nav-shell { display: none !important; }
}
"""

_TL_PRO_JS = """
(function(){
  var links=[].slice.call(document.querySelectorAll('.pro-nav-shell a[href^="#"], .qnav a[href^="#"]'));
  links.forEach(function(a){a.addEventListener('click',function(e){
    var el=document.querySelector(a.getAttribute('href'));
    if(el){e.preventDefault();el.scrollIntoView({behavior:'smooth',block:'start'});}
  });});
})();
"""

# ── "Career Trajectory Atlas" hero/nav/period-header redesign ─────────────
# (2026-07-07, user-supplied, "full visual replacement" selected). This is
# the second dark-theme request in one session; the user explicitly asked
# to replace the previous nav/hero/period-header identity with this one's
# magazine/dashboard look (big serif hero, KPI wall, mini-timeline strip,
# sticky pill quick-nav, circular score gauge per period, eyebrow chip
# rows). Applied directly against real fields (timeline blocks, exec-panel
# data, career_score_pct) rather than the fictional debug-dump schema
# (career_score 0..1, sub_scores.career_activation, etc.) the user's script
# assumed — that schema doesn't exist anywhere in this codebase, same
# lesson as the earlier "professional uplift" HTML that wasn't backed by
# real source. Component classes below use the same --gold/--ink/--surface/
# --line/--font-serif/--font-mono tokens _TL_ELEVATED_CSS already declared
# on :root, so no token redeclaration is needed here — this only adds the
# NEW component classes (.hero, .qnav, .kpi-wall, .strip, .chip, .card,
# .eyebrow, .period-head, .gauge) that didn't exist in this file before.
_TL_ATLAS_CSS = """
.muted{color:var(--ink-mute)}
.small{font-size:11.5px}
.gauge{flex-shrink:0;line-height:0}
.chip{display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.12em;text-transform:uppercase;border:1px solid transparent}
.chip-gold{background:var(--gold-light);color:var(--gold);border-color:var(--gold)}
.chip-purple{background:var(--purple-light);color:var(--purple);border-color:var(--purple)}
.chip-green{background:var(--green-light);color:var(--green);border-color:var(--green)}
.chip-amber{background:var(--amber-light);color:var(--amber);border-color:var(--amber)}
.chip-red{background:var(--red-light);color:var(--red);border-color:var(--red)}
.chip-neutral{background:rgba(148,163,184,0.14);color:#94A3B8;border-color:rgba(148,163,184,0.4)}
.eyebrow{font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.22em;text-transform:uppercase;color:var(--gold)}
.eyebrow.small{font-size:9.5px;letter-spacing:0.18em}

/* Sticky quick-nav (replaces .pro-nav-shell as the primary nav bar) */
.qnav{position:sticky;top:0;z-index:50;background:rgba(15,16,19,0.85);backdrop-filter:saturate(180%) blur(20px);
  border-bottom:1px solid var(--line);padding:12px 32px;display:flex;gap:32px;align-items:center;
  font-family:var(--font-mono);font-size:11px;letter-spacing:0.14em;text-transform:uppercase}
.qnav b{color:var(--gold);letter-spacing:0.24em}
.qnav-links{display:flex;gap:6px;margin-left:auto;overflow:auto}
.qnav-links a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--ink-dim);transition:.2s;white-space:nowrap;text-decoration:none}
.qnav-links a:hover{border-color:var(--gold);color:var(--gold);background:var(--gold-light)}

/* Hero */
.hero{padding:56px 40px 40px;max-width:1360px;margin:0 auto}
.hero-title{font-family:var(--font-serif);font-weight:500;font-size:clamp(44px,5.5vw,72px);line-height:0.98;
  letter-spacing:-0.03em;margin-bottom:14px;color:var(--ink);
  background:linear-gradient(180deg,#F5F2EA 0%,#C9C6BE 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero-title span{color:var(--gold);-webkit-text-fill-color:var(--gold);font-style:italic;font-weight:400;font-size:0.55em;letter-spacing:0.02em}
.hero-sub{max-width:70ch;color:var(--ink-dim);font-size:16px;line-height:1.65;margin-bottom:36px}
.kpi-wall{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:16px;overflow:hidden;margin-bottom:28px}
@media (max-width:1080px){.kpi-wall{grid-template-columns:repeat(3,1fr)}}
.kpi{background:var(--surface);padding:22px 20px;position:relative;min-height:110px}
.kpi::before{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:rgba(255,255,255,0.06)}
.kpi-primary::before{background:var(--grad-gold)}
.kpi-gold::before{background:var(--gold)} .kpi-purple::before{background:var(--purple)} .kpi-green::before{background:var(--green)}
.kpi-l{font-family:var(--font-mono);font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:var(--ink-mute);margin-bottom:12px}
.kpi-v{font-family:var(--font-serif);font-size:22px;font-weight:500;line-height:1.15;color:var(--ink)}
.kpi-unit{color:var(--ink-mute);font-size:0.55em;margin-left:2px}

/* Mini-timeline strip in the hero */
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.strip-item{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px;transition:.2s;position:relative;overflow:hidden;text-decoration:none;display:block}
.strip-item:hover{border-color:var(--gold);transform:translateY(-2px)}
.strip-item::before{content:"";position:absolute;top:0;left:0;right:0;height:3px}
.strip-gold::before{background:var(--gold)} .strip-purple::before{background:var(--purple)}
.strip-amber::before{background:var(--amber)} .strip-green::before{background:var(--green)}
.strip-neutral::before{background:#94A3B8}
.strip-idx{font-family:var(--font-mono);font-size:10px;letter-spacing:0.2em;color:var(--ink-mute);margin-bottom:8px}
.strip-dates{font-family:var(--font-mono);font-size:11px;color:var(--ink-dim);margin-bottom:6px}
.strip-lords{font-family:var(--font-serif);font-size:20px;margin-bottom:6px;color:var(--ink)}
.strip-lords b{color:var(--gold)}
.strip-event{font-family:var(--font-mono);font-size:9.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--ink-mute);margin-bottom:10px}
.strip-score{position:absolute;top:14px;right:16px;font-family:var(--font-serif);font-size:28px;color:var(--gold)}
.strip-bar{height:3px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden}
.strip-bar div{height:100%;background:var(--grad-gold)}

/* Period header (replaces the old roadmap-year-header strip inside each card) */
.period-head{padding-top:0;margin-bottom:24px;display:grid;grid-template-columns:1fr auto;gap:32px;align-items:end}
.period-eyebrow{grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
.p-idx{font-family:var(--font-mono);font-size:11px;letter-spacing:0.24em;text-transform:uppercase;color:var(--gold)}
.period-title{font-family:var(--font-serif);font-size:clamp(32px,4vw,52px);line-height:1;color:var(--ink)}
.period-title .mdl{color:var(--ink-dim)}
.period-title .adl{color:var(--gold)}
.period-title .sep{color:var(--line-strong);margin:0 8px}
.period-dates{font-family:var(--font-mono);font-size:12px;letter-spacing:0.08em;color:var(--ink-mute);margin-top:8px}
.period-score{display:flex;gap:20px;align-items:center}
@media (max-width:760px){.period-head{grid-template-columns:1fr}.period-score{margin-top:16px}}

/* Card shell for wrapping existing content blocks under the new identity */
.card{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:26px;margin-bottom:20px;box-shadow:0 30px 60px -40px rgba(0,0,0,0.6)}
.card-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;gap:12px;flex-wrap:wrap}
"""


def _tl_reading_guide() -> str:
    """Static 'how to read this report' panel. Presentation-only."""
    return (
        '<section class="pro-reading-guide" aria-label="How to read this report">'
        '<div class="pro-guide-kicker">Career Timing Report</div>'
        '<h2>Start with the action signal, then verify the astrology.</h2>'
        '<p>This report separates three reading layers: practical career decision, '
        'family/parent guidance, and technical astrological evidence. The underlying '
        'predictions are unchanged; this only affects presentation and navigation.</p>'
        '<div class="pro-guide-grid">'
        '<div><strong>1</strong><span>Executive decision</span><em>What should be done now</em></div>'
        '<div><strong>2</strong><span>Roadmap windows</span><em>When each career phase activates</em></div>'
        '<div><strong>3</strong><span>Astro audit trail</span><em>KP, D10, Jaimini, transit evidence</em></div>'
        '</div>'
        '</section>'
    )


def _tl_period_jump_links(timeline, outlook_rows=None) -> str:
    """Build 'Jump to period' links using the exact same window + de-dup
    rule _build_career_roadmap_html uses (blocks overlapping the displayed
    outlook_rows years, collapsed when two years resolve to the same
    underlying AD block), so 'period-N' here lines up with the 'period-N'
    id actually rendered on that card. Presentation-only; reads timeline,
    writes nothing back to it."""
    if not timeline:
        return ""
    years = {row.get("year") for row in (outlook_rows or []) if row.get("year") is not None}
    seen_keys = set()
    items = []
    idx = 0
    for b in timeline:
        sd, ed = str(b.get("start_date", "")), str(b.get("end_date", ""))
        if years and not any(sd[:4] <= str(yr) <= ed[:4] for yr in years):
            continue
        key = (b.get("start_date"), b.get("end_date"), b.get("md_lord"), b.get("ad_lord"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        idx += 1
        et = (b.get("event_type") or "").replace("_", " ").title()
        anchor = f"period-{idx}"
        date_range = f'{_fmt_date(b.get("start_date",""))} → {_fmt_date(b.get("end_date",""))}'
        items.append(f'<a href="#{anchor}" title="{esc(date_range)}">{idx}. {esc(et)}</a>')
    if not items:
        return ""
    return '<div class="pro-period-jump"><span>Jump to period</span>' + "".join(items) + '</div>'


def _tl_professional_nav(timeline, outlook_rows=None) -> str:
    """Sticky nav shell with section links + period jump links."""
    section_links = (
        '<div class="pro-nav-links">'
        '<a href="#executive-summary">Executive</a>'
        '<a href="#career-roadmap">Roadmap</a>'
        '<a href="#technical-dashboard">Evidence</a>'
        '<a href="#audit-validation">Audit</a>'
        '</div>'
    )
    return (
        '<nav class="pro-nav-shell" aria-label="Career report navigation">'
        '<div class="pro-nav-brand"><span>Report Navigator</span><strong>Career Timeline</strong></div>'
        + section_links
        + _tl_period_jump_links(timeline, outlook_rows=outlook_rows)
        + '</nav>'
    )


def _build_prashna_panel(prashna_result: Any) -> str:
    """P-7: Render a compact Prashna summary card for the career timeline report.

    Accepts either a PrashnaResult dataclass or a PrashnaResponse pydantic model.
    Returns empty string if prashna_result is None.
    """
    if prashna_result is None:
        return ""
    try:
        # Support both PrashnaResult and PrashnaResponse (dict-like access)
        def _g(key, default=""):
            if hasattr(prashna_result, key):
                return getattr(prashna_result, key) or default
            if isinstance(prashna_result, dict):
                return prashna_result.get(key, default)
            return default

        verdict      = _g("verdict",         "UNKNOWN")
        verdict_lbl  = _g("verdict_label",   verdict)
        confidence   = _g("confidence_pct",  0)
        timing       = _g("timing_estimate", "—")
        question     = _g("question",        "")
        category_lbl = _g("category_label",  _g("category", "Horary Query"))
        pos_rules    = _g("classical_rules_fired", []) or []
        neg_rules    = _g("denial_rules_fired", []) or []
        moon_status  = _g("moon_status", "")
        kp_sublord   = _g("kp_sub_lord_verdict", "")
        moment       = _g("moment", "")

        # Verdict colour
        vcolor = {"YES": "#22c55e", "NO": "#ef4444", "CONDITIONAL": "#f59e0b",
                  "UNCERTAIN": "#64748b"}.get(verdict, "#64748b")

        pos_html = "".join(
            f'<li style="color:#86efac;font-size:12px;margin:2px 0">✓ {r}</li>'
            for r in pos_rules[:4]
        )
        neg_html = "".join(
            f'<li style="color:#fca5a5;font-size:12px;margin:2px 0">✗ {r}</li>'
            for r in neg_rules[:3]
        )
        rules_html = (
            f'<ul style="list-style:none;padding:0;margin:8px 0">{pos_html}{neg_html}</ul>'
            if (pos_rules or neg_rules) else ""
        )

        kp_note  = f'<div style="font-size:11px;color:#94a3b8;margin-top:4px">KP: {kp_sublord}</div>' if kp_sublord else ""
        moon_note = f'<div style="font-size:11px;color:#94a3b8">Moon: {moon_status}</div>' if moon_status else ""
        q_note   = f'<div style="font-style:italic;color:#cbd5e1;font-size:12px;margin-bottom:8px">"{question}"</div>' if question else ""
        time_note = f'<div style="font-size:11px;color:#94a3b8">Timing: {timing}</div>' if timing else ""

        return (
            '<div class="mt-block" style="border:1px solid #334155;border-radius:10px;'
            'background:#0f172a;padding:20px;margin-bottom:24px">'
            '<h2 class="section-heading" style="margin-bottom:12px">Prashna (Horary Analysis)</h2>'
            f'<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">{category_lbl}'
            f'{(" · " + moment) if moment else ""}</div>'
            f'{q_note}'
            '<div style="display:flex;align-items:center;gap:16px;margin:12px 0">'
            f'<div style="font-size:28px;font-weight:700;color:{vcolor}">{verdict}</div>'
            f'<div style="font-size:14px;color:#e2e8f0">{verdict_lbl}</div>'
            f'<div style="margin-left:auto;font-size:13px;color:#94a3b8">'
            f'Confidence: <strong style="color:#e2e8f0">{confidence}%</strong></div>'
            '</div>'
            f'{time_note}{kp_note}{moon_note}'
            f'{rules_html}'
            '</div>'
        )
    except Exception:
        return ""




def _build_foreign_module_condensed_html(foreign_opps: list, year_from: int = 0, year_to: int = 0) -> str:
    """Condensed, inline foreign-opportunity summary (2026-07-05).

    Replaces the old "open in a new HTML page" link card — the opportunity
    windows now render directly on the canvas as compact single-line rows,
    scoped to the same last-1-year-through-next-3-years window as the Career
    Roadmap, instead of the full multi-decade detail cards in the standalone
    report (still generated separately via generate_foreign_report_beside()
    for anyone who wants the exhaustive version).
    """
    if not foreign_opps:
        return ""

    scoped = foreign_opps
    if year_from and year_to:
        scoped = [
            o for o in foreign_opps
            if o.get("start_date", "")[:4].isdigit()
            and year_from <= int(o["start_date"][:4]) <= year_to
        ]
    if not scoped:
        return ""

    best = max(scoped, key=lambda o: o["foreign_score"])
    best_lbl = f"{best['md_lord']}–{best['ad_lord']} ({_fmt_date(best['start_date'][:7])})"
    summary = (
        f"{len(scoped)} window{'s' if len(scoped) != 1 else ''} in this span &middot; "
        f"Peak: {esc(best_lbl)}"
    )

    rows_html = []
    for opp in sorted(scoped, key=lambda o: o.get("start_date", "")):
        sc = opp["foreign_score"]
        bar_w = int(sc * 100)
        bar_col = "#22c55e" if sc >= 0.65 else ("#f59e0b" if sc >= 0.45 else "#818cf8")
        tag = ("Past" if opp.get("is_past") else ("Active" if opp.get("is_current") else "Upcoming"))
        tag_cls = "fop-c-tag-past" if opp.get("is_past") else (
            "fop-c-tag-active" if opp.get("is_current") else "fop-c-tag-upcoming")
        geo = esc(opp.get("geo_affinity", "")) or "—"
        rows_html.append(
            '<div class="fop-c-row">'
            f'<div class="fop-c-dates">{esc(_fmt_date(opp.get("start_date","")[:7]))} &rarr; '
            f'{esc(_fmt_date(opp.get("end_date","")[:7]))}</div>'
            f'<div class="fop-c-lords">{esc(opp.get("md_lord",""))}&ndash;{esc(opp.get("ad_lord",""))}</div>'
            f'<div class="fop-c-bar"><div class="fop-c-fill" style="width:{bar_w}%;background:{bar_col}"></div></div>'
            f'<span class="fop-c-tag {tag_cls}">{tag}</span>'
            f'<div class="fop-c-geo">{geo}</div>'
            '</div>'
        )

    return (
        '<div class="cal-section fop-condensed-section">'
        '<h2 class="cal-heading">Foreign Opportunity Windows</h2>'
        f'<div class="rmap-sub">{summary}</div>'
        f'<div class="fop-c-list">{"".join(rows_html)}</div>'
        '</div>'
    )





# BUG FIX (2026-07-05): _CAREER_WEATHER, _ROADMAP_SIGNAL_DOT, and _NET_SIGNAL_COLOR
# were all referenced below (and further down in the node-rendering loop) without
# ever being defined anywhere in this module — each one is a fresh NameError that
# crashes _build_career_roadmap_html() and, in turn, generate_career_timeline_report()
# entirely (silently caught by the CLI, producing no HTML output). Defining all three
# here, alongside the already-fixed _ROADMAP_EVENT_COLORS.
#
# Ordered highest-bar-first; _career_weather() takes the first row whose thresholds
# are both satisfied by the combined score/signal.
_ROADMAP_SIGNAL_DOT = {
    "favorable":   "#059669",
    "mixed":       "#D97706",
    "neutral":     "#94A3B8",
    "challenging": "#DC2626",
}

_NET_SIGNAL_COLOR = {
    "Favorable":  ("#065F46", "#D1FAE5"),
    "Mixed":      ("#92400E", "#FEF3C7"),
    "Challenging":("#991B1B", "#FEE2E2"),
}


def _kp_house_chain_summary(kp_cusps: dict) -> dict:
    """Phase-1 fix (2026-07-05 roadmap): print the full KP cusp chain
    (sign lord / star lord / sub lord / sub-sub lord) for every career-relevant
    house (2/6/10/11/12), not just H10 in isolation. This is the concrete data
    a KP promotion/job-change/loss verdict needs (2+6+10+11 for promotion,
    3+10+12 for job change, 8+12+weak-10 for loss) — previously only H10 was
    surfaced in the sidebar, and the year narratives had no access to the
    other houses at all, so they could never actually apply the classical
    multi-house KP test even though the source cusp data (payload.kp_cusps)
    always had it."""
    chain = {}
    for h, theme in _KP_CAREER_HOUSES.items():
        cusp = kp_cusps.get(f"H{h}", {}) or {}
        if not cusp:
            continue
        chain[f"H{h}"] = {
            "theme":      theme,
            "sign_lord":  cusp.get("sign_lord", ""),
            "star_lord":  cusp.get("star_lord", ""),
            "sub_lord":   cusp.get("sub_lord", ""),
            "sub_sub_lord": cusp.get("sub_sub_lord", ""),
        }
    return chain


def _build_year_llm_context(best: dict, row: dict, kp_cusps: dict = None, key=None,
                             house_lords: dict = None, d10_strength: float = None,
                             fixed_karakas: dict = None, natal_facts: dict = None) -> dict:
    """Assemble the exact factor values the roadmap-narrative LLM prompt needs
    to explain WHY a year's score/event is what it is — KN Rao dasha, KP,
    Jaimini, D10, D24, D60, plus the year's transit picture. Pulled straight
    from the dominant block's sub_scores (see timeline.py _score_period /
    enhancer_score_delta) — no numbers are invented, only real computed ones.

    `key` lets the caller pass a composite (year, sub-period-index) identifier
    instead of a bare year, so a calendar year that contains a mid-year dasha
    change can generate one narrative per dasha sub-period instead of forcing
    everything into a single blended year narrative (Phase 1 fix, 2026-07-05).

    User-reported gap fix (2026-07): the LLM prompt (`_ROADMAP_SYSTEM_PROMPT`
    in llm_narrative_builder.py) explicitly asks the model to state each
    dasha lord's house lordships — but this context dict never included
    `house_lords`, even though `payload.house_lords` is deterministically
    derivable from Lagna and is already used everywhere else in scoring
    (timeline.py, foreign_opportunities.py). Without it in the LLM's own
    prompt, the model correctly (per its "don't invent facts" instruction)
    reported the data as absent — a real gap, but in what the LLM was fed,
    not in whether the engine computes it. Fixing at the source instead of
    just noting it."""
    sub = best.get("sub_scores", {}) or {}
    hl = house_lords or {}
    _md_lord = best.get("md_lord", "")
    _ad_lord = best.get("ad_lord", "")
    _houses_ruled_by = {}
    for h_str, lord in hl.items():
        _houses_ruled_by.setdefault(lord, []).append(h_str)
    return {
        "year":                  key if key is not None else row.get("year"),
        "period_start":          best.get("start_date", ""),
        "period_end":            best.get("end_date", ""),
        # BUG FIX (flatline 0.0% score, 2026-07-05): this dict previously read
        # best.get("score", ...) / best.get("event", ...) -- but timeline.py's
        # per-period blocks (_score_period / the block-builder around line
        # 3616-3621) store these under "career_score" and "event_type"
        # respectively. "score"/"event" are never set anywhere in timeline.py,
        # so both lookups silently fell back to their defaults (0.0 and "")
        # on every single year/period, producing the literal 0.0% shown next
        # to every "Headwinds"/"Steady, Mixed" weather badge regardless of
        # the real (non-flat) underlying career_score. Root cause was a key-
        # name mismatch, not a missing multiplier or circular reference --
        # fixed by reading the correct keys.
        "career_score_pct":      round(best.get("career_score", 0.0) * 100, 1),
        "event_type":            best.get("event_type", ""),
        # Display-only human label (may read "Promotion Runway + Executive
        # Visibility" instead of the raw "LEADERSHIP_EXPANSION" event_type
        # when AmK-activation/promotion-cycle/senior-stage conditions are
        # met) -- kept separate from "event_type" above so tone-mapping/
        # CSS-class lookups that key off the raw type string still work.
        "event_type_display":    _tl_display_event_type(best),
        "dasha_kn_rao": {
            "md_lord": _md_lord,
            "ad_lord": _ad_lord,
            "chara_dasha_score": sub.get("chara_dasha_score"),
            "md_lord_houses_ruled": sorted(_houses_ruled_by.get(_md_lord, []), key=lambda x: int(x) if str(x).isdigit() else 0),
            "ad_lord_houses_ruled": sorted(_houses_ruled_by.get(_ad_lord, []), key=lambda x: int(x) if str(x).isdigit() else 0),
        },
        "kp": {
            "kp_cusp_alignment":      best.get("kp_cusp_alignment"),
            "kp_ssl_score":           sub.get("kp_ssl_score"),
            "kp_ruling_planets_score": sub.get("kp_ruling_planets_score"),
            "kp_nakshatra_chain":     sub.get("kp_nakshatra_chain"),
            "kp_house_chain":         _kp_house_chain_summary(kp_cusps or {}),
        },
        "jaimini": {
            # Gap fix (2026-07-05, user-reported): AK/AmK are fixed chara
            # karakas for the native's WHOLE chart/lifetime in real Jaimini
            # technique — they must never be recomputed or re-labeled per
            # year. `fixed_karakas` carries the one-time-computed identity +
            # canonical domain label (same _AK_ROLE_MAP used in the chart-level
            # Outcome Snapshot cell) so the LLM anchors every year's prose to
            # the identical planet/label instead of improvising a fresh
            # description each time. `jaimini_role` below remains the
            # legitimately period-varying text — it describes whether THIS
            # year's MD/AD lord happens to BE the (fixed) AK/AmK/other karaka,
            # which is a real per-period fact, not a re-identification of the
            # karaka itself.
            # BUGFIX (2026-07-19, user-reported audit): this read lowercase
            # "ak"/"amk" keys, but `fixed_karakas` is always built with
            # uppercase "AK"/"AmK" keys (see the Outcome Snapshot cell and
            # generate_career_timeline_report()'s own
            # fixed_karakas={"AK":...,"AmK":...} construction) -- so this was
            # silently blank on every single year of every report. It also
            # looked up "ak_label"/"amk_label" sub-keys that never existed
            # anywhere; the actual canonical domain label lives in the
            # module-level _AK_ROLE_MAP this docstring already references.
            "fixed_atmakaraka":        (fixed_karakas or {}).get("AK", ""),
            "fixed_atmakaraka_domain": _AK_ROLE_MAP.get((fixed_karakas or {}).get("AK", ""), ""),
            "fixed_amatyakaraka":        (fixed_karakas or {}).get("AmK", ""),
            "fixed_amatyakaraka_domain": _AK_ROLE_MAP.get((fixed_karakas or {}).get("AmK", ""), ""),
            "jaimini_role":          best.get("jaimini_role", ""),
            "jaimini_score":         sub.get("jaimini_score"),
            "active_houses":         best.get("active_houses", []),
        },
        # Gap fix (2026-07-05, user-reported): active yogas were named
        # (e.g. "NakParivartana_Saturn_Ketu") in sub_scores but no explanation
        # of what they mean reached the LLM narrative layer, so the prose
        # never unpacked them. `active_yoga_explanations` gives the LLM a
        # ready-made explanation per detected tag to work from — it should
        # still translate this into report-appropriate prose, not repeat it
        # verbatim, but must not invent a different meaning for the yoga.
        "active_yogas":              sub.get("active_yogas", []),
        "active_yoga_explanations":  _explain_active_yogas(sub.get("active_yogas", [])),
        # Gap fix (2026-07-05, user-reported): two whole-chart natal facts that
        # are permanently true (not period-dependent) were computed elsewhere
        # in the engine (planet_house / sav_points_houses) but never reached
        # this LLM context at all, so they never appeared in any year's
        # narrative even when highly relevant — a 10th-house occupant (e.g.
        # Ketu) is a classical natal career signal every year should be able
        # to reference, and the Ashtakavarga (SAV) H10 bindu count is the
        # single strongest quantitative career signal available for charts
        # where it is high. Passed once, identically, to every year — this is
        # natal (chart-level) data, not something that varies by year.
        "natal_10th_house_occupants": (natal_facts or {}).get("h10_occupants", []),
        "natal_ketu_house":           (natal_facts or {}).get("ketu_house"),
        "sav_h10_bindus":             (natal_facts or {}).get("sav_h10"),
        "sav_h6_bindus":              (natal_facts or {}).get("sav_h6"),
        "sav_h11_bindus":             (natal_facts or {}).get("sav_h11"),
        "sav_h12_bindus":             (natal_facts or {}).get("sav_h12"),
        "sav_all_houses":             (natal_facts or {}).get("sav_all_houses", {}),
        "d10_dashamsha_alignment":   sub.get("d10_alignment"),
        "d10_full_score":            sub.get("d10_full_score"),
        # Gap fix (2026-07, deep-audit round 2): the whole-chart, period-
        # independent D10 strength (shown in the sidebar as "D10 Strength:
        # Moderate 0.50") was never included in this per-period LLM context,
        # only the per-period d10_alignment/d10_full_score were — so the LLM
        # had no way to reconcile "D10 full score is 0.015, weak" against the
        # sidebar's separate "D10 Strength: Moderate (0.50)" and produced
        # unreconciled, apparently-contradictory prose. Passing both together
        # lets the prompt's reconciliation instruction actually be followed.
              "d10_strength_whole_chart":  (natal_facts or {}).get("d10_strength"),
        # Gap fix (Gap 4): D10 lagna sign and D10 10th-lord were computed
        # elsewhere (payload.d10_lagna_sign / payload.d10_house_lords) but
        # never wired into natal_facts, so this per-period context always
        # read None for them even though the real chart had the data.
        "d10_lagna":                  (natal_facts or {}).get("d10_lagna"),
        "d10_tenth_lord":             (natal_facts or {}).get("d10_tenth_lord"),
        "transit": {
            # Gap fix (2026-07-05, user-reported): Saturn transit commentary
            # was generic boilerplate not anchored to this chart's actual
            # natal Saturn placement/dignity. `_annual_transit_snapshot()` in
            # timeline.py now computes saturn_natal_house/dignity/rules_houses
            # and folds them into the signal itself — surface the same raw
            # facts here too so the LLM prose can name them explicitly
            # instead of only reflecting them through the pre-computed signal.
            "saturn_signal":         sub.get("saturn_signal"),
            "saturn_natal_house":    (natal_facts or {}).get("saturn_natal_house"),
            "saturn_natal_dignity":  (natal_facts or {}).get("saturn_natal_dignity"),
            "saturn_rules_houses":   (natal_facts or {}).get("saturn_rules_houses", []),
            "jupiter_signal":        sub.get("jupiter_signal"),
        },
    }


def _build_career_roadmap_html(timeline, outlook_rows, career_ctx=None,
                                kp_cusps=None, house_lords=None,
                                d10_strength=None, fixed_karakas=None,
                                natal_facts=None, payload=None):
    """Render the merged multi-year career roadmap (last 1yr + this yr + next
    N yrs), combining each year's dominant career event/score with its
    Jupiter/Saturn/Rahu-Ketu transit themes, plus an LLM-generated (or
    deterministic-fallback) narrative and a KN-Rao/KP/Jaimini/D10/D24/D60
    astrological explanation per year.
    """
    if not outlook_rows:
        return ""

    career_ctx = career_ctx or {}
    timeline = timeline or []

    year_contexts = []
    year_meta = {}
    for row in outlook_rows:
        yr = row.get("year")
        if yr is None:
            continue
        _year_blocks = [
            b for b in timeline
            if str(b.get("start_date", ""))[:4] <= str(yr) <= str(b.get("end_date", ""))[:4]
        ]
        if not _year_blocks:
            continue
        # Date-alignment fix (2026-07-07, user-reported): picking the block
        # with the highest career_score, with no regard to whether it is
        # actually running as of `today`, could make the calendar year
        # flagged is_current_year ("Current" badge) display an AD that had
        # already ENDED before today, while the AD genuinely active today —
        # which also overlaps the following calendar year — got selected as
        # "best" there instead and showed up mislabeled "Upcoming". E.g. an
        # AD ending 2026-06-01 was shown as the "2026, Current" card even
        # though today was 2026-07-07 (5+ weeks into the next AD), while that
        # next AD appeared only under "2027, Upcoming".
        # Fix: for the one row flagged is_current_year, prefer whichever
        # overlapping block is itself flagged is_current (set in
        # timeline.py._slice_window as start_date <= today < end_date) —
        # i.e. the AD actually running today — falling back to max
        # career_score only if no block claims is_current (should not
        # normally happen for the current-year row, but kept as a safe
        # fallback). Past/future years keep the original score-based pick.
        if row.get("is_current_year"):
            _active_now = next((b for b in _year_blocks if b.get("is_current")), None)
            best = _active_now or max(_year_blocks, key=lambda b: b.get("career_score", 0.0))
        else:
            best = max(_year_blocks, key=lambda b: b.get("career_score", 0.0))
        ctx = _build_year_llm_context(
            best, row, kp_cusps=kp_cusps, key=yr, house_lords=house_lords,
            d10_strength=d10_strength, fixed_karakas=fixed_karakas, natal_facts=natal_facts,
        )
        year_contexts.append(ctx)
        year_meta[yr] = {"row": row, "best": best}

    # Gap fix (2026-07-07, user-reported): when a single AD spans parts of
    # two calendar years (e.g. Jupiter-Rahu running 01-May-2029 to
    # 01-Jun-2030), the per-calendar-year loop above resolves the SAME
    # underlying block as "best" for both years, so two fully duplicate
    # cards were rendered back to back (identical narrative/KP/D10/PD
    # content), differing only in the year number and Past/Current/Upcoming
    # badge. Collapse consecutive years that resolved to the identical
    # block into a single card labeled with the year span, keeping
    # whichever row is most "advanced" (Current > Upcoming > Past) for the
    # badge/date-alignment logic used later in the loop.
    def _best_key(_b):
        return (_b.get("start_date"), _b.get("end_date"), _b.get("md_lord"), _b.get("ad_lord"))

    _deduped = []
    for ctx in year_contexts:
        yr = ctx["year"]
        key = _best_key(year_meta.get(yr, {}).get("best", {}))
        if _deduped:
            prev_yr = _deduped[-1]["year"]
            if _best_key(year_meta.get(prev_yr, {}).get("best", {})) == key:
                first_yr = year_meta[prev_yr].get("_span_first", prev_yr)
                year_meta[prev_yr]["_span_first"] = first_yr
                year_meta[prev_yr]["_span_last"] = yr
                this_row = year_meta.get(yr, {}).get("row", {})
                prev_row = year_meta.get(prev_yr, {}).get("row", {})
                if this_row.get("is_current_year") and not prev_row.get("is_current_year"):
                    year_meta[prev_yr]["row"] = this_row
                elif not this_row.get("is_past", False) and prev_row.get("is_past", False):
                    year_meta[prev_yr]["row"] = this_row
                continue  # merged into previous card, don't emit a duplicate
        _deduped.append(ctx)
    year_contexts = _deduped

    if not year_contexts:
        return ""

    from Job_Career.timeline import _build_md_narrative

    # LLM on/off switch: same consent gate used everywhere else in the career
    # pipeline (career_mode_runner.py / career_field_report_v2.py). Without
    # this check, generate_annual_roadmap_narratives_sync() only looks at
    # whether an API key is configured — it would silently call the LLM even
    # when LLM_REPORT_CONSENT=false / external_llm_consent is unset.
    _env_llm_consent = str(os.getenv("LLM_REPORT_CONSENT", "")).strip().lower() in {"1", "true", "yes", "on"}
    _llm_consent = bool(getattr(payload, "external_llm_consent", False)) or _env_llm_consent

    llm_narratives = {}
    if _llm_consent:
        try:
            from .llm_narrative_builder import generate_annual_roadmap_narratives_sync
            llm_narratives = generate_annual_roadmap_narratives_sync(year_contexts, career_ctx) or {}
        except Exception as _llm_err:
            logger.warning("Annual roadmap LLM narrative generation skipped: %s", _llm_err)
            llm_narratives = {}
    else:
        logger.info(
            "[PRIVACY] Annual roadmap LLM narratives skipped: external_llm_consent is "
            "false and LLM_REPORT_CONSENT is not set."
        )

    cards = []
    _period_idx = 0
    for ctx in year_contexts:
        yr = ctx["year"]
        meta = year_meta.get(yr, {})
        row = meta.get("row", {})
        best = meta.get("best", {})
        _span_first = meta.get("_span_first")
        _span_last = meta.get("_span_last")
        yr_label = f"{_span_first}–{_span_last}" if _span_last and _span_last != _span_first else str(yr)
        _period_idx += 1
        _period_anchor_id = f"period-{_period_idx}"

        score = ctx.get("career_score_pct", 0.0) / 100.0
        net_signal = row.get("net_signal", "")
        weather_emoji, weather_label = _career_weather(score, net_signal)

        _llm = llm_narratives.get(yr) or llm_narratives.get(str(yr)) or {}
        astro_html = _llm.get("astro_explanation_html", "")
        # BUGFIX (2026-07-19, user-reported audit): _ROADMAP_SYSTEM_PROMPT
        # asks the LLM for TWO segregated layers per year -- "narrative_html"
        # (plain-language, 4-5 paragraph) and "astro_explanation_html"
        # (technical). Only astro_explanation_html was ever rendered below;
        # narrative_html was fetched into `_llm` and then silently discarded,
        # with the deterministic _build_md_narrative() shown in its place
        # (mislabeled "Practical / Astrologer View" for what was actually a
        # non-LLM fallback). Use the LLM's own plain-language narrative when
        # it's available, and fall back to the deterministic narrative only
        # when the LLM call didn't run/failed (e.g. LLM_REPORT_CONSENT=false).
        llm_narrative_html = _llm.get("narrative_html", "")
        narrative = llm_narrative_html or _build_md_narrative(
            best.get("md_lord", ""), _fmt_date(best.get("start_date", "")),
            _fmt_date(best.get("end_date", "")), payload,
            lagna_sign=(natal_facts or {}).get("lagna_sign", ""),
            career_ctx=career_ctx, jaimini_role=best.get("jaimini_role", ""),
            kp_cusp_score=best.get("kp_cusp_alignment") or 0.0,
            ad_event_summary=ctx.get("event_type", ""),
        )

        is_past = row.get("is_past", False)
        is_current = row.get("is_current_year", False)
        year_badge = "Past" if is_past else ("Current" if is_current else "Upcoming")

        # ── GAP 1 fix (2026-07-07, user-reported): Jupiter/Sun event label
        # was rendering as an unqualified "Leadership Expansion" — reading
        # as more certain/positive than the underlying signal supports. This
        # appends the requested caveat sentence directly under the
        # narrative for Jupiter/Sun periods resolving to a leadership/
        # authority-flavored event, without changing event_type or score.
        # See gap_corrections_career_timeline_2026_07.jupiter_sun_event_caveat().
        _caveat_html = ""
        try:
            from Job_Career.gap_corrections_career_timeline_2026_07 import jupiter_sun_event_caveat
            _caveat_text = jupiter_sun_event_caveat(
                best.get("md_lord", ""), best.get("ad_lord", ""), ctx.get("event_type", "")
            )
            if _caveat_text:
                _caveat_html = f'<div class="rmap-event-caveat">{esc(_caveat_text)}</div>'
        except Exception as _cav_err:
            logger.warning("Jupiter/Sun event caveat skipped: %s", _cav_err)

        # ── GAP 2 fix (2026-07-07, user-reported): KP override display ──
        # When the KP promotion-house-vs-foreign/leadership-house override
        # fired in timeline.py._classify_event() (weak 2/6/10/11 KP tie,
        # strong 12/3/9 or 10/1 KP tie), the block carries
        # kp_promotion_override_label — surface it plainly so a reader sees
        # WHY this period is not simply labelled a formal promotion.
        _kp_override_html = ""
        _kp_override_label = best.get("kp_promotion_override_label", "")
        # GAP 3 fix (2026-07-07 follow-up audit): surface the explicit
        # deterministic kp_override_applied/kp_override_reason fields (set
        # in timeline.py._classify_event() via
        # gap_corrections_career_timeline_2026_07.kp_promotion_override_decision())
        # alongside the existing narrative label.
        _kp_override_applied = bool(best.get("kp_override_applied", False))
        _kp_override_reason = best.get("kp_override_reason", "")
        if _kp_override_label or _kp_override_applied:
            _kp_override_html = (
                '<div class="rmap-event-caveat rmap-kp-override">'
                '<strong>KP override:</strong> promotion-significator houses (2/6/10/11) '
                'are weak for this period while foreign/job-change or leadership houses are '
                'strong — final read: ' + esc(_kp_override_label) + '.'
                + (f'<div class="rmap-kp-override-reason">kp_override_applied=true &middot; {esc(_kp_override_reason)}</div>'
                   if _kp_override_applied else '')
                + '</div>'
            )

        yogas_html = ""
        _yoga_expl = ctx.get("active_yoga_explanations") or {}
        if _yoga_expl:
            yogas_html = "".join(
                '<div class="roadmap-yoga"><b>' + esc(tag) + '</b>: ' + esc(expl) + '</div>'
                for tag, expl in _yoga_expl.items()
            )

        natal_note = ""
        _h10_occ = ctx.get("natal_10th_house_occupants") or []
        if _h10_occ:
            natal_note += '<div class="roadmap-natal">Natal 10th-house occupant(s): ' + esc(", ".join(_h10_occ)) + '</div>'
        if ctx.get("natal_ketu_house") == 10:
            natal_note += ('<div class="roadmap-natal">Ketu in the 10th house is a permanent natal '
                            'signal of detachment from conventional status-seeking, volatility around '
                            'designation/title, and a career path defined more by non-attachment to '
                            'outcome than by pursuit of promotion.</div>')
        if ctx.get("sav_h10_bindus"):
            natal_note += ('<div class="roadmap-natal">Ashtakavarga SAV H10 (career house strength): '
                            + esc(str(ctx["sav_h10_bindus"])) + ' bindus.</div>')

        # Gap fix (2026-07-06): per-year scoring matrix (`.rmap-matrix`), KP
        # cusp-chain panel (`.rmap-kp-panel`), and D10 manifestation/verdict
        # (`.rmap-d10-manifestation`/`.rmap-d10-final-verdict`) — all CSS-only
        # dead classes before this pass. Built from `sub_scores` (the real
        # per-block promotion/income/job_change/foreign/risk/stability/
        # visibility dimension scores already computed in timeline.py) and
        # the same `_kp_house_chain_summary`/d10_alignment fields already
        # surfaced to the LLM context above — no new computation invented,
        # only rendered. Omitted entirely (not fabricated) when a chart's
        # sub_scores/kp/d10 fields are genuinely absent for that period.
        _sub_scores = best.get("sub_scores", {}) or {}
        # Gap 3 fix (2026-07-07, user-reiterated): labels renamed to match the
        # exact requested vocabulary ("Job Loss Risk" not "Risk", "Protection"
        # not "Stability" — stability_score is literally the protection-from-
        # disruption signal, so this is a rename, not a new computation).
        # "Career Score" (the block's own aggregate) is now the first row so
        # the whole requested list — Career Score / Promotion / Job Change /
        # Job Loss Risk / Income / Foreign / Protection — appears as one
        # decomposition, per-window.
        _matrix_dims = [
            ("Career Score", best.get("career_score")),
            ("Promotion",    _sub_scores.get("promotion_score")),
            ("Job Change",   _sub_scores.get("job_change_score")),
            ("Job Loss Risk", _sub_scores.get("risk_score")),
            ("Income",       _sub_scores.get("income_score")),
            ("Foreign",      _sub_scores.get("foreign_score")),
            ("Protection",   _sub_scores.get("stability_score")),
            ("Visibility",   _sub_scores.get("visibility_score")),
        ]
        _matrix_dims = [(lbl, v) for lbl, v in _matrix_dims if v is not None]
        matrix_html = ""
        if _matrix_dims:
            _rows = "".join(
                '<div class="rmap-matrix-row"><span class="rmap-matrix-name">' + esc(lbl) + '</span>'
                '<div class="rmap-matrix-track"><div class="rmap-matrix-fill" style="width:' + str(round(min(1.0, max(0.0, v)) * 100)) + '%"></div></div>'
                '<span class="rmap-matrix-pct">' + str(round(min(1.0, max(0.0, v)) * 100)) + '%</span></div>'
                for lbl, v in _matrix_dims
            )
            # GAP 5 fix (2026-07-07 follow-up audit, user-reported): when
            # promotion_score is high (e.g. 0.818) but final_event_type is
            # something else (e.g. LEADERSHIP_EXPANSION after a KP/D10/D9
            # override), a reader sees the two numbers/labels side by side
            # with no explanation of why the high score didn't "win" as a
            # literal PROMOTION label. This adds one small, always-present
            # caption clarifying the relationship — display-only, does not
            # change promotion_score or final_event_type themselves.
            _matrix_caption_html = (
                '<div class="rmap-matrix-caption">Note: promotion_score reflects raw '
                'promotion-potential signal strength before KP/D10/D9 override checks. '
                'final_event_type ("' + esc(str(ctx.get("event_type", "") or "")) + '") is the '
                'result after those checks are applied — a high promotion_score does not by '
                'itself guarantee a title promotion.</div>'
            )
            matrix_html = (
                '<div class="rmap-matrix"><div class="rmap-year-subhead">Score Breakdown</div>'
                + _rows + _matrix_caption_html + '</div>'
            )

        _kp_chain = ctx.get("kp", {}).get("kp_house_chain") or {}
        kp_panel_html = ""
        _kp_ev: List[Dict[str, Any]] = []   # populated below when _kp_chain is present; used by why_html
        if _kp_chain:
            _kp_rows = "".join(
                '<div class="rmap-kp-row"><span class="rmap-kp-house">' + esc(str(h)) + '</span>'
                '<span class="rmap-kp-theme">' + esc(v.get("theme", "")) + '</span>'
                '<span class="rmap-kp-chain">' + esc(" / ".join(
                    x for x in (v.get("sign_lord"), v.get("star_lord"), v.get("sub_lord"), v.get("sub_sub_lord")) if x
                )) + '</span></div>'
                for h, v in _kp_chain.items()
            )
            # Gap fix (2026-07-06): overall KP verdict line (`.rmap-kp-verdict`)
            # summarizing how many of the 4 core career houses (2/6/10/11) tie
            # back to the running MD/AD lord, plus a 12th-house block note —
            # and the full per-event-type breakdown (`.rmap-kp-event-verdicts`)
            # via the new `_kp_event_verdicts()` helper above. Both derived
            # from the same kp_house_chain already computed for the cusp-chain
            # rows just above; no new astrological inputs, only a second pass
            # over data already present.
            _core_houses = ("2", "6", "10", "11")
            _lords_now = {l for l in (best.get("md_lord", ""), best.get("ad_lord", "")) if l}
            _core_hits = 0
            _core_eval = 0
            for h in _core_houses:
                cusp = _kp_chain.get(f"H{h}")
                if not cusp:
                    continue
                _core_eval += 1
                _chain_lords = {cusp.get("sign_lord"), cusp.get("star_lord"),
                                 cusp.get("sub_lord"), cusp.get("sub_sub_lord")}
                if _chain_lords & _lords_now:
                    _core_hits += 1
            _h12 = _kp_chain.get("H12")
            _h12_block = False
            if _h12 and _lords_now:
                _h12_lords = {_h12.get("sign_lord"), _h12.get("star_lord"),
                              _h12.get("sub_lord"), _h12.get("sub_sub_lord")}
                _h12_block = bool(_h12_lords & _lords_now)
            kp_verdict_html = ""
            if _core_eval:
                if _core_hits >= 3:
                    _kpv_color, _kpv_word = "var(--green,#1E7B50)", "Supportive"
                elif _core_hits >= 2:
                    _kpv_color, _kpv_word = "var(--amber,#B8720A)", "Mixed"
                else:
                    _kpv_color, _kpv_word = "var(--red,#B33A2E)", "Weak"
                _block_note = ", 12th-house block present" if _h12_block else ""
                kp_verdict_html = (
                    f'<div class="rmap-kp-verdict" style="color:{_kpv_color}">'
                    f'KP Verdict: {_kpv_word} &mdash; {_core_hits} of {_core_eval} career houses '
                    f'(2/6/10/11) tied to the running MD/AD lord{_block_note}</div>'
                )
            _kp_ev = _kp_event_verdicts(_kp_chain, best.get("md_lord", ""), best.get("ad_lord", ""))
            kp_ev_html = ""
            if _kp_ev:
                _ev_rows = "".join(
                    '<div class="rmap-kp-ev-row"><span class="rmap-kp-ev-name">' + esc(e["name"]) + '</span>'
                    '<span class="rmap-kp-ev-verdict" style="color:' + e["color"] + '">' + esc(e["verdict"]) + '</span>'
                    '<span class="rmap-kp-ev-detail">' + esc(e["detail"]) + '</span></div>'
                    for e in _kp_ev
                )
                kp_ev_html = (
                    '<div class="rmap-kp-event-verdicts"><div class="rmap-year-subhead">'
                    'KP Verdict by Event Type</div>' + _ev_rows + '</div>'
                )
            kp_panel_html = (
                '<div class="rmap-kp-panel"><div class="rmap-year-subhead">'
                'KP Cusp Chain (Sign / Star / Sub / Sub-Sub Lord)</div>' + _kp_rows
                + kp_verdict_html + kp_ev_html + '</div>'
            )

        d10_verdict_html = ""
        _d10_score: Optional[float] = None   # populated below when available; used by why_html
        _d10_align = ctx.get("d10_dashamsha_alignment")
        _d10_full = ctx.get("d10_full_score")
        if _d10_align is not None or _d10_full is not None:
            _d10_score = _d10_full if _d10_full is not None else _d10_align
            try:
                _d10_score = float(_d10_score)
            except (TypeError, ValueError):
                _d10_score = 0.0
            if _d10_score >= 0.55:
                _d10_verdict, _d10_color = "Strong", "var(--green,#1E7B50)"
                _d10_manifest = "D10 supports a clean, comparatively direct manifestation of the D1 promise this period."
            elif _d10_score >= 0.3:
                _d10_verdict, _d10_color = "Moderate", "var(--amber,#B8720A)"
                _d10_manifest = "D10 gives partial support — the D1 signal can manifest but may need extra effort or a longer runway to land."
            else:
                _d10_verdict, _d10_color = "Weak", "var(--red,#B33A2E)"
                _d10_manifest = "D10 does not strongly support an easy/clean result — treat the D1 promise as needing more effort or a longer runway to land."

            _d10_theme = (best.get("sub_scores", {}) or {}).get("d10_lagna_career_theme", "") or ctx.get("d10_lagna_career_theme", "")
            if _d10_theme:
                _d10_manifest = _d10_manifest + " D10 Lagna theme: " + _d10_theme

            _d10_occ_map = (natal_facts or {}).get("d10_house_occupancy") or {}
            _occ_10 = _d10_occ_map.get("10") or _d10_occ_map.get(10) or []
            if _occ_10:
                occupancy_text = (
                    "D10 10th house (career/authority) directly occupied by "
                    + ", ".join(_occ_10)
                )
            else:
                occupancy_text = (
                    f"D10 alignment score of {_d10_score:.2f} reflects how directly the running "
                    f"{best.get('md_lord','')}-{best.get('ad_lord','')} period ties into the D10 "
                    f"10th/11th house structure this period."
                )
            if _d10_score >= 0.3:
                _d10_occ_cls, _d10_occ_label = "rmap-cx-support", "D10 Supports"
            else:
                _d10_occ_cls, _d10_occ_label = "rmap-cx-block", "D10 Blocks"

            d10_manifest_html = (
                f'<div class="rmap-d10-manifestation"><strong>D10 Manifestation:</strong> {esc(_d10_manifest)}</div>'
                f'<div class="rmap-d10-final-verdict" style="color:{_d10_color}">D10 Verdict: {esc(_d10_verdict)}</div>'
            )
            d10_verdict_html = (
                '<div class="rmap-d10-verdict"><div class="rmap-year-subhead">D10 Structural Table (This Period)</div>'
                f'<div class="rmap-cx-row {_d10_occ_cls}"><span class="rmap-cx-label">{_d10_occ_label}</span>'
                f'<span class="rmap-cx-items">{esc(occupancy_text)}</span></div>'
                + d10_manifest_html + '</div>'
            )

        # ── Why this event / why not another (Gap 2, 2026-07-07) ─────────
        why_html = _tl_why_panel_html(
            ctx.get("event_type", ""), _kp_ev, _kp_chain, _sub_scores, _d10_score,
            transit_flags=best.get("transit_flags"),
        )

# Gap fix (2026-07-06): net-confidence "Contradiction Check" panel
        # (`.rmap-cx-panel`). Per project convention this must be gated on
        # RAW component signals that FEED career_score, never on career_score
        # itself (that would be circular). Every item below is read straight
        # from `sub_scores`/`best`, which are the pre-aggregate per-block
        # values timeline.py computes BEFORE they are summed into
        # career_score (yoga_bonus, d9_modifier, chandra_lagna_bonus,
        # gandanta_penalty, papa_kartari/kala_sarpa modifiers, sandhi flag,
        # macro_headwinds flag, jaimini_role/active_houses, D10 alignment).
        # Positive-valued/True signals become "Supporting" items, negative-
        # valued/True-headwind signals become "Blocking" items; the net line
        # is a simple support-count vs block-count comparison, not a re-use
        # of any already-final aggregate score.
        _support_items = []
        _block_items = []
        if (_sub_scores.get("yoga_bonus") or 0) > 0:
            _tags = ctx.get("active_yogas") or []
            _support_items.append("Active yoga(s): " + (", ".join(_tags) if _tags else f"+{_sub_scores['yoga_bonus']:.2f}"))
        if (_sub_scores.get("d9_modifier") or 0) > 0.005:
            _support_items.append(f"D9 dignity supportive (+{_sub_scores['d9_modifier']:.2f})")
        elif (_sub_scores.get("d9_modifier") or 0) < -0.005:
            _block_items.append(f"D9 dignity weak ({_sub_scores['d9_modifier']:.2f})")
        if (_sub_scores.get("chandra_lagna_bonus") or 0) > 0:
            _support_items.append(f"Chandra Lagna support (+{_sub_scores['chandra_lagna_bonus']:.2f})")
        if (_sub_scores.get("gandanta_penalty") or 0) > 0:
            _block_items.append(f"Gandanta penalty (-{_sub_scores['gandanta_penalty']:.2f})")
        if _sub_scores.get("is_sandhi"):
            _block_items.append("Dasha Sandhi (junction) — volatility flag")
        if best.get("macro_headwinds"):
            _block_items.append("Macro-economic headwinds active")
        if _sub_scores.get("d10_structural_score", 0) and _sub_scores["d10_structural_score"] >= 0.55:
            _support_items.append(f"D10 structurally strong ({_sub_scores['d10_structural_score']:.2f})")
        elif _sub_scores.get("d10_structural_score", 1) < 0.3:
            _block_items.append(f"D10 structurally weak ({_sub_scores.get('d10_structural_score', 0):.2f})")

        cx_html = ""
        if _support_items or _block_items:
            _net = "Favorable" if len(_support_items) > len(_block_items) else (
                "Challenging" if len(_block_items) > len(_support_items) else "Mixed")
            _net_color = {"Favorable": "var(--green,#1E7B50)", "Mixed": "var(--amber,#B8720A)",
                          "Challenging": "var(--red,#B33A2E)"}[_net]
            _sup_html = "".join(f"<li>{esc(s)}</li>" for s in _support_items) or "<li>None identified</li>"
            _blk_html = "".join(f"<li>{esc(s)}</li>" for s in _block_items) or "<li>None identified</li>"
            cx_html = (
                '<div class="rmap-cx-panel"><div class="rmap-year-subhead">Contradiction Check</div>'
                f'<div class="rmap-cx-row rmap-cx-support"><span class="rmap-cx-label">Supporting</span>'
                f'<ul>{_sup_html}</ul></div>'
                f'<div class="rmap-cx-row rmap-cx-block"><span class="rmap-cx-label">Blocking</span>'
                f'<ul>{_blk_html}</ul></div>'
                f'<div class="rmap-cx-net" style="color:{_net_color}">Net: {_net}</div></div>'
            )

        # ── B. Parent / Family Guidance panel (Gap 1, 2026-07-07) ────────
        family_html = _tl_family_panel_html(ctx.get("event_type", ""), best.get("career_risk"))

        # ── GAP 1 fix (2026-07-07, user-reported): Jupiter/Sun event label
        # was rendering as an unqualified "Leadership Expansion" — reading
        # as more certain/positive than the underlying signal supports. This
        # appends the requested caveat sentence directly under the
        # narrative for Jupiter/Sun periods resolving to a leadership/
        # authority-flavored event, without changing event_type or score.
        # See gap_corrections_career_timeline_2026_07.jupiter_sun_event_caveat().
        _caveat_html = ""
        try:
            from Job_Career.gap_corrections_career_timeline_2026_07 import jupiter_sun_event_caveat
            _caveat_text = jupiter_sun_event_caveat(
                best.get("md_lord", ""), best.get("ad_lord", ""), ctx.get("event_type", "")
            )
            if _caveat_text:
                _caveat_html = f'<div class="rmap-event-caveat">{esc(_caveat_text)}</div>'
        except Exception as _cav_err:
            logger.warning("Jupiter/Sun event caveat skipped: %s", _cav_err)

        # ── GAP 3 fix (2026-07-07, user-reported): D10 manifestation text ──
        # `d10_verdict_html` above already shows a numeric D10
        # alignment/structural score + one generic sentence. This adds the
        # SPECIFIC "how does this manifest" explanatory sentences (12th-house
        # global/MNC reading, Virgo-10th systems/analytics reading, Mercury-
        # in-12th technical-recognition reading) as an additional block,
        # layered alongside (not replacing) the existing score-based verdict.
        _d10_manifest_gap3_html = ""
        try:
            from Job_Career.gap_corrections_career_timeline_2026_07 import d10_manifestation_text
            _d10_10th_sign = (natal_facts or {}).get("d10_10th_sign", "") or ctx.get("d10_10th_sign", "")
            _manifest_sentences = d10_manifestation_text(
                d10_h10_lord=_sub_scores.get("d10_h10_lord", ""),
                d10_h10_lord_house=_sub_scores.get("d10_h10_lord_house", 0),
                d10_lagna_sign=_sub_scores.get("d10_lagna_sign", ""),
                d10_10th_sign=_d10_10th_sign,
                d10_h12_stellium=bool(_sub_scores.get("d10_h12_stellium")),
            )
            if _manifest_sentences:
                _sentences_html = "".join(f"<li>{esc(s)}</li>" for s in _manifest_sentences)
                _d10_manifest_gap3_html = (
                    '<div class="rmap-d10-manifestation-detail">'
                    '<div class="rmap-year-subhead">D10 Manifestation — How This Shows Up</div>'
                    f'<ul>{_sentences_html}</ul></div>'
                )
        except Exception as _d10g3_err:
            logger.warning("D10 manifestation text (Gap 3) skipped: %s", _d10g3_err)

        # ── GAP 6 fix (2026-07-07 follow-up audit, user-reported): D10
        # sub-dimension scores table. d10_alignment/d10_full_score can be
        # 0.0 for this period even though the SAME D10 facts used just above
        # for the manifestation narrative support 4 distinct structural
        # readings — rendered here as a small labeled-score table alongside
        # that narrative text. See
        # gap_corrections_career_timeline_2026_07.d10_subdimension_scores().
        _d10_subscores_html = ""
        try:
            _d10_sub_labels = [
                ("d10_title_support",              "D10 Title Support"),
                ("d10_global_delivery_support",     "D10 Global/Delivery Support"),
                ("d10_invisible_authority_support", "D10 Invisible Authority Support"),
                ("d10_clean_promotion_support",      "D10 Clean-Promotion Support"),
            ]
            _d10_sub_rows = "".join(
                f'<div class="rmap-d10-subscores-row"><span>{esc(label)}</span>'
                f'<strong>{_sub_scores.get(key):.2f}</strong></div>'
                for key, label in _d10_sub_labels if _sub_scores.get(key) is not None
            )
            if _d10_sub_rows:
                _d10_subscores_html = (
                    '<div class="rmap-d10-subscores"><div class="rmap-year-subhead">'
                    'D10 Sub-Dimension Scores</div>' + _d10_sub_rows + '</div>'
                )
        except Exception as _d10g6_err:
            logger.warning("D10 sub-dimension scores (Gap 6) skipped: %s", _d10g6_err)

        # ── GAP 4 fix (2026-07-07, user-reported): Jupiter-Rahu AD narrative
        # sub-phase breakdown. Display-only slice of the block's own actual
        # [start_date, end_date] into the 3 requested narrative sub-ranges;
        # see gap_corrections_career_timeline_2026_07's module docstring
        # ("GAP 4 root-cause finding") for the honest account of what the
        # underlying date-math investigation did and did not establish.
        _subphase_html = ""
        try:
            from Job_Career.gap_corrections_career_timeline_2026_07 import split_antardasha_subphases
            # GAP 1 fix (2026-07-07 follow-up audit): pass the block's real,
            # already-computed pratyantardasha chain so the sub-phase
            # breakdown uses genuine day-precision PD boundaries (up to 9
            # real sub-windows) instead of 3 hardcoded coarse buckets.
            _subphases = split_antardasha_subphases(
                best.get("md_lord", ""), best.get("ad_lord", ""),
                best.get("start_date", ""), best.get("end_date", ""),
                pratyantardashas=best.get("pratyantardashas") or [],
            )
            if _subphases:
                _rows_html = "".join(
                    f'<div class="rmap-subphase-row"><span class="rmap-subphase-range">'
                    f'{esc(_fmt_date(sp["start"]))} &rarr; {esc(_fmt_date(sp["end"]))}</span>'
                    f'<span class="rmap-subphase-label">{esc(sp["label"])}</span></div>'
                    for sp in _subphases
                )
                _subphase_html = (
                    '<div class="rmap-subphase-panel">'
                    '<div class="rmap-year-subhead">Sub-Phase Breakdown (Jupiter&ndash;Rahu)</div>'
                    + _rows_html + '</div>'
                )
        except Exception as _sp_err:
            logger.warning("Antardasha sub-phase breakdown (Gap 4) skipped: %s", _sp_err)

        card_html = (
            f'<div class="roadmap-year-card" id="{_period_anchor_id}">'
            f'<div class="roadmap-year-header"><span class="roadmap-year-badge roadmap-badge-{year_badge.lower()}">{esc(year_badge)}</span>'
            f'<span class="roadmap-year-label">{esc(yr_label)}</span>'
            f'<span class="roadmap-weather">{weather_emoji} {esc(weather_label)}</span></div>'
            f'<div class="roadmap-md-ad">{esc(best.get("md_lord",""))}&ndash;{esc(best.get("ad_lord",""))} '
            f'&middot; {esc(_fmt_date(best.get("start_date","")))} &rarr; {esc(_fmt_date(best.get("end_date","")))}</div>'
            f'<div class="rmap-audience-label rmap-audience-label-a">In Plain Language</div>'
            f'<div class="roadmap-narrative">{narrative}</div>'
            + _caveat_html + _kp_override_html
            + (
                f'<div class="rmap-audience-label rmap-audience-label-b">Astrological Explanation</div>'
                f'<div class="roadmap-astro-explanation">{astro_html}</div>'
                if astro_html else ""
            )
            + yogas_html + natal_note + matrix_html + kp_panel_html + d10_verdict_html
            + why_html + cx_html + family_html
            + _subphase_html + _d10_manifest_gap3_html + _d10_subscores_html
            + '</div>'
        )
        cards.append(card_html)

    return (
        '<div class="career-roadmap-section">'
        '<h2 class="rmap-section-title">Multi-Year Career Roadmap</h2>'
        + "".join(cards) +
        '</div>'
    )


_DIGNITY_BADGE_COLOR = {
    "EXALTED": "#15803d", "OWN": "#0f766e", "FRIEND": "#4338ca",
    "NEUTRAL": "#6b7280", "ENEMY": "#b8720a", "DEBILITATED": "#b91c1c",
    "MOOLTRIKONA": "#0f766e",
}


def _tl_dignity_badge(dignity: str) -> str:
    """Small colored badge span for a planet's dignity label, matching the
    `.planet-bar-dignity` CSS (border + text color, transparent bg)."""
    if not dignity:
        return ""
    d = str(dignity).upper()
    color = _DIGNITY_BADGE_COLOR.get(d, "#6b7280")
    label = d[:4] if d not in ("OWN", "FRIEND", "ENEMY") else d
    return f'<span class="planet-bar-dignity" style="color:{color};border-color:{color};">{esc(label)}</span>'


def _tl_strength_bar_class(score: float) -> str:
    if score >= 1.5:
        return "pbar-strong"
    if score >= 1.0:
        return "pbar-mod"
    return "pbar-weak"


def _tl_sidebar_html(payload: NatalPayloadV2, blocks: list, kp_cusps: dict,
                      natal_facts: dict, fixed_karakas: dict,
                      house_lords: dict, d10_strength: float,
                      confidence: dict, display_confidence_label: str = "") -> str:
    """Build the left-hand `.tl-sidebar` dashboard column: Snapshot,
    Planetary Strength, D10 Insights, KP Insights, KN Rao Insights,
    Parashara Insights, Jaimini Insights.

    Every value below is sourced from fields that already exist on the
    already-computed `payload` (NatalPayloadV2, populated upstream by
    engine_io.parse_json_payload()) or from the already-computed `blocks`
    (career_timeline) / `kp_cusps` locals passed in from
    generate_career_timeline_report(). No astrology is (re)computed here —
    this is pure HTML assembly. Any data point genuinely not present on the
    payload is rendered as an em dash "—" rather than fabricated, matching
    the missing-data convention used elsewhere in this module (see
    fixed_karakas / house_lords fallbacks above)."""
    em = "—"

    def g(attr, default=""):
        return getattr(payload, attr, default) or default

    # ── current period (Snapshot + KN Rao Insights) ──────────────────────
    current_block = next((b for b in blocks if b.get("is_current")), None) or (blocks[0] if blocks else {})
    md_lord = current_block.get("md_lord", "") or em
    ad_lord = current_block.get("ad_lord", "") or em

    lagna_sign = natal_facts.get("lagna_sign", "") or em
    # BUGFIX (2026-07-19, user-reported audit): this previously showed the
    # raw confidence.tier ("MODERATE") while the report header a few pixels
    # away shows retro_confidence_label()'s retro-validation-capped display
    # label ("Medium-High") -- two different confidence numbers in the same
    # report with no stated relationship between them, reading as an
    # internal contradiction. Show the SAME label everywhere a human reads
    # "confidence" in this report; callers that don't pass
    # display_confidence_label keep the old raw-tier behavior.
    conf_label = display_confidence_label or (confidence or {}).get("tier") or (confidence or {}).get("label") or em

    # ── Snapshot ───────────────────────────────────────────────────────
    snapshot_html = f"""<div class="outcome-bar">
      <div><div class="outcome-label">Lagna</div><div class="outcome-val">{esc(lagna_sign)}</div></div>
      <div><div class="outcome-label">Current Dasha</div><div class="outcome-val">{esc(md_lord)}&ndash;{esc(ad_lord)}</div></div>
      <div><div class="outcome-label">Atmakaraka</div><div class="outcome-val">{esc(fixed_karakas.get("AK","") or em)}</div></div>
      <div><div class="outcome-label">Confidence</div><div class="outcome-val">{esc(str(conf_label))}</div></div>
    </div>"""

    # ── Planetary Strength ────────────────────────────────────────────
    planet_strength = g("planet_strength", {}) or {}
    true_dignities = g("true_planet_dignities", {}) or g("planet_dignities", {}) or {}
    ak = fixed_karakas.get("AK", "")
    amk = fixed_karakas.get("AmK", "")
    h10_occupants = set((natal_facts.get("d10_house_occupancy") or {}).get("10", []) or [])
    planet_order = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
    rows = []
    for p in planet_order:
        score = planet_strength.get(p)
        if score is None:
            continue
        pct = max(0, min(100, round(score / 2.5 * 100)))
        bar_cls = _tl_strength_bar_class(score)
        tags = ""
        if p == ak:
            tags += '<span class="planet-bar-karaka">AK</span>'
        if p == amk:
            tags += '<span class="planet-bar-karaka">AmK</span>'
        dign = true_dignities.get(p, "")
        rows.append(
            f'<div class="planet-bar-row">'
            f'<div class="planet-bar-name">{esc(p)}{tags}{_tl_dignity_badge(dign)}</div>'
            f'<div class="planet-bar-track"><div class="planet-bar-fill {bar_cls}" style="width:{pct}%;"></div></div>'
            f'<div class="planet-bar-val">{score:.2f}</div>'
            f'</div>'
        )
    if rows:
        planet_panel_html = (
            '<div class="planet-panel"><div class="planet-panel-title">Planetary Strength (Shadbala)</div>'
            f'<div class="planet-panel-grid">{"".join(rows)}</div></div>'
        )
    else:
        planet_panel_html = (
            '<div class="planet-panel"><div class="planet-panel-title">Planetary Strength (Shadbala)</div>'
            f'<div class="planet-panel-grid">{em}</div></div>'
        )

    # ── D10 Insights ───────────────────────────────────────────────────
    d10_lagna = g("d10_lagna_sign", "") or em
    d10_10th_lord = (g("d10_house_lords", {}) or {}).get("10", "") or em
    d10_occ = (natal_facts.get("d10_house_occupancy") or {}).get("10", []) or []
    d10_occ_str = ", ".join(d10_occ) if d10_occ else em
    d10_strength_pct = f"{d10_strength:.2f}" if isinstance(d10_strength, (int, float)) else em
    d10_panel_html = f"""<div class="d10-panel"><div class="d10-panel-title">D10 (Dashamsha) Insights</div>
      <div class="d10-cells">
        <div class="d10-cell"><div class="d10-cell-label">D10 Lagna</div><div class="insight-cell-val">{esc(d10_lagna)}</div></div>
        <div class="d10-cell"><div class="d10-cell-label">D10 H10 Lord</div><div class="insight-cell-val">{esc(d10_10th_lord)}</div></div>
        <div class="d10-cell d10-cell-wide"><div class="d10-cell-label">H10 Occupants</div><div class="insight-cell-val">{esc(d10_occ_str)}</div></div>
        <div class="d10-cell d10-cell-wide"><div class="d10-cell-label">D10 Strength Score</div><div class="insight-cell-val">{esc(d10_strength_pct)}</div></div>
      </div></div>"""

    # ── KP Insights (H10 cuspal chain) ───────────────────────────────
    h10_cusp = (kp_cusps or {}).get("H10", {}) or {}
    kp_panel_html = f"""<div class="insight-panel"><div class="insight-panel-title">KP Insights &mdash; H10 Cuspal Chain</div>
      <div class="insight-cells">
        <div class="insight-cell"><div class="insight-cell-label">Sign Lord</div><div class="insight-cell-val">{esc(h10_cusp.get("sign_lord","") or em)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Star Lord</div><div class="insight-cell-val">{esc(h10_cusp.get("star_lord","") or em)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Sub Lord</div><div class="insight-cell-val">{esc(h10_cusp.get("sub_lord","") or em)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Sub-Sub Lord</div><div class="insight-cell-val">{esc(h10_cusp.get("sub_sub_lord","") or em)}</div></div>
      </div></div>"""

    # ── KN Rao Insights (Mahadasha lord + H10 relation) ───────────────
    # BUGFIX (2026-07-19, user-reported audit): "md_lord_houses_ruled" is
    # never set on career_timeline blocks anywhere in timeline.py -- this
    # key was always absent, so "Houses Ruled by MD Lord" was blank on
    # every single report regardless of birth-time precision. Derive it
    # directly from `house_lords` (already passed into this function,
    # and — since the house_lords fix above — always the payload's
    # lagna-derived whole-sign table rather than the KP-cuspal-only one),
    # the same inversion pattern _build_year_context_payload() already
    # uses for the roadmap section.
    md_houses_ruled = sorted(
        (h for h, lord in (house_lords or {}).items() if lord == md_lord),
        key=lambda x: int(x) if str(x).isdigit() else 0,
    )
    md_placement = ", ".join(str(h) for h in md_houses_ruled) if md_houses_ruled else em
    md_house = (g("planet_house", {}) or {}).get(md_lord, None)
    md_house_str = f"House {md_house}" if md_house else em
    knrao_panel_html = f"""<div class="insight-panel"><div class="insight-panel-title">KN Rao Insights &mdash; Mahadasha</div>
      <div class="insight-cells">
        <div class="insight-cell"><div class="insight-cell-label">Mahadasha Lord</div><div class="insight-cell-val">{esc(md_lord)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">MD Lord Placed In</div><div class="insight-cell-val">{esc(md_house_str)}</div></div>
        <div class="insight-cell insight-cell-wide"><div class="insight-cell-label">Houses Ruled by MD Lord</div><div class="insight-cell-val">{esc(md_placement)}</div></div>
      </div></div>"""

    # ── Parashara Insights (lagna lord dignity + active yogas) ───────
    lagna_lord = g("lagna_lord", "") or em
    lagna_lord_dignity = true_dignities.get(g("lagna_lord", ""), "") or em
    yogas = g("yogas_present", []) or g("detected_yogas", []) or []
    yogas_str = ", ".join(yogas[:4]) if yogas else em
    parashara_panel_html = f"""<div class="insight-panel"><div class="insight-panel-title">Parashara Insights</div>
      <div class="insight-cells">
        <div class="insight-cell"><div class="insight-cell-label">Lagna Lord</div><div class="insight-cell-val">{esc(lagna_lord)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Lagna Lord Dignity</div><div class="insight-cell-val">{esc(lagna_lord_dignity)}</div></div>
        <div class="insight-cell insight-cell-wide"><div class="insight-cell-label">Active Yogas</div><div class="insight-cell-val">{esc(yogas_str)}</div></div>
      </div></div>"""

    # ── Jaimini Insights (AK/AmK, Arudha Lagna, Karma Pada, Karakamsha, Darakaraka) ──
    arudha_lagna = g("arudha_lagna", "") or em
    karma_pada = g("a10_sign", "") or em
    karakamsha = g("karakamsha_sign", "") or g("karakamsha", "") or em
    darakaraka = g("darakaraka", "") or (fixed_karakas or {}).get("DK", "") or em
    jaimini_panel_html = f"""<div class="insight-panel"><div class="insight-panel-title">Jaimini Insights</div>
      <div class="insight-cells">
        <div class="insight-cell"><div class="insight-cell-label">Atmakaraka (AK)</div><div class="insight-cell-val">{esc(fixed_karakas.get("AK","") or em)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Amatyakaraka (AmK)</div><div class="insight-cell-val">{esc(fixed_karakas.get("AmK","") or em)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Arudha Lagna</div><div class="insight-cell-val">{esc(arudha_lagna)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Karma Pada (A10)</div><div class="insight-cell-val">{esc(karma_pada)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Karakamsha</div><div class="insight-cell-val">{esc(karakamsha)}</div></div>
        <div class="insight-cell"><div class="insight-cell-label">Darakaraka (DK)</div><div class="insight-cell-val">{esc(darakaraka)}</div></div>
      </div></div>"""

    return f"""<div class="tl-sidebar-label">Snapshot</div>
{snapshot_html}
<div class="tl-sidebar-label">Planetary Strength</div>
{planet_panel_html}
<div class="tl-sidebar-label">D10 Insights</div>
{d10_panel_html}
<div class="tl-sidebar-label">KP Insights</div>
{kp_panel_html}
<div class="tl-sidebar-label">KN Rao Insights</div>
{knrao_panel_html}
<div class="tl-sidebar-label">Parashara Insights</div>
{parashara_panel_html}
<div class="tl-sidebar-label">Jaimini Insights</div>
{jaimini_panel_html}"""


# ═════════════════════════════════════════════════════════════════════════════
# TOP-LEVEL ENTRY POINT — generate_career_timeline_report
# ═════════════════════════════════════════════════════════════════════════════
#
# RECONSTRUCTION NOTE (2026-07-07): this function and the tail of
# _build_career_roadmap_html() above were found MISSING/truncated at the end
# of this file — the exact same "corruption pattern" already documented
# earlier in this module (see the _CSS reconstruction note near the top of
# the file, and jyotish/timeline_inputs.py's compute_confidence_tier, which
# was found compiled-but-returning-None in a stale .pyc, meaning the true
# source had already been lost/truncated at least once before this session).
# No prior complete copy of this function exists anywhere in the repo or in
# any readable bytecode cache (the newer .pyc for this exact module also
# lacks the symbol; the only cache that might have had it is a cpython-3.14
# marshal stream this environment's Python 3.10 cannot parse). This is
# therefore a clean-room reconstruction: it calls the SAME already-existing,
# unmodified helpers this module already defines/imports (build_career_timeline,
# _build_career_roadmap_html, _build_foreign_module_condensed_html, _tl_reading_guide,
# _tl_professional_nav, _kp_house_chain_summary) rather than inventing new
# scoring/astrology logic, so it does not introduce any new astrological
# doctrine — only the HTML assembly/orchestration layer that wires already-
# computed data into a page.
def generate_career_timeline_report(payload: NatalPayloadV2, output_dir: str = ".") -> str:
    """Generate the standalone Career Timeline HTML report for `payload`.

    Reads the already-computed `payload.career_timeline` (list of blocks),
    `payload.annual_transit_outlook`, and `payload.career_context` — all
    populated upstream by engine_io.parse_json_payload()'s call into
    jyotish.timeline.build_career_timeline() / build_annual_transit_outlook().
    This function does not recompute the timeline itself (that would risk
    silently diverging from the exact same values engine.py / micro_timing.py
    / the LLM narrative context already use for this same payload).

    Returns the path to the written HTML file.
    """
    name = getattr(payload, "name", "") or "Unknown"
    safe_name = "".join(c if (c.isalnum() or c in "_- ") else "_" for c in name).strip().replace(" ", "_").lower() or "chart"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(output_dir) / f"career_timeline_{safe_name}_{ts}.html"

    blocks = getattr(payload, "career_timeline", None) or []
    outlook_rows = getattr(payload, "annual_transit_outlook", None) or []
    career_ctx = getattr(payload, "career_context", None) or {}
    kp_cusps = getattr(payload, "kp_cusp_data", None) or {}
    # BUGFIX (2026-07-19, user-reported audit): this was rebuilt from
    # kp_cusps sign_lord ALONE, which is empty whenever birth time is
    # unknown -- even though whole-sign house lordship (which planet rules
    # which house, counted from Lagna) needs no birth time at all and is
    # already computed once, correctly, with a lagna-derived fallback baked
    # in, as `payload.house_lords` (see engine_io.py's
    # _derive_house_lordships_from_lagna()). That left "Houses Ruled by MD/AD
    # Lord" blank on every period for any birth-time-unknown chart. Prefer
    # the payload's own (already-patched) table; fall back to the KP-cuspal
    # rebuild only if the payload attribute is somehow absent.
    house_lords = (
        getattr(payload, "house_lords", None)
        or ({str(i): kp_cusps.get(f"H{i}", {}).get("sign_lord", "") for i in range(1, 13)} if kp_cusps else {})
    )
    d10_strength = getattr(payload, "d10_strength", 0.0)
    # BUGFIX (2026-07-19, user-reported audit): natal_facts previously only
    # ever set 2 of the ~10 keys _build_year_context_payload()/the roadmap
    # LLM prompt actually read from it (d10_lagna, d10_tenth_lord,
    # h10_occupants, ketu_house, the 4 sav_* bindu counts, and the 3
    # saturn_natal_* fields were all silently absent every single year,
    # despite code comments elsewhere claiming this was already wired).
    # All of these are genuinely available on `payload` already -- this
    # was a pure wiring gap, not missing chart data. Saturn's natal
    # house/dignity/ruled-houses mirror the exact same computation
    # Job_Career/timeline.py::_annual_transit_snapshot() already does per
    # transit row, just promoted to chart-level (natal Saturn doesn't
    # change year to year) so the roadmap LLM context gets it too.
    _planet_house_natal = getattr(payload, "planet_house", {}) or {}
    _sav_points = getattr(payload, "sav_points_houses", {}) or {}
    _d10_house_lords = getattr(payload, "d10_house_lords", {}) or {}
    _natal_saturn_dignity = str((getattr(payload, "planet_dignities", {}) or {}).get("Saturn", "")).upper()
    natal_facts = {
        "lagna_sign": getattr(payload, "lagna_sign", "") or getattr(payload, "d1_lagna", ""),
        "d10_house_occupancy": getattr(payload, "d10_house_occupancy", {}) or {},
        "d10_lagna":         getattr(payload, "d10_lagna_sign", ""),
        "d10_tenth_lord":    _d10_house_lords.get("10", ""),
        "d10_strength":      d10_strength,
        "h10_occupants":     sorted(p for p, h in _planet_house_natal.items() if h == 10),
        "ketu_house":        getattr(payload, "ketu_house", 0) or _planet_house_natal.get("Ketu", 0),
        "sav_h10":           _sav_points.get("10"),
        "sav_h6":            _sav_points.get("6"),
        "sav_h11":           _sav_points.get("11"),
        "sav_h12":           _sav_points.get("12"),
        "sav_all_houses":    _sav_points,
        "saturn_natal_house":   _planet_house_natal.get("Saturn", 0),
        "saturn_natal_dignity": _natal_saturn_dignity or "NEUTRAL",
        "saturn_rules_houses":  sorted(
            int(h) for h, lord in house_lords.items()
            if lord == "Saturn" and str(h).isdigit()
        ),
    }
    fixed_karakas = {
        "AK": getattr(payload, "atmakaraka", ""), "AmK": getattr(payload, "amatyakaraka", ""),
    }

    retro_matches = 0
    if blocks:
        retro_matches = blocks[0].get("retro_matches", 0) or 0
    confidence = (blocks[0].get("confidence") if blocks else None) or {}

    roadmap_html = _build_career_roadmap_html(
        blocks, outlook_rows, career_ctx=career_ctx, kp_cusps=kp_cusps,
        house_lords=house_lords, d10_strength=d10_strength,
        fixed_karakas=fixed_karakas, natal_facts=natal_facts, payload=payload,
    )

    try:
        foreign_html = _build_foreign_module_condensed_html(getattr(payload, "foreign_opportunities", None) or [])
    except Exception as _fe:
        logger.warning("Foreign module render skipped: %s", _fe)
        foreign_html = ""

    try:
        nav_html = _tl_professional_nav(blocks, outlook_rows)
    except Exception:
        nav_html = ""
    try:
        reading_guide_html = _tl_reading_guide()
    except Exception:
        reading_guide_html = ""

    # ── GAP 5 fix (2026-07-07, user-reported): "Title vs. influence"
    # outcome-strength table. Generic, reusable section (not one-off HTML
    # hardcoded for a single chart) — see OUTCOME_STRENGTH_TABLE in
    # gap_corrections_career_timeline_2026_07.py for the exact row data.
    try:
        from Job_Career.gap_corrections_career_timeline_2026_07 import outcome_strength_table_html
        outcome_table_html = outcome_strength_table_html()
    except Exception as _ot_err:
        logger.warning("Outcome-strength table (Gap 5) skipped: %s", _ot_err)
        outcome_table_html = ""

    # ── GAP 6 (2026-07-07): overall confidence label shown at report head ──
    # See jyotish/gap_corrections_career_timeline_2026_07.py::retro_confidence_label
    # for the full WHY. In short: showing bare "High" confidence off a single
    # retroactive validation match overstates certainty; this renders a
    # calibrated "Medium-High" label plus an explicit validation-coverage note.
    from Job_Career.gap_corrections_career_timeline_2026_07 import retro_confidence_label
    _conf_label, _conf_note = retro_confidence_label(confidence, retro_matches)

    # GAP 4 fix (2026-07-07 follow-up audit): structured retro_validation
    # summary sourced from the SAME `confidence` dict computed upstream in
    # timeline_inputs.py::compute_confidence_tier (no new scoring here).
    # Fixes the reported inconsistency where retro_matches could be 1 while
    # the caveat text said "No past career events provided" — the counting
    # bug (events_provided undercounting legacy join_date/last_promotion_date
    # fields) is fixed at the source; this only renders the corrected,
    # now-consistent numbers.
    # ── Left-hand dashboard sidebar (Snapshot / Planetary Strength / D10 /
    # KP / KN Rao / Parashara / Jaimini insights). Previously the CSS for
    # `.content-grid` / `.tl-sidebar` / `.outcome-bar` / `.planet-panel` /
    # `.d10-panel` / `.insight-panel` existed but was never emitted into
    # html_out — see _tl_sidebar_html() docstring above for data sourcing.
    try:
        sidebar_html = _tl_sidebar_html(
            payload, blocks, kp_cusps, natal_facts, fixed_karakas,
            house_lords, d10_strength, confidence,
            display_confidence_label=_conf_label,
        )
    except Exception as _sb_err:
        logger.warning("Timeline sidebar render skipped: %s", _sb_err)
        sidebar_html = ""

    _retro_validation = (confidence or {}).get("retro_validation") or {}
    retro_validation_html = ""
    if _retro_validation:
        retro_validation_html = (
            '<div class="rmap-retro-validation">'
            f'<strong>Retro-validation:</strong> {_retro_validation.get("events_matched", 0)} of '
            f'{_retro_validation.get("events_provided", 0)} provided past event(s) matched '
            f'&middot; confidence cap: {esc(str(_retro_validation.get("confidence_cap", "")))} '
            f'&middot; {esc(str(_retro_validation.get("reason", "")))}'
            '</div>'
        )

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Career Timeline — {esc(name)}</title>
{_TL_ELEVATED_HEAD_LINKS}
<style>{_TL_CSS}</style>
<style>{_TL_PRO_CSS}</style>
<style>
.career-roadmap-section {{ max-width: 1040px; margin: 0 auto; padding: 20px; }}
.roadmap-year-card {{ background:var(--surface,#fff); border:1px solid var(--border,#e7dcc8); border-radius:var(--radius-lg,18px); padding:20px 22px; margin-bottom:22px; }}
.roadmap-year-header {{ display:flex; align-items:center; gap:12px; margin-bottom:8px; }}
.roadmap-year-badge {{ font-size:10px; text-transform:uppercase; letter-spacing:.08em; padding:2px 8px; border-radius:10px; background:var(--gold-light,rgba(201,168,76,0.10)); color:var(--gold,#C9A84C); }}
.roadmap-year-label {{ font-family:'Cormorant Garamond',Georgia,serif; font-size:20px; font-weight:700; color:var(--deep,#1A1A2E); }}
.roadmap-weather {{ margin-left:auto; font-size:13px; color:var(--muted,#5F5F7A); }}
.roadmap-md-ad {{ font-size:13px; color:var(--muted,#5F5F7A); margin-bottom:10px; }}
.rmap-audience-label {{ font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--purple,#6B5B8E); margin:10px 0 4px; }}
.roadmap-narrative {{ font-size:14px; line-height:1.6; color:var(--deep,#1A1A2E); margin-bottom:8px; }}
.rmap-event-caveat {{ background:var(--amber-light,rgba(184,114,10,0.09)); border:1px solid var(--amber,#B8720A); border-radius:8px; padding:8px 12px; font-size:12.5px; color:var(--amber,#B8720A); margin-bottom:10px; }}
.rmap-outcome-table {{ width:100%; border-collapse:collapse; margin:14px 0; font-size:13px; }}
.rmap-outcome-table th, .rmap-outcome-table td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--border-soft,#F0ECE2); }}
.rmap-outcome-table th {{ background:var(--surface-warm,#FAF8F3); font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted,#5F5F7A); }}
.rmap-conf-banner {{ background:var(--gold-light,rgba(201,168,76,0.10)); border:1px solid var(--gold-mid,rgba(201,168,76,0.22)); border-radius:var(--radius-md,12px); padding:12px 16px; margin:16px auto; max-width:1040px; font-size:13px; color:var(--deep,#1A1A2E); }}
.rmap-retro-validation {{ background:var(--surface-warm,#FAF8F3); border:1px solid var(--border-soft,#F0ECE2); border-radius:var(--radius-md,12px); padding:10px 16px; margin:0 auto 16px; max-width:1040px; font-size:12.5px; color:var(--muted,#5F5F7A); }}
.rmap-kp-override-reason {{ font-size:11px; color:#64748b; margin-top:4px; }}
.rmap-matrix-caption {{ font-size:11px; color:#64748b; margin-top:6px; font-style:italic; }}
.rmap-d10-subscores {{ margin-top:8px; font-size:12.5px; }}
.rmap-d10-subscores-row {{ display:flex; justify-content:space-between; padding:2px 0; }}
.rmap-subphase-panel {{ margin-top:10px; }}
.rmap-subphase-row {{ display:flex; justify-content:space-between; font-size:12.5px; padding:4px 0; border-bottom:1px dashed var(--border-soft,#F0ECE2); }}
.rmap-d10-manifestation-detail {{ margin-top:10px; font-size:13px; }}
.rmap-outcome-strength-section {{ max-width:1040px; margin:20px auto; padding:0 20px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="brand">JyotishAI Career Timeline</div>
    <div class="title">{esc(name)}</div>
    <div class="meta"><span>Confidence: {esc(_conf_label)}</span></div>
  </div>
  <div class="content-grid">
    <aside class="tl-sidebar">
      {sidebar_html}
    </aside>
    <main class="tl-main">
      <div class="rmap-conf-banner"><strong>Confidence note:</strong> {esc(_conf_note)}</div>
      {retro_validation_html}
      {outcome_table_html}
      {nav_html}
      {roadmap_html}
      {foreign_html}
      {reading_guide_html}
    </main>
  </div>
</div>
<script>
function togglePD(id) {{
  var el = document.getElementById(id);
  var btn = document.getElementById('btn-' + id);
  var hidden = el.hasAttribute('hidden');
  if (hidden) {{
    el.removeAttribute('hidden');
    btn.setAttribute('aria-expanded','true');
    btn.querySelector('.pd-toggle-icon').textContent = '▾';
  }} else {{
    el.setAttribute('hidden','');
    btn.setAttribute('aria-expanded','false');
    btn.querySelector('.pd-toggle-icon').textContent = '▸';
  }}
}}
function toggleWI(btn, panelId) {{
  document.querySelectorAll('.wi-panel').forEach(function(p){{p.classList.remove('shown');}});
  document.querySelectorAll('.wi-btn').forEach(function(b){{b.classList.remove('active');}});
  var panel = document.getElementById(panelId);
  if (panel) {{ panel.classList.add('shown'); btn.classList.add('active'); }}
}}
</script>
</body>
</html>"""

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    logger.info("Career timeline report written -> %s", out_path)
    return str(out_path)
