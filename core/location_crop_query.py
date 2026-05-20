"""
Location-based OpenET crop queries backed by normalized parquet artifacts.

This module preserves the public query surface used by SmartTap while
moving the runtime away from direct GeoPackage reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .crop_utils import matching_crop_codes
from .openet_store import OpenETParquetStore
from .paths import CDL_CODES_CSV


GROUPABLE_FIELDS = {"IRR_STATUS", "ITYPE", "CROP"}
DERIVED_ANNUAL_VARS = {"AREA", "ACRES_FTR_GEOM", "CROP", "IRR_STATUS", "per_IRRIGATED", "IRR_EFF", "ITYPE"}


def normalize_county_name(county_name: str) -> str:
    cleaned = " ".join(str(county_name or "").strip().split())
    if cleaned.lower().endswith(" county"):
        cleaned = cleaned[:-7].strip()
    return cleaned


class LocationCropQuery:
    """Query OpenET crops and variables by location using parquet runtime artifacts."""

    def __init__(
        self,
        base_path: Optional[str] = None,
        full_oregon_gpkg: Optional[str] = None,
    ):
        del full_oregon_gpkg
        if base_path is None:
            base_dir = Path(__file__).parent.parent
        else:
            base_dir = Path(base_path)

        self.store = OpenETParquetStore(base_dir)
        self.cdl_codes_csv = CDL_CODES_CSV if base_dir == Path(__file__).parent.parent else base_dir / "reference" / "CDL_Crop_Codes_Oregon.csv"
        self.crop_names = self._load_crop_names()

    def _load_crop_names(self) -> Dict[int, Dict[str, str]]:
        try:
            df = pd.read_csv(self.cdl_codes_csv)
        except Exception:
            return {}

        mapping: Dict[int, Dict[str, str]] = {}
        for _, row in df.iterrows():
            try:
                code = int(row["CDL_Code"])
            except (TypeError, ValueError):
                continue
            mapping[code] = {
                "name": str(row["Crop_Name"]),
                "group": str(row.get("Crop_Group", "Unknown")),
                "type": str(row.get("Annual_Perennial", "Unknown")),
            }
        return mapping

    def get_crop_name(self, cdl_code: int) -> str:
        if cdl_code in self.crop_names:
            return self.crop_names[cdl_code]["name"]
        return f"Unknown (CDL {cdl_code})"

    def find_fields_by_city(self, city_name: str, max_distance: int = 1) -> pd.DataFrame:
        return self.store.find_fields_by_city(city_name, max_distance=max_distance)

    def find_fields_by_county(self, county_name: str) -> pd.DataFrame:
        return self.store.find_fields_by_county(normalize_county_name(county_name))

    def get_crops_for_fields(self, openet_ids: List[str], year: int = 2024) -> pd.DataFrame:
        years = self.store.available_annual_years()
        if not years:
            return pd.DataFrame(columns=["OPENET_ID", "crop_code"])

        target_year = year if year in years else years[-1]
        crop_df = self.store.load_annual_records(
            [target_year],
            openet_ids,
            columns=["OPENET_ID", "crop_code"],
        )
        if crop_df.empty:
            return pd.DataFrame(columns=["OPENET_ID", "crop_code"])

        crop_df = crop_df.copy()
        crop_df["crop_code"] = pd.to_numeric(crop_df["crop_code"], errors="coerce")
        crop_df = crop_df.dropna(subset=["crop_code"])
        crop_df["crop_code"] = crop_df["crop_code"].astype(int)
        return crop_df[["OPENET_ID", "crop_code"]].reset_index(drop=True)

    def query_crops_by_city(self, city_name: str, year: int = 2024, max_distance: int = 1) -> pd.DataFrame:
        return self._query_crops_by_location(location=city_name, location_type="city", year=year, max_distance=max_distance)

    def query_crops_by_county(self, county_name: str, year: int = 2024) -> pd.DataFrame:
        return self._query_crops_by_location(location=county_name, location_type="county", year=year, max_distance=1)

    def summarize_crops(self, crop_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
        if crop_df.empty:
            return pd.DataFrame()

        summary = crop_df.groupby(["crop_code", "crop_name", "crop_group"]).agg(field_count=("OPENET_ID", "count")).reset_index()
        total = summary["field_count"].sum()
        summary["percentage"] = (summary["field_count"] / total * 100).round(1) if total else 0.0
        return summary.sort_values("field_count", ascending=False).head(top_n).reset_index(drop=True)

    def find_crop_locations(self, crop_name: str, year: int = 2024, county: Optional[str] = None) -> pd.DataFrame:
        matching_codes = self._crop_codes_from_filter(crop_name)
        if not matching_codes:
            return pd.DataFrame()

        if county:
            fields_df = self.find_fields_by_county(county)
        else:
            fields_df = self.store.field_index().copy()

        if fields_df.empty:
            return pd.DataFrame()

        crop_df = self.get_crops_for_fields(fields_df["OPENET_ID"].astype(str).tolist(), year=year)
        if crop_df.empty:
            return pd.DataFrame()

        result = crop_df[crop_df["crop_code"].isin(set(matching_codes))].merge(fields_df, on="OPENET_ID", how="inner")
        if result.empty:
            return result

        result["crop_name"] = result["crop_code"].apply(self.get_crop_name)
        return result.reset_index(drop=True)

    def get_variable_timeseries(
        self,
        openet_ids: List[str],
        variable: str,
        start_date: str,
        end_date: str,
        aggregation: str = "mean",
        crop_filter: Optional[str] = None,
    ) -> pd.DataFrame:
        if variable in DERIVED_ANNUAL_VARS:
            return self.get_annual_derived_timeseries(
                openet_ids=openet_ids,
                variable=variable,
                start_date=start_date,
                end_date=end_date,
                crop_filter=crop_filter,
                aggregation=aggregation,
            )

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        date_range = pd.date_range(start=start.replace(day=1), end=end.replace(day=1), freq="MS")
        if date_range.empty:
            return pd.DataFrame()

        df_melted = self._load_monthly_variable_long(openet_ids, variable, start_date, end_date)
        if df_melted.empty:
            return pd.DataFrame()

        if crop_filter:
            years = sorted({int(timestamp.year) for timestamp in date_range})
            crop_membership, _, crop_status = self._build_crop_membership_frame(openet_ids, years, crop_filter)
            if crop_status != "filter_applied" or crop_membership.empty:
                return pd.DataFrame()
            df_melted["year"] = pd.to_datetime(df_melted["datetime"]).dt.year
            df_melted = df_melted.merge(crop_membership[["OPENET_ID", "year"]], on=["OPENET_ID", "year"], how="inner")
            if df_melted.empty:
                return pd.DataFrame()

        values = pd.to_numeric(df_melted[variable], errors="coerce")
        field_counts = df_melted.groupby("datetime")["OPENET_ID"].nunique().rename("field_count")

        if aggregation == "sum":
            metric = values.groupby(df_melted["datetime"]).sum(min_count=1)
        elif aggregation == "median":
            metric = values.groupby(df_melted["datetime"]).median()
        else:
            metric = values.groupby(df_melted["datetime"]).mean()

        result = metric.rename(variable).reset_index()
        result = pd.DataFrame({"datetime": date_range}).merge(result, on="datetime", how="left")
        result = result.merge(field_counts.reset_index(), on="datetime", how="left")
        result["field_count"] = pd.to_numeric(result["field_count"], errors="coerce").fillna(0).astype(int)
        result["aggregation"] = aggregation
        return result.sort_values("datetime").reset_index(drop=True)

    def _crop_codes_from_filter(self, crop_filter: Optional[str]) -> List[int]:
        if not crop_filter:
            return []
        return matching_crop_codes(crop_filter, self.crop_names)

    def _query_crops_by_location(
        self,
        *,
        location: str,
        location_type: str,
        year: int,
        max_distance: int = 1,
    ) -> pd.DataFrame:
        fields = self._resolve_fields_for_location(location_type, location, max_distance=max_distance)
        if fields.empty:
            return pd.DataFrame()

        crops = self.get_crops_for_fields(fields["OPENET_ID"].astype(str).tolist(), year)
        if crops.empty:
            return pd.DataFrame()

        crops = crops.copy()
        crops["crop_name"] = crops["crop_code"].apply(self.get_crop_name)
        crops["crop_group"] = crops["crop_code"].apply(lambda code: self.crop_names.get(code, {}).get("group", "Unknown"))
        return crops.merge(fields, on="OPENET_ID", how="left")

    def _build_crop_membership_frame(
        self,
        openet_ids: List[str],
        years: List[int],
        crop_filter: Optional[str],
    ) -> tuple[pd.DataFrame, List[str], str]:
        columns = ["OPENET_ID", "year", "crop_code"]
        if not crop_filter:
            return pd.DataFrame(columns=columns), [], "no_filter"

        matching_codes = self._crop_codes_from_filter(crop_filter)
        if not matching_codes:
            return pd.DataFrame(columns=columns), [], "unknown_crop"

        matched_crop_names = [self.crop_names[code]["name"] for code in matching_codes[:3] if code in self.crop_names]
        if not years or not openet_ids:
            return pd.DataFrame(columns=columns), matched_crop_names, "no_crop_fields"

        crop_df = self.store.load_annual_records(years, openet_ids, columns=columns)
        if crop_df.empty:
            return pd.DataFrame(columns=columns), matched_crop_names, "no_crop_fields"

        crop_df = crop_df.copy()
        crop_df["crop_code"] = pd.to_numeric(crop_df["crop_code"], errors="coerce")
        crop_df = crop_df[crop_df["crop_code"].isin(set(matching_codes))]
        if crop_df.empty:
            return pd.DataFrame(columns=columns), matched_crop_names, "no_crop_fields"

        crop_df["crop_code"] = crop_df["crop_code"].astype(int)
        return crop_df[columns].reset_index(drop=True), matched_crop_names, "filter_applied"

    def _query_variable_by_location(
        self,
        *,
        location: str,
        location_type: str,
        variable: str,
        start_date: str,
        end_date: str,
        crop_filter: Optional[str] = None,
        aggregation: str = "mean",
        max_distance: int = 1,
        return_metadata: bool = False,
    ) -> pd.DataFrame | tuple[pd.DataFrame, Dict[str, Any]]:
        fields = self._resolve_fields_for_location(location_type, location, max_distance=max_distance)
        if fields.empty:
            metadata = {"field_count": 0, "fields": [], "no_data_reason": "no_fields"}
            return (pd.DataFrame(), metadata) if return_metadata else pd.DataFrame()

        openet_ids = fields["OPENET_ID"].astype(str).tolist()
        field_metadata: Dict[str, Any] = {
            "field_count": len(openet_ids),
            "location": location,
            "location_type": location_type,
            "fields": [],
        }

        if crop_filter:
            years = list(range(pd.to_datetime(start_date).year, pd.to_datetime(end_date).year + 1))
            crop_membership, matched_crop_names, crop_status = self._build_crop_membership_frame(openet_ids, years, crop_filter)
            field_metadata["crop_filter"] = crop_filter
            field_metadata["matched_crop_names"] = matched_crop_names
            if crop_status == "filter_applied":
                field_metadata["field_count_after_filter"] = int(crop_membership["OPENET_ID"].nunique())
                field_metadata["matched_field_years"] = int(len(crop_membership))
            elif crop_status == "unknown_crop":
                field_metadata["no_data_reason"] = "unknown_crop"
            else:
                field_metadata["field_count_after_filter"] = 0
                field_metadata["no_data_reason"] = "no_crop_fields"

        if field_metadata.get("no_data_reason") in {"unknown_crop", "no_crop_fields"}:
            return (pd.DataFrame(), field_metadata) if return_metadata else pd.DataFrame()

        if return_metadata:
            sample = fields.head(min(20, len(fields)))
            for _, field in sample.iterrows():
                item = {
                    "id": field["OPENET_ID"],
                    "county": field.get("County", "Unknown"),
                    "nearest_city": field.get("Nearest_City_1", "Unknown"),
                }
                if "Dist_City_1_ft" in field and pd.notna(field.get("Dist_City_1_ft")):
                    item["distance_miles"] = round(float(field["Dist_City_1_ft"]) / 5280, 2)
                field_metadata["fields"].append(item)
            if len(openet_ids) > 20:
                field_metadata["truncated"] = True
                field_metadata["total_fields"] = len(openet_ids)

        result = self.get_variable_timeseries(
            openet_ids=openet_ids,
            variable=variable,
            start_date=start_date,
            end_date=end_date,
            aggregation=aggregation,
            crop_filter=crop_filter,
        )

        if result.empty:
            field_metadata.setdefault("no_data_reason", "no_variable_rows")
        else:
            result["location"] = location
            result["location_type"] = location_type

        return (result, field_metadata) if return_metadata else result

    def _load_monthly_variable_long(
        self,
        openet_ids: List[str],
        variable: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        raw = self.store.load_monthly_variable(variable, openet_ids, start_date, end_date)
        if raw.empty:
            return pd.DataFrame(columns=["OPENET_ID", "datetime", variable])
        raw = raw.rename(columns={"value": variable})
        return raw[["OPENET_ID", "datetime", variable]].reset_index(drop=True)

    def _resolve_fields_for_location(self, location_type: str, location: str, max_distance: int = 1) -> pd.DataFrame:
        if location_type == "city":
            return self.find_fields_by_city(location, max_distance=max_distance)
        if location_type == "county":
            return self.find_fields_by_county(location)
        return pd.DataFrame()

    def _group_label_for_value(self, compare_by: str, raw_value: Any, crop_code: Any = None) -> str:
        if compare_by == "IRR_STATUS":
            value = pd.to_numeric(pd.Series([raw_value]), errors="coerce").iloc[0]
            return "Irrigated" if pd.notna(value) and float(value) > 0 else "Non-irrigated"
        if compare_by == "CROP":
            code = pd.to_numeric(pd.Series([crop_code if crop_code is not None else raw_value]), errors="coerce").iloc[0]
            if pd.isna(code):
                return "Unknown Crop"
            return str(self.crop_names.get(int(code), {}).get("name") or f"CDL {int(code)}")
        if compare_by == "ITYPE":
            value = pd.to_numeric(pd.Series([raw_value]), errors="coerce").iloc[0]
            if pd.isna(value):
                return "Unknown ITYPE"
            return f"ITYPE {int(value)}"
        return str(raw_value)

    def _build_group_assignment_frame(
        self,
        openet_ids: List[str],
        years: List[int],
        compare_by: str,
        crop_filter: Optional[str] = None,
    ) -> pd.DataFrame:
        if compare_by not in GROUPABLE_FIELDS or not years:
            return pd.DataFrame()

        columns = ["OPENET_ID", "year", "crop_code", "ACRES_FTR_GEOM", "IRR_EFF", "ITYPE", "irr_status", "per_irrigated"]
        annual_df = self.store.load_annual_records(years, openet_ids, columns=columns)
        if annual_df.empty:
            return pd.DataFrame()

        frame = annual_df.copy()
        frame["crop_code"] = pd.to_numeric(frame["crop_code"], errors="coerce")
        crop_codes = set(self._crop_codes_from_filter(crop_filter))
        if crop_codes:
            frame = frame[frame["crop_code"].isin(crop_codes)]
        if frame.empty:
            return pd.DataFrame()

        frame["IRR_STATUS_value"] = pd.to_numeric(frame["irr_status"], errors="coerce").fillna(0)
        frame["per_IRRIGATED_value"] = pd.to_numeric(frame["per_irrigated"], errors="coerce")
        frame["ITYPE"] = pd.to_numeric(frame["ITYPE"], errors="coerce")
        frame["IRR_EFF"] = pd.to_numeric(frame["IRR_EFF"], errors="coerce")
        frame["ACRES_FTR_GEOM"] = pd.to_numeric(frame["ACRES_FTR_GEOM"], errors="coerce")

        if compare_by == "CROP":
            frame["group_value"] = frame["crop_code"]
        elif compare_by == "IRR_STATUS":
            frame["group_value"] = frame["IRR_STATUS_value"]
        else:
            frame["group_value"] = frame["ITYPE"]

        frame["group_label"] = frame.apply(
            lambda row: self._group_label_for_value(compare_by, row["group_value"], crop_code=row.get("crop_code")),
            axis=1,
        )
        return frame.reset_index(drop=True)

    def _aggregate_grouped_annual_metric(self, field_year_df: pd.DataFrame, variable: str, aggregation: str) -> pd.DataFrame:
        if field_year_df.empty:
            return pd.DataFrame(columns=["datetime", "group", "variable", "value"])

        frame = field_year_df.copy()
        if variable in {"AREA", "ACRES_FTR_GEOM"}:
            series = pd.to_numeric(frame["ACRES_FTR_GEOM"], errors="coerce").fillna(0)
            grouped = frame.assign(metric_value=series).groupby(["year", "group_label"], as_index=False)["metric_value"].sum()
        elif variable == "IRR_EFF":
            series = pd.to_numeric(frame["IRR_EFF"], errors="coerce")
            grouped = frame.assign(metric_value=series).groupby(["year", "group_label"], as_index=False)["metric_value"].mean()
        elif variable == "CROP":
            grouped = frame.assign(metric_value=1.0).groupby(["year", "group_label"], as_index=False)["metric_value"].sum()
        elif variable == "IRR_STATUS":
            series = pd.to_numeric(frame["IRR_STATUS_value"], errors="coerce").fillna(0)
            if aggregation == "sum":
                grouped = frame.assign(metric_value=(series > 0).astype(float)).groupby(["year", "group_label"], as_index=False)["metric_value"].sum()
            else:
                grouped = frame.assign(metric_value=series).groupby(["year", "group_label"], as_index=False)["metric_value"].mean()
        elif variable == "per_IRRIGATED":
            series = pd.to_numeric(frame["per_IRRIGATED_value"], errors="coerce")
            grouped = frame.assign(metric_value=series).groupby(["year", "group_label"], as_index=False)["metric_value"].mean()
        else:
            return pd.DataFrame(columns=["datetime", "group", "variable", "value"])

        grouped["datetime"] = pd.to_datetime(grouped["year"].astype(str) + "-01-01")
        grouped["group"] = grouped["group_label"].astype(str)
        grouped["variable"] = variable
        grouped["value"] = grouped["metric_value"].astype(float)
        return grouped[["datetime", "group", "variable", "value"]]

    def query_grouped_variables_by_location(
        self,
        *,
        location: str,
        location_type: str,
        compare_by: str,
        variables: List[str],
        start_date: str,
        end_date: str,
        crop_filter: Optional[str] = None,
        aggregation: str = "mean",
        max_distance: int = 1,
    ) -> pd.DataFrame:
        if compare_by not in GROUPABLE_FIELDS:
            raise ValueError(f"Unsupported grouped comparison field: {compare_by}")

        fields = self._resolve_fields_for_location(location_type, location, max_distance=max_distance)
        if fields.empty:
            return pd.DataFrame()

        openet_ids = fields["OPENET_ID"].astype(str).tolist()
        years = list(range(pd.to_datetime(start_date).year, pd.to_datetime(end_date).year + 1))
        field_year_df = self._build_group_assignment_frame(openet_ids, years, compare_by, crop_filter=crop_filter)
        if field_year_df.empty:
            return pd.DataFrame()

        value_variables = [value for value in variables if value and value != compare_by]
        if not value_variables:
            return pd.DataFrame()

        results: List[pd.DataFrame] = []
        for variable in value_variables:
            if variable in DERIVED_ANNUAL_VARS:
                annual = self._aggregate_grouped_annual_metric(field_year_df, variable, aggregation)
                if not annual.empty:
                    results.append(annual)
                continue

            raw = self._load_monthly_variable_long(openet_ids, variable, start_date, end_date)
            if raw.empty:
                continue
            raw["year"] = pd.to_datetime(raw["datetime"]).dt.year
            merged = raw.merge(field_year_df[["OPENET_ID", "year", "group_label"]], on=["OPENET_ID", "year"], how="inner")
            if merged.empty:
                continue

            metric_series = pd.to_numeric(merged[variable], errors="coerce")
            if aggregation == "sum":
                grouped = merged.assign(metric_value=metric_series).groupby(["datetime", "group_label"], as_index=False)["metric_value"].sum()
            elif aggregation == "median":
                grouped = merged.assign(metric_value=metric_series).groupby(["datetime", "group_label"], as_index=False)["metric_value"].median()
            else:
                grouped = merged.assign(metric_value=metric_series).groupby(["datetime", "group_label"], as_index=False)["metric_value"].mean()

            grouped["group"] = grouped["group_label"].astype(str)
            grouped["variable"] = variable
            grouped["value"] = grouped["metric_value"].astype(float)
            results.append(grouped[["datetime", "group", "variable", "value"]])

        if not results:
            return pd.DataFrame()

        combined = pd.concat(results, ignore_index=True)
        combined["compare_by"] = compare_by
        combined["location"] = location
        combined["location_type"] = location_type
        return combined.sort_values(["variable", "group", "datetime"]).reset_index(drop=True)

    def query_categorical_counts_by_location(
        self,
        *,
        location: str,
        location_type: str,
        compare_by: str,
        start_date: str,
        end_date: str,
        crop_filter: Optional[str] = None,
        max_distance: int = 1,
    ) -> pd.DataFrame:
        if compare_by not in GROUPABLE_FIELDS:
            raise ValueError(f"Unsupported grouped comparison field: {compare_by}")

        fields = self._resolve_fields_for_location(location_type, location, max_distance=max_distance)
        if fields.empty:
            return pd.DataFrame()

        openet_ids = fields["OPENET_ID"].astype(str).tolist()
        years = list(range(pd.to_datetime(start_date).year, pd.to_datetime(end_date).year + 1))
        field_year_df = self._build_group_assignment_frame(openet_ids, years, compare_by, crop_filter=crop_filter)
        if field_year_df.empty:
            return pd.DataFrame()

        grouped = (
            field_year_df.groupby(["year", "group_label"], as_index=False)
            .size()
            .rename(columns={"group_label": "group", "size": "field_count"})
        )
        grouped["datetime"] = pd.to_datetime(grouped["year"].astype(str) + "-01-01")
        grouped["compare_by"] = compare_by
        grouped["location"] = location
        grouped["location_type"] = location_type
        return grouped[["datetime", "group", "field_count", "compare_by", "location", "location_type"]].sort_values(
            ["datetime", "group"]
        ).reset_index(drop=True)

    def get_annual_derived_timeseries(
        self,
        openet_ids: List[str],
        variable: str,
        start_date: str,
        end_date: str,
        crop_filter: Optional[str] = None,
        aggregation: str = "mean",
    ) -> pd.DataFrame:
        start_year = pd.to_datetime(start_date).year
        end_year = pd.to_datetime(end_date).year
        years = list(range(start_year, end_year + 1))
        if not years:
            return pd.DataFrame()

        columns = ["OPENET_ID", "year", "crop_code", "ACRES_FTR_GEOM", "IRR_EFF", "ITYPE", "irr_status", "per_irrigated"]
        annual_df = self.store.load_annual_records(years, openet_ids, columns=columns)
        if annual_df.empty:
            return pd.DataFrame()

        annual_df = annual_df.copy()
        annual_df["crop_code"] = pd.to_numeric(annual_df["crop_code"], errors="coerce")
        annual_df["ACRES_FTR_GEOM"] = pd.to_numeric(annual_df["ACRES_FTR_GEOM"], errors="coerce")
        annual_df["IRR_EFF"] = pd.to_numeric(annual_df["IRR_EFF"], errors="coerce")
        annual_df["ITYPE"] = pd.to_numeric(annual_df["ITYPE"], errors="coerce")
        annual_df["irr_status"] = pd.to_numeric(annual_df["irr_status"], errors="coerce")
        annual_df["per_irrigated"] = pd.to_numeric(annual_df["per_irrigated"], errors="coerce")

        crop_codes = set(self._crop_codes_from_filter(crop_filter))
        if crop_codes:
            annual_df = annual_df[annual_df["crop_code"].isin(crop_codes)]

        rows: List[Dict[str, Any]] = []
        for year in years:
            frame = annual_df[annual_df["year"] == year].copy()
            if frame.empty:
                value = None
            elif variable in {"AREA", "ACRES_FTR_GEOM"}:
                value = float(frame["ACRES_FTR_GEOM"].fillna(0).sum())
            elif variable == "CROP":
                value = float(frame["crop_code"].notna().sum())
            elif variable == "IRR_EFF":
                value = float(frame["IRR_EFF"].mean())
            elif variable == "ITYPE":
                mode_series = frame["ITYPE"].dropna().mode()
                value = float(mode_series.iloc[0]) if not mode_series.empty else None
            elif variable == "IRR_STATUS":
                vals = frame["irr_status"].fillna(0)
                value = float(vals.mean()) if aggregation == "mean" else float((vals > 0).sum())
            elif variable == "per_IRRIGATED":
                value = float(frame["per_irrigated"].mean())
            else:
                value = None

            rows.append({"datetime": pd.Timestamp(f"{year}-01-01"), variable: value})

        return pd.DataFrame(rows)

    def query_variable_by_city(
        self,
        city_name: str,
        variable: str,
        start_date: str,
        end_date: str,
        crop_filter: Optional[str] = None,
        aggregation: str = "mean",
        max_distance: int = 1,
        return_metadata: bool = False,
    ) -> pd.DataFrame | tuple[pd.DataFrame, Dict[str, Any]]:
        return self._query_variable_by_location(
            location=city_name,
            location_type="city",
            variable=variable,
            start_date=start_date,
            end_date=end_date,
            crop_filter=crop_filter,
            aggregation=aggregation,
            max_distance=max_distance,
            return_metadata=return_metadata,
        )

    def query_variable_by_county(
        self,
        county_name: str,
        variable: str,
        start_date: str,
        end_date: str,
        crop_filter: Optional[str] = None,
        aggregation: str = "mean",
        return_metadata: bool = False,
    ) -> pd.DataFrame | tuple[pd.DataFrame, Dict[str, Any]]:
        return self._query_variable_by_location(
            location=county_name,
            location_type="county",
            variable=variable,
            start_date=start_date,
            end_date=end_date,
            crop_filter=crop_filter,
            aggregation=aggregation,
            return_metadata=return_metadata,
        )
