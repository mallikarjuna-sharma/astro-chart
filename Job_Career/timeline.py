"""JyotishAI — Career Timeline Engine (Job Professionals Only).

Deterministic by default: Python computes all period boundaries, scores,
transit flags, event classifications, and confidence tiers. The LLM receives
a pre-structured block and writes only the narrative prose UNLESS the caller
opts into TimelineConfig(scoring_mode="llm_calibrated", allow_llm_...=True),
in which case Phase 0 LLM output (weight_overrides/intent_tags/sector_modifier)
is also allowed to influence scoring. Default TimelineConfig() keeps scoring
fully deterministic and LLM-free.

Public entry points:
    TimelineChartInput           -- dataclass of all chart fields required
    TimelineChartInput.from_payload(payload) -- factory from NatalPayloadV2
    TimelineConfig                -- controls LLM-scoring isolation + horizon mode
    build_career_timeline(chart, eff_strengths, career_ctx, mode, config=None) -> List[Dict]

Returns a list of PeriodBlock dicts sorted by start_date.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field as dc_field
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Optional, Any, Tuple

from jyotish.constants import (
    _VIMSHOTTARI_YEARS, _VIMSHOTTARI_ORDER,
    _FUNCTIONAL_NATURE, _JOB_KARAKA_WEIGHTS,
    _JOB_HOUSE_ROLE, _DESIGNATION_LEVELS,
    _SIGN_LORD, _NAKSHATRA_LORD,
    _DEBIL_SIGN,   # B2/B4 fix: D1 debilitation detection for PD affliction + H2 qualifier
)
from .timeline_inputs import parse_iso_date, _RETRO_MATCH_DAYS
from .job_loss import classify_adverse_event, career_risk_report  # adverse-event subsystem (job loss framework)
from .astro_enhancer import (
    AstroEnhancer, EnhancerInput, EnhancerResult,
    build_enhancer_input_from_payload, enhancer_score_delta,
    _jupiter_aspect_houses_set, _saturn_aspect_houses_set, _mars_aspect_houses,
)
# GAP FIX (2026-08-21, remediation plan item 2.3, FINAL_VS_V13_ASTROLOGICAL_
# COVERAGE_AUDIT.md P0 #1): reuse the SAME cusp-verification check
# Field_Determination/field_methods/kp.py already gates its KP score with,
# so this module's own KP career-cusp field-ranking signal
# (_kp_career_cusp_score, called below) doesn't grant unverified KP cusps
# full authority either.
from jyotish.kp_audit import audit_kp_cusps
# C-1: Shadbala-SBC manifestation modifier (lazy import to avoid circular deps)
def _compute_sbc_natal_mod(chart: Any) -> float:
    """Return a Shadbala Chakra natal strength modifier in [0.90, 1.10].

    Converts SBC natal strength (0–100) to a ±10% multiplicative modifier:
        strength=100 → +10%, strength=50 → 0%, strength=0 → -10%.
    Fails silently to 1.0 (neutral) if sbc is unavailable.
    """
    try:
        from .sbc import SarvatobhadraEngine
        sbc = SarvatobhadraEngine(chart)
        strength = sbc.compute_natal_strength()  # 0–100
        mod = 1.0 + 0.20 * (strength / 100.0 - 0.50)  # ±10%
        return max(0.90, min(1.10, mod))
    except Exception:
        return 1.0


# -----------------------------------------------------------------------------
# TimelineChartInput: explicit chart data contract for the career timeline engine
# -----------------------------------------------------------------------------

@dataclass
class TimelineChartInput:
    """All chart fields required by the career timeline engine.

    Construct via ``TimelineChartInput.from_payload(payload)`` from a full
    NatalPayloadV2, or populate fields directly for testing/standalone use.

    Passing this instead of the full NatalPayloadV2 makes the timeline
    engine data dependencies explicit and testable in isolation.
    """
    # Birth / identity
    dob: str = ""                                            # "YYYY-MM-DD"
    lagna_sign: str = ""                                     # e.g. "Aries"

    # Dasha sequence (list of dicts with md_planet/lord + start_age/end_age)
    dasha_sequence: list = dc_field(default_factory=list)

    # KP system
    kp_cusps: dict = dc_field(default_factory=dict)          # {"H10": {"sub_lord": ..., "star_lord": ...}, ...}
    kp_significators: dict = dc_field(default_factory=dict)  # {"Saturn": {"level_1": [...], ...}, ...}

    # Jaimini karakas
    atmakaraka: str = ""
    amatyakaraka: str = ""
    kn_rao_jaimini: dict = dc_field(default_factory=dict)    # full jaimini dict

    # House positions
    planet_house: dict = dc_field(default_factory=dict)      # {"Sun": 1, "Moon": 3, ...}
    house_lords: dict = dc_field(default_factory=dict)       # {"1": "Mars", "10": "Saturn", ...}

    # Divisional charts & Ashtakavarga
    d10_house_occupancy: dict = dc_field(default_factory=dict)   # {"10": ["Mars", "Saturn"], ...}
    d10_strength: float = 0.0
    d24_house_occupancy: dict = dc_field(default_factory=dict)   # D24 Siddhamsha: {"4": ["Jupiter"], ...}
    sav_points_houses: dict = dc_field(default_factory=dict)     # {"H10": 34.0, ...}

    # Transit positions (snapshot of today — engine extrapolates per-AD dynamically)
    transit_house_positions: dict = dc_field(default_factory=dict)  # {"Jupiter": 10, ...}

    # Birth time quality: 0 = exact, >5 = uncertain, >30 = approximate.
    # When > 5, KP sub-lord and D10 weights are mathematically degraded.
    birth_time_uncertainty_minutes: int = 0

    # ── Enhancer fields (34-gap fix suite) ───────────────────────────────────
    # All optional — engine degrades gracefully when absent.
    planet_natal_degrees: dict = dc_field(default_factory=dict)  # {planet: ecliptic_deg}
    planet_transit_degrees: dict = dc_field(default_factory=dict)
    planet_sign: dict = dc_field(default_factory=dict)           # {planet: sign_name}
    planet_signs: dict = dc_field(default_factory=dict)          # payload-compatible alias
    planet_nakshatras: dict = dc_field(default_factory=dict)     # {planet: nakshatra name}
    planet_longitudes: dict = dc_field(default_factory=dict)     # {planet: absolute longitude}
    retrograde_planets: list = dc_field(default_factory=list)    # ["Saturn", "Venus", ...]
    pav_data: dict = dc_field(default_factory=dict)              # {planet: {house_str: bindus}}
    varga_dignities: dict = dc_field(default_factory=dict)       # {varga: {planet: dignity}}
    d10_lagna_sign: str = ""
    d10_house_lords: dict = dc_field(default_factory=dict)
    d27_planet_strengths: dict = dc_field(default_factory=dict)  # {planet: "strong"/"weak"/...}
    planet_nakshatra_lord: dict = dc_field(default_factory=dict) # {planet: nak_lord}
    lagna_star_lord: str = ""
    lagna_sub_lord: str = ""
    moon_star_lord: str = ""
    moon_sub_lord: str = ""
    day_lord: str = ""
    karakamsha_sign: str = ""    # AK's sign in D9 — Karakamsha Lagna
    moon_nakshatra_pada_num: int = 0   # 1-108 for Yogini Dasha
    moon_nakshatra_lord: str = ""      # for Ashtottari
    moon_nakshatra: str = ""
    # D9 Navamsha planet dignities — needed for d9_modifier in _score_period
    # Without this field the D9 modifier is always 0.0 (G1 fix)
    d9_planet_dignities: dict = dc_field(default_factory=dict)  # {planet: "exalted"/"own"/"debilitated"/...}

    # Jaimini Arudha of H10 — public career image (used in Jaimini scoring)
    a10_sign: str = ""   # sign in which A10 falls (e.g. "Aries")

    # BUG B FIX (2026-07-08): NatalPayloadV2 already carries these (computed in
    # engine_io.py from ephemeris.py/ashtakavarga.py) but TimelineChartInput —
    # the object actually dataclasses.asdict()-dumped to the CLI JSON output for
    # --mode career/both — never declared these fields, so from_payload() never
    # copied them across and they silently never appeared in the printed JSON.
    ghati_lagna_sign: str = ""                                    # Ghati Lagna sign
    sree_lagna_sign: str = ""                                     # Sree Lagna sign
    bav_points: dict = dc_field(default_factory=dict)             # {planet: {house_str: bindu}}

    @classmethod
    def from_payload(cls, payload) -> "TimelineChartInput":
        """Extract all timeline-relevant fields from a NatalPayloadV2 or compatible object."""
        jdata = (getattr(payload, "kn_rao_jaimini", None)
                 or getattr(payload, "kn_rao_jaimini_data", None)
                 or {})
        return cls(
            dob=getattr(payload, "dob", "") or "",
            lagna_sign=getattr(payload, "lagna_sign", "") or "",
            # B-7: prefer full dasha (with AD dates) but fall back to stripped sequence
            dasha_sequence=(
                getattr(payload, "vimshottari_dasha_full", None)
                or getattr(payload, "dasha_sequence", None)
                or []
            ),
            kp_cusps=getattr(payload, "kp_cusps", {}) or {},
            kp_significators=getattr(payload, "kp_significators", {}) or {},
            atmakaraka=getattr(payload, "atmakaraka", "") or "",
            amatyakaraka=getattr(payload, "amatyakaraka", "") or "",
            kn_rao_jaimini=jdata if isinstance(jdata, dict) else {},
            planet_house=getattr(payload, "planet_house", {}) or {},
            house_lords=getattr(payload, "house_lords", {}) or {},
            d10_house_occupancy=getattr(payload, "d10_house_occupancy", {}) or {},
            d10_strength=float(getattr(payload, "d10_strength", 0.0) or 0.0),
            d24_house_occupancy=getattr(payload, "d24_house_occupancy", {}) or {},
            sav_points_houses=getattr(payload, "sav_points_houses", {}) or {},
            transit_house_positions=getattr(payload, "transit_house_positions", {}) or {},
            birth_time_uncertainty_minutes=int(
                getattr(payload, "birth_time_uncertainty_minutes", 0) or 0
            ),
            # Enhancer fields
            planet_natal_degrees=getattr(payload, "planet_natal_degrees", {}) or {},
            planet_transit_degrees=getattr(payload, "planet_transit_degrees", {}) or {},
            planet_sign=(
                getattr(payload, "planet_sign", None)
                or getattr(payload, "planet_signs", None)
                or {}
            ),
            planet_signs=getattr(payload, "planet_signs", {}) or getattr(payload, "planet_sign", {}) or {},
            planet_nakshatras=getattr(payload, "planet_nakshatras", {}) or {},
            planet_longitudes=getattr(payload, "planet_longitudes", {}) or {},
            retrograde_planets=list(getattr(payload, "retrograde_planets", []) or []),
            pav_data=getattr(payload, "pav_data", {}) or {},
            varga_dignities=getattr(payload, "varga_dignities", {}) or {},
            d10_lagna_sign=getattr(payload, "d10_lagna_sign", "") or "",
            d10_house_lords=getattr(payload, "d10_house_lords", {}) or {},
            d27_planet_strengths=getattr(payload, "d27_planet_strengths", {}) or {},
            planet_nakshatra_lord=getattr(payload, "planet_nakshatra_lord", {}) or {},
            lagna_star_lord=getattr(payload, "lagna_star_lord", "") or "",
            lagna_sub_lord=getattr(payload, "lagna_sub_lord", "") or "",
            moon_star_lord=getattr(payload, "moon_star_lord", "") or "",
            moon_sub_lord=getattr(payload, "moon_sub_lord", "") or "",
            day_lord=getattr(payload, "day_lord", "") or "",
            karakamsha_sign=getattr(payload, "karakamsha_sign", "") or "",
            moon_nakshatra_pada_num=int(getattr(payload, "moon_nakshatra_pada_num", 0) or 0),
            moon_nakshatra_lord=getattr(payload, "moon_nakshatra_lord", "") or "",
            moon_nakshatra=getattr(payload, "moon_nakshatra", "") or "",
            # G1 fix: wire D9 dignities so d9_modifier is non-zero when data is present
            d9_planet_dignities=getattr(payload, "d9_planet_dignities", {}) or {},
            # Jaimini A10 (10th Arudha) sign — career image indicator
            a10_sign=getattr(payload, "a10_sign", "") or "",
            # BUG B FIX (2026-07-08): wire through the real ephemeris/ashtakavarga
            # values already present on NatalPayloadV2 (see class docstring above).
            ghati_lagna_sign=getattr(payload, "ghati_lagna_sign", "") or "",
            sree_lagna_sign=getattr(payload, "sree_lagna_sign", "") or "",
            bav_points=getattr(payload, "bav_points", {}) or {},
        )


@dataclass
class TimelineConfig:
    """Controls whether LLM (Phase 0) output may influence deterministic scoring.

    The module docstring claims the engine is "fully deterministic" — that is
    only true when allow_llm_* flags are False (the default). When any flag is
    True, scoring becomes llm_calibrated and two runs may differ depending on
    LLM availability/output. horizon_mode selects the past-window policy:
      "forecast"   -- fixed _WINDOW_PAST_MONTHS lookback (default; used for
                       live predictions shown to the user).
      "validation" -- past window is derived from the earliest actual career
                       event so a validator LLM/backtest sees full history,
                       matching what career_validation_prompt.py tells it.
    """
    scoring_mode: str = "deterministic"          # "deterministic" | "llm_calibrated"
    allow_llm_weight_overrides: bool = False
    allow_llm_intent_tags: bool = False
    allow_llm_sector_modifier: bool = False
    horizon_mode: str = "forecast"                # "forecast" | "validation"

    def __post_init__(self) -> None:
        # scoring_mode="deterministic" (the default) is a hard override: it
        # forces all LLM-influence flags off regardless of what was passed,
        # so a caller cannot accidentally leave LLM influence on believing
        # the engine is deterministic. To enable LLM calibration, callers
        # must explicitly pass scoring_mode="llm_calibrated" AND the
        # individual allow_llm_* flags they want on.
        if self.scoring_mode != "llm_calibrated":
            self.allow_llm_weight_overrides = False
            self.allow_llm_intent_tags = False
            self.allow_llm_sector_modifier = False


# -- Window constants ──────────────────────────────────────────────────────────
_WINDOW_PAST_MONTHS  = 12   # 1 year back
_WINDOW_FUTURE_YEARS = 4    # 4 years forward (allows up to 12 periods)
_MAX_OUTPUT_PERIODS  = 25   # T1 fix: increased cap to show full current MD
# GAP 7 fix: stratified cooldown windows — each event tier has its own suppression duration.
_COOLDOWN_MONTHS_BY_TIER: Dict[str, int] = {
    "BREAKTHROUGH":         24,   # 24 months — rarest event, longest suppression
    "PROMOTION":            18,   # 18 months — title jumps cannot stack in quick succession
    "LEADERSHIP_EXPANSION": 12,   # 12 months — scope broadening, shorter cooldown
    "INCOME":                6,   # 6 months — salary events can recur on appraisal cycles
}

# ── Scoring weights ───────────────────────────────────────────────────────────
# GAP 1 fix: D10 Dashamsha added as an 8th weighted sub-score (_W_D10_ALIGNMENT = 0.07).
# Calibration v6: All 10 scoring terms (8 primaries + 2 yoga) now form a single
# budget summing to 1.00.  KP trimmed 0.25→0.17 to absorb the yoga weights.
# Primary-8 sum = 0.92; yoga sum = 0.08; grand total = 1.00 ✓
_W_CAREER_ACTIVATION = 0.20   # unchanged
_W_STRENGTH_PRODUCT  = 0.13   # unchanged
_W_FUNCTIONAL_NATURE = 0.13   # unchanged
_W_HOUSE_ACTIVATION  = 0.10   # unchanged
_W_COMPANY_KARAKA    = 0.05   # unchanged
_W_KP_CUSP_SCORE     = 0.17   # v6: trimmed 0.25→0.17 to fund yoga weight budget
_W_JAIMINI_SCORE     = 0.07   # unchanged
_W_D10_ALIGNMENT     = 0.07   # GAP 1: D10 Dashamsha career chart (unchanged)
# primary-8 sum = 0.20+0.13+0.13+0.10+0.05+0.17+0.07+0.07 = 0.92

# ── Explicit yoga primary weights (within the 1.00 budget) ───────────────────
# These ARE part of the primary budget — yoga_rajayoga_sub and yoga_vry_sub
# are 0–1 sub-scores multiplied by these weights and added to combined.
_W_YOGA_RAJAYOGA = 0.05    # within budget: 0.92 + 0.05 + 0.03 = 1.00 ✓
_W_YOGA_VRY      = 0.03    # within budget

# ── KP house career-relevance weights (for house_activation sub-score) ────────
_HOUSE_CAREER_WEIGHT = {
    10: 1.0, 6: 0.9, 11: 0.8, 2: 0.7,
    1: 0.5, 3: 0.4, 9: 0.4, 12: 0.3,
    4: 0.2, 5: 0.2, 8: -0.3,   # H8 penalises
}

# ── Designation experience thresholds ────────────────────────────────────────
_DESIGNATION_MIN_EXP = {
    "junior": 0, "mid": 2, "senior": 4, "lead": 5,
    "manager": 6, "senior_manager": 8, "director": 10, "csuite": 15,
}

# ── Item #2 (2026-07-07): senior-manager+ career-stage event-bias weighting ──
# Small, chart-agnostic biases applied to the matching sub-score for
# manager/director/csuite/lead designation levels only (junior/mid/senior get
# nothing). Magnitudes kept small and consistent with other bonus scales in
# this file (see _amk_exalted_bonus / _amk_activation_bonus above).
_DESIGNATION_EVENT_BIAS = {
    "manager":        {"PROMOTION": 0.06, "LEADERSHIP_EXPANSION": 0.10, "JOB_CHANGE": -0.02},
    "senior_manager": {"PROMOTION": 0.07, "LEADERSHIP_EXPANSION": 0.13, "JOB_CHANGE": -0.03},
    "director":       {"PROMOTION": 0.04, "LEADERSHIP_EXPANSION": 0.12, "JOB_CHANGE": -0.03},
    "csuite":         {"PROMOTION": 0.02, "LEADERSHIP_EXPANSION": 0.14, "JOB_CHANGE": -0.04},
    "lead":           {"PROMOTION": 0.08, "LEADERSHIP_EXPANSION": 0.08, "JOB_CHANGE": -0.01},
}

# ── MD-level career themes (for narrative generation) ────────────────────────
_EVENT_NARRATIVE: Dict[str, str] = {
    "PROMOTION": "Strong career-house activation supports upward movement in designation.",
    "BREAKTHROUGH": "Exceptional dasha-transit alignment — major career leap possible.",
    "LEADERSHIP_EXPANSION": "Expanding sphere of authority; leadership visibility increases.",
    "INCOME_INFLECTION": "H11/H2 activation points to a meaningful salary or income shift.",
    "JOB_CHANGE": "H6/H12 energy and dasha planet favour a role transition.",
    "FOREIGN_POSTING": "H9/H12 activation with Rahu influence supports overseas opportunity.",
    "SALARY_HIKE": "H2/H11 lords active; negotiation or appraisal cycle likely to be rewarding.",
    "SKILL_UPGRADE_PHASE": "H3/H5 period — invest in certifications, learning, or new tools.",
    "TRANSITION": "First major career entry window — foundational choices made here echo long.",
    "RE_ENTRY": "Re-entry conditions are astrologically supported; proactive application advised.",
    "FIRST_JOB": "Strong first-career entry window — initiate applications, build professional network, and align with your natural planetary strengths.",
    "H8_TRANSFORMATION_ACTIVE": "8th-house transformation energy accompanies this period; embrace change and trust the rebirth process.",
    "RISK_PERIOD": "Adverse dasha-transit combination; consolidate position, avoid risky moves.",
    "JOB_LOSS": "Multiple independent layers confirm a service break: operating dasha lords signify 5/8/12/9, the 2/6/10/11 cusp sub-lords fail to protect, D10 career houses are afflicted, and malefic transits hit the career axis. Treat as a high involuntary-exit / income-interruption window.",
    "FORCED_EXIT": "Strong loss signature, but Jupiter or D10 6/11 still protect income continuity — likely a forced role change with continuity rather than outright unemployment. Line up the next role before exiting.",
    "BURNOUT_EXIT": "6/8/12 axis with Moon/Saturn/Ketu and sustained pressure (Sade Sati / burden flags) — exit driven by stress, health, or dissatisfaction rather than external termination. Protect health; do not resign impulsively.",
    "ROLE_RESTRUCTURING": "H6/H10 activation with an 8th-house shock, same employer — reporting line, team, or title changes rather than a break in service. Renegotiate scope; retention is likely.",
    "AUTHORITY_SHIFT": "H10-H8 link suggests structural or organisational change affecting role.",
    "STABILITY": "Consolidation phase — solid ground for performance and skill deepening.",
    "GROWTH": "Gradual positive trajectory; steady efforts yield compounding returns.",
    "CALIBRATION": "Mixed signals; outcomes depend heavily on effort and timing within the window.",
    "SANDHI_PERIOD": "Dasha Chidra (junction period) — transition zone between major cycles; outcomes arrive with delay; best used for preparation rather than action.",
    "EQUITY_EVENT": "H2/H5/H11 convergence supports meaningful asset, equity, or investment crystallisation.",
    "LATERAL_MOVE": "H6/H12 combined with service indicators — an industry or role shift at comparable level; network and domain leverage are key.",
    "ENTREPRENEURSHIP_WINDOW": "H1/H3 self-will + house lords active — favourable for independent ventures, consulting, or fractional leadership.",
}


_MD_THEMES: Dict[str, str] = {
    "Sun":     "authority, institutional recognition, and solar clarity of purpose",
    "Moon":    "public visibility, emotional intelligence, and adaptable positioning",
    "Mars":    "initiative, technical execution, and competitive drive",
    "Mercury": "communication, analytical acuity, and intellectual versatility",
    "Jupiter": "expansion, wisdom, leadership elevation, and advisory influence",
    "Venus":   "relationship-driven growth, financial acuity, and aesthetic intelligence",
    "Saturn":  "disciplined authority, systemic thinking, and structured upward progress",
    "Rahu":    "unconventional ascent, ambition, foreign opportunity, and disruptive innovation",
    "Ketu":    "specialised mastery, research depth, and non-mainstream professional paths",
}

_MD_CAREER_KEYWORDS: Dict[str, List[str]] = {
    "Sun":     ["leadership visibility", "institutional recognition", "authority roles", "promotions"],
    "Moon":    ["public-facing roles", "team dynamics", "adaptability", "client relations"],
    "Mars":    ["technical delivery", "project leadership", "competitive bids", "operational authority"],
    "Mercury": ["strategic communication", "analytics", "IT project delivery", "cross-functional roles"],
    "Jupiter": ["advisory positions", "mentoring roles", "ethical leadership", "international exposure"],
    "Venus":   ["stakeholder management", "people leadership", "financial roles", "creative strategy"],
    "Saturn":  ["governance", "process ownership", "large-team management", "compliance and risk"],
    "Rahu":    ["digital transformation", "foreign collaboration", "network leverage", "rapid advancement"],
    "Ketu":    ["technical research", "niche expertise", "backend systems", "independent contribution"],
}

# ── Jaimini karaka role labels for narrative ──────────────────────────────────
_JAIMINI_ROLE: Dict[str, str] = {
    "AmK": ("Amatyakaraka (career minister) — this Mahadasha activates the core professional "
            "calling with the highest Jaimini authority for career elevation."),
    "AK":  ("Atmakaraka (soul karaka) — this Mahadasha connects career growth to the deepest "
            "vocational soul purpose and karmic mission."),
    "BK":  ("Bhatrukaraka — supports initiative, collaboration with colleagues, and bold professional moves."),
    "MK":  ("Matrukaraka — emotionally intelligent career phase; public-facing and nurturing roles benefit."),
    "PK":  ("Putrakaraka — advisory, creative, and intelligence-driven functions are favoured."),
    "GK":  ("Gnatikaraka — requires careful navigation around competition and workplace conflict."),
    "DK":  ("Darakaraka — partnership-oriented; business development and collaborative leadership supported."),
}


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 — Convert dasha sequence to calendar dates
# ═════════════════════════════════════════════════════════════════════════════

def _dasha_calendar(dasha_seq: List[Dict], dob: date) -> List[Dict]:
    """Convert age-based dasha sequence to calendar dates.

    For each MD entry in dasha_seq:
      - Uses age_start / age_end if present (from pyhora JSON)
      - Expands antardashas proportionally using Vimshottari fractions
    Returns flat list of dicts with keys:
        md_lord, ad_lord, start_date, end_date, md_start, md_end
    """
    result = []
    for md in dasha_seq:
        md_lord  = md.get("md_planet") or md.get("lord") or md.get("planet", "")
        if not md_lord:
            continue
        if md.get("start_date") and md.get("end_date"):
            md_start = parse_iso_date(str(md.get("start_date"))[:10])
            md_end = parse_iso_date(str(md.get("end_date"))[:10])
        else:
            # ── GAP 4 fix (2026-07-07, user-reported): precision bug ──────
            # This branch previously ALWAYS derived md_start/md_end from
            # age_start/age_end, which the source pyhora JSON supplies
            # rounded to only 1 decimal place (e.g. Jupiter MD age_end=53.4).
            # The SAME JSON entry also carries start_year/end_year (2 decimal
            # places of year-fraction, e.g. 2031.74) whenever pyhora provides
            # it — strictly more precise, and previously never read at all.
            # Using the coarser field silently discarded real precision the
            # source data already had, compounding date-drift across every
            # antardasha inside the Mahadasha (this is what produced the
            # user-reported truncated/short-looking Jupiter-Rahu AD window).
            # See jyotish/gap_corrections_career_timeline_2026_07.py's
            # precise_md_bounds() + module docstring "GAP 4 root-cause
            # finding" for the full honest account (including what this fix
            # does NOT claim to resolve exactly).
            _precise_bounds = None
            try:
                from .gap_corrections_career_timeline_2026_07 import precise_md_bounds
                _precise_bounds = precise_md_bounds(md, dob)
            except Exception:
                _precise_bounds = None
            if _precise_bounds:
                md_start, md_end = _precise_bounds
            else:
                # Support both key conventions: payload uses start_age/end_age
                _s = md.get("start_age") if md.get("start_age") is not None else md.get("age_start", 0)
                _e = md.get("end_age")   if md.get("end_age")   is not None else md.get("age_end",   0)
                md_start = _age_to_date(dob, float(_s or 0))
                md_end   = _age_to_date(dob, float(_e or 0))
        if not md_start or not md_end:
            continue
        if md_start >= md_end:
            continue

        # Expand antardashas
        sub = md.get("antardashas", [])
        if sub:
            for ad in sub:
                ad_lord = ad.get("lord") or ad.get("planet") or ad.get("ad_planet", "")
                if not ad_lord:
                    continue
                if ad.get("start_date") and ad.get("end_date"):
                    ad_start = parse_iso_date(str(ad.get("start_date"))[:10])
                    ad_end = parse_iso_date(str(ad.get("end_date"))[:10])
                else:
                    ad_start = _age_to_date(dob, float(ad.get("age_start", 0)))
                    ad_end   = _age_to_date(dob, float(ad.get("age_end",   0)))
                if not ad_start or not ad_end:
                    continue
                result.append({
                    "md_lord": md_lord, "ad_lord": ad_lord,
                    "start_date": ad_start, "end_date": ad_end,
                    "md_start": md_start, "md_end": md_end,
                })
        else:
            # No antardasha data — compute proportionally
            result.extend(_expand_antardashas(md_lord, md_start, md_end))
    return result


# Stable public cross-package adapters. Domain packages must import these
# names rather than the underscored implementation helpers above.
def build_dasha_calendar(dasha_seq: List[Dict], dob: date) -> List[Dict]:
    return _dasha_calendar(dasha_seq, dob)


def expand_pratyantardashas(md_lord: str, ad_lord: str, ad_start: date, ad_end: date) -> List[Dict]:
    return _expand_pratyantardashas(md_lord, ad_lord, ad_start, ad_end)


def get_dynamic_transits(period_start: date, period_end: date, chart: Any, lagna_sign: str, today: date) -> List[str]:
    return _get_dynamic_transits(period_start, period_end, chart, lagna_sign, today)


def jaimini_career_score(md_lord: str, ad_lord: str, payload: Any):
    return _jaimini_career_score(md_lord, ad_lord, payload)


def _expand_antardashas(md_lord: str, md_start: date, md_end: date) -> List[Dict]:
    """Compute antardasha periods from MD period using Vimshottari proportions."""
    md_years = _VIMSHOTTARI_YEARS.get(md_lord, 0)
    if md_years == 0:
        return [{"md_lord": md_lord, "ad_lord": md_lord,
                 "start_date": md_start, "end_date": md_end,
                 "md_start": md_start, "md_end": md_end}]

    total_days = (md_end - md_start).days
    # Start sequence from md_lord within Vimshottari order
    try:
        start_idx = _VIMSHOTTARI_ORDER.index(md_lord)
    except ValueError:
        start_idx = 0

    result = []
    cursor = md_start
    for i in range(9):
        ad_lord = _VIMSHOTTARI_ORDER[(start_idx + i) % 9]
        ad_years = _VIMSHOTTARI_YEARS.get(ad_lord, 0)
        # G4 fix: removed dead first computation; AD fraction = ad_years / 120 of MD total
        ad_days = round(total_days * ad_years / 120.0)
        ad_end = min(cursor + timedelta(days=ad_days), md_end)
        if cursor < ad_end:
            result.append({
                "md_lord": md_lord, "ad_lord": ad_lord,
                "start_date": cursor, "end_date": ad_end,
                "md_start": md_start, "md_end": md_end,
            })
        cursor = ad_end
        if cursor >= md_end:
            break
    # Fill any remainder into the last AD
    if result and cursor < md_end:
        result[-1]["end_date"] = md_end
    return result


# RECONSTRUCTION NOTE (2026-07-07): _expand_pratyantardashas() and
# _expand_sookshams() (both called further down in build_career_timeline())
# were found missing entirely — same corruption pattern documented at other
# reconstruction points this session. Both follow the EXACT SAME proportional
# Vimshottari-fraction expansion algorithm already implemented immediately
# above in _expand_antardashas() (start from the parent lord's own position
# in _VIMSHOTTARI_ORDER, walk 9 lords, split by ad_years/120 of the parent
# span) — just one dasha level deeper each time (AD -> PD -> Sookshama).
# This is a faithful continuation of the same already-established algorithm,
# not a new design, and its call-site usage (reading pd_lord/start_date/
# end_date as full ISO date strings) was confirmed by reading every call
# site in build_career_timeline() before writing this.

def _expand_pratyantardashas(md_lord: str, ad_lord: str, ad_start: date, ad_end: date) -> List[Dict]:
    """Compute Pratyantardasha (3rd-level dasha) periods within one
    Antardasha, using the same Vimshottari proportional-fraction method as
    _expand_antardashas() above, one level deeper."""
    if isinstance(ad_start, str):
        ad_start = parse_iso_date(ad_start[:10]) or ad_start
    if isinstance(ad_end, str):
        ad_end = parse_iso_date(ad_end[:10]) or ad_end
    if not isinstance(ad_start, date) or not isinstance(ad_end, date) or ad_start >= ad_end:
        return []

    total_days = (ad_end - ad_start).days
    try:
        start_idx = _VIMSHOTTARI_ORDER.index(ad_lord)
    except ValueError:
        start_idx = 0

    result = []
    cursor = ad_start
    for i in range(9):
        pd_lord = _VIMSHOTTARI_ORDER[(start_idx + i) % 9]
        pd_years = _VIMSHOTTARI_YEARS.get(pd_lord, 0)
        pd_days = round(total_days * pd_years / 120.0)
        pd_end = min(cursor + timedelta(days=pd_days), ad_end)
        if cursor < pd_end:
            result.append({
                "md_lord": md_lord, "ad_lord": ad_lord, "pd_lord": pd_lord,
                "start_date": cursor.isoformat(), "end_date": pd_end.isoformat(),
            })
        cursor = pd_end
        if cursor >= ad_end:
            break
    if result and cursor < ad_end:
        result[-1]["end_date"] = ad_end.isoformat()
    return result


def _expand_sookshams(pd_lord: str, pd_start: date, pd_end: date) -> List[Dict]:
    """Compute Sookshama Dasha (4th-level, 3-40 day precision) periods within
    one Pratyantardasha, using the same Vimshottari proportional-fraction
    method as _expand_antardashas()/_expand_pratyantardashas() above, one
    level deeper still."""
    if isinstance(pd_start, str):
        pd_start = parse_iso_date(pd_start[:10]) or pd_start
    if isinstance(pd_end, str):
        pd_end = parse_iso_date(pd_end[:10]) or pd_end
    if not isinstance(pd_start, date) or not isinstance(pd_end, date) or pd_start >= pd_end:
        return []

    total_days = (pd_end - pd_start).days
    try:
        start_idx = _VIMSHOTTARI_ORDER.index(pd_lord)
    except ValueError:
        start_idx = 0

    result = []
    cursor = pd_start
    for i in range(9):
        sk_lord = _VIMSHOTTARI_ORDER[(start_idx + i) % 9]
        sk_years = _VIMSHOTTARI_YEARS.get(sk_lord, 0)
        sk_days = round(total_days * sk_years / 120.0)
        sk_end = min(cursor + timedelta(days=sk_days), pd_end)
        if cursor < sk_end:
            result.append({
                "pd_lord": pd_lord, "sk_lord": sk_lord,
                "start_date": cursor.isoformat(), "end_date": sk_end.isoformat(),
            })
        cursor = sk_end
        if cursor >= pd_end:
            break
    if result and cursor < pd_end:
        result[-1]["end_date"] = pd_end.isoformat()
    return result


def _age_to_date(dob: date, age_years: float) -> date:
    """Convert fractional age to a calendar date."""
    whole  = int(age_years)
    frac   = age_years - whole
    days   = round(frac * 365.25)
    try:
        d = dob + relativedelta(years=whole) + timedelta(days=days)
    except Exception:
        d = dob + timedelta(days=round(age_years * 365.25))
    return d


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2 — Slice to 4-year window
# ═════════════════════════════════════════════════════════════════════════════

def _slice_window(
    periods: List[Dict], today: date, past_months: int = _WINDOW_PAST_MONTHS,
    future_years: int = _WINDOW_FUTURE_YEARS,
) -> List[Dict]:
    """Keep only periods overlapping [today-past_months, today+future_years]; clip boundaries.

    past_months defaults to _WINDOW_PAST_MONTHS (12); build_career_timeline
    overrides it (config.horizon_mode="validation") with the span of the
    user's actual career history so a validator LLM receives full
    retroactive coverage. future_years defaults to _WINDOW_FUTURE_YEARS (4)
    and is set to 0 in validation mode (no forward-looking blocks needed).

    GAP 1 fix (2026-07-07 follow-up audit, user-reported): ANY period that
    genuinely STARTS inside the display window (s < win_end) used to have
    its end_date silently clipped to win_end even when the period itself
    runs well past win_end — e.g. the Jupiter-MD Rahu-AD antardasha
    genuinely runs 2029-05-04 to 2031-09-28 (a ~2.4yr AD; see
    engine_io.py::_build_dasha_from_json, which correctly expands the full
    antardasha/pratyantardasha chain from the JSON's own start_year/
    end_year), but with the default 4-year forward window
    (today=2026-06 -> win_end=2030-06) this AD (starting 2029-05, well
    inside the window) was clipped to "...to 2030-06" purely because it
    happened to still be running when the window boundary hit — even
    though it was never "in progress at load time" today, it IS a period
    the window legitimately surfaces (its start date falls inside the
    window), so truncating it makes the report state an end date that is
    flatly wrong, not just "outside the forecast horizon".
    This is a real display-layer truncation bug, not a data bug — the
    full, correct end_date already exists on `p["end_date"]` before this
    function clips it.
    Bounded fix: only clip end_date to win_end for periods that are
    genuinely STILL RUNNING at win_end AND whose own natural span is
    "open-ended" from the window's perspective — in practice this means:
    do not clip end_date at all for any period whose start_date already
    falls inside [win_start, win_end) (i.e. any period the window
    legitimately includes gets shown with its own real end_date, however
    far that extends). A period is only excluded entirely (not clipped)
    when it starts at/after win_end — unchanged from before. This keeps
    the window's PURPOSE (bound which periods appear at all) while no
    longer truncating a period's own real, already-computed end date once
    it has been selected for inclusion.
    """
    win_start = today - relativedelta(months=past_months)
    win_end   = today + relativedelta(years=future_years)
    result = []
    for p in periods:
        s, e = p["start_date"], p["end_date"]
        if e <= win_start or s >= win_end:
            continue
        clipped = dict(p)
        clipped["start_date"] = max(s, win_start)
        # GAP 1 fix: a period whose start_date falls inside the window is
        # kept with its OWN real end_date, uncapped — the window controls
        # which periods are surfaced (via the s >= win_end exclusion
        # above), not how far a surfaced period's own end date is allowed
        # to extend. Only a period that (impossibly, given the exclusion
        # above) somehow starts at/after win_end would need capping, so
        # end_date is never clipped once a period passes the inclusion
        # check.
        clipped["end_date"] = e
        clipped["is_past"]    = clipped["end_date"] <= today
        clipped["is_current"] = clipped["start_date"] <= today < clipped["end_date"]
        result.append(clipped)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# KP CAREER CUSP SCORING (new)
# ═════════════════════════════════════════════════════════════════════════════

def _kp_career_cusp_score(md_lord: str, ad_lord: str, kp_cusps: Dict) -> float:
    """Score based on KP career-cusp sub-lord/star-lord alignment.

    KP doctrine: the sub-lord of a house cusp is the FINAL ARBITER of that
    house's fructification.  We check H10 (career), H11 (gains), H6 (service),
    and H2 (income) in descending priority.

    G2 fix: accumulate contributions from ALL career cusps rather than taking
    max() of a single cusp match.  Multi-cusp alignment (e.g. MD lord is
    sub-lord of BOTH H10 and H11) genuinely represents stronger activation and
    should produce a higher score than a single-cusp match.

    The raw accumulated score is normalised against the maximum possible
    contribution (all sub-lords match = 3.10) and scaled to [0, 1].

    Scoring per cusp:
        sub-lord match:  weight × 1.00  (strongest — final arbiter)
        star-lord match: weight × 0.55  (medium — shows the career environment)
        sign-lord match: weight × 0.25  (weak — background influence only)
    """
    cusp_cfg = {
        "H10": 1.00,   # Prime career cusp (KP primary signal)
        "H11": 0.80,   # Gains and desire-fulfilment
        "H6":  0.70,   # Service, employment, competition
        "H2":  0.60,   # Income, resources
    }
    _MAX_POSSIBLE = sum(cusp_cfg.values())  # 3.10 — all sub-lords match
    raw = 0.0
    for cusp_key, weight in cusp_cfg.items():
        cusp = kp_cusps.get(cusp_key, {})
        if not isinstance(cusp, dict):
            continue
        sub  = cusp.get("sub_lord",  "")
        star = cusp.get("star_lord", "")
        sign = cusp.get("sign_lord", "")
        if sub in (md_lord, ad_lord):
            raw += weight * 1.00
        elif star in (md_lord, ad_lord):
            raw += weight * 0.55
        elif sign in (md_lord, ad_lord):
            raw += weight * 0.25
    # Normalise: single H10 sub-lord match → 1.00/3.10 ≈ 0.32; H10+H11 → 1.80/3.10 ≈ 0.58
    # G1 fix: floor at 0.03 when KP cusp data exists but no keyword chain matched.
    # Prevents hard-zero from triggering false _zero_methods friction flags in engine.py.
    if raw > 0:
        return min(1.0, raw / _MAX_POSSIBLE)
    _has_cusp_data = any(isinstance(kp_cusps.get(k), dict) and kp_cusps[k]
                         for k in cusp_cfg)
    return 0.03 if _has_cusp_data else 0.0


# ═════════════════════════════════════════════════════════════════════════════
# KN RAO JAIMINI CAREER SCORING (new)
# ═════════════════════════════════════════════════════════════════════════════

def _jaimini_career_score(md_lord: str, ad_lord: str, payload: Any) -> Tuple[float, str]:
    """KN Rao Jaimini methodology career score.

    Checks (in priority order):
      1. AmK (Amatyakaraka) match  → 0.92  — prime career karaka period
      2. AK  (Atmakaraka)   match  → 0.72  — soul's vocational calling
      3. Brahma / Maheshwara lord  → 0.62  — creative authority & longevity
      4. Other chara karaka role   → 0.30  — background influence

    Returns (score 0–1, jaimini_role_label string for narrative use).
    """
    ak  = getattr(payload, "atmakaraka",   "") or ""
    amk = getattr(payload, "amatyakaraka", "") or ""

    # Try to get Jaimini special lords and chara karakas from payload
    jdata = (getattr(payload, "kn_rao_jaimini", None)
             or getattr(payload, "kn_rao_jaimini_data", None)
             or {})
    if not isinstance(jdata, dict):
        jdata = {}
    special_lords = jdata.get("jaimini_special_lords", {}) or {}
    chara_karakas = jdata.get("chara_karakas", {}) or {}
    if not chara_karakas:
        # Fall back to top-level payload attributes already parsed by engine_io
        for role in ("AK", "AmK", "BK", "MK", "PK", "GK", "DK"):
            v = getattr(payload, role.lower() + "_planet", "") or ""
            if v:
                chara_karakas[role] = v
        if not chara_karakas.get("AK") and ak:
            chara_karakas["AK"] = ak
        if not chara_karakas.get("AmK") and amk:
            chara_karakas["AmK"] = amk

    brahma     = special_lords.get("brahma",     "")
    maheshwara = special_lords.get("maheshwara", "")

    score      = 0.0
    role_label = ""

    # 1. AmK — prime career indicator in Jaimini
    if md_lord == amk or ad_lord == amk:
        score = max(score, 0.92)
        role_label = _JAIMINI_ROLE.get("AmK", "Amatyakaraka period — peak career activation.")

    # 2. AK — soul's karmic calling
    if md_lord == ak or ad_lord == ak:
        score = max(score, 0.72)
        if not role_label:
            role_label = _JAIMINI_ROLE.get("AK", "Atmakaraka period — vocational soul activation.")

    # 3. Brahma / Maheshwara special lords
    if md_lord in (brahma, maheshwara) or ad_lord in (brahma, maheshwara):
        score = max(score, 0.62)
        if not role_label:
            b_label = f"Brahma={brahma}" if brahma else ""
            m_label = f"Maheshwara={maheshwara}" if maheshwara else ""
            lords_str = " / ".join(x for x in [b_label, m_label] if x) or "Jaimini special lord"
            role_label = f"Jaimini special lord ({lords_str}) active — managerial authority and creative intelligence."

    # 4. Other chara karaka roles
    if not role_label:
        for role_key, planet in chara_karakas.items():
            if planet in (md_lord, ad_lord):
                score = max(score, 0.30)
                role_label = _JAIMINI_ROLE.get(role_key, f"{role_key} dasha active.")
                break

    # 5. A10 (10th Arudha) lord activation — Jaimini public career image signal
    # A10 is the Arudha of H10 and represents the native's career image in the world.
    # When the dasha lord rules the A10 sign, career is highly visible/externally recognised.
    _a10_sign = getattr(payload, "a10_sign", "") or ""
    _a10_lord = _SIGN_LORD.get(_a10_sign, "")
    if _a10_lord and (_a10_lord in (md_lord, ad_lord)):
        score = max(score, 0.52)
        if not role_label:
            role_label = (
                f"A10 (10th Arudha) lord {_a10_lord} active — career reputation heightened; "
                f"public recognition and external validation of professional standing."
            )

    # 6. G-A13: A1 (Arudha Lagna) lord activation — career identity & public brand.
    # A1 shows how the world perceives the native as a professional. When the dasha
    # lord rules the A1 sign, the person's professional identity gains prominence —
    # headhunting, visibility, personal brand recognition events are likely.
    _a1_sign = getattr(payload, "arudha_lagna", "") or ""
    _a1_lord = _SIGN_LORD.get(_a1_sign, "")
    if _a1_lord and (_a1_lord in (md_lord, ad_lord)):
        score = max(score, 0.45)
        if not role_label:
            role_label = (
                f"A1 (Arudha Lagna) lord {_a1_lord} active — professional identity and personal "
                f"brand are highly visible; career opportunities arrive through reputation and referrals."
            )

    return min(1.0, score), role_label


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3 — Score each period (7 sub-scores)
# ═════════════════════════════════════════════════════════════════════════════

def _project_transit_houses_for_period(
    period_start: date,
    period_end: date,
    chart: Any,
    today: date,
) -> Dict[str, int]:
    """Project major transit houses at the period midpoint.

    This uses the same coarse mean-motion model as _get_dynamic_transits. It is
    not an ephemeris; it simply gives scoring layers a consistent projected
    house map instead of an empty placeholder.
    """
    days_per_house = {
        "Jupiter": 365, "Saturn": 912, "Rahu": 548, "Ketu": 548,
        "Mars": 45, "Sun": 30, "Mercury": 25, "Venus": 25, "Moon": 3,
    }
    retro_duration = {
        "Saturn": 137, "Jupiter": 121, "Mars": 72,
        "Venus": 42, "Mercury": 21,
    }
    snapshot = getattr(chart, "transit_house_positions", {}) or {}
    retro_list = set(getattr(chart, "retrograde_planets", []) or [])
    mid = period_start + (period_end - period_start) // 2
    days_ahead = (mid - today).days
    projected: Dict[str, int] = {}

    for planet, dph in days_per_house.items():
        current_h = snapshot.get(planet, 0)
        if not current_h:
            continue
        houses_moved = days_ahead / dph
        if planet in ("Rahu", "Ketu"):
            new_h = int(((current_h - 1 - round(houses_moved)) % 12) + 1)
        elif planet in retro_list:
            retro_dur = retro_duration.get(planet, 90)
            if days_ahead <= retro_dur:
                new_h = int(((current_h - 1 - round(houses_moved)) % 12) + 1)
            else:
                retro_houses = retro_dur / dph
                fwd_houses = (days_ahead - retro_dur) / dph
                new_h = int(((current_h - 1 + max(0, round(fwd_houses - retro_houses))) % 12) + 1)
        else:
            new_h = int(((current_h - 1 + round(houses_moved)) % 12) + 1)
        projected[planet] = new_h
    return projected


def _score_period(
    p: Dict,
    payload: Any,
    eff_strengths: Dict[str, float],
    career_ctx: Dict[str, Any],
    lagna_sign: str,
    detected_yogas: Optional[Dict[str, str]] = None,
    weight_overrides: Optional[Dict[str, float]] = None,
    sbc_natal_mod: float = 1.0,
    today: Optional[date] = None,
    md_change_dates: Optional[List[date]] = None,
    ad_change_dates: Optional[List[date]] = None,
) -> Dict[str, float]:
    """Return dict of sub-scores and combined career_score (0–1).

    Now includes 7 sub-scores:
      career_activation  (KP significators for career houses)
      strength_product   (effective strength product of MD×AD lords)
      functional_nature  (functional benefic/malefic for lagna)
      house_activation   (houses owned/occupied by MD+AD lords)
      company_score      (company-type karaka alignment)
      kp_cusp_score      (NEW: KP career-cusp sub-lord alignment)
      jaimini_score      (NEW: KN Rao Jaimini AmK/AK alignment)
    """
    md_lord = p["md_lord"]
    ad_lord = p["ad_lord"]

    # 1. Career activation: KP significator check for H6, H10, H11, H2
    kp_sigs = getattr(payload, "kp_significators", {}) or {}
    career_houses = {6, 10, 11, 2}

    def _kp_score(planet: str) -> float:
        sig = kp_sigs.get(planet, {})
        if not isinstance(sig, dict):
            sig = {}
        s = 0.0
        for h in career_houses:
            if h in sig.get("level_1", []) or h in sig.get("level_2", []):
                s = max(s, 1.0)
            elif h in sig.get("level_3", []):
                s = max(s, 0.6)
            elif h in sig.get("level_4", []):
                s = max(s, 0.3)
        # GAP 12 fix: when KP significator levels are absent/empty, fall back to
        # checking direct career-house lordship and occupancy in D1.
        # Planets that rule or occupy H6/H10/H11/H2 natively should not score 0.
        if s == 0.0:
            _hl_fb = getattr(payload, "house_lords", {}) or {}
            _ph_fb = getattr(payload, "planet_house", {}) or {}
            for _h in career_houses:
                if _hl_fb.get(str(_h)) == planet:
                    s = max(s, 0.35)   # house lord — highest fallback signal
                    break
                if _ph_fb.get(planet, 0) == _h:
                    s = max(s, 0.28)   # house occupant — moderate fallback
        return s

    career_activation = min(1.0, (_kp_score(md_lord) * 0.6 + _kp_score(ad_lord) * 0.4))

    # 2. Strength product
    s_md = min(eff_strengths.get(md_lord, 0.5), 2.0) / 2.0
    s_ad = min(eff_strengths.get(ad_lord, 0.5), 2.0) / 2.0
    strength_product = s_md * s_ad

    # 3. Functional nature for lagna
    fn = _FUNCTIONAL_NATURE.get(lagna_sign, {})
    fn_md = fn.get(md_lord, 0)
    fn_ad = fn.get(ad_lord, 0)
    # Normalise: yogakaraka(2)=1.0, benefic(1)=0.75, neutral(0)=0.5, malefic(-1)=0.2
    def _fn_norm(v: int) -> float:
        return {2: 1.0, 1: 0.75, 0: 0.5, -1: 0.2}.get(v, 0.5)

    # G-A1 runtime: Rahu/Ketu FN overridden using the actual sign they occupy in D1.
    # The sign lord's FN is used — more accurate than the Saturn/Mars table proxy.
    _ps = getattr(payload, "planet_signs", {}) or {}
    if md_lord in ("Rahu", "Ketu"):
        _node_sign = _ps.get(md_lord, "")
        _node_sl   = _SIGN_LORD.get(_node_sign, "")
        if _node_sl:
            fn_md = fn.get(_node_sl, fn_md)
    if ad_lord in ("Rahu", "Ketu"):
        _node_sign = _ps.get(ad_lord, "")
        _node_sl   = _SIGN_LORD.get(_node_sign, "")
        if _node_sl:
            fn_ad = fn.get(_node_sl, fn_ad)

    # G-A3: Nakshatra lord of MD/AD lord modulates FN (±0.03 per lord, cap ±0.05).
    # If the nakshatra lord has a negative FN for the lagna, it degrades the period.
    _pnaks = getattr(payload, "planet_nakshatras", {}) or {}
    _nak_fn_mod = 0.0
    for _dasha_lord in (md_lord, ad_lord):
        _nak_name  = _pnaks.get(_dasha_lord, "")
        _nak_l     = _NAKSHATRA_LORD.get(_nak_name, "")
        if _nak_l:
            _nak_fn_raw = fn.get(_nak_l, 0)
            _nak_fn_mod += (_fn_norm(_nak_fn_raw) - 0.5) * 0.06   # ±0.03 per lord
    _nak_fn_mod = max(-0.05, min(0.05, _nak_fn_mod))

    functional_nature = min(1.0, max(0.0, (_fn_norm(fn_md) + _fn_norm(fn_ad)) / 2.0 + _nak_fn_mod))

    # 4. House activation: which houses do MD+AD lords own/occupy
    ph = getattr(payload, "planet_house", {}) or {}
    hl = getattr(payload, "house_lords", {}) or {}
    house_score = 0.0
    for planet in [md_lord, ad_lord]:
        # Houses occupied
        occ_h = ph.get(planet, 0)
        if occ_h:
            house_score += _HOUSE_CAREER_WEIGHT.get(occ_h, 0) * 0.5
        # Houses owned (sign lordship)
        for hnum_str, lord in hl.items():
            if lord == planet:
                try:
                    hnum = int(hnum_str)
                    house_score += _HOUSE_CAREER_WEIGHT.get(hnum, 0) * 0.3
                except ValueError:
                    pass
    # Normalise to 0–1
    house_activation = max(0.0, min(1.0, house_score / 1.5))

    # 5. Company karaka alignment
    ctype = career_ctx.get("company_type", "default")
    cw = _JOB_KARAKA_WEIGHTS.get(ctype, _JOB_KARAKA_WEIGHTS["default"])
    company_score = cw.get(md_lord, 0.0) * 0.6 + cw.get(ad_lord, 0.0) * 0.4

    # 5a. G-A2: MD lord self-transit bonus/penalty.
    # Classical rule: during Jupiter MD, Jupiter transiting H10/H11/H9/H2 from natal
    # lagna is an additional positive signal. H8/H12 transit = adverse overlay.
    _transit_hp = getattr(payload, "transit_house_positions", {}) or {}
    _md_transit_h = _transit_hp.get(md_lord, 0)
    _md_transit_bonus = 0.0
    if _md_transit_h:
        _md_fav = {2: 0.03, 5: 0.02, 9: 0.04, 10: 0.05, 11: 0.05}
        _md_adv = {8: -0.04, 12: -0.03}
        _md_transit_bonus = _md_fav.get(_md_transit_h, 0) + _md_adv.get(_md_transit_h, 0)

    # 5b. D10 / SAV compatibility diagnostics for downstream tests and reports
    d10_occ = getattr(payload, "d10_house_occupancy", {}) or {}
    d10_strength = float(getattr(payload, "d10_strength", 0.0) or 0.0)
    career_house_weights = {10: 0.40, 11: 0.25, 2: 0.20, 6: 0.15}
    d10_alignment = 0.0
    for house, weight in career_house_weights.items():
        occupants = d10_occ.get(str(house), []) or []
        if md_lord in occupants or ad_lord in occupants:
            d10_alignment += weight
    d10_alignment = max(0.0, min(1.0, d10_alignment * (0.6 + 0.4 * d10_strength)))

    # 5b-2. Phase 2 (2026-07-05, item #8/#7): D10 structural sub-scores.
    # `d10_alignment` above is a single scalar (does the MD/AD lord occupy a
    # career house in D10, scaled by whole-chart D10 strength). That collapses
    # several structurally distinct D10 facts into one number, which is why
    # narratives could describe the same D10 chart as both "Virgo lagna with
    # Jupiter in lagna" (a real structural strength) and "D10 alignment 0.0"
    # (a real but narrowly-scoped period signal) without acknowledging they
    # are different things. These sub-scores expose each structural piece
    # separately so a report/narrative can distinguish "this chart's D10 is
    # generally strong" from "this specific MD/AD isn't the one activating it."
    d10_lagna_sign   = getattr(payload, "d10_lagna_sign", "") or ""
    d10_house_lords  = getattr(payload, "d10_house_lords", {}) or {}
    d10_planet_digs  = getattr(payload, "d10_planet_dignities", {}) or {}
    d10_lagna_lord   = d10_house_lords.get("1", "") or _SIGN_LORD.get(d10_lagna_sign, "")
    d10_h10_lord     = d10_house_lords.get("10", "")

    # Is the running MD/AD lord itself the D10 lagna lord, or natally placed
    # in the D10 lagna (H1)? Either signifies the period draws on the
    # native's core D10 career identity, not just a peripheral house.
    d10_lagna_occupants = d10_occ.get("1", []) or []
    d10_lagna_support = (
        1.0 if d10_lagna_lord in (md_lord, ad_lord)
        else (0.6 if (md_lord in d10_lagna_occupants or ad_lord in d10_lagna_occupants) else 0.0)
    )

    # Dignity + placement of the D10 10th lord (a fixed natal-D10 fact, not
    # period-dependent) — surfaced so the report can say *why* D10 career
    # authority is strong/weak structurally, independent of which AD is running.
    _d10_h10_lord_dig = str(d10_planet_digs.get(d10_h10_lord, "")).upper() if d10_h10_lord else ""
    d10_h10_lord_dignity_score = {"EXALTED": 1.0, "OWN": 0.8, "DEBILITATED": 0.15}.get(_d10_h10_lord_dig, 0.5)
    d10_h10_lord_house = 0
    for _hnum_str, _occs in d10_occ.items():
        if d10_h10_lord and d10_h10_lord in (_occs or []):
            try:
                d10_h10_lord_house = int(_hnum_str)
            except ValueError:
                pass
            break

    # D10 house-link breakdown for 6/10/11/12 (job-pressure / career /
    # gains / foreign-institutional-pressure) — explicit per-house instead of
    # one blended alignment number.
    d10_house_links = {}
    for _h in (6, 10, 11, 12):
        _occs = d10_occ.get(str(_h), []) or []
        d10_house_links[str(_h)] = 1.0 if (md_lord in _occs or ad_lord in _occs) else 0.0

    d10_structural_score = max(0.0, min(1.0,
        0.30 * d10_lagna_support + 0.25 * d10_h10_lord_dignity_score
        + 0.25 * d10_alignment + 0.20 * d10_strength
    ))

    # User-reported gap fix (2026-07): D10 was under-read structurally in two
    # ways — (1) a genuine multi-planet stellium in the D10 12th house (MNC/
    # global-delivery/hidden-workload signature) wasn't distinguished from a
    # single planet there, and (2) the D10 Lagna sign's classical career
    # theme (Virgo=analytics/systems, Leo=authority/leadership, etc.) was
    # never surfaced even though it's a standard, chart-agnostic reading of
    # any D10 Lagna sign — not specific to any one chart.
    _d10_h12_occupants = d10_occ.get("12", []) or []
    d10_h12_stellium = len(_d10_h12_occupants) >= 3
    _D10_SIGN_CAREER_THEME = {
        "Aries": "initiative-led execution, competitive/pioneering roles",
        "Taurus": "steady operational/financial roles, resource management",
        "Gemini": "communication, multi-tasking, sales/liaison/analytical roles",
        "Cancer": "people-care, HR/nurturing, domestic-linked service roles",
        "Leo": "authority, leadership, public-facing executive roles",
        "Virgo": "analytics, systems, service excellence, process/architecture roles",
        "Libra": "partnership-driven, client-relations, balance/negotiation roles",
        "Scorpio": "research, transformation, crisis-handling, deep-technical roles",
        "Sagittarius": "advisory, teaching, cross-border/consulting roles",
        "Capricorn": "structured authority, discipline, long-haul institutional roles",
        "Aquarius": "innovation, technology, network/community-driven roles",
        "Pisces": "creative/intuitive, behind-the-scenes, service-oriented roles",
    }
    d10_lagna_career_theme = _D10_SIGN_CAREER_THEME.get(d10_lagna_sign, "")

    # GAP 6 fix (2026-07-07 follow-up audit): compute the 4 D10
    # sub-dimension scores here (same underlying facts as
    # d10_manifestation_text()'s narrative), so they can be spread into the
    # sub_scores dict returned below.
    try:
        from .gap_corrections_career_timeline_2026_07 import d10_subdimension_scores
        _d10_subscores = d10_subdimension_scores(
            d10_h10_lord=d10_h10_lord, d10_h10_lord_house=d10_h10_lord_house,
            d10_h10_lord_dignity=_d10_h10_lord_dig, d10_lagna_sign=d10_lagna_sign,
            d10_10th_sign="", d10_h12_stellium=d10_h12_stellium,
        )
    except Exception:
        _d10_subscores = {}

    # 5d. D9 Navamsha cross-validation — dignity of MD/AD lord in D9
    # Exalted/own sign → boost 0.06; debilitated → penalty -0.04
    # G1 fix: read from the explicit field (not a missing payload attribute)
    d9_dignities = (getattr(payload, "d9_planet_dignities", None) or {}) or {}
    d9_modifier = 0.0
    # Phase (2026-07-05 gap review, item #7): track MD and AD lord D9 dignity
    # SEPARATELY, not just as one combined modifier. "D9 dignity weak" alone
    # doesn't say whether it's the MD lord (the overarching multi-year theme)
    # or the AD lord (the specific, immediate result) that's weak — and those
    # have different practical meanings: an AD-lord weakness classically
    # means the specific event may arrive but not fully settle/satisfy, while
    # an MD-lord weakness means the broader arc across the whole Mahadasha
    # may not durably sustain. This distinction is chart-agnostic — it just
    # separates the same lookup by which lord it's checking.
    _d9_md_dig = str(d9_dignities.get(md_lord, "")).lower()
    _d9_ad_dig = str(d9_dignities.get(ad_lord, "")).lower()
    for _pl_dig in (_d9_md_dig, _d9_ad_dig) if md_lord != ad_lord else (_d9_md_dig,):
        if _pl_dig in ("exalted", "own"):
            d9_modifier += 0.06
        elif _pl_dig in ("debilitated", "fallen"):
            d9_modifier -= 0.04
    # Cap: +0.08 max boost, -0.06 max penalty
    d9_modifier = max(-0.06, min(0.08, d9_modifier))

    _md_d9_weak = _d9_md_dig in ("debilitated", "fallen")
    _ad_d9_weak = _d9_ad_dig in ("debilitated", "fallen")
    _md_d9_strong = _d9_md_dig in ("exalted", "own")
    _ad_d9_strong = _d9_ad_dig in ("exalted", "own")
    if _md_d9_weak and _ad_d9_weak:
        d9_contradiction_type = "both_weak"
        d9_weak_lord = "both"
    elif _ad_d9_weak:
        d9_contradiction_type = "satisfaction_durability"   # immediate result may arrive but not settle
        d9_weak_lord = "AD"
    elif _md_d9_weak:
        d9_contradiction_type = "long_term_sustainability"  # broader multi-year arc strain
        d9_weak_lord = "MD"
    elif _md_d9_strong and _ad_d9_strong:
        d9_contradiction_type = "none"
        d9_weak_lord = ""
    else:
        d9_contradiction_type = "neutral"
        d9_weak_lord = ""

    # 5c. D24 Siddhamsha — skill/education houses (H1, H4, H5, H9)
    # MD/AD lord in these D24 houses → boost SKILL_UPGRADE classification
    d24_occ = getattr(payload, "d24_house_occupancy", {}) or {}
    d24_skill_bonus = 0.0
    for _d24h in (1, 4, 5, 9):
        _d24_occ = d24_occ.get(str(_d24h), []) or []
        if md_lord in _d24_occ or ad_lord in _d24_occ:
            d24_skill_bonus = 0.10
            break

    sav_points = getattr(payload, "sav_points_houses", {}) or {}
    sav_total = 0.0
    for house in (10, 11, 2, 6):
        try:
            # Gap 0.1: canonical keys are "1".."12" (normalized in engine_io);
            # legacy "H10" form accepted as fallback for old fixtures.
            sav_total += float(sav_points.get(str(house), sav_points.get(f"H{house}", 0.0)) or 0.0)
        except (TypeError, ValueError):
            continue
    sav_support = max(0.0, min(1.0, sav_total / 140.0))

    # User-reported gap fix (2026-07): Ashtakavarga (SAV) was only used for
    # career houses (2/6/10/11) above — H4 (home/base/property/comfort) and
    # H8 (sudden transformation/restructuring) SAV were computed and stored
    # on the payload but never read anywhere. A weak H4 SAV relative to
    # strong career houses is the classical signature of "career rises, but
    # domestic/base stability may be sacrificed" — and a strong H8 SAV means
    # transformation/restructuring cycles land with more force (not
    # necessarily bad, but more disruptive). Both are chart-agnostic
    # (relative bindu comparison, no hardcoded chart facts).
    def _sav_of(house_num: int) -> float:
        try:
            return float(sav_points.get(str(house_num), sav_points.get(f"H{house_num}", 0.0)) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    _sav_h4 = _sav_of(4)
    _sav_h8 = _sav_of(8)
    _sav_career_avg = (sav_total / 4.0) if sav_total else 0.0
    # Home/base instability: H4 meaningfully weaker than the career-house average
    _sav_home_instability = max(0.0, min(1.0, (_sav_career_avg - _sav_h4) / 15.0)) if _sav_career_avg > 0 else 0.0
    # Transformation intensity: H8 strong in absolute terms (>=30 bindus is the
    # classical "strong house" threshold, matching the capacity-factor logic below)
    _sav_transformation_intensity = max(0.0, min(1.0, (_sav_h8 - 25.0) / 15.0))

    # 6. NEW: KP career-cusp sub-lord alignment
    kp_cusps = getattr(payload, "kp_cusps", {}) or {}
    kp_cusp_score = _kp_career_cusp_score(md_lord, ad_lord, kp_cusps)
    # GAP FIX (2026-08-21, item 2.3): this cusp-derived score previously had
    # no cusp-chain verification at all, unlike the Field_Determination KP
    # scorer. Same conservative discount-not-zero philosophy as that call
    # site: an UNVERIFIED chain is not necessarily wrong, so this discounts
    # confidence rather than eliminating the signal.
    _kp_cusp_audit = audit_kp_cusps(kp_cusps, getattr(payload, "house_system", "") or "")
    if _kp_cusp_audit.get("status") != "VERIFIED":
        kp_cusp_score *= 0.5

    # 7. NEW: KN Rao Jaimini AmK/AK alignment
    jaimini_score, _jai_role = _jaimini_career_score(md_lord, ad_lord, payload)

    # ── FIX 2: SAV house-capacity multiplier ─────────────────────────────────
    # A house must have sufficient SAV bindus to deliver on its activation.
    # Iterate over active career houses and compute a capacity factor.
    sav_pts  = getattr(payload, "sav_points_houses", {}) or {}
    _sav_cap = 0.0
    _sav_n   = 0
    for _h in (10, 11, 2, 6):
        # Gap 0.1: canonical "1".."12" keys first, legacy "H10" fallback.
        _raw_b = sav_pts.get(str(_h), sav_pts.get(f"H{_h}", None))
        if _raw_b is None:
            continue
        try:
            _b = float(_raw_b)
        except (TypeError, ValueError):
            continue
        # < 25 bindus → congested house, cap contribution
        # ≥ 30 bindus → strong house, boost contribution
        if _b < 25:
            _sav_cap += 0.6
        elif _b >= 30:
            _sav_cap += 1.2
        else:
            _sav_cap += 1.0
        _sav_n += 1
    sav_capacity_factor = (_sav_cap / _sav_n) if _sav_n > 0 else 1.0
    # Apply: scale house_activation by capacity; clamp to [0, 1]
    house_activation_adj = min(1.0, house_activation * sav_capacity_factor)

    # ── FIX 1: Birth-time uncertainty → degrade KP/D10 weights ──────────────
    # D10 Ascendant and KP sub-lords shift with even 5-min birth-time error.
    # When uncertainty is high, shift weight from these fast-moving factors
    # to the slower D1 Parashari/Jaimini factors.
    btu = getattr(payload, "birth_time_uncertainty_minutes", 0) or 0
    if btu > 5:
        # degradation: 1.0 at 5 min, 0.3 at 60+ min
        _deg = max(0.3, 1.0 - (btu - 5) / 60.0)
        kp_cusp_score_eff  = kp_cusp_score  * _deg
        d10_alignment_eff  = d10_alignment  * _deg
        # Recover the lost weight into Jaimini (D1-based, immune to birth-time error)
        _recovered = (kp_cusp_score - kp_cusp_score_eff) * _W_KP_CUSP_SCORE \
                   + (d10_alignment - d10_alignment_eff) * 0.05  # D10 not a main weight
        jaimini_score_eff = min(1.0, jaimini_score + _recovered / max(_W_JAIMINI_SCORE, 0.01))
    else:
        kp_cusp_score_eff = kp_cusp_score
        d10_alignment_eff = d10_alignment
        jaimini_score_eff = jaimini_score

    # ── KP promotion tie-breaker (Step 2 calibration v6) ────────────────────
    # When the KP sub-lord is clearly HIGH (≥0.70), inject a small additive bonus
    # that separates this block from adjacent windows with similar base scores.
    # Acts as a primary tie-breaker for PROMOTION vs adjacent PEAK/LEADERSHIP windows.
    _kp_promo_tiebreaker = 0.03 if kp_cusp_score_eff >= 0.70 else 0.0

    # ── Explicit Rajayoga + VRY sub-scores (Steps 2 & 3 calibration v5) ─────
    # These get DEDICATED named weight constants (_W_YOGA_RAJAYOGA / _W_YOGA_VRY)
    # instead of being lumped into the generic yoga_bonus bucket.
    # Sub-score: 1.0 if forming planet is the active MD/AD lord; 0.4 for natal
    # chart potential (yoga present but not the running lord); 0.0 if absent.
    yoga_rajayoga_sub = 0.0
    yoga_vry_sub      = 0.0
    if detected_yogas:
        _md_ycheck = p.get("md_lord", "")
        _ad_ycheck = p.get("ad_lord", "")
        _raja_keys = [k for k in detected_yogas if "Rajayoga" in k]
        _vry_keys  = [k for k in detected_yogas if "_VRY" in k]
        for _k in _raja_keys:
            if detected_yogas[_k] in (_md_ycheck, _ad_ycheck):
                yoga_rajayoga_sub = 1.0
                break
        if yoga_rajayoga_sub < 1.0 and _raja_keys:
            yoga_rajayoga_sub = 0.4   # natal Rajayoga potential (chart-level)
        for _k in _vry_keys:
            if detected_yogas[_k] in (_md_ycheck, _ad_ycheck):
                yoga_vry_sub = 1.0
                break
        if yoga_vry_sub < 1.0 and _vry_keys:
            yoga_vry_sub = 0.4        # natal VRY potential

    # ── Generic yoga bonus (all yogas EXCEPT Rajayoga + VRY, covered above) ──
    yoga_bonus = 0.0
    if detected_yogas:
        md_l = p.get("md_lord", "")
        ad_l = p.get("ad_lord", "")
        _same_lord = (md_l == ad_l)  # prevent double-counting when MD==AD
        for _yname, _yplanet in detected_yogas.items():
            if "Rajayoga" in _yname or "_VRY" in _yname:
                continue  # handled by explicit primary weights above
            # Amala_Yoga_Partial carries a dynamic "__<afflictor(s)>" suffix
            # (see _detect_natal_yogas) so the weight table's exact-match
            # lookup needs the base key, not the full dynamic string.
            _yname_lookup = "Amala_Yoga_Partial" if _yname.startswith("Amala_Yoga_Partial") else _yname
            if _yplanet == md_l:
                yoga_bonus += _YOGA_SCORE_BOOST.get(_yname_lookup, 0.05)
            elif _yplanet == ad_l and not _same_lord:
                # AD lord only adds bonus if it's a different planet from MD lord
                yoga_bonus += _YOGA_SCORE_BOOST.get(_yname_lookup, 0.05) * 0.6
        yoga_bonus = min(0.20, yoga_bonus)  # cap for remaining yogas (Rajayoga/VRY now explicit)

    # ── Chandra Lagna cross-validation ───────────────────────────────────────
    # Check if active houses (relative to Moon lagna) also hit career houses.
    # Moon lagna = house where Moon sits natally becomes H1.
    moon_natal_h = (getattr(payload, "planet_house", None) or {}).get("Moon", 0)
    chandra_bonus = 0.0
    if moon_natal_h:
        _career_h_set = {2, 6, 10, 11}
        _chandra_career_hits = 0
        for _pl in (md_lord, ad_lord):
            _pl_h = (getattr(payload, "planet_house", None) or {}).get(_pl, 0)
            if _pl_h:
                # House relative to Chandra Lagna
                _chandra_h = (_pl_h - moon_natal_h) % 12 + 1
                if _chandra_h in _career_h_set:
                    _chandra_career_hits += 1
        # Both MD+AD active in career houses from Chandra Lagna → strong concordance
        chandra_bonus = 0.04 if _chandra_career_hits >= 2 else (0.02 if _chandra_career_hits == 1 else 0.0)

    # ── 34-Gap Enhancer integration ───────────────────────────────────────────
    _p_start = p.get("start_date")
    _p_end   = p.get("end_date")
    _p_start_d = _p_start if isinstance(_p_start, date) else None
    _p_end_d   = _p_end   if isinstance(_p_end,   date) else None
    _today_d = today or date.today()
    _transit_projected = (
        _project_transit_houses_for_period(_p_start_d, _p_end_d, payload, _today_d)
        if _p_start_d and _p_end_d else {}
    )

    try:
        _dob_str = getattr(payload, "dob", "") or ""
        _dob_d   = parse_iso_date(_dob_str) if _dob_str else None
    except Exception:
        _dob_d = None

    try:
        _enh_inp = build_enhancer_input_from_payload(
            md_lord=md_lord,
            ad_lord=ad_lord,
            period_start=_p_start_d,
            period_end=_p_end_d,
            payload=payload,
            dob=_dob_d,
            transit_projected=_transit_projected,
            md_change_dates=md_change_dates or [],
            ad_change_dates=ad_change_dates or [],
        )
        _enh_result: Optional[EnhancerResult] = AstroEnhancer.run(_enh_inp)
        # GAP FIX (2026-08-21, remediation plan item 2.4): thread the same
        # `btu` (birth_time_uncertainty_minutes) already computed above in
        # this function (FIX 1) into enhancer_score_delta so its Tier 6 KP
        # sub-scores (kp_ssl_score, kp_nakshatra_chain_score,
        # kp_ruling_planets_score and the VIM-KP co-activation bonus) degrade
        # with the same curve as this module's own KP/D10 weights, instead of
        # being applied at full, ungated weight regardless of birth-time
        # precision.
        _enh_delta  = enhancer_score_delta(_enh_result, birth_time_uncertainty_minutes=btu)

        # Phase 3 (2026-07-05, item #6/#9): D60 Shashtiamsha is the most
        # birth-time-sensitive varga in the system — BPHS calls it the most
        # important, but its planetary placements shift materially with even
        # a few minutes of birth-time error, unlike D1/D9. Previously it
        # contributed to career_score with the same implicit confidence as
        # every other factor regardless of how uncertain the input birth time
        # was. Now its contribution is suppressed proportionally to
        # birth_time_uncertainty_minutes — full weight below 5 min, fading to
        # zero by ~35 min uncertainty — rather than quietly treating a
        # possibly-unreliable D60 read as equally trustworthy as D1/D9.
        _btu_d60 = getattr(payload, "birth_time_uncertainty_minutes", 0) or 0
        _birth_precision_d60 = str(getattr(payload, "birth_time_precision", "unknown") or "unknown")
        # GAP-FIX (P0-2/P0-4, CalculationPolicy threading): D60 is the varga
        # CalculationPolicy.d60_claims_allowed exists specifically to gate.
        # Defer the hard "is D60 usable at all" question to the single
        # declared policy; the graduated fade-by-uncertainty curve below
        # still applies within whatever band the policy allows, so a chart
        # near the policy's own exactness threshold doesn't jump straight
        # from full confidence to zero.
        _policy_d60 = getattr(payload, "calculation_policy", None)
        _d60_allowed = (
            bool(_policy_d60.d60_claims_allowed)
            if _policy_d60 is not None and hasattr(_policy_d60, "d60_claims_allowed")
            else _birth_precision_d60 == "exact"
        )
        _d60_confidence = (
            (1.0 if _btu_d60 <= 5 else max(0.0, 1.0 - (_btu_d60 - 5) / 30.0))
            if _d60_allowed else 0.0
        )
        # Global policy: D60 is observation/confirmation only and never changes
        # a field or event score. Preserve the raw value and confidence for the
        # evidence ledger, but remove its contribution from enhancer delta.
        _d60_modifier_gated = 0.0
        _enh_delta = round(_enh_delta - _enh_result.d60_modifier, 4)

        # Apply Dig Bala and Upachaya growth as multiplier on strength_product
        _strength_product_enh = min(
            1.0,
            strength_product
            * _enh_result.dig_bala_factor
            * _enh_result.upachaya_growth_factor
        )
    except Exception as _enh_exc:
        # G10 fix: log the failure so chart-data issues are visible during debugging
        import logging as _log
        _log.getLogger(__name__).warning(
            "AstroEnhancer.run failed for %s/%s: %s",
            md_lord, ad_lord, _enh_exc,
        )
        _enh_result = None
        _enh_delta  = 0.0
        _strength_product_enh = strength_product
        # Fix H (2026-07): the enhancer FAILED here, so D60 modifiers were never
        # actually computed — confidence must reflect that unavailability, not
        # claim full (1.0) confidence. 0.0 is the safe default: matches the
        # "D60 suppressed" narrative shown downstream on failure.
        _d60_confidence = 0.0
        _d60_modifier_gated = 0.0

    # Gap-25 (audit 2026-07) fix: when the enhancer fails, keys like event_hints /
    # is_sandhi silently vanished from the scores dict, changing classifier
    # behaviour (ENTREPRENEURSHIP_WINDOW / EQUITY_EVENT / SANDHI could never fire)
    # depending on enhancer success. Provide explicit safe defaults + a flag so
    # downstream consumers can tell degraded periods apart.
    _enh_failed = _enh_result is None

    # GAP 5 fix: active Pratyantardasha lord micro-boost for the current block.
    # If today falls in this period AND the live PD lord signifies a career house
    # (via KP levels), add a +0.03 signal — the 4th-level dasha is confirming.
    # G-A12: also factor in PD lord's natal FN for the lagna and houses it rules.
    _pd_boost = 0.0
    if p.get("is_current"):
        _prd_lord = getattr(payload, "pratyantar_dasha_lord", "") or ""
        if _prd_lord:
            _prd_kp_s = _kp_score(_prd_lord)
            if _prd_kp_s >= 0.30:
                _pd_boost = 0.03
            # G-A12: PD lord functional nature modifier (sign-lord override for Rahu/Ketu)
            _prd_fn_raw = fn.get(_prd_lord, 0)
            if _prd_lord in ("Rahu", "Ketu"):
                _prd_sign = _ps.get(_prd_lord, "")
                _prd_sl = _SIGN_LORD.get(_prd_sign, "")
                if _prd_sl:
                    _prd_fn_raw = fn.get(_prd_sl, 0)
            _pd_boost += (_fn_norm(_prd_fn_raw) - 0.5) * 0.04   # ±0.02 additive
            # G-A12: PD lord career house rulership contribution
            _prd_hl = getattr(payload, "house_lords", {}) or {}
            _prd_career_h_bonus = sum(
                _HOUSE_CAREER_WEIGHT.get(int(_hstr), 0) * 0.12
                for _hstr, _hlord in _prd_hl.items()
                if _hlord == _prd_lord and _hstr.isdigit()
            )
            _pd_boost += min(0.02, _prd_career_h_bonus)
            # Cap total PD boost to prevent overweight
            _pd_boost = max(-0.03, min(0.06, _pd_boost))

    # ── Combined score ────────────────────────────────────────────────────────
    # Phase 0 LLM weight overrides: chart-specific adjustments (±20% of defaults).
    # Falls back to module-level constants when no overrides are provided.
    _wo  = weight_overrides or {}
    # Gap-28 (audit 2026-07) fix: Phase-0 LLM overrides are documented as "±20% of
    # defaults" but were applied unvalidated — a malformed LLM response could
    # silently reshape all period scores. Clamp each override to that band.
    _WO_DEFAULTS = {
        "career_activation": _W_CAREER_ACTIVATION,
        "strength_product":  _W_STRENGTH_PRODUCT,
        "functional_nature": _W_FUNCTIONAL_NATURE,
        "house_activation":  _W_HOUSE_ACTIVATION,
        "company_score":     _W_COMPANY_KARAKA,
        "kp_cusp_score":     _W_KP_CUSP_SCORE,
        "jaimini_score":     _W_JAIMINI_SCORE,
        "d10_alignment":     _W_D10_ALIGNMENT,
        "yoga_rajayoga":     _W_YOGA_RAJAYOGA,
        "yoga_viparita_ry":  _W_YOGA_VRY,
    }
    _wo_clamped = {}
    for _wk, _wdef in _WO_DEFAULTS.items():
        if _wk in _wo:
            try:
                _wo_clamped[_wk] = max(_wdef * 0.80, min(_wdef * 1.20, float(_wo[_wk])))
            except (TypeError, ValueError):
                continue
    _wo = _wo_clamped
    _wCA  = _wo.get("career_activation",  _W_CAREER_ACTIVATION)
    _wSP  = _wo.get("strength_product",   _W_STRENGTH_PRODUCT)
    _wFN  = _wo.get("functional_nature",  _W_FUNCTIONAL_NATURE)
    _wHA  = _wo.get("house_activation",   _W_HOUSE_ACTIVATION)
    _wCK  = _wo.get("company_score",      _W_COMPANY_KARAKA)
    _wKP  = _wo.get("kp_cusp_score",      _W_KP_CUSP_SCORE)
    _wJA  = _wo.get("jaimini_score",      _W_JAIMINI_SCORE)
    _wD10 = _wo.get("d10_alignment",      _W_D10_ALIGNMENT)   # GAP 1: D10 weight
    _wRJ  = _wo.get("yoga_rajayoga",      _W_YOGA_RAJAYOGA)   # Step 2: explicit Rajayoga weight
    _wVRY = _wo.get("yoga_viparita_ry",   _W_YOGA_VRY)        # Step 3: explicit VRY weight
    # FIX-1: Gandanta disruption penalty
    # If the MD or AD lord's natal position falls within a Gandanta zone
    # (last/first 3°20' of water→fire sign junctions), apply a dynamic
    # penalty proportional to proximity to the junction centre.
    # Max penalty: −0.08 (deep Gandanta); tapers to 0 at zone edge.
    _gandanta_penalty  = 0.0
    _gandanta_note     = ""
    # Fix G (2026-07): `_gandanta_note` narrates only the LAST lord's individual
    # `_pen` (not the summed/capped `_gandanta_penalty` that actually feeds the
    # score). Track that same single-lord value separately so the narrative
    # text and its exposed numeric field are traceable to the same source.
    _gandanta_note_penalty = 0.0
    try:
        from jyotish.constants import is_gandanta as _is_gandanta
        _p_signs   = getattr(payload, "planet_signs", {}) or {}
        _p_lons    = getattr(payload, "planet_longitudes", {}) or {}
        # Derive approximate absolute longitude from sign+degree if available
        # Gap-19 (audit 2026-07) fix: Libra base was 160 (typo) — Libra starts at 180°.
        _SIGN_BASE = {
            "Aries":0,"Taurus":30,"Gemini":60,"Cancer":90,"Leo":120,"Virgo":150,
            "Libra":180,"Scorpio":210,"Sagittarius":240,"Capricorn":270,"Aquarius":300,"Pisces":330,
        }
        for _ck_lord in (md_lord, ad_lord):
            # Gap-0.4/2 (audit 2026-07): planet_longitudes is now populated at
            # ingestion (engine_io) from sign+degree, so this primary path is live.
            # The sign-midpoint fallback can never sit inside a 3°20' junction zone,
            # so it safely produces "no gandanta" rather than a false positive.
            _lon = _p_lons.get(_ck_lord)
            if _lon is None:
                _sign = _p_signs.get(_ck_lord, "")
                _lon  = _SIGN_BASE.get(_sign, -1)
                if _lon >= 0:
                    _lon += 15.0   # midpoint estimate (never triggers gandanta)
            if _lon is not None and _lon >= 0:
                _in_g, _g_label, _g_prox = _is_gandanta(float(_lon))
                if _in_g:
                    # Penalty scales linearly: 0.08 at junction, 0 at zone edge
                    _pen = round(0.08 * (1.0 - _g_prox), 4)
                    _gandanta_penalty += _pen
                    _gandanta_note_penalty = _pen
                    _gandanta_note = (
                        f"{_ck_lord} in Gandanta ({_g_label}, proximity={_g_prox:.2f}) "
                        f"→ disruption penalty −{_pen:.3f}"
                    )
        _gandanta_penalty = min(_gandanta_penalty, 0.12)   # hard cap
    except Exception:
        _gandanta_penalty = 0.0

    combined = (
        _wCA  * career_activation              +
        _wSP  * _strength_product_enh          +
        _wFN  * functional_nature              +
        _wHA  * house_activation_adj           +
        _wCK  * min(1.0, company_score * 3)    +
        _wKP  * kp_cusp_score_eff             +
        _wJA  * jaimini_score_eff              +
        _wD10 * d10_alignment_eff              +   # GAP 1: D10 Dashamsha as 8th sub-score
        _wRJ  * yoga_rajayoga_sub              +   # Step 2: explicit Rajayoga primary component
        _wVRY * yoga_vry_sub                   +   # Step 3: explicit VRY primary component
        yoga_bonus + d9_modifier + chandra_bonus + _enh_delta + _pd_boost  # GAP 5: PD boost
        + _kp_promo_tiebreaker                     # Step 2 v6: KP HIGH (≥0.70) tie-breaker bonus
        + _md_transit_bonus                        # G-A2: MD lord's own transit position bonus
        - _gandanta_penalty                        # FIX-1: Gandanta disruption
    )

    # Gap-25: safe defaults when the enhancer failed (overridden below on success)
    _enh_dict: Dict = {
        "event_hints": [],
        "is_sandhi": False,
        "enhancer_failed": True,
    } if _enh_failed else {}
    if _enh_result is not None:
        _enh_dict = {
            "combustion_modifier":    round(_enh_result.combustion_modifier, 3),
            "retrograde_modifier":    round(_enh_result.retrograde_modifier, 3),
            "neecha_bhanga_bonus":    round(_enh_result.neecha_bhanga_bonus, 3),
            "viparita_raja_bonus":    round(_enh_result.viparita_raja_bonus, 3),
            "papa_kartari_penalty":   round(_enh_result.papa_kartari_penalty, 3),
            "kala_sarpa_modifier":    round(_enh_result.kala_sarpa_modifier, 3),
            "sandhi_modifier":        round(_enh_result.sandhi_modifier, 3),
            "dig_bala_factor":        round(_enh_result.dig_bala_factor, 3),
            "upachaya_growth_factor": round(_enh_result.upachaya_growth_factor, 3),
            "vimsopaka_score":        round(_enh_result.vimsopaka_score, 3),
            "chara_dasha_score":      round(_enh_result.chara_dasha_score, 3),
            "yogini_name":            _enh_result.yogini_name,
            "yogini_score":           round(_enh_result.yogini_score, 3),
            "ashtottari_lord":        _enh_result.ashtottari_lord,
            "ashtottari_active":      _enh_result.ashtottari_active,
            "kp_ssl_score":           round(_enh_result.kp_ssl_score, 3),
            "kp_weighted_score":      round(_enh_result.kp_weighted_score, 3),  # item #5 (2026-07-07)
            "kp_ruling_planets_score":round(_enh_result.kp_ruling_planets_score, 3),
            "kp_nakshatra_chain":     round(_enh_result.kp_nakshatra_chain_score, 3),
            "d10_full_score":         round(_enh_result.d10_full_score, 3),
            "d60_modifier":           _d60_modifier_gated,   # Phase 3: birth-time-confidence gated
            "d60_confidence":         round(_d60_confidence, 3),  # Phase 3, item #6/#9
            "d60_modifier_raw":       round(_enh_result.d60_modifier, 3),  # ungated, for transparency
            "d27_modifier":           round(_enh_result.d27_modifier, 3),
            "surya_lagna_bonus":      round(_enh_result.surya_lagna_bonus, 3),
            "arudha_bonus":           round(_enh_result.arudha_bonus, 3),
            "karakamsha_bonus":       round(_enh_result.karakamsha_bonus, 3),
            "pav_transit_score":      round(_enh_result.pav_transit_score, 3),
            "pav_slow_planet_score":  round(_enh_result.pav_slow_planet_score, 3),
            "kaksha_activation":      _enh_result.kaksha_activation,
            "is_sandhi":              _enh_result.is_sandhi,
            "nakshatra_triggers":     _enh_result.nakshatra_trigger_flags,
            "sooksham_dashas":        _enh_result.sooksham_lords,
            "sooksham_timing_score":  round(_enh_result.sooksham_timing_score, 3),
            "event_hints":            _enh_result.event_hints,
            "mars_aspect_flags":      _enh_result.mars_aspect_flags,
            "transit_aspect_flags":   _enh_result.transit_aspect_flags,
            "enhancer_total_delta":   round(_enh_delta, 4),
            "enhancer_yoga_notes":    _enh_result.yoga_notes,
            "enhancer_timing_notes":  _enh_result.timing_notes,
        }

    # GAP 4 fix: list every non-zero scoring factor so debugging / HTML report can show what fired.
    _fired: List[str] = []
    _factor_vals = [
        ("d9_modifier",         d9_modifier),
        ("yoga_bonus",          yoga_bonus),
        ("yoga_rajayoga",       _wRJ * yoga_rajayoga_sub),
        ("yoga_viparita_ry",    _wVRY * yoga_vry_sub),
        ("chandra_lagna",       chandra_bonus),
        ("pd_lord_boost",       _pd_boost),
        ("kp_promo_tiebreaker", _kp_promo_tiebreaker),
        ("md_transit_bonus",    _md_transit_bonus),    # G-A2: MD lord self-transit
        ("nak_fn_modifier",     _nak_fn_mod),          # G-A3: nakshatra lord FN
        ("gandanta_penalty",   -_gandanta_penalty),    # FIX-1: Gandanta disruption
    ]
    if _enh_result is not None:
        _factor_vals += [
            ("combustion",       _enh_result.combustion_modifier),
            ("retrograde",       _enh_result.retrograde_modifier),
            ("neecha_bhanga",    _enh_result.neecha_bhanga_bonus),
            ("viparita_raja",    _enh_result.viparita_raja_bonus),
            ("papa_kartari",     _enh_result.papa_kartari_penalty),
            ("kala_sarpa",       _enh_result.kala_sarpa_modifier),
            ("sandhi",           _enh_result.sandhi_modifier),
            ("dig_bala",         _enh_result.dig_bala_factor - 1.0),
            ("upachaya_growth",  _enh_result.upachaya_growth_factor - 1.0),
            ("pav_dasha_lord",   0.04 * (_enh_result.pav_transit_score - 0.5)),
            ("pav_slow_planets", 0.04 * (_enh_result.pav_slow_planet_score - 0.5)),
        ]
    _fired = [name for name, val in _factor_vals if abs(val) > 0.005]

    # ── Phase 2 (2026-07-05 architecture pass, item #11): split the single
    # blended career_score into named dimension sub-scores. These are purely
    # ADDITIVE — computed from values already derived above in this same
    # function — and do NOT alter `career_score` or its weights, so every
    # existing consumer of career_score is unaffected. Each dimension
    # re-weights the same underlying house/dignity/yoga/KP signals toward the
    # houses classically associated with that specific outcome, rather than
    # inventing an unrelated formula:
    #   promotion_score  -> H1/H10/H11 (authority/title houses) + yogas + KP/Jaimini
    #   job_change_score -> H3/H10/H12 (classical job-change/instability houses)
    #   income_score     -> H2/H6/H11 (income/service/gains houses)
    #   risk_score       -> negative modifiers (gandanta, papa kartari, kala
    #                       sarpa, sandhi, weak functional nature)
    #   stability_score  -> inverse of risk, scaled by SAV house capacity
    #   visibility_score -> H1/H10 + functional nature + KP + AmK alignment
    # All chart-agnostic: no planet/chart-specific constants, just general
    # house-weight re-emphasis, so this applies uniformly to every chart the
    # engine scores, not just this one.
    def _house_weighted(weight_map: Dict[int, float]) -> float:
        total = 0.0
        for planet in (md_lord, ad_lord):
            occ_h = ph.get(planet, 0)
            if occ_h:
                total += weight_map.get(occ_h, 0.0) * 0.5
            for hnum_str, lord in hl.items():
                if lord == planet:
                    try:
                        total += weight_map.get(int(hnum_str), 0.0) * 0.3
                    except ValueError:
                        pass
        return max(0.0, min(1.0, total / 1.5))

    _promo_houses  = {1: 0.3, 10: 1.0, 11: 0.7}
    _job_houses    = {3: 0.8, 10: 0.6, 12: 0.9}
    _income_houses = {2: 1.0, 6: 0.5, 11: 0.8}
    _vis_houses    = {1: 0.7, 10: 1.0, 11: 0.4}

    _promotion_house_wt  = _house_weighted(_promo_houses)
    _job_change_house_wt = _house_weighted(_job_houses)
    _income_house_wt     = _house_weighted(_income_houses)
    _visibility_house_wt = _house_weighted(_vis_houses)

    # Item #3/#10: AmK-exaltation recognition bonus — a GENERAL rule (applies
    # to any chart where the Amatyakaraka is currently running as MD or AD lord
    # AND is exalted in D1), not hardcoded to any specific planet or person.
    # Amatyakaraka is the Jaimini career-minister karaka; an exalted AmK
    # actively running signifies unusually visible professional authority.
    _amk = getattr(payload, "amatyakaraka", "") or ""
    _dignities_for_amk = (getattr(payload, "true_planet_dignities", None)
                          or getattr(payload, "planet_dignities", None) or {})
    _amk_exalted_bonus = 0.0
    if _amk and _amk in (md_lord, ad_lord):
        if str(_dignities_for_amk.get(_amk, "")).upper() == "EXALTED":
            # Running as AD lord sits closer to day-to-day visible results
            # than running only as MD lord, so it gets the larger bonus.
            _amk_exalted_bonus = 0.18 if _amk == ad_lord else 0.12

    # Item #1 (2026-07-07): AmK-activation bonus — a SMALLER, dignity-agnostic
    # sibling of the exaltation bonus above. Even without exaltation, the
    # Amatyakaraka currently running as MD or AD lord is a general activation
    # of the Jaimini career-minister karaka and deserves a modest boost,
    # distinct from (and smaller than) the exaltation-specific bonus.
    _amk_activated = bool(_amk) and _amk in (md_lord, ad_lord)
    _amk_activation_bonus = 0.06 if _amk_activated else 0.0

    # Item #2 (2026-07-07): senior-manager+ career-stage event-bias weighting.
    # `career_ctx.get("designation")` is the resolved level (already normalised
    # by timeline_inputs._DESIGNATION_TITLE_TO_LEVEL — e.g. "senior manager"
    # resolves to "manager" via keyword match before this point). Only
    # manager/director/csuite/lead levels get a bias; junior/mid/senior get {}.
    _desig_level = career_ctx.get("designation", "") or ""
    _desig_bias_map = _DESIGNATION_EVENT_BIAS.get(_desig_level, {})
    _desig_promo_bias = _desig_bias_map.get("PROMOTION", 0.0) + _desig_bias_map.get("LEADERSHIP_EXPANSION", 0.0)
    _desig_job_change_bias = _desig_bias_map.get("JOB_CHANGE", 0.0)
    _designation_event_bias = dict(_desig_bias_map)  # exposed as-is in output

    # Promotion-cycle gate: a real-world corporate promotion cycle (typically
    # ~24-36 months since the last promotion) opens a natural readiness
    # window. If the native's last_promotion_date is known and >=24 months
    # have elapsed as of current_date, and desired_outcome signals a wish for
    # promotion, apply a modest bonus — mirrors the AmK/designation-bias
    # pattern above rather than inventing a new mechanism.
    _promo_cycle_bonus = 0.0
    _months_since_promotion = None
    _last_promo_dt = parse_iso_date(str(career_ctx.get("last_promotion_date", "")))
    if _last_promo_dt is not None:
        _today_dt = today or parse_iso_date(str(career_ctx.get("current_date", ""))) or date.today()
        _months_since_promotion = (
            (_today_dt.year - _last_promo_dt.year) * 12
            + (_today_dt.month - _last_promo_dt.month)
        )
        _desired_outcome_val = str(career_ctx.get("desired_outcome", "")).lower()
        if _months_since_promotion >= 24 and _desired_outcome_val in ("promotion", "hike", "increment"):
            _promo_cycle_bonus = 0.10

    _sandhi_flag = bool(_enh_result.is_sandhi) if _enh_result is not None else False
    _papa_kartari = _enh_result.papa_kartari_penalty if _enh_result is not None else 0.0
    _kala_sarpa   = _enh_result.kala_sarpa_modifier if _enh_result is not None else 0.0

    promotion_score = max(0.0, min(1.0,
        0.35 * _promotion_house_wt + 0.20 * functional_nature + 0.20 * kp_cusp_score_eff
        + 0.15 * jaimini_score_eff + 0.10 * min(1.0, yoga_bonus + _wRJ * yoga_rajayoga_sub)
        + _amk_exalted_bonus + _amk_activation_bonus + _desig_promo_bias + _promo_cycle_bonus
    ))
    job_change_score = max(0.0, min(1.0,
        0.45 * _job_change_house_wt + 0.25 * (1.0 - functional_nature) + 0.15 * career_activation
        + (0.15 if _sandhi_flag else 0.0)
        + _desig_job_change_bias
    ))
    income_score = max(0.0, min(1.0,
        0.40 * _income_house_wt + 0.25 * company_score * 3 + 0.20 * sav_support
        + 0.15 * jaimini_score_eff
    ))
    visibility_score = max(0.0, min(1.0,
        0.35 * _visibility_house_wt + 0.25 * functional_nature + 0.25 * kp_cusp_score_eff
        + 0.15 * min(1.0, _amk_exalted_bonus * 2)
        + (0.03 if _amk_activated else 0.0)   # item #1: smaller activation bump
    ))
    # User-reported gap fix (2026-07): risk_score previously didn't check
    # whether the running MD/AD lord is itself DEBILITATED in D1, or whether
    # D10's 12th house (hidden workload/backend/MNC-pressure/crisis-handling)
    # is occupied by the running lord — both classical, chart-agnostic risk
    # signals that were being computed elsewhere (true_planet_dignities,
    # d10_house_links) but never fed into risk_score itself. A debilitated
    # dasha lord running its own period is a real risk signal even when
    # other factors (house activation, KP) look fine.
    _dignities_for_risk = (getattr(payload, "true_planet_dignities", None)
                            or getattr(payload, "planet_dignities", None) or {})
    _md_debilitated = str(_dignities_for_risk.get(md_lord, "")).upper() in ("DEBILITATED", "FALLEN")
    _ad_debilitated = str(_dignities_for_risk.get(ad_lord, "")).upper() in ("DEBILITATED", "FALLEN")
    _d10_h12_active = bool(d10_house_links.get("12", 0.0))

    risk_score = max(0.0, min(1.0,
        _gandanta_penalty * 3
        + max(0.0, -_papa_kartari) * 3
        + max(0.0, -_kala_sarpa) * 3
        + (0.30 if _sandhi_flag else 0.0)
        + max(0.0, -d9_modifier) * 3
        + max(0.0, (0.5 - functional_nature)) * 0.6
        + (0.22 if _ad_debilitated else 0.0)
        + (0.12 if _md_debilitated and not _ad_debilitated else 0.0)
        + (0.15 if _d10_h12_active else 0.0)
        + 0.10 * _sav_transformation_intensity
    ))
    stability_score = max(0.0, min(1.0,
        (1.0 - risk_score * 0.7) * (0.5 + 0.5 * sav_capacity_factor)
        - 0.10 * _sav_home_instability
    ))

    # Phase 3 (2026-07-05, item #8 of the Phase-3 spec): D9 sustainability
    # check. D1 (career_score/promotion_score) shows what the period PROMISES;
    # D9 shows whether that promise is likely to hold up under scrutiny/over
    # time (classical use of Navamsha — dharma maturity, sustainability after
    # the initial event). This doesn't change career_score — it's a separate
    # read on how durable the D1 promise is, surfaced as its own label:
    #   D1 strong + D9 weak  -> "STRAIN" (promise likely, but expect friction
    #                           or a result that doesn't fully stick)
    #   D1 + D9 + D10 agree  -> "HIGH_CONFIDENCE" (independent chart layers
    #                           corroborate each other)
    #   otherwise            -> "MODERATE" (no strong agreement or conflict)
    _d1_promise = max(promotion_score, career_activation)
    _d9_weak = d9_modifier < -0.005
    _d9_strong = d9_modifier > 0.005
    _d10_supportive = d10_structural_score >= 0.55
    if _d1_promise >= 0.55 and _d9_weak:
        d9_sustainability = "STRAIN"
    elif _d1_promise >= 0.55 and _d9_strong and _d10_supportive:
        d9_sustainability = "HIGH_CONFIDENCE"
    else:
        d9_sustainability = "MODERATE"
    d9_sustainability_score = max(0.0, min(1.0, 0.5 + d9_modifier * 5 + (0.10 if _d10_supportive else 0.0)))

    # Item #3 (2026-07-07): narrative warning string when MD or AD lord is
    # debilitated in D9 (Navamsha) — a durability/authority-mandate caution,
    # distinct from (and additive to) the existing d9_* fields above.
    _d9_durability_warning = ""
    if d9_weak_lord in ("MD", "AD", "both"):
        if d9_weak_lord == "both":
            _d9_warn_lord_label = f"both the {md_lord} (MD) and {ad_lord} (AD)"
        elif d9_weak_lord == "MD":
            _d9_warn_lord_label = md_lord
        else:
            _d9_warn_lord_label = ad_lord
        _d9_durability_warning = (
            f"D9 shows {_d9_warn_lord_label} debilitated, indicating outer career "
            "progress may outpace inner durability — any promotion or role change "
            "in this period should be secured with clear authority, reporting line, "
            "compensation, and mandate boundaries before being treated as fully realized."
        )

    _result = {
        "career_activation":        round(career_activation,         3),
        "strength_product":         round(_strength_product_enh,     3),
        "functional_nature":        round(functional_nature,         3),
        "house_activation":         round(house_activation_adj,      3),
        "company_score":            round(company_score,             3),
        "d10_alignment":            round(d10_alignment_eff,         3),
        "sav_support":              round(sav_support,               3),
        "sav_capacity_factor":      round(sav_capacity_factor,       3),
        "kp_cusp_score":            round(kp_cusp_score_eff,         3),
        "jaimini_score":            round(jaimini_score_eff,         3),
        "birth_time_uncertainty":   btu,
        # G4 fix: floor combined at 0.05 — prevents penalty stacking from collapsing
        # field separation in the min-max normaliser downstream.
        # Gap-24 (audit 2026-07) fix: sbc_natal_mod now applies BEFORE the floor so
        # a chart-level modifier can no longer lift a floored period back up.
        "career_score":             round(min(1.0, max(0.05, combined * sbc_natal_mod)), 3),
        "sbc_natal_mod":            round(sbc_natal_mod, 4),
        "yoga_bonus":               round(yoga_bonus,                3),
        "yoga_rajayoga_sub":        round(yoga_rajayoga_sub,         3),
        "yoga_vry_sub":             round(yoga_vry_sub,              3),
        "d9_modifier":              round(d9_modifier,               3),
        "chandra_lagna_bonus":      round(chandra_bonus,             3),
        # A5 fix: Rajayoga / VRY tokens are only "active" when the forming planet
        # is the current MD or AD lord; otherwise they are natal background potential
        # and should not appear in the period pill as if they are presently firing.
        "active_yogas":             (
            [k for k, v in detected_yogas.items()
             if "_VRY" not in k and "Rajayoga" not in k]
            + [k for k, v in detected_yogas.items()
               if ("_VRY" in k or "Rajayoga" in k)
               and v in (_md_ycheck, _ad_ycheck)]
        ) if detected_yogas else [],
        "d24_skill_bonus":          round(d24_skill_bonus,           3),
        "pd_lord_boost":            round(_pd_boost,                 3),  # GAP 5
        # Phase 2 (2026-07-05, item #11): named dimension sub-scores, additive
        # only — see comment above `promotion_score` computation for formulas.
        "promotion_score":          round(promotion_score,           3),
        "job_change_score":         round(job_change_score,          3),
        "income_score":             round(income_score,              3),
        "risk_score":               round(risk_score,                3),
        "ad_lord_debilitated":      _ad_debilitated,   # user-reported gap fix, risk transparency
        "md_lord_debilitated":      _md_debilitated,
        "d10_h12_active":           _d10_h12_active,
        "sav_home_instability":     round(_sav_home_instability,     3),   # user-reported gap fix: H4 SAV
        "sav_transformation_intensity": round(_sav_transformation_intensity, 3),  # H8 SAV
        "stability_score":          round(stability_score,           3),
        "visibility_score":         round(visibility_score,          3),
        "amk_exalted_bonus":        round(_amk_exalted_bonus,        3),   # item #3/#10
        "amk_activation_bonus":     round(_amk_activation_bonus,     3),   # item #1 (2026-07-07)
        "amk_activated":            _amk_activated,                        # item #1 (2026-07-07)
        "designation_event_bias":   _designation_event_bias,               # item #2 (2026-07-07)
        "promo_cycle_bonus":        round(_promo_cycle_bonus,        3),   # promotion-cycle gate (2026-07-07)
        "months_since_promotion":   _months_since_promotion,               # promotion-cycle gate (2026-07-07)
        # Phase 2 (2026-07-05, item #8): D10 structural sub-scores.
        "d10_lagna_sign":           d10_lagna_sign,
        "d10_lagna_lord":           d10_lagna_lord,
        "d10_lagna_support":        round(d10_lagna_support,         3),
        "d10_h10_lord":             d10_h10_lord,
        "d10_h10_lord_dignity":     _d10_h10_lord_dig,
        "d10_h10_lord_house":       d10_h10_lord_house,
        "d10_house_links":          d10_house_links,
        "d10_structural_score":     round(d10_structural_score,      3),
        "d10_h12_stellium":         d10_h12_stellium,          # user-reported gap fix
        "d10_lagna_career_theme":   d10_lagna_career_theme,
        # GAP 6 fix (2026-07-07 follow-up audit, user-reported): d10_alignment/
        # d10_full_score can legitimately flatten to 0.0 for this MD/AD even
        # though real D10 structural facts exist (12th-house occupancy,
        # 10th-lord placement/dignity, 10th house sign) — the same facts
        # already used for d10_manifestation_text()'s narrative. These 4
        # sub-dimension scores expose that detail numerically, additive to
        # (not replacing) d10_alignment/d10_full_score below. See
        # gap_corrections_career_timeline_2026_07.d10_subdimension_scores().
        **_d10_subscores,
        # Phase 3, item #8: D9 sustainability read (separate from career_score).
        "d9_sustainability":        d9_sustainability,
        "d9_sustainability_score":  round(d9_sustainability_score,   3),
        # Gap-review item #7: which lord is weak + contradiction type.
        "d9_weak_lord":             d9_weak_lord,
        "d9_contradiction_type":    d9_contradiction_type,
        "d9_md_dignity":            _d9_md_dig,
        "d9_ad_dignity":            _d9_ad_dig,
        "d9_durability_warning":    _d9_durability_warning,   # item #3 (2026-07-07)
        "fired_g_factors":          _fired,                                # GAP 4
        "gandanta_penalty":         round(_gandanta_penalty, 4),           # FIX-1: summed/capped, feeds scoring
        "gandanta_note":            _gandanta_note,                        # FIX-1
        # Fix G: the single-lord penalty that the `gandanta_note` text above is
        # actually describing (may differ from the summed "gandanta_penalty"
        # above when BOTH md_lord and ad_lord are in Gandanta — narrative only
        # describes the last one checked). Does NOT feed scoring; display-only.
        "gandanta_note_penalty":    round(_gandanta_note_penalty, 4),
        **_enh_dict,
    }
    # Fix E (2026-07): expose D10 confidence as 3 explicitly-named, distinct
    # fields instead of leaving callers to infer meaning from d10_full_score /
    # d10_alignment directly. Thresholds match the >=0.55 / <0.3 convention
    # already used elsewhere in this codebase (web_report.py D10 bucketing).
    _d10_full_for_conf = _result.get("d10_full_score")
    _d10_align_for_conf = _result.get("d10_alignment", 0.0) or 0.0
    _result["d10_data_confidence"] = (
        "HIGH" if isinstance(_d10_full_for_conf, (int, float)) and _d10_full_for_conf
        else "LOW"
    )
    _d10_full_val = _d10_full_for_conf if isinstance(_d10_full_for_conf, (int, float)) else 0.0
    _result["d10_structural_relevance"] = (
        "HIGH" if _d10_full_val >= 0.55 else ("MODERATE" if _d10_full_val >= 0.3 else "LOW")
    )
    _result["d10_period_activation"] = (
        "HIGH" if _d10_align_for_conf >= 0.55 else ("MODERATE" if _d10_align_for_conf >= 0.3 else "LOW")
    )
    return _result



def _compute_salary_range(
    event_type: str,
    career_score: float,
    career_ctx: Dict[str, Any],
    macro_score: float,
    h2_sav: float = 28.0,
    h11_sav: float = 28.0,
) -> Optional[Dict]:
    """Estimate salary increment range (% hike) for income-oriented events.

    Returns None for non-income events.
    Formula: base_range × career_score_factor × macro_factor × sav_factor
    """
    _INCOME_EVENTS = {
        "SALARY_HIKE":       (8,  20),
        "INCOME_INFLECTION": (15, 40),
        "PROMOTION":         (20, 50),
        "BREAKTHROUGH":      (30, 80),
        "LEADERSHIP_EXPANSION": (18, 45),
        "GROWTH":            (5,  15),
    }
    # Strip FORECAST_ prefix
    base_type = event_type.replace("FORECAST_", "")
    if base_type not in _INCOME_EVENTS:
        return None

    low_base, high_base = _INCOME_EVENTS[base_type]

    # Score factor: 0.5× at score=0.3, 1.0× at score=0.65, 1.4× at score=1.0
    score_factor = max(0.5, min(1.4, career_score / 0.65))

    # Macro factor: headwinds cut expectation by up to 20%
    macro_factor = max(0.8, min(1.1, macro_score))

    # H2/H11 SAV factor: more bindus → higher upside
    sav_avg = (h2_sav + h11_sav) / 2.0
    sav_factor = 0.85 if sav_avg < 25 else (1.10 if sav_avg >= 30 else 1.0)

    low  = round(low_base  * score_factor * macro_factor * sav_factor)
    high = round(high_base * score_factor * macro_factor * sav_factor)
    low  = max(3, low)
    high = max(low + 3, high)

    return {
        "low_pct":  low,
        "high_pct": high,
        "basis":    f"score={career_score:.2f} macro={macro_score:.2f} sav_avg={sav_avg:.0f}",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Natal yoga detection — boosts career_score when yoga planet is MD/AD lord
# ═════════════════════════════════════════════════════════════════════════════
_YOGA_SCORE_BOOST: Dict[str, float] = {
    # ── Panch Mahapurusha + Gajakesari + Budha-Aditya ────────────────────────
    "Gajakesari":       0.12,
    "Budha_Aditya":     0.08,
    "Ruchaka":          0.10,
    "Hamsa":            0.10,
    "Sasha":            0.08,
    "Malavya":          0.08,
    "Bhadra":           0.08,
    # ── Extended yogas ────────────────────────────────────────────────────────
    "Rajayoga":         0.18,   # trikona lord (forming planet)
    "Rajayoga_pair":    0.18,  # Step 2 fix: kendra lord partner also triggers full boost
    "Rajayoga_H5H10":   0.16,  # raised from 0.12
    "Rajayoga_H9H10":   0.20,  # raised from 0.14
    "Rajayoga_H1H10":   0.15,  # raised from 0.11
    "Rajayoga_H5H4":    0.11,  # raised from 0.08
    "Rajayoga_H9H4":    0.13,  # raised from 0.10
    "Rajayoga_H5H7":    0.11,  # raised from 0.08
    "Rajayoga_H9H7":    0.12,  # raised from 0.09
    # Rajayoga_H1H4 / Rajayoga_H1H7 removed (A2 fix): H1 lord owning another
    # Kendra (H4/H7) = dual-Kendra = Kendraadhipati Dosha, not Rajayoga.
    "Dhana_Yoga":       0.08,
    "Harsha_VRY":       0.09,
    "Sarala_VRY":       0.09,
    "Vimala_VRY":       0.08,
    "Adhi_Yoga":        0.10,
    "Chamara_Yoga":     0.09,
    "Amala_Yoga":       0.07,
    # Afflicted/partial variant (co-occupying Rahu/Ketu/Saturn/Mars) — real
    # but diminished benefit, not the full "spotless" result.
    "Amala_Yoga_Partial": 0.03,
    "Vasumati_Yoga":    0.07,
    "Kemadruma":       -0.08,  # debilitating — negative boost
    "Kala_Sarpa":      -0.05,  # debilitating — negative boost
    # ── G-A5: Parivartana Yogas ───────────────────────────────────────────────
    "Parivartana_H10_H1":  0.14,  # career lord ↔ lagna lord mutual exchange
    "Parivartana_H10_H11": 0.12,  # career lord ↔ income lord — salary/promotion linkage
    "Parivartana_H10_H2":  0.09,  # career lord ↔ wealth lord
    "Parivartana_H10_H6":  0.07,  # career lord ↔ service lord — employment activation
    # ── G-A6: Risk markers ────────────────────────────────────────────────────
    "Drekkana_22_Risk": -0.06,  # 22nd Drekkana lord active → obstacle period
    "NS64_Risk":        -0.05,  # 64th Navamsha lord active → volatile period
    # Neecha Bhanga — key is prefixed
    "Neecha_Bhanga_Sun":     0.11,
    "Neecha_Bhanga_Moon":    0.10,
    "Neecha_Bhanga_Mars":    0.10,
    "Neecha_Bhanga_Mercury": 0.09,
    "Neecha_Bhanga_Jupiter": 0.12,
    "Neecha_Bhanga_Venus":   0.09,
    "Neecha_Bhanga_Saturn":  0.10,
}
_PLANET_EXALT_SIGN: Dict[str, str] = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces", "Saturn": "Libra",
}
_PLANET_OWN_SIGNS: Dict[str, List[str]] = {
    "Sun":     ["Leo"],
    "Moon":    ["Cancer"],
    "Mars":    ["Aries", "Scorpio"],
    "Mercury": ["Gemini", "Virgo"],
    "Jupiter": ["Sagittarius", "Pisces"],
    "Venus":   ["Taurus", "Libra"],
    "Saturn":  ["Capricorn", "Aquarius"],
}
_SIGN_SEQUENCE: List[str] = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]

# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 — Transit overlay (rule-based, deterministic)
# ═════════════════════════════════════════════════════════════════════════════


def _get_dynamic_transits(
    period_start: date,
    period_end: date,
    chart: Any,
    lagna_sign: str,
    today: date,
) -> List[str]:
    """Compute transit flags for a FUTURE period by advancing planet positions.

    FIX 3: Static transit_house_positions only reflects today.
    For periods months/years ahead, we project major planet positions using
    mean orbital speeds (days per house) from the known snapshot date.

    Major planets only — inner planets move too fast to matter over AD windows.
    """
    # Mean days to traverse one house (approx)
    _DAYS_PER_HOUSE = {
        "Jupiter": 365,      # ~1 year per sign/house
        "Saturn":  912,      # ~2.5 years per sign/house
        "Rahu":    548,      # ~18 months per sign/house (retrograde)
        "Ketu":    548,
        "Mars":    45,       # G32: ~45 days per sign (fast, project only ≤9 months)
        "Sun":     30,       # G34: ~1 month per sign  (project only ≤6 months)
        "Mercury": 25,       # G34: ~25 days per sign  (project only ≤4 months)
    }

    snapshot_hp = chart.transit_house_positions or {}
    snapshot_date = today   # the snapshot is always "today"

    # Use period midpoint for transit check
    mid = period_start + (period_end - period_start) // 2
    days_ahead = (mid - snapshot_date).days

    # GAP 2 fix: retrograde-aware direction.
    # chart.retrograde_planets is the list of currently-retrograde planets from the snapshot.
    # Rahu/Ketu are always retrograde (handled explicitly below).
    # For other planets, if retrograde at snapshot, they move backward for the retrograde
    # duration, then resume prograde — net motion is computed accordingly.
    _retro_list = set(getattr(chart, "retrograde_planets", []) or [])
    _RETRO_DURATION_DAYS: Dict[str, int] = {
        "Saturn":  137,   # ~4.5 months retrograde per year
        "Jupiter": 121,   # ~4 months retrograde per year
        "Mars":     72,   # ~2.4 months retrograde every 2 years
        "Venus":    42,   # ~6 weeks retrograde every 18 months
        "Mercury":  21,   # ~3 weeks retrograde (3× per year)
    }

    # GAP FIX (2026-07-05, career timeline audit): Vakri (station) intensification.
    # Classical gochara treats a planet at its stationary point (just before/after
    # a retrograde reversal) as having its strongest and most delay-prone effect —
    # stronger than the same planet mid-transit through the same house. The
    # retrograde handling below only reversed *direction* for projection math; it
    # never flagged the station itself. We can only compute this for the "station
    # direct" case (a planet already retrograde at the snapshot, turning direct
    # partway through the analysis window) — a future "station retrograde" onset
    # can't be derived from mean-motion + a single snapshot without ephemeris data,
    # so that case is intentionally left as a known limitation (see docstring).
    _station_flags: List[str] = []
    _STATION_WINDOW_DAYS = 15   # ± window around the station treated as "intensified"

    projected: dict = {}
    for planet, days_per_house in _DAYS_PER_HOUSE.items():
        current_h = snapshot_hp.get(planet, 0)
        if not current_h:
            continue
        houses_moved = days_ahead / days_per_house
        # Gap-20 (audit 2026-07) fix: int() truncation dropped up to a full house
        # of motion near boundaries; round() halves the average projection error.
        # (Projection is still mean-motion, not ephemeris — see report note.)
        if planet in ("Rahu", "Ketu"):
            # Always retrograde
            new_h = int(((current_h - 1 - round(houses_moved)) % 12) + 1)
        elif planet in _retro_list:
            # GAP 2: currently retrograde — move backward until retrograde ends,
            # then resume prograde.  Net motion depends on days_ahead vs retro duration.
            _retro_dur = _RETRO_DURATION_DAYS.get(planet, 90)
            if days_ahead <= _retro_dur:
                # Still in retrograde phase at period midpoint
                new_h = int(((current_h - 1 - round(houses_moved)) % 12) + 1)
            else:
                # Retrograde ended: net = prograde days − retrograde houses
                _retro_houses = _retro_dur / days_per_house
                _fwd_houses   = (days_ahead - _retro_dur) / days_per_house
                _net = _fwd_houses - _retro_houses
                new_h = int(((current_h - 1 + max(0, round(_net))) % 12) + 1)
            # Vakri station-direct check (Jupiter/Saturn only — the two slow
            # movers where a multi-month period window can plausibly straddle
            # the station day). Compare the period's actual [start, end] range
            # against the snapshot-relative station day, not just the midpoint,
            # so short periods near the station are still caught.
            if planet in ("Jupiter", "Saturn"):
                _station_day_offset = _retro_dur
                _days_to_start = (period_start - snapshot_date).days
                _days_to_end   = (period_end - snapshot_date).days
                if (_days_to_start - _STATION_WINDOW_DAYS) <= _station_day_offset <= (_days_to_end + _STATION_WINDOW_DAYS):
                    _station_flags.append(f"{planet.upper()}_STATION_DIRECT_INTENSIFIED")
        else:
            new_h = int(((current_h - 1 + round(houses_moved)) % 12) + 1)
        projected[planet] = new_h

    # Now derive transit flags from the projected positions.
    flags: List[str] = []
    natal_moon_house = (chart.planet_house or {}).get("Moon", 0)

    jup_h = projected.get("Jupiter", 0)
    if jup_h in (2, 5, 9, 10, 11):
        flags.append(f"JUPITER_H{jup_h}_EXPANSION")
    elif jup_h in (6, 8, 12):
        flags.append(f"JUPITER_H{jup_h}_STRESS")

    sat_h = projected.get("Saturn", 0)
    fn = _FUNCTIONAL_NATURE.get(lagna_sign, {})
    sat_fn = fn.get("Saturn", 0)
    if sat_h == 10:
        flags.append("SATURN_H10_AUTHORITY" if sat_fn >= 0 else "SATURN_H10_BURDEN")
    elif sat_h in (1, 2, 12) and natal_moon_house:
        if sat_h in _sade_sati_houses(natal_moon_house):
            phase = _sade_sati_phase(sat_h, natal_moon_house)
            flags.append(f"SADE_SATI_{phase}")
    if sat_h in (6, 8):
        flags.append(f"SATURN_H{sat_h}_DISRUPTION")

    rahu_h = projected.get("Rahu", 0)
    if rahu_h in (1, 4, 7, 10):
        flags.append("RAHU_KETU_AXIS_MAJOR_CHANGE")

    natal_h10_lord = (chart.house_lords or {}).get("10", "")
    # Pre-compute natal_h10_lord_house unconditionally to avoid NameError
    natal_h10_lord_house = (chart.planet_house or {}).get(natal_h10_lord, 0) if natal_h10_lord else 0

    if natal_h10_lord and jup_h and natal_h10_lord_house:
        if jup_h in _jupiter_aspect_houses(natal_h10_lord_house):
            flags.append("JUPITER_ASPECTS_H10_LORD")

    # Saturn 3rd/10th special aspects (projected)
    if natal_h10_lord and sat_h and natal_h10_lord_house:
        if sat_h in _saturn_aspect_houses(natal_h10_lord_house):
            fn_sat = _FUNCTIONAL_NATURE.get(lagna_sign, {}).get("Saturn", 0)
            flags.append("SATURN_ASPECTS_H10_LORD_POSITIVE" if fn_sat >= 0 else "SATURN_ASPECTS_H10_LORD_STRESS")

    # Venus — use snapshot for near-term periods only.
    # Gap-20 (audit 2026-07) fix: window tightened 180 → 45 days. Venus changes
    # sign every ~25 days, so a 6-month-old snapshot said nothing about the
    # period; beyond ~1.5 months the flag was noise.
    venus_snap_h = snapshot_hp.get("Venus", 0)
    if venus_snap_h and days_ahead <= 45:
        if venus_snap_h in (2, 11, 5):
            flags.append(f"VENUS_H{venus_snap_h}_INCOME_GAIN")
        elif venus_snap_h in (6, 8, 12):
            flags.append(f"VENUS_H{venus_snap_h}_DISSATISFACTION")

    # G32 — Mars transit + 4th/8th house aspects (projected ≤270 days only)
    mars_proj_h = projected.get("Mars", 0)
    if mars_proj_h and days_ahead <= 270:
        if mars_proj_h == 10:
            flags.append("MARS_H10_CAREER_DRIVE")
        elif mars_proj_h in (1, 3, 11):
            flags.append(f"MARS_H{mars_proj_h}_INITIATIVE")
        elif mars_proj_h in (6, 8, 12):
            flags.append(f"MARS_H{mars_proj_h}_CONFLICT_RISK")
        # G32 — Mars 4th/8th aspects on career houses
        for aspect_h in _mars_aspect_houses(mars_proj_h):
            if aspect_h == 10:
                flags.append("MARS_TRANSIT_4TH_8TH_ASPECT_H10")
            elif aspect_h == 1:
                flags.append("MARS_TRANSIT_ASPECTS_LAGNA")
            elif aspect_h == 11:
                flags.append("MARS_TRANSIT_ASPECTS_H11_GAINS")
        if natal_h10_lord_house and natal_h10_lord_house in _mars_aspect_houses(mars_proj_h):
            flags.append("MARS_TRANSIT_ASPECTS_H10_LORD")

    # G34 — Jupiter transit aspects on career-relevant houses
    if jup_h:
        for aspect_h in _jupiter_aspect_houses_set(jup_h):
            if aspect_h == 10 and "JUPITER_H10_EXPANSION" not in flags:
                flags.append("JUP_TRANSIT_ASPECT_H10")
            elif aspect_h in (11, 2):
                flags.append(f"JUP_TRANSIT_ASPECT_H{aspect_h}_GAINS")
            if natal_h10_lord_house and aspect_h == natal_h10_lord_house and "JUPITER_ASPECTS_H10_LORD" not in flags:
                flags.append("JUP_TRANSIT_ASPECT_H10_LORD")

    # G34 — Saturn transit aspects on career-relevant houses
    if sat_h:
        for aspect_h in _saturn_aspect_houses_set(sat_h):
            if aspect_h == 10 and "SATURN_H10_AUTHORITY" not in flags and "SATURN_H10_BURDEN" not in flags:
                fn_sat_d = _FUNCTIONAL_NATURE.get(lagna_sign, {}).get("Saturn", 0)
                flags.append("SAT_TRANSIT_ASPECT_H10_POS" if fn_sat_d >= 0 else "SAT_TRANSIT_ASPECT_H10_DELAY")
            if natal_h10_lord_house and aspect_h == natal_h10_lord_house and "SATURN_ASPECTS_H10_LORD_POSITIVE" not in flags:
                flags.append("SAT_TRANSIT_ASPECT_H10_LORD")

    # G20 — Sun transit (≤180 days) — authority/recognition triggers
    sun_proj_h = projected.get("Sun", 0)
    if sun_proj_h and days_ahead <= 180:
        if sun_proj_h in (1, 10, 11):
            flags.append(f"SUN_TRANSIT_H{sun_proj_h}_AUTHORITY")

    # G20 — Mercury transit (≤120 days) — communication/negotiation windows
    merc_proj_h = projected.get("Mercury", 0)
    if merc_proj_h and days_ahead <= 120:
        if merc_proj_h in (2, 10, 11):
            flags.append(f"MERCURY_TRANSIT_H{merc_proj_h}_COMMUNICATION")

    # G-A15: Moon monthly transit — crystallization window for the period.
    # Moon transiting H10/H11/H1/H2 from natal lagna = most likely timing for events.
    # Only meaningful for near-term periods (≤45 days) since Moon moves ~1 house/2.5 days.
    moon_snap_h = snapshot_hp.get("Moon", 0)
    if moon_snap_h and days_ahead <= 45:
        if moon_snap_h in (1, 2, 10, 11):
            flags.append(f"MOON_TRANSIT_H{moon_snap_h}_CRYSTALLIZE")
        elif moon_snap_h in (6, 8, 12):
            flags.append(f"MOON_TRANSIT_H{moon_snap_h}_OBSTACLE")

    # G-A16: Varshaphal Muntha lord (Solar Return year lord).
    # Muntha advances 1 house per year from H1 at birth. Its lord colours the
    # entire solar year. When Muntha lord = MD or AD lord, the year is heightened.
    _dob_str = getattr(chart, "dob", "") or ""
    if _dob_str:
        try:
            _dob_d = date.fromisoformat(_dob_str)
            # Gap-21 (audit 2026-07) fix: calendar-year subtraction ignored whether
            # the solar return had occurred by the period midpoint — off by one
            # house for ~half of every year. Use completed solar years instead.
            _muntha_house = (int((mid - _dob_d).days / 365.25) % 12) + 1
            _chart_hl = chart.house_lords or {}
            _muntha_lord = _chart_hl.get(str(_muntha_house), "")
            if _muntha_lord:
                flags.append(f"MUNTHA_H{_muntha_house}_LORD_{_muntha_lord.upper()}")
        except (ValueError, AttributeError):
            pass

    # GAP FIX (2026-07-05): Vakri station-direct intensification flags computed
    # above during the retrograde-aware projection loop.
    flags.extend(_station_flags)

    return flags


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4b — Year-by-year Jupiter/Saturn/Rahu-Ketu transit outlook
# (2026-07-05: replaces the Mahadasha Narrative Arcs section in the report.
#  Deterministic, no LLM call — matches the year-by-year "Jupiter Transit
#  20XX" / "Saturn Transit 20XX-XX" / "Rahu-Ketu Transit 20XX-XX" structure
#  used by commercial Vedic transit reports, rather than dasha-period prose.)
# ═════════════════════════════════════════════════════════════════════════════

_JUPITER_FAVORABLE_HOUSES  = frozenset({2, 5, 9, 10, 11})
_JUPITER_CHALLENGING_HOUSES = frozenset({6, 8, 12})
_SATURN_DISRUPTION_HOUSES  = frozenset({6, 8})

_JUPITER_HOUSE_THEME: Dict[int, str] = {
    1:  "Self-projection and visibility rise; good window to raise your profile.",
    2:  "Income and resource growth; favorable for negotiating pay or new revenue lines.",
    3:  "Effort-driven gains through initiative, communication, or skill-building.",
    4:  "Domestic stability supports career; possible base/location change tied to home.",
    5:  "Recognition, strategic thinking, and creative/advisory work are favored.",
    6:  "Competitive pressure at work; good for overcoming rivals but watch overload.",
    7:  "Partnerships, client deals, and collaborations move to the foreground.",
    8:  "Behind-the-scenes transformation; restructuring, research, or a hidden setback.",
    9:  "Expansion, mentorship, and foreign/higher-authority opportunities open up.",
    10: "Direct career elevation — the classic Jupiter transit for promotion/authority.",
    11: "Gains, networks, and long-sought goals materialize; strong for income jumps.",
    12: "Withdrawal, cost, or relocation abroad; less visible, more internal growth.",
}

_SATURN_HOUSE_THEME: Dict[int, str] = {
    1:  "Sade Sati onset or personal-authority tests; discipline reshapes how you show up.",
    2:  "Income/resource pressure; Sade Sati peak zone if Moon is here — budget tightly.",
    3:  "Sade Sati exit zone if Moon is here; steady, effort-based consolidation.",
    4:  "Domestic/base restructuring; slow but stabilizing changes to your foundation.",
    5:  "Delayed recognition; strategic patience required before rewards show.",
    6:  "Hard work pays off against competition/debt; disruption if poorly supported.",
    7:  "Partnership responsibilities increase; contracts get more serious and binding.",
    8:  "High-disruption house — restructuring, layoffs, or forced transformation risk.",
    9:  "Authority earned through discipline; slow-building mentorship or credentials.",
    10: "Saturn's own domain — sustained authority if well-placed, burden if not.",
    11: "Gains arrive slowly but durably; long-term goals crystallize with effort.",
    12: "Isolation, cost, or foreign relocation; low-visibility, high-endurance phase.",
}

_RAHU_KETU_AXIS_THEME: Dict[int, str] = {
    1:  "Rahu H1/Ketu H7 — reinventing personal brand and identity at the cost of partnerships focus.",
    2:  "Rahu H2/Ketu H8 — unconventional income routes; detachment from inherited/shared resources.",
    3:  "Rahu H3/Ketu H9 — bold self-driven initiative; drifting from traditional mentors/beliefs.",
    4:  "Rahu H4/Ketu H10 — ambition to change base/location; career identity in flux.",
    5:  "Rahu H5/Ketu H11 — speculative or unconventional recognition; loosening grip on old networks.",
    6:  "Rahu H6/Ketu H12 — aggressive competitive drive; risk of burnout or hidden costs.",
    7:  "Rahu H7/Ketu H1 — foreign/major partnerships and deals; self-identity takes a back seat.",
    8:  "Rahu H8/Ketu H2 — sudden transformation or windfall/loss; shifting relationship to income.",
    9:  "Rahu H9/Ketu H3 — unconventional foreign/higher-ed path; less patience for routine effort.",
    10: "Rahu H10/Ketu H4 — rapid, unconventional career ascent; less anchoring in home life.",
    11: "Rahu H11/Ketu H5 — networked, digital, or rapid gains; detachment from ego-driven recognition.",
    12: "Rahu H12/Ketu H6 — foreign exposure or behind-the-scenes ambition; competitive drive recedes.",
}


def _annual_transit_snapshot(
    year_date: date,
    chart: Any,
    lagna_sign: str,
    today: date,
) -> Dict[str, Any]:
    """Compute real Jupiter/Saturn/Rahu/Ketu house positions for a given
    calendar anchor date and return a structured (non-prose) summary row.

    BUG FIX (2026-07-05): This previously mean-motion-projected forward from
    chart.transit_house_positions, a snapshot sourced from the input chart
    JSON's pyhora payload. Many chart files ship that field empty (no
    transit data at all), which silently produced "H0" for every planet —
    most visibly Jupiter/Saturn/Rahu/Ketu all showing "H0". Instead, this now
    calls the same ephemeris/orbital-model helper micro_timing.py already
    uses elsewhere (_get_all_planet_positions), which independently computes
    each planet's real sidereal sign/house for an arbitrary date — no
    dependency on the chart JSON carrying live transit data at all.
    """
    from .micro_timing import _get_all_planet_positions

    positions = _get_all_planet_positions(year_date, lagna_sign) or {}
    jup_h  = positions.get("Jupiter", {}).get("house", 0)
    sat_h  = positions.get("Saturn", {}).get("house", 0)
    rahu_h = positions.get("Rahu", {}).get("house", 0)
    ketu_h = positions.get("Ketu", {}).get("house", 0)

    natal_moon_house = (getattr(chart, "planet_house", {}) or {}).get("Moon", 0)
    sade_sati_phase = ""
    if sat_h and natal_moon_house and sat_h in _sade_sati_houses(natal_moon_house):
        sade_sati_phase = _sade_sati_phase(sat_h, natal_moon_house)

    fn = _FUNCTIONAL_NATURE.get(lagna_sign, {})
    sat_fn = fn.get("Saturn", 0)
    jup_fn = fn.get("Jupiter", 0)

    jup_signal = "favorable" if jup_h in _JUPITER_FAVORABLE_HOUSES else (
        "challenging" if jup_h in _JUPITER_CHALLENGING_HOUSES else "neutral")
    if jup_signal == "favorable" and jup_fn < 0:
        jup_signal = "mixed"   # good house, but Jupiter is functionally malefic for this lagna

    # Gap fix (2026-07-05, user-reported): the Saturn transit signal previously
    # relied only on `sat_fn` (a per-lagna functional-benefic/malefic table,
    # generic to the ascendant sign) and the transit house — it never looked at
    # Saturn's own NATAL placement/dignity/lordship for this specific chart, so
    # the resulting narrative text read as boilerplate regardless of whether
    # Saturn natally sits exalted in Libra or debilitated in Aries for this
    # person, or which houses Saturn itself rules. Pull natal Saturn's house,
    # dignity, and lordships in so both the signal itself and the accompanying
    # narrative can be anchored to this chart's real Saturn, not a generic table.
    _natal_saturn_house = (getattr(chart, "planet_house", {}) or {}).get("Saturn", 0)
    _natal_saturn_dignity = str((getattr(chart, "planet_dignities", {}) or {}).get("Saturn", "")).upper()
    _house_lords_natal = getattr(chart, "house_lords", {}) or {}
    _natal_saturn_rules = sorted(
        int(h) for h, lord in _house_lords_natal.items()
        if lord == "Saturn" and str(h).isdigit()
    )
    _sat_dignity_bonus = {"EXALTED": 0.5, "OWN": 0.3, "DEBILITATED": -0.5}.get(_natal_saturn_dignity, 0.0)
    # A natally strong Saturn (exalted/own) tempers an otherwise-challenging
    # transit house; a natally weak (debilitated) Saturn worsens an otherwise-
    # neutral/favorable one — this is what makes the resulting signal specific
    # to THIS chart's Saturn rather than a lagna-generic lookup.
    _effective_sat_fn = sat_fn + _sat_dignity_bonus

    if sade_sati_phase:
        sat_signal = "challenging" if _effective_sat_fn < 0 else "mixed"
    elif sat_h == 10:
        sat_signal = "favorable" if _effective_sat_fn >= 0 else "challenging"
    elif sat_h in _SATURN_DISRUPTION_HOUSES:
        sat_signal = "challenging" if _effective_sat_fn <= 0.3 else "mixed"
    elif _effective_sat_fn >= 0.5:
        sat_signal = "favorable"   # natally strong Saturn upgrades an otherwise-neutral transit
    elif _effective_sat_fn <= -0.5:
        sat_signal = "challenging"  # natally weak/debilitated Saturn downgrades a neutral transit
    else:
        sat_signal = "neutral"

    # Net career signal — simple majority vote across the three transit factors.
    _signals = [jup_signal, sat_signal]
    _favor_ct = _signals.count("favorable")
    _chall_ct = _signals.count("challenging") + _signals.count("mixed") * 0.5
    if _favor_ct > _chall_ct:
        net_signal = "Favorable"
    elif _chall_ct > _favor_ct:
        net_signal = "Challenging"
    else:
        net_signal = "Mixed"

    return {
        "year":              year_date.year,
        "date":              year_date.isoformat(),
        "jupiter_house":     jup_h,
        "jupiter_theme":     _JUPITER_HOUSE_THEME.get(jup_h, ""),
        "jupiter_signal":    jup_signal,
        "saturn_house":      sat_h,
        "saturn_theme":      _SATURN_HOUSE_THEME.get(sat_h, ""),
        "saturn_signal":     sat_signal,
        # Gap fix (2026-07-05, user-reported): expose the natal grounding so
        # the HTML/LLM narrative layer can reference this chart's actual
        # Saturn (house/dignity/lordships) instead of generic transit-only text.
        "saturn_natal_house":    _natal_saturn_house,
        "saturn_natal_dignity":  _natal_saturn_dignity or "NEUTRAL",
        "saturn_rules_houses":   _natal_saturn_rules,
        "sade_sati_phase":   sade_sati_phase,
        "rahu_house":        rahu_h,
        "ketu_house":        ketu_h,
        "rahu_ketu_theme":   _RAHU_KETU_AXIS_THEME.get(rahu_h, ""),
        "net_signal":        net_signal,
    }


def build_annual_transit_outlook(
    chart: Any,
    lagna_sign: str,
    today: Optional[date] = None,
    years_ahead: int = 4,
    years_back: int = 1,
) -> List[Dict[str, Any]]:
    """Build the deterministic year-by-year Jupiter/Saturn/Rahu-Ketu transit
    outlook table (`years_back` prior years, through current year, through
    `years_ahead` following years — default: last 1 year + next 4 years).

    2026-07-05: window widened from "current + 2 years ahead" to "1 year back
    + 3 years ahead" (5 anchor years total) to replace the removed detailed
    Dasha-Period Timeline with a wider before/after career + transit picture.

    Mirrors the year-by-year transit-report structure used by mainstream
    Vedic career reports (Jupiter Transit 20XX / Saturn Transit 20XX-XX /
    Rahu-Ketu Transit 20XX-XX), computed via ephemeris/orbital-model house
    positions rather than a dasha-period prose summary.
    """
    today = today or date.today()
    rows: List[Dict[str, Any]] = []
    for offset in range(-years_back, years_ahead + 1):
        anchor = date(today.year + offset, today.month, today.day) if not (
            today.month == 2 and today.day == 29
        ) else date(today.year + offset, 2, 28)
        row = _annual_transit_snapshot(anchor, chart, lagna_sign, today)
        row["is_past"] = offset < 0
        row["is_current_year"] = offset == 0
        # User-reported gap fix (2026-07): a single anchor-date snapshot per
        # calendar year collapses a genuine mid-year Jupiter/Saturn sign
        # change into one blended reading (e.g. "2026: Jupiter H1" when
        # Jupiter actually moves H1->H2 partway through the year). Sample
        # quarterly across the same calendar year and record sub-windows
        # whenever Jupiter's or Saturn's house differs from the prior
        # quarter — attached as `sub_windows`, additive (existing consumers
        # reading the single annual snapshot fields are unaffected).
        row["sub_windows"] = _quarterly_transit_sub_windows(
            date(anchor.year, 1, 1), date(anchor.year, 12, 31), chart, lagna_sign, today
        )
        rows.append(row)
    return rows


def _quarterly_transit_sub_windows(
    year_start: date, year_end: date, chart: Any, lagna_sign: str, today: date,
) -> List[Dict[str, Any]]:
    """Sample Jupiter/Saturn house positions at quarterly anchors across one
    calendar year and collapse consecutive identical readings into date-
    bounded windows. Quarterly resolution is enough to catch Jupiter's
    ~1-year-per-sign and Saturn's ~2.5-year-per-sign transitions without the
    cost of daily sampling — a sign change happens at most once or twice a
    year for either planet."""
    from .micro_timing import _get_all_planet_positions
    _natal_moon_house = (getattr(chart, "planet_house", {}) or {}).get("Moon", 0)
    _anchors = [year_start + timedelta(days=int(round(365.25 * q / 4))) for q in range(4)]
    _anchors = [min(a, year_end) for a in _anchors]
    _samples = []
    for _a in _anchors:
        _pos = _get_all_planet_positions(_a, lagna_sign) or {}
        _jh = _pos.get("Jupiter", {}).get("house", 0)
        _sh = _pos.get("Saturn", {}).get("house", 0)
        # User-reported gap fix (2026-07): Sade Sati was flagged only once per
        # year at the single annual anchor date, blurring RISING -> PEAK ->
        # EXITING transitions that genuinely happen mid-year as Saturn moves
        # between the 12th/1st/2nd houses from natal Moon. Computed per
        # quarterly sample here using the same classical phase logic
        # (`_sade_sati_phase`) already used for the single-anchor version.
        _ss_phase = ""
        if _natal_moon_house and _sh in _sade_sati_houses(_natal_moon_house):
            _ss_phase = _sade_sati_phase(_sh, _natal_moon_house)
        _samples.append((_a, _jh, _sh, _ss_phase))

    windows = []
    _cur_start, _cur_jh, _cur_sh, _cur_ss = _samples[0]
    for i in range(1, len(_samples)):
        _a, _jh, _sh, _ss = _samples[i]
        if _jh != _cur_jh or _sh != _cur_sh or _ss != _cur_ss:
            windows.append({
                "start_date": _cur_start.isoformat(), "end_date": _a.isoformat(),
                "jupiter_house": _cur_jh, "saturn_house": _cur_sh,
                "sade_sati_phase": _cur_ss,
            })
            _cur_start, _cur_jh, _cur_sh, _cur_ss = _a, _jh, _sh, _ss
    windows.append({
        "start_date": _cur_start.isoformat(), "end_date": year_end.isoformat(),
        "jupiter_house": _cur_jh, "saturn_house": _cur_sh,
        "sade_sati_phase": _cur_ss,
    })
    return windows if len(windows) > 1 else []


_NATURAL_MALEFICS = ("Rahu", "Ketu", "Saturn", "Mars")


def _house_malefic_afflictions(planet_house: Dict[str, int], house: int,
                                exclude: str = "") -> list:
    """Return the natural malefics (Rahu/Ketu/Saturn/Mars) that co-occupy
    `house` alongside the benefic being evaluated for an "unafflicted benefic"
    yoga precondition (Amala and similar). `exclude` is the benefic planet
    itself so it never flags itself. Generic on purpose — reusable by any
    yoga detector with a classical "benefic must be unafflicted" clause, not
    just Amala Yoga (2026-07-05 gap fix)."""
    return [
        m for m in _NATURAL_MALEFICS
        if m != exclude and planet_house.get(m, 0) == house
    ]


def _detect_natal_yogas(planet_house: Dict[str, int], lagna_sign: str,
                        house_lords: Optional[Dict[str, str]] = None,
                        planet_sign: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Detect natal yogas (expanded to 20+ types); return {yoga_name: forming_planet}.

    Now includes:
      Classical 7: Gajakesari, Budha-Aditya, 5 Panch Mahapurusha
      Extended 13: Rajayoga, Dhana, Neecha Bhanga, Viparita (Harsha/Sarala/Vimala),
                   Adhi, Chamara, Amala, Vasumati, Kemadruma (absence), Kala Sarpa
    """
    yogas: Dict[str, str] = {}
    ph = planet_house or {}
    hl = house_lords or {}
    ps = planet_sign or {}
    _KENDRA_SET = {1, 4, 7, 10}
    _TRIK_SET   = {1, 5, 9}
    _DUSTH      = {6, 8, 12}
    ls_idx = _SIGN_SEQUENCE.index(lagna_sign) if lagna_sign in _SIGN_SEQUENCE else 0

    def house_sign(h: int) -> str:
        return _SIGN_SEQUENCE[(ls_idx + h - 1) % 12]

    # ── Classical 7 ──────────────────────────────────────────────────────────
    moon_h = ph.get("Moon", 0)
    jup_h  = ph.get("Jupiter", 0)
    if moon_h and jup_h and (jup_h - moon_h) % 12 in (0, 3, 6, 9):
        yogas["Gajakesari"] = "Jupiter"

    if ph.get("Sun") and ph.get("Sun") == ph.get("Mercury"):
        yogas["Budha_Aditya"] = "Mercury"

    for planet, yoga_name in [
        ("Mars", "Ruchaka"), ("Mercury", "Bhadra"),
        ("Jupiter", "Hamsa"), ("Venus", "Malavya"), ("Saturn", "Sasha"),
    ]:
        h = ph.get(planet, 0)
        if h and h in _KENDRA_SET:
            sign = house_sign(h)
            if sign in _PLANET_OWN_SIGNS.get(planet, []) or sign == _PLANET_EXALT_SIGN.get(planet, ""):
                yogas[yoga_name] = planet

    # ── Rajayoga: lord of trikona + lord of kendra in association ────────────
    trikona_lords  = {hl.get(str(h), "") for h in (1, 5, 9)}
    kendra_lords   = {hl.get(str(h), "") for h in (1, 4, 7, 10)}
    trikona_lords.discard("")
    kendra_lords.discard("")
    for t_lord in trikona_lords:
        for k_lord in kendra_lords:
            if t_lord == k_lord:
                continue  # same planet = automatically Rajayoga if it's a dual lord
            if ph.get(t_lord, 0) and ph.get(t_lord) == ph.get(k_lord):
                # Store BOTH forming planets so the bonus fires in EITHER planet's dasha.
                # Previously only t_lord was stored → k_lord's dasha never triggered bonus.
                yogas["Rajayoga"]      = t_lord   # trikona lord → full boost
                yogas["Rajayoga_pair"] = k_lord   # kendra lord  → same boost (Step 2 fix)
                break
            # Conjunction within same house already caught above; also check mutual aspect
        if "Rajayoga" in yogas:
            break

    # Dual kendra-trikona lordship (pure Trikona H5/H9 + Kendra H4/H7/H10)
    # A2 fix: exclude h_trik=1 (Lagna).  H1 is simultaneously Kendra+Trikona,
    # so a planet owning H1 AND another Kendra (H4/H7/H10) has dual-Kendra
    # ownership → Kendraadhipati Dosha, NOT Rajayoga.  Only fire when the
    # "trikona" house is a PURE trikona (H5 or H9).
    for h_trik in (5, 9):
        for h_kend in (4, 7, 10):
            lord_t = hl.get(str(h_trik), "")
            lord_k = hl.get(str(h_kend), "")
            if lord_t and lord_t == lord_k:
                yogas[f"Rajayoga_H{h_trik}H{h_kend}"] = lord_t

    # ── Dhana Yoga: 2nd + 11th lord in association ────────────────────────────
    l2 = hl.get("2", "")
    l11 = hl.get("11", "")
    if l2 and l11 and l2 != l11:
        if ph.get(l2, 0) and ph.get(l2) == ph.get(l11):
            yogas["Dhana_Yoga"] = l2

    # ── Neecha Bhanga Raja Yoga ───────────────────────────────────────────────
    from .astro_enhancer import _g5_neecha_bhanga as _nb_check
    for pl in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        if _nb_check(pl, ps, ph):
            yogas[f"Neecha_Bhanga_{pl}"] = pl

    # ── Viparita Raja Yoga (Harsha / Sarala / Vimala) ────────────────────────
    h6l = hl.get("6", "")
    h8l = hl.get("8", "")
    h12l = hl.get("12", "")
    if h6l and ph.get(h6l, 0) in _DUSTH:
        yogas["Harsha_VRY"] = h6l
    if h8l and ph.get(h8l, 0) in _DUSTH:
        yogas["Sarala_VRY"] = h8l
    if h12l and ph.get(h12l, 0) in _DUSTH:
        yogas["Vimala_VRY"] = h12l

    # ── Adhi Yoga: benefics in H6/H7/H8 from Moon ────────────────────────────
    if moon_h:
        _benefics_placed = [
            p for p in ("Jupiter", "Venus", "Mercury")
            if ph.get(p, 0) and (ph[p] - moon_h) % 12 + 1 in (6, 7, 8)
        ]
        if len(_benefics_placed) >= 2:
            yogas["Adhi_Yoga"] = _benefics_placed[0]

    # ── Chamara Yoga: lagna lord exalted or own in kendra, Jupiter aspects ───
    lag_lord = hl.get("1", "")
    lag_lord_h = ph.get(lag_lord, 0) if lag_lord else 0
    if lag_lord_h and lag_lord_h in _KENDRA_SET:
        sig = house_sign(lag_lord_h)
        if sig in _PLANET_OWN_SIGNS.get(lag_lord, []) or sig == _PLANET_EXALT_SIGN.get(lag_lord, ""):
            if jup_h and lag_lord_h in _jupiter_aspect_houses_set(jup_h):
                yogas["Chamara_Yoga"] = lag_lord

    # ── Amala Yoga: benefic in H10 from lagna or Moon ────────────────────────
    # Gap fix (2026-07-05): classical Amala Yoga requires the benefic occupying
    # the 10th to be genuinely UNAFFLICTED. This detector previously flagged
    # "Amala_Yoga" purely on house placement, with zero affliction check — so
    # a chart where Ketu (or Rahu/Saturn/Mars) co-occupies the same 10th house
    # as the benefic still got the full, unqualified "spotless career" yoga
    # label, directly contradicting the report's own separate narrative about
    # that same house's Ketu-driven detachment/volatility. `_house_malefic_afflictions`
    # below is a small generic helper (reused by other "unafflicted benefic"
    # yoga preconditions, not just this one) that reports which natural
    # malefics share a given house. When present, the yoga is kept (the
    # benefic placement itself is real) but downgraded to a distinct
    # "Amala_Yoga_Partial" key so the narrative/explanation layer can qualify
    # the language instead of asserting an unblemished result outright.
    for benefic in ("Jupiter", "Venus", "Mercury", "Moon"):
        benefic_h = ph.get(benefic, 0)
        if benefic_h == 10:
            _afflictions = _house_malefic_afflictions(ph, benefic_h, exclude=benefic)
            if _afflictions:
                # Encode the afflictor list in the yoga key itself (rather than a
                # separate dict entry) so this dict's contract — {yoga_name:
                # forming_planet} — is preserved for every existing consumer
                # (_score_period's active_yogas/yoga_bonus loops both assume every
                # value is a real planet name and would otherwise misinterpret or
                # silently leak a stray metadata string into the UI's yoga badges).
                yogas[f"Amala_Yoga_Partial__{'_'.join(_afflictions)}"] = benefic
            else:
                yogas["Amala_Yoga"] = benefic
            break

    # ── Vasumati Yoga: benefics in upachaya (3/6/10/11) from Moon ────────────
    if moon_h:
        _upachaya_benefics = [
            p for p in ("Jupiter", "Venus", "Mercury")
            if ph.get(p, 0) and (ph[p] - moon_h) % 12 + 1 in (3, 6, 10, 11)
        ]
        if len(_upachaya_benefics) >= 3:
            yogas["Vasumati_Yoga"] = _upachaya_benefics[0]

    # ── Kemadruma check (absence yoga — reduces score if no planet flanks Moon) ─
    if moon_h:
        prev_m = (moon_h - 2) % 12 + 1
        next_m = moon_h % 12 + 1
        planets_check = [p for p in ph if p not in ("Rahu", "Ketu", "Moon")]
        flanking = any(ph[p] in (prev_m, next_m) for p in planets_check if ph.get(p, 0))
        if not flanking:
            yogas["Kemadruma"] = "Moon"   # debilitating yoga

    # ── Kala Sarpa Yoga ────────────────────────────────────────────────────────
    rahu_h = ph.get("Rahu", 0)
    ketu_h = ph.get("Ketu", 0)
    if rahu_h and ketu_h:
        _bodies_hs = [ph.get(p, 0) for p in
                      ("Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn")
                      if ph.get(p, 0)]
        # Build clockwise arc from Rahu to Ketu
        _arc: set = set()
        _h = rahu_h % 12 + 1
        while _h != ketu_h:
            _arc.add(_h)
            _h = _h % 12 + 1
        if _bodies_hs and all(bh in _arc or bh == rahu_h for bh in _bodies_hs):
            yogas["Kala_Sarpa"] = "Rahu"

    # ── G-A5: Parivartana Yoga (mutual sign exchange) for career houses ───────
    # H10↔H1, H10↔H2, H10↔H11: lord of each pair exchanges signs = strong career yoga.
    # H10 lord in sign of H1/H2/H11 lord AND that lord in sign of H10 lord.
    if planet_sign:
        l10 = hl.get("10", "")
        _parivartana_pairs = [
            ("1",  "Parivartana_H10_H1"),
            ("2",  "Parivartana_H10_H2"),
            ("11", "Parivartana_H10_H11"),
            ("6",  "Parivartana_H10_H6"),   # service ↔ career = strong employment yoga
        ]
        for _hstr, _yoga_key in _parivartana_pairs:
            l_other = hl.get(_hstr, "")
            if not l10 or not l_other or l10 == l_other:
                continue
            # Check if l10 is in the sign of l_other AND l_other is in sign of l10
            sign_l10     = planet_sign.get(l10, "")
            sign_l_other = planet_sign.get(l_other, "")
            expected_l10_sign     = house_sign(int(_hstr))  # sign ruled by l_other (their house sign)
            expected_l_other_sign = house_sign(10)           # sign ruled by l10 (H10 sign)
            if (sign_l10 == expected_l10_sign and sign_l_other == expected_l_other_sign):
                yogas[_yoga_key] = l10

    # ── G-A6: 22nd Drekkana lord — proxy: lord of 8th house sign ─────────────
    # Classically, the 22nd Drekkana from lagna = first drekkana of the 8th sign.
    # When active as MD/AD lord, it signals a challenging/obstacle period.
    _l8 = hl.get("8", "")
    if _l8:
        yogas["Drekkana_22_Risk"] = _l8

    # ── G-A6: 64th Navamsha lord from Moon — 16th nakshatra from Moon's nak ──
    # When this lord runs as MD/AD, the period carries heightened volatility.
    _nak_seq = [
        "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
        "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni",
        "Uttara Phalguni","Hasta","Chitra","Swati","Vishakha","Anuradha",
        "Jyeshtha","Mula","Purva Ashadha","Uttara Ashadha","Shravana",
        "Dhanishta","Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati",
    ]
    _moon_nak_name = planet_sign.get("_moon_nakshatra", "") if planet_sign else ""
    # Use the nakshatra sequence with Moon's nakshatra from the outer scope if available
    # (passed via the ps dict convention; computed in _detect_natal_yogas callers)
    if _moon_nak_name and _moon_nak_name in _nak_seq:
        _moon_idx = _nak_seq.index(_moon_nak_name)
        _ns64_idx = (_moon_idx + 15) % 27   # 64th navamsha = 16th nakshatra forward (0-indexed)
        _ns64_nak = _nak_seq[_ns64_idx]
        _ns64_lord = _NAKSHATRA_LORD.get(_ns64_nak, "")
        if _ns64_lord:
            yogas["NS64_Risk"] = _ns64_lord

    return yogas


