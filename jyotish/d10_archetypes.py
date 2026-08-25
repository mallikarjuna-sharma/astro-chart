"""Auditable chart-native D10 vocational archetypes, independent of registry leaves.

V1.3 merge plan item 4: PLANET_ARCHETYPES below is now V1.3's richer
vocational_archetypes.py table (jyotish/vocational_archetypes.py in
Jyotish_Field_EngineV1.3), with this engine's pre-existing vocabulary
reconciled into it per the 2026-07 merge decisions:
  - "public_service" (was only on Moon, weight .5) -> folded into
    "public_authority" (Moon's public_authority raised from V1.3's 0.25 to
    max(0.25, 0.5) = 0.50).
  - "analysis" and "technology" (were on Mercury/Rahu/Ketu) -> folded into
    "research" (each planet's research weight raised to the max of V1.3's
    original value and whatever analysis/technology weight this engine had
    for that planet). No new archetype tags were introduced; the vocabulary
    is now V1.3's closed ten-mode set plus nothing.
DOMAIN_ARCHETYPES/DOMAIN_ALIASES/ARCHETYPE_NAMES/canonical_domain/
scale_raw_support/archetype_vector/domain_score/validate_rule_pack are
ported from V1.3 as-is (this engine previously had no domain-level mapping
co-located with the planet archetypes at all).
"""
from __future__ import annotations
import math
from typing import Any, Dict, Mapping

RULE_PACK_VERSION = "chart-native-vocational-archetypes.v2"

SIGNS=("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces")
LORD={"Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon","Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars","Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter"}

PLANET_ARCHETYPES: Dict[str, Dict[str, float]] = {
    "Sun": {"public_authority": 1.00, "administration": 0.80, "scholarship_policy": 0.25},
    "Moon": {"care": 0.90, "communication": 0.45, "public_authority": 0.50},  # public_authority raised: public_service fold
    "Mars": {"engineering_systems": 1.00, "field_operations": 0.90, "research": 0.20},
    "Mercury": {"communication": 1.00, "commerce": 0.85, "research": 0.80, "administration": 0.35},  # research raised: analysis/technology fold
    "Jupiter": {"scholarship_policy": 1.00, "public_authority": 0.55, "research": 0.70, "care": 0.35},
    "Venus": {"design": 1.00, "communication": 0.60, "commerce": 0.50, "care": 0.25},
    "Saturn": {"administration": 0.85, "engineering_systems": 0.80, "field_operations": 0.70, "research": 0.35},
    "Rahu": {"research": 1.00, "engineering_systems": 0.75, "communication": 0.35},  # research raised: technology fold
    "Ketu": {"research": 1.00, "scholarship_policy": 0.45, "care": 0.20},  # research raised: analysis fold
}

DOMAIN_ARCHETYPES: Dict[str, Dict[str, float]] = {
    "engineering": {"engineering_systems": .55, "field_operations": .20, "research": .20, "communication": .05},
    "technology": {"engineering_systems": .50, "research": .30, "communication": .20},
    "science": {"research": .65, "scholarship_policy": .35},
    "law": {"scholarship_policy": .45, "public_authority": .30, "communication": .25},
    "humanities": {"scholarship_policy": .50, "communication": .35, "design": .15},
    "education": {"scholarship_policy": .60, "communication": .30, "administration": .10},
    "public": {"public_authority": .45, "administration": .30, "scholarship_policy": .25},
    "commerce": {"commerce": .60, "communication": .25, "administration": .15},
    "medicine": {"care": .60, "field_operations": .25, "research": .15},
    "arts": {"design": .65, "communication": .35},
    "media": {"communication": .60, "design": .30, "public_authority": .10},
    "agriculture": {"field_operations": .45, "care": .30, "research": .25},
    "sports": {"field_operations": .65, "care": .25, "public_authority": .10},
    "interdisciplinary": {"research": .40, "communication": .25, "scholarship_policy": .20, "design": .15},
}

DOMAIN_ALIASES = {"defence": "public", "defense": "public", "government": "public", "healthcare": "medicine", "research": "science", "management": "commerce"}
ARCHETYPE_NAMES = tuple(sorted({name for row in PLANET_ARCHETYPES.values() for name in row}))


def canonical_domain(domain: str) -> str:
    value = str(domain or "").strip().lower()
    value = DOMAIN_ALIASES.get(value, value)
    if value not in DOMAIN_ARCHETYPES:
        raise ValueError(f"unsupported vocational domain: {domain!r}")
    return value


