"""D9 proposition confirmation; never an independent vocational vote."""
from __future__ import annotations
from typing import Any, Iterable, Mapping

def score_navamsha_confirmation(payload: Any, propositions: Iterable[Mapping]) -> dict:
    digs=getattr(payload,"d9_planet_dignities",{}) or {}; rows=[]; total=weighted=0.0
    if not digs: return {"contract_version":"d9-confirmation.v1","status":"MISSING","score":None,"independent_vote":False,"confirmations":[]}
    for item in propositions or []:
        planets=list(item.get("supporting_planets") or []); weight=max(0.0,float(item.get("weight",1) or 1)); states=[str(digs.get(p,"NEUTRAL")).upper() for p in planets]
        pos=sum(s in {"EXALTED","OWN","OWN_SIGN","MOOLATRIKONA","VARGOTTAMA"} for s in states); neg=sum(s in {"DEBILITATED","ENEMY","M RITA","MRITA"} for s in states)
        value=0.0 if not states else max(-1.0,min(1.0,(pos-neg)/len(states))); weighted+=value*weight; total+=weight
        rows.append({"proposition_id":item.get("proposition_id"),"supporting_planets":planets,"confirmation":round(value,4),"role":"CONFIRMATION_ONLY"})
    return {"contract_version":"d9-confirmation.v1","status":"OBSERVED","score":round(max(0,min(100,50+50*weighted/total if total else 50)),2),"independent_vote":False,"confirmations":rows}

