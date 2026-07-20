"""Bhinnashtakavarga (BAV) -- classical Parashari per-planet Ashtakavarga.

Implements the standard 7-target x 8-contributor x 12-house-position bindu
lookup tables from Parashara's Brihat Parashara Hora Shastra. The bindu
positions below were cross-verified against the open-source PyJHora library
(naturalstupid/PyJHora, `src/jhora/const.py::ashtaka_varga_dict`), itself
based on P.V.R. Narasimha Rao's "Vedic Astrology: An Integrated Approach"
and unit-tested against worked examples from that book.

Convention (kept consistent with the rest of the repo -- see engine_io.py,
constants.py):
    - Sign numbering: Aries=1 .. Pisces=12 (see jyotish.constants._SIGN_NUM).
    - "House position from contributor" is counted INCLUSIVE of the
      contributor's own occupied sign as position 1 (i.e. the same sign the
      contributor sits in is position 1, the next sign is position 2, etc.),
      which is the standard classical convention for Ashtakavarga bindu
      tables (a bindu placed at "1" means the contributor's own sign gets a
      point; "7" means the 7th-from-contributor sign gets a point, etc.).
    - Final output houses (1-12) are always counted from the ASCENDANT
      (Lagna), matching planet_house's convention elsewhere in this repo.

Each of the 7 target grahas below has a fixed 8x12 bindu table: 8 rows (the
7 planets Sun..Saturn + Lagna as contributors) x 12 columns (house position
1..12 counted from that contributor's own natal sign). A "1" bindu means
that contributor grants a point to a native's chart at that house-position;
"0" means no point granted, for that target planet's Bhinnashtakavarga.

The classical per-target-planet grand totals (sum of all 96 cells in each
8x12 table) are fixed constants that every correct implementation must
reproduce: Sun=48, Moon=49, Mars=39, Mercury=54, Jupiter=56, Venus=52,
Saturn=39 (SAV grand total=337). These are used as a self-check in this
module's own test harness and were used to validate the tables below
during development.
"""

from __future__ import annotations

from typing import Dict, List

from .constants import _SIGN_NUM

CONTRIBUTORS: List[str] = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Lagna"]
TARGET_PLANETS: List[str] = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

BAV_GRAND_TOTALS: Dict[str, int] = {
    "Sun": 48, "Moon": 49, "Mars": 39, "Mercury": 54,
    "Jupiter": 56, "Venus": 52, "Saturn": 39,
}


def _row_from_positions(benefic_positions: List[int]) -> List[int]:
    row = [0] * 12
    for pos in benefic_positions:
        row[pos - 1] = 1
    return row


_SUN_POSITIONS: Dict[str, List[int]] = {
    "Sun":     [1, 2, 4, 7, 8, 9, 10, 11],
    "Moon":    [3, 6, 10, 11],
    "Mars":    [1, 2, 4, 7, 8, 9, 10, 11],
    "Mercury": [3, 5, 6, 9, 10, 11, 12],
    "Jupiter": [5, 6, 9, 11],
    "Venus":   [6, 7, 12],
    "Saturn":  [1, 2, 4, 7, 8, 9, 10, 11],
    "Lagna":   [3, 4, 6, 10, 11, 12],
}

_MOON_POSITIONS: Dict[str, List[int]] = {
    "Sun":     [3, 6, 7, 8, 10, 11],
    "Moon":    [1, 3, 6, 7, 9, 10, 11],
    "Mars":    [2, 3, 5, 6, 10, 11],
    "Mercury": [1, 3, 4, 5, 7, 8, 10, 11],
    "Jupiter": [1, 2, 4, 7, 8, 10, 11],
    "Venus":   [3, 4, 5, 7, 9, 10, 11],
    "Saturn":  [3, 5, 6, 11],
    "Lagna":   [3, 6, 10, 11],
}

_MARS_POSITIONS: Dict[str, List[int]] = {
    "Sun":     [3, 5, 6, 10, 11],
    "Moon":    [3, 6, 11],
    "Mars":    [1, 2, 4, 7, 8, 10, 11],
    "Mercury": [3, 5, 6, 11],
    "Jupiter": [6, 10, 11, 12],
    "Venus":   [6, 8, 11, 12],
    "Saturn":  [1, 4, 7, 8, 9, 10, 11],
    "Lagna":   [1, 3, 6, 10, 11],
}

