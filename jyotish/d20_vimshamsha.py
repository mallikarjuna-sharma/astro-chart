"""jyotish/d20_vimshamsha.py — In-house D20 (Vimshamsha) chart construction.

Gap-G20 fix (2026-07 ontology audit): `_d20_vimshamsha_spiritual_calling` in
boosts.py has existed for a while and is wired into engine.py's gap-boost
loop, but it was permanently inert because the upstream pyhora chart export
never includes a "D20_vimshamsha" key in `divisional_charts` (only D9, D10,
and D24 are supplied) — so `payload.d20_planet_dignities` was always `{}`
and the boost's guard clause (`if not d20_planet_dignities: return 0.0`)
always short-circuited, for every chart, regardless of the person's actual
D20 placements.

This module computes D20 in-house from D1 (sign, degree) longitudes, using
the same audited approach already used for D10 (see `compute_d10_chart` /
`compute_d10_sign` in astro.py) — kept in its own file rather than appended
to the already-1000+-line astro.py.

Classical rule (Parashari, BPHS) — Vimshamsha divides each sign into 20
equal parts of exactly 1°30' (1.5 deg):
  - MOVABLE (Chara) signs — Aries, Cancer, Libra, Capricorn: the 20 parts
    are counted starting FROM ARIES.
  - FIXED (Sthira) signs — Taurus, Leo, Scorpio, Aquarius: counted starting
    FROM SAGITTARIUS.
  - DUAL (Dwiswabhava) signs — Gemini, Virgo, Sagittarius, Pisces: counted
    starting FROM LEO.
"""
from __future__ import annotations

from typing import Dict

_SIGN_ORDER = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
               "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
_SIGN_NUM: Dict[str, int] = {s: i + 1 for i, s in enumerate(_SIGN_ORDER)}

_D20_MOVABLE_SIGNS = {"Aries", "Cancer", "Libra", "Capricorn"}
_D20_FIXED_SIGNS   = {"Taurus", "Leo", "Scorpio", "Aquarius"}
_D20_DUAL_SIGNS    = {"Gemini", "Virgo", "Sagittarius", "Pisces"}


def compute_d20_sign(sign: str, degree: float) -> str:
    """Classical Vimshamsha (D20) sign for a single planet/point."""
    if sign not in _SIGN_NUM:
        return ""
    deg = max(0.0, min(float(degree), 29.999999))
    segment_index = int(deg // 1.5)  # 0..19

    if sign in _D20_MOVABLE_SIGNS:
        start_num = _SIGN_NUM["Aries"]
    elif sign in _D20_FIXED_SIGNS:
        start_num = _SIGN_NUM["Sagittarius"]
    else:
        start_num = _SIGN_NUM["Leo"]

    result_num = ((start_num - 1 + segment_index) % 12) + 1
    return _SIGN_ORDER[result_num - 1]


def compute_d20_chart(planets_d1: Dict, lagna_sign: str = "", lagna_degree: float = 0.0) -> Dict[str, Dict[str, str]]:
    """Build the full D20 (Vimshamsha) chart in-house from D1 longitudes.

    Returns {"Lagna": {"sign": ...}, "Sun": {"sign": ...}, ...} — dict-of-dict
    shape matching astro.py's compute_d10_chart(). Planets missing `degree`
    are skipped (caller falls back gracefully — see engine_io.py).
    """
    chart: Dict[str, Dict[str, str]] = {}
    if lagna_sign:
        chart["Lagna"] = {"sign": compute_d20_sign(lagna_sign, lagna_degree)}
    for planet, pdata in (planets_d1 or {}).items():
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        chart[planet] = {"sign": compute_d20_sign(sign, float(degree))}
    return chart
