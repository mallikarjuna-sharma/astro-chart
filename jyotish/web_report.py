"""JyotishAI web report v3 — unified cards, Strong+ filter, soul fallback, DOB."""
import html as _html, os
from datetime import datetime
from typing import Dict, List, Optional
from .payload import NatalPayloadV2, logger

esc = _html.escape

# ── Domain icons & badge colours (small pill only) ────────────────────────────
_DI = {"engineering":"⚙️","technology":"💻","science":"🔬","medicine":"🩺",
       "arts":"🎨","law":"⚖️","interdisciplinary":"🌐","humanities":"📚",
       "commerce":"💼","public":"🏛️","education":"🎓"}
_DA = {"engineering":"#1565c0","technology":"#0277bd","science":"#2e7d32",
       "medicine":"#b71c1c","arts":"#6a1b9a","law":"#e65100",
       "interdisciplinary":"#37474f","humanities":"#4a148c","commerce":"#1b5e20",
       "public":"#37474f","education":"#4e342e"}

def _i(d):   return _DI.get(d, "🌐")
def _da(d):  return _DA.get(d, "#546e7a")

# ── Score helpers ─────────────────────────────────────────────────────────────
def _pct(s): return max(5, min(100, int((s - 100) / 75 * 100)))

def _sl(s, top=175):
    """Labels are relative to this chart's top-scoring field."""
    if s >= top - 10: return "Excellent Match"
    if s >= top - 20: return "Strong Match"
    if s >= top - 35: return "Good Match"
    return "Moderate Match"

def _is_strong(s, top=175): return s >= top - 20   # Strong or Excellent

# ── Entrance exam label map ───────────────────────────────────────────────────
_EL = {"JEE_Advanced":"JEE Advanced","JEE_Main":"JEE Main","NEET_UG":"NEET UG",
       "CLAT":"CLAT","CUET":"CUET","BITSAT":"BITSAT","GATE":"GATE (PG)","CAT":"CAT",
       "AILET":"AILET","LSAT_India":"LSAT India","State_Art_Entrance":"State Art Entrance",
       "Audition_Based":"Audition / Portfolio","BHU_UET":"BHU UET",
       "State_Entrance":"State Entrance","NATA":"NATA","NID_DAT":"NID DAT",
       "UCEED":"UCEED","CEED":"CEED (PG)"}
def _fe(e): return _EL.get(e, e.replace("_"," "))

# ── AK → soul domains (for fallback soul-field picker) ───────────────────────
_AK_SOUL = {
    "Moon":    ["arts","medicine","humanities"],
    "Venus":   ["arts","humanities"],
    "Jupiter": ["humanities","law","medicine"],
    "Mercury": ["technology","science"],
    "Saturn":  ["engineering", "science", "interdisciplinary"],
    "Sun":     ["law","interdisciplinary"],
    "Mars":    ["engineering","science"],
    "Rahu":    ["technology","interdisciplinary"],
    "Ketu":    ["science","interdisciplinary"],
}

# ── AK descriptions for soul justification templates ─────────────────────────
_AK_DESC = {
    "Moon":    "an intuitive, emotionally intelligent soul who thrives in nurturing and expressive roles",
    "Venus":   "a soul drawn to beauty, harmony, and refined aesthetic experience",
    "Jupiter": "a wisdom-seeking soul with natural gifts for teaching, guiding, and expanding minds",
    "Mercury": "an intellectually agile soul who flourishes in analysis, communication, and precision",
    "Saturn":  "a disciplined soul built for structured, long-term, and socially impactful work",
    "Sun":     "a soul with natural authority, leadership, and a drive toward dharmic purpose",
    "Mars":    "an action-oriented soul with courage, drive, and technical mastery",
    "Rahu":    "an ambitious, unconventional soul drawn to future-facing and innovative paths",
    "Ketu":    "a spiritually inclined soul with past-life mastery in esoteric or investigative domains",
}
_DOMAIN_DESC = {
    "arts":           "creative expression, aesthetic beauty, and artistic mastery",
    "technology":     "innovation, computation, and intellectual problem-solving",
    "science":        "discovery and deep understanding of natural laws",
    "medicine":       "healing, compassionate service, and human wellbeing",
    "law":            "justice, governance, and social order",
    "humanities":     "language, culture, philosophy, and human understanding",
    "engineering":    "building, design, and systematic creation",
    "interdisciplinary": "integrative thinking that bridges multiple domains",
    "commerce":       "enterprise, economics, and organisational leadership",
    "public":         "public service, defence, and civic contribution",
    "education":      "teaching, mentorship, and the transmission of knowledge",
}

