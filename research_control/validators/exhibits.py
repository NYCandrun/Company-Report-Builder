"""Validate element-level exhibit fact mapping."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .common import report_for


def validate(elements: list[dict[str, Any]], known_fact_ids: set[str], root: Path, pattern: str = "tools/outputs/exhibit-map.json") -> dict[str, Any]:
    failures: list[str] = []
    seen: set[str] = set()
    for index, element in enumerate(elements, 1):
        element_id = str(element.get("element_id", ""))
        if not element_id:
            failures.append(f"element {index}: missing element_id")
        elif element_id in seen:
            failures.append(f"element {index}: duplicate element_id {element_id}")
        seen.add(element_id)
        facts = element.get("fact_ids", [])
        if element.get("evidence_bearing", True) and not facts:
            failures.append(f"{element_id or index}: no element-level facts")
        for fact_id in facts:
            if fact_id not in known_fact_ids:
                failures.append(f"{element_id or index}: unknown fact {fact_id}")
    return report_for(sys.modules[__name__], "exhibit_mapping", root, [pattern], len(elements), len(elements), failures)
