# -*- coding: utf-8 -*-
"""
report_uplift.py  ·  JyotishAI
--------------------------------
Shared "production uplift" layer for the Career Timeline HTML report.

Provides the app-shell chrome (fixed nav, scroll progress, back-to-top),
a dark/light theme, scroll-reveal + bar/line animations, a print/PDF path,
CSS that repairs the previously-unstyled ``roadmap-*`` detail cards, and an
enhanced career-trajectory area chart.

Two entry points share these assets so the look never drifts:

* ``web_report.generate_career_timeline_report`` imports ``UPLIFT_CSS``,
  ``app_nav_html``, ``app_chrome_js`` and ``build_trajectory_chart`` and
  emits the uplifted markup natively.
* ``uplift_report.py`` (repo root, CLI) calls ``uplift_html`` to transform an
  already-generated report file after the fact.

Pure standard library (``re`` only); safe to import anywhere.
"""

from __future__ import annotations
import re

__all__ = [
    "UPLIFT_CSS", "NAV_SECTIONS", "app_nav_html", "back_to_top_html",
    "app_chrome_js", "build_trajectory_chart", "uplift_html", "is_uplifted",
]

_MARKER = "PRODUCTION UPLIFT"  # idempotency sentinel inside UPLIFT_CSS


# ======================================================================
#  CSS
# ======================================================================
UPLIFT_CSS = r"""
/* ===================================================================
   PRODUCTION UPLIFT  ·  app shell · theme · motion · component repair
   =================================================================== */
:root{ --nav-h:60px; --ease:cubic-bezier(.22,.61,.36,1); }
html{scroll-padding-top:calc(var(--nav-h) + 18px);}
body{padding-top:var(--nav-h);}

.app-progress{position:fixed;top:0;left:0;height:3px;width:0;z-index:1002;
  background:linear-gradient(90deg,var(--gold,#C9A84C),#E7CE86);
  box-shadow:0 0 10px rgba(201,168,76,.55);transition:width .12s linear;}

.app-nav{position:fixed;top:0;left:0;right:0;height:var(--nav-h);z-index:1001;
  display:flex;align-items:center;gap:16px;padding:0 22px;
  background:rgba(20,20,32,.80);backdrop-filter:blur(16px) saturate(1.3);
  -webkit-backdrop-filter:blur(16px) saturate(1.3);
  border-bottom:1px solid rgba(201,168,76,.20);}
.app-nav-brand{display:flex;align-items:center;gap:11px;flex-shrink:0;}
.app-nav-logo{width:32px;height:32px;border-radius:10px;flex-shrink:0;color:#1A1A2E;
  background:linear-gradient(135deg,#E7CE86,var(--gold,#C9A84C));font-size:16px;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 2px 10px rgba(201,168,76,.4);}
.app-nav-title{font-family:'Cormorant Garamond',serif;font-size:17px;font-weight:700;
  color:#fff;letter-spacing:.3px;white-space:nowrap;line-height:1.05;}
.app-nav-title small{display:block;font-family:'Inter',sans-serif;font-size:8px;font-weight:600;
  letter-spacing:2px;text-transform:uppercase;color:var(--gold,#C9A84C);opacity:.9;margin-top:1px;}
.app-nav-links{display:flex;align-items:center;gap:2px;margin-left:12px;flex:1;min-width:0;}
.app-nav-link{font-size:12.5px;font-weight:500;color:rgba(255,255,255,.60);
  text-decoration:none;padding:7px 12px;border-radius:8px;white-space:nowrap;
  transition:color .18s,background .18s;letter-spacing:.2px;}
.app-nav-link:hover{color:#fff;background:rgba(255,255,255,.08);}
.app-nav-link.active{color:var(--gold,#C9A84C);background:rgba(201,168,76,.14);}
.app-nav-actions{display:flex;align-items:center;gap:8px;margin-left:auto;flex-shrink:0;}
.app-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;
  height:36px;padding:0 13px;border-radius:9px;cursor:pointer;font-size:12px;font-weight:600;
  color:rgba(255,255,255,.86);background:rgba(255,255,255,.09);
  border:1px solid rgba(255,255,255,.15);transition:all .18s;white-space:nowrap;font-family:inherit;}
.app-btn:hover{background:rgba(255,255,255,.17);color:#fff;border-color:rgba(201,168,76,.45);}
.app-btn-icon{width:36px;padding:0;font-size:15px;}
.app-nav-toggle{display:none;}

@media(max-width:900px){
  .app-nav-links{position:fixed;top:var(--nav-h);left:0;right:0;flex-direction:column;
    align-items:stretch;gap:2px;background:rgba(16,16,26,.98);backdrop-filter:blur(16px);
    padding:10px 14px 16px;border-bottom:1px solid rgba(201,168,76,.22);
    transform:translateY(-14px);opacity:0;pointer-events:none;transition:all .22s var(--ease);
    max-height:calc(100vh - var(--nav-h));overflow-y:auto;}
  .app-nav-links.open{transform:none;opacity:1;pointer-events:auto;}
  .app-nav-link{padding:12px 14px;font-size:14px;}
  .app-nav-toggle{display:inline-flex;}
  .app-nav-actions .app-btn-label{display:none;}
  .app-nav-title small{display:none;}
}
@media(max-width:520px){ .app-nav-title{font-size:15px;} .app-nav{gap:8px;padding:0 14px;} }

.app-totop{position:fixed;right:22px;bottom:22px;z-index:1000;width:46px;height:46px;
  border-radius:50%;border:none;cursor:pointer;font-size:19px;color:#1A1A2E;
  background:linear-gradient(135deg,#E7CE86,var(--gold,#C9A84C));
  box-shadow:0 6px 22px rgba(201,168,76,.48);
  opacity:0;transform:translateY(16px) scale(.9);pointer-events:none;
  transition:all .28s var(--ease);}
.app-totop.show{opacity:1;transform:none;pointer-events:auto;}
.app-totop:hover{transform:translateY(-3px);box-shadow:0 11px 28px rgba(201,168,76,.6);}

.reveal{opacity:0;transform:translateY(24px);
  transition:opacity .7s var(--ease),transform .7s var(--ease);will-change:opacity,transform;}
.reveal.in{opacity:1;transform:none;}
@media(prefers-reduced-motion:reduce){
  .reveal{opacity:1 !important;transform:none !important;transition:none;}
}

/* enhanced trajectory chart */
.traj-sub{font-size:12.5px;color:var(--muted,#5F5F7A);line-height:1.6;margin:-8px 0 16px;max-width:640px;}
.traj-chart{display:block;width:100%;height:auto;overflow:visible;}
.traj-legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:14px;
  padding-top:14px;border-top:1px solid var(--border-soft,#F0ECE2);}
.traj-legend-item{display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--mid,#3D3D5C);}
.traj-legend-dot{width:11px;height:11px;border-radius:3px;flex-shrink:0;}

/* ---- repair: the roadmap-* detail cards shipped with NO styling ---- */
.roadmap-year-card{background:var(--surface,#fff);border:1px solid var(--border,#E8E2D4);
  border-radius:var(--radius-lg,18px);padding:22px 26px;margin-bottom:18px;
  box-shadow:var(--shadow-sm,0 1px 4px rgba(26,26,46,.06));color:var(--mid,#3D3D5C);
  position:relative;overflow:hidden;
  transition:box-shadow .22s var(--ease),transform .22s var(--ease);}
.roadmap-year-card:hover{box-shadow:var(--shadow-md,0 4px 16px rgba(26,26,46,.08));transform:translateY(-2px);}
.roadmap-year-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;
  background:linear-gradient(180deg,var(--gold,#C9A84C),rgba(201,168,76,.15));}
.roadmap-year-header{display:flex;align-items:center;gap:13px;flex-wrap:wrap;margin-bottom:14px;
  padding-bottom:14px;border-bottom:1px solid var(--border-soft,#F0ECE2);}
.roadmap-year-num{font-family:'Cormorant Garamond',serif;font-size:30px;font-weight:700;
  color:var(--deep,#1A1A2E);line-height:1;letter-spacing:-.5px;}
.roadmap-year-badge{font-size:9.5px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;
  padding:4px 11px;border-radius:20px;background:var(--gold-light,rgba(201,168,76,.10));
  color:var(--amber,#B8720A);border:1px solid var(--gold-mid,rgba(201,168,76,.22));}
.roadmap-weather{font-size:13px;font-weight:600;color:var(--mid,#3D3D5C);}
.roadmap-score{margin-left:auto;font-size:15px;font-weight:700;color:var(--gold,#C9A84C);
  background:var(--gold-light,rgba(201,168,76,.10));border:1px solid var(--gold-mid,rgba(201,168,76,.22));
  border-radius:20px;padding:4px 15px;}
.roadmap-event{font-family:'Cormorant Garamond',serif;font-size:19px;font-weight:700;
  color:var(--deep,#1A1A2E);margin-bottom:11px;letter-spacing:.15px;}
.roadmap-narrative{font-size:13.5px;color:var(--mid,#3D3D5C);line-height:1.78;margin-bottom:12px;}
.roadmap-karaka{font-size:12px;color:var(--mid,#3D3D5C);line-height:1.6;margin:10px 0;padding:8px 14px;
  background:var(--gold-light,rgba(201,168,76,.10));border-radius:8px;
  border:1px solid var(--gold-mid,rgba(201,168,76,.22));}
.roadmap-karaka strong,.roadmap-narrative strong{color:var(--deep,#1A1A2E);font-weight:600;}
.roadmap-natal,.roadmap-saturn{font-size:12.5px;color:var(--mid,#3D3D5C);line-height:1.66;
  margin:7px 0;padding:9px 15px;background:var(--surface-warm,#FAF8F3);border-radius:8px;
  border-left:3px solid var(--purple,#6B5B8E);}
.roadmap-saturn{border-left-color:var(--amber,#B8720A);}
.roadmap-natal strong,.roadmap-saturn strong{color:var(--deep,#1A1A2E);}
.roadmap-yoga{font-size:12.5px;color:var(--mid,#3D3D5C);line-height:1.7;margin:7px 0;padding:9px 15px;
  background:var(--green-light,rgba(30,123,80,.09));border-radius:8px;border-left:3px solid var(--green,#1E7B50);}
.roadmap-yoga b,.roadmap-yoga strong{color:var(--deep,#1A1A2E);font-weight:700;}

/* ---- dark theme ---- */
html[data-theme=dark]{
  --bg:#0E1016; --surface:#171A22; --surface-warm:#1D212B;
  --deep:#ECEAE3; --mid:#C2C6D2; --muted:#8C92A2;
  --border:#2A303D; --border-soft:#222732;
  --gold:#D9BA63; --gold-light:rgba(217,186,99,.13); --gold-mid:rgba(217,186,99,.30);
  --purple:#A793D6; --purple-light:rgba(167,147,214,.14);
  --green:#43C289; --green-light:rgba(67,194,137,.14);
  --amber:#E3A742; --amber-light:rgba(227,167,66,.15);
  --red:#E37A6F; --red-light:rgba(227,122,111,.15);
  --shadow-sm:0 1px 4px rgba(0,0,0,.4),0 2px 10px rgba(0,0,0,.3);
  --shadow-md:0 6px 20px rgba(0,0,0,.45);
}
html[data-theme=dark] body{background:var(--bg);color:var(--deep);}
html[data-theme=dark] .tl-header{background:#11121b;}
html[data-theme=dark] .tl-exec-panel,
html[data-theme=dark] .rmap-cmp-wrap,
html[data-theme=dark] .tl-audit-panel,
html[data-theme=dark] .rmap-year-block,
html[data-theme=dark] .rmap-node-card,
html[data-theme=dark] .transit-year-card,
html[data-theme=dark] .cal-year-card,
html[data-theme=dark] .mt-section,
html[data-theme=dark] .traj-section,
html[data-theme=dark] .glossary-panel,
html[data-theme=dark] .planet-panel,
html[data-theme=dark] .outcome-bar,
html[data-theme=dark] .roadmap-year-card{background:var(--surface);border-color:var(--border);}
html[data-theme=dark] .rmap-node-marker{background:var(--surface-warm);border-color:var(--border);}
html[data-theme=dark] .rmap-node-year{color:var(--deep);}
html[data-theme=dark] .ad-card:hover{background:#1C212C;}
html[data-theme=dark] .d10-panel{
  background:linear-gradient(135deg,rgba(129,140,248,.14),rgba(99,102,241,.07));
  border-color:rgba(129,140,248,.3);}
html[data-theme=dark] .d10-panel-title,html[data-theme=dark] .d10-cell-label{color:#a5b4fc;}
html[data-theme=dark] .insight-panel{
  background:linear-gradient(135deg,rgba(45,212,191,.12),rgba(20,184,166,.05));
  border-color:rgba(45,212,191,.28);}
html[data-theme=dark] .insight-panel-title,html[data-theme=dark] .insight-cell-label{color:#5eead4;}
html[data-theme=dark] .d10-cell,html[data-theme=dark] .insight-cell{
  background:rgba(255,255,255,.05);border-color:rgba(255,255,255,.10);}
html[data-theme=dark] .d10-cell-val,html[data-theme=dark] .insight-cell-val{color:var(--deep);}
html[data-theme=dark] .cal-heading,
html[data-theme=dark] .rmap-node-event,
html[data-theme=dark] .transit-year-num,
html[data-theme=dark] .traj-heading{color:var(--deep);}
html[data-theme=dark] .cal-heading{border-bottom-color:var(--gold);}
html[data-theme=dark] .planet-bar-name{color:var(--deep);}
html[data-theme=dark] .tl-audit-detail,html[data-theme=dark] .tl-footer-line,
html[data-theme=dark] .tl-footer-note{color:var(--muted);}

/* ---- print: hide app-chrome, expand collapsibles ---- */
@media print{
  .app-nav,.app-progress,.app-totop{display:none !important;}
  body{padding-top:0 !important;}
  .reveal{opacity:1 !important;transform:none !important;}
  .roadmap-year-card{box-shadow:none;border:1px solid #e2e8f0;break-inside:avoid;page-break-inside:avoid;}
  .traj-section{break-inside:avoid;}
}
"""


