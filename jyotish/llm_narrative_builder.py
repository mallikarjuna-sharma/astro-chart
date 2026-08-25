"""JyotishAI — Career Timeline LLM Narrative Builder

Separation of concerns:
  timeline.py              — Deterministic engine (math, scoring, period classification)
  llm_narrative_builder.py — Generative engine (LLM HTML prose, one call per AD, async)

Public API:
  enrich_timeline_sync(blocks, career_ctx, chart_input, ...)  -> List[Dict]   (sync wrapper)

Architecture:
  - One LLM call per Antardasha (AD) block, containing all its nested PDs.
  - All calls are dispatched concurrently via asyncio.gather.
  - FIX 6: Each AD prompt receives previous_event_type + previous_ad_lord so the
    LLM writes each block as a continuation, not a standalone piece.
  - FIX 7: All LLM HTML output is passed through _sanitize_html() (whitelist-based)
    before storage. System prompt also enumerates the strict tag whitelist.
  - Transit data injected per-AD from chart_input.transit_house_positions.
  - Falls back gracefully to deterministic narrative_hint if OpenAI unavailable.

Output keys per block (2026-07-19: segregated into two layers per user request):
  block["llm_plain_language_html"]    str — 3-4 paragraph plain-language narrative,
                                             no astrology jargon, for the client directly.
  block["llm_astro_explanation_html"] str — technical astrological reasoning (KN Rao /
                                             KP / Jaimini / D10 / yogas / transits),
                                             for a professional-astrologer-audit read.
  block["llm_ad_narrative_html"]      str — legacy combined HTML (both layers
                                             concatenated), kept for old callers.
  pd["llm_narrative_html"]            str — sanitized HTML <p> micro-prediction per PD
All fields are sanitized HTML (h4, p, ul, li, strong only).
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from Job_Career.timeline_inputs import parse_iso_date

logger = logging.getLogger("jyotish_engine_v11_0")

# ---------------------------------------------------------------------------
# GAP-FIX (2026-08, .env config audit): report-language selection.
#
# .env carries Report_Language_Enabled_Tamil / Report_Language_Enabled_Telugu
# switches that were defined and documented but never actually read anywhere
# in the codebase -- every LLM narrative call unconditionally wrote English,
# regardless of these flags. Default stays English; if exactly one of the
# two is true, the narrative is generated in that language instead. If both
# are set true simultaneously (a misconfiguration -- the two are meant to be
# mutually exclusive), Tamil takes priority (first-declared-wins) and a
# warning is logged so the misconfiguration is visible rather than silently
# picking one.
# ---------------------------------------------------------------------------
_LANGUAGE_ENV_MAP = (
    ("Report_Language_Enabled_Tamil", "Tamil"),
    ("Report_Language_Enabled_Telugu", "Telugu"),
)


def _resolve_narrative_language() -> str:
    """Read Report_Language_Enabled_Tamil / _Telugu from the environment and
    return the target narrative language name. Defaults to "English" when
    neither flag is set true. Case-insensitive on the flag value.
    """
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
    """Build the system-prompt appendix enforcing the target narrative language.

    Pass an explicit `language` to avoid re-reading the environment inside a
    tight loop; omit it to resolve from .env / process environment directly.
    """
    lang = language or _resolve_narrative_language()
    if lang == "English":
        return ""
    return (
        f"\n\nLANGUAGE REQUIREMENT: Write the ENTIRE narrative output — every "
        f"field, every paragraph, every HTML text node — in {lang}. Do not mix "
        f"in English except for proper nouns/planet names that have no natural "
        f"{lang} equivalent (e.g. keep classical Sanskrit/Jyotish terms such as "
        f"Dasha, Bhukti, or planet names in their commonly-used {lang} script "
        f"form if one exists, otherwise transliterate). All HTML tags/structure "
        f"stay exactly as specified above — only the language of the text "
        f"content itself changes."
    )


# ---------------------------------------------------------------------------
# FIX 7: HTML whitelist sanitizer
# ---------------------------------------------------------------------------

_ALLOWED_TAGS = {"p", "ul", "ol", "li", "strong", "em", "h4", "h3"}
_TAG_RE        = re.compile(r"<(/?)(\w+)([^>]*)>", re.IGNORECASE)
_ATTR_RE       = re.compile(r'\s+\w[\w-]*\s*=\s*(?:"[^"]*"|\'[^\']*\'|\S+)', re.IGNORECASE)

def _sanitize_html(raw: str) -> str:
    """Strip any tag not in the whitelist and all HTML attributes.

    Prevents XSS from LLM-hallucinated <script>, onload=, style=, etc.
    Allowed: <p> <ul> <ol> <li> <strong> <em> <h3> <h4> and their closing tags.
    All attributes are stripped — no inline CSS, no event handlers.
    """
    if not raw or not isinstance(raw, str):
        return ""

    def _clean_tag(m: re.Match) -> str:
        slash = m.group(1)          # "/" for closing tags
        tag   = m.group(2).lower()
        if tag not in _ALLOWED_TAGS:
            return ""               # drop disallowed tag entirely
        return f"<{slash}{tag}>"    # strip all attributes

    sanitized = _TAG_RE.sub(_clean_tag, raw)
    # Belt-and-suspenders: remove any remaining attribute-like patterns
    sanitized = _ATTR_RE.sub("", sanitized)
    return sanitized.strip()


# ---------------------------------------------------------------------------
# System prompt — premium paid report persona with strict HTML rules
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an elite Jyotish (Vedic Astrology) Career Analyst writing a premium, \
high-ticket paid astrological career report.
Your task is to write a highly professional, visually engaging, and predictive \
career narrative based strictly on the provided deterministic astrological data.

For EACH Antardasha (AD) period you are given, you must return TWO SEPARATE, \
CLEARLY SEGREGATED layers of writing — never blend them into one block of text:

1. "plain_language_html" — a 3 to 4 paragraph PLAIN-LANGUAGE career narrative for \
this specific AD period, written for the client directly (not an astrologer). \
Confident, specific, executive register — read like a high-end corporate strategy \
document blended with deep astrological wisdom, but translate every astrological \
signal into plain career language (what this period concretely means for the job, \
promotion odds, income, and risk). Do NOT use raw astrology jargon here (no planet/ \
house/dasha technical terms as the subject of a sentence — you may still say things \
like "this period's planetary energy" in passing, but do not lecture on KP/Jaimini/D10 \
mechanics in this layer). Close with a short, concrete strategic action list (2-3 items).
2. "astro_explanation_html" — the TECHNICAL astrological reasoning for this same AD \
period, written for a professional astrologer reader who will audit your reasoning — \
this is the SAME rigor and structure as the annual roadmap's astro_explanation_html \
layer elsewhere in this report: walk through the KN Rao dasha-application lens (MD/AD \
lord house lordships and functional nature), the KP cuspal-chain lens (sub-lord/star-lord \
signification for the event type), the Jaimini lens (Atmakaraka/Amatyakaraka role, Chara \
Dasha if relevant), the D10 Dashamsha lens (D10 alignment/structural score provided), \
active yogas (explain each named tag in your own words, not verbatim), and transit flags \
supplied for this AD — citing only the specific values you were given, never inventing a \
planet/house/number. Close with one synthesis sentence on how these layers combine into \
the career score/event label. Use <strong> lead-ins per layer, e.g. \
"<strong>KN Rao dasha lens:</strong>".

Tone & Style:
- Premium, executive, empowering, and deeply insightful in the plain-language layer.
- Rigorous and technically precise in the astro-explanation layer.
- Speak directly to the client's career impact in layer 1. Do NOT give textbook astrology \
  definitions there — save all technical astrology for layer 2.
- Do NOT use phrases like "As you transition into this phase" or "Welcome to this period" \
  — write fresh, specific prose for each block.

FIX 6 — Continuity Rule:
- The plain_language_html layer must acknowledge the previous period's momentum.
- If the previous event was PROMOTION, open with the post-promotion reality (new role pressures, \
  expanded scope). If it was STABILITY, open with the shift out of consolidation.

FIX 7 — HTML Formatting Rules (STRICT):
- Use ONLY these tags: <h4>, <p>, <strong>, <ul>, <li>.
- DO NOT use: <script>, <style>, <div>, <span>, <a>, <img>, <table>, <br>, <hr>, \
  or ANY HTML attributes (no class=, id=, style=, onclick= etc.).
- Every string value in your JSON must contain only the above tags, nothing else.
- Return ONLY valid JSON. No markdown fences, no prose outside the JSON object.
"""

