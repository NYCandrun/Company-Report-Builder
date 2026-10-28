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
    def test_source_changes_invalidate_verdicts_until_fresh_verification(self) -> None:
        for change in ("context", "delete", "extra-file", "new-transcript"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                atomic_write_text(root / "02-facts/q01.md", FACTS)
                atomic_write_text(root / "05-synthesis/offering.md", "Agents [PRD-001, PRD-002]; network [PRD-003].\n")
                capture = root / "01-sources/captures/SRC-A/content.txt"
                text = "We build agents. We sell services.\n" + "Unchanged background.\n" * 300
                atomic_write_text(capture, text + "This is current.\n")
                atomic_write_text(root / "01-sources/captures/SRC-B/content.txt", "Our network.\n")
                extra = root / "01-sources/captures/SRC-A/appendix.txt"
                atomic_write_text(extra, "Supporting context.\n")
                # content.txt is intentionally omitted: source_excerpt still reads it.
                atomic_write_text(root / "01-sources/MANIFEST.csv", "id,url,grade,local file\n"
                                  "SRC-A,https://example.com,P,01-sources/captures/SRC-A/appendix.txt\n")
                verification.prepare(root)
                part = f"{verification.PART_DIR}/initial.jsonl"
                atomic_write_jsonl(root / part, [
                    {"fact_id": fact_id, "verdict": "confirmed", "reason": "supported",
                     "evidence_paths": ["01-sources/captures/SRC-A/content.txt"]}
                    for fact_id in ("PRD-001", "PRD-002", "PRD-003")
                ])
                verification.reduce_verdicts(root, [part])
                self.assertEqual(3, verification.prepare(root)["reused_verdicts"])
                self.assertEqual([], verification.shards(root))

                if change == "context":
                    # The quote and nearby excerpt remain unchanged.
                    atomic_write_text(capture, text + "This is historical, not current.\n")
                elif change == "delete":
                    capture.unlink()
                elif change == "extra-file":
                    atomic_write_text(extra, "Corrected supporting context.\n")
                else:
                    atomic_write_text(capture.with_name("transcript.txt"), "We build agents, but only in a demo.\n")
                for _ in range(2):
                    self.assertEqual(1, verification.prepare(root)["reused_verdicts"])
                    self.assertEqual([["PRD-001", "PRD-002"]], verification.shards(root))
                # Repeated preparation must not give the old verdict a new fingerprint.
                fresh = f"{verification.PART_DIR}/fresh.jsonl"
                atomic_write_jsonl(root / fresh, [
                    {"fact_id": fact_id, "verdict": "unsupported", "reason": "context changed",
                     "evidence_paths": ["01-sources/captures/SRC-A/appendix.txt"]}
                    for fact_id in ("PRD-001", "PRD-002")
                ])
                verification.reduce_verdicts(root, [fresh])
                self.assertEqual(3, verification.prepare(root)["reused_verdicts"])
                verdicts = {row["fact_id"]: row["verdict"] for row in load_jsonl(root / verification.REUSED)}
                self.assertEqual("unsupported", verdicts["PRD-001"])

    def test_unbound_legacy_verdicts_are_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "02-facts/q01.md", FACTS)
            atomic_write_text(root / "05-synthesis/offering.md", "Agents [PRD-001].\n")
            atomic_write_text(root / "01-sources/captures/SRC-A/content.txt", "We build agents.\n")
            verification.prepare(root)
            row = {"fact_id": "PRD-001", "verdict": "confirmed", "reason": "old verification",
                   "evidence_paths": ["01-sources/captures/SRC-A/content.txt"]}
            for path in (verification.VERDICTS, verification.REUSED, verification.ADDED,
                         f"{verification.PART_DIR}/old.jsonl"):
                atomic_write_jsonl(root / path, [row])
            for _ in range(2):
                self.assertEqual(0, verification.prepare(root)["reused_verdicts"])
                self.assertEqual([["PRD-001"]], verification.shards(root))

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


class SandboxVerificationTests(unittest.TestCase):
    def test_only_facts_cited_after_verification_are_judged_and_added(self) -> None:
        import tempfile

        from research_control import checks, verification_sandbox
        from research_control.io import atomic_write_jsonl, atomic_write_text, load_jsonl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import shutil

            shutil.copytree(Path(__file__).resolve().parents[2] / "prompts", root / "prompts")
            atomic_write_text(root / "01-sources/MANIFEST.csv", "id,grade,title,publisher,url,date published,local file\n"
                              "SRC-A,S,Rival page,rival.example,https://rival.example/,,01-sources/captures/SRC-A/content.txt\n")
            atomic_write_text(root / "01-sources/captures/SRC-A/content.txt", "Rival builds agents for banks.\n")
            atomic_write_text(root / "02-facts/facts.md", "| Fact ID | Claim | Verbatim quote | Source ID | Grade |\n|---|---|---|---|---|\n"
                              "| CMP-001 | Rival builds agents | Rival builds agents | SRC-A | S |\n"
                              "| CMP-002 | Rival serves banks | agents for banks | SRC-A | S |\n")
            atomic_write_jsonl(root / verification.VERDICTS, [
                {"fact_id": "CMP-001", "verdict": "confirmed", "reason": "quoted", "evidence_paths": ["x"]}])
            atomic_write_text(root / "05-synthesis/competitors.md", "Rival builds agents [CMP-001] for banks [CMP-002].\n")
            prepared = verification_sandbox.prepare(root, "market")
            self.assertEqual(1, prepared["facts"])
            self.assertIn("CMP-002", (root / prepared["brief"]).read_text(encoding="utf-8"))
            self.assertIn("verdicts.jsonl is missing", " ".join(verification_sandbox.check(root, "market")))
            atomic_write_jsonl(root / verification_sandbox.SANDBOX / "market/verdicts.jsonl", [
                {"fact_id": "CMP-002", "verdict": "confirmed", "reason": "the quote names banks", "evidence_paths": ["y"]}])
            self.assertEqual([], verification_sandbox.check(root, "market"))
            verification_sandbox.merge(root, "market")
            # The phase's verdict file is untouched; every check now sees both.
            self.assertEqual(["CMP-001"], [row["fact_id"] for row in load_jsonl(root / verification.VERDICTS)])
            self.assertEqual({"CMP-001", "CMP-002"}, {row["fact_id"] for row in checks._verification_records(root)})
            self.assertEqual([], verification_sandbox.unverified(root))
            self.assertIn("CMP-002", (root / verification_sandbox.ADDED_ROWS).read_text(encoding="utf-8"))
