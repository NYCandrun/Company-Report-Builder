from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import conversation
from research_control.io import load_json


class ConversationLogTests(unittest.TestCase):
    def test_new_parts_are_added_then_replaced_by_one_checked_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text('{"text": "start"}\n{"text": "token hf_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"}\n', encoding="utf-8")
            self.assertEqual(2, conversation.snapshot(root, transcript, "start of capture")["new_lines"])
            with transcript.open("a", encoding="utf-8") as handle:
                handle.write('{"text": "steering from the user"}\n')
            self.assertEqual(1, conversation.snapshot(root, transcript, "start of facts")["new_lines"])
            self.assertEqual(0, conversation.snapshot(root, transcript, "save")["new_lines"])
            folder = root / conversation.FOLDER
            self.assertEqual(["part-0001.jsonl", "part-0002.jsonl"], sorted(path.name for path in folder.glob("part-*")))
            self.assertNotIn("hf_ABC", (folder / "part-0001.jsonl").read_text(encoding="utf-8"))
            conversation.record_push(root, "start of facts", "abc123", True)
            self.assertEqual("start of facts", conversation.state(root)["last_verified"])
            result = conversation.finalize(root, transcript)
            self.assertEqual(("finalized", ["conversation.jsonl"], 3), (result["status"], result["files"], result["lines"]))
            self.assertEqual(["conversation.jsonl", "log-state.json"], sorted(path.name for path in folder.iterdir()))
            text = (folder / "conversation.jsonl").read_text(encoding="utf-8")
            self.assertIn("steering from the user", text)
            self.assertIn("[removed Hugging Face token]", text)
            self.assertEqual(2, load_json(root / conversation.STATE)["parts_checked"])
            # Questions after the run are not added.
            with transcript.open("a", encoding="utf-8") as handle:
                handle.write('{"text": "a follow-up question"}\n')
            self.assertEqual("finalized", conversation.snapshot(root, transcript)["status"])
            self.assertNotIn("follow-up", (folder / "conversation.jsonl").read_text(encoding="utf-8"))

    def test_earlier_parts_are_kept_when_the_full_conversation_does_not_contain_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text('{"text": "first"}\n', encoding="utf-8")
            conversation.snapshot(root, transcript, "start of capture")
            transcript.write_text('{"text": "rewritten"}\n{"text": "more"}\n', encoding="utf-8")
            result = conversation.finalize(root, transcript)
            self.assertEqual("earlier parts kept", result["status"])
            self.assertTrue((root / conversation.FOLDER / "part-0001.jsonl").is_file())


class PhaseStartPushTests(unittest.TestCase):
    def test_a_phase_waits_until_the_conversation_is_on_the_remote(self) -> None:
        from unittest import mock

        from research_control import archive

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text('{"text": "hello"}\n', encoding="utf-8")
            saved = {"commit": "c0ffee", "branch": "run-data/x", "pushed": True}
            with mock.patch.object(conversation, "find_transcript", return_value=transcript), \
                    mock.patch.object(archive, "_remote_url", return_value="https://example.com/r.git"), \
                    mock.patch.object(archive, "archive", return_value=saved), \
                    mock.patch.object(archive.subprocess, "run") as remote:
                remote.return_value = mock.Mock(returncode=0, stdout="c0ffee\trefs/heads/run-data/x\n")
                self.assertTrue(archive.ensure_conversation_pushed(root, "start of facts")["on_remote"])
                self.assertEqual("start of facts", conversation.state(root)["last_verified"])
                remote.return_value = mock.Mock(returncode=0, stdout="0ld0ld\trefs/heads/run-data/x\n")
                result = archive.ensure_conversation_pushed(root, "start of review")
                self.assertFalse(result["on_remote"])
                self.assertIn("the remote branch is at 0ld0ld", result["detail"])


if __name__ == "__main__":
    unittest.main()
