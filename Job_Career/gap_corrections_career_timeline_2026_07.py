"""JyotishAI — 2026-07 career-timeline gap corrections (6-item audit).

Companion to jyotish/gap_corrections_2026_07.py (which fixes the EDUCATION
field-determination engine). This module fixes six separate, user-reported
gaps in the CAREER TIMELINE report (career_timeline_*.html), and follows the
same house style: bounded, defensively-wrapped, extensively-commented
functions that are called INTO the existing report/scoring pipeline rather
than replacing it, so nothing here can silently regress the locked
regression suite (tests/test_regression_locked.py,
tests/test_career_track_regressions.py).

The six gaps and where each is wired in:

  GAP 1 — Jupiter/Sun event label too optimistic.
    `jupiter_sun_event_caveat()` — called from web_report.py's per-year card
    builder (_build_career_roadmap_html) to append a caveat sentence
    whenever the running MD/AD pair is literally Jupiter/Sun and the
    resolved event_type is a leadership/authority-flavored one.

  GAP 2 — KP override: weak promotion houses + strong foreign/leadership
    houses should not resolve to "Promotion".
    `kp_promotion_override()` — called from timeline.py._classify_event()
    immediately before it returns "PROMOTION", using the SAME KP cusp-chain
    data timeline.py already threads through (no new astrological input).

  GAP 3 — D10 manifestation explanation (not just a score).
    `d10_manifestation_text()` — pure function of already-computed D10 facts
    (d10_h10_lord, d10_h10_lord_house, d10_lagna_sign, d10_h12_stellium);
    wired into web_report.py alongside (not replacing) the existing
    `_d10_manifest` score-derived sentence.

  GAP 4 — Jupiter/Rahu AD truncation + narrative sub-phase breakdown.
    `split_antardasha_subphases()` — a pure display-layer function that
    slices one already-computed AD block's [start_date, end_date] range
    into narrative sub-phases for rendering; does not touch the underlying
    dasha date math (see the module docstring section "GAP 4 root-cause
    finding" below for the honest account of what was and was not fixed in
    the actual date computation).

  GAP 5 — "Title vs. influence" outcome-strength table.
    `OUTCOME_STRENGTH_TABLE` (module-level constant) + `outcome_strength_table_html()`
    — a generic, reusable report section (not literally hardcoded to one
    chart), rendered once near the top of the report.

  GAP 6 — Overconfident retro-calibration confidence label.
    `retro_confidence_label()` — reads the SAME `retro_matches` int and
    `confidence` dict timeline.py/timeline_inputs.py already compute; caps
    the shown label at "Medium-High" unless genuinely 5+ matches are present,
    and always attaches the required validation-coverage caveat sentence.

GAP 4 root-cause finding (honest account):
    The user-supplied audit states the Jupiter-MD Rahu-AD sub-period "should"
    run through 2031-10-14. Tracing the actual date math (jyotish/timeline.py
    `_expand_antardashas` / jyotish/engine_io.py `_build_dasha_from_json`)
    shows both paths derive AD dates from the chart JSON's own `age_start` /
    `age_end` fields, which are supplied ALREADY ROUNDED to 1 decimal place
    (e.g. Jupiter MD: age_start=37.4, age_end=53.4) even though the SAME JSON
    entries carry a more precise `start_year` / `end_year` pair (e.g.
    2015.74 / 2031.74, i.e. 2 decimal places of year-fraction). Using the
    coarser, rounded age field instead of the more precise year field is a
    real, provable precision bug — it discards information the source data
    already provides and compounds date-drift across 8-9 antardashas inside
    one Mahadasha. That precision bug is fixed here (see
    `precise_md_bounds()`), preferring `start_year`/`end_year` when present.
    However, recomputing with the more precise fields moves the computed
    Jupiter-MD end date only to within a few days of 2031-10-01 (not
    2031-10-14) — this implementation could NOT mechanically reproduce
    2031-10-14 as "the" correct end date from the data actually available in
    Charts/lakshman_chart_details.json, and no higher-precision source (e.g.
    a raw Julian-day dasha table) exists anywhere in this repo. The 3
    sub-phase narrative labels the audit requested are implemented as a
    display-layer breakdown of whatever the (corrected) Jupiter-Rahu AD
    range actually is, proportioned across the requested 3 fixed calendar
    sub-ranges — this is honest about not asserting a specific unverifiable
    end date while still delivering the requested reporting behavior.
"""
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime

