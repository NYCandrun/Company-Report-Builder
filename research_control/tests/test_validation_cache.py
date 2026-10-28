from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import PASS, checks
from research_control.checks import _cached_pass, _validation_engine_key
from research_control.hashing import hash_patterns
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text
from research_control.reporting import make_validation_report
from research_control.tests.test_diagrams import model, write_models


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

    def test_verification_helpers_invalidate_the_engine_cache(self) -> None:
        for helper in ("verification.py", "verification_sandbox.py"):
            with self.subTest(helper=helper), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / "research_control" / helper
                atomic_write_text(path, "original helper\n")
                key = _validation_engine_key(root)
                report = make_validation_report(
                    checker="fixture", checker_version="fixture-v1", status=PASS,
                    expected_count=1, checked_count=1,
                )
                report["cache_key"] = key
                atomic_write_json(root / "report.json", report)
                self.assertIsNotNone(_cached_pass(root, "report.json", key))
                atomic_write_text(path, "changed helper\n")
                self.assertIsNone(_cached_pass(root, "report.json", _validation_engine_key(root)))

    def test_supplemental_verdict_changes_invalidate_every_consumer(self) -> None:
        consumers = [
            (checks.run_validator, "verification_verdict_records"),
            (checks.run_validator, "new_cited_fact_verification"),
            (checks.run_validator, "diagram_models"),
            (checks.run_reconciliation, "cited_fact_verification"),
            (checks.run_reconciliation, "verification_corrections"),
            (checks.run_reconciliation, "final_cited_facts"),
        ]
        for check, name in consumers:
            with self.subTest(check=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                main = root / "tools/outputs/verification-verdicts.jsonl"
                added = root / "tools/outputs/verification-verdicts-added.jsonl"
                verdict = {
                    "fact_id": "ACME-001", "verdict": "confirmed",
                    "reason": "The captured quote supports the claim.",
                    "evidence_paths": ["01-sources/captures/SRC-001/content.txt"],
                }
                atomic_write_jsonl(main, [])
                atomic_write_jsonl(added, [verdict])
                atomic_write_text(root / "tools/lists/cited-facts.txt", "ACME-001\n")
                atomic_write_jsonl(root / "tools/outputs/verification-corrections.jsonl", [{"fact_id": "ACME-001"}])
                atomic_write_json(root / "tools/outputs/citation-map-company-brief.json", {
                    "citations": [{"facts": ["ACME-001"]}],
                })
                atomic_write_text(root / "01-sources/MANIFEST.csv", "id,url\nSRC-001,https://example.com\n")
                atomic_write_text(root / "02-facts/facts.md",
                                  "| Fact ID | Claim | Verbatim quote | Source ID |\n"
                                  "|---|---|---|---|\n"
                                  "| ACME-001 | Acme sells a product. | Our product | SRC-001 |\n")
                write_models(root, model())
                phase = {"id": "verification"}
                report = check(root, phase, name)
                self.assertEqual(PASS, report["status"], report)
                key = _validation_engine_key(root)
                report["cache_key"] = key
                atomic_write_json(root / "report.json", report)
                self.assertIsNotNone(_cached_pass(root, "report.json", key))

                # Only the supplemental verdict changes; citations and primary verdicts do not.
                atomic_write_jsonl(added, [{**verdict, "verdict": "unsupported"}])
                self.assertIsNone(_cached_pass(root, "report.json", key))
                if name in {"new_cited_fact_verification", "diagram_models", "final_cited_facts"}:
                    self.assertNotEqual(PASS, check(root, phase, name)["status"])

                atomic_write_jsonl(added, [verdict])
                self.assertIsNotNone(_cached_pass(root, "report.json", key))
                added.unlink()
                self.assertIsNone(_cached_pass(root, "report.json", key))
                self.assertNotEqual(PASS, check(root, phase, name)["status"])

    def test_adding_a_supplemental_verdict_invalidates_a_cached_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_jsonl(root / "tools/outputs/verification-verdicts.jsonl", [{
                "fact_id": "ACME-001", "verdict": "confirmed", "reason": "Supported.",
                "evidence_paths": ["capture.txt"],
            }])
            report = checks._validate_verdicts(root, "verification_verdict_records")
            self.assertEqual(PASS, report["status"])
            key = _validation_engine_key(root)
            report["cache_key"] = key
            atomic_write_json(root / "report.json", report)
            self.assertIsNotNone(_cached_pass(root, "report.json", key))
            atomic_write_jsonl(root / "tools/outputs/verification-verdicts-added.jsonl", [{
                "fact_id": "ACME-002", "verdict": "invalid", "reason": "Malformed addition.",
                "evidence_paths": ["capture.txt"],
            }])
            self.assertIsNone(_cached_pass(root, "report.json", key))
            self.assertNotEqual(PASS, checks._validate_verdicts(root, "verification_verdict_records")["status"])


if __name__ == "__main__":
    unittest.main()
