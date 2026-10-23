from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS
from research_control.validators.sources import validate_records


class SourceValidatorTests(unittest.TestCase):
    def record(self) -> dict[str, str]:
        return {
            "id": "WEB-001", "grade": "P", "title": "Product", "publisher": "Example",
            "url": "https://example.com/product", "date published": "2026-01-01",
            "date captured": "2026-01-02", "local file": "sources/product.md",
            "method": "browser", "notes": "",
        }

    def test_valid_source_and_local_file_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sources").mkdir()
            (root / "sources/product.md").write_text("receipt", encoding="utf-8")
            (root / "manifest.csv").write_text("fixture", encoding="utf-8")
            report = validate_records([self.record()], root, "manifest.csv")
            self.assertEqual(PASS, report["status"])

    def test_duplicate_id_and_missing_file_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.csv").write_text("fixture", encoding="utf-8")
            report = validate_records([self.record(), self.record()], root, "manifest.csv")
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("duplicate source ID" in item for item in report["failures"]))
            self.assertTrue(any("local file not found" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
