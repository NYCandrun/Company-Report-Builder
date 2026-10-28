"""Validate published/modified separation and fact source-date forms."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from .common import report_for


ISO = re.compile(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])")
WEAK_PUBLICATION_METHODS = {"site-wide deploy timestamp", "homepage metadata", "pricing-page modification metadata", "shallow git clone"}


def validate_source_dates(records: list[dict[str, Any]], root: Path, pattern: str = "01-sources/MANIFEST.csv") -> dict[str, Any]:
    failures: list[str] = []
    for index, row in enumerate(records, 1):
        label = str(row.get("id", f"row {index}"))
        published = str(row.get("date published", row.get("date_published", "")) or "")
        modified = str(row.get("date last modified", row.get("date_last_modified", "")) or "")
        method = str(row.get("date method", row.get("date_method", "")) or "").lower()
        if published and not ISO.match(published):
            failures.append(f"{label}: invalid published date {published!r}")
        if modified and not ISO.match(modified):
            failures.append(f"{label}: invalid modified date {modified!r}")
        if published and method in WEAK_PUBLICATION_METHODS:
            failures.append(f"{label}: weak modified signal used as publication method")
        if published and modified and published == modified and "modified" in method:
            failures.append(f"{label}: modified date copied into published date")
    return report_for(sys.modules[__name__], "source_dates", root, [pattern], len(records), len(records), failures)


def validate_fact_dates(records: list[dict[str, Any]], root: Path, patterns: list[str] | None = None, source_dates: dict[str, str] | None = None) -> dict[str, Any]:
    failures = []
    for index, row in enumerate(records, 1):
        value = str(row.get("source_date", ""))
        if not re.search(r"\d{4}-\d{2}-\d{2}", value):
            failures.append(f"{row.get('fact_id', index)}: source date lacks ISO date")
        if "last modified" in value and "published" in value and ";" not in value:
            failures.append(f"{row.get('fact_id', index)}: published and modified dates are not separated")
        if source_dates is not None:
            source_id = str(row.get("source_id", "")).strip()
            expected = source_dates.get(source_id)
            found = re.search(r"\d{4}-\d{2}-\d{2}", value)
            if expected and (not found or found.group(0) != expected):
                failures.append(f"{row.get('fact_id', index)}: source date {found.group(0) if found else 'missing'} does not match manifest {expected}")
    return report_for(sys.modules[__name__], "fact_dates", root, patterns or ["02-facts/*.md"], len(records), len(records), failures)
