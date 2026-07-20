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
from jyotish.report_utils import (
    field_display_name as _field_display_name,
    print_macro_cluster as _print_macro_cluster,
    cluster_display_name as _cluster_display_name,
    top20_as_four_cluster_groups as _top20_as_four_cluster_groups,
)

from jyotish.payload    import NatalPayloadV2, ENGINE_VERSION, logger
from jyotish.constants  import (
    _KENDRA_HOUSES, _TRIKONA_HOUSES, _KT_HOUSES, _DUSTHANA_HOUSES,
    _SIGN_NUM, _SIGN_LORD, _COMBUST_ORB, _NODAL_DEFAULT_VIRUPAS,
    _PLANET_MIN_SHADBALA, _NAKSHATRA_LORD, _NEECHA_BHANGA_DATA,
    DOMAIN_STRATEGIES, _VALID_PLANETS, _VALID_DOMAINS,
    _MAHESHWARA_DOMAIN_KW, _STREAM_MAP,
)
from jyotish.astro      import (
    compute_dignity, _planet_abs_degree, _compute_whole_sign_houses,
    get_nakshatra_from_longitude, _drishti_bala,
    _get_planetary_aspects, _get_planetary_aspects_weighted,
    _detect_neecha_bhanga, _detect_yogas, _detect_planetary_war,
    _get_nakshatra_dignity, _compute_eff_strengths,
    _is_vargottama, _detect_combust_planets, _calc_age,
    _get_active_dasha_lord,
)
from jyotish.affinity   import BRANCH_PLANET_AFFINITY, compute_branch_affinity_score_llm
from jyotish.engine_io  import parse_json_payload, compute_aptitude_by_domain, _load_course_registry
from jyotish.llm        import (
    _build_chart_summary_for_llm, call_llm_for_fields,
)
from jyotish.boosts     import *
from jyotish.engine     import run_engine, execute_qa_verification_v8_9, classify_age_stage
from jyotish.output     import ExplainabilityEngine
# Prashna (Horary, P-6) logic has moved entirely to
# Field_Determination/prashnam_determination.py — see run_prashna_mode(),
# invoked lazily from the `--mode prashna` CLI branch below.
from jyotish.edu_align import (        # EduAlign: Education stream + exam scoring
    compute_d1_d24_stream_score,
    compute_sub_branch_compatibility,
    rank_sub_branches,
    compute_exam_day_scores,
)

__all__ = [
    "NatalPayloadV2", "ENGINE_VERSION", "BRANCH_PLANET_AFFINITY",
    "parse_json_payload", "run_engine", "ExplainabilityEngine",
    "compute_branch_affinity_score_llm", "call_llm_for_fields",
    "classify_age_stage", "execute_qa_verification_v8_9",
    # Prashna (Horary) — moved to Field_Determination.prashnam_determination
    # EduAlign
    "compute_d1_d24_stream_score", "compute_sub_branch_compatibility",
    "rank_sub_branches", "compute_exam_day_scores",
]


# ── Cluster-strength weighting (Gap fixes 2026-07-08) ────────────────────────
# The old cluster strength was a plain sum of (21-rank)*score over ALL members,
# which let a cluster win on breadth: 5-7 normalization-floor tail fields
# (scores 44.0x, 0.01 apart) outvoted a single rank-1 field at 99+. Fixes:
#   1. Floor exclusion — fields scoring < _CLUSTER_FLOOR_RATIO of the top-1
#      score do not vote (removes the epsilon tie-break tail + registry
#      composition bias: registries with many engineering branches no longer
#      auto-inflate the engineering cluster).
#   2. Member cap — only a cluster's best _CLUSTER_MEMBER_CAP members vote,
#      so cluster identity is decided by its strongest evidence, not its size.
#   3. Exponential rank decay — 0.8^(rank-1) instead of the near-flat linear
#      (21-rank) weight, so rank 1 actually dominates rank 15.

_CLUSTER_RANK_DECAY  = 0.8   # weight multiplier per rank position
_CLUSTER_MEMBER_CAP  = 3     # only a cluster's best N members vote
_CLUSTER_FLOOR_RATIO = 0.5   # fields below 50% of the top-1 score don't vote


