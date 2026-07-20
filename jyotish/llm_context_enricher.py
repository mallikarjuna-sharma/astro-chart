"""JyotishAI -- LLM Pre-Scoring Context Enricher  (Phase 0)

Phase 0 runs BEFORE the deterministic scoring loop.  It calls an LLM once
to produce chart-level calibration signals that bias the per-period weights:

  weight_overrides  -- {sub_score_name: float} adjust the 10 primary weights
  intent_tags       -- ["promotion", "foreign", "business"] for tie-breaking
  sector_modifier   -- float in [-1.0, +1.0] for macro-sector opportunity

Usage
-----
  from jyotish.llm_context_enricher import enrich_career_context, build_chart_basics
  basics   = build_chart_basics(career_ctx, chart)
  enriched = enrich_career_context(career_ctx, basics)
  # enriched keys: weight_overrides, intent_tags, sector_modifier,
  #               career_theme_str, enrichment_ok
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jyotish_engine_v11_0")

# ---------------------------------------------------------------------------
# Phase 0 prompt template
# ---------------------------------------------------------------------------

_PHASE0_PROMPT = """You are a Vedic astrology career analysis assistant. Given the chart summary and career context below, output a JSON object with four keys:

1. "weight_overrides": a dict of sub-score adjustments (float deltas in range -0.05 to +0.05).
   Valid keys: career_activation, strength_product, functional_nature, house_activation,
               company_score, kp_cusp_score, jaimini_score, d10_alignment,
               yoga_rajayoga, yoga_viparita_ry
   Only include keys where adjustment is warranted. Omit all others.

2. "intent_tags": a list of strings identifying the primary career intent.
   Valid values: "promotion", "job_change", "business", "foreign", "stability",
                 "salary_hike", "career_switch"
   Return 1-3 tags in priority order.

3. "sector_modifier": a float from -1.0 to +1.0 rating the macro-sector opportunity.
   +1.0 = sector is booming globally. -1.0 = sector is contracting.

4. "career_theme_str": a 1-sentence theme label (max 12 words) summarising the career arc.

Chart summary
-------------
{chart_summary}

Career context
--------------
{career_context}