# ======================================================================
#  Navigation  (dynamic — only links to sections that exist)
# ======================================================================
# (anchor id, nav label) in document order
NAV_SECTIONS = [
    ("overview",   "Overview"),
    ("validation", "Validation"),
    ("snapshot",   "Snapshot"),
    ("trajectory", "Trajectory"),
    ("roadmap",    "Roadmap"),
    ("foreign",    "Foreign"),
    ("classical",  "Classical"),
    ("glossary",   "Glossary"),
]


def app_nav_html(present_ids, title="Career Timeline", brand="JyotishAI"):
    """Return the fixed nav + progress bar. ``present_ids`` is the set/list of
    anchor ids that actually exist in the document; only those become links."""
    present = set(present_ids)
    links = "".join(
        '<a class="app-nav-link" href="#%s">%s</a>' % (sid, label)
        for sid, label in NAV_SECTIONS if sid in present
    )
    return (
        '<div class="app-progress" id="appProgress"></div>\n'
        '<nav class="app-nav">'
        '<div class="app-nav-brand">'
        '<div class="app-nav-logo">&#10022;</div>'
        '<div class="app-nav-title">%s<small>%s &middot; Career Timeline</small></div>'
        '</div>'
        '<div class="app-nav-links" id="navLinks">%s</div>'
        '<div class="app-nav-actions">'
        '<button class="app-btn app-btn-icon" id="themeBtn" title="Toggle light / dark" aria-label="Toggle dark mode">&#9790;</button>'
        '<button class="app-btn" id="printBtn" title="Print or save as PDF"><span aria-hidden="true">&#8681;</span><span class="app-btn-label">PDF</span></button>'
        '<button class="app-btn app-btn-icon app-nav-toggle" id="menuBtn" aria-label="Open menu" aria-expanded="false">&#9776;</button>'
        '</div></nav>\n'
    ) % (title, brand, links)


