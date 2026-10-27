from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.io import atomic_write_jsonl, atomic_write_text, load_json
from research_control.runtime import RuntimeStore, WorkItem
from research_control.supplement import add_supplement, supplement_added_at
from research_control.triage import (
    RETRIAGE_DECISIONS,
    RETRIAGE_REQUEST,
    TRIAGE_DECISIONS,
    add_scope_question,
    excluded_dispositions,
    triage_included,
    validate_retriage,
)


def _fixture(root: Path) -> None:
    atomic_write_text(root / "00-scope.md", "## Research questions\n\n**Q1. Product.** What is sold?\n\n## Notes for downstream phases\n\n- none\n")
    atomic_write_text(root / "01-sources/MANIFEST.csv", "id,url\nSRC-A,https://a\nSRC-B,https://b\nSRC-C,https://c\n")
    atomic_write_jsonl(root / TRIAGE_DECISIONS, [
        {"id": "SRC-A", "decision": "include", "questions": ["Q1"], "reason": "product page"},
        {"id": "SRC-B", "decision": "exclude", "questions": [], "reason": "podcast off topic"},
        {"id": "SRC-C", "decision": "exclude", "questions": [], "reason": "legal page"},
    ])


class RetriageTests(unittest.TestCase):
    def test_added_question_is_retriaged_without_removing_earlier_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            request = add_scope_question(root, "Q13", "Accounts over time", "How have accounts moved?", "talks", "owner asked")
            scope = (root / "00-scope.md").read_text(encoding="utf-8")
            self.assertLess(scope.index("**Q13. Accounts over time.**"), scope.index("## Notes for downstream phases"))
            self.assertEqual(["Q13"], load_json(root / RETRIAGE_REQUEST)["questions"])
            self.assertIn("captured sources without a re-triage decision", " ".join(validate_retriage(root)))
            atomic_write_jsonl(root / RETRIAGE_DECISIONS, [
                {"request": request["id"], "id": "SRC-A", "relevant": False, "questions": [], "reason": "no accounts"},
                {"request": request["id"], "id": "SRC-B", "relevant": True, "questions": ["Q13"], "reason": "CEO on account growth"},
                {"request": request["id"], "id": "SRC-C", "relevant": False, "questions": [], "reason": "legal"},
            ])
            self.assertEqual([], validate_retriage(root))
            # Relevance adds a source; an earlier include stands even when not relevant now.
            self.assertEqual({"SRC-A", "SRC-B"}, triage_included(root))
            self.assertEqual(["SRC-C"], [row["input_id"] for row in excluded_dispositions(root)])

    def test_relisting_a_supplemented_source_records_when(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_supplement(root, ["SRC-A"], "recaptured", at="2026-10-27T10:00:00Z")
            add_supplement(root, ["SRC-A"], "extracted again for Q13", at="2026-10-27T18:00:00Z")
            self.assertEqual({"SRC-A": "2026-10-27T18:00:00Z"}, supplement_added_at(root))


class ScopeRevisionTests(unittest.TestCase):
    def test_recorded_scope_edit_keeps_scope_and_its_readers_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            with RuntimeStore(root) as store:
                store.initialize(run_id="r", company_url="https://example.com")
                store.add_task(WorkItem(
                    task_id="scope.scope", phase="scope", task_type="scope", inputs=[], outputs=["00-scope.md"],
                    prompt_files=["p.md"],
                ))
                store.add_task(WorkItem(
                    task_id="final.brand-guide", phase="final", task_type="brand_guide",
                    inputs=[{"id": "scope_map", "path": "00-scope.md"}], outputs=["guide.html"], prompt_files=["p.md"],
                    track_input_staleness=True,
                ))
                for task_id in ("scope.scope", "final.brand-guide"):
                    store.claim("w", task_id=task_id, bypass_limits=True)
                    store.start(task_id, "w")
                    if task_id == "final.brand-guide":
                        atomic_write_text(root / "guide.html", "<html></html>")
                    store.complete(task_id, "w")
                add_scope_question(root, "Q13", "Accounts", "How have accounts moved?", "", "owner asked")
                store.record_revision("scope.add-question.q13", "scope", ["00-scope.md", "tools/lists/retriage-request.json"], "Q13", "runtime")
                store.rebaseline_inputs(["00-scope.md"], "Q13 added")
                self.assertEqual([], store.invalidate_stale())
                self.assertEqual("succeeded", store.task("final.brand-guide")["state"])


    def test_recorded_edit_of_a_finished_output_restores_rather_than_reruns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            with RuntimeStore(root) as store:
                store.initialize(run_id="r", company_url="https://example.com")
                store.add_task(WorkItem(
                    task_id="initial_synthesis.write", phase="initial_synthesis", task_type="synthesis", inputs=[],
                    outputs=["05-synthesis/direction.md"], prompt_files=["p.md"],
                ))
                store.claim("w", task_id="initial_synthesis.write", bypass_limits=True)
                store.start("initial_synthesis.write", "w")
                atomic_write_text(root / "05-synthesis/direction.md", "Under AIUC.\n")
                store.complete("initial_synthesis.write", "w")
                atomic_write_text(root / "05-synthesis/direction.md", "Under AIUC-1.\n")
                store.invalidate_stale()
                self.assertNotEqual("succeeded", store.task("initial_synthesis.write")["state"])
                result = store.record_edit(["05-synthesis/direction.md"], "initial_synthesis", "source name", "runtime")
                self.assertEqual(["initial_synthesis.write"], result["restored"])
                self.assertEqual([], store.invalidate_stale())
                self.assertEqual("succeeded", store.task("initial_synthesis.write")["state"])


if __name__ == "__main__":
    unittest.main()


class DefinitionSafeguardTests(unittest.TestCase):
    def test_a_later_revision_of_files_earlier_work_read_does_not_rerun_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            atomic_write_text(root / "WORKFLOW.yaml", '{"phases": [{"id": "verification"}, {"id": "review"}, {"id": "final"}]}')
            atomic_write_text(root / "05-synthesis/offering.md", "first draft\n")

            def finish(store: RuntimeStore, item: WorkItem, output: str, text: str) -> None:
                store.add_task(item)
                store.claim("w", task_id=item.task_id, bypass_limits=True)
                store.start(item.task_id, "w")
                atomic_write_text(root / output, text)
                store.complete(item.task_id, "w")

            reads = [{"id": "synthesis", "path": "05-synthesis/*.md"}]
            with RuntimeStore(root) as store:
                store.initialize(run_id="r", company_url="https://example.com")
                finish(store, WorkItem(task_id="verification.prepare", phase="verification", task_type="verification",
                                       inputs=reads, outputs=["checks.md"], prompt_files=["p.md"],
                                       track_input_staleness=True), "checks.md", "checked\n")
                # Finished earlier, but in a later phase: a revision under it means redoing it.
                finish(store, WorkItem(task_id="final.write-brief", phase="final", task_type="brief_writer",
                                       inputs=reads, outputs=["brief.md"], prompt_files=["p.md"],
                                       track_input_staleness=True), "brief.md", "brief\n")
                finish(store, WorkItem(task_id="review.apply-review", phase="review", task_type="fixer", inputs=reads,
                                       outputs=["05-synthesis/offering.md"], prompt_files=["p.md"], output_mode="revise"),
                       "05-synthesis/offering.md", "revised by the reviews\n")
                self.assertEqual(["final.write-brief"], store.invalidate_stale())
                self.assertEqual("succeeded", store.task("verification.prepare")["state"])
                self.assertEqual("succeeded", store.task("review.apply-review")["state"])

    def test_finished_work_keeps_its_definition_and_unfinished_work_refuses_a_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            with RuntimeStore(root) as store:
                store.initialize(run_id="r", company_url="https://example.com")
                for task_id in ("facts.file-facts", "facts.pending"):
                    store.add_task(WorkItem(task_id=task_id, phase="facts", task_type="filing", inputs=[],
                                            outputs=[f"{task_id}.md"], prompt_files=["p.md"], metadata={"single_writer": True}))
                store.claim("w", task_id="facts.file-facts", bypass_limits=True)
                store.start("facts.file-facts", "w")
                atomic_write_text(root / "facts.file-facts.md", "filed\n")
                store.complete("facts.file-facts", "w")
                # Filing became runtime work after this task finished under the agent definition.
                changed = WorkItem(task_id="facts.file-facts", phase="facts", task_type="filing", inputs=[],
                                   outputs=["facts.file-facts.md"], prompt_files=["p.md"],
                                   metadata={"single_writer": True, "executor": "runtime"})
                self.assertFalse(store.add_task(changed))
                self.assertEqual("succeeded", store.task("facts.file-facts")["state"])
                self.assertNotIn("executor", store.task("facts.file-facts")["metadata"])
                with self.assertRaisesRegex(ValueError, "while the task is unfinished"):
                    store.add_task(WorkItem(task_id="facts.pending", phase="facts", task_type="filing", inputs=[],
                                            outputs=["facts.pending.md"], prompt_files=["p.md"], metadata={"executor": "runtime"}))
