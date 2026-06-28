"""JyotishAI — Career Timeline Engine (Job Professionals Only).

Fully deterministic: Python computes all period boundaries, scores,
transit flags, event classifications, and confidence tiers.
The LLM receives a pre-structured block and writes only the narrative prose.

Public entry points:
    TimelineChartInput           -- dataclass of all chart fields required
    TimelineChartInput.from_payload(payload) -- factory from NatalPayloadV2
    build_career_timeline(chart, eff_strengths, career_ctx, mode) -> List[Dict]

Returns a list of PeriodBlock dicts sorted by start_date.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field as dc_field
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Optional, Any, Tuple

from .constants import (
    _VIMSHOTTARI_YEARS, _VIMSHOTTARI_ORDER,
    _FUNCTIONAL_NATURE, _JOB_KARAKA_WEIGHTS,
    _JOB_HOUSE_ROLE, _DESIGNATION_LEVELS,
    _SIGN_LORD, _NAKSHATRA_LORD,
)
from .timeline_inputs import parse_iso_date, _RETRO_MATCH_DAYS
from .astro_enhancer import (
    AstroEnhancer, EnhancerInput, EnhancerResult,
    build_enhancer_input_from_payload, enhancer_score_delta,
    _jupiter_aspect_houses_set, _saturn_aspect_houses_set, _mars_aspect_houses,
)


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
    # D9 Navamsha planet dignities — needed for d9_modifier in _score_period
    # Without this field the D9 modifier is always 0.0 (G1 fix)
    d9_planet_dignities: dict = dc_field(default_factory=dict)  # {planet: "exalted"/"own"/"debilitated"/...}

    # Jaimini Arudha of H10 — public career image (used in Jaimini scoring)
    a10_sign: str = ""   # sign in which A10 falls (e.g. "Aries")

    @classmethod
    def from_payload(cls, payload) -> "TimelineChartInput":
        """Extract all timeline-relevant fields from a NatalPayloadV2 or compatible object."""
        jdata = (getattr(payload, "kn_rao_jaimini", None)
                 or getattr(payload, "kn_rao_jaimini_data", None)
                 or {})
        return cls(
            dob=getattr(payload, "dob", "") or "",
            lagna_sign=getattr(payload, "lagna_sign", "") or "",
            dasha_sequence=getattr(payload, "dasha_sequence", []) or [],
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
            planet_sign=getattr(payload, "planet_sign", {}) or {},
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
            # G1 fix: wire D9 dignities so d9_modifier is non-zero when data is present
            d9_planet_dignities=getattr(payload, "d9_planet_dignities", {}) or {},
            # Jaimini A10 (10th Arudha) sign — career image indicator
            a10_sign=getattr(payload, "a10_sign", "") or "",
        )


# -- Window constants ──────────────────────────────────────────────────────────
_WINDOW_PAST_MONTHS  = 12   # 1 year back
_WINDOW_FUTURE_YEARS = 4    # 4 years forward (allows up to 12 periods)
_MAX_OUTPUT_PERIODS  = 12   # cap on periods returned
# GAP 7 fix: stratified cooldown windows — each event tier has its own suppression duration.
_COOLDOWN_MONTHS_BY_TIER: Dict[str, int] = {
    "BREAKTHROUGH":         24,   # 24 months — rarest event, longest suppression
    "PROMOTION":            18,   # 18 months — title jumps cannot stack in quick succession
    "LEADERSHIP_EXPANSION": 12,   # 12 months — scope broadening, shorter cooldown
    "INCOME":                6,   # 6 months — salary events can recur on appraisal cycles
}

# ── Scoring weights ───────────────────────────────────────────────────────────
# GAP 1 fix: D10 Dashamsha added as an 8th weighted sub-score (0.08).
# Calibration v5: KP cusp raised 0.20→0.25; CA trimmed 0.22→0.20, SP 0.15→0.13,
# Jaimini 0.08→0.07 to keep primary-8 total at exactly 1.00.
_W_CAREER_ACTIVATION = 0.20   # trimmed 0.22→0.20 to fund KP v5 raise
_W_STRENGTH_PRODUCT  = 0.13   # trimmed 0.15→0.13 to fund KP v5 raise
_W_FUNCTIONAL_NATURE = 0.13   # unchanged
_W_HOUSE_ACTIVATION  = 0.10   # unchanged
_W_COMPANY_KARAKA    = 0.05   # unchanged
_W_KP_CUSP_SCORE     = 0.25   # Step 1 v5: 0.20 → 0.25
_W_JAIMINI_SCORE     = 0.07   # trimmed 0.08→0.07 to fund KP v5 raise
_W_D10_ALIGNMENT     = 0.07   # GAP 1: D10 Dashamsha career chart (unchanged)
# sum = 0.20+0.13+0.13+0.10+0.05+0.25+0.07+0.07 = 1.00 ✓

# ── Explicit yoga primary weights (Steps 2 & 3 calibration v5) ───────────────
# Named additive components outside the 8-weight primary sum so Rajayoga and
# Viparita RY have dedicated weight constants visible to the calibration tool,
# rather than being lumped into the uncapped generic yoga_bonus bucket.
_W_YOGA_RAJAYOGA = 0.05    # Step 2: Rajayoga explicit named weight
_W_YOGA_VRY      = 0.03    # Step 3: Viparita Rajayoga explicit named weight

# ── KP house career-relevance weights (for house_activation sub-score) ────────
_HOUSE_CAREER_WEIGHT = {
    10: 1.0, 6: 0.9, 11: 0.8, 2: 0.7,
    1: 0.5, 3: 0.4, 9: 0.4, 12: 0.3,
    4: 0.2, 5: 0.2, 8: -0.3,   # H8 penalises
}

# ── Designation experience thresholds ────────────────────────────────────────
_DESIGNATION_MIN_EXP = {
    "junior": 0, "mid": 2, "senior": 4, "lead": 5,
    "manager": 6, "director": 10, "csuite": 15,
}

# ── MD-level career themes (for narrative generation) ────────────────────────
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
        md_lord  = md.get("md_planet") or md.get("lord", "")
        if not md_lord:
            continue
        # Support both key conventions: payload uses start_age/end_age
        _s = md.get("start_age") if md.get("start_age") is not None else md.get("age_start", 0)
        _e = md.get("end_age")   if md.get("end_age")   is not None else md.get("age_end",   0)
        md_start = _age_to_date(dob, float(_s or 0))
        md_end   = _age_to_date(dob, float(_e or 0))
        if md_start >= md_end:
            continue

        # Expand antardashas
        sub = md.get("antardashas", [])
        if sub:
            for ad in sub:
                ad_lord = ad.get("lord", "")
                if not ad_lord:
                    continue
                ad_start = _age_to_date(dob, float(ad.get("age_start", 0)))
                ad_end   = _age_to_date(dob, float(ad.get("age_end",   0)))
                result.append({
                    "md_lord": md_lord, "ad_lord": ad_lord,
                    "start_date": ad_start, "end_date": ad_end,
                    "md_start": md_start, "md_end": md_end,
                })
        else:
            # No antardasha data — compute proportionally
            result.extend(_expand_antardashas(md_lord, md_start, md_end))
    return result


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
    periods: List[Dict], today: date, past_months: int = _WINDOW_PAST_MONTHS
) -> List[Dict]:
    """Keep only periods overlapping [today-past_months, today+4yr]; clip boundaries.

    past_months defaults to _WINDOW_PAST_MONTHS (12) but build_career_timeline
    overrides it with the span of the user's actual career history so the LLM
    validator receives full retroactive coverage.
    """
    win_start = today - relativedelta(months=past_months)
    win_end   = today + relativedelta(years=_WINDOW_FUTURE_YEARS)
    result = []
    for p in periods:
        s, e = p["start_date"], p["end_date"]
        if e <= win_start or s >= win_end:
            continue
        clipped = dict(p)
        clipped["start_date"] = max(s, win_start)
        clipped["end_date"]   = min(e, win_end)
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
    return min(1.0, raw / _MAX_POSSIBLE) if raw > 0 else 0.0


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

def _score_period(
    p: Dict,
    payload: Any,
    eff_strengths: Dict[str, float],
    career_ctx: Dict[str, Any],
    lagna_sign: str,
    detected_yogas: Optional[Dict[str, str]] = None,
    weight_overrides: Optional[Dict[str, float]] = None,
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

    # 5d. D9 Navamsha cross-validation — dignity of MD/AD lord in D9
    # Exalted/own sign → boost 0.06; debilitated → penalty -0.04
    # G1 fix: read from the explicit field (not a missing payload attribute)
    d9_dignities = (getattr(payload, "d9_planet_dignities", None) or {}) or {}
    d9_modifier = 0.0
    for _pl in set([md_lord, ad_lord]):
        _dig = str(d9_dignities.get(_pl, "")).lower()
        if _dig in ("exalted", "own"):
            d9_modifier += 0.06
        elif _dig in ("debilitated", "fallen"):
            d9_modifier -= 0.04
    # Cap: +0.08 max boost, -0.06 max penalty
    d9_modifier = max(-0.06, min(0.08, d9_modifier))

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
            sav_total += float(sav_points.get(f"H{house}", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    sav_support = max(0.0, min(1.0, sav_total / 140.0))

    # 6. NEW: KP career-cusp sub-lord alignment
    kp_cusps = getattr(payload, "kp_cusps", {}) or {}
    kp_cusp_score = _kp_career_cusp_score(md_lord, ad_lord, kp_cusps)

    # 7. NEW: KN Rao Jaimini AmK/AK alignment
    jaimini_score, _jai_role = _jaimini_career_score(md_lord, ad_lord, payload)

    # ── FIX 2: SAV house-capacity multiplier ─────────────────────────────────
    # A house must have sufficient SAV bindus to deliver on its activation.
    # Iterate over active career houses and compute a capacity factor.
    sav_pts  = getattr(payload, "sav_points_houses", {}) or {}
    _sav_cap = 0.0
    _sav_n   = 0
    for _h in (10, 11, 2, 6):
        _raw_b = sav_pts.get(f"H{_h}", None)
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
            if _yplanet == md_l:
                yoga_bonus += _YOGA_SCORE_BOOST.get(_yname, 0.05)
            elif _yplanet == ad_l and not _same_lord:
                # AD lord only adds bonus if it's a different planet from MD lord
                yoga_bonus += _YOGA_SCORE_BOOST.get(_yname, 0.05) * 0.6
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
            transit_projected={},   # populated later in _get_dynamic_transits
            md_change_dates=[],     # populated from build_career_timeline if available
            ad_change_dates=[],
        )
        _enh_result: Optional[EnhancerResult] = AstroEnhancer.run(_enh_inp)
        _enh_delta  = enhancer_score_delta(_enh_result)
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
    )

    _enh_dict: Dict = {}
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
            "kp_ruling_planets_score":round(_enh_result.kp_ruling_planets_score, 3),
            "kp_nakshatra_chain":     round(_enh_result.kp_nakshatra_chain_score, 3),
            "d10_full_score":         round(_enh_result.d10_full_score, 3),
            "d60_modifier":           round(_enh_result.d60_modifier, 3),
            "d27_modifier":           round(_enh_result.d27_modifier, 3),
            "surya_lagna_bonus":      round(_enh_result.surya_lagna_bonus, 3),
            "arudha_bonus":           round(_enh_result.arudha_bonus, 3),
            "karakamsha_bonus":       round(_enh_result.karakamsha_bonus, 3),
            "pav_transit_score":      round(_enh_result.pav_transit_score, 3),
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
        ]
    _fired = [name for name, val in _factor_vals if abs(val) > 0.005]

    return {
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
        "career_score":             round(min(1.0, combined),        3),
        "yoga_bonus":               round(yoga_bonus,                3),
        "yoga_rajayoga_sub":        round(yoga_rajayoga_sub,         3),
        "yoga_vry_sub":             round(yoga_vry_sub,              3),
        "d9_modifier":              round(d9_modifier,               3),
        "chandra_lagna_bonus":      round(chandra_bonus,             3),
        "active_yogas":             list(detected_yogas.keys()) if detected_yogas else [],
        "d24_skill_bonus":          round(d24_skill_bonus,           3),
        "pd_lord_boost":            round(_pd_boost,                 3),  # GAP 5
        "fired_g_factors":          _fired,                                # GAP 4
        **_enh_dict,
    }



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
    "Rajayoga_H1H4":    0.11,  # raised from 0.08
    "Rajayoga_H1H7":    0.09,  # raised from 0.07
    "Dhana_Yoga":       0.08,
    "Harsha_VRY":       0.09,
    "Sarala_VRY":       0.09,
    "Vimala_VRY":       0.08,
    "Adhi_Yoga":        0.10,
    "Chamara_Yoga":     0.09,
    "Amala_Yoga":       0.07,
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

def _overlay_transits(
    p: Dict,
    payload: Any,
    lagna_sign: str,
) -> List[str]:
    """Return list of transit flag strings for a CURRENT period (today's snapshot).

    G5 note: This function is NOT called in the main build_career_timeline pipeline.
    All periods (past, current, future) use _get_dynamic_transits() which handles
    current periods via the snapshot for days_ahead<=0 and projected positions for
    future periods.  This function is retained as a utility for testing/standalone
    use only.
    """
    flags = []
    transit_hp = getattr(payload, "transit_house_positions", {}) or {}
    natal_moon_house = (getattr(payload, "planet_house", {}) or {}).get("Moon", 0)

    # Jupiter transit rules
    jup_h = transit_hp.get("Jupiter", 0)
    if jup_h in (2, 5, 9, 10, 11):
        flags.append(f"JUPITER_H{jup_h}_EXPANSION")
    elif jup_h in (6, 8, 12):
        flags.append(f"JUPITER_H{jup_h}_STRESS")

    # Saturn transit rules
    sat_h = transit_hp.get("Saturn", 0)
    fn = _FUNCTIONAL_NATURE.get(lagna_sign, {})
    sat_fn = fn.get("Saturn", 0)
    if sat_h == 10:
        flags.append("SATURN_H10_AUTHORITY" if sat_fn >= 0 else "SATURN_H10_BURDEN")
    elif sat_h in (1, 2, 12) and natal_moon_house:
        # Sade Sati: Saturn transiting Moon±1
        if sat_h in _sade_sati_houses(natal_moon_house):
            phase = _sade_sati_phase(sat_h, natal_moon_house)
            flags.append(f"SADE_SATI_{phase}")
    if sat_h in (6, 8):
        flags.append(f"SATURN_H{sat_h}_DISRUPTION")

    # Rahu/Ketu axis
    rahu_h = transit_hp.get("Rahu", 0)
    if rahu_h in (1, 4, 7, 10):
        flags.append(f"RAHU_KETU_AXIS_MAJOR_CHANGE")

    # Jupiter aspecting natal H10 lord
    natal_h10_lord = (getattr(payload, "house_lords", {}) or {}).get("10", "")
    if natal_h10_lord and jup_h:
        natal_h10_lord_house = (getattr(payload, "planet_house", {}) or {}).get(natal_h10_lord, 0)
        if natal_h10_lord_house and jup_h in _jupiter_aspect_houses(natal_h10_lord_house):
            flags.append("JUPITER_ASPECTS_H10_LORD")

    # Saturn 3rd / 10th special aspects on natal H10 lord
    if natal_h10_lord and sat_h:
        if not natal_h10_lord_house:
            natal_h10_lord_house = (getattr(payload, "planet_house", {}) or {}).get(natal_h10_lord, 0)
        if natal_h10_lord_house and sat_h in _saturn_aspect_houses(natal_h10_lord_house):
            fn_sat = _FUNCTIONAL_NATURE.get(lagna_sign, {}).get("Saturn", 0)
            flags.append("SATURN_ASPECTS_H10_LORD_POSITIVE" if fn_sat >= 0 else "SATURN_ASPECTS_H10_LORD_STRESS")

    # Venus transit — salary / relationship gains
    venus_h = transit_hp.get("Venus", 0)
    if venus_h in (2, 11, 5):
        flags.append(f"VENUS_H{venus_h}_INCOME_GAIN")
    elif venus_h in (6, 8, 12):
        flags.append(f"VENUS_H{venus_h}_DISSATISFACTION")

    # Mars transit — initiative / conflict
    mars_h = transit_hp.get("Mars", 0)
    if mars_h == 10:
        flags.append("MARS_H10_CAREER_DRIVE")
    elif mars_h in (1, 3, 11):
        flags.append(f"MARS_H{mars_h}_INITIATIVE")
    elif mars_h in (6, 8, 12):
        flags.append(f"MARS_H{mars_h}_CONFLICT_RISK")

    return flags


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

    projected: dict = {}
    for planet, days_per_house in _DAYS_PER_HOUSE.items():
        current_h = snapshot_hp.get(planet, 0)
        if not current_h:
            continue
        houses_moved = days_ahead / days_per_house
        if planet in ("Rahu", "Ketu"):
            # Always retrograde
            new_h = int(((current_h - 1 - int(houses_moved)) % 12) + 1)
        elif planet in _retro_list:
            # GAP 2: currently retrograde — move backward until retrograde ends,
            # then resume prograde.  Net motion depends on days_ahead vs retro duration.
            _retro_dur = _RETRO_DURATION_DAYS.get(planet, 90)
            if days_ahead <= _retro_dur:
                # Still in retrograde phase at period midpoint
                new_h = int(((current_h - 1 - int(houses_moved)) % 12) + 1)
            else:
                # Retrograde ended: net = prograde days − retrograde houses
                _retro_houses = _retro_dur / days_per_house
                _fwd_houses   = (days_ahead - _retro_dur) / days_per_house
                _net = _fwd_houses - _retro_houses
                new_h = int(((current_h - 1 + max(0, int(_net))) % 12) + 1)
        else:
            new_h = int(((current_h - 1 + int(houses_moved)) % 12) + 1)
        projected[planet] = new_h

    # Now run the same flag logic as _overlay_transits but with projected positions
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

    # Venus — use snapshot for near-term periods (moves ~30°/month, unreliable to project)
    venus_snap_h = snapshot_hp.get("Venus", 0)
    if venus_snap_h and days_ahead <= 180:
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
            _muntha_house = ((mid.year - _dob_d.year) % 12) + 1
            _chart_hl = chart.house_lords or {}
            _muntha_lord = _chart_hl.get(str(_muntha_house), "")
            if _muntha_lord:
                flags.append(f"MUNTHA_H{_muntha_house}_LORD_{_muntha_lord.upper()}")
        except (ValueError, AttributeError):
            pass

    return flags


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

    # Dual kendra-trikona lordship (e.g., 9th + 10th lord same planet)
    for h_trik in (1, 5, 9):
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
    for benefic in ("Jupiter", "Venus", "Mercury", "Moon"):
        benefic_h = ph.get(benefic, 0)
        if benefic_h == 10:
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
    """Jupiter aspects 5th, 7th, 9th from itself (classical)."""
    return frozenset([
        ((house + 4) % 12) + 1,
        ((house + 6) % 12) + 1,
        ((house + 8) % 12) + 1,
    ])


def _saturn_aspect_houses(house: int) -> frozenset:
    """Saturn's special aspects: 3rd and 10th from itself."""
    return frozenset([
        ((house + 2) % 12) + 1,   # 3rd aspect
        ((house + 9) % 12) + 1,   # 10th aspect
    ])


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

    # ── CHALLENGE / RISK_PERIOD ───────────────────────────────────────────────
    has_sade_sati_peak = "SADE_SATI_PEAK" in flags
    if (fn < 0.3 or h8_active) and len(adverse_flags) >= 1:
        return ("RISK_PERIOD", sorted(active_h), near_miss)
    if has_sade_sati_peak and score < 0.45:
        return ("RISK_PERIOD", sorted(active_h), near_miss)

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

    # ── G31: SANDHI_PERIOD (Dasha Chidra) ────────────────────────────────────
    # G-A14 fix: flag ALL sandhi periods, not just low-score ones.
    # High-score sandhi blocks return the appropriate positive event BUT the
    # near_miss string is set to "SANDHI_VOLATILE" to warn of reversal risk.
    # Low-score sandhi blocks still resolve to SANDHI_PERIOD (unchanged).
    if scores.get("is_sandhi"):
        if score < 0.55:
            return ("SANDHI_PERIOD", sorted(active_h), near_miss)
        # High-score sandhi: positive event will be returned below, but annotate
        if not near_miss:
            near_miss = "SANDHI_VOLATILE — strong period but dasha junction; outcomes may reverse or delay"

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
    "join_date":           {"JOB_CHANGE", "RE_ENTRY", "TRANSITION", "LATERAL_MOVE"},
    "last_promotion_date": {"PROMOTION", "LEADERSHIP_EXPANSION", "BREAKTHROUGH"},
    "last_hike_date":      {"SALARY_HIKE", "INCOME_INFLECTION", "GROWTH", "EQUITY_EVENT"},
    # career_events[] list uses these mappings:
    "PROMOTION":           {"PROMOTION", "BREAKTHROUGH", "LEADERSHIP_EXPANSION"},
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
}


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

    def _check_actual(actual_d: date, valid_types: set) -> bool:
        nonlocal matches
        for p in periods:
            pid = id(p)
            if pid in matched_period_ids:
                continue
            if p.get("event_type") not in valid_types:
                continue
            _sd = p["start_date"]
            _ed = p["end_date"]
            if isinstance(_sd, str):
                _sd = parse_iso_date(_sd) or actual_d
            if isinstance(_ed, str):
                _ed = parse_iso_date(_ed) or actual_d
            mid = _sd + (_ed - _sd) / 2
            if abs((actual_d - mid).days) <= _RETRO_MATCH_DAYS:
                matched_period_ids.add(pid)
                matches += 1
                return True
        return False

    # 1. Legacy 3-field check
    legacy_pairs = [
        ("join_date",           _EVENT_TYPE_GROUPS["join_date"]),
        ("last_promotion_date", _EVENT_TYPE_GROUPS["last_promotion_date"]),
        ("last_hike_date",      _EVENT_TYPE_GROUPS["last_hike_date"]),
    ]
    for field, valid_types in legacy_pairs:
        actual_d = parse_iso_date(career_ctx.get(field, ""))
        if actual_d:
            _check_actual(actual_d, valid_types)

    # 2. Full career_events[] list
    for evt in (career_ctx.get("career_events") or []):
        if not isinstance(evt, dict):
            continue
        actual_d = parse_iso_date(evt.get("date", ""))
        evt_type = (evt.get("event_type") or "").upper()
        if not actual_d or not evt_type:
            continue
        valid_types = _EVENT_TYPE_GROUPS.get(evt_type, {evt_type})
        _check_actual(actual_d, valid_types)

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


