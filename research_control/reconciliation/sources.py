"""Source-discovery to capture reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .assignments import reconcile_records


def reconcile(discovered_ids: Iterable[str], dispositions: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return reconcile_records(
        reconciliation_id="capture_sources", assigned_ids=discovered_ids,
        dispositions=dispositions, root=root,
        input_patterns=["tools/lists/**", "01-sources/manifest-parts/**", "01-sources/blocked-parts/**"],
        allowed_dispositions={"completed", "duplicate", "excluded", "blocked"},
    )
