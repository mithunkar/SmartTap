from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import pandas as pd

from .paths import OPENET_ANNUAL_DIR, OPENET_FIELD_INDEX_PARQUET, OPENET_MONTHLY_DIR


MONTHLY_TABLE_ALIASES = {
    "Prz": "P_rz",
}


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_city_name(value: object) -> str:
    return _normalize_text(str(value or "").split(",")[0])


class OpenETParquetStore:
    """Read normalized OpenET parquet artifacts for runtime queries."""

    def __init__(self, base_path: str | Path | None = None):
        if base_path is None:
            self.openet_root = OPENET_FIELD_INDEX_PARQUET.parent
        else:
            resolved = Path(base_path).resolve()
            project_root = Path(__file__).resolve().parent.parent
            self.openet_root = OPENET_FIELD_INDEX_PARQUET.parent if resolved == project_root else resolved / "data" / "openet"

        self.field_index_path = self.openet_root / OPENET_FIELD_INDEX_PARQUET.name
        self.annual_dir = self.openet_root / OPENET_ANNUAL_DIR.name
        self.monthly_dir = self.openet_root / OPENET_MONTHLY_DIR.name
        self._field_index_cache: pd.DataFrame | None = None
        self._annual_cache: dict[int, pd.DataFrame] = {}

    def _missing_runtime_data_error(self) -> FileNotFoundError:
        return FileNotFoundError(
            "OpenET parquet runtime data is missing. Run "
            "`python scripts/materialize_openet_parquet.py` to build `data/openet/` first."
        )

    def _ensure_exists(self, path: Path) -> None:
        if not path.exists():
            raise self._missing_runtime_data_error()

    def field_index(self) -> pd.DataFrame:
        if self._field_index_cache is not None:
            return self._field_index_cache

        self._ensure_exists(self.field_index_path)
        df = pd.read_parquet(self.field_index_path, engine="pyarrow")
        if "OPENET_ID" not in df.columns:
            raise ValueError(f"Missing OPENET_ID column in {self.field_index_path}")

        enriched = df.copy()
        enriched["County_normalized"] = enriched.get("County", pd.Series(dtype=str)).map(_normalize_text)
        enriched["Nearest_City_1_normalized"] = enriched.get("Nearest_City_1", pd.Series(dtype=str)).map(_normalize_city_name)
        enriched["Nearest_City_2_normalized"] = enriched.get("Nearest_City_2", pd.Series(dtype=str)).map(_normalize_city_name)
        self._field_index_cache = enriched
        return self._field_index_cache

    def available_annual_years(self) -> List[int]:
        if not self.annual_dir.exists():
            return []
        years = []
        for path in sorted(self.annual_dir.glob("*.parquet")):
            try:
                years.append(int(path.stem))
            except ValueError:
                continue
        return years

    def _annual_year_frame(self, year: int) -> pd.DataFrame:
        cached = self._annual_cache.get(year)
        if cached is not None:
            return cached

        path = self.annual_dir / f"{year}.parquet"
        self._ensure_exists(path)
        frame = pd.read_parquet(path, engine="pyarrow")
        self._annual_cache[year] = frame
        return frame

    def load_annual_records(
        self,
        years: Iterable[int],
        openet_ids: Iterable[str],
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        requested_ids = {str(value) for value in openet_ids if str(value).strip()}
        if not requested_ids:
            cols = list(columns or [])
            return pd.DataFrame(columns=cols)

        requested_columns = list(columns or [])
        frames: List[pd.DataFrame] = []
        for year in years:
            try:
                frame = self._annual_year_frame(int(year))
            except FileNotFoundError:
                continue
            filtered = frame[frame["OPENET_ID"].isin(requested_ids)]
            if filtered.empty:
                continue
            if requested_columns:
                available = [column for column in requested_columns if column in filtered.columns]
                filtered = filtered[available]
            frames.append(filtered.copy())

        if not frames:
            return pd.DataFrame(columns=requested_columns)
        return pd.concat(frames, ignore_index=True)

    def openet_location_candidates(self) -> tuple[List[str], List[str]]:
        df = self.field_index()
        counties = sorted({value for value in df["County"].dropna().astype(str).str.strip().tolist() if value})
        cities = sorted(
            {
                value
                for value in pd.concat(
                    [
                        df["Nearest_City_1"].dropna().astype(str).str.split(",").str[0].str.strip(),
                        df["Nearest_City_2"].dropna().astype(str).str.split(",").str[0].str.strip(),
                    ],
                    ignore_index=True,
                ).tolist()
                if value
            }
        )
        return counties, cities

    def city_rows(self) -> pd.DataFrame:
        df = self.field_index()
        frames = []
        for column in ("Nearest_City_1", "Nearest_City_2"):
            if column not in df.columns:
                continue
            frame = df[["County", "Latitude", "Longitude", column]].copy()
            frame = frame.rename(columns={column: "city_name"})
            frame["city_name"] = frame["city_name"].map(_normalize_city_name)
            frames.append(frame)
        if not frames:
            return pd.DataFrame(columns=["County", "Latitude", "Longitude", "city_name"])
        merged = pd.concat(frames, ignore_index=True)
        merged["County"] = merged["County"].map(_normalize_text)
        merged["Latitude"] = pd.to_numeric(merged["Latitude"], errors="coerce")
        merged["Longitude"] = pd.to_numeric(merged["Longitude"], errors="coerce")
        return merged.dropna(subset=["Latitude", "Longitude"])

    def find_fields_by_city(self, city_name: str, max_distance: int = 1) -> pd.DataFrame:
        normalized = _normalize_city_name(city_name)
        if not normalized:
            return pd.DataFrame()

        df = self.field_index()
        if max_distance == 1:
            result = df[df["Nearest_City_1_normalized"] == normalized].copy()
            if "Dist_City_1_ft" in result.columns:
                result = result.sort_values("Dist_City_1_ft")
            return result.reset_index(drop=True)

        mask1 = df["Nearest_City_1_normalized"] == normalized
        mask2 = df["Nearest_City_2_normalized"] == normalized
        result = df[mask1 | mask2].copy()
        if result.empty:
            return result
        result["Distance_ft"] = result.apply(
            lambda row: row.get("Dist_City_1_ft") if row.get("Nearest_City_1_normalized") == normalized else row.get("Dist_City_2_ft"),
            axis=1,
        )
        return result.sort_values("Distance_ft").reset_index(drop=True)

    def find_fields_by_county(self, county_name: str) -> pd.DataFrame:
        normalized = _normalize_text(str(county_name or "").removesuffix(" County").removesuffix(" county"))
        if not normalized:
            return pd.DataFrame()
        df = self.field_index()
        return df[df["County_normalized"] == normalized].copy().reset_index(drop=True)

    def _monthly_file_path(self, variable: str, year: int) -> Path:
        table_name = MONTHLY_TABLE_ALIASES.get(variable, variable)
        return self.monthly_dir / table_name / f"{year}.parquet"

    def load_monthly_variable(
        self,
        variable: str,
        openet_ids: Iterable[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        requested_ids = [str(value) for value in openet_ids if str(value).strip()]
        if not requested_ids:
            return pd.DataFrame(columns=["OPENET_ID", "datetime", "value"])

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        frames: List[pd.DataFrame] = []
        for year in range(start.year, end.year + 1):
            path = self._monthly_file_path(variable, year)
            if not path.exists():
                continue
            frames.append(self._read_monthly_year(path, requested_ids))

        if not frames:
            return pd.DataFrame(columns=["OPENET_ID", "datetime", "value"])

        combined = pd.concat(frames, ignore_index=True)
        combined["datetime"] = pd.to_datetime(combined["datetime"], errors="coerce")
        mask = (combined["datetime"] >= start) & (combined["datetime"] <= end)
        filtered = combined.loc[mask, ["OPENET_ID", "datetime", "value"]].copy()
        return filtered.sort_values(["datetime", "OPENET_ID"]).reset_index(drop=True)

    def _read_monthly_year(self, path: Path, openet_ids: List[str]) -> pd.DataFrame:
        columns = ["OPENET_ID", "datetime", "value"]
        if len(openet_ids) > 5000:
            frame = pd.read_parquet(path, columns=columns, engine="pyarrow")
            return frame[frame["OPENET_ID"].isin(set(openet_ids))].copy()

        chunks: List[pd.DataFrame] = []
        for index in range(0, len(openet_ids), 500):
            chunk = openet_ids[index : index + 500]
            frame = pd.read_parquet(
                path,
                columns=columns,
                filters=[("OPENET_ID", "in", chunk)],
                engine="pyarrow",
            )
            if not frame.empty:
                chunks.append(frame)

        if not chunks:
            return pd.DataFrame(columns=columns)
        return pd.concat(chunks, ignore_index=True)
