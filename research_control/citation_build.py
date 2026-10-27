"""Build the company brief's citations from the fact IDs beside its words.

The report writer keeps fact IDs in square brackets beside the exact words they
support, in prose and in table cells. This script numbers the sources in
reading order (a source keeps its number on every later use), links each
superscript number to the cited fact's deep link (the quoted line at a commit,
the moment in a recording, the quoted words on a page), lists every source once
under the report's Sources heading, and maps each table cell to the facts it
states. Neither the writer nor the fixer numbers citations by hand, so numbering,
links, and source notes cannot drift from the text.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urldefrag
from urllib.request import Request, urlopen

from research_control.io import atomic_write_json, load_json, load_jsonl
from research_control.validators.facts import load_fact_tables, withdrawn_facts

BRIEF = "05-synthesis/company-brief.md"
CITATION_MAP = "tools/outputs/citation-map-company-brief.json"
EXHIBIT_MAP = "tools/outputs/exhibit-map.json"
# Titles found for sources captured without one (a video page that refused the capture, an audio file).
TITLES = "tools/outputs/source-titles.json"
FACT = r"[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?"
# A bracketed group of fact IDs that is not a Markdown link's text.
GROUP = re.compile(rf"\[({FACT}(?:\s*[,;]\s*{FACT})*)\](?!\()")
SOURCES_HEADING = re.compile(r"^##\s+Sources?(?:\s+notes?)?\s*$", re.I)
# Closing sections that hold no claims of their own: they need no citation on every paragraph.
UNCITED_SECTIONS = re.compile(r"open question|whom to ask|limits|^sources?\b|source notes|contents|how to read", re.I)
PARAGRAPH_WORDS = 25
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


REPOSITORY_LINK = re.compile(r"https://github\.com/([^/]+/[^/]+)/(blob|commit|compare|pull)/([^?#]+)")
YOUTUBE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{6,})")
CLOCK = re.compile(r"at (\d+):(\d{2}):(\d{2})")


def _part(link: dict[str, Any]) -> tuple[str, str, str] | None:
    """For a repository fact, the part of the repository it cites: (key, label, link). Different
    files, commits, branches, and pull requests of one repository are separate source entries."""
    if link.get("kind") != "repository" or not link.get("located"):
        return None
    match = REPOSITORY_LINK.match(str(link.get("deep_link", "")))
    if not match:
        return None
    repository, kind, rest = match.groups()
    base = f"https://github.com/{repository}"
    if kind == "blob":
        commit, _, path = rest.partition("/")
        return f"{repository}:{path}", f"file {unquote(path)}", f"{base}/blob/{commit}/{path}"
    if kind == "commit":
        return f"{repository}@{rest}", f"commit {rest[:7]}", f"{base}/commit/{rest}"
    if kind == "pull":
        number = rest.split("/")[0]
        return f"{repository}#{number}", f"pull request #{number}, not merged", f"{base}/pull/{number}"
    return f"{repository}~{rest}", f"branch {rest}, not merged", f"{base}/compare/{rest}"


PASSAGE_WORDS = 6


def _place(link: dict[str, Any], part: tuple[str, str, str] | None, quote: str = "") -> tuple[str, float] | None:
    """Where in the source a fact sits, for the source list: a recording's timestamp, the lines
    of a file or diff, or a page's quoted passage (its first words); with a sort key."""
    anchor = str(link.get("anchor", ""))
    if link.get("kind", "page") == "page" and link.get("located") and quote.strip():
        words = quote.split()
        label = "\u201c" + " ".join(words[:PASSAGE_WORDS]) + ("\u2026" if len(words) > PASSAGE_WORDS else "") + "\u201d"
        return label, 0.0
    clock = CLOCK.match(anchor)
    if link.get("kind") == "recording" and clock:
        hours, minutes, seconds = (int(value) for value in clock.groups())
        label = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
        return label, hours * 3600 + minutes * 60 + seconds
    if part is None:
        return None
    lines = re.search(r"\blines? (\d+)(?:\s*[-–]\s*(\d+))?", anchor)
    if part[1].startswith("file") and lines:
        start, end = lines.group(1), lines.group(2)
        return (f"lines {start} to {end}" if end else f"line {start}"), float(start)
    # A commit or unmerged change: the file and line within it.
    detail = re.sub(r"^(?:commit [0-9a-f]+|branch \S+|pull request #\d+)[,:]?\s*(?:\(unmerged\))?\s*", "", anchor).strip()
    return (detail, float(lines.group(1)) if lines else 0.0) if detail else None


