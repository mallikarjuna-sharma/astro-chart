"""JyotishAI — LLM Pre-Scoring Context Enricher (Phase 0)

Pipeline position: called ONCE, BEFORE build_career_timeline() runs.

Purpose
-------
The 7 scoring weights in timeline._score_period() are fixed module constants
(career_activation=0.27, kp_cusp_score=0.12, ...). They apply identically
to a startup CTO and a government bureaucrat — a structural blindspot.

Phase 0 fixes this with one cheap LLM call (claude-haiku / gpt-4o-mini)
that reads the career context + chart basics and returns:

  intent_tags       — 2-4 semantic career-intent labels
                      (e.g. ["leadership", "technical_expertise"])
                      used by _classify_event() as tiebreaker in the
                      ambiguous score band 0.50–0.68

  weight_overrides  — up to 3 weight adjustments (±20% of defaults)
                      applied inside _score_period() via the llm_context
                      dict that build_career_timeline() accepts

  career_theme_str  — one-sentence career narrative theme injected into
                      each AD-level LLM prompt in llm_narrative_builder.py
                      so all 12 narratives share a coherent through-line

  sector_modifier   — float 0.80–1.20 applied on top of macro_score for
                      this specific sector × dasha combination

Safety rails
------------
- All weight overrides are clamped to ±20% of the default value
- LLM failure → empty dict returned → engine uses defaults unchanged
- intent_tags validated against a fixed whitelist (no hallucinated tags)

Public API
----------
  enrich_career_context(career_ctx, chart_basics) -> Dict[str, Any]
  build_chart_basics(career_ctx, payload)          -> Dict[str, Any]
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jyotish_engine_v11_0")

# ---------------------------------------------------------------------------
# Default weights mirror the module-level constants in timeline.py
# These are the baseline that overrides are applied relative to.
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS: Dict[str, float] = {
    "career_activation":  0.27,
    "strength_product":   0.20,
    "functional_nature":  0.15,
    "house_activation":   0.11,
    "kp_cusp_score":      0.12,
    "jaimini_score":      0.10,
    "company_score":      0.05,
}

_MAX_DELTA     = 0.20   # maximum absolute delta on any single weight
_MAX_OVERRIDES = 3      # LLM may adjust at most 3 weights per call

# ---------------------------------------------------------------------------
# Valid intent tags — fixed whitelist (LLM cannot hallucinate outside this)
# ---------------------------------------------------------------------------

_VALID_INTENT_TAGS = frozenset({
    "leadership",
    "technical_expertise",
    "financial_growth",
    "foreign_exposure",
    "entrepreneurship",
    "stability",
    "creative_domain",
    "research_academia",
    "public_service",
    "career_transition",
    "income_maximisation",
    "skill_upgrade",
})

# ---------------------------------------------------------------------------
# LLM system prompt — calibration persona
# ---------------------------------------------------------------------------

_ENRICHER_SYSTEM_PROMPT = """\
You are a Vedic Astrology career analytics calibration engine.
Given a client's career context and chart basics, output a JSON object that
calibrates the deterministic career scoring engine for this specific person.

Your output drives real scoring math. Be precise and concise.

RULES
1. intent_tags: choose 2–4 tags from the valid_intent_tags list provided.
   Pick tags that best describe what this person wants from their career.
2. weight_overrides: adjust at most 3 keys from valid_weight_keys.
   Each override must be within ±0.20 of the provided default.
   Omit keys you are not adjusting.
   Guidance:
     - High-level professionals → raise jaimini_score, raise kp_cusp_score
     - Technical/specialist → raise career_activation, raise strength_product
     - Government/stability → raise functional_nature, lower company_score
     - Entrepreneur → raise company_score, raise house_activation
     - Foreign/expat → raise kp_cusp_score
3. career_theme_str: one sentence, max 20 words. Capture the core career
   theme that should run through all period narratives.
4. sector_modifier: float 0.80–1.20.
   >1.0 = sector tailwinds this dasha period.
   <1.0 = sector headwinds.