def _derive_career_track(career_ctx: Dict[str, Any]) -> str:
    """Return a career track string: 'IC' (individual contributor) or 'management'."""
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
) -> str:
    """Return an optional secondary event label that adds nuance to the primary.

    For example, a PROMOTION in management track is specifically a TEAM_EXPANSION;
    a JOB_CHANGE with desired_outcome=stability is a LATERAL_MOVE.
    Returns empty string when no secondary is applicable.
    """
    desired = (career_ctx.get("desired_outcome") or "").lower()

    if primary_event == "PROMOTION":
        return "TEAM_EXPANSION" if career_track == "management" else "LEVEL_JUMP"
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

def build_career_timeline(
    chart: "TimelineChartInput",
    eff_strengths: Dict[str, float],
    career_ctx: Dict[str, Any],
    mode: str = "full",
    llm_context: Optional[Dict[str, Any]] = None,
) -> List[Dict]:
    """Build the deterministic career timeline for a salaried professional.

    Args:
        chart: TimelineChartInput with all required chart data.
               Build via TimelineChartInput.from_payload(payload) or directly.
        eff_strengths: effective planetary strengths {planet: float}
        career_ctx: validated career context from timeline_inputs
        mode: "full" | "limited" | "forecast"

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
    # Past window is derived from the actual career history so the validator LLM
    # receives full retroactive coverage rather than just 1 year.
    # Priority: (a) earliest career_event date, (b) join_date, (c) years_experience,
    #           (d) fallback to _WINDOW_PAST_MONTHS (12 months).
    def _derive_past_months() -> int:
        _career_evts = career_ctx.get("career_events") or []
        _earliest: Optional[date] = None
        # Scan all career_events for the earliest date
        for _evt in _career_evts:
            if isinstance(_evt, dict):
                _d = parse_iso_date((_evt.get("date") or "")[:10] + "-01")
                if _d and (_earliest is None or _d < _earliest):
                    _earliest = _d
        # Also check legacy join_date
        _jd = parse_iso_date(career_ctx.get("join_date", ""))
        if _jd and (_earliest is None or _jd < _earliest):
            _earliest = _jd
        if _earliest:
            _months = (today.year - _earliest.year) * 12 + (today.month - _earliest.month) + 6
            return min(360, max(_WINDOW_PAST_MONTHS, _months))  # cap at 30 years
        # Fall back to years_experience if available
        _yrs = career_ctx.get("years_experience") or career_ctx.get("experience_years") or 0
        try:
            _yrs = int(float(str(_yrs)))
        except (ValueError, TypeError):
            _yrs = 0
        if _yrs > 1:
            return min(360, max(_WINDOW_PAST_MONTHS, _yrs * 12 + 6))
        # Ultimate fallback: derive from current_age so the window always covers
        # the person's full employment history regardless of context data quality.
        # Career assumed to start at age 18 — (age - 18) × 12 months back + 6 buffer.
        _age = career_ctx.get("current_age") or 0
        if not _age:
            # Try computing from dob
            _dob_str = career_ctx.get("dob", "")
            if _dob_str:
                try:
                    from datetime import datetime as _dt2
                    _dob_d = None
                    for _fmt2 in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
                        try:
                            _dob_d = _dt2.strptime(_dob_str, _fmt2).date()
                            break
                        except ValueError:
                            pass
                    if _dob_d:
                        _age = (today.year - _dob_d.year
                                - ((today.month, today.day) < (_dob_d.month, _dob_d.day)))
                except Exception:
                    pass
        try:
            _age = int(float(str(_age)))
        except (TypeError, ValueError):
            _age = 0
        if _age > 18:
            return min(360, max(_WINDOW_PAST_MONTHS, (_age - 18) * 12 + 6))
        return _WINDOW_PAST_MONTHS

    _past_months = _derive_past_months()
    window = _slice_window(all_periods, today, past_months=_past_months)
    if not window:
        return []

    # Phase 0 LLM context — extract weight overrides, intent tags, and sector_modifier.
    # llm_context is produced by llm_context_enricher.enrich_career_context()
    # and passed in by engine_io.parse_json_payload().
    _llm_ctx         = llm_context or {}
    _weight_overrides: Dict[str, float] = _llm_ctx.get("weight_overrides", {}) or {}
    _intent_tags: List[str]             = _llm_ctx.get("intent_tags", []) or []
    # GAP 3 fix: sector_modifier — LLM-assessed sector opportunity signal (-1.0 to +1.0)
    _sector_modifier: float = float(_llm_ctx.get("sector_modifier", 0.0) or 0.0)
    # Attach to career_ctx so _classify_event() can read them for tiebreaking
    if _intent_tags:
        career_ctx = {**career_ctx, "_intent_tags": _intent_tags}

    # Steps 3–5: score, transit overlay, classify
    blocks: List[Dict] = []
    _previous_event_type: str = ""       # state machine — carry forward
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
    _ps_for_yogas = dict(getattr(chart, "planet_sign", {}) or {})
    _moon_nak_val = getattr(chart, "moon_nakshatra", "") or ""
    if _moon_nak_val:
        _ps_for_yogas["_moon_nakshatra"] = _moon_nak_val
    _detected_yogas = _detect_natal_yogas(
        planet_house=chart.planet_house or {},
        lagna_sign=lagna_sign,
        house_lords=chart.house_lords or {},
        planet_sign=_ps_for_yogas,
    )

    for p in window:
        scores = _score_period(
            p, chart, eff_strengths, career_ctx, lagna_sign,
            detected_yogas=_detected_yogas,
            weight_overrides=_weight_overrides,
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
        )
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
        career_track = _derive_career_track(career_ctx)
        secondary_event_type = _derive_secondary_event_type(event_type, career_track, career_ctx)
        # GAP 3: planet × industry skill recommendations
        skill_recs = _get_skill_recommendation(p["ad_lord"], career_ctx.get("industry_sector", ""))

        start_str = p["start_date"].isoformat()[:7]
        end_str   = p["end_date"].isoformat()[:7]

        # Expanded AD-level narrative hint (4-5 sentences)
        narrative = _build_narrative_hint(
            base_event_type, p["md_lord"], p["ad_lord"], flags, scores["career_score"],
            kp_cusp_score=kp_c_score, jaimini_score=jai_score,
            jaimini_role=jai_role, career_ctx=career_ctx,
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
        from calendar import monthrange as _monthrange
        for _pd in pd_periods:
            _pd_start = parse_iso_date(str(_pd["start_date"]) + "-01")
            _end_ym   = str(_pd["end_date"])   # "YYYY-MM"
            try:
                _ey, _em = int(_end_ym[:4]), int(_end_ym[5:7])
                _last_day = _monthrange(_ey, _em)[1]
            except Exception:
                _last_day = 28
            _pd_end = parse_iso_date(f"{_end_ym}-{_last_day:02d}")
            _tw = _find_trigger_window(_pd_start, _pd_end, chart, today)
            _pd["trigger_window"] = _tw
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
            "domain_tag":           domain_tag,
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
    birth_time_known = True   # payload always has birth time if lagna is computed
    confidence = compute_confidence_tier(career_ctx, birth_time_known, retro_matches)

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
    _foreign_opps = _compute_foreign_module(blocks, chart, lagna_sign)

    # Now apply the output cap
    _all_blocks = blocks[:_MAX_OUTPUT_PERIODS]

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

    return _all_blocks



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

_GEO_AFFINITY_MAP: Dict[str, str] = {
    "Sun":     "South / Government-sponsored postings",
    "Moon":    "Northwest / Water-adjacent regions (UK, Scandinavia, Singapore)",
    "Mars":    "South / Industrial zones (Germany, Australia, Canada)",
    "Mercury": "East / Financial & tech hubs (UAE, Hong Kong, Singapore)",
    "Jupiter": "Northeast / Prosperous economies (USA, Australia, Canada)",
    "Venus":   "Northwest / Luxury economies (Europe, UAE, USA)",
    "Saturn":  "West / Industrial regions (UK, USA, Germany)",
    "Rahu":    "Far East / Unconventional destinations (Southeast Asia, Americas)",
    "Ketu":    "Southeast / Spiritual destinations or return-from-abroad",
}

_FOREIGN_DURATION_TYPE: Dict[str, str] = {
    "SHORT_TRIP":       "Short Trip (< 3 months)",
    "ASSIGNMENT":       "Foreign Assignment (3–18 months)",
    "RELOCATION":       "Long-term Relocation (18+ months)",
    "LONG_TERM_ABROAD": "Extended Stint Abroad (MD level)",
}

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
        "Jupiter is the natural lord of the 9th house (long journeys, fortune, philosophy). "
        "Its dasha promotes expansion through higher knowledge, international collaborations, "
        "and auspicious travel. Jupiter-ruled foreign stints are typically growth-oriented "
        "and supported by institutions, universities, or multinational corporations."
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
    ),
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
}

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


def _fop_derive_action_steps(duration: str, md_lord: str, ad_lord: str) -> List[str]:
    """Return 5-7 concrete action steps for the given duration type."""
    steps = list(_FOP_ACTION_STEPS.get(duration, _FOP_ACTION_STEPS["SHORT_TRIP"]))
    # Planet-specific prepend
    for p in (ad_lord, md_lord):
        if p == "Rahu":
            steps.insert(0, "Rahu is your dasha lord — be bold, apply to unconventional or international-first companies that you would normally consider 'out of reach'.")
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
    md_lord: str, ad_lord: str, breakdown: List[Dict], duration: str, geo: str
) -> str:
    """Compose a single narrative paragraph explaining this foreign window."""
    md_why   = _FOP_PLANET_WHY.get(md_lord, f"{md_lord} rules this major period.")
    ad_why   = _FOP_PLANET_WHY.get(ad_lord, f"{ad_lord} rules this sub-period.")
    dur_text = _FOREIGN_DURATION_TYPE.get(duration, "international opportunity")
    house_hits = [b["label"] for b in breakdown if b["factor_group"] == "HOUSE_ACTIVE"]
    house_str = "; ".join(house_hits) if house_hits else "foreign houses are indirectly activated"
    transit_hits = [b["label"] for b in breakdown if b["factor_group"] == "TRANSIT"]
    transit_str = (
        f"Transit reinforcement: {'; '.join(transit_hits)}." if transit_hits else
        "Transit planets provide indirect support."
    )
    story = (
        f"During this period {md_lord} runs as the major-period (MD) lord and {ad_lord} "
        f"as the sub-period (AD) lord. {md_why} {ad_why} "
        f"On the chart level, {house_str}. {transit_str} "
        f"The combined energy points toward a {dur_text.lower()} with geo-affinity toward "
        f"{geo}. This is a window where foreign opportunities do not merely become available "
        f"— they become natural extensions of the planetary current running through the chart."
    )
    return story


def _score_foreign_period(
    block: Dict,
    chart: "TimelineChartInput",
    lagna_sign: str,
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
        8:  "H8 activated — sudden transformation abroad",
    }
    for h, w in _FOREIGN_HOUSE_WEIGHTS.items():
        if h in active_h:
            score += w
            lbl = _h_labels[h]
            indicators.append(lbl)
            breakdown.append({
                "factor_group":  "HOUSE_ACTIVE",
                "factor":        f"H{h}_ACTIVE",
                "label":         lbl,
                "contribution":  round(w, 3),
                "max_weight":    0.42,
                "why":           _FOP_HOUSE_WHY[h],
                "pct":           int(w / 1.0 * 100),
            })

    # ── 2. Natal house lordship ─────────────────────────────────────────────
    for planet in (md_lord, ad_lord):
        for h_str, lord in hl.items():
            if lord == planet:
                try:
                    h = int(h_str)
                    w = _FOREIGN_HOUSE_WEIGHTS.get(h, 0) * 0.55
                    if w:
                        score += w
                        lbl = f"{planet} is natal lord of H{h}"
                        indicators.append(lbl)
                        breakdown.append({
                            "factor_group":  "NATAL_LORDSHIP",
                            "factor":        f"{planet}_LORD_H{h}",
                            "label":         lbl,
                            "contribution":  round(w, 3),
                            "max_weight":    0.42 * 0.55,
                            "why": (
                                f"As natal lord of H{h}, {planet} permanently carries the "
                                f"bhava-energy of {_FOP_HOUSE_WHY[h][:80]}… When {planet} "
                                f"runs its dasha, this latent foreign potential becomes active."
                            ),
                            "pct": int(w / 0.42 * 100),
                        })
                except ValueError:
                    pass

    # ── 2b. Natal PLACEMENT of MD/AD lord in a foreign house ───────────────
    # A planet placed in H9/H12/H3/H8 natally is a permanent ambassador of
    # that bhava's energy.  When it runs its dasha, this placement activates.
    # Weight = 70% of the house weight (vs 55% for mere lordship).
    for _planet in set((md_lord, ad_lord)):   # deduplicate if MD==AD
        _natal_h = ph.get(_planet, 0)
        if _natal_h in _FOREIGN_HOUSE_WEIGHTS:
            _place_w = round(_FOREIGN_HOUSE_WEIGHTS[_natal_h] * 0.70, 3)
            _lbl = f"{_planet} natally placed in H{_natal_h} (foreign bhava occupant)"
            indicators.append(_lbl)
            score += _place_w
            breakdown.append({
                "factor_group":  "NATAL_PLACEMENT",
                "factor":        f"{_planet}_PLACED_H{_natal_h}",
                "label":         _lbl,
                "contribution":  _place_w,
                "max_weight":    round(0.42 * 0.70, 3),
                "why": (
                    f"{_planet} is natally positioned in H{_natal_h}. A planet placed in a "
                    f"foreign bhava becomes a lifelong ambassador of that house's themes — "
                    f"wherever {_planet} operates its energy, H{_natal_h} foreign themes follow. "
                    f"During {_planet}'s dasha period this natal placement awakens and produces "
                    f"tangible foreign-land contact — relocation, posting, or sustained travel."
                ),
                "pct": int(_place_w / (0.42 * 0.70) * 100),
            })

    # ── 2c. Parivartana yoga: H9 lord in H12 OR H12 lord in H9 ────────────
    # This mutual exchange (sign-exchange yoga) between the two primary foreign
    # houses creates a permanent two-way circuit of long-journey / foreign-
    # residence energy.  Fires only when either exchange lord runs the dasha.
    _h9_lord  = hl.get("9",  "")
    _h12_lord = hl.get("12", "")
    if _h9_lord and _h12_lord and _h9_lord != _h12_lord:
        _h9lord_placed  = ph.get(_h9_lord,  0)
        _h12lord_placed = ph.get(_h12_lord, 0)
        _parivartana = (_h9lord_placed == 12 or _h12lord_placed == 9)
        _either_active = (_h9_lord in (md_lord, ad_lord)
                          or _h12_lord in (md_lord, ad_lord))
        if _parivartana and _either_active:
            score += 0.22
            _pari_lbl = (
                f"Parivartana yoga: H9 lord {_h9_lord} ↔ H12 lord {_h12_lord} "
                f"(exchange active in current dasha)"
            )
            indicators.append(_pari_lbl)
            breakdown.append({
                "factor_group":  "YOGA",
                "factor":        "PARIVARTANA_H9_H12",
                "label":         _pari_lbl,
                "contribution":  0.22,
                "max_weight":    0.22,
                "why": (
                    "Parivartana yoga (sign exchange) between H9 (fortune and long journeys) "
                    "and H12 (foreign residence and losses from homeland) is one of the most "
                    "powerful natal indicators of a life significantly shaped by foreign countries. "
                    "The two lords each occupy the other's house, creating a permanent circuit "
                    "between journey-energy and foreign-residence energy. During the dasha of "
                    "either lord, both houses activate simultaneously — a double activation "
                    "that rarely leaves the native in their home country."
                ),
                "pct": 100,
            })

    # ── 3. Planet-level foreign affinity ────────────────────────────────────
    for planet in (md_lord, ad_lord):
        pa = _FOREIGN_PLANET_AFFINITY.get(planet, 0)
        if pa:
            score += pa
            _role = "MD lord" if planet == md_lord else "AD lord"
            _kw   = "foreign karaka" if planet in ("Rahu", "Saturn", "Jupiter", "Ketu") else "general travel indicator"
            lbl   = f"{planet} ({_role}) — {_kw}"
            indicators.append(lbl)
            breakdown.append({
                "factor_group":  "PLANET_AFFINITY",
                "factor":        f"{planet}_AFFINITY",
                "label":         lbl,
                "contribution":  round(pa, 3),
                "max_weight":    0.32,
                "why":           _FOP_PLANET_WHY.get(planet, f"{planet} has moderate foreign affinity."),
                "pct":           int(pa / 0.32 * 100),
            })

    # ── 4. Transit support ──────────────────────────────────────────────────
    _period_flags = block.get("transit_flags", [])
    if _period_flags:
        for _flag in _period_flags:
            if "JUPITER_H9" in _flag or "JUPITER_H12" in _flag:
                score += 0.18
                lbl = f"Jupiter projected foreign transit ({_flag})"
                indicators.append(lbl)
                breakdown.append({
                    "factor_group":  "TRANSIT",
                    "factor":        "JUPITER_FOREIGN_TRANSIT",
                    "label":         lbl,
                    "contribution":  0.18,
                    "max_weight":    0.25,
                    "why": (
                        "Jupiter transiting H9 or H12 in the projected period chart is one of "
                        "the strongest transit indicators for foreign opportunity. Jupiter "
                        "expands whatever house it occupies and, in foreign houses, it "
                        "literally opens doors abroad. This is not a snapshot but a per-period "
                        "projection, so it accurately reflects the sky during this AD window."
                    ),
                    "pct": 72,
                })
                break
        for _flag in _period_flags:
            if "RAHU_KETU_AXIS" in _flag:
                score += 0.20
                lbl = "Rahu/Ketu axis on kendra — strong foreign activation"
                indicators.append(lbl)
                breakdown.append({
                    "factor_group":  "TRANSIT",
                    "factor":        "RAHU_KETU_AXIS_TRANSIT",
                    "label":         lbl,
                    "contribution":  0.20,
                    "max_weight":    0.25,
                    "why": (
                        "The Rahu-Ketu nodal axis crossing a kendra (angular house: 1, 4, 7, 10) "
                        "creates a period of maximum destabilisation of the status quo. In foreign "
                        "contexts this manifests as a powerful pull toward new geographies — "
                        "Rahu pulls the native toward unfamiliar territory while Ketu simultaneously "
                        "loosens attachment to the homeland."
                    ),
                    "pct": 80,
                })
                break
        for _flag in _period_flags:
            if "SATURN_H" in _flag and ("9" in _flag or "12" in _flag):
                score += 0.10
                lbl = f"Saturn projected foreign transit ({_flag})"
                indicators.append(lbl)
                breakdown.append({
                    "factor_group":  "TRANSIT",
                    "factor":        "SATURN_FOREIGN_TRANSIT",
                    "label":         lbl,
                    "contribution":  0.10,
                    "max_weight":    0.25,
                    "why": (
                        "Saturn transiting H9 or H12 is a slow, sustained foreign activator. "
                        "Unlike Jupiter's quick expansion, Saturn here produces karmic, long-term "
                        "foreign commitments. Its presence in a foreign house during this AD period "
                        "suggests the native will be 'held' abroad by duty, contract, or circumstance."
                    ),
                    "pct": 40,
                })
                break
    else:
        # Legacy snapshot fallback
        rahu_h = transit.get("Rahu",    0)
        jup_h  = transit.get("Jupiter", 0)
        sat_h  = transit.get("Saturn",  0)
        if rahu_h in (1, 9, 12):
            score += 0.25
            lbl = f"Rahu transiting H{rahu_h} — strong foreign pull (snapshot)"
            indicators.append(lbl)
            breakdown.append({
                "factor_group":  "TRANSIT",
                "factor":        "RAHU_SNAPSHOT_TRANSIT",
                "label":         lbl,
                "contribution":  0.25,
                "max_weight":    0.25,
                "why": "Today's Rahu transit (snapshot). Projected per-period data not available.",
                "pct": 100,
            })
        if jup_h in (9, 12):
            score += 0.18
            lbl = f"Jupiter transiting H{jup_h} — auspicious for abroad (snapshot)"
            indicators.append(lbl)
            breakdown.append({
                "factor_group":  "TRANSIT",
                "factor":        "JUPITER_SNAPSHOT_TRANSIT",
                "label":         lbl,
                "contribution":  0.18,
                "max_weight":    0.25,
                "why": "Today's Jupiter transit (snapshot). Projected per-period data not available.",
                "pct": 72,
            })
        if sat_h in (9, 12):
            score += 0.12
            lbl = f"Saturn transiting H{sat_h} — sustained foreign karma (snapshot)"
            indicators.append(lbl)
            breakdown.append({
                "factor_group":  "TRANSIT",
                "factor":        "SATURN_SNAPSHOT_TRANSIT",
                "label":         lbl,
                "contribution":  0.12,
                "max_weight":    0.25,
                "why": "Today's Saturn transit (snapshot). Projected per-period data not available.",
                "pct": 48,
            })

    # ── 5. Event classified as FOREIGN_POSTING ──────────────────────────────
    if "FOREIGN_POSTING" in block.get("event_type", ""):
        score += 0.40
        lbl = "Event classified as FOREIGN_POSTING by career engine"
        indicators.append(lbl)
        breakdown.append({
            "factor_group":  "EVENT_CLASSIFIER",
            "factor":        "FOREIGN_POSTING_TAG",
            "label":         lbl,
            "contribution":  0.40,
            "max_weight":    0.40,
            "why": (
                "The career scoring engine independently classified this period as a FOREIGN_POSTING "
                "event, based on the combination of H9/H12 KP sub-lord activation, Parashari "
                "functional nature of the MD/AD lords, and Jaimini Chara Dasha support. When the "
                "event classifier and the foreign module agree, confidence is highest."
            ),
            "pct": 100,
        })

    # ── 6. Natal Rahu compounding ───────────────────────────────────────────
    rahu_natal_h = ph.get("Rahu", 0)
    if rahu_natal_h in (9, 12) and "Rahu" in (md_lord, ad_lord):
        score += 0.18
        lbl = f"Natal Rahu in H{rahu_natal_h} + running its own dasha"
        indicators.append(lbl)
        breakdown.append({
            "factor_group":  "NATAL_COMPOUNDING",
            "factor":        "RAHU_NATAL_DASHA_COMPOUND",
            "label":         lbl,
            "contribution":  0.18,
            "max_weight":    0.18,
            "why": (
                f"Natal Rahu placed in H{rahu_natal_h} gives permanent foreign-land desire in "
                f"the chart. When Rahu itself runs as MD or AD lord (its own dasha), this natal "
                f"placement is doubly activated — the planet that rules foreign desire is also "
                f"the current time lord. This compounding effect is one of the most reliable "
                f"indicators of a genuine, sustained foreign opportunity."
            ),
            "pct": 100,
        })

    # ── 7. Venus income-gain transit ────────────────────────────────────────
    for flag in block.get("transit_flags", []):
        if flag.startswith("VENUS_H") and "INCOME_GAIN" in flag:
            score += 0.04
            lbl = f"Venus income-gain transit flag ({flag})"
            indicators.append(lbl)
            breakdown.append({
                "factor_group":  "BONUS",
                "factor":        "VENUS_INCOME_BONUS",
                "label":         lbl,
                "contribution":  0.04,
                "max_weight":    0.08,
                "why": (
                    "A Venus transit into an income house (H2, H11) coinciding with a foreign "
                    "window often signals that the posting comes with a significant compensation "
                    "or lifestyle upgrade — characteristic of luxury-destination or high-earning "
                    "international roles."
                ),
                "pct": 50,
            })
            break

    # ── 7b. Moon natally in H12 + Moon dasha active ─────────────────────────
    # Moon in H12 natally is a classic diaspora indicator — emotional
    # connection with foreign lands, often a foreign-born environment in
    # childhood. When Moon runs its dasha, this H12 placement activates.
    _moon_natal_h = ph.get("Moon", 0)
    if _moon_natal_h == 12 and "Moon" in (md_lord, ad_lord):
        score += 0.08
        _moon_lbl = "Natal Moon in H12 + Moon dasha — innate foreign-land orientation activated"
        indicators.append(_moon_lbl)
        breakdown.append({
            "factor_group":  "NATAL_COMPOUNDING",
            "factor":        "MOON_H12_DASHA_ACTIVE",
            "label":         _moon_lbl,
            "contribution":  0.08,
            "max_weight":    0.08,
            "why": (
                "The Moon placed in H12 natally creates a deep psychological pull toward foreign "
                "lands and away from the birthplace. It is classically associated with living "
                "abroad (often near water), a foreign-born or emotionally distant mother, or a "
                "childhood shaped by relocation. When Moon runs as the MD or AD lord this natal "
                "placement activates and manifests as tangible foreign contact — physical "
                "relocation, sustained travel, or deep emotional investment in a foreign country."
            ),
            "pct": 100,
        })

    # ── 7c. KP H12 sub-lord alignment (foreign cusp precision) ──────────────
    # H12 is the primary KP cusp for foreign residence. When the MD or AD lord
    # is also the sub-lord of H12 in the KP system, the foreign promise is
    # confirmed at the highest KP precision level.
    _kp_cusps_local = chart.kp_cusps if hasattr(chart, "kp_cusps") else {}
    _h12_cusp = _kp_cusps_local.get("H12", {}) or {}
    _h12_sub  = _h12_cusp.get("sub_lord", "")
    _h12_star = _h12_cusp.get("star_lord", "")
    if _h12_sub and _h12_sub in (md_lord, ad_lord):
        score += 0.14
        _kp12_lbl = f"KP H12 sub-lord is {_h12_sub} (matches MD/AD lord) — foreign cusp confirmed"
        indicators.append(_kp12_lbl)
        breakdown.append({
            "factor_group":  "KP_PRECISION",
            "factor":        "KP_H12_SUB_LORD",
            "label":         _kp12_lbl,
            "contribution":  0.14,
            "max_weight":    0.14,
            "why": (
                "In KP (Krishnamurti Paddhati), the sub-lord of H12 is the final arbiter of "
                "foreign-residence fructification. When the running dasha lord (MD or AD) is also "
                "the sub-lord of the H12 cusp, the foreign theme is activated at the highest KP "
                "precision level — natal promise, dasha activation, and KP confirmation converge."
            ),
            "pct": 100,
        })
    elif _h12_star and _h12_star in (md_lord, ad_lord):
        score += 0.07
        _kp12_star_lbl = f"KP H12 star-lord is {_h12_star} (matches MD/AD lord) — foreign cusp signified"
        indicators.append(_kp12_star_lbl)
        breakdown.append({
            "factor_group":  "KP_PRECISION",
            "factor":        "KP_H12_STAR_LORD",
            "label":         _kp12_star_lbl,
            "contribution":  0.07,
            "max_weight":    0.14,
            "why": (
                "The star-lord of H12 cusp in KP represents the house's environment and supporting "
                "energy. When the dasha lord matches the H12 star-lord, the foreign-residence theme "
                "is environmentally supported — less direct than a sub-lord match but still a "
                "meaningful KP confirmation of foreign opportunity in this window."
            ),
            "pct": 50,
        })

    if score < _FOREIGN_SCORE_THRESHOLD:
        return None

    # ── Duration type ──────────────────────────────────────────────────────
    # Gate RELOCATION by actual period length — Rahu MD lasts 18 years but
    # an AD of 10 months within it is at most an ASSIGNMENT, not RELOCATION.
    _sd_raw = parse_iso_date(str(block.get("start_date", ""))[:10])
    _ed_raw = parse_iso_date(str(block.get("end_date",   ""))[:10])
    _period_days = (_ed_raw - _sd_raw).days if (_sd_raw and _ed_raw) else 365
    # RELOCATION requires ≥18 months (≈548 days) of active period length
    _long_enough_to_relocate = _period_days >= 548
    if ("Rahu" == md_lord or score >= 0.72 or 12 in active_h) and _long_enough_to_relocate:
        duration = "RELOCATION"
    elif score >= 0.55 or 9 in active_h or ("Rahu" == md_lord and not _long_enough_to_relocate):
        duration = "ASSIGNMENT"
    else:
        duration = "SHORT_TRIP"

    # ── Geo affinity ────────────────────────────────────────────────────────
    geo_planet = ad_lord if _GEO_AFFINITY_MAP.get(ad_lord) else md_lord
    geo = (
        _GEO_AFFINITY_MAP.get(ad_lord)
        or _GEO_AFFINITY_MAP.get(md_lord)
        or "International posting (direction unspecified)"
    )
    geo_why = (
        _FOP_GEO_WHY.get(geo_planet)
        or "The direction is determined by the dominant dasha lord's elemental rulership."
    )

    # ── Confidence level ────────────────────────────────────────────────────
    factor_count = len(breakdown)
    if score >= 0.65 and factor_count >= 4:
        confidence_level = "High"
        confidence_rationale = (
            f"{factor_count} of 7 factor groups triggered; score {round(score,2)}. "
            f"Multiple independent astrological layers agree on foreign activation — "
            f"natal placement, dasha lord affinity, and transit all converge."
        )
    elif score >= 0.45 or factor_count >= 2:
        confidence_level = "Moderate"
        confidence_rationale = (
            f"{factor_count} factor group(s) active; score {round(score,2)}. "
            f"The foreign signal is present but not fully corroborated across all layers. "
            f"Pursue the opportunity proactively rather than waiting for it to arrive."
        )
    else:
        confidence_level = "Mild"
        confidence_rationale = (
            f"{factor_count} factor group(s) active; score {round(score,2)}. "
            f"A latent foreign thread exists but requires active effort to manifest — "
            f"the chart supports it, but it will not happen on its own."
        )

    # ── Deduplicate indicators ─────────────────────────────────────────────
    seen: set = set()
    unique_ind: List[str] = []
    for ind in indicators:
        if ind not in seen:
            seen.add(ind)
            unique_ind.append(ind)

    # ── Best trigger window (first PD trigger if available) ────────────────
    best_tw: Dict = {}
    for pd in (block.get("pratyantardashas") or []):
        tw = pd.get("trigger_window") or {}
        if tw.get("trigger_planet"):
            best_tw = tw
            break

    # ── Derived explanation fields ──────────────────────────────────────────
    action_steps    = _fop_derive_action_steps(duration, md_lord, ad_lord)
    risk_factors    = _fop_derive_risk_factors(md_lord, ad_lord)
    planetary_story = _fop_build_planetary_story(md_lord, ad_lord, breakdown, duration, geo)

    return {
        # ── Core fields (used by main report + standalone) ────────────────
        "start_date":     block.get("start_date", ""),
        "end_date":       block.get("end_date",   ""),
        "md_lord":        md_lord,
        "ad_lord":        ad_lord,
        "foreign_score":  round(min(1.0, score), 3),
        "indicators":     unique_ind[:7],
        "duration_type":  duration,
        "duration_label": _FOREIGN_DURATION_TYPE[duration],
        "geo_affinity":   geo,
        "event_type":     block.get("event_type", ""),
        "career_score":   block.get("career_score", 0),
        "is_past":        block.get("is_past",    False),
        "is_current":     block.get("is_current", False),
        "trigger_window": best_tw,
        # ── Rich explanation fields (used by standalone report) ───────────
        "scoring_breakdown":   breakdown,
        "planetary_story":     planetary_story,
        "action_steps":        action_steps,
        "risk_factors":        risk_factors,
        "confidence_level":    confidence_level,
        "confidence_rationale": confidence_rationale,
        "geo_why":             geo_why,
    }


def _compute_foreign_module(
    blocks: List[Dict],
    chart: "TimelineChartInput",
    lagna_sign: str,
    window_past_months: int = 12,
    window_future_years: int = 5,
) -> List[Dict]:
    """Extract all foreign opportunity windows in the specified time window.

    Window: past 1 year + next 5 years (default).
    Returns list sorted chronologically; each entry scored >= _FOREIGN_SCORE_THRESHOLD.
    """
    today         = _today_date()
    cutoff_past   = today - relativedelta(months=window_past_months)
    cutoff_future = today + relativedelta(years=window_future_years)

    results: List[Dict] = []
    for block in blocks:
        sd = parse_iso_date(str(block.get("start_date", ""))[:10])
        ed = parse_iso_date(str(block.get("end_date",   ""))[:10])
        if not sd or not ed:
            continue
        # Must overlap with the window
        if ed < cutoff_past or sd > cutoff_future:
            continue
        scored = _score_foreign_period(block, chart, lagna_sign)
        if scored:
            results.append(scored)

    # Chronological order for display
    results.sort(key=lambda x: x["start_date"])
    return results

# ═════════════════════════════════════════════════════════════════════════════
# NARRATIVE GENERATION
# ═════════════════════════════════════════════════════════════════════════════

_EVENT_NARRATIVE: Dict[str, str] = {
    "PROMOTION":            "Strong career-house activation supports upward movement in designation.",
    "BREAKTHROUGH":         "Exceptional dasha-transit alignment — major career leap possible.",
    "LEADERSHIP_EXPANSION": "Expanding sphere of authority; leadership visibility increases.",
    "INCOME_INFLECTION":    "H11/H2 activation points to a meaningful salary or income shift.",
    "JOB_CHANGE":           "H6/H12 energy and dasha planet favour a role transition.",
    "FOREIGN_POSTING":      "H9/H12 activation with Rahu influence supports overseas opportunity.",
    "SALARY_HIKE":          "H2/H11 lords active; negotiation or appraisal cycle likely to be rewarding.",
    "SKILL_UPGRADE_PHASE":  "H3/H5 period — invest in certifications, learning, or new tools.",
    "TRANSITION":           "First major career entry window — foundational choices made here echo long.",
    "RE_ENTRY":             "Re-entry conditions are astrologically supported; proactive application advised.",
    "FIRST_JOB":            "Strong first-career entry window — initiate applications, build professional network, and align with your natural planetary strengths.",
    "H8_TRANSFORMATION_ACTIVE": "8th-house transformation energy accompanies this period; embrace change and trust the rebirth process.",

    "RISK_PERIOD":              "Adverse dasha-transit combination; consolidate position, avoid risky moves.",
    "AUTHORITY_SHIFT":          "H10-H8 link suggests structural or organisational change affecting role.",
    "STABILITY":                "Consolidation phase — solid ground for performance and skill deepening.",
    "GROWTH":                   "Gradual positive trajectory; steady efforts yield compounding returns.",
    "CALIBRATION":              "Mixed signals; outcomes depend heavily on effort and timing within the window.",
    "SANDHI_PERIOD":            "Dasha Chidra (junction period) — transition zone between major cycles; outcomes arrive with delay; best used for preparation rather than action.",
    "EQUITY_EVENT":             "H2/H5/H11 convergence supports meaningful asset, equity, or investment crystallisation.",
    "LATERAL_MOVE":             "H6/H12 combined with service indicators — an industry or role shift at comparable level; network and domain leverage are key.",
    "ENTREPRENEURSHIP_WINDOW":  "H1/H3 self-will + house lords active — favourable for independent ventures, consulting, or fractional leadership.",
}

_PLANET_REMEDY: Dict[str, str] = {
    # Executive behavioral coaching translations of Vedic planetary archetypes.
    # Tone: premium corporate — suitable for VP/Director-level professionals.
    "Sun": (
        "Build executive presence. Volunteer for high-visibility presentations, lead the "
        "quarterly business review, and take explicit ownership of outcomes rather than "
        "attributing results to the team. The Sun period rewards those who step into the light."
    ),
    "Moon": (
        "Invest in emotional intelligence. Schedule structured 1-on-1s with your direct "
        "reports, avoid reactive responses to critical emails — draft, sleep on it, then send. "
        "The Moon period amplifies perception; your leadership brand is being formed by how "
        "people feel in your presence."
    ),
    "Mars": (
        "Operate with disciplined urgency. Prioritise delivery over deliberation — ship "
        "imperfect work and iterate. Cut underperforming initiatives decisively. Mars rewards "
        "those who act; prolonged analysis will cost you the window."
    ),
    "Mercury": (
        "Sharpen your communication infrastructure. Document decisions, create structured "
        "meeting agendas, and build your personal brand as the clearest thinker in the room. "
        "This is the ideal period for publishing thought-leadership content or internal memos "
        "that demonstrate strategic clarity."
    ),
    "Jupiter": (
        "Expand your advisory circle. Seek a senior mentor or executive sponsor, and "
        "simultaneously begin mentoring someone two levels below you. Jupiter periods compound "
        "through generosity — share knowledge visibly, and your reputation will attract "
        "opportunities that outpace active pursuit."
    ),
    "Venus": (
        "Audit and upgrade your professional relationships. Reconnect with dormant network "
        "contacts, invest in cross-functional collaboration, and ensure your compensation "
        "benchmarking is current. Venus periods favour negotiation — this is the right window "
        "to discuss total compensation, equity, or a revised scope of authority."
    ),
    "Saturn": (
        "Audit your delivery systems. Implement strict time-blocking, document your SOPs, "
        "and eliminate process debt that has accumulated. Saturn does not reward brilliance — "
        "it rewards consistency. The professional who ships reliably every sprint, quarter "
        "after quarter, is the one Saturn elevates."
    ),
    "Rahu": (
        "Pursue the unconventional. Accept the cross-border assignment, the emerging-tech "
        "project, or the role that has no clear precedent in your organisation. Rahu periods "
        "reward those who move against the conventional career gradient. Avoid cutting ethical "
        "corners — Rahu amplifies both the upside and the consequence."
    ),
    "Ketu": (
        "Go deep, not wide. Identify the one technical or domain capability that is "
        "genuinely rare in your organisation and spend this period building irreplaceable "
        "expertise in it. Ketu rewards specialists. Resist the pull toward visibility — "
        "your leverage in this period is depth, not breadth."
    ),
}


def _build_narrative_hint(
    event_type: str,
    md_lord: str,
    ad_lord: str,
    flags: List[str],
    score: float,
    kp_cusp_score: float = 0.0,
    jaimini_score: float = 0.0,
    jaimini_role: str = "",
    career_ctx: Optional[Dict] = None,
) -> str:
    """Compose a 4-5 sentence AD-period narrative hint incorporating KP + Jaimini context."""
    career_ctx = career_ctx or {}

    s1 = _EVENT_NARRATIVE.get(event_type, "This period requires careful astrological observation.")

    md_theme = _MD_THEMES.get(md_lord, "planetary influence that shapes the career arc")
    s2 = (f"Within the {md_lord} Mahadasha, which brings {md_theme}, "
          f"the {ad_lord} Antardasha adds its own flavour of "
          f"{_MD_THEMES.get(ad_lord, 'planetary energy')} to this specific window.")

    s3 = ""
    if kp_cusp_score >= 0.70:
        s3 = (f"KP analysis confirms strong career-cusp sub-lord activation "
              f"(alignment score {kp_cusp_score:.2f}) — the planetary chain points to "
              f"tangible career-house fructification during this Antardasha.")
    elif kp_cusp_score >= 0.45:
        s3 = (f"KP cuspal data shows moderate career-house alignment (score {kp_cusp_score:.2f}); "
              f"H10/H11 sub-lord resonance is partial, so timing and proactive effort matter more.")
    elif flags:
        flag_str = flags[0].replace("_", " ").title()
        s3 = (f"{flag_str} is active in transit — this external signal should be "
              f"factored into the timing of any career-related decisions during this window.")

    s4 = ""
    if jaimini_role and jaimini_score >= 0.60:
        s4 = f"Jaimini analysis: {jaimini_role}"
    elif score >= 0.62:
        s4 = (f"The combined {md_lord}-{ad_lord} dasha alignment scores {score:.2f}/1.00 "
              f"— a strongly favourable configuration for the career-related intentions of this window.")
    elif score <= 0.32:
        s4 = (f"The {md_lord}-{ad_lord} combination scores {score:.2f}/1.00 — relatively weak; "
              f"external circumstances and persistence will dominate over astrological push.")

    keywords = _MD_CAREER_KEYWORDS.get(md_lord, [])
    outcome  = career_ctx.get("desired_outcome", "")
    s5 = ""
    if keywords and outcome:
        kw = ", ".join(keywords[:2])
        outcome_clean = outcome.replace("_", " ")
        s5 = (f"Prioritise {kw} during this Antardasha to align with your "
              f"'{outcome_clean}' goal and capitalise on the dasha window.")
    elif keywords:
        s5 = (f"The {md_lord} Mahadasha favours: {', '.join(keywords[:2])} — "
              f"channel this period's energy in those directions for best results.")

    parts = [s for s in [s1, s2, s3, s4, s5] if s]
    return " ".join(parts).strip()


def _build_md_narrative(
    md_lord: str,
    md_start_str: str,
    md_end_str: str,
    payload: Any,
    lagna_sign: str,
    career_ctx: Dict,
    jaimini_role: str = "",
    kp_cusp_score: float = 0.0,
    ad_event_summary: str = "",   # GAP 8: comma-separated event types from all ADs in this MD
) -> str:
    """Build a 3-paragraph MD-level career narrative.

    GAP 8 fix: ad_event_summary is populated by the second pass in build_career_timeline
    after all ADs are scored, so para1 can reference the actual event distribution.
    """
    fn_table = _FUNCTIONAL_NATURE.get(lagna_sign, {})
    fn_val   = fn_table.get(md_lord, 0)
    fn_label = {2: "yogakaraka (doubly beneficial for both dhana and rajya yoga)",
                1: "functional benefic", 0: "functional neutral",
                -1: "functional malefic"}.get(fn_val, "functional neutral")

    md_theme  = _MD_THEMES.get(md_lord, "planetary influence")
    keywords  = _MD_CAREER_KEYWORDS.get(md_lord, ["professional advancement"])
    desig     = career_ctx.get("designation", "professional")
    sector    = career_ctx.get("industry_sector", "your industry")
    outcome   = career_ctx.get("desired_outcome", "career growth")
    outcome_c = outcome.replace("_", " ")

    p1_sentences = [
        f"The {md_lord} Mahadasha ({md_start_str} to {md_end_str}) introduces "
        f"{md_theme} as the overarching career force for this entire 16-year cycle.",
    ]
    if jaimini_role:
        p1_sentences.append(f"In the KN Rao Jaimini framework: {jaimini_role}")
    fn_impact = ("amplified and largely unobstructed" if fn_val >= 1
                 else "challenged and requiring extra effort" if fn_val < 0
                 else "balanced, with results proportional to effort")
    p1_sentences.append(
        f"For the {lagna_sign} Lagna, {md_lord} is a {fn_label}, meaning its career-related "
        f"significations operate in a {fn_impact} manner throughout this Mahadasha."
    )
    kw_str = ", ".join(keywords[:3])
    p1_sentences.append(
        f"The natural domains activated during a {md_lord} period include: {kw_str} — "
        f"these themes will recur across every Antardasha within this window, "
        f"with individual sub-periods adding their own flavour."
    )
    if ad_event_summary:
        p1_sentences.append(
            f"In this window, the Antardasha sequence unfolds as: {ad_event_summary}. "
            f"This spread reflects the layered quality of the {md_lord} Mahadasha — "
            f"not every sub-period fires at the same intensity, and the sequence itself "
            f"tells the career story arc for this cycle."
        )
    para1 = " ".join(p1_sentences)

    kp_cusps = getattr(payload, "kp_cusps", {}) or {}
    h10_sub  = (kp_cusps.get("H10", {}) or {}).get("sub_lord",  "")
    h10_star = (kp_cusps.get("H10", {}) or {}).get("star_lord", "")
    h11_sub  = (kp_cusps.get("H11", {}) or {}).get("sub_lord",  "")
    h6_sub   = (kp_cusps.get("H6",  {}) or {}).get("sub_lord",  "")
    h2_sub   = (kp_cusps.get("H2",  {}) or {}).get("sub_lord",  "")

    p2_sentences = []
    if h10_sub == md_lord:
        p2_sentences.append(
            f"KP analysis places {md_lord} as the sub-lord of the H10 (career) cusp — "
            f"the strongest possible KP confirmation that this Mahadasha will directly "
            f"activate and fructify career house results."
        )
    elif h10_star == md_lord:
        p2_sentences.append(
            f"In KP terms, {md_lord} is the star-lord of the H10 career cusp, "
            f"defining how and where career manifestation occurs throughout this Mahadasha — "
            f"the daily professional environment will carry {md_lord}'s signature."
        )
    else:
        align_level = ("strong" if kp_cusp_score >= 0.60 else
                       "moderate" if kp_cusp_score >= 0.35 else "indirect")
        p2_sentences.append(
            f"KP cuspal alignment for {md_lord} across the four career houses "
            f"(H10/H11/H6/H2) is {align_level} (cusp score {kp_cusp_score:.2f}), "
            f"indicating {'significant' if kp_cusp_score >= 0.45 else 'background'} "
            f"career-cusp resonance."
        )
    extras = []
    if h11_sub == md_lord:
        extras.append(f"H11 (gains) sub-lord is also {md_lord} — financial gains and desire-fulfilment are strongly supported")
    if h6_sub == md_lord:
        extras.append(f"H6 (service/employment) sub-lord is {md_lord} — employment-related matters are under this planet's direct governance")
    if h2_sub == md_lord:
        extras.append(f"H2 (income) sub-lord is {md_lord} — income and resource accumulation are tied to this Mahadasha's activation")
    if extras:
        p2_sentences.append(". ".join(extras) + ".")
    p2_sentences.append(
        f"Within this Mahadasha, the Antardasha periods whose lords are "
        f"KP career-cusp sub-lords will produce the most concrete and measurable outcomes — "
        f"those windows are the decisive moments for {outcome_c}."
    )
    para2 = " ".join(p2_sentences)

    fn_guidance = (
        "Lean into the period's natural energy — the cosmic support is strong."
        if fn_val >= 1 else
        "Exercise patience and sustained effort; the period rewards diligence over opportunism."
        if fn_val < 0 else
        "Outcomes are proportional to effort; avoid passive waiting."
    )
    para3 = (
        f"For a {desig} in the {sector} sector targeting {outcome_c}, "
        f"the {md_lord} Mahadasha offers the following strategic priorities: "
        f"{', '.join(keywords[:2])}. "
        f"{fn_guidance} "
        f"Monitor Antardasha transitions (approximately every 1-2 years) closely — "
        f"each sub-period adds a distinct quality to the overarching {md_lord} theme. "
        f"The sub-periods aligned with your KP career-cusp lords (H10 sub-lord, H11 sub-lord) "
        f"are your prime windows for decisive action toward {outcome_c}."
    )

    return f"{para1}\n\n{para2}\n\n{para3}"


def _build_remedies(event_type: str, md_lord: str, ad_lord: str) -> List[str]:
    """Return 1-2 remedies relevant to this period's planets."""
    remedies = []
    if event_type in ("RISK_PERIOD", "AUTHORITY_SHIFT", "CALIBRATION"):
        for p in [md_lord, ad_lord]:
            r = _PLANET_REMEDY.get(p)
            if r and r not in remedies:
                remedies.append(r)
    else:
        r = _PLANET_REMEDY.get(md_lord)
        if r:
            remedies.append(r)
    return remedies[:2]


