"""Dynamic task-graph construction from the actual research corpus."""

from __future__ import annotations

import csv
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from research_control.discovery import DISCOVERY_CHANNELS, DiscoveryEngine
from research_control.io import atomic_write_jsonl, atomic_write_text, load_json, workflow
from research_control.triage import TRIAGE_DECISIONS, TRIAGE_EXCERPT_CHARACTERS, TRIAGE_INDEX, triage_included
from research_control.orchestration import TASK_SCHEMAS, current_phase, load_state
from research_control.runtime import ACTIVE_STATES, DISCOVERY_TERMINAL, FINAL_STATES, SATISFIED_STATES, UNCAPTURED_RELEVANCE, RuntimeStore, WorkItem


COMPLETION_RULE = "first-party fixed point plus question sufficiency or saturation; never a source count"
# One discovery task per channel. The runtime itself crawls the company site and
# audits its sitemaps; the other eight channels each get their own agent worker.
RUNTIME_DISCOVERY_CHANNELS = {"company_site", "sitemaps"}
# Channels that complete first-party coverage start after the runtime crawl, so
# their workers search for what the crawl could not reach rather than repeat it.
FIRST_PARTY_FOLLOW_UP = {"newsroom_blog", "docs_help", "careers", "code_packages"}


def discovery_task_id(channel: str) -> str:
    return f"capture.discover.{channel.replace('_', '-')}"


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
        # Definitions are topologically ordered in WORKFLOW.yaml.
        for definition in self.document.get("execution_profiles", {}).get(phase_id, {}).get("tasks", []):
            self._add(self._plan_profile_task(phase_id, definition["id"]), created)
        return created

    def _plan_profile_task(self, phase_id: str, task_key: str, *, metadata: dict[str, Any] | None = None) -> WorkItem:
        phase = self._phase(phase_id)
        definition = next(
            item for item in self.document["execution_profiles"][phase_id]["tasks"] if item["id"] == task_key
        )
        return WorkItem(
            task_id=f"{phase_id}.{task_key}",
            phase=phase_id,
            task_type=definition["task_type"],
            inputs=list(definition.get("inputs", phase.get("inputs", []))),
            outputs=list(definition["outputs"]),
            prompt_files=[*definition.get("cores", []), definition["prompt"]],
            depends_on=[f"{phase_id}.{value}" for value in definition.get("depends_on", [])],
            schema_files=TASK_SCHEMAS.get(definition["task_type"], []),
            validators=list(definition.get(
                "validators", [value["id"] for value in phase.get("validators", [])]
            )),
            host_key=str(definition.get("host_key", "")),
            priority=int(definition.get("priority", 100)),
            independent=bool(definition.get("independent")),
            exclusive_inputs=bool(definition.get("exclusive_inputs", True)),
            output_mode=definition.get("output_mode", "create"),
            track_input_staleness=bool(definition.get("track_input_staleness")),
            metadata=dict(metadata if metadata is not None else definition.get("metadata", {"planner": "static-profile"})),
        )

    def _legacy_discovery_cover(self, channel: str, current: dict[str, Any]) -> str | None:
        """Return a finished grouped discovery task whose receipt still matches ``channel``."""
        for task in self.store.tasks(phase="capture"):
            channels = task["metadata"].get("channels") or []
            if task["task_type"] != "source_discovery" or len(channels) < 2 or channel not in channels:
                continue
            if task["state"] not in {"succeeded", "superseded", "stale", "ready"}:
                continue
            receipt_path = self.root / task["metadata"]["receipts"][channels.index(channel)]
            receipt = load_json(receipt_path) if receipt_path.is_file() else {}
            if receipt.get("status") == current.get("state") and receipt.get("evidence") == current.get("completion_evidence"):
                return task["task_id"]
        return None

    def _supersede_split_groups(self) -> None:
        """Retire a grouped discovery task once any of its channels has its own task.

        Its other channels stay covered by its matching receipts; it is never
        redispatched as a group.
        """
        for task in self.store.tasks(phase="capture"):
            channels = task["metadata"].get("channels") or []
            if task["task_type"] != "source_discovery" or len(channels) < 2:
                continue
            if task["state"] in {"superseded", "leased", "running", "validating"}:
                continue
            split = [channel for channel in channels if self.store.task(discovery_task_id(channel))]
            if split:
                self.store.supersede(
                    task["task_id"], f"discovery split per channel; {', '.join(split)} now have their own tasks"
                )

    def _plan_capture(self) -> list[str]:
        created: list[str] = []
        state = load_state(self.root)
        # The brand guide belongs to the final phase but starts now, so it runs
        # alongside research instead of holding any research gate.
        self._add(self._plan_profile_task("final", "brand-guide"), created)
        engine = DiscoveryEngine(self.root, self.store)
        engine.initialize()
        channels = self.store.discovery_channels()
        by_channel = {item["channel"]: item for item in channels}
        discovery_ids: list[str] = []
        for channel in DISCOVERY_CHANNELS:
            task_id = discovery_task_id(channel)
            legacy_id = self._legacy_discovery_cover(channel, by_channel.get(channel, {}))
            if legacy_id and not self.store.task(task_id):
                # A run started before discovery was split per channel keeps the
                # grouped task's finished work until that channel changes.
                discovery_ids.append(legacy_id)
                continue
            discovery_ids.append(task_id)
            receipt = f"tools/outputs/worker-parts/discovery/{_slug(channel)}.json"
            automatic = channel in RUNTIME_DISCOVERY_CHANNELS
            # company_site is planned first, so discovery_ids[0] is whichever task covers it.
            follows_crawl = channel == "sitemaps" or channel in FIRST_PARTY_FOLLOW_UP
            depends_on = [discovery_ids[0]] if follows_crawl else []
            self._add(
                WorkItem(
                    task_id=task_id,
                    phase="capture",
                    task_type="source_discovery",
                    inputs=[
                        {"id": "company_url", "value": state["company_url"]},
                        {"id": "channels", "value": [channel]},
                        {"id": "scope_map", "path": "00-scope.md"},
                    ],
                    outputs=[receipt],
                    prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/discovery.md"],
                    depends_on=depends_on,
                    schema_files=["research_control/schemas/discovery-pass.schema.json"],
                    host_key=state["company_host"] if automatic else "",
                    priority=10 if automatic else 20,
                    independent=not automatic,
                    exclusive_inputs=False,
                    max_attempts=8,
                    metadata={
                        "channels": [channel],
                        "receipts": [receipt],
                        "executor": "runtime" if automatic else "agent",
                    },
                ),
                created,
            )

        self._supersede_split_groups()
        for task_id in discovery_ids:
            task = self.store.task(task_id)
            if not task or task["state"] != "succeeded" or len(task["metadata"]["channels"]) != 1:
                continue
            channel, receipt_relative = task["metadata"]["channels"][0], task["metadata"]["receipts"][0]
            receipt_path = self.root / receipt_relative
            receipt = load_json(receipt_path) if receipt_path.is_file() else {}
            current = by_channel.get(channel, {})
            if receipt.get("status") != current.get("state") or receipt.get("evidence") != current.get("completion_evidence"):
                self.store.mark_stale(task_id, f"discovery channel {channel} changed after the worker receipt")
        discovery_tasks = [self.store.task(task_id) for task_id in discovery_ids]
        discovery_done = bool(channels) and all(item["state"] in DISCOVERY_TERMINAL for item in channels)
        workers_done = all(task and task["state"] in SATISFIED_STATES for task in discovery_tasks)
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
                    validators=["discovery_completion"],
                    exclusive_inputs=True,
                    priority=30,
                    metadata={"completion_rule": COMPLETION_RULE, "executor": "runtime"},
                ),
                created,
            )

        barrier = self.store.task(barrier_id)
        if barrier and barrier["state"] == "succeeded" and any(
            task and task["state"] not in SATISFIED_STATES
            or (task and str(task.get("finished_at") or "") > str(barrier.get("finished_at") or ""))
            for task in discovery_tasks
        ):
            # Discovery reopened after the snapshot: refresh the snapshot. Captures
            # already done stay valid; new sources wait for the refreshed barrier.
            self.store.mark_stale(barrier_id, "discovery changed after the discovery snapshot")
            barrier = self.store.task(barrier_id)
        if barrier and barrier["state"] not in ACTIVE_STATES | FINAL_STATES:
            # A channel task created after the snapshot (a split or reopened channel)
            # must finish before the snapshot is refreshed.
            for task_id in discovery_ids:
                if task_id not in barrier["depends_on"]:
                    self.store.add_dependency(barrier_id, task_id)
            barrier = self.store.task(barrier_id)
        capture_ids: list[str] = []
        if barrier and barrier["state"] == "succeeded":
            for source in self.store.sources():
                if source["relevance"] in UNCAPTURED_RELEVANCE:
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
                        independent=False,
                        metadata={"source_id": source["source_id"], "receipt": receipt, "executor": "runtime"},
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
                    metadata={"single_writer": True, "executor": "runtime"},
                ),
                created,
            )
        return created

    def _plan_facts(self) -> list[str]:
        created: list[str] = []
        triage_id = "facts.triage"
        self._write_triage_index()
        self._add(
            WorkItem(
                task_id=triage_id,
                phase="facts",
                task_type="triage",
                inputs=[
                    {"id": "scope_map", "path": "00-scope.md", "required": True},
                    {"id": "triage_index", "path": TRIAGE_INDEX, "required": True},
                    {"id": "source_manifest", "path": "01-sources/MANIFEST.csv", "required": True},
                ],
                outputs=[TRIAGE_DECISIONS],
                prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/triage.md"],
                schema_files=["research_control/schemas/disposition.schema.json"],
                validators=["extraction_triage"],
                priority=5,
                independent=True,
                exclusive_inputs=True,
                metadata={"selection_rule": "include a source only for the numbered research questions it can answer"},
            ),
            created,
        )
        triage = self.store.task(triage_id)
        if not triage or triage["state"] != "succeeded":
            return created
        slices = self._source_slices(included=triage_included(self.root))
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
                    depends_on=[triage_id],
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
                        {"id": "triage_decisions", "path": TRIAGE_DECISIONS},
                    ],
                    outputs=["tools/candidates/all.jsonl", "tools/outputs/extraction-dispositions.jsonl"],
                    prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/extraction-reducer.md"],
                    depends_on=extraction_ids,
                    schema_files=["research_control/schemas/disposition.schema.json"],
                    validators=["source_extraction"],
                    priority=20,
                    exclusive_inputs=True,
                    metadata={"single_writer": True, "executor": "runtime"},
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

    def _write_triage_index(self) -> None:
        """Write a compact, deterministic index the triage worker reads instead of full sources."""
        manifest = self.root / "01-sources/MANIFEST.csv"
        if not manifest.is_file():
            raise FileNotFoundError("facts planning requires 01-sources/MANIFEST.csv")
        sources = {source["source_id"]: source for source in self.store.sources()}
        with manifest.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        index: list[dict[str, Any]] = []
        for row in rows:
            source_id = row.get("id", "").strip()
            paths = [value.strip() for value in row.get("local file", "").split(";") if value.strip()]
            text_paths = [value for value in paths if value.endswith("content.txt") and (self.root / value).is_file()]
            content = (self.root / text_paths[0]).read_text(encoding="utf-8", errors="replace") if text_paths else ""
            excerpt = re.sub(r"\s+", " ", content)[:TRIAGE_EXCERPT_CHARACTERS].strip()
            index.append({
                "id": source_id,
                "url": row.get("url", ""),
                "title": row.get("title", ""),
                "channel": sources.get(source_id, {}).get("channel", ""),
                "grade": row.get("grade", ""),
                "date_published": row.get("date published", ""),
                "estimated_tokens": max(1, len(content) // 4),
                "excerpt": excerpt,
            })
        atomic_write_jsonl(self.root / TRIAGE_INDEX, index)

    def _source_slices(self, included: set[str] | None = None) -> list[dict[str, Any]]:
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
            if included is not None and source_id not in included:
                continue
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
