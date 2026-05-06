from __future__ import annotations

import math
import sqlite3
from functools import lru_cache
from typing import Dict, List, TypedDict

import pandas as pd

from .agrimet_station_loader import (
    LOCAL_FILE_PREFIX_OVERRIDES,
    find_station_record,
    load_agrimet_station_metadata,
    supported_agrimet_locations as _loader_supported_locations,
)
from .paths import FIELD_POINTS_GPKG


FIELD_POINTS_PATH = FIELD_POINTS_GPKG


class AgrimetLocationResolution(TypedDict, total=False):
    canonical_location: str
    display_location: str
    station_id: str
    station_title: str
    county_name: str
    match_type: str
    station_resolution_mode: str
    supported_local: bool
    distance_km: float


def supported_agrimet_locations() -> List[str]:
    """Return all known AgriMet locations from the full station metadata CSV."""
    return _loader_supported_locations()


def normalize_location_text(location: str) -> str:
    cleaned = str(location or "").strip().lower().replace("_", " ")
    return " ".join(cleaned.split())


def strip_county_suffix(location: str) -> str:
    normalized = normalize_location_text(location)
    if normalized.endswith(" county"):
        return normalized[: -len(" county")].strip()
    return normalized


def display_location_name(location: str, location_type: str | None = None) -> str:
    normalized = normalize_location_text(location)
    if not normalized:
        return ""

    resolved_type = str(location_type or "").lower().strip()
    if resolved_type == "county" or normalized.endswith(" county"):
        base = strip_county_suffix(normalized)
        return f"{base.title()} County"
    return normalized.title()


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return 6371.0 * c


@lru_cache(maxsize=1)
def _metadata_rows() -> List[Dict[str, object]]:
    return load_agrimet_station_metadata().to_dict("records")


@lru_cache(maxsize=1)
def _field_point_city_rows() -> pd.DataFrame:
    if not FIELD_POINTS_PATH.exists():
        return pd.DataFrame(columns=["County", "Latitude", "Longitude", "city_name"])

    conn = sqlite3.connect(FIELD_POINTS_PATH)
    try:
        query = """
        SELECT County, Latitude, Longitude, Nearest_City_1 AS city_name
        FROM field_points
        WHERE Nearest_City_1 IS NOT NULL AND Nearest_City_1 != ''
        UNION ALL
        SELECT County, Latitude, Longitude, Nearest_City_2 AS city_name
        FROM field_points
        WHERE Nearest_City_2 IS NOT NULL AND Nearest_City_2 != ''
        """
        rows = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    if rows.empty:
        return rows

    rows["city_name"] = rows["city_name"].astype(str).str.split(",").str[0].map(normalize_location_text)
    rows["County"] = rows["County"].astype(str).map(normalize_location_text)
    rows["Latitude"] = pd.to_numeric(rows["Latitude"], errors="coerce")
    rows["Longitude"] = pd.to_numeric(rows["Longitude"], errors="coerce")
    return rows.dropna(subset=["Latitude", "Longitude"])


def _field_point_city_profile(location: str) -> Dict[str, str | float] | None:
    city_rows = _field_point_city_rows()
    normalized = strip_county_suffix(location)
    if city_rows.empty or not normalized:
        return None

    matches = city_rows[city_rows["city_name"] == normalized]
    if matches.empty:
        return None

    county_mode = matches["County"].mode()
    county_name = str(county_mode.iloc[0]).strip() if not county_mode.empty else ""
    return {
        "city_name": normalized,
        "county_name": county_name,
        "latitude": float(matches["Latitude"].mean()),
        "longitude": float(matches["Longitude"].mean()),
    }


def _metadata_city_name(row: Dict[str, object], key: str) -> str:
    raw = str(row.get(key, "") or "")
    return strip_county_suffix(raw.split(",")[0])


def _canonical_local_location(station_id: str) -> str | None:
    prefix = LOCAL_FILE_PREFIX_OVERRIDES.get(station_id)
    if not prefix:
        return None
    return normalize_location_text(prefix)


def _metadata_resolution(
    row: Dict[str, object],
    *,
    canonical_location: str,
    display_name: str,
    station_resolution_mode: str,
    distance_km: float | None = None,
) -> AgrimetLocationResolution:
    site_id = normalize_location_text(row.get("station_id", ""))
    local_location = _canonical_local_location(site_id)
    supported_local = local_location is not None
    if local_location:
        canonical_location = local_location

    resolution: AgrimetLocationResolution = {
        "canonical_location": canonical_location,
        "display_location": display_name,
        "station_id": str(row.get("station_id", "") or ""),
        "station_title": str(row.get("title", "") or "").title(),
        "county_name": normalize_location_text(row.get("county", "")),
        "match_type": "station_metadata",
        "station_resolution_mode": station_resolution_mode,
        "supported_local": supported_local,
    }
    if distance_km is not None:
        resolution["distance_km"] = round(float(distance_km), 2)
    return resolution


