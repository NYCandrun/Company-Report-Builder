"""Supplementary evidence added after later phases already ran.

When a source is recaptured with more content (a repository's code, say), its
new text is extracted as a supplement: the facts already filed from it stand,
new facts are appended, and synthesis is reconciled with them instead of the
run rebuilding everything downstream.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, load_json, utc_now

SUPPLEMENT_LIST = "tools/lists/supplement-sources.json"
SUPPLEMENT_FACTS = "tools/lists/supplement-facts.txt"
SUPPLEMENT_REPORT = "06-checks/supplement-reconciliation.md"


def supplement_sources(root: Path) -> dict[str, str]:
    """Source IDs being supplemented, with the reason for each."""
    path = root / SUPPLEMENT_LIST
    return dict(load_json(path).get("sources", {})) if path.is_file() else {}


def supplement_added_at(root: Path) -> dict[str, str]:
    """When each source was last listed: batches planned before then do not cover its text."""
    path = root / SUPPLEMENT_LIST
    return dict(load_json(path).get("added_at", {})) if path.is_file() else {}


def add_supplement(root: Path, source_ids: list[str], reason: str, at: str | None = None) -> dict[str, Any]:
    """List sources for supplement extraction. Listing a source again (for a new
    question or new rules) has its current text extracted again; filed facts stand."""
    if not reason.strip():
        raise ValueError("a supplement needs a reason")
    sources = supplement_sources(root)
    added = supplement_added_at(root)
    stamp = at or utc_now()
    for source_id in source_ids:
        sources[source_id] = reason.strip()
        added[source_id] = stamp
    document = {"sources": dict(sorted(sources.items())), "added_at": dict(sorted(added.items()))}
    path = root / SUPPLEMENT_LIST
    if not path.is_file() or load_json(path) != document:
        atomic_write_json(path, document)
    return {"sources": sources}


def base_source(input_id: str) -> str:
    """The source ID behind an extraction input ID such as ``SRC-X:part-0002``."""
    return str(input_id).split(":", 1)[0]
