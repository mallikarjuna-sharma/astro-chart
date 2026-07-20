"""
sudarshana.py
=============
Standalone Sudarshana Chakra scorer (K.N. Rao method).

Sudarshana Chakra = simultaneous analysis of the same house number
counted from THREE ascendants:
  • Lagna (actual ascendant)
  • Sun (solar ascendant — Surya Lagna)
  • Moon (lunar ascendant — Chandra Lagna)

For career: examine H10 from each base.  When all three point to the
same planetary lord or the same field type, the signal is "sudarshana
convergence" — considered the most reliable indicator in K.N. Rao's system.

Public API:
    score_sudarshana(label, affinity, payload) -> dict
"""
from __future__ import annotations
from typing import Any, Dict, List

# ── Zodiac helpers ────────────────────────────────────────────────────────────
_SIGNS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]
_SIGN_IDX = {s: i for i, s in enumerate(_SIGNS)}

_SIGN_LORD = {
    "Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
    "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
    "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter",
}

def _h10_from(base_sign: str) -> str:
    """Return the sign that is H10 when counted from base_sign."""
    if base_sign not in _SIGN_IDX:
        return ""
    idx = (_SIGN_IDX[base_sign] + 9) % 12   # +9 = 10th house (0-based)
    return _SIGNS[idx]


def _affinity_for_sign(sign: str, affinity: Dict[str, float]) -> float:
    """Sum affinity weights for the lord of the given sign."""
    lord = _SIGN_LORD.get(sign, "")
    return affinity.get(lord, 0.0)


