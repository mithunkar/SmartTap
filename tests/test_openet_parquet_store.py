from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from core.crop_utils import matching_crop_codes
from core.location_crop_query import LocationCropQuery
from core.openet_store import OpenETParquetStore
from core.paths import OPENET_FIELD_INDEX_PARQUET, OPENET_SOURCE_FIELD_POINTS_GPKG, OPENET_SOURCE_FULL_OREGON_GPKG


pytestmark = pytest.mark.skipif(
    not OPENET_SOURCE_FIELD_POINTS_GPKG.exists()
    or not OPENET_SOURCE_FULL_OREGON_GPKG.exists()
    or not OPENET_FIELD_INDEX_PARQUET.exists(),
    reason="OpenET source and parquet runtime data are required for parquet-store regression tests.",
)


MONTHLY_TABLE_NAME = {
    "Prz": "P_rz",
}


@pytest.fixture(scope="module")
def query() -> LocationCropQuery:
    return LocationCropQuery()


@pytest.fixture(scope="module")
def store() -> OpenETParquetStore:
    return OpenETParquetStore()


def _sql_fields_by_city(city_name: str, max_distance: int = 1) -> pd.DataFrame:
    conn = sqlite3.connect(OPENET_SOURCE_FIELD_POINTS_GPKG)
    try:
        if max_distance == 1:
            query = f"""
            SELECT OPENET_ID, County, Nearest_City_1, Nearest_City_2,
                   Longitude, Latitude, Dist_City_1_ft
            FROM field_points
            WHERE Nearest_City_1 LIKE '%{city_name}%'
            ORDER BY Dist_City_1_ft
            """
        else:
            query = f"""
            SELECT OPENET_ID, County, Nearest_City_1, Nearest_City_2,
                   Longitude, Latitude,
                   CASE
                       WHEN Nearest_City_1 LIKE '%{city_name}%' THEN Dist_City_1_ft
                       ELSE Dist_City_2_ft
                   END AS Distance_ft
            FROM field_points
            WHERE Nearest_City_1 LIKE '%{city_name}%'
               OR Nearest_City_2 LIKE '%{city_name}%'
            ORDER BY Distance_ft
            """
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def _sql_fields_by_county(county_name: str) -> pd.DataFrame:
    clean_county = county_name[:-7].strip() if county_name.lower().endswith(" county") else county_name.strip()
    conn = sqlite3.connect(OPENET_SOURCE_FIELD_POINTS_GPKG)
    try:
        query = f"""
        SELECT OPENET_ID, County, Nearest_City_1, Nearest_City_2, Longitude, Latitude
        FROM field_points
        WHERE County LIKE '%{clean_county}%'
        """
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def _fetch_table_subset(conn: sqlite3.Connection, table: str, columns: list[str], openet_ids: list[str]) -> pd.DataFrame:
    if not openet_ids:
        return pd.DataFrame(columns=columns)

    chunks = []
    for index in range(0, len(openet_ids), 2500):
        chunk = openet_ids[index : index + 2500]
        ids = "', '".join(chunk)
        sql = f"""
        SELECT {", ".join(columns)}
        FROM {table}
        WHERE OPENET_ID IN ('{ids}')
        """
        chunks.append(pd.read_sql_query(sql, conn))
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=columns)


def _baseline_crop_membership(query: LocationCropQuery, openet_ids: list[str], years: list[int], crop_filter: str) -> pd.DataFrame:
    matching_codes = set(matching_crop_codes(crop_filter, query.crop_names))
    conn = sqlite3.connect(OPENET_SOURCE_FULL_OREGON_GPKG)
    try:
        crop_columns = ["OPENET_ID"] + [f"CROP_{year}" for year in years]
        crop_df = _fetch_table_subset(conn, "CROP", crop_columns, openet_ids)
    finally:
        conn.close()

    frames = []
    for year in years:
        crop_column = f"CROP_{year}"
        if crop_column not in crop_df.columns:
            continue
        frame = crop_df[["OPENET_ID", crop_column]].copy()
        frame["crop_code"] = pd.to_numeric(frame[crop_column], errors="coerce")
        frame = frame[frame["crop_code"].isin(matching_codes)]
        if frame.empty:
            continue
        frame["crop_code"] = frame["crop_code"].astype(int)
        frame["year"] = year
        frames.append(frame[["OPENET_ID", "year", "crop_code"]])

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["OPENET_ID", "year", "crop_code"])


