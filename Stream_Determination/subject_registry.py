"""Static data: the 3 broad post-10th streams + subjects under each.

Deliberately small and hand-curated (unlike jyotish/india_course_registry_v12.json's
199 vocational branches) -- at under-15, the only real-world decision point is
the 3-way Science / Commerce / Humanities stream choice, and which subjects
within a stream to prioritise. Each subject carries a planet-weight signature
used by stream_scoring.py to rank subjects within a stream from the chart's
own planetary strengths -- the same "planet -> aptitude" idea as
Field_Determination/competency_ontology.py's COMPETENCY_META, scaled down.

Weights are ENGINEERED (this codebase's own reasonable reading of classical
significators), not a literal classical rubric -- see constants.py's
(A) CLASSICAL / (B) ENGINEERED provenance note for the same distinction
applied here.

THIS IS THE PRIMARY RULE SOURCE (documentation note, added 2026-07-24
audit): STREAM_META below (its "planets"/"houses"/"house_weights" per
stream) is what actually drives planetary_strength and house_support --
and, transitively through those, most of the rest of the score -- for every
report stream_scoring.py produces. This is distinct from
field_stream_mapping.py's FIELD_STREAM_AFFINITY/DOMAIN_STREAM_AFFINITY,
which despite its name/docstring is NOT the production rule source; it only
feeds an optional experimental section (field_derived_stream.py, default
OFF) and a report-only cross-check (cross_validate.py). See
field_stream_mapping.py's own module docstring for the full explanation --
if you're trying to understand or change what makes a chart score toward a
given stream, this file (STREAM_META) is the one to read/edit.
"""
from __future__ import annotations

from typing import Any, Dict, List

STREAM_SCIENCE = "science"
STREAM_COMMERCE = "commerce"
STREAM_HUMANITIES = "humanities"