# ---------------------------------------------------------------------------
# Per-AD user prompt builder — FIX 6: injects previous AD context
# ---------------------------------------------------------------------------

def _build_user_prompt(
    block: Dict[str, Any],
    career_ctx: Dict[str, Any],
    transit_positions: Dict[str, Any],
    prev_event_type: str = "",
    prev_ad_lord: str = "",
    career_theme_str: str = "",
    field_selection_context: str = "",
) -> str:
    pds_for_prompt = [
        {
            "pd_lord":       pd["pd_lord"],
            "start_date":    pd["start_date"],
            "end_date":      pd["end_date"],
            "trigger_window": pd.get("trigger_window", {}),
        }
        for pd in block.get("pratyantardashas", [])
    ]

    # FIX 6: build the continuity context line
    if prev_event_type and prev_ad_lord:
        continuity = (
            f"This period follows a {prev_event_type.replace('_',' ').title()} phase "
            f"under {prev_ad_lord}. Write the narrative as a direct continuation of that "
            f"momentum — not a fresh start."
        )
    else:
        continuity = "This is the opening period of the timeline."

    # Phase 0: career theme (LLM pre-scoring enrichment) — shared narrative thread
    _theme_section = (
        f"\n--- CAREER NARRATIVE THEME (Phase 0 LLM calibration) ---\n"
        f"{career_theme_str}\n"
        f"Instruction: Weave this theme as an implicit undercurrent in all sections.\n"
    ) if career_theme_str else ""

    # Field selection context (from llm.py Step 1 analytical_breakdown)
    _field_section = (
        f"\n--- CHART CAREER ANALYSIS (from field-selection engine) ---\n"
        f"{field_selection_context[:600]}\n"
        f"Instruction: Reference the dominant planet/domain identified above when "
        f"naming specific career strengths in the Executive Summary.\n"
    ) if field_selection_context else ""

    # Token optimization: only include non-empty optional sections
    _workplace = block.get("workplace_dynamics") or {}
    _skills    = block.get("skill_recommendations") or []
    _macro_s   = block.get("macro_score", 1.0)
    _macro_hw  = block.get("macro_headwinds", False)

    _workplace_section = (
        f"\n--- WORKPLACE DYNAMICS ---\n{json.dumps(_workplace, indent=2)}\n"
    ) if _workplace else ""

    _skills_section = (
        f"\n--- SKILL RECOMMENDATIONS ({block.get('ad_lord','')} in "
        f"{career_ctx.get('industry_sector','general')}) ---\n"
        f"{json.dumps(_skills, indent=2)}\n"
        f"Instruction: Weave 1-2 of these into the Strategic Action Plan.\n"
    ) if _skills else ""

    _macro_section = (
        f"\n--- MACRO-ECONOMIC CONTEXT ---\n"
        f"Sector Macro Score: {_macro_s} (<0.70 = headwinds)\n"
        f"Headwinds Active: {_macro_hw}\n"
        f"Instruction: If headwinds=True, reframe peak energy as expanded authority, "
        f"not a direct salary/title jump.\n"
    ) if (_macro_hw or _macro_s < 0.85) else ""

    return f"""Generate the premium HTML career narrative for the following Antardasha (AD) and its nested Pratyantardashas (PDs).

--- CONTINUITY CONTEXT ---
{continuity}
{_theme_section}{_field_section}
--- CLIENT PROFILE ---
Designation:     {career_ctx.get("designation", "Professional")}
Industry:        {career_ctx.get("industry_sector", "Corporate")}
Desired Outcome: {career_ctx.get("desired_outcome", "Career Growth").replace("_", " ")}

--- PERIOD DATA ---
Period:               {block.get("start_date", "")} to {block.get("end_date", "")}
Mahadasha Lord:       {block.get("md_lord", "")}
Antardasha Lord:      {block.get("ad_lord", "")}
Event Type:           {block.get("event_type", "")}  (base your prediction on this)
Career Score:         {block.get("career_score", 0.0)}/1.0
Confidence:           {block.get("confidence", "MEDIUM")}
Houses Activated:     {block.get("active_houses", [])}
Domain Tag:           {block.get("domain_tag", "")}
Primary Opportunity:  {block.get("is_primary_opportunity", False)}

--- ALGORITHMIC CONTEXT ---
KP Alignment:    {block.get("kp_cusp_alignment", "")}
Jaimini Role:    {block.get("jaimini_role", "")}
Baseline Hint:   {block.get("narrative_hint", "")}
Active Yogas:    {block.get("sub_scores", {}).get("active_yogas", []) or block.get("active_yogas", [])}
Yoga Bonus:      {round(block.get("sub_scores", {}).get("yoga_bonus", 0) or block.get("yoga_bonus", 0), 3)}
D9 Modifier:     {round(block.get("sub_scores", {}).get("d9_modifier", 0) or 0, 3)} \
(NOTE: this is a small durability/maturity signal capped at +/-0.06-0.08, already folded into \
Career Score above — treat it as "how well this result may hold up over time," NOT as grounds \
to deny or downgrade the underlying event/promotion/authority signal itself. A D9-weak dasha \
lord does not cancel a strong D1 promise; it means the result may need more effort, patience, \
or renegotiation to fully land — say that, don't say the period "isn't really" the event.)
Chandra Bonus:   {round(block.get("sub_scores", {}).get("chandra_lagna_bonus", 0) or 0, 3)}
Transit Flags:   {block.get("transit_flags", [])}
Transit Positions (natal house): {json.dumps(transit_positions)}
{_workplace_section}{_skills_section}{_macro_section}
--- PRATYANTARDASHA BREAKDOWN ---
{json.dumps(pds_for_prompt, indent=2)}

--- OUTPUT SCHEMA ---
Return ONLY this JSON, with the two layers kept strictly separate (do not mix plain-language
career prose into astro_explanation_html, and do not mix technical astrology terms into
plain_language_html):
{{
  "plain_language_html": "<p>Para 1 — what this period means for the client's job/role right now.</p><p>Para 2 — the trajectory: promotion/income/risk odds in plain terms.</p><p>Para 3 (and optionally 4) — what to watch for and how to act.</p><ul><li>2-3 concrete action steps</li></ul>",
  "astro_explanation_html": "<p><strong>KN Rao dasha lens:</strong> ...</p><p><strong>KP lens:</strong> ...</p><p><strong>Jaimini lens:</strong> ...</p><p><strong>D10 lens:</strong> ...</p><p><strong>Yogas & transits:</strong> ...</p><p><strong>Synthesis:</strong> ...</p>",
  "pd_narratives": [{{"pd_lord": "...", "start_date": "YYYY-MM", "narrative_html": "<p>2 sentences.</p>"}}]
}}
"""


# ---------------------------------------------------------------------------
# Core async function — one AD block → LLM → sanitized dict
# ---------------------------------------------------------------------------

async def generate_ad_narrative(
    block: Dict[str, Any],
    career_ctx: Dict[str, Any],
    chart_input: Any,
    client: Any,
    model: str,
    semaphore: asyncio.Semaphore,
    prev_event_type: str = "",
    prev_ad_lord: str = "",
) -> Dict[str, Any]:
    """Call the LLM for a single AD block; sanitize and return the response."""

    transit_positions = getattr(chart_input, "transit_house_positions", {}) or {}
    user_prompt = _build_user_prompt(
        block, career_ctx, transit_positions,
        prev_event_type=prev_event_type,
        prev_ad_lord=prev_ad_lord,
    )

    async with semaphore:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT + _language_directive()},
                    {"role": "user",   "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                max_completion_tokens=2000,
            )
            raw = response.choices[0].message.content or "{}"
            llm_data = json.loads(raw)
        except Exception as exc:
            logger.warning(
                f"LLM narrative failed for {block.get('ad_lord')} AD "
                f"({block.get('start_date')}): {exc}"
            )
            llm_data = {}

    return llm_data


