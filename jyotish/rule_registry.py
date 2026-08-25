"""Minimal, honest rule registry for the LLM rule-trace validator.

GAP-FIX (2026-07, audit item 20): "Add rule IDs, textual source, edition/
chapter/verse or practitioner policy, school, implementation version,
inputs, output, exclusions and confidence to every astrological signal."

This is a STARTING registry, not a complete one. It only documents rules
where this codebase's own source already carries a real citation or a
clearly-stated modeling decision (found during this session's code review) --
it deliberately does NOT invent classical citations for rules that don't
already have one in the code. Any rule not listed here should be treated by
the validator as SOURCE NOT ESTABLISHED, per the validator's own system
prompt instruction, rather than the registry (or the LLM) fabricating one.

Extend this incrementally: when a new gap-boost/dignity/yoga rule gets a real
source citation added to its docstring, add a matching entry here.
"""
from __future__ import annotations

from pathlib import Path
import re
import warnings
from typing import Any, Dict, List

RULES_VERSION = "jyotish-rules.2026-07-17.v2"

# Each entry: rule_id -> {school, source, statement, implementation, confidence}
# `confidence` is NOT a probability -- it is this registry's own honest label
# for how well-attested the rule is (see the fields' descriptions below).
RULE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "DIGNITY.EXALTATION_DEBILITATION_DEGREES": {
        "school": "Parashari",
        "source": "BPHS Ch.4 (exaltation/debilitation degree points); see constants._EXALT_DEGREE",
        "statement": "Each planet has an exact exaltation degree within its exaltation "
                     "sign; debilitation is the same degree-number, 180 deg opposite.",
        "implementation": "jyotish/constants.py:_EXALT_DEGREE, _DEBIL_DEGREE",
        "confidence": "well_attested",
    },
    "RETROGRADE.VAKRA_NEECHA_BHANGA": {
        "school": "multiple (Phaladeepika, Saravali, Uttara Kalamrita cited)",
        "source": "see jyotish/constants.py's _RETRO_EXALTED_DAMPENED docstring for the "
                   "specific citation and the documented asymmetry decision",
        "statement": "A retrograde DEBILITATED planet is treated as strong (debility "
                     "effectively cancelled). The REVERSE (retrograde exalted -> weak) "
                     "is explicitly NOT treated as equally well-attested by this engine.",
        "implementation": "jyotish/astro.py:_compute_eff_strengths dignity modifier block",
        "confidence": "asymmetric: debilitated-direction well_attested, "
                      "exalted-direction minority_view (see source)",
    },
    "COMBUSTION.PER_PLANET_ORBS": {
        "school": "Parashari (BPHS)",
        "source": "jyotish/constants.py:_COMBUST_ORB",
        "statement": "Each planet has its own combustion orb from the Sun "
                     "(Moon 12, Mars 17, Mercury 14, Jupiter 11, Venus 10, Saturn 15 deg); "
                     "Rahu/Ketu are not combust (shadow points, no physical body).",
        "implementation": "jyotish/dignity.py:is_combust, jyotish/astro.py combustion gradient",
        "confidence": "well_attested",
    },
    "COMBUSTION.CAZIMI": {
        "school": "Hellenistic/Western (NOT Parashari)",
        "source": "see jyotish/llm_policy.py:CAZIMI_DOCTRINE_NOTE",
        "statement": "A planet within 1 deg of the Sun is exceptionally strengthened "
                     "rather than combust ('in the heart of the Sun').",
        "implementation": "jyotish/astro.py:_compute_eff_strengths cazimi_mod (1.30x)",
        "confidence": "cross_tradition_import -- not a Parashari doctrine; documented "
                      "deliberate modeling choice, not a classical Vedic rule",
    },
    "NAKSHATRA.RAHU_KETU_ASPECT": {
        "school": "school_dependent (this engine defaults to 5th/9th convention)",
        "source": "jyotish/astro.py:_get_planetary_aspects RAHU_KETU_ASPECT_MODE",
        "statement": "Rahu/Ketu cast special aspects; this engine's default convention "
                     "is 5th and 9th sign from the node (alternates: 7th-only, none).",
        "implementation": "jyotish/astro.py:_get_planetary_aspects",
        "confidence": "school_dependent -- multiple traditions disagree; this engine's "
                      "choice is documented and configurable, not asserted as the only rule",
    },
    "VARGOTTAMA.SAME_SIGN_D1_D9": {
        "school": "Parashari",
        "source": "widely-attested classical convention",
        "statement": "A planet occupying the same sign in D1 and D9 (Navamsha) is "
                     "Vargottama -- a materially strengthened placement.",
        "implementation": "jyotish/astro.py:_is_vargottama",
        "confidence": "well_attested",
    },
    "VIMSHOPAKA.DASAVARGA_WEIGHTS": {
        "school": "Parashari",
        "source": "BPHS Ch.6 (Vimshopaka Bala, Dasavarga table)",
        "statement": "Ten divisional charts (D1,D2,D3,D7,D9,D10,D12,D16,D30,D60) are "
                     "weighted to a 20-point total for cumulative divisional strength.",
        "implementation": "jyotish/vimshopaka.py:DASAVARGA_WEIGHTS",
        "confidence": "well_attested for the weight table; D60's specific SIGN "
                      "convention used to compute the D60 varga itself is "
                      "lower-confidence -- see jyotish/vimshopaka.py:compute_d60_sign",
    },
    "CONFLUENCE.THREE_SOURCE_MINIMUM": {
        "school": "modern synthesis, not a single classical citation",
        "source": "jyotish/boosts.py:_confluence_gate docstring",
        "statement": "A field needs a minimum of 3 independent chart sources "
                     "(house lords, dasha lord, AK, AmK) to be treated as genuinely "
                     "astrologically indicated, not merely hinted at.",
        "implementation": "jyotish/boosts.py:_confluence_gate",
        "confidence": "modern_heuristic -- an engineering threshold for combining "
                      "classical significators, not itself a classical rule",
    },
    "DASHA.VIMSHOTTARI_YEAR_LENGTH": {
        "school": "modern convention (tropical/Gregorian year)",
        "source": "jyotish/llm_policy.py:VIMSHOTTARI_YEAR_LENGTH_DAYS",
        "statement": "MD/AD/PD age-boundary arithmetic uses 365.25-day years.",
        "implementation": "jyotish/engine.py dasha boundary math",
        "confidence": "modern_heuristic -- some classical sources use a "
                      "sidereal/nakshatra year instead; not independently verified "
                      "against a second calculator in this codebase's test suite",
    },
    "DIGNITY.MOOLATRIKONA": {
        "school": "Parashari",
        "source": "BPHS Ch.4 (Moolatrikona sign + degree range per planet)",
        "statement": "Each planet has a Moolatrikona sign and a specific degree "
                     "range within it (e.g. Sun in Leo 0-20 deg); outside that "
                     "range but still in the MT sign, the placement is graded "
                     "as Own rather than Moolatrikona.",
        "implementation": "jyotish/constants.py:_MOOLATRIKONA",
        "confidence": "well_attested",
    },
    "DIGNITY.NAISARGIKA_FRIENDSHIP": {
        "school": "Parashari",
        "source": "BPHS Ch.5 (Naisargika/natural planetary friendship table)",
        "statement": "Each planet has a fixed set of natural friends/neutrals/"
                     "enemies independent of chart placement; this is combined "
                     "with temporal (house-distance) friendship elsewhere for "
                     "the five-fold (Panchadha Maitri) compound relationship.",
        "implementation": "jyotish/constants.py:_NATURAL_FRIENDS",
        "confidence": "well_attested for the natural-friendship table itself; "
                      "the compound five-fold synthesis with temporal friendship "
                      "is this engine's own combination logic, not independently "
                      "cross-checked against a second reference implementation",
    },
    "KARAKA.SYSTEMATIC_FIELD_TABLE": {
        "school": "Parashari / Jaimini",
        "source": "BPHS / Jataka Parijata karakatwa (planet-to-signification list)",
        "statement": "Each graha classically signifies a set of professions/"
                     "domains (e.g. Mercury: commerce/communication/analysis); "
                     "this engine maps that classical karakatwa onto its own "
                     "coarse domain buckets.",
        "implementation": "jyotish/constants.py karaka-to-field table",
        "confidence": "well_attested for the karakatwa list itself; the mapping "
                      "onto this engine's specific domain buckets is a modern "
                      "editorial reduction, not itself a classical statement",
    },
    "BHAVA.COMPOSITE_HOUSE_STRENGTH": {
        "school": "Parashari",
        "source": "BPHS (Bhava Bala as a composite, not a single-house judgment)",
        "statement": "A house's career relevance in classical Jyotish is not "
                     "limited to H10 alone; H2/H6/H10/H11 (and others by "
                     "context) jointly contribute to a composite Bhava Bala "
                     "used for career adjudication.",
        "implementation": "jyotish/boosts.py Bhava Bala functions (career-relevant houses)",
        "confidence": "well_attested for the general composite-strength "
                      "principle; the specific house set and weighting used "
                      "here is this engine's own reduction",
    },
    "GRAHA_YUDDHA.DEGREE_WINNER": {
        "school": "Parashari",
        "source": "classical Graha Yuddha (planetary war) rule",
        "statement": "When two of Mercury/Venus/Mars/Jupiter/Saturn are within "
                     "1 deg of each other, they are in planetary war; the planet "
                     "with the higher longitude (further along in the sign) is "
                     "the winner, the other the loser.",
        "implementation": "jyotish/boosts.py graha yuddha detection",
        "confidence": "well_attested",
    },
    "TAJIKA.APPLYING_SEPARATING_ORB": {
        "school": "Tajika (Perso-Arabic-influenced, adopted into later Jyotish practice)",
        "source": "classical Tajik aspect-orb convention",
        "statement": "An applying aspect within a 0d17' orb is graded as "
                     "maximally powerful; this is a Tajika-school threshold, "
                     "not a Parashari one.",
        "implementation": "jyotish/boosts.py applying-aspect strength grading",
        "confidence": "cross_tradition_import -- Tajika, not Parashari; "
                      "documented as such rather than presented as universal",
    },
    "ASHTAKAVARGA.SAV_BINDU_SCALING": {
        "school": "Parashari",
        "source": "classical Ashtakavarga (Sarvashtakavarga bindu counting), "
                   "this engine's specific linear scaling factor is an engineering "
                   "reduction of the classical bindu-strength principle",
        "statement": "SAV bindu count in a sign/house is used to scale a "
                     "strength factor: baseline 28 bindus = 1.00x, clamped to "
                     "[0.80, 1.20] at +-20 bindus from baseline, 1% per bindu.",
        "implementation": "jyotish/boosts.py SAV bindu factor (see "
                          "test_sav_bindu_factor_math for the locked formula)",
        "confidence": "well_attested for bindu-counting itself; the specific "
                      "linear 1%-per-bindu clamp-to-[0.80,1.20] mapping into a "
                      "career-score multiplier is this engine's own numeric "
                      "choice, not a classical formula",
    },
    "GOCHAR.SATURN_HOUSE_TRANSIT": {
        "school": "Parashari (Gochar Phala)",
        "source": "classical Saturn transit house-effect convention, deliberately "
                   "narrow subset implemented here (not a full Gochar Phala system)",
        "statement": "Saturn's transit through specific houses relative to natal "
                     "Moon/Lagna carries distinct classical significance for "
                     "career growth or restriction.",
        "implementation": "jyotish/boosts.py:_gochar_h10_activation_bonus and "
                          "related Gochar functions",
        "confidence": "well_attested for the general classical principle; "
                      "this engine implements a narrow, explicitly-scoped subset, "
                      "not the full classical Gochar Phala system (documented "
                      "as such in the implementing module)",
    },

