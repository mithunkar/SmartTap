# SmartTap Variable & Crop Keyword Mapping System

**Date**: February 2025  
**Purpose**: Define keyword mappings and identification logic for OpenET variables and crop names in the SmartTap natural language interface

---

## Quick Reference

### 📁 Files Created

1. **`data/openet_variable_keywords.json`**
   - Comprehensive mapping of 12 OpenET variables to keywords/synonyms
   - Each variable includes: name, description, units, keywords, related concepts, example queries
   
2. **`data/crop_name_keywords.json`**
   - Mapping of crop names organized by crop groups (Grain, Row Crop, Hay/Forage, Tree Fruit, etc.)
   - Includes CDL codes, synonyms, and query patterns
   - Covers 102 crop types from Oregon CDL

3. **`docs/RAG_IDENTIFICATION_LOGIC.md`**
   - Full specification of LLM + RAG identification logic
   - Step-by-step process for variable and crop identification
   - Dataset routing rules, query examples, error handling

4. **`llm/keyword_matcher.py`**
   - Python utility for keyword-based matching
   - Used as fallback when LLM is uncertain
   - Includes scoring algorithm and confidence levels

5. **`llm/interpretation.py`** (updated)
   - Enhanced LLM prompt to include OpenET variable keywords
   - Loads keyword mappings dynamically

---

## OpenET Variable Mappings

### Core Variables

| Variable | Description | Key Keywords |
|----------|-------------|--------------|
| **ETa** | Actual Evapotranspiration | evapotranspiration, ET, water use, water consumption, crop water use |
| **PPT** | Gross Precipitation | precipitation, rain, rainfall |
| **P_rz** | Effective Precipitation | effective rain, usable rain, root zone precipitation |
| **AW** | Applied Water | applied water, irrigation applied, total irrigation |
| **IRR_CU_VOLUME** | Consumptive Use (Irrigation) | consumptive use, irrigation consumption, net irrigation |
| **NIWR_VOLUME** | Net Irrigation Water Requirement | irrigation requirement, irrigation need, crop water demand |
| **CROP** | Crop Type | crop, crop type, what crop, planted crop |
| **IRR_STATUS** | Irrigation Status | irrigated, irrigation active |
| **per_IRRIGATED** | Percent Irrigated | percent irrigated, irrigation coverage |
| **AREA** | Field Area | area, field size, acreage, hectares |
| **srctype** | Water Source Type | water source, groundwater, surface water |

### Example Query Mappings

- "How much water did crops use?" → **ETa**
- "What's the irrigation requirement?" → **NIWR_VOLUME**
- "Show me rainfall" → **PPT**
- "How much irrigation water was consumed?" → **IRR_CU_VOLUME**

---

## Crop Name Mappings

### Crop Groups & Examples

**Grain** (wheat, oats, barley)
- Winter Wheat (CDL 24): "winter wheat", "wheat"
- Spring Wheat (CDL 23): "spring wheat", "wheat"
- Barley (CDL 21): "barley"

**Row Crop** (corn, soybeans, potatoes)
- Corn (CDL 1): "corn", "maize", "field corn"
- Potatoes (CDL 43): "potatoes", "potato", "spuds"
- Soybeans (CDL 5): "soybeans", "soy"

**Hay/Forage** (alfalfa, grass hay)
- Alfalfa (CDL 36): "alfalfa", "lucerne"
- Other Hay (CDL 37): "hay", "grass hay", "timothy"
- Pasture/Hay (CDL 181): "pasture", "pasture hay"

**Tree Fruit/Nuts** (orchards)
- Cherries (CDL 72): "cherries", "cherry", "cherry orchard"
- Grapes (CDL 69): "grapes", "grape", "vineyard"
- Apples (CDL 68): "apples", "apple orchard"

**Vegetables**
- Onions (CDL 49): "onions", "onion"
- Lettuce (CDL 50): "lettuce", "greens"
- Carrots (CDL 206): "carrots", "carrot"

### Normalization Rules
- **Case-insensitive**: "WHEAT" = "wheat" = "Wheat"
- **Plural handling**: "cherries" → "cherry"
- **Synonyms**: "maize" → "corn", "lucerne" → "alfalfa"
- **Partial matching**: "wheat" matches both Winter Wheat and Spring Wheat

---

## Identification Logic Flow

