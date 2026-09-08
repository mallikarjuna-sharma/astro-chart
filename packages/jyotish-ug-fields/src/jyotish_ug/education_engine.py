#!/usr/bin/env python3
# Load .env before any jyotish imports so OPENAI_API_KEY is visible to llm.py.
# Works without python-dotenv — pure stdlib fallback.
#!/usr/bin/env python3
# Load .env before any jyotish imports so OPENAI_API_KEY is visible.
# Uses a robust zero-dependency regex parser to handle quotes and inline comments safely.
import os as _os, pathlib as _pathlib, re as _re

# FIX (2026-07-05): on Windows, redirecting stdout to a file (or piping it) makes
# Python fall back to the 'cp1252' codec instead of the interactive console's more
# forgiving encoding. Any Unicode debug-banner character (═, ─, —, emoji, etc.)
# then raises UnicodeEncodeError and kills the whole run before it reaches HTML
# generation — this is what caused "--mode career" to silently produce no HTML
# file. Force UTF-8 stdout/stderr with a safe error handler so no future print()
# can crash the run this way, on any terminal/redirect combination.
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

# This script now lives in Field_Determination/ (one level below the repo
# root). Add the repo root to sys.path so `jyotish` and `Job_Career` remain
# importable when this file is executed directly.
_repo_root = _pathlib.Path(__file__).resolve().parent.parent
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

# .env now lives in Field_Determination/ (this file's own directory), not
# the repo root -- moved there 2026-08-31. Check that location first, and
# keep the old repo-root path as a fallback in case it's ever moved back.
_env_path = _pathlib.Path(__file__).resolve().parent / ".env"
if not _env_path.exists():
    _env_path = _repo_root / ".env"
