from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import verification
from research_control.io import atomic_write_jsonl, atomic_write_text, load_jsonl


FACTS = """# Q1

| Fact ID | Claim | Verbatim quote | Source ID | Location | Source date | Grade |
|---|---|---|---|---|---|---|
| PRD-001 | Tribe builds agents. | We build agents | SRC-A | line 1 | 2026-01-01 | P |
| PRD-002 | Tribe sells services. | We sell services | SRC-A | line 2 | 2026-01-01 | P |
| PRD-003 | Tribe has a network. | Our network | SRC-B | line 4 | 2025-05-01 | S |
| PRD-004 | Uncited. | Not cited | SRC-B | line 9 | 2025-05-01 | S |
"""


class VerificationShardTests(unittest.TestCase):
    def test_cited_facts_are_sharded_by_source_and_merged_in_cited_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "02-facts/q01.md", FACTS)
            atomic_write_text(root / "05-synthesis/offering.md", "Network [PRD-003]. Agents [PRD-001].\n")
            atomic_write_text(root / "05-synthesis/product-map.md", "Services [PRD-002]; agents [PRD-001].\n")
            report = verification.prepare(root)
            self.assertEqual(3, report["cited_facts"])
            self.assertEqual(
                ["PRD-003", "PRD-001", "PRD-002"],
                (root / verification.CITED_LIST).read_text(encoding="utf-8").split(),
            )
            original = verification.SHARD_FACTS
            verification.SHARD_FACTS = 2
            try:
                shards = verification.shards(root)
            finally:
                verification.SHARD_FACTS = original
            # A source's facts stay in one shard.
            self.assertEqual([["PRD-001", "PRD-002"], ["PRD-003"]], shards)
            parts = []
            for fact_ids in shards:
                part = f"{verification.PART_DIR}/{verification.shard_id(fact_ids)}.jsonl"
                atomic_write_jsonl(root / part, [
                    {"fact_id": fact_id, "verdict": "confirmed", "reason": "quote at location",
                     "evidence_paths": ["01-sources/captures/x/content.txt"]}
                    for fact_id in fact_ids
                ])
                self.assertEqual([], verification.validate_part(root, part, fact_ids))
                parts.append(part)
            self.assertIn("no verdict for: PRD-002", verification.validate_part(root, parts[1], ["PRD-003", "PRD-002"])[0])
            result = verification.reduce_verdicts(root, parts)
            self.assertEqual(3, result["confirmed"])
            merged = [row["fact_id"] for row in load_jsonl(root / verification.VERDICTS)]
            self.assertEqual(["PRD-003", "PRD-001", "PRD-002"], merged)
            self.assertIn("| confirmed | 3 |", (root / verification.REPORT).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
