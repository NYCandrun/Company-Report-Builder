"""Parse and validate Markdown fact tables."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Iterable

from .common import report_for


ALIASES = {
    "fact id": "fact_id", "fact_id": "fact_id", "claim": "claim",
    "verbatim quote": "verbatim_quote", "quote": "verbatim_quote",
    "source id": "source_id", "source_id": "source_id", "location": "location",
    "source date": "source_date", "source_date": "source_date", "grade": "grade",
    "topics": "topics", "topic": "topics", "about": "about",
    "said by": "said_by", "said_by": "said_by", "verdict": "verdict",
}
REQUIRED = tuple(dict.fromkeys(ALIASES.values()))
FACT_ID = re.compile(r"^[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?$")
VAGUE_RECEIPTS = {"website", "many pages", "count script", "file path"}


def _cells(line: str) -> list[str]:
    return [value.strip().replace("\\|", "|") for value in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def load_fact_tables(paths: Iterable[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        header: list[str] | None = None
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not line.lstrip().startswith("|"):
                continue
            cells = _cells(line)
            if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                continue
            normalized = [ALIASES.get(cell.lower()) for cell in cells]
            if "fact_id" in normalized and "claim" in normalized:
                header = [value or f"ignored_{index}" for index, value in enumerate(normalized)]
                continue
            if header and len(cells) == len(header):
                row = dict(zip(header, cells))
                row["_path"] = str(path)
                row["_line"] = str(number)
                rows.append(row)
    return rows


def validate_records(records: list[dict[str, Any]], root: Path, source_ids: set[str] | None = None, patterns: list[str] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    seen: set[str] = set()
    content_owner: dict[tuple[str, str, str], str] = {}
    subjects: dict[tuple[str, str, str], list[tuple[str, set[str], str]]] = {}
    for index, row in enumerate(records, 1):
        fact_id = str(row.get("fact_id", "")).strip()
        label = fact_id or f"row {index}"
        if not FACT_ID.match(fact_id):
            failures.append(f"{label}: invalid fact ID")
        if fact_id in seen:
            failures.append(f"{label}: duplicate fact ID")
        seen.add(fact_id)
        for field in REQUIRED:
            if not str(row.get(field, "")).strip():
                failures.append(f"{label}: empty {field}")
        if row.get("grade") not in {"P", "S", "T", "I"}:
            failures.append(f"{label}: invalid grade {row.get('grade')!r}")
        receipt = str(row.get("source_id", "")).strip().lower()
        if receipt in VAGUE_RECEIPTS or "/" in receipt:
            failures.append(f"{label}: vague or path-only source receipt")
        ids = {item.strip() for item in re.split(r"[,;]", str(row.get("source_id", ""))) if item.strip()}
        if source_ids is not None:
            for source_id in sorted(ids - source_ids):
                failures.append(f"{label}: unresolved source ID {source_id}")
        content_key = (
            re.sub(r"\s+", " ", str(row.get("claim", "")).strip().casefold()),
            str(row.get("source_id", "")).strip(), str(row.get("location", "")).strip(),
        )
        if all(content_key):
            owner = content_owner.get(content_key)
            if owner and not row.get("duplicate_of"):
                failures.append(f"{label}: likely duplicate of {owner} lacks duplicate disposition")
            content_owner[content_key] = fact_id
        subject = str(row.get("subject", "")).strip().casefold()
        if subject:
            numbers = set(re.findall(r"(?<![A-Za-z])\$?\d+(?:\.\d+)?%?", str(row.get("claim", ""))))
            key = (str(row.get("about", "")).strip().casefold(), str(row.get("topics", "")).strip().casefold(), subject)
            subjects.setdefault(key, []).append((fact_id, numbers, str(row.get("conflict_group", ""))))
        quote = str(row.get("verbatim_quote", "")).casefold()
        risk_terms = [term for term in ("can", "will", "plan", "aim", "up to", "some", "early", "beta", "coming soon") if re.search(rf"\b{re.escape(term)}\b", quote)]
        if risk_terms and "script-flagged" not in str(row.get("verdict", "")).casefold() and not row.get("overstatement_reviewed"):
            failures.append(f"{label}: overstatement-risk terms not flagged: {', '.join(risk_terms)}")
    for key, values in subjects.items():
        distinct = {tuple(sorted(numbers)) for _fact_id, numbers, _group in values if numbers}
        if len(distinct) > 1 and not all(group for _fact_id, _numbers, group in values):
            failures.append(f"subject {key[2]}: conflicting numeric facts lack conflict_group")
    paths = patterns or ["02-facts/*.md", "04-competitors/*/02-facts/*.md"]
    return report_for(sys.modules[__name__], "fact_records", root, paths, len(records), len(records), failures)