Return ONLY the JSON object. No explanation, no markdown fences."""

# ---------------------------------------------------------------------------
# Weight defaults and validation
# ---------------------------------------------------------------------------

_VALID_WEIGHT_KEYS = {
    "career_activation", "strength_product", "functional_nature",
    "house_activation", "company_score", "kp_cusp_score",
    "jaimini_score", "d10_alignment", "yoga_rajayoga", "yoga_viparita_ry",
}

_MAX_WEIGHT_DELTA = 0.05   # clamp each override to +-5% of base weight


def _validate_weight_overrides(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, float] = {}
    for k, v in raw.items():
        if k in _VALID_WEIGHT_KEYS:
            try:
                result[k] = max(-_MAX_WEIGHT_DELTA, min(_MAX_WEIGHT_DELTA, float(v)))
            except (TypeError, ValueError):
                pass
    return result


def _validate_intent_tags(raw: Any) -> List[str]:
    _valid = {
        "promotion", "job_change", "business", "foreign",
        "stability", "salary_hike", "career_switch",
    }
    if not isinstance(raw, list):
        return []
    return [str(t) for t in raw if str(t) in _valid][:3]


def _validate_sector_modifier(raw: Any) -> float:
    try:
        v = float(raw)
        return max(-1.0, min(1.0, v))
    except (TypeError, ValueError):
        return 0.0


def _validate_theme_str(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    words = str(raw).split()
    return " ".join(words[:12])


# ---------------------------------------------------------------------------
# Chart basics extraction
# ---------------------------------------------------------------------------

def build_chart_basics(career_ctx: Any, payload: Any) -> Dict[str, Any]:
    """Extract a concise chart-summary dict suitable for the Phase 0 prompt.

    Accepts either a NatalPayloadV2 instance or any object with matching attrs.
    Also accepts a TimelineChartInput (duck-typed).
    """
    basics: Dict[str, Any] = {}

    # Core identity
    basics["lagna_sign"]   = getattr(payload, "lagna_sign",   "") or ""
    basics["atmakaraka"]   = getattr(payload, "atmakaraka",   "") or ""
    basics["amatyakaraka"] = getattr(payload, "amatyakaraka", "") or ""
    basics["kp_h10"]       = float(getattr(payload, "kp_h10",      0.5) or 0.5)
    basics["d10_strength"] = float(getattr(payload, "d10_strength", 0.5) or 0.5)
    basics["current_age"]  = float(getattr(payload, "current_age",  0.0) or 0.0)

    # Dasha context
    dasha_seq = getattr(payload, "dasha_sequence", []) or []
    basics["dasha_sequence"] = dasha_seq[:5]   # first 5 periods for brevity

    # Active dasha lord (MD)
    active_md = ""
    age = basics["current_age"]
    try:
        for d in dasha_seq:
            sa = float(d.get("start_age", 0))
            ea = float(d.get("end_age", 999))
            if sa <= age < ea:
                active_md = d.get("lord", "")
                break
    except Exception as _dasha_err:   # C-4: log so dasha parse failures are visible
        logger.debug("C-4 build_chart_basics dasha parse error: %s", _dasha_err)
    basics["active_md"] = active_md

    # Yogas
    yogas = (
        getattr(payload, "detected_yogas", [])
        or getattr(payload, "yogas_present", [])
        or []
    )
    basics["yogas"] = list(yogas)[:8]

    # House lords summary
    hl = getattr(payload, "house_lords", {}) or {}
    basics["house_lords_10_1"] = {
        str(h): lord for h, lord in hl.items()
        if str(h) in ("1", "10", "6", "7", "11")
    }

    return basics


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> Optional[str]:
    """Try available LLM providers in order; return raw text or None."""
    # 1. Gemini via google-generativeai SDK
    try:
        import google.generativeai as genai  # type: ignore
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if api_key:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            text = resp.text.strip()
            if text:
                logger.debug("Phase 0 LLM response received via Gemini (%d chars)", len(text))
                return text
    except Exception as exc:
        logger.warning("Phase 0 LLM call failed via %s: %s", "Gemini", exc)

    # 2. OpenAI fallback
    try:
        import openai  # type: ignore
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0.2,
            )
            text = resp.choices[0].message.content.strip()
            if text:
                return text
    except Exception as exc:
        logger.warning("Phase 0 LLM call failed via %s: %s", "OpenAI", exc)

    return None


# ---------------------------------------------------------------------------
# Engine-default fallback (no LLM needed)
# ---------------------------------------------------------------------------

def _engine_defaults(career_ctx: Dict, chart_basics: Dict) -> Dict[str, Any]:
    """Rule-based fallback when LLM is unavailable."""
    intent_tags: List[str] = []
    desired   = str(career_ctx.get("desired_outcome", "")).lower()
    actively  = bool(career_ctx.get("actively_looking", False))
    on_notice = bool(career_ctx.get("on_notice_period", False))
    geo       = str(career_ctx.get("geographic_preference", "")).lower()
    emp_mode  = str(career_ctx.get("employment_mode", "")).lower()

    if desired in ("promotion", "hike", "increment"):
        intent_tags.append("promotion")
    if desired in ("job_change",) or on_notice or actively:
        intent_tags.append("job_change")
    if desired in ("business", "entrepreneurship", "startup") or emp_mode in ("self_employed", "business"):
        intent_tags.append("business")
    if "foreign" in desired or "abroad" in desired or geo in ("foreign", "overseas", "abroad"):
        intent_tags.append("foreign")
    if desired in ("stability", "settle"):
        intent_tags.append("stability")

    # Weight overrides based on chart quality signals
    overrides: Dict[str, float] = {}
    kp_h10  = chart_basics.get("kp_h10",      0.5)
    d10_str = chart_basics.get("d10_strength", 0.5)
    if kp_h10 >= 0.70:
        overrides["kp_cusp_score"] = 0.03
    if d10_str >= 0.70:
        overrides["d10_alignment"] = 0.03

    return {
        "weight_overrides": overrides,
        "intent_tags":      intent_tags[:3],
        "sector_modifier":  0.0,
        "career_theme_str": "",
        "enrichment_ok":    False,   # engine defaults, not LLM-enriched
    }


# ---------------------------------------------------------------------------
# JSON extraction from LLM response
# ---------------------------------------------------------------------------

def _parse_llm_json(raw: str) -> Optional[Dict]:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(line for line in lines if not line.startswith("```")).strip()
    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("Phase 0: JSON parse failed: %s -- raw: %s", exc, raw[:200])
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# =============================================================================
# GENUINE VALUE-ADD #2 — Free-Form Preference Parser (Pre-Scoring)
# =============================================================================

_PREFERENCE_PARSE_PROMPT = """\
You are a career counselor assistant. A student or professional has described their interests,
strengths, and constraints in natural language. Extract structured fields from their text.

