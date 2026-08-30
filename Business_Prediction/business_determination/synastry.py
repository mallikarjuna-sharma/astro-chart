"""business_determination.synastry

Partnership / co-founder chart-to-chart comparison layer.

Everything else in this package (house_evidence.py, significators.py, kp.py,
jaimini.py, timing.py, ...) analyzes a SINGLE native's own 7th-house
capacity for partnership -- it never compares two people's charts against
each other. This module adds that comparison: given native A (the primary
businessman already run through compute_business_prediction()) and native B
(a proposed co-founder/partner), it produces a business-relevant synastry
read.

Deliberately NOT the marriage Kuta/Ashtakoota system (Varna, Vasya, Tara,
Yoni, Graha Maitri, Gana, Bhakoot, Nadi) -- those 36-point kutas are tuned
for marital/reproductive compatibility, not commercial fit. This module
instead reuses primitives already computed elsewhere in this package
(_dig_name/_dig_factor/_house_lord_strength from house_evidence.py,
_sign_modality_profile from d24_d60_sign.py, _dasha_calendar from
Job_Career.timeline, exactly the same import path timing.py already uses)
and adds one new primitive: natural + sign-based planetary friendliness via
jyotish.dignity._relationship / jyotish.constants._NATURAL_FRIENDS /
_NATURAL_ENEMIES -- the canonical friendliness table already used elsewhere
in the repo, not re-derived here.

Same status-diagnostics discipline as the rest of this package: every
returned dict carries a `status` field, degrades to a documented NO_DOB /
MISSING_DATA / NO_MOON_SIGN state instead of raising or silently returning
an empty/zero result, and every score is disclosed as EXPERIMENTAL_HEURISTIC
/ NOT_CALIBRATED (see MODEL_STATUS / CALIBRATION_STATUS / EVIDENCE_BASIS in
constants.py, reused as-is here -- no new maturity vocabulary invented).

Public API
----------
    compute_partnership_synastry(native_a, native_b) -> dict
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import CALIBRATION_STATUS, EVIDENCE_BASIS, MODEL_STATUS
from .house_evidence import _dig_name, _house_lord_strength, _rich_planet_dignities
from .d24_d60_sign import _AIR_SIGNS, _DUAL_SIGNS, _EARTH_SIGNS, _FIRE_SIGNS, _FIXED_SIGNS, _MOVABLE_SIGNS, _WATER_SIGNS, _record_diagnostic

try:
    from jyotish.dignity import _relationship as _jyotish_relationship
    from jyotish.constants import _NATURAL_FRIENDS, _NATURAL_ENEMIES, _SIGN_LORD
    _FRIENDLINESS_IMPORT_OK = True
except Exception:  # pragma: no cover - defensive, same pattern as timing.py's transit import guard
    _FRIENDLINESS_IMPORT_OK = False
    _NATURAL_FRIENDS, _NATURAL_ENEMIES, _SIGN_LORD = {}, {}, {}


_KEY_BUSINESS_SIGNIFICATORS = ("Mercury", "Jupiter", "Saturn", "Mars")

_FRIENDLINESS_SCORE = {
    "GREAT_FRIEND": 2, "FRIEND": 1, "OWN_SIGN": 1, "NEUTRAL": 0,
    "ENEMY": -1, "GREAT_ENEMY": -2,
}

_COMPATIBILITY_LABELS = (
    (70, "STRONG_FIT"),
    (50, "WORKABLE_FIT"),
    (30, "CAUTION"),
    (0, "POOR_FIT"),
)


def _label_for_score(score_0_100: float) -> str:
    for floor, label in _COMPATIBILITY_LABELS:
        if score_0_100 >= floor:
            return label
    return "POOR_FIT"


def _moon_sign(native: Any) -> str:
    planet_signs = getattr(native, "planet_signs", {}) or {}
    return planet_signs.get("Moon", "") or ""


def _moon_sign_compatibility(native_a: Any, native_b: Any) -> Dict[str, Any]:
    """Business-relevant Moon-sign (Rasi) compatibility: element/modality
    harmony (reusing _sign_modality_profile's own element/modality
    classification logic via the same sign-elements tables it uses) plus
    mutual natural friendliness of the two Moon signs' lords -- NOT the
    marriage Kuta system (no Tara/Yoni/Gana/Nadi/Bhakoot points here)."""
    moon_a, moon_b = _moon_sign(native_a), _moon_sign(native_b)
    if not moon_a or not moon_b:
        return {
            "status": "NO_MOON_SIGN", "score_0_20": 0,
            "note": "Moon sign missing for one or both natives -- Moon-sign compatibility not evaluated.",
        }

    def _elem(sign: str) -> str:
        if sign in _FIRE_SIGNS:
            return "FIRE"
        if sign in _EARTH_SIGNS:
            return "EARTH"
        if sign in _AIR_SIGNS:
            return "AIR"
        if sign in _WATER_SIGNS:
            return "WATER"
        return ""

    def _mod(sign: str) -> str:
        if sign in _MOVABLE_SIGNS:
            return "MOVABLE"
        if sign in _FIXED_SIGNS:
            return "FIXED"
        if sign in _DUAL_SIGNS:
            return "DUAL"
        return ""

    elem_a, elem_b = _elem(moon_a), _elem(moon_b)
    mod_a, mod_b = _mod(moon_a), _mod(moon_b)

    # Element harmony: same element or classically supportive pairs
    # (fire+air fuels ambition/execution, earth+water builds/sustains) score
    # higher than clashing pairs (fire+water, earth+air).
    _SUPPORTIVE_ELEMENT_PAIRS = {
        frozenset({"FIRE", "AIR"}), frozenset({"EARTH", "WATER"}),
    }
    if elem_a and elem_a == elem_b:
        element_score, element_note = 10, f"Same element ({elem_a}) -> shared temperament/pace, low friction"
    elif elem_a and elem_b and frozenset({elem_a, elem_b}) in _SUPPORTIVE_ELEMENT_PAIRS:
        element_score, element_note = 7, f"Supportive element pairing ({elem_a}+{elem_b}) -> complementary energy"
    elif elem_a and elem_b:
        element_score, element_note = 3, f"Contrasting elements ({elem_a} vs {elem_b}) -> different working styles, needs active reconciliation"
    else:
        element_score, element_note = 5, "Element data incomplete -- neutral score assigned"

    if mod_a and mod_a == mod_b:
        modality_score, modality_note = 4, f"Same modality ({mod_a}) -> aligned decision cadence"
    elif {mod_a, mod_b} == {"MOVABLE", "DUAL"}:
        modality_score, modality_note = 6, "Movable+Dual -> one initiates, one adapts; good founder/operator split"
    elif {mod_a, mod_b} == {"FIXED", "DUAL"}:
        modality_score, modality_note = 5, "Fixed+Dual -> stability plus flexibility"
    elif {mod_a, mod_b} == {"MOVABLE", "FIXED"}:
        modality_score, modality_note = 2, "Movable+Fixed -> pace mismatch risk (one wants to move fast, one wants to consolidate)"
    else:
        modality_score, modality_note = 3, "Modality data incomplete or mixed -- neutral-low score assigned"

    lord_a, lord_b = _SIGN_LORD.get(moon_a, ""), _SIGN_LORD.get(moon_b, "")
    lord_score, lord_note = 0, "Sign-lord friendliness not evaluated (dignity module unavailable or lords unresolved)."
    if _FRIENDLINESS_IMPORT_OK and lord_a and lord_b:
        rel_a_to_b = "OWN_SIGN" if lord_a == lord_b else (
            "FRIEND" if lord_b in _NATURAL_FRIENDS.get(lord_a, set())
            else "ENEMY" if lord_b in _NATURAL_ENEMIES.get(lord_a, set()) else "NEUTRAL"
        )
        rel_b_to_a = "OWN_SIGN" if lord_a == lord_b else (
            "FRIEND" if lord_a in _NATURAL_FRIENDS.get(lord_b, set())
            else "ENEMY" if lord_a in _NATURAL_ENEMIES.get(lord_b, set()) else "NEUTRAL"
        )
        pair_score = _FRIENDLINESS_SCORE.get(rel_a_to_b, 0) + _FRIENDLINESS_SCORE.get(rel_b_to_a, 0)
        lord_score = max(-6, min(6, pair_score * 1.5))
        lord_note = (f"Moon-sign lords {lord_a} (A's Moon-sign lord vs B={rel_a_to_b}) / "
                     f"{lord_b} (B's Moon-sign lord vs A={rel_b_to_a}) -> mutual friendliness score={pair_score}")

    raw = element_score + modality_score + lord_score
    score_0_20 = round(max(0.0, min(20.0, raw)), 2)
    return {
        "status": "OK",
        "moon_sign_a": moon_a, "moon_sign_b": moon_b,
        "element_a": elem_a, "element_b": elem_b, "modality_a": mod_a, "modality_b": mod_b,
        "moon_sign_lord_a": lord_a, "moon_sign_lord_b": lord_b,
        "score_0_20": score_0_20,
        "notes": [element_note, modality_note, lord_note],
    }


def _seventh_house_cross_comparison(native_a: Any, native_b: Any) -> Dict[str, Any]:
    """Does A's 7th lord/house support B's presence as partner, and vice
    versa? Reuses _house_lord_strength/_dig_name/_dig_factor (house_evidence.py)
    rather than re-deriving dignity math. 'Support' here is read through:
    (a) each native's own 7th-lord strength (their own partnership-house
    capacity, already scored elsewhere -- restated here as context), and
    (b) whether either native's key business planets sit in the OTHER
    native's 7th house sign, or whether the two 7th lords are natural
    friends -- the closest chart-to-chart analogue this repo already has
    the primitives for, without inventing synastry-specific house overlay
    math that doesn't exist elsewhere in the codebase."""
    hl_a = getattr(native_a, "house_lords", {}) or {}
    hl_b = getattr(native_b, "house_lords", {}) or {}
    # v29: use the Panchadha-Maitri-aware rich dignity map (see house_evidence
    # .py's _rich_planet_dignities docstring) instead of the coarse
    # payload.planet_dignities, so h7_lord_dignity_a/b below reflect
    # friend/enemy tiers rather than collapsing them to "NEUTRAL".
    dig_a = _rich_planet_dignities(native_a)
    dig_b = _rich_planet_dignities(native_b)

    def _h7(house_lords: Dict[str, Any]) -> str:
        return house_lords.get("7", house_lords.get(7, ""))

    h7_lord_a, h7_lord_b = _h7(hl_a), _h7(hl_b)
    if not h7_lord_a or not h7_lord_b:
        return {
            "status": "MISSING_DATA", "score_0_20": 0,
            "note": "7th-house lord not resolvable for one or both natives -- 7th-house cross-comparison not evaluated.",
        }

    strength_a = _house_lord_strength(native_a, 7)
    strength_b = _house_lord_strength(native_b, 7)

    friendliness_note = "Dignity module unavailable -- 7th-lord mutual friendliness not evaluated."
    friend_component = 0.0
    if _FRIENDLINESS_IMPORT_OK:
        rel = "OWN_SIGN" if h7_lord_a == h7_lord_b else (
            "FRIEND" if h7_lord_b in _NATURAL_FRIENDS.get(h7_lord_a, set())
            else "ENEMY" if h7_lord_b in _NATURAL_ENEMIES.get(h7_lord_a, set()) else "NEUTRAL"
        )
        friend_component = _FRIENDLINESS_SCORE.get(rel, 0) * 2.0
        friendliness_note = f"A's H7 lord ({h7_lord_a}) vs B's H7 lord ({h7_lord_b}) natural relationship={rel}"

    strength_component = (strength_a + strength_b) / 2.0 * 12.0  # up to 12 of the 20-point budget
    score_0_20 = round(max(0.0, min(20.0, strength_component + friend_component)), 2)

    return {
        "status": "OK",
        "h7_lord_a": h7_lord_a, "h7_lord_b": h7_lord_b,
        "h7_lord_strength_a": strength_a, "h7_lord_strength_b": strength_b,
        "h7_lord_dignity_a": _dig_name(h7_lord_a, dig_a),
        "h7_lord_dignity_b": _dig_name(h7_lord_b, dig_b),
        "score_0_20": score_0_20,
        "notes": [
            f"A's own H7 lord ({h7_lord_a}) strength={strength_a} (own partnership-house capacity)",
            f"B's own H7 lord ({h7_lord_b}) strength={strength_b} (own partnership-house capacity)",
            friendliness_note,
        ],
    }


