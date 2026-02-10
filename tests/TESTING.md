# SmartTap Testing & Evaluation Framework

## Overview

This testing framework provides comprehensive evaluation of SmartTap's functionality, performance, and accuracy.

## Test Structure

```
tests/
├── fixtures/
│   └── test_cases.json          # Test queries with expected results
├── test_data_fetcher.py         # Unit tests for data loading
├── test_llm_parsing.py          # LLM accuracy evaluation
├── test_llm_routing.py          # Dataset routing tests
├── test_pipeline.py             # End-to-end integration tests
└── evaluation_metrics.py        # Performance & quality metrics

run_tests.py                     # Master test runner
```

## Running Tests

### Quick Start

Run all tests with the master test runner:

```bash
python3 run_tests.py
```

This will:
1. Run all unit and integration tests
2. Measure performance benchmarks
3. Evaluate LLM parsing accuracy
4. Generate a comprehensive evaluation report

### Individual Test Suites

**Unit Tests (Data Fetching)**
```bash
python3 -m pytest tests/test_data_fetcher.py -v
# or
python3 tests/test_data_fetcher.py
```

Tests:
- AgriMet data loading
- OpenET data loading
- Multiple variable handling
- Date filtering
- Invalid location handling

**LLM Parsing Accuracy**
```bash
python3 tests/test_llm_parsing.py
```

Tests:
- Natural language → JSON conversion
- Dataset routing (ET → OpenET, temp → AgriMet)
- Location extraction
- Variable identification
- Date parsing

**Dataset Routing**
```bash
python3 tests/test_llm_routing.py
```

Tests:
- Variable-based routing logic
- AgriMet vs OpenET selection
- Edge cases (precipitation in Klamath Falls)

**Integration Tests**
```bash
python3 tests/test_pipeline.py
```

Tests:
- Full query → chart pipeline
- Multi-variable queries
- Different chart types
- Error handling

### Performance Evaluation

Run performance benchmarks:

```bash
python3 tests/evaluation_metrics.py
```

Measures:
- **Response time**: Parse, fetch, validate, visualize
- **Data quality**: Record counts, validation warnings
- **LLM accuracy**: Parsing correctness percentage
- **Throughput**: PNG generation speed

Results are saved to `evaluation_results/evaluation_YYYYMMDD_HHMMSS.json`

### Multi-Model Comparison (NEW!)

Compare different LLM models to find the best one for your use case:

```bash
# Quick comparison (3 popular models)
python3 tests/model_comparison.py --quick

# Full comparison (all 6 supported models)
python3 tests/model_comparison.py

# Test specific models
python3 tests/model_comparison.py --models gemma2:2b llama3.2:3b

# Include performance benchmarks
python3 tests/model_comparison.py --quick --performance
```

**Supported Models:**
- `gemma2:2b` (default) - Google's Gemma 2
- `llama3.2:3b` - Meta's Llama 3.2
- `qwen2.5:3b` - Alibaba's Qwen 2.5
- `phi3:mini` - Microsoft's Phi-3
- `mistral:7b` - Mistral AI's Mistral
- `llama3.1:8b` - Meta's Llama 3.1

**Output:**
- Accuracy comparison (% of test cases parsed correctly)
- Speed comparison (average parse time)
- Grade for each model (🏆 Excellent, ✅ Very Good, 👍 Good)
- Recommended best model

Results saved to `evaluation_results/model_comparison_YYYYMMDD_HHMMSS.json`

**See [MODEL_EVALUATION.md](../MODEL_EVALUATION.md) for detailed guide.**

## Test Cases

Test cases are defined in `tests/fixtures/test_cases.json`:

### LLM Parsing Tests

Example test case:
```json
{
  "id": "agrimet_temp_simple",
  "query": "Show me temperature in Corvallis for 2020",
  "expected": {
    "dataset": "agrimet",
    "location": "corvallis",
    "variables": ["OBM"],
    "start_date": "2020-01-01",
    "end_date": "2020-12-31"
  }
}
```

### Performance Benchmarks

Queries tested:
1. Simple AgriMet query (should complete < 15s)
2. OpenET query (should complete < 20s)
3. Multi-variable query
4. Multi-year query (2015-2020)

