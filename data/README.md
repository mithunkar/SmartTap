# Local Data

This directory is for local-only heavy datasets and archives. These files are intentionally not tracked in git.

Required files for the retained SmartTap surface:

- `agrimet/*.csv`
- `openet/field_index.parquet`
- `openet/annual/*.parquet`
- `openet/monthly/*/*.parquet`

Offline source files for building the OpenET parquet runtime store:

- `field_points.gpkg`
- `preliminary_or_field_geopackage.gpkg`

Optional legacy files:

- `openet/field_combined_long.csv`
- `openet/huc_combined_long.csv`

Acquisition helpers:

- `scripts/extract_oregon_data.py`
- `scripts/materialize_openet_parquet.py`
- `scripts/fetch_agrimet_data.py`

Tracked reference/config assets were moved out of `data/` and into `reference/`.
