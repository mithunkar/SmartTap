from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .contracts import DatasetAdapter, DatasetContract, QuerySpec
from .agrimet_api import fetch_agrimet_api_data
from .location_crop_query import LocationCropQuery
from .location_resolver import normalize_location_text, resolve_agrimet_location, supported_agrimet_locations
from .variable_registry import AGRIMET_VARIABLES, OPENET_VARIABLES, normalize_openet_variable


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
AGRIMET_DIR = DATA_DIR / "agrimet"
FIELD_POINTS_GPKG = DATA_DIR / "field_points.gpkg"
FULL_OREGON_GPKG = DATA_DIR / "preliminary_or_field_geopackage.gpkg"
OPENET_DIR = DATA_DIR / "openet"
OPENET_FIELD_COMBINED = OPENET_DIR / "field_combined_long.csv"
OPENET_HUC_COMBINED = OPENET_DIR / "huc_combined_long.csv"
AGRIMET_FRIENDLY_NAMES = {
    "corvallis": "corvallis",
    "hood river": "hood_river",
    "klamath falls": "klamath_falls",
    "ontario": "ontario",
    "pendleton": "pendleton",
}

class AgrimetAdapter:
    contract = DatasetContract(
        name="agrimet",
        location_kinds=("city", "station"),
        default_interval="daily",
        supported_variables=tuple(sorted(AGRIMET_VARIABLES)),
        notes="AgriMet queries may require city-to-station resolution before fetch.",
    )

    def fetch(self, spec: QuerySpec) -> Dict[str, Any]:
        return fetch_agrimet_data(spec)


class OpenETAdapter:
    contract = DatasetContract(
        name="openet",
        location_kinds=("city", "county", "field"),
        default_interval="monthly",
        supported_variables=tuple(sorted(OPENET_VARIABLES)),
        notes="OpenET supports location, field, and HUC-style queries depending on spec fields.",
    )

    def fetch(self, spec: QuerySpec) -> Dict[str, Any]:
        return fetch_openet_data(spec)


DATASET_ADAPTERS: Dict[str, DatasetAdapter] = {
    "agrimet": AgrimetAdapter(),
    "openet": OpenETAdapter(),
}

SUPPORTED_OPENET_GROUP_FIELDS = {"IRR_STATUS", "ITYPE", "CROP"}


def _normalize_agrimet_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    resolved = dict(spec)
    location = str(resolved.get("location") or "").strip()
    if not location:
        return resolved

    use_api = os.getenv("AGRIMET_USE_API") == "1"
    match = resolve_agrimet_location(location, local_only=not use_api)
    if not match:
        return resolved

    if match.get("display_location") and not resolved.get("display_location"):
        resolved["display_location"] = match["display_location"]
    if match.get("station_id") and not resolved.get("station_id"):
        resolved["station_id"] = match["station_id"]
    if match.get("station_title") and not resolved.get("station_title"):
        resolved["station_title"] = match["station_title"]

    canonical_location = match.get("canonical_location")
    if canonical_location and (match.get("supported_local", True) or use_api):
        resolved["location"] = canonical_location
    return resolved


def _agrimet_file_prefix(location: str) -> str:
    normalized = normalize_location_text(location)
    if normalized in AGRIMET_FRIENDLY_NAMES:
        return AGRIMET_FRIENDLY_NAMES[normalized]
    available = ", ".join(sorted(AGRIMET_FRIENDLY_NAMES))
    raise ValueError(f"Unknown AgriMet location: '{location}'. Available: {available}")


def _require_file(path: Path, hint: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}\n{hint}")


