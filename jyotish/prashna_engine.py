"""JyotishAI — Prashna Engine Integration Layer  v1.0

This module is the single entry point for the Prashna (Horary) subsystem.
It wraps jyotish.prashna and provides:

  1. PrashnaRequest  — Pydantic input model (matches the UI form fields)
  2. run_prashna_query(request) → PrashnaResponse (Pydantic)
  3. prashna_from_payload(payload, category, question) → PrashnaResponse
       Overlays natal chart data onto the Prashna if available.
  4. generate_prashna_report(response, output_dir) → html_file_path
  5. PRASHNA_CATEGORIES — dict of all valid category keys and display labels

Integration examples
--------------------
  # Standalone (no natal chart needed)
  from jyotish.prashna_engine import PrashnaRequest, run_prashna_query
  req = PrashnaRequest(
      question="Will I get this job offer?",
      category="career_employment",
      moment="2026-06-29 16:44",
      city="Bangalore",
  )
  resp = run_prashna_query(req)
  print(resp.verdict, resp.confidence_band)

  # With natal chart overlay (enriches analysis)
  from jyotish.prashna_engine import prashna_from_payload
  resp = prashna_from_payload(natal_payload, "business", "Will my startup succeed?")

  # Flask / FastAPI
  @app.post("/api/prashna")
  def prashna_endpoint(body: dict):
      req  = PrashnaRequest(**body)
      resp = run_prashna_query(req)
      return resp.model_dump()
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .prashna import (
    PrashnaResult,
    analyze_prashna,
    cast_prashna_chart,
    city_to_coords,
    generate_prashna_html,
    prashna_result_to_dict,
    run_prashna,
    _CATEGORY_LABELS,
    _PRIMARY_HOUSE,
)

logger = logging.getLogger("jyotish_prashna_engine")

# ---------------------------------------------------------------------------
# Verdict display labels (A-2)
# ---------------------------------------------------------------------------

_VERDICT_LABELS: Dict[str, str] = {
    "YES":         "Highly Favourable",
    "NO":          "Not Favourable",
    "CONDITIONAL": "Conditionally Favourable",
    "UNCERTAIN":   "Unclear / Mixed Signals",
}

# gap fix (2026-07-19 audit, 2nd pass): CONDITIONAL used to always render as
# "Conditionally Favourable" regardless of whether the underlying ratio
# leaned yes or no -- a chart at 45% confidence leaning NO displayed the
# exact same yes-sounding label as one at 65% leaning YES. verdict_leaning
# (set in analyze_prashna) now disambiguates which side CONDITIONAL is
# actually hedging toward.
_CONDITIONAL_LABELS: Dict[str, str] = {
    "YES": "Conditionally Favourable",
    "NO":  "Conditionally Unfavourable",
}


def _resolve_verdict_label(verdict: str, verdict_leaning: str) -> str:
    if verdict == "CONDITIONAL":
        return _CONDITIONAL_LABELS.get(verdict_leaning, _VERDICT_LABELS["CONDITIONAL"])
    return _VERDICT_LABELS.get(verdict, verdict)

# ---------------------------------------------------------------------------
# Public category registry
# ---------------------------------------------------------------------------

PRASHNA_CATEGORIES: Dict[str, str] = _CATEGORY_LABELS
"""All supported Prashna categories: {key → display_label}."""

# UI display order
PRASHNA_CATEGORY_ORDER: List[str] = [
    "career_employment",
    "job_change",
    "business",
    "financial",
    "education",
    "foreign_opportunity",
    "relationship",
    "marriage",
    "health",
    "property",
    "legal",
    "travel",
    "competition",
    "pregnancy",
]


# ---------------------------------------------------------------------------
# Pydantic I/O models
# ---------------------------------------------------------------------------

class PrashnaRequest(BaseModel):
    """Input model — matches the Prashna UI form."""

    model_config = ConfigDict(extra="allow")

    question: str = Field(..., description="The querent's question (free text)")
    category: str = Field(..., description="One of PRASHNA_CATEGORIES keys")

    # Moment — accept ISO string or datetime object
    moment: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"),
        description="Moment of question — 'YYYY-MM-DD HH:MM' or ISO-8601",
    )

    # Location
    city: str = Field(default="", description="City name for geocoding")
    lat: Optional[float] = Field(default=None, description="Latitude (overrides city geocoding)")
    lon: Optional[float] = Field(default=None, description="Longitude (overrides city geocoding)")

    # Optional: natal chart overlay fields (if the caller has them)
    natal_lagna_sign: Optional[str]   = None
    natal_moon_sign: Optional[str]    = None
    natal_lagna_lord: Optional[str]   = None
    natal_atmakaraka: Optional[str]   = None
    natal_yogas: Optional[List[str]]  = Field(default_factory=list)

    @field_validator("category", mode="before")
    @classmethod
    def normalise_category(cls, v: str) -> str:
        v = v.strip().lower().replace(" ", "_").replace("&", "and")
        aliases = {
            "career_and_employment": "career_employment",
            "career":                "career_employment",
            "foreign":               "foreign_opportunity",
            "finance":               "financial",
            "job":                   "job_change",
        }
        v = aliases.get(v, v)
        if v not in _CATEGORY_LABELS:
            raise ValueError(
                f"Unknown category '{v}'. Valid: {list(_CATEGORY_LABELS.keys())}"
            )
        return v

    @field_validator("moment", mode="before")
    @classmethod
    def normalise_moment(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M")
        return str(v)


class PrashnaResponse(BaseModel):
    """Output model — all fields JSON-serialisable."""

    model_config = ConfigDict(extra="allow")

    # Echo of request
    question: str = ""
    category: str = ""
    category_label: str = ""
    moment: str = ""
    city: str = ""

    # Core verdict
    verdict: str = "UNCERTAIN"
    verdict_label: str = ""            # A-2: human-readable label e.g. "Highly Favourable"
    confidence: float = 0.5
    confidence_pct: int = 50           # A-2: int 0-100 for easy display
    confidence_band: str = "MODERATE"

    # KP analysis
    kp_sublord_planet: str = ""
    kp_sublord_verdict: str = ""
    kp_signifies_affirm: bool = False

    # Moon
    moon_status: str = ""
    moon_void: bool = False

    # Timing
    timing_estimate: str = ""
    timing_unit: str = ""

    # Significators
    affirm_significators: List[str] = Field(default_factory=list)
    deny_significators: List[str] = Field(default_factory=list)

    # Chart snapshot
    lagna_sign: str = ""
    lagna_lord: str = ""
    moon_sign: str = ""
    moon_nakshatra: str = ""

    # Detailed evidence
    factors: List[Dict[str, Any]] = Field(default_factory=list)
    classical_rules: List[str] = Field(default_factory=list)          # merged (backward compat)
    classical_rules_fired: List[str] = Field(default_factory=list)    # A-2: positive rules only
    denial_rules_fired: List[str] = Field(default_factory=list)       # A-2: negative rules only
    remedies: List[str] = Field(default_factory=list)

    # Full planet and house data (for rendering)
    planets: Dict[str, Dict] = Field(default_factory=dict)
    house_lords: Dict[str, str] = Field(default_factory=dict)
    kp_cusp_sublords: Dict[str, str] = Field(default_factory=dict)

    # Natal overlay context (if provided)
    natal_context_applied: bool = False
    natal_notes: List[str] = Field(default_factory=list)

    # HTML path (if generate_prashna_report was called)
    html_path: Optional[str] = None

    # Gap-remediation (2026-07-18): joint KP cusp check (all doctrinally
    # relevant houses, not just one), Tajika Ithasala/Isbaha note, Moon
    # precision caveat, and the verdict/evidence conflict banner — see
    # jyotish/prashna.py's analyze_prashna() docstring notes for what each
    # of these fixes.
    kp_joint_houses: List[int] = Field(default_factory=list)
    kp_joint_details: Dict[str, str] = Field(default_factory=dict)
    kp_joint_verdict: str = ""
    moon_status_caveat: str = ""
    tajika_aspect_note: str = ""
    internal_conflict_notes: List[str] = Field(default_factory=list)
    afflicted_planets: List[str] = Field(default_factory=list)
    validation_status: Dict[str, Any] = Field(default_factory=dict)
    score_semantics: str = ""
    disclaimer: str = ""

    # gap fix (2026-07-19 audit, 2nd pass): explicit leaning + strict
    # yes/no reading, independent of the hedged verdict/label. See
    # PrashnaResult.verdict_leaning / .binary_answer in prashna.py.
    verdict_leaning: str = ""
    binary_answer: str = ""

    @classmethod
    def from_result(
        cls,
        result: PrashnaResult,
        natal_notes: Optional[List[str]] = None,
    ) -> "PrashnaResponse":
        d = prashna_result_to_dict(result)
        chart = result.chart
        kp_cusp = {}
        if chart:
            kp_cusp = {str(i): chart.kp_sublords.get(str(i), "") for i in range(1, 13)}

        _verdict      = d["verdict"]
        _confidence   = d["confidence"]
        _leaning      = d.get("verdict_leaning", "")
        _pos_rules    = d.get("classical_rules_fired", [])
        _neg_rules    = d.get("denial_rules_fired", [])

        return cls(
            question=d["question"],
            category=d["category"],
            category_label=d["category_label"],
            moment=d["moment"],
            city=d["city"],
            verdict=_verdict,
            verdict_label=_resolve_verdict_label(_verdict, _leaning),    # A-2, gap fix 2026-07-19
            verdict_leaning=_leaning,
            binary_answer=d.get("binary_answer", ""),
            confidence=_confidence,
            confidence_pct=int(round(_confidence * 100)),                # A-2
            confidence_band=d["confidence_band"],
            kp_sublord_planet=d["kp_sublord_planet"],
            kp_sublord_verdict=d["kp_sublord_verdict"],
            kp_signifies_affirm=d["kp_signifies_affirm"],
            moon_status=d["moon_status"],
            moon_void=d["moon_void"],
            timing_estimate=d["timing_estimate"],
            timing_unit=d["timing_unit"],
            affirm_significators=d["affirm_significators"],
            deny_significators=d["deny_significators"],
            lagna_sign=d["lagna_sign"],
            lagna_lord=d["lagna_lord"],
            moon_sign=d["moon_sign"],
            moon_nakshatra=d["moon_nakshatra"],
            factors=d["factors"],
            classical_rules=d["classical_rules"],
            classical_rules_fired=_pos_rules,                            # A-2
            denial_rules_fired=_neg_rules,                               # A-2
            remedies=d["remedies"],
            planets=d["planets"],
            house_lords=d["house_lords"],
            kp_cusp_sublords=kp_cusp,
            natal_context_applied=bool(natal_notes),
            natal_notes=natal_notes or [],
            kp_joint_houses=d.get("kp_joint_houses", []),
            kp_joint_details=d.get("kp_joint_details", {}),
            kp_joint_verdict=d.get("kp_joint_verdict", ""),
            moon_status_caveat=d.get("moon_status_caveat", ""),
            tajika_aspect_note=d.get("tajika_aspect_note", ""),
            internal_conflict_notes=d.get("internal_conflict_notes", []),
            afflicted_planets=d.get("afflicted_planets", []),
            validation_status=d.get("validation_status", {}),
            score_semantics=d.get("score_semantics", ""),
            disclaimer=d.get("disclaimer", ""),
        )


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def _parse_moment(moment_str: str) -> datetime:
    """Parse moment string into datetime; supports common formats."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d-%m-%Y %H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(moment_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse moment '{moment_str}'. Use 'YYYY-MM-DD HH:MM'.")