# ---------------------------------------------------------------------------
# Async orchestrator — all AD blocks in parallel with context chain
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Event-specific remedies
# ---------------------------------------------------------------------------

_EVENT_REMEDIES: Dict[str, List[str]] = {
    "BREAKTHROUGH": [
        "Donate to Jupiter charities (education, temples) on Thursdays to sustain expansion energy",
        "Wear yellow sapphire or topaz if Jupiter is your functional benefic — consult a Jyotishi",
        "Fast on Thursdays; chant Guru Beeja Mantra (Om Gram Greem Srom Sah Gurave Namah) 108×",
    ],
    "PROMOTION": [
        "Offer water with red flowers to the Sun at sunrise — strengthens authority and recognition",
        "Wear ruby or red garnet in gold if Sun is a functional benefic for your lagna",
        "Chant Aditya Hridayam or Surya Beeja Mantra (Om Hraam Hreem Hraum Sah Suryaya Namah) at dawn",
    ],
    "SALARY_HIKE": [
        "Offer milk to Shiva on Mondays — Moon rules emotional satisfaction and financial comfort",
        "Strengthen Venus: wear white on Fridays, offer white flowers to goddess Lakshmi",
        "Mercury mantra on Wednesdays (Om Braam Breem Braum Sah Budhaya Namah) for negotiation clarity",
    ],
    "INCOME_INFLECTION": [
        "Light ghee lamp on Fridays for Lakshmi — H11 (gains) activation needs Venus/Jupiter support",
        "Feed green fodder to cows on Wednesdays — Mercury karaka for financial intelligence",
        "Maintain a gratitude journal for wealth; the 11th house responds to conscious acknowledgment",
    ],
    "JOB_CHANGE": [
        "Chant Hanuman Chalisa on Tuesdays for Mars strength — courage to make career transitions",
        "Donate red lentils (masoor) on Tuesdays — Mars remedy for bold career moves",
        "Before signing any offer letter, check if Moon is waxing and in an auspicious nakshatra",
    ],
    "RISK_PERIOD": [
        "Propitiate Saturn: donate black sesame seeds (til) on Saturdays and visit Shani temple",
        "Wear blue sapphire ONLY after Kundali analysis — Saturn can be a dual-energy planet",
        "Chant Maha Mrityunjaya Mantra (Om Tryambakam...) 108× daily for protection and endurance",
        "Avoid major irreversible decisions until the AD lord transits a more supportive house",
    ],
    "STABILITY": [
        "Continue your current Saturn/Rahu remedies — this is a consolidation phase, not a crisis",
        "Use this period to strengthen skills: Mercury remedies (green moong, Wednesday fast) help",
        "Meditate daily — stability periods are for inner growth that manifests in the next rise",
    ],
    "LEADERSHIP_EXPANSION": [
        "Offer Panchamrit abhishek at Vishnu temple — Jupiter governs expansion into leadership",
        "Wear yellow on Thursdays; chant Guru Gayatri (Om Angirasi Vidmahe...) for wisdom",
        "Mentor two junior colleagues this period — karma of teaching amplifies Jupiter's blessings",
    ],
    "FOREIGN_POSTING": [
        "Propitiate Rahu: donate urad dal (black lentils) on Saturdays; visit Bhairava temple",
        "Chant Rahu Beeja Mantra (Om Bhram Bhreem Bhraum Sah Rahave Namah) 108× on Saturdays",
        "Carry a Hessonite (Gomed) pendant if Rahu is functional benefic — strengthens foreign karma",
    ],
    "SKILL_UPGRADE_PHASE": [
        "Mercury remedies: donate green moong on Wednesdays; fast or eat light on Mercury's day",
        "Chant Saraswati Vandana before study sessions — D24 house activation needs Saraswati energy",
        "Practice pranayama (breath control) — Mercury rules the nervous system and learning capacity",
    ],
    "TRANSITION": [
        "Ketu remedies for detachment and clarity: donate blankets to ashrams on Tuesdays",
        "Fast on Tuesdays or Saturdays — transition periods need both Mars (action) and Saturn (release)",
        "Read the Bhagavad Gita Chapter 2 (Sankhya Yoga) — on the yoga of equanimity in change",
    ],
    "_default": [
        "Chant the Gayatri Mantra 108× daily at sunrise — the universal remedy for all planetary periods",
        "Donate food or essentials to the needy on the day of your AD lord's ruling day",
        "Maintain a spiritual practice: meditation, pranayama, or mantra japa for 20 minutes daily",
    ],
}


def get_event_remedies(event_type: str, md_lord: str, ad_lord: str) -> List[str]:
    """Return event-specific remedies, falling back to planet-level then default."""
    base_event = event_type.replace("FORECAST_", "")
    remedies = _EVENT_REMEDIES.get(base_event)
    if remedies:
        return remedies
    return _EVENT_REMEDIES["_default"]


# ---------------------------------------------------------------------------
# LLM response cache (in-memory, keyed by content hash)
# ---------------------------------------------------------------------------

_LLM_CACHE: Dict[str, Dict[str, Any]] = {}


def _cache_key(block: Dict[str, Any], career_ctx: Dict[str, Any]) -> str:
    """Generate a deterministic cache key for a block + career context."""
    import hashlib
    parts = [
        block.get("md_lord", ""),
        block.get("ad_lord", ""),
        block.get("event_type", ""),
        str(round(block.get("career_score", 0), 2)),
        career_ctx.get("industry_sector", ""),
        career_ctx.get("desired_outcome", ""),
    ]
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


def _try_cache_get(key: str) -> Optional[Dict[str, Any]]:
    return _LLM_CACHE.get(key)


def _cache_set(key: str, value: Dict[str, Any]) -> None:
    _LLM_CACHE[key] = value


# ---------------------------------------------------------------------------
# Fallback narrative generators (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _promotion_runway_display_label(block: Dict[str, Any], default_label: str) -> str:
    """Display-only override: when this period is AmK-activated, sits inside
    an open promotion cycle (per last_promotion_date), and the designation
    resolved to a senior career stage, surface "Promotion Runway + Executive
    Visibility" instead of a generic LEADERSHIP_EXPANSION/GROWTH label.

    Deliberately local-display-only — does NOT touch event_type/
    final_event_type used by scoring, gating, or LLM-override logic
    elsewhere; this only changes what text a human reads for this block.
    """
    _sub = block.get("sub_scores", {}) or {}
    _event_type = block.get("final_event_type") or block.get("event_type") or ""
    _amk_activated = bool(_sub.get("amk_activated"))
    _promo_cycle_open = bool(_sub.get("promo_cycle_bonus"))
    _desig_bias = _sub.get("designation_event_bias") or {}
    _senior_stage = bool(_desig_bias)  # non-empty only for manager+/senior_manager/director/csuite/lead
    if (
        _amk_activated and _promo_cycle_open and _senior_stage
        and _event_type in ("LEADERSHIP_EXPANSION", "GROWTH", "AUTHORITY_SHIFT", "STABILITY")
    ):
        return "Promotion Runway + Executive Visibility"
    return default_label