def _baseline_monthly_variable(
    query: LocationCropQuery,
    openet_ids: list[str],
    variable: str,
    start_date: str,
    end_date: str,
    *,
    aggregation: str = "mean",
    crop_filter: str | None = None,
) -> pd.DataFrame:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    date_range = pd.date_range(start=start.replace(day=1), end=end.replace(day=1), freq="MS")
    if date_range.empty:
        return pd.DataFrame(columns=["datetime", variable])

    table_name = MONTHLY_TABLE_NAME.get(variable, variable)
    unit_map = {
        "ETa": "_in",
        "PPT": "_in",
        "P_rz": "_in",
        "P_eft": "_in",
        "NIWR": "_in",
        "AW": "_acft",
        "IRR_CU_VOLUME": "_acft",
        "IRR_CU_VOLUMEadj": "_acft",
        "NIWR_VOLUME": "_acft",
        "PPT_VOLUME": "_acft",
        "ET_VOLUME": "_acft",
        "ETO_VOLUME": "_acft",
        "ETD_VOLUME": "_acft",
        "ETDa_VOLUME": "_acft",
        "EFF_VOLUME": "_acft",
        "WS_C": "",
    }
    suffix = unit_map.get(table_name, "_in")
    column_names = [(f"{table_name}_{timestamp.strftime('%m_%y')}{suffix}", timestamp) for timestamp in date_range]

    conn = sqlite3.connect(OPENET_SOURCE_FULL_OREGON_GPKG)
    try:
        table_info = pd.read_sql_query(f"PRAGMA table_info({table_name})", conn)
        existing = set(table_info["name"].tolist())
        valid = [(column, timestamp) for column, timestamp in column_names if column in existing]
        raw = _fetch_table_subset(conn, table_name, ["OPENET_ID"] + [column for column, _ in valid], openet_ids)
    finally:
        conn.close()

    if raw.empty or not valid:
        return pd.DataFrame(columns=["datetime", variable])

    melted = raw.melt(id_vars=["OPENET_ID"], value_vars=[column for column, _ in valid], var_name="month_col", value_name=variable)
    col_to_date = {column: timestamp for column, timestamp in valid}
    melted["datetime"] = melted["month_col"].map(col_to_date)
    melted = melted.dropna(subset=["datetime"])

    if crop_filter:
        years = sorted({int(timestamp.year) for timestamp in date_range})
        membership = _baseline_crop_membership(query, openet_ids, years, crop_filter)
        melted["year"] = pd.to_datetime(melted["datetime"]).dt.year
        melted = melted.merge(membership[["OPENET_ID", "year"]], on=["OPENET_ID", "year"], how="inner")

    if melted.empty:
        return pd.DataFrame(columns=["datetime", variable])

    values = pd.to_numeric(melted[variable], errors="coerce")
    if aggregation == "sum":
        metric = values.groupby(melted["datetime"]).sum(min_count=1)
    elif aggregation == "median":
        metric = values.groupby(melted["datetime"]).median()
    else:
        metric = values.groupby(melted["datetime"]).mean()

    result = metric.rename(variable).reset_index()
    return pd.DataFrame({"datetime": date_range}).merge(result, on="datetime", how="left")


