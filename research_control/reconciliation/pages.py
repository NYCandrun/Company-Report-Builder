"""Rendered-page to visual-review reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .assignments import reconcile_records


def reconcile(page_ids: Iterable[str], dispositions: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return reconcile_records(
        reconciliation_id="visual_pages", assigned_ids=page_ids,
        dispositions=dispositions, root=root,
        input_patterns=["07-final-report/*.pdf", "06-checks/visual-review*.md"],
        allowed_dispositions={"completed"},
    )
