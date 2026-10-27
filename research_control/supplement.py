"""Supplementary evidence added after later phases already ran.

When a source is recaptured with more content (a repository's code, say), its
new text is extracted as a supplement: the facts already filed from it stand,
new facts are appended, and synthesis is reconciled with them instead of the
run rebuilding everything downstream.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, load_json

SUPPLEMENT_LIST = "tools/lists/supplement-sources.json"
SUPPLEMENT_FACTS = "tools/lists/supplement-facts.txt"
SUPPLEMENT_REPORT = "06-checks/supplement-reconciliation.md"


def supplement_sources(root: Path) -> dict[str, str]:
    """Source IDs being supplemented, with the reason for each."""
    path = root / SUPPLEMENT_LIST
    return dict(load_json(path).get("sources", {})) if path.is_file() else {}


def add_supplement(root: Path, source_ids: list[str], reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("a supplement needs a reason")
    sources = supplement_sources(root)
    for source_id in source_ids:
        sources[source_id] = reason.strip()
    atomic_write_json(root / SUPPLEMENT_LIST, {"sources": dict(sorted(sources.items()))})
    return {"sources": sources}


def base_source(input_id: str) -> str:
    """The source ID behind an extraction input ID such as ``SRC-X:part-0002``."""
    return str(input_id).split(":", 1)[0]
