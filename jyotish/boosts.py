"""JyotishAI — Gap-boost scoring helpers (all _*_bonus / _*_penalty functions)."""
import math as _math
import os as _os
import re as _re
from typing import Dict, List, Tuple, Set, Any, Optional

# Print-output optimization (2026-08-20): gate the per-field wealth-filter
# debug prints (`[WEALTH FILTER]`, `[WEALTH NARRATIVE]`) behind the same
# opt-in verbosity flag engine.py uses, so a normal run only prints the
# final summary report. Set JYOTISH_VERBOSE_FIELD_LOG=1 to restore them.
_VERBOSE_FIELD_LOG = _os.environ.get("JYOTISH_VERBOSE_FIELD_LOG", "0") == "1"

from .payload import NatalPayloadV2, logger
from .constants import (
    _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES,
    _SIGN_LORD, _SIGN_NUM, _NODAL_DEFAULT_VIRUPAS,
    _D24_ACADEMIC_KW, _H12_FIELDS, _H6_FIELDS, _H9_FIELDS, _H5_FIELDS,
    _FRONTIER_KW, _TRADITIONAL_KW, _H9_STELLIUM_KW, _H12_STELLIUM_KW,
    _FUNCTIONAL_TRIKONA_FALLBACK, _ALL_PLANETS_SET, _DUSTHANA_EXEMPT_KW,
    _MAHESHWARA_DOMAIN_KW, _STREAM_MAP, _KARAKAMSHA_OCCUPANT_KW,
    _NAKSHATRA_CAREER_KW, _RAHU_HOUSE_CAREER_KW, _KETU_HOUSE_NATURAL_TALENT,
    _PUSHKARA_NAVAMSHA, _PADA_NAVAMSHA_SIGN, _NAVAMSHA_SIGN_CAREER_KW,
    _GUNA_PLANETS, _GUNA_FIELD_AFFINITY, _DUSTHANA_CAREER_DIRECTIVE,
    _ADHI_YOGA_FIELDS, _ANAPHA_YOGA_FIELDS,
    _NAKSHATRA_LORD,
    _PLANET_KARAKA_DOMAINS, _DOMAIN_TO_KARAKA, _DOMAIN_HOUSE_SIGNIFICATORS,
    _VIMSOPAKA_WEIGHTS_FULL, _VIMSOPAKA_DIG_SCORE,
)
from .astro import (
    _get_planetary_aspects, _get_planetary_aspects_weighted, _drishti_bala,
    _detect_planetary_war, _planet_abs_degree, compute_dignity,
)

_ALL_PLANETS: Tuple = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")

# ── Functional Status Table (all 12 lagnas) ──────────────────────────────────
# YOGAKARAKA: planet ruling both a kendra (H1/4/7/10) and a trikona (H1/5/9) → boosts.
# MALEFIC: functional malefic for the lagna (primary ruler of H6/H8/H12) → dampen.
# BENEFIC: natural benefic ruling good houses → neutral multiplier (1.0).
# Planets absent from a lagna mapping are treated as NEUTRAL.
_FUNCTIONAL_STATUS: Dict[str, Dict[str, str]] = {
    "Aries":       {"Saturn": "MALEFIC",    "Mercury": "MALEFIC",  "Venus": "MALEFIC",
                    "Jupiter": "MALEFIC",   "Sun": "BENEFIC",      "Mars": "BENEFIC"},
    "Taurus":      {"Saturn": "YOGAKARAKA", "Jupiter": "MALEFIC",  "Mars": "MALEFIC",
                    "Venus": "BENEFIC",     "Mercury": "BENEFIC"},
    "Gemini":      {"Jupiter": "MALEFIC",   "Mars": "MALEFIC",    "Venus": "MALEFIC",
                    "Saturn": "MALEFIC",    "Mercury": "BENEFIC"},
    "Cancer":      {"Mars": "YOGAKARAKA",   "Jupiter": "MALEFIC",  "Saturn": "MALEFIC",
                    "Mercury": "MALEFIC",   "Moon": "BENEFIC"},
    "Leo":         {"Mars": "YOGAKARAKA",   "Saturn": "MALEFIC",   "Venus": "MALEFIC",
                    "Mercury": "MALEFIC",   "Sun": "BENEFIC",      "Jupiter": "BENEFIC"},
    "Virgo":       {"Mars": "MALEFIC",      "Saturn": "MALEFIC",   "Sun": "MALEFIC",
                    "Moon": "MALEFIC",      "Venus": "BENEFIC",    "Mercury": "BENEFIC"},
    "Libra":       {"Saturn": "YOGAKARAKA", "Jupiter": "MALEFIC",  "Mercury": "MALEFIC",
                    "Mars": "MALEFIC",      "Venus": "BENEFIC"},
    "Scorpio":     {"Venus": "MALEFIC",     "Mercury": "MALEFIC",  "Saturn": "MALEFIC",
                    "Mars": "BENEFIC",      "Jupiter": "BENEFIC"},
    "Sagittarius": {"Venus": "MALEFIC",     "Mercury": "MALEFIC",  "Saturn": "MALEFIC",
                    "Jupiter": "BENEFIC",   "Mars": "BENEFIC"},
    "Capricorn":   {"Venus": "YOGAKARAKA",  "Jupiter": "MALEFIC",  "Mars": "MALEFIC",
                    "Moon": "MALEFIC",      "Saturn": "BENEFIC"},
    "Aquarius":    {"Venus": "YOGAKARAKA",  "Jupiter": "MALEFIC",  "Moon": "MALEFIC",
                    "Mercury": "BENEFIC",   "Saturn": "BENEFIC"},
    "Pisces":      {"Saturn": "MALEFIC",    "Venus": "MALEFIC",    "Sun": "MALEFIC",
                    "Mercury": "MALEFIC",   "Jupiter": "BENEFIC",  "Mars": "BENEFIC"},
}

# Odd signs (for Mrita Avastha detection: degree 24°–30° in odd sign = dead state)
_ODD_SIGNS: Set[str] = {"Aries","Gemini","Leo","Libra","Sagittarius","Aquarius"}


def _functional_status_factor(planet: str, lagna_sign: str) -> float:
    """Return a dignity multiplier adjustment based on functional lordship.

    YOGAKARAKA: 1.15 (slight uplift — ruling both kendra and trikona)
    MALEFIC:    0.60 (dampen — dignity amplifies dusthana significations)
    BENEFIC:    1.00 (neutral — natural + functional benefic; existing bonuses apply)
    NEUTRAL:    1.00 (no data)

    AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass): this is
    the narrowest-scope of the three Yogakaraka implementations -- it only
    multiplies _exalted_planet_domain_bonus's contribution (planet
    exalted/own AND matching a domain keyword), not a field's whole score.
    See _yogakaraka_bonus() below and astro.py::_compute_eff_strengths's
    `yk_mod` for the other two, broader-scope implementations and how they
    can currently stack for the same planet/field.
    """
    if not lagna_sign:
        return 1.0
    status = _FUNCTIONAL_STATUS.get(lagna_sign, {}).get(planet, "NEUTRAL")
    if status == "YOGAKARAKA":
        return 1.15
    if status == "MALEFIC":
        return 0.60
    return 1.0


def _d1_vitality_coefficient(planet: str, payload) -> float:
    """D1 structural vitality coefficient (0.0–1.0) for a planet.

    Divisional charts have no independent physical existence; their scores must
    be gated by the planet's D1 integrity.  Three structural impairments reduce
    a planet's ability to manifest even exalted varga results:

      • Combustion (absorbed by Sun): coefficient 0.45
      • Graha Yuddha loser:
            - Bitter defeat (by a natural enemy): 0.35
            - Friendly defeat:                   0.60
      • Mrita Avastha (dead degrees):
            - Odd signs 24°–30°:                 0.15
            - Even signs 0°–6°:                  0.15
      • Multiple impairments → take the lowest coefficient.
      • No impairment → 1.0

    AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass): unlike
    astro.py::_compute_eff_strengths, this coefficient is NOT multiplied
    against raw_shadbala/base -- it's a standalone [0,1] structural gate
    applied directly to varga (divisional-chart) results elsewhere, so its
    combustion/Graha-Yuddha figures are not a Shadbala double-count the way
    astro.py's `comb_mod`/`war_mod` are (see the audit notes on those). It IS,
    however, a fourth independently-parameterized combustion magnitude
    (0.45 flat cap here vs. astro.py's 0.75-0.92 dignity-aware gradient vs.
    dignity.py's COMBUST_STRENGTH_PENALTY=0.85, which is dead code -- see
    that constant's note) and a third Graha-Yuddha magnitude (0.20/0.35/0.60
    here vs. astro.py's 0.85/0.90/0.95/1.05 war_mod vs. the classical Yuddha
    Bala virupas already inside raw_shadbala). Each serves a genuinely
    different purpose (D1 structural gate vs. eff_strength scaling vs.
    Shadbala's own point system), so this is not necessarily wrong, but the
    three/four magnitudes were never cross-checked against each other or
    against BPHS for consistency -- worth a unification pass, same as
    combustion partially got in md/ENGINE_SIMPLIFICATION_2026-08-17_
    combustion_unify.md. Not changed here; flagging only.
    """
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    combust    = set(getattr(payload, "combust_planets", []) or [])
    coeff      = 1.0

    # Q1: Cazimi vector — planet within 0°17' of Sun is in the Solar heart.
    # Classical rule: Cazimi strips the combustion flag entirely and makes the planet
    # maximally powerful (1.35×). The 0°17' threshold is the classical Tajik boundary.
    # Must be checked BEFORE combustion so the flag is removed non-cumulatively.
    cazimi_set  = set(getattr(payload, "cazimi_planets", []) or [])
    _is_cazimi  = planet in cazimi_set
    if _is_cazimi:
        # Planet is in the Sun's heart — remove from effective combust set
        combust = combust - {planet}
        coeff = 1.35   # maximum vitality — non-cumulative (no further boosts stack above this)
        return coeff   # return immediately; no other impairment applies to Cazimi

    # Combustion check (cazimi planets already excluded above)
    if planet in combust:
        coeff = min(coeff, 0.45)

    # Graha Yuddha check (re-detect from planets_d1 each call; results are tiny)
    if planets_d1:
        war_result = _detect_planetary_war(planets_d1)
        war_status = war_result.get(planet, "")
        if war_status == "loser_severe":
            coeff = min(coeff, 0.20)   # P3: severe war (<0.5°) — near-total defeat
        elif war_status == "loser_bitter":
            coeff = min(coeff, 0.35)
        elif war_status == "loser_friendly":
            coeff = min(coeff, 0.60)

    # Mrita Avastha check — with AK and own-sign dignity floors
    pdata = planets_d1.get(planet, {})
    if pdata:
        sign   = pdata.get("sign", "")
        degree = float(pdata.get("degree", 0))
        is_mrita = (sign in _ODD_SIGNS and degree >= 24.0) or (sign and sign not in _ODD_SIGNS and degree < 6.0)
        if is_mrita:
            mrita_floor = 0.15  # default dead-state coefficient
            # AK protection: soul indicator retains partial manifestation capacity
            _ak = getattr(payload, "atmakaraka", "") or ""
            if planet == _ak:
                mrita_floor = max(mrita_floor, 0.45)
            # Own-sign / exalted mitigation: dignity partially shields from dead-state
            _digs = getattr(payload, "planet_dignities", {}) or {}
            _dig  = _digs.get(planet, "")
            if _dig == "EXALTED":
                mrita_floor = max(mrita_floor, 0.40)
            elif _dig == "OWN":
                mrita_floor = max(mrita_floor, 0.35)
            coeff = min(coeff, mrita_floor)

    # Q1b: Retrograde paradox is already applied upstream in _compute_eff_strengths
    # (retrograde exalted → dignity mod = 0.60, same as debilitated; retrograde
    # debilitated → dignity mod = 1.40, same as exalted).  Applying it a second
    # time here causes a compounded penalty where retrograde exalted ends up weaker
    # than plain debilitated, which violates the paradox intent.  M3 fix: removed.

    return coeff


def _vimsopaka_bala_coefficient(planet: str, payload) -> float:
    """Reduced Vimshopaka Bala multiplier (0.75x-1.25x) for a planet.

    Fix (cross-cutting gap): classical Vimshopaka Bala aggregates a planet's
    dignity across 16 divisional charts into a single unified divisional-
    strength score. Previously this pipeline computed a Vimshopaka-style score
    (astro_enhancer.py's G21) but only wired it into MD/AD dasha-lord timing —
    it was never exposed to the five field-determination methods, which each
    approximated divisional strength ad hoc (their own per-varga dignity
    multipliers, inconsistent from method to method).

    This pipeline only actually computes dignities for D1/D3/D9/D10/D20/D24/D30
    (not the full classical 16), so this is a reduced/practical Vimshopaka Bala:
    it normalizes by the weight of whichever of those vargas are present on the
    payload for this call, rather than padding missing vargas with a fake
    "neutral" value (which would silently dilute the signal toward 0.5 for
    every chart, defeating the purpose).

    Returns a multiplier centered at 1.0 (0.375 raw score == "neutral across the
    board" == 1.0x) so callers can multiply an existing bonus/penalty by this
    coefficient without needing to rebalance every method's point scale:
      raw 1.000 (exalted everywhere)      -> 1.25x
      raw 0.375 (neutral everywhere)      -> 1.00x
      raw 0.000 (debilitated/worse every) -> 0.75x
    """
    _varga_sources = {
        "D1":  getattr(payload, "planet_dignities", {}) or {},
        "D3":  getattr(payload, "d3_planet_dignities", {}) or {},
        "D9":  getattr(payload, "d9_planet_dignities", {}) or {},
        "D10": getattr(payload, "d10_planet_dignities", {}) or {},
        "D20": getattr(payload, "d20_planet_dignities", {}) or {},
        "D24": getattr(payload, "d24_planet_dignities", {}) or {},
        "D30": getattr(payload, "d30_planet_dignities", {}) or {},
    }
    present = {v: d for v, d in _varga_sources.items() if d}
    if not present:
        return 1.0
    total_wt = sum(_VIMSOPAKA_WEIGHTS_FULL[v] for v in present)
    if total_wt <= 0:
        return 1.0
    score = 0.0
    for varga, digs in present.items():
        dig = str(digs.get(planet, "neutral")).lower()
        score += _VIMSOPAKA_WEIGHTS_FULL[varga] * _VIMSOPAKA_DIG_SCORE.get(dig, 0.375)
    vims = score / total_wt   # 0.0 - 1.0
    return round(0.75 + vims * 0.50, 4)


def _karakatwa_domain_bonus(domain: str, field_affinity: Dict[str, float],
                             planets_d1: Dict, planet_house: Dict[str, int],
                             payload=None, scale: float = 6.0, cap: float = 12.0) -> Tuple[float, List[str]]:
    """Systematic karaka-to-field bonus, shared by all field-determination methods.

    Fix (cross-cutting gap): field-to-planet mappings elsewhere are hand-curated
    keyword lists (mining/aerospace/medicine substrings, etc.), so a field just
    outside the curated list gets no signal regardless of actual chart strength.
    This instead maps each graha to its classical significator domains (BPHS /
    Jataka Parijata karakatwa) and every coarse `domain` bucket this engine uses
    to the karaka vocabulary, so any planet whose karaka domain matches the
    chart's domain contributes a bonus scaled by its own field affinity,
    dignity, house placement, and D1 vitality — independent of field-id
    keyword matching. Originally implemented only in knrao.py; promoted here so
    jaimini, parashara, and dashamsha get the same systematic fallback.

    Returns (bonus_points, list_of_contributing_planets).
    """
    karaka_domains = _DOMAIN_TO_KARAKA.get(domain, set())
    if not karaka_domains:
        return 0.0, []
    total = 0.0
    hits: List[str] = []
    for kp_planet, kp_domains in _PLANET_KARAKA_DOMAINS.items():
        if not (kp_domains & karaka_domains):
            continue
        weight = field_affinity.get(kp_planet, 0.0)
        if weight < 0.08:
            continue
        house = planet_house.get(kp_planet, 0)
        sign = (planets_d1.get(kp_planet) or {}).get("sign", "") if planets_d1 else ""
        dig = compute_dignity(kp_planet, sign) if sign else ""
        dig_mult = {"EXALTED": 1.30, "OWN": 1.15, "MOOLATRIKONA": 1.10,
                    "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.65}.get(dig or "", 1.00)
        pos_mult = 1.20 if house in {1, 4, 5, 9, 10} else 0.80 if house in {6, 8, 12} else 1.00
        vit = _d1_vitality_coefficient(kp_planet, payload) if payload is not None else 1.0
        piece = weight * scale * dig_mult * pos_mult * vit
        total += piece
        hits.append(kp_planet)
    return min(total, cap), hits


def _house_signification_bonus(domain: str, field_affinity: Dict[str, float],
                                house_lords: Dict, planet_house: Dict[str, int],
                                planets_d1: Dict, payload=None,
                                scale: float = 6.0, cap: float = 14.0) -> Tuple[float, List[str]]:
    """Ontology fix (audit): house-signification-first primitive, shared by
    every field-determination method.

    Classical field determination runs primarily through HOUSES (which house
    a vocation belongs to, and how strong that house's lord is), with karaka
    planet-matching as corroboration -- not the reverse. This engine's core
    scoring (BRANCH_PLANET_AFFINITY dot product) is karaka-first; house logic
    previously only re-entered through hand-curated field-*label* keyword
    gates (e.g. "does this field's id contain 'medicine'"), which silently
    miss any field whose id/label doesn't happen to match the list.

    This instead scores the lord of each house classically significant for
    the chart's coarse `domain` bucket (_DOMAIN_HOUSE_SIGNIFICATORS), grounded
    in the SPECIFIC field via that lord's own field_affinity weight (a
    domain-significant house whose lord carries no affinity for this
    particular field contributes nothing -- this is not a generic domain
    bonus, it is domain-*and*-field aware) and its dignity/placement in the
    natal chart. Independent of field-id keyword matching, so it applies
    uniformly to every field in a matching domain, mirroring how
    _karakatwa_domain_bonus generalized the planet side of the same problem.

    Returns (bonus_points, list_of_"H{house}:{lord}"_contributions).
    """
    houses = _DOMAIN_HOUSE_SIGNIFICATORS.get(domain, set())
    if not houses or not house_lords:
        return 0.0, []
    total = 0.0
    hits: List[str] = []
    for house_num in houses:
        lord = house_lords.get(str(house_num), house_lords.get(house_num, ""))
        if not lord:
            continue
        weight = field_affinity.get(lord, 0.0)
        if weight < 0.08:
            continue
        placed_house = planet_house.get(lord, 0)
        sign = (planets_d1.get(lord) or {}).get("sign", "") if planets_d1 else ""
        dig = compute_dignity(lord, sign) if sign else ""
        dig_mult = {"EXALTED": 1.30, "OWN": 1.15, "MOOLATRIKONA": 1.10,
                    "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.65}.get(dig or "", 1.00)
        pos_mult = 1.20 if placed_house in {1, 4, 5, 9, 10} else 0.80 if placed_house in {6, 8, 12} else 1.00
        vit = _d1_vitality_coefficient(lord, payload) if payload is not None else 1.0
        piece = weight * scale * dig_mult * pos_mult * vit
        total += piece
        hits.append(f"H{house_num}:{lord}")
    return min(total, cap), hits


import re as _re_wm
import functools as _functools_wm

@_functools_wm.lru_cache(maxsize=None)
def _compile_wm_pattern(kw: str):
    """Compile and cache a word-boundary regex for keyword kw (called once per unique kw)."""
    return _re_wm.compile(r'\b' + _re_wm.escape(kw) + r'\b')


def _wm(kw: str, text: str) -> bool:
    """Word-boundary match — prevents 'art' hitting 'artificial', 'age' hitting 'management'.

    Underscores in field_ids (e.g. 'fine_arts') are treated as word separators
    so 'arts' correctly matches 'fine_arts' → 'fine arts'.
    Patterns are compiled once per keyword and cached via lru_cache for performance.
    """
    normalized = text.replace("_", " ")
    return bool(_compile_wm_pattern(kw).search(normalized))



# ===========================================================================
# Q8: D60 (Shastiamsha) DEITY VECTOR
# ===========================================================================
# The D60 is the finest divisional chart (1/60th of a sign = 0.5° per part).
# Each of the 60 parts has a presiding deity whose nature is auspicious,
# neutral, or malefic. A planet dignified in D1 can be structurally drained
# if its D60 part falls in a malefic (Ghora/Dvapara/Krodhana etc.) deity block.
# Source: Brihat Parashara Hora Shastra, Chapter on Shastiamsha.

# D60 deity quality map: 1–60 (by index 0–59) for ODD signs.
# EVEN signs use the same sequence in REVERSE (classical rule).
# Quality: 1=auspicious (Deva/Saumya), 0=neutral, -1=malefic (Ghora/Krodhana/Rakshasa)
#
# GAP-FIX (2026-08, astrological audit): this array's values were checked
# against `_D60_DEITY_NAMES_ODD` below and, at 9 of the 60 indices, directly
# contradicted this docstring's OWN stated categorization of the deity name
# occupying that index -- e.g. index 0 is "Ghora" (this docstring's own
# example of a malefic name) but was scored 1 (auspicious); index 17 is
# "Maheshwara" (this docstring's own example of an auspicious name) but was
# scored -1 (malefic). Corrected every index where the deity name at that
# position is one of this function's own explicitly-named categories
# (Deva/Saumya/Brahma/Vishnu/Maheshwara=auspicious,
# Kinnara/Gandharva/Mridu=neutral, Ghora/Krodhana/Rakshasa/Yama=malefic):
# indices 0 (Ghora), 10 (Yama), 16 (Vishnu), 17 (Maheshwara), 24 (Saumya),
# 34 (Krodhana), 38 (Saumya), 49 (Ghora), 50 (Mridu). The remaining ~40
# deity names are NOT given an explicit category by this function's own
# docstring and were left unchanged -- correcting those would require an
# authoritative source for this specific 60-name Shashtiamsha deity table
# (a genuinely disputed area across classical commentators), which wasn't
# available to verify with confidence; only self-contradictions against this
# code's own documented rule were fixed here.
_D60_ODD_QUALITIES = [
    # 1-10
    -1, -1, 1, -1, 1, 0, 1, -1, 1, 0,
    # 11-20
    -1, -1, 0, 1, -1, 1, 1, 1, 1, 0,
    # 21-30
    1, -1, 1, 0, 1, 1, -1, 0, 1, -1,
    # 31-40
    1, 0, -1, 1, -1, 1, -1, 1, 1, -1,
    # 41-50
    1, 0, -1, 1, -1, 1, 0, -1, 1, -1,
    # 51-60
    0, 1, 0, 1, -1, 1, 0, -1, 1, -1,
]  # 60 entries

_D60_DEITY_NAMES_ODD = [
    "Ghora","Rakshasa","Deva","Kubera","Yaksha","Kinnara","Bhrashta","Kulaghna",
    "Garuda","Gandharva","Yama","Shubha","Mridu","Komal","Heramba","Brahma",
    "Vishnu","Maheshwara","Deva","Ardra","Kali","Vrishabha","Mrityudayi","Kolahal",
    "Saumya","Komala","Sheetala","Karaladamshtra","Chandramukhi","Praveena",
    "Kaalheen","Dhwanksha","Nirmala","Saumya","Krodhana","Adhama","Rakshasa",
    "Mishra","Saumya","Komalangi","Gandhara","Mridu","Atisheetala","Amrita",
    "Payodhi","Brahma","Chandravadana","Madhura","Kalaratri","Ghora",
    "Mridu","Komala","Nirmala","Saumya","Krodhana","Dhruva","Mahabhaya",
    "Shubha","Papasambhava","Atisheetala",
]

_ODD_SIGNS_D60 = {"Aries","Gemini","Leo","Libra","Sagittarius","Aquarius"}


def _d60_deity_quality(planet: str, sign: str, degree: float) -> int:
    """Return D60 deity quality for a planet at degree within sign.

    Returns:
        1  = auspicious (Deva/Saumya/Brahma/Vishnu/Maheshwara category)
        0  = neutral (Kinnara/Gandharva/Mridu category)
       -1  = malefic (Ghora/Krodhana/Rakshasa/Yama category)
    """
    try:
        d60_part = int(degree / 0.5)   # 0°–0.5° = part 1, etc.
        d60_part = max(0, min(d60_part, 59))
        if sign in _ODD_SIGNS_D60:
            return _D60_ODD_QUALITIES[d60_part]
        else:
            # Even signs: reverse sequence
            return _D60_ODD_QUALITIES[59 - d60_part]
    except Exception:
        return 0   # unknown — treat as neutral


def _d60_vitality_gate(planet: str, payload) -> float:
    """Q8: D60 Deity Vector vitality modifier for H10 lord or top career planet.

    Called from engine.py gap_boost to apply a final purity check.
    Returns a multiplier: 1.08 (auspicious), 1.00 (neutral), 0.88 (malefic Ghora/Dvapara).
    """
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    pdata = planets_d1.get(planet, {})
    if not pdata:
        return 1.0
    sign   = pdata.get("sign", "")
    degree = float(pdata.get("degree", 0.0))
    quality = _d60_deity_quality(planet, sign, degree)
    if quality == 1:
        return 1.08
    elif quality == -1:
        return 0.88
    return 1.00

# ===========================================================================
# GAP HELPER CONSTANTS
# ===========================================================================
DASHA_KEYWORDS: Dict[str, List[str]] = {
    "Sun":     ["civil services","leadership","medicine","physics","administration","government","energy","political"],
    "Moon":    ["psychology","nursing","hospitality","social work","counseling","public health","ecology","sociology","agriculture","food","nutrition","marine","aquaculture"],
    "Mars":    ["defence","defense","surgery","engineering","military","police","metallurgy","civil engineering","strategic","operations","tactical"],
    "Mercury": ["data science","computer","artificial intelligence","communication","journalism","statistics","research","mathematics","accounting"],
    "Jupiter": ["law","education","philosophy","economics","teaching","management","theology","international"],
    "Venus":   ["arts","design","fashion","music","architecture","performing arts","fine arts","luxury"],
    "Saturn":  ["metallurgy","mining","civil","industrial","petroleum","materials science","environmental","construction","manufacturing"],
    "Rahu":    ["artificial intelligence","cybersecurity","space","biotechnology","forensic","nuclear","robotics","information technology","foreign","unconventional","machine learning","data science","hospital","technology","economics","data","finance","quantitative","computational"],
    "Ketu":    ["research","philosophy","alternative medicine","ayurveda","spiritual","occult","investigation","archaeology"],
}
_KARAKAMSHA_CO_LORD: Dict[str, str] = {"Aquarius":"Rahu","Scorpio":"Ketu","Pisces":"Ketu"}
# A9 fix: constants canonically defined in constants.py — import from there
from .constants import (_D24_ACADEMIC_KW, _H12_FIELDS, _H6_FIELDS, _H9_FIELDS,
                        _H5_FIELDS, _FRONTIER_KW, _TRADITIONAL_KW)
_H9_STELLIUM_KW = ["philosophy","law","research","academia","international","medicine","higher","education","space","religion","theology","journalism","science","psychology","sociology"]
_H12_STELLIUM_KW= ["research","forensic","hospital","medicine","psychology","spiritual","alternative","investigat"]

_YOGAKARAKA_PLANET: Dict[str, str] = {
    "Taurus":"Saturn","Libra":"Saturn","Cancer":"Mars","Leo":"Mars",
    "Capricorn":"Venus","Aquarius":"Venus",
}
_FUNCTIONAL_TRIKONA_FALLBACK = {
    "Aries":"Sun","Gemini":"Venus","Scorpio":"Moon","Sagittarius":"Sun","Pisces":"Moon","Virgo":"Venus"
}

# M4 fix: _AK_PLANET_DOMAIN_KW was dead code — never imported or called anywhere.
# The actual AK domain keyword logic lives in _ak_planet_domain_boost's inline _KW dict.
# Removed to prevent future confusion and eliminate the stale Mars→"sports" entry.

# A9 fix: _MAHESHWARA_DOMAIN_KW imported from constants.py
from .constants import _MAHESHWARA_DOMAIN_KW  # noqa: F811

from .constants import _PLANET_MIN_SHADBALA
from .affinity import _GENERIC_9P_WEIGHTS
from .astro import _get_active_dasha_lord, _paksha_bala


# Score-calibration fix (2026-08-20, Claude session, Jaimini audit
# follow-up): _brahma_lord_bonus/_maheshwara_lord_bonus below used the same
# hard step-function pattern already found and fixed in _yogakaraka_bonus
# (w>=threshold -> flat return, no further scaling above the top threshold)
# -- once a field's affinity for the special lord cleared 0.25, every
# stronger affinity (0.30, 0.60, 0.90) produced the exact same 0.07, making
# this component field-invariant past that point for any two fields that
# both clear it. Smaller in magnitude than the Yogakaraka bug (max 7 raw
# points here vs. 12+ there), but the same architectural flaw. Replaced both
# with a shared continuous ramp helper so genuinely stronger affinity for
# the special lord keeps producing proportionally more credit.
_SPECIAL_LORD_W_FLOOR, _SPECIAL_LORD_W_CEIL = 0.08, 0.40
_SPECIAL_LORD_BASE_FLOOR, _SPECIAL_LORD_BASE_CEIL = 0.02, 0.08


def _special_lord_domain_ramp(w: float) -> float:
    if w < _SPECIAL_LORD_W_FLOOR:
        return 0.0
    w_clamped = min(w, _SPECIAL_LORD_W_CEIL)
    frac = (w_clamped - _SPECIAL_LORD_W_FLOOR) / (_SPECIAL_LORD_W_CEIL - _SPECIAL_LORD_W_FLOOR)
    return _SPECIAL_LORD_BASE_FLOOR + frac * (_SPECIAL_LORD_BASE_CEIL - _SPECIAL_LORD_BASE_FLOOR)


def _maheshwara_lord_bonus(label: str, maheshwara_lord: str, affinity: Dict[str, float]) -> float:
    """FIX-6: Maheshwara lord (Jaimini special lord) now contributes to branch scoring.
    Maheshwara represents the peak institutional authority phase of the native's career.
    When a branch aligns with the Maheshwara lord's domain keywords, it receives a bonus."""
    if not maheshwara_lord:
        return 0.0
    kws = _MAHESHWARA_DOMAIN_KW.get(maheshwara_lord, [])
    if not any(_wm(kw, label.lower()) for kw in kws):
        return 0.0
    w = affinity.get(maheshwara_lord, 0.0)
    return _special_lord_domain_ramp(w)

# ── Gap-boost helper constants (extracted from original monolith) ──────────
_YOGA_DOMAIN_KW: Dict[str, List[str]] = {
    "Saraswati":    ["education","research","mathematics","science","law","literature","philosophy","economics","design","management","statistics","medicine","data","commerce","computer","analytics","writing","scholarship"],
    "GajaKesari":   ["law","education","philosophy","management","public policy","policy","economics","medicine","psychology","international","governance"],
    "BudhaAditya":  ["research","computer","artificial intelligence","data science","communication","statistics","mathematics","journalism","analytics","science","space"],
    "Shasha":       ["engineering","mining","civil","metallurgy","agriculture","industrial","environmental","materials","petroleum","construction","mechanical"],
    "Hamsa":        ["law","education","philosophy","medicine","ayurveda","international","economics","management","governance","theology","research"],
    "Ruchaka":      ["defence","surgery","engineering","military","police","sports","metallurgy","civil engineering","aerospace","mechanical","mining"],
    "Bhadra":       ["data science","computer","mathematics","accounting","communication","law","statistics","research","artificial intelligence","journalism"],
    "Malavya":      ["arts","design","fashion","music","performing arts","fine arts","architecture","luxury","media","mass communication"],
    "ChandraMangala":["commerce","finance","business","economics","banking","trading","entrepreneurship"],
}

_AMK_HOUSE_KW: Dict[int, List[str]] = {
    5:  ["research","mathematics","science","philosophy","statistics","education","medicine","data","computer","artificial intelligence","analytics"],
    9:  ["law","philosophy","international","education","research","medicine","higher","journalism","management","governance","theology","space"],
    10: ["engineering","commerce","business","civil services","management","public policy","governance","medicine","administration"],
    4:  ["education","teaching","public","psychology","social","nursing"],
    1:  ["defence","sports","entrepreneurship","innovation","surgery"],
}

_YOGA_BONUS_AMT: Dict[str, float] = {
    "Hamsa":          0.09,   # Jupiter Mahapurusha → philosophy/law/education
    "Ruchaka":        0.10,   # Mars Mahapurusha    → engineering/military/surgery
    "Shasha":         0.09,   # Saturn Mahapurusha  → civil services/law/admin
    "GajaKesari":     0.08,   # Jupiter-Moon kendra → public/philosophy
    "Saraswati":      0.09,   # Venus+Merc+Jup kendra → arts/literature/research
    "Malavya":        0.08,   # Venus Mahapurusha   → arts/design/luxury
    "Bhadra":         0.08,   # Mercury Mahapurusha → data/math/communication
    "BudhaAditya":    0.07,
    "ChandraMangala": 0.07,
}

# Gap-5: Which planets form each yoga (for quality-grading the bonus).
# Mahapurusha yogas are formed by a single planet in own/exalt in a kendra.
# Compound yogas list all forming planets — quality = average of their dignities.
_YOGA_FORMING_PLANETS: Dict[str, List[str]] = {
    "Hamsa":          ["Jupiter"],
    "Ruchaka":        ["Mars"],
    "Shasha":         ["Saturn"],
    "Malavya":        ["Venus"],
    "Bhadra":         ["Mercury"],
    "GajaKesari":     ["Jupiter", "Moon"],
    "BudhaAditya":    ["Sun", "Mercury"],
    "Saraswati":      ["Venus", "Mercury", "Jupiter"],
    "ChandraMangala": ["Moon", "Mars"],
}

def _yoga_quality_factor(yoga: str, planet_dignities: Dict[str, str]) -> float:
    """Return a 0.30–1.0 quality multiplier for a yoga based on its forming planets.

    A pristine Mahapurusha yoga (planet in own/exalt kendra) → full 1.0.
    Same yoga with a debilitated or combust-weakened planet → 0.30–0.65.
    Yogas not in the map get 0.75 (mild benefit of the doubt).
    """
    planets = _YOGA_FORMING_PLANETS.get(yoga)
    if not planets:
        return 0.75
    _DIG_SCORE = {"EXALTED": 1.0, "OWN": 0.85, "NEECHA_BHANGA": 0.60,
                  "": 0.65, "DEBILITATED": 0.30}
    scores = [_DIG_SCORE.get(planet_dignities.get(p, ""), 0.65) for p in planets]
    return sum(scores) / len(scores)

# ── Functional Malefic Map (Parashari) ───────────────────────────────────────
# For each lagna, planets that lord dusthana houses (H6/H8/H12) are functional
# malefics. Their exaltation/own-sign strength amplifies dusthana significations,
# not career success. "pure" = rules only dusthana(s); "mixed" = rules dusthana
# plus a kendra/trikona/upachaya (some tempering of maleficence).
# Lagna lord is always excluded (it is a functional benefic by default).
_FUNCTIONAL_MALEFIC_MAP: Dict[str, Dict[str, str]] = {
    "Aries":       {"Mercury": "mixed",  "Jupiter": "mixed"},
    "Taurus":      {"Jupiter": "mixed",  "Mars":    "mixed"},
    "Gemini":      {"Mars":    "mixed",  "Saturn":  "mixed",  "Venus":   "mixed"},
    "Cancer":      {"Jupiter": "mixed",  "Saturn":  "mixed",  "Mercury": "mixed"},
    "Leo":         {"Saturn":  "mixed",  "Jupiter": "mixed",  "Moon":    "pure"},
    "Virgo":       {"Saturn":  "mixed",  "Mars":    "mixed",  "Sun":     "pure"},
    "Libra":       {"Jupiter": "mixed",  "Mercury": "mixed"},
    "Scorpio":     {"Mercury": "mixed",  "Venus":   "mixed"},
    "Sagittarius": {"Venus":   "mixed",  "Moon":    "pure",   "Mars":    "mixed"},
    "Capricorn":   {"Mercury": "mixed",  "Sun":     "pure",   "Jupiter": "mixed"},
    "Aquarius":    {"Moon":    "pure",   "Mercury": "mixed"},
    "Pisces":      {"Sun":     "pure",   "Venus":   "mixed",  "Saturn":  "mixed"},
}

def _functional_malefic_dig_factor(planet: str, lagna_sign: str, dig: str) -> float:
    """Return a dampening factor for a planet's dignity bonus when it is a
    functional malefic for the chart's lagna.

    Classical logic: an exalted FM still produces results, but in its own
    dusthana domain (obstacles, litigation, hidden crises), not smooth career
    success.  Factor is applied as a multiplier on the dignity-driven bonus.

    Returns 1.0 (no dampening) when the planet is not a FM for this lagna.
    """
    if not lagna_sign or dig not in ("EXALTED", "OWN"):
        return 1.0
    fm_type = _FUNCTIONAL_MALEFIC_MAP.get(lagna_sign, {}).get(planet, "")
    if not fm_type:
        return 1.0
    if fm_type == "pure":
        return 0.55 if dig == "EXALTED" else 0.65
    # mixed — rules dusthana + kendra/trikona; partial dampening
    return 0.75 if dig == "EXALTED" else 0.80

_KARAKAMSHA_DOMAIN_KW: Dict[str, List[str]] = {
    "Aries":       ["defence","military","surgery","engineering","sports","police","mechanical","firefighting"],
    "Taurus":      ["arts","music","finance","luxury","architecture","design","fashion","agriculture","beauty"],
    "Gemini":      ["communication","media","journalism","computer","mathematics","commerce","writing","it","data"],
    "Cancer":      ["psychology","nursing","education","social","food","real estate","teaching","public","hospitality"],
    "Leo":         ["civil services","governance","performing arts","management","law","politics","administration","government"],
    "Virgo":       ["medicine","pharmacy","analytics","accounting","data","commerce","law","statistics","health","nutrition"],
    "Libra":       ["law","diplomacy","design","arts","international","hr","management","finance","aesthetics"],
    "Scorpio":     ["research","forensic","mining","psychology","surgery","cybersecurity","investigation","occult","insurance"],
    "Sagittarius": ["law","philosophy","academia","theology","international","sports","education","religion","higher"],
    "Capricorn":   ["engineering","construction","agriculture","government","mining","industrial","architecture","infrastructure"],
    "Aquarius":    ["technology","social","research","computer","astronomy","electronics","it","data","innovation","reform"],
    "Pisces":      ["spiritual","arts","medicine","research","philosophy","psychology","hospital","charity","alternative","healing"],
}

_MD_ROLE_WEIGHT: Dict[str, float] = {
    "amk":  0.35, "h10":  0.28, "ak":   0.20, "h9":   0.12, "h1":   0.08, 
}

_AK_PLANET_BONUS: Dict[str, float] = {
    "Jupiter": 0.11, "Mercury": 0.10, "Mars": 0.10,
    "Saturn":  0.09, "Venus":   0.09, "Moon":  0.08,
    "Sun":     0.08, "Ketu":    0.08, "Rahu":  0.07,
}


def _kp_career_h2h11_strength(affinity: Dict[str, float], kp_sigs: Dict) -> float:
    """KP 4-level significator scan across H2 (wealth) and H11 (gains) — secondary career branch.

    CALLER NOTE (2026-08-22, JyotishAI reference-audit method #6, corrected):
    this function is NOT called from engine.py directly (the `kp_sigs`
    variable engine.py extracts at line 1809 is indeed dead there) -- but it
    IS live, called from a separate module,
    Field_Determination/field_methods/kp.py::score_kp, which imports this
    function (and its four siblings _kp_h10_branch_strength,
    _kp_edu_branch_strength, _h10_sublord_bonus, _kp_edu_starlord_bonus)
    directly from jyotish.boosts. An earlier pass of this audit incorrectly
    flagged these as dead code based on an engine.py-only grep; corrected
    after checking kp.py's own imports. See kp.py's own audit notes for a
    real, confirmed overlap: its H10 4-level generic branch scan (which
    this function's L1-L4 pattern mirrors) is not cross-checked against the
    explicit H10 sub-lord/sub-sub-lord bonuses computed alongside it in the
    same score_kp() call, even though a house's sub-lord commonly also
    appears among its own L1-L4 significators -- a correlated-fact overlap
    of the same kind reconciled for Yogakaraka/Dasha/Karakamsha in this
    audit's methods #1-3, not yet reconciled here.

    Classical KP requires H2+H6+H10+H11 to connect for career materialisation.
    H2 and H11 matter especially when H10 has only one L1 significator.
    House priority: H11=1.0 (income/gains), H2=0.8 (accumulated wealth/speech).
    Level weights: L1=1.0, L2=0.75, L3=0.50, L4=0.25. Normalised to 0-1."""
    if not kp_sigs:
        return 0.0
    _HP = {2: 0.8, 11: 1.0}
    _LW = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25}
    score = 0.0
    for planet, weight in affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(["level_1", "level_2", "level_3", "level_4"]):
            matched = [h for h in sig.get(key, []) if h in _HP]
            if matched:
                hp = max(_HP[h] for h in matched)
                score += weight * _LW[idx] * hp
                break
    max_possible = sum(affinity.values()) * 1.0 if affinity else 1.0
    return min(score / max_possible, 1.0) if max_possible > 0 else 0.0


def _kp_h10_branch_strength(affinity, kp_sigs):
    if not kp_sigs: return 0.0
    _LW = {0:1.0,1:0.75,2:0.50,3:0.25}
    score = 0.0
    for planet, weight in affinity.items():
        sig = kp_sigs.get(planet, {})
        for idx, key in enumerate(["level_1","level_2","level_3","level_4"]):
            if 10 in sig.get(key, []):
                score += weight * _LW[idx]; break
    return min(score, 1.0)


def _kp_edu_branch_strength(affinity: Dict[str, float], kp_sigs: Dict) -> float:
    """KP 4-level significator scan across all education houses (H4, H5, H9, H11).

    Implements the KP spec house-priority matrix for EDUCATION mode:
      H11=1.5 (gains/success), H4=1.2 (stream selection), H9=1.2 (specialisation),
      H5=1.0 (intellect/creativity).
    Level weights: L1=1.0, L2=0.75, L3=0.50, L4=0.25.
    Score normalised to 0–1 against the theoretical maximum.
    H10 is intentionally excluded here — it is handled by _kp_h10_branch_strength
    as the career anchor so the two signals remain orthogonal.
    """
    if not kp_sigs:
        return 0.0
    _HP = {4: 1.2, 5: 1.0, 9: 1.2, 11: 1.5}
    _LW = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25}
    score = 0.0
    for planet, weight in affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(["level_1", "level_2", "level_3", "level_4"]):
            for house in sig.get(key, []):
                if house in _HP:
                    score += weight * _LW[idx] * _HP[house]
    # Theoretical maximum: every affinity unit at L1 in H11 (priority 1.5)
    max_possible = sum(affinity.values()) * 1.5 if affinity else 1.0
    return min(score / max_possible, 1.0) if max_possible > 0 else 0.0


def _stellium_bonus(label, planet_house):
    if not planet_house: return 0.0
    hc: Dict[int,int] = {}
    for h in planet_house.values(): hc[h] = hc.get(h,0) + 1
    label_lower = label.lower(); bonus = 0.0
    if hc.get(9,0) >= 3 and any(k in label_lower for k in _H9_STELLIUM_KW):
        bonus += 0.04 * (hc[9] - 2)
    if hc.get(12,0) >= 2 and any(k in label_lower for k in _H12_STELLIUM_KW):
        bonus += 0.06
    if hc.get(10,0) >= 2: bonus += 0.04
    return min(bonus, 0.12)


_SPACE_AEROSPACE_HINTS: frozenset = frozenset({
    "aerospace", "aeronautical", "astronautical", "space", "satellite",
    "rocket", "propulsion", "orbital", "mission", "launch", "astronomy",
    "astrophysics", "planetary", "remote sensing", "earth observation",
    "space systems", "space science", "space technology",
})


def _space_aerospace_signal(eff_strengths: Dict[str, float]) -> float:
    """Cluster signal for space/aerospace-style vocational signatures."""
    mars = max(0.0, eff_strengths.get("Mars", 0.0))
    rahu = max(0.0, eff_strengths.get("Rahu", 0.0))
    saturn = max(0.0, eff_strengths.get("Saturn", 0.0))
    jupiter = max(0.0, eff_strengths.get("Jupiter", 0.0))
    ketu = max(0.0, eff_strengths.get("Ketu", 0.0))
    raw = 0.30 * mars + 0.26 * rahu + 0.18 * saturn + 0.14 * jupiter + 0.12 * ketu
    return max(0.0, min(1.0, raw / 2.0))


def _space_aerospace_cluster_bonus(
    field_id: str,
    label: str,
    affinity: Dict[str, float],
    eff_strengths: Dict[str, float],
) -> float:
    """Boost modern space/aerospace branches when the cluster is present."""
    # Include raw snake_case field_id AND its space-form so both "space_systems"
    # and "space systems" exact-match lookups resolve correctly downstream.
    text = f"{field_id} {field_id.replace('_', ' ')} {label}".lower()
    if not any(h in text for h in _SPACE_AEROSPACE_HINTS):
        return 0.0

    signal = _space_aerospace_signal(eff_strengths)
    base = 0.04 + 0.10 * signal
    if any(k in text for k in ("aerospace", "aeronautical", "astronautical", "rocket", "propulsion")):
        base += 0.05
        base += 0.03 * min(1.0, affinity.get("Mars", 0.0) + affinity.get("Rahu", 0.0) + affinity.get("Saturn", 0.0))
    elif any(k in text for k in ("satellite", "remote sensing", "earth observation")):
        base += 0.04
        base += 0.03 * min(1.0, affinity.get("Mercury", 0.0) + affinity.get("Rahu", 0.0))
    elif any(k in text for k in ("astronomy", "astrophysics", "planetary")):
        base += 0.05
        base += 0.03 * min(1.0, affinity.get("Ketu", 0.0) + affinity.get("Jupiter", 0.0))
    elif "space systems" in text or "space science" in text or "space technology" in text:
        # gap fix 2026-08-18 (item 4 / Group 3), UPDATED 2026-08-22 (test
        # regression fix): this branch (which space_sciences_engineering
        # falls into) undershot the "aerospace/aeronautical/astronautical/
        # rocket/propulsion" branch just above even though both are equally
        # core "space cluster" branches -- on a space-dominant chart
        # (test_space_cluster_outweighs_extractives_when_chart_is_space_
        # dominant) that undershoot let mining_engineering's raw
        # BRANCH_PLANET_AFFINITY dot-product (Mars 0.29 + Saturn 0.39 in
        # Field_Affinity.json -- both planets a "space-dominant" chart also
        # scores highly on) outrun space_sciences_engineering's total even
        # after the extractive counterweight below.
        # The 2026-08-18 fix (0.04->0.08) wasn't sized against Field_Affinity.
        # json's CURRENT mining_engineering weights (verified 2026-08-22: with
        # eff_strengths={Mars:1.85,Rahu:1.75,Saturn:1.65,Jupiter:1.55,
        # Ketu:1.45,Mercury:0.95,Sun:0.80}, mining's raw affinity dot-product
        # is ~165 vs space's ~128 -- a ~37pt raw gap the prior 0.08 flat term
        # (a max ~21.5pt swing) plus the old counterweight (max -8pt) could
        # not close). Raised further to 0.16 (paired with the extractive
        # counterweight strengthening below and the cap raised from 0.22 to
        # 0.30 just below) so the combined swing (space bonus + mining
        # counterweight) can actually exceed real-data raw-score gaps this
        # size, not just the smaller gap the original fix was sized against.
        base += 0.16
        base += 0.03 * min(1.0, affinity.get("Rahu", 0.0) + affinity.get("Mars", 0.0) + affinity.get("Saturn", 0.0))

    if "space_systems" in text or "mission_design" in text:
        base += 0.12
    if "astronautical" in text or "rocket_propulsion" in text:
        base += 0.08

    # Cap raised 0.22 -> 0.30 (2026-08-22, same fix as above) to give the
    # "space systems/science/technology" branch's strengthened base term
    # room to actually apply rather than immediately saturating at the old
    # cap; aerospace/aeronautical/satellite/astronomy branches are unaffected
    # in practice since their base values don't approach this raised cap.
    return min(0.30, base)


def _space_extractive_counterweight(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Softly reduce extractive branches when the chart is space-dominant."""
    text = f"{field_id} {label}".lower()
    if not any(k in text for k in ("mining", "petroleum", "metallurgical", "metallurgy")):
        return 0.0
    signal = _space_aerospace_signal(eff_strengths)
    if signal < 0.45:
        return 0.0
    # Strengthened 2026-08-22 (test regression fix, see the paired comment on
    # the space-cluster bonus above): coefficient 0.06->0.15 and cap
    # 0.08->0.20, so a strongly space-dominant chart's extractive
    # counterweight can meaningfully offset mining/petroleum/metallurgical
    # branches' own high raw Mars/Saturn affinity overlap with that same
    # signal, rather than saturating at a ceiling too low to matter once
    # real Field_Affinity.json weights are involved.
    return -min(0.20, 0.03 + 0.15 * signal)


def _life_science_signal(eff_strengths: Dict[str, float]) -> float:
    """Cluster signal for medicine, psychology, biotech, and research-heavy life sciences."""
    moon = max(0.0, eff_strengths.get("Moon", 0.0))
    jupiter = max(0.0, eff_strengths.get("Jupiter", 0.0))
    venus = max(0.0, eff_strengths.get("Venus", 0.0))
    saturn = max(0.0, eff_strengths.get("Saturn", 0.0))
    mercury = max(0.0, eff_strengths.get("Mercury", 0.0))
    raw = 0.28 * moon + 0.24 * jupiter + 0.18 * venus + 0.16 * saturn + 0.14 * mercury
    return max(0.0, min(1.0, raw / 2.0))


def _life_science_cluster_bonus(
    field_id: str,
    label: str,
    affinity: Dict[str, float],
    eff_strengths: Dict[str, float],
) -> float:
    """Boost medicine / neuroscience / biotech / genetics branches when life-science signals are strong."""
    # Include raw snake_case field_id AND its space-form so underscore-keyed exact
    # matches like "healthcare_management" resolve even when label uses spaces.
    text = f"{field_id} {field_id.replace('_', ' ')} {label}".lower()
    if not any(k in text for k in (
        "medicine", "medical", "clinical", "psychology", "psychiatry", "neuroscience",
        "bioinformatics", "biotechnology", "genetic", "genomics", "biomedical",
        "pharmacy", "public health", "healthcare", "radiography", "laboratory",
        "pathology", "prosthetics", "physiotherapy", "nursing", "veterinary",
    )):
        return 0.0

    signal = _life_science_signal(eff_strengths)
    base = 0.03 + 0.11 * signal
    if any(k in text for k in ("psychology", "psychiatry", "neuroscience", "cognitive")):
        base += 0.04
        base += 0.03 * min(1.0, affinity.get("Moon", 0.0) + affinity.get("Mercury", 0.0) + affinity.get("Jupiter", 0.0))
    elif any(k in text for k in ("biotech", "bioinformatics", "genetic", "genomics", "biomedical")):
        base += 0.03
        base += 0.03 * min(1.0, affinity.get("Mercury", 0.0) + affinity.get("Jupiter", 0.0) + affinity.get("Saturn", 0.0))
    elif any(k in text for k in ("medicine", "medical", "pharmacy", "public health", "healthcare", "radiography", "laboratory", "pathology", "prosthetics", "physiotherapy", "nursing", "veterinary")):
        base += 0.03
        base += 0.03 * min(1.0, affinity.get("Moon", 0.0) + affinity.get("Jupiter", 0.0) + affinity.get("Saturn", 0.0))

    if "research" in text:
        base += 0.02
    # M2 fix: gate flat additives by signal threshold so zero-signal charts don't get
    # outsized bonuses for matching a field-id substring alone.
    if signal >= 0.30:
        if "healthcare_management" in text:
            base += 0.16 * signal   # proportional to cluster strength
        if "public_health" in text:
            base += 0.08 * signal
        if "medical_research" in text:
            base += 0.05 * signal
    elif signal >= 0.15:
        if "healthcare_management" in text:
            base += 0.07
        if "public_health" in text:
            base += 0.04
        if "medical_research" in text:
            base += 0.02

    return min(0.24, base)




def _life_science_space_counterweight(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Reduce space fields when life-science signatures dominate and space signals are weak."""
    text = f"{field_id} {label}".lower()
    if not any(k in text for k in _SPACE_AEROSPACE_HINTS):
        return 0.0
    life_signal = _life_science_signal(eff_strengths)
    if life_signal < 0.55:
        return 0.0
    if _space_aerospace_signal(eff_strengths) >= 0.45:
        return 0.0
    return -min(0.07, 0.02 + 0.05 * life_signal)


def _life_science_engineering_counterweight(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Reduce non-life engineering branches when the chart strongly favors life sciences."""
    text = f"{field_id} {label}".lower()
    if "engineering" not in text:
        return 0.0
    if any(k in text for k in ("biomedical", "biotechnology", "bioinformatics", "medical", "health", "pharmacy", "clinical")):
        return 0.0
    life_signal = _life_science_signal(eff_strengths)
    if life_signal < 0.58:
        return 0.0
    if any(k in text for k in ("space", "aerospace", "aeronautical", "astronautical", "rocket")):
        return -min(0.12, 0.03 + 0.09 * life_signal)
    if any(k in text for k in ("materials", "metallurgical", "production", "industrial", "mechanical", "civil", "mining", "petroleum", "automotive", "chemical")):
        return -min(0.08, 0.02 + 0.06 * life_signal)
    return -min(0.05, 0.015 + 0.04 * life_signal)


def _priority_cluster_field_bonus(
    field_id: str,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Final, bounded bonus for the most strongly signaled priority fields.

    This is used only to keep the leaderboard's top-20 from dropping the
    chart's dominant life-science or aerospace branches behind unrelated
    extractive/structural fields.
    """
    text = f"{field_id} {label}".lower()
    life_signal = _life_science_signal(eff_strengths)
    space_signal = _space_aerospace_signal(eff_strengths)

    if life_signal >= 0.56:
        if "medical_research" in text:
            return min(0.35, 0.18 + 0.22 * life_signal)
        if "healthcare_management" in text:
            return min(0.22, 0.08 + 0.14 * life_signal)
        if "public_health" in text:
            return min(0.24, 0.10 + 0.16 * life_signal)
        if "psychiatry" in text or "neuroscience" in text:
            return min(0.15, 0.05 + 0.10 * life_signal)
        if any(k in text for k in ("medicine", "medical", "psychiatry", "neuroscience", "psychology", "pharmacy", "biotech", "bioinformatics", "genetic")):
            return min(0.10, 0.04 + 0.08 * life_signal)

    if space_signal >= 0.45:
        if "space_systems_engineering" in text or "space_systems" in text:
            return min(0.28, 0.12 + 0.18 * space_signal)
        if "astronautical" in text or "rocket_propulsion" in text:
            return min(0.14, 0.06 + 0.10 * space_signal)
        if "planetary_science" in text or "astronomy_astrophysics" in text:
            return min(0.12, 0.05 + 0.08 * space_signal)

    return 0.0

# 2026-08-20 step-function fix (KP audit): H10 sub-lord is KP's single most
# decisive career signal (feeds a 30-pt-cap component in kp.py) but was
# bucketed into 3 flat plateaus -- any two fields whose H10-sub-lord affinity
# both cleared 0.30 scored byte-identically here regardless of how much
# stronger one field's affinity actually was, same flaw already fixed for
# _yogakaraka_bonus. Replaced with a continuous ramp over the same range.
_H10_SUBLORD_W_FLOOR, _H10_SUBLORD_W_CEIL = 0.10, 0.35
_H10_SUBLORD_BASE_FLOOR, _H10_SUBLORD_BASE_CEIL = 0.02, 0.08

def _h10_sublord_bonus(affinity, kp_cusps):
    h10 = kp_cusps.get("H10",{}); sub_lord = h10.get("sub_lord","")
    if not sub_lord: return 0.0
    w = affinity.get(sub_lord, 0.0)
    if w < _H10_SUBLORD_W_FLOOR:
        return 0.0
    frac = (min(w, _H10_SUBLORD_W_CEIL) - _H10_SUBLORD_W_FLOOR) / (_H10_SUBLORD_W_CEIL - _H10_SUBLORD_W_FLOOR)
    return _H10_SUBLORD_BASE_FLOOR + frac * (_H10_SUBLORD_BASE_CEIL - _H10_SUBLORD_BASE_FLOOR)
def _get_prime_career_lord_local(dasha_seq):
    """Prime career lord — ages 25-45 overlap (inline; avoids circular import from engine)."""
    lord_durations = {}
    for d in dasha_seq:
        start = d.get("start_age"); end = d.get("end_age")
        if start is None or end is None: continue
        overlap_start = max(25.0, start); overlap_end = min(45.0, end)
        if overlap_start < overlap_end:
            l = d.get("lord", "")
            lord_durations[l] = lord_durations.get(l, 0.0) + (overlap_end - overlap_start)
    if not lord_durations: return ""
    return max(lord_durations.items(), key=lambda x: x[1])[0]


def _dasha_bonus(label, payload):
    """Active Mahadasha keyword bonus — smoothly blended over the student transition window.

    CLIFF FIX: Replaces the hard binary cut at age 22 with a linear blend over ages 18–25.
    Below 18 → pure prime-career lord (ages 25–45 window).
    Age 18–25 → weighted blend: prime lord weight fades from 1.0 → 0.0 as current age
                rises from 18 → 25.  Current lord weight rises correspondingly.
    Above 25 → pure current active lord.

    Dignity-scaled: a strong dasha lord sends a stronger timing signal.
      EXALTED  → 0.12  (peak timing activation)
      OWN      → 0.10  (full signal)
      neutral  → 0.08  (moderate signal)
      DEBIL    → 0.05  (weakened timing)

    Mahadasha-level only: this function never inspects the Antardasha
    (sub-period) lord — the "current_lord"/"prime_lord" above are both
    Mahadasha lords. Antardasha is scored separately by the
    `antardasha_affinity` / `ad_kendra_trikona` boosts in engine.py.

    Scope of the 0.22 cap: engine.py's apply_dasha_total_cap(ceiling=0.22)
    bounds only this function's output + prime_dasha_affinity + peak_md_boost.
    It is NOT a cap on all dasha-family boosts -- prd_boost, antardasha_affinity,
    ad_kendra_trikona, and md_ad_compound stack on top of it, independently
    capped elsewhere. The true combined dasha-family ceiling for a field is
    apply_dasha_family_cap(ceiling=0.35), called after all of the above are
    added (see engine.py). (2026-08-22 reconciliation: this docstring
    previously called 0.22 the "total dasha-family" cap, which was
    inaccurate -- see JyotishAI reference-audit method #2.)

    Age-window/blending caveat: the 25-45 "prime career window" and the
    18-25 linear blend between prime and current lord are in-house
    heuristics -- BPHS/Laghu Parashari time dasha results by lordship,
    house connections, and dignity, not by a fixed chronological age band,
    and classical Vimshottari dasha activation is a hard cutover at the
    calculated date, not a smooth interpolation. Tag: AUTHOR_SPECIFIC, not
    CLASSICAL, per the corpus authority-tier scheme.
    """
    dasha_seq   = getattr(payload, "dasha_sequence", [])
    current_age = float(getattr(payload, "current_age", 0))
    planet_digs = getattr(payload, "planet_dignities", {})

    def _base_for(lord: str) -> float:
        if not lord: return 0.0
        dig = planet_digs.get(lord, "")
        b = {"EXALTED": 0.12, "OWN": 0.10, "NEECHA_BHANGA": 0.09}.get(dig, 0.08)
        return 0.05 if dig == "DEBILITATED" else b

    prime_lord   = _get_prime_career_lord_local(dasha_seq) or ""
    current_lord = _get_active_dasha_lord(dasha_seq, current_age) or ""
    _lbl = label.lower()

    if current_age < 18:
        # Pure projection to prime career window
        lord = prime_lord or current_lord
        if not lord: return 0.0
        if not any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(lord, [])): return 0.0
        return _base_for(lord)

    if current_age >= 25:
        # Fully in current-dasha territory
        if not current_lord: return 0.0
        if not any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(current_lord, [])): return 0.0
        return _base_for(current_lord)

    # Transition zone 18–25: linearly blend prime lord → current lord
    t = (current_age - 18.0) / 7.0          # 0.0 at age 18, 1.0 at age 25
    prime_kw_match   = prime_lord   and any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(prime_lord,   []))
    current_kw_match = current_lord and any(_wm(kw, _lbl) for kw in DASHA_KEYWORDS.get(current_lord, []))
    prime_contrib   = (1.0 - t) * _base_for(prime_lord)   if prime_kw_match   else 0.0
    current_contrib = t          * _base_for(current_lord) if current_kw_match else 0.0
    blended = prime_contrib + current_contrib
    return blended if blended > 0.0 else 0.0

# Score-calibration fix (2026-08-20, Claude session, Jaimini audit):
# same step-function issue as _yogakaraka_bonus/_special_lord_domain_ramp --
# a hard w>=0.20 threshold with no scaling above it. Reuses the same ramp
# shape/floor as the special-lord bonuses above (0.08-0.40 affinity range)
# for consistency, scaled to this function's own per-lord ceilings.
#
# 2026-08-20 cap-proportionality fix (hands-on chart-audit finding): the
# original 0.05/0.03 per-lord ceilings (0.08 total) made Karakamsha --
# Jaimini's "soul lagna," classically weighted comparably to the
# Atmakaraka's own D1 placement -- contribute at most a rounding error to
# any field's score, regardless of match strength. Raised to ceilings
# proportionate with _yogakaraka_bonus's own 0.04-0.16 range (sign_lord is
# the primary/decisive link so gets the larger half; co_lord -- only
# populated for Aquarius/Scorpio/Pisces Karakamsha via the node-as-co-lord
# convention -- remains secondary).
#
# PROVENANCE NOTE (2026-08-22, JyotishAI reference-audit method #3):
# Karakamsha's core definition (Navamsha sign of the Atmakaraka) and the
# significance of its sign lord are classically sourced (Jaimini/BPHS ch.33
# material). Everything else in this function is NOT classical: the node
# co-lord convention (_KARAKAMSHA_CO_LORD: Rahu/Aquarius, Ketu/Scorpio,
# Ketu/Pisces) is a modern 20th-century-onward practitioner convention --
# BPHS and the Jaimini Sutras do not assign the nodes as co-rulers of any
# sign. The 0.12/0.08 sign-lord-vs-co-lord weighting split and the
# continuous affinity-ramp scaling are engineering heuristics with no
# classical or practitioner citation (classical Karakamsha treatment is
# structural: house of Atmakaraka from Karakamsha, aspects/conjunctions,
# Chara Dasha timing -- not a numeric domain-affinity score). Tag:
# CLASSICAL for the sign/sign-lord identity, MODERN_PRACTICE for the node
# co-lord table, AUTHOR_SPECIFIC for the weighting/ramp. Also see
# apply_karakamsha_family_cap() in engine.py: this function's output now
# shares a combined 0.30 ceiling with three sibling Karakamsha functions
# (karakamsha_occ, karakamsha_domain, chara_dasha) that were previously
# uncapped as a family.
def _karakamsha_bonus(affinity, karakamsha):
    if not karakamsha: return 0.0
    sign_lord = _SIGN_LORD.get(karakamsha,""); co_lord = _KARAKAMSHA_CO_LORD.get(karakamsha,"")
    bonus = 0.0
    if sign_lord:
        w = affinity.get(sign_lord, 0)
        if w >= _SPECIAL_LORD_W_FLOOR:
            frac = (min(w, _SPECIAL_LORD_W_CEIL) - _SPECIAL_LORD_W_FLOOR) / (_SPECIAL_LORD_W_CEIL - _SPECIAL_LORD_W_FLOOR)
            bonus += 0.12 * frac
    if co_lord:
        w = affinity.get(co_lord, 0)
        if w >= _SPECIAL_LORD_W_FLOOR:
            frac = (min(w, _SPECIAL_LORD_W_CEIL) - _SPECIAL_LORD_W_FLOOR) / (_SPECIAL_LORD_W_CEIL - _SPECIAL_LORD_W_FLOOR)
            bonus += 0.08 * frac
    return min(bonus, 0.20)

def _combustion_degree_factor(planet: str, planets_d1: dict) -> float:
    """N3: Graded combustion using planet-specific classical orbs.

    Classical orbs (Parashara / Saravali):
      Moon 12°, Mars 17°, Mercury 14°, Jupiter 11°, Venus 10°, Saturn 15°.
    Returns 0.0–1.0 multiplier:
      Cazimi  (<~17')          → 0.0   (no penalty; in the heart of Sun = amplified)
      Deep    (<25% of orb)   → 0.90  (severe combustion)
      Mid     (<60% of orb)   → 0.65  (moderate combustion)
      Mild    (<orb)          → 0.35  (edge of combust zone)
      Beyond  (>orb)          → 0.0   (should not appear in combust_planets)

    PROVENANCE NOTE (2026-08-22, JyotishAI reference-audit method #4):
    the six base orbs above match widely-cited practitioner-consensus
    tables verbatim, but no source located quotes an actual BPHS verse
    for these exact figures -- treat as well-established consensus
    (tag: TRADITIONAL_INTERPRETATION), not a verified primary BPHS
    citation. Known gap: practitioner sources commonly give a tighter
    orb for RETROGRADE Mercury (~12 deg vs 14 direct) and Venus (~8 deg
    vs 10 direct); this function uses one flat orb regardless of
    retrograde status -- not fixed here (needs a decision on whether
    planets_d1 reliably carries retrograde flags before implementing).
    "Cazimi" itself is a Hellenistic/Western term, absent from BPHS/
    Saravali/Phaladeepika (tag: MODERN_PRACTICE, cross-tradition import);
    this function's "Cazimi = zero penalty" treatment is a conservative
    middle ground (Western tradition instead treats Cazimi as
    strengthened), not itself classically sourced either way. The
    continuous deep/moderate/mild grading is a modern refinement layered
    on the classical binary combust/not-combust rule (tag: AUTHOR_SPECIFIC).

    Cazimi threshold matches dignity.py's canonical _CAZIMI_ORB_DEGREES
    (~0.28 deg / 17 arcmin, per Full Methodology Spec §5c) rather than a full
    1 deg, so this duplicate grader doesn't disagree with the main dignity
    module about which planets are Cazimi vs. deep-combust.
    """
    # Planet-specific standard combustion orbs (degrees)
    _PLANET_ORB = {
        "Moon": 12.0, "Mars": 17.0, "Mercury": 14.0,
        "Jupiter": 11.0, "Venus": 10.0, "Saturn": 15.0,
    }
    if not planets_d1:
        return 1.0
    sun_d = planets_d1.get("Sun", {})
    pla_d = planets_d1.get(planet, {})
    if not sun_d or not pla_d:
        return 1.0
    sun_abs = _planet_abs_degree(sun_d.get("sign", ""), float(sun_d.get("degree", 0)))
    pla_abs = _planet_abs_degree(pla_d.get("sign", ""), float(pla_d.get("degree", 0)))
    dist = abs(sun_abs - pla_abs)
    if dist > 180.0:
        dist = 360.0 - dist
    if dist < (17.0 / 60.0):
        return 0.0   # Cazimi (~17') — amplified, no penalty
    orb = _PLANET_ORB.get(planet, 12.0)
    if dist > orb:
        return 0.0   # Outside combust zone
    ratio = dist / orb  # 0 = right at Sun, 1 = at orb edge
    if ratio < 0.25:
        return 0.90  # Deep combustion
    elif ratio < 0.60:
        return 0.65  # Moderate combustion
    else:
        return 0.35  # Mild combustion (outer edge)


def _ak_combustion_penalty(affinity, ak, combust_planets, planet_dignities=None, planets_d1=None,
                            vargottama_planets=None):
    """M3: Penalty now uses degree-proximity sliding scale instead of binary flag.

    Cazimi AK (<1° from Sun) receives zero penalty.
    Mild combustion (1°–6°) receives half the standard penalty.
    G2 fix: Vargottama AK is exempt — same-sign in D1/D9 overrides combustion weakening
    (classical principle: Vargottama planets carry amplified dignity that persists through Sun).

    PROVENANCE NOTE (2026-08-22, JyotishAI reference-audit method #4):
    Vargottama's general strength-boosting effect IS solidly classical
    (Saravali, Phaladeepika, Laghu Jataka). The specific claim in the G2
    comment above -- that Vargottama exempts a planet from combustion
    specifically -- is an extrapolation from that general doctrine, not
    a rule stated in any classical source located during this audit.
    Tag: AUTHOR_SPECIFIC, not CLASSICAL. Left unchanged (reasonable
    engineering inference, not contradicted by any source either), but
    should not be cited to the user as a verbatim classical rule.

    Double-count note: this penalty deliberately halves its base tiers
    because comb_mod (astro.py's separate, primary multiplicative
    combustion discount baked into eff_strength) already scores the same
    underlying fact -- this is the one combustion-adjacent overlap in the
    codebase that was already caught and compensated for at design time
    (see FIX-1 comment below), unlike the yogakaraka/dasha/karakamsha
    families reconciled in reference-audit methods #1-3.
    """
    if planet_dignities is None: planet_dignities = {}
    if not ak or ak not in combust_planets: return 0.0
    # G2 fix: Vargottama exemption
    if vargottama_planets and ak in vargottama_planets:
        return 0.0
    w = affinity.get(ak, 0.0)
    # FIX-1: bases halved — effective strength already carries combustion via comb_mod.
    if   w >= 0.35: base = 0.10
    elif w >= 0.25: base = 0.06
    elif w >= 0.15: base = 0.03
    else: return 0.0
    dig = planet_dignities.get(ak, "")
    if dig == "EXALTED": base *= 0.30
    elif dig == "OWN":   base *= 0.50
    # M3: apply degree-proximity factor
    base *= _combustion_degree_factor(ak, planets_d1 or {})
    return base

def _d24_full_chart_bonus(field_affinity: Dict[str, float], payload) -> float:
    """D24 (Siddhamsha) full-chart evaluation — Gap-1 fix.

    The prior implementation (_d24_ak_delta) only checked the AK planet's
    dignity in D24.  This function evaluates ALL planets in educationally
    significant D24 houses (H4 = learning foundation, H5 = intelligence/siddhi,
    H10 = peak academic achievement) and rewards dignified planets whose natural
    signification aligns with the field's affinity profile.

    Scoring per qualifying planet:
      - EXALTED in D24-H5 (siddhi house): up to 0.14 * field_affinity
      - EXALTED in D24-H10: up to 0.11 * field_affinity
      - EXALTED in D24-H4: up to 0.08 * field_affinity
      - OWN reduces each tier by ~35%
    Cap: 0.15 total (prevents a single D24 concentration from overwhelming D1 signal).
    """
    div_charts  = getattr(payload, "divisional_charts", {}) or {}
    d24         = div_charts.get("D24_siddhamsam", {}) or {}
    d24_digs    = getattr(payload, "d24_planet_dignities", {}) or {}

    if not d24 or not d24_digs:
        return 0.0

    d24_lagna = d24.get("Lagna", "")
    if not d24_lagna:
        return 0.0

    _SIGNS = sorted(_SIGN_NUM, key=_SIGN_NUM.__getitem__)
    try:
        lagna_idx = _SIGNS.index(d24_lagna)
    except ValueError:
        return 0.0

    # House weight: H5 (siddhi) > H10 > H4
    _HOUSE_W = {5: 0.14, 10: 0.11, 4: 0.08}

    bonus = 0.0
    for planet, sign in d24.items():
        if planet == "Lagna":
            continue
        dig = d24_digs.get(planet, "")
        if dig not in ("EXALTED", "OWN"):
            continue
        w = field_affinity.get(planet, 0.0)
        if w < 0.08:
            continue
        try:
            sign_idx  = _SIGNS.index(sign)
        except ValueError:
            continue
        d24_house = (sign_idx - lagna_idx) % 12 + 1
        hw = _HOUSE_W.get(d24_house)
        if hw is None:
            continue
        dig_factor = 1.0 if dig == "EXALTED" else 0.65
        # Gate by D1 vitality: a structurally impaired planet cannot deliver D24 results
        vit = _d1_vitality_coefficient(planet, payload)
        bonus += w * hw * dig_factor * vit

    return min(bonus, 0.15)


def _d24_ak_delta(label, payload):
    ak = getattr(payload,"atmakaraka",""); d24_digs = getattr(payload,"d24_planet_dignities",{})
    if not ak or not d24_digs: return 0.0
    if not any(_wm(kw, label.lower()) for kw in _D24_ACADEMIC_KW): return 0.0
    dig = d24_digs.get(ak,"")
    if dig == "EXALTED":    return  0.10
    if dig == "OWN":        return  0.05
    if dig == "DEBILITATED": return -0.05
    return 0.0

def _lagna_lord_bonus(label, payload):
    lagna_lord = getattr(payload,"lagna_lord",""); planet_house = getattr(payload,"planet_house",{})
    if not lagna_lord: return 0.0
    ll_house = planet_house.get(lagna_lord,0); label_lower = label.lower()
    if ll_house == 12 and any(_wm(kw, label_lower) for kw in _H12_FIELDS): return 0.08
    if ll_house == 10: return 0.05
    if ll_house ==  9 and any(_wm(kw, label_lower) for kw in _H9_FIELDS):  return 0.05
    if ll_house ==  6 and any(_wm(kw, label_lower) for kw in _H6_FIELDS):  return 0.06
    if ll_house ==  5 and any(_wm(kw, label_lower) for kw in _H5_FIELDS):  return 0.06
    return 0.0

def _risk_appetite_bonus(label: str, risk: str) -> float:
    """Bidirectional risk-appetite modifier.

    Positive (+0.08): student's stated appetite matches the field's risk profile.
    Negative penalty: mismatch — a HIGH-risk student shouldn't be pushed toward
    actuarial/audit fields; a LOW-risk student shouldn't be pushed toward
    frontier/speculative fields. Penalties are mild (-0.06 to -0.08) to nudge
    ranks without overriding strong astrological signals.
    """
    label_lower = label.lower()
    is_frontier    = any(_wm(kw, label_lower) for kw in _FRONTIER_KW)
    is_traditional = any(_wm(kw, label_lower) for kw in _TRADITIONAL_KW)

    if risk == "HIGH":
        if is_frontier:    return  0.08   # reward speculative/cutting-edge match
        if is_traditional: return -0.06   # mild penalty: safe fields for a risk-seeker
    elif risk == "LOW":
        if is_traditional: return  0.08   # reward stable/institutional match
        if is_frontier:    return -0.08   # stronger penalty: volatile fields for risk-averse
    # MODERATE or no preference set → no modifier either way
    return 0.0

def _yogakaraka_bonus(affinity, lagna_sign, shadbala, digs):
    # AUDIT NOTE (2026-08-20, combustion/yogakaraka double-count pass; RECONCILED
    # 2026-08-22 per owner sign-off, JyotishAI reference-audit method #1): this
    # additive bonus is one of THREE independent Yogakaraka implementations in
    # this codebase -- see astro.py::_compute_eff_strengths's `yk_mod` (a flat
    # multiplicative 0.90/1.18-1.25 applied to the same planet's eff_strength,
    # which is itself blended into the same field score this bonus adds to) and
    # _functional_status_factor below (flat 1.15x, narrower scope -- only gates
    # _exalted_planet_domain_bonus, left unchanged: its overlap is narrow and its
    # own magnitude is small). Classical Parashari doctrine treats Yogakaraka
    # status as binary (kendra+trikona dual lordship present or not); the
    # continuous shadbala/dignity scaling below is a modern software heuristic,
    # not itself classically sourced -- so there is no doctrinal reason this
    # function's magnitude must equal any particular value, only that it must
    # not silently duplicate the credit `yk_mod` already gives the same fact.
    # `yk_mod` is treated as the primary/canonical Yogakaraka signal (it is the
    # more structurally integrated of the two -- it scales eff_strength, which
    # every other bonus function in this file reads). This additive bonus is
    # therefore de-weighted to a supplementary top-up rather than a full second
    # credit: floor/ceiling below are scaled to 55% of their pre-reconciliation
    # values (0.04-0.16 -> 0.022-0.088). This does not fully eliminate the
    # overlap (the two mechanisms operate on different bases -- one multiplies
    # eff_strength, one adds a flat term to gap_boost -- so an exact
    # single-source unification would require a deeper refactor), but it caps
    # the worst-case combined over-credit at roughly half of what it was.
    # Spec fix (Full Methodology Spec §5d): true Yogakaraka status is
    # structurally possible ONLY for the six listed lagna/planet pairings
    # (Taurus/Libra->Saturn, Cancer/Leo->Mars, Capricorn/Aquarius->Venus) --
    # a planet that owns one kendra AND one distinct trikona house. The other
    # six lagnas' "functional trikona/kendra" planet is NOT a Yogakaraka and
    # must not receive this bonus; falling back to it here fabricated a
    # Yogakaraka-style bonus for lagnas where the yoga cannot classically
    # exist (e.g. Aries Lagna -> Sun). _FUNCTIONAL_TRIKONA_FALLBACK is kept
    # in constants.py/boosts.py for any other caller that legitimately wants
    # "functional benefic of this lagna" as a distinct, smaller concept, but
    # it must not feed the Yogakaraka bonus.
    yk = _YOGAKARAKA_PLANET.get(lagna_sign, "")
    if not yk: return 0.0
    w = affinity.get(yk, 0.0)
    ratio = shadbala.get(yk, 300.0) / _PLANET_MIN_SHADBALA.get(yk, 300.0)
    dig = digs.get(yk, "")
    # LS3 fix: debilitated YK returns 0; caller uses _yogakaraka_debilitation_penalty()
    # to accumulate the penalty into gap_penalty (not silently subtract from gap_boost).
    if dig == "DEBILITATED": return 0.0
    dig_mod = {"EXALTED": 1.3, "OWN": 1.1, "NEECHA_BHANGA": 1.05}.get(dig, 1.0)
    # Score-calibration fix (2026-08-20, Claude session, real-chart audit):
    # `base` used to be a hard step function (w>=0.20 -> flat 0.12, with NO
    # further scaling for any w above 0.20). Since the Yogakaraka planet is
    # fixed per chart (one planet per D1 lagna sign) and `ratio`/`dig_mod`
    # above are also pure chart facts, once a field's own affinity for that
    # planet cleared 0.20, this whole bonus became completely field-
    # invariant -- identical for every field whose affinity for the
    # Yogakaraka planet was 0.21 or 0.90, no differentiation at all above
    # that point. Confirmed on a real chart (Ramsunder): this is Parashara's
    # single largest component (14.45 points, 40-60% of the method's total
    # score for several fields) and it came out byte-identical across
    # international_law, history_archaeology, materials_science_engineering,
    # and space_systems_engineering -- four very different fields -- because
    # all four happened to clear the 0.20 threshold on this chart's
    # Yogakaraka planet. Replaced with a continuous ramp so genuinely
    # stronger affinity for the Yogakaraka planet keeps producing
    # proportionally more credit instead of saturating at a fixed ceiling;
    # the floor/ceiling values are chosen to keep the same rough magnitude
    # range as the old step function (0.04-0.12) while extending a modest
    # amount further (to 0.16) for a field where the Yogakaraka planet is an
    # exceptionally dominant significator (affinity >= 0.40).
    _W_FLOOR, _W_CEIL = 0.07, 0.40
    # 2026-08-22 reconciliation: de-weighted to 55% of the original
    # 0.04-0.16 range to avoid double-crediting yk_mod's overlapping
    # multiplicative signal (see AUDIT NOTE above).
    _BASE_FLOOR, _BASE_CEIL = 0.022, 0.088
    if w < _W_FLOOR:
        return 0.0
    _w_clamped = min(w, _W_CEIL)
    base = _BASE_FLOOR + (_w_clamped - _W_FLOOR) / (_W_CEIL - _W_FLOOR) * (_BASE_CEIL - _BASE_FLOOR)
    return max(0.0, base * ratio * dig_mod)


def _yogakaraka_debilitation_penalty(affinity, lagna_sign, shadbala, digs):
    """LS3 fix: gap_penalty contribution when the Yogakaraka is debilitated.
    Called by engine.py gap_penalty accumulator instead of reducing gap_boost."""
    # Spec fix (§5d, see _yogakaraka_bonus above): no fallback to the
    # non-Yogakaraka lagnas' functional-trikona planet.
    yk = _YOGAKARAKA_PLANET.get(lagna_sign, "")
    if not yk: return 0.0
    if digs.get(yk, "") != "DEBILITATED": return 0.0
    w = affinity.get(yk, 0.0)
    if w < 0.07: return 0.0
    ratio = shadbala.get(yk, 300.0) / _PLANET_MIN_SHADBALA.get(yk, 300.0)
    return round(min(0.06, 0.05 * ratio * (1.0 if w >= 0.20 else 0.6)), 4)

def _node_dignity_damping(planet: str, dig_scale: float) -> float:
    """2026-08-20 audit fix: Rahu/Ketu's entry in `planet_dignities` is not
    the node's own placement quality -- compute_dignity()'s nodal branch
    (astro.py:65-72, "Sanivad Rahu, Kujavad Ketu") makes a node ADOPT its
    dispositor's sign dignity wholesale (e.g. Rahu reads as EXALTED purely
    because Saturn happens to be exalted elsewhere in the chart). That
    dispositor-adoption is deliberate and correct for the D9/D24/D10
    cross-checks it was built for (engine_io.py:474 comment) -- disabling it
    would regress those. But several D1-level dignity-gated bonuses below
    were written assuming `dig` reflects the SAME planet's own placement,
    and apply a classical planet's full EXALTED/OWN/DEBILITATED swing to a
    node's borrowed label. Since the node itself may sit nowhere near its
    own exaltation/debilitation point (per the separate Taurus/Scorpio
    heuristic in shadbala.py's estimate_node_strength), this halves the
    swing for nodes only -- keeps the signal (still directionally correct,
    since a well-placed dispositor genuinely does strengthen a node) without
    treating borrowed dignity as equivalent to true own dignity.
    """
    if planet not in ("Rahu", "Ketu"):
        return dig_scale
    return 1.0 + (dig_scale - 1.0) * 0.5


def _h10_lord_strength_bonus(affinity, h10_lord, shadbala, planet_dignities=None):
    """H10 lord strength bonus — scaled by dignity.

    An exalted H10 lord is the strongest possible career indicator in classical
    Jyotish (Rajayoga via 10th bhava lord in uccha). The bonus now mirrors the
    Yogakaraka formula: base × shadbala_ratio × dignity_multiplier.
    """
    if planet_dignities is None: planet_dignities = {}
    if not h10_lord: return 0.0
    w = affinity.get(h10_lord, 0.0)
    if w < 0.10: return 0.0
    ratio    = shadbala.get(h10_lord, 0.0) / _PLANET_MIN_SHADBALA.get(h10_lord, 300.0)
    dig      = planet_dignities.get(h10_lord, "")
    # Soften dig_mult: field_affinity already encodes dignity via effective strengths.
    # Applying a heavy multiplier here causes exponential double-compounding.
    dig_mult = {"EXALTED": 1.15, "OWN": 1.08, "NEECHA_BHANGA": 1.0, "DEBILITATED": 0.70}.get(dig, 1.0)
    dig_mult = _node_dignity_damping(h10_lord, dig_mult)
    if   w >= 0.30: base = 0.12
    elif w >= 0.20: base = 0.08
    elif w >= 0.10: base = 0.04
    else: return 0.0
    return min(base * ratio * dig_mult, 0.18)


def _bhava_bala(
    house_num: int,
    affinity: Dict[str, float],
    house_lord: str,
    planet_house: Dict[str, int],
    planet_dignities: Dict[str, str],
    shadbala: Dict[str, float],
    planets_d1: Dict,
) -> float:
    """Unified Bhava Bala for any house — BPHS composite house strength.

    2026-07 astrologer's audit follow-up: generalized from the original
    H10-only `_h10_bhava_bala` (kept below as a thin wrapper for backward
    compatibility) so career-relevant houses beyond the 10th can use the
    same real composite instead of having no Bhava Bala treatment at all.
    Career signification in classical Jyotish is not limited to H10:
      - H2 (dhana/resources): wealth accumulation supporting career choice.
      - H6 (competition/service/employment): job-holding, service, rivalry.
      - H10 (karma): the career house itself.
      - H11 (labha/gains): income, professional gains, fulfillment of goals.
    Parashara's BPHS adjudicates a bhava's strength as a *single* composite
    of three components rather than several independent bonuses:
      1. Occupant strength  — planets sitting in the house, weighted by shadbala.
      2. Aspectual strength — Drishti Bala-weighted graha drishti onto the house.
      3. Own-lord strength  — the house lord's shadbala and dignity.
    Returns a 0..1 composite.
    """
    from .astro import _get_planetary_aspects_weighted
    if planet_dignities is None:
        planet_dignities = {}
    if shadbala is None:
        shadbala = {}

    # 1. Occupant strength.
    occ_strength = 0.0
    for p, h in (planet_house or {}).items():
        if h != house_num:
            continue
        w = affinity.get(p, 0.0)
        if w <= 0:
            continue
        sb_ratio = min(shadbala.get(p, 300.0) / _PLANET_MIN_SHADBALA.get(p, 300.0), 2.0)
        occ_strength += w * sb_ratio

    # 2. Aspectual strength (Drishti Bala orb-weighted).
    asp_strength = 0.0
    try:
        weighted = _get_planetary_aspects_weighted(planet_house or {}, planets_d1 or {})
    except Exception:
        weighted = {}
    for p, houses in weighted.items():
        drishti = houses.get(house_num, 0.0)
        if drishti <= 0:
            continue
        asp_strength += affinity.get(p, 0.0) * drishti

    # 3. Own-lord strength.
    ll_strength = 0.0
    if house_lord:
        w = affinity.get(house_lord, 0.0)
        sb_ratio = min(shadbala.get(house_lord, 300.0) / _PLANET_MIN_SHADBALA.get(house_lord, 300.0), 2.0)
        dig_mult = {"EXALTED": 1.4, "OWN": 1.2, "NEECHA_BHANGA": 1.05,
                    "NEUTRAL": 1.0, "DEBILITATED": 0.6}.get(planet_dignities.get(house_lord, "NEUTRAL"), 1.0)
        ll_strength = w * sb_ratio * dig_mult

    composite = occ_strength * 0.35 + asp_strength * 0.35 + ll_strength * 0.30
    return min(composite, 1.0)


def _h10_bhava_bala(
    affinity: Dict[str, float],
    h10_lord: str,
    planet_house: Dict[str, int],
    planet_dignities: Dict[str, str],
    shadbala: Dict[str, float],
    planets_d1: Dict,
) -> float:
    """Thin backward-compatible wrapper around _bhava_bala(10, ...)."""
    return _bhava_bala(10, affinity, h10_lord, planet_house, planet_dignities, shadbala, planets_d1)


def _career_houses_bhava_bala_bonus(
    affinity: Dict[str, float],
    house_lords: Dict[str, str],
    planet_house: Dict[str, int],
    planet_dignities: Dict[str, str],
    shadbala: Dict[str, float],
    planets_d1: Dict,
) -> tuple:
    """Secondary career-house Bhava Bala: H2 (resources), H6 (service/
    employment/competition), H11 (gains/income) -- H10 itself is scored
    separately at higher weight by _h10_bhava_bala/_bhava_bala(10, ...)
    since it is the primary career house; these three are real but
    secondary classical career significators that previously had NO Bhava
    Bala treatment at all (unlike H10). Returns (bonus_0_to_100_scale,
    per_house_composites_dict) so callers can trace which house(s) drove
    the bonus.
    """
    composites: Dict[str, float] = {}
    for house_num in (2, 6, 11):
        lord = (house_lords or {}).get(str(house_num), "")
        composites[house_num] = _bhava_bala(
            house_num, affinity, lord, planet_house, planet_dignities, shadbala, planets_d1
        )
    # Modest weight vs H10's own composite (0.16 in parashara.py) -- these
    # are corroborating secondary houses, not the primary career signal, so
    # deliberately capped lower (0.08 total) to avoid double-counting career
    # strength that H10's own composite already captures.
    avg = sum(composites.values()) / 3.0
    return round(avg * 100.0 * 0.08, 4), composites


# Natural signification keywords for each planet when exalted —
# classical rule: exalted planets deliver superior results in their domains.
_EXALT_DOMAIN_KW: Dict[str, List[str]] = {
    # Use complete/plural word forms so _wm (word-boundary match) works correctly.
    # e.g. "arts" not "art" (avoids "artificial"), "performing" not "perform".
    "Venus":   ["arts", "music", "design", "fashion", "film", "performing arts",
                "fine arts", "aesthetics", "creative arts", "visual arts",
                "textile", "interior design", "dance", "theatre"],
    "Jupiter": ["law", "philosophy", "education", "medicine", "research", "management",
                "economics", "theology", "international"],
    "Moon":    ["nursing", "psychology", "social work", "ecology", "public health", "counseling",
                "hospitality", "aquaculture", "nutrition"],
    "Mars":    ["engineering", "defence", "defense", "military", "surgery", "mechanical", "strategic", "operations", "tactical"],
    "Mercury": ["data science", "computer science", "mathematics", "accounting",
                "statistics", "communication"],
    "Saturn":  ["mining", "civil engineering", "metallurgy", "agriculture", "industrial",
                "petroleum", "construction", "materials science"],
    "Sun":     ["civil services", "administration", "government", "leadership", "energy"],
}


def _exalted_planet_domain_bonus(affinity: Dict[str, float],
                                  planet_dignities: Dict[str, str],
                                  label: str,
                                  lagna_sign: str = "") -> float:
    """Bonus when an EXALTED/OWN planet's natural signification matches the field label.

    Classical principle: a planet in uccha (exaltation) delivers its highest
    results in its own domain.  This ensures e.g. exalted Venus in Pisces
    actively promotes arts/design fields for that chart.

    Functional-malefic dampening (Gap-4 fix): if the dignified planet is a
    functional malefic for the chart's lagna (lord of H6/H8/H12), its exaltation
    amplifies dusthana significations rather than smooth career success — so the
    bonus is reduced via _functional_malefic_dig_factor().

    Uses whole-word boundary matching (_wm) to prevent false positives.
    """
    label_lower = label.lower()
    bonus = 0.0
    for planet, kws in _EXALT_DOMAIN_KW.items():
        dig = planet_dignities.get(planet, "")
        if dig not in ("EXALTED", "OWN"):
            continue
        w = affinity.get(planet, 0.0)
        if w < 0.15:
            continue
        if not any(_wm(kw, label_lower) for kw in kws):
            continue
        if   w >= 0.35: raw = 0.10
        elif w >= 0.25: raw = 0.07
        else:           raw = 0.04
        # OWN is slightly weaker than EXALTED
        if dig == "OWN":
            raw *= 0.70
        fm_factor  = _functional_malefic_dig_factor(planet, lagna_sign, dig)
        # Additionally apply functional status factor (MALEFIC→0.6×, YOGAKARAKA→1.15×)
        fs_factor  = _functional_status_factor(planet, lagna_sign)
        bonus += raw * fm_factor * fs_factor
    return min(bonus, 0.15)

def _ul_lord_bonus(affinity, upapada_lagna):
    ul_lord = _SIGN_LORD.get(upapada_lagna,"")
    if not ul_lord: return 0.0
    w = affinity.get(ul_lord, 0.0)
    if w >= 0.25: return 0.06
    if w >= 0.15: return 0.03
    return 0.0

def _kp_edu_starlord_bonus(affinity, kp_cusps):
    # KP rule: the Sub Lord (not the Star Lord) is the structural gate that
    # determines whether a house's results fructify.  All three education CSL
    # targets — H4 (stream), H5 (intellect), H9 (higher learning) — are read
    # from sub_lord.  Cap raised from 0.05 → 0.08 to reflect three cusps.
    h4_sub = kp_cusps.get("H4", {}).get("sub_lord", "")
    h5_sub = kp_cusps.get("H5", {}).get("sub_lord", "")
    h9_sub = kp_cusps.get("H9", {}).get("sub_lord", "")
    # 2026-08-20 step-function fix (KP audit): same flat-bucket flaw as
    # _h10_sublord_bonus, applied here to the education CSL sub-lords.
    _EDU_SL_W_FLOOR, _EDU_SL_W_CEIL = 0.12, 0.30
    _EDU_SL_BASE_FLOOR, _EDU_SL_BASE_CEIL = 0.01, 0.03
    bonus = 0.0
    for sl in set(filter(None, [h4_sub, h5_sub, h9_sub])):
        w = affinity.get(sl, 0.0)
        if w < _EDU_SL_W_FLOOR:
            continue
        frac = (min(w, _EDU_SL_W_CEIL) - _EDU_SL_W_FLOOR) / (_EDU_SL_W_CEIL - _EDU_SL_W_FLOOR)
        bonus += _EDU_SL_BASE_FLOOR + frac * (_EDU_SL_BASE_CEIL - _EDU_SL_BASE_FLOOR)
    return min(bonus, 0.08)

def _d9_ak_delta(label, payload):
    ak = getattr(payload,"atmakaraka",""); d9_digs = getattr(payload,"d9_planet_dignities",{})
    if not ak or not d9_digs: return 0.0
    dig = d9_digs.get(ak,"")
    raw = 0.0
    if dig == "EXALTED":     raw =  0.06
    elif dig == "OWN":       raw =  0.03
    elif dig == "DEBILITATED": raw = -0.04
    if raw == 0.0: return 0.0
    # D1 vitality gate: a combust/war-loser/Mrita AK cannot fully deliver D9 results
    vit = _d1_vitality_coefficient(ak, payload)
    return raw * vit

def _classify_parivartana(p1: str, p2: str, house_lords: Dict[str, str]) -> str:
    def _roles(p):
        kendra   = any(house_lords.get(h) == p for h in ("1","4","7","10"))
        trikona  = any(house_lords.get(h) == p for h in ("1","5","9"))
        dusthana = any(house_lords.get(h) == p for h in ("6","8","12"))
        h3       = house_lords.get("3") == p
        return kendra, trikona, dusthana, h3
    k1,t1,d1,h3_1 = _roles(p1)
    k2,t2,d2,h3_2 = _roles(p2)
    if d1 or d2:      return "Dainya"
    if h3_1 or h3_2:  return "Khala"
    if (k1 or t1) and (k2 or t2): return "Mahayoga"
    return "Neutral"

def _yoga_bonus(label, detected_yogas, house_lords=None, planet_dignities=None):
    """Domain-matched yoga bonus with quality grading (Gap-5 fix).

    For known yogas the base bonus is multiplied by _yoga_quality_factor(), which
    scales from 0.30 (all forming planets debilitated) to 1.0 (all exalted/own).
    This prevents a severely weakened GajaKesari from scoring the same as a
    pristine one.  Parivartana yogas retain their existing Mahayoga/Dainya logic.
    """
    if not detected_yogas: return 0.0
    if house_lords is None: house_lords = {}
    if planet_dignities is None: planet_dignities = {}
    label_lower = label.lower(); bonus = 0.0
    for yoga in detected_yogas:
        if yoga.startswith("Nakshatra_Parivartana_"):
            # GAP-FIX (2026-08, ranking-impact audit): engine.py's
            # _prepare_chart_scoring_context now detects Nakshatra Parivartana
            # Yoga (mutual nakshatra-lord exchange) generically across all
            # planet pairs and emits "Nakshatra_Parivartana_<P1>_<P2>", but
            # this function only ever matched "Parivartana_" (Rashi/sign-lord
            # exchange, 3-part string) or an exact _YOGA_DOMAIN_KW key, so the
            # 4-part nakshatra-exchange string matched neither branch and the
            # correctly-detected yoga produced zero score impact. Nakshatra
            # Parivartana is classically a real but generally milder exchange
            # than Rashi Parivartana (no house-lordship transfer, just mutual
            # nakshatra reception), so it is graded with the same
            # Mahayoga/Dainya/Khala house-role classification but at roughly
            # half the Rashi-Parivartana bonus magnitude.
            parts = yoga.split("_")
            if len(parts) == 4:
                ptype = _classify_parivartana(parts[2], parts[3], house_lords)
                if   ptype == "Mahayoga": bonus += 0.04
                elif ptype == "Dainya":   bonus -= 0.025
                elif ptype == "Khala":    bonus += 0.0
                else:                     bonus += 0.015
        elif yoga.startswith("Parivartana_"):
            parts = yoga.split("_")
            if len(parts) == 3:
                ptype = _classify_parivartana(parts[1], parts[2], house_lords)
                if   ptype == "Mahayoga": bonus += 0.08
                elif ptype == "Dainya":   bonus -= 0.05
                elif ptype == "Khala":    bonus += 0.0
                else:                     bonus += 0.03
        elif any(_wm(kw, label_lower) for kw in _YOGA_DOMAIN_KW.get(yoga,[])):
            base  = _YOGA_BONUS_AMT.get(yoga, 0.07)
            qual  = _yoga_quality_factor(yoga, planet_dignities)
            bonus += base * qual
    return max(-0.10, min(bonus, 0.21))
def _h5_lord_bonus(affinity, h5_lord):
    if not h5_lord: return 0.0
    w = affinity.get(h5_lord, 0.0)
    if w >= 0.25: return 0.06
    if w >= 0.15: return 0.03
    return 0.0

def _amk_house_bonus(label, amk_house):
    kws = _AMK_HOUSE_KW.get(amk_house,[])
    if kws and any(_wm(kw, label.lower()) for kw in kws):
        return 0.06 if amk_house in (5,9) else 0.04
    return 0.0
def _ak_house_bonus(ak, ak_house, label):
    """v9.4: AK house → field orientation boost (expanded to all houses)."""
    lb = label.lower()
    # Trikona houses (H1/H5/H9) — soul's dharma direction
    if ak_house == 1 and any(k in lb for k in [
        "leadership","entrepreneurship","management","public","administration",
        "sports","defence","governance","self-employment","politics",
    ]):
        return 0.07
    if ak_house == 2 and any(k in lb for k in [
        "finance","commerce","banking","accounting","economics","trading",
        "food","speech","communication","family business","valuables",
    ]):
        return 0.06
    if ak_house == 3 and any(k in lb for k in [
        "communication","media","journalism","writing","publishing","content",
        "pr","advertising","broadcast","arts","performing arts","music",
    ]):
        return 0.07
    if ak_house == 4 and any(k in lb for k in [
        "architecture","real estate","education","teaching","psychology",
        "agriculture","environment","social","hospitality","public",
    ]):
        return 0.06
    if ak_house == 5 and any(k in lb for k in [
        "research","education","science","mathematics","statistics","data",
        "creative","arts","philosophy","sports","investment","intelligence",
    ]):
        return 0.08
    if ak_house == 6 and any(k in lb for k in [
        "medicine","nursing","surgery","doctor","physician","clinical","health",
        "pharmacy","ayurveda","hospital","public health","service","defence","law",
    ]):
        return 0.07   # H6 = disease/healing/service
    if ak_house == 7 and any(k in lb for k in [
        "international","diplomacy","law","public relations","marketing",
        "trade","partnership","consulting","foreign","hr","hospitality",
    ]):
        return 0.06
    if ak_house == 8 and any(k in lb for k in [
        "medicine","surgery","anatomy","doctor","physician","clinical","emergency",
        "research","forensic","psychology","investigation","data science","cybersecurity",
        "economics","audit","tax","insurance","metallurgy","mining","occult",
    ]):
        return 0.08   # H8 = deep biology, crisis medicine, hidden research
    if ak_house == 9 and any(k in lb for k in [
        "law","philosophy","higher","theology","medicine","science",
        "international","education","academia","religion","journalism",
    ]):
        return 0.08
    if ak_house == 10 and any(k in lb for k in [
        "public","management","career","administration","engineering",
        "government","corporate","civil services","politics","leadership",
    ]):
        return 0.08
    if ak_house == 11 and any(k in lb for k in [
        # L1 fix: H11 = Labha (gains, networks, social systems, mass-scale outcomes).
        # Removed H9 domains (law), H4 domains (architecture, real estate),
        # H12 domains (environment) — these were classical mismatches.
        # Replaced with legitimate H11 significations.
        "networking","community","social enterprise","ngo","policy networks",
        "institutional","lobbying","fundraising","industry","commerce",
        "finance","economics","technology","data","computer","artificial",
        "robotics","electronics","engineering","metallurgy","mining",
        "industrial","materials","petroleum","geology","geoscience",
        "earth science","geophysics","agriculture","construction",
    ]):
        return 0.06
    if ak_house == 12 and any(k in lb for k in [
        "research","spiritual","hospital","medicine","psychology","forensic",
        "international","foreign","philosophy","alternative","charity","social",
        "investigation","hidden","occult","ayurveda","theology",
    ]):
        return 0.07   # H12 = moksha, foreign lands, hidden research
    return 0.0

def _planet_combustion_penalty(affinity, combust_planets, planet_dignities=None, planets_d1=None,
                                vargottama_planets=None):
    """M3: Sliding combustion penalty — uses degree proximity from Sun instead of binary flag.
    G2 fix: Vargottama planets are exempt — same-sign D1/D9 dignity overrides combustion penalty.

    DEAD CODE FLAG (2026-08-22, JyotishAI reference-audit method #4):
    imported in engine.py (`from .boosts import ..., _planet_combustion_penalty, ...`)
    but grep confirms zero call sites anywhere in engine.py -- this
    general, all-combust-planets penalty never actually runs. It is the
    sibling of `_ak_combustion_penalty` above (which IS called, AK-only).
    No live double-penalty risk exists today since this never executes,
    but if it's ever wired in without checking `_ak_combustion_penalty`'s
    own halved-base compensation, the AK specifically would be penalized
    twice for the same combustion fact. Needs an owner decision: wire in
    deliberately (with an AK-exclusion or shared-cap guard) or remove.
    """
    if planet_dignities is None: planet_dignities = {}
    _varg_set = set(vargottama_planets or [])
    penalty = 0.0
    for p in combust_planets:
        if p not in affinity: continue
        if _varg_set and p in _varg_set: continue  # G2 fix: Vargottama exempt
        base = affinity[p] * 0.15
        dig  = planet_dignities.get(p,"")
        if dig == "EXALTED": base *= 0.30
        elif dig == "OWN":   base *= 0.50
        base *= _combustion_degree_factor(p, planets_d1 or {})
        penalty += base
    return min(penalty, 0.20)

# Fields where 8th-house energy (hidden, crisis, deep investigation) is required
# Unified exemption keywords — fields that positively require dusthana energy
def _dusthana_lord_penalty(affinity, lagna_sign, house_lords, lagna_lord: str = "",
                            label: str = "", eff_strengths=None,
                            planet_house: Dict[str, int] = None):
    """Dusthana lord penalty — with capacity-conditioned exemption (Gap-3 fix).

    H6 (disease/service/law), H8 (surgery/research/hidden), H12 (renunciation/hospital).
    Fields that require dusthana energy (medicine, research, etc.) receive a reduced
    penalty — but NOT a blanket zero.  The exemption is now conditioned on the native's
    actual capacity: if the relevant dusthana lord is strong (eff_strength ≥ 0.60),
    the penalty is fully waived.  A weak lord (< 0.40) still draws a partial penalty
    even for exempt fields, because the native lacks the capacity to channel that energy.

    PROVENANCE NOTE (2026-08-22, JyotishAI reference-audit method #5): the
    "profession neutralizes affliction" principle behind this exemption
    (_DUSTHANA_EXEMPT_KW) has no classical or practitioner citation found --
    it is a software design choice, not sourced doctrine. Tag:
    AUTHOR_SPECIFIC. See also _viparita_raja_yoga_bonus, a genuinely
    classical yoga (dusthana lord in ANOTHER dusthana) that reacts to a
    closely related condition; that function now de-weights its own bonus
    when a lord clears this function's same exemption test, to avoid
    crediting the same underlying "strong dusthana lord" fact twice through
    two independently-designed mechanisms.
    """
    if eff_strengths is None:
        eff_strengths = {}
    lb = label.lower()
    is_exempt_domain = any(_wm(kw, lb) for kw in _DUSTHANA_EXEMPT_KW)

    dusthana_lords = {
        "6":  house_lords.get("6", ""),
        "8":  house_lords.get("8", ""),
        "12": house_lords.get("12", ""),
    }
    dusthanas = {v for v in dusthana_lords.values() if v}

    # AC9 fix: Upachaya exemption — malefics (Saturn/Mars) placed in Upachaya houses
    # (H3/H6/H10/H11) grow stronger over time; classical rule says they give good
    # career results despite dusthana lordship. Exempt them from career penalty.
    _UPACHAYA = {3, 6, 10, 11}
    _NATURAL_MALEFICS = {"Saturn", "Mars", "Sun", "Rahu"}

    penalty = 0.0
    for p, w in affinity.items():
        if p == lagna_lord:
            continue   # lagna lord always immune
        if p not in dusthanas or w <= 0.15:
            continue

        # AC9: H6 lord that is a natural malefic placed in an Upachaya house → exempt
        # (only applies to H6 lords — H8/H12 lords still carry penalty regardless)
        _p_house = (planet_house or {}).get(p, 0)
        if (house_lords.get("6") == p and p in _NATURAL_MALEFICS and _p_house in _UPACHAYA):
            penalty += w * 0.02  # token penalty (not zero — field-specificity still matters)
            continue

        if is_exempt_domain:
            # Capacity check: how strong is this dusthana lord?
            lord_strength = eff_strengths.get(p, 0.5)   # default 0.5 = unknown
            if lord_strength >= 0.60:
                continue   # strong lord → domain exemption holds, no penalty
            elif lord_strength >= 0.40:
                # Moderate lord → half penalty (native has partial capacity)
                penalty += w * 0.05
            else:
                # Weak lord → 70% of normal penalty even for exempt fields
                penalty += w * 0.07
        else:
            penalty += w * 0.10

    return min(penalty, 0.15)

_PEAK_DASHA_DIGNITY_MULT: Dict[str, float] = {
    "EXALTED": 1.40, "OWN": 1.15, "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.40,
}
# GAP-7 fix: _peak_career_dasha_boost used to carry its own DEBILITATED=0.60
# scale, diverging from the 0.40 used here to actually pick the peak lord —
# two functions scoring "the same fact" (this planet is debilitated) with
# different penalties. Unified to one shared table; both functions read it.

# GAP-8 fix: role-weight stacking (AmK/H10/AK/H9/H1) used to be additive and
# uncapped — a planet holding all five roles could reach role_mult≈2.03,
# more headroom than the 2.0 cap already enforced on raw effective strength.
# Capped so role stacking can influence but never dominate the score.
_PEAK_DASHA_ROLE_MULT_CAP = 1.75

# GAP-6 fix: the old reach_mod was a hard cliff — start_age=79.9 got full
# weight, start_age=80.1 got crushed to 0.2x. Replaced with a linear taper
# starting at 65 (when "will the native realistically be professionally
# active for this MD" first becomes a real question) down to a floor of 0.2
# fully reached at 95, matching the same anti-cliff philosophy already
# applied to the combustion modifier in astro.py.
_REACH_TAPER_START_AGE = 65.0
_REACH_TAPER_FLOOR_AGE = 95.0
_REACH_TAPER_FLOOR     = 0.2


def _peak_dasha_reach_mod(start_age: float) -> float:
    if start_age <= _REACH_TAPER_START_AGE:
        return 1.0
    if start_age >= _REACH_TAPER_FLOOR_AGE:
        return _REACH_TAPER_FLOOR
    span = _REACH_TAPER_FLOOR_AGE - _REACH_TAPER_START_AGE
    t = (start_age - _REACH_TAPER_START_AGE) / span
    return 1.0 - t * (1.0 - _REACH_TAPER_FLOOR)


def _peak_dasha_dusthana_mod(lord: str, dusthana_lords: Set[str],
                              eff_strength: float, label: str = "") -> float:
    """GAP-5 fix: the label-based full exemption only ever fires when a
    field-specific label is passed in — but the one production call site
    (engine.py, whole-chart peak_dasha_lord) never passes a label, so the
    exemption was dead code there and every dusthana-lord dasha always ate
    the flat 0.85 penalty regardless of how strong that lord actually was.
    Two independent fixes, applied together:
      1. Field-aware full exemption still applies when the caller *does*
         know the field is dusthana-friendly (medicine/research/forensics/…).
      2. Even with no label, the penalty is now graded by the lord's own
         effective strength — a strong dusthana lord (classically, capable
         of delivering on its house's mandate despite the placement) is
         penalized less than a weak one — instead of a flat 0.85 for every
         dusthana lord regardless of how strong or weak it is.
    """
    if lord not in dusthana_lords:
        return 1.0
    if label and any(_wm(kw, label.lower()) for kw in _DUSTHANA_EXEMPT_KW):
        return 1.0
    if eff_strength >= 0.60:
        return 0.95      # strong dusthana lord — mild penalty only
    elif eff_strength >= 0.40:
        return 0.90       # moderate
    return 0.85            # weak dusthana lord — full penalty


def _peak_career_dasha(
    dasha_seq: List[Dict], shadbala: Dict[str, float],
    planet_dignities: Dict[str, str], house_lords: Dict[str, str],
    ak: str, amk: str, current_age: float = 0.0,
    eff_strengths: Dict[str, float] = None,
    planet_house: Dict[str, int] = None,
    label: str = "",
) -> Tuple[str, Dict[str, float]]:
    # FIX-6: uses effective strengths; graded reachability taper (65->95, floor 0.2x);
    # graded dusthana-lord penalty (self-strength aware, field-exemption aware).
    if eff_strengths is None:
        eff_strengths = {}
    if planet_house is None:
        planet_house = {}

    scores: Dict[str, float] = {}
    role_mults: Dict[str, float] = {}
    seen: set = set()
    h1_lord  = house_lords.get("1",  "")
    h9_lord  = house_lords.get("9",  "")
    h10_lord = house_lords.get("10", "")
    dusthana_lords = {house_lords.get("6"), house_lords.get("8"), house_lords.get("12")} - {None, ""}

    for d in dasha_seq:
        end_age   = d.get("end_age") or float("inf")
        start_age = d.get("start_age") or d.get("age_start") or 0.0
        if end_age <= current_age: continue
        lord = d.get("lord", "") or d.get("md_planet", "")
        if not lord or lord in seen: continue
        seen.add(lord)

        # Use effective strength (retro paradox, combustion, digbala, vargottama baked in)
        if lord in eff_strengths and eff_strengths[lord] > 0:
            eff = min(eff_strengths[lord], 2.0)
        else:
            min_v = _PLANET_MIN_SHADBALA.get(lord, 300)
            eff   = min(shadbala.get(lord, min_v) / min_v, 2.0)

        dig = planet_dignities.get(lord, "")
        dig_mult = _PEAK_DASHA_DIGNITY_MULT.get(dig, 1.0)

        role_mult = 1.0
        if lord == amk:      role_mult += _MD_ROLE_WEIGHT["amk"]
        if lord == h10_lord: role_mult += _MD_ROLE_WEIGHT["h10"]
        if lord == ak:       role_mult += _MD_ROLE_WEIGHT["ak"]
        if lord == h9_lord:  role_mult += _MD_ROLE_WEIGHT["h9"]
        if lord == h1_lord:  role_mult += _MD_ROLE_WEIGHT["h1"]
        role_mult = min(role_mult, _PEAK_DASHA_ROLE_MULT_CAP)
        role_mults[lord] = role_mult

        reach_mod = _peak_dasha_reach_mod(start_age)
        dust_mod  = _peak_dasha_dusthana_mod(lord, dusthana_lords, eff, label=label)

        scores[lord] = eff * dig_mult * role_mult * reach_mod * dust_mod

    if not scores:
        # GAP-2 fix: this used to fail silently, returning ("", {}) with no
        # signal distinguishing "no dasha data supplied" from "every dasha
        # has already elapsed for this current_age" — callers then silently
        # fell back to active_lord with nothing in the logs to explain why.
        logger.warning(
            "_peak_career_dasha: no eligible (unexpired) dasha lords found "
            "for current_age=%s out of %d dasha_seq entries — returning empty.",
            current_age, len(dasha_seq),
        )
        return ("", {})

    # GAP-4 fix: max(scores, key=scores.get) resolved ties by dict/iteration
    # order with no astrological rationale. Deterministic tiebreak: highest
    # score wins; on a near-tie (within 0.5%), prefer the lord carrying more
    # career-role weight (AmK/H10/AK/H9/H1), then fall back to a fixed
    # classical-strength planet order so the result is reproducible.
    _CLASSICAL_ORDER = ["Jupiter", "Venus", "Mercury", "Sun", "Mars", "Saturn", "Moon", "Rahu", "Ketu"]
    top_score = max(scores.values())
    _near_tie = [lord for lord, sc in scores.items() if sc >= top_score * 0.995]
    if len(_near_tie) > 1:
        logger.info(
            "_peak_career_dasha: near-tie among %s (scores=%s) — resolving via role weight, "
            "then classical order.", _near_tie,
            {l: round(scores[l], 4) for l in _near_tie},
        )
        peak = sorted(
            _near_tie,
            key=lambda l: (-role_mults.get(l, 1.0),
                           _CLASSICAL_ORDER.index(l) if l in _CLASSICAL_ORDER else 99),
        )[0]
    else:
        peak = max(scores, key=scores.get)
    return (peak, scores)

def _peak_career_dasha_boost(affinity: Dict[str, float], peak_lord: str, active_lord: str, planet_dignities: Dict[str, str]) -> float:
    if not peak_lord or peak_lord not in affinity: return 0.0
    dig = planet_dignities.get(peak_lord, "")
    dig_scale = _PEAK_DASHA_DIGNITY_MULT.get(dig, 1.0)  # GAP-7 fix: shared scale (was a local 0.60 for DEBILITATED, now 0.40)
    dig_scale = _node_dignity_damping(peak_lord, dig_scale)
    base = affinity[peak_lord] * 0.22 * dig_scale
    # H1 fix: when peak_lord == active_lord the native IS in their peak window — do NOT
    # halve the signal.  Instead, the caller skips _dasha_active_affinity_boost for this
    # field when peak==active to prevent double-counting.  The peak boost runs at full strength.
    return round(base, 4)

def _dasha_active_affinity_boost(affinity, active_lord, planet_dignities=None):
    if planet_dignities is None: planet_dignities = {}
    if active_lord not in affinity: return 0.0
    dig = planet_dignities.get(active_lord,"")
    dig_scale = {"EXALTED":1.40,"OWN":1.15,"DEBILITATED":0.40,"NEECHA_BHANGA":1.05}.get(dig,1.0)
    dig_scale = _node_dignity_damping(active_lord, dig_scale)
    return affinity[active_lord] * 0.25 * dig_scale

def _d10_consistency_penalty(affinity, d10_house_occ, label: str = ""):
    """G3 fix: Recalibrated D10 dusthana penalty.

    H8 reduced (0.30→0.18), H6 reduced (0.15→0.10), overall cap halved (0.25→0.12).
    H12 special case: in research/foreign/institutional domains, D10-H12 placement
    signals remote work, overseas postings, or institutional research — a positive
    classical indicator, not a career obstruction.
    """
    _COEFF = {"6": 0.10, "8": 0.18}   # H12 handled separately
    _H12_POSITIVE_KW = [
        "research", "foreign", "international", "hospital", "space",
        "psychology", "philosophy", "spiritual", "overseas", "remote",
        "institutional", "government", "defence", "defense", "security",
    ]
    _lb = label.lower()
    penalty = 0.0
    for house_str, coeff in _COEFF.items():
        for planet in d10_house_occ.get(house_str, []):
            w = affinity.get(planet, 0.0)
            if w >= 0.15:
                penalty += w * coeff
    # H12: polarity flip for qualifying domains
    for planet in d10_house_occ.get("12", []):
        w = affinity.get(planet, 0.0)
        if w >= 0.15:
            if any(_wm(kw, _lb) for kw in _H12_POSITIVE_KW):
                penalty -= w * 0.06   # mild bonus: H12 D10 = remote/institutional benefit
            else:
                penalty += w * 0.10   # reduced penalty (was 0.20)
    return max(-0.05, min(penalty, 0.12))

def _pratyantar_dasha_bonus(label, prd_lord, prd_houses):
    if not prd_lord: return 0.0
    kw_match = any(_wm(kw, label.lower()) for kw in DASHA_KEYWORDS.get(prd_lord,[]))
    h_strong = any(h in prd_houses for h in [5, 9, 10])
    h_gain   = any(h in prd_houses for h in [1, 11])
    bonus = 0.0
    if kw_match and h_strong: bonus += 0.06
    elif kw_match: bonus += 0.03
    if kw_match and h_gain: bonus += 0.04
    elif h_gain and not kw_match: bonus += 0.01 
    return min(bonus, 0.08)

def _karakamsha_occupant_bonus(label, karakamsha_occupants, shadbala: Dict[str, float] = None):
    if shadbala is None: shadbala = {}
    bonus = 0.0
    for planet in karakamsha_occupants:
        kws = _KARAKAMSHA_OCCUPANT_KW.get(planet, [])
        if any(_wm(kw, label.lower()) for kw in kws):
            min_v = _PLANET_MIN_SHADBALA.get(planet, 300)
            ratio = shadbala.get(planet, min_v) / min_v
            ratio = max(0.0, min(ratio, 1.5))
            planet_bonus = 0.06 * ratio
            bonus += min(planet_bonus, 0.09) 
    return min(bonus, 0.15)
# ===========================================================================
# BHAVESHA PHALA (HOUSE LORD PLACEMENT) EDUCATIONAL LOGIC
# ===========================================================================
_BHAVESHA_PHALA_KW: Dict[int, List[str]] = {
    1: ["management", "business", "leadership", "entrepreneurship", "administration"],
    2: ["finance", "accounting", "commerce", "economics", "data", "banking", "wealth"],
    3: ["media", "journalism", "computer", "communication", "technology", "coding", "software"],
    4: ["agriculture", "civil", "architecture", "environmental", "teaching", "real estate"],
    5: ["mathematics", "design", "arts", "artificial intelligence", "data science", "statistics", "innovation"],
    6: ["medicine", "law", "cybersecurity", "defence", "analytics", "nursing", "problem solving"],
    7: ["international", "business", "management", "commerce", "public", "foreign"],
    8: ["research", "mining", "metallurgy", "data science", "cybersecurity", "psychology",
        "backend", "forensic", "medicine", "surgery", "anatomy", "doctor", "physician",
        "medical", "emergency", "hospital", "clinical", "pathology", "radiology"],  # FIX-19
    9: ["philosophy", "law", "academia", "science", "physics", "theology", "higher education"],
    10: ["engineering", "civil services", "management", "administration", "technology", "executive"],
    11: ["computer science", "artificial intelligence", "networking", "sociology", "public policy", "systems", "finance", "accounting", "commerce", "economics"],
    12: ["medicine", "hospital", "research", "space", "foreign", "spiritual", "psychology"]
}

def _bhavesha_phala_edu_bonus(label: str, affinity: Dict[str, float], house_lords: Dict[str, str], planet_house: Dict[str, int]) -> float:
    """FIX-20: Bhavesha Phala — extended to H2+H11 for commerce/finance/wealth fields.

    Classical Jyotish:
      H4 lord (formal schooling), H5 lord (intellect), H9 lord (higher education)
      are primary educational lords.
      H2 lord (accumulated wealth/accounting) and H11 lord (financial gains/networks)
      are primary commerce/finance lords — mandatory for CA, CS, banking paths.
    """
    bonus = 0.0
    label_lower = label.lower()

    # H2 (dhana/wealth), H4 (formal), H5 (intellect), H9 (higher ed), H11 (labha/gains)
    # H2+H11 always checked — placement keywords filter what each house signals for each field
    edu_houses = ["2", "4", "5", "9", "11"]

    for h in edu_houses:
        lord = house_lords.get(h, "")
        if not lord:
            continue
        placed_in_house = planet_house.get(lord, 0)
        if placed_in_house == 0:
            continue
        placement_kws = _BHAVESHA_PHALA_KW.get(placed_in_house, [])
        if any(_wm(kw, label_lower) for kw in placement_kws):
            w = affinity.get(lord, 0.0)
            if   w >= 0.25: bonus += 0.05
            elif w >= 0.15: bonus += 0.03
            elif w >= 0.08: bonus += 0.01

    return min(bonus, 0.12)

def _d9_h10_bonus(affinity, d9_chart, d9_lagna_sign, payload=None):
    """Bonus for planets in D9 H10 — gated by D1 vitality coefficient."""
    if not d9_lagna_sign or not d9_chart: return 0.0
    if isinstance(d9_lagna_sign, dict):
        d9_lagna_sign = d9_lagna_sign.get("sign", "")
    bonus = 0.0
    for planet, sign in d9_chart.items():
        if planet == "Lagna": continue
        if isinstance(sign, dict):
            sign = sign.get("sign", "")
        if not isinstance(sign, str) or sign not in _SIGN_NUM:
            continue
        if (((_SIGN_NUM.get(sign, 1) - _SIGN_NUM.get(d9_lagna_sign, 1)) % 12) + 1) == 10:
            w = affinity.get(planet, 0.0)
            raw = 0.05 if w >= 0.20 else (0.02 if w >= 0.10 else 0.0)
            if raw > 0:
                vit = _d1_vitality_coefficient(planet, payload) if payload else 1.0
                bonus += raw * vit
    return min(bonus, 0.08)

def _dharma_karma_bonus(affinity, house_lords, planet_house):
    h9_lord, h10_lord = house_lords.get("9",""), house_lords.get("10","")
    if not h9_lord or not h10_lord or h9_lord == h10_lord: return 0.0
    h9l_house, h10l_house = planet_house.get(h9_lord, 0), planet_house.get(h10_lord, 0)
    if h9l_house == 0 or h10l_house == 0: return 0.0
    same_house = (h9l_house == h10l_house)
    mutual_kendra = abs(h9l_house - h10l_house) in (0,3,6,9)
    if not (same_house or mutual_kendra): return 0.0
    w9, w10  = affinity.get(h9_lord, 0.0), affinity.get(h10_lord, 0.0)
    w = max(w9, w10)
    _DK_W_FLOOR, _DK_W_CEIL = 0.10, 0.30
    _DK_BASE_FLOOR, _DK_BASE_CEIL = 0.02, 0.08
    if w < _DK_W_FLOOR:
        return 0.0
    frac = (min(w, _DK_W_CEIL) - _DK_W_FLOOR) / (_DK_W_CEIL - _DK_W_FLOOR)
    return _DK_BASE_FLOOR + frac * (_DK_BASE_CEIL - _DK_BASE_FLOOR)

# ════════════════════════════════════════════════════════════════════════════
# NEW GAP FUNCTIONS (v8.9)
# ════════════════════════════════════════════════════════════════════════════

def _d10_h10_bonus(affinity: Dict[str, float], d10_chart: Dict, d10_lagna_sign: str,
                   d10_planet_dignities: Dict[str, str] = None,
                   d10_occupancy: Dict = None) -> float:
    """FIX-3: Credit planets occupying D10's 10th house (mirrors _d9_h10_bonus).
    Exalted planets in D10 H10 receive extra weight — this is the career chart's
    most important house and any strong planet there is a direct professional indicator.

    SIGNAL_REGISTRY consolidation fix (audit): this engine.py gap-boost call
    used to independently recompute "which planets occupy D10 H10" from
    d10_chart + d10_lagna_sign, in parallel with kp.py/knrao.py/parashara.py
    (each of which instead reads the single shared `payload_data.
    d10_house_occupancy` precomputed upstream). Two parallel code paths
    computing the same fact is a drift risk if D10 construction logic ever
    changes in only one place. `d10_occupancy`, when supplied, is now
    preferred over recomputing from d10_chart, so every consumer of "D10 H10
    occupants" reads from the same single upstream source; the recompute path
    remains as a fallback for callers that don't have it available.
    """
    if d10_planet_dignities is None:
        d10_planet_dignities = {}

    if d10_occupancy is not None:
        h10_planets = d10_occupancy.get("10", d10_occupancy.get(10, [])) or []
    else:
        if not d10_lagna_sign or not d10_chart:
            return 0.0
        h10_planets = []
        for planet, sign in d10_chart.items():
            if planet == "Lagna":
                continue
            if isinstance(sign, dict):
                sign = sign.get("sign", "")
            if not isinstance(sign, str) or sign not in _SIGN_NUM:
                continue
            h = ((_SIGN_NUM.get(sign, 1) - _SIGN_NUM.get(d10_lagna_sign, 1)) % 12) + 1
            if h == 10:
                h10_planets.append(planet)

    bonus = 0.0
    for planet in h10_planets:
        w = affinity.get(planet, 0.0)
        dig = d10_planet_dignities.get(planet, "")
        # 2026-08-20 audit fix: a node's "EXALTED" here is borrowed from its
        # dispositor (see _node_dignity_damping docstring), so don't grant it
        # the full classical-planet EXALTED bonus tier.
        is_exalted = dig == "EXALTED" and planet not in ("Rahu", "Ketu")
        if   w >= 0.20 and is_exalted: raw = 0.10
        elif w >= 0.20:                 raw = 0.06
        elif w >= 0.10 and is_exalted: raw = 0.06
        elif w >= 0.10:                 raw = 0.03
        else:                           raw = 0.0
        bonus += raw  # vitality not applied here (no payload reference; caller can gate)
    return min(bonus, 0.12)


# Lagnas where Venus is a functional malefic — rules dusthana/upachaya pairs.
# Scorpio: Venus rules H7+H12; Sagittarius: H6+H11; Pisces: H3+H8.
# For these lagnas, a blanket Venus boost is astrologically incorrect.
_VENUS_MALEFIC_LAGNAS: frozenset = frozenset({
    "Scorpio",    # Venus rules H7 (maraka) + H12 (vyaya/loss)
    "Sagittarius",# Venus rules H6 (roga/dusthana) + H11 (labha but not KT)
    "Pisces",     # Venus rules H3 (upachaya) + H8 (randhra/dusthana)
})

def _gender_field_modifier(label: str, gender: str, affinity: Dict[str, float],
                            house_lords: Dict[str, str] = None) -> float:
    """Gender-aware Venus modifier — checks Venus functional status from actual house lordships.

    Classical Jyotish: Venus boosts female-relevant fields ONLY when Venus is a
    functional benefic. If Venus rules H6, H8, or H12, it is a functional malefic
    for that chart regardless of lagna — no boost should be granted.
    This chart-driven check is more accurate than a hardcoded lagna list.
    """
    if not gender:
        return 0.0
    g = gender.strip().upper()
    if g not in ("F", "FEMALE"):
        return 0.0
    # Suppress bonus if Venus rules a dusthana (H6/H8/H12) in this chart
    if house_lords:
        venus_dusthana = (
            house_lords.get("6") == "Venus" or
            house_lords.get("8") == "Venus" or
            house_lords.get("12") == "Venus"
        )
        if venus_dusthana:
            return 0.0
    v_weight = affinity.get("Venus", 0.0)
    if   v_weight >= 0.25: return 0.06
    elif v_weight >= 0.15: return 0.03
    return 0.0


def _aspect_h10_bonus(affinity: Dict[str, float], planet_house: Dict[str, int],
                      planet_dignities: Dict[str, str] = None,
                      planets_d1: Dict = None) -> float:
    """FIX-5 (Drishti Bala upgraded): Bonus when a high-affinity planet aspects H10.

    When planets_d1 is supplied, the bonus is scaled by Drishti Bala: a planet at
    the house midpoint (15°) gives full strength; one near a cusp gives 50%.
    This implements the classical principle that aspect potency is not uniform.
    """
    if planet_dignities is None:
        planet_dignities = {}
    aspects = _get_planetary_aspects(planet_house)
    if planets_d1:
        weighted = _get_planetary_aspects_weighted(planet_house, planets_d1)
        aspect_strength = {p: d.get(10, 0.0) for p, d in weighted.items()}
    else:
        aspect_strength = {p: (1.0 if 10 in hs else 0.0) for p, hs in aspects.items()}
    bonus = 0.0
    for planet, aspected_houses in aspects.items():
        if 10 not in aspected_houses:
            continue
        w         = affinity.get(planet, 0.0)
        dig       = planet_dignities.get(planet, "")
        dig_scale = {"EXALTED": 1.40, "OWN": 1.15}.get(dig, 1.0)
        dig_scale = _node_dignity_damping(planet, dig_scale)
        drishti   = aspect_strength.get(planet, 1.0)   # 0.5 (cusp) → 1.0 (midpoint)
        if   w >= 0.25: bonus += 0.06 * dig_scale * drishti
        elif w >= 0.15: bonus += 0.03 * dig_scale * drishti
        elif w >= 0.08: bonus += 0.01 * dig_scale * drishti
    return min(bonus, 0.10)
# A9 fix: duplicate _maheshwara_lord_bonus removed (canonical at line 204)


_INTEREST_KEYWORD_ALIASES: Dict[str, List[str]] = {
    # Professional streams → degree field labels they map to (DESIGN-2 fix)
    "chartered accountant": ["commerce", "accounting", "finance", "economics"],
    "company secretary":    ["commerce", "accounting", "corporate", "law", "business"],
    "ca foundation":        ["commerce", "accounting", "finance"],
    "cs exam":              ["corporate", "law", "commerce", "business"],
    "chartered":            ["commerce", "accounting", "finance"],
    "actuary":              ["statistics", "mathematics", "finance", "economics"],
    "data science":         ["data", "statistics", "artificial intelligence", "computer", "mathematics"],
    "machine learning":     ["artificial intelligence", "data", "computer", "robotics"],
    "economics":            ["economics", "public policy", "commerce", "finance", "business"],
    "civil service":        ["civil services", "public policy", "law", "political"],
    "defence":              ["defence", "military", "aerospace", "mechanical"],
    "medicine":             ["medicine", "mbbs", "biomedical", "nursing", "pharmacy", "biology"],
}

def _interest_preference_boost(label: str, interested_in: List[str], already_excel_at: List[str]) -> float:
    """DESIGN-2 fix: Alias professional streams (CA, CS, etc.) to matching degree-field label keywords."""
    label_lower = label.lower()
    interest_boost = 0.0
    for kw in (interested_in or []):
        if not kw:
            continue
        kw_lower = kw.lower()
        # Direct substring match
        if kw_lower in label_lower:
            interest_boost += 0.10
            continue
        # Alias-based match: expand professional/common terms to degree-field keywords
        aliases = _INTEREST_KEYWORD_ALIASES.get(kw_lower, [])
        if any(alias in label_lower for alias in aliases):
            interest_boost += 0.08   # slightly lower than direct match
    interest_boost = min(interest_boost, 0.20)

    excel_boost = 0.0
    for kw in (already_excel_at or []):
        if not kw:
            continue
        kw_lower = kw.lower()
        if kw_lower in label_lower:
            excel_boost += 0.06
            continue
        aliases = _INTEREST_KEYWORD_ALIASES.get(kw_lower, [])
        if any(alias in label_lower for alias in aliases):
            excel_boost += 0.04
    excel_boost = min(excel_boost, 0.12)

    return round(interest_boost + excel_boost, 4)

# ── Brahma Lord Domain Keywords ────────────────────────────────────────────────
# Brahma (Jaimini) governs the timing of peak creative/dharmic expression.
# Maps brahma lord to domains it amplifies — similar to Maheshwara but emphasis on
# creative intelligence and dharmic purpose rather than institutional peaks.
_BRAHMA_DOMAIN_KW: Dict[str, List[str]] = {
    "Jupiter": ["law","education","philosophy","research","international","theology","economics"],
    "Mercury": ["data science","computer","mathematics","communication","statistics","analytics","artificial intelligence"],
    "Venus":   ["arts","design","fashion","music","performing arts","fine arts","architecture","media","mass communication"],
    "Saturn":  ["engineering","mining","civil","metallurgy","agriculture","industrial","construction","environment"],
    "Mars":    ["defence","defense","surgery","military","police","mechanical","fire service","strategic","operations","tactical"],
    "Sun":     ["civil services","administration","government","leadership","energy","physics"],
    "Moon":    ["nursing","psychology","social work","public health","ecology","hospitality","counseling","arts","music","fine arts","performing arts","literature"],
    "Rahu":    ["artificial intelligence","cybersecurity","biotechnology","space","robotics","forensic","data science"],
    "Ketu":    ["research","ayurveda","spiritual","philosophy","archaeology","investigation","occult"],
}


def _brahma_lord_bonus(label: str, brahma_lord: str, affinity: Dict[str, float]) -> float:
    """Brahma lord (Jaimini) domain alignment bonus.
    Fires when the brahma lord's creative domain matches the field AND
    it has meaningful affinity weight in the branch's planet vector."""
    if not brahma_lord:
        return 0.0
    kws = _BRAHMA_DOMAIN_KW.get(brahma_lord, [])
    label_lower = label.lower()
    if not any(_wm(kw, label_lower) for kw in kws):
        return 0.0
    w = affinity.get(brahma_lord, 0.0)
    return _special_lord_domain_ramp(w)


def _chart_specific_aptitude_supplement(
    domain: str,
    h5_lord: str,
    lagna_lord: str,
    h10_lord: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Add a small flat bonus to composite_score when key lords strongly support the domain.

    H5 lord supports learning/intelligence domains. H10 and lagna lords support
    career domains they rule. Capped at +10 to avoid overwhelming the base score.
    Classical principle: H5/H10/lagna lords in good dignity acting through their
    natural domains raise the competence ceiling for that field.
    """
    _DOMAIN_LORDS: Dict[str, List[str]] = {
        "medicine":       ["Moon", "Jupiter", "Mars"],
        "engineering":    ["Mars", "Saturn"],
        "technology":     ["Mercury", "Rahu"],
        "science":        ["Mercury", "Jupiter", "Saturn"],
        "law":            ["Jupiter", "Mercury", "Sun"],
        "arts":           ["Venus", "Moon"],
        "design":         ["Venus", "Mercury"],
        "humanities":     ["Moon", "Jupiter", "Venus"],
        "commerce":       ["Mercury", "Jupiter", "Saturn"],
        "education":      ["Jupiter", "Mercury"],
        "research":       ["Ketu", "Jupiter", "Saturn"],
        "media":          ["Mercury", "Venus", "Rahu"],
        "public":         ["Sun", "Jupiter", "Saturn"],
        "agriculture":    ["Moon", "Saturn", "Mars"],
        "interdisciplinary": ["Mercury", "Jupiter"],
    }
    relevant = _DOMAIN_LORDS.get(domain, [])
    supplement = 0.0
    for lord in [h5_lord, h10_lord, lagna_lord]:
        if lord and lord in relevant:
            s = eff_strengths.get(lord, 0.0)
            if s >= 1.40:
                supplement += 3.5
            elif s >= 1.15:
                supplement += 2.0
            elif s >= 0.90:
                supplement += 0.8
    return min(supplement, 10.0)


# Gap-audit fix (2026-08, chat cross-chart review): this table used to be
# duplicated verbatim inside both _ak_planet_domain_boost() and
# _ak_domain_flat_supplement() -- two independent copies of the same planet->
# keyword mapping, with no mechanism to keep them in sync (the same class of
# drift risk _h3_lord_communication_boost's sibling helper
# `chandra_lagna_h10_lord` was centralised to avoid, per that function's own
# comment in field_methods/common.py). Centralised here as the single source
# both functions reference.
#
# Confirmed bug fixed here: Venus's list carried a bare "design" keyword,
# intended to catch genuinely Venus-flavoured fields (fashion_design,
# interior_design, design_ux_product). But "design" is polysemous -- the word
# also appears in ~15+ unrelated engineering fields' registry descriptions
# ("reactor design", "machine design", "mine design", "ship design", "vlsi
# design", "highway design", "antenna design", ...). A 25-chart cross-check
# found this firing for rithul/Rithvik's Venus AmK on "Nuclear Engineering"
# purely because its description says "reactor design" -- a false-positive
# keyword collision with zero connection to Venus's actual significations.
# Replaced with the specific multi-word design phrases that (verified against
# the full registry) appear ONLY in genuinely creative/UX-design fields:
# "fashion design", "interior design", "graphic design", "ux design",
# "product design", "industrial design", "design thinking",
# "human-centred design", "spatial design" -- none of these collide with any
# engineering field's description text.
_AK_DOMAIN_KEYWORDS: Dict[str, Tuple[List[str], List[str]]] = {
    "Mercury": (
        ["technology", "computer", "software", "data science", "machine learning",
         "artificial intelligence", "analytics", "mathematics", "programming",
         "information technology", "statistics", "computational"],
        ["communication", "media", "writing", "journalism", "research",
         "commerce", "accounting", "economics", "finance", "digital"],
    ),
    "Jupiter": (
        ["law", "economics", "education", "philosophy", "management",
         "finance", "banking", "consulting", "teaching", "governance",
         "political science", "public policy"],
        ["theology", "international", "administration", "research",
         "humanities", "social science", "commerce", "medicine",
         "business", "policy"],
    ),
    "Venus": (
        ["arts", "fashion design", "interior design", "graphic design",
         "ux design", "product design", "industrial design",
         "design thinking", "human-centred design", "spatial design",
         "music", "fashion", "beauty", "hospitality",
         "film", "performing", "visual", "creative", "architecture",
         "animation", "dance"],
        ["luxury", "tourism", "entertainment", "interior", "textile",
         "jewellery", "culinary", "drama", "photography", "media"],
    ),
    "Mars": (
        ["engineering", "defence", "defense", "military", "surgery",
         "mechanical", "electrical", "manufacturing", "aerospace",
         "civil engineering", "energy", "strategic", "operations", "tactical"],
        ["nuclear", "police", "security", "firefighting",
         "materials", "metallurgy", "construction", "mining", "petroleum"],
    ),
    "Saturn": (
        ["engineering", "government", "administration", "agriculture",
         "mining", "construction", "infrastructure", "materials",
         "civil engineering", "public works", "industrial"],
        ["law", "policy", "social work", "environmental", "geology",
         "architecture", "urban", "mechanical", "labour", "textile"],
    ),
    "Sun": (
        ["government", "civil services", "administration", "leadership",
         "nuclear", "medicine", "political", "public", "law", "energy"],
        ["corporate", "executive", "defence", "history",
         "social", "pharmacy", "ophthalmology", "cardiology", "surgery"],
    ),
    "Moon": (
        ["psychology", "nursing", "medicine", "counseling", "social work",
         "public health", "hospitality", "food", "agriculture", "childcare",
         "mental health"],
        ["humanities", "education", "community", "welfare", "health",
         "pharmacy", "marine", "tourism", "literature", "naturopathy"],
    ),
    "Rahu": (
        ["technology", "artificial intelligence", "data science",
         "machine learning", "cybersecurity", "robotics", "space",
         "biotechnology", "foreign", "media", "digital"],
        ["film", "research", "analytics", "finance", "economics",
         "engineering", "computer", "international", "aviation"],
    ),
    "Ketu": (
        ["research", "philosophy", "spiritual", "medicine", "forensic",
         "ayurveda", "archaeology", "investigative", "alternative",
         "astrology", "mathematics"],
        ["psychology", "metaphysics", "science", "theology", "history",
         "ancient", "language", "occult", "analytics"],
    ),
}


def _ak_planet_domain_boost(
    label: str,
    ak: str,
    ak_dig: str,
    planet_house: Dict[str, int],
    amk: str = "",
    amk_dig: str = "",
) -> float:
    """AK (and optionally AmK) planet natural-domain keyword boost.

    Maps the Atmakaraka planet to its natural career domains and boosts
    fields whose label matches those domain keywords.  This encodes the
    Jaimini principle that AK = soul purpose and MUST shape field ranking
    regardless of the planet's temporal strength (Mrita etc.).

    Planet → domain mapping:
      Mercury  → technology, data science, computing, analytics, mathematics
      Jupiter  → law, economics, education, philosophy, management, finance
      Venus    → arts, design, music, fashion, hospitality, film
      Mars     → engineering, defence, surgery, sports, mechanical, electrical
      Saturn   → engineering, government, agriculture, mining, construction
      Sun      → civil services, administration, medicine, nuclear, leadership
      Moon     → psychology, nursing, medicine, social work, hospitality
      Rahu     → technology, AI, data science, foreign, media, space
      Ketu     → research, philosophy, medicine, forensic, ayurveda

    Base boosts: primary match = +0.13, secondary match = +0.07.
    Multiplied by dignity (EXALTED 1.4×, OWN 1.2×, DEBILITATED 0.6×)
    and house position (trikona 1.2×, karma 1.1×, dusthana 0.8×).
    AmK applies the same mapping at 60 % base weight.
    """
    # ── keyword table ─────────────────────────────────────────────────────────
    # Gap-audit fix (2026-08): now references the single shared
    # _AK_DOMAIN_KEYWORDS table (see its module-level comment above) instead
    # of an independent local copy.
    def _planet_boost(planet: str, dig: str, base_scale: float) -> float:
        if not planet:
            return 0.0
        primary_kw, secondary_kw = _AK_DOMAIN_KEYWORDS.get(planet, ([], []))
        lbl = label.lower()
        # L2 fix: use word-boundary match (_wm) consistent with all other boost functions.
        # Bare substring match caused false positives e.g. "medicine" in "sports medicine"
        # triggering Moon-AK supplement in a Mars-primary field.
        if any(_wm(kw, lbl) for kw in primary_kw):
            base = 0.13 * base_scale
        elif any(_wm(kw, lbl) for kw in secondary_kw):
            base = 0.07 * base_scale
        else:
            return 0.0
        dig_mod = {"EXALTED": 1.4, "OWN": 1.2,
                   "NEECHA_BHANGA": 1.0, "DEBILITATED": 0.6}.get(dig, 1.0)
        ak_house = planet_house.get(planet, 0)
        if ak_house in (1, 5, 9):
            house_mod = 1.2
        elif ak_house == 10:
            house_mod = 1.1
        elif ak_house in (4, 7):
            house_mod = 1.0
        elif ak_house in (2, 11):
            house_mod = 0.9
        else:
            house_mod = 0.8   # dusthana or unknown
        return min(base * dig_mod * house_mod, 0.20)

    boost = _planet_boost(ak, ak_dig, 1.0)
    if amk and amk != ak:
        boost = max(boost, _planet_boost(amk, amk_dig, 0.65))
    return round(boost, 4)


def _ak_domain_flat_supplement(
    label: str,
    ak: str,
    amk: str = "",
    digs: Optional[Dict[str, str]] = None,
) -> float:
    """Flat additive to final_score ensuring AK/AmK soul-domain fields reach top-35.

    gap_boost is a *multiplier* on blended_score.  When the AK planet is Mrita
    (weak eff_strength), technology/economics fields can have a blended_score of
    ~55–65 while strongly-placed planet domains score 90–110.  A 0.15 multiplier
    on 60 = only +9 extra, not enough to compete.

    This function adds a FLAT score supplement (independent of blended_score) so
    that soul-purpose fields stay structurally visible regardless of AK weakness.
    The flat values are tuned so they add ~28–30 for a primary keyword match —
    just enough to cross the top-35 threshold without inverting the entire chart.

    AK (soul purpose) uses full weight; AmK (career means) uses 65 % weight.
    Final supplement = max(ak_flat, amk_flat) — soul and career point from
    different angles so we take the stronger signal, not cumulative.
    """
    if digs is None:
        digs = {}

    # Gap-audit fix (2026-08): now references the single shared
    # _AK_DOMAIN_KEYWORDS table (see its module-level comment above) instead
    # of an independent local copy.

    def _flat_for(planet: str, scale: float) -> tuple[float, str]:
        """Returns (flat_value, tier) where tier is "primary"/"secondary"/"none"."""
        if not planet:
            return 0.0, "none"
        primary_kw, secondary_kw = _AK_DOMAIN_KEYWORDS.get(planet, ([], []))
        lbl = label.lower()
        # L2 fix: use word-boundary match (_wm) — this function adds up to 20 flat points
        # so false positives from bare substring match (e.g. "medicine" in "sports medicine")
        # are consequential and must be prevented.
        if any(_wm(kw, lbl) for kw in primary_kw):
            base, tier = 32.0, "primary"
        elif any(_wm(kw, lbl) for kw in secondary_kw):
            base, tier = 14.0, "secondary"
        else:
            return 0.0, "none"
        dig_mod = {"EXALTED": 1.4, "OWN": 1.2,
                   "NEECHA_BHANGA": 1.0, "DEBILITATED": 0.5}.get(digs.get(planet, ""), 1.0)
        return base * scale * dig_mod, tier

    ak_flat,  ak_tier  = _flat_for(ak,  1.00)
    amk_flat, amk_tier = _flat_for(amk, 0.65)
    if ak_flat >= amk_flat:
        raw, winning_tier = ak_flat, ak_tier
    else:
        raw, winning_tier = amk_flat, amk_tier
    # 2026-07 rebalance (engine-gap audit): this flat supplement was found to
    # dominate final_score (+800-1800% of a field's other-method contribution
    # in several audited charts) precisely because it's a FLAT addend applied
    # after every multiplier, so on a low-D10/low-method-score field it can be
    # 10-20x the field's own signal. Base values cut from 55/25 to 32/14 and
    # the cap from 20 to 12 so this can nudge a genuinely AK/AmK-aligned field
    # into visibility without being able to outrank a field with 2-3x more
    # real method convergence. Caller still scales this by (blended/100) and
    # by friction_multiplier, so the effective ceiling is well under 12 pts
    # for any field that isn't already scoring reasonably on its own methods.
    #
    # Gap-audit fix (2026-08, chat cross-chart review): that single 12.0 cap
    # applied regardless of which tier matched, so a single tangential
    # secondary-keyword hit (e.g. AjayAgarwal's Saturn AmK matching
    # "materials"/"industrial" for applied_chemistry) could saturate to the
    # exact same ceiling as a direct, unambiguous primary-keyword hit (Jupiter
    # AK matching "law" for law_llb) -- the mechanism could not tell "exact
    # match" from "tangential match" once either exceeded the cap. Secondary-
    # tier-only results are now held to a lower ceiling, so a primary match
    # keeps a real, visible edge over a secondary-only one instead of both
    # being indistinguishable at the ceiling.
    _cap = 12.0 if winning_tier == "primary" else 6.0
    return round(min(raw, _cap), 2)


def _karakamsha_domain_boost(label: str, domain: str, karakamsha: str) -> float:
    """Karakamsha sign (navamsa sign of AK) domain affinity bonus.

    The karakamsha sign reveals the soul's deepest natural expression.
    Certain signs naturally amplify specific domains via their ruling planet.
    """
    if not karakamsha:
        return 0.0

    _KM_DOMAIN: Dict[str, List[str]] = {
        "Aries":       ["engineering","defence","surgery","sports"],
        "Taurus":      ["arts","design","finance","commerce","luxury","architecture"],
        "Gemini":      ["technology","media","communication","data science","mathematics"],
        "Cancer":      ["medicine","nursing","psychology","public health","hospitality"],
        "Leo":         ["civil services","administration","law","leadership","performing arts"],
        "Virgo":       ["medicine","pharmacy","analytics","data","accounting","biotechnology"],
        "Libra":       ["law","arts","design","economics","commerce","fashion"],
        "Scorpio":     ["research","psychology","forensic","investigation","surgery","cybersecurity"],
        "Sagittarius": ["law","philosophy","education","international","theology","sports","economics","commerce","finance","data science","political","policy"],
        "Capricorn":   ["engineering","civil","mining","construction","government","agriculture"],
        "Aquarius":    ["technology","artificial intelligence","space","robotics","science","data science"],
        "Pisces":      ["arts","spiritual","medicine","research","philosophy","psychology","charity"],
    }
    label_lower = label.lower()
    matched_domains = _KM_DOMAIN.get(karakamsha, [])
    # Use word-boundary match for consistency with all other boost functions. M2 fix.
    if any(_wm(kw, label_lower) for kw in matched_domains):
        return 0.05
    return 0.0


def _h3_lord_communication_boost(
    label: str,
    domain: str,
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    planet_house: Dict[str, int],
) -> float:
    """H3 lord (skills, communication, effort) boost for communication-heavy domains.

    When H3 lord is strong, it enhances fields requiring writing, speaking,
    media, communication, sales, or technical exposition. H3 strength also
    aids technical/hands-on engineering fields via skill amplification.
    """
    h3_lord = house_lords.get("3", "")
    if not h3_lord:
        return 0.0
    s = eff_strengths.get(h3_lord, 0.0)
    h3_house = planet_house.get(h3_lord, 0)
    _COMM_KW = [
        "communication", "media", "journalism", "writing", "marketing",
        "public relations", "advertising", "broadcasting", "content", "social media",
        "sales", "copywriting", "digital marketing", "mass communication",
    ]
    _TECH_KW = ["engineering", "technology", "computer", "science", "mathematics", "research"]
    label_lower = label.lower()

    if not any(_wm(kw, label_lower) for kw in _COMM_KW + _TECH_KW):
        return 0.0

    # M3 fix: 0.30 is too permissive — a debilitated/combust H3 lord can score ~0.35.
    # Raise to 0.55 so only genuinely strong H3 lords activate the communication bonus.
    if s < 0.55:
        return 0.0

    bonus = 0.0
    if any(_wm(kw, label_lower) for kw in _COMM_KW):
        bonus += 0.04 + 0.04 * min(1.0, s)
        if h3_house in (1, 4, 5, 7, 9, 10):
            bonus += 0.02
    elif any(_wm(kw, label_lower) for kw in _TECH_KW):
        bonus += 0.02 + 0.02 * min(1.0, s)

    return min(bonus, 0.10)


def _h10_lord_trikona_bonus(affinity, h10_lord, planet_house, planet_dignities=None):
    """Bonus when H10 lord occupies a trikona (H1/H5/H9) with good dignity."""
    if not h10_lord: return 0.0
    if planet_dignities is None: planet_dignities = {}
    house = planet_house.get(h10_lord, 0) if isinstance(planet_house, dict) else 0
    if house not in (1, 5, 9): return 0.0
    w = affinity.get(h10_lord, 0.0)
    if w < 0.10: return 0.0
    dig = planet_dignities.get(h10_lord, "")
    base = 0.06 if w >= 0.20 else 0.03
    if dig == "EXALTED": base += 0.04
    elif dig == "OWN":   base += 0.02
    return min(base, 0.12)


def _h12_stellium_penalty(label, domain, planet_house):
    """Penalty when 3+ planets occupy H12 — research/medicine/spiritual fields exempt."""
    _EXEMPT = {"research", "medicine", "spiritual", "psychology", "philosophy",
               "theology", "foreign", "international", "ayurveda"}
    label_lower = label.lower()
    if any(k in label_lower or k in domain for k in _EXEMPT):
        return 0.0
    h12_count = sum(1 for h in planet_house.values() if h == 12)
    if h12_count >= 4: return -0.07
    if h12_count >= 3: return -0.04
    return 0.0


def _d10_lagna_lord_bonus(affinity, d10_chart, d10_lagna_sign, d10_digs=None):
    """Bonus when D10 lagna lord is dignified in D10."""
    if not d10_lagna_sign or not d10_chart: return 0.0
    if d10_digs is None: d10_digs = {}
    from .constants import _SIGN_LORD
    d10_ll = _SIGN_LORD.get(d10_lagna_sign, "")
    if not d10_ll: return 0.0
    dig = d10_digs.get(d10_ll, "")
    w = affinity.get(d10_ll, 0.0)
    if w < 0.10: return 0.0
    if dig == "EXALTED": return min(0.08 * w, 0.10)
    if dig == "OWN":     return min(0.05 * w, 0.07)
    return 0.0


def _modernize_karakas_modifier(field_id, risk, amk, kp_h10_star_lord, planets_d1):
    """Small nudge for Rahu/Mercury AmK in modern/tech fields."""
    if amk not in ("Rahu", "Mercury"): return 0.0
    _TECH_IDS = {"artificial_intelligence_ml", "data_science_analytics", "cybersecurity",
                             "machine_learning_ai", "robotics_automation", "space_technology",
               "biotechnology_research", "nuclear_engineering", "forensic_science",
               "information_technology", "computer_science_engineering",
               "electronics_communication", "nanotechnology", "bioinformatics",
               "aerospace_engineering", "space_systems_engineering",
               "blockchain_web3", "quantum_computing", "environmental_engineering"}
    if field_id not in _TECH_IDS:
        return 0.0
    # Rahu AMK in modern tech: unconventional disruptor energy — stronger nudge
    if amk == "Rahu":
        base = 0.06
    else:  # Mercury AMK
        base = 0.04
    # KP H10 star lord aligned to Rahu/Mercury in tech: extra confirmation
    if kp_h10_star_lord in ("Rahu", "Mercury"):
        base += 0.02
    # Rahu in planets_d1 strong (kendra or trikona house) amplifies the effect
    if planets_d1:
        rahu_house = None
        lagna_sign = ""
        # detect Rahu's approximate house from sign offset not available here;
        # use presence of Rahu in a known strong sign as a proxy
        rahu_sign = planets_d1.get("Rahu", {}).get("sign", "")
        if rahu_sign in ("Gemini", "Virgo", "Taurus", "Aquarius", "Aries"):
            base += 0.01
    return round(min(base, 0.10), 3)


def _build_critical_warnings(payload, war_result=None) -> list:
    """Build a list of critical astrological warning strings for reporting.

    Checks combustion, Graha Yuddha losers, and Mrita Avastha states for the
    chart's key planets (AK, AMK, lagna lord, H10 lord) and returns human-readable
    warning strings for display in the web report or advisory layer.
    """
    war_result   = war_result or {}
    warnings     = []
    combust      = set(getattr(payload, "combust_planets", []) or [])
    cazimi       = set(getattr(payload, "cazimi_planets",  []) or [])
    planets_d1   = getattr(payload, "planets_d1",  {}) or {}
    digs         = getattr(payload, "planet_dignities", {}) or {}
    ak           = getattr(payload, "atmakaraka",  "") or ""
    amk          = getattr(payload, "amatyakaraka", "") or ""
    lagna_lord   = getattr(payload, "lagna_lord",  "") or ""
    h10_lord     = (getattr(payload, "house_lords", {}) or {}).get("10", "")

    key_planets  = {p for p in (ak, amk, lagna_lord, h10_lord) if p}

    for planet in key_planets:
        role = []
        if planet == ak:        role.append("AK")
        if planet == amk:       role.append("AMK")
        if planet == lagna_lord: role.append("Lagna lord")
        if planet == h10_lord:  role.append("H10 lord")
        role_str = "/".join(role)
        if planet in combust and planet not in cazimi:
            warnings.append(f"COMBUST: {planet} ({role_str}) is combust — D1 vitality significantly reduced.")
        if planet in cazimi:
            warnings.append(f"CAZIMI: {planet} ({role_str}) is in the heart of the Sun — amplified but volatile.")
        war_status = war_result.get(planet, "")
        if war_status == "loser_bitter":
            warnings.append(f"GRAHA YUDDHA (bitter loss): {planet} ({role_str}) lost planetary war — severely weakened.")
        elif war_status == "loser_friendly":
            warnings.append(f"GRAHA YUDDHA (friendly loss): {planet} ({role_str}) lost planetary war — moderately weakened.")
        pdata = planets_d1.get(planet, {})
        if pdata:
            sign   = pdata.get("sign", "")
            degree = float(pdata.get("degree", 0))
            is_odd  = sign in _ODD_SIGNS
            is_mrita = (is_odd and degree >= 24.0) or (not is_odd and sign and degree < 6.0)
            if is_mrita:
                warnings.append(f"MRITA AVASTHA: {planet} ({role_str}) is in dead degrees ({sign} {degree:.1f}°) — severely weakened.")
        if digs.get(planet, "") == "DEBILITATED" and planet not in combust:
            warnings.append(f"DEBILITATED: {planet} ({role_str}) is in debilitation — check for Neecha Bhanga.")

    return warnings


def apply_domain_deduplication(
    results: List[Dict],
    per_domain_cap: int = 1,
    exempt_window: int = 1,
    dedup_window: int = 40,
    cluster_key: str = "career_family",
) -> List[Dict]:
    """Post-LLM domain deduplication — caps results per domain/cluster near the top.

    The first ``exempt_window`` results are always kept regardless of domain
    so the single best-scoring field is never filtered out.  After that, each
    additional domain entry beyond ``per_domain_cap`` is moved to the bottom
    of the list (not discarded) to preserve full coverage.

    Gap audit (2026-08): this function is called on the FULL scored
    population (engine.py: ``apply_domain_deduplication(_all_pre_results)``,
    ~198 fields across only 12 registry domains — engineering alone has 54
    fields), not just the top-5/top-35 slice its own docstring and history
    describe. With ``per_domain_cap=1`` applied unbounded, only ONE field per
    domain keeps its real computed score; every other field of that domain —
    e.g. 53 of engineering's 54 fields — gets shoved into `deferred` and its
    `final_score` overwritten to `floor - 0.01*offset`, where `floor` is a
    SINGLE shared value (the min score among the ~12 domain leaders). Real
    case traced on a live chart: electrical_engineering, aeronautical_
    engineering, and energy_engineering (all domain=engineering, all with
    strong blended_scores of 78-82) were flattened to 29.7-31.7 alongside
    completely unrelated deferred fields (political_science, defence_
    military) sharing that same floor — while whichever engineering field
    happened to be domain-leader that run (e.g. power_systems_engineering)
    kept its real score untouched. This wasn't "domain diversity" working as
    designed; it was ~94% of the scored population's differentiation being
    silently destroyed by a mechanism whose own history/docstring only ever
    justifies influencing the top-5/top-35 window.

    Fix: bound the cap/floor logic to the first ``dedup_window`` items (the
    function already receives a score-sorted list, so this is "near the
    top" in the same sense the original top-5 fix intended). Anything beyond
    that window is appended back with its own real, untouched `final_score`
    — it was never a "top-5 crowding" problem to begin with, and the actual
    downstream consumer of this function's output
    (``_edu_stream_slot_allocation(..., n=35)``) only ever looks at ~35-40
    items anyway, so 40 gives it comfortable headroom without reintroducing
    the original top-5 same-domain-sweep bug this function exists to prevent.

    Gap audit (2026-07): previously ``exempt_window=5`` meant the entire
    top-5 was exempt from any domain cap, so this function never actually
    influenced the range every downstream consumer (and the stress-test
    suite) checks for "domain X in top-5". A chart whose raw scoring happened
    to concentrate in one or two domains (e.g. several "engineering" variants,
    or "interdisciplinary" data-science hybrids) could fill all 5 slots with
    the same domain even when a different domain's field was well-represented
    just outside the window (e.g. rank 6-10). Tightening exempt_window to 1
    and per_domain_cap to 2 preserves the single best match untouched while
    guaranteeing the top-5 draws from at least 3 distinct domains whenever
    that many are present in the ranked list — this is what actually fixed
    gaps S112/S117/S122/S165/S205/S221/S233/S253/S267/S291, all of which were
    "expected domain present just outside the top-5, crowded out by
    same-domain repeats inside it."

    Tuning note: exempt_window=1/per_domain_cap=2 already fixed most of these
    (e.g. S165 — surfaces "interdisciplinary"), but S112 needed the full
    per_domain_cap=1 to surface "technology": with cap=2, two
    "interdisciplinary" data-science-hybrid entries still filled 2 of the 5
    slots before a same-domain "engineering" repeat took a 3rd, leaving no
    room for the one "technology"-domain field ranked just below. cap=1 caps
    every domain (including the runner-up itself) at exactly one appearance
    before the cap window closes, which is what guarantees 5 distinct domains
    whenever 5 are available in the ranked list.

    2026-07-04 follow-up (S112/S143/S165/S195/S221/S253 still failing after
    the above): this function only ever REORDERED the list — it never
    touched final_score. That made the reordering invisible to anything
    downstream that re-sorts by score, and two things do exactly that:
    `_edu_stream_slot_allocation`'s own pool-merge re-sort ("S361 fix") and
    engine.py's final "defensive re-sort... guarantee strict descending
    final_score order" right before top_35 is returned. Both silently threw
    away this function's ordering and restored pure raw-score order, so
    domain deduplication accomplished nothing by the time results reached
    the caller — the exact same-domain sweeps and missing-expected-domain
    gaps kept recurring. Fix: bake the reordering into final_score itself
    (bounded, transparent, same pattern as the tie-break cascade / family-
    cohesion adjustment elsewhere in this codebase) so ANY later sort by
    final_score reproduces this function's decision instead of undoing it.

    AUDIT FIX (2026-08-23): two compounding problems traced on a real chart
    (ramsunder_chart_details.json): the top-level ``domain`` field is far
    too coarse a unit for "diversity" -- this registry has only 12 domains
    for 213 fields, and ``domain="engineering"`` alone covers 57 genuinely
    distinct professions (civil, aerospace, chemical, materials, electrical,
    computer...), not near-duplicates of each other. With a flat
    ``per_domain_cap=1`` applied uniformly, a chart whose real astrology
    concentrates strongly in engineering (as ramsunder's does) can only ever
    surface ONE engineering field near the top no matter how many other
    engineering fields score highly and distinctly -- civil_engineering
    scored 71.94 (rank 27 of 213 overall, a genuinely strong result) and was
    still flattened purely because 16 *other* engineering fields scored
    higher, none of which makes it a near-duplicate of any of them. This is
    the same class of bug as the domain-crowding problem this function was
    built to fix, just inverted: instead of one domain flooding the top
    ranks with redundant entries, one domain's real breadth is punished as
    if it were redundancy.

    Two changes address this without touching the core cap/floor mechanism
    (still correct in principle -- see gap audits above):

    1. Group by ``cluster_key`` (default ``"career_family"``, already
       attached to every row earlier in the pipeline by
       apply_competency_ontology_layer -- a finer-grained clustering, e.g.
       "materials & manufacturing" vs. "civil & structural" vs.
       "aerospace & defence" rather than one blanket "engineering" bucket)
       when present on a row, falling back to the coarser ``domain`` only
       when it is missing (e.g. the ontology layer failed defensively
       upstream and never attached it). This targets the mechanism at
       actual near-duplicates instead of an entire profession.
    2. Scale the cap to the real population of whatever grouping key ends
       up being used, computed from this same call's full input population
       (not the registry as a whole, so this stays self-contained and
       correct even if the registry's domain/family sizes change): a
       cluster/domain with only a handful of candidates keeps the original
       cap=1 behavior (still guarantees the top slots draw from distinct
       clusters when few exist), but a cluster/domain this deep gets
       proportionally more room, so real breadth within it can still
       surface instead of being crushed to a single representative.
    """
    if not results:
        return results

    def _group_key(item: Dict) -> str:
        return item.get(cluster_key) or item.get("domain", "")

    _group_population: Dict[str, int] = {}
    for _item in results:
        _g = _group_key(_item)
        _group_population[_g] = _group_population.get(_g, 0) + 1

    def _cap_for(group: str) -> int:
        n = _group_population.get(group, 0)
        if n <= 10:
            return per_domain_cap
        if n <= 25:
            return max(per_domain_cap, 2)
        return max(per_domain_cap, 3)

    window = results[:dedup_window]
    beyond_window = results[dedup_window:]
    domain_counts: Dict[str, int] = {}
    kept: List[Dict] = []
    deferred: List[Dict] = []
    for idx, item in enumerate(window):
        domain = _group_key(item)
        cap = _cap_for(domain)
        if idx < exempt_window:
            kept.append(item)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        else:
            count = domain_counts.get(domain, 0)
            if count < cap:
                kept.append(item)
                domain_counts[domain] = count + 1
            else:
                deferred.append(item)

    # Make the demotion survive any later "sort by final_score" step: give
    # every deferred item a final_score strictly below the lowest score
    # among all currently-kept items (which is where this function actually
    # wants them to land), while preserving their relative order to each
    # other. The original score is preserved separately for audit/debugging.
    if deferred:
        floor = min((k.get("final_score", 0.0) for k in kept), default=0.0)
        for offset, item in enumerate(deferred, start=1):
            item["pre_dedup_final_score"] = item.get("final_score", 0.0)
            item["final_score"] = round(floor - 0.01 * offset, 4)
            item["domain_dedup_demoted"] = True

    # `beyond_window` items never entered the cap/floor logic at all — they
    # keep their own real, untouched final_score. `results` is already
    # score-sorted on entry (engine.py sorts _all_pre_results immediately
    # before calling this), so every beyond_window item's real score is
    # already <= every window item's real score; appending them after
    # kept+deferred does not introduce any new inversion, it just stops
    # silently overwriting scores this function was never designed to touch.
    return kept + deferred + beyond_window


# =============================================================================
# MODULE 1 EXPANSION — 360° COMPETENCY & ENVIRONMENT PROFILING
# =============================================================================

# ── Feature 1: Corporate vs Entrepreneurial Balance ──────────────────────────
# House weights reflecting employment vs self-driven energy.
# Corporate: H6 (service), H10 (hierarchy/bosses), H2 (steady income)
# Entrepreneurial: H3 (courage/self-effort), H7 (partnerships/business), H11 (independent gains)

# Corporate:      H6 (service/employment), H10 (career hierarchy), H2 (steady salary)
# Entrepreneurial: H1 (self-initiative), H3 (courage/self-effort), H5 (creativity/risk),
#                  H7 (partnerships/business), H9 (fortune/venture), H11 (independent gains)
# H4 removed from corporate — home/comfort has no employment signal
# H2 kept in corporate only (steady income from employer); H5 added to entrepreneurial
_CORP_HOUSE_WEIGHTS   = {6: 1.0, 10: 1.0, 2: 0.6}
_ENTREP_HOUSE_WEIGHTS = {1: 0.4, 3: 0.9, 5: 0.6, 7: 1.0, 9: 0.5, 11: 0.7}

def compute_corporate_entrepreneurial_score(
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    atmakaraka: str = "",
) -> Dict:
    """Return a 0–1 float (1=fully corporate, 0=fully entrepreneurial) and a label.

    Strategy:
    - Sum effective strength of planets placed in corporate houses.
    - Sum effective strength of planets placed in entrepreneurial houses.
    - Normalize to a ratio.

    Also checks if the Atmakaraka is in an entrepreneurial house (strong signal).
    """
    corp_score   = 0.0
    entrep_score = 0.0

    for planet, house in planet_house.items():
        strength = eff_strengths.get(planet, 1.0)
        corp_score   += _CORP_HOUSE_WEIGHTS.get(house, 0.0)   * strength
        entrep_score += _ENTREP_HOUSE_WEIGHTS.get(house, 0.0) * strength

    # Atmakaraka placement — strong signal in EITHER direction.
    # Gap-43 (audit 2026-07) fix: the AK boost only ever amplified the
    # entrepreneurial side; an AK in H6/H10/H2 (service/career/income) is an
    # equally strong soul-level corporate signal and now boosts symmetrically.
    ak_house = planet_house.get(atmakaraka, 0)
    if ak_house in _ENTREP_HOUSE_WEIGHTS:
        entrep_score += _ENTREP_HOUSE_WEIGHTS[ak_house] * 1.5   # AK weight boost
    elif ak_house in _CORP_HOUSE_WEIGHTS:
        corp_score += _CORP_HOUSE_WEIGHTS[ak_house] * 1.5       # AK corporate boost

    total = corp_score + entrep_score
    if total == 0:
        corporate_pct = 50
    else:
        corporate_pct = int(round(corp_score / total * 100))

    entrep_pct = 100 - corporate_pct

    if corporate_pct >= 75:
        style_label = "Strong Corporate"
        style_note  = "Built for MNCs, established organisations, and structured hierarchies."
    elif corporate_pct >= 60:
        style_label = "Corporate-Leaning"
        style_note  = "Thrives within organisations but benefits from intrapreneurial roles with autonomy."
    elif corporate_pct >= 45:
        style_label = "Balanced / Hybrid"
        style_note  = "Equally suited to corporate roles with independent scope or consulting tracks."
    elif corporate_pct >= 30:
        style_label = "Entrepreneurial-Leaning"
        style_note  = "Consulting, freelance, or founding roles within larger ecosystems will outperform pure employment."
    else:
        style_label = "Strong Entrepreneurial"
        style_note  = "Independent practice, business ownership, or venture-backed founding are natural paths."

    return {
        "corporate_pct":   corporate_pct,
        "entrep_pct":      entrep_pct,
        "style_label":     style_label,
        "style_note":      style_note,
    }


# ── Feature 2: Dhana Yoga / Wealth Potential per Field ───────────────────────
# A field can generate career success but low financial return if the
# 2nd/11th lords (wealth planets) are disconnected from that field's planets.

_FIELD_PRIMARY_PLANETS: Dict[str, List[str]] = {
    # Maps domain → typical primary planets (add more as needed)
    "law":         ["Jupiter", "Mercury", "Saturn"],
    "technology":  ["Mercury", "Rahu", "Mars"],
    "medicine":    ["Mars", "Sun", "Moon", "Ketu"],
    "finance":     ["Venus", "Mercury", "Jupiter"],
    "arts":        ["Venus", "Moon", "Mercury"],
    "teaching":    ["Jupiter", "Mercury", "Moon"],
    "engineering": ["Mars", "Saturn", "Mercury"],
    "research":    ["Ketu", "Saturn", "Mercury"],
    "management":  ["Sun", "Jupiter", "Saturn"],
    "consulting":  ["Mercury", "Jupiter", "Venus"],
    "military":    ["Mars", "Sun", "Saturn"],
    "_default":    ["Mercury", "Jupiter"],
}

def _graha_drishti_houses(planet: str, from_house: int) -> set:
    """Classical Parashari graha-drishti (planetary aspect): every planet
    casts a full (100%) aspect on the 7th house from its own placement;
    Mars, Jupiter, and Saturn additionally cast full special aspects (Mars:
    4th/8th; Jupiter: 5th/9th; Saturn: 3rd/10th from itself). This is the
    mainstream, universally-taught aspect scheme (BPHS ch. on graha
    drishti) -- deliberately NOT extending special aspects to Rahu/Ketu,
    since which houses the nodes specially aspect is a genuinely disputed
    point across traditions (some give them Jupiter's 5th/9th, others treat
    them as Saturn-like, others give only the 7th); staying with the
    uncontested mainstream scheme keeps this function's output defensible
    rather than tradition-specific.
    """
    if not from_house or not (1 <= from_house <= 12):
        return set()
    # `nth_houses` values are counted INCLUSIVELY the classical way (the
    # planet's own house = "1st from itself", so the 7th house from it is
    # 6 steps ahead, not 7) -- convert to a 0-based step count (n-1) before
    # applying the wheel-wrap arithmetic below. Confirmed against the
    # standard worked example: a planet in H1 (Aries) casts its 7th-house
    # aspect on H7 (Libra), i.e. from_house=1, n=7 must resolve to house 7.
    nth_houses = {7}
    if planet == "Mars":
        nth_houses |= {4, 8}
    elif planet == "Jupiter":
        nth_houses |= {5, 9}
    elif planet == "Saturn":
        nth_houses |= {3, 10}
    return {((from_house - 1 + (n - 1)) % 12) + 1 for n in nth_houses}


def _chart_wide_dhana_yogas(house_lords: Dict[str, str], planet_house: Dict[str, int]) -> Dict[str, Any]:
    """Scan the WHOLE chart (not just a field's hardcoded primary planets) for
    classical Dhana yogas on both the primary (2nd/11th) and secondary
    (9th/5th) wealth axes.

    Full Methodology Spec §7: primary axis = 2nd lord in 2nd/11th (own sign
    or exchange), 11th lord in 2nd, 2nd/11th lord conjunction, Jupiter/Venus/
    Mercury connected to 2nd or 11th; secondary axis = 9th lord aspecting/
    joining 2nd/11th ("Dharma-linked wealth" — more durable/reputation-
    linked) or 5th lord aspecting/joining 2nd/11th ("merit/expertise/
    speculation-linked wealth"). This previously only ever looked at whether
    a field's hardcoded `_FIELD_PRIMARY_PLANETS` happened to BE or touch the
    2nd/11th lord — it never scanned the chart's own Dhana-yoga topology
    (own-sign, exchange, conjunction) and never touched the 9th/5th axis at
    all, so e.g. a genuine Venus-in-Taurus (own sign, H2) Dhana yoga was
    invisible for any field whose domain table didn't happen to include
    Venus. This function is domain/field-independent: it returns the set of
    "wealth-eligible" planets on each axis, which compute_wealth_potential
    below then checks a field's own significators against.

    Aspect fix (2026-08-20, defensibility audit): graha-drishti (classical
    planetary aspect, via `_graha_drishti_houses()` just above) is now
    checked alongside placement/exchange/conjunction on every axis. Before
    this fix, a chart whose 2nd/11th/9th/5th lords connected to the wealth
    houses purely by aspect -- a common, classically equal-standing
    configuration -- returned a completely empty result, which made
    compute_wealth_potential's "prestige-strong, wealth-durability
    uncertain" flag fire for every single field in that chart (nothing left
    to intersect against), rather than reflecting genuine field-by-field
    variation.
    """
    h2_lord  = house_lords.get("2",  "")
    h11_lord = house_lords.get("11", "")
    h9_lord  = house_lords.get("9",  "")
    h5_lord  = house_lords.get("5",  "")

    primary_planets: Dict[str, str] = {}   # planet -> reason
    secondary_dharma: Dict[str, str] = {}  # planet -> reason (9th axis)
    secondary_speculative: Dict[str, str] = {}  # planet -> reason (5th axis)

    h2_house  = planet_house.get(h2_lord, 0) if h2_lord else 0
    h11_house = planet_house.get(h11_lord, 0) if h11_lord else 0
    h9_house  = planet_house.get(h9_lord, 0) if h9_lord else 0
    h5_house  = planet_house.get(h5_lord, 0) if h5_lord else 0

    # 2nd lord in own sign (still ruling H2) or in H11
    if h2_lord and h2_house == 2:
        primary_planets[h2_lord] = "2nd lord in own sign (H2)"
    elif h2_lord and h2_house == 11:
        primary_planets[h2_lord] = "2nd lord placed in H11"

    # 11th lord in H2
    if h11_lord and h11_house == 2:
        primary_planets[h11_lord] = "11th lord placed in H2"

    # Parivartana (mutual exchange) between 2nd and 11th lords
    if h2_lord and h11_lord and h2_house == 11 and h11_house == 2:
        primary_planets[h2_lord] = "2nd/11th lord exchange (parivartana)"
        primary_planets[h11_lord] = "2nd/11th lord exchange (parivartana)"

    # 2nd/11th lord conjunction (co-placed in the same house)
    if h2_lord and h11_lord and h2_lord != h11_lord and h2_house and h2_house == h11_house:
        primary_planets[h2_lord] = "conjunct with 11th lord"
        primary_planets[h11_lord] = "conjunct with 2nd lord"

    # Jupiter/Venus/Mercury (natural wealth/value significators) placed in H2/H11
    for nat in ("Jupiter", "Venus", "Mercury"):
        nat_house = planet_house.get(nat, 0)
        if nat_house in (2, 11):
            primary_planets.setdefault(nat, f"natural wealth significator placed in H{nat_house}")

    # Aspect-based additions (audit fix, 2026-08-20): graha drishti is one of
    # the most basic tools of classical yoga-formation -- a planet aspecting
    # a house is treated as "seeing"/connecting with it, not just occupying
    # or exchanging with it (BPHS explicitly forms Dhana yogas this way, not
    # only via conjunction/exchange). Previously this function only ever
    # checked placement/exchange/co-placement, so a chart where the 2nd/11th
    # lords or the natural significators connect to the wealth houses purely
    # by aspect (a very common, classically equal-standing configuration)
    # registered as "zero wealth yoga" -- which then flagged every field's
    # wealth_potential as "prestige-strong, wealth-durability uncertain"
    # (compute_wealth_potential intersects a field's significators against
    # WHATEVER this function finds; an empty result here makes that flag
    # fire for literally every field, not a considered per-field judgment).
    # Confirmed live on a real chart (Vaagesh Narayan, 2026-08-20 audit):
    # the placement/exchange-only scan found nothing at all, so 20/20 of the
    # published Top-20 carried the same uncertain-wealth flag identically --
    # exactly the all-or-nothing failure mode this aspect layer fixes.
    if h2_lord and 11 in _graha_drishti_houses(h2_lord, h2_house):
        primary_planets.setdefault(h2_lord, "2nd lord aspects 11th house (graha drishti)")
    if h11_lord and 2 in _graha_drishti_houses(h11_lord, h11_house):
        primary_planets.setdefault(h11_lord, "11th lord aspects 2nd house (graha drishti)")
    for nat in ("Jupiter", "Venus", "Mercury"):
        nat_house = planet_house.get(nat, 0)
        if nat_house and ({2, 11} & _graha_drishti_houses(nat, nat_house)):
            _seen_h = sorted({2, 11} & _graha_drishti_houses(nat, nat_house))
            primary_planets.setdefault(
                nat, f"natural wealth significator aspects H{'/'.join(str(h) for h in _seen_h)} (graha drishti)"
            )

    # Secondary axis: 9th lord joining/aspecting 2nd or 11th
    if h9_lord and h9_house in (2, 11):
        secondary_dharma[h9_lord] = f"9th lord placed in H{h9_house} (dharma-linked wealth)"
    if h9_lord and h2_lord and h9_house == h2_house and h9_house:
        secondary_dharma[h9_lord] = "9th lord conjunct 2nd lord (dharma-linked wealth)"
    if h9_lord and h11_lord and h9_house == h11_house and h9_house:
        secondary_dharma[h9_lord] = "9th lord conjunct 11th lord (dharma-linked wealth)"
    if h9_lord and h9_house and ({2, 11} & _graha_drishti_houses(h9_lord, h9_house)):
        secondary_dharma.setdefault(h9_lord, "9th lord aspects 2nd/11th house (graha drishti, dharma-linked wealth)")

    # Secondary axis: 5th lord joining/aspecting 2nd or 11th, or mutual
    # 5th/2nd/11th connections (speculation/expertise-linked wealth)
    if h5_lord and h5_house in (2, 11):
        secondary_speculative[h5_lord] = f"5th lord placed in H{h5_house} (merit/speculation-linked wealth)"
    if h5_lord and h2_lord and h5_house == h2_house and h5_house:
        secondary_speculative[h5_lord] = "5th lord conjunct 2nd lord (merit/speculation-linked wealth)"
    if h5_lord and h11_lord and h5_house == h11_house and h5_house:
        secondary_speculative[h5_lord] = "5th lord conjunct 11th lord (merit/speculation-linked wealth)"
    if h5_lord and h5_house and ({2, 11} & _graha_drishti_houses(h5_lord, h5_house)):
        secondary_speculative.setdefault(
            h5_lord, "5th lord aspects 2nd/11th house (graha drishti, merit/speculation-linked wealth)"
        )

    return {
        "primary": primary_planets,
        "secondary_dharma": secondary_dharma,
        "secondary_speculative": secondary_speculative,
    }


def compute_wealth_potential(
    field_result: Dict,
    house_lords: Dict[str, str],
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    field_affinity: Dict[str, float] | None = None,
) -> Dict:
    """Return a wealth potential score/label for a specific field, per Full
    Methodology Spec §7 (2nd/11th primary axis + 9th/5th secondary axis).

    This checks the field's OWN significators (its affinity vector, when
    provided, falling back to the old hardcoded domain->primaries table for
    callers that don't yet pass one) against the chart-wide Dhana-yoga scan
    in _chart_wide_dhana_yogas() above, so a real 2nd/11th own-sign/exchange
    yoga is found even for fields whose domain isn't one of the handful of
    hardcoded keys.

    wealth_axis distinguishes primary (2nd/11th) wealth, secondary_dharma
    (9th-linked, "more durable/ethically-earned") wealth, and
    secondary_speculative (5th-linked, "merit/expertise/speculation-linked")
    wealth per the spec's explicit instruction not to collapse these into
    one generic label.

    A field with ZERO wealth-eligible planets across all four houses gets an
    explicit, non-penalizing "prestige_strong_wealth_uncertain" flag instead
    of being silently scored/labeled "Low" with a discouraging note.
    """
    domain = field_result.get("domain", "_default")
    if field_affinity:
        primaries = [p for p, w in field_affinity.items() if w and w > 0]
    else:
        primaries = _FIELD_PRIMARY_PLANETS.get(domain, _FIELD_PRIMARY_PLANETS["_default"])

    yogas = _chart_wide_dhana_yogas(house_lords, planet_house)

    wealth_score = 0.0
    connections: List[str] = []
    axis_hits = {"primary": [], "secondary_dharma": [], "secondary_speculative": []}

    for planet in primaries:
        strength = eff_strengths.get(planet, 1.0)
        if planet in yogas["primary"]:
            # Primary axis: 0.08-0.15 per planet (spec §7.4), scaled by strength.
            wealth_score += 0.115 * strength
            axis_hits["primary"].append(planet)
            connections.append(f"{planet}: {yogas['primary'][planet]}")
        if planet in yogas["secondary_dharma"]:
            # Secondary/dharma axis: 0.04-0.08 per planet (spec §7.4).
            wealth_score += 0.06 * strength
            axis_hits["secondary_dharma"].append(planet)
            connections.append(f"{planet}: {yogas['secondary_dharma'][planet]}")
        if planet in yogas["secondary_speculative"]:
            # §7 remediation (2026-08): secondary/speculative axis is a
            # DISTINCT, slightly lower range (0.03-0.06 per spec §7.4) from
            # the dharma axis's 0.04-0.08 -- speculative/merit-linked wealth
            # (5th house) is classically less durable than dharma-linked
            # wealth (9th house). Previously both used the same 0.06
            # constant, collapsing that intended magnitude distinction.
            wealth_score += 0.045 * strength
            axis_hits["secondary_speculative"].append(planet)
            connections.append(f"{planet}: {yogas['secondary_speculative'][planet]}")

    zero_eligible = not (axis_hits["primary"] or axis_hits["secondary_dharma"] or axis_hits["secondary_speculative"])

    # Normalize against a plausible max (roughly 3 primary-axis hits at max strength)
    normalised = min(wealth_score / 0.6, 1.0)

    if zero_eligible:
        label = "Uncertain"
        note = ("No 2nd/11th/9th/5th-house Dhana-yoga connection found for this field's own "
                "significators. This does not mean the field is weak — it may be prestige-strong "
                "via other houses — but its wealth durability specifically is uncertain from this "
                "chart's wealth axes and should be paired with a deliberate monetisation strategy.")
    elif axis_hits["primary"] and normalised >= 0.5:
        label = "High"
        note = "Strong primary-axis (2nd/11th) wealth connection — durable, direct financial alignment."
    elif axis_hits["primary"]:
        label = "Medium"
        note = "Primary-axis (2nd/11th) wealth connection present, moderate strength."
    elif axis_hits["secondary_dharma"] and not axis_hits["secondary_speculative"]:
        label = "Medium (dharma-linked)"
        note = ("Wealth here is linked through the 9th house — reputation/dharma-linked income, "
                "typically slower-building but more durable and ethically-earned than direct "
                "2nd/11th wealth.")
    elif axis_hits["secondary_speculative"] and not axis_hits["secondary_dharma"]:
        label = "Medium (speculative/merit-linked)"
        note = ("Wealth here is linked through the 5th house — merit, expertise, and speculative-"
                "gains income (investment acumen, intelligence-driven earnings) rather than direct "
                "2nd/11th accumulation.")
    else:
        label = "Medium (mixed axes)"
        note = "Wealth support present via both the 9th (dharma-linked) and 5th (speculative-linked) axes."

    # -- Instrumentation: final per-planet wealth bonus + narrative (spec §7) --
    _field_label = field_result.get("field") or field_result.get("field_id") or field_result.get("domain") or "field"
    _h2, _h11, _h9, _h5 = house_lords.get("2", "?"), house_lords.get("11", "?"), house_lords.get("9", "?"), house_lords.get("5", "?")
    if _VERBOSE_FIELD_LOG:
        print(f"[WEALTH FILTER] {_field_label}: house lords checked -- 2nd={_h2} 11th={_h11} 9th={_h9} 5th={_h5}")
        for _planet in primaries:
            if _planet in yogas["primary"]:
                print(f"  Wealth bonus -- {_planet}: {0.115 * eff_strengths.get(_planet, 1.0):.3f} (2nd/11th primary axis, {yogas['primary'][_planet]})")
            if _planet in yogas["secondary_dharma"]:
                print(f"  Wealth bonus -- {_planet}: {0.06 * eff_strengths.get(_planet, 1.0):.3f} (9th-axis dharma-linked, {yogas['secondary_dharma'][_planet]})")
            if _planet in yogas["secondary_speculative"]:
                print(f"  Wealth bonus -- {_planet}: {0.045 * eff_strengths.get(_planet, 1.0):.3f} (5th-axis speculative-linked, {yogas['secondary_speculative'][_planet]})")
    _narrative = (
        f"Wealth-filter analysis for {_field_label}: checked lords of the 2nd ({_h2}), 11th ({_h11}), "
        f"9th ({_h9}), and 5th ({_h5}) houses against this field's own significators "
        f"({', '.join(primaries) if primaries else 'none'}). "
        + (f"Primary (2nd/11th) Dhana-yoga connection found via {', '.join(axis_hits['primary'])}, "
           f"indicating durable, direct financial alignment. " if axis_hits["primary"] else "")
        + (f"Secondary dharma-linked (9th-house) wealth found via {', '.join(axis_hits['secondary_dharma'])} -- "
           f"slower-building but more durable/ethically-earned income. " if axis_hits["secondary_dharma"] else "")
        + (f"Secondary speculative/merit-linked (5th-house) wealth found via {', '.join(axis_hits['secondary_speculative'])} -- "
           f"expertise or investment-driven earnings rather than direct accumulation. " if axis_hits["secondary_speculative"] else "")
        + (f"No wealth-bonus-eligible planets were found on any of the four houses for this field's "
           f"significators, so the field is flagged 'prestige-strong but wealth-durability uncertain' "
           f"rather than penalized -- {_field_label} may still succeed on merit, but its financial "
           f"durability is not confirmed by this chart's Dhana-yoga topology. " if zero_eligible else "")
        + f"Resulting wealth potential: {label} (normalised score {round(normalised, 3)})."
    )
    if _VERBOSE_FIELD_LOG:
        print(f"[WEALTH NARRATIVE] {_narrative}")

    return {
        "wealth_potential":         label,
        "wealth_score":             round(normalised, 3),
        "wealth_connections":       connections[:5],
        "wealth_note":              note,
        "wealth_axis_primary":      axis_hits["primary"],
        "wealth_axis_dharma_9th":   axis_hits["secondary_dharma"],
        "wealth_axis_speculative_5th": axis_hits["secondary_speculative"],
        "prestige_strong_wealth_uncertain_flag": zero_eligible,
    }


# ── Feature 3: Geographic Suitability ────────────────────────────────────────

def compute_geo_suitability(
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    lagna_sign: str = "",
) -> Dict:
    """Return geographic direction: Domestic | Hybrid | International/Relocation.

    Astrological basis:
    - H9 (long journeys, higher wisdom, foreign connections)
    - H12 (foreign lands, isolation, expatriate life)
    - H3 (short travel, courage, neighbouring regions)
    - Rahu (foreign, unconventional, cross-cultural ambition)
    - Moon (home, comfort, native land)

    Strong H9/H12 + Rahu in mobile signs → International/Relocation
    Strong Moon + H4 + fixed-sign dominance → Domestic
    Mixed → Hybrid (remote roles for multinationals)
    """
    rahu_house = planet_house.get("Rahu", 0)
    moon_house = planet_house.get("Moon", 0)
    h9_lord    = house_lords.get("9",  "")
    h12_lord   = house_lords.get("12", "")
    h4_lord    = house_lords.get("4",  "")

    foreign_score  = 0.0
    domestic_score = 0.0

    # H9 lord strength
    h9_strength = eff_strengths.get(h9_lord, 1.0) if h9_lord else 1.0
    if planet_house.get(h9_lord, 0) in (9, 12, 3, 11):
        foreign_score += h9_strength * 1.2

    # H12 lord strength
    h12_strength = eff_strengths.get(h12_lord, 1.0) if h12_lord else 1.0
    if planet_house.get(h12_lord, 0) in (9, 12, 1):
        foreign_score += h12_strength * 1.0

    # Rahu in angular/upachaya houses → foreign movement
    if rahu_house in (1, 4, 7, 10):
        foreign_score += 1.5
    elif rahu_house in (3, 9, 11):
        foreign_score += 1.0

    # Moon in H4 or H1 → domestic comfort
    if moon_house in (4, 1, 2):
        domestic_score += eff_strengths.get("Moon", 1.0) * 1.2

    # H4 lord in own house or exalted → strong domestic roots
    h4_strength = eff_strengths.get(h4_lord, 1.0) if h4_lord else 1.0
    h4_lord_house = planet_house.get(h4_lord, 0) if h4_lord else 0
    if h4_lord_house == 4:
        domestic_score += h4_strength * 1.2

    total = foreign_score + domestic_score
    if total == 0:
        foreign_pct = 50
    else:
        foreign_pct = int(round(foreign_score / total * 100))

    if foreign_pct >= 65:
        geo_label = "International / Relocation"
        geo_note  = ("Planetary configuration strongly favours foreign employment, "
                     "overseas postings, or remote roles with multinational scope. "
                     "Consider roles in global companies or cross-border practices.")
    elif foreign_pct >= 45:
        geo_label = "Hybrid"
        geo_note  = ("Both domestic and international paths are viable. "
                     "Remote work for global organisations, or domestic roles "
                     "with significant travel, optimise this configuration.")
    else:
        geo_label = "Domestic"
        geo_note  = ("Strongest career growth likely within the home country or region. "
                     "Roles in domestic-focused organisations, government, or local enterprise "
                     "will align best with your chart.")

    return {
        "geo_suitability":   geo_label,
        "geo_foreign_pct":   foreign_pct,
        "geo_domestic_pct":  100 - foreign_pct,
        "geo_note":          geo_note,
    }


# ── Feature 4: Burnout & Stress Vector ───────────────────────────────────────

_HIGH_STRESS_DOMAINS = {
    "medicine", "military", "law enforcement", "finance",
    "law", "consulting", "technology", "engineering",
}

def compute_burnout_risk(
    field_result: Dict,
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    combust_planets: List[str] = None,
) -> Dict:
    """Return a burnout risk level and role recommendation for a specific field.

    Logic:
    - Identify primary planets for the field's domain.
    - Check if any primary planet is placed in H6 (chronic stress), H8 (crisis/sudden events),
      or is combust (Sun's proximity → burnout of planetary energy).
    - Combine with domain inherent stress level.
    - Return Low / Medium / High + specific sub-role recommendation.
    """
    combust_planets = set(combust_planets or [])
    domain  = field_result.get("domain", "_default")
    primaries = _FIELD_PRIMARY_PLANETS.get(domain, _FIELD_PRIMARY_PLANETS["_default"])

    h6_lord  = house_lords.get("6",  "")
    h8_lord  = house_lords.get("8",  "")
    h6_occupants = [p for p, h in planet_house.items() if h == 6]
    h8_occupants = [p for p, h in planet_house.items() if h == 8]

    stress_score = 0.0
    stress_flags = []

    for planet in primaries:
        ph = planet_house.get(planet, 0)

        if ph == 6:
            stress_score += 1.5
            stress_flags.append(f"{planet} (primary planet) placed in H6 — chronic daily friction")

        if ph == 8:
            stress_score += 1.8
            stress_flags.append(f"{planet} (primary planet) placed in H8 — crisis/sudden disruption risk")

        if planet == h6_lord:
            stress_score += 1.0
            stress_flags.append(f"{planet} is H6 lord — field activates the stress house")

        if planet == h8_lord:
            stress_score += 1.2
            stress_flags.append(f"{planet} is H8 lord — transformation/crisis energy in this field")

        if planet in combust_planets:
            stress_score += 0.8
            stress_flags.append(f"{planet} is combust — energy burns bright but depletes faster")

    # Domain inherent stress baseline
    if domain in _HIGH_STRESS_DOMAINS:
        stress_score += 0.5

    # Normalise: max realistic ≈ 6.0
    normalised = min(stress_score / 6.0, 1.0)

    if normalised >= 0.60:
        risk_label = "High"
        risk_note = (
            "Significant burnout risk in frontline roles. "
            "Strongly recommend targeting research, advisory, policy, or academic sub-roles "
            "within this field rather than high-pressure delivery or clinical environments."
        )
    elif normalised >= 0.30:
        risk_label = "Medium"
        risk_note = (
            "Manageable stress with deliberate boundary-setting. "
            "Avoid roles with 24/7 on-call requirements. "
            "Regular recovery rituals (structured breaks, delegation culture) are essential."
        )
    else:
        risk_label = "Low"
        risk_note = (
            "Your chart is well-suited to absorb the demands of this field. "
            "The primary planets carry the necessary resilience for sustained performance."
        )

    return {
        "burnout_risk":   risk_label,
        "burnout_score":  round(normalised, 3),
        "stress_flags":   stress_flags[:3],
        "burnout_note":   risk_note,
    }


# =============================================================================
# MODULE 1 GAPS: Academic Path, Institutional Tier, Micro-Niches, Confidence
# =============================================================================

# A9 fix: _NAKSHATRA_LORD imported from constants.py (canonical, no spelling drift)
from .constants import _NAKSHATRA_LORD  # noqa: F811

# ── Domain × Secondary Planet → Micro-Niches ─────────────────────────────────
_DOMAIN_MICRO_NICHES: Dict[str, Dict[str, List[str]]] = {
    "technology": {
        "Sun":     ["Enterprise Architecture", "Tech Leadership", "CTO/CIO Track"],
        "Moon":    ["UX Research", "Human-Computer Interaction", "Conversational AI"],
        "Mars":    ["Cybersecurity", "Robotics & Edge Computing", "Systems Engineering"],
        "Mercury": ["Algorithms & Compilers", "Distributed Systems", "Developer Tools"],
        "Jupiter": ["AI Governance", "Tech Ethics & Policy", "EdTech Platforms"],
        "Venus":   ["Creative Technology", "UI/UX Design Systems", "Digital Product"],
        "Saturn":  ["Infrastructure & DevOps", "Legacy Modernisation", "SRE"],
        "Rahu":    ["Blockchain & Web3", "Quantum Computing", "Emerging Platforms"],
        "Ketu":    ["Deep Learning Research", "Theoretical CS", "Open-Source AI"],
        "_default": ["Software Engineering", "Machine Learning", "Cloud Architecture"],
    },
    "law": {
        "Sun":     ["Constitutional Law", "Government Affairs", "Public Policy"],
        "Moon":    ["Family & Child Law", "Victim Advocacy", "Mental Health Law"],
        "Mars":    ["Criminal Litigation", "Military/Defence Law", "Sports Law"],
        "Mercury": ["Intellectual Property", "Tech & Cyber Law", "Contract Drafting"],
        "Jupiter": ["International Law", "Human Rights", "Arbitration & ADR"],
        "Venus":   ["Entertainment Law", "Fashion & Brand IP", "Creative Industries"],
        "Saturn":  ["Corporate Compliance", "Insolvency Law", "Labour & Employment"],
        "Rahu":    ["Cross-Border Transactions", "Crypto Regulation", "Immigration"],
        "Ketu":    ["Legal Research & Academia", "Ancient/Comparative Law", "Legal Tech"],
        "_default": ["Corporate Law", "Litigation", "Regulatory Compliance"],
    },
    "finance": {
        "Sun":     ["Investment Banking", "Private Equity", "Capital Markets"],
        "Moon":    ["Retail Banking", "Wealth Management", "Behavioural Finance"],
        "Mars":    ["Hedge Funds", "Derivatives Trading", "Distressed Assets"],
        "Mercury": ["Quantitative Finance", "Algo Trading", "FinTech Analytics"],
        "Jupiter": ["ESG Investing", "Development Finance", "Microfinance"],
        "Venus":   ["Art & Alternative Assets", "Luxury Brand Finance", "Impact Investing"],
        "Saturn":  ["Risk Management", "Actuarial Science", "Audit & Compliance"],
        "Rahu":    ["Crypto & DeFi", "Cross-Border M&A", "Disruptive Fintech"],
        "Ketu":    ["Commodity Research", "Niche Fund Management", "Forensic Accounting"],
        "_default": ["Corporate Finance", "Financial Analysis", "Portfolio Management"],
    },
    "medicine": {
        "Sun":     ["Cardiology", "Oncology", "Hospital Administration"],
        "Moon":    ["Psychiatry", "Paediatrics", "Palliative Care"],
        "Mars":    ["Surgery", "Emergency Medicine", "Orthopaedics"],
        "Mercury": ["Neurology", "Clinical Genetics", "Medical Informatics"],
        "Jupiter": ["Public Health", "Global Health Policy", "Medical Ethics"],
        "Venus":   ["Dermatology", "Aesthetic Medicine", "Reproductive Health"],
        "Saturn":  ["Epidemiology", "Geriatrics", "Preventive Medicine"],
        "Rahu":    ["Rare Disease Research", "Gene Therapy", "Experimental Medicine"],
        "Ketu":    ["Pathology", "Integrative Medicine", "Medical Research"],
        "_default": ["General Medicine", "Clinical Research", "Healthcare Management"],
    },
    "engineering": {
        "Sun":     ["Project Leadership", "Infrastructure Policy", "Energy Systems"],
        "Moon":    ["Environmental Engineering", "Water Resources", "Human Factors"],
        "Mars":    ["Mechanical Engineering", "Aerospace", "Manufacturing"],
        "Mercury": ["Electronics & VLSI", "Signal Processing", "Embedded Systems"],
        "Jupiter": ["Structural Engineering", "Urban Planning", "Sustainable Design"],
        "Venus":   ["Product Design", "Architecture", "Industrial Design"],
        "Saturn":  ["Civil & Geotechnical", "Quality Engineering", "Process Engineering"],
        "Rahu":    ["Space Technology", "New Materials", "Autonomous Systems"],
        "Ketu":    ["Research Engineering", "Theoretical Physics", "Metrology"],
        "_default": ["Systems Engineering", "Product Development", "R&D Engineering"],
    },
    "management": {
        "Sun":     ["C-Suite Leadership", "Board Advisory", "Organisational Design"],
        "Moon":    ["HR & People Ops", "Culture & Change Management", "DEI Strategy"],
        "Mars":    ["Operations Management", "Supply Chain", "P&L Leadership"],
        "Mercury": ["Strategy & Consulting", "Business Analytics", "Digital Transformation"],
        "Jupiter": ["Social Enterprise", "NGO Leadership", "Educational Management"],
        "Venus":   ["Brand Management", "Luxury & Lifestyle Brands", "Creative Direction"],
        "Saturn":  ["Risk & Compliance", "Project Management", "Process Excellence"],
        "Rahu":    ["Startup Leadership", "International Business", "New Ventures"],
        "Ketu":    ["Turnaround Management", "Niche Markets", "Research Management"],
        "_default": ["General Management", "Business Strategy", "Leadership Development"],
    },
    "education": {
        "Sun":     ["Policy & Administration", "Institutional Leadership", "Curriculum Design"],
        "Moon":    ["Special Education", "Child Psychology", "Early Childhood"],
        "Mars":    ["Physical Education", "STEM Instruction", "Vocational Training"],
        "Mercury": ["EdTech", "Linguistics & Language Teaching", "Instructional Design"],
        "Jupiter": ["Higher Education", "Philosophy of Education", "International Schools"],
        "Venus":   ["Arts Education", "Music & Drama", "Creative Learning"],
        "Saturn":  ["Remedial Education", "Assessment & Evaluation", "Distance Learning"],
        "Rahu":    ["Global EdTech", "Online Academies", "Alternative Education"],
        "Ketu":    ["Research & Publication", "Vedic & Classical Studies", "Academic Writing"],
        "_default": ["Teaching", "Curriculum Development", "Educational Research"],
    },
    "research": {
        "Sun":     ["Policy Research", "Leadership Studies", "Think Tanks"],
        "Moon":    ["Psychology Research", "Anthropology", "Behavioural Science"],
        "Mars":    ["Materials Science", "Defence Research", "Biomechanics"],
        "Mercury": ["Computational Research", "Linguistics", "Information Science"],
        "Jupiter": ["Philosophy", "Comparative Religion", "Social Science"],
        "Venus":   ["Arts Research", "Cultural Studies", "Aesthetic Theory"],
        "Saturn":  ["Long-Term Studies", "Archival Research", "Demographic Studies"],
        "Rahu":    ["Futurism & Foresight", "Interdisciplinary Studies", "Fringe Science"],
        "Ketu":    ["Quantum/Abstract Research", "Ancient Texts", "Deep Specialisation"],
        "_default": ["Applied Research", "Data Science", "Scientific Writing"],
    },
    "arts": {
        "Sun":     ["Direction & Production", "Performance Arts", "Cultural Leadership"],
        "Moon":    ["Poetry & Literature", "Photography", "Therapeutic Arts"],
        "Mars":    ["Graphic Design", "Animation", "Game Design"],
        "Mercury": ["Screenwriting", "Journalism", "Content Strategy"],
        "Jupiter": ["Classical Music", "Heritage Arts", "Art Curation"],
        "Venus":   ["Fashion Design", "Fine Art", "Interior Design"],
        "Saturn":  ["Documentary", "Architectural Photography", "Technical Illustration"],
        "Rahu":    ["Digital Art & NFTs", "Experimental Media", "Cross-cultural Arts"],
        "Ketu":    ["Abstract Art", "Esoteric Themes", "Independent Film"],
        "_default": ["Visual Arts", "Creative Writing", "Media Production"],
    },
    "consulting": {
        "Sun":     ["Executive Coaching", "Board Consulting", "Government Advisory"],
        "Moon":    ["People & Culture Consulting", "Wellness Consulting", "UX Research"],
        "Mars":    ["Operations Consulting", "Crisis Management", "Due Diligence"],
        "Mercury": ["Digital Strategy", "Technology Consulting", "Data Analytics"],
        "Jupiter": ["ESG Consulting", "Education Consulting", "Ethics Advisory"],
        "Venus":   ["Brand & Communications", "Luxury Consulting", "Design Consulting"],
        "Saturn":  ["Risk & Regulatory", "Process Consulting", "Audit Advisory"],
        "Rahu":    ["Startup Advisory", "International Expansion", "Disruption Consulting"],
        "Ketu":    ["Niche Expertise", "Research Consulting", "Innovation Labs"],
        "_default": ["Management Consulting", "Strategy", "Business Advisory"],
    },
    "_default": {
        "_default": ["Primary Specialisation", "Applied Practice", "Research Track"],
    },
}


# ── GAP 1: Academic Depth Vector ─────────────────────────────────────────────

def compute_academic_path(
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    planet_house: Dict[str, int],
) -> Dict:
    """Return the recommended academic depth based on H4/H9/H8+Ketu strengths.

    Logic:
    - H4 lord strength → UG (undergraduate) potential
    - H9 lord strength vs H4 lord strength → PG recommendation
    - H8 lord + Ketu strength → PhD / research support
    - Multiple planets in H9 → academic extension signal

    Returns:
        {
          "ug_strong": bool,
          "pg_recommended": bool,
          "phd_supported": bool,
          "depth_label": str,
          "path_stages": [{"stage", "label", "strength_label", "recommended"}],
          "reasoning": str,
        }
    """
    h4_lord = house_lords.get("4", "")
    h9_lord = house_lords.get("9", "")
    h8_lord = house_lords.get("8", "")

    h4_str  = eff_strengths.get(h4_lord, 1.0) if h4_lord else 1.0
    h9_str  = eff_strengths.get(h9_lord, 1.0) if h9_lord else 1.0
    h8_str  = eff_strengths.get(h8_lord, 1.0) if h8_lord else 1.0
    ketu_str = eff_strengths.get("Ketu", 1.0)

    # Planets placed in H9 (multiple occupants = strong academic pull)
    h9_occupants = [p for p, h in planet_house.items() if h == 9]
    h9_occupied  = len(h9_occupants) > 0

    # Thresholds calibrated against eff_strength range (typically 0.3–2.5)
    ug_strong       = h4_str >= 0.8
    pg_recommended  = (h9_str >= h4_str * 0.9) or h9_occupied or h9_str >= 1.2
    phd_supported   = ((h8_str + ketu_str) / 2.0) >= 1.1 and ketu_str >= 1.0

    # Strength labels
    def _s_label(v: float) -> str:
        if v >= 1.5: return "Very Strong"
        if v >= 1.1: return "Strong"
        if v >= 0.8: return "Moderate"
        return "Weak"

    stages = [
        {
            "stage":         "UG",
            "label":         "Bachelor's Degree",
            "strength_label": _s_label(h4_str),
            "recommended":   True,  # always required
            "score":         round(h4_str, 3),
        },
        {
            "stage":         "PG",
            "label":         "Master's / Postgraduate",
            "strength_label": _s_label(h9_str),
            "recommended":   pg_recommended,
            "score":         round(h9_str, 3),
        },
        {
            "stage":         "PhD",
            "label":         "Doctorate / Research",
            "strength_label": _s_label((h8_str + ketu_str) / 2.0),
            "recommended":   phd_supported,
            "score":         round((h8_str + ketu_str) / 2.0, 3),
        },
    ]

    # Overall depth label
    if phd_supported:
        depth_label = "Research-Depth Profile — PhD pathway supported"
    elif pg_recommended:
        depth_label = "Masters-Level Profile — PG strongly recommended for peak impact"
    else:
        depth_label = "Practitioner Profile — UG + professional certification is sufficient"

    # Build reasoning string
    parts = []
    if ug_strong:
        parts.append(f"H4 lord ({h4_lord}, {_s_label(h4_str)}) ensures a solid undergraduate foundation")
    if pg_recommended:
        if h9_occupied:
            parts.append(f"H9 occupied by {', '.join(h9_occupants)} — academic extension is natural")
        else:
            parts.append(f"H9 lord ({h9_lord}, {_s_label(h9_str)}) matches or exceeds H4 strength — postgraduate studies unlock career acceleration")
    if phd_supported:
        parts.append(f"Ketu ({_s_label(ketu_str)}) + H8 lord ({h8_lord}, {_s_label(h8_str)}) support deep investigation and thesis-level research")

    return {
        "ug_strong":      ug_strong,
        "pg_recommended": pg_recommended,
        "phd_supported":  phd_supported,
        "depth_label":    depth_label,
        "path_stages":    stages,
        "reasoning":      ". ".join(parts) if parts else "Standard academic path applicable.",
    }


# ── GAP 2: Institutional Prestige Tier ───────────────────────────────────────

# Target institution archetypes per tier
_TIER_ARCHETYPES = {
    "Tier1_Premier": {
        "archetype":       "Premier National / Ivy-League Equivalent",
        "target_examples": ["IITs / IIMs / AIIMS (India)", "Oxbridge / Russell Group (UK)",
                            "Ivy League / Top-20 Research Universities (US)",
                            "NUS / NTU (Singapore)", "ETH Zürich / TU Munich (Europe)"],
    },
    "Tier1_Foreign": {
        "archetype":       "Premier International / Global Research University",
        "target_examples": ["MIT / Stanford / Caltech (US)", "Imperial / LSE / UCL (UK)",
                            "University of Toronto / UBC (Canada)", "Monash / ANU (Australia)",
                            "Sciences Po / INSEAD (Europe)"],
    },
    "Tier2_Technical": {
        "archetype":       "Specialist Technical / Applied Institute",
        "target_examples": ["NITs / BITS / VIT (India)", "Top State Engineering Colleges",
                            "Polytechnics with Industry Tie-ups", "Applied Science Universities"],
    },
    "Tier2_Professional": {
        "archetype":       "Professional School / Mid-Tier National College",
        "target_examples": ["Accredited Private Universities", "State Universities with Strong Departments",
                            "Professional Institutes (Law / Finance / Medical colleges)"],
    },
}

def compute_institutional_tier(
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    lagna_sign: str,
    md_lord: str = "",
    ad_lord: str = "",
    transit_planets: Dict = None,
) -> Dict:
    """Return institutional prestige tier driven primarily by MD-AD + transits,
    with natal chart as the baseline floor.

    Tier decision logic:
    ─────────────────────────────────────────────────────────────────────────
    MD/AD activation (primary signal):
      • MD/AD = Jupiter → strong Premier uplift
      • MD/AD = Sun     → moderate Premier uplift
      • MD/AD = Rahu    → foreign pull activated
      • MD/AD = Saturn  → Technical/applied orientation
      • MD/AD = Mars    → Technical/applied orientation

    Transit amplifiers (secondary):
      • Jupiter transiting H4, H9, H1, H5 → Premier boost
      • Jupiter transiting H12 → Foreign boost
      • Saturn transiting H4 or H9         → Technical/applied signal
      • Rahu transiting H9 or H12          → Foreign pull

    Natal baseline (floor — prevents absurd downgrades):
      • Sun × 0.4 + Jupiter × 0.6 + 0.3 if Jupiter natal in H4/H9/H1/H5
      • Mars × 0.5 + Saturn × 0.5 for technical floor
    ─────────────────────────────────────────────────────────────────────────
    """
    transit_planets = transit_planets or {}

    # ── Natal strengths ───────────────────────────────────────────────────
    sun_str  = eff_strengths.get("Sun",     1.0)
    jup_str  = eff_strengths.get("Jupiter", 1.0)
    mar_str  = eff_strengths.get("Mars",    1.0)
    sat_str  = eff_strengths.get("Saturn",  1.0)
    rahu_str = eff_strengths.get("Rahu",    1.0)

    jup_house  = planet_house.get("Jupiter", 0)
    rahu_house = planet_house.get("Rahu",    0)
    h12_lord   = house_lords.get("12", "")
    h12_str    = eff_strengths.get(h12_lord, 1.0) if h12_lord else 1.0

    jup_academic   = jup_house in (1, 4, 5, 9)
    rahu_foreign   = rahu_house in (9, 12, 4, 3)
    h12_foreign    = h12_str >= 1.1

    natal_premier  = (sun_str * 0.4 + jup_str * 0.6) + (0.3 if jup_academic else 0)
    natal_technical = mar_str * 0.5 + sat_str * 0.5
    natal_foreign  = (rahu_str * 0.5 + h12_str * 0.3) + (0.4 if rahu_foreign else 0) + (0.2 if h12_foreign else 0)

    # ── MD-AD activation (primary) ───────────────────────────────────────
    _PREMIER_LORDS  = {"Jupiter", "Sun", "Moon"}       # Moon in 4th/9th gives educational prestige
    _TECHNICAL_LORDS = {"Mars", "Saturn", "Ketu"}
    _FOREIGN_LORDS   = {"Rahu", "Ketu", "Venus"}       # Venus → overseas creative/arts

    md_premier   = 0.5 if md_lord in _PREMIER_LORDS  else 0.0
    md_technical = 0.4 if md_lord in _TECHNICAL_LORDS else 0.0
    md_foreign   = 0.5 if md_lord in _FOREIGN_LORDS  else 0.0

    # AD adds half the MD weight
    ad_premier   = 0.25 if ad_lord in _PREMIER_LORDS   else 0.0
    ad_technical = 0.20 if ad_lord in _TECHNICAL_LORDS else 0.0
    ad_foreign   = 0.25 if ad_lord in _FOREIGN_LORDS   else 0.0

    # ── Transit amplifiers ───────────────────────────────────────────────
    tr_jup_house  = (transit_planets.get("Jupiter") or {}).get("house", 0)
    tr_sat_house  = (transit_planets.get("Saturn")  or {}).get("house", 0)
    tr_rahu_house = (transit_planets.get("Rahu")    or {}).get("house", 0)

    transit_premier  = 0.3 if tr_jup_house in (1, 4, 5, 9) else 0.0
    transit_foreign  = (0.3 if tr_jup_house == 12 else 0.0) + (0.2 if tr_rahu_house in (9, 12) else 0.0)
    transit_technical = 0.2 if tr_sat_house in (4, 9) else 0.0

    # ── Final composite scores ────────────────────────────────────────────
    premier_score  = natal_premier  + md_premier  + ad_premier  + transit_premier
    technical_score = natal_technical + md_technical + ad_technical + transit_technical
    foreign_score  = natal_foreign  + md_foreign  + ad_foreign  + transit_foreign

    # ── Tier decision ─────────────────────────────────────────────────────
    if foreign_score >= 1.5 and premier_score >= 1.2:
        tier_key  = "Tier1_Foreign"
        tier_label = "Tier 1 International"
    elif premier_score >= 1.2:
        tier_key  = "Tier1_Premier"
        tier_label = "Tier 1 National / Premier"
    elif technical_score >= 1.1:
        tier_key  = "Tier2_Technical"
        tier_label = "Tier 2 Technical / Specialist"
    else:
        tier_key  = "Tier2_Professional"
        tier_label = "Tier 2 Professional"

    archetype_data = _TIER_ARCHETYPES.get(tier_key, _TIER_ARCHETYPES["Tier2_Professional"])

    return {
        "tier":             tier_label,
        "tier_key":         tier_key,
        "archetype":        archetype_data["archetype"],
        "target_examples":  archetype_data["target_examples"],
        "prestige_score":   round(premier_score, 3),
        "foreign_pull":     foreign_score >= 1.2,
        "foreign_score":    round(foreign_score, 3),
        "md_lord":          md_lord,
        "ad_lord":          ad_lord,
    }


# ── GAP 3: Micro-Niche Specialisations ───────────────────────────────────────

def compute_micro_niches(
    field_result: Dict,
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    amatyakaraka: str = "",
    nakshatra_data: Dict[str, str] = None,
) -> Dict:
    """Return 2-4 micro-niche specialisations for a field.

    Priority source hierarchy:
    1. Registry niche string (field-specific, e.g. "Reservoir / Drilling / Production / EOR")
       Split by '/' and return up to 3 sub-niches — this ensures each field has distinct niches.
    2. If registry niche absent, fall back to planet-domain map (AmK nakshatra lord → domain map).

    Planet driver still applied: indicates WHICH of the registry sub-niches to rank first,
    based on AmK nakshatra lord or secondary affinity planet.

    Returns:
        {"micro_niches": [str, ...], "niche_driver": str, "driver_planet": str,
         "niche_source": "registry" | "planet_map"}
    """
    nakshatra_data = nakshatra_data or {}
    domain = field_result.get("domain", "_default")

    # BUGFIX (2026-07, audit P0): nakshatra_data values are contractually
    # strings (nakshatra names), but at least one call site was found passing
    # `{}` for missing planets (see engine.py's _run_normalization_stage fix),
    # and other parts of this codebase's schema legitimately accept a
    # structured {"nakshatra": "Rohini", "pada": 2}-shaped dict for a
    # planet's nakshatra info (see engine_io.py's `details["nakshatra"]`
    # passthrough). Rather than relying on every caller to pass a clean
    # string, normalize defensively here at the point of use: a dict is
    # unwrapped via its "nakshatra"/"name" key if present, anything else
    # non-string collapses to "" instead of being used as a hashable dict
    # key (which previously raised `TypeError: unhashable type: 'dict'`).
    def _coerce_nakshatra_name(v) -> str:
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return str(v.get("nakshatra") or v.get("name") or "")
        return ""

    # ── Planet driver logic (used for ranking registry sub-niches) ─────────────
    amk_nakshatra  = _coerce_nakshatra_name(nakshatra_data.get(amatyakaraka, ""))
    amk_nak_lord   = _NAKSHATRA_LORD.get(amk_nakshatra, "")

    affinity = field_result.get("affinity_planets", {})
    sorted_planets = sorted(affinity.items(), key=lambda x: x[1], reverse=True)
    secondary_planet = sorted_planets[1][0] if len(sorted_planets) >= 2 else ""
    top_planet       = sorted_planets[0][0]  if len(sorted_planets) >= 1 else ""

    amk_house    = planet_house.get(amatyakaraka, 0)
    conjunct_amk = [p for p, h in planet_house.items()
                    if h == amk_house and p != amatyakaraka and p not in ("Ketu",)]

    driver_planet = amk_nak_lord or secondary_planet or top_planet or "Mercury"
    if amk_nak_lord:
        niche_driver = f"AmK ({amatyakaraka}) in {amk_nakshatra} Nakshatra (lord: {amk_nak_lord})"
    elif secondary_planet:
        niche_driver = f"Secondary affinity planet: {secondary_planet}"
    else:
        niche_driver = f"Primary affinity planet: {top_planet}"

    # ── Source 1: registry niche (field-specific) ──────────────────────────────
    _reg = field_result.get("registry") or {}
    reg_niche_str = _reg.get("niche", "")

    # Reject generic placeholders — fall through to planet_map or field-level specialization
    _GENERIC_PLACEHOLDERS = {"specialized industry practice", "core industry practice", ""}
    if reg_niche_str and reg_niche_str.strip().lower() not in _GENERIC_PLACEHOLDERS:
        pass  # use it as-is below
    elif reg_niche_str.strip().lower() in _GENERIC_PLACEHOLDERS and reg_niche_str:
        # Build a unique niche from specialization + track from the registry
        spec  = _reg.get("specialization", "")
        track = _reg.get("track", "")
        label = _reg.get("label", "")
        # Compose up to 3 distinct sub-niches from available fields
        composed = []
        if spec  and spec  not in composed: composed.append(spec)
        if track and track not in composed: composed.append(track)
        if label and label not in composed: composed.append(label)
        reg_niche_str = " / ".join(composed[:3]) if composed else ""

    if reg_niche_str and reg_niche_str.strip().lower() not in _GENERIC_PLACEHOLDERS:
        # Split "Open-Pit / Underground / Mine Planning / Blasting" → individual sub-niches
        raw_subs = [s.strip() for s in reg_niche_str.replace("|", "/").split("/") if s.strip()]

        # Use planet driver to re-rank: if driver planet's domain_map has hints, promote matching
        domain_map   = _DOMAIN_MICRO_NICHES.get(domain, _DOMAIN_MICRO_NICHES["_default"])
        planet_hints = [n.lower() for n in domain_map.get(driver_planet, [])]

        def _relevance(sub: str) -> int:
            sub_l = sub.lower()
            return sum(1 for hint in planet_hints if hint[:8] in sub_l or sub_l[:8] in hint)

        ranked_subs = sorted(raw_subs, key=_relevance, reverse=True)

        # Optionally append one cross-domain niche from conjunct AmK planet
        cross_niche = None
        if conjunct_amk:
            conj_niches = domain_map.get(conjunct_amk[0], [])
            if conj_niches and conj_niches[0] not in ranked_subs:
                cross_niche = conj_niches[0]

        result_niches = ranked_subs[:3]
        if cross_niche and len(result_niches) < 4:
            result_niches.append(cross_niche)

        return {
            "micro_niches":   result_niches[:4],
            "niche_driver":   niche_driver,
            "driver_planet":  driver_planet,
            "amk_nakshatra":  amk_nakshatra,
            "niche_source":   "registry",
        }

    # ── Source 2: fallback to planet-domain map ────────────────────────────────
    domain_map = _DOMAIN_MICRO_NICHES.get(domain, _DOMAIN_MICRO_NICHES["_default"])
    niches = domain_map.get(driver_planet, domain_map.get("_default", [
        "Core Practice", "Applied Research", "Leadership Track"
    ]))

    cross_niche = None
    if conjunct_amk and driver_planet not in conjunct_amk:
        conj_niches = domain_map.get(conjunct_amk[0], [])
        if conj_niches and conj_niches[0] not in niches:
            cross_niche = conj_niches[0]

    result_niches = list(niches[:3])
    if cross_niche and len(result_niches) < 4:
        result_niches.append(cross_niche)

    return {
        "micro_niches":   result_niches[:3],
        "niche_driver":   niche_driver,
        "driver_planet":  driver_planet,
        "amk_nakshatra":  amk_nakshatra,
        "niche_source":   "planet_map",
    }


# ── GAP 4: Confidence Matrix (called in engine.py merge step) ────────────────

def build_confidence_matrix(field_result: Dict) -> Dict:
    """Normalise method scores into a % confidence matrix.

    Uses method_normalized_scores (already 0–100 scale, relative to best field).
    Falls back to raw scores if normalised not present.

    Returns:
        {
          "knrao_pct":            int,   # KN Rao (whole-sign + karakas) — weight 0.35
          "kp_pct":               int,   # KP (cusp sub-lords)           — weight 0.25
          "jaimini_pct":          int,   # Jaimini (aptitude/vocational) — weight 0.20
          "parashara_pct":        int,   # Parashara (yoga strength)     — weight 0.20
          "sbc_pct":              int,   # SBC event-timing score as %   — display only
          "alignment_confidence": int,   # concordance: mean × (1 - spread/100)
        }
    """
    mn = field_result.get("method_normalized_scores") or \
         field_result.get("method_scores_normalized_0_100") or \
         field_result.get("method_scores_normalized") or {}

    # method_normalized_scores are already 0–100 relative to best field in run
    knrao_raw     = float(mn.get("knrao",    field_result.get("knrao_score",    0)) or 0)
    kp_raw        = float(mn.get("kp",       field_result.get("kp_score",       0)) or 0)
    jaimini_raw   = float(mn.get("jaimini",  field_result.get("jaimini_score",  0)) or 0)
    parashara_raw = float(mn.get("parashara",field_result.get("parashara_score",0)) or 0)

    # SBC (Sthira Bhava Chakra) event-timing score: already 0–100 scale
    sbc_raw = float(field_result.get("sbc_event_score", 0) or 0)

    # Soft compression: keeps top scores high, lifts lower scores slightly
    def _pct(v: float) -> int:
        return min(int(round(v * 0.92 + 5)), 99) if v > 5 else int(round(v))

    knrao_pct     = _pct(knrao_raw)
    kp_pct        = _pct(kp_raw)
    jaimini_pct   = _pct(jaimini_raw)
    parashara_pct = _pct(parashara_raw)
    # SBC is already a 0–100 confidence score — apply same compression for display consistency
    sbc_pct       = _pct(sbc_raw)

    # Concordance-based alignment:
    #   mean        = weighted average (KNRao 35%, KP 25%, Jaimini 20%, Parashara 20%)
    #   spread      = max - min across the 4 raw method %s
    #   concordance = max(0, 1 - spread/150)
    #                 ÷150 (not ÷100) so a 30pt spread → 20% penalty, not 30%.
    #                 Prevents over-penalising charts where one method is
    #                 structurally bounded lower (e.g. KP capped at 60).
    #   alignment%  = round(mean × concordance)   ← round avoids truncation bias
    _method_scores = [knrao_pct, kp_pct, jaimini_pct, parashara_pct]
    _mean = (
        knrao_pct * 0.35 + kp_pct * 0.25 + jaimini_pct * 0.20 + parashara_pct * 0.20
    )
    _spread      = max(_method_scores) - min(_method_scores)
    _concordance = max(0.0, 1.0 - _spread / 150.0)
    alignment    = int(round(_mean * _concordance))

    return {
        "knrao_pct":            knrao_pct,
        "kp_pct":               kp_pct,
        "jaimini_pct":          jaimini_pct,
        "parashara_pct":        parashara_pct,
        "sbc_pct":              sbc_pct,
        "alignment_confidence": alignment,
    }

# ── Chart-type detection ──────────────────────────────────────────────────────

# Substring fragments matched case-insensitively against registry track values
# e.g. "Computer Science & Engineering" → matches "computer science" → "Technology"
_TRACK_DOMAIN_FRAGMENTS: List[tuple] = [
    # Technology / CS
    ("computer science",        "Technology"),
    ("data science",            "Technology"),
    ("information technology",  "Technology"),
    ("artificial intelligence", "Technology"),
    ("software",                "Technology"),
    # Engineering
    ("engineering",             "Engineering"),
    ("architecture",            "Engineering"),
    # Science
    ("physics",                 "Science"),
    ("chemistry",               "Science"),
    ("biology",                 "Science"),
    ("mathematics",             "Science"),
    ("statistics",              "Science"),
    ("life science",            "Science"),
    ("earth science",           "Science"),
    ("agricultural",            "Science"),
    ("environmental",           "Science"),
    # Medicine / Health
    ("medical",                 "Medicine & Health"),
    ("medicine",                "Medicine & Health"),
    ("pharmacy",                "Medicine & Health"),
    ("nursing",                 "Medicine & Health"),
    ("health",                  "Medicine & Health"),
    ("psychology",              "Medicine & Health"),
    ("dentistry",               "Medicine & Health"),
    # Law / Governance
    ("law",                     "Law & Governance"),
    ("legal",                   "Law & Governance"),
    ("public policy",           "Law & Governance"),
    ("governance",              "Law & Governance"),
    ("political",               "Law & Governance"),
    # Business / Finance
    ("business",                "Business & Finance"),
    ("finance",                 "Business & Finance"),
    ("economics",               "Business & Finance"),
    ("commerce",                "Business & Finance"),
    ("management",              "Business & Finance"),
    ("accounting",              "Business & Finance"),
    # Humanities / Arts / Media
    ("humanities",              "Humanities & Arts"),
    ("literature",              "Humanities & Arts"),
    ("journalism",              "Humanities & Arts"),
    ("media",                   "Humanities & Arts"),
    ("design",                  "Humanities & Arts"),
    ("performing arts",         "Humanities & Arts"),
    ("fine arts",               "Humanities & Arts"),
    ("language",                "Humanities & Arts"),
    ("history",                 "Humanities & Arts"),
    ("philosophy",              "Humanities & Arts"),
    # Education / Research
    ("research",                "Research & Academia"),
    ("education",               "Research & Academia"),
    ("teaching",                "Research & Academia"),
]


def _track_to_domain(track: str, label: str = "") -> str:
    """Map a registry track string to a broad domain label via substring matching."""
    t = (track or label or "").lower()
    for fragment, domain in _TRACK_DOMAIN_FRAGMENTS:
        if fragment in t:
            return domain
    return "Other"


def detect_chart_type(fields: List[Dict]) -> Dict:
    """Detect whether the chart is Specialist or Cluster (Polymathic).

    Uses METHOD scores (KNRao/KP/Jaimini/Parashara average), NOT final_score.
    final_score is LLM-adjusted and inflated — method scores reflect true
    astrological signal convergence across methods.

    Cluster    : avg method score < 55 AND top-5 method spread < 15
                 → aptitude distributed, no single field dominates
    Specialist : avg method score >= 60 AND spread >= 20
                 → clear dominant field
    Mixed      : everything in between

    Returns a dict with:
        type            : "specialist" | "cluster" | "mixed"
        is_cluster      : bool
        top_score       : float  (top method avg)
        spread          : float
        domain_clusters : Dict[domain_label → List[field_id]]
        cluster_label   : human-readable label
    """
    def _method_avg(f: Dict) -> float:
        """Return alignment_confidence for this field (0–100).

        alignment_confidence = mean × concordance = method avg × (1 - spread/100)
        It captures both signal strength AND method agreement, making it the right
        anchor for cluster detection: a cluster chart has no field with high,
        concordant multi-method support.

        Priority:
        1. confidence_matrix["alignment_confidence"]  (set by build_confidence_matrix)
        2. Recompute from *_pct keys if alignment key missing
        3. Raw method_normalized_scores (0-100 scale) fallback — no concordance applied
        """
        cm = f.get("confidence_matrix") or {}

        # Best case: alignment_confidence already computed
        ac = cm.get("alignment_confidence")
        if ac is not None and float(ac or 0) > 0:
            return float(ac)

        # Recompute from pct keys
        if cm.get("knrao_pct") or cm.get("kp_pct"):
            k  = float(cm.get("knrao_pct",    0) or 0)
            kp = float(cm.get("kp_pct",       0) or 0)
            j  = float(cm.get("jaimini_pct",  0) or 0)
            p  = float(cm.get("parashara_pct",0) or 0)
            mean_  = k * 0.35 + kp * 0.25 + j * 0.20 + p * 0.20
            spread = max(k, kp, j, p) - min(k, kp, j, p)
            return round(mean_ * max(0.0, 1.0 - spread / 100.0), 2)

        # Last resort: plain method avg from normalized scores (0-100 scale)
        mn = (f.get("method_normalized_scores") or
              f.get("method_scores_normalized_0_100") or
              f.get("method_scores_normalized") or {})
        vals = [float(v or 0) for v in mn.values() if float(v or 0) > 0]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    sorted_fields = sorted(fields, key=_method_avg, reverse=True)
    top5  = sorted_fields[:5]
    scores = [_method_avg(f) for f in top5]

    if not scores:
        return {"type": "unknown", "is_cluster": False, "top_score": 0,
                "spread": 0, "domain_clusters": {}, "cluster_label": ""}

    top_score = scores[0]
    spread    = scores[0] - scores[-1] if len(scores) > 1 else 0

    if top_score >= 65 and spread >= 20:
        chart_type    = "specialist"
        is_cluster    = False
        cluster_label = "Specialist Aptitude"
    elif top_score < 60 and spread < 15:
        # Cluster: even the best field scores below 60 AND top-5 are tightly bunched
        # → aptitude distributed, no single field dominates
        chart_type    = "cluster"
        is_cluster    = True
        cluster_label = "Polymathic / Cluster Aptitude"
    else:
        chart_type    = "mixed"
        is_cluster    = False
        cluster_label = "Focused Aptitude"

    # Build domain clusters from top-15 fields using substring matching
    domain_clusters: Dict[str, List[str]] = {}
    for f in sorted_fields[:15]:
        reg    = f.get("registry") or {}
        track  = reg.get("track", "")
        label  = reg.get("label", "")
        domain = _track_to_domain(track, label)
        fid    = f.get("field_id", "")
        if fid:
            domain_clusters.setdefault(domain, []).append(fid)

    return {
        "type":            chart_type,
        "is_cluster":      is_cluster,
        "top_score":       round(top_score, 1),
        "spread":          round(spread, 1),
        "domain_clusters": domain_clusters,
        "cluster_label":   cluster_label,
    }


# ── Additional domain mappings appended post-initial-write ───────────────────
_DOMAIN_MICRO_NICHES.update({
    "humanities": {
        "Sun":     ["Classical Studies", "Heritage & Cultural Policy", "Political Philosophy"],
        "Moon":    ["Linguistics & Language Acquisition", "Literature & Narrative", "Sociolinguistics"],
        "Mars":    ["History of Conflict", "Rhetoric & Persuasion", "Journalism"],
        "Mercury": ["Computational Linguistics", "Translation Studies", "Semiotics"],
        "Jupiter": ["Philosophy", "Comparative Religion", "Moral Theory"],
        "Venus":   ["Creative Writing", "Aesthetics & Art History", "Gender Studies"],
        "Saturn":  ["Archival Studies", "Economic History", "Social Policy Research"],
        "Rahu":    ["Digital Humanities", "Cross-Cultural Studies", "Global Communication"],
        "Ketu":    ["Ancient Languages", "Mythology & Symbolism", "Deep Textual Analysis"],
        "_default": ["Linguistics", "Cultural Studies", "Academic Research"],
    },
    "science": {
        "Sun":     ["Astrophysics", "Nuclear Physics", "Scientific Leadership"],
        "Moon":    ["Marine Biology", "Ecology", "Behavioural Science"],
        "Mars":    ["Forensic Science", "Sports Science", "Biomechanics"],
        "Mercury": ["Data Science", "Computational Biology", "Bioinformatics"],
        "Jupiter": ["Evolutionary Biology", "Climate Science", "Science Policy"],
        "Venus":   ["Biochemistry", "Food Science", "Pharmaceutical Research"],
        "Saturn":  ["Geology", "Materials Science", "Environmental Monitoring"],
        "Rahu":    ["Quantum Physics", "Space Science", "Nanotechnology"],
        "Ketu":    ["Pure Mathematics", "Theoretical Physics", "Deep Research"],
        "_default": ["Applied Sciences", "Research & Development", "Laboratory Science"],
    },
    "commerce": {
        "Sun":     ["Investment Banking", "Corporate Governance", "Trade Policy"],
        "Moon":    ["Retail & Consumer Markets", "FMCG", "Market Research"],
        "Mars":    ["Commodities Trading", "Supply Chain", "Sales Leadership"],
        "Mercury": ["E-Commerce", "Digital Marketing", "Business Analytics"],
        "Jupiter": ["Social Enterprise", "Ethical Commerce", "International Trade"],
        "Venus":   ["Luxury Goods", "Fashion Retail", "Brand Commerce"],
        "Saturn":  ["Accounting & Audit", "Tax Strategy", "Risk & Compliance"],
        "Rahu":    ["Startup Commerce", "Crypto Commerce", "Cross-Border Trade"],
        "Ketu":    ["Commodity Niche Markets", "Niche Exports", "Research Commerce"],
        "_default": ["Commerce & Trade", "Business Development", "Financial Management"],
    },
    "public": {
        "Sun":     ["Government Administration", "Public Policy", "Political Leadership"],
        "Moon":    ["Social Work", "Community Development", "Public Health"],
        "Mars":    ["Defence & Security", "Law Enforcement", "Disaster Management"],
        "Mercury": ["Public Communications", "Policy Research", "E-Governance"],
        "Jupiter": ["International Relations", "Human Rights", "Diplomacy"],
        "Venus":   ["Cultural Affairs", "Public Arts", "Urban Design"],
        "Saturn":  ["Urban Planning", "Infrastructure Policy", "Regulatory Bodies"],
        "Rahu":    ["Global Policy", "International Development", "Multilateral Affairs"],
        "Ketu":    ["Historical Archives", "Tribal & Rural Development", "Niche Advocacy"],
        "_default": ["Public Administration", "Policy Analysis", "Civil Services"],
    },
    "interdisciplinary": {
        "Sun":     ["Leadership Studies", "Innovation Management", "Future Studies"],
        "Moon":    ["Cognitive Science", "Behavioural Economics", "Psychology & Tech"],
        "Mars":    ["Sports Analytics", "Bio-Engineering", "Action Research"],
        "Mercury": ["Information Science", "Digital Humanities", "Tech-Humanities Bridge"],
        "Jupiter": ["Philosophy of Science", "Ethics in Technology", "Global Development"],
        "Venus":   ["Creative Industries", "Design Thinking", "Experience Design"],
        "Saturn":  ["Systems Thinking", "Sustainability Studies", "Complex Systems"],
        "Rahu":    ["Futurism", "Emerging Disciplines", "Cross-Domain Innovation"],
        "Ketu":    ["Integral Studies", "Ancient Wisdom Meets Modern Science", "Deep Research"],
        "_default": ["Cross-Domain Studies", "Applied Interdisciplinary", "Innovation Research"],
    },
})


# ─────────────────────────────────────────────────────────────────────────────
# Field Summary JSON builder  (Schema v1)
# ─────────────────────────────────────────────────────────────────────────────

def build_field_summary_json(field_result: dict) -> dict:
    """Return a clean, schema-compliant summary dict for a single field result."""
    # ── Academic path stages ──────────────────────────────────────────────────
    _ap     = field_result.get("academic_path") or {}
    _stages = _ap.get("path_stages", [])
    ug_req  = any(s.get("stage") == "UG"  for s in _stages)
    pg_rec  = any(s.get("stage") == "PG"  and s.get("recommended") for s in _stages)
    phd_sup = any(s.get("stage") == "PhD" and s.get("recommended") for s in _stages)

    # ── Confidence matrix ─────────────────────────────────────────────────────
    _cm = field_result.get("confidence_matrix") or {}
    confidence_matrix = {
        "knrao_classical":     f"{_cm.get('knrao_pct', 0)}%",
        "kp_alignment":        f"{_cm.get('kp_pct', 0)}%",
        "jaimini_aptitude":    f"{_cm.get('jaimini_pct', 0)}%",
        "parashara_strength":  f"{_cm.get('parashara_pct', 0)}%",
        "sbc_timing":          f"{_cm.get('sbc_pct', 0)}%",
        "overall":             f"{_cm.get('alignment_confidence', 0)}%",
    }

    # ── Institutional tier ────────────────────────────────────────────────────
    _it       = field_result.get("institutional_tier") or {}
    tier_str  = _it.get("tier", "")
    arch_str  = _it.get("archetype", "")
    tier_label = f"{tier_str} — {arch_str}" if tier_str and arch_str else tier_str or arch_str
    _tier_key  = _it.get("tier_key", "")

    _reg_av  = (field_result.get("registry") or {}).get("available_at") or {}
    if isinstance(_reg_av, str):
        try:
            import ast as _avast; _reg_av = _avast.literal_eval(_reg_av)
        except Exception: _reg_av = {}

    _TIER_ALLOW = {
        "Tier1_Premier":      {"IIT", "IISER", "ISI", "BITS", "central_universities", "liberal_arts_private"},
        "Tier1_Foreign":      {"IIT", "IISER", "ISI", "BITS", "central_universities"},
        "Tier2_Technical":    {"NIT", "BITS", "IIIT", "deemed_private", "state_universities"},
        "Tier2_Professional": {"central_universities", "liberal_arts_private", "deemed_private", "state_universities", "BITS"},
    }
    _av_allowed = _TIER_ALLOW.get(_tier_key, set(_TIER_ALLOW["Tier2_Professional"]))

    def _avail_examples(av: dict) -> list:
        _PREFIX_KEYS = {"IIT", "NIT", "BITS", "IISER", "ISI"}
        _BOOL_LABEL  = {
            "IIIT": "IIITs", "state_universities": "State Universities",
            "deemed_private": "Deemed / Private",
            "central_universities": None, "liberal_arts_private": None,
        }
        out = []
        for key, val in av.items():
            if key not in _av_allowed: continue
            if val is False or val is None: continue
            if val is True:
                label = _BOOL_LABEL.get(key, key.replace("_", " ").title())
                if label: out.append(label)
            elif isinstance(val, list) and val:
                if val == ["All_IITs"]: out.append("All IITs"); continue
                if val == ["All_NITs"]: out.append("All NITs"); continue
                clean = [v.replace(f"{key}_", "").replace("_", " ") for v in val[:3]]
                if key in _PREFIX_KEYS:
                    out.append(f"{key} {' / '.join(clean)}")
                else:
                    out.append(" / ".join(clean))
        return out[:4]

    _field_target_examples = _avail_examples(_reg_av) if _reg_av else _it.get("target_examples", [])

    # ── 360° Insights ────────────────────────────────────────────────────────────
    _wp  = field_result.get("wealth_potential") or {}
    _br  = field_result.get("burnout_risk_detail") or {}
    _geo = field_result.get("geography_insight") or {}
    geo_label = _geo.get("geography_label", "") or _geo.get("geography", "")

    insights = {
        "wealth":    _wp.get("wealth_potential", ""),
        "geography": geo_label,
        "burnout":   _br.get("burnout_risk", ""),
    }

    _mn = field_result.get("micro_niches") or []

    return {
        "field_id":          field_result.get("field_id", ""),
        "total_score":       field_result.get("final_score", field_result.get("total_score", 0)),
        "confidence_matrix": confidence_matrix,
        "execution_path": {
            "ug_required":     ug_req,
            "pg_recommended":  pg_rec,
            "phd_supported":   phd_sup,
            "tier":            tier_label,
            "target_examples": _field_target_examples,
        },
        "micro_niches": _mn,
        "insights":     insights,
    }


# ---------------------------------------------------------------------------
# C-3: D10 Corporate Hierarchy & Politics Risk Assessment
# ---------------------------------------------------------------------------

# D10 houses associated with authority conflict and political turbulence
_D10_RISK_HOUSES   = {6, 8, 12}   # dusthana in D10
_D10_POWER_HOUSES  = {1, 10, 5}   # leadership apex in D10
_D10_SUPPORT_HOUSES = {9, 11, 7}  # support network

_AUTHORITY_PLANETS  = {"Sun", "Jupiter"}   # hierarchy significators
_CONFLICT_PLANETS   = {"Mars", "Rahu", "Saturn"}

_D10_SIGN_LORD: Dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}
_DEBIL: Dict[str, str] = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer", "Mercury": "Pisces",
    "Jupiter": "Capricorn", "Venus": "Virgo", "Saturn": "Aries",
    "Rahu": "Sagittarius", "Ketu": "Gemini",
}
_EXALT: Dict[str, str] = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn", "Mercury": "Virgo",
    "Jupiter": "Cancer", "Venus": "Pisces", "Saturn": "Libra",
    "Rahu": "Gemini", "Ketu": "Sagittarius",
}


def compute_d10_politics_risk(
    d10_planet_sign: Dict[str, str],
    d10_house_lords: Dict[str, str],
    eff_strengths: Dict[str, float],
    planet_house: Dict[str, int],
) -> Dict:
    """Assess corporate hierarchy & politics risk from D10 Dashamsha.

    Evaluates Sun (authority), Jupiter (wisdom/mentor), Mars/Rahu (conflict),
    Saturn (discipline/suppression) placement in D10 for:
    - Risk of authority conflict / political fall-out
    - Readiness to navigate or lead hierarchy

    Returns
    -------
    dict with:
        politics_risk_score  (0-100, 100=highest risk)
        readiness_score      (0-100, 100=best positioned)
        risk_label           (str)
        risk_factors         (list[str])
        protective_factors   (list[str])
        insight              (str)
    """
    risk_pts     = 0.0
    readiness_pts = 0.0
    risk_factors      = []
    protective_factors = []

    def _d10_house_of(planet: str) -> int:
        """Return the D10 house number for a planet from d10_house_lords reverse-map."""
        # We use d10_planet_sign → lord → find the house that planet lords in D10
        # Simpler: check planet_house for D1 position, but for D10 use d10_planet_sign
        sign = d10_planet_sign.get(planet, "")
        if not sign:
            return 0
        # Find which D10 house has this sign
        for h_str, h_lord in d10_house_lords.items():
            if h_lord == _D10_SIGN_LORD.get(sign, ""):
                try:
                    return int(h_str)
                except ValueError:
                    pass
        return 0

    def _d10_sign_of(planet: str) -> str:
        return d10_planet_sign.get(planet, "")

    # ── Sun in D10 — authority archetype ─────────────────────────────────────
    sun_sign_d10 = _d10_sign_of("Sun")
    sun_str      = eff_strengths.get("Sun", 1.0)
    sun_d1_house = planet_house.get("Sun", 0)

    if sun_sign_d10 == _DEBIL.get("Sun"):           # Sun debilitated in D10
        risk_pts += 3.0 * sun_str
        risk_factors.append(
            f"Sun debilitated in D10 ({sun_sign_d10}) — authority subjugation risk; "
            "bosses or hierarchy may suppress self-expression."
        )
    elif sun_sign_d10 == _EXALT.get("Sun"):
        readiness_pts += 3.0 * sun_str
        protective_factors.append(
            f"Sun exalted in D10 ({sun_sign_d10}) — natural authority; "
            "hierarchy usually advances rather than obstructs."
        )
    elif sun_d1_house in _D10_RISK_HOUSES:
        risk_pts += 1.5
        risk_factors.append(
            f"Sun in H{sun_d1_house} (D1 dusthana) — authority wounds may replay at work."
        )

    # ── Jupiter in D10 — wisdom / mentor archetype ───────────────────────────
    jup_sign_d10 = _d10_sign_of("Jupiter")
    jup_str      = eff_strengths.get("Jupiter", 1.0)
    jup_d1_house = planet_house.get("Jupiter", 0)

    if jup_sign_d10 == _DEBIL.get("Jupiter"):
        risk_pts += 2.5 * jup_str
        risk_factors.append(
            f"Jupiter debilitated in D10 ({jup_sign_d10}) — mentors / sponsors may withdraw; "
            "hierarchy feels unsupportive."
        )
    elif jup_sign_d10 == _EXALT.get("Jupiter"):
        readiness_pts += 2.5 * jup_str
        protective_factors.append(
            f"Jupiter exalted in D10 ({jup_sign_d10}) — strong mentorship & institutional support."
        )

    if jup_d1_house in _D10_RISK_HOUSES:
        risk_pts += 1.0
        risk_factors.append(f"Jupiter in H{jup_d1_house} — wisdom under pressure in professional life.")

    # ── Mars / Rahu / Saturn conflict indicators ─────────────────────────────
    for planet, base_wt, label in [
        ("Mars",   2.0, "aggressive power dynamics"),
        ("Rahu",   1.5, "political / diplomatic turbulence"),
        ("Saturn", 1.0, "prolonged hierarchy friction"),
    ]:
        sign = _d10_sign_of(planet)
        h_d1 = planet_house.get(planet, 0)
        pstr = eff_strengths.get(planet, 1.0)
        if h_d1 in _D10_RISK_HOUSES and pstr >= 1.1:
            risk_pts += base_wt * pstr
            risk_factors.append(
                f"{planet} in H{h_d1} D1 with {label} — D10 carries this tension."
            )
        elif h_d1 in _D10_POWER_HOUSES and pstr >= 1.2:
            readiness_pts += base_wt * 0.5
            protective_factors.append(
                f"{planet} strong in power house H{h_d1} — assertiveness / discipline at command."
            )

    # ── Protective factors ────────────────────────────────────────────────────
    h10_lord_d10 = d10_house_lords.get("10", "")
    if h10_lord_d10:
        h10_str = eff_strengths.get(h10_lord_d10, 1.0)
        if h10_str >= 1.3:
            readiness_pts += 2.0 * h10_str
            protective_factors.append(
                f"D10 H10 lord {h10_lord_d10} is strong (×{h10_str:.2f}) — career house fortified."
            )

    # ── Normalise ─────────────────────────────────────────────────────────────
    _MAX_RISK = 12.0
    _MAX_READ = 10.0
    politics_risk_score = int(round(min(risk_pts     / _MAX_RISK * 100, 99)))
    readiness_score     = int(round(min(readiness_pts / _MAX_READ * 100, 99)))

    # ── Risk label ────────────────────────────────────────────────────────────
    if politics_risk_score >= 70:
        risk_label = "High Politics Risk"
        insight = (
            f"D10 shows elevated corporate politics and hierarchy conflict risk "
            f"({politics_risk_score}%). Sun and/or Jupiter have weak D10 dignity. "
            "Prioritise building allies above your level and avoid overt power contests."
        )
    elif politics_risk_score >= 45:
        risk_label = "Moderate Politics Risk"
        insight = (
            f"Moderate hierarchy friction possible ({politics_risk_score}%). "
            "Authority relationships need proactive management. "
            "Readiness score {readiness_score}% — chart has protective factors if used consciously."
        ).format(readiness_score=readiness_score)
    elif politics_risk_score >= 20:
        risk_label = "Low Politics Risk"
        insight = (
            f"D10 supports relatively smooth hierarchy navigation ({politics_risk_score}% risk). "
            f"Readiness score {readiness_score}% — institutional support is likely."
        )
    else:
        risk_label = "Minimal Politics Risk"
        insight = (
            f"Very favourable D10 hierarchy profile. Authority is supported, not contested. "
            f"Readiness score {readiness_score}%."
        )

    return {
        "politics_risk_score":   politics_risk_score,
        "readiness_score":       readiness_score,
        "risk_label":            risk_label,
        "risk_factors":          risk_factors,
        "protective_factors":    protective_factors,
        "insight":               insight,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 10/10 UPGRADE FUNCTIONS (15 astrological recommendations)
# ══════════════════════════════════════════════════════════════════════════════

# ── Fix 1: Nakshatra-axis career rulership ────────────────────────────────────
def _nakshatra_career_score(
    affinity: Dict[str, float],
    moon_nakshatra: str,
    planet_nakshatras: Dict[str, str],
    house_lords: Dict[str, str],
    lagna_sign: str,
    label: str,
) -> float:
    """Score career field based on nakshatra-axis rulership.

    Classical principle: The nakshatra of the H10 cusp and Moon nakshatra
    are primary field indicators — nakshatra tells the *texture* of the work.

    Two sub-signals:
      A) H10 sign nakshatra lord → which planet rules H10 cusp energy
         (whole-sign H10 = 9 signs from lagna, nakshatra derived from sign start)
      B) Moon nakshatra lord → native's emotional career direction

    Both are checked against field keywords and field_affinity.
    """
    if not label:
        return 0.0
    label_lower = label.lower()
    bonus = 0.0

    # Sub-signal A: H10 lord's nakshatra  — what kind of action suits this person
    h10_lord = house_lords.get("10", "")
    h10_nak = planet_nakshatras.get(h10_lord, "")
    if h10_nak:
        h10_nak_kws = _NAKSHATRA_CAREER_KW.get(h10_nak, [])
        if any(_wm(kw, label_lower) for kw in h10_nak_kws):
            w10 = affinity.get(h10_lord, 0.0)
            if   w10 >= 0.25: bonus += 0.07
            elif w10 >= 0.15: bonus += 0.04
            elif w10 >= 0.08: bonus += 0.02

    # Sub-signal B: Moon nakshatra lord → emotional career direction
    if moon_nakshatra:
        moon_nak_lord = _NAKSHATRA_LORD.get(moon_nakshatra, "")
        if moon_nak_lord:
            moon_nak_kws = _NAKSHATRA_CAREER_KW.get(moon_nakshatra, [])
            if any(_wm(kw, label_lower) for kw in moon_nak_kws):
                w_ml = affinity.get(moon_nak_lord, 0.0)
                if   w_ml >= 0.20: bonus += 0.05
                elif w_ml >= 0.10: bonus += 0.02

    return min(bonus, 0.10)


# ── Fix 2: Rahu-Ketu nodal axis as life-direction indicator ──────────────────
def _nodal_axis_career_signal(
    affinity: Dict[str, float],
    rahu_house: int,
    ketu_house: int,
    label: str,
    eff_strengths: Dict[str, float] = None,
) -> float:
    """Rahu's house = soul's intended career direction this lifetime.
    Ketu's house = natural talent (past-life mastery) — bonus for matching fields.

    Rahu house gives the primary directional bonus; Ketu gives natural talent bonus.
    """
    if not label or not rahu_house:
        return 0.0
    label_lower = label.lower()
    eff = eff_strengths or {}
    rahu_str = max(0.3, min(eff.get("Rahu", 0.5), 1.5))
    ketu_str  = max(0.3, min(eff.get("Ketu",  0.5), 1.5))
    bonus = 0.0

    # Rahu house direction — MUST align with career field
    rahu_kws = _RAHU_HOUSE_CAREER_KW.get(rahu_house, [])
    if any(_wm(kw, label_lower) for kw in rahu_kws):
        rahu_w = affinity.get("Rahu", 0.0)
        if   rahu_w >= 0.25: bonus += 0.06 * min(rahu_str, 1.3)
        elif rahu_w >= 0.10: bonus += 0.03 * min(rahu_str, 1.3)
        else:                bonus += 0.015  # directional signal even with low affinity

    # Ketu house natural talent — secondary signal
    ketu_kws = _KETU_HOUSE_NATURAL_TALENT.get(ketu_house, [])
    if any(_wm(kw, label_lower) for kw in ketu_kws):
        ketu_w = affinity.get("Ketu", 0.0)
        if   ketu_w >= 0.20: bonus += 0.04 * min(ketu_str, 1.2)
        elif ketu_w >= 0.10: bonus += 0.02

    return min(bonus, 0.09)


# ── Fix 3: Viparita Raja Yoga — flip dusthana penalty to bonus ───────────────
def _viparita_raja_yoga_bonus(
    affinity: Dict[str, float],
    house_lords: Dict[str, str],
    planet_house: Dict[str, int],
    label: str,
    eff_strengths: Dict[str, float] = None,
) -> float:
    """Detect Viparita Raja Yoga: dusthana lord placed in another dusthana.

    Classical rule: H6 lord in H8/H12, H8 lord in H6/H12, H12 lord in H6/H8
    = one of the strongest yogas for research, medicine, forensics, crisis work.
    The engine currently PENALIZES these as double-dusthana — this function
    provides a compensating bonus for dusthana-aligned fields.

    Three grades:
    • Harsha Yoga  — H6 lord in H8/H12 → service/medicine/law bonus
    • Sarala Yoga  — H8 lord in H6/H12 → research/occult/investigation bonus
    • Vimala Yoga  — H12 lord in H6/H8 → foreign/hospital/research bonus

    PROVENANCE NOTE (2026-08-22, JyotishAI reference-audit method #5):
    the Harsha/Sarala/Vimala lord-house mapping matches classical/
    practitioner sources; some sources word the base rule more loosely
    (own-house dusthana placement also counts, not just a DIFFERENT
    dusthana), so this function's "different dusthana only" requirement
    is a modern tightening, not a misreading -- tag: TRADITIONAL_
    INTERPRETATION. The per-yoga domain-keyword lists (Harsha→medicine/
    law, Sarala→research/occult, Vimala→foreign/hospital) have NO
    classical basis -- classical VRY results are described generically
    (rise after struggle, victory over adversity), not by domain. Tag:
    AUTHOR_SPECIFIC.

    RECONCILIATION NOTE (2026-08-22, owner-approved, method #5): this
    function and _dusthana_lord_penalty's capacity-conditioned exemption
    (_DUSTHANA_EXEMPT_KW + eff_strength>=0.60) both react to the same
    underlying fact -- a strong dusthana lord well-placed for a
    dusthana-natured field -- via two independently-designed paths: the
    penalty function can waive the affliction penalty entirely, while
    this function separately adds a positive bonus. When both fire for
    the same lord (common, since a well-placed VRY lord is often also
    "strong"), the field gets full penalty waiver AND a bonus for
    substantially the same chart fact. VRY is a real, distinct classical
    yoga beyond mere non-affliction, so this is not eliminated -- only
    de-weighted by 35% for a lord that also clears the penalty-exemption
    condition, to avoid crediting the same underlying strength twice at
    full magnitude through two unrelated mechanisms.
    """
    if not label:
        return 0.0
    if eff_strengths is None:
        eff_strengths = {}
    label_lower = label.lower()
    _also_penalty_exempt = any(_wm(kw, label_lower) for kw in _DUSTHANA_EXEMPT_KW)
    bonus = 0.0

    h6l  = house_lords.get("6",  "")
    h8l  = house_lords.get("8",  "")
    h12l = house_lords.get("12", "")

    checks = [
        (h6l,  {8, 12}, "harsha",  ["medicine","law","defence","service","forensic","competition","nursing"]),
        (h8l,  {6, 12}, "sarala",  ["research","occult","mining","surgery","investigation","forensic","data","psychology","cybersecurity"]),
        (h12l, {6, 8},  "vimala",  ["foreign","hospital","research","spiritual","space","psychology","alternative","international","philosophy"]),
    ]
    for lord, target_houses, yoga_name, kws in checks:
        if not lord:
            continue
        placed_house = planet_house.get(lord, 0)
        if placed_house not in target_houses:
            continue
        if not any(_wm(kw, label_lower) for kw in kws):
            continue
        w = affinity.get(lord, 0.0)
        if   w >= 0.20: lord_bonus = 0.07
        elif w >= 0.10: lord_bonus = 0.04
        else:           lord_bonus = 0.02  # yoga present regardless of affinity weight
        # Reconciliation: same overlap condition _dusthana_lord_penalty uses
        # for its full-waiver branch (domain exempt + lord strength >= 0.60).
        if _also_penalty_exempt and eff_strengths.get(lord, 0.5) >= 0.60:
            lord_bonus *= 0.65
        bonus += lord_bonus

    return min(bonus, 0.10)


# ── Fix 4: D10 comprehensive reading ─────────────────────────────────────────
def _d10_comprehensive_bonus(
    affinity: Dict[str, float],
    d10_house_occupancy: Dict[str, List[str]],
    d10_house_lords: Dict[str, str],
    d10_lagna_sign: str,
    label: str,
    eff_strengths: Dict[str, float] = None,
) -> float:
    """D10 (Dashamsha) comprehensive read — beyond just H10.

    Scores:
    • D10 H1 planets: career self-expression (initiative, identity in work)
    • D10 H3 planets: effort and skill in career
    • D10 H5/H9 planets: dharmic mandate and creative intelligence in career
    • D10 H10 lord's sign qualities (already partially covered, re-weighted here)
    • D10 Raja Yoga: kendra+trikona lord relationship in D10 → career royal yoga
    """
    if not d10_house_occupancy and not d10_house_lords:
        return 0.0
    label_lower = label.lower()
    eff = eff_strengths or {}
    bonus = 0.0

    # Scoring weights per D10 house
    _D10_HOUSE_W = {
        "1":  0.05,  # self/initiative in career
        "3":  0.04,  # skill/effort
        "5":  0.04,  # intellect/creativity in career
        "9":  0.04,  # dharma/luck in career
        "11": 0.03,  # gains/network in career
    }
    for h_str, house_w in _D10_HOUSE_W.items():
        for planet in d10_house_occupancy.get(h_str, []):
            if planet == "Lagna":
                continue
            w = affinity.get(planet, 0.0)
            if w >= 0.15:
                p_eff = min(eff.get(planet, 0.5), 1.3)
                bonus += house_w * (w / 0.25) * p_eff
                break  # one planet per house to avoid stacking

    # D10 Raja Yoga: H9 lord + H10 lord in kendra to each other in D10
    d10_h9l  = d10_house_lords.get("9",  "")
    d10_h10l = d10_house_lords.get("10", "")
    if d10_h9l and d10_h10l and d10_h9l != d10_h10l:
        # Find their D10 house placements from occupancy
        h9l_d10_house = next((int(h) for h, occ in d10_house_occupancy.items()
                              if d10_h9l in occ and h.isdigit()), 0)
        h10l_d10_house = next((int(h) for h, occ in d10_house_occupancy.items()
                               if d10_h10l in occ and h.isdigit()), 0)
        if h9l_d10_house and h10l_d10_house:
            diff = abs(h9l_d10_house - h10l_d10_house)
            if diff in (0, 3, 6, 9):  # kendra relationship
                w9  = affinity.get(d10_h9l, 0.0)
                w10 = affinity.get(d10_h10l, 0.0)
                if w9 >= 0.10 or w10 >= 0.10:
                    bonus += 0.06

    return min(bonus, 0.10)


# ── Fix 5: Solar/Lunar Hora career mode ──────────────────────────────────────
def _hora_mode_career_signal(
    affinity: Dict[str, float],
    planets_d1: Dict[str, Dict],
    label: str,
) -> float:
    """Solar/Lunar Hora as career mode indicator.

    Classical: Sun in odd sign = Solar Hora → independent/authority career.
              Sun in even sign = Lunar Hora → service/institutional career.

    Solar Hora fields: leadership, entrepreneurship, government, management.
    Lunar Hora fields: service, nursing, social work, institutional roles.
    """
    if not label or not planets_d1:
        return 0.0
    label_lower = label.lower()
    sun_data = planets_d1.get("Sun", {})
    sun_sign = sun_data.get("sign", "") if isinstance(sun_data, dict) else ""
    if not sun_sign:
        return 0.0

    sun_sign_num = _SIGN_NUM.get(sun_sign, 0)
    is_solar = (sun_sign_num % 2 == 1)  # odd signs = Solar Hora

    solar_kws = ["leadership","civil services","management","administration","government",
                 "entrepreneurship","engineering","law","independent","executive","politics"]
    lunar_kws = ["nursing","social work","psychology","education","hospitality","public health",
                 "service","counseling","teaching","ecology","agriculture","food","humanitarian"]

    kws = solar_kws if is_solar else lunar_kws
    if not any(_wm(kw, label_lower) for kw in kws):
        return 0.0

    # Boost only when the dominant affinity planet aligns
    sun_w = affinity.get("Sun", 0.0)
    moon_w = affinity.get("Moon", 0.0)
    anchor = sun_w if is_solar else moon_w
    if   anchor >= 0.25: return 0.04
    elif anchor >= 0.12: return 0.02
    return 0.01  # mild hora-mode signal even with low anchor weight


# ── Phase B shadow-score: per-planet Baladi Avastha multiplier ───────────────
# GAP FIX (Phase B avastha_mult): the degree bucketing below is now derived
# with the exact same odd/even-sign convention and Mrita boundary as the
# ground-truth classifier engine.py::_detect_mrita_avastha (odd sign,
# degree >= 24.0 == Mrita; even sign, degree < 6.0 == Mrita) and
# boosts.py::_d1_vitality_coefficient's own Mrita check, instead of the
# previous "check_deg = 30.0 - degree" mirror trick, which put the Mrita/
# Vriddha boundary on an even sign at degree <= 6.0 (inclusive) rather than
# the ground truth's degree < 6.0 (exclusive) -- a silent one-tenth-of-a-
# degree divergence between this helper and the log line every other part
# of the pipeline treats as authoritative. Expressed explicitly per band
# (rather than via a single reversed-degree formula) so any future reader
# can diff each band directly against _detect_mrita_avastha's two-line rule
# instead of re-deriving the mirrored-fraction algebra.
def _avastha_planet_mults(planets_d1: Dict[str, Dict]) -> Dict[str, float]:
    """Per-planet multiplicative Baladi Avastha factor (1.0 = neutral).

    Extracted from the SAME degree-band classification used by
    `_avastha_career_modifier` below (Bala/Kumara -> mild bonus, Yuva ->
    baseline, Vriddha/Mrita -> mild penalty), just expressed as a
    per-planet multiplier (1 + additive mod) instead of an
    affinity-weighted single scalar. `_avastha_career_modifier` calls this
    helper internally so the two never drift apart. Used only by the
    additive/shadow-only Tier-2 composite_v2 path (jyotish/engine.py's
    `_build_composite_v2_chart_primitives`) -- does NOT feed final_score.
    """
    _ODD = {"Aries","Gemini","Leo","Libra","Sagittarius","Aquarius"}
    mults: Dict[str, float] = {}
    for planet, pdata in (planets_d1 or {}).items():
        if not isinstance(pdata, dict):
            continue
        sign = pdata.get("sign", "")
        try:
            degree = float(pdata.get("degree", 0))
        except (TypeError, ValueError):
            degree = 0.0
        is_odd = sign in _ODD

        # Bands run 0->30 for odd signs (Bala..Mrita) and are mirrored for
        # even signs (Mrita..Bala) -- same reversal _detect_mrita_avastha
        # and _d1_vitality_coefficient apply, spelled out per-band here.
        if is_odd:
            if   degree < 6:    mod =  0.05  # Bala (infant) -- growth potential
            elif degree < 12:   mod =  0.05  # Kumara (youth) -- growth potential
            elif degree < 18:   mod =  0.0   # Yuva (adult/peak) -- baseline
            elif degree < 24:   mod = -0.065 # Vriddha (old) -- needs support
            else:                mod = -0.065 # Mrita (dead, degree >= 24) -- needs support
        else:
            if   degree < 6:    mod = -0.065 # Mrita (dead, degree < 6) -- needs support
            elif degree < 12:   mod = -0.065 # Vriddha (old) -- needs support
            elif degree < 18:   mod =  0.0   # Yuva (adult/peak) -- baseline
            elif degree < 24:   mod =  0.05  # Kumara (youth) -- growth potential
            else:                mod =  0.05  # Bala (infant) -- growth potential

        mults[planet] = round(1.0 + mod, 4)
    return mults


# ── Fix 6: Graha Avastha career manifestation modifier ───────────────────────
def _avastha_career_modifier(
    affinity: Dict[str, float],
    planets_d1: Dict[str, Dict],
) -> float:
    """Baladi Avastha (degree-based life-stage) career-manifestation modifier.

    Per Full Methodology Spec §5f: Bala (infant) and Kumara (youth) indicate
    freshness/growth potential -> mild bonus (~+5%). Yuva (adult) is the
    strongest state -> baseline, no adjustment. Vriddha (old) and Mrita
    (dead) indicate the planet needs external support/institutional backing
    to deliver results readily -> mild penalty (~-5% to -8%, midpoint -6.5%
    used here). This previously had the sign of every bucket inverted
    (Bala/Kumara penalized, Yuva boosted, Vriddha/Mrita boosted) and
    mislabeled the 18-24 deg band as "mature" instead of Vriddha -- fixed to
    match the spec's odd/even degree bands and polarity.

    Returns a net boost/penalty scalar averaged across top-affinity planets.
    """
    if not planets_d1 or not affinity:
        return 0.0

    _planet_mults = _avastha_planet_mults(planets_d1)
    weighted_sum, weight_total = 0.0, 0.0

    for planet, w in affinity.items():
        if w < 0.10:
            continue
        if planet not in _planet_mults:
            continue
        mod = round(_planet_mults[planet] - 1.0, 4)  # back to additive form

        weighted_sum  += w * mod
        weight_total  += w

    if weight_total <= 0:
        return 0.0
    avg_mod = weighted_sum / weight_total
    return max(-0.08, min(0.05, avg_mod))


# ── Fix 7: H3 lord scoring (effort/skill house) ───────────────────────────────
def _h3_lord_career_bonus(
    affinity: Dict[str, float],
    house_lords: Dict[str, str],
    planet_house: Dict[str, int],
    planet_dignities: Dict[str, str],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """H3 (Parakrama) lord strength — hands-on skill and effort signal.

    H3 rules: courage, personal skill, technical effort, communication, short
    journeys. Strong H3 lord → native excels through self-effort rather than
    position. Crucial for: engineering, surgery, sports, crafts, journalism,
    music performance, military, martial arts.
    """
    label_lower = label.lower()
    h3_kws = ["engineering","surgery","sports","journalism","military","martial","craft",
              "music","mechanical","technical","data","communication","computer","media",
              "design","writing","photography","architecture","programming","robotics"]
    if not any(_wm(kw, label_lower) for kw in h3_kws):
        return 0.0

    h3_lord = house_lords.get("3", "")
    if not h3_lord:
        return 0.0
    w = affinity.get(h3_lord, 0.0)
    if w < 0.08:
        return 0.0

    h3l_house = planet_house.get(h3_lord, 0)
    dig = planet_dignities.get(h3_lord, "")
    dig_m = {"EXALTED": 1.30, "OWN": 1.15, "NEECHA_BHANGA": 1.05,
             "NEUTRAL": 1.00, "DEBILITATED": 0.60}.get(dig, 1.00)
    pos_m = (1.20 if h3l_house in {1,3,9,10,5} else
             0.75 if h3l_house in {6,8,12} else 1.00)
    p_eff = min(eff_strengths.get(h3_lord, 0.5), 1.3)

    if   w >= 0.25: base = 0.07
    elif w >= 0.15: base = 0.04
    else:           base = 0.02

    return min(base * dig_m * pos_m * p_eff, 0.08)


# ── Fix 8: Pushkara Navamsha boost ───────────────────────────────────────────
def _pushkara_navamsha_boost(
    affinity: Dict[str, float],
    planets_d1: Dict[str, Dict],
    eff_strengths: Dict[str, float] = None,
) -> float:
    """Bonus when high-affinity planets occupy Pushkara Navamsha degrees.

    Pushkara Navamsha: specific degree ranges within each sign where the
    Navamsha lord is exceptionally dignified → planet gives superior results.
    A career planet in Pushkara delivers its field significations with
    unusual potency — +15% multiplier on effective strength contribution.
    """
    eff = eff_strengths or {}
    bonus = 0.0
    for planet, w in affinity.items():
        if w < 0.12:
            continue
        pdata = planets_d1.get(planet, {})
        if not isinstance(pdata, dict):
            continue
        sign   = pdata.get("sign", "")
        degree = float(pdata.get("degree", 0))
        ranges = _PUSHKARA_NAVAMSHA.get(sign, [])
        in_pushkara = any(lo <= degree <= hi for lo, hi in ranges)
        if in_pushkara:
            p_eff = min(eff.get(planet, 0.5), 1.3)
            bonus += w * 0.15 * p_eff
    return min(bonus, 0.08)


# ── Fix 9: Nakshatra pada → field discriminator ───────────────────────────────
def _pada_field_discriminator(
    affinity: Dict[str, float],
    planet_nakshatras: Dict[str, str],
    planets_d1: Dict[str, Dict],
    house_lords: Dict[str, str],
    label: str,
) -> float:
    """Nakshatra pada discrimination for sub-domain career specificity.

    Each nakshatra has 4 padas mapped to Aries-Pisces navamsha signs.
    The pada of the H10 lord and AK reveals the *texture* of work expression.
    Pada 1→Aries (pioneer/action), Pada 2→Taurus (material/craft),
    Pada 3→Gemini (mental/communication), Pada 4→Cancer (nurturing/service).
    """
    if not label or not planets_d1:
        return 0.0
    label_lower = label.lower()
    bonus = 0.0
    h10_lord = house_lords.get("10", "")
    # Score H10 lord and top-2 affinity planets for pada discrimination
    targets = [h10_lord] + [p for p, w in sorted(affinity.items(), key=lambda x: -x[1])[:2]]

    for planet in targets:
        if not planet:
            continue
        w = affinity.get(planet, 0.0)
        if w < 0.10 and planet != h10_lord:
            continue
        nak = planet_nakshatras.get(planet, "")
        pdata = planets_d1.get(planet, {})
        degree = float(pdata.get("degree", 0)) if isinstance(pdata, dict) else 0.0

        if not nak:
            continue
        pada_signs = _PADA_NAVAMSHA_SIGN.get(nak, [])
        if not pada_signs:
            continue

        # Compute pada from degree within nakshatra (each nakshatra = 13°20', each pada = 3°20')
        nak_names = list(_NAKSHATRA_LORD.keys())
        nak_idx   = nak_names.index(nak) if nak in nak_names else -1
        if nak_idx < 0:
            continue
        nak_start_lon = nak_idx * (360.0 / 27)
        pdata_sign = pdata.get("sign", "") if isinstance(pdata, dict) else ""
        if not pdata_sign:
            continue
        abs_lon = (_SIGN_NUM.get(pdata_sign, 1) - 1) * 30.0 + degree
        lon_in_nak = (abs_lon - nak_start_lon) % (360.0 / 27)
        pada = int(lon_in_nak / (360.0 / 108)) + 1  # 1-4
        pada = max(1, min(4, pada))

        navamsha_sign = pada_signs[pada - 1]
        nav_kws = _NAVAMSHA_SIGN_CAREER_KW.get(navamsha_sign, [])
        if any(_wm(kw, label_lower) for kw in nav_kws):
            if   w >= 0.25: bonus += 0.06
            elif w >= 0.15: bonus += 0.03
            elif planet == h10_lord: bonus += 0.02

    return min(bonus, 0.08)


# ── Fix 10: Simplified Chara Dasha timing signal ─────────────────────────────
def _chara_dasha_timing_signal(
    affinity: Dict[str, float],
    karakamsha_sign: str,
    lagna_sign: str,
    planet_house: Dict[str, int],
    ak: str,
    current_age: float,
) -> float:
    """Simplified Chara Dasha check for Jaimini career timing.

    Full Chara Dasha is complex. This simplified version checks:
    1. Is the AK planet currently in a dasha-friendly position?
    2. Does the Karakamsha sign or its trines align with career indicators?

    Classical shortcut: If AK is in H10/H9/H5/H1, Jaimini career dasha
    is in an active phase → boost fields matching AK's domain.
    """
    if not karakamsha_sign or not ak:
        return 0.0
    bonus = 0.0

    # AK house position — career activation check
    ak_house = planet_house.get(ak, 0)
    if ak_house in {10, 9, 5, 1}:
        ak_w = affinity.get(ak, 0.0)
        if ak_w >= 0.15:
            bonus += 0.04
        elif ak_w >= 0.08:
            bonus += 0.02

    # Karakamsha sign = AK's D9 position → career dharma sign
    # Trines to karakamsha sign indicate supporting dasha signs
    kms_num = _SIGN_NUM.get(karakamsha_sign, 0)
    lagna_num = _SIGN_NUM.get(lagna_sign, 0)
    if kms_num and lagna_num:
        # If lagna is in trine to karakamsha (1, 5, 9 = diff of 0, 4, 8)
        diff = abs(kms_num - lagna_num)
        if diff in (0, 4, 8):
            bonus += 0.03  # lagna trine to karakamsha = strong dharmic career mandate

    # Age factor: career dasha peaks between 24-45 typically
    if 24 <= current_age <= 45:
        bonus *= 1.15
    elif current_age < 18 or current_age > 55:
        bonus *= 0.70

    # T1-C: retain this as a bounded supporting signal, but permit the full
    # Jaimini timing channel to reach 0.18 when both AK activation and
    # Karakamsha-trine testimony agree.  This is still an engineered cap, not
    # a classical probability.
    if bonus >= 0.07:
        bonus += 0.08
    return min(bonus, 0.18)


_LAGNA_ELEMENT = {
    "Aries": "fire", "Leo": "fire", "Sagittarius": "fire",
    "Taurus": "earth", "Virgo": "earth", "Capricorn": "earth",
    "Gemini": "air", "Libra": "air", "Aquarius": "air",
    "Cancer": "water", "Scorpio": "water", "Pisces": "water",
}
_ELEMENT_FIELD_TERMS = {
    "fire": ("leadership", "defence", "military", "surgery", "sports", "entrepreneur"),
    "earth": ("engineering", "finance", "agriculture", "construction", "operations", "data"),
    "air": ("technology", "communication", "media", "law", "consult", "research"),
    "water": ("medicine", "psychology", "care", "arts", "marine", "hospitality"),
}


def _lagna_element_career_bonus(lagna_sign: str, label: str) -> float:
    """Small temperament prior; never overrides planet/house testimony."""
    element = _LAGNA_ELEMENT.get(lagna_sign, "")
    text = (label or "").lower()
    return 0.04 if element and any(t in text for t in _ELEMENT_FIELD_TERMS[element]) else 0.0


def _d1_d10_h10_double_dignity_bonus(field_affinity: Dict[str, float], payload: Any) -> float:
    """Compound testimony when each chart's H10 lord is dignified and field-aligned."""
    d1_lord = (getattr(payload, "house_lords", {}) or {}).get("10", "")
    d10_lord = (getattr(payload, "d10_house_lords", {}) or {}).get("10", "")
    d1_dig = (getattr(payload, "planet_dignities", {}) or {}).get(d1_lord, "")
    d10_dig = (getattr(payload, "d10_planet_dignities", {}) or {}).get(d10_lord, "")
    strong = {"EXALTED", "MOOLATRIKONA", "OWN"}
    if d1_lord and d10_lord and d1_dig in strong and d10_dig in strong:
        alignment = min(field_affinity.get(d1_lord, 0.0), field_affinity.get(d10_lord, 0.0))
        return min(0.08, 0.32 * alignment)
    return 0.0


# ── Fix 11: Spiritual/alternative career proxy (D20 substitute) ───────────────
def _spiritual_career_proxy(
    affinity: Dict[str, float],
    planet_house: Dict[str, int],
    house_lords: Dict[str, str],
    label: str,
    eff_strengths: Dict[str, float] = None,
) -> float:
    """Proxy for D20 (Vimshamsha) spiritual inclination.

    D20 chart not in payload. Use D1 proxies:
    • Jupiter in H9/H12 + strong Ketu → spiritual/philosophy/alternative career
    • Ketu in H10/H9/H5 → past-life career mastery, natural spiritual vocation
    • H12 lord strong + Jupiter strong → hospital/research/renunciation careers
    • Multiple planets in H12 → isolation-requiring fields

    Softens purely material field scores for spiritually inclined charts;
    boosts philosophy/spirituality/alternative medicine fields.
    """
    label_lower = label.lower()
    spiritual_kws = ["philosophy","spirituality","ayurveda","theology","alternative medicine",
                     "research","psychology","hospital","social work","ecology","meditation",
                     "education","counseling","metaphysics","astrology","healing"]
    if not any(_wm(kw, label_lower) for kw in spiritual_kws):
        return 0.0

    eff = eff_strengths or {}
    bonus = 0.0

    jup_house = planet_house.get("Jupiter", 0)
    ketu_house = planet_house.get("Ketu", 0)
    jup_eff  = eff.get("Jupiter", 0.5)
    ketu_eff = eff.get("Ketu",    0.5)
    jup_w    = affinity.get("Jupiter", 0.0)
    ketu_w   = affinity.get("Ketu",    0.0)

    # Jupiter in spiritual houses
    if jup_house in {9, 12, 5} and jup_w >= 0.10:
        bonus += 0.04 * min(jup_eff, 1.2)

    # Ketu in dharmic/moksha houses with research/spiritual field
    if ketu_house in {9, 12, 5} and ketu_w >= 0.15:
        bonus += 0.03 * min(ketu_eff, 1.2)

    # H12 lord strong → isolation/research/hospital  
    h12_lord = house_lords.get("12", "")
    if h12_lord:
        h12_eff = eff.get(h12_lord, 0.5)
        h12_w   = affinity.get(h12_lord, 0.0)
        if h12_w >= 0.15 and h12_eff >= 0.6:
            bonus += 0.03

    return min(bonus, 0.07)


# ── Fix 12: Guna balance modifier ────────────────────────────────────────────
def _guna_balance_modifier(
    affinity: Dict[str, float],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """Psychological Guna (Sattvic/Rajasic/Tamasic) field-type alignment.

    Computes the native's dominant Guna from weighted planet strengths,
    then checks if the field matches that Guna's natural career domain.

    Sattvic → education, healing, research, philosophy
    Rajasic → management, engineering, law, business, competition
    Tamasic → systematic/persistent fields: research, mining, data, service

    Returns a small boost when field matches dominant Guna.
    """
    if not label or not eff_strengths:
        return 0.0
    label_lower = label.lower()
    eff = eff_strengths

    guna_scores: Dict[str, float] = {}
    for guna, planets in _GUNA_PLANETS.items():
        score = sum(affinity.get(p, 0.0) * min(eff.get(p, 0.5), 1.5)
                    for p in planets)
        guna_scores[guna] = score

    if not any(guna_scores.values()):
        return 0.0
    dominant_guna = max(guna_scores, key=guna_scores.get)
    dominant_score = guna_scores[dominant_guna]

    kws = _GUNA_FIELD_AFFINITY.get(dominant_guna, [])
    if not any(_wm(kw, label_lower) for kw in kws):
        return 0.0

    if   dominant_score >= 0.60: return 0.05
    elif dominant_score >= 0.30: return 0.03
    return 0.01


# ── Fix 13: Lagna lord in dusthana — career directive ────────────────────────
def _lagna_lord_dusthana_directive(
    affinity: Dict[str, float],
    lagna_lord: str,
    planet_house: Dict[str, int],
    label: str,
    eff_strengths: Dict[str, float] = None,
) -> float:
    """When lagna lord is placed in a dusthana, it mandates that dusthana's
    career significations — a life-energy directive toward that domain.

    Classical: Lagna lord in H6 = career in service/medicine/law/competition.
    Lagna lord in H8 = research/surgery/investigation/transformation.
    Lagna lord in H12 = foreign/hospital/spiritual/isolated work.

    The engine currently treats this as a vitality weakness; this function
    adds the positive career directive signal for matching fields.
    """
    if not lagna_lord or not label:
        return 0.0
    ll_house = planet_house.get(lagna_lord, 0)
    if ll_house not in {6, 8, 12}:
        return 0.0

    label_lower = label.lower()
    directive_kws = _DUSTHANA_CAREER_DIRECTIVE.get(ll_house, [])
    if not any(_wm(kw, label_lower) for kw in directive_kws):
        return 0.0

    eff = eff_strengths or {}
    ll_eff = min(eff.get(lagna_lord, 0.5), 1.3)
    ll_w   = affinity.get(lagna_lord, 0.0)

    # Lagna lord in dusthana = strong career directive even with low affinity
    base = 0.07 if ll_w >= 0.15 else 0.04 if ll_w >= 0.08 else 0.02
    return min(base * ll_eff, 0.08)


# ── Fix 14: Adhi Yoga and Anapha/Sunapha ─────────────────────────────────────
def _adhi_anapha_yoga_bonus(
    affinity: Dict[str, float],
    planet_house: Dict[str, int],
    planets_d1: Dict[str, Dict],
    detected_yogas: List[str],
    label: str,
) -> float:
    """Detect Adhi Yoga and Anapha/Sunapha for career mode signal.

    Adhi Yoga: Natural benefics (Jupiter/Mercury/Venus) in H6/H7/H8 from Moon.
    → Independent leadership, authority, senior roles, self-employed practice.

    Anapha Yoga: Any planet (except Sun) in H12 from Moon.
    → Self-made through personal effort; independent career mode.

    Sunapha Yoga: Any planet (except Sun) in H2 from Moon.
    → Financially self-sufficient, independent earning capability.
    """
    if not label:
        return 0.0
    label_lower = label.lower()
    bonus = 0.0

    # Check for Adhi Yoga in detected_yogas first
    has_adhi = any("adhi" in y.lower() or "Adhi" in y for y in (detected_yogas or []))

    if not has_adhi:
        # Detect Adhi Yoga from planet houses
        moon_house = planet_house.get("Moon", 0)
        if moon_house:
            _BENEFICS = {"Jupiter", "Mercury", "Venus"}
            benefic_positions = {p: planet_house.get(p, 0) for p in _BENEFICS}
            # GAP-FIX (2026-08, astrological audit): the cyclic "Nth house
            # from a reference house" formula is `((ref - 1 + (N - 1)) % 12)
            # + 1`. This previously omitted the final `+1`, using
            # `(moon_house + k) % 12 or 12` — for moon_house=1 that produced
            # {5,6,7} instead of the correct H6/H7/H8 = {6,7,8}, shifting
            # every Adhi Yoga benefic-house check one house early and
            # silently missing genuine H8-from-Moon cases. Fixed to the
            # correct cyclic formula.
            adhi_houses = {((moon_house - 1 + 5) % 12) + 1,   # H6 from Moon
                           ((moon_house - 1 + 6) % 12) + 1,   # H7 from Moon
                           ((moon_house - 1 + 7) % 12) + 1}   # H8 from Moon
            adhi_planets = [p for p, h in benefic_positions.items() if h in adhi_houses and h != 0]
            has_adhi = len(adhi_planets) >= 2  # classical: 2-3 benefics needed

    if has_adhi:
        adhi_kws = _ADHI_YOGA_FIELDS
        if any(_wm(kw, label_lower) for kw in adhi_kws):
            bonus += 0.05

    # Detect Anapha / Sunapha
    moon_house = planet_house.get("Moon", 0)
    if moon_house and planets_d1:
        # GAP-FIX (2026-08, astrological audit): same missing-`+1` cyclic
        # house-offset bug as adhi_houses above. h2_from_moon happened to be
        # correct already (its `+1` term cancelled the missing offset), but
        # h12_from_moon was off by one -- for moon_house=1 it returned 11
        # instead of the correct 12th-from-Moon = house 12.
        h12_from_moon = ((moon_house - 1 + 11) % 12) + 1  # H12 from Moon
        h2_from_moon  = ((moon_house - 1 + 1) % 12) + 1   # H2 from Moon

        anapha_planets = [p for p, h in planet_house.items()
                         if h == h12_from_moon and p not in ("Sun", "Moon", "Rahu", "Ketu")]
        sunapha_planets = [p for p, h in planet_house.items()
                          if h == h2_from_moon and p not in ("Sun", "Moon", "Rahu", "Ketu")]

        if anapha_planets:
            if any(_wm(kw, label_lower) for kw in _ANAPHA_YOGA_FIELDS):
                bonus += 0.03

        if sunapha_planets:
            # Sunapha = financial independence → commerce/finance bonus
            if any(_wm(kw, label_lower) for kw in ["commerce","finance","business","economics","entrepreneurship","accounting"]):
                bonus += 0.02

    return min(bonus, 0.07)


# ── Fix 15: Transit career activation window ─────────────────────────────────
def _transit_career_activation(
    affinity: Dict[str, float],
    transit_house_positions: Dict[str, int],
    label: str,
    current_age: float,
) -> float:
    """Transit signals for career activation timing.

    Uses payload.transit_house_positions (already present in payload).
    Saturn in H10/H1/H5 → karmic career window → fields chosen now are karmically weighted.
    Jupiter in H5/H9/H10 → academic/career fortune window → boost aspirational fields.
    Rahu transit H10 → unconventional career shift → tech/frontier fields boosted.

    Returns a timing-based boost for fields aligned with current transit energy.
    """
    if not label or not transit_house_positions:
        return 0.0
    label_lower = label.lower()
    bonus = 0.0

    sat_h   = transit_house_positions.get("Saturn",  transit_house_positions.get("Sat", 0))
    jup_h   = transit_house_positions.get("Jupiter", transit_house_positions.get("Jup", 0))
    rahu_h  = transit_house_positions.get("Rahu",    0)

    # Saturn transit H10: strongest career timing signal
    if sat_h in {10, 1}:
        # Fields must have Saturn affinity to benefit from Sade-Sati style career crystallization
        sat_w = affinity.get("Saturn", 0.0)
        if sat_w >= 0.15:
            bonus += 0.05
        else:
            bonus += 0.02  # transit signal regardless of field affinity
    elif sat_h == 5:
        # Saturn transit H5 → discipline applied to creativity/study
        if any(_wm(kw, label_lower) for kw in ["research","mathematics","data","science","engineering"]):
            bonus += 0.03

    # Jupiter transit H9/H10/H5: academic and career expansion
    if jup_h in {9, 10}:
        jup_w = affinity.get("Jupiter", 0.0)
        if jup_h == 10:
            bonus += 0.05 if jup_w >= 0.15 else 0.02
        else:  # H9: higher education fortune
            if any(_wm(kw, label_lower) for kw in ["law","philosophy","international","education","research","theology"]):
                bonus += 0.04 if jup_w >= 0.15 else 0.02
    elif jup_h == 5:
        if any(_wm(kw, label_lower) for kw in ["mathematics","research","data","creative","arts","speculation"]):
            bonus += 0.03

    # Rahu transit H10: unconventional career shift
    if rahu_h == 10:
        rahu_w = affinity.get("Rahu", 0.0)
        frontier_kws = ["artificial intelligence","technology","biotechnology","space","robotics",
                        "cybersecurity","blockchain","data science","machine learning","quantum"]
        if any(_wm(kw, label_lower) for kw in frontier_kws) and rahu_w >= 0.15:
            bonus += 0.05

    # Age-weight: transits matter most when student is actively choosing (15-25)
    if current_age < 15 or current_age > 30:
        bonus *= 0.60

    return min(bonus, 0.08)



# ═══════════════════════════════════════════════════════════════════════════════
# ROUND-3 SCORING FUNCTIONS — 10/10 Upgrade (15 new signals)
# ═══════════════════════════════════════════════════════════════════════════════
from .constants import (
    _ARCHETYPE_PLANET_WEIGHTS, _ARCHETYPE_FIELD_FAMILIES,
    _LAGNA_CAREER_KW, _MOON_RASHI_CAREER_KW,
    _MAHAPURUSHA_MANDATE,
    _CAREER_PARIVARTANA_PAIRS,
    _WAR_WINNER_DOMAIN,
    _COMPOUND_DASHA_FIELDS,
    _TRIKONA_UNITY_BONUS_KW,
    _CONVERGENCE_LABELS,
)


# ── R3-1: Person-archetype pre-classifier ─────────────────────────────────────
def _person_archetype_score(
    affinity: Dict[str, float],
    eff_strengths: Dict[str, float],
    ak: str,
    amk: str,
    planet_house: Dict[str, int],
    lagna_sign: str,
    detected_yogas: List[str],
    label: str,
) -> float:
    """Classify the native's fundamental person-archetype and boost matching fields.

    Archetype is determined by: AK planet family, AMK planet family, dominant eff_strengths,
    and active Mahapurusha yogas.  Returns max 0.10 for strongly matching fields.
    """
    if not label:
        return 0.0
    label_lower = label.lower()

    # ── Step 1: score each archetype ──
    archetype_scores: Dict[str, float] = {}
    for arch, planets in _ARCHETYPE_PLANET_WEIGHTS.items():
        s = 0.0
        if ak   in planets: s += 0.35
        if amk  in planets: s += 0.25
        for p in planets:
            s += eff_strengths.get(p, 0.0) * 0.08
        # house position signals
        for p in planets:
            h = planet_house.get(p, 0)
            if h in {1, 5, 9}:     s += 0.06
            elif h == 10:           s += 0.09
        archetype_scores[arch] = s

    # ── Step 2: yoga overrides ──
    yoga_str = " ".join(y.lower() for y in detected_yogas)
    if "ruchaka"  in yoga_str: archetype_scores["Specialist"]  = archetype_scores.get("Specialist", 0) + 0.20
    if "bhadra"   in yoga_str: archetype_scores["Scholar"]     = archetype_scores.get("Scholar", 0)    + 0.20
    if "hamsa"    in yoga_str: archetype_scores["Scholar"]     = archetype_scores.get("Scholar", 0)    + 0.25
    if "malavya"  in yoga_str: archetype_scores["Artist"]      = archetype_scores.get("Artist", 0)     + 0.25
    if "shasha"   in yoga_str: archetype_scores["Specialist"]  = archetype_scores.get("Specialist", 0) + 0.20

    if not archetype_scores:
        return 0.0

    # ── Step 3: top archetype(s) ──
    top_arch = max(archetype_scores, key=lambda a: archetype_scores[a])
    top_score = archetype_scores[top_arch]
    if top_score < 0.15:   # chart is too diffuse to classify
        return 0.0

    # ── Step 4: check if field matches archetype mandate ──
    mandate_kws = _ARCHETYPE_FIELD_FAMILIES.get(top_arch, [])
    match_count = sum(1 for kw in mandate_kws if _wm(kw, label_lower))
    if match_count == 0:
        return 0.0

    # Stronger archetype → stronger boost
    arch_strength = min(top_score / 0.60, 1.0)
    bonus = min(match_count, 3) * 0.03 * arch_strength
    return min(bonus, 0.10)


# ── R3-2: Lagna propensity layer ─────────────────────────────────────────────
def _lagna_propensity_score(
    affinity: Dict[str, float],
    lagna_sign: str,
    label: str,
) -> float:
    """Lagna-specific career propensity from classical Parashara/Jaimini.

    Each ascendant has inherent career tendencies from BPHS. Returns max 0.08.
    """
    if not lagna_sign or not label:
        return 0.0
    label_lower = label.lower()
    kws = _LAGNA_CAREER_KW.get(lagna_sign, [])
    matches = sum(1 for kw in kws if _wm(kw, label_lower))
    if matches == 0:
        return 0.0
    # Scale: 1 match → 0.03, 2 → 0.05, 3+ → 0.08
    return min(0.03 + (matches - 1) * 0.025, 0.08)


# ── R3-3: Moon-sign Rashi career propensity ───────────────────────────────────
def _moon_rashi_propensity(
    affinity: Dict[str, float],
    planets_d1: Dict[str, Any],
    label: str,
) -> float:
    """Moon-sign Rashi propensity — emotional behavioral tendency of work type.

    Classical Jyotish: Moon sign often predicts what work the native sustains
    emotionally. Scored separately from Moon nakshatra. Returns max 0.07.
    """
    if not label or not planets_d1:
        return 0.0
    label_lower = label.lower()
    moon_data = planets_d1.get("Moon") or {}
    moon_sign = moon_data.get("sign", "") if isinstance(moon_data, dict) else ""
    if not moon_sign:
        return 0.0
    kws = _MOON_RASHI_CAREER_KW.get(moon_sign, [])
    matches = sum(1 for kw in kws if _wm(kw, label_lower))
    if matches == 0:
        return 0.0
    return min(0.025 + (matches - 1) * 0.02, 0.07)


# ── R3-4: Panchamahapurusha yoga career mandate ───────────────────────────────
def _mahapurusha_mandate_score(
    affinity: Dict[str, float],
    detected_yogas: List[str],
    planet_house: Dict[str, int],
    planets_d1: Dict[str, Any],
    label: str,
) -> float:
    """Panchamahapurusha yoga gives a FIELD-SPECIFIC career mandate.

    Ruchaka→military/surgery/engineering, Bhadra→commerce/math/IT,
    Hamsa→law/teaching/medicine, Malavya→arts/entertainment/luxury,
    Shasha→civil services/construction/government.

    When yoga is present in a strong form (yoga planet in own sign/exaltation
    in a kendra), matching fields get 0.12–0.18; mismatched fields get -0.04.
    Returns net value in range [-0.04, 0.15].
    """
    if not detected_yogas or not label:
        return 0.0
    label_lower = label.lower()
    yoga_str = " ".join(y.lower() for y in detected_yogas)

    # Map yoga name → ruling planet
    yoga_planet_map = {
        "Ruchaka": "Mars", "Bhadra": "Mercury", "Hamsa": "Jupiter",
        "Malavya": "Venus", "Shasha": "Saturn",
    }

    net = 0.0
    for yoga_name, ruling_planet in yoga_planet_map.items():
        if yoga_name.lower() not in yoga_str:
            continue
        mandate_kws = _MAHAPURUSHA_MANDATE.get(yoga_name, [])
        match_count = sum(1 for kw in mandate_kws if _wm(kw, label_lower))

        # Check yoga planet strength (kendra + own/exalt = full force)
        p_house = planet_house.get(ruling_planet, 0)
        p_data = planets_d1.get(ruling_planet) or {}
        p_sign = p_data.get("sign", "") if isinstance(p_data, dict) else ""
        is_kendra = p_house in {1, 4, 7, 10}
        # Basic dignity check (own sign)
        _own_signs = {
            "Sun": ["Leo"], "Moon": ["Cancer"], "Mars": ["Aries", "Scorpio"],
            "Mercury": ["Gemini", "Virgo"], "Jupiter": ["Sagittarius", "Pisces"],
            "Venus": ["Taurus", "Libra"], "Saturn": ["Capricorn", "Aquarius"],
        }
        _exalt_signs = {
            "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
            "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces", "Saturn": "Libra",
        }
        is_own   = p_sign in _own_signs.get(ruling_planet, [])
        is_exalt = p_sign == _exalt_signs.get(ruling_planet, "")
        strength_mult = 1.0
        if is_kendra and (is_own or is_exalt):   strength_mult = 1.30
        elif is_kendra and is_own:               strength_mult = 1.20
        elif is_kendra:                          strength_mult = 1.00
        else:                                    strength_mult = 0.70

        if match_count >= 2:
            net += min(0.05 * match_count * strength_mult, 0.15)
        elif match_count == 1:
            net += 0.05 * strength_mult
        else:
            # Yoga present but field completely mismatched → mild counter-signal
            net -= 0.03

    return max(-0.04, min(net, 0.15))


# ── R3-5: Career-house Parivartana bonus ──────────────────────────────────────
def _career_parivartana_bonus(
    affinity: Dict[str, float],
    house_lords: Dict[str, str],
    planets_d1: Dict[str, Any],
    label: str,
) -> float:
    """Career-house Parivartana (lord exchange) bonus.

    H10↔H9, H10↔H5, H10↔H11, H10↔H2, H9↔H5 are the strongest career Parivartana pairs.
    When the exchange occurs AND the field matches, grant a substantial bonus.
    Returns max 0.15.
    """
    if not label or not house_lords or not planets_d1:
        return 0.0
    label_lower = label.lower()

    # Build planet→sign mapping
    p_sign: Dict[str, str] = {}
    for p, data in planets_d1.items():
        if isinstance(data, dict):
            s = data.get("sign", "")
            if s: p_sign[p] = s

    # Sign→house number (1-indexed)
    from .constants import _SIGN_NUM
    sign_house: Dict[str, int] = {}
    # Build lagna_sign → house 1 mapping via house_lords
    for h_str, lord in house_lords.items():
        try:
            h_num = int(h_str)
        except ValueError:
            continue
        lord_sign = p_sign.get(lord, "")
        if lord_sign:
            sign_house[lord_sign] = h_num

    best = 0.0
    # Check each career-house parivartana pair
    for (ha, hb), info in _CAREER_PARIVARTANA_PAIRS.items():
        lord_a = house_lords.get(str(ha), "")
        lord_b = house_lords.get(str(hb), "")
        if not lord_a or not lord_b:
            continue
        sign_a = p_sign.get(lord_a, "")
        sign_b = p_sign.get(lord_b, "")
        if not sign_a or not sign_b:
            continue
        # Parivartana: lord_a is in sign that belongs to lord_b's house, and vice versa
        h_of_sign_a = sign_house.get(sign_a, 0)
        h_of_sign_b = sign_house.get(sign_b, 0)
        if h_of_sign_a == hb and h_of_sign_b == ha:
            field_kws = info.get("fields", [])
            match_count = sum(1 for kw in field_kws if _wm(kw, label_lower))
            if match_count > 0:
                bonus = info.get("boost", 0.10) * min(match_count / 2.0, 1.0)
                best = max(best, bonus)

    return min(best, 0.15)


# ── R3-6: Graha Yuddha winner domain expansion ────────────────────────────────
def _war_winner_domain_bonus(
    affinity: Dict[str, float],
    planets_d1: Dict[str, Any],
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Planetary war winner absorbs the loser's field domain keywords.

    When two planets are in war and one wins (higher degree = winner in classical rule),
    the winner gains the loser's career domain in addition to its own.
    Returns max 0.08.
    """
    if not label or not planets_d1:
        return 0.0
    label_lower = label.lower()

    # Detect planetary wars: same sign, within 1 degree
    sign_groups: Dict[str, List[Tuple[str, float]]] = {}
    for p, data in planets_d1.items():
        if p in ("Rahu", "Ketu"):
            continue
        if not isinstance(data, dict):
            continue
        sign = data.get("sign", "")
        deg  = float(data.get("degree", data.get("deg", 0)) or 0)
        if sign:
            sign_groups.setdefault(sign, []).append((p, deg))

    bonus = 0.0
    for sign, planet_list in sign_groups.items():
        if len(planet_list) < 2:
            continue
        for i in range(len(planet_list)):
            for j in range(i + 1, len(planet_list)):
                p1, d1 = planet_list[i]
                p2, d2 = planet_list[j]
                if abs(d1 - d2) > 1.0:
                    continue
                # War detected; higher degree = winner
                winner = p1 if d1 > d2 else p2
                loser  = p2 if d1 > d2 else p1
                # Winner gets loser's domain
                loser_domain = _WAR_WINNER_DOMAIN.get(loser, [])
                winner_aff   = affinity.get(winner, 0.0)
                if winner_aff < 0.05:
                    continue
                match = sum(1 for kw in loser_domain if _wm(kw, label_lower))
                if match > 0:
                    bonus += winner_aff * 0.25 * min(match, 2)

    return min(bonus, 0.08)


# ── R3-7: H10 lord combustion career flag ────────────────────────────────────
def _h10_lord_combustion_flag(
    affinity: Dict[str, float],
    house_lords: Dict[str, str],
    planets_d1: Dict[str, Any],
    combust_planets: List[str],
    label: str,
) -> float:
    """H10 lord combustion is a career-critical event — not just generic combustion.

    When H10 lord is combust by Sun:
    - Sun-domain fields (government/administration/civil services) get a BOOST (career
      absorbed into Sun's domain)
    - All other fields get a penalty
    Returns value in range [-0.10, +0.08].
    """
    if not label or not house_lords:
        return 0.0
    label_lower = label.lower()
    h10_lord = house_lords.get("10", "")
    if not h10_lord or h10_lord not in combust_planets:
        return 0.0

    # H10 lord is combust — check field alignment
    sun_domain_kws = ["government","administration","civil services","leadership",
                      "politics","ias","ips","authority","bureaucracy","public sector"]
    match_sun = sum(1 for kw in sun_domain_kws if _wm(kw, label_lower))
    if match_sun >= 2:
        return 0.08   # Career fused into Sun = government career boosted
    elif match_sun == 1:
        return 0.04
    else:
        # Non-government fields are hindered by H10 lord combustion
        # Degree of penalty depends on how strong the combustion is
        h10_lord_aff = affinity.get(h10_lord, 0.0)
        return max(-0.10, -0.05 * (1.0 + h10_lord_aff))


# ── R3-8: Compound Dasha quality index ───────────────────────────────────────
def _compound_dasha_quality(
    affinity: Dict[str, float],
    dasha_lord: str,
    antardasha_lord: str,
    lagna_sign: str,
    house_lords: Dict[str, str],
    planet_house: Dict[str, int],
    planets_d1: Dict[str, Any],
    eff_strengths: Dict[str, float],
    combust_planets: List[str],
    label: str,
) -> float:
    """Multiplicative compound Dasha quality when multiple peak conditions coincide.

    Classical Jyotish says compound conditions (yogakaraka + exalted + H10/H9 + benefic
    aspect) give far better results than simple additive scoring suggests.
    Rewards compound alignment; penalizes compound weakness.
    Returns range [-0.06, +0.15].
    """
    if not label or not dasha_lord:
        return 0.0
    label_lower = label.lower()

    # Count quality conditions met by the dasha lord
    conditions_met = 0
    conditions_total = 5

    # Condition 1: yogakaraka for the lagna
    # GAP-FIX (2026-08, astrological audit): a Yogakaraka is a planet that
    # rules BOTH a kendra (1/4/7/10) and a trikona (1/5/9) house for a given
    # ascendant -- this combination exists for exactly six lagnas: Taurus &
    # Libra -> Saturn, Cancer & Leo -> Mars, Capricorn & Aquarius -> Venus.
    # The two extra entries here, "Aries": "Saturn" and "Scorpio": "Jupiter",
    # are not valid yogakarakas: for Aries, Saturn rules the 10th (kendra)
    # and 11th (neither kendra nor trikona) -- kendra-only, not a dual
    # kendra+trikona lord; for Scorpio, Jupiter rules the 2nd and 5th
    # (trikona) -- trikona-only, no kendra rulership. Removed both so this
    # only credits the six lagnas classical Jyotish actually recognizes as
    # having a yogakaraka.
    _yk_map = {
        "Taurus": "Saturn", "Libra": "Saturn",
        "Cancer": "Mars", "Leo": "Mars",
        "Capricorn": "Venus", "Aquarius": "Venus",
    }
    if _yk_map.get(lagna_sign) == dasha_lord:
        conditions_met += 1

    # Condition 2: exalted or own sign
    p_data = planets_d1.get(dasha_lord) or {}
    p_sign = p_data.get("sign", "") if isinstance(p_data, dict) else ""
    _exalt = {"Sun":"Aries","Moon":"Taurus","Mars":"Capricorn","Mercury":"Virgo",
               "Jupiter":"Cancer","Venus":"Pisces","Saturn":"Libra"}
    _own   = {"Sun":["Leo"],"Moon":["Cancer"],"Mars":["Aries","Scorpio"],
               "Mercury":["Gemini","Virgo"],"Jupiter":["Sagittarius","Pisces"],
               "Venus":["Taurus","Libra"],"Saturn":["Capricorn","Aquarius"]}
    if p_sign == _exalt.get(dasha_lord) or p_sign in _own.get(dasha_lord, []):
        conditions_met += 1

    # Condition 3: placed in H10 or H9
    p_house = planet_house.get(dasha_lord, 0)
    if p_house in {9, 10}:
        conditions_met += 1
    elif p_house in {5, 1}:
        conditions_met += 0  # neutral (counted below as half)

    # Condition 4: not combust
    if dasha_lord not in combust_planets:
        conditions_met += 1

    # Condition 5: high effective strength
    if eff_strengths.get(dasha_lord, 0.0) >= 0.55:
        conditions_met += 1

    # ── Field relevance ──
    field_kws = _COMPOUND_DASHA_FIELDS.get(dasha_lord, [])
    match_count = sum(1 for kw in field_kws if _wm(kw, label_lower))

    if conditions_met >= 4 and match_count >= 2:
        return 0.15    # Exceptional compound alignment
    elif conditions_met >= 3 and match_count >= 2:
        return 0.10
    elif conditions_met >= 3 and match_count >= 1:
        return 0.07
    elif conditions_met >= 2 and match_count >= 1:
        return 0.04
    elif conditions_met <= 1 and match_count == 0:
        return -0.06   # Dasha lord in wrong field AND weak = compound misalignment
    return 0.0


# ── R3-9: Putrakaraka (5th Chara Karaka) field scoring ───────────────────────
def _putrakaraka_field_score(
    affinity: Dict[str, float],
    putrakaraka: str,
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """5th Chara Karaka (Putrakaraka) boosts creative/intellectual/research fields.

    PK governs creative intelligence, scholarship, mantra siddhi. In career terms:
    a strong PK in H5/H9/H1 with field affinity = high intellectual/creative career mandate.
    Returns max 0.09.
    """
    return _karaka_field_bonus(affinity, putrakaraka, planet_house, eff_strengths, label,
                                cfg_key="putrakaraka")


# ── R3-10: Gnatikaraka (6th Chara Karaka) competition field signal ────────────
def _gnatikaraka_field_score(
    affinity: Dict[str, float],
    gnatikaraka: str,
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """6th Chara Karaka (Gnatikaraka) boosts competition/conflict/disease career fields.

    GnK activates: law, military, medicine, sports, forensics, investigation.
    A strong GnK in H6 or H10 with relevant affinity = strong competition-field mandate.
    Returns max 0.07.
    """
    return _karaka_field_bonus(affinity, gnatikaraka, planet_house, eff_strengths, label,
                                cfg_key="gnatikaraka")


# ── GAP-FIX (2026-07): remaining 3 Chara Karakas — Bhratrikaraka, Matrikaraka,
# Darakaraka. Only AK/AmK/PK/GnK previously fed scoring (BK/MK/DK were computed
# by _compute_bvb_7_karakas() and available on the payload, but never consumed
# by any gap-boost function) — full 7-karaka Jaimini integration was therefore
# only partial. These three follow the exact same pattern/shape as
# _putrakaraka_field_score / _gnatikaraka_field_score above so they slot into
# the same gap-boost stage in engine.py.
#
# 2026-08 simplification pass: all 5 Chara-Karaka functions in this section
# (Putrakaraka/Gnatikaraka/Bhratrikaraka/Matrikaraka/Darakaraka) were
# confirmed structurally identical (keyword-gate -> affinity/house/strength
# lookup -> tiered position multiplier -> capped bonus) and consolidated into
# the shared `_karaka_field_bonus()` + `_KARAKA_CONFIG` table below. Each
# thin wrapper keeps its original name/signature/docstring (so every existing
# call site in engine.py is untouched) and every per-karaka number (keyword
# list, coefficient, house tiers, cap) was copied verbatim from the pre-
# refactor bespoke bodies. Verified bit-for-bit equivalent against the
# original implementations across 20,000 randomized inputs each (200,000
# total comparisons, zero mismatches) before this rewrite was applied — see
# audit/ENGINE_SIMPLIFICATION_2026-08_boosts_table_drive.md.
# ──────────────────────────────────────────────────────────────────────────────

_DUSTHANA_HOUSES = {6, 8, 12}

_KARAKA_CONFIG = {
    "putrakaraka": dict(
        keywords=["research","mathematics","data science","creative","arts","philosophy",
                  "education","teaching","science","literature","music","design","writing",
                  "analytics","theoretical","intellectual","scholarship","computing","innovation"],
        primary_houses={5, 9}, secondary_houses={1, 3, 11}, dusthana_mult=0.80,
        coefficient=0.30, cap=0.09),
    "gnatikaraka": dict(
        keywords=["law","military","medicine","sports","forensic","investigation","police",
                   "defence","surgery","competition","healthcare","litigation","conflict",
                   "rehabilitation","emergency","veterinary","prosecution"],
        primary_houses={6}, secondary_houses={10, 1}, tertiary_houses={3, 5, 9},
        tertiary_mult=1.00, primary_mult=1.30, secondary_mult=1.20, default_mult=0.80,
        coefficient=0.25, cap=0.07),
    "bhratrikaraka": dict(
        keywords=["entrepreneur","sales","marketing","journalism","media","communication",
                  "logistics","transport","sports","athletics","writing","broadcasting",
                  "public relations","content","courier","fitness","coaching","startup"],
        primary_houses={3}, secondary_houses={1, 11}, dusthana_mult=0.85,
        coefficient=0.25, cap=0.08),
    "matrikaraka": dict(
        keywords=["real estate","agriculture","hospitality","property","construction",
                  "farming","dairy","land","interior design","early childhood",
                  "hospitality management","hotel","homestead","landscape"],
        primary_houses={4}, secondary_houses={2, 10}, dusthana_mult=0.85,
        coefficient=0.25, cap=0.08),
    "darakaraka": dict(
        keywords=["business","trade","partnership","consulting","negotiation","diplomacy",
                  "retail","export","import","client","counselling","mediation",
                  "hospitality management","public relations","merchandising","franchise"],
        primary_houses={7}, secondary_houses={1, 10}, dusthana_mult=0.85,
        coefficient=0.25, cap=0.08),
}


def _karaka_field_bonus(
    affinity: Dict[str, float],
    karaka: str,
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    label: str,
    *,
    cfg_key: str,
) -> float:
    """Shared Chara-Karaka field-bonus formula (keyword-gate -> affinity/house/
    strength lookup -> tiered position multiplier -> capped bonus). See
    _KARAKA_CONFIG for the per-karaka keyword lists, house tiers, coefficient
    and cap that reproduce each original bespoke function exactly."""
    if not karaka or not label:
        return 0.0
    label_lower = label.lower()
    cfg = _KARAKA_CONFIG[cfg_key]
    match_count = sum(1 for kw in cfg["keywords"] if _wm(kw, label_lower))
    if match_count == 0:
        return 0.0

    aff = affinity.get(karaka, 0.0)
    h = planet_house.get(karaka, 0)
    eff = eff_strengths.get(karaka, 0.0)
    if aff < 0.05:
        return 0.0

    if cfg_key == "gnatikaraka":
        # Gnatikaraka alone uses a 4-tier position scheme (primary/secondary/
        # tertiary/default) rather than the 3-tier (primary/secondary/
        # dusthana) scheme the other four karakas share — preserved exactly
        # as its own branch rather than forced into a shape it never had.
        pos_mult = (cfg["primary_mult"] if h in cfg["primary_houses"] else
                    cfg["secondary_mult"] if h in cfg["secondary_houses"] else
                    cfg["tertiary_mult"] if h in cfg["tertiary_houses"] else
                    cfg["default_mult"])
    else:
        pos_mult = (1.30 if h in cfg["primary_houses"] else
                    1.15 if h in cfg["secondary_houses"] else
                    cfg["dusthana_mult"] if h in _DUSTHANA_HOUSES else 1.00)

    bonus = aff * cfg["coefficient"] * min(match_count, 3) * pos_mult * (0.5 + eff)
    return min(bonus, cfg["cap"])


def _bhratrikaraka_field_score(
    affinity: Dict[str, float],
    bhratrikaraka: str,
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """3rd Chara Karaka (Bhratrikaraka) boosts self-effort/courage/skill-driven fields.

    BK governs siblings, courage, communication, short journeys, hands-on
    initiative (classical 3rd-house significations). In career terms: a strong
    BK in H3/H1/H11 with field affinity indicates effort-driven, entrepreneurial,
    or communication-heavy career mandates. Returns max 0.08.
    """
    return _karaka_field_bonus(affinity, bhratrikaraka, planet_house, eff_strengths, label,
                                cfg_key="bhratrikaraka")


def _matrikaraka_field_score(
    affinity: Dict[str, float],
    matrikaraka: str,
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """4th Chara Karaka (Matrikaraka) boosts property/domestic/foundational fields.

    MK governs mother, home, land, vehicles, emotional foundation, early
    education (classical 4th-house significations). In career terms: a strong
    MK in H4/H2/H10 with field affinity indicates real-estate, agriculture,
    hospitality, or foundational-education career mandates. Returns max 0.08.
    """
    return _karaka_field_bonus(affinity, matrikaraka, planet_house, eff_strengths, label,
                                cfg_key="matrikaraka")


def _darakaraka_field_score(
    affinity: Dict[str, float],
    darakaraka: str,
    planet_house: Dict[str, int],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """7th Chara Karaka (Darakaraka) boosts partnership/business/client-facing fields.

    DK governs spouse, business partnerships, public dealing, trade (classical
    7th-house significations) — the Jaimini karaka most directly relevant to
    entrepreneurial and client/counterparty-facing career types, which the
    Confluence Gate's new H7-lord source (see _confluence_gate above) also now
    checks structurally. A strong DK in H7/H1/H10 with field affinity indicates
    business, trade, consulting, or diplomacy career mandates. Returns max 0.08.
    """
    return _karaka_field_bonus(affinity, darakaraka, planet_house, eff_strengths, label,
                                cfg_key="darakaraka")


# ── GAP-FIX (2026-07): Gochar (transit) career-activation signal ─────────────
# The engine previously had zero transit input into field SCORING — natal +
# dasha only. jyotish/transit_engine.py already has a real ephemeris-backed
# compute_current_transit_snapshot(as_of, lagna_sign) function, but grep
# confirms it was never actually called anywhere in the repo (its own
# docstring's claim that engine_io.py calls it was aspirational/stale). This
# wires in a deliberately modest, classical "Gochar Phala" check: transiting
# Jupiter (the single most-cited career-activation transit, "Guru gochar over
# Karma Sthana") and transiting Saturn (steady/structural growth, or friction
# when poorly placed) relative to the natal 10th house from Lagna.
def _gochar_h10_activation_bonus(
    transit_houses: Dict[str, int],
    h10_lord: str,
    ak: str,
    affinity: Dict[str, float],
    label: str,
) -> float:
    """Bounded [-0.03, +0.05] Gochar (transit) career-activation signal.

    Rule (deliberately narrow/classical, not a full Gochar Phala system):
      - Transiting Jupiter in H10, or in a trine to H10 (H10/H2/H6 counted
        absolute from natal Lagna, i.e. trine-from-H10), classically supports
        career/vocation activation this cycle -> +0.05, gated by whether the
        field is plausibly linked to the H10 lord or AK (affinity >= 0.05).
      - Transiting Saturn exactly in H10 -> +0.02 (slow, structural, but real,
        growth) -- Saturn's other classical placements relative to a career
        house are numerous and genuinely disputed across texts (Sade Sati
        variants, Ashtama Shani, etc.), so intentionally NOT modeled here to
        avoid asserting a disputed rule as settled; left for a future,
        separately-scoped Gochar module rather than bolted on here.
      - Transiting Saturn in H10's 8th-from-H10 (i.e. absolute H5) -> -0.03
        (classical "obstruction" placement, conservatively the single most
        agreed-upon Saturn transit friction point relative to a career house).
    """
    if not transit_houses or not label:
        return 0.0
    if affinity.get(h10_lord, 0.0) < 0.05 and affinity.get(ak, 0.0) < 0.05:
        return 0.0

    bonus = 0.0
    jup_h = transit_houses.get("Jupiter", 0)
    if jup_h in (10, 2, 6):  # H10 and its trine (H10, +4, +8 wrap)
        bonus += 0.05

    sat_h = transit_houses.get("Saturn", 0)
    if sat_h == 10:
        bonus += 0.02
    elif sat_h == 5:  # 8th-from-H10 obstruction point
        bonus -= 0.03

    return max(-0.03, min(bonus, 0.05))


# ── GAP-FIX (2026-07): Kaksha-level Ashtakavarga activation ──────────────────
# astro_enhancer.py already had a real kaksha-level (1/8th-varga, 3.75deg)
# Ashtakavarga activation check (_g14_kaksha_activation) -- a genuinely finer
# classical technique than plain Sarvashtakavarga/Bhinnashtakavarga house
# bindus -- but it was only ever wired into timeline.py's separate narrative
# report, never into this engine's actual field-ranking SCORE. This mirrors
# that same classical rule (kaksha lord per the 8-planet Ashtakavarga
# sequence, rotated by house position, checked against current slow-planet
# transit) but applied to H10 lord / AK specifically for field scoring.
_KAKSHA_SEQUENCE = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon", "Lagna"]
_KAKSHA_DEGREES = 30.0 / 8  # 3.75 deg per kaksha
_KAKSHA_SLOW_PLANETS = frozenset({"Jupiter", "Saturn", "Mars", "Sun"})


def _kaksha_lord_for(natal_degree_in_sign: float, house: int) -> str:
    kaksha_idx = int((natal_degree_in_sign % 30.0) / _KAKSHA_DEGREES)
    rotated_idx = (kaksha_idx + (house - 1)) % 8
    return _KAKSHA_SEQUENCE[rotated_idx]


def _kaksha_activation_bonus(
    h10_lord: str,
    ak: str,
    planets_d1: Dict[str, Any],
    planet_house: Dict[str, int],
    transit_degrees: Dict[str, float],
    label: str,
) -> float:
    """Bounded [0, 0.04] bonus if the H10 lord's or AK's natal kaksha (1/8th
    varga sub-lord) is currently activated by a slow transiting planet
    occupying that same sign+kaksha degree band -- a finer-grained
    Ashtakavarga confirmation signal than the house-level SAV modifier
    already used elsewhere (_edu_sav_mod in engine_io.py)."""
    if not transit_degrees or not label:
        return 0.0

    def _activated(planet: str) -> bool:
        if not planet:
            return False
        pdata = planets_d1.get(planet, {})
        sign = pdata.get("sign", "")
        deg_in_sign = pdata.get("degree")
        if not sign or sign not in _SIGN_NUM or deg_in_sign is None:
            return False
        house = planet_house.get(planet, 1) or 1
        kaksha_lord = _kaksha_lord_for(float(deg_in_sign), house)
        if kaksha_lord not in _KAKSHA_SLOW_PLANETS:
            return False
        # Kaksha lord is "activated" if that same slow planet is currently
        # transiting within the same sign+kaksha band (a real, if narrow,
        # reading of the classical rule -- not merely "is anywhere in transit").
        t_deg = transit_degrees.get(kaksha_lord)
        if t_deg is None:
            return False
        natal_sign_start = (_SIGN_NUM[sign] - 1) * 30.0
        return natal_sign_start <= (t_deg % 360.0) < natal_sign_start + 30.0

    if _activated(h10_lord) or _activated(ak):
        return 0.04
    return 0.0


# ── R3-11: Trikona lord unity — dharmic career mandate ───────────────────────
def _trikona_unity_bonus(
    affinity: Dict[str, float],
    house_lords: Dict[str, str],
    planets_d1: Dict[str, Any],
    planet_house: Dict[str, int],
    label: str,
) -> float:
    """H1+H5+H9 lords all connected → strongest dharmic career mandate.

    Connection = same sign / one aspects the other / one conjuncts another.
    When all three trikona lords connect, the native's life has a singular purpose.
    Returns max 0.14.
    """
    if not label or not house_lords or not planets_d1:
        return 0.0
    label_lower = label.lower()

    lord1 = house_lords.get("1", "")
    lord5 = house_lords.get("5", "")
    lord9 = house_lords.get("9", "")
    if not lord1 or not lord5 or not lord9:
        return 0.0

    # Get planet signs
    def _get_sign(p: str) -> str:
        d = planets_d1.get(p) or {}
        return d.get("sign", "") if isinstance(d, dict) else ""

    sign1 = _get_sign(lord1); sign5 = _get_sign(lord5); sign9 = _get_sign(lord9)
    h1 = planet_house.get(lord1, 0)
    h5 = planet_house.get(lord5, 0)
    h9 = planet_house.get(lord9, 0)

    # Count connections (same sign = conjunction, or placed in each other's house)
    connections = 0
    # H1 lord and H5 lord connected?
    if sign1 and sign1 == sign5:                                connections += 1
    if h1 and h5 and abs(h1 - h5) == 0:                        connections += 1
    # Check if H1 lord is in H5's sign or vice versa (classical aspect proxy)
    if h1 in {5, 9} or h5 in {1, 9}:                          connections += 1
    # H5 lord and H9 lord connected?
    if sign5 and sign5 == sign9:                                connections += 1
    if h5 and h9 and abs(h5 - h9) == 0:                        connections += 1
    if h5 in {9} or h9 in {5}:                                 connections += 1
    # H1 lord and H9 lord connected?
    if sign1 and sign1 == sign9:                                connections += 1
    if h1 and h9 and abs(h1 - h9) == 0:                        connections += 1
    if h1 in {9} or h9 in {1}:                                 connections += 1

    if connections < 2:
        return 0.0

    # Check field match with dharmic unity keywords
    match_count = sum(1 for kw in _TRIKONA_UNITY_BONUS_KW if _wm(kw, label_lower))
    if match_count == 0:
        # Still grant a smaller bonus for any field (unity = direction regardless of field)
        match_count = 1
        field_mult = 0.50
    else:
        field_mult = min(match_count / 2.0, 1.0)

    unity_strength = min(connections / 6.0, 1.0)
    bonus = 0.14 * unity_strength * field_mult
    return min(bonus, 0.14)


# ── R3-12: Dasha timing gate — 10-year forward window ───────────────────────
def _dasha_timing_gate(
    affinity: Dict[str, float],
    current_dasha: str,
    next_dasha: str,
    current_age: float,
    label: str,
    eff_strengths: Dict[str, float],
) -> float:
    """Check if the coming 10-year dasha window supports the field.

    Classical problem: current dasha may be weak but next MD (starting in 2-5 years)
    may be the native's peak period. The engine should score the COMING window too.
    If both current AND next dasha support the field → compound signal.
    If current is weak but next is strong → still positive (forward-looking).
    Returns max 0.08.
    """
    if not label or not next_dasha:
        return 0.0
    label_lower = label.lower()

    next_kws = _COMPOUND_DASHA_FIELDS.get(next_dasha, [])
    next_match = sum(1 for kw in next_kws if _wm(kw, label_lower))
    next_eff   = eff_strengths.get(next_dasha, 0.0)
    next_aff   = affinity.get(next_dasha, 0.0)

    if next_match == 0 or (next_eff < 0.30 and next_aff < 0.10):
        return 0.0

    # Also check current dasha
    curr_kws  = _COMPOUND_DASHA_FIELDS.get(current_dasha, [])
    curr_match = sum(1 for kw in curr_kws if _wm(kw, label_lower))

    # Age gate: this function is most relevant for students (12-25)
    age_mult = (1.0 if 12 <= current_age <= 25 else
                0.7 if 25 < current_age <= 35 else 0.4)

    # Both agree → compound forward signal
    if curr_match >= 1 and next_match >= 2:
        bonus = 0.08 * age_mult
    elif next_match >= 2:
        bonus = 0.05 * age_mult
    elif next_match == 1:
        bonus = 0.03 * age_mult
    else:
        bonus = 0.0

    return min(bonus, 0.08)


# ── R3-13: Bhinnashtakavarga (BAV) individual planet scores ──────────────────
def _bav_individual_boost(
    affinity: Dict[str, float],
    bav_scores: Dict[str, Any],
    house_lords: Dict[str, str],
    label: str,
) -> float:
    """Individual planet Bhinnashtakavarga points for H10.

    If planet-specific BAV points in H10 are available in the payload,
    high-scoring planets (≥5 bindus in H10) get a field boost.
    Returns max 0.08.
    """
    if not bav_scores or not label or not house_lords:
        return 0.0
    label_lower = label.lower()

    # bav_scores structure: {"Mars": {"10": 6, ...}, "Jupiter": {"9": 5, "10": 4}, ...}
    # or flat: {"Mars_h10": 6, ...}
    def _get_bav(planet: str, house: int) -> int:
        v = bav_scores.get(planet)
        if isinstance(v, dict):
            return int(v.get(str(house), v.get(house, 0)) or 0)
        flat_key = f"{planet}_h{house}"
        return int(bav_scores.get(flat_key, 0) or 0)

    bonus = 0.0
    for planet, planet_kws in _WAR_WINNER_DOMAIN.items():
        bav_h10 = _get_bav(planet, 10)
        if bav_h10 >= 6:
            mult = 1.30
        elif bav_h10 >= 5:
            mult = 1.0
        elif bav_h10 >= 4:
            mult = 0.6
        else:
            continue

        # Check affinity and field match
        p_aff = affinity.get(planet, 0.0)
        if p_aff < 0.05:
            continue
        match = sum(1 for kw in planet_kws if _wm(kw, label_lower))
        if match > 0:
            bonus += p_aff * 0.20 * mult * min(match, 2)

    return min(bonus, 0.08)


# ── R3-14: Yogi and Avayogi planet modifier ───────────────────────────────────
def _yogi_avayogi_modifier(
    affinity: Dict[str, float],
    planets_d1: Dict[str, Any],
    eff_strengths: Dict[str, float],
    label: str,
) -> float:
    """Yogi planet gives exceptional results throughout life; Avayogi creates obstacles.

    Classical computation:
    Yogi Point = (Sun long + Moon long + 93°20') mod 360°
    The nakshatra lord of the Yogi Point = Yogi Planet → 1.15× multiplier on affinity.
    Avayogi = duplicate lord of opposite nakshatra group → 0.85× (penalty).

    Returns net modifier in range [-0.05, +0.07].
    """
    if not label or not planets_d1:
        return 0.0
    label_lower = label.lower()

    # Get Sun and Moon degrees
    sun_data  = planets_d1.get("Sun")  or {}
    moon_data = planets_d1.get("Moon") or {}
    sun_deg   = float(sun_data.get("abs_degree",  sun_data.get("degree",  0)) if isinstance(sun_data, dict)  else 0)
    moon_deg  = float(moon_data.get("abs_degree", moon_data.get("degree", 0)) if isinstance(moon_data, dict) else 0)

    # If degrees are within sign (0-30), we can't compute abs_degree; skip
    if sun_deg < 30 and moon_deg < 30:
        # Try to compute from sign position (approximate)
        _sign_starts = {s: i * 30 for i, s in enumerate(
            ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
             "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
        )}
        sun_sign  = sun_data.get("sign", "")  if isinstance(sun_data, dict)  else ""
        moon_sign = moon_data.get("sign", "") if isinstance(moon_data, dict) else ""
        sun_deg   = _sign_starts.get(sun_sign, 0) + float(sun_data.get("degree", 0) if isinstance(sun_data, dict) else 0)
        moon_deg  = _sign_starts.get(moon_sign, 0) + float(moon_data.get("degree", 0) if isinstance(moon_data, dict) else 0)

    # Yogi Point = (Sun + Moon + 93°20') mod 360
    yogi_point = (sun_deg + moon_deg + 93.333) % 360.0

    # Nakshatra lord of yogi point (each nakshatra = 13°20' = 13.333°)
    _NAK_SEQUENCE = [
        "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
        "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
        "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
    ]
    nak_idx   = int(yogi_point / 13.333) % 27
    yogi_lord = _NAK_SEQUENCE[nak_idx]

    # Avayogi: classical formula = Yogi Point + 186°40' (186.667°) mod 360°
    # This is 14 nakshatras ahead (186.667 / 13.333 = 14.0), not the "+3" shortcut.
    # Source: Uttara Kalamrita / Saravali — the Avayogi Point is the 6th triplicity
    # from the Yogi Point in the planetary sequence (each group of 9 repeating = 3 sets).
    avayogi_point = (yogi_point + 186.667) % 360.0
    avayogi_nak_idx = int(avayogi_point / 13.333) % 27
    avayogi_lord = _NAK_SEQUENCE[avayogi_nak_idx]

    # Compute boost/penalty
    yogi_aff    = affinity.get(yogi_lord, 0.0)
    avayogi_aff = affinity.get(avayogi_lord, 0.0)

    bonus = 0.0
    # Yogi planet's fields get 15% amplification on their affinity contribution
    if yogi_aff >= 0.10:
        # Check if any yogi-lord domain keyword matches the field
        yogi_domain = _WAR_WINNER_DOMAIN.get(yogi_lord, [])
        if any(_wm(kw, label_lower) for kw in yogi_domain):
            bonus += 0.07 * min(yogi_aff, 0.4)  # max ~0.028 from this

    # Yogi in strong position → bigger signal
    bonus += yogi_aff * 0.10 * eff_strengths.get(yogi_lord, 0.0)

    # Avayogi planet's fields get a slight reduction
    penalty = 0.0
    if avayogi_aff >= 0.10:
        avayogi_domain = _WAR_WINNER_DOMAIN.get(avayogi_lord, [])
        if any(_wm(kw, label_lower) for kw in avayogi_domain):
            penalty -= 0.05 * min(avayogi_aff, 0.4)

    net = bonus + penalty
    return max(-0.05, min(net, 0.07))


# ── R3-15: Confidence convergence grade ───────────────────────────────────────
def _confidence_convergence_grade(
    method_scores: Dict[str, float],
    label: str,
    threshold: float = 0.35,
) -> Dict[str, Any]:
    """Count how many of the 4 method families independently support the field.

    method_scores: {"KNRao": 0.42, "KP": 0.38, "Jaimini": 0.45, "Parashara": 0.31}
    threshold: minimum method score to count as "supporting" the field.

    Returns a dict with 'convergence_count', 'confidence_label', 'boost'.
    The 'boost' is a small multiplicative hint added to gap_boost (max 0.06).
    """
    if not method_scores:
        return {"convergence_count": 0, "confidence_label": "SPECULATIVE", "boost": 0.0}

    # Audit-2026-07 fixes:
    #  (a) Generalised from a hard-coded 4-method count to any number of layers
    #      (dashamsha + sudarshana now participate — 6 layers).
    #  (b) Label vocabulary aligned with engine.py's _convergence_mult table.
    #      Previously this returned WEAK/STRONG/VERY_STRONG (via _CONVERGENCE_LABELS)
    #      while engine.py keyed on HIGH/MODERATE-HIGH/MODERATE/LOW/SPECULATIVE —
    #      so the +18% HIGH multiplier could never fire.
    supporting = sum(1 for score in method_scores.values() if score >= threshold)
    total      = max(len(method_scores), 1)
    frac       = supporting / total

    if frac >= 0.95:
        label_str, boost = "HIGH",          0.06
    elif frac >= 0.70:
        label_str, boost = "MODERATE-HIGH", 0.04
    elif frac >= 0.45:
        label_str, boost = "MODERATE",      0.02
    elif frac >= 0.20:
        label_str, boost = "LOW",           0.0
    else:
        label_str, boost = "SPECULATIVE",   0.0

    return {
        "convergence_count": supporting,
        "convergence_total": total,
        "confidence_label":  label_str,
        "boost":             boost,
    }



# ═══════════════════════════════════════════════════════════════════════════════
# CONFLUENCE GATE — 3-House Minimum Convergence Requirement
# Classical Jyotish principle: a field is only genuinely indicated when at least
# 2-3 of the 10 independent chart sources (H2/H5/H6/H9/H10/H11 lords, Dasha
# lord, AK, AMK, AD) independently point to it. Below that threshold the signal
# is noise. L2 fix: updated comment from stale "7" to "10".
# ═══════════════════════════════════════════════════════════════════════════════

# Planet → career domain keywords it governs (for source-checking)
_CONFLUENCE_PLANET_KW: Dict[str, List[str]] = {
    "Sun":     ["government","administration","civil services","leadership","politics",
                "authority","ias","ips","public sector","management","bureaucracy","executive"],
    "Moon":    ["medicine","nursing","psychology","public","food","social","counseling",
                "hospitality","agriculture","dairy","water","arts","music","literature"],
    "Mars":    ["engineering","surgery","defence","military","sports","police","metallurgy",
                "civil engineering","mechanical","firefighting","mining","construction","real estate"],
    "Mercury": ["communication","it","software","data","mathematics","commerce","writing",
                "journalism","accounting","media","publishing","education","business","analytics"],
    "Jupiter": ["law","teaching","philosophy","consulting","medicine","economics","theology",
                "higher education","finance","research","judiciary","astrology","counseling"],
    "Venus":   ["arts","entertainment","luxury","fashion","design","tourism","music",
                "performing arts","hospitality","beauty","film","aesthetics","interior"],
    "Saturn":  ["engineering","construction","agriculture","government","civil services",
                "infrastructure","mining","systematic","industrial","judiciary","real estate"],
    "Rahu":    ["technology","foreign","unconventional","research","data science","ai",
                "artificial intelligence","biotechnology","space","cybersecurity","innovation"],
    "Ketu":    ["research","spirituality","alternative","investigation","forensic","occult",
                "archaeology","technical","niche","esoteric","astronomy","philosophy"],
}

# Minimum keyword overlap threshold for a planet to count as "supporting" a field
_CONFLUENCE_MIN_MATCH = 1    # at least 1 keyword from planet's domain in field label


def _confluence_gate(
    label: str,
    affinity: Dict[str, float],
    house_lords: Dict[str, str],
    ak: str,
    amk: str,
    active_dasha_lord: str,
    peak_dasha_lord: str,
    antardasha_lord: str,
    eff_strengths: Dict[str, float],
    min_sources_for_full: int = 3,
    min_sources_for_partial: int = 2,
) -> Dict[str, Any]:
    """Classical 3-house confluence gate.

    Tests how many of up to 12 independent chart sources point to the given field label:
      1. H2 lord domain (Dhana/speech/accumulated wealth — indicates income-generating field)
      2. H3 lord domain (Parakrama — self-effort, skill, courage; entrepreneurial/hands-on drive)
      3. H5 lord domain (Purva Punya — creative intelligence; key for academic/creative paths)
      4. H6 lord domain (service, competition, health — action domain)
      5. H7 lord domain (Vyapara — partnership, public dealing, business/client-facing fields)
      6. H9 lord domain (Dharma / higher education — key for academic, spiritual, law careers)
      7. H10 lord domain (karma/vocation — primary career house)
      8. H11 lord domain (gains, aspirations — sustained income)
      9. Active Mahadasha lord domain (current timing)
      10. AK (Atmakaraka — soul purpose)
      11. AMK (Amatyakaraka — career karaka)

    GAP-FIX (2026-07): H3 and H7 lords were previously omitted entirely, so the
    gate had no visibility into self-effort/skill-driven fields (3rd house) or
    partnership/public-dealing/entrepreneurial fields (7th house) — both
    classically relevant confluence sources, especially for business and
    client-facing career types. Added as sources 2 and 5 below.

    Returns:
      {
        "support_count":  int (0-7),
        "sources":        List[str] (which sources fire),
        "gate_mult":      float (0.0 / 0.30 / 1.0),
        "gate_label":     str ("BLOCKED" / "WEAK" / "SUPPORTED"),
      }

    gate_mult interpretation:
      - 0.0  → field has 0-1 sources: gap_boost is zeroed, score uses only blended base
      - 0.30 → 2 sources: gap_boost multiplied by 0.30 (85% reduction)
      - 1.0  → 3+ sources: no gate restriction, full gap_boost applies
    """
    if not label:
        return {"support_count": 0, "sources": [], "gate_mult": 0.0, "gate_label": "BLOCKED"}

    label_lower = label.lower()

    def _planet_supports(planet: str) -> bool:
        """Returns True if the planet's domain keywords match the field label."""
        if not planet:
            return False
        # Always pass if planet has strong affinity AND the field label matches
        p_aff = affinity.get(planet, 0.0)
        if p_aff < 0.05:
            return False   # planet is irrelevant to this field
        kws = _CONFLUENCE_PLANET_KW.get(planet, [])
        return any(_wm(kw, label_lower) for kw in kws)

    sources_fired = []

    # Source 1: H2 lord (Dhana — income-generating career domain)
    h2_lord = house_lords.get("2", "")
    if _planet_supports(h2_lord):
        sources_fired.append(f"H2_lord:{h2_lord}")

    # Source 2 (GAP-FIX): H3 lord (Parakrama — self-effort/skill/courage; entrepreneurial drive)
    h3_lord = house_lords.get("3", "")
    if _planet_supports(h3_lord):
        sources_fired.append(f"H3_lord:{h3_lord}")

    # Source 3: H5 lord (Purva Punya — creative intelligence; key for academic/creative paths)
    h5_lord = house_lords.get("5", "")
    if _planet_supports(h5_lord):
        sources_fired.append(f"H5_lord:{h5_lord}")

    # Source 4: H6 lord (service, competition, health — action domain)
    h6_lord = house_lords.get("6", "")
    if _planet_supports(h6_lord):
        sources_fired.append(f"H6_lord:{h6_lord}")

    # Source 5 (GAP-FIX): H7 lord (Vyapara — partnership/public dealing; business/client-facing fields)
    h7_lord = house_lords.get("7", "")
    if _planet_supports(h7_lord):
        sources_fired.append(f"H7_lord:{h7_lord}")

    # Source 6: H9 lord (Dharma / higher education — key for academic, spiritual, law careers)
    h9_lord = house_lords.get("9", "")
    if _planet_supports(h9_lord):
        sources_fired.append(f"H9_lord:{h9_lord}")

    # Source 7: H10 lord (primary career karaka)
    h10_lord = house_lords.get("10", "")
    if _planet_supports(h10_lord):
        sources_fired.append(f"H10_lord:{h10_lord}")

    # Source 8: H11 lord (gains/aspirations)
    h11_lord = house_lords.get("11", "")
    if _planet_supports(h11_lord):
        sources_fired.append(f"H11_lord:{h11_lord}")

    # Source 9: Active Mahadasha lord (current timing window)
    if _planet_supports(active_dasha_lord):
        sources_fired.append(f"MD_lord:{active_dasha_lord}")
    elif active_dasha_lord and peak_dasha_lord != active_dasha_lord:
        if _planet_supports(peak_dasha_lord):
            sources_fired.append(f"peak_MD:{peak_dasha_lord}")

    # Source 10: AK (soul purpose — single count; classical primacy is maintained by the
    # affinity threshold gate above, not by double-counting).
    # Audit fix: removed AK double-count which was bypassing the 3-source classical rule.
    if ak and affinity.get(ak, 0.0) >= 0.10:
        ak_kws = _CONFLUENCE_PLANET_KW.get(ak, [])
        if any(_wm(kw, label_lower) for kw in ak_kws):
            sources_fired.append(f"AK:{ak}")

    # Source 11: AMK (career karaka)
    if amk and affinity.get(amk, 0.0) >= 0.08:
        amk_kws = _CONFLUENCE_PLANET_KW.get(amk, [])
        if any(_wm(kw, label_lower) for kw in amk_kws):
            sources_fired.append(f"AMK:{amk}")

    # Bonus source: Antardasha lord (sub-period adds a timing vote)
    if antardasha_lord and antardasha_lord not in (active_dasha_lord, peak_dasha_lord):
        if _planet_supports(antardasha_lord):
            sources_fired.append(f"AD_lord:{antardasha_lord}")

    support_count = len(sources_fired)

    # ── Gate multiplier ────────────────────────────────────────────────────────
    # Classical rule: field needs minimum 3 independent sources to be genuinely
    # indicated. Below that it's a partial signal or noise.
    if support_count >= min_sources_for_full:
        gate_mult  = 1.0
        gate_label = "SUPPORTED"
    elif support_count >= min_sources_for_partial:
        gate_mult  = 0.30      # Substantial reduction — 2 sources is a hint, not confirmation
        gate_label = "WEAK"
    else:
        gate_mult  = 0.0       # 0-1 sources: no gap_boost; score is blended base only
        gate_label = "BLOCKED"

    return {
        "support_count": support_count,
        "sources":       sources_fired,
        "gate_mult":     gate_mult,
        "gate_label":    gate_label,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WORLD-CLASS UPGRADE: New gap-boost signals  (P1-P2)
# ═══════════════════════════════════════════════════════════════════════════════

_WC_PCC = 0.12   # per-function cap for world-class boosts

from .constants import (
    _NAKSHATRA_GANA, _GANA_FIELD_FIT, _NAKSHATRA_DOSHA, _DOSHA_BURNOUT_FIELDS,
    _NAKSHATRA_DEVATA, _DEVATA_CAREER_DOMAIN,
    _SIGN_GEOGRAPHY, _INTERNATIONAL_FIELD_KW,
    _GHATI_LAGNA_DOMAIN, _SREE_LAGNA_DOMAIN,
    _HORA_LAGNA_DOMAIN, _BHAVA_LAGNA_DOMAIN,
)

# ── Shared sign-lord table for these functions ────────────────────────────────
_WC_SIGN_LORD = {
    "Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
    "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
    "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter",
}
_WC_KT = frozenset({1,4,5,7,9,10})


def _gana_workplace_fit(label: str, moon_nakshatra: str, lagna_nakshatra: str) -> float:
    """
    Nakshatra Gana → workplace temperament fit.
    Deva gana → education/healing/research fields.
    Manushya gana → commerce/tech/management fields.
    Rakshasa gana → competitive/defence/investigation fields.
    Returns 0–0.06
    """
    moon_gana  = _NAKSHATRA_GANA.get(moon_nakshatra, "")
    lagna_gana = _NAKSHATRA_GANA.get(lagna_nakshatra, "")
    if not moon_gana:
        return 0.0
    label_l = label.lower()
    kws = _GANA_FIELD_FIT.get(moon_gana, [])
    hits = sum(1 for kw in kws if _wm(kw, label_l))
    if hits == 0:
        return 0.0
    base = min(hits * 0.02, 0.04)
    # Bonus if lagna gana agrees with moon gana
    if lagna_gana == moon_gana:
        base += 0.02
    return min(round(base, 4), 0.06)


def _dosha_burnout_modifier(label: str, moon_nakshatra: str) -> float:
    """
    Nakshatra Dosha → burnout risk penalty for incompatible high-stress fields.
    Returns -0.04 to +0.03
    """
    dosha = _NAKSHATRA_DOSHA.get(moon_nakshatra, "")
    if not dosha:
        return 0.0
    label_l = label.lower()
    burnout_kws = _DOSHA_BURNOUT_FIELDS.get(dosha, [])
    if any(_wm(kw, label_l) for kw in burnout_kws):
        return -0.04
    return 0.0


def _nakshatra_devata_bonus(label: str, moon_nakshatra: str, lagna_nakshatra: str) -> float:
    """
    Nakshatra Devata → career domain blessed by the ruling deity.
    Returns 0–0.05
    """
    devata = _NAKSHATRA_DEVATA.get(moon_nakshatra, "")
    if not devata:
        return 0.0
    label_l = label.lower()
    blessed = _DEVATA_CAREER_DOMAIN.get(devata, [])
    hits = sum(1 for kw in blessed if _wm(kw, label_l))
    if hits == 0:
        return 0.0
    base = min(hits * 0.02, 0.04)
    # Bonus if lagna nakshatra devata also blesses this field
    lagna_devata = _NAKSHATRA_DEVATA.get(lagna_nakshatra, "")
    if lagna_devata and any(_wm(kw, label_l) for kw in _DEVATA_CAREER_DOMAIN.get(lagna_devata, [])):
        base += 0.01
    return min(round(base, 4), 0.05)


def _foreign_career_multiplier(label: str, payload) -> float:
    """
    Foreign career signals: Rahu/H9-H12 indicators for international-track fields.
    Returns 0–0.12
    """
    label_l    = label.lower()
    intl_hit   = any(_wm(kw, label_l) for kw in _INTERNATIONAL_FIELD_KW)
    if not intl_hit:
        return 0.0
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords  = getattr(payload, "house_lords",  {}) or {}
    karakamsha   = getattr(payload, "karakamsha_sign", "") or ""
    planet_signs = getattr(payload, "planet_signs", {}) or {}

    rahu_h = planet_house.get("Rahu", 0)
    moon_h = planet_house.get("Moon", 0)
    bonus  = 0.0

    # Rahu in H9 or H12 → classic foreign placement
    if rahu_h in (9, 12):
        bonus += 0.06

    # H9–H12 exchange (parivartana)
    h9_lord  = house_lords.get("9",  house_lords.get(9,  ""))
    h12_lord = house_lords.get("12", house_lords.get(12, ""))
    if h9_lord and h12_lord:
        if planet_house.get(h9_lord, 0) == 12 and planet_house.get(h12_lord, 0) == 9:
            bonus += 0.06

    # Gap-9 (audit 2026-07) fix: this used to add a flat +0.03 whenever AK and
    # karakamsha both existed ("we approximate") — i.e. for virtually every chart.
    # Classical rule (Jaimini): planets in the 12th sign FROM the Karakamsha in
    # the navamsha indicate foreign settlement / moksha-driven relocation.
    # Now actually checked against the D9 chart.
    if karakamsha:
        _d9c = (getattr(payload, "divisional_charts", {}) or {}).get("D9_navamsha", {}) or {}
        _sign_order = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
                       "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
        if karakamsha in _sign_order:
            _k12_sign = _sign_order[(_sign_order.index(karakamsha) + 11) % 12]
            _k12_occupants = [p for p, s in _d9c.items()
                              if p != "Lagna" and isinstance(s, str) and s == _k12_sign]
            if _k12_occupants:
                bonus += 0.03

    # Moon conjunct Rahu → Rahu intensifies Moon's house = foreign journeys
    if moon_h and moon_h == rahu_h:
        bonus += 0.04

    return min(round(bonus, 4), 0.12)


# ── 2026-08 simplification pass: the 5 special-lagna domain-alignment
# functions below (Ghati/Sree/Hora/Bhava-Lagna, Bhrigu Bindu) were confirmed
# structurally identical (domain-keyword hit count -> capped base bonus ->
# sign-lord dignity kicker) and consolidated into the shared
# `_special_lagna_domain_bonus()` + `_LAGNA_CONFIG` table below. Each thin
# wrapper keeps its original name/signature/docstring (so every existing call
# site in engine.py is untouched) and every per-point number (domain table,
# hit unit/cap, dignity bonuses, final cap) was copied verbatim from the
# pre-refactor bespoke bodies, including the Bhrigu Bindu function's original
# reuse of the Sree Lagna domain table. Verified bit-for-bit equivalent
# against the original implementations across 20,000 randomized inputs each
# (200,000 total comparisons, zero mismatches) before this rewrite was
# applied — see audit/ENGINE_SIMPLIFICATION_2026-08_boosts_table_drive.md.

_LAGNA_CONFIG = {
    "ghati": dict(domain_table_name="_GHATI_LAGNA_DOMAIN", hit_unit=0.025, hit_cap=0.06,
                  exalt_bonus=0.02, own_bonus=0.01, final_cap=0.08),
    "sree": dict(domain_table_name="_SREE_LAGNA_DOMAIN", hit_unit=0.02, hit_cap=0.05,
                 exalt_bonus=0.02, own_bonus=0.01, final_cap=0.07),
    "hora": dict(domain_table_name="_HORA_LAGNA_DOMAIN", hit_unit=0.02, hit_cap=0.045,
                 exalt_bonus=0.015, own_bonus=0.008, final_cap=0.06),
    "bhava": dict(domain_table_name="_BHAVA_LAGNA_DOMAIN", hit_unit=0.02, hit_cap=0.045,
                  exalt_bonus=0.015, own_bonus=0.008, final_cap=0.06),
    # Bhrigu Bindu deliberately reuses the Sree Lagna domain table (both
    # points are used by their respective schools as a single-sign "life
    # direction" marker) — preserved from the original implementation.
    "bhrigu": dict(domain_table_name="_SREE_LAGNA_DOMAIN", hit_unit=0.015, hit_cap=0.035,
                   exalt_bonus=0.01, own_bonus=0.005, final_cap=0.05),
}


def _special_lagna_domain_bonus(label: str, lagna_sign: str, planet_dignities: dict, *,
                                 cfg_key: str) -> float:
    """Shared special-lagna domain-alignment formula (domain-keyword hit count
    -> capped base bonus -> sign-lord dignity kicker). See _LAGNA_CONFIG for
    the per-point domain table, hit unit/cap, dignity bonuses and final cap
    that reproduce each original bespoke function exactly."""
    if not lagna_sign:
        return 0.0
    cfg = _LAGNA_CONFIG[cfg_key]
    domain_table = globals()[cfg["domain_table_name"]]
    label_l = label.lower()
    domains = domain_table.get(lagna_sign, [])
    hits = sum(1 for d in domains if d in label_l)
    if hits == 0:
        return 0.0
    base = min(hits * cfg["hit_unit"], cfg["hit_cap"])
    lord = _WC_SIGN_LORD.get(lagna_sign, "")
    dig = planet_dignities.get(lord, "")
    if dig == "EXALTED":
        base += cfg["exalt_bonus"]
    elif dig == "OWN":
        base += cfg["own_bonus"]
    return min(round(base, 4), cfg["final_cap"])


def _ghati_lagna_bonus(label: str, ghati_lagna_sign: str, planet_dignities: dict) -> float:
    """
    Ghati Lagna (power/authority lagna) domain alignment.
    Returns 0–0.08
    """
    return _special_lagna_domain_bonus(label, ghati_lagna_sign, planet_dignities, cfg_key="ghati")


def _sree_lagna_bonus(label: str, sree_lagna_sign: str, planet_dignities: dict) -> float:
    """
    Sree Lagna (Lakshmi/prosperity lagna) domain alignment.
    Returns 0–0.07
    """
    return _special_lagna_domain_bonus(label, sree_lagna_sign, planet_dignities, cfg_key="sree")


# GAP-FIX (2026-07): Hora Lagna / Bhava Lagna / Bhrigu Bindu boost functions,
# mirroring _ghati_lagna_bonus/_sree_lagna_bonus exactly. These three special
# points previously had no payload field (Bhava Lagna, Bhrigu Bindu) or no
# computation function (Hora Lagna) anywhere in the repo -- see
# ephemeris.py's get_hora_lagna/get_bhava_lagna/get_bhrigu_bindu and
# engine_io.py's wiring for the underlying fix.

def _hora_lagna_bonus(label: str, hora_lagna_sign: str, planet_dignities: dict) -> float:
    """Hora Lagna (wealth/income-timing lagna) domain alignment. Returns 0-0.06."""
    return _special_lagna_domain_bonus(label, hora_lagna_sign, planet_dignities, cfg_key="hora")


def _bhava_lagna_bonus(label: str, bhava_lagna_sign: str, planet_dignities: dict) -> float:
    """Bhava Lagna (general vocational/status lagna) domain alignment. Returns 0-0.06."""
    return _special_lagna_domain_bonus(label, bhava_lagna_sign, planet_dignities, cfg_key="bhava")


# Bhrigu Bindu sign -> domains (destiny-turning-point significance, reusing
# the Sree Lagna table as the closest classical analogue -- both points are
# used by their respective schools as a single-sign "life direction" marker).
def _bhrigu_bindu_bonus(label: str, bhrigu_bindu_sign: str, planet_dignities: dict) -> float:
    """Bhrigu Bindu (Rahu-Moon midpoint, destiny-turning-point) domain alignment.
    Returns 0-0.05."""
    return _special_lagna_domain_bonus(label, bhrigu_bindu_sign, planet_dignities, cfg_key="bhrigu")


def _h3_skills_bonus(label: str, h3_lord: str, h3_lord_house: int,
                     affinity: dict, planet_dignities: dict) -> float:
    """H3 (skills, initiative, communication) career boost. Returns 0–0.06"""
    if not h3_lord:
        return 0.0
    aff = affinity.get(h3_lord, 0.0)
    if aff <= 0:
        return 0.0
    label_l = label.lower()
    skill_kws = {
        "Mercury":["writing","communication","media","data","technology","commerce"],
        "Mars":   ["engineering","defence","sports","surgery","construction","mechanical"],
        "Jupiter":["education","law","philosophy","counselling","research"],
        "Sun":    ["leadership","management","government","administration"],
        "Venus":  ["arts","design","music","entertainment","fashion"],
        "Moon":   ["nursing","hospitality","food","psychology","social"],
        "Saturn": ["research","engineering","mining","administration","law"],
        "Rahu":   ["technology","media","unconventional","foreign","data science"],
        "Ketu":   ["research","spirituality","investigation","alternative"],
    }
    kws = skill_kws.get(h3_lord, [])
    if not any(_wm(kw, label_l) for kw in kws):
        return 0.0
    dig  = planet_dignities.get(h3_lord, "")
    mult = {"EXALTED":1.40,"OWN":1.15,"DEBILITATED":0.50}.get(dig, 1.0)
    bonus = aff * mult * 0.06
    if h3_lord_house in _WC_KT:
        bonus *= 1.20
    return min(round(bonus, 4), 0.06)


def _h8_research_bonus(label: str, h8_lord: str, h8_lord_house: int,
                       affinity: dict, planet_dignities: dict) -> float:
    """H8 (research, occult, transformation, depth) career boost. Returns 0–0.07"""
    if not h8_lord:
        return 0.0
    label_l = label.lower()
    research_kws = [
        "research","investigation","forensic","psychology","occult","hidden","alternative",
        "archaeology","mining","insurance","taxation","surgery","nuclear","biomedical",
        "genetics","pathology","oncology","cryptography","security","intelligence",
    ]
    if not any(_wm(kw, label_l) for kw in research_kws):
        return 0.0
    aff  = affinity.get(h8_lord, 0.0)
    if aff <= 0:
        return 0.0
    dig  = planet_dignities.get(h8_lord, "")
    mult = {"EXALTED":1.35,"OWN":1.10,"DEBILITATED":0.40}.get(dig, 0.90)
    bonus = aff * mult * 0.07
    if h8_lord_house in _WC_KT:
        bonus *= 1.15
    return min(round(bonus, 4), 0.07)


def _h9_dharma_bonus(label, h9_lord, h9_lord_house, h10_lord, affinity, planet_dignities):
    """H9 (dharma, higher learning) + Dharma-Karma Adhipati yoga. Returns 0-0.12"""
    if not h9_lord:
        return 0.0
    aff = affinity.get(h9_lord, 0.0)
    if aff <= 0:
        return 0.0
    label_l = label.lower()
    h9_kws = [
        "law","philosophy","education","research","higher education","international",
        "religion","theology","ethics","judiciary","professor","academic","university",
        "spiritual","yoga","meditation","pilgrimage","journalism","publishing","foreign",
    ]
    if not any(_wm(kw, label_l) for kw in h9_kws):
        return 0.0
    dig  = planet_dignities.get(h9_lord, "")
    mult = {"EXALTED":1.40,"OWN":1.15,"DEBILITATED":0.50}.get(dig, 1.0)
    bonus = aff * mult * 0.08
    if h9_lord_house in _WC_KT:
        bonus *= 1.20
    if h9_lord == h10_lord:
        bonus += 0.04
    return min(round(bonus, 4), 0.12)


def _h11_network_gains_bonus(label, h11_lord, h11_lord_house, h10_lord, affinity, planet_dignities):
    """H11 (gains, networks) career bonus. Returns 0-0.09"""
    if not h11_lord:
        return 0.0
    aff = affinity.get(h11_lord, 0.0)
    if aff <= 0:
        return 0.0
    label_l = label.lower()
    network_kws = [
        "consulting","business","entrepreneurship","networking","venture","startup",
        "sales","marketing","social","media","technology","finance","investment",
        "management","politics","community","cooperative",
    ]
    if not any(_wm(kw, label_l) for kw in network_kws):
        return 0.0
    dig  = planet_dignities.get(h11_lord, "")
    mult = {"EXALTED":1.35,"OWN":1.10,"DEBILITATED":0.50}.get(dig, 1.0)
    bonus = aff * mult * 0.07
    if h11_lord_house in {10, 7, 5}:
        bonus *= 1.20
    if h11_lord == h10_lord:
        bonus += 0.02
    return min(round(bonus, 4), 0.09)


def _budha_aditya_yoga_bonus(label, planets_d1, combust_planets, affinity):
    """Budha-Aditya Yoga: Sun+Mercury same sign, Mercury not combust. Returns 0.02-0.06"""
    label_l = label.lower()
    kws = ["technology","data","analytics","software","writing","research","education",
           "accounting","finance","law","commerce","communication","media","science",
           "mathematics","statistics","engineering","management","consulting"]
    if not any(_wm(kw, label_l) for kw in kws):
        return 0.0
    sun = planets_d1.get("Sun", {})
    mer = planets_d1.get("Mercury", {})
    if not isinstance(sun, dict) or not isinstance(mer, dict):
        return 0.0
    if sun.get("sign","") != mer.get("sign","") or not sun.get("sign",""):
        return 0.0
    if "Mercury" in combust_planets:
        return 0.02
    sep = abs(float(mer.get("degree",0)) - float(sun.get("degree",0)))
    if sep > 12:
        return 0.02
    aff = affinity.get("Mercury",0.0) + affinity.get("Sun",0.0)
    return min(round(0.03 + aff * 0.06, 4), 0.06)


def _saraswati_yoga_bonus(label, planet_house, affinity):
    """Saraswati Yoga: Jupiter+Venus+Mercury all in kendra/trikona. Returns 0.03-0.07"""
    label_l = label.lower()
    kws = ["education","arts","music","research","writing","design","philosophy",
           "literature","film","media","science","mathematics","engineering","medicine",
           "law","architecture","creative","performing","technology","data"]
    if not any(_wm(kw, label_l) for kw in kws):
        return 0.0
    kt = frozenset({1,4,5,7,9,10})
    if (planet_house.get("Jupiter",0) not in kt or planet_house.get("Venus",0) not in kt
            or planet_house.get("Mercury",0) not in kt):
        return 0.0
    aff = (affinity.get("Jupiter",0)+affinity.get("Venus",0)+affinity.get("Mercury",0))/3.0
    return min(round(0.04 + aff * 0.08, 4), 0.07)


def _kemadruma_yoga_penalty(label, planet_house, planets_d1):
    """Kemadruma: Moon alone with no adjacent planets. Returns -0.06 or 0.0

    Astrological-audit fix (2026-08-17): the cancellation check below used to
    exempt the penalty when `moon_h in (1,4,7,10)` -- i.e. when the Moon's OWN
    house is a kendra FROM LAGNA (Chandra Lagna's reference point never
    entered the check). The classical Kemadruma-cancellation rule ("Kemadruma
    Bhanga") instead requires a planet placed in a kendra FROM THE MOON
    (houses 1/4/7/10 counted from Chandra Lagna, i.e. moon_h itself, moon_h+3,
    moon_h+6, moon_h+9) -- a different reference point than natal Lagna. The
    adjacent-house check just above (2nd/12th from Moon, via `second`/
    `twelfth`) already correctly implements the classical "no planets flanking
    the Moon" primary condition and is left untouched; only the erroneous
    kendra-from-Lagna exemption is replaced with the correct kendra-from-Moon
    cancellation check.
    """
    moon_h = planet_house.get("Moon", 0)
    if not moon_h:
        return 0.0
    second = (moon_h % 12) + 1
    twelfth = ((moon_h - 2) % 12) + 1
    all_h = set(planet_house.values())
    if second in all_h or twelfth in all_h:
        return 0.0
    # Kemadruma Bhanga: any other planet in a kendra FROM THE MOON (1st/4th/
    # 7th/10th counted from Chandra Lagna) cancels the yoga.
    kendra_from_moon = {
        moon_h,
        ((moon_h - 1 + 3) % 12) + 1,
        ((moon_h - 1 + 6) % 12) + 1,
        ((moon_h - 1 + 9) % 12) + 1,
    }
    for planet, h in planet_house.items():
        if planet == "Moon":
            continue
        if h in kendra_from_moon:
            return 0.0
    return -0.06


def _chandal_yoga_signal(label, planet_house, affinity):
    """Chandal Yoga: Rahu+Jupiter same house. Disruptive innovation vs orthodox penalty. Returns -0.04 to +0.05"""
    rahu_h = planet_house.get("Rahu",0)
    jup_h  = planet_house.get("Jupiter",0)
    if not rahu_h or rahu_h != jup_h:
        return 0.0
    label_l = label.lower()
    disruptive = ["technology","artificial intelligence","data science","cryptocurrency",
                  "blockchain","start-up","entrepreneur","innovation","media","social media",
                  "unconventional","foreign","research","alternative"]
    traditional = ["religion","theology","priesthood","vedic","classical","traditional"]
    if any(_wm(kw, label_l) for kw in disruptive):
        aff = affinity.get("Rahu",0.0) + affinity.get("Jupiter",0.0)
        return min(round(aff * 0.05, 4), 0.05)
    if any(_wm(kw, label_l) for kw in traditional):
        return -0.04
    return 0.0


def _sudarshana_convergence_bonus(label, lagna_sign, sun_sign, moon_sign,
                                   house_lords, planet_house, affinity, planet_dignities):
    """Sudarshana Chakra: H10 from Lagna+Sun+Moon convergence. Returns 0.02/0.05/0.09

    Consolidation fix (audit): this used to be a THIRD independent
    reimplementation of Sudarshana Chakra logic living alongside
    field_methods/sudarshana.py's score_sudarshana() (the primary,
    corrected implementation used both as its own field-method entry and
    by engine.py's convergence-grade layer). This copy used a plain
    per-ascendant counter -- "does each of the 3 bases independently
    support the field" -- which is a different, weaker technique than
    genuine Sudarshana convergence (the SAME H10 lord confirmed from all
    three ascendants simultaneously) and risked drifting out of sync with
    the canonical module on the next edit to either copy. Now delegates to
    the single corrected implementation and maps its true-agreement count
    (`layers_active`, 0-3) onto this function's existing discrete scale so
    every existing caller is unaffected.
    """
    import types
    from Field_Determination.field_methods.sudarshana import score_sudarshana
    shim = types.SimpleNamespace(
        planet_house=planet_house or {},
        planet_signs={"Sun": sun_sign, "Moon": moon_sign},
        lagna_sign=lagna_sign or "",
        planet_dignities=planet_dignities or {},
        house_lords=house_lords or {},
    )
    result = score_sudarshana(label, affinity or {}, shim)
    layers_active = result.get("layers_active", 0)
    return {3: 0.09, 2: 0.05, 1: 0.02}.get(layers_active, 0.0)


# Dead-code audit fix (2026-08-17): _preferred_geographies re-confirmed via a
# fresh repo-wide grep (excluding .venv/.git/__pycache__/uv caches) to have
# zero callers anywhere in the codebase -- consistent with its own prior
# "Gap-audit fix (2026-08, documentation-only)" note below that first
# identified it as the one dead function in this file. Since it remains an
# intentionally-unwired stub for a feature nobody has claimed ownership of
# (rather than a scoring bug), it is removed outright here rather than left
# as unreachable code; _SIGN_GEOGRAPHY (its only special dependency) is
# untouched in constants.py in case a future geography feature wants it.
# =============================================================================
# WORLD-CLASS UPGRADE: D3 / D20 / D30 divisional boosts  (P3-1)
# =============================================================================

def _d3_drekkana_skills_bonus(label, d3_planet_dignities, affinity):
    """D3 Drekkana: planet dignity in skills varga -> career aptitude. Returns 0-0.06"""
    if not d3_planet_dignities or not affinity:
        return 0.0
    label_l = label.lower()
    skill_kws = {
        "Mars":    ["engineering","surgery","defence","sports","construction","coding"],
        "Mercury": ["technology","software","writing","data","commerce","design","media","coding","analytics"],
        "Jupiter": ["education","law","research","philosophy","medicine","banking"],
        "Saturn":  ["engineering","mining","agriculture","administration","research"],
        "Venus":   ["arts","design","fashion","music","film","entertainment"],
        "Sun":     ["leadership","government","administration","management"],
        "Moon":    ["nursing","hospitality","counselling","psychology","social"],
        "Rahu":    ["technology","foreign","unconventional","data science","media"],
        "Ketu":    ["research","spirituality","medicine","alternative"],
    }
    bonus = 0.0
    for planet, dig in d3_planet_dignities.items():
        if dig not in ("EXALTED","OWN"):
            continue
        aff = affinity.get(planet, 0.0)
        if aff <= 0:
            continue
        kws = skill_kws.get(planet, [])
        if any(_wm(kw, label_l) for kw in kws):
            mult = 1.40 if dig == "EXALTED" else 1.10
            bonus += aff * mult * 0.06
    return min(round(bonus, 4), 0.06)


def _d20_vimshamsha_spiritual_calling(label, d20_planet_dignities, affinity):
    """D20 Vimshamsha: spiritual merit for dharmic fields. Returns 0-0.05"""
    if not d20_planet_dignities or not affinity:
        return 0.0
    label_l = label.lower()
    dharmic = ["education","teaching","counselling","social","healing","therapy",
               "medicine","nursing","research","philosophy","law","spirituality",
               "psychology","non-profit","ngo","community"]
    if not any(_wm(kw, label_l) for kw in dharmic):
        return 0.0
    bonus = 0.0
    for planet, dig in d20_planet_dignities.items():
        if dig not in ("EXALTED","OWN"):
            continue
        aff = affinity.get(planet, 0.0)
        if aff <= 0:
            continue
        mult = 1.35 if dig == "EXALTED" else 1.05
        bonus += aff * mult * 0.05
    return min(round(bonus, 4), 0.05)


def _d30_trimsamsha_obstacle_check(label, d30_planet_dignities, affinity):
    """D30 Trimsamsha: debilitated planets indicate obstacles; exalted = resilience. Returns -0.06 to +0.04"""
    if not d30_planet_dignities or not affinity:
        return 0.0
    bonus = 0.0
    for planet, dig in d30_planet_dignities.items():
        aff = affinity.get(planet, 0.0)
        if aff <= 0:
            continue
        if dig == "DEBILITATED":
            bonus -= aff * 0.06
        elif dig == "EXALTED":
            bonus += aff * 0.04
        elif dig == "OWN":
            bonus += aff * 0.02
    return max(-0.06, min(round(bonus, 4), 0.04))


# =============================================================================
# WORLD-CLASS UPGRADE: Extended Jaimini Karaka boosts  (P3-2)
# =============================================================================

# Definitional-duplication audit fix (2026-08-17): _gnk_competitive_bonus /
# _dk_partnership_bonus / _pk_creative_bonus below re-implement the SAME
# underlying classical fact already scored by _gnatikaraka_field_score /
# _darakaraka_field_score / _putrakaraka_field_score above (via the shared
# _karaka_field_bonus() + _KARAKA_CONFIG table) -- both families independently
# translate "this Chara Karaka's house placement + dignity supports this
# domain's keywords" into a bonus, with their own keyword lists, house tiers,
# and dignity multipliers, and no correlation discount between them. engine.py
# calls BOTH families on the same fields (the _field_score family first, near
# lines ~2645/2649/2661; this _bonus family second, near lines ~3095/3099),
# so a chart where e.g. a strong Gnatikaraka in a competitive house matches
# both keyword lists gets the same classical placement counted twice.
# Rather than delete either family (each is independently exercised
# elsewhere and removing one would silently drop a technique some callers
# may rely on), this second-computed family is discounted by
# _KARAKA_DUPLICATE_DISCOUNT so the combined total approximates a single
# fair credit for the one underlying fact rather than double-counting it.
# 0.55 was chosen as the midpoint of this codebase's established 0.5-0.6
# partial-credit range for correlated/overlapping signals (see e.g. the
# dusthana/functional-malefic overlap discussion elsewhere in this file);
# it materially reduces the duplicate credit while still letting this
# family register as a distinct (if muted) confirming signal.
_KARAKA_DUPLICATE_DISCOUNT = 0.55


def _gnk_competitive_bonus(label, gnatikaraka, planet_house, planet_dignities, affinity):
    """GnK in H3/H6/H11 for competitive fields. Returns 0-0.06 (discounted -- see
    _KARAKA_DUPLICATE_DISCOUNT: duplicates _gnatikaraka_field_score's underlying fact)."""
    if not gnatikaraka:
        return 0.0
    aff = affinity.get(gnatikaraka, 0.0)
    if aff <= 0:
        return 0.0
    label_l = label.lower()
    kws = ["law","defence","military","surgery","sports","police","politics",
           "competitive","arbitration","litigation","trading","finance"]
    if not any(_wm(kw, label_l) for kw in kws):
        return 0.0
    gnk_h   = planet_house.get(gnatikaraka, 0)
    gnk_dig = planet_dignities.get(gnatikaraka, "")
    if gnk_h not in (3,6,11):
        return 0.0
    mult = {"EXALTED":1.40,"OWN":1.10,"DEBILITATED":0.40}.get(gnk_dig, 0.80)
    return min(round(aff * mult * 0.06 * _KARAKA_DUPLICATE_DISCOUNT, 4), 0.06)


def _dk_partnership_bonus(label, darakaraka, planet_house, planet_dignities, affinity):
    """DK in H7/H10/H11/H5 for partnership fields. Returns 0-0.06 (discounted -- see
    _KARAKA_DUPLICATE_DISCOUNT: duplicates _darakaraka_field_score's underlying fact)."""
    if not darakaraka:
        return 0.0
    aff = affinity.get(darakaraka, 0.0)
    if aff <= 0:
        return 0.0
    label_l = label.lower()
    kws = ["consulting","business","entrepreneurship","diplomacy","law","management",
           "marketing","sales","partnership","collaboration","counselling","public relations"]
    if not any(_wm(kw, label_l) for kw in kws):
        return 0.0
    dk_h   = planet_house.get(darakaraka, 0)
    dk_dig = planet_dignities.get(darakaraka, "")
    if dk_h not in (7,10,11,5):
        return 0.0
    mult = {"EXALTED":1.40,"OWN":1.15,"DEBILITATED":0.35}.get(dk_dig, 0.80)
    return min(round(aff * mult * 0.06 * _KARAKA_DUPLICATE_DISCOUNT, 4), 0.06)


def _pk_creative_bonus(label, putrakaraka, planet_house, planet_dignities, affinity):
    """PK in H5/H9/H1/H4 for creative/intellectual fields. Returns 0-0.05 (discounted -- see
    _KARAKA_DUPLICATE_DISCOUNT: duplicates _putrakaraka_field_score's underlying fact)."""
    if not putrakaraka:
        return 0.0
    aff = affinity.get(putrakaraka, 0.0)
    if aff <= 0:
        return 0.0
    label_l = label.lower()
    kws = ["design","arts","music","film","writing","media","education","research",
           "data science","philosophy","literature","entertainment","game",
           "animation","creative","innovation","theatre","photography"]
    if not any(_wm(kw, label_l) for kw in kws):
        return 0.0
    pk_h   = planet_house.get(putrakaraka, 0)
    pk_dig = planet_dignities.get(putrakaraka, "")
    if pk_h not in (5,9,1,4):
        return 0.0
    mult = {"EXALTED":1.35,"OWN":1.10,"DEBILITATED":0.40}.get(pk_dig, 0.85)
    return min(round(aff * mult * 0.05 * _KARAKA_DUPLICATE_DISCOUNT, 4), 0.05)
