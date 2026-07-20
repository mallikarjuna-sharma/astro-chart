"""JyotishAI — Career Timeline: input parsing, validation, and hard gates.

All gates are evaluated BEFORE any astrological computation.
Hard blocks return (False, error_message, None).
Soft warnings are attached to the returned context dict.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Dict, Any, Optional, Tuple

from jyotish.constants import (
    _ALLOWED_EMPLOYMENT_STATUS, _DESIGNATION_LEVELS,
    _DESIRED_OUTCOMES, _JOB_KARAKA_WEIGHTS,
)

# ── Age gate constants ────────────────────────────────────────────────────────
_AGE_HARD_BLOCK   = 20          # strictly below this → block
_AGE_LIMITED_MAX  = 22          # 20–22 inclusive → limited mode
_AGE_EARLY_MAX    = 27          # 23–27 → early career mode
# 28+ → full mode

# ── Retroactive validation window ────────────────────────────────────────────
_RETRO_MATCH_DAYS = 90          # ±90 days counts as a match

# ── desired_outcome aliases ──────────────────────────────────────────────────
# Maps common free-text/legacy values onto the canonical _DESIRED_OUTCOMES set
# instead of silently discarding unrecognised-but-meaningful intent.
_DESIRED_OUTCOME_ALIASES = {
    "role_change":     "job_change",
    "onsite":          "foreign_posting",
    "onsite_transfer": "foreign_posting",
    "increment":       "salary_hike",
    "hike":            "salary_hike",
    "raise":           "salary_hike",
    "growth":          "promotion",
    "career_growth":   "promotion",
    "senior_role":     "leadership_role",
    "management":      "leadership_role",
    "settle":          "stability",
    "settled":         "stability",
    "comeback":        "return_after_gap",
    "career_break_return": "return_after_gap",
}

# ── designation title → seniority level aliases ─────────────────────────────
# Maps common free-text job titles onto the canonical _DESIGNATION_LEVELS set
# instead of blanking the designation (and skipping designation gates) for
# any title that isn't already a bare level word.
_DESIGNATION_TITLE_TO_LEVEL = {
    "test engineer":      "junior",
    "qa engineer":        "junior",
    "software engineer":  "junior",
    "sde":                "junior",
    "developer":          "junior",
    "associate":          "junior",
    "analyst":            "junior",
    "senior engineer":    "senior",
    "senior developer":   "senior",
    "senior analyst":     "senior",
    "team lead":          "lead",
    "tech lead":          "lead",
    "technical lead":     "lead",
    "engineering manager": "manager",
    "manager":            "manager",
    # Exact keys below must be checked before the generic "manager"/"director"
    # substring keyword-fallback would otherwise match them, so senior
    # managers/associate directors aren't silently downgraded a level
    # (2026-07 fix) — dict lookup tries exact match first (see resolution
    # logic below), so having both "manager" and "senior manager" as
    # separate exact keys is safe and correct.
    "senior manager":     "senior_manager",
    "sr manager":         "senior_manager",
    "senior project manager": "senior_manager",
    "associate director": "senior_manager",
    "director":           "director",
    "vp":                 "csuite",
    "vice president":     "csuite",
    "cto":                "csuite",
    "ceo":                "csuite",
    "engineer":           "junior",
}



def _safe_int(value: Any) -> Optional[int]:
    """Safely cast value to int; return None if not convertible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _derive_career_intent(cc: Dict[str, Any]) -> str:
    """C-6: Synthesise a single career_intent string from career_context fields.

    Used by Phase 0 llm_context_enricher for intent_tags extraction.
    Returns one of: 'promotion', 'job_change', 'business', 'foreign', 'stability',
    'salary_hike', 'career_switch', or '' (unspecified).
    """
    desired = str(cc.get("desired_outcome", "")).lower()
    actively = bool(cc.get("actively_looking", False))
    on_notice = bool(cc.get("on_notice_period", False))
    geo = str(cc.get("geographic_preference", "")).lower()
    emp_mode = str(cc.get("employment_mode", "")).lower()

    if desired in ("promotion", "hike", "increment"):
        return "promotion"
    if desired in ("job_change",) or on_notice or actively:
        return "job_change"
    if desired in ("business", "entrepreneurship", "startup") or emp_mode in ("self_employed", "business"):
        return "business"
    if "foreign" in desired or "abroad" in desired or geo in ("foreign", "overseas", "abroad"):
        return "foreign"
    if desired in ("stability", "settle"):
        return "stability"
    if desired in ("salary_hike", "salary"):
        return "salary_hike"
    if desired in ("career_switch", "switch"):
        return "career_switch"
    return desired   # pass through raw value (may be empty)


