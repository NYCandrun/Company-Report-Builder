"""Generic work reconciliation and worker-ledger integrity checks."""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from research_control import FAIL, PASS, UNKNOWN
from research_control.hashing import hash_path
from research_control.reporting import make_validation_report
from research_control.hashing import checker_version, hash_patterns


FINAL_DISPOSITIONS = {"completed", "completed_zero", "duplicate", "excluded", "blocked", "rejected"}
WORKER_TERMINAL = {"succeeded", "failed", "blocked"}
WORKER_REQUIRED = {"worker_id", "task_id", "attempt", "task_type", "input_ids", "exclusive_inputs", "expected_outputs", "required_validators", "status"}


def reconcile_records(
    *,
    reconciliation_id: str,
    assigned_ids: Iterable[str],
    dispositions: list[dict[str, Any]],
    root: Path,
    input_patterns: list[str],
    allowed_dispositions: set[str] | None = None,
    allow_one_to_many: bool = False,
) -> dict[str, Any]:
    assigned = list(assigned_ids)
    allowed = allowed_dispositions or FINAL_DISPOSITIONS
    failures: list[str] = []
    by_input: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in dispositions:
        input_id = str(record.get("input_id", ""))
        if not input_id:
            failures.append("disposition missing input_id")
            continue
        by_input[input_id].append(record)
        value = record.get("disposition")
        if value not in allowed:
            failures.append(f"{input_id}: invalid disposition {value!r}")
        if not str(record.get("reason", "")).strip():
            failures.append(f"{input_id}: missing disposition reason")
        evidence = record.get("evidence_paths", [])
        if value in {"completed", "completed_zero", "duplicate", "blocked", "excluded"} and not evidence:
            failures.append(f"{input_id}: {value} disposition has no evidence path")
        for relative in evidence:
            if not (root / relative).exists():
                failures.append(f"{input_id}: evidence path not found {relative}")
        if not allow_one_to_many and len(record.get("output_ids", [])) > 1:
            failures.append(f"{input_id}: undeclared one-to-many outputs")

    assigned_set = set(assigned)
    if len(assigned) != len(assigned_set):
        duplicates = [item for item, count in Counter(assigned).items() if count > 1]
        failures.append(f"assignment contains duplicate IDs: {duplicates}")
    for input_id in sorted(assigned_set):
        count = len(by_input.get(input_id, []))
        if count == 0:
            failures.append(f"{input_id}: missing final disposition")
        elif count > 1:
            failures.append(f"{input_id}: {count} final dispositions")
    for input_id in sorted(set(by_input) - assigned_set):
        failures.append(f"{input_id}: unassigned output/disposition")

    counts = Counter(str(records[0].get("disposition")) if len(records) == 1 else "ambiguous" for records in by_input.values())
    status = FAIL if failures else PASS
    report = make_validation_report(
        checker=f"reconcile:{reconciliation_id}",
        checker_version=checker_version(sys.modules[__name__]),
        status=status,
        expected_count=len(assigned_set),
        checked_count=len(assigned_set & set(by_input)),
        failures=failures,
        input_hashes=hash_patterns(root, input_patterns),
        details={
            "reconciliation_id": reconciliation_id,
            "assigned": len(assigned_set),
            "completed": counts["completed"] + counts["completed_zero"],
            "excluded": counts["excluded"],
            "blocked": counts["blocked"],
            "duplicate": counts["duplicate"],
            "rejected": counts["rejected"],
            "missing": sum(1 for item in assigned_set if item not in by_input),
            "unexpected": len(set(by_input) - assigned_set),
        },
    )
    report["reconciliation_id"] = reconciliation_id
    return report


def superseded_tasks(root: Path) -> set[str]:
    """Tasks the scheduler retired; their ledger rows record history, not live ownership."""
    database = root / "tools/outputs/runtime.sqlite3"
    if not database.is_file():
        return set()
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return {row[0] for row in connection.execute("SELECT task_id FROM tasks WHERE state='superseded'")}
    finally:
        connection.close()


