"""Score-neutral V1.3-style decision axes with explicit semantics."""
from __future__ import annotations
from statistics import pstdev
from typing import Any, Mapping

WEIGHTS={"d1_synthesis":.28,"d10_vocation":.32,"jaimini_identity":.16,"kp_corroboration":.12,
         "sudarshana_confirmation":.04,"d10_native_domain":.08}
DOMAIN_ARCHETYPES={
    "engineering":{"engineering_systems":.60,"field_operations":.25,"technology":.15},
    "technology":{"technology":.55,"analysis":.25,"engineering_systems":.20},
    "medicine":{"care":.55,"research":.25,"analysis":.20},
    "arts":{"design":.60,"communication":.25,"commerce":.15},
    "law":{"scholarship_policy":.40,"public_authority":.35,"communication":.25},
    "science":{"research":.45,"analysis":.30,"scholarship_policy":.25},
    "business":{"commerce":.45,"administration":.35,"communication":.20},
    "education":{"scholarship_policy":.55,"communication":.25,"public_service":.20},
}

# BUGFIX (2026-07, audit P0): `.get(key, default)` only applies `default`
# when `key` is ABSENT -- it does nothing if the key is present with an
# explicit `None` value, which several upstream siddhamsha_education/etc.
# dicts can legitimately produce for a not-yet-computed sub-score. `_clamp`
# previously crashed with `TypeError: float() argument must be a string or a
# real number, not 'NoneType'` the moment that happened (found via a
# synthetic minimal test payload, but the same shape of missing-vs-None gap
# is called out generally in the 2026-07 audit's item 21 on distinguishing
# "not computed" from "0"/neutral defaults, so this is treated as the same
# class of defect rather than a one-off test fixture issue).
def _clamp(v):
    if v is None:
        return 0.0
    try:
        return max(0.0,min(100.0,float(v)))
    except (TypeError, ValueError):
        return 0.0

def _domain_native_score(row:Mapping[str,Any])->tuple[float,dict]:
    domain=str(row.get("domain","") or "").lower()
    scores=(row.get("d10_chart_native_archetypes") or {}).get("scores",{}) or {}
    mapping=next((weights for key,weights in DOMAIN_ARCHETYPES.items() if key in domain),{})
    if not mapping:return 0.0,{"status":"UNMAPPED_DOMAIN","domain":domain,"weights":{}}
    value=sum(float(scores.get(k,0))*w for k,w in mapping.items())/sum(mapping.values())
    return _clamp(value),{"status":"CALCULATED","domain":domain,"weights":mapping}

# 2026-07 astrologer's audit, fix (2): D1-vs-D10 disagreement penalty.
# Previously this module computed d1_synthesis vs d10_vocation disagreement
# (part of `permanent_astro_fit`) but never fed it back into `final_score` --
# `permanent_astro_fit` was explicitly non-authoritative shadow-only, so a
# field could rank #1 on `final_score` while its own D10 (career-specific)
# chart evidence flatly contradicted its D1 (general-life) evidence, and
# nothing in the authoritative ranking path ever discounted it for that.
# A working Jyotishi weighs D10 more heavily than D1 for "which field", and
# treats a severe D1/D10 split as a real reason to distrust a placement, not
# just an interesting footnote. This adds a bounded multiplicative penalty
# to `final_score` when the split exceeds a threshold, modeled on the same
# spread-penalty convention already used elsewhere in this engine
# (engine.py's _apply_paradigm_spread_penalty uses a 30-point spread
# trigger) for consistency: 30-50 point split -> up to -8%, 50+ point split
# -> up to -15%, scaled linearly within each band. This is a MODEST penalty
# by design (matching the user's "modest multiplicative penalty" framing) --
# it reorders close calls without being a hard veto on a field that has
# other strong corroboration.
D1_D10_DISAGREEMENT_PENALTY_VERSION = "d1-d10-disagreement-penalty.v1"


def _d1_d10_disagreement_penalty(d1_synthesis: float, d10_vocation: float) -> tuple[float, dict]:
    split = abs(d1_synthesis - d10_vocation)
    if split <= 30.0:
        factor = 1.0
        band = "NONE"
    elif split <= 50.0:
        # Linear 0% -> 8% penalty across the 30-50 point band.
        factor = 1.0 - 0.08 * ((split - 30.0) / 20.0)
        band = "MODERATE"
    else:
        # Linear 8% -> 15% penalty across 50-100+ points, capped at 15%.
        factor = 1.0 - min(0.15, 0.08 + 0.07 * ((split - 50.0) / 50.0))
        band = "SEVERE"
    return round(factor, 6), {
        "d1_d10_split": round(split, 4), "band": band,
        "penalty_factor": round(factor, 6), "penalty_pct": round((1.0 - factor) * 100.0, 2),
    }