def _soul_reason_html(rec: Dict, ak: str) -> str:
    """Return 2-paragraph HTML for soul-aligned justification."""
    domain  = rec.get("domain", "interdisciplinary")
    label   = esc(rec.get("field_label", "this field"))
    raw     = rec.get("llm_parent_reason", "").strip()

    if raw:
        paras = [p.strip() for p in raw.replace("\r\n","\n").split("\n\n") if p.strip()]
        if len(paras) >= 2:
            return "".join(f"<p>{esc(p)}</p>" for p in paras[:2])
        if paras:
            soul_note = (
                f"This path carries a deeper soul resonance — it invites your child to "
                f"engage with work that feels purposeful and personally meaningful, honouring "
                f"the karmic direction indicated by their {esc(ak)} Atmakaraka."
            )
            return f"<p>{esc(paras[0])}</p><p>{soul_note}</p>"

    # Template fallback (LLM not available)
    ak_d   = _AK_DESC.get(ak, "a soul with unique karmic gifts")
    dom_d  = _DOMAIN_DESC.get(domain, "meaningful contribution")
    p1 = (
        f"Your child's Atmakaraka ({esc(ak)}) reveals {ak_d}. "
        f"{label} speaks directly to this soul signature — it is a field rooted in "
        f"{dom_d}, resonating with the deepest currents of who they are at a spiritual level."
    )
    p2 = (
        f"While the top recommendations above are determined by planetary strength and "
        f"practical aptitude, {label} is highlighted as the Soul-Aligned choice because it "
        f"aligns with the soul's evolutionary intent. Pursuing this field — even as a "
        f"complementary interest or long-term aspiration — can bring a sense of meaning and "
        f"fulfilment that purely score-driven choices may not always offer."
    )
    return f"<p>{p1}</p><p>{p2}</p>"


def _pick_soul_field(results: List[Dict], shown_ids: set, ak: str) -> Optional[Dict]:
    """Pick a soul-aligned fallback field not already in shown_ids."""
    preferred = _AK_SOUL.get(ak, ["interdisciplinary","arts"])
    for domain in preferred:
        for r in results:
            if r["field_id"] not in shown_ids and r.get("domain") == domain:
                return r
    for r in results:
        if r["field_id"] not in shown_ids:
            return r
    return None


# ── Chart header ──────────────────────────────────────────────────────────────
def _chart_header(payload: NatalPayloadV2) -> str:
    name   = esc(getattr(payload, "name", "Student"))
    dob    = esc(getattr(payload, "dob", "") or "")
    lagna  = esc(getattr(payload, "lagna_sign", ""))
    age    = getattr(payload, "current_age", None)
    ak     = getattr(payload, "atmakaraka", "")
    amk    = getattr(payload, "amatyakaraka", "")
    h10    = getattr(payload, "h10_lord", "")
    digs   = getattr(payload, "planet_dignities", {})
    yogas  = getattr(payload, "detected_yogas", [])[:6]

    def kp(planet, role):
        d = digs.get(planet, "")
        c = "#1565c0" if d in ("EXALTED","OWN") else ("#b71c1c" if d == "DEBILITATED" else "#546e7a")
        badge = f'<span class="dig-badge" style="background:{c}">{esc(d)}</span>' if d else ""
        return (f'<div class="kk-item"><span class="kk-role">{esc(role)}</span>'
                f'<span class="kk-planet">{esc(planet)}{badge}</span></div>')

    yp = "".join(f'<span class="yoga-pill">{esc(y)}</span>' for y in yogas)
    dob_html = f"DOB: <strong>{dob}</strong> &nbsp;·&nbsp; " if dob else ""
    age_html = f"Age: <strong>{int(age)}</strong> &nbsp;·&nbsp; " if age else ""
    return f"""
<div class="chart-header">
  <div class="ch-left">
    <div class="ch-name">{name}</div>
    <div class="ch-meta">{dob_html}{age_html}Lagna: <strong>{lagna}</strong></div>
  </div>
  <div class="ch-right">
    <div class="ch-karakas">{kp(ak,"AK · Soul")}{kp(amk,"AmK · Career")}{kp(h10,"H10 Lord")}</div>
    <div class="ch-yogas">{yp or '<em style="color:#999">No yogas detected</em>'}</div>
  </div>
</div>"""


