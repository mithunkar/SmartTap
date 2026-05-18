from __future__ import annotations

import json
from pathlib import Path

from llm import interpretation
from llm.interpretation import get_task_specification
from scripts import evaluate_prompts


def test_http_ollama_client_posts_chat_requests(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({"message": {"content": "{\"task\": \"visualize_timeseries\"}"}}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(interpretation.urllib_request, "urlopen", fake_urlopen)

    client = interpretation._HttpOllamaClient(host="http://localhost:11434/")
    response = client.chat(model="demo-model", format="json", messages=[{"role": "user", "content": "hello"}])

    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["timeout"] == 90
    assert captured["body"]["stream"] is False
    assert response["message"]["content"] == "{\"task\": \"visualize_timeseries\"}"


def test_get_task_specification_accepts_prompt_path_and_model_override(tmp_path):
    prompt_path = tmp_path / "custom_prompt.txt"
    prompt_path.write_text(
        "Today is {today}.\n\n{variable_section}\n\n{agrimet_location_guidance}\n\nLast year: {last_year}\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_chat_client(**kwargs):
        captured.update(kwargs)
        return {
            "message": {
                "content": json.dumps(
                    {
                        "task": "statistical_summary",
                        "dataset": "agrimet",
                        "location": "Corvallis",
                        "variables": ["PC"],
                    }
                )
            }
        }

    spec = get_task_specification(
        "Show precipitation in Corvallis.",
        prompt_path=prompt_path,
        model_name="demo-model",
        chat_client=fake_chat_client,
    )

    assert captured["model"] == "demo-model"
    assert captured["format"] == "json"
    system_prompt = captured["messages"][0]["content"]  # type: ignore[index]
    assert "OPENET variables:" in system_prompt
    assert "AGRIMET variables:" in system_prompt
    assert "Common local examples" in system_prompt
    assert spec["dataset"] == "agrimet"
    assert spec["variables"] == ["PC"]


def test_load_cases_reads_expected_fixture_metadata():
    cases = evaluate_prompts.load_cases(evaluate_prompts.DEFAULT_CASE_SET)

    assert len(cases) >= 10
    assert {"retained", "stretch", "adversarial"} <= {case["scope"] for case in cases}
    assert "success-ready" in {case["expected_status"] for case in cases}
    assert "clarification" in {case["expected_status"] for case in cases}
    assert any("evidence_pattern" in case["must_match_fields"] for case in cases)


def test_evaluate_prompt_matrix_ranks_prompt_variants_and_tracks_stability(tmp_path):
    baseline_prompt = tmp_path / "baseline.txt"
    compact_prompt = tmp_path / "compact.txt"
    baseline_prompt.write_text("baseline", encoding="utf-8")
    compact_prompt.write_text("compact", encoding="utf-8")

    cases = [
        {
            "id": "retained_trend",
            "query": "How has the amount of farmland planted with alfalfa changed in Morrow County between 2014 and 2022?",
            "expected_partial_spec": {
                "task": "visualize_timeseries",
                "dataset": "openet",
                "location_type": "county",
                "variables": ["ACRES_FTR_GEOM"],
                "crop_filter": "Alfalfa",
                "start_date": "2014-01-01",
                "end_date": "2022-12-31",
                "evidence_pattern": "trend_single",
            },
            "expected_status": "success-ready",
            "must_match_fields": [
                "task",
                "dataset",
                "location_type",
                "variables",
                "crop_filter",
                "start_date",
                "end_date",
                "evidence_pattern",
            ],
            "scope": "retained",
            "notes": "",
        },
        {
            "id": "adversarial_precipitation",
            "query": "Show precipitation",
            "expected_partial_spec": {
                "task": "statistical_summary",
                "dataset": "agrimet",
                "variables": ["PC"],
            },
            "expected_status": "clarification",
            "must_match_fields": ["task", "dataset", "variables"],
            "scope": "adversarial",
            "notes": "",
        },
    ]

    seen_calls: dict[tuple[str, str], int] = {}

    def fake_parse(query: str, *, prompt_path: Path, model_name: str) -> dict[str, object]:
        del model_name
        call_key = (prompt_path.name, query)
        seen_calls[call_key] = seen_calls.get(call_key, 0) + 1

        if "alfalfa" in query.lower():
            if prompt_path.name == "compact.txt" and seen_calls[call_key] == 2:
                return {
                    "task": "visualize_timeseries",
                    "dataset": "openet",
                    "location_type": "county",
                    "variables": ["ACRES_FTR_GEOM"],
                    "crop_filter": "Hay",
                    "start_date": "2014-01-01",
                    "end_date": "2022-12-31",
                    "evidence_pattern": "trend_single",
                }
            return {
                "task": "visualize_timeseries",
                "dataset": "openet",
                "location_type": "county",
                "variables": ["ACRES_FTR_GEOM"],
                "crop_filter": "Alfalfa",
                "start_date": "2014-01-01",
                "end_date": "2022-12-31",
                "evidence_pattern": "trend_single",
            }

        return {
            "task": "statistical_summary",
            "dataset": "agrimet",
            "variables": ["PC"],
            "clarification_needed": ["location"],
        }

    def fake_execute(query: str, *, normalized_spec: dict[str, object]) -> dict[str, object]:
        del query
        assert normalized_spec["dataset"] == "openet"
        return {"success": True, "status": "success"}

    results = evaluate_prompts.evaluate_prompt_matrix(
        prompt_files=[baseline_prompt, compact_prompt],
        models=["demo-model"],
        cases=cases,
        repeats=2,
        include_execution=True,
        parse_fn=fake_parse,
        execute_fn=fake_execute,
    )

    assert len(results) == 2

    baseline = next(result for result in results if result["prompt_file"] == str(baseline_prompt))
    compact = next(result for result in results if result["prompt_file"] == str(compact_prompt))

    assert baseline["metrics"]["status_accuracy"] == 1.0
    assert baseline["metrics"]["stability_rate"] == 1.0
    assert baseline["metrics"]["retained_end_to_end_execution_rate"] == 1.0
    assert compact["metrics"]["required_field_match_rate"] < baseline["metrics"]["required_field_match_rate"]
    assert compact["metrics"]["stability_rate"] < baseline["metrics"]["stability_rate"]
    assert compact["composite_score"] < baseline["composite_score"]

    winner = evaluate_prompts._winner(results)
    assert winner is not None
    assert winner["prompt_file"] == str(baseline_prompt)
