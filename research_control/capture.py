"""Conservative public-page capture helper used by the agent orchestrator."""

from __future__ import annotations

import csv
import ipaddress
import json
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from research_control.io import atomic_write_json, atomic_write_text, utc_now
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
    const page = await browser.newPage({ userAgent: process.argv[2] });
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


def browser_available() -> bool:
    if shutil.which("node") is None:
        return False
    probe = subprocess.run(
        ["node", "-e", "require('playwright')"], text=True, capture_output=True, timeout=30
    )
    return probe.returncode == 0


def _browser_render(url: str) -> dict[str, str]:
    _require_public_host(url)
    result = subprocess.run(
        ["node", "-e", BROWSER_SCRIPT, url, USER_AGENT], text=True, capture_output=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"browser render failed: {result.stderr.strip()[:300]}")
    return json.loads(result.stdout)


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

    if media and urlparse(url).path.casefold().endswith(AUDIO_SUFFIXES):
        # A direct audio or video file has no page text; its transcript is the derivative.
        receipt = _blocked_receipt(root, source_id, url, "direct media file; no page text to capture")
    else:
        receipt = _capture_page(root, url=url, source_id=source_id, grade=grade, store=store, use_browser=use_browser)
    if not media:
        return receipt
    from research_control.media import transcribe

    directory = root / "01-sources/captures" / source_id
    result = transcribe(url, directory)
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
        return _blocked_receipt(root, source_id, url, f"{type(error).__name__}: {error}")
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
        atomic_write_text(directory / "rendered.html", rendered.get("html", ""))
        atomic_write_text(text_path, re.sub(r"\n{3,}", "\n\n", rendered.get("text", "")).strip() + "\n")
        receipt["local_paths"] = list(dict.fromkeys([*receipt["local_paths"], str((directory / "rendered.html").relative_to(root))]))
        if rendered.get("title") and receipt["source"]["title"] in {"", url}:
            receipt["source"]["title"] = rendered["title"]
        return _finish_derivative(
            root, receipt, text_path, "public HTTP capture + headless browser text",
            "JavaScript-rendered page; text taken from the rendered DOM",
        )
    return receipt
