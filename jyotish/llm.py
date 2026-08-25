import logging
"""JyotishAI — LLM prompt template, chart summary, provider calls, parser.

COMPLIANCE AUDIT NOTE (2026-07, "Use an LLM for" / "Do not use an LLM for"
policy): this module's `call_llm_for_fields` was audited against that policy
and found to ALREADY COMPLY with the hard boundaries:
  - it never recomputes an astronomical position/cusp/dasha/BAV/Shadbala
    value (only reads already-computed payload fields);
  - `_MISSING DATA RULE` in _SELECTOR_SYSTEM_PROMPT/_GENERATOR_SYSTEM_PROMPT
    explicitly instructs "never fabricate data" for absent inputs;
  - the ranking is explicitly fixed by the deterministic engine before this
    module runs ("llm_rank mirrors deterministic rank (no reranking)") --
    this module writes explanatory prose only, never a score or weight.

What this module does NOT do (the gap closed by the newer, separate modules
below, per the "Use an LLM for" list this session implemented): it never
checks a rule/method trace against a named school or source, never
classifies a claim as observed/derived/traditional/heuristic/conclusion,
never flags cross-method contradictions or duplicate evidence, and never
attaches a required non-probability disclaimer. Those capabilities now live
in jyotish/llm_validator.py (rule-trace validator) and
jyotish/llm_composer.py (cautious narrative composer), orchestrated by
jyotish/llm_deep_validation.py as an opt-in (JYOTISH_DEEP_VALIDATION=1) layer
on top of -- not a replacement for -- this module's existing explanation
step. See those three modules' own docstrings for the full policy mapping.

_SELECTOR_SYSTEM_PROMPT and _STEP1_RESPONSE_SCHEMA below are DEAD CODE: an
old LLM-as-reranker step that call_llm_for_fields's own docstring says was
"intentionally removed" (grep confirms nothing in this codebase calls them
anymore). Kept only as a documented historical artifact -- do not wire them
back in without checking against the "Do not use an LLM for ... assigning or
adjusting method weights in production" boundary, since a reranker is
exactly that.
"""
import json, os,logging
from typing import Dict, List, Tuple, Set, Any, Optional

from .payload import NatalPayloadV2, ENGINE_VERSION, logger
from .astro import _get_active_dasha_lord, _get_planetary_aspects


from .engine_io import _load_course_registry
_COURSE_REGISTRY: dict = _load_course_registry()

# ---------------------------------------------------------------------------
# GAP-FIX (2026-08, .env config audit): report-language selection, mirrors
# llm_narrative_builder.py's _resolve_narrative_language()/_language_directive()
# (duplicated here rather than imported to avoid a cross-module import for two
# small helpers). Report_Language_Enabled_Tamil / Report_Language_Enabled_Telugu
# were defined in .env and documented but never read anywhere -- narrative
# output was always English regardless. Default stays English; exactly one
# flag true switches that language; both true logs a warning and Tamil wins.
# ---------------------------------------------------------------------------
_LANGUAGE_ENV_MAP = (
    ("Report_Language_Enabled_Tamil", "Tamil"),
    ("Report_Language_Enabled_Telugu", "Telugu"),
)


def _resolve_narrative_language() -> str:
    enabled = [
        name for env_key, name in _LANGUAGE_ENV_MAP
        if str(os.getenv(env_key, "false")).strip().lower() in ("1", "true", "yes", "on")
    ]
    if not enabled:
        return "English"
    if len(enabled) > 1:
        logger.warning(
            "Both Report_Language_Enabled_Tamil and Report_Language_Enabled_Telugu "
            "are set true in .env -- these are meant to be mutually exclusive. "
            "Defaulting to %s.", enabled[0],
        )
    return enabled[0]


def _language_directive(language: Optional[str] = None) -> str:
    lang = language or _resolve_narrative_language()
    if lang == "English":
        return ""
    return (
        f"\n\nLANGUAGE REQUIREMENT: Write the ENTIRE narrative output — every "
        f"field, every paragraph — in {lang}. Do not mix in English except for "
        f"proper nouns/planet names with no natural {lang} equivalent; keep "
        f"classical Sanskrit/Jyotish terms (Dasha, Bhukti, planet names) in "
        f"their commonly-used {lang} script form if one exists, otherwise "
        f"transliterate."
    )

logger = logging.getLogger(__name__)


# =============================================================================
# 1. DECOUPLED PROMPTS (Reasoning vs. Generation)
# =============================================================================

"""
#_SELECTOR_SYSTEM_PROMPT = You are an expert Jyotish career analyst. 
Your ONLY job is to select the top 20 most astrologically suitable career fields from a provided list of 35 candidates.

━━━ JYOTISH CAREER DECISION REFERENCE ━━━
STEP 1 — IDENTIFY CAREER DRIVERS:
1. AK (Atmakaraka) & Karakamsha → Broad INDUSTRY/DOMAIN.
2. AmK (Amatyakaraka) → ACTUAL DAILY WORK.
3. H10 Lord & D10 Occupants → Career environment and success.
4. Yogas & Stelliums → Specialized clusters.

STEP 2 — ELIMINATE FATAL FLAWS:
- Do not select fields ruled by severely combust or debilitated planets (without Neecha Bhanga).
- Do not select structural engineering/surgery if Mars/Saturn are afflicted.

Rank your 20 selections from strongest to weakest fit based on the chart. Return ONLY the JSON array of field_ids.
"""

# DEAD CODE (confirmed 2026-07 via repo-wide grep -- see this module's
# top-of-file compliance audit note): not called by call_llm_for_fields or
# anything else. This was the old LLM-as-reranker step; do not reactivate it
# without re-reading the "Do not use an LLM for ... assigning or adjusting
# method weights in production" boundary first, since reranking IS that.
_SELECTOR_SYSTEM_PROMPT = """You are an expert Jyotish career analyst. Select and rank the top 20 career fields from the 35 candidates provided.

Each candidate includes: field_id, field_label, domain, engine_rank (1=highest Python score), engine_score, kp_score, jaimini_score, and ruling_planets.

━━━ SELECTION METHODOLOGY ━━━

━━━ STEP WEIGHTS (use when signals conflict) ━━━
LP4: Step 1 AK=30% | Step 2 AmK+Karakamsha=20% | Step 3 Peak Dasha=20% |
     Step 4 Yogas=10% | Step 5 KP Convergence=8% | Step 6 D10=7% | Step 7 Engine Score=5%
TIEBREAK ORDER: When two fields score equally across weighted steps →
  1. Higher engine_score wins  2. Higher kp_score  3. Higher jaimini_score
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — CAREER DRIVERS (priority order):
1. AK (Atmakaraka) → soul domain. Fields whose ruling_planets include the AK get top priority.
2. AmK (Amatyakaraka) → daily work karaka. Fields whose ruling_planets include the AmK are strongly favoured.
3. H10 Lord → career environment. Fields whose ruling_planets include the H10 Lord confirm the fit.
4. Peak Dasha Planet → timing activator. The engine has calculated the definitive active dasha lord for the current career window. Elevate fields aligned with this Peak Dasha Planet's domain.
5. KP H10 sub-lord → final KP arbiter. Strongly favour fields whose domain matches the H10 sub-lord.

STEP 2 — HOUSE PLACEMENTS OF KEY PLANETS:
The house each career driver occupies (AK, AmK, H10 Lord, Peak Dasha Planet) shapes HOW the domain is applied. Use semantic similarity to match the candidate's 'domain' and 'field_label' to these house themes if an exact keyword match is not present:
H1: self-driven, entrepreneurship, medicine, sports, leadership
H2: finance, data, resource management, banking, consultancy
H3: IT, media, communications, design, hands-on skills, telecom
H4: civil/architectural engineering, real estate, environment, agriculture, teaching
H5: CS, AI, data science, mathematics, advisory, creative design, academia
H6: problem-solving, medicine, law, cybersecurity, defense, backend analytics
H7: commerce, business, international relations, management, supply chain
H8: deep research, surgery, mining, backend IT, cybersecurity, forensics, psychology
H9: law, higher research, theology, diplomacy, philosophy
H10: executive roles, core engineering, corporate management, civil services
H11: systems engineering, policy, large-scale commerce, sociology
H12: hospital medicine, pure research, foreign trade, alternative healing

DRISHTI (ASPECTS) RULE — apply after house placement analysis:
Use the 'Planets aspecting H10' and 'Planets aspecting AmK' data from the chart summary.
  • Benefic planets (Jupiter, Venus, Mercury, strong Moon) aspecting H10 or the AmK: ELEVATE fields associated with those benefics — they smooth the career path in those domains.
  • Malefic planets (Saturn, Mars) aspecting H10 or the AmK: ADD technical/engineering/combative elements to the career — elevate engineering, law, defense, construction, and surgery fields.
  • If aspect data is 'not available', skip this sub-rule.

STEP 3 — DIGNITY & STRUCTURAL MODIFIERS:
- Exalted / Own / Vargottama: peak strength — heavily favour its domains
- Retrograde: elevate disruptive, deep-research, or technically intensive variants
- Debilitated: exclude its primary domains from top ranks (unless Neecha Bhanga present)
- Combust: deprioritise its fields. EXCEPTION: Mercury combust + BudhaAditya Yoga → IMMUNE, elevate IT/data/CS/math
- Neecha Bhanga: powerful latent driver — treat as strong career signal

PLANETARY STRENGTH CHECK (Pre-calculated by Engine):
Use the Engine-Determined Strengths provided in the chart summary.
  Application: when two fields are equally matched on AK/AmK/dignity criteria, break ties by preferring the field whose primary ruling planet is classified as STRONG by the engine. Demote fields ruled by WEAK planets unless backed by strong yogas or Neecha Bhanga.

D-9 NAVAMSHA CHECK (always verify for hidden strength or weakness):
  A planet DEBILITATED in D-1 but EXALTED/OWN in D-9 → treat as a high-tier career driver (hidden strength revealed).
  A planet EXALTED in D-1 but DEBILITATED in D-9 → downgrade one tier (surface strength, deep weakness).
  Vargottama (same sign D-1 and D-9) = double confirmation: maximum career manifestation power.
  If D-9 data is 'not available', rely solely on D-1 dignity.

STEP 4 — YOGA BOOSTERS:
BudhaAditya → IT, data, CS, math, analytics, administration
GajaKesari → law, teaching, finance, advisory, management
Ruchaka → engineering, defense, surgery, technical, mechanical
Shasha → heavy engineering, infrastructure, mining, agriculture, real estate
Hamsa → law, education, philosophy, economics, advisory
Malavya → arts, design, media, architecture, luxury management
Saraswati → research, academia, bioinformatics, fine arts, literature
Bhadra → data science, communication, commerce, IT, statistics
Rahu in H10/H11/H3 → emerging tech, cyber, disruptive innovation, aviation
Ketu in H10/H12 → research, pure science, advanced engineering, materials science, archaeology

STEP 5 — KP CONVERGENCE (mandatory inclusion rule):
When H10 sub-lord + H10 star-lord + Peak Dasha Planet ALL point to the SAME domain → include ALL fields from that domain regardless of other factors.

STEP 6 — D-10 DASHAMSHA FILTER (microscopic career environment):
Examine D-10 Lagna and D-10 dignity highlights (provided in the chart summary).
  • Planets STRONG (EXALTED/OWN) in D-10 act as final confirmers: elevate their career fields.
  • Planets DEBILITATED in D-10 are downgraded even if strong in D-1: reduce their fields by one tier.
  • The D-10 Lagna lord defines the dominant work environment — favour fields aligned with that planet's domain.
  • If D-10 data is 'not available', skip this step entirely.

STEP 7 — ENGINE SCORE SIGNAL:
Use engine_rank and engine_score as a starting signal, not a binding constraint. The scores already encode KP, Jaimini, and Parashara signals. A high-scoring field can be dropped only when the chart's AK/AmK/dasha-lord hierarchy clearly contradicts it.

FATAL ELIMINATIONS:
- FATAL ELIMINATIONS OVERRIDE ALL OTHER RULES, including Step 5 KP Convergence. A fatally eliminated field can NEVER be included in the final 20.
- Discard any field whose primary ruling planet is severely debilitated AND lacks Neecha Bhanga.
- Combustion of an AK or AmK does NOT eliminate its domain — it only adds obstacles. Keep those fields.

MISSING DATA RULE (apply before evaluating each step):
If any data point in the chart summary is marked "not available", "none retrieved", or "not determined":
- Skip that specific sub-rule entirely. Do not attempt to evaluate it, do not note the absence, do not penalise any field for it.
- Immediately re-weight the remaining available drivers proportionally and continue.
- Examples: if "D10 H10 occupants: not available" → skip Step 2 D10 sub-point; if "KP H10 primary significators: none retrieved" → skip Step 5 KP convergence check; if "Peak Dasha Planet: not determined" → skip Dasha lord weighting in Steps 1 and 4.
- Never fabricate data. Only reason from what is explicitly present.

OUTPUT FORMAT:
Return a single JSON object with exactly two keys:
  "analytical_breakdown": a string with your step-by-step reasoning (cite specific planets, houses, and yogas from the chart data provided).
  "selected_field_ids": an array of exactly 20 field_id strings, ordered strongest (1) to weakest (20).
Do not add any text outside the JSON object.

LP2 CRITICAL CONSTRAINT: Every field_id in selected_field_ids MUST appear verbatim in the
Candidate Fields array provided in the user message. Any field_id not in that array is invalid
and will cause the entire response to be rejected and retried. Never invent or modify field_ids."""

