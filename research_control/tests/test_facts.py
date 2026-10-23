from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS
from research_control.validators.dates import validate_fact_dates, validate_source_dates
from research_control.validators.facts import validate_records
from research_control.validators.quotes import validate as validate_quotes
from research_control.validators.tags import validate as validate_tags


class FactValidatorTests(unittest.TestCase):
    def fact(self) -> dict[str, str]:
        return {
            "fact_id": "PRD-001", "claim": "The product launched.",
            "verbatim_quote": "We launched the product today.", "source_id": "WEB-001",
            "location": "line 12", "source_date": "2026-01-01 (published); captured 2026-01-02",
            "grade": "P", "topics": "products-architecture", "about": "Example",
            "said_by": "Example", "verdict": "pending, script-checked only",
        }

    def test_valid_fact_shape_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "facts.md").write_text("fixture", encoding="utf-8")
            self.assertEqual(PASS, validate_records([self.fact()], root, {"WEB-001"}, ["facts.md"])["status"])
            self.assertEqual(PASS, validate_tags([self.fact()], root, ["facts.md"])["status"])

    def test_duplicate_vague_and_unresolved_receipt_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "facts.md").write_text("fixture", encoding="utf-8")
            bad = self.fact()
            bad["source_id"] = "website"
            report = validate_records([bad, bad], root, {"WEB-001"}, ["facts.md"])
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("duplicate fact ID" in item for item in report["failures"]))
            self.assertTrue(any("vague or path-only" in item for item in report["failures"]))

    def test_wrong_quote_and_location_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_text("A different statement appears here.", encoding="utf-8")
            (root / "facts.md").write_text("fixture", encoding="utf-8")
            bad = self.fact()
            bad["location"] = "line"
            report = validate_quotes([bad], {"WEB-001": source}, root, ["facts.md"])
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("quote not found" in item for item in report["failures"]))
            self.assertTrue(any("not exact" in item for item in report["failures"]))

    def test_modified_date_cannot_masquerade_as_published(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.csv").write_text("fixture", encoding="utf-8")
            row = {"id": "WEB-001", "date published": "2026-01-01", "date last modified": "2026-01-01", "date method": "pricing-page modification metadata"}
            report = validate_source_dates([row], root, "manifest.csv")
            self.assertEqual(FAIL, report["status"])

    def test_duplicate_conflict_wrong_date_and_overstatement_are_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "facts.md").write_text("fixture", encoding="utf-8")
            first = self.fact()
            first.update({"fact_id": "PKG-001", "subject": "price", "claim": "The plan costs $10.", "verbatim_quote": "The plan can cost up to $10."})
            second = self.fact()
            second.update({"fact_id": "PKG-002", "subject": "price", "claim": "The plan costs $20.", "verbatim_quote": "The plan costs $20."})
            duplicate = dict(second)
            duplicate["fact_id"] = "PKG-003"
            report = validate_records([first, second, duplicate], root, {"WEB-001"}, ["facts.md"])
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("likely duplicate" in item for item in report["failures"]))
            self.assertTrue(any("conflicting numeric facts" in item for item in report["failures"]))
            self.assertTrue(any("overstatement-risk" in item for item in report["failures"]))
            wrong_date = dict(self.fact())
            wrong_date["source_date"] = "2025-12-01 (published); captured 2026-01-02"
            date_report = validate_fact_dates([wrong_date], root, ["facts.md"], {"WEB-001": "2026-01-01"})
            self.assertEqual(FAIL, date_report["status"])
            self.assertTrue(any("does not match manifest" in item for item in date_report["failures"]))


if __name__ == "__main__":
    unittest.main()