```
User Query
    ↓
┌─────────────────────────┐
│  RAG Retrieval Layer    │  ← Semantic search over keyword mappings
│  (Future Enhancement)   │     Returns top-k candidates
└───────────┬─────────────┘
            ↓
┌─────────────────────────┐
│  LLM Parser             │  ← Receives query + RAG context
│  (llm/interpretation.py)│     Outputs structured JSON
└───────────┬─────────────┘
            ↓
┌─────────────────────────┐
│  Validation Layer       │  ← Keyword fallback if LLM uncertain
│  (llm/keyword_matcher)  │     Confirms variable/crop validity
└───────────┬─────────────┘
            ↓
      Structured Spec
```

### Current Implementation (Phase 1)
- Keyword mappings loaded into prompt
- Enhanced system prompt with OpenET variable descriptions
- Keyword matcher utility for fallback
- Dataset routing based on variable type

### Future Enhancements (Phase 2)
- ⬜ RAG retrieval with semantic embeddings
- ⬜ Query ambiguity detection and clarification
- ⬜ Fine-tuning keyword weights from user feedback

---

## Dataset Routing

**Rule**: Route to OpenET if variable is in OpenET variable list, otherwise AgriMet

### OpenET Variables
- Data Location: `data/archive/openet_csv_out/{variable}_long.csv`
- Variables: ETa, PPT, P_rz, AW, IRR_CU_VOLUME, NIWR_VOLUME, CROP, IRR_STATUS, per_IRRIGATED, AREA, srctype
- Supports crop filtering via CDL codes
- Geographic attributes from `field_points.gpkg`

### AgriMet Variables
- Data Location: `data/agrimet/{station}_weather_{year}.csv`
- Variables: OBM (temp), MX (max temp), MN (min temp), PC (precip), SR (solar), WS (wind), TU (humidity)
- Weather station based (Corvallis, Hood River, Klamath Falls, etc.)

---

## Usage Examples

### Python API

```python
from llm.keyword_matcher import KeywordMatcher

# Initialize matcher
matcher = KeywordMatcher()

# Match a query
result = matcher.match_query("How much water did alfalfa use?")

print(result["variables"][0])
# Output: {'variable': 'ETa', 'description': 'Actual Evapotranspiration', 'score': 0.95, 'confidence': 'high'}

print(result["crops"][0])
# Output: {'cdl_code': 36, 'crop_name': 'Alfalfa', 'score': 0.98, 'confidence': 'high'}
```

### Test the Matcher

```bash
cd /Users/mithunkarthikeyan/Desktop/Projects/SmartTap
python -m llm.keyword_matcher
```

---

## Query Examples & Expected Outputs

| User Query | Variable Match | Crop Match | Dataset |
|-----------|---------------|------------|---------|
| "How much ET in 2023?" | ETa (0.92) | - | OpenET |
| "Show me winter wheat fields" | - | Winter Wheat/24 (0.95) | OpenET |
| "What's the irrigation requirement for alfalfa?" | NIWR_VOLUME (0.91) | Alfalfa/36 (0.98) | OpenET |
| "Rainfall in Hood River" | PPT (0.95) | - | OpenET |
| "Cherry orchard water use" | ETa (0.87) | Cherries/72 (0.94) | OpenET |
| "Temperature last week" | OBM (0.88) | - | AgriMet |

---

## Performance Targets

- **Retrieval Precision**: >85% of queries should have correct variable/crop in top-3 results
- **LLM Accuracy**: >90% correct variable/crop selection
- **End-to-End Success**: >90% queries result in correct data retrieval
- **Disambiguation Rate**: <10% queries require user clarification

---

## Next Steps

1. **Test keyword matcher** with sample queries
2. **Integrate into validation.py** for LLM fallback
3. **Implement RAG retrieval** using sentence transformers (Phase 2)
4. **Collect user feedback** to refine keyword weights
5. **Add ambiguity detection** for queries matching multiple variables/crops

---

## Files Reference

- **Keyword Mappings**: 
  - [data/openet_variable_keywords.json](../data/openet_variable_keywords.json)
  - [data/crop_name_keywords.json](../data/crop_name_keywords.json)

- **RAG Logic**: [docs/RAG_IDENTIFICATION_LOGIC.md](RAG_IDENTIFICATION_LOGIC.md)

- **Implementation**:
  - [llm/keyword_matcher.py](../llm/keyword_matcher.py)
  - [llm/interpretation.py](../llm/interpretation.py)

- **Data Sources**:
  - [data/OpenET_Data_Fields.html](../data/OpenET_Data_Fields.html) - Variable definitions
  - [data/CDL_Crop_Codes_Oregon.csv](../data/CDL_Crop_Codes_Oregon.csv) - Crop code crosswalk
  - [data/field_points.gpkg](../data/field_points.gpkg) - Field centroids with geographic attributes

---

**Questions?** See the full RAG logic documentation for detailed implementation guidance.