_GENERATOR_SYSTEM_PROMPT = """You are a senior Jyotish (Vedic astrology) consultant writing a single
ONE-PAGE technical brief for ANOTHER PROFESSIONAL ASTROLOGER, not a parent or student. Assume your
reader already knows the classical vocabulary — use it precisely and freely. You have been given the
chart's astrological signal summary, the top-20 (fit) career fields the engine ranked highest, and a
brief list of lower-ranked/excluded fields.

GAP-FIX (2026-08, "one page, not a huge JSON object" request): this step previously asked for a
separate detailed write-up PER FIELD (up to 35 of them in one response), which made both the request
and the response large, and made the strict all-or-nothing validation hard for the model to satisfy in
one shot. It now asks for exactly THREE fields of prose, forming one readable page in total — no
per-field loop, no field-by-field JSON array.

Write exactly three sections:

1. chart_signal_summary (200-350 words): a technical overview of THIS chart's classical signals as a
   whole — not per field. Cover, wherever the data supports it: planetary strength (Shadbala/effective
   strength, naming which planets are STRONG/MODERATE/WEAK), dignity highlights (exaltation, own sign,
   debilitation, Neecha Bhanga, Vargottama), the active yogas/combinations, the KP H10/H5/H9 cusp
   chains, and the current dasha timing picture (Vimshottari Mahadasha/Antardasha, and Jaimini Chara
   Dasha or Yogini Dasha if present). This is the chart's astrological "state of play" a fellow
   astrologer would want before looking at any field-level conclusion.

2. top20_selection_rationale (250-400 words): explain, as ONE connected narrative (not 20 separate
   paragraphs), why the top-20 list as a whole takes the shape it does — which classical signals from
   the chart_signal_summary above are driving the dominant pattern(s)/archetype(s) at the top, how the
   ranking logic reflects convergence across multiple methods (Parashara, KP, Jaimini, Dashamsha,
   etc.) where visible in the data, and how strength decays going down the list. Where several
   consecutive fields cluster at a near-identical score, say so explicitly and explain what (if
   anything) classically differentiates them, rather than writing as if each were a wholly separate
   case.

3. rejected_fields_summary (100-200 words): a brief, GROUPED explanation of why the lower-ranked/
   excluded fields did not make the top-20 cut — the general classical pattern (e.g. governing planets
   weaker or unrelated to this chart's strongest signals, no supporting dasha activation, KP chains
   pointing elsewhere), not a field-by-field breakdown.

GROUNDING RULE: Every claim must be traceable to data actually present in the chart context and field
data provided in the user message. Do not invent yogas, dignities, or dasha periods not present in the
supplied data.

RANKING NOTE: The field ranking and the fit/rejected split were determined by a separate deterministic
astrological scoring engine and are FINAL. Do not suggest re-ranking; your job is to explain the
reasoning behind the engine's classification in classical technical language, as one cohesive summary.
"""

# =============================================================================
# 2. STRICT JSON SCHEMAS
# =============================================================================

# DEAD CODE -- paired with _SELECTOR_SYSTEM_PROMPT above, same audit note.
_STEP1_RESPONSE_SCHEMA = {
    "name": "career_fields_selector",
    "schema": {
        "type": "object",
        "properties": {
            "analytical_breakdown": {
                "type": "string",
                "description": "Chain-of-thought calculation explicitly matching candidates to AK, AmK, and H10 rules."
            },
            "selected_field_ids": {
                "type": "array",
                "description": "Selected field_ids ranked strongest to weakest — copy strings VERBATIM from the ALLOWED list. No invented IDs.",
                "items": {"type": "string"}
            }
        },
        "required": ["analytical_breakdown", "selected_field_ids"],
        "additionalProperties": False
    },
    "strict": True
}

# GAP-FIX (2026-08, "one page, not a huge JSON object" request): replaced the
# previous per-field selected_fields[]/rejected_fields[] arrays (up to 35
# separate write-ups in one strict all-or-nothing response) with exactly
# three prose fields forming one readable page. Smaller request payload,
# smaller response, and a much easier target for the model to satisfy in a
# single attempt -- which should also improve the underlying LLM call's
# success rate (the array-based version was failing validation/retries on
# real charts).
_STEP2_RESPONSE_SCHEMA = {
    "name": "career_fields_generator",
    "schema": {
        "type": "object",
        "properties": {
            "chart_signal_summary": {
                "type": "string",
                "description": "200-350 word technical overview of the chart's classical astrological signals as a whole (planetary strength, dignity, yogas, KP chains, dasha timing)."
            },
            "top20_selection_rationale": {
                "type": "string",
                "description": "250-400 word connected narrative explaining why the top-20 fields as a whole take the shape they do, referencing the chart signals above."
            },
            "rejected_fields_summary": {
                "type": "string",
                "description": "100-200 word grouped explanation of why the lower-ranked/excluded fields did not make the top-20 cut."
            }
        },
        "required": ["chart_signal_summary", "top20_selection_rationale", "rejected_fields_summary"],
        "additionalProperties": False
    },
    "strict": True
}