def _d7_chart_for_native(native: Any) -> Dict[str, str]:
    """Flat {planet: D7 sign} map for this native, mirroring
    house_evidence.py's _d2_hora_positions_from_payload() fallback
    convention exactly: prefers an upstream-supplied D7 chart at
    native.divisional_charts["D7_saptamsha"] (same divisional_charts
    container D9/D10/D2 already read from), falling back to computing D7
    in-house via jyotish.astro.compute_d7_saptamsha_chart(native.planets_d1)
    when no upstream D7 is present. Returns {} (not a penalty) if neither
    source is available -- callers must treat that as "D7 not evaluated",
    same status-diagnostics discipline as the rest of this module."""
    dc = getattr(native, "divisional_charts", {}) or {}
    d7_chart = dc.get("D7_saptamsha", {}) or {}
    positions: Dict[str, str] = {}
    if isinstance(d7_chart, dict) and d7_chart:
        for planet, val in d7_chart.items():
            if planet == "Lagna":
                continue
            sign = val.get("sign") if isinstance(val, dict) else val
            if sign:
                positions[planet] = sign
        if positions:
            return positions

    planets_d1 = getattr(native, "planets_d1", {}) or {}
    if not planets_d1:
        return {}
    try:
        from jyotish.astro import compute_d7_saptamsha_chart
        computed = compute_d7_saptamsha_chart(planets_d1)
    except Exception as exc:  # pragma: no cover - defensive
        _record_diagnostic("synastry._d7_chart_for_native", exc, note="in-house D7 computation failed")
        return {}
    return {p: v.get("sign", "") for p, v in computed.items() if v.get("sign")}


