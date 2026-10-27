"""Find organizations whose client relationship is marked differently across files.

Synthesis files are written by separate workers, so one file can call an
organization a stated client while another calls it inferred or thin
evidence. This script reads the marks the evidence rules ask for (for example
"Microsoft (inferred client: ...)" or "Holiday Inn Club Vacations (lead, thin
evidence: ...)") and lists every organization with more than one, so reviewers
and the worker applying their findings settle each by the evidence instead of
discovering it again.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_text, utc_now

REPORT = "06-checks/relationship-consistency.md"
# A run of capitalized words (with "&") right before "(stated", "(inferred", or "(lead".
MARK = re.compile(r"\b([A-Z][A-Za-z0-9.'-]*(?: (?:[A-Z][A-Za-z0-9.'-]*|&))*) \((?:an? |the )?((?i:stated|inferred|lead))\b")
FIRST_WORD = re.compile(r"^[A-Z]")
NOT_NAMES = {"the", "a", "an", "this", "that", "my inference", "relationship basis"}


def relationship_marks(root: Path) -> dict[str, dict[str, list[str]]]:
    """Each organization's marks, and the synthesis files that use each."""
    marks: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for path in sorted((root / "05-synthesis").glob("*.md")):
        for match in MARK.finditer(path.read_text(encoding="utf-8", errors="replace")):
            name, mark = match.group(1).strip(), match.group(2).casefold()
            if not FIRST_WORD.match(name) or name.casefold() in NOT_NAMES:
                continue
            if path.name not in marks[name][mark]:
                marks[name][mark].append(path.name)
    return {name: dict(found) for name, found in marks.items()}


def write_relationship_report(root: Path) -> dict[str, Any]:
    marks = relationship_marks(root)
    mixed = {name: found for name, found in sorted(marks.items()) if len(found) > 1}
    lines = [
        "# Relationship marks that differ between files", "",
        f"Checked the synthesis files on {utc_now()[:10]}: {len(marks)} organizations carry a "
        f"stated, inferred, or thin-evidence mark; {len(mixed)} carry more than one.", "",
        "Settle each by the evidence (the evidence core's rules): a source that names the relationship, including "
        "the company's own working records, makes it stated; differences by date are a change over time.", "",
    ]
    if not mixed:
        lines.append("None.")
    for name, found in mixed.items():
        lines.append(f"- {name}: " + "; ".join(f"{mark} in {', '.join(files)}" for mark, files in sorted(found.items())))
    atomic_write_text(root / REPORT, "\n".join(lines) + "\n")
    return {"organizations": len(marks), "marked_differently": len(mixed)}