# ── Registry info block ───────────────────────────────────────────────────────
def _reg_block(reg: Dict, view: str = "parent") -> str:
    ug   = esc(reg.get("ug_program",""));  pg  = esc(reg.get("pg_program",""))
    phd  = esc(reg.get("phd_program","")); ug_n= esc(reg.get("ug_niche",""))
    pg_n = esc(reg.get("pg_niche",""));    phd_n=esc(reg.get("phd_niche",""))
    exams = reg.get("admission_exams", []); career = reg.get("career_paths", [])
    niche = esc(reg.get("niche",""))
    ex_str = " &nbsp;·&nbsp; ".join(f"<span class='exam-pill'>{_fe(e)}</span>" for e in exams) or "<em>—</em>"
    car_str = ", ".join(esc(c) for c in career[:5]) or "—"
    rows = ""
    if view == "parent":
        if ug:  rows += f"<tr><td class='rl'>UG Programme</td><td>{ug}</td></tr>"
        if pg:  rows += f"<tr><td class='rl'>PG Programme</td><td>{pg}</td></tr>"
        if phd: rows += f"<tr><td class='rl'>PhD / Research</td><td>{phd}</td></tr>"
        rows += f"<tr><td class='rl'>Entrance Exams</td><td>{ex_str}</td></tr>"
        rows += f"<tr><td class='rl'>Career Paths</td><td>{car_str}</td></tr>"
    else:
        if ug:  rows += f"<tr><td class='rl'>UG</td><td>{ug} <span class='rn'>{ug_n}</span></td></tr>"
        if pg:  rows += f"<tr><td class='rl'>PG</td><td>{pg} <span class='rn'>{pg_n}</span></td></tr>"
        if phd: rows += f"<tr><td class='rl'>PhD</td><td>{phd} <span class='rn'>{phd_n}</span></td></tr>"
        rows += f"<tr><td class='rl'>Entrance</td><td>{ex_str}</td></tr>"
        rows += f"<tr><td class='rl'>Career</td><td>{car_str}</td></tr>"
        if niche: rows += f"<tr><td class='rl'>Specialisation</td><td>{niche}</td></tr>"
    return f'<table class="rt2">{rows}</table>' if rows else ""


# ── Parent-view card (unified neutral colours, soul keeps purple) ─────────────
def _parent_card(rank_lbl: str, rec: Dict, is_soul: bool = False, top: float = 175) -> str:
    label  = esc(rec["field_label"])
    domain = rec.get("domain", "interdisciplinary")
    score  = rec["final_score"]
    pct    = _pct(score)
    sl     = esc(_sl(score, top))
    badge_colour = _da(domain)
    icon   = _i(domain)
    reg    = rec.get("registry", {})
    rh     = _reg_block(reg, "parent")

    if is_soul:
        reason_html = _soul_reason_html(rec, "")   # ak injected from caller
        card_style  = "border-left:5px solid #7b1fa2;background:#fdf3ff"
        sr          = '<div class="soul-ribbon">✨ Soul-Aligned</div>'
        bar_colour  = "#7b1fa2"
    else:
        reason_raw  = rec.get("llm_parent_reason","").strip() or \
                      f"This field aligns well with your child's natural strengths in {domain}."
        reason_html = f"<p>{esc(reason_raw)}</p>"
        card_style  = "border-left:5px solid #5c6bc0;background:#f8f9fe"
        sr          = ""
        bar_colour  = "#5c6bc0"

    return f"""
<div class="fc" style="{card_style}">
  {sr}
  <div class="fch">
    <span class="fc-rank">{rank_lbl}</span><span class="fc-icon">{icon}</span>
    <div class="fctb">
      <span class="fc-title">{label}</span>
      <span class="fc-badge" style="background:{badge_colour}">{domain.upper()}</span>
    </div>
    <div class="fc-score-bar">
      <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{bar_colour}"></div></div>
      <span class="bar-label" style="color:{bar_colour}">{sl}</span>
    </div>
  </div>
  <div class="fc-just">{reason_html}</div>
  {rh}
</div>"""