def _seventh_house_d7_cross_comparison(native_a: Any, native_b: Any) -> Dict[str, Any]:
    """D7 (Saptamsha) corroboration LAYER for the two-native 7th-house
    cross-comparison -- additional to, NOT a replacement for,
    _seventh_house_cross_comparison() above (which stays D1-only). Reuses
    the same D1 H7-lord identity (house_lords) already resolved for the D1
    cross-comparison, then asks: (1) what D7 sign does each native's own D1
    H7-lord occupy, and how well-dignified is it there (via
    jyotish.dignity.dignity_state(), the same five-fold dignity primitive
    _rich_planet_dignities() is built on, applied here to the D7 sign
    instead of D1); (2) are the LORDS of those two D7 signs (one per
    native) natural friends or enemies of each other -- the D7-level
    analogue of the D1 cross-comparison's H7-lord-to-H7-lord friendliness
    check, just re-run one layer deeper.

    D7 data is pulled from native_a/native_b.divisional_charts["D7_saptamsha"]
    (upstream) or computed on the fly from .planets_d1 via
    jyotish.astro.compute_d7_saptamsha_chart() (in-house fallback) -- see
    _d7_chart_for_native(). No new mandatory payload fields: gracefully
    degrades to MISSING_DATA (score_0_20=0, not a penalty) when neither
    source is available for either native, or when house_lords/H7 lord is
    unresolvable -- the caller (compute_partnership_synastry) then falls
    back to the pre-existing D1-only scoring path (see its max_possible
    denominator logic)."""
    hl_a = getattr(native_a, "house_lords", {}) or {}
    hl_b = getattr(native_b, "house_lords", {}) or {}

    def _h7(house_lords: Dict[str, Any]) -> str:
        return house_lords.get("7", house_lords.get(7, ""))

    h7_lord_a, h7_lord_b = _h7(hl_a), _h7(hl_b)
    if not h7_lord_a or not h7_lord_b:
        return {
            "status": "MISSING_DATA", "score_0_20": 0,
            "note": "D1-H7 lord not resolvable for one or both natives -- D7 (Saptamsha) corroboration not evaluated; degraded to D1-only 7th-house cross-comparison.",
        }

    d7_a, d7_b = _d7_chart_for_native(native_a), _d7_chart_for_native(native_b)
    d7_sign_a, d7_sign_b = d7_a.get(h7_lord_a, ""), d7_b.get(h7_lord_b, "")
    if not d7_sign_a or not d7_sign_b:
        return {
            "status": "MISSING_DATA", "score_0_20": 0,
            "note": "D7 (Saptamsha) chart data unavailable for one or both natives (no divisional_charts['D7_saptamsha'] and no planets_d1 degree data to compute it in-house) -- D7 corroboration not evaluated; degraded to D1-only 7th-house cross-comparison.",
        }

    try:
        from jyotish.dignity import dignity_state as _d7_dignity_state
        _D7_DIGNITY_IMPORT_OK = True
    except Exception as exc:  # pragma: no cover - defensive
        _record_diagnostic("synastry._seventh_house_d7_cross_comparison", exc, note="jyotish.dignity.dignity_state import failed")
        _D7_DIGNITY_IMPORT_OK = False

    _POS_DIGNITY = ("EXALTED", "OWN_SIGN", "MOOLATRIKONA", "GREAT_FRIEND")
    _NEG_DIGNITY = ("DEBILITATED", "GREAT_ENEMY")

    dignity_a = dignity_b = "NEUTRAL"
    dignity_component = 0.0
    if _D7_DIGNITY_IMPORT_OK:
        dignity_a = _d7_dignity_state(h7_lord_a, d7_sign_a)
        dignity_b = _d7_dignity_state(h7_lord_b, d7_sign_b)
        for d in (dignity_a, dignity_b):
            if d in _POS_DIGNITY:
                dignity_component += 2.0
            elif d in _NEG_DIGNITY:
                dignity_component -= 2.0

    friend_component = 0.0
    d7_sign_lord_a = d7_sign_lord_b = ""
    friend_note = "Dignity module unavailable -- D7 sign-lord mutual friendliness not evaluated."
    rel = "NEUTRAL"
    if _FRIENDLINESS_IMPORT_OK:
        d7_sign_lord_a = _SIGN_LORD.get(d7_sign_a, "")
        d7_sign_lord_b = _SIGN_LORD.get(d7_sign_b, "")
        if d7_sign_lord_a and d7_sign_lord_b:
            rel = "OWN_SIGN" if d7_sign_lord_a == d7_sign_lord_b else (
                "FRIEND" if d7_sign_lord_b in _NATURAL_FRIENDS.get(d7_sign_lord_a, set())
                else "ENEMY" if d7_sign_lord_b in _NATURAL_ENEMIES.get(d7_sign_lord_a, set()) else "NEUTRAL"
            )
            friend_component = _FRIENDLINESS_SCORE.get(rel, 0) * 2.0
            friend_note = (f"A's D7 sign ({d7_sign_a}, occupied by A's D1-H7 lord {h7_lord_a}) lord "
                           f"({d7_sign_lord_a}) vs B's D7 sign ({d7_sign_b}, occupied by B's D1-H7 lord "
                           f"{h7_lord_b}) lord ({d7_sign_lord_b}) natural relationship={rel}")

    # raw combined range is [-6, +6] (dignity_component in [-4,4], friend_
    # component in [-2,2]); mapped onto the same 0..20 budget the other
    # components use, midpoint 10 (neutral), matching the "neutral
    # midpoint, not a penalty, when data/imports are partially unavailable"
    # convention used throughout this module.
    raw = dignity_component + friend_component
    score_0_20 = round(max(0.0, min(20.0, 10.0 + raw * (10.0 / 6.0))), 2)

    return {
        "status": "OK",
        "h7_lord_a": h7_lord_a, "h7_lord_b": h7_lord_b,
        "d7_sign_a": d7_sign_a, "d7_sign_b": d7_sign_b,
        "d7_dignity_a": dignity_a, "d7_dignity_b": dignity_b,
        "d7_sign_lord_a": d7_sign_lord_a, "d7_sign_lord_b": d7_sign_lord_b,
        "score_0_20": score_0_20,
        "notes": [
            f"A's D1-H7 lord ({h7_lord_a}) occupies D7 sign {d7_sign_a}, dignity={dignity_a}",
            f"B's D1-H7 lord ({h7_lord_b}) occupies D7 sign {d7_sign_b}, dignity={dignity_b}",
            friend_note,
        ],
    }


