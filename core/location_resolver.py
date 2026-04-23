from __future__ import annotations

from pathlib import Path
from typing import List, TypedDict

from .agrimet_station_loader import (
    find_local_file_prefixes,
    find_station_record,
    supported_agrimet_locations as _loader_supported_locations,
)


BASE_DIR = Path(__file__).resolve().parent.parent


class AgrimetLocationResolution(TypedDict, total=False):
    canonical_location: str
    display_location: str
    station_id: str
    station_title: str
    county_name: str
    match_type: str
    supported_local: bool


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


def resolve_agrimet_location(location: str, *, local_only: bool = False) -> AgrimetLocationResolution | None:
    normalized = normalize_location_text(location)
    display_name = display_location_name(location)

    record = find_station_record(normalized)
    if not record:
        return None

    station_id = str(record.get("station_id") or "")
    # A location is considered "supported locally" if the loader can derive
    # at least one likely file prefix (i.e. a matching CSV exists on disk).
    prefixes = find_local_file_prefixes(normalized)
    supported_local = bool(prefixes)

    resolution: AgrimetLocationResolution = {
        "canonical_location": record.get("nearest_city") or station_id,
        "display_location": display_name,
        "station_id": station_id,
        "station_title": record.get("title", ""),
        "county_name": record.get("county", ""),
        "match_type": "station_metadata",
        "supported_local": supported_local,
    }

    if local_only and not supported_local:
        resolution["supported_local"] = False

    return resolution