"""JyotishAI — Career Timeline LLM Narrative Builder

Separation of concerns:
  timeline.py              — Deterministic engine (math, scoring, period classification)
  llm_narrative_builder.py — Generative engine (LLM HTML prose, one call per AD, async)

Public API:
  enrich_timeline_with_llm(blocks, career_ctx, chart_input)  -> List[Dict]   (async)
  enrich_timeline_sync(blocks, career_ctx, chart_input)       -> List[Dict]   (sync wrapper)

Architecture:
  - One LLM call per Antardasha (AD) block, containing all its nested PDs.
  - All calls are dispatched concurrently via asyncio.gather.
  - FIX 6: Each AD prompt receives previous_event_type + previous_ad_lord so the
    LLM writes each block as a continuation, not a standalone piece.
  - FIX 7: All LLM HTML output is passed through _sanitize_html() (whitelist-based)
    before storage. System prompt also enumerates the strict tag whitelist.
  - Transit data injected per-AD from chart_input.transit_house_positions.
  - Falls back gracefully to deterministic narrative_hint if OpenAI unavailable.

Output keys per block:
  block["llm_ad_narrative_html"]   str  — sanitized HTML (h4, p, ul, li, strong only)
  pd["llm_narrative_html"]         str  — sanitized HTML <p> micro-prediction per PD
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jyotish_engine_v11_0")

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

Tone & Style:
- Premium, executive, empowering, and deeply insightful.
- Read like a high-end corporate strategy document blended with deep astrological wisdom.
- Speak directly to the client's career impact. Do NOT give textbook astrology definitions.
- Do NOT use phrases like "As you transition into this phase" or "Welcome to this period" \
  — write fresh, specific prose for each block.

FIX 6 — Continuity Rule:
- Each narrative must acknowledge the previous period's momentum.
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
Active Yogas:    {block.get("sub_scores", {{}}).get("active_yogas", []) or block.get("active_yogas", [])}
Yoga Bonus:      {round(block.get("sub_scores", {{}}).get("yoga_bonus", 0) or block.get("yoga_bonus", 0), 3)}
D9 Modifier:     {round(block.get("sub_scores", {{}}).get("d9_modifier", 0) or 0, 3)}
Chandra Bonus:   {round(block.get("sub_scores", {{}}).get("chandra_lagna_bonus", 0) or 0, 3)}
Transit Flags:   {block.get("transit_flags", [])}
Transit Positions (natal house): {json.dumps(transit_positions)}
{_workplace_section}{_skills_section}{_macro_section}
--- PRATYANTARDASHA BREAKDOWN ---
{json.dumps(pds_for_prompt, indent=2)}

--- OUTPUT SCHEMA ---
Return ONLY this JSON:
{{
  "ad_narrative_html": "<h4>Executive Summary</h4><p>1 para</p><h4>Astrological Dynamics</h4><p>1 para weaving dasha + transit</p><h4>Strategic Action Plan</h4><ul><li>3 specific action steps</li></ul>",
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
                    {"role": "system", "content": _SYSTEM_PROMPT},
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

async def enrich_timeline_with_llm(
    timeline_blocks: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    chart_input: Any = None,
    model: str = "gpt-5.4-mini",
    max_concurrent: int = 8,
) -> List[Dict[str, Any]]:
    """Enrich deterministic timeline blocks with premium HTML LLM prose.

    FIX 6: Each task receives prev_event_type + prev_ad_lord from the preceding block
    (pre-computed from the sorted deterministic output) so the LLM writes continuity.

    FIX 7: All LLM HTML is sanitized through _sanitize_html() before storage.
    """
    if not timeline_blocks:
        return timeline_blocks

    if chart_input is None:
        class _NoChart:
            transit_house_positions: dict = {}
        chart_input = _NoChart()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("LLM enrichment skipped: OPENAI_API_KEY not set.")
        _attach_fallback_narratives(timeline_blocks)
        return timeline_blocks

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("LLM enrichment skipped: openai package not installed.")
        _attach_fallback_narratives(timeline_blocks)
        return timeline_blocks

    client = AsyncOpenAI(api_key=api_key)
    semaphore = asyncio.Semaphore(max_concurrent)

    # Pre-compute continuity chain from deterministic sorted output
    _prev_types: List[str] = [""] + [b.get("event_type", "") for b in timeline_blocks[:-1]]
    _prev_lords: List[str] = [""] + [b.get("ad_lord", "") for b in timeline_blocks[:-1]]

    tasks = [
        generate_ad_narrative(
            block       = block,
            career_ctx  = career_ctx,
            chart_input = chart_input,
            client      = client,
            model       = model,
            semaphore   = semaphore,
            prev_event_type = _prev_types[i],
            prev_ad_lord    = _prev_lords[i],
        )
        for i, block in enumerate(timeline_blocks)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for block, result in zip(timeline_blocks, results):
        if isinstance(result, Exception):
            logger.warning(f"LLM task exception for {block.get('ad_lord')}: {result}")
            _attach_fallback_narrative(block)
            continue

        if not isinstance(result, dict):
            _attach_fallback_narrative(block)
            continue

        ad_html = _sanitize_html(result.get("ad_narrative_html", ""))
        block["llm_ad_narrative_html"] = ad_html or _fallback_ad_html(block)

        pd_narratives = result.get("pd_narratives", [])
        pd_map = {
            item["pd_lord"]: _sanitize_html(item.get("narrative_html", ""))
            for item in pd_narratives
            if isinstance(item, dict) and "pd_lord" in item
        }
        for pd in block.get("pratyantardashas", []):
            pd_html = pd_map.get(pd.get("pd_lord", ""), "")
            pd["llm_narrative_html"] = pd_html or _fallback_pd_html(pd)

    return timeline_blocks


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

def _fallback_ad_html(block: Dict[str, Any]) -> str:
    """Generate clean deterministic HTML when LLM is unavailable."""
    hint = block.get("narrative_hint", "") or ""
    event = (block.get("event_type") or "STABILITY").replace("_", " ").title()
    score = block.get("career_score", 0.5)
    md_l  = block.get("md_lord", "")
    ad_l  = block.get("ad_lord", "")
    houses = block.get("active_houses", [])
    yogas  = block.get("sub_scores", {}).get("active_yogas", []) or []
    yoga_str = f" Active yogas: {', '.join(yogas)}." if yogas else ""
    return (
        f"<h4>Executive Summary</h4>"
        f"<p>{event} period under {md_l} Mahadasha / {ad_l} Antardasha. "
        f"Career score: {round(score * 100)}%.{yoga_str}</p>"
        f"<h4>Astrological Dynamics</h4>"
        f"<p>{hint or 'Planetary energies are active through houses ' + str(houses) + '.'}</p>"
        f"<h4>Strategic Action Plan</h4>"
        f"<ul>"
        f"<li>Monitor key career developments during this period's trigger windows.</li>"
        f"<li>Align actions with the dominant planetary theme of {ad_l}.</li>"
        f"<li>Review remedies specific to this event type for sustained support.</li>"
        f"</ul>"
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
    """Attach deterministic fallback to a single block."""
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
                        {"role": "system", "content": _SYSTEM_PROMPT},
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
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = response.content[0].text if response.content else "{}"
            else:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
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

For each block, output the most appropriate refined_event_type based on the
career context, active houses, and jaimini/kp signals provided.

Valid event types: GROWTH, SALARY_HIKE, LEADERSHIP_EXPANSION, SKILL_UPGRADE_PHASE,
JOB_CHANGE, INCOME_INFLECTION, PROMOTION, STABILITY, CAREER_TRANSITION, AUTHORITY_SHIFT

Rules:
- H10+H1 active + senior designation → LEADERSHIP_EXPANSION or PROMOTION
- H11+H2 active + income intent → SALARY_HIKE or INCOME_INFLECTION
- H3+H5 active → SKILL_UPGRADE_PHASE
- H6+H12 active → JOB_CHANGE or CAREER_TRANSITION
- H10+H8 active → AUTHORITY_SHIFT
- When unsure, keep the deterministic event_type unchanged.

Return ONLY valid JSON: {"resolutions": [{"block_id": "...", "refined_event_type": "...", "reason": "..."}]}
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
            "block_id":     f"{b.get('md_lord','')}/{b.get('ad_lord','')}_{b.get('start_date','')}",
            "event_type":   b.get("event_type", ""),
            "career_score": b.get("career_score", 0),
            "active_houses": b.get("active_houses", []),
            "jaimini_role":  b.get("jaimini_role", ""),
            "kp_alignment":  b.get("kp_cusp_alignment", ""),
            "designation":   career_ctx.get("designation", ""),
            "desired_outcome": career_ctx.get("desired_outcome", ""),
        }
        for b in uncertain
    ]

    user_prompt = (
        f"Client: {career_ctx.get('designation','Professional')} in "
        f"{career_ctx.get('industry_sector','Corporate')}\n\n"
        f"Uncertain blocks:\n{json.dumps(batch, indent=2)}\n\n"
        f"Refine the event_type for each block. Return JSON only."
    )

    async with semaphore:
        try:
            if is_anthropic:
                resp = await client.messages.create(
                    model=model,
                    max_completion_tokens=800,
                    system=_RESOLUTION_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = resp.content[0].text if resp.content else "{}"
            else:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _RESOLUTION_SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_completion_tokens=800,
                )
                raw = resp.choices[0].message.content or "{}"

            data      = json.loads(raw)
            res_list  = data.get("resolutions", [])
            res_map   = {r["block_id"]: r for r in res_list if "block_id" in r}

            # GAP 10 fix: minimum career_score floors per event type.
            # When Phase 2 promotes an event (e.g. GROWTH → SALARY_HIKE), the block's
            # career_score still reflects the deterministic mid-range calculation.
            # If the score is below the floor for the refined type, nudge it up so the
            # label and the score are consistent for the HTML report confidence display.
            _EVENT_SCORE_FLOORS: Dict[str, float] = {
                "BREAKTHROUGH":          0.80,
                "PROMOTION":             0.68,
                "LEADERSHIP_EXPANSION":  0.62,
                "INCOME_INFLECTION":     0.60,
                "SALARY_HIKE":           0.54,
                "JOB_CHANGE":            0.50,
                "FOREIGN_POSTING":       0.50,
                "GROWTH":                0.50,
                "SKILL_UPGRADE_PHASE":   0.40,
                "STABILITY":             0.30,
                "RISK_PERIOD":           0.20,
            }

            # Apply refined event types back to blocks
            for b in uncertain:
                bid = f"{b.get('md_lord','')}/{b.get('ad_lord','')}_{b.get('start_date','')}"
                resolution = res_map.get(bid)
                if resolution:
                    new_type = resolution.get("refined_event_type", "")
                    if new_type and new_type != b.get("event_type", ""):
                        b["event_type"]             = new_type
                        b["event_type_llm_refined"] = True
                        b["event_type_llm_reason"]  = resolution.get("reason", "")
                        # GAP 10: align career_score with the refined event's score floor
                        _floor = _EVENT_SCORE_FLOORS.get(new_type, 0.0)
                        if _floor and b.get("career_score", 0) < _floor:
                            b["career_score"]              = round(_floor, 3)
                            b["career_score_llm_adjusted"] = True

            logger.info(
                "Phase 2: resolved %d uncertain blocks out of %d",
                len(res_map), len(uncertain),
            )

        except Exception as exc:
            logger.warning("Phase 2 event resolution failed: %s", exc)
            # Non-fatal — deterministic event types remain unchanged

    return timeline_blocks


# ---------------------------------------------------------------------------
# Updated enrich_timeline_with_llm — uses caching + provider abstraction
# ---------------------------------------------------------------------------

async def enrich_timeline_with_llm_v2(
    timeline_blocks: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    chart_input: Any = None,
    model: str = "",
    max_concurrent: int = 8,
    include_md_arc: bool = True,
    career_theme_str: str = "",
    field_selection_context: str = "",
    run_phase2_resolution: bool = True,
) -> List[Dict[str, Any]]:
    """Enrich deterministic timeline with LLM narrative (v2 — cached, multi-provider).

    Automatically selects Anthropic or OpenAI based on available API keys.
    Falls back gracefully to deterministic narrative if neither is available.

    New params (Phase 0/2 integration):
      career_theme_str        — from llm_context_enricher (Phase 0); injected into
                                every AD prompt as a narrative through-line
      field_selection_context — from llm.py Step 1 analytical_breakdown; tells the
                                narrative builder which planet/domain dominates
      run_phase2_resolution   — if True, run a batch uncertain-event resolution call
                                before narrative generation (Phase 2)
    """
    if not timeline_blocks:
        return timeline_blocks

    if chart_input is None:
        class _NoChart:
            transit_house_positions: dict = {}
        chart_input = _NoChart()

    client, detected_model = _get_llm_client()
    if model:
        detected_model = model  # explicit override
    is_anthropic = detected_model.startswith("claude")

    if client is None:
        logger.warning("LLM enrichment skipped: no API key found (set OPENAI_API_KEY or ANTHROPIC_API_KEY).")
        _attach_fallback_narratives(timeline_blocks)
        return timeline_blocks

    semaphore = asyncio.Semaphore(max_concurrent)

    # Phase 2: resolve uncertain event types (score 0.50–0.68) before narrative.
    # One batch LLM call refines ambiguous classifications using career context.
    if run_phase2_resolution:
        timeline_blocks = await resolve_uncertain_events(
            timeline_blocks, career_ctx, client, detected_model, semaphore, is_anthropic
        )

    # Pre-compute continuity chain (after Phase 2 — use refined event types)
    _prev_types: List[str] = [""] + [b.get("event_type", "") for b in timeline_blocks[:-1]]
    _prev_lords: List[str] = [""] + [b.get("ad_lord", "") for b in timeline_blocks[:-1]]

    tasks = [
        generate_ad_narrative_cached(
            block                  = block,
            career_ctx             = career_ctx,
            chart_input            = chart_input,
            client                 = client,
            model                  = detected_model,
            semaphore              = semaphore,
            prev_event_type        = _prev_types[i],
            prev_ad_lord           = _prev_lords[i],
            is_anthropic           = is_anthropic,
            career_theme_str       = career_theme_str,
            field_selection_context = field_selection_context,
        )
        for i, block in enumerate(timeline_blocks)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for block, result in zip(timeline_blocks, results):
        if isinstance(result, Exception) or not isinstance(result, dict):
            _attach_fallback_narrative(block)
            continue

        ad_html = _sanitize_html(result.get("ad_narrative_html", ""))
        block["llm_ad_narrative_html"] = ad_html or _fallback_ad_html(block)

        pd_map = {
            item["pd_lord"]: _sanitize_html(item.get("narrative_html", ""))
            for item in result.get("pd_narratives", [])
            if isinstance(item, dict) and "pd_lord" in item
        }
        for pd in block.get("pratyantardashas", []):
            pd_html = pd_map.get(pd.get("pd_lord", ""), "")
            pd["llm_narrative_html"] = pd_html or _fallback_pd_html(pd)

        # Attach event-specific remedies to the block
        block["event_remedies"] = get_event_remedies(
            block.get("event_type", ""),
            block.get("md_lord", ""),
            block.get("ad_lord", ""),
        )

    # MD-level narrative arc
    if include_md_arc:
        try:
            md_arcs = await generate_md_narrative_arc(
                timeline_blocks, career_ctx, client, detected_model, semaphore
            )
            # Attach md_arc_html to first block of each MD
            seen_md: set = set()
            for block in timeline_blocks:
                ml = block.get("md_lord", "")
                if ml not in seen_md and ml in md_arcs:
                    block["md_arc_html"] = md_arcs[ml]
                    seen_md.add(ml)
        except Exception as exc:
            logger.warning(f"MD arc generation failed: {exc}")

    return timeline_blocks


# ---------------------------------------------------------------------------
# Sync wrapper (backward-compatible with engine_io.py)
# ---------------------------------------------------------------------------

def enrich_timeline_sync(
    timeline_blocks: List[Dict[str, Any]],
    career_ctx: Dict[str, Any],
    chart_input: Any = None,
    model: str = "",
    max_concurrent: int = 8,
    include_md_arc: bool = True,
    career_theme_str: str = "",
    field_selection_context: str = "",
    run_phase2_resolution: bool = True,
) -> List[Dict[str, Any]]:
    """Synchronous wrapper around enrich_timeline_with_llm_v2.

    Safe to call from synchronous contexts (e.g., engine_io.py).
    Uses the faster v2 pipeline (caching + multi-provider + Phase 2 resolution).

    New params thread Phase 0/2 context through to the narrative prompts:
      career_theme_str        — from llm_context_enricher Phase 0 output
      field_selection_context — from llm.py Step 1 analytical_breakdown
      run_phase2_resolution   — batch uncertain event resolution before narrative
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio  # type: ignore
            nest_asyncio.apply()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return asyncio.get_event_loop().run_until_complete(
        enrich_timeline_with_llm_v2(
            timeline_blocks,
            career_ctx,
            chart_input,
            model                  = model,
            max_concurrent         = max_concurrent,
            include_md_arc         = include_md_arc,
            career_theme_str       = career_theme_str,
            field_selection_context = field_selection_context,
            run_phase2_resolution  = run_phase2_resolution,
        )
    )


# ---------------------------------------------------------------------------
# Keep original enrich_timeline_with_llm as a thin alias for backward compat
# ---------------------------------------------------------------------------

