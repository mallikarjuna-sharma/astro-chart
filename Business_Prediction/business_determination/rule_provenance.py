"""business_determination.rule_provenance

v-audit fix (typed rule IDs, sixth slice -- item 8, "rule_id values do not
yet connect to a complete provenance registry"): a lookup table from each
`rule_id` significators.py's _add() call sites tag onto evidence (see that
module's docstring for the category/family/rule_id three-axis design) to a
short, honestly-scoped provenance record -- which technique/house-check it
is, which general classical concept it draws on, and an explicit disclosure
of how firm that classical grounding is.

Deliberately does NOT fabricate specific chapter/verse citations. This
codebase's own MATURITY STATEMENT (see scoring.py's module docstring)
already discloses that classical coverage here implements ONE engineered
reading of a named classical method, not a citation-verified doctrinal
consensus -- inventing precise verse numbers this module has not actually
verified against a primary source would be worse than not citing one at all
(a false-precision problem, not a completeness one). Where a technique has a
well-known named source (Phaladeepika ch.5, Jaimini karakas, KP sub-lord
theory, Ashtakavarga), that name is given; where a rule is this engine's own
house-connection heuristic rather than a named classical technique, it is
labeled as such rather than assigned an invented source.

This is read-only, additive metadata. Nothing here changes any score,
weight, or evidence classification -- it exists purely so a caller/reviewer
can answer "where did this rule_id come from" without reading source code.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Each record: technique (short human name), basis (classical source name, or
# "engine heuristic" when this is this codebase's own house-connection logic
# rather than a named classical doctrine), target (category axis this rule
# typically produces: profit / stability_risk / general), controversy (a
# one-line honest note on how settled/debatable this reading is).
RULE_PROVENANCE: Dict[str, Dict[str, str]] = {
    "SIG_COMBUSTION_CHECK": {
        "technique": "Combustion (Asta) proximity-to-Sun check",
        "basis": "Classical combustion (Asta) doctrine",
        "target": "general",
        "controversy": "Orb/severity thresholds and the dignity-leniency discount are this engine's own graduated model, not a single agreed classical formula.",
    },
    "SIG_H7_VENTURE_STRENGTH": {
        "technique": "H7 (partnership/venture house) lord strength",
        "basis": "Standard house-lord strength doctrine (bhava-adhipati bala)",
        "target": "general",
        "controversy": "Strength thresholds (>=0.6 / <0.35) are engine-defined cutoffs, not classical numeric standards.",
    },
    "SIG_H7_D9_CONFIRMATION": {
        "technique": "D9 (Navamsha) dignity confirmation of the H7 lord's D1 promise",
        "basis": "Navamsha as the classical confirmation/durability varga",
        "target": "general",
        "controversy": "Widely accepted that D9 confirms/denies D1 promise; the specific STRONG_DIGNITY/DEBILITATED cutoff set is this engine's simplification.",
    },
    "SIG_JAIMINI_RASI_DRISHTI_H1": {"technique": "Jaimini rasi drishti (whole-sign aspect) onto Lagna", "basis": "Jaimini rasi drishti doctrine", "target": "general", "controversy": "Rasi drishti's exact directional rules vary between Jaimini sub-traditions; this engine implements one reading."},
    "SIG_JAIMINI_RASI_DRISHTI_H7": {"technique": "Jaimini rasi drishti (whole-sign aspect) onto H7", "basis": "Jaimini rasi drishti doctrine", "target": "general", "controversy": "Rasi drishti's exact directional rules vary between Jaimini sub-traditions; this engine implements one reading."},
    "SIG_JAIMINI_RASI_DRISHTI_H10": {"technique": "Jaimini rasi drishti (whole-sign aspect) onto H10", "basis": "Jaimini rasi drishti doctrine", "target": "general", "controversy": "Rasi drishti's exact directional rules vary between Jaimini sub-traditions; this engine implements one reading."},
    "SIG_ARGALA_H1": {"technique": "Argala/Virodhargala onto Lagna", "basis": "Jaimini Argala doctrine", "target": "general", "controversy": "Which houses/planets can cancel (virodhargala) an argala is itself a debated sub-topic across Jaimini commentaries."},
    "SIG_ARGALA_H7": {"technique": "Argala/Virodhargala onto H7", "basis": "Jaimini Argala doctrine", "target": "general", "controversy": "Which houses/planets can cancel (virodhargala) an argala is itself a debated sub-topic across Jaimini commentaries."},
    "SIG_ARGALA_H10": {"technique": "Argala/Virodhargala onto H10", "basis": "Jaimini Argala doctrine", "target": "general", "controversy": "Which houses/planets can cancel (virodhargala) an argala is itself a debated sub-topic across Jaimini commentaries."},
    "SIG_PHALADEEPIKA_MULTI_LAGNA": {
        "technique": "Multi-lagna profession check (10th from Lagna/Moon/Sun)",
        "basis": "Phaladeepika, chapter 5 (profession)",
        "target": "general",
        "controversy": "Named classical source; this engine's exact weighting of each of the three reference points is an engineered choice, not specified verbatim in the source.",
    },
    "SIG_MULTI_VARGA_LAGNA_PRECEDENCE": {"technique": "D9/D10-Lagna native lordship precedence", "basis": "Multi-varga lagna doctrine (D9/D10 as independent ascendants)", "target": "general", "controversy": "Precedence ordering between D9-Lagna and D10-Lagna findings is this engine's own choice."},
    "SIG_D10_NATIVE_HOUSE_GRAPH": {"technique": "D10 (Dashamsha)-native house-graph evidence", "basis": "Dashamsha as the classical career/execution varga", "target": "general", "controversy": "Which D10 house-to-house connections count as significant is an engineered house-graph, not a fixed classical enumeration."},
    "SIG_D9_NATIVE_HOUSE_GRAPH": {"technique": "D9 (Navamsha)-native house-graph evidence", "basis": "Navamsha as the classical durability/confirmation varga", "target": "general", "controversy": "Same house-graph caveat as the D10 entry above."},
    "SIG_D1_TENTH_LORD_DIRECT": {"technique": "Direct D1 10th-lord judgment (strength, house connections, D9/D10 dignity)", "basis": "Standard 10th-house-of-career doctrine", "target": "general", "controversy": "The specific connection set judged (H7-H10/H10-H11/H2-H10, etc.) is an engineered enumeration."},
    "SIG_FIFTH_HOUSE_BUSINESS": {"technique": "5th-house independent-professional/business combinations", "basis": "House-combination (yoga) doctrine, 1-2-5-9-10-11 group", "target": "general", "controversy": "The specific house-pair table is this engine's own compilation, not a single classical verse."},
    "SIG_EXTENDED_HOUSE_COMBINATIONS": {"technique": "Extended multi-lord house-combination checks (2-11, 2-8, 3-7, 4-8, 9-11, etc.)", "basis": "House-combination (yoga) doctrine", "target": "general", "controversy": "This is an engineered enumeration of plausible combinations, not a single named classical yoga list."},
    "SIG_LAGNESH_AFFLICTION_KARAKA": {"technique": "Lagnesh combustion/debilitation and karaka connections", "basis": "Standard Lagnesh (ascendant-lord) strength doctrine", "target": "general", "controversy": "None notable beyond the general engine caveat -- fairly standard doctrine."},
    "SIG_BUSINESS_SIGNIFICATOR_GRAHA_YUDDHA": {"technique": "Graha Yuddha (planetary war) among business significators", "basis": "Classical Graha Yuddha doctrine", "target": "general", "controversy": "Which planets count as 'business significators' for this check (2nd/6th/7th/10th/11th lords + Mercury) is engine-defined scope, not universal."},
    "SIG_JAIMINI_KARAKAMSHA": {"technique": "Jaimini Karakamsha house-lord checks (10th/3rd/7th/11th/2nd from Karakamsha)", "basis": "Jaimini Karakamsha doctrine", "target": "general", "controversy": "Karakamsha derivation method itself varies (Atmakaraka tie-breaking rules differ across sources)."},
    "SIG_JAIMINI_ARUDHA_LAGNA": {"technique": "Jaimini Arudha Lagna / A7 / A10 checks", "basis": "Jaimini Arudha doctrine", "target": "general", "controversy": "Arudha calculation has known classical exception rules (e.g. same-house/4th-from cases) whose full handling is not claimed complete here."},
    "SIG_H11_PROFIT_REALIZATION": {"technique": "H11 (gains house) lord placement/strength", "basis": "Standard 11th-house-of-gains doctrine", "target": "profit", "controversy": "Fairly standard doctrine; weighting is engine-defined."},
    "SIG_H11_D9_CONFIRMATION": {"technique": "D9 dignity confirmation of the H11 lord's gains promise", "basis": "Navamsha as classical confirmation varga", "target": "profit", "controversy": "Standard application of D9 confirmation to a specific house lord."},
    "SIG_H2_CAPITAL_BASE": {"technique": "H2 (capital/wealth-base house) lord placement/strength", "basis": "Standard 2nd-house-of-wealth doctrine", "target": "profit", "controversy": "Fairly standard doctrine; weighting is engine-defined."},
    "SIG_H2_D9_CONFIRMATION": {"technique": "D9 dignity confirmation of the H2 lord's capital promise", "basis": "Navamsha as classical confirmation varga", "target": "profit", "controversy": "Standard application of D9 confirmation to a specific house lord."},
    "SIG_MERCURY_RETROGRADE_TRADE_TIMING": {"technique": "Mercury retrograde (vakra-Budha) linked to a business house", "basis": "Classical retrograde-planet timing caution", "target": "general", "controversy": "The 'delayed-but-not-blocked' framing is this engine's interpretive choice among several possible retrograde readings."},
    "SIG_D2_HORA_WEALTH_FLOW": {"technique": "D2 (Hora) wealth-flow corroboration for H2/H11 lords and wealth karakas", "basis": "Hora as the classical wealth-flow varga", "target": "general", "controversy": "D2 house/lord scope in this engine is narrower than some traditional Hora treatments -- see this rule's own house_evidence.py docstring."},
    "SIG_H3_INITIATIVE_SELF_EFFORT": {"technique": "H3 (self-effort/initiative house) lord placement", "basis": "Standard 3rd-house-of-effort doctrine", "target": "general", "controversy": "Fairly standard doctrine."},
    "SIG_D3_NATIVE_SELF_EFFORT": {"technique": "D3 (Drekkana)-native corroboration of the D1-H3 self-effort promise", "basis": "Drekkana as the classical self-effort/courage varga", "target": "general", "controversy": "D3 house-graph scope here is this engine's own construction, not a fixed classical enumeration."},
    "SIG_JANMA_NAKSHATRA": {"technique": "Janma Nakshatra (birth star) business-signification table", "basis": "Nakshatra-based career/temperament doctrine", "target": "general", "controversy": "The specific 8-entry curated table (nakshatra_business.py) is this engine's own compilation from multiple traditional nakshatra characterizations, not a single verbatim classical list."},
    "SIG_H9_FORTUNE": {"technique": "H9 (fortune house) lord dignity, gated by Neecha Bhanga", "basis": "Standard 9th-house-of-fortune doctrine plus Neecha Bhanga (debilitation-cancellation) doctrine", "target": "general", "controversy": "Neecha Bhanga has several classically-recognized cancellation conditions; this engine's _neecha_bhanga_status() implements a subset, not every documented condition."},
    "SIG_RAHU_H7_H11": {"technique": "Rahu in H7 (partnership) or H11 (gains), gated by affliction", "basis": "Rahu's classical unconventional/foreign-connection signification", "target": "general", "controversy": "Rahu's classical treatment is one of the more divergent topics across traditions (some read it more negatively by default than this engine's affliction-gated approach)."},
    "SIG_DARAKARAKA_H7": {"technique": "Darakaraka (Jaimini spouse/partnership karaka) dignity and H7 linkage", "basis": "Jaimini Darakaraka doctrine", "target": "general", "controversy": "Darakaraka is conceptually a Jaimini karaka, but this rule is tagged family=D1_PROMISE rather than ACTIVATION_DIRECTION (the family reserved for Jaimini/KP activation-direction techniques elsewhere in this registry) -- a deliberate, disclosed inconsistency carried over from when family was still inferred from note wording (this rule's note never used Jaimini-specific phrasing, so the now-deleted text classifier landed it in D1_PROMISE by default), preserved when family tagging became explicit so the switch to typed tags wouldn't silently reclassify it. Not a provenance error, but a known taxonomy quirk worth revisiting: on methodological grounds Darakaraka arguably belongs in ACTIVATION_DIRECTION alongside the other Jaimini techniques."},
    "SIG_MERCURY_VENUS_TRADE": {"technique": "Mercury + Venus conjunction/mutual-aspect trade signature", "basis": "Standard Mercury-Venus (trade/negotiation significators) combination doctrine", "target": "general", "controversy": "Fairly standard doctrine."},
    "SIG_MARS_SATURN_OPERATIONAL": {"technique": "Mars/Saturn in H3/H6/H10 operational-capacity signature", "basis": "Standard Mars/Saturn (execution/discipline significators) house-placement doctrine", "target": "general", "controversy": "Fairly standard doctrine."},
    "SIG_H11_SAV_ASHTAKAVARGA": {"technique": "H11 Sarvashtakavarga (SAV) point-count support", "basis": "Ashtakavarga doctrine", "target": "profit", "controversy": "The >=30 threshold is an engine-defined cutoff, not a universal classical standard (thresholds vary by tradition/commentator)."},
    "SIG_VRY_DUSTHANA_LORD_QUALIFICATION": {"technique": "Viparita Raja Yoga qualification (dusthana-lord placement/exchange)", "basis": "Viparita Raja Yoga doctrine", "target": "stability_risk", "controversy": "VRY qualification/cancellation conditions are one of the most-debated topics in classical yoga doctrine; this engine implements a simplified qualification set (see constants.py's VRY-related comments) -- explicitly flagged elsewhere (astrological-completeness item 9) as incomplete, especially around aspect-based cancellation."},
    "SIG_H12_LOSS_LIABILITY": {"technique": "H12 (loss/liability house) lord placement", "basis": "Standard 12th-house-of-loss/expenditure doctrine", "target": "stability_risk", "controversy": "The foreign-trade/export exception for a strong H12 lord is this engine's interpretive reading, not universally applied in traditional treatments."},
    "SIG_D1_DISPOSITOR_CHAIN": {
        "technique": "Multi-hop D1 dispositor chain for the H7/H10 lords (does the placement rest on a self-sufficient foundation, a mutual exchange, or a compromised/unresolved one?)",
        "basis": "Dispositor (sign-lord) analysis -- a standard, uncontroversial MECHANISM in classical astrology (a planet's strength depends partly on the dignity of the lord of the sign it occupies); the multi-hop CHAIN extension and the specific weights assigned to grounded/exchange/loop/unresolved outcomes are this engine's own construction, not a named classical technique with its own verse citation.",
        "target": "general",
        "controversy": "The mechanism (follow sign-lord, then that planet's own sign-lord, etc.) is mechanical and not itself disputed. What IS this engine's own engineered choice: the exact point weights for each outcome, the 4-hop bound, and treating an unresolved/looped chain as near-neutral rather than negative. D9 and D10 dispositor chains are now also built (SIG_D9_DISPOSITOR_CHAIN, SIG_D10_DISPOSITOR_CHAIN below), sharing this same core mechanism/weights via house_evidence.py::_dispositor_chain_walk.",
    },
    "SIG_D9_DISPOSITOR_CHAIN": {
        "technique": "Multi-hop D9 (Navamsha) dispositor chain for the D1-H7/H10 lords, walked within D9's own house graph",
        "basis": "Same dispositor-chain mechanism as SIG_D1_DISPOSITOR_CHAIN, applied to D9's native house-graph (occupancy derived from divisional_charts['D9_navamsha'], lordship derived from the same resolved D9-Lagna) instead of D1's -- consistent with this module's existing D9-native corroboration checks (e.g. SIG_H7_D9_CONFIRMATION-style checks) that judge D1 significators within D9's own house graph rather than D1's.",
        "target": "general",
        "controversy": "Same engineered choices as SIG_D1_DISPOSITOR_CHAIN (weights, 4-hop bound, near-neutral unresolved/loop treatment), now applied a second time to a different varga. Additionally: D9 occupancy data is only available for charts where divisional_charts['D9_navamsha'] was populated by the ingest path -- this check silently contributes nothing (not a fabricated fallback) for charts lacking that data.",
    },
    "SIG_D10_DISPOSITOR_CHAIN": {
        "technique": "Multi-hop D10 (Dashamsha) dispositor chain for the D1-H7/H10 lords, walked within D10's own house graph",
        "basis": "Same dispositor-chain mechanism as SIG_D1_DISPOSITOR_CHAIN, applied to D10's native house graph (payload.d10_house_lords / d10_house_occupancy, the same source _d10_native_house_evidence already reads) instead of D1's -- D10 is the classical career/livelihood varga, making its own dispositor-chain structure directly relevant to the same H7/H10 significators being judged.",
        "target": "general",
        "controversy": "Same engineered choices as SIG_D1_DISPOSITOR_CHAIN (weights, 4-hop bound, near-neutral unresolved/loop treatment), now applied a third time to a different varga. Silently contributes nothing for charts lacking d10_house_lords/d10_house_occupancy data.",
    },
}


def resolve_rule_provenance(rule_id: Optional[str]) -> Dict[str, Any]:
    """Look up a rule_id's provenance record. Falls back to a clearly-marked
    'unregistered' record (rather than raising) for any rule_id not yet
    catalogued above, so a caller iterating over live evidence never crashes
    on a newly-added rule_id whose registry entry hasn't been written yet --
    that gap is visible in the returned record itself (`registered: False`),
    not hidden behind an exception.
    """
    if rule_id and rule_id in RULE_PROVENANCE:
        record = dict(RULE_PROVENANCE[rule_id])
        record["rule_id"] = rule_id
        record["registered"] = True
        return record
    return {
        "rule_id": rule_id,
        "registered": False,
        "technique": None,
        "basis": None,
        "target": None,
        "controversy": None,
    }