# ─────────────────────────────────────────────────────────────────────────
# GAP 1 — Jupiter/Sun event label caveat
# ─────────────────────────────────────────────────────────────────────────
# Exact text requested by the audit. Kept as a single constant (not
# assembled piecemeal) so the wording is byte-for-byte auditable and cannot
# silently drift if this module is edited later.
#
# GAP 2 fix (2026-07-07 follow-up audit, user-reported): a chart's
# LLM-generated per-year narrative text (non-deterministic, produced
# elsewhere in the pipeline, not by this module) was observed to say
# something like "...this is more consistent with promotion than general
# expansion" for a Jupiter/Sun period whose final_event_type was correctly
# resolved to LEADERSHIP_EXPANSION — directly contradicting that resolved
# label. This module's caveat sentence is the one DETERMINISTIC, always-
# appended sentence for Jupiter/Sun periods (see jupiter_sun_event_caveat()
# below), so it is strengthened here to explicitly state the correct
# reading and supersede any contradictory LLM narrative phrasing a reader
# might see elsewhere on the same card.
_JUPITER_SUN_CAVEAT = (
    "Jupiter/Sun = Authority Visibility + Mandate Expansion; promotion "
    "possible only if organizational cycle supports it. For a senior "
    "software manager, this is more consistent with authority visibility, "
    "mandate expansion, executive trust and promotion runway than "
    "guaranteed HR/title promotion."
)

# Event types this caveat applies to. Scoped to the leadership/authority
# family the audit's example ("Leadership Expansion") belongs to — NOT
# applied to unrelated event types (e.g. JOB_CHANGE, RISK_PERIOD) that a
# Jupiter/Sun period could in principle also resolve to, since the caveat's
# wording ("promotion possible only if...") is specific to authority/
# leadership-flavored outcomes.
_JUPITER_SUN_CAVEAT_EVENTS = {
    "LEADERSHIP_EXPANSION", "PROMOTION", "BREAKTHROUGH", "AUTHORITY_SHIFT",
    "FORECAST_LEADERSHIP_EXPANSION", "FORECAST_PROMOTION",
}


def jupiter_sun_event_caveat(md_lord: str, ad_lord: str, event_type: str) -> str:
    """Return the GAP-1 caveat sentence when this block is a Jupiter/Sun
    period resolving to a leadership/authority-flavored event; "" otherwise.

    Bounded/scoped: only ever returns this one fixed sentence, only for the
    exact planet pair + event-type family the audit specified. Does not
    change `event_type` itself or any score — display-layer only, exactly
    like the existing `_tl_display_event_type` override pattern already used
    in web_report.py for "Promotion Runway + Executive Visibility".
    """
    try:
        _md = str(md_lord or "").strip().title()
        _ad = str(ad_lord or "").strip().title()
        _et = str(event_type or "").upper().replace(" ", "_")
        if _md == "Jupiter" and _ad == "Sun" and _et in _JUPITER_SUN_CAVEAT_EVENTS:
            return _JUPITER_SUN_CAVEAT
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────────────────
# GAP 2 — KP override: weak promotion houses, strong foreign/leadership
# houses -> do not label the event "Promotion".
# ─────────────────────────────────────────────────────────────────────────
# House groups per the audit's own spec. Promotion significators (KP):
# 2 (income/status), 6 (service/competition), 10 (career/authority),
# 11 (gains/elevation) — this matches _KP_EVENT_HOUSE_RULES["Promotion"]
# already defined in jyotish/astrology_explainer.py, confirmed by re-reading
# that module before writing this override (no invented house set).
_KP_PROMOTION_HOUSES = ("2", "6", "10", "11")
# Foreign-travel / job-change significators per the audit: 12 (foreign
# residence/expenditure), 3 (short travel/change of role), 9 (long
# journeys/fortune) — matches _KP_EVENT_HOUSE_RULES["Foreign"]/["Job Change"].
_KP_FOREIGN_JOBCHANGE_HOUSES = ("12", "3", "9")
# Leadership significators per the audit: 10 (authority), 1 (self/identity)
# — matches _KP_EVENT_HOUSE_RULES["Leadership"] minus 5/11 (already covered
# by the promotion group above, so not double-counted here).
_KP_LEADERSHIP_HOUSES = ("10", "1")

_WEAK_HOUSE_RATIO = 0.34   # < ~1/3 of evaluated houses tied to MD/AD lord => "weak"
_STRONG_HOUSE_RATIO = 0.5  # >= 1/2 of evaluated houses tied to MD/AD lord => "strong"


def _house_group_ratio(kp_house_chain: Dict[str, Any], houses: Tuple[str, ...],
                        lords: set) -> Optional[float]:
    """Fraction of `houses` (that actually have KP cusp data) whose
    sign/star/sub/sub-sub lord chain contains one of `lords` (the running
    MD/AD lord). Returns None if none of the houses have data at all (so
    the caller can distinguish "genuinely weak" from "no data available",
    and skip the override rather than fabricate a verdict from nothing —
    same conservative convention as _kp_event_verdicts() in
    astrology_explainer.py, which this function deliberately mirrors."""
    if not kp_house_chain or not lords:
        return None
    evaluated = 0
    hits = 0
    for h in houses:
        cusp = kp_house_chain.get(f"H{h}")
        if not cusp:
            continue
        evaluated += 1
        chain_lords = {cusp.get("sign_lord"), cusp.get("star_lord"),
                       cusp.get("sub_lord"), cusp.get("sub_sub_lord")}
        if chain_lords & lords:
            hits += 1
    if evaluated == 0:
        return None
    return hits / evaluated