Return ONLY a JSON object with these keys (omit any key if no signal exists):
  "interested_in":    list of strings — subjects, fields, or activities they enjoy or are curious about
  "already_excel_at": list of strings — things they are good at or have demonstrated skill in
  "avoid_domains":    list of strings — domains, subjects, or work types they explicitly dislike or want to avoid
  "preferred_work_style": one string — "analytical", "creative", "social", "hands_on", "leadership", or "research"
  "geographic_preference": one string — "india", "foreign", "remote", or "flexible" if mentioned
  "notes":            string — any other relevant context not captured above (max 20 words)

Rules:
  - Keep each item in "interested_in" and "already_excel_at" concise (1-3 words each).
  - Do NOT invent signals not present in the text.
  - Return ONLY the JSON object. No markdown, no explanation.

Free-form input:
\"\"\"{free_text}\"\"\"
"""

# Keyword maps for deterministic fallback (no LLM)
_INTEREST_KEYWORDS: Dict[str, List[str]] = {
    "computers":        ["computer science", "programming", "coding", "software", "IT"],
    "mathematics":      ["math", "maths", "mathematics", "calculus", "algebra", "statistics"],
    "biology":          ["biology", "bio", "life science", "genetics", "microbiology"],
    "physics":          ["physics", "mechanics", "optics", "quantum"],
    "chemistry":        ["chemistry", "chem", "organic", "biochemistry"],
    "art":              ["art", "drawing", "painting", "design", "creative", "sketch"],
    "music":            ["music", "singing", "instrument", "guitar", "piano"],
    "writing":          ["writing", "essay", "literature", "journalism", "content"],
    "business":         ["business", "entrepreneur", "startup", "commerce", "trade"],
    "medicine":         ["doctor", "medicine", "mbbs", "hospital", "clinical", "surgery"],
    "law":              ["law", "legal", "advocate", "lawyer", "court", "judiciary"],
    "teaching":         ["teaching", "education", "school", "tutor"],
    "sports":           ["sport", "cricket", "football", "athlete", "fitness", "gym"],
    "engineering":      ["engineering", "mechanical", "electrical", "civil", "build", "construct"],
    "data":             ["data", "analytics", "machine learning", "AI", "artificial intelligence"],
    "finance":          ["finance", "banking", "investment", "stock", "economy"],
    "psychology":       ["psychology", "counseling", "mental health", "behaviour"],
}

_AVOID_KEYWORDS: List[str] = [
    "hate", "dislike", "don't like", "dont like", "not interested", "avoid",
    "bad at", "not good at", "boring", "terrible at",
]

_EXCEL_KEYWORDS: Dict[str, List[str]] = {
    "math":          ["good at math", "strong in math", "excel in math", "love math"],
    "writing":       ["good writer", "strong writer", "writing skills"],
    "communication": ["public speaking", "communication", "presenting"],
    "analytical":    ["analytical", "logical", "problem-solving", "problem solver"],
    "creative":      ["creative", "imagination", "innovative"],
    "leadership":    ["leadership", "team lead", "captain", "managing"],
    "research":      ["research", "studying", "reading", "investigating"],
    "coding":        ["coding", "programming", "developer", "software"],
}


def _keyword_fallback(free_text: str) -> Dict[str, Any]:
    """Rule-based preference extraction when LLM is unavailable."""
    text_lower = free_text.lower()
    interested_in: List[str] = []
    avoid_domains: List[str] = []
    already_excel: List[str] = []

    for canonical, keywords in _INTEREST_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            in_avoid_ctx = any(
                f"{avoid} {kw}" in text_lower or f"{kw} {avoid}" in text_lower
                for avoid in _AVOID_KEYWORDS
                for kw in keywords
            )
            if in_avoid_ctx:
                avoid_domains.append(canonical)
            else:
                interested_in.append(canonical)

    for canonical, phrases in _EXCEL_KEYWORDS.items():
        if any(ph in text_lower for ph in phrases):
            already_excel.append(canonical)

    work_style = ""
    if any(w in text_lower for w in ("research", "study", "read", "investigate", "lab")):
        work_style = "research"
    elif any(w in text_lower for w in ("creative", "design", "art", "music", "imagine")):
        work_style = "creative"
    elif any(w in text_lower for w in ("people", "social", "team", "communicate", "teach")):
        work_style = "social"
    elif any(w in text_lower for w in ("build", "make", "hands", "workshop", "repair")):
        work_style = "hands_on"
    elif any(w in text_lower for w in ("lead", "manage", "organise", "startup", "founder")):
        work_style = "leadership"
    elif any(w in text_lower for w in ("logic", "analyse", "data", "math", "code", "solve")):
        work_style = "analytical"

    result: Dict[str, Any] = {}
    if interested_in:
        result["interested_in"] = interested_in[:8]
    if already_excel:
        result["already_excel_at"] = already_excel[:5]
    if avoid_domains:
        result["avoid_domains"] = avoid_domains[:5]
    if work_style:
        result["preferred_work_style"] = work_style

    if any(w in text_lower for w in ("abroad", "foreign", "overseas", "international", "usa", "uk", "canada")):
        result["geographic_preference"] = "foreign"
    elif any(w in text_lower for w in ("india", "home", "domestic", "hometown")):
        result["geographic_preference"] = "india"
    elif "remote" in text_lower:
        result["geographic_preference"] = "remote"

    result["_source"] = "keyword_fallback"
    return result


def parse_free_form_preferences(
    free_text: str,
    max_words: int = 500,
) -> Dict[str, Any]:
    """Parse free-form user input into structured preference fields.

    Converts natural language like:
      "I love computers and maths, hate outdoor work, good at problem-solving"
    into:
      {"interested_in": ["computers", "mathematics"], "avoid_domains": ["outdoor"],
       "already_excel_at": ["analytical"], "preferred_work_style": "analytical"}

    The returned dict can be used to populate payload fields before scoring:
      payload.interested_in    <- result["interested_in"]
      payload.already_excel_at <- result["already_excel_at"]

    Falls back to keyword extraction if LLM is unavailable.
    """
    if not free_text or not free_text.strip():
        return {}

    words = free_text.split()
    if len(words) > max_words:
        free_text = " ".join(words[:max_words]) + "..."
        logger.debug("parse_free_form_preferences: input truncated to %d words.", max_words)

    try:
        from .engine_io import _maybe_load_dotenv
        _maybe_load_dotenv()
    except Exception:
        pass

    _provider_name = os.getenv("LLM_PROVIDER", "gemini").lower()
    _LLM_PROVIDERS_LOCAL = {
        "gemini":    ("GEMINI_API_KEY",    "gemini-2.5-pro"),
        "anthropic": ("ANTHROPIC_API_KEY", "claude-haiku-4-5-20251001"),
        "openai":    ("OPENAI_API_KEY",    "gpt-4o-mini"),
    }
    _env_var, _default_model = _LLM_PROVIDERS_LOCAL.get(
        _provider_name, _LLM_PROVIDERS_LOCAL["gemini"]
    )
    api_key = os.getenv(_env_var)

    if not api_key:
        logger.debug("parse_free_form_preferences: no API key -- using keyword fallback.")
        return _keyword_fallback(free_text)

    prompt = _PREFERENCE_PARSE_PROMPT.format(free_text=free_text)
    raw: Optional[str] = None

    try:
        if _provider_name == "anthropic":
            import anthropic as _ant  # type: ignore
            client = _ant.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=_default_model, max_tokens=512, temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text if resp.content else None
        elif _provider_name == "gemini":
            from google import genai as _genai  # type: ignore
            from google.genai import types as _gt  # type: ignore
            gc = _genai.Client(api_key=api_key)
            resp = gc.models.generate_content(
                model=_default_model, contents=prompt,
                config=_gt.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=512,
                    temperature=0.0,
                ),
            )
            raw = resp.text
        else:
            import openai as _oai  # type: ignore
            oc = _oai.OpenAI(api_key=api_key)
            resp = oc.chat.completions.create(
                model=_default_model, max_tokens=512, temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content
    except Exception as exc:
        logger.warning("parse_free_form_preferences: LLM call failed -- %s. Using keyword fallback.", exc)
        return _keyword_fallback(free_text)

    parsed = _parse_llm_json(raw or "")
    if not parsed:
        logger.warning("parse_free_form_preferences: JSON parse failed -- using keyword fallback.")
        return _keyword_fallback(free_text)

    result: Dict[str, Any] = {}
    for list_key in ("interested_in", "already_excel_at", "avoid_domains"):
        raw_list = parsed.get(list_key, [])
        if isinstance(raw_list, list):
            result[list_key] = [str(v).strip() for v in raw_list if isinstance(v, str) and v.strip()][:10]

    _valid_styles = {"analytical", "creative", "social", "hands_on", "leadership", "research"}
    ws = str(parsed.get("preferred_work_style", "")).strip().lower()
    if ws in _valid_styles:
        result["preferred_work_style"] = ws

    _valid_geo = {"india", "foreign", "remote", "flexible"}
    geo = str(parsed.get("geographic_preference", "")).strip().lower()
    if geo in _valid_geo:
        result["geographic_preference"] = geo

    notes = str(parsed.get("notes", "")).strip()
    if notes:
        result["notes"] = " ".join(notes.split()[:20])

    result["_source"] = "llm"
    logger.info(
        "parse_free_form_preferences: parsed %d interests, %d strengths, %d avoids.",
        len(result.get("interested_in", [])),
        len(result.get("already_excel_at", [])),
        len(result.get("avoid_domains", [])),
    )
    return result



def enrich_career_context(
    career_ctx: Dict[str, Any],
    chart_basics: Dict[str, Any],
) -> Dict[str, Any]:
    """Run Phase 0 LLM enrichment and return calibration signals.

    Always returns a dict with keys:
        weight_overrides, intent_tags, sector_modifier, career_theme_str, enrichment_ok
    Falls back to rule-based defaults if LLM is unavailable.
    """
    defaults = _engine_defaults(career_ctx, chart_basics)

    chart_summary = json.dumps({
        "lagna":        chart_basics.get("lagna_sign", ""),
        "atmakaraka":   chart_basics.get("atmakaraka", ""),
        "amatyakaraka": chart_basics.get("amatyakaraka", ""),
        "active_md":    chart_basics.get("active_md", ""),
        "kp_h10":       chart_basics.get("kp_h10", 0.5),
        "d10_strength": chart_basics.get("d10_strength", 0.5),
        "yogas":        chart_basics.get("yogas", []),
        "house_lords":  chart_basics.get("house_lords_10_1", {}),
        "current_age":  chart_basics.get("current_age", 0),
    }, indent=2)

    career_context_str = json.dumps({
        k: v for k, v in career_ctx.items()
        if k not in ("_intent_tags", "_payload_ref", "warnings")
    }, indent=2, default=str)

    _PHASE0_PROMPT_LOCAL = """You are a Vedic astrology career analysis assistant. Given the chart summary and career context below, output a JSON object with four keys:

1. "weight_overrides": a dict of sub-score adjustments (float deltas in range -0.05 to +0.05).
   Valid keys: career_activation, strength_product, functional_nature, house_activation,
               company_score, kp_cusp_score, jaimini_score, d10_alignment,
               yoga_rajayoga, yoga_viparita_ry
   Only include keys where adjustment is warranted. Omit all others.

2. "intent_tags": a list of strings identifying the primary career intent.
   Valid values: "promotion", "job_change", "business", "foreign", "stability",
                 "salary_hike", "career_switch"
   Return 1-3 tags in priority order.

3. "sector_modifier": a float from -1.0 to +1.0 rating the macro-sector opportunity.
   +1.0 = sector is booming globally. -1.0 = sector is contracting.

4. "career_theme_str": a 1-sentence theme label (max 12 words) summarising the career arc.

Chart summary
-------------
{chart_summary}

Career context
--------------
{career_context}

Return ONLY the JSON object. No explanation, no markdown fences."""

    prompt = _PHASE0_PROMPT_LOCAL.format(
        chart_summary=chart_summary,
        career_context=career_context_str,
    )

    raw = _call_llm(prompt)
    if not raw:
        logger.debug("Phase 0: LLM returned empty -- using engine defaults.")
        return defaults

    parsed = _parse_llm_json(raw)
    if not parsed:
        return defaults

    result: Dict[str, Any] = {
        "weight_overrides": _validate_weight_overrides(parsed.get("weight_overrides", {})),
        "intent_tags":      _validate_intent_tags(parsed.get("intent_tags", [])),
        "sector_modifier":  _validate_sector_modifier(parsed.get("sector_modifier", 0.0)),
        "career_theme_str": _validate_theme_str(parsed.get("career_theme_str", "")),
    }

    if not result["intent_tags"]:
        result["intent_tags"] = defaults["intent_tags"]

    logger.info(
        "Phase 0 enrichment complete: tags=%s overrides=%s sector_mod=%.2f theme=\'%s\'",
        result["intent_tags"],
        result["weight_overrides"],
        result["sector_modifier"],
        result.get("career_theme_str", ""),
    )
    result["enrichment_ok"] = True
    return result
