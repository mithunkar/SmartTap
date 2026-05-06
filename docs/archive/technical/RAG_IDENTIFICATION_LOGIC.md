# RAG Logic for Variable and Crop Identification

## Overview

This document defines how the SmartTap system uses LLM + RAG (Retrieval-Augmented Generation) to identify OpenET variables and crop names from natural language user questions.

## Architecture

```
User Query → [RAG Retrieval] → [LLM Parser] → [Validation] → Structured Spec
                    ↓
         Keyword Mappings + Descriptions
```

### Components

1. **Keyword Mappings** (`data/openet_variable_keywords.json`, `data/crop_name_keywords.json`)
   - Pre-defined mappings of variables and crops to synonyms/keywords
   - Used for both exact matching and semantic embedding

2. **RAG Retrieval Layer** (to be implemented)
   - Semantic search over variable descriptions and crop names
   - Returns top-k relevant candidates to augment LLM context

3. **LLM Parser** (`llm/interpretation.py`)
   - Receives user query + RAG context
   - Outputs structured JSON specification

4. **Validation Layer** (`core/validation.py`)
   - Fallback keyword matching
   - Validates LLM output against known variables/crops

---

## Variable Identification Logic

### Step 1: RAG Retrieval for Variables

**Input**: User query (e.g., "How much water did crops consume last year?")

**Process**:
1. Embed the user query using a sentence transformer model
2. Search against embedded variable descriptions from `openet_variable_keywords.json`
3. Return top-3 most relevant variables with their descriptions

**Example Retrieval**:
```json
{
  "query": "How much water did crops consume?",
  "retrieved_variables": [
    {
      "variable": "ETa",
      "relevance_score": 0.89,
      "description": "Actual Evapotranspiration - Total water consumed (crop + soil evaporation)",
      "keywords": ["water use", "water consumption", "crop water use"]
    },
    {
      "variable": "IRR_CU_VOLUME",
      "relevance_score": 0.76,
      "description": "Consumptive Use of Irrigation Water - Water consumed from irrigation",
      "keywords": ["consumptive use", "irrigation consumption"]
    },
    {
      "variable": "NIWR_VOLUME",
      "relevance_score": 0.65,
      "description": "Net Irrigation Water Requirement - Theoretical irrigation demand",
      "keywords": ["irrigation need", "irrigation demand"]
    }
  ]
}
```

### Step 2: LLM Parsing with RAG Context

**Augmented Prompt**:
```
You are parsing a natural language query about agricultural data.

User Query: "How much water did crops consume last year?"

Relevant Variables (from RAG):
1. ETa (Actual Evapotranspiration): Total water consumed by crops and soil evaporation from all sources. Keywords: water use, water consumption, crop water use
2. IRR_CU_VOLUME (Irrigation Consumptive Use): Water consumed specifically from irrigation. Keywords: consumptive use, irrigation consumption
3. NIWR_VOLUME (Net Irrigation Water Requirement): Theoretical irrigation demand. Keywords: irrigation need, irrigation demand

Based on the user's query and these relevant variables, extract:
- variable: Which variable best matches? (or null if none match)
- time_period: What time range?
- location: Geographic filter?

Output JSON only.
```

**Expected LLM Output**:
```json
{
  "variable": "ETa",
  "time_period": {"start": "2024-01-01", "end": "2024-12-31"},
  "location": null,
  "reasoning": "User asked about total water consumption, which matches ETa"
}
```

### Step 3: Validation with Keyword Fallback

**Process**:
1. Check if LLM-parsed variable exists in `openet_variable_keywords.json`
2. If null or invalid, perform keyword matching on query:
   - Extract tokens from query
   - Match against keyword lists in mapping file
   - Score each variable by keyword overlap
   - Select highest-scoring variable

**Fallback Example**:
```python
query = "show me crop water use"
tokens = ["show", "crop", "water", "use"]

# Match against ETa keywords: ["water use", "crop water use", ...]
# Match score: 3 (water, crop, use all present)
# Select: ETa
```

---

## Crop Identification Logic

### Step 1: RAG Retrieval for Crops

**Input**: User query (e.g., "Show me winter wheat fields in Hood River")

**Process**:
1. Embed the user query
2. Search against crop names + keywords from `crop_name_keywords.json`
3. Return top-5 most relevant crops with CDL codes

