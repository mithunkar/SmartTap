from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .contracts import DatasetAdapter, DatasetContract, QuerySpec
from .agrimet_api import fetch_agrimet_api_data
from .agrimet_station_loader import find_local_file_prefixes
from .location_crop_query import LocationCropQuery
from .location_resolver import normalize_location_text, resolve_agrimet_candidates
from . import location_resolver as _location_resolver
from .paths import (
    AGRIMET_DIR,
)
from .variable_registry import (
    AGRIMET_VARIABLES,
    OPENET_VARIABLES,
    default_aggregation_for_variables,
    normalize_openet_variable,
    variable_label,
)


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
        notes="Runtime OpenET queries use normalized parquet artifacts only.",
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

    candidates = resolve_agrimet_candidates(
        location,
        local_only=False,
        start_date=str(resolved.get("start_date") or "") or None,
        end_date=str(resolved.get("end_date") or "") or None,
    )
    if candidates:
        resolved["station_candidates"] = [
            {
                "station_id": candidate.get("station_id"),
                "station_title": candidate.get("station_title"),
                "station_resolution_mode": candidate.get("station_resolution_mode"),
                "station_install_date": candidate.get("station_install_date"),
                "valid_for_requested_range": bool(candidate.get("valid_for_requested_range", True)),
                "supported_local": bool(candidate.get("supported_local", False)),
                "distance_km": candidate.get("distance_km"),
            }
            for candidate in candidates
        ]
    match = candidates[0] if candidates else None
    if not match:
        return resolved

    if match.get("display_location") and not resolved.get("display_location"):
        resolved["display_location"] = match["display_location"]
    if match.get("station_id"):
        resolved["resolved_station_id"] = match["station_id"]
    if match.get("station_id") and not resolved.get("station_id"):
        resolved["station_id"] = match["station_id"]
    if match.get("station_title"):
        resolved["resolved_station_title"] = match["station_title"]
    if match.get("station_title") and not resolved.get("station_title"):
        resolved["station_title"] = match["station_title"]
    if match.get("county_name") and not resolved.get("county_name"):
        resolved["county_name"] = match["county_name"]
    if match.get("station_resolution_mode"):
        resolved["station_resolution_mode"] = match["station_resolution_mode"]
    if "valid_for_requested_range" in match:
        resolved["valid_for_requested_range"] = bool(match.get("valid_for_requested_range", True))
    if match.get("station_install_date"):
        resolved["station_install_date"] = match["station_install_date"]
    resolved["supported_local"] = bool(match.get("supported_local", True))
    resolved["source_mode"] = "agrimet_api"

    canonical_location = match.get("canonical_location")
    if canonical_location:
        resolved["location"] = canonical_location
    resolved["fetch_mode"] = "api"
    return resolved


def _agrimet_file_prefix(location: str) -> str:
    """Offline helper for local AgriMet bundle discovery; runtime fetches are API-only."""
    normalized = normalize_location_text(location)
    prefixes = find_local_file_prefixes(normalized)

    if prefixes:
        for prefix in prefixes:
            if any(AGRIMET_DIR.glob(f"{prefix}_weather_*.csv")):
                return prefix
        return prefixes[0]

    available = ", ".join(_location_resolver.supported_agrimet_locations())
    raise ValueError(
        f"Unknown AgriMet location: '{location}'. "
        f"No matching station found in metadata. Available: {available}"
    )


def get_data_files_for_range(location: str, start_date: str, end_date: str) -> List[Path]:
    """Offline helper retained for QA utilities; runtime AgriMet reads use the API only."""
    normalized = normalize_location_text(location)
    prefixes = find_local_file_prefixes(normalized)
    if not prefixes:
        prefixes = [_agrimet_file_prefix(location)]

    start_year = int((start_date or "2015-01-01").split("-")[0])
    end_year = int((end_date or "2025-12-31").split("-")[0])

    for prefix in prefixes:
        files = [
            AGRIMET_DIR / f"{prefix}_weather_{year}.csv"
            for year in range(start_year, end_year + 1)
            if (AGRIMET_DIR / f"{prefix}_weather_{year}.csv").exists()
        ]
        if files:
            return files
    return []
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


