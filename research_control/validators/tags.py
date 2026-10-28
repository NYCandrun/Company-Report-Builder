"""Validate fact `about` and `said_by` tags."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .common import report_for


INVALID = {"unknown", "n/a", "none", "speaker", "website"}


def validate(records: list[dict[str, Any]], root: Path, patterns: list[str] | None = None) -> dict[str, Any]:
    failures = []
    for index, row in enumerate(records, 1):
        label = row.get("fact_id", index)
        for field in ("about", "said_by"):
            value = str(row.get(field, "")).strip()
            if not value or value.lower() in INVALID:
                failures.append(f"{label}: invalid {field} tag {value!r}")
        if " per " in str(row.get("about", "")).lower() and "(" not in str(row.get("about", "")):
            failures.append(f"{label}: cross-organization about tag must use X (per Y)")
    return report_for(sys.modules[__name__], "fact_tags", root, patterns or ["02-facts/*.md"], len(records), len(records), failures)
