from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import export_qa_bundle


def _write_fake_result(case_id: str) -> dict:
    result_dir = Path("results") / "partner_queries" / case_id
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
    return {
        "success": True,
        "files": {
            "png": str(result_dir / "chart.png"),
            "data": str(result_dir / "data.csv"),
            "resolved_query": str(result_dir / "resolved_query.json"),
        },
    }


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
    assert all(item["status"] == "success" for item in run_summary["cases"])


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
        ("workbook_row_17", "mdfo", ""),
        ("workbook_row_18", "imbo", ""),
        ("workbook_row_19", "mrso", ""),
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
    assert run_summary["cases"][0]["status"] == "no_data"