PLATFORM_SUFFIX = re.compile(r"\s*(?:[-|·]\s*)?(?:YouTube|Apple Podcasts|Spotify|LinkedIn|GitHub)\s*$", re.I)


def _clean_title(title: str) -> str:
    """A page's own title without the platform's name tacked on the end."""
    return PLATFORM_SUFFIX.sub("", title.strip()).strip(" -|·")


def _cut_off(title: str) -> bool:
    """Platforms shorten long titles in the page title ("S8E3: Jaclyn Rice Nelson and h…")."""
    return bool(re.search(r"(?:\.\.\.|…)(?:\s*[-|·]|\s*$)", title))


def _found_title(source: dict[str, str], dated: dict[str, Any], known: dict[str, Any], fetch: bool) -> tuple[str, str]:
    """(title, publisher) for a source captured without a title: from the feed item its date was
    read from, a YouTube video's own title (fetched once and kept), or a plain description."""
    source_id, url = source.get("id", ""), source.get("url", "")
    if source_id in known:
        return known[source_id]["title"], known[source_id].get("publisher", "")
    basis = str(dated.get("basis", ""))
    video = YOUTUBE.search(url)
    for pattern, title_group, show_group in ((r'\(([^()"]+)\) item "([^"]+)"', 2, 1), (r'item "([^"]+)"', 1, 0),
                                             (r'\(([^,()"]+), "([^"]+)"\)', 2, 1)):
        match = re.search(pattern, basis)
        if match and not (video and fetch and _cut_off(match.group(title_group))):
            # A feed item's title; a cut-off one for a video is replaced by the video's own title below.
            return match.group(title_group).rstrip(". "), match.group(show_group) if show_group else ""
    if video and fetch:
        try:
            request = Request(f"https://www.youtube.com/oembed?format=json&url={quote('https://www.youtube.com/watch?v=' + video.group(1), safe='')}",
                              headers={"User-Agent": "research-control citation build"})
            with urlopen(request, timeout=15) as response:
                found = json.loads(response.read().decode("utf-8"))
            known[source_id] = {"title": found.get("title", ""), "publisher": found.get("author_name", "")}
            return known[source_id]["title"], known[source_id]["publisher"]
        except (OSError, ValueError):
            pass
    host = re.sub(r"^https?://(www\.)?([^/]+).*$", r"\2", url)
    if video:
        return f"Video on {host}", ""
    if re.search(r"\.(?:mp3|m4a|wav|ogg)\b", url):
        return f"Audio recording on {host}", ""
    return (f"Data query on {host}" if "query=" in url else f"Page on {host}"), ""


def _reader_date(dated: dict[str, Any], published: str) -> str:
    """The source's date as a reader sees it; a live page dated only by its capture says so."""
    posted = str(dated.get("posted_date") or dated.get("content_date") or published or "")
    captured = str(dated.get("captured") or "")
    live = posted and posted == captured and dated.get("flag") == "current"
    match = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", posted)
    if match:
        month = MONTHS[int(match.group(2)) - 1]
        posted = f"{month} {int(match.group(3))}, {match.group(1)}" if match.group(3) else f"{month} {match.group(1)}"
    return f"viewed {posted}" if live else posted


def _canonical(url: str) -> str:
    return urldefrag(url or "")[0].rstrip("/")


def _manifest(root: Path) -> dict[str, dict[str, str]]:
    path = root / "01-sources/MANIFEST.csv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def _by_id(path: Path, key: str) -> dict[str, dict[str, Any]]:
    return {str(row.get(key)): row for row in load_jsonl(path)} if path.is_file() else {}