def _sade_sati_houses(moon_h: int) -> frozenset:
    return frozenset([((moon_h - 2) % 12) + 1, moon_h, (moon_h % 12) + 1])


def _sade_sati_phase(sat_h: int, moon_h: int) -> str:
    if sat_h == ((moon_h - 2) % 12) + 1:
        return "RISING"
    if sat_h == moon_h:
        return "PEAK"
    return "EXITING"


def _jupiter_aspect_houses(house: int) -> frozenset:
    """Jupiter aspects 5th, 7th, 9th from itself (classical).
    GAP-FIX (2026-08-22): offsets were N-1 (off-by-one); corrected to N-2,
    matching this module's own _compute_arudha convention
    ((lord_house + steps - 1) % 12 + 1)."""
    return frozenset([
        ((house + 3) % 12) + 1,
        ((house + 5) % 12) + 1,
        ((house + 7) % 12) + 1,
    ])


def _saturn_aspect_houses(house: int) -> frozenset:
    """Saturn's special aspects: 3rd and 10th from itself.
    GAP-FIX (2026-08-22): offsets were N-1 (off-by-one); corrected to N-2."""
    return frozenset([
        ((house + 1) % 12) + 1,   # 3rd aspect
        ((house + 8) % 12) + 1,   # 10th aspect
    ])


