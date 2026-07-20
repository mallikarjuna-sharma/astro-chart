"""
employment_mode.py
==================
Job vs Business discriminator for JyotishAI.

Answers the #1 career consultation question: "Should I do a job or start a business?"

Computes four mode scores:
  - employment_score    (salaried job — Saturn/H6/H10 signals)
  - business_score      (own business — H7/H11/DK signals)
  - independent_score   (self-employed professional — H1/Sun signals)
  - family_biz_score    (family business — H4/H2/Moon signals)

Public API:
    compute_employment_mode(payload) -> dict
"""
from __future__ import annotations
from typing import Any, Dict, List

_SIGN_LORD = {
    "Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
    "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
    "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter",
}
_KENDRA   = frozenset({1, 4, 7, 10})
_TRIKONA  = frozenset({1, 5, 9})
_KT       = _KENDRA | _TRIKONA


def _dig_factor(planet: str, dignities: Dict[str, str]) -> float:
    return {"EXALTED": 1.40, "OWN": 1.15, "DEBILITATED": 0.55}.get(dignities.get(planet, ""), 1.0)


def compute_employment_mode(payload: Any) -> Dict:
    """
    Returns a dict:
    {
      "employment_score": int 0-100,
      "business_score": int 0-100,
      "independent_score": int 0-100,
      "family_biz_score": int 0-100,
      "recommended_mode": str,
      "confidence": str,         # HIGH / MODERATE / LOW
      "key_signals": List[str],
      "geographic_preference": str,  # domestic / international / both
    }
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords  = getattr(payload, "house_lords", {}) or {}
    planet_dig   = getattr(payload, "planet_dignities", {}) or {}
    planets_d1   = getattr(payload, "planets_d1", {}) or {}
    # Gap 0.4 fix: attribute was `sarvashtakavarga` (never exists on the payload);
    # the real field is `sav_points_houses` with canonical "1".."12" keys.
    sav          = getattr(payload, "sav_points_houses", {}) or {}
    darakaraka   = getattr(payload, "darakaraka", "") or ""

    signals: List[str] = []
    emp_raw  = 0.0
    biz_raw  = 0.0
    ind_raw  = 0.0
    fam_raw  = 0.0

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    def _sav_h(h: int) -> int:
        return sav.get(str(h), sav.get(h, 28))

    h2_lord  = _h(2);  h4_lord  = _h(4);  h6_lord  = _h(6)
    h7_lord  = _h(7);  h10_lord = _h(10); h11_lord = _h(11)
    h1_lord  = _h(1)   # lagna lord

    # ── EMPLOYMENT SIGNALS ────────────────────────────────────────────────────
    sat_h = _ph("Saturn")
    if sat_h == 10:
        emp_raw += 20; signals.append("Saturn in H10 → structured employment organisation")
    elif sat_h in (4, 7):
        emp_raw += 12; signals.append("Saturn aspects H10 → disciplined career environment")

    sun_h = _ph("Sun")
    if sun_h == 10:
        emp_raw += 15; signals.append("Sun in H10 → government/corporate authority role")

    if h6_lord and _ph(h6_lord) in _KT:
        emp_raw += 12 * _dig_factor(h6_lord, planet_dig)
        signals.append(f"H6 lord ({h6_lord}) in kendra/trikona → service/employment sector")

    if _sav_h(10) >= 35:
        emp_raw += 8; signals.append("H10 SAV ≥35 → strong institutional career mandate")

    # ── BUSINESS SIGNALS ─────────────────────────────────────────────────────
    if h7_lord and _ph(h7_lord) in _KT:
        biz_raw += 18 * _dig_factor(h7_lord, planet_dig)
        signals.append(f"H7 lord ({h7_lord}) in kendra/trikona → business partnerships activated")

    rahu_h = _ph("Rahu")
    if rahu_h == 7:
        biz_raw += 14; signals.append("Rahu in H7 → unconventional/foreign business partnerships")

    if h11_lord and _ph(h11_lord) in {10, 7}:
        biz_raw += 12; signals.append(f"H11 lord ({h11_lord}) in H10/H7 → business gains activated")

    if darakaraka and _ph(darakaraka) in _KT:
        biz_raw += 10 * _dig_factor(darakaraka, planet_dig)
        signals.append(f"DK ({darakaraka}) in kendra/trikona → strong partnership karma")

    mer_h = _ph("Mercury"); ven_h = _ph("Venus")
    if mer_h in _KT and ven_h in _KT:
        biz_raw += 10; signals.append("Mercury + Venus in kendra/trikona → commerce/trading aptitude")

    if h2_lord and h7_lord and (h2_lord == h7_lord or _ph(h2_lord) == 7):
        biz_raw += 8; signals.append("H2-H7 connection → business wealth accumulation")

    # ── INDEPENDENT PRACTICE SIGNALS ─────────────────────────────────────────
    if h1_lord and _ph(h1_lord) in {1, 10}:
        ind_raw += 18 * _dig_factor(h1_lord, planet_dig)
        signals.append(f"Lagna lord ({h1_lord}) in H1/H10 → independent professional mandate")

    sun_dig = planet_dig.get("Sun", "")
    if sun_dig in ("EXALTED", "OWN") and sun_h in _KT:
        ind_raw += 14; signals.append("Sun strong in kendra → independent leadership practice")

    # Gap-46 (audit 2026-07) fix: an empty H7 is true for ~40% of charts —
    # weight reduced 8 → 4 so an absence-signal cannot rival placement signals.
    planets_in_h7 = [p for p, h in planet_house.items() if h == 7]
    if not planets_in_h7:
        ind_raw += 4; signals.append("No planet in H7 → independent work, no partnership compulsion")

    if mer_h in {1, 10}:
        ind_raw += 10; signals.append("Mercury in H1/H10 → intellectual independent practice")

    # ── FAMILY BUSINESS SIGNALS ───────────────────────────────────────────────
    if h4_lord and h2_lord and (h4_lord == h2_lord or _ph(h4_lord) == 2):
        fam_raw += 16; signals.append("H4-H2 connection → family wealth/property involvement")

    moon_h   = _ph("Moon")
    moon_dig = planet_dig.get("Moon", "")
    if moon_h in {4, 10} and moon_dig in ("EXALTED", "OWN"):
        fam_raw += 14; signals.append("Moon strong in H4/H10 → family business emotional foundation")

    if h4_lord and _ph(h4_lord) == 10:
        fam_raw += 12; signals.append("H4 lord in H10 → career rooted in family/homeland")

    if ven_h in {2, 4}:
        fam_raw += 8; signals.append("Venus in H2/H4 → family commerce/arts business")

    # ── NORMALISATION ────────────────────────────────────────────────────────
    # Gap-41 (audit 2026-07) fix: all four modes previously divided by the same
    # constant (50) although their achievable maxima differ (~60 employment,
    # ~83 business, ~53 independent, ~50 family) — a structural bias toward
    # "business" recommendations. Each mode now normalizes by its own maximum.
    _MODE_MAX = {
        "employment":  60.0,   # 20 + 15 + 12×1.4 + 8
        "business":    83.0,   # 18×1.4 + 14 + 12 + 10×1.4 + 10 + 8
        "independent": 53.0,   # 18×1.4 + 14 + 4 + 10
        "family":      50.0,   # 16 + 14 + 12 + 8
    }

    def _scale(raw: float, mode: str) -> int:
        return min(int((raw / _MODE_MAX[mode]) * 100), 100)

    emp_s = _scale(emp_raw, "employment");   biz_s = _scale(biz_raw, "business")
    ind_s = _scale(ind_raw, "independent");  fam_s = _scale(fam_raw, "family")

    scores = {"employment": emp_s, "business": biz_s,
              "independent": ind_s, "family_business": fam_s}
    recommended = max(scores, key=scores.get)

    sorted_scores = sorted(scores.values(), reverse=True)
    gap = sorted_scores[0] - sorted_scores[1]
    confidence = "HIGH" if gap >= 20 else "MODERATE" if gap >= 10 else "LOW"

    # Geographic preference
    geo_pref = "domestic"
    if rahu_h in {9, 12} or (_ph("Moon") == rahu_h) or (h7_lord and _ph(h7_lord) == 12):
        geo_pref = "international"
    elif rahu_h == 7:
        geo_pref = "both"

    return {
        "employment_score":      emp_s,
        "business_score":        biz_s,
        "independent_score":     ind_s,
        "family_biz_score":      fam_s,
        "recommended_mode":      recommended,
        "confidence":            confidence,
        "key_signals":           signals[:8],
        "geographic_preference": geo_pref,
    }