def scale_raw_support(raw: float) -> float:
    """Stable absolute 0..100 scale without information-destroying clipping.

    One support unit remains approximately 50.  Additional corroboration has
    diminishing returns but never collapses distinct raw values to the same
    hard-ceiling score.
    """
    return round(100.0 * (1.0 - math.exp(-math.log(2.0) * max(0.0, float(raw)))), 4)


def archetype_vector(raw_totals: Mapping[str, float]) -> Dict[str, float]:
    return {name: scale_raw_support(raw_totals.get(name, 0.0)) for name in ARCHETYPE_NAMES}


def domain_score(vector: Mapping[str, float], domain: str) -> Dict[str, Any]:
    normalized = canonical_domain(domain)
    mapping = DOMAIN_ARCHETYPES[normalized]
    weight_sum = sum(mapping.values())
    if abs(weight_sum - 1.0) > 1e-9:
        raise ValueError(f"domain mapping weights do not sum to 1: {normalized}={weight_sum}")
    score = sum(float(vector.get(name, 0.0)) * weight for name, weight in mapping.items())
    return {"domain": normalized, "score": round(max(0.0, min(100.0, score)), 2), "mapping_weights": dict(mapping)}


def validate_rule_pack() -> Dict[str, Any]:
    errors = []
    for domain, mapping in DOMAIN_ARCHETYPES.items():
        if abs(sum(mapping.values()) - 1.0) > 1e-9: errors.append(f"{domain}: weights do not sum to 1")
        unknown = sorted(set(mapping) - set(ARCHETYPE_NAMES))
        if unknown: errors.append(f"{domain}: unknown archetypes {unknown}")
    missing_planets = sorted({"Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"} - set(PLANET_ARCHETYPES))
    if missing_planets: errors.append(f"missing planets: {missing_planets}")
    return {"ok": not errors, "errors": errors, "rule_pack": RULE_PACK_VERSION,
            "domain_count": len(DOMAIN_ARCHETYPES), "archetype_count": len(ARCHETYPE_NAMES)}


DIGNITY={"EXALTED":1.20,"OWN":1.12,"MOOLATRIKONA":1.10,"NEECHA_BHANGA":1.0,"NEUTRAL":.90,"DEBILITATED":.50}
HOUSE_CONTEXT={
    1:{"public_authority":.45,"administration":.35},2:{"communication":.35,"commerce":.35},
    3:{"communication":.45,"field_operations":.35},5:{"scholarship_policy":.55,"research":.30,"design":.25},
    6:{"field_operations":.40,"care":.30,"administration":.25},8:{"research":.65,"care":.20},
    9:{"scholarship_policy":.75,"communication":.25,"public_authority":.20},
    10:{"public_authority":.35,"administration":.35},11:{"commerce":.35,"administration":.25,"communication":.20},
    12:{"research":.40,"care":.30,"administration":.20},
}

def _get(obj:Any,key:str,default=None): return obj.get(key,default) if isinstance(obj,Mapping) else getattr(obj,key,default)

def _house_lord(lagna:str,house:int)->str:
    if lagna not in SIGNS:return ""
    return LORD[SIGNS[(SIGNS.index(lagna)+house-1)%12]]

def _planet_house(planet:str,signs:Mapping[str,str],lagna:str)->int:
    sign=signs.get(planet,"")
    return ((SIGNS.index(sign)-SIGNS.index(lagna))%12)+1 if sign in SIGNS and lagna in SIGNS else 0

