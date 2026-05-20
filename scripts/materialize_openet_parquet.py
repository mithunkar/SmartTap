#!/usr/bin/env python3
"""
Materialize normalized OpenET parquet artifacts for SmartTap runtime queries.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import OPENET_DIR, OPENET_SOURCE_FIELD_POINTS_GPKG, OPENET_SOURCE_FULL_OREGON_GPKG


MONTHLY_RUNTIME_VARIABLES = [
    "AW",
    "ETDa",
    "ETa",
    "IRR_CU_VOLUMEadj",
    "NIWR",
    "PPT",
    "P_rz",
    "WS_C",
]

MONTHLY_COLUMN_RE = re.compile(r"^(?P<prefix>.+)_(?P<mm>\d{2})_(?P<yy>\d{2})(?:_(?P<units>[^_]+))?$")
CROP_YEAR_RE = re.compile(r"^CROP_(?P<year>\d{4})$")
IRR_STATUS_YEAR_RE = re.compile(r"^IRR_STATUS_(?P<year>\d{4})$")
PER_IRRIGATED_YEAR_RE = re.compile(r"^per_IRRIGATED_(?P<yy>\d{2})$")


def yy_to_year(yy: int, pivot: int = 24) -> int:
    return 2000 + yy if yy <= pivot else 1900 + yy


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    info = pd.read_sql_query(f"PRAGMA table_info({table})", conn)
    return [str(value) for value in info["name"].tolist()]


def sql_select(conn: sqlite3.Connection, table: str, columns: Iterable[str]) -> pd.DataFrame:
    quoted = ", ".join(f'"{column}"' for column in columns)
    return pd.read_sql_query(f'SELECT {quoted} FROM "{table}"', conn)


def prepare_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    annual_dir = output_dir / "annual"
    monthly_dir = output_dir / "monthly"

    if annual_dir.exists():
        shutil.rmtree(annual_dir)
    if monthly_dir.exists():
        shutil.rmtree(monthly_dir)

    field_index = output_dir / "field_index.parquet"
    if field_index.exists():
        field_index.unlink()

    annual_dir.mkdir(parents=True, exist_ok=True)
    monthly_dir.mkdir(parents=True, exist_ok=True)


def materialize_field_index(field_points_gpkg: Path, output_dir: Path) -> None:
    print(f"Materializing field index from {field_points_gpkg}...")
    conn = sqlite3.connect(field_points_gpkg)
    try:
        columns = [column for column in table_columns(conn, "field_points") if column != "geom"]
        field_index = sql_select(conn, "field_points", columns)
    finally:
        conn.close()

    if "fid" in field_index.columns:
        field_index = field_index.drop(columns=["fid"])
    field_index.to_parquet(output_dir / "field_index.parquet", index=False, engine="pyarrow")
    print(f"  wrote {len(field_index):,} field rows")


def extract_year_mapping(columns: Iterable[str], pattern: re.Pattern[str], *, two_digit: bool = False) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    for column in columns:
        match = pattern.match(column)
        if not match:
            continue
        if two_digit:
            year = yy_to_year(int(match.group("yy")))
        else:
            year = int(match.group("year"))
        mapping[year] = column
    return mapping


def materialize_annual(openet_gpkg: Path, output_dir: Path) -> None:
    print(f"Materializing annual tables from {openet_gpkg}...")
    conn = sqlite3.connect(openet_gpkg)
    try:
        crop_columns = table_columns(conn, "CROP")
        irr_status_columns = table_columns(conn, "IRR_STATUS")
        per_irrigated_columns = table_columns(conn, "per_IRRIGATED")

        crop_years = extract_year_mapping(crop_columns, CROP_YEAR_RE)
        irr_status_years = extract_year_mapping(irr_status_columns, IRR_STATUS_YEAR_RE)
        per_irrigated_years = extract_year_mapping(per_irrigated_columns, PER_IRRIGATED_YEAR_RE, two_digit=True)

        static_columns = ["OPENET_ID", "ACRES_FTR_GEOM", "IRR_EFF", "ITYPE"]
        crop_df = sql_select(conn, "CROP", static_columns + [crop_years[year] for year in sorted(crop_years)])
        irr_status_df = sql_select(conn, "IRR_STATUS", ["OPENET_ID"] + [irr_status_years[year] for year in sorted(irr_status_years)])
        per_irrigated_df = sql_select(conn, "per_IRRIGATED", ["OPENET_ID"] + [per_irrigated_years[year] for year in sorted(per_irrigated_years)])
    finally:
        conn.close()

    annual_dir = output_dir / "annual"
    for year in sorted(crop_years):
        crop_column = crop_years[year]
        frame = crop_df[["OPENET_ID", "ACRES_FTR_GEOM", "IRR_EFF", "ITYPE", crop_column]].copy()
        frame = frame.rename(columns={crop_column: "crop_code"})
        frame["year"] = year

        irr_column = irr_status_years.get(year)
        if irr_column:
            frame = frame.merge(
                irr_status_df[["OPENET_ID", irr_column]].rename(columns={irr_column: "irr_status"}),
                on="OPENET_ID",
                how="left",
            )
        else:
            frame["irr_status"] = pd.NA

        per_column = per_irrigated_years.get(year)
        if per_column:
            frame = frame.merge(
                per_irrigated_df[["OPENET_ID", per_column]].rename(columns={per_column: "per_irrigated"}),
                on="OPENET_ID",
                how="left",
            )
        else:
            frame["per_irrigated"] = pd.NA

        frame.to_parquet(annual_dir / f"{year}.parquet", index=False, engine="pyarrow")

    print(f"  wrote {len(crop_years):,} annual parquet files")


def monthly_columns_by_year(table_name: str, columns: Iterable[str]) -> Dict[int, List[tuple[int, str]]]:
    year_map: Dict[int, List[tuple[int, str]]] = {}
    for column in columns:
        match = MONTHLY_COLUMN_RE.match(column)
        if not match:
            continue
        if match.group("prefix") != table_name:
            continue
        month = int(match.group("mm"))
        year = yy_to_year(int(match.group("yy")))
        year_map.setdefault(year, []).append((month, column))

    for year in year_map:
        year_map[year] = sorted(year_map[year], key=lambda item: item[0])
    return year_map


def materialize_monthly(openet_gpkg: Path, output_dir: Path, variables: List[str]) -> None:
    print(f"Materializing monthly tables from {openet_gpkg}...")
    conn = sqlite3.connect(openet_gpkg)
    try:
        for variable in variables:
            columns = table_columns(conn, variable)
            year_map = monthly_columns_by_year(variable, columns)
            variable_dir = output_dir / "monthly" / variable
            variable_dir.mkdir(parents=True, exist_ok=True)
            print(f"  {variable}: {len(year_map):,} yearly parquet files")

            for year, month_columns in sorted(year_map.items()):
                selected_columns = ["OPENET_ID"] + [column for _, column in month_columns]
                wide = sql_select(conn, variable, selected_columns)
                frames = []
                for month, column in month_columns:
                    part = wide[["OPENET_ID", column]].copy()
                    part["datetime"] = pd.Timestamp(year=year, month=month, day=1)
                    part["value"] = pd.to_numeric(part[column], errors="coerce")
                    frames.append(part[["OPENET_ID", "datetime", "value"]])

                long_df = pd.concat(frames, ignore_index=True)
                long_df = long_df.dropna(subset=["value"])
                long_df.to_parquet(variable_dir / f"{year}.parquet", index=False, engine="pyarrow")
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize OpenET parquet runtime artifacts.")
    parser.add_argument(
        "--field-points-gpkg",
        default=str(OPENET_SOURCE_FIELD_POINTS_GPKG),
        help="Path to field_points.gpkg",
    )
    parser.add_argument(
        "--openet-gpkg",
        default=str(OPENET_SOURCE_FULL_OREGON_GPKG),
        help="Path to the statewide OpenET geopackage",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OPENET_DIR),
        help="Output directory for parquet artifacts",
    )
    parser.add_argument(
        "--monthly-variables",
        nargs="*",
        default=MONTHLY_RUNTIME_VARIABLES,
        help="Monthly OpenET tables to materialize. Defaults to the runtime variable set.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    field_points_gpkg = Path(args.field_points_gpkg)
    openet_gpkg = Path(args.openet_gpkg)
    output_dir = Path(args.output_dir)

    if not field_points_gpkg.exists():
        raise FileNotFoundError(f"Missing field points GeoPackage: {field_points_gpkg}")
    if not openet_gpkg.exists():
        raise FileNotFoundError(f"Missing statewide OpenET GeoPackage: {openet_gpkg}")

    prepare_output_dir(output_dir)
    materialize_field_index(field_points_gpkg, output_dir)
    materialize_annual(openet_gpkg, output_dir)
    materialize_monthly(openet_gpkg, output_dir, variables=args.monthly_variables)
    print(f"Done. Parquet runtime artifacts are available in {output_dir}")


if __name__ == "__main__":
    main()
