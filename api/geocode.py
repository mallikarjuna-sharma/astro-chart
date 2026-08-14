"""Resolve place names to coordinates (Google if configured, else OpenStreetMap/Nominatim)."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import certifi
import pytz
import requests
import ssl
from geopy.adapters import RequestsAdapter
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import GoogleV3, Nominatim

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

_HTTP_HEADERS = {"User-Agent": "pyjhora-api/1.0"}


class GeocodeError(ValueError):
    """Location could not be resolved."""


@dataclass(frozen=True)
class _GeoResult:
    latitude: float
    longitude: float
    address: str


# Fast offline lookup for common Indian birth places (case-insensitive key).
_KNOWN_PLACES: dict[str, dict[str, object]] = {
    "srirangam": {
        "place_label": "Srirangam, Tiruchirappalli, Tamil Nadu, India",
        "latitude": 10.8655,
        "longitude": 78.6882,
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
    "kochi": {
        "place_label": "Kochi, Kerala, India",
        "latitude": 9.9312,
        "longitude": 76.2673,
    },
    "cochin": {
        "place_label": "Kochi, Kerala, India",
        "latitude": 9.9312,
        "longitude": 76.2673,
    },
    "kollam": {
        "place_label": "Kollam, Kerala, India",
        "latitude": 8.8932,
        "longitude": 76.6141,
    },
    "hyderabad": {
        "place_label": "Hyderabad, Telangana, India",
        "latitude": 17.3850,
        "longitude": 78.4867,
    },
    "bangalore": {
        "place_label": "Bengaluru, Karnataka, India",
        "latitude": 12.9716,
        "longitude": 77.5946,
    },
    "bengaluru": {
        "place_label": "Bengaluru, Karnataka, India",
        "latitude": 12.9716,
        "longitude": 77.5946,
    },
    "tiruchirappalli": {
        "place_label": "Tiruchirappalli, Tamil Nadu, India",
        "latitude": 10.7905,
        "longitude": 78.7047,
    },
    "trichy": {
        "place_label": "Tiruchirappalli, Tamil Nadu, India",
        "latitude": 10.7905,
        "longitude": 78.7047,
    },
    "jaipur": {
        "place_label": "Jaipur, Rajasthan, India",
        "latitude": 26.9124,
        "longitude": 75.7873,
    },
}


def _google_geocode_api_key() -> str:
    return os.getenv("GOOGLE_MAPS_API_KEY", "").strip()


def _google_places_api_key() -> str:
    """Places autocomplete/details key; falls back to GOOGLE_MAPS_API_KEY if unset."""
    return (
        os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
        or _google_geocode_api_key()
    )


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


def _india_ist_offset(latitude: float, longitude: float) -> float | None:
    """India uses IST (UTC+5:30) nationwide — avoid heavy timezone DB on small servers."""
    if 6.0 <= latitude <= 37.5 and 68.0 <= longitude <= 97.5:
        return 5.5
    return None


def _timezone_offset_hours(latitude: float, longitude: float) -> float | None:
    ist = _india_ist_offset(latitude, longitude)
    if ist is not None:
        return ist
    try:
        from timezonefinder import TimezoneFinder

        tz_name = TimezoneFinder().timezone_at(lat=latitude, lng=longitude)
        if not tz_name:
            return None
        tz = pytz.timezone(tz_name)
        offset = tz.utcoffset(datetime.utcnow())
        if offset is None:
            return None
        return offset.total_seconds() / 3600.0
    except Exception:
        return None


def _http_get_json(url: str) -> Any:
    try:
        resp = requests.get(
            url,
            headers=_HTTP_HEADERS,
            timeout=20,
            verify=certifi.where(),
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.SSLError:
        return _curl_json(url)
    except requests.RequestException as exc:
        raise GeocodeError(str(exc)) from exc


def _curl_json(url: str) -> Any:
    proc = subprocess.run(
        ["curl", "-sS", "-A", "pyjhora-api/1.0", url],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    if proc.returncode != 0:
        raise GeocodeError(proc.stderr.strip() or f"curl failed with code {proc.returncode}")
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GeocodeError(f"Invalid JSON from geocoder: {exc}") from exc


def _certifi_adapter_factory(*, proxies, ssl_context):
    ctx = ssl.create_default_context(cafile=certifi.where())
    return RequestsAdapter(proxies=proxies, ssl_context=ctx)


def _result_payload(query: str, location: _GeoResult, provider: str) -> dict[str, object]:
    tz_offset = _timezone_offset_hours(location.latitude, location.longitude)
    return {
        "query": query,
        "place_label": location.address,
        "latitude": round(location.latitude, 6),
        "longitude": round(location.longitude, 6),
        "timezone_offset_hours": tz_offset,
        "provider": provider,
    }


def _geocode_with_google(query: str, api_key: str) -> _GeoResult | None:
    try:
        geocoder = GoogleV3(
            api_key=api_key,
            timeout=10,
            adapter_factory=_certifi_adapter_factory,
        )
        for candidate in (query, f"{query}, India"):
            location = geocoder.geocode(candidate, region="in")
            if location:
                return _GeoResult(
                    latitude=float(location.latitude),
                    longitude=float(location.longitude),
                    address=location.address or candidate,
                )
    except (GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable):
        pass
    return _geocode_with_google_http(query, api_key)


def _geocode_with_google_http(query: str, api_key: str) -> _GeoResult | None:
    for candidate in (query, f"{query}, India"):
        params = urllib.parse.urlencode({"address": candidate, "key": api_key, "region": "in"})
        url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
        payload = _http_get_json(url)
        if payload.get("status") == "OK" and payload.get("results"):
            item = payload["results"][0]
            loc = item["geometry"]["location"]
            return _GeoResult(
                latitude=float(loc["lat"]),
                longitude=float(loc["lng"]),
                address=item.get("formatted_address") or candidate,
            )
        if payload.get("status") not in ("ZERO_RESULTS",):
            msg = payload.get("error_message") or payload.get("status")
            raise GeocodeError(f"Google Geocoding error: {msg}")
    return None


def _geocode_with_nominatim(query: str) -> _GeoResult | None:
    try:
        return _geocode_with_nominatim_geopy(query)
    except GeocoderUnavailable as exc:
        if "SSL" not in str(exc) and "CERTIFICATE" not in str(exc):
            raise
    return _geocode_with_nominatim_http(query)


def _geocode_with_nominatim_geopy(query: str) -> _GeoResult | None:
    geocoder = Nominatim(
        user_agent="pyjhora-api/1.0",
        timeout=10,
        adapter_factory=_certifi_adapter_factory,
    )
    for candidate in (query, f"{query}, India"):
        location = geocoder.geocode(candidate, country_codes="in", addressdetails=True)
        if location:
            return _GeoResult(
                latitude=float(location.latitude),
                longitude=float(location.longitude),
                address=location.address or candidate,
            )
    location = geocoder.geocode(query, addressdetails=True)
    if location:
        return _GeoResult(
            latitude=float(location.latitude),
            longitude=float(location.longitude),
            address=location.address or query,
        )
    return None


def _geocode_with_nominatim_http(query: str) -> _GeoResult | None:
    for candidate in (query, f"{query}, India"):
        params = urllib.parse.urlencode(
            {
                "q": candidate,
                "format": "json",
                "limit": 1,
                "countrycodes": "in",
                "addressdetails": "1",
            }
        )
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        items = _http_get_json(url)
        if isinstance(items, list) and items:
            item = items[0]
            return _GeoResult(
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                address=item.get("display_name") or candidate,
            )
    return None


def geocode_location(query: str) -> dict[str, object]:
    text = query.strip()
    if not text:
        raise GeocodeError("location is required")

    known = _lookup_known_place(text)
    if known is not None:
        return known

    google_key = _google_geocode_api_key()
    provider = "nominatim"
    try:
        if google_key:
            location = _geocode_with_google(text, google_key)
            provider = "google"
        else:
            location = _geocode_with_nominatim(text)
    except (GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable) as exc:
        raise GeocodeError(f"Geocoding service error: {exc}") from exc

    if location is None:
        raise GeocodeError(f"Could not find coordinates for {text!r}")

    return _result_payload(text, location, provider)


def geocode_place_id(place_id: str) -> dict[str, object]:
    place_id = place_id.strip()
    if not place_id:
        raise GeocodeError("place_id is required")

    api_key = _google_places_api_key()
    if not api_key:
        raise GeocodeError(
            "GOOGLE_PLACES_API_KEY (or GOOGLE_MAPS_API_KEY) is required for place lookup"
        )

    params = urllib.parse.urlencode(
        {
            "place_id": place_id,
            "fields": "geometry,formatted_address",
            "key": api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/place/details/json?{params}"
    payload = _http_get_json(url)
    if payload.get("status") != "OK" or not payload.get("result"):
        msg = payload.get("error_message") or payload.get("status")
        raise GeocodeError(f"Google Place Details error: {msg}")

    result = payload["result"]
    loc = result["geometry"]["location"]
    location = _GeoResult(
        latitude=float(loc["lat"]),
        longitude=float(loc["lng"]),
        address=result.get("formatted_address") or place_id,
    )
    return _result_payload(place_id, location, "google-places")


def places_autocomplete(query: str) -> list[dict[str, str]]:
    text = query.strip()
    if not text:
        raise GeocodeError("input is required")

    api_key = _google_places_api_key()
    if not api_key:
        raise GeocodeError(
            "GOOGLE_PLACES_API_KEY (or GOOGLE_MAPS_API_KEY) is required for autocomplete. "
            "Enable Places API in Google Cloud Console."
        )

    params = urllib.parse.urlencode(
        {
            "input": text,
            "components": "country:in",
            "key": api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?{params}"
    payload = _http_get_json(url)
    status = payload.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        msg = payload.get("error_message") or status
        raise GeocodeError(f"Google Places Autocomplete error: {msg}")

    return [
        {"place_id": item["place_id"], "description": item["description"]}
        for item in payload.get("predictions", [])
    ]