def _agrimet_no_sensor_message(
    *,
    empty_variables: List[str],
    station_id: str,
    display_location: str,
    county_name: str | None = None,
) -> str:
    """Build a clear user-facing message when a station has no data for requested sensors."""
    from .agrimet_station_loader import find_stations_for_county
    labels = ", ".join(variable_label(v) for v in empty_variables)
    msg = (
        f"No data available for {labels} at the {display_location} station ({station_id}). "
        f"This station may not record these sensors."
    )
    if county_name:
        alternatives = [s for s in find_stations_for_county(county_name) if s != station_id]
        if alternatives:
            msg += f" Other stations in this county you could try: {', '.join(alternatives)}."
    return msg


def _agrimet_range_no_station_message(spec: Dict[str, Any]) -> str:
    display = str(spec.get("display_location") or spec.get("location") or "this location")
    labels = ", ".join(variable_label(variable) for variable in spec.get("variables", []) or []) or "requested variables"
    date_range = ""
    if spec.get("start_date") and spec.get("end_date"):
        date_range = f" for {spec['start_date']} to {spec['end_date']}"

    install_date = str(spec.get("station_install_date") or "").strip()
    station_bits = " ".join(
        value
        for value in [
            spec.get("resolved_station_title") or spec.get("station_title"),
            f"({spec.get('resolved_station_id') or spec.get('station_id')})"
            if (spec.get("resolved_station_id") or spec.get("station_id"))
            else "",
        ]
        if value
    )
    message = f"No AgriMet station active near {display} could serve {labels}{date_range}."
    if station_bits and install_date:
        message += f" Closest candidate: {station_bits}, installed {install_date}."
    elif station_bits:
        message += f" Closest candidate: {station_bits}."
    return message




