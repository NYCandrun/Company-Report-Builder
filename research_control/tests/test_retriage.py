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


if __name__ == "__main__":
    unittest.main()
