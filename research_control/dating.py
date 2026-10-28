"""Date every captured source by its content, with its age at the research date.

A source is dated by what it reflects, not by when it was captured: a
published date, a date the page embeds (a video's upload date), a
last-modified or last-commit date. Its age in quarters is measured against the
research date, so stale evidence is flagged wherever it is used.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_control.capture import _embedded_publish_date, _iso_date
from research_control.io import atomic_write_jsonl, atomic_write_text, load_json, load_jsonl

SOURCE_DATES = "tools/outputs/source-dates.jsonl"
DATE_OVERRIDES = "tools/lists/source-date-overrides.jsonl"
DATING_REPORT = "06-checks/source-dating.md"
PAGE_FILES = ("raw.html", "rendered.html")
LIVE_FILES = (*PAGE_FILES, "raw.txt", "raw.json")


def research_date(root: Path) -> date:
    state = root / "tools/outputs/run-state.json"
    created = load_json(state).get("created_at", "") if state.is_file() else ""
    return date.fromisoformat(created[:10]) if created[:10] else date.today()


def _as_date(value: str) -> date | None:
    text = _iso_date(value or "")
    try:
        return date.fromisoformat(text) if len(text) == 10 else None
    except ValueError:
        return None


def _media_info_date(directory: Path) -> tuple[date | None, str]:
    """The release or upload date that yt-dlp or Invidious recorded beside a media capture."""
    for path in sorted(directory.glob("*.info.json")):
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key in ("release_date", "upload_date"):
            value = str(info.get(key) or "")
            if len(value) == 8 and value.isdigit():
                return date(int(value[:4]), int(value[4:6]), int(value[6:])), f"{key.replace('_', ' ')} in {path.name}"
        for key in ("release_timestamp", "timestamp"):
            if isinstance(info.get(key), (int, float)):
                return datetime.fromtimestamp(info[key], timezone.utc).date(), f"{key.replace('_', ' ')} in {path.name}"
    return None, ""


def _channel(directory: Path) -> str:
    """The channel or uploader a media route recorded, where there is one."""
    for path in sorted(directory.glob("*.info.json")):
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key in ("channel", "uploader", "author"):
            if info.get(key):
                return str(info[key])
    return ""


def _flag(content: date, as_of: date) -> tuple[float, str]:
    quarters = round(max((as_of - content).days, 0) / 91.3, 1)
    return quarters, "current" if quarters < 1 else "as of" if quarters <= 2 else "dated"


RECORDED = re.compile(r"Recorded:\s*(\d{4}-\d{2}-\d{2})")


def recorded_dates(root: Path) -> dict[str, tuple[str, str]]:
    """Recording dates that extraction found stated in recordings, by source:
    the earliest stated date and the note that states it."""
    found: dict[str, tuple[str, str]] = {}
    for path in sorted((root / "tools/outputs/worker-parts/extraction").glob("*.candidates.jsonl")):
        for row in load_jsonl(path):
            match = RECORDED.search(str(row.get("notes", "")))
            if match and _as_date(match.group(1)):
                source_id = str(row.get("source_id", ""))
                note = str(row.get("notes", ""))[:240]
                if source_id not in found or match.group(1) < found[source_id][0]:
                    found[source_id] = (match.group(1), note)
    return found


def date_source(
    root: Path, receipt: dict[str, Any], as_of: date, override: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The content date, its basis, and its age flag for one capture receipt.

    An override (a date a worker found on the episode page, feed, or upload
    metadata) wins over what the capture recorded, and keeps its evidence.
    """
    source = receipt.get("source", {})
    source_id = str(receipt.get("source_id") or source.get("id", ""))
    content: date | None = _as_date(str(override.get("date", ""))) if override else None
    basis = f"{override.get('basis', 'found by a dating pass')} ({override.get('evidence', '')})" if content and override else ""
    published = _as_date(str(source.get("date published", "")))
    if content is None and published:
        content, basis = published, "published"
    if content is None:
        # A video's air or upload date, recorded by the route that fetched it.
        content, basis = _media_info_date(root / "01-sources/captures" / source_id)
    if content is None:
        directory = root / "01-sources/captures" / source_id
        for name in PAGE_FILES:
            page = directory / name
            if page.is_file():
                embedded = _as_date(_embedded_publish_date(page.read_text(encoding="utf-8", errors="replace")))
                if embedded:
                    content, basis = embedded, f"date embedded in {name}"
                    break
    if content is None:
        modified = _as_date(str(source.get("date last modified", "")))
        if modified:
            git = "git" in str(source.get("method", "")).casefold()
            content, basis = modified, "last commit" if git else "last modified"
    captured = _as_date(str(source.get("date captured", "")))
    directory = root / "01-sources/captures" / source_id
    live_page = (
        content is None and captured is not None
        and not (directory / "transcript.txt").is_file()
        and any((directory / name).is_file() for name in LIVE_FILES)
    )
    if live_page:
        # An undated live page or feed (a job board, a query result) shows what it said
        # when captured: that is its snapshot.
        content, basis = captured, "live page at capture" if any((directory / name).is_file() for name in PAGE_FILES) else "live data at capture"
    row: dict[str, Any] = {
        "source_id": source_id,
        "url": source.get("url", ""),
        "platform": (urlparse(str(source.get("url", ""))).hostname or "").removeprefix("www."),
        "publisher": _channel(root / "01-sources/captures" / source_id) or str(source.get("publisher", "")),
        "content_date": content.isoformat() if content else "",
        "basis": basis or "undated",
        "captured": captured.isoformat() if captured else "",
    }
    if content is None:
        row.update({"age_quarters": None, "flag": "undated"})
        return row
    quarters = round(max((as_of - content).days, 0) / 91.3, 1)
    flag = "current" if quarters < 1 else "as of" if quarters <= 2 else "dated"
    row.update({"age_quarters": quarters, "flag": flag})
    return row