# ── Astro-view card ───────────────────────────────────────────────────────────
def _astro_card(rank_lbl: str, rec: Dict, is_soul: bool, ak: str = "") -> str:
    label  = esc(rec["field_label"])
    domain = rec.get("domain", "interdisciplinary")
    score  = rec["final_score"]
    badge_colour = _da(domain)
    icon   = _i(domain)
    reg    = rec.get("registry", {})
    rh     = _reg_block(reg, "astro")
    gap    = rec.get("gap_breakdown", {})
    boosts = sorted([(k,v) for k,v in gap.items() if v and v > 0.001], key=lambda x:-x[1])
    pens   = sorted([(k,v) for k,v in gap.items() if v and v < -0.001], key=lambda x:x[1])
    top_pl = rec.get("top_affinity_planets", {})
    sc     = rec.get("score_components", {})
    blended= sc.get("blended", 0); gbp = sc.get("gap_boost_pct", 0); gpp = sc.get("gap_penalty_pct", 0)
    bi = "".join(f'<span class="gap-boost">+{v:.3f} {k}</span>' for k,v in boosts[:5])
    pi = "".join(f'<span class="gap-pen">{v:.3f} {k}</span>'   for k,v in pens[:3])
    pli= "".join(f'<span class="planet-pill">{esc(p)} {w:.2f}</span>' for p,w in list(top_pl.items())[:3])
    pen_row = f"<div class='amg'><span class='aml'>Penalties</span>{pi}</div>" if pi else ""

    if is_soul:
        reason_html = _soul_reason_html(rec, ak)
        card_style  = "border-left:5px solid #7b1fa2;background:#fdf3ff"
        sr          = '<div class="soul-ribbon">✨ Soul-Aligned</div>'
    else:
        reason_raw  = rec.get("llm_astrological_reason","").strip() or \
                      "Score driven by planetary affinity and domain-aptitude convergence."
        reason_html = f"<p>{esc(reason_raw)}</p>"
        card_style  = "border-left:5px solid #5c6bc0;background:#f8f9fe"
        sr          = ""

    return f"""
<div class="fc" style="{card_style}">
  {sr}
  <div class="fch">
    <span class="fc-rank">{rank_lbl}</span><span class="fc-icon">{icon}</span>
    <div class="fctb">
      <span class="fc-title">{label}</span>
      <span class="fc-badge" style="background:{badge_colour}">{domain.upper()}</span>
    </div>
    <div class="a-score-block">
      <span class="a-score-val">{score:.1f}</span>
      <span class="a-score-detail">base {blended:.1f} +{gbp:.0f}% -{gpp:.0f}%</span>
    </div>
  </div>
  <div class="fc-just">{reason_html}</div>
  <div class="ameta">
    <div class="amg"><span class="aml">Planets</span>{pli}</div>
    <div class="amg"><span class="aml">Boosts</span>{bi or "<em>none</em>"}</div>
    {pen_row}
  </div>
  {rh}
</div>"""


# ── Remaining fields table ────────────────────────────────────────────────────
def _remaining_table(all_results: List[Dict], shown_ids: set, top: float = 175) -> str:
    rest = [r for r in all_results if r["field_id"] not in shown_ids][:15]
    if not rest: return ""
    rows = ""
    for i, r in enumerate(rest, 1):
        d = r.get("domain",""); ac = _da(d); score = r["final_score"]
        exams = r.get("registry",{}).get("admission_exams",[])
        ex_str = " · ".join(_fe(e) for e in exams[:2])
        ug = r.get("registry",{}).get("ug_program","")
        sl_label = _sl(score, top)
        rows += f"""<tr>
  <td class="rt-rank">{i}</td>
  <td><span>{_i(d)}</span> <strong>{esc(r['field_label'])}</strong>
    <span class="rt-badge" style="background:{ac}">{d.upper()}</span></td>
  <td class="rt-score">{score:.1f}</td>
  <td style="font-size:12px;color:#555">{sl_label}</td>
  <td style="font-size:12px;color:#555">{esc(ug) or "—"}</td>
  <td style="font-size:12px;color:#555">{esc(ex_str) or "—"}</td>
</tr>"""
    return f"""
<div class="section-title" style="margin-top:32px">Other High-Scoring Fields</div>
<div class="table-wrap">
<table class="rem-table">
  <thead><tr><th>#</th><th>Field</th><th>Score</th><th>Match</th><th>UG Programme</th><th>Key Exam</th></tr></thead>
  <tbody>{rows}</tbody>
</table></div>"""


