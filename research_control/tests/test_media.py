from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.discovery import admissible_media, discoverable_link
from research_control.media import is_media_url, youtube_id
from research_control.validators import quotes


class MediaTests(unittest.TestCase):
    def test_youtube_ids_and_media_hosts(self) -> None:
        self.assertEqual("Pq0g8_L9TZw", youtube_id("https://www.youtube.com/watch?v=Pq0g8_L9TZw"))
        self.assertEqual("zMfnoS9Tq9c", youtube_id("https://youtu.be/zMfnoS9Tq9c?feature=shared"))
        self.assertEqual("abc", youtube_id("https://www.youtube.com/embed/abc"))
        self.assertIsNone(youtube_id("https://example.com/watch?v=abc"))
        self.assertTrue(is_media_url("https://feeds.example.com/episode.mp3"))
        self.assertTrue(is_media_url("https://podcasts.apple.com/us/podcast/x/id1"))
        self.assertFalse(is_media_url("https://www.tribe.ai/about"))
        self.assertTrue(is_media_url("https://www.bloomberg.com/news/videos/2025-01-30/tribe-ai-ceo"))

    def test_media_channels_admit_audio_but_crawl_skips_it(self) -> None:
        url = "https://traffic.example.com/episode-541.mp3"
        self.assertFalse(discoverable_link(url))
        self.assertTrue(admissible_media(url, "podcasts"))
        self.assertFalse(admissible_media(url, "company_site"))

    def test_quotes_are_checked_against_every_text_derivative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "content.txt"
            transcript = root / "transcript.txt"
            page.write_text("Most teams have the tools.\n", encoding="utf-8")
            transcript.write_text("[00:01:02] We embed forward deployed engineers.\n", encoding="utf-8")
            rows = [
                {"fact_id": "F-1", "source_id": "S", "quote": "Most teams have the tools", "location": "line 1"},
                {"fact_id": "F-2", "source_id": "S", "quote": "We embed forward deployed engineers", "location": "00:01:02"},
            ]
            report = quotes.validate(rows, {"S": [page, transcript]}, root)
            self.assertEqual("PASS", report["status"], report)


if __name__ == "__main__":
    unittest.main()