def _mars_aspect_houses(house: int) -> frozenset:
    """RECONSTRUCTION NOTE (2026-07-07): called from this module (line ~2128/
    ~2135 at the time of this fix) but never defined anywhere — same
    corruption pattern as several other reconstructions this session.
    Mars's special aspects: 4th, 7th, 8th from itself (classical Vedic
    drishti rule), matching the exact sibling convention immediately above
    (_jupiter_aspect_houses / _saturn_aspect_houses already in this file).
    GAP-FIX (2026-08-22): offsets were N-1 (off-by-one); corrected to N-2."""
    return frozenset([
        ((house + 2) % 12) + 1,   # 4th aspect
        ((house + 5) % 12) + 1,   # 7th aspect (universal)
        ((house + 6) % 12) + 1,   # 8th aspect
    ])


# RECONSTRUCTION NOTE (2026-07-07): call sites in this module use the
# "_set"-suffixed names (_jupiter_aspect_houses_set / _saturn_aspect_houses_set)
# while only the non-suffixed functions above are actually defined — these
# thin aliases restore the exact names the call sites expect without
# duplicating the (already correct) aspect-house logic above.
_jupiter_aspect_houses_set = _jupiter_aspect_houses
_saturn_aspect_houses_set = _saturn_aspect_houses