def kp_promotion_override(kp_house_chain: Dict[str, Any], md_lord: str, ad_lord: str) -> Optional[str]:
    """GAP 2: if promotion houses (2/6/10/11) are weak AND EITHER the
    foreign/job-change group (12/3/9) OR the leadership group (10/1) is
    strong, return the override label string; otherwise return None (caller
    keeps whatever event_type it already resolved).

    Conservative by construction: returns None (no override) whenever the
    KP cusp chain doesn't have enough data to evaluate either side — this
    function should never MANUFACTURE a verdict from missing data, matching
    the same convention already used by _kp_event_verdicts() in
    astrology_explainer.py (evaluated == 0 => skip, don't guess).
    """
    try:
        _decision = kp_promotion_override_decision(kp_house_chain, md_lord, ad_lord)
        if _decision.get("applied"):
            return "Role expansion / global mandate / external opportunity / leadership visibility"
    except Exception:
        pass
    return None


# 2026-07-07 follow-up audit — GAP 3: make the KP override an explicit,
# structured deterministic decision (kp_override_applied: bool,
# kp_override_reason: str, plus which target label was chosen) rather than
# only a narrative string, so the caller can set real fields on the block
# instead of inferring "did an override happen?" from string presence.
_KP_OVERRIDE_TARGET_BY_HOUSE_PATTERN: Dict[str, str] = {
    # Keyed by which group(s) were strong -> which specific override label
    # fits best, per the audit's own house-pattern guidance. Configurable:
    # a caller with a different house emphasis can extend/override this
    # mapping without touching the decision logic itself.
    "foreign":           "GLOBAL_MANDATE",
    "leadership":        "AUTHORITY_SHIFT",
    "foreign+leadership": "LEADERSHIP_EXPANSION",
}


def kp_promotion_override_decision(kp_house_chain: Dict[str, Any], md_lord: str, ad_lord: str) -> Dict[str, Any]:
    """GAP 3 (2026-07-07 follow-up audit): explicit, structured version of
    the KP-override rule.

    Rule (deterministic, house-strength-based, using the SAME KP cusp-chain
    data already threaded through timeline.py — no new astrological input):
      - IF the KP promotion/income significator group (houses 2/6/10/11,
        `_KP_PROMOTION_HOUSES`) is WEAK for the running MD/AD lord
        (ratio <= _WEAK_HOUSE_RATIO)
      - AND EITHER the foreign/job-change group (12/3/9) OR the leadership
        group (10/1) is STRONG (ratio >= _STRONG_HOUSE_RATIO)
      - THEN downgrade any candidate "PROMOTION" event_type to one of
        LEADERSHIP_EXPANSION / GLOBAL_MANDATE / AUTHORITY_SHIFT, picked by
        which house group(s) were strong (both -> LEADERSHIP_EXPANSION, the
        broadest/most conservative label; foreign-only -> GLOBAL_MANDATE;
        leadership-only -> AUTHORITY_SHIFT). This mapping is itself
        overridable via _KP_OVERRIDE_TARGET_BY_HOUSE_PATTERN above.

    Returns a dict always containing:
      {"applied": bool, "reason": str, "target_event_type": str,
       "promo_ratio": float|None, "foreign_ratio": float|None,
       "leadership_ratio": float|None}
    so the caller can set kp_override_applied / kp_override_reason directly
    on the block, and log/inspect the underlying ratios if needed.

    Conservative by construction (mirrors kp_promotion_override() above):
    "applied" is only ever True when both sides of the rule are actually
    evaluable from real KP cusp data — missing data always yields
    applied=False with a reason explaining why, never a manufactured verdict.
    """
    _out = {
        "applied": False, "reason": "", "target_event_type": "",
        "promo_ratio": None, "foreign_ratio": None, "leadership_ratio": None,
    }
    try:
        lords = {l for l in (md_lord, ad_lord) if l}
        if not lords or not kp_house_chain:
            _out["reason"] = "No KP house-cusp chain or dasha lords available — override not evaluable."
            return _out

        promo_ratio = _house_group_ratio(kp_house_chain, _KP_PROMOTION_HOUSES, lords)
        _out["promo_ratio"] = promo_ratio
        if promo_ratio is None:
            _out["reason"] = "KP promotion houses (2/6/10/11) have no cusp data for this chart — override skipped."
            return _out
        if promo_ratio > _WEAK_HOUSE_RATIO:
            _out["reason"] = (
                f"KP promotion houses (2/6/10/11) are not weak "
                f"(ratio {promo_ratio:.2f} > {_WEAK_HOUSE_RATIO}) — override not needed."
            )
            return _out

        foreign_ratio = _house_group_ratio(kp_house_chain, _KP_FOREIGN_JOBCHANGE_HOUSES, lords)
        leadership_ratio = _house_group_ratio(kp_house_chain, _KP_LEADERSHIP_HOUSES, lords)
        _out["foreign_ratio"] = foreign_ratio
        _out["leadership_ratio"] = leadership_ratio

        foreign_strong = foreign_ratio is not None and foreign_ratio >= _STRONG_HOUSE_RATIO
        leadership_strong = leadership_ratio is not None and leadership_ratio >= _STRONG_HOUSE_RATIO

        if not (foreign_strong or leadership_strong):
            _out["reason"] = (
                f"KP promotion houses weak (ratio {promo_ratio:.2f}) but neither foreign/job-change "
                f"(12/3/9) nor leadership (10/1) houses are strong enough — override not applied."
            )
            return _out

        if foreign_strong and leadership_strong:
            _pattern = "foreign+leadership"
        elif foreign_strong:
            _pattern = "foreign"
        else:
            _pattern = "leadership"
        _target = _KP_OVERRIDE_TARGET_BY_HOUSE_PATTERN.get(_pattern, "LEADERSHIP_EXPANSION")

        _out["applied"] = True
        _out["target_event_type"] = _target
        _out["reason"] = (
            f"KP promotion houses (2/6/10/11) weak for {'/'.join(sorted(lords))} "
            f"(ratio {promo_ratio:.2f} <= {_WEAK_HOUSE_RATIO}) while "
            + ("foreign/job-change (12/3/9)" if foreign_strong else "")
            + (" and " if foreign_strong and leadership_strong else "")
            + ("leadership (10/1)" if leadership_strong else "")
            + f" houses are strong — downgraded candidate PROMOTION to {_target}."
        )
        return _out
    except Exception as _exc:
        _out["reason"] = f"KP override evaluation failed ({_exc}) — no override applied."
        return _out


