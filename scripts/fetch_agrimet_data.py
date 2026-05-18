from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import requests

from core.location_resolver import resolve_agrimet_location


TARGET_LOCATIONS = {
    "corvallis": {"display_name": "Corvallis", "file_prefix": "corvallis"},
    "hood river": {"display_name": "Hood River", "file_prefix": "hood_river"},
    "klamath falls": {"display_name": "Klamath Falls", "file_prefix": "klamath_falls"},
    "ontario": {"display_name": "Ontario", "file_prefix": "ontario"},
    "pendleton": {"display_name": "Pendleton", "file_prefix": "pendleton"},
}

YEARS = range(2015, 2026)
REQUEST_TIMEOUT_SECONDS = 40
REQUEST_DELAY_SECONDS = 2


def resolve_station_for_year(location: str, year: int) -> Dict[str, Any] | None:
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    resolution = resolve_agrimet_location(location, start_date=start_date, end_date=end_date, local_only=False)
    if not resolution or resolution.get("valid_for_requested_range") is False:
        return None
    return resolution


def fetch_station_data(station_id: str, year: int) -> pd.DataFrame | None:
    params = {
        "list": f"{station_id} mx, {station_id} mn, {station_id} pc, {station_id} sr, {station_id} ws",
        "start": f"{year}-01-01",
        "end": f"{year}-12-31",
        "format": "csv",
    }
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    try:
        response = requests.get(
            "https://www.usbr.gov/pn-bin/daily.pl",
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        print(f"Connection failed for {station_id} {year}: {exc}")
        return None

    if "DateTime" not in response.text:
        print(f"Invalid CSV payload for {station_id} {year}.")
        return None

    frame = pd.read_csv(io.StringIO(response.text))
    frame.columns = [col.replace(f"{station_id}_", "").strip() for col in frame.columns]
    frame = frame.rename(
        columns={
            "DateTime": "date",
            "mx": "max_temp_f",
            "mn": "min_temp_f",
            "pc": "cum_precip_in",
            "sr": "solar_langley",
            "ws": "wind_speed_mph",
        }
    )
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).reset_index(drop=True)
    return frame


def derive_daily_precip(frame: pd.DataFrame) -> tuple[pd.Series, int]:
    cumulative = pd.to_numeric(frame["cum_precip_in"], errors="coerce")
    delta = cumulative.diff()
    dates = pd.to_datetime(frame["date"], errors="coerce")
    water_year_reset = (dates.dt.month == 10) & (dates.dt.day == 1)
    anomaly_mask = delta.lt(0) & ~water_year_reset.fillna(False)

    daily = delta.astype("float64")
    if not cumulative.empty:
        daily.iloc[0] = cumulative.iloc[0]
    reset_mask = water_year_reset.fillna(False) & delta.lt(0)
    daily = daily.where(~reset_mask, cumulative)
    daily = daily.where(~anomaly_mask, pd.NA)
    daily = daily.round(2)
    return daily, int(anomaly_mask.sum())


def sensor_coverage(frame: pd.DataFrame) -> Dict[str, int]:
    return {
        "temperature_rows": int(frame[["max_temp_f", "min_temp_f"]].dropna(how="all").shape[0]),
        "solar_rows": int(pd.to_numeric(frame["solar_langley"], errors="coerce").notna().sum()),
        "wind_rows": int(pd.to_numeric(frame["wind_speed_mph"], errors="coerce").notna().sum()),
        "precip_rows": int(pd.to_numeric(frame["cum_precip_in"], errors="coerce").notna().sum()),
    }


