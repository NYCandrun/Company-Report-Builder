"""Question-bounded extraction triage.

Capture is cheap and deterministic, so the corpus may hold more pages than the
brief can use. Triage decides which captured sources are read in full for fact
extraction, by the numbered research questions in ``00-scope.md``. Every
captured source receives exactly one decision; excluded sources keep their
capture and provenance and receive an ``excluded`` extraction disposition.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from research_control.io import load_jsonl


TRIAGE_INDEX = "tools/lists/triage-index.jsonl"
TRIAGE_DECISIONS = "tools/lists/extraction-triage.jsonl"
TRIAGE_PENDING = "tools/lists/triage-pending.jsonl"
TRIAGE_EXCERPT_CHARACTERS = 500
DECISIONS = {"include", "exclude"}
QUESTION_ID = re.compile(r"^Q\d+$")


def _manifest_ids(root: Path) -> list[str]:
    path = root / "01-sources/MANIFEST.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [row.get("id", "").strip() for row in csv.DictReader(handle) if row.get("id", "").strip()]


def scope_question_ids(root: Path) -> set[str]:
    path = root / "00-scope.md"
    if not path.is_file():
        return set()
    return set(re.findall(r"\bQ\d+\b", path.read_text(encoding="utf-8", errors="replace")))


def triage_rows(root: Path) -> list[dict[str, Any]]:
    path = root / TRIAGE_DECISIONS
    return load_jsonl(path) if path.is_file() and path.stat().st_size else []


def triage_included(root: Path) -> set[str]:
    return {str(row["id"]) for row in triage_rows(root) if row.get("decision") == "include"}


def validate_triage(root: Path) -> list[str]:
    """Return failures; an empty list means every captured source has one valid decision."""
    failures: list[str] = []
    manifest = _manifest_ids(root)
    questions = scope_question_ids(root)
    if not questions:
        failures.append("00-scope.md names no research question IDs (Q1, Q2, ...)")
    rows = triage_rows(root)
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        source_id = str(row.get("id", ""))
        if source_id in seen:
            failures.append(f"row {index}: duplicate decision for {source_id}")
        seen.add(source_id)
        if source_id not in manifest:
            failures.append(f"row {index}: {source_id or 'blank ID'} is not a captured source")
        decision = row.get("decision")
        if decision not in DECISIONS:
            failures.append(f"{source_id}: decision must be include or exclude")
        if not str(row.get("reason", "")).strip():
            failures.append(f"{source_id}: decision lacks a reason")
        cited = row.get("questions", [])
        if not isinstance(cited, list) or any(not QUESTION_ID.match(str(value)) for value in cited):
            failures.append(f"{source_id}: questions must be a list of IDs such as Q1")
            continue
        if decision == "include" and not cited:
            failures.append(f"{source_id}: an included source must name the questions it answers")
        unknown = sorted(set(map(str, cited)) - questions) if questions else []
        if unknown:
            failures.append(f"{source_id}: unknown research question IDs {', '.join(unknown)}")
    missing = [source_id for source_id in manifest if source_id not in seen]
    if missing:
        failures.append(f"captured sources without a triage decision: {', '.join(missing[:20])}"
                        + (f" and {len(missing) - 20} more" if len(missing) > 20 else ""))
    if rows and not any(row.get("decision") == "include" for row in rows):
        failures.append("triage included no sources")
    return failures


def excluded_dispositions(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "assignment_id": "facts.triage",
            "input_id": str(row["id"]),
            "disposition": "excluded",
            "reason": f"triage: {row.get('reason', '').strip()}",
            "evidence_paths": [TRIAGE_DECISIONS],
            "output_ids": [],
        }
        for row in triage_rows(root)
        if row.get("decision") == "exclude"
    ]
