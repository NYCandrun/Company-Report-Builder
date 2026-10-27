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


class SourceListTests(unittest.TestCase):
    def test_repository_parts_are_separate_entries_and_recordings_list_their_timestamps(self) -> None:
        import tempfile

        from research_control import citation_build
        from research_control.io import atomic_write_jsonl, atomic_write_text, load_json
        from research_control.publication import markdown_to_html
        from research_control.validators import citations

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "01-sources/MANIFEST.csv",
                              "id,grade,title,publisher,url,date published\n"
                              "SRC-R,P,acme/agent,GitHub,https://github.com/acme/agent,\n"
                              "SRC-V,P,https://youtu.be/abcdefghijk,youtube.com,https://youtu.be/abcdefghijk,\n"
                              "SRC-W,P,,youtube.com,https://www.youtube.com/watch?v=abcdefghijk,\n")
            atomic_write_text(root / "02-facts/facts.md", "| Fact ID | Claim | Verbatim quote | Source ID | Grade |\n|---|---|---|---|---|\n" + "".join(
                f"| PRD-00{n} | c | q | {source} | P |\n" for n, source in ((1, "SRC-R"), (2, "SRC-R"), (3, "SRC-R"), (4, "SRC-V"), (5, "SRC-W"), (6, "SRC-V"))))
            sha = "c75fda00ff0e41c8ee331ae312c8a07f1967653b"
            atomic_write_jsonl(root / "tools/outputs/fact-links.jsonl", [
                {"fact_id": "PRD-001", "kind": "repository", "located": True, "anchor": f"src/run.py line 40 at {sha[:7]}",
                 "deep_link": f"https://github.com/acme/agent/blob/{sha}/src/run.py?plain=1#L40"},
                {"fact_id": "PRD-002", "kind": "repository", "located": True, "anchor": f"src/run.py line 3 at {sha[:7]}",
                 "deep_link": f"https://github.com/acme/agent/blob/{sha}/src/run.py?plain=1#L3"},
                {"fact_id": "PRD-003", "kind": "repository", "located": True, "anchor": "commit e34f6f9, README.md line 60",
                 "deep_link": "https://github.com/acme/agent/commit/e34f6f9#diff-1R60"},
                {"fact_id": "PRD-004", "kind": "recording", "located": True, "anchor": "at 00:08:13",
                 "deep_link": "https://www.youtube.com/watch?v=abcdefghijk&t=493s"},
                {"fact_id": "PRD-005", "kind": "recording", "located": True, "anchor": "at 01:02:05",
                 "deep_link": "https://www.youtube.com/watch?v=abcdefghijk&t=3725s"},
                {"fact_id": "PRD-006", "kind": "recording", "located": True, "anchor": "at 00:01:30",
                 "deep_link": "https://www.youtube.com/watch?v=abcdefghijk&t=90s"},
            ])
            atomic_write_jsonl(root / "tools/outputs/source-dates.jsonl", [])
            (root / citation_build.TITLES).parent.mkdir(parents=True, exist_ok=True)
            (root / citation_build.TITLES).write_text('{"SRC-V": {"title": "Building agents", "publisher": "Acme"}}')
            atomic_write_text(root / citation_build.BRIEF, "# Company brief\n\n## Summary\n\nA [PRD-001]. B [PRD-003]. "
                              "C [PRD-002]. D [PRD-004]. E [PRD-005, PRD-006].\n\n## Sources\n")
            built = citation_build.build(root)
            data = load_json(root / citation_build.CITATION_MAP)
            # One file is one entry (lines in file order); a commit is another; the video is one entry
            # under both of its addresses, with every cited moment in recording order.
            self.assertEqual([(1, "file src/run.py", ["line 3", "line 40"]), (2, "commit e34f6f9", ["README.md line 60"]),
                              (3, None, ["1:30", "8:13", "1:02:05"])],
                             [(note["n"], note.get("part"), [place["label"] for place in note["places"]]) for note in data["notes"]])
            self.assertEqual("Building agents", data["notes"][2]["title"])
            self.assertEqual([1, 2, 1, 3, 3], [item["n"] for item in data["citations"]])
            self.assertEqual([], citations.validate_map(data, root)["failures"])
            page = markdown_to_html((root / citation_build.BRIEF).read_text(encoding="utf-8"), "Company brief", "", data)
            self.assertIn('data-cite="3" title="8:13">3</a>', page)
            self.assertIn('<span class="part">File src/run.py</span>. Cited at <a href="https://github.com/acme/agent/blob/'
                          f'{sha}/src/run.py?plain=1#L3">line 3</a>', page)
            self.assertIn('Cited at <a href="https://www.youtube.com/watch?v=abcdefghijk&amp;t=90s">1:30</a>', page)
            self.assertEqual([], built["problems"])