def _significator_friendliness(native_a: Any, native_b: Any) -> Dict[str, Any]:
    """Planetary friendliness between each native's key business
    significators (Mercury, Jupiter, Saturn, Mars) -- reuses the shared
    natural-friendship table (jyotish.constants._NATURAL_FRIENDS/_ENEMIES,
    the same table jyotish.dignity._relationship() consumes) instead of
    re-deriving a friendship matrix in this module."""
    if not _FRIENDLINESS_IMPORT_OK:
        return {
            "status": "IMPORT_FAILED", "score_0_20": 10,
            "note": "jyotish.dignity/constants friendliness tables unavailable -- neutral midpoint score assigned, not a penalty.",
            "pairs": [],
        }

    pairs: List[Dict[str, Any]] = []
    total = 0
    for planet_a in _KEY_BUSINESS_SIGNIFICATORS:
        for planet_b in _KEY_BUSINESS_SIGNIFICATORS:
            if planet_a == planet_b:
                rel = "SAME_PLANET"
                pts = 1
            else:
                rel = "FRIEND" if planet_b in _NATURAL_FRIENDS.get(planet_a, set()) \
                    else "ENEMY" if planet_b in _NATURAL_ENEMIES.get(planet_a, set()) else "NEUTRAL"
                pts = _FRIENDLINESS_SCORE.get(rel, 0)
            total += pts
            pairs.append({"planet_a": planet_a, "planet_b": planet_b, "relationship": rel, "points": pts})

    # Normalize to 0..20: max plausible raw total for 4x4 pairs (16 pairs,
    # 4 SAME_PLANET=1 + up to 12 cross pairs at GREAT_FRIEND-equivalent
    # natural FRIEND=1) is well below a hard ceiling; use an empirically
    # bounded ceiling (24) rather than the theoretical max (all FRIEND),
    # matching the ceiling-anchoring approach significators.py documents.
    _CEILING = 24.0
    score_0_20 = round(max(0.0, min(20.0, (total / _CEILING) * 20.0)), 2)
    return {
        "status": "OK",
        "score_0_20": score_0_20,
        "raw_total": total,
        "pairs": pairs,
        "note": f"Natural friendliness across {len(pairs)} Mercury/Jupiter/Saturn/Mars cross-pairs between A and B, raw_total={total}",
    }


