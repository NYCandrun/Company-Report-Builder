"""Dynamic task-graph construction from the actual research corpus."""

from __future__ import annotations

import csv
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from research_control.discovery import DISCOVERY_CHANNELS, DiscoveryEngine
from research_control.io import atomic_write_text, load_json, workflow
from research_control.orchestration import TASK_SCHEMAS, current_phase, load_state
from research_control.runtime import DISCOVERY_TERMINAL, RuntimeStore, WorkItem


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _batch_id(items: list[dict[str, Any]]) -> str:
    signature = "|".join(
        f"{item['source_id']}:{item.get('token_start', 0)}:{item.get('token_end', '')}" for item in items
    )
    return sha256(signature.encode("utf-8")).hexdigest()[:12]


class AdaptivePlanner:
    """Reconcile desired work with durable scheduler state.

    Planning is deliberately repeatable.  New source-dependent work appears
    when discovery/capture produces new facts about the corpus; already leased
    or completed definitions never change.
    """

    def __init__(self, root: Path, store: RuntimeStore) -> None:
        self.root = root.resolve()
        self.store = store
        self.document = workflow(self.root / "WORKFLOW.yaml")
        batching = self.document.get("adaptive_runtime", {}).get("batching", {})
        self.target_extraction_tokens = int(batching.get("target_extraction_tokens", 70_000))
        self.max_extraction_tokens = int(batching.get("maximum_extraction_tokens", 90_000))

    def reconcile(self) -> dict[str, Any]:
        phase = current_phase(self.root, load_state(self.root))
        created: list[str] = []
        if phase is None:
            return {"phase": None, "created": [], "status": "released"}
        if phase == "capture":
            created.extend(self._plan_capture())
        elif phase == "facts":
            created.extend(self._plan_facts())
        elif phase not in {"bootstrap", "release_acceptance"}:
            created.extend(self._plan_static(phase))
        self.store.refresh_ready()
        tasks = self.store.tasks(phase=phase)
        return {
            "phase": phase,
            "created": created,
            "task_count": len(tasks),
            "states": _counts(tasks, "state"),
            "status": "planned",
        }

    def _phase(self, phase_id: str) -> dict[str, Any]:
        for phase in self.document["phases"]:
            if phase["id"] == phase_id:
                return phase
        raise KeyError(f"unknown phase: {phase_id}")

    def _add(self, item: WorkItem, created: list[str]) -> None:
        if self.store.add_task(item):
            created.append(item.task_id)

    def _plan_static(self, phase_id: str) -> list[str]:
        created: list[str] = []
        phase = self._phase(phase_id)
        profile = self.document.get("execution_profiles", {}).get(phase_id, {})
        tasks = profile.get("tasks", [])
        # Definitions are topologically ordered in WORKFLOW.yaml.
        for definition in tasks:
            task_id = f"{phase_id}.{definition['id']}"
            dependencies = [f"{phase_id}.{value}" for value in definition.get("depends_on", [])]
            self._add(
                WorkItem(
                    task_id=task_id,
                    phase=phase_id,
                    task_type=definition["task_type"],
                    inputs=list(phase.get("inputs", [])),
                    outputs=list(definition["outputs"]),
                    prompt_files=[*definition.get("cores", []), definition["prompt"]],
                    depends_on=dependencies,
                    schema_files=TASK_SCHEMAS.get(definition["task_type"], []),
                    validators=[value["id"] for value in phase.get("validators", [])],
                    independent=bool(definition.get("independent")),
                    exclusive_inputs=bool(definition.get("exclusive_inputs", True)),
                    output_mode=definition.get("output_mode", "create"),
                    track_input_staleness=bool(definition.get("track_input_staleness")),
                    metadata={"planner": "static-profile"},
                ),
                created,
            )
        return created

    def _plan_capture(self) -> list[str]:
        created: list[str] = []
        engine = DiscoveryEngine(self.root, self.store)
        engine.initialize()
        discovery_ids: list[str] = []
        for channel in DISCOVERY_CHANNELS:
            task_id = f"capture.discover.{_slug(channel)}"
            discovery_ids.append(task_id)
            output = f"tools/outputs/worker-parts/discovery/{_slug(channel)}.json"
            self._add(
                WorkItem(
                    task_id=task_id,
                    phase="capture",
                    task_type="source_discovery",
                    inputs=[
                        {"id": "company_url", "value": load_state(self.root)["company_url"]},
                        {"id": "channel", "value": channel},
                    ],
                    outputs=[output],
                    prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/discovery.md"],
                    schema_files=["research_control/schemas/discovery-pass.schema.json"],
                    host_key="" if channel != "company_site" else load_state(self.root)["company_host"],
                    priority=10 if channel in {"company_site", "sitemaps"} else 20,
                    independent=True,
                    exclusive_inputs=False,
                    max_attempts=8,
                    metadata={"channel": channel, "receipt": output},
                ),
                created,
            )

        channels = self.store.discovery_channels()
        by_channel = {item["channel"]: item for item in channels}
        for task_id in discovery_ids:
            task = self.store.task(task_id)
            if not task or task["state"] != "succeeded":
                continue
            receipt_path = self.root / task["metadata"]["receipt"]
            receipt = load_json(receipt_path) if receipt_path.is_file() else {}
            current = by_channel.get(task["metadata"]["channel"], {})
            if receipt.get("status") != current.get("state") or receipt.get("evidence") != current.get("completion_evidence"):
                self.store.mark_stale(task_id, "discovery channel changed after the worker receipt")
        discovery_tasks = [self.store.task(task_id) for task_id in discovery_ids]
        discovery_done = bool(channels) and all(item["state"] in DISCOVERY_TERMINAL for item in channels)
        workers_done = all(task and task["state"] == "succeeded" for task in discovery_tasks)
        barrier_id = "capture.reduce-discovery"
        if discovery_done and workers_done:
            self._add(
                WorkItem(
                    task_id=barrier_id,
                    phase="capture",
                    task_type="discovery_reducer",
                    inputs=[
                        {"id": "source_catalog", "path": "tools/outputs/discovery/sources.jsonl"},
                        {"id": "channel_status", "path": "tools/outputs/discovery/status.json"},
                        {"id": "worker_parts", "path": "tools/outputs/worker-parts/discovery/*.json"},
                    ],
                    outputs=["tools/outputs/discovery/final.json", "06-checks/discovery-coverage.md"],
                    prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/discovery-reducer.md"],
                    depends_on=discovery_ids,
                    schema_files=["research_control/schemas/discovery-pass.schema.json"],
                    validators=["discovery_saturation"],
                    exclusive_inputs=True,
                    priority=30,
                    metadata={"completion_rule": "channel_saturation_not_source_count"},
                ),
                created,
            )

        barrier = self.store.task(barrier_id)
        capture_ids: list[str] = []
        if barrier and barrier["state"] == "succeeded":
            for source in self.store.sources():
                if source["relevance"] in {"excluded", "duplicate"}:
                    continue
                if source["status"] == "blocked":
                    continue
                task_id = f"capture.source.{source['source_id'].casefold()}"
                capture_ids.append(task_id)
                directory = f"01-sources/captures/{source['source_id']}"
                receipt = f"tools/outputs/worker-parts/capture/{source['source_id']}.json"
                self._add(
                    WorkItem(
                        task_id=task_id,
                        phase="capture",
                        task_type="capture",
                        inputs=[{
                            "id": source["source_id"],
                            "source_id": source["source_id"],
                            "url": source["canonical_url"],
                            "channel": source["channel"],
                            "source_kind": source["source_kind"],
                        }],
                        outputs=[directory, receipt],
                        prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/capture-source.md"],
                        depends_on=[barrier_id],
                        schema_files=["research_control/schemas/source.schema.json", "research_control/schemas/disposition.schema.json"],
                        validators=["capture_receipt", "canonical_content"],
                        host_key=source["host_key"],
                        priority=40,
                        independent=True,
                        metadata={"source_id": source["source_id"], "receipt": receipt},
                    ),
                    created,
                )

        capture_tasks = [self.store.task(task_id) for task_id in capture_ids]
        if capture_ids and all(task and task["state"] == "succeeded" for task in capture_tasks):
            self._add(
                WorkItem(
                    task_id="capture.reduce-captures",
                    phase="capture",
                    task_type="capture_reducer",
                    inputs=[
                        {"id": "capture_parts", "path": "tools/outputs/worker-parts/capture/*.json"},
                        {"id": "source_catalog", "path": "tools/outputs/discovery/sources.jsonl"},
                    ],
                    outputs=[
                        "01-sources/MANIFEST.csv", "01-sources/publish-dates.csv", "01-sources/BLOCKED.md",
                        "06-checks/coverage.md", "tools/lists/extraction-scope.csv",
                        "tools/outputs/capture-dispositions.jsonl",
                    ],
                    prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/capture-reducer.md"],
                    depends_on=capture_ids,
                    schema_files=["research_control/schemas/source.schema.json", "research_control/schemas/disposition.schema.json"],
                    validators=["source_records", "source_dates", "manifest_files", "capture_workers"],
                    priority=50,
                    exclusive_inputs=True,
                    metadata={"single_writer": True},
                ),
                created,
            )
        return created

    def _plan_facts(self) -> list[str]:
        created: list[str] = []
        slices = self._source_slices()
        batches = self._pack_slices(slices)
        extraction_ids: list[str] = []
        for batch in batches:
            identifier = _batch_id(batch)
            task_id = f"facts.extract.{identifier}"
            extraction_ids.append(task_id)
            candidate_part = f"tools/outputs/worker-parts/extraction/{identifier}.candidates.jsonl"
            disposition_part = f"tools/outputs/worker-parts/extraction/{identifier}.dispositions.jsonl"
            self._add(
                WorkItem(
                    task_id=task_id,
                    phase="facts",
                    task_type="extraction",
                    inputs=batch,
                    outputs=[candidate_part, disposition_part],
                    prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/extraction.md"],
                    schema_files=["research_control/schemas/disposition.schema.json"],
                    validators=["extraction_part"],
                    priority=10,
                    independent=True,
                    metadata={
                        "estimated_tokens": sum(int(item["estimated_tokens"]) for item in batch),
                        "candidate_id_prefix": f"CAND-{identifier.upper()}-",
                        "candidate_part": candidate_part,
                        "disposition_part": disposition_part,
                    },
                ),
                created,
            )
        extraction_tasks = [self.store.task(task_id) for task_id in extraction_ids]
        reducer_id = "facts.reduce-extraction"
        if extraction_ids and all(task and task["state"] == "succeeded" for task in extraction_tasks):
            self._add(
                WorkItem(
                    task_id=reducer_id,
                    phase="facts",
                    task_type="extraction_reducer",
                    inputs=[
                        {"id": "candidate_parts", "path": "tools/outputs/worker-parts/extraction/*.candidates.jsonl"},
                        {"id": "disposition_parts", "path": "tools/outputs/worker-parts/extraction/*.dispositions.jsonl"},
                    ],
                    outputs=["tools/candidates/all.jsonl", "tools/outputs/extraction-dispositions.jsonl"],
                    prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/extraction-reducer.md"],
                    depends_on=extraction_ids,
                    schema_files=["research_control/schemas/disposition.schema.json"],
                    validators=["source_extraction"],
                    priority=20,
                    exclusive_inputs=True,
                    metadata={"single_writer": True},
                ),
                created,
            )
        reducer = self.store.task(reducer_id)
        if reducer and reducer["state"] == "succeeded":
            phase = self._phase("facts")
            definition = next(
                item for item in self.document["execution_profiles"]["facts"]["tasks"] if item["id"] == "file-facts"
            )
            self._add(
                WorkItem(
                    task_id="facts.file-facts",
                    phase="facts",
                    task_type="filing",
                    inputs=list(phase.get("inputs", [])),
                    outputs=list(definition["outputs"]),
                    prompt_files=[*definition.get("cores", []), definition["prompt"]],
                    depends_on=[reducer_id],
                    schema_files=TASK_SCHEMAS.get("filing", []),
                    validators=[value["id"] for value in phase.get("validators", [])],
                    exclusive_inputs=False,
                    priority=30,
                    metadata={"single_writer": True},
                ),
                created,
            )
        return created

    def _source_slices(self) -> list[dict[str, Any]]:
        sources = {source["source_id"]: source for source in self.store.sources()}
        manifest = self.root / "01-sources/MANIFEST.csv"
        if not manifest.is_file():
            raise FileNotFoundError("facts planning requires 01-sources/MANIFEST.csv")
        rows: list[dict[str, str]]
        with manifest.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        slices: list[dict[str, Any]] = []
        for row in rows:
            source_id = row.get("id", "").strip()
            paths = [value.strip() for value in row.get("local file", "").split(";") if value.strip()]
            text_paths = [
                value for value in paths
                if (self.root / value).suffix.casefold() in {".txt", ".md", ".json", ".jsonl", ".csv", ".xml"}
                and (self.root / value).is_file()
            ]
            if not text_paths:
                raise ValueError(f"{source_id}: no canonical text derivative is available")
            sections = []
            for value in text_paths:
                content = (self.root / value).read_text(encoding="utf-8", errors="replace")
                sections.append(f"--- SOURCE FILE: {value} ---\n{content.rstrip()}\n")
            content = "\n".join(sections)
            canonical = self.root / "tools/extracts/canonical" / f"{source_id}.txt"
            atomic_write_text(canonical, content)
            canonical_relative = str(canonical.relative_to(self.root))
            estimated = max(1, len(content) // 4)
            source = sources.get(source_id, {})
            if source and int(source.get("content_tokens") or 0) != estimated:
                self.store.update_source(source_id, content_tokens=estimated)
            if estimated <= self.max_extraction_tokens:
                slices.append({
                    "id": source_id, "source_id": source_id, "path": canonical_relative,
                    "source_paths": paths,
                    "estimated_tokens": estimated, "token_start": 0, "token_end": estimated,
                })
                continue
            char_start = 0
            part = 1
            target_characters = self.target_extraction_tokens * 4
            while char_start < len(content):
                char_end = min(char_start + target_characters, len(content))
                if char_end < len(content):
                    boundary = content.rfind("\n\n", char_start, char_end)
                    if boundary > char_start + target_characters // 2:
                        char_end = boundary + 2
                slice_path = self.root / "tools/extracts/slices" / f"{source_id}.part-{part:04d}.txt"
                atomic_write_text(slice_path, content[char_start:char_end])
                start = char_start // 4
                end = max(start + 1, char_end // 4)
                slices.append({
                    "id": f"{source_id}:part-{part:04d}", "source_id": source_id,
                    "path": str(slice_path.relative_to(self.root)), "source_paths": paths,
                    "estimated_tokens": end - start, "token_start": start, "token_end": end,
                })
                char_start = char_end
                part += 1
        return slices

    def _pack_slices(self, slices: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        batches: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        tokens = 0
        for item in slices:
            size = int(item["estimated_tokens"])
            if current and tokens + size > self.max_extraction_tokens:
                batches.append(current)
                current = []
                tokens = 0
            current.append(item)
            tokens += size
            if tokens >= self.target_extraction_tokens:
                batches.append(current)
                current = []
                tokens = 0
        if current:
            batches.append(current)
        return batches


def _counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in records:
        value = str(record[key])
        result[value] = result.get(value, 0) + 1
    return result
