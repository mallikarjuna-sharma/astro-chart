"""
Business_Prediction/business_engine.py
=======================================
Business/entrepreneurship prediction engine for JyotishAI.

MATURITY STATEMENT (read this before treating any output as authoritative):

    Architecturally mature and internally validated: implementation rules,
    invariants, regression behavior, and end-to-end execution are tested.
    Real-world predictive validity has NOT been established, because no
    prospective labeled outcome corpus has been evaluated. Astrological
    precedence and conflict resolution remain explicit engineered
    interpretations, not uniquely authoritative classical doctrine.

Concretely, keep these distinctions in mind whenever reading this module's
output or test suite:

  - Tests validate implementation -- not predictions. A green test suite
    proves the code executes its own intended rules; it does not prove
    those rules are astrologically complete or empirically accurate.
  - Synthetic data (Business_Prediction/synthetic_calibration_seed.py)
    validates the CALIBRATION PIPELINE -- not the model. It proves
    validate_outcomes()/score_calibration() work end-to-end on fabricated
    rows; it says nothing about this engine's real predictive accuracy.
  - Classical coverage does not imply classical consensus. Where this
    module cites a classical method (Phaladeepika ch.5, Viparita Raja
    Yoga, KP significators, Jaimini karakas), it implements ONE documented
    reading of that method, not the only one a traditional astrologer
    would accept, and it does not yet handle every rare yoga, cancellation
    condition, or conflicting-yoga interaction a full classical review
    would consider.
  - "Heuristic tier" (HIGH/MODERATE/LOW) is not statistical confidence.
    It is a deterministic threshold on two already-computed scores, not a
    measured probability or a claim backed by a labeled outcome corpus.
  - Outputs are decision-support narratives, not financial forecasts. They
    exist to prompt further astrological review and human judgment, not to
    be acted on as investment or career advice.

This module has NOT been empirically calibrated against dated business
outcomes (see CALIBRATION_STATUS / Business_Prediction/calibration.py).
Every score below is a rule-weighted, dignity-gated, multi-varga-
corroborated heuristic -- extensively tested for internal consistency, not
validated against real-world outcomes. See `model_status` /
`evidence_basis` / `calibration_status` / `maturity_statement` in every
returned dict for a machine-readable statement of these limits.

Mirrors the layered pipeline used across the engine (Stream_Determination /
Field_Determination / Job_Career): a shared NatalPayloadV2 chart object is
scored by domain-specific layers that reuse, wherever possible, primitives
that already exist elsewhere in the repo rather than re-deriving them:

  Layer 1 — Viability gate
      compute_business_mode_gate(payload) (this module) computes signed,
      dignity-gated, D9/D10-corroborated employment/business/independent/
      family_business scores -- the same evidence policy as Layer 2 below,
      not the older jyotish.employment_mode.compute_employment_mode(),
      which used several unconditional/ungated rules (Rahu-in-H7, DK in
      any kendra/trikona, independent Mercury+Venus placement, empty-H7 as
      positive evidence) and had no negative ledger or varga corroboration.
      Its business_score / independent_score / family_biz_score gate
      whether business-track analysis should be surfaced for this chart,
      and compute_business_prediction() additionally requires the
      venture-type score to beat employment_score by a minimum margin
      before "proceed" is set (comparative advantage, not just absolute
      viability).

  Layer 2 — House/planet business-strength significators
      Business-specific (H2/H3/H6/H7/H9/H10/H11/H12 + planetary roles),
      now with dignity-gated exceptions (Viparita Raja Yoga case for
      dusthana lords, debilitation checks before "fortune supports"
      claims) instead of unconditional signal-sum rules. Produces a
      positive/negative evidence ledger, not a single opaque number.

  Layer 3 — Sector/domain scoring
      Blends three components per sector, all three actually reading the
      registry's declared `core_houses` / `core_planets` (previously only
      the generic archetype vector was used and core_houses/core_planets
      were declared but dead):
        (a) generic archetype vector (jyotish.d10_archetypes math, general
            aptitude signature, not sector-specific)
        (b) core_houses strength: lordship placement + dignity of each
            house the registry declares for that sector
        (c) core_planets strength: dignity + placement of each planet the
            registry declares as a driver for that sector

  Layer 4 — Timed windows, bounded forecast horizon
      Reuses Job_Career.timeline._dasha_calendar (MD/AD calendar
      expansion), bounded to an explicit forecast window (default: today
      .. +years_ahead) instead of the chart owner's full lifetime. Each AD
      window gets a signed net evidence score (dignity, dusthana
      lordship/VRY exception, corroboration between MD and AD) and a
      single dominant label instead of independently-fireable, possibly
      contradictory tags.

Public API
----------
    compute_business_prediction(payload, venture_type="business",
                                 years_ahead=15) -> dict
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

from jyotish.d10_archetypes import (
    PLANET_ARCHETYPES,
    ARCHETYPE_NAMES,
    DIGNITY,
    scale_raw_support,
)


"""business_determination.jaimini

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""

