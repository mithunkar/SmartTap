# Multi-Model Evaluation Guide

## Overview

SmartTap now supports testing different LLM models and comparing their performance. This allows you to:
- Compare accuracy across different models
- Measure parsing speed differences
- Find the best model for your use case
- Track model performance over time

## Supported Models

The following models are configured by default:

| Model | Size | Description |
|-------|------|-------------|
| **gemma2:2b** | 2B | Google's Gemma 2 (default) |
| **llama3.2:3b** | 3B | Meta's Llama 3.2 |
| **qwen2.5:3b** | 3B | Alibaba's Qwen 2.5 |
| **phi3:mini** | 3.8B | Microsoft's Phi-3 |
| **mistral:7b** | 7B | Mistral AI's Mistral |
| **llama3.1:8b** | 8B | Meta's Llama 3.1 |

## Setting the Model

### Environment Variable

Set the model for all SmartTap operations:

```bash
export SMARTTAP_MODEL="llama3.2:3b"
python3 smarttap.py "Show me temperature in Corvallis"
```

### Programmatic

```python
from llm.config import set_model_name

set_model_name("phi3:mini")
# Now all queries use phi3:mini
```

### Default Model

If no model is specified, SmartTap uses `gemma2:2b`.

## Running Comparisons

### Quick Comparison (3 models)

Test 3 popular models with accuracy tests only:

```bash
python3 tests/model_comparison.py --quick
```

Output:
```
MULTI-MODEL EVALUATION
======================================================================
Testing 3 models...

🔬 Testing: Gemma 2 (2B)
   ------------------------------------------------------------
   ✅ agrimet_temp_simple (4.21s)
   ✅ agrimet_precip_simple (3.89s)
   ...

COMPARISON SUMMARY
======================================================================
Model                          Accuracy     Avg Parse    Grade     
----------------------------------------------------------------------
Llama 3.2 (3B)                 100.0%       3.45s       🏆 Excellent
Gemma 2 (2B)                   100.0%       4.12s       🏆 Excellent
Phi-3 Mini (3.8B)              85.7%        2.89s       ✅ Very Good

🥇 BEST MODEL: Llama 3.2 (3B)
   Accuracy: 100.0%
   Speed: 3.45s average parse time
   Correct: 7/7 test cases
```

### Full Comparison (All models)

Test all supported models:

```bash
python3 tests/model_comparison.py
```

### Specific Models

Test only specific models:

```bash
python3 tests/model_comparison.py --models gemma2:2b llama3.2:3b
```

### With Performance Benchmarks

Include end-to-end performance tests (takes longer):

```bash
python3 tests/model_comparison.py --quick --performance
```

This adds:
- Full pipeline execution time
- Data fetching + visualization timing
- Real-world usage scenarios

## Interpreting Results

### Accuracy Metrics

- **100%**: Perfect parsing, all test cases correct
- **>90%**: Excellent, production-ready
- **70-90%**: Good, may need prompt tuning
- **<70%**: Fair, consider different model

### Performance Metrics

- **Parse Time**: How fast the model converts natural language to JSON
  - <3s: Very fast
  - 3-5s: Fast
  - 5-10s: Acceptable
  - >10s: Slow

- **Total Time**: Full query → chart pipeline
  - <10s: Excellent
  - 10-15s: Good
  - 15-25s: Acceptable
  - >25s: Needs improvement

### Grade System

- 🏆 **Excellent**: ≥95% accuracy
- ✅ **Very Good**: ≥85% accuracy
- 👍 **Good**: ≥70% accuracy
- ⚠️ **Fair**: <70% accuracy

## Results Storage

Results are saved to `evaluation_results/model_comparison_YYYYMMDD_HHMMSS.json`:

```json
{
  "timestamp": "2026-02-09T14:30:22",
  "models_tested": 3,
  "results": {
    "gemma2:2b": {
      "model": "gemma2:2b",
      "display_name": "Gemma 2 (2B)",
      "accuracy": 1.0,
      "correct": 7,
      "total": 7,
      "avg_parse_time": 4.12,
      "errors": []
    }
  }
}
```

