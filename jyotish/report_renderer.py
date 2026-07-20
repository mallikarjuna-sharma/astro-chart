"""jyotish/report_renderer.py

Phase 4 of the career-report refactor: renders the new Jinja2-templated
career report from a raw engine/timeline payload, using view_model.py +
narrative_composer.py to populate the template.

This is additive — it does not replace jyotish/web_report.py, which remains
the legacy fallback renderer (see career_field_report_v2.generate_career_field_report_v2
for the old/new cutover switch).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .payload import ENGINE_VERSION
from .view_model import build_report_view_model
from .narrative_composer import (
    compose_reader_narrative,
    compose_astrological_basis,
    build_evidence_ladder,
    build_action_plan,
)

import logging
logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
_STATIC_CSS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "career_report.css")


def _get_env() -> Environment:
    if not os.path.isdir(_TEMPLATE_DIR):
        raise RuntimeError(f"Template directory not found: {_TEMPLATE_DIR}")

    template_path = os.path.join(_TEMPLATE_DIR, "career_report.html.j2")
    if not os.path.exists(template_path):
        raise RuntimeError(f"career_report.html.j2 not found: {template_path}")

    if os.path.getsize(template_path) == 0:
        raise RuntimeError(f"career_report.html.j2 is empty: {template_path}")

    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
    )


def _load_css() -> str:
    try:
        with open(_STATIC_CSS_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def render_career_report(raw_json: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """Build the view model from `raw_json` and render the new career report
    HTML. Returns the rendered HTML string; also writes it to `output_path`
    if provided.

    `raw_json` is expected to carry (all optional, defensively handled):
      raw_json["context"]   -> parse_career_context() output
      raw_json["chart"]     -> natal/varga/KP/Jaimini/transit fields
      raw_json["periods"]   -> list of timeline antardasha period dicts
      raw_json["confidence"]-> compute_confidence_tier() output
      raw_json["roadmap_narratives"] -> {year: {"narrative_html", "astro_explanation_html"}}
        from jyotish.llm_narrative_builder.generate_annual_roadmap_narratives(),
        reused directly per period rather than regenerated.
    """
    vm = build_report_view_model(raw_json)
    roadmap_narratives = raw_json.get("roadmap_narratives") or {}
    chart = raw_json.get("chart", {}) or {}

    for period in vm["periods"]:
        year_key = None
        if period.year_label:
            try:
                year_key = int(period.year_label[:4])
            except ValueError:
                year_key = None
        roadmap_entry = roadmap_narratives.get(year_key) if year_key is not None else None

        period.parent_narrative_html = compose_reader_narrative(period, "parent", roadmap_entry)
        period.student_narrative_html = compose_reader_narrative(period, "student", roadmap_entry)

        basis = compose_astrological_basis(period, chart, roadmap_entry)
        period.kp_basis_html = basis["kp_basis_html"]
        period.d10_basis_html = basis["d10_basis_html"]
        period.jaimini_basis_html = basis["jaimini_basis_html"]
        period.transit_basis_html = basis["transit_basis_html"]
        period.astrological_basis_html = basis["astrological_basis_html"]

        period.evidence_chips = build_evidence_ladder(period, chart)
        period.action_plan = build_action_plan(period, chart)

    env = _get_env()
    template = env.get_template("career_report.html.j2")
    html = template.render(
    periods=vm["periods"],
    sidebar=vm["sidebar"],
    context=vm["context"],
    chart=vm["chart"],
    css=_load_css(),
    generated_at=datetime.now().strftime("%d %b %Y, %H:%M"),
    engine_version=ENGINE_VERSION,
)

    if not html or not str(html).strip():
        raise RuntimeError(
            "report_renderer.render_career_report produced empty HTML. "
            "Check templates/career_report.html.j2 and view_model periods."
        )

    if "<body" not in html.lower() and "<html" not in html.lower():
        raise RuntimeError(
            "report_renderer.render_career_report produced invalid HTML without <html>/<body>."
        )

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)

    return html