STREAM_META: Dict[str, Dict[str, Any]] = {
    STREAM_SCIENCE: {
        "label": "Science",
        "planets": {"Mars": 0.30, "Sun": 0.20, "Saturn": 0.25, "Mercury": 0.25},
        # 2026-07-22 audit fix (gap 10): Science's house ontology was too
        # narrow (3/5/9 only), missing several houses a real technical/
        # engineering chart routinely shows strength through: H6 (technical
        # service, routines, problem-solving), H8 (deep investigation,
        # research, transformation), H11 (systems, networks, large-scale
        # engineering outcomes). Added at modest weights -- H11 in
        # particular is a UNIVERSAL house (same reasoning as Commerce's
        # gap-9 fix), so it is capped low here too rather than counted at
        # full strength.
        # 2026-07-22b correction: an earlier version of this fix added H11
        # too, on top of H6/H8 -- but that made Science's house list cover
        # HALF the chart, which let house_support saturate almost regardless
        # of what a chart's houses actually show (confirmed live: Ramsunder's
        # house_support hit near its cap on both Science and an even-more-
        # expanded Humanities, making the two indistinguishable on that
        # section). Dropped H11 (the weakest, most "universal" of the three
        # additions) to keep this expansion genuinely selective rather than
        # accidentally re-broadening the house list back toward "most houses
        # count for most streams," which is exactly what gap 9's fix was
        # trying to undo in the first place.
        "houses": [3, 5, 6, 8, 9],
        "house_weights": {3: 0.85, 5: 0.90, 6: 0.50, 8: 0.50, 9: 0.50},
        "description": (
            "Analytical/technical aptitude -- precision (Mercury), execution and "
            "rigor (Mars/Saturn), and native intelligence/vitality (Sun) applied "
            "to the natural and physical world."
        ),
    },
    STREAM_COMMERCE: {
        "label": "Commerce",
        "planets": {"Mercury": 0.35, "Jupiter": 0.25, "Saturn": 0.25, "Venus": 0.15},
        # 2026-07-22 audit fix: was [2, 5, 9, 11]. The 9th house (dharma, law,
        # higher philosophy/learning) is NOT commerce's classical domain --
        # it's Humanities' (see STREAM_HUMANITIES.houses below), and having
        # both streams share it meant a 9th-house planetary cluster (however
        # governance/law-flavoured in a specific chart) counted identically
        # toward Commerce and Humanities regardless of what it was actually
        # signifying. Replaced with commerce's own classical significator
        # houses: 2nd (wealth/accumulated value), 7th (trade/partnership/
        # exchange), 10th (profession), 11th (gains/income). 5th (general
        # intelligence/education) is intentionally kept out of Commerce too
        # -- it's shared across all three streams already via each stream's
        # own subject list, not via a duplicated house entry here.
        "houses": [2, 7, 10, 11],
        # 2026-07-22 audit fix (gap 9): H10 and H11 are UNIVERSAL houses --
        # career/status and gains/achievement apply to every stream, not
        # commerce specifically (a strong Saturn in H11 can just as easily
        # mean engineering systems, research, or public administration). Cut
        # their weight sharply so a chart with any strong career/achievement
        # signal stops picking up an undeserved Commerce lean; 2nd (wealth,
        # accumulated value) and 7th (trade/exchange/contracts) are genuinely
        # commerce-specific and keep their weight.
        "house_weights": {2: 0.95, 7: 0.70, 10: 0.40, 11: 0.45},
        "description": (
            "Numerate, transactional and structured-value aptitude -- "
            "calculation and trade (Mercury), wealth judgment (Jupiter), "
            "discipline in ledgers/process (Saturn), and exchange/negotiation "
            "sense (Venus)."
        ),
    },
    STREAM_HUMANITIES: {
        "label": "Humanities",
        # 2026-07-22 audit fix: added Sun. Sun (authority, governance, command
        # presence) is a legitimate Humanities-competency signature planet in
        # its own right -- see competency_ontology.py's own
        # "governance_institutions" competency, which already lists Sun
        # alongside Jupiter/Saturn for exactly this reason. Previously Sun
        # was absent from every stream's planet-weight table except Science's,
        # so a chart where Sun is the strongest testimony for a
        # governance/law/public-authority reading (e.g. as 10th lord or
        # Amatyakaraka) contributed nothing to the Humanities score no matter
        # how strong or well-placed it was.
        "planets": {"Moon": 0.25, "Jupiter": 0.25, "Mercury": 0.20, "Venus": 0.15, "Sun": 0.15},
        # 2026-07-22 audit fix (gap 11): was [4,5,9,12] only, missing H3
        # (writing/journalism/communication), H6 (law/disputes/public
        # service), H7 (diplomacy/legal contracts). Added at modest
        # weights; H10/H11 (government/administration, society/political
        # networks) are also genuinely Humanities-relevant per the audit,
        # but are UNIVERSAL houses (same reasoning as Commerce's gap-9 fix)
        # so are capped low rather than counted at full strength. H12 stays
        # weighted down (too broad on its own -- research/foreign/medicine/
        # spirituality/loss all live there too, not just Humanities).
        # 2026-07-22b correction: an earlier version added H3/H6/H7 AND
        # H10/H11 on top of the original [4,5,9,12] -- 9 houses total, nearly
        # the whole chart. Confirmed live on Ramsunder that this let
        # house_support hit 7.84/8 (near-saturated) almost regardless of
        # what the chart actually showed, which defeats house_support's
        # entire purpose as a discriminating signal. Dropped H10/H11 (the
        # two most "universal," least Humanities-specific of the additions,
        # same reasoning as excluding them from Commerce/Science) and H3
        # (the weakest-linked addition); kept H6/H7 (law/disputes and
        # diplomacy/legal-contracts are more distinctively Humanities-
        # relevant than H3's generic communication/effort signification).
        "houses": [4, 5, 6, 7, 9, 12],
        "house_weights": {4: 0.55, 5: 0.80, 6: 0.40, 7: 0.40, 9: 1.00, 12: 0.40},
        "description": (
            "People, society, language, governance and meaning-making "
            "aptitude -- empathy/intuition (Moon), wisdom and broad judgment "
            "(Jupiter), aesthetic/relational sense (Venus), articulate "
            "expression (Mercury), and authority/public leadership (Sun)."
        ),
    },
}

