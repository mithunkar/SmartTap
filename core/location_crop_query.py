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
from typing import List, Dict, Optional, Tuple
from collections import Counter
from datetime import datetime

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
        
        query = f"""
        SELECT OPENET_ID, County, Nearest_City_1, Nearest_City_2,
               Longitude, Latitude
        FROM field_points
        WHERE County LIKE '%{county_name}%'
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
        # Step 1: Find fields near the city
        fields = self.find_fields_by_city(city_name, max_distance)
        
        if fields.empty:
            print(f"No fields found near {city_name}")
            return pd.DataFrame()
        
        print(f"Found {len(fields)} fields near {city_name}")
        
        # Step 2: Get crop data for those fields
        crops = self.get_crops_for_fields(fields['OPENET_ID'].tolist(), year)
        
        if crops.empty:
            print(f"No crop data available for fields near {city_name}")
            return pd.DataFrame()
        
        # Step 3: Add crop names
        crops['crop_name'] = crops['crop_code'].apply(self.get_crop_name)
        crops['crop_group'] = crops['crop_code'].apply(
            lambda x: self.crop_names.get(x, {}).get('group', 'Unknown')
        )
        
        # Step 4: Join with field location data
        result = crops.merge(fields, on='OPENET_ID', how='left')
        
        return result
    
    def query_crops_by_county(self, county_name: str, year: int = 2024) -> pd.DataFrame:
        """Query what crops are grown in a county"""
        # Step 1: Find fields in the county
        fields = self.find_fields_by_county(county_name)
        
        if fields.empty:
            print(f"No fields found in {county_name} County")
            return pd.DataFrame()
        
        print(f"Found {len(fields)} fields in {county_name} County")
        
        # Step 2: Get crop data
        crops = self.get_crops_for_fields(fields['OPENET_ID'].tolist(), year)
        
        if crops.empty:
            print(f"No crop data available for {county_name} County")
            return pd.DataFrame()
        
        # Step 3: Add crop names
        crops['crop_name'] = crops['crop_code'].apply(self.get_crop_name)
        crops['crop_group'] = crops['crop_code'].apply(
            lambda x: self.crop_names.get(x, {}).get('group', 'Unknown')
        )
        
        # Step 4: Join with field data
        result = crops.merge(fields, on='OPENET_ID', how='left')
        
        return result
    
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
        
        if county:
            query = f"""
            SELECT OPENET_ID, County, Nearest_City_1, Longitude, Latitude
            FROM field_points
            WHERE County LIKE '%{county}%'
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
    
    def query_variable_by_city(self, city_name: str, variable: str,
                               start_date: str, end_date: str,
                               crop_filter: Optional[str] = None,
                               aggregation: str = "mean",
                               max_distance: int = 1) -> pd.DataFrame:
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
        
        Returns:
            DataFrame with datetime and variable timeseries
        """
        # Step 1: Find fields near the city
        fields = self.find_fields_by_city(city_name, max_distance)
        
        if fields.empty:
            print(f"No fields found near {city_name}")
            return pd.DataFrame()
        
        openet_ids = fields['OPENET_ID'].tolist()
        
        # Step 2: Apply crop filter if requested
        if crop_filter:
            # Parse start date to get year for crop data
            year = pd.to_datetime(start_date).year
            crops = self.get_crops_for_fields(openet_ids, year)
            
            # Find matching crop codes with improved matching (handle singular/plural)
            matching_codes = []
            crop_filter_lower = crop_filter.lower().strip()
            
            # Try exact match first
            for code, info in self.crop_names.items():
                crop_name_lower = info['name'].lower()
                # Check if filter is in crop name OR crop name is in filter
                # This handles:  "cherry" matches "Cherries", "wheat" matches "Winter Wheat"
                if (crop_filter_lower in crop_name_lower or 
                    crop_name_lower in crop_filter_lower or
                    # Handle plurals: "cherry" -> "cherries", "berries" -> "berry"
                    crop_filter_lower.rstrip('s') in crop_name_lower or
                    crop_name_lower.rstrip('s') in crop_filter_lower):
                    matching_codes.append(code)
            
            if matching_codes:
                crops_filtered = crops[crops['crop_code'].isin(matching_codes)]
                openet_ids = crops_filtered['OPENET_ID'].tolist() 
                matched_crop_names = [self.crop_names[c]['name'] for c in matching_codes[:3]]
                print(f"Filtered to {len(openet_ids)} {'/'.join(matched_crop_names)} fields near {city_name}")
            else:
                print(f"Warning: No crop found matching '{crop_filter}', using all fields")
        else:
            print(f"Querying {variable} for {len(openet_ids)} fields near {city_name}")
        
        if not openet_ids:
            print("No fields match the criteria")
            return pd.DataFrame()
        
        # Step 3: Get variable timeseries
        result = self.get_variable_timeseries(openet_ids, variable, start_date, end_date, aggregation)
        
        # Add location info
        if not result.empty:
            result['location'] = city_name
            result['location_type'] = 'city'
        
        return result
    
    def query_variable_by_county(self, county_name: str, variable: str,
                                 start_date: str, end_date: str,
                                 crop_filter: Optional[str] = None,
                                 aggregation: str = "mean") -> pd.DataFrame:
        """
        Query OpenET variable for fields in a county
        
        Args:
            county_name: Name of the county (e.g., "Benton")
            variable: OpenET variable (ETa, PPT, AW, P_rz, etc.)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            crop_filter: Optional crop name to filter
            aggregation: How to aggregate ("mean", "sum", "median")
        
        Returns:
            DataFrame with datetime and variable timeseries
        """
        # Step 1: Find fields in the county
        fields = self.find_fields_by_county(county_name)
        
        if fields.empty:
            print(f"No fields found in {county_name} County")
            return pd.DataFrame()
        
        openet_ids = fields['OPENET_ID'].tolist()
        
        # Step 2: Apply crop filter if requested
        if crop_filter:
            year = pd.to_datetime(start_date).year
            crops = self.get_crops_for_fields(openet_ids, year)
            
            # Find matching crop codes with improved matching
            matching_codes = []
            crop_filter_lower = crop_filter.lower().strip()
            
            for code, info in self.crop_names.items():
                crop_name_lower = info['name'].lower()
                if (crop_filter_lower in crop_name_lower or 
                    crop_name_lower in crop_filter_lower or
                    crop_filter_lower.rstrip('s') in crop_name_lower or
                    crop_name_lower.rstrip('s') in crop_filter_lower):
                    matching_codes.append(code)
            
            if matching_codes:
                crops_filtered = crops[crops['crop_code'].isin(matching_codes)]
                openet_ids = crops_filtered['OPENET_ID'].tolist()
                matched_crop_names = [self.crop_names[c]['name'] for c in matching_codes[:3]]
                print(f"Filtered to {len(openet_ids)} {'/'.join(matched_crop_names)} fields in {county_name} County")
            else:
                print(f"Warning: No crop found matching '{crop_filter}', using all fields")
        else:
            print(f"Querying {variable} for {len(openet_ids)} fields in {county_name} County")
        
        if not openet_ids:
            print("No fields match the criteria")
            return pd.DataFrame()
        
        # Step 3: Get variable timeseries
        result = self.get_variable_timeseries(openet_ids, variable, start_date, end_date, aggregation)
        
        # Add location info
        if not result.empty:
            result['location'] = county_name
            result['location_type'] = 'county'
        
        return result


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
