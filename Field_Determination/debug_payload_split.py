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
}

# Registry/ontology/catalog reference data backing a field.
REFERENCE_KEYS = {
    "registry_v12", "registry", "ontology_v12", "available_at_normalized",
    "sub_branch_compatibility", "graph_cluster", "graph_family_memberships",
    "institutional_tier", "routes", "academic_path", "geo_suitability",
    "siddhamsha_education", "shashtiamsha_confirmation",
    "navamsha_confirmation", "d10_verification", "affinity_planets",
    "micro_niches", "exact_field_contract", "graph_broadness_penalty",
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
