from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.io import atomic_write_jsonl, atomic_write_text, load_json
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


if __name__ == "__main__":
    unittest.main()