def attach_decision_axes(rows:list[dict],canonical_report:Mapping[str,Any])->list[dict]:
    provenance=canonical_report.get("provenance_bundle") or {}
    critical_ok=bool(provenance.get("ok",False))
    for row in rows:
        groups=((((row.get("shadow_score_audit") or {}).get("dependency_reduction") or {}).get("groups")) or {})
        values={k:_clamp((groups.get(k) or {}).get("score",0)) for k in WEIGHTS if k!="d10_native_domain"}
        native,native_trace=_domain_native_score(row);values["d10_native_domain"]=native
        permanent=sum(values[k]*WEIGHTS[k] for k in WEIGHTS)
        educational=_clamp((row.get("siddhamsha_education") or {}).get("educational_suitability",50))
        method_values=[v for k,v in values.items() if k not in {"sudarshana_confirmation"} and v>0]
        agreement=max(0.0,100.0-(pstdev(method_values) if len(method_values)>1 else 35.0)*2.0)
        provenance_factor=1.0 if critical_ok else .70
        backed=min(1.0,len(method_values)/4.0)
        confidence=_clamp((.60*agreement+.40*backed*100)*provenance_factor)
        half=5 if confidence>=75 else 8 if confidence>=60 else 12 if confidence>=45 else 18

        # Fix (follow-up, same session): jyotish/evidence_integrity.py's
        # reduce_method_evidence() builds d10_vocation's group purely from
        # `present = {method: scores[method] for method in ("dashamsha",)
        # if method in method_scores}` -- if "dashamsha" is simply ABSENT
        # from this row's method scores (not scored, not merely low), the
        # empty dict collapses to score=0.0, indistinguishable from a real
        # dashamsha score of 0. Without this guard, that absence would look
        # identical to a maximal D1/D10 contradiction and trigger the
        # "SEVERE" -15% penalty band below for every field where the
        # dashamsha method simply didn't run -- punishing missing data as if
        # it were disagreeing data, which is not what a real Jyotishi does
        # (no D10 reading at all is a reason to lower confidence, not a
        # reason to conclude the vocational chart actively contradicts D1).
        _method_scores_present = (
            row.get("method_normalized_scores")
            or row.get("method_scores_normalized_0_100")
            or row.get("method_scores_normalized")
            or {}
        )
        _d10_data_present = "dashamsha" in _method_scores_present

        original_final_score = round(float(row.get("final_score", 0)), 4)
        if _d10_data_present:
            penalty_factor, penalty_detail = _d1_d10_disagreement_penalty(
                values.get("d1_synthesis", 0.0), values.get("d10_vocation", 0.0)
            )
        else:
            penalty_factor, penalty_detail = 1.0, {
                "d1_d10_split": None, "band": "SKIPPED_D10_DATA_MISSING",
                "penalty_factor": 1.0, "penalty_pct": 0.0,
            }
        if penalty_factor < 1.0:
            row["final_score"] = round(original_final_score * penalty_factor, 4)

        row["decision_axes"]={
            "contract_version":"decision-axes.v1-shadow","authoritative":False,
            "legacy_relative_score":original_final_score,
            "permanent_astro_fit":round(permanent,4),"within_chart_index":None,
            "educational_suitability":round(educational,4),"evidence_confidence":round(confidence,4),
            "confidence_label":"HIGH" if confidence>=75 else "MODERATE_HIGH" if confidence>=60 else "MODERATE" if confidence>=45 else "LOW",
            "permanent_fit_interval":[round(_clamp(permanent-half),2),round(_clamp(permanent+half),2)],
            "timing_readiness":None,"component_values":{k:round(v,4) for k,v in values.items()},
            "authority_weights":WEIGHTS,"d10_domain_mapping":native_trace,
            "excluded_from_permanent_fit":["d9","d24","dasha","transit","student_preference","gender","risk_appetite","route","market","llm","relative_rank"],
            "provenance_ok":critical_ok,"calibration_version":"bounded-native-shadow.v1-no-population-anchors",
            "d1_d10_disagreement_penalty":{
                **penalty_detail,
                "contract_version": D1_D10_DISAGREEMENT_PENALTY_VERSION,
                "final_score_before_penalty": original_final_score,
                "final_score_after_penalty": round(float(row.get("final_score", 0)), 4),
                "applied_to_final_score": penalty_factor < 1.0,
            },
        }
    vals=[(r.get("decision_axes") or {}).get("permanent_astro_fit",0) for r in rows]
    lo,hi=(min(vals),max(vals)) if vals else (0,0)
    for row,value in zip(rows,vals):
        idx=(value-lo)/(hi-lo)*100 if hi-lo>=1 else 50.0
        row["decision_axes"]["within_chart_index"]=round(_clamp(idx),4)
        row["decision_axes"]["within_chart_index_semantics"]="DISPLAY_ONLY_RELATIVE_NOT_CONFIDENCE"
    # NOTE: deliberately NOT re-sorting `rows` here even though final_score
    # may have changed above. release_candidate.py's frozen-invariant check
    # (apply_release_4_7) asserts field_id ORDER is unchanged through the
    # R4-R7 audit steps (to catch accidental corruption) and treats
    # reordering as this module's caller's responsibility, not this
    # function's. The actual re-sort by (possibly penalized) final_score
    # happens in jyotish/engine.py's run_engine(), immediately after
    # apply_release_4_7 returns, before results are handed to the caller.
    return rows