# ─────────────────────────────────────────────────────────────────────────
# GAP 3 — D10 manifestation explanation
# ─────────────────────────────────────────────────────────────────────────
_D10_H12_TEXT = "global/MNC/back-office/invisible ownership"
_D10_VIRGO_10TH_TEXT = "systems, delivery excellence, architecture, analytics"
_D10_MERCURY_H12_TEXT = "recognition through behind-the-scenes technical responsibility"


def d10_manifestation_text(d10_h10_lord: str = "", d10_h10_lord_house: int = 0,
                            d10_lagna_sign: str = "", d10_10th_sign: str = "",
                            d10_h12_stellium: bool = False) -> List[str]:
    """GAP 3: return a list of plain-English sentences explaining HOW a
    career event manifests structurally, based on already-computed D10
    facts — never a new score, purely explanatory text layered ALONGSIDE
    the existing numeric D10 alignment/structural scores (timeline.py's
    `d10_structural_score`, `d10_alignment`) which this function does not
    touch or replace.

    Each rule below is independent and additive (a chart can match more
    than one), mirroring the audit's own three example rules:
      1. D10 10th-lord (or any tracked planet) placed in the D10 12th house
         -> "global/MNC/back-office/invisible ownership" reading.
      2. D10 10th house sign = Virgo -> "systems, delivery excellence,
         architecture, analytics" reading.
      3. D10 10th-lord = Mercury AND Mercury itself placed in the D10 12th
         house -> the more specific "recognition through behind-the-scenes
         technical responsibility" reading (supersedes/adds to rule 1's
         more generic 12th-house reading for this specific combination).
    """
    out: List[str] = []
    try:
        _h10_lord = str(d10_h10_lord or "").strip()
        _h10_house = int(d10_h10_lord_house or 0)
        _tenth_sign = str(d10_10th_sign or "").strip()
        _lagna_sign = str(d10_lagna_sign or "").strip()

        # Rule 3 (most specific) checked first so its more precise wording
        # is not diluted/duplicated by the generic Rule 1 sentence below.
        _rule3_hit = (_h10_lord == "Mercury" and _h10_house == 12)
        if _rule3_hit:
            out.append(
                "D10 10th-lord (Mercury) is placed in the D10 12th house: " + _D10_MERCURY_H12_TEXT + "."
            )
        elif _h10_house == 12 and _h10_lord:
            out.append(
                f"D10 10th-lord ({_h10_lord}) is placed in the D10 12th house: " + _D10_H12_TEXT + "."
            )
        elif d10_h12_stellium:
            # Stellium (3+ planets) in D10 12th house without necessarily
            # being the 10th lord itself — still a genuine 12th-house-heavy
            # D10 signature, worth the same generic reading (audit's rule 1
            # is about "D10 planet/lord in 12th house" broadly).
            out.append(
                "Multiple D10 planets (stellium) occupy the D10 12th house: " + _D10_H12_TEXT + "."
            )

        _effective_10th_sign = _tenth_sign or _lagna_sign
        if _effective_10th_sign == "Virgo":
            out.append(
                "D10 10th house sign is Virgo: career manifests through " + _D10_VIRGO_10TH_TEXT + "."
            )
    except Exception:
        pass
    return out


