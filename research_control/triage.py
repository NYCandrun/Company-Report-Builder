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

from hashlib import sha256

from research_control.io import atomic_write_json, atomic_write_text, load_json, load_jsonl, utc_now


TRIAGE_INDEX = "tools/lists/triage-index.jsonl"
TRIAGE_DECISIONS = "tools/lists/extraction-triage.jsonl"
TRIAGE_PENDING = "tools/lists/triage-pending.jsonl"
# Questions added to the scope after triage: every captured source is decided
# again against them alone. A relevant source is included (and, if it was
# already extracted, extracted again for them); a decision never removes one.
RETRIAGE_REQUEST = "tools/lists/retriage-request.json"
RETRIAGE_DECISIONS = "tools/lists/retriage-decisions.jsonl"
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


def retriage_request(root: Path) -> dict[str, Any]:
    path = root / RETRIAGE_REQUEST
    return dict(load_json(path)) if path.is_file() else {}


def retriage_rows(root: Path) -> list[dict[str, Any]]:
    """Decisions for the current re-triage request."""
    request = retriage_request(root)
    path = root / RETRIAGE_DECISIONS
    if not request or not path.is_file():
        return []
    return [row for row in load_jsonl(path) if row.get("request") == request.get("id")]


def retriage_relevant(root: Path) -> set[str]:
    return {str(row["id"]) for row in retriage_rows(root) if row.get("relevant") is True}


def triage_included(root: Path) -> set[str]:
    included = {str(row["id"]) for row in triage_rows(root) if row.get("decision") == "include"}
    return included | retriage_relevant(root)


def validate_retriage(root: Path) -> list[str]:
    """Failures in the current re-triage; empty when every captured source has one decision."""
    request = retriage_request(root)
    if not request:
        return ["no re-triage request"]
    asked = set(map(str, request.get("questions", [])))
    failures: list[str] = []
    seen: set[str] = set()
    manifest = set(_manifest_ids(root))
    for index, row in enumerate(retriage_rows(root), 1):
        source_id = str(row.get("id", ""))
        if source_id in seen:
            failures.append(f"row {index}: duplicate decision for {source_id}")
        seen.add(source_id)
        if source_id not in manifest:
            failures.append(f"row {index}: {source_id or 'blank ID'} is not a captured source")
        if not isinstance(row.get("relevant"), bool):
            failures.append(f"{source_id}: relevant must be true or false")
        if not str(row.get("reason", "")).strip():
            failures.append(f"{source_id}: decision lacks a reason")
        cited = set(map(str, row.get("questions", []) or []))
        if row.get("relevant") is True and not cited:
            failures.append(f"{source_id}: a relevant source must name the added questions it answers")
        if cited - asked:
            failures.append(f"{source_id}: questions {', '.join(sorted(cited - asked))} are not in this re-triage")
    missing = sorted(manifest - seen)
    if missing:
        failures.append(f"captured sources without a re-triage decision: {', '.join(missing[:20])}"
                        + (f" and {len(missing) - 20} more" if len(missing) > 20 else ""))
    return failures


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
        if row.get("decision") == "exclude" and str(row["id"]) not in retriage_relevant(root)
    ]


def add_scope_question(root: Path, question_id: str, title: str, text: str, channels: str, reason: str) -> dict[str, Any]:
    """Add a research question to the scope and request that every captured source
    be decided again against it. Questions added before a pending re-triage runs
    join that request."""
    if not QUESTION_ID.match(question_id):
        raise ValueError("question ID must look like Q13")
    if not (title.strip() and text.strip() and reason.strip()):
        raise ValueError("a question needs a title, text, and reason")
    scope = root / "00-scope.md"
    document = scope.read_text(encoding="utf-8")
    if re.search(rf"\*\*{question_id}\.", document):
        raise ValueError(f"{question_id} is already in the scope")
    block = f"**{question_id}. {title.strip().rstrip('.')}.** {text.strip()}\n" + (f"Channels: {channels.strip()}\n" if channels.strip() else "")
    marker = "\n## Notes for downstream phases"
    document = document.replace(marker, f"\n{block}{marker}", 1) if marker in document else document.rstrip("\n") + f"\n\n{block}"
    atomic_write_text(scope, document)
    request = retriage_request(root)
    questions = sorted(set(request.get("questions", [])) | {question_id}) if request and not retriage_rows(root) else [question_id]
    requested_at = utc_now()
    identifier = sha256(f"{','.join(questions)}|{requested_at}".encode("utf-8")).hexdigest()[:12]
    request = {"id": identifier, "questions": questions, "reason": reason.strip(), "requested_at": requested_at}
    atomic_write_json(root / RETRIAGE_REQUEST, request)
    return request
