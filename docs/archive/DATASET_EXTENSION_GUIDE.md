# Dataset Extension Guide

## Overview

This guide explains how to add new datasets to SmartTap. The system is designed to be modular, with configuration files separating data paths from code logic.

## Quick Start

Adding a new dataset involves:
1. **Configure** - Add dataset metadata to `config/datasets.yaml`
2. **Implement** - Create data loading logic (optional if using existing patterns)
3. **Register** - Add variables to keyword mappings for LLM recognition
4. **Document** - Update user-facing documentation

---

## Step 1: Configure Dataset in YAML

### Add to `config/datasets.yaml`

```yaml
# Example: Adding NASS Crop Data
nass:
  # Directory containing NASS data files
  data_dir: "data/nass"
  
  # API configuration (if applicable)
  api_endpoint: "https://quickstats.nass.usda.gov/api"
  api_key_env: "NASS_API_KEY"  # Environment variable name
  
  # Available variables
  variables:
    - YIELD       # Crop yield (bushels/acre)
    - ACRES       # Planted acres
    - PRODUCTION  # Total production
  
  # Time range available
  start_year: 2010
  end_year: 2024
  
  # Default settings
  default_interval: "yearly"
  default_aggregation: "sum"
```

### Key Configuration Fields

- **`data_dir`**: Relative path from project root where data files are stored
- **`variables`**: List of variable codes available in this dataset
- **`start_year` / `end_year`**: Data availability range
- **`default_interval`**: Default time granularity ("daily", "monthly", "yearly")
- **`api_*` fields**: Optional API configuration if dataset can be fetched dynamically

---

## Step 2: Implement Data Loading Logic

### Option A: Use Existing Patterns

If your dataset follows CSV/file patterns similar to AgriMet:

```python
# In core/data_fetcher.py

def fetch_nass_data(spec: dict) -> dict:
    """
    Fetch NASS crop data
    
    Args:
        spec: Query specification with location, variables, date_range
    
    Returns:
        Payload dict with spec and records
    """
    config = get_config()
    nass_dir = config.get_dataset_path("nass", "data_dir")
    
    location = spec.get("location")
    variable = spec.get("variables", [])[0]
    start_year = pd.to_datetime(spec.get("start_date")).year
    end_year = pd.to_datetime(spec.get("end_date")).year
    
    # Load CSV files for year range
    records = []
    for year in range(start_year, end_year + 1):
        filepath = nass_dir / f"{location}_nass_{year}.csv"
        if filepath.exists():
            df = pd.read_csv(filepath)
            # Transform to standard format
            records.extend(df.to_dict('records'))
    
    return {
        "spec": spec,
        "data": {"records": records}
    }
```

### Option B: Create Custom Data Source Class

For databases or complex APIs, create a plugin:

```python
# In core/data_sources/nass_source.py

from .base import DataSource

class NASSDataSource(DataSource):
    """Data source for NASS crop statistics"""
    
    def __init__(self):
        self.config = get_config().get_dataset_config("nass")
        self.api_key = os.environ.get(self.config.get("api_key_env"))
    
    def can_handle(self, spec: dict) -> bool:
        """Check if this source can handle the query"""
        return spec.get("dataset") == "nass"
    
    def fetch(self, spec: dict) -> dict:
        """Fetch data based on specification"""
        # Implement API calls or database queries
        pass
    
    def validate(self, spec: dict) -> dict:
        """Validate query specification"""
        pass
```

---

## Step 3: Register Variables for LLM Recognition

### Add to `data/openet_variable_keywords.json` (or create new file)

For a new dataset, create `data/nass_variable_keywords.json`:

```json
{
  "YIELD": {
    "variable_name": "Crop Yield",
    "keywords": ["yield", "production per acre", "bushels per acre", "harvest yield"],
    "units": "bushels/acre",
    "description": "Crop yield measured in bushels per acre"
  },
  "ACRES": {
    "variable_name": "Planted Acres",
    "keywords": ["acres", "planted", "harvested acres", "crop acres"],
    "units": "acres",
    "description": "Total acres planted or harvested"
  },
  "PRODUCTION": {
    "variable_name": "Total Production",
    "keywords": ["total production", "crop production", "harvest total"],
    "units": "bushels",
    "description": "Total production in bushels"
  }
}
```

### Update LLM Interpretation Prompt

Modify `prompts/interpretation.txt` to include your new dataset:

```text
NASS Variables (crop statistics - county/state level):
- YIELD: crop yield, bushels per acre, production
- ACRES: planted acres, harvested acres
- PRODUCTION: total production, harvest total
```

---

## Step 4: Integrate with Query Routing

### Register in `core/data_fetcher.py`

```python
def fetch_data(spec: dict) -> dict:
    """Route to appropriate data fetcher"""
    dataset = spec.get("dataset", "").lower()
    
    if dataset == "agrimet":
        return fetch_agrimet_data(spec)
    elif dataset == "openet":
        return fetch_openet_data(spec)
    elif dataset == "nass":
        return fetch_nass_data(spec)  # Your new fetcher
    else:
        raise ValueError(f"Unknown dataset: {dataset}")
```

---

## Step 5: Test Your Integration

### Create Test Queries

