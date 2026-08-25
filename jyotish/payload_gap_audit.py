"""Incoming-JSON ingestion audit — extraction/validation gap for Step 1.

GAP FIX (2026-08-17): the 9-step career-determination framework's Step 1
("Foundational Chart Assessment") depends on a chart payload that is
actually complete. Prior to this fix, `jyotish/engine_io.py::parse_json_payload`
extracted every field with silent `.get(..., default)` fallbacks -- a
missing `moon_nakshatra`, `atmakaraka`, or `dasha_sequence` in the incoming
JSON degraded silently to "" / {} / [] with no record that anything was
missing, and every downstream scorer (this session added several -- Yogini
Dasha, the Vimshottari longevity filter, Step-9 convergence) would then
silently score that dimension as neutral without anyone knowing why.

The ONLY existing ingestion-time check, `jyotish.engine._validate_payload_schema`,
is an all-or-nothing gate on exactly four fields (planets_d1,
kp_significators, kp_cusps, dasha_sequence) that raises ValueError and stops
the whole engine run. It does not flag gaps in the other ~15 fields the
9-step framework and this session's fixes actually depend on, and it never
attempts to fill in a value that IS derivable from data already present.

This module is deliberately NOT a replacement for that hard gate -- it runs
BEFORE it, in `parse_json_payload`, right after the NatalPayloadV2 object is
constructed, and does two things `_validate_payload_schema` does not:
    1. Audits a much wider field set (everything the 9-step framework and
       this session's Yogini/longevity/convergence/AmK fixes read), and
       flags gaps with a severity level and a plain-English description of
       exactly which downstream feature the gap silently degrades.
    2. For a specific, deliberately conservative set of fields that ARE
       safely re-derivable from other fields already present on the SAME
       payload (no ephemeris, no external lookups), computes and fills the
       value in place, and records what was derived and why -- so a
       consumer can distinguish "genuinely supplied by the source chart"
       from "reconstructed here because it was missing."
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

_ZODIAC_ORDER: List[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_SIGN_LORD: Dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

# 27 nakshatras in classical order, 13°20' each -- used only for the
# conservative moon_nakshatra derivation below when jyotish.astro's own
# get_nakshatra_from_longitude isn't importable (avoids a hard dependency /
# possible circular import; falls back to this self-contained table).
_NAKSHATRA_ORDER: List[str] = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

# Severity levels, ordered by how much they degrade downstream scoring.
CRITICAL = "CRITICAL"    # blocks a whole scoring layer; that layer returns neutral for every field
IMPORTANT = "IMPORTANT"  # degrades one specific signal within a layer
OPTIONAL = "OPTIONAL"    # narrative/advisory-only impact


def _sign_from_house(lagna_sign: str, house_num: int) -> str:
    if not lagna_sign or lagna_sign not in _ZODIAC_ORDER or not house_num:
        return ""
    lagna_idx = _ZODIAC_ORDER.index(lagna_sign)
    return _ZODIAC_ORDER[(lagna_idx + house_num - 1) % 12]


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (int, float)):
        return value == 0
    if hasattr(value, "__len__"):
        return len(value) == 0
    return False


def _derive_house_lords(lagna_sign: str) -> Dict[str, str]:
    """Whole-sign house-lord map for all 12 houses from lagna_sign alone --
    purely a lookup table, needs no ephemeris."""
    out: Dict[str, str] = {}
    for h in range(1, 13):
        sign = _sign_from_house(lagna_sign, h)
        out[str(h)] = _SIGN_LORD.get(sign, "")
    return out


def _derive_moon_nakshatra(moon_longitude: float) -> str:
    if moon_longitude is None:
        return ""
    idx = int((float(moon_longitude) % 360.0) // (360.0 / 27.0))
    idx = max(0, min(26, idx))
    return _NAKSHATRA_ORDER[idx]


def _derive_current_age(dob_str: str) -> Optional[float]:
    """Rough fallback recompute of current_age from dob, using today's date.
    Flagged as approximate in the audit report -- this is NOT a substitute
    for the original chart's own `current_date` context, which may differ
    from wall-clock "today" (e.g. a report generated for a past/future
    reference date). Only used when current_age is missing/zero AND dob is
    present, as a last resort so downstream career-phase logic doesn't
    silently divide-by/compare-against 0."""
    if not dob_str:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            dob = datetime.strptime(str(dob_str)[:10], fmt).date()
            break
        except ValueError:
            dob = None
    if dob is None:
        return None
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return float(age)


def _derive_karaka_by_strength(eff_strengths: Dict[str, float], exclude: Optional[set] = None, rank: int = 1) -> str:
    """Approximate Atmakaraka/Amatyakaraka by Shadbala-derived strength
    ranking when the real (degree-based) Jaimini karaka isn't supplied.
    This is a DELIBERATE approximation, not the classical computation
    (true AK/AmK use each planet's degree-within-sign, not overall
    strength) -- flagged as low-confidence in the audit report so a
    consumer can choose not to trust it for precision Jaimini work."""
    if not eff_strengths:
        return ""
    exclude = exclude or {"Rahu", "Ketu"}
    ranked = sorted(
        ((p, v) for p, v in eff_strengths.items() if p not in exclude and v is not None),
        key=lambda kv: -kv[1],
    )
    if len(ranked) < rank:
        return ""
    return ranked[rank - 1][0]


def _build_kp_significators_fallback(planet_house: Dict[str, int], kp_cusps: Dict[str, Dict]) -> Dict[str, Dict[str, List[int]]]:
    """Same derivation already used in jyotish/engine_io.py's
    `_build_kp_significators` -- duplicated here (not imported) to avoid a
    circular import (engine_io imports this module, not the reverse)."""
    significators: Dict[str, Dict[str, List[int]]] = {}

    def _ensure(planet: str) -> Dict[str, List[int]]:
        if planet not in significators:
            significators[planet] = {"level_1": [], "level_2": [], "level_3": [], "level_4": []}
        return significators[planet]

    for planet, house in (planet_house or {}).items():
        if planet and house:
            _ensure(planet)["level_1"].append(int(house))

    for cusp_key, cusp in (kp_cusps or {}).items():
        if not isinstance(cusp, dict):
            continue
        try:
            house_num = int(cusp_key[1:]) if cusp_key.startswith("H") else int(cusp_key)
        except (TypeError, ValueError):
            continue
        for key, level in (("sign_lord", "level_1"), ("star_lord", "level_2"), ("sub_lord", "level_3"), ("sub_sub_lord", "level_4")):
            planet = cusp.get(key, "")
            if planet:
                _ensure(planet)[level].append(house_num)

    return {planet: levels for planet, levels in significators.items() if any(levels.values())}


# Fields the 9-step framework and this session's fixes (Amatyakaraka,
# Yogini Dasha, Vimshottari longevity, KP sub-field narrowing, Step 9
# convergence) actually read, with severity and plain-English impact if
# missing. `derivable` marks fields this module can attempt to fill.
FIELD_IMPACT: Dict[str, Dict[str, Any]] = {
    "lagna_sign":        {"severity": CRITICAL,  "impact": "Blocks nearly everything -- house lordships, D10/D9 cross-checks, Arudha, all Parashari signification.", "derivable": False},
    "lagna_lord":        {"severity": IMPORTANT, "impact": "Step 1 foundational read degrades; several bonus checks compare planets against lagna_lord directly.", "derivable": True},
    "house_lords":       {"severity": CRITICAL,  "impact": "Blocks Step 2 (2/6/7/9/10/11 house-lord scoring), Step 8 Dhana/Raja yoga detection, and the career-house-lordship affinity used by the Job_Career dasha-longevity filter.", "derivable": True},
    "planets_d1":        {"severity": CRITICAL,  "impact": "Blocks the whole D1 layer -- already hard-gated by jyotish.engine._validate_payload_schema, repeated here for visibility.", "derivable": False},
    "moon_nakshatra":     {"severity": IMPORTANT, "impact": "Blocks Yogini Dasha entirely (jyotish.dasha_longevity companion module) and the Step 1 Moon-nakshatra read.", "derivable": True},
    "moon_nakshatra_pada": {"severity": IMPORTANT, "impact": "Yogini Dasha's start-index calculation needs this; without it Yogini Dasha returns neutral for every field.", "derivable": False},
    "atmakaraka":         {"severity": IMPORTANT, "impact": "Blocks Jaimini Karakamsha/AK-based scoring (Step 5).", "derivable": True},
    "amatyakaraka":       {"severity": IMPORTANT, "impact": "Blocks the Amatyakaraka scoring wired into Job_Career/astro_enhancer.py this session (Step 5) -- AmK is 'often more precise than the 10th lord' per the framework.", "derivable": True},
    "karakamsha":         {"severity": OPTIONAL,  "impact": "Karakamsha-lagna bonus (G24) degrades to 0.", "derivable": False},
    "d10_lagna_sign":     {"severity": IMPORTANT, "impact": "Blocks D10/Dashamsha scoring (Step 4) -- this session raised D10's weight from 0.00, so a missing D10 here silently reverts that fix's benefit.", "derivable": False},
    "d10_house_lords":    {"severity": IMPORTANT, "impact": "Blocks D10 H10-lord and kendra/trikona checks (Step 4).", "derivable": False},
    "d10_house_occupancy": {"severity": IMPORTANT, "impact": "Blocks D10 occupancy scoring and this session's D10 kendra/trikona addition (Step 4).", "derivable": False},
    "kp_cusps":           {"severity": CRITICAL,  "impact": "Blocks the entire KP layer (Step 6) and the KP sub-field narrowing added this session -- already hard-gated by jyotish.engine._validate_payload_schema.", "derivable": False},
    "kp_significators":   {"severity": CRITICAL,  "impact": "Blocks KP significator-chain scoring -- already hard-gated by jyotish.engine._validate_payload_schema; this module can synthesize a fallback from planet_house + kp_cusps if both are present (same logic as engine_io.py's own fallback).", "derivable": True},
    "dasha_sequence":     {"severity": CRITICAL,  "impact": "Blocks the Vimshottari longevity filter (jyotish.dasha_longevity, Step 7) entirely -- it returns neutral 1.0x for every field with no dasha data. Already hard-gated by jyotish.engine._validate_payload_schema.", "derivable": False},
    "current_age":        {"severity": IMPORTANT, "impact": "Blocks career-phase resolution and the dasha-longevity filter's 'as-of' point; without it the longevity filter can't find the active dasha period.", "derivable": True},
    "dob":                {"severity": IMPORTANT, "impact": "Blocks age calculation and any dasha-calendar work downstream.", "derivable": False},
    "retrograde_planets": {"severity": OPTIONAL,  "impact": "Retrograde caution flags (G2) and Ashtottari applicability check degrade silently.", "derivable": False},
    "eff_strengths":      {"severity": IMPORTANT, "impact": "Blocks Shadbala-derived strength ranking (Step 8) and the AK/AmK approximate-derivation fallback in this module.", "derivable": False},
    "yogas_present":      {"severity": IMPORTANT, "impact": "Blocks all yoga-based bonuses (Neecha-Bhanga, Viparita Raja Yoga, and the Dhana Yoga detector added this session, Step 8).", "derivable": False},
    "varga_dignities":    {"severity": OPTIONAL,  "impact": "Dignity bonuses across D10/D9/D24 checks degrade to neutral.", "derivable": False},
}


def audit_and_fill_payload(payload: Any) -> Dict[str, Any]:
    """Audit `payload` (a constructed NatalPayloadV2) for gaps against
    FIELD_IMPACT, filling in the conservative, safely-derivable subset in
    place, and returning a structured report. Does not raise -- flags gaps,
    it doesn't block ingestion (jyotish.engine._validate_payload_schema
    remains the hard gate for the four truly-mandatory fields).
    """
    missing_critical: List[Dict[str, Any]] = []
    missing_important: List[Dict[str, Any]] = []
    missing_optional: List[Dict[str, Any]] = []
    derived_fields: Dict[str, Any] = {}

    def _record_missing(field: str, spec: Dict[str, Any]) -> None:
        entry = {"field": field, "severity": spec["severity"], "impact": spec["impact"]}
        if spec["severity"] == CRITICAL:
            missing_critical.append(entry)
        elif spec["severity"] == IMPORTANT:
            missing_important.append(entry)
        else:
            missing_optional.append(entry)

    for field, spec in FIELD_IMPACT.items():
        current_value = getattr(payload, field, None)
        if not _is_empty(current_value):
            continue  # present, nothing to do

        derived_value = None
        derivation_note = ""

        if field == "lagna_lord":
            lagna_sign = getattr(payload, "lagna_sign", "") or ""
            if lagna_sign:
                derived_value = _SIGN_LORD.get(lagna_sign, "")
                derivation_note = f"Looked up from lagna_sign ({lagna_sign}) via standard sign-lord table."

        elif field == "house_lords":
            lagna_sign = getattr(payload, "lagna_sign", "") or ""
            if lagna_sign:
                derived_value = _derive_house_lords(lagna_sign)
                derivation_note = f"Full 12-house whole-sign lordship map derived from lagna_sign ({lagna_sign})."

        elif field == "moon_nakshatra":
            planet_longitudes = getattr(payload, "planet_longitudes", {}) or {}
            moon_lon = planet_longitudes.get("Moon")
            if moon_lon is not None:
                derived_value = _derive_moon_nakshatra(moon_lon)
                derivation_note = f"Derived from planet_longitudes['Moon'] ({moon_lon}) via 13°20' nakshatra spans."

        elif field == "atmakaraka":
            eff = getattr(payload, "eff_strengths", {}) or {}
            if eff:
                derived_value = _derive_karaka_by_strength(eff, rank=1)
                derivation_note = "APPROXIMATE: highest-Shadbala planet used as an Atmakaraka proxy (not the classical degree-based rule) — treat as low-confidence."

        elif field == "amatyakaraka":
            eff = getattr(payload, "eff_strengths", {}) or {}
            if eff:
                derived_value = _derive_karaka_by_strength(eff, rank=2)
                derivation_note = "APPROXIMATE: 2nd-highest-Shadbala planet used as an Amatyakaraka proxy (not the classical degree-based rule) — treat as low-confidence."

        elif field == "current_age":
            dob_val = getattr(payload, "dob", "") or ""
            recomputed = _derive_current_age(dob_val)
            if recomputed is not None:
                derived_value = recomputed
                derivation_note = f"APPROXIMATE: recomputed from dob ({dob_val}) against today's date, not the chart's original current_date context."

        elif field == "kp_significators":
            planet_house = getattr(payload, "planet_house", {}) or {}
            kp_cusps = getattr(payload, "kp_cusps", {}) or {}
            if planet_house and kp_cusps:
                derived_value = _build_kp_significators_fallback(planet_house, kp_cusps)
                derivation_note = "Synthesized from planet_house + kp_cusps lordships (same fallback logic as engine_io.py's own KP-significator synthesizer)."

        if derived_value not in (None, "", {}, []):
            try:
                setattr(payload, field, derived_value)
                derived_fields[field] = {"value_summary": str(derived_value)[:200], "note": derivation_note}
            except Exception:
                # Pydantic validation on the derived value failed (e.g. wrong
                # type) -- treat as still-missing rather than crash ingestion.
                _record_missing(field, spec)
        else:
            _record_missing(field, spec)

    report = {
        "is_complete": not missing_critical and not missing_important,
        "missing_critical": missing_critical,
        "missing_important": missing_important,
        "missing_optional": missing_optional,
        "derived_fields": derived_fields,
        "summary": (
            f"{len(missing_critical)} critical, {len(missing_important)} important, "
            f"{len(missing_optional)} optional field(s) missing; "
            f"{len(derived_fields)} field(s) auto-derived from other present data."
        ),
    }

    # extra='allow' on NatalPayloadV2 means this is safe to attach even
    # though gap_audit_report isn't a formally declared schema field.
    try:
        setattr(payload, "gap_audit_report", report)
    except Exception:
        pass

    return report
