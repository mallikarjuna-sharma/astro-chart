"""Prashna (horary) API — cast chart at question moment and return UI-ready JSON."""
from __future__ import annotations

from typing import Any

from api.geocode import GeocodeError, geocode_location
from jyotish.prashna_engine import (
    PrashnaRequest,
    PrashnaResponse,
    batch_prashna,
    get_category_metadata,
    run_prashna_query,
    _parse_moment,
)


class PrashnaError(ValueError):
    """Raised when a Prashna request cannot be completed."""


def _resolve_location(request: PrashnaRequest) -> PrashnaRequest:
    """Prefer explicit lat/lon; otherwise geocode city via the shared API geocoder."""
    if request.lat is not None and request.lon is not None:
        return request

    city = (request.city or "").strip()
    if city:
        try:
            geo = geocode_location(city)
            return request.model_copy(
                update={
                    "lat": float(geo["latitude"]),
                    "lon": float(geo["longitude"]),
                    "city": str(geo.get("place_label") or city),
                }
            )
        except GeocodeError:
            pass

    return request


def run_prashna_analysis(request: PrashnaRequest) -> PrashnaResponse:
    """Validate, resolve location, cast Prashna chart, and return structured analysis."""
    try:
        resolved = _resolve_location(request)
        return run_prashna_query(resolved)
    except ValueError as exc:
        raise PrashnaError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise PrashnaError(f"Prashna analysis failed: {exc}") from exc


def run_prashna_batch(
    question: str,
    categories: list[str],
    *,
    moment: str | None = None,
    city: str = "Delhi",
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, PrashnaResponse]:
    """Run multiple category analyses at the same moment (chart cast once)."""
    dt = _parse_moment(moment) if moment else None

    if lat is None or lon is None:
        try:
            geo = geocode_location(city)
            lat = float(geo["latitude"])
            lon = float(geo["longitude"])
            city = str(geo.get("place_label") or city)
        except GeocodeError:
            pass

    try:
        return batch_prashna(
            question=question,
            categories=categories,
            moment=dt,
            city=city,
            lat=lat,
            lon=lon,
        )
    except ValueError as exc:
        raise PrashnaError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise PrashnaError(f"Batch Prashna analysis failed: {exc}") from exc


def list_prashna_categories() -> list[dict[str, Any]]:
    """Return UI dropdown metadata for all supported Prashna categories."""
    return get_category_metadata()
