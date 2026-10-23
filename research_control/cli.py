"""Command-line entry point for the operational company-research workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from research_control import PASS, __version__
from research_control.adaptive import advance, complete_work, open_runtime, runtime_status
from research_control.capture import capture_source_part, capture_url
from research_control.checks import check_phase
from research_control.discovery import DISCOVERY_CHANNELS, DiscoveryEngine
from research_control.gates.release import check_release
from research_control.io import workflow
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
from research_control.reducers import reduce_capture_parts, reduce_discovery, reduce_extraction_parts
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
        "prompts/phases/discovery.md",
        "prompts/phases/discovery-reducer.md",
        "prompts/phases/capture-source.md",
        "prompts/phases/capture-reducer.md",
        "prompts/phases/extraction-reducer.md",
        "prompts/phases/brand-guide.md",
        "prompts/phases/diagram-modeling.md",
        "prompts/phases/diagram-building.md",
        "research_control/schemas/work-item.schema.json",
        "research_control/schemas/discovery-pass.schema.json",
        "research_control/schemas/diagram-models.schema.json",
        "research_control/schemas/diagram-review.schema.json",
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
        adaptive = document.get("adaptive_runtime", {})
        if adaptive.get("completion_basis") != "channel_saturation_not_source_count":
            failures.append("adaptive runtime must use channel saturation rather than a source count")
        scheduler = adaptive.get("scheduler", {})
        for setting in ("global_concurrency", "per_host_concurrency", "lease_seconds", "max_attempts"):
            if int(scheduler.get(setting, 0)) < 1:
                failures.append(f"adaptive scheduler setting must be positive: {setting}")
        batching = adaptive.get("batching", {})
        if int(batching.get("target_extraction_tokens", 0)) > int(batching.get("maximum_extraction_tokens", 0)):
            failures.append("target extraction tokens exceed the maximum")
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
    run = subparsers.add_parser("run", help="initialize or advance the adaptive research orchestrator")
    run.add_argument("--url")
    subparsers.add_parser("next", help="write and list permitted task packets")
    subparsers.add_parser("status", help="show resumable run state")

    work = subparsers.add_parser("work", help="operate the durable adaptive work queue")
    work_sub = work.add_subparsers(dest="work_command", required=True)
    work_claim = work_sub.add_parser("claim")
    work_claim.add_argument("task_id")
    work_claim.add_argument("--worker-id", required=True)
    work_start = work_sub.add_parser("start")
    work_start.add_argument("task_id")
    work_start.add_argument("--worker-id", required=True)
    work_heartbeat = work_sub.add_parser("heartbeat")
    work_heartbeat.add_argument("task_id")
    work_heartbeat.add_argument("--worker-id", required=True)
    work_succeed = work_sub.add_parser("succeed")
    work_succeed.add_argument("task_id")
    work_succeed.add_argument("--worker-id", required=True)
    work_succeed.add_argument("--model")
    work_succeed.add_argument("--effort")
    work_succeed.add_argument("--input-tokens", type=int)
    work_succeed.add_argument("--output-tokens", type=int)
    work_fail = work_sub.add_parser("fail")
    work_fail.add_argument("task_id")
    work_fail.add_argument("--worker-id", required=True)
    work_fail.add_argument("--reason", required=True)
    work_fail.add_argument("--terminal", action="store_true", help="do not retry this failure")
    work_sub.add_parser("recover", help="recover expired leases")

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

    discovery = subparsers.add_parser("discovery", help="record saturation-based source discovery")
    discovery_sub = discovery.add_subparsers(dest="discovery_command", required=True)
    discovery_sub.add_parser("crawl", help="crawl the public first-party frontier to saturation")
    discovery_add = discovery_sub.add_parser("add", help="record one discovery pass and its newly found URLs")
    discovery_add.add_argument("--channel", required=True, choices=DISCOVERY_CHANNELS)
    discovery_add.add_argument("--url", action="append", default=[])
    discovery_add.add_argument("--evidence", required=True)
    discovery_add.add_argument("--discovered-from", default="agent-search")
    discovery_close = discovery_sub.add_parser("close", help="close a channel with explicit evidence")
    discovery_close.add_argument("--channel", required=True, choices=DISCOVERY_CHANNELS)
    discovery_close.add_argument("--state", required=True, choices=["saturated", "not_applicable", "blocked", "incomplete"])
    discovery_close.add_argument("--evidence", required=True)
    discovery_receipt = discovery_sub.add_parser("receipt", help="write the current channel's worker receipt")
    discovery_receipt.add_argument("--channel", required=True, choices=DISCOVERY_CHANNELS)

    source = subparsers.add_parser("source", help="capture one scheduler-owned source into an isolated worker part")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_capture = source_sub.add_parser("capture")
    source_capture.add_argument("--source-id", required=True)
    source_capture.add_argument("--grade", choices=["P", "S", "T", "I"])
    source_capture.add_argument("--title")
    source_capture.add_argument("--publisher")

    reduce = subparsers.add_parser("reduce", help="merge isolated worker parts as the single writer")
    reduce.add_argument("kind", choices=["discovery", "capture", "extraction"])

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
        if args.command == "run":
            _print_json(advance(root, args.url))
            return
        if args.command == "next":
            result = next_packets(root)
            _print_json(result)
            return
        if args.command == "status":
            _print_json(runtime_status(root) if (root / "tools/outputs/runtime.sqlite3").is_file() else status_summary(root))
            return
        if args.command == "work":
            if args.work_command == "recover":
                with open_runtime(root) as store:
                    _print_json({"recovered": store.recover_expired(), "runtime": store.summary()})
                return
            if args.work_command == "succeed":
                telemetry = {
                    key: value for key, value in {
                        "model": args.model, "effort": args.effort,
                        "input_tokens": args.input_tokens, "output_tokens": args.output_tokens,
                    }.items() if value is not None
                }
                _print_json(complete_work(root, args.task_id, args.worker_id, telemetry=telemetry))
                return
            with open_runtime(root) as store:
                if args.work_command == "claim":
                    claimed = store.claim(args.worker_id, task_id=args.task_id)
                    if claimed is None:
                        raise ValueError(f"task is not currently claimable: {args.task_id}")
                    _print_json(claimed)
                elif args.work_command == "start":
                    _print_json(store.start(args.task_id, args.worker_id))
                elif args.work_command == "heartbeat":
                    _print_json(store.heartbeat(args.task_id, args.worker_id))
                elif args.work_command == "fail":
                    _print_json(store.fail(args.task_id, args.worker_id, args.reason, retryable=not args.terminal))
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
        if args.command == "discovery":
            with open_runtime(root) as store:
                engine = DiscoveryEngine(root, store)
                engine.initialize()
                if args.discovery_command == "crawl":
                    passes = []
                    while True:
                        result = engine.crawl_company_site()
                        passes.append(result)
                        if result["status"] in {"saturated", "incomplete", "blocked"}:
                            break
                    _print_json({"status": passes[-1]["status"], "passes": passes})
                elif args.discovery_command == "add":
                    _print_json(engine.add_candidates(
                        args.channel, args.url, discovered_from=args.discovered_from,
                        evidence=args.evidence, record_pass=True,
                    ))
                elif args.discovery_command == "close":
                    _print_json(engine.close_channel(args.channel, args.state, args.evidence))
                else:
                    channel = store.discovery_channel(args.channel)
                    if not channel or channel["state"] == "open":
                        raise ValueError(f"discovery channel is not terminal: {args.channel}")
                    receipt = {
                        "schema_version": "1.0.0", "channel": args.channel,
                        "status": channel["state"], "passes": channel["total_passes"],
                        "new_sources": channel["total_new_sources"],
                        "evidence": channel["completion_evidence"],
                    }
                    path = root / "tools/outputs/worker-parts/discovery" / f"{args.channel.replace('_', '-')}.json"
                    from research_control.io import atomic_write_json
                    atomic_write_json(path, receipt)
                    _print_json({**receipt, "receipt": str(path.relative_to(root))})
            return
        if args.command == "source":
            with open_runtime(root) as store:
                source_record = store.source(args.source_id)
                if not source_record:
                    raise KeyError(f"unknown source: {args.source_id}")
                if source_record["channel"] in {"video", "podcasts"}:
                    raise ValueError(
                        f"{args.source_id}: media sources require caption/transcription capture and a manual receipt"
                    )
                grade = args.grade or ("S" if source_record["channel"] == "independent_web" else "P")
                _print_json(capture_source_part(
                    root, url=source_record["canonical_url"], source_id=args.source_id,
                    grade=grade, title=args.title, publisher=args.publisher,
                ))
            return
        if args.command == "reduce":
            if args.kind == "extraction":
                _print_json(reduce_extraction_parts(root))
            else:
                with open_runtime(root) as store:
                    _print_json(reduce_discovery(root, store) if args.kind == "discovery" else reduce_capture_parts(root, store))
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
