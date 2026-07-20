"""D1/D10 vocational promise separated from exact modern leaves."""
from __future__ import annotations

def compute_broad_domain_promise(d1_score, d10_score, d24_score=None) -> dict:
    values=[float(d1_score),float(d10_score)]; weights=[.55,.45]
    if d24_score is not None: values.append(float(d24_score)); weights=[.40,.35,.25]
    if any(not 0<=v<=100 for v in values): raise ValueError("broad-domain inputs must be 0..100")
    mean=sum(v*w for v,w in zip(values,weights)); disagreement=max(values)-min(values)
    score=max(0.0,min(100.0,mean-.10*disagreement-.10*max(0.0,25-min(values))))
    status="STRONGLY_PROMISED" if score>=60 and min(values[:2])>=40 and disagreement<=25 else "PROMISED" if score>=45 and min(values[:2])>=30 else "CONDITIONAL" if score>=35 else "WEAK"
    return {"contract_version":"broad-domain-promise.v1","score":round(score,4),"status":status,"inputs":{"d1":values[0],"d10":values[1],"d24":values[2] if len(values)>2 else None},"disagreement":round(disagreement,4),"scope":"BROAD_DOMAIN_ONLY"}

