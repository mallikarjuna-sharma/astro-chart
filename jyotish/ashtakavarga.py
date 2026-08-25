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

from .constants import _SIGN_NUM, _SIGN_LORD

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


# ── Shodhana (BPHS Ch.5 reduction processes) ────────────────────────────────
# GAP-FIX (2026-07-20, astrological-gap pass): the tables above reproduce raw
# Bhinnashtakavarga/Sarvashtakavarga bindus, cross-verified against PyJHora
# and the classical grand totals. BPHS itself does not stop at the raw
# bindus -- two reduction (shodhana) processes are classically applied before
# the bindu counts are used for prediction: Trikona Shodhana (trine
# normalization) and Ekadhipatya Shodhana (same-lord-house normalization).
# This engine previously computed and consumed only the raw, unreduced
# totals (see engine_io.py `_sav_normalized` and
# Field_Determination/field_methods/__init__.py's SAV confidence multiplier)
# with no disclosure that the classical reduction step was being skipped.
#
# Honesty note on provenance (matching this codebase's existing convention
# for items like SIGNAL.BHRIGU_BINDU/SIGNAL.SUDARSHANA): the *existence* and
# general mechanics of both shodhana processes are well attested across
# secondary Ashtakavarga literature and standard software implementations
# (the same class of source already cited for this module's bindu tables),
# but this session did not independently retrieve a primary BPHS
# chapter/verse pinning the exact pairwise-vs-minimum-subtraction arithmetic
# below. The algorithm implemented is the one most consistently described
# across secondary sources and matches common Jyotish software convention;
# treat it as classically_attested_secondary_literature, not verse-exact.
_SIGNS_IN_ORDER: List[str] = sorted(_SIGN_NUM, key=lambda s: _SIGN_NUM[s])

# The four trikona (trine) groups, houses counted from Lagna (1-12).
TRIKONA_GROUPS: List[List[int]] = [[1, 5, 9], [2, 6, 10], [3, 7, 11], [4, 8, 12]]


def apply_trikona_shodhana(house_bindus: Dict[int, int]) -> Dict[int, int]:
    """Trikona Shodhana: within each of the four trine groups (1-5-9, 2-6-10,
    3-7-11, 4-8-12), reduce every house's bindu count by the minimum bindu
    count found anywhere in that same group. This is the standard
    "normalize to the group's own floor" mechanic: a trine group where one
    house has 0 bindus contributes nothing extra from its trine-mates either
    (all three drop to their excess-over-zero), while a group where all
    three houses are evenly strong is left with a smaller, but still
    internally consistent, positive count in every house.

    Input/output: {house_num (1-12): bindu_count}, same shape as one entry
    of compute_bav_points()'s return value.
    """
    reduced = dict(house_bindus)
    for group in TRIKONA_GROUPS:
        values = [house_bindus.get(h, 0) for h in group]
        floor = min(values) if values else 0
        for h in group:
            reduced[h] = house_bindus.get(h, 0) - floor
    return reduced


def apply_ekadhipatya_shodhana(
    house_bindus: Dict[int, int],
    lagna_sign: str,
) -> Dict[int, int]:
    """Ekadhipatya Shodhana: for any planet that rules two of the twelve
    houses (every classical graha except Sun and Moon, which rule exactly
    one sign each), compare that planet's two ruled houses' bindu counts.
    If they are unequal, the house with the LOWER count is reduced to zero
    (the weaker of the two ownership claims is dropped entirely, rather than
    partially discounted); if equal, both are left unchanged, since there is
    no basis to prefer one over the other.

    Sun and Moon (single-sign rulers) never trigger this reduction; Rahu/
    Ketu are shadow points with no sign rulership in the classical scheme
    and are likewise excluded.

    Input/output: {house_num (1-12): bindu_count}. House-to-sign mapping is
    derived from lagna_sign using whole-sign houses, matching this repo's
    existing house-system convention (see calculation_policy.natal_house_system).
    """
    reduced = dict(house_bindus)
    lagna_num = _SIGN_NUM.get(lagna_sign, 0)
    if not lagna_num:
        return reduced

    # House -> ruling planet, via whole-sign houses from Lagna.
    house_lord: Dict[int, str] = {}
    for house in range(1, 13):
        sign_num = ((lagna_num - 1 + house - 1) % 12) + 1
        sign_name = _SIGNS_IN_ORDER[sign_num - 1]
        house_lord[house] = _SIGN_LORD.get(sign_name, "")

    # Group houses by their lord; only lords ruling exactly 2 houses (every
    # classical graha except Sun/Moon) are eligible for this reduction.
    lord_houses: Dict[str, List[int]] = {}
    for house, lord in house_lord.items():
        if lord in ("Sun", "Moon", ""):
            continue
        lord_houses.setdefault(lord, []).append(house)

    for lord, houses in lord_houses.items():
        if len(houses) != 2:
            continue
        h1, h2 = houses
        v1, v2 = house_bindus.get(h1, 0), house_bindus.get(h2, 0)
        if v1 < v2:
            reduced[h1] = 0
        elif v2 < v1:
            reduced[h2] = 0
        # v1 == v2: both left unchanged, per the honesty note above.
    return reduced


def compute_bav_points_shodhita(
    planet_signs: Dict[str, str],
    lagna_sign: str,
) -> Dict[str, Dict[int, int]]:
    """Raw BAV (compute_bav_points) with both classical shodhana reductions
    applied, per target planet. Applied in the conventional order (Trikona
    first, then Ekadhipatya on the trikona-reduced counts) since Ekadhipatya
    is meant to compare already-normalized house strengths.
    """
    raw = compute_bav_points(planet_signs, lagna_sign)
    out: Dict[str, Dict[int, int]] = {}
    for target, houses in raw.items():
        trikona_reduced = apply_trikona_shodhana(houses)
        out[target] = apply_ekadhipatya_shodhana(trikona_reduced, lagna_sign)
    return out


def compute_sav_points_shodhita(
    planet_signs: Dict[str, str],
    lagna_sign: str,
) -> Dict[int, int]:
    """Sarvashtakavarga (grand total across all 7 target planets' BAVs) built
    from the shodhana-reduced per-target BAVs, not the raw ones. This is
    additive/new -- see the module-level GAP-FIX note above for why this is
    NOT yet wired into the live SAV confidence multiplier
    (Field_Determination/field_methods/__init__.py): that multiplier's
    thresholds (>=360, >=340, <=300, <=280) were empirically set against RAW
    SAV totals (grand total 337 across all targets), and shodhana reduction
    systematically lowers totals, so swapping the input without
    recalibrating the thresholds would silently miscalibrate every chart's
    confidence multiplier. Exposed here as correct, disclosed data for a
    follow-up recalibration pass, not a silent scoring change.
    """
    bav_shodhita = compute_bav_points_shodhita(planet_signs, lagna_sign)
    sav: Dict[int, int] = {h: 0 for h in range(1, 13)}
    for houses in bav_shodhita.values():
        for h, v in houses.items():
            sav[h] += v
    return sav
