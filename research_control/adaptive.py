"""High-level adaptive orchestration service used by the CLI and agents."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from research_control import PASS
from research_control.checks import check_phase, run_validator
from research_control.dispatch import emit_ready_packets
from research_control.discovery import ALTERNATES_PART, BLOCKED_SOURCES_LIST
from research_control.io import load_json, load_jsonl, workflow
from research_control.orchestration import current_phase, initialize, load_state, phase_order, reopen_phase, set_phase_result
from research_control import verification
from research_control.validators.extraction import validate_part as validate_extraction_part
from research_control.automatic import RUNTIME_WORKER, run_automatic
from research_control.media import is_media_url
from research_control.planner import AdaptivePlanner
from research_control.triage import validate_retriage, validate_triage
from research_control.runtime import ACTIVE_STATES, DISCOVERY_TERMINAL, SATISFIED_STATES, RuntimeStore


RUNTIME_LIMITS = "tools/lists/runtime-limits.json"


def open_runtime(root: Path) -> RuntimeStore:
    state = load_state(root)
    configuration = workflow(root / "WORKFLOW.yaml").get("adaptive_runtime", {}).get("scheduler", {})
    # The orchestrator's tuning for this environment (`limits`) outlasts one
    # command; an environment variable still wins for a single invocation.
    limits = root / RUNTIME_LIMITS
    configuration = {**configuration, **(load_json(limits) if limits.is_file() else {})}
    store = RuntimeStore(root)
    # WORKFLOW.yaml values are defaults; the orchestrator may tune them for the environment.
    store.initialize(
        run_id=state["run_id"], company_url=state["company_url"],
        global_concurrency=int(os.environ.get("RESEARCH_CONTROL_AGENT_CONCURRENCY") or configuration.get("global_concurrency", 12)),
        host_concurrency=int(os.environ.get("RESEARCH_CONTROL_AGENT_PER_HOST") or configuration.get("per_host_concurrency", 2)),
        lease_seconds=int(configuration.get("lease_seconds", 1_800)),
    )
    return store


def advance(root: Path, company_url: str | None = None, *, automatic: bool = True) -> dict[str, Any]:
    """Advance automatically until worker work, a failed gate, or release.

    With ``automatic=False`` the orchestrator plans and writes agent packets but
    does not execute runtime-owned work (for example while another `run`
    process is already capturing).
    """
    state_path = root / "tools/outputs/run-state.json"
    if not state_path.is_file():
        if not company_url:
            raise FileNotFoundError("no run exists; pass --url on the first `run` invocation")
        initialize(root, company_url)
    elif company_url and load_state(root)["company_url"] != company_url:
        raise ValueError("existing run uses a different company URL")

    with open_runtime(root) as store:
        recovered = store.recover_expired()
        stale = store.invalidate_stale()
        for _step in range(16):
            _reopen_unsatisfied_phases(root, store)
            phase = current_phase(root)
            if phase is None:
                return {"status": "released", "phase": None, "recovered": recovered, "stale": stale}
            if phase == "release_acceptance":
                return {
                    "status": "release_ready",
                    "phase": phase,
                    "next": "python3 -m research_control release",
                    "runtime": store.summary(),
                    "recovered": recovered,
                    "stale": stale,
                }
            if phase == "bootstrap":
                report, path = check_phase(root, "bootstrap", update_state=True)
                if report["status"] != PASS:
                    return {"status": "gate_failed", "phase": phase, "report": str(path.relative_to(root)), "details": report}
                continue

            planned = AdaptivePlanner(root, store).reconcile()
            order = phase_order(root)
            executed = {"executed": 0, "failed": [], "skipped": not automatic}
            if automatic:
                executed = run_automatic(
                    root, store, order[: order.index(phase) + 1],
                    lambda current_store, task, worker: _complete(root, current_store, task, worker),
                    lambda: AdaptivePlanner(root, store).reconcile(),
                )
            if executed["executed"] or executed["failed"]:
                planned = AdaptivePlanner(root, store).reconcile()
            dispatch = emit_ready_packets(root, store, phase)
            if dispatch["ready_count"]:
                return {
                    "status": "work_ready",
                    "phase": phase,
                    "planning": planned,
                    "automatic": executed,
                    "dispatch": dispatch,
                    "recovered": recovered,
                    "stale": stale,
                }
            tasks = store.tasks(phase=phase)
            active = [task["task_id"] for task in tasks if task["state"] in ACTIVE_STATES]
            blocked = [task["task_id"] for task in tasks if task["state"] in {"blocked", "failed"}]
            if blocked:
                return {
                    "status": "blocked",
                    "phase": phase,
                    "blocked_tasks": blocked,
                    "runtime": store.summary(),
                }
            if active:
                return {"status": "waiting", "phase": phase, "active_tasks": active, "runtime": store.summary()}
            if tasks and all(task["state"] in SATISFIED_STATES for task in tasks):
                report, path = check_phase(root, phase, update_state=True)
                if report["status"] != PASS and _refresh_dependency_gates(root, report):
                    report, path = check_phase(root, phase, update_state=True)
                if report["status"] != PASS:
                    return {
                        "status": "gate_failed", "phase": phase,
                        "report": str(path.relative_to(root)), "details": report,
                    }
                continue
            waiting = [task["task_id"] for task in tasks if task["state"] == "planned"]
            return {
                "status": "waiting" if waiting else "no_work",
                "phase": phase,
                "waiting_tasks": waiting,
                "runtime": store.summary(),
            }
    raise RuntimeError("adaptive advance exceeded the phase-transition safety bound")


STALE_DEPENDENCY = re.compile(r"^dependency gate (\w+): (?:stale input |report status )")


def _refresh_dependency_gates(root: Path, report: dict[str, Any]) -> bool:
    """Re-check earlier gates that are stale only because their recorded inputs moved
    (an engine sync rewrites WORKFLOW.yaml and the validators). Returns whether every
    problem was such a gate and each passed again; real failures are left alone."""
    problems = [str(item) for item in list(report.get("failures", [])) + list(report.get("unknowns", []))]
    matches = [STALE_DEPENDENCY.match(item) for item in problems]
    if not problems or not all(matches):
        return False
    order = phase_order(root)
    gates = sorted({match.group(1) for match in matches if match}, key=lambda gate: order.index(gate) if gate in order else len(order))
    for gate in gates:
        # A completed phase is re-checked as completed work, then its result recorded.
        report, path = check_phase(root, gate, update_state=False)
        if report["status"] != PASS:
            return False
        set_phase_result(root, gate, PASS, str(path.relative_to(root)))
    return True


def _reopen_unsatisfied_phases(root: Path, store: RuntimeStore) -> None:
    """A passed gate no longer holds once any of its phase's tasks must rerun."""
    state = load_state(root)
    for phase_id in phase_order(root):
        if state["phases"][phase_id]["status"] != "complete":
            continue
        pending = [task["task_id"] for task in store.tasks(phase=phase_id) if task["state"] not in SATISFIED_STATES]
        if pending:
            reopen_phase(root, phase_id, f"{len(pending)} task(s) must rerun, e.g. {pending[0]}")
        elif phase_id == "capture":
            # A discovery channel reopened after capture finished brings capture back.
            reopened = [item["channel"] for item in store.discovery_channels() if item["state"] not in DISCOVERY_TERMINAL]
            if reopened:
                reopen_phase(root, phase_id, f"discovery channel(s) reopened: {', '.join(reopened)}")


