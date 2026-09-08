"""Output layer for the under-15 stream engine: JSON payload + standalone HTML.

Deliberately does not import jyotish/output.py's ExplainabilityEngine (built
around 199 field cards, route-suitability badges, etc.) -- this report is
much simpler by design: 3 streams, each with its ranked subject list.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime
from typing import Any, Dict

from jyotish.validation_contract import UNIVERSAL_DISCLAIMER
from subject_registry import STREAM_META
from field_derived_stream import FIELD_DERIVED_EVIDENCE_CAP

# 2026-07-24: bumped v4->v5 -- CRITICAL bug #1 fix (see
# md/STREAM_DETERMINATION_CRITICAL_FIXES_20260724.md): surfaced
# numeric_rank/d1_candidate_rank/precedence_decision/recommended_stream
# explicitly, and added recommendation_basis_note so a reader can no longer
# be misled when recommended_stream != the highest normalized_score stream.
REPORT_CONTRACT_VERSION = "stream-determination-report.v5"


# 2026-08-22 audit fix (gap 6): companion to STREAM_META's Rahu/Ketu weights
# in subject_registry.py -- those weights carry a source comment noting
# Rahu/Ketu significator use in Science is "NOT a BPHS-original... common
# Jaimini-adjacent practice, not a classical BPHS doctrine", but that
# disclosure never reached a generated report. This surfaces it as a short
# note whenever Rahu/Ketu is one of a stream's weighted signature planets
# AND actually carries meaningful (above-baseline) strength for this chart.
_RAHU_KETU_CAVEAT_TEXT = (
    "Note: Rahu/Ketu weighting for this stream reflects contemporary "
    "practitioner usage, not classical BPHS doctrine."
)


def _rahu_ketu_caveat(stream_id: str, planet_strengths: Dict[str, Any]) -> str | None:
    meta = STREAM_META.get(stream_id, {})
    weights = meta.get("planets", {}) or {}
    for shadow_planet in ("Rahu", "Ketu"):
        if shadow_planet not in weights:
            continue
        strength = planet_strengths.get(shadow_planet)
        if strength is None:
            continue
        try:
            if float(strength) > 1.0:
                return _RAHU_KETU_CAVEAT_TEXT
        except (TypeError, ValueError):
            continue
    return None


def build_report_payload(
    payload: Any, determination: Dict[str, Any], *,
    forced_override: bool = False, eligibility_status: str = "NORMAL",
    cross_validation: Dict[str, Any] | None = None,
    stream_narrative: Dict[str, Any] | None = None,
    report_view: str = "astrologer",
) -> Dict[str, Any]:
    """Wrap the raw scoring output with chart identity + disclaimer for JSON export.

    GAP-FIX (2026-07-22, audit gap 25): `forced_override`/`eligibility_status`
    make it explicit when a report was generated with force=True on a chart
    whose current_age is >= 15 (valid for regression testing, but the report
    must say so rather than silently presenting a test run as a normal
    "Strongest Match" recommendation for a child).
    """
    # GAP-FIX (2026-07-22, audit): stamp the same source_sha256/chart_path
    # jyotish/engine_io.py already computes at parse time (payload.
    # source_identity) into every stream report. Without this, two reports
    # for a same-named chart file generated at different times had no way
    # to prove whether they were scored against the same underlying chart
    # data -- confirmed live during this audit: a chart's own on-disk
    # shadbala_virupas values had drifted between two report-generation
    # runs, and nothing in the report could reveal that.
    source_identity = getattr(payload, "source_identity", {}) or {}
    return {
        "contract_version": REPORT_CONTRACT_VERSION,
        "engine_version": determination.get("engine_version"),
        "calculation_profile": determination.get("calculation_profile", "UNKNOWN"),
        "scoring_contract_version": determination.get("scoring_contract_version"),
        "engine_build_fingerprint": determination.get("engine_build_fingerprint", {}),
        "calculation_identity": determination.get("calculation_identity", {}),
        "input_quality": determination.get("input_quality", {}),
        "calibration": determination.get("calibration", {}),
        "forced_override": forced_override,
        "eligibility_status": eligibility_status,
        "name": getattr(payload, "name", "") or "Unknown",
        "current_age": getattr(payload, "current_age", None),
        "dob": getattr(payload, "dob", ""),
        "source_identity": {
            "source_sha256": source_identity.get("source_sha256", "NOT_AVAILABLE"),
            "chart_path": source_identity.get("chart_path", "NOT_SUPPLIED"),
            "note": (
                "Hash of the raw chart JSON this report was scored against. "
                "Two reports for a same-named chart file are only guaranteed "
                "to reflect identical underlying data if this hash matches."
            ),
        },
        "eligibility_note": (
            "Generated by the early-age (<15) Stream Determination engine, not "
            "the main Field Determination engine. Recommends broad Science / "
            "Commerce / Humanities direction and subject choices only -- not "
            "specific vocational branches, which are only meaningful once a "
            "stream and subject combination has actually been chosen."
        ),
        "dominant_stream": determination.get("dominant_stream"),
        "top_ranked_stream": determination.get("top_ranked_stream"),
        # GAP-FIX (2026-07-24, CRITICAL bug #1): see stream_scoring.py's
        # SCORING_CONTRACT_VERSION v7 note. numeric_rank/d1_candidate_rank/
        # precedence_decision/recommended_stream are now separate, named
        # fields instead of being implied by streams[] list order.
        "numeric_rank": determination.get("numeric_rank", []),
        "d1_candidate_rank": determination.get("d1_candidate_rank", []),
        "precedence_decision": determination.get("precedence_decision"),
        "recommended_stream": determination.get("recommended_stream"),
        # A reader who only glances at "recommended_stream" and the streams[]
        # score list could otherwise be misled exactly the way the
        # 2026-07-24 external review was (recommended stream shown with a
        # LOWER normalized_score than another stream) -- state explicitly
        # whenever that's the case, and always state the basis.
        "recommendation_basis_note": (
            (
                "recommended_stream ({rec}) is the classical-precedence-informed pick "
                "(see precedence_chain_resolution_stage='{stage}'), NOT the raw "
                "numeric score leader ({num}). Compare the two streams' "
                "normalized_score in streams[] / numeric_rank before treating this as "
                "a purely score-based ranking."
            ).format(
                rec=determination.get("recommended_stream"),
                stage=determination.get("precedence_chain_resolution_stage"),
                num=(determination.get("numeric_rank") or [None])[0],
            )
            if (determination.get("recommended_stream")
                and determination.get("numeric_rank")
                and determination.get("recommended_stream") != determination["numeric_rank"][0])
            else (
                "recommended_stream matches the raw numeric score leader "
                "(numeric_rank[0]) for this chart."
            )
        ),
        "recommendation_status": determination.get("recommendation_status", "UNKNOWN"),
        "evidence_completeness": determination.get("evidence_completeness", 0.0),
        "planet_strength_coverage": determination.get("planet_strength_coverage", 0.0),
        "score_gap_top_two": determination.get("score_gap_top_two", 0.0),
        "is_close_call": determination.get("is_close_call", False),
        "close_call_note": determination.get("close_call_note", ""),
        # GAP-FIX (audit, 2026-07-23): every stream bunched within the
        # near-tie margin of its neighbor, in ranked order -- lets the
        # report distinguish a genuine 2-way tie from a 3-way toss-up.
        "tied_streams": determination.get("tied_streams", []),
        # GAP-FIX (audit #66): which stream each rubric section alone would
        # pick, vs the final combined winner -- see stream_scoring.py.
        "disagreement_ledger": determination.get("disagreement_ledger", {}),
        # BUGFIX (2026-07-24, full-production D24-arbitration run): these two
        # keys are produced by compute_stream_determination() (see
        # stream_scoring.py ~L2980) but were never copied into the saved
        # report dict here, so every report silently dropped the D24/JAIMINI
        # arbitration outcome even though the policy ran and could have
        # changed top_ranked_stream. Restored so d1_arbitration_status /
        # d1_arbitration_detail are actually visible on disk.
        "d1_arbitration_status": determination.get("d1_arbitration_status"),
        "d1_arbitration_detail": determination.get("d1_arbitration_detail"),
        # GAP-FIX (2026-07-24): CLASSICAL PRECEDENCE CHAIN -- see
        # stream_scoring.py's _apply_classical_precedence_chain() and the
        # large comment block above it. Restored into the saved report the
        # same way d1_arbitration_status/_detail were (see BUGFIX note
        # directly above) so this is never silently dropped either.
        "precedence_chain_resolution_stage": determination.get("precedence_chain_resolution_stage"),
        "precedence_chain_detail": determination.get("precedence_chain_detail"),
        # GAP-FIX (2026-07-24, dasha as_of_date reproducibility): the exact
        # calendar date Stage 4 (dasha-relevance) used as "today" -- see
        # stream_scoring.py's compute_stream_determination(as_of_date=...).
        "evaluation_as_of_date": determination.get("evaluation_as_of_date"),
        # GAP-FIX (audit #45): non-None only when current_age indicates an
        # adult chart -- independent, second age check at the scoring layer
        # itself, not just the CLI's forced_override/eligibility_status.
        "age_routing_note": determination.get("age_routing_note"),
        "streams": [
            {
                "stream_id": s["stream_id"],
                "label": s["label"],
                "sub_archetype": s.get("sub_archetype", "General"),
                "description": s.get("description", ""),
                "score": s.get("score"),
                "normalized_score": s.get("normalized_score"),
                "score_rubric": s.get("score_rubric", {}),
                "score_compression": s.get("score_compression", {}),
                "role_placement_data_status": s.get("role_placement_data_status", "UNKNOWN"),
                # GAP-FIX (audit #62): cross-section NEUTRAL_NO_SIGNAL vs
                # POSITIVE_SUPPORT consistency, previously only on d24.
                "role_placement_signal_state": s.get("role_placement_signal_state", "UNKNOWN"),
                "relational_d1_signal_state": s.get("relational_d1_signal_state", "UNKNOWN"),
                "d24_confirmation_signal_state": s.get("d24_confirmation_signal_state", "UNKNOWN"),
                "trace": s.get("trace", []),
                "subjects": s.get("subjects", []),
                # 2026-08-22 audit fix (gap 6): the Rahu/Ketu "not BPHS-
                # original, contemporary-practice" caveat previously existed
                # only as a source comment in subject_registry.py, invisible
                # to anyone reading a generated report. Surface it here
                # whenever Rahu or Ketu meaningfully contributed to this
                # stream's score (i.e. is one of its weighted signature
                # planets AND has an above-baseline eff_strength).
                "rahu_ketu_caveat": _rahu_ketu_caveat(
                    s["stream_id"], determination.get("planet_strengths", {}) or {}
                ),
                # Round 4 addition: which classical yogas (Budha-Aditya,
                # Saraswati, Dharma-Karmadhipati, Gaja-Kesari, Dhana) were
                # detected as present AND relevant to this stream, and the
                # bounded score adjustment they produced -- see
                # stream_scoring.py::score_stream's "yoga_detection" field,
                # wired through the same way "rahu_ketu_caveat" was wired in
                # round 2.
                "yoga_detection": s.get("yoga_detection", {}),
            }
            for s in determination.get("streams", [])
        ],
        "planet_strengths": determination.get("planet_strengths", {}),
        # GAP-FIX ("include the comparison in the final report"): independent
        # cross-check against Field_Determination's own adult-engine macro
        # career cluster -- see Stream_Determination/cross_validate.py. None
        # if the caller skipped it (include_cross_validation=False).
        "cross_validation": cross_validation,
        # None unless compute_stream_determination() was called with
        # include_field_derived_evidence=True (default False -- experimental).
        "field_determination_evidence": determination.get("field_determination_evidence"),
        "stream_narrative": stream_narrative,
        # Audience switch: "astrologer" (default) shows the full technical
        # report -- rubric/section breakdowns, classical yoga detections,
        # the disagreement ledger, cross-validation and any field-derived
        # evidence panel, plus the astrological-reasoning narrative column.
        # "parent" shows only the plain-language recommendation surfaces
        # (hero, scoreboard, the parent-facing narrative paragraph) and
        # hides every astrologer-technical section, including the
        # "Astrological reasoning" narrative column, which is not rendered
        # at all in parent view rather than merely relabeled.
        "report_view": report_view if report_view in ("astrologer", "parent") else "astrologer",
        # GAP-FIX (2026-07-22, audit gap 22): scores like "95.5" or "Physics
        # 89.3" visually resemble calibrated probabilities or validated
        # percentages -- they are not. State this explicitly rather than
        # letting the number format imply a precision the engine doesn't have.
        "score_interpretation_note": (
            "All scores in this report are relative internal support indices. "
            "They are outcome-calibrated probabilities only when calibration.status "
            "is VALIDATED_CALIBRATED and a passing validation report is attached; "
            "otherwise they are engineered, provisional 0-100 indices and must not "
            "be read as aptitude probabilities."
        ),
        # GAP-FIX (audit -- stream/planet mapping provenance): Science/
        # Commerce/Humanities are modern (CBSE-era) educational categories --
        # no classical Jyotish text defines these three exact streams, so
        # the mapping from graha/house significations (STREAM_META in
        # subject_registry.py) to "which of these 3 modern categories" is
        # this engine's own INTERPRETIVE synthesis of classical significator
        # doctrine, not a documented classical rule set or a surveyed expert
        # consensus. This is a genuine, permanent epistemic limitation, not
        # a bug to be fixed -- stated here explicitly rather than left
        # implicit in code comments a report reader would never see.
        "mapping_provenance_note": (
            "The Science/Commerce/Humanities stream categories themselves are modern "
            "(CBSE-era) educational constructs with no single classical Jyotish "
            "definition. This engine's planet-to-stream signature mapping (which "
            "grahas 'belong' to which stream) is an interpretive synthesis of "
            "classical significator doctrine (e.g. Mercury=analysis/commerce, "
            "Jupiter=wisdom/law, Mars=technical rigor), not a mapping drawn from a "
            "single cited classical source or validated against expert-astrologer "
            "consensus. Several planets (Mercury, Jupiter, Mars, Saturn, Venus, Moon) "
            "legitimately support more than one stream at once in classical doctrine; "
            "this engine resolves that overlap NUMERICALLY (see "
            "_planet_exclusivity/'exclusivity' values throughout this report's traces), "
            "by discounting a shared planet's contribution in proportion to how many "
            "streams claim it -- not by an astrological priority rule that decides "
            "which single stream a shared planet 'really' belongs to for this specific "
            "chart. That numerical resolution is an engineering choice, not a "
            "classical technique."
        ),
        "disclaimer": UNIVERSAL_DISCLAIMER,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


# GAP-FIX (audit, 2026-07-23): str(None) renders as the literal word "None"
# in HTML -- fine in JSON (null is a real, meaningful value there: e.g.
# dominant_stream is null on purpose when Stream_Determination withholds a
# pick), but confusing to a parent/student reading the rendered report.
# Route any Optional value that reaches the HTML template through this
# instead of a bare str(...) call.
def _fmt_optional(value: Any, none_label: str = "not declared") -> str:
    return none_label if value is None else str(value)


_REPORT_CSS = r"""
/* ---- tokens ---- */
:root{
  --ink:#1c1a2b;
  --ink-soft:#4a4560;
  --muted:#847d8f;
  --paper:#faf6ee;
  --paper-raised:#ffffff;
  --paper-sunk:#f2ecdf;
  --line:#e6ddc9;
  --line-soft:#efe8d8;
  --accent:#a3742c;
  --accent-soft:#f1e4c8;
  --science:#1f6f68;
  --science-soft:#e3f1ee;
  --humanities:#834569;
  --humanities-soft:#f3e5ee;
  --commerce:#a3552e;
  --commerce-soft:#f6e6db;
  --good:#2f7a52;
  --good-soft:#e4f2e9;
  --warn:#a56b16;
  --warn-soft:#faedd4;
  --bad:#ad3a3a;
  --bad-soft:#fbe6e6;
  --shadow:0 1px 2px rgba(28,26,43,.04), 0 8px 24px -12px rgba(28,26,43,.16);
  --font-display:"Fraunces", Georgia, "Times New Roman", serif;
  --font-body:"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono:"IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ink:#ede7f0;
    --ink-soft:#c6bfd4;
    --muted:#948d9f;
    --paper:#171522;
    --paper-raised:#1f1d2e;
    --paper-sunk:#141220;
    --line:#332f46;
    --line-soft:#292640;
    --accent:#d3a556;
    --accent-soft:#3a3020;
    --science:#5cbcb2;
    --science-soft:#16302c;
    --humanities:#d792bb;
    --humanities-soft:#33202c;
    --commerce:#e0925c;
    --commerce-soft:#332318;
    --good:#5ec98c;
    --good-soft:#1a2f22;
    --warn:#e0ac4f;
    --warn-soft:#332510;
    --bad:#e2807f;
    --bad-soft:#331d1d;
    --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px -12px rgba(0,0,0,.5);
  }
}
:root[data-theme="dark"]{
  --ink:#ede7f0;
  --ink-soft:#c6bfd4;
  --muted:#948d9f;
  --paper:#171522;
  --paper-raised:#1f1d2e;
  --paper-sunk:#141220;
  --line:#332f46;
  --line-soft:#292640;
  --accent:#d3a556;
  --accent-soft:#3a3020;
  --science:#5cbcb2;
  --science-soft:#16302c;
  --humanities:#d792bb;
  --humanities-soft:#33202c;
  --commerce:#e0925c;
  --commerce-soft:#332318;
  --good:#5ec98c;
  --good-soft:#1a2f22;
  --warn:#e0ac4f;
  --warn-soft:#332510;
  --bad:#e2807f;
  --bad-soft:#331d1d;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px -12px rgba(0,0,0,.5);
}