def run_prashna_query(
    request: PrashnaRequest,
    output_dir: Optional[str] = None,   # D-2: optional HTML output
) -> PrashnaResponse:
    """
    Main entry point: cast the Prashna chart and analyse it.

    Parameters
    ----------
    request    : PrashnaRequest — validated input (question, category, moment, city/lat/lon)
    output_dir : str | None — if provided, an HTML report is written here (D-2)

    Returns
    -------
    PrashnaResponse — all analysis fields, JSON-serialisable.
    """
    # 1. Resolve location
    if request.lat is not None and request.lon is not None:
        lat, lon = request.lat, request.lon
        city_name = request.city or f"{lat:.2f},{lon:.2f}"
    else:
        lat, lon = city_to_coords(request.city or "Delhi")
        city_name = request.city or "Delhi"

    # 2. Parse moment
    moment = _parse_moment(request.moment)

    # 3. Cast chart
    chart = cast_prashna_chart(moment, lat, lon, city_name)

    # 4. Analyse
    result = analyze_prashna(chart, request.category, request.question)

    # 5. Optional natal overlay notes
    natal_notes = _natal_overlay_notes(request, result)
    response = PrashnaResponse.from_result(result, natal_notes)

    # D-2: write HTML if output_dir provided
    if output_dir:
        html_path = generate_prashna_report(response, result, output_dir)
        response.html_path = html_path

    return response