# Each subject: id, label, a planet-weight signature (need not sum to 1 --
# normalized at scoring time), and `core` (True = one of the fixed core
# subjects real CBSE schools require for this stream; False = an optional
# elective offered alongside them). Ordering here is the display default
# order.
#
# 2026-07-22 expansion: filled out each stream's list to match the real CBSE
# Class 11 elective menu (core subjects + the electives most schools actually
# offer alongside them -- see the CBSE-subject-list research this was built
# from). A few electives (Psychology, Physical Education, Legal Studies,
# Entrepreneurship) are genuinely offered as electives in more than one
# stream in real CBSE schools; each stream gets its own entry (distinct id,
# same underlying planetary signature) so a chart's fit for e.g. "Psychology
# as a Science elective" and "Psychology as the Humanities core subject" can
# be ranked independently within their own stream's subject list.
#
# 2026-07-22 `core` flag added: stream_scoring.py's dominant-stream formula
# now folds in an average across ALL of a stream's core subjects (not just
# the top one) plus its single best elective, specifically so a stream
# cannot be crowned dominant (or passed over) purely on its 4 signature
# planets/houses while ignoring what its own core-subject scores actually
# say -- see stream_scoring.py::_subject_evidence_section.
# `shared_elective`: True if the SAME elective (by real-world identity, not
# just by id) is genuinely offered under more than one stream in real CBSE
# schools (Physical Education under all three; Entrepreneurship under
# Commerce+Humanities). 2026-07-22 audit fix (gap 14): a subject offered
# identically everywhere cannot, by definition, distinguish one stream from
# another -- stream_scoring.py's best-elective pick now excludes these, so
# they still display in the subject list (a real, valid choice) but no
# longer inflate whichever stream's "best elective" slot they happen to win.
#
# `mandatory`: the single planet whose weakness should IMPOSE A CEILING on
# this subject's score rather than being averaged away by other strong
# planets. 2026-07-22 audit fix (gaps 16/17): a plain weighted average lets
# a strong secondary planet fully compensate for a weak indispensable one
# (the audit's own worked examples: Sindhuja's Accountancy scored 64.0
# despite Mercury=0.429, carried entirely by Saturn/Venus; Lakshman's
# Business Studies scored 96.2 off an exalted Sun with Mercury doing little
# of the actual work). stream_scoring.py::score_subjects now applies a
# bounded ceiling multiplier when the mandatory planet's strength is below
# the classical minimum-viable baseline (eff_strength < 1.0) -- this is the
# subject-level contraindication channel the audit asked for, scoped to
# each subject's single most indispensable planet rather than a full
# per-subject affliction checklist (aspects/D24/dispositor-affliction
# checks remain future work -- see the conversation's final scope note).
SUBJECT_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
    STREAM_SCIENCE: [
        # 2026-07-22 audit fix (gap 18): was Mars-heavy {Mars:.40,Saturn:.35,
        # Sun:.25}, underweighting Mercury/Rahu for the mathematical/
        # theoretical/frontier-science side of Physics (vs. just hands-on
        # execution). Mandatory=Mercury: theoretical/mathematical reasoning
        # is indispensable to Physics even when Mars/Saturn execution is strong.
        {"id": "physics", "label": "Physics", "core": True, "mandatory": "Mercury",
         "planets": {"Mercury": 0.25, "Mars": 0.25, "Saturn": 0.20, "Sun": 0.15, "Rahu": 0.15}},
        {"id": "chemistry", "label": "Chemistry", "core": True, "mandatory": "Mercury",
         "planets": {"Mercury": 0.35, "Saturn": 0.25, "Mars": 0.20, "Venus": 0.20}},
        # Audit gap 18: added Mars for life-process/anatomy; kept Mercury as
        # mandatory since Class-11 Biology is still heavily analytical/
        # factual-processing, not purely observational.
        {"id": "biology", "label": "Biology", "core": True, "mandatory": "Mercury",
         "planets": {"Moon": 0.30, "Jupiter": 0.25, "Mercury": 0.20, "Mars": 0.15, "Venus": 0.10}},
        {"id": "mathematics", "label": "Mathematics", "core": True, "mandatory": "Mercury",
         "planets": {"Mercury": 0.50, "Saturn": 0.30, "Rahu": 0.20}},
        {"id": "computer_science", "label": "Computer Science", "core": False,
         "planets": {"Mercury": 0.45, "Rahu": 0.35, "Saturn": 0.20}},
        {"id": "biotechnology", "label": "Biotechnology", "core": False,
         "planets": {"Moon": 0.30, "Mercury": 0.30, "Rahu": 0.25, "Mars": 0.15}},
        {"id": "psychology_science", "label": "Psychology (Science elective)", "core": False,
         "mandatory": "Moon",
         "planets": {"Moon": 0.30, "Mercury": 0.25, "Jupiter": 0.20, "Saturn": 0.15, "Ketu": 0.10}},
        {"id": "physical_education_science", "label": "Physical Education", "core": False,
         "shared_elective": True,
         "planets": {"Mars": 0.45, "Sun": 0.30, "Saturn": 0.25}},
    ],
    STREAM_COMMERCE: [
        # 2026-07-22 audit fix (gaps 16/18) -- the flagship worked example:
        # Venus at 25% let Venus+Saturn fully carry Accountancy's score
        # regardless of Mercury. Reduced Venus, raised Mercury, and marked
        # Mercury mandatory so a weak/combust Mercury now imposes a real
        # ceiling -- numerical discrimination and bookkeeping accuracy are
        # not substitutable by Saturn's discipline or Venus's judgment.
        {"id": "accountancy", "label": "Accountancy", "core": True, "mandatory": "Mercury",
         "planets": {"Mercury": 0.55, "Saturn": 0.30, "Venus": 0.15}},
        # 2026-07-22 audit fix (gap 15): Economics under Commerce vs
        # Humanities used to be IDENTICAL weights -- the same astrological
        # object counted as if it were two independent testimonies. Now
        # differentiated: Commerce's Economics leans Mercury/Saturn
        # (markets, business economics, commercial mathematics); Humanities'
        # leans Jupiter/Moon (policy, political economy, social systems) --
        # see economics_humanities below.
        {"id": "economics_commerce", "label": "Economics", "core": True, "mandatory": "Mercury",
         "planets": {"Mercury": 0.40, "Saturn": 0.35, "Jupiter": 0.25}},
        # 2026-07-22 audit fix (gaps 16/18) -- second flagship worked
        # example: an exalted Sun alone drove Business Studies to 96.2 while
        # Mercury (commercial acumen, distinct from Sun's leadership) barely
        # contributed. Reduced Sun's share, raised Mercury, and marked
        # Mercury mandatory -- leadership presence (Sun) supports but cannot
        # substitute for commercial/analytical aptitude.
        {"id": "business_studies", "label": "Business Studies", "core": True, "mandatory": "Mercury",
         "planets": {"Mercury": 0.45, "Jupiter": 0.25, "Sun": 0.30}},
        {"id": "statistics", "label": "Statistics", "core": False,
         "planets": {"Mercury": 0.50, "Saturn": 0.30, "Rahu": 0.20}},
        {"id": "commerce_mathematics", "label": "Mathematics (Commerce)", "core": False,
         "planets": {"Mercury": 0.50, "Saturn": 0.35, "Jupiter": 0.15}},
        {"id": "informatics_practices", "label": "Informatics Practices", "core": False,
         "planets": {"Mercury": 0.45, "Rahu": 0.35, "Saturn": 0.20}},
        {"id": "entrepreneurship_commerce", "label": "Entrepreneurship", "core": False,
         "shared_elective": True,
         "planets": {"Sun": 0.30, "Mars": 0.25, "Mercury": 0.25, "Rahu": 0.20}},
        {"id": "physical_education_commerce", "label": "Physical Education", "core": False,
         "shared_elective": True,
         "planets": {"Mars": 0.45, "Sun": 0.30, "Saturn": 0.25}},
    ],
    STREAM_HUMANITIES: [
        # 2026-07-22 audit fix (gap 18): a strong Ketu alone could carry
        # History to 30% of the score with no memory/interpretive support --
        # added Mercury (interpretation/articulation) and Moon (memory),
        # marked Mercury mandatory.
        {"id": "history", "label": "History", "core": True, "mandatory": "Mercury",
         "planets": {"Saturn": 0.30, "Jupiter": 0.25, "Ketu": 0.20, "Mercury": 0.15, "Moon": 0.10}},
        # Audit gap 18: Mars at 30% could inflate Political Science in
        # purely martial (not constitutional/diplomatic/administrative)
        # charts. Reduced Mars, added Mercury (articulation/debate), kept
        # Saturn (institutions/structure); mandatory=Jupiter (constitutional/
        # governance judgment is the one truly indispensable signal here).
        {"id": "political_science", "label": "Political Science", "core": True, "mandatory": "Jupiter",
         "planets": {"Sun": 0.35, "Jupiter": 0.30, "Mercury": 0.20, "Saturn": 0.15}},
        # Audit gap 18: added Jupiter/Saturn for judgment/discipline
        # differentiation beyond Moon-Mercury-Ketu alone; mandatory=Moon
        # (empathy/intuition is indispensable to Psychology specifically).
        {"id": "psychology", "label": "Psychology", "core": True, "mandatory": "Moon",
         "planets": {"Moon": 0.30, "Mercury": 0.25, "Jupiter": 0.20, "Saturn": 0.15, "Ketu": 0.10}},
        {"id": "sociology", "label": "Sociology", "core": True,
         "planets": {"Moon": 0.35, "Jupiter": 0.35, "Venus": 0.30}},
        # Audit gap 18: Mars at 35% underweighted Mercury/Rahu for mapping/
        # spatial-analysis/earth-systems aspects of Geography specifically
        # (vs. Mars's more generic effort/fieldwork signature); mandatory=
        # Mercury (spatial-analytical capacity).
        {"id": "geography", "label": "Geography", "core": True, "mandatory": "Mercury",
         "planets": {"Saturn": 0.25, "Moon": 0.20, "Mars": 0.20, "Mercury": 0.20, "Rahu": 0.15}},
        {"id": "economics_humanities", "label": "Economics", "core": True,
         "planets": {"Jupiter": 0.45, "Moon": 0.30, "Mercury": 0.25}},
        {"id": "literature_languages", "label": "Literature & Languages", "core": False,
         "planets": {"Venus": 0.45, "Mercury": 0.35, "Moon": 0.20}},
        {"id": "legal_studies", "label": "Legal Studies", "core": False,
         "planets": {"Jupiter": 0.40, "Saturn": 0.35, "Sun": 0.25}},
        {"id": "fine_arts", "label": "Fine Arts", "core": False,
         "planets": {"Venus": 0.50, "Moon": 0.30, "Mercury": 0.20}},
        {"id": "mass_media_journalism", "label": "Mass Media / Journalism", "core": False,
         "planets": {"Mercury": 0.40, "Rahu": 0.30, "Venus": 0.30}},
        {"id": "entrepreneurship_humanities", "label": "Entrepreneurship", "core": False,
         "shared_elective": True,
         "planets": {"Sun": 0.30, "Mars": 0.25, "Mercury": 0.25, "Rahu": 0.20}},
        {"id": "home_science", "label": "Home Science", "core": False,
         "planets": {"Moon": 0.40, "Venus": 0.35, "Mercury": 0.25}},
        {"id": "physical_education_humanities", "label": "Physical Education", "core": False,
         "shared_elective": True,
         "planets": {"Mars": 0.45, "Sun": 0.30, "Saturn": 0.25}},
    ],
}

