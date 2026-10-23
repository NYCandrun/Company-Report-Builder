"""Validate quote presence in captured source text."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from .common import report_for


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def validate(records: list[dict[str, Any]], source_paths: dict[str, Path], root: Path, patterns: list[str] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    checked = 0
    for index, row in enumerate(records, 1):
        label = str(row.get("fact_id", index))
        source_id = str(row.get("source_id", "")).strip()
        path = source_paths.get(source_id)
        if path is None or not path.is_file():
            failures.append(f"{label}: captured source not found for {source_id}")
            continue
        checked += 1
        source = normalize(path.read_text(encoding="utf-8", errors="replace"))
        quote = str(row.get("verbatim_quote", row.get("quote", "")))
        parts = [normalize(item).strip(" .,;:") for item in re.split(r"\s*(?:\.\.\.|…)\s*", quote)]
        parts = [item for item in parts if len(item.split()) >= 2]
        if not parts or not all(item in source for item in parts):
            failures.append(f"{label}: quote not found in captured source")
        location = str(row.get("location", "")).strip().lower()
        if not location or location in {"source", "page", "line"}:
            failures.append(f"{label}: location is not exact")
    return report_for(sys.modules[__name__], "fact_quotes", root, patterns or ["02-facts/*.md"], len(records), checked, failures)
