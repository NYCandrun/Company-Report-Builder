from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.dating import DATE_OVERRIDES, SOURCE_DATES, write_source_dates
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text, load_jsonl


class SourceDatingTests(unittest.TestCase):
    def test_sources_are_dated_by_content_with_age_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_write_json(root / "tools/outputs/run-state.json", {"created_at": "2026-10-27T00:00:00Z"})
            receipts = [
                {"source_id": "SRC-PUB", "status": "captured", "source": {"date published": "2026-09-01", "date captured": "2026-10-27"}},
                {"source_id": "SRC-OLD", "status": "captured", "source": {"date published": "2025-12-15", "date captured": "2026-10-27"}},
                {"source_id": "SRC-VID", "status": "captured", "source": {"date captured": "2026-10-27"}},
                {"source_id": "SRC-LIVE", "status": "captured", "source": {"date captured": "2026-10-27"}},
                {"source_id": "SRC-POD", "status": "captured", "source": {"date captured": "2026-10-27"}},
                {"source_id": "SRC-FEED", "status": "captured", "source": {"date captured": "2026-10-27"}},
                {"source_id": "SRC-YT", "status": "captured", "source": {"date captured": "2026-10-27"}},
            ]
            atomic_write_text(root / "01-sources/captures/SRC-VID/raw.html", '"publishDate":{"simpleText":"Jul 25, 2025"}')
            atomic_write_text(root / "01-sources/captures/SRC-VID/transcript.txt", "# Transcript\n")
            atomic_write_text(root / "01-sources/captures/SRC-LIVE/raw.html", "<html>Careers</html>")
            atomic_write_text(root / "01-sources/captures/SRC-POD/transcript.txt", "# Transcript\n")
            atomic_write_text(root / "01-sources/captures/SRC-FEED/raw.json", '{"jobs": []}')
            # A video captured through yt-dlp keeps its metadata: the air date wins over the upload date.
            atomic_write_text(root / "01-sources/captures/SRC-YT/transcript.txt", "# Transcript\n")
            atomic_write_json(root / "01-sources/captures/SRC-YT/captions.info.json", {"release_date": "20220915", "upload_date": "20220916"})
            report = write_source_dates(root, receipts)
            rows = {row["source_id"]: row for row in load_jsonl(root / SOURCE_DATES)}
            self.assertEqual("current", rows["SRC-PUB"]["flag"])
            self.assertEqual("dated", rows["SRC-OLD"]["flag"])
            self.assertEqual(("2025-07-25", "dated"), (rows["SRC-VID"]["content_date"], rows["SRC-VID"]["flag"]))
            self.assertEqual("live page at capture", rows["SRC-LIVE"]["basis"])
            self.assertEqual(("live data at capture", "current"), (rows["SRC-FEED"]["basis"], rows["SRC-FEED"]["flag"]))
            self.assertEqual("undated", rows["SRC-POD"]["flag"])
            self.assertEqual(("2022-09-15", "release date in captions.info.json"), (rows["SRC-YT"]["content_date"], rows["SRC-YT"]["basis"]))
            self.assertEqual("youtube.com", rows["SRC-YT"]["platform"] or "youtube.com")
            # A recording that says when it was recorded is dated by that; the posting date is kept.
            atomic_write_jsonl(root / "tools/outputs/worker-parts/extraction/x.candidates.jsonl", [
                {"source_id": "SRC-YT", "notes": "Recorded: 2022-06-02; basis: host says 'June 2nd' at [00:00:40]"},
            ])
            write_source_dates(root, receipts)
            row = {row["source_id"]: row for row in load_jsonl(root / SOURCE_DATES)}["SRC-YT"]
            self.assertEqual(("2022-06-02", "2022-09-15"), (row["content_date"], row["posted_date"]))
            self.assertEqual("recorded 2022-06-02, posted 2022-09-15", row["date_note"])
            write_source_dates(root, receipts)
            self.assertEqual(1, report["undated"])
            # A dating pass's override fills an undated source, keeping its evidence.
            atomic_write_jsonl(root / DATE_OVERRIDES, [
                {"source_id": "SRC-POD", "date": "2026-06-04", "basis": "episode page", "evidence": "https://example.com/ep"},
            ])
            write_source_dates(root, receipts)
            rows = {row["source_id"]: row for row in load_jsonl(root / SOURCE_DATES)}
            self.assertEqual(("2026-06-04", "as of"), (rows["SRC-POD"]["content_date"], rows["SRC-POD"]["flag"]))
            self.assertIn("episode page", rows["SRC-POD"]["basis"])


if __name__ == "__main__":
    unittest.main()
