from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "evaluation_results"
DEFAULT_REGRESSION_REPORT = DEFAULT_OUTPUT_ROOT / "regression_suite_latest"
DEFAULT_PROMPT_REPORT = DEFAULT_OUTPUT_ROOT / "prompt_benchmark_latest"
DEFAULT_QA_RUN_SUMMARY = REPO_ROOT / "artifacts" / "qa" / "run_summary.json"
DEFAULT_WORKBOOK_EVAL = REPO_ROOT / "evaluation_results" / "workbook_evaluation_20260415_071203.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_summary_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if path.is_dir():
        summary_path = path / "summary.json"
        return summary_path if summary_path.exists() else None
    return path if path.exists() else None


def _artifact_bundle_dir(run_summary_path: Path, case: dict[str, Any]) -> Path | None:
    folder_name = case.get("folder")
    if folder_name:
        folder_path = run_summary_path.parent / str(folder_name)
        if folder_path.exists():
            return folder_path
    return None


def _artifact_exists(run_summary_path: Path, case: dict[str, Any], artifact_key: str, fallback_name: str) -> bool:
    artifacts = case.get("artifacts") or {}
    artifact_path = artifacts.get(artifact_key)
    if artifact_path and Path(str(artifact_path)).exists():
        return True

    bundle_dir = _artifact_bundle_dir(run_summary_path, case)
    return bool(bundle_dir and (bundle_dir / fallback_name).exists())


