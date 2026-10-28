"""Check one extraction batch's parts when its worker reports success."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_control.io import load_jsonl

from .quotes import validate as validate_quotes

CANDIDATE_FIELDS = ("topic", "claim", "quote", "source_id", "location", "source_date", "grade", "about", "said_by", "notes")
DISPOSITIONS = {"completed", "completed_zero", "duplicate", "excluded", "blocked", "rejected"}
TEXT_SUFFIXES = {".txt", ".md", ".json", ".jsonl", ".csv", ".xml"}


def validate_part(root: Path, task: dict[str, Any]) -> list[str]:
    """Failures in an extraction batch's candidate and disposition parts; empty when it holds."""
    metadata = task["metadata"]
    prefix = str(metadata.get("candidate_id_prefix", ""))
    inputs = {str(item["id"]): item for item in task["inputs"]}
    texts: dict[str, list[Path]] = {}
    for item in task["inputs"]:
        paths = [root / item["path"]] if item.get("path") else []
        paths += [root / value for value in item.get("source_paths", []) if Path(value).suffix in TEXT_SUFFIXES]
        texts.setdefault(str(item["source_id"]), []).extend(path for path in paths if path.is_file())

    failures: list[str] = []
    candidates = load_jsonl(root / metadata["candidate_part"])
    seen: set[str] = set()
    for index, row in enumerate(candidates, 1):
        identifier = str(row.get("candidate_id", row.get("id", "")))
        label = identifier or f"candidate {index}"
        if not identifier.startswith(prefix):
            failures.append(f"{label}: ID must start with {prefix}")
        if identifier in seen:
            failures.append(f"{label}: duplicate candidate ID")
        seen.add(identifier)
        missing = [field for field in CANDIDATE_FIELDS if field not in row]
        if missing:
            failures.append(f"{label}: missing fields {', '.join(missing)}")
        if str(row.get("source_id", "")) not in texts:
            failures.append(f"{label}: source {row.get('source_id')} is not an input of this batch")
    quotable = [
        {**row, "fact_id": row.get("candidate_id", row.get("id", ""))}
        for row in candidates if str(row.get("source_id", "")) in texts
    ]
    failures += validate_quotes(quotable, texts, root)["failures"]

    dispositions = load_jsonl(root / metadata["disposition_part"])
    covered: dict[str, int] = {}
    for index, row in enumerate(dispositions, 1):
        input_id = str(row.get("input_id", ""))
        if input_id not in inputs:
            failures.append(f"disposition {index}: {input_id or 'blank input_id'} is not an input of this batch")
        if row.get("disposition") not in DISPOSITIONS:
            failures.append(f"{input_id or index}: invalid disposition {row.get('disposition')!r}")
        covered[input_id] = covered.get(input_id, 0) + 1
    for input_id in inputs:
        if covered.get(input_id, 0) != 1:
            failures.append(f"{input_id}: needs exactly one disposition, found {covered.get(input_id, 0)}")
    return failures
