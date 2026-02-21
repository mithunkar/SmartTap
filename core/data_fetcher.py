"""
Data Fetcher Module for SmartTap
Loads pre-downloaded data from local CSV files (AgriMet) and OpenET (Field/HUC).
Produces a unified payload format:
  {"spec": spec, "data": {"records": [ {"datetime": ..., <var1>: ..., <var2>: ...}, ... ]}}

Extended to support location-based OpenET queries:
  - Query by city: "Show ETa for fields in Corvallis"
  - Query by county: "What is PPT for Benton County fields"
  - Optional crop filter: "ETa for wheat fields in Hood River"
"""

import os
import glob
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
from .location_crop_query import LocationCropQuery


# -------------------------
# Base directories
# -------------------------

# base data directory
DATA_DIR = Path(__file__).parent.parent / "data"

# recommended structure:
# data/
#   agrimet/
#   openet/
AGRIMET_DIR = DATA_DIR / "agrimet"
OPENET_DIR = DATA_DIR / "openet"

# OpenET combined long tables (created in your Step 3 & Step 5)
OPENET_FIELD_COMBINED = OPENET_DIR / "field_combined_long.csv"
OPENET_HUC_COMBINED = OPENET_DIR / "huc_combined_long.csv"


# -------------------------
# AgriMet configuration
# -------------------------

# location name to file prefix mapping (matches your saved file names)
LOCATION_PREFIXES = {
    "corvallis": "corvallis_weather",
    "pendleton": "pendleton_weather",
    "hood river": "hood_river_weather",
    "klamath falls": "klamath_falls_weather",
    "ontario": "ontario_weather",
}


def _require_file(path: Path, hint: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}\n{hint}")


def _pivot_long_to_wide(
    df: pd.DataFrame,
    time_col: str,
    var_col: str,
    value_col: str,
) -> pd.DataFrame:
    """
    Convert long format -> wide timeseries:
      datetime | var1 | var2 | ...
    """
    wide = (
        df.pivot_table(index=time_col, columns=var_col, values=value_col, aggfunc="mean")
        .reset_index()
        .sort_values(time_col)
    )
    return wide


