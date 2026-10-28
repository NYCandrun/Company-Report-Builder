from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS
from research_control.validators.citations import validate_map


class CitationTests(unittest.TestCase):
    def valid(self) -> dict:
        return {
            "sources": {"S1": {"url": "https://one.example/page"}, "S2": {"url": "https://two.example/page"}},
            "facts": {"F1": {"source_ids": ["S1"]}, "F2": {"source_ids": ["S2"]}},
            "notes": [
                {"n": 1, "source_id": "S1", "url": "https://one.example/page"},
                {"n": 2, "source_id": "S2", "url": "https://two.example/page"},
            ],
            "citations": [{"n": 1, "facts": ["F1"]}, {"n": 2, "facts": ["F2"]}, {"n": 1, "facts": ["F1"]}],
            "markdown_citations": [{"facts": ["F1"]}, {"facts": ["F2"]}, {"facts": ["F1"]}],
        }

    def check(self, data: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "map.json").write_text("fixture", encoding="utf-8")
            return validate_map(data, root, "map.json")

    def test_valid_map_passes(self) -> None:
        self.assertEqual(PASS, self.check(self.valid())["status"])

    def test_six_planted_citation_errors_are_caught(self) -> None:
        mutations = []
        duplicate_number = self.valid()
        duplicate_number["notes"].append({"n": 3, "source_id": "S1", "url": "https://three.example"})
        mutations.append(duplicate_number)
        removed_source = self.valid()
        removed_source["notes"][0].pop("source_id")
        mutations.append(removed_source)
        out_of_order = self.valid()
        out_of_order["citations"][0]["n"] = 2
        mutations.append(out_of_order)
        swapped = self.valid()
        swapped["citations"][0]["facts"] = ["F2"]
        swapped["citations"][1]["facts"] = ["F1"]
        mutations.append(swapped)
        wrong_page = self.valid()
        wrong_page["notes"][0]["url"] = "https://wrong.example/page"
        mutations.append(wrong_page)
        duplicate_page = self.valid()
        duplicate_page["notes"][1]["url"] = "https://one.example/page"
        mutations.append(duplicate_page)
        original = copy.deepcopy(self.valid())
        for index, mutation in enumerate(mutations, 1):
            with self.subTest(error=index):
                self.assertEqual(FAIL, self.check(mutation)["status"])
        self.assertEqual(original, self.valid())


if __name__ == "__main__":
    unittest.main()
