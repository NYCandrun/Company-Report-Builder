from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS, UNKNOWN
from research_control.gates.phase_gate import check_phase_gate
from research_control.tests.helpers import populate_gate_fixture, validation, write_json, write_jsonl, worker


class PhaseGateTests(unittest.TestCase):
    def test_complete_current_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = populate_gate_fixture(root)
            report, _ = check_phase_gate(root, "capture", workflow)
            self.assertEqual(PASS, report["status"])

    def test_absent_worker_output_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = populate_gate_fixture(root)
            (root / "out/result.txt").unlink()
            write_jsonl(root / "tools/outputs/worker-ledger.jsonl", [worker(root)])
            report, _ = check_phase_gate(root, "capture", workflow)
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("required output absent" in item for item in report["failures"]))

    def test_validator_that_never_ran_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = populate_gate_fixture(root)
            (root / "tools/outputs/validations/records.json").unlink()
            report, _ = check_phase_gate(root, "capture", workflow)
            self.assertEqual(UNKNOWN, report["status"])

    def test_short_validator_run_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = populate_gate_fixture(root)
            write_json(root / "tools/outputs/validations/records.json", validation(expected=2, checked=1))
            report, _ = check_phase_gate(root, "capture", workflow)
            self.assertEqual(UNKNOWN, report["status"])
            self.assertTrue(any("fewer records" in item for item in report["unknowns"]))

    def test_state_cannot_claim_complete_before_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = populate_gate_fixture(root)
            (root / "WORKFLOW_STATE.md").write_text("| capture | Done |\n", encoding="utf-8")
            report, _ = check_phase_gate(root, "capture", workflow)
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("marks capture complete" in item for item in report["failures"]))

    def test_failed_gate_does_not_authorize_complete_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = populate_gate_fixture(root)
            (root / "WORKFLOW_STATE.md").write_text("| capture | Complete |\n", encoding="utf-8")
            write_json(root / "tools/outputs/gates/capture.json", validation(status=FAIL))
            report, _ = check_phase_gate(root, "capture", workflow)
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("marks capture complete" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
