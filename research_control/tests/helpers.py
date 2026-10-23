from __future__ import annotations

import json
from pathlib import Path

from research_control import PASS
from research_control.hashing import hash_path
from research_control.io import atomic_write_json, utc_now


def validation(status: str = PASS, expected: int = 1, checked: int = 1, input_hashes: dict[str, str] | None = None, details: dict | None = None) -> dict:
    return {
        "schema_version": "1.0.0", "checker": "fixture", "checker_version": "fixture-v1",
        "status": status, "expected_count": expected, "checked_count": checked,
        "failure_count": 0 if status == PASS else 1, "exception_count": 0,
        "failures": [] if status == PASS else ["planted failure"], "unknowns": [],
        "input_hashes": input_hashes or {}, "completed_at": utc_now(), "details": details or {},
    }


def write_json(path: Path, value: object) -> None:
    atomic_write_json(path, value)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def worker(root: Path, *, output: str = "out/result.txt", status: str = "succeeded", task_type: str = "capture") -> dict:
    path = root / output
    hashes = {output: hash_path(path)} if path.exists() else {}
    return {
        "worker_id": "worker-1", "task_id": "task-1", "attempt": 1,
        "task_type": task_type, "input_ids": ["IN-1"], "exclusive_inputs": True,
        "expected_outputs": [output], "required_validators": ["local"], "status": status,
        "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:01:00Z",
        "exit_status": 0, "output_validation_status": PASS, "output_hashes": hashes,
    }


def minimal_gate_workflow(root: Path) -> Path:
    document = {
        "schema_version": "1.0.0",
        "global": {"ledger": "tools/outputs/worker-ledger.jsonl", "gate_directory": "tools/outputs/gates", "release_manifest": "07-final-report/release-manifest.json"},
        "test_suites": [{"id": "execution_integrity", "report": "tools/outputs/tests/execution.json"}],
        "phases": [{
            "id": "capture", "depends_on": [], "stale_if": ["inputs.txt", "out/result.txt"],
            "reconciliations": [{"id": "work", "report": "tools/outputs/reconciliation/work.json"}],
            "validators": [{"id": "records", "report": "tools/outputs/validations/records.json"}],
            "semantic_reviews": [{"id": "coverage", "path": "review.md", "role": "reviewer", "independent": True}],
            "gate": {"name": "capture", "required_paths": ["out/result.txt"],
                     "required_reconciliations": ["work"], "required_validators": ["records"],
                     "required_semantic_reviews": ["coverage"], "required_tests": ["execution_integrity"],
                     "required_worker_task_types": ["capture"]},
        }],
    }
    path = root / "WORKFLOW.yaml"
    write_json(path, document)
    return path


def populate_gate_fixture(root: Path) -> Path:
    workflow = minimal_gate_workflow(root)
    (root / "out").mkdir(parents=True)
    (root / "out/result.txt").write_text("done\n", encoding="utf-8")
    (root / "inputs.txt").write_text("IN-1\n", encoding="utf-8")
    (root / "review.md").write_text("review complete\n", encoding="utf-8")
    for relative in ("tools/outputs/reconciliation/work.json", "tools/outputs/validations/records.json", "tools/outputs/tests/execution.json"):
        write_json(root / relative, validation())
    write_jsonl(root / "tools/outputs/worker-ledger.jsonl", [worker(root)])
    return workflow
