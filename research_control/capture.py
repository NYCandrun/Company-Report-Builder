"""Conservative public-page capture helper used by the agent orchestrator."""

from __future__ import annotations

import csv
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from research_control.io import atomic_write_json, atomic_write_text, utc_now
from research_control.resources import runtime_limits
from research_control.runtime import RuntimeStore
from research_control.web_cache import SharedWebCache


USER_AGENT = "CompanyResearchAgent/1.2 (+public-research)"
MANIFEST_FIELDS = (
    "id",
    "grade",
    "title",
    "publisher",
    "url",
    "date published",
    "date last modified",
    "date captured",
    "local file",
    "method",
    "notes",
)


@dataclass(frozen=True)
class _PublicResponse:
    url: str
    content_type: str
    body: bytes
    status: int
    headers: dict[str, str]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.skip_depth = 0
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag.casefold() == "title":
            self.in_title = True
        if tag.casefold() == "meta":
            key = attributes.get("property") or attributes.get("name") or attributes.get("itemprop")
            if key and attributes.get("content"):
                self.meta[key.casefold()] = attributes["content"].strip()
        if tag.casefold() in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag.casefold() == "title":
            self.in_title = False
        if tag.casefold() in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        self.parts.append(data)

    def text(self) -> str:
        # Inline elements are joined as rendered: whitespace comes only from the
        # document itself, so text split across per-letter spans stays intact.
        value = "".join(self.parts)
        value = re.sub(r"[ \t\r\f\v\u00a0]+", " ", value)
        value = re.sub(r" *\n[\s]*", "\n", value)
        return value.strip() + "\n"

    def title(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.title_parts)).strip()


def _require_public_host(url: str) -> None:
    hostname = urlparse(url).hostname
    if not hostname:
        raise ValueError("capture URL has no hostname")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as error:
        raise ValueError(f"capture hostname cannot be resolved: {hostname}") from error
    unsafe = [value for value in addresses if not ipaddress.ip_address(value).is_global]
    if unsafe:
        raise PermissionError(f"capture URL resolves to a non-public address: {hostname}")


class PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _require_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _iso_date(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if match:
        return match.group(0)
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    # Display dates such as "Jul 25, 2025" or "Premiered March 3, 2024".
    match = re.search(r"([A-Z][a-z]{2,8})\.? (\d{1,2}), (\d{4})", value)
    if match:
        for pattern in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(" ".join(match.groups()), pattern).date().isoformat()
            except ValueError:
                continue
    return ""


# Publication dates that pages embed outside standard meta tags, as YouTube
# watch pages do in their player data.
EMBEDDED_DATES = (
    re.compile(r'itemprop="(?:datePublished|uploadDate)"\s+content="([^"]+)"'),
    re.compile(r'"(?:uploadDate|publishDate|datePublished)"\s*:\s*"([^"]+)"'),
    re.compile(r'"publishDate":\{"simpleText":"([^"]+)"\}'),
    re.compile(r'(?:property|name)="(?:article:published_time|og:published_time|pubdate|publish-date)"\s+content="([^"]+)"'),
    re.compile(r'content="([^"]+)"\s+(?:property|name)="(?:article:published_time|og:published_time|pubdate|publish-date)"'),
    # Last resort: the page's first <time datetime>, which on article and
    # episode pages is the publication date.
    re.compile(r'<time[^>]*\sdatetime="([^"]+)"'),
)


def _embedded_publish_date(html: str) -> str:
    for pattern in EMBEDDED_DATES:
        match = pattern.search(html)
        if match and _iso_date(match.group(1)):
            return _iso_date(match.group(1))
    return ""


def _manifest_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or not path.stat().st_size:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{key: value or "" for key, value in row.items()} for row in csv.DictReader(handle)]


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, buffer.getvalue())


def capture_url(
    root: Path,
    *,
    url: str,
    source_id: str,
    grade: str,
    title: str | None = None,
    publisher: str | None = None,
) -> dict[str, Any]:
    if grade not in {"P", "S", "T", "I"}:
        raise ValueError("grade must be P, S, T, or I")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", source_id):
        raise ValueError("source ID may contain only letters, numbers, period, underscore, and hyphen")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("capture URL must be absolute http(s)")
    _require_public_host(url)

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5"})
    with build_opener(PublicRedirectHandler()).open(request, timeout=30) as response:
        body = response.read()
        final_url = response.geturl()
        content_type = response.headers.get_content_type()
        modified_raw = response.headers.get("Last-Modified", "")
        modified = _iso_date(modified_raw)
    directory = root / "01-sources/captures" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    method = "public HTTP capture"
    date_published = ""
    notes = ""
    if content_type in {"text/html", "application/xhtml+xml"}:
        raw_path = directory / "raw.html"
        raw_path.write_bytes(body)
        decoded = body.decode("utf-8", errors="replace")
        extractor = TextExtractor()
        extractor.feed(decoded)
        text_path = directory / "content.txt"
        atomic_write_text(text_path, extractor.text())
        title = title or extractor.title() or final_url
        for key in ("article:published_time", "datepublished", "date", "publish-date", "pubdate"):
            if extractor.meta.get(key):
                raw_date = extractor.meta[key]
                date_published = _iso_date(raw_date)
                if not date_published:
                    notes = f"Unparsed publication-date metadata: {raw_date}"
                break
        local_files = f"{raw_path.relative_to(root)};{text_path.relative_to(root)}"
    else:
        suffix = ".pdf" if content_type == "application/pdf" else ".bin"
        raw_path = directory / f"source{suffix}"
        raw_path.write_bytes(body)
        title = title or Path(parsed.path).name or final_url
        local_files = str(raw_path.relative_to(root))
        notes = f"Binary {content_type}; create a canonical text derivative before extraction."
        method = f"public HTTP capture ({content_type})"

    row = {
        "id": source_id,
        "grade": grade,
        "title": title,
        "publisher": publisher or parsed.netloc.removeprefix("www."),
        "url": final_url,
        "date published": date_published,
        "date last modified": modified,
        "date captured": datetime.now(timezone.utc).date().isoformat(),
        "local file": local_files,
        "method": method,
        "notes": notes,
    }
    manifest = root / "01-sources/MANIFEST.csv"
    rows = _manifest_rows(manifest)
    if any(existing.get("id") == source_id for existing in rows):
        raise ValueError(f"source ID already exists: {source_id}")
    rows.append(row)
    _write_manifest(manifest, rows)
    return {"status": "captured", "source": row, "captured_at": utc_now()}


