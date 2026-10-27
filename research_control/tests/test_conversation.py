from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import conversation
from research_control.io import load_json


class ConversationLogTests(unittest.TestCase):
    def test_parts_are_logged_redacted_then_replaced_by_one_checked_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text('{"text": "start"}\n{"text": "token hf_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"}\n', encoding="utf-8")
            self.assertEqual(2, conversation.snapshot(root, transcript)["new_lines"])
            with transcript.open("a", encoding="utf-8") as handle:
                handle.write('{"text": "steering from the user"}\n')
            self.assertEqual(1, conversation.snapshot(root, transcript)["new_lines"])
            self.assertEqual(0, conversation.snapshot(root, transcript)["new_lines"])
            folder = root / conversation.FOLDER
            self.assertEqual(["part-0001.jsonl", "part-0002.jsonl"], sorted(path.name for path in folder.glob("part-*")))
            self.assertNotIn("hf_ABC", (folder / "part-0001.jsonl").read_text(encoding="utf-8"))
            result = conversation.finalize(root, transcript)
            self.assertEqual(("finalized", ["conversation.jsonl"], 3), (result["status"], result["files"], result["lines"]))
            self.assertEqual([], list(folder.glob("part-*")))
            text = (folder / "conversation.jsonl").read_text(encoding="utf-8")
            self.assertIn("steering from the user", text)
            self.assertIn("[removed Hugging Face token]", text)
            # Questions after the run are not added.
            with transcript.open("a", encoding="utf-8") as handle:
                handle.write('{"text": "a follow-up question"}\n')
            self.assertEqual("finalized", conversation.snapshot(root, transcript)["status"])
            self.assertNotIn("follow-up", (folder / "conversation.jsonl").read_text(encoding="utf-8"))
            self.assertIn("finalized", load_json(root / conversation.STATE))

    def test_parts_are_kept_when_the_full_transcript_does_not_contain_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text('{"text": "first"}\n', encoding="utf-8")
            conversation.snapshot(root, transcript)
            transcript.write_text('{"text": "rewritten"}\n', encoding="utf-8")
            result = conversation.finalize(root, transcript)
            self.assertEqual("parts kept", result["status"])
            self.assertTrue((root / conversation.FOLDER / "part-0001.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
