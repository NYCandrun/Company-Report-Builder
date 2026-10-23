"""Command-line entry point for the operational company-research workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from research_control import PASS, __version__
from research_control.capture import capture_url
from research_control.checks import check_phase
from research_control.gates.release import check_release
from research_control.io import load_json, workflow
from research_control.orchestration import (
    current_phase,
    fail_task,
    finish_task,
    initialize,
    load_state,
    next_packets,
    set_phase_result,
    start_task,
    status_summary,
)
from research_control.publication import render
from research_control.reporting import print_summary


def _root(value: str | Path) -> Path:
    return Path(value).resolve()


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _refresh_release_evidence(root: Path) -> None:
    """Rebuild deterministic evidence once, without mutating completed state."""
    from tools.run_integrity_tests import CATEGORIES, run_category

    for category in CATEGORIES:
        report = run_category(category, root / "tools/outputs/tests")
        if report["status"] != PASS:
            raise ValueError(f"integrity suite failed during release refresh: {category}")
    document = workflow(root / "WORKFLOW.yaml")
    for phase in document["phases"]:
        if phase["id"] == "release_acceptance":
            continue
        report, _path = check_phase(root, phase["id"], update_state=False, run_tests=False)
        if report["status"] != PASS:
            raise ValueError(f"phase evidence is not releasable: {phase['id']}={report['status']}")


def preflight(root: Path) -> int:
    required = [
        "README.md",
        "RESEARCH_CONSTITUTION.md",
        "WORKFLOW.yaml",
        "docs/legacy-prompt.md",
        "prompts/core/runtime.md",
        "prompts/core/evidence.md",
        "prompts/core/writing.md",
    ]
    failures = [f"missing required file: {relative}" for relative in required if not (root / relative).is_file()]
    warnings: list[str] = []
    if sys.version_info < (3, 11):
        failures.append(f"Python 3.11+ required; found {sys.version.split()[0]}")
    if shutil.which("git") is None:
        failures.append("git is unavailable")
    try:
        document = workflow(root / "WORKFLOW.yaml")
        profiles = document.get("execution_profiles", {})
        phase_ids = {phase["id"] for phase in document["phases"]}
        if phase_ids != set(profiles):
            failures.append(f"execution profiles do not match phases: {sorted(phase_ids ^ set(profiles))}")
        for phase_id, profile in profiles.items():
            task_ids = [task.get("id") for task in profile.get("tasks", [])]
            if len(task_ids) != len(set(task_ids)):
                failures.append(f"{phase_id}: duplicate execution task IDs")
            for task in profile.get("tasks", []):
                if not task.get("outputs"):
                    failures.append(f"{phase_id}.{task.get('id')}: task has no exact outputs")
                for dependency in task.get("depends_on", []):
                    if dependency not in task_ids:
                        failures.append(f"{phase_id}.{task.get('id')}: unknown task dependency {dependency}")
                for relative in [*task.get("cores", []), task.get("prompt")]:
                    if relative and not (root / relative).is_file():
                        failures.append(f"{phase_id}.{task.get('id')}: missing prompt {relative}")
    except Exception as error:
        failures.append(f"workflow is invalid: {error}")
    if shutil.which("pdftoppm") is None:
        warnings.append("pdftoppm not found; renderer will produce SVG page previews for visual review")
    if not any((
        shutil.which("weasyprint"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").is_file(),
        shutil.which("wkhtmltopdf"),
    )):
        warnings.append("no CSS-capable PDF renderer found; deterministic styled-text PDF fallback will be used")
    result = {
        "status": "PASS" if not failures else "FAIL",
        "version": __version__,
        "python": sys.version.split()[0],
        "root": str(root),
        "failures": failures,
        "warnings": warnings,
    }
    _print_json(result)
    return 0 if not failures else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchctl", description="Operational company-research control plane")
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("preflight", help="verify the copied template and local runtime")
    init = subparsers.add_parser("init", help="initialize a URL-only research run")
    init.add_argument("--url", required=True)
    subparsers.add_parser("next", help="write and list permitted task packets")
    subparsers.add_parser("status", help="show resumable run state")

    task = subparsers.add_parser("task", help="record task attempt lifecycle")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_start = task_sub.add_parser("start")
    task_start.add_argument("task_id")
    task_start.add_argument("--worker-id", required=True)
    task_finish = task_sub.add_parser("finish")
    task_finish.add_argument("task_id")
    task_fail = task_sub.add_parser("fail")
    task_fail.add_argument("task_id")
    task_fail.add_argument("--reason", required=True)

    check = subparsers.add_parser("check", help="produce reports and evaluate a phase")
    check.add_argument("--phase")
    check.add_argument("--no-state-update", action="store_true")

    capture = subparsers.add_parser("capture", help="capture one ordinary public URL into the source manifest")
    capture.add_argument("--url", required=True)
    capture.add_argument("--source-id", required=True)
    capture.add_argument("--grade", required=True, choices=["P", "S", "T", "I"])
    capture.add_argument("--title")
    capture.add_argument("--publisher")

    subparsers.add_parser("render", help="build final HTML, PDF, and page previews")
    subparsers.add_parser("release", help="run independent exact-artifact release acceptance")
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = _root(args.root)
    try:
        if args.command == "preflight":
            raise SystemExit(preflight(root))
        if args.command == "init":
            state = initialize(root, args.url)
            _print_json({"status": "initialized", "run_id": state["run_id"], "company_url": state["company_url"], "next": "python3 -m research_control check --phase bootstrap"})
            return
        if args.command == "next":
            result = next_packets(root)
            _print_json(result)
            return
        if args.command == "status":
            _print_json(status_summary(root))
            return
        if args.command == "task":
            if args.task_command == "start":
                _print_json(start_task(root, args.task_id, args.worker_id))
            elif args.task_command == "finish":
                _print_json(finish_task(root, args.task_id))
            else:
                _print_json(fail_task(root, args.task_id, args.reason))
            return
        if args.command == "check":
            phase_label = args.phase or current_phase(root)
            report, path = check_phase(root, args.phase, not args.no_state_update)
            print_summary(f"phase:{phase_label}", report, str(path))
            raise SystemExit(0 if report["status"] == PASS else 1)
        if args.command == "capture":
            _print_json(capture_url(root, url=args.url, source_id=args.source_id, grade=args.grade, title=args.title, publisher=args.publisher))
            return
        if args.command == "render":
            _print_json(render(root))
            return
        if args.command == "release":
            state = load_state(root)
            if current_phase(root, state) != "release_acceptance":
                raise ValueError(f"release is not permitted; current phase is {current_phase(root, state)}")
            _refresh_release_evidence(root)
            report, validation_path, manifest_path = check_release(root)
            set_phase_result(root, "release_acceptance", report["status"], str(validation_path.relative_to(root)))
            print_summary("release", report, str(validation_path))
            if report["status"] == PASS:
                print(f"release_manifest={manifest_path}")
            raise SystemExit(0 if report["status"] == PASS else 1)
    except (FileNotFoundError, KeyError, ValueError, RuntimeError, PermissionError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
