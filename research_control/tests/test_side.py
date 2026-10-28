from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_control import side
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text, load_json, load_jsonl
from research_control.runtime import RuntimeStore, WorkItem

TEMPLATE = Path(__file__).resolve().parents[2]
SECTION = "## Market, positioning, and competitors"


def _main_run(root: Path) -> None:
    shutil.copytree(TEMPLATE / "prompts", root / "prompts")
    atomic_write_text(root / "00-scope.md", (
        "# Scope\n\n## Research questions\n\n"
        "**Q1. Product.** What is sold?\n\n"
        "**Q7. Market and competitors.** Which firms compete, and how large is the market?\n\n"
        "## Notes for downstream phases\n\n- Rival is a direct competitor.\n"))
    atomic_write_text(root / "01-sources/MANIFEST.csv", (
        "id,grade,title,publisher,url,date published,date last modified,date captured,local file,method,notes\n"
        "SRC-A,S,Rival site,rival.example,https://rival.example/,,,2026-10-27,01-sources/captures/SRC-A/content.txt,capture,\n"
        "SRC-T,P,Tribe site,tribe.example,https://tribe.example/,,,2026-10-27,01-sources/captures/SRC-T/content.txt,capture,\n"))
    atomic_write_text(root / "01-sources/captures/SRC-A/content.txt", "Rival deploys engineers into banks.\nRival raised $20 million in 2026.\n")
    atomic_write_text(root / "01-sources/captures/SRC-T/content.txt", "Tribe builds agents.\n")
    atomic_write_text(root / "tools/extracts/canonical/SRC-A.txt", "--- SOURCE FILE: 01-sources/captures/SRC-A/content.txt ---\nRival deploys engineers into banks.\nRival raised $20 million in 2026.\n")
    atomic_write_text(root / "02-facts/q01-product.md", "# Q1\n\n| Fact ID | Claim | Verbatim quote | Source ID | Location | Source date | Grade | Topics | About | Said by | Verdict | Candidate | Notes | Conflict group | Cross-source repeats |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n| PRD-001 | Tribe builds agents | Tribe builds agents | SRC-T | p1 | 2026-10-27 | P | Q1 | Tribe | Tribe | filed | CAND-X-1 |  |  |  |\n")
    atomic_write_text(root / "02-facts/q07-market-and-competitors.md", "# Q7\n\n| Fact ID | Claim | Verbatim quote | Source ID | Location | Source date | Grade | Topics | About | Said by | Verdict | Candidate | Notes | Conflict group | Cross-source repeats |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n| CMP-001 | Rival serves banks | engineers into banks | SRC-A | p1 | 2026-10-27 | S | Q7 | Rival | Rival | filed | CAND-X-2 |  |  |  |\n")
    atomic_write_jsonl(root / "tools/outputs/verification-verdicts.jsonl", [
        {"fact_id": "PRD-001", "verdict": "confirmed", "reason": "quoted", "evidence_paths": ["x"]},
        {"fact_id": "CMP-001", "verdict": "confirmed", "reason": "quoted", "evidence_paths": ["x"]}])
    atomic_write_jsonl(root / "tools/outputs/fact-links.jsonl", [
        {"fact_id": "PRD-001", "source_id": "SRC-T", "url": "https://tribe.example/", "deep_link": "https://tribe.example/#:~:text=Tribe", "anchor": "quoted text", "kind": "page", "located": True},
        {"fact_id": "CMP-001", "source_id": "SRC-A", "url": "https://rival.example/", "deep_link": "https://rival.example/#:~:text=banks", "anchor": "quoted text", "kind": "page", "located": True}])
    atomic_write_jsonl(root / "tools/outputs/source-dates.jsonl", [])
    atomic_write_text(root / "05-synthesis/competitors.md", "# Competitors\n\nRival serves banks [CMP-001].\n")
    atomic_write_text(root / "05-synthesis/company-brief.md", (
        "# Company brief\n\n## Executive summary\n\nTribe builds agents [PRD-001].\n\n"
        f"{SECTION}\n\n### Competitors\n\nRival serves banks [CMP-001].\n\n"
        "## What it sells\n\nAgents [PRD-001].\n\n## Sources\n"))
    atomic_write_json(root / "tools/lists/deferred-slices.json", {"slices": {
        "SRC-A": {"sha256": "x", "reason": "over the extraction token budget (1)", "by": "budget", "at": "2026-10-27T00:00:00Z"}}})
    atomic_write_text(root / "WORKFLOW.yaml", '{"phases": [{"id": "facts"}, {"id": "final"}]}')
    atomic_write_text(root / "RUN_HISTORY.md", "# History\n")


