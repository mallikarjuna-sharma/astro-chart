"""Yogini Dasha field-determination module.

GAP FIX (2026-08-17): the 9-step career-determination framework's Step 7
("Dasha-Based Longevity Filter") explicitly calls for scoring a field's
supporting planets against BOTH current/upcoming Vimshottari AND Yogini
Dasha windows. Prior to this fix, Yogini Dasha had zero references anywhere
in the Field_Determination engine (Job_Career's astro_enhancer.py already
scored it via `_g16_yogini_dasha`, but Field_Determination -- the more
sophisticated of the two career engines -- had no equivalent).

Mirrors Job_Career/astro_enhancer.py's `_g16_yogini_dasha` cycle math (start
index derived from Moon-nakshatra pada, 8-yogini/36-year cycle), but is
wired here the same way D9/Navamsha is wired into this engine (see
navamsha.py's `score_navamsha_adjustment`): as a bounded post-blend
CONFIRMATION multiplier, not an independent ninth vote. Rationale: Yogini
Dasha is a secondary/alternative dasha system used classically to confirm or
add timing nuance to a Vimshottari-based read, not to independently
determine which field fits -- the same logic navamsha.py's docstring uses to
justify D9's multiplier-not-vote treatment. Bounded to +/-8% for the same
reason (shift close rankings without overriding the primary weighted-blend
methods).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

# 27 nakshatras in classical order, needed to convert a Moon-nakshatra name +
# pada (1-4) into an absolute pada number (1-108) for the Yogini start-index
# calculation, matching Job_Career/astro_enhancer.py's `moon_nakshatra_pada_num`.
_NAKSHATRA_ORDER: List[str] = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

# (name, ruling_planet, years) — same 8-Yogini, 36-year cycle used in
# Job_Career/astro_enhancer.py's `_YOGINI_DATA`.
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

_YOGINI_MULT_MIN = 0.92
_YOGINI_MULT_MAX = 1.08


def _moon_nakshatra_pada_num(moon_nakshatra: str, moon_pada: int) -> int:
    """Absolute pada number 1-108, or 0 if the nakshatra name isn't recognized."""
    if not moon_nakshatra or moon_nakshatra not in _NAKSHATRA_ORDER:
        return 0
    nak_idx = _NAKSHATRA_ORDER.index(moon_nakshatra)
    pada = moon_pada if moon_pada in (1, 2, 3, 4) else 1
    return nak_idx * 4 + pada


def get_current_yogini(moon_nakshatra: str, moon_pada: int, current_age: float) -> Tuple[str, str]:
    """Return (yogini_name, ruling_planet) active at `current_age` years old.

    Uses the same cycle math as Job_Career/astro_enhancer.py's
    `_g16_yogini_dasha`, substituting `current_age` for
    `(period_start - dob).days / 365.25` since Field_Determination scores a
    single "as-of-now" chart snapshot rather than per-dasha-period timelines.

    GAP-FIX (2026-08, astrological audit): the STARTING Yogini lord is
    classically determined by birth NAKSHATRA alone -- every pada of a given
    nakshatra shares the same starting Yogini; only the precise balance of
    the dasha elapsed at birth (not which Yogini starts) is degree/pada-
    sensitive, and this function doesn't attempt that finer balance anyway
    (it works off `current_age` directly, not days-elapsed-since-birth
    within the first Yogini period). The prior version derived the start
    index from the absolute 1-108 pada number (`(pada_num - 1) % 8`), which
    rotates the starting Yogini across the FOUR padas of the SAME nakshatra
    (e.g. Bharani pada 1-4 previously resolved to four different Yoginis
    instead of the one classically-correct lord for all of Bharani). Fixed
    to index purely off the nakshatra's own 0-based position, matching the
    standard cyclic nakshatra-to-Yogini table (Ashwini/Ashlesha/Magha/
    Moola-group -> Mangala start, Bharani/... -> Pingala start, and so on,
    repeating every 8 nakshatras) used by Job_Career/astro_enhancer.py's
    `_g16_yogini_dasha` sibling implementation.
    """
    if not moon_nakshatra or moon_nakshatra not in _NAKSHATRA_ORDER:
        return "", ""
    if current_age is None or current_age < 0:
        return "", ""
    nak_idx = _NAKSHATRA_ORDER.index(moon_nakshatra)

    start_idx = nak_idx % 8
    total_years = sum(y for _, _, y in _YOGINI_DATA)  # 36
    elapsed_in_cycle = float(current_age) % total_years
    cumulative = 0.0
    for i in range(8):
        name, planet, years = _YOGINI_DATA[(start_idx + i) % 8]
        if cumulative + years > elapsed_in_cycle:
            return name, planet
        cumulative += years
    name, planet, _ = _YOGINI_DATA[start_idx % 8]
    return name, planet


def score_yogini_dasha_adjustment(
    payload_data: Any,
    field_affinity: Mapping[str, float] | None = None,
) -> Dict[str, Any]:
    """Bounded confirmation multiplier from the current Yogini Dasha lord's
    affinity to this field.

    Returns {"status", "multiplier", "trace", "yogini_name", "yogini_lord"}.
    multiplier is in [_YOGINI_MULT_MIN, _YOGINI_MULT_MAX]; 1.0 = neutral/no data.
    """
    moon_nakshatra = str(getattr(payload_data, "moon_nakshatra", "") or "")
    moon_pada = int(getattr(payload_data, "moon_nakshatra_pada", 0) or 0)
    current_age = getattr(payload_data, "current_age", None)

    if not field_affinity or not moon_nakshatra or not current_age:
        return {
            "status": "UNCONFIRMED_NO_YOGINI_DATA",
            "multiplier": 0.97,
            "trace": [
                "Moon nakshatra/pada, current age, or field affinity unavailable — "
                "no independent Yogini Dasha confirmation possible; applying a mild "
                "confidence dampener (0.97x) rather than a silent neutral 1.0x."
            ],
            "yogini_name": "", "yogini_lord": "",
        }

    name, lord = get_current_yogini(moon_nakshatra, moon_pada, float(current_age))
    if not name or not lord:
        return {
            "status": "UNCONFIRMED_NO_YOGINI_DATA",
            "multiplier": 0.97,
            "trace": ["Could not resolve a Yogini Dasha lord from the available Moon-nakshatra data."],
            "yogini_name": "", "yogini_lord": "",
        }

    max_aff = max((v for v in field_affinity.values() if v is not None), default=0.0)
    lord_aff = field_affinity.get(lord, 0.0) or 0.0
    ratio = (lord_aff / max_aff) if max_aff > 0 else 0.5
    ratio = min(1.0, max(0.0, ratio))

    multiplier = round(_YOGINI_MULT_MIN + (_YOGINI_MULT_MAX - _YOGINI_MULT_MIN) * ratio, 4)
    trace = [
        f"Current Yogini Dasha is {name} (ruled by {lord}); field-affinity ratio "
        f"{ratio:.2f} against this field's top-affinity planet -> {multiplier}x confirmation."
    ]
    return {
        "status": "CONFIRMED",
        "multiplier": multiplier,
        "trace": trace,
        "yogini_name": name,
        "yogini_lord": lord,
    }
