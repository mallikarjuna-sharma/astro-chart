"""JyotishAI — LLM prompt template, chart summary, provider calls, parser."""
import json, os
from typing import Dict, List, Tuple, Set, Any, Optional

from .payload import NatalPayloadV2, ENGINE_VERSION, logger
from .astro import _get_active_dasha_lord


from .engine_io import _load_course_registry
_COURSE_REGISTRY: dict = _load_course_registry()


_LLM_FIELD_PROMPT_TEMPLATE = """You are an expert Jyotish career analyst. Using the birth chart below, select exactly 20 courses ranked by astrological fit.

{chart_summary}

━━━ JYOTISH CAREER DECISION REFERENCE ━━━

STEP 1 — IDENTIFY CAREER DRIVERS (in priority order):
1. AK (Atmakaraka) & Karakamsha → The soul's ultimate desire. This sets the broad INDUSTRY or DOMAIN. The Karakamsha sign reveals innate talents.
2. AmK (Amatyakaraka) → The Executive Minister. This defines the ACTUAL DAILY WORK or functional role.
3. H10 Lord & D10 (Dashamsha) Occupants → Karma-bhava. H10 defines public impact. Planets in the 10th house of the D10 chart show the specific career environment.
4. Active Mahadasha / Antardasha Lords → The current period activates those planets' domains for the timing of education/career entry.
5. Strongest planet by effective strength → Amplifies domains of #1–4 when aligned.

STEP 2 — HOUSE MODIFIERS (The Karmic Application):
Evaluate the House Placement of the primary career drivers (AK, AmK, H10 Lord, Dasha Lord). The house dictates HOW and WHERE the planet's domain is applied:
* H1: Independent execution, entrepreneurship, sports, medicine, and leadership.
* H2: Resource management, finance, accounting, banking, data analytics, and consultancy.
* H3: Hands-on skills, IT/software, journalism, media, design, telecommunications, and arts.
* H4: Infrastructure, environment, civil/architectural engineering, real estate, teaching, agriculture.
* H5: Advisory, AI, computer science, data science, mathematics, academia, and creative design.
* H6: Solving problems, medicine, nursing, law, cybersecurity, defense, and backend analytics.
* H7: Business dealings, commerce, international relations, management, and supply chain.
* H8: Deep tech, surgery, mining, backend IT, cybersecurity, forensics, and occult/psychology.
* H9: Guiding principles, law, university-level research, theology, diplomacy, and higher education.
* H10: Executive power, civil services, corporate management, core engineering, and high-visibility roles. [KETU IN H10 EXCEPTION: When Ketu occupies H10, the career becomes research-oriented, unconventional, or spiritually driven — elevate materials science, space sciences, research academia, ayurveda, and archaeology over conventional management/corporate fields.]
* H11: Large group dynamics, systems engineering, public policy, large-scale commerce, and sociology.
* H12: Behind-the-scenes, hospital medicine, pure research, foreign trade, and alternative healing.

STEP 3 — DIGNITY & STRUCTURAL MODIFIERS:
* Exalted / Own Sign / Vargottama: Planet operates with peak clarity. Heavily favor its domains.
* Retrograde (Vakri): Highly driven internal effort. Elevate disruptive, highly technical, or deep-research variants of its domains.
* Neecha Bhanga: Powerful, late-blooming career driver. 
* Debilitated: Exclude its primary domains from the top ranks.
* Enemy Sign: Moderate penalty — slightly reduce priority but DO NOT exclude. CRITICAL: if this planet is the AK (Atmakaraka), its soul-direction fields must remain in the top ranks despite the dignity challenge. The soul is still directed toward those domains, it just faces obstacles.
* Combust: Deprioritize its fields, with TWO EXCEPTIONS:
  1. Mercury Combust + BudhaAditya Yoga: IMMUNE to penalties. Actively elevate Computer Science, Data, AI, and Math fields.
  2. High Shadbala (>= 1.30x): Strength overrides the combustion.

STEP 4 — YOGA BOOSTS:
* BudhaAditya → Elevates data, analytics, IT, computer science, math, and administrative fields.
* GajaKesari → Elevates teaching, law, management, finance, and advisory fields.
* Ruchaka → Elevates defense, engineering, surgery, mechanical, sports, and technical fields.
* Hamsa → Elevates law, education, philosophy, economics, and advisory fields.
* Malavya → Elevates arts, design, media, architecture, and luxury management fields.
* Shasha → Elevates heavy engineering, infrastructure, mining, agriculture, and real estate fields.
* Bhadra → Elevates data science, communication, commerce, IT, and statistical fields.
* Saraswati → Elevates research, academia, literature, fine arts, and bioinformatics fields.
* ChandraMangala → Elevates commerce, entrepreneurship, finance, and logistics fields.
* Raja Yoga → Elevates civil services, governance, corporate management, and elite professional fields.
* Rahu-Ketu Axis in Career Houses → Rahu in H10/H11/H3 elevates emerging tech, cyber, and disruptive innovation. Ketu in H10/H12 elevates research, pure science, materials science, advanced engineering, ayurveda, yoga, and archaeology (moksha-oriented, unconventional careers).

STEP 5 — KP (KRISHNAMURTI PADDHATI) CUSP ANALYSIS:
In KP astrology, the sub-lord of each house cusp is the FINAL ARBITER of that house's fructification. Apply these rules AFTER Steps 1–4, and use them to break ties or confirm rankings.

H10 Sub-lord (primary career determinant):
The career MUST align with the sub-lord's planet domain. This overrides weaker dignity or house signals.
  • Jupiter sub-lord → philosophy, law, education, management, research, finance, advisory
  • Mercury sub-lord → IT, data analytics, mathematics, communication, commerce
  • Mars sub-lord    → engineering, surgery, defence, metallurgy, construction
  • Venus sub-lord   → arts, design, media, hospitality, life sciences, commerce
  • Saturn sub-lord  → civil services, heavy engineering, mining, agriculture, materials science, infrastructure
  • Sun sub-lord     → administration, government, physics, energy, leadership roles
  • Moon sub-lord    → nursing, food science, marine, psychology, public service
  • Rahu sub-lord    → emerging tech, AI, pharma, aviation, foreign trade, unconventional fields
  • Ketu sub-lord    → research, occult, ayurveda, space science, electronics, materials science

H10 Star-lord (secondary career medium/context):
The star-lord defines HOW and WHERE the career manifests (the day-to-day environment). Cross-reference with H10 sub-lord domains for strongest alignment.

H5 Sub-lord (education stream):
Determines the primary academic discipline the student is naturally drawn to. Apply the same planet-domain mapping as H10 sub-lord above.

H9 Sub-lord (higher education / philosophy of learning):
Governs the higher education path and guiding philosophy. Align with H10 sub-lord for a cohesive academic-career trajectory.

KP H10 Significators — Elevation Rule:
  • L1/L2 (primary): If a field's top-weight karaka planet appears as a primary H10 significator (L1/L2), ELEVATE that field — this is the strongest KP career confirmation signal.
  • L3/L4 (secondary): Mild supporting signal. Use to break ties between similarly-scored fields.

KP Convergence Rule (highest priority career signal):
When the H10 sub-lord + H10 star-lord + active Mahadasha lord ALL point to the SAME domain → that domain has the strongest possible KP validation. Elevate ALL fields in that domain regardless of other factors, subject only to the cluster limit.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRE-SCORED TOP-35 FIELDS (Python deterministic scores — highest first):
{top_35_fields}

━━━ YOUR TASK: DEEP ANALYSIS — SELECT 5 MATCH + 1 SOUL ━━━

You must return exactly TWO groups:

GROUP A — TOP 5 STRONG MATCH FIELDS
Select the 5 best fields from the list above that show the strongest overall fit for THIS chart.
Consider: AK dignity + yogas, AmK functional role, H10 lord placement, active dasha activation, domain convergence.
Respect deterministic Python ranks — do not drop a top-ranked field unless you identify a genuine karmic mismatch.

GROUP B — SOUL-ALIGNED JUSTIFICATION (FIELD IS PRE-DETERMINED)
The soul-aligned field for this chart has been deterministically pre-selected by the engine:
  field_id : {soul_field_id}
  label    : {soul_field_label}
  domain   : {soul_field_domain}

Write the soul-level justification for THIS field ONLY — do NOT select a different field.
The field_id in "soul_aligned" MUST be exactly "{soul_field_id}" (verbatim, no changes).
Base the justification on the AK planet dignity/placement, Karakamsha sign, and soul-karaka significations.

For EACH of the 6 fields (5 match + 1 soul), write:
1. A full-paragraph ASTROLOGICAL JUSTIFICATION (4-6 sentences, 80-120 words) for astrologers:
   — Name the specific planets, houses, dignities, yogas, and dasha lords from THIS chart.
   — Explain the karmic logic: why does THIS combination of factors make this field the right choice?
   — Reference AK, AmK, H10 lord, active dasha, and any relevant yogas explicitly.
2. A full-paragraph PARENT EXPLANATION (3-5 sentences, 60-90 words) in plain English:
   — No astrology terms whatsoever (no planet names, no 'lagna', 'dasha', 'karaka', 'exalted', 'yoga').
   — Describe the child's natural personality strengths, thinking style, and WHY this career fits them.
   — Mention real-world outcomes: what kind of work they'll do, where they'll work, what impact they'll have.

Also write:
- A global ASTROLOGICAL OVERVIEW (4-5 sentences) for astrologers summarising the chart's career signature.
- A global PARENT OVERVIEW (3-4 sentences) in plain English for parents about their child's overall direction.

Return ONLY valid JSON (no markdown fences, no prose outside JSON):
{{
  "astrologer_overview": "4-5 sentence astrological summary of this chart's career signature: AK + dignity + yogas + dasha + domain convergence.",
  "parent_overview": "3-4 plain-English sentences for parents. NO astrology jargon. Child's personality, strengths, and broad career direction.",
  "top_5_match": [
    {{
      "field_id": "exact_field_id_from_pre_scored_list",
      "rank": 1,
      "astrologer_justification": "Full paragraph (80-120 words) for astrologers: specific planets, dignities, yogas, houses, dasha from THIS chart.",
      "parent_explanation": "Full paragraph (60-90 words) for parents: plain English, personality-driven, outcome-focused. Zero jargon."
    }}
  ],
  "soul_aligned": {{
    "field_id": "{soul_field_id}",
    "astrologer_justification": "Full paragraph (80-120 words) explaining the soul-level fit of {soul_field_label}: AK planet, Karakamsha, soul-karaka significations from THIS chart.",
    "parent_explanation": "Full paragraph (60-90 words) in plain English: what makes {soul_field_label} the deepest calling for this child."
  }}
}}

Output rules:
1. Exactly 5 items in top_5_match (rank 1 to 5).
2. Exactly 1 item in soul_aligned.
3. Every field_id must appear VERBATIM from the pre-scored list — do not invent field_ids.
4. astrologer_justification must cite THIS chart's specific data — no generic significations.
5. parent_explanation and parent_overview must be completely jargon-free.
6. No planet_affinity needed — computed in Python.
"""

