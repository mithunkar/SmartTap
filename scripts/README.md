# SmartTap Scripts

These are the active utility scripts for setup and handoff.

## Active Utilities

### `extract_oregon_data.py`

Extracts the statewide OpenET GeoPackage:

```bash
python scripts/extract_oregon_data.py
```

Input:

- `data/archive/preliminary_or_field_geopackage.7z`

Output:

- `data/preliminary_or_field_geopackage.gpkg`

### `materialize_openet_parquet.py`

Builds the parquet runtime store used by SmartTap OpenET queries:

```bash
python scripts/materialize_openet_parquet.py
```

Inputs:

- `data/field_points.gpkg`
- `data/preliminary_or_field_geopackage.gpkg`

Outputs:

- `data/openet/field_index.parquet`
- `data/openet/annual/*.parquet`
- `data/openet/monthly/*/*.parquet`

### `fetch_agrimet_data.py`

Downloads AgriMet weather CSVs into `data/agrimet/`:

```bash
python scripts/fetch_agrimet_data.py
```

### `list_stations.py`

Looks up AgriMet stations by name or state:

```bash
python scripts/list_stations.py --search "Salem"
python scripts/list_stations.py --state OR
```

### `export_qa_bundle.py`

Exports the tracked workbook QA bundle into `artifacts/qa/` by default:

```bash
python scripts/export_qa_bundle.py --clean
```

## Archive Boundary

Legacy and one-time utilities live in [`scripts/archive/README.md`](/Users/mithunkarthikeyan/Desktop/Projects/SmartTap/scripts/archive/README.md). They are not part of the active runtime path unless explicitly called out.

## Notes

- Run scripts from the project root
- Most scripts support `--help`
- Active scripts should only write to local data directories or tracked handoff artifact directories intentionally