# ═════════════════════════════════════════════════════════════════════════════
# STEP 5 — Event classification (decision tree)
# ═════════════════════════════════════════════════════════════════════════════

def _classify_event(
    scores: Dict[str, float],
    flags: List[str],
    career_ctx: Dict[str, Any],
    payload: Any,
    mode: str,
    previous_event: str = "",
    macro_score: float = 1.0,
    cooldown_by_tier: Optional[Dict[str, bool]] = None,   # GAP 7: replaces cooldown_active
    kp_house_chain: Optional[Dict[str, Any]] = None,       # GAP 2 (2026-07-07): KP promotion override input
) -> Tuple[str, List[str], str]:
    """Return (event_type, active_houses_list, near_miss).

    near_miss is a non-empty string when a high-value event gate (PROMOTION /
    LEADERSHIP_EXPANSION) was triggered but the inner house-activity check
    failed, e.g. "PROMOTION — H10/H1/H11 not active".

    Applies designation and experience gates before assigning event type.
    """
    near_miss: str = ""
    score    = scores["career_score"]
    ca       = scores["career_activation"]
    fn       = scores["functional_nature"]
    ha       = scores["house_activation"]
    desig    = career_ctx.get("designation", "")
    yoe      = career_ctx.get("years_experience")
    status   = career_ctx.get("employment_status", "employed")
    outcome  = career_ctx.get("desired_outcome", "")

    # Determine active houses (informational)
    ph = getattr(payload, "planet_house", {}) or {}
    hl = getattr(payload, "house_lords", {}) or {}
    active_h = set()
    for planet in [scores.get("_md_lord", ""), scores.get("_ad_lord", "")]:
        occ = ph.get(planet, 0)
        if occ:
            active_h.add(occ)
        for hstr, lord in hl.items():
            if lord == planet:
                try:
                    active_h.add(int(hstr))
                except ValueError:
                    pass

    adverse_flags = [f for f in flags if any(k in f for k in ("STRESS","BURDEN","DISRUPTION","PEAK","RISING","OBSTACLE"))]
    expansion_flags = [f for f in flags if any(k in f for k in ("EXPANSION","AUTHORITY","OPPORTUNITY","EXITING","CRYSTALLIZE"))]

    ad_lord = scores.get("_ad_lord", "")
    md_lord = scores.get("_md_lord", "")

    # G-A16: Muntha lord matching the MD/AD lord boosts expansion signal strength.
    # (Flag format: MUNTHA_H{n}_LORD_{PLANET})
    _muntha_md_match = any(
        ("MUNTHA" in f and md_lord.upper() in f) or ("MUNTHA" in f and ad_lord.upper() in f)
        for f in flags
    )
    if _muntha_md_match:
        expansion_flags.append("MUNTHA_DASHA_LORD_MATCH")  # counts as an expansion signal

    # H8 in active houses is a negative modifier
    h8_active = 8 in active_h

    # ── Gate: re-entry (unemployed only) (GAP-2 FIX) ────────────────────────
    # H8 active no longer blocks RE_ENTRY; 8th house transformation is actually
    # the most common trigger for career re-entries. Flag it instead.
    if status == "unemployed":
        if ca >= 0.4 and fn >= 0.5:
            if h8_active:
                flags.append("H8_TRANSFORMATION_ACTIVE")
            return ("RE_ENTRY", sorted(active_h), near_miss)
        return ("STABILITY", sorted(active_h), near_miss)

    # ── Gate: limited mode (young / unemployed <22) (GAP-2 FIX) ─────────────
    if mode == "limited":
        if ca >= 0.4:
            return ("FIRST_JOB", sorted(active_h), near_miss)    # first career entry window
        if ca >= 0.3:
            return ("TRANSITION", sorted(active_h), near_miss)   # preparatory window
        return ("STABILITY", sorted(active_h), near_miss)

    # ── CHALLENGE / RISK_PERIOD / adverse-event subsystem ─────────────────────
    # Job-loss framework (G1/G2/G11): before collapsing everything into the
    # coarse RISK_PERIOD bucket, run the multi-layer confirmation ledger. It
    # only returns a concrete adverse event (JOB_LOSS / FORCED_EXIT /
    # BURNOUT_EXIT / ROLE_RESTRUCTURING / JOB_CHANGE) when the evidence is
    # strong; otherwise it returns None and we fall through exactly as before.
    # Clean/positive periods never reach a "high" ledger label, so PROMOTION /
    # GROWTH / STABILITY outcomes are unaffected.
    has_sade_sati_peak = "SADE_SATI_PEAK" in flags
    _coarse_adverse = (
        ((fn < 0.3 or h8_active) and len(adverse_flags) >= 1)
        or (has_sade_sati_peak and score < 0.45)
    )
    try:
        _adv_event, _adv_detail = classify_adverse_event(
            scores, flags, payload, active_h,
            coarse_adverse=_coarse_adverse,
            known_events_present=_has_known_past_events(career_ctx),
        )
    except Exception:   # never let the adverse layer break the timeline
        _adv_event, _adv_detail = (None, {})
    if _adv_detail:
        scores["_adverse_detail"] = _adv_detail
    if _adv_event:
        return (_adv_event, sorted(active_h), near_miss)
    if _coarse_adverse:
        return ("RISK_PERIOD", sorted(active_h), near_miss)

    # Dasha Chidra / Sandhi must be known before positive-event early returns.
    # Low-score sandhi is its own event; high-score sandhi keeps its event type
    # but carries a volatility note through near_miss.
    if scores.get("is_sandhi"):
        if score < 0.55:
            return ("SANDHI_PERIOD", sorted(active_h), near_miss)
        near_miss = (
            "SANDHI_VOLATILE - strong period but dasha junction; "
            "outcomes may reverse or delay"
        )

    # GAP 7 fix: tier-stratified cooldown — each tier has its own suppression window.
    _cbt            = cooldown_by_tier or {}
    _on_cooldown    = _cbt.get("high", False)    # BREAKTHROUGH tier (24 months)
    _cooldown_mid   = _cbt.get("mid",  False)    # PROMOTION tier (18 months)
    _cooldown_low   = _cbt.get("low",  False)    # LEADERSHIP_EXPANSION tier (12 months)
    _cooldown_inc   = _cbt.get("income", False)  # SALARY_HIKE/INCOME_INFLECTION (6 months)

    # ── GAP 4: Macro-economic headwind check ──────────────────────────────
    # Below the headwind threshold, peak astrological events manifest as
    # expanded scope/authority rather than direct title/salary changes.
    _macro_headwind = macro_score < _MACRO_HEADWIND_THRESHOLD

    # ── BREAKTHROUGH / LEADERSHIP_EXPANSION high-signal tier (GAP-2 FIX) ─────
    # When all signal conditions are met, directors+ get BREAKTHROUGH.
    # Others (junior/mid) are no longer silently dropped — they get LEADERSHIP_EXPANSION.
    if ca >= 0.8 and scores["strength_product"] >= 0.65 and len(expansion_flags) >= 1:
        if _on_cooldown or _macro_headwind:
            # Cooldown or macro headwinds: step down to LEADERSHIP_EXPANSION
            return ("LEADERSHIP_EXPANSION", sorted(active_h), near_miss)
        if _gate_designation(desig, yoe, "director"):
            return ("BREAKTHROUGH", sorted(active_h), near_miss)
        else:
            return ("LEADERSHIP_EXPANSION", sorted(active_h), near_miss)

    # ── PROMOTION ────────────────────────────────────────────────────────────
    # Gate: not already csuite; experience threshold met
    if (ca >= 0.65 and fn >= 0.6 and score >= 0.65
            and desig != "csuite"
            and _exp_ok(yoe, desig)):
        if {10, 1} & active_h or {10, 11} & active_h:
            if _cooldown_mid or _macro_headwind:   # GAP 7: PROMOTION-tier cooldown
                # Cooldown or macro headwinds: lateral growth, not title jump
                return ("LEADERSHIP_EXPANSION", sorted(active_h), near_miss)
            # ── GAP 2 fix (2026-07-07, user-reported): KP override ──────────
            # The house-activation gate above (active_h from planet_house/
            # house_lords) is a coarse, whole-chart signal — it does not
            # check whether the classical KP promotion significators
            # (houses 2/6/10/11) are actually tied to the RUNNING MD/AD lord
            # via their cuspal sub-lord chain. A chart can pass the coarse
            # gate above (MD/AD lord occupies/rules H10 or H1/H11 natally)
            # while the KP cuspal chain for 2/6/10/11 is genuinely weak for
            # THIS SPECIFIC period, and simultaneously have a strong KP tie
            # on the foreign/job-change houses (12/3/9) or leadership houses
            # (10/1). In that case classical KP practice would not confirm
            # a literal title-change "Promotion" — it reads as expanded
            # scope/mandate/visibility instead. See
            # gap_corrections_career_timeline_2026_07.kp_promotion_override()
            # for the exact bounded rule (weak/strong thresholds, conservative
            # None-on-missing-data behavior). This only overrides the LABEL
            # returned here; it does not touch career_score or any other
            # scoring input, so it cannot alter which period gets picked as
            # "best" elsewhere in the pipeline.
            if kp_house_chain:
                # GAP 3 fix (2026-07-07 follow-up audit): use the structured
                # decision function so kp_override_applied/kp_override_reason
                # (real deterministic fields, not just a narrative string)
                # can be set on `scores` and later surfaced onto the block by
                # build_career_timeline() below (see "kp_override_applied"/
                # "kp_override_reason" in the block dict construction).
                try:
                    from .gap_corrections_career_timeline_2026_07 import kp_promotion_override_decision
                    _kp_decision = kp_promotion_override_decision(kp_house_chain, md_lord, ad_lord)
                except Exception:
                    _kp_decision = {"applied": False, "reason": "", "target_event_type": ""}
                scores["_kp_override_applied"] = bool(_kp_decision.get("applied"))
                scores["_kp_override_reason"] = _kp_decision.get("reason", "")
                if _kp_decision.get("applied"):
                    _target = _kp_decision.get("target_event_type") or "LEADERSHIP_EXPANSION"
                    scores["_kp_promotion_override_label"] = (
                        "Role expansion / global mandate / external opportunity / leadership visibility"
                    )
                    return (_target, sorted(active_h), near_miss)
            return ("PROMOTION", sorted(active_h), near_miss)
        else:
            # Gate passed but H10/H1/H11 not active — record near-miss
            near_miss = "PROMOTION — H10/H1/H11 not active (active: {})".format(
                ",".join(f"H{h}" for h in sorted(active_h)) or "none"
            )

    # ── LEADERSHIP_EXPANSION ─────────────────────────────────────────────────
    # Gate: experience ≥ 5, designation ≥ senior
    # G-A10 fix: H3 replaced with H11 (income/gain). Classical leadership expansion
    # requires career (H10) + self-assertion (H1) + gains/elevation (H11), NOT H3.
    # H3 (Parakrama) drives communication/effort roles, not leadership elevation.
    if (ca >= 0.6 and score >= 0.6
            and _gate_designation(desig, yoe, "senior")
            and (yoe is None or yoe >= 5)
            and not _cooldown_low):    # GAP 7: LEADERSHIP_EXPANSION-tier cooldown
        if {10, 1, 11} & active_h:
            return ("LEADERSHIP_EXPANSION", sorted(active_h), near_miss)
        elif not near_miss:
            # Gate passed but H10/H1/H11 not active — record near-miss
            near_miss = "LEADERSHIP_EXPANSION — H10/H1/H11 not active (active: {})".format(
                ",".join(f"H{h}" for h in sorted(active_h)) or "none"
            )

    # ── INCOME_INFLECTION ─────────────────────────────────────────────────────
    if {11, 2} & active_h and scores["strength_product"] >= 0.55 and ca >= 0.5:
        return ("INCOME_INFLECTION", sorted(active_h), near_miss)

    # ── G-A7: CAREER_THROUGH_PARTNERSHIP (H7 = 10th from 10th, bhavat bhavam) ─
    # H7 is the 10th from the 10th: career growth via business partners, clients,
    # alliances, or international contracts. Previously excluded as "business house".
    # Re-included: H7 activation + H10 in active_h is a leadership-through-network signal.
    # Resolves to BREAKTHROUGH if signal is strong, else LEADERSHIP_EXPANSION.
    if 7 in active_h and ca >= 0.55 and fn >= 0.5:
        if 10 in active_h or 11 in active_h:
            if ca >= 0.75 and scores["strength_product"] >= 0.60:
                return ("BREAKTHROUGH", sorted(active_h), near_miss)
            return ("LEADERSHIP_EXPANSION", sorted(active_h), near_miss)
        # H7 alone (without H10/H11) = JOB_CHANGE through partnership/referral
        if ca >= 0.45:
            return ("JOB_CHANGE", sorted(active_h), near_miss)

    # ── FOREIGN_POSTING ──────────────────────────────────────────────────────
    geo = career_ctx.get("geographic_preference", "open")
    rahu_flag  = any("RAHU" in f for f in flags)
    # Widened gate (audit fix): Saturn in H9/H12 transit also triggers foreign
    # to handle Saturn-MD periods with strong H12 dasha activation.
    saturn_h9_12_flag = any(
        ("SATURN_H9" in f or "SATURN_H12" in f or "SAT_TRANSIT_ASPECT_H10_LORD" in f)
        for f in flags
    )
    if ({9, 12} & active_h and ca >= 0.5 and geo != "domestic"
            and (rahu_flag or "JUPITER_H9_EXPANSION" in flags
                 or saturn_h9_12_flag or "JUP_TRANSIT_ASPECT_H10_LORD" in flags)):
        return ("FOREIGN_POSTING", sorted(active_h), near_miss)

    # ── G30: LATERAL_MOVE — checked BEFORE JOB_CHANGE so it takes precedence ──
    # G30 fires when H6/H12 + H10 are active but H1/H11 (growth) are absent,
    # which is the exact same house pattern that would trigger JOB_CHANGE below.
    # Without this ordering, JOB_CHANGE always fires first and G30 never lands.
    if "LATERAL_MOVE" in scores.get("event_hints", []):
        if ca >= 0.40 and fn >= 0.45:
            return ("LATERAL_MOVE", sorted(active_h), near_miss)

    # ── JOB_CHANGE ──────────────────────────────────────────────────────────
    if {6, 12} & active_h and ca >= 0.4 and fn >= 0.45:
        return ("JOB_CHANGE", sorted(active_h), near_miss)
    if status == "on_notice_period" and ca >= 0.4:
        return ("JOB_CHANGE", sorted(active_h), near_miss)

    # ── SALARY_HIKE ─────────────────────────────────────────────────────────
    if {11, 2} & active_h and ca >= 0.4:
        if _cooldown_inc:   # GAP 7: income-tier cooldown (6 months)
            return ("GROWTH", sorted(active_h), near_miss)
        return ("SALARY_HIKE", sorted(active_h), near_miss)

    # ── G28: ENTREPRENEURSHIP_WINDOW ─────────────────────────────────────────
    if "ENTREPRENEURSHIP_WINDOW" in scores.get("event_hints", []):
        if ca >= 0.45 and fn >= 0.45:
            return ("ENTREPRENEURSHIP_WINDOW", sorted(active_h), near_miss)

    # ── G29: EQUITY_EVENT ────────────────────────────────────────────────────
    if "EQUITY_EVENT" in scores.get("event_hints", []):
        if {2, 5, 11} & active_h and ca >= 0.50:
            return ("EQUITY_EVENT", sorted(active_h), near_miss)

    # ── SKILL_UPGRADE_PHASE ──────────────────────────────────────────────────
    _d24_active = scores.get("d24_skill_bonus", 0) > 0
    _skill_ca_thresh = 0.42 if _d24_active else 0.50
    if {5, 3} & active_h and ca < _skill_ca_thresh:
        return ("SKILL_UPGRADE_PHASE", sorted(active_h), near_miss)

    # ── AUTHORITY_SHIFT ──────────────────────────────────────────────────────
    if 10 in active_h and 8 in active_h:
        return ("AUTHORITY_SHIFT", sorted(active_h), near_miss)

    # ── GROWTH (general positive period) ─────────────────────────────────────
    if score >= 0.55 and fn >= 0.5:
        # Phase 0 intent-tag tiebreaker: in the ambiguous 0.55–0.68 band,
        # use career intent (from LLM context enrichment) to refine the event.
        # This prevents the same mid-score block from always resolving to GROWTH
        # regardless of whether the person wants leadership vs income vs learning.
        _tags = career_ctx.get("_intent_tags", [])
        if _tags and 0.55 <= score <= 0.68:
            if "leadership" in _tags and _gate_designation(desig, yoe, "senior") and 10 in active_h:
                return ("LEADERSHIP_EXPANSION", sorted(active_h), near_miss)
            if "income_maximisation" in _tags and {11, 2} & active_h:
                return ("SALARY_HIKE", sorted(active_h), near_miss)
            if "skill_upgrade" in _tags and {3, 5} & active_h:
                return ("SKILL_UPGRADE_PHASE", sorted(active_h), near_miss)
            if "career_transition" in _tags and {6, 12} & active_h:
                return ("JOB_CHANGE", sorted(active_h), near_miss)
            if "entrepreneurship" in _tags and {1, 3} & active_h:
                return ("ENTREPRENEURSHIP_WINDOW", sorted(active_h), near_miss)
        return ("GROWTH", sorted(active_h), near_miss)

    # ── G-A8: CAREER_PLATEAU ─────────────────────────────────────────────────
    # Low-moderate score, some FN negativity but not adverse enough for RISK_PERIOD.
    # No active growth houses; no particular stress. Classic plateau: employed but stuck.
    if fn < 0.45 and 0.35 <= score < 0.52 and not adverse_flags:
        if not (active_h & {2, 10, 11, 6, 12}):   # no career house activation
            return ("CAREER_PLATEAU", sorted(active_h), near_miss)

    # ── G-A9: STAGNATION ─────────────────────────────────────────────────────
    # Very low score, negative functional nature, no events firing — genuine stagnation.
    if fn < 0.35 and score < 0.38 and not adverse_flags:
        return ("STAGNATION", sorted(active_h), near_miss)

    # ── STABILITY (default) ───────────────────────────────────────────────────
    return ("STABILITY", sorted(active_h), near_miss)


