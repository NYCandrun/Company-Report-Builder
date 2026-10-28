"""Stable SHA-256 hashing for files, directories, patterns, and checkers."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any, Iterable

from research_control.io import resolve_pattern


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    if path.is_file():
        return sha256_file(path)
    digest = hashlib.sha256()
    for item in sorted((x for x in path.rglob("*") if x.is_file()), key=lambda value: value.as_posix()):
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(sha256_file(item).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def hash_patterns(root: Path, patterns: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for pattern in patterns:
        matches = resolve_pattern(root, pattern)
        if not matches:
            result[f"pattern:{pattern}"] = "MISSING"
            continue
        for path in matches:
            result[str(path.relative_to(root))] = hash_path(path)
    return dict(sorted(result.items()))


def checker_version(module_or_path: Any) -> str:
    if isinstance(module_or_path, Path):
        return sha256_file(module_or_path)[:16]
    path = inspect.getsourcefile(module_or_path)
    return sha256_file(Path(path))[:16] if path else "unknown"


def report_inputs_current(root: Path, report: dict[str, Any]) -> tuple[bool, list[str]]:
    stale: list[str] = []
    for relative, expected in report.get("input_hashes", {}).items():
        if relative.startswith("pattern:"):
            pattern = relative.split(":", 1)[1]
            current = hash_patterns(root, [pattern]).get(relative, "EXPANDED")
        else:
            current = hash_path(root / relative)
        if current != expected:
            stale.append(relative)
    return not stale, stale