def _apply_interval(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """
    Aggregate to monthly/yearly if asked. Assumes df has a datetime column.
    """
    interval = (interval or "daily").lower()

    if interval == "daily":
        return df

    if interval == "monthly":
        df = df.copy()
        df["__m"] = pd.to_datetime(df["datetime"]).dt.to_period("M")
        agg_cols = [c for c in df.columns if c not in {"datetime", "__m"}]
        df = df.groupby("__m")[agg_cols].mean().reset_index()
        df["datetime"] = df["__m"].dt.to_timestamp()
        df = df.drop(columns=["__m"]).sort_values("datetime")
        return df

    if interval == "yearly":
        df = df.copy()
        df["__y"] = pd.to_datetime(df["datetime"]).dt.year
        agg_cols = [c for c in df.columns if c not in {"datetime", "__y"}]
        df = df.groupby("__y")[agg_cols].mean().reset_index()
        df["datetime"] = pd.to_datetime(df["__y"].astype(str) + "-01-01")
        df = df.drop(columns=["__y"]).sort_values("datetime")
        return df

    if interval == "hourly":
        # your agrimet files are daily; openet is monthly/yearly. Don’t upsample.
        print("Requested hourly, but local data is not hourly. Returning native resolution.")
        return df

    print(f"Unknown interval '{interval}', returning native resolution.")
    return df


# -------------------------
# AgriMet loading
# -------------------------

def get_data_files_for_range(location: str, start_date: str, end_date: str) -> List[Path]:
    """
    Get list of CSV files needed to cover the date range.

    We support both:
      - old layout: data/<prefix>_<year>.csv
      - new layout: data/agrimet/<prefix>_<year>.csv
    """
    loc = (location or "").lower().strip()
    if loc not in LOCATION_PREFIXES:
        available_locs = ", ".join(sorted(LOCATION_PREFIXES.keys()))
        raise ValueError(f"Unknown AgriMet location: '{location}'. Available: {available_locs}")

    start_year = int(start_date.split("-")[0]) if start_date else 2015
    end_year = int(end_date.split("-")[0]) if end_date else 2025

    prefix = LOCATION_PREFIXES[loc]
    files: List[Path] = []

    for year in range(start_year, end_year + 1):
        # Prefer data/agrimet/...
        p1 = AGRIMET_DIR / f"{prefix}_{year}.csv"
        # Backward compatible: data/...
        p2 = DATA_DIR / f"{prefix}_{year}.csv"

        if p1.exists():
            files.append(p1)
        elif p2.exists():
            files.append(p2)

    return files


def fetch_agrimet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load AgriMet weather data from local yearly CSV files.
    Returns payload in SmartTap format (datetime + requested variables).
    """
    location = (spec.get("location", "corvallis") or "corvallis").lower().strip()
    variables = spec.get("variables", []) or []
    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    interval = spec.get("interval", "daily")

    csv_files = get_data_files_for_range(location, start_date, end_date)
    if not csv_files:
        raise FileNotFoundError(
            f"No AgriMet files found for {location} in range {start_date}..{end_date}. "
            f"Expected files like: {LOCATION_PREFIXES.get(location,'<prefix>')}_YYYY.csv in data/agrimet/ or data/."
        )

    print(f"Loading AgriMet data from {len(csv_files)} file(s) for {location}...")

    dfs = []
    for csv_file in csv_files:
        df_year = pd.read_csv(csv_file)
        if "date" not in df_year.columns:
            raise ValueError(f"AgriMet file missing 'date' column: {csv_file}")
        df_year["date"] = pd.to_datetime(df_year["date"], errors="coerce")
        df_year = df_year.dropna(subset=["date"])
        dfs.append(df_year)

    df = pd.concat(dfs, ignore_index=True).sort_values("date").reset_index(drop=True)

    # filter by date range
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    if df.empty:
        raise ValueError(f"No AgriMet data found for date range {start_date}..{end_date}")

    # rename date -> datetime
    df = df.rename(columns={"date": "datetime"})

    # build result frame
    result_df = pd.DataFrame({"datetime": df["datetime"]})

    # map SmartTap variable codes -> your CSV columns/transforms
    # (same logic you already had)
    for var in variables:
        if var == "OBM":
            # avg temp F
            if "max_temp_f" not in df.columns or "min_temp_f" not in df.columns:
                raise ValueError("AgriMet CSV missing max_temp_f/min_temp_f for OBM.")
            result_df["OBM"] = ((df["max_temp_f"] + df["min_temp_f"]) / 2).round(2)

        elif var == "MX":
            if "max_temp_f" not in df.columns:
                raise ValueError("AgriMet CSV missing max_temp_f for MX.")
            result_df["MX"] = df["max_temp_f"].round(2)

        elif var == "MN":
            if "min_temp_f" not in df.columns:
                raise ValueError("AgriMet CSV missing min_temp_f for MN.")
            result_df["MN"] = df["min_temp_f"].round(2)

        elif var == "PC":
            # precip in mm (from inches)
            if "daily_precip_in" not in df.columns:
                raise ValueError("AgriMet CSV missing daily_precip_in for PC.")
            result_df["PC"] = (df["daily_precip_in"] * 25.4).round(2)

        elif var == "SR":
            if "solar_langley" not in df.columns:
                raise ValueError("AgriMet CSV missing solar_langley for SR.")
            result_df["SR"] = df["solar_langley"].round(2)

        elif var == "WS":
            if "wind_speed_mph" not in df.columns:
                raise ValueError("AgriMet CSV missing wind_speed_mph for WS.")
            result_df["WS"] = df["wind_speed_mph"].round(2)

        elif var == "TU":
            print("TU (Humidity) not available in local data, skipping")

        else:
            print(f"Variable {var} not recognized for AgriMet.")

    # fail fast if requested variables missing
    requested = variables or []
    present = set(result_df.columns) - {"datetime"}
    missing = [v for v in requested if v not in present and v != "TU"]
    if missing:
        raise ValueError(
            f"Requested variables missing from local AgriMet data: {missing}. "
            f"Present: {sorted(present)}"
        )

    # interval aggregation
    result_df["datetime"] = pd.to_datetime(result_df["datetime"])
    result_df = _apply_interval(result_df, interval)

    records = result_df.to_dict(orient="records")
    print(f"Loaded {len(records)} AgriMet records")

    return {"spec": spec, "data": {"records": records}}


# -------------------------
# OpenET loading (FIELD + HUC)
# -------------------------

# Optional aliasing so users can say "eta" and we map to "ETa" etc.
OPENET_ALIASES = {
    "eta": "ETa",
    "et": "ETa",
    "ppt": "PPT",
    "precip": "PPT",
    "precipitation": "PPT",
    "aw": "AW",
    "ws": "WS_C",
    "wsc": "WS_C",
}


def _normalize_openet_vars(vars_in: List[str]) -> List[str]:
    out = []
    for v in vars_in or []:
        if not isinstance(v, str):
            continue
        key = v.strip()
        mapped = OPENET_ALIASES.get(key.lower(), key)
        out.append(mapped)
    return out


def fetch_openet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load OpenET data from local combined-long CSVs and return records usable by visualizer:
      records = [{"datetime": ..., "ETa": ..., "PPT": ...}, ...]
      
    spec fields supported:
      - openet_geo: "field" | "location" | "huc8" | "huc12"   (default "huc8")
      - openet_id (field) OR huc8_code/huc12_code (huc)
      - location: city or county name (for location-based queries)
      - location_type: "city" or "county" (optional, auto-detected)
      - crop_filter: crop name to filter fields (optional)
      - aggregation: "mean", "sum", "median" (for multi-field queries)
      - variables: list of metric/variable names (optional)
      - start_date, end_date (optional)
      - interval: "monthly" | "yearly" | "daily" (daily will just return native)
    """
    geo = (spec.get("openet_geo") or "huc8").lower().strip()
    variables = _normalize_openet_vars(spec.get("variables") or spec.get("metrics") or [])
    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    interval = spec.get("interval", "monthly")

    if geo not in {"field", "location", "huc8", "huc12"}:
        raise ValueError(f"openet_geo must be one of field/location/huc8/huc12, got: {geo}")

    # -------------------
    # LOCATION (city/county-based field queries)
    # -------------------
    if geo == "location" or (geo == "field" and spec.get("location")):
        location = spec.get("location")
        if not location:
            raise ValueError("location-based query requires 'location' field (city or county name)")
        
        location_type = spec.get("location_type", "city").lower()
        crop_filter = spec.get("crop_filter")
        aggregation = spec.get("aggregation", "mean")
        
        if not variables:
            raise ValueError("location-based query requires at least one variable (ETa, PPT, AW, etc.)")
        
        # Use full Oregon geopackage path
        full_oregon_gpkg = DATA_DIR / "preliminary_or_field_geopackage.gpkg"
        
        # Initialize query system
        query_system = LocationCropQuery(full_oregon_gpkg=str(full_oregon_gpkg))
        
        # Query each variable and combine results
        all_results = {}  # Changed to dict to track which variable each result is for
        for variable in variables:
            print(f"\nQuerying {variable} for {location} ({location_type})...")
            
            if location_type == "city":
                df_var = query_system.query_variable_by_city(
                    city_name=location,
                    variable=variable,
                    start_date=start_date or "2020-01-01",
                    end_date=end_date or "2024-12-31",
                    crop_filter=crop_filter,
                    aggregation=aggregation
                )
            elif location_type == "county":
                df_var = query_system.query_variable_by_county(
                    county_name=location,
                    variable=variable,
                    start_date=start_date or "2020-01-01",
                    end_date=end_date or "2024-12-31",
                    crop_filter=crop_filter,
                    aggregation=aggregation
                )
            else:
                raise ValueError(f"location_type must be 'city' or 'county', got: {location_type}")
            
            if df_var.empty:
                print(f"Warning: No data for {variable}")
                continue
                
            all_results[variable] = df_var
        
        if not all_results:
            if location_type == "city":
                raise ValueError(
                    f"No OpenET data found for '{location}'. This city may not exist in Oregon, "
                    f"or there may be no agricultural fields near this location. "
                    f"Try: Corvallis, Hood River, Klamath Falls, Hermiston, Pendleton, etc."
                )
            else:
                raise ValueError(
                    f"No OpenET data found for '{location}' County. This county may not exist in Oregon, "
                    f"or there may be no agricultural fields in this county. "
                    f"Try: Benton, Marion, Klamath, Hood River, Umatilla, Malheur, etc."
                )
        
        # Merge all variables on datetime
        first_var = list(all_results.keys())[0]
        wide = all_results[first_var][['datetime', first_var]].copy()
        
        for var in list(all_results.keys())[1:]:
            wide = wide.merge(
                all_results[var][['datetime', var]],
                on='datetime',
                how='outer'
            )
        
        wide = wide.sort_values('datetime').reset_index(drop=True)

    # -------------------
    # FIELD
    # -------------------
    elif geo == "field":
        _require_file(
            OPENET_FIELD_COMBINED,
            "Create it by running: python combine_openet_field.py (expects field_long_out/*_field_long.csv first).",
        )
        df = pd.read_csv(OPENET_FIELD_COMBINED)

        if "datetime" not in df.columns:
            raise ValueError("field_combined_long.csv must contain a 'datetime' column (from your reshaper).")

        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])

        # filter by OPENET_ID if provided
        openet_id = spec.get("openet_id") or spec.get("OPENET_ID")
        if openet_id and "OPENET_ID" in df.columns:
            df = df[df["OPENET_ID"].astype(str) == str(openet_id)]

        # filter date range
        if start_date:
            df = df[df["datetime"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["datetime"] <= pd.to_datetime(end_date)]

        # field long uses column "variable"
        if variables:
            if "variable" not in df.columns:
                raise ValueError("field_combined_long.csv must contain 'variable' and 'value' columns.")
            df = df[df["variable"].isin(variables)]

        if df.empty:
            raise ValueError("No OpenET FIELD data after filters (openet_id/variables/date range).")

        wide = _pivot_long_to_wide(df, time_col="datetime", var_col="variable", value_col="value")

    # -------------------
    # HUC8 / HUC12
    # -------------------
    else:
        _require_file(
            OPENET_HUC_COMBINED,
            "Create it by running: python combine_openet_huc.py (expects openet_exports/*_long.csv first).",
        )
        df = pd.read_csv(OPENET_HUC_COMBINED)

        # Ensure datetime column exists
        if "datetime" not in df.columns:
            if "year" in df.columns:
                df["month"] = pd.to_numeric(df.get("month", 1), errors="coerce").fillna(1).astype(int)
                df["year"] = pd.to_numeric(df["year"], errors="coerce").astype(int)
                df["datetime"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1), errors="coerce")
            else:
                raise ValueError("huc_combined_long.csv missing datetime and year/month columns.")

        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])

        # filter by HUC code
        if geo == "huc8":
            code = spec.get("huc8_code") or spec.get("HUC8_code") or spec.get("HUC8")
            if code:
                col = "HUC8_code" if "HUC8_code" in df.columns else "HUC8"
                if col in df.columns:
                    df = df[df[col].astype(str) == str(code)]
        else:
            code = spec.get("huc12_code") or spec.get("HUC12_code") or spec.get("HUC12")
            if code:
                col = "HUC12_code" if "HUC12_code" in df.columns else "HUC12"
                if col in df.columns:
                    df = df[df[col].astype(str) == str(code)]

        # filter date range
        if start_date:
            df = df[df["datetime"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["datetime"] <= pd.to_datetime(end_date)]

        # huc long uses column "metric"
        if variables:
            if "metric" not in df.columns:
                raise ValueError("huc_combined_long.csv must contain 'metric' and 'value' columns.")
            df = df[df["metric"].isin(variables)]

        if df.empty:
            raise ValueError("No OpenET HUC data after filters (huc code/variables/date range).")

        wide = _pivot_long_to_wide(df, time_col="datetime", var_col="metric", value_col="value")

    # interval aggregation
    wide["datetime"] = pd.to_datetime(wide["datetime"])
    wide = _apply_interval(wide, interval)

    records = wide.to_dict(orient="records")
    print(f"Loaded {len(records)} OpenET records ({geo})")

    return {"spec": spec, "data": {"records": records}}


# -------------------------
# Router
# -------------------------

def fetch_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main data fetching function that routes to appropriate data source.
    """
    if spec.get("task") == "error":
        raise ValueError(f"Error in spec: {spec.get('error_message')}")

    dataset = (spec.get("dataset") or "agrimet").lower().strip()

    if dataset == "openet":
        return fetch_openet_data(spec)
    if dataset == "agrimet":
        return fetch_agrimet_data(spec)

    raise ValueError(f"Unknown dataset: {dataset}")


# -------------------------
# Quick tests
# -------------------------

if __name__ == "__main__":
    # 1) AgriMet test (make sure you have matching files in data/agrimet/ or data/)
    test_agrimet = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "location": "corvallis",
        "variables": ["OBM", "PC"],
        "start_date": "2015-07-01",
        "end_date": "2015-07-10",
        "interval": "daily",
        "chart_type": "line",
    }

    print("\n--- Testing AgriMet ---")
    payload = fetch_data(test_agrimet)
    print(f"AgriMet records: {len(payload['data']['records'])}")
    print("Sample:", payload["data"]["records"][0])

    # 2) OpenET FIELD test (requires data/openet/field_combined_long.csv)
    # Replace openet_id with a real one you have.
    test_openet_field = {
        "task": "visualize_timeseries",
        "dataset": "openet",
        "openet_geo": "field",
        "openet_id": "ORx_158886",
        "variables": ["ETa", "PPT"],
        "start_date": "2018-01-01",
        "end_date": "2020-12-31",
        "interval": "monthly",
        "chart_type": "line",
    }

    print("\n--- Testing OpenET FIELD ---")
    try:
        payload = fetch_data(test_openet_field)
        print(f"OpenET FIELD records: {len(payload['data']['records'])}")
        print("Sample:", payload["data"]["records"][0])
    except Exception as e:
        print("OpenET FIELD test skipped / failed:", e)

    # 3) OpenET HUC test (requires data/openet/huc_combined_long.csv)
    # Replace huc8_code with a real one you have.
    test_openet_huc = {
        "task": "visualize_timeseries",
        "dataset": "openet",
        "openet_geo": "huc8",
        "huc8_code": "18010204",
        "variables": ["ET_r", "PPT_r"],
        "start_date": "2005-01-01",
        "end_date": "2020-12-31",
        "interval": "yearly",
        "chart_type": "line",
    }

    print("\n--- Testing OpenET HUC8 ---")
    try:
        payload = fetch_data(test_openet_huc)
        print(f"OpenET HUC records: {len(payload['data']['records'])}")
        print("Sample:", payload["data"]["records"][0])
    except Exception as e:
        print("OpenET HUC test skipped / failed:", e)
