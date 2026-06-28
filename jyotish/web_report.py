"""JyotishAI web report v4 — dual-audience LLM support, global toggle, DOB."""
import html as _html
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from .payload import NatalPayloadV2, logger
from .foreign_opportunities import generate_foreign_report_beside

esc = _html.escape

# ─── Domain icons & badge colours (small pill only) ───────────────
_DI = {
    "engineering":"⚙️","technology":"💻","science":"🔬","medicine":"🩺",
    "arts":"🎨","law":"⚖️","interdisciplinary":"🌐","humanities":"📚",
    "commerce":"💼","public":"🏛️","education":"🎓"
}
_DA = {
    "engineering":"#1565c0","technology":"#0277bd","science":"#2e7d32",
    "medicine":"#b71c1c","arts":"#6a1b9a","law":"#e65100",
    "interdisciplinary":"#37474f","humanities":"#4a148c","commerce":"#1b5e20",
    "public":"#37474f","education":"#4e342e"
}

_CSS = """
:root {
    --bg: #f8fafc; --text: #1e293b; --card-bg: #ffffff;
    --border: #e2e8f0; --primary: #0f172a; --secondary: #64748b;
    --astro-bg: #f1f5f9; --astro-border: #94a3b8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 20px; }
.container { max-width: 1280px; margin: 0 auto; }

/* Header */
.header { text-align: center; margin-bottom: 40px; padding-bottom: 20px; border-bottom: 2px solid var(--border); }
.brand { font-size: 0.9rem; font-weight: 700; letter-spacing: 2px; color: var(--secondary); text-transform: uppercase; margin-bottom: 10px; }
.title { font-size: 2.5rem; font-weight: 800; color: var(--primary); margin-bottom: 15px; }
.meta { display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; font-size: 0.95rem; color: var(--secondary); }
.meta span { background: #e2e8f0; padding: 4px 12px; border-radius: 20px; font-weight: 500; }

/* Section label */
.section-label { text-align: center; font-size: 0.85rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: var(--secondary); margin-bottom: 24px; }

/* Cards */
.card-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; align-items: start; }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
.card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
.card-title { display: flex; align-items: center; gap: 10px; font-size: 1.15rem; font-weight: 700; color: var(--primary); }
.rank { background: var(--primary); color: white; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 1rem; }
.badges { display: flex; gap: 8px; }
.badge { padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: 600; color: white; }
.badge-score { background: var(--secondary); }

/* Content Areas */
.explanation { margin-top: 15px; }
.explanation-title { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; margin-bottom: 5px; }
.parent-text { font-size: 1.05rem; color: #334155; }
.astro-box { margin-top: 15px; padding: 15px; background: var(--astro-bg); border-left: 4px solid var(--astro-border); border-radius: 0 8px 8px 0; }
.astro-text { font-size: 0.95rem; font-family: Consolas, Monaco, "Courier New", monospace; color: #475569; }

/* Parent-friendly explanation section */
.pfe-section { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 14px 16px; margin: 12px 0; }
.pfe-label { font-size: 11px; font-weight: 700; color: #166534; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 8px; }
.pfe-body { font-size: 1.02rem; color: #1e293b; line-height: 1.65; }

/* ── GAP 1–4: Academic path, Institutional tier, Micro-niches, Confidence ── */
/* Micro-niches */
.niche-row{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 4px;}
.niche-pill{font-size:10.5px;font-weight:600;padding:2px 9px;border-radius:12px;
  background:rgba(201,168,76,0.12);color:#7A5E00;border:1px solid rgba(201,168,76,0.3);}
.niche-driver{font-size:10px;color:#94a3b8;margin-top:3px;}

/* Confidence matrix */
.conf-matrix{background:#f8fafc;border-radius:8px;padding:10px 12px;margin-top:10px;
  border:1px solid rgba(0,0,0,0.06);}
.conf-overall{font-size:12px;font-weight:700;color:#475569;margin-bottom:6px;}
.conf-overall span{color:#1e40af;font-size:14px;}
.conf-bars{display:flex;flex-direction:column;gap:5px;}
.conf-bar-row{display:flex;align-items:center;gap:8px;}
.conf-bar-label{font-size:10.5px;font-weight:600;color:#64748b;width:110px;flex-shrink:0;}
.conf-bar-track{flex:1;height:7px;background:#e2e8f0;border-radius:99px;overflow:hidden;}
.conf-bar-fill{height:100%;border-radius:99px;background:linear-gradient(90deg,#3b82f6,#6366f1);}
.conf-bar-pct{font-size:10.5px;font-weight:700;color:#475569;width:32px;text-align:right;flex-shrink:0;}

/* Academic path */
.acad-path{margin-top:12px;padding-top:10px;border-top:1px solid rgba(0,0,0,0.06);}
.acad-path-label{font-size:10.5px;font-weight:700;color:#7A5E00;text-transform:uppercase;
  letter-spacing:.06em;margin-bottom:8px;}
.acad-stages{display:flex;align-items:center;gap:0;flex-wrap:wrap;}
.acad-stage{display:flex;align-items:center;}
.acad-stage-box{padding:5px 11px;border-radius:8px;font-size:11px;font-weight:700;
  border:1px solid transparent;text-align:center;}
.acad-stage-box small{display:block;font-size:9px;font-weight:400;opacity:0.75;}
.acad-req {background:#ecfdf5;color:#065f46;border-color:#6ee7b7;}
.acad-rec {background:#eff6ff;color:#1e40af;border-color:#93c5fd;}
.acad-opt {background:#f8fafc;color:#64748b;border-color:#cbd5e1;}
.acad-off {background:#fafafa;color:#9ca3af;border-color:#e5e7eb;opacity:0.55;}
.acad-arrow{color:#94a3b8;font-size:14px;padding:0 5px;}

/* Institutional tier */
.inst-tier{display:flex;align-items:flex-start;gap:8px;margin-top:10px;
  padding:9px 12px;background:#fff7ed;border-radius:8px;border:1px solid #fdba74;}
.inst-tier-badge{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;
  color:#9a3412;background:#fed7aa;border-radius:6px;padding:2px 8px;flex-shrink:0;white-space:nowrap;}
.inst-tier-detail{font-size:11px;color:#334155;line-height:1.5;}
.inst-tier-detail strong{color:#1A1A2E;}

@media (max-width: 768px) {
    .card-list { grid-template-columns: 1fr; }
    .card-header { flex-direction: column; }
}

/* ── 360° Insight badges ─────────────────────────────────────── */
.insight-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;padding-top:10px;border-top:1px solid rgba(0,0,0,0.06);}
.ins-badge{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:700;
  letter-spacing:0.3px;padding:3px 9px;border-radius:20px;border:1px solid transparent;}
.ins-wealth-High   {background:#ecfdf5;color:#065f46;border-color:#6ee7b7;}
.ins-wealth-Medium {background:#fffbeb;color:#92400e;border-color:#fcd34d;}
.ins-wealth-Low    {background:#fef2f2;color:#991b1b;border-color:#fca5a5;}
.ins-geo-int  {background:#eff6ff;color:#1e40af;border-color:#93c5fd;}
.ins-geo-hyb  {background:#f5f3ff;color:#4c1d95;border-color:#c4b5fd;}
.ins-geo-dom  {background:#f0fdf4;color:#14532d;border-color:#86efac;}
.ins-burn-Low  {background:#ecfdf5;color:#065f46;border-color:#6ee7b7;}
.ins-burn-Med  {background:#fffbeb;color:#92400e;border-color:#fcd34d;}
.ins-burn-High {background:#fef2f2;color:#991b1b;border-color:#fca5a5;}

/* ── Corporate / Entrepreneur gauge ─────────────────────────── */
.corp-gauge-wrap{margin:18px 0 6px;padding:14px 18px;
  background:rgba(255,255,255,0.55);border:1px solid rgba(201,168,76,0.25);
  border-radius:12px;backdrop-filter:blur(4px);}
.corp-gauge-label{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:#7A5E00;margin-bottom:8px;}
.corp-gauge-bar-wrap{display:flex;align-items:center;gap:10px;}
.corp-gauge-bar{flex:1;height:10px;border-radius:99px;
  background:linear-gradient(90deg,#3b82f6 0%,var(--gold) 100%);
  position:relative;overflow:hidden;}
.corp-gauge-bar-inner{height:100%;background:rgba(255,255,255,0.35);position:absolute;right:0;top:0;}
.corp-gauge-ends{display:flex;justify-content:space-between;font-size:10px;color:#64748b;margin-top:4px;}
.corp-gauge-pct{font-size:12px;font-weight:700;white-space:nowrap;color:#1A1A2E;min-width:80px;text-align:right;}
.corp-style-note{font-size:12px;color:#475569;margin-top:6px;line-height:1.5;}

/* Academic stage: registry program name + niche sub-line */
.acad-stage-name{font-weight:700;font-size:11px;line-height:1.3;}
.acad-stage-niche{font-size:9.5px;color:#6b7280;margin-top:2px;font-style:italic;line-height:1.3;}

/* ── New elements from scoring Gap fixes ───────────────────────────────── */
/* Top karakas pill row (Gap-6: top_karakas now forwarded from engine) */
.karaka-row{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 4px;}
.karaka-pill{font-size:10.5px;font-weight:700;padding:2px 10px;border-radius:12px;
  background:rgba(30,64,175,0.08);color:#1e40af;border:1px solid rgba(30,64,175,0.18);}

/* Structural friction warning (Gap-3) */
.friction-alert{display:flex;align-items:flex-start;gap:7px;margin:8px 0;padding:8px 12px;
  background:#fff7ed;border-left:3px solid #f97316;border-radius:0 8px 8px 0;
  font-size:11px;color:#9a3412;}
.friction-icon{font-size:13px;flex-shrink:0;margin-top:1px;}
.friction-text{line-height:1.5;}

/* Score meta row: boost_pct / timing_band / sbc_event_score / pre_norm_score */
.score-meta-row{display:flex;flex-wrap:wrap;gap:5px;margin:6px 0;}
.meta-pill{font-size:10px;font-weight:600;padding:2px 9px;border-radius:10px;}
.meta-boost{background:#dcfce7;color:#166534;border:1px solid #86efac;}
.meta-timing{background:#eff6ff;color:#1e40af;border:1px solid #93c5fd;}
.meta-sbc{background:#f5f3ff;color:#5b21b6;border:1px solid #c4b5fd;}
.meta-norm{background:#f8fafc;color:#475569;border:1px solid #cbd5e1;cursor:help;}
.cluster-banner{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;
  background:linear-gradient(135deg,#f0f9ff 0%,#e0f2fe 100%);
  border:1.5px solid #38bdf8;border-radius:14px;padding:18px 20px;margin-bottom:18px;}
.cluster-banner-left{display:flex;gap:12px;align-items:flex-start;flex:1;min-width:260px;}
.cluster-banner-icon{font-size:26px;line-height:1;flex-shrink:0;}
.cluster-banner-title{font-weight:700;font-size:15px;color:#0369a1;margin-bottom:4px;}
.cluster-banner-sub{font-size:11.5px;color:#0c4a6e;line-height:1.55;max-width:420px;}
.cluster-domain-grid{display:flex;flex-wrap:wrap;gap:8px;align-items:center;}
.cluster-domain-pill{display:flex;flex-direction:column;align-items:center;
  background:#fff;border:1px solid #7dd3fc;border-radius:10px;
  padding:6px 12px;min-width:90px;}
.cluster-domain-name{font-size:10.5px;font-weight:700;color:#0369a1;}
.cluster-domain-count{font-size:9.5px;color:#64748b;margin-top:2px;}

/* ── 360° expanded insight detail blocks ───────────────────────────── */
.ins-detail-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;padding-top:8px;border-top:1px solid rgba(0,0,0,0.05);}
.ins-detail-block{flex:1;min-width:150px;background:#f8fafc;border-radius:7px;padding:7px 10px;border:1px solid #e2e8f0;}
.ins-detail-label{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.07em;color:#94a3b8;margin-bottom:4px;}
.ins-detail-value{font-size:10.5px;color:#334155;line-height:1.5;}
.ins-detail-note{font-size:10px;color:#64748b;line-height:1.4;margin-top:3px;font-style:italic;}
.ins-geo-bar{height:5px;border-radius:99px;background:#e2e8f0;margin:5px 0 2px;overflow:hidden;}
.ins-geo-bar-fill{height:100%;border-radius:99px;}
.ins-stress-flag{font-size:10px;color:#92400e;line-height:1.4;margin-top:2px;}
.ins-stress-flag::before{content:"⚡ ";}

/* ── SBC timing detail collapsible ─────────────────────────────────── */
.sbc-detail-box{margin-top:8px;border-radius:8px;background:#faf5ff;border:1px solid #e9d5ff;padding:8px 11px;font-size:10.5px;}
.sbc-detail-box summary{font-weight:700;color:#6d28d9;cursor:pointer;user-select:none;list-style:none;display:flex;align-items:center;gap:5px;}
.sbc-detail-box summary::before{content:"▶";font-size:8px;transition:transform .2s;}
.sbc-detail-box[open] summary::before{transform:rotate(90deg);}
.sbc-naks{color:#4c1d95;font-weight:600;margin:5px 0 4px;}
.sbc-prot{color:#065f46;margin-bottom:2px;padding-left:4px;}
.sbc-obs{color:#991b1b;margin-bottom:2px;padding-left:4px;}
.sbc-prot::before{content:"✓ ";}
.sbc-obs::before{content:"✗ ";}

/* ── Verified factors pill row ─────────────────────────────────────── */
.vfact-row{display:flex;flex-wrap:wrap;gap:4px;margin:5px 0 2px;}
.vfact-label{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.07em;color:#94a3b8;align-self:center;margin-right:3px;}
.vfact-pill{font-size:9.5px;padding:2px 8px;border-radius:8px;background:#f0fdf4;color:#14532d;border:1px solid #86efac;font-weight:600;}
.vfact-pill.neg{background:#fef2f2;color:#991b1b;border-color:#fca5a5;}
"""



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

    # ── Score meta row: boost_pct, pre_norm, timing ──────────────────────────
    _boost_pct  = field.get("boost_pct", 0)
    _pre_norm   = field.get("pre_norm_score")
    _norm_note  = field.get("norm_note", "")
    _timing     = field.get("timing_band", "")
    _sbc        = field.get("sbc_event_score") or field.get("smi")
    score_meta_parts = []
    if _boost_pct:
        score_meta_parts.append(f'<span class="meta-pill meta-boost">+{_boost_pct:.0f}% gap boost</span>')
    if _timing:
        score_meta_parts.append(f'<span class="meta-pill meta-timing">⏱ {esc(_timing)}</span>')
    if _sbc is not None:
        score_meta_parts.append(f'<span class="meta-pill meta-sbc">SBC {_sbc:.0f}</span>')
    if _pre_norm is not None:
        _norm_short = _norm_note.split("→")[0].strip() if _norm_note else ""
        score_meta_parts.append(
            f'<span class="meta-pill meta-norm" title="{esc(_norm_note)}">'
            f'pre-norm {_pre_norm:.1f}</span>'
        )
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

    conf_html = (
        f'<div class="conf-matrix">'
        f'<div class="conf-overall">{_conf_label}: <span>{_ov_p}%</span></div>'
        f'<div class="conf-bars">'
        + _conf_bar("KN Rao (Classical)",    _kn_p,  "#4f46e5")
        + _conf_bar("KP (Micro-Timing)",     _kp_p,  "#7c3aed")
        + _conf_bar("Jaimini (Aptitude)",    _ji_p,  "#0891b2")
        + _conf_bar("Parashara (Strength)",  _pa_p,  "#059669")
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
            {inst_html}
        </div>
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

def _pd_narrative(pd_lord: str, md_lord: str = "") -> str:
    return _PD_THEMES.get(pd_lord, "A focused sub-period that colours the Antardasha energy.")

def _tl_conf_badge(conf: str) -> str:
    css = "conf-strong" if conf == "STRONG" else ("conf-moderate" if conf == "MODERATE" else "conf-mismatch")
    label = conf.replace("_", " ").replace("CALIBRATION MISMATCH", "Calibrating")
    return f'<span class="tl-conf-badge {css}">{esc(label)}</span>'

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

def _tl_ad_card(period: dict, idx: int) -> str:
    md_lord    = period.get("md_lord", "")
    ad         = esc(period.get("ad_lord", ""))
    et         = period.get("event_type", "DEFAULT")
    score      = period.get("career_score", 0.0)
    start      = esc(_fmt_date(period.get("start_date", "")))
    end        = esc(_fmt_date(period.get("end_date", "")))
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

            pd_plain = esc(_pd_narrative(pdl, md_lord))
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
            chips += (
                f'<div class="pd-item">'
                f'<div class="pd-header">'
                f'<span class="pd-chip">{esc(pdl)}</span>'
                f'<span class="pd-dates">{esc(pd_date_str)}</span>'
                f'</div><div class="pd-content">{pd_body}</div></div>'
            )
        pd_id  = f"pd-{idx}"
        pd_html = (
            f'<button class="pd-toggle" onclick="togglePD(\'{pd_id}\')" aria-expanded="false" id="btn-{pd_id}">'
            f'<span class="pd-toggle-icon">&#9656;</span> Sub-periods ({len(pds)})</button>'
            f'<div class="pd-list" id="{pd_id}" hidden>{chips}</div>'
        )

    narrative_section = (
        f'<div class="llm-narrative">{llm_html}</div>'
        if llm_html else
        (f'<div class="ad-insight">{plain_hint}</div>' if plain_hint else "")
    )

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
        _yoga_badge = (
            f'<span class="pill" style="background:rgba(201,168,76,0.12);color:#7A5E00;'
            f'border-color:rgba(201,168,76,0.35)" title="Active natal yogas">'
            f'✦ {", ".join(_yogas[:2])}</span>'
        )

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
  --muted:       #8A8AA8;
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
  max-width:960px;margin:0 auto;position:relative;z-index:1;gap:24px;
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

/* ── Content ─────────────────────────────────────────────────── */
.content{max-width:960px;margin:0 auto;padding:36px 24px 72px}

/* ── Outcome bar ─────────────────────────────────────────────── */
.outcome-bar{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius-lg);padding:20px 28px;
  display:flex;align-items:stretch;margin-bottom:32px;
  box-shadow:var(--shadow-sm);overflow:hidden;
}
.outcome-bar>div{
  flex:1;padding:4px 24px;
  border-right:1px solid var(--border-soft);
}
.outcome-bar>div:first-child{padding-left:0}
.outcome-bar>div:last-child{padding-right:0;border-right:none}
.outcome-label{
  font-size:10px;font-weight:600;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--muted);margin-bottom:4px;
}
.outcome-val{font-size:15px;font-weight:600;color:var(--deep);text-transform:capitalize}

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
.cal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;}
.cal-year-card{background:#fff;border:1px solid var(--border);border-radius:10px;
  padding:12px 14px;transition:box-shadow 0.2s;}