from .constants import _VALID_DOMAINS

# AK → preferred soul domains (mirrors web_report._AK_SOUL — kept in sync here
# to avoid circular imports; both dicts must stay identical)
_AK_SOUL_DOMAINS: Dict[str, list] = {
    "Moon":    ["arts", "medicine", "humanities"],
    "Venus":   ["arts", "humanities"],
    "Jupiter": ["humanities", "law", "medicine"],
    "Mercury": ["technology", "science"],
    "Saturn":  ["engineering", "science", "interdisciplinary"],
    "Sun":     ["law", "interdisciplinary"],
    "Mars":    ["engineering", "science"],
    "Rahu":    ["technology", "interdisciplinary"],
    "Ketu":    ["science", "interdisciplinary"],
}


def _pick_soul_from_top35(
    top_35_fields: List[Dict], ak: str
) -> tuple:
    """Deterministically pre-select the soul-aligned field from the pre-scored top-35.

    Rules:
      1. Take the top-5 by python_score as the approximate "match" set (these will
         be shown as career recommendations; the soul field should ideally differ).
      2. Among the remaining fields, find the highest-scoring one whose domain is in
         the AK's preferred soul domains (_AK_SOUL_DOMAINS).
      3. If none found in preferred domains, take the 6th-highest-scoring field overall.
      4. Returns (field_id, field_label, domain) or ("", "", "") if list is empty.

    This function is called BEFORE the LLM — it makes the soul field deterministic
    for the same chart regardless of how many times the LLM is invoked.
    """
    if not top_35_fields:
        return "", "", ""
    sorted_f = sorted(top_35_fields, key=lambda x: -x.get("python_score", 0))
    top5_ids = {r["field_id"] for r in sorted_f[:5]}
    preferred = _AK_SOUL_DOMAINS.get(ak, ["interdisciplinary", "arts"])
    # Search preferred domains first (in priority order)
    for domain in preferred:
        for r in sorted_f:
            if r["field_id"] not in top5_ids and r.get("domain") == domain:
                label = r.get("field_label", r["field_id"].replace("_", " ").title())
                return r["field_id"], label, domain
    # Fallback: 6th best field overall (regardless of domain)
    for r in sorted_f:
        if r["field_id"] not in top5_ids:
            label = r.get("field_label", r["field_id"].replace("_", " ").title())
            return r["field_id"], label, r.get("domain", "interdisciplinary")
    # Last resort: position 6 if it exists
    if len(sorted_f) > 5:
        r = sorted_f[5]
        label = r.get("field_label", r["field_id"].replace("_", " ").title())
        return r["field_id"], label, r.get("domain", "interdisciplinary")
    return "", "", ""