class SideRunTests(unittest.TestCase):
    def test_a_side_run_drafts_files_verifies_renders_and_merges_without_the_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _main_run(root)
            with RuntimeStore(root) as store:
                store.initialize(run_id="r", company_url="https://tribe.example")
                store.add_task(WorkItem(task_id="final.write-brief", phase="final", task_type="brief_writer", inputs=[],
                                        outputs=["05-synthesis/company-brief.md"], prompt_files=["p.md"]))
                store.claim("w", task_id="final.write-brief", bypass_limits=True)
                store.start("final.write-brief", "w")
                store.complete("final.write-brief", "w")
            # 1. Lay out: the held source, one extraction brief, the fact store copied for numbering.
            laid = side.new(root, "market", ["Q7"], section=SECTION)
            self.assertEqual(["SRC-A"], load_json(root / side.SIDE_DIR / "market/side.json")["sources"])
            folder = root / side.SIDE_DIR / "market"
            brief = Path(laid["start_workers"][0]["read"]).read_text(encoding="utf-8")
            self.assertIn("Rival raised $20 million", brief)
            self.assertLess(brief.index("## The source text"), brief.index("## The task's instructions"))
            self.assertIn("American English", brief)
            batch = laid["start_workers"][0]["read"].rsplit("/", 1)[-1].split(".")[0]
            task = load_json(folder / "extract" / f"{batch}.json")
            self.assertIn("not written yet", side.check(root, "market", "extract")["problems"][0])
            # 2. A worker drafts one new fact and one repeat of a filed fact.
            prefix = task["metadata"]["candidate_id_prefix"]
            atomic_write_jsonl(folder / task["metadata"]["candidate_part"], [
                {"candidate_id": f"{prefix}0001", "topic": "Q7 funding", "claim": "Rival raised $20 million in 2026",
                 "quote": "Rival raised $20 million in 2026.", "source_id": "SRC-A", "location": "p1", "source_date": "2026-10-27",
                 "grade": "S", "about": "Rival", "said_by": "Rival", "notes": ""},
                {"candidate_id": f"{prefix}0002", "topic": "Q7 customers", "claim": "Rival serves banks",
                 "quote": "engineers into banks", "source_id": "SRC-A", "location": "p1", "source_date": "2026-10-27",
                 "grade": "S", "about": "Rival", "said_by": "Rival", "notes": ""}])
            atomic_write_jsonl(folder / task["metadata"]["disposition_part"], [
                {"assignment_id": task["task_id"], "input_id": "SRC-A", "source_id": "SRC-A", "disposition": "completed",
                 "reason": "read", "evidence_paths": [task["metadata"]["candidate_part"]], "output_ids": [f"{prefix}0001"]}])
            self.assertEqual("clean", side.check(root, "market", "extract")["status"])
            filed = side.file(root, "market")
            self.assertEqual(1, filed["new_facts"])
            new_fact = (folder / "new-facts.txt").read_text(encoding="utf-8").split()[0]
            self.assertEqual("CMP-002", new_fact)
            self.assertNotIn("CMP-002", (root / "02-facts/q07-market-and-competitors.md").read_text(encoding="utf-8"))
            writing = (folder / "write/brief.md").read_text(encoding="utf-8")
            self.assertIn("CMP-002", writing)
            self.assertIn("Rival is a direct competitor", writing)
            # 3. The writer updates the section; its check builds the citations.
            atomic_write_text(folder / "05-synthesis/company-brief.md",
                              f"{SECTION}\n\n### Competitors\n\nRival serves banks [CMP-001] and raised $20 million in 2026 [CMP-002].\n\n## Sources\n")
            atomic_write_text(folder / "05-synthesis/competitors.md", "# Competitors\n\nRival serves banks [CMP-001]; it raised $20 million in 2026 [CMP-002].\n")
            self.assertEqual([], side.check(root, "market", "write")["problems"])
            # 4. Only the newly cited fact is verified, in a sandbox.
            prepared = side.verify(root, "market")
            self.assertEqual(1, prepared["facts"])
            with self.assertRaisesRegex(ValueError, "no verdict yet"):
                side.merge(root, "market")
            atomic_write_jsonl(folder / "tools/outputs/verification-sandbox/side/verdicts.jsonl", [
                {"fact_id": "CMP-002", "verdict": "confirmed", "reason": "the quote states it", "evidence_paths": ["x"]}])
            self.assertEqual("clean", side.check(root, "market", "verify")["status"])
            side.verify(root, "market", merge=True)
            # 5. The section renders on its own with linked citations.
            rendered = side.render(root, "market")
            page = (folder / rendered["html"]).read_text(encoding="utf-8")
            self.assertIn('data-cite="1"', page)
            self.assertNotIn("CMP-00", page)
            # 6. The merge records everything in the main run; nothing reruns.
            merged = side.merge(root, "market")
            table = (root / "02-facts/q07-market-and-competitors.md").read_text(encoding="utf-8")
            self.assertIn("| CMP-002 |", table)
            main_brief = (root / "05-synthesis/company-brief.md").read_text(encoding="utf-8")
            self.assertIn("raised $20 million in 2026 [CMP-002]", main_brief)
            self.assertIn("## What it sells\n\nAgents [PRD-001].", main_brief)
            self.assertEqual(1, main_brief.count("## Sources"))
            self.assertIn("CMP-002", {row["fact_id"] for row in load_jsonl(root / "tools/outputs/fact-links.jsonl")})
            self.assertIn("CMP-002", {row["fact_id"] for row in load_jsonl(root / "tools/outputs/verification-verdicts-added.jsonl")})
            self.assertEqual(task["inputs"][0]["sha256"], next(iter(side.extracted_text(root))))
            self.assertIn("05-synthesis/company-brief.md", merged["touched"])
            with RuntimeStore(root) as store:
                self.assertEqual("succeeded", store.task("final.write-brief")["state"])
                self.assertEqual([], store.invalidate_stale())
            self.assertEqual({"new", "file", "verify", "render", "merge"}, set(side.status(root, "market")["steps"]))


