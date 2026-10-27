from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json

from research_control.capture import _reusable_transcript
from research_control.discovery import admissible_media, discoverable_link
from research_control.media import _label_speakers, is_media_url, youtube_id
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

    def test_recapture_reuses_a_finished_transcript_of_the_same_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            url = "https://cdn.example.com/episode.mp3"
            transcript = root / "01-sources/captures/S1/transcript.txt"
            transcript.parent.mkdir(parents=True)
            transcript.write_text(f"# Transcript: {url}\n[00:00:01] hello\n", encoding="utf-8")
            receipt = root / "tools/outputs/worker-parts/capture/S1.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({"transcript": {"status": "transcribed", "method": "whisper", "segments": 1}}))
            self.assertEqual(transcript, _reusable_transcript(root, "S1", url)["path"])
            self.assertIsNone(_reusable_transcript(root, "S1", "https://cdn.example.com/other.mp3"))

    def test_words_take_the_speaker_of_their_turn_and_lines_break_on_changes(self) -> None:
        words = [(0.0, 0.4, " Thanks"), (0.4, 0.8, " for"), (0.8, 1.2, " joining."),
                 (1.6, 2.0, " Happy"), (2.0, 2.4, " to"), (2.4, 2.8, " be"), (2.8, 3.0, " here.")]
        turns = [(0.0, 1.3, 7), (1.5, 3.1, 3)]
        self.assertEqual(
            [(0.0, "Speaker 1: Thanks for joining."), (1.6, "Speaker 2: Happy to be here.")],
            _label_speakers(words, turns),
        )

    def test_github_organization_listing_is_recorded_as_blocked_with_a_reason(self) -> None:
        from research_control.capture import auto_capture_source

        with tempfile.TemporaryDirectory() as directory:
            receipt = auto_capture_source(Path(directory), url="https://github.com/ExampleOrg", source_id="G1", grade="P")
            self.assertEqual("blocked", receipt["status"])
            self.assertIn("organization", receipt["reason"])


if __name__ == "__main__":
    unittest.main()
