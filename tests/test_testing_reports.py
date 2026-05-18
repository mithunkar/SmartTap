from __future__ import annotations

import json
from pathlib import Path

from scripts import build_testing_report, run_regression_suite


def test_parse_regression_outputs_extracts_key_metrics():
    pytest_output = "======================== 166 passed, 1 skipped in 12.71s ========================\n"
    vitest_output = """
 Test Files  2 passed (2)
      Tests  7 passed (7)
   Duration  1.23s
 The width(0) and height(0) of chart should be greater than 0
"""
    build_output = "dist/index.html 1.23 kB\nbuilt in 11.80s\nSome chunks are larger than 500 kB after minification.\n"

    pytest_summary = run_regression_suite.parse_pytest_output(pytest_output)
    vitest_summary = run_regression_suite.parse_vitest_output(vitest_output)
    build_summary = run_regression_suite.parse_build_output(build_output)

    assert pytest_summary == {
        "passed": 166,
        "failed": 0,
        "skipped": 1,
        "errors": 0,
        "duration_seconds": 12.71,
    }
    assert vitest_summary["test_files_passed"] == 2
    assert vitest_summary["tests_passed"] == 7
    assert vitest_summary["duration_seconds"] == 1.23
    assert vitest_summary["warnings"] == ["ChartRenderer zero-size warning in jsdom"]
    assert build_summary["duration_seconds"] == 11.8
    assert build_summary["bundle_size_warning"] is True


