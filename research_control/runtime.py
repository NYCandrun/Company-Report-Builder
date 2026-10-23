"""Durable adaptive work queue for research runs.

The SQLite database is the scheduler's private source of truth.  Workers never
write it directly: they claim work and report outcomes through this module (or
the CLI commands that wrap it).  Human-readable JSONL is emitted as an audit
log and remains compatible with the existing phase gates.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from research_control import PASS
from research_control.hashing import hash_path, hash_patterns
from research_control.io import append_jsonl, resolve_pattern, utc_now


DATABASE_PATH = "tools/outputs/runtime.sqlite3"
EVENT_LOG_PATH = "tools/outputs/runtime-events.jsonl"
DEFAULT_GLOBAL_CONCURRENCY = 12
DEFAULT_HOST_CONCURRENCY = 2
DEFAULT_LEASE_SECONDS = 1_800
DEFAULT_MAX_ATTEMPTS = 3

TASK_STATES = {
    "planned",
    "ready",
    "leased",
    "running",
    "validating",
    "succeeded",
    "retryable",
    "failed",
    "blocked",
    "stale",
    "cancelled",
}
ACTIVE_STATES = {"leased", "running", "validating"}
SUCCESS_STATES = {"succeeded"}
FINAL_STATES = {"succeeded", "failed", "blocked", "cancelled"}
DISCOVERY_TERMINAL = {"saturated", "not_applicable", "blocked", "incomplete"}
DISCOVERY_COMPLETE = {"saturated", "not_applicable"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _parse(value: str | None, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    return json.loads(value)


def _iso_after(seconds: int) -> str:
    value = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_source_id(url: str) -> str:
    return f"SRC-{sha256(url.encode('utf-8')).hexdigest()[:12].upper()}"


@dataclass(frozen=True)
class WorkItem:
    """Immutable worker contract stored by the scheduler."""

    task_id: str
    phase: str
    task_type: str
    inputs: list[dict[str, Any]]
    outputs: list[str]
    prompt_files: list[str]
    depends_on: list[str] = field(default_factory=list)
    schema_files: list[str] = field(default_factory=list)
    validators: list[str] = field(default_factory=list)
    host_key: str = ""
    priority: int = 100
    independent: bool = False
    exclusive_inputs: bool = True
    output_mode: str = "create"
    track_input_staleness: bool = False
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.task_id or not self.phase or not self.task_type:
            raise ValueError("work item requires task_id, phase, and task_type")
        if not self.outputs:
            raise ValueError(f"{self.task_id}: at least one exact output is required")
        if not self.prompt_files:
            raise ValueError(f"{self.task_id}: at least one prompt file is required")
        if self.max_attempts < 1:
            raise ValueError(f"{self.task_id}: max_attempts must be positive")
        if self.task_id in self.depends_on:
            raise ValueError(f"{self.task_id}: task cannot depend on itself")


class RuntimeStore:
    """Single-writer scheduler state with transactional task leasing."""

    def __init__(self, root: Path, database: str = DATABASE_PATH) -> None:
        self.root = root.resolve()
        self.path = self.root / database
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = FULL")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self._create_schema()

    def __enter__(self) -> "RuntimeStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                phase TEXT NOT NULL,
                task_type TEXT NOT NULL,
                state TEXT NOT NULL,
                priority INTEGER NOT NULL,
                host_key TEXT NOT NULL,
                independent INTEGER NOT NULL,
                exclusive_inputs INTEGER NOT NULL,
                output_mode TEXT NOT NULL,
                track_input_staleness INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                lease_owner TEXT,
                lease_expires_at TEXT,
                heartbeat_at TEXT,
                inputs_json TEXT NOT NULL,
                outputs_json TEXT NOT NULL,
                prompts_json TEXT NOT NULL,
                schemas_json TEXT NOT NULL,
                validators_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                input_hashes_json TEXT NOT NULL DEFAULT '{}',
                output_hashes_json TEXT NOT NULL DEFAULT '{}',
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS dependencies (
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                depends_on TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
                PRIMARY KEY (task_id, depends_on)
            );
            CREATE TABLE IF NOT EXISTS attempts (
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                attempt INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                state TEXT NOT NULL,
                started_at TEXT NOT NULL,
                heartbeat_at TEXT,
                finished_at TEXT,
                failure_reason TEXT,
                telemetry_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (task_id, attempt)
            );
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                canonical_url TEXT NOT NULL UNIQUE,
                original_url TEXT NOT NULL,
                host_key TEXT NOT NULL,
                channel TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                relevance TEXT NOT NULL,
                discovered_from TEXT,
                depth INTEGER NOT NULL DEFAULT 0,
                local_paths_json TEXT NOT NULL DEFAULT '[]',
                content_bytes INTEGER,
                content_tokens INTEGER,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovery_channels (
                channel TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                consecutive_empty_passes INTEGER NOT NULL DEFAULT 0,
                total_passes INTEGER NOT NULL DEFAULT 0,
                total_new_sources INTEGER NOT NULL DEFAULT 0,
                completion_evidence TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shared_urls (
                url TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                final_url TEXT,
                content_type TEXT,
                status_code INTEGER,
                headers_json TEXT NOT NULL DEFAULT '{}',
                content_sha256 TEXT,
                object_path TEXT,
                content_bytes INTEGER,
                first_seen_at TEXT NOT NULL,
                fetched_at TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shared_url_uses (
                url TEXT NOT NULL REFERENCES shared_urls(url) ON DELETE CASCADE,
                consumer TEXT NOT NULL,
                purpose TEXT NOT NULL,
                discovered_from TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (url, consumer, purpose)
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                subject_id TEXT,
                details_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS tasks_state_priority ON tasks(state, priority, created_at);
            CREATE INDEX IF NOT EXISTS tasks_host_state ON tasks(host_key, state);
            CREATE INDEX IF NOT EXISTS sources_channel_status ON sources(channel, status);
            CREATE INDEX IF NOT EXISTS shared_urls_final_url ON shared_urls(final_url);
            CREATE INDEX IF NOT EXISTS shared_url_uses_purpose ON shared_url_uses(purpose, consumer);
            """
        )
        self.connection.commit()

    def initialize(
        self,
        *,
        run_id: str,
        company_url: str,
        global_concurrency: int = DEFAULT_GLOBAL_CONCURRENCY,
        host_concurrency: int = DEFAULT_HOST_CONCURRENCY,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> None:
        values = {
            "run_id": run_id,
            "company_url": company_url,
            "global_concurrency": str(global_concurrency),
            "host_concurrency": str(host_concurrency),
            "lease_seconds": str(lease_seconds),
            "schema_version": "2.0.0",
        }
        was_initialized = bool(self.metadata())
        with self.connection:
            existing = self.metadata()
            if existing and (
                existing.get("run_id") != run_id or existing.get("company_url") != company_url
            ):
                raise ValueError("adaptive runtime belongs to a different research run")
            for key, value in values.items():
                self.connection.execute(
                    "INSERT INTO metadata(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
        if not was_initialized:
            self.event("runtime_initialized", run_id, values)

    def metadata(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self.connection.execute("SELECT key, value FROM metadata")}

    def event(self, event_type: str, subject_id: str | None, details: dict[str, Any]) -> None:
        now = utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO events(occurred_at, event_type, subject_id, details_json) VALUES (?, ?, ?, ?)",
                (now, event_type, subject_id, _json(details)),
            )
        append_jsonl(
            self.root / EVENT_LOG_PATH,
            {"occurred_at": now, "event_type": event_type, "subject_id": subject_id, "details": details},
        )

    def add_task(self, item: WorkItem) -> bool:
        item.validate()
        now = utc_now()
        payload = asdict(item)
        immutable = {
            key: payload[key]
            for key in (
                "phase", "task_type", "inputs", "outputs", "prompt_files", "schema_files",
                "validators", "host_key", "priority", "independent", "exclusive_inputs",
                "output_mode", "track_input_staleness", "max_attempts", "metadata",
            )
        }
        existing = self.task(item.task_id)
        if existing:
            comparison = {
                "phase": existing["phase"],
                "task_type": existing["task_type"],
                "inputs": existing["inputs"],
                "outputs": existing["outputs"],
                "prompt_files": existing["prompt_files"],
                "schema_files": existing["schema_files"],
                "validators": existing["validators"],
                "host_key": existing["host_key"],
                "priority": existing["priority"],
                "independent": existing["independent"],
                "exclusive_inputs": existing["exclusive_inputs"],
                "output_mode": existing["output_mode"],
                "track_input_staleness": existing["track_input_staleness"],
                "max_attempts": existing["max_attempts"],
                "metadata": existing["metadata"],
            }
            if comparison != immutable:
                raise ValueError(f"{item.task_id}: immutable work-item definition changed")
            for dependency in item.depends_on:
                self.add_dependency(item.task_id, dependency)
            return False
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO tasks(
                    task_id, phase, task_type, state, priority, host_key, independent,
                    exclusive_inputs, output_mode, track_input_staleness, max_attempts,
                    inputs_json, outputs_json, prompts_json, schemas_json, validators_json,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'planned', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.task_id, item.phase, item.task_type, item.priority, item.host_key,
                    int(item.independent), int(item.exclusive_inputs), item.output_mode,
                    int(item.track_input_staleness), item.max_attempts, _json(item.inputs),
                    _json(item.outputs), _json(item.prompt_files), _json(item.schema_files),
                    _json(item.validators), _json(item.metadata), now, now,
                ),
            )
            for dependency in item.depends_on:
                if not self.task(dependency):
                    raise ValueError(f"{item.task_id}: dependency does not exist: {dependency}")
                self.connection.execute(
                    "INSERT OR IGNORE INTO dependencies(task_id, depends_on) VALUES (?, ?)",
                    (item.task_id, dependency),
                )
        self.event("task_planned", item.task_id, {"phase": item.phase, "task_type": item.task_type})
        self.refresh_ready()
        return True

    def add_dependency(self, task_id: str, depends_on: str) -> None:
        task = self.task(task_id)
        if not task or not self.task(depends_on):
            raise KeyError(f"unknown dependency edge: {task_id} -> {depends_on}")
        present = self.connection.execute(
            "SELECT 1 FROM dependencies WHERE task_id=? AND depends_on=?", (task_id, depends_on)
        ).fetchone()
        if present:
            return
        if task["state"] in ACTIVE_STATES | FINAL_STATES:
            raise ValueError(f"{task_id}: cannot add a dependency after execution began")
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO dependencies(task_id, depends_on) VALUES (?, ?)",
                (task_id, depends_on),
            )
            self.connection.execute(
                "UPDATE tasks SET state='planned', updated_at=? WHERE task_id=?",
                (utc_now(), task_id),
            )

    def _task_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result.update(
            {
                "inputs": _parse(result.pop("inputs_json"), []),
                "outputs": _parse(result.pop("outputs_json"), []),
                "prompt_files": _parse(result.pop("prompts_json"), []),
                "schema_files": _parse(result.pop("schemas_json"), []),
                "validators": _parse(result.pop("validators_json"), []),
                "metadata": _parse(result.pop("metadata_json"), {}),
                "input_hashes": _parse(result.pop("input_hashes_json"), {}),
                "output_hashes": _parse(result.pop("output_hashes_json"), {}),
                "independent": bool(result["independent"]),
                "exclusive_inputs": bool(result["exclusive_inputs"]),
                "track_input_staleness": bool(result["track_input_staleness"]),
            }
        )
        result["depends_on"] = [
            value[0]
            for value in self.connection.execute(
                "SELECT depends_on FROM dependencies WHERE task_id=? ORDER BY depends_on", (result["task_id"],)
            )
        ]
        return result

    def task(self, task_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._task_from_row(row) if row else None

    def tasks(self, *, phase: str | None = None, states: Iterable[str] | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if phase:
            clauses.append("phase=?")
            values.append(phase)
        state_values = list(states or [])
        if state_values:
            clauses.append(f"state IN ({','.join('?' for _ in state_values)})")
            values.extend(state_values)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            f"SELECT * FROM tasks{where} ORDER BY priority, created_at, task_id", values
        ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def refresh_ready(self) -> int:
        changed = 0
        now = utc_now()
        with self.connection:
            candidates = self.connection.execute(
                "SELECT task_id, state, attempt_count, max_attempts FROM tasks "
                "WHERE state IN ('planned', 'ready', 'retryable', 'stale')"
            ).fetchall()
            for row in candidates:
                if int(row["attempt_count"]) >= int(row["max_attempts"]):
                    if row["state"] != "blocked":
                        self.connection.execute(
                            "UPDATE tasks SET state='blocked', last_error=?, updated_at=? WHERE task_id=?",
                            ("maximum attempts exhausted", now, row["task_id"]),
                        )
                        changed += 1
                    continue
                unmet = self.connection.execute(
                    """
                    SELECT COUNT(*) FROM dependencies d
                    JOIN tasks parent ON parent.task_id=d.depends_on
                    WHERE d.task_id=? AND parent.state!='succeeded'
                    """,
                    (row["task_id"],),
                ).fetchone()[0]
                desired = "retryable" if row["state"] == "retryable" and not unmet else "ready" if not unmet else "planned"
                if desired != row["state"]:
                    self.connection.execute(
                        "UPDATE tasks SET state=?, updated_at=? WHERE task_id=?",
                        (desired, now, row["task_id"]),
                    )
                    changed += 1
        return changed

    def invalidate_stale(self) -> list[str]:
        """Invalidate changed successes and every completed downstream consumer."""
        stale: set[str] = set()
        successes = self.tasks(states={"succeeded"})
        output_owner: dict[str, tuple[str, tuple[str, int, str, str]]] = {}
        for task in successes:
            rank = (
                str(task.get("finished_at") or ""),
                int(task.get("output_mode") == "revise"),
                str(task.get("created_at") or ""),
                task["task_id"],
            )
            for relative in task["output_hashes"]:
                prior = output_owner.get(relative)
                if prior is None or rank >= prior[1]:
                    output_owner[relative] = (task["task_id"], rank)
        for task in successes:
            owned_outputs = {
                relative: digest for relative, digest in task["output_hashes"].items()
                if output_owner.get(relative, (None, ""))[0] == task["task_id"]
            }
            outputs_current = bool(task["output_hashes"]) and all(
                hash_path(self.root / relative) == digest
                for relative, digest in owned_outputs.items()
            )
            inputs_current = True
            if task["track_input_staleness"]:
                patterns = [str(item["path"]) for item in task["inputs"] if item.get("path")]
                inputs_current = hash_patterns(self.root, patterns) == task["input_hashes"]
            if not outputs_current or not inputs_current:
                stale.add(task["task_id"])
        frontier = list(stale)
        while frontier:
            parent = frontier.pop()
            children = self.connection.execute(
                "SELECT task_id FROM dependencies WHERE depends_on=?", (parent,)
            ).fetchall()
            for row in children:
                child = row["task_id"]
                task = self.task(child)
                if task and task["state"] == "succeeded" and child not in stale:
                    stale.add(child)
                    frontier.append(child)
        if stale:
            now = utc_now()
            with self.connection:
                self.connection.executemany(
                    "UPDATE tasks SET state='stale', finished_at=NULL, updated_at=? WHERE task_id=?",
                    [(now, task_id) for task_id in sorted(stale)],
                )
            for task_id in sorted(stale):
                self.event("task_stale", task_id, {"reason": "input, output, or upstream hash changed"})
        self.refresh_ready()
        return sorted(stale)

    def mark_stale(self, task_id: str, reason: str) -> dict[str, Any]:
        task = self.task(task_id)
        if not task:
            raise KeyError(f"unknown task: {task_id}")
        if task["state"] != "succeeded":
            return task
        with self.connection:
            self.connection.execute(
                "UPDATE tasks SET state='stale', finished_at=NULL, last_error=?, updated_at=? WHERE task_id=?",
                (reason, utc_now(), task_id),
            )
        self.event("task_stale", task_id, {"reason": reason})
        self.refresh_ready()
        return self.task(task_id) or task

    def claim(
        self,
        worker_id: str,
        *,
        task_id: str | None = None,
        capabilities: Iterable[str] | None = None,
        phase: str | None = None,
    ) -> dict[str, Any] | None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        self.recover_expired()
        self.refresh_ready()
        metadata = self.metadata()
        global_limit = int(metadata.get("global_concurrency", DEFAULT_GLOBAL_CONCURRENCY))
        host_limit = int(metadata.get("host_concurrency", DEFAULT_HOST_CONCURRENCY))
        capability_values = sorted(set(capabilities or []))
        clauses = ["state IN ('ready', 'retryable')", "attempt_count < max_attempts"]
        values: list[Any] = []
        if task_id:
            clauses.append("task_id=?")
            values.append(task_id)
        if phase:
            clauses.append("phase=?")
            values.append(phase)
        if capability_values:
            clauses.append(f"task_type IN ({','.join('?' for _ in capability_values)})")
            values.extend(capability_values)
        with self.connection:
            active = self.connection.execute(
                "SELECT COUNT(*) FROM tasks WHERE state IN ('leased','running','validating')"
            ).fetchone()[0]
            if active >= global_limit:
                return None
            rows = self.connection.execute(
                f"SELECT task_id, host_key FROM tasks WHERE {' AND '.join(clauses)} "
                "ORDER BY priority, created_at, task_id",
                values,
            ).fetchall()
            selected: sqlite3.Row | None = None
            for row in rows:
                if row["host_key"]:
                    host_active = self.connection.execute(
                        "SELECT COUNT(*) FROM tasks WHERE host_key=? AND state IN ('leased','running','validating')",
                        (row["host_key"],),
                    ).fetchone()[0]
                    if host_active >= host_limit:
                        continue
                selected = row
                break
            if selected is None:
                return None
            selected_task = self.task(selected["task_id"])
            assert selected_task is not None
            if selected_task["independent"]:
                prior = self.connection.execute(
                    """
                    SELECT COUNT(*) FROM attempts a
                    JOIN tasks t ON t.task_id=a.task_id
                    WHERE a.worker_id=? AND t.phase=? AND t.independent=1 AND t.task_id!=?
                    """,
                    (worker_id, selected_task["phase"], selected_task["task_id"]),
                ).fetchone()[0]
                if prior:
                    raise ValueError(
                        f"{selected_task['task_id']}: independent work requires a worker identity "
                        f"not already used in phase {selected_task['phase']}"
                    )
            now = utc_now()
            lease_seconds = int(metadata.get("lease_seconds", DEFAULT_LEASE_SECONDS))
            result = self.connection.execute(
                """
                UPDATE tasks SET state='leased', lease_owner=?, lease_expires_at=?, heartbeat_at=?,
                    attempt_count=attempt_count+1, updated_at=?
                WHERE task_id=? AND state IN ('ready','retryable')
                """,
                (worker_id, _iso_after(lease_seconds), now, now, selected["task_id"]),
            )
            if result.rowcount != 1:
                return None
            task = self.task(selected["task_id"])
            assert task is not None
            self.connection.execute(
                "INSERT INTO attempts(task_id, attempt, worker_id, state, started_at, heartbeat_at) "
                "VALUES (?, ?, ?, 'leased', ?, ?)",
                (task["task_id"], task["attempt_count"], worker_id, now, now),
            )
        self.event("task_leased", task["task_id"], {"worker_id": worker_id, "attempt": task["attempt_count"]})
        return self.task(task["task_id"])

    def start(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task = self._owned_active(task_id, worker_id, {"leased"})
        now = utc_now()
        input_patterns = [str(item["path"]) for item in task["inputs"] if item.get("path")]
        with self.connection:
            self.connection.execute(
                "UPDATE tasks SET state='running', heartbeat_at=?, input_hashes_json=?, updated_at=? WHERE task_id=?",
                (now, _json(hash_patterns(self.root, input_patterns)), now, task_id),
            )
            self.connection.execute(
                "UPDATE attempts SET state='running', heartbeat_at=? WHERE task_id=? AND attempt=?",
                (now, task_id, task["attempt_count"]),
            )
        self.event("task_started", task_id, {"worker_id": worker_id, "attempt": task["attempt_count"]})
        return self.task(task_id) or task

    def heartbeat(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task = self._owned_active(task_id, worker_id, ACTIVE_STATES)
        metadata = self.metadata()
        now = utc_now()
        with self.connection:
            self.connection.execute(
                "UPDATE tasks SET heartbeat_at=?, lease_expires_at=?, updated_at=? WHERE task_id=?",
                (now, _iso_after(int(metadata.get("lease_seconds", DEFAULT_LEASE_SECONDS))), now, task_id),
            )
            self.connection.execute(
                "UPDATE attempts SET heartbeat_at=? WHERE task_id=? AND attempt=?",
                (now, task_id, task["attempt_count"]),
            )
        return self.task(task_id) or task

    def _owned_active(self, task_id: str, worker_id: str, states: set[str]) -> dict[str, Any]:
        task = self.task(task_id)
        if not task:
            raise KeyError(f"unknown task: {task_id}")
        if task["state"] not in states:
            raise ValueError(f"{task_id}: expected state {sorted(states)}, found {task['state']}")
        if task["lease_owner"] != worker_id:
            raise PermissionError(f"{task_id}: lease belongs to {task['lease_owner']}")
        return task

    def complete(self, task_id: str, worker_id: str, *, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
        task = self._owned_active(task_id, worker_id, {"running", "validating"})
        if task["track_input_staleness"]:
            patterns = [str(item["path"]) for item in task["inputs"] if item.get("path")]
            if hash_patterns(self.root, patterns) != task["input_hashes"]:
                raise ValueError(f"{task_id}: inputs changed during execution; discard and retry the stale task")
        with self.connection:
            self.connection.execute("UPDATE tasks SET state='validating', updated_at=? WHERE task_id=?", (utc_now(), task_id))
        resolved: list[str] = []
        missing: list[str] = []
        for pattern in task["outputs"]:
            matches = [path for path in resolve_pattern(self.root, pattern) if path.is_dir() or (path.is_file() and path.stat().st_size)]
            if not matches:
                missing.append(pattern)
            resolved.extend(str(path.relative_to(self.root)) for path in matches)
        if missing:
            with self.connection:
                self.connection.execute("UPDATE tasks SET state='running', updated_at=? WHERE task_id=?", (utc_now(), task_id))
            raise ValueError(f"{task_id}: outputs missing or empty: {', '.join(missing)}")
        output_hashes = {relative: hash_path(self.root / relative) for relative in sorted(set(resolved))}
        now = utc_now()
        terminal = {
            "worker_id": worker_id,
            "task_id": task_id,
            "workflow_id": self.metadata().get("run_id"),
            "attempt": task["attempt_count"],
            "phase": task["phase"],
            "task_type": task["task_type"],
            "input_ids": [str(item.get("id", item.get("source_id", item.get("path", "input")))) for item in task["inputs"]],
            "input_patterns": [str(item["path"]) for item in task["inputs"] if item.get("path")],
            "input_hashes": task["input_hashes"],
            "exclusive_inputs": task["exclusive_inputs"],
            "expected_outputs": sorted(set(resolved)),
            "required_validators": task["validators"],
            "depends_on": task["depends_on"],
            "independent": task["independent"],
            "output_mode": task["output_mode"],
            "track_input_staleness": task["track_input_staleness"],
            "status": "succeeded",
            "started_at": self._attempt(task_id, task["attempt_count"])["started_at"],
            "finished_at": now,
            "exit_status": 0,
            "output_validation_status": PASS,
            "output_hashes": output_hashes,
            "telemetry": telemetry or {},
        }
        append_jsonl(self.root / "tools/outputs/worker-ledger.jsonl", terminal)
        with self.connection:
            self.connection.execute(
                """
                UPDATE tasks SET state='succeeded', output_hashes_json=?, lease_owner=NULL,
                    lease_expires_at=NULL, heartbeat_at=?, updated_at=?, finished_at=?, last_error=NULL
                WHERE task_id=?
                """,
                (_json(output_hashes), now, now, now, task_id),
            )
            self.connection.execute(
                "UPDATE attempts SET state='succeeded', heartbeat_at=?, finished_at=?, telemetry_json=? "
                "WHERE task_id=? AND attempt=?",
                (now, now, _json(telemetry or {}), task_id, task["attempt_count"]),
            )
        self.event("task_succeeded", task_id, {"worker_id": worker_id, "attempt": task["attempt_count"]})
        self.refresh_ready()
        return terminal

    def fail(
        self,
        task_id: str,
        worker_id: str,
        reason: str,
        *,
        retryable: bool = True,
        telemetry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = self._owned_active(task_id, worker_id, ACTIVE_STATES)
        exhausted = task["attempt_count"] >= task["max_attempts"]
        state = "retryable" if retryable and not exhausted else "blocked" if retryable else "failed"
        now = utc_now()
        terminal = {
            "worker_id": worker_id,
            "task_id": task_id,
            "workflow_id": self.metadata().get("run_id"),
            "attempt": task["attempt_count"],
            "phase": task["phase"],
            "task_type": task["task_type"],
            "input_ids": [str(item.get("id", item.get("source_id", item.get("path", "input")))) for item in task["inputs"]],
            "exclusive_inputs": task["exclusive_inputs"],
            "expected_outputs": [],
            "required_validators": task["validators"],
            "depends_on": task["depends_on"],
            "independent": task["independent"],
            "status": "failed" if state == "retryable" else state,
            "started_at": self._attempt(task_id, task["attempt_count"])["started_at"],
            "finished_at": now,
            "exit_status": 1,
            "output_validation_status": "FAIL",
            "output_hashes": {},
            "failure_reason": reason.strip() or "unspecified failure",
            "telemetry": telemetry or {},
        }
        append_jsonl(self.root / "tools/outputs/worker-ledger.jsonl", terminal)
        with self.connection:
            self.connection.execute(
                """
                UPDATE tasks SET state=?, lease_owner=NULL, lease_expires_at=NULL, heartbeat_at=?,
                    updated_at=?, finished_at=?, last_error=? WHERE task_id=?
                """,
                (state, now, now, now if state in FINAL_STATES else None, terminal["failure_reason"], task_id),
            )
            self.connection.execute(
                "UPDATE attempts SET state=?, heartbeat_at=?, finished_at=?, failure_reason=?, telemetry_json=? "
                "WHERE task_id=? AND attempt=?",
                (state, now, now, terminal["failure_reason"], _json(telemetry or {}), task_id, task["attempt_count"]),
            )
        self.event("task_failed", task_id, {"state": state, "reason": terminal["failure_reason"]})
        return terminal

    def _attempt(self, task_id: str, attempt: int) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM attempts WHERE task_id=? AND attempt=?", (task_id, attempt)
        ).fetchone()
        if not row:
            raise KeyError(f"missing attempt {task_id}/{attempt}")
        result = dict(row)
        result["telemetry"] = _parse(result.pop("telemetry_json"), {})
        return result

    def recover_expired(self, *, now: str | None = None) -> list[str]:
        current = now or utc_now()
        rows = self.connection.execute(
            "SELECT task_id, lease_owner FROM tasks WHERE state IN ('leased','running','validating') "
            "AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
            (current,),
        ).fetchall()
        recovered: list[str] = []
        for row in rows:
            self.fail(
                row["task_id"],
                row["lease_owner"],
                "worker lease expired; task recovered by scheduler",
                retryable=True,
            )
            recovered.append(row["task_id"])
        return recovered

    def add_source(
        self,
        *,
        canonical_url: str,
        original_url: str,
        host_key: str,
        channel: str,
        source_kind: str,
        relevance: str = "candidate",
        discovered_from: str | None = None,
        depth: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        existing = self.connection.execute(
            "SELECT * FROM sources WHERE canonical_url=?", (canonical_url,)
        ).fetchone()
        if existing:
            return self._source_from_row(existing), False
        source_id = stable_source_id(canonical_url)
        now = utc_now()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO sources(
                    source_id, canonical_url, original_url, host_key, channel, source_kind,
                    status, relevance, discovered_from, depth, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'discovered', ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id, canonical_url, original_url, host_key, channel, source_kind,
                    relevance, discovered_from, depth, _json(metadata or {}), now, now,
                ),
            )
        self.ensure_discovery_channel(channel)
        current = self.discovery_channel(channel)
        if current and (current["state"] != "open" or int(current["consecutive_empty_passes"]) != 0):
            with self.connection:
                self.connection.execute(
                    """
                    UPDATE discovery_channels SET state='open', consecutive_empty_passes=0,
                        completion_evidence=?, updated_at=? WHERE channel=?
                    """,
                    (f"reopened by newly discovered source {source_id}", utc_now(), channel),
                )
            self.event("discovery_channel_reopened", channel, {"source_id": source_id})
        self.event("source_discovered", source_id, {"url": canonical_url, "channel": channel})
        return self.source(source_id) or {}, True

    def _source_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["local_paths"] = _parse(result.pop("local_paths_json"), [])
        result["metadata"] = _parse(result.pop("metadata_json"), {})
        return result

    def source(self, source_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        return self._source_from_row(row) if row else None

    def sources(self, *, statuses: Iterable[str] | None = None) -> list[dict[str, Any]]:
        values = list(statuses or [])
        where = f" WHERE status IN ({','.join('?' for _ in values)})" if values else ""
        rows = self.connection.execute(
            f"SELECT * FROM sources{where} ORDER BY created_at, source_id", values
        ).fetchall()
        return [self._source_from_row(row) for row in rows]

    def update_source(self, source_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {"status", "relevance", "local_paths", "content_bytes", "content_tokens", "metadata"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported source fields: {', '.join(sorted(unknown))}")
        if not self.source(source_id):
            raise KeyError(f"unknown source: {source_id}")
        columns: list[str] = []
        values: list[Any] = []
        for key, value in changes.items():
            column = {"local_paths": "local_paths_json", "metadata": "metadata_json"}.get(key, key)
            columns.append(f"{column}=?")
            values.append(_json(value) if key in {"local_paths", "metadata"} else value)
        columns.append("updated_at=?")
        values.extend([utc_now(), source_id])
        with self.connection:
            self.connection.execute(f"UPDATE sources SET {', '.join(columns)} WHERE source_id=?", values)
        self.event("source_updated", source_id, changes)
        return self.source(source_id) or {}

    def ensure_discovery_channel(self, channel: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO discovery_channels(channel, state, updated_at) VALUES (?, 'open', ?)",
                (channel, utc_now()),
            )

    def record_discovery_pass(
        self,
        channel: str,
        *,
        new_sources: int,
        evidence: str,
        saturation_passes: int = 2,
    ) -> dict[str, Any]:
        if new_sources < 0:
            raise ValueError("new_sources cannot be negative")
        self.ensure_discovery_channel(channel)
        row = self.connection.execute(
            "SELECT * FROM discovery_channels WHERE channel=?", (channel,)
        ).fetchone()
        empty = 0 if new_sources else int(row["consecutive_empty_passes"]) + 1
        state = "saturated" if empty >= saturation_passes else "open"
        now = utc_now()
        with self.connection:
            self.connection.execute(
                """
                UPDATE discovery_channels SET state=?, consecutive_empty_passes=?,
                    total_passes=total_passes+1, total_new_sources=total_new_sources+?,
                    completion_evidence=?, updated_at=? WHERE channel=?
                """,
                (state, empty, new_sources, evidence, now, channel),
            )
        result = self.discovery_channel(channel) or {}
        self.event("discovery_pass", channel, {"new_sources": new_sources, "state": state, "evidence": evidence})
        return result

    def set_discovery_channel(self, channel: str, state: str, evidence: str) -> dict[str, Any]:
        if state not in DISCOVERY_TERMINAL | {"open"}:
            raise ValueError(f"unsupported discovery state: {state}")
        self.ensure_discovery_channel(channel)
        with self.connection:
            if state == "open":
                self.connection.execute(
                    "UPDATE discovery_channels SET state=?, consecutive_empty_passes=0, "
                    "completion_evidence=?, updated_at=? WHERE channel=?",
                    (state, evidence, utc_now(), channel),
                )
            else:
                self.connection.execute(
                    "UPDATE discovery_channels SET state=?, completion_evidence=?, updated_at=? WHERE channel=?",
                    (state, evidence, utc_now(), channel),
                )
        self.event("discovery_channel_updated", channel, {"state": state, "evidence": evidence})
        return self.discovery_channel(channel) or {}

    def discovery_channel(self, channel: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM discovery_channels WHERE channel=?", (channel,)
        ).fetchone()
        return dict(row) if row else None

    def discovery_channels(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM discovery_channels ORDER BY channel")]

    def summary(self) -> dict[str, Any]:
        task_counts = {
            row["state"]: row["count"]
            for row in self.connection.execute("SELECT state, COUNT(*) AS count FROM tasks GROUP BY state")
        }
        source_counts = {
            row["status"]: row["count"]
            for row in self.connection.execute("SELECT status, COUNT(*) AS count FROM sources GROUP BY status")
        }
        channels = self.discovery_channels()
        return {
            "database": str(self.path.relative_to(self.root)),
            "metadata": self.metadata(),
            "task_counts": task_counts,
            "source_counts": source_counts,
            "discovery": {
                "terminal": bool(channels) and all(item["state"] in DISCOVERY_TERMINAL for item in channels),
                "complete": bool(channels) and all(item["state"] in DISCOVERY_COMPLETE for item in channels),
                "limitations": [item["channel"] for item in channels if item["state"] in {"blocked", "incomplete"}],
                "channels": channels,
            },
        }