def complete_work(
    root: Path,
    task_id: str,
    worker_id: str,
    *,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with open_runtime(root) as store:
        task = store.task(task_id)
        if not task:
            raise KeyError(f"unknown task: {task_id}")
        if task["metadata"].get("executor") == "runtime" and worker_id != RUNTIME_WORKER:
            raise ValueError(f"{task_id}: runtime-executed work is completed by `research_control run`, not a worker")
        result = _complete(root, store, task, worker_id, telemetry=telemetry)
        AdaptivePlanner(root, store).reconcile()
        return result


def _complete(
    root: Path,
    store: RuntimeStore,
    task: dict[str, Any],
    worker_id: str,
    *,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = task["task_id"]
    _validate_semantic_receipt(root, store, task)
    result = store.complete(task_id, worker_id, telemetry=telemetry)
    if task["task_type"] == "capture":
        receipt = load_json(root / task["metadata"]["receipt"])
        source_id = task["metadata"]["source_id"]
        if receipt["status"] == "captured":
            store.update_source(
                source_id,
                status="captured",
                local_paths=list(receipt.get("local_paths", [])),
                content_bytes=int(receipt.get("content_bytes", 0)),
                content_tokens=int(receipt.get("estimated_tokens", 0)),
                metadata={"capture_receipt": task["metadata"]["receipt"]},
            )
        else:
            store.update_source(
                source_id,
                status="blocked",
                metadata={
                    "capture_receipt": task["metadata"]["receipt"],
                    "capture_reason": receipt.get("reason", receipt.get("disposition", {}).get("reason", "blocked")),
                },
            )
    return result


def check_work(root: Path, task_id: str) -> dict[str, Any]:
    """What `work succeed` would refuse, without completing: a worker runs this until it is clean.

    Covers the checks completion applies, plus the task's synthesis validators,
    which completion leaves to the phase gate.
    """
    with open_runtime(root) as store:
        task = store.task(task_id)
        if not task:
            raise KeyError(f"unknown task: {task_id}")
        problems: list[str] = []
        try:
            _validate_semantic_receipt(root, store, task)
        except ValueError as error:
            problems.append(str(error))
        document = workflow(root / "WORKFLOW.yaml")
        phase = next((item for item in document["phases"] if item["id"] == task["phase"]), None)
        if phase is not None:
            for validator_id in task.get("validators", []):
                if validator_id.startswith("synthesis_"):
                    report = run_validator(root, phase, validator_id)
                    if report.get("status") != PASS:
                        problems.extend(f"{validator_id}: {item}" for item in (report.get("failures") or report.get("unknowns") or [])[:20])
        for output in task["outputs"]:
            if "*" not in output and "{" not in output and not (root / output).exists():
                problems.append(f"output missing: {output}")
        return {"task_id": task_id, "problems": problems, "status": "clean" if not problems else "problems"}


def _validate_semantic_receipt(root: Path, store: RuntimeStore, task: dict[str, Any]) -> None:
    if task["task_type"] in {"brand_guide", "diagram_modeler", "diagram_builder"}:
        document = workflow(root / "WORKFLOW.yaml")
        phase = next(item for item in document["phases"] if item["id"] == task["phase"])
        for validator_id in task.get("validators", []):
            validation = run_validator(root, phase, validator_id)
            if validation.get("status") != PASS:
                details = validation.get("failures") or validation.get("unknowns") or ["validation did not pass"]
                raise ValueError(
                    f"{task['task_id']}: {validator_id} failed: {'; '.join(str(item) for item in details)}"
                )
    if task["task_type"] == "source_discovery":
        channels = task["metadata"].get("channels") or [task["metadata"]["channel"]]
        receipts = task["metadata"].get("receipts") or [task["metadata"]["receipt"]]
        for channel, relative in zip(channels, receipts):
            path = root / relative
            if not path.is_file():
                raise ValueError(f"{task['task_id']}: discovery receipt is missing for {channel}")
            receipt = load_json(path)
            current = store.discovery_channel(channel)
            if receipt.get("channel") != channel:
                raise ValueError(f"{task['task_id']}: discovery receipt channel mismatch for {channel}")
            if not current or current["state"] not in DISCOVERY_TERMINAL:
                raise ValueError(f"{task['task_id']}: discovery channel {channel} has not reached a terminal state")
            if receipt.get("status") != current["state"]:
                raise ValueError(f"{task['task_id']}: {channel} receipt does not match scheduler state")
            if not str(receipt.get("evidence", "")).strip():
                raise ValueError(f"{task['task_id']}: {channel} receipt lacks completion evidence")
    if task["task_type"] == "alternate_copies":
        listed = next((item["path"] for item in task["inputs"] if item.get("id") == "blocked_sources"), BLOCKED_SOURCES_LIST)
        blocked = {row["source_id"] for row in load_jsonl(root / listed)}
        part = root / ALTERNATES_PART
        handled = {row["source_id"] for row in load_jsonl(part)} if part.is_file() else set()
        missing = sorted(blocked - handled)
        if missing:
            raise ValueError(
                f"{task['task_id']}: no alternate or --none record for: {', '.join(missing[:15])}"
            )
    if task["task_type"] == "extraction" and task["metadata"].get("candidate_part"):
        failures = validate_extraction_part(root, task)
        if failures:
            raise ValueError(
                f"{task['task_id']}: extraction parts are invalid ({len(failures)} problems): {'; '.join(failures[:10])}"
            )
    if task["task_type"] == "verification" and task["metadata"].get("part"):
        failures = verification.validate_part(root, task["metadata"]["part"], task["metadata"]["fact_ids"])
        if failures:
            raise ValueError(f"{task['task_id']}: verdict part is invalid: {'; '.join(failures[:10])}")
    if task["task_type"] == "triage":
        failures = validate_triage(root)
        if failures:
            raise ValueError(f"{task['task_id']}: triage is invalid: {'; '.join(failures[:10])}")
    if task["task_type"] == "retriage":
        failures = validate_retriage(root)
        if failures:
            raise ValueError(f"{task['task_id']}: re-triage is invalid: {'; '.join(failures[:10])}")
    if task["task_type"] == "capture":
        path = root / task["metadata"]["receipt"]
        if not path.is_file():
            raise ValueError(f"{task['task_id']}: capture receipt is missing")
        receipt = load_json(path)
        if receipt.get("source_id") != task["metadata"]["source_id"]:
            raise ValueError(f"{task['task_id']}: capture receipt source mismatch")
        if receipt.get("status") not in {"captured", "blocked"}:
            raise ValueError(f"{task['task_id']}: capture is not terminal; create required derivatives or record blocking evidence")
        if receipt.get("status") == "captured" and not receipt.get("canonical_text_ready"):
            raise ValueError(f"{task['task_id']}: captured source lacks canonical text")


def retry_media(root: Path, source_ids: list[str] | None = None) -> dict[str, Any]:
    """Re-queue media captures whose transcript was unavailable.

    YouTube rate limits and bot checks come and go, so a later attempt can
    succeed. The capture tasks go stale and the runtime recaptures them on the
    next `run`; dependent reducers are invalidated through the usual hashes.
    """
    selected = set(source_ids or [])
    requeued: list[str] = []
    with open_runtime(root) as store:
        for task in store.tasks(states={"succeeded", "blocked", "failed"}):
            if task["task_type"] != "capture":
                continue
            source_id = task["metadata"].get("source_id", "")
            if selected and source_id not in selected:
                continue
            receipt_path = root / task["metadata"]["receipt"]
            receipt = load_json(receipt_path) if receipt_path.is_file() else {}
            source = store.source(source_id) or {}
            is_media = source.get("channel") in {"video", "podcasts"} or is_media_url(source.get("canonical_url", ""))
            transcribed = (receipt.get("transcript") or {}).get("status") == "transcribed"
            if source_id in selected or (is_media and not transcribed):
                store.mark_stale(task["task_id"], "media transcript retry requested")
                requeued.append(source_id)
    return {"requeued": requeued, "next": "python3 -m research_control run"}


def requeue_captures(root: Path, source_ids: list[str] | None = None, *, blocked: bool = False) -> dict[str, Any]:
    """Re-queue chosen captures, or every blocked one, after a capture method improves."""
    selected = set(source_ids or [])
    requeued: list[str] = []
    with open_runtime(root) as store:
        for task in store.tasks(states={"succeeded", "blocked", "failed"}):
            if task["task_type"] != "capture":
                continue
            source_id = task["metadata"].get("source_id", "")
            receipt_path = root / task["metadata"]["receipt"]
            receipt = load_json(receipt_path) if receipt_path.is_file() else {}
            if source_id in selected or (blocked and receipt.get("status") == "blocked"):
                store.mark_stale(task["task_id"], "recapture requested")
                requeued.append(source_id)
    return {"requeued": requeued, "next": "python3 -m research_control run"}


def runtime_status(root: Path) -> dict[str, Any]:
    state = load_state(root)
    with open_runtime(root) as store:
        store.invalidate_stale()
        tasks = store.tasks(phase=current_phase(root, state)) if current_phase(root, state) else []
        return {
            "run_id": state["run_id"],
            "company_url": state["company_url"],
            "status": state["status"],
            "current_phase": current_phase(root, state),
            "phase_statuses": {key: value["status"] for key, value in state["phases"].items()},
            "current_tasks": [
                {"task_id": task["task_id"], "task_type": task["task_type"], "state": task["state"], "worker_id": task["lease_owner"]}
                for task in tasks
            ],
            "runtime": store.summary(),
        }