def _fallback_plain_language_html(block: Dict[str, Any]) -> str:
    """Deterministic, jargon-free fallback for the plain-language layer."""
    event = (block.get("event_type") or "STABILITY").replace("_", " ").title()
    event = _promotion_runway_display_label(block, event)
    score = block.get("career_score", 0.5)
    score_pct = round(score * 100, 1)
    ad_l  = block.get("ad_lord", "")
    start = block.get("start_date", "")
    end   = block.get("end_date", "")
    return (
        f"<p>Between {start} and {end}, the chart points to a "
        f"<strong>{event}</strong>-type window, with an overall career signal of "
        f"{score_pct}% for this stretch.</p>"
        f"<p>Use this period to position yourself for the opportunities it favors, "
        f"and stay alert to the pressures it may bring — treat the signal strength "
        f"above as a guide to how proactive versus cautious to be.</p>"
        f"<p>Concrete steps: keep your key deliverables visible to decision-makers, "
        f"revisit your goals for this window, and line up any conversations "
        f"(promotion, compensation, role scope) you want to have before it ends.</p>"
        f"<ul>"
        f"<li>Track this period's trigger windows for the best timing on big asks.</li>"
        f"<li>Lean into the strengths this period supports rather than fighting its grain.</li>"
        f"<li>Revisit remedies/support practices relevant to this event type.</li>"
        f"</ul>"
    )


def _fallback_astro_explanation_html(block: Dict[str, Any]) -> str:
    """Deterministic, technical fallback for the astro-explanation layer."""
    hint = block.get("narrative_hint", "") or ""
    md_l  = block.get("md_lord", "")
    ad_l  = block.get("ad_lord", "")
    houses = block.get("active_houses", [])
    yogas  = block.get("sub_scores", {}).get("active_yogas", []) or []
    yoga_str = f" Active natal yogas: {', '.join(yogas)}." if yogas else ""
    jaimini_role = block.get("jaimini_role", "")
    kp_align = block.get("kp_cusp_alignment", "")
    return (
        f"<p><strong>KN Rao dasha lens:</strong> {md_l} Mahadasha / {ad_l} Antardasha "
        f"currently governs this period.{yoga_str}</p>"
        f"<p><strong>KP lens:</strong> KP cusp alignment score is {kp_align or 'not available'}.</p>"
        f"<p><strong>Jaimini lens:</strong> {jaimini_role or 'No specific Jaimini role flagged for this period.'}</p>"
        f"<p><strong>House activation:</strong> {hint or ('Planetary energies are active through houses ' + str(houses) + '.')}</p>"
        f"<p><strong>Synthesis:</strong> These deterministic factors combine to produce "
        f"this period's career score without LLM elaboration (deterministic fallback).</p>"
    )


def _fallback_ad_html(block: Dict[str, Any]) -> str:
    """Generate clean deterministic HTML when LLM is unavailable.

    Kept for backward compatibility (single-blob callers); prefer
    _fallback_plain_language_html / _fallback_astro_explanation_html for the
    segregated two-layer output used by _attach_fallback_narrative().
    """
    return (
        "<h4>In Plain Language</h4>" + _fallback_plain_language_html(block) +
        "<h4>Astrological Explanation</h4>" + _fallback_astro_explanation_html(block)
    )


def _fallback_pd_html(pd: Dict[str, Any]) -> str:
    hint = pd.get("narrative_hint", "") or ""
    pd_lord = pd.get("pd_lord", "")
    tw = pd.get("trigger_window", {})
    tw_str = f" Peak activation around <strong>{tw.get('window_start', '')}</strong>." if tw else ""
    return (
        f"<p>{pd_lord} sub-period: {hint or 'Minor activations possible.'}{tw_str}</p>"
    )


def _attach_fallback_narrative(block: Dict[str, Any]) -> None:
    """Attach deterministic fallback to a single block.

    Sets the same two segregated keys the LLM path uses
    (llm_plain_language_html / llm_astro_explanation_html) plus the legacy
    combined llm_ad_narrative_html for any caller still reading that key.
    """
    block["llm_plain_language_html"]   = _fallback_plain_language_html(block)
    block["llm_astro_explanation_html"] = _fallback_astro_explanation_html(block)
    block["llm_ad_narrative_html"] = _fallback_ad_html(block)
    for pd in block.get("pratyantardashas", []):
        if not pd.get("llm_narrative_html"):
            pd["llm_narrative_html"] = _fallback_pd_html(pd)


def _attach_fallback_narratives(timeline_blocks: List[Dict[str, Any]]) -> None:
    """Attach deterministic fallbacks to all blocks when LLM is unavailable."""
    for block in timeline_blocks:
        _attach_fallback_narrative(block)


# ---------------------------------------------------------------------------
# MD-level narrative arc (one call per unique Mahadasha lord)
# ---------------------------------------------------------------------------

async def generate_md_narrative_arc(
    timeline_blocks: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    client: Any,
    model: str,
    semaphore: asyncio.Semaphore,
) -> Dict[str, str]:
    """Generate one thematic paragraph per unique MD lord covering the full MD arc.

    Returns: {md_lord: html_narrative}
    """
    # Group blocks by MD lord
    from collections import defaultdict
    md_groups: Dict[str, List[Dict]] = defaultdict(list)
    for b in timeline_blocks:
        ml = b.get("md_lord", "")
        if ml:
            md_groups[ml].append(b)

    md_html: Dict[str, str] = {}

    for md_lord, blocks in md_groups.items():
        start = blocks[0].get("start_date", "")
        end   = blocks[-1].get("end_date", "")
        scores = [b.get("career_score", 0.5) for b in blocks]
        avg_score = round(sum(scores) / len(scores), 2)
        peak_block = max(blocks, key=lambda b: b.get("career_score", 0))
        events = [b.get("event_type", "").replace("FORECAST_", "") for b in blocks]
        yogas  = list({y for b in blocks
                       for y in (b.get("sub_scores", {}).get("active_yogas", []) or [])})

        prompt = f"""Write ONE paragraph of premium HTML career narrative describing the OVERARCHING THEME of the {md_lord} Mahadasha ({start} to {end}).

Client: {career_ctx.get("designation", "Professional")} in {career_ctx.get("industry_sector", "industry")}
Average career score across this MD: {avg_score}/1.0
Peak event period: {peak_block.get("event_type","")} (score {peak_block.get("career_score",0):.2f})
Event sequence: {', '.join(events)}
Active yogas in this MD: {yogas if yogas else 'None'}

Write 3-4 sentences. Use ONLY <h4> and <p> tags. No lists. Speak to the overarching career theme, the dominant lesson or growth arc, and the most transformative sub-period. Sound like a premium executive advisor, not a textbook.
Return JSON: {{"md_html": "<h4>MD Arc: {md_lord}</h4><p>...</p>"}}"""

        async with semaphore:
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT + _language_directive()},
                        {"role": "user",   "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.35,
                    max_completion_tokens=500,
                )
                raw = resp.choices[0].message.content or "{}"
                data = json.loads(raw)
                md_html[md_lord] = _sanitize_html(data.get("md_html", ""))
            except Exception as exc:
                logger.warning(f"MD narrative failed for {md_lord}: {exc}")
                md_html[md_lord] = (
                    f"<h4>MD Arc: {md_lord}</h4>"
                    f"<p>The {md_lord} Mahadasha ({start}–{end}) spans a pivotal chapter "
                    f"with an average career score of {avg_score}/1.0, culminating in "
                    f"{peak_block.get('event_type','').replace('_',' ').title()} as the peak expression.</p>"
                )

    return md_html


# ---------------------------------------------------------------------------
# 2026-07-05: Annual Career Roadmap narrative + astrological explanation.
# One LLM call per roadmap year (last 1yr + this yr + next 3yrs = 5 calls),
# each grounded in the ACTUAL deterministic factor values for that year's
# dominant AD block — KP (sub-lord/ruling-planets/nakshatra-chain), Jaimini
# (chara dasha / atmakaraka role), D10 Dashamsha, D24 Siddhamsha, D60
# Shashtiamsha, and the KN Rao dasha-application layer — so the LLM explains
# WHY the score/event is what it is using real numbers, not generic filler.
# ---------------------------------------------------------------------------