from .constants import _DUSTHANA, _KT, _STRONG_DIGNITY
from .house_evidence import _dig_disclosure, _dig_factor, _dig_name, _effective_benefic_malefic_sets, _house_from_reference_lord, _house_sign, _mercury_contextual_nature, _moon_contextual_nature


def _jaimini_rasi_drishti_evidence(payload: Any, reference_house: int = 7) -> Tuple[float, List[str]]:
    """Jaimini whole-sign (rasi) aspect onto a reference house's sign.

    Reuses Stream_Determination.stream_scoring._rasi_drishti_targets
    verbatim (the only implementation of the classical movable/fixed/dual
    rasi-drishti rule found in this repo) rather than re-deriving the
    sign-aspect arithmetic. A natural benefic occupying a sign that casts
    rasi drishti onto the reference house's sign is treated as supportive
    evidence; a natural malefic, as pressure. Moon and Mercury now use
    their CONTEXTUAL nature (_effective_benefic_malefic_sets -- Moon's
    waxing/waning paksha, Mercury's conjunction-based association) instead
    of a fixed classification. Sun's context-dependent nuance (functional
    lordship by Lagna) remains an open, undocumented-here simplification.
    """
    from Stream_Determination.stream_scoring import _rasi_drishti_targets, _RASI_SIGNS

    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    if not lagna_sign or not planet_signs:
        return 0.0, []

    ref_sign = _house_sign(lagna_sign, reference_house)
    if not ref_sign:
        return 0.0, []

    benefics, malefics = _effective_benefic_malefic_sets(payload)

    # v34 audit fix: Moon/Mercury's benefic-vs-malefic membership above
    # already comes from a real, per-chart CONTEXTUAL reason (paksha for
    # Moon, conjunction-association for Mercury -- see
    # _moon_contextual_nature/_mercury_contextual_nature), but that reason
    # was computed, then discarded (only the resulting set membership was
    # kept) -- so a reader saw "Mercury ... -> malefic pressure" with no
    # way to tell WHY Mercury was malefic this chart without re-deriving it
    # themselves. Re-fetches the same reason text (already-computed logic,
    # not new astrology) and appends it inline for Moon/Mercury specifically,
    # since those are the two planets in this function whose classification
    # is genuinely chart-contextual rather than a fixed natural-benefic/
    # malefic label that needs no further explanation.
    _moon_reason = _moon_contextual_nature(payload)[1] if "Moon" in planet_signs else ""
    _merc_reason = _mercury_contextual_nature(payload)[1] if "Mercury" in planet_signs else ""

    # v46 audit fix (item 5, "Jaimini/Rasi-drishti interpretation" --
    # user-directed): declares the NEUTRAL-treatment policy this function
    # previously left implicit. Any planet whose rasi drishti lands on the
    # reference house's sign but is classified in NEITHER
    # _effective_benefic_malefic_sets() bucket (rare -- the classical
    # 9-graha set is normally fully partitioned into benefic/malefic,
    # including the Moon/Mercury contextual cases above, but a caller could
    # in principle supply a planet name this repo doesn't recognize in
    # either set) is now explicitly logged as NEUTRAL/no-scoring-effect
    # rather than silently skipped with no trace -- so a reader auditing
    # this function's notes can see every planet that WAS in aspecting
    # range and confirm none were dropped without explanation.
    net = 0.0
    notes: List[str] = []
    for planet, sign in planet_signs.items():
        if sign not in _RASI_SIGNS:
            continue
        if ref_sign not in _rasi_drishti_targets(sign):
            continue
        context_reason = ""
        if planet == "Moon":
            context_reason = f" (contextual nature: {_moon_reason})"
        elif planet == "Mercury":
            context_reason = f" (contextual nature: {_merc_reason})"
        if planet not in benefics and planet not in malefics:
            notes.append(f"{planet} casts Jaimini rasi drishti on H{reference_house} sign {ref_sign} -> NEUTRAL (not classified benefic or malefic for this chart); no scoring effect, per declared neutral-treatment policy{context_reason}")
            continue
        if planet in benefics:
            net += 3
            notes.append(f"{planet} casts Jaimini rasi drishti (whole-sign aspect) on H{reference_house} sign {ref_sign} -> benefic support{context_reason}")
        elif planet in malefics:
            # v35 audit fix (#22): treating every malefic rasi drishti as a
            # flat -3 "malefic pressure" collapses a real qualitative
            # distinction -- Saturn/Rahu/Ketu influence is classically read
            # as delayed, unconventional, technical/large-scale or hidden-
            # sector in character (mass visibility, foreign/unconventional
            # image, research prominence, durable-but-slow reputation), not
            # simply obstructive the way Mars' aggression or the Sun's
            # ego/authority friction reads. Softens the penalty and names
            # the distinct quality for Saturn/Rahu/Ketu specifically,
            # rather than collapsing every malefic influence into identical
            # "pressure" language; Mars/Sun (and any contextually-malefic
            # Moon/Mercury) keep the full -3, since their classical
            # character genuinely is more directly obstructive/volatile.
            if planet in ("Saturn", "Rahu", "Ketu"):
                net -= 1.5
                notes.append(f"{planet} casts Jaimini rasi drishti on H{reference_house} sign {ref_sign} -> not simply obstructive; reads as delayed-but-durable, unconventional, technical/large-scale, or hidden-sector influence rather than direct pressure{context_reason}")
            else:
                net -= 3
                notes.append(f"{planet} casts Jaimini rasi drishti on H{reference_house} sign {ref_sign} -> malefic pressure{context_reason}")

    return net, notes