def write_source_dates(root: Path, receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Date every captured source and write the dating table and its report."""
    as_of = research_date(root)
    overrides_path = root / DATE_OVERRIDES
    overrides = {str(row.get("source_id")): row for row in load_jsonl(overrides_path)} if overrides_path.is_file() else {}
    recorded = recorded_dates(root)
    rows = [
        date_source(root, receipt, as_of, overrides.get(str(receipt.get("source_id"))))
        for receipt in receipts if receipt.get("status") == "captured"
    ]
    # What a recording says about when it was recorded dates what was said in it;
    # the posting date is kept beside it.
    for row in rows:
        row["posted_date"] = row["content_date"]
        stated = recorded.get(row["source_id"])
        if not stated:
            continue
        row["recorded_date"], row["recorded_basis"] = stated
        recorded_on = date.fromisoformat(stated[0])
        if row["content_date"] and abs((date.fromisoformat(row["content_date"]) - recorded_on).days) <= 3:
            continue
        row["date_note"] = f"recorded {stated[0]}, posted {row['content_date'] or 'undated'}"
        row["content_date"] = stated[0]
        row["basis"] = f"recorded date stated in the recording (posted {row['posted_date'] or 'undated'})"
        row["age_quarters"], row["flag"] = _flag(recorded_on, as_of)
    rows.sort(key=lambda row: row["source_id"])
    atomic_write_jsonl(root / SOURCE_DATES, rows)
    counts = {flag: sum(1 for row in rows if row["flag"] == flag) for flag in ("current", "as of", "dated", "undated")}
    lines = [
        "# Source dating",
        "",
        f"Every captured source is dated by its content, not its capture, as of the research date {as_of.isoformat()}.",
        "Flags: `current` under one quarter old; `as of` one to two quarters, cited with its date; "
        "`dated` more than two quarters, cited with its date and age wherever used; `undated` no content date found, "
        "so its capture date is only an upper bound.",
        "",
        "| Flag | Sources |",
        "|---|---|",
        *(f"| {flag} | {count} |" for flag, count in counts.items()),
        "",
        "## Dated and undated sources",
        "",
        "| Source | Content date | Basis | Age (quarters) | Flag | URL |",
        "|---|---|---|---|---|---|",
    ]
    mismatched = [row for row in rows if row.get("date_note")]
    lines += [
        f"| `{row['source_id']}` | {row['content_date'] or '—'} | {row['basis']} | "
        f"{'' if row['age_quarters'] is None else row['age_quarters']} | {row['flag']} | {row['url']} |"
        for row in rows if row["flag"] in {"dated", "undated"}
    ]
    lines += [
        "",
        f"## Recordings dated differently from their posting ({len(mismatched)})",
        "",
        "| Source | Recorded | Posted | Stated in the recording | Publisher | URL |",
        "|---|---|---|---|---|---|",
        *(
            f"| `{row['source_id']}` | {row['recorded_date']} | {row['posted_date'] or '—'} | "
            f"{row['recorded_basis'].replace('|', '/')} | {row['publisher']} | {row['url']} |"
            for row in mismatched
        ),
    ]
    atomic_write_text(root / DATING_REPORT, "\n".join(lines) + "\n")
    return {"sources": len(rows), **counts}
