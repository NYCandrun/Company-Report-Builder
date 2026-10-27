from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.capture import TextExtractor, _blocked_receipt, _clear_stale_block, _embedded_publish_date, _refusal_marker


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


if __name__ == "__main__":
    unittest.main()
