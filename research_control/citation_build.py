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
import re
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag

from research_control.io import atomic_write_json, load_jsonl
from research_control.validators.facts import load_fact_tables, withdrawn_facts

BRIEF = "05-synthesis/company-brief.md"
CITATION_MAP = "tools/outputs/citation-map-company-brief.json"
EXHIBIT_MAP = "tools/outputs/exhibit-map.json"
FACT = r"[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?"
# A bracketed group of fact IDs that is not a Markdown link's text.
GROUP = re.compile(rf"\[({FACT}(?:\s*[,;]\s*{FACT})*)\](?!\()")
SOURCES_HEADING = re.compile(r"^##\s+Sources?(?:\s+notes?)?\s*$", re.I)
# Closing sections that hold no claims of their own: they need no citation on every paragraph.
UNCITED_SECTIONS = re.compile(r"open question|whom to ask|limits|^sources?\b|source notes|contents|how to read", re.I)
PARAGRAPH_WORDS = 25
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


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
            # Sources that are the same public page share one note.
            key = _canonical(source.get("url", "")) or source_id
            if key not in number_for:
                number_for[key] = len(notes) + 1
                dated = dates.get(source_id, {})
                notes.append({
                    "n": number_for[key], "source_ids": [source_id], "url": source.get("url", ""),
                    "title": source.get("title", ""), "publisher": source.get("publisher") or dated.get("publisher", ""),
                    "date": _reader_date(dated, source.get("date published", "")),
                    "grade": source.get("grade", ""),
                })
            note = notes[number_for[key] - 1]
            if source_id not in note["source_ids"]:
                note["source_ids"].append(source_id)
            by_number.setdefault(number_for[key], []).append(fact_id)
        for number in sorted(by_number):
            note = notes[number - 1]
            located = [links[fact]["deep_link"] for fact in by_number[number]
                       if links.get(fact, {}).get("located") and links[fact].get("deep_link")]
            citations.append({"n": number, "group": index, "facts": by_number[number],
                              "link": located[0] if located else note["url"], "deep": bool(located)})
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
        atomic_write_json(root / CITATION_MAP, data)
        atomic_write_json(root / EXHIBIT_MAP, {"document": BRIEF, "built_by": "research_control.citation_build", "elements": elements})
    return {"problems": problems, "citations": len(citations), "sources": len(notes),
            "deep_links": sum(1 for item in citations if item["deep"]), "exhibit_cells": len(elements), "map": data}