*{box-sizing:border-box;}
html{background:var(--paper);}
body{
  margin:0; background:var(--paper); color:var(--ink); font-family:var(--font-body);
  -webkit-font-smoothing:antialiased; line-height:1.5;
}
::selection{background:var(--accent-soft); color:var(--ink);}
h1,h2,h3{font-family:var(--font-display); color:var(--ink); text-wrap:balance; margin:0;}
.num{font-family:var(--font-mono); font-variant-numeric:tabular-nums;}
a{color:inherit;}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px;}
@media (prefers-reduced-motion: reduce){ *{animation-duration:.001ms !important; transition-duration:.001ms !important;} }

.page{ max-width:1180px; margin:0 auto; padding:28px 20px 64px; display:flex; flex-direction:column; gap:22px; }

/* ---- hero ---- */
.hero{
  background:
    radial-gradient(720px 320px at 88% -10%, var(--accent-soft), transparent 60%),
    var(--paper-raised);
  border:1px solid var(--line); border-radius:18px; padding:34px 36px 30px;
  box-shadow:var(--shadow); position:relative; overflow:hidden;
}
.hero .eyebrow{
  font-family:var(--font-mono); font-size:.7rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--accent); font-weight:600;
}
.hero-top{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }
.theme-toggle{
  display:inline-flex; gap:2px; background:var(--paper-sunk); border:1px solid var(--line);
  border-radius:999px; padding:3px; flex-shrink:0;
}
.theme-toggle button{
  font-family:var(--font-body); font-size:.74rem; font-weight:600; padding:6px 13px; border-radius:999px;
  border:none; background:transparent; color:var(--muted); cursor:pointer; display:flex; align-items:center; gap:5px;
}
.theme-toggle button[aria-pressed="true"]{ background:var(--paper-raised); color:var(--ink); box-shadow:var(--shadow); }
.theme-toggle button:hover{ color:var(--ink); }
.theme-toggle svg{ width:13px; height:13px; }
.hero h1{ font-size:clamp(1.9rem,3.4vw,2.8rem); font-weight:600; margin-top:.3rem; }
.hero .sub{ color:var(--ink-soft); font-size:1rem; max-width:60ch; margin-top:.5rem; }
.hero-meta{ display:flex; flex-wrap:wrap; gap:8px 22px; margin-top:18px; font-size:.86rem; color:var(--muted); }
.hero-meta b{ color:var(--ink-soft); font-weight:600; }
.hero-pills{ display:flex; flex-wrap:wrap; gap:8px; margin-top:20px; }
.pill{
  display:inline-flex; align-items:center; gap:6px; padding:5px 12px; border-radius:999px;
  font-size:.78rem; font-weight:600; border:1px solid transparent;
}
.pill-good{ background:var(--good-soft); color:var(--good); border-color:color-mix(in srgb, var(--good) 35%, transparent); }
.pill-warn{ background:var(--warn-soft); color:var(--warn); border-color:color-mix(in srgb, var(--warn) 35%, transparent); }
.pill-neutral{ background:var(--paper-sunk); color:var(--ink-soft); border-color:var(--line); }
.pill-accent{ background:var(--accent-soft); color:var(--accent); }

