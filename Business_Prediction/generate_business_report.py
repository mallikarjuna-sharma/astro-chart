#!/usr/bin/env python3
"""generate_business_report.py — CLI wrapper for the Business Prediction
Analysis report.

Usage
-----
    python -m Business_Prediction.generate_business_report Charts/ramsunder_chart_details.json
    python -m Business_Prediction.generate_business_report Charts/ramsunder_chart_details.json --name "Ramsunder" --out educational_records

Mirrors Job_Career/generate_career_field_report.py's structure: parse the
chart JSON into the shared NatalPayloadV2, run the Business_Prediction
engine, and render a standalone HTML report using the same _esc()/_table()
helper style as career_field_report_v2.py so output looks consistent with
the rest of the engine's reports.
"""
from __future__ import annotations

import argparse
import logging
import os
import pathlib
import re
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

_repo = pathlib.Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

# Load .env before jyotish imports, same zero-dependency approach as the
# other CLI wrappers in this repo (Job_Career/generate_career_field_report.py).
_env_path = _repo / ".env"
if _env_path.exists():
    _env_regex = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(["\']?)(.*?)\2\s*(?:#.*)?$')
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _match = _env_regex.match(_line)
        if _match:
            _k, _, _v = _match.groups()
            if _k not in os.environ:
                os.environ[_k] = _v

import json
import importlib.util as _importlib_util

from jyotish.engine_io import parse_json_payload
from Business_Prediction.business_engine import compute_business_prediction, _load_business_registry
from Business_Prediction.business_determination.muhurta import find_business_muhurta, MAX_SCAN_DAYS
from Business_Prediction.business_determination.ashtakavarga_timing import rank_business_years


def _load_react_report_module():
    """Loads generate_react_report.py by filesystem path rather than a
    normal `import` -- this file is invoked both as a script (`python
    generate_business_report.py chart.json`, cwd-relative) and as part of
    the Business_Prediction package (`from Business_Prediction.generate_business_report
    import ...`), and generate_react_report.py needs to resolve the same
    way in both cases without assuming which one is active. Loading it by
    the path next to this file's own __file__ works unconditionally
    either way. Re-imports fresh each call (this is a CLI report generator
    run once per process, not a hot path) rather than caching in
    sys.modules, so editing generate_react_report.py during development
    doesn't require restarting anything.
    """
    react_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_react_report.py")
    spec = _importlib_util.spec_from_file_location("jyotishai_generate_react_report", react_path)
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _default_business_muhurta_result(
    payload: Any = None,
    event_type: str = "BUSINESS_LAUNCH",
    location: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Computes a sensible default find_business_muhurta() call so both
    report editions can show a real "Muhurta Recommendations" section
    without every caller having to invoke find_business_muhurta()/stitch
    it in manually. Scans from today through today + MAX_SCAN_DAYS - 1 (the
    same cap muhurta.py enforces internally, kept inclusive so the span is
    exactly MAX_SCAN_DAYS days), defaults event_type to "BUSINESS_LAUNCH"
    (overridable by the caller), and passes the same `payload` used for the
    rest of the report through as native_payload so the personal cross-check
    bonus scoring can apply.

    location: this package's payload objects (NatalPayloadV2-shaped, see
    jyotish/engine_io.py and Business_Prediction/tests/test_business_engine.py's
    _FakePayload) do not carry birth lat/lon/tz anywhere in the current
    schema -- there is no "birth_place" or "lat"/"lon" attribute to read.
    Rather than guess a location (which would silently mislocate a real
    chart's Panchang/Rahu Kalam computation), this looks for an explicit
    `lat`/`lon` (optionally `tz_offset_hours`) on the payload object or a
    dict-shaped payload, and otherwise passes location=None straight
    through to find_business_muhurta(), which already degrades this to
    the "NO_LOCATION" diagnostic status (never raises).

    Never raises: any unexpected failure here degrades to the same
    diagnostic-dict contract find_business_muhurta() itself uses, so a
    report can never fail to render because of this helper.
    """
    try:
        if location is None:
            lat = lon = None
            tz_offset = None
            if isinstance(payload, dict):
                lat = payload.get("lat")
                lon = payload.get("lon")
                tz_offset = payload.get("tz_offset_hours")
            else:
                lat = getattr(payload, "lat", None)
                lon = getattr(payload, "lon", None)
                tz_offset = getattr(payload, "tz_offset_hours", None)
            if lat is not None and lon is not None:
                location = {"lat": lat, "lon": lon}
                if tz_offset is not None:
                    location["tz_offset_hours"] = tz_offset

        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=MAX_SCAN_DAYS - 1)

        return find_business_muhurta(
            start_date, end_date, event_type, location, native_payload=payload,
        )
    except Exception as exc:  # pragma: no cover - defensive, mirrors muhurta.py's own contract
        return {
            "status": "EPHEMERIS_UNAVAILABLE",
            "note": f"Muhurta scan could not run for this report: {exc}",
            "event_type": event_type,
            "results": [],
            "scanned_days": 0,
        }


def _default_ashtakavarga_years_result(
    payload: Any = None,
    timed_windows: Optional[List[Dict[str, Any]]] = None,
    years_ahead: int = 6,
) -> Dict[str, Any]:
    """Content-restructuring audit fix (item 7b, "Strongest Years"
    section wired but never called): rank_business_years() is a
    caller-chosen-year-range computation, distinct from
    compute_business_prediction()'s fixed pipeline, so
    _section_ashtakavarga_years_html() was previously never actually
    invoked by either report renderer -- fully built, styled, and
    translated content that never reached a real report. Mirrors
    _default_business_muhurta_result()'s pattern exactly: a sensible
    report-time default (this year through +years_ahead-1) so both
    editions can show real content without every caller having to call
    rank_business_years() and stitch it in manually themselves. Never
    raises: any failure degrades to the same {"status": ...} diagnostic
    contract rank_business_years()/_section_ashtakavarga_years_html()
    already use, so a report can never fail to render because of this
    helper."""
    try:
        start_year = datetime.now().year
        end_year = start_year + years_ahead - 1
        return rank_business_years(payload, start_year, end_year, timing_windows=timed_windows)
    except Exception as exc:  # pragma: no cover - defensive, mirrors muhurta.py's own contract
        return {
            "status": "COMPUTE_FAILED",
            "note": f"Ashtakavarga year ranking could not run for this report: {exc}",
            "ranked_years": [],
        }


def _kpi_bar_html(value: Any) -> str:
    """"Elevate the screen" pass: a small CSS-only horizontal progress bar
    under a KPI card's numeric value, color-matched to the same
    strong/moderate/weak tiering _score_tier_class() already uses for the
    card's left border -- previously a KPI card was a bare number with no
    visual sense of where it sits on the 0-100 scale relative to the
    other seven cards next to it; a reader had to read every digit to
    compare cards instead of scanning bar lengths at a glance. Returns an
    empty string for non-numeric values (confidence labels, +/- margin
    points) so those cards render exactly as before -- this only adds a
    bar where a real 0-100 score exists."""
    try:
        v = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return ""
    tier = "strong" if v >= 70 else ("moderate" if v >= 50 else "weak")
    return (
        f'<div class="kpi-bar-track"><div class="kpi-bar-fill kpi-bar-{tier}" '
        f'style="width:{v:.1f}%"></div></div>'
    )


def _prefix_not_evaluated_disclosure(section_html: str, disclosure_text: str) -> str:
    """Inserts a visible "not evaluated as part of the scored prediction"
    disclosure paragraph immediately after the section's <h2> heading.

    Used when a report section (e.g. Muhurta Recommendations) is being
    populated from a report-time auto-default computation while the
    corresponding field in the authoritative `compute_business_prediction()`
    result (e.g. muhurta_check) is null -- so a reader of the debug JSON and
    a reader of the HTML report do not see contradictory completeness
    signals for the same field. Falls back to prepending the disclosure if
    no <h2> tag is found. No-ops on an empty section_html (nothing to
    prefix -- avoids creating a disclosure-only section for a section that
    itself returned "").
    """
    if not section_html:
        return section_html
    marker = "</h2>"
    idx = section_html.find(marker)
    disclosure_html = f"""
  <p class="not-evaluated-disclosure" style="margin-top:-4px; font-size:13px; color:var(--muted, #666); font-style:italic;">{_esc(disclosure_text)}</p>"""
    if idx == -1:
        return disclosure_html + section_html
    insert_at = idx + len(marker)
    return section_html[:insert_at] + disclosure_html + section_html[insert_at:]


def _resolve_report_language() -> str:
    """Resolves the HTML report language from the two .env flags the user
    controls: Report_Language_Enabled_Tamil / Report_Language_Enabled_Telugu.
    Tamil takes priority if both are somehow set true. Both false (or
    absent/unparseable) falls back to English. Returns 'ta' / 'te' / 'en'.
    """
    def _truthy(name: str) -> bool:
        return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes", "on")

    if _truthy("Report_Language_Enabled_Tamil"):
        return "ta"
    if _truthy("Report_Language_Enabled_Telugu"):
        return "te"
    return "en"


# Static UI-chrome translations for the two report editions. Only the fixed
# labels/headings/nav/footer/disclaimer chrome are translated here -- the
# engine's own dynamically-generated evidence text (mode-gate signal notes,
# contradiction findings, significator citations, KN Rao / decision-hierarchy
# traces, and the raw rec["reasoning"] sentence) is left in English, since
# reliably machine-translating free-form astrological evidence text on the
# fly is out of scope for this pass. The LLM dual-narrative section (when
# generated) IS produced directly in the target language -- see
# _DUAL_NARRATIVE_SYSTEM_PROMPT / _generate_dual_audience_narratives below.
_TR: Dict[str, Dict[str, str]] = {
    "ta": {
        "not_available_word": "கிடைக்கவில்லை",
        "none_recorded": "எதுவும் பதிவு செய்யப்படவில்லை",
        "astrologer_kicker": "ஜோதிஷ்ஏஐ · தொழில்முறை பதிப்பு",
        "astrologer_title": "வணிக ஜோதிட கணிப்பு பகுப்பாய்வு",
        "client_kicker": "உங்களுக்காக தயாரிக்கப்பட்டது",
        "client_title": "உங்கள் வணிக ஜோதிட அறிக்கை",
        "generated_prefix": "உருவாக்கப்பட்டது",
        "rule_pack_word": "விதி தொகுப்பு",
        "nav_narrative": "உங்கள் வாசிப்பு",
        "nav_reading_astrologer": "ஆலோசனை",
        "nav_summary": "சுருக்கம்",
        "nav_promise_fields_astro": "கட்டமைப்பு வாக்குறுதி புலங்கள்",
        "nav_promise_fields_client": "உங்கள் மதிப்பெண்கள்",
        "nav_forecast_window": "முன்னறிவிப்பு காலம்",
        "nav_significators": "வலிமை குறிகாட்டிகள்",
        "nav_sectors_astro": "வணிகத் துறைகள்",
        "nav_sectors_client": "சிறந்த பொருத்தமான துறைகள்",
        "nav_windows_astro": "காலக்கெடு சாளரங்கள்",
        "nav_windows_client": "சாதகமான காலகட்டங்கள்",
        "nav_method_status": "முறை நிலை",
        "h_recommendation": "பரிந்துரை",
        "h_in_summary": "சுருக்கமாக",
        "h_promise_fields": "கட்டமைப்பு வாக்குறுதி புலங்கள்",
        "h_your_scores": "ஒரு பார்வையில் உங்கள் மதிப்பெண்கள்",
        "h_forecast_window": "முன்னறிவிப்பு காலம் & காலநேர நிலை",
        "p_forecast_window": "கீழே உள்ள காலக்கெடு சாளரங்கள் மற்றும் தொடர்பு காலநேரம் பிரிவுகளுக்குப் பின்னால் உள்ள தேதி வரம்பு மற்றும் தசா-நாட்காட்டி கணக்கீட்டு நிலை.",
        "tt_authoritative_verdict": "அதிகாரப்பூர்வ தீர்ப்பு",
        "tt_action_level": "செயல் நிலை",
        "h_significators": "வணிக-வலிமை குறிகாட்டிகள்",
        "h_sectors_astro": "வணிகத் துறைகள்",
        "h_sectors_client": "உங்களுக்கு மிகவும் பொருத்தமான துறைகள்",
        "h_windows_astro": "காலக்கெடு சாளரங்கள்",
        "h_windows_client": "முன்னால் உள்ள சாதகமான காலகட்டங்கள்",
        "h_method_status": "முறை-நிலை",
        "h_narrative_astro": "ஜோதிட வாசிப்பு (ஜோதிடருக்கு)",
        "h_narrative_client": "உங்கள் ஜோதிட வாசிப்பு",
        "verdict_business_yes": "வணிகப்-பாதை ஆதரிக்கப்படுகிறது",
        "verdict_business_no": "தற்போதைக்கு வேலைவாய்ப்பு/கலப்பு முறை சாதகமானது",
        "final_verdict_label": "இறுதி தீர்ப்பு",
        "verdict_pursue_business": "வணிகத்தைத் தொடரவும்",
        "verdict_stay_employed": "வேலையில் தொடரவும்",
        "verdict_hybrid": "கலப்பு / படிப்படியான அணுகுமுறை",
        "business_promise_word": "வணிக வாக்குறுதி",
        "job_promise_word": "வேலை வாக்குறுதி",
        "weight_zero_applied_prefix": "0% பயன்படுத்தப்பட்டது (அறிவிக்கப்பட்ட அதிகபட்சம்",
        "score_not_available": "N/A (தரவு இல்லை)",
        "exploratory_match_chip_client": "பரந்த பொருத்தம் — உறுதிப்படுத்தப்பட்ட பரிந்துரை அல்ல",
        "client_summary_intro": "உங்கள் ஜாதகம் உண்மையான வணிக மற்றும் வாடிக்கையாளர்-தொடர்பு வலிமையைக் காட்டுகிறது, ஆனால் கீழே உள்ள எண்கள் வணிகமோ சம்பள வேலையோ தெளிவாக வெல்லாத அளவுக்கு நெருக்கமாக உள்ளன — அதனால்தான் மேலே உள்ள தீர்ப்பு நேரடி 'தொடரவும்' அல்ல, 'கலப்பு' ஆகும்.",
        "caveat_revenue_vs_retention": "உங்கள் ஜாதகம் நிகர லாபத்தை விட வாய்ப்பு மற்றும் வருவாயை எளிதாக உருவாக்குகிறது — வளர்ச்சியை மட்டும் அல்ல, ஒழுங்கான பண மேலாண்மையையும் திட்டமிடுங்கள்.",
        "caveat_d60_unavailable": "இந்த ஜாதகத்திற்கு ஆழமான உறுதிப்படுத்தல் அடுக்கு (D60) சரிபார்க்க முடியவில்லை, எனவே இந்த வாசிப்பு மற்ற எட்டு அடுக்குகளை மட்டுமே சார்ந்துள்ளது.",
        "caveat_kp_job_leaning": "ஒரு பிரத்யேக வாழ்வாதார-காலநேர முறை (KP) சம்பள வேலையை நோக்கி சாய்கிறது, மற்ற பெரும்பாலான முறைகள் வணிகத்தை நோக்கி சாய்ந்தாலும் — இது எச்சரிக்கைக்கான காரணம், நிராகரிப்புக்கு அல்ல.",
        "caveat_sectors_exploratory": "கீழே பட்டியலிடப்பட்டுள்ள துறைகள் பரந்த திறன் பொருத்தங்கள், உறுதிப்படுத்தப்பட்ட சரியான பரிந்துரைகள் அல்ல — இந்த ஜாதகத்தில் எதுவும் ஒரு பாரம்பரிய சரியான-சேர்க்கை பொருத்தத்தைக் காட்டவில்லை.",
        "general_career_favorable_badge": "பொதுவாக சாதகமானது (வணிகத்திற்கு-குறிப்பானது அல்ல)",
        "extended_outlook_summary": "விரிவாக்கப்பட்ட முன்னோக்கு (சுமார் 5 ஆண்டுகளுக்கு அப்பால் -- MD/AD காலநேரம் மட்டும் இவ்வளவு தொலைவில் குறைவான துல்லியமானது)",
        "heuristic_tier_disclaimer": "கீழே உள்ள \"ஹியூரிஸ்டிக் நிலை\" (உயர்/மிதமான/குறைவான) என்பது இரண்டு உறுதியான மதிப்பெண்களின் மீதான ஒரு உள்ளக, அளவீடு செய்யப்படாத விதி வரம்பு. இது ஒரு அளவிடப்பட்ட புள்ளிவிவர நம்பிக்கை, நிகழ்தகவு, அல்லது நிதி/சட்ட/முதலீட்டு ஆலோசனை அல்ல. இந்த அறிக்கை மேலும் ஜோதிட மறுஆய்வுக்கான ஒரு முடிவு-ஆதரவு விவரிப்பு, நிதி முன்னறிவிப்பு அல்ல.",
        "footer_astro": "ஜோதிஷ்ஏஐ வணிக கணிப்பு பகுப்பாய்வு (ஜோதிடர் பதிப்பு)",
        "footer_client": "ஜோதிஷ்ஏஐ · உங்கள் வணிக ஜோதிட அறிக்கை. பாரம்பரிய ஜோதிட முறைகள்; மேலும் சிந்தனைக்கான ஒரு முடிவு-ஆதரவு வாசிப்பு, நிதி, சட்ட அல்லது மருத்துவ ஆலோசனை அல்ல.",
        "translation_incomplete_notice": "குறிப்பு: இந்த அறிக்கை உருவாக்கப்பட்டபோது சில தொழில்நுட்ப ஆதார வாக்கியங்களின் நேரடி மொழிபெயர்ப்பு கிடைக்கவில்லை; அந்த குறிப்பிட்ட வாக்கியங்கள் கீழே ஆங்கிலத்தில் உள்ளன.",
        "evidence_word": "ஆதாரம்",
        "arbitration_ledger_word": "நடுவர் பதிவேடு",
        "tiers_word": "அடுக்குகள்",
        "tier_word": "அடுக்கு",
        "calendar_periods_found": "காணப்பட்ட நாட்காட்டி காலங்கள்",
        "p_narrative_astro": "இந்த அறிக்கையில் உள்ள உறுதியான ஆதாரங்களிலிருந்து (வீடு/அதிபதி ஆதாரம், வாக்குறுதி மதிப்பெண்கள், துறை தரவரிசை, முரண்பாடு கண்டறிதல்கள், காலக்கெடு சாளரங்கள்) மட்டுமே கண்டிப்பாக உருவாக்கப்பட்ட ஒரு நீண்ட-வடிவ விவரணை — மாதிரி ஏற்கனவே உள்ள ஆதாரத்தை விளக்குகிறது, புதிய ஜோதிட கூற்றுகளை அறிமுகப்படுத்தவில்லை.",
        "p_promise_fields": "ஒன்றாக இணைக்கப்பட்ட ஒரு வணிகம்-vs-வேலை ஒப்பீடு அல்ல, ஒன்பது தனித்தனியாக கணக்கிடப்பட்ட புலங்கள் — ஒரு சுயதொழில் வாக்குறுதி, ஒரு ஒப்பீட்டு வணிகம்-vs-வேலை வாக்குறுதி, புலம்/செயல்பாட்டு மாதிரி பொருத்தம், மற்றும் ஒரு முறை-ஒப்புதல் அடிப்படையிலான நம்பிக்கை லேபிள், என்ஜினின் v17 தணிக்கை-திருத்த கட்டமைப்பின்படி.",
        "h3_full_field_detail": "முழு புல விவரம்",
        "h3_biz_layers": "வணிக வாக்குறுதி — அறிவிக்கப்பட்ட அடுக்கு எடைகள் (மொத்தம் 100%)",
        "h3_job_layers": "வேலை வாக்குறுதி — அறிவிக்கப்பட்ட அடுக்கு எடைகள் (மொத்தம் 100%)",
        "h3_op_model_d1": "செயல்பாட்டு மாதிரி பொருத்தம் (D1)",
        "h3_op_model_d10": "செயல்பாட்டு மாதிரி பொருத்தம் — D10-சொந்த பிரதிபலிப்பு",
        "h3_contradiction": "முரண்பாடு-கட்டுப்பாடு கண்டறிதல்கள்",
        "p_contradiction": "ஒரு விதியின் மூல நேர்மறை கடன் ஒரு பாரம்பரிய எச்சரிக்கையால் குறைக்கப்படும்போது பயன்படுத்தப்படும் வெளிப்படையான தண்டனைகள் (எ.கா. 2ம்/10ம்/11ம் இணைப்பு இல்லாத வலுவான 7ம் வீடு வாடிக்கையாளர்-எதிர்கொள்ளும் வேலைவாய்ப்பாக படிக்கப்படுகிறது, உரிமையாக அல்ல) — மேலே உள்ள புலங்களில் ஏற்கனவே கழிக்கப்பட்டது, வெளிப்படைத்தன்மைக்காக இங்கே காட்டப்படுகிறது.",
        "h3_forecast_window": "முன்னறிவிப்பு காலம் & காலநேர நிலை",
        "as_of_word": "நிலவரப்படி",
        "years_ahead_word": "ஆண்டுகள் முன்",
        "p_significators": "வீடு/கிரக அதிபத்தியம், D9/D10 கண்ணியம், D10-சொந்த வீடு வரைபடம், பலதீபிகா பல-லக்னம், ஜைமினி ராசி திருஷ்டி/அர்கலா — முழு பட்டியலுக்கு அடிப்படை JSON-ல் உள்ள EVIDENCE_BASIS-ஐ காணவும்.",
        "overall_strength_word": "மொத்த வலிமை",
        "heuristic_scale_note": "ஹியூரிஸ்டிக் தொடர்பான அளவுகோல், நிகழ்தகவு அல்ல",
        "positive_total_word": "நேர்மறை மொத்தம்",
        "negative_total_word": "எதிர்மறை மொத்தம்",
        "net_word": "நிகரம்",
        "h3_positive_signals": "நேர்மறை சமிக்ஞைகள்",
        "h3_risk_signals": "அபாய சமிக்ஞைகள்",
        "all_ranked_word": "அனைத்தும்",
        "ranked_word": "தரவரிசைப்படுத்தப்பட்டது",
        "p_timed_windows": "மேலே உள்ள முன்னறிவிப்பு காலத்திற்குள் வரையறுக்கப்பட்ட தசை/அந்தர்தசை நாட்காட்டி. ஒவ்வொரு சாளரமும் அடுக்கு முன்னுரிமை நடுவர் மூலம் தயாரிக்கப்பட்ட ஒரு நிகர-மதிப்பெண் லேபிளைக் காட்டுகிறது (D1 → D9/D10 உறுதி/மறுப்பு → KP இறுதி நடுவர் → ஜைமினி செயல்பாடு → கிரக சஞ்சாரம்/ஷட்பல தூண்டுதல்) — முழு ஆதார பதிவேடு மற்றும் நடுவர் தடத்திற்கு ஒரு சாளரத்தை விரிவாக்கவும்.",
        "p_method_status": "இந்த ஜாதகத்திற்கு உண்மையில் இயங்கியது, தரவு இல்லாமல் அல்லது கிடைக்காமல் இருந்தவை — மேலே உள்ள \"காலநேர கணக்கீட்டு நிலை\"-லிருந்து வேறுபட்டது, இது தசை நாட்காட்டியே கணக்கிடப்பட்டதா என்பதை மட்டும் பிரதிபலிக்கிறது.",
        "footer_astro_tail": "பரிசோதனை ஜோதிட ஹியூரிஸ்டிக்குகள்; அளவீடு செய்யப்பட்ட நிதி, சட்ட அல்லது முதலீட்டு ஆலோசனை அல்ல.",
        "timing_word": "காலநேரம்",
        "no_favorable_windows": "தற்போதைய முன்னறிவிப்பு காலத்தில் தெளிவாக சாதகமான சாளரங்கள் எதுவும் இல்லை — காலநேரம் இப்போது தீர்க்கமானதை விட கலவையாக உள்ளது.",
        "exploratory_match_chip": "ஆய்வுநிலை — பாரம்பரிய சேர்க்கை பொருத்தம் இல்லை",
        "p_your_scores": "உங்கள் ஜாதகத்தின் எட்டு தனித்தனி வாசிப்புகள் — ஒரே ஒரு வணிகம்-vs-வேலை தீர்ப்பு அல்ல, மாறாக உங்கள் பலம் மற்றும் தயார்நிலை உண்மையில் எங்கே உள்ளது என்பதன் முழுமையான படம்.",
        "your_top_word": "உங்கள் சிறந்த",
        "best_matching_word": "உங்கள் ஜாதகத்தின் வீடுகள் மற்றும் கிரகங்களின் அடிப்படையில், மிகச் சிறந்த பொருந்தும் வணிகத் துறைகள்.",
        "p_favorable_periods": "மேலே பயன்படுத்தப்பட்ட அதே முன்னறிவிப்பு காலத்தின் அடிப்படையில், வணிகம் அல்லது தொழில்முனைவு நடவடிக்கையை மிகவும் ஆதரிக்கும் உங்கள் தசை (கிரக காலம்) நாட்காட்டியில் உள்ள காலக்கெடுகள்.",
        "print_button": "அச்சிடு / PDF ஆக சேமி",
        "glossary_title": "இந்த அறிக்கையை எப்படி படிப்பது — ஜோதிட சொற்கள் விளக்கப்பட்டுள்ளன",
        "glossary_intro": "இந்த அறிக்கை முழுவதும் பாரம்பரிய ஜோதிட சொற்களைப் பயன்படுத்துகிறது (வீட்டு அதிபதிகள், யோகங்கள், கண்ணியம், பிரிவு ஜாதகங்கள், தசை காலங்கள் மற்றும் பல). கீழே உள்ள ஒவ்வொரு சொல்லும் இங்கே ஒரு முறை எளிய மொழியில் விளக்கப்பட்டுள்ளது, அதனால் நீங்கள் ஆவணத்தை விட்டு வெளியேறாமல் எதையும் தேடிப் பார்க்கலாம் — அச்சிடப்பட்ட அல்லது PDF நகலிலும் கூட.",
        "nav_at_a_glance": "ஒரு பார்வையில்",
        "nav_appendix": "தொழில்நுட்ப பிற்சேர்க்கை",
        "h_at_a_glance": "ஒரு பார்வையில்",
        "p_at_a_glance": "இந்த அறிக்கையின் நான்கு முக்கிய தகவல்கள், ஒரே இடத்தில் — ஒவ்வொன்றும் பக்கத்தில் மேலும் விரிவாக விளக்கப்பட்டுள்ளது; இங்கு எதுவும் புதிதாக கணக்கிடப்படவில்லை.",
        "glance_verdict": "தீர்ப்பு",
        "glance_top_sector": "சிறந்த பொருத்தமான துறை",
        "glance_top_window": "அருகிலுள்ள சாதகமான காலம்",
        "glance_top_risk": "மிகப் பெரிய அபாய குறி",
        "glance_no_sector": "தரவரிசைப்படுத்தப்பட்ட துறை இல்லை",
        "glance_no_window": "இந்த காலத்தில் சிறப்பாக சாதகமான காலம் இல்லை",
        "glance_no_risk": "பெரிய அபாய குறிகள் எதுவும் இல்லை",
        "h_technical_appendix": "தொழில்நுட்ப பிற்சேர்க்கை — துணை ஆதாரங்கள் & விரிவான சரிபார்ப்புகள்",
        "p_technical_appendix": "மேலே உள்ள தீர்ப்பு, மதிப்பெண்கள், துறைகள் மற்றும் காலநேரம் ஏற்கனவே கீழே உள்ள அனைத்தையும் உள்ளடக்கியுள்ளன — இந்த பிற்சேர்க்கை அவற்றுக்கு பங்களித்த தனிப்பட்ட பாரம்பரிய சரிபார்ப்புகளை (யோகங்கள், பிரிவு-ஜாதக ஆதாரம், ஒற்றை-கிரக தீர்ப்புகள் மற்றும் பல) காட்டுகிறது, முழு மேற்கோள் தடத்தை விரும்பும் வாசகர்களுக்காக.",
        "h_lagnesh_neecha_bhanga_client": "தனியாக தொடங்குவதற்கான நம்பிக்கை (லக்ன சரிபார்ப்பு)",
        "p_lagnesh_client_cancelled": "உங்கள் சுயநிலை மற்றும் தனிப்பட்ட உந்துதலை பிரதிநிதித்துவப்படுத்தும் கிரகம் ({lagnesh}) உங்கள் ஜாதகத்தில் பலவீனமான நிலையில் தொடங்குகிறது — ஆனால் பாரம்பரிய விதிகள் இந்த பலவீனம் மற்றொரு காரணியால் ஈடுசெய்யப்படுவதைக் காட்டுகின்றன, எனவே இது தனியாக முன்னெடுக்கும் உங்கள் நம்பிக்கையை பெரிதும் பாதிக்காது.",
        "p_lagnesh_client_uncancelled": "உங்கள் சுயநிலை மற்றும் தனிப்பட்ட உந்துதலை பிரதிநிதித்துவப்படுத்தும் கிரகம் ({lagnesh}) உங்கள் ஜாதகத்தில் பலவீனமான நிலையில் தொடங்குகிறது, மேலும் பாரம்பரிய விதிகள் இது மற்றொரு காரணியால் ஈடுசெய்யப்படுவதைக் காட்டவில்லை. இது முக்கியமாக முழுமையாக சுய-நிதியளிக்கப்பட்ட, தனி முயற்சிக்கான நம்பிக்கையை பாதிக்கிறது — இது ஆலோசனை, கற்பித்தல் அல்லது குழு அடிப்படையிலான தொழில்முறை பாத்திரங்களில் வெற்றிபெறும் உங்கள் திறனைக் குறைக்காது, அவை ஜாதகத்தின் மற்ற பகுதிகளைச் சார்ந்துள்ளன.",
        "cover_subtitle": "வணிக சாத்தியக்கூறு, சிறந்த பொருத்தமான தொழில் துறைகள் மற்றும் சாதகமான காலநேரம் பற்றிய பாரம்பரிய வேத ஜோதிட வாசிப்பு -- மேலும் சிந்தனைக்கான முடிவு-ஆதரவு, நிதி, சட்ட அல்லது முதலீட்டு ஆலோசனை அல்ல.",
        "cover_prepared_for": "இதற்காக தயாரிக்கப்பட்டது",
        "cover_confidential": "தனிப்பட்ட & இரகசியமானது -- பெயரிடப்பட்ட பெறுநருக்காக மட்டும் தயாரிக்கப்பட்டது.",
        "cover_teaser_verdict": "தீர்ப்பு",
        "cover_teaser_sector": "சிறந்த பொருத்தமான துறை",
        "toc_title": "உள்ளடக்கம்",
        "toc_sub": "இந்த ஆவணத்தில் தோன்றும் வரிசையில் பட்டியலிடப்பட்டுள்ளது.",
        "toc_part_appendix": "பிற்சேர்க்கை",
    },
    "te": {
        "not_available_word": "అందుబాటులో లేదు",
        "none_recorded": "ఏవీ నమోదు కాలేదు",
        "astrologer_kicker": "జ్యోతిష్AI · వృత్తిపరమైన ఎడిషన్",
        "astrologer_title": "వ్యాపార జ్యోతిష్య అంచనా విశ్లేషణ",
        "client_kicker": "మీ కోసం సిద్ధం చేయబడింది",
        "client_title": "మీ వ్యాపార జ్యోతిష్య నివేదిక",
        "generated_prefix": "రూపొందించబడింది",
        "rule_pack_word": "నియమ ప్యాక్",
        "nav_narrative": "మీ పఠనం",
        "nav_reading_astrologer": "సలహా",
        "nav_summary": "సారాంశం",
        "nav_promise_fields_astro": "నిర్మాణాత్మక వాగ్దాన క్షేత్రాలు",
        "nav_promise_fields_client": "మీ స్కోర్‌లు",
        "nav_forecast_window": "సూచన కాలం",
        "nav_significators": "బలం సూచికలు",
        "nav_sectors_astro": "వ్యాపార రంగాలు",
        "nav_sectors_client": "ఉత్తమ-సరిపోలిక రంగాలు",
        "nav_windows_astro": "సమయ విండోలు",
        "nav_windows_client": "అనుకూల కాలాలు",
        "nav_method_status": "పద్ధతి స్థితి",
        "h_recommendation": "సిఫార్సు",
        "h_in_summary": "సారాంశంలో",
        "h_promise_fields": "నిర్మాణాత్మక వాగ్దాన క్షేత్రాలు",
        "h_your_scores": "ఒక్క చూపులో మీ స్కోర్‌లు",
        "h_forecast_window": "సూచన కాలం & సమయ స్థితి",
        "p_forecast_window": "దిగువ టైమ్డ్ విండోస్ మరియు ట్రాన్సిషన్ టైమింగ్ విభాగాల వెనుక ఉన్న తేదీ పరిధి మరియు దశా-క్యాలెండర్ గణన స్థితి.",
        "tt_authoritative_verdict": "అధికారిక తీర్పు",
        "tt_action_level": "చర్య స్థాయి",
        "h_significators": "వ్యాపార-బల సూచికలు",
        "h_sectors_astro": "వ్యాపార రంగాలు",
        "h_sectors_client": "మీకు బాగా సరిపోయే రంగాలు",
        "h_windows_astro": "సమయ విండోలు",
        "h_windows_client": "ముందున్న అనుకూల కాలాలు",
        "h_method_status": "పద్ధతి-స్థాయి స్థితి",
        "h_narrative_astro": "జ్యోతిష్య పఠనం (జ్యోతిష్కుని కోసం)",
        "h_narrative_client": "మీ జ్యోతిష్య పఠనం",
        "verdict_business_yes": "వ్యాపార-మార్గం మద్దతు ఉంది",
        "verdict_business_no": "ప్రస్తుతానికి ఉద్యోగం/హైబ్రిడ్ మార్గం అనుకూలం",
        "final_verdict_label": "తుది తీర్పు",
        "verdict_pursue_business": "వ్యాపారాన్ని కొనసాగించండి",
        "verdict_stay_employed": "ఉద్యోగంలో కొనసాగండి",
        "verdict_hybrid": "హైబ్రిడ్ / దశలవారీ విధానం",
        "business_promise_word": "వ్యాపార వాగ్దానం",
        "job_promise_word": "ఉద్యోగ వాగ్దానం",
        "weight_zero_applied_prefix": "0% వర్తింపజేయబడింది (ప్రకటించిన గరిష్టం",
        "score_not_available": "N/A (డేటా లేదు)",
        "exploratory_match_chip_client": "విస్తృత సరిపోలిక — నిర్ధారిత సిఫార్సు కాదు",
        "client_summary_intro": "మీ జాతకం నిజమైన వ్యాపార మరియు క్లయింట్-ఎదుర్కొనే బలాన్ని చూపిస్తుంది, కానీ దిగువ సంఖ్యలు వ్యాపారం లేదా జీతం ఉద్యోగం స్పష్టంగా గెలవనంత దగ్గరగా ఉన్నాయి — అందుకే పైన ఉన్న తీర్పు నేరుగా 'కొనసాగించండి' కాదు, 'హైబ్రిడ్'.",
        "caveat_revenue_vs_retention": "మీ జాతకం నికర లాభాన్ని కంటే అవకాశం మరియు టర్నోవర్‌ను సులభంగా సృష్టిస్తుంది — వృద్ధిని మాత్రమే కాకుండా, క్రమశిక్షణతో కూడిన నగదు నిర్వహణను కూడా ప్లాన్ చేయండి.",
        "caveat_d60_unavailable": "ఈ జాతకానికి లోతైన నిర్ధారణ పొర (D60) తనిఖీ చేయబడలేదు, కాబట్టి ఈ పఠనం మిగిలిన ఎనిమిది పొరలపై మాత్రమే ఆధారపడి ఉంటుంది.",
        "caveat_kp_job_leaning": "ఒక ప్రత్యేక జీవనోపాధి-సమయ పద్ధతి (KP) జీతం ఉద్యోగం వైపు మొగ్గు చూపుతుంది, మిగిలిన చాలా పద్ధతులు వ్యాపారం వైపు మొగ్గు చూపినప్పటికీ — ఇది జాగ్రత్తకు కారణం, తిరస్కరణకు కాదు.",
        "caveat_sectors_exploratory": "దిగువ జాబితా చేయబడిన రంగాలు విస్తృత సామర్థ్య సరిపోలికలు, నిర్ధారిత ఖచ్చితమైన సిఫార్సులు కావు — ఈ జాతకంలో ఏదీ సాంప్రదాయ ఖచ్చితమైన-కలయిక సరిపోలికను చూపదు.",
        "general_career_favorable_badge": "సాధారణంగా అనుకూలం (వ్యాపార-నిర్దిష్టం కాదు)",
        "extended_outlook_summary": "విస్తరించిన దృక్పథం (సుమారు 5 సంవత్సరాలకు మించి -- MD/AD సమయపాలన మాత్రమే ఇంత దూరంలో తక్కువ ఖచ్చితమైనది)",
        "heuristic_tier_disclaimer": "క్రింద ఉన్న \"హ్యూరిస్టిక్ టైర్\" (అధిక/మధ్యస్థ/తక్కువ) అనేది రెండు నిర్ధారిత స్కోర్‌లపై ఒక అంతర్గత, క్రమాంకనం చేయని నియమ పరిమితి. ఇది కొలవబడిన గణాంక విశ్వాసం, సంభావ్యత, లేదా ఆర్థిక/న్యాయ/పెట్టుబడి సలహా కాదు. ఈ నివేదిక తదుపరి జ్యోతిష్య సమీక్ష కోసం ఒక నిర్ణయ-మద్దతు కథనం, ఆర్థిక అంచనా కాదు.",
        "footer_astro": "జ్యోతిష్AI వ్యాపార అంచనా విశ్లేషణ (జ్యోతిష్కుడి ఎడిషన్)",
        "footer_client": "జ్యోతిష్AI · మీ వ్యాపార జ్యోతిష్య నివేదిక. సాంప్రదాయ జ్యోతిష్య పద్ధతులు; తదుపరి ఆలోచన కోసం ఒక నిర్ణయ-మద్దతు పఠనం, ఆర్థిక, న్యాయ లేదా వైద్య సలహా కాదు.",
        "translation_incomplete_notice": "గమనిక: ఈ నివేదిక రూపొందించినప్పుడు కొన్ని సాంకేతిక ఆధార వాక్యాల ప్రత్యక్ష అనువాదం అందుబాటులో లేదు; ఆ నిర్దిష్ట వాక్యాలు క్రింద ఇంగ్లీష్‌లో ఉన్నాయి.",
        "evidence_word": "ఆధారం",
        "arbitration_ledger_word": "మధ్యవర్తిత్వ లెడ్జర్",
        "tiers_word": "అంచెలు",
        "tier_word": "అంచె",
        "calendar_periods_found": "కనుగొన్న క్యాలెండర్ కాలాలు",
        "p_narrative_astro": "ఈ నివేదికలోని నిర్ధారిత ఆధారాల (ఇల్లు/అధిపతి ఆధారం, వాగ్దాన స్కోర్‌లు, రంగ ర్యాంకింగ్, వైరుధ్య అన్వేషణలు, సమయ విండోలు) నుండి మాత్రమే ఖచ్చితంగా రూపొందించబడిన సుదీర్ఘ కథనం — మోడల్ ఇప్పటికే ఉన్న ఆధారాన్ని వివరిస్తోంది, కొత్త జ్యోతిష్య వాదనలను ప్రవేశపెట్టడం లేదు.",
        "p_promise_fields": "ఒకే కుదించిన వ్యాపారం-vs-ఉద్యోగం పోలిక కాదు, తొమ్మిది విడివిడిగా లెక్కించిన క్షేత్రాలు — స్వతంత్ర-వ్యాపార వాగ్దానం, తులనాత్మక వ్యాపారం-vs-ఉద్యోగం వాగ్దానం, క్షేత్రం/నిర్వహణ నమూనా సరిపోలిక, మరియు పద్ధతి-అంగీకార ఆధారిత విశ్వాస లేబుల్, ఇంజిన్ యొక్క v17 ఆడిట్-ఫిక్స్ ఫ్రేమ్‌వర్క్ ప్రకారం.",
        "h3_full_field_detail": "పూర్తి క్షేత్ర వివరం",
        "h3_biz_layers": "వ్యాపార వాగ్దానం — ప్రకటించిన పొర బరువులు (మొత్తం 100%)",
        "h3_job_layers": "ఉద్యోగ వాగ్దానం — ప్రకటించిన పొర బరువులు (మొత్తం 100%)",
        "h3_op_model_d1": "నిర్వహణ నమూనా సరిపోలిక (D1)",
        "h3_op_model_d10": "నిర్వహణ నమూనా సరిపోలిక — D10-స్థానిక ప్రతిబింబం",
        "h3_contradiction": "వైరుధ్య-నియంత్రణ అన్వేషణలు",
        "p_contradiction": "ఒక నియమం యొక్క ముడి సానుకూల క్రెడిట్ ఒక సాంప్రదాయ హెచ్చరిక ద్వారా బలహీనపడినప్పుడు వర్తించే స్పష్టమైన పెనాల్టీలు (ఉదా. 2వ/10వ/11వ కనెక్షన్ లేని బలమైన 7వ ఇల్లు యాజమాన్యంగా కాకుండా క్లయింట్-ఎదుర్కొనే ఉద్యోగంగా చదవబడుతుంది) — పైన ఉన్న క్షేత్రాలలో ఇప్పటికే తగ్గించబడింది, పారదర్శకత కోసం ఇక్కడ చూపబడింది.",
        "h3_forecast_window": "సూచన కాలం & సమయ స్థితి",
        "as_of_word": "నాటికి",
        "years_ahead_word": "సంవత్సరాల ముందు",
        "p_significators": "ఇల్లు/గ్రహ అధిపత్యం, D9/D10 గౌరవం, D10-స్థానిక ఇల్లు గ్రాఫ్, ఫలదీపిక బహుళ-లగ్నం, జైమిని రాశి దృష్టి/అర్గళ — పూర్తి జాబితా కోసం అంతర్లీన JSON లోని EVIDENCE_BASIS చూడండి.",
        "overall_strength_word": "మొత్తం బలం",
        "heuristic_scale_note": "హ్యూరిస్టిక్ సాపేక్ష స్కేల్, సంభావ్యత కాదు",
        "positive_total_word": "సానుకూల మొత్తం",
        "negative_total_word": "ప్రతికూల మొత్తం",
        "net_word": "నికర",
        "h3_positive_signals": "సానుకూల సంకేతాలు",
        "h3_risk_signals": "ప్రమాద సంకేతాలు",
        "all_ranked_word": "అన్నీ",
        "ranked_word": "ర్యాంక్ చేయబడింది",
        "p_timed_windows": "పైన ఉన్న సూచన కాలానికి పరిమితం చేయబడిన దశ/అంతర్దశ క్యాలెండర్. ప్రతి విండో అంచె ప్రాధాన్యత మధ్యవర్తిత్వం ద్వారా రూపొందించబడిన ఒకే నికర-స్కోర్ లేబుల్‌ను చూపుతుంది (D1 → D9/D10 నిర్ధారణ/తిరస్కరణ → KP అంతిమ మధ్యవర్తి → జైమిని క్రియాశీలత → గోచార/షడ్బల ట్రిగ్గర్) — పూర్తి ఆధార లెడ్జర్ మరియు మధ్యవర్తిత్వ ట్రయిల్ కోసం ఒక విండోను విస్తరించండి.",
        "p_method_status": "ఈ జాతకానికి నిజంగా ఏమి నడిచింది, డేటా లేకుండా లేదా అందుబాటులో లేని దానికి వ్యతిరేకంగా — పైన ఉన్న \"సమయ గణన స్థితి\" నుండి భిన్నంగా, ఇది దశ క్యాలెండర్ స్వయంగా గణించబడిందా అనే దానిని మాత్రమే ప్రతిబింబిస్తుంది.",
        "footer_astro_tail": "ప్రయోగాత్మక జ్యోతిష్య హ్యూరిస్టిక్స్; క్రమాంకనం చేసిన ఆర్థిక, న్యాయ లేదా పెట్టుబడి సలహా కాదు.",
        "timing_word": "సమయం",
        "no_favorable_windows": "ప్రస్తుత సూచన కాలంలో స్పష్టంగా అనుకూలమైన విండోలు గుర్తించబడలేదు — సమయం ఇప్పుడు నిర్ణయాత్మకంగా కాకుండా మిశ్రమంగా ఉంది.",
        "exploratory_match_chip": "అన్వేషణాత్మకం — శాస్త్రీయ కలయిక సరిపోలిక లేదు",
        "p_your_scores": "మీ జాతకం యొక్క ఎనిమిది వేర్వేరు పఠనాలు — ఒకే వ్యాపారం-vs-ఉద్యోగం తీర్పు కాదు, మీ బలాలు మరియు సంసిద్ధత నిజంగా ఎక్కడ ఉన్నాయో పూర్తి చిత్రం.",
        "your_top_word": "మీ అగ్రస్థాన",
        "best_matching_word": "మీ జాతకం యొక్క ఇళ్లు మరియు గ్రహాల ఆధారంగా, ఉత్తమంగా సరిపోలే వ్యాపార రంగాలు.",
        "p_favorable_periods": "పైన ఉపయోగించిన అదే సూచన హోరిజోన్ ఆధారంగా, వ్యాపారం లేదా వ్యవస్థాపక చర్యకు ఎక్కువగా మద్దతు ఇచ్చే మీ దశ (గ్రహ కాలం) క్యాలెండర్‌లోని సమయ విండోలు.",
        "print_button": "ప్రింట్ / PDF గా సేవ్ చేయండి",
        "glossary_title": "ఈ నివేదికను ఎలా చదవాలి — జ్యోతిష్య పదాలు వివరించబడ్డాయి",
        "glossary_intro": "ఈ నివేదిక అంతటా శాస్త్రీయ జ్యోతిష్య పరిభాషను ఉపయోగిస్తుంది (ఇంటి అధిపతులు, యోగాలు, గౌరవం, విభాగ జాతకాలు, దశ కాలాలు మరియు మరిన్ని). దిగువ ప్రతి పదం ఇక్కడ ఒకసారి సాధారణ భాషలో నిర్వచించబడింది, తద్వారా మీరు పత్రాన్ని విడిచిపెట్టకుండా దేనినైనా వెతకవచ్చు — ముద్రించిన లేదా PDF కాపీలో కూడా.",
        "nav_at_a_glance": "ఒక్క చూపులో",
        "nav_appendix": "సాంకేతిక అనుబంధం",
        "h_at_a_glance": "ఒక్క చూపులో",
        "p_at_a_glance": "ఈ నివేదిక యొక్క నాలుగు ప్రధాన అంశాలు, ఒకే చోట — ప్రతి ఒక్కటి పేజీలో మరింత వివరంగా వివరించబడింది; ఇక్కడ కొత్తగా ఏమీ లెక్కించబడలేదు.",
        "glance_verdict": "తీర్పు",
        "glance_top_sector": "అత్యుత్తమ సరిపోలిక రంగం",
        "glance_top_window": "సమీప అనుకూల కాలం",
        "glance_top_risk": "అతిపెద్ద ప్రమాద సూచిక",
        "glance_no_sector": "ర్యాంక్ చేయబడిన రంగం అందుబాటులో లేదు",
        "glance_no_window": "ఈ కాలంలో ప్రత్యేకంగా అనుకూలమైన విండో లేదు",
        "glance_no_risk": "పెద్ద ప్రమాద సూచికలు నమోదు కాలేదు",
        "h_technical_appendix": "సాంకేతిక అనుబంధం — మద్దతు ఆధారాలు & లోతైన తనిఖీలు",
        "p_technical_appendix": "పైన ఉన్న తీర్పు, స్కోర్‌లు, రంగాలు మరియు సమయం ఇప్పటికే దిగువ ఉన్న ప్రతిదాన్ని కలిగి ఉన్నాయి — ఈ అనుబంధం వాటికి దోహదపడిన వ్యక్తిగత శాస్త్రీయ తనిఖీలను (యోగాలు, విభాగ-జాతక ఆధారాలు, ఒకే-గ్రహ తీర్పులు మరియు మరిన్ని) చూపిస్తుంది, పూర్తి ఆధార క్రమాన్ని కోరుకునే పాఠకుల కోసం.",
        "h_lagnesh_neecha_bhanga_client": "ఒంటరిగా ప్రారంభించడానికి విశ్వాసం (లగ్న తనిఖీ)",
        "p_lagnesh_client_cancelled": "మీ స్వీయ భావన మరియు వ్యక్తిగత చొరవను సూచించే గ్రహం ({lagnesh}) మీ జాతకంలో బలహీనమైన స్థానం నుండి ప్రారంభమవుతుంది — కానీ శాస్త్రీయ నియమాలు ఈ బలహీనత మరొక అంశం ద్వారా భర్తీ చేయబడుతుందని చూపుతాయి, కాబట్టి ఇది మీ స్వంతంగా ముందుకు సాగే విశ్వాసాన్ని గణనీయంగా అడ్డుకోదు.",
        "p_lagnesh_client_uncancelled": "మీ స్వీయ భావన మరియు వ్యక్తిగత చొరవను సూచించే గ్రహం ({lagnesh}) మీ జాతకంలో బలహీనమైన స్థానం నుండి ప్రారంభమవుతుంది, మరియు శాస్త్రీయ నియమాలు ఇది మరొక అంశం ద్వారా భర్తీ చేయబడుతున్నట్లు చూపించవు. ఇది ప్రధానంగా పూర్తిగా స్వయం-నిధులతో నడిచే, ఒంటరి వెంచర్ కోసం విశ్వాసాన్ని ప్రభావితం చేస్తుంది — ఇది సలహా, బోధన లేదా బృంద-ఆధారిత వృత్తిపరమైన పాత్రలలో విజయం సాధించే మీ సామర్థ్యాన్ని తగ్గించదు, అవి జాతకంలోని ఇతర భాగాలపై ఆధారపడి ఉంటాయి.",
        "cover_subtitle": "వ్యాపార సాధ్యత, ఉత్తమ సరిపోలిక పరిశ్రమ రంగాలు మరియు అనుకూలమైన సమయం గురించి శాస్త్రీయ వేద జ్యోతిష్య పఠనం -- మరింత ఆలోచన కోసం నిర్ణయ-మద్దతు, ఆర్థిక, న్యాయ లేదా పెట్టుబడి సలహా కాదు.",
        "cover_prepared_for": "దీని కోసం సిద్ధం చేయబడింది",
        "cover_confidential": "వ్యక్తిగతం & గోప్యమైనది -- పేరు పెట్టబడిన స్వీకర్త కోసం మాత్రమే సిద్ధం చేయబడింది.",
        "cover_teaser_verdict": "తీర్పు",
        "cover_teaser_sector": "అత్యుత్తమ సరిపోలిక రంగం",
        "toc_title": "విషయ సూచిక",
        "toc_sub": "ఈ పత్రంలో కనిపించే క్రమంలో జాబితా చేయబడింది.",
        "toc_part_appendix": "అనుబంధం",
    },
}


def _t(lang: str, key: str, default: str) -> str:
    """Translation lookup with English fallback: returns _TR[lang][key] if
    present, else `default` (the English string already in the template).
    """
    return _TR.get(lang, {}).get(key, default)


# Static-vocabulary label/value translations covering the fixed set of
# English strings _prepare_common_sections() emits into table headers,
# KPI labels/hints, row labels, and the finite enum-style values the
# engine returns (heuristic tiers, timing bands, window labels, method
# statuses, boolean-ish yes/no words). Keyed by the EXACT English string
# used in the code below, looked up via _lt(). Unlike free-form evidence
# prose (which goes through _translate_texts_llm), every one of these is a
# known, enumerable value defined by this codebase, so it can be
# hand-translated once and reused deterministically -- no LLM call needed
# and no risk of a stray English word surviving because a live API call
# wasn't reachable.
_LABEL_TR: Dict[str, Dict[str, str]] = {
    # Look&feel fix: rec.get('comparative_advantage') / rec.get('hybrid_suggested')
    # are genuine Python booleans, not enum strings -- rendered raw they
    # showed the literal words "True"/"False" in the Recommendation section
    # (in every language, since _lt() only translates for lang != "en").
    # _fmt_yes_no() below routes bools through these two keys instead.
    "Yes": {"ta": "ஆம்", "te": "అవును"},
    "No": {"ta": "இல்லை", "te": "కాదు"},
    # v37 fix: registry sector labels (row['label'] in the sector
    # leaderboard) were never routed through _lt(), so Tamil/Telugu
    # reports always showed English sector names -- a direct violation of
    # "no English words, strongly enforce". All 19 registry sector labels
    # are hand-translated here (finite, fixed vocabulary; no LLM needed).
    "Trading & Commerce": {"ta": "வர்த்தகம் & வணிகம்", "te": "వాణిజ్యం & వ్యాపారం"},
    "Manufacturing & Industrial": {"ta": "உற்பத்தி & தொழில்துறை", "te": "తయారీ & పారిశ్రామిక"},
    "Real Estate & Construction": {"ta": "நிலம் & கட்டுமானம்", "te": "రియల్ ఎస్టేట్ & నిర్మాణం"},
    "Consulting & Professional Services": {"ta": "ஆலோசனை & தொழில்முறை சேவைகள்", "te": "కన్సల్టింగ్ & వృత్తిపరమైన సేవలు"},
    "Finance & Investment": {"ta": "நிதி & முதலீடு", "te": "ఆర్థిక & పెట్టుబడి"},
    "Hospitality & Lifestyle": {"ta": "விருந்தோம்பல் & வாழ்க்கை முறை", "te": "ఆతిథ్యం & జీవనశైలి"},
    "Technology Startup": {"ta": "தொழில்நுட்ப தொடக்க நிறுவனம்", "te": "సాంకేతిక స్టార్టప్"},
    "Import/Export & Foreign Trade": {"ta": "இறக்குமதி/ஏற்றுமதி & வெளிநாட்டு வர்த்தகம்", "te": "దిగుమతి/ఎగుమతి & విదేశీ వాణిజ్యం"},
    "Agriculture & Commodities": {"ta": "விவசாயம் & பொருட்கள்", "te": "వ్యవసాయం & వస్తువులు"},
    "Media & Creative Business": {"ta": "ஊடகம் & படைப்பாற்றல் வணிகம்", "te": "మీడియా & సృజనాత్మక వ్యాపారం"},
    "Healthcare & Wellness Venture": {"ta": "சுகாதாரம் & நல்வாழ்வு தொழில்முனைவு", "te": "ఆరోగ్య సంరక్షణ & వెల్‌నెస్ వెంచర్"},
    "Family Business Continuation": {"ta": "குடும்ப வணிகத் தொடர்ச்சி", "te": "కుటుంబ వ్యాపార కొనసాగింపు"},
    "Education & Training Institutions": {"ta": "கல்வி & பயிற்சி நிறுவனங்கள்", "te": "విద్య & శిక్షణ సంస్థలు"},
    "Logistics & Transportation": {"ta": "தளவாடங்கள் & போக்குவரத்து", "te": "లాజిస్టిక్స్ & రవాణా"},
    "Retail": {"ta": "சில்லறை வணிகம்", "te": "రిటైల్"},
    "Legal Services": {"ta": "சட்ட சேவைகள்", "te": "న్యాయ సేవలు"},
    "Entertainment & Sports": {"ta": "பொழுதுபோக்கு & விளையாட்டு", "te": "వినోదం & క్రీడలు"},
    "Energy & Utilities": {"ta": "எரிசக்தி & பயன்பாடுகள்", "te": "ఇంధనం & యుటిలిటీలు"},
    "Pharma & Biotech": {"ta": "மருந்தியல் & உயிரி தொழில்நுட்பம்", "te": "ఫార్మా & బయోటెక్"},
    "Strength of an independent-enterprise path for you": {"ta": "உங்களுக்கான சுயதொழில் பாதையின் வலிமை", "te": "మీ కోసం స్వతంత్ర వ్యాపార మార్గం యొక్క బలం"},
    "Strength of a salaried-employment path for you": {"ta": "உங்களுக்கான சம்பள வேலை பாதையின் வலிமை", "te": "మీ కోసం జీతం ఉద్యోగ మార్గం యొక్క బలం"},
    "Solo practice or consulting, without running a full business": {"ta": "முழு வணிகம் இல்லாமல் தனித்தொழில் அல்லது ஆலோசனை", "te": "పూర్తి వ్యాపారం లేకుండా ఒంటరి ప్రాక్టీస్ లేదా కన్సల్టింగ్"},
    "How well your top sector matches your chart": {"ta": "உங்கள் முதன்மைத் துறை உங்கள் ஜாதகத்துடன் எவ்வளவு பொருந்துகிறது", "te": "మీ అగ్రస్థాన రంగం మీ జాతకంతో ఎంత సరిపోతుంది"},
    "Your day-to-day ability to run it": {"ta": "இதை நடத்துவதற்கான உங்கள் அன்றாடத் திறன்", "te": "దీన్ని నడిపే మీ రోజువారీ సామర్థ్యం"},
    "Support for turning activity into real profit": {"ta": "செயல்பாட்டை உண்மையான லாபமாக மாற்றுவதற்கான ஆதரவு", "te": "కార్యకలాపాన్ని నిజమైన లాభంగా మార్చడానికి మద్దతు"},
    "How sustainable this path looks over time": {"ta": "இந்தப் பாதை காலப்போக்கில் எவ்வளவு நிலைத்தன்மையானதாகத் தெரிகிறது", "te": "ఈ మార్గం కాలక్రమేణా ఎంత స్థిరంగా కనిపిస్తుంది"},
    "Whether right now is a supported time to act": {"ta": "இப்போது செயல்படுவதற்கான சாதகமான காலமா என்பது", "te": "ఇప్పుడు చర్య తీసుకోవడానికి అనుకూలమైన సమయమేనా"},
    "Business Promise": {"ta": "வணிக வாக்குறுதி", "te": "వ్యాపార వాగ్దానం"},
    "Job Promise": {"ta": "வேலை வாக்குறுதி", "te": "ఉద్యోగ వాగ్దానం"},
    "Independent-Profession Promise": {"ta": "சுயதொழில் வாக்குறுதி", "te": "స్వతంత్ర వృత్తి వాగ్దానం"},
    "Business Sector Fit": {"ta": "வணிகத் துறை பொருத்தம்", "te": "వ్యాపార రంగ సరిపోలిక"},
    "Execution Capacity": {"ta": "செயல்படுத்தும் திறன்", "te": "అమలు సామర్థ్యం"},
    "Profitability": {"ta": "லாபகரத்தன்மை", "te": "లాభదాయకత"},
    "Stability": {"ta": "நிலைத்தன்மை", "te": "స్థిరత్వం"},
    "Timing Readiness": {"ta": "காலநேர தயார்நிலை", "te": "సమయ సంసిద్ధత"},
    "Business-over-Job Confidence": {"ta": "வேலையை விட வணிகத்தின் நம்பிக்கை", "te": "ఉద్యోగం కంటే వ్యాపారంపై విశ్వాసం"},
    "Business Advantage Margin": {"ta": "வணிக நன்மை வித்தியாசம்", "te": "వ్యాపార ప్రయోజన మార్జిన్"},
    "How strong is the independent-enterprise promise itself": {"ta": "சுயமாக தொழில் தொடங்குவதற்கான வாக்குறுதி எவ்வளவு வலிமையானது", "te": "స్వతంత్ర వ్యాపార వాగ్దానం ఎంత బలంగా ఉంది"},
    "How strong is the salaried-employment promise": {"ta": "சம்பள வேலைக்கான வாக்குறுதி எவ்வளவு வலிமையானது", "te": "జీతం ఉద్యోగ వాగ్దానం ఎంత బలంగా ఉంది"},
    "Solo practice / consulting without a trading structure": {"ta": "தனித்தொழில் / ஆலோசனை (வணிக அமைப்பு இல்லாமல்)", "te": "వ్యాపార నిర్మాణం లేకుండా ఒంటరి ప్రాక్టీస్ / కన్సల్టింగ్"},
    "How well the top sector matches this chart": {"ta": "முதன்மைத் துறை இந்த ஜாதகத்துடன் எவ்வளவு பொருந்துகிறது", "te": "ఈ జాతకానికి అగ్రస్థాన రంగం ఎంత సరిపోతుంది"},
    "D10-confirmed ability to run it day-to-day": {"ta": "D10 உறுதிப்படுத்திய அன்றாட நிர்வாகத் திறன்", "te": "D10 ధృవీకరించిన రోజువారీ నిర్వహణ సామర్థ్యం"},
    "2nd/11th-house profit and monetisation support": {"ta": "2ம்/11ம் வீட்டு லாபம் மற்றும் வருவாய் ஆதரவு", "te": "2వ/11వ ఇంటి లాభం మరియు ఆదాయ మద్దతు"},
    "D9-durability and D60-modified sustainability": {"ta": "D9 நீடிப்புத்தன்மை மற்றும் D60 மாற்றியமைக்கப்பட்ட நிலைத்தன்மை", "te": "D9 మన్నిక మరియు D60 మార్పు చెందిన స్థిరత్వం"},
    "Whether the current dasha activates business houses": {"ta": "தற்போதைய தசை வணிக வீடுகளை செயல்படுத்துகிறதா", "te": "ప్రస్తుత దశ వ్యాపార భావాలను సక్రియం చేస్తుందా"},
    "Field": {"ta": "புலம்", "te": "క్షేత్రం"},
    "Value": {"ta": "மதிப்பு", "te": "విలువ"},
    "Business promise": {"ta": "வணிக வாக்குறுதி", "te": "వ్యాపార వాగ్దానం"},
    "Job promise": {"ta": "வேலை வாக்குறுதி", "te": "ఉద్యోగ వాగ్దానం"},
    "Independent-profession promise": {"ta": "சுயதொழில் வாக்குறுதி", "te": "స్వతంత్ర వృత్తి వాగ్దానం"},
    "Business sector fit": {"ta": "வணிகத் துறை பொருத்தம்", "te": "వ్యాపార రంగ సరిపోలిక"},
    "Business execution capacity": {"ta": "வணிக செயல்படுத்தும் திறன்", "te": "వ్యాపార అమలు సామర్థ్యం"},
    "client_acquisition": {"ta": "வாடிக்கையாளர் பெறுதல்", "te": "క్లయింట్ సముపార్జన"},
    "commercial_execution": {"ta": "வணிக செயல்படுத்தல்", "te": "వాణిజ్య అమలు"},
    "capital_debt_management": {"ta": "மூலதனம்/கடன் மேலாண்மை", "te": "మూలధన/రుణ నిర్వహణ"},
    "operational_liability_risk": {"ta": "செயல்பாட்டு/பொறுப்பு அபாயம்", "te": "నిర్వహణ/బాధ్యత ప్రమాదం"},
    "self_agency": {"ta": "சுய முகவர்த்துவம்", "te": "స్వీయ ఏజెన్సీ"},
    "business_durability": {"ta": "வணிக நீடிப்புத்தன்மை", "te": "వ్యాపార మన్నిక"},
    "cash_flow_stability": {"ta": "பண ஓட்ட நிலைத்தன்மை", "te": "నగదు ప్రవాహ స్థిరత్వం"},
    "ownership_stability": {"ta": "உரிமையாண்மை நிலைத்தன்மை", "te": "యాజమాన్య స్థిరత్వం"},
    "registering_or_launching_business": {"ta": "வணிகத்தை பதிவு செய்தல்/தொடங்குதல்", "te": "వ్యాపారాన్ని నమోదు చేయడం/ప్రారంభించడం"},
    "partnership_formation": {"ta": "கூட்டாண்மை உருவாக்கம்", "te": "భాగస్వామ్య ఏర్పాటు"},
    "capital_deployment_or_borrowing": {"ta": "மூலதன பயன்பாடு/கடன் வாங்குதல்", "te": "మూలధన వినియోగం/రుణం తీసుకోవడం"},
    "expansion_or_scaling": {"ta": "விரிவாக்கம்/அளவை உயர்த்துதல்", "te": "విస్తరణ/స్కేలింగ్"},
    "remaining_employed": {"ta": "வேலையில் தொடர்தல்", "te": "ఉద్యోగంలో కొనసాగడం"},
    "foreign_or_exit_linked": {"ta": "வெளிநாட்டு/வெளியேற்றம் தொடர்பான", "te": "విదేశీ/నిష్క్రమణ సంబంధిత"},
    "Business profitability": {"ta": "வணிக லாபகரத்தன்மை", "te": "వ్యాపార లాభదాయకత"},
    "Business stability": {"ta": "வணிக நிலைத்தன்மை", "te": "వ్యాపార స్థిరత్వం"},
    "Current timing readiness": {"ta": "தற்போதைய காலநேர தயார்நிலை", "te": "ప్రస్తుత సమయ సంసిద్ధత"},
    "Business-over-job confidence": {"ta": "வேலையை விட வணிகத்தின் நம்பிக்கை", "te": "ఉద్యోగం కంటే వ్యాపారంపై విశ్వాసం"},
    "Business advantage margin": {"ta": "வணிக நன்மை வித்தியாசம்", "te": "వ్యాపార ప్రయోజన మార్జిన్"},
    "Operating-model best fit": {"ta": "செயல்பாட்டு மாதிரி சிறந்த பொருத்தம்", "te": "నిర్వహణ నమూనా ఉత్తమ సరిపోలిక"},
    "D24 competency status": {"ta": "D24 திறன் நிலை", "te": "D24 సామర్థ్య స్థితి"},
    "D60 confirmation status": {"ta": "D60 உறுதிப்படுத்தல் நிலை", "te": "D60 నిర్ధారణ స్థితి"},
    "Sign/modality field affinities": {"ta": "ராசி/முறைமை புல ஈடுபாடுகள்", "te": "రాశి/విధాన క్షేత్ర అనుకూలతలు"},
    "KP 10th-cusp job-vs-business": {"ta": "KP 10ம் கஸ்ப் வேலை-vs-வணிகம்", "te": "KP 10వ కస్ప్ ఉద్యోగం-vs-వ్యాపారం"},
    "Mode": {"ta": "பயன்முறை", "te": "మోడ్"},
    "Penalty": {"ta": "தண்டனை", "te": "పెనాల్టీ"},
    "Contradiction finding": {"ta": "முரண்பாடு கண்டறிதல்", "te": "వైరుధ్య అన్వేషణ"},
    "No contradiction-control findings for this chart.": {"ta": "இந்த ஜாதகத்திற்கு முரண்பாடு கண்டறிதல்கள் இல்லை.", "te": "ఈ జాతకానికి వైరుధ్య నియంత్రణ అన్వేషణలు లేవు."},
    "Operating model": {"ta": "செயல்பாட்டு மாதிரி", "te": "నిర్వహణ నమూనా"},
    "Relative fit (0-100, within-chart)": {"ta": "தொடர்புடைய பொருத்தம் (0-100, ஜாதகத்திற்குள்)", "te": "సాపేక్ష సరిపోలిక (0-100, జాతకంలో)"},
    "No operating-model data.": {"ta": "செயல்பாட்டு மாதிரி தரவு இல்லை.", "te": "నిర్వహణ నమూనా డేటా లేదు."},
    "Operating model (D10-native)": {"ta": "செயல்பாட்டு மாதிரி (D10-சொந்த)", "te": "నిర్వహణ నమూనా (D10-స్థానిక)"},
    "No D10-native operating-model data.": {"ta": "D10-சொந்த செயல்பாட்டு மாதிரி தரவு இல்லை.", "te": "D10-స్థానిక నిర్వహణ నమూనా డేటా లేదు."},
    "Business layer": {"ta": "வணிக அடுக்கு", "te": "వ్యాపార పొర"},
    "Weight (%)": {"ta": "எடை (%)", "te": "బరువు (%)"},
    "Layer score (0-100)": {"ta": "அடுக்கு மதிப்பெண் (0-100)", "te": "పొర స్కోరు (0-100)"},
    "No business-layer breakdown.": {"ta": "வணிக அடுக்கு விவரம் இல்லை.", "te": "వ్యాపార పొర విభజన లేదు."},
    "Job layer": {"ta": "வேலை அடுக்கு", "te": "ఉద్యోగ పొర"},
    "No job-layer breakdown.": {"ta": "வேலை அடுக்கு விவரம் இல்லை.", "te": "ఉద్యోగ పొర విభజన లేదు."},
    "Model status:": {"ta": "மாதிரி நிலை:", "te": "మోడల్ స్థితి:"},
    "Maturity statement:": {"ta": "முதிர்ச்சி அறிக்கை:", "te": "పరిపక్వత ప్రకటన:"},
    "The \"Heuristic Tier\" below (HIGH/MODERATE/LOW) is an internal, uncalibrated rule": {
        "ta": "கீழே உள்ள \"ஹியூரிஸ்டிக் நிலை\" (HIGH/MODERATE/LOW) என்பது ஒரு உள்ளக, அளவீடு செய்யப்படாத விதி",
        "te": "క్రింద ఉన్న \"హ్యూరిస్టిక్ టైర్\" (HIGH/MODERATE/LOW) అనేది ఒక అంతర్గత, క్రమాంకనం చేయని నియమం",
    },
    "Comparative advantage over employment": {"ta": "வேலைவாய்ப்பை விட ஒப்பீட்டு நன்மை", "te": "ఉద్యోగంపై తులనాత్మక ప్రయోజనం"},
    "Hybrid suggested": {"ta": "கலப்பு முறை பரிந்துரை", "te": "హైబ్రిడ్ సూచించబడింది"},
    "Metric": {"ta": "அளவீடு", "te": "మెట్రిక్"},
    "Positive business-strength signal": {"ta": "நேர்மறை வணிக-வலிமை சமிக்ஞை", "te": "సానుకూల వ్యాపార-బల సంకేతం"},
    "No positive signals found.": {"ta": "நேர்மறை சமிக்ஞைகள் எதுவும் இல்லை.", "te": "సానుకూల సంకేతాలు కనుగొనబడలేదు."},
    "Negative / risk signal": {"ta": "எதிர்மறை / அபாய சமிக்ஞை", "te": "ప్రతికూల / ప్రమాద సంకేతం"},
    "No negative signals found.": {"ta": "எதிர்மறை சமிக்ஞைகள் எதுவும் இல்லை.", "te": "ప్రతికూల సంకేతాలు కనుగొనబడలేదు."},
    "No timed windows in the requested forecast horizon.": {"ta": "கோரப்பட்ட முன்னறிவிப்பு காலத்தில் காலக்கெடு சாளரங்கள் இல்லை.", "te": "అభ్యర్థించిన సూచన కాలంలో సమయ విండోలు లేవు."},
    "Method": {"ta": "முறை", "te": "పద్ధతి"},
    "Status": {"ta": "நிலை", "te": "స్థితి"},
    "Detail": {"ta": "விவரம்", "te": "వివరం"},
    "Timing computation status:": {"ta": "காலநேர கணக்கீட்டு நிலை:", "te": "సమయ గణన స్థితి:"},
    "HIGH": {"ta": "உயர்", "te": "అధిక"},
    "MODERATE": {"ta": "மிதமான", "te": "మధ్యస్థ"},
    "LOW": {"ta": "குறைவான", "te": "తక్కువ"},
    "UNKNOWN": {"ta": "தெரியவில்லை", "te": "తెలియదు"},
    "FAVORABLE": {"ta": "சாதகமான", "te": "అనుకూలమైన"},
    "STRONG_FAVORABLE": {"ta": "வலுவான சாதகமான", "te": "బలమైన అనుకూలమైన"},
    "UNFAVORABLE": {"ta": "சாதகமற்ற", "te": "అననుకూలమైన"},
    "STRONG_UNFAVORABLE": {"ta": "வலுவான சாதகமற்ற", "te": "బలమైన అననుకూలమైన"},
    "NEUTRAL": {"ta": "நடுநிலை", "te": "తటస్థ"},
    "MIXED": {"ta": "கலப்பு", "te": "మిశ్రమ"},
    "COMPUTED": {"ta": "கணக்கிடப்பட்டது", "te": "గణించబడింది"},
    "SKIPPED_NO_DATA": {"ta": "தரவு இல்லாததால் தவிர்க்கப்பட்டது", "te": "డేటా లేనందున దాటవేయబడింది"},
    "PARTIAL": {"ta": "பகுதி", "te": "పాక్షిక"},
    "ERROR": {"ta": "பிழை", "te": "లోపం"},
    "True": {"ta": "ஆம்", "te": "అవును"},
    "False": {"ta": "இல்லை", "te": "కాదు"},
    "Yes": {"ta": "ஆம்", "te": "అవును"},
    "No": {"ta": "இல்லை", "te": "కాదు"},
    "Venture type:": {"ta": "தொழில் வகை:", "te": "వెంచర్ రకం:"},
    "Heuristic tier:": {"ta": "ஹியூரிஸ்டிக் நிலை:", "te": "హ్యూరిస్టిక్ టైర్:"},
    "STRONG_BUSINESS_ADVANTAGE": {"ta": "வலுவான வணிக நன்மை", "te": "బలమైన వ్యాపార ప్రయోజనం"},
    "MODERATE_BUSINESS_ADVANTAGE": {"ta": "மிதமான வணிக நன்மை", "te": "మధ్యస్థ వ్యాపార ప్రయోజనం"},
    "SLIGHT_BUSINESS_ADVANTAGE": {"ta": "சிறிய வணிக நன்மை", "te": "స్వల్ప వ్యాపార ప్రయోజనం"},
    "HYBRID_OR_INCONCLUSIVE": {"ta": "கலப்பு / முடிவற்ற", "te": "హైబ్రిడ్ / అనిశ్చిత"},
    "SLIGHT_JOB_ADVANTAGE": {"ta": "சிறிய வேலை நன்மை", "te": "స్వల్ప ఉద్యోగ ప్రయోజనం"},
    "MODERATE_JOB_ADVANTAGE": {"ta": "மிதமான வேலை நன்மை", "te": "మధ్యస్థ ఉద్యోగ ప్రయోజనం"},
    "STRONG_JOB_ADVANTAGE": {"ta": "வலுவான வேலை நன்மை", "te": "బలమైన ఉద్యోగ ప్రయోజనం"},
    "STRONG_BUSINESS_ADVANTAGE_BUT_BELOW_ABSOLUTE_FLOOR": {"ta": "வலுவான வணிக நன்மை (குறைந்தபட்ச வலிமை நிபந்தனை பூர்த்தியாகவில்லை)", "te": "బలమైన వ్యాపార ప్రయోజనం (కనీస బలం పరిమితి చేరలేదు)"},
    "VERY_HIGH": {"ta": "மிக உயர்", "te": "చాలా అధిక"},
    "EXPLORATORY_ONLY": {"ta": "ஆய்வுநிலை மட்டும்", "te": "అన్వేషణాత్మకం మాత్రమే"},
    "EXPERIMENTAL_HEURISTIC": {"ta": "பரிசோதனை ஹியூரிஸ்டிக்", "te": "ప్రయోగాత్మక హ్యూరిస్టిక్"},
    "NOT_CALIBRATED_NO_BACKTEST_NO_LABELED_OUTCOMES": {
        "ta": "அளவீடு செய்யப்படவில்லை — பின்சோதனை இல்லை, லேபிள் செய்யப்பட்ட முடிவுகள் இல்லை",
        "te": "క్రమాంకనం చేయబడలేదు — బ్యాక్‌టెస్ట్ లేదు, లేబుల్ చేసిన ఫలితాలు లేవు",
    },
}


def _lt(lang: str, text: Any) -> str:
    """Label/value translator for the finite, enumerable strings the
    engine and this template use (table headers, KPI/field labels, and
    enum-style status/tier/label words) -- looks up _LABEL_TR by the
    exact English text. Falls back to the original text (English) only
    if the string genuinely isn't in the map, which should not happen for
    any of the fixed-vocabulary call sites below since every one of them
    has a corresponding entry.
    """
    if lang == "en" or text is None:
        return str(text) if text is not None else ""
    key = str(text)
    if key in _LABEL_TR:
        return _LABEL_TR[key].get(lang, key)
    # v37 fix: enum/status words sometimes reach here in a different case
    # than the dict key was authored in (e.g. sbc_timing_band returning
    # "Moderate" while the dict's enum key is "MODERATE") -- a case
    # mismatch silently fell through to the English original before. Try
    # the upper-case enum form as a second lookup rather than giving up.
    upper_key = key.upper()
    if upper_key in _LABEL_TR:
        return _LABEL_TR[upper_key].get(lang, key)
    return key


def _fmt_field_value(lang: str, value: Any) -> str:
    """Formats a raw engine field value for display in a details/factor
    table cell (_table() does not escape or special-case its cells, so
    whatever a caller hands it goes straight into the HTML). Fixes the
    same class of leak as _fmt_yes_no() -- a genuine Python None field
    (e.g. combustion_distance_deg, own_d1_house, h7_strength when not
    computed) previously rendered as the literal word "None", and a
    genuine bool field (e.g. row['cancelled'], combustion['combust'])
    rendered as the literal word "True"/"False" -- for any details-table
    row across the report, not just the two the current pass touched."""
    if value is None:
        return _esc(_t(lang, 'not_available_word', 'Not available'))
    if isinstance(value, bool):
        return _esc(_fmt_yes_no(lang, value))
    return _esc(str(value))


def _fmt_yes_no(lang: str, value: Any) -> str:
    """Formats a genuine Python bool (rec['comparative_advantage'],
    rec['hybrid_suggested']) as "Yes"/"No" (translated via _LABEL_TR),
    instead of the raw str(True)/str(False) that leaked into the
    Recommendation section previously. Non-bool/None values pass through
    _lt() unchanged, so this is safe to use anywhere a value might or
    might not actually be boolean."""
    if isinstance(value, bool):
        return _lt(lang, "Yes" if value else "No")
    return _lt(lang, value)


def _esc(text: Any) -> str:
    return (str(text if text is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _fmt_pct(value: Any) -> str:
    """Formats a genuinely 0-100-bounded score as a percentage string, e.g.
    73.2 -> "73.2%". Only use this for fields actually clamped to [0, 100]
    by the engine (business_promise, job_promise, sector scores, etc.) --
    NOT for signed margins, 0-1 confidence scores (scale first), raw
    ledger/net-score point totals, or SAV/Ashtakavarga bindu counts, which
    need their own formatting (see callers). Falls back to the file's
    existing missing-value convention (an em dash) for non-numeric input.
    """
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _table(headers: List[str], rows: List[List[str]]) -> str:
    thead = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>"


# Content-restructuring audit fix (item 6): the significator evidence
# ledger previously rendered as one long, undifferentiated table (30+ rows
# on a typical chart) interleaving Parashari house-lord findings, Jaimini
# karaka/argala/rasi-drishti evidence, KP sub-lord findings, and D2/D9/D10
# varga-chart confirmations with no visual separation -- a reader had to
# read every row's prose to work out which classical method it came from.
# Ordered (prefix-substrings, group-label-key, group-label-default) triples,
# checked top-to-bottom, first match wins -- an evidence line that happens
# to mention two methods is filed under whichever is checked first, which
# is an acceptable heuristic for a display grouping (it changes nothing
# about the evidence itself, only which sub-heading it's displayed under).
_SIGNIFICATOR_EVIDENCE_GROUPS: List[Tuple[Tuple[str, ...], str, str]] = [
    (("Jaimini", "Arudha", "Karakamsha", "Atmakaraka", "Amatyakaraka", "Argala", "argala", "rasi drishti"),
     "grp_jaimini", "Jaimini System Evidence"),
    (("KP ", "KP-", "cusp", "sub-lord", "Sub-lord"),
     "grp_kp", "KP (Krishnamurti Paddhati) Evidence"),
    (("Phaladeepika",),
     "grp_phaladeepika", "Phaladeepika Multi-Lagna Evidence"),
    (("D2-Hora", "D2 Hora"),
     "grp_d2", "D2 (Hora) Wealth-Flow Evidence"),
    (("D9-native", "D9 (Navamsha", "Navamsha"),
     "grp_d9", "D9 (Navamsha) Confirmation"),
    (("D10-native", "D10 (Dashamsha", "Dashamsha", "D10 dispositor"),
     "grp_d10", "D10 (Dashamsha) Confirmation"),
]
_SIGNIFICATOR_EVIDENCE_DEFAULT_GROUP = ("grp_parashari", "Parashari House/Planet-Lord Evidence")


def _grouped_significator_table_html(lines: List[str], lang: str, column_header: str) -> str:
    """Buckets an already-translated list of significator evidence strings
    into classical-method sub-groups (see _SIGNIFICATOR_EVIDENCE_GROUPS
    above) and renders one small table per group instead of one flat
    table -- purely a display regrouping of the exact same strings; no
    evidence line's text or the underlying scoring is touched. Falls back
    to the previous flat single-table rendering when there are too few
    lines (<=6) for grouping to be worth the extra sub-headings, so short
    charts don't get a page of near-empty sub-sections."""
    if not lines:
        return ""
    if len(lines) <= 6:
        return _table([column_header], [[_esc(s)] for s in lines])

    buckets: Dict[str, List[str]] = {}
    order: List[str] = []
    for line in lines:
        matched_key, matched_label = _SIGNIFICATOR_EVIDENCE_DEFAULT_GROUP
        for prefixes, key, label in _SIGNIFICATOR_EVIDENCE_GROUPS:
            if any(p in line for p in prefixes):
                matched_key, matched_label = key, label
                break
        if matched_key not in buckets:
            buckets[matched_key] = []
            order.append(matched_key)
        buckets[matched_key].append(line)

    label_by_key = {key: label for _, key, label in _SIGNIFICATOR_EVIDENCE_GROUPS}
    label_by_key[_SIGNIFICATOR_EVIDENCE_DEFAULT_GROUP[0]] = _SIGNIFICATOR_EVIDENCE_DEFAULT_GROUP[1]

    # Parashari (the default/base bucket) reads first, as the classical
    # foundation the other systems corroborate -- then the rest in a fixed,
    # stable order (not bucket-size order, so re-running on the same chart
    # always produces the same group sequence).
    _display_order = [_SIGNIFICATOR_EVIDENCE_DEFAULT_GROUP[0]] + [k for _, k, _ in _SIGNIFICATOR_EVIDENCE_GROUPS]
    parts = []
    for key in _display_order:
        if key not in buckets:
            continue
        group_lines = buckets[key]
        parts.append(
            f'<h4 style="margin:14px 0 4px; font-size:12.5px; color:var(--navy-2); text-transform:uppercase; letter-spacing:.03em;">'
            f'{_esc(_t(lang, key, label_by_key[key]))} <span style="color:var(--ink-soft); font-weight:400; text-transform:none;">({len(group_lines)})</span></h4>'
            + _table([column_header], [[_esc(s)] for s in group_lines])
        )
    return "".join(parts)


_NARRATIVE_DISCLAIMER = (
    "Traditional interpretive guidance; not scientifically validated or a substitute "
    "for professional career, financial, legal, or medical advice."
)

_NARRATIVE_BANNED_PHRASES = (
    "% chance", "percent chance", "probability of", "guaranteed", "certain to", "will definitely",
)


def _narrative_evidence_pack(name: str, prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the ONLY facts the narrative LLM call is allowed to see, all
    read from already-computed engine output -- no astronomical/dasha/
    dignity value is recomputed or invented here. Mirrors the same
    discipline as jyotish/llm_composer.py's compose_narrative(): the model
    is asked to phrase existing deterministic evidence in readable prose
    for two audiences, never to introduce a new placement, yoga, date, or
    numeric claim of its own.
    """
    sig = prediction.get("significators", {}) or {}
    rec = prediction.get("recommendation", {}) or {}
    confidence = prediction.get("business_over_job_confidence", {}) or {}
    operating_model = prediction.get("operating_model", {}) or {}
    top_sectors = prediction.get("top_sectors", []) or []
    contradictions = prediction.get("contradiction_findings", []) or []
    timed_windows = prediction.get("timed_windows", []) or []

    favorable_windows = [
        w for w in timed_windows
        if str(w.get("label", "")).upper() in ("FAVORABLE", "STRONG_FAVORABLE")
    ][:3]

    return {
        "name": name,
        "recommendation_proceed": bool(rec.get("proceed")),
        "venture_type": rec.get("venture_type"),
        "heuristic_tier": rec.get("heuristic_tier"),
        "reasoning": rec.get("reasoning"),
        "business_promise": prediction.get("business_promise"),
        "job_promise": prediction.get("job_promise"),
        "independent_profession_promise": prediction.get("independent_profession_promise"),
        "business_field_fit": prediction.get("business_field_fit"),
        "business_execution_capacity": prediction.get("business_execution_capacity"),
        "business_profitability": prediction.get("business_profitability"),
        "business_stability": prediction.get("business_stability"),
        "current_timing_readiness": prediction.get("current_timing_readiness"),
        "business_advantage_margin": prediction.get("business_advantage_margin"),
        "business_advantage_label": prediction.get("business_advantage_label"),
        "confidence_label": confidence.get("label"),
        "confidence_method_agreement": confidence.get("method_agreement"),
        "operating_model_best_fit": operating_model.get("best_fit"),
        "top_sectors": [
            {"rank": s["rank"], "label": s["label"], "score": s["score"]} for s in top_sectors[:5]
        ],
        "top_positive_signals": (sig.get("signals") or [])[:8],
        "top_risk_signals": (sig.get("risk_signals") or [])[:6],
        "contradiction_notes": [c.get("note") for c in contradictions][:6],
        "favorable_timed_windows": [
            {"start": w.get("start_date"), "end": w.get("end_date"),
             "md_lord": w.get("md_lord"), "ad_lord": w.get("ad_lord"), "label": w.get("label")}
            for w in favorable_windows
        ],
    }


def _validate_dual_narrative(data: Dict[str, Any]) -> None:
    for key in ("astrologer_narrative_paragraphs", "client_narrative_paragraphs"):
        paras = data.get(key)
        if not isinstance(paras, list) or not (5 <= len(paras) <= 10):
            raise ValueError(f"{key} must be a list of 5-10 paragraphs, got {paras!r}")
        for p in paras:
            if not isinstance(p, str) or len(p.strip()) < 40:
                raise ValueError(f"{key} contains an empty or too-short paragraph")
    text_blob = " ".join(
        data.get("astrologer_narrative_paragraphs", []) + data.get("client_narrative_paragraphs", [])
    ).lower()
    for banned in _NARRATIVE_BANNED_PHRASES:
        if banned in text_blob:
            raise ValueError(f"Narrative used probability/certainty language: {banned!r}")
    if not data.get("disclaimer"):
        raise ValueError("disclaimer is required and must not be empty.")


_DUAL_NARRATIVE_SCHEMA = {
    "name": "dual_audience_narrative",
    "schema": {
        "type": "object",
        "properties": {
            "astrologer_narrative_paragraphs": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 10},
            "client_narrative_paragraphs": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 10},
            "disclaimer": {"type": "string"},
        },
        "required": ["astrologer_narrative_paragraphs", "client_narrative_paragraphs", "disclaimer"],
        "additionalProperties": False,
    },
    "strict": True,
}

_DUAL_NARRATIVE_SYSTEM_PROMPT = """You are writing two long-form narrative sections for a Vedic astrology
business-prediction report, using ONLY the supplied evidence pack (already-computed engine output).
Do not invent any placement, yoga, house lord, dasha date, or numeric score not present in the evidence.
Do not state a model score as a probability or certainty. Preserve appropriate uncertainty and note that
this is one engineered reading, not the only classical interpretation. Write in flowing prose paragraphs
(no bullet lists, no headers inside the paragraphs).

Produce TWO separate narratives:
1. "astrologer_narrative_paragraphs" (5 to 10 paragraphs): written for a professional Vedic astrologer
   peer-reviewing this chart. Use precise classical terminology (houses, lords, dignity, dasha/bhukti,
   Jaimini karakas, KP significators, yogas) freely, referencing the specific evidence given. Explain the
   reasoning chain: why business vs job vs independent-profession promise land where they do, which
   houses/lords are driving the top sector, what the contradiction findings mean classically, and what the
   timing windows suggest. Technical, dense, confident in tone but epistemically honest about uncertainty.
2. "client_narrative_paragraphs" (5 to 10 paragraphs): written directly TO the chart's subject, in plain,
   warm, encouraging, jargon-light language. Explain what this means for their life and career choices in
   practical terms, translate the technical evidence into everyday implications, and end with grounded,
   actionable guidance (not vague reassurance). Address them in second person ("you").

Also return "disclaimer": a short standard disclaimer stating this is traditional interpretive guidance,
not scientifically validated, and not a substitute for professional career/financial/legal/medical advice.

Output JSON only, matching the required schema exactly."""


def _has_llm_narrative_consent(payload: Optional[Any] = None) -> bool:
    """Same consent contract the engine's own compose_narrative() gate
    uses (business_determination/mode_gate.py's _compose_business_narrative):
    LLM_REPORT_CONSENT=true/1/yes/on in .env grants consent for every
    report run in this environment; otherwise consent falls back to the
    per-chart payload.external_llm_consent field. Centralizing this check
    here (rather than treating "the user asked for this feature" as a
    standing consent signal) means the dual-audience narrative respects
    the same on/off switch as the rest of this repo's LLM narrative layer.
    """
    env_consent = str(os.getenv("LLM_REPORT_CONSENT", "")).strip().lower() in {"1", "true", "yes", "on"}
    return env_consent or bool(getattr(payload, "external_llm_consent", False))


_LANGUAGE_NAMES = {"ta": "Tamil", "te": "Telugu", "en": "English"}

# Process-lifetime cache so the same English sentence (e.g. a recurring
# risk-signal phrase like "Lagnesh is DEBILITATED -> ...") is only sent to
# the translation model once per language, not once per report/session.
_DYNAMIC_TRANSLATION_CACHE: Dict[str, Dict[str, str]] = {"ta": {}, "te": {}}

# v37 hard zero-English-leakage fix: when live LLM translation of dynamic
# content is unavailable, this native-script placeholder is shown instead
# of the raw English sentence -- so "strongly enforce, no English words"
# holds even without network/API access. Deliberately generic ("detail not
# available in this language") rather than per-sentence, since there is no
# reliable offline translation for arbitrary free-form astrology prose.
_UNAVAILABLE_PLACEHOLDER = {
    "ta": "(இந்த விவரம் இந்த மொழியில் தற்போது கிடைக்கவில்லை)",
    "te": "(ఈ వివరం ప్రస్తుతం ఈ భాషలో అందుబాటులో లేదు)",
}


def _translate_texts_llm(texts: List[str], lang: str, payload: Optional[Any] = None) -> Optional[List[str]]:
    """Batch-translates a list of arbitrary English strings (engine-
    generated evidence sentences, findings, reasoning, etc.) into the
    target language via the same consent-gated LLM path the dual-audience
    narrative uses. Returns a list the SAME LENGTH as `texts`, in the same
    order, on success; returns None (never raises) if consent isn't
    granted, no provider/key is configured, or the call fails -- callers
    must treat None as "translation unavailable" and decide how to
    degrade, never assume every string was translated.

    This exists because the report's dynamic content (house/lord evidence
    citations, contradiction findings, dasha-window evidence, the
    recommendation's reasoning sentence, maturity caveats) is free-form
    prose generated by the astrology engine itself -- there is no fixed
    vocabulary to hand-translate the way static UI chrome (_TR dict) can
    be. Honoring "the entire HTML output must be in the selected
    language, no compromises" for this content requires an actual
    translation pass, not a lookup table.
    """
    if lang == "en" or not texts:
        return list(texts)
    if not _has_llm_narrative_consent(payload):
        return None

    cache = _DYNAMIC_TRANSLATION_CACHE.setdefault(lang, {})
    uncached_indices = [i for i, t in enumerate(texts) if t not in cache]
    if uncached_indices:
        try:
            from jyotish.llm import _LLM_PROVIDERS, _ProviderClientWrapper, _run_llm_with_retry
        except Exception:
            return None

        provider = str(os.getenv("LLM_PROVIDER", "openai")).strip().lower()
        if provider not in _LLM_PROVIDERS:
            return None
        env_var, default_model, call_fn = _LLM_PROVIDERS[provider]
        api_key = os.getenv(env_var)
        if not api_key:
            return None

        lang_name = _LANGUAGE_NAMES.get(lang, "English")
        to_translate = [texts[i] for i in uncached_indices]
        schema = {
            "name": "translated_strings",
            "schema": {
                "type": "object",
                "properties": {
                    "translations": {"type": "array", "items": {"type": "string"}, "minItems": len(to_translate), "maxItems": len(to_translate)},
                },
                "required": ["translations"],
                "additionalProperties": False,
            },
            "strict": True,
        }

        def _validate(data: Dict[str, Any]) -> None:
            out = data.get("translations")
            if not isinstance(out, list) or len(out) != len(to_translate):
                raise ValueError(f"Expected {len(to_translate)} translations, got {out!r}")

        system_prompt = (
            f"You translate short technical Vedic-astrology report strings from English into {lang_name}. "
            f"Translate EVERY string in the given JSON array into {lang_name}, preserving order and array "
            f"length exactly. Keep numbers, house numbers, planet names, sign names, dates, and percentages "
            f"as-is or in their common {lang_name} transliterated form -- do not drop or alter numeric "
            f"values. Do not add commentary, only translate. Return strict JSON only."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"strings": to_translate}, ensure_ascii=False)},
        ]
        try:
            if provider == "openai":
                import openai as _openai
                client = _openai.OpenAI(api_key=api_key)
            else:
                client = _ProviderClientWrapper(call_fn, api_key, default_model)
            result = _run_llm_with_retry(client, messages, schema, _validate, max_retries=2)
        except Exception:
            logging.getLogger(__name__).warning("Dynamic-content translation failed for lang=%s", lang, exc_info=True)
            return None
        if not result:
            return None
        for i, translated in zip(uncached_indices, result["translations"]):
            cache[texts[i]] = translated

    return [cache.get(t, t) for t in texts]


def _generate_dual_audience_narratives(
    name: str,
    prediction: Dict[str, Any],
    payload: Optional[Any] = None,
    lang: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Consent-gated LLM narrative layer, distinct from the engine's own
    opt-in compose_narrative() (which returns one short structured
    summary) but sharing its exact consent contract via
    _has_llm_narrative_consent(): gated on LLM_REPORT_CONSENT in .env, or
    payload.external_llm_consent for per-chart opt-in. Returns None
    (never raises) if consent isn't granted, no API key is configured, or
    the call fails -- callers must treat this as narrative sugar over the
    deterministic evidence, never a second source of truth.

    lang: 'ta' / 'te' / 'en' (default: resolved from .env). When non-
    English, both narrative paragraph sets AND the disclaimer are
    requested directly in that language from the model itself -- this is
    the one place in the report where non-English text is model-generated
    rather than looked up from the static _TR dictionary.
    """
    if not _has_llm_narrative_consent(payload):
        return None
    lang = lang or _resolve_report_language()

    try:
        from jyotish.llm import _LLM_PROVIDERS, _ProviderClientWrapper, _run_llm_with_retry
    except Exception:
        return None

    provider = str(os.getenv("LLM_PROVIDER", "openai")).strip().lower()
    if provider not in _LLM_PROVIDERS:
        return None
    env_var, default_model, call_fn = _LLM_PROVIDERS[provider]
    api_key = os.getenv(env_var)
    if not api_key:
        return None

    evidence = _narrative_evidence_pack(name, prediction)
    system_prompt = _DUAL_NARRATIVE_SYSTEM_PROMPT
    if lang != "en":
        lang_name = _LANGUAGE_NAMES.get(lang, "English")
        system_prompt += (
            f"\n\nIMPORTANT: Write BOTH \"astrologer_narrative_paragraphs\" and "
            f"\"client_narrative_paragraphs\" (and the \"disclaimer\") entirely in {lang_name}, "
            f"not English. Keep house/planet names and technical astrological terms that lack a "
            f"natural {lang_name} equivalent in their common transliterated form, but all "
            f"explanatory prose must be in {lang_name}."
        )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "EVIDENCE PACK (JSON):\n" + json.dumps(evidence, indent=2, default=str)},
    ]

    try:
        if provider == "openai":
            import openai as _openai
            client = _openai.OpenAI(api_key=api_key)
        else:
            client = _ProviderClientWrapper(call_fn, api_key, default_model)
        result = _run_llm_with_retry(client, messages, _DUAL_NARRATIVE_SCHEMA, _validate_dual_narrative, max_retries=3)
    except Exception:
        logging.getLogger(__name__).warning("Dual-audience narrative generation failed", exc_info=True)
        return None
    return result


_METHOD_STATUS_LABELS = {
    "d9_navamsha": "D9 (Navamsha) confirmation",
    "d10_dashamsha": "D10 (Dashamsha) confirmation",
    "kp_significators": "KP significators",
    "jaimini_karakas": "Jaimini karakas (AK/AmK)",
    "shadbala": "Shadbala",
    "dynamic_transit": "Dynamic transit projection",
    "sbc_advisory": "SBC (Sarvatobhadra Chakra) advisory timing",
}


def _shared_css() -> str:
    """CSS shared by both the astrologer report and the client report --
    kept as one function so the two deliverables stay visually consistent
    (same palette/type scale/card style) while their section content
    differs. Includes print rules (@page sizing, break-inside avoidance,
    sticky-nav removal in print) so either report exports cleanly to PDF
    via the browser's own Print-to-PDF, no separate PDF library needed."""
    return """
:root {
  --navy: #12213f; --navy-2: #1c2f57; --gold: #b8863b; --gold-light: #f4e7d0;
  --ink: #1c2430; --ink-soft: #566072; --line: #e2e6ee; --panel: #ffffff;
  --bg: #f4f6fa; --green: #1c7d4f; --green-bg: #e5f6ec; --amber: #92650c;
  --amber-bg: #fdf1dc; --red: #a3293b; --red-bg: #fbe7ea; --gray-bg: #eef0f4;
  --radius: 12px;
  --shadow: 0 1px 2px rgba(20,30,60,.05), 0 6px 20px rgba(20,30,60,.06);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  font-family: "Segoe UI", Inter, -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif;
  margin: 0; color: var(--ink); background: var(--bg); line-height: 1.55;
  /* Audit fix (printable-report pass): without this, most browsers strip
     background colors/gradients on print by default, so every colored
     chip/badge/hero band that carries real meaning (favorable/caution/
     risk bands, verdict color) silently turns invisible/plain-black-on-
     white in Print-to-PDF -- the single biggest "not actually printable"
     defect the report had. */
  -webkit-print-color-adjust: exact; print-color-adjust: exact; color-adjust: exact;
}

/* ---- print/floating toolbar: screen-only "Print / Save as PDF" trigger.
   Never appears in the printed output itself (see @media print below). ---- */
.print-toolbar { position: fixed; right: 18px; bottom: 18px; z-index: 50; }
.print-btn {
  display: flex; align-items: center; gap: 7px; background: var(--navy); color: #fff;
  border: none; border-radius: 999px; padding: 11px 18px; font-size: 13px; font-weight: 700;
  cursor: pointer; box-shadow: 0 4px 16px rgba(18,33,63,.28); font-family: inherit;
}
.print-btn:hover { background: var(--navy-2); }
.print-btn svg { width: 15px; height: 15px; }

/* ---- "How to read this report" glossary: astrological-explainability
   pass. Sits once, above the toggled Chart Profile / Astrologer View
   panels, so every jargon term (Lagna, Dasha, yoga, dignity, kendra/
   trikona/dusthana, D9/D10 varga charts, KP sub-lord, Jaimini karakas)
   used throughout the report has a plain-language definition a reader
   can find without leaving the document -- and, critically, without
   relying on JS/hover tooltips that don't survive Print-to-PDF. ---- */
.glossary { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 16px 20px; margin: 16px 0; }
.glossary h2 { font-size: 16px; margin-bottom: 4px; }
.glossary > p.glossary-intro { margin-top: 0; font-size: 13px; }
.glossary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 6px 20px; margin-top: 10px; }
.glossary-grid dt { font-weight: 700; color: var(--navy-2); font-size: 13px; margin-top: 6px; }
.glossary-grid dd { margin: 1px 0 0; font-size: 12.5px; color: var(--ink-soft); line-height: 1.4; }

/* ---- content-restructuring pass: visual tiering between "core decision
   content" (verdict, recommendation, scores, sectors, timing -- Tier 1/2,
   unchanged styling) and the long tail of single-technique supporting/
   deep-dive checks (yogas, legal-dispute risk, D2-Hora, Mercury
   adjudication, Lagnesh Neecha Bhanga, nakshatra chain, foreign-business,
   partnership fit, etc. -- Tier 3). Same content, same functions, only a
   wrapping divider + section styling so a reader can tell, by scanning,
   which part of the page they're in without having to read every H2. ---- */
.technical-appendix-divider {
  margin: 30px 0 16px; padding: 16px 20px; background: var(--gray-bg);
  border-left: 4px solid var(--gold); border-radius: 8px;
}
.technical-appendix-divider h2 { margin: 0 0 4px; font-size: 18px; }
.technical-appendix-divider p { margin: 0; font-size: 12.5px; }
.technical-appendix { opacity: 0.97; }
.technical-appendix section { background: #fbfbfd; }
.technical-appendix section .card { background: #ffffff; }
.paired-section-link { font-size: 11.5px; font-style: italic; color: var(--ink-soft); margin: -6px 0 6px; }
.wrap { max-width: 1200px; margin: 0 auto; padding: 0 24px 36px; }
/* Used only to host the glossary/print-toolbar ahead of the standalone
   astrologer/client reports' own main wrap element -- deliberately a
   DIFFERENT class name (not another wrap) so render_combined_report_html's
   string-based extraction of that inner wrap's content (which locates the
   first literal occurrence of the wrap-div opening tag in the source) is
   never at risk of accidentally matching this container instead. */
.pre-wrap { max-width: 1200px; margin: 0 auto; padding: 0 24px; }
h1, h2, h3 { color: var(--navy); font-weight: 700; letter-spacing: -0.01em; }
h2 { font-size: 20px; margin: 0 0 10px; padding-top: 4px; }
h3 { font-size: 15.5px; margin: 16px 0 8px; color: var(--navy-2); }
p { color: var(--ink-soft); font-size: 14px; line-height: 1.5; }
a { color: var(--navy-2); }

.hero {
  background: linear-gradient(135deg, var(--navy) 0%, var(--navy-2) 60%, #24406f 100%);
  color: #fff; padding: 26px 24px 20px; margin-bottom: 0;
}
.hero-inner { max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px; }
.hero h1 { color: #fff; font-size: 26px; margin: 0 0 6px; }
.hero .kicker { font-size: 11.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--gold-light); font-weight: 700; margin-bottom: 6px; }
.hero .subject { font-size: 15px; color: #cfd9ef; }
.hero .meta { font-size: 12.5px; color: #9fb0d6; margin-top: 4px; }
.hero-recommend { text-align: right; }
.hero-recommend .verdict { font-size: 22px; font-weight: 700; }
.hero-recommend .verdict.yes { color: #7be3ab; }
.hero-recommend .verdict.no { color: #f4a8b3; }
.hero-recommend .venture { font-size: 12.5px; color: #cfd9ef; margin-top: 2px; }
.final-verdict { text-align: right; }
.final-verdict-label { font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; color: #9fb0d6; font-weight: 700; }
.final-verdict-value { font-size: 24px; font-weight: 800; margin-top: 2px; }
.final-verdict.yes .final-verdict-value { color: #7be3ab; }
.final-verdict.no .final-verdict-value { color: #f4a8b3; }
.final-verdict.hybrid .final-verdict-value { color: #f5c56b; }
.final-verdict-meta { font-size: 11.5px; color: #9fb0d6; margin-top: 2px; }
.verdict-inline { font-weight: 700; }
.verdict-inline.yes { color: #7be3ab; }
.verdict-inline.no { color: #f4a8b3; }

/* ---- view switcher: toggles the Chart Profile / Astrologer View panels
   in the combined single-page report (render_combined_report_html). Sits
   above nav.tabs in the sticky stack so both remain visible together. ---- */
nav.viewswitch {
  position: sticky; top: 0; z-index: 30; background: #fff; border-bottom: 1px solid var(--line);
  box-shadow: 0 2px 8px rgba(20,30,60,.05);
}
nav.viewswitch .vs-inner { max-width: 1200px; margin: 0 auto; padding: 10px 24px; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.vs-label { font-size: 11.5px; letter-spacing: .06em; text-transform: uppercase; font-weight: 700; color: var(--ink-soft); }
.vs-btn {
  border: 1px solid var(--line); background: #fff; color: var(--ink-soft); font-weight: 700; font-size: 13.5px;
  padding: 8px 18px; border-radius: 999px; cursor: pointer; transition: all .15s ease;
}
.vs-btn.active { background: var(--navy); color: #fff; border-color: var(--navy); }
.vs-btn:not(.active):hover { border-color: var(--navy-2); color: var(--navy-2); }

/* .view/.view.active: the two toggled report panels in the combined
   report. Standalone astrologer/client renders never emit .view wrappers,
   so this rule is inert (display:block by default, harmless) for those. */
.view { display: none; }
.view.active { display: block; }

nav.tabs {
  position: sticky; top: 0; z-index: 20; background: #fff; border-bottom: 1px solid var(--line);
  box-shadow: 0 2px 8px rgba(20,30,60,.04); overflow-x: auto; white-space: nowrap;
}
/* Combined report only: nav.tabs sits directly under the sticky
   viewswitch bar rather than at the very top. */
.has-viewswitch nav.tabs { top: 49px; }
nav.tabs .tabs-inner { max-width: 1200px; margin: 0 auto; padding: 0 32px; }
nav.tabs a {
  display: inline-block; padding: 12px 16px; font-size: 13px; font-weight: 600; color: var(--ink-soft);
  text-decoration: none; border-bottom: 3px solid transparent;
}
nav.tabs a:hover { color: var(--navy); border-bottom-color: var(--gold-light); }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin: 16px 0 6px; }
.kpi-card {
  background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--ink-soft);
  border-radius: var(--radius); padding: 10px 14px; box-shadow: var(--shadow);
}
.kpi-card.kpi-strong { border-left-color: var(--green); }
.kpi-card.kpi-moderate { border-left-color: var(--amber); }
.kpi-card.kpi-weak { border-left-color: var(--red); }
.kpi-card .kpi-label { font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--ink-soft); }
.kpi-card .kpi-value { font-size: 26px; font-weight: 800; color: var(--navy); margin: 4px 0 2px; }
.kpi-card .kpi-hint { font-size: 11.5px; color: var(--ink-soft); }
.kpi-card.kpi-confidence .kpi-value { font-size: 18px; }
/* "Elevate the screen" pass: visual progress bar under each numeric KPI
   value so the 0-100 scale reads at a glance, not just as a digit. */
.kpi-bar-track { height: 5px; border-radius: 3px; background: var(--gray-bg); overflow: hidden; margin: 2px 0 6px; }
.kpi-bar-fill { height: 100%; border-radius: 3px; transition: width .3s ease; }
.kpi-bar-fill.kpi-bar-strong { background: var(--green); }
.kpi-bar-fill.kpi-bar-moderate { background: var(--amber); }
.kpi-bar-fill.kpi-bar-weak { background: var(--red); }

.card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 18px; margin-bottom: 14px; box-shadow: var(--shadow); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.grid-2 .card { margin-bottom: 0; }
@media (max-width: 880px) { .grid-2 { grid-template-columns: 1fr; } }

table { border-collapse: collapse; width: 100%; margin-bottom: 4px; table-layout: auto; }
th, td { border-bottom: 1px solid var(--line); padding: 6px 10px; text-align: left; font-size: 13px; line-height: 1.35; vertical-align: top; }
th { background: var(--gray-bg); color: var(--navy); font-size: 11.5px; text-transform: uppercase; letter-spacing: .03em; font-weight: 700; }
tbody tr:hover { background: #f8f9fc; }

.badge { display: inline-block; padding: 4px 11px; border-radius: 20px; font-weight: 700; font-size: 12px; }
.badge.HIGH, .badge.STRONG_FAVORABLE { background: var(--green-bg); color: var(--green); }
.badge.MODERATE, .badge.FAVORABLE { background: var(--amber-bg); color: var(--amber); }
.badge.LOW, .badge.MIXED { background: var(--gray-bg); color: var(--ink-soft); }
.badge.CAUTION { background: #fdeccb; color: #8a4b00; }
.badge.HIGH_RISK { background: var(--red-bg); color: var(--red); }
.net-score { font-family: "SF Mono", Consolas, monospace; color: var(--ink-soft); margin-left: 10px; font-size: 12.5px; }

.disclaimer { background: var(--gold-light); border: 1px solid #e2c491; border-radius: var(--radius); padding: 14px 18px; margin: 16px 0; font-size: 13.5px; }
.disclaimer p { color: #5b4620; margin: 4px 0; }
.disclaimer ul { margin: 6px 0 0 18px; padding: 0; color: #5b4620; font-size: 13px; }

.window-block { border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; background: #fbfcfe; }
.window-block h3 { font-size: 14px; margin: 2px 0; color: var(--navy); }
details summary { cursor: pointer; font-size: 12.5px; color: var(--navy-2); margin-top: 4px; font-weight: 600; }
details ul { font-size: 12.5px; margin: 4px 0; color: var(--ink-soft); line-height: 1.4; }
.windows-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 10px; }

.sector-leaderboard { display: flex; flex-wrap: wrap; gap: 8px; }
.sector-row { flex: 1 1 360px; display: grid; grid-template-columns: 34px 1fr 150px; align-items: center; gap: 14px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--line); background: #fbfcfe; }
.sector-row.tier-top { background: linear-gradient(90deg, var(--gold-light), #fff); border-color: #e6cd9d; }
.sector-row.tier-mid { background: #f6f8fc; }
.sector-rank { font-size: 15px; font-weight: 800; color: var(--navy); text-align: center; }
.tier-top .sector-rank { color: var(--gold); }
.sector-label-line { display: flex; justify-content: space-between; font-size: 13.5px; }
.sector-label { font-weight: 600; color: var(--ink); }
.sector-score { font-weight: 800; color: var(--navy); }
.sector-bar-track { height: 6px; background: var(--gray-bg); border-radius: 4px; margin-top: 6px; overflow: hidden; }
.sector-bar-fill { height: 100%; background: linear-gradient(90deg, var(--gold), var(--navy-2)); border-radius: 4px; }
.sector-meta { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; }
.chip { font-size: 10.5px; font-weight: 700; padding: 3px 8px; border-radius: 20px; background: var(--gray-bg); color: var(--ink-soft); white-space: nowrap; }
.chip-band-HIGH { background: var(--green-bg); color: var(--green); }
.chip-band-MODERATE { background: var(--amber-bg); color: var(--amber); }
.chip-band-LOW { background: var(--red-bg); color: var(--red); }

footer { font-size: 12px; color: var(--ink-soft); margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--line); }

/* ---- multi-column item grid: used by list-style sections (yogas,
   legal-dispute-risk flags, D2 Hora evidence, etc.) so short parallel
   items sit side-by-side on wide screens instead of stacking full-width.
   Flexbox (not CSS Grid) chosen deliberately: weasyprint's PDF path
   renders flex-wrap reliably, whereas its grid support is inconsistent,
   and @media print below forces single-column stacking anyway so the
   printed/PDF page never depends on the grid behaving. ---- */
.item-grid { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
.item-grid li {
  flex: 1 1 280px; border: 1px solid var(--line); border-radius: 8px; background: #fbfcfe;
  padding: 8px 12px; font-size: 13.5px; line-height: 1.45;
}

/* ---- narrative prose (astrologer or client reading) ---- */
.narrative-panel p { color: var(--ink); font-size: 14.5px; line-height: 1.6; margin: 0 0 12px; }
.narrative-panel p:first-of-type::first-letter {
  font-size: 2.6em; font-weight: 800; color: var(--gold); float: left; line-height: 0.85; margin: 4px 6px 0 0;
}
.narrative-panel-astrologer { border-top: 3px solid var(--navy-2); }
.narrative-panel-client { border-top: 3px solid var(--gold); }
.narrative-disclaimer { font-size: 12px; font-style: italic; color: var(--ink-soft); margin-top: 12px; }

/* ---- cover block (print title page) ---- */
.cover {
  min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center;
  text-align: center; background: linear-gradient(160deg, var(--navy) 0%, var(--navy-2) 55%, #24406f 100%);
  color: #fff; padding: 40px;
}
.cover .kicker { font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: var(--gold-light); font-weight: 700; margin-bottom: 18px; }
.cover h1 { color: #fff; font-size: 34px; margin: 0 0 10px; max-width: 640px; }
.cover .cover-subtitle { font-size: 14px; color: #cfd9ef; max-width: 520px; margin: 0 0 30px; line-height: 1.5; }
.cover .subject-name { font-size: 20px; color: #dbe4f8; margin-bottom: 4px; }
.cover .cover-meta { font-size: 12.5px; color: #9fb0d6; margin-top: 24px; }
.cover .cover-badge { margin-top: 28px; }
.cover .cover-rule { width: 64px; height: 2px; background: var(--gold); margin: 22px 0; border: none; }
.cover .cover-prepared-for { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: #9fb0d6; margin-top: 30px; }
.cover .cover-teaser { display: flex; gap: 22px; margin-top: 26px; flex-wrap: wrap; justify-content: center; }
.cover .cover-teaser-item { min-width: 130px; }
.cover .cover-teaser-label { font-size: 10px; letter-spacing: .06em; text-transform: uppercase; color: #9fb0d6; }
.cover .cover-teaser-value { font-size: 16px; font-weight: 700; color: #fff; margin-top: 2px; }
.cover .cover-confidential { position: absolute; bottom: 28px; font-size: 10.5px; color: #7d8bb0; letter-spacing: .04em; }

/* ---- print-only table of contents page ---- */
.toc-page { display: none; }
.toc-page h2 { font-size: 22px; margin-bottom: 4px; }
.toc-page .toc-sub { font-size: 12.5px; color: var(--ink-soft); margin: 0 0 20px; }
.toc-page ol { list-style: none; margin: 0; padding: 0; counter-reset: toc-counter; }
.toc-page ol li {
  counter-increment: toc-counter; display: flex; align-items: baseline; gap: 10px;
  padding: 9px 0; border-bottom: 1px dotted var(--line); font-size: 14px;
}
.toc-page ol li::before {
  content: counter(toc-counter) "."; color: var(--gold); font-weight: 700; min-width: 22px;
}
.toc-page ol li .toc-part-label {
  font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-soft); margin-left: auto;
}

/* ---- dense professional report layout ----
   The hero already carries every fact from the former full-viewport cover.
   Keeping both wasted an entire screen/page before any decision content.
   The cover remains in the DOM for backward-compatible HTML consumers but
   is visually suppressed on screen -- re-enabled for print below, as a
   proper print title page/table-of-contents, per the "professional
   printable report" audit pass. */
.cover { display: none; }
body { background: #eef2f7; line-height: 1.42; }
.wrap { max-width: 1480px; padding: 12px 22px 28px; }
.hero { padding: 18px 22px 16px; border-bottom: 3px solid var(--gold); }
.hero-inner, nav.viewswitch .vs-inner, nav.tabs .tabs-inner { max-width: 1480px; }
.hero h1 { font-size: 24px; margin-bottom: 2px; }
.hero .kicker { margin-bottom: 3px; }
.final-verdict-value { font-size: 21px; }
nav.viewswitch .vs-inner { padding: 6px 22px; gap: 10px; }
.vs-btn { padding: 6px 14px; font-size: 12.5px; }
.has-viewswitch nav.tabs { top: 41px; }
nav.tabs .tabs-inner { padding: 0 16px; }
nav.tabs a { padding: 9px 11px 8px; font-size: 12px; }
h2 { font-size: 17px; margin: 0 0 7px; padding-top: 1px; }
h3 { font-size: 14px; margin: 10px 0 6px; }
p { font-size: 13px; line-height: 1.42; margin: 6px 0; }
section { min-width: 0; margin: 0; }
.card { border-radius: 8px; padding: 10px 13px; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(18,33,63,.05); }
.disclaimer { padding: 9px 13px; margin: 0 0 10px; border-radius: 8px; }
.disclaimer p, .disclaimer li { font-size: 11.5px; line-height: 1.35; }
.kpi-grid { grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 7px; margin: 9px 0 2px; }
.kpi-card { border-radius: 8px; padding: 8px 10px; box-shadow: none; }
.kpi-card .kpi-value { font-size: 21px; margin: 1px 0; }
.kpi-card .kpi-label, .kpi-card .kpi-hint { font-size: 10.5px; }
.grid-2 { gap: 9px; }
th, td { padding: 5px 7px; font-size: 11.7px; line-height: 1.28; }
th { font-size: 10.5px; position: sticky; top: 82px; z-index: 2; }
.badge { padding: 3px 8px; font-size: 10.5px; }
.window-block { padding: 8px 10px; margin-bottom: 6px; border-radius: 7px; }
.windows-grid { grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 7px; }
.sector-leaderboard { gap: 6px; }
.sector-row { flex-basis: 410px; grid-template-columns: 28px 1fr minmax(105px, 135px); gap: 9px; padding: 7px 9px; border-radius: 7px; }
.item-grid { gap: 6px; }
.item-grid li { flex-basis: 235px; padding: 7px 9px; font-size: 12px; line-height: 1.35; border-radius: 6px; }
details summary { font-size: 11.5px; }
details ul { font-size: 11.5px; }
footer { margin-top: 14px; padding-top: 8px; }

/* Client/profile view: pair compact evidence sections while preserving a
   full-width reading lane for the decision, KPIs, sectors and timing. */
#view-profile.active { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 10px 12px; }
#view-profile > .disclaimer,
#view-profile > #p-verdict-reconciliation,
#view-profile > #p-recommendation,
#view-profile > #p-promise-fields,
#view-profile > #p-sectors,
#view-profile > #p-timed-windows { grid-column: 1 / -1; }
#view-profile > section { grid-column: span 6; }

/* Technical view: keep data-heavy ledgers full width; arrange concise
   decision/status modules in two columns. */
#view-astrologer.active { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 10px 12px; }
#view-astrologer > .disclaimer,
#view-astrologer > #a-verdict-reconciliation,
#view-astrologer > #a-promise-fields,
#view-astrologer > #a-significators,
#view-astrologer > #a-sectors,
#view-astrologer > #a-timed-windows,
#view-astrologer > #a-method-status { grid-column: 1 / -1; }
#view-astrologer > section { grid-column: span 6; }

@media (max-width: 900px) {
  .wrap { padding: 10px 12px 24px; }
  .hero { padding: 15px 14px; }
  .hero-inner { align-items: flex-start; }
  .hero-recommend, .final-verdict { text-align: left; }
  #view-profile.active, #view-astrologer.active { display: block; }
  #view-profile > section, #view-astrologer > section { margin-bottom: 10px; }
  .sector-row { grid-template-columns: 24px 1fr; }
  .sector-meta { grid-column: 2; justify-content: flex-start; }
  th { position: static; }
}

@media print {
  /* Audit fix: named running header/footer via CSS page-margin boxes plus
     a page counter, so a printed/PDF report -- which can run to dozens of
     pages once evidence ledgers are included -- carries a page number and
     the subject's identity on every page instead of only the first. Page-
     margin @page content is supported by Chromium's Print-to-PDF (the
     realistic path most users take) and by weasyprint; browsers without
     support simply show no footer text, never an error. */
  @page {
    size: A4; margin: 16mm 10mm 14mm;
    @bottom-center { content: "Business Astrology Report -- Page " counter(page) " of " counter(pages); font-size: 9px; color: #7a8296; }
  }
  nav.tabs, nav.viewswitch { display: none; }
  .print-toolbar { display: none !important; }
  /* "Professional printable report" pass: a real title page and table of
     contents at the front of the printed/PDF document -- previously
     .cover was suppressed everywhere (screen AND print), so a printed
     copy of a 40-90 page report opened directly on its dense data hero
     with no title page at all. Screen behavior is untouched (the compact
     hero still serves that role there, where screen space is precious);
     this only changes what Print-to-PDF produces. */
  .cover {
    display: flex !important; min-height: auto; height: 277mm; position: relative;
    page-break-after: always; break-after: page;
  }
  .toc-page {
    display: block !important; padding: 20mm 14mm; page-break-after: always; break-after: page;
  }
  /* Content-restructuring pass (item 9): the Technical Appendix divider
     starts a fresh printed page/section, so a long printed report reads
     as "Part 1: Decision Summary" then "Part 2: Technical Appendix"
     instead of one undifferentiated scroll transplanted onto paper. */
  .technical-appendix-divider { page-break-before: always; break-before: page; background: #f3f3f6 !important; }
  /* Combined report: both toggled panels print in full, one after the
     other, instead of only whichever one was active on screen. */
  .view { display: block !important; page-break-before: always; }
  .cover { display: none !important; }
  .hero { padding: 8mm 5mm 5mm; }
  .card, .kpi-card, .sector-row, .window-block, .item-grid li, .glossary { box-shadow: none; break-inside: avoid; page-break-inside: avoid; }
  h2 { page-break-after: avoid; break-after: avoid; }
  /* Long sections (tables, timing ledgers) must be allowed to split;
     forbidding section breaks was the main source of blank half-pages. */
  section { page-break-inside: auto; break-inside: auto; }
  body { background: #fff; }
  .wrap { max-width: 100%; padding: 3mm 0 6mm; }
  #view-profile, #view-astrologer { display: block !important; }
  #view-profile > section, #view-astrologer > section { margin-bottom: 3mm; }
  th { position: static; }
  /* Audit fix: repeat the table header row on every printed page a long
     evidence table spans (this report's significator ledgers can run to
     30+ rows) instead of only showing column headers on the first page a
     table starts on, and keep individual rows from being split across a
     page break mid-row. */
  thead { display: table-header-group; }
  tfoot { display: table-footer-group; }
  tr { break-inside: avoid; page-break-inside: avoid; }
  table { break-inside: auto; page-break-inside: auto; }
  /* Force single-column stacking for the item-grid / sector-leaderboard /
     windows-grid flex layouts in print so weasyprint/browser Print-to-PDF
     never has to lay out wrapped flex rows across a forced page break. */
  .item-grid, .sector-leaderboard, .windows-grid { display: block; }
  .item-grid li, .sector-row, .window-block { margin-bottom: 8px; }
  /* Audit fix: hyperlink URLs are meaningless on paper and clutter a
     printed page if any external links are ever added to this template. */
  a[href]::after { content: ""; }
}
"""


def _print_toolbar_html(lang: str = "en") -> str:
    """Screen-only floating "Print / Save as PDF" button. Never visible in
    the printed/PDF output itself (.print-toolbar is forced display:none
    inside @media print in _shared_css()) -- it exists purely so a reader
    viewing the report in a browser has an obvious, one-click path to a
    printable/PDF copy instead of having to know Ctrl/Cmd+P themselves."""
    label = _t(lang, "print_button", "Print / Save as PDF")
    return f"""
<div class="print-toolbar">
  <button class="print-btn" type="button" onclick="window.print()" aria-label="{_esc(label)}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
    {_esc(label)}
  </button>
</div>"""


# Plain-language definitions for the classical-astrology vocabulary this
# report uses throughout (house-lord evidence tables, yoga names, varga
# chart references, KP/Jaimini terminology). Kept as one ordered list of
# (term, definition) pairs -- rendered once, near the top of the report,
# so a reader unfamiliar with Vedic astrology jargon has a plain-language
# reference without needing to look anything up outside the document, and
# so the definitions are guaranteed to survive Print-to-PDF (a hover
# tooltip would not survive being printed onto paper).
_GLOSSARY_TERMS: List[Tuple[str, str]] = [
    ("Lagna (Ascendant)", "The sign rising on the eastern horizon at the exact moment of birth. It anchors the entire chart -- every house is counted from it -- and its lord's strength reflects personal agency and self-driven initiative, including the confidence to start a venture."),
    ("House (Bhava)", "One of 12 divisions of the chart, each governing a specific life domain -- e.g. the 2nd house is accumulated wealth, the 7th is partnership/trade, the 10th is career/status. This report scores which houses are active and well-supported for business purposes."),
    ("House Lord", "The planet that rules the sign occupying a given house. A house's strength is read largely through where its lord sits, how it's placed relative to that house, and its own dignity -- not just what occupies the house itself."),
    ("Kendra / Trikona / Dusthana", "Three house groupings classical texts treat very differently. Kendras (1st/4th/7th/10th) are pillars of strength and stability. Trikonas (1st/5th/9th) are houses of fortune and merit. Dusthanas (6th/8th/12th) are houses of struggle, debt, and loss -- a planet's placement in one of these groups materially changes how its influence is read."),
    ("Dignity (Exalted / Own Sign / Debilitated / Moolatrikona)", "How comfortable and empowered a planet is in the sign it occupies. Exalted is a planet's strongest placement; debilitated is its weakest; own sign and moolatrikona are strong, stable placements in between. Dignity is used throughout this report to decide how much weight a given piece of evidence carries."),
    ("Yoga", "A specific, named planetary combination that classical texts associate with a particular life outcome -- e.g. Raja Yoga (status/power) or Dhana Yoga (wealth). These are recurring patterns astrologers watch for, not a one-off reading of any single planet."),
    ("Dasha (Mahadasha / Antardasha)", "The classical timing system that divides a lifetime into planetary periods (Mahadasha, further subdivided into Antardasha) during which that planet's significations are considered most active. This report's timed-window sections use this system to flag favorable and cautionary periods ahead."),
    ("Varga (Divisional) Charts -- D9, D10, D24, D60", "Charts derived mathematically from the birth chart (D1) that each zoom into one life theme for finer-grained confirmation: D9 (Navamsha) for marriage/general fortune and the durability of a promise, D10 (Dashamsha) for career/livelihood execution specifically, D24 for learning/competency, D60 for a fine-grained reliability check. This report cross-checks D1 findings against these charts rather than relying on the birth chart alone."),
    ("KP (Krishnamurti Paddhati) Sub-Lord", "A modern refinement of house-cusp analysis that subdivides each sign further by nakshatra sub-lord for very precise yes/no-style questions (e.g. job vs. business). Used in this report only when the underlying chart's house system is confirmed Placidus -- otherwise it's shown for reference only and excluded from scoring."),
    ("Jaimini Karakas (Atmakaraka / Amatyakaraka)", "An alternate classical system (Jaimini astrology) that ranks planets by degree within their sign rather than by house lordship. The Atmakaraka (soul significator, highest degree) and Amatyakaraka (career significator, second-highest) anchor a separate line of professional-direction evidence used to corroborate -- not replace -- the house-lord findings."),
    ("Nakshatra", "One of 27 lunar constellations the Moon (and every other point in the chart) falls into, each with its own significations and ruling planet -- used here for finer-grained business-aptitude and timing evidence beyond sign-level placement alone."),
    ("Retrograde", "A planet's apparent backward motion from Earth's vantage point. Classically read as an internalized, revisited, or delayed -- not blocked -- expression of that planet's significations; this report notes it as a citation, not a penalty, wherever it's relevant."),
    ("Rahu / Ketu (Lunar Nodes)", "The two shadow points marking where the Moon's orbit crosses the ecliptic. Rahu is associated with amplification, foreign/unconventional pursuits, and worldly ambition; Ketu with detachment, research depth, and letting go. Their dignity/strength readings vary more by classical school than other planets' do -- see the maturity disclosures in this report for that caveat."),
]

# Tamil/Telugu translations of _GLOSSARY_TERMS above, in the exact same
# order, so _glossary_section_html() can zip them positionally against the
# English list -- keeps translation-completeness trivial to audit (any
# list here shorter than _GLOSSARY_TERMS is caught explicitly below rather
# than silently mis-pairing terms with the wrong definition).
_GLOSSARY_TERMS_TR: Dict[str, List[Tuple[str, str]]] = {
    "ta": [
        ("லக்னம் (உதயம்)", "பிறந்த நேரம் கிழக்கு அடிவானத்தில் உதிக்கும் ராசி. இது முழு ஜாதகத்தின் அடிப்படை — ஒவ்வொரு வீடும் இதிலிருந்தே எண்ணப்படுகிறது; அதன் அதிபதியின் வலிமை தனிப்பட்ட முன்முயற்சி மற்றும் ஒரு தொழிலைத் தொடங்கும் தன்னம்பிக்கையை பிரதிபலிக்கிறது."),
        ("வீடு (பாவம்)", "ஜாதகத்தின் 12 பிரிவுகளில் ஒன்று, ஒவ்வொன்றும் ஒரு குறிப்பிட்ட வாழ்க்கைத் துறையை ஆளுகிறது — எ.கா. 2ஆம் வீடு சேமித்த செல்வம், 7ஆம் வீடு கூட்டாண்மை/வர்த்தகம், 10ஆம் வீடு தொழில்/அந்தஸ்து. இந்த அறிக்கை வணிக நோக்கத்திற்காக எந்த வீடுகள் செயலில் மற்றும் நன்கு ஆதரிக்கப்படுகின்றன என்பதை மதிப்பிடுகிறது."),
        ("வீட்டு அதிபதி", "ஒரு குறிப்பிட்ட வீட்டை ஆக்கிரமிக்கும் ராசியை ஆளும் கிரகம். ஒரு வீட்டின் வலிமை பெரும்பாலும் அதன் அதிபதி எங்கே அமர்ந்துள்ளது, அந்த வீட்டிற்கு ஒப்பீட்டளவில் அது எவ்வாறு அமைந்துள்ளது, மற்றும் அதன் சொந்த கண்ணியம் ஆகியவற்றின் மூலம் படிக்கப்படுகிறது — வீட்டில் என்ன உள்ளது என்பது மட்டும் அல்ல."),
        ("கேந்திரம் / திரிகோணம் / துஸ்தானம்", "பாரம்பரிய நூல்கள் மிகவும் வித்தியாசமாக நடத்தும் மூன்று வீட்டு குழுக்கள். கேந்திரங்கள் (1,4,7,10) வலிமை மற்றும் ஸ்திரத்தன்மையின் தூண்கள். திரிகோணங்கள் (1,5,9) பாக்கியம் மற்றும் தகுதியின் வீடுகள். துஸ்தானங்கள் (6,8,12) போராட்டம், கடன் மற்றும் இழப்பின் வீடுகள் — ஒரு கிரகம் இந்த குழுக்களில் எங்கு அமைந்துள்ளது என்பது அதன் தாக்கத்தை பெரிதும் மாற்றுகிறது."),
        ("கண்ணியம் (உச்சம் / சொந்த வீடு / நீசம் / மூலத்ரிகோணம்)", "ஒரு கிரகம் அது அமைந்துள்ள ராசியில் எவ்வளவு வசதியாகவும் வலிமையாகவும் உள்ளது என்பது. உச்சம் என்பது ஒரு கிரகத்தின் மிக வலிமையான நிலை; நீசம் மிகவும் பலவீனமானது; சொந்த வீடு மற்றும் மூலத்ரிகோணம் இடையே உள்ள வலிமையான, நிலையான நிலைகள். இந்த அறிக்கை முழுவதும் கண்ணியம் என்பது ஒரு குறிப்பிட்ட ஆதாரம் எவ்வளவு எடையுடையது என்பதை தீர்மானிக்கப் பயன்படுகிறது."),
        ("யோகம்", "பாரம்பரிய நூல்கள் ஒரு குறிப்பிட்ட வாழ்க்கை விளைவுடன் தொடர்புபடுத்தும் ஒரு குறிப்பிட்ட, பெயரிடப்பட்ட கிரக சேர்க்கை — எ.கா. ராஜயோகம் (அந்தஸ்து/அதிகாரம்) அல்லது தனயோகம் (செல்வம்). இவை ஜோதிடர்கள் கவனிக்கும் மீண்டும் மீண்டும் வரும் வடிவங்கள், ஒரு கிரகத்தின் ஒரு முறை வாசிப்பு அல்ல."),
        ("தசை (மகாதசை / அந்தர்தசை)", "ஒரு வாழ்நாளை கிரக காலங்களாக (மகாதசை, மேலும் அந்தர்தசையாக பிரிக்கப்படும்) பிரிக்கும் பாரம்பரிய காலநேர முறை, அப்போது அந்த கிரகத்தின் அறிகுறிகள் மிகவும் செயலில் இருப்பதாக கருதப்படுகிறது. இந்த அறிக்கையின் காலக்கெடு சாளர பிரிவுகள் முன்னால் உள்ள சாதகமான மற்றும் எச்சரிக்கை காலகட்டங்களைக் குறிக்க இந்த முறையைப் பயன்படுத்துகின்றன."),
        ("பிரிவு (வர்க்க) ஜாதகங்கள் -- D9, D10, D24, D60", "பிறப்பு ஜாதகத்திலிருந்து (D1) கணிதரீதியாக பெறப்பட்ட ஜாதகங்கள், ஒவ்வொன்றும் ஒரு வாழ்க்கை கருப்பொருளில் நுணுக்கமான உறுதிப்படுத்தலுக்காக கவனம் செலுத்துகிறது: D9 (நவாம்சம்) திருமணம்/பொது பாக்கியம் மற்றும் ஒரு வாக்குறுதியின் நீடித்தன்மைக்கு, D10 (தசாம்சம்) குறிப்பாக தொழில்/வாழ்வாதார செயல்பாட்டுக்கு, D24 கற்றல்/திறமைக்கு, D60 நுணுக்கமான நம்பகத்தன்மை சரிபார்ப்புக்கு. இந்த அறிக்கை பிறப்பு ஜாதகத்தை மட்டும் நம்பாமல் D1 கண்டுபிடிப்புகளை இந்த ஜாதகங்களுக்கு எதிராக குறுக்கு-சரிபார்க்கிறது."),
        ("KP (கிருஷ்ணமூர்த்தி பத்ததி) துணை அதிபதி", "வீட்டு எல்லைக் கோடு பகுப்பாய்வின் நவீன செம்மைப்படுத்தல், மிகவும் துல்லியமான ஆம்/இல்லை பாணி கேள்விகளுக்காக (எ.கா. வேலையா வணிகமா) நட்சத்திர துணை அதிபதி மூலம் ஒவ்வொரு ராசியையும் மேலும் உட்பிரிவு செய்கிறது. அடிப்படை ஜாதகத்தின் வீட்டு முறை பிளாசிடஸ் என்று உறுதிப்படுத்தப்பட்டால் மட்டுமே இந்த அறிக்கையில் பயன்படுத்தப்படுகிறது — இல்லையெனில் இது குறிப்புக்காக மட்டுமே காட்டப்பட்டு மதிப்பீட்டிலிருந்து விலக்கப்படுகிறது."),
        ("ஜைமினி காரகங்கள் (ஆத்மகாரகன் / அமாத்யகாரகன்)", "ஒரு மாற்று பாரம்பரிய முறை (ஜைமினி ஜோதிடம்) வீட்டு அதிபதித்துவத்தை விட ராசியில் உள்ள பாகைகளின் அடிப்படையில் கிரகங்களை தரவரிசைப்படுத்துகிறது. ஆத்மகாரகன் (ஆன்மா குறிகாட்டி, அதிக பாகை) மற்றும் அமாத்யகாரகன் (தொழில் குறிகாட்டி, இரண்டாவது அதிக பாகை) ஒரு தனி தொழில்-திசை ஆதார வரிசையை நிலைநிறுத்துகின்றன — வீட்டு அதிபதி கண்டுபிடிப்புகளை மாற்றாமல் உறுதிப்படுத்த."),
        ("நட்சத்திரம்", "27 சந்திர நட்சத்திரங்களில் ஒன்று, சந்திரன் (மற்றும் ஜாதகத்தில் உள்ள மற்ற ஒவ்வொரு புள்ளியும்) விழும் இடம், ஒவ்வொன்றும் அதன் சொந்த அறிகுறிகள் மற்றும் ஆளும் கிரகத்துடன் — ராசி மட்ட இருப்பிடத்தை தாண்டி நுணுக்கமான வணிக-திறன் மற்றும் காலநேர ஆதாரத்திற்காக இங்கு பயன்படுத்தப்படுகிறது."),
        ("வக்ரம் (Retrograde)", "பூமியின் பார்வையிலிருந்து ஒரு கிரகத்தின் வெளித்தோற்ற பின்னோக்கிய இயக்கம். பாரம்பரியமாக அந்த கிரகத்தின் அறிகுறிகளின் உள்வாங்கப்பட்ட, மறுபரிசீலனை செய்யப்பட்ட அல்லது தாமதமான — தடுக்கப்பட்டதல்ல — வெளிப்பாடாக படிக்கப்படுகிறது; இந்த அறிக்கை இது தொடர்புடைய இடங்களில் இதை ஒரு மேற்கோளாக குறிப்பிடுகிறது, தண்டனையாக அல்ல."),
        ("ராகு / கேது (சாயா கிரகங்கள்)", "சந்திரனின் சுற்றுப்பாதை கிரகணப் பாதையை கடக்கும் இடங்களைக் குறிக்கும் இரண்டு நிழல் புள்ளிகள். ராகு பெருக்கம், வெளிநாடு/வழக்கத்திற்கு மாறான முயற்சிகள் மற்றும் உலகியல் லட்சியத்துடன் தொடர்புடையது; கேது பற்றின்மை, ஆராய்ச்சி ஆழம் மற்றும் விடுதலையுடன். அவற்றின் கண்ணியம்/வலிமை வாசிப்புகள் மற்ற கிரகங்களை விட பாரம்பரிய பள்ளிக்கு ஏற்ப அதிகம் மாறுபடும் — இந்த அறிக்கையில் அந்த எச்சரிக்கைக்கு முதிர்ச்சி வெளிப்பாடுகளைப் பார்க்கவும்."),
    ],
    "te": [
        ("లగ్నం (ఉదయం)", "జన్మ సమయంలో తూర్పు క్షితిజంపై ఉదయించే రాశి. ఇది మొత్తం జాతకానికి ఆధారం — ప్రతి ఇల్లు దీని నుండే లెక్కించబడుతుంది; దాని అధిపతి బలం వ్యక్తిగత చొరవ మరియు ఒక వ్యాపారాన్ని ప్రారంభించే ఆత్మవిశ్వాసాన్ని ప్రతిబింబిస్తుంది."),
        ("ఇల్లు (భావం)", "జాతకంలోని 12 విభాగాలలో ఒకటి, ప్రతి ఒక్కటి ఒక నిర్దిష్ట జీవిత రంగాన్ని పరిపాలిస్తుంది — ఉదా. 2వ ఇల్లు కూడబెట్టిన సంపద, 7వ ఇల్లు భాగస్వామ్యం/వ్యాపారం, 10వ ఇల్లు వృత్తి/హోదా. ఈ నివేదిక వ్యాపార ప్రయోజనాల కోసం ఏ ఇళ్లు చురుకుగా మరియు బాగా మద్దతు ఇవ్వబడుతున్నాయో అంచనా వేస్తుంది."),
        ("ఇంటి అధిపతి", "ఒక నిర్దిష్ట ఇంటిని ఆక్రమించే రాశిని పాలించే గ్రహం. ఒక ఇంటి బలం ఎక్కువగా దాని అధిపతి ఎక్కడ కూర్చున్నాడు, ఆ ఇంటికి సాపేక్షంగా అది ఎలా ఉంచబడింది, మరియు దాని స్వంత గౌరవం ద్వారా చదవబడుతుంది — ఇంట్లో ఏమి ఉంది అనేది మాత్రమే కాదు."),
        ("కేంద్రం / త్రికోణం / దుస్థానం", "శాస్త్రీయ గ్రంథాలు చాలా భిన్నంగా పరిగణించే మూడు ఇంటి సమూహాలు. కేంద్రాలు (1,4,7,10) బలం మరియు స్థిరత్వానికి స్తంభాలు. త్రికోణాలు (1,5,9) అదృష్టం మరియు యోగ్యత ఇళ్లు. దుస్థానాలు (6,8,12) పోరాటం, అప్పు మరియు నష్టం ఇళ్లు — ఒక గ్రహం ఈ సమూహాలలో ఎక్కడ ఉందో అది దాని ప్రభావాన్ని గణనీయంగా మారుస్తుంది."),
        ("గౌరవం (ఉచ్ఛ / స్వరాశి / నీచ / మూలత్రికోణ)", "ఒక గ్రహం అది ఆక్రమించిన రాశిలో ఎంత సౌకర్యవంతంగా మరియు శక్తివంతంగా ఉందో. ఉచ్ఛ అనేది గ్రహం యొక్క బలమైన స్థానం; నీచ దాని బలహీనమైనది; స్వరాశి మరియు మూలత్రికోణ మధ్యస్థంగా బలమైన, స్థిరమైన స్థానాలు. ఈ నివేదిక అంతటా గౌరవం ఒక నిర్దిష్ట ఆధారం ఎంత బరువుగా ఉంటుందో నిర్ణయించడానికి ఉపయోగించబడుతుంది."),
        ("యోగం", "శాస్త్రీయ గ్రంథాలు ఒక నిర్దిష్ట జీవిత ఫలితంతో అనుసంధానించే ఒక నిర్దిష్ట, పేరు పెట్టబడిన గ్రహ కలయిక — ఉదా. రాజయోగం (హోదా/అధికారం) లేదా ధనయోగం (సంపద). ఇవి జ్యోతిష్కులు గమనించే పునరావృత నమూనాలు, ఒక్క గ్రహం యొక్క ఒకసారి పఠనం కాదు."),
        ("దశ (మహాదశ / అంతర్దశ)", "ఒక జీవితకాలాన్ని గ్రహ కాలాలుగా (మహాదశ, మరింత అంతర్దశగా విభజించబడింది) విభజించే శాస్త్రీయ కాల వ్యవస్థ, ఆ సమయంలో ఆ గ్రహం యొక్క సూచనలు అత్యంత చురుకుగా పరిగణించబడతాయి. ఈ నివేదిక యొక్క సమయ విండో విభాగాలు ముందున్న అనుకూలమైన మరియు జాగ్రత్త కాలాలను గుర్తించడానికి ఈ వ్యవస్థను ఉపయోగిస్తాయి."),
        ("విభాగ (వర్గ) జాతకాలు -- D9, D10, D24, D60", "జన్మ జాతకం (D1) నుండి గణితశాస్త్రపరంగా ఉత్పన్నమైన జాతకాలు, ప్రతి ఒక్కటి ఒక జీవిత అంశంపై సూక్ష్మ నిర్ధారణ కోసం దృష్టి పెడుతుంది: D9 (నవాంశ) వివాహం/సాధారణ అదృష్టం మరియు వాగ్దానం యొక్క మన్నికకు, D10 (దశాంశ) ప్రత్యేకంగా వృత్తి/జీవనోపాధి అమలుకు, D24 అభ్యాసం/సామర్థ్యానికి, D60 సూక్ష్మ విశ్వసనీయత తనిఖీకి. ఈ నివేదిక జన్మ జాతకంపై మాత్రమే ఆధారపడకుండా D1 ఫలితాలను ఈ జాతకాలకు వ్యతిరేకంగా క్రాస్-చెక్ చేస్తుంది."),
        ("KP (కృష్ణమూర్తి పద్ధతి) ఉప-అధిపతి", "ఇంటి కస్ప్ విశ్లేషణ యొక్క ఆధునిక శుద్ధీకరణ, చాలా ఖచ్చితమైన అవును/కాదు తరహా ప్రశ్నల కోసం (ఉదా. ఉద్యోగమా వ్యాపారమా) నక్షత్ర ఉప-అధిపతి ద్వారా ప్రతి రాశిని మరింత ఉప-విభజిస్తుంది. అంతర్లీన జాతకం యొక్క ఇంటి వ్యవస్థ ప్లాసిడస్ అని నిర్ధారించబడినప్పుడు మాత్రమే ఈ నివేదికలో ఉపయోగించబడుతుంది — లేకపోతే ఇది సూచన కోసం మాత్రమే చూపబడి స్కోరింగ్ నుండి మినహాయించబడుతుంది."),
        ("జైమిని కారకాలు (ఆత్మకారక / అమాత్యకారక)", "ఇంటి అధిపత్యానికి బదులుగా వారి రాశిలోని డిగ్రీల ద్వారా గ్రహాలను ర్యాంక్ చేసే ప్రత్యామ్నాయ శాస్త్రీయ వ్యవస్థ (జైమిని జ్యోతిష్యం). ఆత్మకారక (ఆత్మ సూచిక, అత్యధిక డిగ్రీ) మరియు అమాత్యకారక (వృత్తి సూచిక, రెండవ అత్యధిక డిగ్రీ) ఒక ప్రత్యేక వృత్తి-దిశ ఆధార రేఖను స్థాపిస్తాయి — ఇంటి-అధిపతి ఫలితాలను భర్తీ చేయకుండా నిర్ధారించడానికి."),
        ("నక్షత్రం", "27 చంద్ర నక్షత్రాలలో ఒకటి, చంద్రుడు (మరియు జాతకంలోని ప్రతి ఇతర బిందువు) పడే స్థానం, ప్రతి ఒక్కటి దాని స్వంత సూచనలు మరియు పాలక గ్రహంతో — రాశి-స్థాయి స్థానానికి మించి సూక్ష్మ వ్యాపార-సామర్థ్యం మరియు సమయ ఆధారం కోసం ఇక్కడ ఉపయోగించబడుతుంది."),
        ("వక్రి (Retrograde)", "భూమి దృక్కోణం నుండి గ్రహం యొక్క స్పష్టమైన వెనుకకు కదలిక. శాస్త్రీయంగా ఆ గ్రహం యొక్క సూచనల యొక్క అంతర్గతీకరించిన, పునఃసందర్శించిన లేదా ఆలస్యమైన — నిరోధించబడని — వ్యక్తీకరణగా చదవబడుతుంది; ఈ నివేదిక దీన్ని సంబంధిత ప్రతిచోటా ఒక ఉదాహరణగా గమనిస్తుంది, జరిమానాగా కాదు."),
        ("రాహు / కేతు (ఛాయా గ్రహాలు)", "చంద్రుని కక్ష్య గ్రహణ మార్గాన్ని దాటే స్థానాలను గుర్తించే రెండు నీడ బిందువులు. రాహు విస్తరణ, విదేశీ/అసాధారణ కార్యకలాపాలు మరియు ప్రాపంచిక ఆశయంతో సంబంధం కలిగి ఉంటుంది; కేతు నిర్లిప్తత, పరిశోధన లోతు మరియు వదిలివేయడంతో. వాటి గౌరవం/బలం పఠనాలు ఇతర గ్రహాల కంటే శాస్త్రీయ పాఠశాల ప్రకారం ఎక్కువగా మారుతూ ఉంటాయి — ఆ హెచ్చరిక కోసం ఈ నివేదికలోని పరిపక్వత వెల్లడింపులను చూడండి."),
    ],
}


def _glossary_section_html(lang: str = "en") -> str:
    """Renders the plain-language "How to Read This Report" glossary once,
    outside the toggled Chart Profile / Astrologer View panels, so it
    appears exactly once regardless of which view is active on screen and
    exactly once in the printed/PDF output (see .glossary's page-break-
    avoidance rule in _shared_css()). Always fully expanded/static (not a
    collapsible <details>) so its content is guaranteed visible on paper --
    a closed <details> element's content is dropped by most browsers'
    Print-to-PDF path, which would silently defeat the whole purpose of
    adding this section to a report meant to be printable.

    lang: looks up _GLOSSARY_TERMS_TR[lang] (same term order as the English
    _GLOSSARY_TERMS list) when available. Falls back to English per-term if
    the translated list for this language is missing or -- defensively --
    shorter than the English list, so a future edit that adds an English
    term without also adding its translation degrades to showing that one
    term in English rather than raising or silently mis-pairing a
    translated definition against the wrong term."""
    translated = _GLOSSARY_TERMS_TR.get(lang) if lang != "en" else None
    pairs = []
    for i, (term_en, definition_en) in enumerate(_GLOSSARY_TERMS):
        if translated and i < len(translated):
            term, definition = translated[i]
        else:
            term, definition = term_en, definition_en
        pairs.append((term, definition))
    items = "".join(
        f"<dt>{_esc(term)}</dt><dd>{_esc(definition)}</dd>"
        for term, definition in pairs
    )
    title = _t(lang, "glossary_title", "How to Read This Report — Astrological Terms Explained")
    intro = _t(
        lang, "glossary_intro",
        "This report cites classical Vedic-astrology terminology throughout (house lords, yogas, "
        "dignity, divisional charts, dasha periods, and more). Each term below is defined in plain "
        "language once, here, so you can look anything up without leaving the document — including "
        "in a printed or PDF copy."
    )
    return f"""
<section class="glossary" id="glossary">
  <h2>{_esc(title)}</h2>
  <p class="glossary-intro">{_esc(intro)}</p>
  <dl class="glossary-grid">{items}</dl>
</section>"""


def _prepare_common_sections(name: str, prediction: Dict[str, Any], lang: str = "en", payload: Optional[Any] = None) -> Dict[str, Any]:
    """Computes every section-HTML fragment shared by both the astrologer
    and the client reports, exactly once, from the same prediction dict --
    so the two deliverables can never drift into showing different
    numbers for the same underlying field. Which fragments each report
    actually uses (and at what level of technical detail) is decided by
    the two render_*_report_html() functions below, not here.

    lang: 'ta' / 'te' / 'en'. Fixed-vocabulary labels/headers/enum values
    are translated deterministically via _lt(). Free-form engine-generated
    prose (signals, risk signals, contradiction notes, window evidence,
    arbitration-ledger actions, method-status details, the recommendation
    reasoning sentence, the maturity statement/caveats) is translated in
    ONE batched LLM call via _translate_texts_llm() so the entire report
    body -- not just its static chrome -- renders in the target language.
    If that call is unavailable (no consent/key, or the provider can't be
    reached), `translation_incomplete` is returned True so callers can
    show an explicit on-page notice. v37 hard-enforcement fix: previously
    the untranslated ENGLISH originals were shown inline in that case,
    which technically satisfied "best effort" but violated the explicit
    "no English words, strongly enforce" requirement for Tamil/Telugu
    output -- a reader could still see raw English sentences mixed into an
    otherwise-Tamil report. Now, whenever translation is unavailable for a
    non-English report, every affected dynamic sentence is replaced with a
    short, fully-native-script placeholder (never the English original),
    so no English can leak into the page regardless of LLM availability;
    the on-page notice still explains why some detail is condensed.
    """
    translation_incomplete = False

    def _dyn(texts: List[str]) -> List[str]:
        nonlocal translation_incomplete
        if lang == "en" or not texts:
            return list(texts)
        result = _translate_texts_llm(texts, lang, payload=payload)
        if result is None:
            translation_incomplete = True
            placeholder = _UNAVAILABLE_PLACEHOLDER.get(lang, _UNAVAILABLE_PLACEHOLDER["ta"])
            return [placeholder if t else t for t in texts]
        return result

    sig = prediction["significators"]
    rec = prediction["recommendation"]
    timing_status = prediction.get("timing_status", {})
    method_status = prediction.get("method_status", {})
    model_status = prediction.get("model_status", "UNKNOWN")
    calibration_status = prediction.get("calibration_status", "UNKNOWN")
    maturity_statement = prediction.get("maturity_statement", "")
    maturity_caveats = prediction.get("maturity_caveats", [])
    forecast_window = prediction.get("forecast_window", {})

    # v17: nine separately-computed promise/fit/confidence fields, plus the
    # supporting operating-model/contradiction/D24/D60/KP-10th-cusp/sign-
    # modality layers -- rendered as their own report section rather than
    # folded into the mode-gate table, since the whole point of the v17
    # audit fix was that these are DISTINCT determinations, not aliases of
    # employment_score/business_score.
    confidence = prediction.get("business_over_job_confidence", {}) or {}
    operating_model = prediction.get("operating_model", {}) or {}
    contradiction_findings = prediction.get("contradiction_findings", []) or []
    d24_status = prediction.get("d24_competency_status", {}) or {}
    d60_status = prediction.get("d60_confirmation_status", {}) or {}
    sign_modality = prediction.get("sign_modality_profile", {}) or {}
    kp10 = prediction.get("kp_10th_cusp_job_vs_business", {}) or {}

    # Uplift: the report's most important numbers (the nine spec-named
    # promise/fit/confidence fields) were previously buried as rows 1-9 of
    # a 15-row generic table, indistinguishable from D24/D60/sign-modality
    # metadata below them. This renders the same nine values (identical
    # numbers, no recomputation) as a KPI card grid at the top of the
    # report, since that's the information a reader actually scans for
    # first.
    def _score_tier_class(value: Any) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "kpi-neutral"
        if v >= 70:
            return "kpi-strong"
        if v >= 50:
            return "kpi-moderate"
        return "kpi-weak"

    # --- Batched dynamic-content translation -------------------------------
    # Every genuinely free-form English sentence the engine produces for
    # this chart is collected here FIRST and sent through _dyn() in one
    # shot, so a single LLM round-trip (not dozens) translates the whole
    # report body. Order is tracked via a simple pop-queue so the results
    # can be unpacked back into their original call sites below.
    sig_signals_raw = list(sig.get("signals", []) or [])
    sig_risk_raw = list(sig.get("risk_signals", []) or [])
    contradiction_notes_raw = [str(c.get("note", "")) for c in contradiction_findings]
    d24_note_raw = str(d24_status.get("note", "—"))
    d60_note_raw = str(d60_status.get("note", "—"))
    kp10_note_raw = str(kp10.get("note", "—"))
    sign_affinities_raw = list(sign_modality.get("field_affinities", []) or [])
    operating_best_fit_raw = str(operating_model.get("best_fit", "—"))
    reasoning_raw = str(rec.get("reasoning", ""))
    venture_type_raw = str(rec.get("venture_type", "—"))
    maturity_statement_raw = str(maturity_statement)
    maturity_caveats_raw = [str(c) for c in maturity_caveats]
    timing_error_raw = str(timing_status.get("error", "")) if timing_status.get("error") else ""

    window_evidence_raw: List[str] = []
    window_evidence_counts: List[int] = []
    window_ledger_actions_raw: List[str] = []
    window_ledger_counts: List[int] = []
    for w in prediction["timed_windows"]:
        ev = list(w.get("evidence", []) or [])
        window_evidence_raw.extend(str(e) for e in ev)
        window_evidence_counts.append(len(ev))
        ledger = list(w.get("arbitration_ledger", []) or [])
        window_ledger_actions_raw.extend(str(t.get("action", "")) for t in ledger)
        window_ledger_counts.append(len(ledger))

    method_detail_keys = list(method_status.keys())
    method_detail_raw: List[str] = []

    def _method_detail(val: Dict[str, Any]) -> str:
        # Audit fix: previously only showed val["error"], leaving the cell
        # blank for the common case (no error, just informational detail).
        # Now surfaces error first if present, otherwise note/precision_note
        # (informational fields like timing_precision's disclosure or the
        # transit method's mean-motion caveat), otherwise level (for
        # timing_precision), otherwise falls back to the static/timing
        # breakdown so the reader isn't left with a blank cell.
        if val.get("error"):
            return str(val["error"])
        if val.get("note"):
            return str(val["note"])
        if val.get("precision_note"):
            return str(val["precision_note"])
        if val.get("level"):
            return f"level={val['level']}"
        if val.get("rows_annotated") is not None:
            return f"rows_annotated={val['rows_annotated']}"
        parts = []
        if "static_natal_use" in val:
            parts.append(f"static={val['static_natal_use']}")
        if "timing_window_activation" in val:
            parts.append(f"timing_windows={val['timing_window_activation']}")
        return ", ".join(parts)

    for key in method_detail_keys:
        method_detail_raw.append(_method_detail(method_status[key]))

    # Single batch call for everything above.
    _batch_in = (
        sig_signals_raw + sig_risk_raw + contradiction_notes_raw
        + [d24_note_raw, d60_note_raw, kp10_note_raw] + sign_affinities_raw
        + [operating_best_fit_raw, reasoning_raw, maturity_statement_raw, venture_type_raw]
        + maturity_caveats_raw + ([timing_error_raw] if timing_error_raw else [])
        + window_evidence_raw + window_ledger_actions_raw + method_detail_raw
    )
    _batch_out = _dyn(_batch_in) if _batch_in else []
    _q = list(_batch_out)

    def _take(n: int) -> List[str]:
        out = _q[:n]
        del _q[:n]
        return out

    sig_signals = _take(len(sig_signals_raw))
    sig_risk = _take(len(sig_risk_raw))
    contradiction_notes = _take(len(contradiction_notes_raw))
    d24_note, d60_note, kp10_note = _take(3)
    sign_affinities = _take(len(sign_affinities_raw))
    (operating_best_fit, reasoning_text, maturity_statement_t, venture_type_t) = _take(4)
    maturity_caveats_t = _take(len(maturity_caveats_raw))
    timing_error_t = _take(1)[0] if timing_error_raw else ""
    window_evidence_t = _take(len(window_evidence_raw))
    window_ledger_actions_t = _take(len(window_ledger_actions_raw))
    method_detail_t = _take(len(method_detail_raw))

    # Overwrite rec["reasoning"] with the translated sentence so every
    # caller downstream (both editions read s['rec']['reasoning']) gets
    # the translated version automatically, without touching every call
    # site individually.
    rec = dict(rec)
    rec["reasoning"] = reasoning_text if lang != "en" else rec.get("reasoning", "")
    rec["venture_type"] = venture_type_t if lang != "en" else rec.get("venture_type", "")
    if lang == "en":
        reasoning_text = rec.get("reasoning", "")

    # --- KPI grid ------------------------------------------------------
    _kpi_defs = [
        ("Business Promise", prediction.get("business_promise"), "How strong is the independent-enterprise promise itself"),
        ("Job Promise", prediction.get("job_promise"), "How strong is the salaried-employment promise"),
        ("Independent-Profession Promise", prediction.get("independent_profession_promise"), "Solo practice / consulting without a trading structure"),
        ("Top-Sector Astrological Fit", prediction.get("business_field_fit"), "Same score as the first displayed ranked sector; an astrological affinity, not market feasibility"),
        ("Execution Capacity", prediction.get("business_execution_capacity"), "D10-confirmed ability to run it day-to-day"),
        ("Astrological Profit Support", prediction.get("business_profitability"), "Weighted 11th-house receipts and 2nd-house retention support; not projected financial profit"),
        ("Stability", prediction.get("business_stability"), "D9-durability and D60-modified sustainability"),
        ("Timing Readiness", prediction.get("current_timing_readiness"), "Whether the current dasha activates business houses"),
    ]
    kpi_cards_html = "".join(
        f"""<div class="kpi-card {_score_tier_class(v)}">
          <div class="kpi-label">{_esc(_lt(lang, label))}</div>
          <div class="kpi-value">{_fmt_pct(v) if isinstance(v, (int, float)) else _esc(_lt(lang, v) if v is not None else "—")}</div>
          {_kpi_bar_html(v)}
          <div class="kpi-hint">{_esc(_lt(lang, hint))}</div>
        </div>"""
        for label, v, hint in _kpi_defs
    )
    _conf_label = confidence.get("label", "UNKNOWN")
    _conf_score_0_1 = confidence.get("score_0_1")
    _conf_method_agreement = confidence.get("method_agreement")
    # score_0_1/method_agreement are genuinely 0..1-bounded (not 0-100) --
    # scale to 0-100 before handing to _fmt_pct so they read as valid
    # percentages, not as a bare "0.7" that looks like 0.7%.
    _conf_score_pct = _fmt_pct(_conf_score_0_1 * 100.0) if isinstance(_conf_score_0_1, (int, float)) else "—"
    _conf_agreement_pct = _fmt_pct(_conf_method_agreement * 100.0) if isinstance(_conf_method_agreement, (int, float)) else "—"
    kpi_cards_html += f"""<div class="kpi-card kpi-confidence conf-{_esc(_conf_label)}">
      <div class="kpi-label">{_esc(_lt(lang, 'Business-over-Job Confidence'))}</div>
      <div class="kpi-value">{_esc(_lt(lang, _conf_label))}</div>
      <div class="kpi-hint">{_esc(_t(lang, 'kpi_hint_confidence', 'How much the different scoring methods agree that business beats staying employed'))} &mdash; {_esc(_t(lang, 'method_agreement_word', 'method agreement'))}: {_conf_agreement_pct}, {_esc(_t(lang, 'score_word', 'score'))}: {_conf_score_pct}</div>
    </div>"""
    _margin_raw = prediction.get('business_advantage_margin')
    _margin_display = f"{float(_margin_raw):+.1f} pts" if isinstance(_margin_raw, (int, float)) else "—"
    _margin_label = prediction.get('business_advantage_label', 'UNKNOWN')
    kpi_cards_html += f"""<div class="kpi-card kpi-margin">
      <div class="kpi-label">{_esc(_lt(lang, 'Business Advantage Margin'))}</div>
      <div class="kpi-value">{_esc(_margin_display)}</div>
      <div class="kpi-hint">{_esc(_t(lang, 'kpi_hint_margin', 'Point gap between Business Promise and Job Promise (positive favors business)'))} &mdash; {_esc(_lt(lang, _margin_label))}</div>
    </div>"""
    section_kpi_grid = f'<div class="kpi-grid">{kpi_cards_html}</div>'

    # v42 audit fix (user-caught via real generated output): the v41
    # sub-dimension breakdowns (business_execution_capacity_components,
    # business_stability_components) were computed by the engine but never
    # rendered anywhere in either report -- the whole point of un-blending
    # those aggregates was reader transparency, which requires them to
    # actually be visible. Added as extra rows immediately under their
    # parent aggregate field, prefixed for readability.
    _exec_components = prediction.get("business_execution_capacity_components", {}) or {}
    _stability_components = prediction.get("business_stability_components", {}) or {}
    # v42 fix: _lt() only translates for ta/te and passes English straight
    # through unchanged, so raw snake_case dict keys (e.g.
    # "client_acquisition") were showing up verbatim in English reports --
    # not translated wrongly, just never given a human-readable English
    # label in the first place. A snake_case -> Title Case fallback via
    # .replace('_',' ').title() ensures English always reads as a proper
    # label too, while Tamil/Telugu still route through the _LABEL_TR
    # entries added above.
    def _sub_label(key: str) -> str:
        return _lt(lang, key) if lang != "en" else key.replace("_", " ").title()

    _exec_component_rows = [(f"  → {_sub_label(k)}", v) for k, v in _exec_components.items()]
    _stability_component_rows = [(f"  → {_sub_label(k)}", v) for k, v in _stability_components.items()]

    # v42 audit fix (#20): bootstrap_capacity/external_capital_raising_capacity/
    # capital_strategy_lean (scoring.py) are new granular sub-components of
    # business_execution_capacity_components answering "self-fund vs raise
    # external capital?" -- they already appear generically in
    # _exec_component_rows above (like every other sub-component), but that
    # generic row is just a number; capital_strategy_lean deserves its own
    # plain-language surfacing since it's the whole point of the split.
    # Astrologer edition: full house-lord citation (2nd vs 11th/8th lord
    # strength). Client edition (built further down where this string is
    # reused) gets a plain-language-only sentence, no house/lord jargon.
    _bootstrap_val = _exec_components.get("bootstrap_capacity")
    _external_val = _exec_components.get("external_capital_raising_capacity")
    _capital_lean = _exec_components.get("capital_strategy_lean", "INSUFFICIENT_DATA")
    _capital_lean_astrologer_text = {
        "BOOTSTRAP_FAVORED": _t(lang, "capital_lean_bootstrap_astrologer",
            "2nd-house (personal wealth) lord strength ({bootstrap}) clearly exceeds the 11th/8th-house "
            "(gains-through-others/joint-resources) blended lord strength ({external}) -- self-funding is "
            "the better-supported capital strategy for this chart.").format(bootstrap=_bootstrap_val, external=_external_val),
        "EXTERNAL_CAPITAL_FAVORED": _t(lang, "capital_lean_external_astrologer",
            "The 11th/8th-house (gains-through-others/joint-resources) blended lord strength ({external}) "
            "clearly exceeds 2nd-house (personal wealth) lord strength ({bootstrap}) -- raising external "
            "capital/investors is the better-supported capital strategy for this chart.").format(bootstrap=_bootstrap_val, external=_external_val),
        "EXTERNAL_CAPITAL_ACCESSIBLE_BUT_NOT_ADVISABLE": _t(lang, "capital_lean_external_not_advisable_astrologer",
            "The 11th/8th-house blended lord strength ({external}) exceeds 2nd-house lord strength ({bootstrap}), "
            "so this chart is structurally more oriented toward raising external capital than self-funding -- "
            "but that comparative lean is gated off here because the capital_debt_management sub-score is 0 and/or "
            "capital_readiness is NOT_SUPPORTED: this chart shows an ABILITY to access outside capital but not "
            "current READINESS to responsibly deploy or service it. Treat as EXTERNAL_CAPITAL_ACCESSIBLE_BUT_NOT_"
            "ADVISABLE, not EXTERNAL_CAPITAL_FAVORED -- resolve the underlying debt-management/capital-readiness "
            "gaps before pursuing external capital.").format(bootstrap=_bootstrap_val, external=_external_val),
        "BALANCED": _t(lang, "capital_lean_balanced_astrologer",
            "2nd-house lord strength ({bootstrap}) and 11th/8th-house blended lord strength ({external}) are "
            "close enough that neither self-funding nor external capital is clearly favored by this chart alone.").format(bootstrap=_bootstrap_val, external=_external_val),
        "INSUFFICIENT_DATA": _t(lang, "capital_lean_insufficient_astrologer",
            "House-lord data needed to compare self-funding vs external-capital capacity is not available for this chart."),
    }.get(_capital_lean, "")
    _capital_lean_client_text = {
        "BOOTSTRAP_FAVORED": _t(lang, "capital_lean_bootstrap_client",
            "Your chart shows stronger support for self-funding/bootstrapping than for raising outside investment."),
        "EXTERNAL_CAPITAL_FAVORED": _t(lang, "capital_lean_external_client",
            "Your chart shows stronger support for raising outside investment/partners' capital than for self-funding alone."),
        "EXTERNAL_CAPITAL_ACCESSIBLE_BUT_NOT_ADVISABLE": _t(lang, "capital_lean_external_not_advisable_client",
            "Your chart leans toward being ABLE to raise outside investment more easily than self-funding, but other "
            "readiness signals (debt-management capacity and/or overall capital readiness) are not yet in place -- "
            "treat outside capital as accessible in principle, not advisable right now. Strengthen debt-management "
            "and capital-readiness fundamentals before pursuing it."),
        "BALANCED": _t(lang, "capital_lean_balanced_client",
            "Your chart shows roughly balanced support for either self-funding or raising outside investment."),
        "INSUFFICIENT_DATA": _t(lang, "capital_lean_insufficient_client",
            "There isn't enough chart data available to compare self-funding vs outside-investment support."),
    }.get(_capital_lean, "")
    section_capital_strategy_astrologer = f'<p style="font-size:13px;">{_esc(_capital_lean_astrologer_text)}</p>' if _capital_lean_astrologer_text else ""
    section_capital_strategy_client = f'<p style="font-size:13px;">{_esc(_capital_lean_client_text)}</p>' if _capital_lean_client_text else ""
    _kp_event_signals = (kp10 or {}).get("event_type_signals", {}) or {}
    _kp_event_rows = [(f"  → {_sub_label(k)}", v) for k, v in _kp_event_signals.items()]

    # v-audit: fields genuinely clamped 0-100 by scoring.py (business_promise,
    # job_promise, independent_profession_promise, business_field_fit,
    # business_execution_capacity/its components, business_profitability,
    # business_stability/its components, current_timing_readiness) render
    # as "%"; business_advantage_margin is a signed point-delta (NOT 0-100,
    # can be negative) so it renders as "pts"; confidence's score_0_1/
    # method_agreement are 0..1-bounded so they are scaled by 100 before
    # formatting as "%".
    _pct_field_names = {
        "Business promise", "Job promise", "Independent-profession promise",
        "Business sector fit", "Business execution capacity",
        "Business profitability", "Business stability", "Current timing readiness",
    }

    def _named_value(k: str, v: Any) -> str:
        if k in _pct_field_names and isinstance(v, (int, float)):
            return _fmt_pct(v)
        return _esc(v)

    named_field_rows = [[_esc(_lt(lang, k)), _named_value(k, v)] for k, v in (
        ("Business promise", prediction.get("business_promise")),
        ("Job promise", prediction.get("job_promise")),
        ("Independent-profession promise", prediction.get("independent_profession_promise")),
        ("Business sector fit", prediction.get("business_field_fit")),
        ("Business execution capacity", prediction.get("business_execution_capacity")),
    )]
    named_field_rows += [[_esc(f"  → {_sub_label(k)}"), _esc(_fmt_pct(v) if isinstance(v, (int, float)) else v)] for k, v in _exec_components.items()]
    named_field_rows += [[_esc(_lt(lang, k)), _named_value(k, v)] for k, v in (
        ("Business profitability", prediction.get("business_profitability")),
        ("Business stability", prediction.get("business_stability")),
    )]
    named_field_rows += [[_esc(f"  → {_sub_label(k)}"), _esc(_fmt_pct(v) if isinstance(v, (int, float)) else v)] for k, v in _stability_components.items()]
    _conf_score_named = confidence.get("score_0_1")
    _conf_agree_named = confidence.get("method_agreement")
    _conf_score_named_pct = _fmt_pct(_conf_score_named * 100.0) if isinstance(_conf_score_named, (int, float)) else "—"
    _conf_agree_named_pct = _fmt_pct(_conf_agree_named * 100.0) if isinstance(_conf_agree_named, (int, float)) else "—"
    _margin_named_raw = prediction.get("business_advantage_margin")
    _margin_named_display = f"{float(_margin_named_raw):+.1f} pts" if isinstance(_margin_named_raw, (int, float)) else "—"
    named_field_rows += [[_esc(_lt(lang, k)), _esc(v)] for k, v in (
        ("Current timing readiness", _named_value("Current timing readiness", prediction.get("current_timing_readiness"))),
        ("Business-over-job confidence", f"{_lt(lang, confidence.get('label', 'UNKNOWN'))} (score={_conf_score_named_pct}, method_agreement={_conf_agree_named_pct})"),
        ("Business advantage margin", f"{_margin_named_display} ({_lt(lang, prediction.get('business_advantage_label', 'UNKNOWN'))})"),
        ("Operating-model best fit", operating_best_fit),
        ("D24 competency status", d24_note),
        ("D60 confirmation status", d60_note),
        ("Sign/modality field affinities", ", ".join(sign_affinities) or "—"),
        ("KP 10th-cusp job-vs-business", (
            kp10_note if kp10.get("chain_verified")
            else (
                "NOT VALIDLY APPLIED -- house system not confirmed Placidus / "
                "sub-lord chain unverified (cusp_audit.status="
                f"{(kp10.get('cusp_audit') or {}).get('status', 'UNVERIFIED')}, "
                f"reasons={(kp10.get('cusp_audit') or {}).get('reasons', [])}); "
                "excluded from weighted scoring. Raw (unvalidated) reading for "
                f"reference only: {kp10_note}"
            )
        )),
        *_kp_event_rows,
    )]
    section_named_fields = _table([_lt(lang, "Field"), _lt(lang, "Value")], named_field_rows)

    contradiction_rows = [[_esc(_lt(lang, c.get("mode", ""))), _esc(c.get("weight", "")), _esc(note)] for c, note in zip(contradiction_findings, contradiction_notes)]
    section_contradictions = _table([_lt(lang, "Mode"), _lt(lang, "Penalty"), _lt(lang, "Contradiction finding")], contradiction_rows) if contradiction_rows else f"<p><em>{_esc(_lt(lang, 'No contradiction-control findings for this chart.'))}</em></p>"

    operating_model_rows = [[_esc(name_), _esc(operating_model.get("normalized_0_100", {}).get(name_, "—"))] for name_, _score in operating_model.get("ranked", [])]
    section_operating_model = _table([_lt(lang, "Operating model"), _lt(lang, "Relative fit (0-100, within-chart)")], operating_model_rows) if operating_model_rows else f"<p><em>{_esc(_lt(lang, 'No operating-model data.'))}</em></p>"

    # v20: D10-native operating-model mirror, so D1's and D10's named
    # best-fit models can be compared side by side in the report itself.
    operating_model_d10 = prediction.get("operating_model_d10", {}) or {}
    operating_model_d10_rows = [[_esc(name_), _esc(operating_model_d10.get("normalized_0_100", {}).get(name_, "—"))] for name_, _score in operating_model_d10.get("ranked", [])]
    section_operating_model_d10 = _table([_lt(lang, "Operating model (D10-native)"), _lt(lang, "Relative fit (0-100, within-chart)")], operating_model_d10_rows) if operating_model_d10_rows else f"<p><em>{_esc(_lt(lang, 'No D10-native operating-model data.'))}</em></p>"

    # Issue 7 fix: when D1's and D10's named best-fit operating models
    # disagree, don't just list both tables side by side and leave the
    # reader to reconcile them -- attempt an explicit synthesis category
    # where the two models have coherent real-world overlap (e.g. a
    # scalable platform that IS the trading/brokerage venue is a single
    # recognizable business archetype), and when no coherent overlap
    # exists, say so explicitly and report a reduced operating-model
    # agreement confidence rather than silently implying the two rankings
    # are equally trustworthy.
    _d1_best_model = operating_model.get("best_fit")
    _d10_best_model = operating_model_d10.get("best_fit")
    # Curated, disclosed (not exhaustive) set of coherent D1+D10 model
    # pairings -- unordered pairs mapped to a plain-language synthesis
    # label. Anything not in this table falls back to the explicit
    # no-coherent-synthesis path below.
    _OPERATING_MODEL_SYNTHESIS = {
        frozenset({"scalable_platform", "trading_brokerage"}): "technology-enabled marketplace / brokerage platform / intermediary network",
        frozenset({"scalable_platform", "professional_practice"}): "platform-delivered professional services (a scaled practice, not a one-to-one practice)",
        frozenset({"trading_brokerage", "partnership"}): "brokerage/trading firm run as a formal partnership",
        frozenset({"partnership", "professional_practice"}): "professional practice run jointly with partners (e.g. a firm, not a solo practice)",
        frozenset({"partnership", "family_business"}): "family-partnership hybrid (kin as co-owners/partners)",
        frozenset({"sole_owner", "professional_practice"}): "independent, self-owned professional practice",
        frozenset({"sole_owner", "trading_brokerage"}): "sole-proprietor trading/dealing operation",
        frozenset({"family_business", "manufacturing"}): "family-run manufacturing/production business",
        frozenset({"scalable_platform", "manufacturing"}): "asset-light, platform-coordinated production/supply model",
    }
    operating_model_agreement_confidence = 100
    if _d1_best_model and _d10_best_model:
        if _d1_best_model == _d10_best_model:
            operating_model_synthesis_text = _t(
                lang, "operating_model_synthesis_agree",
                "D1 and D10 agree on the best-fit operating model ({model}) -- high structural confidence in this "
                "operating archetype.",
            ).format(model=_d1_best_model)
        else:
            _pair_key = frozenset({_d1_best_model, _d10_best_model})
            _synth = _OPERATING_MODEL_SYNTHESIS.get(_pair_key)
            if _synth:
                operating_model_agreement_confidence = 65
                operating_model_synthesis_text = _t(
                    lang, "operating_model_synthesis_found",
                    "D1's best-fit operating model ({d1_model}) and D10-native's best-fit operating model "
                    "({d10_model}) disagree at the individual-label level, but they have a coherent real-world "
                    "overlap: {synthesis}. Read the operating-model recommendation as this synthesis rather than "
                    "either single label alone -- structural confidence is moderate, not the same as a clean D1/D10 "
                    "agreement.",
                ).format(d1_model=_d1_best_model, d10_model=_d10_best_model, synthesis=_synth)
            else:
                operating_model_agreement_confidence = 35
                operating_model_synthesis_text = _t(
                    lang, "operating_model_synthesis_none",
                    "D1's best-fit operating model ({d1_model}) and D10-native's best-fit operating model "
                    "({d10_model}) disagree, and there is no coherent synthesis category linking them -- these "
                    "are two structurally different ways of running a venture, not two descriptions of the same "
                    "one. Operating-model confidence is reduced (agreement_confidence={conf}/100) until a "
                    "specific operating structure is chosen and re-checked against both D1 and D10 independently.",
                ).format(d1_model=_d1_best_model, d10_model=_d10_best_model, conf=operating_model_agreement_confidence)
    else:
        operating_model_synthesis_text = _t(
            lang, "operating_model_synthesis_unavailable",
            "D10-native operating-model data is unavailable for this chart, so D1-vs-D10 operating-model "
            "agreement cannot be assessed.",
        )
    # Audit item 6 fix: the operating-model conclusion above is D10-derived
    # (directly, when D10 alone drives it; or as a contributing input to the
    # D1/D10 synthesis above). d10_rectification_sensitivity (see
    # d10_rectification.py) can label this chart's D10 reading FRAGILE --
    # meaning a small (~5 minute) birth-time correction changes the D10
    # Lagna sign and/or 10th-lord, which would change the operating-model
    # conclusion itself. That caveat was previously computed but never
    # attached to this specific conclusion text -- add it explicitly here
    # so a reader of the operating-model section sees the caveat right next
    # to the conclusion it qualifies, not only in a separate D10-sensitivity
    # section elsewhere in the report.
    _d10_sens = prediction.get("d10_rectification_sensitivity") or {}
    _d10_sens_stability = _d10_sens.get("stability")
    _d10_fragile_caveat = ""
    if _d10_sens_stability == "FRAGILE":
        _tolerance_note = _d10_sens.get("tolerance_minutes") or _d10_sens.get("sensitivity_window_minutes") or "approximately +/-4"
        _d10_fragile_caveat = _t(
            lang, "p_d10_fragile_operating_model_caveat",
            "CAUTION -- this operating-model reading is CONDITIONAL on birth time being accurate to within "
            "{tolerance} minutes; a small birth-time correction within that window has been shown to change the "
            "D10 Lagna sign and/or 10th lord for this chart (see D10 rectification sensitivity below), which would "
            "change this operating-model conclusion itself. Rectification is recommended before treating this as a "
            "firm structural conclusion.",
        ).format(tolerance=_tolerance_note)
    section_operating_model_synthesis = f'<p style="font-size:13px;">{_esc(operating_model_synthesis_text)} <em>(operating_model_agreement_confidence={operating_model_agreement_confidence}/100)</em></p>'
    if _d10_fragile_caveat:
        section_operating_model_synthesis += f'<p style="font-size:12px; color:#a15c00; font-weight:600; margin-top:6px;">{_esc(_d10_fragile_caveat)}</p>'

    # Issue 14 fix: partnership-capable framing, not a partnership
    # recommendation. operating_model / operating_model_d10 rank
    # "partnership" as a structural fit purely from H7 strength and
    # (elsewhere) client-acquisition score -- a within-chart propensity
    # reading, not an assessment of any actual proposed partner. This
    # engine can only produce an actual partnership RECOMMENDATION via
    # partnership_synastry (chart-to-chart comparison against a specific
    # partner's chart); when that field is null/absent, make the
    # distinction explicit wherever partnership ranks prominently, instead
    # of letting a high relative-fit number read as "you should get a
    # business partner."
    _partnership_synastry_for_note = prediction.get("partnership_synastry")
    _d1_partnership_fit = (operating_model.get("normalized_0_100", {}) or {}).get("partnership")
    _d10_partnership_fit = (operating_model_d10.get("normalized_0_100", {}) or {}).get("partnership")
    _partnership_ranks_prominently = (
        (_d1_partnership_fit is not None and _d1_partnership_fit >= 70)
        or (_d10_partnership_fit is not None and _d10_partnership_fit >= 70)
    )
    if _partnership_ranks_prominently and not _partnership_synastry_for_note:
        _partnership_capable_note = _t(
            lang, "p_partnership_capable_not_recommendation",
            "Note on partnership: this chart shows genuine PARTNERSHIP-CAPABLE structural propensity (7th-house/H7 "
            "lord strength above, and this chart's own client-acquisition score) -- this is a reading of the "
            "native's OWN capacity/orientation toward partnership as a structure, not a recommendation to actually "
            "form one. Whether a SPECIFIC partnership is favorable depends on chart-to-chart synastry with the "
            "actual proposed partner (partnership_synastry), which is not available for this report (no partner "
            "chart was supplied) -- do not read the fit numbers above as approval of any particular partner or as "
            "advice to seek a partner.",
        )
        section_operating_model_synthesis += f'<p style="font-size:12px; color:var(--muted, #666); margin-top:8px;">{_esc(_partnership_capable_note)}</p>'

    # v18: the declared-weight layer breakdown for business_promise/
    # job_promise, so the composition is auditable in the report itself,
    # not just asserted in prose.
    biz_layers = prediction.get("business_promise_layers", {}) or {}
    job_layers = prediction.get("job_promise_layers", {}) or {}

    # v37 audit fix: this table previously showed D60's declared 3% weight
    # and its raw 50.0 layer score exactly like every other row, even
    # though the v36 fix already excludes D60 from weighted_total when
    # d60_evidence_available is False -- a reader could not tell from the
    # table alone that D60 contributed nothing to the actual score. Now
    # a row whose evidence is genuinely unavailable shows "N/A (no data)"
    # for its score and "0% applied (declared max N%)" for its weight,
    # matching what the number actually did in the weighted sum.
    def _layer_row(layers_dict: Dict[str, Any], k: str, w: Any) -> List[str]:
        evidence_available = layers_dict.get("d60_evidence_available", True) if k == "d60" else True
        if evidence_available is False:
            weight_display = f"{_t(lang, 'weight_zero_applied_prefix', '0% applied (declared max')} {w}%)"
            score_display = _t(lang, 'score_not_available', 'N/A (no data)')
        else:
            weight_display = f"{w}%"
            score_display = str(layers_dict.get("layers", {}).get(k, "—"))
        return [_esc(k), _esc(weight_display), _esc(score_display)]

    biz_layer_rows = [_layer_row(biz_layers, k, w) for k, w in biz_layers.get("weights", {}).items()]
    job_layer_rows = [_layer_row(job_layers, k, w) for k, w in job_layers.get("weights", {}).items()]
    section_biz_layers = _table([_lt(lang, "Business layer"), _lt(lang, "Weight (%)"), _lt(lang, "Layer score (0-100)")], biz_layer_rows) if biz_layer_rows else f"<p><em>{_esc(_lt(lang, 'No business-layer breakdown.'))}</em></p>"
    section_job_layers = _table([_lt(lang, "Job layer"), _lt(lang, "Weight (%)"), _lt(lang, "Layer score (0-100)")], job_layer_rows) if job_layer_rows else f"<p><em>{_esc(_lt(lang, 'No job-layer breakdown.'))}</em></p>"

    caveats_html = "".join(f"<li>{_esc(c)}</li>" for c in maturity_caveats_t)
    translation_notice_html = (
        f"""<p style="color:var(--red); font-weight:600;">{_esc(_t(lang, 'translation_incomplete_notice', 'Note: live translation of some technical evidence text was unavailable when this report was generated; those specific sentences below remain in English.'))}</p>"""
        if translation_incomplete else ""
    )
    disclaimer_html = f"""
<div class="disclaimer">
  <p><strong>{_esc(_lt(lang, 'Model status:'))} {_esc(_lt(lang, model_status))}</strong> &mdash; {_esc(_lt(lang, calibration_status))}</p>
  <p><strong>{_esc(_lt(lang, 'Maturity statement:'))}</strong> {_esc(maturity_statement_t)}</p>
  {f"<ul>{caveats_html}</ul>" if caveats_html else ""}
  <p>{_esc(_t(lang, 'heuristic_tier_disclaimer', 'The "Heuristic Tier" below (HIGH/MODERATE/LOW) is an internal, uncalibrated rule threshold on two deterministic scores. It is not a measured statistical confidence, a probability, or financial/legal/investment advice. This report is a decision-support narrative for further astrological review, not a financial forecast.'))}</p>
  {translation_notice_html}
</div>"""

    # Content-restructuring audit fix (item 6): grouped by classical method
    # (Parashari / Jaimini / KP / D2 / D9 / D10) instead of one flat table
    # once the ledger is long enough to benefit -- see
    # _grouped_significator_table_html's docstring for the exact rule and
    # fallback behavior on short lists.
    section_signals = (
        _grouped_significator_table_html(sig_signals, lang, _lt(lang, "Positive business-strength signal"))
        if sig_signals else f"<p><em>{_esc(_lt(lang, 'No positive signals found.'))}</em></p>"
    )

    risk_rows = [[_esc(s)] for s in sig_risk]
    section_risk_signals = _table([_lt(lang, "Negative / risk signal")], risk_rows) if risk_rows else f"<p><em>{_esc(_lt(lang, 'No negative signals found.'))}</em></p>"

    # Uplift: a plain <table> of 19 rows wastes the report's width and gives
    # the reader no immediate sense of relative gap between sectors. This
    # keeps the exact same underlying data (rank/label/score/sbc_smi/
    # sbc_timing_band, unchanged) but renders it as a ranked leaderboard
    # with an inline proportional score bar, tiered row styling (top-3 /
    # next-4 / rest) and a timing-band chip, so the same information reads
    # in seconds on a wide screen instead of requiring a full table scan.
    _max_sector_score = max((row["score"] for row in prediction["top_sectors"]), default=100.0) or 100.0
    sector_leaderboard_rows = []
    for row in prediction["top_sectors"]:
        rank = row["rank"]
        tier_class = "tier-top" if rank <= 3 else ("tier-mid" if rank <= 7 else "tier-rest")
        bar_pct = round(100.0 * row["score"] / _max_sector_score, 1)
        timing_band_raw = row.get("sbc_timing_band", "—")
        timing_band = _esc(_lt(lang, timing_band_raw))
        smi = row.get("sbc_smi", "—")
        match_confidence_raw = row.get("match_confidence", "")
        match_chip_html = ""
        if match_confidence_raw == "EXPLORATORY_SECTOR_MATCH":
            match_chip_html = f'<span class="chip chip-band chip-band-LOW">{_esc(_t(lang, "exploratory_match_chip", "EXPLORATORY — no classical combo match"))}</span>'
        # v43: transparency note for the +4.0 cross-link bonus engine.py's
        # _OPERATING_MODEL_TO_COMPATIBLE_SECTORS applies to sectors compatible
        # with the D10 best-fit operating model -- without this the sector
        # ranking and the operating-model ranking look like silent, unrelated
        # duplicates instead of one intentionally cross-referencing the other.
        op_bonus_model = row.get("operating_model_alignment_bonus_applied")
        op_bonus_html = ""
        if op_bonus_model:
            op_bonus_note = _t(
                lang, "sector_op_model_bonus_note",
                "+4 bonus: compatible with your D10 best-fit operating model ({model})",
            ).format(model=_esc(_lt(lang, op_bonus_model)))
            op_bonus_html = f'<span class="chip chip-band">{_esc(op_bonus_note)}</span>'
        sector_leaderboard_rows.append(f"""
        <div class="sector-row {tier_class}">
          <div class="sector-rank">{rank}</div>
          <div class="sector-main">
            <div class="sector-label-line">
              <span class="sector-label">{_esc(_lt(lang, row['label']))}</span>
              <span class="sector-score">{_fmt_pct(row['score'])}</span>
            </div>
            <div class="sector-bar-track"><div class="sector-bar-fill" style="width:{bar_pct}%"></div></div>
          </div>
          <div class="sector-meta">
            <span class="chip chip-smi">SMI {_esc(smi)}</span>
            <span class="chip chip-band chip-band-{str(timing_band_raw).upper() if timing_band_raw != '—' else 'NA'}">{timing_band}</span>
            {match_chip_html}
            {op_bonus_html}
          </div>
        </div>""")
    section_sectors = f'<div class="sector-leaderboard">{"".join(sector_leaderboard_rows)}</div>'

    # Audit item 7 fix: "Technology Startup" as the bare top-sector label
    # can read as a narrower claim (a VC-style software startup) than the
    # underlying evidence actually supports on a Mercury-driven chart --
    # the same Mercury/analytics/communication significators that drive
    # tech_startup also drive adjacent registry sectors (education,
    # consulting, and any sector this chart's own core_planets/houses
    # overlap with Mercury on). Rather than rewriting the tech_startup
    # registry label/id (a wider, riskier change touching every chart,
    # not just this one), this surfaces the existing adjacent Mercury-
    # aligned sectors already present in the ranked list as a small,
    # additive cluster note -- the same restrained bonus-note pattern
    # already used above for op_bonus_html/match_chip_html, consistent
    # with this codebase's v27/v40 established small-additive-adjustment
    # convention rather than a wholesale rewrite.
    _MERCURY_ALIGNED_SECTOR_IDS = {
        "tech_startup", "education_institutions", "consulting_professional_services",
    }
    section_sector_mercury_cluster_note = ""
    if prediction["top_sectors"] and (
        prediction["top_sectors"][0].get("sector") == "tech_startup"
        or prediction["top_sectors"][0].get("label") == "Technology Startup"
    ):
        _cluster_rows = [
            row for row in prediction["top_sectors"]
            if row.get("sector") in _MERCURY_ALIGNED_SECTOR_IDS
            or row.get("label") in ("Education & Training Institutions", "Consulting & Professional Services")
        ]
        if len(_cluster_rows) > 1:
            _cluster_text = _t(
                lang, "p_sector_mercury_cluster_note",
                "Note on the top sector label: 'Technology Startup' is the single highest-scoring registry entry, "
                "but the underlying evidence driving it (Mercury-based analytics/communication significators) also "
                "supports a cluster of adjacent sectors on this chart: {cluster}. Read the top-sector conclusion as "
                "'Mercury-driven analytics/advisory/technology-enabled work' broadly -- education, consulting, and "
                "data/platform variants of this same underlying strength -- rather than narrowly as a VC-style "
                "software startup specifically.",
            ).format(cluster=", ".join(f"{_lt(lang, r['label'])} ({_fmt_pct(r['score'])})" for r in _cluster_rows))
            section_sector_mercury_cluster_note = f'<p style="font-size:12px; color:var(--muted, #666); margin-top:8px;">{_esc(_cluster_text)}</p>'
    section_sectors += section_sector_mercury_cluster_note

    _ev_idx = 0
    _lg_idx = 0
    window_blocks = []
    for i, w in enumerate(prediction["timed_windows"]):
        n_ev = window_evidence_counts[i]
        ev_slice = window_evidence_t[_ev_idx:_ev_idx + n_ev]
        _ev_idx += n_ev
        n_lg = window_ledger_counts[i]
        action_slice = window_ledger_actions_t[_lg_idx:_lg_idx + n_lg]
        _lg_idx += n_lg

        evidence_html = "".join(f"<li>{_esc(e)}</li>" for e in ev_slice)
        ledger_html = "".join(
            f"<li>{_esc(_t(lang, 'tier_word', 'Tier'))} {_esc(t['tier'])}: {_esc(t['net_before'])} → {_esc(t['net_after'])} ({_esc(action)})</li>"
            for t, action in zip(w.get("arbitration_ledger", []), action_slice)
        )
        window_label_raw = w.get("label", "")

        # PD (Pratyantardasha) sub-windows -- additive, nested under the
        # parent AD window. Astrologer edition shows full PD lord/tier/
        # citation detail using the .item-grid convention already used
        # elsewhere in this file (detected yogas, legal risk, D2 hora).
        pd_subs = w.get("pd_subwindows") or []
        if pd_subs:
            pd_items = "".join(f"""
            <li class="item-card">
              <span class="badge {_esc(pd.get('label',''))}">{_esc(_lt(lang, pd.get('label','')))}</span>
              <strong>{_esc(pd.get('start_date',''))} &rarr; {_esc(pd.get('end_date',''))}</strong>
              &mdash; PD {_esc(pd.get('pd_lord',''))}
              <span class="net-score">net_score = {_esc(pd.get('net_score',''))}</span>
              <div class="detail">{_esc(pd.get('detail',''))}</div>
            </li>""" for pd in pd_subs)
            pd_html = f"""
  <details>
    <summary>{_esc(_t(lang, 'pd_subwindows_word', 'Pratyantardasha sub-windows'))} ({len(pd_subs)})</summary>
    <ul class="item-grid">{pd_items}</ul>
  </details>"""
        elif w.get("pd_status") and w.get("pd_status") != "OK":
            pd_html = f"""
  <p class="pd-degraded"><em>{_esc(_t(lang, 'pd_unavailable_word', 'Pratyantardasha refinement unavailable for this window'))}: {_esc(w.get('pd_status',''))}</em></p>"""
        else:
            pd_html = ""

        # Audit item 8 fix: additive gain/expenditure tension flag (see
        # engine.py::_annotate_window_gain_expenditure_tension) -- purely
        # additive, does not touch the shared _label_for_net() badge above
        # (that function is deliberately left untouched per v33/v38).
        _tension_html = ""
        if w.get("gain_expenditure_tension") and w.get("gain_expenditure_tension_detail"):
            _tension_text = _t(
                lang, "p_window_gain_expenditure_tension",
                "MIXED-nature caveat: {detail} Better suited for market validation, a side venture, systems "
                "improvement, building reserves, or testing partnerships during this window -- NOT a debt-heavy "
                "launch or an abrupt employment exit.",
            ).format(detail=w["gain_expenditure_tension_detail"])
            _tension_html = f'<p class="window-tension-note" style="font-size:12px; color:#a15c00; margin:6px 0 0;">{_esc(_tension_text)}</p>'

        window_blocks.append((w, f"""
<div class="window-block">
  <h3>{_esc(w['start_date'])} → {_esc(w['end_date'])} &mdash; MD {_esc(w['md_lord'])} / AD {_esc(w['ad_lord'])}
    <span class="badge {_esc(window_label_raw)}">{_esc(_lt(lang, window_label_raw))}</span>
    <span class="net-score">net_score = {_esc(w['net_score'])}</span>
  </h3>
  {_tension_html}
  <details>
    <summary>{_esc(_t(lang, 'evidence_word', 'Evidence'))} ({len(ev_slice)})</summary>
    <ul>{evidence_html}</ul>
  </details>
  <details>
    <summary>{_esc(_t(lang, 'arbitration_ledger_word', 'Arbitration ledger'))} ({len(action_slice)} {_esc(_t(lang, 'tiers_word', 'tiers'))})</summary>
    <ul>{ledger_html}</ul>
  </details>{pd_html}
</div>"""))

    # v40 audit fix (#28, user-caught): MD/AD-level timing without
    # Pratyantar-dasha/Sookshma/exact-transit refinement becomes
    # increasingly unreliable further out, but this report previously gave
    # a window 14 years away the exact same visual prominence as next
    # year's window. Near-term windows (within ~5 years of today, where
    # MD/AD timing is most actionable) are now shown at full prominence;
    # anything further out is collapsed into an "Extended Outlook" details
    # block so a reader's attention naturally lands on what's actually
    # decision-relevant soon, without deleting the longer-horizon data.
    _today_for_split = datetime.now().date()
    _near_term_cutoff = _today_for_split.replace(year=_today_for_split.year + 5)

    def _window_start_date(w: Dict[str, Any]):
        try:
            return datetime.strptime(str(w.get("start_date", "")), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return _today_for_split

    near_term_html = "".join(html for w, html in window_blocks if _window_start_date(w) <= _near_term_cutoff)
    extended_html = "".join(html for w, html in window_blocks if _window_start_date(w) > _near_term_cutoff)
    section_windows = (
        (near_term_html or f"<p><em>{_esc(_lt(lang, 'No timed windows in the requested forecast horizon.'))}</em></p>")
        + (
            f"""<details style="margin-top:16px;"><summary>{_esc(_t(lang, 'extended_outlook_summary', 'Extended Outlook (beyond ~5 years -- MD/AD timing alone is less precise this far out)'))}</summary>{extended_html}</details>"""
            if extended_html else ""
        )
    )

    timing_status_html = (
        f"<p><strong>{_esc(_lt(lang, 'Timing computation status:'))}</strong> {_esc(_lt(lang, timing_status.get('status', 'UNKNOWN')))}"
        + (f" &mdash; {_esc(timing_error_t)}" if timing_error_raw else "")
        + f" ({_esc(_t(lang, 'calendar_periods_found', 'calendar periods found'))}: {_esc(timing_status.get('calendar_periods_found', '—'))})</p>"
    )

    method_rows = [
        [_esc(_lt(lang, _METHOD_STATUS_LABELS.get(key, key))), _esc(_lt(lang, method_status[key].get("status", "UNKNOWN"))), _esc(detail)]
        for key, detail in zip(method_detail_keys, method_detail_t)
    ]
    section_method_status = _table([_lt(lang, "Method"), _lt(lang, "Status"), _lt(lang, "Detail")], method_rows)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    proceed_yes = bool(rec["proceed"])
    tier = _esc(rec['heuristic_tier'])

    # v37 professionalism fix: the engine has computed a single reconciled
    # `authoritative_recommendation` (business_promise vs job_promise,
    # contradiction-penalized, with a conservative post-hoc gate against the
    # legacy mode_gate track) since v35, but no report ever surfaced it --
    # readers only ever saw the legacy PROCEED/DO NOT PROCEED badge, with no
    # visible reconciliation against the newer, more discriminating layered
    # verdict. This renders ONE clear, professionally labelled "Final
    # Verdict" card the reader sees first, using the engine's own
    # authoritative fields (no recomputation), so the two-track architecture
    # is presented as a single confident answer rather than left for the
    # reader to reconcile from scattered numbers.
    authoritative = prediction.get("authoritative_recommendation", {}) or {}
    verdict_raw = str(authoritative.get("verdict", "—"))
    # Issue 8 fix: when the engine's additive final_category fires
    # EMPLOYMENT_SUPPORTED_INDEPENDENT_PRACTICE (a coherent middle path
    # between the binary job/business verdict), use it as the headline
    # framing instead of defaulting to the binary verdict label.
    _final_category_raw = str(authoritative.get("final_category", verdict_raw))
    _independent_practice_headline = _final_category_raw == "EMPLOYMENT_SUPPORTED_INDEPENDENT_PRACTICE"
    # QA fix (found while verifying the legacy-removal/percentage pass):
    # these two dicts only ever covered 3 of the 6 verdict strings
    # authoritative_recommendation.verdict can actually hold (see
    # engine.py's _layered_verdict) -- PURSUE_BUSINESS_CAUTIOUSLY,
    # HYBRID_LEANING_BUSINESS and HYBRID_LEANING_JOB all silently fell
    # through to the raw untranslated enum string (e.g. a reader would
    # have seen literally "HYBRID_LEANING_JOB" as the headline verdict
    # value) and the generic "hybrid" CSS class. Filled in all six so
    # every real verdict this field can take gets a proper label/color.
    verdict_display = {
        "PURSUE_BUSINESS": _t(lang, "verdict_pursue_business", "Pursue Business"),
        "PURSUE_BUSINESS_CAUTIOUSLY": _t(lang, "verdict_pursue_business_cautiously", "Pursue Business, Cautiously"),
        "STAY_EMPLOYED": _t(lang, "verdict_stay_employed", "Stay Employed"),
        "HYBRID": _t(lang, "verdict_hybrid", "Hybrid / Phased Approach"),
        "HYBRID_LEANING_BUSINESS": _t(lang, "verdict_hybrid_leaning_business", "Hybrid, Leaning Business"),
        "HYBRID_LEANING_JOB": _t(lang, "verdict_hybrid_leaning_job", "Hybrid, Leaning Employment"),
    }.get(verdict_raw, _lt(lang, verdict_raw))
    verdict_css = {
        "PURSUE_BUSINESS": "yes",
        "PURSUE_BUSINESS_CAUTIOUSLY": "yes",
        "STAY_EMPLOYED": "no",
        "HYBRID": "hybrid",
        "HYBRID_LEANING_BUSINESS": "hybrid",
        "HYBRID_LEANING_JOB": "hybrid",
    }.get(verdict_raw, "hybrid")
    if _independent_practice_headline:
        verdict_display = _t(
            lang, "verdict_employment_supported_independent_practice",
            "Employment-Supported Independent Practice",
        )
        verdict_css = "hybrid"
    section_final_verdict = f"""
<div class="final-verdict {verdict_css}">
  <div class="final-verdict-label">{_esc(_t(lang, 'final_verdict_label', 'Final Verdict'))}</div>
  <div class="final-verdict-value">{_esc(verdict_display)}</div>
  <div class="final-verdict-meta">{_esc(_t(lang, 'business_promise_word', 'Business promise'))}: {_fmt_pct(authoritative.get('business_promise'))} &middot; {_esc(_t(lang, 'job_promise_word', 'Job promise'))}: {_fmt_pct(authoritative.get('job_promise'))}</div>
  {f'<div class="final-verdict-meta">' + _esc(str(authoritative.get('final_category_note', ''))) + '</div>' if _independent_practice_headline else ''}
</div>"""

    # Audit fix (item 1/2): the headline "Final Verdict" above is the
    # AUTHORITATIVE layered business_promise/job_promise verdict only.
    # It does not, by itself, tell a reader that a separate legacy
    # analysis (mode_gate.py) independently produced a DIFFERENT verdict
    # ("independent"/self-employed-professional, confidence HIGH) from a
    # DIFFERENT evidentiary basis (Jaimini argala/rasi-drishti + D10
    # venture-house evidence), nor does it show the raw pre-penalty
    # promise numbers and the specific engineered contradiction penalties
    # that flipped the ranking. This section makes both signals and the
    # penalty math explicit instead of presenting one suppressed headline.
    _mg = prediction.get("mode_gate", {}) or {}
    _legacy_mode = str(_mg.get("recommended_mode", "UNKNOWN"))
    _legacy_conf = str(_mg.get("confidence", "UNKNOWN"))
    _indep_promise = prediction.get("independent_profession_promise")
    _biz_promise = prediction.get("business_promise")
    _job_promise = prediction.get("job_promise")
    _contra_penalty = (prediction.get("recommendation", {}) or {}).get("contradiction_penalty_applied", {}) or {}
    _contra_total = sum(v for v in _contra_penalty.values() if isinstance(v, (int, float)))
    _contra_rows_html = "".join(
        f"<li>-{_esc(c.get('weight'))} pts ({_esc(c.get('mode',''))}): {_esc(c.get('note',''))}</li>"
        for c in contradiction_findings
    ) or f"<li><em>{_esc(_t(lang, 'no_contradiction_findings', 'None recorded for this chart.'))}</em></li>"
    # Issue 17 fix: quantify the "raw promise reversed by contradiction
    # penalty" claim with the engine's own numbers instead of leaving it
    # as unquantified prose -- business_promise/job_promise ARE already
    # penalty-applied (see scoring.py: business_promise = weighted_total -
    # biz_penalty), so the pre-penalty raw comparison has to be
    # reconstructed from business_promise_layers/job_promise_layers'
    # weighted_total fields (the same numbers scoring.py itself subtracts
    # the penalty from).
    _biz_layers = prediction.get("business_promise_layers", {}) or {}
    _job_layers = prediction.get("job_promise_layers", {}) or {}
    _biz_raw = _biz_layers.get("weighted_total")
    _job_raw = _job_layers.get("weighted_total")
    _raw_margin = (_biz_raw - _job_raw) if isinstance(_biz_raw, (int, float)) and isinstance(_job_raw, (int, float)) else None
    _structural_favors_business = _raw_margin is not None and _raw_margin > 0
    if _structural_favors_business:
        _headline_framing_text = _t(
            lang, "p_headline_framing_business_favored_raw",
            "Quantified: raw (pre-contradiction-penalty) business promise ({biz_raw}) exceeds raw job promise "
            "({job_raw}) by {margin:+.1f} pts -- the chart itself STRUCTURALLY FAVORS BUSINESS. A contradiction "
            "penalty of {penalty:.1f} pts (see the Contradiction-Control table below) is what reverses this into "
            "the net {net_label} headline above. Read this as: the chart structurally favors business; engine-side "
            "execution/stability contraindications make an immediate, unqualified transition unsafe -- NOT as "
            "'the chart favors employment' in its own right.",
        ).format(
            biz_raw=_biz_raw, job_raw=_job_raw, margin=_raw_margin,
            penalty=(_biz_raw - prediction.get("business_promise", _biz_raw)) if isinstance(_biz_raw, (int, float)) else 0.0,
            net_label=prediction.get("business_advantage_label", ""),
        )
    else:
        _headline_framing_text = ""
    _op_model = prediction.get("operating_model", {}) or {}
    _op_taxonomy_label = {
        "sole_owner": _t(lang, "op_model_sole_owner", "Sole-owner / freelance-style independent operation"),
        "professional_practice": _t(lang, "op_model_professional_practice", "Consulting / freelancing / professional practice"),
        "partnership": _t(lang, "op_model_partnership", "Partnership-based venture"),
        "family_business": _t(lang, "op_model_family_business", "Family-run enterprise"),
        "trading_brokerage": _t(lang, "op_model_trading_brokerage", "Trading / brokerage operation"),
        "manufacturing": _t(lang, "op_model_manufacturing", "Capital-intensive manufacturing enterprise"),
        "scalable_platform": _t(lang, "op_model_scalable_platform", "Scalable, platform-style entrepreneurship"),
    }.get(str(_op_model.get("best_fit", "")), _lt(lang, str(_op_model.get("best_fit", "—"))))
    # DYNAMIC employment-evidence-bundle check (was previously a hardcoded
    # "the engine does not yet compute this" claim -- job_promise_layers has
    # carried a real 7-layer positive employment-evidence bundle since v18/v20
    # (d1_service_hierarchy, d10_service_execution, integration_6_10_11,
    # saturn_sun_institutional, kp_2_6_10_11, jaimini_service, d9_durability).
    # Inspect the ACTUAL populated payload on THIS run rather than asserting
    # a fixed claim, so this text can never go stale again for any chart.
    _job_layer_map = (_job_layers.get("layers") or {})
    _job_layer_excluded = set(_job_layers.get("excluded_layers") or [])
    _job_layers_populated = [
        k for k, v in _job_layer_map.items()
        if k not in _job_layer_excluded and isinstance(v, (int, float))
    ]
    if _job_layers_populated:
        _employment_evidence_caveat_text = _t(
            lang, "p_employment_evidence_caveat_dynamic",
            "Employment-superiority note: this engine DOES compute a dedicated positive "
            "employment-evidence bundle (job_promise_layers: {layers}), separate from the "
            "business-side contradiction penalties above -- weighted_total={weighted_total} "
            "(weights: {weights}). Employment superiority in the verdict above reflects both "
            "this independently-computed positive employment evidence AND business-side "
            "penalties outweighing a weak business case, not merely the absence of a "
            "business case.",
        ).format(
            layers=", ".join(f"{k}={_job_layer_map[k]:g}" for k in _job_layers_populated),
            weighted_total=_job_layers.get("weighted_total", "n/a"),
            weights=", ".join(
                f"{k}={v}" for k, v in (_job_layers.get("weights") or {}).items()
                if k in _job_layers_populated
            ),
        )
    else:
        _employment_evidence_caveat_text = _t(
            lang, "p_employment_evidence_caveat_missing",
            "Employment-superiority note: on THIS run, job_promise_layers returned no populated "
            "positive employment-evidence sub-scores (all layers excluded/unavailable) -- "
            "employment superiority in the verdict above, if any, reflects business-side "
            "penalties outweighing a weak business case rather than independently confirmed "
            "positive employment evidence; treat a job-favoring lean as 'not disproven by this "
            "chart's structural business case' rather than 'proven' in that case.",
        )
    section_verdict_reconciliation = f"""
<section id="verdict-reconciliation">
  <h2>{_esc(_t(lang, 'h_verdict_reconciliation', 'Signal Reconciliation: Employment vs. Independent Profession vs. Business'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_verdict_reconciliation_intro',
      "The headline verdict above reflects the authoritative layered business_promise/job_promise system only. "
      "A separate, differently-derived legacy analysis (Jaimini argala/rasi-drishti plus D10 venture-house evidence) "
      "independently reads this chart as favoring an INDEPENDENT PROFESSION (self-directed consulting/practice, not "
      "necessarily a scalable/capital-intensive business and not necessarily salaried employment). Both signals are "
      "shown below with their own confidence, rather than collapsing them into one suppressed headline."))}</p>
  <div class="card">
    <ul class="item-grid">
      <li><strong>{_esc(_t(lang, 'authoritative_verdict_label', 'Authoritative verdict (business_promise/job_promise layer)'))}</strong>: {_esc(verdict_display)} (business_promise={_fmt_pct(_biz_promise)}, job_promise={_fmt_pct(_job_promise)})</li>
      <li><strong>{_esc(_t(lang, 'legacy_mode_gate_label', 'Legacy mode_gate signal (diagnostic-only, not decision-driving)'))}</strong>: {_esc(_lt(lang, _legacy_mode))} (confidence={_esc(_lt(lang, _legacy_conf))}, independent_score={_esc(_mg.get('independent_score'))})</li>
      <li><strong>{_esc(_t(lang, 'final_category_label', 'Final category (reconciled, additive)'))}</strong>: {_esc(_lt(lang, _final_category_raw))}</li>
      <li><strong>{_esc(_t(lang, 'independent_profession_promise_label', 'Independent-profession promise (separate from business_promise)'))}</strong>: {_fmt_pct(_indep_promise)}</li>
      <li><strong>{_esc(_t(lang, 'operating_model_label', 'Best-fit operating model (D1)'))}</strong>: {_esc(_op_taxonomy_label)} ({_esc(_op_model.get('best_fit',''))})</li>
    </ul>
    <p style="margin-top:12px; font-size:12px; color:var(--muted, #666);">{_esc(_t(lang, 'p_mode_vs_comparative_confidence_note', str(authoritative.get('mode_confidence_vs_comparative_confidence_note', ''))))}</p>
    {f'<p style="margin-top:12px; font-weight:600;">{_esc(_headline_framing_text)}</p>' if _headline_framing_text else ''}
    <p style="margin-top:12px;">{_esc(_t(lang, 'p_verdict_reconciliation_note',
        "In plain terms: the business side has genuine, independently-corroborated structural promise (raw evidence "
        "before penalties, and a separate legacy technique both point toward an independent/self-directed professional "
        "path), but execution/retention contraindications below reverse the recommendation for a full employment exit -- "
        "this is a case of 'greater raw promise, reversed by specific contraindications', not 'business unsupported'."))}</p>
    <h3 style="margin-top:16px; font-size:15px;">{_esc(_t(lang, 'h_penalty_math', 'Penalty math applied to the business score'))}</h3>
    <p style="margin-top:-4px;">{_esc(_t(lang, 'p_penalty_math_intro', 'Specific engineered contradiction penalties subtracted from the raw business gate score:'))} <strong>-{_contra_total:g} {_esc(_t(lang, 'points_total', 'points total'))}</strong></p>
    <ul class="item-grid">{_contra_rows_html}</ul>
    <p style="margin-top:12px; font-size:12px; color:var(--muted, #666);">{_esc(_employment_evidence_caveat_text)}</p>
  </div>
</section>"""

    # v37 audit fix: the client edition previously rendered rec["reasoning"]
    # verbatim -- an internal machine string ("gate_score=100
    # contradiction_penalty(business=23.0...) NOT_CALIBRATED_NO_BACKTEST...")
    # that is meaningless to a non-astrologer reader and actively
    # contradicted the polished KPI cards around it. This builds a plain-
    # language summary from the SAME authoritative fields (no
    # recomputation) plus the handful of caveats an honest reading of this
    # chart requires but which were previously buried in technical tables
    # only the astrologer edition showed: the revenue-vs-retention split,
    # D60 unavailability, KP's job-leaning 10th-cusp judgment, sole-owner
    # suitability, and that every ranked sector is exploratory (no exact
    # classical combination match) rather than a confirmed recommendation.
    gross_revenue = prediction.get("gross_revenue_potential")
    profit_retention = prediction.get("profit_retention")
    kp10_leaning = kp10.get("leaning", "")
    all_sectors_exploratory = bool(prediction.get("top_sectors")) and all(
        row.get("match_confidence") == "EXPLORATORY_SECTOR_MATCH" for row in prediction.get("top_sectors", [])
    )
    # QA fix (found while verifying the legacy-removal/percentage pass):
    # this intro sentence was a single hardcoded string that always
    # claimed "the verdict above is Hybrid" regardless of what the
    # verdict actually was -- a chart reading a clean PURSUE_BUSINESS
    # with a wide margin still got told the numbers were "close enough
    # that neither wins outright." Now keyed off the same verdict_raw
    # driving the Final Verdict card just above, so the summary text
    # always agrees with the badge the reader just looked at.
    _summary_intro_by_verdict = {
        "PURSUE_BUSINESS": _t(
            lang, "client_summary_intro_pursue_business",
            "Your chart shows a clear, well-supported case for business over staying employed -- the numbers below back the verdict above without needing a hedge.",
        ),
        "PURSUE_BUSINESS_CAUTIOUSLY": _t(
            lang, "client_summary_intro_pursue_business_cautiously",
            "Your chart favors business by a real margin, but one or more supporting factors fall short of full confidence -- worth pursuing, with the cautions below kept in mind.",
        ),
        "STAY_EMPLOYED": _t(
            lang, "client_summary_intro_stay_employed",
            "Your chart's numbers favor staying employed for now -- business is not well-supported enough on its own evidence to justify stepping away from a salaried role.",
        ),
        "HYBRID_LEANING_BUSINESS": _t(
            lang, "client_summary_intro_hybrid_leaning_business",
            "Your chart shows real commercial and client-facing strength, and leans toward business, but not by a wide enough margin to call it outright -- a phased or piloted approach fits better than a clean break.",
        ),
        "HYBRID_LEANING_JOB": _t(
            lang, "client_summary_intro_hybrid_leaning_job",
            "Your chart shows some commercial strength, but the numbers lean toward staying employed rather than business -- worth validating carefully before committing to a full transition.",
        ),
    }
    _client_summary_parts = [_summary_intro_by_verdict.get(verdict_raw, _t(
        lang, "client_summary_intro",
        "Your chart shows real commercial and client-facing strength, but the numbers below are close enough that neither business nor a salaried role clearly wins outright -- which is why the verdict above is Hybrid, not an outright Pursue Business call.",
    ))]
    _caveat_items: List[str] = []
    if isinstance(gross_revenue, (int, float)) and isinstance(profit_retention, (int, float)) and abs(gross_revenue - profit_retention) >= 15:
        _caveat_items.append(_t(
            lang, "caveat_revenue_vs_retention",
            "Your chart generates opportunity and turnover more easily than it retains net profit -- plan for disciplined cash management, not just growth.",
        ))
    if str(d60_status.get("status", "")) != "OK":
        _caveat_items.append(_t(
            lang, "caveat_d60_unavailable",
            "The deepest confirmation layer (D60) could not be checked for this chart, so this reading rests on the other eight layers alone.",
        ))
    if kp10_leaning == "JOB":
        _caveat_items.append(_t(
            lang, "caveat_kp_job_leaning",
            "One dedicated livelihood-timing method (KP) leans toward salaried employment even though most other methods lean toward business -- a reason for caution, not dismissal.",
        ))
    if all_sectors_exploratory:
        _caveat_items.append(_t(
            lang, "caveat_sectors_exploratory",
            "The sectors listed below are broad aptitude matches, not confirmed exact recommendations -- none of them show a classical exact-combination match in this chart.",
        ))
    caveat_items_html = "".join(f"<li>{_esc(c)}</li>" for c in _caveat_items)
    section_client_summary = (
        f'<p style="font-size:15px; color:var(--ink); margin-top:0;">{_esc(_client_summary_parts[0])}</p>'
        + (f'<ul style="margin-top:10px;">{caveat_items_html}</ul>' if caveat_items_html else "")
    )

    return {
        "section_client_summary": section_client_summary,
        "section_final_verdict": section_final_verdict,
        "verdict_display": verdict_display,
        "section_verdict_reconciliation": section_verdict_reconciliation,
        "authoritative_recommendation": authoritative,
        "generated": generated,
        "proceed_yes": proceed_yes,
        "tier": tier,
        "rec": rec,
        "sig": sig,
        "model_status": model_status,
        "calibration_status": calibration_status,
        "forecast_window": forecast_window,
        "disclaimer_html": disclaimer_html,
        "section_kpi_grid": section_kpi_grid,
        "section_named_fields": section_named_fields,
        "section_capital_strategy_astrologer": section_capital_strategy_astrologer,
        "section_capital_strategy_client": section_capital_strategy_client,
        "section_biz_layers": section_biz_layers,
        "section_job_layers": section_job_layers,
        "section_operating_model": section_operating_model,
        "section_operating_model_d10": section_operating_model_d10,
        "section_operating_model_synthesis": section_operating_model_synthesis,
        "section_contradictions": section_contradictions,
        "section_signals": section_signals,
        "section_risk_signals": section_risk_signals,
        "section_sectors": section_sectors,
        "section_windows": section_windows,
        "timing_status_html": timing_status_html,
        "section_method_status": section_method_status,
        "translation_incomplete": translation_incomplete,
    }


def _technical_appendix_divider_html(lang: str = "en") -> str:
    """Content-restructuring audit fix (item 1/2): a visible divider
    marking the start of the "Technical Appendix" -- the long tail of
    single-technique supporting/deep-dive sections (yogas, legal-dispute
    risk, D2-Hora, Mercury adjudication, Lagnesh Neecha Bhanga, nakshatra
    evidence/chain, foreign-business, partnership fit, muhurta,
    ashtakavarga years) that previously rendered as an undifferentiated
    continuation of the core decision-support content above it, with no
    visual or navigational signal that a reader had moved from "the
    verdict and its direct support" into "narrow classical citations."
    Purely a wrapping/labeling change -- every section after this divider
    is the exact same function call, in the exact same order, as before;
    nothing is removed, renamed, or recomputed."""
    return f"""
<div class="technical-appendix-divider" id="appendix">
  <h2>{_esc(_t(lang, 'h_technical_appendix', 'Technical Appendix — Supporting Evidence & Deep-Dive Checks'))}</h2>
  <p>{_esc(_t(lang, 'p_technical_appendix', 'The verdict, scores, sectors, and timing above already incorporate everything below -- this appendix shows the individual classical checks (yogas, divisional-chart evidence, single-planet adjudications, and more) that fed into them, for readers who want the full citation trail.'))}</p>
</div>"""


def _section_at_a_glance_html(prediction: Dict[str, Any], s: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Content-restructuring audit fix (item 3): a single "At a Glance"
    dashboard combining the four facts a reader currently has to visit
    four separate sections to assemble by hand -- the headline verdict
    (already computed for the hero), the top-ranked sector, the nearest
    favorable timed window, and the single most significant risk flag.
    Placed once, near the top of the body, before Signal Reconciliation --
    everything shown here is a citation of already-computed values from
    elsewhere in this same report (top_sectors[0], timed_windows, the
    significator risk ledger, contradiction findings); nothing new is
    computed or claimed here that isn't independently visible, with full
    detail, further down the page.

    Deliberately audience-agnostic in content (same four facts for both
    editions) -- only the surrounding label language differs slightly --
    since this is meant to be the one card a first-time reader of either
    edition sees before anything else."""
    top_sectors = prediction.get("top_sectors") or []
    top_sector = top_sectors[0] if top_sectors else None

    timed_windows = prediction.get("timed_windows") or []
    top_window = next(
        (w for w in timed_windows if str(w.get("label", "")).upper() in ("STRONG_FAVORABLE", "FAVORABLE")),
        None,
    )

    sig = s.get("sig") or {}
    risk_signals = sig.get("risk_signals") or []
    contradictions = prediction.get("contradiction_findings") or []
    top_risk_text = None
    if risk_signals:
        top_risk_text = str(risk_signals[0])
    elif contradictions:
        top_risk_text = str(contradictions[0].get("note", ""))

    sector_value = (
        f"{_esc(top_sector.get('label', ''))} <span style=\"font-size:12px; color:var(--ink-soft);\">({_fmt_pct(top_sector.get('score'))})</span>"
        if top_sector else
        f"<em>{_esc(_t(lang, 'glance_no_sector', 'No ranked sector available'))}</em>"
    )
    window_value = (
        f"{_esc(str(top_window.get('start_date', '')))} &rarr; {_esc(str(top_window.get('end_date', '')))}"
        f"<span style=\"font-size:12px; color:var(--ink-soft);\"><br>{_esc(str(top_window.get('md_lord','')))}/{_esc(str(top_window.get('ad_lord','')))}</span>"
        if top_window else
        f"<em>{_esc(_t(lang, 'glance_no_window', 'No standout favorable window in range'))}</em>"
    )
    risk_value = (
        f"<span style=\"font-size:13px;\">{_esc(top_risk_text[:160])}{'…' if len(top_risk_text) > 160 else ''}</span>"
        if top_risk_text else
        f"<em>{_esc(_t(lang, 'glance_no_risk', 'No major risk flags recorded'))}</em>"
    )

    return f"""
<section id="at-a-glance">
  <h2>{_esc(_t(lang, 'h_at_a_glance', 'At a Glance'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_at_a_glance', 'The four headline facts from this report, gathered in one place -- each is explained in full further down the page; nothing here is new or separately computed.'))}</p>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">{_esc(_t(lang, 'glance_verdict', 'Verdict'))}</div>
      {s['section_final_verdict']}
    </div>
    <div class="kpi-card">
      <div class="kpi-label">{_esc(_t(lang, 'glance_top_sector', 'Top-Fit Sector'))}</div>
      <div class="kpi-value" style="font-size:16px;">{sector_value}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">{_esc(_t(lang, 'glance_top_window', 'Nearest Favorable Window'))}</div>
      <div class="kpi-value" style="font-size:15px;">{window_value}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">{_esc(_t(lang, 'glance_top_risk', 'Biggest Risk Flag'))}</div>
      <div class="kpi-value" style="font-size:13px; font-weight:600;">{risk_value}</div>
    </div>
  </div>
</section>"""


def _section_detected_yogas_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the "Detected Yogas" / "Classical Combinations" section from
    prediction['detected_yogas'] (see business_determination/yogas.py::
    detect_business_yogas). Returns an empty string when no yogas were
    detected -- keeps reports for charts with none of the currently-
    detected combinations byte-identical to before this feature existed,
    for both the astrologer and client editions (same empty-state pattern
    as _section_partnership_synastry_html above)."""
    yogas = prediction.get("detected_yogas")
    if not yogas:
        status = prediction.get("yoga_detection_status", "NOT_EVALUATED")
        if status == "EVALUATED_NO_MATCH":
            text = (
                "EVALUATED_NO_MATCH -- named-yoga detection ran on the available D1 lordship and placement facts, "
                "but none of the combinations currently implemented by this module met their exact criteria. "
                "This does not mean the chart has no yogas; it means no supported named match was produced by "
                "this detector."
            )
        else:
            text = (
                "NOT_EVALUATED -- the minimum D1 lordship/placement facts required for named-yoga detection were "
                "not available. This is not the same as finding no yogas."
            )
        return f"""
<section id="detected-yogas">
  <h2>{_esc(_t(lang, 'h_detected_yogas' if audience == 'astrologer' else 'h_detected_yogas_client', 'Detected Yogas -- Classical Combinations' if audience == 'astrologer' else 'Special Combinations in Your Chart'))}</h2>
  <p style="font-size:13px; color:var(--muted, #666);">{_esc(text)}</p>
</section>"""

    if audience == "astrologer":
        rows = "".join(
            f"""<li><strong>{_esc(y.get('yoga_name', ''))}</strong>"""
            f"""{f" ({_esc(y.get('sanskrit_name'))})" if y.get('sanskrit_name') else ""}"""
            f""" — <em>{_esc(y.get('confidence_tier', ''))}</em><br>"""
            f"""<span style="font-size:13px; color:var(--muted, #666);">{_esc(y.get('detail', ''))}</span></li>"""
            for y in yogas
        )
        return f"""
<section id="detected-yogas">
  <h2>{_esc(_t(lang, 'h_detected_yogas', 'Detected Yogas — Classical Combinations'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_detected_yogas', 'Discrete named classical/engineered combinations detected on this chart (Raja Yoga, Dhana Yoga, Mercury-Saturn-Rahu business combination) — packaged from the same house-lord evidence scored elsewhere in this report, not a separate scoring pass.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""

    # Client edition: plain-language effect only, no technical citation.
    rows = "".join(
        f"""<li><strong>{_esc(y.get('yoga_name', ''))}</strong> — {_esc(y.get('effect', ''))}</li>"""
        for y in yogas
    )
    return f"""
<section id="detected-yogas">
  <h2>{_esc(_t(lang, 'h_detected_yogas_client', 'Special Combinations in Your Chart'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_detected_yogas_client', 'Named classical combinations found in your chart that support business success.'))}</p>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_yogas_explainer_client', 'A "yoga" is a specific planetary combination that classical texts associate with particular life outcomes -- these are recurring patterns astrologers watch for, not a one-off reading of your chart.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""


def _section_legal_dispute_risk_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the "Legal Dispute / Litigation Risk" section from
    prediction['legal_dispute_risk'] (see business_determination/
    legal_risk.py::detect_legal_dispute_risk). Returns an empty string when
    no risk patterns were detected -- keeps reports for charts with none of
    the currently-detected patterns byte-identical to before this feature
    existed, for both the astrologer and client editions (same empty-state
    pattern as _section_detected_yogas_html above)."""
    risks = prediction.get("legal_dispute_risk")
    if not risks:
        # Issue 15 fix: distinguish NOT_EVALUATED (missing D1 house_lords/
        # planet_house -- the check genuinely could not run) from
        # EVALUATED_NO_MATCH (data present, all 4 named patterns checked,
        # none matched) instead of silently rendering nothing either way,
        # which reads as "no risk found" -- consistent with this report's
        # existing not-evaluated-disclosure pattern used for muhurta/
        # annual-Ashtakavarga elsewhere.
        _legal_status = prediction.get("legal_dispute_risk_status", "NOT_EVALUATED")
        if _legal_status == "NOT_EVALUATED":
            _status_text = _t(
                lang, "p_legal_dispute_risk_not_evaluated",
                "NOT_EVALUATED -- required D1 chart data (house_lords/planet_house) was not available, so "
                "legal-dispute/litigation-risk detection could not run for this chart. This is NOT the same as "
                "'no risk found'; it means the check was not performed.",
            )
        else:
            _status_text = _t(
                lang, "p_legal_dispute_risk_no_match",
                "EVALUATED_NO_MATCH -- legal-dispute/litigation-risk detection ran (Rahu-Ketu axis on 6/7/12, "
                "Mars-Saturn on 6/7/8, afflicted 7th lord, 6th/7th lord exchange) and none of the four named "
                "patterns matched this chart. This reflects only these four specific classical combinations, not "
                "a general absence of operational/liability risk -- see the generic H6/H8/H12 loss/liability "
                "exposure scoring elsewhere in this report (e.g. operational_liability_risk) for that broader read.",
            )
        return f"""
<section id="legal-dispute-risk">
  <h2>{_esc(_t(lang, 'h_legal_dispute_risk' if audience == 'astrologer' else 'h_legal_dispute_risk_client', 'Legal Dispute / Litigation Risk' if audience == 'astrologer' else 'Dispute & Contract Caution Points'))}</h2>
  <p style="font-size:13px; color:var(--muted, #666);">{_esc(_status_text)}</p>
</section>"""

    disclaimer_text = _t(
        lang, 'p_legal_dispute_risk_disclaimer',
        'Astrological indication only, not legal advice. This does not predict a specific outcome, '
        'lawsuit, or legal liability -- it flags classical combinations associated with dispute-prone '
        'periods and relationships so they can be discussed with a qualified legal professional if relevant.'
    )

    if audience == "astrologer":
        rows = "".join(
            f"""<li><strong>{_esc(r.get('risk_type', ''))}</strong>"""
            f""" (H{'/'.join(str(h) for h in r.get('houses_involved', []))})"""
            f""" — <em>{_esc(r.get('confidence_tier', ''))}</em><br>"""
            f"""<span style="font-size:13px; color:var(--muted, #666);">{_esc(r.get('detail', ''))}</span></li>"""
            for r in risks
        )
        return f"""
<section id="legal-dispute-risk">
  <h2>{_esc(_t(lang, 'h_legal_dispute_risk', 'Legal Dispute / Litigation Risk'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_legal_dispute_risk', 'Discrete named litigation/dispute-risk combinations detected on this chart (Rahu-Ketu axis on 6/7/12, Mars-Saturn on 6/7/8, afflicted 7th lord, 6th/7th lord exchange) — distinct from the generic H6/H8/H12 loss/liability exposure language scored elsewhere in this report.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
  <p style="font-size:12px; color:var(--muted, #666);">{_esc(disclaimer_text)}</p>
</section>"""

    # Client edition: plain-language effect only, no technical citation.
    rows = "".join(
        f"""<li><strong>{_esc(r.get('risk_type', '').replace('_', ' ').title())}</strong> — {_esc(r.get('effect', ''))}</li>"""
        for r in risks
    )
    return f"""
<section id="legal-dispute-risk">
  <h2>{_esc(_t(lang, 'h_legal_dispute_risk_client', 'Dispute & Contract Caution Points'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_legal_dispute_risk_client', 'Chart combinations that indicate elevated caution around disputes, contracts, or partnerships.'))}</p>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_legal_risk_explainer_client', 'These come from houses and planetary placements classically linked to conflict and litigation (6th house enemies/disputes, 7th house contracts/partners, 8th/12th house losses) -- flags here mean the pattern is present, not that a dispute will happen.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
  <p style="font-size:12px; color:var(--muted, #666);">{_esc(disclaimer_text)}</p>
</section>"""


_TRANSITION_VERDICT_CSS = {
    "ACT_NOW": "yes",
    "WAIT_FOR_WINDOW": "hybrid",
    "RECONSIDER_MODE": "no",
    "INSUFFICIENT_DATA": "hybrid",
}


def _section_transition_timing_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the "Should You Transition Now, Or Wait?" section from
    prediction['transition_timing_recommendation'] (see
    business_determination/transition_timing.py::
    compute_transition_timing_recommendation). Positioned right after the
    top-level Recommendation/Summary section in both editions (not buried
    near the bottom) because this composes mode_gate's static
    recommended_mode against timing's favorable-window calendar to answer
    the single most actionable question a client asks: switch now, or wait?

    Returns an empty string only if the key is entirely absent (e.g. an
    older cached prediction dict computed before this feature existed) --
    keeps such reports byte-identical, same empty-state convention as
    _section_detected_yogas_html/_section_legal_dispute_risk_html above."""
    tt = prediction.get("transition_timing_recommendation")
    if not tt:
        return ""

    verdict = str(tt.get("verdict", "INSUFFICIENT_DATA"))
    css = _TRANSITION_VERDICT_CSS.get(verdict, "hybrid")
    current_window = tt.get("current_window")
    next_window = tt.get("next_favorable_window")

    verdict_label_astro = {
        "ACT_NOW": _t(lang, "tt_verdict_act_now", "Act Now"),
        "WAIT_FOR_WINDOW": _t(lang, "tt_verdict_wait", "Wait For a Favorable Window"),
        "RECONSIDER_MODE": _t(lang, "tt_verdict_reconsider", "Reconsider Mode (Favors Controlled Experimentation, Not Full Exit)"),
        "INSUFFICIENT_DATA": _t(lang, "tt_verdict_insufficient", "Insufficient Data"),
    }.get(verdict, verdict)

    if audience == "astrologer":
        authoritative = prediction.get("authoritative_recommendation", {}) or {}
        auth_verdict = authoritative.get("verdict", "—")
        auth_action_level = authoritative.get("action_level", "—")
        basis_line = (
            f"{_esc(_t(lang, 'tt_authoritative_verdict', 'Authoritative verdict'))}: {_esc(str(auth_verdict))} "
            f"({_esc(_t(lang, 'tt_action_level', 'action level'))}: {_esc(str(auth_action_level))}) "
            f"· {_esc(_t(lang, 'business_promise_word', 'Business promise'))}: {_fmt_pct(authoritative.get('business_promise'))} "
            f"· {_esc(_t(lang, 'job_promise_word', 'Job promise'))}: {_fmt_pct(authoritative.get('job_promise'))}"
        ) if authoritative else _esc(_t(lang, 'tt_no_basis', 'authoritative recommendation basis unavailable'))
        window_lines = []
        if current_window:
            window_lines.append(
                f"<li>{_esc(_t(lang, 'tt_current_window', 'Current window'))}: {_esc(current_window.get('start_date',''))}"
                f"&ndash;{_esc(current_window.get('end_date',''))} (MD {_esc(current_window.get('md_lord',''))} / "
                f"AD {_esc(current_window.get('ad_lord',''))}) &mdash; <strong>{_esc(current_window.get('label',''))}</strong></li>"
            )
        if next_window:
            window_lines.append(
                f"<li>{_esc(_t(lang, 'tt_next_window', 'Next favorable window'))}: {_esc(next_window.get('start_date',''))}"
                f"&ndash;{_esc(next_window.get('end_date',''))} (MD {_esc(next_window.get('md_lord',''))} / "
                f"AD {_esc(next_window.get('ad_lord',''))}) &mdash; <strong>{_esc(next_window.get('label',''))}</strong></li>"
            )
        windows_html = f"<ul class='item-grid'>{''.join(window_lines)}</ul>" if window_lines else ""
        return f"""
<section id="transition-timing">
  <h2>{_esc(_t(lang, 'h_transition_timing', 'Transition Timing: Act Now or Wait?'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_transition_timing', "Composes the authoritative business_promise/job_promise verdict against timing's favorable-window calendar -- neither subsystem alone answers whether now is the right moment to transition."))}</p>
  <div class="card">
    <div class="final-verdict {css}" style="margin-bottom:12px;">
      <div class="final-verdict-label">{_esc(_t(lang, 'tt_verdict_label', 'Transition Verdict'))}</div>
      <div class="final-verdict-value">{_esc(verdict_label_astro)}</div>
    </div>
    <p style="font-size:14px;">{_esc(basis_line)}</p>
    {windows_html}
    <p style="font-size:14px; margin-top:10px;">{_esc(tt.get('astrologer_detail', ''))}</p>
    <p style="font-size:12px; color:var(--muted, #666); margin-bottom:0;">{_esc(tt.get('disclaimer', ''))}</p>
  </div>
</section>"""

    # Client edition: plain-language message only.
    return f"""
<section id="transition-timing">
  <h2>{_esc(_t(lang, 'h_transition_timing_client', 'Should You Move Now, Or Wait?'))}</h2>
  <div class="card">
    <div class="final-verdict {css}" style="margin-bottom:12px;">
      <div class="final-verdict-label">{_esc(_t(lang, 'tt_verdict_label_client', 'Our Read'))}</div>
      <div class="final-verdict-value">{_esc(verdict_label_astro)}</div>
    </div>
    <p style="font-size:15px; color:var(--ink); margin-top:0;">{_esc(tt.get('client_message', ''))}</p>
    <p style="font-size:12px; color:var(--muted, #666); margin-bottom:0;">{_esc(tt.get('disclaimer', ''))}</p>
  </div>
</section>"""


def _section_d2_hora_evidence_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the "Wealth Flow (D2 Hora)" section from
    prediction['d2_hora_evidence'] (see business_determination/
    house_evidence.py::_d2_native_house_evidence). Returns an empty string
    when no D2 data is available on this chart -- keeps reports for charts
    without D2 data byte-identical to before this feature existed, same
    empty-state pattern as _section_detected_yogas_html/
    _section_legal_dispute_risk_html above. Distinct dedicated section
    (rather than folding into prose) because D2/Hora evidence is a
    discrete, individually-citable list of findings exactly like yogas/
    legal-dispute-risk, not a single blended narrative number the way
    D24/D60 (which only ever produce one status dict, not a list) are
    handled elsewhere in this report."""
    items = prediction.get("d2_hora_evidence")
    if not items:
        return ""

    if audience == "astrologer":
        rows = "".join(
            f"""<li><strong>{'+' if it.get('weight', 0) >= 0 else ''}{it.get('weight', 0)}</strong> — {_esc(it.get('note', ''))}</li>"""
            for it in items
        )
        return f"""
<section id="d2-hora-evidence">
  <h2>{_esc(_t(lang, 'h_d2_hora_evidence', 'Wealth Flow (D2 Hora)'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_d2_hora_evidence', "Corroborating wealth-flow evidence from the Hora (D2) chart -- Moon's Hora (Cancer half) vs Sun's Hora (Leo half) placement of the 2nd/11th lords and the wealth significators (Jupiter, Venus, Moon). A light, narrow-scoped corroboration layer, not a primary wealth determinant -- see the module docstring for the classical basis and caveats."))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""

    # Client edition: plain-language, sign of the finding only.
    rows = "".join(
        f"""<li>{_esc(it.get('note', ''))}</li>"""
        for it in items
    )
    return f"""
<section id="d2-hora-evidence">
  <h2>{_esc(_t(lang, 'h_d2_hora_evidence_client', 'Wealth Flow Indicators'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_d2_hora_evidence_client', 'Additional chart signals about how steadily money is retained versus spent.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""


def _section_d2_hora_deep_evidence_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the D2-Hora deep structural read (audit item 5) from
    prediction['d2_hora_deep_evidence'] (see business_determination/
    house_evidence.py::_d2_hora_deep_evidence) -- D2 Lagna, Hora Lagna
    lord + its own D1 dignity, Sun's/Moon's own condition within D2, and
    separate earning/accumulation/expenditure sub-conclusions. Distinct
    from, and additional to, _section_d2_hora_evidence_html above (which
    renders the flat Sun-Hora/Moon-Hora weighted list this section does
    not duplicate). Returns an empty string when no D2 data is available
    (status != "OK"), same empty-state convention used throughout this
    report generator."""
    data = prediction.get("d2_hora_deep_evidence") or {}
    if data.get("status") != "OK":
        return ""

    if audience == "astrologer":
        rows = "".join(f"<li>{_esc(line)}</li>" for line in (
            f"D2 Lagna Hora: {data.get('d2_lagna_hora', 'n/a')} (lord: {data.get('hora_lagna_lord', 'n/a')}, D1 dignity: {data.get('hora_lagna_lord_d1_dignity', 'n/a')})",
            f"Sun's own condition in D2: {data.get('sun_hora', 'n/a')} ({data.get('sun_condition', 'n/a')})",
            f"Moon's own condition in D2: {data.get('moon_hora', 'n/a')} ({data.get('moon_condition', 'n/a')})",
            f"H2 lord ({data.get('h2_lord', 'n/a')}) Hora: {data.get('h2_lord_hora', 'n/a')}, co-Hora with D2 Lagna: {data.get('h2_lord_co_hora_with_lagna', False)}",
            f"H11 lord ({data.get('h11_lord', 'n/a')}) Hora: {data.get('h11_lord_hora', 'n/a')}, co-Hora with D2 Lagna: {data.get('h11_lord_co_hora_with_lagna', False)}",
            data.get("earning_conclusion", ""),
            data.get("accumulation_conclusion", ""),
            data.get("expenditure_conclusion", ""),
        ) if line)
        return f"""
<section id="d2-hora-deep-evidence">
  <h2>{_esc(_t(lang, 'h_d2_hora_deep_evidence', 'D2-Hora Structural Read'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_d2_hora_deep_evidence', 'D2 Lagna, Hora Lagna lord dignity, and separate earning/accumulation/expenditure sub-conclusions -- extends the Wealth Flow (D2 Hora) list above with a fuller structural read.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""

    # Client edition: the three plain-language sub-conclusions only.
    rows = "".join(f"<li>{_esc(line)}</li>" for line in (
        data.get("earning_conclusion", ""),
        data.get("accumulation_conclusion", ""),
        data.get("expenditure_conclusion", ""),
    ) if line)
    if not rows:
        return ""
    return f"""
<section id="d2-hora-deep-evidence">
  <h2>{_esc(_t(lang, 'h_d2_hora_deep_evidence_client', 'Earning, Saving & Spending Signals'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_d2_hora_deep_evidence_client', 'Separate signals for active earning capacity, retention of wealth, and expenditure pressure.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""


def _section_janma_nakshatra_evidence_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the "Birth Star (Janma Nakshatra) Business Aptitude" section
    from prediction['janma_nakshatra_evidence'] (see business_determination/
    nakshatra_business.py::janma_nakshatra_business_evidence). Returns an
    empty string when no citation is available -- keeps reports for charts
    whose birth nakshatra has no classical business citation on file (or
    whose payload lacks moon_nakshatra) byte-identical to before this
    feature existed, same empty-state pattern as
    _section_d2_hora_evidence_html above. This is a minor, modest-weighted
    (+1.0..+2.0) supporting technique -- distinct from muhurta.py's
    transit-date nakshatra scoring for choosing event dates."""
    items = prediction.get("janma_nakshatra_evidence")
    if not items:
        return ""

    if audience == "astrologer":
        rows = "".join(
            f"""<li><strong>+{it.get('weight', 0)}</strong> — {_esc(it.get('detail', it.get('note', '')))}</li>"""
            for it in items
        )
        return f"""
<section id="janma-nakshatra-evidence">
  <h2>{_esc(_t(lang, 'h_janma_nakshatra_evidence', 'Birth Star (Janma Nakshatra) Business Aptitude'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_janma_nakshatra_evidence', "A minor, modest-weighted supporting classical technique: the native's own birth Moon nakshatra reputation for trade/business aptitude, independent of house/dasha placement already scored elsewhere. Not a primary determinant -- see the module docstring for the classical basis and caveats."))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""

    # Client edition: simple one-liner(s) only.
    rows = "".join(
        f"""<li>{_esc(it.get('effect', it.get('note', '')))}</li>"""
        for it in items
    )
    return f"""
<section id="janma-nakshatra-evidence">
  <h2>{_esc(_t(lang, 'h_janma_nakshatra_evidence_client', 'Your Birth Star & Business'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_janma_nakshatra_evidence_client', 'A supporting, minor signal based on your birth star.'))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""


def _section_janma_nakshatra_chain_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the fuller nakshatra-vocational chain section from
    prediction['janma_nakshatra_full_chain'] (see business_determination/
    nakshatra_business.py::janma_nakshatra_full_chain_evidence): 10th
    lord's nakshatra-lord, Amatyakaraka's nakshatra, current dasha-lord's
    nakshatra linkage, and whether the chain terminates in a
    business-relevant house (2/3/6/7/10/11). Structural chain data, not a
    weighted citation ledger -- distinct from
    _section_janma_nakshatra_evidence_html above (the single Janma
    Nakshatra table-lookup). Returns an empty string when the chain has no
    populated sub-fields, keeping reports without this data unaffected."""
    chain = prediction.get("janma_nakshatra_full_chain") or {}
    tenth = chain.get("tenth_lord_nakshatra_lord") or {}
    amk = chain.get("amatyakaraka_nakshatra") or {}
    dasha = chain.get("dasha_lord_nakshatra_linkage") or {}
    if not (tenth or amk or dasha):
        return ""

    terminates = bool(chain.get("terminates_in_relevant_house"))
    terminal_hits = chain.get("terminal_house_hits") or []

    if audience == "astrologer":
        rows = []
        if tenth:
            rows.append(
                f"<li><strong>10th-lord nakshatra chain:</strong> 10th lord {_esc(str(tenth.get('tenth_lord','')))} "
                f"is born in {_esc(str(tenth.get('nakshatra','')))}, ruled by {_esc(str(tenth.get('nakshatra_lord','')))} "
                f"(placed in house {_esc(str(tenth.get('nakshatra_lord_house','')))}).</li>"
            )
        if amk:
            rows.append(
                f"<li><strong>Amatyakaraka chain:</strong> Amatyakaraka {_esc(str(amk.get('amatyakaraka','')))} "
                f"is born in {_esc(str(amk.get('nakshatra','')))}, ruled by {_esc(str(amk.get('nakshatra_lord','')))} "
                f"(placed in house {_esc(str(amk.get('nakshatra_lord_house','')))}).</li>"
            )
        if dasha:
            rows.append(
                f"<li><strong>Current dasha-lord chain:</strong> {_esc(str(dasha.get('dasha_lord','')))} "
                f"is born in {_esc(str(dasha.get('dasha_lord_nakshatra','')))}, ruled by "
                f"{_esc(str(dasha.get('nakshatra_lord','')))} (house {_esc(str(dasha.get('nakshatra_lord_house','')))}: "
                f"{_esc(str(dasha.get('nakshatra_lord_house_significations','')))}).</li>"
            )
        verdict = (
            f"Chain terminates in a business-relevant house ({', '.join(str(h) for h in terminal_hits)}) -- "
            "supports a commerce/service/business vocational direction."
            if terminates else
            "Chain does not terminate in a business-relevant house (2/3/6/7/10/11) -- "
            "no additional nakshatra-chain support for a business vocational direction from this technique."
        )
        return f"""
<section id="janma-nakshatra-chain">
  <h2>{_esc(_t(lang, 'h_nakshatra_chain', 'Nakshatra-Lord Vocational Chain'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_nakshatra_chain', 'Traces the classical nakshatra-lord chain (10th lord, Amatyakaraka, current dasha lord) to see whether it terminates in a business/commerce/service-relevant house -- a structural corroboration layer, not a standalone weighted score.'))}</p>
  <div class="card"><ul class="item-grid">{''.join(rows)}</ul>
  <p><em>{_esc(verdict)}</em></p></div>
</section>"""

    verdict_client = (
        _t(lang, 'p_nakshatra_chain_client_yes', 'The nakshatra-lord chain in your chart points toward a business/service/commerce vocational direction.')
        if terminates else
        _t(lang, 'p_nakshatra_chain_client_no', 'The nakshatra-lord chain in your chart does not add extra support toward a business vocational direction.')
    )
    return f"""
<section id="janma-nakshatra-chain">
  <h2>{_esc(_t(lang, 'h_nakshatra_chain_client', 'Vocational Direction (Star-Lord Chain)'))}</h2>
  <p style="margin-top:-8px;">{_esc(verdict_client)}</p>
</section>"""


def _section_mercury_adjudication_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Render the consolidated Mercury judgment when Mercury carries the
    business/career decision.  The engine already computes this evidence;
    keeping it out of HTML made the most important planet unauditable."""
    row = prediction.get("mercury_adjudication") or {}
    if row.get("status") != "OK":
        return ""
    combustion = row.get("combustion_verdict") or {}
    strength = row.get("strength_metric") or {}
    houses_ruled_list = row.get("houses_ruled", []) or []
    houses = ", ".join(f"H{h}" for h in houses_ruled_list) or "--"

    # Founder-dependency qualitative flag: Mercury ruling BOTH 7th
    # (commerce/partnerships) and 10th (profession/authority) while
    # combust-but-strong (own-sign/exalted, not weak/debilitated) reads
    # as one person structurally holding strategist + negotiator +
    # operator + decision-maker roles at once -- a real over-centralization
    # tendency, not a score change (that's what the combustion penalty
    # already covers), but a qualitative flag this report previously never
    # surfaced.
    _rules_7_and_10 = 7 in houses_ruled_list and 10 in houses_ruled_list
    _is_combust = bool(combustion.get("combust"))
    _strong_dignity = str(row.get("d1_dignity") or "") in ("OWN", "EXALTED", "MOOLATRIKONA")
    _founder_dependency_flag = _rules_7_and_10 and _is_combust and _strong_dignity
    _founder_dependency_text = _t(
        lang, "p_mercury_founder_dependency",
        "Founder-dependency signal: Mercury rules BOTH the 7th house (commerce/partnerships) "
        "and 10th house (profession/authority) and is combust-but-strong (dignity holds despite "
        "combustion). Classically this reads as one person holding the strategist, negotiator, "
        "operator, and decision-maker roles simultaneously rather than delegating them -- this "
        "supports business ability but signals founder-dependency risk. Deliberate delegation "
        "and management-team-building are advisable so the venture is not structurally bottlenecked "
        "on one person's bandwidth.",
    ) if _founder_dependency_flag else ""

    if audience == "client":
        return f"""
<section id="mercury-adjudication">
  <h2>{_esc(_t(lang, 'h_mercury_adjudication_client', 'Mercury: Commerce and Career'))}</h2>
  <div class="card">
    <p>{_esc(row.get('synthesized_verdict', ''))}</p>
    <p style="font-size:12px; color:var(--muted, #666);">Mercury is {_esc('combust' if combustion.get('combust') else 'not combust')} under the declared rule ({_esc(combustion.get('reason', 'not available'))}). This can modify how reliably its commercial and professional promise expresses.</p>
    {f'<p style="font-size:12px; color:var(--muted, #666); margin-top:8px;">{_esc(_founder_dependency_text)}</p>' if _founder_dependency_text else ''}
  </div>
</section>"""
    details = [
        ("Houses ruled", _fmt_field_value(lang, houses)),
        ("D1 house", _fmt_field_value(lang, row.get("own_d1_house"))),
        ("D1 dignity", _esc(row.get("d1_dignity") or "NOT_AVAILABLE")),
        ("D9 dignity", _esc(row.get("d9_dignity") or "NOT_AVAILABLE")),
        ("D10 dignity", _esc(row.get("d10_dignity") or "NOT_AVAILABLE")),
        ("Retrograde", _fmt_field_value(lang, row.get("retrograde"))),
        ("Combustion distance", (f"{_fmt_field_value(lang, row.get('combustion_distance_deg'))} deg" if row.get('combustion_distance_deg') is not None else _fmt_field_value(lang, None))),
        ("Combustion verdict", f"{_fmt_yes_no(lang, combustion.get('combust'))} -- {_esc(combustion.get('reason', ''))}"),
        ("Strength metric", f"{_esc(strength.get('source', 'NOT_AVAILABLE'))}: {_esc(strength.get('value', 'NOT_AVAILABLE'))}"),
        ("Nakshatra", _esc(row.get("nakshatra") or "NOT_AVAILABLE")),
        ("Nakshatra lord", _esc(row.get("nakshatra_lord") or "NOT_AVAILABLE")),
        ("KP sub-lord", _esc(row.get("kp_sub_lord") or "NOT_AVAILABLE")),
        ("H7 strength", _fmt_field_value(lang, row.get("h7_strength"))),
        ("H10 strength", _fmt_field_value(lang, row.get("h10_strength"))),
    ]
    table = _table(["Mercury factor", "Observed value"], details)
    return f"""
<section id="mercury-adjudication">
  <h2>{_esc(_t(lang, 'h_mercury_adjudication', 'Mercury Adjudication -- Commerce vs Career'))}</h2>
  <p style="margin-top:-8px;">A consolidated audit of Mercury's combustion, motion, dignity, strength, nakshatra/KP context and H7-versus-H10 expression. Missing varga fields are shown explicitly rather than silently treated as neutral.</p>
  <div class="card">{table}<p><strong>Synthesis:</strong> {_esc(row.get('synthesized_verdict', ''))}</p>
  {f'<p style="margin-top:8px; font-size:13px;"><strong>{_esc(_t(lang, "h_mercury_founder_dependency", "Founder-dependency note"))}:</strong> {_esc(_founder_dependency_text)}</p>' if _founder_dependency_text else ''}
  </div>
</section>"""


def _section_lagnesh_neecha_bhanga_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the explicit Lagnesh Neecha Bhanga adjudication (audit item
    5) -- an already-computed check (house_evidence.py::
    lagnesh_neecha_bhanga_adjudication, reusing the real, tested
    _neecha_bhanga_status()) that was previously only visible buried
    inside free-form significator evidence notes. Returns an empty string
    when status is not OK/NOT_APPLICABLE (e.g. suppressed or Lagnesh
    unavailable) so this section only appears when there is a real,
    citable verdict to show."""
    row = prediction.get("lagnesh_neecha_bhanga") or {}
    status = row.get("status")
    if status not in ("OK", "NOT_APPLICABLE"):
        return ""
    if status == "NOT_APPLICABLE":
        # Lagnesh is not debilitated on this chart -- nothing to caution
        # about, so skip rather than render a non-finding as a section.
        return ""
    note = row.get("note", "")
    heading = _t(lang, "h_lagnesh_neecha_bhanga", "Lagna Lord (Lagnesh) Debilitation -- Neecha Bhanga Check")
    if audience == "client":
        # Readability audit fix: this was the one client-audience section
        # in the whole file that reused the raw, dense engine-generated
        # `note` verbatim (full dispositor-chain/cancellation-condition
        # prose meant for a practicing astrologer) instead of a plain-
        # language sentence -- every other client section in this file
        # follows the "single simple framing line" pattern. Built here
        # from the same structured fields (lagnesh, cancelled) the
        # astrologer table below cites, not a re-interpretation of new
        # astrology -- just a plain-English restatement of the same
        # already-computed verdict.
        client_heading = _t(lang, "h_lagnesh_neecha_bhanga_client", "Confidence for Going It Alone (Lagna Check)")
        lagnesh_name = _esc(str(row.get("lagnesh", "")))
        if row.get("cancelled"):
            client_note = _t(
                lang, "p_lagnesh_client_cancelled",
                "The planet that represents your sense of self and personal drive ({lagnesh}) starts from a "
                "weakened position in your chart -- but classical rules show this weakness is offset by another "
                "factor, so it does not significantly hold back your confidence to strike out on your own."
            ).format(lagnesh=lagnesh_name)
        else:
            client_note = _t(
                lang, "p_lagnesh_client_uncancelled",
                "The planet that represents your sense of self and personal drive ({lagnesh}) starts from a "
                "weakened position in your chart, and classical rules do not show this being offset by another "
                "factor. This mainly affects confidence for a fully self-funded, solo venture -- it does not "
                "reduce your ability to succeed in advisory, teaching, or team-based professional roles, which "
                "depend on other parts of the chart instead."
            ).format(lagnesh=lagnesh_name)
        return f"""
<section id="lagnesh-neecha-bhanga">
  <h2>{_esc(client_heading)}</h2>
  <div class="card"><p>{_esc(client_note)}</p></div>
</section>"""
    details = [
        ("Lagnesh", _fmt_field_value(lang, row.get("lagnesh"))),
        ("Dignity", _fmt_field_value(lang, row.get("dignity"))),
        ("Sign", _fmt_field_value(lang, row.get("sign"))),
        ("Dispositor of debilitation sign", _fmt_field_value(lang, row.get("dispositor"))),
        ("Neecha Bhanga cancelled?", _fmt_yes_no(lang, row.get("cancelled"))),
        ("Cancellation reason (if any)", _esc(row.get("cancellation_reason") or "--")),
    ]
    table = _table(["Factor", "Observed value"], details)
    return f"""
<section id="lagnesh-neecha-bhanga">
  <h2>{_esc(heading)}</h2>
  <p style="margin-top:-8px;">Explicit adjudication of whether the Lagna lord's debilitation is classically cancelled (Neecha Bhanga) on this chart -- real dispositor and cancellation-condition citations, not a flat claim.</p>
  <div class="card">{table}<p><strong>Verdict:</strong> {_esc(note)}</p></div>
</section>"""


def _section_d10_rectification_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the D10 birth-time rectification sensitivity subsection
    from prediction['d10_rectification_sensitivity'] (see
    business_determination/d10_rectification.py). Placed near the D10
    evidence in the report so a reader sees, right alongside D10's
    decisive negative business findings, whether those findings are
    STABLE or FRAGILE to ordinary birth-time recording uncertainty.
    Returns an empty string when status != OK (no ephemeris/dob/tob/lat/
    lon available), so reports without a working ephemeris backend are
    unaffected."""
    sens = prediction.get("d10_rectification_sensitivity") or {}
    if sens.get("status") != "OK":
        return ""

    stability = sens.get("stability", "UNKNOWN")
    note = sens.get("note", "")
    badge = "STABLE" if stability == "STABLE" else "FRAGILE"
    color = "#1a7f37" if stability == "STABLE" else "#b42318"

    if audience == "astrologer":
        offsets = sens.get("offset_results") or []
        rows = "".join(
            f"""<li><strong>{o.get('offset_minutes', 0):+d} min</strong> — D10 Lagna: {_esc(str(o.get('d10_lagna','')))}, """
            f"""matches baseline: {'yes' if o.get('matches_baseline') else 'NO (diff)'}</li>"""
            for o in offsets if o.get("status") != "COMPUTE_FAILED"
        )
        return f"""
<section id="d10-rectification-sensitivity">
  <h3>{_esc(_t(lang, 'h_d10_rectification', 'D10 Birth-Time Rectification Sensitivity'))}
    <span style="color:{color}; font-weight:bold;">[{badge}]</span></h3>
  <p style="margin-top:-8px;">{_esc(note)}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""

    client_note = (
        _t(lang, 'p_d10_rectification_client_stable', 'This finding was checked against small birth-time recording errors (up to 5 minutes) and did not change -- it is a stable/reliable reading.')
        if stability == "STABLE" else
        _t(lang, 'p_d10_rectification_client_fragile', 'This finding was checked against small birth-time recording errors (up to 5 minutes) and DID change for some offsets -- treat it with caution and consider birth-time rectification (confirming your exact birth time) before relying heavily on it.')
    )
    return f"""
<section id="d10-rectification-sensitivity">
  <h3>{_esc(_t(lang, 'h_d10_rectification_client', 'Reliability Check (Birth-Time Sensitivity)'))}</h3>
  <p style="margin-top:-8px;">{_esc(client_note)}</p>
</section>"""


def _section_foreign_business_evidence_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the "Foreign / Cross-Border Business Indications" section
    from prediction['foreign_business_evidence'] (see business_determination/
    foreign_business.py::foreign_business_viability_evidence). Returns an
    empty string when no citation is available (no notable foreign
    indicator on this chart, or house_lords/planet_house data is
    unavailable) -- same empty-state pattern as
    _section_janma_nakshatra_evidence_html/_section_d2_hora_evidence_html
    above, so reports for charts with nothing to cite here stay
    byte-identical to before this feature existed.

    Astrologer edition: full technical citations (12th/9th lord dignity,
    Rahu placement/conjunction-aspect notes). Client edition: a single
    simple framing line -- supportive, cautionary, or (implicitly, via the
    empty-string return above) neutral/no-notable-indication."""
    items = prediction.get("foreign_business_evidence")
    if not items:
        return ""

    if audience == "astrologer":
        rows = "".join(
            f"""<li><strong>{'+' if it.get('polarity') == 'POSITIVE' else ''}{it.get('weight', 0)}</strong> — {_esc(it.get('note', ''))}</li>"""
            for it in items
        )
        return f"""
<section id="foreign-business-evidence">
  <h2>{_esc(_t(lang, 'h_foreign_business_evidence', 'Foreign / Cross-Border Business Indications'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_foreign_business_evidence', "A dedicated, modest-weighted supporting technique bundle answering one narrow question -- is foreign/cross-border business favorable for this native -- via 12th-lord (primary, videsha/foreign residence house) and 9th-lord (secondary, long-distance/foreign-learning) strength-dignity, plus Rahu's foreign-house placement and conjunction/aspect to the 9th/12th lord. Distinct from the generic Import/Export & Foreign Trade sector-affinity averaging elsewhere in this report; not a primary determinant on its own -- see the module docstring for classical basis and caveats."))}</p>
  <div class="card"><ul class="item-grid">{rows}</ul></div>
</section>"""

    # Client edition: a simple supportive/cautionary framing line, no
    # technical citations. Uses the strongest-magnitude item's polarity as
    # the overall framing (mirrors how other client sections in this
    # report summarize a ledger into one plain-language read).
    has_positive = any(it.get("polarity") == "POSITIVE" for it in items)
    has_negative = any(it.get("polarity") == "NEGATIVE" for it in items)
    if has_positive and not has_negative:
        framing = _t(lang, 'p_foreign_business_client_positive', 'Your chart shows supportive indications for cross-border or foreign-facing business.')
    elif has_negative and not has_positive:
        framing = _t(lang, 'p_foreign_business_client_caution', 'Your chart shows some cautionary indications specifically for cross-border or foreign-facing business -- worth reviewing before committing to an overseas venture.')
    else:
        framing = _t(lang, 'p_foreign_business_client_mixed', 'Your chart shows mixed indications for cross-border or foreign-facing business -- some supportive, some cautionary.')
    return f"""
<section id="foreign-business-evidence">
  <h2>{_esc(_t(lang, 'h_foreign_business_evidence_client', 'Foreign / Cross-Border Business'))}</h2>
  <p style="margin-top:-8px;">{_esc(framing)}</p>
</section>"""


def _section_muhurta_recommendations_html(
    muhurta_result: Dict[str, Any], lang: str = "en", audience: str = "astrologer",
) -> str:
    """Renders a "Muhurta Recommendations" (auspicious date/time selection)
    section from the dict returned by business_determination/muhurta.py::
    find_business_muhurta(start_date, end_date, event_type, location,
    native_payload=None).

    This is a SEPARATE, on-demand computation -- find_business_muhurta()
    scans a date RANGE for a caller-chosen event type/location and is not
    part of compute_business_prediction()'s fixed-birth-chart pipeline, so
    this renderer is not auto-invoked inside build_report_context()/the
    main report flow above. A caller who wants a combined report should:

        prediction = compute_business_prediction(payload)
        ctx = build_report_context(prediction, ...)
        muhurta_result = find_business_muhurta(start, end, event_type, location)
        muhurta_html = _section_muhurta_recommendations_html(muhurta_result, lang, audience)
        # then append muhurta_html into the assembled report HTML string
        # (e.g. right before the closing </body>, or wherever the caller's
        # template inserts other section_* strings from ctx).

    Returns an empty string when status != "OK" or there are no results,
    so a report is never left with a broken/empty-looking section.
    """
    if not muhurta_result or muhurta_result.get("status") != "OK":
        note = _esc((muhurta_result or {}).get("note", "Muhurta scan not available."))
        status = _esc((muhurta_result or {}).get("status", "UNKNOWN"))
        return f"""
<section id="muhurta-recommendations">
  <h2>{_esc(_t(lang, 'h_muhurta', 'Auspicious Date/Time Recommendations'))}</h2>
  <div class="card"><p><em>{status}</em>: {note}</p></div>
</section>"""

    results = muhurta_result.get("results") or []
    if not results:
        return ""

    top = results[:10]
    disclaimer_text = _t(
        lang, 'p_muhurta_disclaimer',
        'Electional (muhurta) guidance only -- a rule-based reading of classical Panchang '
        'and Kalam conventions for the requested event type, not a guarantee of outcome. '
        'Cross-check with a qualified astrologer before committing to a specific date, '
        'especially for high-stakes events.'
    )

    if audience == "astrologer":
        rows = "".join(
            f"""<li><strong>{_esc(r.get('date',''))}</strong> """
            f"""({_esc(r.get('window_start','').split(' ')[-1] if r.get('window_start') else '')}"""
            f"""-{_esc(r.get('window_end','').split(' ')[-1] if r.get('window_end') else '')})"""
            f""" — <em>{_esc(r.get('tier',''))}</em> ({_fmt_pct(r.get('score_0_100', 0))})<br>"""
            f"""<span style="font-size:13px; color:var(--muted, #666);">"""
            f"""{_esc('; '.join(r.get('citations', [])))}"""
            f"""<br>Panchang: {_esc(', '.join(f'{k}={v}' for k, v in (r.get('panchang') or {}).items()))}"""
            f"""<br>Rahu Kalam {_esc(r.get('rahu_kalam',''))}, Yamaganda {_esc(r.get('yamaganda',''))}, """
            f"""Gulika Kalam {_esc(r.get('gulika_kalam',''))}</span></li>"""
            for r in top
        )
        return f"""
<section id="muhurta-recommendations">
  <h2>{_esc(_t(lang, 'h_muhurta', 'Auspicious Date/Time Recommendations'))} — {_esc(muhurta_result.get('event_type',''))}</h2>
  <p style="margin-top:-8px;">{_esc(muhurta_result.get('note',''))}</p>
  <div class="card"><ol>{rows}</ol></div>
  <p style="font-size:12px; color:var(--muted, #666);">{_esc(disclaimer_text)}</p>
</section>"""

    # Client edition: plain-language reasons only, no technical citation.
    rows = "".join(
        f"""<li><strong>{_esc(r.get('date',''))}</strong> — <em>{_esc(r.get('tier',''))}</em><br>"""
        f"""<span style="font-size:13px;">{_esc(' '.join(r.get('reasons', [])))}</span></li>"""
        for r in top
    )
    return f"""
<section id="muhurta-recommendations">
  <h2>{_esc(_t(lang, 'h_muhurta_client', 'Best Dates for Your Business Event'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_muhurta_explainer_client', 'A "muhurta" is a classically chosen auspicious date and time, picked using the Panchang (lunar-day calendar) and planetary hours -- the dates below are the strongest matches for your event within the range you requested.'))}</p>
  <div class="card"><ol>{rows}</ol></div>
  <p style="font-size:12px; color:var(--muted, #666);">{_esc(disclaimer_text)}</p>
</section>"""


def _section_ashtakavarga_years_html(
    ranking_result: Dict[str, Any], lang: str = "en", audience: str = "astrologer",
) -> str:
    """Renders a "Strongest Years (Ashtakavarga)" section from the dict
    returned by business_determination/ashtakavarga_timing.py::
    rank_business_years(payload, start_year, end_year, timing_windows=None).

    This is a SEPARATE, on-demand computation with a caller-chosen YEAR
    RANGE (not part of compute_business_prediction()'s fixed-birth-chart
    pipeline), so this renderer is not auto-invoked inside
    build_report_context()/the main report flow -- same calling pattern as
    _section_muhurta_recommendations_html above:

        prediction = compute_business_prediction(payload)
        ctx = build_report_context(prediction, ...)
        ranking = rank_business_years(payload, start_year, end_year,
                                       timing_windows=prediction.get("timed_windows"))
        av_html = _section_ashtakavarga_years_html(ranking, lang, audience)
        # then append av_html into the assembled report HTML string

    Returns an empty string when status != "OK" or there are no ranked
    years, so a report is never left with a broken/empty-looking section.
    """
    if not ranking_result or ranking_result.get("status") != "OK":
        note = _esc((ranking_result or {}).get("note", "Ashtakavarga year ranking not available."))
        status = _esc((ranking_result or {}).get("status", "UNKNOWN"))
        return f"""
<section id="ashtakavarga-years">
  <h2>{_esc(_t(lang, 'h_ashtakavarga_years', 'Strongest Years (Ashtakavarga)'))}</h2>
  <div class="card"><p><em>{status}</em>: {note}</p></div>
</section>"""

    ranked = ranking_result.get("ranked_years") or []
    if not ranked:
        return ""

    top = ranked[:10]
    disclaimer_text = _t(
        lang, 'p_ashtakavarga_years_disclaimer',
        'Sarvashtakavarga (SAV) year ranking is a heuristic cross-reference of natal SAV bindu '
        'strength in the business houses (2nd/6th/7th/10th/11th) against mean-motion-projected '
        'Jupiter/Saturn transits -- not a full ephemeris re-derivation and not a guarantee of '
        'outcome for any specific year. Cross-check against the dasha/bhukti timing windows '
        'elsewhere in this report and with a qualified astrologer before committing to a specific year.'
    )

    def _fmt_bindus(v: Any) -> str:
        # Raw-value leak fix: bav_bindus_jupiter/saturn is a genuine Python
        # None (not a placeholder string) whenever BAV_UNAVAILABLE -- left
        # unhandled this rendered the literal word "None" in the report
        # ("Saturn=None bindus"). Anything non-numeric reads as "n/a".
        return str(v) if isinstance(v, (int, float)) else "n/a"

    if audience == "astrologer":
        rows = "".join(
            f"""<li><strong>{y.get('year','')}</strong>"""
            f""" — <em>{_esc(y.get('tier',''))}</em> (SAV score {y.get('sav_score', 0)}"""
            f""", BAV bonus {y.get('bav_bonus', 0):+.1f}, composite {y.get('composite_score', y.get('sav_score', 0))})<br>"""
            f"""<span style="font-size:13px; color:var(--muted, #666);">{_esc(y.get('reasons', {}).get('detail', ''))}"""
            + (
                f"""<br>BAV detail: Jupiter={_fmt_bindus(y.get('bav_bindus_jupiter'))} bindus ({_esc(y.get('bav_interpretation', {}).get('Jupiter', ''))}), """
                f"""Saturn={_fmt_bindus(y.get('bav_bindus_saturn'))} bindus ({_esc(y.get('bav_interpretation', {}).get('Saturn', ''))}) """
                f"""[bav_status={_esc(y.get('bav_status', ''))}]"""
                if y.get('bav_status') != "NOT_APPLICABLE" else ""
            )
            + (
                f"""<br>Dasha corroboration: {_esc('; '.join(f"{d.get('md_lord','')}/{d.get('ad_lord','')} {d.get('label','')}" for d in y.get('dasha_corroboration', [])))}"""
                if y.get('dasha_corroboration') else ""
            )
            + """</span></li>"""
            for y in top
        )
        return f"""
<section id="ashtakavarga-years">
  <h2>{_esc(_t(lang, 'h_ashtakavarga_years', 'Strongest Years (Ashtakavarga)'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_ashtakavarga_years', 'Calendar years in the requested range ranked by a composite Sarvashtakavarga (SAV) business-strength score, cross-referenced against dasha/bhukti windows elsewhere in this report where available.'))}</p>
  <div class="card"><ol>{rows}</ol></div>
  <p style="font-size:12px; color:var(--muted, #666);">{_esc(disclaimer_text)}</p>
</section>"""

    # Client edition: plain-language effect only, no technical citation.
    rows = "".join(
        f"""<li><strong>{y.get('year','')}</strong> — <em>{_esc(y.get('tier',''))}</em><br>"""
        f"""<span style="font-size:13px;">{_esc(y.get('reasons', {}).get('effect', ''))}</span></li>"""
        for y in top
    )
    return f"""
<section id="ashtakavarga-years">
  <h2>{_esc(_t(lang, 'h_ashtakavarga_years_client', 'Your Strongest Years for Business'))}</h2>
  <div class="card"><ol>{rows}</ol></div>
  <p style="font-size:12px; color:var(--muted, #666);">{_esc(disclaimer_text)}</p>
</section>"""


def _section_partnership_synastry_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders the "Partnership Fit" section from prediction['partnership_synastry']
    (see business_determination/synastry.py::compute_partnership_synastry).
    Returns an empty string when no synastry data is present -- this keeps
    single-native reports (no partner_payload passed to
    compute_business_prediction()) byte-identical to before this feature
    existed, for both the astrologer and client editions."""
    syn = prediction.get("partnership_synastry")
    if not syn:
        return ""
    if syn.get("status") != "OK":
        note = _esc(syn.get("note", "Partnership synastry not evaluated."))
        return f"""
<section id="partnership-fit">
  <h2>{_esc(_t(lang, 'h_partnership_fit', 'Partnership Fit'))}</h2>
  <div class="card"><p>{note}</p></div>
</section>"""

    label = syn.get("compatibility_label", "—")
    score = syn.get("composite_score_0_100", 0)
    strengths = syn.get("complementary_strengths", [])
    frictions = syn.get("friction_points", [])
    strengths_html = "".join(f"<li>{_esc(s.get('note', ''))}</li>" for s in strengths) or f"<li>{_esc(_t(lang, 'none_noted', 'None noted.'))}</li>"
    frictions_html = "".join(f"<li>{_esc(f.get('note', ''))}</li>" for f in frictions) or f"<li>{_esc(_t(lang, 'none_noted', 'None noted.'))}</li>"

    d7 = syn.get("seventh_house_d7_cross_comparison") or {}
    d7_html = ""
    if d7.get("status") == "OK":
        d7_html = f"""
    <p style="font-size:13px;">{_esc(_t(lang, 'p_d7_corroboration', 'D7 (Saptamsha) corroboration'))}: A's D1-H7 lord ({_esc(str(d7.get('h7_lord_a','')))}) in D7 sign {_esc(str(d7.get('d7_sign_a','')))} (dignity: {_esc(str(d7.get('d7_dignity_a','')))}); B's D1-H7 lord ({_esc(str(d7.get('h7_lord_b','')))}) in D7 sign {_esc(str(d7.get('d7_sign_b','')))} (dignity: {_esc(str(d7.get('d7_dignity_b','')))}).</p>"""
    elif d7.get("status") == "MISSING_DATA":
        d7_html = f"""
    <p style="font-size:12px; color:var(--muted, #666);">{_esc(_t(lang, 'p_d7_unavailable', 'D7 (Saptamsha) corroboration not evaluated — insufficient divisional-chart/degree data for one or both natives.'))}</p>"""

    if audience == "astrologer":
        comp = syn.get("component_scores_0_20", {})
        components_html = "".join(
            f"<li>{_esc(k)}: {v} / 20</li>" for k, v in comp.items()
        )
        return f"""
<section id="partnership-fit">
  <h2>{_esc(_t(lang, 'h_partnership_fit', 'Partnership Fit'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_partnership_fit', 'Chart-to-chart synastry between the primary native and the proposed partner/co-founder — Moon-sign element/modality harmony, 7th-house cross-comparison, D7 (Saptamsha) corroboration, Mercury/Jupiter/Saturn/Mars natural friendliness, and current-dasha overlap. NOT the marriage Kuta/Ashtakoota system.'))}</p>
  {d7_html}
  <div class="card">
    <p style="margin-top:0;">{_esc(_t(lang, 'composite_score_word', 'Composite compatibility score'))}: <strong style="color:var(--navy); font-size:16px;">{_fmt_pct(score)}</strong> — <strong>{_esc(label)}</strong></p>
    <ul>{components_html}</ul>
  </div>
  <div class="grid-2">
    <div class="card">
      <h3 style="margin-top:0; color:var(--green);">{_esc(_t(lang, 'h3_complementary_strengths', 'Complementary strengths'))}</h3>
      <ul>{strengths_html}</ul>
    </div>
    <div class="card">
      <h3 style="margin-top:0; color:var(--red);">{_esc(_t(lang, 'h3_friction_points', 'Friction points'))}</h3>
      <ul>{frictions_html}</ul>
    </div>
  </div>
  <p style="font-size:12px; color:var(--muted, #666);">{_esc(syn.get('note', ''))}</p>
</section>"""

    # Client edition: same numbers, simplified prose, no raw component ledger.
    d7_client_html = ""
    if d7.get("status") == "OK":
        d7_positive = d7.get("d7_dignity_a") in ("EXALTED", "OWN_SIGN", "MOOLATRIKONA", "GREAT_FRIEND") or \
                      d7.get("d7_dignity_b") in ("EXALTED", "OWN_SIGN", "MOOLATRIKONA", "GREAT_FRIEND")
        d7_negative = d7.get("d7_dignity_a") in ("DEBILITATED", "GREAT_ENEMY") or \
                      d7.get("d7_dignity_b") in ("DEBILITATED", "GREAT_ENEMY")
        if d7_negative:
            d7_msg = _t(lang, 'p_d7_client_caution', 'A deeper-level (Saptamsha) check raises some caution about the partnership fit — worth a closer look before committing.')
        elif d7_positive:
            d7_msg = _t(lang, 'p_d7_client_support', 'A deeper-level (Saptamsha) check also supports this partnership reading.')
        else:
            d7_msg = _t(lang, 'p_d7_client_neutral', 'A deeper-level (Saptamsha) check was evaluated and is broadly neutral.')
        d7_client_html = f'<p style="font-size:13px;">{_esc(d7_msg)}</p>'

    return f"""
<section id="partnership-fit">
  <h2>{_esc(_t(lang, 'h_partnership_fit', 'Partnership Fit'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_partnership_fit_client', "How well your chart and your proposed partner/co-founder's chart work together for business — not a marriage-compatibility reading."))}</p>
  <div class="card">
    <p style="margin-top:0;">{_esc(_t(lang, 'your_match_word', 'Your match'))}: <strong style="color:var(--navy); font-size:16px;">{label}</strong> ({score:.0f}/100)</p>
    {d7_client_html}
  </div>
  <div class="grid-2">
    <div class="card">
      <h3 style="margin-top:0; color:var(--green);">{_esc(_t(lang, 'h3_complementary_strengths', 'Complementary strengths'))}</h3>
      <ul>{strengths_html}</ul>
    </div>
    <div class="card">
      <h3 style="margin-top:0; color:var(--red);">{_esc(_t(lang, 'h3_friction_points', 'Friction points'))}</h3>
      <ul>{frictions_html}</ul>
    </div>
  </div>
</section>"""


def _section_diversified_sectors_html(prediction: Dict[str, Any], lang: str = "en", audience: str = "astrologer") -> str:
    """Renders prediction['diversified_sectors'] (diversify_sector_ranking()
    output, business_determination/sectors.py) -- the diversity-clustered
    view that surfaces one representative sector per archetype_family
    before near-duplicate sectors of the same underlying planetary
    signature (e.g. consulting/finance/education, all Jupiter+Mercury
    scholarship_policy-driven) crowd the top of the list.

    This is ADDITIVE, not a replacement: the astrologer edition still
    renders the full flat-ranked leaderboard elsewhere (labeled "Full
    Ranked List (Technical)" in render_astrologer_report_html) so no
    information is lost for a technical reader. Degrades to an empty
    string if diversify_sector_ranking() was never wired in (e.g. an
    older cached prediction dict) rather than crashing on a missing key.
    """
    diversified = prediction.get("diversified_sectors") or {}
    top_rows = diversified.get("diversified_top_sectors") or []
    if not top_rows:
        return ""

    family_groups = {g["archetype_family"]: g for g in diversified.get("family_groups", [])}
    _max_score = max((row["score"] for row in top_rows), default=100.0) or 100.0

    rows_html = []
    for row in top_rows:
        rank = row.get("rank", "")
        tier_class = "tier-top" if isinstance(rank, int) and rank <= 3 else "tier-mid"
        bar_pct = round(100.0 * row["score"] / _max_score, 1)
        family = row.get("archetype_family")
        group = family_groups.get(family) if family else None
        similar_note_html = ""
        if group and group.get("hidden_count", 0) > 0:
            similar_note_html = (
                f'<li class="chip chip-band chip-band-NA">'
                f'{group["hidden_count"]} {_esc(_t(lang, "similar_sectors_word", "similar sector(s) not shown"))}'
                f'</li>'
            )
        match_confidence_raw = row.get("match_confidence", "")
        match_chip_html = ""
        if match_confidence_raw == "EXPLORATORY_SECTOR_MATCH":
            chip_label = (
                _t(lang, "exploratory_match_chip", "EXPLORATORY — no classical combo match")
                if audience == "astrologer"
                else _t(lang, "exploratory_match_chip_client", "BROAD MATCH — not a confirmed exact recommendation")
            )
            match_chip_html = f'<span class="chip chip-band chip-band-LOW">{_esc(chip_label)}</span>'
        rows_html.append(f"""
        <div class="sector-row {tier_class}">
          <div class="sector-rank">{rank}</div>
          <div class="sector-main">
            <div class="sector-label-line">
              <span class="sector-label">{_esc(_lt(lang, row['label']))}</span>
              <span class="sector-score">{_fmt_pct(row['score'])}</span>
            </div>
            <div class="sector-bar-track"><div class="sector-bar-fill" style="width:{bar_pct}%"></div></div>
            <ul class="item-grid">{similar_note_html}</ul>
          </div>
          <div class="sector-meta">
            {match_chip_html}
          </div>
        </div>""")

    intro = _t(
        lang,
        "diversified_sectors_intro",
        "One representative per distinct planetary/archetype signature shown first, so near-duplicate sectors "
        "driven by the same underlying combination don't crowd out genuinely different matches.",
    )
    return f"""
<div class="card">
  <p style="margin-top:0; color:var(--muted); font-size:13px;">{_esc(intro)}</p>
  <div class="sector-leaderboard">{"".join(rows_html)}</div>
</div>"""


def _cover_block(
    kicker: str, title: str, name: str, generated: str, rule_pack_version: str, lang: str = "en",
    verdict_label: Optional[str] = None,
    top_sector_label: Optional[str] = None,
    top_sector_score: Optional[float] = None,
) -> str:
    """"Professional printable report" pass: the print title page. Kept
    visually suppressed on screen (unchanged, see _shared_css()'s .cover
    rule) and re-enabled specifically for print output, where a title
    page is standard practice for a document this long. verdict_label /
    top_sector_* are optional citations of already-computed headline
    numbers (never re-derived here) shown as a small teaser strip, same
    "everything here is a citation of something explained in full further
    in the document" discipline as _section_at_a_glance_html."""
    teaser_items = []
    if verdict_label:
        teaser_items.append((
            _t(lang, 'cover_teaser_verdict', 'Verdict'), _esc(str(verdict_label)),
        ))
    if top_sector_label:
        score_suffix = f" ({_fmt_pct(top_sector_score)})" if top_sector_score is not None else ""
        teaser_items.append((
            _t(lang, 'cover_teaser_sector', 'Top-Fit Sector'), f"{_esc(str(top_sector_label))}{score_suffix}",
        ))
    teaser_html = ""
    if teaser_items:
        teaser_html = '<div class="cover-teaser">' + "".join(
            f'<div class="cover-teaser-item"><div class="cover-teaser-label">{_esc(label)}</div>'
            f'<div class="cover-teaser-value">{value}</div></div>'
            for label, value in teaser_items
        ) + '</div>'

    return f"""
<div class="cover">
  <div class="kicker">{_esc(kicker)}</div>
  <h1>{_esc(title)}</h1>
  <p class="cover-subtitle">{_esc(_t(lang, 'cover_subtitle', 'A classical Vedic-astrology reading of business viability, best-fit industry sectors, and favorable timing -- decision support for further reflection, not financial, legal, or investment advice.'))}</p>
  <hr class="cover-rule">
  <div class="cover-prepared-for">{_esc(_t(lang, 'cover_prepared_for', 'Prepared for'))}</div>
  <div class="subject-name">{_esc(name)}</div>
  {teaser_html}
  <div class="cover-meta">{_esc(_t(lang, 'generated_prefix', 'Generated'))} {_esc(generated)} &middot; {_esc(_t(lang, 'rule_pack_word', 'Rule pack'))} {_esc(rule_pack_version)}</div>
  <div class="cover-confidential">{_esc(_t(lang, 'cover_confidential', 'Personal & confidential -- prepared exclusively for the named recipient.'))}</div>
</div>"""


_TOC_ASTROLOGER_SECTIONS: List[Tuple[str, str, str]] = [
    ("at_a_glance", "nav_at_a_glance", "At a Glance"),
    ("recommendation", "h_recommendation", "Recommendation"),
    ("financial-readiness", "h_financial_readiness", "Financial Readiness Evidence"),
    ("transition-timing", "h_transition_timing", "Transition Timing"),
    ("promise-fields", "h_promise_fields", "Structural Promise Fields"),
    ("forecast-window", "h_forecast_window", "Forecast Window & Timing Status"),
    ("significators", "h_significators", "Business-Strength Significators"),
    ("sectors", "h_sectors_astro", "Business Sectors"),
    ("timed-windows", "h_windows_astro", "Timed Windows"),
    ("method-status", "h_method_status", "Method-level Status"),
    ("appendix", "h_technical_appendix", "Technical Appendix"),
]

_TOC_CLIENT_SECTIONS: List[Tuple[str, str, str]] = [
    ("at_a_glance", "nav_at_a_glance", "At a Glance"),
    ("recommendation", "h_in_summary", "In Summary"),
    ("financial-readiness", "h_financial_readiness", "Financial Readiness Evidence"),
    ("transition-timing", "h_transition_timing_client", "Should You Move Now, Or Wait?"),
    ("promise-fields", "h_your_scores", "Your Scores at a Glance"),
    ("sectors", "h_sectors_client", "Sectors That Fit You Best"),
    ("timed-windows", "h_windows_client", "Favorable Periods Ahead"),
    ("appendix", "h_technical_appendix", "Technical Appendix"),
]


def _toc_block(lang: str, audience: str = "astrologer") -> str:
    """Print-only table of contents page, listed right after the cover
    page. A fixed, hand-curated list of the report's top-level sections
    (not an auto-crawl of every <h2> in the document, which would also
    pick up every narrow Technical Appendix sub-check and produce an
    unreadably long contents page) -- mirrors the same Tier 1/2 vs.
    Appendix grouping the on-screen nav bar and Technical Appendix
    divider already use, with an inline label distinguishing the two
    groups. Page numbers are deliberately NOT included: CSS
    target-counter() page-number support is inconsistent across the
    browsers/engines a reader might use for Print-to-PDF, and a wrong
    page number would be worse than none -- this instead gives a reading
    map in document order, which every renderer can produce reliably."""
    rows = _TOC_ASTROLOGER_SECTIONS if audience == "astrologer" else _TOC_CLIENT_SECTIONS
    items = []
    for anchor, key, default in rows:
        label = _esc(_t(lang, key, default))
        part_label = (
            _esc(_t(lang, 'toc_part_appendix', 'Appendix'))
            if anchor == "appendix" else ""
        )
        part_label_html = f'<span class="toc-part-label">{part_label}</span>' if part_label else ""
        items.append(f'<li>{label}{part_label_html}</li>')
    return f"""
<div class="toc-page">
  <h2>{_esc(_t(lang, 'toc_title', 'Contents'))}</h2>
  <p class="toc-sub">{_esc(_t(lang, 'toc_sub', 'Listed in the order they appear in this document.'))}</p>
  <ol>{"".join(items)}</ol>
</div>"""


def _section_financial_readiness_html(prediction: Dict[str, Any], lang: str = "en") -> str:
    """Render the external-evidence gate separately from astrological support."""
    authoritative = prediction.get("authoritative_recommendation", {}) or {}
    evidence = authoritative.get("financial_readiness", {}) or {}
    certified = bool(authoritative.get("capital_readiness_certified"))
    status = evidence.get("status", "MISSING_EXTERNAL_FINANCIAL_EVIDENCE")
    failed = evidence.get("failed_checks", []) or []
    missing = evidence.get("missing_fields", []) or []
    _none_recorded = _esc(_t(lang, 'none_recorded', 'None recorded'))
    failed_html = ", ".join(_esc(str(item)) for item in failed) or _none_recorded
    missing_html = ", ".join(_esc(str(item)) for item in missing) or _none_recorded
    return f"""
<section id="financial-readiness">
  <h2>{_esc(_t(lang, 'h_financial_readiness', 'Financial Readiness Evidence'))}</h2>
  <div class="card">
    <p><strong>{_esc(_t(lang, 'certification_status', 'Certification status'))}:</strong>
      {_esc('CERTIFIED' if certified else 'NOT CERTIFIED')} &middot; {_esc(str(status))}</p>
    <p><strong>{_esc(_t(lang, 'capital_astrology_status', 'Astrological capital status'))}:</strong>
      {_esc(str(authoritative.get('capital_readiness_status', 'NOT_SUPPORTED')))}</p>
    <p><strong>{_esc(_t(lang, 'failed_checks', 'Failed checks'))}:</strong> {failed_html}</p>
    <p><strong>{_esc(_t(lang, 'missing_evidence_fields', 'Missing evidence fields'))}:</strong> {missing_html}</p>
    <p style="margin-bottom:0;">{_esc(str(evidence.get('note', 'External financial, market, legal and accounting review remains required.')))}</p>
  </div>
</section>"""


def render_astrologer_report_html(
    name: str,
    prediction: Dict[str, Any],
    dual_narrative: Optional[Dict[str, Any]] = None,
    lang: Optional[str] = None,
    payload: Optional[Any] = None,
    muhurta_result: Optional[Dict[str, Any]] = None,
    muhurta_event_type: str = "BUSINESS_LAUNCH",
) -> str:
    """Full technical report for the practicing astrologer: every
    deterministic section (mode gate, promise-field layer weights,
    operating-model comparisons, contradiction-control findings,
    significator evidence ledger, method-level status) plus the
    astrologer-facing narrative -- nothing hidden, nothing simplified.
    Printable to PDF via the browser's own Print dialog (@page rules and
    break-inside:avoid are in _shared_css()).

    lang: 'ta' / 'te' / 'en' (default: resolved from the .env
    Report_Language_Enabled_Tamil / _Telugu flags via
    _resolve_report_language()). Translates the static UI chrome via _t()/
    _lt() AND the engine's dynamic evidence prose (signals, contradiction
    findings, window evidence, method-status detail, the recommendation
    reasoning sentence, maturity statement/caveats) via a batched LLM
    translation pass in _prepare_common_sections() -- the whole report
    body, not just its headings, renders in the target language. If that
    translation pass could not run (no consent/API key/connectivity), a
    visible on-page notice says so rather than silently leaving English
    text mixed into a Tamil/Telugu report.
    """
    lang = lang or _resolve_report_language()
    s = _prepare_common_sections(name, prediction, lang=lang, payload=payload)
    rec = s["rec"]

    # Wired-by-default muhurta section (previously required a caller to
    # invoke find_business_muhurta() separately and stitch the HTML in
    # themselves -- both editions now always attempt this so a generated
    # report actually shows real electional-timing content, not just the
    # scaffolding for it).
    _muhurta_was_auto_defaulted = muhurta_result is None
    if muhurta_result is None:
        muhurta_result = _default_business_muhurta_result(payload, event_type=muhurta_event_type)
    muhurta_section_html = _section_muhurta_recommendations_html(muhurta_result, lang=lang, audience="astrologer")
    if _muhurta_was_auto_defaulted and prediction.get("muhurta_check") is None:
        muhurta_section_html = _prefix_not_evaluated_disclosure(
            muhurta_section_html,
            _t(lang, 'p_muhurta_auto_default_disclosure',
               "Not evaluated as part of the scored prediction above -- the underlying "
               "compute_business_prediction() result has muhurta_check = null (no candidate "
               "date/period was supplied to the scoring pipeline). The section below is a "
               "supplementary, separately-run scan defaulted to today through the maximum "
               "scan window, shown for convenience only; it is not part of the weighted "
               "business/job scoring above and did not influence it."),
        )

    # Content-restructuring audit fix (item 7b): "Strongest Years
    # (Ashtakavarga)" was fully built/styled/translated but never actually
    # invoked by either report renderer -- same auto-default treatment as
    # muhurta above so it now reaches the real report instead of being
    # dead, unreachable content.
    ashtakavarga_result = _default_ashtakavarga_years_result(payload, timed_windows=prediction.get("timed_windows"))
    ashtakavarga_section_html = _section_ashtakavarga_years_html(ashtakavarga_result, lang=lang, audience="astrologer")
    if ashtakavarga_section_html:
        ashtakavarga_section_html = _prefix_not_evaluated_disclosure(
            ashtakavarga_section_html,
            _t(lang, 'p_ashtakavarga_auto_default_disclosure',
               "Supplementary, separately-run year-range scan (this year through +5 years), shown "
               "for convenience only -- it is not part of the weighted business/job scoring above "
               "and did not influence it. Cross-check against the Timed Windows and Transition "
               "Timing sections before treating any single year as decisive."),
        )

    astro_paras = ""
    narrative_section = ""
    if dual_narrative:
        astro_paras = "".join(f"<p>{_esc(p)}</p>" for p in dual_narrative.get("astrologer_narrative_paragraphs", []))
        narrative_disclaimer = _esc(dual_narrative.get("disclaimer", _NARRATIVE_DISCLAIMER))
        narrative_section = f"""
<section id="narrative">
  <h2>{_esc(_t(lang, 'h_narrative_astro', 'Astrological Reading — Technical Notes'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_narrative_astro', 'A long-form narrative generated strictly from the deterministic evidence in this report (house/lord evidence, promise scores, sector ranking, contradiction findings, timed windows) — the model is phrasing existing evidence, not introducing new astrological claims of its own.'))}</p>
  <div class="card narrative-panel narrative-panel-astrologer">
    {astro_paras}
  </div>
  <p class="narrative-disclaimer">{narrative_disclaimer}</p>
</section>"""

    _authoritative_for_rec = s.get("authoritative_recommendation", {}) or {}
    _recommendation_basis_text = _t(
        lang, "p_recommendation_basis",
        "Verdict: {verdict} (action level: {action_level}) -- based on business_promise ({business_promise}) vs "
        "job_promise ({job_promise}), the declared-layer-weight system, contradiction-penalized. This is the "
        "authoritative basis for this report's recommendation.",
    ).format(
        verdict=_lt(lang, str(_authoritative_for_rec.get("verdict", "—"))),
        action_level=_lt(lang, str(_authoritative_for_rec.get("action_level", "—"))),
        business_promise=_fmt_pct(_authoritative_for_rec.get("business_promise")),
        job_promise=_fmt_pct(_authoritative_for_rec.get("job_promise")),
    )

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(_t(lang, 'astrologer_title', 'Business Prediction Analysis'))} (Astrologer Edition) — {_esc(name)}</title>
<style>{_shared_css()}</style>
</head>
<body>

{_cover_block(_t(lang, 'astrologer_kicker', 'JyotishAI · Astrologer Edition'), _t(lang, 'astrologer_title', 'Business Prediction Analysis'), name, s['generated'], prediction.get('rule_pack_version', '—'), lang=lang, verdict_label=s.get('verdict_display'), top_sector_label=(prediction.get('top_sectors') or [{}])[0].get('label'), top_sector_score=(prediction.get('top_sectors') or [{}])[0].get('score'))}
{_toc_block(lang, audience="astrologer")}

<header class="hero">
  <div class="hero-inner">
    <div>
      <div class="kicker">{_esc(_t(lang, 'astrologer_kicker', 'Astrologer Edition — Full Technical Report'))}</div>
      <h1>{_esc(_t(lang, 'astrologer_title', 'Business Prediction Analysis'))}</h1>
      <div class="subject">{_esc(name)}</div>
      <div class="meta">{_esc(_t(lang, 'generated_prefix', 'Generated'))} {s['generated']} &middot; {_esc(_t(lang, 'rule_pack_word', 'Rule pack'))} {_esc(prediction.get('rule_pack_version', '—'))}</div>
    </div>
    <div class="hero-recommend">
      {s['section_final_verdict']}
      <div class="venture">{_esc(_lt(lang, 'Venture type:'))} {_esc(rec.get('venture_type', ''))} &middot; {_esc(_lt(lang, 'Heuristic tier:'))} <span class="badge {s['tier']}">{_esc(_lt(lang, s['tier']))}</span></div>
    </div>
  </div>
</header>

<nav class="tabs">
  <div class="tabs-inner">
    <a href="#at-a-glance">{_esc(_t(lang, 'nav_at_a_glance', 'At a Glance'))}</a>
    {f'<a href="#narrative">{_esc(_t(lang, "nav_reading_astrologer", "Astrological Reading"))}</a>' if dual_narrative else ''}
    <a href="#recommendation">{_esc(_t(lang, 'nav_summary', 'Recommendation'))}</a>
    <a href="#promise-fields">{_esc(_t(lang, 'nav_promise_fields_astro', 'Promise Fields'))}</a>
    <a href="#forecast-window">{_esc(_t(lang, 'nav_forecast_window', 'Forecast Window'))}</a>
    <a href="#significators">{_esc(_t(lang, 'nav_significators', 'Significators'))}</a>
    <a href="#sectors">{_esc(_t(lang, 'nav_sectors_astro', 'Sectors'))}</a>
    <a href="#timed-windows">{_esc(_t(lang, 'nav_windows_astro', 'Timed Windows'))}</a>
    <a href="#method-status">{_esc(_t(lang, 'nav_method_status', 'Method Status'))}</a>
    <a href="#appendix" style="border-left:1px solid var(--line); margin-left:4px; padding-left:12px;">{_esc(_t(lang, 'nav_appendix', 'Technical Appendix'))}</a>
  </div>
</nav>

<div class="pre-wrap">
{_glossary_section_html(lang)}
</div>
{_print_toolbar_html(lang)}

<div class="wrap">

{_section_at_a_glance_html(prediction, s, lang=lang, audience="astrologer")}

{s.get('section_verdict_reconciliation', '')}

{s['disclaimer_html']}

{narrative_section}

<section id="recommendation">
  <h2>{_esc(_t(lang, 'h_recommendation', 'Recommendation'))}</h2>
  <div class="card">
    <p style="font-size:15px; color:var(--ink); margin-top:0;">{_esc(_recommendation_basis_text)}</p>
    <p style="margin-bottom:0;">{_esc(_lt(lang, 'Actionable business advantage over employment'))}: <strong>{_esc(_fmt_yes_no(lang, rec.get('comparative_advantage')))}</strong>
    &nbsp;&middot;&nbsp; {_esc(_lt(lang, 'Hybrid suggested'))}: <strong>{_esc(_fmt_yes_no(lang, rec.get('hybrid_suggested')))}</strong></p>
  </div>
</section>

{_section_financial_readiness_html(prediction, lang=lang)}

{_section_transition_timing_html(prediction, lang=lang, audience="astrologer")}

<section id="promise-fields">
  <h2>{_esc(_t(lang, 'h_promise_fields', 'Structural Promise Fields'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_promise_fields', "Nine separately-computed fields, not a single collapsed business-vs-job comparison — an independent-enterprise promise, a comparative business-vs-job promise, field/operating-model fit, and a method-agreement-based confidence label, per the engine's v17 audit-fix framework."))}</p>
  {s['section_kpi_grid']}

  <div class="card" style="margin-top:22px;">
    <h3 style="margin-top:0;">{_esc(_t(lang, 'h3_full_field_detail', 'Full field detail'))}</h3>
    {s['section_named_fields']}
  </div>

  <div class="card" style="margin-top:14px;">
    <h3 style="margin-top:0;">{_esc(_t(lang, 'h3_capital_strategy', 'Capital Strategy: Bootstrap vs External Capital'))}</h3>
    {s['section_capital_strategy_astrologer']}
  </div>

  <div class="grid-2">
    <div class="card">
      <h3 style="margin-top:0;">{_esc(_t(lang, 'h3_biz_layers', 'Business promise — declared layer weights (sum to 100%)'))}</h3>
      {s['section_biz_layers']}
    </div>
    <div class="card">
      <h3 style="margin-top:0;">{_esc(_t(lang, 'h3_job_layers', 'Job promise — declared layer weights (sum to 100%)'))}</h3>
      {s['section_job_layers']}
    </div>
  </div>

  <p style="margin-top:22px; margin-bottom:-8px;">{_esc(_t(lang, 'p_operating_model_framing', "This ranks HOW you are best structured to run a business (sole owner, partnership, family-run, scalable platform, etc.) -- a different question from the Business Sectors list below, which ranks WHICH industry fits your chart. The D1 and D10 tables are two lenses on that same structural question; D10-compatible sectors get a small ranking bonus in the Business Sectors section, flagged inline there."))}</p>
  <div class="grid-2">
    <div class="card">
      <h3 style="margin-top:0;">{_esc(_t(lang, 'h3_op_model_d1', 'Operating-model fit (D1)'))}</h3>
      {s['section_operating_model']}
    </div>
    <div class="card">
      <h3 style="margin-top:0;">{_esc(_t(lang, 'h3_op_model_d10', 'Operating-model fit — D10-native mirror'))}</h3>
      {s['section_operating_model_d10']}
      {s['section_operating_model_synthesis']}
    </div>
  </div>

  {_section_d10_rectification_html(prediction, lang=lang, audience="astrologer")}

  <div class="card" style="margin-top:22px;">
    <h3 style="margin-top:0;">{_esc(_t(lang, 'h3_contradiction', 'Contradiction-control findings'))}</h3>
    <p style="margin-top:-4px;">{_esc(_t(lang, 'p_contradiction', "Explicit penalties applied when a rule's raw positive credit is undercut by a classical caveat (e.g. a strong 7th house with no 2nd/10th/11th connection reads as client-facing employment, not ownership) — already netted into the fields above, shown here for transparency."))}</p>
    {s['section_contradictions']}
  </div>
</section>

<section id="forecast-window">
  <h2>{_esc(_t(lang, 'h_forecast_window', 'Forecast Window & Timing Status'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_forecast_window', 'The date range and dasha-calendar computation status behind the Timed Windows and Transition Timing sections below.'))}</p>
  <div class="card">
    <p>{_esc(_t(lang, 'as_of_word', 'As of'))} {_esc(s['forecast_window'].get('as_of', '—'))}, {_esc(s['forecast_window'].get('years_ahead', '—'))} {_esc(_t(lang, 'years_ahead_word', 'years ahead'))}.</p>
    {s['timing_status_html']}
  </div>
</section>

<section id="significators">
  <h2>{_esc(_t(lang, 'h_significators', 'Business-Strength Significators'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_significators', 'House/planet lordship, D9/D10 dignity, D10-native house graph, Phaladeepika multi-lagna, Jaimini rasi drishti/argala — see EVIDENCE_BASIS in the underlying JSON for the full list.'))}</p>
  <div class="card">
    <p style="margin-top:0;">{_esc(_t(lang, 'overall_strength_word', 'Overall strength'))}: <strong style="color:var(--navy); font-size:16px;">{_fmt_pct(s['sig']['strength_0_100'])}</strong>
    ({_esc(_t(lang, 'heuristic_scale_note', 'heuristic relative scale, not a probability'))}) &mdash; {_esc(_t(lang, 'positive_total_word', 'positive total'))}: {s['sig']['positive_total']:.1f},
    {_esc(_t(lang, 'negative_total_word', 'negative total'))}: {s['sig']['negative_total']:.1f}, {_esc(_t(lang, 'net_word', 'net'))}: {s['sig']['net_score']:.1f}</p>
  </div>
  <div class="grid-2">
    <div class="card">
      <h3 style="margin-top:0; color:var(--green);">{_esc(_t(lang, 'h3_positive_signals', 'Positive signals'))}</h3>
      {s['section_signals']}
    </div>
    <div class="card">
      <h3 style="margin-top:0; color:var(--red);">{_esc(_t(lang, 'h3_risk_signals', 'Risk signals'))}</h3>
      {s['section_risk_signals']}
    </div>
  </div>
</section>

<section id="sectors">
  <h2>{_esc(_t(lang, 'h_sectors_astro', 'Business Sectors'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_sectors_framing', "This ranks WHICH industries best fit your chart -- a different question from the Operating-Model tables above, which rank HOW you are best structured to run whichever business you choose."))}</p>
  <p style="margin-top:-8px; font-size:12px; color:var(--muted, #666);">{_esc(_t(lang, 'p_sectors_viability_caveat',
      "Issue 16 note: sector-fit/field-fit percentages below measure THEMATIC ASTROLOGICAL AFFINITY (which "
      "industries this chart's planetary significators resonate with) -- they are NOT a measure of operating "
      "feasibility, profit retention, or survival odds in that sector. Compare this fit score against this chart's "
      "own business_execution_capacity, business_profitability, and business_stability figures elsewhere in this "
      "report before reading a high sector-fit number as 'this is a viable business' -- a sector can be a strong "
      "thematic match while execution/profitability/stability for actually running any business remain weak."))}</p>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'h_sectors_diversified_sub', 'Diversified view -- one representative per distinct planetary signature.'))}</p>
  {_section_diversified_sectors_html(prediction, lang=lang, audience="astrologer")}
  <h3 style="margin-top:22px;">{_esc(_t(lang, 'h_sectors_full_ranked', 'Full Ranked List (Technical)'))} &mdash; {_esc(_t(lang, 'all_ranked_word', 'All'))} {len(prediction['top_sectors'])} {_esc(_t(lang, 'ranked_word', 'Ranked'))}</h3>
  <div class="card">{s['section_sectors']}</div>
</section>

<section id="timed-windows">
  <h2>{_esc(_t(lang, 'h_windows_astro', 'Timed Windows'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_timed_windows', 'Dasha/antardasha calendar bounded to the forecast window above. Each window shows a single net-scored label produced by tiered precedence arbitration (D1 → D9/D10 confirm/deny → KP final arbiter → Jaimini activation → transit/Shadbala trigger) — expand a window for its full evidence ledger and arbitration trail.'))}</p>
  <div class="windows-grid">{s['section_windows']}</div>
</section>

<section id="method-status">
  <h2>{_esc(_t(lang, 'h_method_status', 'Method-level status'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_method_status', 'What actually ran for this chart, vs what was missing data or unavailable — distinct from "timing computation status" above, which only reflects whether the dasha calendar itself computed.'))}</p>
  <div class="card">{s['section_method_status']}</div>
</section>

{_technical_appendix_divider_html(lang)}
<div class="technical-appendix">

{muhurta_section_html}

{ashtakavarga_section_html}

{_section_detected_yogas_html(prediction, lang=lang, audience="astrologer")}
{_section_legal_dispute_risk_html(prediction, lang=lang, audience="astrologer")}
{_section_d2_hora_evidence_html(prediction, lang=lang, audience="astrologer")}
<p class="paired-section-link">{_esc(_t(lang, 'p_d2_hora_deep_continues', '↳ Continues the D2-Hora wealth-flow analysis above with a fuller structural read.'))}</p>
{_section_d2_hora_deep_evidence_html(prediction, lang=lang, audience="astrologer")}
{_section_mercury_adjudication_html(prediction, lang=lang, audience="astrologer")}
{_section_lagnesh_neecha_bhanga_html(prediction, lang=lang, audience="astrologer")}
{_section_janma_nakshatra_evidence_html(prediction, lang=lang, audience="astrologer")}
<p class="paired-section-link">{_esc(_t(lang, 'p_nakshatra_chain_continues', '↳ Continues the birth-star analysis above with the fuller nakshatra-lord vocational chain.'))}</p>
{_section_janma_nakshatra_chain_html(prediction, lang=lang, audience="astrologer")}
{_section_foreign_business_evidence_html(prediction, lang=lang, audience="astrologer")}

{_section_partnership_synastry_html(prediction, lang=lang, audience="astrologer")}

</div>

<footer>
{_esc(_t(lang, 'footer_astro', 'JyotishAI Business Prediction Analysis (Astrologer Edition)'))} — {_esc(_lt(lang, s['model_status']))}. {_esc(_lt(lang, s['calibration_status']))}.
{_esc(_t(lang, 'footer_astro_tail', 'Experimental Jyotish heuristics; not calibrated financial, legal, or investment advice.'))}
</footer>

</div>
</body>
</html>"""


def render_client_report_html(
    name: str,
    prediction: Dict[str, Any],
    dual_narrative: Optional[Dict[str, Any]] = None,
    lang: Optional[str] = None,
    payload: Optional[Any] = None,
    muhurta_result: Optional[Dict[str, Any]] = None,
    muhurta_event_type: str = "BUSINESS_LAUNCH",
) -> str:
    """Simplified, narrative-led report for the chart holder: leads with
    the plain-language reading, shows the same underlying KPI numbers and
    sector ranking as the astrologer edition (never different numbers),
    but omits the audit-internal sections (raw mode-gate table, layer-
    weight breakdowns, contradiction-control ledger, significator
    evidence list, method-level status) that only make sense to someone
    auditing the engine itself. Printable to PDF via the browser's own
    Print dialog.

    lang: 'ta' / 'te' / 'en' (default: resolved from .env flags). See
    render_astrologer_report_html's docstring for the same full-body
    translation scope (static chrome via _t()/_lt(), dynamic prose via
    the batched LLM pass in _prepare_common_sections()).
    """
    lang = lang or _resolve_report_language()
    s = _prepare_common_sections(name, prediction, lang=lang, payload=payload)
    rec = s["rec"]
    translation_incomplete = s.get("translation_incomplete", False)

    # Wired-by-default muhurta section -- see render_astrologer_report_html's
    # matching comment above for why this is now computed here rather than
    # requiring a separate manual find_business_muhurta() call/splice.
    _muhurta_was_auto_defaulted = muhurta_result is None
    if muhurta_result is None:
        muhurta_result = _default_business_muhurta_result(payload, event_type=muhurta_event_type)
    muhurta_section_html = _section_muhurta_recommendations_html(muhurta_result, lang=lang, audience="client")
    if _muhurta_was_auto_defaulted and prediction.get("muhurta_check") is None:
        muhurta_section_html = _prefix_not_evaluated_disclosure(
            muhurta_section_html,
            _t(lang, 'p_muhurta_auto_default_disclosure_client',
               "Note: this was not part of the main scored reading above -- no specific date "
               "range was requested, so we ran a separate default scan (today onward) just to "
               "show sample dates. It did not affect your business/job recommendation."),
        )

    # Content-restructuring audit fix (item 7b) -- see matching comment in
    # render_astrologer_report_html above.
    ashtakavarga_result = _default_ashtakavarga_years_result(payload, timed_windows=prediction.get("timed_windows"))
    ashtakavarga_section_html = _section_ashtakavarga_years_html(ashtakavarga_result, lang=lang, audience="client")
    if ashtakavarga_section_html:
        ashtakavarga_section_html = _prefix_not_evaluated_disclosure(
            ashtakavarga_section_html,
            _t(lang, 'p_ashtakavarga_auto_default_disclosure_client',
               "Note: this was not part of the main scored reading above -- a separate default "
               "scan (this year through +5 years). It did not affect your business/job "
               "recommendation; cross-check it against the Favorable Periods section above."),
        )

    client_paras = ""
    narrative_section = ""
    if dual_narrative:
        client_paras = "".join(f"<p>{_esc(p)}</p>" for p in dual_narrative.get("client_narrative_paragraphs", []))
        narrative_disclaimer = _esc(dual_narrative.get("disclaimer", _NARRATIVE_DISCLAIMER))
        narrative_section = f"""
<section id="narrative">
  <h2>{_esc(_t(lang, 'h_narrative_client', 'Your Astrological Reading'))}</h2>
  <div class="card narrative-panel narrative-panel-client">
    {client_paras}
  </div>
  <p class="narrative-disclaimer">{narrative_disclaimer}</p>
</section>"""

    # Simplified sector view: top 8 only, same underlying numbers as the
    # astrologer edition's leaderboard (no separate computation), just a
    # shorter list -- a chart holder does not need all 19 ranked sectors,
    # only the ones worth their attention.
    top_sectors_simple = prediction.get("top_sectors", [])[:8]
    _max_score = max((row["score"] for row in top_sectors_simple), default=100.0) or 100.0
    simple_sector_rows = []
    for row in top_sectors_simple:
        rank = row["rank"]
        tier_class = "tier-top" if rank <= 3 else "tier-mid"
        bar_pct = round(100.0 * row["score"] / _max_score, 1)
        timing_band_raw = row.get("sbc_timing_band", "—")
        timing_band = _esc(_lt(lang, timing_band_raw))
        # v37 audit fix: the astrologer edition already flagged sectors with
        # no classical exact-combination match as EXPLORATORY, but the
        # client edition silently dropped that badge -- a client reading
        # e.g. "Import/Export 85.2" with no qualifier could reasonably take
        # it as a confirmed recommendation rather than a broad aptitude
        # match. Same chip, plain-language client wording.
        client_match_chip_html = ""
        if row.get("match_confidence") == "EXPLORATORY_SECTOR_MATCH":
            client_match_chip_html = f'<span class="chip chip-band chip-band-LOW">{_esc(_t(lang, "exploratory_match_chip_client", "BROAD MATCH — not a confirmed exact recommendation"))}</span>'
        simple_sector_rows.append(f"""
        <div class="sector-row {tier_class}">
          <div class="sector-rank">{rank}</div>
          <div class="sector-main">
            <div class="sector-label-line">
              <span class="sector-label">{_esc(_lt(lang, row['label']))}</span>
              <span class="sector-score">{_fmt_pct(row['score'])}</span>
            </div>
            <div class="sector-bar-track"><div class="sector-bar-fill" style="width:{bar_pct}%"></div></div>
          </div>
          <div class="sector-meta">
            <span class="chip chip-band chip-band-{str(timing_band_raw).upper() if timing_band_raw != '—' else 'NA'}">{timing_band} {_esc(_t(lang, 'timing_word', 'timing'))}</span>
            {client_match_chip_html}
          </div>
        </div>""")
    section_sectors_simple = f'<div class="sector-leaderboard">{"".join(simple_sector_rows)}</div>'

    # Simplified timed windows: favorable/strong-favorable only, dates and
    # a plain label, no evidence ledger or arbitration trail (that detail
    # belongs in the astrologer edition, not here).
    favorable = [w for w in prediction.get("timed_windows", []) if str(w.get("label", "")).upper() in ("FAVORABLE", "STRONG_FAVORABLE")][:6]
    if favorable:
        # v40 audit fix (#26, user-caught): a window's FAVORABLE/
        # STRONG_FAVORABLE label comes from the shared dasha-timing net
        # score, which can be driven by H9 status/fortune/career-visibility
        # evidence just as easily as by genuinely business-discriminating
        # H1/H3/H7 evidence (e.g. the engine's own
        # business_relevance=SHARED_HOUSE_ONLY/NO_HOUSE_EVIDENCE
        # annotation, added in v34, already distinguishes these -- it just
        # wasn't consulted here). Listing every FAVORABLE window under
        # "Favorable Periods Ahead" implied every one of them specifically
        # supports a business launch/expansion, when several may only be
        # generally career-favorable. Windows are now split: genuinely
        # business-discriminating ones keep the FAVORABLE badge, others get
        # a distinct "general career favorable, not business-specific"
        # badge -- same underlying data, no relabeling of the engine's own
        # net_score-derived label, just an honest client-facing framing.
        def _pd_portion_hint(w: Dict[str, Any]) -> str:
            # Client-edition framing: "within this window, which portion is
            # more favorable" -- derived from the same pd_subwindows the
            # astrologer edition shows in full detail, just collapsed to a
            # single early/mid/late-portion sentence instead of per-PD-lord
            # citations. No new scoring -- same net_score/label per PD
            # sub-window, just a simpler presentation.
            pd_subs = w.get("pd_subwindows") or []
            if not pd_subs:
                return ""
            _order = {"STRONG_FAVORABLE": 4, "FAVORABLE": 3, "MIXED": 2, "CAUTION": 1, "HIGH_RISK": 0}
            best = max(pd_subs, key=lambda pd: _order.get(pd.get("label", ""), -1))
            n = len(pd_subs)
            best_idx = pd_subs.index(best)
            portion = (
                _t(lang, "portion_early", "early")
                if best_idx < n / 3 else
                _t(lang, "portion_late", "late")
                if best_idx >= 2 * n / 3 else
                _t(lang, "portion_mid", "middle")
            )
            if best.get("label") in ("STRONG_FAVORABLE", "FAVORABLE"):
                return (
                    f'<p class="pd-hint">{_esc(_t(lang, "pd_hint_favorable", "Within this window, the {portion} portion looks strongest.").format(portion=portion))}</p>'
                )
            return ""

        window_items = "".join(f"""
        <div class="window-block">
          <h3>{_esc(w['start_date'])} &rarr; {_esc(w['end_date'])}
            {f'<span class="badge {_esc(w["label"])}">{_esc(_lt(lang, w["label"]))}</span>' if w.get('business_relevance') == 'BUSINESS_DISCRIMINATING' else f'<span class="badge MIXED">{_esc(_t(lang, "general_career_favorable_badge", "GENERALLY FAVORABLE (not business-specific)"))}</span>'}
          </h3>
          {_pd_portion_hint(w)}
        </div>""" for w in favorable)
        section_windows_simple = f'<div class="windows-grid">{window_items}</div>'
    else:
        section_windows_simple = f"<p><em>{_esc(_t(lang, 'no_favorable_windows', 'No clearly favorable windows identified in the current forecast horizon — timing is more mixed than decisive right now.'))}</em></p>"

    # Simplified KPI grid: same 8 core scores as the astrologer edition,
    # plain-language hints only, no raw method_agreement/score_0_1 jargon.
    def _score_tier_class(value: Any) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "kpi-neutral"
        if v >= 70:
            return "kpi-strong"
        if v >= 50:
            return "kpi-moderate"
        return "kpi-weak"

    confidence = prediction.get("business_over_job_confidence", {}) or {}
    _kpi_defs = [
        ("Business Promise", prediction.get("business_promise"), "Strength of an independent-enterprise path for you"),
        ("Job Promise", prediction.get("job_promise"), "Strength of a salaried-employment path for you"),
        ("Independent-Profession Promise", prediction.get("independent_profession_promise"), "Solo practice or consulting, without running a full business"),
        ("Business Sector Fit", prediction.get("business_field_fit"), "How well your top sector matches your chart"),
        ("Execution Capacity", prediction.get("business_execution_capacity"), "Your day-to-day ability to run it"),
        ("Profitability", prediction.get("business_profitability"), "Support for turning activity into real profit"),
        ("Stability", prediction.get("business_stability"), "How sustainable this path looks over time"),
        ("Timing Readiness", prediction.get("current_timing_readiness"), "Whether right now is a supported time to act"),
    ]
    kpi_cards_html = "".join(
        f"""<div class="kpi-card {_score_tier_class(v)}">
          <div class="kpi-label">{_esc(_lt(lang, label))}</div>
          <div class="kpi-value">{_fmt_pct(v) if isinstance(v, (int, float)) else _esc(v if v is not None else "—")}</div>
          {_kpi_bar_html(v)}
          <div class="kpi-hint">{_esc(_lt(lang, hint))}</div>
        </div>"""
        for label, v, hint in _kpi_defs
    )
    section_kpi_grid_simple = f'<div class="kpi-grid">{kpi_cards_html}</div>'

    _capital_strategy_client_html = s.get("section_capital_strategy_client", "")
    section_capital_strategy_card = (
        f'<div class="card" style="margin-top:14px;"><h3 style="margin-top:0;">'
        f'{_esc(_t(lang, "h3_capital_strategy", "Capital Strategy: Bootstrap vs External Capital"))}</h3>'
        f'{_capital_strategy_client_html}</div>'
    ) if _capital_strategy_client_html else ""

    _margin_label = _lt(lang, prediction.get('business_advantage_label', 'UNKNOWN')) if lang != "en" else prediction.get('business_advantage_label', 'UNKNOWN').replace('_', ' ').title()

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(_t(lang, 'client_title', 'Your Business Astrology Report'))} — {_esc(name)}</title>
<style>{_shared_css()}</style>
</head>
<body>

{_cover_block(_t(lang, 'client_kicker', 'JyotishAI · Personal Edition'), _t(lang, 'client_title', 'Your Business Astrology Report'), name, s['generated'], prediction.get('rule_pack_version', '—'), lang=lang, verdict_label=s.get('verdict_display'), top_sector_label=(prediction.get('top_sectors') or [{}])[0].get('label'), top_sector_score=(prediction.get('top_sectors') or [{}])[0].get('score'))}
{_toc_block(lang, audience="client")}

<header class="hero">
  <div class="hero-inner">
    <div>
      <div class="kicker">{_esc(_t(lang, 'client_kicker', 'Prepared For You'))}</div>
      <h1>{_esc(_t(lang, 'client_title', 'Your Business Astrology Report'))}</h1>
      <div class="subject">{_esc(name)}</div>
      <div class="meta">{_esc(_t(lang, 'generated_prefix', 'Generated'))} {s['generated']}</div>
    </div>
    <div class="hero-recommend">
      {s['section_final_verdict']}
      <div class="venture">{_esc(_margin_label)}</div>
    </div>
  </div>
</header>

<nav class="tabs">
  <div class="tabs-inner">
    <a href="#at-a-glance">{_esc(_t(lang, 'nav_at_a_glance', 'At a Glance'))}</a>
    {f'<a href="#narrative">{_esc(_t(lang, "nav_narrative", "Your Reading"))}</a>' if dual_narrative else ''}
    <a href="#recommendation">{_esc(_t(lang, 'nav_summary', 'Summary'))}</a>
    <a href="#promise-fields">{_esc(_t(lang, 'nav_promise_fields_client', 'Your Scores'))}</a>
    <a href="#sectors">{_esc(_t(lang, 'nav_sectors_client', 'Best-Fit Sectors'))}</a>
    <a href="#timed-windows">{_esc(_t(lang, 'nav_windows_client', 'Favorable Periods'))}</a>
    <a href="#appendix" style="border-left:1px solid var(--line); margin-left:4px; padding-left:12px;">{_esc(_t(lang, 'nav_appendix', 'Technical Appendix'))}</a>
  </div>
</nav>

<div class="pre-wrap">
{_glossary_section_html(lang)}
</div>
{_print_toolbar_html(lang)}

<div class="wrap">

{_section_at_a_glance_html(prediction, s, lang=lang, audience="client")}

{s['disclaimer_html']}

{narrative_section}

<section id="recommendation">
  <h2>{_esc(_t(lang, 'h_in_summary', 'In Summary'))}</h2>
  <div class="card">
    {s['section_client_summary']}
  </div>
</section>

{_section_financial_readiness_html(prediction, lang=lang)}

{_section_transition_timing_html(prediction, lang=lang, audience="client")}

<section id="promise-fields">
  <h2>{_esc(_t(lang, 'h_your_scores', 'Your Scores at a Glance'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_your_scores', 'Eight separate readings of your chart — not one single business-vs-job verdict, but a fuller picture of where your strengths and readiness actually lie.'))}</p>
  {section_kpi_grid_simple}
  {section_capital_strategy_card}
</section>

{s.get('section_verdict_reconciliation', '')}

<section id="sectors">
  <h2>{_esc(_t(lang, 'h_sectors_client', 'Sectors That Fit You Best'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_sectors_framing_client', "This section is about WHICH industry suits you -- a separate question from HOW you'd run it, which is covered by your scores above."))}</p>
  <p style="margin-top:-8px; font-size:12px; color:var(--muted, #666);">{_esc(_t(lang, 'p_sectors_viability_caveat_client',
      "Important: this fit score measures how well an industry MATCHES your chart's natural strengths and interests "
      "-- it does not measure whether a business in that industry would actually run smoothly, stay profitable, or "
      "survive long-term. Check the Execution, Profitability, and Stability scores above alongside this fit score "
      "before treating a high match as a green light to start."))}</p>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_sectors_explainer_client', "This ranks industries by matching classical planetary significators in your chart (e.g. Mercury for trade, Mars for engineering, Venus for arts and luxury) against each field's traditional associations."))}</p>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'best_matching_word_diversified', "Your best-matching business sectors, one per distinct planetary signature so similar-sounding options don't repeat."))}</p>
  {_section_diversified_sectors_html(prediction, lang=lang, audience="client") or f'<div class="card">{section_sectors_simple}</div>'}
</section>

<section id="timed-windows">
  <h2>{_esc(_t(lang, 'h_windows_client', 'Favorable Periods Ahead'))}</h2>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_favorable_periods', 'Time windows in your dasha (planetary period) calendar that most support business or entrepreneurial action, based on the same forecast horizon used above.'))}</p>
  <p style="margin-top:-8px;">{_esc(_t(lang, 'p_windows_explainer_client', 'Vedic astrology tracks favorable and unfavorable periods using planetary cycles called dashas -- this section shows what your current and upcoming cycles suggest for business timing.'))}</p>
  <p style="margin-top:-8px; font-size:12px; color:var(--muted, #666);">{_esc(_t(lang, 'p_windows_precision_caveat',
      "Issue 13 precision note: these are BROAD Mahadasha/Antardasha-level windows suitable for exploratory, "
      "reversible action (a pilot, a first client, a side practice) -- NOT specific dates or a promise that any "
      "single day within a window is favorable. The underlying transit projection uses a mean-motion approximation "
      "(no station/retrograde precision, no exact ingress or real longitude-based aspect contacts), and finer-grain "
      "checks -- muhurta (specific-date electional astrology) and annual/varshaphal Ashtakavarga -- are NOT evaluated "
      "here. Narrow any window to an actual date only with a dedicated muhurta check before committing to it."))}</p>
  {section_windows_simple}
</section>

{_technical_appendix_divider_html(lang)}
<div class="technical-appendix">

{muhurta_section_html}

{ashtakavarga_section_html}

{_section_detected_yogas_html(prediction, lang=lang, audience="client")}
{_section_legal_dispute_risk_html(prediction, lang=lang, audience="client")}
{_section_d2_hora_evidence_html(prediction, lang=lang, audience="client")}
<p class="paired-section-link">{_esc(_t(lang, 'p_d2_hora_deep_continues', '↳ Continues the D2-Hora wealth-flow analysis above with a fuller structural read.'))}</p>
{_section_d2_hora_deep_evidence_html(prediction, lang=lang, audience="client")}
{_section_mercury_adjudication_html(prediction, lang=lang, audience="client")}
{_section_lagnesh_neecha_bhanga_html(prediction, lang=lang, audience="client")}
{_section_janma_nakshatra_evidence_html(prediction, lang=lang, audience="client")}
<p class="paired-section-link">{_esc(_t(lang, 'p_nakshatra_chain_continues', '↳ Continues the birth-star analysis above with the fuller nakshatra-lord vocational chain.'))}</p>
{_section_janma_nakshatra_chain_html(prediction, lang=lang, audience="client")}
{_section_d10_rectification_html(prediction, lang=lang, audience="client")}
{_section_foreign_business_evidence_html(prediction, lang=lang, audience="client")}

{_section_partnership_synastry_html(prediction, lang=lang, audience="client")}

</div>

<footer>
{_esc(_t(lang, 'footer_client', 'JyotishAI · Your Business Astrology Report. Traditional Jyotish heuristics; a decision-support reading for further reflection, not financial, legal, or medical advice.'))}
</footer>

</div>
</body>
</html>"""


_ID_ATTR_RE = re.compile(r'id="([a-zA-Z0-9_-]+)"')
_HREF_ANCHOR_RE = re.compile(r'href="#([a-zA-Z0-9_-]+)"')


def _prefix_fragment_ids(html_fragment: str, prefix: str) -> str:
    """Rewrites every id="..." and href="#..." in an extracted HTML
    fragment to carry `prefix`, so two fragments that each independently
    use the same section ids (both editions have a "recommendation",
    "sectors", "timed-windows", etc.) can be hosted in the same DOM
    without id collisions or broken in-page anchor links."""
    html_fragment = _ID_ATTR_RE.sub(lambda m: f'id="{prefix}{m.group(1)}"', html_fragment)
    html_fragment = _HREF_ANCHOR_RE.sub(lambda m: f'href="#{prefix}{m.group(1)}"', html_fragment)
    return html_fragment


def _extract_between(html: str, start_marker: str, end_marker: str) -> str:
    start = html.index(start_marker) + len(start_marker)
    end = html.rindex(end_marker)
    return html[start:end]


def render_combined_report_html(
    name: str,
    prediction: Dict[str, Any],
    dual_narrative: Optional[Dict[str, Any]] = None,
    lang: Optional[str] = None,
    payload: Optional[Any] = None,
    muhurta_result: Optional[Dict[str, Any]] = None,
    muhurta_event_type: str = "BUSINESS_LAUNCH",
) -> str:
    """Single-page report replacing the previous two-file (astrologer +
    client) output: one shared hero identifies the subject by name, and a
    "Chart Profile" / "Astrologer View" switch toggles between the
    client-facing and astrologer-facing content in place, on the same
    page.

    Deliberately reuses render_astrologer_report_html() and
    render_client_report_html() verbatim rather than re-implementing their
    section-building logic a third time -- this guarantees the combined
    report can never show different numbers/evidence/narrative than the
    two individual renderers would have, and stays in sync automatically
    as those functions evolve. It extracts each renderer's own
    <div class="wrap"> body and <nav class="tabs"> bar, ID-prefixes them
    (p- for the client/profile edition, a- for the astrologer edition) so
    the two editions' overlapping section ids don't collide once both are
    present in one DOM, and re-hosts them as two toggled `.view` panels
    under one shared hero/disclaimer/footer. Both panels remain in the
    document (not re-rendered on toggle), so in-page anchor links, browser
    Ctrl/Cmd+F, and Print-to-PDF (which prints both panels in full, see
    _shared_css()'s @media print rules) all keep working.
    """
    lang = lang or _resolve_report_language()
    astrologer_html = render_astrologer_report_html(
        name, prediction, dual_narrative=dual_narrative, lang=lang, payload=payload,
        muhurta_result=muhurta_result, muhurta_event_type=muhurta_event_type,
    )
    client_html = render_client_report_html(
        name, prediction, dual_narrative=dual_narrative, lang=lang, payload=payload,
        muhurta_result=muhurta_result, muhurta_event_type=muhurta_event_type,
    )

    astro_tabs = _prefix_fragment_ids(_extract_between(astrologer_html, '<nav class="tabs">', '</nav>'), "a-")
    astro_body = _prefix_fragment_ids(_extract_between(astrologer_html, '<div class="wrap">', '</div>\n</body>'), "a-")
    client_tabs = _prefix_fragment_ids(_extract_between(client_html, '<nav class="tabs">', '</nav>'), "p-")
    client_body = _prefix_fragment_ids(_extract_between(client_html, '<div class="wrap">', '</div>\n</body>'), "p-")

    s = _prepare_common_sections(name, prediction, lang=lang, payload=payload)

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(_t(lang, 'client_title', 'Business Astrology Report'))} — {_esc(name)}</title>
<style>{_shared_css()}</style>
</head>
<body class="has-viewswitch">

{_cover_block(_t(lang, 'client_kicker', 'JyotishAI · Business Astrology Report'), _t(lang, 'client_title', 'Business Astrology Report'), name, s['generated'], prediction.get('rule_pack_version', '—'), lang=lang, verdict_label=s.get('verdict_display'), top_sector_label=(prediction.get('top_sectors') or [{}])[0].get('label'), top_sector_score=(prediction.get('top_sectors') or [{}])[0].get('score'))}
{_toc_block(lang, audience="astrologer")}

<header class="hero">
  <div class="hero-inner">
    <div>
      <div class="kicker">{_esc(_t(lang, 'client_kicker', 'JyotishAI · Business Astrology Report'))}</div>
      <h1>{_esc(name)}</h1>
      <div class="meta">{_esc(_t(lang, 'generated_prefix', 'Generated'))} {s['generated']} &middot; {_esc(_t(lang, 'rule_pack_word', 'Rule pack'))} {_esc(prediction.get('rule_pack_version', '—'))}</div>
    </div>
    <div class="hero-recommend">
      {s['section_final_verdict']}
    </div>
  </div>
</header>

<nav class="viewswitch">
  <div class="vs-inner">
    <span class="vs-label">{_esc(_t(lang, 'viewing_as_word', 'Viewing as'))}</span>
    <button class="vs-btn active" id="btn-profile" onclick="jyotishShowView('profile')">{_esc(_t(lang, 'view_chart_profile', 'Chart Profile'))}</button>
    <button class="vs-btn" id="btn-astrologer" onclick="jyotishShowView('astrologer')">{_esc(_t(lang, 'view_astrologer', 'Astrologer View'))}</button>
  </div>
</nav>

<nav class="tabs" id="tabs-profile">{client_tabs}</nav>
<nav class="tabs" id="tabs-astrologer" style="display:none;">{astro_tabs}</nav>

<div class="wrap">

{_glossary_section_html(lang)}

<div class="view active" id="view-profile">
{client_body}
</div>

<div class="view" id="view-astrologer">
{astro_body}
</div>

</div>

{_print_toolbar_html(lang)}

<script>
function jyotishShowView(v) {{
  document.getElementById('view-profile').classList.toggle('active', v === 'profile');
  document.getElementById('view-astrologer').classList.toggle('active', v === 'astrologer');
  document.getElementById('btn-profile').classList.toggle('active', v === 'profile');
  document.getElementById('btn-astrologer').classList.toggle('active', v === 'astrologer');
  document.getElementById('tabs-profile').style.display = v === 'profile' ? 'block' : 'none';
  document.getElementById('tabs-astrologer').style.display = v === 'astrologer' ? 'block' : 'none';
}}
</script>

</body>
</html>"""


def generate_business_report(
    chart_path: str,
    student_name: str = None,
    output_dir: str = "educational_records",
    llm_narrative: bool = True,
    financial_readiness_inputs: Optional[Dict[str, Any]] = None,
    render_react: bool = True,
) -> Dict[str, str]:
    """Generates ONE combined, print-ready HTML deliverable from a single
    engine run: a single page, headed by the subject's name, with a
    "Chart Profile" / "Astrologer View" switch toggling between the
    client-facing (simplified, narrative-led) and astrologer-facing (full
    technical detail) content in place -- replacing the previous two-file
    (separate astrologer-edition/client-edition) output. Both views read
    from the exact same `prediction` dict via render_combined_report_html()
    (which itself reuses render_astrologer_report_html()/
    render_client_report_html() verbatim), so the two views can never show
    different underlying numbers for the same chart, only different levels
    of detail. Returns {"combined": path} (kept as a dict, not a bare
    string, so existing callers that do out_paths["combined"]-style access
    don't need an isinstance check).

    llm_narrative=True (default) only ATTEMPTS the narrative call -- it
    still requires real consent via _has_llm_narrative_consent()
    (LLM_REPORT_CONSENT=true in .env, or this chart's own
    external_llm_consent field) plus a configured provider API key.
    Without consent, the report renders normally with the narrative
    section simply omitted, never a placeholder claiming failure.

    render_react=True (default) additionally renders the standalone React
    edition (generate_react_report.py) from the same in-memory `prediction`
    dict and returns its path as out["main"] -- this is now the primary
    deliverable of this CLI. out["combined"]/out["legacy"] (same path,
    both keys kept for backward compatibility with existing callers) is
    still always written too. Pass render_react=False to skip the React
    build and fall back to the legacy server-rendered report as main.
    """
    with open(chart_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    payload = parse_json_payload(data, chart_path=chart_path)
    name = student_name or getattr(payload, "name", "Unknown")

    # v29 audit fix: this previously called compute_business_prediction()
    # with its default top_n_sectors=5, silently truncating the rendered
    # "Top Business Sectors" table to 5 of the registry's 19 sectors even
    # though the engine itself ranks every registered sector. Passing the
    # full registry count here means the report always shows every
    # currently-registered sector, and stays correct automatically if the
    # registry grows or shrinks in the future (no hardcoded "19").
    all_sector_count = len(_load_business_registry().get("sectors", {}))
    prediction = compute_business_prediction(
        payload, top_n_sectors=all_sector_count,
        financial_readiness_inputs=financial_readiness_inputs,
    )

    # Resolved once here (from Report_Language_Enabled_Tamil / _Telugu in
    # .env) and threaded through the narrative call and the render so the
    # narrative language and the report chrome language can never disagree.
    lang = _resolve_report_language()

    dual_narrative = _generate_dual_audience_narratives(name, prediction, payload=payload, lang=lang) if llm_narrative else None

    combined_html = render_combined_report_html(name, prediction, dual_narrative=dual_narrative, lang=lang, payload=payload)

    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = str(name).lower().replace(" ", "_")
    lang_suffix = f"_{lang}" if lang != "en" else ""
    combined_path = os.path.join(output_dir, f"business_prediction_report_{safe_name}{lang_suffix}_{ts}.html")

    with open(combined_path, "w", encoding="utf-8") as fh:
        fh.write(combined_html)

    # The React report (generate_react_report.py) is now the primary
    # deliverable of this CLI -- it's built from the exact same in-memory
    # `prediction` dict as combined_html above (never re-read from disk,
    # never a second engine run), so the two outputs can never disagree on
    # a number even though they're rendered by two completely separate
    # templating systems. The old server-rendered combined_html keeps
    # being written too (kept as "legacy"/"combined" in the return dict)
    # since some callers may still depend on that specific file existing.
    #
    # Wrapped in try/except deliberately: if generate_react_report.py is
    # ever missing/broken/moved, that should degrade this CLI back to
    # "just the legacy report" rather than take down the whole run --
    # same "never crash the whole report over an optional layer" posture
    # llm_narrative already follows above.
    react_path = None
    if render_react:
        try:
            react_module = _load_react_report_module()
            react_report_data = react_module._build_report_data(prediction, name_override=name, dual_narrative=dual_narrative)
            react_html = react_module.render_html(react_report_data)
            react_path = os.path.join(output_dir, f"business_prediction_react_{safe_name}{lang_suffix}_{ts}.html")
            with open(react_path, "w", encoding="utf-8") as fh:
                fh.write(react_html)
        except Exception:
            logging.getLogger(__name__).warning("React report generation failed; falling back to the legacy report as main output", exc_info=True)
            react_path = None

    main_path = react_path or combined_path
    return {"main": main_path, "react": react_path, "combined": combined_path, "legacy": combined_path}


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the Business Prediction Analysis report (combined Chart Profile / Astrologer View single page).")
    ap.add_argument("chart", help="Path to chart JSON file")
    ap.add_argument("--name", default=None, help="Override student/subject name (default: chart's own name field)")
    ap.add_argument("--out", default="educational_records", help="Output directory (default: educational_records)")
    ap.add_argument("--no-llm-narrative", action="store_true", help="Skip the LLM-generated astrologer/client narrative section")
    ap.add_argument("--no-react", action="store_true", help="Skip the React edition and fall back to the legacy server-rendered report as main output")
    ap.add_argument("--financial-readiness-json", default=None,
                    help="Path to independently reviewed financial-readiness evidence JSON")
    args = ap.parse_args()

    chart_path = pathlib.Path(args.chart).resolve()
    if not chart_path.exists():
        print(f"ERROR: chart file not found: {chart_path}", file=sys.stderr)
        sys.exit(1)

    financial_inputs = None
    if args.financial_readiness_json:
        evidence_path = pathlib.Path(args.financial_readiness_json).resolve()
        if not evidence_path.is_file():
            ap.error(f"financial readiness JSON not found: {evidence_path}")
        with evidence_path.open("r", encoding="utf-8") as fh:
            financial_inputs = json.load(fh)
        if not isinstance(financial_inputs, dict):
            ap.error("financial readiness JSON must contain an object")

    out_paths = generate_business_report(
        str(chart_path), student_name=args.name, output_dir=args.out,
        llm_narrative=not args.no_llm_narrative,
        financial_readiness_inputs=financial_inputs,
        render_react=not args.no_react,
    )
    print(f"[JyotishAI] Report written -> {out_paths['main']}")
    if out_paths.get("react"):
        print(f"[JyotishAI] Legacy server-rendered edition also written -> {out_paths['legacy']}")


if __name__ == "__main__":
    main()
