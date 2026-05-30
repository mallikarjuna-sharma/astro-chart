"""Resolve place names to coordinates (Google if configured, else OpenStreetMap/Nominatim)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

import pytz
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import GoogleV3, Nominatim
from timezonefinder import TimezoneFinder


class GeocodeError(ValueError):
    """Location could not be resolved."""


# Fast offline lookup for common Indian birth places (case-insensitive key).
_KNOWN_PLACES: dict[str, dict[str, object]] = {
    "srirangam": {
        "place_label": "Srirangam, Tiruchirappalli, Tamil Nadu, India",
        "latitude": 10.8627,
        "longitude": 78.6928,
    },
    "madurai": {
        "place_label": "Madurai, Tamil Nadu, India",
        "latitude": 9.9252,
        "longitude": 78.1198,
    },
    "kolkata": {
        "place_label": "Kolkata, West Bengal, India",
        "latitude": 22.5726,
        "longitude": 88.3639,
    },
    "delhi": {
        "place_label": "Delhi, India",
        "latitude": 28.6139,
        "longitude": 77.2090,
    },
    "new delhi": {
        "place_label": "New Delhi, Delhi, India",
        "latitude": 28.6139,
        "longitude": 77.2090,
    },
    "pune": {
        "place_label": "Pune, Maharashtra, India",
        "latitude": 18.5204,
        "longitude": 73.8567,
    },
    "chennai": {
        "place_label": "Chennai, Tamil Nadu, India",
        "latitude": 13.0827,
        "longitude": 80.2707,
    },
    "mumbai": {
        "place_label": "Mumbai, Maharashtra, India",
        "latitude": 19.0760,
        "longitude": 72.8777,
    },
    "dharmapuri": {
        "place_label": "Dharmapuri, Tamil Nadu, India",
        "latitude": 12.1360,
        "longitude": 78.1432,
    },
}


def _lookup_known_place(query: str) -> dict[str, object] | None:
    key = query.strip().lower()
    candidates = {key, key.split(",")[0].strip()}
    for candidate in candidates:
        if candidate in _KNOWN_PLACES:
            known = _KNOWN_PLACES[candidate]
            return {
                "query": query,
                "place_label": known["place_label"],
                "latitude": known["latitude"],
                "longitude": known["longitude"],
                "timezone_offset_hours": 5.5,
                "provider": "builtin",
            }
    return None


@lru_cache(maxsize=1)
def _timezone_finder() -> TimezoneFinder:
    return TimezoneFinder()


def _timezone_offset_hours(latitude: float, longitude: float) -> float | None:
    tz_name = _timezone_finder().timezone_at(lat=latitude, lng=longitude)
    if not tz_name:
        return None
    tz = pytz.timezone(tz_name)
    offset = tz.utcoffset(datetime.now(timezone.utc))
    if offset is None:
        return None
    return offset.total_seconds() / 3600.0


def _pick_best_result(results: list) -> object | None:
    if not results:
        return None
    return results[0]


def _geocode_with_google(query: str, api_key: str):
    geocoder = GoogleV3(api_key=api_key, timeout=10)
    location = geocoder.geocode(query, region="in")
    if location:
        return location
    return geocoder.geocode(f"{query}, India")


def _geocode_with_nominatim(query: str):
    geocoder = Nominatim(user_agent="pyjhora-api/1.0", timeout=10)
    for candidate in (query, f"{query}, India"):
        location = geocoder.geocode(candidate, country_codes="in", addressdetails=True)
        if location:
            return location
    return geocoder.geocode(query, addressdetails=True)


def geocode_location(query: str) -> dict[str, object]:
    text = query.strip()
    if not text:
        raise GeocodeError("location is required")

    known = _lookup_known_place(text)
    if known is not None:
        return known

    google_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    try:
        if google_key:
            location = _geocode_with_google(text, google_key)
            provider = "google"
        else:
            location = _geocode_with_nominatim(text)
            provider = "nominatim"
    except (GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable) as exc:
        raise GeocodeError(f"Geocoding service error: {exc}") from exc

    if location is None:
        raise GeocodeError(f"Could not find coordinates for {text!r}")

    latitude = float(location.latitude)
    longitude = float(location.longitude)
    tz_offset = _timezone_offset_hours(latitude, longitude)
    address = location.address or text

    return {
        "query": text,
        "place_label": address,
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "timezone_offset_hours": tz_offset,
        "provider": provider,
    }