## Success Criteria

### Unit Tests
- ✅ All data fetching tests pass
- ✅ Date filtering works correctly
- ✅ Invalid inputs raise appropriate errors

### LLM Accuracy
- ✅ ≥70% parsing accuracy (acceptable)
- ✅ ≥90% parsing accuracy (excellent)
- ✅ Dataset routing is 100% correct

### Performance
- ✅ Average query time < 15s (good)
- ✅ Average query time < 25s (acceptable)
- ✅ No query should take > 30s

### Integration
- ✅ Full pipeline completes without errors
- ✅ Chart generation produces valid PNG
- ✅ Vega spec is valid JSON

## Adding New Tests

### 1. Add Test Case to Fixtures

Edit `tests/fixtures/test_cases.json`:

```json
{
  "llm_parsing_tests": [
    {
      "id": "your_test_id",
      "query": "Your natural language query",
      "expected": {
        "dataset": "agrimet",
        "location": "corvallis",
        "variables": ["OBM"]
      }
    }
  ]
}
```

### 2. Add Unit Test

Create or edit test file in `tests/`:

```python
def test_your_feature(self):
    """Test description"""
    # Arrange
    spec = {...}
    
    # Act
    result = your_function(spec)
    
    # Assert
    self.assertEqual(result, expected_value)
```

### 3. Run Tests

```bash
python3 run_tests.py
```

## Interpreting Results

### Test Output

```
SMARTTAP TEST SUITE
======================================================================
test_agrimet_basic_fetch (test_data_fetcher.TestDataFetcher) ... ok
test_parsing_accuracy (test_llm_parsing.TestLLMParsing) ... ok
...

TEST SUMMARY
======================================================================
Tests run: 18
Successes: 17
Failures: 1
Errors: 0
```

### Performance Report

```
BENCHMARK SUMMARY
======================================================================
Successful: 5/5
Average time: 12.34s
Min time: 8.21s
Max time: 18.67s
✅ Performance: GOOD (avg < 15s)
```

### Accuracy Report

```
LLM PARSING ACCURACY: 6/7 (85.7%)
======================================================================
❌ agrimet_bar_chart: Field 'chart_type' expected 'bar', got 'line'
```

### Evaluation JSON

Results saved to `evaluation_results/evaluation_20260209_143022.json`:

```json
{
  "timestamp": "2026-02-09T14:30:22",
  "performance": {
    "summary": {
      "total_tests": 5,
      "successful": 5,
      "avg_time": 12.34,
      "max_time": 18.67
    }
  },
  "accuracy": {
    "accuracy": 0.857,
    "correct": 6,
    "total": 7
  }
}
```

## Continuous Integration

To run tests in CI/CD:

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests with coverage
python3 -m pytest tests/ --cov=core --cov=llm

# Run benchmarks
python3 tests/evaluation_metrics.py

# Check results
if [ $? -eq 0 ]; then
  echo "Tests passed"
else
  echo "Tests failed"
  exit 1
fi
```

## Troubleshooting

### Import Errors

If you get `ModuleNotFoundError`:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python3 run_tests.py
```

### LLM Service Not Running

Tests requiring LLM (test_llm_parsing.py) need ollama running:
```bash
ollama serve
ollama run gemma2:2b
```

### Missing OpenET Data

Some tests are skipped if OpenET data is not available. To enable:
```bash
python3 scripts/convert_openet_gpkg.py
python3 scripts/combine_openet_huc.py
```

### Slow Tests

If tests are timing out:
- Check ollama is running locally (not remote)
- Reduce test data size in fixtures
- Increase timeout thresholds in evaluation_metrics.py

## Best Practices

1. **Run tests before commits**
   ```bash
   python3 run_tests.py
   ```

2. **Add tests for new features**
   - Add test case to fixtures/test_cases.json
   - Add unit test if needed
   - Update this documentation

3. **Monitor performance**
   - Run evaluation_metrics.py weekly
   - Track trends in evaluation_results/
   - Investigate performance regressions

4. **Keep tests fast**
   - Use small date ranges for test queries
   - Mock LLM responses if possible
   - Parallelize independent tests