class SideSearchTests(unittest.TestCase):
    def test_a_search_side_run_lists_pages_and_refuses_known_or_malformed_ones(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _main_run(root)
            laid = side.search(root, "deeper", ["Q7"], section=SECTION, firms=["Rival"])
            brief = Path(laid["start_workers"][0]["read"]).read_text(encoding="utf-8")
            self.assertIn("- Rival", brief)
            self.assertIn("https://rival.example/", brief)
            self.assertIn("not written yet", side.check(root, "deeper", "search")["problems"][0])
            atomic_write_jsonl(root / side.SIDE_DIR / "deeper" / side.SEARCH_LIST, [
                {"url": "https://rival.example/", "grade": "P", "title": "Rival", "publisher": "Rival", "why": "home", "question": "Q7"},
                {"url": "https://rival.example/case-studies", "grade": "P", "title": "Cases", "publisher": "Rival", "why": "named customers", "question": "Q7"},
                {"url": "https://rival.example/careers", "grade": "P", "title": "Careers", "publisher": "Rival", "why": "job adverts", "question": "Q7"}])
            problems = side.check(root, "deeper", "search")["problems"]
            self.assertEqual(2, len(problems))
            self.assertIn("already in the run's source list", problems[0])
            self.assertIn("job advert", problems[1])