def _natal_overlay_notes(
    request: PrashnaRequest,
    result: PrashnaResult,
) -> List[str]:
    """
    If natal chart data was provided on the request, compare key indicators
    with the Prashna chart and emit contextual notes.
    """
    notes: List[str] = []
    if not any([request.natal_lagna_sign, request.natal_moon_sign,
                request.natal_lagna_lord, request.natal_atmakaraka]):
        return notes

    # Prashna Lagna matches natal Lagna → querent strongly connected to this moment
    if request.natal_lagna_sign and request.natal_lagna_sign == result.lagna_sign:
        notes.append(
            f"Prashna Lagna ({result.lagna_sign}) matches natal Lagna — "
            "the querent is strongly aligned with this moment; adds weight to the YES verdict"
            if result.verdict in ("YES", "CONDITIONAL") else
            f"Prashna Lagna ({result.lagna_sign}) matches natal Lagna — "
            "the querent is deeply invested; the NO verdict is more definitive"
        )

    # Prashna Moon in same sign as natal Moon → emotionally sincere query
    prashna_moon = result.chart.planets_d1.get("Moon", {}).get("sign", "") if result.chart else ""
    if request.natal_moon_sign and prashna_moon == request.natal_moon_sign:
        notes.append(
            f"Prashna Moon in natal Moon sign ({request.natal_moon_sign}) — "
            "query is emotionally sincere; no deceit or confusion in the question"
        )

    # Atmakaraka in affirming house of Prashna chart
    if request.natal_atmakaraka and result.chart:
        ak_data = result.chart.planets_d1.get(request.natal_atmakaraka, {})
        from .prashna import _AFFIRM_HOUSES
        if ak_data.get("house") in _AFFIRM_HOUSES.get(result.category, []):
            notes.append(
                f"Natal Atmakaraka {request.natal_atmakaraka} occupies H{ak_data['house']} "
                f"in the Prashna chart — soul-level confirmation for {result.category}"
            )

    # Natal yogas intersection with Prashna verdict
    if request.natal_yogas:
        benefic_yogas = [y for y in request.natal_yogas
                         if any(k in y.lower() for k in ("raja", "dhana", "gaja", "chandra"))]
        if benefic_yogas and result.verdict in ("YES", "CONDITIONAL"):
            notes.append(
                f"Natal yoga(s) {', '.join(benefic_yogas[:2])} support the positive Prashna verdict"
            )

    return notes


