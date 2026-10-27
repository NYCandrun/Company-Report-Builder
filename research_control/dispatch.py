"""Render scheduler work items into immutable, host-neutral agent packets."""

from __future__ import annotations

import json
from hashlib import sha256
import re
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, atomic_write_text, utc_now
from research_control.runtime import RuntimeStore
from research_control.routing import model_route


PACKET_DIRECTORY = "tools/outputs/task-packets"


ONLY_FOR = re.compile(r"^<!-- only: (.+?) -->[ \t]*\n?", re.M)


def _prompt(root: Path, relative: str, task_type: str | None = None) -> str:
    """A prompt file's text for one kind of task: a section marked `<!-- only: ... -->`
    is kept only for the task types it names, so each task carries the rules it uses."""
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"task prompt missing: {relative}")
    text = path.read_text(encoding="utf-8").strip()
    kept = []
    for section in re.split(r"(?m)^(?=## )", text):
        marker = ONLY_FOR.search(section)
        if marker and task_type is not None and task_type not in {item.strip() for item in marker.group(1).split(",")}:
            continue
        kept.append(ONLY_FOR.sub("", section))
    return "".join(kept).strip()


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
        lines.extend([f"### `{relative}`", "", _prompt(root, relative, task["task_type"]), ""])
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
    material, elsewhere = task_material(root, task)
    atomic_write_text(brief_path, worker_brief(root, task, route, md_path) + "\n".join([
        "", "---", "", "# The task's instructions", "", md_path.read_text(encoding="utf-8").strip(), "",
        "---", "", "# The files this task reads", "",
        material or "(none: the instructions name what to open)",
        *(["", "Not included above (open only what you need, as the instructions say):",
           *(f"- `{path}`" for path in elsewhere)] if elsewhere else []),
    ]) + "\n")
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


# What a worker reads is put in its brief, so it reads once instead of opening file
# after file. Stores (captures, the fact store, the final report) stay out: the
# instructions say which rows or passages to open.
MATERIAL_LIMIT = 1_000_000
MATERIAL_FILE_LIMIT = 400_000
NOT_INLINED = ("01-sources/", "02-facts/", "04-competitors/", "07-final-report/", "tools/outputs/git-cache/")
TEXT_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml"}


def task_material(root: Path, task: dict[str, Any]) -> tuple[str, list[str]]:
    """The text of the files a task reads, each under a header, and the paths left out
    (stores, files the task edits, files over the size limits)."""
    from research_control.io import resolve_pattern

    outputs = {str(path.relative_to(root)) for pattern in task["outputs"] for path in resolve_pattern(root, pattern)}
    outputs |= {pattern for pattern in task["outputs"] if not any(mark in pattern for mark in "*{?")}
    parts: list[str] = []
    left: list[str] = []
    total = 0
    for item in task["inputs"]:
        pattern = str(item.get("path", "")) if isinstance(item, dict) else ""
        if not pattern:
            continue
        if pattern.startswith(NOT_INLINED):
            left.append(pattern)
            continue
        paths = sorted(resolve_pattern(root, pattern)) if any(mark in pattern for mark in "*{?") else [root / pattern]
        for path in paths:
            relative = str(path.relative_to(root))
            if not path.is_file() or relative in outputs or path.suffix.casefold() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace").rstrip()
            if len(text) > MATERIAL_FILE_LIMIT or total + len(text) > MATERIAL_LIMIT:
                left.append(relative)
                continue
            total += len(text)
            parts.append(f"=== FILE: {relative} ===\n{text}\n")
    return "\n".join(parts), left