/* ---- override banner ---- */
.banner-slot:empty{ display:none; }
.banner{
  border-radius:14px; padding:14px 18px; font-size:.92rem; display:flex; gap:12px; align-items:flex-start;
  border:1px solid; box-shadow:var(--shadow);
}
.banner-critical{ background:var(--bad-soft); border-color:color-mix(in srgb, var(--bad) 40%, transparent); color:var(--bad); }
.banner-critical b{ color:var(--bad); }
.banner .mark{ font-family:var(--font-mono); font-weight:700; font-size:1.05rem; line-height:1.2; }
.banner p{ margin:0; color:var(--ink-soft); }
.banner p b{ color:inherit; }

/* ---- scoreboard ---- */
.scoreboard{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }
.scard{
  background:var(--paper-raised); border:1px solid var(--line); border-radius:16px; padding:20px 22px;
  box-shadow:var(--shadow); position:relative;
}
.scard[data-stream="science"]{ border-top:3px solid var(--science); }
.scard[data-stream="humanities"]{ border-top:3px solid var(--humanities); }
.scard[data-stream="commerce"]{ border-top:3px solid var(--commerce); }
.scard-top{ display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
.scard-rank{ font-family:var(--font-mono); font-size:.72rem; color:var(--muted); letter-spacing:.06em; }
.scard h3{ font-size:1.28rem; font-weight:600; margin-top:2px; }
.scard .arch{ font-size:.8rem; color:var(--muted); font-weight:400; margin-left:.35em; }
.scard-badge{ font-size:.66rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; padding:3px 9px; border-radius:999px; white-space:nowrap; }
.scard-score{ display:flex; align-items:baseline; gap:6px; margin-top:14px; }
.scard-score .val{ font-family:var(--font-mono); font-size:2.1rem; font-weight:600; }
.scard-score .of{ font-size:.85rem; color:var(--muted); }
.sbar{ height:8px; border-radius:999px; background:var(--paper-sunk); overflow:hidden; margin-top:10px; }
.sbar > span{ display:block; height:100%; border-radius:999px; }
.scard[data-stream="science"] .sbar>span{ background:var(--science); }
.scard[data-stream="humanities"] .sbar>span{ background:var(--humanities); }
.scard[data-stream="commerce"] .sbar>span{ background:var(--commerce); }
.scard-dots{ display:flex; gap:5px; margin-top:16px; flex-wrap:wrap; }
.dot{ width:9px; height:9px; border-radius:50%; background:var(--line); }
.dot[data-hit="1"][data-stream="science"]{ background:var(--science); }
.dot[data-hit="1"][data-stream="humanities"]{ background:var(--humanities); }
.dot[data-hit="1"][data-stream="commerce"]{ background:var(--commerce); }
.scard-dots-label{ font-size:.68rem; color:var(--muted); margin-top:6px; }

/* ---- planet panel ---- */
.panel{ background:var(--paper-raised); border:1px solid var(--line); border-radius:16px; padding:24px 26px; box-shadow:var(--shadow); }
.panel h2{ font-size:1.3rem; font-weight:600; }
.panel .lede{ color:var(--muted); font-size:.88rem; max-width:70ch; margin-top:.35rem; }

/* ---- deep dive tabs ---- */
.deepdive-head{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
.deepdive-head h2{ font-size:1.3rem; font-weight:600; }
.tabs{ display:flex; gap:6px; background:var(--paper-sunk); padding:4px; border-radius:11px; }
.tab-btn{
  font-family:var(--font-body); font-size:.86rem; font-weight:600; padding:8px 16px; border-radius:8px;
  border:none; background:transparent; color:var(--muted); cursor:pointer;
}
.tab-btn[aria-selected="true"]{ background:var(--paper-raised); color:var(--ink); box-shadow:var(--shadow); }
.tab-btn:hover{ color:var(--ink); }

.dive{ background:var(--paper-raised); border:1px solid var(--line); border-radius:16px; padding:26px 28px; box-shadow:var(--shadow); }
.dive-head{ display:flex; justify-content:space-between; gap:20px; flex-wrap:wrap; align-items:flex-start; border-bottom:1px solid var(--line-soft); padding-bottom:18px; margin-bottom:20px; }
.dive-title h3{ font-size:1.5rem; font-weight:600; }
.dive-title .arch{ color:var(--muted); font-weight:400; font-size:1rem; margin-left:.4em; }
.dive-desc{ color:var(--ink-soft); font-size:.92rem; max-width:62ch; margin-top:.5rem; }
.dive-scorebox{ text-align:right; }
.dive-scorebox .n{ font-family:var(--font-mono); font-size:2.3rem; font-weight:600; }
.dive-scorebox .lbl{ font-size:.72rem; color:var(--muted); letter-spacing:.05em; text-transform:uppercase; }

.rubric-grid{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-bottom:22px; }
.rubric-item{ border:1px solid var(--line); border-radius:10px; padding:12px 14px; background:var(--paper-sunk); }
.rubric-item.penalty{ background:var(--bad-soft); border-color:color-mix(in srgb, var(--bad) 30%, transparent); }
.rubric-top{ display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
.rubric-name{ font-size:.83rem; font-weight:700; }
.rubric-num{ font-family:var(--font-mono); font-size:.83rem; color:var(--ink-soft); }
.rtrack{ height:6px; border-radius:999px; background:var(--line-soft); margin-top:8px; overflow:hidden; }
.rtrack>span{ display:block; height:100%; border-radius:999px; }
.rubric-item.penalty .rtrack>span{ background:var(--bad); }
details.rubric-note{ margin-top:8px; }
details.rubric-note summary{ font-size:.74rem; color:var(--accent); cursor:pointer; font-weight:600; list-style:none; }
details.rubric-note summary::-webkit-details-marker{ display:none; }
details.rubric-note summary::before{ content:"Why this number \25B8"; }
details.rubric-note[open] summary::before{ content:"Hide reasoning \25BE"; }
details.rubric-note p{ font-size:.8rem; color:var(--ink-soft); margin:.5rem 0 0; line-height:1.55; }

.signals{ display:flex; gap:16px; flex-wrap:wrap; font-size:.78rem; color:var(--muted); margin-bottom:20px; padding:10px 14px; background:var(--paper-sunk); border-radius:10px; }
.signals b{ color:var(--ink-soft); }
.sig-pos{ color:var(--good); font-weight:700; }
.sig-neu{ color:var(--muted); font-weight:700; }

table.subjects{ width:100%; border-collapse:collapse; font-size:.86rem; }
table.subjects th{ text-align:left; padding:9px 10px; font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); border-bottom:1px solid var(--line); font-weight:700; }
table.subjects td{ padding:11px 10px; border-bottom:1px solid var(--line-soft); vertical-align:top; }
table.subjects tr:last-child td{ border-bottom:none; }
.subj-name{ font-weight:600; }
.tag{ display:inline-block; font-size:.65rem; font-weight:700; padding:2px 7px; border-radius:5px; margin-left:6px; letter-spacing:.02em; vertical-align:1px; }
.tag-core{ background:var(--good-soft); color:var(--good); }
.tag-elective{ background:var(--paper-sunk); color:var(--muted); border:1px solid var(--line); }
.tag-contra{ background:var(--bad-soft); color:var(--bad); }
.subj-score{ font-family:var(--font-mono); font-weight:700; color:var(--ink); white-space:nowrap; }
.subj-rationale{ color:var(--ink-soft); font-size:.82rem; line-height:1.5; }
.subj-rationale .contra-text{ display:block; margin-top:4px; color:var(--bad); }

.yogas{ margin-top:22px; }
.yogas h4{ font-family:var(--font-body); font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-bottom:10px; }
.yoga-cards{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:10px; }
.yoga-card{ border:1px solid var(--line); border-radius:10px; padding:12px 14px; background:var(--paper-sunk); }
.yoga-card.dim{ opacity:.55; }
.yoga-top{ display:flex; justify-content:space-between; gap:8px; align-items:baseline; }
.yoga-name{ font-family:var(--font-display); font-weight:600; font-size:.98rem; }
.yoga-precision{ font-size:.64rem; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); font-family:var(--font-mono); }
.yoga-notes{ font-size:.8rem; color:var(--ink-soft); margin-top:5px; }
.yoga-cite{ font-size:.72rem; color:var(--muted); margin-top:6px; font-style:italic; }

/* ---- ledger ---- */
.ledger-table{ width:100%; border-collapse:collapse; font-size:.86rem; margin-top:16px; }
.ledger-table th{ text-align:left; padding:8px 10px; font-size:.68rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); border-bottom:1px solid var(--line); }
.ledger-table td{ padding:9px 10px; border-bottom:1px solid var(--line-soft); }
.ledger-table tr:last-child td{ border-bottom:none; }
.lstream{ font-weight:700; padding:2px 9px; border-radius:6px; font-size:.78rem; display:inline-block; }
.lstream.science{ background:var(--science-soft); color:var(--science); }
.lstream.humanities{ background:var(--humanities-soft); color:var(--humanities); }
.lstream.commerce{ background:var(--commerce-soft); color:var(--commerce); }
.ledger-flag{ font-size:.7rem; color:var(--warn); font-weight:600; }

