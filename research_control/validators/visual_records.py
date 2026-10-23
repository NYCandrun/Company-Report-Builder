"""Reconcile rendered pages to complete visual-review records."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .common import report_for


def validate(expected_pages: int, records: list[dict[str, Any]], root: Path, pattern: str = "06-checks/visual-review.json") -> dict[str, Any]:
    failures: list[str] = []
    pages: dict[int, dict[str, Any]] = {}
    for record in records:
        page = record.get("page")
        if not isinstance(page, int):
            failures.append(f"invalid page value {page!r}")
            continue
        if page in pages:
            failures.append(f"page {page} reviewed more than once")
        pages[page] = record
        if record.get("status") not in {"clean", "issues"}:
            failures.append(f"page {page}: invalid review status")
        if record.get("status") == "issues" and not record.get("issues"):
            failures.append(f"page {page}: issues status has no issue records")
    for page in range(1, expected_pages + 1):
        if page not in pages:
            failures.append(f"page {page}: no visual-review record")
    for page in sorted(set(pages) - set(range(1, expected_pages + 1))):
        failures.append(f"unexpected page {page} in visual review")
    return report_for(sys.modules[__name__], "visual_records", root, [pattern], expected_pages, len(set(pages) & set(range(1, expected_pages + 1))), failures)