def _cluster_strength_weighted(rank_row_pairs, top_score):
    """Weighted cluster strength from (rank, result_row) pairs. See notes above."""
    votes = []
    for rank, row in rank_row_pairs:
        score = float(row.get("final_score", 0.0) or 0.0)
        if top_score > 0 and score < top_score * _CLUSTER_FLOOR_RATIO:
            continue  # normalization-floor tail — not real evidence
        votes.append((_CLUSTER_RANK_DECAY ** (rank - 1)) * score)
    votes.sort(reverse=True)
    return sum(votes[:_CLUSTER_MEMBER_CAP])


def _top20_as_four_cluster_groups(results):
    """Return up to four display groups covering every branch in results[:20]."""
    grouped = {}
    order = []
    for rank, row in enumerate(results[:20], 1):
        cluster = _print_macro_cluster(row)
        if cluster not in grouped:
            grouped[cluster] = []
            order.append(cluster)
        grouped[cluster].append((rank, row))

    top_score = float(results[0].get("final_score", 0.0) or 0.0) if results else 0.0
    ranked_groups = sorted(
        [(cluster, grouped[cluster]) for cluster in order],
        key=lambda item: (
            -_cluster_strength_weighted(item[1], top_score),
            min(rank for rank, _ in item[1]),  # tie-break: best member rank
        ),
    )

    if len(ranked_groups) <= 4:
        return ranked_groups

    groups = ranked_groups[:3]
    remainder = []
    for _, rows in ranked_groups[3:]:
        remainder.extend(rows)
    remainder.sort(key=lambda item: item[0])
    groups.append(("Additional Top-20 Branches", remainder))
    return groups


def _field_display_name(row):
    return row.get("field_label") or row.get("field_id", "Unknown").replace("_", " ").title()


def _print_macro_cluster(row):
    fid = row.get("field_id", "")
    family = (row.get("career_family_label") or row.get("career_family") or "").lower()
    label = _field_display_name(row).lower()
    domain = (row.get("domain") or "").lower()

    if fid in {
        "international_law", "civil_services", "public_policy", "international_relations",
        "political_science", "law_llb", "environmental_law", "corporate_law",
        "criminal_law", "intellectual_property_law",
    } or "law" in label or "governance" in label or "civil service" in label or "diplomacy" in label:
        # FIX (2026-07-08): was `"civil" in label`, which wrongly classified
        # "Civil Engineering" as Law/Governance. Only civil SERVICE belongs here.
        return "Law, Governance & Public Leadership"
    if fid in {
        "research_academia", "history_archaeology", "philosophy", "education_teaching",
        "organisational_psychology", "gender_studies", "sociology_anthropology",
        "planetary_science",
    } or "research" in label or "academia" in label or "psychology" in label:
        return "Research, Academia & Knowledge Systems"
    if fid in {
        "medicine_mbbs", "public_health", "healthcare_management", "medical_research",
        "ayurveda", "homeopathy", "unani_medicine", "yoga_naturopathy",
    } or "health" in label or "medicine" in label or "hospital" in label:
        return "Medical, Public Health & Welfare"
    if fid in {
        "economics_data_science", "economics", "computational_finance", "finance_banking",
        "computational_social_science", "econometrics",
    } or domain in {"finance", "economics"}:
        # FIX (2026-07-08): dropped "commerce" from this domain set. Generic
        # commerce fields (B.Com, Real Estate, Business Mgmt) are NOT policy
        # analytics — they now fall through to their engine graph_cluster
        # ("Commerce, Finance & Enterprise" → "Economics, Finance & Enterprise").
        return "Economics, Policy Analytics & Social Sciences"
    if "agri" in family or "agri" in label:
        return "Agriculture, Environment & Sustainability"
    return _cluster_display_name(
        row.get("graph_cluster")
        or row.get("competency_label")
        or row.get("career_family_label")
        or row.get("domain")
        or "Other"
    )


_CLUSTER_DISPLAY_LABELS = {
    "Advanced Engineering & Physical Systems": "Engineering, Space & Physical Systems",
    "Computation, Data & Digital Intelligence": "Economics, Analytics & Digital Intelligence",
    "Medicine, Health & Life Sciences": "Medical, Health & Public Welfare",
    "Governance, Law & Strategic/Defence Institutions": "Law, Governance & Public Leadership",
    "Knowledge, Humanities & Behavioural Sciences": "Research, Academia & Knowledge Systems",
    "Commerce, Finance & Enterprise": "Economics, Finance & Enterprise",
    "Design, Media & Creative Expression": "Design, Media & Creative Expression",
    "Agriculture & Environmental Systems": "Agriculture, Environment & Sustainability",
}


