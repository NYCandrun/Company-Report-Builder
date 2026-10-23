"""Validate citation numbering, notes, source identity, links, and placement."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag

from .common import report_for


def canonical_url(value: str) -> str:
    url, _fragment = urldefrag(value or "")
    return url.rstrip("/")


def validate_map(data: dict[str, Any], root: Path, pattern: str = "tools/outputs/citation-map.json") -> dict[str, Any]:
    citations = data.get("citations", [])
    notes = data.get("notes", [])
    markdown = data.get("markdown_citations", [])
    sources = data.get("sources", {})
    facts = data.get("facts", {})
    failures: list[str] = []

    note_by_number: dict[int, dict[str, Any]] = {}
    source_owner: dict[str, int] = {}
    url_owner: dict[str, int] = {}
    for note in notes:
        number = note.get("n")
        if number in note_by_number:
            failures.append(f"citation note number {number} appears twice")
        note_by_number[number] = note
        note_sources = note.get("source_ids") or ([note.get("source_id")] if note.get("source_id") else [])
        if not note_sources:
            failures.append(f"note {number} has no source")
        for source_id in note_sources:
            source_id = str(source_id)
            if source_id in source_owner:
                failures.append(f"source {source_id} has numbers {source_owner[source_id]} and {number}")
            source_owner[source_id] = number
        url = canonical_url(str(note.get("url", "")))
        if url and url in url_owner and not note.get("duplicate_url_justification"):
            failures.append(f"notes {url_owner[url]} and {number} link to the same canonical page")
        if url:
            url_owner[url] = number
        for source_id in note_sources:
            expected_url = canonical_url(str(sources.get(str(source_id), {}).get("url", "")))
            if expected_url and url != expected_url and len(note_sources) == 1:
                failures.append(f"note {number} links to the wrong page for {source_id}")

    seen: set[int] = set()
    next_number = 1
    used: set[int] = set()
    for index, citation in enumerate(citations):
        number = citation.get("n")
        used.add(number)
        if number not in seen:
            if number != next_number:
                failures.append(f"new citation {number} appears where {next_number} was expected")
            seen.add(number)
            next_number += 1
        if number not in note_by_number:
            failures.append(f"citation {number} has no source note")
        else:
            note = note_by_number[number]
            note_sources = set(note.get("source_ids") or ([note.get("source_id")] if note.get("source_id") else []))
            fact_sources = {
                source_id
                for fact_id in citation.get("facts", [])
                for source_id in facts.get(fact_id, {}).get("source_ids", [])
            }
            if fact_sources and not fact_sources.issubset(note_sources):
                failures.append(f"citation {number} note omits sources {sorted(fact_sources - note_sources)}")
        if index < len(markdown) and citation.get("facts", []) != markdown[index].get("facts", []):
            failures.append(f"citation {number} facts do not match Markdown placement")
    for number in sorted(set(note_by_number) - used):
        failures.append(f"source note {number} is unused")
    if len(markdown) != len(citations):
        failures.append(f"Markdown has {len(markdown)} citation groups but output has {len(citations)}")
    return report_for(sys.modules[__name__], "citation_structure", root, [pattern], len(citations), len(citations), failures)