def capture_source_part(
    root: Path,
    *,
    url: str,
    source_id: str,
    grade: str = "P",
    title: str | None = None,
    publisher: str | None = None,
    store: RuntimeStore | None = None,
) -> dict[str, Any]:
    """Capture one source without touching a shared manifest.

    Parallel workers use this entry point.  A single reducer later validates
    the receipts and writes the canonical manifest and disposition files.
    """
    if grade not in {"P", "S", "T", "I"}:
        raise ValueError("grade must be P, S, T, or I")
    if not re.fullmatch(r"SRC-[A-F0-9]{12}|[A-Za-z0-9][A-Za-z0-9._-]*", source_id):
        raise ValueError("source ID may contain only letters, numbers, period, underscore, and hyphen")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("capture URL must be absolute http(s)")
    def fetch_uncached() -> _PublicResponse:
        _require_public_host(url)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5"})
        with build_opener(PublicRedirectHandler()).open(request, timeout=30) as response:
            return _PublicResponse(
                url=response.geturl(),
                content_type=response.headers.get_content_type(),
                body=response.read(),
                status=int(getattr(response, "status", 200)),
                headers={str(key): str(value) for key, value in response.headers.items()},
            )

    if store is not None:
        cached = SharedWebCache(root, store).fetch_or_reuse(
            url,
            consumer=f"capture.source.{source_id.casefold()}",
            purpose="research_capture",
            fetcher=fetch_uncached,
        )
        body = cached.body
        final_url = cached.final_url
        content_type = cached.content_type
        headers = cached.headers
        cache_hit = cached.cache_hit
        cache_object = cached.object_path
    else:
        response = fetch_uncached()
        body = response.body
        final_url = response.url
        content_type = response.content_type
        headers = response.headers
        cache_hit = False
        cache_object = ""
    modified = _iso_date(headers.get("Last-Modified", headers.get("last-modified", "")))
    directory = root / "01-sources/captures" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    date_published = ""
    notes = ""
    canonical_text = False
    if content_type in {"text/html", "application/xhtml+xml"}:
        raw_path = directory / "raw.html"
        raw_path.write_bytes(body)
        extractor = TextExtractor()
        extractor.feed(body.decode("utf-8", errors="replace"))
        content = extractor.text()
        text_path = directory / "content.txt"
        atomic_write_text(text_path, content)
        canonical_text = bool(content.strip())
        title = title or extractor.title() or final_url
        for key in ("article:published_time", "datepublished", "date", "publish-date", "pubdate"):
            if extractor.meta.get(key):
                raw_date = extractor.meta[key]
                date_published = _iso_date(raw_date)
                if not date_published:
                    notes = f"Unparsed publication-date metadata: {raw_date}"
                break
        date_published = date_published or _embedded_publish_date(body.decode("utf-8", errors="replace"))
        local_files = [str(raw_path.relative_to(root)), str(text_path.relative_to(root))]
        method = "shared-cache public HTTP capture" if cache_hit else "public HTTP capture"
        token_estimate = max(1, len(content) // 4)
    elif content_type.startswith("text/") or content_type in {"application/json", "application/xml", "application/rss+xml", "application/atom+xml"}:
        suffix = ".xml" if "xml" in content_type else ".json" if content_type == "application/json" else ".txt"
        raw_path = directory / f"raw{suffix}"
        raw_path.write_bytes(body)
        content = body.decode("utf-8", errors="replace")
        text_path = directory / "content.txt"
        atomic_write_text(text_path, content)
        local_files = [str(raw_path.relative_to(root)), str(text_path.relative_to(root))]
        title = title or Path(parsed.path).name or final_url
        method = f"{'shared-cache ' if cache_hit else ''}public HTTP capture ({content_type})"
        token_estimate = max(1, len(content) // 4)
        canonical_text = bool(content.strip())
    else:
        suffix = ".pdf" if content_type == "application/pdf" else ".bin"
        raw_path = directory / f"source{suffix}"
        raw_path.write_bytes(body)
        local_files = [str(raw_path.relative_to(root))]
        title = title or Path(parsed.path).name or final_url
        method = f"{'shared-cache ' if cache_hit else ''}public HTTP capture ({content_type})"
        token_estimate = max(1, len(body) // 4)
        notes = f"Binary {content_type}; worker must create a canonical text derivative before extraction."

    source = {
        "id": source_id,
        "grade": grade,
        "title": title,
        "publisher": publisher or parsed.netloc.removeprefix("www."),
        "url": final_url,
        "date published": date_published,
        "date last modified": modified,
        "date captured": datetime.now(timezone.utc).date().isoformat(),
        "local file": ";".join(local_files),
        "method": method,
        "notes": notes,
    }
    receipt = {
        "schema_version": "1.0.0",
        "task_type": "capture",
        "source_id": source_id,
        "status": "captured" if canonical_text else "needs_derivative",
        "source": source,
        "local_paths": local_files,
        "content_bytes": len(body),
        "estimated_tokens": token_estimate,
        "canonical_text_ready": canonical_text,
        "shared_cache_hit": cache_hit,
        "shared_cache_object": cache_object,
        "captured_at": utc_now(),
        "disposition": {
            "input_id": source_id,
            "disposition": "completed" if canonical_text else "blocked",
            "reason": "captured with canonical text" if canonical_text else notes,
            "evidence_paths": local_files,
            "output_ids": [source_id] if canonical_text else [],
        },
    }
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
    atomic_write_json(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path.relative_to(root))}


BROWSER_SCRIPT = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      ...(process.argv[2] ? { userAgent: process.argv[2] } : {}),
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1,
      isMobile: false,
      hasTouch: false,
      locale: 'en-US',
    });
    await page.goto(process.argv[1], { waitUntil: 'networkidle', timeout: 45000 });
    const title = await page.title();
    const text = await page.evaluate(() => document.body ? document.body.innerText : '');
    const html = await page.content();
    process.stdout.write(JSON.stringify({ url: page.url(), title, text, html }));
  } finally {
    await browser.close();
  }
})().catch((error) => { process.stderr.write(String(error)); process.exit(1); });
"""
MIN_HTML_TEXT_CHARACTERS = 200
REFUSAL_STATUSES = {401, 403, 429}
REFUSAL_TITLES = (
    "access denied", "403", "forbidden", "just a moment", "attention required", "are you a robot", "unusual traffic",
)
# A render that lands on one of these hosts or paths was redirected to a bot
# check, whatever the page says.
REFUSAL_URL_MARKERS = ("google.com/sorry", "/captcha", "challenges.cloudflare.com")
# Owner policy: the headless browser always presents as desktop Chrome in a
# desktop window, so pages render their desktop layout and content.
DESKTOP_USER_AGENT = os.environ.get(
    "RESEARCH_CONTROL_DESKTOP_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36",
)


def browser_available() -> bool:
    if shutil.which("node") is None:
        return False
    probe = subprocess.run(
        ["node", "-e", "require('playwright')"], text=True, capture_output=True, timeout=30
    )
    return probe.returncode == 0


_browser_slots = threading.BoundedSemaphore(runtime_limits()["browser_jobs"])


def _render_once(url: str, user_agent: str) -> dict[str, str]:
    with _browser_slots:
        result = subprocess.run(
            ["node", "-e", BROWSER_SCRIPT, url, user_agent], text=True, capture_output=True, timeout=120
        )
    if result.returncode != 0:
        raise RuntimeError(f"browser render failed: {result.stderr.strip().splitlines()[0][:200] if result.stderr.strip() else 'no output'}")
    return json.loads(result.stdout)


def _refusal_marker(rendered: dict[str, str]) -> str:
    """The refusal a render shows (a bot-check redirect or refusal title), or ''."""
    landed = str(rendered.get("url", "")).casefold()
    for value in REFUSAL_URL_MARKERS:
        if value in landed:
            return f"redirect to {value}"
    text = re.sub(r"\s+", " ", rendered.get("text", "")).strip()
    marker = f"{rendered.get('title', '')} {text[:200]}".casefold()
    for value in REFUSAL_TITLES:
        if value in marker:
            return f"refusal page {str(rendered.get('title', ''))[:80]!r}"
    return ""


def _refused(rendered: dict[str, str]) -> bool:
    text = re.sub(r"\s+", " ", rendered.get("text", "")).strip()
    return bool(_refusal_marker(rendered)) or len(text) < MIN_HTML_TEXT_CHARACTERS


def _browser_render(url: str) -> dict[str, str]:
    """Render in a desktop window as desktop Chrome; if refused, retry once with the browser's own identity.

    Sites differ: on the Tribe run, OpenAI served only the desktop identity while
    PitchBook and Bloomberg served only the browser's default one. Both attempts
    use the desktop window, so the layout is always desktop.
    """
    _require_public_host(url)
    failures: list[str] = []
    rendered: dict[str, str] | None = None
    for user_agent in (DESKTOP_USER_AGENT, ""):
        try:
            rendered = _render_once(url, user_agent)
        except Exception as error:
            failures.append(str(error))
            continue
        if not _refused(rendered):
            return rendered
        failures.append(f"refusal page {rendered.get('title', '')!r}")
    if rendered is not None:
        return rendered
    raise RuntimeError("; ".join(failures))


def _pdf_text(pdf_path: Path, text_path: Path) -> int:
    """Write a page-marked UTF-8 derivative; return the page count."""
    if shutil.which("pdftotext") is None:
        raise RuntimeError("pdftotext is unavailable for PDF text derivation")
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr.decode('utf-8', errors='replace')[:300]}")
    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    body = "".join(f"--- page {number} ---\n{page.rstrip()}\n\n" for number, page in enumerate(pages, 1))
    atomic_write_text(text_path, body)
    return len(pages)


def _blocked_receipt(root: Path, source_id: str, url: str, reason: str) -> dict[str, Any]:
    directory = root / "01-sources/captures" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    # Page files from a refused attempt (a bot-check page) are not the source.
    for name in ("raw.html", "rendered.html", "content.txt"):
        (directory / name).unlink(missing_ok=True)
    atomic_write_text(directory / "BLOCKED.txt", f"{url}\n{reason}\n")
    receipt = {
        "schema_version": "1.0.0",
        "task_type": "capture",
        "source_id": source_id,
        "status": "blocked",
        "reason": reason,
        "access_method": "runtime public HTTP capture",
        "local_paths": [str((directory / "BLOCKED.txt").relative_to(root))],
        "canonical_text_ready": False,
        "captured_at": utc_now(),
        "disposition": {
            "input_id": source_id,
            "disposition": "blocked",
            "reason": reason,
            "evidence_paths": [str((directory / "BLOCKED.txt").relative_to(root))],
            "output_ids": [],
        },
    }
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
    atomic_write_json(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path.relative_to(root))}


def _finish_derivative(root: Path, receipt: dict[str, Any], text_path: Path, method: str, note: str) -> dict[str, Any]:
    content = text_path.read_text(encoding="utf-8", errors="replace")
    relative = str(text_path.relative_to(root))
    paths = list(dict.fromkeys([*receipt["local_paths"], relative]))
    receipt["local_paths"] = paths
    receipt["source"]["local file"] = ";".join(paths)
    receipt["source"]["method"] = method
    receipt["source"]["notes"] = note
    receipt["estimated_tokens"] = max(1, len(content) // 4)
    receipt["canonical_text_ready"] = bool(content.strip())
    receipt["status"] = "captured" if content.strip() else "blocked"
    receipt["disposition"] = {
        "input_id": receipt["source_id"],
        "disposition": "completed" if content.strip() else "blocked",
        "reason": "captured with canonical text" if content.strip() else f"{method} produced no text",
        "evidence_paths": paths,
        "output_ids": [receipt["source_id"]] if content.strip() else [],
    }
    if not content.strip():
        receipt["reason"] = receipt["disposition"]["reason"]
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{receipt['source_id']}.json"
    atomic_write_json(receipt_path, {key: value for key, value in receipt.items() if key != "receipt"})
    return {**receipt, "receipt": str(receipt_path.relative_to(root))}


def auto_capture_source(
    root: Path,
    *,
    url: str,
    source_id: str,
    grade: str,
    store: RuntimeStore | None = None,
    use_browser: bool | None = None,
    media: bool = False,
) -> dict[str, Any]:
    """Capture a public page, PDF, or media source end to end without an agent.

    Produces a terminal receipt: ``captured`` with a canonical text derivative,
    or ``blocked`` with the concrete reason. Media sources also get a
    timestamped transcript when captions or a public audio download allow it.
    Access restrictions are recorded, never bypassed.
    """
    from research_control.media import AUDIO_SUFFIXES

    if (urlparse(url).hostname or "").casefold().removeprefix("www.") == "github.com":
        try:
            return _clear_stale_block(root, source_id, _github_capture(root, url=url, source_id=source_id, grade=grade))
        except Exception as error:
            return _blocked_receipt(root, source_id, url, f"{type(error).__name__}: {error}")
    prior_transcript = _reusable_transcript(root, source_id, url) if media else None
    if media and urlparse(url).path.casefold().endswith(AUDIO_SUFFIXES):
        # A direct audio or video file has no page text; its transcript is the derivative.
        receipt = _blocked_receipt(root, source_id, url, "direct media file; no page text to capture")
    else:
        receipt = _capture_page(root, url=url, source_id=source_id, grade=grade, store=store, use_browser=use_browser)
    if not media:
        return _clear_stale_block(root, source_id, receipt)
    from research_control.media import transcribe

    directory = root / "01-sources/captures" / source_id
    # A recapture (for example after an upstream invalidation) keeps a finished
    # transcript of the same URL instead of downloading and transcribing again.
    result = prior_transcript or transcribe(url, directory)
    receipt.pop("receipt", None)
    if result["status"] != "transcribed":
        receipt["transcript"] = {"status": "unavailable", "reason": result["reason"]}
        if receipt.get("status") == "captured":
            note = f"Transcript unavailable: {result['reason']}"
            receipt["source"]["notes"] = "; ".join(value for value in (receipt["source"].get("notes"), note) if value)
        receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
        atomic_write_json(receipt_path, receipt)
        return {**receipt, "receipt": str(receipt_path.relative_to(root))}
    transcript = str(result["path"].relative_to(root))
    if receipt.get("status") != "captured":
        parsed = urlparse(url)
        receipt["source"] = {
            "id": source_id, "grade": grade, "title": url, "publisher": parsed.netloc.removeprefix("www."),
            "url": url, "date published": "", "date last modified": "",
            "date captured": datetime.now(timezone.utc).date().isoformat(), "local file": "",
            "method": "", "notes": f"Page text unavailable: {receipt.get('reason', 'blocked')}",
        }
        receipt["local_paths"] = []
        receipt.pop("reason", None)
    paths = list(dict.fromkeys([*receipt.get("local_paths", []), transcript]))
    text_tokens = sum(
        len((root / value).read_text(encoding="utf-8", errors="replace")) // 4
        for value in paths if value.endswith(".txt") and (root / value).is_file()
    )
    receipt.update({
        "status": "captured",
        "local_paths": paths,
        "canonical_text_ready": True,
        "estimated_tokens": max(1, text_tokens),
        "transcript": {key: result[key] for key in ("status", "method", "segments", "audio_sha256", "attempts")},
        "disposition": {
            "input_id": source_id, "disposition": "completed",
            "reason": "captured with timestamped transcript",
            "evidence_paths": paths, "output_ids": [source_id],
        },
    })
    receipt["source"]["local file"] = ";".join(paths)
    receipt["source"]["method"] = "; ".join(value for value in (receipt["source"].get("method"), result["method"]) if value)
    receipt["source"]["notes"] = "; ".join(
        value for value in (receipt["source"].get("notes"), "Machine transcript; speaker identity not established") if value
    )
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
    atomic_write_json(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path.relative_to(root))}


def _reusable_transcript(root: Path, source_id: str, url: str) -> dict[str, Any] | None:
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
    transcript_path = root / "01-sources/captures" / source_id / "transcript.txt"
    if not receipt_path.is_file() or not transcript_path.is_file():
        return None
    try:
        prior = json.loads(receipt_path.read_text(encoding="utf-8")).get("transcript") or {}
        header = transcript_path.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    except (OSError, ValueError):
        return None
    if prior.get("status") != "transcribed" or header != f"# Transcript: {url}":
        return None
    return {
        "status": "transcribed",
        "method": prior.get("method", ""),
        "path": transcript_path,
        "segments": prior.get("segments", 0),
        "audio_sha256": prior.get("audio_sha256", ""),
        "attempts": [*prior.get("attempts", []), "reused transcript from the previous capture of this URL"],
    }




def _browser_capture(root: Path, *, url: str, source_id: str, grade: str, http_reason: str) -> dict[str, Any]:
    """Capture a page through the headless browser after the plain request was refused."""
    try:
        rendered = _browser_render(url)
    except Exception as error:
        return _blocked_receipt(root, source_id, url, f"{http_reason}; headless browser: {str(error).splitlines()[0][:160]}")
    text = re.sub(r"\n{3,}", "\n\n", rendered.get("text", "")).strip()
    title = str(rendered.get("title", ""))
    refusal = _refusal_marker(rendered)
    if refusal or len(text) < MIN_HTML_TEXT_CHARACTERS:
        detail = refusal or f"only {len(text)} characters of text"
        return _blocked_receipt(root, source_id, url, f"{http_reason}; headless browser got {detail}")
    directory = root / "01-sources/captures" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write_text(directory / "rendered.html", rendered.get("html", ""))
    atomic_write_text(directory / "content.txt", text + "\n")
    paths = [str((directory / "rendered.html").relative_to(root)), str((directory / "content.txt").relative_to(root))]
    parsed = urlparse(url)
    receipt = {
        "schema_version": "1.0.0", "task_type": "capture", "source_id": source_id, "status": "captured",
        "source": {
            "id": source_id, "grade": grade, "title": title or url,
            "publisher": parsed.netloc.removeprefix("www."), "url": url,
            "date published": _embedded_publish_date(rendered.get("html", "")), "date last modified": "",
            "date captured": datetime.now(timezone.utc).date().isoformat(),
            "local file": ";".join(paths), "method": "headless browser capture after HTTP refusal",
            "notes": f"Plain HTTP request was refused ({http_reason}); text taken from the rendered page",
        },
        "local_paths": paths, "content_bytes": len(text.encode("utf-8")),
        "estimated_tokens": max(1, len(text) // 4), "canonical_text_ready": True, "captured_at": utc_now(),
        "disposition": {
            "input_id": source_id, "disposition": "completed", "reason": "captured with a headless browser",
            "evidence_paths": paths, "output_ids": [source_id],
        },
    }
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
    atomic_write_json(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path.relative_to(root))}


def _clear_stale_block(root: Path, source_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """A successful capture removes the BLOCKED.txt an earlier refused attempt left behind."""
    if receipt.get("status") == "captured":
        (root / "01-sources/captures" / source_id / "BLOCKED.txt").unlink(missing_ok=True)
    return receipt


def _capture_page(
    root: Path,
    *,
    url: str,
    source_id: str,
    grade: str,
    store: RuntimeStore | None,
    use_browser: bool | None,
) -> dict[str, Any]:
    try:
        receipt = capture_source_part(root, url=url, source_id=source_id, grade=grade, store=store)
    except Exception as error:  # every source receives a terminal disposition
        reason = f"{type(error).__name__}: {error}"
        if getattr(error, "code", None) in REFUSAL_STATUSES and (use_browser if use_browser is not None else browser_available()):
            # Some sites refuse plain HTTP clients but serve a real browser.
            return _browser_capture(root, url=url, source_id=source_id, grade=grade, http_reason=reason)
        return _blocked_receipt(root, source_id, url, reason)
    landed = str(receipt.get("source", {}).get("url", "")).casefold()
    redirect = next((marker for marker in REFUSAL_URL_MARKERS if marker in landed), "")
    if redirect:
        # The request was redirected to a bot check, not to the content.
        reason = f"redirected to a bot check ({redirect})"
        if use_browser if use_browser is not None else browser_available():
            return _browser_capture(root, url=url, source_id=source_id, grade=grade, http_reason=reason)
        return _blocked_receipt(root, source_id, url, reason)
    directory = root / "01-sources/captures" / source_id
    pdf_path = directory / "source.pdf"
    if pdf_path.is_file():
        try:
            pages = _pdf_text(pdf_path, directory / "content.txt")
        except Exception as error:
            return _blocked_receipt(root, source_id, url, f"PDF text derivation failed: {error}")
        return _finish_derivative(
            root, receipt, directory / "content.txt",
            "public HTTP capture (application/pdf) + pdftotext", f"{pages} PDF pages with page markers",
        )
    text_path = directory / "content.txt"
    thin = (
        receipt["status"] == "captured"
        and text_path.is_file()
        and len(text_path.read_text(encoding="utf-8", errors="replace").strip()) < MIN_HTML_TEXT_CHARACTERS
    )
    if thin or receipt["status"] != "captured":
        if use_browser is None:
            use_browser = browser_available()
        if not use_browser:
            if receipt["status"] == "captured":
                return receipt
            return _blocked_receipt(
                root, source_id, url, "no canonical text from HTTP capture and no headless browser is available"
            )
        try:
            rendered = _browser_render(url)
        except Exception as error:
            if receipt["status"] == "captured":
                return receipt
            return _blocked_receipt(root, source_id, url, f"browser render failed: {error}")
        refusal = _refusal_marker(rendered)
        if refusal:
            if receipt["status"] == "captured":
                return receipt
            return _blocked_receipt(root, source_id, url, f"headless browser got {refusal}")
        atomic_write_text(directory / "rendered.html", rendered.get("html", ""))
        atomic_write_text(text_path, re.sub(r"\n{3,}", "\n\n", rendered.get("text", "")).strip() + "\n")
        receipt["local_paths"] = list(dict.fromkeys([*receipt["local_paths"], str((directory / "rendered.html").relative_to(root))]))
        if rendered.get("title") and receipt["source"]["title"] in {"", url}:
            receipt["source"]["title"] = rendered["title"]
        if not receipt["source"].get("date published"):
            receipt["source"]["date published"] = _embedded_publish_date(rendered.get("html", ""))
        return _finish_derivative(
            root, receipt, text_path, "public HTTP capture + headless browser text",
            "JavaScript-rendered page; text taken from the rendered DOM",
        )
    return receipt


GIT_CACHE = "tools/outputs/git-cache"
_repo_locks: dict[str, threading.Lock] = {}
_repo_locks_guard = threading.Lock()


def _git(args: list[str], cwd: Path | None = None, timeout: int = 60) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def _github_checkout(root: Path, owner: str, repo: str) -> Path:
    """Clone a public repository once per run, with its full history, every branch, and every
    pull request head, and reuse it for every source in it."""
    key = f"{owner}/{repo}".casefold()
    with _repo_locks_guard:
        lock = _repo_locks.setdefault(key, threading.Lock())
    target = root / GIT_CACHE / owner.casefold() / repo.casefold()
    environment = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}
    with lock:
        if not (target / ".git").is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            command = ["clone", "--filter=blob:none", "--quiet", f"https://github.com/{owner}/{repo}", str(target)]
            for attempt in (1, 2):
                result = subprocess.run(["git", *command], text=True, capture_output=True, timeout=900, env=environment)
                if result.returncode == 0:
                    break
                shutil.rmtree(target, ignore_errors=True)
                # One retry for the git proxy's per-repository concurrency limit.
                if attempt == 1 and "429" in result.stderr:
                    time.sleep(5)
                    continue
                raise RuntimeError(f"git clone of {owner}/{repo} failed: {result.stderr.strip()[:300]}")
        if not (target / ".git" / "refs" / "remotes" / "pull").exists() and not (target / ".git" / "work-refs").exists():
            # Earlier runs cached shallow default-branch clones; deepen them and fetch
            # every branch and pull request head, so unmerged work is visible too.
            shallow = _git(["rev-parse", "--is-shallow-repository"], cwd=target).strip() == "true"
            fetch = ["fetch", "--quiet", "--filter=blob:none", *(["--unshallow"] if shallow else []), "origin",
                     "+refs/heads/*:refs/remotes/origin/*", "+refs/pull/*/head:refs/remotes/pull/*"]
            result = subprocess.run(["git", *fetch], cwd=target, text=True, capture_output=True, timeout=900, env=environment)
            if result.returncode != 0:
                raise RuntimeError(f"git fetch of {owner}/{repo} branches failed: {result.stderr.strip()[:300]}")
            (target / ".git" / "work-refs").write_text("fetched\n", encoding="utf-8")
        return target


# Repository text included in a capture, so extraction can read what the code
# does rather than only what its README says. Docs and manifests come first,
# then source code, then other text such as datasets, until the budget is used.
REPOSITORY_TEXT_BUDGET = 1_000_000
REPOSITORY_FILE_LIMIT = 250_000
SKIPPED_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Cargo.lock", "go.sum"}
MANIFEST_NAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "package.json", "Dockerfile",
    "docker-compose.yml", "Makefile", "plugin.json", "marketplace.json", "manifest.json", "SKILL.md",
}
CODE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".rb", ".sh",
    ".sql", ".yaml", ".yml", ".toml", ".ini", ".cfg",
}


def _repository_rank(path: str) -> tuple[int, str]:
    name = Path(path).name
    if name.upper().startswith("README") or (path.endswith(".md") and "/" not in path):
        return (0, path)
    if name in MANIFEST_NAMES or path.startswith(".github/"):
        return (1, path)
    if Path(path).suffix in CODE_SUFFIXES or path.endswith(".md"):
        return (2, path)
    return (3, path)


def _repository_text(checkout: Path, listed: list[str]) -> list[str]:
    """File contents in priority order within the budget, with every omission listed.

    A file over the per-file limit waits for a second pass and is included if the
    budget still has room, so one large data file never crowds out the code but is
    not dropped when there is space for it.
    """
    lines: list[str] = []
    used = 0
    omitted: list[str] = []
    deferred: list[tuple[str, str]] = []
    for path in sorted(listed, key=_repository_rank):
        file_path = checkout / path
        if Path(path).name in SKIPPED_FILES or not file_path.is_file():
            omitted.append(f"{path} (lockfile or not a file)")
            continue
        data = file_path.read_bytes()
        if path.casefold().endswith(".pdf") and shutil.which("pdftotext"):
            # A document kept in a repository (notes, a proposal) is read as text.
            with tempfile.TemporaryDirectory() as scratch:
                try:
                    pages = _pdf_text(file_path, Path(scratch) / "pdf.txt")
                    text = re.sub("[\u200b\u200c\u200d\ufeff]", "", (Path(scratch) / "pdf.txt").read_text(encoding="utf-8"))
                    path = f"{path} (PDF, {pages} pages, as text)"
                except RuntimeError as error:
                    omitted.append(f"{path} (PDF text failed: {str(error)[:80]})")
                    continue
        elif b"\0" in data[:8192]:
            omitted.append(f"{path} (binary)")
            continue
        else:
            text = data.decode("utf-8", errors="replace")
        if len(text) > REPOSITORY_FILE_LIMIT:
            deferred.append((path, text))
            continue
        if used + len(text) > REPOSITORY_TEXT_BUDGET:
            omitted.append(f"{path} (capture budget reached)")
            continue
        used += len(text)
        lines += ["", f"--- FILE: {path} ({text.count(chr(10)) + 1} lines) ---", text.rstrip("\n")]
    for path, text in deferred:
        if used + len(text) > REPOSITORY_TEXT_BUDGET:
            omitted.append(f"{path} ({len(text)} characters, over the remaining capture budget)")
            continue
        used += len(text)
        lines += ["", f"--- FILE: {path} ({text.count(chr(10)) + 1} lines) ---", text.rstrip("\n")]
    if omitted:
        lines += ["", f"--- FILES NOT INCLUDED ({len(omitted)}) ---", *omitted]
    return lines


# History and work that is not on the default branch: the commit log, every
# commit's changes (earlier versions of files show how deals, projects, and the
# company moved), then each branch or pull request the default branch lacks.
HISTORY_LIMIT = 2_000
CHANGE_HISTORY_BUDGET = 1_500_000
CHANGE_COMMIT_LIMIT = 200_000
UNMERGED_TEXT_BUDGET = 600_000
UNMERGED_REF_LIMIT = 300_000
BOT_MARKERS = ("[bot]", "dependabot", "renovate")


def _commit_history(checkout: Path, scope: str = "") -> list[str]:
    log = _git(["log", "--format=%cs %h %s", "--", scope or "."], cwd=checkout).splitlines()
    if not log:
        return []
    under = f" under {scope}" if scope else ""
    lines = ["", f"--- COMMIT HISTORY OF THE DEFAULT BRANCH{under} ({len(log)} commits, {log[-1][:10]} to {log[0][:10]}) ---"]
    lines += log[:HISTORY_LIMIT]
    if len(log) > HISTORY_LIMIT:
        lines.append(f"... {len(log) - HISTORY_LIMIT} earlier commits")
    return lines


def _change_history(checkout: Path, scope: str = "") -> list[str]:
    """Every human commit's changes on the default branch, oldest first.

    Earlier versions of files are evidence too: an account book's stages over
    time, a plan's revisions, a product's growth. Within the budget the newest
    commits are kept (a fork's upstream history is oldest); commits by bots and
    lockfile changes are left out, and every omission is listed.
    """
    rows = _git(["log", "--no-merges", "--format=%H%x09%cs%x09%an%x09%ae%x09%s", "--", scope or "."], cwd=checkout).splitlines()
    kept: list[list[str]] = []
    omitted: list[str] = []
    used = 0
    excludes = [f":(exclude,glob)**/{name}" for name in sorted(SKIPPED_FILES)]
    for row in rows:
        sha, day, author, email, subject = (row.split("\t") + [""] * 5)[:5]
        if any(marker in f"{author} {email}".casefold() for marker in BOT_MARKERS):
            continue
        if used >= CHANGE_HISTORY_BUDGET:
            omitted.append(f"{day} {sha[:7]} {subject} (history budget reached)")
            continue
        patch = _git(["show", "--no-color", "--format=", sha, "--", scope or ".", *excludes], cwd=checkout, timeout=300)
        if len(patch) > CHANGE_COMMIT_LIMIT or used + len(patch) > CHANGE_HISTORY_BUDGET:
            stat = _git(["show", "--format=", "--stat=200", sha, "--", scope or ".", *excludes], cwd=checkout).rstrip()
            kept.append([f"=== COMMIT {sha[:7]} {day} {subject} (diff of {len(patch)} characters not included; files changed below) ===", stat])
            used += len(stat)
            continue
        used += len(patch)
        kept.append([f"=== COMMIT {sha[:7]} {day} {subject} ===", patch.replace("\0", "").rstrip("\n")])
    if not kept:
        return []
    lines = ["", f"--- CHANGE HISTORY OF THE DEFAULT BRANCH ({len(kept)} commits with their changes, oldest first) ---",
             "Each commit shows what changed that day: removed lines (-) are earlier versions that were overwritten."]
    for block in reversed(kept):
        lines += ["", *block]
    if omitted:
        lines += ["", f"--- EARLIER COMMITS NOT SHOWN ({len(omitted)}) ---", *omitted]
    return lines


def _unmerged_work(checkout: Path, scope: str = "", merged: frozenset[int] = frozenset()) -> tuple[list[str], str]:
    """Branches and pull request heads with commits the default branch lacks.

    Refs whose commits are all by bots (dependency bumps) are skipped; refs with the
    same human commits are reported once, under every name. Returns the text and
    the latest unmerged commit date.
    """
    refs = _git(["for-each-ref", "--format=%(refname)", "refs/remotes/origin", "refs/remotes/pull"], cwd=checkout).split()
    groups: dict[frozenset[str], list[str]] = {}
    for ref in refs:
        if ref.endswith("/HEAD"):
            continue
        commits = _git(["log", "--format=%H\t%an\t%ae", ref, "^HEAD", "--", scope or "."], cwd=checkout).splitlines()
        human = frozenset(
            row.split("\t")[0] for row in commits
            if not any(marker in row.casefold() for marker in BOT_MARKERS)
        )
        if human:
            groups.setdefault(human, []).append(ref)
    # A ref whose human commits another ref already carries is that ref's earlier state.
    kept = [key for key in groups if not any(key < other for other in groups)]
    if not kept:
        checked = len([ref for ref in refs if not ref.endswith("/HEAD")])
        return ["", f"--- WORK NOT ON THE DEFAULT BRANCH (none: {checked} branch and pull request refs checked, "
                    "all contained in the default branch or bot-only) ---"], ""
    lines = ["", f"--- WORK NOT ON THE DEFAULT BRANCH ({len(kept)} branches or pull requests, unmerged) ---",
             "Unmerged work is built but not merged into the default branch, so not shipped. "
             "Each block is dated by its own commits."]
    used = 0
    latest = ""
    for key in sorted(kept, key=lambda item: -len(item)):
        names = sorted(ref.removeprefix("refs/remotes/").removeprefix("origin/") for ref in groups[key])
        names = [name if not name.startswith("pull/") else f"pull request #{name.split('/')[1]}" for name in names]
        ref = groups[key][0]
        log = [row for row in _git(["log", "--format=%cs %h %s", ref, "^HEAD", "--", scope or "."], cwd=checkout).splitlines()]
        first, last = log[-1][:10], log[0][:10]
        latest = max(latest, last)
        diff = _git(["diff", "--stat=200", "HEAD..." + ref, "--", scope or "."], cwd=checkout).rstrip()
        numbers = {int(name.rsplit("#", 1)[1]) for name in names if name.startswith("pull request #")}
        if numbers & merged:
            # Merged on github.com by squash or rebase: the default branch carries the
            # change under different commits, so it is shipped, not unmerged.
            lines += ["", f"=== MERGED BY SQUASH OR REBASE: {', '.join(names)} ({len(log)} commits, {first} to {last}; "
                          "the pull request page shows it merged, so this work is on the default branch) ===",
                      *log, "", diff]
            continue
        lines += ["", f"=== UNMERGED: {', '.join(names)} ({len(log)} commits, {first} to {last}) ===", *log, "", diff]
        changed = _git(["diff", "--name-only", "--diff-filter=AM", "HEAD..." + ref, "--", scope or "."], cwd=checkout).splitlines()
        patch_paths = [path for path in changed if Path(path).name not in SKIPPED_FILES]
        if not patch_paths:
            continue
        patch = _git(["diff", "--no-color", "HEAD..." + ref, "--", *patch_paths], cwd=checkout, timeout=120)
        if "\0" in patch:
            patch = patch.replace("\0", "")
        if len(patch) > UNMERGED_REF_LIMIT or used + len(patch) > UNMERGED_TEXT_BUDGET:
            lines.append(f"(diff of {len(patch)} characters not included: over the unmerged-work budget)")
            continue
        used += len(patch)
        lines += ["", patch.rstrip("\n")]
    return lines, latest


# Pull request and issue conversations (titles, descriptions, comments, reviews,
# and their dates) are github.com pages, not repository content. Plain requests
# to them are refused here, but the headless browser renders them.
CONVERSATION_BUDGET = 800_000
CONVERSATION_PAGE_LIMIT = 150_000
CONVERSATION_LIMIT = 300
GITHUB_PAGE_SCRIPT = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      userAgent: process.argv[2], viewport: { width: 1440, height: 900 }, locale: 'en-US',
    });
    await page.goto(process.argv[1], { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(1500);
    const result = await page.evaluate(() => {
      // Relative times ("last week") become the dates they stand for.
      for (const node of document.querySelectorAll('relative-time, time-ago, local-time, time')) {
        const when = node.getAttribute('datetime');
        if (when) node.replaceWith(document.createTextNode(when.slice(0, 10)));
      }
      const main = document.querySelector('main') || document.body;
      const links = Array.from(document.querySelectorAll('a[href]')).map((a) => a.getAttribute('href'));
      return { text: main ? main.innerText : '', links };
    });
    process.stdout.write(JSON.stringify({ url: page.url(), title: await page.title(), ...result }));
  } finally {
    await browser.close();
  }
})().catch((error) => { process.stderr.write(String(error)); process.exit(1); });
"""


def _github_page(url: str) -> dict[str, Any]:
    with _browser_slots:
        result = subprocess.run(
            ["node", "-e", GITHUB_PAGE_SCRIPT, url, DESKTOP_USER_AGENT], text=True, capture_output=True, timeout=150
        )
    if result.returncode != 0:
        raise RuntimeError(f"browser render failed: {(result.stderr.strip().splitlines() or ['no output'])[0][:200]}")
    rendered = json.loads(result.stdout)
    if _refusal_marker(rendered) or len(rendered.get("text", "").strip()) < 100:
        raise RuntimeError(_refusal_marker(rendered) or "page rendered no text")
    return rendered


def _conversation_numbers(checkout: Path, scope: str = "") -> list[int]:
    """Pull request numbers worth reading: every human pull request in a repository, or for a
    path inside someone else's repository, the pull requests that changed that path."""
    numbers: set[int] = set()
    for ref in _git(["for-each-ref", "--format=%(refname)", "refs/remotes/pull"], cwd=checkout).split():
        number = ref.rsplit("/", 1)[-1]
        if not number.isdigit():
            continue
        head = _git(["log", "-1", "--format=%an %ae", ref], cwd=checkout).casefold()
        if any(marker in head for marker in BOT_MARKERS):
            continue
        if not scope or _git(["log", "--format=%h", ref, "^HEAD", "--", scope], cwd=checkout).strip():
            numbers.add(int(number))
    if scope:
        # Merged pull requests name themselves in the commits they left on the path.
        subjects = _git(["log", "--format=%s", "--", scope], cwd=checkout)
        numbers.update(int(value) for value in re.findall(r"(?:pull request |\(|\s)#(\d+)\b", subjects))
    return sorted(numbers)


def _issue_numbers(owner: str, repo: str) -> list[int]:
    numbers: set[int] = set()
    pattern = re.compile(rf"^/{re.escape(owner)}/{re.escape(repo)}/issues/(\d+)$", re.IGNORECASE)
    for page in range(1, 11):
        try:
            listing = _github_page(f"https://github.com/{owner}/{repo}/issues?q=is%3Aissue&page={page}")
        except Exception as error:
            if page == 1:
                raise RuntimeError(f"the issue list could not be read: {str(error)[:120]}") from error
            break
        found = {int(match.group(1)) for link in listing.get("links", []) if (match := pattern.match(str(link or "")))}
        if not found - numbers:
            break
        numbers |= found
    return sorted(numbers)


MERGED_PAGE = re.compile(r"\bmerged \d+ commits? into\b")


def _github_conversations(checkout: Path, owner: str, repo: str, scope: str = "") -> tuple[list[str], frozenset[int]]:
    """Pull request and issue pages as text, with their dates, within the budget, and the
    numbers of the pull requests the pages show as merged."""
    if not browser_available():
        return ["", "--- PULL REQUESTS AND ISSUES NOT CAPTURED (no headless browser on this host) ---"], frozenset()
    targets = [("pull", number) for number in _conversation_numbers(checkout, scope)]
    unread = ""
    if not scope:
        try:
            targets += [("issues", number) for number in _issue_numbers(owner, repo)]
        except RuntimeError as error:
            unread = str(error)
    lines: list[str] = []
    missed: list[str] = []
    merged: set[int] = set()
    used = 0
    for kind, number in targets[:CONVERSATION_LIMIT]:
        url = f"https://github.com/{owner}/{repo}/{kind}/{number}"
        try:
            rendered = _github_page(url)
        except Exception as error:
            missed.append(f"{url} ({str(error)[:120]})")
            continue
        text = re.sub(r"\n{3,}", "\n\n", rendered.get("text", "")).strip()[:CONVERSATION_PAGE_LIMIT]
        if used + len(text) > CONVERSATION_BUDGET:
            missed.append(f"{url} (conversation budget reached)")
            continue
        used += len(text)
        if kind == "pull" and MERGED_PAGE.search(text[:1500]):
            merged.add(number)
        label = "PULL REQUEST" if kind == "pull" else "ISSUE"
        lines += ["", f"=== {label} #{number}: {rendered.get('title', '')} ({url}) ===", text]
    if not targets:
        issues = f"; {unread}" if unread else ("" if scope else ", and the issue list on github.com is empty")
        return ["", f"--- PULL REQUESTS AND ISSUES (none: no pull request refs{issues}) ---"], frozenset()
    header = [
        "", f"--- PULL REQUESTS AND ISSUES ({len(targets) - len(missed)} of {len(targets)}, rendered from github.com; "
        "dates are the pages' own timestamps) ---",
    ]
    if unread:
        missed.append(unread)
    if missed:
        lines += ["", f"--- CONVERSATIONS NOT CAPTURED ({len(missed)}) ---", *missed]
    return header + lines, frozenset(merged)


def _github_conversation_capture(root: Path, *, url: str, source_id: str, grade: str) -> dict[str, Any]:
    """A single pull request, issue, or discussion page, rendered with its dates."""
    rendered = _github_page(url)
    text = re.sub(r"\n{3,}", "\n\n", rendered.get("text", "")).strip()
    directory = root / "01-sources/captures" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    text_path = directory / "content.txt"
    atomic_write_text(text_path, f"Page: {url}\nTitle: {rendered.get('title', '')}\n\n{text}\n")
    dates = sorted(re.findall(r"\b(20\d\d-\d\d-\d\d)\b", text))
    relative_text = str(text_path.relative_to(root))
    parsed = [part for part in urlparse(url).path.split("/") if part]
    source = {
        "id": source_id, "grade": grade, "title": rendered.get("title", "") or url,
        "publisher": f"GitHub ({parsed[0]})", "url": url,
        "date published": dates[0] if dates else "", "date last modified": dates[-1] if dates else "",
        "date captured": datetime.now(timezone.utc).date().isoformat(),
        "local file": relative_text, "method": "headless browser render of the github.com page",
        "notes": "Opened on its earliest timestamp, last activity on its latest; both from the page",
    }
    receipt = {
        "schema_version": "1.0.0", "task_type": "capture", "source_id": source_id, "status": "captured",
        "source": source, "local_paths": [relative_text], "content_bytes": len(text.encode("utf-8")),
        "estimated_tokens": max(1, len(text) // 4), "canonical_text_ready": True, "captured_at": utc_now(),
        "disposition": {
            "input_id": source_id, "disposition": "completed", "reason": "rendered with a headless browser",
            "evidence_paths": [relative_text], "output_ids": [source_id],
        },
    }
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
    atomic_write_json(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path.relative_to(root))}


def _github_capture(root: Path, *, url: str, source_id: str, grade: str) -> dict[str, Any]:
    """Capture a public GitHub repository, directory, or file through git rather than web pages."""
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) < 2:
        raise RuntimeError(
            "a GitHub organization or user listing needs the GitHub API, which this session cannot reach; "
            "its public repositories are captured individually"
        )
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if len(parts) > 3 and parts[2] in {"pull", "issues", "discussions"}:
        # Conversations are github.com pages, not repository content.
        return _github_conversation_capture(root, url=url, source_id=source_id, grade=grade)
    if len(parts) > 2 and parts[2] not in {"tree", "blob"}:
        raise RuntimeError(f"a GitHub {parts[2]} page is neither repository content nor a conversation page")
    checkout = _github_checkout(root, owner, repo)
    unmerged_latest = ""
    relative = "/".join(parts[4:]) if len(parts) > 4 and parts[2] in {"tree", "blob"} else ""
    commit, committed = _git(["log", "-1", "--format=%H %cI"], cwd=checkout).split()
    lines = [
        f"Repository: {owner}/{repo}",
        f"Source URL: {url}",
        f"Captured commit: {commit} (committed {committed})",
        "Method: git clone of the public repository with its history, branches, and pull request heads",
        "",
    ]
    target = checkout / relative if relative else checkout
    if target.is_file():
        lines += [f"--- FILE: {relative} ---", target.read_text(encoding="utf-8", errors="replace")[:200_000]]
    elif target.is_dir():
        listed = _git(["ls-files", "--", relative or "."], cwd=checkout).splitlines()
        lines += [f"--- FILE TREE ({len(listed)} files{', under ' + relative if relative else ''}) ---", *listed[:500]]
        if len(listed) > 500:
            lines.append(f"... {len(listed) - 500} more files")
        lines += _repository_text(checkout, listed)
    # A path inside a repository gets that path's history, unmerged work, and
    # the pull requests that changed it; a whole repository gets all of them.
    if target.exists():
        lines += _commit_history(checkout, relative)
        lines += _change_history(checkout, relative)
        conversations, merged = _github_conversations(checkout, owner, repo, relative)
        unmerged, unmerged_latest = _unmerged_work(checkout, relative, merged)
        lines += unmerged
        lines += conversations
    else:
        raise RuntimeError(f"{relative} is not in {owner}/{repo} at its default branch head")
    directory = root / "01-sources/captures" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    text_path = directory / "content.txt"
    atomic_write_text(text_path, "\n".join(lines).rstrip() + "\n")
    content = text_path.read_text(encoding="utf-8")
    relative_text = str(text_path.relative_to(root))
    source = {
        "id": source_id, "grade": grade,
        "title": f"{owner}/{repo}" + (f": {relative}" if relative else ""),
        "publisher": f"GitHub ({owner})", "url": url,
        "date published": "", "date last modified": max(committed[:10], unmerged_latest),
        "date captured": datetime.now(timezone.utc).date().isoformat(),
        "local file": relative_text, "method": "git clone of public repository",
        "notes": (
            f"Default branch at commit {commit[:12]} ({committed[:10]})"
            + (f"; unmerged branch or pull request work to {unmerged_latest}" if unmerged_latest else "")
            + "; last-modified is the latest commit's date, not a publication date"
        ),
    }
    receipt = {
        "schema_version": "1.0.0", "task_type": "capture", "source_id": source_id, "status": "captured",
        "source": source, "local_paths": [relative_text], "content_bytes": len(content.encode("utf-8")),
        "estimated_tokens": max(1, len(content) // 4), "canonical_text_ready": True,
        "captured_at": utc_now(),
        "disposition": {
            "input_id": source_id, "disposition": "completed", "reason": "captured from git",
            "evidence_paths": [relative_text], "output_ids": [source_id],
        },
    }
    receipt_path = root / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
    atomic_write_json(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path.relative_to(root))}
