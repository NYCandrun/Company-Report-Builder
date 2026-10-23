"""Validate captured-source manifest records and local receipts."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Any

from .common import report_for


REQUIRED = ("id", "grade", "title", "publisher", "url", "date published", "date captured", "local file", "method", "notes")


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{str(key).strip().lower(): (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def validate_records(records: list[dict[str, Any]], root: Path, manifest_path: str = "01-sources/MANIFEST.csv") -> dict[str, Any]:
    failures: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(records, 1):
        source_id = str(row.get("id", "")).strip()
        for field in REQUIRED:
            if field not in row:
                failures.append(f"row {index}: missing column {field}")
        if not source_id:
            failures.append(f"row {index}: empty source ID")
        elif source_id in seen:
            failures.append(f"row {index}: duplicate source ID {source_id}")
        seen.add(source_id)
        if row.get("grade") not in {"P", "S", "T", "I"}:
            failures.append(f"{source_id or index}: invalid grade {row.get('grade')!r}")
        local_files = [item.strip() for item in str(row.get("local file", "")).split(";") if item.strip()]
        if not local_files:
            failures.append(f"{source_id or index}: missing local file")
        for relative in local_files:
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                failures.append(f"{source_id or index}: unsafe local file {relative}")
            elif not (root / relative).is_file():
                failures.append(f"{source_id or index}: local file not found {relative}")
        date = str(row.get("date captured", ""))
        if not re.match(r"^\d{4}-\d{2}-\d{2}", date):
            failures.append(f"{source_id or index}: invalid capture date {date!r}")
    return report_for(sys.modules[__name__], "source_records", root, [manifest_path], len(records), len(records), failures)
