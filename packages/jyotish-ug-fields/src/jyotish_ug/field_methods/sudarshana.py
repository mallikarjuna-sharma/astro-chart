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

from jyotish.boosts import _d1_vitality_coefficient

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
    apply_unmatched_floor: bool = True,
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

    # Sudarshana gap-audit fix (2026-08): the dignity table only recognized
    # EXALTED/OWN/DEBILITATED -- MOOLATRIKONA (roughly OWN-strength) and
    # NEECHA_BHANGA (classically a substantial recovery from debilitation,
    # not merely "no longer penalized") both silently fell through to the
    # neutral 1.0 default, understating both. Extended to match the richer
    # dignity tables every other method in this engine already uses.
    def _dig_mult(planet: str) -> float:
        return {"EXALTED": 1.40, "OWN": 1.15, "MOOLATRIKONA": 1.20,
                "NEECHA_BHANGA": 1.05, "DEBILITATED": 0.60}.get(
            planet_dig.get(planet, ""), 1.0
        )

    # ── Score each layer ──────────────────────────────────────────────────────
    _KT = frozenset({1, 4, 5, 7, 9, 10})

    def _layer_score(lord: str, h10_sign: str, tag: str, base_sign: str) -> float:
        # Sudarshana gap-audit fix: vitality (D1 impairment) was not applied
        # anywhere in this method -- every other method in this engine
        # discounts a field-driving planet's contribution when it's afflicted
        # (combust, weak, etc.) via _d1_vitality_coefficient; Sudarshana had
        # no such check despite the Surya-Lagna layer specifically being
        # anchored on the Sun, where combustion (proximity to the Sun) is
        # mechanically almost guaranteed to be relevant for nearby planets.
        vit = _d1_vitality_coefficient(lord, payload) if lord else 1.0
        aff = affinity.get(lord, 0.0) * _dig_mult(lord) * vit
        _floored = False
        if aff <= 0:
            # 2026-08-20 gap-audit fix: this used to return a hard 0.0 for the
            # ENTIRE layer whenever `lord` (this chart's fixed Lagna/Surya/
            # Chandra H10-lord -- there are only 3, and they never change
            # across fields) happened not to be listed in the field's curated
            # affinity vector (BRANCH_PLANET_AFFINITY). But Sudarshana Chakra
            # is a HOUSE-based technique (which sign/lord governs H10 counted
            # from each ascendant) -- it is not supposed to go silent just
            # because that lord isn't one of a field's hand-picked karaka
            # planets. Confirmed on a real chart: 6/20 of a native's top-20
            # fields hit this cliff to an identical, exact 0.00 -- all
            # Saturn/Mars/Rahu/Ketu-only affinity vectors that never happened
            # to include that chart's fixed Moon/Sun/Jupiter H10-lords, while
            # unrelated fields with a Moon/Sun/Jupiter entry scored normally.
            # A small, deliberately modest floor now applies instead, so the
            # layer still registers the lord's own structural quality
            # (dignity + kendra/trikona from its own ascendant) without
            # affinity backing -- capped low enough (see the floor constant
            # below) that it can never approach a genuinely affinity-matched
            # layer or the convergence bonuses further down, which remain
            # this method's real differentiator. `affinity.get(...)` itself
            # is untouched, so the convergence-bonus logic below (which reads
            # the real dict directly) is unaffected by this floor.
            if not lord:
                return 0.0
            if not apply_unmatched_floor:
                # §9 remediation (2026-08-19): when computing the bounded
                # confirmation-bonus version of this method (see
                # field_methods/__init__.py's sudarshan_confirmation
                # wiring), the floor must be OFF -- §9 explicitly prohibits
                # a cross-verification layer from assigning any score to a
                # planet with zero other karaka support for the field. The
                # floor stays ON by default for this function's own
                # standalone display/audit score (method_entries["sudarshana"]),
                # where it remains a deliberate, documented design choice
                # for a different purpose (not going silent on fields whose
                # curated affinity vector simply omits this chart's fixed
                # H10 lords).
                return 0.0
            _SUDARSHANA_UNMATCHED_FLOOR = 0.05
            aff = _SUDARSHANA_UNMATCHED_FLOOR * _dig_mult(lord) * vit
            _floored = True
        score = aff * 30.0   # base: up to ~30 if lord is the dominant planet
        # Sudarshana gap-audit fix: kendra/trikona strength must be judged
        # FROM THE SAME ASCENDANT this layer is anchored to (Surya Lagna for
        # the Sun layer, Chandra Lagna for the Moon layer) -- not always from
        # the physical D1 lagna. The previous version used `planet_house`
        # (D1-lagna-numbered) for all three layers, which is only correct for
        # the Lagna layer itself; the Sun/Moon layers were silently judging
        # kendra/trikona strength in the wrong reference frame.
        lord_sign = planet_signs.get(lord, "")
        lord_house_from_base = 0
        if lord_sign in _SIGN_IDX and base_sign in _SIGN_IDX:
            lord_house_from_base = ((_SIGN_IDX[lord_sign] - _SIGN_IDX[base_sign]) % 12) + 1
        if lord_house_from_base in _KT:
            score *= 1.20
            trace.append(f"  {tag}: {lord} in kendra/trikona from {tag} ascendant ({base_sign}) → +20%")
        if vit < 1.0:
            trace.append(f"  {tag}: {lord} vitality reduced ({vit:.2f}) by D1 impairment.")
        if _floored:
            trace.append(
                f"  {tag}: {lord} (H10 lord from {tag} ascendant) is not one of this field's "
                "weighted karaka planets -- nominal structural floor only, no affinity backing."
            )
        trace.append(f"  {tag}: H10 sign={h10_sign} lord={lord} aff={aff:.3f} → layer_score={score:.1f}")
        return min(score, 30.0)

    s_lagna = _layer_score(lagna_lord, lagna_h10, "Lagna", lagna_sign)
    s_sun   = _layer_score(sun_lord,   sun_h10,   "Sun",   sun_sign)
    s_moon  = _layer_score(moon_lord,  moon_h10,  "Moon",  moon_sign)

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

    # [CROSS-VERIFICATION NARRATIVE] (§9 audit, real-technique instrumentation):
    # Sudarshana Chakra's own robustness bonus — the overlay of Lagna,
    # Moon-as-Lagna, and Sun-as-Lagna as three simultaneous ascendants
    # (lagna_lord/sun_lord/moon_lord already computed above) — reported per
    # confirming planet, built from local variables only.
    for _sd_lord, _sd_count in lord_counts.items():
        if _sd_count >= 2:
            # print(
            #     f"Sudarshana robustness bonus — {_sd_lord}: {(convergence_bonus / 100.0):.3f} "
            #     f"(angular/trinal from all 3 ascendants)"
            #     if _sd_count == 3 else
            #     f"Sudarshana robustness bonus — {_sd_lord}: {(convergence_bonus / 100.0):.3f} "
            #     f"(confirmed by {_sd_count} of 3 ascendant overlays)"
            # )
            pass
    # print(
    #     f"[CROSS-VERIFICATION NARRATIVE] Sudarshana overlay checked H10 from Lagna "
    #     f"({lagna_sign or '—'} → {lagna_h10 or '—'}, lord {lagna_lord or '—'}), from "
    #     f"Moon-as-Lagna ({moon_sign or '—'} → {moon_h10 or '—'}, lord {moon_lord or '—'}), "
    #     f"and from Sun-as-Lagna ({sun_sign or '—'} → {sun_h10 or '—'}, lord {sun_lord or '—'}); "
    #     + (
    #         f"planet(s) {', '.join(sorted(set(active_lords)))} held up across the overlay "
    #         f"(max agreement {max_agreement} of 3 ascendants)"
    #         if active_lords else "no planet held up with field-affinity backing across the overlay"
    #     )
    #     + ". Sudarshana's cross-check of three independent ascendant reference frames makes it "
    #     "especially valuable as a robustness check under birth-time uncertainty, since a planet "
    #     "confirmed from Moon-as-Lagna and Sun-as-Lagna (both largely insensitive to a few minutes' "
    #     "birth-time error, unlike the Lagna-based cusp itself) still corroborates the judgment even "
    #     "if the physical ascendant degree is only approximately known."
    # )

    return {
        "score":           score,
        "layers_active":   layers_active,
        "lagna_h10":       lagna_h10,
        "sun_h10":         sun_h10,
        "moon_h10":        moon_h10,
        "converging_lords": list(set(active_lords)),
        "trace":           trace,
    }
