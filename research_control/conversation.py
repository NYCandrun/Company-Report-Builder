"""Keep the control agent's conversation with the run, written by script and read by no one.

Every time the run is saved (`archive`), including the push at the start of
every phase that a script confirms reached the remote, the transcript lines
written since the last save are added to `08-control agent conversation
history/` as a new numbered part, with secrets removed. When the run is
released, the whole conversation is written as one file, a script checks that
every earlier part is contained in it, and the parts are deleted. After that
the folder is left alone: questions after the run are not added.

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
SNAPSHOT_STEM = "conversation-so-far"
FINAL_STEM = "conversation"
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


def _redacted_lines(source: Path) -> list[str]:
    return [redact(line) for line in source.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)]


def _digest(lines: list[str]) -> str:
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def state(root: Path) -> dict[str, Any]:
    path = root / STATE
    return load_json(path) if path.is_file() else {}


def _save(root: Path, document: dict[str, Any]) -> None:
    atomic_write_json(root / STATE, document)


def _write(folder: Path, stem: str, lines: list[str]) -> list[str]:
    """One file, or numbered files when the whole is over the remote's file-size limit."""
    chunks: list[list[str]] = [[]]
    size = 0
    for line in lines:
        length = len(line.encode("utf-8"))
        if chunks[-1] and size + length > FILE_LIMIT_BYTES:
            chunks.append([])
            size = 0
        chunks[-1].append(line)
        size += length
    for old in [folder / f"{stem}.jsonl", *folder.glob(f"{stem}-[0-9][0-9].jsonl")]:
        old.unlink(missing_ok=True)
    names = []
    for number, chunk in enumerate(chunks, 1):
        name = f"{stem}.jsonl" if len(chunks) == 1 else f"{stem}-{number:02d}.jsonl"
        (folder / name).write_text("".join(chunk), encoding="utf-8")
        names.append(name)
    return names


def snapshot(root: Path, source: Path | None = None, label: str = "") -> dict[str, Any]:
    """Add what the transcript gained since the last save as a new part."""
    document = state(root)
    if document.get("finalized"):
        return {"status": "finalized"}
    source = source or find_transcript()
    if source is None:
        return {"status": "no transcript found"}
    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    series_list = document.setdefault("series", [])
    series = next((item for item in series_list if item["source"] == str(source)), None)
    if series is None:
        series = {"source": str(source), "lines": 0, "parts": []}
        series_list.append(series)
    lines = _redacted_lines(source)
    new = lines[series["lines"]:]
    if new:
        number = sum(len(item["parts"]) for item in series_list) + 1
        name = f"part-{number:04d}.jsonl"
        (folder / name).write_text("".join(new), encoding="utf-8")
        series["parts"].append(name)
        series["lines"] = len(lines)
        document.setdefault("saves", []).append({"label": label, "at": utc_now(), "part": name, "new_lines": len(new)})
    _save(root, document)
    return {"status": "logged", "new_lines": len(new), "parts": sum(len(item["parts"]) for item in series_list)}


def finalize(root: Path, source: Path | None = None) -> dict[str, Any]:
    """Write the whole conversation once, check every earlier part is contained in it, then
    delete the parts."""
    document = state(root)
    if document.get("finalized"):
        return {"status": "finalized", "files": document.get("files", [])}
    snapshot(root, source, "end of the run")
    document = state(root)
    folder = root / FOLDER
    series_list = document.get("series", [])
    copies = document.get("copies", [])
    sources = list(dict.fromkeys([item["source"] for item in series_list] + [item["source"] for item in copies]))
    if not sources:
        return {"status": "no transcript found"}
    full = {name: _redacted_lines(Path(name)) if Path(name).is_file() else [] for name in sources}
    problems = []
    for series in series_list:
        # Cheap check: the parts, joined in order, are exactly the start of the full conversation.
        parts = "".join((folder / name).read_text(encoding="utf-8") for name in series["parts"] if (folder / name).is_file())
        whole = "".join(full[series["source"]])
        if not whole.startswith(parts):
            problems.append(f"the parts from {Path(series['source']).name} are not contained in the full conversation")
    for item in copies:
        # Full copies an earlier version of this logger wrote, checked by line count and hash.
        lines = full.get(item["source"], [])
        if len(lines) < item["lines"] or _digest(lines[: item["lines"]]) != item["sha256"]:
            problems.append(f"the copy made at {item['at']} is not contained in the full conversation")
    files: list[str] = []
    for index, name in enumerate(sources, 1):
        stem = FINAL_STEM if len(sources) == 1 else f"{FINAL_STEM}-session-{index}"
        files += _write(folder, stem, full[name])
    if problems:
        document["final_check"] = {"at": utc_now(), "status": "earlier parts kept", "problems": problems}
        _save(root, document)
        return {"status": "earlier parts kept", "files": files, "problems": problems}
    for old in [*folder.glob("part-*.jsonl"), folder / f"{SNAPSHOT_STEM}.jsonl", *folder.glob(f"{SNAPSHOT_STEM}-[0-9][0-9].jsonl")]:
        old.unlink(missing_ok=True)
    final = {
        "finalized": utc_now(), "files": files, "lines": sum(len(lines) for lines in full.values()),
        "check": "every earlier part, joined in order, matched the start of the full conversation; "
                 "the parts were then deleted",
        "parts_checked": sum(len(item["parts"]) for item in series_list) + len(copies),
        "saves": document.get("saves", []), "pushes": document.get("pushes", []),
    }
    _save(root, final)
    return {"status": "finalized", "files": files, "lines": final["lines"]}


def record_push(root: Path, label: str, commit: str, verified: bool, detail: str = "") -> None:
    document = state(root)
    document.setdefault("pushes", []).append(
        {"label": label, "at": utc_now(), "commit": commit, "on_remote": verified, **({"detail": detail} if detail else {})}
    )
    if verified:
        document["last_verified"] = label
    _save(root, document)
