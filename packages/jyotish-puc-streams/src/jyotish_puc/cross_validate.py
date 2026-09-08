"""Cross-validation: reverse-derive which CBSE stream a chart's own
Field_Determination top-most macro career cluster implies, and compare that
against Stream_Determination's own dominant_stream call for the same chart.

This is NOT a replacement for Stream_Determination's own scoring, and it is
NOT part of the under-15 report pipeline -- it is a separate, standalone
validation tool, meant to be run by a developer/auditor against known adult
charts (>=15, ideally charts whose real-world stream choice is already
known) to sanity-check whether the two independently-built engines land on
compatible directions. It reuses Field_Determination's own existing "macro
career identity" (competency_ontology.py::build_cluster_report --
career_cluster_report["macro_identity"]/["clusters"]) rather than re-deriving
any new clustering logic -- the top member of that report's #1 cluster IS
the "top-most macro cluster" this module reads.

GAP this closes: nothing in the codebase previously cross-checked
Stream_Determination's under-15 output against Field_Determination's own,
independently-computed, much more heavily-audited adult engine. The two
engines share almost no code (by design -- see stream_scoring.py's own
module docstring) and could in principle drift toward incompatible
directions for the same chart without anything ever comparing them.

LLM determinism note: Field_Determination's run_engine() accepts an
enable_llm flag; even with enable_llm=False passed explicitly, LLM
enrichment is additionally gated by payload.external_llm_consent (see
jyotish/engine.py::run_engine -- llm_authorized requires BOTH). For this
validator to be reproducible run-to-run on the same chart, that consent
flag is forced to False for the duration of the call and then restored to
whatever it was set to beforehand -- so running this validator has no
lasting side effect on the payload object for any other caller that
touches it afterward.
"""
from __future__ import annotations

from typing import Any, Dict, List

# GAP-FIX (audit -- "two parallel ontologies for the same domain->stream
# question"): this used to be a SECOND, hand-maintained dict, independent of
# field_stream_mapping.py's DOMAIN_STREAM_AFFINITY (used by
# field_derived_stream.py's score-affecting section) -- same underlying
# question (which CBSE stream does an adult vocational domain most commonly
# require), two separately-edited answers that could silently drift apart
# (e.g. someone tweaking one file's "law" weighting without knowing the
# other file makes the same real-world claim). Now DERIVED from that single
# fractional source of truth (highest-affinity stream per domain) instead of
# maintained by hand a second time. domain->stream is still a many-to-one
# simplification of a much richer real-world admissions picture (e.g. "law"
# can realistically be reached via Commerce too, not only Humanities) -- see
# field_stream_mapping.py's own module docstring for the full rationale.
# "interdisciplinary" has no entry in DOMAIN_STREAM_AFFINITY at all
# (deliberately left unmapped there), so it falls through to AMBIGUOUS here.
def _build_domain_to_stream() -> Dict[str, str]:
    from .field_stream_mapping import DOMAIN_STREAM_AFFINITY
    result: Dict[str, str] = {}
    for domain, affinity in DOMAIN_STREAM_AFFINITY.items():
        result[domain] = max(affinity, key=affinity.get)
    # "interdisciplinary" has no entry in DOMAIN_STREAM_AFFINITY (deliberately
    # unmapped there too) -- label it AMBIGUOUS explicitly rather than
    # letting the later .get(domain, "UNKNOWN") fallback report it as
    # "UNKNOWN". Both strings are treated identically by this module's own
    # agree logic (`implied_stream not in ("UNKNOWN", "AMBIGUOUS")`), but the
    # label itself matters to a human reading the report: AMBIGUOUS says
    # "we know this domain genuinely spans multiple streams," UNKNOWN says
    # "we have no idea," and those are different, useful pieces of information.
    result["interdisciplinary"] = "AMBIGUOUS"
    return result


# 2026-08-22 audit fix (gap 9): DISCLOSURE -- DOMAIN_TO_STREAM (derived
# above) and its source, field_stream_mapping.py's DOMAIN_STREAM_AFFINITY,
# are this codebase's own ENGINEERED ESTIMATES of real-world domain-to-
# stream affinity -- not derived from classical Jyotish texts and not from
# an official CBSE table or published statistic. See field_stream_mapping.py's
# own module-level disclosure note for the full explanation.
DOMAIN_TO_STREAM: Dict[str, str] = _build_domain_to_stream()