def _cluster_display_name(cluster):
    return _CLUSTER_DISPLAY_LABELS.get(cluster, cluster)


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
        from jyotish.engine import _resolve_career_phase
        career_phase = _resolve_career_phase(payload)
    except Exception:
        career_phase = "auto"
    lines.extend(_best_path_lines(results, career_phase))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse, json, os, sys
    from jyotish.engine_io import parse_json_payload

    ap = argparse.ArgumentParser(
        description="JyotishAI Engine - Field Determination and/or Career Timeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modes:\n"
            "  field   - Run field determination only\n"
            "  career  - Run career timeline only\n"
            "  both    - Run both\n"
            "  prashna - Run Prashna query\n"
            "  edu     - Run EduAlign\n\n"
            "Examples:\n"
            "  python field_deterministic_engine_v1_llm.py chart.json\n"
            "  python field_deterministic_engine_v1_llm.py chart.json --mode career\n"
            "  python field_deterministic_engine_v1_llm.py chart.json --mode field\n"
        ),
    )
    ap.add_argument("chart", nargs="?", default="ramsunder_chart_details.json",
                    help="Path to chart JSON file (default: ramsunder_chart_details.json)")
    ap.add_argument("--mode", choices=["field", "career", "both", "prashna", "edu"], default="field",
                    help="Which report(s) to generate (default: field).")
    ap.add_argument("--exam-dates", default="[]",
                    help='JSON array of exam date dicts, e.g. ''[{"name":"JEE","date":"2025-04-06"}]''')
    ap.add_argument("--question", default="",
                    help="Prashna question text (used with --mode prashna)")
    ap.add_argument("--category", default="career_employment",
                    help="Prashna category (used with --mode prashna). Default: career_employment")
    ap.add_argument("--out", default="educational_records",
                    help="Output directory for HTML reports (default: educational_records)")
    args = ap.parse_args()

    with open(args.chart) as f:
        raw = json.load(f)

    payload = parse_json_payload(raw, build_timeline=args.mode in ("career", "both"), chart_path=args.chart)
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    if args.mode in ("field", "both"):
        from jyotish.engine import run_engine
        from jyotish.astro import _get_active_dasha_lord

        # Keep the printed/top-level field output tied to the deterministic
        # astrological engine. LLM selection can reorder/filter candidates when
        # credentials are present, which makes the console "field output"
        # diverge from the engine's own ranking.
        results = run_engine(payload, enable_llm=False)
        active_lord = _get_active_dasha_lord(
            getattr(payload, "dasha_sequence", []),
            float(getattr(payload, "current_age", 0)),
        )

        print(f"\nEngine: {ENGINE_VERSION}  |  Active Dasha: {active_lord or 'N/A'}")
        print()
        print(_render_top20_cluster_markdown(results, payload))
        from jyotish.validation_contract import UNIVERSAL_DISCLAIMER
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
            cfr_path = generate_career_field_report_v2(
                args.chart, student_name=getattr(payload, "name", None), output_dir=out_dir,
                precomputed_results=results,
            )
            print(f"Career Field Recommendation report: {cfr_path}")
        except Exception as _cfr_e:
            import traceback; traceback.print_exc()
            print(f"\nCareer Field Recommendation report generation failed: {_cfr_e}")

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
        paths = split_debug_payload(safe_results, out_dir, _debug_stem)
        for _label, _path in paths.items():
            print(f"\n{_label} JSON payload saved to: {_path}")
    
    # Career Timeline
    if args.mode in ("career", "both"):
        import json, dataclasses
        from Job_Career.timeline import TimelineChartInput

        # ── Debug: inputs ("prompt") going into build_career_timeline ─────────
        _cc  = getattr(payload, "career_context", {}) or {}
        _chi = TimelineChartInput.from_payload(payload)
        print("\n" + "═"*80)
        print("CAREER TIMELINE INPUT — career_context")
        print("═"*80)
        _redact_debug = bool(getattr(payload, "redact_debug_output", True))
        print(json.dumps(
            {"redacted": True, "keys_present": sorted(_cc.keys())} if _redact_debug else _cc,
            indent=2, ensure_ascii=False, default=str,
        ))
        print("\n" + "─"*80)
        print("CAREER TIMELINE INPUT — TimelineChartInput chart fields")
        print("─"*80)
        print(json.dumps(
            {"redacted": True, "input_contract": type(_chi).__name__}
            if _redact_debug else dataclasses.asdict(_chi),
            indent=2, ensure_ascii=False, default=str,
        ))

        # ── LLM narrative enrichment ──────────────────────────────────────────
        # Phase 0 context (career_theme_str, weight_overrides, intent_tags)
        # is stored on the payload by engine_io after enrich_career_context().
        _llm_ctx       = getattr(payload, "llm_context", {}) or {}
        _career_theme  = _llm_ctx.get("career_theme_str", "")
        # field_selection_context: analytical_breakdown from llm.py Step 1 selector
        # Stored on the payload after run_engine() completes (engine.py wires it).
        _field_ctx     = getattr(payload, "llm_selection_rationale", "") or ""

        _raw_timeline = getattr(payload, "career_timeline", []) or []
        if _raw_timeline:
            try:
                from jyotish.llm_narrative_builder import enrich_timeline_sync
                print(f"\nEnriching {len(_raw_timeline)} AD block(s) with LLM narratives ...")
                _enriched = enrich_timeline_sync(
                    _raw_timeline, _cc, chart_input=_chi,
                    career_theme_str        = _career_theme,
                    field_selection_context = _field_ctx,
                    run_phase2_resolution   = True,
                )
                payload.career_timeline = _enriched
                print("LLM enrichment complete.")
            except Exception as _le:
                import traceback; traceback.print_exc()
                print(f"LLM enrichment failed (deterministic narratives preserved): {_le}")

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
            import traceback; traceback.print_exc()
            print("\nCareer timeline report generation failed: " + str(_e))

        # \u2500\u2500 Debug: enriched Career Timeline JSON \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        timeline = getattr(payload, "career_timeline", []) or []
        if timeline:
            print("\n" + "\u2550"*80)
            print(f"CAREER TIMELINE OUTPUT \u2014 {len(timeline)} period(s) (LLM-enriched where available)")
            print("\u2550"*80)
            for blk in timeline:
                print(json.dumps(blk, indent=2, ensure_ascii=False, default=str))
                print("-"*40)
        else:
            print("\n[Career Timeline] No blocks generated (career_context missing or blocked).")

    # \u2500\u2500 Prashna (Horary) Mode \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    # All logic lives in Field_Determination/prashnam_determination.py now.
    if args.mode == "prashna":
        from Field_Determination.prashnam_determination import run_prashna_mode
        run_prashna_mode(payload, args, out_dir)

    # ── EduAlign Mode ──────────────────────────────────────────────────────────
    if args.mode == "edu":
        import json as _json, datetime as _dt

        # Mapping: edu_align sub-branch key → engine field_id(s) in course registry
        _EDU_TO_ENGINE = {
            "computer_science":        ["computer_science_engineering"],
            "artificial_intelligence": ["artificial_intelligence"],
            "electronics_comm":        ["electronics_communication_engineering"],
            "electrical":              ["electrical_engineering"],
            "mechanical":              ["mechanical_engineering"],
            "civil":                   ["civil_engineering"],
            "chemical":                ["chemical_engineering"],
            "metallurgy":              ["metallurgical_engineering"],
            "materials_science":       ["materials_science_engineering"],
            "aerospace":               ["aerospace_engineering", "aeronautical_engineering"],
            "biomedical":              ["biomedical_engineering"],
            "environmental":           ["environmental_engineering", "environmental_science"],
            "surgery":                 ["medicine_mbbs"],
            "psychiatry":              ["clinical_psychology", "psychology"],
            "pediatrics":              ["medicine_mbbs"],
            "pharmacology":            ["pharmacy"],
            "radiology":               ["radiography_imaging", "medical_physics"],
            "dermatology":             ["medicine_mbbs"],
            "finance":                 ["finance_banking", "actuarial_science"],
            "marketing":               ["digital_marketing", "business_management"],
            "hr_management":           ["business_management"],
            "operations_logistics":    ["supply_chain_logistics", "industrial_engineering"],
            "entrepreneurship":        ["entrepreneurship"],
            "physics":                 ["physics"],
            "mathematics":             ["mathematics", "mathematics_computing"],
            "chemistry":               ["chemistry", "applied_chemistry"],
            "biology":                 ["biological_sciences", "biology"],
            "astronomy":               ["astronomy_astrophysics"],
            "law":                     ["law_llb", "corporate_law"],
            "journalism":              ["journalism_media", "mass_communication"],
            "psychology":              ["psychology", "clinical_psychology"],
            "fine_arts":               ["fine_arts", "design_ux_product"],
            "architecture":            ["architecture"],
            "education_teaching":      ["education_teaching"],
            "sports":                  ["sports_science_management", "physical_education"],
        }

        # Parse exam dates from --exam-dates arg
        try:
            _exam_dates = _json.loads(args.exam_dates)
        except Exception:
            _exam_dates = []

        _eff       = getattr(payload, "eff_strengths", {}) or {}
        _dignities = getattr(payload, "planet_dignities", {}) or {}
        _dasha_seq = getattr(payload, "dasha_sequence", []) or []
        _dob       = getattr(payload, "dob", "") or ""
        _lagna     = getattr(payload, "lagna_sign", "") or ""

        # ── Run 4-system field determination engine ────────────────────────────
        # Use _run_normalization_stage (not run_engine) so we get the full top-35
        # deterministic scores BEFORE LLM filtering. run_engine() only returns
        # the 15-17 LLM-selected fields, which miss most edu sub-branch mappings.
        print("\nRunning 4-system deterministic scoring (KNRao / KP / Jaimini / Parashara) ...")
        _engine_results = []
        _engine_lookup  = {}   # field_id → result dict
        try:
            from jyotish.engine import _run_normalization_stage as _det_stage
            _top35, _eff_eng, _lagna_eng, _ak_eng = _det_stage(payload)
            _engine_results = _top35
            _engine_lookup  = {r.get("field_id", ""): r for r in _engine_results if r.get("field_id")}
            # final_score is already normalised 20-100 by _run_normalization_stage
            _top_eng = max((r.get("final_score", 0) for r in _engine_results), default=1.0) or 1.0
            for _r in _engine_results:
                _r["_norm_pct"] = round(_r.get("final_score", 0) / _top_eng * 100, 1)
            print(f"  Deterministic stage scored {len(_engine_results)} fields (pre-LLM, all methods).")
        except Exception as _ee:
            import traceback; traceback.print_exc()
            print(f"  Field engineering stage failed: {_ee}")
            _engine_results = []

        if not _engine_results:
            print("  No deterministic results -- cannot run EduAlign.")
        else:
            # D1/D24 stream scoring
            print("\nRunning D1/D24 stream scoring ...")
            _stream_scores = compute_d1_d24_stream_score(payload)
            print("  Stream scores:", {k: round(v, 3) for k, v in _stream_scores.items()})

            # Sub-branch compatibility
            print("\nRanking sub-branches ...")
            _sub_ranks = rank_sub_branches(payload, _engine_results, top_n=10)
            print(f"  Top sub-branches ({len(_sub_ranks)}):")
            for _sb in _sub_ranks[:5]:
                print(f"    {_sb.get('sub_branch','?'):<35}  score={_sb.get('score',0):.3f}  "
                      f"engine_field={_sb.get('engine_field_id','-')}")

            # Exam day scoring
            if _exam_dates:
                print(f"\nScoring {len(_exam_dates)} exam date(s) ...")
                _exam_scores = compute_exam_day_scores(payload, _exam_dates)
                for _ex in _exam_scores:
                    print(f"  {_ex.get('name','?'):<20}  date={_ex.get('date','?')}  "
                          f"score={_ex.get('score',0):.3f}  verdict={_ex.get('verdict','?')}")
            else:
                print("\n[Exam dates] None provided (pass --exam-dates JSON to score dates).")

            # Save EduAlign JSON output
            _edu_out = {
                "stream_scores":   _stream_scores,
                "sub_branch_rank": _sub_ranks,
                "exam_scores":     _exam_scores if _exam_dates else [],
            }
            _edu_path = os.path.join(out_dir, f"{payload.name.replace(' ','_')}_edu_align.json")
            with open(_edu_path, "w", encoding="utf-8") as _f:
                import json as _json2
                _json2.dump(_edu_out, _f, indent=2, ensure_ascii=False, default=str)
            print(f"\nEduAlign report saved: {_edu_path}")
