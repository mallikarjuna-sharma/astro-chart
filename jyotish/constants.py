"""JyotishAI — Shared astrological constants and lookup tables."""
from typing import Dict, List, Tuple, Set, Any, Optional

_EXALT_SIGN = {"Sun":"Aries","Moon":"Taurus","Mars":"Capricorn","Mercury":"Virgo",
               "Jupiter":"Cancer","Venus":"Pisces","Saturn":"Libra"}
_DEBIL_SIGN  = {"Sun":"Libra","Moon":"Scorpio","Mars":"Cancer","Mercury":"Pisces",
               "Jupiter":"Capricorn","Venus":"Virgo","Saturn":"Aries"}
_OWN_SIGN    = {"Sun":["Leo"],"Moon":["Cancer"],"Mars":["Aries","Scorpio"],
               "Mercury":["Gemini","Virgo"],"Jupiter":["Sagittarius","Pisces"],
               "Venus":["Taurus","Libra"],"Saturn":["Capricorn","Aquarius"]}
_DIGNITY_MOD = {"EXALTED":1.40,"OWN":1.15,"DEBILITATED":0.60,"NEECHA_BHANGA":1.05,"":1.0}

_KENDRA_HOUSES  = frozenset({1, 4, 7, 10})
_TRIKONA_HOUSES = frozenset({1, 5, 9})
_KT_HOUSES      = _KENDRA_HOUSES | _TRIKONA_HOUSES
_DUSTHANA_HOUSES= frozenset({6, 8, 12})

_SIGN_NUM = {"Aries":1,"Taurus":2,"Gemini":3,"Cancer":4,"Leo":5,"Virgo":6,
             "Libra":7,"Scorpio":8,"Sagittarius":9,"Capricorn":10,"Aquarius":11,"Pisces":12}
_SIGN_LORD = {"Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
              "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
              "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter"}
_COMBUST_ORB = {"Moon":12,"Mars":17,"Mercury":14,"Jupiter":11,"Venus":10,"Saturn":15}
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
    # Uniform w1/w2 = 0.40 levels the math ceiling across all domains.
    # min_score retained per domain — engineering/medicine still require higher base.
    "engineering":       {"w1":0.40,"w2":0.40,"min_score":55},
    "science":           {"w1":0.40,"w2":0.40,"min_score":55},
    "technology":        {"w1":0.40,"w2":0.40,"min_score":45},
    "medicine":          {"w1":0.40,"w2":0.40,"min_score":55},
    "law":               {"w1":0.40,"w2":0.40,"min_score":40},
    "humanities":        {"w1":0.40,"w2":0.40,"min_score":35},
    "arts":              {"w1":0.40,"w2":0.40,"min_score":30},
    "commerce":          {"w1":0.40,"w2":0.40,"min_score":50},
    "education":         {"w1":0.40,"w2":0.40,"min_score":40},
    "public":            {"w1":0.40,"w2":0.40,"min_score":40},
    "media":             {"w1":0.40,"w2":0.40,"min_score":35},
    "agriculture":       {"w1":0.40,"w2":0.40,"min_score":40},
    "interdisciplinary": {"w1":0.40,"w2":0.40,"min_score":38},
    "research":          {"w1":0.40,"w2":0.40,"min_score":45},
    "design":            {"w1":0.40,"w2":0.40,"min_score":35},
}

_VALID_PLANETS = frozenset(("Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"))
_VALID_DOMAINS = frozenset((
    "engineering","science","technology","medicine","law","humanities","arts",
    "commerce","education","public","media","agriculture","research","design","interdisciplinary",
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
    "Moon":    ["nursing","psychology","social work","public health","ecology","hospitality","counseling"],
    "Rahu":    ["artificial intelligence","cybersecurity","biotechnology","space","robotics","forensic"],
    "Ketu":    ["research","ayurveda","spiritual","philosophy","archaeology","investigation"],
}

def _maheshwara_lord_bonus(label: str, maheshwara_lord: str, affinity: Dict[str, float]) -> float:
    """FIX-6: Maheshwara lord (Jaimini special lord) now contributes to branch scoring.
    Maheshwara represents the peak institutional authority phase of the native's career.
    When a branch aligns with the Maheshwara lord's domain keywords, it receives a bonus."""
    if not maheshwara_lord:
        return 0.0
    kws = _MAHESHWARA_DOMAIN_KW.get(maheshwara_lord, [])
    if not any(kw in label.lower() for kw in kws):
        return 0.0
    w = affinity.get(maheshwara_lord, 0.0)
    if   w >= 0.25: return 0.07
    if   w >= 0.15: return 0.04
    if   w >= 0.08: return 0.02
    return 0.0

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
    "Cancer":      {"Sun":0,  "Moon":1,  "Mars":2,  "Mercury":-1, "Jupiter":1,  "Venus":0,  "Saturn":-1, "Rahu":-1, "Ketu":2},
    "Leo":         {"Sun":1,  "Moon":-1, "Mars":2,  "Mercury":0,  "Jupiter":1,  "Venus":0,  "Saturn":-1, "Rahu":-1, "Ketu":2},
    "Virgo":       {"Sun":-1, "Moon":0,  "Mars":-1, "Mercury":1,  "Jupiter":0,  "Venus":1,  "Saturn":1,  "Rahu":1,  "Ketu":-1},
    "Libra":       {"Sun":0,  "Moon":0,  "Mars":-1, "Mercury":1,  "Jupiter":-1, "Venus":1,  "Saturn":2,  "Rahu":2,  "Ketu":-1},
    "Scorpio":     {"Sun":0,  "Moon":1,  "Mars":1,  "Mercury":-1, "Jupiter":1,  "Venus":-1, "Saturn":0,  "Rahu":0,  "Ketu":1},
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

# Designation levels in seniority order (for gate checks)
_DESIGNATION_LEVELS = ["junior","mid","senior","lead","manager","director","csuite"]

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
