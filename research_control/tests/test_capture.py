from __future__ import annotations

import os
import subprocess
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from research_control.capture import (
    REPOSITORY_FILE_LIMIT,
    TextExtractor,
    _Blame,
    _blocked_receipt,
    _change_history,
    _clear_stale_block,
    _commit_history,
    _conversation_numbers,
    _drop_blobs,
    _transient,
    _with_retries,
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
    def test_change_history_keeps_overwritten_versions_oldest_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _git(repo, "init", "-q", "-b", "main")
            (repo / "accounts.md").write_text("| Acme | Proposal |\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "Add account book", date="2026-03-01T12:00:00Z")
            (repo / "accounts.md").write_text("| Acme | Signed |\n", encoding="utf-8")
            (repo / "uv.lock").write_text("pinned\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "Acme signed", date="2026-05-01T12:00:00Z")
            (repo / "accounts.md").write_text("| Acme | Signed |\n| Beta | Lead |\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "chore: bump", author="dependabot[bot]")
            text = "\n".join(_change_history(repo))
            self.assertLess(text.index("Add account book"), text.index("Acme signed"))
            self.assertIn("-| Acme | Proposal |", text)
            self.assertIn("+| Acme | Signed |", text)
            self.assertNotIn("pinned", text)
            self.assertNotIn("Beta", text)
            # With blame, an added line still in the current file is counted, not repeated;
            # what was overwritten stays, and the current file dates its lines by commit.
            (repo / "accounts.md").write_text("| Acme | Signed |\n| Beta | Lead |\n| Gamma | Lost |\n", encoding="utf-8")
            (repo / "tests").mkdir()
            (repo / "tests/test_book.py").write_text(
                'def test_acme_signed():\n    """Acme is signed."""\n    assert book()["Acme"] == "Signed"\n', encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "Gamma lost", date="2026-06-01T12:00:00Z")
            blame = _Blame(repo)
            history = "\n".join(_change_history(repo, "", blame))
            self.assertIn("-| Acme | Proposal |", history)
            self.assertIn("+[1 added line still in the current file]", history)
            self.assertNotIn("+| Acme | Signed |", history)
            self.assertNotIn("Acme is signed", history)
            files = "\n".join(_repository_text(repo, ["accounts.md", "tests/test_book.py"], blame))
            self.assertRegex(files, r"--- FILE: accounts.md \(\d+ lines; written 1-1 [0-9a-f]{7} 2026-05-01; 2-2 [0-9a-f]{7} 2026-05-01; 3-3 [0-9a-f]{7} 2026-06-01\) ---")
            self.assertIn("--- FILE: tests/test_book.py (tests, names only)", files)
            self.assertIn('def test_acme_signed():\n    """Acme is signed."""', files)
            self.assertNotIn("assert book()", files)

    def test_large_file_is_included_when_the_budget_has_room(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / "README.md").write_text("# Tool\n", encoding="utf-8")
            (checkout / "notes.txt").write_text("x" * (REPOSITORY_FILE_LIMIT + 10), encoding="utf-8")
            text = "\n".join(_repository_text(checkout, ["README.md", "notes.txt"]))
            self.assertIn("--- FILE: notes.txt", text)
            self.assertNotIn("FILES NOT INCLUDED", text)

    def test_large_data_files_are_sampled_and_html_is_read_as_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            records = [{"id": number, "title": f"Document {number}", "body": "y" * 400} for number in range(3000)]
            (checkout / "documents.json").write_text(json.dumps(records), encoding="utf-8")
            (checkout / "report.html").write_text(
                "<html><style>p{}</style><body><h1>Claim quality</h1><p>42 videos scored</p>"
                "<script>var data = 1;</script></body></html>", encoding="utf-8")
            lines = _repository_text(checkout, ["documents.json", "report.html"])
            text = "\n".join(lines)
            header = next(line for line in lines if line.startswith("--- FILE: documents.json"))
            self.assertIn("data sample: 3000 records", header)
            self.assertIn('"title": "Document 0"', text)
            self.assertLess(len(text), 30_000)
            self.assertIn("--- FILE: report.html (HTML, as text)", text)
            self.assertIn("42 videos scored", text)
            self.assertNotIn("var data", text)
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
            # A pull request its page shows as merged (squash or rebase) is shipped, not unmerged.
            merged_text = "\n".join(_unmerged_work(repo, merged=frozenset({4}))[0])
            self.assertIn("=== MERGED BY SQUASH OR REBASE: feature, pull request #4", merged_text)
            self.assertNotIn("=== UNMERGED", merged_text)
            # A diff over the per-ref limit is included file by file, naming what did not fit.
            with mock.patch("research_control.capture.UNMERGED_REF_LIMIT", 10):
                by_file = "\n".join(_unmerged_work(repo)[0])
            self.assertIn("included file by file", by_file)
            self.assertIn("claim quality", by_file)
            with mock.patch("research_control.capture.UNMERGED_REF_LIMIT", 10), mock.patch("research_control.capture.PATCH_FILE_LIMIT", 10):
                by_file = "\n".join(_unmerged_work(repo)[0])
            self.assertIn("file diffs not included: explorer.py", by_file)
            self.assertNotIn("claim quality", by_file)
            # Pull requests worth reading: human ones, and for a path, those that changed it.
            _git(repo, "update-ref", "refs/remotes/pull/9", "bump")
            self.assertEqual([4], _conversation_numbers(repo))
            self.assertEqual([4], _conversation_numbers(repo, "explorer.py"))
            self.assertEqual([], _conversation_numbers(repo, "app.py"))
            history = "\n".join(_commit_history(repo))
            self.assertIn("1 commits, 2026-01-10 to 2026-01-10", history)
            self.assertIn("Initial tool", history)


class ResilienceTests(unittest.TestCase):
    def test_transient_failures_are_retried_and_refusals_are_not(self) -> None:
        calls: list[int] = []

        def flaky() -> str:
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionResetError("Connection reset by peer")
            return "ok"

        with mock.patch("research_control.capture.time.sleep"):
            self.assertEqual("ok", _with_retries(flaky))
            refused = mock.Mock(side_effect=type("Refused", (Exception,), {"code": 403})())
            with self.assertRaises(Exception):
                _with_retries(refused)
        self.assertEqual(3, len(calls))
        self.assertEqual(1, refused.call_count)
        self.assertTrue(_transient(TimeoutError("timed out")))
        self.assertFalse(_transient(ValueError("capture URL must be absolute http(s)")))

    def test_embedded_base64_is_replaced_on_its_own_line(self) -> None:
        blob = "A" * 1200
        text = f"line one\n+{blob}\n<img src=\"data:image/png;base64,{'B' * 300}\">\nline four\n"
        cleaned = _drop_blobs(text)
        self.assertEqual(text.count("\n"), cleaned.count("\n"))
        self.assertIn("\n+[1200 base64 characters not shown]\n", cleaned)
        self.assertIn("data:image/png;base64,[300 base64 characters not shown]", cleaned)
        self.assertIn("line four", cleaned)


if __name__ == "__main__":
    unittest.main()


class ShallowLookTests(unittest.TestCase):
    def test_a_shallow_look_reads_markdown_and_csv_only_readme_first(self) -> None:
        from research_control.capture import shallow_files

        listed = ["src/agent.py", "docs/clients.md", "README.md", "data/accounts.csv", "notes.md",
                  "node_modules/pkg/README.md", "package.json", "team/org-chart.tsv"]
        self.assertEqual(["README.md", "notes.md", "data/accounts.csv", "docs/clients.md", "team/org-chart.tsv"],
                         shallow_files(listed))
