import os
import re
import argparse
from typing import List, Tuple, Optional

import pandas as pd
import geopandas as gpd
import fiona


# -------------------------
# Helpers: time column parse
# -------------------------

YEAR2_RE = re.compile(r"^(?P<metric>.+)_(?P<yy>\d{2})$")            # e.g., ET_v_85
YYYYMM_RE = re.compile(r"^(?P<metric>.+)_(?P<yyyy>\d{4})(?P<mm>\d{2})$")  # e.g., ET_v_201905
YYYY_MM_RE = re.compile(r"^(?P<metric>.+)_(?P<yyyy>\d{4})_(?P<mm>\d{2})$") # e.g., ET_v_2019_05
YYYY_DASH_MM_RE = re.compile(r"^(?P<metric>.+)_(?P<yyyy>\d{4})-(?P<mm>\d{2})$") # e.g., ET_v_2019-05


def yy_to_year(yy: int, pivot: int = 24) -> int:
    """
    Convert 2-digit year into full year.
    pivot=24 means 00-24 -> 2000-2024, else -> 1900s.
    """
    return 2000 + yy if yy <= pivot else 1900 + yy


def classify_time_columns(columns: List[str]) -> Tuple[List[str], List[str]]:
    """
    Returns (time_value_cols, non_time_cols)
    time_value_cols are those we can parse as a time-series column.
    """
    time_cols = []
    non_time = []
    for c in columns:
        if YEAR2_RE.match(c) or YYYYMM_RE.match(c) or YYYY_MM_RE.match(c) or YYYY_DASH_MM_RE.match(c):
            time_cols.append(c)
        else:
            non_time.append(c)
    return time_cols, non_time


def parse_time_col(col: str) -> Optional[Tuple[str, int, Optional[int]]]:
    """
    Parse a time-encoded column name into (metric, year, month).
    Returns None if not parseable.
    """
    m = YEAR2_RE.match(col)
    if m:
        metric = m.group("metric")
        year = yy_to_year(int(m.group("yy")))
        return (metric, year, None)

    m = YYYYMM_RE.match(col)
    if m:
        metric = m.group("metric")
        year = int(m.group("yyyy"))
        month = int(m.group("mm"))
        return (metric, year, month)

    m = YYYY_MM_RE.match(col)
    if m:
        metric = m.group("metric")
        year = int(m.group("yyyy"))
        month = int(m.group("mm"))
        return (metric, year, month)

    m = YYYY_DASH_MM_RE.match(col)
    if m:
        metric = m.group("metric")
        year = int(m.group("yyyy"))
        month = int(m.group("mm"))
        return (metric, year, month)

    return None


def reshape_wide_to_long(df: pd.DataFrame, layer_name: str) -> Optional[pd.DataFrame]:
    """
    If df has parseable time columns, convert from wide to long format:
    id_cols + [year, month?] + metric + value
    Returns None if no time columns found.
    """
    cols = list(df.columns)
    time_cols, id_cols = classify_time_columns(cols)

    if not time_cols:
        return None

    # Build long rows efficiently
    long_parts = []
    for c in time_cols:
        parsed = parse_time_col(c)
        if not parsed:
            continue
        metric, year, month = parsed

        part = df[id_cols + [c]].copy()
        part["metric"] = metric
        part["year"] = year
        part["month"] = month  # None for yearly columns
        part = part.rename(columns={c: "value"})
        long_parts.append(part)

    if not long_parts:
        return None

    out = pd.concat(long_parts, ignore_index=True)

    # Reorder columns nicely
    # Put id_cols first, then time, then metric/value
    ordered = id_cols + ["year", "month", "metric", "value"]
    out = out[ordered]

    # Add layer name (optional but useful for debugging / combined analysis)
    out.insert(0, "layer", layer_name)

    return out


# -------------------------
# Main conversion pipeline
# -------------------------

def gpkg_to_csv_and_long(gpkg_path: str, out_dir: str, pivot: int = 24) -> None:
    os.makedirs(out_dir, exist_ok=True)

    layers = fiona.listlayers(gpkg_path)
    print(f"Found {len(layers)} layers in: {gpkg_path}")

    for layer in layers:
        print("\n" + "=" * 70)
        print(f"Layer: {layer}")

        # Read
        gdf = gpd.read_file(gpkg_path, layer=layer)

        # Drop geometry for CSV
        df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))

        # Save wide CSV
        wide_path = os.path.join(out_dir, f"{layer}.csv")
        df.to_csv(wide_path, index=False)
        print(f"Saved wide CSV: {wide_path}  (rows={len(df)}, cols={len(df.columns)})")

        # Reshape if it looks like time-series wide format
        long_df = reshape_wide_to_long(df, layer_name=layer)

        if long_df is None:
            print("No parseable time-series columns found → skipping long reshape.")
            continue

        # Save long CSV
        long_path = os.path.join(out_dir, f"{layer}_long.csv")
        long_df.to_csv(long_path, index=False)
        print(f"Saved long CSV: {long_path}  (rows={len(long_df)}, cols={len(long_df.columns)})")

    print("\nDone ✅")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export all GPKG layers to CSV + reshape time columns to long CSV.")
    parser.add_argument("--gpkg", required=True, help="Path to .gpkg file")
    parser.add_argument("--out", default="openet_csv_out", help="Output directory for CSVs")
    args = parser.parse_args()

    gpkg_to_csv_and_long(args.gpkg, args.out)