```python
# In tests/test_nass_integration.py

def test_nass_yield_query():
    """Test NASS yield data query"""
    spec = {
        "task": "visualize_timeseries",
        "dataset": "nass",
        "location": "Marion County",
        "variables": ["YIELD"],
        "start_date": "2020-01-01",
        "end_date": "2024-12-31"
    }
    
    result = fetch_data(spec)
    assert result["data"]["records"]
    assert "YIELD" in result["data"]["records"][0]
```

### Test with UI

```bash
# Start Streamlit app
streamlit run smarttap_ui.py

# Try natural language queries:
# "Show crop yield in Marion County from 2020 to 2024"
# "What was the average wheat yield in Oregon last year?"
```

---

## Step 6: Document for Users

### Update README.md

Add dataset description:

```markdown
### Available Datasets

- **OpenET**: Field-level evapotranspiration, precipitation, irrigation (2016-2024)
- **AgriMet**: Weather station data - temperature, precipitation, solar radiation (2015-2025)
- **NASS**: Crop statistics - yield, planted acres, production (2010-2024) ← NEW
```

### Create Dataset-Specific Documentation

Create `docs/NASS_DATA_GUIDE.md`:

```markdown
# NASS Dataset Guide

## Overview
National Agricultural Statistics Service (NASS) crop statistics...

## Available Variables
- YIELD (bushels/acre)
- ACRES (planted acres)
- PRODUCTION (total bushels)

## Example Queries
- "Show corn yield in Marion County over the last 5 years"
- "Compare wheat production between counties"
```

---

## Advanced: Adding Spatial Datasets

For datasets with spatial components (like PostGIS):

### 1. Configure Spatial Connection

```yaml
# In config/datasets.yaml
postgis:
  connection:
    host: "localhost"
    port: 5432
    database: "oregon_ag"
    user_env: "POSTGIS_USER"
    password_env: "POSTGIS_PASSWORD"
  
  tables:
    field_boundaries: "ag_fields"
    crop_data: "crop_surveys"
  
  srid: 4326  # WGS84
```

### 2. Create Spatial Query Class

```python
# In core/data_sources/postgis_source.py

import psycopg2
from shapely import wkb

class PostGISDataSource(DataSource):
    def __init__(self):
        config = get_config().get_dataset_config("postgis")
        conn_params = config["connection"]
        self.conn = psycopg2.connect(
            host=conn_params["host"],
            dbname=conn_params["database"],
            user=os.environ.get(conn_params["user_env"]),
            password=os.environ.get(conn_params["password_env"])
        )
    
    def query_by_geometry(self, geometry_wkt: str, variable: str):
        """Query data within geometry"""
        # Implement spatial query
        pass
```

---

## Common Patterns

### Pattern 1: Time Series Data (CSV Files)

**Use Case**: Weather stations, sensor data, historical records

**File Structure**:
```
data/mydata/
  station1_2020.csv
  station1_2021.csv
  station2_2020.csv
```

**Implementation**: Similar to AgriMet fetcher

### Pattern 2: Single Combined File

**Use Case**: Small datasets, aggregated data

**File Structure**:
```
data/mydata/
  combined_data.csv  # All data in one file
```

**Implementation**: Single CSV load with filtering

### Pattern 3: API + Local Cache

**Use Case**: Live data with fallback, rate-limited APIs

**Implementation**:
```python
def fetch_with_cache(spec):
    cache_file = get_cache_path(spec)
    if cache_file.exists() and not is_stale(cache_file):
        return load_from_cache(cache_file)
    else:
        data = fetch_from_api(spec)
        save_to_cache(data, cache_file)
        return data
```

### Pattern 4: Geopackage / SQLite

**Use Case**: Spatial data, large datasets

**Implementation**: Similar to OpenET LocationCropQuery

---

## Troubleshooting

### Issue: LLM Not Recognizing New Variables

**Solution**: Ensure keywords in JSON are descriptive and match user language patterns:
```json
{
  "MYVAR": {
    "keywords": [
      "user friendly term",
      "alternative name",
      "common abbreviation"
    ]
  }
}
```

### Issue: Data Format Mismatch

**Solution**: Transform data to standard record format:
```python
{
  "datetime": "2024-01-01",
  "VAR1": 123.45,
  "VAR2": 67.89
}
```

### Issue: Configuration Not Loading

**Solution**: Check YAML syntax and file location:
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config/datasets.yaml'))"

# Check config loading
python -c "from core.config_loader import get_config; print(get_config().datasets)"
```

---

## Checklist

Before considering your dataset integration complete:

- [ ] Configuration added to `config/datasets.yaml`
- [ ] Data loading function implemented in `core/data_fetcher.py`
- [ ] Variable keywords added to JSON file
- [ ] LLM prompt updated with new variables
- [ ] Query routing integrated
- [ ] Tests created and passing
- [ ] User documentation added (README, guide)
- [ ] Example queries documented
- [ ] Error handling implemented
- [ ] Validated with UI

---

## Next Steps

- See [PROMPT_CUSTOMIZATION_GUIDE.md](PROMPT_CUSTOMIZATION_GUIDE.md) for tuning LLM interpretation
- See [ADDING_QUERY_HANDLERS.md](ADDING_QUERY_HANDLERS.md) for custom query logic
- See [ARCHITECTURE.md](ARCHITECTURE.md) for system overview

## Support

Questions? Check existing datasets (AgriMet, OpenET) as implementation examples.
