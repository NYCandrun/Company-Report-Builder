from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import PASS
from research_control.gates.phase_gate import gate_report_is_current
from research_control.hashing import hash_path
from research_control.tests.helpers import validation


class StalenessTests(unittest.TestCase):
    def test_changed_input_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "artifact.txt"
            target.write_text("validated", encoding="utf-8")
            report = validation(input_hashes={"artifact.txt": hash_path(target)})
            self.assertTrue(gate_report_is_current(root, report)[0])
            target.write_text("changed", encoding="utf-8")
            current, errors = gate_report_is_current(root, report)
            self.assertFalse(current)
            self.assertTrue(any("stale input" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