def back_to_top_html():
    return '<button class="app-totop" id="toTop" aria-label="Back to top" title="Back to top">&#8593;</button>\n'


# ======================================================================
#  Client JS  (theme · progress · reveal · bar/line animation · print)
# ======================================================================
def app_chrome_js():
    return r"""<script>
(function(){
  var doc=document.documentElement;
  var themeBtn=document.getElementById('themeBtn');
  function setTheme(t){doc.setAttribute('data-theme',t);if(themeBtn){themeBtn.innerHTML=(t==='dark')?'&#9728;':'&#9790;';themeBtn.title=(t==='dark')?'Switch to light':'Switch to dark';}}
  var initial=(window.matchMedia&&matchMedia('(prefers-color-scheme:dark)').matches)?'dark':'light';
  setTheme(initial);
  if(themeBtn)themeBtn.addEventListener('click',function(){setTheme(doc.getAttribute('data-theme')==='dark'?'light':'dark');});

  // Fix (2026-07-07): togglePD is referenced by onclick="togglePD(id)" on the
  // PD sub-periods button, and now also the score-decomposition and why/why-not
  // panel toggles, but was never defined anywhere — those buttons silently did
  // nothing when clicked. Generic show/hide-by-id toggle, reused by all three.
  window.togglePD=function(id){
    var el=document.getElementById(id);if(!el)return;
    var btn=document.getElementById('btn-'+id);
    var hidden=el.hasAttribute('hidden');
    if(hidden){el.removeAttribute('hidden');}else{el.setAttribute('hidden','');}
    if(btn)btn.setAttribute('aria-expanded',hidden?'true':'false');
  };

  var menuBtn=document.getElementById('menuBtn'),navLinks=document.getElementById('navLinks');
  if(menuBtn&&navLinks){menuBtn.addEventListener('click',function(){var o=navLinks.classList.toggle('open');menuBtn.setAttribute('aria-expanded',o);});
    navLinks.addEventListener('click',function(e){if(e.target.tagName==='A')navLinks.classList.remove('open');});}

  var prog=document.getElementById('appProgress'),toTop=document.getElementById('toTop');
  function onScroll(){var h=doc.scrollHeight-doc.clientHeight;var p=h>0?(doc.scrollTop/h)*100:0;
    if(prog)prog.style.width=p+'%';if(toTop)toTop.classList.toggle('show',doc.scrollTop>440);}
  window.addEventListener('scroll',onScroll,{passive:true});onScroll();
  if(toTop)toTop.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'});});

  var links=[].slice.call(document.querySelectorAll('.app-nav-link'));
  var secs=links.map(function(l){return document.querySelector(l.getAttribute('href'));}).filter(Boolean);
  if('IntersectionObserver' in window){
    var spy=new IntersectionObserver(function(es){es.forEach(function(en){if(en.isIntersecting){
      var id=en.target.id;links.forEach(function(l){l.classList.toggle('active',l.getAttribute('href')==='#'+id);});}});},
      {rootMargin:'-45% 0px -50% 0px',threshold:0});
    secs.forEach(function(x){spy.observe(x);});
    var rev=new IntersectionObserver(function(es,ob){es.forEach(function(en){if(en.isIntersecting){en.target.classList.add('in');ob.unobserve(en.target);}});},
      {rootMargin:'0px 0px -7% 0px',threshold:0.05});
    [].forEach.call(document.querySelectorAll('.reveal'),function(el){rev.observe(el);});
  } else {
    [].forEach.call(document.querySelectorAll('.reveal'),function(el){el.classList.add('in');});
  }

  var reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches;
  var fillSel='.planet-bar-fill,.rmap-node-scorefill,.rmap-matrix-fill,.bar-mini-fill,.fop-score-fill,.fop-c-fill';
  var fills=[].slice.call(document.querySelectorAll(fillSel));
  fills.forEach(function(f){f.setAttribute('data-w',f.style.width||'');});
  if(!reduce && 'IntersectionObserver' in window){
    fills.forEach(function(f){if(f.getAttribute('data-w')){f.style.width='0';f.style.transition='width 1.1s cubic-bezier(.22,.61,.36,1)';}});
    var barObs=new IntersectionObserver(function(es,ob){es.forEach(function(en){if(en.isIntersecting){
      var f=en.target;requestAnimationFrame(function(){f.style.width=f.getAttribute('data-w');});ob.unobserve(f);}});},{threshold:0.15});
    fills.forEach(function(f){barObs.observe(f);});
    var tp=document.getElementById('trajLine');var tsec=document.getElementById('trajectory');
    if(tp&&tp.getTotalLength&&tsec){var len=tp.getTotalLength();tp.style.strokeDasharray=len;tp.style.strokeDashoffset=len;
      var to=new IntersectionObserver(function(es,ob){es.forEach(function(en){if(en.isIntersecting){
        tp.style.transition='stroke-dashoffset 1.7s ease';tp.style.strokeDashoffset='0';ob.unobserve(en.target);}});},{threshold:0.25});
      to.observe(tsec);}
  }

  function expandForPrint(){[].forEach.call(document.querySelectorAll('.reveal'),function(el){el.classList.add('in');});
    fills.forEach(function(f){if(f.getAttribute('data-w'))f.style.width=f.getAttribute('data-w');});
    var tp=document.getElementById('trajLine');if(tp)tp.style.strokeDashoffset='0';}
  var printBtn=document.getElementById('printBtn');
  if(printBtn)printBtn.addEventListener('click',function(){window.print();});
  window.addEventListener('beforeprint',function(){doc.setAttribute('data-print-theme',doc.getAttribute('data-theme')||'light');setTheme('light');expandForPrint();});
  window.addEventListener('afterprint',function(){setTheme(doc.getAttribute('data-print-theme')||'light');});
})();
</script>
"""


