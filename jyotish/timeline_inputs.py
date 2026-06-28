"""JyotishAI — Career Timeline: input parsing, validation, and hard gates.

All gates are evaluated BEFORE any astrological computation.
Hard blocks return (False, error_message, None).
Soft warnings are attached to the returned context dict.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Dict, Any, Optional, Tuple

from .constants import (
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

    ctx: Dict[str, Any] = {
        # ── Tier 1 (required) ──
        "employment_status":     str(cc.get("employment_status", "")).lower().strip(),
        "current_date":          (data.get("system_config", {}).get("current_date", "")
                                  or cc.get("current_date", "")),
        # ── Tier 2 (optional but unlock calibration) ──
        "join_date":             cc.get("join_date", ""),           # ISO date YYYY-MM or YYYY-MM-DD
        "last_promotion_date":   cc.get("last_promotion_date", ""),
        "last_hike_date":        cc.get("last_hike_date", ""),
        "designation":           str(cc.get("designation", "")).lower().strip(),
        "years_experience":      _safe_int(cc.get("years_experience")),
        "industry_sector":       str(cc.get("industry_sector", "")).lower().strip(),
        "company_type":          str(cc.get("company_type", "default")).lower().strip(),
        "actively_looking":      bool(cc.get("actively_looking", False)),
        "on_notice_period":      bool(cc.get("on_notice_period", False)),
        "desired_outcome":       str(cc.get("desired_outcome", "")).lower().strip(),
        "geographic_preference": str(cc.get("geographic_preference", "open")).lower().strip(),
        "is_family_business":    bool(cc.get("is_family_business", False)),
        # ── Internal ──
        "warnings":              [],
    }

    # Normalise on_notice_period → employment_status override
    if ctx["on_notice_period"] and ctx["employment_status"] == "employed":
        ctx["employment_status"] = "on_notice_period"

    # Normalise desired_outcome
    if ctx["desired_outcome"] not in _DESIRED_OUTCOMES:
        ctx["desired_outcome"] = ""   # will be treated as unspecified

    # Normalise company_type
    if ctx["company_type"] not in _JOB_KARAKA_WEIGHTS:
        ctx["company_type"] = "default"

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
        warnings.append(f"Designation '{desig}' not recognised. Designation gates will be skipped.")
        ctx["designation"] = ""

    if not ctx.get("desired_outcome"):
        warnings.append("No desired_outcome provided — output will show all event types without reordering.")

    yoe = ctx.get("years_experience")
    if yoe is None:
        warnings.append("years_experience not provided — LEADERSHIP_EXPANSION gate will use age as proxy.")

    # ── Astrological tension flag (chart has strong business indicators) ──────
    # Checked by timeline.py at runtime against H7 strength; flag placeholder here.
    ctx["_business_tension_check"] = True

    return (True, "", mode)


def compute_confidence_tier(
    ctx: Dict[str, Any],
    birth_time_known: bool,
    retro_matches: int,          # 0, 1, 2, or 3
) -> str:
    """Assign confidence tier based on data quality and retroactive validation."""
    if not birth_time_known:
        return "INDICATIVE"

    tier2_count = sum([
        bool(ctx.get("join_date")),
        bool(ctx.get("last_promotion_date")),
        bool(ctx.get("last_hike_date")),
        bool(ctx.get("designation")),
        ctx.get("years_experience") is not None,
        bool(ctx.get("industry_sector")),
        bool(ctx.get("desired_outcome")),
    ])

    if retro_matches >= 2:
        return "VALIDATED" if retro_matches == 2 else "VALIDATED_STRONG"
    if retro_matches == 0 and tier2_count >= 3:
        # Data provided but nothing matches — flag mismatch
        return "CALIBRATION_MISMATCH"
    if tier2_count >= 5:
        return "HIGH"
    if tier2_count >= 2:
        return "STANDARD"
    return "LOW"


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_iso_date(s: str) -> Optional[date]:
    """Parse YYYY-MM-DD or YYYY-MM into a date (day defaults to 1)."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
