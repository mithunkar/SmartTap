from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_METADATA_PATH = DATA_DIR / "agrimet_stations_full_metadata.csv"
FALLBACK_METADATA_PATH = DATA_DIR / "agrimet_stations_full_metadata_pilot1_subset_v2_county.csv"

_DF: Optional[pd.DataFrame] = None


COLUMN_ALIASES = {
    "station_id": ["station_id", "prop_siteid", "siteid", "site_id"],
    "title": ["title", "prop_title", "station_name", "name"],
    "state": ["state", "prop_state"],
    "nearest_city": ["nearest_city", "Nearest_City_1", "city", "nearest_city_1"],
    "nearest_city_2": ["nearest_city_2", "Nearest_City_2"],
    "county": ["county", "county_name", "County"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng"],
}


def _pick_first_existing(df: pd.DataFrame, candidates: List[str]) -> str | None:
    for name in candidates:
        if name in df.columns:
            return name
    return None


def _metadata_path() -> Path:
    if DEFAULT_METADATA_PATH.exists():
        return DEFAULT_METADATA_PATH
    return FALLBACK_METADATA_PATH


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    text = " ".join(text.split())
    if text.endswith(", or"):
        text = text[:-4].strip()
    return text


def _clean_city(value: object) -> str:
    text = _normalize_text(value)
    if text.endswith(", or"):
        text = text[:-4].strip()
    if text.endswith(" or"):
        text = text[:-3].strip()
    return text


def load_agrimet_station_metadata() -> pd.DataFrame:
    global _DF
    if _DF is not None:
        return _DF

    path = _metadata_path()
    if not path.exists():
        raise FileNotFoundError(
            "AgriMet station metadata file not found. Expected one of: "
            f"{DEFAULT_METADATA_PATH} or {FALLBACK_METADATA_PATH}"
        )

    raw = pd.read_csv(path).fillna("")
    normalized: Dict[str, pd.Series] = {}
    for canonical, options in COLUMN_ALIASES.items():
        found = _pick_first_existing(raw, options)
        normalized[canonical] = raw[found] if found else pd.Series([""] * len(raw))

    df = pd.DataFrame(normalized)
    df["station_id"] = df["station_id"].map(_normalize_text)
    df["title"] = df["title"].map(_normalize_text)
    df["state"] = df["state"].map(_normalize_text)
    df["nearest_city"] = df["nearest_city"].map(_clean_city)
    df["nearest_city_2"] = df["nearest_city_2"].map(_clean_city)
    df["county"] = df["county"].map(_normalize_text)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    # Keep Oregon stations by default when state info exists.
    if (df["state"] != "").any():
        df = df[(df["state"] == "or") | (df["state"] == "")].copy()

    df = df.drop_duplicates(subset=["station_id"]).reset_index(drop=True)
    _DF = df
    return _DF


def supported_agrimet_locations() -> List[str]:
    df = load_agrimet_station_metadata()
    values = set(df["nearest_city"]) | set(df["county"]) | set(df["station_id"])
    values = {value for value in values if value}
    return sorted(values)


def is_supported_agrimet_location(location: str) -> bool:
    if not location:
        return False
    df = load_agrimet_station_metadata()
    loc = _normalize_text(location)
    county_loc = loc[:-7].strip() if loc.endswith(" county") else loc

    mask = (
        (df["station_id"] == loc)
        | (df["nearest_city"] == loc)
        | (df["nearest_city_2"] == loc)
        | (df["county"] == loc)
        | (df["county"] == county_loc)
        | (df["title"].str.contains(loc, na=False))
    )
    return bool(mask.any())


def find_station_record(location: str) -> Optional[dict]:
    if not location:
        return None
    df = load_agrimet_station_metadata()
    loc = _normalize_text(location)

    checks = [
        df[df["station_id"] == loc],
        df[df["nearest_city"] == loc],
        df[df["nearest_city_2"] == loc],
        df[df["county"] == (loc[:-7].strip() if loc.endswith(" county") else loc)],
        df[df["title"].str.contains(loc, na=False)],
    ]
    for match in checks:
        if not match.empty:
            return match.iloc[0].to_dict()
    return None


def resolve_location_to_station_id(location: str) -> Optional[str]:
    record = find_station_record(location)
    if not record:
        return None
    return str(record.get("station_id") or "") or None


def find_stations_for_county(county: str) -> List[str]:
    if not county:
        return []
    df = load_agrimet_station_metadata()
    normalized = _normalize_text(county)
    if normalized.endswith(" county"):
        normalized = normalized[:-7].strip()
    matches = df[df["county"] == normalized]["station_id"].dropna().astype(str)
    return sorted({value for value in matches if value})


def find_local_file_prefixes(location: str) -> List[str]:
    """
    Return likely local CSV prefixes for a location.
    Existing local files are named like corvallis_weather_2025.csv, while the
    metadata station IDs are codes like crvo or abro. We therefore try city/title
    based prefixes first for local disk lookup.
    """
    record = find_station_record(location)
    if not record:
        return []

    prefixes: List[str] = []
    nearest_city = _normalize_text(record.get("nearest_city", ""))
    title = _normalize_text(record.get("title", ""))
    station_id = _normalize_text(record.get("station_id", ""))

    if nearest_city:
        prefixes.append(nearest_city.replace(" ", "_"))
    if title:
        title_prefix = title.split(" agrimet")[0].strip().replace(",", "").replace(" ", "_")
        prefixes.append(title_prefix)
    if station_id:
        prefixes.append(station_id)

    seen = set()
    ordered: List[str] = []
    for prefix in prefixes:
        cleaned = "_".join(part for part in prefix.split("_") if part)
        if cleaned and cleaned not in seen:
            ordered.append(cleaned)
            seen.add(cleaned)
    return ordered
