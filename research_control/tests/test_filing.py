from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.filing import DISPOSITIONS, SPOT_SAMPLE, file_candidates, scope_questions
from research_control.io import atomic_write_jsonl, atomic_write_text, load_json, load_jsonl
from research_control.supplement import write_claim_digests
from research_control.validators.facts import load_fact_tables

SCOPE = """# Scope

**Q1. Product and architecture.** What does it deliver?

**Q2. Accounts and engagements over time.** Who buys?
"""
HEADER = ("| Fact ID | Claim | Verbatim quote | Source ID | Location | Source date | Grade | Topics | About | Said by | "
          "Verdict | Candidate | Notes | Conflict group | Cross-source repeats |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def candidate(number: int, quote: str, claim: str, topic: str = "Q1 product", **extra: str) -> dict[str, str]:
    return {"candidate_id": f"CAND-AAA-{number:03d}", "source_id": "SRC-1", "quote": quote, "claim": claim,
            "topic": topic, "location": "content.txt line 3", "source_date": "2026-05-01", "grade": "P",
            "about": "Tribe AI", "said_by": "Tribe AI", "notes": "Shipped.", **extra}


class RuntimeFilingTests(unittest.TestCase):
    def test_candidates_are_filed_merged_and_rejected_without_a_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "00-scope.md", SCOPE)
            atomic_write_text(root / "01-sources/captures/SRC-1/content.txt",
                              "Header\nWe build agents for enterprise teams every single day.\nWe can sell workshops to buyers.\n"
                              "Our engagements with buyers run for months.\n")
            atomic_write_text(root / "01-sources/MANIFEST.csv",
                              "id,url,grade,local file\nSRC-1,https://example.com,P,01-sources/captures/SRC-1/content.txt\n")
            atomic_write_text(root / "02-facts/q01-product-architecture.md", "# Q1\n\n" + HEADER
                              + "| PRD-001 | Tribe builds agents. | We build agents for enterprise teams every single day. | SRC-1 | "
                                "line 2 | 2026-05-01 | P | Q1 | Tribe AI | Tribe AI | filed | CAND-OLD-001 | | | |\n")
            atomic_write_jsonl(root / "tools/candidates/all.jsonl", [
                candidate(1, "We build agents for enterprise teams every single day.", "Tribe builds agents."),
                candidate(2, "We build agents for enterprise teams every single", "Tribe builds agents for enterprises."),
                candidate(3, "We can sell workshops to buyers.", "Tribe sells workshops.", topic="Q2 accounts"),
                candidate(4, "We never said this at all anywhere.", "Invented."),
                candidate(5, "We can sell workshops to buyers.", "Tribe sells workshops.", duplicate_of="CAND-AAA-003"),
                candidate(6, "Our engagements with buyers run for months.", "Accounts last months.", topic="engagement history"),
            ])
            self.assertEqual({1: "Product and architecture", 2: "Accounts and engagements over time"}, scope_questions(root))
            result = file_candidates(root)
            self.assertEqual((3, 2), (result["filed"], result["exact duplicates"]))
            self.assertEqual(1, result["rejected: quote not in source"])
            rows = {row["fact_id"]: row for row in load_fact_tables(sorted((root / "02-facts").glob("*.md")))}
            # A new question gets its own table and prefix; the existing row is untouched.
            self.assertIn("ACC-001", rows)
            self.assertIn("script-flagged overstatement-risk (quote terms: can)", rows["ACC-001"]["verdict"])
            self.assertEqual("Tribe builds agents.", rows["PRD-001"]["claim"])
            dispositions = {row["input_id"]: row for row in load_jsonl(root / DISPOSITIONS)}
            self.assertEqual(6, len(dispositions))
            self.assertEqual(["ACC-001"], dispositions["CAND-AAA-005"]["output_ids"])
            self.assertEqual(["PRD-002"], dispositions["CAND-AAA-002"]["output_ids"])
            sample = load_json(root / SPOT_SAMPLE)
            self.assertIn("excerpt", sample["filed"][0])
            # Filing again changes nothing: every candidate already has its disposition.
            self.assertEqual(0, file_candidates(root)["processed"])
            # The runtime's topic digests give synthesis one line per fact.
            counts = write_claim_digests(root, "tools/digests")
            self.assertEqual({"q01-product-architecture": 2, "q02-accounts-engagements": 2}, counts)
            # A topic without a question number is filed by the words it shares with a question.
            self.assertIn("Q2", rows["ACC-002"]["topics"] if "topics" in rows["ACC-002"] else str(rows["ACC-002"]))
            self.assertIn("ACC-001 · 2026-05-01 · P · SRC-1 · Tribe AI · Tribe sells workshops.",
                          (root / "tools/digests/q02-accounts-engagements.md").read_text(encoding="utf-8"))


    def test_distinct_claims_and_quotes_survive_duplicate_hints_and_repeated_filing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quote = "We employ ten engineers and earn two million dollars annually."
            shorter = "We employ ten engineers and earn two million dollars"
            atomic_write_text(root / "00-scope.md", SCOPE)
            atomic_write_text(root / "01-sources/captures/SRC-1/content.txt", quote)
            atomic_write_text(root / "01-sources/MANIFEST.csv",
                              "id,url,grade,local file\nSRC-1,https://example.com,P,01-sources/captures/SRC-1/content.txt\n")
            candidates = [
                candidate(1, quote, "The company employs ten engineers."),
                candidate(2, quote, "The company earns two million dollars annually.", duplicate_of="CAND-AAA-001"),
                candidate(3, shorter, "The company earns two million dollars.", duplicate_of="CAND-AAA-001"),
                candidate(4, shorter, "The company employs ten engineers."),
                candidate(5, quote.upper(), "  The company employs  TEN engineers. ", duplicate_of="missing"),
            ]
            atomic_write_jsonl(root / "tools/candidates/all.jsonl", candidates)
            result = file_candidates(root)
            self.assertEqual((4, 1), (result["filed"], result["exact duplicates"]))
            paths = sorted((root / "02-facts").glob("*.md"))
            rows = load_fact_tables(paths)
            self.assertEqual([item["claim"] for item in candidates[:4]], [row["claim"] for row in rows])
            dispositions = {row["input_id"]: row for row in load_jsonl(root / DISPOSITIONS)}
            self.assertEqual(dispositions["CAND-AAA-001"]["output_ids"], dispositions["CAND-AAA-005"]["output_ids"])
            before = {path: path.read_bytes() for path in [*paths, root / DISPOSITIONS]}
            self.assertEqual(0, file_candidates(root)["processed"])
            self.assertEqual(before, {path: path.read_bytes() for path in before})
            # A later extraction with another ID also resolves against existing rows.
            candidates.append(candidate(6, quote, "The company earns two million dollars annually."))
            atomic_write_jsonl(root / "tools/candidates/all.jsonl", candidates)
            self.assertEqual(1, file_candidates(root)["exact duplicates"])
            self.assertEqual(4, len(load_fact_tables(paths)))


if __name__ == "__main__":
    unittest.main()
