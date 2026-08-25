"""Split the Field Determination engine's per-field debug payload into
smaller, purpose-specific JSON files instead of one monolithic blob.

Why: profiling a real chart run showed the combined debug JSON for ~35
candidate fields runs 3-5MB, almost entirely from per-field audit/provenance
trails (method_log, calc_trace, evidence_ledger_v2, ...) that most consumers
(a UI, the HTML report, an LLM prompt) never read. Splitting by purpose lets
each consumer load only what it actually needs, and keeps the always-loaded
file small.

Three output files, each a list of per-field records keyed by `field_id`
(+`rank`) so they can be re-joined if needed:

- ``<stem>_summary.json``   Small. Ranked scores, labels, career/market info,
                            disclaimers -- everything a UI, report, or LLM
                            prompt needs to *display or reason about* results.
- ``<stem>_reference.json`` Medium. Registry/ontology/catalog data backing
                            each field (course registry, confirmations,
                            geo/institutional data). Larger but fairly
                            stable/cacheable across runs.
- ``<stem>_audit.json``     Large. Full calculation/evidence/provenance
                            trail. Only needed for defensibility audits or
                            debugging, not normal consumption.

``registry_legacy`` is dropped entirely: verified byte-identical to
``registry`` on every field in real output, so it's pure duplication.

Any key not explicitly classified falls into the audit file (safe default --
new debug fields stay visible for audits rather than silently disappearing).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

# Small, high-value fields a UI/report/LLM prompt needs to show or reason
# about a ranked field candidate.
SUMMARY_KEYS = {
    "field_id", "rank", "field_label", "field_role", "domain",
    "career_family", "career_family_label", "competency", "competency_label",
    "final_score", "composite_score", "astrological_score",
    "publication_score", "affinity_score", "blended_score",
    "weighted_method_score", "pre_norm_score", "raw_combined_score",
    "method_total_score", "knrao_score", "jaimini_score", "kp_score",
    "dashamsha_score", "parashara_score", "gap_penalty", "gap_boost",
    "boost_pct", "confidence_band", "score_confidence",
    "score_confidence_note", "hard_lockout", "llm_enrichment_used",
    "career_outcomes", "market", "curriculum", "disclaimer", "top_karakas",
    "admission_exams_canonical", "score_semantics", "norm_note",
    "graph_note", "parent_friendly_explanation", "astrological_reason",
    "sudarshana_score", "family_cohesion_adjustment_pct",
    # Bug fix (2026-08 gap-audit round 2, "fix as per sequence" item 3):
    # siddhamsha_score/shashtiamsha_score (D24/D60 method scores) were added
    # to engine.py's published row dicts alongside the other six
    # *_score keys (knrao_score, kp_score, jaimini_score, dashamsha_score,
    # parashara_score, sudarshana_score -- all already in SUMMARY_KEYS above),
    # but were never added here, so split_debug_payload() silently dropped
    # them into the audit-only file instead of the summary file every
    # consumer (UI/report/LLM prompt) actually reads. Confirmed missing from
    # redacted_engine_summary.json on a live Midhula-chart run (2026-08-14)
    # before this fix.
    "siddhamsha_score", "shashtiamsha_score",
    # Stage 1 (Astro-OS v3 gap-audit implementation plan, 2026-08):
    # structural_patterns_score (D1 house-occupancy clustering, 9th voting
    # method) -- same class of always-relevant *_score key as the seven
    # above; classified here up front, same as confidence_dimensions below.
    "structural_patterns_score",
    # Stage 4 (Astro-OS v3 gap-audit implementation plan, 2026-08):
    # multi-dimensional confidence decomposition (structural/educational/
    # professional/research/leadership/timing fit) -- exactly the kind of
    # small, high-value, always-relevant field a UI/report/LLM prompt needs,
    # per this file's own SUMMARY_KEYS criteria. Classified here up front
    # rather than left to fall into the audit-only file, unlike
    # siddhamsha_score/shashtiamsha_score above which had to be fixed after
    # the fact.
    "confidence_dimensions",
    # Stage 3 (Astro-OS v3 gap-audit implementation plan, 2026-08): career
    # archetype discovery -- chart-level, additive-only descriptive output,
    # same class of always-relevant field as confidence_dimensions above.
    "career_archetype",
    # Fix A (2026-08 gap-audit, "fix all identified gaps" round): these are
    # already-computed, already-legitimate ranking-adjacent diagnostics
    # (ranking_policy.annotate_rank_differentiation / defensibility.py) that
    # were being written into the row but classified nowhere here, so they
    # silently fell into the audit-only file and never reached the
    # report/summary layer any UI/LLM-prompt consumer reads. score_ceiling_tie
    # and low_rank_differentiation flag exactly the "convincing-looking but
    # statistically undifferentiated" rank clusters found on both the Akash
    # and Ramsunder audits (e.g. computational_finance/econometrics tied at
    # the 100.00 ceiling); publication_ranking_adjustments is the bounded,
    # auditable adjustment trail apply_publication_ranking_policy() already
    # produces; the defensibility_summary subset surfaces tier/specificity
    # without touching ranking (ranking_effect stays NONE -- see
    # jyotish/defensibility.py docstring; this is transparency only). The
    # row key produced by release_candidate.py is "defensibility" (full
    # dict: tier/specificity_score/independent_supported_groups/
    # advisory_codes/ranking_effect) -- classified here as-is rather than
    # inventing a new key, since evaluate_defensibility() already keeps it
    # small and self-describing.
    "score_ceiling_tie", "low_rank_differentiation",
    "publication_ranking_adjustments", "defensibility",
    # Gap fix (2026-08-18, tiered-ranking audit): jyotish/tiered_ranking.py
    # attaches these on every published row (tier1/2/3_score = the 3-tier
    # classical-authority sub-scores that now decide field ranking;
    # tier_decision_trace = human-readable "why this field landed here";
    # final_score_legacy_blend = the retired flat-9-method-blend score, for
    # audit/comparison). Confirmed missing from redacted_engine_summary.json
    # and the HTML report on a live Ramsunder run (2026-08-18) -- same
    # silent-drop failure mode as the siddhamsha_score/shashtiamsha_score
    # gap above, and the earlier "LS12 fix" method_normalized_scores rename
    # this session: a new field gets added to the row dict, but not to this
    # allow-list, so it never reaches a report/UI/LLM-prompt consumer even
    # though the code that renders it (career_field_report_v2.py's
    # enriched_top20_payload() and its tier-trace method-card note) was
    # already fixed to read it.
    "tier1_score", "tier2_score", "tier3_score", "tier_decision_trace",
    "final_score_legacy_blend", "tier1_leakage_discounted",
    # Gap fix (2026-08-18, "Best UG Route" astrological-alignment review):
    # career_field_report_v2.py::_select_headline_routes() reads
    # row["method_breakdown"]["siddhamsha"]["normalized_score"] to check
    # whether D24/Siddhamsha independently favors a different field for PG
    # than the locked UG pick (pg_divergence_alert). That read happens on
    # `results` AFTER slim_for_render() has already run (see
    # career_field_report_v2.py's build flow), and method_breakdown was not
    # on this allow-list -- same silent-drop failure mode as every other
    # entry in this list's history. Confirmed live: pg_divergence_alert never
    # fired on a real report (Akash Shanmugham, 2026-08-18) because
    # _d24_support() always read an empty dict and returned 0.0 for every
    # candidate, not because no real divergence existed. method_breakdown is
    # per-method {raw_score, normalized_score, weight, ...} for all 10
    # field-determination tiers -- small (10 short dicts), not the bulky
    # audit trail (method_log/calc_trace/evidence_ledger_v2) this file's
    # slimming step exists to drop.
    "method_breakdown",
}

# Registry/ontology/catalog reference data backing a field.
REFERENCE_KEYS = {
    "registry_v12", "registry", "ontology_v12", "available_at_normalized",
    "sub_branch_compatibility", "graph_cluster", "graph_family_memberships",
    "institutional_tier", "routes", "academic_path", "geo_suitability",
    "siddhamsha_education", "shashtiamsha_confirmation",
    "navamsha_confirmation", "d10_verification", "affinity_planets",
    "micro_niches", "exact_field_contract", "graph_broadness_penalty",
    # Bug fix (2026-08 gap-audit round 2, item 2 follow-through): these two
    # confirmation/timing objects are the same class of content as
    # navamsha_confirmation/siddhamsha_education just above (per-field
    # corroboration detail a reference/audit consumer wants), but were never
    # classified here, so -- once engine.py's row-builder allow-list gap for
    # them is also fixed -- they would still have fallen through to the
    # audit-only file instead of *_reference.json.
    "d9_navamsha_confirmation", "jaimini_chara_dasha_timing",
}

# Small identifier/aliasing keys some downstream code (SBC, suitability,
# id-resolution helpers) looks up directly. Not scored/audit content, just
# routing keys -- always safe and cheap to keep.
EXTRA_ALLOW_KEYS = {"is_afflicted", "net_contraindication_index", "branch_id", "id", "key"}

# Exact-duplicate keys dropped outright.
DROP_KEYS = {"registry_legacy"}

# Everything a UI/report/LLM prompt or the HTML renderer's own consumers
# (career_field_report_v2.py, sbc.py, field_suitability.py) actually touch.
# Verified by grepping every `row.get(...)`/`r.get(...)` call across those
# three modules -- nothing in that call graph reads an audit-only key.
RENDER_KEYS = SUMMARY_KEYS | REFERENCE_KEYS | EXTRA_ALLOW_KEYS


def _split_record(record: Dict[str, Any]) -> tuple[dict, dict, dict]:
    summary, reference, audit = {}, {}, {}
    for k, v in record.items():
        if k in DROP_KEYS:
            continue
        if k in SUMMARY_KEYS:
            summary[k] = v
        elif k in REFERENCE_KEYS:
            reference[k] = v
        else:
            audit[k] = v
    return summary, reference, audit


def slim_for_render(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip audit-only keys from engine rows before they enter the HTML
    report pipeline (SBC layer, suitability annotation, LLM prompt builder,
    render_report_html*).

    Keeps only RENDER_KEYS (= SUMMARY_KEYS | REFERENCE_KEYS |
    EXTRA_ALLOW_KEYS). Everything downstream in career_field_report_v2.py /
    sbc.py / field_suitability.py only ever reads keys in that set -- this
    was verified by grepping every `.get(...)` call across those modules,
    not assumed. Report/SBC code that runs *after* this point (registry_v12
    injection, sbc_manifestation, recommendation_assessment, engine_field/
    engine_rank) adds its own keys back onto each row, so nothing needed
    later is dropped here -- only the never-read audit trail is.
    """
    return [
        {k: v for k, v in record.items() if k in RENDER_KEYS}
        for record in results
    ]


def split_debug_payload(
    results: List[Dict[str, Any]], out_dir: str, stem: str
) -> Dict[str, str]:
    """Write summary/reference/audit JSON files for `results`.

    Returns {label: path} for the files written, in size order (smallest
    first) so callers can print a friendly summary.
    """
    summaries, references, audits = [], [], []
    for record in results:
        s, r, a = _split_record(record)
        summaries.append(s)
        references.append(r)
        audits.append(a)

    paths = {}
    for label, data, suffix in (
        ("Summary", summaries, "summary"),
        ("Reference", references, "reference"),
        ("Audit", audits, "audit"),
    ):
        path = os.path.join(out_dir, f"{stem}_{suffix}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        paths[label] = path
    return paths
