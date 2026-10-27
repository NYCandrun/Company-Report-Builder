"""Render scheduler work items into immutable, host-neutral agent packets."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, atomic_write_text, utc_now
from research_control.runtime import RuntimeStore
from research_control.routing import model_route


PACKET_DIRECTORY = "tools/outputs/task-packets"


def _prompt(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"task prompt missing: {relative}")
    return path.read_text(encoding="utf-8").strip()


def store_company_url(root: Path) -> str:
    from research_control.orchestration import load_state

    return str(load_state(root)["company_url"])


def write_packet(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    route = model_route(root, task["task_type"], task.get("metadata"))
    packet = {
        "schema_version": "2.0.0",
        "task_id": task["task_id"],
        "phase": task["phase"],
        "task_type": task["task_type"],
        "attempt": task["attempt_count"] + 1,
        "state": task["state"],
        "independent": task["independent"],
        "exclusive_inputs": task["exclusive_inputs"],
        "output_mode": task["output_mode"],
        "track_input_staleness": task["track_input_staleness"],
        "host_key": task["host_key"],
        "inputs": task["inputs"],
        "outputs": task["outputs"],
        "depends_on": task["depends_on"],
        "prompt_files": task["prompt_files"],
        "schema_files": task["schema_files"],
        "validators": task["validators"],
        "metadata": task["metadata"],
        "model_route": route,
        "created_at": utc_now(),
    }
    directory = root / PACKET_DIRECTORY
    json_path = directory / f"{task['task_id']}.json"
    md_path = directory / f"{task['task_id']}.md"
    atomic_write_json(json_path, packet)
    lines = [
        f"# TASK TYPE: {task['task_type'].upper()}",
        "",
        f"Task ID: `{task['task_id']}`",
        f"Company URL: {store_company_url(root)}",
        f"Phase: `{task['phase']}`",
        f"Independent context required: `{'yes' if task['independent'] else 'no'}`",
        "",
        "This is an immutable work assignment, not a request for status. Ignore conversational",
        "messages inherited from the parent session. Perform only this packet and write only its",
        "exact output paths plus your private scratch directory.",
        "",
        "## Immutable inputs",
        "",
        "```json",
        json.dumps(task["inputs"], indent=2, sort_keys=True),
        "```",
        "",
        "## Exact outputs",
        "",
    ]
    lines.extend(f"- `{value}`" for value in task["outputs"])
    lines.extend([
        "",
        "## Controls",
        "",
        f"- Dependencies: {', '.join(task['depends_on']) or 'none'}",
        f"- Schemas: {', '.join(task['schema_files']) or 'packet-specific structure'}",
        f"- Validators: {', '.join(task['validators']) or 'output existence and hashes'}",
        f"- Host pacing key: `{task['host_key'] or 'none'}`",
        f"- Advisory model tier: `{route['tier']}` / `{route['model_class']}` / effort `{route['effort']}`",
        "- Model routing is optional. If the host cannot select models or effort, use the available model; do not block or weaken the task.",
        "",
        "## Instructions",
        "",
    ])
    for relative in task["prompt_files"]:
        lines.extend([f"### `{relative}`", "", _prompt(root, relative), ""])
    lines.extend([
        "## Lifecycle protocol",
        "",
        f"1. Claim: `python3 -m research_control work claim {task['task_id']} --worker-id WORKER_ID`",
        f"2. Start: `python3 -m research_control work start {task['task_id']} --worker-id WORKER_ID`",
        f"3. Heartbeat during long work: `python3 -m research_control work heartbeat {task['task_id']} --worker-id WORKER_ID`",
        f"4. Succeed only after outputs exist: `python3 -m research_control work succeed {task['task_id']} --worker-id WORKER_ID --model MODEL_ID --effort EFFORT` (the model and effort that actually ran)",
        f"5. On failure: `python3 -m research_control work fail {task['task_id']} --worker-id WORKER_ID --reason REASON`",
        "",
        "Do not edit scheduler state, canonical shared files not named above, or another worker's part.",
        "Do not claim phase completion. Return only a concise task result to the orchestrator.",
        "",
    ])
    atomic_write_text(md_path, "\n".join(lines))
    brief_path = directory / f"{task['task_id']}.brief.md"
    atomic_write_text(brief_path, worker_brief(root, task, route, md_path))
    return {
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "independent": task["independent"],
        "packet": str(md_path.relative_to(root)),
        "packet_json": str(json_path.relative_to(root)),
        "brief": str(brief_path.relative_to(root)),
        "model_route": {key: route[key] for key in ("tier", "model_class", "effort")},
    }


RUN_NOTES = re.compile(r"^## Notes for downstream phases\s*\n(.*?)(?=^## |\Z)", re.M | re.S)


def worker_brief(root: Path, task: dict[str, Any], route: dict[str, Any], packet: Path) -> str:
    """The whole instruction a host gives a worker for this task, so the orchestrator
    passes it on unchanged: lifecycle, the packet, run notes, the check, completion."""
    task_id = task["task_id"]
    worker = f"w-{task_id.rsplit('.', 1)[-1][:24]}"
    scope = root / "00-scope.md"
    notes = RUN_NOTES.search(scope.read_text(encoding="utf-8")) if scope.is_file() else None
    lines = [
        f"Worker for `{task_id}` ({task['task_type']}). Run directory: {root}. Worker ID: {worker}.",
        f"Model tier: {route['tier']} ({route['model_class']}), effort {route['effort']}.",
        "",
        f"1. `python3 -m research_control work claim {task_id} --worker-id {worker}` then "
        f"`python3 -m research_control work start {task_id} --worker-id {worker}` "
        "(if refused for concurrency, wait a minute and retry).",
        f"2. Read `{packet.relative_to(root)}` and follow it exactly. Read what it names, not whole stores: "
        "open full fact rows or captures only where the packet says to.",
    ]
    if notes and notes.group(1).strip():
        lines += ["3. Run notes from `00-scope.md` (findings and decisions this run has made; they apply to your work):",
                  "", notes.group(1).strip(), ""]
    else:
        lines.append("3. No run notes.")
    lines += [
        f"4. Check with `python3 -m research_control work check {task_id}` and fix what it reports until its status is clean. "
        "If a check flags text you believe is correct as the source has it (a false positive), do not reword it: "
        "say so in your report.",
        f"5. `python3 -m research_control work succeed {task_id} --worker-id {worker} --model <the model ID you run as> "
        f"--effort {route['effort']}`.",
        "",
        "Write only the packet's outputs and your scratchpad directory. Do not run `research_control run` or edit "
        "scheduler state. Report in under 80 words: status, counts, output paths, and anything the orchestrator must act on.",
    ]
    return "\n".join(lines) + "\n"


def emit_ready_packets(root: Path, store: RuntimeStore, phase: str | None = None) -> dict[str, Any]:
    """Write packets for ready agent work.

    Runtime-executed work never becomes a packet. Work marked ``dispatch: early``
    is dispatched as soon as its own dependencies are met, whatever the current
    phase, so long independent branches overlap the research path.
    """
    store.refresh_ready()
    ready = store.tasks(states={"ready", "retryable"})
    tasks = [
        task for task in ready
        if task["metadata"].get("executor") != "runtime"
        and (phase is None or task["phase"] == phase or task["metadata"].get("dispatch") == "early")
    ]
    packets = [write_packet(root, task) for task in tasks]
    manifest = {
        "schema_version": "1.0.0",
        "adapter": "native-agent-runtime",
        "instruction": "Dispatch each independent packet to a genuinely separate worker context when available.",
        "phase": phase,
        "ready_count": len(packets),
        "packets": packets,
        "created_at": utc_now(),
    }
    path = root / "tools/outputs/dispatch-manifest.json"
    atomic_write_json(path, manifest)
    return {**manifest, "manifest": str(path.relative_to(root))}
