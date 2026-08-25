"""JyotishAI — Shared astrological constants and lookup tables.

GAP-FIX (2026-07, transparency/provenance): this module (and the tuning
constants scattered through engine.py/boosts.py that reference it) mixes two
genuinely different kinds of numbers, and until now nothing distinguished
them in the code. Going forward, every constant added or touched should be
labeled as one of:

  (A) CLASSICAL -- taken directly from a named classical text or a single
      well-established convention (e.g. _EXALT_SIGN/_DEBIL_SIGN degrees from
      BPHS, DASAVARGA_WEIGHTS from BPHS Ch.6 in vimshopaka.py). These are
      not calibrated against outcomes; they are transcriptions of a
      documented source, and disagree with other classical schools only in
      the ordinary way any two classical texts can disagree (each such case
      is flagged inline where it matters, e.g. dignity.py's graha_yuddha
      winner-rule docstring, vimshopaka.py's D60 sign-convention note).

  (B) ENGINEERED -- a weight, cap, decay rate, or blend ratio chosen by this
      codebase's own maintainers (not from a classical text) to make the
      multi-stage scoring pipeline behave sensibly -- things like per-
      component gap-boost caps (_PCC/_D10_PCC in engine.py), the cluster
      vote decay (_CLUSTER_RANK_DECAY), domain blend ratios
      (DOMAIN_STRATEGIES below), and the spread-penalty curve in
      _apply_paradigm_spread_penalty. These numbers are NOT independently
      validated against ground-truth career outcomes (see
      tests/test_career_track_regressions.py and test_backtesting.py for
      the closest thing this repo has to that kind of check -- a small,
      hand-curated set of expected-domain assertions, not a calibration
      study). Treat any (B) constant as "this is the engineering team's
      best judgment for how much weight this signal should carry," not as
      astrological doctrine.

Most of the numeric tables in THIS file specifically are (A) -- signs,
degrees, dignity relationships, and domain-keyword mappings taken from
classical sources or (for the *_DOMAIN keyword tables) a reasonable modern
reading of a classical significator list. Where a table in this file is
itself an engineered scoring knob rather than a classical fact (e.g. the
Dignity Multiplier values below, which ARE a considered translation of
classical dignity into a numeric multiplier but the specific numbers
1.40/1.15/1.25/etc. are this codebase's own choice, not literally printed in
BPHS), that is noted at the specific constant.
"""
from typing import Dict, List, Tuple, Set, Any, Optional

_EXALT_SIGN = {"Sun":"Aries","Moon":"Taurus","Mars":"Capricorn","Mercury":"Virgo",
               "Jupiter":"Cancer","Venus":"Pisces","Saturn":"Libra"}
_DEBIL_SIGN  = {"Sun":"Libra","Moon":"Scorpio","Mars":"Cancer","Mercury":"Pisces",
               "Jupiter":"Capricorn","Venus":"Virgo","Saturn":"Aries"}
_OWN_SIGN    = {"Sun":["Leo"],"Moon":["Cancer"],"Mars":["Aries","Scorpio"],
               "Mercury":["Gemini","Virgo"],"Jupiter":["Sagittarius","Pisces"],
               "Venus":["Taurus","Libra"],"Saturn":["Capricorn","Aquarius"]}
# PROVENANCE: (B) ENGINEERED. The dignity STATES (EXALTED/OWN/etc.) are (A)
# classical; the specific numeric multipliers attached to each state here
# (1.40, 1.15, 0.60, ...) are this codebase's own translation of "how much
# should exaltation strengthen a planet's scoring weight," not a table
# printed in any classical text -- BPHS and other sources describe dignity
# qualitatively (a graded ranking) and via Shadbala's own point system
# (see shadbala.py), not as a single multiplicative scalar like this. Treat
# these specific values as calibrated engineering judgment.
_DIGNITY_MOD = {"EXALTED":1.40,"OWN":1.15,"DEBILITATED":0.60,"NEECHA_BHANGA":1.05,
                "MOOLATRIKONA":1.25,"":1.0}

# ── Retrograde-dignity asymmetry (SHADBALA-FIX-1) ───────────────────────────
# Classical sources (Phaladeepika, Saravali, Uttara Kalamrita) attest that a
# RETROGRADE DEBILITATED planet is treated as strong/cancelled-debility
# ("vakra neecha bhanga") — this direction is well-supported and is kept at
# full EXALTED strength (1.40) below.
# The *reverse* claim — that a retrograde EXALTED planet becomes as weak as a
# debilitated one (previously modelled here as a full swap to 0.60) — is a
# minority/synthesized rule, not a broadly attested classical doctrine. Most
# classical treatments instead note only mild instability/restlessness for a
# retrograde exalted planet, not a collapse to debilitated strength. This
# constant models that softer, asymmetric penalty instead of the old
# full-swap value.
_RETRO_EXALTED_DAMPENED = 1.15

# ── Exact exaltation / debilitation peak degrees (BPHS) ─────────────────────
# The "point" degree is the exact peak of exaltation/debilitation strength
# WITHIN the exaltation/debilitation sign (0-30 scale). Distance from this
# point — not just sign membership — is what classical texts use to grade
# dignity strength (e.g. Sun at 0.5 deg Aries has barely entered the
# exaltation sign and is nowhere near the full exaltation strength Sun
# carries at its exact 10 deg Aries exaltation point).
_EXALT_DEGREE: Dict[str, float] = {
    "Sun": 10.0, "Moon": 3.0, "Mars": 28.0, "Mercury": 15.0,
    "Jupiter": 5.0, "Venus": 27.0, "Saturn": 20.0,
}
# Debilitation point is always 180° opposite the exaltation point, landing
# at the same degree-number within the debilitation sign.
_DEBIL_DEGREE: Dict[str, float] = dict(_EXALT_DEGREE)

# ── Moolatrikona sign + degree range (BPHS Ch.4) ─────────────────────────────
# (sign, start_degree, end_degree) — degrees are WITHIN that sign (0-30).
# Outside this range but still in the MT sign, the planet is simply OWN.
_MOOLATRIKONA: Dict[str, tuple] = {
    "Sun":     ("Leo", 0.0, 20.0),
    "Moon":    ("Taurus", 3.0, 30.0),
    "Mars":    ("Aries", 0.0, 12.0),
    "Mercury": ("Virgo", 15.0, 20.0),
    "Jupiter": ("Sagittarius", 0.0, 10.0),
    "Venus":   ("Libra", 0.0, 15.0),
    "Saturn":  ("Aquarius", 0.0, 20.0),
}

_KENDRA_HOUSES  = frozenset({1, 4, 7, 10})
_TRIKONA_HOUSES = frozenset({1, 5, 9})
_KT_HOUSES      = _KENDRA_HOUSES | _TRIKONA_HOUSES

# ── Systematic karaka-to-field table (BPHS/Jataka Parijata karakatwa) ─────────
# Shared across ALL field-determination methods (jaimini, parashara, dashamsha,
# knrao) so that a classically valid planet-house yoga isn't wasted just because
# a field's id/label doesn't happen to match one of that method's hand-curated
# keyword lists (e.g. Rahu-in-H10 for "quantitative_trading" previously scored
# nothing anywhere outside knrao.py because "trading" wasn't in a keyword list).
# Originally added only to knrao.py; promoted here so every method benefits.
_PLANET_KARAKA_DOMAINS: Dict[str, Set[str]] = {
    "Sun":     {"management", "defense", "administration", "law", "government"},
    "Moon":    {"healthcare", "hospitality", "arts", "public_service"},
    "Mars":    {"engineering", "defense", "surgery", "sports", "law_enforcement"},
    "Mercury": {"commerce", "technology", "science", "communication", "research"},
    "Jupiter": {"law", "education", "management", "finance", "religion"},
    "Venus":   {"arts", "commerce", "hospitality", "diplomacy", "design"},
    "Saturn":  {"engineering", "research", "administration", "labor_service", "agriculture"},
    "Rahu":    {"technology", "science", "research", "foreign_affairs"},
    "Ketu":    {"research", "religion", "healthcare"},
}
# Maps the coarse `domain` argument every score_* function receives onto the
# karaka domain vocabulary above. Domains not present here get no systematic
# bonus and fall back to each method's keyword-based signals only.
_DOMAIN_TO_KARAKA: Dict[str, Set[str]] = {
    "engineering": {"engineering"},
    "medicine": {"healthcare", "surgery"},
    "technology": {"technology"},
    "science": {"science", "research"},
    "law": {"law"},
    "management": {"management", "administration"},
    "research": {"research"},
    "commerce": {"commerce", "finance"},
    "healthcare": {"healthcare"},
    "defense": {"defense", "law_enforcement"},
    "interdisciplinary": {"research", "science"},
}

# ── Ontology fix (audit): house-signification-first primitive ───────────────
# The core field-determination signal (BRANCH_PLANET_AFFINITY dot product in
# affinity.py) is a karaka-match model: "which planets are strong, and which
# fields does classical literature associate with those planets." Classical
# field determination is supposed to run primarily through HOUSES (2nd/6th/
# 10th/11th and their field-relevant sub-significations), with karakas as
# corroboration -- not the reverse. House-linkage previously only re-entered
# each method through fragile, hand-curated field-*label* keyword gates
# (e.g. knrao.py's _SERVICE_FIELDS_KN, kp.py's _is_earth_field), which the
# methods' own comments acknowledge: a field whose id/label doesn't contain
# the right substring gets no signal from an otherwise-valid house yoga.
#
# This maps each coarse `domain` bucket (same vocabulary as _DOMAIN_TO_KARAKA
# above) to the houses classically significant for THAT vocation beyond the
# universal 2nd (livelihood) / 10th (karma) / 11th (gains) -- which every
# method already scores directly via h10_lord/h2/h11 checks, so they are
# deliberately excluded here to avoid re-scoring the same universal fact a
# second time under a different name:
#   3  = skill, effort, hands-on craft/courage
#   5  = intelligence, analysis, creative self-expression, students/teaching
#   6  = service, disease, disputes/litigation, daily labor
#   7  = partnerships, contracts, trade, the "other party"
#   8  = deep/hidden investigation, surgery, transformation, occult
#   9  = dharma, higher learning, publishing, guru-disciple transmission
#   12 = institutions (hospitals/ashrams/foreign postings), solitary service
# Domains absent here fall back to the domain-agnostic universal houses only
# (still scored elsewhere), not to zero.
_DOMAIN_HOUSE_SIGNIFICATORS: Dict[str, Set[int]] = {
    "engineering":       {3, 6},
    "medicine":          {6, 8, 12},
    "healthcare":        {6, 8, 12},
    "technology":        {3, 8},
    "science":           {5, 8},
    "research":          {8, 12},
    "law":               {6, 7, 9},
    "management":        {7},
    "commerce":          {7},
    "defense":           {3, 6, 8},
    "interdisciplinary": {5, 8, 9},
}