## Model Selection Guide

### Choose by Priority

**Best Accuracy**: 
- llama3.2:3b or llama3.1:8b
- 100% accuracy on test suite

**Best Speed**:
- phi3:mini
- ~3s parse time

**Best Balance**:
- gemma2:2b (default)
- Good accuracy + reasonable speed

**Most Powerful**:
- llama3.1:8b or mistral:7b
- Higher context understanding

### By Use Case

**Production API** (response time critical):
```bash
export SMARTTAP_MODEL="phi3:mini"
```

**Accuracy Critical** (research, analysis):
```bash
export SMARTTAP_MODEL="llama3.1:8b"
```

**General Use** (balanced):
```bash
export SMARTTAP_MODEL="gemma2:2b"  # or leave default
```

**Low Memory** (resource constrained):
```bash
export SMARTTAP_MODEL="gemma2:2b"
```

## Prerequisites

Models must be installed with ollama:

```bash
# Install a model
ollama pull gemma2:2b

# List installed models
ollama list

# Install multiple models for comparison
ollama pull llama3.2:3b
ollama pull phi3:mini
ollama pull qwen2.5:3b
```

## Advanced Usage

### Custom Model List

Edit `llm/config.py`:

```python
SUPPORTED_MODELS = [
    "your-custom-model",
    "another-model:version",
]
```

### Add Model Display Names

```python
MODEL_DISPLAY_NAMES = {
    "your-custom-model": "Your Custom Model Name",
}
```

### Test Single Model

```bash
export SMARTTAP_MODEL="your-model"
python3 tests/evaluation_metrics.py
```

## Continuous Monitoring

Track model performance over time:

```bash
# Run weekly comparisons
python3 tests/model_comparison.py --quick > weekly_comparison.log

# Compare results
ls -lt evaluation_results/model_comparison_*.json | head -5
```

## Troubleshooting

### Model Not Found

```
Error: Model 'llama3.2:3b' not found
```

Solution:
```bash
ollama pull llama3.2:3b
```

### Slow Performance

- Smaller models (2-3B) are faster
- Check CPU/GPU availability
- Reduce test case count for quick tests

### Low Accuracy

- Try larger models (7B+)
- Adjust system prompt in `llm/interpretation.py`
- Add more test cases to `tests/fixtures/test_cases.json`

## Examples

### Find Best Model for Your Dataset

```bash
# Test all models with performance
python3 tests/model_comparison.py --performance

# Review results
cat evaluation_results/model_comparison_*.json | tail -1 | jq '.results[] | {model, accuracy, avg_parse_time}'
```

### A/B Test Two Models

```bash
# Test model A
export SMARTTAP_MODEL="gemma2:2b"
python3 tests/evaluation_metrics.py

# Test model B
export SMARTTAP_MODEL="llama3.2:3b"
python3 tests/evaluation_metrics.py

# Compare results
diff evaluation_results/evaluation_*.json
```

### Production Deployment

```bash
# Run thorough evaluation
python3 tests/model_comparison.py --performance

# Select best model based on results
export SMARTTAP_MODEL="llama3.2:3b"

# Set in production environment
echo 'export SMARTTAP_MODEL="llama3.2:3b"' >> ~/.bashrc

# Verify
python3 -c "from llm.config import get_model_name; print(get_model_name())"
```

## Contributing

To add support for new models:

1. Install model: `ollama pull model-name`
2. Add to `SUPPORTED_MODELS` in `llm/config.py`
3. Add display name to `MODEL_DISPLAY_NAMES`
4. Run comparison: `python3 tests/model_comparison.py --models model-name`
5. Document results

---

**Created**: February 9, 2026  
**Purpose**: Multi-model evaluation and comparison for SmartTap