_ROADMAP_SYSTEM_PROMPT = """\
You are a senior Vedic Astrology (Jyotish) career analyst writing the flagship \
section of a premium paid career report: the year-by-year Career Roadmap. This \
report is read by both the client AND, separately, by professional astrologers \
who will audit your reasoning — so your astrological explanation must stand up \
to expert scrutiny, not just sound plausible.

For EACH year you are given, you must return TWO pieces of writing:

1. "narrative_html" — a 4 to 5 paragraph professional-tone career narrative for \
that specific calendar year. Written like a senior career strategist's annual \
review: what this year concretely means for the client's job, promotion odds, \
income, and risk exposure. Confident, specific, executive register. No astrology \
jargon in this section — translate the astrology into career language.

2. "astro_explanation_html" — a LONG, RIGOROUS, TECHNICAL astrological methodology \
explanation — written for a professional astrologer reader, not a layperson — that \
lays out COMPLETELY and IN DETAIL why the career signal score and the named event \
(promotion / job change / salary hike / stability / risk, etc.) came out the way \
they did THIS year. Target 7-10 substantial paragraphs and/or bullet groups (do \
not artificially shorten this — depth and completeness matter more than brevity \
here). You must work through EACH of the following layers as its own clearly \
labeled reasoning step (use <strong> lead-ins, e.g. "<strong>KN Rao dasha lens:</strong>"), \
explicitly citing the specific values you were given for each — never invent a \
number, sign, planet, or house that wasn't provided:
   - <strong>KN Rao dasha-application lens:</strong> name the exact running \
Mahadasha lord and Antardasha lord, state which houses each one rules/occupies \
from lagna, and apply KN Rao's rule of judging results from the combined \
significations of the MD lord and AD lord together (their house lordships, \
natural/functional benefic-malefic status, and any conjunctions/aspects supplied). \
Explain concretely why this MD-AD combination is expected to produce (or resist) \
the scored outcome this year.
   - <strong>KP (Krishnamurti Paddhati) lens:</strong> walk the full cuspal chain \
you were given for the relevant house (sign lord → star lord → sub-lord → \
sub-sub-lord if provided), state whether the sub-lord signifies the houses needed \
for the event type (e.g. 2/6/10/11 for promotion/income, 12/8 with 10 for job \
change or setback), and explain the ruling-planet/nakshatra alignment's bearing \
on timing.
   - <strong>Jaimini lens:</strong> reference the Atmakaraka/Amatyakaraka and their \
Chara Dasha role if given, the active Arudha/Karma Pada houses, and what Jaimini \
principles (e.g. karaka strength, argala, house of the AK) say about this year's \
theme. IMPORTANT — the fields "fixed_atmakaraka"/"fixed_atmakaraka_domain" and \
"fixed_amatyakaraka"/"fixed_amatyakaraka_domain" identify the SAME planet and the \
SAME career-domain label for this person in every year of the report (Jaimini \
karakas are computed once from the natal chart and never change). Always use \
these exact planet names and exact domain-label phrasing verbatim when naming the \
AK/AmK and their domain — do not paraphrase, re-derive, or invent an alternative \
description of what the AK/AmK "represents" in different words across years. Only \
"jaimini_role" (whether THIS year's dasha lord happens to activate the AK/AmK/\
another karaka) is expected to vary year to year — the karaka identity and domain \
label themselves must read identically every time they appear.
   - <strong>Natal (D1) 10th-house and Ashtakavarga foundation:</strong> if \
"natal_10th_house_occupants" lists any planet(s) (e.g. Ketu), name them explicitly \
and state their classical career significance as permanent occupants of the 10th \
house — this is a lifelong natal placement, not a per-year fact, and should be \
referenced as background context underpinning EVERY year's reading, not something \
that appears only in some years. If "sav_h10_bindus" is provided, state the number \
and compare it plainly to the classical 28-bindu average (above ~30 is a strong \
quantitative career signal; below ~25 is a weak one) — treat a high value as one of \
the strongest available quantitative signals for career capacity, on par with or \
exceeding the qualitative yoga/dasha reasoning. If below the ~28-bindu benchmark, \
note that it suggests moderate (not absent) authority/status support rather than a \
deficiency; if "sav_h6_bindus" or "sav_h11_bindus" is available and higher than \
"sav_h10_bindus", note that service/problem-solving effort (6th) or gains/networks \
(11th) may be a stronger structural support than pure authority/status (10th) for \
this native. If these fields are empty/absent, say so briefly rather than \
fabricating an occupant or bindu count.
   - <strong>D10 Dashamsha (career varga) lens:</strong> state the D10 lagna, the \
D10 house-lord/occupancy detail provided, and explain how this varga-level \
placement supports or complicates the D1-level reading. Two distinct D10 numbers \
may both be supplied: a whole-chart, period-independent "D10 strength" (the \
native's baseline career-varga capacity, true for every year of their life) and a \
per-period "D10 alignment"/"D10 full score" (how strongly THIS SPECIFIC \
Mahadasha/Antardasha lord activates that D10 structure). These measure different \
things and can legitimately differ a lot — a chart can have solid whole-chart D10 \
strength while a given AD lord barely touches the D10 lagna/10th house this year. \
If both values are supplied, explicitly say so in one sentence (e.g. "the D10 is \
structurally solid overall, but this particular period does not draw heavily on \
it") — never present them as if they contradict each other without that one \
reconciling sentence.
   - <strong>D24 Siddhamsha and D60 Shashtiamsha modifiers:</strong> if non-zero/\
non-neutral values were supplied, explain their contribution (skill/education \
readiness for D24; fine-grained karmic modifier for D60); if the values are \
near-neutral or zero, say so explicitly in one sentence rather than fabricating \
significance — do not skip this layer, just be brief when there is nothing there.
   - <strong>Active yogas:</strong> if "active_yogas" lists any named yoga tags for \
this period, use the paired "active_yoga_explanations" entry for each tag to explain \
IN YOUR OWN WORDS (do not just copy the explanation text verbatim) what that yoga \
means and specifically how it bears on this year's career theme/event. Never leave a \
named yoga unexplained — a bare yoga name with no unpacking is not acceptable. If the \
list is empty, skip this bullet without comment.
   - <strong>Transit overlay:</strong> tie in the Jupiter/Saturn/Rahu-Ketu house \
positions and signal/theme supplied for the year, and state plainly how the transit \
layer reinforces or tempers the dasha-and-varga-level reading above. For Saturn \
specifically, you MUST ground the commentary in this chart's own natal Saturn — cite \
"saturn_natal_house" (which D1 house Saturn natally occupies), "saturn_natal_dignity" \
(EXALTED/OWN/DEBILITATED/NEUTRAL), and "saturn_rules_houses" (which house(s) natal \
Saturn is lord of) before describing what the CURRENT transiting Saturn house means — \
a transiting Saturn placement means something different for a natally exalted Saturn \
that also rules two houses than for a natally debilitated, lordship-less Saturn. Do \
not write generic Saturn-transit commentary that could apply to any chart.
   - <strong>Synthesis:</strong> close with a short paragraph explicitly stating how \
these layers were weighted together to arrive at the final career signal score and \
event label for the year — this is the sentence a fellow astrologer would look for \
to confirm the score isn't arbitrary.
Do not invent numbers, planets, signs, or houses — use only the values provided. \
If a factor's value is near-neutral/zero, say so briefly rather than fabricating \
significance, but still name the factor so the astrologer knows it was considered.

Formatting rules (STRICT):
- Use ONLY these tags: <p>, <strong>, <ul>, <li>. No <h3>/<h4>, no <div>/<span>/<a>, \
no attributes of any kind.
- Return ONLY valid JSON: {"years": {"<year>": {"narrative_html": "...", \
"astro_explanation_html": "..."}, ...}}
- No markdown fences, no prose outside the JSON object.
"""