def citation_groups(markdown: str) -> list[list[str]]:
    """Each bracketed fact-ID group in reading order."""
    return [re.split(r"\s*[,;]\s*", match.group(1)) for match in GROUP.finditer(markdown)]


def _sections(markdown: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.*)$", line)
        if heading:
            sections.append((heading.group(1).strip(), []))
        else:
            sections[-1][1].append(line)
    return sections


def _uncited_paragraphs(markdown: str) -> list[str]:
    problems: list[str] = []
    for heading, lines in _sections(markdown):
        if not heading or UNCITED_SECTIONS.search(heading):
            continue
        blocks, current = [], []
        for line in lines + [""]:
            if not line.strip() or line.lstrip().startswith(("|", "#")) or re.match(r"^\s*([-*]|\d+\.)\s", line):
                if current:
                    blocks.append(" ".join(current))
                current = [line.strip()] if re.match(r"^\s*([-*]|\d+\.)\s", line) else []
                continue
            current.append(line.strip())
        for block in blocks:
            if len(block.split()) >= PARAGRAPH_WORDS and not GROUP.search(block):
                problems.append(f'"{heading}": a paragraph cites no fact: "{" ".join(block.split()[:10])} ..."')
    return problems


def _exhibit_elements(markdown: str) -> tuple[list[dict[str, Any]], list[str]]:
    """One element per table cell that cites facts; a fact-bearing row with none is a problem."""
    elements: list[dict[str, Any]] = []
    problems: list[str] = []
    table = 0
    title = ""
    rows: list[list[str]] = []

    def flush() -> None:
        nonlocal rows, table
        if not rows:
            return
        table += 1
        data = rows[2:] if len(rows) > 1 and all(re.fullmatch(r":?-+:?", cell) for cell in rows[1]) else rows
        for number, row in enumerate(data, 1):
            cited = False
            for column, cell in enumerate(row, 1):
                facts = [fact for group in citation_groups(cell) for fact in group]
                if facts:
                    cited = True
                    elements.append({"element_id": f"exhibit-{table}-row-{number}-col-{column}", "exhibit": title,
                                     "text": GROUP.sub("", cell).strip(), "fact_ids": facts, "evidence_bearing": True})
            # A row with one filled cell is a label or divider, not a claim.
            if not cited and sum(1 for cell in row if cell.strip()) > 1 and title_checked:
                problems.append(f'table "{title or table}": row "{" | ".join(row)[:80]}" cites no fact')
        rows = []

    title_checked = True
    for line in markdown.splitlines():
        if line.lstrip().startswith("|") and line.rstrip().endswith("|"):
            rows.append([cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))])
            continue
        flush()
        heading = re.match(r"^#{2,4}\s+(.*)$", line) or re.match(r"^\*\*(Exhibit[^*]*)\*\*", line.strip())
        if heading:
            title = heading.group(1).strip()
            if line.startswith("## "):
                title_checked = not UNCITED_SECTIONS.search(title)
    flush()
    return elements, problems


