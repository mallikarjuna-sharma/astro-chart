"""POST API: birth data in; JSON table or HTML (table + text meta)."""
from __future__ import annotations

import html
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from botocore.exceptions import ClientError, NoCredentialsError

from jhora import const, utils
from jhora.horoscope.chart import charts as jhora_charts
from jhora.horoscope.match import compatibility
from jhora.panchanga import drik
from jhora.panchanga.drik import nakshatra_pada

from api import extended
from api.db import repository as chart_repository
from api.db.dynamo import DynamoDBNotConfiguredError, dynamo_client_error
from api.geocode import GeocodeError, geocode_location, geocode_place_id, places_autocomplete
from api.jhora_bootstrap import init_jhora
from api.schemas.chart import (
    BirthChartBody,
    BirthRequest,
    ConsolidatedRequest,
    DivisionalChart,
    DivisionalChartsResponse,
    HtmlDocumentJson,
    TableResponse,
)
from api.schemas.storage import (
    SavedChartListResponse,
    SavedChartResponse,
    SaveChartRequest,
)

_PLANET_NAMES = {
    0: "Sun",
    1: "Moon",
    2: "Mars",
    3: "Mercury",
    4: "Jupiter",
    5: "Venus",
    6: "Saturn",
    7: "Rahu",
    8: "Ketu",
}


def _deg_to_dms(deg: float) -> str:
    x = abs(deg)
    d = int(math.floor(x))
    m_float = (x - d) * 60.0
    m = int(math.floor(m_float))
    s = int(round((m_float - m) * 60.0))
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        d += 1
    sign = "-" if deg < 0 else ""
    return f"{sign}{d}°{m:02d}′{s:02d}″"


def _nak_name(nak_index_1_to_27: int) -> str:
    if 1 <= nak_index_1_to_27 <= len(compatibility.nakshatra_list):
        return compatibility.nakshatra_list[nak_index_1_to_27 - 1]
    return ""