async def generate_annual_roadmap_narratives(
    year_contexts: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    client: Any,
    model: str,
    semaphore: asyncio.Semaphore,
    is_anthropic: bool = False,
) -> Dict[int, Dict[str, str]]:
    """Generate {"narrative_html", "astro_explanation_html"} per roadmap year.

    year_contexts: one dict per roadmap year, each containing everything the
    LLM needs to ground its explanation in real computed values — see
    _build_year_context_payload() in web_report.py for the exact shape.
    One call per year (not batched) so each year gets full prompt attention
    and 4-5 paragraphs of real estate; years are dispatched concurrently.
    """
    results: Dict[int, Dict[str, str]] = {}

    async def _one(yr_ctx: Dict[str, Any]) -> None:
        year = yr_ctx.get("year")
        user_prompt = (
            f"Client: {career_ctx.get('designation', 'Professional')} in "
            f"{career_ctx.get('industry_sector', 'industry')}\n\n"
            f"Year: {year}\n"
            f"{json.dumps(yr_ctx, indent=2, default=str)}\n\n"
            f"Write narrative_html and astro_explanation_html for this year only. "
            f'Return JSON: {{"years": {{"{year}": {{"narrative_html": "...", '
            f'"astro_explanation_html": "..."}}}}}}'
        )
        async with semaphore:
            try:
                if is_anthropic:
                    response = await client.messages.create(
                        model=model,
                        max_completion_tokens=4000,
                        system=_ROADMAP_SYSTEM_PROMPT + _language_directive(),
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    raw = response.content[0].text if response.content else "{}"
                else:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": _ROADMAP_SYSTEM_PROMPT + _language_directive()},
                            {"role": "user",   "content": user_prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.35,
                        max_completion_tokens=4000,
                    )
                    raw = response.choices[0].message.content or "{}"
                data = json.loads(raw)
                yr_data = (data.get("years") or {}).get(str(year), {})
                results[year] = {
                    "narrative_html":        _sanitize_html(yr_data.get("narrative_html", "")),
                    "astro_explanation_html": _sanitize_html(yr_data.get("astro_explanation_html", "")),
                }
            except Exception as exc:
                logger.warning(f"Annual roadmap narrative failed for {year}: {exc}")
                results[year] = {}

    await asyncio.gather(*(_one(yc) for yc in year_contexts))
    return results


def generate_annual_roadmap_narratives_sync(
    year_contexts: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    max_concurrent: int = 5,
) -> Dict[int, Dict[str, str]]:
    """Synchronous, self-contained wrapper — builds its own LLM client so
    callers (e.g. the CLI entry script) don't need to manage async plumbing.
    Returns {} entirely if no LLM provider is configured (ANTHROPIC_API_KEY /
    OPENAI_API_KEY), so callers must handle the empty-dict fallback case."""
    if not year_contexts:
        return {}

    client, model = _get_llm_client()
    if client is None:
        logger.warning("No LLM provider configured — annual roadmap narratives skipped.")
        return {}

    is_anthropic = model.startswith("claude")
    semaphore = asyncio.Semaphore(max_concurrent)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio  # type: ignore
            nest_asyncio.apply()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return asyncio.get_event_loop().run_until_complete(
        generate_annual_roadmap_narratives(
            year_contexts, career_ctx, client, model, semaphore, is_anthropic=is_anthropic,
        )
    )


# ---------------------------------------------------------------------------
# Provider-agnostic LLM client factory
# ---------------------------------------------------------------------------

def _get_llm_client(provider: str = "auto") -> tuple:
    """Return (async_client, model_string) for the configured provider.

    Priority: ANTHROPIC_API_KEY → OPENAI_API_KEY → fallback None
    Override with LLM_PROVIDER env var: 'openai' | 'anthropic'
    """
    if provider == "auto":
        provider = os.getenv("LLM_PROVIDER", "auto").lower()

    # Try Anthropic
    if provider in ("anthropic", "auto"):
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            try:
                from anthropic import AsyncAnthropic  # type: ignore
                return AsyncAnthropic(api_key=anthropic_key), "claude-haiku-4-5-20251001"
            except ImportError:
                pass

    # Try OpenAI
    if provider in ("openai", "auto"):
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            try:
                from openai import AsyncOpenAI  # type: ignore
                return AsyncOpenAI(api_key=openai_key), "gpt-5.4-mini"
            except ImportError:
                pass

    return None, ""


# ---------------------------------------------------------------------------
# Updated generate_ad_narrative — with caching + provider abstraction
# ---------------------------------------------------------------------------

async def generate_ad_narrative_cached(
    block: Dict[str, Any],
    career_ctx: Dict[str, Any],
    chart_input: Any,
    client: Any,
    model: str,
    semaphore: asyncio.Semaphore,
    prev_event_type: str = "",
    prev_ad_lord: str = "",
    is_anthropic: bool = False,
    career_theme_str: str = "",
    field_selection_context: str = "",
) -> Dict[str, Any]:
    """LLM call for a single AD block with cache check.

    Identical to generate_ad_narrative but adds:
    - In-memory cache keyed on (md_lord, ad_lord, event_type, score, career_ctx)
    - Anthropic API support (claude models use messages API without response_format)
    """
    cache_key = _cache_key(block, career_ctx)
    cached = _try_cache_get(cache_key)
    if cached:
        logger.debug(f"Cache HIT for {block.get('ad_lord')} AD {block.get('start_date')}")
        return cached

    transit_positions = getattr(chart_input, "transit_house_positions", {}) or {}
    user_prompt = _build_user_prompt(
        block, career_ctx, transit_positions,
        prev_event_type=prev_event_type,
        prev_ad_lord=prev_ad_lord,
        career_theme_str=career_theme_str,
        field_selection_context=field_selection_context,
    )

    async with semaphore:
        try:
            if is_anthropic:
                # Anthropic claude API — no response_format param
                response = await client.messages.create(
                    model=model,
                    max_completion_tokens=2000,
                    system=_SYSTEM_PROMPT + _language_directive(),
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = response.content[0].text if response.content else "{}"
            else:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT + _language_directive()},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.4,
                    max_completion_tokens=2000,
                )
                raw = response.choices[0].message.content or "{}"

            llm_data = json.loads(raw)
            _cache_set(cache_key, llm_data)
            return llm_data

        except Exception as exc:
            logger.warning(
                f"LLM narrative failed for {block.get('ad_lord')} AD "
                f"({block.get('start_date')}): {exc}"
            )
            return {}


# ---------------------------------------------------------------------------
# Phase 2 — Uncertain Event Resolution
# ---------------------------------------------------------------------------
# Called between deterministic timeline output and narrative generation.
# Blocks where career_score falls in [0.50, 0.68] are in the "ambiguous zone"
# where the decision tree cannot reliably distinguish e.g. SALARY_HIKE from
# LEADERSHIP_EXPANSION. A single batch LLM call resolves all uncertain blocks.

_UNCERTAIN_LOW  = 0.50
_UNCERTAIN_HIGH = 0.68

_RESOLUTION_SYSTEM_PROMPT = """\
You are a Vedic Astrology career event classifier.
You will receive a batch of career period blocks that the deterministic engine
classified with low confidence (score between 0.50–0.68).

For each block, output the most appropriate suggested_event_type based on the
career context, active houses, and jaimini/kp signals provided.

Your output is ADVISORY ONLY. You do NOT overwrite deterministic_event_type —
the deterministic engine's own validation rule decides whether your suggestion
is ever accepted, and only as a secondary, clearly-labeled signal.

Valid event types: GROWTH, SALARY_HIKE, LEADERSHIP_EXPANSION, SKILL_UPGRADE_PHASE,
JOB_CHANGE, INCOME_INFLECTION, PROMOTION, STABILITY, CAREER_TRANSITION, AUTHORITY_SHIFT

Rules:
- H10+H1 active + senior designation → LEADERSHIP_EXPANSION or PROMOTION
- H11+H2 active + income intent → SALARY_HIKE or INCOME_INFLECTION
- H3+H5 active → SKILL_UPGRADE_PHASE
- H6+H12 active → JOB_CHANGE or CAREER_TRANSITION
- H10+H8 active → AUTHORITY_SHIFT
- When unsure, keep the deterministic event_type unchanged.

Return ONLY valid JSON: {"resolutions": [{"block_id": "...", "suggested_event_type": "...", "confidence": "...", "reason": "..."}]}
"""