def build(root: Path, write: bool = True) -> dict[str, Any]:
    """Number, link, and map the brief's citations; return the maps and any problems."""
    brief = root / BRIEF
    if not brief.is_file():
        return {"problems": [f"{BRIEF} is missing"], "citations": 0}
    markdown = brief.read_text(encoding="utf-8")
    facts = {row["fact_id"]: row for row in load_fact_tables(sorted((root / "02-facts").glob("*.md"))) if row.get("fact_id")}
    links = _by_id(root / "tools/outputs/fact-links.jsonl", "fact_id")
    dates = _by_id(root / "tools/outputs/source-dates.jsonl", "source_id")
    manifest = _manifest(root)
    withdrawn = withdrawn_facts(root)
    known = load_json(root / TITLES) if (root / TITLES).is_file() else {}
    titles_before = len(known)
    problems: list[str] = []
    notes: list[dict[str, Any]] = []
    number_for: dict[str, int] = {}
    citations: list[dict[str, Any]] = []
    for index, group in enumerate(citation_groups(markdown)):
        by_number: dict[int, list[str]] = {}
        for fact_id in group:
            row = facts.get(fact_id)
            if row is None:
                problems.append(f"{fact_id} is not in the fact store")
                continue
            if fact_id in withdrawn:
                problems.append(f"{fact_id} was withdrawn and may not be cited")
            source_id = str(row.get("source_id", "")).strip()
            source = manifest.get(source_id)
            if source is None:
                problems.append(f"{fact_id}: source {source_id or '(none)'} is not in the source list")
                continue
            # The same page or recording is one entry, cited again by the same number wherever it is
            # reused; different parts of a repository (files, commits, unmerged changes) are separate.
            link = links.get(fact_id, {})
            part = _part(link)
            youtube = YOUTUBE.search(source.get("url", ""))
            key = part[0] if part else (f"youtube:{youtube.group(1)}" if youtube else _canonical(source.get("url", "")) or source_id)
            if key not in number_for:
                number_for[key] = len(notes) + 1
                dated = dates.get(source_id, {})
                title, publisher = _clean_title(source.get("title", "")), source.get("publisher") or dated.get("publisher", "")
                if not title or title.startswith("http") or _cut_off(title):
                    found, found_publisher = _found_title(source, dated, known, fetch=write)
                    if found and not (_cut_off(found) and title and not title.startswith("http")):
                        title, publisher = found, found_publisher or publisher
                notes.append({
                    "n": number_for[key], "source_ids": [source_id], "url": part[2] if part else source.get("url", ""),
                    "title": title, "publisher": publisher,
                    "date": _reader_date(dated, source.get("date published", "")),
                    "grade": source.get("grade", ""), **({"part": part[1]} if part else {}), "places": [],
                })
            note = notes[number_for[key] - 1]
            if source_id not in note["source_ids"]:
                note["source_ids"].append(source_id)
            place = _place(link, part, str(row.get("verbatim_quote", "")))
            if place and link.get("deep_link") and link["deep_link"] not in {item["link"] for item in note["places"]}:
                note["places"].append({"label": place[0], "link": link["deep_link"], "order": place[1]})
            by_number.setdefault(number_for[key], []).append(fact_id)
        for number in sorted(by_number):
            note = notes[number - 1]
            located = [fact for fact in by_number[number]
                       if links.get(fact, {}).get("located") and links[fact].get("deep_link")]
            place = _place(links[located[0]], _part(links[located[0]]), str(facts[located[0]].get("verbatim_quote", ""))) if located else None
            citations.append({"n": number, "group": index, "facts": by_number[number],
                              "link": links[located[0]]["deep_link"] if located else note["url"], "deep": bool(located),
                              **({"place": place[0]} if place else {})})
    for note in notes:
        # Timestamps in recording order, lines in file order.
        note["places"].sort(key=lambda item: item["order"])
    data = {
        "document": BRIEF,
        "built_by": "research_control.citation_build",
        "citations": citations,
        "markdown_citations": [{"n": item["n"], "facts": item["facts"]} for item in citations],
        "notes": notes,
        "sources": {source_id: {"url": note["url"]} for note in notes for source_id in note["source_ids"]},
        "facts": {fact: {"source_ids": [str(facts[fact].get("source_id", ""))]}
                  for item in citations for fact in item["facts"]},
    }
    elements, table_problems = _exhibit_elements(markdown)
    problems += table_problems + _uncited_paragraphs(markdown)
    if not any(SOURCES_HEADING.match(line) for line in markdown.splitlines()):
        problems.append("the report has no `## Sources` heading for the numbered source list")
    if write:
        if len(known) > titles_before:
            atomic_write_json(root / TITLES, known)
        atomic_write_json(root / CITATION_MAP, data)
        atomic_write_json(root / EXHIBIT_MAP, {"document": BRIEF, "built_by": "research_control.citation_build", "elements": elements})
    return {"problems": problems, "citations": len(citations), "sources": len(notes),
            "deep_links": sum(1 for item in citations if item["deep"]), "exhibit_cells": len(elements), "map": data}