from .engine_io import _load_course_registry


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

    # D10 (Dashamsha) H10 occupants — already computed by engine_io.parse_json_payload
    # and stored in payload.d10_house_occupancy as {house_str: [planets]}
    d10_h10 = getattr(payload, "d10_house_occupancy", {}).get("10", [])

    # Neecha Bhanga planets
    nb = list(getattr(payload, "neecha_bhanga_planets", []) or [])

    lines = [
        "═══ BIRTH CHART FOR CAREER FIELD SELECTION ═══",
        f"Lagna: {payload.lagna_sign} | Lagna Lord: {payload.lagna_lord} | Gender: {getattr(payload,'gender','') or 'unspecified'}",
        f"AK  (soul karaka):   {payload.atmakaraka}",
        f"AmK (career karaka): {payload.amatyakaraka}",
        f"Karakamsha sign: {payload.karakamsha or 'not available'}",
        f"Active Mahadasha: {active_lord or 'not determined'}"
        + (f" | Antardasha: {antardasha_lord}" if antardasha_lord else ""),
        f"House lords: H2={hl.get('2','')} H4={hl.get('4','')} H5={hl.get('5','')} "
        f"H9={hl.get('9','')} H10={hl.get('10','')}",
        f"Planet positions: " + " ".join(f"{p}:H{h}" for p, h in sorted(ph.items())),
        f"Effective strengths (desc): {planet_eff_str}",
        f"Dignity highlights: {dig_str}",
        f"Nakshatra of key planets: {nak_str}",
        f"Retrograde planets: {', '.join(retro) or 'none'}",
        f"Vargottama planets: {', '.join(vargo) or 'none'}",
        f"Neecha Bhanga planets: {', '.join(nb) or 'none'}",
        f"Combust planets: {', '.join(combust) or 'none'}",
        f"D10 H10 occupants: {', '.join(d10_h10) or 'not available'}",
        f"Active yogas: {', '.join(yogas_all[:10]) or 'none'}",
        f"Student interests: {', '.join(getattr(payload,'interested_in',[])[:5]) or 'none'}",
        f"Already excels at: {', '.join(getattr(payload,'already_excel_at',[])[:3]) or 'none'}",
        f"Current age: {age:.1f}",
    ]

    # ── KP (Krishnamurti Paddhati) cusp data ─────────────────────────────────
    kp_cusps_raw = getattr(payload, "kp_cusps", {})
    kp_sigs_raw  = getattr(payload, "kp_significators", {})

    def _kp_cusp_str(h: str) -> str:
        c = kp_cusps_raw.get(h, {})
        sl  = c.get("sign_lord",  "?")
        stl = c.get("star_lord",  "?")
        sub = c.get("sub_lord",   "?")
        return f"sign={sl} star={stl} sub={sub}"

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
        f"KP H10 cusp (career):    {_kp_cusp_str('H10')}",
        f"KP H5  cusp (education): {_kp_cusp_str('H5')}",
        f"KP H9  cusp (higher ed): {_kp_cusp_str('H9')}",
        f"KP H10 primary significators  (L1/L2): {', '.join(h10_primary_sigs)   or 'none retrieved'}",
        f"KP H10 secondary significators(L3/L4): {', '.join(h10_secondary_sigs) or 'none retrieved'}",
    ]

    return "\n".join(lines)

