"""Final citation reference to source-note reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .assignments import reconcile_records


def reconcile(reference_ids: Iterable[str], dispositions: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return reconcile_records(
        reconciliation_id="citation_sources", assigned_ids=reference_ids,
        dispositions=dispositions, root=root,
        input_patterns=["tools/outputs/citation-map-*.json", "07-final-report/*.html", "05-synthesis/*.md"],
        allowed_dispositions={"completed"},
        allow_one_to_many=True,
    )
