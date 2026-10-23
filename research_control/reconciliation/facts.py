"""Candidate-fact to filed-fact reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .assignments import reconcile_records


def reconcile(candidate_ids: Iterable[str], dispositions: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return reconcile_records(
        reconciliation_id="candidate_filing", assigned_ids=candidate_ids,
        dispositions=dispositions, root=root,
        input_patterns=["tools/candidates/**", "02-facts/**", "04-competitors/*/02-facts/**"],
        allowed_dispositions={"completed", "duplicate", "rejected"},
    )
