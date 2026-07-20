"""Per-field evidence, score, selection, sibling, and lineage ledgers."""
from __future__ import annotations
from typing import Any, Mapping

METHODS=("knrao","kp","jaimini","parashara","dashamsha","sudarshana")

def _methods(row):return row.get("method_normalized_scores") or row.get("method_scores_normalized_0_100") or row.get("method_scores_normalized") or {}

def build_field_ledger(row:Mapping[str,Any],rank:int)->dict:
    axes=row.get("decision_axes") or {}
    return {"field_id":row.get("field_id"),"legacy_rank":rank,"legacy_relative_score":row.get("final_score"),
            "structural_fit":(row.get("structural_vocational_fit") or {}).get("score"),
            **{k:axes.get(k) for k in ("permanent_astro_fit","within_chart_index","educational_suitability","evidence_confidence","permanent_fit_interval")}}

def build_evidence_ledger(row:Mapping[str,Any])->dict:
    methods=_methods(row);items=[]
    components=row.get("method_components") or {}
    for method in METHODS:
        score=float(methods.get(method,0) or 0)
        atomic=components.get(method) if isinstance(components,Mapping) else None
        items.append({"evidence_id":f"method:{method}","method":method,"value":round(score,4),
                      "polarity":"POSITIVE" if score>0 else "NEUTRAL","dependency_group":method,
                      "atomic_components":atomic or {},"audit_placeholder":not bool(atomic)})
    d10=row.get("d10_chart_native_archetypes") or {}
    items.extend(d10.get("support_ledger",[]) or [])
    return {"field_id":row.get("field_id"),"evidence_items":items,
            "methods_with_atomic_components":sum(not i.get("audit_placeholder",False) for i in items if i.get("method")),
            "d10_status":d10.get("status"),"kp_status":(row.get("kp_authority_audit") or {}).get("status")}

def attach_audit_ledgers(rows:list[dict],canonical_report:Mapping[str,Any])->dict:
    by_family={}
    for row in rows:by_family.setdefault(str(row.get("career_family") or row.get("domain") or "UNCLASSIFIED"),[]).append(row)
    for rank,row in enumerate(rows,1):
        row["field_score_ledger"]=build_field_ledger(row,rank)
        row["evidence_ledger_v2"]=build_evidence_ledger(row)
        family=str(row.get("career_family") or row.get("domain") or "UNCLASSIFIED")
        peers=[p for p in by_family[family] if p is not row]
        nearest=min(peers,key=lambda p:abs(float(p.get("final_score",0))-float(row.get("final_score",0))),default=None)
        gap=abs(float(row.get("final_score",0))-float(nearest.get("final_score",0))) if nearest else None
        row["sibling_comparison_ledger"]={"family":family,"nearest_sibling_field_id":nearest.get("field_id") if nearest else None,
            "legacy_score_gap":round(gap,4) if gap is not None else None,"ordering_is_meaningful":bool(gap is not None and gap>=2.0),
            "comparison_status":"EVIDENCE_BACKED" if gap is not None and gap>=2.0 else "UNRESOLVED_SIBLINGS" if nearest else "FAMILY_ONLY"}
        axes=row.get("decision_axes") or {}
        forbidden=set(axes.get("excluded_from_permanent_fit",[]));used=set((axes.get("component_values") or {}).keys())
        row["prohibited_source_audit"]={"status":"PASSED" if not forbidden&used else "FAILED","hits":sorted(forbidden&used)}
    return {"contract_version":"audit-ledgers.v1","field_count":len(rows),
            "provenance_ok":bool((canonical_report.get("provenance_bundle") or {}).get("ok")),
            "lineage_clean":all((r.get("prohibited_source_audit") or {}).get("status")=="PASSED" for r in rows)}
