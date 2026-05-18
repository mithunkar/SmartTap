from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = REPO_ROOT / "web"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "evaluation_results"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_command(command: Sequence[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return {
        "command": list(command),
        "cwd": str(cwd),
        "exit_code": int(completed.returncode),
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def parse_pytest_output(output: str) -> dict[str, Any]:
    summary = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "duration_seconds": None,
    }
    match = re.search(
        r"(?P<passed>\d+)\s+passed(?:,\s+(?P<failed>\d+)\s+failed)?(?:,\s+(?P<skipped>\d+)\s+skipped)?(?:,\s+(?P<errors>\d+)\s+error(?:s)?)?\s+in\s+(?P<duration>[\d.]+)s",
        output,
    )
    if not match:
        return summary

    summary["passed"] = int(match.group("passed") or 0)
    summary["failed"] = int(match.group("failed") or 0)
    summary["skipped"] = int(match.group("skipped") or 0)
    summary["errors"] = int(match.group("errors") or 0)
    summary["duration_seconds"] = float(match.group("duration"))
    return summary


def parse_vitest_output(output: str) -> dict[str, Any]:
    summary = {
        "test_files_passed": 0,
        "test_files_total": 0,
        "tests_passed": 0,
        "tests_total": 0,
        "duration_seconds": None,
        "warnings": [],
    }

    files_match = re.search(r"Test Files\s+(\d+)\s+passed\s+\((\d+)\)", output)
    if files_match:
        summary["test_files_passed"] = int(files_match.group(1))
        summary["test_files_total"] = int(files_match.group(2))

    tests_match = re.search(r"Tests\s+(\d+)\s+passed\s+\((\d+)\)", output)
    if tests_match:
        summary["tests_passed"] = int(tests_match.group(1))
        summary["tests_total"] = int(tests_match.group(2))

    duration_match = re.search(r"Duration\s+([\d.]+)s", output)
    if duration_match:
        summary["duration_seconds"] = float(duration_match.group(1))

    warning_lines = []
    for line in output.splitlines():
        cleaned = line.strip()
        if "width(0) and height(0) of chart should be greater than 0" in cleaned:
            warning_lines.append("ChartRenderer zero-size warning in jsdom")
    summary["warnings"] = sorted(set(warning_lines))
    return summary


def parse_build_output(output: str) -> dict[str, Any]:
    summary = {
        "duration_seconds": None,
        "warnings": [],
        "bundle_size_warning": False,
    }
    duration_match = re.search(r"built in\s+([\d.]+)s", output)
    if duration_match:
        summary["duration_seconds"] = float(duration_match.group(1))
    if "Some chunks are larger than 500 kB after minification" in output:
        summary["warnings"].append("Bundle chunk size exceeds 500 kB")
        summary["bundle_size_warning"] = True
    return summary


def markdown_report(summary: dict[str, Any]) -> str:
    steps = summary["steps"]
    lines = [
        "# Regression Suite",
        "",
        f"- Run timestamp: {summary['run']['timestamp_utc']}",
        f"- Overall status: {'green' if summary['summary']['all_green'] else 'failing'}",
        "",
        "| Step | Status | Key metrics |",
        "| --- | --- | --- |",
    ]

    pytest_metrics = steps["backend_pytest"]["metrics"]
    vitest_metrics = steps["frontend_vitest"]["metrics"]
    build_metrics = steps["frontend_build"]["metrics"]
    lines.append(
        f"| backend_pytest | {'ok' if steps['backend_pytest']['ok'] else 'fail'} | "
        f"{pytest_metrics['passed']} passed, {pytest_metrics['skipped']} skipped |"
    )
    lines.append(
        f"| frontend_vitest | {'ok' if steps['frontend_vitest']['ok'] else 'fail'} | "
        f"{vitest_metrics['tests_passed']} tests across {vitest_metrics['test_files_passed']} files |"
    )
    lines.append(
        f"| frontend_build | {'ok' if steps['frontend_build']['ok'] else 'fail'} | "
        f"bundle warning={build_metrics['bundle_size_warning']} |"
    )
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "summary.md").write_text(markdown_report(summary), encoding="utf-8")

    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "ok", "exit_code", "details"])
        for step_name, payload in summary["steps"].items():
            writer.writerow(
                [
                    step_name,
                    payload["ok"],
                    payload["exit_code"],
                    json.dumps(payload["metrics"], sort_keys=True),
                ]
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SmartTap backend/frontend regression checks.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_ROOT / f"regression_suite_{_timestamp()}"),
        help="Directory where JSON/Markdown/CSV outputs will be written.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    backend_pytest = run_command([sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT)
    frontend_vitest = run_command(["npm", "test"], cwd=WEB_ROOT)
    frontend_build = run_command(["npm", "run", "build"], cwd=WEB_ROOT)

    backend_pytest["metrics"] = parse_pytest_output(backend_pytest["stdout"] + "\n" + backend_pytest["stderr"])
    frontend_vitest["metrics"] = parse_vitest_output(frontend_vitest["stdout"] + "\n" + frontend_vitest["stderr"])
    frontend_build["metrics"] = parse_build_output(frontend_build["stdout"] + "\n" + frontend_build["stderr"])

    summary = {
        "run": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        "steps": {
            "backend_pytest": backend_pytest,
            "frontend_vitest": frontend_vitest,
            "frontend_build": frontend_build,
        },
        "summary": {
            "all_green": all(step["ok"] for step in [backend_pytest, frontend_vitest, frontend_build]),
        },
    }

    output_dir = Path(args.output).expanduser().resolve()
    write_outputs(output_dir, summary)
    print(str(output_dir / "summary.json"))
    return 0 if summary["summary"]["all_green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