async def resolve_uncertain_events(
    timeline_blocks: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    client: Any,
    model: str,
    semaphore: asyncio.Semaphore,
    is_anthropic: bool = False,
) -> List[Dict[str, Any]]:
    """Phase 2: batch resolve event types for ambiguous score-band blocks.

    Identifies blocks with career_score in [0.50, 0.68], sends them in ONE
    LLM call, and applies the refined event_type back to the block list.
    Returns the (possibly modified) timeline_blocks list.
    """
    uncertain = [
        b for b in timeline_blocks
        if _UNCERTAIN_LOW <= b.get("career_score", 0) <= _UNCERTAIN_HIGH
    ]
    if not uncertain:
        return timeline_blocks

    # Build a compact representation — only what the LLM needs
    batch = [
        {
            "block_id":     f"{b.get('md_lord','')}/{b.get('ad_lord','')}/{b.get('start_date','')}",
            "md_lord":      b.get("md_lord", ""),
            "ad_lord":      b.get("ad_lord", ""),
            "career_score": b.get("career_score", 0.0),
            "event_type":   b.get("event_type", ""),
            "active_houses": b.get("active_houses", []),
            "jaimini_role":  b.get("jaimini_role", ""),
            "kp_ssl_score":  (b.get("sub_scores", {}) or {}).get("kp_ssl_score"),
        }
        for b in uncertain
    ]

    user_prompt = (
        f"Career context: {career_ctx.get('designation', 'Professional')} in "
        f"{career_ctx.get('industry_sector', 'industry')}\n\n"
        f"Ambiguous blocks:\n{json.dumps(batch, indent=2, default=str)}\n\n"
        f"Your suggestion is advisory only and does NOT overwrite deterministic_event_type.\n"
        f'Return ONLY: {{"resolutions": [{{"block_id": "...", '
        f'"suggested_event_type": "...", "confidence": "...", "reason": "..."}}]}}'
    )

    async with semaphore:
        try:
            if is_anthropic:
                response = await client.messages.create(
                    model=model,
                    max_completion_tokens=2000,
                    system=_RESOLUTION_SYSTEM_PROMPT + _language_directive(),
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = response.content[0].text if response.content else "{}"
            else:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _RESOLUTION_SYSTEM_PROMPT + _language_directive()},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_completion_tokens=2000,
                )
                raw = response.choices[0].message.content or "{}"

            data = json.loads(raw)
            resolutions = {
                r.get("block_id"): r
                for r in (data.get("resolutions") or [])
                if r.get("block_id")
            }
        except Exception as exc:
            logger.warning(f"Uncertain-event resolution batch failed: {exc}")
            return timeline_blocks

    _VALID_EVENT_TYPES = {
        "GROWTH", "SALARY_HIKE", "LEADERSHIP_EXPANSION", "SKILL_UPGRADE_PHASE",
        "JOB_CHANGE", "INCOME_INFLECTION", "PROMOTION", "STABILITY",
        "CAREER_TRANSITION", "AUTHORITY_SHIFT", "LATERAL_MOVE",
    }
    # LATERAL_MOVE was previously missing from this set even though it is a
    # first-class deterministic output (see timeline.py G30 branch) and is
    # explicitly named in the comment below as one of the "weaker claims" the
    # gate is meant to allow through unaffected. Its absence meant an LLM
    # suggestion of LATERAL_MOVE could never pass _passes_deterministic_check,
    # and — more importantly — it left no correct downgrade target for the
    # tenure gate, which used to fall back to the stronger "JOB_CHANGE" label
    # instead of "movement without promotion". Fixed below.

    # PROMOTION is treated as a "strong" claim: relabeling an ambiguous block
    # as PROMOTION requires either the deterministic pass having already said
    # PROMOTION (no upgrade happening), or strong corroborating evidence
    # (10th/11th house activation + a high kp_ssl_score, matching the >= 0.65
    # "strong" threshold convention used elsewhere for kp_ssl_score/vimsopaka —
    # see astro_enhancer.py). Weaker claims (LATERAL_MOVE/JOB_CHANGE/
    # ROLE_EXPANSION/STABILITY-style) are unaffected and keep the original
    # acceptance behavior.
    _STRONG_KP_SSL_THRESHOLD = 0.65
    _MIN_TENURE_MONTHS_FOR_PROMOTION = 9
    _join_date = parse_iso_date(str(career_ctx.get("join_date", "")))

    # Fix F (2026-07): retro-validation split — when a known join_date falls
    # inside one block but was immediately preceded by a different-lord block,
    # the "before" block often represents search pressure / detachment /
    # transition trigger rather than the actual outcome, while the block that
    # actually CONTAINS the join_date is where materialization/settlement
    # happened. Annotate both blocks generically (by date position, not by
    # hardcoding specific lord names) so this works for any chart. Runs over
    # the FULL ordered timeline_blocks list (not just the ambiguous `uncertain`
    # subset) since the "before" block need not itself be ambiguous.
    if _join_date is not None:
        _ordered_blocks = sorted(
            (bb for bb in timeline_blocks if parse_iso_date(str(bb.get("start_date", ""))) is not None),
            key=lambda bb: parse_iso_date(str(bb.get("start_date", ""))),
        )
        _containing_block = None
        _containing_idx = None
        for _idx, _blk in enumerate(_ordered_blocks):
            _b_start = parse_iso_date(str(_blk.get("start_date", "")))
            _b_end   = parse_iso_date(str(_blk.get("end_date", "")))
            if _b_start is not None and _b_start <= _join_date and (_b_end is None or _join_date < _b_end):
                _containing_block = _blk
                _containing_idx = _idx
                break
        if _containing_block is not None and _containing_idx is not None and _containing_idx > 0:
            _before_block = _ordered_blocks[_containing_idx - 1]
            _before_lord = _before_block.get("ad_lord") or _before_block.get("md_lord") or ""
            _containing_lord = _containing_block.get("ad_lord") or _containing_block.get("md_lord") or ""
            if _before_lord and _containing_lord and _before_lord != _containing_lord:
                _before_block["retro_note"] = (
                    f"Likely represents search pressure / detachment / transition trigger "
                    f"({_before_lord} period) rather than the final outcome — the actual "
                    f"join/materialization falls in a later period ({_containing_lord})."
                )
                _containing_block["retro_note"] = (
                    f"Contains the actual join date — likely materialization/settlement "
                    f"({_containing_lord} period) of the outcome that began forming in the "
                    f"prior ({_before_lord}) period."
                )

    # Retro-validation extension: last_promotion_date. Same idea as the
    # join_date check above — if a known historical promotion date is
    # supplied, find the block whose [start_date, end_date) window actually
    # contains it and annotate it as a confirmed historical event. This lets
    # the current/future scoring be read against a real calibration point
    # ("did the engine's rules actually fire for a promotion that we know
    # happened?") instead of always waiting for a future forecast to validate itself.
    # RECONSTRUCTION NOTE (2026-07-08): this trailing section was found
    # truncated mid-sentence with no function return — same corruption
    # pattern documented elsewhere in this codebase (see timeline.py's
    # "RECONSTRUCTION NOTE (2026-07-07)"). The block below completes the
    # last_promotion_date retro-validation annotation (mirroring the
    # join_date block immediately above it) and restores the function's
    # closing `return timeline_blocks` that any caller of
    # resolve_uncertain_events() requires.
    _last_promo_date = parse_iso_date(str(career_ctx.get("last_promotion_date", "")))
    if _last_promo_date is not None:
        _ordered_blocks2 = sorted(
            (bb for bb in timeline_blocks if parse_iso_date(str(bb.get("start_date", ""))) is not None),
            key=lambda bb: parse_iso_date(str(bb.get("start_date", ""))),
        )
        for _blk in _ordered_blocks2:
            _b_start = parse_iso_date(str(_blk.get("start_date", "")))
            _b_end   = parse_iso_date(str(_blk.get("end_date", "")))
            if _b_start is not None and _b_start <= _last_promo_date and (_b_end is None or _last_promo_date < _b_end):
                _blk["retro_note"] = (
                    (_blk.get("retro_note", "") + " " if _blk.get("retro_note") else "")
                    + f"Confirmed historical promotion ({_last_promo_date.isoformat()}) falls inside "
                    f"this period — usable as a real calibration point for the engine's scoring rules."
                ).strip()
                _blk["retro_confirmed_promotion"] = True
                break

    return timeline_blocks


