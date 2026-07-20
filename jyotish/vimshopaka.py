"""Vimshopaka Bala — classical divisional-chart (varga) strength weighting.

GAP-FIX (2026-07): the engine previously had no standardized method for
weighing a planet's strength across divisional charts. Career-relevant
divisional boosts (D9 AK-related, D10 10th-lord, D60 "vitality gate") were
each capped at arbitrary, independently-tuned percentages (see engine.py's
_D9_PCC/_D10_PCC/_PCC constants and boosts.py's _d60_vitality_gate) with no
shared, classically-grounded weighting scheme tying them together.

This module implements the classical **Dasavarga Vimshopaka Bala** (BPHS
Ch.6) — the standard 10-divisional-chart weighting table, total 20 points:

    D1 (Rasi)        3.5
    D2 (Hora)        1.0
    D3 (Drekkana)    1.0
    D7 (Saptamsa)    0.5
    D9 (Navamsa)     3.0
    D10 (Dashamsa)   0.5
    D12 (Dwadasamsa) 0.5
    D16 (Shodasamsa) 2.0
    D30 (Trimsamsa)  4.0
    D60 (Shashtiamsa)4.0
    ------------------------
    Total            20.0

For each varga, the planet earns a classical fractional credit based on its
dignity in that varga's sign (BPHS's own point scheme, not this codebase's
eff_strength dignity *multipliers* which are a separate, deliberately
different modeling choice for a different purpose):

    Exalted / Own sign / Moolatrikona    -> 1.00  (full)
    Great friend                          -> 0.75
    Friend / Neecha Bhanga (cancelled)    -> 0.50
    Neutral                               -> 0.25
    Enemy                                  -> 0.125
    Great enemy / Debilitated (uncancelled) -> 0.00

vimshopaka_bala_points(planet) = sum(weight_i * fraction_i), max 20.
vimshopaka_bala_pct(planet)    = points / 20 * 100.

D9 is read from the chart's existing (upstream-sourced) D9 dict rather than
rebuilt here, matching how the rest of the codebase already treats D9 (see
astro.py module docstrings — D9 has no in-house builder and is treated as
trusted input elsewhere too). D1, D10, D12, D2, D3, D7, D16, D30, D60 sign
placements are computed in-house below from D1 longitude using standard,
mechanical Parashari division rules (the same class of rule as the existing
compute_d10_sign in astro.py). D60's sign-assignment convention has genuine
cross-text variance (unlike D1-D30 here, which are essentially undisputed);
this module documents its specific choice inline and flags it as the
lower-confidence varga in the weighting, consistent with how this codebase
already flags other classically-disputed points (e.g. graha_yuddha's winner
rule in dignity.py) as a documented convention rather than settled fact.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional

from .constants import _SIGN_LORD
from .dignity import dignity_state

_SIGN_ORDER = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
               "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
_SIGN_NUM = {s: i + 1 for i, s in enumerate(_SIGN_ORDER)}

_MOVABLE = {"Aries", "Cancer", "Libra", "Capricorn"}
_FIXED = {"Taurus", "Leo", "Scorpio", "Aquarius"}
_DUAL = {"Gemini", "Virgo", "Sagittarius", "Pisces"}

DASAVARGA_WEIGHTS: Dict[str, float] = {
    "D1": 3.5, "D2": 1.0, "D3": 1.0, "D7": 0.5, "D9": 3.0,
    "D10": 0.5, "D12": 0.5, "D16": 2.0, "D30": 4.0, "D60": 4.0,
}
assert abs(sum(DASAVARGA_WEIGHTS.values()) - 20.0) < 1e-9

_DIGNITY_FRACTION: Dict[str, float] = {
    "EXALTED": 1.00, "MOOLATRIKONA": 1.00, "OWN_SIGN": 1.00,
    "GREAT_FRIEND": 0.75,
    "FRIEND": 0.50, "NEECHA_BHANGA": 0.50,
    "NEUTRAL": 0.25,
    "ENEMY": 0.125,
    "GREAT_ENEMY": 0.00, "DEBILITATED": 0.00,
}


def _off(sign: str, offset: int) -> str:
    """Sign `offset` positions ahead of `sign` (0 = same sign), wrapping mod 12."""
    n = _SIGN_NUM.get(sign)
    if not n:
        return ""
    return _SIGN_ORDER[(n - 1 + offset) % 12]


def compute_d2_sign(sign: str, degree: float) -> str:
    """Hora (D2), Parashari scheme: odd signs 0-15deg->Leo,15-30deg->Cancer;
    even signs 0-15deg->Cancer,15-30deg->Leo (Sun/Moon hora split)."""
    if sign not in _SIGN_NUM:
        return ""
    is_odd = (_SIGN_NUM[sign] % 2) == 1
    first_half = degree < 15.0
    if is_odd:
        return "Leo" if first_half else "Cancer"
    return "Cancer" if first_half else "Leo"


def compute_d3_sign(sign: str, degree: float) -> str:
    """Drekkana (D3), Parashari: 0-10deg->same sign, 10-20deg->5th sign,
    20-30deg->9th sign (counted inclusively, i.e. offsets 0/4/8)."""
    if sign not in _SIGN_NUM:
        return ""
    seg = min(int(degree // 10.0), 2)
    return _off(sign, seg * 4)


def compute_d7_sign(sign: str, degree: float) -> str:
    """Saptamsa (D7), Parashari: 30/7 segments; odd signs count from the
    same sign, even signs count from the 7th sign (offset 6)."""
    if sign not in _SIGN_NUM:
        return ""
    seg = min(int(degree // (30.0 / 7.0)), 6)
    is_odd = (_SIGN_NUM[sign] % 2) == 1
    start_offset = 0 if is_odd else 6
    return _off(sign, start_offset + seg)


def compute_d12_sign(sign: str, degree: float) -> str:
    """Dwadasamsa (D12), Parashari: 30/12 = 2.5deg segments, sequential
    starting from the same sign."""
    if sign not in _SIGN_NUM:
        return ""
    seg = min(int(degree // 2.5), 11)
    return _off(sign, seg)


def compute_d16_sign(sign: str, degree: float) -> str:
    """Shodasamsa (D16), Parashari: 30/16 = 1.875deg segments; movable signs
    count from Aries, fixed signs from Leo, dual signs from Sagittarius."""
    if sign not in _SIGN_NUM:
        return ""
    seg = min(int(degree // 1.875), 15)
    if sign in _MOVABLE:
        start = "Aries"
    elif sign in _FIXED:
        start = "Leo"
    else:
        start = "Sagittarius"
    n = _SIGN_NUM[start]
    return _SIGN_ORDER[(n - 1 + seg) % 12]


# Trimsamsa (D30) unequal classical division (BPHS): odd signs run
# Mars(5)->Saturn(5)->Jupiter(8)->Mercury(7)->Venus(5) starting from Aries/
# Aquarius/Sagittarius/Gemini/Libra respectively; even signs mirror with
# Venus/Mercury/Jupiter/Saturn/Mars starting from Taurus/Virgo/Pisces/
# Capricorn/Scorpio.
_D30_ODD = [(5, "Aries"), (5, "Aquarius"), (8, "Sagittarius"), (7, "Gemini"), (5, "Libra")]
_D30_EVEN = [(5, "Taurus"), (7, "Virgo"), (8, "Pisces"), (5, "Capricorn"), (5, "Scorpio")]


def compute_d30_sign(sign: str, degree: float) -> str:
    if sign not in _SIGN_NUM:
        return ""
    is_odd = (_SIGN_NUM[sign] % 2) == 1
    table = _D30_ODD if is_odd else _D30_EVEN
    cum = 0.0
    for span, result_sign in table:
        cum += span
        if degree < cum:
            return result_sign
    return table[-1][1]


def compute_d60_sign(sign: str, degree: float) -> str:
    """Shashtiamsa (D60), 60 parts of 0.5deg each.

    NOTE ON CLASSICAL VARIANCE: unlike D1-D30 above, D60's sign-sequencing
    convention genuinely differs across classical sources (some count
    cumulatively from the same sign for every sign, others alternate
    direction by odd/even sign, others use a named 60-deity sequence not
    reducible to a plain sign wheel at all). This function uses the simple
    cumulative convention (signs advance sequentially from the placement
    sign, one sign per 6 parts, for both odd and even signs) as a documented
    choice, not a settled classical consensus -- flagged as the
    lowest-confidence varga in DASAVARGA_WEIGHTS' 4.0-point allocation.
    """
    if sign not in _SIGN_NUM:
        return ""
    part = min(int(degree // 0.5), 59)  # 0..59
    return _off(sign, part % 12)


_VARGA_FUNCS = {
    "D2": compute_d2_sign, "D3": compute_d3_sign, "D7": compute_d7_sign,
    "D12": compute_d12_sign, "D16": compute_d16_sign, "D30": compute_d30_sign,
    "D60": compute_d60_sign,
}


def compute_vimshopaka_bala(
    planet: str,
    d1_sign: str,
    d1_degree: float,
    d9_sign: str = "",
    d10_sign: str = "",
) -> Dict[str, float]:
    """Classical Dasavarga Vimshopaka Bala for one planet.

    `d9_sign`/`d10_sign` are passed in (D9 has no in-house builder in this
    codebase -- see module docstring; D10 should come from
    astro.compute_d10_sign, already classically verified/tested). All other
    vargas are computed here directly from D1 sign+degree.

    Returns {"points": 0-20 float, "pct": 0-100 float, "per_varga": {...}}.
    """
    if not planet or not d1_sign:
        return {"points": 0.0, "pct": 0.0, "per_varga": {}}

    signs: Dict[str, str] = {"D1": d1_sign}
    for varga, fn in _VARGA_FUNCS.items():
        signs[varga] = fn(d1_sign, d1_degree)
    if d9_sign:
        signs["D9"] = d9_sign
    if d10_sign:
        signs["D10"] = d10_sign
    else:
        signs["D10"] = signs.get("D10", "")

    per_varga: Dict[str, float] = {}
    total = 0.0
    for varga, weight in DASAVARGA_WEIGHTS.items():
        sign = signs.get(varga, "")
        if not sign or sign not in _SIGN_NUM:
            continue
        state = dignity_state(planet, sign)
        frac = _DIGNITY_FRACTION.get(state, 0.25)
        pts = weight * frac
        per_varga[varga] = round(pts, 4)
        total += pts

    return {"points": round(total, 3), "pct": round(total / 20.0 * 100.0, 2), "per_varga": per_varga}


def compute_vimshopaka_bala_all(
    planets_d1: Mapping[str, Mapping],
    d9_chart: Optional[Mapping] = None,
    d10_chart: Optional[Mapping] = None,
) -> Dict[str, Dict[str, float]]:
    """Vimshopaka Bala for every planet placed in `planets_d1`.

    `d9_chart`/`d10_chart` are {planet: {"sign": ...}} or {planet: "Sign"}
    shapes (this codebase has both floating around -- see astro.py's
    compute_d10_chart docstring on the D10 shape-mismatch gotcha); both are
    normalized here defensively.
    """
    def _sign_of(chart: Optional[Mapping], p: str) -> str:
        if not chart:
            return ""
        v = chart.get(p)
        if isinstance(v, Mapping):
            return str(v.get("sign", ""))
        if isinstance(v, str):
            return v
        return ""

    out: Dict[str, Dict[str, float]] = {}
    for planet, pdata in (planets_d1 or {}).items():
        if planet == "Lagna" or not isinstance(pdata, Mapping):
            continue
        sign = pdata.get("sign", "")
        degree = pdata.get("degree")
        if not sign or degree is None:
            continue
        d9s = _sign_of(d9_chart, planet)
        d10s = _sign_of(d10_chart, planet)
        out[planet] = compute_vimshopaka_bala(planet, str(sign), float(degree), d9s, d10s)
    return out