# 2026-07-22 audit fix (gap 12): a Science student chooses a feasible SUBJECT
# BUNDLE (PCM, PCB, or the heavier PCMB), not an unweighted average across
# Physics+Chemistry+Biology+Mathematics as if all four were being studied
# together as the "Science identity." stream_scoring.py's subject-evidence
# section now scores every bundle below and uses whichever is strongest,
# reporting which one, instead of diluting a clear PCM (or PCB) chart with
# whichever of Biology/Mathematics happens to be weaker.
SCIENCE_SUBJECT_BUNDLES: Dict[str, List[str]] = {
    "PCM": ["physics", "chemistry", "mathematics"],
    "PCB": ["physics", "chemistry", "biology"],
    "PCMB": ["physics", "chemistry", "mathematics", "biology"],
}


def all_streams() -> List[str]:
    return list(STREAM_META.keys())


# GAP-FIX (2026-07-22h, audit gaps 22/23/24): a bare "Science" or
# "Humanities" label hides which flavour of that stream the chart actually
# supports -- Science covers both PCM/engineering and PCB/life-science
# charts equally well by that label alone, and Humanities covers
# governance/law, social-science, and language/arts charts identically.
# This is a lightweight labeling layer, NOT a fourth scoring dimension: it
# reads which core subject(s) actually ranked highest (already computed by
# _subject_evidence_section/SCIENCE_SUBJECT_BUNDLES) and reports the nearest
# named sub-archetype, so the headline stream name carries more information
# without re-architecting STREAM_META/SUBJECT_REGISTRY into sub-streams.
SUBJECT_SUB_ARCHETYPES: Dict[str, str] = {
    # Science
    "physics": "Technical/Engineering", "chemistry": "Technical/Engineering",
    "mathematics": "Technical/Engineering", "computer_science": "Technical/Engineering",
    "biology": "Life Science/Medical", "biotechnology": "Life Science/Medical",
    "psychology_science": "Life Science/Medical",
    # Commerce
    "accountancy": "Finance/Accounting", "business_studies": "Management/Business",
    "economics_commerce": "Finance/Accounting", "statistics": "Finance/Accounting",
    "commerce_mathematics": "Finance/Accounting", "informatics_practices": "Management/Business",
    # Humanities
    "political_science": "Governance/Law", "legal_studies": "Governance/Law",
    "history": "Governance/Law",
    "psychology": "Social Science", "sociology": "Social Science",
    "economics_humanities": "Social Science", "geography": "Social Science",
    "literature_languages": "Language/Arts", "fine_arts": "Language/Arts",
    "mass_media_journalism": "Language/Arts", "home_science": "Language/Arts",
}
