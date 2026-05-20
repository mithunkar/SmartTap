from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smarttap_service import process_query
from core.paths import QA_ARTIFACTS_DIR


FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "acceptance_queries.json"
DEFAULT_OUTPUT_DIR = QA_ARTIFACTS_DIR
CASE_ID_RANGE = range(2, 21)
CASE_IDS = {f"workbook_row_{index:02d}" for index in CASE_ID_RANGE}
SUCCESS_STATUSES = {"success", "no_data"}


def load_fixture_cases() -> List[Dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    return [case for case in cases if case.get("id") in CASE_IDS]


def case_positions(cases: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    return {str(case["id"]): index for index, case in enumerate(cases, start=1)}


def parse_case_ids(values: List[str] | None) -> List[str] | None:
    if not values:
        return None

    parsed: List[str] = []
    for value in values:
        parts = [part.strip() for part in value.split(",")]
        parsed.extend(part for part in parts if part)
    return parsed or None


def select_cases(all_cases: List[Dict[str, Any]], requested_ids: List[str] | None = None) -> List[Dict[str, Any]]:
    if not requested_ids:
        return list(all_cases)

    requested = set(requested_ids)
    available = {str(case["id"]) for case in all_cases}
    missing = sorted(requested - available)
    if missing:
        raise ValueError(f"Unknown case ids: {', '.join(missing)}")

    return [case for case in all_cases if case["id"] in requested]


def build_seed_spec(case: Dict[str, Any]) -> Dict[str, Any]:
    expected = dict(case.get("expected_initial") or {})
    expected.pop("status", None)
    expected.pop("clarification_fields", None)

    spec = dict(case.get("raw_spec") or {})
    spec.update(expected)
    spec["partner_query_id"] = str((case.get("raw_spec") or {}).get("partner_query_id") or case["id"])
    spec["confirmation_status"] = "confirmed"

    return spec


def case_prompt(case: Dict[str, Any]) -> str:
    return str(case.get("prompt") or "").strip()


def case_original_prompt(case: Dict[str, Any]) -> str:
    return str(case.get("original_prompt") or case_prompt(case)).strip()


def case_rewrite_reason(case: Dict[str, Any]) -> str:
    return str(case.get("rewrite_reason") or "").strip()


def case_is_rewritten(case: Dict[str, Any]) -> bool:
    return case_original_prompt(case) != case_prompt(case)


def executed_prompt(case: Dict[str, Any], *, use_original_prompts_for_rewrites: bool = False) -> str:
    if use_original_prompts_for_rewrites and case_is_rewritten(case):
        return case_original_prompt(case)
    return case_prompt(case)


def executed_prompt_source(case: Dict[str, Any], *, use_original_prompts_for_rewrites: bool = False) -> str:
    if use_original_prompts_for_rewrites and case_is_rewritten(case):
        return "original_prompt"
    return "prompt"


def executed_prompt_pass(status: str) -> bool:
    return str(status or "").strip().lower() in SUCCESS_STATUSES


def original_prompt_status(case: Dict[str, Any], executed_status: str, prompt_source: str = "prompt") -> str:
    if case_is_rewritten(case) and prompt_source != "original_prompt":
        return "rewritten_not_evaluated"
    return str(executed_status or "failed")


def original_prompt_pass(case: Dict[str, Any], executed_status: str, prompt_source: str = "prompt") -> bool:
    return original_prompt_status(case, executed_status, prompt_source) != "rewritten_not_evaluated" and executed_prompt_pass(
        executed_status
    )


@contextmanager
def temporary_cwd(path: Path) -> Iterator[None]:
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


@contextmanager
def agrimet_mode(*, use_api: bool) -> Iterator[None]:
    original = os.environ.get("AGRIMET_USE_API")
    if use_api:
        os.environ["AGRIMET_USE_API"] = "1"
    else:
        os.environ.pop("AGRIMET_USE_API", None)

    try:
        yield
    finally:
        if original is None:
            os.environ.pop("AGRIMET_USE_API", None)
        else:
            os.environ["AGRIMET_USE_API"] = original


def export_folder_name(case_id: str, positions: Dict[str, int]) -> str:
    return f"{positions[case_id]:02d}_{case_id}"


def prepare_case_output_dir(output_dir: Path, folder_name: str) -> Path:
    case_dir = output_dir / folder_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def artifact_sources(result: Dict[str, Any], run_dir: Path) -> Dict[str, Path]:
    files = result.get("files") or {}
    sources = {
        "chart.png": run_dir / str(files["png"]),
        "data.csv": run_dir / str(files["data"]),
        "spec.json": run_dir / str(files["resolved_query"]),
    }
    if files.get("validation"):
        sources["validation.json"] = run_dir / str(files["validation"])
    return sources


def copy_required_artifacts(result: Dict[str, Any], run_dir: Path, destination_dir: Path) -> None:
    for target_name, source_path in artifact_sources(result, run_dir).items():
        if target_name == "validation.json" and not source_path.exists():
            continue
        if not source_path.exists():
            raise FileNotFoundError(f"Missing artifact: {source_path}")
        shutil.copy2(source_path, destination_dir / target_name)


def write_failure_artifacts(
    destination_dir: Path,
    case: Dict[str, Any],
    result: Dict[str, Any],
    spec: Dict[str, Any],
    *,
    use_original_prompts_for_rewrites: bool = False,
) -> None:
    executed = executed_prompt(case, use_original_prompts_for_rewrites=use_original_prompts_for_rewrites)
    prompt_source = executed_prompt_source(case, use_original_prompts_for_rewrites=use_original_prompts_for_rewrites)
    error_message = (
        result.get("error")
        or result.get("clarification_prompt")
        or result.get("confirmation_prompt")
        or "Unknown export failure."
    )

    spec_payload = {
        "prompt": case_prompt(case),
        "original_prompt": case_original_prompt(case),
        "rewritten": case_is_rewritten(case),
        "rewrite_reason": case_rewrite_reason(case) or None,
        "comparison_alignment": {
            "target": "todd_original_workbook_queries",
            "executed_prompt_source": prompt_source,
            "executed_prompt": executed,
            "used_original_prompt_for_execution": prompt_source == "original_prompt",
        },
        "spec": result.get("spec") or spec,
        "summary": {
            "status": "failed",
            "error": error_message,
        },
    }
    (destination_dir / "spec.json").write_text(json.dumps(spec_payload, indent=2), encoding="utf-8")

    error_lines = [
        "# Export Error",
        "",
        f"- Case ID: {case['id']}",
        f"- Executed prompt source: {prompt_source}",
        f"- Executed prompt: {executed}",
        f"- Error: {error_message}",
        "",
    ]
    (destination_dir / "ERROR.md").write_text("\n".join(error_lines), encoding="utf-8")


def enrich_case_spec(
    case_dir: Path,
    case: Dict[str, Any],
    result: Dict[str, Any],
    *,
    use_original_prompts_for_rewrites: bool = False,
) -> None:
    spec_path = case_dir / "spec.json"
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    result_status = str((result.get("summary") or {}).get("status") or "success")
    executed = executed_prompt(case, use_original_prompts_for_rewrites=use_original_prompts_for_rewrites)
    prompt_source = executed_prompt_source(case, use_original_prompts_for_rewrites=use_original_prompts_for_rewrites)
    payload["prompt"] = case_prompt(case)
    payload["original_prompt"] = case_original_prompt(case)
    payload["rewritten"] = case_is_rewritten(case)
    if case_rewrite_reason(case):
        payload["rewrite_reason"] = case_rewrite_reason(case)
    payload["comparison_alignment"] = {
        "target": "todd_original_workbook_queries",
        "executed_prompt_source": prompt_source,
        "executed_prompt": executed,
        "used_original_prompt_for_execution": prompt_source == "original_prompt",
    }
    payload["qa_review"] = {
        "case_id": str(case["id"]),
        "acceptance_target": "original_prompt",
        "executed_prompt": executed,
        "executed_prompt_source": prompt_source,
        "original_prompt": case_original_prompt(case),
        "rewritten": case_is_rewritten(case),
        "rewrite_reason": case_rewrite_reason(case) or None,
        "status": result_status,
        "executed_prompt_status": result_status,
        "executed_prompt_pass": executed_prompt_pass(result_status),
        "original_prompt_status": original_prompt_status(case, result_status, prompt_source),
        "original_prompt_pass": original_prompt_pass(case, result_status, prompt_source),
        "no_data_reason": (result.get("summary") or {}).get("no_data_reason"),
    }
    spec_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_case(
    case: Dict[str, Any],
    output_dir: Path,
    positions: Dict[str, int],
    *,
    use_original_prompts_for_rewrites: bool = False,
) -> Dict[str, Any]:
    case_id = str(case["id"])
    folder_name = export_folder_name(case_id, positions)
    case_dir = prepare_case_output_dir(output_dir, folder_name)
    spec = build_seed_spec(case)
    executed = executed_prompt(case, use_original_prompts_for_rewrites=use_original_prompts_for_rewrites)
    prompt_source = executed_prompt_source(case, use_original_prompts_for_rewrites=use_original_prompts_for_rewrites)

    summary: Dict[str, Any] = {
        "case_id": case_id,
        "prompt": case_prompt(case),
        "original_prompt": case_original_prompt(case),
        "executed_prompt": executed,
        "executed_prompt_source": prompt_source,
        "rewritten": case_is_rewritten(case),
        "rewrite_reason": case_rewrite_reason(case) or None,
        "folder": folder_name,
        "status": "failed",
        "executed_prompt_status": "failed",
        "executed_prompt_pass": False,
        "original_prompt_status": original_prompt_status(case, "failed", prompt_source),
        "original_prompt_pass": original_prompt_pass(case, "failed", prompt_source),
        "error": None,
        "no_data_reason": None,
    }

    with tempfile.TemporaryDirectory(prefix=f"qa_export_{case_id}_") as temp_dir:
        run_dir = Path(temp_dir)
        with temporary_cwd(run_dir):
            result = process_query(executed, spec=spec)

        if not result.get("success"):
            summary["error"] = (
                result.get("error")
                or result.get("clarification_prompt")
                or result.get("confirmation_prompt")
                or "Unknown export failure."
            )
            write_failure_artifacts(
                case_dir,
                case,
                result,
                spec,
                use_original_prompts_for_rewrites=use_original_prompts_for_rewrites,
            )
            summary["artifacts"] = {
                "spec": str(case_dir / "spec.json"),
                "error": str(case_dir / "ERROR.md"),
            }
            return summary

        copy_required_artifacts(result, run_dir, case_dir)
        enrich_case_spec(
            case_dir,
            case,
            result,
            use_original_prompts_for_rewrites=use_original_prompts_for_rewrites,
        )

    result_summary = result.get("summary") or {}
    summary["status"] = str(result_summary.get("status") or "success")
    summary["executed_prompt_status"] = summary["status"]
    summary["executed_prompt_pass"] = executed_prompt_pass(summary["status"])
    summary["original_prompt_status"] = original_prompt_status(case, summary["status"], prompt_source)
    summary["original_prompt_pass"] = original_prompt_pass(case, summary["status"], prompt_source)
    summary["no_data_reason"] = result_summary.get("no_data_reason")
    summary["dataset"] = result_summary.get("dataset")
    summary["location"] = result_summary.get("location")
    summary["station_id"] = result_summary.get("station_id")
    summary["variable_labels"] = result_summary.get("variable_labels")
    summary["artifacts"] = {
        "chart": str(case_dir / "chart.png"),
        "csv": str(case_dir / "data.csv"),
        "spec": str(case_dir / "spec.json"),
    }
    validation_path = case_dir / "validation.json"
    if validation_path.exists():
        summary["artifacts"]["validation"] = str(validation_path)
    return summary


def write_run_summary(output_dir: Path, summaries: List[Dict[str, Any]]) -> None:
    payload = {
        "total_cases": len(summaries),
        "acceptance_target": "original_prompt",
        "successful_cases": sum(1 for item in summaries if item["status"] in SUCCESS_STATUSES),
        "failed_cases": sum(1 for item in summaries if item["status"] not in SUCCESS_STATUSES),
        "executed_prompt_successful_cases": sum(1 for item in summaries if item["executed_prompt_pass"]),
        "executed_prompt_failed_cases": sum(1 for item in summaries if not item["executed_prompt_pass"]),
        "original_prompt_successful_cases": sum(1 for item in summaries if item["original_prompt_pass"]),
        "original_prompt_failed_cases": sum(
            1
            for item in summaries
            if item["original_prompt_status"] not in {"rewritten_not_evaluated"} and not item["original_prompt_pass"]
        ),
        "original_prompt_not_evaluated_cases": sum(
            1 for item in summaries if item["original_prompt_status"] == "rewritten_not_evaluated"
        ),
        "rewritten_cases": sum(1 for item in summaries if item["rewritten"]),
        "cases": summaries,
    }
    (output_dir / "run_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_cases(
    *,
    output_dir: Path,
    requested_case_ids: List[str] | None = None,
    clean: bool = False,
    use_original_prompts_for_rewrites: bool = False,
) -> int:
    all_cases = load_fixture_cases()
    positions = case_positions(all_cases)
    cases = select_cases(all_cases, requested_case_ids)

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries = [
        run_case(
            case,
            output_dir,
            positions,
            use_original_prompts_for_rewrites=use_original_prompts_for_rewrites,
        )
        for case in cases
    ]
    write_run_summary(output_dir, summaries)

    return 0 if all(item["status"] in SUCCESS_STATUSES for item in summaries) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export QA artifacts for workbook queries.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where the QA bundle will be written.",
    )
    parser.add_argument(
        "--case-ids",
        nargs="*",
        help="Optional workbook case ids to export. Accepts repeated values or comma-separated lists.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete and rebuild the output directory before exporting.",
    )
    parser.add_argument(
        "--use-original-prompts-for-rewrites",
        action="store_true",
        help="For rewritten workbook cases, execute the original workbook prompt instead of the rewritten QA prompt.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    requested_case_ids = parse_case_ids(args.case_ids)
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = (Path.cwd() / output_dir).resolve()

    return export_cases(
        output_dir=output_dir,
        requested_case_ids=requested_case_ids,
        clean=bool(args.clean),
        use_original_prompts_for_rewrites=bool(args.use_original_prompts_for_rewrites),
    )


if __name__ == "__main__":
    raise SystemExit(main())