# =============================================================================
# GAP 4 -- MACRO-ECONOMIC CALIBRATION INDEX
# =============================================================================

_MACRO_INDEX: Dict[str, float] = {
    "technology":          0.72,
    "software":            0.72,
    "it":                  0.72,
    "finance":             0.88,
    "healthcare":          1.15,
    "consulting":          0.85,
    "manufacturing":       0.90,
    "real_estate":         0.68,
    "retail":              0.75,
    "media":               0.65,
    "education":           0.95,
    "energy":              1.05,
    "logistics":           0.82,
    "government":          1.00,
    "pharma":              1.10,
    "_default":            0.90,
}

_MACRO_HEADWIND_THRESHOLD = 0.70


def _get_macro_score(industry_sector: str, career_ctx=None) -> float:
    """Return current macro health score for the given sector."""
    if career_ctx:
        _override = career_ctx.get("macro_override")
        if _override is not None:
            try:
                return float(_override)
            except (TypeError, ValueError):
                pass

    import pathlib, json as _json
    _cfg_file = pathlib.Path(__file__).with_name("macro_config.json")
    _idx = _MACRO_INDEX
    if _cfg_file.exists():
        try:
            _loaded = _json.loads(_cfg_file.read_text(encoding="utf-8"))
            if isinstance(_loaded.get("sectors"), dict):
                _idx = _loaded["sectors"]
        except Exception:
            pass

    sector_key = (industry_sector or "").lower().replace(" ", "_").replace("-", "_")
    return (
        _idx.get(sector_key)
        or next((v for k, v in _idx.items() if sector_key.startswith(k[:4]) and k != "_default"), None)
        or _idx.get("_default", 0.90)
    )


