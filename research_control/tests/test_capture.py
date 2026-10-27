from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from research_control.capture import (
    REPOSITORY_FILE_LIMIT,
    TextExtractor,
    _blocked_receipt,
    _clear_stale_block,
    _commit_history,
    _embedded_publish_date,
    _refusal_marker,
    _repository_text,
    _unmerged_work,
)


class TextExtractionTests(unittest.TestCase):
    def test_inline_elements_join_as_rendered(self) -> None:
        extractor = TextExtractor()
        extractor.feed(
            "<p>Hello <b>big</b> world</p>"
            "<div><span>M</span><span>o</span><span>s</span><span>t</span> teams</div>"
            "<ul><li>one</li><li>two</li></ul><script>ignored()</script>"
        )
        self.assertEqual("Hello big world\nMost teams\none\ntwo\n", extractor.text())


    def test_embedded_publish_dates_are_read(self) -> None:
        youtube = '..."dateText":{"simpleText":"x"},"publishDate":{"simpleText":"Jul 25, 2025"},...'
        self.assertEqual("2025-07-25", _embedded_publish_date(youtube))
        self.assertEqual("2024-03-03", _embedded_publish_date('<meta itemprop="datePublished" content="2024-03-03T10:00:00-08:00">'))
        self.assertEqual("2023-09-14", _embedded_publish_date('{"uploadDate":"September 14, 2023"}'))
        self.assertEqual("", _embedded_publish_date("<p>No date here</p>"))
        self.assertEqual("2023-02-24", _embedded_publish_date('<script>{"datePublished": "2023-02-24T05:40:00Z"}</script>'))
        self.assertEqual("2024-09-20", _embedded_publish_date('<meta property="article:published_time" content="2024-09-20T00:10:00+00:00" />'))
        self.assertEqual("2023-06-28", _embedded_publish_date('<time datetime="June 28, 2023" class="x">June 28, 2023</time>'))


class RefusalTests(unittest.TestCase):
    def test_bot_check_redirect_is_a_refusal_however_long_the_page(self) -> None:
        sorry = {
            "url": "https://www.google.com/sorry/index?continue=https://www.youtube.com/watch%3Fv%3Dabc",
            "title": "https://www.youtube.com/watch?v=abc",
            "text": "Our systems have detected unusual traffic from your computer network. " * 5,
        }
        self.assertIn("google.com/sorry", _refusal_marker(sorry))
        page = {"url": "https://example.com/a", "title": "About", "text": "A real page about the company. " * 10}
        self.assertEqual("", _refusal_marker(page))

    def test_blocked_receipt_drops_refused_page_files_but_keeps_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "01-sources/captures/SRC-1"
            capture.mkdir(parents=True)
            for name in ("content.txt", "rendered.html", "transcript.txt"):
                (capture / name).write_text("x\n", encoding="utf-8")
            receipt = _blocked_receipt(root, "SRC-1", "https://www.youtube.com/watch?v=abc", "bot check")
            self.assertEqual("blocked", receipt["status"])
            self.assertEqual(["BLOCKED.txt", "transcript.txt"], sorted(item.name for item in capture.iterdir()))


    def test_successful_capture_clears_an_earlier_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _blocked_receipt(root, "SRC-2", "https://example.com/a", "HTTP 429")
            _clear_stale_block(root, "SRC-2", {"status": "captured"})
            self.assertFalse((root / "01-sources/captures/SRC-2/BLOCKED.txt").exists())


def _git(cwd: Path, *args: str, date: str = "2026-05-01T12:00:00Z", author: str = "Dev") -> None:
    environment = {
        **os.environ, "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": f"{author.lower().replace(' ', '')}@example.com",
        "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": "c@example.com",
        "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date,
    }
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=environment)


class RepositoryCaptureTests(unittest.TestCase):
    def test_large_file_is_included_when_the_budget_has_room(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / "README.md").write_text("# Tool\n", encoding="utf-8")
            (checkout / "data.json").write_text("x" * (REPOSITORY_FILE_LIMIT + 10), encoding="utf-8")
            text = "\n".join(_repository_text(checkout, ["README.md", "data.json"]))
            self.assertIn("--- FILE: data.json", text)
            self.assertNotIn("FILES NOT INCLUDED", text)

    def test_unmerged_branches_and_pull_requests_are_captured_once_without_bot_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _git(repo, "init", "-q", "-b", "main")
            (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "Initial tool", date="2026-01-10T12:00:00Z")
            _git(repo, "checkout", "-q", "-b", "feature")
            (repo / "explorer.py").write_text("def explore():\n    return 'claim quality'\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "Add video-quality explorer", date="2026-06-26T12:00:00Z")
            _git(repo, "checkout", "-q", "-b", "bump", "main")
            (repo / "uv.lock").write_text("bumped\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "chore(deps): bump", author="dependabot[bot]")
            _git(repo, "checkout", "-q", "main")
            # The same commit published as a branch and as a pull request head.
            _git(repo, "update-ref", "refs/remotes/origin/feature", "feature")
            _git(repo, "update-ref", "refs/remotes/pull/4", "feature")
            _git(repo, "update-ref", "refs/remotes/origin/dependabot/uv", "bump")
            lines, latest = _unmerged_work(repo)
            text = "\n".join(lines)
            self.assertEqual("2026-06-26", latest)
            self.assertIn("UNMERGED: feature, pull request #4 (1 commits, 2026-06-26 to 2026-06-26)", text)
            self.assertIn("claim quality", text)
            self.assertNotIn("bump", text)
            self.assertEqual(1, text.count("=== UNMERGED"))
            history = "\n".join(_commit_history(repo))
            self.assertIn("1 commits, 2026-01-10 to 2026-01-10", history)
            self.assertIn("Initial tool", history)


if __name__ == "__main__":
    unittest.main()