def _argala_evidence(payload: Any, reference_house: int = 7) -> Tuple[float, List[str]]:
    """Argala (support) surviving Virodhargala (obstruction) cancellation
    on a reference house, reusing jyotish.astro._compute_jaimini_virodhargala
    verbatim (already-existing generic argala/virodhargala implementation,
    used elsewhere in this repo for H10 in jyotish/engine.py). Applied here
    to H7 (venture/partnership house) by default."""
    from jyotish.astro import _compute_jaimini_virodhargala

    planet_house = getattr(payload, "planet_house", {}) or {}
    if not planet_house:
        return 0.0, []

    survivors = _compute_jaimini_virodhargala(reference_house, planet_house)
    if not survivors:
        return 0.0, []

    effective_benefics, effective_malefics = _effective_benefic_malefic_sets(payload)
    net = 0.0
    notes: List[str] = []
    benefics = [p for p in survivors if p in effective_benefics]
    malefics = [p for p in survivors if p in effective_malefics]
    if benefics:
        net += 4
        notes.append(f"Uncancelled argala on H{reference_house} from {', '.join(sorted(benefics))} -> supportive, obstruction-free backing")
    if malefics:
        net -= 4
        notes.append(f"Uncancelled argala on H{reference_house} from {', '.join(sorted(malefics))} -> obstructive pressure not cancelled by virodhargala")

    return net, notes

