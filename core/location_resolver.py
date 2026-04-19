from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, TypedDict

from .agrimet_api import LOCATION_ALIASES


BASE_DIR = Path(__file__).resolve().parent.parent
AGRIMET_METADATA_PATH = BASE_DIR / "data" / "agrimet_stations_full_metadata.csv"
AGRIMET_FRIENDLY_NAMES = {
    "corvallis": "corvallis",
    "hood river": "hood_river",
    "klamath falls": "klamath_falls",
    "ontario": "ontario",
    "pendleton": "pendleton",
}
LOCAL_AGRIMET_ALIASES = {
    name: alias for name, alias in LOCATION_ALIASES.items() if name in AGRIMET_FRIENDLY_NAMES
}


class AgrimetLocationResolution(TypedDict, total=False):
    canonical_location: str
    display_location: str
    station_id: str
    station_title: str
    county_name: str
    match_type: str
    supported_local: bool


def supported_agrimet_locations() -> List[str]:
    return sorted(AGRIMET_FRIENDLY_NAMES.keys())


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


@lru_cache(maxsize=1)
def _load_agrimet_station_metadata() -> List[Dict[str, str]]:
    if not AGRIMET_METADATA_PATH.exists():
        return []

    with AGRIMET_METADATA_PATH.open(newline="", encoding="utf-8") as handle:
        return [{key: str(value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def resolve_agrimet_location(location: str, *, local_only: bool = False) -> AgrimetLocationResolution | None:
    normalized = normalize_location_text(location)
    county_normalized = strip_county_suffix(location)
    display_name = display_location_name(location)

    if normalized in AGRIMET_FRIENDLY_NAMES:
        return {
            "canonical_location": normalized,
            "display_location": display_name,
            "station_id": LOCAL_AGRIMET_ALIASES.get(normalized, ""),
            "match_type": "friendly_name",
            "supported_local": True,
        }

    metadata_rows = _load_agrimet_station_metadata()
    local_rows: List[AgrimetLocationResolution] = []
    fallback_rows: List[AgrimetLocationResolution] = []
    for row in metadata_rows:
        site_id = normalize_location_text(row.get("prop_siteid", ""))
        title = normalize_location_text(row.get("prop_title", ""))
        county = normalize_location_text(row.get("county_name", ""))
        city_1 = strip_county_suffix(row.get("Nearest_City_1", "").split(",")[0])
        city_2 = strip_county_suffix(row.get("Nearest_City_2", "").split(",")[0])

        canonical_location = ""
        supported_local = site_id in LOCAL_AGRIMET_ALIASES.values()
        if supported_local:
            canonical_location = next(name for name, alias in LOCAL_AGRIMET_ALIASES.items() if alias == site_id)
        else:
            for candidate in supported_agrimet_locations():
                if candidate in {title, city_1, city_2} or candidate in title:
                    canonical_location = candidate
                    supported_local = True
                    break

        matches_query = normalized in {site_id, title, city_1, city_2} or county_normalized == county
        if not matches_query:
            continue

        enriched: AgrimetLocationResolution = {
            "canonical_location": canonical_location or normalized,
            "display_location": display_name,
            "station_id": row.get("prop_siteid", ""),
            "station_title": row.get("prop_title", ""),
            "county_name": row.get("county_name", ""),
            "match_type": "county" if county_normalized == county else "station_metadata",
            "supported_local": supported_local,
        }
        if supported_local:
            local_rows.append(enriched)
        fallback_rows.append(enriched)

    if local_rows:
        return local_rows[0]
    if local_only:
        if fallback_rows:
            fallback = dict(fallback_rows[0])
            fallback["supported_local"] = False
            return fallback
        return None
    if fallback_rows:
        return fallback_rows[0]
    return None