.cal-year-card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.08);}
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
  .ad-card,.md-group,.cal-year-card,.md-arc-card{break-inside:avoid;page-break-inside:avoid}
  .fop-section,.traj-section{break-before:auto}
  .ad-card{box-shadow:none;border:1px solid #e2e8f0}
  .content{max-width:100%;padding:0 8px}
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

.traj-section{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md);padding:16px 20px;margin-bottom:20px;}
.traj-heading{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:12px;}
.traj-wrap{position:relative;height:100px;}

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
.fop-geo{font-size:10.5px;color:#7dd3fc;margin-bottom:7px;line-height:1.4;}
.fop-indicators{display:flex;flex-wrap:wrap;gap:5px;}
.fop-indicator{font-size:9.5px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);color:#bae6fd;border-radius:6px;padding:2px 8px;line-height:1.5;}
.fop-trigger{margin-top:8px;font-size:10px;color:#fde68a;border-top:1px solid rgba(255,255,255,0.08);padding-top:7px;}
.fop-trigger-label{font-weight:700;text-transform:uppercase;font-size:8.5px;letter-spacing:.06em;margin-right:4px;}
.fop-empty{font-size:12px;color:#94d2e8;text-align:center;padding:16px 0;}
"""


def _build_micro_timing_panels(mt: dict, timeline: list = None) -> str:
    """Render the 4 micro-timing panels as an HTML string."""
    if not mt:
        return ""
    html_parts = []
    _tl = timeline or []  # timeline blocks for scenario-specific enrichment

    # 1. Negotiation Heatmap
    hm = mt.get("negotiation_heatmap", {})
    if hm:
        month_label = hm.get("current_month_label", "")
        wins = hm.get("windows", [])
        best = hm.get("best_window")
        win_html = ""
        for w in wins:
            colour = w["colour"]
            label_txt  = w.get("label", "Neutral")
            advice_txt = w.get("advice", "")
            # Correct "avoid" + positive advice contradiction
            if colour == "avoid" and (
                "trine" in advice_txt.lower()
                or "excellent" in advice_txt.lower()
                or "favourable" in advice_txt.lower()
            ):
                colour = "neutral"
                label_txt = "Neutral"
            cls   = "hm-" + colour
            ds    = w["date_start"][5:]
            de    = w["date_end"][5:]
            tip   = esc(advice_txt)
            mh    = w["moon_house"]
            win_html += (
                f'<div class="hm-win {cls}">{ds}\u2013{de}<br>H{mh}'
                f'<div class="hm-tooltip">{esc(label_txt)}: {tip}</div></div>'
            )
        best_html = ""
        if best:
            best_html = (
                f'<div class="hm-best-label">&#9733; Best window: '
                f'{best["date_start"]} — {esc(best["advice"])}</div>'
            )
        html_parts.append(
            f'<div class="mt-section">'
            f'<div class="mt-section-title"><span>&#128197;</span> Interview &amp; Negotiation Heatmap — {month_label}</div>'
            f'<div class="hm-grid">{win_html}</div>{best_html}'
            f'</div>'
        )

    # 2. Stakeholder Radar
    sr = mt.get("stakeholder_radar", {})
    if sr:
        climate  = sr.get("climate_label", "Clear")
        colour   = sr.get("climate_colour", "clear")
        advice   = esc(sr.get("advice", ""))
        quarter  = sr.get("quarter_label", "")
        aff      = sr.get("afflictors", {})
        h6_warn  = len(aff.get("h6",  [])) > 0
        h10_warn = len(aff.get("h10", [])) > 0
        h7_warn  = len(aff.get("h7",  [])) > 0
        h6_cls   = "radar-house-warn" if h6_warn  else "radar-house-ok"
        h10_cls  = "radar-house-warn" if h10_warn else "radar-house-ok"
        h7_cls   = "radar-house-warn" if h7_warn  else "radar-house-ok"
        h6_txt   = ("&#9888; H6 Colleagues"  if h6_warn  else "&#10003; H6 Clear")
        h10_txt  = ("&#9888; H10 Management" if h10_warn else "&#10003; H10 Clear")
        h7_txt   = ("&#9888; H7 Partners"    if h7_warn  else "&#10003; H7 Clear")
        html_parts.append(
            f'<div class="mt-section">'
            f'<div class="mt-section-title"><span>&#128737;</span> Workplace Climate Radar — {quarter}</div>'
            f'<div class="radar-card">'
            f'<span class="radar-climate radar-{colour}">{climate}</span>'
            f'<div><div class="radar-advice">{advice}</div>'
            f'<div class="radar-houses">'
            f'<span class="radar-house-pill {h6_cls}">{h6_txt}</span>'
            f'<span class="radar-house-pill {h10_cls}">{h10_txt}</span>'
            f'<span class="radar-house-pill {h7_cls}">{h7_txt}</span>'
            f'</div></div></div></div>'
        )

    # 3. What-If Simulator — scenario-specific content derived from timeline
    wi_all = mt.get("whatif_scenarios", {})
    if wi_all:
        # ── Build per-scenario best-block enrichment from timeline ────────────
        # Match using the same per-scenario event types as micro_timing.py
        _et_map = {
            "negotiate": ("SALARY_HIKE", "INCOME_INFLECTION", "BREAKTHROUGH", "PROMOTION"),
            "quit":      ("JOB_CHANGE", "LATERAL_MOVE", "BREAKTHROUGH", "ENTREPRENEURSHIP_WINDOW"),
            "promotion": ("PROMOTION", "LEADERSHIP_EXPANSION", "BREAKTHROUGH", "INCOME_INFLECTION"),
            "freelance": ("ENTREPRENEURSHIP_WINDOW", "INCOME_INFLECTION", "JOB_CHANGE", "LATERAL_MOVE", "BREAKTHROUGH"),
            "join":      ("JOB_CHANGE", "BREAKTHROUGH", "FOREIGN_POSTING"),
            "relocate":  ("FOREIGN_POSTING", "JOB_CHANGE", "BREAKTHROUGH"),
            "invest":    ("INCOME_INFLECTION", "BREAKTHROUGH", "SALARY_HIKE"),
        }
        _wi_override: dict = {}
        if _tl:
            _upcoming = [b for b in _tl if not b.get("is_past", False)]
            for _sc_key, _et_types in _et_map.items():
                _matching = [b for b in _upcoming if b.get("event_type","") in _et_types]
                _best_sc  = max(_matching, key=lambda b: b.get("career_score", 0), default=None)
                if _best_sc:
                    _md = _best_sc.get("md_lord","?")
                    _ad = _best_sc.get("ad_lord","?")
                    _sd = (_best_sc.get("start_date","") or "")[:7]
                    _sc = int(_best_sc.get("career_score",0)*100)
                    _et = (_best_sc.get("event_type","") or "").replace("_"," ").title()
                    _wi_override[_sc_key] = {
                        "best_block": f"{_md}–{_ad} ({_sd[:4]}-{_sd[5:7] if len(_sd)>=7 else '?'})",
                        "event_type": _et,
                        "score":      _sc,
                    }
                # No override if no matching block — fall through to micro_timing advisability

        # ── Scenario-specific text templates ──────────────────────────────────
        _scenario_meta: dict = {
            "negotiate": {
                "label":    "Salary Negotiation",
                "houses":   "H2/H11 (wealth & gains)",
                "tip_good": "Time your negotiation to the heatmap Favourable windows above. Lead with impact metrics, not tenure.",
                "tip_med":  "Mixed signals. Prepare a strong case now — initiate only after a clear win or performance milestone.",
                "tip_bad":  "No strong salary-hike period upcoming. Build leverage through visibility projects before asking.",
                "risk":     "Initiating salary talks during H8 or H12 Moon (Avoid windows above) risks a stalled or rejected appraisal.",
            },
            "quit": {
                "label":    "Quitting / Resigning",
                "houses":   "H6/H8/H12 (transition, ending, change)",
                "tip_good": "Line up the next role before formally resigning. Have a signed offer letter before giving notice.",
                "tip_med":  "Proceed carefully — secure an alternative first. Do not resign into a gap.",
                "tip_bad":  "No strong job-change period visible. Stay put and upskill until the dasha shifts.",
                "risk":     "Resigning impulsively during a Saturn or Rahu adverse period may create a gap without a landing pad.",
            },
            "promotion": {
                "label":    "Applying for Promotion",
                "houses":   "H10/H1 (career & identity)",
                "tip_good": "Submit your promotion case at least 4 weeks before the peak period. Document all impact.",
                "tip_med":  "Build your case now for a window opening soon. Focus on H10 visibility projects.",
                "tip_bad":  "Dasha energy does not strongly support designation change now. Focus on visibility first.",
                "risk":     "Applying when H10 is afflicted (see Workplace Radar above) may meet structural resistance.",
            },
            "freelance": {
                "label":    "Going Freelance",
                "houses":   "H3/H5/H7 (clients, creativity, partnerships)",
                "tip_good": "Start the transition gradually — take projects alongside employment to build pipeline first.",
                "tip_med":  "Test the market with freelance work before exiting employment. Validate revenue before committing.",
                "tip_bad":  "Planetary support for independent income is limited now. Wait for a stronger Jupiter or Venus AD.",
                "risk":     "Full-time freelancing before a financial cushion (H2/H11 activated) carries income instability risk.",
            },
            "join": {
                "label":    "Joining a New Company",
                "houses":   "H1/H10 (identity & career)",
                "tip_good": "Strong dasha for onboarding. Negotiate well before joining — initial terms are hard to change.",
                "tip_med":  "Evaluate offers carefully. Ensure role alignment with your medium-term trajectory.",
                "tip_bad":  "No strong joining period upcoming. Explore internal growth first.",
                "risk":     "Joining during a Saturn H10 transit may start the new role under pressure.",
            },
            "relocate": {
                "label":    "Geographic Relocation",
                "houses":   "H9/H12 (foreign, travel)",
                "tip_good": "Excellent window for relocation. Align your move with the H12/H9 transit peaks in your Foreign module.",
                "tip_med":  "Relocation is feasible but ensure legal/logistics groundwork is complete before committing.",
                "tip_bad":  "Foreign/travel houses are not strongly activated. Delaying relocation may yield better opportunities.",
                "risk":     "Relocating without a confirmed role or visa in hand during a Rahu period can create instability.",
            },
            "invest": {
                "label":    "Making a Major Investment",
                "houses":   "H2/H5/H11 (wealth, speculation, gains)",
                "tip_good": "H2/H11 well-activated — favourable for committing capital to long-term assets.",
                "tip_med":  "Proceed with measured amounts. Avoid illiquid or speculative instruments this window.",
                "tip_bad":  "H8 or adverse Saturn transit — preserve capital; avoid new illiquid commitments.",
                "risk":     "Committing large capital during an H8-activated period risks unexpected write-offs or delays.",
            },
        }

        btn_html   = ""
        panel_html = ""
        _first_key = next(iter(wi_all), None)  # auto-open first panel
        colour_map = {"Favourable": "wi-fav", "Caution": "wi-caut", "Unadvisable": "wi-unad"}
        adv_cls_map = {"Favourable": "wi-adv-fav", "Caution": "wi-adv-caut", "Unadvisable": "wi-adv-unad"}

        for key, wi in wi_all.items():
            meta   = _scenario_meta.get(key, {})
            label  = meta.get("label") or wi.get("action_label", key.title())
            ovr    = _wi_override.get(key, {})

            # Advisability: trust micro_timing's full 6-month net score (don't override)
            adv = wi.get("advisability", "Caution")

            _bblk  = ovr.get("best_block")
            _et    = ovr.get("event_type","")
            _sc    = ovr.get("score", 0)
            houses = meta.get("houses","")

            # ── Timing line (never contradicts advisability) ───────────────────
            if adv == "Favourable":
                if _bblk:
                    timing = (
                        f"Next matched window: <strong>{esc(_bblk)}</strong> — "
                        f"{esc(_et)} ({_sc}%). Active houses: {esc(houses)}."
                    )
                else:
                    timing = esc(wi.get("timing_note",""))
                reco = meta.get("tip_good","") + (f" Best window: {_bblk}." if _bblk else "")
            elif adv == "Caution":
                if _bblk and _sc >= 50:
                    timing = (
                        f"Nearest aligned window: <strong>{esc(_bblk)}</strong> — "
                        f"{esc(_et)} ({_sc}%). Proceed with care."
                    )
                else:
                    timing = esc(wi.get("timing_note","Mixed signals — proceed only after securing next step."))
                reco = meta.get("tip_med", meta.get("tip_bad",""))
            else:  # Unadvisable
                _earliest = wi.get("earliest_opportunity_date","")
                if _earliest:
                    timing = (
                        f"Unadvisable in the current window. "
                        f"Next meaningful opportunity opens around <strong>{esc(_earliest)}</strong>."
                    )
                else:
                    timing = esc(wi.get("timing_note",
                        f"Significant risk overlay — no strong {label.lower()} window visible in the near term."))
                reco = meta.get("tip_bad","Wait for a more supportive planetary window.")

            # ── Risks & Opportunities (up to 3 each) ─────────────────────────
            risks         = wi.get("risk_factors", [])
            opps          = wi.get("opportunity_factors", [])
            risk_specific = meta.get("risk","")
            panel_cls     = colour_map.get(adv, "wi-caut")
            adv_cls       = adv_cls_map.get(adv, "wi-adv-caut")

            risk_li  = f"<li>{esc(risk_specific)}</li>" if risk_specific else ""
            risk_li += "".join(f"<li>{esc(r)}</li>" for r in risks[:2])
            opp_li   = "".join(f"<li>{esc(o)}</li>" for o in opps[:3])
            factors  = ""
            if risk_li:
                factors += f'<div class="wi-factors"><strong>Risks to watch:</strong><ul>{risk_li}</ul></div>'
            if opp_li:
                factors += f'<div class="wi-factors"><strong>Opportunities:</strong><ul>{opp_li}</ul></div>'

            _auto_shown = " shown" if key == _first_key else ""
            _active_cls = " active" if key == _first_key else ""
            btn_html   += (
                f'<button class="wi-btn{_active_cls}" '
                f'onclick="toggleWI(this,\'wi-{key}\')">{esc(label)}</button>'
            )
            panel_html += (
                f'<div class="wi-panel {panel_cls}{_auto_shown}" id="wi-{key}">'
                f'<span class="wi-advisability {adv_cls}">{esc(adv)}</span>'
                f'<div class="wi-timing">{timing}</div>'
                f'<div class="wi-reco">{esc(reco)}</div>'
                f'{factors}'
                f'</div>'
            )
        html_parts.append(
            f'<div class="mt-section">'
            f'<div class="mt-section-title"><span>&#128260;</span> What-If Scenario Simulator</div>'
            f'<div class="wi-grid">{btn_html}</div>'
            f'{panel_html}'
            f'</div>'
        )

    # 4. Hora Timing (if present)
    ht = mt.get("hora_timing") or {}
    if ht:
        weeks_html = ""
        for w in ht.get("weeks", []):
            is_cur    = w.get("is_current", False)
            cur_cls   = " current" if is_cur else ""
            freq_html    = (f'<span class="ht-freq">{esc(w.get("frequency",""))}</span>'
                            if w.get("frequency") else "")
            pd_note_html = (f'<div class="ht-pd-note">{esc(w.get("pd_note",""))}</div>'
                            if w.get("pd_note") else "")
            weeks_html += (
                f'<div class="ht-week{cur_cls}">'
                f'<div class="ht-week-label">{esc(w.get("week_label",""))}</div>'
                f'<div class="ht-title">{esc(w.get("title",""))}{freq_html}</div>'
                f'<div class="ht-detail">{esc(w.get("detail",""))}</div>'
                f'{pd_note_html}'
                f'</div>'
            )
        html_parts.append(
            f'<div class="mt-section">'
            f'<div class="mt-section-title"><span>&#9200;</span> Hora &amp; Weekly Timing</div>'
            f'<div class="ht-weeks">{weeks_html}</div>'
            f'</div>'
        )

    return "\n".join(html_parts)



def _build_foreign_module_html(foreign_opps: list) -> str:
    """Render the Foreign Opportunities module section (past 1yr + next 5yr)."""
    if not foreign_opps:
        return ""

    strong   = sum(1 for o in foreign_opps if o["foreign_score"] >= 0.65)
    moderate = sum(1 for o in foreign_opps if 0.45 <= o["foreign_score"] < 0.65)
    mild     = sum(1 for o in foreign_opps if o["foreign_score"] < 0.45)
    best     = max(foreign_opps, key=lambda o: o["foreign_score"])
    best_lbl = f"{best['md_lord']}–{best['ad_lord']} ({_fmt_date(best['start_date'][:7])})"

    parts = []
    if strong:   parts.append(f"{strong} strong")
    if moderate: parts.append(f"{moderate} moderate")
    if mild:     parts.append(f"{mild} mild")
    summary = (
        f"{len(foreign_opps)} foreign window{'s' if len(foreign_opps)>1 else ''} detected"
        + (f" ({', '.join(parts)})" if parts else "")
        + f" · Peak: {esc(best_lbl)}"
    )

    _dur_cls = {
        "SHORT_TRIP":       "fop-badge-blue",
        "ASSIGNMENT":       "fop-badge-amber",
        "RELOCATION":       "fop-badge-red",
        "LONG_TERM_ABROAD": "fop-badge-red",
    }

    cards_html = ""
    for opp in foreign_opps:
        sc      = opp["foreign_score"]
        bar_w   = int(sc * 100)
        bar_col = ("#22c55e" if sc >= 0.65 else ("#f59e0b" if sc >= 0.45 else "#818cf8"))
        dur_cls = _dur_cls.get(opp.get("duration_type", ""), "fop-badge-blue")

        tag = ("\U0001f550 Past" if opp.get("is_past")
               else ("\U0001f534 Active" if opp.get("is_current") else "\U0001f535 Upcoming"))

        indicators_html = "".join(
            f'<span class="fop-indicator">{esc(ind)}</span>'
            for ind in (opp.get("indicators") or [])
        )

        tw = opp.get("trigger_window") or {}
        trigger_html = ""
        if tw.get("trigger_planet") and tw.get("trigger_start"):
            t_start = esc(_fmt_date(tw.get("trigger_start", "")))
            t_end   = esc(_fmt_date(tw.get("trigger_end",   "")))
            t_note  = esc(tw.get("trigger_note", ""))
            trigger_html = (
                f'<div class="fop-trigger">'
                f'<span class="fop-trigger-label">Best action window:</span>'
                f'{tw["trigger_planet"]} enters trigger zone {t_start}–{t_end}'
                + (f' — {t_note}' if t_note else "")
                + f'</div>'
            )

        card_extra = " fop-card-upcoming"
        if opp.get("is_current"):
            card_extra = " fop-card-active"
        elif opp.get("is_past"):
            card_extra = " fop-card-past"

        cards_html += (
            f'\n<div class="fop-card{card_extra}">'
            f'<div class="fop-card-header">'
            f'<div class="fop-lords">'
            f'<span class="fop-md">{esc(opp.get("md_lord",""))}</span>'
            f'<span class="fop-dash">–</span>'
            f'<span class="fop-ad">{esc(opp.get("ad_lord",""))}</span>'
            f'</div>'
            f'<span class="fop-dates">{esc(_fmt_date(opp.get("start_date","")))} → {esc(_fmt_date(opp.get("end_date","")))}</span>'
            f'<span class="fop-tag">{tag}</span>'
            f'</div>'
            f'<div class="fop-score-row">'
            f'<div class="fop-score-bar">'
            f'<div class="fop-score-fill" style="width:{bar_w}%;background:{bar_col}"></div>'
            f'</div>'
            f'<span class="fop-score-num">{bar_w}%</span>'
            f'<span class="fop-badge {dur_cls}">{esc(opp.get("duration_label",""))}</span>'
            f'</div>'
            f'<div class="fop-geo">\U0001f30d {esc(opp.get("geo_affinity",""))}</div>'
            f'<div class="fop-indicators">{indicators_html}</div>'
            f'{trigger_html}'
            f'</div>'
        )

    return (
        f'\n<div class="fop-section">'
        f'<div class="fop-section-header">'
        f'<div class="fop-section-title">\U0001f310 Foreign Opportunity Windows</div>'
        f'<div class="fop-section-sub">{summary}</div>'
        f'</div>'
        f'<div class="fop-cards">{cards_html}</div>'
        f'</div>'
    )


def _build_annual_calendar_html(timeline: list) -> str:
    """Render a compact year-by-year card grid showing dominant event per year."""
    if not timeline:
        return ""

    _YEAR_EVENT_COLORS = {
        "BREAKTHROUGH":         ("#C9A84C", "#7A5E00"),
        "PROMOTION":            ("#1E7B50", "#fff"),
        "LEADERSHIP_EXPANSION": ("#1E7B50", "#fff"),
        "INCOME_INFLECTION":    ("#2563EB", "#fff"),
        "SALARY_HIKE":          ("#2563EB", "#fff"),
        "JOB_CHANGE":           ("#7C3AED", "#fff"),
        "FOREIGN_POSTING":      ("#0891B2", "#fff"),
        "RISK_PERIOD":          ("#DC2626", "#fff"),
        "SKILL_UPGRADE_PHASE":  ("#0891B2", "#fff"),
        "STABILITY":            ("#94A3B8", "#fff"),
        "GROWTH":               ("#059669", "#fff"),
        "TRANSITION":           ("#6B7280", "#fff"),
        "CAREER_PLATEAU":       ("#B45309", "#fff"),
        "STAGNATION":           ("#6B7280", "#fff"),
        "CAREER_THROUGH_PARTNERSHIP": ("#0369A1", "#fff"),
    }

    year_map: dict = {}
    for block in timeline:
        sd = block.get("start_date", "")
        if not sd:
            continue
        try:
            y = int(sd[:4])
        except ValueError:
            continue
        cs = block.get("career_score", 0.0)
        et = (block.get("event_type") or "STABILITY").replace("FORECAST_", "")
        if y not in year_map or cs > year_map[y]["score"]:
            year_map[y] = {"event": et, "score": cs, "ad_lord": block.get("ad_lord", "")}

    if not year_map:
        return ""

    cards = []
    for yr in sorted(year_map):
        info  = year_map[yr]
        et    = info["event"]
        score = info["score"]
        ad    = info["ad_lord"]
        bar_c, _ = _YEAR_EVENT_COLORS.get(et, ("#94A3B8", "#fff"))
        label = et.replace("_", " ").title()
        pct   = int(score * 100)
        cards.append(
            f'<div class="cal-year-card">'
            f'<div class="cal-year-label">{yr}</div>'
            f'<div class="cal-year-event" style="color:{bar_c}">{label}</div>'
            f'<div class="cal-year-score">{ad} AD &middot; {pct}% score</div>'
            f'<div class="cal-year-bar" style="background:{bar_c};width:{pct}%;max-width:100%"></div>'
            f'</div>'
        )

    return (
        '<div class="cal-section">'
        '<div class="cal-heading">Annual Career Calendar</div>'
        f'<div class="cal-grid">{"".join(cards)}</div>'
        '</div>'
    )


def _build_md_arc_section_html(timeline: list) -> str:
    """Render the LLM-generated MD-level narrative arcs (if present)."""
    seen: set = set()
    cards = []
    for block in timeline:
        ml = block.get("md_lord", "")
        arc = block.get("md_arc_html", "")
        if ml and arc and ml not in seen:
            seen.add(ml)
            cards.append(f'<div class="md-arc-card">{arc}</div>')
    if not cards:
        return ""
    return (
        '<div class="md-arc-section">'
        '<div class="cal-heading" style="margin-bottom:14px">Mahadasha Narrative Arcs</div>'
        + "".join(cards) +
        '</div>'
    )


def generate_career_timeline_report(payload: "NatalPayloadV2", output_dir: str = ".") -> str:
    """Generate career timeline HTML report. Returns absolute path."""
    name     = esc(getattr(payload, "name", "Native"))
    dob      = esc(getattr(payload, "dob", ""))
    lagna    = esc(getattr(payload, "lagna_sign", "Unknown"))
    gen_date = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _cc  = getattr(payload, "career_context", {}) or {}
    ak   = esc(_cc.get("atmakaraka",  "") or getattr(payload, "atmakaraka",  "") or "—")
    amk  = esc(_cc.get("amatyakaraka","") or getattr(payload, "amatyakaraka","") or "—")
    _kar = getattr(payload, "jaimini_karakas", {}) or {}
    if ak  == "—": ak  = esc(_kar.get("AK",  "") or "—")
    if amk == "—": amk = esc(_kar.get("AmK", "") or "—")

    timeline = getattr(payload, "career_timeline", []) or []
    conf     = (getattr(payload, "overall_confidence", "")
                or _cc.get("overall_confidence", "Moderate")).title()
    conf_cls = ("conf-strong"    if conf.lower() == "strong" else
                ("conf-mismatch" if conf.lower() in ("mismatch","weak") else "conf-moderate"))

    _retro_n = 0
    for _b in timeline:
        _retro_n = _b.get("retro_matches", 0) or 0
        if _retro_n:
            break
    if _retro_n:
        _retro_cls = "retro-badge" if _retro_n >= 2 else "retro-badge retro-badge-warn"
        _retro_icon = "✓" if _retro_n >= 2 else "~"
        _retro_badge = (
            f'<span class="{_retro_cls}" title="Engine correctly predicted {_retro_n} past events">'
            f'{_retro_icon} Validated against {_retro_n} past event{"s" if _retro_n != 1 else ""}'
            f'</span>'
        )
    else:
        _retro_badge = ""

    def _compute_outcome_bar(cc: dict, tl: list) -> tuple:
        primary_opp = cc.get("primary_opportunity", "") or ""
        peak_md     = cc.get("peak_md_lord", "")        or ""
        peak_years  = str(cc.get("peak_years", ""))     or ""
        growth_arc  = cc.get("growth_arc", "")          or ""
        if tl:
            _best = max(tl, key=lambda b: b.get("career_score", 0))
            _best_et = (_best.get("event_type") or "Growth").replace("_", " ").title()
            if not primary_opp:
                primary_opp = _best_et
            if not peak_md:
                peak_md = _best.get("md_lord", "—")
            if not peak_years:
                _ys = _best.get("start_date", "")[:4]
                _ye = _best.get("end_date", "")[:4]
                peak_years = f"{_ys}–{_ye}" if _ys and _ye and _ys != _ye else _ys
            if not growth_arc:
                _scores = [b.get("career_score", 0) for b in tl]
                _avg    = sum(_scores) / len(_scores) if _scores else 0
                _max    = max(_scores) if _scores else 0
                growth_arc = (
                    "Strong Upward" if _max >= 0.75 else
                    "Moderate Growth" if _avg >= 0.55 else
                    "Steady" if _avg >= 0.45 else "Developing"
                )
        return (
            primary_opp or "—",
            peak_md     or "—",
            peak_years  or "—",
            growth_arc  or "—",
        )

    _out_opp, _out_md, _out_years, _out_arc = _compute_outcome_bar(_cc, timeline)
    outcome_html = (
        f'<div class="outcome-bar">'
        f'<div><div class="outcome-label">Primary Opportunity</div>'
        f'<div class="outcome-val">{esc(_out_opp)}</div></div>'
        f'<div><div class="outcome-label">Peak MD Lord</div>'
        f'<div class="outcome-val">{esc(_out_md)}</div></div>'
        f'<div><div class="outcome-label">Peak Years</div>'
        f'<div class="outcome-val">{esc(_out_years)}</div></div>'
        f'<div><div class="outcome-label">Growth Arc</div>'
        f'<div class="outcome-val">{esc(_out_arc)}</div></div>'
        f'</div>'
    )

    _chart_labels = []
    _chart_scores = []
    _chart_colors = []
    _event_color_map = {
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
        "CAREER_THROUGH_PARTNERSHIP":"#0369A1",
    }
    for _p in timeline:
        _et  = (_p.get("event_type") or "STABILITY").replace("FORECAST_", "")
        _lbl = f"{_p.get('ad_lord','?')} ({_p.get('start_date','')[:7]})"
        _score = _p.get("career_score", 0.5)
        _chart_labels.append(_lbl)
        _chart_scores.append(round(_score * 100, 1))
        _chart_colors.append(_event_color_map.get(_et, "#94A3B8"))

    import json as _json
    _chart_data_json    = _json.dumps(_chart_scores)
    _chart_labels_json  = _json.dumps(_chart_labels)
    _chart_colors_json  = _json.dumps(_chart_colors)
    _chart_section = "" if not _chart_scores else (
        '<div class="traj-section">'
        '<div class="traj-heading">Career Score Trajectory</div>'
        '<div class="traj-wrap"><canvas id="trajChart" height="90"></canvas></div>'
        '</div>'
    )

    if not timeline:
        _cards_html = (
            '<div class="tl-empty">'
            '<div class="tl-empty-icon">\U0001f52d</div>'
            '<div class="tl-empty-title">No Timeline Periods Generated</div>'
            '<p style="font-size:13px;color:#64748b;max-width:420px;margin:0 auto">'
            'The career timeline could not be built. This usually means the birth date '
            'and Dasha balance are missing or the career context was not provided. '
            'Please ensure <code>dasha_periods</code> and <code>career_context</code> '
            'are present in the input payload.'
            '</p></div>'
        )
    else:
        _non_past = [b for b in timeline if not b.get("is_past", False)]
        _pool = _non_past if _non_past else timeline
        _best_idx = max(range(len(_pool)), key=lambda i: _pool[i].get("career_score", 0))
        _best_block_id = id(_pool[_best_idx])
        for _b in timeline:
            _b["is_primary_opportunity"] = (id(_b) == _best_block_id)

        from itertools import groupby as _groupby
        _md_groups = []
        for _md, _group in _groupby(timeline, key=lambda b: b.get("md_lord", "?")):
            _md_groups.append((_md, list(_group)))

        _cards_parts = []
        _global_idx = 0
        for _md_lord, _blocks in _md_groups:
            _md_start = _fmt_date((_blocks[0].get("start_date") or "")[:7])
            _md_end   = _fmt_date((_blocks[-1].get("end_date") or "")[:7])
            _md_score = max(b.get("career_score", 0) for b in _blocks)
            _md_icon  = {
                "Sun": "☀", "Moon": "☽", "Mars": "♂", "Mercury": "☿",
                "Jupiter": "♃", "Venus": "♀", "Saturn": "♄",
                "Rahu": "☊", "Ketu": "☋",
            }.get(_md_lord, "✶")
            _md_head_html = (
                f'<div class="md-group">'
                f'<div class="md-head">'
                f'<div class="md-planet-badge">{_md_icon}</div>'
                f'<div><div class="md-title">{esc(_md_lord)} Mahadasha</div>'
                f'<div class="md-dates">{_md_start} → {_md_end}</div></div>'
                f'<div class="md-score-pill">Peak {int(_md_score * 100)}%</div>'
                f'</div>'
                f'<div class="ad-list">'
            )
            _cards_parts.append(_md_head_html)
            for _b in _blocks:
                _cards_parts.append(_tl_ad_card(_b, _global_idx))
                _global_idx += 1
            _cards_parts.append('</div></div>')

        _cards_html = "\n".join(_cards_parts)

    _annual_cal_html = _build_annual_calendar_html(timeline)
    _md_arc_html     = _build_md_arc_section_html(timeline)

    _fop_list = []
    for _b in timeline:
        _fo = _b.get("foreign_opportunity")
        if _fo:
            _fop_list.append(_fo)
    _seen_fop = set()
    _uniq_fop = []
    for _fo in _fop_list:
        _key = (_fo.get("start_date", ""), _fo.get("ad_lord", ""))
        if _key not in _seen_fop:
            _seen_fop.add(_key)
            _uniq_fop.append(_fo)
    _fop_html = _build_foreign_module_html(_uniq_fop)

    mt_data   = _cc.get("micro_timing") or getattr(payload, "micro_timing", None) or {}
    mt_html   = _build_micro_timing_panels(mt_data, timeline=timeline)
    mt_section = (
        f'<div class="mt-block"><h2 class="section-heading">Micro-Timing Intelligence</h2>'
        f'{mt_html}</div>'
    ) if mt_html else ""

    html = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        f"<title>Career Timeline — {name}</title>\n"
        f"<style>{_TL_CSS}</style>\n"
        "</head>\n<body>\n"
        "<div class=\"tl-header\">\n"
        "  <div class=\"tl-header-inner\">\n"
        "    <div>\n"
        "      <div class=\"tl-brand\">JyotishAI · Career Timeline</div>\n"
        f"      <div class=\"tl-name\">{name}</div>\n"
        "      <div class=\"tl-meta\">\n"
        f"        DOB {dob} &nbsp;·&nbsp; Lagna {lagna}<br>\n"
        f"        AK {ak} &nbsp;·&nbsp; AmK {amk}\n"
        "      </div>\n"
        f"      <div style='margin-top:6px'>{_retro_badge}</div>\n"
        "    </div>\n"
        "    <div class=\"tl-conf\">\n"
        f"      <div class=\"tl-conf-badge {conf_cls}\">{conf}</div>\n"
        "      <div class=\"tl-conf-sub\">Chart Confidence</div>\n"
        "    </div>\n"
        "  </div>\n"
        "</div>\n"
        "<div class=\"content\">\n"
        f"  {outcome_html}\n"
        f"  {_chart_section}\n"
        f"  {_annual_cal_html}\n"
        f"  {_md_arc_html}\n"
        f"  {_fop_html}\n"
        "  <div class=\"timeline-list\">\n"
        f"    {_cards_html}\n"
        "  </div>\n"
        f"  {mt_section}\n"
        "  <div style=\"font-size:10.5px;color:#94a3b8;text-align:center;margin-top:32px;"
        "padding-top:16px;border-top:1px solid var(--border);\">\n"
        f"    Generated {gen_date} · JyotishAI Engine\n"
        "  </div>\n"
        "</div>\n"
        "<script src=\"https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js\"></script>\n"
        "<script>\n"
        f"var _TJ_LABELS={_chart_labels_json};\n"
        f"var _TJ_SCORES={_chart_data_json};\n"
        f"var _TJ_COLORS={_chart_colors_json};\n"
        "document.addEventListener('DOMContentLoaded',function(){\n"
        "  var ctx=document.getElementById('trajChart');\n"
        "  if(!ctx)return;\n"
        "  new Chart(ctx,{\n"
        "    type:'line',\n"
        "    data:{\n"
        "      labels:_TJ_LABELS,\n"
        "      datasets:[{\n"
        "        data:_TJ_SCORES,\n"
        "        borderColor:'#C9A84C',borderWidth:2,\n"
        "        pointBackgroundColor:_TJ_COLORS,pointRadius:6,pointHoverRadius:8,\n"
        "        fill:true,\n"
        "        backgroundColor:'rgba(201,168,76,0.07)',\n"
        "        tension:0.35\n"
        "      }]\n"
        "    },\n"
        "    options:{\n"
        "      responsive:true,maintainAspectRatio:false,\n"
        "      plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){return c.raw+'% career score';}}}},\n"
        "      scales:{\n"
        "        y:{min:0,max:100,ticks:{stepSize:25,callback:function(v){return v+'%';}},grid:{color:'rgba(0,0,0,0.05)'}},\n"
        "        x:{ticks:{maxRotation:35,font:{size:9}},grid:{display:false}}\n"
        "      }\n"
        "    }\n"
        "  });\n"
        "});\n"
        "function togglePD(id) {\n"
        "  var el = document.getElementById(id);\n"
        "  var btn = document.getElementById('btn-' + id);\n"
        "  var hidden = el.hasAttribute('hidden');\n"
        "  if (hidden) {\n"
        "    el.removeAttribute('hidden');\n"
        "    btn.setAttribute('aria-expanded','true');\n"
        "    btn.querySelector('.pd-toggle-icon').textContent = '▾';\n"
        "  } else {\n"
        "    el.setAttribute('hidden','');\n"
        "    btn.setAttribute('aria-expanded','false');\n"
        "    btn.querySelector('.pd-toggle-icon').textContent = '▸';\n"
        "  }\n"
        "}\n"
        "function toggleWI(btn, panelId) {\n"
        "  document.querySelectorAll('.wi-panel').forEach(function(p){p.classList.remove('shown');});\n"
        "  document.querySelectorAll('.wi-btn').forEach(function(b){b.classList.remove('active');});\n"
        "  var panel = document.getElementById(panelId);\n"
        "  if (panel) { panel.classList.add('shown'); btn.classList.add('active'); }\n"
        "}\n"
        "</script>\n"
        "</body>\n</html>"
    )

    os.makedirs(output_dir, exist_ok=True)
    fp = os.path.join(output_dir, f"career_timeline_{name.replace(' ', '_')}.html")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(html)

    _raw_name    = getattr(payload, "name", "Native") or "Native"
    _raw_dob     = getattr(payload, "dob", "") or ""
    _raw_lagna   = getattr(payload, "lagna_sign", "") or ""
    try:
        generate_foreign_report_beside(
            _uniq_fop,
            main_report_path=fp,
            name=_raw_name,
            dob=_raw_dob,
            lagna=_raw_lagna,
        )
    except Exception as _fe:
        logger.warning("Foreign opportunities report failed: %s", _fe)

    import os as _os_val
    if _os_val.environ.get("OPENAI_API_KEY"):
        try:
            from .career_validation_prompt import (
                extract_actual_history_from_payload,
                call_validation_llm,
                generate_validation_html,
            )
            _actual_history = extract_actual_history_from_payload(payload)
            if _actual_history:
                logger.info(
                    "[Validation] Running career validator for %s (%d actual events)...",
                    _raw_name, len(_actual_history),
                )
                _val_result = call_validation_llm(
                    payload=payload,
                    predicted_blocks=timeline,
                    actual_history=_actual_history,
                )
                _val_html_path = generate_validation_html(
                    _val_result, payload, output_dir=output_dir,
                )
                logger.info("[Validation] Report: %s", _val_html_path)
            else:
                logger.info(
                    "[Validation] Skipped — no career_events found in payload for %s",
                    _raw_name,
                )
        except Exception as _ve:
            logger.warning("Career validation report failed (non-fatal): %s", _ve)

    return fp
