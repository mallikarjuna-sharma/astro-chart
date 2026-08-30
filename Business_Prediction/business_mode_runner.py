#!/usr/bin/env python3
"""Business-prediction CLI mode logic (--mode business).

Mirrors Job_Career/career_mode_runner.py's run_career_mode() shape so the
main CLI dispatcher can add a 'business' branch the same way it already
has 'career' / 'field' / 'stream' branches.

Public entry point: run_business_mode(payload, args, out_dir)
"""
import json
import os


def _dump_business_debug(prediction: dict, name: str, out_dir: str) -> str:
    """Write business_debug.json: the exact data handed to the business
    prediction HTML, for parity with Job_Career/career_mode_runner.py's
    _dump_job_debug().
    """
    debug_payload = {
        "name": name or "Unknown",
        "mode_gate": prediction.get("mode_gate", {}),
        "significators": prediction.get("significators", {}),
        "top_sectors": prediction.get("top_sectors", []),
        "timed_windows": prediction.get("timed_windows", []),
        "timing_status": prediction.get("timing_status", {}),
        "method_status": prediction.get("method_status", {}),
        "recommendation": prediction.get("recommendation", {}),
        "authoritative_recommendation": prediction.get("authoritative_recommendation", {}),
        "model_status": prediction.get("model_status"),
        "calibration_status": prediction.get("calibration_status"),
        "calibration_state": prediction.get("calibration_state", {}),
        "evidence_basis": prediction.get("evidence_basis"),
        "maturity_statement": prediction.get("maturity_statement"),
        "maturity_caveats": prediction.get("maturity_caveats", []),
        "rule_pack_version": prediction.get("rule_pack_version"),
        "forecast_window": prediction.get("forecast_window", {}),
        # v17: the nine separately-computed promise/fit/confidence fields
        # plus the supporting D24/D60/KP-10th-cusp/sign-modality/operating-
        # model/contradiction layers, so they're inspectable from the CLI
        # output the same way every other layer already is.
        "business_promise": prediction.get("business_promise"),
        "job_promise": prediction.get("job_promise"),
        "business_promise_layers": prediction.get("business_promise_layers", {}),
        "job_promise_layers": prediction.get("job_promise_layers", {}),
        "independent_profession_promise": prediction.get("independent_profession_promise"),
        "business_field_fit": prediction.get("business_field_fit"),
        "business_execution_capacity": prediction.get("business_execution_capacity"),
        # v42 audit fix: business_execution_capacity_components/
        # business_stability_components (added v41 -- client_acquisition/
        # commercial_execution/capital_debt_management/operational_
        # liability_risk/self_agency and business_durability/cash_flow_
        # stability/ownership_stability respectively) were computed by the
        # engine but never surfaced in this CLI debug dump, so a reader of
        # business_debug.json had no way to see the sub-dimension breakdown
        # the aggregate scores were un-blended from.
        "business_execution_capacity_components": prediction.get("business_execution_capacity_components", {}),
        "competency_readiness": prediction.get("competency_readiness"),
        "business_profitability": prediction.get("business_profitability"),
        "gross_revenue_potential": prediction.get("gross_revenue_potential"),
        "profit_retention": prediction.get("profit_retention"),
        "business_stability": prediction.get("business_stability"),
        "business_stability_components": prediction.get("business_stability_components", {}),
        "current_timing_readiness": prediction.get("current_timing_readiness"),
        "business_over_job_confidence": prediction.get("business_over_job_confidence", {}),
        "business_advantage_margin": prediction.get("business_advantage_margin"),
        "business_advantage_label": prediction.get("business_advantage_label"),
        "strong_business_absolute_floor_met": prediction.get("strong_business_absolute_floor_met"),
        "operating_model": prediction.get("operating_model", {}),
        "operating_model_d10": prediction.get("operating_model_d10", {}),
        # Item 7 audit fix: D1-vs-D10 operating-model synthesis (agreement /
        # compatible-hybrid label / D10-near-term-precedence framing) was
        # computed but missing from this allowlist -- same class of gap as
        # the janma_nakshatra_full_chain/d10_rectification_sensitivity note
        # above.
        "operating_model_synthesis": prediction.get("operating_model_synthesis", {}),
        "contradiction_findings": prediction.get("contradiction_findings", []),
        "d24_competency_status": prediction.get("d24_competency_status", {}),
        "d60_confirmation_status": prediction.get("d60_confirmation_status", {}),
        "d11_gains_status": prediction.get("d11_gains_status", {}),
        "sign_modality_profile": prediction.get("sign_modality_profile", {}),
        "kp_10th_cusp_job_vs_business": prediction.get("kp_10th_cusp_job_vs_business", {}),
        # v25: 8-guard false-conclusion checklist (spec section 15) -- was
        # computed and returned by compute_business_prediction() but not
        # yet surfaced in this debug dump.
        "false_conclusion_guard_checklist": prediction.get("false_conclusion_guard_checklist", []),
        # v25: literal-ordered traces for spec section 7 (10-step KN Rao
        # sequence) and section 16 (20-step final decision hierarchy) --
        # each step cites the real already-computed value it corresponds
        # to, so the sequencing itself is inspectable, not just documented.
        "kn_rao_validation_sequence": prediction.get("kn_rao_validation_sequence", []),
        "final_decision_hierarchy_trace": prediction.get("final_decision_hierarchy_trace", []),
        # audit fix: detected_yogas/legal_dispute_risk/d2_hora_evidence are
        # always added to compute_business_prediction()'s result dict, and
        # partnership_synastry is added when a partner payload is supplied
        # -- none of the four were in this allowlist, so business_debug.json
        # silently omitted them even though the HTML reports (which read the
        # live prediction dict directly) render them correctly.
        "detected_yogas": prediction.get("detected_yogas", []),
        "yoga_detection_status": prediction.get("yoga_detection_status", "NOT_EVALUATED"),
        "legal_dispute_risk": prediction.get("legal_dispute_risk", []),
        "legal_dispute_risk_status": prediction.get("legal_dispute_risk_status", "NOT_EVALUATED"),
        "d2_hora_evidence": prediction.get("d2_hora_evidence", []),
        "d2_hora_deep_evidence": prediction.get("d2_hora_deep_evidence", {}),
        "mercury_adjudication": prediction.get("mercury_adjudication", {}),
        "janma_nakshatra_evidence": prediction.get("janma_nakshatra_evidence", []),
        # audit fix (remaining-gaps pass): janma_nakshatra_full_chain and
        # d10_rectification_sensitivity are always added to
        # compute_business_prediction()'s result dict (same as
        # d2_hora_evidence/janma_nakshatra_evidence above) but were missing
        # from this allowlist, so business_debug.json silently omitted them.
        "janma_nakshatra_full_chain": prediction.get("janma_nakshatra_full_chain", {}),
        "d10_rectification_sensitivity": prediction.get("d10_rectification_sensitivity", {}),
        "foreign_business_evidence": prediction.get("foreign_business_evidence", []),
        "partnership_synastry": prediction.get("partnership_synastry"),
        # Capital/financial evidence lives under the authoritative result;
        # mirror it here so CLI audits do not silently lose the new gate.
        "capital_readiness_status": prediction.get("authoritative_recommendation", {}).get("capital_readiness_status"),
        "capital_readiness_certified": prediction.get("authoritative_recommendation", {}).get("capital_readiness_certified", False),
        "financial_readiness": prediction.get("authoritative_recommendation", {}).get("financial_readiness", {}),
        "ashtakavarga_year_check": prediction.get("authoritative_recommendation", {}).get("ashtakavarga_year_check"),
        "muhurta_check": prediction.get("authoritative_recommendation", {}).get("muhurta_check"),
    }
    out_path = os.path.join(out_dir, "business_debug.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(debug_payload, fh, indent=2, ensure_ascii=False, default=str)
    return out_path


def run_business_mode(payload, args, out_dir):
    """Run the '--mode business' CLI branch.

    Parameters
    ----------
    payload : the parsed chart payload (jyotish.engine_io.parse_json_payload output)
    args    : argparse.Namespace from the CLI (unused directly here, kept for
              parity with run_career_mode)
    out_dir : str, output directory for generated HTML/debug files
    """
    from Business_Prediction.business_engine import compute_business_prediction
    from Business_Prediction.generate_business_report import (
        render_combined_report_html, _resolve_report_language,
        _load_business_registry,
    )

    name = getattr(payload, "name", "") or "Unknown"

    # v42 audit fix (user-caught via real generated CLI output, real bug):
    # this called compute_business_prediction(payload) with its default
    # top_n_sectors=5, silently truncating the CLI's own business_debug.json
    # and both HTML reports to 5 of the registry's 19 sectors -- the exact
    # v29 bug that generate_business_report.py's own generate_business_
    # report() function was fixed for, but this separate CLI entry point
    # was never updated to match. Always uses the full current registry
    # count, same as the other generation path, so results never silently
    # depend on which entry point produced them.
    all_sector_count = len(_load_business_registry().get("sectors", {}))
    prediction = compute_business_prediction(
        payload, top_n_sectors=all_sector_count,
        financial_readiness_inputs=getattr(args, "financial_readiness_inputs", None),
    )
    _dump_business_debug(prediction, name, out_dir)

    # v43 uplift: this CLI branch now mirrors generate_business_report()'s
    # single combined page (a "Chart Profile" / "Astrologer View" switch
    # on one page, replacing the earlier two-file astrologer/client
    # split) so both generation entry points produce the exact same
    # deliverable shape from the same prediction dict.
    # v31: also mirrors generate_business_report()'s Tamil/Telugu/English
    # localization, resolved from the same .env flags.
    lang = _resolve_report_language()
    combined_html = render_combined_report_html(name, prediction, lang=lang, payload=payload)

    os.makedirs(out_dir, exist_ok=True)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = str(name).lower().replace(" ", "_")
    lang_suffix = f"_{lang}" if lang != "en" else ""
    combined_path = os.path.join(out_dir, f"business_prediction_report_{safe_name}{lang_suffix}_{ts}.html")
    with open(combined_path, "w", encoding="utf-8") as fh:
        fh.write(combined_html)

    print(f"[JyotishAI] Combined report written -> {combined_path}")
    return combined_path