def score_sudarshana(
    label: str,
    affinity: Dict[str, float],
    payload: Any,
) -> Dict:
    """
    Score a career field label using Sudarshana Chakra.

    Parameters
    ----------
    label    : career field label (e.g. "Software Engineering")
    affinity : {planet: weight} dict from the field definition
    payload  : NatalPayloadV2 instance

    Returns
    -------
    dict with keys:
        score           float 0-100
        layers_active   int  (0, 1, 2, or 3)
        lagna_h10       str  (sign that is H10 from lagna)
        sun_h10         str  (sign that is H10 from Sun)
        moon_h10        str  (sign that is H10 from Moon)
        converging_lords List[str]
        trace           List[str]
    """
    planet_house  = getattr(payload, "planet_house",   {}) or {}
    planet_signs  = getattr(payload, "planet_signs",   {}) or {}
    lagna_sign    = getattr(payload, "lagna_sign",     "") or ""
    planet_dig    = getattr(payload, "planet_dignities",{}) or {}
    house_lords   = getattr(payload, "house_lords",    {}) or {}

    trace: List[str] = []

    # ── Determine base signs for the three ascendants ─────────────────────────
    sun_sign  = planet_signs.get("Sun",  "")
    moon_sign = planet_signs.get("Moon", "")

    # Fallback: derive from planet_house + lagna_sign chain
    if not sun_sign:
        sun_h = planet_house.get("Sun", 0)
        if sun_h and lagna_sign in _SIGN_IDX:
            sun_sign = _SIGNS[(_SIGN_IDX[lagna_sign] + sun_h - 1) % 12]
    if not moon_sign:
        moon_h = planet_house.get("Moon", 0)
        if moon_h and lagna_sign in _SIGN_IDX:
            moon_sign = _SIGNS[(_SIGN_IDX[lagna_sign] + moon_h - 1) % 12]

    # ── H10 from each ascendant ───────────────────────────────────────────────
    lagna_h10 = _h10_from(lagna_sign)
    sun_h10   = _h10_from(sun_sign)
    moon_h10  = _h10_from(moon_sign)

    lagna_lord = _SIGN_LORD.get(lagna_h10, "")
    sun_lord   = _SIGN_LORD.get(sun_h10,   "")
    moon_lord  = _SIGN_LORD.get(moon_h10,  "")

    def _dig_mult(planet: str) -> float:
        return {"EXALTED": 1.40, "OWN": 1.15, "DEBILITATED": 0.60}.get(
            planet_dig.get(planet, ""), 1.0
        )

    # ── Score each layer ──────────────────────────────────────────────────────
    _KT = frozenset({1, 4, 5, 7, 9, 10})

    def _layer_score(lord: str, h10_sign: str, tag: str) -> float:
        aff = affinity.get(lord, 0.0) * _dig_mult(lord)
        if aff <= 0:
            return 0.0
        score = aff * 30.0   # base: up to ~30 if lord is the dominant planet
        # Boost if the lord is placed in a kendra/trikona in D1
        if planet_house.get(lord, 0) in _KT:
            score *= 1.20
            trace.append(f"  {tag}: {lord} in kendra/trikona → +20%")
        trace.append(f"  {tag}: H10 sign={h10_sign} lord={lord} aff={aff:.3f} → layer_score={score:.1f}")
        return min(score, 30.0)

    s_lagna = _layer_score(lagna_lord, lagna_h10, "Lagna")
    s_sun   = _layer_score(sun_lord,   sun_h10,   "Sun")
    s_moon  = _layer_score(moon_lord,  moon_h10,  "Moon")

    # ── Convergence bonus ────────────────────────────────────────────────────
    # Bug fix (audit): Sudarshana Chakra's entire premise is AGREEMENT -- the
    # same H10 lord confirmed from Lagna, Surya, and Chandra simultaneously.
    # The previous implementation computed `layers_active = len(set(active_lords))`,
    # i.e. the count of *distinct* lords among the three -- which is inverted:
    # three genuinely agreeing ascendants (all pointing to one lord) collapse to
    # set-size 1 (minimum bonus), while three unrelated lords that each merely
    # happen to have nonzero field affinity collapse to set-size 3 (maximum
    # bonus). That rewards divergence and penalizes the exact condition this
    # technique is named for. Fixed to measure how many of the three
    # ascendant-derived H10 lords AGREE on the same lord (multiset mode count),
    # with a separate, smaller allowance for independent-but-non-agreeing
    # witnesses so real convergence always outranks scattered support.
    from collections import Counter

    active_lords = [l for l in [lagna_lord, sun_lord, moon_lord] if l and affinity.get(l, 0) > 0]
    lord_counts = Counter(active_lords)
    max_agreement = max(lord_counts.values()) if lord_counts else 0
    num_active = len(active_lords)
    layers_active = max_agreement  # kept name/range (0-3) for API compatibility

    convergence_bonus = 0.0
    if max_agreement == 3:
        convergence_bonus = 30.0
        trace.append(
            "Sudarshana triple convergence (+30): Lagna, Surya, and Chandra "
            "H10 all point to the same lord -- true classical convergence."
        )
    elif max_agreement == 2:
        convergence_bonus = 15.0
        trace.append(
            "Sudarshana dual convergence (+15): 2 of the 3 ascendants agree on the same H10 lord."
        )
    elif num_active >= 1:
        # No agreement between ascendants -- 1 to 3 independent, non-agreeing
        # witnesses. This is NOT classical "convergence" and must stay well
        # below the agreement tiers above; it still credits genuine
        # independent support so a chart isn't scored as if Sudarshana were
        # silent, but it can never outrank real lord-agreement.
        convergence_bonus = 3.0 * num_active
        trace.append(
            f"Sudarshana: {num_active} independent (non-agreeing) supportive "
            f"witness(es) (+{convergence_bonus:.0f}) -- distinct lords, not true convergence."
        )

    # Special: all three H10 signs are the SAME (exact Sudarshana triple lock)
    triple_lock = (lagna_h10 and lagna_h10 == sun_h10 == moon_h10)
    if triple_lock:
        convergence_bonus += 10.0
        trace.append("Sudarshana triple-lock: all H10 signs identical (+10)")

    raw = s_lagna + s_sun + s_moon + convergence_bonus
    score = min(round(raw, 2), 100.0)

    return {
        "score":           score,
        "layers_active":   layers_active,
        "lagna_h10":       lagna_h10,
        "sun_h10":         sun_h10,
        "moon_h10":        moon_h10,
        "converging_lords": list(set(active_lords)),
        "trace":           trace,
    }
