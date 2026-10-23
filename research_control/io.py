"""Small, dependency-free I/O helpers used throughout the control plane."""

from __future__ import annotations

import glob
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{number}: JSONL record is not an object")
            rows.append(value)
    return rows


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def brace_expand(pattern: str) -> list[str]:
    """Expand simple comma braces recursively without shell evaluation."""
    match_start = pattern.find("{")
    if match_start < 0:
        return [pattern]
    depth = 0
    match_end = -1
    for index in range(match_start, len(pattern)):
        if pattern[index] == "{":
            depth += 1
        elif pattern[index] == "}":
            depth -= 1
            if depth == 0:
                match_end = index
                break
    if match_end < 0:
        return [pattern]
    prefix, body, suffix = pattern[:match_start], pattern[match_start + 1:match_end], pattern[match_end + 1:]
    return [expanded for item in body.split(",") for expanded in brace_expand(prefix + item + suffix)]


def resolve_pattern(root: Path, pattern: str) -> list[Path]:
    matches: list[Path] = []
    for expanded in brace_expand(pattern):
        candidate = root / expanded
        if any(char in expanded for char in "*?["):
            matches.extend(Path(item) for item in glob.glob(str(candidate), recursive=True))
        elif candidate.exists():
            matches.append(candidate)
    return sorted(set(matches), key=lambda path: path.as_posix())


def require_nonempty_paths(root: Path, patterns: Iterable[str]) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for pattern in patterns:
        matches = resolve_pattern(root, pattern)
        good = [path for path in matches if path.is_dir() or path.stat().st_size > 0]
        if good:
            present.extend(str(path.relative_to(root)) for path in good)
        else:
            missing.append(pattern)
    return present, missing


def workflow(path: Path) -> dict[str, Any]:
    """WORKFLOW.yaml is deliberately JSON-compatible YAML."""
    value = load_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("phases"), list):
        raise ValueError(f"{path}: invalid workflow document")
    return value


def find_phase(document: dict[str, Any], phase_or_gate: str) -> dict[str, Any]:
    for phase in document["phases"]:
        gate = phase.get("gate", {})
        if phase.get("id") == phase_or_gate or gate.get("name") == phase_or_gate:
            return phase
    raise KeyError(f"unknown phase or gate: {phase_or_gate}")