# ======================================================================
#  Enhanced trajectory chart
# ======================================================================
def build_trajectory_chart(pairs, current_year=None, sub=None):
    """Return an animated area/line trajectory ``<section>``.

    ``pairs``        : list of ``(year, score_0_100)`` in chronological order.
    ``current_year`` : the year to flag with a NOW marker (defaults to the
                       middle-ish current point if omitted).
    """
    pairs = [(int(y), float(s)) for y, s in pairs if y is not None]
    if len(pairs) < 2:
        return ""
    years = [p[0] for p in pairs]
    scores = [max(0.0, min(100.0, p[1])) for p in pairs]
    if current_year is None:
        current_year = years[min(len(years) - 1, max(0, len(years) // 2))]

    W, H = 720.0, 250.0
    padL, padR, padT, padB = 46.0, 20.0, 26.0, 44.0
    lo = max(0.0, min(scores) - 12)
    hi = min(100.0, max(scores) + 12)
    if hi - lo < 25:
        hi = min(100.0, lo + 25)

    def X(i):
        return padL + i * (W - padL - padR) / (len(years) - 1)

    def Y(v):
        v = max(lo, min(hi, v))
        return (H - padB) - (v - lo) / (hi - lo) * (H - padB - padT)

    pts = [(X(i), Y(scores[i])) for i in range(len(years))]
    line = "M " + " L ".join("%.1f,%.1f" % p for p in pts)
    area = ("M %.1f,%.1f L " % (pts[0][0], H - padB)
            + " L ".join("%.1f,%.1f" % p for p in pts)
            + " L %.1f,%.1f Z" % (pts[-1][0], H - padB))

    grid = ""
    step = 10
    g = int((lo // step + 1) * step)
    while g < hi:
        gy = Y(g)
        grid += ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--border-soft,#F0ECE2)" stroke-width="1"/>'
                 '<text x="%.1f" y="%.1f" font-size="9" fill="var(--muted,#5F5F7A)" text-anchor="end">%d</text>'
                 % (padL, gy, W - padR, gy, padL - 8, gy + 3, g))
        g += step

    dots = ""
    for i, (x, y) in enumerate(pts):
        now = years[i] == current_year
        r = 6 if now else 4.5
        dots += ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="var(--surface,#fff)" stroke-width="2"/>'
                 % (x, y, r, "#E7CE86" if now else "var(--gold,#C9A84C)"))
        dots += ('<text x="%.1f" y="%.1f" font-size="10.5" font-weight="700" fill="var(--deep,#1A1A2E)" text-anchor="middle">%.0f%%</text>'
                 % (x, y - 13, scores[i]))
        dots += ('<text x="%.1f" y="%.1f" font-size="10" fill="var(--muted,#5F5F7A)" text-anchor="middle">%d</text>'
                 % (x, H - padB + 20, years[i]))
        if now:
            dots += ('<rect x="%.1f" y="%.1f" width="42" height="15" rx="7" fill="var(--gold,#C9A84C)"/>'
                     '<text x="%.1f" y="%.1f" font-size="8.5" font-weight="800" fill="#1A1A2E" text-anchor="middle" letter-spacing="0.5">NOW</text>'
                     % (x - 21, y - 40, x, y - 29))

    sub_txt = sub or ("Blended career-signal strength across the roadmap window. "
                      "Peaks mark the strongest promotion &amp; recognition windows; dips flag consolidation years.")
    return (
        '<section class="traj-section reveal" id="trajectory">'
        '<div class="traj-heading">Career Signal Trajectory</div>'
        '<div class="traj-sub">%s</div>'
        '<svg class="traj-chart" viewBox="0 0 %g %g" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">'
        '<defs><linearGradient id="trajFill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%%" stop-color="var(--gold,#C9A84C)" stop-opacity="0.28"/>'
        '<stop offset="100%%" stop-color="var(--gold,#C9A84C)" stop-opacity="0.02"/></linearGradient></defs>'
        '%s'
        '<path d="%s" fill="url(#trajFill)" stroke="none"/>'
        '<path id="trajLine" d="%s" fill="none" stroke="var(--gold,#C9A84C)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        '%s'
        '</svg>'
        '<div class="traj-legend">'
        '<div class="traj-legend-item"><span class="traj-legend-dot" style="background:var(--gold,#C9A84C)"></span>Blended career signal (0&ndash;100)</div>'
        '<div class="traj-legend-item"><span class="traj-legend-dot" style="background:#E7CE86"></span>Current year</div>'
        '</div>'
        '</section>'
    ) % (sub_txt, W, H, grid, area, line, dots)


# ======================================================================
#  Post-processor  (used by the CLI on already-generated report files)
# ======================================================================
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "param", "source", "track", "wbr"}


def is_uplifted(html):
    return _MARKER in html


def _auto_close(html):
    """Return closing tags for whatever is left open from ``<body>`` onward,
    excluding html/body (closed by the caller). Repairs truncated reports."""
    try:
        start = html.index("<body>")
    except ValueError:
        start = 0
    stack = []
    for m in re.finditer(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>', html[start:]):
        closing, name, selfclose = m.group(1), m.group(2).lower(), m.group(3)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == name:
                    del stack[i:]
                    break
        elif not selfclose and name not in _VOID:
            stack.append(name)
    stack = [t for t in stack if t not in ("html", "body")]
    return "".join("</%s>" % t for t in reversed(stack))


def _parse_year_scores(html):
    """Best-effort per-year (year, score%) extraction from roadmap cards."""
    nums = re.findall(r'roadmap-year-num">\s*(\d{4})', html)
    scores = re.findall(r'roadmap-score">\s*([0-9.]+)\s*%', html)
    pairs = []
    for y, s in zip(nums, scores):
        pairs.append((int(y), float(s)))
    # de-dup consecutive identical years while preserving order
    seen, out = set(), []
    for y, s in pairs:
        if y not in seen:
            seen.add(y)
            out.append((y, s))
    return out


def uplift_html(html, title=None, brand="JyotishAI"):
    """Transform an already-generated Career Timeline report into the uplifted
    style. Idempotent, and safe on both complete and truncated documents."""
    if is_uplifted(html):
        return html  # already processed

    if title is None:
        m = re.search(r'<h1 class="tl-name">(.*?)</h1>', html, re.S)
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else "Career Timeline"

    # 1) CSS
    if "</style>" in html:
        html = html.replace("</style>", UPLIFT_CSS + "\n</style>", 1)
    else:  # no style block (unexpected) — inject one in <head>
        html = html.replace("</head>", "<style>%s</style>\n</head>" % UPLIFT_CSS, 1)

    # 2) enhanced trajectory chart (replace the flat placeholder svg)
    pairs = _parse_year_scores(html)
    if pairs and 'class="trajectory-svg"' in html:
        chart = build_trajectory_chart(pairs)
        if chart:
            html = re.sub(r'<svg viewBox="0 0 600 120" class="trajectory-svg">.*?</svg>',
                          lambda _m: chart, html, count=1, flags=re.S)

    # 3) section ids + reveal hooks (only where the anchor exists)
    present = set()

    def _mark(needle, repl, sid=None):
        nonlocal html
        if needle in html:
            html = html.replace(needle, repl, 1)
            if sid:
                present.add(sid)

    _mark('<div class="content">', '<div class="content" id="overview">', "overview")
    _mark('<div class="tl-exec-panel">', '<div class="tl-exec-panel reveal">')
    _mark('<div class="tl-audit-panel">', '<div class="tl-audit-panel reveal" id="validation">', "validation")
    _mark('<aside class="tl-sidebar">', '<aside class="tl-sidebar" id="snapshot">', "snapshot")
    if 'id="trajectory"' in html:
        present.add("trajectory")
    _mark('<div class="cal-section rmap-section">',
          '<div class="cal-section rmap-section reveal" id="roadmap">', "roadmap")
    _mark('<section class="fop-section">', '<section class="fop-section reveal" id="foreign">', "foreign")
    _mark('<div class="fop-condensed-section">', '<div class="fop-condensed-section reveal" id="foreign">', "foreign")
    _mark('<div class="insight-panel">', '<div class="insight-panel reveal" id="classical">', "classical")
    _mark('<details class="glossary-panel">', '<details class="glossary-panel reveal" id="glossary">', "glossary")
    _mark('<div class="glossary-panel">', '<div class="glossary-panel reveal" id="glossary">', "glossary")

    # reveal on remaining repeated blocks + the other insight panels
    html = html.replace('<div class="insight-panel">', '<div class="insight-panel reveal">')
    for cls in ("rmap-cmp-wrap", "rmap-year-block", "roadmap-year-card", "planet-panel", "d10-panel"):
        html = html.replace('<div class="%s">' % cls, '<div class="%s reveal">' % cls)
    html = html.replace('<div class="rmap-node ', '<div class="rmap-node reveal ')

    # 4) nav after <body>
    nav = app_nav_html(present, title=title, brand=brand)
    html = html.replace("<body>", "<body>\n" + nav, 1)

    # 5) close/repair + chrome + JS
    tail = back_to_top_html() + app_chrome_js()
    if re.search(r'</body>\s*</html>\s*$', html):
        html = re.sub(r'</body>\s*</html>\s*$', tail + "</body>\n</html>\n", html)
    else:  # truncated document — rebuild the closing
        html = html.rstrip()
        if html.endswith("Amala_Yoga_P"):
            html = html[:-2]
        html += _auto_close(html) + "\n" + tail + "</body>\n</html>\n"

    return html