def d10_chart_native_archetype_profile(payload:Any)->dict:
    divisions=_get(payload,"divisional_charts",{}) or {}
    chart=divisions.get("D10_dashamsha",{}) or {}
    signs={p:(v.get("sign","") if isinstance(v,Mapping) else v) for p,v in chart.items()}
    lagna=str(_get(payload,"d10_lagna_sign","") or signs.get("Lagna","") or "")
    occupancy=_get(payload,"d10_house_occupancy",{}) or {}
    dignities=_get(payload,"d10_planet_dignities",{}) or {}
    if not lagna and not occupancy:
        return {"contract_version":"d10-archetypes.v2","scores":{},"raw_support":{},"support_ledger":[],
                "status":"MISSING_D10_LAGNA","source":"D10_CHART_ONLY","registry_inputs_used":False}
    roles={}
    def add(planet:str,value:float,source:str):
        if not planet:return
        old=roles.get(planet,{"weight":0.0,"sources":[]})
        old["weight"]=min(1.5,old["weight"]+value);old["sources"].append(source);roles[planet]=old
    h10l=_house_lord(lagna,10);h10l_house=_planet_house(h10l,signs,lagna)
    add(h10l,1.0 if h10l_house in {1,4,5,7,9,10} else .70 if h10l_house in {2,3,11} else .45,"D10_H10_LORD")
    add(_house_lord(lagna,1),.45,"D10_LAGNA_LORD")
    add(_house_lord(lagna,9),.25,"D10_H9_LORD")
    add(_house_lord(lagna,5),.20,"D10_H5_LORD")
    for p in occupancy.get("10",occupancy.get(10,[])) or []:add(p,.90,"D10_H10_OCCUPANT")
    for p in occupancy.get("9",occupancy.get(9,[])) or []:add(p,.15,"D10_H9_OCCUPANT")
    for p in occupancy.get("5",occupancy.get(5,[])) or []:add(p,.10,"D10_H5_OCCUPANT")
    totals={};ledger=[]
    for planet,role in roles.items():
        mult=DIGNITY.get(str(dignities.get(planet,"NEUTRAL")).upper(),.90)
        for archetype,affinity in PLANET_ARCHETYPES.get(planet,{}).items():
            contribution=role["weight"]*mult*affinity
            totals[archetype]=totals.get(archetype,0.0)+contribution
            ledger.append({"evidence_id":f"d10:{planet}:{archetype}","planet":planet,"archetype":archetype,
                           "role_weight":round(role["weight"],4),"role_sources":role["sources"],
                           "dignity_multiplier":mult,"contribution":round(contribution,6),"polarity":"POSITIVE"})
    for archetype,value in HOUSE_CONTEXT.get(h10l_house,{}).items():
        totals[archetype]=totals.get(archetype,0.0)+value
        ledger.append({"evidence_id":f"d10:h10lord_house:{h10l_house}:{archetype}","archetype":archetype,
                       "contribution":value,"polarity":"POSITIVE","source":"D10_H10_LORD_HOUSE_CONTEXT"})
    h10=set(occupancy.get("10",occupancy.get(10,[])) or []);support=set()
    for h in (3,10,11):support.update(occupancy.get(str(h),occupancy.get(h,[])) or [])
    if "Rahu" in h10 and {"Mars","Saturn"}&support:
        # Fix (2026-08-19): "technology" is a DOMAIN name (see DOMAIN_ARCHETYPES),
        # not one of the ten planet-level archetypes in ARCHETYPE_NAMES/
        # PLANET_ARCHETYPES -- this module's own docstring says "technology"
        # was folded into "research" during the V1.3 merge, closing the
        # vocabulary to ten modes. Writing into totals["technology"] here
        # therefore added a key that scale_raw_support()/archetype_vector()
        # never read (ARCHETYPE_NAMES is derived only from PLANET_ARCHETYPES),
        # so this Rahu-in-D10-H10-with-Mars/Saturn signal was silently
        # discarded before it could reach `scores` or any domain_score() call
        # -- it only ever showed up, inertly, in raw_support. Redirected to
        # "research" (the archetype this contribution was actually folded
        # into) and the ledger now records both contributions so the evidence
        # trail matches what's actually scored.
        totals["engineering_systems"]=totals.get("engineering_systems",0)+.45
        totals["research"]=totals.get("research",0)+.35
        ledger.append({"evidence_id":"d10:technical_signature:engineering_systems","archetype":"engineering_systems",
                       "contribution":.45,"polarity":"POSITIVE","source":"RAHU_H10_WITH_MARS_OR_SATURN"})
        ledger.append({"evidence_id":"d10:technical_signature:research","archetype":"research",
                       "contribution":.35,"polarity":"POSITIVE","source":"RAHU_H10_WITH_MARS_OR_SATURN"})
    scores={k:round(min(100.0,v/2.0*100.0),2) for k,v in totals.items()}
    return {"contract_version":"d10-archetypes.v2","scores":scores,"raw_support":{k:round(v,6) for k,v in totals.items()},
            "support_ledger":ledger,"planet_roles":roles,"status":"CALCULATED" if lagna else "DEGRADED_OCCUPANCY_ONLY","source":"D10_CHART_ONLY",
            "registry_inputs_used":False,"d10_lagna":lagna,"d10_h10_lord":h10l,"d10_h10_lord_house":h10l_house}

def d10_chart_native_archetype_scores(payload:Any)->dict:
    return d10_chart_native_archetype_profile(payload)
