"""Canonical-source to extraction reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .assignments import reconcile_records


def reconcile(source_ids: Iterable[str], dispositions: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return reconcile_records(
        reconciliation_id="source_extraction", assigned_ids=source_ids,
        dispositions=dispositions, root=root,
        input_patterns=["tools/lists/extraction-scope.csv", "tools/extracts/**", "tools/candidates/**"],
        allowed_dispositions={"completed", "completed_zero", "duplicate", "excluded", "blocked"},
        allow_one_to_many=True,
    )