def worker_brief(root: Path, task: dict[str, Any], route: dict[str, Any], packet: Path) -> str:
    """The whole instruction a host gives a worker for this task, so the orchestrator
    only points the worker at it: lifecycle, run notes, the check, completion; the
    task's instructions and the files it reads are appended after it."""
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
        "2. Everything you need is in this file: the task's instructions follow these steps, then the files the "
        "task reads, each under `=== FILE: path ===`. Read this file whole, in as few reads as you can (Read with "
        "allow_large, or a few large ranges), and follow the instructions exactly. Open another file only to edit "
        "an output, or where the instructions say to (a full fact row or a capture), never a whole store.",
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
        "Write the report in plain English: no jargon or internal shorthand; say what things are, and name a "
        "repository by its GitHub name (owner/repository).",
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
        "instruction": "Start one worker per entry in `agents`, passing its brief: separate workers for work that "
                       "reads different material, one worker for tasks that read the same files.",
        "phase": phase,
        "ready_count": len(packets),
        "packets": packets,
        "agents": agent_groups(root, tasks, packets),
        "created_at": utc_now(),
    }
    path = root / "tools/outputs/dispatch-manifest.json"
    atomic_write_json(path, manifest)
    return {**manifest, "manifest": str(path.relative_to(root))}


# Reviews whose value is independent judgment get a worker each even though they
# read the same synthesis; the two citation checks are deliberate double checks.
KEEP_SEPARATE = {"technical_review", "devils_advocate", "insider_review", "editor_review", "citation_claim_review"}
# Reference files every task of a phase may consult; sharing them is not overlap.
SHARED_REFERENCES = {"00-scope.md", "01-sources/MANIFEST.csv", "WORKFLOW.yaml", "tools/lists/triage-index.jsonl"}


def _reads(task: dict[str, Any]) -> set[str]:
    """The files a task exists to read: concrete input paths, not globs or shared references."""
    paths = {str(item.get("path", "")) for item in task["inputs"] if isinstance(item, dict)}
    return {path for path in paths if path and not any(mark in path for mark in "*{?") and path not in SHARED_REFERENCES}


def agent_groups(root: Path, tasks: list[dict[str, Any]], packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per worker to start. Ready tasks of the same type and model level that read
    the same files go to one worker, which reads them once; everything else gets its own
    worker, so work that reads different material runs in parallel."""
    by_id = {packet["task_id"]: packet for packet in packets}
    parent = {task["task_id"]: task["task_id"] for task in tasks}

    def find(task_id: str) -> str:
        while parent[task_id] != task_id:
            parent[task_id] = parent[parent[task_id]]
            task_id = parent[task_id]
        return task_id

    readers: dict[tuple[str, str, str], str] = {}
    for task in tasks:
        if task["task_type"] in KEEP_SEPARATE:
            continue
        tier = str(by_id[task["task_id"]]["model_route"]["tier"])
        for path in _reads(task):
            key = (task["task_type"], tier, path)
            if key in readers:
                parent[find(task["task_id"])] = find(readers[key])
            else:
                readers[key] = task["task_id"]
    groups: dict[str, list[str]] = {}
    for task in tasks:
        groups.setdefault(find(task["task_id"]), []).append(task["task_id"])
    agents: list[dict[str, Any]] = []
    for members in groups.values():
        if len(members) == 1:
            packet = by_id[members[0]]
            agents.append({"tasks": members, "brief": packet["brief"], "model_route": packet["model_route"]})
            continue
        identifier = sha256("\n".join(sorted(members)).encode("utf-8")).hexdigest()[:12]
        path = root / PACKET_DIRECTORY / f"group-{identifier}.brief.md"
        atomic_write_text(path, "\n".join([
            f"One worker does these {len(members)} tasks, one after another, because they read the same files: "
            "read each shared file once and keep it in mind for the next task.",
            "",
            *(f"- `{task_id}`: follow `{by_id[task_id]['brief']}`" for task_id in members),
            "",
            "Each task keeps its own claim, start, check, and completion; report once, in plain English, "
            "covering every task.",
        ]) + "\n")
        agents.append({"tasks": members, "brief": str(path.relative_to(root)), "model_route": by_id[members[0]]["model_route"]})
    return agents