class AmericanEnglishTests(unittest.TestCase):
    def test_british_spelling_and_terms_are_found_in_authored_text_only(self) -> None:
        from research_control.validators import american

        found = [word for word, _advice in american.findings(
            "The programme was labelled a bespoke job advert, and the company are prioritising colour in the "
            "financial year. Royal London's Aladdin Programme stays a name, as does \"our colour scheme\" in a quote, "
            "`organise.py`, https://example.com/catalogue, and inference-catalogue.md.")]
        self.assertEqual(["programme", "labelled", "prioritising", "colour", "bespoke", "job advert", "financial year",
                          "the company are"], sorted(found, key=lambda word: [
                              "programme", "labelled", "prioritising", "colour", "bespoke", "job advert",
                              "financial year", "the company are"].index(word.casefold())))
        self.assertEqual([], american.findings("Analyses of the program show modeled costs and a canceled catalog."))
        # A heading's first word is checked; a name that continues in capitals is not.
        self.assertEqual(["Catalogue"], [word for word, _ in american.findings("Catalogue of what the company sells")])
        self.assertEqual([], american.findings("Centre for AI Safety and the UN Development Programme"))

    def test_the_framework_itself_is_written_in_american_english(self) -> None:
        from research_control.validators import american

        repository = Path(__file__).resolve().parents[2]
        texts = [*sorted((repository / "prompts").rglob("*.md")), repository / "README.md", repository / "CLAUDE.md",
                 repository / "RESEARCH_CONSTITUTION.md"]
        problems = [f"{path.relative_to(repository)} {problem}" for path in texts for problem in american.check_file(path)]
        self.assertEqual([], problems)


class AmericanEnglishEverywhereTests(unittest.TestCase):
    def test_every_drafting_worker_and_the_engines_own_text_use_american_english(self) -> None:
        import ast
        import json

        from research_control.validators import american

        repository = Path(__file__).resolve().parents[2]
        workflow = json.loads((repository / "WORKFLOW.yaml").read_text(encoding="utf-8"))
        for profile in workflow["execution_profiles"].values():
            for task in profile.get("tasks", []):
                if (task.get("metadata") or {}).get("executor") != "runtime":
                    self.assertIn("prompts/core/runtime.md", task.get("cores", []), task["id"])
        self.assertIn("## American English", (repository / "prompts/core/runtime.md").read_text(encoding="utf-8"))
        # Text the engine writes into a run (state files, reports, notes): sentences in its string literals.
        problems = []
        for path in sorted((repository / "research_control").rglob("*.py")):
            if "tests" in path.parts or path.name == "american.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and " " in node.value.strip():
                    problems += [f"{path.name}:{node.lineno} {word}" for word, _ in american.findings(node.value)]
        self.assertEqual([], problems)

    def test_the_control_agents_recorded_edits_are_held_to_american_english(self) -> None:
        import tempfile

        from research_control.cli import _require_american
        from research_control.io import atomic_write_text

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "00-scope.md", "**Q14. Partner programme.** How does the programme work?\n")
            with self.assertRaisesRegex(ValueError, "programme"):
                _require_american(root, ["00-scope.md"])
            with self.assertRaisesRegex(ValueError, "job advert"):
                _require_american(root, [], ["Seen in a job advert"])
            atomic_write_text(root / "00-scope.md", "**Q14. Partner program.** How does the program work?\n")
            _require_american(root, ["00-scope.md"], ["Seen in a job posting"])
