"""Thin state and task-packet orchestration for agent-driven research runs."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_control import PASS
from research_control.hashing import hash_path, hash_patterns
from research_control.io import (
    append_jsonl,
    atomic_write_json,
    atomic_write_text,
    load_json,
    load_jsonl,
    resolve_pattern,
    utc_now,
    workflow,
)
from research_control.routing import model_route


STATE_PATH = "tools/outputs/run-state.json"
ACTIVE_PATH = "tools/outputs/active-tasks.json"
PACKET_DIRECTORY = "tools/outputs/task-packets"
TASK_SCHEMAS = {
    "capture": ["research_control/schemas/source.schema.json", "research_control/schemas/disposition.schema.json"],
    "extraction": ["research_control/schemas/disposition.schema.json"],
    "filing": ["research_control/schemas/fact.schema.json", "research_control/schemas/disposition.schema.json"],
    "verification": ["research_control/schemas/verification.schema.json"],
    "technical_review": ["research_control/schemas/review-finding.schema.json"],
    "devils_advocate": ["research_control/schemas/review-finding.schema.json"],
    "insider_review": ["research_control/schemas/review-finding.schema.json"],
    "editor_review": ["research_control/schemas/review-finding.schema.json"],
    "visual_review": [
        "research_control/schemas/visual-review.schema.json",
        "research_control/schemas/diagram-review.schema.json",
    ],
    "diagram_modeler": ["research_control/schemas/diagram-models.schema.json"],
    "diagram_builder": ["research_control/schemas/diagram-models.schema.json"],
}
RUN_DIRECTORIES = (
    "00-inputs",
    "01-sources",
    "02-facts",
    "03-timelines",
    "04-competitors",
    "05-synthesis/design",
    "05-synthesis/brand-guide/evidence/screenshots",
    "06-checks",
    "07-final-report",
    "scratchpad",
    "tools/candidates",
    "tools/digests",
    "tools/lists",
    "tools/outputs/cited-facts",
    "tools/outputs/discovery",
    "tools/outputs/gates",
    "tools/outputs/reconciliation",
    "tools/outputs/task-packets",
    "tools/outputs/validations",
    "tools/outputs/web-cache/objects",
    "tools/outputs/worker-parts/capture",
    "tools/outputs/worker-parts/discovery",
    "tools/outputs/worker-parts/extraction",
    "tools/extracts/canonical",
    "tools/extracts/slices",
)


def validate_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("company URL must be an absolute public http(s) URL")
    return value.strip()


def _workflow(root: Path) -> dict[str, Any]:
    return workflow(root / "WORKFLOW.yaml")


def load_state(root: Path) -> dict[str, Any]:
    path = root / STATE_PATH
    if not path.is_file():
        raise FileNotFoundError("no run state; execute `python3 -m research_control init --url URL`")
    value = load_json(path)
    if not isinstance(value, dict) or not value.get("company_url"):
        raise ValueError(f"{STATE_PATH} is malformed")
    return value


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    atomic_write_json(root / STATE_PATH, state)
    lines = [
        "# Workflow state",
        "",
        f"- Run ID: `{state['run_id']}`",
        f"- Company URL: {state['company_url']}",
        f"- Overall status: **{state['status']}**",
        f"- Updated: {state['updated_at']}",
        "",
        "| Phase | Status | Completed |",
        "|---|---|---|",
    ]
    for phase_id, record in state["phases"].items():
        lines.append(f"| {phase_id} | {record['status']} | {record.get('completed_at') or ''} |")
    atomic_write_text(root / "WORKFLOW_STATE.md", "\n".join(lines) + "\n")


def append_history(root: Path, event: str, details: str) -> None:
    path = root / "RUN_HISTORY.md"
    prior = path.read_text(encoding="utf-8") if path.exists() else "# Run history\n\n"
    atomic_write_text(path, prior + f"- {utc_now()} | `{event}` | {details}\n")


def _ensure_git(root: Path) -> None:
    if (root / ".git").exists():
        return
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=root, text=True, capture_output=True
    )
    if inside.returncode == 0 and inside.stdout.strip() == "true":
        # A run directory inside the template checkout is versioned by that repository.
        return
    result = subprocess.run(["git", "init"], cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"could not initialize git: {result.stderr.strip()}")


def initialize(root: Path, company_url: str) -> dict[str, Any]:
    company_url = validate_url(company_url)
    state_path = root / STATE_PATH
    if state_path.exists():
        state = load_state(root)
        if state["company_url"] != company_url:
            raise ValueError(
                f"run already initialized for {state['company_url']}; preserve it or use a clean repository"
            )
        return state

    _ensure_git(root)
    for relative in RUN_DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)

    document = _workflow(root)
    created = utc_now()
    host = urlparse(company_url).netloc.lower().removeprefix("www.")
    slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-") or "company"
    state = {
        "schema_version": "1.0.0",
        "run_id": f"{slug}-{created[:10]}",
        "company_url": company_url,
        "company_host": host,
        "created_at": created,
        "updated_at": created,
        "status": "running",
        "phases": {
            phase["id"]: {
                "status": "ready" if index == 0 else "pending",
                "completed_at": None,
                "report": None,
            }
            for index, phase in enumerate(document["phases"])
        },
    }

    atomic_write_text(root / document["global"]["ledger"], "")
    atomic_write_json(root / ACTIVE_PATH, {})
    save_state(root, state)
    append_history(root, "initialized", f"company_url={company_url}")
    return state


def phase_order(root: Path) -> list[str]:
    return [phase["id"] for phase in _workflow(root)["phases"]]


def current_phase(root: Path, state: dict[str, Any] | None = None) -> str | None:
    state = state or load_state(root)
    for phase_id in phase_order(root):
        if state["phases"][phase_id]["status"] != "complete":
            return phase_id
    return None


def reopen_phase(root: Path, phase_id: str, reason: str) -> None:
    """Return a completed phase to ready when its work is no longer current.

    Completed later phases reopen too, so the run passes through each again:
    the planner re-plans it against the changed upstream work, and a phase
    whose work is still current simply passes its gate again.
    """
    state = load_state(root)
    record = state["phases"][phase_id]
    if record["status"] != "complete":
        return
    record["status"] = "ready"
    record.pop("completed_at", None)
    order = phase_order(root)
    later = [item for item in order[order.index(phase_id) + 1:] if state["phases"][item]["status"] == "complete"]
    for item in later:
        state["phases"][item]["status"] = "pending"
        state["phases"][item].pop("completed_at", None)
    state["status"] = "running"
    save_state(root, state)
    append_history(root, "phase-reopened", f"{phase_id}: {reason}" + (f"; later phases reopened: {', '.join(later)}" if later else ""))


def set_phase_result(root: Path, phase_id: str, status: str, report: str) -> dict[str, Any]:
    state = load_state(root)
    if phase_id not in state["phases"]:
        raise KeyError(f"unknown phase {phase_id}")
    record = state["phases"][phase_id]
    record["report"] = report
    if status == PASS:
        record["status"] = "complete"
        record["completed_at"] = utc_now()
        state["status"] = "running"
        order = phase_order(root)
        index = order.index(phase_id)
        if index + 1 < len(order):
            next_record = state["phases"][order[index + 1]]
            if next_record["status"] == "pending":
                next_record["status"] = "ready"
        else:
            state["status"] = "released"
    else:
        record["status"] = "blocked"
        record["completed_at"] = None
        state["status"] = "blocked"
    save_state(root, state)
    append_history(root, f"phase-{status.lower()}", f"phase={phase_id} report={report}")
    return state


def _phase(document: dict[str, Any], phase_id: str) -> dict[str, Any]:
    for phase in document["phases"]:
        if phase["id"] == phase_id:
            return phase
    raise KeyError(f"unknown phase {phase_id}")


def all_task_definitions(root: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    document = _workflow(root)
    definitions: dict[str, tuple[str, dict[str, Any]]] = {}
    for phase_id, profile in document.get("execution_profiles", {}).items():
        for task in profile.get("tasks", []):
            full_id = f"{phase_id}.{task['id']}"
            definitions[full_id] = (phase_id, task)
    return definitions


def _latest_ledger(root: Path) -> dict[str, dict[str, Any]]:
    document = _workflow(root)
    path = root / document["global"]["ledger"]
    rows = load_jsonl(path) if path.is_file() and path.stat().st_size else []
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = str(row.get("task_id", ""))
        if not task_id:
            continue
        if task_id not in latest or int(row.get("attempt", 0)) > int(latest[task_id].get("attempt", 0)):
            latest[task_id] = row
    return latest


def _task_current(root: Path, row: dict[str, Any]) -> bool:
    hashes = row.get("output_hashes", {})
    outputs_current = bool(row.get("expected_outputs")) and all(
        hash_path(root / relative) == hashes.get(relative)
        for relative in row.get("expected_outputs", [])
    )
    if not outputs_current:
        return False
    if row.get("track_input_staleness"):
        return hash_patterns(root, row.get("input_patterns", [])) == row.get("input_hashes", {})
    return True


def _read_prompt(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"task prompt missing: {relative}")
    return path.read_text(encoding="utf-8").strip()


def _write_packet(root: Path, phase: dict[str, Any], task: dict[str, Any]) -> tuple[Path, Path]:
    task_id = f"{phase['id']}.{task['id']}"
    route = model_route(root, task["task_type"], task.get("metadata"))
    packet = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "phase": phase["id"],
        "task_type": task["task_type"],
        "independent": bool(task.get("independent")),
        "exclusive_inputs": bool(task.get("exclusive_inputs", True)),
        "output_mode": task.get("output_mode", "create"),
        "track_input_staleness": bool(task.get("track_input_staleness")),
        "model_route": route,
        "company_url": load_state(root)["company_url"],
        "inputs": task.get("inputs", phase.get("inputs", [])),
        "outputs": task.get("outputs", []),
        "required_validators": list(task.get(
            "validators", [item["id"] for item in phase.get("validators", [])]
        )),
        "required_reconciliations": [item["id"] for item in phase.get("reconciliations", [])],
        "depends_on": [f"{phase['id']}.{item}" for item in task.get("depends_on", [])],
        "prompt_files": [*task.get("cores", []), task["prompt"]],
        "schema_files": TASK_SCHEMAS.get(task["task_type"], []),
        "created_at": utc_now(),
    }
    directory = root / PACKET_DIRECTORY
    json_path = directory / f"{task_id}.json"
    md_path = directory / f"{task_id}.md"
    atomic_write_json(json_path, packet)

    lines = [
        f"# Task packet: {task_id}",
        "",
        f"- Company URL: {packet['company_url']}",
        f"- Phase: `{phase['id']}`",
        f"- Task type: `{task['task_type']}`",
        f"- Independent context required: `{'yes' if task.get('independent') else 'no'}`",
        f"- Output mode: `{packet['output_mode']}`",
        f"- Advisory model tier: `{route['tier']}` / `{route['model_class']}` / effort `{route['effort']}`",
        "- Model routing is optional; use the available model when the host cannot route models.",
        "",
        "## Inputs",
        "",
    ]
    for item in packet["inputs"]:
        location = item.get("path", item.get("kind", "runtime value"))
        lines.append(f"- `{item['id']}`: `{location}` (required: {bool(item.get('required'))})")
    lines.extend(["", "## Exact outputs", ""])
    lines.extend(f"- `{item}`" for item in task.get("outputs", []))
    lines.extend(["", "## Required controls", ""])
    lines.append("- Task dependencies: " + (", ".join(packet["depends_on"]) or "none"))
    lines.append("- Validators: " + (", ".join(packet["required_validators"]) or "none"))
    lines.append("- Reconciliations: " + (", ".join(packet["required_reconciliations"]) or "none"))
    lines.append("- Schemas: " + (", ".join(packet["schema_files"]) or "phase validators define the contract"))
    lines.extend(["", "## Instructions", ""])
    for relative in packet["prompt_files"]:
        lines.extend([f"### `{relative}`", "", _read_prompt(root, relative), ""])
    lines.extend([
        "## Completion protocol",
        "",
        f"Start with `python3 -m research_control task start {task_id} --worker-id WORKER_ID`.",
        f"After every exact output exists, run `python3 -m research_control task finish {task_id}`.",
        "Do not mark the phase complete yourself.",
        "",
    ])
    atomic_write_text(md_path, "\n".join(lines))
    return md_path, json_path


def next_packets(root: Path, write: bool = True) -> dict[str, Any]:
    state = load_state(root)
    phase_id = current_phase(root, state)
    if phase_id is None:
        return {"status": "released", "phase": None, "pending": [], "complete": []}
    document = _workflow(root)
    phase = _phase(document, phase_id)
    profile = document.get("execution_profiles", {}).get(phase_id, {})
    latest = _latest_ledger(root)
    pending: list[dict[str, Any]] = []
    complete: list[str] = []
    waiting: list[dict[str, Any]] = []
    for task in profile.get("tasks", []):
        task_id = f"{phase_id}.{task['id']}"
        row = latest.get(task_id)
        if row and row.get("status") == "succeeded" and row.get("output_validation_status") == PASS and _task_current(root, row):
            complete.append(task_id)
            continue
        dependency_ids = [f"{phase_id}.{item}" for item in task.get("depends_on", [])]
        unmet = [
            dependency for dependency in dependency_ids
            if not (
                latest.get(dependency, {}).get("status") == "succeeded"
                and latest.get(dependency, {}).get("output_validation_status") == PASS
                and _task_current(root, latest[dependency])
            )
        ]
        if unmet:
            waiting.append({"task_id": task_id, "waiting_for": unmet})
            continue
        if write:
            md_path, json_path = _write_packet(root, phase, task)
        else:
            directory = root / PACKET_DIRECTORY
            md_path = directory / f"{task_id}.md"
            json_path = directory / f"{task_id}.json"
        pending.append({
            "task_id": task_id,
            "task_type": task["task_type"],
            "independent": bool(task.get("independent")),
            "packet": str(md_path.relative_to(root)),
            "packet_json": str(json_path.relative_to(root)),
        })
    return {
        "status": "tasks" if pending else "waiting" if waiting else "ready_for_check",
        "phase": phase_id,
        "automatic": bool(profile.get("automatic")),
        "pending": pending,
        "waiting": waiting,
        "complete": complete,
    }


def _active(root: Path) -> dict[str, Any]:
    path = root / ACTIVE_PATH
    if not path.exists():
        return {}
    value = load_json(path)
    return value if isinstance(value, dict) else {}


def start_task(root: Path, task_id: str, worker_id: str) -> dict[str, Any]:
    definitions = all_task_definitions(root)
    if task_id not in definitions:
        raise KeyError(f"unknown task {task_id}; run `python3 -m research_control next`")
    phase_id, task = definitions[task_id]
    if current_phase(root) != phase_id:
        raise ValueError(f"task {task_id} is not permitted in the current phase")
    active = _active(root)
    if task_id in active:
        return active[task_id]
    latest = _latest_ledger(root)
    unmet = [
        f"{phase_id}.{dependency}"
        for dependency in task.get("depends_on", [])
        if not (
            latest.get(f"{phase_id}.{dependency}", {}).get("status") == "succeeded"
            and latest.get(f"{phase_id}.{dependency}", {}).get("output_validation_status") == PASS
            and _task_current(root, latest[f"{phase_id}.{dependency}"])
        )
    ]
    if unmet:
        raise ValueError(f"task dependencies are incomplete: {', '.join(unmet)}")
    state = load_state(root)
    if (
        latest.get(task_id, {}).get("status") == "succeeded"
        and _task_current(root, latest[task_id])
        and state["phases"][phase_id]["status"] != "blocked"
    ):
        raise ValueError(f"task {task_id} already succeeded")
    attempts = [
        int(row.get("attempt", 0))
        for row in (load_jsonl(root / _workflow(root)["global"]["ledger"]) if (root / _workflow(root)["global"]["ledger"]).stat().st_size else [])
        if row.get("task_id") == task_id
    ]
    attempt = max(attempts, default=0) + 1
    maximum = int(_workflow(root)["global"]["retry_policy"]["max_attempts_per_assignment"])
    if attempt > maximum:
        raise ValueError(f"task {task_id} exhausted its {maximum} permitted attempts")

    if task.get("independent"):
        used_workers = {
            str(row.get("worker_id"))
            for row in latest.values()
            if row.get("phase") == phase_id and row.get("independent") and row.get("task_id") != task_id
        }
        used_workers.update(
            str(row.get("worker_id"))
            for row in active.values()
            if row.get("phase") == phase_id and row.get("independent") and row.get("task_id") != task_id
        )
        if worker_id in used_workers:
            raise ValueError(f"independent task requires a worker ID not already used in phase {phase_id}")

    phase = _phase(_workflow(root), phase_id)
    record = {
        "worker_id": worker_id,
        "task_id": task_id,
        "attempt": attempt,
        "phase": phase_id,
        "task_type": task["task_type"],
        "input_ids": [item["id"] for item in task.get("inputs", phase.get("inputs", []))],
        "input_patterns": [item["path"] for item in task.get("inputs", phase.get("inputs", [])) if item.get("path")],
        "input_hashes": hash_patterns(root, [item["path"] for item in task.get("inputs", phase.get("inputs", [])) if item.get("path")]),
        "exclusive_inputs": bool(task.get("exclusive_inputs", True)),
        "expected_output_patterns": task.get("outputs", []),
        "required_validators": list(task.get(
            "validators", [item["id"] for item in phase.get("validators", [])]
        )),
        "depends_on": [f"{phase_id}.{item}" for item in task.get("depends_on", [])],
        "independent": bool(task.get("independent")),
        "output_mode": task.get("output_mode", "create"),
        "track_input_staleness": bool(task.get("track_input_staleness")),
        "status": "running",
        "started_at": utc_now(),
    }
    active[task_id] = record
    atomic_write_json(root / ACTIVE_PATH, active)
    append_history(root, "task-started", f"task={task_id} attempt={attempt} worker={worker_id}")
    return record


def _resolved_outputs(root: Path, patterns: list[str]) -> tuple[list[str], list[str]]:
    outputs: list[str] = []
    missing: list[str] = []
    for pattern in patterns:
        matches = [
            path for path in resolve_pattern(root, pattern)
            if path.is_dir() or (path.is_file() and path.stat().st_size > 0)
        ]
        if not matches:
            missing.append(pattern)
        else:
            outputs.extend(str(path.relative_to(root)) for path in matches)
    return list(dict.fromkeys(outputs)), missing


def finish_task(root: Path, task_id: str) -> dict[str, Any]:
    active = _active(root)
    if task_id not in active:
        raise ValueError(f"task {task_id} is not active")
    record = active[task_id]
    outputs, missing = _resolved_outputs(root, record["expected_output_patterns"])
    if missing:
        raise ValueError(f"task outputs missing or empty: {', '.join(missing)}")
    if record["task_type"] in {"brand_guide", "diagram_modeler", "diagram_builder"}:
        from research_control.checks import run_validator

        phase = _phase(_workflow(root), record["phase"])
        for validator_id in record.get("required_validators", []):
            validation = run_validator(root, phase, validator_id)
            if validation.get("status") != PASS:
                details = validation.get("failures") or validation.get("unknowns") or ["validation did not pass"]
                raise ValueError(f"{task_id}: {validator_id} failed: {'; '.join(details)}")
    terminal = {
        **record,
        "expected_outputs": outputs,
        "status": "succeeded",
        "finished_at": utc_now(),
        "exit_status": 0,
        "output_validation_status": PASS,
        "output_hashes": {relative: hash_path(root / relative) for relative in outputs},
    }
    if terminal.get("track_input_staleness"):
        terminal["input_hashes"] = hash_patterns(root, terminal.get("input_patterns", []))
    terminal.pop("expected_output_patterns", None)
    append_jsonl(root / _workflow(root)["global"]["ledger"], terminal)
    del active[task_id]
    atomic_write_json(root / ACTIVE_PATH, active)
    append_history(root, "task-succeeded", f"task={task_id} attempt={terminal['attempt']}")
    return terminal


def fail_task(root: Path, task_id: str, reason: str) -> dict[str, Any]:
    active = _active(root)
    if task_id not in active:
        raise ValueError(f"task {task_id} is not active")
    record = active[task_id]
    terminal = {
        **record,
        "expected_outputs": [],
        "status": "failed",
        "finished_at": utc_now(),
        "exit_status": 1,
        "output_validation_status": "FAIL",
        "output_hashes": {},
        "failure_reason": reason.strip() or "unspecified failure",
    }
    terminal.pop("expected_output_patterns", None)
    append_jsonl(root / _workflow(root)["global"]["ledger"], terminal)
    del active[task_id]
    atomic_write_json(root / ACTIVE_PATH, active)
    append_history(root, "task-failed", f"task={task_id} attempt={terminal['attempt']} reason={terminal['failure_reason']}")
    return terminal


def status_summary(root: Path) -> dict[str, Any]:
    state = load_state(root)
    next_info = next_packets(root, write=False)
    active = _active(root)
    return {
        "run_id": state["run_id"],
        "company_url": state["company_url"],
        "status": state["status"],
        "current_phase": current_phase(root, state),
        "phase_statuses": {key: value["status"] for key, value in state["phases"].items()},
        "active_tasks": sorted(active),
        "pending_tasks": [item["task_id"] for item in next_info.get("pending", [])],
        "next_action": next_info["status"],
    }