_MERCURY_POSITIONS: Dict[str, List[int]] = {
    "Sun":     [5, 6, 9, 11, 12],
    "Moon":    [2, 4, 6, 8, 10, 11],
    "Mars":    [1, 2, 4, 7, 8, 9, 10, 11],
    "Mercury": [1, 3, 5, 6, 9, 10, 11, 12],
    "Jupiter": [6, 8, 11, 12],
    "Venus":   [1, 2, 3, 4, 5, 8, 9, 11],
    "Saturn":  [1, 2, 4, 7, 8, 9, 10, 11],
    "Lagna":   [1, 2, 4, 6, 8, 10, 11],
}

_JUPITER_POSITIONS: Dict[str, List[int]] = {
    "Sun":     [1, 2, 3, 4, 7, 8, 9, 10, 11],
    "Moon":    [2, 5, 7, 9, 11],
    "Mars":    [1, 2, 4, 7, 8, 10, 11],
    "Mercury": [1, 2, 4, 5, 6, 9, 10, 11],
    "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
    "Venus":   [2, 5, 6, 9, 10, 11],
    "Saturn":  [3, 5, 6, 12],
    "Lagna":   [1, 2, 4, 5, 6, 7, 9, 10, 11],
}

_VENUS_POSITIONS: Dict[str, List[int]] = {
    "Sun":     [8, 11, 12],
    "Moon":    [1, 2, 3, 4, 5, 8, 9, 11, 12],
    "Mars":    [3, 4, 6, 9, 11, 12],
    "Mercury": [3, 5, 6, 9, 11],
    "Jupiter": [5, 8, 9, 10, 11],
    "Venus":   [1, 2, 3, 4, 5, 8, 9, 10, 11],
    "Saturn":  [3, 4, 5, 8, 9, 10, 11],
    "Lagna":   [1, 2, 3, 4, 5, 8, 9, 11],
}

_SATURN_POSITIONS: Dict[str, List[int]] = {
    "Sun":     [1, 2, 4, 7, 8, 10, 11],
    "Moon":    [3, 6, 11],
    "Mars":    [3, 5, 6, 10, 11, 12],
    "Mercury": [6, 8, 9, 10, 11, 12],
    "Jupiter": [5, 6, 11, 12],
    "Venus":   [6, 11, 12],
    "Saturn":  [3, 5, 6, 11],
    "Lagna":   [1, 3, 4, 6, 10, 11],
}

_SUN_BAV: Dict[str, List[int]] = {k: _row_from_positions(v) for k, v in _SUN_POSITIONS.items()}
_MOON_BAV: Dict[str, List[int]] = {k: _row_from_positions(v) for k, v in _MOON_POSITIONS.items()}
_MARS_BAV: Dict[str, List[int]] = {k: _row_from_positions(v) for k, v in _MARS_POSITIONS.items()}
_MERCURY_BAV: Dict[str, List[int]] = {k: _row_from_positions(v) for k, v in _MERCURY_POSITIONS.items()}
_JUPITER_BAV: Dict[str, List[int]] = {k: _row_from_positions(v) for k, v in _JUPITER_POSITIONS.items()}
_VENUS_BAV: Dict[str, List[int]] = {k: _row_from_positions(v) for k, v in _VENUS_POSITIONS.items()}
_SATURN_BAV: Dict[str, List[int]] = {k: _row_from_positions(v) for k, v in _SATURN_POSITIONS.items()}

_BAV_TABLES: Dict[str, Dict[str, List[int]]] = {
    "Sun": _SUN_BAV,
    "Moon": _MOON_BAV,
    "Mars": _MARS_BAV,
    "Mercury": _MERCURY_BAV,
    "Jupiter": _JUPITER_BAV,
    "Venus": _VENUS_BAV,
    "Saturn": _SATURN_BAV,
}


def _sign_num_for(planet: str, planet_signs: Dict[str, str], lagna_sign: str) -> int:
    if planet == "Lagna":
        return _SIGN_NUM.get(lagna_sign, 0)
    return _SIGN_NUM.get(planet_signs.get(planet, ""), 0)


