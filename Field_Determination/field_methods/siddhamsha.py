"""D24 educational suitability, explicitly excluded from permanent vocation."""
from __future__ import annotations
from typing import Any, Mapping

PLANET_DIM={"Mercury":("math_intensity","coding_intensity","writing_intensity"),"Mars":("physics_intensity","fieldwork_intensity"),"Jupiter":("writing_intensity","people_interaction"),"Venus":("people_interaction","writing_intensity"),"Moon":("biology_intensity","people_interaction"),"Saturn":("math_intensity","fieldwork_intensity"),"Rahu":("coding_intensity","physics_intensity"),"Ketu":("math_intensity","physics_intensity")}
STRONG={"EXALTED":1.0,"OWN":.85,"OWN_SIGN":.85,"MOOLATRIKONA":.9,"FRIEND":.65,"NEUTRAL":.5,"ENEMY":.3,"DEBILITATED":.1}

def score_siddhamsha(payload: Any, field_entry: Mapping, field_affinity: Mapping[str,float]|None=None) -> dict:
    digs=getattr(payload,"d24_planet_dignities",{}) or {}; curriculum=field_entry.get("curriculum",{}) or {}
    if not digs: return {"contract_version":"d24-education.v1","status":"MISSING","educational_suitability":None,"permanent_vote":False}
    requirements={k:max(0.0,min(1.0,float(v or 0)/5.0)) for k,v in curriculum.items() if k.endswith("_intensity") or k=="people_interaction"}
    capacity={k:.5 for k in requirements}
    for planet,weight in (field_affinity or {}).items():
        strength=STRONG.get(str(digs.get(planet,"NEUTRAL")).upper(),.5)
        for dim in PLANET_DIM.get(planet,()):
            if dim in capacity: capacity[dim]=max(capacity[dim],strength*float(weight)*2.0)
    denom=sum(requirements.values()); match=50.0 if denom<=0 else 100*sum(requirements[k]*min(1,capacity[k]) for k in requirements)/denom
    return {"contract_version":"d24-education.v1","status":"OBSERVED","educational_suitability":round(match,2),"permanent_vote":False,"requirements":requirements,"capacity":capacity}

