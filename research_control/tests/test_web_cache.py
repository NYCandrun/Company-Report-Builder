from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from research_control.runtime import RuntimeStore
from research_control.web_cache import SharedWebCache


@dataclass
class Response:
    url: str
    content_type: str
    body: bytes
    status: int = 200
    headers: dict[str, str] | None = None


class SharedWebCacheTests(unittest.TestCase):
    def test_fetch_or_reuse_calls_transport_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []

            def fetch() -> Response:
                calls.append("fetch")
                return Response("https://example.com/", "text/html", b"example")

            with RuntimeStore(root) as store:
                store.initialize(run_id="cache-0", company_url="https://example.com")
                cache = SharedWebCache(root, store)
                first = cache.fetch_or_reuse(
                    "https://example.com", consumer="research", purpose="research_discovery",
                    fetcher=fetch,
                )
                second = cache.fetch_or_reuse(
                    "https://example.com", consumer="brand", purpose="brand_discovery",
                    fetcher=fetch,
                )
                self.assertFalse(first.cache_hit)
                self.assertTrue(second.cache_hit)
                self.assertEqual(["fetch"], calls)

    def test_reuses_bytes_across_separate_research_and_brand_purposes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with RuntimeStore(root) as store:
                store.initialize(run_id="cache-1", company_url="https://example.com")
                cache = SharedWebCache(root, store)
                stored = cache.store_response(
                    "https://example.com/",
                    final_url="https://example.com/",
                    content_type="text/html",
                    status=200,
                    headers={"Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"},
                    body=b"<html><body>Example</body></html>",
                    consumer="capture.discover.company-site",
                    purpose="research_discovery",
                )
                self.assertFalse(stored.cache_hit)
                reused = cache.lookup(
                    "https://example.com",
                    consumer="capture.brand-guide",
                    purpose="brand_discovery",
                )
                self.assertIsNotNone(reused)
                assert reused is not None
                self.assertTrue(reused.cache_hit)
                self.assertEqual(stored.content_sha256, reused.content_sha256)
                records = cache.records()
                self.assertEqual(1, len(records))
                self.assertEqual(
                    {"research_discovery", "brand_discovery"},
                    {item["purpose"] for item in records[0]["uses"]},
                )


if __name__ == "__main__":
    unittest.main()