# ─────────────────────────────────────────────────────────────────────────
# GAP 6 (2026-07-07 follow-up audit) — D10 sub-dimension scores
# ─────────────────────────────────────────────────────────────────────────
# The flat d10_alignment/d10_full_score fields can legitimately compute to
# 0.0 for a period whose MD/AD lord doesn't itself occupy a D10 career
# house — but that flat number discards the SAME underlying D10 facts
# already used for the narrative text in d10_manifestation_text() above
# (12th-house occupancy/stellium, 10th-lord placement, 10th house sign).
# These 4 sub-dimension scores expose those facts as separate, bounded
# [0,1] numbers with fixed, documented weightings — additive fields, kept
# alongside (never replacing) d10_alignment/d10_full_score for backward
# compatibility with any existing test/consumer of those flat fields.
#
# Weighting rationale (fixed, chart-agnostic, applied consistently):
#   d10_title_support              — LOW baseline (~0.20): a 12th-house-
#     heavy D10 signature (back-office/global/invisible-ownership) is
#     classically a WEAK indicator of a clean formal TITLE change; it's
#     bumped only slightly by favorable 10th-lord dignity.
#   d10_global_delivery_support     — HIGH baseline (~0.85) for the same
#     12th-house-heavy signature: that is precisely the classical D10
#     signature for global/MNC/cross-border delivery responsibility.
#   d10_invisible_authority_support — HIGH baseline (~0.80): 12th-house
#     placement + Virgo-type systems/analytics themes read as authority
#     that operates behind the scenes rather than via a public title.
#   d10_clean_promotion_support     — LOW-MEDIUM baseline (~0.25): a
#     "clean" promotion (title + visible authority together) needs the
#     10th lord to be OUT of the 12th house and well-dignified; scores
#     higher only when neither the 12th-house nor stellium signature is
#     present and the 10th lord's dignity is favorable.
_D10_SUBSCORE_BASE = {
    "d10_title_support":              0.20,
    "d10_global_delivery_support":     0.85,
    "d10_invisible_authority_support": 0.80,
    "d10_clean_promotion_support":     0.25,
}


def d10_subdimension_scores(d10_h10_lord: str = "", d10_h10_lord_house: int = 0,
                              d10_h10_lord_dignity: str = "", d10_lagna_sign: str = "",
                              d10_10th_sign: str = "", d10_h12_stellium: bool = False) -> Dict[str, float]:
    """GAP 6: derive 4 bounded [0,1] D10 sub-dimension scores from the SAME
    already-computed D10 facts used by d10_manifestation_text() — no new
    astrological input, purely a re-expression of existing facts as
    separate numeric dimensions instead of one flattened scalar.

    Returns a dict with exactly the 4 keys documented in
    _D10_SUBSCORE_BASE above, each rounded to 3 decimals.
    """
    try:
        _h12_signature = bool(d10_h10_lord_house == 12) or bool(d10_h12_stellium)
        _dig = str(d10_h10_lord_dignity or "").upper()
        _dignity_bonus = {"EXALTED": 0.15, "OWN": 0.10, "DEBILITATED": -0.10}.get(_dig, 0.0)
        _virgo_theme = str(d10_10th_sign or d10_lagna_sign or "").strip() == "Virgo"

        _title = _D10_SUBSCORE_BASE["d10_title_support"]
        _global = _D10_SUBSCORE_BASE["d10_global_delivery_support"]
        _invisible = _D10_SUBSCORE_BASE["d10_invisible_authority_support"]
        _clean = _D10_SUBSCORE_BASE["d10_clean_promotion_support"]

        if _h12_signature:
            # 12th-house/back-office pattern present: reinforces global-
            # delivery + invisible-authority readings, further weakens the
            # clean-title-promotion reading (title support gets a small
            # dignity-linked bump only, since a well-dignified 10th lord in
            # the 12th can still occasionally surface as a formal title).
            _title = max(0.0, min(1.0, _title + max(0.0, _dignity_bonus) * 0.5))
            _global = max(0.0, min(1.0, _global + 0.05))
            _invisible = max(0.0, min(1.0, _invisible + 0.05))
            _clean = max(0.0, min(1.0, _clean - 0.05))
        else:
            # No 12th-house/back-office signature: the D10 10th lord is
            # more visibly placed, so the clean-promotion reading improves
            # (scaled by dignity) and the invisible-authority reading eases
            # back toward its own baseline-minus-offset.
            _clean = max(0.0, min(1.0, _clean + 0.30 + _dignity_bonus))
            _title = max(0.0, min(1.0, _title + 0.20 + _dignity_bonus))
            _invisible = max(0.0, min(1.0, _invisible - 0.25))
            _global = max(0.0, min(1.0, _global - 0.20))

        if _virgo_theme:
            # Virgo 10th/lagna theme (systems/analytics/delivery-excellence)
            # further reinforces global-delivery support specifically.
            _global = max(0.0, min(1.0, _global + 0.05))

        return {
            "d10_title_support":              round(_title, 3),
            "d10_global_delivery_support":     round(_global, 3),
            "d10_invisible_authority_support": round(_invisible, 3),
            "d10_clean_promotion_support":     round(_clean, 3),
        }
    except Exception:
        return dict(_D10_SUBSCORE_BASE)