# =============================================================================
# GAP 1 -- MICRO-TRIGGER WINDOW
# =============================================================================

_SUN_DAYS_PER_SIGN     = 30
_MARS_DAYS_PER_SIGN    = 45
_JUPITER_DAYS_PER_SIGN = 365


def _find_trigger_window(pd_start, pd_end, chart, today) -> dict:
    """Find the peak-probability activation window within a Pratyantardasha."""
    h10_lord     = (chart.house_lords or {}).get("10", "")
    amk          = chart.amatyakaraka or ""
    planet_house = chart.planet_house or {}

    target_houses = []
    for p in [h10_lord, amk]:
        h = planet_house.get(p, 0)
        if h:
            target_houses.append(h)
    if not target_houses:
        return {"trigger_planet": None, "trigger_start": None,
                "trigger_end": None, "trigger_note": ""}

    transit_snap = chart.transit_house_positions or {}

    best = {"trigger_planet": None, "trigger_start": None,
            "trigger_end": None, "trigger_note": ""}

    _trigger_planets = [
        ("Jupiter", _JUPITER_DAYS_PER_SIGN),
        ("Sun",     _SUN_DAYS_PER_SIGN),
        ("Mars",    _MARS_DAYS_PER_SIGN),
    ]
    for planet, days_per_sign in _trigger_planets:
        current_h = transit_snap.get(planet, 0)
        if not current_h:
            continue
        for target_h in target_houses:
            fwd = (target_h - current_h) % 12
            days_until_target = int(fwd * days_per_sign)
            transit_date = today + timedelta(days=days_until_target)
            if pd_start <= transit_date <= pd_end:
                window_start = transit_date
                window_end   = min(transit_date + timedelta(days=days_per_sign), pd_end)
                lord_label   = h10_lord if target_h == planet_house.get(h10_lord, 0) else amk
                best = {
                    "trigger_planet": planet,
                    "trigger_start":  window_start.isoformat(),
                    "trigger_end":    window_end.isoformat(),
                    "trigger_note": (
                        f"{planet} activates natal {lord_label} (H{target_h}) "
                        f"between {window_start.strftime('%d %b %Y')} "
                        f"and {window_end.strftime('%d %b %Y')} -- "
                        f"highest probability window for this period's event to crystallise."
                    ),
                }
                return best

    return best