def _escape_cell(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _build_html_page(title: str, columns: list[str], rows: list[list[Any]], meta: dict[str, Any]) -> str:
    """Full minimal HTML: heading + meta as plain text + one data table."""
    e = html.escape
    meta_lines = [
        f"Place: {meta.get('place_label', '')}",
        f"Birth (local): {meta.get('birth_local', '')}",
        f"Latitude: {meta.get('latitude', '')}  Longitude: {meta.get('longitude', '')}",
        f"Timezone (hours E of UTC): {meta.get('timezone_offset_hours', '')}",
        f"Julian day: {meta['julian_day']}",
        f"Ayanamsa: {meta['ayanamsa_mode']}",
        f"Use true nodes: {meta['use_true_nodes']}",
        f"Include outer planets: {meta['include_outer_planets']}",
        "",
        str(meta.get("ephemeris_note", "")),
    ]
    if meta.get("upagraha_warnings"):
        meta_lines.extend(["", "Upagraha warnings:"])
        meta_lines.extend(str(w) for w in meta["upagraha_warnings"])
    meta_text = "\n".join(meta_lines)
    thead = "<tr>" + "".join(f"<th scope='col'>{_escape_cell(c)}</th>" for c in columns) + "</tr>"
    tbody_rows = []
    for row in rows:
        tbody_rows.append(
            "<tr>" + "".join(f"<td>{_escape_cell(cell)}</td>" for cell in row) + "</tr>"
        )
    tbody = "\n".join(tbody_rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{e(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; line-height: 1.45; }}
    h1 {{ font-size: 1.25rem; margin-bottom: 0.75rem; }}
    .meta {{ white-space: pre-wrap; margin: 1rem 0; font-size: 0.9rem; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 56rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
  </style>
</head>
<body>
  <h1>{e(title)}</h1>
  <section class="meta" aria-label="Chart parameters">{e(meta_text)}</section>
  <table>
    <thead>{thead}</thead>
    <tbody>
{tbody}
    </tbody>
  </table>
</body>
</html>
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_jhora()
    yield


app = FastAPI(title="PyJHora table API", lifespan=lifespan)

_cors_raw = os.getenv("CORS_ORIGINS", "*").strip()
_cors_list = ["*"] if _cors_raw == "*" else [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _compute_birth_chart(body: BirthChartBody) -> TableResponse:
    init_jhora()
    if body.use_true_nodes:
        const.set_node_mode(True)
    else:
        const.set_node_mode(False)

    place = drik.Place(
        body.place_label,
        body.latitude,
        body.longitude,
        body.timezone_offset_hours,
    )
    jd = utils.julian_day_number(
        (body.year, body.month, body.day),
        (body.hour, body.minute, body.second),
    )
    mode = (body.ayanamsa or const._DEFAULT_AYANAMSA_MODE).upper()
    try:
        drik.set_ayanamsa_mode(mode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unknown ayanamsa: {mode!r}: {exc}") from exc

    try:
        asc_rasi, asc_lon, asc_nak, asc_pada = drik.ascendant(jd, place)
        positions = drik.dhasavarga(
            jd,
            place,
            divisional_chart_factor=1,
            set_rahu_ketu_as_true_nodes=body.use_true_nodes,
            include_western_planets=body.include_outer_planets,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Ephemeris/planet calculation failed. "
                "If you enabled true nodes or outer planets, install full Swiss ephemeris "
                "files into jhora/data/ephe. "
                f"Original error: {exc}"
            ),
        ) from exc

    columns = [
        "body",
        "rasi",
        "longitude_in_rasi",
        "longitude_dms",
        "nakshatra",
        "pada",
    ]
    rows: list[list[Any]] = []

    rows.append(
        [
            "Lagna",
            const.rasi_names_en[asc_rasi],
            round(asc_lon, 6),
            _deg_to_dms(asc_lon),
            _nak_name(asc_nak),
            asc_pada,
        ]
    )

    for planet_id, (rasi_idx, lon_in_rasi) in positions:
        if not isinstance(planet_id, int):
            continue
        if planet_id > const.KETU_ID and not body.include_outer_planets:
            continue
        full = (rasi_idx % 12) * 30.0 + float(lon_in_rasi)
        nak_idx, pada_idx, _ = nakshatra_pada(full)
        name = _PLANET_NAMES.get(planet_id, f"planet_{planet_id}")
        rows.append(
            [
                name,
                const.rasi_names_en[rasi_idx % 12],
                round(float(lon_in_rasi), 6),
                _deg_to_dms(float(lon_in_rasi)),
                _nak_name(int(nak_idx)),
                int(pada_idx),
            ]
        )

    # Gulika / Maandi (Saturn-segment upagrahas; PyJHora: drik.gulika_longitude / maandi_longitude)
    dob = drik.Date(body.year, body.month, body.day)
    tob_tuple = (body.hour, body.minute, body.second)
    upagraha_warnings: list[str] = []
    for label, lon_fn in (
        ("Gulika", drik.gulika_longitude),
        ("Maandi", drik.maandi_longitude),
    ):
        try:
            r_i, lon_i = lon_fn(dob, tob_tuple, place)
            full_u = (r_i % 12) * 30.0 + float(lon_i)
            nak_u, pada_u, _ = nakshatra_pada(full_u)
            rows.append(
                [
                    label,
                    const.rasi_names_en[r_i % 12],
                    round(float(lon_i), 6),
                    _deg_to_dms(float(lon_i)),
                    _nak_name(int(nak_u)),
                    int(pada_u),
                ]
            )
        except Exception as exc:
            upagraha_warnings.append(f"{label}: {exc}")

    meta = {
        "place_label": body.place_label,
        "birth_local": f"{body.year:04d}-{body.month:02d}-{body.day:02d} "
        f"{body.hour:02d}:{body.minute:02d}:{body.second:02d}",
        "latitude": body.latitude,
        "longitude": body.longitude,
        "timezone_offset_hours": body.timezone_offset_hours,
        "julian_day": jd,
        "ayanamsa_mode": mode,
        "use_true_nodes": body.use_true_nodes,
        "include_outer_planets": body.include_outer_planets,
        "ephemeris_note": (
            "Default API uses mean Rahu/Ketu so PyPI ephemeris works. "
            "Set use_true_nodes=true only with full sepl*.se1 files."
        ),
    }
    if upagraha_warnings:
        meta["upagraha_warnings"] = upagraha_warnings
    return TableResponse(
        title="Sidereal D1 (Rasi) — Lagna, graha, Gulika, Maandi",
        columns=columns,
        rows=rows,
        meta=meta,
    )


class GeocodeResponse(BaseModel):
    query: str
    place_label: str
    latitude: float
    longitude: float
    timezone_offset_hours: float | None = None
    provider: str


class PlaceSuggestion(BaseModel):
    place_id: str
    description: str


class AutocompleteResponse(BaseModel):
    suggestions: list[PlaceSuggestion]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/geocode", response_model=GeocodeResponse)
def geocode_location_endpoint(
    location: str = Query(..., min_length=1, max_length=200, examples=["Srirangam"]),
) -> GeocodeResponse:
    """Resolve a place name to latitude, longitude, and timezone offset."""
    try:
        result = geocode_location(location)
    except GeocodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding failed: {exc}") from exc
    return GeocodeResponse.model_validate(result)


@app.get("/api/places/autocomplete", response_model=AutocompleteResponse)
def places_autocomplete_endpoint(
    input: str = Query(..., min_length=1, max_length=200, alias="input", examples=["Kollam"]),
) -> AutocompleteResponse:
    """Google Places autocomplete for Indian locations (requires GOOGLE_MAPS_API_KEY + Places API)."""
    try:
        items = places_autocomplete(input)
    except GeocodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Autocomplete failed: {exc}") from exc
    return AutocompleteResponse(suggestions=items)


@app.get("/api/places/resolve", response_model=GeocodeResponse)
def places_resolve_endpoint(
    place_id: str = Query(..., min_length=1, max_length=200, examples=["ChIJ..."]),
) -> GeocodeResponse:
    """Resolve a Google place_id to coordinates (requires GOOGLE_MAPS_API_KEY + Places API)."""
    try:
        result = geocode_place_id(place_id)
    except GeocodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Place resolve failed: {exc}") from exc
    return GeocodeResponse.model_validate(result)


@app.post(
    "/api/birth-chart-table",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/html": {},
            },
        },
    },
)
def birth_chart_table(body: BirthRequest) -> TableResponse | HTMLResponse | HtmlDocumentJson:
    """
    Returns sidereal D1 graha positions + Lagna.

    - `response_format`: `"json"` (default) → `columns` / `rows` / `meta`.
    - `response_format`: `"html"` → full HTML document, `Content-Type: text/html` (open URL or save as `.html`).
    - `response_format`: `"html_json"` → JSON `{ "html": "<!DOCTYPE html>..." }` for `iframe.srcdoc` / `document.write`.
    """
    data = _compute_birth_chart(body)
    if body.response_format == "html":
        page = _build_html_page(data.title, data.columns, data.rows, data.meta)
        return HTMLResponse(content=page, media_type="text/html; charset=utf-8")
    if body.response_format == "html_json":
        page = _build_html_page(data.title, data.columns, data.rows, data.meta)
        return HtmlDocumentJson(html=page)
    return data


@app.post(
    "/api/birth-chart-html",
    response_class=HTMLResponse,
    summary="Birth chart as HTML only",
)
def birth_chart_html(body: BirthChartBody) -> HTMLResponse:
    """
    Same inputs as `/api/birth-chart-table`, but always returns a **complete HTML page** string
    (`text/html`) you can open in a browser or embed (`iframe.srcdoc`, `blob:` URL).
    """
    data = _compute_birth_chart(body)
    page = _build_html_page(data.title, data.columns, data.rows, data.meta)
    return HTMLResponse(content=page, media_type="text/html; charset=utf-8")


@app.get(
    "/api/birth-chart-view",
    response_class=HTMLResponse,
    summary="Birth chart HTML in browser (query string)",
)
def birth_chart_view(
    year: int = Query(..., examples=[2014]),
    month: int = Query(..., ge=1, le=12),
    day: int = Query(..., ge=1, le=31),
    hour: int = Query(0, ge=0, le=23),
    minute: int = Query(0, ge=0, le=59),
    second: int = Query(0, ge=0, le=59),
    place_label: str = Query("Birth place"),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    timezone_offset_hours: float = Query(..., description="IST = 5.5"),
    ayanamsa: str | None = Query(None, description="e.g. LAHIRI"),
    use_true_nodes: bool = Query(False),
    include_outer_planets: bool = Query(False),
) -> HTMLResponse:
    """
    Same chart as `POST /api/birth-chart-html`, but parameters are in the **URL query string**.
    Paste the full URL into a browser address bar (while the API server is running).
    """
    body = BirthChartBody(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        place_label=place_label,
        latitude=latitude,
        longitude=longitude,
        timezone_offset_hours=timezone_offset_hours,
        ayanamsa=ayanamsa,
        use_true_nodes=use_true_nodes,
        include_outer_planets=include_outer_planets,
    )
    data = _compute_birth_chart(body)
    page = _build_html_page(data.title, data.columns, data.rows, data.meta)
    return HTMLResponse(content=page, media_type="text/html; charset=utf-8")


# ---------------------------------------------------------------------------
# Divisional charts (D1..D9) — independent endpoint for the Vedic chart grid
# ---------------------------------------------------------------------------

# Short labels used in chart cells (compact for South-Indian style 12 boxes).
_BODY_SHORT = {
    "L": "La",  # Lagna / Ascendant
    0: "Su",
    1: "Mo",
    2: "Ma",
    3: "Me",
    4: "Ju",
    5: "Ve",
    6: "Sa",
    7: "Ra",
    8: "Ke",
    9: "Ur",
    10: "Ne",
    11: "Pl",
    "Gu": "Gu",  # Gulika
    "Md": "Md",  # Maandi
}

_DIVISION_NAMES = {
    1: "Rasi (D1)",
    2: "Hora (D2)",
    3: "Drekkana (D3)",
    4: "Chaturthamsa (D4)",
    5: "Panchamsa (D5)",
    6: "Shashthamsa (D6)",
    7: "Saptamsa (D7)",
    8: "Ashtamsa (D8)",
    9: "Navamsa (D9)",
    10: "Dasamsa (D10)",
    16: "Shodasamsa (D16)",
    24: "Siddhamsa (D24)",
    60: "Shashtiamsa (D60)",
    81: "Ashtottariamsa (D81)",
}


def _compute_divisional_charts(
    body: BirthChartBody, factors: list[int]
) -> DivisionalChartsResponse:
    """Compute D-N varga charts for the given factors. Adds Lagna + 9 grahas (+ Gulika/Maandi for D-N).

    Sources:
      - PyJHora `jhora.horoscope.chart.charts.divisional_chart(jd, place, divisional_chart_factor=N)`
        returns `[['L', (rasi, lon)], [planet_id, (rasi, lon)], ...]`.
      - Gulika/Maandi via `drik.gulika_longitude` / `drik.maandi_longitude` (both accept
        `divisional_chart_factor` and return `[rasi, lon_in_rasi]`).
    """
    init_jhora()
    if body.use_true_nodes:
        const.set_node_mode(True)
    else:
        const.set_node_mode(False)

    place = drik.Place(
        body.place_label,
        body.latitude,
        body.longitude,
        body.timezone_offset_hours,
    )
    jd = utils.julian_day_number(
        (body.year, body.month, body.day),
        (body.hour, body.minute, body.second),
    )
    mode = (body.ayanamsa or const._DEFAULT_AYANAMSA_MODE).upper()
    try:
        drik.set_ayanamsa_mode(mode)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Unknown ayanamsa: {mode!r}: {exc}"
        ) from exc

    dob = drik.Date(body.year, body.month, body.day)
    tob_tuple = (body.hour, body.minute, body.second)

    out_charts: list[DivisionalChart] = []
    warnings: list[str] = []

    for factor in factors:
        try:
            positions = jhora_charts.divisional_chart(
                jd, place, divisional_chart_factor=factor
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"divisional_chart failed for D{factor}: {exc}",
            ) from exc

        # Initialize 12 buckets keyed by rasi index (0..11)
        buckets: list[list[str]] = [[] for _ in range(12)]
        for pid, (rasi_idx, _lon) in positions:
            r = int(rasi_idx) % 12
            label = _BODY_SHORT.get(pid, str(pid))
            # Skip outer planets (>= Uranus) unless explicitly requested.
            if isinstance(pid, int) and pid > const.KETU_ID and not body.include_outer_planets:
                continue
            buckets[r].append(label)

        # Optional upagrahas: Gulika and Maandi for the same divisional factor
        for label, lon_fn in (
            ("Gu", drik.gulika_longitude),
            ("Md", drik.maandi_longitude),
        ):
            try:
                r_i, _lon_i = lon_fn(dob, tob_tuple, place, divisional_chart_factor=factor)
                buckets[int(r_i) % 12].append(label)
            except Exception as exc:
                warnings.append(f"D{factor} {label}: {exc}")

        houses = [
            {
                "rasi": r,
                "rasi_name": const.rasi_names_en[r],
                "bodies": buckets[r],
            }
            for r in range(12)
        ]

        out_charts.append(
            DivisionalChart(
                factor=factor,
                name=_DIVISION_NAMES.get(factor, f"D{factor}"),
                houses=houses,
            )
        )

    meta = {
        "place_label": body.place_label,
        "birth_local": (
            f"{body.year:04d}-{body.month:02d}-{body.day:02d} "
            f"{body.hour:02d}:{body.minute:02d}:{body.second:02d}"
        ),
        "latitude": body.latitude,
        "longitude": body.longitude,
        "timezone_offset_hours": body.timezone_offset_hours,
        "julian_day": jd,
        "ayanamsa_mode": mode,
        "use_true_nodes": body.use_true_nodes,
        "include_outer_planets": body.include_outer_planets,
        "body_short_legend": {
            "La": "Lagna",
            "Su": "Sun",
            "Mo": "Moon",
            "Ma": "Mars",
            "Me": "Mercury",
            "Ju": "Jupiter",
            "Ve": "Venus",
            "Sa": "Saturn",
            "Ra": "Rahu",
            "Ke": "Ketu",
            "Gu": "Gulika",
            "Md": "Maandi",
        },
    }
    if warnings:
        meta["warnings"] = warnings
    return DivisionalChartsResponse(charts=out_charts, meta=meta)


_ALLOWED_DIVISIONAL_FACTORS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 24, 60, 81}