def _course_registry_domain(field_id: str) -> str:
    """GAP-FIX (caught testing this module against Lakshman): the raw JSON
    file (jyotish/india_course_registry_v12.json) nests branches under a
    top-level "branches" key, but jyotish.engine._load_course_registry()
    already returns that inner dict UNWRAPPED (flat {field_id: {...}, ...}) --
    confirmed live: reg.get('branches', {}) silently returned {} for every
    field_id, so every domain lookup came back empty and every
    domain_implied_stream fell through to UNKNOWN. Fixed to index the
    loader's return value directly."""
    if not field_id:
        return ""
    from jyotish.engine import _load_course_registry
    registry = _load_course_registry()
    entry = registry.get(field_id, {}) or {}
    return entry.get("domain", "")


def cross_validate_against_field_determination(
    payload: Any, *, snapshot: "FieldEngineSnapshot | None" = None,
    precomputed_determination: Dict[str, Any] | None = None,
    include_field_derived_evidence: bool = False,
    d24_arbitration_enabled: bool = False,
    classical_precedence_chain_enabled: bool = True,
) -> Dict[str, Any]:
    """Run Field_Determination's adult engine on this SAME payload, pull its
    own top-most macro career cluster, map that cluster's field back to the
    CBSE stream its domain most commonly requires, and compare that against
    Stream_Determination's own dominant_stream call for the same chart.

    Returns a comparison dict; does not mutate payload's own scoring state
    (career_cluster_report/dominant_stream are read from fresh calls, not
    cached attributes) and restores payload.external_llm_consent to its
    original value before returning -- see module docstring's LLM
    determinism note.

    OPTIMIZATION: pass `snapshot=` an already-fetched FieldEngineSnapshot
    (e.g. one early_age_stream_engine.py already fetched for
    field_derived_stream.py in the same CLI run) to avoid running the adult
    engine a second time for the same chart. If omitted, fetches its own.

    BUG FIX (2026-07-24, config-drift): this module used to ALWAYS call
    compute_stream_determination(payload) with no config kwargs, silently
    defaulting include_field_derived_evidence=False even when the caller's
    own main report was computed with include_field_derived_evidence=True
    (early_age_stream_engine.py's default via run_for_payload). That meant
    this cross-check's stream_determination_*/agree fields could describe a
    DIFFERENT determination state than the one actually shown to the user in
    the same report -- confirmed to flip recommended_stream for 3 charts
    (Ajay Agarwal, Sai Havish, Ajay Siddarth). Fix: pass
    `precomputed_determination=` the SAME determination dict the caller
    already computed (early_age_stream_engine.py's run_for_payload does
    this) so this module never triggers a second, differently-configured
    recompute. Only the standalone/CLI path below (no caller-supplied
    determination) still recomputes -- and now does so with its config
    (include_field_derived_evidence / d24_arbitration_enabled /
    classical_precedence_chain_enabled) passed explicitly instead of
    silently defaulted, so anyone using this module standalone can see and
    control exactly which config was used.
    """
    from .stream_scoring import compute_stream_determination
    # GAP-FIX (shared-runner consolidation, per review point 4): this used to
    # call jyotish.engine.run_engine() directly with its own inline LLM
    # force-off/restore logic -- now delegates to adult_engine_bridge.py so
    # this comparison and field_derived_stream.py's score-affecting section
    # can never silently drift onto different adult-engine invocation
    # configurations (deep-copy behavior, LLM suppression, field extraction).
    from .adult_engine_bridge import FieldEngineSnapshot, get_field_engine_snapshot

    snapshot = snapshot if snapshot is not None else get_field_engine_snapshot(payload)
    # GAP-FIX (shared-snapshot error-transparency): a caller-supplied
    # snapshot may have come from safe_get_field_engine_snapshot() (which
    # never raises, only records warnings) -- surface that as a real
    # failure here rather than silently proceeding with an empty
    # clusters/fields snapshot, which would otherwise produce a "successful"
    # comparison full of None/UNKNOWN fields instead of safe_cross_validate's
    # proper error contract.
    if snapshot.warnings:
        raise RuntimeError(f"adult engine snapshot unavailable: {'; '.join(snapshot.warnings)}")
    cluster_report = snapshot.career_cluster_report or {}
    macro_identity = cluster_report.get("macro_identity") or {}
    clusters = cluster_report.get("clusters", [])

    # GAP-FIX (caught testing this module against Lakshman): field_id and
    # field_label used to come from TWO DIFFERENT rankings -- field_id from
    # clusters[0] (ranked by raw family_score), field_label from
    # macro_identity.anchor_field (ranked by a top-20 rank+score-weighted
    # distribution -- a DIFFERENT ranking, per competency_ontology.py's own
    # build_cluster_report docstring/comments, which explicitly documents
    # these two can disagree and had to be reconciled internally there for
    # exactly this reason). Mixing them here reintroduced the same
    # "contradictory macro identity" bug that codebase's own audit already
    # fixed once -- confirmed live: field_id "research_academia" (from
    # clusters[0]) paired with label "Computational Social Science" (from
    # macro_identity, a different field entirely). Now both id and label
    # come from the SAME source (a single cluster's own member list) for
    # internal consistency; macro_identity's own (possibly different)
    # anchor field is reported separately and labelled as such, never
    # blended with the chosen member's field id.
    #
    # SELECTION RULE (per explicit request: "select the macrocluster which
    # has the highest confidence even if its not the top 1st field"):
    # clusters[0] is ranked by aggregate family_score (a whole-family sum),
    # not by any single member's own confidence. A field in cluster_rank 2
    # or 3 can individually be a stronger, higher-confidence signal
    # (higher final_score / confidence_band) than clusters[0]'s own top
    # member even though its family's aggregate is lower. So instead of
    # always reading clusters[0]["members"][0], scan every member of every
    # returned cluster and pick the single highest final_score member
    # chart-wide -- that member's OWN cluster (family/competency) is what
    # gets reported alongside it, not necessarily clusters[0].
    top_field_id = None
    top_field_label = None
    top_field_score = None
    top_field_confidence_band = None
    source_cluster = None
    best_score = float("-inf")
    for cluster in clusters:
        for member in cluster.get("members", []):
            score = member.get("final_score")
            try:
                score_val = float(score)
            except (TypeError, ValueError):
                continue
            if score_val > best_score:
                best_score = score_val
                top_field_id = member.get("field_id")
                top_field_label = member.get("field_label")
                top_field_score = score_val
                top_field_confidence_band = member.get("confidence_band")
                source_cluster = cluster

    domain = _course_registry_domain(top_field_id)
    implied_stream = DOMAIN_TO_STREAM.get(domain, "UNKNOWN")

    if precomputed_determination is not None:
        stream_determination = precomputed_determination
    else:
        stream_determination = compute_stream_determination(
            payload,
            include_field_derived_evidence=include_field_derived_evidence,
            d24_arbitration_enabled=d24_arbitration_enabled,
            classical_precedence_chain_enabled=classical_precedence_chain_enabled,
        )
    streams = stream_determination.get("streams", [])
    top_ranked_stream = stream_determination.get("top_ranked_stream") or (
        streams[0]["stream_id"] if streams else None
    )
    # GAP-FIX (caught testing this module against Lakshman): dominant_stream
    # can be legitimately None -- stream_scoring.py withholds it on purpose
    # (recommendation_status IN {INSUFFICIENT_DATA, INDETERMINATE_LOW_SUPPORT,
    # INDETERMINATE_CLOSE_CALL}) when confidence is low, which is NOT the
    # same as "no stream data exists." Comparing against a None dominant_stream
    # would make every low-confidence chart silently report agree=False/None
    # for the wrong reason (missing data, not disagreement). This validator
    # compares against top_ranked_stream (always populated whenever any
    # stream was scored at all) and separately reports whether
    # Stream_Determination itself was confident enough to assert that pick.
    own_dominant = stream_determination.get("dominant_stream")
    recommendation_status = stream_determination.get("recommendation_status", "UNKNOWN")
    # BUG FIX (2026-07-24, wrong comparison target): `recommended_stream` is
    # Stream_Determination's classical-precedence-chain pick -- the ACTUAL
    # stream shown to the user as THE recommendation -- and can legitimately
    # differ from top_ranked_stream/numeric_rank[0] (the raw normalized-score
    # leader) when Jaimini AK/AmK, vargottama, or another precedence rule
    # overrides the numeric leader (see stream_scoring.py's
    # precedence_decision/recommended_stream doc-comments). This module used
    # to compare implied_stream ONLY against top_ranked_stream and expose
    # that single result as `agree` -- confirmed misleading for Hemant M,
    # whose numeric leader (Commerce) matches the adult-evidence-implied
    # stream while the ACTUAL recommendation (Humanities, precedence-
    # overridden) does not; the old `agree=True` silently endorsed a stream
    # that was not even being recommended. Now both comparisons are computed
    # and reported as separate, explicitly named fields.
    recommended_stream = stream_determination.get("recommended_stream") or own_dominant or top_ranked_stream
    _implied_is_conclusive = implied_stream not in ("UNKNOWN", "AMBIGUOUS")
    adult_vs_numeric_agreement = (
        (implied_stream == top_ranked_stream) if _implied_is_conclusive else None
    )
    adult_vs_recommended_agreement = (
        (implied_stream == recommended_stream) if _implied_is_conclusive else None
    )
    # `agree`: kept for backward compatibility ONLY. Equals
    # adult_vs_numeric_agreement (the OLD, numeric-leader-based comparison)
    # -- NOT adult_vs_recommended_agreement. New callers should read the two
    # explicit fields above instead of this ambiguous one.
    agree = adult_vs_numeric_agreement

    return {
        "field_determination_top_cluster_field_id": top_field_id,
        "field_determination_top_cluster_field_label": top_field_label,
        "field_determination_top_cluster_field_score": (
            round(top_field_score, 2) if top_field_score is not None else None
        ),
        "field_determination_top_cluster_confidence_band": top_field_confidence_band,
        "field_determination_top_cluster_rank": (
            source_cluster.get("cluster_rank") if source_cluster else None
        ),
        "field_determination_macro_career_family": (
            source_cluster.get("career_family") if source_cluster else macro_identity.get("career_family")
        ),
        "field_determination_macro_competency": (
            source_cluster.get("competency") if source_cluster else macro_identity.get("competency")
        ),
        "field_determination_macro_identity_anchor_field": macro_identity.get("anchor_field"),
        "field_determination_top_cluster_domain": domain,
        "domain_implied_stream": implied_stream,
        "stream_determination_top_ranked_stream": top_ranked_stream,
        "stream_determination_dominant_stream": own_dominant,
        "stream_determination_recommendation_status": recommendation_status,
        "stream_determination_is_close_call": stream_determination.get("is_close_call"),
        "stream_determination_recommended_stream": recommended_stream,
        "adult_vs_numeric_agreement": adult_vs_numeric_agreement,
        "adult_vs_recommended_agreement": adult_vs_recommended_agreement,
        "agree": agree,
        "note": (
            "Independent cross-check, not a merge or override of either engine's own "
            "result. The Field_Determination side is the single HIGHEST-CONFIDENCE "
            "field across ALL reported clusters (highest final_score/confidence_band "
            "chart-wide), not necessarily clusters[0]'s top member -- a family ranked "
            "#2 or #3 by aggregate family_score can still contain the single strongest "
            "individual signal. adult_vs_numeric_agreement compares against "
            "top_ranked_stream (the plain highest-score stream, always populated); "
            "adult_vs_recommended_agreement compares against recommended_stream "
            "(Stream_Determination's actual user-facing pick, which may be "
            "precedence-overridden away from the numeric leader -- see "
            "stream_scoring.py's recommended_stream doc-comment). These two CAN "
            "legitimately disagree with each other. `agree` is kept for backward "
            "compatibility and equals adult_vs_numeric_agreement only -- not "
            "dominant_stream (which Stream_Determination may deliberately withhold -- "
            "see stream_determination_recommendation_status -- when its own "
            "confidence gates aren't met; that withholding is not the same as a "
            "disagreement with this validator). domain->stream is a many-to-one "
            "simplification (see "
            "DOMAIN_TO_STREAM) -- a disagreement here is worth reviewing manually, "
            "especially if stream_determination_is_close_call is also true. "
            "Field_Determination is designed for adult charts with a stable "
            "D10/dasha-timed career signal -- this validator is most meaningful run "
            "against adult (>=15, ideally >=21) charts by a developer/auditor, not as "
            "a live component of the under-15 report pipeline itself."
        ),
    }