# =============================================================================
# GAP 2 -- WORKPLACE FRICTION SCORING
# =============================================================================

_MALEFIC_PLANETS = {"Saturn", "Rahu", "Mars", "Ketu"}


def _compute_workplace_friction(transit_flags, transit_positions, chart, lagna_sign) -> dict:
    """Return workplace friction flags based on transit malefic positions."""
    h10_lord     = (chart.house_lords or {}).get("10", "")
    h10_lord_h   = (chart.planet_house or {}).get(h10_lord, 0)
    planet_house = transit_positions or {}

    flags = []
    weights = {"BOSS_FRICTION": 0.40, "TEAM_ATTRITION": 0.30,
               "PEER_RIVALRY": 0.20, "ISOLATION_RISK": 0.10}

    for planet in _MALEFIC_PLANETS:
        ph = planet_house.get(planet, 0)
        if not ph:
            continue
        if ph == 10 or (h10_lord_h and ph == h10_lord_h):
            if "BOSS_FRICTION" not in flags:
                flags.append("BOSS_FRICTION")
        if ph == 6:
            if "TEAM_ATTRITION" not in flags:
                flags.append("TEAM_ATTRITION")
        if planet in ("Rahu", "Mars") and ph in (3, 11):
            if "PEER_RIVALRY" not in flags:
                flags.append("PEER_RIVALRY")
        if planet == "Saturn" and ph in (12, 4):
            if "ISOLATION_RISK" not in flags:
                flags.append("ISOLATION_RISK")

    if any("STRESS" in f or "DISRUPTION" in f for f in transit_flags):
        if "BOSS_FRICTION" not in flags:
            flags.append("BOSS_FRICTION")
    if any("SADE_SATI" in f for f in transit_flags):
        if "ISOLATION_RISK" not in flags:
            flags.append("ISOLATION_RISK")

    score = round(min(sum(weights.get(f, 0.1) for f in flags), 1.0), 3)

    parts = []
    if "BOSS_FRICTION" in flags:
        parts.append("potential tension with direct leadership or authority figures")
    if "TEAM_ATTRITION" in flags:
        parts.append("friction in daily team dynamics or subordinate turnover")
    if "PEER_RIVALRY" in flags:
        parts.append("competitive pressure from peers or lateral colleagues")
    if "ISOLATION_RISK" in flags:
        parts.append("risk of professional isolation or reduced visibility")

    narrative = (
        "Workplace dynamics are smooth this period -- focus on delivery." if not parts
        else "Workplace environment flags: " + "; ".join(parts) + "."
    )

    return {
        "friction_flags":     flags,
        "friction_score":     score,
        "friction_narrative": narrative,
    }