# ---------------------------------------------------------------------------
# HTML report writer
# ---------------------------------------------------------------------------

def generate_prashna_report(
    response: PrashnaResponse,
    result: Optional[PrashnaResult] = None,
    output_dir: str = ".",
) -> str:
    """
    Write the Prashna HTML report to output_dir.

    Parameters
    ----------
    response   : PrashnaResponse (from run_prashna_query)
    result     : original PrashnaResult (needed for full chart data in HTML)
                 If None, re-casts the chart from response fields.
    output_dir : directory to write the .html file

    Returns
    -------
    str : absolute path to the written HTML file.
    """
    if result is None:
        # Re-build a minimal result for HTML from the response dict
        lat, lon = city_to_coords(response.city or "Delhi")
        moment   = _parse_moment(response.moment)
        chart    = cast_prashna_chart(moment, lat, lon, response.city)
        result   = analyze_prashna(chart, response.category, response.question)

    html = generate_prashna_html(result)
    os.makedirs(output_dir, exist_ok=True)
    safe_cat  = response.category.replace(" ", "_").lower()
    moment_dt = _parse_moment(response.moment)
    fname     = f"prashna_{safe_cat}_{moment_dt.strftime('%Y%m%d_%H%M')}.html"
    fpath     = os.path.join(output_dir, fname)
    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write(html)
    logger.info("[PrashnaEngine] HTML written: %s", fpath)
    return fpath