# ── Reduced Vimshopaka Bala weights ───────────────────────────────────────────
# Classical Vimshopaka Bala aggregates dignity across 16 divisional charts
# (D1,D2,D3,D4,D7,D9,D10,D12,D16,D20,D24,D27,D30,D40,D45,D60 — weights below).
# This pipeline only actually computes D1/D3/D9/D10/D20/D24/D30, so the
# per-planet coefficient is built from that subset (normalized by the weights
# that are actually present) rather than padding missing vargas with a fake
# "neutral" value that would silently dilute the signal toward 0.5 for every
# chart. This is a reduced/practical Vimshopaka Bala, not the full 16-varga
# classical one — documented as such wherever it's used.
_VIMSOPAKA_WEIGHTS_FULL: Dict[str, int] = {
    "D1": 6, "D2": 2, "D3": 4, "D4": 1, "D7": 1, "D9": 3,
    "D10": 5, "D12": 2, "D16": 2, "D20": 2, "D24": 2, "D27": 3,
    "D30": 5, "D40": 4, "D45": 3, "D60": 5,
}
_VIMSOPAKA_DIG_SCORE: Dict[str, float] = {
    "exalted": 1.0, "moolatrikona": 0.875, "own": 0.75,
    "friendly": 0.50, "neutral": 0.375, "enemy": 0.25,
    "debilitated": 0.125, "fallen": 0.125,
}
_DUSTHANA_HOUSES= frozenset({6, 8, 12})

_SIGN_NUM = {"Aries":1,"Taurus":2,"Gemini":3,"Cancer":4,"Leo":5,"Virgo":6,
             "Libra":7,"Scorpio":8,"Sagittarius":9,"Capricorn":10,"Aquarius":11,"Pisces":12}
_SIGN_LORD = {"Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
              "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
              "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter"}
_COMBUST_ORB = {"Moon":12,"Mars":17,"Mercury":14,"Jupiter":11,"Venus":10,"Saturn":15}

