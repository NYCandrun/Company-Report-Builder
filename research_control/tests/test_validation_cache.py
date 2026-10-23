from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import PASS
from research_control.checks import _cached_pass, _validation_engine_key
from research_control.hashing import hash_patterns
from research_control.io import atomic_write_json
from research_control.reporting import make_validation_report


class ValidationCacheTests(unittest.TestCase):
    def test_pass_is_reused_only_for_identical_inputs_and_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.txt"
            artifact.write_text("one\n", encoding="utf-8")
            key = _validation_engine_key(root)
            report = make_validation_report(
                checker="fixture",
                checker_version="fixture-v1",
                status=PASS,
                expected_count=1,
                checked_count=1,
                input_hashes=hash_patterns(root, ["artifact.txt"]),
            )
            report["cache_key"] = key
            atomic_write_json(root / "report.json", report)
            self.assertIsNotNone(_cached_pass(root, "report.json", key))
            artifact.write_text("two\n", encoding="utf-8")
            self.assertIsNone(_cached_pass(root, "report.json", key))
            artifact.write_text("one\n", encoding="utf-8")
            self.assertIsNone(_cached_pass(root, "report.json", "different-engine"))


if __name__ == "__main__":
    unittest.main()
