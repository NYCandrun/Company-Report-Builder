from __future__ import annotations

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from research_control.deeplinks import deep_link, text_fragment
from research_control.io import atomic_write_text

REPO = "\n".join([
    "Repository: TribeAI/tool",
    "Source URL: https://github.com/TribeAI/tool",
    "Captured commit: abcdef1234567890 (committed 2026-06-01T00:00:00Z)",
    "Method: git clone",
    "",
    "--- FILE: README.md (3 lines) ---",
    "# Tool",
    "Scores Microsoft Learn modules for freshness.",
    "Built for the ASN workstream.",
    "",
    "--- CHANGE HISTORY OF THE DEFAULT BRANCH (1 commits with their changes, oldest first) ---",
    "",
    "=== COMMIT 1234567 2026-05-01 Add scorer ===",
    "diff --git a/app/score.py b/app/score.py",
    "--- a/app/score.py",
    "+++ b/app/score.py",
    "@@ -1,2 +1,3 @@",
    " import os",
    "-THRESHOLD = 0.5",
    "+THRESHOLD = 0.7",
    "+REVIEWERS = 3",
    "",
    "--- FILE: public/report/index.html (HTML, as text) (2 lines) ---",
    "Claim quality",
    "42 videos scored",
])


class DeepLinkTests(unittest.TestCase):
    def test_repository_quotes_link_to_file_lines_and_diff_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "01-sources/captures/SRC-R/content.txt", REPO + "\n")
            source = {"id": "SRC-R", "url": "https://github.com/TribeAI/tool"}
            link = deep_link(root, source, "Scores Microsoft Learn modules for freshness.")
            self.assertEqual("https://github.com/TribeAI/tool/blob/abcdef1234567890/README.md?plain=1#L2", link["deep_link"])
            link = deep_link(root, source, "REVIEWERS = 3")
            anchor = sha256(b"app/score.py").hexdigest()
            self.assertEqual(f"https://github.com/TribeAI/tool/commit/1234567#diff-{anchor}R3", link["deep_link"])
            # A page read as text has no matching source line, so the link is to the file.
            link = deep_link(root, source, "42 videos scored")
            self.assertEqual("https://github.com/TribeAI/tool/blob/abcdef1234567890/public/report/index.html", link["deep_link"])

    def test_recordings_link_to_the_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_text(root / "01-sources/captures/SRC-V/transcript.txt",
                              "# Transcript\n[00:00:05] welcome back\n[00:12:34] we started with one team at the bank\n")
            source = {"id": "SRC-V", "url": "https://www.youtube.com/watch?v=abc&feature=shared"}
            link = deep_link(root, source, "we started with one team at the bank")
            self.assertEqual("https://www.youtube.com/watch?v=abc&t=754s", link["deep_link"])
            self.assertEqual("at 00:12:34", link["anchor"])

    def test_pages_get_a_text_fragment(self) -> None:
        url = text_fragment("https://www.tribe.ai/about#team", "Tribe works with global enterprises like Koch and FIS")
        self.assertEqual("https://www.tribe.ai/about#:~:text=Tribe%20works%20with%20global%20enterprises%20like%20Koch%20and%20FIS", url)
        long = text_fragment("https://x.com/a", "one two three four five six seven eight nine ten eleven twelve thirteen")
        self.assertTrue(long.endswith("#:~:text=one%20two%20three%20four%20five%20six,eight%20nine%20ten%20eleven%20twelve%20thirteen"))


if __name__ == "__main__":
    unittest.main()