def _strip_llm_fences(raw: str) -> str:
    """Strip markdown code fences and extract the JSON object from LLM output.

    Handles three common LLM response shapes:
      1. Raw JSON (already clean — Gemini with response_mime_type=application/json)
      2. ```json ... ``` fenced block
      3. JSON object embedded inside prose (extracted by brace-matching)
    """
    raw = raw.strip()

    # ── Case 2: fenced block ──────────────────────────────────────────────────
    if raw.startswith("```"):
        end = raw.rfind("```")
        inner = raw[3:end] if end > 3 else raw[3:]
        if inner.lstrip().startswith("json"):
            inner = inner.lstrip()[4:]
        return inner.strip()

    # ── Case 1: already starts with { ────────────────────────────────────────
    if raw.startswith("{"):
        return raw

    # ── Case 3: JSON object embedded in prose — find outermost { } ───────────
    start = raw.find("{")
    if start != -1:
        depth, end = 0, -1
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            return raw[start:end + 1]

    return raw

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
    """Call OpenAI Chat Completions and return raw response text."""
    import openai as _openai
    client = _openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model, max_completion_tokens=8192,
        temperature=0,   # deterministic
        seed=0,          # reproducible sampling
        response_format={"type": "json_object"},  # guaranteed clean JSON — no fence-stripping needed
        messages=[{"role": "user", "content": prompt}],
    )
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
    "gemini":    ("GEMINI_API_KEY",    "gemini-2.5-flash",          _call_gemini),
}