def validate_station_frame(frame: pd.DataFrame, year: int) -> tuple[bool, str]:
    expected_days = 366 if year % 4 == 0 else 365
    if len(frame) < expected_days * 0.9:
        return False, f"incomplete data ({len(frame)}/{expected_days} days)"

    temp_range = pd.to_numeric(frame["max_temp_f"], errors="coerce").max() - pd.to_numeric(frame["min_temp_f"], errors="coerce").min()
    if pd.notna(temp_range) and float(temp_range) < 10:
        return False, f"suspicious temperature range ({temp_range:.1f}F)"

    coverage = sensor_coverage(frame)
    if coverage["solar_rows"] == 0:
        return False, "missing solar sensor coverage"
    if coverage["wind_rows"] == 0:
        return False, "missing wind sensor coverage"
    return True, ""


def build_station_metadata(location: str, year: int, resolution: Dict[str, Any], frame: pd.DataFrame, precip_anomaly_count: int) -> Dict[str, Any]:
    coverage = sensor_coverage(frame)
    return {
        "requested_location": location,
        "file_prefix": TARGET_LOCATIONS[location]["file_prefix"],
        "year": year,
        "source_station_id": resolution.get("station_id"),
        "source_station_title": resolution.get("station_title"),
        "station_install_date": resolution.get("station_install_date"),
        "station_resolution_mode": resolution.get("station_resolution_mode"),
        "valid_for_requested_range": resolution.get("valid_for_requested_range"),
        "row_count": int(len(frame)),
        "sensor_coverage": coverage,
        "precip_anomaly_count": precip_anomaly_count,
    }


def write_outputs(output_dir: Path, location: str, year: int, frame: pd.DataFrame, metadata: Dict[str, Any]) -> Path:
    file_prefix = TARGET_LOCATIONS[location]["file_prefix"]
    csv_path = output_dir / f"{file_prefix}_weather_{year}.csv"
    meta_path = output_dir / f"{file_prefix}_weather_{year}.meta.json"
    frame.to_csv(csv_path, index=False)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return csv_path


def main() -> None:
    output_dir = Path("data") / "agrimet"
    output_dir.mkdir(parents=True, exist_ok=True)

    total_fetches = len(TARGET_LOCATIONS) * len(YEARS)
    current = 0
    saved_files: list[Path] = []
    failures: list[str] = []

    print(f"\n{'=' * 70}")
    print(f"Fetching data for {len(TARGET_LOCATIONS)} locations across {len(YEARS)} years ({total_fetches} total fetches)")
    print(f"{'=' * 70}\n")

    for year in YEARS:
        print(f"\n--- Year {year} ---")
        for location, info in TARGET_LOCATIONS.items():
            current += 1
            display_name = info["display_name"]
            print(f"[{current}/{total_fetches}] Resolving {display_name} for {year}...")

            resolution = resolve_station_for_year(location, year)
            if not resolution:
                failures.append(f"{display_name} {year}: no valid station for requested range")
                print(f"Skipping {display_name} {year}: no active station matched this range.")
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            station_id = str(resolution.get("station_id") or "").lower()
            station_title = resolution.get("station_title") or station_id
            print(f"Fetching {year} data for {display_name} via {station_title} ({station_id})...")

            frame = fetch_station_data(station_id, year)
            if frame is None or frame.empty:
                failures.append(f"{display_name} {year}: fetch failed for {station_id}")
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            frame["daily_precip_in"], precip_anomaly_count = derive_daily_precip(frame)
            frame["location"] = display_name

            is_valid, reason = validate_station_frame(frame, year)
            if not is_valid:
                failures.append(f"{display_name} {year}: {reason}")
                print(f"Skipping {display_name} {year}: {reason}")
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            metadata = build_station_metadata(location, year, resolution, frame, precip_anomaly_count)
            csv_path = write_outputs(output_dir, location, year, frame, metadata)
            saved_files.append(csv_path)
            print(
                f"Saved {csv_path.name} ({len(frame)} rows, station={station_id}, "
                f"wind_rows={metadata['sensor_coverage']['wind_rows']}, precip_anomalies={precip_anomaly_count})"
            )
            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Saved files: {len(saved_files)}")
    if failures:
        print(f"Failures: {len(failures)}")
        for failure in failures[:20]:
            print(f" - {failure}")


if __name__ == "__main__":
    main()