/* ---- cross check ---- */
.cc-grid{ display:grid; grid-template-columns:1fr auto 1fr; gap:20px; align-items:center; margin-top:18px; }
.cc-side{ border:1px solid var(--line); border-radius:12px; padding:16px 18px; background:var(--paper-sunk); }
.cc-side h4{ font-size:.7rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-bottom:8px; }
.cc-side .big{ font-family:var(--font-display); font-size:1.25rem; font-weight:600; }
.cc-side .small{ font-size:.82rem; color:var(--ink-soft); margin-top:4px; }
.cc-mid{ display:flex; flex-direction:column; align-items:center; gap:6px; }
.cc-agree{ width:52px; height:52px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.4rem; }
.cc-agree.yes{ background:var(--good-soft); color:var(--good); }
.cc-agree.no{ background:var(--bad-soft); color:var(--bad); }
.cc-mid span{ font-size:.68rem; color:var(--muted); text-align:center; }
.cc-note{ font-size:.83rem; color:var(--muted); margin-top:16px; line-height:1.6; }

/* ---- narrative ---- */
.narrative{ background:var(--paper-raised); border:1px solid var(--line); border-radius:16px; padding:28px 30px; box-shadow:var(--shadow); }
.narrative-top{ display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:10px; margin-bottom:20px; }
.narrative-top .tag-locked{ font-family:var(--font-mono); font-size:.68rem; color:var(--muted); }
.narrative-cols{ display:grid; grid-template-columns:minmax(0,.95fr) minmax(0,1.15fr); gap:clamp(24px,4vw,52px); }
.narrative-cols.single-col{ grid-template-columns:1fr; max-width:640px; }
.narrative-cols h4{ font-family:var(--font-body); font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; color:var(--accent); font-weight:700; margin-bottom:10px; }
.narrative-cols p{ font-size:.95rem; color:var(--ink-soft); margin:0 0 .85rem; line-height:1.65; }
.narrative-cols p:last-child{ margin-bottom:0; }
@media (max-width:800px){ .narrative-cols{ grid-template-columns:1fr; } }