def test_retained_qa_summary_recovers_artifacts_from_bundle_folder_when_paths_are_stale(tmp_path):
    bundle_dir = tmp_path / "qa_bundle"
    case_dir = bundle_dir / "01_case"
    case_dir.mkdir(parents=True)
    for filename in ["chart.png", "data.csv", "spec.json", "validation.json"]:
        (case_dir / filename).write_text("x", encoding="utf-8")

    run_summary_path = bundle_dir / "run_summary.json"
    run_summary_path.write_text(
        json.dumps(
            {
                "total_cases": 1,
                "cases": [
                    {
                        "case_id": "case_01",
                        "folder": "01_case",
                        "status": "success",
                        "artifacts": {
                            "chart": "/stale/chart.png",
                            "csv": "/stale/data.csv",
                            "spec": "/stale/spec.json",
                            "validation": "/stale/validation.json",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_testing_report.retained_qa_summary(run_summary_path)

    assert summary["total_cases"] == 1
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 0
    assert summary["executed_prompt_success_count"] == 1
    assert summary["original_prompt_success_count"] == 1
    assert summary["original_prompt_not_evaluated_count"] == 0
    assert summary["artifact_generation_rate"] == 1.0
    assert summary["validation_report_generation_rate"] == 1.0


def test_workbook_eval_summary_categorizes_failure_modes_and_instability(tmp_path):
    workbook_path = tmp_path / "workbook.json"
    workbook_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total_queries": 2,
                    "included_in_pass_rate": 2,
                    "counts": {"pass": 0, "fail": 1, "needs_review": 1},
                    "pass_rate": 0.0,
                },
                "records": [
                    {
                        "failure_reasons": ["Expected variables to equal ['ETa']", "Missing summary fields: row_count"],
                        "unstable_fields": ["variables"],
                    },
                    {
                        "failure_reasons": [
                            "Expected crop_filter to equal 'Potato'",
                            "Expected evidence_pattern to equal 'trend_single'",
                            "Expected needs_clarification to be True",
                        ],
                        "unstable_fields": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_testing_report.workbook_eval_summary(workbook_path)

    assert summary["total_queries"] == 2
    assert summary["fail_count"] == 1
    assert summary["needs_review_count"] == 1
    assert summary["instability_count"] == 1
    categories = dict(summary["top_failure_categories"])
    assert categories["variable normalization mismatch"] == 1
    assert categories["missing summary fields"] == 1
    assert categories["crop extraction mismatch"] == 1
    assert categories["unsupported chart/evidence package type"] == 1
    assert categories["clarification missed when needed"] == 1


def test_retained_qa_summary_tracks_rewritten_cases_separately(tmp_path):
    run_summary_path = tmp_path / "run_summary.json"
    run_summary_path.write_text(
        json.dumps(
            {
                "total_cases": 2,
                "executed_prompt_successful_cases": 2,
                "original_prompt_successful_cases": 1,
                "original_prompt_not_evaluated_cases": 1,
                "rewritten_cases": 1,
                "cases": [
                    {"case_id": "case_01", "status": "success", "rewritten": False, "folder": "01_case", "artifacts": {}},
                    {
                        "case_id": "case_02",
                        "status": "success",
                        "rewritten": True,
                        "original_prompt_status": "rewritten_not_evaluated",
                        "folder": "02_case",
                        "artifacts": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "01_case").mkdir()
    (tmp_path / "02_case").mkdir()

    summary = build_testing_report.retained_qa_summary(run_summary_path)

    assert summary["rewritten_count"] == 1
    assert summary["executed_prompt_success_count"] == 2
    assert summary["original_prompt_success_count"] == 1
    assert summary["original_prompt_not_evaluated_count"] == 1


def test_build_testing_report_main_writes_slide_ready_outputs(tmp_path):
    regression_dir = tmp_path / "regression"
    regression_dir.mkdir()
    (regression_dir / "summary.json").write_text(
        json.dumps(
            {
                "summary": {"all_green": True},
                "steps": {
                    "backend_pytest": {"metrics": {"passed": 166, "skipped": 1}},
                    "frontend_vitest": {"metrics": {"tests_passed": 7, "test_files_passed": 2}},
                    "frontend_build": {"metrics": {"bundle_size_warning": True}},
                },
            }
        ),
        encoding="utf-8",
    )

    prompt_dir = tmp_path / "prompt"
    prompt_dir.mkdir()
    (prompt_dir / "summary.json").write_text(
        json.dumps(
            {
                "results": [{"prompt_label": "prompts/interpretation.txt", "model": "demo-model"}],
                "winner": {
                    "prompt_label": "prompts/interpretation.txt",
                    "model": "demo-model",
                    "composite_score": 0.95,
                    "metrics": {"required_field_match_rate": 1.0, "stability_rate": 1.0},
                },
            }
        ),
        encoding="utf-8",
    )

    qa_dir = tmp_path / "qa"
    case_dir = qa_dir / "01_case"
    case_dir.mkdir(parents=True)
    for filename in ["chart.png", "data.csv", "spec.json", "validation.json"]:
        (case_dir / filename).write_text("x", encoding="utf-8")
    qa_path = qa_dir / "run_summary.json"
    qa_path.write_text(
        json.dumps(
            {
                "total_cases": 1,
                "cases": [{"case_id": "case_01", "folder": "01_case", "status": "success", "artifacts": {}}],
            }
        ),
        encoding="utf-8",
    )

    workbook_path = tmp_path / "workbook.json"
    workbook_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total_queries": 2,
                    "included_in_pass_rate": 2,
                    "counts": {"pass": 0, "fail": 1, "needs_review": 1},
                    "pass_rate": 0.0,
                },
                "records": [{"failure_reasons": ["Expected dataset to equal 'openet'"], "unstable_fields": []}],
            }
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "testing_story"
    exit_code = build_testing_report.main(
        [
            "--regression-report",
            str(regression_dir),
            "--prompt-report",
            str(prompt_dir),
            "--qa-run-summary",
            str(qa_path),
            "--workbook-eval",
            str(workbook_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["regression_suite"]["all_green"] is True
    assert summary["prompt_benchmark"]["winner"]["prompt_label"] == "prompts/interpretation.txt"
    assert summary["retained_qa"]["artifact_generation_rate"] == 1.0
    assert summary["retained_qa"]["original_prompt_success_count"] == 1
    assert summary["workbook_stress"]["top_failure_categories"][0][0] == "dataset routing mismatch"
    assert (output_dir / "summary.md").exists()
    assert (output_dir / "summary.csv").exists()