# ─────────────────────────────────────────────────────────────────────────
# GAP 4 — Jupiter/Rahu AD precision fix + narrative sub-phase breakdown
# ─────────────────────────────────────────────────────────────────────────

def precise_md_bounds(md_entry: Dict[str, Any], dob: date) -> Optional[Tuple[date, date]]:
    """GAP 4 (real bug fix): given one raw vimshottari_dasha_sequence MD
    entry from the chart JSON, compute (start_date, end_date) preferring
    the more precise `start_year`/`end_year` fields over the coarser
    `age_start`/`age_end` fields (rounded to 1 decimal in the source data).

    Root-cause note: jyotish/timeline.py's `_dasha_calendar` and
    jyotish/engine_io.py's `_build_dasha_from_json` both currently derive
    dates ONLY from age_start/age_end. Where start_year/end_year are also
    present (as they are for Charts/lakshman_chart_details.json), they
    carry 2 decimal places of year-fraction precision vs. age's 1 decimal
    place — using the coarser field discards real precision the source
    data already has. This function is a bounded, additive precision
    improvement: it does NOT change which fields are read when start_year/
    end_year are absent (falls back to age_start/age_end unchanged), so it
    cannot regress any chart whose JSON lacks these fields.

    Returns None if neither precise nor coarse fields are usable.
    """
    try:
        start_year = md_entry.get("start_year")
        end_year = md_entry.get("end_year")
        if start_year is not None and end_year is not None:
            # Derive the native's own birth fractional-year from dob so the
            # start_year/end_year (absolute calendar years) can be converted
            # into a day-count offset from dob consistently with how
            # age_start/age_end are already interpreted elsewhere (365.25
            # days/year approximation — matches _age_to_date's own
            # convention so the two paths stay mutually consistent).
            dob_frac_year = dob.year + (dob.timetuple().tm_yday - 1) / 365.25
            start_age = float(start_year) - dob_frac_year
            end_age = float(end_year) - dob_frac_year
            from dateutil.relativedelta import relativedelta
            from datetime import timedelta as _td

            def _age_to_dt(age: float) -> date:
                whole = int(age)
                frac = age - whole
                days = round(frac * 365.25)
                return dob + relativedelta(years=whole) + _td(days=days)

            return (_age_to_dt(start_age), _age_to_dt(end_age))
    except Exception:
        pass
    return None


# 2026-07-07 follow-up audit fix: the ORIGINAL 3 fixed calendar-anchor
# sub-phases below are superseded by the real, already-computed
# Pratyantardasha (PD) chain (see jyotish/timeline.py::_expand_pratyantardashas,
# wired onto every AD block as block["pratyantardashas"]) — that PD chain
# already has 8-9 genuine sub-windows with day-precision boundaries for the
# Jupiter-MD Rahu-AD period, which is strictly more accurate than 3
# hardcoded coarse buckets. Kept only as a fallback for charts/blocks where
# no real `pratyantardashas` list is available (defensive, not the primary
# path any more).
_JUPITER_RAHU_SUBPHASES: List[Tuple[str, str, str]] = [
    ("2029-05", "2029-12", "Entry disruption / new direction"),
    ("2030-01", "2030-12", "Global/technology transformation"),
    ("2031-01", "2031-10", "Closure before Saturn MD"),
]

# Narrative label keyed by PD lord, per the user's detailed Jupiter/Rahu
# sub-window breakdown (7 named windows out of the 9 real PDs — the
# remaining 1-2 PDs, e.g. Rahu's own PD at the very start and Ketu's PD in
# the 2030 Sep-Nov gap, render with a generic fallback label rather than
# invented narrative content, since the user explicitly said not to
# fabricate detail for those gaps).
_JUPITER_RAHU_PD_LABELS: Dict[str, str] = {
    "Rahu":    "Disruption, foreign/global trigger, new mandate seed",
    "Jupiter": "Expansion, advisory/growth opportunity",
    "Saturn":  "Responsibility, structural pressure",
    "Mercury": "Technology, architecture, communication, role redesign",
    "Venus":   "Network, comfort, global collaboration, benefits",
    "Sun":     "Authority/visibility peak",
    "Mars":    "Decisive action before Saturn MD",
    "Moon":    "Emotional/domestic recalibration alongside the professional shift",
    "Ketu":    "Quiet transition / release before the next PD",
}


