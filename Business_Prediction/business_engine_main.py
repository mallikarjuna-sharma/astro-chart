#!/usr/bin/env python3
# Load .env before any jyotish imports so OPENAI_API_KEY/GEMINI_API_KEY/etc.
# are visible to llm.py. Works without python-dotenv -- pure stdlib fallback.
# (Mirrors the header in Job_Career/job_engine.py so this file works
# standalone too.)
import os as _os, pathlib as _pathlib, re as _re

# Same rationale as Job_Career/job_engine.py: on Windows, redirecting/piping
# stdout makes Python fall back to the 'cp1252' codec, and a stray Unicode
# debug-banner character then raises UnicodeEncodeError and kills the run
# before it reaches HTML generation. Force UTF-8 stdout/stderr up front.
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

# This file lives in Business_Prediction/, one level below the repo root.
# Add the repo root to sys.path so `jyotish`, `Job_Career`, and
# `Business_Prediction` remain importable however this file ends up being
# invoked (direct script run, -m, etc.).
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
Business_Prediction/business_engine_main.py -- Business Prediction Analysis
CLI entry point.

Standalone home for `--mode business`, deliberately kept out of
Field_Determination/education_engine.py, the same way Job_Career/job_engine.py
keeps `--mode career` standalone rather than folding it into that file. All
logic for this command lives here: chart loading, payload parsing, and
generating the Business Prediction Analysis HTML report (delegated to
Business_Prediction.business_mode_runner.run_business_mode, which also
drives the business_debug.json dump).

Usage:
    python Business_Prediction/business_engine_main.py charts/lakshman_chart_details.json --mode business
    python Business_Prediction/business_engine_main.py charts/lakshman_chart_details.json --out my_reports
"""

import json


def run_business_engine(chart_path: str, out_dir: str = "educational_records", payload=None,
                        financial_readiness_inputs=None):
    """Run the Business Prediction Analysis pipeline for `chart_path` and
    write the HTML report.

    Parameters
    ----------
    chart_path : path to the chart JSON file.
    out_dir    : output directory for the generated HTML/JSON artifacts.
    payload    : optional already-parsed NatalPayloadV2. If omitted, this
                 function parses the chart itself. Business Prediction does
                 not require build_timeline=True (it builds its own dasha
                 calendar via Job_Career.timeline._dasha_calendar directly),
                 so a plain parse_json_payload() call is enough.

    Returns
    -------
    The parsed/used payload (so callers can inspect it further if needed).
    """
    import os as _os
    from jyotish.engine_io import parse_json_payload
    from Business_Prediction.business_mode_runner import run_business_mode

    if payload is None:
        with open(chart_path, encoding="utf-8") as f:
            raw = json.load(f)
        payload = parse_json_payload(raw, chart_path=chart_path)

    _os.makedirs(out_dir, exist_ok=True)

    # run_business_mode() only reads args.chart / args.mode / args.out today,
    # but keep a real argparse.Namespace (not a plain object) so it behaves
    # identically to what a CLI block would pass -- same convention
    # job_engine.py's run_career_engine() uses.
    import argparse
    args = argparse.Namespace(
        chart=chart_path, mode="business", out=out_dir,
        financial_readiness_inputs=financial_readiness_inputs,
    )

    run_business_mode(payload, args, out_dir)
    return payload


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description=(
            "JyotishAI Business Prediction Analysis Engine -- "
            "architecturally mature and internally validated; real-world "
            "predictive validity has NOT been established (no prospective "
            "labeled outcome corpus evaluated). Outputs are decision-support "
            "narratives for further astrological review, not financial "
            "forecasts. See maturity_statement/maturity_caveats in the "
            "generated business_debug.json for the full statement."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python Business_Prediction/business_engine_main.py charts/lakshman_chart_details.json --mode business\n"
            "  python Business_Prediction/business_engine_main.py charts/lakshman_chart_details.json --out educational_records\n"
        ),
    )
    ap.add_argument("chart", nargs="?", default="ramsunder_chart_details.json",
                    help="Path to chart JSON file (default: ramsunder_chart_details.json)")
    ap.add_argument("--mode", choices=["business"], default="business",
                    help="Kept for command-line parity with the other engine entry points. "
                         "This entry point only ever runs the business prediction analysis.")
    ap.add_argument("--out", default="educational_records",
                    help="Output directory for HTML/JSON reports (default: educational_records)")
    ap.add_argument("--financial-readiness-json", default=None,
                    help="Path to independently reviewed financial-readiness evidence JSON")
    args = ap.parse_args()

    financial_inputs = None
    if args.financial_readiness_json:
        evidence_path = _pathlib.Path(args.financial_readiness_json).resolve()
        if not evidence_path.is_file():
            ap.error(f"financial readiness JSON not found: {evidence_path}")
        with evidence_path.open("r", encoding="utf-8") as fh:
            financial_inputs = json.load(fh)
        if not isinstance(financial_inputs, dict):
            ap.error("financial readiness JSON must contain an object")

    run_business_engine(args.chart, args.out, financial_readiness_inputs=financial_inputs)