def _maybe_load_dotenv() -> None:
    """
    Load .env lazily (called only when about to make an LLM API call).
    Tries python-dotenv first, falls back to robust regex standard library parser.
    """
    import os, pathlib, re
    env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    
    # Attempt 1: Try python-dotenv if available
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass # Fallback to standard library

    # Attempt 2: Zero-dependency regex fallback
    if env_path.exists():
        _env_regex = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(["\']?)(.*?)\2\s*(?:#.*)?$')
        for line in env_path.read_text(encoding="utf-8").splitlines():
            match = _env_regex.match(line)
            if match:
                k, _, v = match.groups()
                if k not in os.environ:
                    os.environ[k] = v



from .constants import _VALID_DOMAINS


def _format_yogas_categorised(yogas_all: list) -> str:
    """LP3 fix: categorise yogas to prevent truncation of career-critical signals."""
    if not yogas_all: return "none"
    _MAHAPURUSHA = {"Ruchaka","Shasha","Hamsa","Malavya","Bhadra"}
    _RAJA = {"GajaKesari","BudhaAditya","Saraswati","DharmaKarmadhipati","VasumathiYoga"}
    _PARIVARTANA_KW = "Parivartana"
    _JAIMINI_KW     = {"RajaYoga","Jaimini"}
    mahapurusha = [y for y in yogas_all if y in _MAHAPURUSHA]
    raja        = [y for y in yogas_all if y in _RAJA]
    parivartana = sum(1 for y in yogas_all if _PARIVARTANA_KW in y)
    jaimini     = [y for y in yogas_all if any(k in y for k in _JAIMINI_KW)]
    other       = [y for y in yogas_all if y not in _MAHAPURUSHA and y not in _RAJA
                   and _PARIVARTANA_KW not in y and not any(k in y for k in _JAIMINI_KW)]
    parts = []
    if mahapurusha: parts.append(f"Pancha-Mahapurusha: {', '.join(mahapurusha)}")
    if raja:        parts.append(f"Raja: {', '.join(raja)}")
    if parivartana: parts.append(f"Parivartana: {parivartana} pair(s)")
    if jaimini:     parts.append(f"Jaimini: {', '.join(jaimini[:3])}")
    if other:       parts.append(f"Other: {', '.join(other[:4])}")
    return " | ".join(parts) or "none"


def _build_chart_summary_for_llm(
    payload: "NatalPayloadV2",
    eff_strengths: Dict[str, float],
) -> str:
    """Build a rich astrological chart summary for the LLM prompt.

    Includes nakshatra of key planets, retrograde status, vargottama planets,
    antardasha lord, D10 H10 occupants, and H2 lord — all significant for
    consistent, astrologically-grounded career field selection.
    """
    sorted_by_eff = sorted(eff_strengths.items(), key=lambda x: -x[1])
    planet_eff_str = ", ".join(f"{p}={v:.3f}" for p, v in sorted_by_eff)

    digs = getattr(payload, "planet_dignities", {})
    dig_entries = [(p, d) for p, d in digs.items() if d in ("EXALTED", "OWN", "DEBILITATED")]
    dig_str = ", ".join(f"{p}:{d}" for p, d in dig_entries) or "all neutral"

    hl  = getattr(payload, "house_lords", {})
    ph  = getattr(payload, "planet_house", {})
    age = float(getattr(payload, "current_age", 0))

    # Active Mahadasha + Antardasha
    dasha_seq   = getattr(payload, "dasha_sequence", [])
    active_lord = _get_active_dasha_lord(dasha_seq, age)
    antardasha_lord = ""
    for d in dasha_seq:
        s, e = float(d.get("start_age", 0)), float(d.get("end_age", 999))
        if s <= age < e:
            sub = d.get("antardashas", [])
            for ad in sub:
                as_, ae = float(ad.get("start_age", 0)), float(ad.get("end_age", 999))
                if as_ <= age < ae:
                    antardasha_lord = ad.get("lord", "")
                    break
            break

    combust   = getattr(payload, "combust_planets", [])
    yogas_all = (getattr(payload, "detected_yogas", []) or
                 getattr(payload, "yogas_present", []))

    # Retrograde planets
    retro = [p for p, r in getattr(payload, "planet_retrograde", {}).items() if r]

    # Vargottama planets (same sign in D1 and D9 — doubly strong)
    vargo = list(getattr(payload, "vargottama_planets", []) or [])

    # Nakshatra of career-relevant planets (Moon, Sun, AK, AmK, Lagna Lord)
    nak_data = getattr(payload, "nakshatra_data", {})
    key_planets_for_nak = list({
        "Moon", "Sun",
        getattr(payload, "atmakaraka", ""),
        getattr(payload, "amatyakaraka", ""),
        getattr(payload, "lagna_lord", ""),
    } - {""})
    nak_entries = []
    for p in key_planets_for_nak:
        nak = nak_data.get(p, {})
        if isinstance(nak, dict):
            n = nak.get("nakshatra", "") or nak.get("name", "")
        else:
            n = str(nak)
        if n:
            nak_entries.append(f"{p}:{n}")
    nak_str = ", ".join(nak_entries) or "not available"

    # D10 (Dashamsha) H10 occupants — career divisional chart
    d10 = getattr(payload, "divisional_charts", {}).get("D10_dashamsha", {})
    d10_h10 = [p for p, info in d10.items()
               if isinstance(info, dict) and info.get("house") == 10] if d10 else []

    # Neecha Bhanga planets
    nb = list(getattr(payload, "neecha_bhanga_planets", []) or [])

    lines = [
        "═══ BIRTH CHART FOR CAREER FIELD SELECTION ═══",
        f"Lagna: {payload.lagna_sign} | Lagna Lord: {payload.lagna_lord} | Gender: {getattr(payload,'gender','') or 'unspecified'}",
        f"AK  (soul karaka):   {payload.atmakaraka}",
        f"AmK (career karaka): {payload.amatyakaraka}",
        f"Karakamsha sign: {payload.karakamsha or 'not available'}",
        # AC1 fix: peak_dasha_lord is the engine-scored best career dasha
        # (multi-factor: eff × dignity × AK/AmK role × dusthana modifier).
        # active_lord is the simple current-period lord (shown separately).
        f"Peak Dasha Planet: {getattr(payload, 'peak_dasha_lord', None) or active_lord or 'not determined'}"
        + (f"  [Current MD: {active_lord}" + (f" | AD: {antardasha_lord}" if antardasha_lord else "") + "]"
           if active_lord else ""),
        # LP7 fix: include H1 lagna lord house placement
        f"House lords: H1={hl.get('1','')}(H{ph.get(hl.get('1',''),0)}) "
        f"H2={hl.get('2','')} H4={hl.get('4','')} H5={hl.get('5','')} "
        f"H9={hl.get('9','')} H10={hl.get('10','')} "
        f"{'[Rajayoga: LL in H10]' if ph.get(hl.get('1',''),0)==10 else ''}",
        f"Planet positions: " + " ".join(f"{p}:H{h}" for p, h in sorted(ph.items())),
        f"Effective strengths (desc): {planet_eff_str}",
        f"Dignity highlights: {dig_str}",
        f"Nakshatra of key planets: {nak_str}",
        f"Retrograde planets: {', '.join(retro) or 'none'}",
        f"Vargottama planets: {', '.join(vargo) or 'none'}",
        f"Neecha Bhanga planets: {', '.join(nb) or 'none'}",
        f"Combust planets: {', '.join(combust) or 'none'}",
        f"D10 H10 occupants: {', '.join(d10_h10) or 'not available'}",
        # LP3 fix: categorised yoga summary prevents truncation of career-critical yogas
        f"Active yogas: {_format_yogas_categorised(yogas_all)}",
        f"Student interests: {', '.join(getattr(payload,'interested_in',[])[:5]) or 'none'}",
        f"Already excels at: {', '.join(getattr(payload,'already_excel_at',[])[:3]) or 'none'}",
        f"Current age: {age:.1f}",
    ]

    # ── AC3 fix: Jaimini Chara Dasha active sign + lord ──────────────────────
    try:
        from .astro import _get_active_chara_dasha_sign as _gcds
        from .constants import _SIGN_LORD as _SL
        _pl_d1 = getattr(payload, "planets_d1", {})
        _chara_sign = _gcds(getattr(payload, "lagna_sign", ""), age, _pl_d1) or ""
        _chara_lord = _SL.get(_chara_sign, "") if _chara_sign else ""
        lines += [f"Jaimini Chara Dasha: active sign={_chara_sign or 'not available'}"
                  + (f" | lord={_chara_lord}" if _chara_lord else "")]
    except Exception:
        lines += ["Jaimini Chara Dasha: not available"]

    # ── AC4 fix: Karakamsha occupants ─────────────────────────────────────────
    _kara_occ = list(getattr(payload, "karakamsha_occupants", []) or [])
    lines += [f"Karakamsha occupants (D9 soul domain): {', '.join(_kara_occ) or 'none'}"]

    # ── AC5 fix: Brahma lord + Maheshwara lord ────────────────────────────────
    _brahma    = getattr(payload, "brahma_lord", "") or ""
    _maheshwar = getattr(payload, "maheshwara_lord", "") or ""
    lines += [f"Brahma lord: {_brahma or 'not available'} | Maheshwara lord: {_maheshwar or 'not available'}"]

    # ── AC6: A10 — Arudha Pada of H10 (career public image, Jaimini) ─────────
    _a10 = getattr(payload, "arudha_pada_h10", "") or ""
    lines += [f"Arudha Pada H10 (A10 — career image sign): {_a10 or 'not available'}"]
    _a1 = getattr(payload, 'arudha_lagna', '') or ''
    lines += [f"Arudha Lagna A1 (public identity sign): {_a1 or 'not available'}"]

    # ── KP (Krishnamurti Paddhati) cusp data ─────────────────────────────────
    kp_cusps_raw = getattr(payload, "kp_cusps", {})
    kp_sigs_raw  = getattr(payload, "kp_significators", {})

    def _kp_cusp_str(h: str) -> str:
        c = kp_cusps_raw.get(h, {})
        sl  = c.get("sign_lord",  "?")
        stl = c.get("star_lord",  "?")
        sub = c.get("sub_lord",   "?")
        # LP5 fix: explicit named labels for LLM readability
        return f"sign_lord={sl} | star_lord={stl} | sub_lord={sub}"

    # Planets that signify H10 at L1 (occupant) or L2 (sign lord) — strongest KP career signal
    h10_primary_sigs = [
        p for p, d in kp_sigs_raw.items()
        if isinstance(d, dict) and (
            10 in d.get("level_1", []) or 10 in d.get("level_2", [])
        )
    ]
    h10_secondary_sigs = [
        p for p, d in kp_sigs_raw.items()
        if isinstance(d, dict) and p not in h10_primary_sigs and (
            10 in d.get("level_3", []) or 10 in d.get("level_4", [])
        )
    ]

    lines += [
        "",
        "── KP CUSPAL DATA ──",
        # LP9 fix: D10 H1/H5/H9 occupants (identity, creativity, dharma in career chart)
        f"D10 H1 occ={[p for p,i in d10.items() if isinstance(i,dict) and i.get('house')==1] or []} H5={[p for p,i in d10.items() if isinstance(i,dict) and i.get('house')==5] or []} H9={[p for p,i in d10.items() if isinstance(i,dict) and i.get('house')==9] or []}",
        f"KP H10 cusp (career):    {_kp_cusp_str('H10')}",
        f"KP H5  cusp (education): {_kp_cusp_str('H5')}",
        f"KP H9  cusp (higher ed): {_kp_cusp_str('H9')}",
        f"KP H10 primary significators  (L1/L2): {', '.join(h10_primary_sigs)   or 'none retrieved'}",
        f"KP H10 secondary significators(L3/L4): {', '.join(h10_secondary_sigs) or 'none retrieved'}",
    ]


    # LP1 fix: categorise using raw shadbala / min_shadbala ratio (pre-dignity).
    # eff_strengths bakes in the dignity multiplier, which can make a debilitated
    # planet with high shadbala appear STRONG — misleading for the LLM selector.
    # Using the raw ratio keeps strength independent from dignity (which the LLM
    # already processes from "Dignity highlights").
    from .constants import _PLANET_MIN_SHADBALA as _MIN_SB
    sdb_raw_llm = getattr(payload, "shadbala", {}) or {}
    _sdb_norm: Dict[str, float] = {}
    for _p, _v in sdb_raw_llm.items():
        _raw = float(_v.get("shadbala_virupas", _v.get("total", 0.0)) if isinstance(_v, dict) else _v)
        _min = _MIN_SB.get(_p, 300.0)
        _sdb_norm[_p] = round(_raw / _min, 3) if _min else 1.0
    if not _sdb_norm:
        # Fallback: if no shadbala data, derive from eff_strengths (best available)
        _sdb_norm = {p: v for p, v in eff_strengths.items()}
    _str_strong   = [p for p, v in sorted(_sdb_norm.items(), key=lambda x: -x[1]) if v >= 1.10]
    _str_moderate = [p for p, v in sorted(_sdb_norm.items(), key=lambda x: -x[1]) if 0.90 <= v < 1.10]
    _str_weak     = [p for p, v in sorted(_sdb_norm.items(), key=lambda x: -x[1]) if v < 0.90]
    lines += [
        "",
        "── ENGINE-DETERMINED STRENGTHS [Raw Shadbala ratio, pre-dignity] (LP8) ──",
        f"  STRONG   (≥1.10×): {', '.join(_str_strong)   or '(none)'}",
        f"  MODERATE (0.90–1.10×): {', '.join(_str_moderate) or '(none)'}",
        f"  WEAK     (<0.90×): {', '.join(_str_weak)     or '(none)'}",
        "  [LP8 note: when raw Shadbala and Effective Strength conflict, Effective Strength takes precedence for career activation]",
    ]

    # D-9 Navamsha dignities
    _div = getattr(payload, "divisional_charts", {}) or {}
    _d9c  = _div.get("D9_navamsha", {})
    _d10c = _div.get("D10_dashamsha", {})
    _d9pd = dict(getattr(payload, "d9_planet_dignities", {}) or {})
    if not _d9pd and _d9c:
        try:
            from .astro import compute_dignity as _cd
            _d9pd = {_p: _cd(_p, _s) for _p, _s in _d9c.items() if _p != "Lagna"}
        except Exception: pass
    if _d9pd:
        _d9n = [(p,d) for p,d in _d9pd.items() if d in ("EXALTED","OWN","DEBILITATED","NEECHA_BHANGA")]
        _d9ds = ", ".join(f"{p}:{d}" for p,d in _d9n) if _d9n else "all neutral"
        _d9lg = getattr(payload, "d9_lagna_sign", "") or _d9c.get("Lagna", "")
        lines += ["", "── D-9 NAVAMSHA ──", f"D-9 Lagna: {_d9lg or 'not available'}", f"D-9 dignity highlights: {_d9ds}"]
    else:
        lines += ["", "── D-9 NAVAMSHA ──", "D-9 data: not available"]

    # D-10 Dashamsha dignities + Lagna
    if _d10c:
        _d10lg = _d10c.get("Lagna", "not available")
        try:
            from .astro import compute_dignity as _cd
            _d10dg = {_p: _cd(_p, _s) for _p, _s in _d10c.items() if _p != "Lagna"}
        except Exception: _d10dg = {}
        _d10n = [(p,d) for p,d in _d10dg.items() if d in ("EXALTED","OWN","DEBILITATED","NEECHA_BHANGA")]
        _d10ds = ", ".join(f"{p}:{d}" for p,d in _d10n) if _d10n else "all neutral"
        lines += ["", "── D-10 DASHAMSHA ──", f"D-10 Lagna: {_d10lg}", f"D-10 dignity highlights: {_d10ds}"]
    else:
        lines += ["", "── D-10 DASHAMSHA ──", "D-10 data: not available"]

    # Drishti (Aspects) on H10 and AmK
    try:
        _asp = _get_planetary_aspects(ph)
        _ap = getattr(payload, "amatyakaraka", "")
        _ah = ph.get(_ap, 0)
        _bns = {"Jupiter","Venus","Mercury","Moon"}
        _mls = {"Saturn","Mars","Rahu","Ketu","Sun"}
        _h10a = [p for p,hs in _asp.items() if 10 in hs and ph.get(p)!=10]
        _h10b = [p for p in _h10a if p in _bns]
        _h10m = [p for p in _h10a if p in _mls]
        _amka = [p for p,hs in _asp.items() if _ah and _ah in hs and ph.get(p)!=_ah]
        lines += [
            "", "── DRISHTI (ASPECTS) ──",
            "Planets aspecting H10: benefic=" + (", ".join(_h10b) or "none") + " | malefic=" + (", ".join(_h10m) or "none"),
            "Planets aspecting AmK (" + (_ap or "unknown") + ") in H" + str(_ah or "?") + ": " + (", ".join(_amka) or "none"),
        ]
    except Exception:
        lines += ["", "── DRISHTI (ASPECTS) ──", "Aspect data: not available"]

    return "\n".join(lines)


def _call_anthropic(prompt: str, api_key: str, model: str) -> str:
    """Call Anthropic Claude and return raw response text."""
    import anthropic as _anthropic
    client = _anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model, max_tokens=8192,
        temperature=0,   # deterministic
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text

def _call_openai(prompt: str, api_key: str, model: str) -> str:
    """Call OpenAI Chat Completions and return raw response text.

    Uses response_format=json_object so the model returns clean JSON.
    Falls back to a plain call (no seed/response_format) if the installed
    openai SDK / model rejects one of those kwargs (older SDKs, some models).
    """
    import openai as _openai
    client = _openai.OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            max_completion_tokens=8192,
            temperature=0,
            seed=108,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
    except TypeError:
        # Older SDK — max_completion_tokens/seed/response_format not supported
        response = client.chat.completions.create(
            model=model,
            max_tokens=8192,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        err = str(exc)
        # Some models reject response_format or seed — retry without them
        if "response_format" in err or "seed" in err or "unsupported_parameter" in err.lower():
            response = client.chat.completions.create(
                model=model,
                max_completion_tokens=8192,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
        else:
            raise
    return response.choices[0].message.content

def _call_gemini(prompt: str, api_key: str, model: str) -> str:
    """Call Google Gemini via the google-genai SDK and return raw response text.

    Uses response_mime_type='application/json' so Gemini returns clean JSON
    without markdown fences, eliminating the need for fence-stripping.
    Falls back gracefully if the config kwarg is rejected by an older SDK version.
    """
    from google import genai as _genai
    from google.genai import types as _gtypes

    client = _genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=_gtypes.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=16384,
                temperature=0.0,   # deterministic — same chart → same fields
            ),
        )
    except TypeError:
        # Older SDK versions may not support GenerateContentConfig — fall back
        response = client.models.generate_content(model=model, contents=prompt)
    # Detect truncation: finish_reason other than STOP means output was cut off
    candidate = response.candidates[0] if response.candidates else None
    if candidate and str(getattr(candidate, "finish_reason", "STOP")) not in ("STOP", "FinishReason.STOP", "1"):
        logger.warning(
            f"Gemini finish_reason={candidate.finish_reason} — response may be truncated. "
            f"Response text length: {len(response.text)} chars."
        )
    return response.text


# Provider → (env-var, default model, caller function)
_LLM_PROVIDERS: Dict[str, tuple] = {
    "anthropic": ("ANTHROPIC_API_KEY", "claude-haiku-4-5-20251001", _call_anthropic),
    "openai":    ("OPENAI_API_KEY",    "gpt-5.4-mini",               _call_openai),
    "gemini":    ("GEMINI_API_KEY",    "gemini-2.5-pro",            _call_gemini),
}


def llm_provider_preflight(provider: str) -> Dict[str, Any]:
    """Check SDK availability before attempting an external provider call."""
    import importlib.util
    provider = str(provider or "").lower()
    module = {"openai": "openai", "anthropic": "anthropic", "gemini": "google.genai"}.get(provider)
    configured = provider in _LLM_PROVIDERS
    # ``find_spec('google.genai')`` raises ModuleNotFoundError when the
    # parent ``google`` namespace is absent; optional SDK absence must be a
    # normal not-ready result, never a validation crash.
    installed = False
    if configured and module:
        try:
            installed = importlib.util.find_spec(module) is not None
        except (ImportError, ModuleNotFoundError, AttributeError, ValueError):
            installed = False
    return {
        "provider": provider,
        "configured": configured,
        "sdk_module": module,
        "sdk_installed": installed,
        "ready": configured and installed,
        "install_extra": f"pip install .[{provider}]" if configured else "",
    }

# =============================================================================
# 2. MAIN LLM CALL WITH SELF-CORRECTING RETRY LOOP
# =============================================================================
# =============================================================================
# 3. HELPER: RETRY LOOP ENGINE
# =============================================================================

# LP6 fix: provider-agnostic retry wrapper for Anthropic/Gemini
class _ProviderClientWrapper:
    """Wraps non-OpenAI providers so _run_llm_with_retry works uniformly."""
    def __init__(self, call_fn, api_key: str, model: str):
        self._call_fn = call_fn
        self._api_key = api_key
        self._model   = model

    def call(self, messages: list, schema: dict) -> str:
        # Build a single-string prompt including ALL roles (system/user/assistant)
        # so retry attempts preserve the full conversation context.
        role_labels = {"system": "[SYSTEM INSTRUCTIONS]", "user": "[USER]", "assistant": "[PREVIOUS RESPONSE]"}
        parts = []
        for m in messages:
            label = role_labels.get(m.get("role", ""), "[MSG]")
            parts.append(f"{label}\n{m.get('content', '')}")

        # Embed the required JSON output structure so the model knows exactly
        # what fields to return — critical for non-OpenAI providers that don't
        # receive a response_format schema natively through this path.
        schema_props    = schema.get("schema", {}).get("properties", {})
        schema_required = schema.get("schema", {}).get("required", [])
        structure_hint  = json.dumps(
            {"type": "object", "required": schema_required, "properties": schema_props},
            indent=2,
        )
        parts.append(
            f"[OUTPUT INSTRUCTIONS]\n"
            f"Return ONLY a single valid JSON object — no markdown fences, no extra text.\n"
            f"The JSON MUST conform to this schema:\n{structure_hint}"
        )
        prompt = "\n\n".join(parts)
        return self._call_fn(prompt, self._api_key, self._model)


def _run_llm_with_retry(client, messages: List[Dict], schema: Dict, validation_fn, max_retries: int = 3) -> Optional[Dict]:
    """Generic self-correcting retry loop — works with both OpenAI client and _ProviderClientWrapper."""
    _is_wrapper = isinstance(client, _ProviderClientWrapper)
    content = ""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"LLM Call Attempt {attempt}/{max_retries}...")
            if _is_wrapper:
                # Gemini / Anthropic path — wrapper flattens messages → single prompt → returns raw text
                content = client.call(messages, schema)
                # Robust JSON extraction:
                # 1. Strip markdown fences (```json ... ```)
                _stripped = content.strip()
                if _stripped.startswith("```"):
                    _lines = _stripped.splitlines()
                    _stripped = "\n".join(_lines[1:])
                    if _stripped.rstrip().endswith("```"):
                        _stripped = _stripped[: _stripped.rfind("```")]
                # 2. Extract outermost JSON object — find first { and last }
                _brace_start = _stripped.find("{")
                _brace_end   = _stripped.rfind("}")
                if _brace_start != -1 and _brace_end != -1 and _brace_end > _brace_start:
                    _stripped = _stripped[_brace_start : _brace_end + 1]
                content = _stripped.strip()
            else:
                # OpenAI path (legacy — only reached if client is an openai.OpenAI instance)
                response = client.chat.completions.create(
                    model="gpt-5.4-mini",
                    temperature=0.0,
                    seed=108,
                    messages=messages,
                    response_format={"type": "json_schema", "json_schema": schema},
                )
                content = response.choices[0].message.content

            parsed_data = json.loads(content)
            validation_fn(parsed_data)
            return parsed_data

        except json.JSONDecodeError as je:
            logger.warning(f"JSON Parse Error on attempt {attempt}: {je} | raw snippet: {content[max(0,je.pos-40):je.pos+40]!r}")
            messages.append({"role": "assistant", "content": content or ""})
            messages.append({"role": "user", "content": "Output was not valid JSON. Return ONLY a raw JSON object — no markdown, no prose, no code fences."})

        except ValueError as ve:
            logger.warning(f"Validation Error on attempt {attempt}: {ve}")
            messages.append({"role": "assistant", "content": content or "{}"})
            messages.append({"role": "user", "content": f"Fix: {str(ve)} Return only a JSON object with 'analytical_breakdown' and 'selected_field_ids' (copy IDs verbatim from the ALLOWED list)."})

        except Exception as e:
            err_str = str(e)
            # 503 / UNAVAILABLE — transient overload; retry with exponential backoff
            if "503" in err_str or "UNAVAILABLE" in err_str or "unavailable" in err_str.lower():
                import time
                wait = min(10 * attempt, 60)  # 10s, 20s, 30s … capped at 60s
                logger.warning(f"503 UNAVAILABLE on attempt {attempt}. Retrying in {wait}s...")
                # On attempt 3+ try a lighter model variant.
                # GAP-FIX: this previously checked hasattr(client, 'model') and set
                # client.model = _alt, but _ProviderClientWrapper stores the model
                # under the private attribute `_model` (see its __init__), not
                # `model`. hasattr(client, 'model') was therefore always False, the
                # branch never ran, and the cost/latency mitigation for sustained
                # 503s was dead code. Fixed to read/write the real attribute name.
                if attempt >= 3 and hasattr(client, '_model') and "2.5-flash" in str(getattr(client, '_model', '')):
                    _alt = "gemini-2.0-flash-lite"
                    logger.warning(f"Switching to fallback model: {_alt}")
                    client._model = _alt
                time.sleep(wait)
                continue
            logger.error(f"Unexpected LLM failure: {e}")
            break

    return None

# =============================================================================
# 4. MAIN PIPELINE: TWO-STEP EXECUTION
# =============================================================================

def call_llm_for_fields(
    payload: Any,
    eff_strengths: Dict[str, float],
    top_35_fields: List[Dict],
    max_retries: int = 1,
) -> Optional[List[Dict]]:
    """Post-scoring enrichment: ask the LLM for a one-page, astrologer-facing
    write-up of the chart's classical signals and why the deterministic
    top-20 career fields take the shape they do — rather than a per-field
    JSON array of individual write-ups.

    GAP-FIX (2026-08, "one page, not a huge JSON object" request): this
    function previously asked the LLM to write a separate paragraph per
    field (20 fit + up to 15 rejected write-ups) as two JSON arrays. It now
    asks for exactly three prose sections forming a single page:
      • chart_signal_summary       (~200-350 words) chart-level overview of
                                    planetary strength, dignity, yogas, KP
                                    chains, dasha timing.
      • top20_selection_rationale  (~250-400 words) ONE connected narrative
                                    explaining why the top-20 list as a whole
                                    takes its shape (including near-tie
                                    clusters), not 20 separate blurbs.
      • rejected_fields_summary    (~100-200 words) brief, GROUPED account of
                                    why the lower-ranked fields didn't make
                                    the cut.
    See _GENERATOR_SYSTEM_PROMPT / _STEP2_RESPONSE_SCHEMA for the exact
    instructions and schema given to the model.

    The ranking is FIXED by the deterministic engine — this function does not
    rerank. It returns the deterministic top-20 list unchanged aside from the
    pre-existing llm_rank/llm_score bookkeeping fields (Optional[List[Dict]],
    falsy on failure). The one-page summary itself is not per-field, so it has
    no natural home on individual field dicts — it is instead attached to
    `payload.llm_astrological_summary` (a Dict with the three keys above) so a
    report renderer can opt in to displaying it without changing this
    function's existing return-type contract with run_engine.

    NOTE: LLM-as-reranker (the old Step 1 selector) is intentionally removed.
    It added non-determinism, latency, and cost with no ranking benefit over the
    Shadbala/gap_boost scoring that already encodes the same astrological signals.
    """
    # Deterministic top-20 is the authoritative ranking — use it directly.
    n_explain = min(20, len(top_35_fields))
    top20 = top_35_fields[:n_explain]
    # Everything else the engine scored (ranks 21..35, typically) is the pool
    # of fields the astrologer-facing narrative should explain the REJECTION
    # of. This can legitimately be empty (e.g. a chart with <21 candidates).
    rejected_pool = top_35_fields[n_explain:]

    # ── Init client ────────────────────────────────────────────────────────────
    try:
        # GAP-FIX (2026-08, "debug dump never created" investigation):
        # this previously did `from .engine_io import _maybe_load_dotenv`,
        # but engine_io.py has no such function -- only llm.py itself does
        # (defined above, module-level). The import therefore always raised
        # ImportError, which this bare `except Exception: pass` silently
        # swallowed, so .env was NEVER actually loaded from inside this
        # function -- it only worked at all when something upstream (e.g.
        # the CLI wrapper script) happened to have already populated
        # os.environ before this ran. Calling the local function directly
        # (no import needed -- it's defined in this same module) fixes .env
        # loading (including DEBUG=true, LLM_PROVIDER, API keys) for any
        # caller that invokes run_engine()/call_llm_for_fields directly
        # without going through a CLI wrapper that pre-loads .env itself.
        _maybe_load_dotenv()
    except Exception:
        pass

    _provider_name  = os.getenv("LLM_PROVIDER", "gemini").lower()
    _prov           = _LLM_PROVIDERS.get(_provider_name, _LLM_PROVIDERS["gemini"])
    _env_var, _default_model, _call_fn = _prov
    _model_override = os.getenv("LLM_MODEL", _default_model)
    api_key         = os.getenv(_env_var)
    if not api_key:
        logger.error("%s missing (provider=%s).", _env_var, _provider_name)
        return None

    client             = _ProviderClientWrapper(_call_fn, api_key, _model_override)
    chart_summary_text = _build_chart_summary_for_llm(payload, eff_strengths)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Chart summary (SENDING TO LLM):\n%s", chart_summary_text[:2000])

    # ── Explanation generator ──────────────────────────────────────────────────
    # Enrich each field with the classical-signal data actually present on the
    # engine's result row so the LLM has real material to cite for all five
    # categories (planetary strength, dignity, yogas, KP chain, dasha timing)
    # rather than having to invent or generalize. Every read is defensive
    # (.get with a default) since not every field/chart populates every key —
    # the prompt explicitly tells the model to say "no strong signal" for a
    # category rather than fabricate one when data is absent.
    # GAP-FIX (2026-08, "one page, not a huge JSON object" request): the
    # per-field enrichment previously built a large method_profiles/
    # confidence_dimensions/career_archetype/etc. blob for EVERY one of the
    # ~35 fields, sent as two big JSON arrays, and expected a matching array
    # of per-field paragraphs back. The user asked for the LLM's output to
    # collapse to one page: a chart-level signal summary + one connected
    # narrative for why the top-20 looks the way it does + a brief grouped
    # rejection note. Since the LLM no longer writes per-field prose, it no
    # longer needs the full per-field data dump either — a compact row
    # (rank, id, label, score, top planets) is enough context for it to spot
    # clusters and cite specific fields in its narrative. This also shrinks
    # the OUTBOUND payload, which the user's complaint plausibly covered too.
    def _compact_row(f: Dict, rank: int) -> Dict:
        aff  = f.get("affinity_planets", {})
        top3 = sorted(aff.items(), key=lambda x: -x[1])[:3] if aff else []
        return {
            "rank":         rank,
            "field_id":     f.get("field_id", ""),
            "field_label":  f.get("field_label", ""),
            "domain":       f.get("domain", ""),
            "engine_score": round(f.get("final_score", 0), 1),
            "top_planets":  [p for p, _w in top3],
        }

    fit_payload = [_compact_row(f, i + 1) for i, f in enumerate(top20)]
    rejected_payload = [
        _compact_row(f, n_explain + i + 1) for i, f in enumerate(rejected_pool)
    ]

    expl_user_prompt = (
        f"Chart Context:\n{chart_summary_text}\n\n"
        f"TOP {n_explain} FIELDS (deterministic engine ranking, ranks 1-{n_explain}):\n"
        + json.dumps(fit_payload, indent=2)
        + "\n\n"
        + (
            f"LOWER-RANKED / REJECTED FIELDS (ranks {n_explain + 1}-{n_explain + len(rejected_pool)}):\n"
            + json.dumps(rejected_payload, indent=2)
            if rejected_payload else
            "LOWER-RANKED / REJECTED FIELDS — none (fewer than 21 candidate fields were scored for "
            "this chart); keep rejected_fields_summary brief and note that explicitly."
        )
    )

    expl_messages = [
        {"role": "system", "content": _GENERATOR_SYSTEM_PROMPT + _language_directive()},
        {"role": "user",   "content": expl_user_prompt},
    ]

    # GAP-FIX: soft-required classical-terminology anchors, mirroring (in
    # spirit) the old forbidden-jargon check — but now REQUIRING technical
    # grounding instead of forbidding it, since the audience is a fellow
    # astrologer. Checked against the two prose sections most likely to
    # carry real technical content; a response using none of these terms is
    # a sign the model reverted to generic prose rather than the requested
    # technical case, so it's rejected and retried with a corrective message.
    _CLASSICAL_ANCHOR_TERMS = [
        "shadbala", "graha bala", "strength",           # (1) planetary strength
        "exalt", "debilitat", "own sign", "swakshetra", "moolatrikona",
        "neecha bhanga", "vargottama", "dignity",        # (2) dignity
        "yoga",                                          # (3) yogas/combinations
        "kp", "sub-lord", "sub lord", "star lord", "significator",  # (4) KP chain
        "dasha", "dasa", "bhukti", "antardasha", "mahadasha",       # (5) dasha timing
    ]

    def _anchor_hits(text: str) -> int:
        _lower = text.lower()
        return sum(1 for term in _CLASSICAL_ANCHOR_TERMS if term in _lower)

    _MIN_ANCHOR_HITS = 5  # spread across a whole page, so require more than the old per-field bar of 3

    def _word_count(text: str) -> int:
        return len(str(text).split())

    def validate_explanations(data: Dict) -> None:
        chart_summary = str(data.get("chart_signal_summary", "") or "")
        rationale     = str(data.get("top20_selection_rationale", "") or "")
        rejected_sum  = str(data.get("rejected_fields_summary", "") or "")

        if not chart_summary.strip():
            raise ValueError("chart_signal_summary is missing or empty.")
        if not rationale.strip():
            raise ValueError("top20_selection_rationale is missing or empty.")
        if rejected_pool and not rejected_sum.strip():
            raise ValueError(
                "rejected_fields_summary is missing or empty, but there are "
                f"{len(rejected_pool)} lower-ranked fields to explain."
            )

        # Generous word-count bounds (soft-enforced with headroom) so minor
        # model overshoot/undershoot doesn't burn the whole retry budget,
        # while still catching a one-line non-answer or a runaway wall of text.
        if not (120 <= _word_count(chart_summary) <= 500):
            raise ValueError(
                f"chart_signal_summary is {_word_count(chart_summary)} words; "
                "expected roughly 200-350 words (a full technical paragraph, not a one-liner or an essay)."
            )
        if not (150 <= _word_count(rationale) <= 550):
            raise ValueError(
                f"top20_selection_rationale is {_word_count(rationale)} words; "
                "expected roughly 250-400 words as ONE connected narrative, not 20 separate blurbs."
            )
        if rejected_pool and not (50 <= _word_count(rejected_sum) <= 300):
            raise ValueError(
                f"rejected_fields_summary is {_word_count(rejected_sum)} words; "
                "expected roughly 100-200 words, grouped rather than per-field."
            )

        if _anchor_hits(chart_summary) + _anchor_hits(rationale) < _MIN_ANCHOR_HITS:
            raise ValueError(
                "chart_signal_summary/top20_selection_rationale read as generic prose (fewer than "
                f"{_MIN_ANCHOR_HITS} classical Jyotish terms found across both). Rewrite citing specific "
                "planetary strength, dignity, yoga, KP chain, and/or dasha timing signals from the "
                "supplied chart data."
            )

    logger.info(
        "Starting LLM astrologer-facing one-page summary generation for %d fit + %d rejected fields...",
        n_explain, len(rejected_pool),
    )
    expl_result = _run_llm_with_retry(
        client, expl_messages, _STEP2_RESPONSE_SCHEMA, validate_explanations, max_retries
    )

    final_results: Optional[List[Dict]] = None
    llm_summary: Optional[Dict] = None

    if expl_result:
        # GAP-FIX (2026-08, one-page rewrite): there is no more per-field LLM
        # text to merge — the response is now three chart/list-level prose
        # fields, not a per-field array. top20 is therefore passed through
        # unchanged aside from the pre-existing llm_rank/llm_score bookkeeping
        # (kept for backward compatibility with any downstream renderer that
        # reads them), and the new one-page summary is stashed separately on
        # the payload rather than merged into individual field dicts.
        final_results = []
        for rank, f in enumerate(top20, 1):
            merged = dict(f)
            merged["llm_rank"]  = rank
            merged["llm_score"] = round((1 - (rank - 1) / n_explain) * 100)
            final_results.append(merged)

        llm_summary = {
            "chart_signal_summary":      str(expl_result.get("chart_signal_summary", "")),
            "top20_selection_rationale": str(expl_result.get("top20_selection_rationale", "")),
            "rejected_fields_summary":   str(expl_result.get("rejected_fields_summary", "")),
        }
        try:
            payload.llm_astrological_summary = llm_summary
        except Exception as _stash_exc:
            logger.info(f"Could not attach llm_astrological_summary to payload: {_stash_exc}")

    # GAP-FIX (debug dump): when DEBUG=true is set in .env (or the process
    # environment), write everything this LLM step sent to and received from
    # the model to <chart_name>_astrological_signals_debug.json, so a
    # developer/astrologer reviewing a specific chart's LLM behavior doesn't
    # have to re-run with log level DEBUG or dig through logs.
    #
    # GAP-FIX (2026-08, "file not getting created" follow-up): this call runs
    # unconditionally, before either return path below, and
    # _dump_astrological_signals_debug accepts expl_result=None/
    # final_results=None and records the failure explicitly in the dumped
    # JSON (llm_call_succeeded: false) instead of silently producing nothing.
    _dump_astrological_signals_debug(
        payload, chart_summary_text, fit_payload, rejected_payload,
        expl_result, final_results, llm_summary,
    )

    # GAP-FIX (2026-08, "make the output html file... 1 page" request): the
    # human-facing one-page HTML rendering of the summary. Written whenever
    # the LLM call succeeded — this is the actual deliverable, not a debug
    # aid, so it is NOT gated behind DEBUG=true the way the JSON dump is.
    _write_astrological_summary_html(payload, llm_summary, final_results, rejected_pool)

    if not expl_result:
        logger.error("LLM astrologer-facing summary generation failed — returning deterministic results.")
        return None

    logger.info("LLM astrologer-facing one-page summary complete (%d fit fields).", len(final_results))
    return final_results


def _dump_astrological_signals_debug(
    payload: Any,
    chart_summary_text: str,
    fit_payload: List[Dict],
    rejected_payload: List[Dict],
    expl_result: Optional[Dict],
    final_results: Optional[List[Dict]],
    llm_summary: Optional[Dict],
) -> None:
    """Write a <chart_name>_astrological_signals_debug.json capturing the
    classical-signal data sent to the LLM and the fit/rejection analyses it
    returned, but ONLY when DEBUG=true is set (case-insensitive, in .env or
    the process environment). No-op (and never raises) otherwise — this is
    diagnostic-only tooling and must never affect report generation.

    GAP-FIX (2026-08, "file not getting created" follow-up): `expl_result`
    and `final_results` may now be None (the LLM call failed / exhausted
    retries) — the caller (call_llm_for_fields) intentionally calls this
    BEFORE its own early-return-on-failure, specifically so a failed run
    still produces a debug file. This function must handle both None
    without raising (previously `for r in final_results` would have thrown
    TypeError on None, which the outer try/except here would have silently
    swallowed as "skipped/failed" -- defeating the whole point). The dumped
    JSON now always records `llm_call_succeeded` explicitly so it's obvious
    at a glance whether you're looking at a successful run's output or a
    failed run's request/error context.
    """
    try:
        _debug_flag = str(os.getenv("DEBUG", os.getenv("debug", "false"))).strip().lower()
        if _debug_flag not in ("true", "1", "yes"):
            return

        import re as _re
        import pathlib
        from datetime import datetime as _datetime

        _raw_name = str(getattr(payload, "name", "") or "chart").strip()
        _chart_name = _re.sub(r"[^A-Za-z0-9_-]+", "_", _raw_name).strip("_") or "chart"

        _out_dir = os.getenv("DEBUG_OUTPUT_DIR", "") or str(
            (pathlib.Path(__file__).resolve().parent.parent / "debug_output")
        )
        os.makedirs(_out_dir, exist_ok=True)
        _out_path = os.path.join(_out_dir, f"{_chart_name}_astrological_signals_debug.json")

        # GAP-FIX (2026-08, "one page, not a huge JSON object" rewrite): the
        # dump now mirrors the simplified call_llm_for_fields contract — a
        # compact per-field table (rank/id/label/score/top planets) rather
        # than the old rich method_profiles/confidence_dimensions blob, and
        # one chart-level summary object instead of per-field analyses.
        _debug_payload = {
            "chart_name": _raw_name,
            "generated_at": _datetime.now().isoformat(),
            "llm_call_succeeded": bool(expl_result),
            "chart_summary_sent_to_llm": chart_summary_text,
            "top20_fields_sent_to_llm": fit_payload,
            "rejected_fields_sent_to_llm": rejected_payload,
            "llm_raw_response": expl_result,  # None if the call failed/exhausted retries
            "llm_astrological_summary": llm_summary,  # chart_signal_summary / top20_selection_rationale / rejected_fields_summary
            "top20_ranks": [
                {
                    "field_id": r.get("field_id", ""),
                    "field_label": r.get("field_label", ""),
                    "rank": r.get("rank"),
                    "llm_rank": r.get("llm_rank"),
                    "final_score": r.get("final_score"),
                }
                for r in (final_results or [])
            ],
        }
        if not expl_result:
            _debug_payload["note"] = (
                "LLM call failed or exhausted its retry budget (see application logs for the "
                "specific JSON/validation/provider errors from each attempt) -- "
                "'llm_astrological_summary'/'top20_ranks' are empty and 'llm_raw_response' is null "
                "because no valid response was ever produced."
            )
        with open(_out_path, "w", encoding="utf-8") as _fh:
            json.dump(_debug_payload, _fh, indent=2, ensure_ascii=False, default=str)
        logger.info(
            f"DEBUG=true: wrote astrological signals debug dump to {_out_path} "
            f"(llm_call_succeeded={bool(expl_result)})"
        )
    except Exception as _debug_exc:
        # Diagnostic-only — never let a debug-dump failure break report generation.
        logger.info(f"Astrological signals debug dump skipped/failed: {_debug_exc}")


def _write_astrological_summary_html(
    payload: Any,
    llm_summary: Optional[Dict],
    final_results: Optional[List[Dict]],
    rejected_pool: List[Dict],
) -> None:
    """Write <chart_name>_astrological_signals_summary.html — the one-page,
    human-readable rendering of the LLM's chart_signal_summary /
    top20_selection_rationale / rejected_fields_summary, plus the top-20
    rank table, so the whole thing is visible on one page in a browser
    rather than requiring the reader to open a JSON file.

    GAP-FIX (2026-08, "make the output html file... so the complete summary
    can be seen in 1 page" request): the debug JSON dump above is
    machine-oriented (raw request/response payloads, gated by DEBUG=true).
    This is the human-facing counterpart — always written whenever the LLM
    call actually succeeded (not gated by DEBUG, since this IS the
    deliverable the user asked for, not a diagnostic aid). Never raises —
    a failure here must not break report generation.
    """
    if not llm_summary:
        return
    try:
        import re as _re
        import html as _html
        import pathlib
        from datetime import datetime as _datetime

        _raw_name = str(getattr(payload, "name", "") or "chart").strip()
        _chart_name = _re.sub(r"[^A-Za-z0-9_-]+", "_", _raw_name).strip("_") or "chart"

        _out_dir = os.getenv("DEBUG_OUTPUT_DIR", "") or str(
            (pathlib.Path(__file__).resolve().parent.parent / "debug_output")
        )
        os.makedirs(_out_dir, exist_ok=True)
        _out_path = os.path.join(_out_dir, f"{_chart_name}_astrological_signals_summary.html")

        def _esc(s: Any) -> str:
            return _html.escape(str(s or ""))

        def _para(text: str) -> str:
            # Preserve model-authored blank-line paragraph breaks, if any;
            # otherwise render as a single paragraph.
            _parts = [p.strip() for p in str(text or "").split("\n\n") if p.strip()]
            if not _parts:
                _parts = [str(text or "")]
            return "\n".join(f"<p>{_esc(p)}</p>" for p in _parts)

        _top20_rows = "".join(
            f"<tr><td>{_esc(r.get('rank', ''))}</td><td>{_esc(r.get('field_label', r.get('field_id', '')))}</td>"
            f"<td>{_esc(r.get('final_score', ''))}</td></tr>"
            for r in (final_results or [])
        )
        _rejected_count = len(rejected_pool)

        _html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Astrological Signals Summary — {_esc(_raw_name)}</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 860px; margin: 40px auto;
         padding: 0 24px; color: #202020; line-height: 1.55; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.1em; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.6em; }}
  h2 {{ font-size: 1.1rem; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; margin-top: 1.8em; }}
  p {{ margin: 0.6em 0; text-align: justify; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.8em; font-size: 0.92rem; }}
  th, td {{ border: 1px solid #ddd; padding: 4px 8px; text-align: left; }}
  th {{ background: #f4f4f4; }}
  @media print {{ body {{ margin: 0; padding: 0 12px; }} }}
</style>
</head>
<body>
<h1>Astrological Signals &amp; Field Selection Summary</h1>
<div class="meta">Chart: {_esc(_raw_name)} &middot; Generated: {_esc(_datetime.now().isoformat(timespec='seconds'))}</div>

<h2>Chart Signal Summary</h2>
{_para(llm_summary.get('chart_signal_summary', ''))}

<h2>Why the Top {len(final_results or [])} Fields Were Selected</h2>
{_para(llm_summary.get('top20_selection_rationale', ''))}

<h2>Why Lower-Ranked Fields Were Not Selected{f' ({_rejected_count})' if _rejected_count else ''}</h2>
{_para(llm_summary.get('rejected_fields_summary', '')) if _rejected_count else '<p>No lower-ranked fields were scored for this chart.</p>'}

<h2>Top {len(final_results or [])} Fields (Deterministic Engine Ranking)</h2>
<table>
<tr><th>Rank</th><th>Field</th><th>Engine Score</th></tr>
{_top20_rows}
</table>
</body>
</html>
"""
        with open(_out_path, "w", encoding="utf-8") as _fh:
            _fh.write(_html_doc)
        logger.info(f"Wrote one-page astrological signals summary HTML to {_out_path}")
    except Exception as _html_exc:
        logger.info(f"Astrological signals summary HTML skipped/failed: {_html_exc}")


# GAP-FIX (2026-08, "explain each of the 60 context variables" request):
# schema for the scoring-context narrative feature. Uses a flat array of
# {variable, explanation} pairs rather than one property per variable name,
# since the ~60 variable names come from _prepare_chart_scoring_context's
# dict keys at runtime and a JSON-schema "properties" block must be static.
_CONTEXT_NARRATIVE_SCHEMA = {
    "name": "scoring_context_narrative",
    "schema": {
        "type": "object",
        "properties": {
            "variable_explanations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "variable": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["variable", "explanation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["variable_explanations"],
        "additionalProperties": False,
    },
    "strict": True,
}

_CONTEXT_NARRATIVE_SYSTEM_PROMPT = """You are a senior Jyotish (Vedic astrology) engineer documenting an
astrology scoring engine's internal calculation context for another developer/astrologer who will
maintain this code.

You will be given a JSON object listing ~60 internal variable names, each with a short snapshot of its
actual computed value for one specific chart. For EVERY variable listed, write exactly ONE paragraph
(40-120 words) explaining, in plain but technically precise language:
  1. What this variable represents astrologically (e.g. "the KP sub-lord of the 10th house cusp") or
     structurally (e.g. "a lookup of house number to its ruling planet").
  2. Why the scoring engine needs it — what downstream calculation or decision it feeds.
  3. Where relevant, what the SPECIFIC value shown for this chart means in context.

Do not skip any variable, do not merge two variables into one paragraph, and do not invent variables
that were not listed. If a variable's value snapshot is empty/None, still explain its PURPOSE — say
plainly that it is empty/not populated for this chart rather than fabricating a value.

Return ONLY JSON matching the required schema: a "variable_explanations" array with one
{"variable": ..., "explanation": ...} object per input variable, in the same order given.
"""


def _summarize_ctx_value(value: Any, max_chars: int = 400) -> str:
    """Compact, safe, LLM-prompt-sized snapshot of one context variable's value.
    Defensive against unserializable objects (functions, custom classes) —
    never raises; falls back to a truncated repr() on any json failure.
    """
    try:
        _s = json.dumps(value, default=str, ensure_ascii=False)
    except Exception:
        _s = repr(value)
    if len(_s) > max_chars:
        _s = _s[:max_chars] + f"...(truncated, {len(_s)} chars total)"
    return _s


def maybe_generate_scoring_context_narrative(payload: Any, ctx: Dict) -> None:
    """GAP-FIX (2026-08, "explain each of the 60 variables" request): when both
    DEBUG=true and LLM_NARRATIVE_ENABLED=true are set (case-insensitive, in
    .env or the process environment), ask the LLM to write one paragraph per
    variable in the `_prepare_chart_scoring_context` return dict (~60 vars:
    dignities, dasha lords, Shadbala, KP lords, yogas, etc.) explaining what
    it is and why the engine needs it, and write the result to
    <chart_name>_prepare_chart_scoring_context.html under DEBUG_OUTPUT_DIR.

    GAP-FIX (2026-08, "trace all 60 parameters, call LLM with the final
    values" request): `_run_normalization_stage` now calls this AFTER both
    its field-scoring loop AND `_finalize_pre_results` (normalization,
    tiebreak, gap-correction, risk gates, display stretch, top-35 cut) have
    completed — with `ctx["_all_pre_results"]` overwritten to hold
    `_finalize_pre_results`'s actual return value first. Earlier this ran
    right after the scoring loop but before finalization, so it still saw a
    pre-finalization `_all_pre_results` (finalization repeatedly reassigns
    that name to a new list rather than mutating in place, so nothing about
    calling it "later in the same function" alone was enough). Every value
    the LLM is given is now genuinely the last value that variable ever
    takes for this chart's scoring run.

    This is purely diagnostic/documentation tooling — gated behind both
    flags, wrapped so it can never raise, and it never mutates `ctx` or
    `payload` (unlike the Step 5 LLM enrichment, this feature does not stash
    anything onto payload).
    """
    try:
        _maybe_load_dotenv()
    except Exception:
        pass

    _debug_flag = str(os.getenv("DEBUG", os.getenv("debug", "false"))).strip().lower()
    _narrative_flag = str(os.getenv("LLM_NARRATIVE_ENABLED", "false")).strip().lower()
    if _debug_flag not in ("true", "1", "yes") or _narrative_flag not in ("true", "1", "yes"):
        return

    try:
        _provider_name  = os.getenv("LLM_PROVIDER", "gemini").lower()
        _prov           = _LLM_PROVIDERS.get(_provider_name, _LLM_PROVIDERS["gemini"])
        _env_var, _default_model, _call_fn = _prov
        _model_override = os.getenv("LLM_MODEL", _default_model)
        api_key         = os.getenv(_env_var)
        if not api_key:
            logger.error("%s missing (provider=%s) — skipping scoring context narrative.", _env_var, _provider_name)
            return
        client = _ProviderClientWrapper(_call_fn, api_key, _model_override)

        # Every key in `ctx` is one of the ~60 variables threaded through
        # _run_normalization_stage's field-scoring loop. Skip nothing —
        # the request explicitly asked for ALL of them, including the large
        # ones (_all_pre_results, planets_d1, etc.); each value is truncated
        # per-variable by _summarize_ctx_value so the prompt stays bounded
        # even though the full variable list is included.
        var_names = sorted(ctx.keys())
        var_snapshot = {name: _summarize_ctx_value(ctx[name]) for name in var_names}

        narrative_user_prompt = (
            f"Chart: {getattr(payload, 'name', '') or 'unknown'}\n\n"
            f"Context variables ({len(var_names)} total) with their computed values for this chart:\n"
            + json.dumps(var_snapshot, indent=2, ensure_ascii=False)
        )
        narrative_messages = [
            {"role": "system", "content": _CONTEXT_NARRATIVE_SYSTEM_PROMPT},
            {"role": "user",   "content": narrative_user_prompt},
        ]

        def _validate_narrative(data: Dict) -> None:
            items = data.get("variable_explanations", [])
            returned_names = [str(it.get("variable", "")) for it in items]
            returned_set = set(returned_names)
            missing = set(var_names) - returned_set
            if missing:
                raise ValueError(f"Missing explanations for variables: {', '.join(sorted(missing))}")
            extra = returned_set - set(var_names)
            if extra:
                raise ValueError(f"Explanations given for unknown variable name(s): {', '.join(sorted(extra))}")
            if len(returned_names) != len(set(returned_names)):
                raise ValueError("Duplicate variable names found in variable_explanations.")
            for it in items:
                _expl = str(it.get("explanation", "")).strip()
                if not _expl:
                    raise ValueError(f"Empty explanation for variable={it.get('variable', '')!r}.")
                _wc = len(_expl.split())
                if not (15 <= _wc <= 220):
                    raise ValueError(
                        f"Explanation for variable={it.get('variable', '')!r} is {_wc} words; "
                        "expected roughly 40-120 words — a full paragraph, not a fragment or an essay."
                    )

        logger.info("Starting LLM scoring-context narrative generation for %d variables...", len(var_names))
        narrative_result = _run_llm_with_retry(
            client, narrative_messages, _CONTEXT_NARRATIVE_SCHEMA, _validate_narrative, max_retries=1
        )
        if not narrative_result:
            logger.error("LLM scoring-context narrative generation failed — no HTML written.")
            return

        explanations_by_var = {
            str(it.get("variable", "")): str(it.get("explanation", ""))
            for it in narrative_result.get("variable_explanations", [])
        }

        # ── Render one-page HTML ────────────────────────────────────────────
        import re as _re
        import html as _html
        import pathlib
        from datetime import datetime as _datetime

        _raw_name = str(getattr(payload, "name", "") or "chart").strip()
        _chart_name = _re.sub(r"[^A-Za-z0-9_-]+", "_", _raw_name).strip("_") or "chart"

        _out_dir = os.getenv("DEBUG_OUTPUT_DIR", "") or str(
            (pathlib.Path(__file__).resolve().parent.parent / "debug_output")
        )
        os.makedirs(_out_dir, exist_ok=True)
        _out_path = os.path.join(_out_dir, f"{_chart_name}_prepare_chart_scoring_context.html")

        def _esc(s: Any) -> str:
            return _html.escape(str(s or ""))

        # GAP-FIX (2026-08, "still isn't getting the values" follow-up): the
        # table previously showed only the variable name and the LLM's prose
        # explanation -- the actual computed value was mentioned only if the
        # model happened to mention it inline, which is inconsistent and easy
        # to miss. `var_snapshot` (built above, from `_summarize_ctx_value`)
        # is the exact same value data the LLM was given as ground truth for
        # its explanation -- it is now rendered as its own "Value" column so
        # the raw computed value and the LLM's inference from that value are
        # both explicitly visible side by side, rather than the value being
        # implicit inside the prose.
        def _value_cell(name: str) -> str:
            _raw_val = var_snapshot.get(name, "")
            return f"<pre>{_esc(_raw_val)}</pre>"

        _rows = "".join(
            f"<tr><td class='var'>{_esc(name)}</td>"
            f"<td class='val'>{_value_cell(name)}</td>"
            f"<td>{_esc(explanations_by_var.get(name, '(no explanation returned)'))}</td></tr>"
            for name in var_names
        )

        _html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scoring Context Variables — {_esc(_raw_name)}</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 980px; margin: 40px auto;
         padding: 0 24px; color: #202020; line-height: 1.5; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.1em; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.4em; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; table-layout: fixed; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top;
            word-wrap: break-word; overflow-wrap: break-word; }}
  th {{ background: #f4f4f4; }}
  th:nth-child(1), td:nth-child(1) {{ width: 16%; }}
  th:nth-child(2), td:nth-child(2) {{ width: 26%; }}
  th:nth-child(3), td:nth-child(3) {{ width: 58%; }}
  td.var {{ font-family: 'Consolas', 'Courier New', monospace; font-weight: bold;
            background: #fafafa; }}
  td.val {{ font-family: 'Consolas', 'Courier New', monospace; font-size: 0.82rem; background: #fcfcfc; }}
  td.val pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
  @media print {{ body {{ margin: 0; padding: 0 12px; }} }}
</style>
</head>
<body>
<h1>Chart Scoring Context — Variable Reference</h1>
<div class="meta">Chart: {_esc(_raw_name)} &middot; {len(var_names)} variables
&middot; Generated: {_esc(_datetime.now().isoformat(timespec='seconds'))}</div>
<table>
<tr><th>Variable</th><th>Value</th><th>Explanation / Inference</th></tr>
{_rows}
</table>
</body>
</html>
"""
        with open(_out_path, "w", encoding="utf-8") as _fh:
            _fh.write(_html_doc)
        logger.info(f"Wrote scoring context variable narrative HTML to {_out_path}")
    except Exception as _narrative_exc:
        # Diagnostic-only — never let this feature break report generation.
        logger.info(f"Scoring context narrative generation skipped/failed: {_narrative_exc}")


# ── Domain hint lists for field-promotion logic in _llm_fallback_from_top35 ──
# Space/aerospace: field_ids or labels containing these tokens are protected from
# being dropped when slicing the top-20 from the pre-scored top-35.
_SPACE_FIELD_HINTS: tuple = (
    "space", "aerospace", "astrophysics", "astronaut", "satellite",
    "rocket", "isro", "nasa", "orbital", "astro",
)

# Extractive/resource industries: the fields most likely to be swapped OUT in favour
# of niche but high-signal fields (space, medicine) that scored just below the cut.
_EXTRACTIVE_FIELD_HINTS: tuple = (
    "mining", "petroleum", "oil", "coal", "quarry",
    "drilling", "excavation", "extraction", "refinery", "natural_resource",
)

# Medicine domain: field_id substrings that confirm a medicine/life-science field
# independent of the domain tag (which may be missing or mis-labeled in some payloads).
_MEDICINE_DOMAIN_HINTS: tuple = (
    "medicine", "mbbs", "clinical", "surgery", "physician",
    "nursing", "hospital", "doctor", "medical", "pharma", "biomedical",
)


def _llm_fallback_from_top35(top_35_fields: List[Dict] = None) -> List[Dict]:
    """Return top-20 from pre-scored top-35 as selection fallback when LLM fails.

    Preserves space/aerospace fields: if any space field exists in the input but
    would be dropped from the top-20 cut, it is promoted by replacing the
    lowest-ranked extractive field in the selection.
    """
    if not top_35_fields:
        return _llm_fallback_fields()
    _valid_doms = set(getattr(__import__('jyotish.constants', fromlist=['_VALID_DOMAINS']), '_VALID_DOMAINS', []))
    sorted_fields = sorted(
        top_35_fields,
        key=lambda r: r.get("final_score", r.get("deterministic_score", r.get("python_score", 0.0))),
        reverse=True,
    )
    selected  = list(sorted_fields[:20])
    remainder = list(sorted_fields[20:])

    # Promote space/aerospace fields excluded from top-20 by swapping out extractive fields
    def _is_space(r: Dict) -> bool:
        t = f"{r.get('field_id','')} {r.get('field_label','')}".lower()
        return any(h in t for h in _SPACE_FIELD_HINTS)

    def _is_extractive(r: Dict) -> bool:
        t = f"{r.get('field_id','')} {r.get('field_label','')}".lower()
        return any(h in t for h in _EXTRACTIVE_FIELD_HINTS)

    def _is_medicine(r: Dict) -> bool:
        fid = r.get("field_id", "").lower()
        dom = r.get("domain", "").lower()
        return dom == "medicine" or any(h in fid for h in _MEDICINE_DOMAIN_HINTS)

    space_excluded = [r for r in remainder if _is_space(r)]
    if space_excluded:
        extractive_idxs = [i for i, r in enumerate(selected) if _is_extractive(r)]
        for sp in space_excluded:
            if not extractive_idxs:
                break
            swap_idx = extractive_idxs.pop()
            selected[swap_idx] = sp

    # Promote medicine/life-science fields excluded from top-20 by swapping out extractive fields.
    medicine_excluded = [r for r in remainder if _is_medicine(r)]
    if medicine_excluded:
        extractive_idxs = [i for i, r in enumerate(selected) if _is_extractive(r)]
        for med in medicine_excluded:
            if not extractive_idxs:
                break
            swap_idx = extractive_idxs.pop()
            selected[swap_idx] = med

    selected.sort(
        key=lambda r: r.get("final_score", r.get("deterministic_score", r.get("python_score", 0.0))),
        reverse=True,
    )

    out = []
    for row in selected:
        fid   = row.get("field_id", "")
        label = row.get("field_label", fid.replace("_", " ").title())
        dom   = row.get("domain", "interdisciplinary").strip().lower()
        if _valid_doms and dom not in _valid_doms:
            dom = "interdisciplinary"
        out.append({
            **row,                     # carry ALL original fields (knrao_score, kp_score, etc.)
            "field_id":                fid,
            "field_label":             label,
            "domain":                  dom,
            "final_score":             row.get("final_score", row.get("deterministic_score", row.get("python_score", 0.0))),
            "astrological_reason":     "Deterministic pre-score selection (LLM fallback).",
            "parent_reason":           "",
            "llm_group":               "fallback",
            "llm_rank":                len(out) + 1,
            "llm_selection_rationale": "",
            "llm_parent_summary":      "",
            "registry_description":    row.get("registry_description", ""),
            "registry_niche":          row.get("registry_niche", ""),
        })
    return out


def _llm_fallback_fields() -> List[Dict]:
    """Minimal generic field set used when LLM call is unavailable."""
    return [
        {"field_id":"computer_science_engineering",  "field_label":"Computer Science & Engineering",        "domain":"technology",  "planet_affinity":{"Mercury":0.40,"Rahu":0.30,"Saturn":0.20,"Sun":0.10}},
        {"field_id":"data_science_analytics",        "field_label":"Data Science & Analytics",              "domain":"technology",  "planet_affinity":{"Mercury":0.40,"Rahu":0.30,"Saturn":0.20,"Jupiter":0.10}},
        {"field_id":"artificial_intelligence_ml",    "field_label":"Artificial Intelligence & Machine Learning","domain":"technology","planet_affinity":{"Mercury":0.35,"Rahu":0.35,"Saturn":0.20,"Jupiter":0.10}},
        {"field_id":"medicine_mbbs",                 "field_label":"Medicine (MBBS)",                       "domain":"medicine",    "planet_affinity":{"Mars":0.30,"Sun":0.25,"Moon":0.25,"Mercury":0.20}},
        {"field_id":"law_llb",                       "field_label":"Law (LLB)",                             "domain":"law",         "planet_affinity":{"Jupiter":0.40,"Mercury":0.30,"Sun":0.20,"Saturn":0.10}},
        {"field_id":"economics",                     "field_label":"Economics",                             "domain":"commerce",    "planet_affinity":{"Jupiter":0.35,"Mercury":0.30,"Saturn":0.20,"Sun":0.15}},
        {"field_id":"civil_engineering",             "field_label":"Civil Engineering",                     "domain":"engineering", "planet_affinity":{"Saturn":0.40,"Mars":0.35,"Sun":0.15,"Mercury":0.10}},
        {"field_id":"psychology",                    "field_label":"Psychology",                            "domain":"humanities",  "planet_affinity":{"Moon":0.40,"Mercury":0.30,"Jupiter":0.20,"Ketu":0.10}},
        {"field_id":"education_teaching",            "field_label":"Education & Teaching",                  "domain":"education",   "planet_affinity":{"Jupiter":0.40,"Mercury":0.30,"Moon":0.20,"Sun":0.10}},
        {"field_id":"finance_banking",               "field_label":"Finance & Banking",                     "domain":"commerce",    "planet_affinity":{"Mercury":0.35,"Saturn":0.30,"Jupiter":0.25,"Venus":0.10}},
        {"field_id":"mechanical_engineering",        "field_label":"Mechanical Engineering",                "domain":"engineering", "planet_affinity":{"Mars":0.40,"Saturn":0.35,"Sun":0.15,"Jupiter":0.10}},
        {"field_id":"electrical_engineering",        "field_label":"Electrical Engineering",                "domain":"engineering", "planet_affinity":{"Mars":0.35,"Saturn":0.30,"Rahu":0.25,"Mercury":0.10}},
        {"field_id":"architecture",                  "field_label":"Architecture",                          "domain":"design",      "planet_affinity":{"Saturn":0.30,"Venus":0.30,"Mars":0.25,"Mercury":0.15}},
        {"field_id":"political_science_governance",  "field_label":"Political Science & Governance",        "domain":"public",      "planet_affinity":{"Sun":0.35,"Jupiter":0.30,"Saturn":0.25,"Mars":0.10}},
        {"field_id":"fine_arts_creative_design",     "field_label":"Fine Arts & Creative Design",           "domain":"arts",        "planet_affinity":{"Venus":0.45,"Moon":0.30,"Mercury":0.15,"Rahu":0.10}},
        {"field_id":"biotechnology",                 "field_label":"Biotechnology",                         "domain":"science",     "planet_affinity":{"Mercury":0.30,"Moon":0.25,"Jupiter":0.25,"Mars":0.20}},
        {"field_id":"research_academia",             "field_label":"Research & Academia",                   "domain":"research",    "planet_affinity":{"Mercury":0.35,"Ketu":0.30,"Jupiter":0.25,"Saturn":0.10}},
    ]


# =============================================================================
# GENUINE VALUE-ADD #3 — Top-3 Narrative Summary
# =============================================================================

_TOP3_SUMMARY_SYSTEM_PROMPT = """\
You are a warm, expert Jyotish career counselor writing a concise summary for a student or professional.
You have been given the top 3 career fields recommended by a Vedic astrology engine, along with key chart signals.

Write 2 paragraphs (50-70 words each) that:
  Paragraph 1: Summarise what ties these 3 fields together — the underlying natural aptitude,
               thinking style, or innate orientation that makes all 3 a strong fit.
  Paragraph 2: Briefly note the single most important chart signal (AK, AmK, or dominant yoga)
               driving these recommendations, in plain language a parent can understand.

Rules:
  - No jargon: avoid planet names, house numbers, nakshatra names, yoga names, dasha, rashi, karaka, lagna.
  - Speak directly to the person ("Your chart shows...", "You are naturally suited...").
  - Do NOT rank or compare the 3 fields — treat them as equally valid paths.
  - Return ONLY JSON: {"summary": "<paragraph 1> <paragraph 2>"}
"""


def generate_top3_narrative(
    top3_fields: List[Dict],
    payload: Any,
    eff_strengths: Dict[str, float],
) -> str:
    """Generate a cohesive 2-paragraph plain-English summary for the end user
    explaining why the top-3 career recommendations fit their chart.

    Returns a plain-text string (no HTML/markdown).
    Falls back to a deterministic template if the LLM is unavailable.

    Args:
        top3_fields:   First 3 items from the deterministic results list.
        payload:       NatalPayloadV2 instance (or duck-typed equivalent).
        eff_strengths: Dict of effective planetary strengths from the engine.
    """
    if not top3_fields:
        return ""

    # ── Deterministic fallback ────────────────────────────────────────────────
    def _fallback() -> str:
        labels = [f.get("field_label", f.get("field_id", "")) for f in top3_fields[:3]]
        ak  = getattr(payload, "atmakaraka",   "") or ""
        amk = getattr(payload, "amatyakaraka", "") or ""
        yogas = (getattr(payload, "detected_yogas", []) or
                 getattr(payload, "yogas_present",  []) or [])
        yoga_str = f", supported by active yogas ({', '.join(yogas[:2])})" if yogas else ""
        return (
            f"Based on your astrological chart, your top three recommended career paths are "
            f"{labels[0]}, {labels[1]}, and {labels[2] if len(labels) > 2 else ''}. "
            f"These fields share a common thread: they align with your natural aptitude for "
            f"structured thinking, analytical problem-solving, and meaningful contribution "
            f"in your chosen domain{yoga_str}. "
            f"Each path offers a strong alignment with who you are at your core and the unique "
            f"strengths your chart reveals."
        )

    # ── Init client ───────────────────────────────────────────────────────────
    try:
        # GAP-FIX (2026-08, "debug dump never created" investigation):
        # this previously did `from .engine_io import _maybe_load_dotenv`,
        # but engine_io.py has no such function -- only llm.py itself does
        # (defined above, module-level). The import therefore always raised
        # ImportError, which this bare `except Exception: pass` silently
        # swallowed, so .env was NEVER actually loaded from inside this
        # function -- it only worked at all when something upstream (e.g.
        # the CLI wrapper script) happened to have already populated
        # os.environ before this ran. Calling the local function directly
        # (no import needed -- it's defined in this same module) fixes .env
        # loading (including DEBUG=true, LLM_PROVIDER, API keys) for any
        # caller that invokes run_engine()/call_llm_for_fields directly
        # without going through a CLI wrapper that pre-loads .env itself.
        _maybe_load_dotenv()
    except Exception:
        pass

    _provider_name  = os.getenv("LLM_PROVIDER", "gemini").lower()
    _prov           = _LLM_PROVIDERS.get(_provider_name, _LLM_PROVIDERS["gemini"])
    _env_var, _default_model, _call_fn = _prov
    _model_override = os.getenv("LLM_MODEL", _default_model)
    api_key         = os.getenv(_env_var)
    if not api_key:
        logger.debug("generate_top3_narrative: no API key — using fallback template.")
        return _fallback()

    client = _ProviderClientWrapper(_call_fn, api_key, _model_override)

    # ── Build prompt ──────────────────────────────────────────────────────────
    fields_summary = [
        {
            "rank":              i + 1,
            "field_label":       f.get("field_label", ""),
            "domain":            f.get("domain", ""),
            "astrological_reason": f.get("astrological_reason", ""),
        }
        for i, f in enumerate(top3_fields[:3])
    ]

    # Compact chart signals — enough context for a plain-language bridge
    ak  = getattr(payload, "atmakaraka",   "") or "unknown"
    amk = getattr(payload, "amatyakaraka", "") or "unknown"
    yogas = (getattr(payload, "detected_yogas", []) or
             getattr(payload, "yogas_present",  []) or [])
    digs = getattr(payload, "planet_dignities", {}) or {}
    age  = float(getattr(payload, "current_age", 0))

    # Strongest planet by effective strength
    top_planet = max(eff_strengths, key=eff_strengths.get) if eff_strengths else ""

    chart_signals = {
        "atmakaraka":       ak,
        "amatyakaraka":     amk,
        "ak_dignity":       digs.get(ak, "neutral"),
        "amk_dignity":      digs.get(amk, "neutral"),
        "strongest_planet": top_planet,
        "active_yogas":     yogas[:4],
        "current_age":      age,
    }

    user_prompt = (
        f"Top 3 recommended fields:\n{json.dumps(fields_summary, indent=2)}\n\n"
        f"Key chart signals (internal — do NOT mention these terms in output):\n"
        f"{json.dumps(chart_signals, indent=2)}\n\n"
        f"Write the 2-paragraph summary. Return ONLY JSON: {{\"summary\": \"...\"}}"
    )

    messages = [
        {"role": "system", "content": _TOP3_SUMMARY_SYSTEM_PROMPT + _language_directive()},
        {"role": "user",   "content": user_prompt},
    ]

    _SUMMARY_SCHEMA = {
        "name": "top3_summary",
        "schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    def _validate_summary(data: Dict) -> None:
        s = data.get("summary", "")
        if not s or len(s.split()) < 20:
            raise ValueError("Summary too short — expected at least 20 words.")

    try:
        result = _run_llm_with_retry(client, messages, _SUMMARY_SCHEMA, _validate_summary, max_retries=2)
        if result:
            summary = result.get("summary", "").strip()
            if summary:
                logger.info("generate_top3_narrative: summary generated (%d words).", len(summary.split()))
                return summary
    except Exception as exc:
        logger.warning("generate_top3_narrative: LLM call failed -- %s", exc)

    return _fallback()


_STAGE1_NARRATIVE_SYSTEM_PROMPT = """\
You are a Jyotish (Vedic astrology) analyst writing an internal audit note for
Stage 1 of a scoring pipeline: astro.py::_compute_eff_strengths(), which turns
each planet's raw Shadbala into a single classically-adjusted "effective
strength" figure (dignity, combustion, Panchadha Maitri, Vargottama, Baladi
Avastha, functional role, nakshatra-lord house placement, and Paksha Bala all
folded in; Graha Yuddha and Yogakaraka deliberately excluded at this stage --
they're applied later, at Stage 2).

You are given the final eff_strength number for every planet plus the
per-planet factors that produced it (dignity label, combustion multiplier,
avastha multiplier, vargottama flag).

Write ONE paragraph (60-90 words) that:
  - States which planet(s) came out strongest and weakest after this stage's
    adjustments, and the single biggest reason why (dignity, combustion, or
    avastha -- whichever moved that planet's number the most).
  - Notes anything analytically notable: a planet whose raw strength was
    reshaped substantially by combustion/avastha, or a vargottama planet.
  - Stays strictly descriptive of what Stage 1's numbers show -- do NOT
    recommend a career field, do NOT rank fields, do NOT introduce any
    number not present in the input data.

Rules:
  - Plain language a non-astrologer analyst could follow; planet names and
    dignity/combustion/avastha terms are fine here (this is an internal
    audit note, not end-user copy).
  - Return ONLY JSON: {"narrative": "<one paragraph>"}
"""


def generate_stage1_narrative(
    eff_strengths: Dict[str, float],
    payload: Any,
) -> str:
    """Stage 1 audit-trace narrative: one paragraph summarizing what
    astro.py::_compute_eff_strengths()'s output shows for this chart --
    strongest/weakest planets and the dominant factor (dignity/combustion/
    avastha) behind each, per the audit_trace_cli.py Stage 1 request.

    Returns a plain-text string (no HTML/markdown). Falls back to a
    deterministic template if the LLM is unavailable.

    Args:
        eff_strengths: Dict of effective planetary strengths (Stage 1 output).
        payload:       NatalPayloadV2 instance (or duck-typed equivalent) --
                       used to read the per-planet factors (dignity,
                       combustion, avastha, vargottama) that produced
                       eff_strengths, for context only.
    """
    if not eff_strengths:
        return ""

    # ── Deterministic fallback ────────────────────────────────────────────────
    def _fallback() -> str:
        strongest = max(eff_strengths, key=eff_strengths.get)
        weakest = min(eff_strengths, key=eff_strengths.get)
        return (
            f"Stage 1 (effective strength) ranks {strongest} highest "
            f"({eff_strengths[strongest]:.3f}) and {weakest} lowest "
            f"({eff_strengths[weakest]:.3f}) after folding in dignity, "
            f"combustion, Panchadha Maitri, Vargottama, and Baladi Avastha "
            f"(Graha Yuddha and Yogakaraka are applied later, at Stage 2). "
            f"This is a deterministic fallback summary -- no LLM provider "
            f"was available."
        )

    # ── Init client ───────────────────────────────────────────────────────────
    try:
        # GAP-FIX (2026-08, "debug dump never created" investigation):
        # this previously did `from .engine_io import _maybe_load_dotenv`,
        # but engine_io.py has no such function -- only llm.py itself does
        # (defined above, module-level). The import therefore always raised
        # ImportError, which this bare `except Exception: pass` silently
        # swallowed, so .env was NEVER actually loaded from inside this
        # function -- it only worked at all when something upstream (e.g.
        # the CLI wrapper script) happened to have already populated
        # os.environ before this ran. Calling the local function directly
        # (no import needed -- it's defined in this same module) fixes .env
        # loading (including DEBUG=true, LLM_PROVIDER, API keys) for any
        # caller that invokes run_engine()/call_llm_for_fields directly
        # without going through a CLI wrapper that pre-loads .env itself.
        _maybe_load_dotenv()
    except Exception:
        pass

    _provider_name  = os.getenv("LLM_PROVIDER", "gemini").lower()
    _prov           = _LLM_PROVIDERS.get(_provider_name, _LLM_PROVIDERS["gemini"])
    _env_var, _default_model, _call_fn = _prov
    _model_override = os.getenv("LLM_MODEL", _default_model)
    api_key         = os.getenv(_env_var)
    if not api_key:
        logger.debug("generate_stage1_narrative: no API key -- using fallback template.")
        return _fallback()

    client = _ProviderClientWrapper(_call_fn, api_key, _model_override)

    # ── Build prompt: eff_strengths + the per-planet factors behind them ──────
    dignity_labels   = dict(getattr(payload, "planet_dignities", {}) or {})
    combustion_mult  = dict(getattr(payload, "combustion_mult", {}) or {})
    avastha_mult     = dict(getattr(payload, "avastha_mult", {}) or {})
    vargottama_set   = set(getattr(payload, "vargottama_planets", []) or [])

    planet_breakdown = [
        {
            "planet":            p,
            "eff_strength":      round(float(v), 4),
            "dignity":           dignity_labels.get(p, ""),
            "combustion_mult":   combustion_mult.get(p, 1.0),
            "avastha_mult":      avastha_mult.get(p, 1.0),
            "vargottama":        p in vargottama_set,
        }
        for p, v in sorted(eff_strengths.items(), key=lambda x: -x[1])
    ]

    user_prompt = (
        f"Stage 1 eff_strength results and contributing factors, strongest to weakest:\n"
        f"{json.dumps(planet_breakdown, indent=2)}\n\n"
        f"Write the one-paragraph Stage 1 analysis note. Return ONLY JSON: {{\"narrative\": \"...\"}}"
    )

    messages = [
        {"role": "system", "content": _STAGE1_NARRATIVE_SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    _NARRATIVE_SCHEMA = {
        "name": "stage1_narrative",
        "schema": {
            "type": "object",
            "properties": {"narrative": {"type": "string"}},
            "required": ["narrative"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    def _validate_narrative(data: Dict) -> None:
        s = data.get("narrative", "")
        if not s or len(s.split()) < 15:
            raise ValueError("Narrative too short -- expected at least 15 words.")

    try:
        result = _run_llm_with_retry(client, messages, _NARRATIVE_SCHEMA, _validate_narrative, max_retries=2)
        if result:
            narrative = result.get("narrative", "").strip()
            if narrative:
                logger.info("generate_stage1_narrative: narrative generated (%d words).", len(narrative.split()))
                return narrative
    except Exception as exc:
        logger.warning("generate_stage1_narrative: LLM call failed -- %s", exc)

    return _fallback()


def generate_stage_narrative(
    stage_no: int,
    stage_title: str,
    stage_description: str,
    planet_rows: List[Dict[str, Any]],
    primary_metric: str,
    extra_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Generic Stage 2-8 audit-trace narrative (mirrors generate_stage1_narrative's
    pattern, generalised so Stages 2-8 don't each need a bespoke function).

    One paragraph (60-90 words) summarizing what this pipeline stage's own
    math shows for this chart -- descriptive only, never a field
    recommendation or ranking (that boundary matters here specifically
    because these are internal audit notes, not the LLM narrative the live
    engine already generates for end users elsewhere in this module).

    Returns a plain-text string (no HTML/markdown). Falls back to a
    deterministic template if the LLM is unavailable.

    Args:
        stage_no:           Stage number (2-8) for labeling only.
        stage_title:        Short "what this stage computes" line, e.g.
                             "adjusted_strength = eff_strength x yogakaraka_mult x graha_yuddha_mult".
        stage_description:  1-3 sentence note on what's analytically interesting
                             to look for at this stage (drives the system prompt).
        planet_rows:        List of {"planet": p, <primary_metric>: v, ...context}
                             dicts -- the per-planet table this stage printed.
                             May be empty for a stage with no planet dimension
                             (e.g. Stage 7's plain scalar overwrite); the
                             narrative then falls back to extra_context only.
        primary_metric:     Key inside each planet_rows dict to rank
                             strongest/weakest by (for both the fallback
                             template and to tell the LLM what to focus on).
        extra_context:      Optional dict of stage-level scalar context (field
                             id, composite/gate values, etc.) included as
                             read-only background, never as something to
                             recommend or rank on.
    """
    if not planet_rows and not extra_context:
        return ""

    # ── Deterministic fallback ────────────────────────────────────────────────
    def _fallback() -> str:
        if planet_rows:
            ranked = sorted(planet_rows, key=lambda r: r.get(primary_metric, 0) or 0, reverse=True)
            strongest, weakest = ranked[0], ranked[-1]
            body = (
                f"Stage {stage_no} ({stage_title}) ranks {strongest.get('planet', '?')} highest "
                f"({strongest.get(primary_metric)}) and {weakest.get('planet', '?')} lowest "
                f"({weakest.get(primary_metric)}) on {primary_metric}."
            )
        else:
            ctx_bits = ", ".join(f"{k}={v}" for k, v in (extra_context or {}).items())
            body = f"Stage {stage_no} ({stage_title}): {ctx_bits}."
        return body + " This is a deterministic fallback summary -- no LLM provider was available."

    # ── Init client ───────────────────────────────────────────────────────────
    try:
        # GAP-FIX (2026-08, "debug dump never created" investigation):
        # this previously did `from .engine_io import _maybe_load_dotenv`,
        # but engine_io.py has no such function -- only llm.py itself does
        # (defined above, module-level). The import therefore always raised
        # ImportError, which this bare `except Exception: pass` silently
        # swallowed, so .env was NEVER actually loaded from inside this
        # function -- it only worked at all when something upstream (e.g.
        # the CLI wrapper script) happened to have already populated
        # os.environ before this ran. Calling the local function directly
        # (no import needed -- it's defined in this same module) fixes .env
        # loading (including DEBUG=true, LLM_PROVIDER, API keys) for any
        # caller that invokes run_engine()/call_llm_for_fields directly
        # without going through a CLI wrapper that pre-loads .env itself.
        _maybe_load_dotenv()
    except Exception:
        pass

    _provider_name  = os.getenv("LLM_PROVIDER", "gemini").lower()
    _prov           = _LLM_PROVIDERS.get(_provider_name, _LLM_PROVIDERS["gemini"])
    _env_var, _default_model, _call_fn = _prov
    _model_override = os.getenv("LLM_MODEL", _default_model)
    api_key         = os.getenv(_env_var)
    if not api_key:
        logger.debug("generate_stage_narrative(stage=%s): no API key -- using fallback template.", stage_no)
        return _fallback()

    client = _ProviderClientWrapper(_call_fn, api_key, _model_override)

    system_prompt = (
        f"You are a Jyotish (Vedic astrology) analyst writing an internal audit note for "
        f"Stage {stage_no} of a scoring pipeline.\n\n"
        f"What Stage {stage_no} computes: {stage_title}\n"
        f"{stage_description}\n\n"
        f"Write ONE paragraph (60-90 words) that:\n"
        f"  - States which planet(s) (or, if no planet table is given, which overall "
        f"figures) stand out at this stage and the single biggest reason why.\n"
        f"  - Notes anything analytically notable about this stage's own numbers.\n"
        f"  - Stays strictly descriptive of what THIS stage's numbers show -- do NOT "
        f"recommend a career field, do NOT rank fields, do NOT introduce any number "
        f"not present in the input data, and do NOT restate other stages' results.\n\n"
        f"Rules:\n"
        f"  - Plain language a non-astrologer analyst could follow; planet names and "
        f"astrological terms are fine here (this is an internal audit note).\n"
        f"  - Return ONLY JSON: {{\"narrative\": \"<one paragraph>\"}}"
    )

    user_prompt_parts = []
    if planet_rows:
        ranked_rows = sorted(planet_rows, key=lambda r: r.get(primary_metric, 0) or 0, reverse=True)
        user_prompt_parts.append(
            f"Stage {stage_no} per-planet table, strongest to weakest on '{primary_metric}':\n"
            f"{json.dumps(ranked_rows, indent=2)}"
        )
    if extra_context:
        user_prompt_parts.append(f"Stage {stage_no} scalar context:\n{json.dumps(extra_context, indent=2)}")
    user_prompt_parts.append(f'Write the one-paragraph Stage {stage_no} analysis note. Return ONLY JSON: {{"narrative": "..."}}')
    user_prompt = "\n\n".join(user_prompt_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    _NARRATIVE_SCHEMA = {
        "name": f"stage{stage_no}_narrative",
        "schema": {
            "type": "object",
            "properties": {"narrative": {"type": "string"}},
            "required": ["narrative"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    def _validate_narrative(data: Dict) -> None:
        s = data.get("narrative", "")
        if not s or len(s.split()) < 15:
            raise ValueError("Narrative too short -- expected at least 15 words.")

    try:
        result = _run_llm_with_retry(client, messages, _NARRATIVE_SCHEMA, _validate_narrative, max_retries=2)
        if result:
            narrative = result.get("narrative", "").strip()
            if narrative:
                logger.info("generate_stage_narrative(stage=%s): narrative generated (%d words).", stage_no, len(narrative.split()))
                return narrative
    except Exception as exc:
        logger.warning("generate_stage_narrative(stage=%s): LLM call failed -- %s", stage_no, exc)

    return _fallback()
