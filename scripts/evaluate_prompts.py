from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable, Iterator


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm.config import DEFAULT_MODEL
from llm.interpretation import get_task_specification
from core.validation import validate_and_fix_spec


DEFAULT_CASE_SET = REPO_ROOT / "tests" / "fixtures" / "prompt_eval_cases.json"
DEFAULT_PROMPT_FILE = REPO_ROOT / "prompts" / "interpretation.txt"
DEFAULT_PROMPT_DIR = REPO_ROOT / "prompts" / "variants"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "evaluation_results"
SUCCESSFUL_EXECUTION_STATUSES = {"success", "no_data"}
ALLOWED_CASE_STATUSES = {"clarification", "confirmation", "success-ready"}
ALLOWED_CASE_SCOPES = {"retained", "stretch", "adversarial"}
DEFAULT_MATCH_FIELDS = [
    "task",
    "dataset",
    "location_type",
    "variables",
    "crop_filter",
    "start_date",
    "end_date",
    "statistics",
    "evidence_pattern",
]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def parse_repeated_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    parsed: list[str] = []
    for value in values:
        parsed.extend(part.strip() for part in value.split(",") if part.strip())
    return parsed


def prompt_label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def load_prompt_files(*, prompt_files: list[str], prompt_dirs: list[str]) -> list[Path]:
    resolved: list[Path] = [DEFAULT_PROMPT_FILE.resolve()]
    seen = {resolved[0]}

    for value in prompt_files:
        path = Path(value).expanduser().resolve()
        if path not in seen:
            resolved.append(path)
            seen.add(path)

    dirs = [Path(value).expanduser().resolve() for value in prompt_dirs] or [DEFAULT_PROMPT_DIR.resolve()]
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.txt")):
            resolved_path = path.resolve()
            if resolved_path not in seen:
                resolved.append(resolved_path)
                seen.add(resolved_path)

    missing = [path for path in resolved if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing prompt files: {', '.join(str(path) for path in missing)}")
    return resolved


def load_cases(case_set: Path) -> list[dict[str, Any]]:
    payload = json.loads(case_set.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"Prompt case set must contain a top-level 'cases' list: {case_set}")

    validated: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Prompt case #{index} is not an object.")
        for key in ["id", "query", "expected_partial_spec", "expected_status", "scope"]:
            if key not in case:
                raise ValueError(f"Prompt case #{index} is missing '{key}'.")
        if case["expected_status"] not in ALLOWED_CASE_STATUSES:
            raise ValueError(f"Prompt case {case['id']} has invalid expected_status={case['expected_status']!r}.")
        if case["scope"] not in ALLOWED_CASE_SCOPES:
            raise ValueError(f"Prompt case {case['id']} has invalid scope={case['scope']!r}.")
        if not isinstance(case["expected_partial_spec"], dict):
            raise ValueError(f"Prompt case {case['id']} expected_partial_spec must be an object.")
        must_match_fields = case.get("must_match_fields") or list(case["expected_partial_spec"].keys()) or list(DEFAULT_MATCH_FIELDS)
        if not isinstance(must_match_fields, list) or any(not isinstance(value, str) for value in must_match_fields):
            raise ValueError(f"Prompt case {case['id']} has invalid must_match_fields.")

        validated.append(
            {
                "id": str(case["id"]),
                "query": str(case["query"]),
                "expected_partial_spec": dict(case["expected_partial_spec"]),
                "expected_status": str(case["expected_status"]),
                "must_match_fields": [str(value) for value in must_match_fields],
                "scope": str(case["scope"]),
                "notes": str(case.get("notes") or ""),
            }
        )
    return validated


def normalize_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    return value


def derive_prompt_status(normalized_spec: dict[str, Any]) -> str:
    if normalized_spec.get("task") == "error":
        return "clarification"
    if normalized_spec.get("clarification_needed"):
        return "clarification"
    if normalized_spec.get("confirmation_status") == "confirmed":
        return "confirmation"
    return "success-ready"


def evaluate_field_matches(
    *,
    expected_partial_spec: dict[str, Any],
    actual_spec: dict[str, Any],
    must_match_fields: Iterable[str],
) -> dict[str, Any]:
    matches: dict[str, bool] = {}
    expected_values: dict[str, Any] = {}
    actual_values: dict[str, Any] = {}

    for field in must_match_fields:
        if field not in expected_partial_spec:
            continue
        expected_value = normalize_value(expected_partial_spec.get(field))
        actual_value = normalize_value(actual_spec.get(field))
        expected_values[field] = expected_value
        actual_values[field] = actual_value
        matches[field] = actual_value == expected_value

    matched_fields = [field for field, ok in matches.items() if ok]
    mismatched_fields = [field for field, ok in matches.items() if not ok]
    return {
        "field_matches": matches,
        "expected_values": expected_values,
        "actual_values": actual_values,
        "matched_fields": matched_fields,
        "mismatched_fields": mismatched_fields,
        "matched_count": len(matched_fields),
        "field_count": len(matches),
    }


@contextmanager
def temporary_cwd(path: Path) -> Iterator[None]:
    original = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original)


