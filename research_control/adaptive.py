"""High-level adaptive orchestration service used by the CLI and agents."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from research_control import PASS
from research_control.checks import check_phase, run_validator
from research_control.dispatch import emit_ready_packets
from research_control.discovery import ALTERNATES_PART, BLOCKED_SOURCES_LIST
from research_control.io import load_json, load_jsonl, workflow
from research_control.orchestration import current_phase, initialize, load_state, phase_order
from research_control.automatic import RUNTIME_WORKER, run_automatic
from research_control.media import is_media_url
from research_control.planner import AdaptivePlanner
from research_control.triage import validate_triage
from research_control.runtime import ACTIVE_STATES, DISCOVERY_TERMINAL, RuntimeStore


def open_runtime(root: Path) -> RuntimeStore:
    state = load_state(root)
    configuration = workflow(root / "WORKFLOW.yaml").get("adaptive_runtime", {}).get("scheduler", {})
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
            if tasks and all(task["state"] == "succeeded" for task in tasks):
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
    if task["task_type"] == "triage":
        failures = validate_triage(root)
        if failures:
            raise ValueError(f"{task['task_id']}: triage is invalid: {'; '.join(failures[:10])}")
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
        for task in store.tasks(states={"succeeded"}):
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
        for task in store.tasks(states={"succeeded"}):
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
