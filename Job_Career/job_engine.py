#!/usr/bin/env python3
# Load .env before any jyotish imports so OPENAI_API_KEY is visible to llm.py.
# Works without python-dotenv — pure stdlib fallback. (Mirrors the header in
# field_deterministic_engine_v1_llm.py so this file works standalone too.)
import os as _os, pathlib as _pathlib, re as _re

# See field_deterministic_engine_v1_llm.py's header for the full rationale:
# on Windows, redirecting/piping stdout makes Python fall back to 'cp1252',
# and a stray Unicode debug-banner char (═, ─, —, ...) then raises
# UnicodeEncodeError and kills the run before it reaches HTML generation.
# Force UTF-8 stdout/stderr with a safe error handler up front.
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

# This file lives in Job_Career/, one level below the repo root. Add the
# repo root to sys.path so `jyotish` and `Job_Career` remain importable
# however this file ends up being invoked (direct script run, -m, etc.).
_repo_root = _pathlib.Path(__file__).resolve().parent.parent
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

_env_path = _repo_root / ".env"
if _env_path.exists():
    # Matches: KEY = "VALUE" # comment
    _env_regex = _re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(["\']?)(.*?)\2\s*(?:#.*)?$')
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _match = _env_regex.match(_line)
        if _match:
            _k, _, _v = _match.groups()
            if _k not in _os.environ:
                _os.environ[_k] = _v

"""
Job_Career/job_engine.py — Career Timeline CLI entry point.

This is the moved, standalone home of what used to be:

    python field_deterministic_engine_v1_llm.py <chart.json> --mode career

All logic for that command now lives here: chart loading, payload parsing
(with the career timeline built), and generating the Career Timeline HTML
report (delegated to Job_Career.career_mode_runner.run_career_mode, which
also drives the LLM_REPORT_CONSENT gate and the job_debug.json dump).

Usage:
    python Job_Career/job_engine.py charts/lakshman_chart_details.json --mode career
    python Job_Career/job_engine.py charts/lakshman_chart_details.json --out my_reports

field_deterministic_engine_v1_llm.py's own `--mode career` / `--mode both`
branch now just calls run_career_engine() below instead of duplicating this
logic.
"""

import json


def run_career_engine(chart_path: str, out_dir: str = "educational_records", payload=None):
    """Run the Career Timeline pipeline for `chart_path` and write the HTML report.

    Parameters
    ----------
    chart_path : path to the chart JSON file.
    out_dir    : output directory for the generated HTML/JSON artifacts.
    payload    : optional already-parsed NatalPayloadV2 (with career_timeline
                 already built, i.e. parsed via parse_json_payload(...,
                 build_timeline=True)). Callers like field_deterministic_engine_
                 v1_llm.py's `--mode both` branch — which already parsed the
                 payload once for the field-determination half — pass it in
                 here so the chart JSON isn't re-read/re-parsed a second time.
                 If omitted, this function parses the chart itself.

    Returns
    -------
    The parsed/used payload (so callers can inspect payload.career_timeline
    etc. afterward if needed).
    """
    import os as _os
    from jyotish.engine_io import parse_json_payload
    from Job_Career.career_mode_runner import run_career_mode

    if payload is None:
        with open(chart_path, encoding="utf-8") as f:
            raw = json.load(f)
        payload = parse_json_payload(raw, build_timeline=True, chart_path=chart_path)

    _os.makedirs(out_dir, exist_ok=True)

    # run_career_mode() only reads args.chart / args.mode / args.out today,
    # but keep a real argparse.Namespace (not a plain object) so it behaves
    # identically to what the CLI block used to pass.
    import argparse
    args = argparse.Namespace(chart=chart_path, mode="career", out=out_dir)

    run_career_mode(payload, args, out_dir)
    return payload


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="JyotishAI Job/Career Engine — Career Timeline report generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python Job_Career/job_engine.py charts/lakshman_chart_details.json --mode career\n"
            "  python Job_Career/job_engine.py charts/lakshman_chart_details.json --out educational_records\n"
        ),
    )
    ap.add_argument("chart", nargs="?", default="ramsunder_chart_details.json",
                    help="Path to chart JSON file (default: ramsunder_chart_details.json)")
    ap.add_argument("--mode", choices=["career"], default="career",
                    help="Kept for command-line parity with the old CLI. "
                         "This entry point only ever runs the career timeline.")
    ap.add_argument("--out", default="educational_records",
                    help="Output directory for HTML/JSON reports (default: educational_records)")
    args = ap.parse_args()

    run_career_engine(args.chart, args.out)
