#!/usr/bin/env python3
"""generate_career_field_report.py — CLI wrapper for the 14-section Career
Field Recommendation Report (jyotish/career_field_report_v2.py).

Usage
-----
    python generate_career_field_report.py Charts/ramsunder_chart_details.json
    python generate_career_field_report.py Charts/ramsunder_chart_details.json --name "Ramsunder" --out educational_records

Requires an LLM_PROVIDER + matching API key in .env (GEMINI_API_KEY / ANTHROPIC_API_KEY /
OPENAI_API_KEY) for the narrative sections (identity, astrological signature,
education routes, avoid-list, engine-gap audit, parent/student summaries).
Without a key, the report is still generated with clearly labelled
deterministic placeholder text in those sections.
"""
import argparse
import os as _os
import pathlib
import re as _re
import sys

_repo = pathlib.Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

# Load .env before jyotish imports so GEMINI_API_KEY / ANTHROPIC_API_KEY /
# OPENAI_API_KEY / LLM_PROVIDER are visible to jyotish/llm.py. Zero-dependency
# regex parser (same approach as field_deterministic_engine_v1_llm.py) so this
# script works standalone without requiring python-dotenv.
_env_path = _repo / ".env"
if _env_path.exists():
    _env_regex = _re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(["\']?)(.*?)\2\s*(?:#.*)?$')
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _match = _env_regex.match(_line)
        if _match:
            _k, _, _v = _match.groups()
            if _k not in _os.environ:
                _os.environ[_k] = _v

from Job_Career.career_field_report_v2 import generate_career_field_report_v2


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the 14-section Career Field Recommendation Report.")
    ap.add_argument("chart", help="Path to chart JSON file")
    ap.add_argument("--name", default=None, help="Override student name (default: chart's own name field)")
    ap.add_argument("--out", default="educational_records", help="Output directory (default: educational_records)")
    args = ap.parse_args()

    chart_path = pathlib.Path(args.chart).resolve()
    if not chart_path.exists():
        print(f"ERROR: chart file not found: {chart_path}", file=sys.stderr)
        sys.exit(1)

    out_path = generate_career_field_report_v2(
        str(chart_path), student_name=args.name, output_dir=args.out
    )
    print(f"[JyotishAI] Career Field Recommendation Report written -> {out_path}")


if __name__ == "__main__":
    main()
