#!/usr/bin/env python3
"""Career-timeline CLI mode logic (--mode career / --mode both).

Extracted from field_deterministic_engine_v1_llm.py's (moved 2026-07-19
from Field_Determination/ to the repo root) `if __name__ == "__main__":`
block so that the main() entry point stays focused on argument parsing /
dispatch, and the career-mode logic lives alongside the rest of the
Job_Career package.

Public entry point: run_career_mode(payload, args, out_dir)
"""

import json
import os
import dataclasses


def _dump_job_debug(payload, out_dir):
    """Write job_debug.json: the exact data handed to the career-timeline HTML.

    Reproduces (without recomputing anything) the same fields that
    jyotish.web_report.generate_career_timeline_report() reads off `payload`
    just before rendering — blocks, transit outlook rows, career context, KP
    cusps/house-lords, D10 strength, natal facts, fixed karakas, and the
    confidence/retro-match summary. Kept in sync manually with that
    function's field list; if it starts reading new payload attributes,
    add them here too.

    Returns the path to the written job_debug.json file.
    """
    blocks = getattr(payload, "career_timeline", None) or []
    outlook_rows = getattr(payload, "annual_transit_outlook", None) or []
    career_ctx = getattr(payload, "career_context", None) or {}
    kp_cusps = getattr(payload, "kp_cusp_data", None) or {}
    house_lords = (
        {str(i): kp_cusps.get(f"H{i}", {}).get("sign_lord", "") for i in range(1, 13)}
        if kp_cusps else {}
    )
    d10_strength = getattr(payload, "d10_strength", 0.0)
    natal_facts = {
        "lagna_sign": getattr(payload, "lagna_sign", "") or getattr(payload, "d1_lagna", ""),
        "d10_house_occupancy": getattr(payload, "d10_house_occupancy", {}) or {},
    }
    fixed_karakas = {
        "AK": getattr(payload, "atmakaraka", ""),
        "AmK": getattr(payload, "amatyakaraka", ""),
    }

    retro_matches = 0
    if blocks:
        retro_matches = blocks[0].get("retro_matches", 0) or 0
    confidence = (blocks[0].get("confidence") if blocks else None) or {}

    debug_payload = {
        "name": getattr(payload, "name", "") or "Unknown",
        "career_timeline": blocks,
        "annual_transit_outlook": outlook_rows,
        "career_context": career_ctx,
        "kp_cusp_data": kp_cusps,
        "house_lords": house_lords,
        "d10_strength": d10_strength,
        "natal_facts": natal_facts,
        "fixed_karakas": fixed_karakas,
        "retro_matches": retro_matches,
        "confidence": confidence,
    }

    out_path = os.path.join(out_dir, "job_debug.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(debug_payload, fh, indent=2, ensure_ascii=False, default=str)
    return out_path


def run_career_mode(payload, args, out_dir):
    """Run the '--mode career' / '--mode both' CLI branch.

    Parameters
    ----------
    payload : the parsed chart payload (jyotish.engine_io.parse_json_payload output)
    args    : argparse.Namespace from the CLI (unused directly here, kept for
              parity/future flags)
    out_dir : str, output directory for generated HTML reports
    """
    from Job_Career.timeline import TimelineChartInput

    # ── Debug: inputs ("prompt") going into build_career_timeline ─────────
    _cc = getattr(payload, "career_context", {}) or {}
    _chi = TimelineChartInput.from_payload(payload)
    print("\n" + "═" * 80)
    print("CAREER TIMELINE INPUT — career_context")
    print("═" * 80)
    _redact_debug = bool(getattr(payload, "redact_debug_output", True))
    print(json.dumps(
        {"redacted": True, "keys_present": sorted(_cc.keys())} if _redact_debug else _cc,
        indent=2, ensure_ascii=False, default=str,
    ))
    print("\n" + "─" * 80)
    print("CAREER TIMELINE INPUT — TimelineChartInput chart fields")
    print("─" * 80)
    print(json.dumps(
        {"redacted": True, "input_contract": type(_chi).__name__}
        if _redact_debug else dataclasses.asdict(_chi),
        indent=2, ensure_ascii=False, default=str,
    ))

    # ── LLM narrative enrichment ──────────────────────────────────────────
    # Phase 0 context (career_theme_str, weight_overrides, intent_tags)
    # is stored on the payload by engine_io after enrich_career_context().
    _llm_ctx = getattr(payload, "llm_context", {}) or {}
    _career_theme = _llm_ctx.get("career_theme_str", "")
    # field_selection_context: analytical_breakdown from llm.py Step 1 selector
    # Stored on the payload after run_engine() completes (engine.py wires it).
    _field_ctx = getattr(payload, "llm_selection_rationale", "") or ""

    # LLM on/off switch: same consent gate as career_field_report_v2.py.
    # LLM usage can be granted per-chart (student_context.external_llm_consent
    # in the chart JSON) or globally via the LLM_REPORT_CONSENT env var
    # (.env). The env var is a blanket on/off switch for every report run in
    # this environment; the per-chart flag still works on its own for callers
    # who want consent scoped to a single student rather than the whole box.
    _env_llm_consent = str(os.getenv("LLM_REPORT_CONSENT", "")).strip().lower() in {"1", "true", "yes", "on"}
    _llm_consent = bool(getattr(payload, "external_llm_consent", False)) or _env_llm_consent
    if _env_llm_consent:
        print("[career_mode_runner] LLM consent granted via LLM_REPORT_CONSENT env var.")

    _raw_timeline = getattr(payload, "career_timeline", []) or []
    if _raw_timeline and _llm_consent:
        try:
            from jyotish.llm_narrative_builder import enrich_timeline_sync
            print(f"\nEnriching {len(_raw_timeline)} AD block(s) with LLM narratives ...")
            _enriched = enrich_timeline_sync(
                _raw_timeline, _cc, chart_input=_chi,
                career_theme_str=_career_theme,
                field_selection_context=_field_ctx,
                run_phase2_resolution=True,
            )
            payload.career_timeline = _enriched
            print("LLM enrichment complete.")
        except Exception as _le:
            import traceback
            traceback.print_exc()
            print(f"LLM enrichment failed (deterministic narratives preserved): {_le}")
    elif _raw_timeline and not _llm_consent:
        print(
            "\n[PRIVACY] LLM narrative enrichment skipped: external_llm_consent is "
            "false and LLM_REPORT_CONSENT is not set. Deterministic narratives preserved."
        )

    # ── Debug: dump the exact data handed to the HTML renderer ─────────────
    # Mirrors the same fields jyotish.web_report.generate_career_timeline_report()
    # reads off `payload` right before it builds the HTML, so job_debug.json is
    # a faithful snapshot of "what the career timeline HTML actually received"
    # (post LLM-enrichment, pre-render).
    try:
        _job_debug_path = _dump_job_debug(payload, out_dir)
        print(f"\nCareer timeline HTML input dump: {_job_debug_path}")
    except Exception as _jd_err:
        import traceback
        traceback.print_exc()
        print(f"\njob_debug.json dump failed: {_jd_err}")

    # ── Generate HTML report ──────────────────────────────────────────────
    try:
        from jyotish.web_report import generate_career_timeline_report
        career_html = generate_career_timeline_report(payload, output_dir=out_dir)
        if career_html:
            print("\nCareer Timeline report: " + career_html)
            _foreign_html = os.path.join(
                os.path.dirname(career_html),
                os.path.basename(career_html).replace("career_timeline", "foreign_opportunities"),
            )
            if os.path.exists(_foreign_html):
                print("Foreign Opportunity report: " + _foreign_html)
        else:
            print("\nCareer Timeline report: (no output generated — career_timeline may be empty)")
    except Exception as _e:
        import traceback
        traceback.print_exc()
        print("\nCareer timeline report generation failed: " + str(_e))

    # ── Debug: enriched Career Timeline JSON ────────────────────────────────
    timeline = getattr(payload, "career_timeline", []) or []
    if timeline:
        print("\n" + "═" * 80)
        print(f"CAREER TIMELINE OUTPUT — {len(timeline)} period(s) (LLM-enriched where available)")
        print("═" * 80)
        for blk in timeline:
            print(json.dumps(blk, indent=2, ensure_ascii=False, default=str))
            print("-" * 40)
    else:
        print("\n[Career Timeline] No blocks generated (career_context missing or blocked).")
