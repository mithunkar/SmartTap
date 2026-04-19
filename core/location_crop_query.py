"""
Location-based crop queries linking field_points.gpkg, CROP data, and CDL codes
Enables queries like: "What crops are grown in Corvallis?" or "Show alfalfa fields in Hood River"

Extended to support OpenET variable queries by location:
- "Show me ETa for fields in Corvallis from 2020-2022"
- "What is the irrigation water applied to wheat fields in Hood River?"
"""

import sqlite3
import pandas as pd
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple
from collections import Counter
from datetime import datetime

from .crop_utils import matching_crop_codes


GROUPABLE_FIELDS = {"IRR_STATUS", "ITYPE", "CROP"}
DERIVED_ANNUAL_VARS = {"AREA", "ACRES_FTR_GEOM", "CROP", "IRR_STATUS", "per_IRRIGATED", "IRR_EFF", "ITYPE"}


def normalize_county_name(county_name: str) -> str:
    cleaned = " ".join(str(county_name or "").strip().split())
    if cleaned.lower().endswith(" county"):
        cleaned = cleaned[:-7].strip()
    return cleaned

class LocationCropQuery:
    """Query crops by location using field_points.gpkg and CROP data"""
    
    def __init__(self, base_path: Optional[str] = None, 
                 full_oregon_gpkg: Optional[str] = None):
        """
        Initialize with paths to data files
        
        Args:
            base_path: Base directory (defaults to project root)
            full_oregon_gpkg: Path to full Oregon geopackage (if extracted)
                             If provided, will use this instead of CROP.csv
        """
        if base_path is None:
            base_path = Path(__file__).parent.parent
        else:
            base_path = Path(base_path)
        
        self.field_points_gpkg = base_path / "data" / "field_points.gpkg"
        self.cdl_codes_csv = base_path / "data" / "CDL_Crop_Codes_Oregon.csv"
        
        # Determine crop data source
        if full_oregon_gpkg and Path(full_oregon_gpkg).exists():
            self.crop_source = "geopackage"
            self.crop_gpkg = Path(full_oregon_gpkg)
            print(f"Using full Oregon geopackage: {self.crop_gpkg.name}")
        else:
            self.crop_source = "csv"
            self.crop_csv = base_path / "data" / "archive" / "openet_csv_out" / "CROP.csv"
            print(f"Using CSV crop data (Klamath subset only)")
            print(f"Note: To query all Oregon, extract data/archive/preliminary_or_field_geopackage.7z")
        
        # Load CDL crop codes for name lookup
        self.crop_names = self._load_crop_names()
    
    def _load_crop_names(self) -> Dict[int, Dict]:
        """Load CDL crop code to name mapping"""
        try:
            df = pd.read_csv(self.cdl_codes_csv)
            mapping = {}
            for _, row in df.iterrows():
                mapping[int(row['CDL_Code'])] = {
                    'name': row['Crop_Name'],
                    'group': row.get('Crop_Group', 'Unknown'),
                    'type': row.get('Annual_Perennial', 'Unknown')
                }
            return mapping
        except Exception as e:
            print(f"Warning: Could not load crop names: {e}")
            return {}
    
    def get_crop_name(self, cdl_code: int) -> str:
        """Get crop name from CDL code"""
        if cdl_code in self.crop_names:
            return self.crop_names[cdl_code]['name']
        return f"Unknown (CDL {cdl_code})"
    
    def find_fields_by_city(self, city_name: str, max_distance: int = 1) -> pd.DataFrame:
        """
        Find all fields near a city
        
        Args:
            city_name: Name of the city
            max_distance: 1 = nearest city only, 2 = include second nearest
        
        Returns:
            DataFrame with OPENET_ID, County, Nearest_City_1, Nearest_City_2, Lat, Lon
        """
        conn = sqlite3.connect(self.field_points_gpkg)
        
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
                   END as Distance_ft
            FROM field_points
            WHERE Nearest_City_1 LIKE '%{city_name}%' 
               OR Nearest_City_2 LIKE '%{city_name}%'
            ORDER BY Distance_ft
            """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def find_fields_by_county(self, county_name: str) -> pd.DataFrame:
        """Find all fields in a county"""
        conn = sqlite3.connect(self.field_points_gpkg)
        normalized_county = normalize_county_name(county_name)
        
        query = f"""
        SELECT OPENET_ID, County, Nearest_City_1, Nearest_City_2,
               Longitude, Latitude
        FROM field_points
        WHERE County LIKE '%{normalized_county}%'
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def get_crops_for_fields(self, openet_ids: List[str], year: int = 2024) -> pd.DataFrame:
        """
        Get crop data for specific fields
        
        Args:
            openet_ids: List of OPENET_ID values
            year: Which year's crop data to get (2024 default)
        
        Returns:
            DataFrame with OPENET_ID and crop code
        """
        if self.crop_source == "geopackage":
            # Query from geopackage
            conn = sqlite3.connect(self.crop_gpkg)
            crop_col = f'CROP_{year}'
            
            # Build query for subset of IDs
            ids_str = "', '".join(openet_ids)
            query = f"""
            SELECT OPENET_ID, {crop_col} as crop_code
            FROM CROP
            WHERE OPENET_ID IN ('{ids_str}')
            """
            
            try:
                crop_df = pd.read_sql_query(query, conn)
            except Exception as e:
                # Try most recent year if specified year not available
                available_cols = pd.read_sql_query("SELECT * FROM CROP LIMIT 1", conn).columns
                crop_years = [col for col in available_cols if col.startswith('CROP_')]
                if crop_years:
                    crop_col = sorted(crop_years)[-1]
                    print(f"Year {year} not available, using {crop_col}")
                    query = f"""
                    SELECT OPENET_ID, {crop_col} as crop_code
                    FROM CROP
                    WHERE OPENET_ID IN ('{ids_str}')
                    """
                    crop_df = pd.read_sql_query(query, conn)
                else:
                    conn.close()
                    return pd.DataFrame()
            
            conn.close()
        else:
            # Load from CSV (Klamath subset only)
            crop_df = pd.read_csv(self.crop_csv)
            
            # Filter to requested fields
            crop_df = crop_df[crop_df['OPENET_ID'].isin(openet_ids)]
            
            # Get crop column for the year
            crop_col = f'CROP_{year}'
            if crop_col not in crop_df.columns:
                # Try most recent available year
                available_years = [col for col in crop_df.columns if col.startswith('CROP_')]
                if available_years:
                    crop_col = sorted(available_years)[-1]
                    print(f"Year {year} not available, using {crop_col}")
                else:
                    return pd.DataFrame()
            
            # Return OPENET_ID and crop code
            crop_df = crop_df[['OPENET_ID', crop_col]].copy()
            crop_df.rename(columns={crop_col: 'crop_code'}, inplace=True)
        
        # Convert crop codes to int (handle NaN)
        crop_df['crop_code'] = pd.to_numeric(crop_df['crop_code'], errors='coerce')
        crop_df = crop_df.dropna(subset=['crop_code'])
        crop_df['crop_code'] = crop_df['crop_code'].astype(int)
        
        return crop_df
    
    def query_crops_by_city(self, city_name: str, year: int = 2024, 
                           max_distance: int = 1) -> pd.DataFrame:
        """
        Query what crops are grown near a city
        
        Args:
            city_name: Name of the city (e.g., "Corvallis")
            year: Which year's crop data (default 2024)
            max_distance: 1 = nearest city only, 2 = include second nearest
        
        Returns:
            DataFrame with summary of crops grown
        """
        return self._query_crops_by_location(location=city_name, location_type="city", year=year, max_distance=max_distance)
    
    def query_crops_by_county(self, county_name: str, year: int = 2024) -> pd.DataFrame:
        """Query what crops are grown in a county"""
        return self._query_crops_by_location(location=county_name, location_type="county", year=year, max_distance=1)
    
    def summarize_crops(self, crop_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
        """
        Summarize crop data by counting fields per crop
        
        Args:
            crop_df: DataFrame from query_crops_by_city or query_crops_by_county
            top_n: Number of top crops to show
        
        Returns:
            DataFrame with crop_name, field_count, percentage
        """
        if crop_df.empty:
            return pd.DataFrame()
        
        # Count fields per crop
        summary = crop_df.groupby(['crop_code', 'crop_name', 'crop_group']).agg(
            field_count=('OPENET_ID', 'count')
        ).reset_index()
        
        # Add percentage
        total = summary['field_count'].sum()
        summary['percentage'] = (summary['field_count'] / total * 100).round(1)
        
        # Sort by count
        summary = summary.sort_values('field_count', ascending=False)
        
        # Return top N
        return summary.head(top_n)
    
    def find_crop_locations(self, crop_name: str, year: int = 2024, 
                           county: Optional[str] = None) -> pd.DataFrame:
        """
        Find where a specific crop is grown
        
        Args:
            crop_name: Name of crop (e.g., "Alfalfa", "Winter Wheat")
            year: Which year's data
            county: Optional county filter
        
        Returns:
            DataFrame with fields growing that crop
        """
        # Find matching crop codes
        matching_codes = []
        crop_name_lower = crop_name.lower()
        
        for code, info in self.crop_names.items():
            if crop_name_lower in info['name'].lower():
                matching_codes.append(code)
        
        if not matching_codes:
            print(f"No crop found matching '{crop_name}'")
            print("Try one of:", sorted(set([info['name'] for info in self.crop_names.values()]))[:20])
            return pd.DataFrame()
        
        print(f"Searching for crops: {[self.crop_names[c]['name'] for c in matching_codes]}")
        
        # Load crop data
        crop_col = f'CROP_{year}'
        
        if self.crop_source == "geopackage":
            conn = sqlite3.connect(self.crop_gpkg)
            
            # Build query for matching crop codes
            codes_str = ", ".join(str(c) for c in matching_codes)
            
            if county:
                # Join with field_points for county filter - use subquery
                query = f"""
                SELECT OPENET_ID, {crop_col} as crop_code
                FROM CROP
                WHERE {crop_col} IN ({codes_str})
                """
            else:
                query = f"""
                SELECT OPENET_ID, {crop_col} as crop_code
                FROM CROP
                WHERE {crop_col} IN ({codes_str})
                """
            
            try:
                crop_df = pd.read_sql_query(query, conn)
                crop_df.rename(columns={crop_col: 'crop_code'}, inplace=True)
            except Exception as e:
                # Try most recent year
                available_cols = pd.read_sql_query("SELECT * FROM CROP LIMIT 1", conn).columns
                crop_years = [col for col in available_cols if col.startswith('CROP_')]
                if crop_years:
                    crop_col = sorted(crop_years)[-1]
                    print(f"Using {crop_col}")
                    query = query.replace(f'CROP_{year}', crop_col)
                    crop_df = pd.read_sql_query(query, conn)
                    crop_df.rename(columns={crop_col: 'crop_code'}, inplace=True)
                else:
                    conn.close()
                    return pd.DataFrame()
            
            conn.close()
        else:
            # Load from CSV
            crop_df = pd.read_csv(self.crop_csv)
            
            if crop_col not in crop_df.columns:
                available_years = [col for col in crop_df.columns if col.startswith('CROP_')]
                crop_col = sorted(available_years)[-1]
                print(f"Using {crop_col}")
            
            # Filter to matching crops
            crop_df[crop_col] = pd.to_numeric(crop_df[crop_col], errors='coerce')
            crop_df = crop_df[crop_df[crop_col].isin(matching_codes)]
            crop_df = crop_df[['OPENET_ID', crop_col]].copy()
            crop_df.rename(columns={crop_col: 'crop_code'}, inplace=True)
        
        if crop_df.empty:
            print(f"No fields found growing {crop_name} in {year}")
            return pd.DataFrame()
        
        # Get field locations
        conn = sqlite3.connect(self.field_points_gpkg)
        normalized_county = normalize_county_name(county) if county else county
        
        if county:
            query = f"""
            SELECT OPENET_ID, County, Nearest_City_1, Longitude, Latitude
            FROM field_points
            WHERE County LIKE '%{normalized_county}%'
            """
        else:
            query = "SELECT OPENET_ID, County, Nearest_City_1, Longitude, Latitude FROM field_points"
        
        fields_df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Join
        result = crop_df.merge(fields_df, on='OPENET_ID', how='inner')
        result['crop_name'] = result['crop_code'].apply(self.get_crop_name)
        
        print(f"Found {len(result)} fields growing {crop_name}" + 
              (f" in {county} County" if county else ""))
        
        return result
    
    def get_variable_timeseries(self, openet_ids: List[str], variable: str,                                 start_date: str, end_date: str, 
                                aggregation: str = "mean") -> pd.DataFrame:
        """
        Get OpenET variable timeseries for specific fields
        
        Args:
            openet_ids: List of OPENET_ID values
            variable: OpenET variable (ETa, PPT, AW, P_rz, etc.)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            aggregation: How to aggregate across fields ("mean", "sum", "median")
        
        Returns:
            DataFrame with datetime and variable columns
        """
        if self.crop_source != "geopackage":
            print("Error: Variable queries require full Oregon geopackage")
            print("Extract data/preliminary_or_field_geopackage.7z to enable this feature")
            return pd.DataFrame()
        
        # Parse dates
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        # Some query intents require yearly derived metrics from wide annual layers
        # instead of monthly variable tables (e.g., CROP, IRR_STATUS, per_IRRIGATED, AREA).
        derived_vars = {"AREA", "ACRES_FTR_GEOM", "CROP", "IRR_STATUS", "per_IRRIGATED", "IRR_EFF", "ITYPE"}
        if variable in derived_vars:
            return self.get_annual_derived_timeseries(
                openet_ids=openet_ids,
                variable=variable,
                start_date=start_date,
                end_date=end_date,
                crop_filter=None,
                aggregation=aggregation,
            )
        
        # Determine unit suffix for this variable
        # Different variables use different units
        unit_map = {
            'ETa': '_in',
            'PPT': '_in',
            'P_rz': '_in',
            'P_eft': '_in',
            'NIWR': '_in',
            'AW': '_acft',
            'IRR_CU_VOLUME': '_acft',
            'IRR_CU_VOLUMEadj': '_acft',
            'NIWR_VOLUME': '_acft',
            'PPT_VOLUME': '_acft',
            'ET_VOLUME': '_acft',
            'ETO_VOLUME': '_acft',
            'ETD_VOLUME': '_acft',
            'ETDa_VOLUME': '_acft',
            'EFF_VOLUME': '_acft',
            'WS_C': '',  # No unit suffix
        }
        unit_suffix = unit_map.get(variable, '_in')  # Default to _in if unknown
        
        # Determine which monthly columns to query
        # Format: VAR_MM_YY_unit (e.g., ETa_01_20_in, AW_01_20_acft)
        date_range = pd.date_range(start=start.replace(day=1), 
                                   end=end.replace(day=1), freq='MS')
        
        columns_to_fetch = []
        for dt in date_range:
            # Format: MM_YY
            month_year = dt.strftime("%m_%y")
            col_name = f"{variable}_{month_year}{unit_suffix}"
            columns_to_fetch.append((col_name, dt))
        
        if not columns_to_fetch:
            print("No data columns found for date range")
            return pd.DataFrame()
        
        # Query geopackage
        conn = sqlite3.connect(self.crop_gpkg)
        
        # First, check which columns actually exist in the table
        check_query = f"PRAGMA table_info({variable})"
        try:
            table_info = pd.read_sql_query(check_query, conn)
            existing_columns = set(table_info['name'].tolist())
        except Exception as e:
            print(f"Error checking table {variable}: {e}")
            conn.close()
            return pd.DataFrame()
        
        # Filter to only columns that exist
        valid_columns = []
        valid_dates = []
        for col_name, dt in columns_to_fetch:
            if col_name in existing_columns:
                valid_columns.append(col_name)
                valid_dates.append(dt)
        
        if not valid_columns:
            print(f"No {variable} data columns found for date range {start_date} to {end_date}")
            conn.close()
            return pd.DataFrame()
        
        # Build column list
        cols_str = ", ".join(valid_columns)
        
        # Build query
        ids_str = "', '".join(openet_ids)
        query = f"""
        SELECT OPENET_ID, {cols_str}
        FROM {variable}
        WHERE OPENET_ID IN ('{ids_str}')
        """
        
        try:
            df = pd.read_sql_query(query, conn)
        except Exception as e:
            print(f"Error querying {variable}: {e}")
            print(f"Ensure table '{variable}' exists in geopackage")
            conn.close()
            return pd.DataFrame()
        
        conn.close()
        
        if df.empty:
            print(f"No data found for {len(openet_ids)} fields")
            return pd.DataFrame()
        
        # Convert to long format
        df_melted = df.melt(id_vars=['OPENET_ID'], 
                           value_vars=valid_columns,
                           var_name='month_col', 
                           value_name=variable)
        
        # Map column names back to dates
        col_to_date = {col: dt for col, dt in zip(valid_columns, valid_dates)}
        df_melted['datetime'] = df_melted['month_col'].map(col_to_date)
        
        # Drop rows with missing dates (in case some columns didn't exist)
        df_melted = df_melted.dropna(subset=['datetime'])
        
        # Aggregate across fields
        if aggregation == "mean":
            result = df_melted.groupby('datetime')[variable].mean().reset_index()
        elif aggregation == "sum":
            result = df_melted.groupby('datetime')[variable].sum().reset_index()
        elif aggregation == "median":
            result = df_melted.groupby('datetime')[variable].median().reset_index()
        else:
            print(f"Unknown aggregation: {aggregation}, using mean")
            result = df_melted.groupby('datetime')[variable].mean().reset_index()
        
        # Sort by date
        result = result.sort_values('datetime').reset_index(drop=True)
        
        # Add field count column
        result['field_count'] = len(openet_ids)
        result['aggregation'] = aggregation
        
        return result

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
            place = f"near {location}" if location_type == "city" else f"in {location} County"
            print(f"No fields found {place}")
            return pd.DataFrame()

        crops = self.get_crops_for_fields(fields["OPENET_ID"].tolist(), year)
        if crops.empty:
            print(f"No crop data available for {location}")
            return pd.DataFrame()

        crops["crop_name"] = crops["crop_code"].apply(self.get_crop_name)
        crops["crop_group"] = crops["crop_code"].apply(
            lambda x: self.crop_names.get(x, {}).get("group", "Unknown")
        )
        return crops.merge(fields, on="OPENET_ID", how="left")

    def _filter_field_ids_by_crop(
        self,
        *,
        openet_ids: List[str],
        crop_filter: Optional[str],
        year: int,
    ) -> tuple[List[str], List[str], str]:
        if not crop_filter:
            return openet_ids, [], "no_filter"

        crops = self.get_crops_for_fields(openet_ids, year)
        matching_codes = self._crop_codes_from_filter(crop_filter)
        if not matching_codes:
            return [], [], "unknown_crop"
        if crops.empty:
            matched_crop_names = [self.crop_names[code]["name"] for code in matching_codes[:3] if code in self.crop_names]
            return [], matched_crop_names, "no_crop_fields"

        crops_filtered = crops[crops["crop_code"].isin(matching_codes)]
        filtered_ids = crops_filtered["OPENET_ID"].tolist()
        matched_crop_names = [self.crop_names[code]["name"] for code in matching_codes[:3] if code in self.crop_names]
        if not filtered_ids:
            return [], matched_crop_names, "no_crop_fields"
        return filtered_ids, matched_crop_names, "filter_applied"

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
    ) -> pd.DataFrame:
        fields = self._resolve_fields_for_location(location_type, location, max_distance=max_distance)
        if fields.empty:
            place = f"near {location}" if location_type == "city" else f"in {location} County"
            print(f"No fields found {place}")
            if return_metadata:
                return pd.DataFrame(), {"field_count": 0, "fields": [], "no_data_reason": "no_fields"}
            return pd.DataFrame()

        openet_ids = fields["OPENET_ID"].tolist()
        field_metadata = {
            "field_count": len(openet_ids),
            "location": location,
            "location_type": location_type,
            "fields": [],
        }

        if crop_filter:
            year = pd.to_datetime(start_date).year
            filtered_ids, matched_crop_names, crop_status = self._filter_field_ids_by_crop(
                openet_ids=openet_ids,
                crop_filter=crop_filter,
                year=year,
            )
            if crop_status == "filter_applied":
                openet_ids = filtered_ids
                print(
                    f"Filtered to {len(openet_ids)} {'/'.join(matched_crop_names)} fields "
                    f"{'near' if location_type == 'city' else 'in'} {location}"
                )
                field_metadata["crop_filter"] = crop_filter
                field_metadata["field_count_after_filter"] = len(openet_ids)
                field_metadata["matched_crop_names"] = matched_crop_names
            elif crop_status == "unknown_crop":
                print(f"Warning: No crop found matching '{crop_filter}'")
                field_metadata["crop_filter"] = crop_filter
                field_metadata["no_data_reason"] = "unknown_crop"
            else:
                print(f"No {crop_filter} fields found {'near' if location_type == 'city' else 'in'} {location}")
                field_metadata["crop_filter"] = crop_filter
                field_metadata["matched_crop_names"] = matched_crop_names
                field_metadata["field_count_after_filter"] = 0
                field_metadata["no_data_reason"] = "no_crop_fields"
        else:
            print(f"Querying {variable} for {len(openet_ids)} fields {'near' if location_type == 'city' else 'in'} {location}")

        if not openet_ids:
            field_metadata.setdefault("no_data_reason", "no_crop_fields" if crop_filter else "no_fields")
            if return_metadata:
                return pd.DataFrame(), field_metadata
            return pd.DataFrame()

        if return_metadata:
            for _, field in fields.head(min(20, len(fields))).iterrows():
                if field["OPENET_ID"] not in openet_ids:
                    continue
                field_info = {
                    "id": field["OPENET_ID"],
                    "county": field.get("County", "Unknown"),
                    "nearest_city": field.get("Nearest_City_1", "Unknown"),
                }
                if "Dist_City_1_ft" in field:
                    field_info["distance_miles"] = round(field["Dist_City_1_ft"] / 5280, 2)
                field_metadata["fields"].append(field_info)
            if len(openet_ids) > 20:
                field_metadata["truncated"] = True
                field_metadata["total_fields"] = len(openet_ids)

        if variable in DERIVED_ANNUAL_VARS:
            result = self.get_annual_derived_timeseries(
                openet_ids=openet_ids,
                variable=variable,
                start_date=start_date,
                end_date=end_date,
                crop_filter=crop_filter,
                aggregation=aggregation,
            )
        else:
            result = self.get_variable_timeseries(openet_ids, variable, start_date, end_date, aggregation)

        if not result.empty:
            result["location"] = location
            result["location_type"] = location_type
        else:
            field_metadata.setdefault("no_data_reason", "no_variable_rows")

        if return_metadata:
            return result, field_metadata
        return result

    def _yearly_column(self, variable: str, year: int) -> Optional[str]:
        if variable == "CROP":
            return f"CROP_{year}"
        if variable == "IRR_STATUS":
            return f"IRR_STATUS_{year}"
        if variable == "per_IRRIGATED":
            return f"per_IRRIGATED_{year % 100:02d}"
        return None

    def _fetch_table_subset(self, conn: sqlite3.Connection, table: str, cols: List[str], openet_ids: List[str]) -> pd.DataFrame:
        if not openet_ids:
            return pd.DataFrame(columns=cols)

        safe_cols = [c for c in cols if c]
        if "OPENET_ID" not in safe_cols:
            safe_cols = ["OPENET_ID"] + safe_cols
        col_str = ", ".join(dict.fromkeys(safe_cols))

        chunks: List[pd.DataFrame] = []
        chunk_size = 2500
        for i in range(0, len(openet_ids), chunk_size):
            chunk = openet_ids[i : i + chunk_size]
            ids_str = "', '".join(chunk)
            query = f"""
            SELECT {col_str}
            FROM {table}
            WHERE OPENET_ID IN ('{ids_str}')
            """
            chunks.append(pd.read_sql_query(query, conn))

        if not chunks:
            return pd.DataFrame(columns=safe_cols)
        return pd.concat(chunks, ignore_index=True)

    def _load_monthly_variable_long(
        self,
        openet_ids: List[str],
        variable: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if self.crop_source != "geopackage":
            return pd.DataFrame()

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        unit_map = {
            'ETa': '_in',
            'PPT': '_in',
            'P_rz': '_in',
            'P_eft': '_in',
            'NIWR': '_in',
            'AW': '_acft',
            'IRR_CU_VOLUME': '_acft',
            'IRR_CU_VOLUMEadj': '_acft',
            'NIWR_VOLUME': '_acft',
            'PPT_VOLUME': '_acft',
            'ET_VOLUME': '_acft',
            'ETO_VOLUME': '_acft',
            'ETD_VOLUME': '_acft',
            'ETDa_VOLUME': '_acft',
            'EFF_VOLUME': '_acft',
            'WS_C': '',
        }
        unit_suffix = unit_map.get(variable, '_in')
        date_range = pd.date_range(start=start.replace(day=1), end=end.replace(day=1), freq='MS')
        columns_to_fetch = []
        for dt in date_range:
            month_year = dt.strftime("%m_%y")
            columns_to_fetch.append((f"{variable}_{month_year}{unit_suffix}", dt))

        conn = sqlite3.connect(self.crop_gpkg)
        try:
            table_info = pd.read_sql_query(f"PRAGMA table_info({variable})", conn)
            existing_columns = set(table_info['name'].tolist())
            valid_columns = []
            valid_dates = []
            for col_name, dt in columns_to_fetch:
                if col_name in existing_columns:
                    valid_columns.append(col_name)
                    valid_dates.append(dt)
            if not valid_columns:
                return pd.DataFrame()

            raw = self._fetch_table_subset(conn, variable, ["OPENET_ID"] + valid_columns, openet_ids)
        finally:
            conn.close()

        if raw.empty:
            return pd.DataFrame()

        melted = raw.melt(
            id_vars=["OPENET_ID"],
            value_vars=valid_columns,
            var_name="month_col",
            value_name=variable,
        )
        col_to_date = {col: dt for col, dt in zip(valid_columns, valid_dates)}
        melted["datetime"] = melted["month_col"].map(col_to_date)
        melted = melted.dropna(subset=["datetime"])
        return melted[["OPENET_ID", "datetime", variable]]

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
            info = self.crop_names.get(int(code), {})
            return str(info.get("name") or f"CDL {int(code)}")
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

        crop_cols = [f"CROP_{y}" for y in years]
        base_cols = ["OPENET_ID", "ACRES_FTR_GEOM", "IRR_EFF", "ITYPE"] + crop_cols
        irr_status_cols = [f"IRR_STATUS_{y}" for y in years]
        per_irr_cols = [f"per_IRRIGATED_{y % 100:02d}" for y in years]

        conn = sqlite3.connect(self.crop_gpkg)
        try:
            crop_df = self._fetch_table_subset(conn, "CROP", base_cols, openet_ids)
            irr_status_df = self._fetch_table_subset(conn, "IRR_STATUS", ["OPENET_ID"] + irr_status_cols, openet_ids)
            per_irr_df = self._fetch_table_subset(conn, "per_IRRIGATED", ["OPENET_ID"] + per_irr_cols, openet_ids)
        finally:
            conn.close()

        if crop_df.empty:
            return pd.DataFrame()

        crop_codes = set(self._crop_codes_from_filter(crop_filter))
        frames: List[pd.DataFrame] = []

        for year in years:
            crop_col = f"CROP_{year}"
            if crop_col not in crop_df.columns:
                continue

            frame = crop_df[["OPENET_ID", "ACRES_FTR_GEOM", "IRR_EFF", "ITYPE", crop_col]].copy()
            frame["year"] = year
            frame["crop_code"] = pd.to_numeric(frame[crop_col], errors="coerce")
            if crop_codes:
                frame = frame[frame["crop_code"].isin(crop_codes)]
            if frame.empty:
                continue

            irr_col = f"IRR_STATUS_{year}"
            per_irr_col = f"per_IRRIGATED_{year % 100:02d}"
            if irr_col in irr_status_df.columns:
                frame = frame.merge(irr_status_df[["OPENET_ID", irr_col]], on="OPENET_ID", how="left")
                frame["IRR_STATUS_value"] = pd.to_numeric(frame[irr_col], errors="coerce").fillna(0)
            else:
                frame["IRR_STATUS_value"] = 0

            if per_irr_col in per_irr_df.columns:
                frame = frame.merge(per_irr_df[["OPENET_ID", per_irr_col]], on="OPENET_ID", how="left")
                frame["per_IRRIGATED_value"] = pd.to_numeric(frame[per_irr_col], errors="coerce")
            else:
                frame["per_IRRIGATED_value"] = pd.NA

            if compare_by == "CROP":
                frame["group_value"] = frame["crop_code"]
            elif compare_by == "IRR_STATUS":
                frame["group_value"] = frame["IRR_STATUS_value"]
            else:
                frame["group_value"] = pd.to_numeric(frame["ITYPE"], errors="coerce")

            frame["group_label"] = frame.apply(
                lambda row: self._group_label_for_value(compare_by, row["group_value"], crop_code=row.get("crop_code")),
                axis=1,
            )
            frames.append(frame)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _aggregate_grouped_annual_metric(
        self,
        field_year_df: pd.DataFrame,
        variable: str,
        aggregation: str,
    ) -> pd.DataFrame:
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
                metric = frame.assign(metric_value=(series > 0).astype(float))
                grouped = metric.groupby(["year", "group_label"], as_index=False)["metric_value"].sum()
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
        if self.crop_source != "geopackage":
            return pd.DataFrame()
        if compare_by not in GROUPABLE_FIELDS:
            raise ValueError(f"Unsupported grouped comparison field: {compare_by}")

        fields = self._resolve_fields_for_location(location_type, location, max_distance=max_distance)
        if fields.empty:
            return pd.DataFrame()

        openet_ids = fields["OPENET_ID"].tolist()
        years = list(range(pd.to_datetime(start_date).year, pd.to_datetime(end_date).year + 1))
        field_year_df = self._build_group_assignment_frame(
            openet_ids=openet_ids,
            years=years,
            compare_by=compare_by,
            crop_filter=crop_filter,
        )
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

    def get_annual_derived_timeseries(
        self,
        openet_ids: List[str],
        variable: str,
        start_date: str,
        end_date: str,
        crop_filter: Optional[str] = None,
        aggregation: str = "mean",
    ) -> pd.DataFrame:
        """
        Build annual derived metrics from wide yearly layers in the geopackage.
        """
        if self.crop_source != "geopackage":
            return pd.DataFrame()

        start_year = pd.to_datetime(start_date).year
        end_year = pd.to_datetime(end_date).year
        years = list(range(start_year, end_year + 1))
        if not years:
            return pd.DataFrame()

        crop_cols = [f"CROP_{y}" for y in years]
        base_cols = ["OPENET_ID", "ACRES_FTR_GEOM", "IRR_EFF", "ITYPE"] + crop_cols

        irr_status_cols = [f"IRR_STATUS_{y}" for y in years] if variable == "IRR_STATUS" else []
        per_irr_cols = [f"per_IRRIGATED_{y % 100:02d}" for y in years] if variable == "per_IRRIGATED" else []

        conn = sqlite3.connect(self.crop_gpkg)
        try:
            crop_df = self._fetch_table_subset(conn, "CROP", base_cols, openet_ids)

            irr_status_df = pd.DataFrame()
            if irr_status_cols:
                irr_status_df = self._fetch_table_subset(conn, "IRR_STATUS", ["OPENET_ID"] + irr_status_cols, openet_ids)

            per_irr_df = pd.DataFrame()
            if per_irr_cols:
                per_irr_df = self._fetch_table_subset(conn, "per_IRRIGATED", ["OPENET_ID"] + per_irr_cols, openet_ids)
        finally:
            conn.close()

        if crop_df.empty:
            return pd.DataFrame()

        crop_codes = set(self._crop_codes_from_filter(crop_filter))
        rows: List[Dict[str, Any]] = []

        for year in years:
            crop_col = f"CROP_{year}"
            if crop_col not in crop_df.columns:
                continue

            frame = crop_df.copy()
            frame[crop_col] = pd.to_numeric(frame[crop_col], errors="coerce")

            if crop_codes:
                frame = frame[frame[crop_col].isin(crop_codes)]

            if frame.empty:
                value = 0.0
            elif variable in {"AREA", "ACRES_FTR_GEOM"}:
                value = float(pd.to_numeric(frame["ACRES_FTR_GEOM"], errors="coerce").fillna(0).sum())
            elif variable == "CROP":
                # If a crop filter is supplied, this is annual field-count for that crop.
                # Otherwise, use all fields with a valid crop code.
                value = float(frame[crop_col].notna().sum())
            elif variable == "IRR_EFF":
                value = float(pd.to_numeric(frame["IRR_EFF"], errors="coerce").mean())
            elif variable == "ITYPE":
                mode_series = pd.to_numeric(frame["ITYPE"], errors="coerce").dropna().mode()
                value = float(mode_series.iloc[0]) if not mode_series.empty else 0.0
            elif variable == "IRR_STATUS":
                year_col = f"IRR_STATUS_{year}"
                if irr_status_df.empty or year_col not in irr_status_df.columns:
                    value = 0.0
                else:
                    merged = frame[["OPENET_ID"]].merge(
                        irr_status_df[["OPENET_ID", year_col]], on="OPENET_ID", how="left"
                    )
                    vals = pd.to_numeric(merged[year_col], errors="coerce").fillna(0)
                    if aggregation == "mean":
                        value = float(vals.mean())
                    else:
                        value = float((vals > 0).sum())
            elif variable == "per_IRRIGATED":
                year_col = f"per_IRRIGATED_{year % 100:02d}"
                if per_irr_df.empty or year_col not in per_irr_df.columns:
                    value = 0.0
                else:
                    merged = frame[["OPENET_ID"]].merge(
                        per_irr_df[["OPENET_ID", year_col]], on="OPENET_ID", how="left"
                    )
                    vals = pd.to_numeric(merged[year_col], errors="coerce")
                    value = float(vals.mean())
            else:
                value = 0.0

            rows.append({
                "datetime": pd.Timestamp(f"{year}-01-01"),
                variable: value,
            })

        return pd.DataFrame(rows)
    
    def query_variable_by_city(self, city_name: str, variable: str,
                               start_date: str, end_date: str,
                               crop_filter: Optional[str] = None,
                               aggregation: str = "mean",
                               max_distance: int = 1,
                               return_metadata: bool = False) -> pd.DataFrame:
        """
        Query OpenET variable for fields near a city
        
        Args:
            city_name: Name of the city (e.g., "Corvallis")
            variable: OpenET variable (ETa, PPT, AW, P_rz, etc.)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            crop_filter: Optional crop name to filter (e.g., "Wheat")
            aggregation: How to aggregate ("mean", "sum", "median")
            max_distance: 1 = nearest city only, 2 = include second nearest
            return_metadata: If True, return tuple (data, field_metadata)
        
        Returns:
            DataFrame with datetime and variable timeseries
            OR tuple of (DataFrame, dict) if return_metadata=True
        """
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
    
    def query_variable_by_county(self, county_name: str, variable: str,
                                 start_date: str, end_date: str,
                                 crop_filter: Optional[str] = None,
                                 aggregation: str = "mean",
                                 return_metadata: bool = False) -> pd.DataFrame:
        """
        Query OpenET variable for fields in a county
        
        Args:
            county_name: Name of the county (e.g., "Benton")
            variable: OpenET variable (ETa, PPT, AW, P_rz, etc.)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            crop_filter: Optional crop name to filter
            aggregation: How to aggregate ("mean", "sum", "median")
            return_metadata: If True, return tuple (data, field_metadata)
        
        Returns:
            DataFrame with datetime and variable timeseries
            OR tuple of (DataFrame, dict) if return_metadata=True
        """
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


if __name__ == "__main__":
    # Test the system
    query = LocationCropQuery()
    
    print("=" * 60)
    print("TEST 1: What crops are grown in Corvallis?")
    print("=" * 60)
    corvallis_crops = query.query_crops_by_city("Corvallis", year=2024, max_distance=2)
    
    if not corvallis_crops.empty:
        print("\nTop 10 crops near Corvallis:")
        summary = query.summarize_crops(corvallis_crops, top_n=10)
        print(summary.to_string(index=False))
        
        print(f"\nTotal fields analyzed: {len(corvallis_crops)}")
        print(f"Unique crops: {corvallis_crops['crop_name'].nunique()}")
    
    print("\n" + "=" * 60)
    print("TEST 2: Where is alfalfa grown in Benton County?")
    print("=" * 60)
    alfalfa = query.find_crop_locations("Alfalfa", county="Benton")
    
    if not alfalfa.empty:
        print(f"\nTop cities with alfalfa:")
        city_counts = alfalfa['Nearest_City_1'].value_counts().head(5)
        for city, count in city_counts.items():
            print(f"  {city}: {count} fields")
