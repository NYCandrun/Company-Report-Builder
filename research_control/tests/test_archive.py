from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from research_control.archive import ARCHIVE_GIT, BUNDLE_DIR, archive
from research_control.io import atomic_write_json, atomic_write_text


class ArchiveTests(unittest.TestCase):
    def test_archive_keeps_sources_and_bundles_and_leaves_out_audio_and_caches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runs/acme"
            atomic_write_json(root / "tools/outputs/run-state.json", {"slug": "acme"})
            atomic_write_text(root / "01-sources/captures/SRC-1/transcript.txt", "# Transcript\n")
            atomic_write_text(root / "01-sources/captures/SRC-1/raw.html", "<html></html>")
            atomic_write_text(root / "01-sources/captures/SRC-2/audio.mp3", "audio")
            atomic_write_text(root / "tools/outputs/web-cache/x.bin", "cached")
            atomic_write_text(root / "scratchpad/w/notes.txt", "scratch")
            repo = root / "tools/outputs/git-cache/acme/tool"
            repo.mkdir(parents=True)
            (repo / "README.md").write_text("# Tool\n", encoding="utf-8")
            for args in (["init", "-q"], ["add", "."], ["-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "init"]):
                subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
            result = archive(root, push=False)
            self.assertTrue(result["committed"])
            self.assertEqual("bundled", result["repositories"]["acme__tool"])
            listed = subprocess.run(
                ["git", f"--git-dir={root / ARCHIVE_GIT}", "ls-tree", "-r", "--name-only", "HEAD"],
                text=True, capture_output=True, check=True,
            ).stdout.split()
            self.assertIn("01-sources/captures/SRC-1/transcript.txt", listed)
            self.assertIn("01-sources/captures/SRC-1/raw.html", listed)
            self.assertIn(f"{BUNDLE_DIR}/acme__tool.bundle", listed)
            self.assertFalse(any("audio.mp3" in path or "web-cache" in path or "scratchpad" in path for path in listed))
            # Nothing new to keep: no empty commit.
            self.assertFalse(archive(root, push=False)["committed"])


if __name__ == "__main__":
    unittest.main()
