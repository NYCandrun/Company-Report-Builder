"""Adaptive, question-bounded source discovery.

Discovery has no source quota.  The first-party site is crawled to a fixed point
by the runtime.  Search-driven channels stop when they are ``sufficient`` for the
brief's numbered research questions, or ``saturated`` when repeated passes add
nothing.  Numeric limits in ``DiscoveryPolicy`` are circuit breakers: hitting
one produces ``incomplete``, never a complete state.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, build_opener

from research_control.capture import PublicRedirectHandler, USER_AGENT, _robots_allowed
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text, utc_now, workflow
from research_control.runtime import DISCOVERY_COMPLETE, DISCOVERY_TERMINAL, RuntimeStore
from research_control.web_cache import SharedWebCache


DISCOVERY_CHANNELS = (
    "company_site",
    "sitemaps",
    "newsroom_blog",
    "docs_help",
    "careers",
    "video",
    "podcasts",
    "social",
    "code_packages",
    "independent_web",
)

TRACKING_PARAMETERS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer", "source",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}
SKIP_SCHEMES = {"mailto", "tel", "javascript", "data", "blob"}
# Login-walled platforms: their URLs are kept as leads with provenance, but are
# not assigned capture work because public capture cannot read them.
LEAD_ONLY_HOSTS = (
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "threads.net", "tiktok.com",
)
QUESTION_ID = re.compile(r"\bQ\d+\b")
SKIP_SUFFIXES = {
    ".7z", ".avi", ".css", ".dmg", ".eot", ".exe", ".gif", ".gz", ".ico",
    ".jpeg", ".jpg", ".mov", ".mp3", ".mp4", ".otf", ".png", ".rar", ".svg",
    ".tar", ".tgz", ".ttf", ".wav", ".webm", ".webp", ".woff", ".woff2", ".zip",
}


@dataclass(frozen=True)
class DiscoveryPolicy:
    """Safety breakers, not completeness targets."""

    max_pages: int = 10_000
    max_bytes: int = 1_000_000_000
    max_elapsed_seconds: int = 14_400
    max_depth: int = 12
    max_document_bytes: int = 25_000_000
    saturation_passes: int = 2
    min_host_interval_seconds: float = 1.0


@dataclass(frozen=True)
class FetchResult:
    url: str
    content_type: str
    body: bytes
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.canonical: str | None = None
        self._anchor: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        lowered = tag.casefold()
        if lowered == "a" and values.get("href"):
            self._anchor = values["href"]
            self._text = []
        if lowered == "link" and "canonical" in values.get("rel", "").casefold() and values.get("href"):
            self.canonical = values["href"]

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._anchor is not None:
            self.links.append((self._anchor, re.sub(r"\s+", " ", " ".join(self._text)).strip()))
            self._anchor = None
            self._text = []


def canonicalize_url(url: str, base: str | None = None) -> str:
    absolute = urljoin(base or "", url.strip())
    parsed = urlparse(absolute)
    if parsed.scheme.casefold() in SKIP_SCHEMES or parsed.scheme.casefold() not in {"http", "https"}:
        raise ValueError("only absolute public HTTP(S) URLs are discoverable")
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        raise ValueError("URL has no hostname")
    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme.casefold() == "http" and port == 80) or (parsed.scheme.casefold() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted((key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.casefold() not in TRACKING_PARAMETERS),
        doseq=True,
    )
    return urlunparse((parsed.scheme.casefold(), netloc, path, "", query, ""))


def host_key(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def _same_company_host(candidate: str, company_host: str) -> bool:
    value = host_key(candidate)
    return value == company_host or value.endswith(f".{company_host}") or company_host.endswith(f".{value}")


def classify_channel(url: str, company_host: str, anchor_text: str = "") -> str:
    parsed = urlparse(url)
    host = host_key(url)
    signal = f"{host} {parsed.path.casefold()} {anchor_text.casefold()}"
    if any(name in host for name in ("youtube.com", "youtu.be", "vimeo.com", "loom.com", "wistia.com")):
        return "video"
    if any(name in host for name in ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com", "threads.net")):
        return "social"
    if any(name in host for name in ("github.com", "gitlab.com", "pypi.org", "npmjs.com", "rubygems.org", "crates.io")):
        return "code_packages"
    if any(name in host for name in ("spotify.com", "podcasts.apple.com", "podbean.com", "transistor.fm", "buzzsprout.com")) or "podcast" in signal:
        return "podcasts"
    if any(term in signal for term in ("/careers", "/jobs", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com")):
        return "careers"
    if any(term in signal for term in ("/docs", "/documentation", "/help", "/support", "readme.io", "gitbook.io")):
        return "docs_help"
    if any(term in signal for term in ("/blog", "/news", "/press", "/resources", "/insights", "/webinars")):
        return "newsroom_blog"
    return "company_site" if _same_company_host(url, company_host) else "independent_web"


def lead_only(url: str) -> bool:
    host = host_key(url)
    return any(host == name or host.endswith(f".{name}") for name in LEAD_ONLY_HOSTS)


def candidate_relevance(url: str) -> str:
    path = urlparse(url).path.casefold()
    if "sitemap" in path and path.endswith(".xml"):
        return "inventory"
    return "lead" if lead_only(url) else "candidate"


def source_kind(url: str) -> str:
    path = urlparse(url).path.casefold()
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith((".xml", ".rss", ".atom")) or "feed" in path:
        return "feed"
    return "web_page"


def discoverable_link(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    path = parsed.path.casefold()
    if host == "linkedin.com" and path.rstrip("/") == "/sharing/share-offsite":
        return False
    if host in {"twitter.com", "x.com"} and path.rstrip("/") == "/intent/tweet":
        return False
    return not any(path.endswith(suffix) for suffix in SKIP_SUFFIXES)


def xml_links(body: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return []
    values: list[str] = []
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1].casefold()
        if local in {"loc", "link"} and element.text and element.text.strip().startswith(("http://", "https://")):
            values.append(element.text.strip())
        href = element.attrib.get("href", "").strip()
        if local == "link" and href.startswith(("http://", "https://")):
            values.append(href)
    return list(dict.fromkeys(values))


def public_fetch(url: str, policy: DiscoveryPolicy) -> FetchResult:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("discovery URL has no hostname")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as error:
        raise ValueError(f"discovery hostname cannot be resolved: {hostname}") from error
    if any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise PermissionError(f"discovery URL resolves to a non-public address: {hostname}")
    if not _robots_allowed(url):
        raise PermissionError(f"robots.txt disallows discovery fetch: {url}")
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.2"},
    )
    with build_opener(PublicRedirectHandler()).open(request, timeout=30) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > policy.max_document_bytes:
            raise ValueError(f"document exceeds safety limit: {length} bytes")
        body = response.read(policy.max_document_bytes + 1)
        if len(body) > policy.max_document_bytes:
            raise ValueError(f"document exceeds safety limit: {policy.max_document_bytes} bytes")
        return FetchResult(
            url=response.geturl(),
            content_type=response.headers.get_content_type(),
            body=body,
            status=getattr(response, "status", 200),
            headers={str(key): str(value) for key, value in response.headers.items()},
        )


class DiscoveryEngine:
    def __init__(
        self,
        root: Path,
        store: RuntimeStore,
        *,
        policy: DiscoveryPolicy | None = None,
        fetcher: Callable[[str, DiscoveryPolicy], FetchResult] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.store = store
        if policy is None:
            values = workflow(self.root / "WORKFLOW.yaml").get("adaptive_runtime", {}).get("discovery", {})
            breakers = values.get("safety_circuit_breakers", {})
            policy = DiscoveryPolicy(
                max_pages=int(breakers.get("max_pages", 10_000)),
                max_bytes=int(breakers.get("max_bytes", 1_000_000_000)),
                max_elapsed_seconds=int(breakers.get("max_elapsed_seconds", 14_400)),
                max_depth=int(breakers.get("max_depth", 12)),
                saturation_passes=int(values.get("saturation_empty_passes", 2)),
                min_host_interval_seconds=float(values.get("min_host_interval_seconds", 1.0)),
            )
        self.policy = policy
        self.fetcher = fetcher or public_fetch
        self.shared_cache = SharedWebCache(self.root, store)
        metadata = store.metadata()
        self.company_url = canonicalize_url(metadata["company_url"])
        self.company_host = host_key(self.company_url)

    def initialize(self) -> dict[str, Any]:
        for channel in DISCOVERY_CHANNELS:
            self.store.ensure_discovery_channel(channel)
        source, _created = self.store.add_source(
            canonical_url=self.company_url,
            original_url=self.company_url,
            host_key=self.company_host,
            channel="company_site",
            source_kind="web_page",
            relevance="required",
            depth=0,
            metadata={"seed": True},
        )
        self.shared_cache.note_url(
            self.company_url,
            consumer="capture.discover.company-site",
            purpose="research_discovery",
            discovered_from="company_url",
        )
        self.write_catalog()
        return source

    def add_candidates(
        self,
        channel: str,
        urls: list[str],
        *,
        discovered_from: str,
        evidence: str,
        depth: int = 0,
        record_pass: bool = True,
    ) -> dict[str, Any]:
        if channel not in DISCOVERY_CHANNELS:
            raise ValueError(f"unknown discovery channel: {channel}")
        created: list[str] = []
        rejected: list[dict[str, str]] = []
        for value in urls:
            try:
                canonical = canonicalize_url(value, self.company_url)
                if not discoverable_link(canonical):
                    raise ValueError("non-research media or asset URL")
                actual_channel = classify_channel(canonical, self.company_host)
                selected_channel = channel if channel != "company_site" else actual_channel
                source, was_created = self.store.add_source(
                    canonical_url=canonical,
                    original_url=value,
                    host_key=host_key(canonical),
                    channel=selected_channel,
                    source_kind=source_kind(canonical),
                    relevance=candidate_relevance(canonical),
                    discovered_from=discovered_from,
                    depth=depth,
                )
                self.shared_cache.note_url(
                    canonical,
                    consumer=f"capture.discover.{channel.replace('_', '-')}",
                    purpose="research_discovery",
                    discovered_from=discovered_from,
                )
                if was_created:
                    created.append(source["source_id"])
            except (ValueError, PermissionError) as error:
                rejected.append({"url": value, "reason": str(error)})
        channel_state = None
        if record_pass:
            channel_state = self.store.record_discovery_pass(
                channel,
                new_sources=len(created),
                evidence=evidence,
                saturation_passes=self.policy.saturation_passes,
            )
        self.write_catalog()
        return {"channel": channel, "new_source_ids": created, "rejected": rejected, "channel_state": channel_state}

    def seed_sitemaps(self) -> dict[str, Any]:
        """Admit robots-declared and conventional sitemaps as crawl inventories."""
        parsed = urlparse(self.company_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        declared = [f"{base}/sitemap.xml"]
        note = "robots.txt read"
        try:
            robots = self.fetcher(f"{base}/robots.txt", self.policy)
            for line in robots.body.decode("utf-8", errors="replace").splitlines():
                if line.strip().casefold().startswith("sitemap:"):
                    declared.append(line.split(":", 1)[1].strip())
        except Exception as error:  # an unreadable robots file only removes declared sitemaps
            note = f"robots.txt unavailable: {error}"
        created: list[str] = []
        for value in dict.fromkeys(declared):
            try:
                canonical = canonicalize_url(value, self.company_url)
            except ValueError:
                continue
            if not _same_company_host(canonical, self.company_host):
                continue
            source, was_created = self.store.add_source(
                canonical_url=canonical,
                original_url=value,
                host_key=host_key(canonical),
                channel="sitemaps",
                source_kind="feed",
                relevance="inventory",
                discovered_from="robots.txt",
                depth=1,
                metadata={"discovered_via": "sitemap_seed"},
            )
            if was_created:
                created.append(source["source_id"])
        self.write_catalog()
        return {"seeded": created, "note": note}

    def audit_sitemaps(self, *, refetch: bool) -> dict[str, Any]:
        """Record one sitemap fixed-point pass: every listed URL must be cataloged."""
        known = {source["canonical_url"] for source in self.store.sources()}
        inventories = [
            source for source in self.store.sources()
            if source["relevance"] == "inventory" and source["status"] == "discovered_fetched"
        ]
        added: list[str] = []
        listed = 0
        for inventory in inventories:
            if refetch:
                try:
                    body = self.fetcher(inventory["canonical_url"], self.policy).body
                except Exception:
                    continue
            else:
                paths = inventory.get("local_paths") or []
                if not paths or not (self.root / paths[0]).is_file():
                    continue
                body = (self.root / paths[0]).read_bytes()
            for href in xml_links(body):
                try:
                    candidate = canonicalize_url(href, inventory["canonical_url"])
                except ValueError:
                    continue
                if not discoverable_link(candidate) or not _same_company_host(candidate, self.company_host):
                    continue
                listed += 1
                if candidate in known:
                    continue
                source, was_created = self.store.add_source(
                    canonical_url=candidate,
                    original_url=href,
                    host_key=host_key(candidate),
                    channel=classify_channel(candidate, self.company_host),
                    source_kind=source_kind(candidate),
                    relevance=candidate_relevance(candidate),
                    discovered_from=inventory["source_id"],
                    depth=int(inventory["depth"]) + 1,
                    metadata={"discovered_via": "sitemap_audit"},
                )
                known.add(candidate)
                if was_created:
                    added.append(source["source_id"])
        method = "fresh re-fetch" if refetch else "cached bytes"
        channel = self.store.record_discovery_pass(
            "sitemaps",
            new_sources=len(added),
            evidence=(
                f"sitemap audit ({method}): {len(inventories)} inventories, {listed} listed company URLs, "
                f"{len(added)} not previously cataloged"
            ),
            saturation_passes=self.policy.saturation_passes,
        )
        self.write_catalog()
        return {"inventories": len(inventories), "listed": listed, "new_source_ids": added, "channel_state": channel}

    def crawl_company_site(self) -> dict[str, Any]:
        """Drain the first-party frontier once; repeat calls prove saturation."""
        started = time.monotonic()
        pages = 0
        bytes_read = 0
        new_sources = 0
        failures: list[dict[str, str]] = []
        fetched: list[str] = []
        cache_hits = 0
        last_request: dict[str, float] = {}
        while True:
            frontier = [
                source for source in self.store.sources(statuses={"discovered"})
                if source["channel"] in {"company_site", "newsroom_blog", "docs_help", "careers", "sitemaps"}
                and _same_company_host(source["canonical_url"], self.company_host)
            ]
            if not frontier:
                break
            source = frontier[0]
            elapsed = time.monotonic() - started
            breaker: str | None = None
            if pages >= self.policy.max_pages:
                breaker = f"page safety limit reached ({self.policy.max_pages})"
            elif bytes_read >= self.policy.max_bytes:
                breaker = f"byte safety limit reached ({self.policy.max_bytes})"
            elif elapsed >= self.policy.max_elapsed_seconds:
                breaker = f"runtime safety limit reached ({self.policy.max_elapsed_seconds}s)"
            if breaker:
                channel = self.store.set_discovery_channel("company_site", "incomplete", breaker)
                self.write_catalog()
                return {
                    "status": "incomplete", "reason": breaker, "pages_fetched": pages,
                    "bytes_read": bytes_read, "new_sources": new_sources, "cache_hits": cache_hits,
                    "channel_state": channel,
                }
            if source["depth"] > self.policy.max_depth:
                self.store.update_source(source["source_id"], status="excluded", metadata={"reason": "depth safety limit"})
                continue
            try:
                key = source["host_key"]
                consumer = f"capture.discover.{str(source['channel']).replace('_', '-')}"

                def fetch_uncached() -> FetchResult:
                    if self.fetcher is public_fetch and key in last_request:
                        remaining = self.policy.min_host_interval_seconds - (time.monotonic() - last_request[key])
                        if remaining > 0:
                            time.sleep(remaining)
                    fetched_result = self.fetcher(source["canonical_url"], self.policy)
                    last_request[key] = time.monotonic()
                    return fetched_result

                cached = self.shared_cache.fetch_or_reuse(
                    source["canonical_url"],
                    consumer=consumer,
                    purpose="research_discovery",
                    discovered_from=str(source.get("discovered_from") or ""),
                    fetcher=fetch_uncached,
                )
                if cached.cache_hit:
                    cache_hits += 1
                result = FetchResult(
                    url=cached.final_url,
                    content_type=cached.content_type,
                    body=cached.body,
                    status=cached.status,
                    headers=cached.headers,
                )
                pages += 1
                bytes_read += len(result.body)
                fetched.append(source["source_id"])
                cache = self.root / "01-sources/discovery-cache" / source["source_id"]
                cache.mkdir(parents=True, exist_ok=True)
                suffix = ".html" if result.content_type in {"text/html", "application/xhtml+xml"} else ".xml" if "xml" in result.content_type else ".bin"
                raw_path = cache / f"response{suffix}"
                raw_path.write_bytes(result.body)
                metadata = {
                    **source["metadata"],
                    "discovery_fetched_at": utc_now(),
                    "content_type": result.content_type,
                    "http_status": result.status,
                    "final_url": result.url,
                    "shared_cache_object": cached.object_path,
                    "shared_cache_hit": cached.cache_hit,
                }
                self.store.update_source(
                    source["source_id"], status="discovered_fetched",
                    local_paths=[str(raw_path.relative_to(self.root))], content_bytes=len(result.body), metadata=metadata,
                )
                if result.content_type in {"text/html", "application/xhtml+xml"}:
                    parser = LinkExtractor()
                    parser.feed(result.body.decode("utf-8", errors="replace"))
                    for href, anchor in parser.links:
                        try:
                            candidate = canonicalize_url(href, result.url)
                        except ValueError:
                            continue
                        if not discoverable_link(candidate):
                            continue
                        channel = classify_channel(candidate, self.company_host, anchor)
                        if channel == "independent_web":
                            # Arbitrary outbound links are evidence leads, not a license to crawl the web.
                            continue
                        _added, created = self.store.add_source(
                            canonical_url=candidate,
                            original_url=href,
                            host_key=host_key(candidate),
                            channel=channel,
                            source_kind=source_kind(candidate),
                            relevance=candidate_relevance(candidate),
                            discovered_from=source["source_id"],
                            depth=source["depth"] + 1,
                            metadata={"anchor_text": anchor},
                        )
                        self.shared_cache.note_url(
                            candidate,
                            consumer=f"capture.discover.{channel.replace('_', '-')}",
                            purpose="research_discovery",
                            discovered_from=source["source_id"],
                        )
                        new_sources += int(created)
                elif "xml" in result.content_type or source["source_kind"] == "feed":
                    for href in xml_links(result.body):
                        try:
                            candidate = canonicalize_url(href, result.url)
                        except ValueError:
                            continue
                        if not discoverable_link(candidate):
                            continue
                        channel = classify_channel(candidate, self.company_host)
                        if channel == "independent_web":
                            continue
                        _added, created = self.store.add_source(
                            canonical_url=candidate,
                            original_url=href,
                            host_key=host_key(candidate),
                            channel=channel,
                            source_kind=source_kind(candidate),
                            relevance=candidate_relevance(candidate),
                            discovered_from=source["source_id"],
                            depth=source["depth"] + 1,
                            metadata={"discovered_via": "xml_feed_or_sitemap"},
                        )
                        self.shared_cache.note_url(
                            candidate,
                            consumer=f"capture.discover.{channel.replace('_', '-')}",
                            purpose="research_discovery",
                            discovered_from=source["source_id"],
                        )
                        new_sources += int(created)
            except Exception as error:  # each source gets a terminal disposition; unrelated discovery continues
                failures.append({"source_id": source["source_id"], "url": source["canonical_url"], "reason": str(error)})
                self.store.update_source(source["source_id"], status="blocked", metadata={"discovery_error": str(error)})
        channel = self.store.record_discovery_pass(
            "company_site",
            new_sources=new_sources,
            evidence=f"frontier drained; fetched={pages}; blocked={len(failures)}; new={new_sources}",
            saturation_passes=self.policy.saturation_passes,
        )
        self.write_catalog()
        return {
            "status": channel["state"],
            "pages_fetched": pages,
            "bytes_read": bytes_read,
            "new_sources": new_sources,
            "cache_hits": cache_hits,
            "fetched_source_ids": fetched,
            "failures": failures,
            "channel_state": channel,
        }

    def close_channel(self, channel: str, state: str, evidence: str) -> dict[str, Any]:
        if state not in DISCOVERY_TERMINAL:
            raise ValueError(
                "channel may only be closed as saturated, sufficient, not_applicable, blocked, or incomplete"
            )
        if state == "sufficient":
            current = self.store.discovery_channel(channel)
            if not current or int(current["total_passes"]) < 1:
                raise ValueError(f"{channel}: sufficiency requires at least one recorded discovery pass")
            if not QUESTION_ID.search(evidence):
                raise ValueError(
                    f"{channel}: sufficiency evidence must name the research question IDs (Q1, Q2, ...) "
                    "the channel's admitted sources answer and why further search would not change them"
                )
        if state == "saturated":
            current = self.store.discovery_channel(channel)
            if not current or int(current["consecutive_empty_passes"]) < self.policy.saturation_passes:
                raise ValueError(
                    f"{channel}: saturation requires {self.policy.saturation_passes} recorded empty passes; "
                    "use `discovery add` for each materially different pass"
                )
        result = self.store.set_discovery_channel(channel, state, evidence)
        self.write_catalog()
        return result

    def retry_blocked_sources(
        self,
        channel: str,
        *,
        evidence: str,
        source_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return explicitly selected transport-blocked sources to the frontier.

        This is a controller-owned recovery path for a changed transport condition,
        such as moving a run from a DNS-restricted sandbox to an approved public
        network context. It never retries excluded, captured, or other terminal
        dispositions implicitly.
        """
        if channel not in DISCOVERY_CHANNELS:
            raise ValueError(f"unknown discovery channel: {channel}")
        if not evidence.strip():
            raise ValueError("retry evidence is required")
        selected = set(source_ids or [])
        if selected:
            unknown = selected - {item["source_id"] for item in self.store.sources()}
            if unknown:
                raise KeyError(f"unknown source IDs: {', '.join(sorted(unknown))}")
        candidates = [
            source for source in self.store.sources(statuses={"blocked"})
            if source["channel"] == channel and (not selected or source["source_id"] in selected)
        ]
        if selected:
            ineligible = selected - {item["source_id"] for item in candidates}
            if ineligible:
                raise ValueError(
                    "retry accepts only blocked sources in the selected channel: "
                    + ", ".join(sorted(ineligible))
                )
        for source in candidates:
            metadata = dict(source.get("metadata") or {})
            metadata["discovery_retry"] = {
                "at": utc_now(),
                "evidence": evidence.strip(),
                "prior_error": metadata.get("discovery_error", ""),
            }
            self.store.update_source(source["source_id"], status="discovered", metadata=metadata)
        if candidates:
            state = self.store.set_discovery_channel(
                channel,
                "open",
                f"retrying {len(candidates)} blocked source(s): {evidence.strip()}",
            )
        else:
            state = self.store.discovery_channel(channel)
        self.write_catalog()
        return {
            "channel": channel,
            "retried": len(candidates),
            "source_ids": [item["source_id"] for item in candidates],
            "channel_state": state,
        }

    def exclude_sources(
        self,
        channel: str,
        *,
        evidence: str,
        source_ids: list[str],
    ) -> dict[str, Any]:
        """Exclude audited non-evidence leads without deleting their provenance."""
        if channel not in DISCOVERY_CHANNELS:
            raise ValueError(f"unknown discovery channel: {channel}")
        if not evidence.strip():
            raise ValueError("exclusion evidence is required")
        if not source_ids:
            raise ValueError("at least one source ID is required")
        selected = set(source_ids)
        sources = {item["source_id"]: item for item in self.store.sources()}
        unknown = selected - set(sources)
        if unknown:
            raise KeyError(f"unknown source IDs: {', '.join(sorted(unknown))}")
        ineligible = [
            source_id for source_id in sorted(selected)
            if sources[source_id]["channel"] != channel
            or sources[source_id]["status"] == "captured"
        ]
        if ineligible:
            raise ValueError(
                "exclusion accepts only uncaptured sources in the selected channel: "
                + ", ".join(ineligible)
            )
        for source_id in sorted(selected):
            source = sources[source_id]
            metadata = dict(source.get("metadata") or {})
            metadata["discovery_exclusion"] = {
                "at": utc_now(),
                "evidence": evidence.strip(),
            }
            self.store.update_source(
                source_id, relevance="excluded", metadata=metadata
            )
        self.write_catalog()
        return {
            "channel": channel,
            "excluded": len(selected),
            "source_ids": sorted(selected),
            "evidence": evidence.strip(),
        }

    def write_catalog(self) -> None:
        sources = self.store.sources()
        atomic_write_jsonl(self.root / "tools/outputs/discovery/sources.jsonl", sources)
        channels = self.store.discovery_channels()
        atomic_write_json(
            self.root / "tools/outputs/discovery/status.json",
            {
                "schema_version": "1.0.0",
                "completion_rule": "all applicable channels reach a documented fixed point; source count is not a target",
                "terminal": bool(channels) and all(item["state"] in DISCOVERY_TERMINAL for item in channels),
                "complete": bool(channels) and all(item["state"] in DISCOVERY_COMPLETE for item in channels),
                "limitations": [item["channel"] for item in channels if item["state"] in {"blocked", "incomplete"}],
                "channels": channels,
                "source_count": len(sources),
                "updated_at": utc_now(),
            },
        )
        lines = [
            "# Discovery coverage", "",
            "Discovery has no source-count target. The runtime crawls the company site to a fixed point; "
            "search channels close as `sufficient` for named research questions or `saturated`.", "",
            "| Channel | State | Passes | New sources | Evidence |", "|---|---|---:|---:|---|",
        ]
        for item in channels:
            evidence = str(item.get("completion_evidence") or "").replace("|", "\\|")
            lines.append(
                f"| {item['channel']} | {item['state']} | {item['total_passes']} | {item['total_new_sources']} | {evidence} |"
            )
        atomic_write_text(self.root / "06-checks/discovery-coverage.md", "\n".join(lines) + "\n")