def call_llm_for_fields(
    payload: "NatalPayloadV2",
    eff_strengths: Dict[str, float],
    top_35_fields: List[Dict] = None,
    api_key: str = "",
    model: str = "",
    provider: str = "",
) -> List[Dict]:
    """Call an LLM to select final 20 from pre-scored top-35 fields.

    Pipeline-inversion (Task#3): Python has already scored all 188 fields;
    this function receives the pre-ranked top-35 and asks the LLM to:
      1. Select the best 20 using astrological synthesis
      2. Write a 100-word selection rationale
      3. Provide a <=20-word astrological reason per field (no planet_affinity — that
         comes from BRANCH_PLANET_AFFINITY in Python).

    Provider selection (first match wins):
      1. ``provider`` param if given  ("anthropic" | "openai" | "gemini")
      2. ``LLM_PROVIDER`` environment variable
      3. Auto-detect: whichever of ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY
         is set first (checked in that order)

    Returns
    -------
    List of up to 20 dicts: [{field_id, astrological_reason, llm_selection_rationale}, ...]
    Falls back to top-20 of top_35_fields (by python_score) on any error.
    """
    # 1. Resolve provider
    _prov = (provider or os.environ.get("LLM_PROVIDER", "")).strip().lower()
    if _prov and _prov not in _LLM_PROVIDERS:
        logger.warning(f"Unknown LLM provider '{_prov}' — auto-detecting.")
        _prov = ""
    if not _prov:
        for name, (env_var, _, _fn) in _LLM_PROVIDERS.items():
            if os.environ.get(env_var, ""):
                _prov = name
                break
    if not _prov:
        logger.warning(
            "No LLM provider detected. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or "
            "GEMINI_API_KEY (and optionally LLM_PROVIDER) — using fallback field set."
        )
        return _llm_fallback_from_top35(top_35_fields)

    env_var, default_model, caller_fn = _LLM_PROVIDERS[_prov]

    # 2. Resolve API key
    _key = api_key or os.environ.get(env_var, "")
    if not _key:
        logger.warning(f"{env_var} not set for provider '{_prov}' — using fallback.")
        return _llm_fallback_from_top35(top_35_fields)

    # 3. Resolve model
    _model = model or default_model

    # 4. Build prompt — pass pre-scored top-35 so LLM selects from known-good fields
    chart_summary = _build_chart_summary_for_llm(payload, eff_strengths)
    _top35_text = ""
    if top_35_fields:
        lines = []
        for row in top_35_fields:
            karakas = ", ".join(row.get("top_karakas", []))
            lines.append(
                f"  {row['rank']:2d}. {row['field_id']:<45} score={row['python_score']:5.1f}"
                f"  [{row['domain']}]  karakas: {karakas}"
            )
        _top35_text = "\n".join(lines)
    else:
        logger.warning(
            "top_35_fields is empty — course registry may not have loaded. "
            "Injecting full registry field_id list so LLM has valid IDs to choose from."
        )
        if _COURSE_REGISTRY:
            reg_lines = [f"  {fid}" for fid in sorted(_COURSE_REGISTRY.keys())]
            _top35_text = (
                "(pre-scored list not available — select from the following valid field_ids ONLY)\n"
                + "\n".join(reg_lines)
            )
        else:
            _top35_text = "(pre-scored list not available — select from full registry)"
    # Pre-select soul field deterministically — before LLM call
    ak = getattr(payload, "atmakaraka", "") or ""
    _pre_soul_fid, _pre_soul_label, _pre_soul_domain = _pick_soul_from_top35(top_35_fields, ak)
    if not _pre_soul_fid:
        logger.warning("_pick_soul_from_top35 returned empty — will rely on LLM soul selection.")
        _pre_soul_fid    = ""
        _pre_soul_label  = "not determined"
        _pre_soul_domain = "interdisciplinary"
    else:
        logger.info(f"Pre-selected soul field (deterministic): '{_pre_soul_fid}' "
                    f"(label='{_pre_soul_label}', domain='{_pre_soul_domain}', ak='{ak}')")

    prompt = _LLM_FIELD_PROMPT_TEMPLATE.format(
        chart_summary=chart_summary,
        top_35_fields=_top35_text,
        soul_field_id=_pre_soul_fid or "see_top35_list",
        soul_field_label=_pre_soul_label,
        soul_field_domain=_pre_soul_domain,
    )

    logger.info(f"Calling LLM provider='{_prov}' model='{_model}'")
    logger.debug(
        f"\n{'='*60}\nLLM INPUT PROMPT ({_prov}/{_model})\n{'='*60}\n"
        f"{prompt}\n{'='*60}"
    )
    try:
        raw_text = caller_fn(prompt, _key, _model)
        logger.debug(
            f"\n{'='*60}\nLLM RAW OUTPUT ({_prov}/{_model})\n{'='*60}\n"
            f"{raw_text}\n{'='*60}"
        )
        cleaned = _strip_llm_fences(raw_text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as je:
            logger.error(
                f"JSON parse failed ({_prov}): {je}\n"
                f"--- raw response (first 500 chars) ---\n{raw_text[:500]}\n"
                f"--- after fence-strip (first 500 chars) ---\n{cleaned[:500]}"
            )
            return _llm_fallback_from_top35(top_35_fields)

        # ── New format: top_5_match + soul_aligned ───────────────────────────
        astro_overview  = data.get("astrologer_overview", data.get("selection_rationale", ""))
        parent_overview = data.get("parent_overview",     data.get("parent_summary", ""))

        top5_raw    = data.get("top_5_match", [])
        soul_raw    = data.get("soul_aligned", {})

        # Also handle legacy format (selected_fields) as fallback
        legacy_raw  = data.get("selected_fields", data.get("fields", []))

        if top5_raw or soul_raw:
            # New format path
            result_fields: List[Dict] = []
            for entry in top5_raw:
                result_fields.append({
                    "field_id":              str(entry.get("field_id","")).strip().lower().replace(" ","_"),
                    "astrological_reason":   entry.get("astrologer_justification", entry.get("astrological_reason","")),
                    "parent_reason":         entry.get("parent_explanation", entry.get("parent_reason","")),
                    "llm_rank":              entry.get("rank", len(result_fields)+1),
                    "llm_group":             "match",
                    "llm_selection_rationale": astro_overview,
                    "llm_parent_summary":      parent_overview,
                })
            if soul_raw or _pre_soul_fid:
                # Enforce the deterministically pre-selected field_id.
                # The LLM provides justification text; we override its field choice.
                llm_soul_fid = str(soul_raw.get("field_id","")).strip().lower().replace(" ","_") if soul_raw else ""
                enforced_fid = _pre_soul_fid if _pre_soul_fid else llm_soul_fid
                if llm_soul_fid and llm_soul_fid != enforced_fid:
                    logger.warning(
                        f"LLM chose soul field '{llm_soul_fid}' but pre-selected is "
                        f"'{enforced_fid}' — overriding to keep deterministic soul selection."
                    )
                result_fields.append({
                    "field_id":              enforced_fid,
                    "astrological_reason":   (soul_raw or {}).get("astrologer_justification",
                                              (soul_raw or {}).get("astrological_reason", "")),
                    "parent_reason":         (soul_raw or {}).get("parent_explanation",
                                              (soul_raw or {}).get("parent_reason", "")),
                    "llm_rank":              6,
                    "llm_group":             "soul",
                    "llm_selection_rationale": astro_overview,
                    "llm_parent_summary":      parent_overview,
                })
        else:
            # Legacy format fallback
            result_fields = []
            for i, entry in enumerate(legacy_raw):
                result_fields.append({
                    "field_id":              str(entry.get("field_id","")).strip().lower().replace(" ","_"),
                    "astrological_reason":   entry.get("astrological_reason",""),
                    "parent_reason":         entry.get("parent_reason",""),
                    "llm_rank":              i+1,
                    "llm_group":             "match" if i < 5 else "extended",
                    "llm_selection_rationale": astro_overview,
                    "llm_parent_summary":      parent_overview,
                })

        logger.info(f"LLM returned {len(result_fields)} field selections (new format).")
        validated = _validate_llm_fields(result_fields, top_35_fields=top_35_fields)

        # ── Defensive re-apply: _validate_llm_fields may run from a stale .pyc
        # that strips llm_group / parent_reason.  Re-stamp directly from raw JSON.
        # Defensive re-apply: use _pre_soul_fid (deterministic) not LLM's field choice.
        _soul_stamp_fid = _pre_soul_fid if _pre_soul_fid else (
            str(soul_raw.get("field_id","")).strip().lower().replace(" ","_") if soul_raw else ""
        )
        if _soul_stamp_fid:
            for r in validated:
                if r["field_id"] == _soul_stamp_fid:
                    r["llm_group"]           = "soul"
                    r["llm_rank"]            = 6
                    r["parent_reason"]       = (soul_raw or {}).get("parent_explanation",
                                                (soul_raw or {}).get("parent_reason", r.get("parent_reason","")))
                    r["astrological_reason"] = (soul_raw or {}).get("astrologer_justification",
                                                (soul_raw or {}).get("astrological_reason", r.get("astrological_reason","")))
                    r["llm_selection_rationale"] = astro_overview
                    r["llm_parent_summary"]      = parent_overview
                    break
        for entry in top5_raw:
            fid = str(entry.get("field_id","")).strip().lower().replace(" ","_")
            pr  = entry.get("parent_explanation", entry.get("parent_reason",""))
            ar  = entry.get("astrologer_justification", entry.get("astrological_reason",""))
            for r in validated:
                if r["field_id"] == fid and r.get("llm_group","match") != "soul":
                    if pr: r["parent_reason"]       = pr
                    if ar: r["astrological_reason"] = ar
                    r["llm_selection_rationale"] = astro_overview
                    r["llm_parent_summary"]      = parent_overview
                    break

        return validated
    except Exception as exc:
        logger.error(f"LLM call failed ({_prov}/{_model}): {exc}. Using fallback.")
        return _llm_fallback_from_top35(top_35_fields)


def _fuzzy_match_field_id(fid: str) -> Optional[str]:
    """Try to find the closest registry key for a hallucinated field_id.

    Strategy (in order):
      1. Exact match (already tried by caller — included for completeness).
      2. Registry key starts-with or ends-with all tokens from fid.
      3. Token overlap: fraction of fid tokens present in registry key tokens.
         Accept if overlap >= 0.6 AND the matched key shares at least 2 tokens.
    Returns canonical field_id string or None.
    """
    if not _COURSE_REGISTRY:
        return None
    if fid in _COURSE_REGISTRY:
        return fid
    fid_tokens = set(fid.split("_"))
    best_key: Optional[str] = None
    best_score = 0.0
    for key in _COURSE_REGISTRY:
        key_tokens = set(key.split("_"))
        common = fid_tokens & key_tokens
        if len(common) < 2:
            continue
        score = len(common) / max(len(fid_tokens), len(key_tokens))
        if score > best_score:
            best_score = score
            best_key   = key
    if best_key and best_score >= 0.6:
        return best_key
    return None


def _validate_llm_fields(fields_raw: List[Dict], top_35_fields: List[Dict] = None) -> List[Dict]:
    """Validate LLM-returned field selections (pipeline-inversion format).

    New format: LLM returns {field_id, astrological_reason} only — no planet_affinity
    (that comes from BRANCH_PLANET_AFFINITY in Python).
    • Resolves field_id against _COURSE_REGISTRY for canonical label/domain.
    • Fuzzy-matches near-miss field_ids before rejecting them.
    • Warns and skips hallucinated field_ids (not in registry).
    • Ensures unique field_ids; caps at 20 entries.
    • Pads to 20 from top_35_fields pre-scored list if LLM returned fewer.
    """
    seen_ids: set = set()
    validated: List[Dict] = []

    for f in fields_raw:
        fid           = str(f.get("field_id", "")).strip().lower().replace(" ", "_")
        reason        = str(f.get("astrological_reason", "")).strip()
        parent_reason = str(f.get("parent_reason", "")).strip()
        llm_group     = f.get("llm_group", "match")
        llm_rank      = f.get("llm_rank", len(validated)+1)
        llm_rationale = f.get("llm_selection_rationale", "")
        llm_ps        = f.get("llm_parent_summary", "")

        if not fid or fid in seen_ids:
            continue

        # ── Registry lookup with fuzzy fallback ──────────────────────────────
        reg_entry = _COURSE_REGISTRY.get(fid)
        if not reg_entry:
            fuzzy = _fuzzy_match_field_id(fid)
            if fuzzy:
                logger.info(f"Fuzzy-matched LLM field_id '{fid}' → '{fuzzy}'")
                fid = fuzzy
                reg_entry = _COURSE_REGISTRY.get(fid)
        if not reg_entry:
            logger.warning(f"LLM returned field_id '{fid}' not in registry — skipping.")
            continue

        if fid in seen_ids:
            continue
        seen_ids.add(fid)

        label = reg_entry.get("label", fid.replace("_", " ").title())
        dom   = reg_entry.get("domain", "interdisciplinary").strip().lower()
        if dom not in _VALID_DOMAINS:
            dom = "interdisciplinary"

        validated.append({
            "field_id":               fid,
            "field_label":            label,
            "domain":                 dom,
            "astrological_reason":    reason,
            "parent_reason":          parent_reason,
            "llm_group":              llm_group,
            "llm_rank":               llm_rank,
            "llm_selection_rationale": llm_rationale,
            "llm_parent_summary":      llm_ps,
            "registry_description":   reg_entry.get("description", ""),
            "registry_niche":         reg_entry.get("niche", ""),
        })

        if len(validated) == 20:
            break

    # Pad to 20 from pre-scored top_35 if LLM returned fewer
    if len(validated) < 20 and top_35_fields:
        for row in top_35_fields:
            if len(validated) >= 20:
                break
            fid = row.get("field_id","")
            if fid and fid not in seen_ids:
                seen_ids.add(fid)
                reg_entry = _COURSE_REGISTRY.get(fid, {})
                validated.append({
                    "field_id":            fid,
                    "field_label":         row.get("field_label", fid.replace("_"," ").title()),
                    "domain":              row.get("domain","interdisciplinary"),
                    "astrological_reason": "",
                    "registry_description": reg_entry.get("description",""),
                    "registry_niche":       reg_entry.get("niche",""),
                })

    return validated


def _llm_fallback_from_top35(top_35_fields: List[Dict] = None) -> List[Dict]:
    """Return top-20 from pre-scored top-35 as selection fallback when LLM fails."""
    if top_35_fields:
        result = []
        for row in sorted(top_35_fields, key=lambda x: -x.get("python_score", 0))[:20]:
            fid = row.get("field_id", "")
            if not fid:
                continue
            reg_entry = _COURSE_REGISTRY.get(fid, {})
            result.append({
                "field_id":                fid,
                "field_label":             row.get("field_label", reg_entry.get("label", fid.replace("_", " ").title())),
                "domain":                  row.get("domain", reg_entry.get("domain", "interdisciplinary")),
                "astrological_reason":     "",
                "parent_reason":           "",
                "llm_group":               "match",
                "llm_rank":                len(result) + 1,
                "llm_selection_rationale": "",
                "llm_parent_summary":      "",
                "registry_description":    reg_entry.get("description", ""),
                "registry_niche":          reg_entry.get("niche", ""),
            })
        return result
    return []
