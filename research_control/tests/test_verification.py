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
            lines = ["Title: Tribe", "URL: https://example.com", *[f"filler line {n}" for n in range(200)],
                     "We build agents for enterprises.", *[f"after line {n}" for n in range(200)]]
            atomic_write_text(root / "01-sources/captures/SRC-A/content.txt", "\n".join(lines) + "\n")
            report = verification.prepare(root)
            self.assertEqual(3, report["cited_facts"])
            # Each packet carries the located quote with its context, not just the capture's path.
            excerpt = verification.load_json(root / verification.PACKET_DIR / "PRD-001.json")["excerpt"]
            self.assertEqual((True, 203), (excerpt["located"], excerpt["line"]))
            self.assertIn("We build agents for enterprises.", excerpt["text"])
            self.assertLess(len(excerpt["text"]), 4_000)
            self.assertEqual("Title: Tribe", excerpt["head"][0])
            self.assertFalse(verification.load_json(root / verification.PACKET_DIR / "PRD-003.json")["excerpt"]["located"])
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
            # The brief and diagrams work from one table of the cited facts.
            rows = (root / verification.CITED_ROWS).read_text(encoding="utf-8")
            self.assertIn("| PRD-001 | confirmed | Tribe builds agents. | We build agents | SRC-A |", rows)
            self.assertNotIn("PRD-004", rows)

            # Re-preparing after a change re-verifies only the changed fact.
            atomic_write_text(root / "02-facts/q01.md", FACTS.replace("Tribe has a network.", "Tribe has a talent network."))
            report = verification.prepare(root)
            self.assertEqual(2, report["reused_verdicts"])
            self.assertEqual([["PRD-003"]], verification.shards(root))
            part = f"{verification.PART_DIR}/{verification.shard_id(['PRD-003'])}.jsonl"
            atomic_write_jsonl(root / part, [{
                "fact_id": "PRD-003", "verdict": "corrected", "reason": "narrower",
                "evidence_paths": ["x"], "corrected_claim": "Tribe has a network of engineers.",
            }])
            result = verification.reduce_verdicts(root, [part])
            self.assertEqual({"confirmed": 2, "corrected": 1}, {key: result[key] for key in ("confirmed", "corrected")})


if __name__ == "__main__":
    unittest.main()


class WithdrawnFactTests(unittest.TestCase):
    def test_withdrawn_facts_are_not_quote_checked_and_cannot_be_cited(self) -> None:
        from research_control import checks
        from research_control.io import atomic_write_json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "02-facts/q01.md", FACTS)
            # A standard's name shaped like an ID (AIUC-1) is not a citation; an unknown PRD ID is.
            atomic_write_text(root / "05-synthesis/offering.md", "Network [PRD-003] under AIUC-1.\n")
            self.assertEqual([], checks._validate_synthesis_ids(root, "synthesis_fact_ids").get("failures", []))
            atomic_write_text(root / "05-synthesis/direction.md", "Plan [PRD-099].\n")
            self.assertIn("unknown fact ID PRD-099", checks._validate_synthesis_ids(root, "synthesis_fact_ids")["failures"][0])
            (root / "05-synthesis/direction.md").unlink()
            atomic_write_json(root / "tools/lists/withdrawn-facts.json", {"facts": {"PRD-003": "capture omission since fixed"}})
            failures = checks._validate_synthesis_ids(root, "synthesis_fact_ids")["failures"]
            self.assertIn("cites withdrawn fact PRD-003", failures[0])