# ── Planet panel (astro view) ─────────────────────────────────────────────────
def _planet_panel(payload: NatalPayloadV2) -> str:
    digs    = getattr(payload, "planet_dignities", {})
    ak      = getattr(payload, "atmakaraka", "")
    amk     = getattr(payload, "amatyakaraka", "")
    h10     = getattr(payload, "h10_lord", "")
    combust = getattr(payload, "combust_planets", [])
    nb      = getattr(payload, "neecha_bhanga_planets", [])
    rows = ""
    for p in ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"]:
        d  = digs.get(p, "")
        roles = [r for r, pl in [("AK",ak),("AmK",amk),("H10",h10)] if pl == p]
        rs    = "".join(f'<span class="a-role">{r}</span>' for r in roles)
        flags = ("🔥" if p in combust else "") + (" ↑NB" if p in nb else "")
        dc = "#1b5e20" if d in ("EXALTED","OWN") else ("#b71c1c" if d == "DEBILITATED" else "#333")
        rows += f"<tr><td>{esc(p)}{rs}</td><td style='color:{dc}'>{esc(d) or '—'}{flags}</td></tr>"
    return f"""<div class="planet-panel">
  <div class="panel-title">Planetary Dignities</div>
  <table class="planet-table">
    <thead><tr><th>Planet</th><th>Dignity</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>"""


# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f8;color:#1a1a2e;line-height:1.55}
.report-header{background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:26px 40px 20px}
.brand{display:inline-block;background:rgba(255,255,255,.18);border-radius:20px;padding:2px 14px;font-size:11px;font-weight:800;letter-spacing:1.5px;margin-bottom:10px}
.rh-title{font-size:22px;font-weight:700}.rh-sub{font-size:13px;opacity:.7;margin-top:3px}
.chart-header{background:#fff;border-radius:12px;padding:20px 28px;box-shadow:0 2px 12px rgba(0,0,0,.07);margin:22px 40px 0;display:flex;gap:32px;flex-wrap:wrap;align-items:flex-start}
.ch-left{flex:1;min-width:200px}.ch-name{font-size:22px;font-weight:800;color:#1a237e}.ch-meta{font-size:13px;color:#666;margin-top:4px}
.ch-right{display:flex;flex-direction:column;gap:10px}.ch-karakas{display:flex;gap:20px;flex-wrap:wrap}
.kk-item{display:flex;flex-direction:column}.kk-role{font-size:10px;font-weight:700;text-transform:uppercase;color:#999;letter-spacing:.5px}
.kk-planet{font-size:15px;font-weight:600;color:#1a237e;margin-top:2px}
.dig-badge{display:inline-block;font-size:9px;font-weight:700;padding:1px 6px;border-radius:8px;color:#fff;margin-left:4px;vertical-align:middle}
.ch-yogas{display:flex;flex-wrap:wrap;gap:5px}.yoga-pill{background:#ede7f6;color:#4a148c;font-size:11px;font-weight:600;padding:3px 9px;border-radius:10px}
.toggle-bar{display:flex;margin:20px 40px;background:#e8eaf6;border-radius:8px;padding:4px;width:fit-content}
.tbtn{padding:9px 32px;border:none;background:transparent;cursor:pointer;font-size:14px;font-weight:600;border-radius:6px;color:#5c6bc0;transition:all .18s}
.tbtn.active{background:#283593;color:#fff;box-shadow:0 2px 10px rgba(40,53,147,.3)}
.content{padding:0 40px 56px}.section-title{font-size:17px;font-weight:700;color:#1a237e;margin:26px 0 14px}
.overview-box{border-radius:12px;padding:16px 22px;margin-bottom:20px;font-size:14px;line-height:1.7}
.overview-parent{background:#fffde7;border-left:5px solid #f9a825}.overview-astro{background:#e8f5e9;border-left:5px solid #2e7d32;color:#1b5e20}
.cards-grid{display:flex;flex-direction:column;gap:18px}
.fc{border-radius:12px;padding:22px 24px;box-shadow:0 2px 12px rgba(0,0,0,.07);position:relative;transition:box-shadow .2s}
.fc:hover{box-shadow:0 4px 22px rgba(0,0,0,.13)}
.soul-ribbon{position:absolute;top:14px;right:16px;background:linear-gradient(135deg,#6a1b9a,#ab47bc);color:#fff;font-size:11px;font-weight:700;padding:3px 12px;border-radius:12px}
.fch{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.fc-rank{font-size:28px;font-weight:800;color:#283593;min-width:36px}.fc-icon{font-size:24px}
.fctb{flex:1;min-width:180px}.fc-title{font-size:17px;font-weight:700;display:block}
.fc-badge{color:#fff;font-size:10px;font-weight:700;padding:2px 9px;border-radius:10px;display:inline-block;margin-top:3px}
.fc-score-bar{display:flex;flex-direction:column;align-items:flex-end;gap:4px;min-width:120px}
.bar-track{width:120px;height:8px;background:#e0e0e0;border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px}.bar-label{font-size:11px;font-weight:700}
.fc-just{font-size:14px;line-height:1.7;color:#333;margin-bottom:14px;padding:12px 16px;background:rgba(255,255,255,.6);border-radius:8px}
.fc-just p{margin-bottom:8px}.fc-just p:last-child{margin-bottom:0}
.a-score-block{display:flex;flex-direction:column;align-items:flex-end;min-width:80px}
.a-score-val{font-size:22px;font-weight:800;color:#1b5e20}.a-score-detail{font-size:11px;color:#888}
.ameta{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}.amg{display:flex;flex-wrap:wrap;align-items:center;gap:5px}
.aml{font-size:11px;font-weight:700;text-transform:uppercase;color:#888;letter-spacing:.4px;margin-right:3px}
.planet-pill{background:#e8eaf6;color:#1a237e;font-size:11px;font-weight:600;padding:2px 8px;border-radius:8px}
.gap-boost{background:#e8f5e9;color:#2e7d32;font-size:11px;font-weight:600;padding:2px 8px;border-radius:8px}
.gap-pen{background:#fce4ec;color:#b71c1c;font-size:11px;font-weight:600;padding:2px 8px;border-radius:8px}
.a-role{background:#e8eaf6;color:#283593;font-size:10px;font-weight:700;padding:1px 5px;border-radius:6px;margin-left:3px;vertical-align:middle}
.rt2{width:100%;border-collapse:collapse;margin-top:4px;font-size:13px}
.rt2 tr{border-bottom:1px solid rgba(0,0,0,.06)}.rt2 tr:last-child{border-bottom:none}
.rl{font-weight:700;color:#555;padding:5px 12px 5px 0;white-space:nowrap;width:130px;vertical-align:top}
.rt2 td{padding:5px 0}.rn{font-size:11px;color:#888;display:block;margin-top:1px}
.exam-pill{display:inline-block;background:#fff3e0;color:#e65100;font-size:11px;font-weight:600;padding:2px 8px;border-radius:8px;margin:1px}
.astro-meta-row{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:20px}
.planet-panel{background:#fff;border-radius:12px;padding:16px 20px;box-shadow:0 2px 10px rgba(0,0,0,.07);min-width:220px}
.panel-title{font-size:11px;font-weight:700;text-transform:uppercase;color:#999;letter-spacing:.5px;margin-bottom:8px}
.planet-table{width:100%;border-collapse:collapse;font-size:13px}
.planet-table th{background:#f5f5f5;padding:5px 10px;text-align:left;font-weight:700;color:#555}
.planet-table td{padding:4px 10px;border-bottom:1px solid #f0f0f0}
.table-wrap{overflow-x:auto}
.rem-table{width:100%;border-collapse:collapse;font-size:13px;min-width:700px}
.rem-table thead th{background:#283593;color:#fff;padding:9px 14px;text-align:left;font-weight:700}
.rem-table tbody tr:hover td{background:#f5f7ff}
.rem-table td{padding:9px 14px;border-bottom:1px solid #eee;vertical-align:top}
.rt-rank{font-weight:800;color:#283593;font-size:15px;text-align:center;width:36px}
.rt-score{font-weight:700;color:#2e7d32;text-align:right;white-space:nowrap}
.rt-badge{font-size:9px;font-weight:700;color:#fff;padding:1px 6px;border-radius:8px;margin-left:5px;vertical-align:middle}
.soul-divider{display:flex;align-items:center;gap:14px;margin:28px 0 16px}
.soul-divider::before,.soul-divider::after{content:'';flex:1;height:1px;background:linear-gradient(to right,transparent,#9c27b0,transparent)}
.soul-divider-label{font-size:14px;font-weight:700;color:#6a1b9a;white-space:nowrap}
.filter-note{font-size:12px;color:#888;font-style:italic;margin-bottom:12px}
.report-footer{text-align:center;font-size:12px;color:#999;padding:20px 40px 28px}
"""

_JS = """
function switchView(v){
  document.getElementById('view-parent').style.display=v==='parent'?'':'none';
  document.getElementById('view-astro').style.display=v==='astro'?'':'none';
  document.querySelectorAll('.tbtn').forEach(b=>b.classList.remove('active'));
  document.getElementById('btn-'+v).classList.add('active');
}
"""


# ── Soul parent card (purple, 2-paragraph justification) ─────────────────────
def _make_soul_parent_card(rec: Dict, ak: str, top: float = 175) -> str:
    """Parent-view soul card with 2-paragraph soul-aligned justification."""
    label        = esc(rec["field_label"])
    domain       = rec.get("domain", "interdisciplinary")
    score        = rec["final_score"]
    pct          = _pct(score)
    sl           = esc(_sl(score, top))
    badge_colour = _da(domain)
    icon         = _i(domain)
    reg          = rec.get("registry", {})
    rh           = _reg_block(reg, "parent")
    reason_html  = _soul_reason_html(rec, ak)
    return f"""
<div class="fc" style="border-left:5px solid #7b1fa2;background:#fdf3ff">
  <div class="soul-ribbon">&#10024; Soul-Aligned</div>
  <div class="fch">
    <span class="fc-rank">Soul</span><span class="fc-icon">{icon}</span>
    <div class="fctb">
      <span class="fc-title">{label}</span>
      <span class="fc-badge" style="background:{badge_colour}">{domain.upper()}</span>
    </div>
    <div class="fc-score-bar">
      <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:#7b1fa2"></div></div>
      <span class="bar-label" style="color:#7b1fa2">{sl}</span>
    </div>
  </div>
  <div class="fc-just">{reason_html}</div>
  {rh}
</div>"""


# ── Main entry point ──────────────────────────────────────────────────────────
def build_web_report_html(results, payload) -> str:
    """Render the career guidance HTML report (no file I/O)."""
    ak   = getattr(payload, "atmakaraka", "")
    sorted_results = sorted(results, key=lambda x: (-x["final_score"], x["field_id"]))
    top_score = sorted_results[0]["final_score"] if sorted_results else 175

    # Separate LLM-tagged soul field from match fields
    lm_soul_fields  = [r for r in sorted_results if r.get("llm_group") == "soul"]
    all_match_fields = [r for r in sorted_results if r.get("llm_group", "match") != "soul"]

    # Top-5 cards: prefer LLM's explicit top-5 selection (llm_rank 1–5) so the
    # HTML fields and justification text always match the LLM JSON output.
    # Fall back to Python-score top-5 only when LLM ranking is unavailable.
    lm_top5 = sorted(
        [r for r in all_match_fields if 1 <= r.get("llm_rank", 99) <= 5],
        key=lambda x: x.get("llm_rank", 99),
    )
    if len(lm_top5) >= 3:
        match_fields = lm_top5[:5]
    else:
        # Fallback: Python-score top-5 filtered to Strong/Excellent
        strong_matches = [r for r in all_match_fields if _is_strong(r["final_score"], top_score)][:5]
        match_fields   = strong_matches if strong_matches else all_match_fields[:3]

    strong_matches = match_fields  # kept for filter_note count

    # Soul field: use LLM's choice when available (engine guarantees it is always merged);
    # fall back to deterministic AK-domain picker only when LLM returned no soul field.
    shown_ids = {r["field_id"] for r in match_fields}
    if lm_soul_fields:
        soul_field = lm_soul_fields[0]
    else:
        soul_field = _pick_soul_field(sorted_results, shown_ids, ak)
    if soul_field:
        shown_ids.add(soul_field["field_id"])

    parent_overview = esc((results[0].get("llm_parent_summary","") if results else "").strip())
    astro_overview  = esc((results[0].get("llm_selection_rationale","") if results else "").strip())
    student_name    = esc(getattr(payload, "name", "Student"))
    generated_at    = datetime.now().strftime("%d %B %Y, %I:%M %p")
    chart_hdr       = _chart_header(payload)

    count_strong = len(match_fields)
    filter_note  = (f'<p class="filter-note">Showing {count_strong} top recommended field'
                    f'{"s" if count_strong != 1 else ""}. '
                    f'Additional fields appear in the table below.</p>') if count_strong < 5 else ""

    # ── Parent view ────────────────────────────────────────────────────────────
    pob = f'<div class="overview-box overview-parent"><p>{parent_overview}</p></div>' if parent_overview else ""
    pm  = "\n".join(_parent_card(f"#{i+1}", r, top=top_score) for i, r in enumerate(match_fields))
    psb = ""
    if soul_field:
        soul_card_p = _make_soul_parent_card(soul_field, ak, top=top_score)
        psb = (f'<div class="soul-divider"><span class="soul-divider-label">'
               f'&#10024; Soul-Aligned Recommendation</span></div>\n{soul_card_p}')
    prem = _remaining_table(sorted_results, shown_ids, top=top_score)

    parent_view = f"""
<div id="view-parent" class="view-section">
  <div class="section-title">Your Child's Top Career Recommendations</div>
  {pob}{filter_note}
  <div class="cards-grid">{pm}</div>
  {psb}
  {prem}
</div>"""

    # ── Astro view ─────────────────────────────────────────────────────────────
    aob = f'<div class="overview-box overview-astro"><p>{astro_overview}</p></div>' if astro_overview else ""
    pnl = _planet_panel(payload)
    am  = "\n".join(_astro_card(f"#{i+1}", r, False, ak) for i, r in enumerate(match_fields))
    asb = ""
    if soul_field:
        asb = (f'<div class="soul-divider"><span class="soul-divider-label">'
               f'&#10024; Soul-Aligned Field</span></div>\n{_astro_card("Soul", soul_field, True, ak)}')
    arem = _remaining_table(sorted_results, shown_ids, top=top_score)


    astro_view = f"""
<div id="view-astro" class="view-section" style="display:none">
  <div class="section-title">Astrological Career Analysis</div>
  {aob}
  <div class="astro-meta-row">{pnl}</div>
  <div class="section-title" style="margin-top:8px">Top Match Fields</div>
  {filter_note}
  <div class="cards-grid">{am}</div>
  {asb}
  {arem}
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>JyotishAI Career Report &#8212; {student_name}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="report-header">
  <div class="brand">JYOTISHAI</div>
  <div class="rh-title">Career Guidance Report &#8212; {student_name}</div>
  <div class="rh-sub">AI-powered Vedic Astrology Career Analysis &nbsp;&middot;&nbsp; {generated_at}</div>
</div>
{chart_hdr}
<div class="toggle-bar">
  <button class="tbtn active" id="btn-parent" onclick="switchView('parent')">&#128106; For Parents</button>
  <button class="tbtn"        id="btn-astro"  onclick="switchView('astro')">&#128301; For Astrologers</button>
</div>
<div class="content">
  {parent_view}
  {astro_view}
</div>
<div class="report-footer">
  JyotishAI Engine &nbsp;&middot;&nbsp; {generated_at} &nbsp;&middot;&nbsp; For educational guidance only.
</div>
<script>{_JS}</script>
</body>
</html>"""


def generate_web_report(results, payload, output_dir="educational_records"):
    os.makedirs(output_dir, exist_ok=True)
    name = getattr(payload, "name", "student").lower().replace(" ", "_")
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp   = os.path.join(output_dir, f"{name}_web_report_{ts}.html")
    page = build_web_report_html(results, payload)

    with open(fp, "w", encoding="utf-8") as fh:
        fh.write(page)
    logger.info(f"Web report -> {fp}")
    return fp