**Example Retrieval**:
```json
{
  "query": "Show me winter wheat fields in Hood River",
  "retrieved_crops": [
    {
      "cdl_code": 24,
      "crop_name": "Winter Wheat",
      "crop_group": "Grain",
      "relevance_score": 0.95,
      "keywords": ["winter wheat", "wheat", "winter grain"]
    },
    {
      "cdl_code": 23,
      "crop_name": "Spring Wheat",
      "crop_group": "Grain",
      "relevance_score": 0.72,
      "keywords": ["spring wheat", "wheat"]
    },
    {
      "cdl_code": 21,
      "crop_name": "Barley",
      "crop_group": "Grain",
      "relevance_score": 0.45,
      "keywords": ["barley"]
    }
  ]
}
```

### Step 2: LLM Parsing with Crop Context

**Augmented Prompt**:
```
User Query: "Show me winter wheat fields in Hood River"

Relevant Crops (from RAG):
1. Winter Wheat (CDL Code 24, Group: Grain): Keywords: winter wheat, wheat, winter grain
2. Spring Wheat (CDL Code 23, Group: Grain): Keywords: spring wheat, wheat
3. Barley (CDL Code 21, Group: Grain): Keywords: barley

Extract:
- crop_code: Which CDL code matches? (or null)
- crop_name: Name of the crop
- location: Geographic filter
```

**Expected LLM Output**:
```json
{
  "crop_code": 24,
  "crop_name": "Winter Wheat",
  "location": {"county": "Hood River"}
}
```

### Step 3: Normalization and Validation

**Normalization Rules** (from `crop_name_keywords.json`):
1. **Case-insensitive matching**: "WHEAT" = "wheat" = "Wheat"
2. **Plural normalization**: "cherries" → "cherry", "grapes" → "grape"
3. **Synonym expansion**: "maize" → "corn", "lucerne" → "alfalfa"
4. **Partial matching**: "wheat" matches both "Winter Wheat" and "Spring Wheat"
   - If ambiguous, ask user for clarification or default to most common

**Validation**:
1. Check if crop_code exists in CDL mapping
2. Verify crop_name matches CDL_Code
3. If crop_name provided but no code, look up code from `CDL_Crop_Codes_Oregon.csv`

---

## Combined Variable + Crop Queries

### Example: "How much water did alfalfa use in Morrow County?"

**Step 1: Parallel RAG Retrieval**
```json
{
  "variable_retrieval": [
    {"variable": "ETa", "score": 0.88},
    {"variable": "IRR_CU_VOLUME", "score": 0.74}
  ],
  "crop_retrieval": [
    {"crop_code": 36, "crop_name": "Alfalfa", "score": 0.98}
  ]
}
```

**Step 2: LLM Parsing**
```json
{
  "variable": "ETa",
  "crop_code": 36,
  "crop_name": "Alfalfa",
  "location": {"county": "Morrow"}
}
```

---

## Dataset Routing Logic

Once variable and crop are identified, route to the correct dataset:

### Decision Tree

```
Is variable in OpenET variable list (ETa, PPT, P_rz, AW, CU, NIWR, CROP, IRR_STATUS, etc.)?
├─ YES → Use OpenET dataset
│         - File: data/archive/openet_csv_out/{variable}_long.csv
│         - Filter by crop_code if specified
│         - Join with field_points.gpkg for geographic attributes
│
└─ NO → Use AgriMet dataset
          - File: data/agrimet/{station}_weather_{year}.csv
          - Variables: OBM (temp), PC (precip), MM (irrigation), etc.
          - Route to nearest weather station
```

### OpenET Data Loading

**File Structure**:
- Variable files: `data/archive/openet_csv_out/ETa_long.csv`, `PPT_long.csv`, etc.
- Field metadata: `data/field_points.gpkg` (centroids with lat/lon/county)
- Crop codes: `data/CDL_Crop_Codes_Oregon.csv`

**Loading Process**:
```python
# Pseudo-code
variable_data = pd.read_csv(f"data/archive/openet_csv_out/{variable}_long.csv")
field_metadata = gpd.read_file("data/field_points.gpkg")
crop_codes = pd.read_csv("data/CDL_Crop_Codes_Oregon.csv")

# Join
combined = (variable_data
    .merge(field_metadata, on="field_id")
    .merge(crop_codes, left_on="crop_code", right_on="CDL_Code")
)

# Filter by crop if specified
if crop_code:
    combined = combined[combined.crop_code == crop_code]

# Filter by location if specified
if location.county:
    combined = combined[combined.county == location.county]
```

---

## Implementation Roadmap