# =============================================================================
# PRATYANTARDASHA (PD) SUB-PERIODS
# =============================================================================

def _expand_pratyantardashas(md_lord: str, ad_lord: str, ad_start, ad_end) -> list:
    """Expand an Antardasha into its 9 Pratyantardasha sub-periods."""
    if isinstance(ad_start, str):
        ad_start = parse_iso_date(ad_start)
    if isinstance(ad_end, str):
        ad_end = parse_iso_date(ad_end)

    total_days = (ad_end - ad_start).days
    if total_days <= 0:
        return []

    _TOTAL_YEARS = sum(_VIMSHOTTARI_YEARS.values())
    start_idx = _VIMSHOTTARI_ORDER.index(ad_lord) if ad_lord in _VIMSHOTTARI_ORDER else 0

    pds = []
    cursor = ad_start
    for i in range(9):
        pd_lord = _VIMSHOTTARI_ORDER[(start_idx + i) % 9]
        pd_days = int(round(total_days * _VIMSHOTTARI_YEARS[pd_lord] / _TOTAL_YEARS))
        pd_end_d = cursor + timedelta(days=pd_days)
        if pd_end_d > ad_end:
            pd_end_d = ad_end
        pds.append({
            "pd_lord":    pd_lord,
            "start_date": cursor.strftime("%Y-%m"),
            "end_date":   pd_end_d.strftime("%Y-%m"),
        })
        cursor = pd_end_d
        if cursor >= ad_end:
            break

    return pds