def safe_cross_validate(
    payload: Any, *, snapshot: Any = None,
    precomputed_determination: Dict[str, Any] | None = None,
    include_field_derived_evidence: bool = False,
    d24_arbitration_enabled: bool = False,
    classical_precedence_chain_enabled: bool = True,
) -> Dict[str, Any]:
    """Wraps cross_validate_against_field_determination with error handling,
    for callers (e.g. early_age_stream_engine.py, stream_report.py) that must
    not let this OPTIONAL, heavier adult-engine cross-check take down the
    primary under-15 report if it fails or the chart data can't support it
    (e.g. run_engine raising on a genuinely malformed/thin payload).

    Pass `snapshot=` a pre-fetched FieldEngineSnapshot (see
    adult_engine_bridge.py) to reuse an adult-engine run already done
    elsewhere in the same CLI invocation instead of running it twice.

    Pass `precomputed_determination=` the SAME determination dict the caller
    already computed via compute_stream_determination() (e.g.
    early_age_stream_engine.py's run_for_payload) so this cross-check never
    silently triggers a second, differently-configured recompute -- see
    cross_validate_against_field_determination()'s docstring for the
    config-drift bug this fixes. If omitted (e.g. this module's own
    standalone __main__ CLI use), a fresh determination is computed using
    the include_field_derived_evidence/d24_arbitration_enabled/
    classical_precedence_chain_enabled kwargs passed here (explicit, not
    silently defaulted).
    """
    try:
        return cross_validate_against_field_determination(
            payload, snapshot=snapshot,
            precomputed_determination=precomputed_determination,
            include_field_derived_evidence=include_field_derived_evidence,
            d24_arbitration_enabled=d24_arbitration_enabled,
            classical_precedence_chain_enabled=classical_precedence_chain_enabled,
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
        return {
            "field_determination_top_cluster_field_id": None,
            "field_determination_top_cluster_field_label": None,
            "field_determination_top_cluster_field_score": None,
            "field_determination_top_cluster_confidence_band": None,
            "field_determination_top_cluster_rank": None,
            "field_determination_macro_career_family": None,
            "field_determination_macro_competency": None,
            "field_determination_macro_identity_anchor_field": None,
            "field_determination_top_cluster_domain": None,
            "domain_implied_stream": None,
            "stream_determination_top_ranked_stream": None,
            "stream_determination_dominant_stream": None,
            "stream_determination_recommended_stream": None,
            "stream_determination_recommendation_status": None,
            "stream_determination_is_close_call": None,
            "adult_vs_numeric_agreement": None,
            "adult_vs_recommended_agreement": None,
            "agree": None,
            "error": f"{type(exc).__name__}: {exc}",
            "note": (
                "Cross-validation against Field_Determination could not be completed for "
                "this chart (see 'error') -- this is optional supplementary evidence, "
                "not required for the primary Stream_Determination report, and its "
                "absence does not affect that report's own score or dominant stream."
            ),
        }


def format_cross_validation_text(report: Dict[str, Any]) -> List[str]:
    """Human-readable line-by-line rendering of a cross-validation report,
    shared by the CLI printer below and any other plain-text consumer."""
    if report.get("error"):
        return [
            "Cross-validation against Field_Determination: NOT AVAILABLE",
            f"  Reason: {report['error']}",
        ]
    def _label(value):
        return "AGREE" if value is True else "DISAGREE" if value is False else "N/A (ambiguous domain)"

    adult_vs_numeric = report.get("adult_vs_numeric_agreement", report.get("agree"))
    adult_vs_recommended = report.get("adult_vs_recommended_agreement")
    lines = [
        "Cross-validation against Field_Determination (adult engine, independent check):",
        f"  Field_Determination's highest-confidence field: {report.get('field_determination_top_cluster_field_label')} "
        f"(field_id={report.get('field_determination_top_cluster_field_id')}, "
        f"score={report.get('field_determination_top_cluster_field_score')}, "
        f"confidence={report.get('field_determination_top_cluster_confidence_band')}, "
        f"from cluster_rank={report.get('field_determination_top_cluster_rank')}, "
        f"domain={report.get('field_determination_top_cluster_domain')})",
        f"  Macro career family / competency: {report.get('field_determination_macro_career_family')} / "
        f"{report.get('field_determination_macro_competency')}",
        f"  Domain implies stream: {report.get('domain_implied_stream')}",
        f"  Stream_Determination's top-ranked stream (numeric): {report.get('stream_determination_top_ranked_stream')} "
        f"(dominant_stream={report.get('stream_determination_dominant_stream')}, "
        f"recommended_stream={report.get('stream_determination_recommended_stream')}, "
        f"status={report.get('stream_determination_recommendation_status')}, "
        f"close_call={report.get('stream_determination_is_close_call')})",
        f"  vs. numeric leader (top_ranked_stream): {_label(adult_vs_numeric)}",
        f"  vs. actual recommendation (recommended_stream): {_label(adult_vs_recommended)}",
    ]
    return lines


if __name__ == "__main__":
    import json
    import sys as _sys
    from jyotish.engine_io import parse_json_payload

    chart_path = _sys.argv[1] if len(_sys.argv) > 1 else "Charts/lakshman_chart_details.json"
    with open(chart_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    payload = parse_json_payload(raw, chart_path=chart_path)
    report = cross_validate_against_field_determination(payload)

    print()
    for line in format_cross_validation_text(report):
        print(line)
    print()
    print("Full JSON:")
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
