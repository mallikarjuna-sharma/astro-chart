"""JyotishAI — Astrological Enhancer Module (34-Gap Fix Suite).

All 34 identified astrological gaps filled in one standalone module.
Import into timeline.py via:
    from .astro_enhancer import (
        AstroEnhancer, EnhancerInput, EnhancerResult
    )

No circular imports — this module has zero dependency on timeline.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field as dc_field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple, Set, Any

from jyotish.kp_subfield_hint import narrow_field_specialization  # GAP FIX (2026-08-17): Step 6 sub-field narrowing
# GAP FIX (2026-08-21, remediation plan item 2.3, FINAL_VS_V13_ASTROLOGICAL_
# COVERAGE_AUDIT.md P0 #1): reuse the same cusp-verification check
# Field_Determination/field_methods/kp.py already gates its KP score with,
# so this module's Tier 6 KP functions (which read inp.kp_cusps_full for
# field-ranking purposes) don't grant unverified KP cusps full authority.
from jyotish.kp_audit import audit_kp_cusps
from jyotish.dasha_longevity import score_dasha_longevity  # GAP FIX (2026-08-17): Step 7 Vimshottari longevity filter
# GAP FIX (2026-08-21, Gap_Analysis_2026-07 §1.1/§1.2): reuse the canonical, chart-sensitive
# Jaimini Chara Dasha sequence (direction + per-sign duration both derived from the actual
# chart) instead of this module's own forward-only, fixed-duration-table reimplementation.
from jyotish.astro import compute_chara_dasha_sequence

# ─────────────────────────────────────────────────────────────────────────────
# Shared constants
# ─────────────────────────────────────────────────────────────────────────────

_SIGN_SEQ: List[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_SIGN_LORD: Dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

_PLANET_EXALT_SIGN: Dict[str, str] = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces",
    "Saturn": "Libra", "Rahu": "Taurus", "Ketu": "Scorpio",
}

_PLANET_DEBIL_SIGN: Dict[str, str] = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo",
    "Saturn": "Aries", "Rahu": "Scorpio", "Ketu": "Taurus",
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

_NATURAL_MALEFICS: Set[str] = {"Saturn", "Mars", "Rahu", "Ketu", "Sun"}
_NATURAL_BENEFICS: Set[str] = {"Jupiter", "Venus", "Mercury", "Moon"}

_VIMSHOTTARI_ORDER: List[str] = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"
]
_VIMSHOTTARI_YEARS: Dict[str, int] = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}

_KENDRA: Set[int] = {1, 4, 7, 10}
_TRIKONA: Set[int] = {1, 5, 9}
_DUSTHANA: Set[int] = {6, 8, 12}
_UPACHAYA: Set[int] = {3, 6, 10, 11}

# ─────────────────────────────────────────────────────────────────────────────
# Nakshatra tables
# ─────────────────────────────────────────────────────────────────────────────

_NAKSHATRA_NAMES: List[str] = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha",
    "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
    "Shravana", "Dhanishtha", "Shatabhisha", "Purva Bhadra",
    "Uttara Bhadra", "Revati",
]

_NAKSHATRA_LORDS: Dict[str, str] = {
    "Ashwini": "Ketu",      "Bharani": "Venus",     "Krittika": "Sun",
    "Rohini": "Moon",       "Mrigashira": "Mars",   "Ardra": "Rahu",
    "Punarvasu": "Jupiter", "Pushya": "Saturn",     "Ashlesha": "Mercury",
    "Magha": "Ketu",        "Purva Phalguni": "Venus", "Uttara Phalguni": "Sun",
    "Hasta": "Moon",        "Chitra": "Mars",       "Swati": "Rahu",
    "Vishakha": "Jupiter",  "Anuradha": "Saturn",  "Jyeshtha": "Mercury",
    "Mula": "Ketu",         "Purva Ashadha": "Venus", "Uttara Ashadha": "Sun",
    "Shravana": "Moon",     "Dhanishtha": "Mars",  "Shatabhisha": "Rahu",
    "Purva Bhadra": "Jupiter", "Uttara Bhadra": "Saturn", "Revati": "Mercury",
}

_NAK_SPAN: float = 360.0 / 27.0  # 13.333...°


def get_nakshatra(degree: float) -> str:
    """Return Nakshatra name for an ecliptic degree 0–360."""
    idx = int((degree % 360) / _NAK_SPAN)
    return _NAKSHATRA_NAMES[min(idx, 26)]


def get_nakshatra_lord(degree: float) -> str:
    return _NAKSHATRA_LORDS.get(get_nakshatra(degree), "")


def get_nakshatra_pada(degree: float) -> int:
    """Return pada (1–4) within a Nakshatra."""
    pos_in_nak = (degree % 360) % _NAK_SPAN
    return int(pos_in_nak / (_NAK_SPAN / 4)) + 1


# ─────────────────────────────────────────────────────────────────────────────
# Data contract
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EnhancerInput:
    """All extra chart fields needed by the 34-gap enhancer.

    Pass alongside the existing TimelineChartInput; these fields are
    optional — missing data gracefully degrades to 0/neutral.
    """
    # Per-period context
    md_lord: str = ""
    ad_lord: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    # Native birth data
    dob: Optional[date] = None
    lagna_sign: str = ""

    # Planet degrees (ecliptic, 0–360)
    planet_natal_degrees: Dict[str, float] = dc_field(default_factory=dict)
    planet_transit_degrees: Dict[str, float] = dc_field(default_factory=dict)

    # Planet sign and house positions
    planet_sign: Dict[str, str] = dc_field(default_factory=dict)
    planet_house: Dict[str, int] = dc_field(default_factory=dict)
    house_lords: Dict[str, str] = dc_field(default_factory=dict)

    # Retrograde status
    retrograde_planets: Set[str] = dc_field(default_factory=set)

    # Ashtakavarga
    pav_data: Dict[str, Dict[str, int]] = dc_field(default_factory=dict)  # {planet: {house_str: bindus}}
    sav_data: Dict[str, int] = dc_field(default_factory=dict)             # {house_str: total_bindus}

    # Divisional chart dignities: {varga: {planet: dignity_string}}
    varga_dignities: Dict[str, Dict[str, str]] = dc_field(default_factory=dict)

    # D10 extended
    d10_lagna_sign: str = ""
    d10_house_lords: Dict[str, str] = dc_field(default_factory=dict)
    d10_house_occupancy: Dict[str, List[str]] = dc_field(default_factory=dict)

    # D27 planet strengths: {planet: "strong"/"moderate"/"weak"/"very_weak"}
    d27_planet_strengths: Dict[str, str] = dc_field(default_factory=dict)

    # KP extended
    kp_cusps_full: Dict[str, Dict] = dc_field(default_factory=dict)      # includes sub_sub_lord
    planet_nakshatra_lord: Dict[str, str] = dc_field(default_factory=dict)
    kp_significators: Dict[str, Dict] = dc_field(default_factory=dict)
    lagna_star_lord: str = ""
    lagna_sub_lord: str = ""
    moon_star_lord: str = ""
    moon_sub_lord: str = ""
    day_lord: str = ""

    # Jaimini
    atmakaraka: str = ""
    amatyakaraka: str = ""  # GAP FIX (2026-08-17): AmK — often more precise than
                             # the 10th lord for career per Jaimini; was defined
                             # nowhere in this module prior to this fix.
    jaimini_chara_lagna_sign: str = ""  # AK sign in D9 = Karakamsha Lagna

    # Transit projected positions
    transit_projected: Dict[str, int] = dc_field(default_factory=dict)   # {planet: house}

    # Dasha change dates for sandhi detection
    md_change_dates: List[date] = dc_field(default_factory=list)
    ad_change_dates: List[date] = dc_field(default_factory=list)

    # Moon Nakshatra pada number (1–108) for Yogini Dasha
    moon_nakshatra_pada_num: int = 0

    # Moon Nakshatra lord (for Ashtottari)
    moon_nakshatra_lord: str = ""

    # Rahu house (for Ashtottari condition check)
    rahu_house: int = 0
    moon_house: int = 0

    # Full Vimshottari MD sequence (GAP FIX 2026-08-17, Step 7 longevity filter)
    dasha_sequence: List[Dict] = dc_field(default_factory=list)


@dataclass
class EnhancerResult:
    """Output from AstroEnhancer for a single dasha period."""
    # Tier 1 — Scoring modifiers (summed into career_score)
    combustion_modifier: float = 0.0          # G1: -0.08 to 0
    retrograde_modifier: float = 0.0          # G2: -0.05 to 0
    graha_yuddha_modifier: float = 0.0        # G3: -0.08 to 0
    dig_bala_factor: float = 1.0              # G4: 0.3–1.0 multiplier on strength_product
    neecha_bhanga_bonus: float = 0.0          # G5: +0.12 if active
    viparita_raja_bonus: float = 0.0          # G6: +0.10 if active
    papa_kartari_penalty: float = 0.0         # G7: -0.08 to 0
    kala_sarpa_modifier: float = 0.0          # G8: -0.05 to 0
    upachaya_growth_factor: float = 1.0       # G9: 0.6–1.2

    # Tier 2 — Timing precision flags
    sooksham_lords: List[Dict] = dc_field(default_factory=list)   # G10
    sooksham_timing_score: float = 0.0   # G10 precision score: 0=unavail, 0.5=neutral, 0.8=concentrated
    is_sandhi: bool = False                                        # G11
    sandhi_modifier: float = 0.0                                   # G11
    nakshatra_trigger_flags: List[str] = dc_field(default_factory=list)  # G12
    pav_transit_score: float = 0.5            # G13: 0–1 (MD/AD lord transit PAV)
    pav_slow_planet_score: float = 0.5        # G13b: 0–1 (Jupiter/Saturn/Rahu/Ketu, dasha-independent)
    kaksha_activation: bool = False           # G14

    # Tier 3 — Alternative dasha systems
    chara_dasha_score: float = 0.5            # G15
    yogini_name: str = ""                     # G16
    yogini_score: float = 0.5                 # G16
    ashtottari_lord: str = ""                 # G17
    ashtottari_active: bool = False           # G17

    # Tier 4 — Divisional chart
    d10_full_score: float = 0.0               # G18
    d60_modifier: float = 0.0                 # G19
    d27_modifier: float = 0.0                 # G20
    vimsopaka_score: float = 0.5              # G21

    # Tier 5 — Lagna systems
    surya_lagna_bonus: float = 0.0            # G22
    arudha_bonus: float = 0.0                 # G23
    karakamsha_bonus: float = 0.0             # G24
    amatyakaraka_score: float = 0.5           # G24b (GAP FIX 2026-08-17)

    # Tier 6 — KP precision
    kp_ssl_score: float = 0.0                 # G25
    kp_weighted_score: float = 0.0            # item #5 (2026-07-07): multi-level KP scoring
    kp_ruling_planets_score: float = 0.5     # G26
    kp_nakshatra_chain_score: float = 0.0    # G27
    kp_subfield_hint: str = ""  # GAP FIX (2026-08-17): Step 6 sub-field narrowing, advisory only
    dasha_longevity_score: float = 0.5  # GAP FIX (2026-08-17): Step 7 Vimshottari longevity filter
    # GAP FIX (2026-08-21, remediation plan item 2.3): whether inp.kp_cusps_full
    # passed the same cusp-chain verification (jyotish/kp_audit.py::audit_kp_cusps)
    # Field_Determination/field_methods/kp.py already gates its KP score with.
    # Defaults True so any caller that never populates it (there should be none
    # after this fix, since AstroEnhancer.run() always sets it) doesn't get a
    # false discount.
    kp_cusp_verified: bool = True

    # Tier 8 — Aspect flags (G32–G34, used by transit layer)
    mars_aspect_flags: List[str] = dc_field(default_factory=list)
    transit_aspect_flags: List[str] = dc_field(default_factory=list)

    # Narrative annotations
    combustion_notes: List[str] = dc_field(default_factory=list)
    retrograde_notes: List[str] = dc_field(default_factory=list)
    yoga_notes: List[str] = dc_field(default_factory=list)
    timing_notes: List[str] = dc_field(default_factory=list)

    # New event type hints (G28–G31)
    event_hints: List[str] = dc_field(default_factory=list)

    @property
    def total_bonus(self) -> float:
        """Net additive modifier to career_score from all enhancer factors."""
        return round(
            self.combustion_modifier
            + self.retrograde_modifier
            + self.graha_yuddha_modifier
            + self.neecha_bhanga_bonus
            + self.viparita_raja_bonus
            + self.papa_kartari_penalty
            + self.kala_sarpa_modifier
            + self.sandhi_modifier
            + self.surya_lagna_bonus
            + self.arudha_bonus
            + self.karakamsha_bonus
            + self.d60_modifier
            + self.d27_modifier,
            4,
        )


# ─────────────────────────────────────────────────────────────────────────────
# G1 — Combustion (Asta)
# ─────────────────────────────────────────────────────────────────────────────

# V1.3 merge plan item 1: _is_combust now delegates to the canonical
# jyotish/dignity.py::is_combust() instead of maintaining its own orb table.
# This retires a real drift bug: this module's old table gave Rahu/Ketu an
# 8-degree orb, while the canonical constants.py._COMBUST_ORB table (used by
# astro.py's _detect_combust_planets) has no Rahu/Ketu entries at all -- the
# two combustion checks could disagree on Rahu/Ketu for the same chart. Per
# the 2026-07 merge decision, Rahu/Ketu are excluded from combustion
# classification (shadow points have no physical body to "burn").
# _COMBUSTION_ORBS is kept only for the display-string orb value in
# _g1_combustion's note text below (falls back to 10.0 for any planet not in
# canonical _COMBUST_ORB, matching the old default).
from jyotish.dignity import is_combust as _dignity_is_combust
from jyotish.constants import _COMBUST_ORB as _CANONICAL_COMBUST_ORB

_COMBUSTION_ORBS: Dict[str, float] = dict(_CANONICAL_COMBUST_ORB)


def _is_combust(planet: str, natal_degs: Dict[str, float], retrograde: bool = False) -> bool:
    sun_deg = natal_degs.get("Sun")
    p_deg = natal_degs.get(planet)
    return _dignity_is_combust(planet, p_deg, sun_deg, retrograde=retrograde)


def _g1_combustion(inp: EnhancerInput) -> Tuple[float, List[str]]:
    # 2026-08-17 combustion-rule unification: retrograde Mercury/Venus now use
    # jyotish/dignity.py's narrower classical orb here too (previously this
    # call never passed retrograde status through, even though EnhancerInput
    # already tracks it in retrograde_planets), and a cazimi dasha lord (see
    # is_cazimi() in dignity.py) is no longer misclassified as combust. See
    # md/ENGINE_SIMPLIFICATION_2026-08-17_combustion_unify.md.
    degs = inp.planet_natal_degrees
    retro_set = inp.retrograde_planets
    modifier = 0.0
    notes: List[str] = []
    for pl, penalty in [(inp.md_lord, -0.08), (inp.ad_lord, -0.04)]:
        if pl and _is_combust(pl, degs, retrograde=pl in retro_set):
            modifier += penalty
            notes.append(
                f"{pl} is combust (within {_COMBUSTION_ORBS.get(pl, 10):.0f}° of Sun) — "
                "planetary vitality reduced; results delivered late or through intermediaries."
            )
    return max(-0.10, modifier), notes


# ─────────────────────────────────────────────────────────────────────────────
# G2 — Retrograde natal status
# ─────────────────────────────────────────────────────────────────────────────

def _g2_retrograde(inp: EnhancerInput) -> Tuple[float, List[str]]:
    retro = inp.retrograde_planets
    modifier = 0.0
    notes: List[str] = []
    if inp.md_lord in retro:
        modifier -= 0.03
        notes.append(
            f"{inp.md_lord} (MD lord) is natal retrograde — results arrive after initial "
            "reversal or through an unconventional, non-linear career path."
        )
    if inp.ad_lord in retro and inp.ad_lord != inp.md_lord:
        modifier -= 0.02
        notes.append(
            f"{inp.ad_lord} (AD lord) is natal retrograde — sub-period outcomes may initially "
            "appear to move backward before consolidating."
        )
    return modifier, notes


# ─────────────────────────────────────────────────────────────────────────────
# G3 — Graha Yuddha (Planetary War)
# ─────────────────────────────────────────────────────────────────────────────

def _g3_graha_yuddha(inp: EnhancerInput) -> Tuple[float, List[str]]:
    """Identify planetary war losers and penalise if they are dasha lords."""
    degs = inp.planet_natal_degrees
    war_losers: List[str] = []
    non_luminaries = ["Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

    for i, p1 in enumerate(non_luminaries):
        for p2 in non_luminaries[i + 1:]:
            d1 = degs.get(p1)
            d2 = degs.get(p2)
            if d1 is None or d2 is None:
                continue
            diff = abs(d1 - d2) % 360
            if diff > 180:
                diff = 360 - diff
            if diff <= 1.0:
                # Loser = higher ecliptic longitude (some schools differ; using standard)
                loser = p1 if (d1 % 360) > (d2 % 360) else p2
                if loser not in war_losers:
                    war_losers.append(loser)

    modifier = 0.0
    notes: List[str] = []
    if inp.md_lord in war_losers:
        modifier -= 0.06
        notes.append(
            f"{inp.md_lord} lost a natal Graha Yuddha (Planetary War) — "
            "its dasha delivers permanently weakened, contested results."
        )
    if inp.ad_lord in war_losers and inp.ad_lord != inp.md_lord:
        modifier -= 0.03
        notes.append(
            f"{inp.ad_lord} lost a natal Graha Yuddha — sub-period results are "
            "diluted or come through persistent struggle."
        )
    return max(-0.08, modifier), notes


# ─────────────────────────────────────────────────────────────────────────────
# G4 — Dig Bala (Directional Strength)
# ─────────────────────────────────────────────────────────────────────────────

_DIG_BALA_IDEAL_HOUSE: Dict[str, int] = {
    "Jupiter": 1, "Mercury": 1,  # East — Lagna
    "Sun": 10,    "Mars": 10,    # South — Karma Bhava
    "Saturn": 7,                 # West — Partnership
    "Moon": 4,    "Venus": 4,    # North — Home
}


def _g4_dig_bala_factor(planet: str, planet_house: Dict[str, int]) -> float:
    """Return 0.3–1.0; 1.0 = maximum directional strength."""
    ideal = _DIG_BALA_IDEAL_HOUSE.get(planet, 0)
    if not ideal:
        return 0.7  # Rahu/Ketu — no classical Dig Bala
    actual = planet_house.get(planet, 0)
    if not actual:
        return 0.7
    dist = abs(actual - ideal)
    if dist > 6:
        dist = 12 - dist
    # Distance 0 = 1.0, distance 6 = 0.3
    return round(1.0 - (dist / 6.0) * 0.7, 3)


def _g4_combined_dig_bala(inp: EnhancerInput) -> float:
    f_md = _g4_dig_bala_factor(inp.md_lord, inp.planet_house)
    f_ad = _g4_dig_bala_factor(inp.ad_lord, inp.planet_house)
    # Weighted average: MD lord has more influence
    return round(f_md * 0.65 + f_ad * 0.35, 3)


# ─────────────────────────────────────────────────────────────────────────────
# G5 — Neecha Bhanga Raja Yoga
# ─────────────────────────────────────────────────────────────────────────────

def _is_debilitated(planet: str, planet_sign: Dict[str, str]) -> bool:
    return planet_sign.get(planet, "") == _PLANET_DEBIL_SIGN.get(planet, "__NONE__")


def _g5_neecha_bhanga(planet: str, planet_sign: Dict[str, str], planet_house: Dict[str, int]) -> bool:
    """Return True if debilitation is cancelled (Neecha Bhanga)."""
    if not _is_debilitated(planet, planet_sign):
        return False

    debil_sign = _PLANET_DEBIL_SIGN.get(planet, "")
    exalt_sign = _PLANET_EXALT_SIGN.get(planet, "")
    debil_lord = _SIGN_LORD.get(debil_sign, "")
    exalt_lord = _SIGN_LORD.get(exalt_sign, "")

    # Rule 1: Lord of debilitation sign in kendra from lagna
    if debil_lord and planet_house.get(debil_lord, 0) in _KENDRA:
        return True
    # Rule 2: Lord of exaltation sign in kendra from lagna
    if exalt_lord and planet_house.get(exalt_lord, 0) in _KENDRA:
        return True
    # Rule 3: Debilitated planet itself in kendra and its exaltation lord in kendra
    if planet_house.get(planet, 0) in _KENDRA and exalt_lord and planet_house.get(exalt_lord, 0) in _KENDRA:
        return True
    # Rule 4: Planet that would be exalted in the debilitation sign is in kendra from Moon
    # (Classical 4th cancellation rule — simplified)
    return False


def _g5_neecha_bhanga_bonus(inp: EnhancerInput) -> Tuple[float, List[str]]:
    bonus = 0.0
    notes: List[str] = []
    for pl, wt in [(inp.md_lord, 0.12), (inp.ad_lord, 0.07)]:
        if pl and _g5_neecha_bhanga(pl, inp.planet_sign, inp.planet_house):
            bonus += wt
            notes.append(
                f"{pl} is debilitated but Neecha Bhanga cancels the fall — "
                "this creates a powerful Raja Yoga; the dasha delivers exceptional results "
                "especially in the second half of the period."
            )
    return min(0.15, bonus), notes


# ─────────────────────────────────────────────────────────────────────────────
# G6 — Viparita Raja Yoga
# ─────────────────────────────────────────────────────────────────────────────

def _g6_viparita_raja_yoga(
    inp: EnhancerInput,
) -> Tuple[float, Dict[str, str], List[str]]:
    hl = inp.house_lords
    ph = inp.planet_house
    h6l = hl.get("6", "")
    h8l = hl.get("8", "")
    h12l = hl.get("12", "")
    yogas: Dict[str, str] = {}

    if h6l and ph.get(h6l, 0) in _DUSTHANA:
        yogas["Harsha_VRY"] = h6l
    if h8l and ph.get(h8l, 0) in _DUSTHANA:
        yogas["Sarala_VRY"] = h8l
    if h12l and ph.get(h12l, 0) in _DUSTHANA:
        yogas["Vimala_VRY"] = h12l

    active = [y for y, pl in yogas.items()
              if pl in (inp.md_lord, inp.ad_lord)]
    bonus = len(active) * 0.05
    notes: List[str] = []
    for y in active:
        notes.append(
            f"{yogas[y]} forms {y.replace('_VRY', '')} Viparita Raja Yoga — "
            "dusthana lord in dusthana converts obstacles into sudden career breakthroughs."
        )
    return min(0.10, bonus), yogas, notes


# ─────────────────────────────────────────────────────────────────────────────
# G7 — Papa Kartari Yoga
# ─────────────────────────────────────────────────────────────────────────────

def _g7_papa_kartari(inp: EnhancerInput) -> Tuple[float, List[str]]:
    ph = inp.planet_house
    penalty = 0.0
    notes: List[str] = []

    for career_h, h_wt in [(10, 0.05), (11, 0.03), (2, 0.02)]:
        prev_h = (career_h - 2) % 12 + 1
        next_h = career_h % 12 + 1
        prev_mal = any(ph.get(m, 0) == prev_h for m in _NATURAL_MALEFICS)
        next_mal = any(ph.get(m, 0) == next_h for m in _NATURAL_MALEFICS)
        if prev_mal and next_mal:
            penalty -= h_wt
            notes.append(
                f"H{career_h} is hemmed by malefics (Papa Kartari) — "
                f"H{prev_h} and H{next_h} carry malefic planets; "
                "career-house energy is squeezed; outcomes arrive under friction."
            )
    return max(-0.08, penalty), notes


# ─────────────────────────────────────────────────────────────────────────────
# G8 — Kala Sarpa Yoga
# ─────────────────────────────────────────────────────────────────────────────

_KSY_NAMES: Dict[int, str] = {
    1: "Ananta", 2: "Kulika", 3: "Vasuki", 4: "Shankha",
    5: "Padma", 6: "Mahapadma", 7: "Takshaka", 8: "Karkotaka",
    9: "Shankhachuda", 10: "Ghatak", 11: "Vishadhari", 12: "Sheshanaga",
}


def _g8_kala_sarpa(inp: EnhancerInput) -> Tuple[float, str, List[str]]:
    ph = inp.planet_house
    rahu_h = ph.get("Rahu", 0)
    ketu_h = ph.get("Ketu", 0)
    if not rahu_h or not ketu_h:
        return 0.0, "", []

    bodies = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    planet_hs = [ph[p] for p in bodies if ph.get(p, 0)]
    if not planet_hs:
        return 0.0, "", []

    # Arc from Rahu to Ketu (clockwise = increasing house numbers)
    arc: Set[int] = set()
    h = rahu_h % 12 + 1
    while h != ketu_h:
        arc.add(h)
        h = h % 12 + 1

    if all(p_h in arc or p_h == rahu_h for p_h in planet_hs):
        name = _KSY_NAMES.get(rahu_h, f"KSY-Rahu{rahu_h}")
        note = (
            f"{name} Kala Sarpa Yoga — all planets hemmed between Rahu (H{rahu_h}) and "
            f"Ketu (H{ketu_h}). Career typically rises in dramatic cycles with breakthrough "
            "near Rahu/Ketu transit of own axis; sustained stability is harder to maintain."
        )
        return -0.05, name, [note]
    return 0.0, "", []


# ─────────────────────────────────────────────────────────────────────────────
# G9 — Upachaya Malefic Growth Over Time
# ─────────────────────────────────────────────────────────────────────────────

def _g9_upachaya_growth(inp: EnhancerInput) -> float:
    """Growth factor for malefics in upachaya houses as native ages."""
    if not inp.dob or not inp.period_start:
        return 1.0
    age = (inp.period_start - inp.dob).days / 365.25
    ph = inp.planet_house

    factor = 1.0
    for pl in (inp.md_lord, inp.ad_lord):
        if pl not in _NATURAL_MALEFICS:
            continue
        if ph.get(pl, 0) in _UPACHAYA:
            # 0.7 at age 20, grows to 1.25 at age 55+
            growth = 0.7 + min(0.55, max(0.0, (age - 20) / 35.0) * 0.55)
            factor = max(factor, growth)
    return round(factor, 3)


# ─────────────────────────────────────────────────────────────────────────────
# G10 — Sooksham Dasha (4th level)
# ─────────────────────────────────────────────────────────────────────────────

def _g10_sooksham_dashas(
    pd_lord: str,
    pd_start: date,
    pd_end: date,
) -> List[Dict]:
    """Expand a Pratyantardasha into 9 Sooksham (4th-level) sub-periods."""
    total_days = (pd_end - pd_start).days
    if total_days <= 0 or pd_lord not in _VIMSHOTTARI_ORDER:
        return []

    total_vimsh_years = sum(_VIMSHOTTARI_YEARS.values())  # 120
    start_idx = _VIMSHOTTARI_ORDER.index(pd_lord)
    sds: List[Dict] = []
    cursor = pd_start

    for i in range(9):
        sd_lord = _VIMSHOTTARI_ORDER[(start_idx + i) % 9]
        sd_days = round(total_days * _VIMSHOTTARI_YEARS[sd_lord] / total_vimsh_years)
        sd_end = min(cursor + timedelta(days=max(1, sd_days)), pd_end)
        sds.append({
            "sd_lord": sd_lord,
            "start": cursor.isoformat(),
            "end": sd_end.isoformat(),
            "days": (sd_end - cursor).days,
        })
        cursor = sd_end
        if cursor >= pd_end:
            break

    if sds and cursor < pd_end:
        sds[-1]["end"] = pd_end.isoformat()
    return sds


# ─────────────────────────────────────────────────────────────────────────────
# G11 — Dasha Sandhi (Junction Periods)
# ─────────────────────────────────────────────────────────────────────────────

def _g11_dasha_sandhi(inp: EnhancerInput) -> Tuple[float, bool, List[str]]:
    """Penalise periods overlapping MD/AD lord junctions (Dasha Chidra).

    Gap fix (2026-07-05 audit): `inp.period_start`/`period_end` are usually an
    entire Antardasha block's own start/end dates (a full AD is, by definition,
    bounded by two entries in `ad_change_dates` — its own opening and closing
    transition). The old overlap check compared the period's boundary against
    ALL change dates including its own, so `period_start <= change_date+90d`
    was trivially true whenever `change_date == period_start` (delta with
    itself is 0 days). That made every single AD block — regardless of whether
    it ran 10 months or 3 years — register as "Dasha Sandhi (junction period)"
    for its ENTIRE duration, since a period always borders itself. In a real
    generated report this produced "Sandhi Period" / "Dasha Chidra" on every
    single year of a 5-year roadmap (Jupiter-Sun, Jupiter-Moon, Jupiter-Mars,
    Jupiter-Rahu all tagged identically), which is not how dasha sandhi works
    classically — it's a narrow ~90-day-each-side window around a transition,
    not a label for the whole antardasha that transition happens to open or
    close. Fixed by requiring the junction-adjacent window to cover a
    meaningful share (>=50%) of the period's own length, so only genuinely
    short/transition-dominated periods (e.g. a ~10-month AD where the 180-day
    combined buffer is most of it) get flagged, while multi-year ADs whose
    edges merely happen to be dasha boundaries (true of every AD) do not.
    """
    if not inp.period_start or not inp.period_end:
        return 0.0, False, []

    SANDHI_DAYS = 90  # 3 months each side
    delta = timedelta(days=SANDHI_DAYS)
    notes: List[str] = []
    period_len_days = (inp.period_end - inp.period_start).days or 1

    for change_date in inp.md_change_dates + inp.ad_change_dates:
        window_start = change_date - delta
        window_end = change_date + delta
        overlap_start = max(inp.period_start, window_start)
        overlap_end = min(inp.period_end, window_end)
        overlap_days = (overlap_end - overlap_start).days
        if overlap_days <= 0:
            continue
        if (overlap_days / period_len_days) < 0.5:
            # This period merely borders a transition at one edge (true of
            # every AD block by definition) but the junction-adjacent window
            # doesn't dominate the period — don't blanket-label it sandhi.
            continue
        notes.append(
            f"Dasha Sandhi (junction): this period falls within {SANDHI_DAYS} days of "
            f"a Mahadasha/Antardasha change on {change_date}, and that junction window "
            "covers most of the period's own span. Junction periods are inherently "
            "unstable — avoid major decisions; consolidate instead."
        )
        return -0.07, True, notes

    return 0.0, False, []


# ─────────────────────────────────────────────────────────────────────────────
# G12 — Nakshatra Transit Triggers
# ─────────────────────────────────────────────────────────────────────────────

_SLOW_PLANETS = ("Jupiter", "Saturn", "Rahu", "Ketu", "Mars")


def _g12_nakshatra_triggers(inp: EnhancerInput) -> List[str]:
    """Return flags when any slow-moving transit planet enters natal MD/AD Nakshatra."""
    flags: List[str] = []
    natal = inp.planet_natal_degrees
    transit = inp.planet_transit_degrees

    for dasha_lord in {inp.md_lord, inp.ad_lord}:
        if not dasha_lord:
            continue
        n_deg = natal.get(dasha_lord)
        if n_deg is None:
            continue
        natal_nak = get_nakshatra(n_deg)

        for t_planet in _SLOW_PLANETS:
            t_deg = transit.get(t_planet)
            if t_deg is None:
                continue
            t_nak = get_nakshatra(t_deg)
            if t_nak == natal_nak and t_planet != dasha_lord:
                flags.append(
                    f"NAK_TRIGGER_{t_planet.upper()}_IN_"
                    f"{natal_nak.upper().replace(' ', '_')}_OF_{dasha_lord.upper()}"
                )
    return flags


# ─────────────────────────────────────────────────────────────────────────────
# G13 — PAV Transit Bindu Score
# ─────────────────────────────────────────────────────────────────────────────

def _g13_pav_transit_score(
    planet: str,
    transit_house: int,
    pav_data: Dict[str, Dict[str, int]],
) -> float:
    """PAV bindu score for planet transiting a house (0–1; 1 = 8/8 bindus)."""
    if not pav_data or not transit_house:
        return 0.5  # neutral default when data absent
    bindus = float(pav_data.get(planet, {}).get(str(transit_house), 0) or 0)
    return round(bindus / 8.0, 3)


def _g13_career_pav_score(inp: EnhancerInput) -> float:
    """Average PAV score of MD/AD lords over career-relevant transit houses."""
    projected = inp.transit_projected
    if not projected or not inp.pav_data:
        return 0.5
    scores: List[float] = []
    for pl in (inp.md_lord, inp.ad_lord):
        t_h = projected.get(pl, 0)
        if not t_h:
            continue
        scores.append(_g13_pav_transit_score(pl, t_h, inp.pav_data))
    return round(sum(scores) / max(1, len(scores)), 3) if scores else 0.5


# GAP FIX (2026-07-05, career timeline audit): G13 above only scores PAV bindus
# for whichever planet happens to be the current MD/AD lord. Classical gochara
# phalam is built specifically around Jupiter, Saturn, Rahu, and Ketu transits
# regardless of dasha lordship — a Venus-MD/Mercury-AD period with a strong
# Jupiter or Saturn transit previously got zero PAV credit. This function scores
# those four slow-movers unconditionally so their transit strength is never
# silently dropped just because they aren't the running dasha lord.
_SLOW_TRANSIT_PLANETS: tuple = ("Jupiter", "Saturn", "Rahu", "Ketu")


def _g13b_slow_planet_pav_score(inp: EnhancerInput) -> float:
    """Average PAV bindu score for Jupiter/Saturn/Rahu/Ketu transits, independent
    of whether they are the current dasha lord."""
    projected = inp.transit_projected
    if not projected or not inp.pav_data:
        return 0.5
    scores: List[float] = []
    for pl in _SLOW_TRANSIT_PLANETS:
        t_h = projected.get(pl, 0)
        if not t_h:
            continue
        scores.append(_g13_pav_transit_score(pl, t_h, inp.pav_data))
    return round(sum(scores) / max(1, len(scores)), 3) if scores else 0.5


# ─────────────────────────────────────────────────────────────────────────────
# G14 — Kaksha-Level Ashtakavarga Activation
# ─────────────────────────────────────────────────────────────────────────────

_KAKSHA_SEQUENCE = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon", "Lagna"]
_KAKSHA_DEGREES = 30.0 / 8  # 3.75° per kaksha


def _g14_kaksha_activation(inp: EnhancerInput) -> bool:
    """True if MD lord's kaksha is activated by a slow transiting planet.

    GAP-FIX (2026-08-22, audit item #18): previously "activation" only
    checked that the transiting planet's *name* matched the kaksha lord and
    that SOME transit-degree entry existed for it (`transit.get(t_planet) is
    not None`) — never the transiting planet's actual degree/position. Per
    Kakshya theory (each 30° sign divides into 8 kakshyas of 3°45' each,
    ruled in sequence Saturn-Jupiter-Mars-Sun-Venus-Mercury-Moon-Lagna, a
    sequence this module already uses correctly), activation is explicitly
    degree-dependent: a kakshya's effects trigger only when a planet is
    actually positioned within that kakshya's arc, not by name-match alone.
    Now requires genuine "own kakshya" (swakakshya) positional confirmation:
    the candidate planet must itself be transiting through a kakshya slot
    that IT rules (computed the same way the MD lord's natal kakshya lord is
    derived below), not merely be present in the transit-degree table.
    """
    natal = inp.planet_natal_degrees
    transit = inp.planet_transit_degrees
    transit_houses = inp.transit_projected

    md_deg = natal.get(inp.md_lord)
    if md_deg is None:
        return False

    # Determine kaksha lord for MD lord's natal position
    sign_deg = md_deg % 30.0  # position within its sign
    kaksha_idx = int(sign_deg / _KAKSHA_DEGREES)
    # Offset by house number (H1 starts Saturn, H2 starts Jupiter, etc.)
    h = inp.planet_house.get(inp.md_lord, 1)
    rotated_idx = (kaksha_idx + (h - 1)) % 8
    kaksha_lord = _KAKSHA_SEQUENCE[rotated_idx]

    # Check if any slow transit planet is the kaksha lord AND is itself
    # currently positioned in a kakshya slot it rules (own-kakshya/
    # swakakshya) — genuine positional activation, not name-match alone.
    for t_planet in _SLOW_PLANETS:
        if t_planet != kaksha_lord:
            continue
        t_deg = transit.get(t_planet)
        if t_deg is None:
            continue
        t_house = transit_houses.get(t_planet) if transit_houses else None
        if not t_house:
            continue  # can't verify degree-position without a transit house
        t_sign_deg = t_deg % 30.0
        t_kaksha_idx = int(t_sign_deg / _KAKSHA_DEGREES)
        t_rotated_idx = (t_kaksha_idx + (t_house - 1)) % 8
        if _KAKSHA_SEQUENCE[t_rotated_idx] == t_planet:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# G15 — Jaimini Chara Dasha
# ─────────────────────────────────────────────────────────────────────────────

# GAP FIX (2026-08-21, Gap_Analysis_2026-07 §1.1/§1.2): the previous
# `_CHARA_DASHA_YEARS` fixed lookup table (Aries=7, Taurus=6, ... keyed only by
# sign name) ignored the chart entirely, and the walk below always advanced
# forward through the zodiac regardless of lord placement -- both contradict
# the classical technique's chart-sensitivity. Removed in favor of
# jyotish.astro.compute_chara_dasha_sequence(), the canonical "Standard Jaimini
# (Parashara-compatible)" implementation already used elsewhere in this
# codebase (see that function's docstring for the odd/even-count direction
# rule and the count-to-own-lord duration rule, including the count==1 -> 12
# year exception). Kept here only as a historical note, not read anywhere.


def _g15_chara_dasha_score(inp: EnhancerInput) -> float:
    """Career affinity score from the current Jaimini Chara Dasha sign.

    GAP FIX (2026-08-21, Gap_Analysis_2026-07 §1.1/§1.2): direction and
    per-sign duration now come from jyotish.astro.compute_chara_dasha_sequence
    (chart-sensitive, odd/even-count direction rule), not the old forward-only
    walk over a fixed duration table."""
    if not inp.dob or not inp.period_start or not inp.lagna_sign:
        return 0.5
    if inp.lagna_sign not in _SIGN_SEQ:
        return 0.5

    # planets_d1 shape expected by compute_chara_dasha_sequence: {planet: {"sign": str}}.
    # This scorer only needs sign-level lordship, so degree is omitted.
    planets_d1 = {p: {"sign": s} for p, s in inp.planet_sign.items() if s}
    sequence = compute_chara_dasha_sequence(inp.lagna_sign, planets_d1)
    if not sequence:
        # Unresolvable chart (e.g. insufficient lord-placement data) -- neutral score,
        # same fallback behavior as the previous implementation's early-outs.
        return 0.5

    age = (inp.period_start - inp.dob).days / 365.25
    cumulative = 0.0
    current_sign = inp.lagna_sign
    for entry in sequence:
        years = entry["years"]
        if cumulative + years > age:
            current_sign = entry["sign"]
            break
        cumulative += years
    else:
        # Age exceeds the full 12-sign cycle length (rare, but the fixed 66-year
        # forward-only table could never reach this branch); fall back to the
        # last sign in the sequence rather than leaving the Lagna sign stale.
        if sequence:
            current_sign = sequence[-1]["sign"]

    ak = inp.atmakaraka
    if not ak:
        return 0.5
    ak_sign = inp.planet_sign.get(ak, "")
    if not ak_sign or ak_sign not in _SIGN_SEQ:
        return 0.5

    ak_idx = _SIGN_SEQ.index(ak_sign)
    cur_idx = _SIGN_SEQ.index(current_sign)
    dist = (cur_idx - ak_idx) % 12 + 1

    if dist in _TRIKONA:
        return 0.85
    elif dist in _KENDRA:
        return 0.72
    elif dist in {2, 11}:
        return 0.60
    elif dist in _DUSTHANA:
        return 0.30
    return 0.45


# ─────────────────────────────────────────────────────────────────────────────
# G15b — Vimshottari Dasha Longevity Filter
# GAP FIX (2026-08-17): Step 7 asks whether this period's MD lord has "long,
# stable" career-relevant support ahead, vs. being about to hand off from a
# strong career significator to a weak one. astro_enhancer.py previously had
# no Vimshottari-longevity concept at all (only Yogini/Chara/Ashtottari
# sub-systems, and a per-period read, never a forward-looking one). Reuses
# the shared jyotish.dasha_longevity module built for Field_Determination,
# with a career-house-lordship-derived affinity dict standing in for
# Field_Determination's field_affinity (Job_Career has no per-field
# affinity concept — it scores career events generally, not field choice —
# so "affinity" here means "is this planet a career-house lord").
# ─────────────────────────────────────────────────────────────────────────────

_CAREER_LORDSHIP_HOUSES: Dict[int, float] = {10: 0.32, 11: 0.20, 2: 0.15, 6: 0.13, 9: 0.12, 7: 0.08}


def _career_lordship_affinity(inp: EnhancerInput) -> Dict[str, float]:
    """Build a lightweight 'career affinity' dict from house lordships, for
    reuse with the shared dasha-longevity scorer (which was designed for
    Field_Determination's per-field affinity weights)."""
    affinity: Dict[str, float] = {}
    for h, wt in _CAREER_LORDSHIP_HOUSES.items():
        lord = inp.house_lords.get(str(h), "")
        if lord:
            affinity[lord] = affinity.get(lord, 0.0) + wt
    return affinity


def _g15b_dasha_longevity(inp: EnhancerInput) -> float:
    """Return a 0-1 score (0.5 = neutral/no data) from the shared Vimshottari
    longevity filter's bounded multiplier."""
    if not inp.dasha_sequence or not inp.dob or not inp.period_start:
        return 0.5
    age_at_period = (inp.period_start - inp.dob).days / 365.25
    affinity = _career_lordship_affinity(inp)
    if not affinity:
        return 0.5
    result = score_dasha_longevity(inp.dasha_sequence, age_at_period, affinity)
    multiplier = result.get("multiplier", 1.0)
    # multiplier is bounded [0.90, 1.10]; map to a 0-1 score around 0.5 the
    # same way the rest of this module's sub-scores are expressed.
    return round(min(1.0, max(0.0, 0.5 + (multiplier - 1.0) * 5.0)), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G16 — Yogini Dasha
# ─────────────────────────────────────────────────────────────────────────────

_YOGINI_DATA: List[Tuple[str, str, int]] = [
    ("Mangala",  "Moon",    1),
    ("Pingala",  "Sun",     2),
    ("Dhanya",   "Jupiter", 3),
    ("Bhramari", "Mars",    4),
    ("Bhadrika", "Mercury", 5),
    ("Ulka",     "Saturn",  6),
    ("Siddha",   "Venus",   7),
    ("Sankata",  "Rahu",    8),
]

_YOGINI_CAREER_SCORE: Dict[str, float] = {
    "Mangala": 0.65, "Pingala": 0.70, "Dhanya": 0.80,
    "Bhramari": 0.55, "Bhadrika": 0.75, "Ulka": 0.45,
    "Siddha": 0.85, "Sankata": 0.38,
}


def _g16_yogini_dasha(inp: EnhancerInput) -> Tuple[str, str, float]:
    """Return (yogini_name, ruling_planet, career_score)."""
    if not inp.dob or not inp.period_start or inp.moon_nakshatra_pada_num == 0:
        return "", "", 0.5

    # GAP-FIX (2026-08, astrological audit): the STARTING Yogini lord is
    # classically determined by birth NAKSHATRA alone -- every pada of a
    # given nakshatra shares the same starting Yogini. The previous
    # `(pada_num - 1) % 8` derived the start index from the absolute
    # 0-based pada number (nak_idx*4 + pada_offset, see EnhancerInput
    # construction), which rotates the starting Yogini across the four
    # padas of the SAME nakshatra instead of giving them all the one
    # classically-correct lord. moon_nakshatra_pada_num is built as
    # `nak_idx * 4 + (pada - 1)`, so integer-dividing by 4 recovers the
    # nakshatra index exactly (the pada offset is always 0-3, i.e. always
    # < 4), letting the start index be derived from nakshatra alone without
    # needing a new field on EnhancerInput. Same fix, same reasoning, as
    # Field_Determination/field_methods/yogini_dasha.py's
    # get_current_yogini() -- this function is that module's sibling
    # implementation and had the identical bug.
    start_idx = (inp.moon_nakshatra_pada_num // 4) % 8
    elapsed = (inp.period_start - inp.dob).days / 365.25
    total_years = sum(y for _, _, y in _YOGINI_DATA)  # 36
    elapsed_in_cycle = elapsed % total_years
    cumulative = 0.0

    for i in range(8):
        name, planet, years = _YOGINI_DATA[(start_idx + i) % 8]
        if cumulative + years > elapsed_in_cycle:
            return name, planet, _YOGINI_CAREER_SCORE.get(name, 0.5)
        cumulative += years

    return _YOGINI_DATA[start_idx % 8][0], _YOGINI_DATA[start_idx % 8][1], 0.5


# ─────────────────────────────────────────────────────────────────────────────
# G17 — Ashtottari Dasha
# ─────────────────────────────────────────────────────────────────────────────

_ASHTOTTARI_PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Saturn", "Jupiter", "Rahu", "Venus"]
_ASHTOTTARI_YEARS  = {
    "Sun": 6, "Moon": 15, "Mars": 8, "Mercury": 17,
    "Saturn": 10, "Jupiter": 19, "Rahu": 12, "Venus": 21,
}

_ASHTOTTARI_CAREER: Dict[str, float] = {
    "Sun": 0.68, "Moon": 0.60, "Mars": 0.55, "Mercury": 0.72,
    "Saturn": 0.58, "Jupiter": 0.80, "Rahu": 0.65, "Venus": 0.75,
}


def _g17_should_use_ashtottari(rahu_house: int, moon_house: int) -> bool:
    """Ashtottari applies when Rahu is in a kendra from the Moon."""
    if not rahu_house or not moon_house:
        return False
    rel = (rahu_house - moon_house) % 12 + 1
    return rel in _KENDRA


def _g17_ashtottari_period(inp: EnhancerInput) -> Tuple[bool, str, float]:
    """Return (is_active, current_lord, career_score)."""
    if not _g17_should_use_ashtottari(inp.rahu_house, inp.moon_house):
        return False, "", 0.5
    if not inp.dob or not inp.period_start:
        return True, "", 0.5

    moon_nak_lord = inp.moon_nakshatra_lord
    if moon_nak_lord not in _ASHTOTTARI_PLANETS:
        return True, "", 0.5

    elapsed = (inp.period_start - inp.dob).days / 365.25
    total = sum(_ASHTOTTARI_YEARS.values())  # 108
    elapsed_in_cycle = elapsed % total
    start_idx = _ASHTOTTARI_PLANETS.index(moon_nak_lord)
    cumulative = 0.0

    for i in range(8):
        pl = _ASHTOTTARI_PLANETS[(start_idx + i) % 8]
        yrs = _ASHTOTTARI_YEARS[pl]
        if cumulative + yrs > elapsed_in_cycle:
            score = _ASHTOTTARI_CAREER.get(pl, 0.6)
            return True, pl, score
        cumulative += yrs

    return True, moon_nak_lord, 0.5


# ─────────────────────────────────────────────────────────────────────────────
# G18 — D10 Dashamsha Full Analysis
# ─────────────────────────────────────────────────────────────────────────────

def _g18_d10_full(inp: EnhancerInput) -> float:
    """Full D10 career chart score: lagna lord, H10 lord, occupancy, dignity."""
    score = 0.0
    d10_ll = _SIGN_LORD.get(inp.d10_lagna_sign, "")
    d10_h10l = inp.d10_house_lords.get("10", "")
    occ = inp.d10_house_occupancy

    # D10 lagna lord is dasha lord
    if d10_ll and d10_ll == inp.md_lord:
        score += 0.15
    elif d10_ll and d10_ll == inp.ad_lord:
        score += 0.08

    # D10 H10 lord is dasha lord
    if d10_h10l and d10_h10l == inp.md_lord:
        score += 0.20
    elif d10_h10l and d10_h10l == inp.ad_lord:
        score += 0.10

    # House occupancy bonus
    career_wts = {10: 0.32, 11: 0.20, 2: 0.15, 6: 0.13, 9: 0.12, 7: 0.08}
    for h, wt in career_wts.items():
        occupants = occ.get(str(h), []) or []
        if inp.md_lord in occupants:
            score += wt * 0.12
        if inp.ad_lord in occupants and inp.ad_lord != inp.md_lord:
            score += wt * 0.06

    # Dignity bonus from D10 (if available in varga_dignities)
    d10_dig = inp.varga_dignities.get("D10", {})
    for pl in {inp.md_lord, inp.ad_lord}:
        dig = str(d10_dig.get(pl, "")).lower()
        if dig in ("exalted", "own", "moolatrikona"):
            score += 0.06
        elif dig in ("debilitated", "fallen"):
            score -= 0.04

    # GAP FIX (2026-08-17): D10 kendra/trikona placement of D10 lagna lord and
    # H10 lord — the framework's Step 4 "planets in D10 kendras/trikonas" check
    # was previously absent; D10 was reduced to a lordship/dignity scalar only.
    d10_ll_house = 0
    if d10_ll:
        # Find which D10 house the D10 lagna lord itself occupies.
        for h_str, occupants in occ.items():
            if d10_ll in (occupants or []):
                try:
                    d10_ll_house = int(h_str)
                except ValueError:
                    pass
                break
    if d10_ll_house in _KENDRA:
        score += 0.05
    elif d10_ll_house in _TRIKONA:
        score += 0.07

    return round(min(1.0, max(0.0, score)), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G19 — D60 Shashtyamsha Modifier
# ─────────────────────────────────────────────────────────────────────────────

def _g19_d60_modifier(inp: EnhancerInput) -> float:
    """D60 dignity modifier — BPHS calls this the most important varga."""
    d60_dig = inp.varga_dignities.get("D60", {})
    if not d60_dig:
        return 0.0
    modifier = 0.0
    for pl, wt in [(inp.md_lord, 0.08), (inp.ad_lord, 0.04)]:
        dig = str(d60_dig.get(pl, "")).lower()
        if dig in ("exalted", "moolatrikona"):
            modifier += wt
        elif dig == "own":
            modifier += wt * 0.75
        elif dig == "friendly":
            modifier += wt * 0.40
        elif dig in ("enemy", "debilitated", "fallen"):
            modifier -= wt * 0.75
    return round(max(-0.10, min(0.10, modifier)), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G20 — D27 Bhamsha (Nakshatramsha) Modifier
# ─────────────────────────────────────────────────────────────────────────────

_D27_STRENGTH_MAP: Dict[str, float] = {
    "strong": 0.05, "moderate": 0.01, "weak": -0.04, "very_weak": -0.07,
}


def _g20_d27_modifier(inp: EnhancerInput) -> float:
    """D27 strength modifier — links Nakshatra strength to Vimshottari timing."""
    modifier = 0.0
    for pl in {inp.md_lord, inp.ad_lord}:
        s = inp.d27_planet_strengths.get(pl, "moderate")
        modifier += _D27_STRENGTH_MAP.get(s, 0.0)
    return round(max(-0.08, min(0.08, modifier)), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G21 — Vimsopaka Bala (aggregate varga strength)
# ─────────────────────────────────────────────────────────────────────────────

# GAP-FIX (2026-08-22, audit item — Vimshopaka weight proportions): replaced
# with the classical Shodasha Varga ("sixteen-fold") weight table per BPHS —
# Rasi 3.5, Hora 1, Drekkana 1, Shodasamsa(D16) 2, Navamsa 3, Shashtiamsa(D60)
# 4, Trimsamsa(D30) 1, remaining nine divisions 0.5 each (9 x 0.5 = 4.5);
# 3.5+1+1+2+3+4+1+4.5 = 20 exactly, matching the "twenty units" the technique
# is named for. The prior table (D1=6, D9=3, D10=5, D60=5, sum 50) did not
# match any published classical scheme: it overweighted D10 (career-relevant
# Dasamsa) roughly 4x versus tradition (0.5/20, since Vimshopaka Bala measures
# GENERAL planetary strength, not career-specific strength) and understated
# D60 (Shashtiamsa), classically the single heaviest varga at 4/20 (20%) for
# its fine-grained decisiveness. _g21_vimsopaka_bala() below renormalizes by
# present_weight (the sum of only the vargas actually populated), so an
# absolute total of exactly 20 is not functionally required for scoring to
# work, but the RELATIVE proportions between vargas now match BPHS.
_VIMSOPAKA_WEIGHTS: Dict[str, float] = {
    "D1": 3.5, "D2": 1.0, "D3": 1.0, "D4": 0.5, "D7": 0.5, "D9": 3.0,
    "D10": 0.5, "D12": 0.5, "D16": 2.0, "D20": 0.5, "D24": 0.5, "D27": 0.5,
    "D30": 1.0, "D40": 0.5, "D45": 0.5, "D60": 4.0,
}

_DIG_SCORE_MAP = {
    "exalted": 1.0, "moolatrikona": 0.875, "own": 0.75,
    "friendly": 0.50, "neutral": 0.375, "enemy": 0.25,
    "debilitated": 0.125, "fallen": 0.125,
}


def _g21_vimsopaka_bala(planet: str, varga_dignities: Dict[str, Dict[str, str]]) -> float:
    """Vimsopaka Bala for a planet (0-1; 1 = maximum across all vargas).

    V1.3 merge plan item 3: renormalize over only the vargas actually
    present in varga_dignities, instead of dividing by the fixed weight of
    all 16 classical vargas. This engine currently only populates a subset
    (D1/D9/D10/D20/D24/D27 per the V1.3 audit), so the previous fixed-weight
    version silently defaulted every missing varga to "neutral" (0.375),
    systematically dragging every planet's score toward 0.375 regardless of
    its true strength in the vargas that were actually computed.
    """
    present_weight = 0
    score = 0.0
    for varga, wt in _VIMSOPAKA_WEIGHTS.items():
        varga_map = varga_dignities.get(varga)
        if not varga_map or planet not in varga_map:
            continue
        dig = str(varga_map[planet]).lower()
        score += wt * _DIG_SCORE_MAP.get(dig, 0.375)
        present_weight += wt
    if present_weight == 0:
        return 0.5  # no data at all: neutral default
    return round(score / present_weight, 3)


def _g21_combined_vimsopaka(inp: EnhancerInput) -> float:
    if not inp.varga_dignities:
        return 0.5
    s_md = _g21_vimsopaka_bala(inp.md_lord, inp.varga_dignities)
    s_ad = _g21_vimsopaka_bala(inp.ad_lord, inp.varga_dignities)
    return round(s_md * 0.65 + s_ad * 0.35, 3)


# ─────────────────────────────────────────────────────────────────────────────
# G22 — Surya Lagna Cross-Validation
# ─────────────────────────────────────────────────────────────────────────────

def _g22_surya_lagna_bonus(inp: EnhancerInput) -> float:
    """Bonus when MD/AD lords activate career houses from Sun sign (Surya Lagna)."""
    sun_h = inp.planet_house.get("Sun", 0)
    if not sun_h:
        return 0.0
    career = {2, 6, 10, 11}
    bonus = 0.0
    for pl in {inp.md_lord, inp.ad_lord}:
        pl_h = inp.planet_house.get(pl, 0)
        if pl_h:
            surya_h = (pl_h - sun_h) % 12 + 1
            if surya_h in career:
                bonus += 0.02
    return round(min(0.04, bonus), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G23 — Arudha Pada (A1, A10)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_arudha(house: int, lord_house: int) -> int:
    """Compute Arudha Pada for a given house and its lord's house position."""
    steps = (lord_house - house) % 12
    arudha = (lord_house + steps - 1) % 12 + 1
    # Correction: arudha must not fall in same or 7th house
    if arudha == house:
        arudha = (house + 9 - 1) % 12 + 1
    elif arudha == (house + 6 - 1) % 12 + 1:
        arudha = (house + 3 - 1) % 12 + 1
    return arudha


def _g23_arudha_bonus(inp: EnhancerInput) -> Tuple[float, List[str]]:
    """Bonus when dasha lord activates A1 (Arudha Lagna) or A10 (Rajyapada)."""
    hl = inp.house_lords
    ph = inp.planet_house

    h1l = hl.get("1", "")
    h10l = hl.get("10", "")
    h1l_h = ph.get(h1l, 0) if h1l else 0
    h10l_h = ph.get(h10l, 0) if h10l else 0

    if not h1l_h or not h10l_h:
        return 0.0, []

    a1  = _compute_arudha(1, h1l_h)
    a10 = _compute_arudha(10, h10l_h)

    bonus = 0.0
    notes: List[str] = []
    for pl in {inp.md_lord, inp.ad_lord}:
        pl_h = ph.get(pl, 0)
        if pl_h in (a1, a10):
            bonus += 0.04
            pada = "A1 (Arudha Lagna)" if pl_h == a1 else "A10 (Karma Pada/Rajyapada)"
            notes.append(
                f"{pl} occupies {pada} (H{pl_h}) — worldly career image and "
                "professional reputation are directly activated; high external visibility."
            )
        # Also check if planet lords a house = a1 or a10
        for h_str, lord in hl.items():
            if lord == pl:
                try:
                    if int(h_str) in (a1, a10):
                        bonus += 0.02
                except ValueError:
                    pass

    return round(min(0.08, bonus), 3), notes


# ─────────────────────────────────────────────────────────────────────────────
# G24 — Karakamsha Lagna
# ─────────────────────────────────────────────────────────────────────────────

def _g24_karakamsha_bonus(inp: EnhancerInput) -> float:
    """Bonus when dasha lord activates houses from Karakamsha Lagna (AK in D9)."""
    kk_sign = inp.jaimini_chara_lagna_sign
    if not kk_sign or kk_sign not in _SIGN_SEQ or not inp.lagna_sign:
        return 0.0
    if inp.lagna_sign not in _SIGN_SEQ:
        return 0.0

    kk_idx  = _SIGN_SEQ.index(kk_sign)
    lag_idx = _SIGN_SEQ.index(inp.lagna_sign)
    kk_house = (kk_idx - lag_idx) % 12 + 1

    # Career-relevant houses from Karakamsha: 1st (identity), 5th (intellect),
    # 9th (fortune/dharma), 10th (karma), 2nd (wealth), 11th (gains)
    career_from_kk = {1, 2, 5, 9, 10, 11}
    bonus = 0.0
    for pl in {inp.md_lord, inp.ad_lord}:
        pl_h = inp.planet_house.get(pl, 0)
        if pl_h:
            rel_h = (pl_h - kk_house) % 12 + 1
            if rel_h in career_from_kk:
                bonus += 0.025
    return round(min(0.05, bonus), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G24b — Amatyakaraka (Jaimini)
# GAP FIX (2026-08-17): the framework's Step 5 calls the Amatyakaraka "often
# more precise than the 10th lord" for career, but it was never scored by
# this module (only Atmakaraka fed G15/G24). AmK is a real field on the
# shared jyotish.engine payload — this wires it into the career blend here.
# ─────────────────────────────────────────────────────────────────────────────

_CAREER_HOUSES_AMK = {2, 6, 9, 10, 11}


def _g24b_amatyakaraka_score(inp: EnhancerInput) -> float:
    """Career-alignment score (0-1, 0.5=neutral) from the Amatyakaraka's
    house placement, dasha-lordship, and dignity."""
    amk = inp.amatyakaraka
    if not amk:
        return 0.5

    score = 0.5
    amk_house = inp.planet_house.get(amk, 0)
    if amk_house in _CAREER_HOUSES_AMK:
        score += 0.15
    elif amk_house in _DUSTHANA:
        score -= 0.10

    if amk == inp.md_lord:
        score += 0.15
    elif amk == inp.ad_lord:
        score += 0.08

    amk_sign = inp.planet_sign.get(amk, "")
    if amk_sign:
        # Reuse whatever dignity data is already tracked for D1 via varga_dignities
        # keyed "D1" if present; otherwise skip (no dignity source duplicated here).
        d1_dig = inp.varga_dignities.get("D1", {})
        dig = str(d1_dig.get(amk, "")).lower()
        if dig in ("exalted", "own", "moolatrikona"):
            score += 0.05
        elif dig in ("debilitated", "fallen"):
            score -= 0.05

    return round(min(1.0, max(0.0, score)), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G25 — KP Sub-Sub-Lord (4th level)
# ─────────────────────────────────────────────────────────────────────────────

def _g25c_kp_subfield_hint(inp: EnhancerInput) -> str:
    """Advisory sub-field narrowing (GAP FIX 2026-08-17, Step 6) — derives a
    specialization orientation from the H10 cuspal chain, e.g. distinguishing
    a Mars-ruled (interventional) vs Mercury-ruled (diagnostic) orientation
    within a broad field like medicine. Does not affect any score/ranking."""
    h10 = inp.kp_cusps_full.get("H10", {}) or {}
    result = narrow_field_specialization(
        field_label="",
        sub_lord=h10.get("sub_lord", ""),
        sub_sub_lord=h10.get("sub_sub_lord", ""),
        star_lord=h10.get("star_lord", ""),
    )
    return result["sub_field_hint"]


def _g25_kp_ssl_score(inp: EnhancerInput) -> float:
    """KP 4th-level (sub-sub-lord) alignment for career cusps."""
    career_wts = {"H10": 0.32, "H11": 0.20, "H2": 0.15, "H6": 0.13, "H9": 0.12, "H7": 0.08}  # GAP FIX (2026-08-17): added H9/H7
    score = 0.0
    for cusp, wt in career_wts.items():
        cusp_data = inp.kp_cusps_full.get(cusp, {}) or {}
        ssl = cusp_data.get("sub_sub_lord", "")
        if ssl == inp.md_lord:
            score += wt * 1.00
        elif ssl == inp.ad_lord:
            score += wt * 0.65
    return round(min(1.0, score), 3)


def _g25_kp_weighted_score(inp: EnhancerInput) -> float:
    """Multi-level KP scoring: sub-lord, sub-sub-lord, star-lord, sign-lord match
    against running MD/AD lords, weighted 0.40/0.25/0.20/0.10/0.05 (last 0.05 reserved
    for ruling-planet match if that data is available; otherwise redistribute proportionally
    across the other four).

    Reuses the same H10/H11/H6/H2 career-cusp house set and MD/AD-lord matching
    logic as `_g25_kp_ssl_score`, but additionally checks `sub_lord`, `star_lord`,
    and `sign_lord` (not just `sub_sub_lord`).

    Ruling-planet data (lagna/moon star & sub lords, day lord — see
    `_g26_kp_ruling_planets`) is a chart-level match, not a per-cusp field on
    `kp_cusps_full`, so there is no per-cusp "ruling_planet" to check here.
    The reserved 0.05 weight is therefore redistributed proportionally across
    the 4 active levels by dividing each nominal weight by 0.95, so the max
    achievable score remains 1.0:
        0.40/0.95 = 0.4211, 0.25/0.95 = 0.2632, 0.20/0.95 = 0.2105, 0.10/0.95 = 0.1053
    """
    _LEVEL_WEIGHTS_NOMINAL = {
        "sub_lord": 0.40, "sub_sub_lord": 0.25, "star_lord": 0.20, "sign_lord": 0.10,
    }
    _REDIST_FACTOR = 1.0 / 0.95   # redistribute the reserved 0.05 ruling-planet slot
    level_wts = {k: v * _REDIST_FACTOR for k, v in _LEVEL_WEIGHTS_NOMINAL.items()}
    career_wts = {"H10": 0.32, "H11": 0.20, "H2": 0.15, "H6": 0.13, "H9": 0.12, "H7": 0.08}  # GAP FIX (2026-08-17): added H9/H7

    score = 0.0
    for cusp, cusp_wt in career_wts.items():
        cusp_data = inp.kp_cusps_full.get(cusp, {}) or {}
        cusp_score = 0.0
        for level, level_wt in level_wts.items():
            lord = cusp_data.get(level, "")
            if lord == inp.md_lord:
                cusp_score += level_wt * 1.00
            elif lord == inp.ad_lord:
                cusp_score += level_wt * 0.65
        score += cusp_wt * min(1.0, cusp_score)
    return round(min(1.0, score), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G26 — KP Ruling Planets
# ─────────────────────────────────────────────────────────────────────────────

def _g26_kp_ruling_planets(inp: EnhancerInput) -> float:
    """Score based on MD/AD lord appearing in the current KP ruling planets."""
    ruling = {
        inp.lagna_star_lord, inp.lagna_sub_lord,
        inp.moon_star_lord, inp.moon_sub_lord,
        inp.day_lord,
    }
    ruling.discard("")
    if not ruling:
        return 0.5

    score = 0.40  # base
    if inp.md_lord in ruling:
        score += 0.35
    if inp.ad_lord in ruling and inp.ad_lord != inp.md_lord:
        score += 0.15
    return round(min(1.0, score), 3)


# ─────────────────────────────────────────────────────────────────────────────
# G27 — KP Nakshatra Significator Chain (full 4-level)
# ─────────────────────────────────────────────────────────────────────────────

_CAREER_HOUSES = {2, 6, 7, 9, 10, 11}  # GAP FIX (2026-08-17): added 7th/9th (Step 2)


def _g27_nakshatra_chain_score(planet: str, inp: EnhancerInput) -> float:
    """
    KP chain: planet → nakshatra lord of planet → significators of nakshatra lord.
    Return highest career-house alignment level as 0–1.
    """
    nak_lord = inp.planet_nakshatra_lord.get(planet, "")
    if not nak_lord:
        # Fallback: derive from natal degree
        deg = inp.planet_natal_degrees.get(planet)
        if deg is not None:
            nak_lord = get_nakshatra_lord(deg)

    if not nak_lord:
        return 0.0

    sig = inp.kp_significators.get(nak_lord, {})
    if not isinstance(sig, dict):
        return 0.0

    for level, score in [("level_1", 1.0), ("level_2", 0.80), ("level_3", 0.55), ("level_4", 0.30)]:
        for h in _CAREER_HOUSES:
            if h in sig.get(level, []):
                return score
    return 0.0


def _g27_combined_chain(inp: EnhancerInput) -> float:
    s_md = _g27_nakshatra_chain_score(inp.md_lord, inp)
    s_ad = _g27_nakshatra_chain_score(inp.ad_lord, inp)
    return round(s_md * 0.65 + s_ad * 0.35, 3)


# ─────────────────────────────────────────────────────────────────────────────
# G28–G31 — New Event Type Hints
# ─────────────────────────────────────────────────────────────────────────────

def _g28_entrepreneurship_hint(inp: EnhancerInput) -> bool:
    """H5 + H9 + H3 or Rahu in H1/H10 — entrepreneurship window."""
    ph = inp.planet_house
    hl = inp.house_lords
    active = set()
    for pl in (inp.md_lord, inp.ad_lord):
        active.add(ph.get(pl, 0))
        for h_str, lord in hl.items():
            if lord == pl:
                try:
                    active.add(int(h_str))
                except ValueError:
                    pass
    entro_houses = {5, 9, 3}
    rahu_h = ph.get("Rahu", 0)
    has_rahu_trigger = rahu_h in (1, 10) and "Rahu" in (inp.md_lord, inp.ad_lord)
    return (len(entro_houses & active) >= 2) or has_rahu_trigger


def _g29_equity_event_hint(inp: EnhancerInput) -> bool:
    """H2 + H5 + H8 + H11 combination — sudden wealth/equity event."""
    ph = inp.planet_house
    hl = inp.house_lords
    active = set()
    for pl in (inp.md_lord, inp.ad_lord):
        active.add(ph.get(pl, 0))
        for h_str, lord in hl.items():
            if lord == pl:
                try:
                    active.add(int(h_str))
                except ValueError:
                    pass
    equity_houses = {2, 5, 8, 11}
    return len(equity_houses & active) >= 3


def _g30_lateral_move_hint(inp: EnhancerInput) -> bool:
    """H6/H12 active + H10 without H1/H11 = lateral move signature."""
    ph = inp.planet_house
    hl = inp.house_lords
    active = set()
    for pl in (inp.md_lord, inp.ad_lord):
        active.add(ph.get(pl, 0))
        for h_str, lord in hl.items():
            if lord == pl:
                try:
                    active.add(int(h_str))
                except ValueError:
                    pass
    has_lateral = {6, 12} & active
    has_h10 = 10 in active
    has_growth = {1, 11} & active
    return bool(has_lateral and has_h10 and not has_growth)


def _g31_sandhi_event_hint(is_sandhi: bool) -> bool:
    return is_sandhi


def _g28_to_g31_hints(inp: EnhancerInput, is_sandhi: bool) -> List[str]:
    hints: List[str] = []
    if _g28_entrepreneurship_hint(inp):
        hints.append("ENTREPRENEURSHIP_WINDOW")
    if _g29_equity_event_hint(inp):
        hints.append("EQUITY_EVENT")
    if _g30_lateral_move_hint(inp):
        hints.append("LATERAL_MOVE")
    if _g31_sandhi_event_hint(is_sandhi):
        hints.append("SANDHI_PERIOD")
    return hints


# ─────────────────────────────────────────────────────────────────────────────
# G32 — Mars Special Aspects (4th and 8th)
# ─────────────────────────────────────────────────────────────────────────────

def _mars_aspect_houses(house: int) -> frozenset:
    """Mars aspects 4th and 8th house from its position.

    GAP-FIX (2026-08, astrological audit): to count the Nth house from a
    base house, the offset added before the mod must be N-2 (base house
    itself is offset 0 = "1st from itself"), i.e. `(house + N - 2) % 12 + 1`
    -- this file's own G23 `_compute_arudha` uses exactly that pattern
    (`(lord_house + steps - 1) % 12 + 1` for a 1-based `steps`). This
    function used `house + (N-1)` -- one too many -- so every aspect house
    landed one sign later than the classical target (e.g. Mars in house 1
    aspecting its 4th/8th should hit houses 4 and 8, but returned 5 and 9).
    Fixed to `house + N - 2`.
    """
    return frozenset([
        (house + 2) % 12 + 1,  # 4th aspect
        (house + 6) % 12 + 1,  # 8th aspect
    ])


def _g32_mars_aspect_flags(inp: EnhancerInput) -> List[str]:
    """Generate flags for Mars's 4th and 8th aspect on career houses."""
    projected = inp.transit_projected
    ph = inp.planet_house
    hl = inp.house_lords

    mars_h = projected.get("Mars", ph.get("Mars", 0))  # use transit if available
    if not mars_h:
        return []

    natal_h10l = hl.get("10", "")
    natal_h10l_h = ph.get(natal_h10l, 0) if natal_h10l else 0

    flags: List[str] = []
    mars_aspects = _mars_aspect_houses(mars_h)

    if 10 in mars_aspects:
        flags.append("MARS_4TH_OR_8TH_ASPECT_H10_CAREER_DRIVE")
    if natal_h10l_h and natal_h10l_h in mars_aspects:
        flags.append("MARS_ASPECTS_H10_LORD_DIRECT")
    for h in (11, 2, 6):
        if h in mars_aspects:
            flags.append(f"MARS_ASPECTS_H{h}_ACTIVATION")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# G33 — Full Mutual Natal Aspect Matrix (planet-on-planet aspects)
# ─────────────────────────────────────────────────────────────────────────────

def _g33_natal_aspect_modifier(inp: EnhancerInput) -> float:
    """
    Check aspects received by MD/AD lord from other natal planets.
    Jupiter aspecting MD/AD lord = boost; Saturn aspecting = delay modifier.
    """
    ph = inp.planet_house
    modifier = 0.0

    for target in (inp.md_lord, inp.ad_lord):
        target_h = ph.get(target, 0)
        if not target_h:
            continue

        jup_h = ph.get("Jupiter", 0)
        if jup_h and target_h in _jupiter_aspect_houses_set(jup_h):
            modifier += 0.03

        sat_h = ph.get("Saturn", 0)
        if sat_h and target_h in _saturn_aspect_houses_set(sat_h):
            modifier -= 0.02   # Saturn aspect = delay

        mars_h = ph.get("Mars", 0)
        if mars_h and target_h in _mars_aspect_houses(mars_h):
            modifier += 0.01   # Mars aspect = energy injection

    return round(max(-0.06, min(0.06, modifier)), 3)


def _jupiter_aspect_houses_set(house: int) -> frozenset:
    """Jupiter aspects 5th, 7th, 9th from its position.

    GAP-FIX (2026-08, astrological audit): same off-by-one as
    _mars_aspect_houses above -- offset must be N-2, not N-1.
    """
    return frozenset([
        (house + 3) % 12 + 1,
        (house + 5) % 12 + 1,
        (house + 7) % 12 + 1,
    ])


def _saturn_aspect_houses_set(house: int) -> frozenset:
    """Saturn aspects 3rd and 10th from its position.

    GAP-FIX (2026-08, astrological audit): same off-by-one as
    _mars_aspect_houses above -- offset must be N-2, not N-1.
    """
    return frozenset([
        (house + 1) % 12 + 1,
        (house + 8) % 12 + 1,
    ])


# ─────────────────────────────────────────────────────────────────────────────
# G34 — Transit Aspects vs. Transit Occupancy
# ─────────────────────────────────────────────────────────────────────────────

def _g34_transit_aspect_flags(inp: EnhancerInput) -> List[str]:
    """Generate flags for transit planets' aspects on natal career positions."""
    projected = inp.transit_projected
    ph = inp.planet_house
    hl = inp.house_lords
    flags: List[str] = []

    natal_h10l = hl.get("10", "")
    natal_h10l_h = ph.get(natal_h10l, 0) if natal_h10l else 0

    jup_h = projected.get("Jupiter", 0)
    if jup_h:
        for aspect_h in _jupiter_aspect_houses_set(jup_h):
            if aspect_h == 10:
                flags.append("JUP_TRANSIT_ASPECTS_H10_CAREER")
            elif aspect_h in (11, 2):
                flags.append(f"JUP_TRANSIT_ASPECTS_H{aspect_h}_GAINS")
            if natal_h10l_h and aspect_h == natal_h10l_h:
                flags.append("JUP_TRANSIT_ASPECTS_H10_LORD")

    sat_h = projected.get("Saturn", 0)
    if sat_h:
        for aspect_h in _saturn_aspect_houses_set(sat_h):
            if aspect_h == 10:
                flags.append("SAT_TRANSIT_ASPECTS_H10")
            if natal_h10l_h and aspect_h == natal_h10l_h:
                flags.append("SAT_TRANSIT_ASPECTS_H10_LORD")

    mars_t_h = projected.get("Mars", 0)
    if mars_t_h:
        for aspect_h in _mars_aspect_houses(mars_t_h):
            if aspect_h == 10:
                flags.append("MARS_TRANSIT_ASPECTS_H10")
            elif aspect_h == 1:
                flags.append("MARS_TRANSIT_ASPECTS_LAGNA_ENERGY")
            elif aspect_h == 11:
                flags.append("MARS_TRANSIT_ASPECTS_H11_GAINS")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# Main Enhancer Class
# ─────────────────────────────────────────────────────────────────────────────

class AstroEnhancer:
    """Compute all 34 gap fixes for a single dasha period.

    Usage::

        inp = EnhancerInput(md_lord="Jupiter", ad_lord="Saturn", ...)
        result = AstroEnhancer.run(inp)
        # result.total_bonus → float to add to career_score
        # result.event_hints → ['ENTREPRENEURSHIP_WINDOW', ...]
    """

    @staticmethod
    def run(inp: EnhancerInput) -> EnhancerResult:
        r = EnhancerResult()

        # ── Tier 1: Scoring accuracy ──────────────────────────────────────────
        r.combustion_modifier, r.combustion_notes = _g1_combustion(inp)

        retro_mod, retro_notes = _g2_retrograde(inp)
        r.retrograde_modifier = retro_mod
        r.retrograde_notes = retro_notes

        yuddha_mod, yuddha_notes = _g3_graha_yuddha(inp)
        r.graha_yuddha_modifier = yuddha_mod
        r.yoga_notes.extend(yuddha_notes)

        r.dig_bala_factor = _g4_combined_dig_bala(inp)

        nb_bonus, nb_notes = _g5_neecha_bhanga_bonus(inp)
        r.neecha_bhanga_bonus = nb_bonus
        r.yoga_notes.extend(nb_notes)

        vry_bonus, _vry_yogas, vry_notes = _g6_viparita_raja_yoga(inp)
        r.viparita_raja_bonus = vry_bonus
        r.yoga_notes.extend(vry_notes)

        pky_penalty, pky_notes = _g7_papa_kartari(inp)
        r.papa_kartari_penalty = pky_penalty
        r.yoga_notes.extend(pky_notes)

        ksy_mod, _ksy_name, ksy_notes = _g8_kala_sarpa(inp)
        r.kala_sarpa_modifier = ksy_mod
        r.yoga_notes.extend(ksy_notes)

        r.upachaya_growth_factor = _g9_upachaya_growth(inp)

        # ── Tier 2: Timing precision ──────────────────────────────────────────
        if inp.period_start and inp.period_end:
            # Use AD lord as proxy PD lord for Sooksham expansion
            r.sooksham_lords = _g10_sooksham_dashas(
                inp.ad_lord, inp.period_start, inp.period_end
            )
            # G10 timing score: power concentration when MD/AD lord appears in sooksham cycle
            if r.sooksham_lords:
                _sd_lords = {sd["sd_lord"] for sd in r.sooksham_lords}
                if inp.md_lord in _sd_lords or inp.ad_lord in _sd_lords:
                    r.sooksham_timing_score = 0.8   # concentrated: dasha power echoed at 4th level
                else:
                    r.sooksham_timing_score = 0.5   # timing precision available, neutral alignment
            # else: 0.0 (no sooksham data — timing precision unavailable)

        sandhi_mod, is_sandhi, sandhi_notes = _g11_dasha_sandhi(inp)
        r.sandhi_modifier = sandhi_mod
        r.is_sandhi = is_sandhi
        r.timing_notes.extend(sandhi_notes)

        r.nakshatra_trigger_flags = _g12_nakshatra_triggers(inp)
        r.pav_transit_score = _g13_career_pav_score(inp)
        r.pav_slow_planet_score = _g13b_slow_planet_pav_score(inp)
        r.kaksha_activation = _g14_kaksha_activation(inp)

        # ── Tier 3: Alternative dasha systems ────────────────────────────────
        r.chara_dasha_score = _g15_chara_dasha_score(inp)
        r.dasha_longevity_score = _g15b_dasha_longevity(inp)

        yog_name, yog_planet, yog_score = _g16_yogini_dasha(inp)
        r.yogini_name = yog_name
        r.yogini_score = yog_score

        ash_active, ash_lord, _ash_score = _g17_ashtottari_period(inp)
        r.ashtottari_active = ash_active
        r.ashtottari_lord = ash_lord

        # ── Tier 4: Divisional charts ─────────────────────────────────────────
        r.d10_full_score = _g18_d10_full(inp)
        r.d60_modifier   = _g19_d60_modifier(inp)
        r.d27_modifier   = _g20_d27_modifier(inp)
        r.vimsopaka_score = _g21_combined_vimsopaka(inp)

        # ── Tier 5: Lagna systems ─────────────────────────────────────────────
        r.surya_lagna_bonus  = _g22_surya_lagna_bonus(inp)
        r.arudha_bonus, arudha_notes = _g23_arudha_bonus(inp)
        r.yoga_notes.extend(arudha_notes)
        r.karakamsha_bonus = _g24_karakamsha_bonus(inp)
        r.amatyakaraka_score = _g24b_amatyakaraka_score(inp)

        # ── Tier 6: KP precision ──────────────────────────────────────────────
        r.kp_ssl_score             = _g25_kp_ssl_score(inp)
        r.kp_weighted_score        = _g25_kp_weighted_score(inp)
        r.kp_ruling_planets_score  = _g26_kp_ruling_planets(inp)
        r.kp_nakshatra_chain_score = _g27_combined_chain(inp)
        r.kp_subfield_hint         = _g25c_kp_subfield_hint(inp)
        # GAP FIX (2026-08-21, item 2.3): cusp-chain verification for the
        # Tier 6 KP scores above. house_system label is passed empty since
        # EnhancerInput doesn't carry it and audit_kp_cusps treats geometric
        # self-consistency (not the label) as authoritative anyway (see
        # kp_audit.py's own 2026-08-18 fix comment).
        r.kp_cusp_verified = (
            audit_kp_cusps(inp.kp_cusps_full, "").get("status") == "VERIFIED"
        )

        # ── Tier 7 (G28–G31): Event type hints ───────────────────────────────
        r.event_hints = _g28_to_g31_hints(inp, is_sandhi)

        # ── Tier 8 (G32–G34): Aspect flags ───────────────────────────────────
        r.mars_aspect_flags    = _g32_mars_aspect_flags(inp)
        r.transit_aspect_flags = _g34_transit_aspect_flags(inp)
        # G33 natal aspect modifier folds into total_bonus via yoga_notes:
        _g33_mod = _g33_natal_aspect_modifier(inp)
        # Store as ad-hoc field on result for scoring integration
        object.__setattr__(r, "_natal_aspect_modifier", _g33_mod) \
            if hasattr(r, "__dict__") else None
        # Safer: accumulate into retrograde_modifier (same sign category)
        r.retrograde_modifier = round(r.retrograde_modifier + _g33_mod, 4)

        return r


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: integrate EnhancerResult into timeline.py's _score_period dict
# ─────────────────────────────────────────────────────────────────────────────

# Weights for new enhancer factors in the combined career score.
# Calibration v6 (Steps 3–5 improvement plan):
#   KP_SSL      0.03 → 0.06   (+0.03, Step 4: clearer AD-window separation)
#   SOOKSHAM    0.00 → 0.03   (+0.03, Step 5: Sooksham precision into timing stack)
#   VIMSOPAKA   0.12 → 0.10   (-0.02, rebalance)
#   KP_CHAIN    0.03 → 0.01   (-0.02, rebalance)
#   CHARA_DASHA 0.01 → 0.00   (-0.01, rebalance)
#   D10_FULL    0.01 → 0.00   (-0.01, rebalance)
#   Net change: 0 (weight envelope preserved)
_W_ENHANCER_VIMSOPAKA   = 0.06   # G21 (GAP FIX 2026-08-17: 0.10→0.06, trimmed to help
                                  # fund the D10_FULL restoration below)
_W_ENHANCER_KP_CHAIN    = 0.01   # G27 (v6: 0.03→0.01 to fund KP_SSL + SOOKSHAM)
_W_ENHANCER_CHARA_DASHA = 0.00   # G15 (v6: 0.01→0.00)
_W_ENHANCER_KP_SSL      = 0.05   # G25 (GAP FIX 2026-08-17: 0.06→0.05, trimmed slightly
                                  # to help fund the D10_FULL restoration below)
_W_ENHANCER_D10_FULL    = 0.10   # G18 (GAP FIX 2026-08-17: restored from 0.00 —
                                  # D10/Dashamsha is the classical career-specialization
                                  # chart; funded by trimming VIMSOPAKA and KP_SSL above)
_W_ENHANCER_KP_RULING   = 0.00   # G26 (dropped earlier)
_W_SOOKSHAM_TIMING      = 0.03   # G10 (Step 5: dedicated Sooksham timing bonus)
_W_VIM_KP_ALIGN         = 0.02   # Step 3: co-activation bonus when Vimsopaka AND KP-SSL both HIGH
_W_ENHANCER_AMATYAKARAKA = 0.05  # GAP FIX (2026-08-17): Jaimini Amatyakaraka — the
                                  # framework notes AmK is "often more precise than
                                  # 10th lord" for career; previously computed nowhere
                                  # in this module's scoring path.
_W_ENHANCER_DASHA_LONGEVITY = 0.04  # GAP FIX (2026-08-17): Step 7 Vimshottari longevity
                                  # filter — is the active MD lord a career-house lord
                                  # with long, stable support ahead, or about to hand off
                                  # to a weak one? Funded by trimming KP_CHAIN below.
# GAP FIX (2026-07-05): PAV (Ashtakavarga bindu) transit scores were computed
# but never fed into the final score — reporting only. Wired in below.
_W_ENHANCER_PAV_DASHA   = 0.04   # G13: MD/AD lord's own PAV transit strength
_W_ENHANCER_PAV_SLOW    = 0.04   # G13b: Jupiter/Saturn/Rahu/Ketu PAV, dasha-independent


def enhancer_score_delta(result: EnhancerResult, birth_time_uncertainty_minutes: int = 0) -> float:
    """
    Compute the net score delta contributed by the enhancer to add onto
    the base career_score from _score_period.

    Formula:
        delta = total_bonus (additive modifiers)
              + weighted sub-scores (replace placeholder 0.5 baselines)
              + sooksham timing precision bonus (Step 5)
              + vimsopaka×KP co-activation bonus (Step 3)

    Returns a float, typically in range [-0.20, +0.20].

    GAP FIX (2026-08-21, remediation plan item 2.4): the four Tier 6 KP
    functions (_g25_kp_ssl_score, _g25_kp_weighted_score,
    _g26_kp_ruling_planets, _g27_combined_chain -> kp_ssl_score,
    kp_weighted_score is unused in this formula, kp_ruling_planets_score,
    kp_nakshatra_chain_score) fed into this delta with NO birth-time
    precision gating, unlike Job_Career/timeline.py's sibling KP/D10
    degradation (see that module's "FIX 1: Birth-time uncertainty ->
    degrade KP/D10 weights" comment), which applies full weight at <=5min
    uncertainty, decaying linearly to 0.3x by 60+min. KP sub-lords are
    exactly the fast-moving, birth-time-sensitive chain these Tier 6
    functions consume, so they need the same curve. Reusing the identical
    formula here (not inventing a new one) keeps the two modules'
    degradation behavior consistent for the same underlying KP signal.
    """
    btu = birth_time_uncertainty_minutes or 0
    _kp_deg = max(0.3, 1.0 - (btu - 5) / 60.0) if btu > 5 else 1.0
    # GAP FIX (2026-08-21, item 2.3): fold the cusp-chain-verification
    # discount (conservative 0.5x, same factor kp.py uses for UNVERIFIED
    # cusps, not a hard zero) into the same combined KP degradation factor
    # as the birth-time-precision curve above, since both discount the same
    # Tier 6 KP signal for the same reason (untrustworthy cusp-derived data).
    _kp_deg *= 1.0 if result.kp_cusp_verified else 0.5
    _kp_ssl_eff = result.kp_ssl_score * _kp_deg
    weighted = (
        _W_ENHANCER_VIMSOPAKA   * (result.vimsopaka_score - 0.5)
        + _W_ENHANCER_KP_CHAIN  * (result.kp_nakshatra_chain_score * _kp_deg - 0.5 * _kp_deg)
        + _W_ENHANCER_CHARA_DASHA * (result.chara_dasha_score - 0.5)
        + _W_ENHANCER_KP_SSL    * (_kp_ssl_eff - 0.5 * _kp_deg)        # Step 4: raised weight
        + _W_ENHANCER_D10_FULL  * (result.d10_full_score - 0.33)
        + _W_ENHANCER_KP_RULING * (result.kp_ruling_planets_score * _kp_deg - 0.5 * _kp_deg)
        + _W_SOOKSHAM_TIMING    * (result.sooksham_timing_score - 0.5)  # Step 5: timing precision
        + _W_ENHANCER_PAV_DASHA * (result.pav_transit_score - 0.5)       # G13: MD/AD lord PAV transit
        + _W_ENHANCER_PAV_SLOW  * (result.pav_slow_planet_score - 0.5)  # G13b: Jup/Sat/Rahu/Ketu PAV
        + _W_ENHANCER_AMATYAKARAKA * (result.amatyakaraka_score - 0.5)  # G24b: Amatyakaraka (GAP FIX 2026-08-17)
        + _W_ENHANCER_DASHA_LONGEVITY * (result.dasha_longevity_score - 0.5)  # G15b: Vimshottari longevity (GAP FIX 2026-08-17)
    )
    # Step 3: VIM-KP co-activation bonus — fires when BOTH Vimsopaka AND KP-SSL are HIGH.
    # Gated by the same _kp_deg curve (via _kp_ssl_eff) since this bonus is itself
    # a KP-derived signal (GAP FIX 2026-08-21, item 2.4).
    _vim_kp_align = (
        _W_VIM_KP_ALIGN * _kp_deg
        if result.vimsopaka_score >= 0.65 and _kp_ssl_eff >= 0.65
        else 0.0
    )
    return round(result.total_bonus + weighted + _vim_kp_align, 4)


def build_enhancer_input_from_payload(
    md_lord: str,
    ad_lord: str,
    period_start: Optional[date],
    period_end: Optional[date],
    payload: Any,
    dob: Optional[date] = None,
    transit_projected: Optional[Dict[str, int]] = None,
    md_change_dates: Optional[List[date]] = None,
    ad_change_dates: Optional[List[date]] = None,
) -> EnhancerInput:
    """Build EnhancerInput from a NatalPayloadV2-compatible object.

    All getattr calls are guarded — missing fields degrade gracefully.
    """
    g = lambda attr, default=None: getattr(payload, attr, default) or default

    # ── House / sign maps ────────────────────────────────────────────────────
    planet_house  = g("planet_house",  {}) or {}
    house_lords   = g("house_lords",   {}) or {}
    planet_signs  = g("planet_signs",  {}) or {}

    # ── Retrograde set ───────────────────────────────────────────────────────
    retro_map = g("planet_retrograde", {}) or {}
    retrograde_planets: Set[str] = {p for p, v in retro_map.items() if v}

    # ── Varga dignities: merge D1/D9/D24 into {varga: {planet: dignity}} ───
    varga_dignities: Dict[str, Dict[str, str]] = {}
    d1_dig   = g("planet_dignities",     {}) or {}
    d9_dig   = g("d9_planet_dignities",  {}) or {}
    d24_dig  = g("d24_planet_dignities", {}) or {}
    div_str  = g("divisional_planet_strength", {}) or {}
    if d1_dig:
        varga_dignities["D1"]  = d1_dig
    if d9_dig:
        varga_dignities["D9"]  = d9_dig
    if d24_dig:
        varga_dignities["D24"] = d24_dig
    for _vk, _vv in div_str.items():
        if _vk not in varga_dignities and isinstance(_vv, dict):
            varga_dignities[_vk] = {p: str(v) for p, v in _vv.items()}

    # ── KP data ──────────────────────────────────────────────────────────────
    kp_cusps_full    = g("kp_cusps",         {}) or {}
    kp_significators = g("kp_significators", {}) or {}
    # Bugfix (2026-07-05): kp_cusps_full is populated verbatim from the raw
    # pyhora `kp_cusp_data` dict, which is keyed "H1".."H12" (confirmed against
    # Charts/lakshman_chart_details.json), not the bare "1" this lookup used.
    # The mismatch meant lagna_star_lord/lagna_sub_lord were always empty,
    # silently starving _g26_kp_ruling_planets (and any other consumer of
    # these two fields) of real data. Accept both key styles defensively.
    _c1              = kp_cusps_full.get("H1", {}) or kp_cusps_full.get("1", {}) or {}
    lagna_star_lord  = _c1.get("star_lord", "") or _c1.get("nakshatra_lord", "")
    lagna_sub_lord   = _c1.get("sub_lord", "")
    _moon_kp         = kp_significators.get("Moon", {}) or {}
    moon_star_lord   = _moon_kp.get("star_lord", "") or _moon_kp.get("nakshatra_lord", "")
    moon_sub_lord    = _moon_kp.get("sub_lord", "")

    # ── Nakshatra lords per planet ───────────────────────────────────────────
    nak_data = g("nakshatra_data", {}) or {}
    planet_nakshatra_lord: Dict[str, str] = {}
    for _p, _nd in nak_data.items():
        if isinstance(_nd, dict):
            planet_nakshatra_lord[_p] = _nd.get("lord", "") or _nd.get("nakshatra_lord", "")
        elif isinstance(_nd, str):
            planet_nakshatra_lord[_p] = _NAKSHATRA_LORDS.get(_nd, "")

    # ── Moon pada (for Yogini) ────────────────────────────────────────────────
    _moon_pada_raw  = g("moon_nakshatra_pada", 0) or 0
    _moon_nak_name  = g("moon_nakshatra", "") or ""
    try:
        _nak_idx = _NAKSHATRA_NAMES.index(_moon_nak_name) if _moon_nak_name in _NAKSHATRA_NAMES else 0
    except ValueError:
        _nak_idx = 0
    moon_nakshatra_pada_num = _nak_idx * 4 + (int(_moon_pada_raw) - 1 if _moon_pada_raw else 0)
    moon_nakshatra_lord_val = _NAKSHATRA_LORDS.get(_moon_nak_name, "")

    # ── Jaimini ──────────────────────────────────────────────────────────────
    _d9_lagna  = g("d9_lagna_sign", "") or ""
    _karamksha = g("karakamsha",    "") or ""
    jaimini_chara_lagna_sign = _karamksha or _d9_lagna

    # ── SAV (Ashtakavarga) ───────────────────────────────────────────────────
    sav_data = g("sav_points_houses", {}) or {}

    return EnhancerInput(
        md_lord=md_lord,
        ad_lord=ad_lord,
        period_start=period_start,
        period_end=period_end,
        dob=dob,
        lagna_sign=g("lagna_sign", "") or "",
        planet_natal_degrees={},
        planet_transit_degrees={},
        planet_sign=planet_signs,
        planet_house=planet_house,
        house_lords=house_lords,
        retrograde_planets=retrograde_planets,
        pav_data={},
        sav_data={str(k): v for k, v in sav_data.items()},
        varga_dignities=varga_dignities,
        d10_lagna_sign=g("d10_lagna_sign", "") or "",
        d10_house_lords=g("d10_house_lords", {}) or {},
        d10_house_occupancy=g("d10_house_occupancy", {}) or {},
        d27_planet_strengths={},
        kp_cusps_full=kp_cusps_full,
        planet_nakshatra_lord=planet_nakshatra_lord,
        kp_significators=kp_significators,
        lagna_star_lord=lagna_star_lord,
        lagna_sub_lord=lagna_sub_lord,
        moon_star_lord=moon_star_lord,
        moon_sub_lord=moon_sub_lord,
        day_lord="",
        atmakaraka=g("atmakaraka", "") or "",
        amatyakaraka=g("amatyakaraka", "") or "",  # GAP FIX (2026-08-17)
        jaimini_chara_lagna_sign=jaimini_chara_lagna_sign,
        transit_projected=transit_projected or {},
        md_change_dates=md_change_dates or [],
        ad_change_dates=ad_change_dates or [],
        moon_nakshatra_pada_num=moon_nakshatra_pada_num,
        moon_nakshatra_lord=moon_nakshatra_lord_val,
        rahu_house=g("rahu_house", 0) or 0,
        moon_house=planet_house.get("Moon", 0),
        dasha_sequence=g("dasha_sequence", []) or [],  # GAP FIX (2026-08-17)
    )
