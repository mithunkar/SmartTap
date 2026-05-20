from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, List, Optional, TypedDict

import pandas as pd

from .agrimet_station_loader import (
    LOCAL_FILE_PREFIX_OVERRIDES,
    find_station_record,
    load_agrimet_station_metadata,
    supported_agrimet_locations as _loader_supported_locations,
)
from .openet_store import OpenETParquetStore


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
    station_install_date: str
    valid_for_requested_range: bool


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
    try:
        return OpenETParquetStore().city_rows()
    except (FileNotFoundError, ValueError):
        return pd.DataFrame(columns=["County", "Latitude", "Longitude", "city_name"])


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


def _requested_start_timestamp(start_date: str | None, end_date: str | None) -> pd.Timestamp | None:
    if start_date:
        return pd.to_datetime(start_date, errors="coerce")
    if end_date:
        return pd.to_datetime(end_date, errors="coerce")
    return None


def _row_install_timestamp(row: Dict[str, object]) -> pd.Timestamp | None:
    install_date = row.get("install_date")
    if isinstance(install_date, pd.Timestamp):
        return install_date if pd.notna(install_date) else None
    parsed = pd.to_datetime(install_date, errors="coerce")
    return parsed if pd.notna(parsed) else None


def _row_valid_for_requested_range(
    row: Dict[str, object],
    *,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    requested_start = _requested_start_timestamp(start_date, end_date)
    if requested_start is None or pd.isna(requested_start):
        return True
    install_date = _row_install_timestamp(row)
    if install_date is None:
        return True
    return install_date <= requested_start


def _resolution_sort_key(item: AgrimetLocationResolution) -> tuple[float, int, int, str]:
    return (
        0 if item.get("valid_for_requested_range", True) else 1,
        float(item.get("distance_km") or 0.0),
        0 if item.get("supported_local") else 1,
        str(item.get("station_id") or ""),
    )


def _candidate_identity(item: AgrimetLocationResolution) -> tuple[str]:
    return (str(item.get("station_id") or ""),)


def _metadata_resolution(
    row: Dict[str, object],
    *,
    canonical_location: str,
    display_name: str,
    station_resolution_mode: str,
    start_date: str | None = None,
    end_date: str | None = None,
    distance_km: float | None = None,
) -> AgrimetLocationResolution:
    site_id = normalize_location_text(row.get("station_id", ""))
    local_location = _canonical_local_location(site_id)
    supported_local = local_location is not None
    if local_location:
        canonical_location = local_location
    install_ts = _row_install_timestamp(row)

    resolution: AgrimetLocationResolution = {
        "canonical_location": canonical_location,
        "display_location": display_name,
        "station_id": str(row.get("station_id", "") or ""),
        "station_title": str(row.get("title", "") or "").title(),
        "county_name": normalize_location_text(row.get("county", "")),
        "match_type": "station_metadata",
        "station_resolution_mode": station_resolution_mode,
        "supported_local": supported_local,
        "station_install_date": install_ts.strftime("%Y-%m-%d") if install_ts is not None else "",
        "valid_for_requested_range": _row_valid_for_requested_range(row, start_date=start_date, end_date=end_date),
    }
    if distance_km is not None:
        resolution["distance_km"] = round(float(distance_km), 2)
    return resolution


def _direct_metadata_match(
    location: str,
    display_name: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> AgrimetLocationResolution | None:
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
                    start_date=start_date,
                    end_date=end_date,
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
                    start_date=start_date,
                    end_date=end_date,
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
                    start_date=start_date,
                    end_date=end_date,
                )
            )

    if not matches:
        return None

    matches.sort(key=_resolution_sort_key)
    return matches[0]


def _nearest_station_resolution(
    *,
    canonical_location: str,
    display_name: str,
    latitude: float,
    longitude: float,
    county_name: str = "",
    station_resolution_mode: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> AgrimetLocationResolution | None:
    candidates: List[AgrimetLocationResolution] = []

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
            start_date=start_date,
            end_date=end_date,
            distance_km=distance_km,
        )
        if county_name and not resolution.get("county_name"):
            resolution["county_name"] = county_name
        candidates.append(resolution)

    if not candidates:
        return None

    candidates.sort(key=_resolution_sort_key)
    return candidates[0]


def _city_centroid_resolution(
    location: str,
    display_name: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> AgrimetLocationResolution | None:
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
        start_date=start_date,
        end_date=end_date,
    )
    return resolution


def _county_fallback_resolution(
    location: str,
    display_name: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> AgrimetLocationResolution | None:
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

    best = sorted(
        county_matches,
        key=lambda row: (
            0 if _row_valid_for_requested_range(row, start_date=start_date, end_date=end_date) else 1,
            normalize_location_text(row.get("station_id", "")),
        ),
    )[0]
    return _metadata_resolution(
        best,
        canonical_location=normalize_location_text(location),
        display_name=display_name,
        station_resolution_mode="county_fallback",
        start_date=start_date,
        end_date=end_date,
    )


def resolve_agrimet_candidates(
    location: str,
    *,
    local_only: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[AgrimetLocationResolution]:
    display_name = display_location_name(location)
    raw_candidates = [
        _direct_metadata_match(location, display_name, start_date=start_date, end_date=end_date),
        _city_centroid_resolution(location, display_name, start_date=start_date, end_date=end_date),
        _county_fallback_resolution(location, display_name, start_date=start_date, end_date=end_date),
    ]

    deduped: Dict[tuple[str, str], AgrimetLocationResolution] = {}
    for candidate in raw_candidates:
        if candidate is None:
            continue
        if local_only and not candidate.get("supported_local"):
            continue
        identity = _candidate_identity(candidate)
        previous = deduped.get(identity)
        if previous is None or _resolution_sort_key(candidate) < _resolution_sort_key(previous):
            deduped[identity] = candidate

    candidates = sorted(deduped.values(), key=_resolution_sort_key)
    if candidates:
        return candidates

    fallback_candidates = []
    for candidate in raw_candidates:
        if candidate is None:
            continue
        if local_only and not candidate.get("supported_local"):
            fallback_candidates.append(candidate)
            continue
        fallback_candidates.append(candidate)

    deduped_fallback: Dict[tuple[str, str], AgrimetLocationResolution] = {}
    for candidate in fallback_candidates:
        identity = _candidate_identity(candidate)
        previous = deduped_fallback.get(identity)
        if previous is None or _resolution_sort_key(candidate) < _resolution_sort_key(previous):
            deduped_fallback[identity] = candidate
    return sorted(deduped_fallback.values(), key=_resolution_sort_key)


def resolve_agrimet_location(
    location: str,
    *,
    local_only: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> AgrimetLocationResolution | None:
    candidates = resolve_agrimet_candidates(
        location,
        local_only=local_only,
        start_date=start_date,
        end_date=end_date,
    )
    if candidates:
        return candidates[0]

    return None
