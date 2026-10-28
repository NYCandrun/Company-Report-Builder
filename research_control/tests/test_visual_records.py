from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS
from research_control.validators.visual_records import validate


class VisualRecordTests(unittest.TestCase):
    def test_every_page_recorded_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "visual.json").write_text("fixture", encoding="utf-8")
            records = [{"page": page, "status": "clean", "issues": []} for page in range(1, 4)]
            self.assertEqual(PASS, validate(3, records, root, "visual.json")["status"])

    def test_skipped_page_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "visual.json").write_text("fixture", encoding="utf-8")
            records = [{"page": 1, "status": "clean", "issues": []}, {"page": 3, "status": "clean", "issues": []}]
            report = validate(3, records, root, "visual.json")
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("page 2" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