def _ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 4 -> '4th', 11/12/13 -> 'th'
    (English ordinal-suffix exception for the 11-13 teens). Audit fix:
    the Karakamsha evidence string previously used a bare f"{house_num}th"
    which rendered "3th-from-Karakamsha" instead of "3rd-from-Karakamsha"."""
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _karakamsha_business_evidence(payload: Any) -> List[Tuple[float, str]]:
    """v17 audit fix: Karakamsha (the Navamsha/D9 sign occupied by the
    Atmakaraka) was entirely absent from this module. Jaimini treats the
    10th-from-Karakamsha as the deeper vocational-mode indicator,
    corroborating (not replacing) the D1/D10 read. Checks the 10th, 3rd,
    7th, 11th and 2nd houses counted FROM Karakamsha for lords well placed
    (kendra/trikona, not debilitated) in the D1 chart -- the same
    corroboration pattern _phaladeepika_multi_lagna_evidence already uses
    for Moon/Sun references, applied to the Jaimini reference point."""
    atmakaraka = getattr(payload, "atmakaraka", "") or ""
    d9_chart = ((getattr(payload, "divisional_charts", {}) or {}).get("D9_navamsha", {}) or {})
    if not atmakaraka or not d9_chart:
        return []
    karakamsha_sign = d9_chart.get(atmakaraka, "")
    if not karakamsha_sign:
        return []

    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = getattr(payload, "planet_dignities", {}) or {}
    results: List[Tuple[float, str]] = []

    _KARAKAMSHA_HOUSE_WEIGHT = {10: 8.0, 3: 5.0, 7: 5.0, 11: 6.0, 2: 4.0}
    for house_num, weight in _KARAKAMSHA_HOUSE_WEIGHT.items():
        lord = _house_from_reference_lord(karakamsha_sign, house_num)
        if not lord:
            continue
        placed = planet_house.get(lord, 0)
        dig = _dig_name(lord, dignities)
        if placed in _KT and dig != "DEBILITATED":
            results.append((weight * _dig_factor(lord, dignities),
                             f"Jaimini Karakamsha: {_ordinal(house_num)}-from-Karakamsha lord ({lord}) in kendra/trikona, dignity={_dig_disclosure(lord, dignities, payload)} -> vocational mode corroborates business houses"))
        elif dig == "DEBILITATED" and placed in _DUSTHANA:
            results.append((-3.0, f"Jaimini Karakamsha: {_ordinal(house_num)}-from-Karakamsha lord ({lord}) debilitated in a dusthana -> vocational-mode corroboration withheld"))

    # v18 audit fix: the above only ever judged LORDS of houses counted
    # from Karakamsha, never who actually OCCUPIES the Karakamsha sign
    # itself (or its 10th) -- classical Jaimini reads planets conjunct/
    # aspecting Karakamsha as direct participants in the vocational
    # signature, not just the sign's ruler. Adds occupancy of the
    # Karakamsha sign itself and its 10th (the deeper vocational-mode
    # house) via D1 sign placement (planet_signs).
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    benefics, malefics = _effective_benefic_malefic_sets(payload)
    if planet_signs:
        karakamsha_occupants = [p for p, s in planet_signs.items() if s == karakamsha_sign and p != atmakaraka]
        ben_occ = [p for p in karakamsha_occupants if p in benefics]
        mal_occ = [p for p in karakamsha_occupants if p in malefics]
        if ben_occ:
            results.append((4.0, f"Jaimini Karakamsha: benefic(s) {', '.join(sorted(set(ben_occ)))} occupy the Karakamsha sign ({karakamsha_sign}) itself -> direct vocational-signature support"))
        if mal_occ:
            results.append((-3.0, f"Jaimini Karakamsha: malefic(s) {', '.join(sorted(set(mal_occ)))} occupy the Karakamsha sign ({karakamsha_sign}) itself -> vocational-signature pressure"))

        from jyotish.constants import _SIGN_NUM
        if karakamsha_sign in _SIGN_NUM:
            signs_ordered = sorted(_SIGN_NUM, key=_SIGN_NUM.__getitem__)
            tenth_from_karakamsha_sign = signs_ordered[(_SIGN_NUM[karakamsha_sign] - 1 + 9) % 12]
            tenth_occupants = [p for p, s in planet_signs.items() if s == tenth_from_karakamsha_sign]
            ben_tenth = [p for p in tenth_occupants if p in benefics]
            if ben_tenth:
                results.append((4.0, f"Jaimini Karakamsha: benefic(s) {', '.join(sorted(set(ben_tenth)))} occupy the 10th-from-Karakamsha sign ({tenth_from_karakamsha_sign}) -> vocational-mode house directly activated"))

    return results

def _arudha_business_evidence(payload: Any) -> List[Tuple[float, str]]:
    """v17 audit fix: Arudha Lagna (AL), A7/Darapada and A10 (visible
    professional image) were entirely absent. Reuses
    jyotish.astro._compute_arudha_pada (the same classical Parashara-method
    Arudha calculator already used elsewhere in this repo) to derive AL,
    A7 and A10 sign, then checks: A10 lord's own D1 strength (public
    professional image credibility), an A10-A7 sign connection (business
    role backed by real commercial/customer interface, not just image),
    and whether AL itself is occupied/aspected by a benefic (visible
    social manifestation supports business)."""
    from jyotish.astro import _compute_arudha_pada
    from jyotish.constants import _SIGN_LORD

    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    planet_signs = getattr(payload, "planet_signs", {}) or {}
    if not lagna_sign or not planet_signs:
        return []
    planets_d1 = {p: {"sign": s} for p, s in planet_signs.items()}

    al_sign = _compute_arudha_pada(1, lagna_sign, planets_d1)
    a7_sign = _compute_arudha_pada(7, lagna_sign, planets_d1)
    a10_sign = _compute_arudha_pada(10, lagna_sign, planets_d1)
    if not (al_sign or a7_sign or a10_sign):
        return []

    planet_house = getattr(payload, "planet_house", {}) or {}
    dignities = getattr(payload, "planet_dignities", {}) or {}
    benefics, malefics = _effective_benefic_malefic_sets(payload)
    results: List[Tuple[float, str]] = []

    if a10_sign:
        a10_lord = _SIGN_LORD.get(a10_sign, "")
        if a10_lord:
            placed = planet_house.get(a10_lord, 0)
            dig = _dig_name(a10_lord, dignities)
            if placed in _KT and dig != "DEBILITATED":
                results.append((6.0 * _dig_factor(a10_lord, dignities),
                                 f"Jaimini: A10 (Arudha of 10th, sign {a10_sign}) lord ({a10_lord}) well placed -> visible professional/business image is credible"))
            elif dig == "DEBILITATED":
                results.append((-3.0, f"Jaimini: A10 lord ({a10_lord}) debilitated -> visible professional image undermined"))

    if a10_sign and a7_sign:
        a10_lord = _SIGN_LORD.get(a10_sign, "")
        a7_lord = _SIGN_LORD.get(a7_sign, "")
        if a10_sign == a7_sign or (a10_lord and a7_lord and a10_lord == a7_lord):
            results.append((5.0, "Jaimini: A10-A7 connection -> visible business role is backed by a real commercial/customer interface, not mere image"))

    if al_sign:
        al_occupants = [p for p, s in planet_signs.items() if s == al_sign]
        benefic_al = [p for p in al_occupants if p in benefics]
        malefic_al = [p for p in al_occupants if p in malefics]
        if benefic_al:
            results.append((4.0, f"Jaimini: benefic(s) {', '.join(sorted(set(benefic_al)))} occupy Arudha Lagna (AL, sign {al_sign}) -> visible social manifestation supports business"))
        elif malefic_al:
            results.append((-3.0, f"Jaimini: malefic(s) {', '.join(sorted(set(malefic_al)))} occupy Arudha Lagna (AL, sign {al_sign}) -> visible social manifestation strained"))

    # v18/v19 audit fix: Argala/Virodhargala and rasi drishti were previously
    # applied only to D1 houses (H1/H7/H10), never to A7/A10/AL themselves,
    # even though both helper functions already accept an arbitrary
    # reference_house. Since D1 houses are whole-sign from Lagna, an
    # Arudha's own "house number from Lagna" can be computed the same way
    # _compute_arudha_pada itself does, then fed straight into the existing
    # reference_house-parameterized helpers -- no new argala machinery
    # needed, just correct reuse of what already exists.
    # v19 fix (user-caught): the v18 comment claimed BOTH argala and rasi
    # drishti were extended to A7/A10/AL, but the loop only ever called
    # _argala_evidence() -- _jaimini_rasi_drishti_evidence() was never
    # invoked here. Both are now genuinely applied.
    from jyotish.constants import _SIGN_NUM
    if lagna_sign in _SIGN_NUM:
        for arudha_name, arudha_sign in (("A10", a10_sign), ("A7", a7_sign), ("AL", al_sign)):
            if not arudha_sign or arudha_sign not in _SIGN_NUM:
                continue
            house_from_lagna = (_SIGN_NUM[arudha_sign] - _SIGN_NUM[lagna_sign]) % 12 + 1
            _, argala_notes = _argala_evidence(payload, reference_house=house_from_lagna)
            for note in argala_notes:
                weight = 4.0 if "supportive" in note else -4.0
                results.append((weight, note.replace(f"H{house_from_lagna}", f"{arudha_name} (H{house_from_lagna} from Lagna, sign {arudha_sign})")))
            _, drishti_notes = _jaimini_rasi_drishti_evidence(payload, reference_house=house_from_lagna)
            for note in drishti_notes:
                weight = 3.0 if "benefic support" in note else -3.0
                results.append((weight, note.replace(f"H{house_from_lagna}", f"{arudha_name} (H{house_from_lagna} from Lagna, sign {arudha_sign})")))

    # v18 audit fix: no AK-AmK RELATIONSHIP test existed -- only AmK's own
    # house lordship was checked (in the mode gate). Jaimini treats a
    # strong Atmakaraka-Amatyakaraka relationship (same sign, mutual
    # kendra/trikona, or conjunction) as alignment between personal
    # identity (AK) and professional action (AmK), which the spec calls
    # out explicitly as a distinct check from AmK's house rulership alone.
    atmakaraka = getattr(payload, "atmakaraka", "") or ""
    amatyakaraka = getattr(payload, "amatyakaraka", "") or ""
    if atmakaraka and amatyakaraka and atmakaraka != amatyakaraka:
        ak_house, amk_house = planet_house.get(atmakaraka, 0), planet_house.get(amatyakaraka, 0)
        ak_sign, amk_sign = planet_signs.get(atmakaraka, ""), planet_signs.get(amatyakaraka, "")
        if ak_sign and ak_sign == amk_sign:
            results.append((5.0, f"Jaimini: AK ({atmakaraka}) and AmK ({amatyakaraka}) conjunct in the same sign ({ak_sign}) -> personal identity and professional action are directly aligned"))
        elif ak_house and amk_house:
            diff = abs(ak_house - amk_house) % 12
            if diff in (0, 3, 6, 9):  # same/kendra-from-each-other
                results.append((3.0, f"Jaimini: AK ({atmakaraka}) and AmK ({amatyakaraka}) in mutual kendra -> identity and professional action reinforce each other"))
            elif diff in (4, 8):  # mutual trikona
                results.append((3.0, f"Jaimini: AK ({atmakaraka}) and AmK ({amatyakaraka}) in mutual trikona -> identity and professional action reinforce each other"))

    # Argala on the house AmK itself occupies (its professional-karaka
    # "home base" for this chart) -- Argala is classically applied to
    # houses, not planets directly, so this reads the support/obstruction
    # environment of wherever the professional karaka sits.
    if amatyakaraka:
        amk_house = planet_house.get(amatyakaraka, 0)
        if amk_house:
            _, amk_argala_notes = _argala_evidence(payload, reference_house=amk_house)
            for note in amk_argala_notes:
                weight = 3.0 if "supportive" in note else -3.0
                results.append((weight, note.replace(f"H{amk_house}", f"AmK's house (H{amk_house})")))

    return results

def _jaimini_business_score(md_lord: str, ad_lord: str, payload: Any) -> Tuple[float, str]:
    """Reuses Job_Career.timeline._jaimini_career_score, with one narrow
    business-only gate layered on top (v38 audit fix, #16, user-caught):
    the shared function treats EVERY chara-karaka role match as flat
    positive credit purely from being active in the dasha, regardless of
    the matched planet's own dignity/house placement -- including GK
    (Gnatikaraka, the "enemy/obstacle/competition" karaka), whose classical
    signification is conflict and rivalry, not straightforward gain. A
    Gnatikaraka period being "active" should not automatically add
    positive business points; whether it helps or hurts still depends on
    that planet's own condition. This wrapper does NOT modify the shared
    Job_Career function (career and business dasha-timing share this
    scoring deliberately, and Job_Career has its own separate test suite
    this change must not risk) -- it only re-examines the GK case
    specifically, using dignity data already on the business payload, and
    discounts/re-labels the credit when GK's own dignity does not support
    a positive read. AK/AmK/Brahma/Maheshwara/A10/A1 activations are left
    exactly as returned by the shared function (these are genuine
    livelihood/recognition karakas whose "being active" IS classically a
    positive signal, unlike GK)."""
    from Job_Career.timeline import jaimini_career_score
    score, label = jaimini_career_score(md_lord, ad_lord, payload)
    if score <= 0.0:
        return score, label

    jdata = getattr(payload, "kn_rao_jaimini", None) or getattr(payload, "kn_rao_jaimini_data", None) or {}
    chara_karakas = (jdata.get("chara_karakas", {}) if isinstance(jdata, dict) else {}) or {}
    gk_planet = chara_karakas.get("GK", "")
    gk_active = bool(gk_planet) and gk_planet in (md_lord, ad_lord)
    # Only intervene when GK specifically is the (sole) role that produced
    # this credit -- if a stronger role (AmK/AK/Brahma-Maheshwara) already
    # matched, the shared function's max()-based priority means the label
    # already reflects that stronger role, not GK, and should be left alone.
    if gk_active and "gnatikaraka" in str(label).lower():
        dignities = getattr(payload, "planet_dignities", {}) or {}
        gk_dignity = str(dignities.get(gk_planet, "")).upper()
        if gk_dignity not in _STRONG_DIGNITY:
            discounted = round(score * 0.4, 2)
            return discounted, (
                f"Gnatikaraka ({gk_planet}) period active -- classically signifies rivalry/obstacles/"
                f"competition, not straightforward gain; {gk_planet}'s own dignity ({gk_dignity or 'unknown'}) "
                f"does not support treating this as a clear positive, credit discounted accordingly"
            )
    return score, label