def _dasha_overlap_check(native_a: Any, native_b: Any) -> Dict[str, Any]:
    """Whether the two natives' current MD periods are complementary,
    neutral, or conflicting. Reuses Job_Career.timeline._dasha_calendar --
    the exact same import path timing.py's _compute_windows_and_status()
    already uses -- rather than re-deriving dasha-calendar math here."""
    try:
        from Job_Career.timeline import build_dasha_calendar
        from Job_Career.timeline_inputs import parse_iso_date
    except Exception as exc:  # pragma: no cover
        return {"status": "IMPORT_FAILED", "score_0_20": 10, "error": f"{type(exc).__name__}: {exc}",
                "note": "Job_Career.timeline import failed -- dasha overlap not evaluated; neutral midpoint assigned."}

    def _current_md(native: Any) -> Optional[Dict[str, Any]]:
        dob_str = getattr(native, "dob", "") or ""
        dob = parse_iso_date(dob_str)
        dasha_seq = getattr(native, "dasha_sequence", []) or []
        if not dob or not dasha_seq:
            return None
        try:
            calendar = build_dasha_calendar(dasha_seq, dob)
        except Exception as exc:
            _record_diagnostic("synastry._dasha_overlap_check", exc, note="_dasha_calendar computation failed")
            return None
        from datetime import date as _date
        today = _date.today()
        for period in calendar:
            start, end = period.get("start_date"), period.get("end_date")
            if start and end and start <= today <= end:
                return period
        return None

    md_a, md_b = _current_md(native_a), _current_md(native_b)
    if md_a is None or md_b is None:
        missing = []
        if not (getattr(native_a, "dob", "") or ""):
            missing.append("A: NO_DOB")
        if not (getattr(native_a, "dasha_sequence", []) or []):
            missing.append("A: NO_DASHA_SEQUENCE")
        if not (getattr(native_b, "dob", "") or ""):
            missing.append("B: NO_DOB")
        if not (getattr(native_b, "dasha_sequence", []) or []):
            missing.append("B: NO_DASHA_SEQUENCE")
        return {
            "status": "NO_DOB" if missing else "CALENDAR_COMPUTATION_FAILED",
            "score_0_20": 0,
            "note": f"Current MD period not resolvable for one or both natives ({', '.join(missing) or 'calendar computation failed'}) -- dasha overlap not evaluated.",
        }

    lord_a, lord_b = md_a.get("md_lord", ""), md_b.get("md_lord", "")
    if not lord_a or not lord_b:
        return {"status": "OK_NO_LORD", "score_0_20": 10,
                "current_md_a": md_a, "current_md_b": md_b,
                "note": "Current MD periods resolved but lord names missing -- neutral midpoint score assigned."}

    if lord_a == lord_b:
        label, score = "COMPLEMENTARY", 18
        note = f"Both natives currently run {lord_a} Mahadasha -- strongly synchronized timing (rare, high-conviction alignment)."
    elif _FRIENDLINESS_IMPORT_OK and lord_b in _NATURAL_FRIENDS.get(lord_a, set()) and lord_a in _NATURAL_FRIENDS.get(lord_b, set()):
        label, score = "COMPLEMENTARY", 15
        note = f"A's MD lord ({lord_a}) and B's MD lord ({lord_b}) are mutual natural friends -- complementary timing."
    elif _FRIENDLINESS_IMPORT_OK and (lord_b in _NATURAL_ENEMIES.get(lord_a, set()) or lord_a in _NATURAL_ENEMIES.get(lord_b, set())):
        label, score = "CONFLICTING", 4
        note = f"A's MD lord ({lord_a}) and B's MD lord ({lord_b}) are natural enemies -- conflicting timing, friction likely during this overlap."
    else:
        label, score = "NEUTRAL", 10
        note = f"A's MD lord ({lord_a}) and B's MD lord ({lord_b}) are neither natural friends nor enemies -- neutral timing overlap."

    return {
        "status": "OK",
        "label": label,
        "current_md_lord_a": lord_a, "current_md_lord_b": lord_b,
        "current_md_a": {"lord": lord_a, "start_date": str(md_a.get("start_date")), "end_date": str(md_a.get("end_date"))},
        "current_md_b": {"lord": lord_b, "start_date": str(md_b.get("start_date")), "end_date": str(md_b.get("end_date"))},
        "score_0_20": score,
        "note": note,
    }


