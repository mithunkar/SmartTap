from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

REFERENCE_DIR = BASE_DIR / "reference"
DATA_DIR = BASE_DIR / "data"
ARTIFACTS_DIR = BASE_DIR / "artifacts"

AGRIMET_DIR = DATA_DIR / "agrimet"
ARCHIVE_DATA_DIR = DATA_DIR / "archive"
OPENET_DIR = DATA_DIR / "openet"

OPENET_FIELD_INDEX_PARQUET = OPENET_DIR / "field_index.parquet"
OPENET_ANNUAL_DIR = OPENET_DIR / "annual"
OPENET_MONTHLY_DIR = OPENET_DIR / "monthly"

OPENET_SOURCE_FIELD_POINTS_GPKG = DATA_DIR / "field_points.gpkg"
OPENET_SOURCE_FULL_OREGON_GPKG = DATA_DIR / "preliminary_or_field_geopackage.gpkg"

OPENET_FIELD_COMBINED = OPENET_DIR / "field_combined_long.csv"
OPENET_HUC_COMBINED = OPENET_DIR / "huc_combined_long.csv"

AGRIMET_STATIONS_METADATA = REFERENCE_DIR / "agrimet_stations_full_metadata.csv"
AGRIMET_STATIONS_METADATA_FALLBACK = REFERENCE_DIR / "agrimet_stations_full_metadata_pilot1_subset_v2_county.csv"
CDL_CODES_CSV = REFERENCE_DIR / "CDL_Crop_Codes_Oregon.csv"
OPENET_VARIABLE_KEYWORDS_JSON = REFERENCE_DIR / "openet_variable_keywords.json"
CROP_NAME_KEYWORDS_JSON = REFERENCE_DIR / "crop_name_keywords.json"
OPENET_DATA_FIELDS_HTML = REFERENCE_DIR / "OpenET_Data_Fields.html"
OPENET_DATA_ACCESS_GUIDE_DOCX = REFERENCE_DIR / "OpenET_Data_Access_Guide.docx"

QA_ARTIFACTS_DIR = ARTIFACTS_DIR / "qa"
EXAMPLE_PARTNER_QUERIES_DIR = ARTIFACTS_DIR / "examples" / "partner_queries"
RUNTIME_PARTNER_QUERIES_DIR = Path("outputs") / "partner_queries"