@app.post("/api/divisional-charts", response_model=DivisionalChartsResponse)
def divisional_charts_endpoint(
    body: BirthChartBody,
    factors: str | None = Query(
        None,
        description=(
            "Comma-separated divisional factors (e.g. `10,16,24,60,81`). "
            "Defaults to D1..D9. Allowed: 1-10,16,24,60,81."
        ),
    ),
) -> DivisionalChartsResponse:
    """Return divisional charts as 12-house buckets (Aries..Pisces) with body short codes.

    The frontend uses this to render the South-Indian style 4x4 chart grid for each
    division. By default returns D1..D9; pass `?factors=10,16,24,60,81` for the
    extended (varga) set.
    """
    if factors:
        try:
            requested = [int(f.strip()) for f in factors.split(",") if f.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid factors: {factors!r}") from exc
        bad = [f for f in requested if f not in _ALLOWED_DIVISIONAL_FACTORS]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unsupported divisional factors: {bad}")
        selected = requested
    else:
        selected = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    return _compute_divisional_charts(body, factors=selected)


def _dynamo_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DynamoDBNotConfiguredError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, NoCredentialsError):
        return HTTPException(
            status_code=503,
            detail=(
                "AWS credentials not found. Run `aws configure` or set "
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, then restart the server."
            ),
        )
    if isinstance(exc, ClientError):
        return HTTPException(status_code=502, detail=f"DynamoDB error: {dynamo_client_error(exc)}")
    return HTTPException(status_code=500, detail=str(exc))