def _gate_designation(desig: str, yoe: Optional[int], min_desig: str) -> bool:
    """True if designation meets or exceeds min_desig, or if designation unknown."""
    if not desig:
        return True   # unknown — don't gate
    try:
        return _DESIGNATION_LEVELS.index(desig) >= _DESIGNATION_LEVELS.index(min_desig)
    except ValueError:
        return True


def _exp_ok(yoe: Optional[int], desig: str) -> bool:
    """True if experience meets the minimum for the current designation."""
    if yoe is None or not desig:
        return True
    min_exp = _DESIGNATION_MIN_EXP.get(desig, 0)
    return yoe >= min_exp


# ═════════════════════════════════════════════════════════════════════════════
# STEP 6 — Retroactive validation
# ═════════════════════════════════════════════════════════════════════════════

_EVENT_TYPE_GROUPS: Dict[str, set] = {
    "join_date":           {"JOB_CHANGE", "RE_ENTRY", "TRANSITION", "LATERAL_MOVE", "FIRST_JOB"},
    # Widened (2026-07): a real historical promotion can land in a period the
    # deterministic classifier labeled AUTHORITY_SHIFT or CAREER_TRANSITION —
    # both are promotion-adjacent outcomes in this taxonomy (see
    # _DESIGNATION_EVENT_BIAS / _EVENT_NARRATIVE) — restricting this set to
    # only the 3 "purest" labels caused real, date-correct promotions to
    # never register a retro-match when the classifier's contemporaneous
    # label was a plausible-but-not-identical neighbor.
    "last_promotion_date": {"PROMOTION", "LEADERSHIP_EXPANSION", "BREAKTHROUGH", "AUTHORITY_SHIFT", "CAREER_TRANSITION"},
    "last_hike_date":      {"SALARY_HIKE", "INCOME_INFLECTION", "GROWTH", "EQUITY_EVENT"},
    # career_events[] list uses these mappings:
    "PROMOTION":           {"PROMOTION", "BREAKTHROUGH", "LEADERSHIP_EXPANSION", "AUTHORITY_SHIFT"},
    "JOB_CHANGE":          {"JOB_CHANGE", "TRANSITION", "FOREIGN_POSTING", "RE_ENTRY", "LATERAL_MOVE"},
    "SALARY_HIKE":         {"SALARY_HIKE", "INCOME_INFLECTION", "GROWTH"},
    "FOREIGN_POSTING":     {"FOREIGN_POSTING", "JOB_CHANGE"},
    "FIRST_JOB":           {"FIRST_JOB", "TRANSITION"},
    "TRANSITION":          {"TRANSITION", "JOB_CHANGE", "RE_ENTRY", "SANDHI_PERIOD"},
    "BREAKTHROUGH":        {"BREAKTHROUGH", "PROMOTION"},
    "INCOME_INFLECTION":   {"INCOME_INFLECTION", "SALARY_HIKE", "GROWTH", "EQUITY_EVENT"},
    "ENTREPRENEURSHIP_WINDOW": {"ENTREPRENEURSHIP_WINDOW", "JOB_CHANGE", "BREAKTHROUGH"},
    "EQUITY_EVENT":        {"EQUITY_EVENT", "INCOME_INFLECTION"},
    "LATERAL_MOVE":        {"LATERAL_MOVE", "JOB_CHANGE"},
    "SANDHI_PERIOD":       {"SANDHI_PERIOD", "STABILITY"},
    # ── Adverse-event categories (job-loss framework G10 retro-validation) ────
    # Let declared past layoffs / forced exits / burnout breaks / restructures
    # be matched against the adverse events the engine now predicts.
    "JOB_LOSS":            {"JOB_LOSS", "FORCED_EXIT", "BURNOUT_EXIT", "RISK_PERIOD"},
    "LAYOFF":              {"JOB_LOSS", "FORCED_EXIT", "RISK_PERIOD"},
    "FORCED_EXIT":         {"FORCED_EXIT", "JOB_LOSS", "JOB_CHANGE", "RISK_PERIOD"},
    "BURNOUT_EXIT":        {"BURNOUT_EXIT", "JOB_LOSS", "RISK_PERIOD", "SANDHI_PERIOD"},
    "BURNOUT":             {"BURNOUT_EXIT", "JOB_LOSS", "RISK_PERIOD"},
    "ROLE_RESTRUCTURING":  {"ROLE_RESTRUCTURING", "AUTHORITY_SHIFT", "LATERAL_MOVE", "JOB_CHANGE"},
    "RESTRUCTURING":       {"ROLE_RESTRUCTURING", "AUTHORITY_SHIFT", "JOB_CHANGE"},
    "SABBATICAL":          {"RISK_PERIOD", "SANDHI_PERIOD", "BURNOUT_EXIT"},
    "MANAGER_CONFLICT":    {"RISK_PERIOD", "ROLE_RESTRUCTURING", "JOB_CHANGE"},
}


def _has_known_past_events(career_ctx: Dict[str, Any]) -> bool:
    """True if career_ctx carries ANY source of real past-event data.

    Bug fix (2026-07-08, user-reported): the two call sites below previously
    checked ONLY `career_ctx.get("known_events")` to decide
    `known_events_present` for job_loss.py's jobloss_confirmation_ledger()
    (which gates whether "retro_validated" is even considered as the 7th
    confirmation layer). But `_retroactive_validate()` (this module, a few
    lines below) actually matches past events from THREE independent
    sources: the legacy join_date/last_promotion_date/last_hike_date trio,
    the typed career_events[] list, AND known_events[]. A chart supplying
    only the legacy fields (the most common real-world case — most callers
    still pass last_promotion_date alone, not the newer known_events
    schema) silently reported "no past events provided" / never engaged the
    retro-validation confirmation layer, even though _retroactive_validate()
    itself was correctly matching those legacy dates against predicted
    windows the whole time. This helper mirrors _retroactive_validate()'s
    own source list so "were any real past events supplied" and "were any
    real past events actually usable for matching" always agree.
    """
    if career_ctx.get("known_events"):
        return True
    if career_ctx.get("career_events"):
        return True
    for _legacy_field in ("join_date", "last_promotion_date", "last_hike_date"):
        if career_ctx.get(_legacy_field):
            return True
    return False


def _retroactive_validate(
    periods: List[Dict],
    career_ctx: Dict[str, Any],
) -> int:
    """Compare actual career events to predicted transition windows.

    Returns count of matches.
    Sources of truth:
      1. Legacy 3-field check: join_date, last_promotion_date, last_hike_date
      2. career_events[]: list of {date, event_type} dicts for full history
    Each match: actual event date falls within ±90 days of a period with
    the corresponding event type.
    """
    matched_period_ids: set = set()
    matches = 0

    def _check_actual(actual_d: date, valid_types: set, label: str = "") -> bool:
        nonlocal matches
        for p in periods:
            pid = id(p)
            if pid in matched_period_ids:
                continue
            # Bug fix (2026-07): event_type can carry a "FORECAST_" prefix
            # (set at line ~3797 when mode=="forecast") — every OTHER
            # consumer of event_type in this file strips this prefix before
            # comparing (see the .replace("FORECAST_", "") pattern used at
            # lines ~1750, 3335, 3969, 4054, 4166, 4316), but this retro-match
            # check compared the raw string directly, so a period genuinely
            # classified as "PROMOTION" but tagged "FORECAST_PROMOTION" could
            # never match valid_types={"PROMOTION",...} — this was very
            # likely why real promotion/join dates that landed inside a
            # forecast-mode period never registered a match at all.
            _p_event_type = (p.get("event_type") or "").replace("FORECAST_", "")
            if _p_event_type not in valid_types:
                continue
            _sd = p["start_date"]
            _ed = p["end_date"]
            if isinstance(_sd, str):
                _sd = parse_iso_date(_sd) or actual_d
            if isinstance(_ed, str):
                _ed = parse_iso_date(_ed) or actual_d
            # Bug fix (2026-07): matching was midpoint-only (±90 days from the
            # period's midpoint), which silently fails for wide AD-level
            # periods — e.g. a ~32-month Jupiter-Venus AD block has its
            # midpoint over a year away from an event that happened early or
            # late in that same period (a real promotion on 2024-01-15 inside
            # a 2023-08-13..2026-04-13 AD window is ~13 months from the
            # midpoint, well outside ±90 days, so it never matched despite
            # genuinely falling inside the period). A date that falls inside
            # the period's own [start_date, end_date) range is a real match
            # regardless of distance from the midpoint; the ±90-day midpoint
            # check is kept as a secondary allowance for near-miss dates that
            # fall just outside a period's boundary (e.g. a PD-level event
            # dated a few weeks before/after its actual sub-period).
            mid = _sd + (_ed - _sd) / 2
            _within_range = _sd <= actual_d < _ed
            _near_midpoint = abs((actual_d - mid).days) <= _RETRO_MATCH_DAYS
            if _within_range or _near_midpoint:
                matched_period_ids.add(pid)
                matches += 1
                # User-reported gap fix (2026-07): attach match detail onto the
                # period itself so the report can show WHICH real event
                # matched WHICH predicted window, instead of only a bare
                # count feeding a "Validated against N past events" badge —
                # that count was real (date-based, ±90-day window match, not
                # score-based as claimed), but not previously visible.
                p["retro_matched_event"] = {
                    "date": actual_d.isoformat(), "label": label or "career event",
                }
                return True
        return False

    # 1. Legacy 3-field check
    legacy_pairs = [
        ("join_date",           _EVENT_TYPE_GROUPS["join_date"],           "Join date"),
        ("last_promotion_date", _EVENT_TYPE_GROUPS["last_promotion_date"], "Promotion"),
        ("last_hike_date",      _EVENT_TYPE_GROUPS["last_hike_date"],      "Salary hike"),
    ]
    for field, valid_types, label in legacy_pairs:
        actual_d = parse_iso_date(career_ctx.get(field, ""))
        if actual_d:
            _check_actual(actual_d, valid_types, label)

    # 2. Full career_events[] list (typed: {date, event_type})
    for evt in (career_ctx.get("career_events") or []):
        if not isinstance(evt, dict):
            continue
        actual_d = parse_iso_date(evt.get("date", ""))
        evt_type = (evt.get("event_type") or "").upper()
        if not actual_d or not evt_type:
            continue
        valid_types = _EVENT_TYPE_GROUPS.get(evt_type, {evt_type})
        _check_actual(actual_d, valid_types, evt_type.replace("_", " ").title())

    # 3. User-reported gap fix (2026-07): "known_events" — free-text life
    # events ({date, event} description strings, matching the schema the
    # user requested) without a formal event_type. Since these can't be
    # type-matched against _EVENT_TYPE_GROUPS, match against ANY period
    # whose date range contains the event date (not just its midpoint
    # window) — a looser but still genuinely date-based check, better than
    # not validating free-text events at all.
    for evt in (career_ctx.get("known_events") or []):
        if not isinstance(evt, dict):
            continue
        actual_d = parse_iso_date(evt.get("date", ""))
        desc = str(evt.get("event", "") or evt.get("description", "")).strip()
        if not actual_d or not desc:
            continue
        for p in periods:
            pid = id(p)
            if pid in matched_period_ids:
                continue
            _sd = p["start_date"]
            _ed = p["end_date"]
            if isinstance(_sd, str):
                _sd = parse_iso_date(_sd) or actual_d
            if isinstance(_ed, str):
                _ed = parse_iso_date(_ed) or actual_d
            if _sd and _ed and _sd <= actual_d <= _ed:
                matched_period_ids.add(pid)
                matches += 1
                p["retro_matched_event"] = {"date": actual_d.isoformat(), "label": desc}
                break

    return matches


# ═════════════════════════════════════════════════════════════════════════════
# STEP 7 — Desired-outcome reorder
# ═════════════════════════════════════════════════════════════════════════════

_OUTCOME_EVENT_PRIORITY: Dict[str, List[str]] = {
    "promotion":      ["PROMOTION","BREAKTHROUGH","LEADERSHIP_EXPANSION","GROWTH"],
    "job_change":     ["JOB_CHANGE","TRANSITION","FOREIGN_POSTING","GROWTH"],
    "salary_hike":    ["INCOME_INFLECTION","SALARY_HIKE","GROWTH","PROMOTION"],
    "foreign_posting":["FOREIGN_POSTING","JOB_CHANGE","BREAKTHROUGH","GROWTH"],
    "leadership_role":["LEADERSHIP_EXPANSION","BREAKTHROUGH","PROMOTION","GROWTH"],
    "stability":      ["STABILITY","GROWTH","SKILL_UPGRADE_PHASE","CONSOLIDATION"],
    "return_after_gap":["RE_ENTRY","TRANSITION","JOB_CHANGE","GROWTH"],
    "first_job":       ["FIRST_JOB","TRANSITION","GROWTH","STABILITY"],
}

# B1 fix: Separate stricter filter for the goal-sentence (s5) injection.
# _OUTCOME_EVENT_PRIORITY above keeps BREAKTHROUGH/GROWTH for sorting purposes
# (_mark_primary_opportunities), but those generic types must NOT trigger the
# "Prioritise X to align with your 'promotion' goal" sentence on every block.
# Only event types that are genuinely aligned with the stated goal fire s5.
_OUTCOME_GOAL_SENTENCE_FILTER: Dict[str, List[str]] = {
    "promotion":       ["PROMOTION", "LEADERSHIP_EXPANSION"],
    "job_change":      ["JOB_CHANGE", "TRANSITION"],
    "salary_hike":     ["INCOME_INFLECTION", "SALARY_HIKE"],
    "foreign_posting": ["FOREIGN_POSTING"],
    "leadership_role": ["LEADERSHIP_EXPANSION", "PROMOTION"],
    "stability":       ["STABILITY", "CONSOLIDATION"],
    "return_after_gap":["RE_ENTRY", "TRANSITION"],
    "first_job":       ["FIRST_JOB"],
}

def _mark_primary_opportunities(periods: List[Dict], desired_outcome: str) -> None:
    """G3 fix: Flag exactly ONE block as the primary opportunity.

    Original design flagged ALL blocks whose event_type matched desired_outcome,
    leaving the deduplication to the HTML renderer — architecturally wrong.

    Rules:
      1. Only non-past blocks are eligible (future > current > past fallback).
      2. Among eligible blocks, pick the one with the highest career_score.
      3. If desired_outcome is unset, pick the globally highest-scoring non-past block.
      4. Exactly one block gets is_primary_opportunity=True; all others get False.
    """
    # Clear all flags first
    for p in periods:
        p["is_primary_opportunity"] = False

    priority = _OUTCOME_EVENT_PRIORITY.get(desired_outcome, [])
    non_past = [p for p in periods if not p.get("is_past", False)]
    pool = non_past if non_past else periods  # fall back to past if all blocks are past

    # Prefer blocks matching the desired outcome
    if priority:
        matching = [p for p in pool if p.get("event_type", "") in priority]
        candidates = matching if matching else pool
    else:
        candidates = pool

    if not candidates:
        return

    best = max(candidates, key=lambda p: p.get("career_score", 0))
    best["is_primary_opportunity"] = True


# ═════════════════════════════════════════════════════════════════════════════
# PERIOD HELPER DERIVATIONS
# ═════════════════════════════════════════════════════════════════════════════

