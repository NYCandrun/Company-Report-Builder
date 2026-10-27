"""Command-line entry point for the operational company-research workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from research_control import PASS, __version__
from research_control.adaptive import advance, complete_work, open_runtime, requeue_captures, retry_media, runtime_status
from research_control.capture import capture_source_part, capture_url
from research_control.checks import check_phase
from research_control.discovery import DISCOVERY_CHANNELS, DiscoveryEngine, DiscoveryPolicy, public_fetch
from research_control.gates.release import check_release
from research_control.io import atomic_write_json, load_json, utc_now, workflow
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
from research_control.planner import ALTERNATES_TASK, discovery_task_id
from research_control.supplement import add_supplement, defer_slices
from research_control.provision import RUNS_DIRECTORY, provision_run, run_slug, sync_engine
from research_control.publication import render
from research_control.reducers import reduce_capture_parts, reduce_discovery, reduce_extraction_parts
from research_control.reporting import print_summary
from research_control.web_cache import SharedWebCache


def _root(value: str | Path) -> Path:
    return Path(value).resolve()


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _refresh_release_evidence(root: Path) -> None:
    """Rebuild company-run validation evidence without mutating completed state."""
    document = workflow(root / "WORKFLOW.yaml")
    for phase in document["phases"]:
        if phase["id"] == "release_acceptance":
            continue
        report, _path = check_phase(root, phase["id"], update_state=False)
        if report["status"] != PASS:
            raise ValueError(f"phase evidence is not releasable: {phase['id']}={report['status']}")


# Discovery commands that change a channel's record are worker actions and need a
# held lease; crawl, reopen, and retry are controller actions.
WORKER_DISCOVERY_COMMANDS = {"add", "close", "exclude", "receipt"}


def _require_discovery_lease(store: Any, channel: str) -> None:
    covering = [
        task for task in store.tasks(phase="capture")
        if task["task_type"] == "source_discovery" and channel in (task["metadata"].get("channels") or [])
    ]
    if not any(task["state"] in {"leased", "running"} for task in covering):
        raise ValueError(
            f"no claimed discovery task covers {channel}; claim and start {discovery_task_id(channel)} first "
            "(if it is not ready, the orchestrator must reopen the channel and rerun `run`)"
        )


def _web_fetch(args: argparse.Namespace, cache: SharedWebCache) -> None:
    if args.refresh:
        fetched = public_fetch(args.url, DiscoveryPolicy())
        response = cache.store_response(
            args.url,
            final_url=fetched.url,
            content_type=fetched.content_type,
            status=fetched.status,
            headers=fetched.headers,
            body=fetched.body,
            consumer=args.consumer,
            purpose=args.purpose,
            discovered_from=args.discovered_from,
        )
    else:
        response = cache.fetch_or_reuse(
            args.url,
            consumer=args.consumer,
            purpose=args.purpose,
            discovered_from=args.discovered_from,
            fetcher=lambda: public_fetch(args.url, DiscoveryPolicy()),
        )
    _print_json({
        "status": "fetched", "url": response.requested_url,
        "final_url": response.final_url, "content_type": response.content_type,
        "http_status": response.status, "content_bytes": len(response.body),
        "content_sha256": response.content_sha256,
        "object_path": response.object_path, "cache_hit": response.cache_hit,
    })


def preflight(root: Path) -> int:
    required = [
        "README.md",
        "RESEARCH_CONSTITUTION.md",
        "WORKFLOW.yaml",
        "prompts/core/runtime.md",
        "prompts/core/evidence.md",
        "prompts/core/writing.md",
        "prompts/phases/discovery.md",
        "prompts/phases/discovery-reducer.md",
        "prompts/phases/capture-source.md",
        "prompts/phases/capture-reducer.md",
        "prompts/phases/extraction-reducer.md",
        "prompts/phases/triage.md",
        "prompts/phases/alternate-copies.md",
        "prompts/phases/synthesis-groundwork.md",
        "prompts/phases/currency-review.md",
        "prompts/phases/synthesis-supplement.md",
        "prompts/phases/inference-catalogue.md",
        "prompts/phases/brand-guide.md",
        "prompts/phases/diagram-modeling.md",
        "prompts/phases/diagram-building.md",
        "research_control/schemas/work-item.schema.json",
        "research_control/schemas/discovery-pass.schema.json",
        "research_control/schemas/diagram-models.schema.json",
        "research_control/schemas/diagram-review.schema.json",
        "research_control/web_cache.py",
        "research_control/routing.py",
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
        if adaptive.get("completion_basis") != "question_sufficiency_or_saturation_not_source_count":
            failures.append("adaptive runtime must close discovery by question sufficiency or saturation, never a source count")
        scheduler = adaptive.get("scheduler", {})
        for setting in ("global_concurrency", "per_host_concurrency", "lease_seconds", "max_attempts"):
            if int(scheduler.get(setting, 0)) < 1:
                failures.append(f"adaptive scheduler setting must be positive: {setting}")
        batching = adaptive.get("batching", {})
        if int(batching.get("target_extraction_tokens", 0)) > int(batching.get("maximum_extraction_tokens", 0)):
            failures.append("target extraction tokens exceed the maximum")
        routing = adaptive.get("model_routing", {})
        if routing and routing.get("optional") is not True:
            failures.append("model routing must remain optional and advisory")
        if routing and routing.get("fallback") != "use_available_model":
            failures.append("model routing must fall back to the available session model")
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
    if shutil.which("yt-dlp") is None:
        warnings.append("yt-dlp not found; media sources are captured as pages without transcripts")
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        warnings.append("faster-whisper not found; downloaded audio cannot be transcribed locally")
    try:
        import nemo  # noqa: F401
    except ImportError:
        try:
            import sherpa_onnx  # noqa: F401
            warnings.append("NeMo not found; speaker labels fall back to sherpa-onnx clustering (weaker on quick exchanges)")
        except ImportError:
            warnings.append("neither NeMo nor sherpa-onnx found; Whisper transcripts will not label speakers")
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
    new = subparsers.add_parser("new", help="provision an isolated run directory and initialize it")
    new.add_argument("--url", required=True)
    new.add_argument("--dir", help="run directory (default: runs/<company-host-slug>)")
    subparsers.add_parser("sync-engine", help="refresh a run's engine, prompts, and policy from its template")
    init = subparsers.add_parser("init", help="initialize a URL-only research run")
    init.add_argument("--url", required=True)
    run = subparsers.add_parser("run", help="initialize or advance the adaptive research orchestrator")
    run.add_argument("--url")
    run.add_argument("--plan-only", action="store_true", help="plan and write packets without running runtime-owned work")
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
    work_defer = work_sub.add_parser(
        "defer-slices", help="orchestrator: leave extraction slices out (a token budget); the gap stays recorded"
    )
    work_defer.add_argument("slice_ids", nargs="+")
    work_defer.add_argument("--reason", required=True)
    work_rerun = work_sub.add_parser(
        "rerun", help="orchestrator: rerun a finished task, and its finished consumers, after its inputs changed"
    )
    work_rerun.add_argument("task_id")
    work_rerun.add_argument("--reason", required=True)
    work_rerun.add_argument(
        "--only", action="store_true",
        help="rerun this task alone; its consumers stand and are replanned from what changes (supplements)",
    )
    work_restore = work_sub.add_parser(
        "restore", help="orchestrator: restore a superseded or rerun-marked task whose last attempt succeeded"
    )
    work_restore.add_argument("task_id")
    work_restore.add_argument("--reason", required=True)
    limits_parser = subparsers.add_parser(
        "limits", help="orchestrator: set this run's agent concurrency for the environment it runs in"
    )
    limits_parser.add_argument("--global", dest="global_concurrency", type=int)
    limits_parser.add_argument("--per-host", dest="per_host_concurrency", type=int)
    scope_parser = subparsers.add_parser("scope", help="orchestrator: change the research questions mid-run")
    scope_sub = scope_parser.add_subparsers(dest="scope_command", required=True)
    scope_add = scope_sub.add_parser(
        "add-question", help="add a research question; every captured source is re-triaged against it"
    )
    scope_add.add_argument("--id", required=True, help="new question ID, e.g. Q13")
    scope_add.add_argument("--title", required=True)
    scope_add.add_argument("--text", required=True)
    scope_add.add_argument("--channels", default="")
    scope_add.add_argument("--reason", required=True)
    scope_edit = scope_sub.add_parser(
        "record-edit", help="record an orchestrator's edit of 00-scope.md so tasks that read it keep their results"
    )
    scope_edit.add_argument("--reason", required=True)
    archive_parser = subparsers.add_parser(
        "archive", help="orchestrator: commit the run's sources and outputs to its run-data branch on the remote"
    )
    archive_parser.add_argument("--remote", help="remote URL (default: the template checkout's origin)")
    archive_parser.add_argument("--branch", help="branch (default: run-data/<slug>)")
    archive_parser.add_argument("--no-push", action="store_true")
    supplement = subparsers.add_parser(
        "supplement", help="orchestrator: extract a recaptured source's new text as a supplement to its filed facts"
    )
    supplement.add_argument("--source-id", action="append", required=True)
    supplement.add_argument("--reason", required=True)

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
    discovery_close.add_argument("--state", required=True, choices=["saturated", "sufficient", "not_applicable", "blocked", "incomplete"])
    discovery_close.add_argument("--evidence", required=True)
    discovery_alternate = discovery_sub.add_parser(
        "alternate", help="record a public alternate copy of a blocked source, or --none when there is none"
    )
    discovery_alternate.add_argument("--source-id", required=True)
    discovery_alternate.add_argument("--url")
    discovery_alternate.add_argument("--none", action="store_true", help="no public alternate copy exists")
    discovery_alternate.add_argument("--evidence", required=True)
    discovery_reopen = discovery_sub.add_parser("reopen", help="reopen a closed channel after a scope change")
    discovery_reopen.add_argument("--channel", required=True, choices=DISCOVERY_CHANNELS)
    discovery_reopen.add_argument("--evidence", required=True)
    discovery_retry = discovery_sub.add_parser(
        "retry", help="return explicitly transport-blocked sources to the discovery frontier"
    )
    discovery_retry.add_argument("--channel", required=True, choices=DISCOVERY_CHANNELS)
    discovery_retry.add_argument("--source-id", action="append", default=[])
    discovery_retry.add_argument("--evidence", required=True)
    discovery_exclude = discovery_sub.add_parser(
        "exclude", help="exclude audited non-evidence leads while preserving provenance"
    )
    discovery_exclude.add_argument("--channel", required=True, choices=DISCOVERY_CHANNELS)
    discovery_exclude.add_argument("--source-id", action="append", required=True)
    discovery_exclude.add_argument("--evidence", required=True)
    discovery_receipt = discovery_sub.add_parser("receipt", help="write the current channel's worker receipt")
    discovery_receipt.add_argument("--channel", required=True, choices=DISCOVERY_CHANNELS)

    source = subparsers.add_parser("source", help="capture one scheduler-owned source into an isolated worker part")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_capture = source_sub.add_parser("capture")
    source_capture.add_argument("--source-id", required=True)
    source_capture.add_argument("--grade", choices=["P", "S", "T", "I"])
    source_capture.add_argument("--title")
    source_capture.add_argument("--publisher")

    web = subparsers.add_parser("web", help="use the shared transport cache and URL lead ledger")
    web_sub = web.add_subparsers(dest="web_command", required=True)
    for command in ("register", "fetch"):
        web_item = web_sub.add_parser(command)
        web_item.add_argument("--url", required=True)
        web_item.add_argument("--consumer", required=True)
        web_item.add_argument("--purpose", required=True)
        web_item.add_argument("--discovered-from", default="")
        if command == "fetch":
            web_item.add_argument("--refresh", action="store_true")
    web_list = web_sub.add_parser("list")
    web_list.add_argument("--purpose")
    web_list.add_argument("--state", choices=["registered", "fetched"])
    web_list.add_argument("--offset", type=int, default=0)
    web_list.add_argument("--limit", type=int, default=200)
    web_list.add_argument("--details", action="store_true")
    web_sub.add_parser("export")

    media = subparsers.add_parser("media", help="manage media transcripts")
    media_sub = media.add_subparsers(dest="media_command", required=True)
    media_retry = media_sub.add_parser("retry", help="re-queue media captures whose transcript was unavailable")
    media_retry.add_argument("--source-id", action="append", default=[])

    recapture = subparsers.add_parser("recapture", help="re-queue chosen or blocked captures after a capture method improves")
    recapture.add_argument("--source-id", action="append", default=[])
    recapture.add_argument("--blocked", action="store_true", help="re-queue every capture whose receipt is blocked")

    reduce = subparsers.add_parser("reduce", help="merge isolated worker parts as the single writer")
    reduce.add_argument("kind", choices=["discovery", "capture", "extraction", "dating", "links"])

    subparsers.add_parser("render", help="build final HTML, PDF, and page previews")
    subparsers.add_parser("release", help="run independent exact-artifact release acceptance")
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = _root(args.root)
    try:
        if args.command == "preflight":
            raise SystemExit(preflight(root))
        if args.command == "new":
            run_root = Path(args.dir).resolve() if args.dir else root / RUNS_DIRECTORY / run_slug(args.url)
            provision_run(root, run_root)
            result = advance(run_root, args.url)
            relative = os.path.relpath(run_root, Path.cwd())
            _print_json({
                "run_root": str(run_root),
                "next": f"cd {relative} && python3 -m research_control run",
                "advance": result,
            })
            return
        if args.command == "sync-engine":
            template = Path(__file__).resolve().parents[1]
            _print_json({"synced": sync_engine(template, root), "template": str(template), "run_root": str(root)})
            return
        if args.command == "init":
            state = initialize(root, args.url)
            _print_json({"status": "initialized", "run_id": state["run_id"], "company_url": state["company_url"], "next": "python3 -m research_control check --phase bootstrap"})
            return
        if args.command == "run":
            _print_json(advance(root, args.url, automatic=not args.plan_only))
            return
        if args.command == "next":
            result = next_packets(root)
            _print_json(result)
            return
        if args.command == "supplement":
            _print_json(add_supplement(root, args.source_id, args.reason))
            return
        if args.command == "limits":
            from research_control.adaptive import RUNTIME_LIMITS

            path = root / RUNTIME_LIMITS
            current = load_json(path) if path.is_file() else {}
            for key in ("global_concurrency", "per_host_concurrency"):
                value = getattr(args, key)
                if value is not None:
                    if value < 1:
                        raise ValueError(f"{key} must be positive")
                    current[key] = value
            atomic_write_json(path, current)
            with open_runtime(root):
                pass
            _print_json(current)
            return
        if args.command == "scope":
            from research_control.orchestration import append_history
            from research_control.triage import add_scope_question

            from research_control.automatic import RUNTIME_WORKER
            from research_control.triage import RETRIAGE_REQUEST

            if args.scope_command == "record-edit":
                outputs = ["00-scope.md"] + ([RETRIAGE_REQUEST] if (root / RETRIAGE_REQUEST).is_file() else [])
                with open_runtime(root) as store:
                    revision = store.record_revision(
                        f"scope.edit.{utc_now().replace(':', '').replace('-', '').lower()}", "scope", outputs,
                        args.reason, RUNTIME_WORKER,
                    )
                    rebaselined = store.rebaseline_inputs(["00-scope.md"], args.reason)
                append_history(root, "scope-edit-recorded", args.reason)
                _print_json({"revision": revision["task_id"], "rebaselined": rebaselined})
                return
            request = add_scope_question(root, args.id, args.title, args.text, args.channels, args.reason)
            with open_runtime(root) as store:
                # The scope edit is a recorded revision: it owns the new scope, and
                # tasks reading the scope keep their results; the question reaches
                # them through re-triage and supplement extraction instead.
                store.record_revision(
                    f"scope.add-question.{args.id.lower()}", "scope", ["00-scope.md", RETRIAGE_REQUEST],
                    f"{args.id} added: {args.reason}", RUNTIME_WORKER,
                )
                rebaselined = store.rebaseline_inputs(["00-scope.md"], f"{args.id} added; re-triage {request['id']}")
            append_history(root, "scope-question-added", f"{args.id}: {args.title} ({args.reason}); re-triage {request['id']}")
            _print_json({**request, "rebaselined": rebaselined})
            return
        if args.command == "archive":
            from research_control.archive import archive

            _print_json(archive(root, remote=args.remote, branch=args.branch, push=not args.no_push))
            return
        if args.command == "status":
            _print_json(runtime_status(root) if (root / "tools/outputs/runtime.sqlite3").is_file() else status_summary(root))
            return
        if args.command == "work":
            if args.work_command == "recover":
                with open_runtime(root) as store:
                    _print_json({"recovered": store.recover_expired(), "runtime": store.summary()})
                return
            if args.work_command == "restore":
                with open_runtime(root) as store:
                    _print_json(store.restore(args.task_id, args.reason))
                return
            if args.work_command == "defer-slices":
                _print_json(defer_slices(root, args.slice_ids, args.reason))
                return
            if args.work_command == "rerun":
                with open_runtime(root) as store:
                    if not store.task(args.task_id):
                        raise KeyError(f"unknown task: {args.task_id}")
                    _print_json(store.mark_stale(args.task_id, f"rerun requested: {args.reason}", propagate=not args.only))
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
                if args.discovery_command in WORKER_DISCOVERY_COMMANDS:
                    _require_discovery_lease(store, args.channel)
                if args.discovery_command == "alternate":
                    if not any(
                        task["task_type"] == "alternate_copies"
                        for task in store.tasks(phase="capture", states=["leased", "running"])
                    ):
                        raise ValueError(f"claim and start an {ALTERNATES_TASK} task before recording alternates")
                    if bool(args.url) == bool(args.none):
                        raise ValueError("pass exactly one of --url or --none")
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
                elif args.discovery_command == "alternate":
                    _print_json(engine.add_alternate(args.source_id, args.url, args.evidence))
                elif args.discovery_command == "reopen":
                    _print_json(engine.reopen_channel(args.channel, args.evidence))
                elif args.discovery_command == "retry":
                    _print_json(engine.retry_blocked_sources(
                        args.channel, evidence=args.evidence, source_ids=args.source_id,
                    ))
                elif args.discovery_command == "exclude":
                    _print_json(engine.exclude_sources(
                        args.channel, evidence=args.evidence, source_ids=args.source_id,
                    ))
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
                    grade=grade, title=args.title, publisher=args.publisher, store=store,
                ))
            return
        if args.command == "web":
            with open_runtime(root) as store:
                cache = SharedWebCache(root, store)
                if args.web_command == "register":
                    normalized = cache.note_url(
                        args.url, consumer=args.consumer, purpose=args.purpose,
                        discovered_from=args.discovered_from,
                    )
                    _print_json({"status": "registered", "url": normalized})
                elif args.web_command == "fetch":
                    try:
                        _web_fetch(args, cache)
                    except (HTTPError, URLError, PermissionError, ValueError, TimeoutError) as error:
                        _print_json({
                            "status": "unavailable", "url": args.url,
                            "http_status": getattr(error, "code", None),
                            "reason": f"{type(error).__name__}: {error}",
                        })
                elif args.web_command == "list":
                    records = cache.records(purpose=args.purpose, state=args.state)
                    if args.offset < 0 or args.limit < 1 or args.limit > 1000:
                        raise ValueError("web list requires offset >= 0 and limit between 1 and 1000")
                    selected = records[args.offset:args.offset + args.limit]
                    if not args.details:
                        selected = [{
                            "url": item["url"],
                            "state": item["state"],
                            "final_url": item.get("final_url"),
                            "content_type": item.get("content_type"),
                            "object_path": item.get("object_path"),
                            "purposes": sorted({use["purpose"] for use in item.get("uses", [])}),
                        } for item in selected]
                    next_offset = args.offset + len(selected) if args.offset + len(selected) < len(records) else None
                    _print_json({
                        "note": "URL leads and cached bytes are not evidence until admitted by the consuming workflow.",
                        "total": len(records), "offset": args.offset, "count": len(selected),
                        "next_offset": next_offset, "urls": selected,
                    })
                else:
                    path = cache.export_ledger()
                    _print_json({"status": "exported", "ledger": str(path.relative_to(root))})
            return
        if args.command == "media":
            _print_json(retry_media(root, args.source_id))
            return
        if args.command == "recapture":
            if not args.source_id and not args.blocked:
                raise ValueError("recapture needs --source-id or --blocked")
            _print_json(requeue_captures(root, args.source_id, blocked=args.blocked))
            return
        if args.command == "reduce":
            if args.kind == "extraction":
                _print_json(reduce_extraction_parts(root))
            elif args.kind == "links":
                from research_control.deeplinks import write_fact_links
                _print_json(write_fact_links(root))
            elif args.kind == "dating":
                from research_control.dating import write_source_dates
                from research_control.reducers import _json_parts
                _print_json(write_source_dates(root, _json_parts(root / "tools/outputs/worker-parts/capture")))
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