# ---------------------------------------------------------------------------
# Public sync API — enrich_timeline_sync
# ---------------------------------------------------------------------------
# This is the module's documented public entry point (see module docstring,
# "Public API" section at the top of this file) and is the function the CLI
# (field_deterministic_engine_v1_llm.py, "career"/"both" mode) imports and
# calls. It was previously MISSING from this file entirely — the import at
# the CLI call site therefore always raised ImportError, which the CLI's own
# try/except silently swallowed ("LLM enrichment failed (deterministic
# narratives preserved)"). That accidental failure was actually harmless for
# the deterministic decision fields (final_event_type, kp_override_*,
# retro_validation, D10 sub-scores, etc. all passed through untouched), but
# it also meant NO supplementary LLM prose was ever actually added, and any
# future working implementation risked re-introducing the exact overwrite
# bug this rewrite is designed to avoid. Implemented properly below, and
# — per the same discipline documented in jyotish/llm.py ("The ranking is
# FIXED by the deterministic engine ... LLM-as-reranker is intentionally
# removed") — this function ONLY ADDS narrative/prose fields
# (llm_ad_narrative_html, pd["llm_narrative_html"], and — for
# resolve_uncertain_events — an advisory-only "llm_suggested_event_type"
# field). It never overwrites event_type/final_event_type/final_event_source,
# kp_override_applied/kp_override_reason, retro_validation, the D10
# sub-dimension scores (d10_title_support, d10_global_delivery_support,
# d10_invisible_authority_support, d10_clean_promotion_support), or any
# foreign-opportunity/Venus narrative fields (those live in
# jyotish/foreign_opportunities.py / jyotish/timeline.py's foreign module and
# are never touched here).

async def _enrich_timeline_async(
    timeline_blocks: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    chart_input: Any,
    career_theme_str: str = "",
    field_selection_context: str = "",
    run_phase2_resolution: bool = False,
    max_concurrent: int = 5,
) -> List[Dict[str, Any]]:
    if not timeline_blocks:
        return timeline_blocks

    client, model = _get_llm_client()
    if client is None:
        logger.warning("No LLM provider configured — attaching deterministic fallback narratives only.")
        _attach_fallback_narratives(timeline_blocks)
        return timeline_blocks

    is_anthropic = model.startswith("claude")
    semaphore = asyncio.Semaphore(max_concurrent)

    # Phase 2 (optional): advisory-only event-type resolution for ambiguous
    # score-band blocks. Does NOT overwrite deterministic_event_type/
    # final_event_type — see resolve_uncertain_events()'s own docstring and
    # the _RESOLUTION_SYSTEM_PROMPT, which both state this explicitly. Any
    # suggestion is stored under a clearly separate "llm_suggested_event_type"
    # key so downstream code can display it as a secondary signal without any
    # risk of it being mistaken for the deterministic decision.
    if run_phase2_resolution:
        try:
            timeline_blocks = await resolve_uncertain_events(
                timeline_blocks, career_ctx, client, model, semaphore, is_anthropic=is_anthropic,
            )
        except Exception as exc:
            logger.warning(f"Phase 2 uncertain-event resolution failed (non-fatal): {exc}")

    # Phase 1: per-AD narrative prose, one LLM call per AD block, dispatched
    # concurrently. FIX 6 continuity context is threaded from the previous
    # block in chronological order.
    _ordered = sorted(
        (b for b in timeline_blocks if parse_iso_date(str(b.get("start_date", ""))) is not None),
        key=lambda b: parse_iso_date(str(b.get("start_date", ""))),
    )

    async def _one(idx: int, block: Dict[str, Any]) -> None:
        prev_event_type = ""
        prev_ad_lord = ""
        if idx > 0:
            _prev = _ordered[idx - 1]
            prev_event_type = _prev.get("final_event_type") or _prev.get("event_type", "")
            prev_ad_lord = _prev.get("ad_lord", "")

        llm_data = await generate_ad_narrative_cached(
            block, career_ctx, chart_input, client, model, semaphore,
            prev_event_type=prev_event_type,
            prev_ad_lord=prev_ad_lord,
            is_anthropic=is_anthropic,
            career_theme_str=career_theme_str,
            field_selection_context=field_selection_context,
        )

        if llm_data.get("plain_language_html") or llm_data.get("astro_explanation_html"):
            # ADDITIVE ONLY: narrative prose fields, never decision fields.
            # Two segregated layers (2026-07-19, user request): plain-language
            # career prose vs. technical astrological reasoning, kept as
            # separate keys so the renderer can show them as distinct panels
            # instead of one blended block.
            if llm_data.get("plain_language_html"):
                block["llm_plain_language_html"] = _sanitize_html(llm_data["plain_language_html"])
            if llm_data.get("astro_explanation_html"):
                block["llm_astro_explanation_html"] = _sanitize_html(llm_data["astro_explanation_html"])
            # Legacy combined key, kept for any caller still reading
            # llm_ad_narrative_html as a single blob (e.g. Job_Career/
            # generate_career_report.py's standalone renderer).
            block["llm_ad_narrative_html"] = (
                "<h4>In Plain Language</h4>" + block.get("llm_plain_language_html", "") +
                "<h4>Astrological Explanation</h4>" + block.get("llm_astro_explanation_html", "")
            )
        else:
            # Graceful fallback — deterministic narrative_hint-derived prose,
            # never leaves the block without SOME narrative text.
            _attach_fallback_narrative(block)

        _pd_narratives = llm_data.get("pd_narratives") or []
        if _pd_narratives:
            _by_lord = {
                (pd.get("pd_lord"), pd.get("start_date")): pd.get("narrative_html", "")
                for pd in _pd_narratives
            }
            for pd in block.get("pratyantardashas", []) or []:
                _key = (pd.get("pd_lord"), pd.get("start_date"))
                _html = _by_lord.get(_key)
                if _html:
                    pd["llm_narrative_html"] = _sanitize_html(_html)

    await asyncio.gather(*[_one(i, b) for i, b in enumerate(_ordered)])
    return timeline_blocks


def enrich_timeline_sync(
    timeline_blocks: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    chart_input: Any = None,
    career_theme_str: str = "",
    field_selection_context: str = "",
    run_phase2_resolution: bool = False,
) -> List[Dict[str, Any]]:
    """Synchronous, self-contained wrapper — mirrors
    generate_annual_roadmap_narratives_sync's pattern so the CLI entry script
    doesn't need to manage async plumbing.

    Guarantee: this function only ever ADDS narrative/prose fields to each
    block (llm_ad_narrative_html, pd["llm_narrative_html"]) plus, when
    run_phase2_resolution=True, an advisory-only llm_suggested_event_type.
    It never mutates event_type, final_event_type, final_event_source,
    kp_override_applied, kp_override_reason, retro_validation, the D10
    sub-dimension scores, or any foreign-opportunity/Venus fields (those are
    computed entirely in timeline.py/foreign_opportunities.py and are not
    touched by this module). If anything below raises, the ORIGINAL
    timeline_blocks (deterministic, unmodified) is returned unchanged so the
    caller's existing try/except fallback path still behaves correctly.
    """
    if not timeline_blocks:
        return timeline_blocks

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio  # type: ignore
            nest_asyncio.apply()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return asyncio.get_event_loop().run_until_complete(
            _enrich_timeline_async(
                timeline_blocks, career_ctx, chart_input,
                career_theme_str=career_theme_str,
                field_selection_context=field_selection_context,
                run_phase2_resolution=run_phase2_resolution,
            )
        )
    except Exception as exc:
        logger.warning(f"enrich_timeline_sync failed — returning deterministic blocks unmodified: {exc}")
        return timeline_blocks
