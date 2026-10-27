"""Keep the control agent's conversation with the run, written by script and read by no one.

The whole transcript, secrets removed, is copied into
`08-control agent conversation history/` and pushed with the run: whenever the
run is saved (`archive`), and at the start of every phase, where a script
confirms the push reached the remote before the phase begins. Each copy is
the full conversation so far; its line count and hash are recorded. When the
run is released, the whole conversation is written as one final file, a
script checks that every earlier copy is contained in it (the same lines, by
hash), and the earlier copy is deleted. After that the folder is left alone:
questions after the run are not added.

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
    """Copy the whole conversation so far, secrets removed, and record its size and hash."""
    document = state(root)
    if document.get("finalized"):
        return {"status": "finalized"}
    source = source or find_transcript()
    if source is None:
        return {"status": "no transcript found"}
    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    lines = _redacted_lines(source)
    files = _write(folder, SNAPSHOT_STEM, lines)
    copies = document.setdefault("copies", [])
    copies.append({"label": label, "at": utc_now(), "source": str(source), "lines": len(lines),
                   "sha256": _digest(lines), "files": files})
    _save(root, document)
    return {"status": "copied", "lines": len(lines), "files": files}


def finalize(root: Path, source: Path | None = None) -> dict[str, Any]:
    """Write the whole conversation once, check every earlier copy is contained in it, then
    delete the earlier copies."""
    document = state(root)
    if document.get("finalized"):
        return {"status": "finalized", "files": document.get("files", [])}
    source = source or find_transcript()
    copies = list(document.get("copies", []))
    sources = list(dict.fromkeys([item["source"] for item in copies] + ([str(source)] if source else [])))
    if not sources:
        return {"status": "no transcript found"}
    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    full = {name: _redacted_lines(Path(name)) for name in sources if Path(name).is_file()}
    problems = []
    for item in copies:
        lines = full.get(item["source"], [])
        # Cheap check: the earlier copy is exactly the start of the full conversation.
        if len(lines) < item["lines"] or _digest(lines[: item["lines"]]) != item["sha256"]:
            problems.append(f"the copy made at {item['at']} ({item.get('label') or 'save'}) is not contained in the full conversation")
    for part in sorted(folder.glob("part-*.jsonl")):
        # Parts written by the earlier logger: each must appear in the full conversation.
        text = part.read_text(encoding="utf-8")
        if not any(text in "".join(lines) for lines in full.values()):
            problems.append(f"{part.name} is not contained in the full conversation")
    files: list[str] = []
    for index, name in enumerate(sources, 1):
        stem = FINAL_STEM if len(sources) == 1 else f"{FINAL_STEM}-session-{index}"
        files += _write(folder, stem, full.get(name, []))
    if problems:
        document["final_check"] = {"at": utc_now(), "status": "earlier copies kept", "problems": problems}
        _save(root, document)
        return {"status": "earlier copies kept", "files": files, "problems": problems}
    for old in [folder / f"{SNAPSHOT_STEM}.jsonl", *folder.glob(f"{SNAPSHOT_STEM}-[0-9][0-9].jsonl"), *folder.glob("part-*.jsonl")]:
        old.unlink(missing_ok=True)
    final = {
        "finalized": utc_now(), "files": files, "lines": sum(len(lines) for lines in full.values()),
        "check": "every earlier copy matched, by line count and hash, the start of the full conversation; "
                 "the earlier copies were then deleted",
        "copies_checked": len(copies), "pushes": document.get("pushes", []),
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