# ── Planet × Industry Skill Recommendations (GAP 3) ─────────────────────
# Maps (planet, industry_sector) → list of 3 targeted skill recommendations.
# Industry keys are lowercase and match career_ctx["industry_sector"].
_PLANET_INDUSTRY_SKILLS: Dict[str, Dict[str, List[str]]] = {
    "Mercury": {
        "technology":   ["Machine learning & MLOps", "System design at scale", "Data engineering pipelines"],
        "finance":      ["Quantitative modelling", "Regulatory technology (RegTech)", "Algorithmic risk frameworks"],
        "healthcare":   ["Health informatics & HL7/FHIR", "Clinical decision support systems", "Medical data privacy (HIPAA/GDPR)"],
        "consulting":   ["Strategic narrative frameworks", "Executive data storytelling", "Scenario planning methodologies"],
        "_default":     ["Analytical communication", "Structured problem-solving", "Data-driven decision frameworks"],
    },
    "Mars": {
        "technology":   ["Cloud infrastructure & IaC (Terraform)", "Cybersecurity & threat modelling", "High-performance backend systems"],
        "finance":      ["Trading systems & low-latency architecture", "Risk operations", "Derivatives execution"],
        "healthcare":   ["Medical device engineering", "Surgical robotics & embedded systems", "Emergency operations management"],
        "consulting":   ["Rapid prototyping & lean delivery", "Operational turnaround", "Change management execution"],
        "_default":     ["Project execution excellence", "Operational risk management", "Delivery leadership"],
    },
    "Venus": {
        "technology":   ["Product management & UX strategy", "Design systems & frontend architecture", "Growth & conversion optimisation"],
        "finance":      ["Client relationship management", "Wealth advisory & ESG investing", "Financial product design"],
        "healthcare":   ["Patient experience design", "Healthcare CX & digital engagement", "Brand strategy for health systems"],
        "consulting":   ["Client engagement & trust-building", "Human-centred design thinking", "Executive stakeholder influence"],
        "_default":     ["Stakeholder management", "Brand & communications strategy", "Relationship-led growth"],
    },
    "Jupiter": {
        "technology":   ["Enterprise architecture & platform thinking", "AI/ML strategy & governance", "CTO/CPO leadership frameworks"],
        "finance":      ["Portfolio strategy & capital allocation", "ESG & sustainable investing frameworks", "Board-level financial advisory"],
        "healthcare":   ["Healthcare policy & system design", "Population health management", "Medical leadership & ethics"],
        "consulting":   ["Management consulting methodology", "Corporate strategy & M&A", "Executive coaching certification"],
        "_default":     ["Strategic thinking & business acumen", "Leadership philosophy & team-building", "Advisory and mentorship frameworks"],
    },
    "Saturn": {
        "technology":   ["Site reliability engineering (SRE)", "Compliance automation & security posture", "Legacy modernisation & tech debt reduction"],
        "finance":      ["Regulatory compliance (Basel, SOX)", "Audit & internal controls", "Process automation & efficiency"],
        "healthcare":   ["Clinical governance & accreditation", "Healthcare compliance & HIPAA auditing", "Operational excellence in care delivery"],
        "consulting":   ["Process improvement (Lean, Six Sigma)", "Governance & accountability frameworks", "Large-scale programme management"],
        "_default":     ["Operational discipline & SOP documentation", "Governance frameworks", "Structured programme delivery"],
    },
    "Rahu": {
        "technology":   ["Generative AI & LLM productisation", "Web3 & decentralised systems", "Cross-border tech scaling & localisation"],
        "finance":      ["Fintech & embedded finance", "Crypto-asset risk management", "Alternative investments & frontier markets"],
        "healthcare":   ["Digital health & telemedicine", "AI-assisted diagnostics", "Global health & cross-border clinical trials"],
        "consulting":   ["Digital transformation advisory", "Emerging market strategy", "Disruptive innovation facilitation"],
        "_default":     ["Emerging technology adoption", "Cross-cultural leadership", "Innovation & intrapreneurship"],
    },
    "Sun": {
        "technology":   ["Engineering leadership & people management", "Public speaking & technical advocacy", "Building high-performance engineering culture"],
        "finance":      ["Executive financial leadership", "Investor relations & board communication", "C-suite financial strategy"],
        "healthcare":   ["Clinical leadership & CMO pathway", "Healthcare executive communications", "Institutional credibility-building"],
        "consulting":   ["Thought leadership & publishing", "C-suite advisory relationships", "Practice leadership & business development"],
        "_default":     ["Executive presence & influence", "Visible ownership of strategic outcomes", "Public-facing leadership"],
    },
    "Moon": {
        "technology":   ["Engineering culture & psychological safety", "Agile facilitation & team dynamics", "Employee experience & retention strategy"],
        "finance":      ["Client psychology & advisory empathy", "Team motivation & performance culture", "Crisis communication & soft skills"],
        "healthcare":   ["Bedside manner & patient-centred care", "Interdisciplinary team coordination", "Mental health & wellbeing in clinical settings"],
        "consulting":   ["Facilitation & workshop design", "Active listening & client trust", "Change management & adoption"],
        "_default":     ["Emotional intelligence & team leadership", "Communication & active listening", "Conflict resolution & mediation"],
    },
    "Ketu": {
        "technology":   ["Deep specialisation in AI safety or cryptography", "Open-source contribution & technical reputation", "Research engineering & publications"],
        "finance":      ["Quantitative research & factor investing", "Niche regulatory expertise", "Financial forensics & complex modelling"],
        "healthcare":   ["Sub-specialty clinical expertise", "Rare disease research", "Academic medicine & clinical trials"],
        "consulting":   ["Subject matter expert positioning", "Niche industry specialisation", "Research-led consulting methodology"],
        "_default":     ["Deep domain expertise", "Research & intellectual rigour", "Specialist niche positioning"],
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# RECONSTRUCTION NOTE (2026-07-07): _build_narrative_hint() and
# _build_md_narrative() (below _get_skill_recommendation) were found called
# from multiple sites in this file and in jyotish/web_report.py, but with NO
# definition anywhere in the repository — the same "corruption pattern"
# documented at several other reconstruction points this session (see
# jyotish/web_report.py's generate_career_timeline_report() note for the
# fullest account). No readable bytecode cache exists for either symbol.
# These are clean-room reconstructions built strictly from: (a) each
# function's exact call-site signature (parameter names/order confirmed by
# reading every call site in timeline.py and web_report.py), and (b) the
# ALREADY-EXISTING text banks in this same module (_EVENT_NARRATIVE,
# _MD_THEMES, _MD_CAREER_KEYWORDS, _JAIMINI_ROLE) — composing sentences from
# vocabulary this codebase already committed to, not inventing new
# astrological doctrine or wording conventions.
# ═════════════════════════════════════════════════════════════════════════════

def _build_narrative_hint(
    event_type: str, md_lord: str, ad_lord: str, flags: List[str], career_score: float,
    kp_cusp_score: float = 0.0, jaimini_score: float = 0.0, jaimini_role: str = "",
    career_ctx: Optional[Dict[str, Any]] = None, d9_digs: Optional[Dict[str, str]] = None,
    planet_sign: Optional[Dict[str, str]] = None, lagna_sign: str = "",
) -> str:
    """Build the 4-5 sentence Antardasha-level narrative hint for one period
    block. Composes from the existing _EVENT_NARRATIVE / _MD_THEMES /
    _MD_CAREER_KEYWORDS text banks (already defined above in this module) —
    this function's job is assembly/selection, not inventing new sentences
    from nothing.
    """
    _et = (event_type or "").replace("FORECAST_", "").upper()
    sentences: List[str] = []

    # 1. Core event-type sentence (existing text bank).
    _event_sentence = _EVENT_NARRATIVE.get(_et, "")
    if _event_sentence:
        sentences.append(_event_sentence)

    # 2. MD lord theme sentence.
    _md_theme = _MD_THEMES.get(md_lord, "")
    if _md_theme:
        sentences.append(f"The {md_lord} Mahadasha brings {_md_theme}.")

    # 3. AD lord practical keyword sentence (what to focus on this sub-period).
    _ad_keywords = _MD_CAREER_KEYWORDS.get(ad_lord, [])
    if _ad_keywords:
        sentences.append(
            f"The {ad_lord} Antardasha favours: " + ", ".join(_ad_keywords[:3]) + "."
        )

    # 4. KP/Jaimini corroboration sentence, only when genuinely informative.
    if kp_cusp_score and kp_cusp_score >= 0.4:
        sentences.append(
            f"KP cuspal alignment for this period is supportive (score {kp_cusp_score:.2f})."
        )
    if jaimini_role:
        sentences.append(jaimini_role)

    # 5. Any high-signal transit flag, plainly stated (not astrologically
    # re-derived — flags are already computed upstream by _get_dynamic_transits).
    _notable_flags = [f for f in (flags or []) if any(
        k in f for k in ("EXPANSION", "AUTHORITY", "OPPORTUNITY", "STRESS", "BURDEN", "DISRUPTION")
    )]
    if _notable_flags:
        sentences.append("Active transit signal(s): " + ", ".join(_notable_flags[:2]) + ".")

    if not sentences:
        sentences.append(
            f"The {md_lord}-{ad_lord} period shows a career score of {career_score:.2f}; "
            "no single dominant astrological driver stands out — outcomes depend on "
            "effort and external timing more than a strong planetary push."
        )

    return " ".join(sentences)


def _build_md_narrative(
    md_lord: str, start_str: str, end_str: str, payload: Any, lagna_sign: str = "",
    career_ctx: Optional[Dict[str, Any]] = None, jaimini_role: str = "",
    kp_cusp_score: float = 0.0, ad_event_summary: str = "",
) -> str:
    """Build the 3-paragraph Mahadasha-level narrative summary shown at the
    top of each MD's first block / each roadmap year-card. Same
    "assemble from existing text banks" approach as _build_narrative_hint()
    above (_MD_THEMES / _MD_CAREER_KEYWORDS / _JAIMINI_ROLE), not new
    astrological doctrine.
    """
    _theme = _MD_THEMES.get(md_lord, "career development")
    _keywords = _MD_CAREER_KEYWORDS.get(md_lord, [])

    para1 = (
        f"The {md_lord} Mahadasha ({start_str} to {end_str}) introduces {_theme} "
        f"as the dominant career theme for this multi-year period."
    )
    if lagna_sign:
        para1 += f" For the {lagna_sign} Lagna, {md_lord}'s career-related significations play out against that ascendant's own natural strengths and constraints."

    para2 = ""
    if _keywords:
        para2 = (
            f"The natural domains activated during a {md_lord} period include: "
            + ", ".join(_keywords) + " — these themes will recur across every Antardasha within this Mahadasha, "
            "even as the specific event type shifts sub-period to sub-period."
        )

    para3_parts = []
    if jaimini_role:
        para3_parts.append(jaimini_role)
    if kp_cusp_score:
        _kp_word = "strongly" if kp_cusp_score >= 0.6 else ("moderately" if kp_cusp_score >= 0.35 else "weakly")
        para3_parts.append(f"KP cuspal analysis ties this Mahadasha lord {_kp_word} to the core career houses (score {kp_cusp_score:.2f}).")
    if ad_event_summary:
        para3_parts.append(f"Across its sub-periods, this Mahadasha's dominant signals include: {ad_event_summary}.")
    para3 = " ".join(para3_parts)

    return " ".join(p for p in (para1, para2, para3) if p)


def _get_skill_recommendation(ad_lord: str, industry_sector: str) -> List[str]:
    """Return 3 targeted skill recommendations for this planet × industry combination."""
    planet_map = _PLANET_INDUSTRY_SKILLS.get(ad_lord, {})
    sector_key = (industry_sector or "").lower().replace(" ", "_").replace("-", "_")
    # Try exact match, then prefix match, then default
    skills = (
        planet_map.get(sector_key)
        or next((v for k, v in planet_map.items() if sector_key.startswith(k[:4]) and k != "_default"), None)
        or planet_map.get("_default", [])
    )
    return skills[:3]


# Planet → professional domain label
_PLANET_DOMAIN: Dict[str, str] = {
    "Sun":     "Leadership & Administration",
    "Moon":    "People & Creative",
    "Mars":    "Engineering & Execution",
    "Mercury": "Technology & Communication",
    "Jupiter": "Strategy & Advisory",
    "Venus":   "Design, Finance & Relationships",
    "Saturn":  "Operations & Governance",
    "Rahu":    "Innovation & Cross-Border",
    "Ketu":    "Research & Specialisation",
}

def _derive_domain_tag(
    md_lord: str,
    ad_lord: str,
    active_houses: list,
    career_ctx: Dict[str, Any],
) -> str:
    """Return a short domain label for this AD period.

    Blends the MD/AD planetary domains with the industry sector from career_ctx
    to produce a human-readable tag for the HTML report.
    """
    sector = (career_ctx.get("industry_sector") or "").lower()
    md_domain = _PLANET_DOMAIN.get(md_lord, "General")
    ad_domain = _PLANET_DOMAIN.get(ad_lord, "General")

    # House-based overrides
    h_set = set(active_houses) if active_houses else set()
    if 10 in h_set and 11 in h_set:
        base = "Authority & Growth"
    elif 6 in h_set and 10 in h_set:
        base = "Service & Leadership"
    elif 2 in h_set and 11 in h_set:
        base = "Income & Expansion"
    elif 9 in h_set or 12 in h_set:
        base = "Global & Advisory"
    else:
        # Blend MD and AD domains; if same, just return one
        base = ad_domain if md_domain == ad_domain else f"{ad_domain}"

    # Prepend sector for colour
    if sector and sector not in ("other", "general"):
        sector_cap = sector.replace("_", " ").title()
        return f"{sector_cap} — {base}"
    return base


# Phase 3 (2026-07-05, item #18): for a senior professional, "PROMOTION"
# rarely means a first-rung title bump — it manifests as scope/authority
# changes that a generic label doesn't capture. Threshold matches the
# `_DESIGNATION_MIN_EXP` "director" tier already used elsewhere in this file,
# so it's consistent with the engine's existing seniority notion rather than
# inventing a new one.
_SENIOR_EXPERIENCE_YEARS = 20
_SENIOR_EVENT_FRAMING: Dict[str, str] = {
    "PROMOTION": ("At this experience level, \"promotion\" more plausibly reads as portfolio "
                  "expansion, practice leadership, global stakeholder influence, a title "
                  "correction, or delivery/P&L ownership — not a first-rung title bump."),
    "LEADERSHIP_EXPANSION": ("At this experience level, this more plausibly reads as broader "
                             "organizational scope or cross-functional authority, not a step "
                             "up the individual-contributor ladder."),
    "JOB_CHANGE": ("At this experience level, a job change more plausibly reads as a lateral "
                  "strategic move or an advisory/board-level transition, not an entry- or "
                  "mid-level role switch."),
    "INCOME_INFLECTION": ("At this experience level, income movement more plausibly comes "
                          "through compensation renegotiation or equity/incentive "
                          "restructuring, not a standard annual increment."),
}


def _derive_stage_domain_framing(
    event_type: str, md_lord: str, ad_lord: str, career_ctx: Dict[str, Any],
    chart: Any = None, sub_scores: Optional[Dict] = None,
) -> str:
    """Return an optional one/two-sentence framing note that translates a
    generic event label through (a) career seniority and (b) industry domain.
    Both pieces are general/chart-agnostic — seniority framing keys off
    years_experience (any chart), domain framing reuses the existing
    `_PLANET_INDUSTRY_SKILLS`/`_PLANET_DOMAIN` tables (already covering
    technology/finance/healthcare/consulting + a generic default for any
    other sector) rather than inventing chart-specific text. Returns ""
    when neither applies, so most charts/periods are unaffected.

    User-reported gap fix (2026-07): a flat single-planet domain label
    ("Jupiter = Strategy & Advisory") was too generic for a senior technical
    career — it didn't distinguish someone whose chart specifically shows
    Lagna-lord/10th-lord exchange (architecture/advisory bridge), an exalted
    Amatyakaraka (executive visibility), a D10 12th-house stellium (global-
    delivery/MNC exposure), or Rahu influence (AI/automation/emerging tech).
    `payload`/`sub_scores` are optional so existing callers without them are
    unaffected — when present, this layers 0-2 extra structural sentences
    onto the existing planet/industry framing, built entirely from already-
    computed general facts (parivartana_pairs, amk_exalted_bonus,
    d10_h12_stellium, d10_lagna_career_theme), not chart-specific text."""
    base = event_type.replace("FORECAST_", "")
    parts: List[str] = []

    yoe = career_ctx.get("years_experience", 0) or 0
    try:
        yoe = float(yoe)
    except (TypeError, ValueError):
        yoe = 0
    if yoe >= _SENIOR_EXPERIENCE_YEARS and base in _SENIOR_EVENT_FRAMING:
        parts.append(_SENIOR_EVENT_FRAMING[base])

    sector = career_ctx.get("industry_sector", "") or ""
    domain_lbl = _PLANET_DOMAIN.get(ad_lord, "")
    _skills = _get_skill_recommendation(ad_lord, sector)
    if domain_lbl and _skills and base in (
        "PROMOTION", "LEADERSHIP_EXPANSION", "SALARY_HIKE", "INCOME_INFLECTION", "JOB_CHANGE",
    ):
        _sector_lbl = sector.replace("_", " ").title() if sector else "this field"
        parts.append(
            f"Domain lens ({_sector_lbl}): {ad_lord} here points toward {domain_lbl.lower()} — "
            f"concretely, {_skills[0].lower()}."
        )

    if chart is not None:
        _hl_dsf = getattr(chart, "house_lords", {}) or {}
        _ph_dsf = getattr(chart, "planet_house", {}) or {}
        _lagna_lord = _hl_dsf.get("1", "")
        _h10_lord   = _hl_dsf.get("10", "")
        # Self-contained Parivartana (mutual exchange) check: lagna lord and
        # 10th lord are different planets, and each sits in the other's house
        # — the classical "identity and career are directly bridged" yoga.
        # Derived from house_lords/planet_house already on `chart`, no
        # separate payload-level parivartana_pairs dependency needed.
        _exchange = bool(
            _lagna_lord and _h10_lord and _lagna_lord != _h10_lord
            and _ph_dsf.get(_lagna_lord, 0) == 10 and _ph_dsf.get(_h10_lord, 0) == 1
        )
        if _exchange and ad_lord in (_lagna_lord, _h10_lord):
            parts.append(
                f"Structural note: Lagna lord ({_lagna_lord}) and 10th lord ({_h10_lord}) are in "
                f"exchange — identity and career are directly bridged, favoring architecture/advisory/"
                f"consulting-leadership roles over a purely execution-only track."
            )
        _sub = sub_scores or {}
        if _sub.get("amk_exalted_bonus", 0.0) and _sub.get("amk_exalted_bonus", 0.0) > 0.05:
            parts.append("Structural note: exalted Amatyakaraka actively running — favors executive visibility and senior stakeholder access, not just routine advancement.")
        if _sub.get("d10_h12_stellium"):
            parts.append("Structural note: D10 12th-house stellium — favors MNC/global-delivery/offshore-onsite matrix work, often behind-the-scenes rather than front-stage.")
        _d10_theme = _sub.get("d10_lagna_career_theme", "")
        if _d10_theme:
            parts.append(f"D10 Lagna theme: {_d10_theme}.")
        if ad_lord == "Rahu" or md_lord == "Rahu":
            parts.append("Rahu influence: favors AI/automation/emerging-technology and cross-border platform work over traditional linear advancement.")

    return " ".join(parts)


def _derive_career_track(career_ctx: Dict[str, Any]) -> str:
    """Return the user's operating career mode for timeline blocks."""
    status = (career_ctx.get("employment_status") or "").lower()
    emp_mode = (career_ctx.get("employment_mode") or "").lower()
    if status in {"self_employed", "business_owner", "freelancer"}:
        return "business"
    if emp_mode in {"self_employed", "freelance", "freelancer", "business", "business_owner"}:
        return "business"
    if career_ctx.get("is_family_business"):
        return "business"
    if status in {"employed", "on_notice_period"}:
        return "corporate"
    desig = (career_ctx.get("designation") or "").lower()
    mgmt_keywords = ("manager", "director", "vp", "svp", "head", "chief", "president",
                     "lead", "principal", "partner", "gm", "c-suite", "csuite")
    if any(kw in desig for kw in mgmt_keywords):
        return "management"
    return "IC"


def _derive_secondary_event_type(
    primary_event: str,
    career_track: str,
    career_ctx: Dict[str, Any],
    sub_scores: Optional[Dict[str, Any]] = None,
) -> str:
    """Return an optional secondary event label that adds nuance to the primary.

    For example, a PROMOTION in management track is specifically a TEAM_EXPANSION;
    a JOB_CHANGE with desired_outcome=stability is a LATERAL_MOVE.
    Returns empty string when no secondary is applicable.

    Phase 2 (2026-07-05, item #9/#12): `sub_scores` (the Phase-2 dimension
    split — promotion/job_change/income/visibility/risk/amk_exalted_bonus) is
    optional and chart-agnostic — these branches check general score patterns,
    not any specific planet/chart, so they apply uniformly across charts and
    fall through to the pre-existing labels unchanged when sub_scores is not
    supplied (backward compatible with any caller that doesn't pass it).
    """
    desired = (career_ctx.get("desired_outcome") or "").lower()
    ss = sub_scores or {}

    # ── Phase 2 general taxonomy additions (checked before the older,
    # coarser labels below so a strongly-signalled senior-career pattern
    # gets the sharper label instead of a generic one) ──────────────────────
    if primary_event in {"PROMOTION", "FORECAST_PROMOTION", "LEADERSHIP_EXPANSION",
                         "FORECAST_LEADERSHIP_EXPANSION"}:
        if ss.get("amk_exalted_bonus", 0.0) > 0.05:
            # An exalted Amatyakaraka actively running is specifically a
            # visible-authority event, not just a generic promotion.
            return "AUTHORITY_SHIFT"
        if ss.get("visibility_score", 0.0) >= 0.65 and ss.get("promotion_score", 0.0) < 0.55:
            # Visibility/recognition outrunning the formal promotion signal —
            # classic "title correction" pattern (recognition before title).
            return "TITLE_CORRECTION"
        if ss.get("visibility_score", 0.0) >= 0.60:
            return "STAKEHOLDER_VISIBILITY"
    if primary_event in {"JOB_CHANGE", "FORECAST_JOB_CHANGE"}:
        if ss.get("risk_score", 0.0) >= 0.55 and ss.get("job_change_score", 0.0) >= 0.5:
            return "ROLE_RESTRUCTURING"
    if ss.get("income_score", 0.0) >= 0.65 and ss.get("promotion_score", 0.0) < 0.55:
        # Strong income signal without a matching promotion signal — gains
        # come through negotiation/scope, not a title change.
        return "INCOME_NEGOTIATION"
    if ss.get("risk_score", 0.0) >= 0.70 and ss.get("stability_score", 0.0) < 0.35:
        return "WORKLOAD_SPIKE"

    if career_track == "business":
        if primary_event in {
            "PROMOTION", "FORECAST_PROMOTION",
            "LEADERSHIP_EXPANSION", "FORECAST_LEADERSHIP_EXPANSION",
            "BUSINESS_EXPANSION", "FORECAST_BUSINESS_EXPANSION",
            "BUSINESS_BREAKTHROUGH", "FORECAST_BUSINESS_BREAKTHROUGH",
        }:
            return "PARTNERSHIP_EXPANSION" if career_ctx.get("is_family_business") else "CLIENT_GAINS"
        if primary_event in {
            "INCOME_INFLECTION", "FORECAST_INCOME_INFLECTION",
            "REVENUE_GROWTH", "FORECAST_REVENUE_GROWTH",
        }:
            return "CLIENT_GAINS"
    if primary_event == "PROMOTION":
        if career_track == "management":
            return "TEAM_EXPANSION"
        if career_track == "corporate":
            return "PROMOTION"
        return "LEVEL_JUMP"
    if primary_event == "JOB_CHANGE":
        if desired in ("stability", "return_after_gap"):
            return "LATERAL_MOVE"
        return "ROLE_TRANSITION"
    if primary_event == "INCOME_INFLECTION":
        return "COMPENSATION_RESET"
    if primary_event == "LEADERSHIP_EXPANSION":
        return "SCOPE_BROADENING"
    if primary_event == "STABILITY":
        return "CONSOLIDATION_PHASE"
    return ""


# ═════════════════════════════════════════════════════════════════════════════
# MAIN PUBLIC FUNCTION
# ═════════════════════════════════════════════════════════════════════════════

def _adapt_event_for_career_track(event_type: str, career_track: str) -> str:
    """Translate salaried event labels into track-native labels."""
    if career_track != "business":
        return event_type
    return {
        "PROMOTION": "BUSINESS_EXPANSION",
        "LEADERSHIP_EXPANSION": "BUSINESS_EXPANSION",
        "BREAKTHROUGH": "BUSINESS_BREAKTHROUGH",
        "JOB_CHANGE": "CLIENT_PIPELINE_SHIFT",
        "LATERAL_MOVE": "MARKET_REPOSITIONING",
        "SALARY_HIKE": "REVENUE_GROWTH",
        "INCOME_INFLECTION": "REVENUE_GROWTH",
        "RE_ENTRY": "BUSINESS_REENTRY",
        "FIRST_JOB": "FIRST_CLIENT_WINDOW",
    }.get(event_type, event_type)


def compute_next_dasha_lookahead(dasha_sequence: List[Dict], dob: date,
                                  window_end: Optional[date],
                                  eff_strengths: Optional[Dict[str, float]] = None) -> Dict:
    """Gap fix (2026-07-05): the roadmap/timeline only ever covers the current
    Jupiter Mahadasha window (~1yr back + 4yr ahead) and never tells the reader
    what comes NEXT — a real gap since dasha transitions are the single biggest
    driver of career-trajectory change, and a naturally weak next MD lord
    (lowest Shadbala/eff_strength) is worth flagging in advance rather than
    only after the window has already ended.

    Returns a dict: {next_md_lord, next_md_start (iso), is_weakest_natal_planet,
    weakest_planet, note} — or {} if the sequence/dob is unusable. Purely
    additive/read-only: does not touch career_score or any existing scoring
    path (per the project's anti-circular-reference / no-reorder-only-fix
    conventions — this is new narrative surface, not a rescoring of anything)."""
    if not dasha_sequence or not dob or not window_end:
        return {}
    calendar = _dasha_calendar(dasha_sequence, dob)
    if not calendar:
        return {}
    # Distinct MD lords in chronological order, keyed by md_start
    _md_starts = sorted({
        (p.get("md_start"), p.get("md_lord"))
        for p in calendar
        if isinstance(p.get("md_start"), date) and p.get("md_lord")
    })
    if not _md_starts:
        return {}
    _next = None
    for _start, _lord in _md_starts:
        if _start > window_end:
            _next = (_start, _lord)
            break
    if _next is None:
        return {}
    _next_start, _next_lord = _next

    _weakest_planet = ""
    _is_weakest = False
    if eff_strengths:
        _natural_planets = {
            k: v for k, v in eff_strengths.items()
            if k in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")
            and isinstance(v, (int, float))
        }
        if _natural_planets:
            _weakest_planet = min(_natural_planets, key=lambda k: _natural_planets[k])
            _is_weakest = (_weakest_planet == _next_lord)

    note = f"Next Mahadasha lord after this window: {_next_lord} (from {_next_start.isoformat()})."
    if _is_weakest:
        note += (
            f" {_next_lord} is this chart's weakest planet by natural/effective "
            f"strength (Shadbala proxy) — worth flagging in advance, as the "
            f"upcoming period may run with reduced natural support until "
            f"remedial or compensatory factors are engaged."
        )
    return {
        "next_md_lord": _next_lord,
        "next_md_start": _next_start.isoformat(),
        "weakest_natal_planet": _weakest_planet,
        "next_lord_is_weakest": _is_weakest,
        "note": note,
    }


# RECONSTRUCTION NOTE (2026-07-07): _compute_workplace_friction() and
# _check_business_tension() (both called inside build_career_timeline()
# below) were found missing entirely — same corruption pattern documented
# at other reconstruction points this session. Both are informational-only
# (workplace_dynamics is read by llm_narrative_builder.py/view_model.py as
# a JSON-dumped dict / two flat fields respectively; business_tension is
# described at its own call site as "informational only" and its return
# value is discarded, i.e. it mutates `blocks` in place). Built from
# classical, chart-agnostic Vedic house-affliction rules already used
# elsewhere in this file (dusthana houses 6/8/12 for friction; the same
# _derive_career_track() classification already defined above for the
# tension check) — no new astrological doctrine invented.

def _compute_workplace_friction(flags: List[str], projected_transit_positions: Dict[str, int],
                                 chart: Any, lagna_sign: str) -> Dict[str, Any]:
    """Flag workplace-friction signals from already-computed transit flags
    plus projected malefic-transit house positions (Saturn/Rahu/Mars/Ketu),
    scored against the classical dusthana houses (6=conflict/competition,
    8=sudden disruption, 12=loss/isolation) and the natal 10th-lord's house.
    """
    friction_flags: List[str] = []
    house_lords = getattr(chart, "house_lords", {}) or {}
    planet_house = getattr(chart, "planet_house", {}) or {}
    h10_lord = house_lords.get("10", "")
    h10_lord_house = planet_house.get(h10_lord, 0) if h10_lord else 0

    _dusthana = {6, 8, 12}
    friction_score = 0.0
    for planet, proj_house in (projected_transit_positions or {}).items():
        if proj_house in _dusthana:
            friction_flags.append(f"{planet} transiting a dusthana house ({proj_house}) — elevated friction risk")
            friction_score += 0.15
        if h10_lord_house and proj_house == h10_lord_house:
            friction_flags.append(f"{planet} transiting the natal 10th-lord's house — workplace authority under pressure")
            friction_score += 0.20

    for f in (flags or []):
        if any(k in f for k in ("STRESS", "BURDEN", "DISRUPTION", "OBSTACLE")):
            friction_flags.append(f"Transit flag: {f}")
            friction_score += 0.10

    friction_score = round(min(1.0, friction_score), 3)
    return {
        "friction_flags": friction_flags,
        "friction_score": friction_score,
        "friction_level": ("high" if friction_score >= 0.5 else ("moderate" if friction_score >= 0.2 else "low")),
    }


def _check_business_tension(blocks: List[Dict], career_ctx: Dict[str, Any], lagna_sign: str) -> None:
    """Informational-only: flag periods where the running MD/AD lord carries
    a business/enterprise-track signature (Mars/Rahu/Venus dual-lordship of
    business-relevant houses per _derive_career_track()'s own convention)
    while the user's stated career_ctx points to salaried/stability
    preference — a real tension worth surfacing, not a scoring change.
    Mutates `blocks` in place (adds "business_tension" key); returns None.
    """
    _career_track = _derive_career_track(career_ctx)
    if _career_track == "business":
        return   # user is already on a business track — no tension to flag
    _desired = (career_ctx.get("desired_outcome") or "").lower()
    if _desired not in ("stability", "promotion", ""):
        return

    _business_signature_planets = {"Mars", "Rahu", "Venus"}
    for b in blocks:
        _md, _ad = b.get("md_lord", ""), b.get("ad_lord", "")
        if _md in _business_signature_planets and _ad in _business_signature_planets:
            b["business_tension"] = (
                f"{_md}-{_ad} period carries an entrepreneurial/business-track signature "
                "even though your stated preference is salaried stability — if an "
                "independent opportunity appears during this window, it may be worth "
                "evaluating rather than dismissing outright."
            )


def build_career_timeline(
    chart: "TimelineChartInput",
    eff_strengths: Dict[str, float],
    career_ctx: Dict[str, Any],
    mode: str = "full",
    llm_context: Optional[Dict[str, Any]] = None,
    config: Optional["TimelineConfig"] = None,
) -> List[Dict]:
    """Build the deterministic career timeline for a salaried professional.

    Args:
        chart: TimelineChartInput with all required chart data.
               Build via TimelineChartInput.from_payload(payload) or directly.
        eff_strengths: effective planetary strengths {planet: float}
        career_ctx: validated career context from timeline_inputs
        mode: "full" | "limited" | "forecast"
        config: TimelineConfig controlling LLM-scoring isolation and horizon
                policy. Defaults to fully deterministic + forecast horizon.

    Returns a list of PeriodBlock dicts, each containing:
        md_lord, ad_lord, start_date, end_date (as ISO strings),
        is_past, is_current, event_type, active_houses, transit_flags,
        career_score, sub_scores, domain_tag,
        narrative_hint (4-5 sentences, AD-level),
        md_narrative (3-paragraph MD-level summary, on first block of each MD),
        jaimini_role, kp_cusp_alignment,
        remedies, pratyantardashas
    """
    from .timeline_inputs import compute_confidence_tier

    config = config or TimelineConfig()

    dob_str     = chart.dob or ""
    dob         = parse_iso_date(dob_str)
    if not dob:
        return []

    current_date_str = career_ctx.get("current_date", "")
    today = parse_iso_date(current_date_str) or date.today()

    lagna_sign = chart.lagna_sign or ""
    dasha_seq  = chart.dasha_sequence or []
    kp_cusps   = chart.kp_cusps or {}

    # Step 1: dasha calendar
    all_periods = _dasha_calendar(dasha_seq, dob)
    if not all_periods:
        return []

    # Step 2: slice to window.
    #
    # Two distinct horizon policies (config.horizon_mode) resolve a real
    # contradiction: career_validation_prompt.py tells the validator LLM it
    # has "full predicted blocks covering the person's career history" and
    # says not to restrict to a fixed number of years, but this function used
    # to always return a hardcoded 12-month past window — so validation runs
    # would mark real historical events (5-15+ years back) as "missed" simply
    # because no blocks were ever generated for those years.
    #
    #   "forecast"   -- (default) last _WINDOW_PAST_MONTHS (12) + next
    #                    _WINDOW_FUTURE_YEARS (4) years. What the user sees.
    #   "validation" -- past window reaches back to the earliest known actual
    #                    career_event (plus a 12-month pad), no future window,
    #                    so the validator's own instructions are actually true.
    #
    # Bug fix (2026-07): "forecast" mode used to hard-return _WINDOW_PAST_MONTHS
    # (12) regardless of career_ctx, so join_date/last_promotion_date supplied
    # 2-4+ years in the past never had a corresponding dasha block generated at
    # all -- _retroactive_validate() then always found 0 matches, not because
    # its matching logic was wrong (it wasn't), but because the periods it
    # needed to check against were never sliced into existence in the first
    # place. Both modes now derive the lookback from career_ctx; forecast mode
    # keeps the future window intact (unlike validation mode) and the existing
    # _MAX_OUTPUT_PERIODS budget (~line 4166) already prioritizes current/future
    # blocks and trims older past blocks for DISPLAY only, after retro-validation
    # has already run against the full widened window -- so widening this is
    # safe and does not flood the visible report with two decades of history.
    def _derive_past_months() -> int:
        earliest: Optional[date] = None
        for ev in (career_ctx.get("career_events") or []):
            ev_date = parse_iso_date(str(ev.get("date", ""))) if isinstance(ev, dict) else None
            if ev_date and (earliest is None or ev_date < earliest):
                earliest = ev_date
        if earliest is None:
            for _fld in ("join_date", "last_promotion_date", "last_hike_date"):
                _d = parse_iso_date(str(career_ctx.get(_fld, "")))
                if _d and (earliest is None or _d < earliest):
                    earliest = _d
        if earliest is None:
            return _WINDOW_PAST_MONTHS
        months_back = (today.year - earliest.year) * 12 + (today.month - earliest.month)
        return max(_WINDOW_PAST_MONTHS, months_back + 12)   # +12mo pad

    _past_months = _derive_past_months()
    _future_years = 0 if config.horizon_mode == "validation" else _WINDOW_FUTURE_YEARS
    window = _slice_window(all_periods, today, past_months=_past_months, future_years=_future_years)
    if not window:
        return []

    # Phase 0 LLM context — extract weight overrides, intent tags, and sector_modifier.
    # llm_context is produced by llm_context_enricher.enrich_career_context()
    # and passed in by engine_io.parse_json_payload().
    #
    # Isolation: this whole block only runs, and only feeds scoring, if
    # config allows it. Default config (scoring_mode="deterministic") keeps
    # every flag False, so no LLM call happens and _weight_overrides /
    # _intent_tags / _sector_modifier are always empty/zero — matching the
    # module docstring's "fully deterministic" claim. Set
    # config.scoring_mode="llm_calibrated" plus the individual allow_llm_*
    # flags to opt into calibration explicitly.
    _any_llm_scoring_allowed = (
        config.allow_llm_weight_overrides
        or config.allow_llm_intent_tags
        or config.allow_llm_sector_modifier
    )
    _llm_ctx: Dict[str, Any] = {}
    if _any_llm_scoring_allowed:
        _llm_ctx = llm_context or {}
        # B-5: If llm_context is absent, attempt inline enrichment so direct callers
        # (tests, CLI, batch) also benefit from Phase 0 calibration.
        if not _llm_ctx or not _llm_ctx.get("enrichment_ok"):
            try:
                from jyotish.llm_context_enricher import enrich_career_context, build_chart_basics
                _chart_basics = build_chart_basics(career_ctx, chart)
                _enriched = enrich_career_context(career_ctx, _chart_basics)
                if _enriched and _enriched.get("enrichment_ok"):
                    _llm_ctx = {**_llm_ctx, **_enriched}
            except Exception as _enrich_err:
                import logging as _log
                _log.getLogger("jyotish_timeline").debug(
                    "Phase 0 inline enrichment skipped: %s", _enrich_err
                )
    _weight_overrides: Dict[str, float] = (
        (_llm_ctx.get("weight_overrides", {}) or {}) if config.allow_llm_weight_overrides else {}
    )
    _intent_tags: List[str] = (
        (_llm_ctx.get("intent_tags", []) or []) if config.allow_llm_intent_tags else []
    )
    # GAP 3 fix: sector_modifier — LLM-assessed sector opportunity signal (-1.0 to +1.0)
    _sector_modifier: float = (
        float(_llm_ctx.get("sector_modifier", 0.0) or 0.0) if config.allow_llm_sector_modifier else 0.0
    )
    # Attach to career_ctx so _classify_event() can read them for tiebreaking
    if _intent_tags:
        career_ctx = {**career_ctx, "_intent_tags": _intent_tags}

    # GAP 2 fix (2026-07-07): compute the KP house-chain summary ONCE here
    # (chart-level, does not change per-period) so _classify_event() can
    # apply the promotion-house-vs-foreign/leadership-house override without
    # recomputing this per period. Wrapped defensively — a chart with no/
    # malformed kp_cusps data simply gets kp_house_chain={} and the override
    # in _classify_event() is a no-op (conservative default preserved).
    try:
        from jyotish.astrology_explainer import _kp_house_chain_summary
        _kp_house_chain_for_override = _kp_house_chain_summary(kp_cusps) if kp_cusps else {}
    except Exception:
        _kp_house_chain_for_override = {}

    # Steps 3–5: score, transit overlay, classify
    blocks: List[Dict] = []
    _previous_event_type: str = ""       # state machine — carry forward
    _md_change_dates = sorted({
        _p.get("md_start") for _p in all_periods
        if isinstance(_p.get("md_start"), date)
    })
    _ad_change_dates = sorted({
        _p.get("start_date") for _p in all_periods
        if isinstance(_p.get("start_date"), date)
    })
    # GAP 7 fix: per-tier cooldown tracking replaces single _last_high_event_date.
    _last_event_dates: Dict[str, Optional[date]] = {
        "high":   None,   # BREAKTHROUGH
        "mid":    None,   # PROMOTION
        "low":    None,   # LEADERSHIP_EXPANSION
        "income": None,   # SALARY_HIKE / INCOME_INFLECTION
    }

    def _tier_cooldown_active(tier: str, ref_date: date) -> bool:
        _d = _last_event_dates.get(tier)
        if _d is None:
            return False
        return (ref_date - _d).days / 30.4 < _COOLDOWN_MONTHS_BY_TIER.get(
            {"high": "BREAKTHROUGH", "mid": "PROMOTION",
             "low": "LEADERSHIP_EXPANSION", "income": "INCOME"}[tier], 18
        )

    # Augment planet_sign with moon nakshatra key so _detect_natal_yogas can
    # compute the 64th Navamsha lord (G-A6) without a new function parameter.
    _ps_for_yogas = dict(
        getattr(chart, "planet_sign", None)
        or getattr(chart, "planet_signs", None)
        or {}
    )
    _moon_nak_val = getattr(chart, "moon_nakshatra", "") or ""
    if _moon_nak_val:
        _ps_for_yogas["_moon_nakshatra"] = _moon_nak_val
    _detected_yogas = _detect_natal_yogas(
        planet_house=chart.planet_house or {},
        lagna_sign=lagna_sign,
        house_lords=chart.house_lords or {},
        planet_sign=_ps_for_yogas,
    )

    # C-1: Compute SBC natal strength modifier once — reused across all periods
    _sbc_natal_mod: float = _compute_sbc_natal_mod(chart)

    for p in window:
        scores = _score_period(
            p, chart, eff_strengths, career_ctx, lagna_sign,
            detected_yogas=_detected_yogas,
            weight_overrides=_weight_overrides,
            sbc_natal_mod=_sbc_natal_mod,
            today=today,
            md_change_dates=_md_change_dates,
            ad_change_dates=_ad_change_dates,
        )
        scores["_md_lord"] = p["md_lord"]
        scores["_ad_lord"] = p["ad_lord"]
        # FIX 3: dynamic per-AD transits instead of static today-snapshot
        flags  = _get_dynamic_transits(
            p["start_date"], p["end_date"], chart, lagna_sign, today
        )
        _macro_score = _get_macro_score(career_ctx.get("industry_sector", ""), career_ctx)
        # GAP 3 fix: apply Phase 0 LLM sector_modifier to the static macro index.
        # sector_modifier is -1.0 to +1.0; ±15% adjustment on the macro score.
        if _sector_modifier:
            _macro_score = max(0.30, min(1.50, _macro_score * (1.0 + 0.15 * _sector_modifier)))
        # GAP 7 fix: tier-stratified cooldown — compute active flags for all tiers.
        _cooldown_by_tier = {
            "high":   _tier_cooldown_active("high",   p["start_date"]),
            "mid":    _tier_cooldown_active("mid",    p["start_date"]),
            "low":    _tier_cooldown_active("low",    p["start_date"]),
            "income": _tier_cooldown_active("income", p["start_date"]),
        }
        event_type, active_houses, near_miss = _classify_event(
            scores, flags, career_ctx, chart, mode,
            previous_event=_previous_event_type,
            macro_score=_macro_score,
            cooldown_by_tier=_cooldown_by_tier,
            kp_house_chain=_kp_house_chain_for_override,   # GAP 2 (2026-07-07)
        )
        career_track = _derive_career_track(career_ctx)
        event_type = _adapt_event_for_career_track(event_type, career_track)
        base_event_type = event_type
        if mode == "forecast":
            event_type = f"FORECAST_{base_event_type}"

        # G11 fix: reuse the scores already computed inside _score_period rather than
        # calling _kp_career_cusp_score and _jaimini_career_score a second time.
        # The role label (jai_role) is not stored in sub_scores so Jaimini is still
        # called once here — but only for the label, not the score.
        kp_c_score = scores.get("kp_cusp_score", 0.0)          # from sub_scores
        jai_score  = scores.get("jaimini_score", 0.0)           # from sub_scores
        _, jai_role = _jaimini_career_score(p["md_lord"], p["ad_lord"], chart)  # role label only

        # Domain tag from company karaka + active houses
        domain_tag = _derive_domain_tag(p["md_lord"], p["ad_lord"], active_houses, career_ctx)
        secondary_event_type = _derive_secondary_event_type(event_type, career_track, career_ctx, sub_scores=scores)
        # GAP 3: planet × industry skill recommendations
        skill_recs = _get_skill_recommendation(p["ad_lord"], career_ctx.get("industry_sector", ""))
        # Phase 3, item #18: career-stage + domain framing (empty string for
        # most charts/periods — only fires for senior experience or when a
        # domain-relevant event type is active).
        stage_domain_framing = _derive_stage_domain_framing(
            event_type, p["md_lord"], p["ad_lord"], career_ctx, chart=chart, sub_scores=scores
        )

        start_str = p["start_date"].isoformat()[:7]
        end_str   = p["end_date"].isoformat()[:7]

        # Expanded AD-level narrative hint (4-5 sentences)
        narrative = _build_narrative_hint(
            base_event_type, p["md_lord"], p["ad_lord"], flags, scores["career_score"],
            kp_cusp_score=kp_c_score, jaimini_score=jai_score,
            jaimini_role=jai_role, career_ctx=career_ctx,
            d9_digs=getattr(chart, "d9_planet_dignities", {}) or {},
            planet_sign=getattr(chart, "planet_sign", {}) or {},   # B4 fix
            lagna_sign=getattr(chart, "lagna_sign", "") or "",     # B4 fix
        )

        # GAP 8 fix: MD narrative is built in a second pass AFTER all ADs are scored,
        # so it can reference the full distribution of event types in this MD window.
        # We store the MD date strings on the block as internal keys for the second pass.
        md_narrative = ""
        _md_start_str = p["md_start"].isoformat()[:7] if hasattr(p.get("md_start", None), "isoformat") else start_str
        _md_end_str   = p["md_end"].isoformat()[:7]   if hasattr(p.get("md_end",   None), "isoformat") else end_str

        remedies   = _build_remedies(base_event_type, p["md_lord"], p["ad_lord"])
        pd_periods = _expand_pratyantardashas(
            p["md_lord"], p["ad_lord"], p["start_date"], p["end_date"]
        )
        # GAP 1 / G6 fix: annotate each PD with its micro-trigger window
        # GAP 11 fix: expand each PD into sooksham (4th-level) sub-periods
        # User-reported gap fix (2026-07): pd start/end are now full
        # day-precision ISO dates ("YYYY-MM-DD"), not "YYYY-MM" — parse
        # directly instead of reconstructing a month-end date.
        for _pd in pd_periods:
            _pd_start = parse_iso_date(str(_pd["start_date"])[:10])
            _pd_end   = parse_iso_date(str(_pd["end_date"])[:10])
            _tw = _find_trigger_window(_pd_start, _pd_end, chart, today)
            _pd["trigger_window"] = _tw
            # 4B fix: tag each PD with affliction level so the HTML narrative
            # can swap positive keywords for cautionary ones when the PD lord
            # is weak.  Proxy: eff_strength (already encodes debil, combust,
            # retrograde paradox, war-loss, etc. via _compute_eff_strengths).
            _pd_eff = eff_strengths.get(_pd["pd_lord"], 1.0)
            _pd_d9  = (getattr(chart, "d9_planet_dignities", {}) or {}).get(_pd["pd_lord"], "")
            # B2 fix: also check D1 natal debilitation via chart.planet_sign.
            # When d9_planet_dignities is absent (common with partial chart JSONs),
            # a Neecha planet in D1 (e.g. Mercury in Pisces) was getting affliction="ok"
            # and rendering the upbeat base-tier text ("Communication clarity").
            _pd_d1_sign  = (getattr(chart, "planet_sign", {}) or {}).get(_pd["pd_lord"], "")
            _pd_d1_debil = bool(_pd_d1_sign) and _DEBIL_SIGN.get(_pd["pd_lord"], "") == _pd_d1_sign
            if _pd_eff < 0.45 or str(_pd_d9).upper() == "DEBILITATED" or _pd_d1_debil:
                _pd["affliction"] = "severe"
            elif _pd_eff < 0.65:
                _pd["affliction"] = "moderate"
            else:
                _pd["affliction"] = "ok"

            # Phase 3 (2026-07-05, item #20): explicit 0-1 PD-level score, not
            # just an affliction label. Combines the same class of signals
            # already used at the AD level — dasha-lord career-house
            # lordship/occupancy, KP significator overlap, D10 occupancy,
            # transit trigger presence — scaled down for a single planet
            # instead of an MD+AD pair. Chart-agnostic: no planet/chart-
            # specific constants, just general house/KP/D10 lookups.
            _pd_lord = _pd["pd_lord"]
            _pd_house_score = 0.0
            _pd_h = (chart.planet_house or {}).get(_pd_lord, 0)
            if _pd_h:
                _pd_house_score += _HOUSE_CAREER_WEIGHT.get(_pd_h, 0.0) * 0.5
            for _hnum_str, _lord in (chart.house_lords or {}).items():
                if _lord == _pd_lord:
                    try:
                        _pd_house_score += _HOUSE_CAREER_WEIGHT.get(int(_hnum_str), 0.0) * 0.3
                    except ValueError:
                        pass
            _pd_house_score = max(0.0, min(1.0, _pd_house_score / 1.2))

            _pd_kp_sig = (getattr(chart, "kp_significators", {}) or {}).get(_pd_lord, {})
            _pd_kp_score = 0.0
            if isinstance(_pd_kp_sig, dict):
                for _h in (2, 6, 10, 11):
                    if _h in _pd_kp_sig.get("level_1", []) or _h in _pd_kp_sig.get("level_2", []):
                        _pd_kp_score = max(_pd_kp_score, 1.0)
                    elif _h in _pd_kp_sig.get("level_3", []):
                        _pd_kp_score = max(_pd_kp_score, 0.6)
                    elif _h in _pd_kp_sig.get("level_4", []):
                        _pd_kp_score = max(_pd_kp_score, 0.3)

            _pd_d10_occ = getattr(chart, "d10_house_occupancy", {}) or {}
            _pd_d10_score = 0.0
            for _h in ("10", "11"):
                if _pd_lord in (_pd_d10_occ.get(_h, []) or []):
                    _pd_d10_score = 1.0
                    break

            _pd["pd_score"] = round(max(0.0, min(1.0,
                0.35 * _pd_house_score + 0.25 * _pd_kp_score + 0.20 * _pd_d10_score
                + 0.20 * min(1.0, _pd_eff / 1.4)
                + (0.05 if _tw else 0.0)   # small trigger-window presence bonus
            )), 3)

            # GAP 11: sooksham dasha (4th level) — 3-40 day precision windows
            if _pd_start and _pd_end:
                _pd["sookshams"] = _expand_sookshams(_pd["pd_lord"], _pd_start, _pd_end)
        block = {
            "md_lord":              p["md_lord"],
            "ad_lord":              p["ad_lord"],
            "start_date":           start_str,
            "end_date":             end_str,
            "is_past":              p.get("is_past", False),
            "is_current":           p.get("is_current", False),
            "event_type":           event_type,
            "secondary_event_type": secondary_event_type,
            "career_track":         career_track,
            "active_houses":        active_houses,
            "transit_flags":        flags,
            "career_score":         scores["career_score"],
            "sub_scores":           {k: v for k, v in scores.items()
                                     if not k.startswith("_") and k != "career_score"},
            # GAP 2 fix (2026-07-07): surface the KP promotion-override label
            # (if the override fired for this block) directly on the block
            # so the report can display it, instead of it only living inside
            # `scores` under an underscore-prefixed key that sub_scores above
            # deliberately excludes.
            "kp_promotion_override_label": scores.get("_kp_promotion_override_label", ""),
            # GAP 3 fix (2026-07-07 follow-up audit): explicit deterministic
            # fields (not just narrative) — see
            # gap_corrections_career_timeline_2026_07.kp_promotion_override_decision().
            "kp_override_applied":  bool(scores.get("_kp_override_applied", False)),
            "kp_override_reason":   scores.get("_kp_override_reason", ""),
            "domain_tag":           domain_tag,
            "stage_domain_framing": stage_domain_framing,   # Phase 3, item #18
            "jaimini_role":         jai_role,
            "kp_cusp_alignment":    round(kp_c_score, 3),
            "near_miss":            near_miss,
            "narrative_hint":       narrative,
            "md_narrative":         md_narrative,   # populated by second pass below
            "_md_start_str":        _md_start_str,  # internal — consumed in second pass
            "_md_end_str":          _md_end_str,    # internal — consumed in second pass
            "remedies":             remedies,
            "pratyantardashas":     pd_periods,
            "is_primary_opportunity": False,   # populated by _mark_primary_opportunities below
            "skill_recommendations": skill_recs,   # GAP 3: planet × industry skills
            "macro_score":         round(_macro_score, 3),   # GAP 4: sector macro health
            "macro_headwinds":     _macro_score < _MACRO_HEADWIND_THRESHOLD,
            "salary_range":         _compute_salary_range(
                base_event_type,
                scores["career_score"],
                career_ctx,
                _macro_score,
                h2_sav=float((getattr(chart, "sav_points_houses", {}) or {}).get("H2", 28)),
                h11_sav=float((getattr(chart, "sav_points_houses", {}) or {}).get("H11", 28)),
            ),
        }

        # Item #4 (2026-07-07): mandate-quality scoring (net-new). Only
        # chart-derivable dimensions are populated here — `event_type` is only
        # genuinely available at this point in the pipeline (after
        # _classify_event), not inside _score_period, so this block is
        # attached here rather than inside the sub_scores dict. Signals used
        # are strictly ones already in scope in this loop: `active_houses`
        # (H9/H12 = classical foreign/overseas-exposure houses, standing in
        # for a foreign/global-visibility read since a separate foreign_score
        # is computed in an unrelated module not in scope here) and
        # scores.get("d9_weak_lord") (already-computed D9 debility signal).
        if block.get("event_type", "").replace("FORECAST_", "") in (
            "PROMOTION", "LEADERSHIP_EXPANSION", "AUTHORITY_SHIFT"
        ):
            _mq_global_exposure = bool({9, 12} & set(active_houses or []))
            _mq_weak_lord = scores.get("d9_weak_lord", "")
            _mq_elevated_risk = _mq_weak_lord in ("MD", "AD", "both")
            # Schema reshaped (2026-07) to a REQUIRED/WATCH verification
            # checklist per the user's exact spec, rather than None-valued
            # numeric placeholders — the astrology genuinely cannot compute
            # authority/budget/team-control/compensation-alignment values
            # (those need external HR/org data this engine doesn't have),
            # but it CAN and should say "these must be verified before
            # accepting" for any promotion/leadership-expansion/authority
            # period — that's the actionable signal, not a blank None.
            block["mandate_quality"] = {
                "required":               True,
                "title_clarity":          "REQUIRED",
                "budget_control":         "REQUIRED",
                "team_control":           "REQUIRED",
                "reporting_line":         "REQUIRED",
                "executive_sponsorship":  "REQUIRED",
                "success_metrics":        "REQUIRED",
                "political_risk":         "HIGH_WATCH" if _mq_elevated_risk else "WATCH",
                "global_visibility":      "HIGH" if _mq_global_exposure else "MODERATE",
                "narrative": (
                    "Do not accept only title expansion. Ensure authority, team, "
                    "budget, reporting line, and measurable business ownership are "
                    "clear" + (
                        " — D9 debility on this period's dasha lord raises the "
                        "durability stakes further, so mandate clarity matters more "
                        "than the title itself." if _mq_elevated_risk else "."
                    )
                ),
            }

        # GAP 2: Workplace friction dynamics
        _projected_transit_positions = {}
        for _planet in ("Saturn", "Rahu", "Mars", "Ketu"):
            _cur_h = (chart.transit_house_positions or {}).get(_planet, 0)
            if _cur_h:
                _mid_days = (p["start_date"] + (p["end_date"] - p["start_date"]) // 2 - today).days
                _days_per_h = {"Saturn": 912, "Rahu": 548, "Mars": 45, "Ketu": 548}.get(_planet, 365)
                _moved = int(_mid_days / _days_per_h) if _days_per_h else 0
                _dir = -1 if _planet in ("Rahu", "Ketu") else 1
                _projected_transit_positions[_planet] = int((_cur_h - 1 + _dir * _moved) % 12) + 1
        workplace = _compute_workplace_friction(flags, _projected_transit_positions, chart, lagna_sign)
        block["workplace_dynamics"] = workplace

        # Job-loss framework: surface the multi-layer confirmation ledger so the
        # report can show which independent layers agreed (votes, label, per-layer).
        _adv_detail = scores.get("_adverse_detail")
        if _adv_detail and _adv_detail.get("label") != "pressure_only":
            block["adverse_confirmation"] = {
                "label":        _adv_detail.get("label"),
                "votes":        _adv_detail.get("votes"),
                "required_met": _adv_detail.get("required_met"),
                "layers":       _adv_detail.get("layers"),
                "balance":      _adv_detail.get("balance"),
            }

        # Production-grade multi-event career-risk object (0-100 per event,
        # severity, recovery, numeric guardrail, evidence ledger). Attached to
        # every block so the report/API/UI can consume comparable scores. Never
        # overrides block["event_type"] — it is an additive scoring artifact.
        try:
            block["career_risk"] = career_risk_report(
                scores, flags, chart, active_h=set(active_houses or []),
                known_events_present=_has_known_past_events(career_ctx),
            )
        except Exception:   # scoring must never break timeline generation
            pass

        blocks.append(block)
        _previous_event_type = event_type
        # GAP 7 fix: update per-tier last-event dates
        if base_event_type == "BREAKTHROUGH":
            _last_event_dates["high"] = p["start_date"]
        elif base_event_type == "PROMOTION":
            _last_event_dates["mid"] = p["start_date"]
        elif base_event_type == "LEADERSHIP_EXPANSION":
            _last_event_dates["low"] = p["start_date"]
        elif base_event_type in ("SALARY_HIKE", "INCOME_INFLECTION"):
            _last_event_dates["income"] = p["start_date"]

    # GAP 8 fix: second pass — build MD narratives with full AD event-type context.
    # This ensures the MD narrative references the spread of events across all its ADs
    # rather than just the first AD's data.
    _md_first_block: Dict[str, Dict] = {}
    _md_ad_events:   Dict[str, List[str]] = {}
    for _b in blocks:
        _ml = _b["md_lord"]
        if _ml not in _md_first_block:
            _md_first_block[_ml] = _b
        _md_ad_events.setdefault(_ml, []).append(_b.get("event_type", ""))

    for _ml, _fb in _md_first_block.items():
        _ad_evt_list = _md_ad_events.get(_ml, [])
        # Deduplicated ordered event types (strip FORECAST_ prefix for readability)
        _ad_evt_summary = ", ".join(
            dict.fromkeys(e.replace("FORECAST_", "") for e in _ad_evt_list if e)
        )
        _jai_s_md, _jai_r_md = _jaimini_career_score(_ml, _ml, chart)
        _kp_s_md = _kp_career_cusp_score(_ml, _ml, kp_cusps)
        _fb["md_narrative"] = _build_md_narrative(
            _ml,
            _fb.get("_md_start_str", _fb["start_date"]),
            _fb.get("_md_end_str",   _fb["end_date"]),
            chart, lagna_sign, career_ctx,
            jaimini_role=_jai_r_md, kp_cusp_score=_kp_s_md,
            ad_event_summary=_ad_evt_summary,
        )

    # Remove internal second-pass keys
    for _b in blocks:
        _b.pop("_md_start_str", None)
        _b.pop("_md_end_str",   None)

    # Step 6: retroactive validation
    retro_matches = _retroactive_validate(blocks, career_ctx)

    # Confidence tier
    birth_time_known = str(
        career_ctx.get("birth_time_precision", "unknown") or "unknown"
    ).lower() != "unknown"
    # BUG FIX: confidence previously never checked whether any transit data
    # was actually populated for this chart. If all relevant transit arrays
    # are empty, compute_confidence_tier caps the tier by one step.
    _transit_data_available = bool(
        (getattr(chart, "transit_house_positions", None) or {})
        or (getattr(chart, "planet_transit_degrees", None) or {})
    )
    confidence = compute_confidence_tier(
        career_ctx, birth_time_known, retro_matches,
        transit_data_available=_transit_data_available,
    )

    # GAP 6 fix: retroactive calibration — past match rate nudges forward block scores.
    # A well-calibrated chart (2+ past matches) gets a small upward adjustment;
    # poor calibration (0 matches, 2+ past blocks) gets a downward one.
    _past_count = sum(1 for b in blocks if b.get("is_past"))
    _retro_rate = (retro_matches / max(_past_count, 1)) if _past_count > 0 else 0.5
    if retro_matches >= 2 and _retro_rate >= 0.5:
        _retro_cal = 1.03   # well-calibrated: +3% nudge on forward scores
    elif retro_matches == 0 and _past_count >= 2:
        _retro_cal = 0.97   # poor calibration: -3% nudge
    else:
        _retro_cal = 1.0

    # Attach confidence and retro info to every block
    for b in blocks:
        if not b.get("is_past") and _retro_cal != 1.0:
            b["career_score"] = round(min(1.0, b["career_score"] * _retro_cal), 3)
        b["confidence"]               = confidence
        b["retro_matches"]            = retro_matches
        b["retro_calibration_factor"] = round(_retro_cal, 3)

    # Step 7: always chronological; mark primary opportunities (FIX 5)
    blocks = sorted(blocks, key=lambda x: x["start_date"])
    desired = career_ctx.get("desired_outcome", "")
    _mark_primary_opportunities(blocks, desired)

    # Add business-tension flag if applicable (informational only)
    _check_business_tension(blocks, career_ctx, lagna_sign)

    # Step 8: foreign opportunity module (past 1yr + next 5yr)
    # G8 fix: compute foreign opportunities from ALL blocks BEFORE applying the
    # _MAX_OUTPUT_PERIODS cap.  The 5-year foreign window can extend beyond 12 blocks
    # for charts with many short ADs, so slicing first caused missed opportunities.
    _foreign_opps = _compute_foreign_module(blocks, chart, lagna_sign, today=today, career_ctx=career_ctx)

    # T1 fix: apply the output cap with priority selection so that current and
    # future blocks always survive.  When _past_months is large (e.g. 25 years
    # of experience), purely chronological slicing would fill all slots with old
    # Mahadasha blocks and discard the entire future forecast window.
    #
    # Algorithm:
    #   1. Take ALL current + future blocks (must-include)
    #   2. Fill remaining budget with past blocks, most-recent first
    #   3. Re-sort chronologically for display
    _future_cur = [b for b in blocks if not b.get("is_past", True)]
    _past_only  = [b for b in blocks if b.get("is_past", False)]
    _budget     = max(_MAX_OUTPUT_PERIODS - len(_future_cur), 0)
    _past_sel   = _past_only[-_budget:] if _budget else []   # most-recent-past first
    _all_blocks = sorted(_future_cur + _past_sel, key=lambda x: x["start_date"])

    # Attach each foreign opportunity to its matching block for cross-reference.
    # GAP 9 fix: match by md_lord+ad_lord instead of start_date+ad_lord —
    # start_date on _fo is the FULL (unclipped) block date; _all_blocks entries may
    # have start_date clipped to the window boundary, causing the old comparison to fail.
    # md_lord+ad_lord is unique within the output window and immune to date clipping.
    for _fo in _foreign_opps:
        _fo_md = _fo.get("md_lord", "")
        _fo_ad = _fo.get("ad_lord", "")
        for _b in _all_blocks:
            if _b.get("md_lord") == _fo_md and _b.get("ad_lord") == _fo_ad:
                _b["foreign_opportunity"] = _fo
                break

    # Gap-review (2026-07-05, Phase 1 of 4th round): semantic reclassification.
    # Three general (chart-agnostic) rules that fire only on already-computed
    # signals — no new astrology, just refusing to let a single generic label
    # survive when a stronger, more specific signal is present on the SAME
    # block. Each demotes the original label to `secondary_event_type` rather
    # than discarding it.
    for _b in _all_blocks:
        _sub = _b.get("sub_scores", {}) or {}
        _promo = _sub.get("promotion_score", 0.0) or 0.0
        _ad_l  = _b.get("ad_lord", "")
        _fo_b  = _b.get("foreign_opportunity") or {}
        _fscore = _fo_b.get("foreign_score", 0.0) or 0.0
        _orig_et = _b.get("event_type", "")
        _promo_tier = _orig_et.replace("FORECAST_", "") in ("PROMOTION", "LEADERSHIP_EXPANSION", "BREAKTHROUGH")

        # Gap 3, tightened (user-reported round): a period reading strongly
        # foreign (>=0.80 blended, now also confidence-capped upstream — see
        # _score_foreign_period) but weak on promotion used to ALWAYS become
        # "FOREIGN_BASE_REPOSITIONING," implying a physical base change —
        # even when the manifestation breakdown clearly favors foreign-client/
        # remote-delivery work over relocation/settlement (e.g. Venus or Moon
        # AD periods, which classically indicate global-platform/foreign-
        # client exposure more than physical relocation). Now picks the label
        # that actually matches the DOMINANT manifestation sub-score instead
        # of defaulting to the relocation-flavored label every time.
        if _fscore >= 0.80 and _promo < 0.55 and _promo_tier:
            _manif = _fo_b.get("manifestation_scores", {}) or {}
            _reloc_like = max(_manif.get("relocation", 0.0) or 0.0, _manif.get("settlement", 0.0) or 0.0)
            _client_like = max(_manif.get("foreign_client", 0.0) or 0.0,
                                _manif.get("remote_global_delivery", 0.0) or 0.0,
                                _manif.get("onsite_assignment", 0.0) or 0.0)
            _new_tag = "FOREIGN_BASE_REPOSITIONING" if _reloc_like >= _client_like else "FOREIGN_CLIENT_PLATFORM_GROWTH"
            _b["secondary_event_type"] = _orig_et.replace("FORECAST_", "")
            _b["event_type"] = ("FORECAST_" if _orig_et.startswith("FORECAST_") else "") + _new_tag

        # Gap 5: Rahu as the running AD lord is astrologically non-linear/
        # disruptive by nature (sudden, unconventional, restructuring-linked)
        # even when the underlying numeric score reads as a clean promotion
        # tier — the planetary agent, not just the score, should shape the
        # label. Promotion becomes the secondary (still-possible) outcome.
        elif _ad_l == "Rahu" and _promo_tier:
            _b["secondary_event_type"] = _orig_et.replace("FORECAST_", "")
            _b["event_type"] = ("FORECAST_" if _orig_et.startswith("FORECAST_") else "") + "DISRUPTIVE_GLOBAL_TRANSFORMATION"

        # Gap 6: Mars simultaneously ruling a growth house (10/11) and a
        # dusthana/pressure house (6/8/12) for the active MD/AD is the
        # classical dual-lordship signature of gains achieved through
        # workload, competition, or conflict — general rule for any lagna
        # where this specific dual placement occurs, not Gemini-specific.
        elif _ad_l == "Mars":
            _ah = set(_b.get("active_houses", []) or [])
            if _ah & {10, 11} and _ah & {6, 8, 12}:
                _b["secondary_event_type"] = _orig_et.replace("FORECAST_", "")
                _b["event_type"] = ("FORECAST_" if _orig_et.startswith("FORECAST_") else "") + "PRESSURE_GAIN_WINDOW"

    # D-3: Compute micro-timing and store on payload (if a payload reference is available).
    # career_ctx may carry a "_payload_ref" set by engine_io so we can attach the result.
    _payload_ref = career_ctx.get("_payload_ref")
    if _payload_ref is not None:
        try:
            from .micro_timing import compute_all_micro_timing as _camt
            _active_block = next(
                (b for b in _all_blocks if b.get("is_current")), None
            ) or (_all_blocks[0] if _all_blocks else {})
            _mt_result = _camt(
                today=today,
                lagna_sign=lagna_sign,
                planet_house=getattr(_payload_ref, "planet_house", {}),
                house_lords=getattr(_payload_ref, "house_lords", {}),
                active_ad_lord=_active_block.get("ad_lord", ""),
                active_pd_lord=getattr(_payload_ref, "pratyantar_dasha_lord", ""),
                timeline_blocks=_all_blocks,
            )
            _payload_ref.micro_timing = _mt_result
        except Exception as _mt_err:
            import logging as _log
            _log.getLogger("jyotish_timeline").debug("D-3 micro_timing skipped: %s", _mt_err)

        # 2026-07-05: deterministic year-by-year Jupiter/Saturn/Rahu-Ketu
        # transit outlook (replaces the LLM Mahadasha Narrative Arcs section).
        try:
            _payload_ref.annual_transit_outlook = build_annual_transit_outlook(
                chart=chart, lagna_sign=lagna_sign, today=today, years_ahead=4, years_back=1,
            )
        except Exception as _ato_err:
            import logging as _log
            _log.getLogger("jyotish_timeline").debug(
                "annual_transit_outlook skipped: %s", _ato_err
            )

    # Gap-review (2026-07-05, Phase 2, item 'Gap 11'): validate the finished
    # block list against a small set of internal-consistency invariants
    # before it's handed to the HTML renderers. Non-fatal — logs warnings and
    # tags each offending block with `_schema_warnings` for transparency,
    # rather than crashing report generation over a data-quality issue. This
    # is what would have caught things like "foreign score 46 but duration
    # labelled Relocation" or "two blocks both marked is_current" earlier,
    # deterministically, instead of only surfacing via manual audit.
    try:
        _validate_career_timeline_schema(_all_blocks, today)
    except Exception as _val_err:
        import logging as _log
        _log.getLogger("jyotish_timeline").debug("Schema validation skipped: %s", _val_err)

    return _all_blocks


# Approved primary event tags — the practical whitelist is whatever
# `_ROADMAP_EVENT_COLORS` (web_report.py) knows how to color, since an
# event_type outside that set would silently render with the grey fallback
# color anyway. Kept here as a plain set (not importing web_report.py, which
# would create a circular import) so schema validation doesn't need the
# rendering module — hand-synced comment marks where to update both if the
# taxonomy grows.
_APPROVED_EVENT_TAGS = {
    "BREAKTHROUGH", "PROMOTION", "LEADERSHIP_EXPANSION", "INCOME_INFLECTION",
    "SALARY_HIKE", "JOB_CHANGE", "FOREIGN_POSTING", "GROWTH",
    "SKILL_UPGRADE_PHASE", "AUTHORITY_SHIFT", "RISK_PERIOD", "STABILITY",
    "TRANSITION", "RE_ENTRY", "FIRST_JOB", "CALIBRATION",
    "ENTREPRENEURSHIP_WINDOW", "EQUITY_EVENT", "LATERAL_MOVE", "SANDHI_PERIOD",
    "CAREER_PLATEAU", "STAGNATION", "CAREER_THROUGH_PARTNERSHIP",
    "BUSINESS_EXPANSION", "BUSINESS_BREAKTHROUGH", "CLIENT_PIPELINE_SHIFT",
    "MARKET_REPOSITIONING", "REVENUE_GROWTH", "BUSINESS_REENTRY",
    "FIRST_CLIENT_WINDOW",
    # Gap-review Phase 1 (4th round) semantic-reclassification tags:
    "FOREIGN_BASE_REPOSITIONING", "DISRUPTIVE_GLOBAL_TRANSFORMATION",
    "PRESSURE_GAIN_WINDOW",
    # User-reported gap fix (2026-07): foreign-client/remote-delivery variant,
    # distinct from relocation-flavored FOREIGN_BASE_REPOSITIONING.
    "FOREIGN_CLIENT_PLATFORM_GROWTH",
}
# Sub-score keys that are contractually 0-1 (as opposed to signed modifiers
# like d9_modifier/gandanta_penalty, which can legitimately be negative).
_ZERO_TO_ONE_SUBSCORE_KEYS = (
    "career_activation", "strength_product", "functional_nature",
    "house_activation", "d10_alignment", "sav_support", "kp_cusp_score",
    "jaimini_score", "promotion_score", "job_change_score", "income_score",
    "risk_score", "stability_score", "visibility_score", "d10_structural_score",
    "d10_lagna_support", "d9_sustainability_score",
)


def _validate_career_timeline_schema(blocks: List[Dict], today: Optional[date]) -> List[str]:
    """Non-fatal internal-consistency check over the finished block list.
    Logs a warning per issue and attaches `block["_schema_warnings"]` so a
    report can surface data-quality caveats instead of silently rendering a
    contradiction. Returns the list of warning strings (mainly for tests)."""
    import logging as _log
    logger = _log.getLogger("jyotish_timeline.schema")
    all_warnings: List[str] = []
    _today = today or date.today()
    _current_flags = 0

    for b in blocks:
        b["_schema_warnings"] = []

        sd, ed = b.get("start_date"), b.get("end_date")
        sd_d = parse_iso_date(sd) if isinstance(sd, str) else sd
        ed_d = parse_iso_date(ed) if isinstance(ed, str) else ed
        if sd_d and ed_d and sd_d >= ed_d:
            w = f"Block {b.get('md_lord')}-{b.get('ad_lord')}: start_date >= end_date ({sd} >= {ed})"
            b["_schema_warnings"].append(w)

        base_et = (b.get("event_type") or "").replace("FORECAST_", "")
        if base_et and base_et not in _APPROVED_EVENT_TAGS:
            w = f"Block {b.get('md_lord')}-{b.get('ad_lord')}: unrecognized event_type '{base_et}'"
            b["_schema_warnings"].append(w)

        sub = b.get("sub_scores", {}) or {}
        for k in _ZERO_TO_ONE_SUBSCORE_KEYS:
            v = sub.get(k)
            if v is not None and not (0.0 <= float(v) <= 1.0 + 1e-6):
                w = f"Block {b.get('md_lord')}-{b.get('ad_lord')}: sub_score '{k}'={v} out of [0,1]"
                b["_schema_warnings"].append(w)
        cs = b.get("career_score")
        if cs is not None and not (0.0 <= float(cs) <= 1.0 + 1e-6):
            b["_schema_warnings"].append(f"Block {b.get('md_lord')}-{b.get('ad_lord')}: career_score={cs} out of [0,1]")

        if sd_d and ed_d and sd_d <= _today < ed_d:
            if b.get("is_current"):
                _current_flags += 1

        fo = b.get("foreign_opportunity")
        if fo:
            fscore = fo.get("foreign_score", 0.0) or 0.0
            dur = fo.get("duration_type", "")
            if dur == "RELOCATION" and fscore < 0.55:
                w = (f"Block {b.get('md_lord')}-{b.get('ad_lord')}: foreign duration_type=RELOCATION "
                     f"but foreign_score={fscore:.2f} (<0.55) — inconsistent confidence")
                b["_schema_warnings"].append(w)

        for w in b["_schema_warnings"]:
            logger.warning(w)
            all_warnings.append(w)

    if _current_flags > 1:
        w = f"{_current_flags} blocks flagged is_current=True for the same 'today' — expected at most 1"
        logger.warning(w)
        all_warnings.append(w)

    return all_warnings



def _today_date():
    """Return today as a date object (mockable in tests)."""
    from datetime import date as _d
    return _d.today()



# ═════════════════════════════════════════════════════════════════════════════
# FOREIGN OPPORTUNITY MODULE  (past 1 yr + next 5 yrs)
# ═════════════════════════════════════════════════════════════════════════════

_FOREIGN_HOUSE_WEIGHTS: Dict[int, float] = {
    12: 0.42,   # House of foreign residence / emigration
    9:  0.32,   # Long journeys, fortune abroad
    3:  0.16,   # Short trips, neighboring countries
    8:  0.08,   # Sudden transformation (sometimes foreign via crisis)
}

_FOREIGN_PLANET_AFFINITY: Dict[str, float] = {
    "Rahu":    0.32,   # Primary karaka of foreign lands
    "Ketu":    0.10,   # Wandering, detachment from homeland
    "Jupiter": 0.14,   # Natural karaka of H9 (long journeys)
    "Saturn":  0.10,   # Long stays abroad; karmic foreign postings
    "Venus":   0.08,   # Foreign comforts, luxury placements
    "Moon":    0.06,   # Travel in general; emotional restlessness
    "Mercury": 0.05,   # Business travel, international communication
    "Mars":    0.04,   # Competitive/defence/engineering foreign markets
    "Sun":     0.04,   # Government/official foreign postings & deputations
}

# Gap-review (4th round, Gap 20): converted from a single comma-separated
# string per planet to a structured dict (direction, regions, rationale).
# The old flat string was truncated in the summary strip whenever it got
# sliced by character count (e.g. "Northwest / Water-adjacent regions (UK"),
# because a UI could only safely cut a plain string mid-word. Structured
# data lets the renderer show each region as its own pill and never has to
# guess where a safe truncation point is.
_GEO_AFFINITY_STRUCTURED: Dict[str, Dict[str, Any]] = {
    "Sun":     {"direction": "South",      "regions": ["Government-sponsored postings"], "rationale": "Sun governs authority/government-linked foreign postings."},
    "Moon":    {"direction": "Northwest",  "regions": ["UK", "Scandinavia", "Singapore"], "rationale": "Moon-linked water-adjacent, emotionally-familiar foreign environments."},
    "Mars":    {"direction": "South",      "regions": ["Germany", "Australia", "Canada"], "rationale": "Mars governs industrial/engineering-heavy foreign zones."},
    "Mercury": {"direction": "East",       "regions": ["UAE", "Hong Kong", "Singapore"], "rationale": "Mercury governs financial and tech-hub foreign centers."},
    "Jupiter": {"direction": "Northeast",  "regions": ["USA", "Australia", "Canada"], "rationale": "Jupiter governs prosperous, growth-oriented foreign economies."},
    # Gap fix (2026-07-05 audit): was "Northwest", contradicting _FOP_GEO_WHY's
    # "Venus governs the southeast direction" text (classical Vastu/Jyotish
    # directional-lord convention: Venus = Southeast/Agneya).
    "Venus":   {"direction": "Southeast",  "regions": ["Europe", "UAE", "USA"], "rationale": "Venus governs luxury/aesthetic-economy foreign regions."},
    "Saturn":  {"direction": "West",       "regions": ["UK", "USA", "Germany"], "rationale": "Saturn governs disciplined, industrial-economy foreign regions."},
    "Rahu":    {"direction": "Far East",   "regions": ["Southeast Asia", "Americas"], "rationale": "Rahu governs unconventional, non-traditional foreign destinations."},
    "Ketu":    {"direction": "Southeast",  "regions": ["Spiritual destinations", "Return-from-abroad"], "rationale": "Ketu governs detachment-linked or return-oriented foreign themes."},
}
# Back-compat flat-string map, derived from the structured data above so the
# two can never drift out of sync (previously two independent hardcoded maps).
_GEO_AFFINITY_MAP: Dict[str, str] = {
    _p: f'{_d["direction"]} / {", ".join(_d["regions"])}'
    for _p, _d in _GEO_AFFINITY_STRUCTURED.items()
}

_FOREIGN_DURATION_TYPE: Dict[str, str] = {
    "SHORT_TRIP":       "Short Trip (< 3 months)",
    "ASSIGNMENT":       "Foreign Assignment (3–18 months)",
    "RELOCATION":       "Long-term Relocation (18+ months)",
    "LONG_TERM_ABROAD": "Extended Stint Abroad (MD level)",
    "FOREIGN_LINKED":   "Foreign-linked exposure (no confirmed onsite/relocation signal)",
}

# Minimum onsite_assignment/relocation manifestation-score required before an
# "ASSIGNMENT"-tier duration label is allowed to be shown. Below this, the
# generic blended score alone is not considered sufficient evidence of an
# actual onsite/relocation-type foreign window (Fix C, 2026-07).
_FOREIGN_MANIF_MIN = 0.15

# Minimum score to be included as a foreign window
_FOREIGN_SCORE_THRESHOLD = 0.35

# ── Detailed "why" text for each foreign-house activation ─────────────────
_FOP_HOUSE_WHY: Dict[int, str] = {
    12: (
        "The 12th house is the primary bhava for foreign residence, extended stays abroad, "
        "and voluntary or involuntary exile. Its activation by the current dasha lord strongly "
        "suggests an environment shift outside the birth land — this can be a posting, a "
        "relocation, settlement, or significant time spent in a foreign country."
    ),
    9: (
        "The 9th house governs long-distance journeys, higher fortune, and international "
        "expansion. When dasha lords activate H9, fate-altering travel or overseas career "
        "opportunities arise naturally — often without the native actively seeking them."
    ),
    3: (
        "The 3rd house rules short excursions, neighbouring countries, and communication-based "
        "travel. Its activation suggests frequent short international trips, border-crossing "
        "assignments, or roles requiring multi-country presence within a compact region."
    ),
    8: (
        "The 8th house is the house of sudden transformation and hidden resources. Foreign "
        "connection here often arrives unexpectedly — a crisis-driven relocation, a sudden "
        "overseas offer, or gains through inheritance / foreign spouse's country."
    ),
}

# ── Planetary contribution explanations ────────────────────────────────────
_FOP_PLANET_WHY: Dict[str, str] = {
    "Rahu": (
        "Rahu is the primary karaka (signifier) of foreign lands in Vedic astrology. Its dasha "
        "period is the single strongest trigger for crossing borders, settling abroad, and "
        "breaking away from the native cultural environment. Rahu amplifies ambition for "
        "what is unfamiliar and unreachable within familiar surroundings."
    ),
    "Ketu": (
        "Ketu represents detachment, spirituality, and wandering. During Ketu periods the "
        "native may be drawn away from the homeland — sometimes through spiritual pilgrimage, "
        "sometimes through a sense of not belonging. Foreign postings during Ketu tend to be "
        "isolating but deeply transformative."
    ),
    "Jupiter": (
        "Jupiter is the natural signifier (Naisargika Karaka) of 9th-house themes "
        "(long journeys, fortune, philosophy) — note this is karaka signification, not "
        "house lordship, which varies by lagna. Its dasha promotes expansion through "
        "higher knowledge, international collaborations, and auspicious travel. "
        "Jupiter-ruled foreign stints are typically growth-oriented and supported by "
        "institutions, universities, or multinational corporations."
    ),
    "Saturn": (
        "Saturn governs karma, discipline, and sustained effort in alien environments. Its "
        "foreign periods tend to be long, demanding, and karmic in nature — the native earns "
        "slowly but surely. Saturn-driven relocations are often to industrial, cold, or "
        "structurally rigid countries (UK, Germany, Scandinavian nations)."
    ),
    "Venus": (
        "Venus rules comfort, luxury, and diplomatic arts. Foreign opportunities under Venus "
        "are often in hospitality, fashion, entertainment, or financial services. The "
        "destination is usually aesthetically appealing — Europe, UAE, Southeast Asia — "
        "and the posting involves a notable quality-of-life upgrade."
    ),  # NOTE (2026-07-08 fix, issue #6): this generic entry is now used only as the
        # non-software/MNC fallback — see _fop_planet_why() below, which swaps in a
        # software/MNC-specific Venus narrative when the chart's career_ctx indicates
        # a software/technology industry and/or senior-manager+ management track.
    "Moon": (
        "The Moon governs travel, mental restlessness, and the public. Moon periods incline "
        "the native toward frequent movement and changes of environment. Foreign periods "
        "under Moon are often emotionally driven — following a partner, family, or simply "
        "a deep inner need for a different emotional landscape."
    ),
    "Mercury": (
        "Mercury rules trade, communication, and analytical work. Its foreign triggers "
        "typically involve business travel, international client relationships, remote "
        "cross-border work, or moving for an education / research opportunity. Mercury "
        "periods abroad are mentally stimulating and commercially productive."
    ),
    "Sun": (
        "The Sun represents authority, government, and the state. Foreign periods under "
        "the Sun often involve official deputation, government postings, ambassadorial "
        "roles, or senior-level transfers arranged by an institution or state body."
    ),
    "Mars": (
        "Mars governs energy, engineering, and competition. Its foreign periods involve "
        "tough, dynamic environments — defence, mining, construction, or highly competitive "
        "markets. The posting typically demands physical effort and resilience."
    ),
}

# ── Geo direction explanation (WHY that direction) ─────────────────────────
_FOP_GEO_WHY: Dict[str, str] = {
    "Sun": (
        "Sun is lord of the south direction and signifies government and authority. Postings "
        "south of the birth place, or in countries with strong governmental or regulatory "
        "industries, align with Sun's energy."
    ),
    "Moon": (
        "Moon rules the northwest direction and water bodies. Countries adjacent to seas, "
        "rivers, or with a humid climate — UK, Scandinavia, coastal Southeast Asia — "
        "resonate with lunar energy. The native often feels emotionally comfortable there."
    ),
    "Mars": (
        "Mars governs the south direction and fiery, industrial environments. Germany, "
        "Australia, and Canada with their engineering, manufacturing, and mining sectors "
        "match Mars energy. Physical-labour or defence roles are common."
    ),
    "Mercury": (
        "Mercury governs the north and east, and rules commerce and communication. Financial "
        "hubs like UAE, Hong Kong, and Singapore draw Mercury-driven natives who thrive in "
        "trade, analytics, IT, and finance roles."
    ),
    "Jupiter": (
        "Jupiter rules the northeast direction and prosperity. Countries with strong "
        "educational institutions, rule of law, and high living standards — USA, Canada, "
        "Australia — are classically Jupiterian. The native typically goes to advance "
        "knowledge, teach, or join a major institution."
    ),
    "Venus": (
        "Venus governs the southeast direction and luxury. Western Europe, the UAE, "
        "and the USA — centres of art, culture, and high consumption — align with Venusian "
        "energy. The native often finds beauty, comfort, and strong material rewards."
    ),
    "Saturn": (
        "Saturn rules the west and karmic, disciplined environments. The UK, USA, "
        "and Germany — mature industrial economies — draw Saturn's energy. The native "
        "earns steadily but must invest sustained effort over many years."
    ),
    "Rahu": (
        "Rahu has no fixed direction — it pulls toward the exotic and unconventional. "
        "Southeast Asia (Malaysia, Thailand, Singapore), the Americas, and emerging "
        "markets are typical Rahu destinations. The native breaks all expected patterns "
        "and thrives precisely because the environment is unfamiliar."
    ),
    "Ketu": (
        "Ketu is associated with the southeast and spiritual renunciation. Its destinations "
        "tend to be spiritually significant, or the native may return from abroad after "
        "a Ketu period — Ketu dissolves attachment to places."
    ),
}

# ── Action step templates per duration type ────────────────────────────────
_FOP_ACTION_STEPS: Dict[str, List[str]] = {
    "SHORT_TRIP": [
        "Identify 2–3 target companies or clients in the geo-affinity region and begin outreach 60 days before the window opens.",
        "Renew or obtain a visa for the target region before the window starts — avoid last-minute delays.",
        "Book exploratory or networking trips in the first half of the window while planetary energy is building.",
        "Carry updated work samples, certificates, and a compact professional portfolio for in-person meetings abroad.",
        "Use the PD (sub-sub-period) trigger dates as your primary scheduling anchor for key decisions.",
    ],
    "ASSIGNMENT": [
        "Begin conversations with your current employer about secondment or relocation options 3–4 months before the window.",
        "Update LinkedIn and resume for an international audience; highlight cross-cultural work, languages, and remote collaboration.",
        "Research work authorisation (visa/work permit) requirements for the geo-affinity region — timelines vary by country.",
        "Identify and contact 5–7 hiring managers or recruiters specialising in the target geography.",
        "Lock in the negotiation of the assignment package (housing, travel, tax equalisation) during the peak trigger window dates.",
        "Plan for a spouse or family's needs in the destination country to remove personal obstacles to relocation.",
    ],
    "RELOCATION": [
        "Start the immigration or work-visa process now — long-term relocation windows require 6–18 months of document preparation.",
        "Build financial reserves for a 6-month transition buffer; property rental, school fees, and initial set-up costs are higher than expected.",
        "Network actively with diaspora communities from your target country — they provide the most practical recent advice.",
        "Consider a short scouting trip 6–8 months before the window's midpoint to evaluate neighbourhoods, schools, and lifestyle.",
        "Inform your current employer of your aspirations early so they can offer a transfer rather than losing you to a competitor.",
        "Consult a cross-border tax advisor before accepting any international package — dual taxation can erode significant income.",
        "Align the final acceptance or lease-signing with the best trigger sub-period dates within this window.",
    ],
    "LONG_TERM_ABROAD": [
        "Treat this as a permanent life chapter — make long-term decisions about property, family base, and children's education abroad.",
        "Begin the permanent residency or citizenship pathway research for your target country.",
        "Invest in language or cultural immersion if the destination has a non-English professional environment.",
        "Diversify financial assets across home and host country currencies to reduce exchange-rate risk over a multi-year stint.",
        "Build a strong local professional network within the first 12 months — international success depends heavily on local relationships.",
        "Revisit your original industry position: long MD-level foreign stints often create an opportunity to shift into a senior or niche role.",
    ],
    # Conservative action set for periods downgraded from ASSIGNMENT to
    # FOREIGN_LINKED because onsite/relocation manifestation scores were too
    # low (2026-07-07 fix). Previously this duration key had no dedicated
    # entry and silently fell back to SHORT_TRIP's action text (visa renewal,
    # exploratory trips) — inappropriate advice for a period the engine has
    # explicitly flagged as having "no confirmed onsite/relocation signal".
    # Deliberately excludes visa/relocation-package/family-relocation advice.
    "FOREIGN_LINKED": [
        "Build visibility with global stakeholders, clients, or leadership through your current role — no physical move is indicated by this period's chart signals.",
        "Seek cross-border project ownership, timezone-overlapping collaboration, or a global account/portfolio assignment from your current base.",
        "Document delivery impact for global or multinational engagements — this evidence strengthens a promotion or scope-expansion case even without relocation.",
        "If an employer-initiated onsite or relocation opportunity arises independently, revisit relocation-specific planning at that point — do not pursue it proactively based on this reading alone.",
    ],
}

# Gap fix (2026-07-08, issue #6): the Venus foreign-opportunity narrative was
# generic hospitality/fashion/entertainment boilerplate regardless of the
# native's actual career context. When the chart's career_ctx indicates a
# software/technology/IT industry and/or a senior-manager+ management track
# (same `_derive_career_track` == "management" classification used
# elsewhere in this module), Venus is instead narrated through its actual
# significations relevant to that context — stakeholder diplomacy,
# client-facing polish, global collaboration, executive relationship
# management — rather than the unrelated luxury-industry text. Non-software/
# MNC contexts (or when career_ctx is unavailable) keep the original generic
# text unchanged, so this is additive, not a removal of prior content.
_SOFTWARE_MNC_INDUSTRY_KEYWORDS = (
    "software", "technology", "tech", "it", "information technology",
    "saas", "computer", "mnc",
)


def _is_software_mnc_context(career_ctx: Optional[Dict[str, Any]]) -> bool:
    """True when career_ctx indicates a software/technology/MNC senior context.

    Gated on the SAME `industry_sector` and `_derive_career_track` signals
    already used elsewhere in this file (see _get_macro_score/_derive_career_track)
    — no new astrological or profile input is introduced here.
    """
    if not career_ctx:
        return False
    sector = str(career_ctx.get("industry_sector", "") or "").lower()
    _sector_hit = any(kw in sector for kw in _SOFTWARE_MNC_INDUSTRY_KEYWORDS)
    _track = _derive_career_track(career_ctx)
    _senior_desig = str(career_ctx.get("designation", "") or "").lower()
    _senior_hit = _track == "management" or any(
        kw in _senior_desig for kw in ("senior_manager", "senior manager", "director", "vp", "csuite", "c-suite", "head")
    )
    return _sector_hit or _senior_hit


_FOP_VENUS_SOFTWARE_MNC_WHY = (
    "Venus supports stakeholder diplomacy, client-facing polish, global collaboration, "
    "executive relationship management, and comfort/benefit improvement within MNC "
    "technology environments. Foreign-linked opportunities under Venus in this context "
    "typically surface through client-facing roles, cross-border partnership management, "
    "or executive-level relationship building with global stakeholders, rather than a "
    "lifestyle-industry posting."
)


def _fop_planet_why(planet: str, career_ctx: Optional[Dict[str, Any]] = None) -> str:
    """Context-aware wrapper around _FOP_PLANET_WHY — see _is_software_mnc_context()."""
    if planet == "Venus" and _is_software_mnc_context(career_ctx):
        return _FOP_VENUS_SOFTWARE_MNC_WHY
    return _FOP_PLANET_WHY.get(planet, f"{planet} rules this period.")


# ── Risk factor templates ───────────────────────────────────────────────────
_FOP_RISK_FACTORS: Dict[str, List[str]] = {
    "Rahu": [
        "Rahu periods can bring sudden reversals near their end — secure the foreign role in the first two-thirds of the window.",
        "Over-ambition is a Rahu pitfall; ensure the target role or country is genuinely suited to your qualifications, not just aspirationally attractive.",
    ],
    "Ketu": [
        "Ketu creates isolation and introversion; overseas postings during Ketu require strong emotional support networks to avoid disillusionment.",
        "Ketu periods can end foreign stints abruptly — do not enter a long-term lease or mortgage if the window ends within 18 months.",
    ],
    "Saturn": [
        "Saturn's foreign periods begin slowly; the first 6 months abroad may feel grinding before results appear — persist.",
        "Health and fatigue can be Saturn vulnerabilities in cold or high-pressure environments — build rest into the plan.",
    ],
    "Jupiter": [
        "Over-confidence is a Jupiter risk — do thorough due diligence on the employer or institution before relocating.",
        "Jupiter abroad can create ethical friction if the host-country work culture conflicts with the native's values.",
    ],
    "Venus": [
        "Overspending and lifestyle inflation are Venus risks in luxury destinations — set a budget ceiling early.",
        "Relationship complications (long-distance or relocation of partner) need explicit planning during Venus windows.",
    ],
    "Moon": [
        "Emotional homesickness can be acute during Moon periods abroad; schedule regular contact with family and familiar communities.",
        "Moon periods are prone to frequent changes of plan — commit early and avoid re-deciding after the window starts.",
    ],
    "Mercury": [
        "Communication misunderstandings in a cross-cultural setting are amplified during Mercury periods — invest in cultural training.",
        "Mercury's restlessness can cause premature return; stay for the full planned duration to realise the gains.",
    ],
    "Sun": [
        "Ego clashes with foreign authority figures or government contacts are a Sun risk — adopt humility in a new hierarchy.",
        "Government-driven postings can be cancelled or changed with little notice — have a Plan B opportunity identified.",
    ],
    "Mars": [
        "Conflict with colleagues or management is a Mars risk in competitive foreign environments — channel energy constructively.",
        "Impulsive decisions about accepting or leaving the role can undermine an otherwise strong Mars foreign window.",
    ],
}

_FOP_GENERIC_RISKS: List[str] = [
    "Any malefic transit (Saturn or Mars) over the natal lagna or 12th-house lord during this window can delay or complicate the departure.",
    "Papakartari yoga (malefics flanking the active house) reduces the cleanness of the foreign outcome — check the natal chart carefully.",
    "Family obligations or elderly-parent responsibilities at home are the most common non-astrological blockers; plan support structures.",
]


# Gap fix (2026-07-08, issue #5): the Rahu/dasha-lord action-step advice was
# relocation-heavy by default (visa renewal, exploratory trips, "identify
# foreign companies") even for periods where the manifestation-score gating
# elsewhere in this module (manifestation_scores["relocation"] /
# ["onsite_assignment"] vs. _FOREIGN_MANIF_MIN, see _score_foreign_period)
# has NOT actually confirmed relocation — i.e. exactly the same
# "short-trip/foreign-linked-exposure vs. confirmed relocation" distinction
# the FOREIGN_LINKED duration bucket was introduced for on 2026-07-07.
# Rather than deleting relocation-specific advice outright (some charts DO
# show a genuinely confirmed relocation signal and should keep it), gate the
# Rahu-period advice on that same signal: only the confirmed-relocation case
# (duration in {"RELOCATION", "LONG_TERM_ABROAD"} OR the onsite/relocation
# manifestation sub-scores clear _FOREIGN_MANIF_MIN) keeps the bold
# "apply to unconventional/international-first companies" + visa/relocation
# framing; every other case gets the softened, non-relocation advice.
_FOP_RAHU_CONFIRMED_RELOCATION_STEP = (
    "Rahu is your dasha lord — be bold, apply to unconventional or international-first "
    "companies that you would normally consider 'out of reach'."
)
_FOP_RAHU_EXPOSURE_ONLY_STEP = (
    "Rahu is your dasha lord — channel its boundary-breaking energy into prioritizing "
    "global clients, offshore/onsite matrix exposure, and ownership of an AI/automation "
    "transformation initiative; build international stakeholder relationships from your "
    "current base. Do not proactively relocate unless an employer/institutional trigger "
    "arises independently — this period's chart signals support global exposure, not a "
    "confirmed physical move."
)


def _fop_derive_action_steps(
    duration: str, md_lord: str, ad_lord: str,
    manifestation_scores: Optional[Dict[str, float]] = None,
) -> List[str]:
    """Return 5-7 concrete action steps for the given duration type."""
    steps = list(_FOP_ACTION_STEPS.get(duration, _FOP_ACTION_STEPS["SHORT_TRIP"]))
    _ms = manifestation_scores or {}
    _confirmed_relocation = (
        duration in ("RELOCATION", "LONG_TERM_ABROAD")
        or _ms.get("relocation", 0.0) >= _FOREIGN_MANIF_MIN
        or _ms.get("onsite_assignment", 0.0) >= _FOREIGN_MANIF_MIN
    )
    # Planet-specific prepend
    for p in (ad_lord, md_lord):
        if p == "Rahu":
            steps.insert(0, _FOP_RAHU_CONFIRMED_RELOCATION_STEP if _confirmed_relocation
                         else _FOP_RAHU_EXPOSURE_ONLY_STEP)
            break
        if p == "Jupiter":
            steps.insert(0, "Jupiter's expansive energy rewards formal applications to universities, research bodies, and large institutions abroad.")
            break
        if p == "Saturn":
            steps.insert(0, "Saturn rewards persistence — begin the foreign application process early and expect a 6–12 month gestation before offers materialise.")
            break
    return steps[:7]


def _fop_derive_risk_factors(md_lord: str, ad_lord: str) -> List[str]:
    """Return combined risk factors for the two active lords."""
    risks: List[str] = []
    seen: set = set()
    for p in (md_lord, ad_lord):
        for r in _FOP_RISK_FACTORS.get(p, []):
            if r not in seen:
                seen.add(r)
                risks.append(r)
    risks.extend(_FOP_GENERIC_RISKS)
    return risks[:5]


def _fop_build_planetary_story(
    md_lord: str, ad_lord: str, breakdown: List[Dict], duration: str, geo: str,
    foreign_score: Optional[float] = None,
    transit_data_available: bool = True,
    career_ctx: Optional[Dict[str, Any]] = None,
) -> str:
    """Compose a single narrative paragraph explaining this foreign window."""
    # Gap fix (2026-07-08, issue #6): use the context-aware Venus lookup so a
    # software/MNC senior-manager chart gets the MNC-specific Venus narrative
    # (see _fop_planet_why / _is_software_mnc_context above) instead of the
    # generic hospitality/fashion/entertainment text unconditionally.
    md_why   = _fop_planet_why(md_lord, career_ctx)
    ad_why   = _fop_planet_why(ad_lord, career_ctx)
    dur_text = _FOREIGN_DURATION_TYPE.get(duration, "international opportunity")
    house_hits = [b["label"] for b in breakdown if b["factor_group"] == "HOUSE_ACTIVE"]
    house_str = "; ".join(house_hits) if house_hits else "foreign houses are indirectly activated"
    transit_hits = [b["label"] for b in breakdown if b["factor_group"] == "TRANSIT"]
    if transit_hits:
        transit_str = f"Transit reinforcement: {'; '.join(transit_hits)}."
    elif not transit_data_available:
        transit_str = (
            "Transit layer is unavailable; foreign-linked potential is inferred only "
            "from dasha/house activation and must not be treated as transit-confirmed."
        )
    else:
        transit_str = "Transit planets provide indirect support."
    # Gap fix (2026-07-07): when the underlying foreign_score is low (weak
    # onsite/relocation signal), naming specific countries reads as a
    # confident relocation prediction it isn't. Soften to "may include" +
    # an explicit non-confirmation note in that case; keep the more direct
    # phrasing only when the score genuinely supports an assignment-tier
    # window.
    _geo_is_soft = isinstance(foreign_score, (int, float)) and foreign_score < 0.55
    if _geo_is_soft:
        geo_clause = (
            f"classical geo-affinity points toward {dur_text.lower()}-style environments such as "
            f"{geo} — these are illustrative regions based on the ruling planet's traditional "
            f"direction/geography, not a relocation prediction; physical relocation is not confirmed"
        )
    else:
        geo_clause = f"a {dur_text.lower()} with geo-affinity toward {geo}"
    story = (
        f"During this period {md_lord} runs as the major-period (MD) lord and {ad_lord} "
        f"as the sub-period (AD) lord. {md_why} {ad_why} "
        f"On the chart level, {house_str}. {transit_str} "
        f"The combined energy points toward {geo_clause}. This is a window where foreign-linked "
        f"opportunities become more accessible, without implying that relocation itself is "
        f"confirmed by the chart."
    )
    # Gap fix (2026-07-07): destination text is keyed purely off the dasha
    # lord's classical geo-affinity, not independently weighted by actual
    # 9th/12th cusp strength for this chart. The card itself is already
    # gated at foreign_score >= _FOREIGN_SCORE_THRESHOLD (0.35), but a score
    # only moderately above that threshold should not carry the same
    # confident destination-naming tone as a robustly high score. Use the
    # same >=0.55 "High" convention applied elsewhere in this codebase
    # (D10/KP confidence bucketing) for consistency.
    if isinstance(foreign_score, (int, float)) and foreign_score < 0.55:
        story += (
            " Note: this signal is moderate rather than strong — foreign/client-linked "
            "exposure is possible, but confirming an actual relocation would need stronger "
            "dedicated 9th/12th cusp, transit, and opportunity-context signals."
        )
    return story


def _score_foreign_period(
    block: Dict,
    chart: "TimelineChartInput",
    lagna_sign: str,
    today: Optional[date] = None,
    career_ctx: Optional[Dict[str, Any]] = None,
) -> Optional[Dict]:
    """Score one career block for foreign opportunity likelihood.

    Returns a structured dict if score >= _FOREIGN_SCORE_THRESHOLD, else None.
    The returned dict includes rich explanation fields for the standalone report.
    """
    md_lord  = block.get("md_lord", "")
    ad_lord  = block.get("ad_lord", "")
    hl       = chart.house_lords or {}
    ph       = chart.planet_house or {}
    transit  = chart.transit_house_positions or {}
    active_h = set(block.get("active_houses", []))

    score      = 0.0
    indicators: List[str] = []
    breakdown:  List[Dict] = []   # NEW — rich per-factor explanation

    # ── 1. Active house weights ─────────────────────────────────────────────
    _h_labels = {
        12: "H12 activated — foreign residence / emigration",
        9:  "H9 activated — long journeys / fortune abroad",
        3:  "H3 activated — short trips / neighboring countries",
        8:  "H8 activated — sudden/unexpected foreign transformation",
    }
    for _h, _label in _h_labels.items():
        if _h in active_h:
            _w = {12: 0.30, 9: 0.22, 3: 0.12, 8: 0.10}.get(_h, 0.0)
            score += _w
            indicators.append(_label)
            breakdown.append({"factor_group": "HOUSE_ACTIVE", "label": _label, "weight": _w})

    # ── 2. Planetary lord weights (Rahu/Ketu/Moon are classical foreign karakas) ──
    _lord_weights = {"Rahu": 0.25, "Ketu": 0.12, "Moon": 0.10, "Venus": 0.08,
                      "Mercury": 0.08, "Saturn": 0.06, "Jupiter": 0.10, "Mars": 0.05, "Sun": 0.04}
    for _p in (md_lord, ad_lord):
        _w = _lord_weights.get(_p, 0.0)
        if _w:
            score += _w
            _label = f"{_p} as dasha lord — classical foreign-travel signifier"
            indicators.append(_label)
            breakdown.append({"factor_group": "DASHA_LORD", "label": _label, "weight": _w})

    # ── 3. House lordship: does md/ad lord rule 3/9/12 (classical foreign houses)? ──
    for _p in (md_lord, ad_lord):
        _ruled = [int(h) for h, l in hl.items() if l == _p and str(h).isdigit()]
        _foreign_ruled = [h for h in _ruled if h in (3, 9, 12)]
        if _foreign_ruled:
            _w = 0.08 * len(_foreign_ruled)
            score += _w
            _label = f"{_p} rules house(s) {_foreign_ruled} — foreign-house lordship"
            indicators.append(_label)
            breakdown.append({"factor_group": "LORDSHIP", "label": _label, "weight": _w})

    # ── 4. Transit reinforcement: is md/ad lord transiting a foreign house now? ──
    for _p in (md_lord, ad_lord):
        _th = transit.get(_p)
        if _th in (3, 9, 12):
            _w = 0.05
            score += _w
            _label = f"{_p} transiting house {_th} — active foreign-window reinforcement"
            indicators.append(_label)
            breakdown.append({"factor_group": "TRANSIT", "label": _label, "weight": _w})

    score = round(min(1.0, score), 3)
    if score < _FOREIGN_SCORE_THRESHOLD:
        return None

    # ── Manifestation-type breakdown (Phase 3, 2026-07-05): does this window ──
    # manifest as relocation/settlement or as foreign-client/remote/onsite work?
    # Computed BEFORE duration selection (Fix C, 2026-07) so the duration/label
    # choice below can be gated on the actual onsite_assignment/relocation
    # sub-scores instead of relying purely on the generic blended `score`.
    _settlement_lords = {"Rahu": 0.35, "Saturn": 0.25, "Ketu": 0.10}
    _client_lords = {"Mercury": 0.30, "Venus": 0.20, "Jupiter": 0.15, "Moon": 0.15}
    manifestation_scores = {
        "relocation":              round(_settlement_lords.get(md_lord, 0.0) * 0.6 + _settlement_lords.get(ad_lord, 0.0) * 0.4, 3),
        "settlement":              round(_settlement_lords.get(ad_lord, 0.0) * 0.6 + _settlement_lords.get(md_lord, 0.0) * 0.4, 3),
        "foreign_client":          round(_client_lords.get(md_lord, 0.0) * 0.5 + _client_lords.get(ad_lord, 0.0) * 0.5, 3),
        "remote_global_delivery":  round(_client_lords.get(ad_lord, 0.0) * 0.6 + _client_lords.get(md_lord, 0.0) * 0.4, 3),
        "onsite_assignment":       round((_lord_weights.get(md_lord, 0.0) + _lord_weights.get(ad_lord, 0.0)) * 0.3, 3),
    }

    # ── Duration type: stronger scores / MD-level periods -> longer stints ──
    _is_md_level = bool(block.get("is_md_level"))
    _has_onsite_or_relocation_signal = (
        manifestation_scores["onsite_assignment"] >= _FOREIGN_MANIF_MIN
        or manifestation_scores["relocation"] >= _FOREIGN_MANIF_MIN
    )
    if score >= 0.80 and _is_md_level:
        duration = "LONG_TERM_ABROAD"
    elif score >= 0.65:
        duration = "RELOCATION"
    elif score >= 0.50:
        if _has_onsite_or_relocation_signal:
            duration = "ASSIGNMENT"
        else:
            # Generic blended score suggests an assignment-tier window, but
            # neither onsite_assignment nor relocation sub-scores support it
            # — downgrade to a conservative, non-committal label instead of
            # asserting "Foreign Assignment (3-18 months)" without evidence.
            duration = "FOREIGN_LINKED"
    else:
        duration = "SHORT_TRIP"

    # ── Geo affinity: driven by the stronger of md/ad lord's classical direction ──
    _geo_lord = md_lord if _lord_weights.get(md_lord, 0.0) >= _lord_weights.get(ad_lord, 0.0) else ad_lord
    geo_affinity = _GEO_AFFINITY_MAP.get(_geo_lord, "")
    geo_affinity_structured = _GEO_AFFINITY_STRUCTURED.get(_geo_lord, {})

    action_steps  = _fop_derive_action_steps(duration, md_lord, ad_lord, manifestation_scores=manifestation_scores)
    risk_factors  = _fop_derive_risk_factors(md_lord, ad_lord)
    # Same transit-data-availability check used for confidence-tier computation
    # (see `_transit_data_available` in _build_career_timeline) — reused here so
    # the planetary-story fallback text is honest about whether transit data
    # actually exists for this chart.
    _transit_data_available = bool(
        (getattr(chart, "transit_house_positions", None) or {})
        or (getattr(chart, "planet_transit_degrees", None) or {})
    )
    planetary_story = _fop_build_planetary_story(
        md_lord, ad_lord, breakdown, duration, geo_affinity, foreign_score=score,
        transit_data_available=_transit_data_available,
        career_ctx=career_ctx,
    )

    return {
        "md_lord":                  md_lord,
        "ad_lord":                  ad_lord,
        "start_date":               block.get("start_date", ""),
        "end_date":                 block.get("end_date", ""),
        "foreign_score":            score,
        "indicators":               indicators,
        "breakdown":                breakdown,
        "duration_type":            duration,
        "duration_label":           _FOREIGN_DURATION_TYPE.get(duration, "International opportunity"),
        "geo_affinity":             geo_affinity,
        "geo_affinity_structured":  geo_affinity_structured,
        "geo_affinity_why":         _FOP_GEO_WHY.get(_geo_lord, ""),
        "manifestation_scores":     manifestation_scores,
        "action_steps":             action_steps,
        "risk_factors":             risk_factors,
        "planetary_story":          planetary_story,
    }


def _compute_foreign_module(
    blocks: List[Dict],
    chart: "TimelineChartInput",
    lagna_sign: str,
    today: Optional[date] = None,
    career_ctx: Optional[Dict[str, Any]] = None,
) -> List[Dict]:
    """Run `_score_foreign_period` over every timeline block and collect the
    windows that clear `_FOREIGN_SCORE_THRESHOLD`. This is the single
    entry point `_build_career_timeline` calls (see the `_foreign_opps =
    _compute_foreign_module(...)` call site) — kept as a thin wrapper so the
    per-block scoring logic in `_score_foreign_period` stays independently
    testable.
    """
    results: List[Dict] = []
    for _block in blocks:
        _opp = _score_foreign_period(_block, chart, lagna_sign, today=today, career_ctx=career_ctx)
        if _opp is not None:
            results.append(_opp)
    results.sort(key=lambda o: o.get("foreign_score", 0.0), reverse=True)
    return results


# RECONSTRUCTION NOTE (2026-07-07): _PLANET_REMEDY (referenced by
# _build_remedies() immediately below) was found missing entirely — same
# corruption pattern documented at other reconstruction points this
# session. Standard, generic classical remedy suggestions per planet
# (mantra + one practical/charitable action), not chart-specific — this is
# the same LEVEL of remedy content already visible elsewhere in this
# codebase's conservative, non-prescriptive tone (see _EVENT_ACTIONS in
# jyotish/web_report.py for the equivalent "short, practical, non-alarmist"
# convention used for event-type actions).
_PLANET_REMEDY: Dict[str, str] = {
    "Sun":     "Offer water to the rising sun (Surya Arghya) and recite the Aditya Hridayam or Gayatri mantra on Sundays.",
    "Moon":    "Recite the Chandra mantra on Mondays and maintain emotional steadiness through meditation or journaling.",
    "Mars":    "Recite the Hanuman Chalisa on Tuesdays and channel excess drive into disciplined physical exercise.",
    "Mercury":  "Recite Vishnu Sahasranama or the Budha mantra on Wednesdays; keep communication clear and written where possible.",
    "Jupiter": "Recite the Guru mantra on Thursdays and consult a mentor or teacher before major career decisions this period.",
    "Venus":   "Recite the Shukra mantra on Fridays and prioritize fair, transparent dealings in partnerships or negotiations.",
    "Saturn":  "Recite the Shani mantra or Hanuman Chalisa on Saturdays; maintain discipline and avoid shortcuts during this period.",
    "Rahu":    "Recite the Durga or Rahu mantra; avoid impulsive, high-risk decisions and verify unfamiliar opportunities carefully.",
    "Ketu":    "Recite the Ganesha or Ketu mantra; ground ambition with practical planning rather than pure intuition.",
}


def _build_remedies(event_type: str, md_lord: str, ad_lord: str) -> List[str]:
    """Return 1-2 remedies relevant to this period's planets."""
    remedies: List[str] = []
    if event_type in ("RISK_PERIOD", "AUTHORITY_SHIFT", "CALIBRATION"):
        for p in (md_lord, ad_lord):
            r = _PLANET_REMEDY.get(p)
            if r and r not in remedies:
                remedies.append(r)
    else:
        r = _PLANET_REMEDY.get(md_lord)
        if r:
            remedies.append(r)
    return remedies[:2]


_MACRO_INDEX: Dict[str, float] = {
    "technology": 1.1, "software": 1.1, "it": 1.05, "finance": 1.0,
    "healthcare": 1.05, "consulting": 0.95, "manufacturing": 0.9,
    "real_estate": 0.85, "retail": 0.85, "media": 0.9, "education": 0.95,
    "energy": 0.95, "logistics": 0.9, "government": 1.0, "pharma": 1.05,
    "_default": 0.95,
}
_MACRO_HEADWIND_THRESHOLD = 0.7


def _get_macro_score(industry_sector: str, career_ctx: Dict[str, Any]) -> float:
    """Return current macro health score for the given sector."""
    if career_ctx:
        _override = career_ctx.get("macro_override")
        if _override is not None:
            try:
                return float(_override)
            except (TypeError, ValueError):
                pass
    try:
        import pathlib
        import json as _json
        _cfg_file = pathlib.Path(__file__).with_name("macro_config.json")
        _idx = _MACRO_INDEX
        if _cfg_file.exists():
            _loaded = _json.loads(_cfg_file.read_text(encoding="utf-8"))
            if isinstance(_loaded.get("sectors"), dict):
                _idx = _loaded["sectors"]
        sector_key = str(industry_sector or "").lower().replace(" ", "_").replace("-", "_")
        if _idx.get(sector_key):
            return _idx.get(sector_key)
        return next(
            (v for k, v in _idx.items() if sector_key.startswith(k[:4]) and k != "_default"),
            _idx.get("_default", 0.9),
        )
    except Exception:
        return _MACRO_INDEX.get("_default", 0.9)


_SUN_DAYS_PER_SIGN = 30
_MARS_DAYS_PER_SIGN = 45
_JUPITER_DAYS_PER_SIGN = 365


def _find_trigger_window(pd_start, pd_end, chart: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """Find the peak-probability activation window within a Pratyantardasha."""
    h10_lord = (getattr(chart, "house_lords", {}) or {}).get("10", "")
    amk = getattr(chart, "amatyakaraka", "") or ""
    planet_house = getattr(chart, "planet_house", {}) or {}
    target_houses = []
    for p in (h10_lord, amk):
        h = planet_house.get(p, 0)
        if h:
            target_houses.append(h)
    if not target_houses:
        return {"trigger_planet": None, "trigger_start": None, "trigger_end": None, "trigger_note": ""}

    transit_snap = getattr(chart, "transit_house_positions", {}) or {}
    best = {"trigger_planet": None, "trigger_start": None, "trigger_end": None, "trigger_note": ""}
    _trigger_planets = [("Jupiter", _JUPITER_DAYS_PER_SIGN), ("Sun", _SUN_DAYS_PER_SIGN), ("Mars", _MARS_DAYS_PER_SIGN)]

    for planet, days_per_sign in _trigger_planets:
        current_h = transit_snap.get(planet, 0)
        if not current_h:
            continue
        for target_h in target_houses:
            # RECONSTRUCTION NOTE (2026-07-07): this loop body (and the
            # function's final `return best`) were found missing at the
            # source-file level — the .py file itself ended mid-statement
            # right after this `for target_h in target_houses:` line, the
            # same "corruption pattern" documented elsewhere in this module
            # (see jyotish/web_report.py's generate_career_timeline_report()
            # reconstruction note for the fuller account). No prior complete
            # copy of this function's tail exists in any readable bytecode
            # cache. This is a clean-room completion consistent with the
            # function's own docstring ("Find the peak-probability
            # activation window within a Pratyantardasha") and the transit-
            # distance variables (days_per_sign) already set up above:
            # estimate how many whole-sign steps the trigger planet is from
            # the target house, convert that to a day offset using the
            # planet's own transit speed, and clamp the resulting window to
            # the Pratyantardasha's own [pd_start, pd_end] bounds so this
            # never claims a trigger date outside the period being described.
            house_distance = (target_h - current_h) % 12
            if house_distance == 0:
                house_distance = 12  # already conjunct this cycle; next hit is a full cycle away
            days_to_trigger = house_distance * days_per_sign
            if today is not None:
                candidate_start = today + timedelta(days=days_to_trigger)
            else:
                candidate_start = pd_start + timedelta(days=days_to_trigger) if isinstance(pd_start, date) else pd_start
            if not isinstance(candidate_start, date):
                continue
            # Clamp into the Pratyantardasha window; skip if the estimated
            # trigger falls entirely outside this sub-period.
            if candidate_start < pd_start or candidate_start > pd_end:
                continue
            candidate_end = min(candidate_start + timedelta(days=max(7, days_per_sign // 4)), pd_end)
            if best["trigger_start"] is None or candidate_start < best["trigger_start"]:
                best = {
                    "trigger_planet": planet,
                    "trigger_start": candidate_start,
                    "trigger_end": candidate_end,
                    "trigger_note": (
                        f"{planet} transits house {target_h} (~{house_distance} sign-steps from "
                        f"its current position) — estimated peak-activation window within this "
                        f"Pratyantardasha."
                    ),
                }

    return best


def compute_d10_pivot_radar(dasha_sequence: List[Dict], d10_house_lords: Dict[str, str],
                             eff_strengths: Dict[str, float], today: Optional[date] = None) -> Dict[str, Any]:
    """C-1: "D10 Pivot Radar" — flags upcoming Mahadasha lords whose D10
    (Dashamsha) house lordship signals a corporate/entrepreneurial pivot
    point (a change in the STRUCTURAL nature of the career, not just a
    score change).

    RECONSTRUCTION NOTE (2026-07-07): this function was found entirely
    MISSING from the source file even though jyotish/__init__.py imports it
    unconditionally (breaking every import of the `jyotish` package) and
    jyotish/engine.py calls it (wrapped in try/except, so that one call site
    alone would have silently no-op'd, masking the missing-function problem
    there). No readable bytecode cache exists anywhere in this repo for this
    exact symbol (only cpython-3.12/3.14 caches survive for this module,
    and this environment's Python 3.10 cannot parse their marshal format),
    so unlike compute_aptitude_by_domain()/_load_course_registry() in
    jyotish/engine_io.py (recovered by disassembling a readable 3.10 cache),
    this one could not be recovered byte-for-byte. This is therefore a
    clean-room implementation, built strictly from: (a) the function's own
    call-site usage in engine.py (exact parameter names/types, and that its
    result is stored as one dict under "d10_pivot_radar"), and (b) its own
    name/docstring convention ("Pivot Radar" = flags UPCOMING dasha changes
    with D10 structural significance) — no invented astrological doctrine
    beyond reading the same d10_house_lords facts this module already
    computes/receives elsewhere (see d10_house_lords usage throughout
    build_career_timeline() above).
    """
    result: Dict[str, Any] = {"upcoming_pivots": [], "note": ""}
    try:
        if not dasha_sequence or not d10_house_lords:
            return result
        _today = today or date.today()

        # A Mahadasha lord is a "D10 pivot" candidate if that same planet
        # rules the D10 1st (identity/self), 7th (partnership/business), or
        # 10th (career/authority) house — i.e. its arrival restructures how
        # career identity/authority/partnership manifest in the D10 chart,
        # not merely a strength change.
        _pivot_houses = {"1": "identity/self-employment pivot",
                          "7": "partnership/business-structure pivot",
                          "10": "career-authority/role-structure pivot"}
        _lord_to_pivot_houses: Dict[str, List[str]] = {}
        for h, lord in (d10_house_lords or {}).items():
            if str(h) in _pivot_houses and lord:
                _lord_to_pivot_houses.setdefault(lord, []).append(str(h))

        if not _lord_to_pivot_houses:
            return result

        for md in dasha_sequence:
            _lord = md.get("md_planet") or md.get("lord") or md.get("planet", "")
            if not _lord or _lord not in _lord_to_pivot_houses:
                continue
            _start = None
            _end = None
            if md.get("start_date"):
                _start = parse_iso_date(str(md.get("start_date"))[:10])
            if md.get("end_date"):
                _end = parse_iso_date(str(md.get("end_date"))[:10])
            if _end and _end < _today:
                continue   # already past — not "upcoming"
            _strength = float((eff_strengths or {}).get(_lord, 1.0) or 1.0)
            _houses = _lord_to_pivot_houses[_lord]
            _themes = [_pivot_houses[h] for h in _houses]
            result["upcoming_pivots"].append({
                "md_lord": _lord,
                "d10_houses_ruled": _houses,
                "pivot_themes": _themes,
                "strength": round(_strength, 3),
                "start_date": _start.isoformat() if _start else md.get("start_date", ""),
                "end_date": _end.isoformat() if _end else md.get("end_date", ""),
            })

        if result["upcoming_pivots"]:
            result["note"] = (
                f"{len(result['upcoming_pivots'])} upcoming Mahadasha period(s) carry D10 "
                "structural-pivot significance (identity/partnership/authority restructuring), "
                "not merely a strength change."
            )
    except Exception:
        pass
    return result
