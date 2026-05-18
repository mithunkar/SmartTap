from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import export_qa_bundle
from core.paths import QA_ARTIFACTS_DIR


def _write_fake_result(case_id: str, *, include_validation: bool = False) -> dict:
    result_dir = Path("outputs") / "partner_queries" / case_id
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "chart.png").write_bytes(b"png-bytes")
    (result_dir / "data.csv").write_text("datetime,value\n2024-01-01,1.0\n", encoding="utf-8")
    (result_dir / "resolved_query.json").write_text(
        json.dumps(
            {
                "prompt": f"Prompt for {case_id}",
                "spec": {"partner_query_id": case_id},
                "summary": {"dataset": "openet"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    files = {
        "png": str(result_dir / "chart.png"),
        "data": str(result_dir / "data.csv"),
        "resolved_query": str(result_dir / "resolved_query.json"),
    }
    if include_validation:
        (result_dir / "validation.json").write_text(json.dumps({"status": "ok"}, indent=2), encoding="utf-8")
        files["validation"] = str(result_dir / "validation.json")

    return {
        "success": True,
        "files": files,
    }


def test_export_qa_bundle_default_output_dir_points_to_tracked_artifacts():
    assert export_qa_bundle.DEFAULT_OUTPUT_DIR == QA_ARTIFACTS_DIR


def test_export_qa_bundle_writes_ordered_folders_and_summary(tmp_path, monkeypatch):
    seen_specs: list[dict] = []

    def fake_process_query(prompt: str, spec: dict) -> dict:
        del prompt
        seen_specs.append(dict(spec))
        return _write_fake_result(spec["partner_query_id"])

    monkeypatch.setattr(export_qa_bundle, "process_query", fake_process_query)

    output_dir = tmp_path / "QA"
    exit_code = export_qa_bundle.main(["--output-dir", str(output_dir), "--clean"])

    assert exit_code == 0
    assert len(seen_specs) == 19

    expected_folders = [f"{index:02d}_workbook_row_{index + 1:02d}" for index in range(1, 20)]
    assert [path.name for path in sorted(output_dir.iterdir()) if path.is_dir()] == expected_folders

    for folder_name in expected_folders:
        case_dir = output_dir / folder_name
        assert (case_dir / "chart.png").exists()
        assert (case_dir / "data.csv").exists()
        assert (case_dir / "spec.json").exists()

    run_summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert run_summary["total_cases"] == 19
    assert run_summary["successful_cases"] == 19
    assert run_summary["failed_cases"] == 0
    assert run_summary["acceptance_target"] == "original_prompt"
    assert run_summary["executed_prompt_successful_cases"] == 19
    assert run_summary["original_prompt_successful_cases"] == 16
    assert run_summary["original_prompt_not_evaluated_cases"] == 3
    assert run_summary["rewritten_cases"] == 3
    assert all(item["status"] == "success" for item in run_summary["cases"])
    rewritten_case = next(item for item in run_summary["cases"] if item["case_id"] == "workbook_row_15")
    assert rewritten_case["rewritten"] is True
    assert rewritten_case["executed_prompt_pass"] is True
    assert rewritten_case["original_prompt_status"] == "rewritten_not_evaluated"
    assert rewritten_case["original_prompt_pass"] is False
    assert rewritten_case["original_prompt"].startswith("How did water demand change near Pendleton")

    spec_payload = json.loads((output_dir / "14_workbook_row_15" / "spec.json").read_text(encoding="utf-8"))
    assert spec_payload["rewritten"] is True
    assert spec_payload["original_prompt"].startswith("How did water demand change near Pendleton")
    assert spec_payload["qa_review"]["rewritten"] is True
    assert spec_payload["qa_review"]["executed_prompt_pass"] is True
    assert spec_payload["qa_review"]["original_prompt_status"] == "rewritten_not_evaluated"
    assert spec_payload["qa_review"]["original_prompt_pass"] is False


def test_export_qa_bundle_does_not_apply_case_specific_station_overrides(tmp_path, monkeypatch):
    captured: list[tuple[str, str | None, str]] = []

    def fake_process_query(prompt: str, spec: dict) -> dict:
        del prompt
        captured.append((spec["partner_query_id"], spec.get("station_id"), os.environ.get("AGRIMET_USE_API", "")))
        return _write_fake_result(spec["partner_query_id"])

    monkeypatch.setattr(export_qa_bundle, "process_query", fake_process_query)

    output_dir = tmp_path / "QA"
    exit_code = export_qa_bundle.main(
        [
            "--output-dir",
            str(output_dir),
            "--case-ids",
            "workbook_row_17",
            "workbook_row_18",
            "workbook_row_19",
            "workbook_row_20",
        ]
    )

    assert exit_code == 0
    assert captured == [
        ("workbook_row_17", "crvo", ""),
        ("workbook_row_18", "imbo", ""),
        ("workbook_row_19", "ptro", ""),
        ("workbook_row_20", "subo", ""),
    ]


def test_export_qa_bundle_counts_no_data_as_completed(tmp_path, monkeypatch):
    def fake_process_query(prompt: str, spec: dict) -> dict:
        del prompt
        result = _write_fake_result(spec["partner_query_id"])
        result["summary"] = {"status": "no_data"}
        return result

    monkeypatch.setattr(export_qa_bundle, "process_query", fake_process_query)

    output_dir = tmp_path / "QA"
    exit_code = export_qa_bundle.main(["--output-dir", str(output_dir), "--case-ids", "workbook_row_10"])

    assert exit_code == 0
    run_summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert run_summary["successful_cases"] == 1
    assert run_summary["failed_cases"] == 0
    assert run_summary["executed_prompt_successful_cases"] == 1
    assert run_summary["original_prompt_successful_cases"] == 1
    assert run_summary["original_prompt_not_evaluated_cases"] == 0
    assert run_summary["cases"][0]["status"] == "no_data"
    assert run_summary["cases"][0]["no_data_reason"] is None


def test_export_qa_bundle_surfaces_no_data_reason_and_rewrite_metadata(tmp_path, monkeypatch):
    def fake_process_query(prompt: str, spec: dict) -> dict:
        del prompt
        result = _write_fake_result(spec["partner_query_id"])
        result["summary"] = {
            "status": "no_data",
            "dataset": "agrimet",
            "location": "La Grande",
            "station_id": "imbo",
            "variable_labels": ["Average Humidity (percent)"],
            "no_data_reason": "No usable AgriMet values were available.",
        }
        return result

    monkeypatch.setattr(export_qa_bundle, "process_query", fake_process_query)

    output_dir = tmp_path / "QA"
    exit_code = export_qa_bundle.main(["--output-dir", str(output_dir), "--case-ids", "workbook_row_02"])

    assert exit_code == 0
    run_summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    case_summary = run_summary["cases"][0]
    assert case_summary["status"] == "no_data"
    assert case_summary["no_data_reason"] == "No usable AgriMet values were available."
    assert case_summary["rewritten"] is False
    assert case_summary["executed_prompt_pass"] is True
    assert case_summary["original_prompt_pass"] is True

    spec_payload = json.loads((output_dir / "01_workbook_row_02" / "spec.json").read_text(encoding="utf-8"))
    assert spec_payload["qa_review"]["status"] == "no_data"
    assert spec_payload["qa_review"]["executed_prompt_status"] == "no_data"
    assert spec_payload["qa_review"]["original_prompt_status"] == "no_data"
    assert spec_payload["qa_review"]["no_data_reason"] == "No usable AgriMet values were available."


def test_export_qa_bundle_copies_validation_artifact_when_present(tmp_path, monkeypatch):
    def fake_process_query(prompt: str, spec: dict) -> dict:
        del prompt
        return _write_fake_result(spec["partner_query_id"], include_validation=True)

    monkeypatch.setattr(export_qa_bundle, "process_query", fake_process_query)

    output_dir = tmp_path / "QA"
    exit_code = export_qa_bundle.main(["--output-dir", str(output_dir), "--case-ids", "workbook_row_02"])

    assert exit_code == 0
    case_dir = output_dir / "01_workbook_row_02"
    assert (case_dir / "validation.json").exists()

    run_summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    artifacts = run_summary["cases"][0]["artifacts"]
    assert artifacts["validation"].endswith("validation.json")