def parse_career_context(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract career_context block from the full chart JSON payload.

    Accepts two locations: top-level 'career_context' key, or nested inside
    'student_context' (for backward compatibility with existing chart JSONs).
    """
    cc = data.get("career_context") or {}
    if not cc:
        # fallback: some fields may live inside student_context
        sc = data.get("student_context", {})
        cc = sc.get("career_context", {})

    _designation = str(
        cc.get("designation", "") or cc.get("current_designation", "")
    ).lower().strip()
    _current_age = data.get("current_age", cc.get("current_age"))
    _dob = (
        data.get("dob", "")
        or data.get("student_context", {}).get("dob", "")
        or cc.get("dob", "")
    )
    # BUGFIX (2026-07-19, user-reported job_debug.json audit): when the chart
    # JSON doesn't carry an explicit "current_age" field (the common case --
    # most chart JSONs only supply dob), _current_age stayed None all the way
    # through to the output context, even though dob + current_date were both
    # available to derive it. engine_io.py already computes the payload-level
    # current_age via jyotish.astro._calc_age(dob, system_config.current_date)
    # -- mirror that here so career_context.current_age is never silently
    # None when it's derivable.
    if _current_age is None and _dob:
        from jyotish.astro import _calc_age
        _cd = data.get("system_config", {}).get("current_date", "") or cc.get("current_date", "")
        _current_age = _calc_age(_dob, _cd)

    ctx: Dict[str, Any] = {
        # ── Tier 1 (required) ──
        "employment_status":     str(cc.get("employment_status", "")).lower().strip(),
        "current_date":          (data.get("system_config", {}).get("current_date", "")
                                  or cc.get("current_date", "")),
        # ── Tier 2 (optional but unlock calibration) ──
        "join_date":             cc.get("join_date", ""),           # ISO date YYYY-MM or YYYY-MM-DD
        "last_promotion_date":   cc.get("last_promotion_date", ""),
        "last_hike_date":        cc.get("last_hike_date", ""),
        "designation":           _designation,
        "current_designation":   _designation,
        "years_experience":      _safe_int(cc.get("years_experience")),
        "industry_sector":       str(cc.get("industry_sector", "")).lower().strip(),
        "company_type":          str(cc.get("company_type", "default")).lower().strip(),
        "career_events":         list(cc.get("career_events", []) or []),
        "career_timeline":       list(cc.get("career_timeline", []) or []),
        # User-reported gap fix (2026-07): free-text known-events schema
        # ({"date": ..., "event": "Joined EY"}), whitelisted through so
        # `_retroactive_validate` (timeline.py) can match real life events
        # against predicted windows even without a formal event_type.
        "known_events":          list(cc.get("known_events", []) or []),
        # 2026-07-08: additional optional career-context pass-through fields
        # (pure wiring, no calculation) — mirror the same .get()-with-default
        # pattern used for the fields immediately above. All gracefully
        # default (empty list/string) when absent from the input JSON, so old
        # chart files without these keys never crash. known_events entries
        # may now also carry event_type/company_type/role_level (in addition
        # to the existing date/event keys already consumed by
        # timeline.py::_retroactive_validate).
        "major_role_changes":                list(cc.get("major_role_changes", []) or []),
        "manager_change_dates":              list(cc.get("manager_change_dates", []) or []),
        "onsite_or_foreign_client_periods":  list(cc.get("onsite_or_foreign_client_periods", []) or []),
        "notice_period_history":             list(cc.get("notice_period_history", []) or []),
        "job_search_periods":                list(cc.get("job_search_periods", []) or []),
        "birth_time_precision":  str(
            cc.get("birth_time_precision", "")
            or data.get("birth_time_precision", "")
            or data.get("pyhora_calculations", {}).get("birth_time_precision", "unknown")
        ).lower().strip(),
        "current_age":           _safe_int(_current_age),
        "dob":                   _dob,
        "macro_override":        cc.get("macro_override", None),
        "actively_looking":      bool(cc.get("actively_looking", False)),
        "on_notice_period":      bool(cc.get("on_notice_period", False)),
        "desired_outcome":       str(cc.get("desired_outcome", "")).lower().strip(),
        "geographic_preference": str(cc.get("geographic_preference", "open")).lower().strip(),
        "is_family_business":    bool(cc.get("is_family_business", False)),
        # F-4: employment_mode preserved so llm_context_enricher._engine_defaults can
        # detect business/self-employed intent downstream.
        "employment_mode":       str(cc.get("employment_mode", "")).lower().strip(),
        # C-6: career_intent — synthesised from desired_outcome + employment mode for
        # use by Phase 0 enricher intent_tags extraction (llm_context_enricher.py)
        "career_intent":         _derive_career_intent(cc),
        # ── Internal ──
        "warnings":              [],
    }

    # Normalise on_notice_period → employment_status override
    if ctx["on_notice_period"] and ctx["employment_status"] == "employed":
        ctx["employment_status"] = "on_notice_period"

    # Normalise desired_outcome — keep the raw value the user/caller supplied
    # so downstream consumers (or a human auditor) can see intent even when
    # it doesn't match our canonical taxonomy, and map common aliases onto
    # canonical values instead of silently discarding them.
    ctx["desired_outcome_raw"] = ctx["desired_outcome"]
    if ctx["desired_outcome"] not in _DESIRED_OUTCOMES:
        aliased = _DESIRED_OUTCOME_ALIASES.get(ctx["desired_outcome"])
        if aliased is not None:
            ctx["desired_outcome"] = aliased
        else:
            ctx["desired_outcome"] = ""   # will be treated as unspecified

    # Normalise company_type
    if ctx["company_type"] not in _JOB_KARAKA_WEIGHTS:
        ctx["company_type"] = "default"
    if ctx["birth_time_precision"] not in {"exact", "approximate", "unknown"}:
        ctx["birth_time_precision"] = "unknown"

    # BUGFIX (2026-07-19, user-reported job_debug.json audit): flag when the
    # chart JSON's system_config.current_date has drifted far from the real
    # "today". Every "is_current"/"is_past" AD/PD flag and the annual transit
    # outlook's is_current_year are all anchored on this one field (see
    # engine_io.py's re-use of it for both current_age and the timeline/
    # micro-timing "today" anchor), so a stale value here can silently pick
    # the wrong current period near a month/year boundary. This is a soft
    # warning only -- current_date is still honoured as provided (chart JSONs
    # legitimately pin a specific "as of" date for reproducible/backtest
    # runs) -- it just makes the drift visible instead of silent.
    if ctx["current_date"]:
        try:
            _cd_parsed = datetime.fromisoformat(str(ctx["current_date"])[:10]).date()
            _drift_days = abs((date.today() - _cd_parsed).days)
            if _drift_days > 14:
                ctx["warnings"].append(
                    f"career_context.current_date ({ctx['current_date']}) is "
                    f"{_drift_days} day(s) away from today's real date "
                    f"({date.today().isoformat()}). AD/PD 'is_current' and "
                    f"annual-outlook 'is_current_year' flags are anchored on "
                    f"this value -- refresh system_config.current_date in the "
                    f"chart JSON if this run should reflect the real present."
                )
        except (ValueError, TypeError):
            pass

    return ctx


def validate_career_context(
    ctx: Dict[str, Any],
    age: float,
    lagna_sign: str = "",
    birth_time_known: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """Apply all hard gates and return (is_valid, error_or_warning, mode).

    mode is one of: 'limited' | 'early_career' | 'full' | None (on block)
    """
    status = ctx.get("employment_status", "")

    # ── Hard block 1: Age ────────────────────────────────────────────────────
    if age < _AGE_HARD_BLOCK:
        return (
            False,
            f"Career Timeline requires minimum age {_AGE_HARD_BLOCK}. "
            f"Current age {age:.1f}. Use the Field Selection module for students.",
            None,
        )

    # ── Hard block 2: Employment status ─────────────────────────────────────
    if status not in _ALLOWED_EMPLOYMENT_STATUS:
        _block_msgs = {
            "student":         "This module is for working professionals. "
                               "Use the Field Selection module for students.",
        }
        msg = _block_msgs.get(status,
              f"Employment status '{status}' is not supported by this module. "
              "Supported: employed, on_notice_period, unemployed, self_employed, business_owner, freelancer.")
        return (False, msg, None)

    if status in {"self_employed", "business_owner", "freelancer"}:
        warnings = ctx.setdefault("warnings", [])
        warnings.append("Self-directed employment detected - switching to forecast mode.")
        ctx["_self_directed"] = True
        return (True, "", "forecast")

    # ── Soft gate 3: Unemployed age check → limited mode (GAP-2 FIX) ─────────
    # Previously a hard block; now returns limited mode so young job-seekers
    # can still receive FIRST_JOB timeline events.
    if status == "unemployed" and age < 22:
        return (True, "", "limited")

    # ── Determine mode ───────────────────────────────────────────────────────
    if age <= _AGE_LIMITED_MAX:
        mode = "limited"        # only entry-window predictions
    elif age <= _AGE_EARLY_MAX:
        mode = "early_career"   # entry + first growth window
    else:
        mode = "full"

    # ── Soft warnings (attach to ctx, do not block) ──────────────────────────
    warnings = ctx.setdefault("warnings", [])

    if not birth_time_known:
        warnings.append(
            "Birth time unknown — Lagna is uncertain. "
            "All predictions will be marked INDICATIVE."
        )

    desig = ctx.get("designation", "")
    if desig and desig not in _DESIGNATION_LEVELS:
        ctx["designation_title_raw"] = desig
        resolved_level = _DESIGNATION_TITLE_TO_LEVEL.get(desig)
        if resolved_level is None:
            for _keyword, _level in _DESIGNATION_TITLE_TO_LEVEL.items():
                if _keyword in desig:
                    resolved_level = _level
                    break
        if resolved_level is not None:
            ctx["designation"] = resolved_level
        else:
            warnings.append(f"Designation '{desig}' not recognised. Designation gates will be skipped.")
            ctx["designation"] = ""

    if not ctx.get("desired_outcome"):
        # Fall back to career_intent, then the raw pre-alias value, before
        # concluding that no outcome intent is available at all.
        _fallback = ctx.get("career_intent") or ctx.get("desired_outcome_raw")
        if _fallback:
            _fallback = str(_fallback).lower().strip()
            if _fallback not in _DESIRED_OUTCOMES:
                _fallback = _DESIRED_OUTCOME_ALIASES.get(_fallback, "")
            if _fallback:
                ctx["desired_outcome"] = _fallback

    if not ctx.get("desired_outcome"):
        warnings.append("No desired_outcome provided — output will show all event types without reordering.")

    yoe = ctx.get("years_experience")
    if yoe is None:
        warnings.append("years_experience not provided — LEADERSHIP_EXPANSION gate will use age as proxy.")

    # ── Astrological tension flag (chart has strong business indicators) ──────
    # Checked by timeline.py._check_business_tension().
    # Threshold: if MD or AD lord are enterprise planets and desired_outcome implies
    # salaried preference, flag the tension.

    # F-1 fix: was missing — function fell off with implicit None return, causing
    # engine.py unpack `_, _, _tl_mode = validate_career_context(...)` to crash.
    return (True, "", mode)


def parse_iso_date(date_str: str):
    """Parse YYYY-MM-DD or YYYY-MM format. Returns date or None."""
    if not date_str:
        return None
    s = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def compute_confidence_tier(
    career_ctx: Dict[str, Any],
    birth_time_known: bool,
    retro_matches: int,
    transit_data_available: bool = True,
) -> Dict[str, Any]:
    """
    Compute a confidence tier for the career timeline output.

    RECONSTRUCTION NOTE (2026-07-07): this function's body was found
    TRUNCATED at the source-file level (the .py file itself ended mid-
    docstring, mid-word). A newer compiled .pyc cache for this exact module
    was still present and loadable, so the compiled bytecode was recovered
    and disassembled (dis.dis) to reconstruct this function faithfully —
    same scoring weights, same caveat strings, same tier thresholds as the
    bytecode actually encoded. This is a restoration of lost source, not a
    new design. See jyotish/web_report.py's own similar reconstruction note
    on generate_career_timeline_report() for the matching "corruption
    pattern" found in a second module this same session.

    Factors:
      1. Birth time precision — KP sub-lords shift every 4-12 min; unknown time
         degrades sub-lord reliability and cuspal accuracy.
      2. Retroactive match rate — if past dasha windows matched declared career
         events, the chart is well-calibrated for forward prediction.
      3. Career context completeness — years_experience, current_designation,
         desired_outcome all present improves reliability (not scored
         directly in the recovered bytecode below; kept as documented
         context for future extension).

    Returns a dict: {"score": int, "tier": str, "label": str, "caveats": [...]}.
    """
    score = 50
    caveats: List[str] = []

    birth_precision = career_ctx.get("birth_time_precision", "unknown") or "unknown"

    if birth_time_known and birth_precision == "exact":
        score += 20
    elif birth_precision == "approximate":
        score -= 10
        caveats.append("Birth time is approximate — KP sub-lord predictions may shift.")
    elif birth_precision == "unknown":
        score -= 25
        caveats.append(
            "Birth time unknown — KP cusp analysis is unavailable; "
            "predictions rely on whole-sign lords only."
        )

    # GAP 4 fix (2026-07-07 follow-up audit, user-reported): `past_events`
    # used to count ONLY the structured `career_events`/`career_timeline`
    # list, silently ignoring the legacy single-value fields
    # (join_date/last_promotion_date/last_hike_date) and the free-text
    # `known_events` list — even though _retroactive_validate() in
    # timeline.py DOES check those legacy fields (see its "1. Legacy
    # 3-field check" section) and can genuinely set retro_matches=1 from
    # them. That mismatch is exactly why a chart like Lakshman Kumar's
    # (which supplies join_date + last_promotion_date but no
    # career_events[] list) could show retro_matches=1 on the block while
    # this function's "No past career events provided" caveat fired anyway
    # — past_events was 0 by this narrow count even though 2 real
    # past-event data points (and 1 confirmed match) genuinely existed.
    # Fixed by counting every source _retroactive_validate() itself reads.
    _legacy_event_fields = ("join_date", "last_promotion_date", "last_hike_date")
    _legacy_events_provided = sum(1 for _f in _legacy_event_fields if career_ctx.get(_f))
    _structured_events = career_ctx.get("career_events", []) or career_ctx.get("career_timeline", []) or []
    _known_events = career_ctx.get("known_events", []) or []
    past_events = _legacy_events_provided + len(_structured_events) + len(_known_events)

    if past_events == 0:
        score -= 5
        caveats.append("No past career events provided — retroactive validation skipped.")
        tier = "MODERATE"
    elif retro_matches >= 2:
        match_rate = retro_matches / max(past_events, 1)
        if match_rate >= 0.6:
            score += 20
            tier = "STRONG"
        elif match_rate >= 0.4:
            score += 10
            tier = "MODERATE"
        else:
            score += 5
            tier = "MODERATE"
    elif retro_matches == 1:
        score += 5
        caveats.append(
            f"Only {retro_matches} retroactive match out of {past_events} provided past "
            "event(s) — chart calibration is partial; insufficient for high-confidence calibration."
        )
        tier = "MODERATE"
    else:
        score -= 10
        caveats.append(
            "No retroactive matches found — forward predictions have higher "
            "uncertainty for this chart."
        )
        tier = "CALIBRATION_MISMATCH"

    # BUG FIX (2026-07-05, restored alongside this reconstruction): a chart
    # with no transit data available at all should not be shown as STRONG
    # confidence even if birth time + retro-match scoring alone would say
    # so — caps the tier by one step per the caller-side comment in
    # timeline.py where transit_data_available is computed.
    if not transit_data_available and tier == "STRONG":
        tier = "MODERATE"
        caveats.append("Transit data unavailable for this chart — confidence capped at MODERATE.")

    score = max(0, min(100, score))

    # GAP 4 fix (2026-07-07 follow-up audit): structured retro_validation
    # block — surfaces the SAME events_provided/events_matched counts used
    # above (not new/duplicate data) as an explicit dict so the report can
    # render a consistent confidence-cap explanation next to the banner
    # instead of only prose in `caveats`.
    if past_events == 0:
        _retro_reason = "No past career events provided — retroactive validation skipped."
    elif past_events == 1:
        _retro_reason = "Only one confirmed event; insufficient for high-confidence calibration."
    else:
        _retro_reason = (
            f"{retro_matches} of {past_events} provided past event(s) matched a predicted "
            "period; confidence scales with match coverage."
        )
    retro_validation = {
        "events_provided": past_events,
        "events_matched":  int(retro_matches or 0),
        "confidence_cap":  "MODERATE" if past_events <= 1 else tier,
        "reason":          _retro_reason,
    }

    return {
        "score": score,
        "tier": tier,
        "label": tier.replace("_", " ").title(),
        "caveats": caveats,
        # GAP 4 fix (2026-07-07 follow-up audit): structured, consistent
        # retro-validation summary — see comment above where it is built.
        "retro_validation": retro_validation,
    }
