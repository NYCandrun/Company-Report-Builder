from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS
from research_control.reconciliation.assignments import reconcile_records, validate_ledger


FIXTURES = Path(__file__).with_name("fixtures")


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class ReconciliationTests(unittest.TestCase):
    def test_missing_disposition_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence").mkdir()
            (root / "evidence/SRC-001.md").write_text("captured", encoding="utf-8")
            report = reconcile_records(
                reconciliation_id="capture", assigned_ids=["SRC-001", "SRC-002"],
                dispositions=jsonl(FIXTURES / "dispositions-missing.jsonl"), root=root,
                input_patterns=[],
            )
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("SRC-002: missing" in item for item in report["failures"]))

    def test_explicit_completed_zero_is_accounted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence").mkdir()
            for name in ("SRC-001", "SRC-002"):
                (root / f"evidence/{name}.md").write_text("read", encoding="utf-8")
            report = reconcile_records(
                reconciliation_id="capture", assigned_ids=["SRC-001", "SRC-002"],
                dispositions=jsonl(FIXTURES / "dispositions-complete.jsonl"), root=root,
                input_patterns=[],
            )
            self.assertEqual(PASS, report["status"])
            self.assertEqual(2, report["details"]["completed"])

    def test_overlapping_exclusive_assignments_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for task in ("task-a", "task-b"):
                rows.append({
                    "worker_id": f"worker-{task}", "task_id": task, "attempt": 1,
                    "task_type": "capture", "input_ids": ["SRC-001"], "exclusive_inputs": True,
                    "expected_outputs": [f"{task}.md"], "required_validators": [], "status": "failed",
                })
            report = validate_ledger(root, rows)
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("overlaps tasks" in item for item in report["failures"]))

    def test_worker_success_without_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = validate_ledger(Path(directory), jsonl(FIXTURES / "worker-success-missing-output.jsonl"))
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("required output absent" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