Return ONLY valid JSON with keys: intent_tags, weight_overrides,
career_theme_str, sector_modifier. No explanation, no markdown.
"""

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_enricher_prompt(
    career_ctx: Dict[str, Any],
    chart_basics: Dict[str, Any],
) -> str:
    return (
        f"CLIENT CAREER CONTEXT\n"
        f"  Designation:      {career_ctx.get('designation', 'Professional')}\n"
        f"  Industry sector:  {career_ctx.get('industry_sector', 'Corporate')}\n"
        f"  Desired outcome:  {career_ctx.get('desired_outcome', 'CAREER_GROWTH')}\n"
        f"  Years experience: {career_ctx.get('years_experience', 'not specified')}\n"
        f"  Employment:       {career_ctx.get('employment_status', 'employed')}\n"
        f"\n"
        f"CHART BASICS\n"
        f"  Active MD lord:   {chart_basics.get('active_md', 'unknown')}\n"
        f"  Active AD lord:   {chart_basics.get('active_ad', 'unknown')}\n"
        f"  AK (soul):        {chart_basics.get('atmakaraka', 'unknown')}\n"
        f"  AmK (career):     {chart_basics.get('amatyakaraka', 'unknown')}\n"
        f"  Lagna sign:       {chart_basics.get('lagna_sign', 'unknown')}\n"
        f"  H10 lord:         {chart_basics.get('h10_lord', 'unknown')}\n"
        f"  Active yogas:     {', '.join(chart_basics.get('active_yogas', [])) or 'none'}\n"
        f"\n"
        f"valid_intent_tags: {sorted(_VALID_INTENT_TAGS)}\n"
        f"valid_weight_keys: {list(_DEFAULT_WEIGHTS.keys())}\n"
        f"weight_defaults:   {_DEFAULT_WEIGHTS}\n"
        f"\n"
        f"Return JSON only."
    )


# ---------------------------------------------------------------------------
# Response validators / sanitisers
# ---------------------------------------------------------------------------

def _clamp_weight_overrides(raw: Any) -> Dict[str, float]:
    """Clamp each override to ±_MAX_DELTA of default; drop unknown keys."""
    if not isinstance(raw, dict):
        return {}
    clamped: Dict[str, float] = {}
    for key, value in list(raw.items())[:_MAX_OVERRIDES]:
        default = _DEFAULT_WEIGHTS.get(key)
        if default is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        lo = max(0.0,  default - _MAX_DELTA)
        hi = min(0.60, default + _MAX_DELTA)
        clamped[key] = round(max(lo, min(hi, v)), 4)
    return clamped


def _validate_intent_tags(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, str) and t in _VALID_INTENT_TAGS][:4]


def _validate_sector_modifier(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 1.0
    return round(max(0.80, min(1.20, v)), 3)


def _validate_theme_str(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    # Trim to 200 chars; strip newlines
    return raw.replace("\n", " ").strip()[:200]


# ---------------------------------------------------------------------------
# Sync LLM call — uses the provider priority from llm.py
# ---------------------------------------------------------------------------

def _call_enricher_llm(prompt: str) -> str:
    """Make one cheap synchronous LLM call. Returns raw text or '{}'."""
    from .llm import _LLM_PROVIDERS, _maybe_load_dotenv

    _maybe_load_dotenv()

    provider_name  = os.getenv("LLM_PROVIDER", "auto").lower()
    model_override = os.getenv("LLM_MODEL", "")

    # Provider resolution order: env var → Anthropic key → OpenAI key → Gemini
    provider_order = (
        [provider_name] if provider_name != "auto"
        else ["anthropic", "openai", "gemini"]
    )

    for pname in provider_order:
        prov = _LLM_PROVIDERS.get(pname)
        if not prov:
            continue
        env_var, default_model, call_fn = prov
        api_key = os.getenv(env_var, "")
        if not api_key:
            continue

        # Use a cheap fast model for Phase 0 calibration
        _cheap: Dict[str, str] = {
            "anthropic": "claude-haiku-4-5-20251001",
            "openai":    "gpt-5.4-mini",
            "gemini":    "gemini-2.0-flash",
        }
        model = model_override or _cheap.get(pname, default_model)

        # For non-OpenAI providers, wrap into the combined prompt format
        full_prompt = (
            f"[SYSTEM]\n{_ENRICHER_SYSTEM_PROMPT}\n\n"
            f"[USER]\n{prompt}\n\n"
            f"Respond with valid JSON only."
        )

        try:
            if pname == "openai":
                # OpenAI: use response_format=json_object for clean output
                import openai as _openai
                client = _openai.OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0.1,
                    max_completion_tokens=400,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _ENRICHER_SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                )
                return resp.choices[0].message.content or "{}"
            else:
                # Anthropic / Gemini: single string prompt
                return call_fn(full_prompt, api_key, model)
        except Exception as exc:
            logger.warning("Phase 0 LLM call failed via %s: %s", pname, exc)
            continue

    return "{}"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_chart_basics(career_ctx: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    """Extract minimal chart facts needed for Phase 0 enrichment.

    Designed to be called from engine_io.parse_json_payload() where the
    full NatalPayloadV2 object is available, before build_career_timeline().
    """
    active_md, active_ad = "", ""
    try:
        from .astro import _get_active_dasha_lord
        age       = float(getattr(payload, "current_age", 0) or 0)
        dasha_seq = getattr(payload, "dasha_sequence", []) or []
        active_md = _get_active_dasha_lord(dasha_seq, age) or ""
        for d in dasha_seq:
            s, e = float(d.get("start_age", 0)), float(d.get("end_age", 999))
            if s <= age < e:
                for ad in d.get("antardashas", []):
                    as_, ae = float(ad.get("start_age", 0)), float(ad.get("end_age", 999))
                    if as_ <= age < ae:
                        active_ad = ad.get("lord", "")
                        break
                break
    except Exception:
        pass

    yogas = (
        getattr(payload, "detected_yogas", [])
        or getattr(payload, "yogas_present", [])
        or []
    )
    hl    = getattr(payload, "house_lords", {}) or {}

    return {
        "active_md":    active_md,
        "active_ad":    active_ad,
        "atmakaraka":   getattr(payload, "atmakaraka", "") or "",
        "amatyakaraka": getattr(payload, "amatyakaraka", "") or "",
        "lagna_sign":   getattr(payload, "lagna_sign", "") or "",
        "h10_lord":     hl.get("10", "") or hl.get(10, ""),
        "active_yogas": list(yogas)[:5],
    }


def enrich_career_context(
    career_ctx: Dict[str, Any],
    chart_basics: Dict[str, Any],
) -> Dict[str, Any]:
    """Phase 0: one LLM call before scoring; returns calibration dict.

    Returns dict with keys:
      intent_tags       List[str]       — semantic intent labels
      weight_overrides  Dict[str,float] — scoring weight adjustments
      career_theme_str  str             — narrative through-line
      sector_modifier   float           — sector tailwind/headwind factor

    Returns {} on any failure (engine uses default weights / no tags).
    """
    prompt = _build_enricher_prompt(career_ctx, chart_basics)

    raw = _call_enricher_llm(prompt)
    if not raw or raw.strip() == "{}":
        logger.debug("Phase 0: LLM returned empty — using engine defaults.")
        return {}

    # Strip markdown fences if the provider ignored the json_object instruction
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Phase 0: JSON parse failed: %s — raw: %s", exc, raw[:200])
        return {}

    result: Dict[str, Any] = {
        "intent_tags":      _validate_intent_tags(data.get("intent_tags", [])),
        "weight_overrides": _clamp_weight_overrides(data.get("weight_overrides", {})),
        "career_theme_str": _validate_theme_str(data.get("career_theme_str", "")),
        "sector_modifier":  _validate_sector_modifier(data.get("sector_modifier", 1.0)),
    }

    logger.info(
        "Phase 0 enrichment complete: tags=%s overrides=%s sector_mod=%.2f theme='%s'",
        result["intent_tags"],
        result["weight_overrides"],
        result["sector_modifier"],
        result["career_theme_str"][:60],
    )
    return result