### Phase 1: Enhanced Keyword Matching (Current + Immediate)
- Created `openet_variable_keywords.json`
- Created `crop_name_keywords.json`
- ⬜ Update `llm/interpretation.py` to load and use keyword mappings
- ⬜ Enhance `core/validation.py` with comprehensive keyword fallback

### Phase 2: RAG Retrieval Layer (Next Sprint)
- ⬜ Choose embedding model (e.g., `sentence-transformers/all-MiniLM-L6-v2`)
- ⬜ Pre-compute embeddings for all variable descriptions
- ⬜ Pre-compute embeddings for all crop names + keywords
- ⬜ Implement semantic search function
- ⬜ Add retrieval step before LLM parsing

### Phase 3: LLM Context Augmentation (After RAG)
- ⬜ Update LLM prompt template to include RAG results
- ⬜ Add few-shot examples for variable + crop identification
- ⬜ Implement disambiguation logic for ambiguous queries

### Phase 4: Feedback Loop (Future)
- ⬜ Log LLM predictions vs. user corrections
- ⬜ Fine-tune keyword weights based on usage patterns
- ⬜ Add query expansion for common misspellings

---

## Query Examples and Expected Behavior

### Variable-Focused Queries

| User Query | RAG Top Result | LLM Output | Dataset |
|-----------|---------------|-----------|---------|
| "How much ET in 2023?" | ETa (0.92) | `{"variable": "ETa", "year": 2023}` | OpenET |
| "Show me rainfall" | PPT (0.95) | `{"variable": "PPT"}` | OpenET |
| "What's the irrigation requirement?" | NIWR_VOLUME (0.91) | `{"variable": "NIWR_VOLUME"}` | OpenET |
| "Temperature last week" | OBM (0.88) | `{"variable": "OBM", "time": "last week"}` | AgriMet |

### Crop-Focused Queries

| User Query | RAG Top Result | LLM Output |
|-----------|---------------|-----------|
| "Where is alfalfa planted?" | Alfalfa/36 (0.97) | `{"crop_code": 36, "crop_name": "Alfalfa"}` |
| "Show wheat fields" | Winter Wheat/24 (0.78), Spring Wheat/23 (0.76) | `{"crop_code": null, "crop_name": "wheat", "ambiguous": true}` → Ask user |
| "Cherry orchards in Hood River" | Cherries/72 (0.94) | `{"crop_code": 72, "location": {"county": "Hood River"}}` |

### Combined Queries

| User Query | Variable RAG | Crop RAG | LLM Output |
|-----------|------------|---------|-----------|
| "Alfalfa water use in June" | ETa (0.87) | Alfalfa/36 (0.98) | `{"variable": "ETa", "crop_code": 36, "month": 6}` |
| "How much rain did potatoes get?" | PPT (0.93) | Potatoes/43 (0.96) | `{"variable": "PPT", "crop_code": 43}` |
| "Irrigation applied to grapes" | AW (0.89) | Grapes/69 (0.97) | `{"variable": "AW", "crop_code": 69}` |

---

## Error Handling

### Ambiguous Variables
If RAG returns multiple high-scoring variables (score difference < 0.15):
1. Present top candidates to user
2. Ask: "Did you mean: (A) Actual ET, (B) Irrigation Requirement, or (C) Precipitation?"
3. Store user choice for future queries

### Ambiguous Crops
If multiple crops match (e.g., "wheat" → Winter Wheat + Spring Wheat):
1. Check if context provides clues (e.g., "June" → Spring Wheat more likely)
2. Default to most common crop in location
3. Ask user for clarification if needed

### No Matches
If RAG scores are all < 0.5:
1. Return top candidate with low confidence flag
2. Show user: "I think you're asking about [variable], is that correct?"
3. Provide list of available variables/crops

---

## Performance Metrics

Track these metrics to evaluate RAG effectiveness:

1. **Retrieval Precision**: % of queries where top RAG result matches ground truth
2. **LLM Accuracy**: % of queries where LLM selects correct variable/crop
3. **End-to-End Success**: % of queries that result in correct data retrieval
4. **Disambiguation Rate**: % of queries requiring user clarification
5. **Fallback Rate**: % of queries that trigger keyword fallback

Target: >90% end-to-end success for common query patterns

---

## References

- Variable Definitions: `data/OpenET_Data_Fields.html`
- Crop Codes: `data/CDL_Crop_Codes_Oregon.csv`
- Variable Keywords: `data/openet_variable_keywords.json`
- Crop Keywords: `data/crop_name_keywords.json`
- Current LLM Parser: `llm/interpretation.py`
- Validation Logic: `core/validation.py`