def _apply_interval(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    interval = (interval or "daily").lower()
    if interval == "daily":
        return df

    group_cols = [col for col in df.columns if col != "datetime"]
    if interval == "monthly":
        grouped = df.assign(_period=pd.to_datetime(df["datetime"]).dt.to_period("M"))
        grouped = grouped.groupby("_period")[group_cols].mean(numeric_only=True).reset_index()
        grouped["datetime"] = grouped["_period"].dt.to_timestamp()
        return grouped.drop(columns="_period")

    if interval == "yearly":
        grouped = df.assign(_year=pd.to_datetime(df["datetime"]).dt.year)
        grouped = grouped.groupby("_year")[group_cols].mean(numeric_only=True).reset_index()
        grouped["datetime"] = pd.to_datetime(grouped["_year"].astype(str) + "-01-01")
        return grouped.drop(columns="_year")

    return df


def _normalize_openet_vars(values: List[str]) -> List[str]:
    normalized = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        normalized.append(normalize_openet_variable(value))
    return normalized


def _pivot_long_to_wide(df: pd.DataFrame, time_col: str, var_col: str, value_col: str) -> pd.DataFrame:
    return (
        df.pivot_table(index=time_col, columns=var_col, values=value_col, aggfunc="mean")
        .reset_index()
        .sort_values(time_col)
    )


def _openet_no_data_message(
    *,
    location: str,
    location_type: str,
    crop_filter: str | None,
    start_date: str | None,
    end_date: str | None,
    reason: str | None = None,
) -> str:
    place = f"near {location}" if location_type == "city" else f"in {location}"
    if start_date and end_date:
        time_part = f" for {start_date} to {end_date}"
    else:
        time_part = ""

    if reason == "no_fields":
        return f"No OpenET fields found {place}."
    if reason == "unknown_crop" and crop_filter:
        return f"No OpenET crop label matched '{crop_filter}' {place}{time_part}."
    if reason == "no_crop_fields" and crop_filter:
        return f"No OpenET fields matched crop '{crop_filter}' {place}{time_part}."
    if reason == "no_variable_rows" and crop_filter:
        return f"No OpenET variable rows were found for {crop_filter} fields {place}{time_part}."
    if crop_filter:
        return f"No OpenET data found for {crop_filter} fields {place}{time_part}."
    return f"No OpenET data found for '{location}'."


def get_data_files_for_range(location: str, start_date: str, end_date: str) -> List[Path]:
    prefix = _agrimet_file_prefix(location)
    start_year = int((start_date or "2015-01-01").split("-")[0])
    end_year = int((end_date or "2025-12-31").split("-")[0])
    files: List[Path] = []
    for year in range(start_year, end_year + 1):
        candidate = AGRIMET_DIR / f"{prefix}_weather_{year}.csv"
        if candidate.exists():
            files.append(candidate)
    return files


def _load_local_agrimet_frame(spec: Dict[str, Any]) -> pd.DataFrame:
    files = get_data_files_for_range(
        spec.get("location", ""),
        spec.get("start_date") or "2015-01-01",
        spec.get("end_date") or "2025-12-31",
    )
    if not files:
        raise FileNotFoundError(f"No AgriMet files found for {spec.get('location')}.")

    frames = [pd.read_csv(path) for path in files]
    df = pd.concat(frames, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["datetime"])

    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    if start_date:
        df = df[df["datetime"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["datetime"] <= pd.to_datetime(end_date)]
    return df.sort_values("datetime").reset_index(drop=True)


def _build_agrimet_result_frame(df: pd.DataFrame, variables: List[str]) -> pd.DataFrame:
    result = pd.DataFrame({"datetime": df["datetime"]})
    for variable in variables:
        if variable in {"OBM", "AVG_TMP"}:
            result[variable] = ((df["max_temp_f"] + df["min_temp_f"]) / 2).round(2)
        elif variable == "MX":
            result[variable] = df["max_temp_f"].round(2)
        elif variable == "MN":
            result[variable] = df["min_temp_f"].round(2)
        elif variable in {"PC", "24_HR_PCP"}:
            result[variable] = (df["daily_precip_in"] * 25.4).round(2)
        elif variable == "SR":
            result[variable] = df["solar_langley"].round(2)
        elif variable in {"WS", "AV_WSPD"}:
            result[variable] = df["wind_speed_mph"].round(2)
        elif variable in {"TU", "AVG_HUM", "ET", "PEN_ET", "Kc"}:
            result[variable] = pd.NA
        else:
            raise ValueError(f"Unsupported AgriMet variable: {variable}")
    return result


def _fetch_agrimet_from_api(spec: Dict[str, Any]) -> Dict[str, Any]:
    spec = _normalize_agrimet_spec(spec)
    df = fetch_agrimet_api_data(
        location=str(spec.get("station_id") or spec.get("location") or "corvallis").lower(),
        variables=spec.get("variables", []) or [],
        start_date=spec.get("start_date") or "2024-01-01",
        end_date=spec.get("end_date") or "2024-12-31",
    )
    if df.empty:
        raise ValueError(f"No AgriMet data returned from API for {spec.get('location')}")
    df = df.rename(columns={"date": "datetime"})
    result = _build_agrimet_result_frame(df, spec.get("variables", []) or [])
    result = _apply_interval(result, spec.get("interval", "daily"))
    return {"spec": spec, "data": {"records": result.to_dict(orient="records")}}


def fetch_agrimet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    spec = _normalize_agrimet_spec(spec)
    use_api = os.getenv("AGRIMET_USE_API") == "1"
    if use_api:
        return _fetch_agrimet_from_api(spec)

    df = _load_local_agrimet_frame(spec)
    result = _build_agrimet_result_frame(df, spec.get("variables", []) or [])
    result = _apply_interval(result, spec.get("interval", "daily"))
    return {"spec": spec, "data": {"records": result.to_dict(orient="records")}}


def fetch_openet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    geo = (spec.get("openet_geo") or "location").lower().strip()
    variables = _normalize_openet_vars(spec.get("variables") or [])
    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    interval = spec.get("interval", "monthly")

    if geo in {"location", "field"} and spec.get("location"):
        location = spec.get("location")
        location_type = (spec.get("location_type") or "city").lower()
        crop_filter = spec.get("crop_filter")
        aggregation = spec.get("aggregation", "mean")
        query_system = LocationCropQuery(full_oregon_gpkg=str(FULL_OREGON_GPKG))

        results: Dict[str, pd.DataFrame] = {}
        no_data_reasons: List[str] = []
        for variable in variables:
            if location_type == "city":
                frame, metadata = query_system.query_variable_by_city(
                    city_name=location,
                    variable=variable,
                    start_date=start_date or "2024-01-01",
                    end_date=end_date or "2024-12-31",
                    crop_filter=crop_filter,
                    aggregation=aggregation,
                    return_metadata=True,
                )
            elif location_type == "county":
                frame, metadata = query_system.query_variable_by_county(
                    county_name=location,
                    variable=variable,
                    start_date=start_date or "2024-01-01",
                    end_date=end_date or "2024-12-31",
                    crop_filter=crop_filter,
                    aggregation=aggregation,
                    return_metadata=True,
                )
            else:
                raise ValueError(f"location_type must be city or county, got {location_type}")

            if not frame.empty:
                results[variable] = frame[["datetime", variable]].copy()
            else:
                no_data_reasons.append(str(metadata.get("no_data_reason") or ""))

        if not results:
            raise ValueError(
                _openet_no_data_message(
                    location=str(location),
                    location_type=location_type,
                    crop_filter=str(crop_filter) if crop_filter else None,
                    start_date=str(start_date) if start_date else None,
                    end_date=str(end_date) if end_date else None,
                    reason=next((value for value in no_data_reasons if value), None),
                )
            )

        names = list(results)
        wide = results[names[0]]
        for variable in names[1:]:
            wide = wide.merge(results[variable], on="datetime", how="outer")
        wide = wide.sort_values("datetime").reset_index(drop=True)
        wide = _apply_interval(wide, interval)
        return {"spec": spec, "data": {"records": wide.to_dict(orient="records")}}

    if geo == "field":
        _require_file(
            OPENET_FIELD_COMBINED,
            "Create data/openet/field_combined_long.csv or use location-based OpenET queries.",
        )
        df = pd.read_csv(OPENET_FIELD_COMBINED)
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])
        if start_date:
            df = df[df["datetime"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["datetime"] <= pd.to_datetime(end_date)]
        if variables:
            df = df[df["variable"].isin(variables)]
        wide = _pivot_long_to_wide(df, "datetime", "variable", "value")
        wide = _apply_interval(wide, interval)
        return {"spec": spec, "data": {"records": wide.to_dict(orient="records")}}

    _require_file(
        OPENET_HUC_COMBINED,
        "Create data/openet/huc_combined_long.csv or use location-based OpenET queries.",
    )
    df = pd.read_csv(OPENET_HUC_COMBINED)
    if "datetime" not in df.columns and {"year", "month"}.issubset(df.columns):
        df["datetime"] = pd.to_datetime(
            dict(year=pd.to_numeric(df["year"]), month=pd.to_numeric(df["month"]), day=1),
            errors="coerce",
        )
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"])
    if start_date:
        df = df[df["datetime"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["datetime"] <= pd.to_datetime(end_date)]
    if variables:
        metric_col = "metric" if "metric" in df.columns else "variable"
        df = df[df[metric_col].isin(variables)]
        wide = _pivot_long_to_wide(df, "datetime", metric_col, "value")
    else:
        metric_col = "metric" if "metric" in df.columns else "variable"
        wide = _pivot_long_to_wide(df, "datetime", metric_col, "value")
    wide = _apply_interval(wide, interval)
    return {"spec": spec, "data": {"records": wide.to_dict(orient="records")}}


def fetch_openet_grouped_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    location = spec.get("location")
    location_type = (spec.get("location_type") or "city").lower().strip()
    compare_by = str(spec.get("compare_by") or spec.get("split_by") or "").strip()
    variables = _normalize_openet_vars(spec.get("variables") or [])
    value_variables = [value for value in variables if value != compare_by]

    if not location:
        raise ValueError("Grouped OpenET queries require a location.")
    if location_type not in {"city", "county"}:
        raise ValueError(f"Grouped OpenET queries require city/county location_type, got {location_type}.")
    if compare_by not in SUPPORTED_OPENET_GROUP_FIELDS:
        supported = ", ".join(sorted(SUPPORTED_OPENET_GROUP_FIELDS))
        raise ValueError(f"Unsupported grouped comparison field: {compare_by}. Supported: {supported}")
    if not value_variables:
        raise ValueError("Grouped OpenET queries require at least one numeric comparison variable.")

    query_system = LocationCropQuery(full_oregon_gpkg=str(FULL_OREGON_GPKG))
    frame = query_system.query_grouped_variables_by_location(
        location=str(location),
        location_type=location_type,
        compare_by=compare_by,
        variables=value_variables,
        start_date=spec.get("start_date") or "2024-01-01",
        end_date=spec.get("end_date") or "2024-12-31",
        crop_filter=spec.get("crop_filter"),
        aggregation=spec.get("aggregation", "mean"),
    )
    if frame.empty:
        raise ValueError(
            _openet_no_data_message(
                location=str(location),
                location_type=location_type,
                crop_filter=str(spec.get("crop_filter")) if spec.get("crop_filter") else None,
                start_date=str(spec.get("start_date")) if spec.get("start_date") else None,
                end_date=str(spec.get("end_date")) if spec.get("end_date") else None,
            )
        )
    return {"spec": spec, "data": {"records": frame.to_dict(orient="records")}}


def get_dataset_adapter(dataset: str) -> DatasetAdapter:
    normalized = (dataset or "agrimet").lower().strip()
    adapter = DATASET_ADAPTERS.get(normalized)
    if adapter is None:
        raise ValueError(f"Unknown dataset: {normalized}")
    return adapter


def fetch_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    dataset = (spec.get("dataset") or "agrimet").lower().strip()
    adapter = get_dataset_adapter(dataset)
    return adapter.fetch(spec)


def fetch_grouped_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    dataset = (spec.get("dataset") or "").lower().strip()
    if dataset != "openet":
        raise ValueError("Grouped comparison support is currently implemented for OpenET only.")
    return fetch_openet_grouped_data(spec)