# ---------------------------------------------------------------------------
# Natal payload convenience wrapper
# ---------------------------------------------------------------------------

def prashna_from_payload(
    payload: Any,
    category: str,
    question: str,
    moment: Optional[datetime] = None,
    output_dir: Optional[str] = None,
) -> PrashnaResponse:
    """
    Run a Prashna query enriched with data from an existing NatalPayloadV2.

    Parameters
    ----------
    payload    : NatalPayloadV2 or dict containing natal chart data
    category   : Prashna category key
    question   : The querent's question
    moment     : Datetime of the question (defaults to now)
    output_dir : If provided, HTML report is written here

    Returns
    -------
    PrashnaResponse with natal overlay notes applied.

    Location resolution (in priority order)
    -----------------------------------------
    1. payload["prashna_details"]["latitude_cp"] / ["longitude_cp"] — explicit
       lat/lon for wherever the question is being asked *right now*, paired
       with ["current_place"] as the display name. This is the querent's
       present location, distinct from their birth details.
    2. payload["prashna_details"]["current_place"] alone (no lat/lon given)
       — geocoded via city_to_coords().
    3. payload["birth_place"] — legacy fallback, geocoded via city_to_coords().
    4. "Delhi" — final fallback if nothing else is available.

    Moment resolution (in priority order)
    ----------------------------------------
    1. The explicit `moment` argument, if the caller passed one (unchanged
       behaviour — always wins).
    2. payload["prashna_details"]["current_date"] + ["current_time"], if both
       are present — the moment the question is actually being asked, as
       supplied by the caller (e.g. "2026-07-18" + "09:12:00").
    3. payload["prashna_details"]["current_time"] alone (no current_date) —
       combined with today's date, since a horary chart is nearly always
       cast for "right now"; only the time-of-day portion is customised.
    4. datetime.now() — final fallback (previous default behaviour).
    """
    def _g(key: str, default: Any = None) -> Any:
        if isinstance(payload, dict):
            return payload.get(key, default)
        return getattr(payload, key, default)

    # Extract the current-location details (prashna_details block), e.g.:
    #   "prashna_details": {
    #       "current_place": "Chennai, Tamil Nadu, India",
    #       "latitude_cp": 13.0843, "longitude_cp": 80.2705, ...
    #   }
    _prashna_details = _g("prashna_details", {}) or {}
    if not isinstance(_prashna_details, dict):
        # Pydantic sub-model or similar; normalise to dict if possible.
        _prashna_details = getattr(_prashna_details, "__dict__", {}) or {}

    current_place = _prashna_details.get("current_place", "")
    lat_cp = _prashna_details.get("latitude_cp")
    lon_cp = _prashna_details.get("longitude_cp")

    if lat_cp is not None and lon_cp is not None:
        # Explicit current-location coordinates supplied — use them directly,
        # no geocoding lookup needed.
        lat, lon = float(lat_cp), float(lon_cp)
        city_name = current_place or f"{lat:.4f},{lon:.4f}"
    elif current_place:
        lat, lon = city_to_coords(current_place)
        city_name = current_place
    else:
        # Legacy fallback: no prashna_details block supplied, fall back to
        # birth_place (previous behaviour), then Delhi.
        birth_place = _g("birth_place", "")
        if birth_place:
            lat, lon = city_to_coords(birth_place)
            city_name = birth_place
        else:
            lat, lon = city_to_coords("Delhi")
            city_name = "Delhi"

    # Resolve the query moment: explicit `moment` arg wins; otherwise look
    # for prashna_details.current_date/current_time (the moment the
    # querent is actually asking), falling back to datetime.now().
    if moment is None:
        _current_date = _prashna_details.get("current_date", "")
        _current_time = _prashna_details.get("current_time", "")
        if _current_time:
            _date_part = _current_date or datetime.now().strftime("%Y-%m-%d")
            try:
                moment = datetime.strptime(f"{_date_part} {_current_time}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    moment = datetime.strptime(f"{_date_part} {_current_time}", "%Y-%m-%d %H:%M")
                except ValueError:
                    moment = None  # malformed — fall through to datetime.now() below

    # Build request
    req = PrashnaRequest(
        question=question,
        category=category,
        moment=(moment or datetime.now()).strftime("%Y-%m-%d %H:%M"),
        city=city_name,
        lat=lat,
        lon=lon,
        natal_lagna_sign=_g("lagna_sign"),
        natal_moon_sign=_g("planet_signs", {}).get("Moon") if isinstance(_g("planet_signs", {}), dict) else None,
        natal_lagna_lord=_g("lagna_lord"),
        natal_atmakaraka=_g("atmakaraka"),
        natal_yogas=_g("yogas_present", []),
    )

    # Cast + analyse
    dt      = _parse_moment(req.moment)
    chart   = cast_prashna_chart(dt, lat, lon, city_name)
    result  = analyze_prashna(chart, req.category, req.question)
    natal_notes = _natal_overlay_notes(req, result)
    response    = PrashnaResponse.from_result(result, natal_notes)

    # Optionally write HTML
    if output_dir:
        html_path = generate_prashna_report(response, result, output_dir)
        response.html_path = html_path

    return response


# ---------------------------------------------------------------------------
# Batch Prashna (multiple categories at once)
# ---------------------------------------------------------------------------

def batch_prashna(
    question: str,
    categories: List[str],
    moment: Optional[datetime] = None,
    city: str = "Delhi",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, PrashnaResponse]:
    """
    Run Prashna analysis for multiple categories at the same moment.
    Casts the chart once and reuses it for all categories.

    Returns {category_key: PrashnaResponse}
    """
    if lat is None or lon is None:
        lat, lon = city_to_coords(city)

    dt    = moment or datetime.now()
    chart = cast_prashna_chart(dt, lat, lon, city)

    results: Dict[str, PrashnaResponse] = {}
    for cat in categories:
        try:
            r = analyze_prashna(chart, cat, question)
            results[cat] = PrashnaResponse.from_result(r)
        except Exception as exc:
            logger.warning("[PrashnaEngine] batch_prashna error for %s: %s", cat, exc)

    return results


# -----------------------------------
# Utility: category metadata for UI
# ---------------------------------------------------------------------------

def get_category_metadata():
    """Return UI-ready list of all Prashna categories with labels, primary house, and examples."""
    _examples = {
        "career_employment":   "Will I get this job offer?",
        "job_change":          "Should I change my job now?",
        "business":            "Will my business venture succeed?",
        "financial":           "Will I receive the expected money?",
        "education":           "Will I pass my exam / get admission?",
        "foreign_opportunity": "Will I get a chance to go abroad?",
        "relationship":        "Will this relationship work out?",
        "marriage":            "Will my marriage happen this year?",
        "health":              "Will I recover from this illness quickly?",
        "property":            "Will I be able to buy/sell this property?",
        "legal":               "Will the legal case go in my favour?",
        "travel":              "Will my travel plans go ahead smoothly?",
        "competition":         "Will I win this competition / election?",
        "pregnancy":           "Will I conceive soon?",
    }
    return [
        {
            "key":           cat,
            "label":         PRASHNA_CATEGORIES.get(cat, cat),
            "primary_house": _PRIMARY_HOUSE.get(cat, 0),
            "example":       _examples.get(cat, "Will this happen?"),
        }
        for cat in PRASHNA_CATEGORY_ORDER
    ]
