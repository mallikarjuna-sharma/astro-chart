"""Release 7 empirical-readiness gate and R4-R7 orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .defensibility import evaluate_defensibility
from .hierarchical_ranking import attach_hierarchy
from Field_Determination.structural_vocational_fit import compute_structural_fit
from .meaningful_margins import attach_meaningful_margin_tiers
from Field_Determination.exact_field_defensibility import attach_exact_field_contract
from .decision_summary import attach_decision_summaries
from .broad_domain_promise import compute_broad_domain_promise
from Field_Determination.field_methods.navamsha import score_navamsha_confirmation
from Field_Determination.field_methods.siddhamsha import score_siddhamsha
from Field_Determination.field_methods.shashtiamsha import score_shashtiamsha
from .d10_archetypes import d10_chart_native_archetype_scores
from .decision_axes import attach_decision_axes
from .audit_ledgers import attach_audit_ledgers
from .d10_verification import assess_d10_verification

READINESS_VERSION = "empirical-readiness.r7.v1"


def apply_release_4_7(rows: list[dict], canonical_report: Mapping[str, Any], payload: Any = None) -> tuple[list[dict], dict]:
    frozen = [(row.get("field_id"), row.get("final_score")) for row in rows]
    d10_archetypes = d10_chart_native_archetype_scores(payload) if payload is not None else {"contract_version":"d10-archetypes.v1","scores":{},"status":"MISSING"}
    d10_verification = assess_d10_verification(payload, canonical_report) if payload is not None else {"fact_status":"MISSING","authority_eligible":False}
    for row in rows:
        methods = row.get("method_normalized_scores") or row.get("method_scores_normalized_0_100") or row.get("method_scores_normalized") or {}
        affinity = row.get("affinity_planets") or {}
        propositions = [{"proposition_id": f"field:{row.get('field_id')}", "supporting_planets": list(affinity)[:4], "weight": 1.0}]
        row["navamsha_confirmation"] = score_navamsha_confirmation(payload, propositions) if payload is not None else {"status":"MISSING","independent_vote":False}
        registry = row.get("registry_v12") or {}
        field_entry = {"field_id": row.get("field_id"), "curriculum": row.get("curriculum") or registry.get("curriculum") or {}}
        row["siddhamsha_education"] = score_siddhamsha(payload, field_entry, affinity) if payload is not None else {"status":"MISSING","permanent_vote":False}
        row["shashtiamsha_confirmation"] = score_shashtiamsha(payload, affinity) if payload is not None else {"status":"MISSING","independent_vote":False}
        row["d10_chart_native_archetypes"] = d10_archetypes
        row["d10_verification"] = d10_verification
        d1=float(methods.get("parashara",0) or 0); d10=float(methods.get("dashamsha",0) or 0); d24=row["siddhamsha_education"].get("educational_suitability")
        row["broad_domain_promise"] = compute_broad_domain_promise(d1,d10,d24)
        kp_audit=canonical_report.get("kp_cusp_audit") or {}
        row["kp_authority_audit"] = kp_audit
        if kp_audit.get("status") != "VERIFIED":
            kp_group=((((row.get("shadow_score_audit") or {}).get("dependency_reduction") or {}).get("groups") or {}).get("kp_corroboration") or {})
            kp_group["pre_audit_score"] = kp_group.get("score",0.0); kp_group["score"] = 0.0; kp_group["authority_suppressed"] = True
        row["structural_vocational_fit"] = compute_structural_fit(row, canonical_report)
    attach_hierarchy(rows)
    for row in rows:
        row["defensibility"] = evaluate_defensibility(row, canonical_report)
    attach_meaningful_margin_tiers(rows)
    attach_exact_field_contract(rows)
    attach_decision_summaries(rows)
    attach_decision_axes(rows, canonical_report)
    ledger_summary = attach_audit_ledgers(rows, canonical_report)
    # 2026-07 astrologer's audit, fix (2): attach_decision_axes() now
    # intentionally mutates final_score (a bounded multiplicative penalty
    # when a row's D1/D10 evidence disagrees severely -- see
    # decision_axes.py's _d1_d10_disagreement_penalty). The original blind
    # `assert frozen == [...]` compared raw (field_id, final_score) pairs
    # and would crash every production run where that penalty fires. This
    # is relaxed to check what actually matters: (a) field_id set and order
    # are unchanged (nothing was added/removed/reordered by the R4-R7 audit
    # steps themselves -- ordering is decision_axes' own responsibility now,
    # not an accidental side effect), and (b) any final_score change is
    # fully accounted for by that row's own recorded penalty_factor, i.e.
    # nothing else silently touched final_score.
    _frozen_ids = [fid for fid, _ in frozen]
    _current_ids = [row.get("field_id") for row in rows]
    assert _frozen_ids == _current_ids, (
        "R4-R7 audit steps changed field_id membership/order, which should never happen"
    )
    for (_fid, _orig_score), row in zip(frozen, rows):
        _new_score = row.get("final_score")
        if _orig_score == _new_score:
            continue
        _penalty = (row.get("decision_axes") or {}).get("d1_d10_disagreement_penalty") or {}
        _expected = _penalty.get("final_score_after_penalty")
        assert _penalty.get("applied_to_final_score") and _expected == _new_score, (
            f"final_score changed for {_fid} without a recorded, accounted-for penalty "
            f"(orig={_orig_score}, new={_new_score}, penalty_record={_penalty})"
        )
    established = sum((row.get("defensibility") or {}).get("tier") == "ESTABLISHED" for row in rows)
    summary = {
        "contract_version": READINESS_VERSION,
        "promotion_authorized": False,
        "status": "SHADOW_VALIDATED_SOFTWARE_ONLY",
        "candidate_count": len(rows),
        "established_count": established,
        "blocking_requirements": [
            "FROZEN_REVIEWED_LABELLED_OUTCOME_BENCHMARK",
            "PREREGISTERED_METRICS",
            "GOLDEN_D1_D9_D10_D24_KP_FIXTURES",
            "OUT_OF_SAMPLE_CALIBRATION",
            "REVIEWED_SIBLING_DISCRIMINATORS",
        ],
        "ranking_unchanged": True,
        "audit_ledgers": ledger_summary,
    }
    return rows, summary


def evaluate_benchmark(path: Path) -> dict:
    if not path.exists():
        return {"contract_version": READINESS_VERSION, "promotion_authorized": False, "status": "BLOCKED_MISSING_BENCHMARK"}
    data = json.loads(path.read_text(encoding="utf-8"))
    ok = data.get("status") == "FROZEN_REVIEWED" and bool(data.get("labels")) and bool(data.get("preregistered_metrics"))
    return {"contract_version": READINESS_VERSION, "promotion_authorized": bool(ok), "status": "READY_FOR_HOLDOUT_EVALUATION" if ok else "BLOCKED_INVALID_BENCHMARK"}
