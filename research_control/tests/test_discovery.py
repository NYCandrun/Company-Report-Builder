from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from research_control.discovery import (
    DiscoveryEngine,
    DiscoveryPolicy,
    FetchResult,
    canonicalize_url,
    discoverable_link,
    xml_links,
)
from research_control.runtime import RuntimeStore


SOURCE_ROOT = Path(__file__).resolve().parents[2]


class DiscoveryTests(unittest.TestCase):
    def test_share_intent_links_are_not_discoverable_evidence(self) -> None:
        self.assertFalse(discoverable_link("https://www.linkedin.com/sharing/share-offsite/?url=https://example.com"))
        self.assertFalse(discoverable_link("https://twitter.com/intent/tweet?url=https://example.com"))
        self.assertFalse(discoverable_link("https://x.com/intent/tweet?url=https://example.com"))
        self.assertTrue(discoverable_link("https://www.linkedin.com/company/example"))

    def test_sitemap_and_feed_links_are_extracted(self) -> None:
        body = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/a</loc></url><url><loc>https://example.com/b</loc></url></urlset>'
        self.assertEqual(["https://example.com/a", "https://example.com/b"], xml_links(body))

    def test_company_frontier_stops_on_saturation_not_source_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(SOURCE_ROOT / "WORKFLOW.yaml", root / "WORKFLOW.yaml")
            graph = {
                "https://example.com/": b'<a href="/about?utm_source=test">About</a><a href="https://youtube.com/@example">Video</a>',
                "https://example.com/about": b"<html><body>About Example</body></html>",
            }

            def fetch(url: str, _policy: DiscoveryPolicy) -> FetchResult:
                return FetchResult(url=url, content_type="text/html", body=graph[url])

            with RuntimeStore(root) as store:
                store.initialize(run_id="discover-1", company_url="https://example.com")
                engine = DiscoveryEngine(root, store, fetcher=fetch)
                engine.initialize()
                first = engine.crawl_company_site()
                self.assertGreater(first["new_sources"], 0)
                self.assertEqual("open", first["status"])
                second = engine.crawl_company_site()
                self.assertEqual("open", second["status"])
                third = engine.crawl_company_site()
                self.assertEqual("saturated", third["status"])
                self.assertEqual(3, len(store.sources()))
                self.assertEqual(
                    "https://example.com/about",
                    canonicalize_url("https://EXAMPLE.com/about/?utm_source=x"),
                )

    def test_external_channel_needs_repeated_empty_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(SOURCE_ROOT / "WORKFLOW.yaml", root / "WORKFLOW.yaml")
            with RuntimeStore(root) as store:
                store.initialize(run_id="discover-2", company_url="https://example.com")
                engine = DiscoveryEngine(root, store)
                engine.initialize()
                with self.assertRaises(ValueError):
                    engine.close_channel("independent_web", "saturated", "unsupported shortcut")
                one = engine.add_candidates(
                    "independent_web", ["https://news.example.org/story"],
                    discovered_from="query-1", evidence="first query family",
                )
                self.assertEqual(1, len(one["new_source_ids"]))
                self.assertEqual("open", one["channel_state"]["state"])
                empty_one = engine.add_candidates(
                    "independent_web", [], discovered_from="query-2", evidence="second query family: no new evidence",
                )
                self.assertEqual("open", empty_one["channel_state"]["state"])
                empty_two = engine.add_candidates(
                    "independent_web", [], discovered_from="query-3", evidence="third query family: no new evidence",
                )
                self.assertEqual("saturated", empty_two["channel_state"]["state"])
                engine.close_channel("video", "incomplete", "fixture safety breaker")
                summary = store.summary()["discovery"]
                self.assertFalse(summary["complete"])
                self.assertIn("video", summary["limitations"])

    def test_explicit_retry_returns_only_blocked_channel_sources_to_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(SOURCE_ROOT / "WORKFLOW.yaml", root / "WORKFLOW.yaml")
            with RuntimeStore(root) as store:
                store.initialize(run_id="discover-retry", company_url="https://example.com")
                engine = DiscoveryEngine(root, store)
                engine.initialize()
                result = engine.add_candidates(
                    "company_site",
                    ["https://example.com/about"],
                    discovered_from="fixture",
                    evidence="fixture branch",
                    record_pass=False,
                )
                source_id = result["new_source_ids"][0]
                store.update_source(
                    source_id,
                    status="blocked",
                    metadata={"discovery_error": "temporary DNS failure", "fixture": True},
                )
                store.set_discovery_channel("company_site", "saturated", "stale empty-pass proof")

                retried = engine.retry_blocked_sources(
                    "company_site", evidence="approved public network is now available"
                )

                self.assertEqual([source_id], retried["source_ids"])
                self.assertEqual("discovered", store.source(source_id)["status"])
                self.assertTrue(store.source(source_id)["metadata"]["fixture"])
                self.assertEqual("temporary DNS failure", store.source(source_id)["metadata"]["discovery_retry"]["prior_error"])
                channel = store.discovery_channel("company_site")
                self.assertEqual("open", channel["state"])
                self.assertEqual(0, channel["consecutive_empty_passes"])

    def test_explicit_exclusion_preserves_lead_and_removes_it_from_capture_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(SOURCE_ROOT / "WORKFLOW.yaml", root / "WORKFLOW.yaml")
            with RuntimeStore(root) as store:
                store.initialize(run_id="discover-exclude", company_url="https://example.com")
                engine = DiscoveryEngine(root, store)
                engine.initialize()
                source, _created = store.add_source(
                    canonical_url="https://twitter.com/intent/tweet?url=https://example.com",
                    original_url="https://twitter.com/intent/tweet?url=https://example.com",
                    host_key="twitter.com",
                    channel="social",
                    source_kind="web_page",
                )

                result = engine.exclude_sources(
                    "social",
                    source_ids=[source["source_id"]],
                    evidence="share-intent transport is not research evidence",
                )

                self.assertEqual(1, result["excluded"])
                updated = store.source(source["source_id"])
                self.assertEqual("excluded", updated["relevance"])
                self.assertIn("discovery_exclusion", updated["metadata"])


if __name__ == "__main__":
    unittest.main()