def compute_bav_points(
    planet_signs: Dict[str, str],
    lagna_sign: str,
) -> Dict[str, Dict[int, int]]:
    """Compute Bhinnashtakavarga bindu counts for the 7 classical grahas.

    Returns {target_planet: {house_num (1-12, from Lagna): bindu_count}}.
    """
    lagna_num = _SIGN_NUM.get(lagna_sign, 0)

    result: Dict[str, Dict[int, int]] = {}
    for target, table in _BAV_TABLES.items():
        house_bindus: Dict[int, int] = {h: 0 for h in range(1, 13)}
        for contributor in CONTRIBUTORS:
            contributor_sign_num = _sign_num_for(contributor, planet_signs, lagna_sign)
            if not contributor_sign_num:
                continue
            row = table.get(contributor)
            if not row:
                continue
            for pos_from_contributor in range(1, 13):
                bindu = row[pos_from_contributor - 1]
                if not bindu:
                    continue
                target_sign_num = ((contributor_sign_num - 1 + pos_from_contributor - 1) % 12) + 1
                house_from_lagna = ((target_sign_num - lagna_num) % 12) + 1
                house_bindus[house_from_lagna] += 1
        result[target] = house_bindus
    return result


def compute_bav_points_str_keys(
    planet_signs: Dict[str, str],
    lagna_sign: str,
) -> Dict[str, Dict[str, int]]:
    """Same as compute_bav_points(), but with house numbers as string keys.

    Some downstream consumers (e.g. boosts.py:_bav_individual_boost, which
    expects bav_scores in the shape {"Mars": {"10": 6, ...}}) need string
    house keys rather than the int keys compute_bav_points() returns.
    """
    raw = compute_bav_points(planet_signs, lagna_sign)
    return {planet: {str(h): v for h, v in houses.items()} for planet, houses in raw.items()}


def compute_pav_data(
    planet_signs: Dict[str, str],
    lagna_sign: str,
) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Compute the full Prastarashtakavarga (PAV) -- the unreduced 8-source x
    12-house contribution grid PER reference (target) planet, i.e. the exact
    per-source bindu data that `compute_bav_points()` above already sums into
    each target planet's Bhinnashtakavarga (BAV) house totals, but exposed
    here BEFORE the summation instead of only after it.

    2026-07-08 gap fix: BAV (per-planet summed bindus, `compute_bav_points`)
    and SAV (grand total across all 7 BAVs, `engine_io.py`'s
    `_sav_normalized`) were both already computed, but the intermediate
    per-source detail -- "which of the 8 sources (7 planets + Lagna)
    contributed a bindu to which house, for THIS reference planet's BAV" --
    was discarded as soon as the per-house sum was taken, with no code path
    exposing it. This function re-derives exactly that intermediate grid
    from the same classical bindu tables (`_BAV_TABLES`) used by
    `compute_bav_points`, so the underlying source-by-source detail is
    available without changing that function's existing output shape (kept
    for backward compatibility with every existing consumer of
    `bav_points`).

    Output shape (documented here since there is no pre-existing PAV schema
    in this codebase to match):
        {reference_planet: {source: {house_str "1".."12": 0_or_1}}}
    where `reference_planet` is one of the 7 classical BAV targets (Sun,
    Moon, Mars, Mercury, Jupiter, Venus, Saturn), `source` is one of the 8
    classical contributors (the same 7 planets + "Lagna"), and each house's
    value is exactly 1 if that source placed a bindu in that house for that
    reference planet's Prastarashtakavarga, else 0. Summing
    pav_data[ref][source][house] over all 8 sources for a fixed
    (ref, house) reproduces compute_bav_points()[ref][int(house)] exactly --
    this identity is asserted by the accompanying test.
    """
    lagna_num = _SIGN_NUM.get(lagna_sign, 0)

    result: Dict[str, Dict[str, Dict[str, int]]] = {}
    for target, table in _BAV_TABLES.items():
        per_source: Dict[str, Dict[str, int]] = {
            src: {str(h): 0 for h in range(1, 13)} for src in CONTRIBUTORS
        }
        for contributor in CONTRIBUTORS:
            contributor_sign_num = _sign_num_for(contributor, planet_signs, lagna_sign)
            if not contributor_sign_num or not lagna_num:
                continue
            row = table.get(contributor)
            if not row:
                continue
            for pos_from_contributor in range(1, 13):
                bindu = row[pos_from_contributor - 1]
                if not bindu:
                    continue
                target_sign_num = ((contributor_sign_num - 1 + pos_from_contributor - 1) % 12) + 1
                house_from_lagna = ((target_sign_num - lagna_num) % 12) + 1
                per_source[contributor][str(house_from_lagna)] = 1
        result[target] = per_source
    return result
