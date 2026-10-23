"""Semantic finding to decision reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .assignments import reconcile_records


def reconcile(finding_ids: Iterable[str], dispositions: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return reconcile_records(
        reconciliation_id="review_findings", assigned_ids=finding_ids,
        dispositions=dispositions, root=root,
        input_patterns=["06-checks/review-*.md", "05-synthesis/*.md"],
        allowed_dispositions={"completed", "rejected"},
    )
