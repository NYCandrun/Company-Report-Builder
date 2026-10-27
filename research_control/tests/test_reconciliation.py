from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS
from research_control.reconciliation.assignments import reconcile_records, validate_ledger
from research_control.runtime import RuntimeStore, WorkItem


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
            # A batch the scheduler superseded no longer owns its inputs.
            with RuntimeStore(root) as store:
                store.initialize(run_id="run", company_url="https://example.com")
                store.add_task(WorkItem(
                    task_id="task-a", phase="capture", task_type="capture", inputs=[{"id": "SRC-001"}],
                    outputs=["task-a.md"], prompt_files=["prompt.md"],
                ))
                store.supersede("task-a", "replaced by task-b")
            report = validate_ledger(root, rows)
            self.assertFalse(any("overlaps tasks" in item for item in report["failures"]))

    def test_worker_success_without_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = validate_ledger(Path(directory), jsonl(FIXTURES / "worker-success-missing-output.jsonl"))
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("required output absent" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()


class CarriedWorkTests(unittest.TestCase):
    def test_retired_successful_work_still_shows_its_kind_was_done(self) -> None:
        from unittest import mock

        from research_control.reconciliation import assignments

        row = {"task_id": "verification.verify.a", "task_type": "verification", "exit_status": 0, "attempt": 1}
        with mock.patch.object(assignments, "superseded_tasks", return_value={"verification.verify.a"}):
            report = assignments.validate_ledger(Path("."), [row], {"verification"})
        self.assertNotIn("no ledger attempts registered for required task type verification", report.get("unknowns", []))
        with mock.patch.object(assignments, "superseded_tasks", return_value={"verification.verify.a"}):
            report = assignments.validate_ledger(Path("."), [{**row, "exit_status": 1}], {"verification"})
        self.assertIn("no ledger attempts registered for required task type verification", report.get("unknowns", []))


class RelationshipConsistencyTests(unittest.TestCase):
    def test_organizations_marked_differently_across_files_are_listed(self) -> None:
        import tempfile

        from research_control.consistency import REPORT, write_relationship_report
        from research_control.io import atomic_write_text

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "05-synthesis/offering.md", "Work for Microsoft (inferred client: the ASN repository).\n")
            atomic_write_text(root / "05-synthesis/customers-proof.md",
                              "Microsoft (stated client: an employee's plugin names it). Acme (inferred client: two commits).\n"
                              "Holiday Inn Club Vacations (lead, thin evidence: one demo).\n")
            atomic_write_text(root / "05-synthesis/direction.md", "Holiday Inn Club Vacations (inferred client: a demo and a proposal).\n")
            result = write_relationship_report(root)
            self.assertEqual(2, result["marked_differently"])
            text = (root / REPORT).read_text(encoding="utf-8")
            self.assertIn("- Microsoft: inferred in offering.md; stated in customers-proof.md", text)
            self.assertIn("- Holiday Inn Club Vacations: inferred in direction.md; lead in customers-proof.md", text)
            self.assertNotIn("- Acme", text)


class ReportOutlineTests(unittest.TestCase):
    def test_the_report_outline_follows_the_runs_questions(self) -> None:
        import tempfile

        from research_control.io import atomic_write_text, load_json
        from research_control.report_outline import OUTLINE, report_words, write_report_outline

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "00-scope.md", "# Scope\n\nFocus: Go-to-market\n\n"
                              "**Q1. Product and architecture.** What does it deliver?\n\n"
                              "**Q2. Accounts and engagements over time.** How have client accounts moved?\n\n"
                              "**Q10. Scale.** How big is it?\n")
            result = write_report_outline(root)
            outline = load_json(root / OUTLINE)
            self.assertEqual(["Q1", "Q2", "Q10"], [section["question"] for section in outline["sections"]])
            self.assertEqual("Accounts and engagements over time", outline["sections"][1]["title"])
            self.assertEqual("Go-to-market", outline["focus"])
            self.assertEqual({"include": True, "questions": ["Q2"]}, outline["accounts_exhibit"])
            self.assertEqual(1_500 + 3 * 450, outline["words"]["target"])
            self.assertEqual(3, result["sections"])
            # Prose is counted; tables and fact IDs are not.
            self.assertEqual(4, report_words("Tribe builds agents today [PRD-001, PRD-002].\n| a | b |\n|---|---|\n| c | d |\n"))
            # A scope that lists its questions one per line works too, with a general focus.
            atomic_write_text(root / "00-scope.md", "# Scope\n\n## Research questions\n\n- Q1 product and architecture.\n- Q7 competitors.\n")
            outline = load_json(root / OUTLINE) if write_report_outline(root) else {}
            self.assertEqual(("Company research", ["Q1", "Q7"], False),
                             (outline["focus"], [section["question"] for section in outline["sections"]], outline["accounts_exhibit"]["include"]))