# ── Classical (BPHS Ch.5) Naisargika (natural) planetary friendship table ───
# V1.3 merge plan item 1: ported so jyotish/dignity.py's GREAT_FRIEND/FRIEND/
# NEUTRAL/ENEMY/GREAT_ENEMY relationship logic has a source table to read
# from -- this engine had no such table before (only own/exalt/debil/
# moolatrikona). Naisargika (natural, fixed) relationships only -- temporal
# (tatkalika, house-distance-based) friendship is intentionally out of scope.
_NATURAL_FRIENDS: Dict[str, Set[str]] = {
    "Sun":     {"Moon", "Mars", "Jupiter"},
    "Moon":    {"Sun", "Mercury"},
    "Mars":    {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus":   {"Mercury", "Saturn"},
    "Saturn":  {"Mercury", "Venus"},
    "Rahu":    {"Venus", "Saturn"},
    "Ketu":    {"Venus", "Saturn"},
}
_NATURAL_ENEMIES: Dict[str, Set[str]] = {
    "Sun":     {"Venus", "Saturn"},
    "Moon":    set(),
    "Mars":    {"Mercury"},
    "Mercury": {"Moon"},
    "Jupiter": {"Mercury", "Venus"},
    "Venus":   {"Sun", "Moon"},
    "Saturn":  {"Sun", "Moon", "Mars"},
    "Rahu":    {"Sun", "Moon"},
    "Ketu":    {"Sun", "Moon"},
}
_NODAL_DEFAULT_VIRUPAS = 300.0
_PLANET_MIN_SHADBALA: Dict[str, float] = {
    "Sun":390.0,"Moon":360.0,"Mars":300.0,"Mercury":420.0,  # FIX-1: classical standard 390
    "Jupiter":390.0,"Venus":330.0,"Saturn":300.0,"Rahu":300.0,"Ketu":300.0,
}
# K.N. Rao / Jaimini Rasi Drishti (Sign Aspects)
_JAIMINI_RASI_DRISHTI = {
    "Aries":       ["Leo", "Scorpio", "Aquarius"],
    "Taurus":      ["Cancer", "Libra", "Capricorn"],
    "Gemini":      ["Virgo", "Sagittarius", "Pisces"],
    "Cancer":      ["Scorpio", "Aquarius", "Taurus"],
    "Leo":         ["Libra", "Capricorn", "Aries"],
    "Virgo":       ["Gemini", "Sagittarius", "Pisces"],
    "Libra":       ["Aquarius", "Taurus", "Leo"],
    "Scorpio":     ["Capricorn", "Aries", "Cancer"],
    "Sagittarius": ["Gemini", "Virgo", "Pisces"],
    "Capricorn":   ["Taurus", "Leo", "Scorpio"],
    "Aquarius":    ["Aries", "Cancer", "Libra"],
    "Pisces":      ["Gemini", "Virgo", "Sagittarius"]
}
_NAKSHATRA_LORD: Dict[str, str] = {
    "Ashwini":"Ketu","Bharani":"Venus","Krittika":"Sun","Rohini":"Moon",
    "Mrigashira":"Mars","Ardra":"Rahu","Punarvasu":"Jupiter","Pushya":"Saturn",
    "Ashlesha":"Mercury","Magha":"Ketu","Purva Phalguni":"Venus",
    "Uttara Phalguni":"Sun","Hasta":"Moon","Chitra":"Mars","Swati":"Rahu",
    "Vishakha":"Jupiter","Anuradha":"Saturn","Jyeshtha":"Mercury","Mula":"Ketu",
    "Purva Ashadha":"Venus","Uttara Ashadha":"Sun","Shravana":"Moon",
    "Dhanishta":"Mars","Shatabhisha":"Rahu","Purva Bhadrapada":"Jupiter",
    "Uttara Bhadrapada":"Saturn","Revati":"Mercury",
}
_FAVORABLE_NAKSHATRA_BASE: Dict[str, float] = {
    "Pushya":1.20,"Rohini":1.15,"Uttara Phalguni":1.10,"Hasta":1.08,"Revati":1.05,
}
_KARAKAMSHA_OCCUPANT_KW: Dict[str, List[str]] = {
    "Jupiter": ["law","education","philosophy","medicine","economics","management","research"],
    "Mercury": ["accounting","data science","communication","law","computer","mathematics","statistics"],
    "Ketu":    ["research","ayurveda","spiritual","occult","engineering","investigation","archaeology"],
    "Venus":   ["arts","design","fashion","music","performing arts","luxury","fine arts","architecture"],
    "Mars":    ["surgery","defence","military","engineering","police","sports","metallurgy"],
    "Saturn":  ["mining","metallurgy","civil","agriculture","industrial","petroleum","materials"],
    "Sun":     ["civil services","administration","medicine","government","leadership","physics"],
    "Moon":    ["nursing","psychology","hospitality","public health","social work","ecology"],
    "Rahu":    ["artificial intelligence","cybersecurity","biotechnology","space","foreign","robotics"],
}

_NEECHA_BHANGA_DATA: Dict[str, Dict[str, str]] = {
    "Sun":     {"debil_sign_lord":"Venus",   "exalt_lord":"Mars"},
    "Moon":    {"debil_sign_lord":"Mars",    "exalt_lord":"Venus"},
    "Mars":    {"debil_sign_lord":"Moon",    "exalt_lord":"Saturn"},
    "Mercury": {"debil_sign_lord":"Jupiter", "exalt_lord":"Venus"},  # FIX-5: Venus exalts in Pisces (Mercury debil sign)
    "Jupiter": {"debil_sign_lord":"Saturn",  "exalt_lord":"Moon"},
    "Venus":   {"debil_sign_lord":"Mercury", "exalt_lord":"Jupiter"},
    "Saturn":  {"debil_sign_lord":"Mars",    "exalt_lord":"Venus"},
}
DOMAIN_STRATEGIES = {
    # w1 = weight on method-score bundle (structural planetary signals)
    # w2 = weight on affinity/aptitude composite (domain cultural fit)
    # Higher w1 = field has clear classical planetary signature (engineering, medicine, defence)
    # Higher w2 = field driven by Venus/Moon cultural affinity (arts, humanities, media)
    "engineering":       {"w1": 0.60, "w2": 0.40, "min_score": 55},
    "science":           {"w1": 0.58, "w2": 0.42, "min_score": 55},
    "technology":        {"w1": 0.50, "w2": 0.50, "min_score": 45},
    "medicine":          {"w1": 0.65, "w2": 0.35, "min_score": 55},
    "law":               {"w1": 0.60, "w2": 0.40, "min_score": 40},
    "humanities":        {"w1": 0.38, "w2": 0.62, "min_score": 35},
    "arts":              {"w1": 0.35, "w2": 0.65, "min_score": 30},
    "commerce":          {"w1": 0.55, "w2": 0.45, "min_score": 50},
    "education":         {"w1": 0.45, "w2": 0.55, "min_score": 40},
    "public":            {"w1": 0.60, "w2": 0.40, "min_score": 40},
    "media":             {"w1": 0.40, "w2": 0.60, "min_score": 35},
    "agriculture":       {"w1": 0.45, "w2": 0.55, "min_score": 40},
    "interdisciplinary": {"w1": 0.42, "w2": 0.58, "min_score": 38},
    "research":          {"w1": 0.55, "w2": 0.45, "min_score": 45},
    "design":            {"w1": 0.38, "w2": 0.62, "min_score": 35},
    "defence":           {"w1": 0.70, "w2": 0.30, "min_score": 50},
}

_VALID_PLANETS = frozenset(("Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"))
_VALID_DOMAINS = frozenset((
    "engineering","science","technology","medicine","law","humanities","arts",
    "commerce","education","public","media","agriculture","research","design",
    "interdisciplinary","defence",
))

_D24_ACADEMIC_KW = ["research","medicine","science","mathematics","biology","chemistry",
                    "physics","philosophy","education","academia","law","psychology",
                    "biotechnology","statistics","ayurveda","pharmacy"]
_H12_FIELDS = ["research","forensic","hospital","medicine","psychology","spiritual","alternative","international","investigation","hidden"]
_H6_FIELDS  = ["medicine","defence","military","nursing","service","public health"]
_H9_FIELDS  = ["law","philosophy","international","education","research","academia","theology","journalism"]
_H5_FIELDS  = ["research","mathematics","science","medicine","education","physics","statistics","data","artificial intelligence","philosophy","psychology","computer","analytics","chemistry","biology","biotechnology","law"]
_FRONTIER_KW    = ["artificial intelligence","cybersecurity","space","robotics","nuclear","forensic","biotechnology","astrophysics","genetic","performing arts","investigative","journalism","biomedical","environmental science"]
_TRADITIONAL_KW = ["commerce","accounting","education teaching","civil services","law llb","medicine mbbs","business management","agriculture"]
_H9_STELLIUM_KW = ["philosophy","law","research","academia","international","medicine","higher","education","space","religion","theology","journalism","science","psychology","sociology"]
_H12_STELLIUM_KW= ["research","forensic","hospital","medicine","psychology","spiritual","alternative","investigat"]

_YOGAKARAKA_PLANET: Dict[str, str] = {
    "Taurus":"Saturn","Libra":"Saturn","Cancer":"Mars","Leo":"Mars",
    "Capricorn":"Venus","Aquarius":"Venus",
}
_FUNCTIONAL_TRIKONA_FALLBACK = {
    "Aries":"Sun","Gemini":"Venus","Scorpio":"Moon","Sagittarius":"Sun","Pisces":"Moon","Virgo":"Venus"
}

_ALL_PLANETS_SET = frozenset(("Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"))

_DUSTHANA_EXEMPT_KW = frozenset([
    "medicine", "surgery", "doctor", "physician", "nursing", "hospital", "clinical",
    "pharmacy", "ayurveda", "public health", "veterinary", "research", "forensic",
    "data", "psychology", "cybersecurity", "analytics", "investigation", "intelligence",
    "economics", "audit", "taxation", "actuary", "insurance", "mining", "archaeology",
    "backend", "law", "legal", "defence", "police", "military",
])

_MAHESHWARA_DOMAIN_KW: Dict[str, List[str]] = {
    # Maheshwara (Jaimini) governs longevity, transformation, and institutional peaks.
    # Jupiter Maheshwara → education, law, philosophy, expansion.
    # Saturn Maheshwara → engineering, materials, construction, agriculture, mining.
    # Venus Maheshwara → arts, design, architecture, luxury.
    "Jupiter": ["law","education","philosophy","medicine","economics","management","research","international","theology"],
    "Mercury": ["data science","computer","mathematics","accounting","statistics","communication","artificial intelligence"],
    "Venus":   ["arts","design","fashion","music","architecture","fine arts","performing arts","real estate","luxury"],
    "Saturn":  ["engineering","mining","civil","metallurgy","agriculture","industrial","petroleum","materials","construction","environment"],
    "Mars":    ["defence","surgery","military","police","sports","mechanical","fire"],
    "Sun":     ["civil services","administration","medicine","government","leadership","physics","energy"],
    "Moon":    ["nursing","psychology","social work","public health","ecology","hospitality","counseling","arts","music","fine arts","performing arts","literature"],
    "Rahu":    ["artificial intelligence","cybersecurity","biotechnology","space","robotics","forensic"],
    "Ketu":    ["research","ayurveda","spiritual","philosophy","archaeology","investigation"],
}

# 2026-08-17 cleanup: this file used to have its own stale copy of
# _maheshwara_lord_bonus() (plain substring keyword matching, no word-boundary
# guard) alongside boosts.py's real one (which uses the word-boundary-safe
# _wm() matcher and is what every live call site actually imports -- see
# jyotish/engine.py and Field_Determination/field_methods/jaimini.py). This
# copy had zero importers anywhere in the repo, so it never affected any
# score; removed as dead code rather than left as a landmine for a future
# import-from-the-wrong-module mistake. See
# md/ENGINE_SIMPLIFICATION_2026-08-17_combustion_unify.md.

_STREAM_MAP = {
    # domain → recommended 11th-12th stream
    "engineering":  "PCM (Physics, Chemistry, Maths)",
    "technology":   "PCM (Physics, Chemistry, Maths)",
    "science":      "PCM / PCB depending on top branch",
    "medicine":     "PCB (Physics, Chemistry, Biology)",
    "commerce":     "Commerce (Accounts, Economics, Business Studies)",
    "law":          "Commerce or Humanities (Political Science, History)",
    "humanities":   "Humanities / Arts stream",
    "arts":         "Humanities / Fine Arts stream",
    "education":    "Humanities or Commerce stream",
    "public":       "Humanities (Political Science, Sociology)",
    "media":        "Humanities or Commerce stream",
    "agriculture":       "PCB (Biology, Chemistry) or PCM",
    "interdisciplinary": "Liberal Arts / PCM or PCB depending on chosen focus",
}

# ── Career Timeline Constants ──────────────────────────────────────────────────

# Vimshottari Dasha: planet → total years in the 120-yr cycle
_VIMSHOTTARI_YEARS: Dict[str, int] = {
    "Ketu":7, "Venus":20, "Sun":6, "Moon":10, "Mars":7,
    "Rahu":18, "Jupiter":16, "Saturn":19, "Mercury":17,
}
# Classical sequence (which nakshatra starts which MD — full cycle order)
_VIMSHOTTARI_ORDER = ["Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury"]

# Functional nature per lagna: 2=Yogakaraka, 1=Benefic, 0=Neutral, -1=Malefic
# Rahu uses Saturn as proxy (classical: Rahu co-lords Aquarius, Saturn-like in function).
# Ketu uses Mars as proxy (classical: Ketu co-lords Scorpio, Mars-like in function).
# At runtime in _score_period, if Rahu/Ketu are the dasha lords, this value is OVERRIDDEN
# using the actual sign lord of the sign they occupy in the natal chart (more accurate).
# The table entries serve as the fallback when planet_signs data is unavailable.
_FUNCTIONAL_NATURE: Dict[str, Dict[str, int]] = {
    #              Sun   Moon  Mars  Merc  Jup   Venus Sat   Rahu  Ketu
    "Aries":       {"Sun":1,  "Moon":0,  "Mars":1,  "Mercury":-1, "Jupiter":1,  "Venus":0,  "Saturn":0,  "Rahu":0,  "Ketu":1},
    "Taurus":      {"Sun":0,  "Moon":0,  "Mars":-1, "Mercury":1,  "Jupiter":-1, "Venus":1,  "Saturn":2,  "Rahu":2,  "Ketu":-1},
    "Gemini":      {"Sun":0,  "Moon":0,  "Mars":-1, "Mercury":1,  "Jupiter":0,  "Venus":1,  "Saturn":0,  "Rahu":0,  "Ketu":-1},
    "Cancer":      {"Sun":0,  "Moon":1,  "Mars":2,  "Mercury":-1, "Jupiter":0,  "Venus":0,  "Saturn":-1, "Rahu":-1, "Ketu":2},
    # Cancer: Jupiter rules H6 (dusthana) + H9 (trikona) → H6 lordship makes it neutral/mixed (0), not purely benefic (1)
    "Leo":         {"Sun":1,  "Moon":-1, "Mars":2,  "Mercury":0,  "Jupiter":0,  "Venus":0,  "Saturn":-1, "Rahu":-1, "Ketu":2},
    # Leo: Jupiter rules H5 (trikona) + H8 (dusthana) → H8 lordship neutralises the trikona benefit → 0
    "Virgo":       {"Sun":-1, "Moon":0,  "Mars":-1, "Mercury":1,  "Jupiter":0,  "Venus":1,  "Saturn":1,  "Rahu":1,  "Ketu":-1},
    "Libra":       {"Sun":0,  "Moon":0,  "Mars":-1, "Mercury":1,  "Jupiter":-1, "Venus":1,  "Saturn":2,  "Rahu":2,  "Ketu":-1},
    "Scorpio":     {"Sun":1,  "Moon":1,  "Mars":1,  "Mercury":-1, "Jupiter":1,  "Venus":-1, "Saturn":0,  "Rahu":0,  "Ketu":1},
    # Scorpio: Sun rules H10 (career kendra) → functionally benefic (1)
    "Sagittarius": {"Sun":1,  "Moon":-1, "Mars":1,  "Mercury":0,  "Jupiter":1,  "Venus":-1, "Saturn":0,  "Rahu":0,  "Ketu":1},
    "Capricorn":   {"Sun":-1, "Moon":-1, "Mars":0,  "Mercury":1,  "Jupiter":-1, "Venus":2,  "Saturn":1,  "Rahu":1,  "Ketu":0},
    "Aquarius":    {"Sun":-1, "Moon":-1, "Mars":0,  "Mercury":1,  "Jupiter":0,  "Venus":2,  "Saturn":1,  "Rahu":1,  "Ketu":0},
    "Pisces":      {"Sun":-1, "Moon":1,  "Mars":1,  "Mercury":0,  "Jupiter":1,  "Venus":-1, "Saturn":-1, "Rahu":-1, "Ketu":1},
}

# Planet weights per company type (for scoring career-activation by employer context)
_JOB_KARAKA_WEIGHTS: Dict[str, Dict[str, float]] = {
    "government":  {"Sun":0.40, "Saturn":0.35, "Jupiter":0.15, "Mars":0.10},
    "psu":         {"Saturn":0.40, "Sun":0.30, "Jupiter":0.20, "Mars":0.10},
    "mnc":         {"Rahu":0.35, "Mercury":0.30, "Saturn":0.20, "Venus":0.15},
    "startup":     {"Rahu":0.40, "Mars":0.30, "Mercury":0.20, "Sun":0.10},
    "private_sme": {"Saturn":0.35, "Mercury":0.30, "Mars":0.20, "Sun":0.15},
    "ngo":         {"Jupiter":0.40, "Moon":0.30, "Venus":0.20, "Mercury":0.10},
    "default":     {"Saturn":0.35, "Mercury":0.25, "Sun":0.20, "Jupiter":0.20},
}

# House roles for job-career timeline (H7 explicitly excluded — business house)
_JOB_HOUSE_ROLE: Dict[int, str] = {
    6:  "service",          # primary: employment, daily work
    10: "career",           # primary: designation, status
    2:  "salary",           # primary: fixed income
    11: "income_gain",      # primary: hike, bonus
    3:  "skills",           # secondary: effort, communication
    1:  "self",             # secondary: initiative, brand
    9:  "senior_mentor",    # secondary: overseas company, mentor, luck
    12: "exit_or_foreign",  # secondary: exit current role, foreign posting
    4:  "stability",        # secondary: comfort, WFH
    5:  "recognition",      # secondary: creative output, appreciation
    8:  "disruption",       # adverse: restructuring, sudden change
}

# Designation levels in seniority order (for gate checks). "senior_manager"
# sits between "manager" and "director" — a distinct level from "manager" so
# 20+ year senior managers aren't silently downgraded to generic manager-tier
# gating/bias (2026-07 fix). Consumers use .index() ordering, not hardcoded
# positions, so inserting a new level here is safe.
_DESIGNATION_LEVELS = ["junior","mid","senior","lead","manager","senior_manager","director","csuite"]

# Employment status values that are ALLOWED (all others → hard block)
_ALLOWED_EMPLOYMENT_STATUS = frozenset([
    "employed",
    "on_notice_period",
    "unemployed",
    "self_employed",
    "business_owner",
    "freelancer",
])

# Desired outcome values
_DESIRED_OUTCOMES = frozenset([
    "promotion","job_change","salary_hike","foreign_posting",
    "leadership_role","stability","return_after_gap",
])


# ---------------------------------------------------------------------------
# FIX-2: Node calculation mode — True vs Mean Rahu/Ketu
# ---------------------------------------------------------------------------
# "TRUE"  — Astronomical true node (oscillates around the mean node due to
#           lunar orbit eccentricity; can differ by up to ±1.5° from mean).
#           This shifts the exact second a planet crosses a KP sub-lord
#           boundary in Prashna and can alter the active nakshatra during
#           fast-moving Moon transits.
# "MEAN"  — Mean node (smoothed; traditional default in most Vedic software).
#
# Set this once here; engine_io.py and prashna.py both read NODE_MODE.
# If your ephemeris source (pyhora / swisseph) exposes a node flag, pass
# NODE_MODE as the toggle argument.
NODE_MODE: str = "TRUE"    # "TRUE" | "MEAN"


# ---------------------------------------------------------------------------
# FIX-1: Gandanta Zone boundaries (sidereal absolute degrees)
# ---------------------------------------------------------------------------
# Gandanta = the 3°20' (= 800' / 3 = 3.333...°) on each side of the
# water-sign → fire-sign junctions.  These junctions correspond to the
# Nakshatra transitions:
#   Ashlesha (Cancer 26°40'–30°) → Magha (Leo 0°–3°20')
#   Jyeshtha (Scorpio 26°40'–30°) → Mula (Sagittarius 0°–3°20')
#   Revati   (Pisces 26°40'–30°) → Ashwini (Aries 0°–3°20')
#
# Each tuple: (zone_start_deg, zone_end_deg, sign_pair_label)
# Degrees are sidereal absolute (0 = Aries 0°).
_GANDANTA_HALF_SPAN: float = 10.0 / 3.0   # 3°20' = 3.333...°
_GANDANTA_JUNCTIONS: tuple = (
    (120.0, "Ashlesha-Magha"),    # Cancer-Leo boundary
    (240.0, "Jyeshtha-Mula"),     # Scorpio-Sagittarius boundary
    (  0.0, "Revati-Ashwini"),    # Pisces-Aries boundary (0°/360°)
)
# Build zone list: (start, end, label)
_GANDANTA_ZONES: list = []
for _gj, _gl in _GANDANTA_JUNCTIONS:
    _start = (_gj - _GANDANTA_HALF_SPAN) % 360
    _end   = (_gj + _GANDANTA_HALF_SPAN) % 360
    _GANDANTA_ZONES.append((_start, _end, _gl))


def is_gandanta(abs_lon: float) -> tuple:
    """Return (True, label, proximity) if abs_lon falls in a Gandanta zone.

    proximity is 0.0 (exact junction) to 1.0 (edge of zone, mildest disruption).
    Returns (False, "", 0.0) if not in any Gandanta zone.
    """
    lon = abs_lon % 360
    for start, end, label in _GANDANTA_ZONES:
        # Handle the 0°/360° wrap-around zone for Revati-Ashwini
        if start > end:   # wrap-around: e.g., 356.667° – 3.333°
            in_zone = (lon >= start) or (lon <= end)
        else:
            in_zone = start <= lon <= end
        if in_zone:
            # Distance to exact junction (midpoint of zone)
            junc = (start + _GANDANTA_HALF_SPAN) % 360
            dist = abs(lon - junc)
            if dist > 180:
                dist = 360 - dist
            proximity = min(dist / _GANDANTA_HALF_SPAN, 1.0)
            return (True, label, proximity)
    return (False, "", 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION IMPLEMENTATION CONSTANTS (10/10 upgrade)
# ══════════════════════════════════════════════════════════════════════════════

# ── Fix 1: Nakshatra career keyword map ──────────────────────────────────────
# Maps each nakshatra to the career domain keywords it amplifies.
# Based on classical Jyotish texts (Brihat Samhita, Hora Sara, BV Raman).
_NAKSHATRA_CAREER_KW: Dict[str, List[str]] = {
    "Ashwini":          ["medicine","surgery","sports","veterinary","emergency","horse","healing","speed"],
    "Bharani":          ["arts","fashion","entertainment","occult","finance","luxury","creative","design"],
    "Krittika":         ["engineering","metallurgy","military","surgery","fire service","cooking","physics","energy"],
    "Rohini":           ["agriculture","arts","beauty","commerce","hospitality","music","design","real estate","food"],
    "Mrigashira":       ["research","exploration","music","travel","journalism","botany","geography","data","writing"],
    "Ardra":            ["research","engineering","destruction","reconstruction","data science","storm","chaos","innovation"],
    "Punarvasu":        ["education","philosophy","law","international","medicine","spirituality","counseling","teaching"],
    "Pushya":           ["government","administration","banking","economics","public service","law","management","civil services"],
    "Ashlesha":         ["law","psychology","chemistry","pharmacy","mysticism","politics","data","research"],
    "Magha":            ["government","leadership","civil services","administration","history","archaeology","management","politics"],
    "Purva Phalguni":   ["arts","music","fashion","entertainment","media","luxury","design","performing arts","film"],
    "Uttara Phalguni":  ["social work","public service","medicine","education","law","government","administration"],
    "Hasta":            ["medicine","nursing","pharmacy","craft","accounting","commerce","data","statistics","surgery"],
    "Chitra":           ["architecture","design","engineering","arts","jewellery","fashion","technology","fine arts"],
    "Swati":            ["international","trade","commerce","law","diplomacy","business","economics","foreign"],
    "Vishakha":         ["law","politics","military","agriculture","chemistry","research","science","engineering"],
    "Anuradha":         ["management","corporate","science","technology","friendship","public relations","engineering"],
    "Jyeshtha":         ["government","security","defence","administration","leadership","management","law enforcement"],
    "Mula":             ["research","philosophy","medicine","ayurveda","agriculture","mining","investigation","archaeology"],
    "Purva Ashadha":    ["water","medicine","international","law","arts","philosophy","teaching","journalism"],
    "Uttara Ashadha":   ["government","civil services","military","research","mathematics","philosophy","law"],
    "Shravana":         ["education","communication","media","music","law","international","technology","journalism"],
    "Dhanishta":        ["music","military","real estate","engineering","construction","metallurgy","sports","management"],
    "Shatabhisha":      ["medicine","research","pharmacy","space","technology","healing","astronomy","data science"],
    "Purva Bhadrapada": ["research","occult","fire service","spiritual","philosophy","engineering","alternative medicine"],
    "Uttara Bhadrapada":["medicine","law","spirituality","social work","philosophy","international","education"],
    "Revati":           ["arts","travel","international","spirituality","marine","psychology","hospitality","music"],
}

# ── Fix 2: Rahu house → career direction keywords ──────────────────────────
_RAHU_HOUSE_CAREER_KW: Dict[int, List[str]] = {
    1:  ["entrepreneurship","innovation","technology","unconventional","leadership","self-made","foreign"],
    2:  ["finance","banking","economics","commerce","accounting","wealth management","taxation"],
    3:  ["media","journalism","communication","technology","marketing","writing","digital","it","data"],
    4:  ["real estate","education","public","agriculture","environmental","psychology","social"],
    5:  ["research","mathematics","data science","artificial intelligence","speculation","creative","innovation"],
    6:  ["medicine","law","defence","military","forensic","cybersecurity","competition","analytics"],
    7:  ["international","business","partnership","law","diplomacy","commerce","consulting","foreign"],
    8:  ["research","forensic","insurance","mining","surgery","investigation","data science","occult","cybersecurity"],
    9:  ["international","philosophy","law","teaching","journalism","higher education","research","space","theology"],
    10: ["engineering","civil services","management","politics","administration","technology","ambition","government"],
    11: ["technology","networks","economics","artificial intelligence","social","data","innovation","finance"],
    12: ["hospital","research","foreign","spiritual","space","alternative medicine","international","psychology"],
}

_KETU_HOUSE_NATURAL_TALENT: Dict[int, List[str]] = {
    1:  ["leadership","medicine","alternative","spiritual","healing"],
    2:  ["arts","music","language","finance","trade"],
    3:  ["communication","writing","martial arts","sports","courage"],
    4:  ["agriculture","real estate","education","psychology","environment"],
    5:  ["mathematics","research","philosophy","teaching","creativity"],
    6:  ["medicine","law","military","healing","competition"],
    7:  ["diplomacy","international","business","counseling","partnership"],
    8:  ["research","occult","investigation","mining","surgery","forensic"],
    9:  ["philosophy","law","spirituality","international","education"],
    10: ["engineering","government","management","administration","leadership"],
    11: ["networks","economics","technology","social","innovation"],
    12: ["spirituality","research","foreign","hospital","meditation","healing"],
}

# ── Fix 8: Pushkara Navamsha degrees (exact degree ranges in D1 sign) ──────
# Source: Pushkara Navamsha table from Jyotish classics.
# Each entry: {sign: [(start_degree, end_degree), ...]}
# Planets within these degree ranges are in Pushkara Navamsha — exceptional results.
_PUSHKARA_NAVAMSHA: Dict[str, List[tuple]] = {
    "Aries":       [(19.0, 23.33)],           # pada 3 (Gemini navamsha)
    "Taurus":      [(23.33, 26.67)],           # pada 3 (Capricorn navamsha)
    "Gemini":      [(3.33, 6.67), (26.67, 30.0)],  # padas 1+4
    "Cancer":      [(3.33, 6.67)],             # pada 1 (Aries navamsha)
    "Leo":         [(10.0, 13.33)],            # pada 2 (Taurus navamsha)
    "Virgo":       [(16.67, 20.0)],            # pada 3 (Sagittarius navamsha)
    "Libra":       [(3.33, 6.67)],             # pada 1 (Capricorn navamsha)
    "Scorpio":     [(10.0, 13.33)],            # pada 2 (Pisces navamsha)
    "Sagittarius": [(16.67, 20.0)],            # pada 3 (Aries navamsha)
    "Capricorn":   [(3.33, 6.67)],             # pada 1 (Gemini navamsha)
    "Aquarius":    [(10.0, 13.33)],            # pada 2 (Cancer navamsha)
    "Pisces":      [(16.67, 20.0)],            # pada 3 (Libra navamsha)
}

# ── Fix 9: Nakshatra pada → Navamsha sign mapping ──────────────────────────
# Each nakshatra has 4 padas. Pada 1 of Ashwini = Aries navamsha, etc.
# Maps (nakshatra, pada) → navamsha sign for sub-domain discrimination.
_PADA_NAVAMSHA_SIGN: Dict[str, List[str]] = {
    # [pada1_sign, pada2_sign, pada3_sign, pada4_sign]
    "Ashwini":          ["Aries","Taurus","Gemini","Cancer"],
    "Bharani":          ["Leo","Virgo","Libra","Scorpio"],
    "Krittika":         ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Rohini":           ["Aries","Taurus","Gemini","Cancer"],
    "Mrigashira":       ["Leo","Virgo","Libra","Scorpio"],
    "Ardra":            ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Punarvasu":        ["Aries","Taurus","Gemini","Cancer"],
    "Pushya":           ["Leo","Virgo","Libra","Scorpio"],
    "Ashlesha":         ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Magha":            ["Aries","Taurus","Gemini","Cancer"],
    "Purva Phalguni":   ["Leo","Virgo","Libra","Scorpio"],
    "Uttara Phalguni":  ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Hasta":            ["Aries","Taurus","Gemini","Cancer"],
    "Chitra":           ["Leo","Virgo","Libra","Scorpio"],
    "Swati":            ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Vishakha":         ["Aries","Taurus","Gemini","Cancer"],
    "Anuradha":         ["Leo","Virgo","Libra","Scorpio"],
    "Jyeshtha":         ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Mula":             ["Aries","Taurus","Gemini","Cancer"],
    "Purva Ashadha":    ["Leo","Virgo","Libra","Scorpio"],
    "Uttara Ashadha":   ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Shravana":         ["Aries","Taurus","Gemini","Cancer"],
    "Dhanishta":        ["Leo","Virgo","Libra","Scorpio"],
    "Shatabhisha":      ["Sagittarius","Capricorn","Aquarius","Pisces"],
    "Purva Bhadrapada": ["Aries","Taurus","Gemini","Cancer"],
    "Uttara Bhadrapada":["Leo","Virgo","Libra","Scorpio"],
    "Revati":           ["Sagittarius","Capricorn","Aquarius","Pisces"],
}

# Navamsha sign → career keywords (for pada-based sub-domain discrimination)
_NAVAMSHA_SIGN_CAREER_KW: Dict[str, List[str]] = {
    "Aries":       ["engineering","defence","military","surgery","sports","pioneer","mechanical","firefighting"],
    "Taurus":      ["finance","arts","agriculture","luxury","music","beauty","real estate","commerce","design"],
    "Gemini":      ["communication","media","computer","mathematics","journalism","writing","technology","data"],
    "Cancer":      ["nursing","psychology","public","social work","food","hospitality","education","counseling"],
    "Leo":         ["government","administration","leadership","performing arts","management","civil services"],
    "Virgo":       ["medicine","analytics","accounting","law","pharmacy","data","statistics","health","research"],
    "Libra":       ["law","diplomacy","arts","design","hr","international","aesthetics","justice","balance"],
    "Scorpio":     ["research","forensic","mining","investigation","surgery","cybersecurity","psychology","occult"],
    "Sagittarius": ["law","philosophy","international","higher education","theology","sports","research","religion"],
    "Capricorn":   ["engineering","government","construction","agriculture","industrial","infrastructure","mining"],
    "Aquarius":    ["technology","science","innovation","social reform","computer","data","electronics","research"],
    "Pisces":      ["spirituality","arts","medicine","psychology","alternative healing","research","charity","philosophy"],
}

# ── Fix 12: Guna planet assignments ──────────────────────────────────────────
# Sattvic: purity, wisdom, dharma → education, healing, research, spiritual
# Rajasic: ambition, action, leadership → management, engineering, law, business
# Tamasic: patience, persistence, service → research, mining, service, systematic work
_GUNA_PLANETS: Dict[str, List[str]] = {
    "sattvic": ["Jupiter", "Moon", "Sun"],
    "rajasic":  ["Sun", "Mars", "Mercury"],
    "tamasic":  ["Saturn", "Rahu", "Ketu"],
}

_GUNA_FIELD_AFFINITY: Dict[str, List[str]] = {
    "sattvic": ["education","philosophy","medicine","law","research","spirituality","psychology","counseling",
                "theology","ecology","social work","public health","nursing","teaching","humanities"],
    "rajasic":  ["engineering","management","entrepreneurship","civil services","law","business","politics",
                 "defence","surgery","sports","finance","commerce","leadership","media","administration"],
    "tamasic":  ["research","mining","data science","construction","agriculture","industrial","metallurgy",
                 "forensic","cybersecurity","investigation","alternative","archaeology","petroleum","materials"],
}

# ── Fix 13: H6/H8/H12 house → career directive keywords ─────────────────────
_DUSTHANA_CAREER_DIRECTIVE: Dict[int, List[str]] = {
    6:  ["medicine","law","defence","military","nursing","service","competition","public health","veterinary",
         "forensic","policing","sports","rehabilitation","social service"],
    8:  ["research","surgery","mining","insurance","investigation","forensic","psychology","occult",
         "data science","cybersecurity","archaeology","nuclear","geology","astrology"],
    12: ["hospital","research","foreign","spirituality","space","alternative medicine","international",
         "psychology","meditation","isolated work","writing","philosophy","prison","reform"],
}

# ── Fix 14: Adhi Yoga & Anapha/Sunapha field keywords ───────────────────────
_ADHI_YOGA_FIELDS = ["law","medicine","management","consulting","independent practice",
                     "entrepreneurship","architecture","design","research","teaching"]
_ANAPHA_YOGA_FIELDS = ["entrepreneurship","self-employed","research","writing","arts",
                       "independent","creative","spiritual","technical specialist"]

# ═══════════════════════════════════════════════════════════════════════════════
# ROUND-3 CONSTANTS — 10/10 Upgrade (Person-archetype, Lagna/Rashi propensity,
#   Mahapurusha mandate, Parivartana, War-winner, Dasha compound, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

# ── R3-1: Person-archetype planet dominance weights ──────────────────────────
# Archetype determined by: which planets are AK/AMK, which are in H1/H5/H9/H10,
# and which yogas are active. Maps archetype → field families that get a boost.
_ARCHETYPE_PLANET_WEIGHTS: Dict[str, List[str]] = {
    "Researcher":   ["Mercury", "Ketu", "Saturn", "Jupiter"],   # deep, specialized
    "Leader":       ["Sun", "Mars", "Jupiter"],                  # authority, direction
    "Artist":       ["Venus", "Moon", "Mercury"],                # aesthetic, creative
    "Entrepreneur": ["Rahu", "Mars", "Mercury", "Sun"],         # risk, innovation
    "Specialist":   ["Saturn", "Mercury", "Ketu", "Mars"],      # technical mastery
    "Scholar":      ["Jupiter", "Mercury", "Moon"],              # teaching, learning
    "Healer":       ["Moon", "Jupiter", "Venus", "Ketu"],       # service, medicine
    "Mystic":       ["Ketu", "Jupiter", "Saturn", "Moon"],      # spiritual, esoteric
}

_ARCHETYPE_FIELD_FAMILIES: Dict[str, List[str]] = {
    "Researcher":   ["research","data","science","analytics","investigation","forensic",
                     "mathematics","statistics","laboratory","computational","bioinformatics"],
    "Leader":       ["management","administration","government","civil services","politics",
                     "military","leadership","entrepreneurship","policy","executive"],
    "Artist":       ["arts","music","film","design","fashion","photography","animation",
                     "performing arts","creative writing","interior","architecture"],
    "Entrepreneur": ["entrepreneurship","business","commerce","startup","fintech",
                     "technology","e-commerce","marketing","trading","investment"],
    "Specialist":   ["engineering","medicine","law","surgery","software","data science",
                     "cybersecurity","quantum","robotics","materials","architecture"],
    "Scholar":      ["education","philosophy","law","theology","international",
                     "humanities","psychology","social science","literature","linguistics"],
    "Healer":       ["medicine","nursing","psychology","counseling","public health",
                     "ayurveda","pharmacy","alternative","veterinary","rehabilitation"],
    "Mystic":       ["spirituality","astrology","philosophy","alternative","research",
                     "meditation","yoga","occult","theology","archaeology"],
}

# ── R3-2: Lagna → classical career propensities ──────────────────────────────
_LAGNA_CAREER_KW: Dict[str, List[str]] = {
    "Aries":       ["surgery","defence","military","engineering","sports","police","civil","pioneer"],
    "Taurus":      ["finance","arts","agriculture","luxury","music","banking","real estate","design"],
    "Gemini":      ["communication","media","commerce","writing","journalism","it","technology","data"],
    "Cancer":      ["medicine","nursing","psychology","hospitality","food","public","education","social"],
    "Leo":         ["government","performing arts","administration","management","politics","civil services"],
    "Virgo":       ["medicine","pharmacy","analytics","law","data","accounting","health","research"],
    "Libra":       ["law","diplomacy","arts","design","hr","international","aesthetics","finance"],
    "Scorpio":     ["research","forensic","mining","investigation","surgery","cybersecurity","psychology"],
    "Sagittarius": ["law","philosophy","international","higher education","theology","sports","research"],
    "Capricorn":   ["engineering","government","construction","agriculture","industrial","infrastructure"],
    "Aquarius":    ["technology","science","innovation","social reform","computer","data","electronics"],
    "Pisces":      ["spirituality","arts","medicine","psychology","alternative","research","international"],
}

# ── R3-3: Moon sign (Rashi) → career propensities ────────────────────────────
_MOON_RASHI_CAREER_KW: Dict[str, List[str]] = {
    "Aries":       ["pioneering","competitive","engineering","sports","defence","surgery","startups"],
    "Taurus":      ["finance","creative","arts","real estate","food","stability","music","luxury"],
    "Gemini":      ["communication","writing","data","technology","media","commerce","intellectual"],
    "Cancer":      ["nurturing","medicine","food","public","social","education","counseling","home"],
    "Leo":         ["leadership","performing","government","arts","management","celebrity","teaching"],
    "Virgo":       ["analytical","health","medicine","statistics","accounting","precision","research"],
    "Libra":       ["harmonizing","law","design","creative","diplomacy","aesthetics","hr","balance"],
    "Scorpio":     ["investigation","research","transformative","psychology","surgery","forensic"],
    "Sagittarius": ["philosophy","international","sports","law","teaching","religion","travel"],
    "Capricorn":   ["systematic","government","construction","engineering","mining","administrative"],
    "Aquarius":    ["innovative","humanitarian","technology","science","reform","groups","electronics"],
    "Pisces":      ["spiritual","artistic","healing","psychology","international","charity","creative"],
}

# ── R3-4: Panchamahapurusha → field mandate keywords ─────────────────────────
# When yoga is present AND strong, these fields get mandate boost;
# completely opposite fields get mild counter-signal.
_MAHAPURUSHA_MANDATE: Dict[str, List[str]] = {
    "Ruchaka":  ["military","surgery","engineering","sports","metallurgy","defence","police",
                 "firefighting","civil engineering","competitive sports","mining"],
    "Bhadra":   ["accounting","communication","mathematics","data","law","business","journalism",
                 "commerce","software","writing","publishing","education","it"],
    "Hamsa":    ["law","teaching","philosophy","medicine","spiritual","judiciary","economics",
                 "consulting","religion","higher education","research","theology"],
    "Malavya":  ["arts","entertainment","luxury","film","design","fashion","tourism",
                 "performing arts","music","aesthetics","hospitality","media"],
    "Shasha":   ["civil services","mining","construction","agriculture","real estate","judiciary",
                 "administration","manual","infrastructure","government","land"],
}

# ── R3-5: Career-house Parivartana pairs and their field associations ─────────
# (house_a, house_b) → [(field_keywords, boost), ...]
_CAREER_PARIVARTANA_PAIRS: Dict[tuple, Dict] = {
    (5, 9):  {"label": "trikona_exchange", "boost": 0.18,
              "fields": ["education","research","law","philosophy","teaching","theology",
                         "creative","intellectual","spiritual","higher education"]},
    (9, 10): {"label": "fortune_karma_exchange", "boost": 0.15,
              "fields": ["law","teaching","government","administration","consulting",
                         "international","academia","philosophy","policy","media"]},
    (5, 10): {"label": "intellect_career_exchange", "boost": 0.14,
              "fields": ["research","data","mathematics","creative","academia","arts",
                         "software","design","intellectual","science","media"]},
    (10, 11): {"label": "career_gains_exchange", "boost": 0.13,
               "fields": ["business","commerce","finance","entrepreneurship","investment",
                          "trading","economics","management","consulting","technology"]},
    (2, 10): {"label": "wealth_career_exchange", "boost": 0.12,
              "fields": ["commerce","banking","finance","accounting","business","economics",
                         "trade","investment","administration","valuations"]},
    (1, 10): {"label": "self_career_exchange", "boost": 0.11,
              "fields": ["entrepreneurship","leadership","independent","pioneer","startups",
                         "self-employed","creative","arts","research"]},
    (9, 5):  {"label": "trikona_exchange", "boost": 0.18,     # mirror
              "fields": ["education","research","law","philosophy","teaching","theology",
                         "creative","intellectual","spiritual","higher education"]},
    (10, 9): {"label": "fortune_karma_exchange", "boost": 0.15,
              "fields": ["law","teaching","government","administration","consulting",
                         "international","academia","philosophy","policy","media"]},
    (10, 5): {"label": "intellect_career_exchange", "boost": 0.14,
              "fields": ["research","data","mathematics","creative","academia","arts",
                         "software","design","intellectual","science","media"]},
    (11, 10): {"label": "career_gains_exchange", "boost": 0.13,
               "fields": ["business","commerce","finance","entrepreneurship","investment",
                          "trading","economics","management","consulting","technology"]},
    (10, 2): {"label": "wealth_career_exchange", "boost": 0.12,
              "fields": ["commerce","banking","finance","accounting","business","economics",
                         "trade","investment","administration","valuations"]},
    (10, 1): {"label": "self_career_exchange", "boost": 0.11,
              "fields": ["entrepreneurship","leadership","independent","pioneer","startups",
                         "self-employed","creative","arts","research"]},
}

# ── R3-7: Graha Yuddha — loser's domain is absorbed by winner ────────────────
# Planet → the domain keywords it brings when it wins a planetary war
_WAR_WINNER_DOMAIN: Dict[str, List[str]] = {
    "Sun":     ["government","administration","authority","civil services","leadership","politics"],
    "Moon":    ["nursing","psychology","public","food","arts","social","counseling"],
    "Mars":    ["engineering","surgery","defence","sports","mechanical","metallurgy","civil"],
    "Mercury": ["communication","data","mathematics","commerce","writing","it","software"],
    "Jupiter": ["law","teaching","philosophy","finance","medicine","consulting","theology"],
    "Venus":   ["arts","design","luxury","entertainment","fashion","hospitality","music"],
    "Saturn":  ["construction","mining","agriculture","civil services","government","systematic"],
    "Rahu":    ["technology","foreign","unconventional","research","innovation","frontier"],
    "Ketu":    ["research","spiritual","technical","investigation","alternative","occult"],
}

# ── R3-9: Compound dasha quality threshold combinations ──────────────────────
# These flag when a compound exceptional quality event is active
_COMPOUND_DASHA_FIELDS: Dict[str, List[str]] = {
    # When Sun is in exceptional compound quality, boost these fields hard
    "Sun":     ["government","administration","civil services","leadership","politics","ias","authority"],
    "Moon":    ["medicine","nursing","public health","food","psychology","counseling","social"],
    "Mars":    ["engineering","defence","surgery","sports","military","mechanical","civil"],
    "Mercury": ["it","data science","mathematics","communication","software","commerce","writing"],
    "Jupiter": ["law","teaching","philosophy","consulting","medicine","economics","theology"],
    "Venus":   ["arts","entertainment","fashion","design","luxury","tourism","performing"],
    "Saturn":  ["engineering","construction","government","civil","mining","agriculture","judiciary"],
    "Rahu":    ["technology","artificial intelligence","data","foreign","unconventional","research"],
    "Ketu":    ["research","spirituality","technical","investigation","forensic","alternative"],
}

# ── R3-11: Trikona unity field mandate keywords ───────────────────────────────
# When H1+H5+H9 lords are all connected (same sign / mutual aspect / parivartana)
# the connected lords' combined domain becomes a dharmic mandate
_TRIKONA_UNITY_BONUS_KW = [
    "law","philosophy","teaching","education","research","theology","medicine","spirituality",
    "psychology","counseling","arts","creative","literature","humanities","social science"
]

# ── R3-14: Yogi Point — Nakshatra lord of the auspicious point ────────────────
# Classical computation: Yogi Point = (Sun long + Moon long + 93°20') mod 360°
# The nakshatra lord of that point i# The nakshatra lord of the Yogi Point is the Yogi Planet (career blessing lord).
_YOGI_POINT_NAKSHATRAS = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
    "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni",
    "Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha",
    "Mula","Purva Ashadha","Uttara Ashadha","Shravana","Dhanishta",
    "Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati",
]
_NAKSHATRA_LORD = {
    "Ashwini":"Ketu","Bharani":"Venus","Krittika":"Sun","Rohini":"Moon",
    "Mrigashira":"Mars","Ardra":"Rahu","Punarvasu":"Jupiter","Pushya":"Saturn",
    "Ashlesha":"Mercury","Magha":"Ketu","Purva Phalguni":"Venus","Uttara Phalguni":"Sun",
    "Hasta":"Moon","Chitra":"Mars","Swati":"Rahu","Vishakha":"Jupiter",
    "Anuradha":"Saturn","Jyeshtha":"Mercury","Mula":"Ketu","Purva Ashadha":"Venus",
    "Uttara Ashadha":"Sun","Shravana":"Moon","Dhanishta":"Mars","Shatabhisha":"Rahu",
    "Purva Bhadrapada":"Jupiter","Uttara Bhadrapada":"Saturn","Revati":"Mercury",
}

# ── R3-15: Confidence convergence labels ─────────────────────────────────────
_CONVERGENCE_LABELS: Dict[int, str] = {
    0: "SPECULATIVE",
    1: "WEAK",
    2: "MODERATE",
    3: "STRONG",
    4: "VERY_STRONG",
    5: "VERY_STRONG",
}

# ═══════════════════════════════════════════════════════════════════════════════
# WORLD-CLASS UPGRADE: Nakshatra Gana / Dosha / Devata tables  (P2-1)
# ═══════════════════════════════════════════════════════════════════════════════

# Gana (temperament): Deva=divine/sattvic, Manushya=human/rajasic, Rakshasa=demonic/tamasic
_NAKSHATRA_GANA: Dict[str, str] = {
    "Ashwini":"Deva","Bharani":"Manushya","Krittika":"Rakshasa","Rohini":"Manushya",
    "Mrigashira":"Deva","Ardra":"Manushya","Punarvasu":"Deva","Pushya":"Deva",
    "Ashlesha":"Rakshasa","Magha":"Rakshasa","Purva Phalguni":"Manushya",
    "Uttara Phalguni":"Manushya","Hasta":"Deva","Chitra":"Rakshasa","Swati":"Deva",
    "Vishakha":"Rakshasa","Anuradha":"Deva","Jyeshtha":"Rakshasa","Mula":"Rakshasa",
    "Purva Ashadha":"Manushya","Uttara Ashadha":"Manushya","Shravana":"Deva",
    "Dhanishta":"Rakshasa","Shatabhisha":"Rakshasa","Purva Bhadrapada":"Manushya",
    "Uttara Bhadrapada":"Deva","Revati":"Deva",
}

# Gana → career field fit keywords
_GANA_FIELD_FIT: Dict[str, List[str]] = {
    "Deva":      ["education","research","medicine","philosophy","spirituality","law",
                  "counselling","social work","non-profit","teaching","healing"],
    "Manushya":  ["business","management","commerce","engineering","technology",
                  "finance","marketing","entrepreneurship","consulting","architecture"],
    "Rakshasa":  ["defence","surgery","investigation","forensic","competitive law",
                  "politics","criminal justice","sports","military","security"],
}

# Nakshatra Dosha (burnout/imbalance tendency in certain fields)
_NAKSHATRA_DOSHA: Dict[str, str] = {
    "Ashwini":"Vata","Bharani":"Pitta","Krittika":"Pitta","Rohini":"Kapha",
    "Mrigashira":"Vata","Ardra":"Vata","Punarvasu":"Vata","Pushya":"Kapha",
    "Ashlesha":"Kapha","Magha":"Kapha","Purva Phalguni":"Pitta",
    "Uttara Phalguni":"Pitta","Hasta":"Vata","Chitra":"Pitta","Swati":"Vata",
    "Vishakha":"Pitta","Anuradha":"Kapha","Jyeshtha":"Pitta","Mula":"Vata",
    "Purva Ashadha":"Pitta","Uttara Ashadha":"Pitta","Shravana":"Kapha",
    "Dhanishta":"Pitta","Shatabhisha":"Vata","Purva Bhadrapada":"Vata",
    "Uttara Bhadrapada":"Kapha","Revati":"Kapha",
}

# Dosha → fields with burnout risk (avoid overexposure)
_DOSHA_BURNOUT_FIELDS: Dict[str, List[str]] = {
    "Vata":  ["surgery","intensive care","emergency medicine","military combat",
              "high-frequency trading","data center ops","air traffic control"],
    "Pitta": ["corporate law","investment banking","competitive sports","political campaigns",
              "criminal prosecution","high-stakes consulting","media broadcasting"],
    "Kapha": ["entrepreneurship","start-up","innovation","creative arts","freelance",
              "agile technology","performing arts","film"],
}

# Nakshatra Devata (ruling deity)
_NAKSHATRA_DEVATA: Dict[str, str] = {
    "Ashwini":"Ashwini Kumaras","Bharani":"Yama","Krittika":"Agni","Rohini":"Brahma",
    "Mrigashira":"Soma","Ardra":"Rudra","Punarvasu":"Aditi","Pushya":"Brihaspati",
    "Ashlesha":"Nagas","Magha":"Pitrs","Purva Phalguni":"Bhaga","Uttara Phalguni":"Aryaman",
    "Hasta":"Savitar","Chitra":"Vishvakarma","Swati":"Vayu","Vishakha":"Indra-Agni",
    "Anuradha":"Mitra","Jyeshtha":"Indra","Mula":"Nirriti","Purva Ashadha":"Apas",
    "Uttara Ashadha":"Vishvedevas","Shravana":"Vishnu","Dhanishta":"Vasus",
    "Shatabhisha":"Varuna","Purva Bhadrapada":"Aja Ekapad","Uttara Bhadrapada":"Ahir Budhnya",
    "Revati":"Pushan",
}

# Devata → career domain alignment (primary career domains the deity blesses)
_DEVATA_CAREER_DOMAIN: Dict[str, List[str]] = {
    "Ashwini Kumaras": ["medicine","healing","alternative medicine","ayurveda","therapy"],
    "Yama":            ["law","judiciary","taxation","administration","civil services"],
    "Agni":            ["chemistry","metallurgy","energy","fire safety","cooking","refinery"],
    "Brahma":          ["education","research","writing","publishing","creation","design"],
    "Soma":            ["medicine","pharmacy","food science","agriculture","botany"],
    "Rudra":           ["surgery","emergency","defence","destruction","transformation"],
    "Aditi":           ["international relations","diplomacy","social work","motherhood"],
    "Brihaspati":      ["education","law","religion","philosophy","banking","finance"],
    "Nagas":           ["investigation","forensics","occult","alternative","hidden"],
    "Pitrs":           ["history","heritage","administration","government","ancestors"],
    "Bhaga":           ["commerce","luxury","entertainment","arts","wealth management"],
    "Aryaman":         ["nobility","hospitality","tourism","hotel management","social"],
    "Savitar":         ["technology","engineering","precision","craftsmanship","solar energy"],
    "Vishvakarma":     ["architecture","design","engineering","manufacturing","art"],
    "Vayu":            ["aviation","environment","logistics","transport","communication"],
    "Indra-Agni":      ["leadership","politics","military strategy","energy","fire"],
    "Mitra":           ["diplomacy","international","cooperation","social","public"],
    "Indra":           ["politics","administration","leadership","authority","rain/water"],
    "Nirriti":         ["research","depth psychology","forensics","hidden","occult"],
    "Apas":            ["water resources","shipping","navy","aquaculture","fisheries"],
    "Vishvedevas":     ["multi-disciplinary","public administration","universal fields"],
    "Vishnu":          ["preservation","management","law","governance","stability"],
    "Vasus":           ["material wealth","finance","real estate","construction","mining"],
    "Varuna":          ["law","ethics","ocean","diplomacy","international law","navy"],
    "Aja Ekapad":      ["mysticism","research","higher knowledge","unconventional"],
    "Ahir Budhnya":    ["deep research","occult","spirituality","marine","submarine"],
    "Pushan":          ["travel","logistics","agriculture","trade routes","food"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# WORLD-CLASS UPGRADE: Geographic / Foreign career tables  (P2-4)
# ═══════════════════════════════════════════════════════════════════════════════

# Sign → geographic region cluster (for H9/H12 lord sign → country affinity)
_SIGN_GEOGRAPHY: Dict[str, List[str]] = {
    "Aries":       ["UK","Germany","Denmark","Israel","Poland"],
    "Taurus":      ["Ireland","Switzerland","Iran","Cyprus"],
    "Gemini":      ["USA","Belgium","Wales","Sardinia","Armenia"],
    "Cancer":      ["Scotland","Netherlands","New Zealand","Paraguay","Africa-West"],
    "Leo":         ["France","Italy","Romania","Bohemia","Sicily"],
    "Virgo":       ["Greece","Turkey","Mesopotamia","Brazil","Malaysia"],
    "Libra":       ["Austria","Japan","Argentina","China","Burma"],
    "Scorpio":     ["Algeria","Morocco","Norway","Bavaria","Syria"],
    "Sagittarius": ["Australia","Spain","Hungary","Arabia","South Africa"],
    "Capricorn":   ["India","Afghanistan","Bulgaria","Lithuania","Mexico"],
    "Aquarius":    ["Russia","Sweden","Ethiopia","Iran","Poland"],
    "Pisces":      ["Portugal","Egypt","Scandinavia","Sahara","Sri Lanka"],
}

# International field keywords (fields indicating foreign career track)
_INTERNATIONAL_FIELD_KW: List[str] = [
    "international","foreign","global","multinational","export","import","diplomatic",
    "overseas","immigration","transnational","cross-border","offshore","expat",
    "international law","international business","international relations","mbbs abroad",
    "foreign language","trade","shipping","aviation","tourism","hospitality international",
    "united nations","who","imf","world bank","ngo international",
]

# ═══════════════════════════════════════════════════════════════════════════════
# WORLD-CLASS UPGRADE: Special Lagna → domain tables  (P1-3)
# ═══════════════════════════════════════════════════════════════════════════════

# Ghati Lagna sign → domains it empowers (authority/power domains)
_GHATI_LAGNA_DOMAIN: Dict[str, List[str]] = {
    "Aries":       ["defence","military","surgery","sports","engineering","police"],
    "Taurus":      ["finance","banking","luxury","art","real estate","agriculture"],
    "Gemini":      ["media","communication","technology","writing","commerce","data"],
    "Cancer":      ["medicine","nursing","food","social work","psychology","real estate"],
    "Leo":         ["government","administration","politics","leadership","management"],
    "Virgo":       ["medicine","accounting","data analytics","research","editing"],
    "Libra":       ["law","diplomacy","art","fashion","design","counselling"],
    "Scorpio":     ["research","investigation","surgery","forensics","occult","finance"],
    "Sagittarius": ["law","philosophy","education","international","religion","travel"],
    "Capricorn":   ["engineering","administration","mining","construction","judiciary"],
    "Aquarius":    ["technology","social reform","aviation","research","innovation"],
    "Pisces":      ["medicine","spirituality","art","film","marine","research"],
}

# Sree Lagna sign → domains it blesses (prosperity/Lakshmi domains)
_SREE_LAGNA_DOMAIN: Dict[str, List[str]] = {
    "Aries":       ["entrepreneurship","business","sports commerce","real estate"],
    "Taurus":      ["luxury","beauty","fashion","food","finance","agriculture"],
    "Gemini":      ["media","communication","writing","commerce","technology"],
    "Cancer":      ["real estate","food","hospitality","social","medicine"],
    "Leo":         ["entertainment","arts","management","government","jewellery"],
    "Virgo":       ["healthcare","accounting","pharma","data","editing"],
    "Libra":       ["fashion","luxury","law","art","diplomacy","beauty"],
    "Scorpio":     ["insurance","finance","mining","investigation","research"],
    "Sagittarius": ["education","publishing","international trade","law","philosophy"],
    "Capricorn":   ["real estate","construction","government","administration"],
    "Aquarius":    ["technology","social enterprise","innovation","research"],
    "Pisces":      ["film","music","spirituality","medicine","marine","tourism"],
}

# GAP-FIX (2026-07): Hora Lagna (wealth/income-timing lagna) and Bhava Lagna
# (general vocational/status lagna) domain tables, mirroring the existing
# Ghati/Sree Lagna tables above. These two payload fields (hora_lagna_sign /
# bhava_lagna_sign) previously existed on NatalPayloadV2 but were never
# actually computed anywhere in the pipeline (see jyotish/ephemeris.py's
# get_hora_lagna/get_bhava_lagna and engine_io.py's wiring for the fix).

# Hora Lagna sign -> domains it empowers (wealth/income-generation domains --
# classical significance of Hora Lagna per BPHS/Phaladeepika).
_HORA_LAGNA_DOMAIN: Dict[str, List[str]] = {
    "Aries":       ["entrepreneurship","sales","commodities trading","sports commerce"],
    "Taurus":      ["banking","finance","luxury goods","agriculture","real estate"],
    "Gemini":      ["commerce","trading","media sales","commission-based","brokerage"],
    "Cancer":      ["hospitality","food business","real estate","import export"],
    "Leo":         ["management","government contracts","luxury","entertainment business"],
    "Virgo":       ["accounting","auditing","data services","consulting","pharma trade"],
    "Libra":       ["fashion retail","luxury trade","legal practice","design business"],
    "Scorpio":     ["insurance","mining","finance","forensic consulting"],
    "Sagittarius": ["international trade","publishing","education business","law practice"],
    "Capricorn":   ["real estate","construction business","mining","government finance"],
    "Aquarius":    ["technology startups","social enterprise","innovation consulting"],
    "Pisces":      ["film production","marine trade","spiritual services","import export"],
}

# Bhava Lagna sign -> domains it empowers (general vocational/life-status
# significance -- classical significance of Bhava Lagna per BPHS/Phaladeepika).
_BHAVA_LAGNA_DOMAIN: Dict[str, List[str]] = {
    "Aries":       ["defence","military","engineering","sports","surgery"],
    "Taurus":      ["finance","banking","agriculture","luxury","real estate"],
    "Gemini":      ["communication","media","technology","commerce","writing"],
    "Cancer":      ["medicine","hospitality","social work","real estate","psychology"],
    "Leo":         ["government","administration","politics","leadership","entertainment"],
    "Virgo":       ["medicine","accounting","research","data analytics","editing"],
    "Libra":       ["law","diplomacy","design","fashion","counselling"],
    "Scorpio":     ["research","investigation","surgery","finance","forensics"],
    "Sagittarius": ["law","education","philosophy","international","religion"],
    "Capricorn":   ["engineering","administration","mining","construction","judiciary"],
    "Aquarius":    ["technology","social reform","aviation","research","innovation"],
    "Pisces":      ["medicine","spirituality","art","film","marine biology"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# WORLD-CLASS UPGRADE: Exam Timing tables  (P2-5)
# ═══════════════════════════════════════════════════════════════════════════════

_EXAM_FIELD_MAP: Dict[str, List[str]] = {
    "Medicine":                    ["NEET-UG","NEET-PG","AIIMS"],
    "Engineering":                 ["JEE-Main","JEE-Advanced","GATE"],
    "Civil Services":              ["UPSC-CSE","UPSC-IFS","State-PSC"],
    "Law":                         ["CLAT","AILET","LSAT-India"],
    "Management":                  ["CAT","XAT","GMAT"],
    "Defence":                     ["NDA","CDS","AFCAT"],
    "Architecture":                ["NATA","JEE-Paper2"],
    "Finance / Banking":           ["CA-Foundation","IBPS","RBI-Grade-B"],
    "Education / Teaching":        ["CTET","UGC-NET","State-TET"],
    "Research / Academia":         ["UGC-NET","CSIR-NET","JEST"],
    "Software Engineering":        ["GATE","Campus-Placement"],
    "Data Science":                ["GATE","Campus-Placement"],
    "Biotechnology":               ["GATE-BT","CSIR-NET"],
    "Pharmacy":                    ["GPAT","NIPER"],
    "Nursing":                     ["AIIMS-BSc-Nursing","State-CET"],
    "Journalism / Media":          ["IIMC","XIC","ACJ"],
    "Social Work":                 ["TISS-NET","State-MSW-CET"],
    "Design":                      ["NID","NIFT","CEED"],
    "Agriculture":                 ["ICAR-AIEEA","State-Agri-CET"],
    "Psychology":                  ["NIMHANS","DU-MSc-Psych"],
}

_EXAM_PLANET_ACTIVATORS: Dict[str, List[str]] = {
    "NEET-UG":          ["Moon","Mars","Sun","Jupiter"],
    "NEET-PG":          ["Mercury","Saturn","Mars","Moon"],
    "JEE-Main":         ["Mercury","Saturn","Mars","Sun"],
    "JEE-Advanced":     ["Mercury","Saturn","Jupiter"],
    "GATE":             ["Mercury","Saturn","Jupiter","Rahu"],
    "UPSC-CSE":         ["Saturn","Jupiter","Sun","Moon"],
    "CLAT":             ["Mercury","Jupiter","Saturn"],
    "CAT":              ["Mercury","Jupiter","Rahu","Venus"],
    "NDA":              ["Mars","Sun","Saturn","Jupiter"],
    "CDS":              ["Mars","Sun","Saturn"],
    "NATA":             ["Venus","Mercury","Moon"],
    "CA-Foundation":    ["Mercury","Saturn","Venus","Jupiter"],
    "UGC-NET":          ["Jupiter","Mercury","Saturn"],
    "CSIR-NET":         ["Saturn","Mercury","Jupiter"],
    "CTET":             ["Jupiter","Moon","Mercury"],
    "Campus-Placement": ["Mercury","Jupiter","Rahu","Venus"],
    "NID":              ["Venus","Mercury","Moon","Rahu"],
    "NIFT":             ["Venus","Mercury","Moon"],
    "ICAR-AIEEA":       ["Moon","Mars","Saturn","Mercury"],
    "IBPS":             ["Mercury","Jupiter","Saturn"],
    # RECONSTRUCTION NOTE (2026-07-07): this dict literal was found truncated
    # at the source-file level, cut off mid-entry right after the
    # "RBI-Grade-B" key with no value and no closing brace (same corruption
    # pattern documented in several other modules this session — see
    # jyotish/web_report.py's generate_career_timeline_report() reconstruction
    # note for the fuller account). Closing the entry with a planet set
    # consistent with this exam's own domain (RBI Grade B is a
    # finance/economics/regulatory civil-services-style exam) and closing the
    # dict literal here restores valid Python; no other exam entries were
    # altered.
    "RBI-Grade-B":      ["Mercury","Jupiter","Saturn","Sun"],
}