if _env_path.exists():
    # Matches: KEY = "VALUE" # comment
    # Groups: (1) Key, (2) Quote char or empty, (3) Value
    _env_regex = _re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(["\']?)(.*?)\2\s*(?:#.*)?$')
    
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _match = _env_regex.match(_line)
        if _match:
            _k, _, _v = _match.groups()
            if _k not in _os.environ:
                _os.environ[_k] = _v

"""
field_deterministic_engine_v1_llm.py — JyotishAI Career Engine v11.0

Backward-compatibility shim. All logic now lives in the jyotish/ package:
  jyotish/payload.py     — NatalPayloadV2 dataclass + ENGINE_VERSION
  jyotish/constants.py   — Astrological constants and lookup tables
  jyotish/astro.py       — Core Vedic math (dignity, aspects, Drishti Bala, Shadbala)
  jyotish/affinity.py    — BRANCH_PLANET_AFFINITY + affinity scorer
  jyotish/engine_io.py   — Payload parser, aptitude scorer, registry loader
  jyotish/llm.py         — Prompt template, chart summary, LLM provider calls
  jyotish/boosts.py      — Gap-boost helper functions (50+ scorers)
  jyotish/engine.py      — run_engine() main loop + QA helpers
  jyotish/output.py      — ExplainabilityEngine + HTML report generators

Import from this file or from the jyotish package directly — both work.
"""
from Field_Determination.jyotish.report_utils import (
    field_display_name as _field_display_name,
    print_macro_cluster as _print_macro_cluster,
    cluster_display_name as _cluster_display_name,
    top20_as_four_cluster_groups as _top20_as_four_cluster_groups,
)

from Field_Determination.jyotish.payload    import NatalPayloadV2, ENGINE_VERSION, logger
from Field_Determination.jyotish.constants  import (
    _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES,
    _SIGN_NUM, _SIGN_LORD, _COMBUST_ORB, _NODAL_DEFAULT_VIRUPAS,
    _PLANET_MIN_SHADBALA, _NAKSHATRA_LORD, _NEECHA_BHANGA_DATA,
    DOMAIN_STRATEGIES, _VALID_PLANETS, _VALID_DOMAINS,
    _MAHESHWARA_DOMAIN_KW, _STREAM_MAP,
)
from Field_Determination.jyotish.astro      import (
    compute_dignity, _planet_abs_degree, _compute_whole_sign_houses,
    get_nakshatra_from_longitude, _drishti_bala,
    _get_planetary_aspects, _get_planetary_aspects_weighted,
    _detect_neecha_bhanga, _detect_yogas, _detect_planetary_war,
    _get_nakshatra_dignity, _compute_eff_strengths,
    _is_vargottama, _detect_combust_planets, _calc_age,
    _get_active_dasha_lord,
)
from Field_Determination.jyotish.affinity   import BRANCH_PLANET_AFFINITY, compute_branch_affinity_score_llm
from Field_Determination.jyotish.engine_io  import parse_json_payload, compute_aptitude_by_domain, _load_course_registry
from Field_Determination.jyotish.llm        import (
    _build_chart_summary_for_llm, call_llm_for_fields,
)
from Field_Determination.jyotish.boosts     import *
from Field_Determination.jyotish.engine     import run_engine, execute_qa_verification_v8_9, classify_age_stage
from Field_Determination.jyotish.output     import ExplainabilityEngine
# SCOPE CUT (2026-08-31, user request): this file is now single-purpose --
# chart in, Top-20 fields table + HTML/JSON reports out. Career Timeline,
# Prashna (Horary), and EduAlign (stream/sub-branch/exam scoring) all moved
# to archive/career_prashna_cli.py, unchanged in behavior, just
# relocated -- use that script for those instead.

__all__ = [
    "NatalPayloadV2", "ENGINE_VERSION", "BRANCH_PLANET_AFFINITY",
    "parse_json_payload", "run_engine", "ExplainabilityEngine",
    "compute_branch_affinity_score_llm", "call_llm_for_fields",
    "classify_age_stage", "execute_qa_verification_v8_9",
]


# ── Cluster-strength weighting ────────────────────────────────────────────
# Gap-audit fix (2026-08): this whole block (_CLUSTER_RANK_DECAY/_MEMBER_CAP/
# _FLOOR_RATIO, _cluster_strength_weighted, _top20_as_four_cluster_groups,
# _field_display_name, _print_macro_cluster, _CLUSTER_DISPLAY_LABELS,
# _cluster_display_name) used to be defined here a SECOND time, byte-for-byte
# identical to jyotish/report_utils.py's canonical versions -- which this
# file already imports at the top (as _field_display_name, _print_macro_cluster,
# _cluster_display_name, _top20_as_four_cluster_groups). Because Python name
# binding is last-write-wins, these local redefinitions silently SHADOWED the
# imports: every one of this file's own callers was actually running the
# stale local copy, and any future edit to report_utils.py (the module its own
# docstring calls canonical/shared) would have had zero effect here. The two
# copies happened to be identical today, so there was no live behavior bug --
# but it was a maintenance trap. Removed; this module now uses the imported
# report_utils versions directly, so there is exactly one place that decides
# cluster grouping/ranking/display.


def _merged_cluster_display_name(rows):
    seen = []
    for _, row in rows:
        label = _print_macro_cluster(row)
        if label not in seen:
            seen.append(label)
    if not seen:
        return "Additional High-Fit Branches"
    if len(seen) == 1:
        return seen[0]
    if any("Law" in s or "Governance" in s for s in seen) and any("Economics" in s or "Finance" in s for s in seen):
        return "Law, Governance, Economics & Applied Enterprise"
    if len(seen) == 2:
        return f"{seen[0]} & {seen[1]}"
    # 3+ distinct clusters: use "+" as the separator (not ",") because each
    # individual cluster label already contains internal commas (e.g.
    # "Medical, Public Health & Welfare"), so comma-joining them produced an
    # unreadable run-on AND silently dropped every cluster past the 2nd.
    # Cap at 3 named clusters to keep the header readable; summarize the rest.
    if len(seen) <= 3:
        return " + ".join(seen)
    return " + ".join(seen[:3]) + " + Other Fields"


def _markdown_table(rows):
    lines = [
        "| Rank | Field |",
        "| ---: | ----- |",
    ]
    for rank, row in rows:
        lines.append(f"| {rank:>4} | {_field_display_name(row)} |")
    return "\n".join(lines)


def _macro_identity_line(results):
    report = (results[0].get("career_cluster_report") if results else {}) or {}
    macro = report.get("macro_identity") or {}
    parts = [
        macro.get("competency", ""),
        macro.get("career_family", ""),
        macro.get("anchor_field", ""),
    ]
    parts = [p for p in parts if p]
    if parts:
        return " + ".join(parts)

    top_clusters = [cluster for cluster, _ in _top20_as_four_cluster_groups(results)[:2]]
    return " + ".join(top_clusters) if top_clusters else "Not enough field data to derive a macro identity"


def _best_path_lines(results, career_phase="auto"):
    is_adult = career_phase in ("mid", "senior")

    if not results:
        if is_adult:
            return [
                "**Current strength:** Aligned to the top cluster",
                "**Upskilling:** Certification/specialization aligned to the strongest career family",
                "**Career direction:** Build toward the top-ranked field cluster.",
            ]
        return [
            "**UG:** BA / BSc / BCom aligned to the top cluster",
            "**PG:** Specialization aligned to the strongest career family",
            "**Career:** Build toward the top-ranked field cluster.",
        ]

    macro = ((results[0].get("career_cluster_report") if results else {}) or {}).get("macro_identity") or {}
    top = results[0]
    top_field = macro.get("anchor_field") or _field_display_name(top)
    family = macro.get("career_family") or top.get("career_family_label") or top.get("career_family") or "the strongest career family"
    cluster = macro.get("competency") or top.get("graph_cluster") or top.get("competency_label") or "the strongest macro-cluster"
    domain = (top.get("domain") or "").lower()
    combined_text = f"{top_field} {family} {cluster} {domain}".lower()

    ug_by_domain = {
        "law": "LLB / BA LLB / BA Political Science",
        "medicine": "MBBS / BAMS / allied health foundation",
        "technology": "BTech Computer Science / Data Science",
        "engineering": "BTech aligned to the selected engineering branch",
        "commerce": "BCom / BBA / Economics",
        "arts": "BDes / BA aligned to the creative specialization",
        "humanities": "BA aligned to the knowledge-system specialization",
        "science": "BSc aligned to the research specialization",
        "research": "BSc / BA with research-methods foundation",
    }
    pg_by_domain = {
        "law": "Public Policy / International Relations / Constitutional or International Law",
        "medicine": "Clinical, public-health, integrative-health, or hospital-management specialization",
        "technology": "AI / Data Science / Cybersecurity / Systems specialization",
        "engineering": "MTech / MS in the strongest engineering family",
        "commerce": "MBA / Finance / Economics / Analytics",
        "arts": "Design / Media / Creative Strategy specialization",
        "humanities": "Research / Education / Social Sciences specialization",
        "science": "MSc / Research master's in the strongest science family",
        "research": "Research master's / PhD track",
    }

    if "governance" in combined_text or "law" in combined_text or "civil" in combined_text:
        ug = "BA Political Science / Economics / LLB"
        pg = "Public Policy / International Relations / Constitutional or International Law"
    elif any(token in combined_text for token in ("yoga", "naturopathy", "ayurveda", "homeopathy", "unani", "holistic")):
        ug = "BNYS / BAMS / allied health foundation"
        pg = "Public Health / Integrative Medicine / Hospital or Wellness Management"
    elif "public policy" in combined_text or "governance" in combined_text:
        ug = "BA Political Science / Economics / LLB"
        pg = "Public Policy / International Relations / Constitutional or International Law"
    elif "data" in combined_text or "analytics" in combined_text:
        ug = "BSc/BTech Data Science / Economics / Statistics"
        pg = "Data Science / Economics / Computational Finance / Policy Analytics"
    else:
        ug = ug_by_domain.get(domain, "UG track aligned to " + top_field)
        pg = pg_by_domain.get(domain, "PG specialization aligned to " + family)

    if is_adult:
        # Q7/mid-senior career phase: an adult with an existing career should
        # never be handed a fresh-UG-admission plan. Reframe the same
        # underlying UG/PG signal as a certification/upskilling track instead
        # of a degree program, and phrase "Career" as a direction/transition
        # rather than an entry point. See gap_corrections_2026_07.py's round-3
        # docstring for the case that surfaced this (a 41-year-old chart was
        # rendered with "UG: BA Political Science / LLB").
        return [
            f"**Current strength:** {top_field} ({family})",
            f"**Upskilling:** Certifications/specialization equivalent to — {pg}",
            f"**Career direction:** {top_field}, {family}, and adjacent roles in {cluster}.",
        ]

    return [
        f"**UG:** {ug}",
        f"**PG:** {pg}",
        f"**Career:** {top_field}, {family}, and adjacent roles in {cluster}.",
    ]


# Fields actually read by jyotish/output.py::ExplainabilityEngine when it
# builds the full-trace HTML report (audited 2026-08-31 by grepping every
# `<record>.get("...")` / `<record>["..."]` access in that module). Everything
# NOT in this set (career_archetype, curriculum, market, competency/
# career_family labels, disclaimer, defensibility, boost_pct, top_karakas,
# etc.) is genuinely computed and consumed elsewhere -- web_report.py,
# competency_ontology.py, debug_payload_split.py's own classification, the
# console table/markdown below, the *_summary/_reference/_audit.json exports
# -- so it is NOT removed from engine.py's result dicts (that would break
# those other consumers). This filter only trims the copy handed to the HTML
# renderer, which never reads those fields anyway.
_HTML_TRACE_RESULT_KEYS = {
    "rank", "field_id", "field_label", "domain",
    "final_score", "affinity_score", "composite_score", "blended_score",
    "method_breakdown",
    "knrao_score", "kp_score", "jaimini_score", "parashara_score",
    "dashamsha_score", "sudarshana_score",
    "confidence_dimensions", "method_total_score", "weighted_method_score",
    "hard_lockout", "pre_norm_score", "norm_note",
    "confidence_band", "score_confidence",
    "career_outcomes", "admission_exams_canonical",
    "score_ceiling_tie", "tier1_score", "tier2_score", "tier3_score",
    "tier_decision_trace",
    # BUGFIX (2026-08-31, verify pass): the first cut of this whitelist was
    # built against educational_records/*_summary.json, which is ITSELF a
    # pre-filtered subset of the real run_engine() result dict (see
    # debug_payload_split.py) -- so it was missing keys that summary.json
    # drops into _reference/_audit.json but that output.py still reads
    # directly off the raw record. Confirmed by diffing the actual HTML
    # before/after this filter: the per-field "strongest planet" sentence
    # (via _top_planets() -> rec["affinity_planets"]) silently disappeared.
    # Re-derived from the real run_engine() output instead (see
    # jyotish/output.py call sites) -- these 7 were the ones missing:
    "affinity_planets", "calc_trace", "d9_navamsha_confirmation",
    "engine_rank", "explainability_matrix", "method_log", "wealth_potential",
    # LLM-enrichment fields: absent when enable_llm=False (this CLI's default
    # non-LLM run), but output.py does read them when present -- keep them
    # passing through rather than silently dropping LLM-enriched output.
    "llm_score", "llm_narrative", "llm_parent_reason",
    "llm_astrological_reason", "llm_selection_rationale", "llm_payload",
    "llm_rank", "llm_padded", "astrological_reason",
    "parent_friendly_explanation",
}


def _slim_results_for_html_trace(results):
    """Return a copy of `results` with each record filtered down to the keys
    jyotish/output.py's ExplainabilityEngine actually reads (see
    _HTML_TRACE_RESULT_KEYS above). Non-destructive: the original `results`
    list (used for the console table/markdown and the JSON exports) is
    untouched.
    """
    return [
        {k: v for k, v in r.items() if k in _HTML_TRACE_RESULT_KEYS}
        for r in results
    ]


def _print_jaimini_karaka_scheme_disclosure(payload):
    """Audit fix (2026-08-20, spec §3 "Scheme disclosure required" /
    claim #9 minor gap): the engine's own docstring for
    astro.py::_compute_bvb_7_karakas already documented, in detail, that
    this engine uses the classical Sapta (7) Chara Karaka scheme (Rahu
    excluded from the AK/AmK degree-sort) rather than the Ashtaka (8)
    scheme some Jaimini practitioners use (which can shift which planet
    is Atmakaraka), and explicitly flagged that "no end-user-facing
    disclosure of this caveat currently exists ... consider surfacing it
    there if AK-driven conclusions are presented to end users." AK-driven
    conclusions (career signification, Karakamsha) are presented in every
    run's Top-20/report output, so print the disclosure once per run,
    naming the actual Atmakaraka this chart resolved to under the 7-karaka
    scheme.
    """
    ak = getattr(payload, "atmakaraka", "") or "not available"
    print(
        f"\n[JAIMINI KARAKA SCHEME] Atmakaraka = {ak}, computed under the classical "
        f"Sapta (7) Chara Karaka scheme (Sun-Saturn; Rahu excluded from the "
        f"degree-rank sort), per the majority Parashara/BV Raman reading. A "
        f"minority Ashtaka (8) scheme includes Rahu as an 8th candidate and can "
        f"assign a different Atmakaraka on charts where Rahu's effective degree "
        f"ranks near this planet's. All AK-driven findings below (career "
        f"signification, Karakamsha) are conditioned on the 7-karaka reading."
    )


def _print_final_top20_table(results, payload, file=None):
    """Print the FINAL, actually-published Top-20 ranking as one plain
    rank-ordered CLI table (rank / field / domain / final_score /
    confidence_band). Added per user request (2026-08-20): the CLI already
    prints a Top-20 view via _render_top20_cluster_markdown() just below,
    but that groups fields by career-cluster/stream, not by rank -- there
    was no single place in the CLI output where a reader could see "these
    are the 20 fields, in order, with the score that actually decided that
    order" at a glance, without re-deriving it from the per-field
    [FIELD SCORE]/[V2-PRIMARY FINAL_SCORE]/[TIE-BREAK] instrumentation
    scattered earlier in the run. Reads `rank`/`final_score` exactly as
    stamped by _finalize_published_results() -- the same fields the HTML
    report's ranking-overview table and the *_summary.json export both
    read -- so this table can never disagree with what ships elsewhere.
    """
    import sys as _sys_mod
    if file is None:
        file = _sys_mod.stdout
    name = getattr(payload, "name", "") or "Native"
    ranked = sorted(
        (r for r in results if isinstance(r.get("rank"), int)),
        key=lambda r: r["rank"],
    )[:20]
    print("\n" + "=" * 92, file=file)
    print(f"FINAL TOP 20 FIELDS — {name} (published ranking, decided by final_score)", file=file)
    print("=" * 92, file=file)
    header = f"{'#':>3}  {'Field':<48} {'Domain':<16} {'Score':>7}  {'Confidence':<21}"
    print(header, file=file)
    print("-" * len(header), file=file)
    for r in ranked:
        rank = r.get("rank", "?")
        label = str(r.get("field_label", r.get("field_id", "")))[:48]
        domain = str(r.get("domain", ""))[:16]
        score = r.get("final_score", 0.0) or 0.0
        conf = str(r.get("confidence_band", "") or "")[:21]
        flags = []
        if r.get("core_three_excluded_applied"):
            flags.append("EXCLUDED-core-three")
        if r.get("dasha_coverage_reject_applied"):
            flags.append("DOWNRANKED-sustainability")
        if r.get("v2_tiebreak_applied"):
            flags.append("tie-broken")
        flag_str = f"  [{'+'.join(flags)}]" if flags else ""
        print(f"{rank:>3}  {label:<48} {domain:<16} {score:>7.2f}  {conf:<21}{flag_str}", file=file)
    print("=" * 92 + "\n", file=file)


def _render_top20_cluster_markdown(results, payload):
    name = getattr(payload, "name", "") or "Native"
    groups = _top20_as_four_cluster_groups(results)
    lines = [f"## {name} — Top 20 Fields Grouped by Cluster", ""]

    for idx, (cluster, rows) in enumerate(groups, 1):
        cluster_label = (
            _merged_cluster_display_name(rows)
            if cluster == "Additional Top-20 Branches"
            else _cluster_display_name(cluster)
        )
        lines.append(f"### Cluster {idx}: {cluster_label}")
        lines.append("")
        if idx == 1:
            lines.append("**Strongest macro-cluster**")
            lines.append("")
        lines.append(_markdown_table(rows))
        lines.append("")

    lines.append("## Final macro identity")
    lines.append("")
    lines.append(f"**{_macro_identity_line(results)}**")
    lines.append("")
    lines.append("Best path:")
    lines.append("")
    try:
        from Field_Determination.jyotish.engine import _resolve_career_phase
        career_phase = _resolve_career_phase(payload)
    except Exception:
        career_phase = "auto"
    lines.extend(_best_path_lines(results, career_phase))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse, json, os, sys
    from Field_Determination.jyotish.engine_io import parse_json_payload

    # CLI-quiet mode (user request, 2026-08-31): the console should show
    # ONLY the "Engine: ... | Active Dasha: ..." line + the FINAL TOP 20
    # FIELDS table below -- every other print()/logger.info/warning() call
    # made anywhere in this run (course-registry load, KP self-heal,
    # eff_strength narrative, dasha-continuity bonuses, V2/field-filter
    # narratives, Jaimini karaka disclosure, cluster markdown, career field
    # report, tie-break disclosure, explainability sections, final report,
    # LLM pipeline banner, JSON-payload-saved lines, etc.) is suppressed
    # rather than deleted -- the underlying computation, file writes
    # (HTML/JSON reports) and return values are completely unaffected;
    # only what reaches the terminal changes. `_real_stdout` keeps a
    # handle to the actual console so the two kept print() calls below can
    # still reach it.
    import io as _io
    import logging as _logging
    _real_stdout = sys.stdout
    sys.stdout = _io.StringIO()
    _logging.disable(_logging.CRITICAL)

    ap = argparse.ArgumentParser(
        description="JyotishAI Engine - Field Determination (Top 20 Fields)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "SCOPE CUT (2026-08-31): this CLI now only produces the Top-20\n"
            "fields table + its HTML/JSON reports. Career Timeline, Prashna\n"
            "(Horary), and EduAlign moved to\n"
            "archive/career_prashna_cli.py -- use that script for\n"
            "those instead.\n\n"
            "Examples:\n"
            "  python education_engine.py chart.json\n"
            "  python education_engine.py chart.json --out my_reports\n"
        ),
    )
    ap.add_argument("chart", nargs="?", default="ramsunder_chart_details.json",
                    help="Path to chart JSON file (default: ramsunder_chart_details.json)")
    ap.add_argument(
        "audience", nargs="?", default=None,
        help=(
            "Optional second positional argument selecting which audience's LLM "
            "narrative/report wording is used: 'Astrologer' (technical, "
            "astrological_reason -- the default, matching --Astrologer_Version's "
            "own default of True) or 'Parent' (plain-language, "
            "parent_friendly_explanation). Case-insensitive. When given, this "
            "overrides --Astrologer_Version/--no-Astrologer_Version. Same underlying "
            "audience switch documented on --Astrologer_Version below -- see "
            "jyotish/llm.py::call_llm_for_fields for how it's consumed."
        ),
    )
    ap.add_argument("--out", default="educational_records",
                    help="Output directory for HTML reports (default: educational_records)")
    ap.add_argument(
        "--llm", action="store_true",
        help=(
            "Enable per-field LLM astrologer explanations (jyotish/llm.py::call_llm_for_fields) "
            "on the 14-section Career Field Recommendation Report this CLI also generates. Also "
            "requires LLM consent -- either external_llm_consent:true in the chart JSON's "
            "student_context, or LLM_REPORT_CONSENT=true in .env -- plus a working LLM_PROVIDER "
            "+ API key in .env. Off by default: this makes a real LLM API call per report. With "
            "DEBUG=true also set in .env, this is what triggers "
            "<chart_name>_astrological_signals_debug.json to be written. This flag does NOT "
            "affect the deterministic console table/markdown printed by this CLI -- see the "
            "GAP-FIX comment at the generate_career_field_report_v2(...) call site below for why."
        ),
    )
    ap.add_argument(
        "--Astrologer_Version", dest="Astrologer_Version",
        action=argparse.BooleanOptionalAction, default=True,
        help=(
            "Toggle astrologer-facing output framing/wording for the console "
            "table and generated reports. Default: True (--no-Astrologer_Version "
            "to disable)."
        ),
    )
    args = ap.parse_args()

    # Positional `audience` (Astrologer|Parent, case-insensitive) overrides
    # --Astrologer_Version/--no-Astrologer_Version when given. Validated
    # strictly -- an unrecognized value is a hard error, not a silent
    # fallback, since silently picking the wrong audience would generate a
    # wrong-tone report without any indication anything went wrong.
    if args.audience is not None:
        _audience_norm = args.audience.strip().lower()
        if _audience_norm not in {"astrologer", "parent"}:
            ap.error(
                f"invalid audience {args.audience!r} -- expected 'Astrologer' or "
                "'Parent' (case-insensitive)"
            )
        args.Astrologer_Version = (_audience_norm == "astrologer")

    with open(args.chart) as f:
        raw = json.load(f)

    payload = parse_json_payload(raw, build_timeline=False, chart_path=args.chart)
    # --Astrologer_Version / --no-Astrologer_Version (default: True). Stashed
    # on the payload (NatalPayloadV2 has extra="allow") so it reaches
    # call_llm_for_fields() in jyotish/llm.py without threading a new
    # parameter through run_engine()/call_llm_for_fields()'s signatures --
    # it decides which audience's LLM narrative (+ prompt) gets generated
    # and dumped to disk: astrologer-facing only (default) or
    # parent/client/student-facing only.
    payload.astrologer_version = bool(args.Astrologer_Version)

    # BUG FIX (2026-09, same "--llm on, llm_narrative still null" report):
    # --llm's own help text (see ap.add_argument("--llm", ...) above) has
    # always documented TWO ways to grant consent -- "either
    # external_llm_consent:true in the chart JSON's student_context, or
    # LLM_REPORT_CONSENT=true in .env" -- but the env-var bypass was only
    # ever implemented inside generate_career_field_report_v2()'s own local
    # _env_llm_consent check (Job_Career package), never for run_engine()
    # itself. run_engine()'s llm_authorized gate only ever reads
    # payload.external_llm_consent (see engine.py), so a chart JSON without
    # student_context.external_llm_consent:true silently never ran the LLM
    # step for this CLI's own `results` even with LLM_REPORT_CONSENT=true
    # set and --llm passed. Mirrors that same env-var bypass here so both
    # documented consent paths actually work for this CLI, not just the
    # (Job_Career-only) CFR report path.
    if args.llm and not getattr(payload, "external_llm_consent", False):
        _env_llm_consent = str(os.getenv("LLM_REPORT_CONSENT", "")).strip().lower() in {"1", "true", "yes", "on"}
        if _env_llm_consent:
            payload.external_llm_consent = True
            print("[LLM] LLM consent granted via LLM_REPORT_CONSENT env var.")

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    # ── Early-age gate (2026-07-22) ─────────────────────────────────────────
    # A chart belonging to a child under 15 should never be run through the
    # 205-branch field engine below (gap-audit fix, 2026-08: was "199-branch",
    # stale -- the verified, currently-agreeing count across the loaded
    # registry/affinity.py/ontology is 205; see
    # jyotish/ONTOLOGY_REGISTRY_V12_README.md's "Expected result" section)
    # (or its career-timeline/prashna/edu
    # siblings) -- that machinery adjudicates between specific vocational
    # branches, which is not a meaningful question yet at that age. Divert
    # entirely to the separate Stream_Determination package (Science/
    # Commerce/Humanities + subject ranking), which lives in its own folder,
    # writes its own output files, and is only imported here -- it shares no
    # code with the field engine below other than chart-parsing/astrology
    # primitives it already imported independently.
    # SCOPE CUT (2026-08-31): this file is field-only now (Career/Prashna/
    # EduAlign moved to archive/career_prashna_cli.py), so this gate always applies
    # unconditionally -- no more --mode branching here.
    try:
        from Stream_Determination.early_age_stream_engine import is_eligible, run_for_payload
    except ModuleNotFoundError:
        # Stream_Determination/ was removed from this repo checkout. Without
        # it we can't do the under-15 diversion check, so fall through to the
        # full Field Determination engine below instead of crashing.
        is_eligible = None
        run_for_payload = None

    if is_eligible is not None and is_eligible(payload):
        print(
            f"\nChart age ({getattr(payload, 'current_age', '?')}) is under 15 -- "
            "routing to the Stream Determination engine (Science/Commerce/"
            "Humanities + subjects) instead of the full Field Determination engine."
        )
        _stream_result = run_for_payload(payload, out_dir=out_dir)
        print(f"Dominant stream: {_stream_result.get('dominant_stream')}")
        print(f"Stream report (JSON): {_stream_result['paths']['json']}")
        print(f"Stream report (HTML): {_stream_result['paths']['html']}")
        sys.exit(0)

    from Field_Determination.jyotish.engine import run_engine
    from Field_Determination.jyotish.astro import _get_active_dasha_lord

    # BUG FIX (2026-09, "--llm on but Summary/Reference JSON llm_narrative
    # still null" report): this used to hard-code enable_llm=False so the
    # printed/top-level field output stayed tied to the deterministic
    # engine -- the original rationale being that LLM selection could
    # reorder/filter candidates when credentials were present, making the
    # console "field output" diverge from the engine's own ranking. That
    # rationale is stale: call_llm_for_fields() was rewritten (see its own
    # "one page, not a huge JSON object" GAP-FIX docstring) to pass the
    # deterministic top20 through UNCHANGED in rank order, only attaching
    # llm_rank/llm_score/field-narrative bookkeeping on top -- it no longer
    # reorders or filters anything. So hard-coding enable_llm=False here was
    # silently preventing --llm (+ external_llm_consent) from ever reaching
    # this CLI's own `results` -- the same `results` route_map.py and
    # cluster_field_export.py build the Summary/Reference JSON from -- which
    # is why llm_narrative stayed null even with LLM consent switched on.
    # run_engine() itself still gates this on payload.external_llm_consent
    # (see engine.py's llm_authorized check) and falls back to the identical
    # deterministic result set on any failure, so this is safe even when
    # --llm is passed without consent configured.
    results = run_engine(
        payload, enable_llm=bool(getattr(args, "llm", False)),
        # field_narratives (2026-09 addition) requires the model to fill in
        # one entry per fit field (up to 20), a stricter target than the
        # old 3-section-only response -- bump the retry budget from
        # run_engine()'s own default of 1 so a single missing/short
        # per-field entry doesn't exhaust the whole call on the first try.
        llm_max_retries=2,
    )

    # DIAGNOSTIC (2026-09, "why still the llm_narrative is null" -- 3rd pass):
    # every point where the LLM step can silently no-op (consent false,
    # provider API key missing, call_llm_for_fields returning falsy after
    # exhausting retries) only ever went through logger.warning/logger.error,
    # which this CLI's own logging.disable(CRITICAL) quiet-mode swallows
    # completely -- so none of those reasons ever reached the user's
    # terminal. Surface the actual reason directly to _real_stdout instead of
    # guessing further.
    _llm_requested = bool(getattr(args, "llm", False))
    _llm_consent   = bool(getattr(payload, "external_llm_consent", False))
    # NOTE (fix): the field run_engine()/_attach_validation_contract() actually
    # sets is "llm_enrichment_used", not "llm_used" -- the previous diagnostic
    # build checked the wrong key and always read False regardless of whether
    # the LLM call had actually succeeded, which made every earlier diagnostic
    # run here misleading.
    _llm_used_flag = bool((results[0] or {}).get("llm_enrichment_used")) if results else False
    _sample_narrative = None
    for _row in (results or [])[:5]:
        _sample_narrative = _row.get("astrological_reason") or _row.get("parent_friendly_explanation")
        if _sample_narrative:
            break
    if _llm_requested:
        print(f"\n[LLM DIAGNOSTIC] --llm passed: True | consent granted: {_llm_consent} | "
              f"llm_used on results: {_llm_used_flag}", file=_real_stdout)
        if not _llm_consent:
            print("[LLM DIAGNOSTIC] -> Skipped: external_llm_consent is not true on the payload. "
                  "Set student_context.external_llm_consent=true in the chart JSON, or set "
                  "LLM_REPORT_CONSENT=true in the environment/.env before running.", file=_real_stdout)
        else:
            _provider_name = os.getenv("LLM_PROVIDER", "gemini").lower()
            _env_var_map = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
            _expected_env_var = _env_var_map.get(_provider_name, "GEMINI_API_KEY")
            _has_key = bool(os.getenv(_expected_env_var))
            print(f"[LLM DIAGNOSTIC] LLM_PROVIDER={_provider_name!r} | expects env var "
                  f"{_expected_env_var}={'<set>' if _has_key else '<MISSING>'}", file=_real_stdout)
            if not _has_key:
                print(f"[LLM DIAGNOSTIC] -> Skipped: {_expected_env_var} is not set in the environment "
                      f"this process sees (check your .env is in the working directory the CLI is run "
                      f"from, and that it's actually being loaded).", file=_real_stdout)
            elif not _llm_used_flag:
                print("[LLM DIAGNOSTIC] -> Consent + API key both present, but results show llm_used=False. "
                      "This means call_llm_for_fields() ran and returned falsy -- most likely it exhausted "
                      "llm_max_retries on schema/validation failures (e.g. the model didn't fill in all "
                      "field_narratives entries) or the provider call itself raised/errored.", file=_real_stdout)
                _llm_last_errors = getattr(payload, "llm_last_errors", None) or []
                if _llm_last_errors:
                    print("[LLM DIAGNOSTIC] Actual per-attempt failure reasons:", file=_real_stdout)
                    for _err_line in _llm_last_errors:
                        print(f"[LLM DIAGNOSTIC]   - {_err_line}", file=_real_stdout)
                else:
                    print("[LLM DIAGNOSTIC] No per-attempt error detail captured (unexpected) -- set "
                          "DEBUG=true and re-run for the *_astrologer_narrative_debug.json / "
                          "*_parent_narrative_debug.json dump.", file=_real_stdout)
            else:
                print("[LLM DIAGNOSTIC] -> LLM step ran successfully (llm_enrichment_used=True). "
                      f"Sample per-field narrative present: {bool(_sample_narrative)}"
                      + (f" -> {_sample_narrative[:120]!r}..." if _sample_narrative else ""), file=_real_stdout)
    else:
        print("\n[LLM DIAGNOSTIC] --llm was not passed on this run, so the LLM step never runs regardless "
              "of consent -- pass --llm to enable it.", file=_real_stdout)

    active_lord = _get_active_dasha_lord(
        getattr(payload, "dasha_sequence", []),
        float(getattr(payload, "current_age", 0)),
    )

    print(f"\nEngine: {ENGINE_VERSION}  |  Active Dasha: {active_lord or 'N/A'}", file=_real_stdout)
    print(file=_real_stdout)
    _print_final_top20_table(results, payload, file=_real_stdout)
    _print_jaimini_karaka_scheme_disclosure(payload)
    print(_render_top20_cluster_markdown(results, payload))
    from Field_Determination.jyotish.validation_contract import UNIVERSAL_DISCLAIMER
    print(f"\nIMPORTANT: {UNIVERSAL_DISCLAIMER}")

    # NOTE (2026-07, user request): the plain generate_web_report()
    # card-list output (jyotish_report_<name>.html) was removed here.
    # It duplicated the richer 14-section career_field_report_v2 output
    # below (career_field_report_<name>_<timestamp>.html) on every run,
    # writing two HTML reports for one invocation. generate_web_report()
    # itself is untouched in jyotish/web_report.py in case another
    # caller still wants the plainer card-list format -- only this CLI's
    # automatic call to it was removed.

    # ── 14-section Career Field Recommendation Report ─────────────────────
    # This is the richer report (career_field_report_v2.render_report_html)
    # that generate_career_field_report.py produces standalone — wired in
    # here too so `--mode field`/`--mode both` on this CLI also emits it,
    # not just the plainer generate_web_report() card-list report above.
    try:
        from Job_Career.career_field_report_v2 import generate_career_field_report_v2
        # GAP-FIX (2026-08, "wire --llm through education_engine.py"):
        # generate_career_field_report_v2() only calls run_engine() (and
        # therefore only ever triggers call_llm_for_fields / the
        # astrologer-facing LLM explanations / the DEBUG=true debug
        # dump) when precomputed_results is None -- see its own
        # `if precomputed_results is None: results = run_engine(...)`
        # branch. This CLI always passed its own already-computed
        # `results` (from the deliberately enable_llm=False run above,
        # kept non-LLM so the console table/markdown never gets
        # reordered/filtered by LLM enrichment -- see the comment on
        # that run_engine() call) as precomputed_results, which meant
        # generate_career_field_report_v2()'s own enable_llm_field_explanations
        # parameter was silently a no-op here: the report always reused
        # the same non-LLM `results`, regardless of that flag.
        # When --llm is passed, let the report do its own fresh
        # run_engine(payload, enable_llm=True) pass instead of reusing
        # this CLI's deterministic `results` -- this CLI's own printed
        # console table/markdown above is unaffected either way, since
        # it was already rendered from `results` before this point.
        cfr_path = generate_career_field_report_v2(
            args.chart, student_name=getattr(payload, "name", None), output_dir=out_dir,
            precomputed_results=None if args.llm else results,
            enable_llm_field_explanations=args.llm,
            # Bug fix (2026-08-17): this CLI's own `payload` already ran
            # run_engine() above (line ~380) and got peak_dasha_lord set
            # as a side effect (e.g. "Saturn", logged as "Peak career
            # MD"). generate_career_field_report_v2() builds its OWN
            # fresh payload from args.chart internally and, when given
            # precomputed_results, never reruns run_engine() on it -- so
            # without this, it silently fell back to the active dasha
            # (e.g. "Jupiter") instead of the real peak dasha, causing
            # the CLI markdown and the HTML report to disagree about
            # which Mahadasha is the chart's career-peak period. Still
            # passed through even when --llm triggers a fresh internal
            # run_engine() call, since peak_dasha_lord is a deterministic
            # chart fact unaffected by enable_llm.
            peak_dasha_lord=getattr(payload, "peak_dasha_lord", ""),
        )
        print(f"Career Field Recommendation report: {cfr_path}")
        if args.llm:
            print(
                "  (--llm enabled: report includes astrologer-facing classical-signal "
                "explanations; with DEBUG=true in .env, an "
                "<chart_name>_astrological_signals_debug.json debug dump was also attempted -- "
                "see logs above if it's not present.)"
            )
    except ModuleNotFoundError as _cfr_e:
        # Job_Career/ was removed from this repo checkout, so the 14-section
        # Career Field Recommendation report is expected to be unavailable --
        # a known, already-diagnosed condition, not a bug. Say so briefly
        # instead of dumping a full traceback on every run.
        print(
            f"\nCareer Field Recommendation report skipped: {_cfr_e} "
            "(Job_Career package not present in this checkout)"
        )
    except Exception as _cfr_e:
        import traceback; traceback.print_exc()
        print(f"\nCareer Field Recommendation report generation failed: {_cfr_e}")

    # Retired 2026-09-01: full-trace HTML report generation disabled per user request; simplified summary HTML (export_html_simple_summary) is now the primary output.
    #     # ── Full-trace explainability report (Parent | Astrologer | Debug Trace) ──
    #     # ExplainabilityEngine.export_html_full_trace() is the report-assembly
    #     # function audited/instrumented against spec §12 ("Output Ranking &
    #     # Reporting Format") -- Chart Summary, technique-first Evidence Table,
    #     # raw-vs-adjusted planetary-strength ranking, Top-N Fields table (with
    #     # Recommended Stream / Peak Career Dasha Window / Wealth-Sustainability
    #     # Note / Risk-Caveat columns), Grouped Stream Recommendation, Practical
    #     # Next Steps, and Caveats & Confidence Notes. It was imported at module
    #     # load (see `from jyotish.output import ExplainabilityEngine` above) but
    #     # never actually invoked from this CLI -- wired in here so `--mode
    #     # field`/`--mode both` produces it alongside the CFR report above.
    #     # Reuses this CLI's own `payload`/`results` (already ran run_engine()),
    #     # same peak_dasha_lord fix as the CFR call above.
    #     try:
    #         explain_path = ExplainabilityEngine.export_html_full_trace(
    #             _slim_results_for_html_trace(results),
    #             payload,
    #             active_lord=active_lord or "",
    #             peak_lord=getattr(payload, "peak_dasha_lord", "") or active_lord or "",
    #             student_name=getattr(payload, "name", None) or "Native",
    #             top_n=20,
    #             output_dir=out_dir,
    #         )
    #         print(f"Full explainability report (Top 20, Parent/Astrologer/Debug-Trace): {explain_path}")
    #     except Exception as _explain_e:
    #         import traceback; traceback.print_exc()
    #         print(f"\nFull explainability report generation failed: {_explain_e}")

    # ── Debug: LLM output summary ─────────────────────────────────────────
    print("\n" + "═"*80)
    print("LLM PIPELINE OUTPUT (TOP 5)")
    print("═"*80)

    llm_selected_fields = [r for r in results if "parent_friendly_explanation" in r]
    for i, field in enumerate(llm_selected_fields[:5], 1):
        label = field.get("field_label", field.get("field_id", "Unknown"))
        parent_exp = field.get("parent_friendly_explanation", "No parent text generated.")
        astro_exp  = field.get("astrological_reason",         "No astrological text generated.")
        print(f"\n[{i}] {label.upper()}")
        print("-" * 60)
        print(f"PARENT EXPLANATION:\n{parent_exp}\n")
        print(f"ASTROLOGICAL REASON:\n{astro_exp}")

    print("\n" + "═"*80)

    import json
    import os
    _redact_debug = bool(getattr(payload, "redact_debug_output", True))
    _debug_stem = "redacted_engine" if _redact_debug else payload.name.replace(' ', '_')
    safe_results = [
        {k: v for k, v in r.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
        for r in results
    ]

    # ── Astrologer_Version audience filter (final JSON output) ────────────
    # --Astrologer_Version / --no-Astrologer_Version (default: True) decides
    # which audience's narrative text survives into the final JSON files
    # (*_summary.json / *_reference.json / *_audit.json below, and the
    # in-memory `safe_results` the rest of this block also reads for the
    # "LLM PIPELINE OUTPUT" console preview). The engine writes two parallel
    # narrative fields per candidate field: "astrological_reason" (technique
    # names, yogas, dasha/varga citations -- written for an astrologer
    # reader) and "parent_friendly_explanation" (plain-language, written for
    # a client/parent/student reader). Only one survives per run:
    #   True  (default) -> astrologer-facing only: drop
    #                       parent_friendly_explanation, keep
    #                       astrological_reason.
    #   False            -> client/parent/student-facing only: drop
    #                       astrological_reason, keep
    #                       parent_friendly_explanation.
    # Every other key (scores, career_outcomes, market, disclaimers, etc.)
    # is audience-neutral and is left untouched either way.
    _ASTROLOGER_ONLY_KEYS = {"parent_friendly_explanation"}
    _PARENT_ONLY_KEYS = {"astrological_reason", "llm_astrological_reason"}
    _drop_keys = _ASTROLOGER_ONLY_KEYS if args.Astrologer_Version else _PARENT_ONLY_KEYS
    safe_results = [
        {k: v for k, v in r.items() if k not in _drop_keys}
        for r in safe_results
    ]

    # ── Split the debug payload into 3 smaller, purpose-specific files ────
    # instead of one monolithic *_llm_debug.json. Rationale (2026-07-18,
    # user request "optimize/reduce size"): profiling one real chart
    # showed the combined payload runs ~3-5MB for ~35 candidate fields,
    # almost entirely from per-field audit/provenance trails that most
    # consumers (UI, reports, LLM prompts) never read. Splitting by
    # purpose lets each consumer load only what it needs:
    #   *_summary.json  - small, everything a UI/report/LLM prompt needs
    #                      to display or reason about ranked results.
    #   *_reference.json - registry/ontology/catalog data backing each
    #                      field (larger, but stable/cacheable).
    #   *_audit.json    - full calculation/evidence/provenance trail,
    #                      only needed for defensibility audits/debugging.
    # `registry_legacy` is dropped entirely: verified to be byte-identical
    # to `registry` on every field, so it's pure duplication.
    from Field_Determination.debug_payload_split import split_debug_payload
    # skip_labels=all three (2026-09 fix, "*_audit.json should get created
    # as the LAST step, after the astrological explanation is added -- not
    # written early and then modified"): education_engine.py immediately
    # replaces the content of all three files below anyway (Summary with
    # the route-map, Reference with the cluster/field export, Audit with
    # the astrological-trace export -- the last of which can involve a slow
    # LLM call). Previously split_debug_payload wrote its own raw/fallback
    # content to disk FIRST and this code overwrote it moments later --
    # visibly "created, then modified" on disk, and briefly holding wrong
    # content in the case something else was reading it in between. Only
    # COMPUTE the paths here; each file is now written exactly once, by
    # whichever block below actually has its final content ready.
    paths, _raw_debug_data = split_debug_payload(safe_results, out_dir, _debug_stem, skip_labels={"Summary", "Reference", "Audit"})

    # ── Summary JSON cleanup (2026-09, "keep 3 JSON simple" request) ──────
    # *_summary.json previously carried the same big per-field score/label
    # dump as *_reference.json/*_audit.json (just a smaller key subset of
    # the same rows) -- heavily overlapping content across all three files.
    # Replaced with the actual "Summary" content from the parent/student-
    # facing report: the one-line overall recommendation, the Route A/B/C
    # education map, and the "avoid as primary" verdict -- ported from
    # Job_Career/career_field_report_v2.py's deterministic route-selection
    # pipeline into Field_Determination/route_map.py (see that module's
    # docstring) since the Job_Career package itself isn't part of this
    # checkout. Deliberately best-effort: on any failure (e.g. a chart with
    # too few candidate fields to fill all three routes), falls back to
    # leaving *_summary.json as split_debug_payload wrote it above rather
    # than breaking report generation.
    try:
        from Field_Determination.route_map import build_route_map_summary
        route_map_summary = build_route_map_summary(results)
        with open(paths["Summary"], "w", encoding="utf-8") as _sf:
            json.dump(route_map_summary, _sf, indent=4, ensure_ascii=False)
        print(f"\nSummary JSON payload saved to: {paths['Summary']}")
    except Exception as _route_map_exc:
        import traceback; traceback.print_exc()
        with open(paths["Summary"], "w", encoding="utf-8") as _sf_fallback:
            json.dump(_raw_debug_data["Summary"], _sf_fallback, indent=4, ensure_ascii=False)
        print(
            f"\nRoute-map summary JSON generation failed ({_route_map_exc}); "
            f"Summary JSON payload saved to: {paths['Summary']} (per-field fallback content)"
        )

    # ── Reference JSON cleanup (2026-09, same "keep 3 JSON simple" request) ─
    # *_reference.json previously carried per-field registry/ontology data
    # keyed by rank (no cluster grouping, no LLM narrative attached).
    # Replaced with: (1) the same 4-cluster grouping + per-cluster strength
    # percentage as the HTML "Field scores by cluster" panel (rank, cluster
    # name, strength_pct, and each cluster's top-20 member fields with
    # final_score), and (2) a flat "fields" lookup keyed by field_id holding
    # the FULL v12 course-registry record for each field plus that field's
    # LLM narrative text when one exists on the row (or, failing that, the
    # chart-level one-page LLM summary -- see cluster_field_export.py's
    # _field_llm_narrative()). Same best-effort fallback pattern as the
    # Summary JSON above: on failure, leaves *_reference.json as
    # split_debug_payload wrote it rather than breaking report generation.
    try:
        from Field_Determination.cluster_field_export import build_cluster_field_export
        cluster_field_export = build_cluster_field_export(results, payload)
        with open(paths["Reference"], "w", encoding="utf-8") as _rf:
            json.dump(cluster_field_export, _rf, indent=4, ensure_ascii=False, default=str)
        print(f"\nReference JSON payload saved to: {paths['Reference']}")
    except Exception as _cluster_export_exc:
        import traceback; traceback.print_exc()
        with open(paths["Reference"], "w", encoding="utf-8") as _rf_fallback:
            json.dump(_raw_debug_data["Reference"], _rf_fallback, indent=4, ensure_ascii=False)
        print(
            f"\nCluster/field reference JSON generation failed ({_cluster_export_exc}); "
            f"Reference JSON payload saved to: {paths['Reference']} (per-field fallback content)"
        )

    # ── Audit JSON cleanup (2026-09, "just the astrological trace of each
    # field + an astrological explanation on the traces" request) ─────────
    # *_audit.json previously dumped the engine's raw internal per-field
    # result row verbatim -- ~50 top-level keys, most of it scoring-audit
    # bookkeeping (signal_provenance alone has 143 keys) with no
    # astrological content. Replaced with, per field: (1) a compact
    # astrological_trace pulled from the SAME row (karakas, dasha lords,
    # per-planet sign/house/nakshatra/dignity/strength, the named classical
    # techniques that actually moved the score, D10 archetypes, KP status,
    # evidence) -- see astro_trace.py::build_field_trace -- and (2) an
    # astrological_explanation grounded in that trace, generated by the LLM
    # when --llm + consent are available (same gate as the narrative step
    # above); null otherwise rather than silently omitted. Same best-effort
    # fallback pattern as Summary/Reference above.
    try:
        from Field_Determination.astro_trace import build_astro_trace_export
        from Field_Determination.jyotish.engine_io import _load_course_registry
        astro_trace_export = build_astro_trace_export(
            results, payload, _load_course_registry(),
            enable_llm=bool(getattr(args, "llm", False)),
            llm_max_retries=2,
        )
        with open(paths["Audit"], "w", encoding="utf-8") as _af:
            json.dump(astro_trace_export, _af, indent=4, ensure_ascii=False, default=str)
        print(f"\nAudit JSON payload saved to: {paths['Audit']}")
        if not astro_trace_export.get("llm_explanations_generated"):
            _debug_reason = astro_trace_export.get("llm_explanations_debug_reason")
            print(
                f"[AUDIT DIAGNOSTIC] astrological_explanation is null for every field. "
                f"Reason: {_debug_reason or '(no reason captured)'}",
                file=_real_stdout,
            )
            _trace_errors = getattr(payload, "llm_trace_explain_last_errors", None) or []
            if _trace_errors:
                print("[AUDIT DIAGNOSTIC] Actual per-attempt failure reasons:", file=_real_stdout)
                for _terr in _trace_errors:
                    print(f"[AUDIT DIAGNOSTIC]   - {_terr}", file=_real_stdout)
            else:
                print(
                    "[AUDIT DIAGNOSTIC] No per-attempt error detail captured on payload "
                    "(llm_trace_explain_last_errors empty/missing).",
                    file=_real_stdout,
                )
    except Exception as _astro_trace_exc:
        import traceback; traceback.print_exc()
        with open(paths["Audit"], "w", encoding="utf-8") as _af_fallback:
            json.dump(_raw_debug_data["Audit"], _af_fallback, indent=4, ensure_ascii=False)
        print(
            f"\nAstrological trace/audit JSON generation failed ({_astro_trace_exc}); "
            f"Audit JSON payload saved to: {paths['Audit']} (per-field fallback content)"
        )

    # ── Simplified 2-tab HTML summary report (executive summary + top-20
    # fields with collapsible astrological explanations) ──────────────────
    # Built directly from the same three in-memory dicts just assembled
    # above for the Summary/Reference/Audit JSON files (route_map_summary,
    # cluster_field_export, astro_trace_export) -- no JSON round-trip.
    # Mirrors export_html_full_trace()'s call pattern (~line 763 above);
    # best-effort like the three JSON blocks above, so a failure here never
    # blocks the rest of the run.
    try:
        _simple_summary_path = ExplainabilityEngine.export_html_simple_summary(
            locals().get("route_map_summary", {}),
            locals().get("cluster_field_export", {}),
            locals().get("astro_trace_export", {}),
            student_name=getattr(payload, "name", None) or "Native",
            output_dir=out_dir,
        )
        print(f"Simple summary report (Executive Summary + Top 20 Fields): {_simple_summary_path}")
    except Exception as _simple_summary_exc:
        import traceback; traceback.print_exc()
        print(f"\nSimple summary report generation failed: {_simple_summary_exc}")

    for _label, _path in paths.items():
        if _label in ("Summary", "Reference", "Audit"):
            continue
        print(f"\n{_label} JSON payload saved to: {_path}")
    