def retained_qa_summary(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    cases = payload.get("cases") or []
    success_count = sum(1 for case in cases if case.get("status") == "success")
    no_data_count = sum(1 for case in cases if case.get("status") == "no_data")
    failure_count = sum(1 for case in cases if case.get("status") not in {"success", "no_data"})
    rewritten_count = sum(1 for case in cases if bool(case.get("rewritten")))
    executed_prompt_success_count = sum(
        1 for case in cases if bool(case.get("executed_prompt_pass", case.get("status") in {"success", "no_data"}))
    )
    original_prompt_success_count = sum(
        1
        for case in cases
        if bool(
            case.get(
                "original_prompt_pass",
                (not bool(case.get("rewritten"))) and case.get("status") in {"success", "no_data"},
            )
        )
    )
    original_prompt_not_evaluated_count = sum(
        1
        for case in cases
        if str(case.get("original_prompt_status") or "").strip().lower() == "rewritten_not_evaluated"
        or (case.get("rewritten") and "original_prompt_status" not in case)
    )
    original_prompt_failed_count = sum(
        1
        for case in cases
        if not bool(
            case.get(
                "original_prompt_pass",
                (not bool(case.get("rewritten"))) and case.get("status") in {"success", "no_data"},
            )
        )
        and not (
            str(case.get("original_prompt_status") or "").strip().lower() == "rewritten_not_evaluated"
            or (case.get("rewritten") and "original_prompt_status" not in case)
        )
    )

    complete_artifacts = 0
    validation_artifacts = 0
    for case in cases:
        if (
            _artifact_exists(path, case, "chart", "chart.png")
            and _artifact_exists(path, case, "csv", "data.csv")
            and _artifact_exists(path, case, "spec", "spec.json")
        ):
            complete_artifacts += 1
        if _artifact_exists(path, case, "validation", "validation.json"):
            validation_artifacts += 1

    return {
        "source": str(path),
        "total_cases": int(payload.get("total_cases") or len(cases)),
        "success_count": success_count,
        "no_data_count": no_data_count,
        "failure_count": failure_count,
        "rewritten_count": rewritten_count,
        "executed_prompt_success_count": int(payload.get("executed_prompt_successful_cases") or executed_prompt_success_count),
        "original_prompt_success_count": int(payload.get("original_prompt_successful_cases") or original_prompt_success_count),
        "original_prompt_failed_count": int(payload.get("original_prompt_failed_cases") or original_prompt_failed_count),
        "original_prompt_not_evaluated_count": int(
            payload.get("original_prompt_not_evaluated_cases") or original_prompt_not_evaluated_count
        ),
        "executed_prompt_success_rate": round(executed_prompt_success_count / len(cases), 4) if cases else None,
        "original_prompt_success_rate": round(original_prompt_success_count / len(cases), 4) if cases else None,
        "artifact_generation_rate": round(complete_artifacts / len(cases), 4) if cases else None,
        "validation_report_generation_rate": round(validation_artifacts / len(cases), 4) if cases else None,
    }


def categorize_failure_reason(reason: str) -> list[str]:
    lowered = reason.lower()
    categories: list[str] = []
    if "expected variables" in lowered:
        categories.append("variable normalization mismatch")
    if "expected crop_filter".lower() in lowered or "expected crop filter" in lowered:
        categories.append("crop extraction mismatch")
    if "expected dataset" in lowered:
        categories.append("dataset routing mismatch")
    if any(token in lowered for token in ["expected evidence_pattern", "expected analysis_family", "expected chart_package"]):
        categories.append("unsupported chart/evidence package type")
    if "missing summary fields" in lowered:
        categories.append("missing summary fields")
    if any(token in lowered for token in ["companion view", "secondary_view_count", "min_secondary_view_count"]):
        categories.append("missing companion views")
    if any(token in lowered for token in ["expected needs_clarification", "expected clarification fields"]):
        categories.append("clarification missed when needed")
    return categories or ["other"]


def workbook_eval_summary(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    summary = payload.get("summary") or {}
    records = payload.get("records") or []

    instability_count = sum(1 for record in records if record.get("unstable_fields"))
    category_counter: Counter[str] = Counter()
    for record in records:
        for reason in record.get("failure_reasons") or []:
            for category in categorize_failure_reason(str(reason)):
                category_counter[category] += 1

    return {
        "source": str(path),
        "total_queries": int(summary.get("total_queries") or len(records)),
        "included_in_pass_rate": int(summary.get("included_in_pass_rate") or 0),
        "pass_count": int((summary.get("counts") or {}).get("pass") or 0),
        "fail_count": int((summary.get("counts") or {}).get("fail") or 0),
        "needs_review_count": int((summary.get("counts") or {}).get("needs_review") or 0),
        "pass_rate": summary.get("pass_rate"),
        "instability_count": instability_count,
        "top_failure_categories": category_counter.most_common(7),
    }


def regression_suite_summary(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = load_json(path)
    steps = payload.get("steps") or {}
    return {
        "source": str(path),
        "all_green": bool((payload.get("summary") or {}).get("all_green")),
        "backend_pytest": steps.get("backend_pytest", {}).get("metrics", {}),
        "frontend_vitest": steps.get("frontend_vitest", {}).get("metrics", {}),
        "frontend_build": steps.get("frontend_build", {}).get("metrics", {}),
    }


def prompt_benchmark_summary(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = load_json(path)
    results = payload.get("results") or []
    winner = payload.get("winner")
    return {
        "source": str(path),
        "results_count": len(results),
        "winner": winner,
        "top_result_metrics": (winner or {}).get("metrics"),
    }


def markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# SmartTap Testing Story Report",
        "",
        f"- Run timestamp: {summary['run']['timestamp_utc']}",
        "",
        "## Automated Coverage",
        "",
    ]

    regression = summary.get("regression_suite")
    if regression:
        lines.extend(
            [
                f"- Overall green: {regression['all_green']}",
                f"- Backend pytest: {regression['backend_pytest'].get('passed', 0)} passed, {regression['backend_pytest'].get('skipped', 0)} skipped",
                f"- Frontend vitest: {regression['frontend_vitest'].get('tests_passed', 0)} tests across {regression['frontend_vitest'].get('test_files_passed', 0)} files",
                f"- Frontend build warning: {regression['frontend_build'].get('bundle_size_warning')}",
                "",
            ]
        )
    else:
        lines.extend(["- Regression suite report not provided.", ""])

    qa = summary["retained_qa"]
    lines.extend(
        [
            "## Retained QA",
            "",
            f"- Total cases: {qa['total_cases']}",
            f"- Executed-prompt passes: {qa['executed_prompt_success_count']}",
            f"- Original-prompt passes: {qa['original_prompt_success_count']}",
            f"- Rewritten / not fully evaluated against original prompts: {qa['original_prompt_not_evaluated_count']}",
            f"- Successful evidence packages: {qa['success_count']}",
            f"- Correct no-data responses: {qa['no_data_count']}",
            f"- Crash/failure count: {qa['failure_count']}",
            f"- Artifact generation rate: {qa['artifact_generation_rate']}",
            f"- Validation report generation rate: {qa['validation_report_generation_rate']}",
            "",
        ]
    )

    prompt = summary.get("prompt_benchmark")
    if prompt:
        prompt_metrics = prompt.get("top_result_metrics") or {}
        lines.extend(
            [
                "## Prompt Benchmark",
                "",
                f"- Result sets: {prompt['results_count']}",
                f"- Winner: {prompt['winner']['prompt_label']} on {prompt['winner']['model']} (score={prompt['winner']['composite_score']})" if prompt.get("winner") else "- Winner: unavailable",
                f"- Required-field match rate: {prompt_metrics.get('required_field_match_rate')}" if prompt_metrics else "- Required-field match rate: unavailable",
                f"- Status accuracy: {prompt_metrics.get('status_accuracy')}" if prompt_metrics else "- Status accuracy: unavailable",
                f"- Stability across repeats: {prompt_metrics.get('stability_rate')}" if prompt_metrics else "- Stability across repeats: unavailable",
                "",
            ]
        )
    else:
        lines.extend(["## Prompt Benchmark", "", "- Prompt benchmark report not provided.", ""])

    workbook = summary["workbook_stress"]
    lines.extend(
        [
            "## Broader Workbook Stress Test",
            "",
            f"- Total queries: {workbook['total_queries']}",
            f"- Pass / fail / needs review: {workbook['pass_count']} / {workbook['fail_count']} / {workbook['needs_review_count']}",
            f"- Pass rate: {workbook['pass_rate']}",
            f"- Unstable queries across repeats: {workbook['instability_count']}",
            "",
            "### Top Failure Categories",
            "",
            "| Category | Count |",
            "| --- | --- |",
        ]
    )
    for category, count in workbook["top_failure_categories"]:
        lines.append(f"| {category} | {count} |")
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "summary.md").write_text(markdown_report(summary), encoding="utf-8")

    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "metric", "value"])

        regression = summary.get("regression_suite")
        if regression:
            writer.writerow(["regression_suite", "all_green", regression["all_green"]])
            writer.writerow(["regression_suite", "backend_passed", regression["backend_pytest"].get("passed")])
            writer.writerow(["regression_suite", "frontend_tests_passed", regression["frontend_vitest"].get("tests_passed")])
            writer.writerow(["regression_suite", "bundle_size_warning", regression["frontend_build"].get("bundle_size_warning")])

        qa = summary["retained_qa"]
        writer.writerow(["retained_qa", "total_cases", qa["total_cases"]])
        writer.writerow(["retained_qa", "executed_prompt_success_count", qa["executed_prompt_success_count"]])
        writer.writerow(["retained_qa", "original_prompt_success_count", qa["original_prompt_success_count"]])
        writer.writerow(["retained_qa", "original_prompt_not_evaluated_count", qa["original_prompt_not_evaluated_count"]])
        writer.writerow(["retained_qa", "rewritten_count", qa["rewritten_count"]])
        writer.writerow(["retained_qa", "success_count", qa["success_count"]])
        writer.writerow(["retained_qa", "no_data_count", qa["no_data_count"]])
        writer.writerow(["retained_qa", "failure_count", qa["failure_count"]])
        writer.writerow(["retained_qa", "artifact_generation_rate", qa["artifact_generation_rate"]])
        writer.writerow(["retained_qa", "validation_report_generation_rate", qa["validation_report_generation_rate"]])

        prompt = summary.get("prompt_benchmark")
        if prompt and prompt.get("winner"):
            writer.writerow(["prompt_benchmark", "winner_prompt", prompt["winner"]["prompt_label"]])
            writer.writerow(["prompt_benchmark", "winner_model", prompt["winner"]["model"]])
            writer.writerow(["prompt_benchmark", "winner_score", prompt["winner"]["composite_score"]])
            winner_metrics = prompt.get("top_result_metrics") or {}
            writer.writerow(["prompt_benchmark", "required_field_match_rate", winner_metrics.get("required_field_match_rate")])
            writer.writerow(["prompt_benchmark", "status_accuracy", winner_metrics.get("status_accuracy")])
            writer.writerow(["prompt_benchmark", "stability_rate", winner_metrics.get("stability_rate")])

        workbook = summary["workbook_stress"]
        writer.writerow(["workbook_stress", "total_queries", workbook["total_queries"]])
        writer.writerow(["workbook_stress", "pass_count", workbook["pass_count"]])
        writer.writerow(["workbook_stress", "fail_count", workbook["fail_count"]])
        writer.writerow(["workbook_stress", "needs_review_count", workbook["needs_review_count"]])
        writer.writerow(["workbook_stress", "instability_count", workbook["instability_count"]])
        writer.writerow(["workbook_stress", "pass_rate", workbook["pass_rate"]])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate SmartTap testing artifacts into a slide-ready report.")
    parser.add_argument("--regression-report", help="Path to regression suite summary.json or its containing directory.")
    parser.add_argument("--prompt-report", help="Path to prompt benchmark summary.json or its containing directory.")
    parser.add_argument("--qa-run-summary", default=str(DEFAULT_QA_RUN_SUMMARY), help="Path to artifacts/qa/run_summary.json.")
    parser.add_argument(
        "--workbook-eval",
        default=str(DEFAULT_WORKBOOK_EVAL),
        help="Path to workbook evaluation JSON.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_ROOT / f"testing_story_{_timestamp()}"),
        help="Directory where JSON/Markdown/CSV outputs will be written.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    regression = regression_suite_summary(resolve_summary_path(args.regression_report))
    prompt = prompt_benchmark_summary(resolve_summary_path(args.prompt_report))
    retained = retained_qa_summary(Path(args.qa_run_summary).expanduser().resolve())
    workbook = workbook_eval_summary(Path(args.workbook_eval).expanduser().resolve())

    summary = {
        "run": {"timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")},
        "regression_suite": regression,
        "prompt_benchmark": prompt,
        "retained_qa": retained,
        "workbook_stress": workbook,
    }

    output_dir = Path(args.output).expanduser().resolve()
    write_outputs(output_dir, summary)
    print(str(output_dir / "summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