def _baseline_annual_area(query: LocationCropQuery, openet_ids: list[str], start_date: str, end_date: str, crop_filter: str) -> pd.DataFrame:
    start_year = pd.to_datetime(start_date).year
    end_year = pd.to_datetime(end_date).year
    years = list(range(start_year, end_year + 1))
    matching_codes = set(matching_crop_codes(crop_filter, query.crop_names))

    conn = sqlite3.connect(OPENET_SOURCE_FULL_OREGON_GPKG)
    try:
        columns = ["OPENET_ID", "ACRES_FTR_GEOM"] + [f"CROP_{year}" for year in years]
        crop_df = _fetch_table_subset(conn, "CROP", columns, openet_ids)
    finally:
        conn.close()

    rows = []
    for year in years:
        column = f"CROP_{year}"
        frame = crop_df.copy()
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame[frame[column].isin(matching_codes)]
        value = float(pd.to_numeric(frame["ACRES_FTR_GEOM"], errors="coerce").fillna(0).sum()) if not frame.empty else None
        rows.append({"datetime": pd.Timestamp(f"{year}-01-01"), "ACRES_FTR_GEOM": value})
    return pd.DataFrame(rows)


def _baseline_grouped_itype_counts(query: LocationCropQuery, openet_ids: list[str], start_date: str, end_date: str, crop_filter: str) -> pd.DataFrame:
    start_year = pd.to_datetime(start_date).year
    end_year = pd.to_datetime(end_date).year
    years = list(range(start_year, end_year + 1))
    matching_codes = set(matching_crop_codes(crop_filter, query.crop_names))

    conn = sqlite3.connect(OPENET_SOURCE_FULL_OREGON_GPKG)
    try:
        columns = ["OPENET_ID", "ITYPE"] + [f"CROP_{year}" for year in years]
        crop_df = _fetch_table_subset(conn, "CROP", columns, openet_ids)
    finally:
        conn.close()

    rows = []
    for year in years:
        column = f"CROP_{year}"
        frame = crop_df[["OPENET_ID", "ITYPE", column]].copy()
        frame["crop_code"] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame[frame["crop_code"].isin(matching_codes)]
        if frame.empty:
            continue
        frame["ITYPE"] = pd.to_numeric(frame["ITYPE"], errors="coerce")
        frame["group"] = frame["ITYPE"].apply(lambda value: f"ITYPE {int(value)}" if pd.notna(value) else "Unknown ITYPE")
        grouped = frame.groupby("group", as_index=False).size().rename(columns={"size": "field_count"})
        for _, row in grouped.iterrows():
            rows.append(
                {
                    "datetime": pd.Timestamp(f"{year}-01-01"),
                    "group": row["group"],
                    "field_count": int(row["field_count"]),
                }
            )

    return pd.DataFrame(rows).sort_values(["datetime", "group"]).reset_index(drop=True)


def test_store_city_lookup_matches_sql_openet_ids(store: OpenETParquetStore) -> None:
    parquet_ids = set(store.find_fields_by_city("Corvallis", max_distance=2)["OPENET_ID"].astype(str))
    sql_ids = set(_sql_fields_by_city("Corvallis", max_distance=2)["OPENET_ID"].astype(str))
    assert parquet_ids == sql_ids


def test_store_county_lookup_accepts_county_suffix(store: OpenETParquetStore) -> None:
    direct = store.find_fields_by_county("Morrow")
    with_suffix = store.find_fields_by_county("Morrow County")
    assert set(direct["OPENET_ID"].astype(str)) == set(with_suffix["OPENET_ID"].astype(str))


def test_store_load_annual_records_has_requested_years_and_columns(store: OpenETParquetStore) -> None:
    fields = store.find_fields_by_county("Morrow County").head(20)
    records = store.load_annual_records([2019, 2020], fields["OPENET_ID"].astype(str).tolist(), columns=["OPENET_ID", "year", "crop_code"])
    assert not records.empty
    assert set(records.columns) == {"OPENET_ID", "year", "crop_code"}
    assert set(records["year"].unique()) <= {2019, 2020}


def test_store_monthly_loader_reads_only_requested_years(store: OpenETParquetStore) -> None:
    fields = store.find_fields_by_county("Klamath County").head(50)
    records = store.load_monthly_variable("ETa", fields["OPENET_ID"].astype(str).tolist(), "2019-01-01", "2020-12-31")
    assert not records.empty
    years = set(pd.to_datetime(records["datetime"]).dt.year.unique().tolist())
    assert years == {2019, 2020}