def split_antardasha_subphases(md_lord: str, ad_lord: str, start_date: str, end_date: str,
                                 pratyantardashas: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
    """GAP 1 (2026-07-07 follow-up audit): return the narrative sub-phase
    breakdown for a Jupiter-MD Rahu-AD block.

    Root-cause note: an earlier version of this function only ever produced
    3 coarse, hardcoded calendar-anchor buckets (see _JUPITER_RAHU_SUBPHASES
    above), which is what earlier reports rendered as "2029 May-Dec / 2030 /
    2031 Jan-Oct" — narrower and less precise than the real dasha data. The
    REAL pratyantardasha chain for this exact AD (already computed by
    jyotish/timeline.py::_expand_pratyantardashas and threaded onto the
    block as `pratyantardashas`) has 9 genuine sub-windows with day-precision
    boundaries running the full 2029-05-04 to 2031-09-28 span. This function
    now uses that REAL PD list (when provided) as the primary source of
    sub-phase boundaries, labeling each PD window with the narrative theme
    for its PD lord — this is what produces the requested 7-8 sub-window
    breakdown instead of 3 coarse buckets, and what makes the LAST sub-
    window's end date the block's true end_date (2031-09-28), not a
    truncated 2030-06.

    Falls back to the old fixed 3-bucket behavior only if no real PD list
    is supplied (e.g. an older caller that hasn't been updated) — this
    preserves prior behavior for any caller not yet passing
    `pratyantardashas`.

    Returns [] for any other MD/AD pair (this breakdown's narrative labels
    are specific to the Jupiter/Rahu period the audit called out).
    """
    out: List[Dict[str, str]] = []
    try:
        if str(md_lord or "").strip().title() != "Jupiter" or str(ad_lord or "").strip().title() != "Rahu":
            return []

        if pratyantardashas:
            for _pd in pratyantardashas:
                _pd_lord = str(_pd.get("pd_lord") or _pd.get("planet") or "").strip().title()
                _pd_sd = _parse_ym_date(_pd.get("start_date", ""))
                _pd_ed = _parse_ym_date(_pd.get("end_date", ""), end_of_month=False)
                if not _pd_sd or not _pd_ed:
                    continue
                _label = _JUPITER_RAHU_PD_LABELS.get(_pd_lord, f"{_pd_lord} Pratyantardasha")
                out.append({
                    "start": _pd_sd.isoformat(),
                    "end": _pd_ed.isoformat(),
                    "label": f"{_pd_lord} PD — {_label}" if _pd_lord else _label,
                })
            if out:
                return out
            # fall through to legacy 3-bucket behavior if PD parsing failed

        # Legacy fallback: fixed 3-bucket breakdown, clipped to the block's
        # own actual [start_date, end_date].
        _sd = _parse_ym_date(start_date)
        _ed = _parse_ym_date(end_date, end_of_month=True)
        if not _sd or not _ed:
            return []
        for ph_start, ph_end, label in _JUPITER_RAHU_SUBPHASES:
            _ps = datetime.strptime(ph_start, "%Y-%m").date()
            _pe = datetime.strptime(ph_end, "%Y-%m").date()
            _clip_start = max(_ps, _sd)
            _clip_end = min(_pe, _ed)
            if _clip_start <= _clip_end:
                out.append({
                    "start": _clip_start.isoformat(),
                    "end": _clip_end.isoformat(),
                    "label": label,
                })
    except Exception:
        pass
    return out


def _parse_ym_date(d: Any, end_of_month: bool = False) -> Optional[date]:
    """Best-effort parse of a date-ish value. Handles both full ISO dates
    ("YYYY-MM-DD") and the truncated "YYYY-MM" month-strings this codebase
    also stores on career-timeline blocks (see timeline.py's month-level
    truncation) — without this,
    split_antardasha_subphases() silently failed to parse any block whose
    start_date/end_date arrived as "YYYY-MM" rather than a full date, which
    is the common case for top-level block dates in this report.
    """
    if isinstance(d, date):
        return d
    s = str(d or "").strip()
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    if len(s) == 7:
        try:
            _y, _m = (int(x) for x in s.split("-"))
            if end_of_month:
                _next_m = _m + 1
                _next_y = _y
                if _next_m > 12:
                    _next_m = 1
                    _next_y += 1
                from datetime import timedelta as _td_local
                return date(_next_y, _next_m, 1) - _td_local(days=1)
            return date(_y, _m, 1)
        except (ValueError, TypeError):
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────
# GAP 5 — "Title vs. influence" outcome-strength table
# ─────────────────────────────────────────────────────────────────────────
# Generic (chart-agnostic) reusable table, per the audit's own text.
# Kept as a fixed ordered list of (outcome, strength) tuples rather than a
# dict so row order in the rendered table exactly matches the audit's spec.
OUTCOME_STRENGTH_TABLE: List[Tuple[str, str]] = [
    ("Leadership scope", "High"),
    ("Global/MNC authority", "High"),
    ("Formal promotion", "Medium"),
    ("Income jump", "Medium-low unless KP 2/11 confirms"),
    ("Job change/external mandate", "Medium-high"),
    ("Job loss risk", "Low to moderate, mainly during Rahu/Mars/Saturn triggers"),
]

_STRENGTH_COLOR = {
    "high": "var(--green,#1E7B50)",
    "medium-high": "#3B82F6",
    "medium": "var(--amber,#B8720A)",
    "medium-low": "#B8720A",
    "low": "#94A3B8",
}


def _strength_color_for(strength_text: str) -> str:
    """Best-effort color lookup keyed on the leading word(s) of the
    strength text (handles compound values like 'Medium-low unless KP
    2/11 confirms' by matching the leading 'medium-low' token)."""
    key = strength_text.lower().split(" unless")[0].split(",")[0].strip()
    return _STRENGTH_COLOR.get(key, "#64748b")


def outcome_strength_table_html(rows: Optional[List[Tuple[str, str]]] = None) -> str:
    """GAP 5: render the Outcome / Strength table as its own report section.
    Generic by default (uses OUTCOME_STRENGTH_TABLE); callers may pass a
    chart-specific override list if a future chart genuinely needs a
    different table, but no chart-specific values are hardcoded here."""
    import html as _html
    esc = _html.escape
    rows = rows or OUTCOME_STRENGTH_TABLE
    body_rows = "".join(
        f'<tr><td>{esc(outcome)}</td>'
        f'<td style="color:{_strength_color_for(strength)};font-weight:600">{esc(strength)}</td></tr>'
        for outcome, strength in rows
    )
    return (
        '<div class="rmap-outcome-strength-section">'
        '<h3 class="rmap-year-subhead">Title vs. Influence — Outcome Strength</h3>'
        '<table class="rmap-outcome-table"><thead><tr><th>Outcome</th><th>Strength</th></tr></thead>'
        f'<tbody>{body_rows}</tbody></table>'
        '<p style="font-size:11.5px;color:#64748b;margin-top:6px">'
        'Distinguishes scope/influence gains (often the most likely outcome) from a formal '
        'title change (a narrower, less certain outcome) for this kind of period profile.</p>'
        '</div>'
    )


# ─────────────────────────────────────────────────────────────────────────
# GAP 6 — Overconfident retro-calibration confidence label
# ─────────────────────────────────────────────────────────────────────────
_MIN_MATCHES_FOR_HIGH = 5   # audit's own requested threshold (5-7 known events)
_MIN_MATCHES_FOR_MEDIUM_HIGH = 1

_VALIDATION_COVERAGE_NOTE = (
    "This chart has been validated against {n} known past career event(s) so far. "
    "Full \"High\" confidence requires validation against at least 5-7 known life "
    "events (joining dates, promotions, hikes, job changes, major role changes, "
    "foreign/client changes) — this chart is currently only partially validated."
)


def retro_confidence_label(confidence: Optional[Dict[str, Any]], retro_matches: int) -> Tuple[str, str]:
    """GAP 6: return (display_label, coverage_note) for the report's overall
    confidence banner.

    Bounded rule: even if the underlying `confidence` tier computation (or
    any upstream default) resolves to "High"/"STRONG", this function never
    lets the DISPLAYED label exceed "Medium-High" unless retro_matches is
    genuinely >= 5 (the audit's own stated bar for true "High" confidence).
    This is a presentation-layer cap only — it does not alter
    `compute_confidence_tier`'s own internal score/caveats, so any other
    consumer of the raw `confidence` dict (e.g. a JSON API response) is
    unaffected; only what a human reads in the HTML report is capped here.
    """
    try:
        n = int(retro_matches or 0)
    except (TypeError, ValueError):
        n = 0

    raw_label = ""
    if isinstance(confidence, dict):
        raw_label = str(confidence.get("label", "") or confidence.get("tier", "") or "")
    elif isinstance(confidence, str):
        raw_label = confidence

    if n >= _MIN_MATCHES_FOR_HIGH:
        # Genuinely well-validated — allow the underlying tier through
        # unmodified (still capped to whatever compute_confidence_tier
        # itself produced; this function does not manufacture "High" on
        # its own even at n>=5, it only stops SUPPRESSING it).
        label = raw_label or "High"
    elif n >= _MIN_MATCHES_FOR_MEDIUM_HIGH:
        label = "Medium-High"
    else:
        label = "Medium" if raw_label else "Medium (unvalidated)"

    note = _VALIDATION_COVERAGE_NOTE.format(n=n)
    return label, note