def validate_ledger(root: Path, records: list[dict[str, Any]], task_types: set[str] | None = None) -> dict[str, Any]:
    retired = superseded_tasks(root)
    records = [row for row in records if str(row.get("task_id", "")) not in retired]
    selected = [row for row in records if task_types is None or row.get("task_type") in task_types]
    final_output_owner: dict[str, tuple[str, str]] = {}
    for row in records:
        task_id = str(row.get("task_id", ""))
        mode = str(row.get("output_mode", "create"))
        for output in row.get("expected_outputs", []):
            final_output_owner[str(output)] = (task_id, mode)
    failures: list[str] = []
    unknowns: list[str] = []
    attempts: set[tuple[str, int]] = set()
    exclusive_owner: dict[tuple[str, str], str] = {}
    output_owner: dict[str, tuple[str, str]] = {}
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if task_types:
        represented = {str(row.get("task_type")) for row in selected}
        for missing_type in sorted(task_types - represented):
            unknowns.append(f"no ledger attempts registered for required task type {missing_type}")

    for index, row in enumerate(selected, 1):
        missing = sorted(WORKER_REQUIRED - set(row))
        if missing:
            failures.append(f"ledger row {index}: missing fields {', '.join(missing)}")
            continue
        task_id = str(row["task_id"])
        by_task[task_id].append(row)
        try:
            key = (task_id, int(row["attempt"]))
        except (TypeError, ValueError):
            failures.append(f"{task_id}: attempt is not a positive integer")
            continue
        if key in attempts:
            failures.append(f"{task_id}: duplicate attempt {key[1]}")
        attempts.add(key)
        if key[1] < 1:
            failures.append(f"{task_id}: attempt must be positive")
        if row.get("exclusive_inputs"):
            for input_id in row.get("input_ids", []):
                ownership_key = (str(row.get("phase", "")), str(input_id))
                owner = exclusive_owner.get(ownership_key)
                if owner is not None and owner != task_id and owner not in row.get("depends_on", []):
                    failures.append(f"exclusive input {input_id} overlaps tasks {owner} and {task_id}")
                exclusive_owner[ownership_key] = task_id
        output_mode = str(row.get("output_mode", "create"))
        for output in row.get("expected_outputs", []):
            owner = output_owner.get(output)
            if owner is not None and owner[0] != task_id and output_mode != "revise":
                failures.append(f"output path {output} overlaps tasks {owner[0]} and {task_id}")
            output_owner[output] = (task_id, output_mode)

    for task_id, attempts_for_task in by_task.items():
        ordered = sorted(attempts_for_task, key=lambda row: int(row.get("attempt", 0)))
        latest = ordered[-1]
        if latest.get("status") not in WORKER_TERMINAL:
            unknowns.append(f"{task_id}: latest attempt is {latest.get('status')!r}")
        elif latest.get("status") != "succeeded":
            failures.append(f"{task_id}: latest attempt ended {latest.get('status')}")
        else:
            attempt = int(latest.get("attempt", 0))
            if latest.get("output_validation_status") != PASS:
                failures.append(f"{task_id} attempt {attempt}: succeeded without PASS output validation")
            if latest.get("track_input_staleness"):
                current_inputs = hash_patterns(root, latest.get("input_patterns", []))
                if current_inputs != latest.get("input_hashes", {}):
                    failures.append(f"{task_id} attempt {attempt}: review inputs are stale")
            hashes = latest.get("output_hashes", {})
            for output in latest.get("expected_outputs", []):
                # A later declared revision owns the current bytes. Earlier task
                # hashes remain historical evidence rather than false staleness.
                owner = final_output_owner.get(output)
                if owner is not None and owner[0] != task_id:
                    continue
                current = hash_path(root / output)
                if current == "MISSING":
                    failures.append(f"{task_id} attempt {attempt}: required output absent {output}")
                elif hashes.get(output) != current:
                    failures.append(f"{task_id} attempt {attempt}: missing or stale output hash for {output}")

    status = FAIL if failures else UNKNOWN if unknowns else PASS
    return make_validation_report(
        checker="worker_ledger",
        checker_version=checker_version(sys.modules[__name__]),
        status=status,
        expected_count=len(selected),
        checked_count=len(selected),
        failures=failures,
        unknowns=unknowns,
        input_hashes=hash_patterns(root, ["tools/outputs/worker-ledger.jsonl"]),
        details={"task_types": sorted(task_types or []), "tasks": len(by_task), "attempts": len(selected)},
    )