# --- SIGNAL.* provenance resolution (2026-07-18) ---
# Every engine-emitted SIGNAL.* id is classified as either (A) a real classical
# citation found via web search this session, or (B) an honest
# 'modern_engineering_or_unclassified' construct (source starts with 'N/A --').
# See RULE_PROVENANCE_RESOLUTION_2026-07-18.md for the full research log.
    "SIGNAL.ADHI_ANAPHA_YOGA": {
        "school": "Parashari (BPHS / widely-repeated classical convention)",
        "source": "Chandra Yoga (Sunapha/Anapha/Durudhara/Kemadruma) doctrine -- benefics/malefics in 2nd and/or 12th from Moon; general chapter area and wording confirmed via web search (thevedichoroscope.com, vedicrishi.in, wisdomlib.org summarizing BPHS Chandra Yoga chapter); a specific BPHS verse number was not independently confirmed in this session",
        "statement": "Engine signal 'ADHI_ANAPHA_YOGA': classical lunar (Chandra) yoga condition based on planets adjacent to (2nd/12th from) the Moon.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.AD_KENDRA_TRIKONA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'AD_KENDRA_TRIKONA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_AMK": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_AMK' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_COMBUSTION_PENALTY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_COMBUSTION_PENALTY' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_D24": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_D24' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_DOMAIN_FLAT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_DOMAIN_FLAT' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_HOUSE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_HOUSE' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_PLANET_DOMAIN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_PLANET_DOMAIN' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_PRIMARY_KARAKA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_PRIMARY_KARAKA' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AK_SOUL_MANDATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AK_SOUL_MANDATE' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AMALA_YOGA": {
        "school": "Parashari (BPHS)",
        "source": "BPHS shloka paraphrased across sources as 'Chandrat dashame sthite shubhe Amala yogah' -- a benefic in the 10th from the Moon (or Lagna) forms Amala Yoga; confirmed via web search (astrosight.ai, rashiratanbhagya.com, mpanchang.com all repeating the same classical formulation)",
        "statement": "Benefic in the 10th house from Moon/Lagna -- Amala Yoga.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.AMK_HOUSE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'AMK_HOUSE' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.ANTARDASHA_AFFINITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'ANTARDASHA_AFFINITY' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.ARGALA": {
        "school": "Jaimini",
        "source": "Argala / Virodhargala (counter-argala) doctrine from the Jaimini Sutras -- planets in 2nd/4th/11th (and 5th) from a house provide argala, with 3rd/10th/12th planets providing virodhargala that can cancel it; confirmed via web search (askastrologer.com Jaimini guide)",
        "statement": "Argala: planets in 2nd/4th/11th (and 5th) from a reference point providing supportive influence.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.ARGALA_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Argala / Virodhargala (counter-argala) doctrine from the Jaimini Sutras -- planets in 2nd/4th/11th (and 5th) from a house provide argala, with 3rd/10th/12th planets providing virodhargala that can cancel it; confirmed via web search (askastrologer.com Jaimini guide)",
        "statement": "Modern construct applying the classical Jaimini Argala doctrine specifically to the 10th house for career scoring -- the H10-specific application is this engine's own construct.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.ARTS_PLACEMENT_GUARD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'ARTS_PLACEMENT_GUARD' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.ASPECT_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'ASPECT_H10' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.AVASTHA_MODIFIER": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'AVASTHA_MODIFIER' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BADHAKA_LORD_PENALTY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Badhakasthana/Badhakesh: for movable signs the 11th house is Badhaka, fixed signs the 9th, dual signs the 7th; confirmed via web search (varahamihira.blogspot.com). Search also surfaced the caveat that Parashara used Badhaka specifically in relation to Chara Dasha, not as a universal malefic-house rule",
        "statement": "Modern penalty construct applied to the classical Parashari Badhaka (obstructor) lord -- the penalty magnitude and career-scoring application are this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BAV_INDIVIDUAL": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'BAV_INDIVIDUAL' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BHAVA_LAGNA": {
        "school": "Parashari in origin, Jaimini in common use (Vishesha Lagna)",
        "source": "Special lagnas (Bhava/Hora/Ghati/Sree Lagna) are documented in Parashari literature (BPHS) and used heavily in Jaimini-school practice; confirmed via web search (paramarsh.app 'Jaimini Special Lagnas', barbarapijan.com); exact BPHS verse numbers were not independently confirmed in this session",
        "statement": "Bhava Lagna, a classical Vishesha (special) Lagna.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.BHAVESHA_PHALA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'BHAVESHA_PHALA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BHRATRIKARAKA_FIELD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'BHRATRIKARAKA_FIELD' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BHRIGU_BINDU": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- attribution uncertain. Bhrigu Bindu (midpoint of Rahu and Moon) is popularly attributed to the Bhrigu/Nadi tradition, but web search (astrolight08.wordpress.com, howisyourdaytoday.com) indicates it came into modern prominence via C.S. Patel's Nadi-astrology writings, referencing Dev Keralam (Chandra Kala Nadi) rather than BPHS; a primary classical-text citation could not be independently confirmed, so no citation is asserted",
        "statement": "Bhrigu Bindu: midpoint of Rahu and Moon, used as a sensitive predictive point in Nadi-influenced practice; classical primary-source attestation not independently confirmed.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BIRTH_TIME_PRECISION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'BIRTH_TIME_PRECISION' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BRAHMA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'BRAHMA' (jyotish/field_methods/jaimini.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BRAHMA_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'BRAHMA_LORD' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.BUDHA_ADITYA": {
        "school": "Parashari",
        "source": "Budha-Aditya Yoga: Sun-Mercury conjunction, a long-attested classical combination discussed across Parashari literature; confirmed via web search (satyori.com, jothishi.com) though a specific BPHS verse was not independently pinned in this session",
        "statement": "Sun-Mercury conjunction -- Budha-Aditya Yoga.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.CAREER_DOMAIN_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CAREER_DOMAIN_BONUS' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CAREER_PARIVARTANA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CAREER_PARIVARTANA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CHANDAL_YOGA": {
        "school": "Parashari / widely-repeated classical convention",
        "source": "Guru Chandal Yoga = Jupiter conjunct (or aspected by) Rahu; confirmed via web search (satyori.com, astroparasar.com and others) as a long-standing named classical combination, though a specific primary-text verse citation was not independently confirmed in this session",
        "statement": "Jupiter conjunct/aspected by Rahu -- Guru Chandal Yoga.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_by_tradition",
    },
    "SIGNAL.CHANDRA_H10_JAIMINI": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CHANDRA_H10_JAIMINI' (jyotish/field_methods/jaimini.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CHANDRA_H10_KP": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CHANDRA_H10_KP' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CHANDRA_H10_PARASHARA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CHANDRA_H10_PARASHARA' (jyotish/field_methods/parashara.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CHANDRA_LAGNA_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CHANDRA_LAGNA_H10' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CHARA_DASHA": {
        "school": "Jaimini",
        "source": "Chara Dasha -- a rashi (sign)-based Jaimini dasha system, one of the foundational Jaimini timing techniques described across Jaimini Sutras commentary; well-attested by convention though a specific sutra number was not independently pinned in this session's search",
        "statement": "Chara Dasha: Jaimini rashi (sign)-based dasha sequencing system.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.CHARA_DASHA_SIGN_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Dasha -- a rashi (sign)-based Jaimini dasha system, one of the foundational Jaimini timing techniques described across Jaimini Sutras commentary; well-attested by convention though a specific sutra number was not independently pinned in this session's search",
        "statement": "Modern construct evaluating the sign lord active under the classical Jaimini Chara Dasha for career-timing scoring -- the specific scoring use is this engine's own construct.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CLUSTER_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CLUSTER_BONUS' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CLUSTER_COUNTERWEIGHT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CLUSTER_COUNTERWEIGHT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.COMBUSTION_PENALTY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'COMBUSTION_PENALTY' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.COMPOUND_DASHA_QUALITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'COMPOUND_DASHA_QUALITY' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CONFLUENCE_GATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CONFLUENCE_GATE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.CONFLUENCE_SOURCES": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'CONFLUENCE_SOURCES' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_COMPREHENSIVE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_COMPREHENSIVE' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_D1_CONCORDANCE_YOGA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_D1_CONCORDANCE_YOGA' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_DUSTHANA_PENALTY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_DUSTHANA_PENALTY' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H10' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H10_LORD_DIGNITY_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H10_LORD_DIGNITY_BONUS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H10_LORD_DUSTHANA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H10_LORD_DUSTHANA' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H10_LORD_KENDRA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H10_LORD_KENDRA' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H10_LORD_NEUTRAL": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H10_LORD_NEUTRAL' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H10_OCCUPANTS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H10_OCCUPANTS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H10_STELLIUM": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H10_STELLIUM' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H11_OCCUPANTS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H11_OCCUPANTS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H5_INTELLIGENCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H5_INTELLIGENCE' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_H9_DHARMA_SUPPORT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_H9_DHARMA_SUPPORT' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_LAGNA_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_LAGNA_LORD' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_LAGNA_LORD_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_LAGNA_LORD_BONUS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_LAGNA_LORD_DUSTHANA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_LAGNA_LORD_DUSTHANA' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_LAGNA_LORD_KENDRA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_LAGNA_LORD_KENDRA' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_LAGNA_SIGN_AFFINITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_LAGNA_SIGN_AFFINITY' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_LL_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_LL_BONUS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_RAJ_YOGA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_RAJ_YOGA' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_VALIDATION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D10_VALIDATION' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D10_YOGAKARAKA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Yogakaraka: a single planet ruling both a kendra (1/4/7/10) and a trikona (1/5/9) house is a first-rate functional benefic; BPHS Ch.34 cited in web search summary (grokipedia.com Yoga-karakas page), though the primary verse text was not independently retrieved in this session",
        "statement": "Modern scoring construct 'D10_YOGAKARAKA' built on the classical Yogakaraka concept (planet ruling both a kendra and a trikona) -- the specific penalty/varga-application logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D1_D10_DOUBLE_DIGNITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D1_D10_DOUBLE_DIGNITY' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D1_D10_H10_DOUBLE_DIGNITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D1_D10_H10_DOUBLE_DIGNITY' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D1_H10_LORD_IN_D10_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D1_H10_LORD_IN_D10_H10' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D20_VIMSHAMSHA": {
        "school": "Parashari (BPHS Shodasavarga chapter)",
        "source": "The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "D20 (Vimshamsha) divisional chart, part of BPHS's Shodasavarga scheme.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.D24_AK": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D24_AK' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D24_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D24_BONUS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D24_FULL": {
        "school": "Parashari (BPHS Shodasavarga chapter)",
        "source": "The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "D24 (Siddhamsha/Chaturvimshamsha) divisional chart, part of BPHS's Shodasavarga scheme.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.D30_TRIMSAMSHA": {
        "school": "Parashari (BPHS Shodasavarga chapter)",
        "source": "The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "D30 (Trimshamsha) divisional chart, part of BPHS's Shodasavarga scheme.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.D3_DREKKANA": {
        "school": "Parashari (BPHS Shodasavarga chapter)",
        "source": "The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "D3 (Drekkana) divisional chart, part of BPHS's Shodasavarga scheme.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.D60_APPLIED_MULTIPLIER": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D60_APPLIED_MULTIPLIER' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D60_COMBINED_OBSERVATION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D60_COMBINED_OBSERVATION' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D60_ROLE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D60_ROLE' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D60_VIMSHOPAKA_GATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D60_VIMSHOPAKA_GATE' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D9_AK": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D9_AK' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D9_FIRST_CLASS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D9_FIRST_CLASS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D9_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D9_H10' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.D9_VALIDATION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'D9_VALIDATION' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DARAKARAKA_FIELD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'DARAKARAKA_FIELD' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DASHA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DASHA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DASHA_THREAD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DASHA_THREAD' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DASHA_TIMING_GATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DASHA_TIMING_GATE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DEBIL_AK_SOUL_PEN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'DEBIL_AK_SOUL_PEN' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DEVATA_DOMAIN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DEVATA_DOMAIN' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DHARMA_KARMA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DHARMA_KARMA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DIGBALA_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DIGBALA_H10' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DK_PARTNERSHIP": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'DK_PARTNERSHIP' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DOSHA_BURNOUT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DOSHA_BURNOUT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.DUSTHANA_PENALTY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'DUSTHANA_PENALTY' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.EDU_BRANCH": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'EDU_BRANCH' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.EDU_HOUSE_SAV_FACTOR": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'EDU_HOUSE_SAV_FACTOR' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.EDU_STAR": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'EDU_STAR' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.ENGINEERING_YK_MANDATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'ENGINEERING_YK_MANDATE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.EXALTED_DOMAIN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'EXALTED_DOMAIN' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.FOREIGN_CAREER_MULT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'FOREIGN_CAREER_MULT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.GAJA_KESARI_MEDICINE_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'GAJA_KESARI_MEDICINE_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.GANA_WORKPLACE_FIT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'GANA_WORKPLACE_FIT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.GENDER_FIELD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'GENDER_FIELD' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.GHATI_LAGNA": {
        "school": "Parashari in origin, Jaimini in common use (Vishesha Lagna)",
        "source": "Special lagnas (Bhava/Hora/Ghati/Sree Lagna) are documented in Parashari literature (BPHS) and used heavily in Jaimini-school practice; confirmed via web search (paramarsh.app 'Jaimini Special Lagnas', barbarapijan.com); exact BPHS verse numbers were not independently confirmed in this session",
        "statement": "Ghati Lagna, a classical Vishesha (special) Lagna.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.GNATIKARAKA_FIELD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'GNATIKARAKA_FIELD' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.GNK_COMPETITIVE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'GNK_COMPETITIVE' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.GOCHAR_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'GOCHAR_H10' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.GUNA_BALANCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'GUNA_BALANCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_BRANCH": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_BRANCH' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_CONSENSUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_CONSENSUS' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_LORD_COMBUSTION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_LORD_COMBUSTION' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_LORD_DUSTHANA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_LORD_DUSTHANA' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_LORD_KENDRA_TRIKONA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_LORD_KENDRA_TRIKONA' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_LORD_STR": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_LORD_STR' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_LORD_TRIKONA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_LORD_TRIKONA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_SUBLORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_SUBLORD' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H10_SUB_SUB_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H10_SUB_SUB_LORD' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H11_NETWORK": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H11_NETWORK' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H12_STELLIUM_PEN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H12_STELLIUM_PEN' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H2H11_BRANCH": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H2H11_BRANCH' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H3_COMM": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H3_COMM' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H3_PARAKRAMA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H3_PARAKRAMA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H3_PARAKRAMA_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H3_PARAKRAMA_LORD' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H3_SKILLS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H3_SKILLS' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H5_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H5_LORD' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H6_DEFENCE_GATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H6_DEFENCE_GATE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H6_SERVICE_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H6_SERVICE_LORD' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H7_SUBLORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H7_SUBLORD' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H8_EARTH_BRANCH": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H8_EARTH_BRANCH' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H8_MEDICINE_GATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H8_MEDICINE_GATE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H8_RESEARCH": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H8_RESEARCH' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H9_DHARMA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H9_DHARMA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.H9_LORD_STRENGTH": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'H9_LORD_STRENGTH' (jyotish/field_methods/parashara.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.HORA_LAGNA": {
        "school": "Parashari in origin, Jaimini in common use (Vishesha Lagna)",
        "source": "Special lagnas (Bhava/Hora/Ghati/Sree Lagna) are documented in Parashari literature (BPHS) and used heavily in Jaimini-school practice; confirmed via web search (paramarsh.app 'Jaimini Special Lagnas', barbarapijan.com); exact BPHS verse numbers were not independently confirmed in this session",
        "statement": "Hora Lagna, a classical Vishesha (special) Lagna.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.HORA_MODE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'HORA_MODE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.HOUSE_SIGNIFICATION_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'HOUSE_SIGNIFICATION_BONUS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.INTERDISCIPLINARY_MIXED_KARAKA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'INTERDISCIPLINARY_MIXED_KARAKA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.INTEREST_PREF": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'INTEREST_PREF' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.JAIMINI_MATRIX": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'JAIMINI_MATRIX' (jyotish/field_methods/jaimini.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.JUPITER_AK_MEDICINE_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'JUPITER_AK_MEDICINE_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.JUPITER_AMK_LAW_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'JUPITER_AMK_LAW_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.JUPITER_LAW_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'JUPITER_LAW_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KAKSHA_ACTIVATION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'KAKSHA_ACTIVATION' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KARAKAMSHA": {
        "school": "Jaimini",
        "source": "Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Karakamsha = Navamsha sign occupied by the Atmakaraka; Jaimini soul-purpose indicator.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.KARAKAMSHA_DOMAIN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'KARAKAMSHA_DOMAIN' applying the classical Jaimini Karakamsha (Atmakaraka's Navamsha sign) to this engine's own H10/domain/occupancy scoring -- the application logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KARAKAMSHA_H10": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'KARAKAMSHA_H10' applying the classical Jaimini Karakamsha (Atmakaraka's Navamsha sign) to this engine's own H10/domain/occupancy scoring -- the application logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KARAKAMSHA_LAGNA_DRISHTI": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'KARAKAMSHA_LAGNA_DRISHTI' applying the classical Jaimini Karakamsha (Atmakaraka's Navamsha sign) to this engine's own H10/domain/occupancy scoring -- the application logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KARAKAMSHA_OCC": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'KARAKAMSHA_OCC' applying the classical Jaimini Karakamsha (Atmakaraka's Navamsha sign) to this engine's own H10/domain/occupancy scoring -- the application logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KARAKA_DOMAIN_BONUS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: The sixteen divisional charts (Shodasavarga) including D3 Drekkana, D9 Navamsha, D10 Dashamsha, D20 Vimshamsha, D24 Siddhamsha/Chaturvimshamsha, D30 Trimshamsha and D60 Shashtyamsha are defined in BPHS; confirmed via web search (prokerala.com, vedicdream.com, astro-seek.com Shodasha Varga summaries attributing the scheme to BPHS/Parashara)",
        "statement": "Modern scoring construct 'KARAKA_DOMAIN_BONUS' built on classical divisional-chart (D3/D9/D10/D20/D24/D30/D60, per BPHS Shodasavarga) and/or classical dignity/house concepts -- the specific bonus/penalty magnitude, validation/stellium/occupant logic, or cross-varga combination is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KEMADRUMA": {
        "school": "Parashari (BPHS / widely-repeated classical convention)",
        "source": "Chandra Yoga (Sunapha/Anapha/Durudhara/Kemadruma) doctrine -- benefics/malefics in 2nd and/or 12th from Moon; general chapter area and wording confirmed via web search (thevedichoroscope.com, vedicrishi.in, wisdomlib.org summarizing BPHS Chandra Yoga chapter); a specific BPHS verse number was not independently confirmed in this session",
        "statement": "Engine signal 'KEMADRUMA': classical lunar (Chandra) yoga condition based on planets adjacent to (2nd/12th from) the Moon.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.KENDRADHIPATI_CANCELLATION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Kendradhipati Dosha -- a natural benefic ruling only kendra houses (Gemini/Virgo Jupiter, Sagittarius/Pisces Mercury) loses some auspiciousness; confirmed via web search (srikeralabhagavathiastro.com, astrosaxena.com) as a Parashari doctrine, though the exact BPHS verse was not independently retrieved",
        "statement": "Modern construct deciding when the classical Kendradhipati Dosha (benefic kendra-lord losing auspiciousness) is treated as cancelled -- the cancellation logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KETU_RESEARCH_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'KETU_RESEARCH_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KETU_RESEARCH_H9H5": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'KETU_RESEARCH_H9H5' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.KP_LOW_CONFIDENCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'KP_LOW_CONFIDENCE' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LAGNA_ELEMENT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LAGNA_ELEMENT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LAGNA_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LAGNA_LORD' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LAGNA_LORD_DIRECTIVE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LAGNA_LORD_DIRECTIVE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LAGNA_LORD_H10_DOMAIN_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LAGNA_LORD_H10_DOMAIN_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LAGNA_PROPENSITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LAGNA_PROPENSITY' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LAGNA_TATVA_CLUSTER": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LAGNA_TATVA_CLUSTER' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LEO_VENUS_AK_ENGINEERING_GUARD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LEO_VENUS_AK_ENGINEERING_GUARD' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.LIFE_SCIENCE_CLUSTER": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'LIFE_SCIENCE_CLUSTER' (jyotish/field_methods/jaimini.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MAHAPURUSHA_MANDATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Panchamahapurusha Yoga (Ruchaka/Bhadra/Hamsa/Malavya/Sasa) -- Mars/Mercury/Jupiter/Venus/Saturn in own or exaltation sign in a kendra from Lagna; confirmed via web search as appearing across BPHS, Phaladeepika, Saravali and Brihat Jataka",
        "statement": "Modern 'mandate' gating construct built on the classical Panchamahapurusha Yoga (Ruchaka/Bhadra/Hamsa/Malavya/Sasa) -- the gating/mandate logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MAHESHWARA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MAHESHWARA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MALAVYA_ARTS_MANDATE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MALAVYA_ARTS_MANDATE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MARS_AMK_ENGINEERING_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MARS_AMK_ENGINEERING_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MARS_ENGINEERING_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MARS_ENGINEERING_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MATERIAL_GRIT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MATERIAL_GRIT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MATRIKARAKA_FIELD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'MATRIKARAKA_FIELD' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MD_AD_COMPOUND": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MD_AD_COMPOUND' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MERCURY_AMK_TECH_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MERCURY_AMK_TECH_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MERCURY_TECH_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MERCURY_TECH_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MODERNIZE_KARAKAS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'MODERNIZE_KARAKAS' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MOON_ARTS_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MOON_ARTS_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MOON_HUMANITIES_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MOON_HUMANITIES_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MOON_JUPITER_MEDICINE_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MOON_JUPITER_MEDICINE_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MOON_MEDICINE_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MOON_MEDICINE_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MOON_NAKSHATRA_FIRST_CLASS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MOON_NAKSHATRA_FIRST_CLASS' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MOON_NAKSHATRA_KP": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MOON_NAKSHATRA_KP' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.MOON_RASHI_PROPENSITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'MOON_RASHI_PROPENSITY' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.NAKSHATRA_CAREER": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'NAKSHATRA_CAREER' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.NATHONNATHA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'NATHONNATHA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.NB_MARS_YK_BROAD_ENGINEERING_RESTORE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'NB_MARS_YK_BROAD_ENGINEERING_RESTORE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.NB_MARS_YK_ENGINEERING_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'NB_MARS_YK_ENGINEERING_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.NIPUNA_YOGA": {
        "school": "Parashari (a named variant of Budha-Aditya Yoga)",
        "source": "Nipuna Yoga = Sun-Mercury conjunction where Mercury avoids combustion (distance/retrograde/exaltation); confirmed via web search (satyori.com, jothishi.com) as a recognized classical sub-case of Budhaditya Yoga",
        "statement": "Sun-Mercury conjunction where Mercury avoids combustion -- Nipuna Yoga.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.NODAL_AXIS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'NODAL_AXIS' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PADA_DISCRIMINATOR": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'PADA_DISCRIMINATOR' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PANCHANGA_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring construct. Classical base: the Panchanga limbs (tithi/vara/nakshatra/yoga/karana) and their ruling lords are a well-established classical concept, but applying a given limb's lord to a career-domain score is this engine's own construct.",
        "statement": "Modern construct applying a classical Panchanga limb's ruling lord to career-domain scoring -- not itself a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PEAK_MD_BOOST": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'PEAK_MD_BOOST' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PERSON_ARCHETYPE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'PERSON_ARCHETYPE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PISCES_BENEFIC_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'PISCES_BENEFIC_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PK_CREATIVE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'PK_CREATIVE' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PRD_BOOST": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'PRD_BOOST' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PRIME_DASHA_AFFINITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'PRIME_DASHA_AFFINITY' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PUSHKARA_NAVAMSHA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'PUSHKARA_NAVAMSHA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.PUTRAKARAKA_FIELD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Chara Karaka scheme (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka) per the Jaimini Sutras; confirmed via web search (askastrologer.com, jyotishabharati.com Jaimini astrology notes PDF)",
        "statement": "Modern construct 'PUTRAKARAKA_FIELD' built on the classical Jaimini Chara Karaka scheme (Atmakaraka/Amatyakaraka/Bhratrikaraka/Matrikaraka/Putrakaraka/Gnatikaraka/Darakaraka) -- the specific domain-mapping, house-scoring, combustion-penalty or 'mandate' logic applied to a given karaka is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.RAHU_CAREER_H10H6": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'RAHU_CAREER_H10H6' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.RAHU_H10_YOGA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'RAHU_H10_YOGA' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.RAJ_YOGA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'RAJ_YOGA' (jyotish/field_methods/jaimini.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.RISK_APPETITE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'RISK_APPETITE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.RULING_PLANETS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'RULING_PLANETS' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.RULING_PLANETS_UNCONFIRMED": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'RULING_PLANETS_UNCONFIRMED' (jyotish/field_methods/kp.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/kp.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.SARASWATI_YOGA": {
        "school": "classical (Phaladeepika / Jataka Parijata)",
        "source": "Saraswati Yoga (Mantreswara, Phaladeepika) -- Jupiter, Mercury and Venus in kendra/trikona/2nd house, with Jupiter well placed; confirmed via web search (sanatanveda.com summarizing Phaladeepika's formulation; Jataka Parijata cited for a 2nd-house-centric variant)",
        "statement": "Jupiter, Mercury and Venus in kendra/trikona/2nd -- Saraswati Yoga.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.SATURN_AK_ENGINEERING_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'SATURN_AK_ENGINEERING_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.SATURN_AMK_ENGINEERING_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'SATURN_AMK_ENGINEERING_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.SAV_BINDU_FACTOR": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'SAV_BINDU_FACTOR' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.SPACE_AEROSPACE_CLUSTER": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'SPACE_AEROSPACE_CLUSTER' (jyotish/field_methods/jaimini.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.SPIRITUAL_PROXY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'SPIRITUAL_PROXY' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.SREE_LAGNA": {
        "school": "Parashari in origin, Jaimini in common use (Vishesha Lagna)",
        "source": "Special lagnas (Bhava/Hora/Ghati/Sree Lagna) are documented in Parashari literature (BPHS) and used heavily in Jaimini-school practice; confirmed via web search (paramarsh.app 'Jaimini Special Lagnas', barbarapijan.com); exact BPHS verse numbers were not independently confirmed in this session",
        "statement": "Sree Lagna, a classical Vishesha (special) Lagna.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.STELLIUM": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'STELLIUM' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.SUDARSHANA": {
        "school": "attributed to Parashara (BPHS) per secondary sources",
        "source": "Sudarshana Chakra (combined Lagna/Moon/Sun chart analysis) is described by multiple secondary sources as a BPHS technique (also referenced in Phaladeepika and Jataka Parijata per web search of instaastro.com/futuresobright.com), but this session could not independently retrieve the primary BPHS verse; treated as attributed-but-not-independently-verified",
        "statement": "Sudarshana Chakra: combined analysis of Lagna, Moon and Sun charts as simultaneous reference points.",
        "implementation": "jyotish/engine.py",
        "confidence": "attributed_not_independently_verified",
    },
    "SIGNAL.TRIKONA_SHODHANA": {
        "school": "Parashari (BPHS Ch.5, Ashtakavarga reduction)",
        "source": "Trikona Shodhana (trine normalization of raw Bhinnashtakavarga bindus) "
                  "is a well-attested classical reduction step described across standard "
                  "Ashtakavarga secondary literature and matched by common Jyotish software "
                  "convention (the same class of source already used for this module's bindu "
                  "tables, see jyotish/ashtakavarga.py module docstring); this session did not "
                  "independently retrieve a primary BPHS verse pinning the exact "
                  "subtract-the-group-minimum arithmetic implemented, so this is treated as "
                  "attributed-but-not-independently-verified for the precise mechanics, while "
                  "the existence and purpose of the reduction step itself is well attested.",
        "statement": "Within each trikona group of houses (1-5-9, 2-6-10, 3-7-11, 4-8-12), "
                     "every house's Bhinnashtakavarga bindu count is reduced by the minimum "
                     "bindu count found anywhere in that same group.",
        "implementation": "jyotish/ashtakavarga.py:apply_trikona_shodhana",
        "confidence": "attributed_not_independently_verified",
    },
    "SIGNAL.EKADHIPATYA_SHODHANA": {
        "school": "Parashari (BPHS Ch.5, Ashtakavarga reduction)",
        "source": "Ekadhipatya Shodhana (same-lord-house normalization) is a well-attested "
                  "classical reduction step for planets ruling two signs (every graha except "
                  "Sun/Moon); this session did not independently retrieve a primary BPHS verse "
                  "pinning the exact reduce-the-lower-house-to-zero arithmetic implemented, so "
                  "this is treated as attributed-but-not-independently-verified for the precise "
                  "mechanics, while the existence and purpose of the reduction step itself is "
                  "well attested across standard Ashtakavarga secondary literature.",
        "statement": "For any planet ruling two houses (via whole-sign houses from Lagna), if "
                     "the Bhinnashtakavarga bindu counts in its two ruled houses are unequal, "
                     "the house with the lower count is reduced to zero.",
        "implementation": "jyotish/ashtakavarga.py:apply_ekadhipatya_shodhana",
        "confidence": "attributed_not_independently_verified",
    },
    "SIGNAL.SUN_LEADERSHIP_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'SUN_LEADERSHIP_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.TRANSIT_ACTIVATION": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'TRANSIT_ACTIVATION' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.TRIKONA_UNITY": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring construct. Classical base: trikona (1st/5th/9th trine) houses are a well-established Parashari significance category (common knowledge, not requiring a specific citation beyond the general Parashari trikona doctrine), but the 'unity'/agreement scoring across trikona houses used here is this engine's own construct.",
        "statement": "Modern scoring construct measuring agreement/convergence across the classical trikona (trine) houses -- not itself a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.UL_LORD": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Upapada Lagna = Arudha of the 12th house, treated in the Jaimini Sutras (4th quarter, marriage/spouse section per search summary of lakshminarayanlenasia.com Jaimini Sutras text); confirmed via web search",
        "statement": "Modern construct: lord of the classical Jaimini Upapada Lagna (Arudha of the 12th) evaluated for career scoring -- applying UL-lord strength to a career field is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.UPAPADA": {
        "school": "Jaimini",
        "source": "Upapada Lagna = Arudha of the 12th house, treated in the Jaimini Sutras (4th quarter, marriage/spouse section per search summary of lakshminarayanlenasia.com Jaimini Sutras text); confirmed via web search",
        "statement": "Upapada Lagna = Arudha of the 12th house (Jaimini marriage/livelihood indicator).",
        "implementation": "jyotish/field_methods/jaimini.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.VASUMATI_YOGA": {
        "school": "Parashari (classical, exact source text not pinned)",
        "source": "Benefics (Jupiter/Venus/Mercury) in Upachaya houses (3/6/10/11) from Lagna or Moon form Vasumati Yoga; confirmed via web search (sanatanveda.com, vedicmystics.com) quoting a classical verse in translation, but the search did not surface a specific BPHS chapter/verse citation",
        "statement": "Benefics in Upachaya houses (3/6/10/11) from Lagna/Moon -- Vasumati Yoga.",
        "implementation": "jyotish/field_methods/parashara.py",
        "confidence": "classically_attested_source_text_not_pinned",
    },
    "SIGNAL.VENUS_ARTS_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'VENUS_ARTS_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.VENUS_ARTS_FORCE_AMK": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'VENUS_ARTS_FORCE_AMK' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.VENUS_DESIGN_FORCE": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'VENUS_DESIGN_FORCE' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.VIMSHOPAKA_AK_PCT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'VIMSHOPAKA_AK_PCT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.VIMSHOPAKA_H10_LORD_PCT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'VIMSHOPAKA_H10_LORD_PCT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.VIMSOPAKA_BALA": {
        "school": "Parashari",
        "source": "See RULE_REGISTRY['VIMSHOPAKA.DASAVARGA_WEIGHTS'] in this same file -- this SIGNAL id is the engine-emitted duplicate of the same classical Vimshopaka Bala (Dasavarga weight table, BPHS Ch.6) concept, computed in field_methods/dashamsha.py.",
        "statement": "Vimshopaka Bala: cumulative divisional-chart strength scored out of 20 across a weighted set of vargas.",
        "implementation": "jyotish/field_methods/dashamsha.py",
        "confidence": "well_attested for the weight table itself (see cross-referenced entry)",
    },
    "SIGNAL.VIPARITA_RAJA_YOGA": {
        "school": "classical (Phaladeepika; also discussed in later Parashari-tradition works)",
        "source": "Viparita Raja Yoga (Harsha/Sarala/Vimala) -- 6th/8th/12th lord placed in another dusthana; Harsha Yoga specifically cited to Phaladeepika Ch.6 sloka 63 in web search results",
        "statement": "6th/8th/12th lord placed in another dusthana -- Viparita Raja Yoga.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.VIRODHA_ARGALA": {
        "school": "Jaimini",
        "source": "Argala / Virodhargala (counter-argala) doctrine from the Jaimini Sutras -- planets in 2nd/4th/11th (and 5th) from a house provide argala, with 3rd/10th/12th planets providing virodhargala that can cancel it; confirmed via web search (askastrologer.com Jaimini guide)",
        "statement": "Virodhargala: planets in 3rd/10th/12th that can cancel/obstruct an Argala.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested",
    },
    "SIGNAL.WAR_WINNER_DOMAIN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'WAR_WINNER_DOMAIN' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.WHOLE_SIGN_CAREER": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'WHOLE_SIGN_CAREER' (jyotish/field_methods/knrao.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/field_methods/knrao.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.YOGA": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal 'YOGA' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.YOGAKARAKA": {
        "school": "Parashari (BPHS)",
        "source": "Yogakaraka: a single planet ruling both a kendra (1/4/7/10) and a trikona (1/5/9) house is a first-rate functional benefic; BPHS Ch.34 cited in web search summary (grokipedia.com Yoga-karakas page), though the primary verse text was not independently retrieved in this session",
        "statement": "A single planet ruling both a kendra and a trikona house -- Yogakaraka, a first-rate functional benefic.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_chapter_area_only",
    },
    "SIGNAL.YOGAKARAKA_DEB_PEN": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Yogakaraka: a single planet ruling both a kendra (1/4/7/10) and a trikona (1/5/9) house is a first-rate functional benefic; BPHS Ch.34 cited in web search summary (grokipedia.com Yoga-karakas page), though the primary verse text was not independently retrieved in this session",
        "statement": "Modern scoring construct 'YOGAKARAKA_DEB_PEN' built on the classical Yogakaraka concept (planet ruling both a kendra and a trikona) -- the specific penalty/varga-application logic is this engine's own construct, not a classical formula.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL.YOGI_AVAYOGI": {
        "school": "traditional Panchanga/Muhurta literature",
        "source": "Yogi point = Sun+Moon longitude + 93d20' (start of Pushya); Avayogi = lord of the 6th nakshatra from the Yogi nakshatra. Confirmed via web search (timelineastrology.com, barbarapijan.com) as a standard traditional Panchanga-derived technique (the Yoga limb / Nithya Yoga scheme); not confirmed as appearing in BPHS itself -- attested in later Panchanga/Muhurta compilations",
        "statement": "Yogi/Avayogi points derived from Sun+Moon longitude and the Panchanga Yoga limb.",
        "implementation": "jyotish/engine.py",
        "confidence": "classically_attested_secondary_literature",
    },
    "SIGNAL._CONFIDENCE_LABEL": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal '_CONFIDENCE_LABEL' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL._CONVERGENCE_COUNT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal '_CONVERGENCE_COUNT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL._CONVERGENCE_MULT": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal '_CONVERGENCE_MULT' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL._SOUL_STACK_CAP": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of classical inputs (see 'statement')",
        "statement": "Engine-internal signal '_SOUL_STACK_CAP' (jyotish/engine.py) is a modern scoring/engineering construct (bonus, penalty, gate, multiplier, domain-mapping, confidence label, or convergence/cluster arithmetic) built on top of classical chart inputs; it is not itself a discrete classical rule with an independent citation.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
    "SIGNAL._SUDARSHANA_LAYERS": {
        "school": "modern_engineering_or_unclassified",
        "source": "N/A -- not a discrete classical rule; modern scoring/engineering construct built on top of a classical input (see 'statement'). Classical base: Sudarshana Chakra (combined Lagna/Moon/Sun chart analysis) is described by multiple secondary sources as a BPHS technique (also referenced in Phaladeepika and Jataka Parijata per web search of instaastro.com/futuresobright.com), but this session could not independently retrieve the primary BPHS verse; treated as attributed-but-not-independently-verified",
        "statement": "Modern construct counting/weighting how many of the Lagna/Moon/Sun Sudarshana reference charts agree ('layers') -- the layering/weighting logic itself is this engine's own scoring construct built on the classical Sudarshana Chakra concept.",
        "implementation": "jyotish/engine.py",
        "confidence": "modern_heuristic",
    },
}


def _register_all_emitted_signals() -> None:
    """Guarantee provenance coverage for every statically emitted component.

    Coverage is distinct from classical attestation: previously-unregistered
    signals are explicitly classified as modern/unreviewed and retain
    SOURCE_NOT_ESTABLISHED until a source excerpt is reviewed.
    """
    root = Path(__file__).resolve().parent
    patterns = (
        re.compile(r'gap_detail\[\s*["\']([^"\']+)["\']\s*\]'),
        re.compile(r'components\[\s*["\']([^"\']+)["\']\s*\]'),
    )
    # GAP-FIX (2026-07-20, signal-class exposure pass): field_methods/ moved
    # from jyotish/field_methods/ to Field_Determination/field_methods/ during
    # a later repo split (commit a7b280d). The old hardcoded path silently
    # globbed to nothing after that move, so every component key emitted by
    # knrao.py/kp.py/jaimini.py/parashara.py/dashamsha.py has been getting
    # NO provenance coverage at all (not even the UNREVIEWED_PROVENANCE
    # fallback) since the split -- this is the same class of stale-path bug
    # documented for the earlier consolidated audit's grep checks. Point at
    # both the current field_methods location and the repo root's
    # Job_Career/timeline.py, which also emits components[...]/gap_detail[...]
    # literals for career-timeline signals.
    _candidate_dirs = [
        root / "field_methods",                                    # legacy, kept in case it's restored
        root.parent / "Field_Determination" / "field_methods",
    ]
    _paths = [root / "engine.py"]
    _field_methods_hits = 0
    for _d in _candidate_dirs:
        if _d.is_dir():
            _found = sorted(_d.glob("*.py"))
            _paths.extend(_found)
            _field_methods_hits += len(_found)

    # Gap-audit fix (2026-08): the hardcoded candidate-dir list above has
    # ALREADY silently broken once (the 2026-07-20 fix above documents that
    # a repo split moved field_methods/ and every emitted signal from
    # knrao.py/kp.py/jaimini.py/parashara.py/dashamsha.py got zero coverage,
    # with no error raised, for as long as the move went unnoticed). A second
    # move (e.g. to a src/ layout, or a package rename) would reproduce the
    # exact same silent failure. Two mitigations, both non-behavior-changing
    # when the hardcoded paths are correct (as they are today):
    #   1. A bounded upward/sideways filesystem search for any sibling
    #      directory literally named "field_methods" that isn't already one
    #      of the candidates above, so a future rename/move is still found.
    #   2. A loud warnings.warn() (not a silent no-op) if, after all of the
    #      above, zero field_methods .py files were located -- so a future
    #      break surfaces as a visible warning at import time instead of a
    #      silent provenance-coverage gap discovered only by manual audit.
    if _field_methods_hits == 0:
        _known = {d.resolve() for d in _candidate_dirs}
        for _sibling in sorted(root.parent.glob("*/field_methods")):
            if _sibling.is_dir() and _sibling.resolve() not in _known:
                _found = sorted(_sibling.glob("*.py"))
                _paths.extend(_found)
                _field_methods_hits += len(_found)
                _known.add(_sibling.resolve())
        if _field_methods_hits == 0:
            warnings.warn(
                "rule_registry._register_all_emitted_signals(): no "
                "field_methods/*.py files found in any candidate location "
                f"({[str(d) for d in _candidate_dirs]}) or via fallback "
                f"sibling search under {root.parent}. Provenance coverage "
                "for every parashara/jaimini/kp/knrao/dashamsha-emitted "
                "signal will silently be missing (same failure class as the "
                "2026-07-20 repo-split incident documented above) unless "
                "this path list is updated to match the current repo "
                "layout.",
                RuntimeWarning,
                stacklevel=2,
            )
    _timeline = root.parent / "Job_Career" / "timeline.py"
    if _timeline.is_file():
        _paths.append(_timeline)
    else:
        warnings.warn(
            f"rule_registry._register_all_emitted_signals(): expected "
            f"timeline file not found at {_timeline}; career-timeline "
            "signals will get no provenance coverage until this path is "
            "corrected.",
            RuntimeWarning,
            stacklevel=2,
        )
    for path in _paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            _impl_path = path.relative_to(root).as_posix()
            _impl_path = f"jyotish/{_impl_path}"
        except ValueError:
            # path lives outside jyotish/ (Field_Determination/, Job_Career/)
            # after the module split -- record relative to the repo root instead.
            _impl_path = path.relative_to(root.parent).as_posix()
        for pattern in patterns:
            for key in pattern.findall(text):
                rule_id = f"SIGNAL.{key.upper()}"
                RULE_REGISTRY.setdefault(rule_id, {
                    "school": "modern_engineering_or_unclassified",
                    "source": "SOURCE NOT ESTABLISHED",
                    "statement": f"Engine-emitted signal '{key}'.",
                    "implementation": _impl_path,
                    "inputs": [], "output": key, "exclusions": [],
                    "implementation_version": RULES_VERSION,
                    "confidence": "UNREVIEWED_PROVENANCE",
                })


_register_all_emitted_signals()


def signal_class(component_key: str) -> str:
    """P0-5 gap-fix: honest three-way classification for a single component/
    trace key, reusing the same source-string logic provenance_coverage()
    already applies chart-wide, but scoped to one signal so callers (results
    builders, reports, LLM prompts) can tag output as factual-calculation vs.
    classical-doctrine vs. modern-heuristic without a full data-model rewrite.

    Returns one of: "classically_sourced", "modern_heuristic",
    "unreviewed_provenance" (registered but not yet source-checked), or
    "source_not_established" (component key not found in the registry at all
    -- should be rare after _register_all_emitted_signals(), but reported
    honestly rather than defaulted to something reassuring-sounding).
    """
    rule_id = f"SIGNAL.{component_key.upper()}"
    entry = RULE_REGISTRY.get(rule_id)
    if not entry:
        return "source_not_established"
    source = entry.get("source", "SOURCE NOT ESTABLISHED")
    confidence = str(entry.get("confidence", ""))
    if source == "SOURCE NOT ESTABLISHED":
        return "unreviewed_provenance" if confidence == "UNREVIEWED_PROVENANCE" else "source_not_established"
    if source.startswith("N/A --"):
        return "modern_heuristic"
    return "classically_sourced"


def lookup_rule(rule_id: str) -> Dict[str, Any]:
    """Returns the registry entry, or a SOURCE NOT ESTABLISHED stub if absent
    -- never fabricates a citation for an unlisted rule."""
    entry = RULE_REGISTRY.get(rule_id)
    if entry:
        return {"rule_id": rule_id, "found": True, **entry}
    return {
        "rule_id": rule_id,
        "found": False,
        "school": "unknown",
        "source": "SOURCE NOT ESTABLISHED",
        "statement": "",
        "implementation": "",
        "confidence": "SOURCE NOT ESTABLISHED",
    }


def build_rule_registry_json(rule_ids: List[str]) -> Dict[str, Any]:
    """Subset of the registry relevant to a given method-trace validation
    call -- fed to the LLM validator as `rule_registry_json`."""
    return {rid: lookup_rule(rid) for rid in rule_ids}


def provenance_coverage() -> Dict[str, Any]:
    """Three-bucket honest coverage report.

    - classically_sourced: entries whose `source` is a real citation (not the
      literal SOURCE NOT ESTABLISHED sentinel, and not this registry's own
      'N/A --' modern-heuristic marker).
    - modern_heuristic: entries explicitly and honestly classified as modern
      engineering/scoring constructs (source begins with 'N/A --'), per the
      2026-07-18 provenance resolution -- NOT counted as classically sourced,
      to avoid inflating the citation count with non-classical rules.
    - source_not_established: entries still carrying the literal sentinel;
      this should be 0 after the 2026-07-18 resolution pass, but is reported
      honestly rather than assumed.

    Backward-compatible keys (`sourced`, `source_not_established`) are kept
    alongside the new three-bucket keys for any existing caller that expects
    the old two-bucket shape; `sourced` under the old definition counts
    anything with a non-sentinel source (classically_sourced + modern_heuristic
    combined), which is why the three-bucket keys are the more honest signal.
    """
    total = len(RULE_REGISTRY)
    classically_sourced = 0
    modern_heuristic = 0
    not_established = 0
    for v in RULE_REGISTRY.values():
        source = v.get("source", "SOURCE NOT ESTABLISHED")
        if source == "SOURCE NOT ESTABLISHED":
            not_established += 1
        elif source.startswith("N/A --"):
            modern_heuristic += 1
        else:
            classically_sourced += 1
    sourced = classically_sourced + modern_heuristic
    return {
        "rules_version": RULES_VERSION,
        "registered": total,
        "classically_sourced": classically_sourced,
        "modern_heuristic": modern_heuristic,
        "source_not_established": not_established,
        "sourced": sourced,
        "coverage_complete": True,
    }