def _expand_sookshams(pd_lord: str, pd_start, pd_end) -> list:
    """Expand a Pratyantardasha into its 9 Sooksham sub-periods."""
    total_days = (pd_end - pd_start).days
    if total_days <= 0:
        return []

    _TOTAL_YEARS = sum(_VIMSHOTTARI_YEARS.values())
    start_idx = _VIMSHOTTARI_ORDER.index(pd_lord) if pd_lord in _VIMSHOTTARI_ORDER else 0

    sookshams = []
    cursor = pd_start
    for i in range(9):
        sk_lord = _VIMSHOTTARI_ORDER[(start_idx + i) % 9]
        sk_days = max(1, int(round(total_days * _VIMSHOTTARI_YEARS[sk_lord] / _TOTAL_YEARS)))
        sk_end  = cursor + timedelta(days=sk_days)
        if sk_end > pd_end:
            sk_end = pd_end
        sookshams.append({
            "sk_lord":       sk_lord,
            "start_date":    cursor.isoformat(),
            "end_date":      sk_end.isoformat(),
            "duration_days": (sk_end - cursor).days,
        })
        cursor = sk_end
        if cursor >= pd_end:
            break

    return sookshams


from typing import List, Dict, Any

def _check_business_tension(blocks: List[Dict[str, Any]], career_ctx: Dict[str, Any], lagna_sign: str) -> None:
    """
    Flag AD blocks where engine output conflicts with business/startup desired outcome.
    Modifies the blocks in-place by adding a 'business_tension' key if a conflict exists.
    """
    desired = career_ctx.get("desired_outcome", "")
    if desired not in {"START_BUSINESS", "ENTREPRENEURSHIP", "INDEPENDENT_PRACTICE"}:
        return

    # Using a set for O(1) lookups
    employment_events = {
        "PROMOTION", "SALARY_HIKE", "LEADERSHIP_EXPANSION",
        "AUTHORITY_SHIFT", "STABILITY",
    }
    
    for b in blocks:
        et = b.get("event_type", "")
        if et in employment_events:
            b["business_tension"] = (
                f"Engine shows salaried {et.replace('_',' ').lower()} energy. "
                "For entrepreneurship, pair this with H5/H9/H3 activation periods; "
                "Rahu or Jupiter in lagna/H10 are additional triggers."
            )