def _default_parse_fn(
    query: str,
    *,
    prompt_path: Path,
    model_name: str,
) -> dict[str, Any]:
    return get_task_specification(query, prompt_path=prompt_path, model_name=model_name)


def _default_execute_fn(
    query: str,
    *,
    normalized_spec: dict[str, Any],
) -> dict[str, Any]:
    from smarttap_service import process_query

    confirmed_spec = dict(normalized_spec)
    confirmed_spec["confirmation_status"] = "confirmed"

    with TemporaryDirectory(prefix="prompt_eval_") as temp_dir:
        run_dir = Path(temp_dir)
        with temporary_cwd(run_dir):
            result = process_query(query, spec=confirmed_spec)

    summary = result.get("summary") or {}
    return {
        "success": bool(result.get("success")),
        "status": str(summary.get("status") or ("success" if result.get("success") else "failed")),
        "no_data_reason": summary.get("no_data_reason"),
        "needs_clarification": bool(result.get("needs_clarification")),
        "needs_confirmation": bool(result.get("needs_confirmation")),
        "error": result.get("error"),
    }


def evaluate_case(
    *,
    case: dict[str, Any],
    prompt_path: Path,
    model_name: str,
    repeat_index: int,
    parse_fn: Callable[..., dict[str, Any]] | None = None,
    execute_fn: Callable[..., dict[str, Any]] | None = None,
    include_execution: bool = True,
) -> dict[str, Any]:
    parse_callable = parse_fn or _default_parse_fn
    execute_callable = execute_fn or _default_execute_fn

    error_message = None
    raw_spec: dict[str, Any]
    try:
        raw_spec = dict(
            parse_callable(
                case["query"],
                prompt_path=prompt_path,
                model_name=model_name,
            )
            or {}
        )
    except Exception as exc:
        raw_spec = {"task": "error", "error_message": str(exc)}
        error_message = str(exc)

    json_valid = not (
        raw_spec.get("task") == "error"
        and str(raw_spec.get("error_message") or "").startswith("Parser returned invalid JSON")
    )
    normalized_spec = normalize_value(validate_and_fix_spec(raw_spec, case["query"]))
    actual_status = derive_prompt_status(normalized_spec)
    field_eval = evaluate_field_matches(
        expected_partial_spec=case["expected_partial_spec"],
        actual_spec=normalized_spec,
        must_match_fields=case["must_match_fields"],
    )

    execution: dict[str, Any] | None = None
    if include_execution and case["scope"] == "retained" and actual_status == "success-ready":
        try:
            execution = execute_callable(case["query"], normalized_spec=normalized_spec)
        except Exception as exc:
            execution = {
                "success": False,
                "status": "failed",
                "no_data_reason": None,
                "needs_clarification": False,
                "needs_confirmation": False,
                "error": str(exc),
            }

    execution_completed = bool(
        execution
        and execution.get("success")
        and str(execution.get("status") or "") in SUCCESSFUL_EXECUTION_STATUSES
    )

    fingerprint_payload = {
        "actual_status": actual_status,
        "field_values": field_eval["actual_values"],
        "json_valid": json_valid,
    }
    return {
        "case_id": case["id"],
        "query": case["query"],
        "scope": case["scope"],
        "notes": case["notes"],
        "expected_status": case["expected_status"],
        "actual_status": actual_status,
        "status_match": actual_status == case["expected_status"],
        "json_valid": json_valid,
        "confirmation_ready": actual_status == "success-ready",
        "matched_fields": field_eval["matched_fields"],
        "mismatched_fields": field_eval["mismatched_fields"],
        "matched_field_count": field_eval["matched_count"],
        "field_count": field_eval["field_count"],
        "field_matches": field_eval["field_matches"],
        "expected_values": field_eval["expected_values"],
        "actual_values": field_eval["actual_values"],
        "raw_spec": normalize_value(raw_spec),
        "normalized_spec": normalized_spec,
        "prompt_file": str(prompt_path),
        "prompt_label": prompt_label(prompt_path),
        "model": model_name,
        "repeat_index": repeat_index,
        "error": error_message or raw_spec.get("error_message"),
        "execution": execution,
        "execution_completed": execution_completed,
        "fingerprint": json.dumps(fingerprint_payload, sort_keys=True),
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _field_accuracy(results: list[dict[str, Any]], field: str) -> float | None:
    relevant = [result for result in results if field in result["field_matches"]]
    if not relevant:
        return None
    return _rate(sum(1 for result in relevant if result["field_matches"][field]), len(relevant))


def _stability_rate(results: list[dict[str, Any]]) -> float | None:
    if not results:
        return None
    grouped: dict[str, list[str]] = defaultdict(list)
    for result in results:
        grouped[result["case_id"]].append(result["fingerprint"])
    stable = sum(1 for values in grouped.values() if len(set(values)) == 1)
    return _rate(stable, len(grouped))


def summarize_prompt_run(
    *,
    prompt_path: Path,
    model_name: str,
    cases: list[dict[str, Any]],
    repeats: int,
    case_results: list[dict[str, Any]],
) -> dict[str, Any]:
    total_field_count = sum(result["field_count"] for result in case_results)
    matched_field_count = sum(result["matched_field_count"] for result in case_results)
    retained_results = [result for result in case_results if result["scope"] == "retained"]
    retained_executed = [result for result in retained_results if result["execution"] is not None]

    metrics = {
        "json_valid_rate": _rate(sum(1 for result in case_results if result["json_valid"]), len(case_results)),
        "required_field_match_rate": _rate(matched_field_count, total_field_count),
        "status_accuracy": _rate(sum(1 for result in case_results if result["status_match"]), len(case_results)),
        "task_classification_accuracy": _field_accuracy(case_results, "task"),
        "dataset_routing_accuracy": _field_accuracy(case_results, "dataset"),
        "variable_mapping_accuracy": _field_accuracy(case_results, "variables"),
        "crop_filter_accuracy": _field_accuracy(case_results, "crop_filter"),
        "clarification_trigger_accuracy": _rate(
            sum(
                1
                for result in case_results
                if (result["actual_status"] == "clarification") == (result["expected_status"] == "clarification")
            ),
            len(case_results),
        ),
        "stability_rate": _stability_rate(case_results),
        "downstream_confirmation_ready_rate": _rate(
            sum(1 for result in case_results if result["confirmation_ready"]),
            len(case_results),
        ),
        "retained_end_to_end_execution_rate": _rate(
            sum(1 for result in retained_executed if result["execution_completed"]),
            len(retained_executed),
        ),
    }
    available_scores = [value for value in metrics.values() if value is not None]
    composite_score = round(mean(available_scores), 4) if available_scores else None

    case_summaries = []
    for case in cases:
        grouped = [result for result in case_results if result["case_id"] == case["id"]]
        if not grouped:
            continue
        stable = len({result["fingerprint"] for result in grouped}) == 1
        case_summaries.append(
            {
                "case_id": case["id"],
                "scope": case["scope"],
                "expected_status": case["expected_status"],
                "actual_statuses": [result["actual_status"] for result in grouped],
                "json_valid_runs": sum(1 for result in grouped if result["json_valid"]),
                "field_match_rate": _rate(
                    sum(result["matched_field_count"] for result in grouped),
                    sum(result["field_count"] for result in grouped),
                ),
                "stable_across_repeats": stable,
                "execution_completed_runs": sum(1 for result in grouped if result["execution_completed"]),
            }
        )

    return {
        "prompt_file": str(prompt_path),
        "prompt_label": prompt_label(prompt_path),
        "model": model_name,
        "repeats": repeats,
        "cases_total": len(cases),
        "results_total": len(case_results),
        "retained_cases_total": sum(1 for case in cases if case["scope"] == "retained"),
        "metrics": metrics,
        "composite_score": composite_score,
        "case_results": case_results,
        "case_summaries": case_summaries,
    }


def evaluate_prompt_matrix(
    *,
    prompt_files: list[Path],
    models: list[str],
    cases: list[dict[str, Any]],
    repeats: int,
    include_execution: bool = True,
    parse_fn: Callable[..., dict[str, Any]] | None = None,
    execute_fn: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for prompt_path in prompt_files:
        for model_name in models:
            case_results: list[dict[str, Any]] = []
            for case in cases:
                for repeat_index in range(1, repeats + 1):
                    case_results.append(
                        evaluate_case(
                            case=case,
                            prompt_path=prompt_path,
                            model_name=model_name,
                            repeat_index=repeat_index,
                            parse_fn=parse_fn,
                            execute_fn=execute_fn,
                            include_execution=include_execution,
                        )
                    )
            results.append(
                summarize_prompt_run(
                    prompt_path=prompt_path,
                    model_name=model_name,
                    cases=cases,
                    repeats=repeats,
                    case_results=case_results,
                )
            )
    return results


def _winner(summary_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in summary_rows if row.get("composite_score") is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: float(row["composite_score"]))


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Prompt Benchmark",
        "",
        f"- Run timestamp: {summary['run']['timestamp_utc']}",
        f"- Case set: {summary['run']['case_set']}",
        f"- Repeat count: {summary['run']['repeats']}",
        f"- Prompt files tested: {summary['run']['prompt_file_count']}",
        f"- Models tested: {summary['run']['model_count']}",
        "",
        "## Ranked Results",
        "",
        "| Rank | Prompt | Model | Composite Score | Field Match | Status Accuracy | Stability | Retained Execution |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    ranked = sorted(
        summary["results"],
        key=lambda row: float(row.get("composite_score") or -1),
        reverse=True,
    )
    for index, row in enumerate(ranked, start=1):
        metrics = row["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    row["prompt_label"],
                    row["model"],
                    str(row.get("composite_score")),
                    str(metrics.get("required_field_match_rate")),
                    str(metrics.get("status_accuracy")),
                    str(metrics.get("stability_rate")),
                    str(metrics.get("retained_end_to_end_execution_rate")),
                ]
            )
            + " |"
        )

    winner = summary.get("winner")
    if winner:
        lines.extend(
            [
                "",
                "## Winner",
                "",
                f"- Prompt: {winner['prompt_label']}",
                f"- Model: {winner['model']}",
                f"- Composite score: {winner['composite_score']}",
            ]
        )
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_json = output_dir / "summary.json"
    summary_md = output_dir / "summary.md"
    summary_csv = output_dir / "summary.csv"

    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary_md.write_text(render_markdown(summary), encoding="utf-8")

    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "prompt_label",
                "model",
                "composite_score",
                "json_valid_rate",
                "required_field_match_rate",
                "status_accuracy",
                "task_classification_accuracy",
                "dataset_routing_accuracy",
                "variable_mapping_accuracy",
                "crop_filter_accuracy",
                "clarification_trigger_accuracy",
                "stability_rate",
                "downstream_confirmation_ready_rate",
                "retained_end_to_end_execution_rate",
            ]
        )
        for row in summary["results"]:
            metrics = row["metrics"]
            writer.writerow(
                [
                    row["prompt_label"],
                    row["model"],
                    row.get("composite_score"),
                    metrics.get("json_valid_rate"),
                    metrics.get("required_field_match_rate"),
                    metrics.get("status_accuracy"),
                    metrics.get("task_classification_accuracy"),
                    metrics.get("dataset_routing_accuracy"),
                    metrics.get("variable_mapping_accuracy"),
                    metrics.get("crop_filter_accuracy"),
                    metrics.get("clarification_trigger_accuracy"),
                    metrics.get("stability_rate"),
                    metrics.get("downstream_confirmation_ready_rate"),
                    metrics.get("retained_end_to_end_execution_rate"),
                ]
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark SmartTap prompt variants against parser fixtures.")
    parser.add_argument("--prompt-file", action="append", help="Specific prompt file(s) to evaluate.")
    parser.add_argument("--prompt-dir", action="append", help="Directory of prompt variants to evaluate.")
    parser.add_argument("--model", action="append", help=f"Ollama model(s) to evaluate. Defaults to {DEFAULT_MODEL}.")
    parser.add_argument("--repeats", type=int, default=3, help="Number of repeated parses per case.")
    parser.add_argument("--case-set", default=str(DEFAULT_CASE_SET), help="Path to the prompt evaluation case set JSON.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_ROOT / f"prompt_benchmark_{_timestamp()}"),
        help="Directory where JSON/Markdown/CSV outputs will be written.",
    )
    parser.add_argument(
        "--skip-execution",
        action="store_true",
        help="Skip downstream confirmed execution checks for retained prompts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    prompt_files = load_prompt_files(
        prompt_files=parse_repeated_values(args.prompt_file),
        prompt_dirs=parse_repeated_values(args.prompt_dir),
    )
    models = parse_repeated_values(args.model) or [DEFAULT_MODEL]
    cases = load_cases(Path(args.case_set).expanduser().resolve())
    repeats = max(1, int(args.repeats))

    results = evaluate_prompt_matrix(
        prompt_files=prompt_files,
        models=models,
        cases=cases,
        repeats=repeats,
        include_execution=not args.skip_execution,
    )

    summary = {
        "run": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "case_set": str(Path(args.case_set).expanduser().resolve()),
            "repeats": repeats,
            "prompt_file_count": len(prompt_files),
            "model_count": len(models),
            "include_execution": not args.skip_execution,
        },
        "results": results,
        "winner": _winner(results),
    }

    output_dir = Path(args.output).expanduser().resolve()
    write_outputs(output_dir, summary)
    print(str(output_dir / "summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