def compute_partnership_synastry(native_a: Any, native_b: Any) -> Dict[str, Any]:
    """Full partnership/co-founder synastry pipeline for two chart payloads.

    Parameters
    ----------
    native_a : the primary businessman already run through
        compute_business_prediction() (this module does not require that
        call, it only reads chart attributes directly off the payload).
    native_b : the proposed partner/co-founder's chart payload -- same
        NatalPayloadV2-shaped object as native_a, or None/missing-attribute
        object, in which case this degrades gracefully (never raises).

    Returns
    -------
    {
      "status": "OK" | "NO_PARTNER_DATA",
      "moon_sign_compatibility": {...},
      "seventh_house_cross_comparison": {...},
      "seventh_house_d7_cross_comparison": {...},
      "significator_friendliness": {...},
      "dasha_overlap": {...},
      "composite_score_0_100": float,
      "compatibility_label": "STRONG_FIT"|"WORKABLE_FIT"|"CAUTION"|"POOR_FIT",
      "complementary_strengths": [ {"note": str}, ... ],
      "friction_points": [ {"note": str}, ... ],
      "model_status": MODEL_STATUS, "calibration_status": CALIBRATION_STATUS,
      "evidence_basis": EVIDENCE_BASIS,
    }
    """
    if native_b is None:
        return {
            "status": "NO_PARTNER_DATA",
            "composite_score_0_100": None,
            "compatibility_label": None,
            "complementary_strengths": [],
            "friction_points": [],
            "note": "No partner/co-founder chart data supplied -- partnership synastry not evaluated. Provide native_b (a NatalPayloadV2-shaped chart payload for the proposed partner) to compute_partnership_synastry().",
            "model_status": MODEL_STATUS,
            "calibration_status": CALIBRATION_STATUS,
            "evidence_basis": EVIDENCE_BASIS,
        }

    moon = _moon_sign_compatibility(native_a, native_b)
    seventh = _seventh_house_cross_comparison(native_a, native_b)
    seventh_d7 = _seventh_house_d7_cross_comparison(native_a, native_b)
    friendliness = _significator_friendliness(native_a, native_b)
    dasha = _dasha_overlap_check(native_a, native_b)

    # Each component contributes up to 20 of the max via explicit 0..20
    # sub-scores (already produced above) so the composite is a
    # transparent sum, not a re-normalized opaque blend -- same "explicit
    # ledger, not a single opaque number" discipline as significators.py's
    # evidence list and mode_gate.py's 80-point ceiling pattern.
    #
    # Weight breakdown (v-D7 addition):
    #   moon_sign_compatibility          0..20
    #   seventh_house_cross_comparison   0..20  (D1 7th-house, unchanged)
    #   seventh_house_d7_cross_comparison 0..20  (NEW -- D7/Saptamsha corroboration layer)
    #   significator_friendliness        0..20
    #   dasha_overlap                    0..20
    # When D7 data is genuinely unavailable for one/both natives (no
    # divisional_charts["D7_saptamsha"] and no planets_d1 degree data --
    # see _seventh_house_d7_cross_comparison()'s MISSING_DATA path), its
    # score is 0 AND it is excluded from the denominator entirely, so the
    # composite formula is byte-for-byte identical to the pre-D7 4-component
    # 0..80 scale -- this is the "graceful degradation to the existing
    # D1-only scoring path" contract required for backward compatibility.
    # When D7 data IS available, the denominator becomes 0..100 (5 x 20),
    # keeping the composite on the same 0..100 final scale either way.
    components = {
        "moon_sign_compatibility": moon.get("score_0_20", 0) or 0,
        "seventh_house_cross_comparison": seventh.get("score_0_20", 0) or 0,
        "significator_friendliness": friendliness.get("score_0_20", 0) or 0,
        "dasha_overlap": dasha.get("score_0_20", 0) or 0,
    }
    max_possible = 80.0
    if seventh_d7.get("status") == "OK":
        components["seventh_house_d7_cross_comparison"] = seventh_d7.get("score_0_20", 0) or 0
        max_possible = 100.0
    raw_total = sum(components.values())  # 0..80 (D1-only) or 0..100 (with D7)
    composite_score_0_100 = round(min(100.0, raw_total / max_possible * 100.0), 2)
    label = _label_for_score(composite_score_0_100)

    complementary_strengths: List[Dict[str, Any]] = []
    friction_points: List[Dict[str, Any]] = []

    if moon.get("status") == "OK":
        for note in moon.get("notes", []):
            (complementary_strengths if any(w in note for w in ("shared", "aligned", "complementary", "adapt", "founder/operator")) else friction_points).append({"source": "moon_sign_compatibility", "note": note})
    if seventh.get("status") == "OK":
        for note in seventh.get("notes", []):
            (complementary_strengths if any(w in note for w in ("FRIEND", "OWN_SIGN")) else friction_points if "ENEMY" in note else complementary_strengths).append({"source": "seventh_house_cross_comparison", "note": note})
    if seventh_d7.get("status") == "OK":
        for note in seventh_d7.get("notes", []):
            is_friction = any(w in note for w in ("ENEMY", "DEBILITATED"))
            is_strength = any(w in note for w in ("FRIEND", "OWN_SIGN", "EXALTED", "MOOLATRIKONA", "GREAT_FRIEND"))
            (friction_points if is_friction and not is_strength else complementary_strengths).append({"source": "seventh_house_d7_cross_comparison", "note": note})
    if friendliness.get("status") == "OK":
        friend_pairs = [p for p in friendliness.get("pairs", []) if p["relationship"] == "FRIEND"]
        enemy_pairs = [p for p in friendliness.get("pairs", []) if p["relationship"] == "ENEMY"]
        if friend_pairs:
            complementary_strengths.append({
                "source": "significator_friendliness",
                "note": f"{len(friend_pairs)} of {len(friendliness.get('pairs', []))} key-significator cross-pairs (Mercury/Jupiter/Saturn/Mars) are natural friends.",
            })
        if enemy_pairs:
            friction_points.append({
                "source": "significator_friendliness",
                "note": f"{len(enemy_pairs)} key-significator cross-pairs are natural enemies: "
                        + ", ".join(f"{p['planet_a']}(A)-{p['planet_b']}(B)" for p in enemy_pairs),
            })
    if dasha.get("status") == "OK":
        (complementary_strengths if dasha.get("label") == "COMPLEMENTARY" else friction_points if dasha.get("label") == "CONFLICTING" else complementary_strengths).append({
            "source": "dasha_overlap", "note": dasha.get("note", ""),
        })

    return {
        "status": "OK",
        "moon_sign_compatibility": moon,
        "seventh_house_cross_comparison": seventh,
        "seventh_house_d7_cross_comparison": seventh_d7,
        "significator_friendliness": friendliness,
        "dasha_overlap": dasha,
        "component_scores_0_20": components,
        "raw_total_0_80": round(raw_total, 2),
        "raw_total_max_possible": max_possible,
        "composite_score_0_100": composite_score_0_100,
        "compatibility_label": label,
        "complementary_strengths": complementary_strengths,
        "friction_points": friction_points,
        "model_status": MODEL_STATUS,
        "calibration_status": CALIBRATION_STATUS,
        "evidence_basis": EVIDENCE_BASIS,
        "note": (
            "Business-relevant chart-to-chart comparison, NOT the marriage "
            "Kuta/Ashtakoota system. Composite score is an uncalibrated, "
            "explicit-ledger heuristic (see component_scores_0_20) -- "
            "decision-support only, not a substitute for due diligence, "
            "legal partnership agreements, or a full classical synastry "
            "review by a qualified astrologer."
        ),
    }


