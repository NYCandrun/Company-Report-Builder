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
    def test_the_report_is_top_down_and_places_every_question(self) -> None:
        import tempfile

        from research_control.io import atomic_write_text, load_json
        from research_control.report_outline import OUTLINE, write_report_outline

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "00-scope.md", "# Scope\n\nFocus: Go-to-market\n\n"
                              "**Q1. Product and architecture.** What does it deliver?\n\n"
                              "**Q2. Accounts and engagements over time.** How have client accounts moved?\n\n"
                              "**Q3. Competitors.** Who else competes?\n\n"
                              "**Q10. Scale and financial signals.** How big is it?\n")
            write_report_outline(root)
            outline = load_json(root / OUTLINE)
            # Broad context first, then specifics; not the questions' numbered order.
            self.assertEqual(
                [("company", ["Q10"]), ("market", ["Q3"]), ("offering", ["Q1"]), ("customers", ["Q2"])],
                [(part["part"], [item["question"] for item in part["covers"]]) for part in outline["parts"]],
            )
            self.assertEqual("executive summary", outline["opening"])
            self.assertEqual("Go-to-market", outline["focus"])
            self.assertEqual({"include": True, "questions": ["Q2"]}, outline["accounts_exhibit"])
            # No length target: the report is as long as the evidence needs.
            self.assertNotIn("words", outline)
            # A scope that lists its questions one per line works too, with the whole company as focus.
            atomic_write_text(root / "00-scope.md", "# Scope\n\n## Research questions\n\n- Q1 product and architecture.\n- Q7 competitors.\n")
            write_report_outline(root)
            outline = load_json(root / OUTLINE)
            self.assertEqual(("The whole company", ["market", "offering"], False),
                             (outline["focus"], [part["part"] for part in outline["parts"]], outline["accounts_exhibit"]["include"]))


class CitationBuildTests(unittest.TestCase):
    def test_fact_ids_become_numbered_superscripts_linked_to_deep_links(self) -> None:
        import tempfile

        from research_control import citation_build
        from research_control.io import atomic_write_jsonl, atomic_write_text, load_json
        from research_control.publication import markdown_to_html

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "01-sources/MANIFEST.csv",
                              "id,grade,title,publisher,url,date published\n"
                              "SRC-A,P,Home page,example.com,https://example.com/,\n"
                              "SRC-B,S,Launch post,news.example,https://news.example/launch,2026-03-01\n")
            atomic_write_text(root / "02-facts/facts.md",
                              "| Fact ID | Claim | Verbatim quote | Source ID | Grade |\n|---|---|---|---|---|\n"
                              "| PRD-001 | Sells agents | agents | SRC-A | P |\n| PRD-002 | Launched | launched | SRC-B | S |\n"
                              "| PRD-003 | Ships fast | fast | SRC-A | P |\n")
            atomic_write_jsonl(root / "tools/outputs/fact-links.jsonl", [
                {"fact_id": "PRD-001", "located": True, "deep_link": "https://example.com/#:~:text=agents"},
                {"fact_id": "PRD-002", "located": False, "deep_link": "https://news.example/launch"},
            ])
            filler = "This paragraph talks at length about the market in general terms without showing any evidence at all for what it says here, which a reader cannot check."
            atomic_write_text(root / citation_build.BRIEF,
                              "# Company brief\n\n## Executive summary\n\nIt sells agents [PRD-001] and launched [PRD-002, PRD-003].\n\n"
                              f"{filler}\n\n| Offering | Evidence |\n|---|---|\n| Agents | Stated [PRD-001] |\n| Studio | Lead |\n\n"
                              "## Open questions and whom to ask\n\n" + filler + "\n\n## Sources\n")
            built = citation_build.build(root)
            data = load_json(root / citation_build.CITATION_MAP)
            # A source keeps its first number; each number links to its fact's deep link where one was located.
            self.assertEqual([(1, ["PRD-001"]), (1, ["PRD-003"]), (2, ["PRD-002"]), (1, ["PRD-001"])],
                             [(item["n"], item["facts"]) for item in data["citations"]])
            self.assertEqual("https://example.com/#:~:text=agents", data["citations"][0]["link"])
            self.assertEqual("https://example.com/", data["citations"][1]["link"])
            self.assertEqual(["exhibit-1-row-1-col-2"], [item["element_id"] for item in load_json(root / citation_build.EXHIBIT_MAP)["elements"]])
            # Filler in a body part and an uncited table row are flagged; closing sections are not.
            self.assertEqual(2, len(built["problems"]))
            self.assertIn("cites no fact", built["problems"][0])
            page = markdown_to_html((root / citation_build.BRIEF).read_text(encoding="utf-8"), "Company brief", "", data)
            self.assertIn('<sup class="cn"><a href="https://example.com/#:~:text=agents" data-cite="1">1</a></sup>', page)
            self.assertIn('data-cite="1">1</a>,<a href="https://news.example/launch" data-cite="2">2</a></sup>', page)
            self.assertNotIn("PRD-00", page)
            self.assertIn('<li id="note-2" value="2"><span class="grade">S</span> Launch post. news.example. March 1, 2026.', page)