@app.post("/api/users/{user_id}/charts", response_model=SavedChartResponse)
def create_saved_chart(user_id: str, body: SaveChartRequest) -> SavedChartResponse:
    """Compute D1 table + D1..D9 charts and persist the snapshot in DynamoDB."""
    user_id = user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    d1 = _compute_birth_chart(body.birth_input)
    divisional = _compute_divisional_charts(body.birth_input, factors=[1, 2, 3, 4, 5, 6, 7, 8, 9])
    try:
        item = chart_repository.save_birth_chart(
            user_id,
            body.user_info.model_dump(),
            body.birth_input,
            d1,
            divisional,
        )
    except Exception as exc:
        raise _dynamo_http_error(exc) from exc
    return SavedChartResponse.model_validate(item)


@app.get("/api/users/{user_id}/charts", response_model=SavedChartListResponse)
def list_saved_charts(user_id: str) -> SavedChartListResponse:
    user_id = user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        charts = chart_repository.list_user_charts(user_id)
    except Exception as exc:
        raise _dynamo_http_error(exc) from exc
    return SavedChartListResponse(charts=charts)


@app.get("/api/users/{user_id}/charts/{chart_id}", response_model=SavedChartResponse)
def get_saved_chart(user_id: str, chart_id: str) -> SavedChartResponse:
    user_id = user_id.strip()
    chart_id = chart_id.strip()
    if not user_id or not chart_id:
        raise HTTPException(status_code=400, detail="user_id and chart_id are required")
    try:
        item = chart_repository.get_birth_chart(user_id, chart_id)
    except Exception as exc:
        raise _dynamo_http_error(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Chart not found")
    return SavedChartResponse.model_validate(item)


@app.delete("/api/users/{user_id}/charts/{chart_id}")
def delete_saved_chart(user_id: str, chart_id: str) -> dict[str, str]:
    user_id = user_id.strip()
    chart_id = chart_id.strip()
    if not user_id or not chart_id:
        raise HTTPException(status_code=400, detail="user_id and chart_id are required")
    try:
        deleted = chart_repository.delete_birth_chart(user_id, chart_id)
    except Exception as exc:
        raise _dynamo_http_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Chart not found")
    return {"status": "deleted", "chart_id": chart_id}


def _run_extended(label: str, fn, body: BirthChartBody) -> dict[str, Any]:
    """Run a single extended computation, converting failures to HTTP 502 with a clear message."""
    try:
        return fn(body)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface library errors to the client
        raise HTTPException(
            status_code=502, detail=f"{label} computation failed: {exc}"
        ) from exc


@app.post("/api/panchanga")
def panchanga_endpoint(body: BirthChartBody) -> dict[str, Any]:
    """Tithi, Nakshatra (+pada), Yoga, Karana, Moon Rasi and Rasi lord at birth."""
    return _run_extended("Panchanga", extended.compute_panchanga, body)


@app.post("/api/ashtakavarga")
def ashtakavarga_endpoint(body: BirthChartBody) -> dict[str, Any]:
    """Sarvashtakavarga (SAV) per house + Bhinnashtakavarga (BAV) per contributor."""
    return _run_extended("Ashtakavarga", extended.compute_ashtakavarga, body)


@app.post("/api/shadbala")
def shadbala_endpoint(body: BirthChartBody) -> dict[str, Any]:
    """Shadbala strength per planet (Rupas + percentage of required strength)."""
    return _run_extended("Shadbala", extended.compute_shadbala, body)


@app.post("/api/jaimini")
def jaimini_endpoint(body: BirthChartBody) -> dict[str, Any]:
    """Jaimini chara karakas, karakamsa, Arudha/Upapada lagna and Chara dasha."""
    return _run_extended("Jaimini", extended.compute_jaimini, body)


@app.post("/api/vimshottari")
def vimshottari_endpoint(body: BirthChartBody) -> dict[str, Any]:
    """Vimshottari mahadasha periods plus current maha/antardasha."""
    return _run_extended("Vimshottari", extended.compute_vimshottari, body)


@app.post("/api/kp")
def kp_endpoint(body: BirthChartBody) -> dict[str, Any]:
    """KP system: sign lord, star (nakshatra) lord and sub lord for each body."""
    return _run_extended("KP", extended.compute_kp, body)


@app.post("/api/consolidated")
def consolidated_endpoint(req: ConsolidatedRequest) -> dict[str, Any]:
    """Single consolidated KP-oriented JSON (KP ayanamsa, true nodes, 7-karaka).

    Bundles system config, student context, D1 planets (with retrograde/latitude/
    shadbala), D9/D10/D24 signs, KP cusps + significators, Jaimini (KN Rao), SAV
    and the Vimshottari maha sequence into one copy-friendly object.
    """
    sc = req.student_context.model_dump() if req.student_context else None
    try:
        return extended.compute_consolidated(req.birth_input, sc)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Consolidated export failed: {exc}") from exc


# NOTE: The planetary-transits feature (1960-2080) is intentionally decoupled
# from the running app. The precomputed data is kept in git at
# `api/data/transits_1960_2080.json` and can be regenerated via
# `api.extended._compute_transits_uncached()`, but no route serves it and the
# UI does not request it.


_web_dir = Path(__file__).resolve().parent.parent / "web"
if _web_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
