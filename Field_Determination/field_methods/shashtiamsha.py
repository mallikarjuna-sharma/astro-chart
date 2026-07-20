"""D60 bounded confirmation evidence owner."""
from __future__ import annotations
from typing import Any, Mapping
from jyotish.boosts import _d60_deity_quality

def score_shashtiamsha(payload: Any, field_affinity: Mapping[str,float]) -> dict:
    planets=getattr(payload,"planets_d1",{}) or {}; privileged=[getattr(payload,"h10_lord",""),getattr(payload,"atmakaraka",""),getattr(payload,"amatyakaraka","")]
    candidates=list(dict.fromkeys([p for p in privileged if p]+[p for p,_ in sorted((field_affinity or {}).items(),key=lambda x:-x[1])[:3]])); total=weighted=0.0; evidence=[]
    for p in candidates:
        data=planets.get(p) or {}; sign=data.get("sign");
        if not sign: continue
        weight=max(float((field_affinity or {}).get(p,0)),.15 if p in privileged else 0); quality=_d60_deity_quality(p,sign,float(data.get("degree",0) or 0)); weighted+=weight*quality; total+=weight
        evidence.append({"planet":p,"quality":quality,"weight":round(weight,4),"dependency_group":"d60_deity_vitality","role":"CONFIRMATION_ONLY"})
    score=50.0 if total<=0 else max(0,min(100,50+50*weighted/total))
    return {"contract_version":"d60-confirmation.v1","status":"OBSERVED" if total else "MISSING","score":round(score,2),"independent_vote":False,"evidence_items":evidence}

