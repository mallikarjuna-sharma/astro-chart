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

_GENERATOR_SYSTEM_PROMPT = """You are an empathetic Jyotish career counselor. You have been given a list of 20 pre-selected career fields and chart context. Write two things for each field:

1. astrological_reason (max 20 words): Cite the specific planet, house placement, dignity, or yoga from THIS chart that justifies this field. Be concrete.
   — Relevant chart signals to draw from: AK (Atmakaraka), AmK (Amatyakaraka), Peak Dasha Planet, Engine-Determined Strengths (STRONG/MODERATE/WEAK), Neecha Bhanga, Vargottama, active yogas, KP sub-lord, D10 H10 occupants.
   — "Peak Dasha Planet" is the engine-identified planet whose dasha best activates career energy for the current life period; reference it by its planet name, not as "Mahadasha lord."

2. parent_friendly_explanation (two paragraphs, ~50 words each):
   Paragraph 1: Describe what this field involves as a career — the day-to-day work, skills used, and types of problems solved.
   Paragraph 2: Explain why THIS student is well-suited — their natural strengths, thinking style, and how these align with what the field demands.

LP5 RANKING NOTE: The field ranking (position 1 through 20) was determined by a separate
rigorous astrological analysis and is FINAL. Do not imply any field should rank higher or
lower than its assigned position. Simply explain why each field is an excellent fit.

CRITICAL RULE: parent_friendly_explanation MUST NOT contain any astrological terms whatsoever.
Forbidden: planet names (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu), house numbers (H1, H2...H12, 1st house etc.), yoga names (GajaKesari, BudhaAditya etc.), nakshatra names, dasha, karaka, lagna, rashi, AK, AmK, dignity terms (exalted, combust, debilitated), or any Jyotish/Vedic terminology.
Write in plain English that a parent with zero astrology knowledge can fully understand.
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

_STEP2_RESPONSE_SCHEMA = {
    "name": "career_fields_generator",
    "schema": {
        "type": "object",
        "properties": {
            "selected_fields": {
                "type": "array",
                "description": "Explanations for the 20 pre-selected career fields.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_id": {"type": "string"},
                        "astrological_reason": {"type": "string"},
                        "parent_friendly_explanation": {"type": "string"}
                    },
                    "required": ["field_id", "astrological_reason", "parent_friendly_explanation"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["selected_fields"],
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


def _provider_api_key(provider: str, env_var: str) -> str:
    key = (os.getenv(env_var) or "").strip()
    if provider == "gemini" and not key:
        key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    return key


def call_llm_text_prompt(
    prompt: str,
    *,
    providers: list[str] | None = None,
    model_override: str | None = None,
) -> tuple[str, str, str]:
    """Call the first configured LLM provider that succeeds.

    Returns ``(response_text, provider_name, model_name)``.
    Raises ``RuntimeError`` when every provider fails or none is configured.
    """
    primary = (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    order = providers or [primary] + [p for p in ("gemini", "openai", "anthropic") if p != primary]

    errors: list[str] = []
    for provider in order:
        spec = _LLM_PROVIDERS.get(provider)
        if not spec:
            continue
        env_var, default_model, call_fn = spec
        api_key = _provider_api_key(provider, env_var)
        if not api_key:
            errors.append(f"{provider}: {env_var} missing")
            continue
        model = model_override or os.getenv("LLM_MODEL") or default_model
        try:
            return call_fn(prompt, api_key, model), provider, model
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{provider}: {type(exc).__name__}: {exc}")

    if not errors:
        raise RuntimeError("No LLM providers are configured (set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)")
    raise RuntimeError("; ".join(errors))


def llm_provider_preflight(provider: str) -> Dict[str, Any]:
    """Check SDK availability before attempting an external provider call."""
    import importlib.util
    provider = str(provider or "").lower()
    module = {"openai": "openai", "anthropic": "anthropic", "gemini": "google.genai"}.get(provider)
    configured = provider in _LLM_PROVIDERS
    installed = bool(module and importlib.util.find_spec(module)) if configured else False
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
                # On attempt 3+ try a lighter model variant
                if attempt >= 3 and hasattr(client, 'model') and "2.5-flash" in str(getattr(client, 'model', '')):
                    _alt = "gemini-2.0-flash-lite"
                    logger.warning(f"Switching to fallback model: {_alt}")
                    client.model = _alt
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
    """Post-scoring enrichment: attach natural-language explanations to the
    deterministic top-20 career fields.

    The ranking is FIXED by the deterministic engine — this function adds:
      • astrological_reason          ≤20 words citing AK/AmK/house/yoga from THIS chart
      • parent_friendly_explanation  2 plain-English paragraphs, zero jargon

    NOTE: LLM-as-reranker (the old Step 1 selector) is intentionally removed.
    It added non-determinism, latency, and cost with no ranking benefit over the
    Shadbala/gap_boost scoring that already encodes the same astrological signals.
    """
    # Deterministic top-20 is the authoritative ranking — use it directly.
    n_explain = min(20, len(top_35_fields))
    top20 = top_35_fields[:n_explain]

    # ── Init client ────────────────────────────────────────────────────────────
    try:
        from .engine_io import _maybe_load_dotenv
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
    # Enrich each field with engine scores + top affinity planets so the LLM
    # can write a specific astrological_reason rather than a generic summary.
    def _enrich_for_explanation(f: Dict, rank: int) -> Dict:
        aff   = f.get("affinity_planets", {})
        top3  = sorted(aff.items(), key=lambda x: -x[1])[:3] if aff else []
        trace = f.get("calc_trace", f.get("gap_detail", {}))
        return {
            "rank":             rank,
            "field_id":         f.get("field_id", ""),
            "field_label":      f.get("field_label", ""),
            "domain":           f.get("domain", ""),
            "engine_score":     round(f.get("final_score", 0), 1),
            "top_planets":      [{"planet": p, "weight": round(w, 2)} for p, w in top3],
            "verified_factors": (trace.get("verified_factors", "") if isinstance(trace, dict) else ""),
            "gap_boost":        round(f.get("gap_boost", 0), 3),
        }

    expl_user_prompt = (
        f"Chart Context:\n{chart_summary_text}\n\n"
        f"Selected Fields to Write For (deterministic ranking by engine score):\n"
        + json.dumps(
            [_enrich_for_explanation(f, i + 1) for i, f in enumerate(top20)],
            indent=2,
        )
    )

    expl_messages = [
        {"role": "system", "content": _GENERATOR_SYSTEM_PROMPT},
        {"role": "user",   "content": expl_user_prompt},
    ]

    top20_ids = [f.get("field_id") for f in top20]

    def validate_explanations(data: Dict) -> None:
        fields = data.get("selected_fields", [])
        if len(fields) != n_explain:
            raise ValueError(f"Expected {n_explain} explanations, got {len(fields)}.")
        returned_ids = {f["field_id"] for f in fields}
        missing = set(top20_ids) - returned_ids
        if missing:
            raise ValueError(f"Missing explanations for: {', '.join(sorted(missing))}")

    logger.info("Starting LLM explanation generation for deterministic top-%d...", n_explain)
    expl_result = _run_llm_with_retry(
        client, expl_messages, _STEP2_RESPONSE_SCHEMA, validate_explanations, max_retries
    )

    if not expl_result:
        logger.error("LLM explanation generation failed — returning deterministic results.")
        return None

    # ── Merge explanations into deterministic results (preserve engine order) ──
    generated_dict = {f["field_id"]: f for f in expl_result["selected_fields"]}
    final_results: List[Dict] = []
    for rank, f in enumerate(top20, 1):
        fid      = f.get("field_id", "")
        llm_data = generated_dict.get(fid, {})
        merged   = {**f, **llm_data}
        # llm_rank mirrors deterministic rank (no reranking)
        merged["llm_rank"]  = rank
        merged["llm_score"] = round((1 - (rank - 1) / n_explain) * 100)
        final_results.append(merged)

    logger.info("LLM explanation generation complete for %d fields.", len(final_results))
    return final_results

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
        from .engine_io import _maybe_load_dotenv
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
        {"role": "system", "content": _TOP3_SUMMARY_SYSTEM_PROMPT},
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
