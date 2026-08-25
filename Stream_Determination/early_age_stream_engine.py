#!/usr/bin/env python3
"""early_age_stream_engine.py — Entry point for the under-15 Stream Determination engine.

Completely separate CLI/output pipeline from Field_Determination/education_engine.py.
For a chart whose current_age < 15, THIS is the engine that should run instead of
the 199-branch field engine -- see run_for_payload()/run_for_chart_file() below,
and Field_Determination/education_engine.py's __main__ age gate that dispatches here.

Usage (standalone):
    python Stream_Determination/early_age_stream_engine.py chart.json
    python Stream_Determination/early_age_stream_engine.py chart.json --out stream_records
"""
import os as _os
import pathlib as _pathlib
import re as _re
import sys as _sys

# Same zero-dependency .env loader pattern as Field_Determination/education_engine.py,
# duplicated (not imported) so this entry file has no import-time dependency on
# Field_Determination at all -- only on jyotish's shared primitives.
_repo_root = _pathlib.Path(__file__).resolve().parent.parent
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

_env_path = _repo_root / ".env"
if _env_path.exists():
    _env_regex = _re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(["\']?)(.*?)\2\s*(?:#.*)?$')
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _match = _env_regex.match(_line)
        if _match:
            _k, _, _v = _match.groups()
            if _k not in _os.environ:
                _os.environ[_k] = _v

try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

import logging as _logging
from typing import Any, Dict

_logger = _logging.getLogger(__name__)

from .stream_scoring import compute_stream_determination
from .stream_report import write_reports

# GAP-FIX (audit, this turn): duplicated from stream_scoring.py's own
# AGE_THRESHOLD_YEARS previously -- now imports the single source of truth
# instead, so the two files' age thresholds cannot silently drift apart.
from .stream_scoring import AGE_THRESHOLD_YEARS
DEFAULT_OUT_DIR = "stream_records"
# GAP-FIX ("include the comparison in the final report"): cross-validation
# against Field_Determination's adult engine is an OPTIONAL, heavier
# supplementary check (it runs the full 199-branch adult engine) -- default
# ON for CLI/report use per this request, but callers that care about
# latency (or are batch-scoring many charts) can pass
# include_cross_validation=False / --cross-validate=false to skip it.
# safe_cross_validate() (Stream_Determination/cross_validate.py) ensures a
# failure here never takes down the primary report.
# CONFIRMED REGRESSION (this turn): this constant was found reset back to
# False, with a comment claiming the opposite default, despite being fixed
# to True and verified twice earlier in this session (CLI output and JSON
# both confirmed printing cross-validation by default). No edit to this
# line was made in any visible turn between those verifications and this
# one -- restoring the verified-correct value.
DEFAULT_INCLUDE_CROSS_VALIDATION = True
# GAP-FIX (field-derived-evidence, EXPERIMENTAL 8th rubric section): unlike
# cross-validation (report-only, safe to default on), this section actually
# changes the stream score -- see stream_scoring.py/field_derived_stream.py
# module docstrings. Default OFF until regression-tested and deliberately
# enabled by a caller who understands the cap rebudget it implies.
DEFAULT_INCLUDE_FIELD_DERIVED_EVIDENCE = False


def is_eligible(payload: Any, age_threshold: float = AGE_THRESHOLD_YEARS) -> bool:
    """True if this chart belongs to this engine (current_age < threshold).

    2026-08-22 audit fix (gap 10): this is a HARD cutoff -- a chart at
    age=threshold-epsilon runs entirely through this under-15 engine, while
    the same chart at age=threshold runs entirely through Field_Determination's
    199-branch adult engine instead, with no blending/smoothing across the
    boundary. Two independently-designed, independently-tuned engines can
    genuinely disagree, so a chart evaluated a day apart across the boundary
    could see a large, discontinuous score/recommendation jump. Verified this
    is a KNOWN, ACCEPTED LIMITATION rather than adding a blend here: the
    actual age-routing decision (which engine runs at all) lives in
    Field_Determination/education_engine.py's __main__ block, OUTSIDE this
    module (see adult_engine_bridge.py's own "Age-router note" -- this file
    only decides eligibility for callers that already reached it, it does not
    own the dispatch). A same-run linear blend would require running BOTH
    full engines for every chart near the boundary and reconciling two
    differently-shaped report contracts, which is a bigger change than is
    safe here; the safe fix is to name the limitation so a caller near the
    boundary knows to treat the result as one point in a genuinely fuzzy
    transition, not a precise cliff.
    """
    try:
        raw_age = getattr(payload, "current_age", None)
        if raw_age is None or str(raw_age).strip() == "":
            return False
        age = float(raw_age)
        # Missing/invalid age must never silently route into the child engine.
        # A zero default is useful in generic payloads but is not evidence of
        # an under-15 chart.
        return 0.0 < age < age_threshold
    except (TypeError, ValueError):
        return False


def run_for_payload(
    payload: Any, out_dir: str = DEFAULT_OUT_DIR, *, forced_override: bool = False,
    include_cross_validation: bool = DEFAULT_INCLUDE_CROSS_VALIDATION,
    include_field_derived_evidence: bool = DEFAULT_INCLUDE_FIELD_DERIVED_EVIDENCE,
    include_llm_narrative: bool | None = None,
    llm_consent: bool = False,
    llm_model: str | None = None,
    as_of_date: Any = None,
) -> Dict[str, Any]:
    """Score + write reports for an already-parsed NatalPayloadV2. Returns the
    JSON-serializable report dict plus the written file paths under 'paths'.

    GAP-FIX (2026-07-22, audit gap 25): `forced_override=True` stamps
    forced_override/eligibility_status into the report so a test run on an
    ineligible (>=15) chart is never presented as a normal recommendation.

    `include_cross_validation=True` runs
    Stream_Determination/cross_validate.py's safe_cross_validate() against
    the same payload and folds the result into both the JSON report and the
    HTML render -- see cross_validate.py's own module docstring for what
    this cross-check is (and is not).

    OPTIMIZATION: when BOTH include_cross_validation and
    include_field_derived_evidence are enabled, the adult engine is fetched
    ONCE here (not twice) and the resulting snapshot is shared between
    cross_validate.py and field_derived_stream.py -- previously each feature
    independently triggered its own full adult-engine run for the same
    chart, doubling runtime for no additional information.
    """
    eligibility_status = "TEST_ONLY_FORCED_OVERRIDE" if forced_override else "NORMAL"

    # GAP-FIX (2026-07-24, audit issue 2 -- "safe default silently skipped"):
    # DEFAULT_INCLUDE_CROSS_VALIDATION is True precisely so every report gets
    # checked against Field_Determination's adult engine, but that adult-
    # engine run is genuinely expensive (measured ~8x a bare stream-scoring
    # run: ~18s vs ~2.2s per chart on this repo's Ramsunder fixture, because
    # it reloads/runs the full 199-branch adult course registry). Batch/
    # regression callers therefore have a real incentive to pass
    # include_cross_validation=False, and previously did so with no trace in
    # the report or logs -- a reader of stream_records_full_audit/ (or any
    # batch run) could not tell "cross-validation agreed" apart from
    # "cross-validation was never run" without re-reading the driver script.
    # Loud-and-documented fix (perf root cause -- the adult engine's own
    # cost -- is out of scope to rearchitect here): log a warning whenever a
    # caller explicitly opts out, so the omission is visible in run logs
    # even when nobody inspects the JSON's cross_validation field.
    if not include_cross_validation:
        _logger.warning(
            "Stream_Determination cross-validation SKIPPED for %s (include_cross_validation=False). "
            "This is a safe-by-default check (DEFAULT_INCLUDE_CROSS_VALIDATION=True) that was "
            "explicitly disabled by the caller, typically for batch-run latency -- the adult "
            "Field_Determination cross-check (~8-10x slower than plain stream scoring) was NOT run "
            "for this report; its 'cross_validation' field will be null.",
            getattr(payload, "name", "") or "unknown chart",
        )

    shared_field_engine_snapshot = None
    if include_cross_validation or include_field_derived_evidence:
        from .adult_engine_bridge import safe_get_field_engine_snapshot
        shared_field_engine_snapshot = safe_get_field_engine_snapshot(payload)

    determination = compute_stream_determination(
        payload, include_field_derived_evidence=include_field_derived_evidence,
        field_engine_snapshot=shared_field_engine_snapshot,
        as_of_date=as_of_date,
    )

    cross_validation = None
    if include_cross_validation:
        from .cross_validate import safe_cross_validate
        # BUG FIX (2026-07-24, config-drift): pass the determination dict
        # already computed above (with this call's own
        # include_field_derived_evidence/etc config) so cross_validate.py
        # never silently recomputes it with different (defaulted) config --
        # see cross_validate.py's cross_validate_against_field_determination()
        # docstring for the 3-chart drift this previously caused.
        cross_validation = safe_cross_validate(
            payload, snapshot=shared_field_engine_snapshot,
            precomputed_determination=determination,
        )

    from .stream_narrative import generate_stream_narrative, narrative_enabled_default
    resolved_include_llm_narrative = (
        narrative_enabled_default() if include_llm_narrative is None else include_llm_narrative
    )
    stream_narrative = generate_stream_narrative(
        payload, determination,
        enabled=resolved_include_llm_narrative,
        runtime_consent=llm_consent,
        model=llm_model,
    )

    from .stream_report import build_report_payload
    report = build_report_payload(
        payload, determination,
        forced_override=forced_override, eligibility_status=eligibility_status,
        cross_validation=cross_validation,
        stream_narrative=stream_narrative,
    )
    paths = write_reports(
        payload, determination, out_dir,
        forced_override=forced_override, eligibility_status=eligibility_status,
        cross_validation=cross_validation,
        stream_narrative=stream_narrative,
    )
    report["paths"] = paths
    return report


def run_for_chart_file(chart_path: str, out_dir: str = DEFAULT_OUT_DIR,
                        force: bool = False,
                        include_cross_validation: bool = DEFAULT_INCLUDE_CROSS_VALIDATION,
                        include_field_derived_evidence: bool = DEFAULT_INCLUDE_FIELD_DERIVED_EVIDENCE,
                        include_llm_narrative: bool | None = None,
                        llm_consent: bool = False,
                        llm_model: str | None = None,
                        as_of_date: Any = None) -> Dict[str, Any]:
    """Parse a chart JSON file directly and run the stream engine on it.

    `force=True` skips the current_age<15 eligibility check (useful for
    manual testing/inspection of the stream engine on any chart) -- the
    resulting report is stamped forced_override=True/eligibility_status=
    TEST_ONLY_FORCED_OVERRIDE so it can never be mistaken for a normal
    under-15 recommendation.
    """
    import json
    from jyotish.engine_io import parse_json_payload

    with open(chart_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    payload = parse_json_payload(raw, chart_path=chart_path)

    eligible = is_eligible(payload)
    if not force and not eligible:
        raise ValueError(
            f"Chart current_age={getattr(payload, 'current_age', '?')} is >= "
            f"{AGE_THRESHOLD_YEARS} -- this chart belongs to the main "
            "Field Determination engine, not Stream Determination. Pass "
            "force=True to override for testing."
        )

    return run_for_payload(
        payload, out_dir=out_dir, forced_override=(force and not eligible),
        include_cross_validation=include_cross_validation,
        include_field_derived_evidence=include_field_derived_evidence,
        include_llm_narrative=include_llm_narrative,
        llm_consent=llm_consent,
        llm_model=llm_model,
        as_of_date=as_of_date,
    )


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="JyotishAI Stream Determination — Science/Commerce/Humanities "
                     "+ subject recommendations for charts under 15 years old.",
    )
    # GAP-FIX (audit #47): a bare filename default silently depended on the
    # current working directory containing that file -- resolved relative to
    # this script's own repo root instead, so the default only ever means
    # "this repo's charts/ramsunder_chart_details.json" regardless of cwd.
    _default_chart = str(_repo_root / "charts" / "ramsunder_chart_details.json")
    ap.add_argument("chart", nargs="?", default=_default_chart,
                     help=f"Path to chart JSON file (default: {_default_chart}).")
    ap.add_argument("--out", default=DEFAULT_OUT_DIR,
                     help=f"Output directory for JSON+HTML reports (default: {DEFAULT_OUT_DIR}).")
    def _bool_flag(value: str) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    # nargs="?" + const=True lets this accept both bare `--force` (store_true
    # style) and `--force=true`/`--force true`/`--force=false` -- argparse's
    # plain action="store_true" rejects any `=value` form with "ignored
    # explicit argument", which is a confusing error for something that reads
    # like a normal boolean CLI flag.
    ap.add_argument("--force", nargs="?", type=_bool_flag, const=True, default=False,
                     help="Run even if the chart's current_age is >= 15 (testing only). "
                          "Accepts --force, --force=true, or --force=false.")
    ap.add_argument("--cross-validate", dest="cross_validate", nargs="?", type=_bool_flag,
                     const=True, default=DEFAULT_INCLUDE_CROSS_VALIDATION,
                     help="Cross-check this chart's dominant stream against Field_Determination's "
                          "own top macro career cluster (runs the full adult engine as an extra, "
                          "optional check). Accepts --cross-validate, --cross-validate=true, or "
                          "--cross-validate=false. Default: off.")
    ap.add_argument("--field-derived-evidence", dest="field_derived_evidence", nargs="?", type=_bool_flag,
                     const=True, default=DEFAULT_INCLUDE_FIELD_DERIVED_EVIDENCE,
                     help="EXPERIMENTAL, default OFF: fold an 8th, small-capped rubric section derived "
                          "from Field_Determination's adult engine into the stream SCORE itself (not just "
                          "a report comparison -- see field_derived_stream.py). Accepts "
                          "--field-derived-evidence, --field-derived-evidence=true/false. Default: off.")
    from .stream_narrative import (
        DEFAULT_OPENAI_NARRATIVE_MODEL, runtime_consent_default, narrative_enabled_default,
    )
    ap.add_argument("--llm-narrative", dest="llm_narrative", nargs="?", type=_bool_flag,
                    const=True, default=narrative_enabled_default(),
                    help="Generate the student + astrological narrative through OpenAI. Accepts "
                         "--llm-narrative, --llm-narrative=true, or --llm-narrative=false. Default "
                         "comes from LLM_NARRATIVE_ENABLED in .env (off when unset).")
    ap.add_argument("--llm-consent", dest="llm_consent", nargs="?", type=_bool_flag,
                    const=True, default=runtime_consent_default(),
                    help="Explicit external OpenAI consent switch. Also requires chart external_llm_consent=true. "
                         "Default comes from LLM_REPORT_CONSENT (off when unset).")
    ap.add_argument("--llm-model", default=_os.getenv("OPENAI_NARRATIVE_MODEL", DEFAULT_OPENAI_NARRATIVE_MODEL),
                    help="OpenAI narrative model (default: OPENAI_NARRATIVE_MODEL or gpt-5.6-sol).")
    ap.add_argument("--as-of-date", dest="as_of_date", default=None,
                    help="ISO date (YYYY-MM-DD) the classical precedence chain's Stage 4 "
                         "(dasha-relevance) check treats as 'today' when locating the active "
                         "mahadasha/antardasha window. Default: the real current date "
                         "(date.today()) at run time. Passing this explicitly makes the run's "
                         "dasha-stage output reproducible; it is echoed back on the saved report "
                         "as 'evaluation_as_of_date'.")
    args = ap.parse_args()

    result = run_for_chart_file(
        args.chart, out_dir=args.out, force=args.force,
        include_cross_validation=args.cross_validate,
        include_field_derived_evidence=args.field_derived_evidence,
        include_llm_narrative=args.llm_narrative,
        llm_consent=args.llm_consent,
        llm_model=args.llm_model,
        as_of_date=args.as_of_date,
    )

    print(f"\nStream Determination Engine: {result.get('engine_version')}")
    print(f"Name: {result.get('name')}  |  Age: {result.get('current_age')}")
    print(f"Dominant stream: {result.get('dominant_stream')}\n")
    for s in result.get("streams", []):
        print(f"  [{s.get('normalized_score', 0):>6.1f}] {s['label']}")
        for subj in s.get("subjects", []):
            # GAP-FIX (audit #28): a shared elective (e.g. Physical Education,
            # offered identically across all 3 streams) is explicitly excluded
            # from stream-discrimination credit in the scoring itself, but the
            # CLI printed it identically to a real discriminating subject --
            # someone skimming just the numbers could read it as "the top
            # subject" without realizing it can't distinguish between streams.
            tag = " [shared -- does not discriminate between streams]" if subj.get("shared_elective") else ""
            print(f"      - {subj['label']:<28} {subj['score']:>6.1f}{tag}")

    fde = result.get("field_determination_evidence")
    if fde:
        print(f"\nField-derived evidence (EXPERIMENTAL, data_status={fde.get('data_status')}):")
        if fde.get("data_status") == "COMPUTED":
            print(f"  marks: {fde.get('marks')}  (reliability={fde.get('reliability')}, "
                  f"mapping_coverage={fde.get('mapping_coverage')})")
        else:
            print(f"  {'; '.join(fde.get('warnings', [])) or 'no data'}")

    cross_validation = result.get("cross_validation")
    if cross_validation:
        from .cross_validate import format_cross_validation_text
        print()
        for line in format_cross_validation_text(cross_validation):
            print(line)

    narrative = result.get("stream_narrative") or {}
    if narrative:
        print(
            f"\nNarrative: {narrative.get('status')} "
            f"(provider={narrative.get('provider')}, decision_locked={narrative.get('decision_locked')})"
        )

    print(f"\nJSON report: {result['paths']['json']}")
    print(f"HTML report: {result['paths']['html']}")