def _direct_metadata_match(location: str, display_name: str) -> AgrimetLocationResolution | None:
    normalized = normalize_location_text(location)
    county_normalized = strip_county_suffix(location)
    matches: List[AgrimetLocationResolution] = []

    for row in _metadata_rows():
        site_id = normalize_location_text(row.get("station_id", ""))
        title = normalize_location_text(row.get("title", ""))
        county = normalize_location_text(row.get("county", ""))
        city_1 = _metadata_city_name(row, "nearest_city")
        city_2 = _metadata_city_name(row, "nearest_city_2")

        if normalized == site_id or normalized == title:
            matches.append(
                _metadata_resolution(
                    row,
                    canonical_location=normalized,
                    display_name=display_name,
                    station_resolution_mode="exact",
                )
            )
            continue

        if normalized in {city_1, city_2}:
            matches.append(
                _metadata_resolution(
                    row,
                    canonical_location=normalized,
                    display_name=display_name,
                    station_resolution_mode="nearest_city",
                )
            )
            continue

        if county_normalized and county_normalized == county:
            matches.append(
                _metadata_resolution(
                    row,
                    canonical_location=normalized,
                    display_name=display_name,
                    station_resolution_mode="county_fallback",
                )
            )

    if not matches:
        return None

    matches.sort(
        key=lambda item: (
            0 if item.get("supported_local") else 1,
            str(item.get("station_id") or ""),
        )
    )
    return matches[0]


def _nearest_station_resolution(
    *,
    canonical_location: str,
    display_name: str,
    latitude: float,
    longitude: float,
    county_name: str = "",
    station_resolution_mode: str,
) -> AgrimetLocationResolution | None:
    best_resolution: AgrimetLocationResolution | None = None
    best_distance: float | None = None

    for row in _metadata_rows():
        try:
            station_lat = float(row.get("latitude", "") or "")
            station_lon = float(row.get("longitude", "") or "")
        except (TypeError, ValueError):
            continue

        distance_km = _haversine_distance_km(latitude, longitude, station_lat, station_lon)
        resolution = _metadata_resolution(
            row,
            canonical_location=canonical_location,
            display_name=display_name,
            station_resolution_mode=station_resolution_mode,
            distance_km=distance_km,
        )
        if county_name and not resolution.get("county_name"):
            resolution["county_name"] = county_name

        if best_resolution is None or best_distance is None:
            best_resolution = resolution
            best_distance = distance_km
            continue

        if distance_km < best_distance - 1e-9:
            best_resolution = resolution
            best_distance = distance_km
            continue

        if abs(distance_km - best_distance) <= 1e-9 and str(resolution.get("station_id") or "") < str(best_resolution.get("station_id") or ""):
            best_resolution = resolution
            best_distance = distance_km

    return best_resolution


def _city_centroid_resolution(location: str, display_name: str) -> AgrimetLocationResolution | None:
    profile = _field_point_city_profile(location)
    if not profile:
        return None

    resolution = _nearest_station_resolution(
        canonical_location=normalize_location_text(location),
        display_name=display_name,
        latitude=float(profile["latitude"]),
        longitude=float(profile["longitude"]),
        county_name=str(profile.get("county_name") or ""),
        station_resolution_mode="centroid_nearest_station",
    )
    return resolution


def _county_fallback_resolution(location: str, display_name: str) -> AgrimetLocationResolution | None:
    county_name = strip_county_suffix(location)
    if not county_name:
        profile = _field_point_city_profile(location)
        county_name = normalize_location_text((profile or {}).get("county_name", ""))
    if not county_name:
        return None

    county_matches = [
        row
        for row in _metadata_rows()
        if normalize_location_text(row.get("county", "")) == normalize_location_text(county_name)
    ]
    if not county_matches:
        return None

    best = sorted(county_matches, key=lambda row: normalize_location_text(row.get("station_id", "")))[0]
    return _metadata_resolution(
        best,
        canonical_location=normalize_location_text(location),
        display_name=display_name,
        station_resolution_mode="county_fallback",
    )


def resolve_agrimet_location(location: str, *, local_only: bool = False) -> AgrimetLocationResolution | None:
    display_name = display_location_name(location)
    direct = _direct_metadata_match(location, display_name)
    if direct is not None:
        if local_only and direct.get("supported_local"):
            return direct
        if not local_only or not direct.get("supported_local"):
            return direct

    centroid = _city_centroid_resolution(location, display_name)
    if centroid is not None:
        if local_only and centroid.get("supported_local"):
            return centroid
        if not local_only or not centroid.get("supported_local"):
            return centroid

    county_fallback = _county_fallback_resolution(location, display_name)
    if county_fallback is not None:
        if local_only and county_fallback.get("supported_local"):
            return county_fallback
        if not local_only or not county_fallback.get("supported_local"):
            return county_fallback

    if local_only:
        return direct or centroid or county_fallback
    return direct or centroid or county_fallback
