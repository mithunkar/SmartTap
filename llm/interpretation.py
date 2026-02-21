import ollama
import json
import os
from datetime import date
from .config import get_model_name

# Load keyword mappings
def load_keyword_mappings():
    """Load OpenET variable and crop keyword mappings"""
    base_path = os.path.dirname(os.path.dirname(__file__))
    
    # Load variable keywords
    var_path = os.path.join(base_path, "data", "openet_variable_keywords.json")
    crop_path = os.path.join(base_path, "data", "crop_name_keywords.json")
    
    variable_keywords = {}
    crop_keywords = {}
    
    try:
        with open(var_path, 'r') as f:
            variable_keywords = json.load(f)
    except FileNotFoundError:
        print(f"Warning: Variable keywords file not found at {var_path}")
    
    try:
        with open(crop_path, 'r') as f:
            crop_keywords = json.load(f)
    except FileNotFoundError:
        print(f"Warning: Crop keywords file not found at {crop_path}")
    
    return variable_keywords, crop_keywords

def get_task_specification(user_query):

    today = date.today().strftime("%Y-%m-%d")
    
    # Load keyword mappings for enhanced variable identification
    variable_keywords, crop_keywords = load_keyword_mappings()
    
    # Build variable hints from keyword mappings
    variable_hints = []
    if variable_keywords:
        # OpenET variables
        for var, info in list(variable_keywords.items())[:8]:  # Top 8 for prompt brevity
            keywords_str = ", ".join(info.get("keywords", [])[:5])
            variable_hints.append(f"- {var} ({info.get('variable_name', '')}): {keywords_str}")
    
    variable_section = "\n".join(variable_hints) if variable_hints else """ - ETa: evapotranspiration, water use, water consumption
                                                                            - PPT: precipitation, rain, rainfall
                                                                            - P_rz: effective precipitation, usable rain
                                                                            - AW: applied water, irrigation applied
                                                                            - IRR_CU_VOLUME: consumptive use, irrigation consumption"""

    system_prompt = f"""You are a JSON converter for agricultural and weather data queries. Today: {today}

SPECIAL CASE: Crop Summary Queries
If the query asks "what crops", "which crops", "list crops", "crops grown", etc. → task = "summarize_crops"
Format: {{"task": "summarize_crops", "location": "<city or county>", "location_type": "<city|county>", "year": <YYYY>}}
If no year mentioned, use 2024.

Example: "What crops are grown in Corvallis?" 
→ {{"task": "summarize_crops", "location": "Corvallis", "location_type": "city", "year": 2024}}

If this is a crop summary query, output the JSON immediately and skip the steps below.

STEP 1: Identify the variable

OpenET Variables (irrigation/crop data - field level):
{variable_section}

AgriMet Variables (weather station data):
- PC: precip, rain, rainfall
- SR: solar radiation, sun
- WS: wind speed, wind
- TU: humidity, relative humidity
- OBM: temperature (average)
- MX: max temperature, high temp
- MN: min temperature, low temp

DISAMBIGUATION: For overlapping variables (precipitation exists in both datasets)
PRECIPITATION routing rules:
- If query mentions "field-level", "fields", "crops", "irrigation", or a specific crop → OpenET (PPT - monthly field data)
- If query mentions "weather station", "station data", "daily", or "point data" → AgriMet (PC - daily station data)
- Counties are ONLY available in OpenET → use PPT
- If ambiguous, DEFAULT to OpenET (PPT) for better spatial coverage

User can explicitly specify:
- "field-level precipitation" → OpenET (PPT)
- "weather station precipitation" → AgriMet (PC)

STEP 2: Choose dataset and query type
- If variable is OpenET (ETa, PPT, P_rz, AW, etc.) → dataset = "openet"
  * If query mentions a city name (Corvallis, Hood River, Klamath Falls, etc.) → openet_geo = "location", location_type = "city"
  * If query mentions a county (Benton County, Klamath County, etc.) → openet_geo = "location", location_type = "county"
  * Otherwise for specific field → openet_geo = "field", openet_id = "<id>"

- If variable is AgriMet (PC, SR, WS, etc.) → dataset = "agrimet"

STEP 3: Extract location
For OpenET location queries:
- Cities: Corvallis, Portland, Salem, Eugene, Bend, Hood River, Pendleton, Ontario, Hermiston, Klamath Falls, etc.
- Counties: Benton, Marion, Multnomah, Deschutes, Hood River, Umatilla, Malheur, Klamath, etc.

For AgriMet queries:
- Valid stations: corvallis, pendleton, hood river, klamath falls, ontario

STEP 4: Detect crop filter (optional for OpenET queries)
If query mentions a specific crop (wheat, alfalfa, corn, grass, etc.) → add "crop_filter": "<crop_name>"

STEP 5: Extract dates (REQUIRED - MUST include start_date and end_date)
- If specific year mentioned (e.g. "2020", "in 2024") → "YYYY-01-01" to "YYYY-12-31"
- If "last year" → "{int(today.split('-')[0])-1}-01-01" to "{int(today.split('-')[0])-1}-12-31"
- If NO date mentioned → use full year 2024: "2024-01-01" to "2024-12-31"
ALWAYS output complete year ranges with start_date and end_date.

STEP 6: Build JSON

AgriMet format:
{{"task": "visualize_timeseries", "dataset": "agrimet", "location": "<location>", "variables": ["<VAR>"], "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "interval": "daily", "chart_type": "line"}}

OpenET location-based format (NEW):
{{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "<city or county>", "location_type": "<city|county>", "variables": ["<VAR>"], "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "interval": "monthly", "chart_type": "line"}}

With crop filter:
{{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "Hood River", "location_type": "city", "crop_filter": "wheat", "variables": ["ETa"], "start_date": "2020-01-01", "end_date": "2022-12-31", "interval": "monthly", "chart_type": "line"}}

EXAMPLES:
Query: "show me solar radiation in corvallis" 
Result: {{"task": "visualize_timeseries", "dataset": "agrimet", "location": "corvallis", "variables": ["SR"], "start_date": "2024-01-01", "end_date": "2024-12-31", "interval": "daily", "chart_type": "line"}}

Query: "ETa in Corvallis from 2020 to 2022" 
Result: {{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "Corvallis", "location_type": "city", "variables": ["ETa"], "start_date": "2020-01-01", "end_date": "2022-12-31", "interval": "monthly", "chart_type": "line"}}

Query: "irrigation water for wheat fields in Hood River in 2023"
Result: {{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "Hood River", "location_type": "city", "crop_filter": "wheat", "variables": ["AW"], "start_date": "2023-01-01", "end_date": "2023-12-31", "interval": "monthly", "chart_type": "line"}}

Query: "precipitation in Benton County last year"
Result: {{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "Benton", "location_type": "county", "variables": ["PPT"], "start_date": "2025-01-01", "end_date": "2025-12-31", "interval": "monthly", "chart_type": "line"}}

Query: "irrigation water for alfalfa fields in Klamath Falls"
Result: {{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "Klamath Falls", "location_type": "city", "crop_filter": "alfalfa", "variables": ["AW"], "start_date": "2024-01-01", "end_date": "2024-12-31", "interval": "monthly", "chart_type": "line"}}

Query: "weather station precipitation in Hood River"
Result: {{"task": "visualize_timeseries", "dataset": "agrimet", "location": "Hood River", "variables": ["PC"], "start_date": "2024-01-01", "end_date": "2024-12-31", "interval": "daily", "chart_type": "line"}}

Query: "field-level precipitation in Corvallis"
Result: {{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "Corvallis", "location_type": "city", "variables": ["PPT"], "start_date": "2024-01-01", "end_date": "2024-12-31", "interval": "monthly", "chart_type": "line"}}

Query: "precipitation for wheat fields in Hermiston"
Result: {{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "location", "location": "Hermiston", "location_type": "city", "crop_filter": "wheat", "variables": ["PPT"], "start_date": "2024-01-01", "end_date": "2024-12-31", "interval": "monthly", "chart_type": "line"}}

Output ONLY valid JSON. No explanations."""

    # Get configured model (defaults to gemma2:2b)
    model_name = get_model_name()
    
    #using json format to force structured output
    response = ollama.chat(
        model=model_name, 
        format='json',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_query},
        ]
    )
    
    raw_content = response.message.content
    
    try:
        parsed = json.loads(raw_content)
        return parsed
    except json.JSONDecodeError as e:
        return {"error": "JSON Parsing Error", "details": str(e), "raw": raw_content}
    except Exception as e:
        return {"error": "Unexpected Error", "details": str(e), "raw": raw_content}


if __name__ == "__main__":
    # Test queries
    queries = ["Compare temperature and precipitation in Corvallis during summer 2024"]

    for query in queries:
        print(f"User Query: {query}")
        print(json.dumps(get_task_specification(query), indent=2))