"""Mechanical writing-rule checks for authored Markdown and text."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .common import report_for


def unquoted(value: str) -> str:
    value = re.sub(r"`[^`]*`", "", value)
    value = re.sub(r'"[^"\n]*"', "", value)
    return value


def validate(paths: list[Path], root: Path) -> dict:
    failures: list[str] = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            check = unquoted(line)
            if "—" in check:
                failures.append(f"{path.relative_to(root)}:{number}: em dash")
            if re.search(r"\bsuggested\b", check, re.IGNORECASE):
                failures.append(f"{path.relative_to(root)}:{number}: forbidden word suggested")
    patterns = [str(path.relative_to(root)) for path in paths]
    return report_for(sys.modules[__name__], "writing_rules", root, patterns, len(paths), len(paths), failures)
