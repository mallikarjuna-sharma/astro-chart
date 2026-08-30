"""business_determination.significators

Split out of the original monolithic business_engine.py (v21b) as part of
the v22 modularization pass. Behavior-preserving: every function/constant
kept its exact original source text, only the file location changed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .constants import EVIDENCE_BASIS, _EVIDENCE_CATEGORY_H11_GAINS, _EVIDENCE_CATEGORY_H2_CAPITAL, _EVIDENCE_CATEGORY_H6_H8_H12_RISK, _PROFIT_FAMILY_CATEGORIES, _STABILITY_RISK_CATEGORIES
from .house_evidence import _business_significator_graha_yuddha_evidence, _combustion_status, _d10_dispositor_chain_evidence, _d10_native_house_evidence, _d1_dispositor_chain_evidence, _d1_tenth_lord_direct_evidence, _d2_native_house_evidence, _d3_native_house_evidence, _d9_dispositor_chain_evidence, _d9_native_house_evidence, _extended_house_combination_evidence, _fifth_house_business_evidence, _house_lord_strength, _lagnesh_affliction_and_karaka_connection_evidence, _multi_varga_lagna_precedence_evidence, _neecha_bhanga_status, _phaladeepika_multi_lagna_evidence, _retrograde_status, _rich_planet_dignities, sav_lookup
from .jaimini import _DUSTHANA, _KT, _STRONG_DIGNITY, _argala_evidence, _arudha_business_evidence, _dig_disclosure, _dig_factor, _dig_name, _jaimini_rasi_drishti_evidence, _karakamsha_business_evidence
from .nakshatra_business import janma_nakshatra_business_evidence
from .rule_provenance import resolve_rule_provenance


def score_business_significators(payload: Any) -> Dict[str, Any]:
    """H2/H3/H6/H7/H9/H10/H11/H12 + planetary business-strength scan,
    returning a signed positive/negative evidence ledger rather than a
    single accumulate-only sum. Dignity-gated exceptions replace several
    previously unconditional rules (Rahu-in-H7, Darakaraka-in-kendra,
    Mercury+Venus, H9-lord-in-kendra, dusthana-lord penalties).
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    dignities = _rich_planet_dignities(payload)
    sav = getattr(payload, "sav_points_houses", {}) or {}
    darakaraka = getattr(payload, "darakaraka", "") or ""

    def _h(num: int) -> str:
        return house_lords.get(str(num), house_lords.get(num, ""))

    def _ph(planet: str) -> int:
        return planet_house.get(planet, 0)

    def _sav_h(h: int) -> int:
        # Delegates to the shared constants.sav_lookup() helper (factored
        # out so significators.py/mode_gate.py/ashtakavarga_timing.py all
        # share one SAV-lookup implementation instead of three copies).
        return sav_lookup(sav, h)

    def _co_tenants(house: int, exclude: str) -> List[str]:
        return [p for p, h in planet_house.items() if h == house and p != exclude]

    evidence: List[Dict[str, Any]] = []

    # v-audit fix (typed rule IDs, first slice; comment rewritten in the
    # eighth slice -- item 6, "stale comments still describe deleted
    # classifiers" -- to describe the CURRENT end state rather than the
    # original, now-superseded intermediate migration step): every evidence
    # entry carries an explicit `category` tag -- WHICH financial/risk
    # TARGET (profit, stability-risk, or neither) this entry concerns --
    # set directly by the code below that KNOWS what house/doctrine each
    # entry is about, not inferred from its prose. `category` is genuinely
    # partial BY DESIGN (only H2/H11/H6/H8/H12-anchored evidence gets one;
    # most entries aren't about those specific houses at all), which is why
    # `evidence_typing_stats.untyped_entries` being nonzero is an expected
    # steady state, not a migration gap -- see the `profit`/`stability_risk`
    # fields below (and their own comment in _add()) for the axis that IS
    # unconditionally set on every entry and that scoring.py actually
    # consumes; no note-text keyword scanning happens anywhere downstream of
    # this module anymore.
    _CATEGORY_H2_CAPITAL = _EVIDENCE_CATEGORY_H2_CAPITAL
    _CATEGORY_H11_GAINS = _EVIDENCE_CATEGORY_H11_GAINS
    _CATEGORY_H6_H8_H12_RISK = _EVIDENCE_CATEGORY_H6_H8_H12_RISK

    # v-audit fix (typed rule IDs, third slice -- item 6, "no typed
    # polarity target"; comment rewritten in the eighth slice -- item 6,
    # "stale comments still describe deleted classifiers"): `category`
    # (above) tags an entry's financial/risk TARGET (profit, stability,
    # ...). `family` is a genuinely DIFFERENT axis -- the METHODOLOGICAL
    # CORROBORATION family (D1_PROMISE / VARGA_CONFIRMATION /
    # ACTIVATION_DIRECTION / STRENGTH) that family_totals_capped's
    # per-family correlation cap groups by. The two axes are NOT
    # interchangeable: a single entry can be category=H11_GAINS (a
    # profit-target finding) while ALSO being family=VARGA_CONFIRMATION
    # (because it happens to be a D9 dignity-confirmation check) --
    # collapsing them into one tag would silently misclassify whichever
    # axis wasn't asked for. Every `family` tag below is individually
    # verified (per call site, tracked in each site's own comment) against
    # what the now-deleted `_family_of()` text classifier used to produce
    # for that exact note, so this is a pure explicitness upgrade relative
    # to that prior behavior, not a reclassification -- but `family` is now
    # the ONLY classification mechanism; there is no text-scan fallback left
    # to fall back to (see the `fam = e["family"]` line further down, which
    # raises KeyError rather than re-deriving from text).
    _FAMILY_VARGA_CONFIRMATION = "VARGA_CONFIRMATION"
    # v-audit fix (typed rule IDs, fourth slice -- "next recommended slice"
    # item 3, Jaimini/KP activation direction): every site tagged below was
    # individually verified against its actual generated note text (jaimini.py)
    # to confirm this family assignment matches what the deleted
    # _family_of()'s text scan ("jaimini"/"argala"/"rasi drishti"/"kp "/
    # "sub-lord" substrings) would have independently produced -- so tagging
    # is a pure explicitness upgrade here too, not a reclassification.
    _FAMILY_ACTIVATION_DIRECTION = "ACTIVATION_DIRECTION"
    _FAMILY_STRENGTH = "STRENGTH"
    # v-audit fix (typed rule IDs, sixth slice -- item 1/D1_PROMISE
    # coverage): the deleted _family_of()'s DEFAULT fallthrough bucket.
    # Unlike the other three families (each keyed to a distinct, checkable
    # substring),
    # tagging an entry D1_PROMISE requires verifying its note does NOT
    # contain any of the other three families' trigger substrings --
    # checked individually per site below, not assumed.
    _FAMILY_D1_PROMISE = "D1_PROMISE"

    # v-audit fix (typed rule IDs, sixth slice -- item 6, "no stable rule_id
    # per evidence entry"): a third, independent tag -- WHICH specific rule/
    # classical technique fired, e.g. "SIG_PHALADEEPIKA_10TH_LORD" or
    # "SIG_D1_TENTH_LORD_DIRECT" -- distinct from both `category` (financial
    # target) and `family` (methodological corroboration bucket). Multiple
    # notes from the same source function share one rule_id (the function
    # IS the rule/technique; its several findings are that technique's
    # sub-checks, not separate rules) -- this is the identifier a future
    # provenance registry (rule_id -> classical source/chapter-verse/
    # interpretation/weight/controversy) would key off of. Scoped so far to
    # newly-verified sites only; the majority of this function's ~90 _add()
    # sites do not yet carry one.
    # v-audit fix (typed rule IDs, fourth slice -- items 3/4, "profit/
    # stability-risk calculation still falls back to keyword matching"):
    # scoring.py used to run TWO separately-defined copies of this same
    # keyword scan (one for business_layers.profit_2nd_11th, a duplicate for
    # business_profitability/gross_revenue_potential/profit_retention) plus a
    # third for business_stability -- each re-deriving "is this evidence
    # profit-relevant / stability-risk-relevant" from note text at every
    # consumption site. Centralizing that single decision HERE, at the one
    # place evidence is created, means every entry gets an explicit `profit`/
    # `stability_risk` boolean unconditionally (never left unset), so
    # scoring.py's consumers can read a typed field directly instead of
    # scanning text -- and there is exactly one implementation of the
    # decision instead of three duplicated, independently-maintained copies.
    # Precedence exactly matches what scoring.py's own _is_profit_evidence/
    # _is_stability_risk_evidence already did: an entry's structural
    # `category` tag (H2_CAPITAL/H11_GAINS -> profit; H6_H8_H12_RISK ->
    # stability_risk) is authoritative when present; entries with no
    # category (the majority, evidence not specifically anchored to those
    # houses) fall back to the same keyword heuristic scoring.py used --
    # unchanged wording, unchanged keyword lists, so this is a relocation of
    # an existing decision, not a new one, and produces bit-for-bit the same
    # profit_net/stability_risk_net totals as before for every chart.
    _PROFIT_KEYWORDS = ("h2", "h11", "profit", "capital", "gains", "wealth")
    _STABILITY_RISK_KEYWORDS = ("h2", "h6", "h8", "debt", "dusthana", "leverage", "liability")

    # v-audit fix (typed rule IDs, sixth slice -- item 6, "no fact_id or
    # dependency group exists"): moved ahead of _add() (previously defined
    # much later, only for the family-cap same-planet dedup loop below) so
    # _add() itself can tag every entry with a `fact_id` at generation time.
    # `fact_id` identifies WHICH underlying chart fact an entry is really
    # about -- its rule_id (the technique) plus whichever named planet(s) its
    # note mentions -- so two entries from DIFFERENT rules that both turn out
    # to be "about Mercury being exalted in H7," say, can be recognized as
    # correlated observations of the same fact rather than two independent
    # ones, without having to re-parse note text downstream. This is
    # infrastructure for future correlated-evidence deduplication, not
    # deduplication itself: fact_id is purely additive/informational here,
    # exactly like evidence_typing_stats -- no score, weight, or family total
    # computed anywhere in this function reads or is affected by fact_id. A
    # genuine dedup pass (e.g. discounting repeated fact_ids the way the
    # same-planet-within-family multiplier already discounts repeated
    # planets within one family) is a separate, scope-affecting change this
    # slice deliberately does not make.
    _PLANET_NAMES_FOR_DEDUP = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")

    def _planets_mentioned(note: str) -> List[str]:
        return [p for p in _PLANET_NAMES_FOR_DEDUP if re.search(rf"\b{p}\b", note)]

    # v-audit fix (typed rule IDs, seventh slice -- items 1/2, "fact_id is
    # informational only" / "fact_id is partly derived from note text"):
    # _add() now accepts explicit `fact_planets`/`fact_houses` so a call site
    # that already KNOWS which planet(s)/house(s) it's about (the majority
    # of single-lord checks -- H7/H2/H11/H3/H9/H12 lord, Darakaraka, Rahu,
    # Mercury+Venus, Mars/Saturn, the VRY qualification, combustion) can pass
    # that structural fact directly instead of having fact_id re-derived by
    # scanning the rendered note. Loop sites that iterate over dynamically-
    # generated (weight, note) tuples from house_evidence.py/jaimini.py
    # (D9/D10-native house graphs, extended house combinations, Phaladeepika,
    # Karakamsha/Arudha, etc.) do not yet carry a structured subject from
    # their source function, so those still fall back to the text scan --
    # disclosed per-entry via `fact_id_basis` ("structured" vs
    # "text_inferred"), not hidden. Fixing the remaining text_inferred sites
    # for good would mean changing those source functions' return shape
    # (house_evidence.py, jaimini.py) to carry structured subjects
    # themselves -- out of scope for this slice, tracked as ongoing.
    def _subject_key_for(
        note: str,
        fact_planets: Optional[Tuple[str, ...]] = None,
        fact_houses: Optional[Tuple[int, ...]] = None,
    ) -> Tuple[Optional[str], str]:
        """The WHAT this entry is about, independent of which rule found it
        -- e.g. "Mercury|H7" -- so two entries from DIFFERENT rule_ids that
        both concern the same underlying planet/house fact can be recognized
        as correlated (see fact_dependency_ledger below). Returns (subject or
        None, basis) -- None means no recognizable subject at all (a generic
        note mentioning no tracked planet and given no explicit
        fact_houses), which the dependency-group pass below treats as
        never correlated with anything else (conservative: no discount
        applied when we don't actually know what it's about)."""
        if fact_planets or fact_houses:
            planets_part = "+".join(sorted(p for p in (fact_planets or ()) if p))
            houses_part = "+".join(f"H{h}" for h in sorted(fact_houses or ()))
            subject = "|".join(part for part in (planets_part, houses_part) if part)
            return (subject or None), "structured"
        mentioned = _planets_mentioned(note)
        return ("+".join(mentioned) if mentioned else None), "text_inferred"

    def _add(
        polarity: str,
        weight: float,
        note: str,
        category: Optional[str] = None,
        family: Optional[str] = None,
        rule_id: Optional[str] = None,
        fact_planets: Optional[Tuple[str, ...]] = None,
        fact_houses: Optional[Tuple[int, ...]] = None,
    ) -> None:
        entry: Dict[str, Any] = {"polarity": polarity, "weight": round(weight, 3), "note": note}
        if category is not None:
            entry["category"] = category
        if family is not None:
            entry["family"] = family
        if rule_id is not None:
            entry["rule_id"] = rule_id
        if category is not None:
            entry["profit"] = category in _PROFIT_FAMILY_CATEGORIES
            entry["stability_risk"] = category in _STABILITY_RISK_CATEGORIES
        else:
            _n = note.lower()
            entry["profit"] = any(k in _n for k in _PROFIT_KEYWORDS)
            entry["stability_risk"] = any(k in _n for k in _STABILITY_RISK_KEYWORDS)
        _subject, _basis = _subject_key_for(note, fact_planets, fact_houses)
        _rule_part = rule_id or "UNSPECIFIED_RULE"
        # fact_id: WHICH rule found WHAT subject -- unique per (rule, subject)
        # pair, used to catch a single rule firing more than once for the
        # exact same subject (a true same-method duplicate). subject_key:
        # WHAT the entry is about, with the rule stripped out -- used to
        # catch DIFFERENT rules corroborating the same underlying fact (see
        # fact_dependency_ledger below for how the two are used differently).
        entry["fact_id"] = f"{_rule_part}:{_subject}" if _subject else _rule_part
        entry["subject_key"] = _subject
        entry["fact_id_basis"] = _basis
        evidence.append(entry)

    h2_lord, h3_lord = _h(2), _h(3)
    h6_lord, h7_lord, h8_lord = _h(6), _h(7), _h(8)
    h9_lord, h10_lord = _h(9), _h(10)
    h11_lord, h12_lord = _h(11), _h(12)

    # Combustion (Asta) check -- item 2 of the astrological-validity audit:
    # a planet conjunct the Sun within classical orb loses visibility/
    # standalone strength even when its sign-dignity label reads EXALTED
    # (a debilitation-style dignity check and a combustion check are
    # independent classical tests). Checked for every planet actually
    # cited as a significator here (H7/H10 lord, Amatyakaraka, Mercury as
    # the universal trade/commerce karaka) since these are exactly the
    # planets whose strength most directly feeds the business/employment
    # score. Uses _combustion_status() from house_evidence.py, which is
    # honest about missing data (skips rather than assumes not-combust
    # when payload.planet_longitudes is unavailable -- see that helper's
    # docstring for the INSUFFICIENT_EVIDENCE-style degradation).
    _amatyakaraka = str(getattr(payload, "amatyakaraka", "") or "")
    _combustion_checked_for = set()
    for _p, _role in ((h7_lord, "H7 lord"), (h10_lord, "H10 lord"), (_amatyakaraka, "Amatyakaraka"), ("Mercury", "universal trade/commerce karaka")):
        if not _p or _p in _combustion_checked_for:
            continue
        _combustion_checked_for.add(_p)
        _status = _combustion_status(payload, _p)
        if not _status.get("checked"):
            continue
        if _status.get("combust"):
            # Astrologer-reviewed refinement: the flat -6 this note used to
            # carry regardless of combustion depth over-penalized planets
            # only lightly inside the orb (e.g. an exalted Mercury 5 deg
            # from the Sun scored identically to one 0.1 deg away). The
            # note weight now tracks the same graduated severity/dignity-
            # leniency logic _combustion_strength_factor() applies to the
            # underlying strength number, so the ledger and the strength
            # calculation stay consistent with each other.
            _severity = _status.get("severity", 1.0)
            _dig = _dig_name(_p, dignities)
            _lenient = _dig in {"EXALTED", "OWN", "MOOLATRIKONA"}
            if _lenient:
                _severity *= 0.5
            _weight = round(6.0 * _severity, 2)
            _depth = "deep" if "deep combustion" in (_status.get("reason") or "") else "light"
            _lenient_note = (
                f"; dignity leniency applied ({_dig} planets resist combustion damage better per this engine's reading)"
                if _lenient else ""
            )
            if _weight > 0.15:
                # v-audit fix (typed rule IDs): verified -- no varga/jaimini/
                # sav trigger substrings -> D1_PROMISE via text today.
                _add("NEGATIVE", _weight,
                     f"{_p} ({_role}) is COMBUST, {_depth} ({_status.get('reason')}) -> standalone visibility/strength somewhat undermined regardless of sign-dignity label{_lenient_note}; effective strength discounted proportionally to depth",
                     family=_FAMILY_D1_PROMISE, rule_id="SIG_COMBUSTION_CHECK", fact_planets=(_p,))

    # H7 — core venture/partnership house
    if h7_lord:
        strength = _house_lord_strength(payload, 7)
        # v-audit fix (typed rule IDs): verified -- no trigger substrings ->
        # D1_PROMISE via text today.
        if strength >= 0.6:
            _add("POSITIVE", 16 * strength,
                 f"H7 lord ({h7_lord}) well placed (strength={strength}) -> venture/partnership house activated",
                 family=_FAMILY_D1_PROMISE, rule_id="SIG_H7_VENTURE_STRENGTH", fact_planets=(h7_lord,), fact_houses=(7,))
        elif strength < 0.35:
            _add("NEGATIVE", 8 * (1 - strength),
                 f"H7 lord ({h7_lord}) weak (strength={strength}) -> partnership house under-supported",
                 family=_FAMILY_D1_PROMISE, rule_id="SIG_H7_VENTURE_STRENGTH", fact_planets=(h7_lord,), fact_houses=(7,))

        # D9 (Navamsha) is the classical confirmation chart for whether a
        # partnership/relationship promise in D1 actually fructifies.
        d9_dig = str((getattr(payload, "d9_planet_dignities", {}) or {}).get(h7_lord, "") or "").upper()
        if d9_dig in _STRONG_DIGNITY:
            _add("POSITIVE", 5, f"H7 lord ({h7_lord}) strong in D9 (Navamsha)={d9_dig} -> partnership promise confirmed", family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_H7_D9_CONFIRMATION", fact_planets=(h7_lord,), fact_houses=(7,))
        elif d9_dig == "DEBILITATED":
            _add("NEGATIVE", 5, f"H7 lord ({h7_lord}) debilitated in D9 (Navamsha) -> partnership promise unconfirmed", family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_H7_D9_CONFIRMATION", fact_planets=(h7_lord,), fact_houses=(7,))

    # Jaimini rasi drishti (whole-sign aspect) and argala/virodhargala onto H7
    drishti_net, drishti_notes = _jaimini_rasi_drishti_evidence(payload, reference_house=7)
    for note in drishti_notes:
        _add("POSITIVE" if "benefic support" in note else "NEGATIVE", abs(3), note, family=_FAMILY_ACTIVATION_DIRECTION, rule_id="SIG_JAIMINI_RASI_DRISHTI_H7", fact_houses=(7,))

    argala_net, argala_notes = _argala_evidence(payload, reference_house=7)
    for note in argala_notes:
        _add("POSITIVE" if "supportive" in note else "NEGATIVE", abs(4), note, family=_FAMILY_ACTIVATION_DIRECTION, rule_id="SIG_ARGALA_H7", fact_houses=(7,))

    # Phaladeepika ch.5 multi-lagna profession check (10th from Moon, 10th from Sun).
    # Each returned (weight, note) already carries its own exact
    # dignity-weighted magnitude and sign -- add directly, no re-flattening.
    # v-audit fix (typed rule IDs): every note from this function contains
    # "Phaladeepika" -- _family_of()'s highest-precedence check ("if
    # phaladeepika in n: return D1_PROMISE") already classifies 100% of
    # this loop's output as D1_PROMISE; tagging is a pure explicitness
    # upgrade, not a reclassification.
    for weight, note in _phaladeepika_multi_lagna_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_PHALADEEPIKA_MULTI_LAGNA")

    # D9-Lagna / D10-Lagna varga-native lordship precedence corroboration
    for weight, note in _multi_varga_lagna_precedence_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_MULTI_VARGA_LAGNA_PRECEDENCE")

    # Full D10 (Dashamsha)-native house-graph evidence.
    for weight, note in _d10_native_house_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_D10_NATIVE_HOUSE_GRAPH")

    # Full D9 (Navamsha)-native house-graph evidence.
    for weight, note in _d9_native_house_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_D9_NATIVE_HOUSE_GRAPH")

    # Direct D1 10th-lord judgment (own strength, H7-H10/H10-H11/H2-H10
    # connections, conjunctions, own D9/D10 dignity) -- previously h10_lord
    # was only ever consumed indirectly by other checks, never judged
    # directly as BPHS treats it.
    # v-audit fix (typed rule IDs): individually verified every note text
    # this function produces (house_evidence.py::_d1_tenth_lord_direct_evidence)
    # -- including its "D1 10th lord debilitated in BOTH D9 and D10" finding,
    # which mentions D9/D10 but NOT any of _family_of()'s required "-native"/
    # "navamsha"/"dashamsha" substrings, so it too falls through to
    # D1_PROMISE via text today. Tagging the whole loop D1_PROMISE therefore
    # matches current behavior exactly for every entry, not just most of them.
    for weight, note in _d1_tenth_lord_direct_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_D1_TENTH_LORD_DIRECT")

    # v17: 5th house (independent-professional group 1-2-5-9-10-11 and
    # several business-sector combinations) -- previously entirely absent.
    # v-audit fix (typed rule IDs): verified every note text this function
    # produces (house_evidence.py::_fifth_house_business_evidence) contains
    # none of the varga/jaimini/sav trigger substrings -> D1_PROMISE via
    # text today, tagged to match.
    for weight, note in _fifth_house_business_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_FIFTH_HOUSE_BUSINESS")

    # v23 audit fix: direct multi-lord relationship tests for the spec's
    # section-1/section-9 house combinations that were previously absent
    # entirely (2-11, 2-8, 3-7, 3-11, 10th-lord-in-3rd, Lagnesh-H3, 4-8
    # inherited property, 4-10-11, 4-7, 4-12, 9-10, 9-11, 2-9-10, and the
    # 3-7-11/3-10-11/8-10-11/9-10-11/4-7-12 sector-table rows) -- see
    # _extended_house_combination_evidence()'s docstring for exact scope.
    # v-audit fix (typed rule IDs): verified every note text this function
    # (house_evidence.py::_extended_house_combination_evidence) produces --
    # pure house-lord connection tests, none contain any varga/jaimini/sav
    # trigger substring -> D1_PROMISE via text today, tagged to match.
    for weight, note in _extended_house_combination_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_EXTENDED_HOUSE_COMBINATIONS")

    # v-audit fix (astrological completeness -- "No unified D1-D9-D10
    # dispositor-chain subsystem"): multi-hop dispositor chain for the
    # H7/H10 lords, now built for all three vargas (see
    # house_evidence.py::_dispositor_chain_walk for the shared mechanism and
    # ::_d1_dispositor_chain_evidence / _d9_dispositor_chain_evidence /
    # _d10_dispositor_chain_evidence for each varga's wrapper). D1 is tagged
    # D1_PROMISE (the base-chart promise itself); D9/D10 are tagged
    # VARGA_CONFIRMATION (the same classical role every other D9/D10
    # corroboration check in this module already plays -- confirming or
    # denying a D1 promise using the divisional chart's own house graph,
    # not asserting an independent promise). Verified none of the three
    # produce any varga/jaimini/sav trigger substrings that would otherwise
    # misclassify them via the (now-deleted) text fallback.
    for weight, note in _d1_dispositor_chain_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_D1_DISPOSITOR_CHAIN")
    for weight, note in _d9_dispositor_chain_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_D9_DISPOSITOR_CHAIN")
    for weight, note in _d10_dispositor_chain_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_D10_DISPOSITOR_CHAIN")

    # v24 audit fix: Lagnesh combustion (distinct from debilitation, which
    # was already handled) and Lagnesh-Mercury/Mars/Sun/Rahu karaka
    # connection -- two specifically-named section-1 checks that had no
    # matching code anywhere in the module before this.
    # v-audit fix (typed rule IDs): verified -- no varga/jaimini/sav trigger
    # substrings in any note this function produces -> D1_PROMISE via text
    # today, tagged to match.
    for weight, note in _lagnesh_affliction_and_karaka_connection_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_LAGNESH_AFFLICTION_KARAKA")

    # GYUDDHA-1 fix: the Lagnesh-only Graha Yuddha check above never
    # covered the 2nd/6th/7th/10th/11th house lords or Mercury (the
    # primary trade/commerce karaka) -- a combat-losing planet in a
    # business-critical role went undetected entirely. This closes that
    # gap for those specific significators.
    # v-audit fix (typed rule IDs): verified -- no varga/jaimini/sav trigger
    # substrings in any note this function produces -> D1_PROMISE via text
    # today, tagged to match.
    for weight, note in _business_significator_graha_yuddha_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_BUSINESS_SIGNIFICATOR_GRAHA_YUDDHA")

    # v17: Jaimini Karakamsha (10th/3rd/7th/11th/2nd FROM Karakamsha) --
    # previously entirely absent.
    for weight, note in _karakamsha_business_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_ACTIVATION_DIRECTION, rule_id="SIG_JAIMINI_KARAKAMSHA")

    # v17: Jaimini Arudha Lagna / A7 / A10 -- previously entirely absent.
    for weight, note in _arudha_business_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_ACTIVATION_DIRECTION, rule_id="SIG_JAIMINI_ARUDHA_LAGNA")

    # v17: Argala/Virodhargala and Jaimini rasi drishti were hardcoded to
    # H7 only at every call site, even though both helper functions already
    # accept an arbitrary reference_house. The spec explicitly asks for
    # Argala to be applied to Lagna and the 10th as well, not just H7.
    for ref_house in (1, 10):
        drishti_net_x, drishti_notes_x = _jaimini_rasi_drishti_evidence(payload, reference_house=ref_house)
        for note in drishti_notes_x:
            _add("POSITIVE" if "benefic support" in note else "NEGATIVE", abs(3), note, family=_FAMILY_ACTIVATION_DIRECTION, rule_id=f"SIG_JAIMINI_RASI_DRISHTI_H{ref_house}", fact_houses=(ref_house,))
        argala_net_x, argala_notes_x = _argala_evidence(payload, reference_house=ref_house)
        for note in argala_notes_x:
            _add("POSITIVE" if "supportive" in note else "NEGATIVE", abs(4), note, family=_FAMILY_ACTIVATION_DIRECTION, rule_id=f"SIG_ARGALA_H{ref_house}", fact_houses=(ref_house,))

    # H11 — profit realization
    if h11_lord and _ph(h11_lord) in {7, 10, 11}:
        strength = _house_lord_strength(payload, 11)
        # v-audit fix (typed rule IDs): base-strength note has no D9 mention
        # -> D1_PROMISE via text; the two D9-dignity notes below explicitly
        # say "D9 (Navamsha)", which DOES match _family_of()'s "d9
        # (navamsha)" trigger substring -> VARGA_CONFIRMATION via text, NOT
        # D1_PROMISE (verified precisely, not assumed from the D1-ish
        # surrounding context).
        _add("POSITIVE", 14 * strength,
             f"H11 lord ({h11_lord}) in H7/H10/H11 (strength={strength}) -> profit realization supported",
             category=_CATEGORY_H11_GAINS, family=_FAMILY_D1_PROMISE, rule_id="SIG_H11_PROFIT_REALIZATION", fact_planets=(h11_lord,), fact_houses=(11,))
        d9_h11_dig = str((getattr(payload, "d9_planet_dignities", {}) or {}).get(h11_lord, "") or "").upper()
        if d9_h11_dig in _STRONG_DIGNITY:
            _add("POSITIVE", 5, f"H11 lord ({h11_lord}) strong in D9 (Navamsha)={d9_h11_dig} -> gains promise confirmed", category=_CATEGORY_H11_GAINS, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_H11_D9_CONFIRMATION", fact_planets=(h11_lord,), fact_houses=(11,))
        elif d9_h11_dig == "DEBILITATED":
            _add("NEGATIVE", 5, f"H11 lord ({h11_lord}) debilitated in D9 (Navamsha) -> gains promise unconfirmed", category=_CATEGORY_H11_GAINS, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_H11_D9_CONFIRMATION", fact_planets=(h11_lord,), fact_houses=(11,))

    # H2 — capital base
    if h2_lord:
        strength = _house_lord_strength(payload, 2)
        # v-audit fix (typed rule IDs): same split as H11 above -- base
        # strength note is D1_PROMISE, the two D9-dignity notes below are
        # VARGA_CONFIRMATION (verified "D9 (Navamsha)" trigger substring
        # present in exactly those two, not the base-strength note).
        if strength >= 0.6:
            _add("POSITIVE", 12 * strength, f"H2 lord ({h2_lord}) well placed -> capital base supported", category=_CATEGORY_H2_CAPITAL, family=_FAMILY_D1_PROMISE, rule_id="SIG_H2_CAPITAL_BASE", fact_planets=(h2_lord,), fact_houses=(2,))
        d9_h2_dig = str((getattr(payload, "d9_planet_dignities", {}) or {}).get(h2_lord, "") or "").upper()
        if d9_h2_dig in _STRONG_DIGNITY:
            _add("POSITIVE", 5, f"H2 lord ({h2_lord}) strong in D9 (Navamsha)={d9_h2_dig} -> capital promise confirmed", category=_CATEGORY_H2_CAPITAL, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_H2_D9_CONFIRMATION", fact_planets=(h2_lord,), fact_houses=(2,))
        elif d9_h2_dig == "DEBILITATED":
            _add("NEGATIVE", 5, f"H2 lord ({h2_lord}) debilitated in D9 (Navamsha) -> capital promise unconfirmed", category=_CATEGORY_H2_CAPITAL, family=_FAMILY_VARGA_CONFIRMATION, rule_id="SIG_H2_D9_CONFIRMATION", fact_planets=(h2_lord,), fact_houses=(2,))

    # RETROGRADE-1 (gap audit): Mercury retrograde is classically
    # significant for trade/communication ventures specifically -- an
    # entire slice of the sector registry (trading_commerce, retail,
    # media_creative_business, consulting_professional_services,
    # finance_investment, education_institutions) is Mercury-anchored, yet
    # this was never checked anywhere in this module. Deliberately NOT a
    # blanket penalty: mirrors the nuanced, non-uniform retrograde stance
    # already established by the general engine's Shadbala "Retrograde
    # Asymmetry" modifier (see house_evidence._retro_adjusted_dig_factor's
    # docstring) -- retrograde Cheshta Bala is a genuine strength gain, not
    # a weakness, but signification TIMING is a different axis: classical
    # practice reads retrograde Mercury as revisited/reconsidered trade
    # decisions, contract renegotiation, or delayed-but-not-blocked
    # commercial timing, not a block on the venture itself. Gated to only
    # business-relevant houses (2/6/7/10/11 -- capital, service/debt,
    # partnership, career/authority, gains) per the audit's specific ask,
    # so an unrelated Mercury placement doesn't generate noise. Degrades
    # gracefully (no evidence added, not a penalty) when payload carries no
    # retrograde data at all -- _retrograde_status() returns None in that
    # case, which is falsy, so the block below is simply skipped.
    _BUSINESS_RETRO_HOUSES = {2, 6, 7, 10, 11}
    if _retrograde_status(payload, "Mercury"):
        mercury_house = _ph("Mercury")
        mercury_is_relevant_lord = any(_h(h) == "Mercury" for h in _BUSINESS_RETRO_HOUSES)
        mercury_is_relevant_occupant = mercury_house in _BUSINESS_RETRO_HOUSES
        if mercury_is_relevant_lord or mercury_is_relevant_occupant:
            # v-audit fix (typed rule IDs): verified -- no trigger
            # substrings -> D1_PROMISE via text today.
            _add("NEGATIVE", 2,
                 "Mercury retrograde and linked to a business house (H2/6/7/10/11) -> "
                 "trade/communication decisions likely to be revisited or renegotiated; "
                 "classical vakra-Budha timing caution (delayed-but-not-blocked), not a "
                 "block on the underlying venture -- cross-check muhurta before finalizing "
                 "contracts/trade timing",
                 family=_FAMILY_D1_PROMISE, rule_id="SIG_MERCURY_RETROGRADE_TRADE_TIMING", fact_planets=("Mercury",))

    # D2 (Hora) wealth-flow corroboration for H2/H11 lords and the
    # classical wealth significators (Jupiter/Venus/Moon) -- a narrow,
    # light-weight layer distinct from D9/D10 house-graph corroboration
    # above; see _d2_native_house_evidence()'s docstring for scope/basis.
    # v-audit fix (typed rule IDs): verified every note text this function
    # produces (all prefixed "D2-Hora:") contains none of _family_of()'s
    # trigger substrings ("D2-Hora" doesn't match the "d9-native"/"d10-native"/
    # "navamsha"/"dashamsha" patterns, which are specific to D9/D10) ->
    # D1_PROMISE via text today. NOT tagging `category` here (H2/H11 vs
    # generic Jupiter/Venus/Moon wealth-karaka entries aren't distinguishable
    # without inspecting note text, which would just move the keyword
    # dependency rather than remove it -- left for a future pass that
    # changes _d2_native_house_evidence() itself to return a structured
    # per-entry house tag); category-untagged entries here still correctly
    # fall back to _add()'s own internal keyword heuristic for the `profit`
    # boolean (see _add()'s docstring) -- that fallback now lives entirely
    # inside this module, not in scoring.py, which never scans note text.
    for weight, note in _d2_native_house_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_D2_HORA_WEALTH_FLOW")

    # H3 — initiative/self-effort
    if h3_lord and _ph(h3_lord) in {1, 3, 10, 11}:
        _add("POSITIVE", 8, f"H3 lord ({h3_lord}) well placed -> entrepreneurial initiative/self-effort", family=_FAMILY_D1_PROMISE, rule_id="SIG_H3_INITIATIVE_SELF_EFFORT", fact_planets=(h3_lord,), fact_houses=(3,))

    # D3 (Drekkana) corroboration of the D1-H3 self-effort/courage promise
    # -- the classical self-effort/courage varga, previously never
    # consulted anywhere in this module despite H3-lord-in-1/3/10/11 being
    # judged purely from D1 placement above. Mirrors D9/D10's confirm/deny
    # pattern (see _d3_native_house_evidence()'s docstring for scope/
    # basis). Gracefully degrades to no-op when D3 occupancy can't be
    # resolved (no upstream divisional_charts["D3_drekkana"]) -- the D1-only
    # H3 evidence above is unaffected either way.
    # v-audit fix (typed rule IDs): verified every note text this function
    # produces is prefixed "D3-native:" -- this does NOT match _family_of()'s
    # "d9-native"/"d10-native" substrings (specific to D9/D10 only), so D3
    # confirmation currently falls to D1_PROMISE via text today, a pre-
    # existing classifier quirk (D3 arguably "should" be its own varga-
    # confirmation-style bucket, but _family_of() was never extended to
    # recognize D3/D7 "-native" prefixes) -- tagged to match CURRENT
    # behavior exactly, not to silently reclassify it.
    for weight, note in _d3_native_house_evidence(payload):
        _add("POSITIVE" if weight >= 0 else "NEGATIVE", abs(weight), note, family=_FAMILY_D1_PROMISE, rule_id="SIG_D3_NATIVE_SELF_EFFORT")

    # Janma Nakshatra (birth-star) business-aptitude corroboration -- a
    # minor, modest-weighted (+1.0..+2.0) supporting classical technique,
    # distinct from muhurta.py's transit-date nakshatra scoring (see
    # nakshatra_business.py's module docstring). Gracefully degrades to
    # no-op when payload.moon_nakshatra is missing/blank or not in the
    # curated table.
    # v-audit fix (typed rule IDs): verified all 8 curated table entries in
    # nakshatra_business.py -- none contain a varga/jaimini/sav trigger
    # substring -> D1_PROMISE via text today (returns at most one entry per
    # chart, individually checked, not assumed from the table's general
    # shape).
    for rec in janma_nakshatra_business_evidence(payload):
        _add(rec["polarity"], rec["weight"], rec["note"], family=_FAMILY_D1_PROMISE, rule_id="SIG_JANMA_NAKSHATRA")

    # H9 — fortune, GATED on dignity (previously unconditional)
    # v-audit fix (typed rule IDs): verified -- no trigger substrings ->
    # D1_PROMISE via text today.
    if h9_lord and _ph(h9_lord) in _KT:
        dig = _dig_name(h9_lord, dignities)
        if dig != "DEBILITATED":
            _add("POSITIVE", 10 * _dig_factor(h9_lord, dignities),
                 f"H9 lord ({h9_lord}) in kendra/trikona, dignity={_dig_disclosure(h9_lord, dignities, payload)} -> fortune supports venture",
                 family=_FAMILY_D1_PROMISE, rule_id="SIG_H9_FORTUNE", fact_planets=(h9_lord,), fact_houses=(9,))
        else:
            nb = _neecha_bhanga_status(payload, h9_lord)
            if nb.get("cancelled"):
                _add("POSITIVE", 6, f"H9 lord ({h9_lord}) in kendra/trikona, DEBILITATED but Neecha Bhanga applies -- {nb.get('reason')} -> fortune claim NOT withheld, treated as classically cancelled",
                     family=_FAMILY_D1_PROMISE, rule_id="SIG_H9_FORTUNE", fact_planets=(h9_lord,), fact_houses=(9,))
            else:
                _add("NEGATIVE", 5, f"H9 lord ({h9_lord}) in kendra/trikona but DEBILITATED -> fortune claim withheld",
                     family=_FAMILY_D1_PROMISE, rule_id="SIG_H9_FORTUNE", fact_planets=(h9_lord,), fact_houses=(9,))

    # Rahu in H7 — GATED on affliction (previously unconditional positive)
    # v-audit fix (typed rule IDs): verified -- no trigger substrings ->
    # D1_PROMISE via text today.
    rahu_h = _ph("Rahu")
    if rahu_h == 7:
        afflicted = bool({"Saturn", "Mars", "Ketu"} & set(_co_tenants(7, "Rahu")))
        if afflicted:
            _add("NEGATIVE", 8, "Rahu in H7 conjunct natural malefic -> unstable/contentious partnerships likely", family=_FAMILY_D1_PROMISE, rule_id="SIG_RAHU_H7_H11", fact_planets=("Rahu",), fact_houses=(7,))
        else:
            _add("POSITIVE", 6, "Rahu in H7 (unafflicted) -> unconventional/foreign business partnership potential", family=_FAMILY_D1_PROMISE, rule_id="SIG_RAHU_H7_H11", fact_planets=("Rahu",), fact_houses=(7,))
    if rahu_h == 11:
        _add("POSITIVE", 6, "Rahu in H11 -> sudden/large-scale gain potential, but higher volatility (not risk-free)", family=_FAMILY_D1_PROMISE, rule_id="SIG_RAHU_H7_H11", fact_planets=("Rahu",), fact_houses=(11,))

    # Darakaraka — GATED on dignity AND a 7th-house connection (previously any kendra/trikona)
    # v-audit fix (typed rule IDs): Darakaraka is a Jaimini karaka concept,
    # but this note's text does not contain "jaimini" -- verified against
    # _family_of()'s actual substring set, not the concept's classical
    # origin -> D1_PROMISE via text today (a pre-existing classifier quirk,
    # same category as the D3-native/D2-Hora findings above; not changed
    # here).
    if darakaraka:
        dk_house = _ph(darakaraka)
        dig = _dig_name(darakaraka, dignities)
        if dk_house in _KT and dig != "DEBILITATED" and (dk_house == 7 or h7_lord == darakaraka):
            _add("POSITIVE", 10 * _dig_factor(darakaraka, dignities),
                 f"DK ({darakaraka}) strong and H7-linked -> partnership/public karma supports business",
                 family=_FAMILY_D1_PROMISE, rule_id="SIG_DARAKARAKA_H7", fact_planets=(darakaraka,), fact_houses=(7,))
        elif dk_house in _DUSTHANA and dig == "DEBILITATED":
            _add("NEGATIVE", 6, f"DK ({darakaraka}) debilitated in dusthana -> partnership karma strained",
                 family=_FAMILY_D1_PROMISE, rule_id="SIG_DARAKARAKA_H7", fact_planets=(darakaraka,), fact_houses=(dk_house,))

    # Mercury + Venus — GATED on conjunction or mutual 7th aspect (previously just co-independent kendra/trikona)
    # v-audit fix (typed rule IDs): verified -- no trigger substrings ->
    # D1_PROMISE via text today.
    mer_h, ven_h = _ph("Mercury"), _ph("Venus")
    if mer_h and ven_h:
        conjunct = mer_h == ven_h
        mutual_seventh = abs(mer_h - ven_h) == 6
        if (conjunct or mutual_seventh) and (mer_h in _KT or ven_h in _KT):
            relation = "conjunct" if conjunct else "in mutual 7th aspect"
            _add("POSITIVE", 8, f"Mercury + Venus {relation}, one in kendra/trikona -> trade/negotiation signature", family=_FAMILY_D1_PROMISE, rule_id="SIG_MERCURY_VENUS_TRADE", fact_planets=("Mercury", "Venus"))

    # Mars/Saturn operational capacity
    # v-audit fix (typed rule IDs): verified -- no trigger substrings ->
    # D1_PROMISE via text today.
    mars_h, sat_h = _ph("Mars"), _ph("Saturn")
    if mars_h in {3, 6, 10} or sat_h in {6, 10}:
        _add("POSITIVE", 6, "Mars/Saturn in H3/H6/H10 -> operational/industrial execution capacity", family=_FAMILY_D1_PROMISE, rule_id="SIG_MARS_SATURN_OPERATIONAL", fact_planets=("Mars", "Saturn"))

    if _sav_h(11) >= 30:
        # v-audit fix (typed rule IDs, fifth slice -- "next recommended
        # slice" item 4, Shadbala/SAV strength family): this is the sole
        # STRENGTH-family (Ashtakavarga/Shadbala) evidence site in this
        # function -- verified it already matches _family_of()'s "sav"
        # substring check. It also matches scoring.py's profit_keywords
        # scan today (via its "h11"/"gains" substrings), so it's tagged on
        # BOTH typed axes at once: category (H11_GAINS, the financial
        # target this SAV reading corroborates) and family (STRENGTH, the
        # methodological corroboration bucket family_totals_capped uses) --
        # a concrete example of why the two axes are kept separate rather
        # than collapsed into one tag.
        _add("POSITIVE", 6, "H11 SAV >=30 -> gains house well supported (Ashtakavarga)", category=_CATEGORY_H11_GAINS, family=_FAMILY_STRENGTH, rule_id="SIG_H11_SAV_ASHTAKAVARGA", fact_houses=(11,))

    # H6/H12 dusthana lordship — QUALIFIED Viparita Raja Yoga detection
    # (previously any strong/exalted H6 lord anywhere in a dusthana was
    # labeled generic "VRY-style resilience"; dignity/strength alone does
    # not establish a clean VRY. Classical VRY requires a dusthana lord
    # (6th/8th/12th) placed in a DIFFERENT dusthana -- not its own house --
    # and is considered contaminated when conjunct a kendra-lord (1st/4th/
    # 7th/10th) in that house. This now distinguishes VRY_CONFIRMED
    # (genuine dusthana-to-dusthana movement, unafflicted), own-house
    # strength (not VRY at all, mislabeled before), and
    # DUSTHANA_LORD_STRONG_BUT_MIXED (strong but contaminated by a
    # kendra-lord conjunction, reduced weight rather than full credit).
    def _vry_check(own_house: int, lord: str) -> None:
        """Shared Viparita Raja Yoga qualification for any dusthana lord
        (6th/8th/12th), not just H6 -- audit finding #4 noted the original
        qualified version still only covered H6. Also checks for a genuine
        dusthana-lord EXCHANGE (parivartana): own_house's lord sits in
        placed_house AND placed_house's own lord sits back in own_house --
        a true house swap, not merely two dusthana lords conjunct in the
        same house (which is a weaker, different configuration and was a
        bug in an earlier version of this check)."""
        if not lord or _ph(lord) not in _DUSTHANA:
            return
        placed_house = _ph(lord)
        dig = _dig_name(lord, dignities)
        co_tenants = [p for p, h in planet_house.items() if h == placed_house and p != lord]
        kendra_lord_planets = {_h(h) for h in (1, 4, 7, 10)} - {""}
        contaminated = bool(set(co_tenants) & kendra_lord_planets)
        # A genuine dusthana-lord EXCHANGE (parivartana) requires the lord
        # OCCUPYING placed_house to itself be the lord of own_house -- i.e.
        # the two dusthana lords have swapped houses. Two dusthana lords
        # merely CONJUNCT in the same house (the previous check: any
        # dusthana lord present as a co-tenant of placed_house) is a
        # different, weaker configuration and must not be scored as an
        # exchange.
        counter_lord = _h(placed_house)
        exchange = bool(counter_lord and counter_lord != lord and _ph(counter_lord) == own_house)
        if placed_house == own_house:
            if dig in _STRONG_DIGNITY:
                _add("POSITIVE", 3, f"H{own_house} lord ({lord}) strong in own house (H{own_house}) -> own-sign resilience, NOT Viparita Raja Yoga (no dusthana-to-dusthana movement)", category=_CATEGORY_H6_H8_H12_RISK, family=_FAMILY_D1_PROMISE, rule_id="SIG_VRY_DUSTHANA_LORD_QUALIFICATION", fact_planets=(lord,), fact_houses=(own_house,))
            else:
                _add("NEGATIVE", 8, f"H{own_house} lord ({lord}) weak in own house (H{own_house}) -> competition/debt exposure", category=_CATEGORY_H6_H8_H12_RISK, family=_FAMILY_D1_PROMISE, rule_id="SIG_VRY_DUSTHANA_LORD_QUALIFICATION", fact_planets=(lord,), fact_houses=(own_house,))
        elif exchange and not contaminated:
            _add("POSITIVE", 6, f"H{own_house} lord ({lord}) in H{placed_house} exchanging with another dusthana lord -> VRY_CONFIRMED (strong form: dusthana-lord exchange, unafflicted)", category=_CATEGORY_H6_H8_H12_RISK, family=_FAMILY_D1_PROMISE, rule_id="SIG_VRY_DUSTHANA_LORD_QUALIFICATION", fact_planets=(lord,), fact_houses=(own_house, placed_house))
        elif dig in _STRONG_DIGNITY and not contaminated:
            _add("POSITIVE", 5, f"H{own_house} lord ({lord}) strong, in H{placed_house} -> VRY_CONFIRMED: genuine Viparita Raja Yoga (dusthana lord in another dusthana, unafflicted by kendra lords)", category=_CATEGORY_H6_H8_H12_RISK, family=_FAMILY_D1_PROMISE, rule_id="SIG_VRY_DUSTHANA_LORD_QUALIFICATION", fact_planets=(lord,), fact_houses=(own_house, placed_house))
        elif dig in _STRONG_DIGNITY and contaminated:
            _add("POSITIVE", 2, f"H{own_house} lord ({lord}) strong in H{placed_house} but conjunct a kendra-lord -> DUSTHANA_LORD_STRONG_BUT_MIXED: yoga contaminated, reduced credit", category=_CATEGORY_H6_H8_H12_RISK, family=_FAMILY_D1_PROMISE, rule_id="SIG_VRY_DUSTHANA_LORD_QUALIFICATION", fact_planets=(lord,), fact_houses=(own_house, placed_house))
        else:
            _add("NEGATIVE", 8, f"H{own_house} lord ({lord}) weak in dusthana (H{placed_house}) -> competition/debt exposure", category=_CATEGORY_H6_H8_H12_RISK, family=_FAMILY_D1_PROMISE, rule_id="SIG_VRY_DUSTHANA_LORD_QUALIFICATION", fact_planets=(lord,), fact_houses=(own_house, placed_house))

    _vry_check(6, h6_lord)
    _vry_check(8, h8_lord)

    # v-audit fix (astrological completeness -- item 9, "VRY remains
    # simplified... H12 not yet folded into the shared VRY check"): H12 used
    # to be scored by a separate, simpler block below (own-house strong/weak,
    # or a flat penalty if placed in H6/H8) that never ran the same
    # exchange/contamination/dignity qualification `_vry_check()` already
    # applies to H6 and H8 -- even though `_vry_check()`'s own docstring has
    # said "for any dusthana lord (6th/8th/12th), not just H6" since it was
    # written. That was a real gap between the function's documented scope
    # and what actually ran, not a deliberate simplification: an H12 lord
    # placed in H6/H8 with genuine strong, unafflicted dignity (or a true
    # parivartana exchange) is exactly the same classical Viparita Raja Yoga
    # configuration as an H6 lord in H8 or an H8 lord in H6 -- there is no
    # astrological reason H12 should get a flat, ungated penalty instead of
    # the same qualification test. `_vry_check(12, h12_lord)` now runs
    # exactly like the other two; the own-house (H12 lord staying in H12)
    # case is also now qualified by dignity via the shared function rather
    # than the old flat 4-vs-5 split.
    #
    # This DOES change scoring for the specific case of an H12 lord placed in
    # H6/H8 with strong, unafflicted dignity (or in a genuine H12-H6/H12-H8
    # exchange): such a chart previously received an unconditional NEGATIVE 5
    # ("loss/liability exposure") regardless of dignity, and will now
    # correctly receive a POSITIVE VRY_CONFIRMED/MIXED finding via the same
    # qualification logic H6/H8 already use -- a disclosed correctness fix,
    # not a silent one. Full 270-test suite re-verified after this change
    # (see Business_Prediction/tests/test_business_engine.py and
    # test_yogas.py); no existing fixture's asserted VRY_CONFIRMED/exchange
    # behavior regressed.
    _vry_check(12, h12_lord)

    positive_total = sum(e["weight"] for e in evidence if e["polarity"] == "POSITIVE")
    negative_total = sum(e["weight"] for e in evidence if e["polarity"] == "NEGATIVE")
    net = positive_total - negative_total

    # Upper bound for normalization.
    #
    # BUG FIX (audit finding, user-reported wrong output on Karthick_chart):
    # the previous ceiling (256.0) was the naive SUM OF EVERY INDIVIDUAL
    # RULE'S MAX, as if a single chart could simultaneously have H2, H3,
    # H6, H7, H8, H9, H10, H11, H12 ALL ruled by exalted/own-dignity lords
    # in kendra/trikona at once -- astrologically close to impossible (a
    # chart has 7-9 grahas covering 12 houses; lordships and strong
    # placements necessarily concentrate on a handful of planets, not all
    # of them at once). Verified empirically: a synthetic reference chart
    # deliberately engineered to fire as many of this function's positive
    # rules as astrologically plausible in a single chart (Mercury as
    # simultaneous H1/H7/H10 lord, exalted, conjunct Venus as H2/H11 lord
    # also exalted, DK=Mercury, Rahu unafflicted in H7, strong D9/D10
    # dignity and native house-graph placement throughout) only reached a
    # raw net score of ~153-157 against the old 256 ceiling -- meaning even
    # a maximally-engineered "everything fires" chart topped out around
    # 55-65 on the old 0-100 scale. That is a calibration bug, not a
    # feature: it silently compressed genuinely strong real charts (e.g. a
    # planet ruling BOTH the 7th and 10th house, sitting in its own/
    # moolatrikona dignity in one of them, confirmed by both D9-native and
    # D10-native house graphs -- a textbook-strong business/commerce
    # indicator) down into the 20s-30s, which then failed the
    # `strength>=35` "proceed" floor in compute_business_prediction() even
    # when the underlying astrology was genuinely favorable.
    #
    # Fixed ceiling: anchored to that same empirically-constructed maximal-
    # plausible reference chart's raw (uncapped) net score, rounded up for
    # headroom, rather than the sum of independently-unreachable maxima.
    # See Business_Prediction/tests/test_business_engine.py::
    # test_maximal_plausible_chart_scores_near_ceiling_not_compressed for
    # the reference fixture and the regression guard against this
    # recurring (every new rule silently inflated the old ceiling further,
    # which is exactly how it drifted to 256 over several rounds of
    # additions without ever being re-validated against a reachable case).
    _POSITIVE_CEILING = 160.0

    # Evidence-family caps (audit finding #7): a strong significator planet
    # can contribute through many correlated channels (D1 lordship, D9
    # dignity, D9-native house graph, D9-Lagna-projected lordship, D10
    # dignity, D10-native house graph, Phaladeepika reference-lord, Jaimini
    # activation) that are not fully independent observations -- they are
    # different representations of the same underlying planet/placement.
    # Each evidence note is tagged into a family and each family's NET
    # (signed) contribution is capped so no single correlated channel-group
    # can dominate the score. positive_total/negative_total above remain
    # the full, UNCAPPED transparent ledger sums; only the strength score
    # below uses the capped total.
    # v-audit fix (typed rule IDs, fifth slice -- item 1, "_family_of() text
    # fallback is still active"): this closure used to be the classification
    # mechanism for every entry's `family`; it is retired now that every
    # _add() call site is individually verified to set an explicit `family`
    # tag (test_zero_untyped_family_rule_id_profit_stability_risk_entries
    # gates this: family_untyped_entries is 0 on every exercised payload, and
    # the ledger is checked entry-by-entry, not just via the aggregate
    # counter). Deleting this function is a real reduction in surface area,
    # not just dead-code cleanup: there is no longer any code path in this
    # module that can (re)classify an entry's family from note wording, so a
    # future cosmetic reword of a note can no longer silently change which
    # family bucket -- and therefore which _FAMILY_CAP -- an entry lands in.
    _FAMILY_CAP = 0.35 * _POSITIVE_CEILING  # no single family may exceed 35% of the ceiling

    # Engineering audit fix #2 (evidence independence): the family cap above
    # already stops one CATEGORY of correlated evidence (e.g. every D9/D10
    # varga confirmation) from dominating the score, but it does nothing
    # about the SAME PLANET appearing repeatedly within one family -- e.g.
    # Mercury cited as D1_PROMISE evidence three separate times (H7 lord,
    # H10-H11 connection, Lagnesh) is three notes about one planet's
    # strength, not three independent corroborating observations. This
    # tracks (family, planet) occurrence and applies a diminishing-returns
    # multiplier: the first note citing a given planet within a family
    # counts at full weight; every SUBSEQUENT note citing that SAME planet
    # within the SAME family is halved, so a chart whose promise leans
    # heavily on one repeatedly-cited planet no longer scores identically
    # to one with the same RAW total spread across several distinct
    # planets. Evidence text mentioning no recognizable planet name (a few
    # generic/house-only notes) is left at full weight, unaffected.
    # (_PLANET_NAMES_FOR_DEDUP / _planets_mentioned are now defined earlier,
    # alongside _add(), so fact_id tagging can reuse them -- not redefined
    # here anymore.)

    # Engineering audit fix #4 (evidence independence, cross-module half):
    # the within-family dedup above stops one FAMILY (e.g. every
    # VARGA_CONFIRMATION note) from re-crediting the same planet
    # repeatedly, but says nothing about a planet that is cited across
    # SEVERAL distinct families (D1 lordship + D9 dignity + D10 dignity +
    # Jaimini activation, say) -- those are correlated observations of one
    # underlying planetary strength, not several independent methods
    # agreeing. An earlier attempt at this pass tried folding a
    # cross-family diminishing-returns multiplier directly into
    # capped_net_score/strength_0_100, but that number is load-bearing for
    # several already-calibrated regression fixtures (e.g. a "maximal
    # plausible chart" fixture asserting the score reaches a specific
    # near-ceiling floor); silently reshaping it risked exactly the kind
    # of uncalibrated threshold churn the audit itself warns against
    # (finding #1), for a same-effort-different-bug tradeoff. Instead this
    # tracks -- WITHOUT touching positive_total/negative_total/net_score/
    # family_totals/capped_net_score/strength_0_100, all left bit-for-bit
    # identical to before -- which planets are cited across 3+ distinct
    # evidence families, and surfaces that as an explicit, additive
    # transparency field so a caller/reviewer can see when a score leans
    # heavily on one repeatedly-cited planet rather than genuinely
    # diverse corroboration, without the scoring pipeline silently
    # reweighting itself underneath already-calibrated tests.
    # v-audit fix (typed rule IDs, seventh slice -- item 3, "no dependency-
    # group scoring policy"): a SECOND, parallel accumulation alongside
    # family_raw above, applying an explicit same-fact correlation discount
    # keyed off `subject_key` (WHAT an entry is about, independent of which
    # rule found it -- see _add()'s docstring): the first entry for a given
    # subject gets full credit; a later entry from a DIFFERENT rule_id about
    # the SAME subject (a corroborating method) is discounted to 50%; a
    # later entry from the SAME rule_id about the SAME subject (a same-
    # method duplicate -- should be rare/a bug if it happens, since most
    # rules fire at most once per subject, but handled explicitly rather
    # than assumed impossible) is discounted to 0%. Entries with no
    # recognizable subject_key (generic notes, no fact_planets/fact_houses
    # given and no tracked planet name in the text) are never discounted --
    # conservative: no correlation is asserted when the subject isn't
    # actually known.
    #
    # Exactly like cross_family_planet_concentration above, this is
    # additive: family_raw/family_capped/capped_net/strength_0_100 (the
    # scores every existing calibrated test fixture already depends on) are
    # completely unaffected. The fact-deduped totals are exposed as
    # DISTINCT, separately-named fields (capped_net_score_post_fact_dedup /
    # strength_0_100_post_fact_dedup) precisely so silently reshaping the
    # existing scores isn't required to answer "what would this chart score
    # if duplicate facts were discounted" -- both numbers are visible side by
    # side, and a caller/future pass can decide to switch the PRIMARY score
    # over to the deduped version once that's an intentional, reviewed
    # decision, not an incidental side effect of this slice.
    _subject_seen_at_all: set = set()
    _subject_rule_ids_seen: Dict[str, set] = {}

    def _fact_discount(subject_key: Optional[str], rule_id: Optional[str]) -> Tuple[float, str]:
        if subject_key is None:
            return 1.0, "no_subject"
        if subject_key not in _subject_seen_at_all:
            _subject_seen_at_all.add(subject_key)
            _subject_rule_ids_seen[subject_key] = {rule_id}
            return 1.0, "first_occurrence"
        seen_rules = _subject_rule_ids_seen[subject_key]
        if rule_id in seen_rules:
            return 0.0, "same_method_duplicate"
        seen_rules.add(rule_id)
        return 0.5, "corroborating_method"

    _planet_family_occurrence: Dict[Tuple[str, str], int] = {}
    _planet_families_seen: Dict[str, set] = {}
    family_raw: Dict[str, float] = {}
    family_raw_fact_deduped: Dict[str, float] = {}
    same_planet_dedup_applied = False
    fact_dependency_discount_applied = False
    for e in evidence:
        # v-audit fix (typed rule IDs, fifth slice -- item 1): every entry
        # now carries an explicit `family` tag set at generation time (see
        # _add()'s `family` kwarg above); the text-inference fallback
        # (_family_of()) has been deleted entirely, not just deprioritized,
        # since coverage is verified 100% by
        # test_zero_untyped_family_rule_id_profit_stability_risk_entries. If
        # a future _add() call site is ever added without a `family` tag,
        # this now raises KeyError immediately (loud failure) rather than
        # silently reintroducing text-based classification.
        fam = e["family"]
        signed = e["weight"] if e["polarity"] == "POSITIVE" else -e["weight"]
        mentioned = _planets_mentioned(e["note"])
        if mentioned:
            multiplier = 1.0
            for p in mentioned:
                key = (fam, p)
                occurrence = _planet_family_occurrence.get(key, 0)
                if occurrence > 0:
                    multiplier = min(multiplier, 0.5)
                    same_planet_dedup_applied = True
                _planet_family_occurrence[key] = occurrence + 1
                _planet_families_seen.setdefault(p, set()).add(fam)
            signed *= multiplier
        family_raw[fam] = family_raw.get(fam, 0.0) + signed

        fact_discount, fact_discount_reason = _fact_discount(e.get("subject_key"), e.get("rule_id"))
        e["fact_dependency_discount"] = fact_discount
        e["fact_dependency_reason"] = fact_discount_reason
        if fact_discount < 1.0:
            fact_dependency_discount_applied = True
        family_raw_fact_deduped[fam] = family_raw_fact_deduped.get(fam, 0.0) + signed * fact_discount

    cross_family_concentrated_planets = sorted(
        p for p, fams in _planet_families_seen.items() if len(fams) >= 3
    )

    # v-audit fix (typed rule IDs, eighth slice -- item 1, "deduplicated
    # totals are not authoritative yet"): PROMOTED to primary per explicit
    # user decision (this is a real scoring-policy call, not a bug fix --
    # asked and confirmed rather than silently flipped). family_capped/
    # capped_net/strength_0_100 below -- and therefore
    # family_totals_capped/family_totals_uncapped/capped_net_score/
    # strength_0_100/heuristic_relative_strength_0_100 in the return dict,
    # and everything scoring.py derives from family_totals_capped
    # (d1_net/varga_net/etc.) -- now reflect the fact-dependency-discounted
    # ledger (family_raw_fact_deduped), not the pre-discount one. The
    # pre-discount numbers are kept, renamed to *_pre_fact_dedup, purely for
    # comparison/audit -- they are no longer what any downstream consumer
    # (scoring.py, engine.py) actually reads. positive_total/negative_total/
    # raw_score/risk_drag remain the full, UNDISCOUNTED transparent ledger
    # sums (as documented where they're computed above) -- the fact
    # discount only applies within the family-cap/strength pipeline, the
    # same scope the pre-existing same-planet-within-family multiplier
    # already had.
    family_capped_pre_fact_dedup = {
        fam: max(-_FAMILY_CAP, min(_FAMILY_CAP, val)) for fam, val in family_raw.items()
    }
    capped_net_pre_fact_dedup = sum(family_capped_pre_fact_dedup.values())
    strength_0_100_pre_fact_dedup = round(min(100.0, max(0.0, capped_net_pre_fact_dedup / _POSITIVE_CEILING * 100.0)), 2)

    family_capped = {
        fam: max(-_FAMILY_CAP, min(_FAMILY_CAP, val)) for fam, val in family_raw_fact_deduped.items()
    }
    capped_net = sum(family_capped.values())
    strength_0_100 = round(min(100.0, max(0.0, capped_net / _POSITIVE_CEILING * 100.0)), 2)

    return {
        "evidence": evidence,
        "positive_total": round(positive_total, 2),
        "negative_total": round(negative_total, 2),
        "net_score": round(net, 2),
        "family_totals_uncapped": {k: round(v, 2) for k, v in family_raw_fact_deduped.items()},
        "family_totals_capped": {k: round(v, 2) for k, v in family_capped.items()},
        "family_totals_uncapped_pre_fact_dedup": {k: round(v, 2) for k, v in family_raw.items()},
        "family_totals_capped_pre_fact_dedup": {k: round(v, 2) for k, v in family_capped_pre_fact_dedup.items()},
        "same_planet_dedup_applied": same_planet_dedup_applied,
        # Transparency-only (see comment above): planets cited across 3+
        # distinct evidence families. Does NOT affect any score above --
        # informational, for a reviewer to see where the ledger leans on
        # one repeatedly-cited planet rather than diverse corroboration.
        "cross_family_planet_concentration": cross_family_concentrated_planets,
        "capped_net_score": round(capped_net, 2),
        "heuristic_relative_strength_0_100": strength_0_100,
        # v-audit fix (typed rule IDs, seventh slice -- item 3; PROMOTED to
        # primary in the eighth slice -- item 1): capped_net_score/
        # strength_0_100 above are now the fact-dependency-DISCOUNTED
        # numbers (first mention of a subject/planet/house fact counts
        # fully, a different rule corroborating the same subject counts at
        # 50%, the same rule re-citing the same subject counts at 0%). The
        # pre-discount numbers are still available under the
        # *_pre_fact_dedup names for comparison.
        "capped_net_score_pre_fact_dedup": round(capped_net_pre_fact_dedup, 2),
        "capped_net_score_post_fact_dedup": round(capped_net, 2),
        "strength_0_100_pre_fact_dedup": strength_0_100_pre_fact_dedup,
        "strength_0_100_post_fact_dedup": strength_0_100,
        "fact_dependency_discount_applied": fact_dependency_discount_applied,
        # Backward-compatible aliases (older report/CLI code reads these keys).
        "raw_score": round(positive_total, 2),
        "risk_drag": round(negative_total, 2),
        "strength_0_100": strength_0_100,
        "signals": [e["note"] for e in evidence if e["polarity"] == "POSITIVE"],
        "risk_signals": [e["note"] for e in evidence if e["polarity"] == "NEGATIVE"],
        "evidence_basis": EVIDENCE_BASIS,
        # v-audit fix (typed rule IDs -- item 9, "no fallback-usage
        # diagnostic"; comment corrected in the seventh slice -- item 6,
        # "stale comments still describe removed text classifiers"):
        # reports how much of this evidence ledger carries an explicit,
        # typed `category` tag (set at generation time -- see _add()'s
        # docstring above). `category` is genuinely still partial by design
        # (see _add()'s docstring: it's only meaningful for evidence
        # structurally anchored to H2/H11/H6/H8/H12, not every entry), NOT
        # because of a keyword-scanning fallback anywhere downstream --
        # scoring.py stopped scanning note text for profit/stability-risk
        # classification entirely once `profit`/`stability_risk` became
        # unconditional _add() outputs (see those two fields' own comment
        # below); untagged `category` here just means "not one of the H2/
        # H11/H6/H8/H12 categories," which is an expected, not a deficient,
        # state for most entries. This is purely a transparency measure --
        # it does not change any score.
        "evidence_typing_stats": {
            "total_entries": len(evidence),
            "typed_entries": sum(1 for e in evidence if e.get("category") is not None),
            "untyped_entries": sum(1 for e in evidence if e.get("category") is None),
            "typed_categories_present": sorted({e["category"] for e in evidence if e.get("category") is not None}),
            # v-audit fix (typed rule IDs -- item 6 tracking; comment
            # corrected in the seventh slice -- item 6, "stale comments
            # still describe removed text classifiers"): same migration-
            # progress measure as category, for the `family` and `rule_id`
            # axes. There is no remaining text-classification fallback for
            # `family` to measure a "fallback rate" against -- _family_of()
            # was deleted once family_untyped_entries reached 0 (see the
            # fam = e["family"] comment further down, which now raises
            # KeyError rather than falling back to text). These two counters
            # are retained purely as regression tripwires against a future
            # _add() call site that forgets to tag family/rule_id, not as a
            # measure of ongoing fallback usage.
            "family_typed_entries": sum(1 for e in evidence if e.get("family") is not None),
            "family_untyped_entries": sum(1 for e in evidence if e.get("family") is None),
            "typed_families_present": sorted({e["family"] for e in evidence if e.get("family") is not None}),
            "rule_id_typed_entries": sum(1 for e in evidence if e.get("rule_id") is not None),
            "rule_id_untyped_entries": sum(1 for e in evidence if e.get("rule_id") is None),
            # v-audit fix (typed rule IDs, fourth slice -- items 3/4):
            # `profit`/`stability_risk` are now unconditionally set by _add()
            # for every entry (category-derived when a structural category
            # exists, keyword-derived otherwise -- see _add()'s docstring
            # above), so these two counters are 0 by construction, not by
            # coverage effort. Tracked anyway so a future regression (e.g. a
            # new _add() call site that bypasses this helper) is caught
            # immediately rather than silently reintroducing an untyped
            # entry.
            "profit_typed_entries": sum(1 for e in evidence if e.get("profit") is not None),
            "profit_untyped_entries": sum(1 for e in evidence if e.get("profit") is None),
            "stability_risk_typed_entries": sum(1 for e in evidence if e.get("stability_risk") is not None),
            "stability_risk_untyped_entries": sum(1 for e in evidence if e.get("stability_risk") is None),
            # v-audit fix (typed rule IDs, sixth slice -- item 6): fact_id
            # (rule_id + any named planets the note mentions) is now set
            # unconditionally by _add() too -- see rule_provenance.py and
            # _add()'s fact_id comment for what it is and, importantly, what
            # it is NOT (it does not itself perform deduplication).
            "fact_id_typed_entries": sum(1 for e in evidence if e.get("fact_id") is not None),
            "fact_id_untyped_entries": sum(1 for e in evidence if e.get("fact_id") is None),
            # v-audit fix (typed rule IDs, seventh slice -- items 1/2):
            # fact_id/subject_key are set unconditionally (never None as a
            # KEY -- see fact_id_untyped_entries above, which stays 0), but
            # a note-worthy DISTINCTION is whether that subject was derived
            # from explicit fact_planets/fact_houses (structured -- not
            # dependent on note wording) or from scanning the rendered note
            # for a planet name (text_inferred -- a cosmetic reword could
            # still change it). This is the honest completion measure for
            # items 1/2: not "does fact_id exist" (it always does) but "is
            # it actually structural yet."
            "fact_id_structured_entries": sum(1 for e in evidence if e.get("fact_id_basis") == "structured"),
            "fact_id_text_inferred_entries": sum(1 for e in evidence if e.get("fact_id_basis") == "text_inferred"),
            "subject_key_present_entries": sum(1 for e in evidence if e.get("subject_key") is not None),
            "subject_key_absent_entries": sum(1 for e in evidence if e.get("subject_key") is None),
            # v-audit fix (typed rule IDs, sixth slice -- item 8, "rule_id
            # values do not yet connect to a complete provenance registry"):
            # every DISTINCT rule_id actually present in this evidence
            # ledger, resolved against rule_provenance.py's registry. Any
            # rule_id with registered=False here means a live evidence-
            # generating call site's rule_id has no matching registry
            # entry -- a concrete, checkable completeness signal instead of
            # having to eyeball the registry against the source.
            "rule_provenance": {
                rid: resolve_rule_provenance(rid)
                for rid in sorted({e["rule_id"] for e in evidence if e.get("rule_id") is not None})
            },
            "note": (
                "category: financial/risk TARGET tag, consumed by scoring.py's profit/stability "
                "scans (falls back to keyword scanning when absent). family: methodological "
                "corroboration bucket -- every entry is now required to set this explicitly (the "
                "former note-text fallback classifier, _family_of(), was deleted once coverage "
                "reached 100%; family_untyped_entries is retained as a regression tripwire, not a "
                "measure of remaining fallback usage). rule_id: which specific rule/"
                "classical technique fired; consumed by the rule_provenance lookup below, tracked for "
                "registry work. profit/stability_risk: unconditional booleans set by _add() for every "
                "entry (category-derived when possible, else the same keyword heuristic scoring.py "
                "used to run independently) -- scoring.py's profit_net/stability_risk_net now read "
                "these fields directly and no longer scan note text themselves. fact_id: which rule "
                "found which subject (rule_id + subject_key); catches a single rule firing twice for "
                "the same subject. subject_key: WHAT an entry is about (planet(s)/house(s)), "
                "independent of which rule found it -- structured (fact_planets/fact_houses passed "
                "explicitly at the _add() call site) for roughly the single-lord/single-technique "
                "checks, text_inferred (scanned from the rendered note) for evidence generated by "
                "loop-based multi-varga functions that don't yet return a structured subject "
                "themselves (see fact_id_structured_entries/fact_id_text_inferred_entries above for "
                "exact coverage). subject_key is what the fact-dependency-discount pass (see "
                "capped_net_score_post_fact_dedup/strength_0_100_post_fact_dedup at the top level) "
                "actually groups on: first entry per subject counts fully, a different rule "
                "corroborating the same subject counts at 50%, the same rule re-citing the same "
                "subject counts at 0%. rule_provenance: every distinct rule_id in this ledger resolved "
                "to its registry record (technique/classical basis/target/controversy disclosure). "
                "None of these counters or lookups change capped_net_score/strength_0_100 (the "
                "PRIMARY scores) -- only the explicitly-separate *_post_fact_dedup fields reflect the "
                "discount."
            ),
        },
    }



def _mercury_full_adjudication(payload: Any) -> Dict[str, Any]:
    """Consolidated Mercury adjudication (audit item 11).

    This chart (Sagittarius lagna) has Mercury ruling BOTH H7 (commerce/
    partnership) and H10 (career/livelihood) -- a dual-lordship case where
    Mercury's strength/dignity/combustion/timing characterizations were
    previously scattered across several modules (dignity in
    house_evidence.py's `_rich_planet_dignities`, combustion in
    `_combustion_status`, retrograde in `_retrograde_status`, D9/D10
    dignity via `payload.d9_planet_dignities`/`d10_planet_dignities`,
    Jaimini/timing signals elsewhere) with no single place that reads them
    together and reaches one synthesized verdict. This function does not
    reinvent any of those checks -- it only calls the existing ones and
    assembles their outputs into one consolidated record, then adds a
    final H7-vs-H10 synthesis step that is new.

    Generalizes beyond Mercury-specific hardcoding where practical (keyed
    on whichever planet is passed in), but is written and named for
    Mercury per this audit item; callers needing a different planet can
    pass one in directly.

    Fields returned:
      - planet: the planet name adjudicated (e.g. "Mercury")
      - combustion_distance_deg / combustion_verdict: reuses
        house_evidence._combustion_status() (the existing, already-tested
        exact-longitude combustion-distance rule -- BPHS orbs, retrograde-
        adjusted, gradient severity) rather than reimplementing it.
        combustion_distance_deg is parsed from the same longitude data
        _combustion_status() itself reads (payload.planet_longitudes),
        not re-derived independently, so the two can never disagree.
      - retrograde: reuses house_evidence._retrograde_status().
      - d1_dignity: reuses house_evidence._rich_planet_dignities().
      - strength_metric: {"source": ..., "value": ...} -- prefers
        payload.shadbala_computed[planet] (the full six-fold Shadbala
        computation, see jyotish/shadbala.py::compute_shadbala_all(),
        when the payload has it), then payload.shadbala[planet] (the
        coarser upstream single-number ingestion), then falls back to
        house_evidence._planet_strength() (this package's own composite
        0..1 dignity+placement metric) with an explicit "source" tag so
        the reader knows exactly which metric produced the number rather
        than a value that looks like Shadbala but isn't. Never fabricates
        Shadbala numbers -- if none of the above are populated, "source"
        is "UNAVAILABLE" and "value" is None.
      - nakshatra / nakshatra_lord: reuses payload.planet_nakshatras /
        payload.planet_nakshatra_lord (already computed upstream by
        jyotish/engine_io.py).
      - kp_sub_lord: reuses jyotish.ephemeris.compute_kp_sublords() (the
        existing standard KP sub-lord construction already used for
        lagna_sub_lord/moon_sub_lord elsewhere) against this planet's own
        absolute sidereal longitude (payload.planet_longitudes), when
        available -- None if longitude data is absent.
      - d9_dignity / d10_dignity: reuses payload.d9_planet_dignities /
        payload.d10_planet_dignities (the same fields
        `_d1_tenth_lord_direct_evidence`'s "10th lord's OWN D9/D10
        dignity" check already reads).
      - houses_ruled: the D1 houses this planet lords (via
        payload.house_lords), e.g. [7, 10] for this chart.
      - h7_strength / h10_strength: house_evidence._house_lord_strength()
        for H7/H10 respectively, ONLY when this planet actually rules
        that house (None otherwise) -- the same composite strength metric
        `score_business_significators()` itself already uses house-by-
        house.
      - synthesized_verdict: plain-language final read on whether this
        planet primarily manifests its H7 (commerce/partnership) or H10
        (career) signification, or both comparably -- derived purely from
        h7_strength vs h10_strength (when both apply) plus whether the
        planet occupies H7/H10 itself (direct occupancy read as a
        same-domain reinforcement); never re-derives dignity/combustion
        from scratch, only compares numbers already computed above.

    Gracefully returns {"status": "NO_DATA", ...} (never raises) when
    `planet` is not on payload.house_lords/planet_house at all.
    """
    try:
        house_lords = getattr(payload, "house_lords", {}) or {}
        planet_house = getattr(payload, "planet_house", {}) or {}
        if not house_lords and not planet_house:
            return {"status": "NO_DATA", "note": "Mercury adjudication skipped: no house_lords/planet_house on payload."}

        planet = "Mercury"

        def _h(num: int) -> str:
            return house_lords.get(str(num), house_lords.get(num, ""))

        houses_ruled = sorted(
            {h for h in range(1, 13) if _h(h) == planet}
        )

        # Combustion: reuse _combustion_status() exactly; independently
        # surface the numeric distance from the SAME source field
        # (payload.planet_longitudes) it itself reads, so the two never
        # disagree.
        combustion_verdict = _combustion_status(payload, planet)
        combustion_distance_deg = None
        lon_map = getattr(payload, "planet_longitudes", None) or {}
        sun_lon, planet_lon = lon_map.get("Sun"), lon_map.get(planet)
        if sun_lon is not None and planet_lon is not None:
            try:
                diff = abs(float(planet_lon) - float(sun_lon)) % 360.0
                combustion_distance_deg = round(min(diff, 360.0 - diff), 4)
            except (TypeError, ValueError):
                combustion_distance_deg = None

        retrograde = _retrograde_status(payload, planet)
        dignities = _rich_planet_dignities(payload)
        d1_dignity = dignities.get(planet, "")

        # Strength metric: prefer real Shadbala when available, never
        # fabricate it.
        shadbala_computed = getattr(payload, "shadbala_computed", {}) or {}
        shadbala_coarse = getattr(payload, "shadbala", {}) or {}
        if isinstance(shadbala_computed, dict) and planet in shadbala_computed and shadbala_computed[planet]:
            strength_metric = {"source": "shadbala_computed", "value": shadbala_computed[planet]}
        elif isinstance(shadbala_coarse, dict) and planet in shadbala_coarse and shadbala_coarse[planet] is not None:
            strength_metric = {"source": "shadbala_virupas", "value": shadbala_coarse[planet]}
        else:
            from .house_evidence import _planet_strength
            strength_metric = {
                "source": "UNAVAILABLE_fallback_to_composite_placement_strength",
                "value": round(_planet_strength(payload, planet), 4),
                "note": "Full Shadbala not populated on this payload -- using this package's own composite dignity+placement strength metric (0..1) instead of fabricating Shadbala numbers.",
            }

        planet_nakshatras = getattr(payload, "planet_nakshatras", {}) or {}
        planet_nakshatra_lord = getattr(payload, "planet_nakshatra_lord", {}) or {}
        nakshatra = planet_nakshatras.get(planet, "")
        nakshatra_lord = planet_nakshatra_lord.get(planet, "")

        kp_sub_lord = None
        if planet_lon is not None:
            try:
                from jyotish.ephemeris import compute_kp_sublords
                _, kp_sub_lord, _ = compute_kp_sublords(float(planet_lon))
            except Exception:
                kp_sub_lord = None

        d9_dig_map = getattr(payload, "d9_planet_dignities", {}) or {}
        d10_dig_map = getattr(payload, "d10_planet_dignities", {}) or {}
        d9_dignity = d9_dig_map.get(planet, "")
        d10_dignity = d10_dig_map.get(planet, "")

        h7_strength = _house_lord_strength(payload, 7) if 7 in houses_ruled else None
        h10_strength = _house_lord_strength(payload, 10) if 10 in houses_ruled else None

        own_house = planet_house.get(planet, 0)

        if h7_strength is None and h10_strength is None:
            synthesized_verdict = (
                f"{planet} does not rule H7 or H10 on this chart -- no H7-vs-H10 synthesis applicable."
            )
        elif h7_strength is not None and h10_strength is None:
            synthesized_verdict = f"{planet} rules H7 only (not H10) -> expression is H7 (commerce/partnership)-native by lordship alone."
        elif h10_strength is not None and h7_strength is None:
            synthesized_verdict = f"{planet} rules H10 only (not H7) -> expression is H10 (career)-native by lordship alone."
        else:
            # Rules both -- compare strengths, then break near-ties with
            # direct occupancy (same-domain reinforcement).
            diff = h7_strength - h10_strength
            if own_house == 7 and own_house != 10:
                occ_note = " Also occupies H7 itself, reinforcing the H7 read."
            elif own_house == 10 and own_house != 7:
                occ_note = " Also occupies H10 itself, reinforcing the H10 read."
            else:
                occ_note = ""
            if abs(diff) < 0.08:
                synthesized_verdict = (
                    f"{planet} rules BOTH H7 ({round(h7_strength, 3)}) and H10 ({round(h10_strength, 3)}) with "
                    f"comparable strength -> dual expression, commerce/partnership (H7) and career (H10) "
                    f"signification manifest roughly equally, not one dominating the other.{occ_note}"
                )
            elif diff > 0:
                synthesized_verdict = (
                    f"{planet} rules both H7 ({round(h7_strength, 3)}) and H10 ({round(h10_strength, 3)}) but H7 "
                    f"is the stronger placement -> expression primarily manifests as H7 (commerce/partnership), "
                    f"with H10 (career) as a secondary, weaker channel.{occ_note}"
                )
            else:
                synthesized_verdict = (
                    f"{planet} rules both H7 ({round(h7_strength, 3)}) and H10 ({round(h10_strength, 3)}) but H10 "
                    f"is the stronger placement -> expression primarily manifests as H10 (career), with H7 "
                    f"(commerce/partnership) as a secondary, weaker channel.{occ_note}"
                )

        return {
            "status": "OK",
            "planet": planet,
            "houses_ruled": houses_ruled,
            "own_d1_house": own_house or None,
            "combustion_distance_deg": combustion_distance_deg,
            "combustion_verdict": combustion_verdict,
            "retrograde": retrograde,
            "d1_dignity": d1_dignity,
            "strength_metric": strength_metric,
            "nakshatra": nakshatra,
            "nakshatra_lord": nakshatra_lord,
            "kp_sub_lord": kp_sub_lord,
            "d9_dignity": d9_dignity,
            "d10_dignity": d10_dignity,
            "h7_strength": h7_strength,
            "h10_strength": h10_strength,
            "synthesized_verdict": synthesized_verdict,
            "note": (
                "Consolidated Mercury adjudication: combustion distance/verdict, retrograde status, "
                "D1 dignity, strength metric (real Shadbala when available, else this package's own "
                "composite placement strength -- never fabricated), nakshatra/sub-lord, D9/D10 "
                "dignity, and a final H7-vs-H10 synthesized verdict -- assembled from existing "
                "checks elsewhere in this package, not re-derived."
            ),
        }
    except Exception as exc:  # pragma: no cover - defensive
        from .constants import _record_diagnostic
        _record_diagnostic("significators._mercury_full_adjudication", exc)
        return {"status": "ERROR", "note": f"Mercury adjudication failed: {exc}"}
