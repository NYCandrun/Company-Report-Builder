"""Keep the control agent's conversation with the run, written by script and read by no one.

Every `archive` appends the transcript lines written since the last one to a new
numbered part in `08-control agent conversation history/`, so the conversation
is kept as the run goes. When the run is released, the whole transcript is
written as one file (or a few, under the remote's file-size limit), a script
checks that every earlier part is contained in it, and the parts are deleted.
After that the folder is left alone: questions after the run are not added.

Secrets pasted into the conversation (access tokens, API keys, private keys)
are replaced before anything is written. The orchestrator does not read or
review these files unless the user asks it to.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, load_json, utc_now

FOLDER = "08-control agent conversation history"
STATE = f"{FOLDER}/log-state.json"
FILE_LIMIT_BYTES = 90 * 1024 * 1024
SECRETS = (
    (re.compile(r"hf_[A-Za-z0-9]{20,}"), "Hugging Face token"),
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub token"),
    (re.compile(r"sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"), "API key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS key"),
    (re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{20,}=*"), "bearer token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "private key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:\\n|[^-])*?-----END [A-Z ]*PRIVATE KEY-----"), "private key"),
)


def find_transcript() -> Path | None:
    """The host's transcript of this conversation: `RESEARCH_CONTROL_TRANSCRIPT`, or the
    most recently written session file in Claude Code's project folders."""
    override = os.environ.get("RESEARCH_CONTROL_TRANSCRIPT")
    if override:
        return Path(override) if Path(override).is_file() else None
    base = Path.home() / ".claude" / "projects"
    candidates = [path for path in base.glob("*/*.jsonl") if path.is_file()] if base.is_dir() else []
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def redact(text: str) -> str:
    for pattern, label in SECRETS:
        text = pattern.sub(f"[removed {label}]", text)
    return text


def _lines(source: Path) -> list[str]:
    return source.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def _state(root: Path) -> dict[str, Any]:
    path = root / STATE
    return load_json(path) if path.is_file() else {"series": []}


def snapshot(root: Path, source: Path | None = None) -> dict[str, Any]:
    """Append what the transcript gained since the last snapshot as a new part."""
    state = _state(root)
    if state.get("finalized"):
        return {"status": "finalized"}
    source = source or find_transcript()
    if source is None:
        return {"status": "no transcript found"}
    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    series = next((item for item in state["series"] if item["source"] == str(source)), None)
    if series is None:
        series = {"source": str(source), "lines": 0, "parts": []}
        state["series"].append(series)
    lines = _lines(source)
    new = lines[series["lines"]:]
    if new:
        number = sum(len(item["parts"]) for item in state["series"]) + 1
        name = f"part-{number:04d}.jsonl"
        (folder / name).write_text(redact("".join(new)), encoding="utf-8")
        series["parts"].append(name)
        series["lines"] = len(lines)
    atomic_write_json(root / STATE, state)
    return {"status": "logged", "new_lines": len(new), "parts": sum(len(item["parts"]) for item in state["series"])}


def finalize(root: Path, source: Path | None = None) -> dict[str, Any]:
    """Write the whole conversation, check every part is contained in it, then delete the parts."""
    state = _state(root)
    if state.get("finalized"):
        return {"status": "finalized", "files": state.get("files", [])}
    snapshot(root, source)
    state = _state(root)
    folder = root / FOLDER
    whole: list[str] = []
    problems: list[str] = []
    for series in state["series"]:
        path = Path(series["source"])
        lines = [redact(line) for line in _lines(path)] if path.is_file() else []
        if not lines:
            problems.append(f"transcript {path.name} is no longer readable")
        # Cheap check: the parts, joined, are exactly the start of the full transcript.
        parts = "".join((folder / name).read_text(encoding="utf-8") for name in series["parts"] if (folder / name).is_file())
        start = "".join(lines)[: len(parts)]
        if hashlib.sha256(parts.encode("utf-8")).hexdigest() != hashlib.sha256(start.encode("utf-8")).hexdigest():
            problems.append(f"the parts from {path.name} are not contained in the full transcript")
        whole.extend(lines)
    # One file, or numbered files when the whole is over the remote's file-size limit.
    files: list[str] = []
    chunks: list[list[str]] = [[]]
    size = 0
    for line in whole:
        length = len(line.encode("utf-8"))
        if chunks[-1] and size + length > FILE_LIMIT_BYTES:
            chunks.append([])
            size = 0
        chunks[-1].append(line)
        size += length
    for number, chunk in enumerate(chunks, 1):
        name = "conversation.jsonl" if len(chunks) == 1 else f"conversation-{number:02d}.jsonl"
        (folder / name).write_text("".join(chunk), encoding="utf-8")
        files.append(name)
    if problems:
        state["final_check"] = {"at": utc_now(), "status": "parts kept", "problems": problems}
        atomic_write_json(root / STATE, state)
        return {"status": "parts kept", "files": files, "problems": problems}
    for series in state["series"]:
        for name in series["parts"]:
            (folder / name).unlink(missing_ok=True)
    final = {
        "finalized": utc_now(), "files": files, "lines": len(whole),
        "check": "every earlier part was found, in order, at the start of the full transcript before the parts were deleted",
        "sources": [{"source": series["source"], "lines": series["lines"]} for series in state["series"]],
    }
    atomic_write_json(root / STATE, final)
    return {"status": "finalized", "files": files, "lines": len(whole)}