/* ---- foot ---- */
.foot{ text-align:center; color:var(--muted); font-size:.78rem; padding-top:10px; line-height:1.7; }
.foot b{ color:var(--ink-soft); }

@media (max-width:860px){
  .scoreboard{ grid-template-columns:1fr; }
  .rubric-grid{ grid-template-columns:1fr; }
  .cc-grid{ grid-template-columns:1fr; }
  .cc-mid{ flex-direction:row; justify-content:center; }
  table.subjects{ display:block; overflow-x:auto; white-space:nowrap; }
}
"""

_REPORT_JS = r"""
(function(){
  var D = JSON.parse(document.getElementById('report-data').textContent);
  var STREAM_LABEL = {science:'Science', humanities:'Humanities', commerce:'Commerce'};
  var SECTION_LABEL = {
    planetary_strength:'Planetary strength', house_support:'House support', role_placement:'Role placement',
    subject_evidence:'Subject evidence', d24_confirmation:'D24 confirmation', relational_d1:'Relational D1',
    jaimini_apparatus:'Jaimini apparatus', contraindications:'Contraindications'
  };
  var esc = function(s){ return String(s==null?'':s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var streamOrder = D.streams.slice().sort(function(a,b){ return b.score - a.score; });
  /* Audience switch: "parent" (vs. default "astrologer") hides every
     astrologer-technical section -- the rubric/yoga deep-dive, the
     disagreement ledger, and the astrological-reasoning narrative column --
     and keeps only the plain-language recommendation surfaces. */
  var isParentView = D.report_view === 'parent';

  /* ---------- theme toggle (light / dim / auto) ---------- */
  var THEME_KEY = 'jyotishai-stream-report-theme';
  function applyTheme(mode){
    var root = document.documentElement;
    if(mode === 'light'){ root.setAttribute('data-theme','light'); }
    else if(mode === 'dark'){ root.setAttribute('data-theme','dark'); }
    else { root.removeAttribute('data-theme'); }
    try{ localStorage.setItem(THEME_KEY, mode); }catch(e){}
    var buttons = document.querySelectorAll('.theme-toggle button');
    Array.prototype.forEach.call(buttons, function(b){
      b.setAttribute('aria-pressed', b.getAttribute('data-mode') === mode ? 'true' : 'false');
    });
  }
  var savedTheme = 'auto';
  try{ savedTheme = localStorage.getItem(THEME_KEY) || 'auto'; }catch(e){}
  applyTheme(savedTheme);
  var ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>';
  var ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/></svg>';
  var themeToggleHtml =
    '<div class="theme-toggle" role="group" aria-label="Theme">' +
      '<button type="button" data-mode="light" aria-pressed="false">' + ICON_SUN + ' Light</button>' +
      '<button type="button" data-mode="dark" aria-pressed="false">' + ICON_MOON + ' Dim</button>' +
    '</div>';

  /* ---------- hero ---------- */
  (function(){
    var el = document.getElementById('hero');
    el.innerHTML =
      '<div class="hero-top"><div class="eyebrow">JyotishAI &middot; Early-Age Stream Determination &middot; ' + esc(D.engine_version) + '</div>' + themeToggleHtml + '</div>' +
      '<h1>' + esc(D.name) + '&rsquo;s Stream Reading</h1>' +
      '<p class="sub">Evidence-weighted exploratory guidance across Science, Commerce and Humanities, built from D1 chart promise, D24 (Siddhamsha) education-chart confirmation, and Jaimini soul-apparatus, then explained subject by subject.</p>' +
      '<div class="hero-meta">' +
        '<span><b>Age</b> ' + D.current_age + '</span>' +
        '<span><b>DOB</b> ' + esc(D.dob) + '</span>' +
        '<span><b>Calculation profile</b> ' + esc(D.calculation_profile) + '</span>' +
        '<span><b>Evaluated</b> ' + esc(D.evaluation_as_of_date) + '</span>' +
      '</div>' +
      '<div class="hero-pills">' +
        '<span class="pill pill-good">' + esc(D.recommendation_status) + '</span>' +
        '<span class="pill pill-accent">Recommended: ' + esc(STREAM_LABEL[D.recommended_stream] || D.recommended_stream) + '</span>' +
        '<span class="pill pill-neutral">Evidence completeness ' + Math.round(D.evidence_completeness*100) + '%</span>' +
        '<span class="pill pill-neutral">Top-two gap ' + D.score_gap_top_two + ' pts</span>' +
        (D.is_close_call ? '<span class="pill pill-warn">Close call</span>' : '<span class="pill pill-neutral">Not a close call</span>') +
      '</div>' +
      (D.numeric_rank && D.recommended_stream && D.recommended_stream !== D.numeric_rank[0] ?
        '<p class="sub" style="margin-top:14px;color:var(--warn);font-weight:600;">&#9888; Recommended stream differs from the raw numeric leader (' +
          esc(STREAM_LABEL[D.numeric_rank[0]] || D.numeric_rank[0]) + '). ' + esc(D.recommendation_basis_note||'') + '</p>' : '');
    applyTheme(savedTheme);
    el.querySelector('.theme-toggle').addEventListener('click', function(e){
      var btn = e.target.closest('button[data-mode]');
      if(!btn) return;
      savedTheme = btn.getAttribute('data-mode');
      applyTheme(savedTheme);
    });
  })();

  /* ---------- override banner ---------- */
  (function(){
    var el = document.getElementById('banner-slot');
    if(!D.forced_override) return;
    el.innerHTML =
      '<div class="banner banner-critical">' +
        '<div class="mark">&#9888;</div>' +
        '<p><b>Forced test override active.</b> This chart is age ' + D.current_age + ' &mdash; outside this engine&rsquo;s normal under-15 scope. ' +
        'It is being shown only because <code class="num">force=True</code> was passed to the CLI. ' + esc(D.age_routing_note) + '</p>' +
      '</div>';
  })();

  /* ---------- scoreboard ---------- */
  (function(){
    var el = document.getElementById('scoreboard');
    var maxScore = Math.max.apply(null, D.streams.map(function(s){return s.score;}));
    var sectionsForDots = ['planetary_strength','house_support','role_placement','subject_evidence','d24_confirmation','relational_d1','jaimini_apparatus'];
    var leaders = (D.disagreement_ledger && D.disagreement_ledger.section_leading_stream) || {};
    el.innerHTML = streamOrder.map(function(s, i){
      var dots = sectionsForDots.map(function(sec){
        var leaderLabel = leaders[sec];
        var hit = leaderLabel === STREAM_LABEL[s.stream_id] ? '1' : '0';
        return '<span class="dot" data-stream="'+s.stream_id+'" data-hit="'+hit+'" title="'+SECTION_LABEL[sec]+': '+esc(leaderLabel||'n/a')+' leads"></span>';
      }).join('');
      return (
      '<article class="scard" data-stream="'+s.stream_id+'">' +
        '<div class="scard-top">' +
          '<div><div class="scard-rank">RANK '+(i+1)+'</div><h3>'+STREAM_LABEL[s.stream_id]+'<span class="arch">'+esc(s.sub_archetype)+'</span></h3></div>' +
          (s.stream_id === D.recommended_stream ? '<span class="scard-badge" style="background:var(--good-soft);color:var(--good)">Recommended</span>' : '') +
        '</div>' +
        '<div class="scard-score"><span class="val num">'+s.score.toFixed(1)+'</span><span class="of">/ 100</span></div>' +
        '<div class="sbar"><span style="width:'+((s.score/Math.max(maxScore,1))*100)+'%"></span></div>' +
        '<div class="scard-dots">'+dots+'</div>' +
        '<div class="scard-dots-label">Rubric sections where this stream leads on its own evidence</div>' +
      '</article>');
    }).join('');
  })();

  /* ---------- deep dive tabs ---------- */
  var SECTION_KEYS = ['planetary_strength','house_support','role_placement','subject_evidence','d24_confirmation','relational_d1','jaimini_apparatus','contraindications'];

  function renderDive(streamId){
    var s = D.streams.filter(function(x){return x.stream_id===streamId;})[0];
    var rubric = {};
    s.score_rubric.sections.forEach(function(sec){ rubric[sec.section] = sec; });

    var rubricHtml = SECTION_KEYS.map(function(key){
      var sec = rubric[key];
      if(!sec) return '';
      var isPenalty = sec.kind === 'penalty';
      var pct = isPenalty ? Math.min(100, (Math.abs(sec.actual)/sec.cap)*100) : Math.min(100, (sec.actual/sec.cap)*100);
      var barColor = isPenalty ? 'var(--bad)' : ('var(--'+streamId+')');
      return (
      '<div class="rubric-item'+(isPenalty?' penalty':'')+'">' +
        '<div class="rubric-top"><span class="rubric-name">'+SECTION_LABEL[key]+'</span>' +
        '<span class="rubric-num">'+(isPenalty?sec.actual:'+'+sec.actual)+' <span style="opacity:.6">(cap '+sec.cap+')</span></span></div>' +
        '<div class="rtrack"><span style="width:'+pct+'%;background:'+barColor+'"></span></div>' +
        '<details class="rubric-note"><p>'+esc(sec.note)+'</p></details>' +
      '</div>');
    }).join('');

    var signalsHtml =
      '<span><b>Role placement</b> ' + sigTag(s.role_placement_signal_state) + '</span>' +
      '<span><b>Relational D1</b> ' + sigTag(s.relational_d1_signal_state) + '</span>' +
      '<span><b>D24 confirmation</b> ' + sigTag(s.d24_confirmation_signal_state) + '</span>';

    var subjectsHtml = s.subjects.slice().sort(function(a,b){return b.score-a.score;}).map(function(sub){
      var contraNote = '';
      var ratMatch = /Contraindication:(.*)$/.exec(sub.rationale);
      var baseRationale = ratMatch ? sub.rationale.slice(0, ratMatch.index).trim() : sub.rationale;
      if(ratMatch){ contraNote = '<span class="contra-text">&#9888; Contraindication:'+esc(ratMatch[1])+'</span>'; }
      return (
      '<tr>' +
        '<td><span class="subj-name">'+esc(sub.label)+'</span>' +
          (sub.core ? '<span class="tag tag-core">Core</span>' : '<span class="tag tag-elective">'+(sub.shared_elective?'Elective &middot; shared':'Elective')+'</span>') +
          (sub.mandatory_contraindication ? '<span class="tag tag-contra">Capped</span>' : '') +
        '</td>' +
        '<td class="subj-score num">'+sub.score.toFixed(1)+'</td>' +
        '<td class="subj-rationale">'+esc(baseRationale)+contraNote+'</td>' +
      '</tr>');
    }).join('');

    var yogaList = (s.yoga_detection && s.yoga_detection.contributing_yogas) || [];
    var yogaHtml = yogaList.map(function(y){
      return (
      '<div class="yoga-card'+(y.relevant_to_this_stream?'':' dim')+'">' +
        '<div class="yoga-top"><span class="yoga-name">'+esc(y.yoga_name)+'</span><span class="yoga-precision">'+esc(y.precision)+'</span></div>' +
        '<div class="yoga-notes">'+esc(y.notes)+(y.relevant_to_this_stream?'':' <em>(not counted toward this stream)</em>')+'</div>' +
        '<div class="yoga-cite">'+esc(y.classical_citation)+'</div>' +
      '</div>');
    }).join('');

    return (
    '<div class="dive" data-stream="'+streamId+'">' +
      '<div class="dive-head">' +
        '<div class="dive-title"><h3>'+STREAM_LABEL[streamId]+'<span class="arch">'+esc(s.sub_archetype)+'</span></h3>' +
        '<p class="dive-desc">'+esc(s.description)+'</p></div>' +
        '<div class="dive-scorebox"><div class="n num">'+s.score.toFixed(1)+'</div><div class="lbl">of 100</div></div>' +
      '</div>' +
      '<div class="signals">'+signalsHtml+'</div>' +
      (s.rahu_ketu_caveat ? '<p class="cc-note" style="margin:-8px 0 18px;color:var(--warn);">&#9888; '+esc(s.rahu_ketu_caveat)+'</p>' : '') +
      '<div class="rubric-grid">'+rubricHtml+'</div>' +
      '<table class="subjects"><thead><tr><th>Subject</th><th>Score</th><th>Astrological rationale</th></tr></thead><tbody>'+subjectsHtml+'</tbody></table>' +
      (yogaHtml ? '<div class="yogas"><h4>Classical yogas detected in this chart</h4><div class="yoga-cards">'+yogaHtml+'</div></div>' : '') +
    '</div>');
  }
  function sigTag(state){
    if(state === 'POSITIVE_SUPPORT') return '<span class="sig-pos">Positive support</span>';
    if(state === 'NEUTRAL_NO_SIGNAL') return '<span class="sig-neu">No signal (not negative)</span>';
    return '<span class="sig-neu">'+esc(state)+'</span>';
  }

  (function(){
    var deepdiveEl = document.getElementById('deepdive');
    if(isParentView){ deepdiveEl.remove(); return; }
    var tabsEl = document.getElementById('tabs');
    var panelEl = document.getElementById('tabpanel');
    tabsEl.innerHTML = streamOrder.map(function(s,i){
      return '<button class="tab-btn" role="tab" aria-selected="'+(i===0?'true':'false')+'" data-stream="'+s.stream_id+'">'+STREAM_LABEL[s.stream_id]+'</button>';
    }).join('');
    function select(id){
      Array.prototype.forEach.call(tabsEl.querySelectorAll('.tab-btn'), function(b){
        b.setAttribute('aria-selected', b.getAttribute('data-stream')===id ? 'true':'false');
      });
      panelEl.innerHTML = renderDive(id);
    }
    tabsEl.addEventListener('click', function(e){
      var btn = e.target.closest('.tab-btn');
      if(btn) select(btn.getAttribute('data-stream'));
    });
    select(streamOrder[0].stream_id);
  })();

  /* ---------- disagreement ledger ---------- */
  (function(){
    var el = document.getElementById('ledgerpanel');
    var L = D.disagreement_ledger;
    if(isParentView || !L) { el.remove(); return; }
    var rows = Object.keys(L.section_leading_stream).map(function(k){
      var leader = L.section_leading_stream[k];
      var disagrees = (L.sections_disagreeing_with_final||[]).indexOf(k) !== -1;
      return (
      '<tr><td>'+(SECTION_LABEL[k]||k)+'</td>' +
      '<td><span class="lstream '+leader.toLowerCase()+'">'+esc(leader)+'</span></td>' +
      '<td>'+(disagrees ? '<span class="ledger-flag">&ne; final ('+esc(L.final_leading_stream)+')</span>' : '<span style="color:var(--good);font-size:.78rem;font-weight:600;">matches final</span>')+'</td></tr>');
    }).join('');
    el.innerHTML =
      '<div class="panel">' +
      '<h2>Which stream each evidence channel favors alone</h2>' +
      '<p class="lede">Every rubric section is combined to reach the final "'+esc(L.final_leading_stream)+'" recommendation. Read individually, three sections would have pointed elsewhere &mdash; that disagreement is normal and does not mean those sections are wrong, only that this one evidence channel alone favors a different stream.</p>' +
      '<table class="ledger-table"><thead><tr><th>Evidence channel</th><th>Leads toward</th><th>vs. final</th></tr></thead><tbody>'+rows+'</tbody></table>' +
      '</div>';
  })();

  /* ---------- cross-validation ---------- */
  (function(){
    var el = document.getElementById('crosscheck');
    var CV = D.cross_validation;
    if(!CV){ el.remove(); return; }
    el.innerHTML =
      '<div class="panel">' +
      '<h2>Cross-check against the adult Field Determination engine</h2>' +
      '<p class="lede">An independent supplementary check: this reverse-derives which stream '+esc(D.name)+'&rsquo;s own highest-confidence adult career field implies, and compares it to this report&rsquo;s result. It never overrides or merges into the stream score above.</p>' +
      '<div class="cc-grid">' +
        '<div class="cc-side"><h4>Field Determination (adult engine)</h4>' +
          '<div class="big">'+esc(CV.field_determination_top_cluster_field_label)+'</div>' +
          '<div class="small">Score '+CV.field_determination_top_cluster_field_score+' &middot; '+esc(CV.field_determination_top_cluster_confidence_band)+' confidence &middot; rank #'+CV.field_determination_top_cluster_rank+'<br>'+esc(CV.field_determination_macro_career_family)+' / '+esc(CV.field_determination_macro_competency)+'<br>implies stream: <b>'+esc(STREAM_LABEL[CV.domain_implied_stream])+'</b></div>' +
        '</div>' +
        '<div class="cc-mid">' +
          '<div class="cc-agree '+(CV.agree?'yes':'no')+'">'+(CV.agree?'&#10003;':'&#10005;')+'</div>' +
          '<span>Overall agreement</span>' +
        '</div>' +
        '<div class="cc-side"><h4>Stream Determination (this engine)</h4>' +
          '<div class="big">'+esc(STREAM_LABEL[CV.stream_determination_recommended_stream])+'</div>' +
          '<div class="small">Numeric leader: '+esc(STREAM_LABEL[CV.stream_determination_top_ranked_stream])+' &middot; status '+esc(CV.stream_determination_recommendation_status)+'<br>vs. numeric leader: <b style="color:'+(CV.adult_vs_numeric_agreement?'var(--good)':'var(--bad)')+'">'+(CV.adult_vs_numeric_agreement?'AGREE':'DISAGREE')+'</b><br>vs. actual recommendation: <b style="color:'+(CV.adult_vs_recommended_agreement?'var(--good)':'var(--bad)')+'">'+(CV.adult_vs_recommended_agreement?'AGREE':'DISAGREE')+'</b></div>' +
        '</div>' +
      '</div>' +
      '<p class="cc-note">'+esc(CV.note)+'</p>' +
      '</div>';
  })();

  /* ---------- narrative ---------- */
  (function(){
    var el = document.getElementById('narrative');
    var N = D.stream_narrative;
    if(!N){ el.remove(); return; }
    function toParas(node){
      var paras = [];
      if(Array.isArray(node)) paras = node;
      else if(node && Array.isArray(node.paragraphs)) paras = node.paragraphs;
      else if(typeof node === 'string') paras = node.split(/\n+/);
      return paras.filter(Boolean).map(function(p){return '<p>'+esc(p)+'</p>';}).join('');
    }
    var isLLM = N.provider === 'openai';
    var studentHeading = isLLM ? 'A note for you, about ' + esc(D.name) : 'What this means for ' + esc(D.name);
    var studentCol = '<div><h4>'+studentHeading+'</h4>'+toParas(N.student_narrative)+'</div>';
    /* Parent view never renders the "Astrological reasoning" column at all
       (not merely relabeled) -- the whole narrative section becomes a
       single, full-width plain-language column. */
    var astroCol = isParentView ? '' : '<div><h4>Astrological reasoning</h4>'+toParas(N.astrological_narrative)+'</div>';
    el.innerHTML =
      '<div class="narrative-top"><h2>Reading this chart</h2>' +
      '<span class="tag-locked">status: '+esc(N.status)+' &middot; provider: '+esc(N.provider)+' &middot; decision locked: '+(N.decision_locked?'true':'false')+'</span></div>' +
      '<div class="narrative-cols'+(isParentView?' single-col':'')+'">' +
        studentCol + astroCol +
      '</div>' +
      '<p class="cc-note" style="margin-top:18px;">The narrative explains the deterministic result and cannot change scores, ranking, dominant stream or tie status.</p>';
  })();

  /* ---------- field-derived evidence (experimental, optional) ---------- */
  (function(){
    var el = document.getElementById('fieldderived');
    var fde = D.field_determination_evidence;
    if(!fde){ el.remove(); return; }
    if(fde.data_status !== 'COMPUTED'){
      el.innerHTML = '<div class="panel"><h2>Experimental: Field Determination&ndash;derived stream evidence</h2>' +
        '<p class="lede">Not available for this chart (' + esc(fde.data_status) + '): ' + esc((fde.warnings||[]).join('; ') || 'no data') + '</p></div>';
      return;
    }
    var marks = fde.marks || {}, adjusted = fde.adjusted_distribution || {}, raw = fde.raw_distribution || {};
    var rows = ['science','commerce','humanities'].map(function(k){
      return '<tr><td><span class="lstream '+k+'">'+STREAM_LABEL[k]+'</span></td>' +
        '<td class="num">'+(marks[k]||0).toFixed(2)+'</td>' +
        '<td class="num">'+Math.round((adjusted[k]||0)*100)+'% <span style="color:var(--muted)">(raw '+Math.round((raw[k]||0)*100)+'%)</span></td></tr>';
    }).join('');
    el.innerHTML = '<div class="panel"><h2>Experimental: Field Determination&ndash;derived stream evidence</h2>' +
      '<p class="lede">A small, capped extra rubric section (already folded into each stream&rsquo;s score above) derived by re-reading this same chart through the adult vocational-branch engine. Not an independent method &mdash; reuses the same D1/D24/Jaimini facts through a different lens.</p>' +
      '<table class="ledger-table"><thead><tr><th>Stream</th><th>Marks earned</th><th>Adjusted share</th></tr></thead><tbody>'+rows+'</tbody></table>' +
      '<p class="cc-note">usable fields: '+(fde.usable_field_count||0)+' &middot; families: '+(fde.family_count||0)+' (mapped '+(fde.mapped_field_count||fde.mapped_family_count||0)+') &middot; mapping coverage '+Math.round((fde.mapping_coverage||0)*100)+'% &middot; reliability '+((fde.reliability||0).toFixed ? fde.reliability.toFixed(2) : fde.reliability)+'</p>' +
      '<p class="cc-note" style="margin-top:10px;">'+esc(fde.note||'')+'</p></div>';
  })();

  /* ---------- footer ---------- */
  (function(){
    document.getElementById('foot').innerHTML =
      '<p><b>'+esc(D.disclaimer)+'</b></p>' +
      '<p>Generated '+esc(D.generated_at)+' &middot; report contract '+esc(D.contract_version)+'</p>';
  })();
})();
"""

_REPORT_HTML_SHELL = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
__CSS__
</style>
</head>
<body>
<div class="page">
  <header class="hero" id="hero"></header>
  <section class="banner-slot" id="banner-slot"></section>
  <section class="scoreboard" id="scoreboard"></section>
  <section class="narrative" id="narrative"></section>
  <section class="deepdive" id="deepdive">
    <div class="deepdive-head">
      <h2>Stream deep-dive</h2>
      <div class="tabs" id="tabs"></div>
    </div>
    <div id="tabpanel"></div>
  </section>
  <section class="ledgerpanel" id="ledgerpanel"></section>
  <section class="crosscheck" id="crosscheck"></section>
  <section class="crosscheck" id="fieldderived"></section>
  <footer class="foot" id="foot"></footer>
</div>

<script type="application/json" id="report-data">
__DATA__
</script>
<script>
__JS__
</script>
</body>
</html>


"""


def render_report_html(report: Dict[str, Any]) -> str:
    """Render the full standalone HTML report for a single chart.

    2026-09 redesign: renders client-side from an embedded JSON blob of the
    same `report` payload (identical to the sibling .json file) instead of
    hand-built server-side HTML strings -- this keeps the HTML and JSON
    reports in permanent lockstep (no risk of one surfacing a field the
    other silently drops) and surfaces sections the old template computed
    but never rendered: per-planet strength chart, per-stream rubric-section
    bars with their reasoning notes, classical yoga cards for every stream
    (not just whichever the narrative happened to mention), the
    disagreement ledger, the Rahu/Ketu weighting caveat, and the
    D1-vs-D24/Jaimini weight split. See stream_records/*.html for output.
    """
    name = report.get("name", "Unknown")
    title = f"Early-Age Stream & Subject Report \u2014 {name}"
    data_json = json.dumps(report, ensure_ascii=False, default=str).replace("</", "<\\/")
    return (
        _REPORT_HTML_SHELL
        .replace("__TITLE__", html.escape(title))
        .replace("__CSS__", _REPORT_CSS)
        .replace("__JS__", _REPORT_JS)
        .replace("__DATA__", data_json)
    )


def write_reports(
    payload: Any, determination: Dict[str, Any], out_dir: str, *,
    forced_override: bool = False, eligibility_status: str = "NORMAL",
    cross_validation: Dict[str, Any] | None = None,
    stream_narrative: Dict[str, Any] | None = None,
    report_view: str = "astrologer",
) -> Dict[str, str]:
    """Write both JSON and HTML reports; returns {"json": path, "html": path}."""
    os.makedirs(out_dir, exist_ok=True)
    stem = (getattr(payload, "name", "") or "Unknown").replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = build_report_payload(
        payload, determination,
        forced_override=forced_override, eligibility_status=eligibility_status,
        cross_validation=cross_validation,
        stream_narrative=stream_narrative,
        report_view=report_view,
    )

    json_path = os.path.join(out_dir, f"stream_report_{stem}_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    html_path = os.path.join(out_dir, f"stream_report_{stem}_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_report_html(report))

    return {"json": json_path, "html": html_path}
