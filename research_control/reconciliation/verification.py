"""Cited-fact to model-verdict reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .assignments import reconcile_records


def reconcile(fact_ids: Iterable[str], dispositions: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return reconcile_records(
        reconciliation_id="cited_fact_verification", assigned_ids=fact_ids,
        dispositions=dispositions, root=root,
        input_patterns=["tools/lists/cited-facts.txt", "tools/outputs/verification-verdicts.jsonl", "02-facts/**"],
        allowed_dispositions={"completed", "blocked"},
    )