def test_parquet_city_monthly_query_matches_geopackage_baseline(query: LocationCropQuery) -> None:
    parquet = query.query_variable_by_city("Corvallis", variable="ETa", start_date="2024-01-01", end_date="2024-12-31")
    sql_fields = _sql_fields_by_city("Corvallis")
    baseline = _baseline_monthly_variable(
        query,
        sql_fields["OPENET_ID"].astype(str).tolist(),
        "ETa",
        "2024-01-01",
        "2024-12-31",
    )
    pdt.assert_frame_equal(
        parquet[["datetime", "ETa"]].reset_index(drop=True),
        baseline[["datetime", "ETa"]].reset_index(drop=True),
        check_dtype=False,
    )


def test_parquet_county_monthly_query_matches_geopackage_baseline(query: LocationCropQuery) -> None:
    parquet = query.query_variable_by_county(
        "Umatilla County",
        variable="AW",
        start_date="2023-01-01",
        end_date="2023-12-31",
        aggregation="sum",
    )
    sql_fields = _sql_fields_by_county("Umatilla County")
    baseline = _baseline_monthly_variable(
        query,
        sql_fields["OPENET_ID"].astype(str).tolist(),
        "AW",
        "2023-01-01",
        "2023-12-31",
        aggregation="sum",
    )
    pdt.assert_frame_equal(
        parquet[["datetime", "AW"]].reset_index(drop=True),
        baseline[["datetime", "AW"]].reset_index(drop=True),
        check_dtype=False,
    )


def test_parquet_crop_filtered_query_matches_geopackage_baseline(query: LocationCropQuery) -> None:
    parquet = query.query_variable_by_county(
        "Klamath County",
        variable="ETa",
        start_date="2019-01-01",
        end_date="2020-12-31",
        crop_filter="Mint",
    )
    sql_fields = _sql_fields_by_county("Klamath County")
    baseline = _baseline_monthly_variable(
        query,
        sql_fields["OPENET_ID"].astype(str).tolist(),
        "ETa",
        "2019-01-01",
        "2020-12-31",
        crop_filter="Mint",
    )
    pdt.assert_frame_equal(
        parquet[["datetime", "ETa"]].reset_index(drop=True),
        baseline[["datetime", "ETa"]].reset_index(drop=True),
        check_dtype=False,
    )


def test_parquet_annual_derived_query_matches_geopackage_baseline(query: LocationCropQuery) -> None:
    parquet = query.query_variable_by_county(
        "Morrow County",
        variable="ACRES_FTR_GEOM",
        start_date="2014-01-01",
        end_date="2022-12-31",
        crop_filter="Alfalfa",
    )
    sql_fields = _sql_fields_by_county("Morrow County")
    baseline = _baseline_annual_area(
        query,
        sql_fields["OPENET_ID"].astype(str).tolist(),
        "2014-01-01",
        "2022-12-31",
        "Alfalfa",
    )
    pdt.assert_frame_equal(
        parquet[["datetime", "ACRES_FTR_GEOM"]].reset_index(drop=True),
        baseline[["datetime", "ACRES_FTR_GEOM"]].reset_index(drop=True),
        check_dtype=False,
    )


def test_parquet_grouped_comparison_matches_geopackage_baseline(query: LocationCropQuery) -> None:
    parquet = query.query_categorical_counts_by_location(
        location="Jefferson County",
        location_type="county",
        compare_by="ITYPE",
        start_date="2015-01-01",
        end_date="2021-12-31",
        crop_filter="Wheat",
    )
    sql_fields = _sql_fields_by_county("Jefferson County")
    baseline = _baseline_grouped_itype_counts(
        query,
        sql_fields["OPENET_ID"].astype(str).tolist(),
        "2015-01-01",
        "2021-12-31",
        "Wheat",
    )
    pdt.assert_frame_equal(
        parquet[["datetime", "group", "field_count"]].reset_index(drop=True),
        baseline[["datetime", "group", "field_count"]].reset_index(drop=True),
        check_dtype=False,
    )