def _sensor_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([float("nan")] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _build_agrimet_result_frame(
    df: pd.DataFrame,
    variables: List[str],
    spec: Dict[str, Any] | None = None,
) -> pd.DataFrame:
    result = pd.DataFrame({"datetime": df["datetime"]})
    empty_variables: List[str] = []

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
        elif variable in {"TU", "AVG_HUM"}:
            result[variable] = _sensor_series(df, "rh").round(2)
        elif variable in {"ET", "PEN_ET"}:
            result[variable] = _sensor_series(df, "et").round(2)
        elif variable == "Kc":
            result[variable] = _sensor_series(df, "kc").round(3)
        else:
            raise ValueError(f"Unsupported AgriMet variable: {variable}")

        # Track variables that came back entirely empty (all None/NaN)
        if variable in result.columns:
            col = result[variable]
            is_empty = (
                col.isna().all()
                if not pd.api.types.is_numeric_dtype(col)
                else col.dropna().empty
            )
            if is_empty:
                empty_variables.append(variable)

    # ALL variables empty — raise a clear, user-facing error
    if empty_variables and len(empty_variables) == len(variables):
        station_id = str((spec or {}).get("station_id") or "unknown")
        display_location = str(
            (spec or {}).get("display_location")
            or (spec or {}).get("location")
            or "this station"
        )
        county_name = str((spec or {}).get("county_name") or "") or None
        raise ValueError(
            _agrimet_no_sensor_message(
                empty_variables=empty_variables,
                station_id=station_id,
                display_location=display_location,
                county_name=county_name,
            )
        )

    # SOME variables empty — warn but continue with the ones that have data
    if empty_variables:
        labels = ", ".join(variable_label(v) for v in empty_variables)
        print(f"⚠️  Warning: No data returned for {labels} — these columns will be blank.")

    return result


def _finalize_agrimet_payload(spec: Dict[str, Any], result: pd.DataFrame) -> Dict[str, Any]:
    requested_variables = [str(value) for value in spec.get("variables", []) or []]
    nonnull_counts = {
        variable: int(result[variable].notna().sum())
        for variable in requested_variables
        if variable in result.columns
    }

    if requested_variables and all(nonnull_counts.get(variable, 0) == 0 for variable in requested_variables):
        labels = ", ".join(variable_label(variable) for variable in requested_variables)
        station_bits = " ".join(
            value
            for value in [
                spec.get("station_title"),
                f"({spec.get('station_id')})" if spec.get("station_id") else "",
            ]
            if value
        )
        date_range = f"{spec.get('start_date')} to {spec.get('end_date')}" if spec.get("start_date") and spec.get("end_date") else ""
        message = f"No usable AgriMet values were available for {labels}"
        if station_bits:
            message += f" at {station_bits}"
        elif spec.get("display_location") or spec.get("location"):
            message += f" near {spec.get('display_location') or spec.get('location')}"
        if date_range:
            message += f" for {date_range}"
        message += "."
        spec["no_data_reason"] = message

    return {"spec": spec, "data": {"records": result.to_dict(orient="records")}}


def _agrimet_api_no_data_message(spec: Dict[str, Any], detail: str | None = None) -> str:
    requested_variables = [str(value) for value in spec.get("variables", []) or []]
    labels = ", ".join(variable_label(variable) for variable in requested_variables) or "requested AgriMet variables"
    station_bits = " ".join(
        value
        for value in [
            spec.get("station_title"),
            f"({spec.get('station_id')})" if spec.get("station_id") else "",
        ]
        if value
    )
    date_range = f"{spec.get('start_date')} to {spec.get('end_date')}" if spec.get("start_date") and spec.get("end_date") else ""

    message = f"No AgriMet API data was available for {labels}"
    if station_bits:
        message += f" at {station_bits}"
    elif spec.get("display_location") or spec.get("location"):
        message += f" near {spec.get('display_location') or spec.get('location')}"
    if date_range:
        message += f" for {date_range}"
    if detail:
        message += f". API detail: {detail}"
    else:
        message += "."
    return message


def _apply_api_candidate(spec: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(spec)
    station_id = str(candidate.get("station_id") or "").strip()
    station_title = str(candidate.get("station_title") or "").strip()
    if station_id:
        updated["station_id"] = station_id
        updated["data_station_id"] = station_id
    if station_title:
        updated["station_title"] = station_title
        updated["data_station_title"] = station_title
    if candidate.get("station_install_date"):
        updated["data_station_install_date"] = str(candidate.get("station_install_date"))
    updated["valid_for_requested_range"] = bool(candidate.get("valid_for_requested_range", True))
    if station_id and updated.get("resolved_station_id") and updated.get("resolved_station_id") != station_id:
        notes = list(updated.get("notes") or [])
        notes.append(
            f"Closest AgriMet candidate {updated.get('resolved_station_id')} returned no API data; using {station_id} instead."
        )
        updated["notes"] = notes
    return updated


def _fetch_agrimet_from_api(spec: Dict[str, Any]) -> Dict[str, Any]:
    spec = _normalize_agrimet_spec(spec)
    spec["source_mode"] = "agrimet_api"
    if spec.get("valid_for_requested_range") is False:
        spec["no_data_reason"] = _agrimet_range_no_station_message(spec)
        return {"spec": spec, "data": {"records": []}}
    display = spec.get("display_location") or spec.get("location") or "this location"
    candidate_specs = [
        dict(candidate)
        for candidate in spec.get("station_candidates", []) or []
        if bool(candidate.get("valid_for_requested_range", True))
    ]
    if not candidate_specs:
        candidate_specs = [
            {
                "station_id": spec.get("station_id"),
                "station_title": spec.get("station_title"),
                "station_install_date": spec.get("station_install_date"),
                "valid_for_requested_range": True,
            }
        ]

    api_errors: List[str] = []
    tried: List[str] = []
    for candidate in candidate_specs:
        station_id = str(candidate.get("station_id") or spec.get("station_id") or spec.get("location") or "corvallis").lower()
        candidate_spec = _apply_api_candidate(spec, candidate)
        tried.append(station_id)
        try:
            df = fetch_agrimet_api_data(
                location=station_id,
                variables=spec.get("variables", []) or [],
                start_date=spec.get("start_date") or "2024-01-01",
                end_date=spec.get("end_date") or "2024-12-31",
            )
        except ValueError as exc:
            api_errors.append(f"{station_id}: {exc}")
            continue

        if df.empty:
            api_errors.append(f"{station_id}: No AgriMet data returned from API for {display}.")
            continue

        candidate_spec["api_station_candidates_tried"] = tried
        candidate_spec["source_mode"] = "agrimet_api"
        candidate_spec["fetch_mode"] = "api"
        if "datetime" not in df.columns and "date" in df.columns:
            df = df.rename(columns={"date": "datetime"})
        elif "datetime" in df.columns and "date" in df.columns:
            df = df.drop(columns=["date"])
        result = _build_agrimet_result_frame(df, spec.get("variables", []) or [], candidate_spec)
        result = _apply_interval(result, spec.get("interval", "daily"))
        return _finalize_agrimet_payload(candidate_spec, result)

    spec["api_station_candidates_tried"] = tried
    detail = None
    if api_errors:
        detail = api_errors[-1].split(": ", 1)[-1]
        if len(tried) > 1:
            detail = f"Tried stations {', '.join(tried)}. Last detail: {detail}"
    spec["no_data_reason"] = _agrimet_api_no_data_message(spec, detail)
    return {"spec": spec, "data": {"records": []}}


def fetch_agrimet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    return _fetch_agrimet_from_api(spec)


def fetch_openet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    geo = (spec.get("openet_geo") or "location").lower().strip()
    variables = _normalize_openet_vars(spec.get("variables") or [])
    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    interval = spec.get("interval", "monthly")
    spec = dict(spec)
    spec["source_mode"] = "openet_parquet"

    if geo in {"location", "field"} and spec.get("location"):
        location = spec.get("location")
        location_type = (spec.get("location_type") or "city").lower()
        crop_filter = spec.get("crop_filter")
        aggregation = spec.get("aggregation") or default_aggregation_for_variables(variables)
        query_system = LocationCropQuery()

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
            spec["no_data_reason"] = _openet_no_data_message(
                location=str(location),
                location_type=location_type,
                crop_filter=str(crop_filter) if crop_filter else None,
                start_date=str(start_date) if start_date else None,
                end_date=str(end_date) if end_date else None,
                reason=next((value for value in no_data_reasons if value), None),
            )
            return {"spec": spec, "data": {"records": []}}

        names = list(results)
        wide = results[names[0]]
        for variable in names[1:]:
            wide = wide.merge(results[variable], on="datetime", how="outer")
        wide = wide.sort_values("datetime").reset_index(drop=True)
        wide = _apply_interval(wide, interval)
        return {"spec": spec, "data": {"records": wide.to_dict(orient="records")}}
    raise ValueError(
        "Runtime OpenET queries require a city or county location and use the parquet runtime store only. "
        "Legacy field/HUC CSV routes are disabled."
    )


def fetch_openet_grouped_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    spec = dict(spec)
    spec["source_mode"] = "openet_parquet"
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

    query_system = LocationCropQuery()
    frame = query_system.query_grouped_variables_by_location(
        location=str(location),
        location_type=location_type,
        compare_by=compare_by,
        variables=value_variables,
        start_date=spec.get("start_date") or "2024-01-01",
        end_date=spec.get("end_date") or "2024-12-31",
        crop_filter=spec.get("crop_filter"),
        aggregation=spec.get("aggregation") or default_aggregation_for_variables(value_variables),
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
