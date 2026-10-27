"""Keep a run's evidence on the remote, so nothing is captured twice.

A run lives in an ignored folder of the template checkout, so its sources,
transcripts, facts, and drafts exist only on the machine that ran it. `archive`
commits the run to its own branch of the template's remote (`run-data/<slug>`)
through a separate git directory, leaving the template branch untouched. Each
archive is a new commit, so the branch is the run's history too.

Kept: every capture (page text and HTML, transcripts and captions, receipts),
the fact store, synthesis, checks, final report, scheduler snapshot, and a git
bundle of each cloned repository with all its history, branches, and pull
request heads. Left out: downloaded audio (its transcript is kept), the HTTP
transport cache, worker scratch space, and live database files.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

from research_control.capture import GIT_CACHE
from research_control.io import atomic_write_text, load_json, utc_now

ARCHIVE_GIT = "tools/archive.git"
BUNDLE_DIR = "01-sources/repositories"
BUNDLE_MANIFEST = "01-sources/repositories/MANIFEST.json"
SNAPSHOT_DB = "tools/outputs/runtime-snapshot.sqlite3"
# GitHub refuses files over 100 MB; a larger repository keeps its captured text.
BUNDLE_LIMIT_BYTES = 95 * 1024 * 1024
EXCLUDES = (
    "/tools/archive.git/",
    "/tools/outputs/git-cache/",
    "/tools/outputs/web-cache/",
    "/tools/outputs/runtime.sqlite3",
    "/tools/outputs/runtime.sqlite3-*",
    "/scratchpad/",
    "*.part",
    "*.ytdl",
    "audio.*",
    "*.mp3",
    "*.m4a",
    "*.wav",
    "*.webm",
    "*.opus",
    "*.ogg",
    "__pycache__/",
)


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["git", f"--git-dir={root / ARCHIVE_GIT}", f"--work-tree={root}", *args]
    result = subprocess.run(command, text=True, capture_output=True, timeout=1800)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {(result.stderr or result.stdout).strip()[:400]}")
    return result


def _snapshot_database(root: Path) -> None:
    live = root / "tools/outputs/runtime.sqlite3"
    if not live.is_file():
        return
    target = root / SNAPSHOT_DB
    with sqlite3.connect(f"file:{live}?mode=ro", uri=True) as source, sqlite3.connect(target) as copy:
        source.backup(copy)


def _bundle_repositories(root: Path) -> dict[str, Any]:
    """A full git bundle of each cloned repository, or why it was left out."""
    cache = root / GIT_CACHE
    directory = root / BUNDLE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    for git_dir in sorted(cache.glob("*/*/.git")):
        checkout = git_dir.parent
        name = f"{checkout.parent.name}__{checkout.name}"
        bundle = directory / f"{name}.bundle"
        head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True, capture_output=True).stdout.strip()
        if bundle.is_file() and manifest_entry(root, name).get("head") == head:
            manifest[name] = manifest_entry(root, name)
            continue
        result = subprocess.run(
            ["git", "-C", str(checkout), "bundle", "create", str(bundle), "--all"],
            text=True, capture_output=True, timeout=1800,
        )
        if result.returncode != 0:
            bundle.unlink(missing_ok=True)
            manifest[name] = {"status": "not bundled", "reason": result.stderr.strip()[:300]}
            continue
        size = bundle.stat().st_size
        if size > BUNDLE_LIMIT_BYTES:
            bundle.unlink()
            manifest[name] = {
                "status": "not bundled", "head": head,
                "reason": f"bundle of {size // (1024 * 1024)} MB is over the remote's file limit; its captured text is kept",
            }
            continue
        manifest[name] = {"status": "bundled", "head": head, "bytes": size, "path": str(bundle.relative_to(root))}
    atomic_write_text(root / BUNDLE_MANIFEST, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def manifest_entry(root: Path, name: str) -> dict[str, Any]:
    path = root / BUNDLE_MANIFEST
    return dict(load_json(path).get(name, {})) if path.is_file() else {}


def _remote_url(root: Path) -> str:
    state = root / "tools/outputs/run-state.json"
    template = Path(load_json(state).get("template", "")) if state.is_file() else Path()
    candidates = [template, root.parent.parent]
    for candidate in candidates:
        result = subprocess.run(["git", "-C", str(candidate), "remote", "get-url", "origin"], text=True, capture_output=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    raise RuntimeError("no origin remote found for the template checkout; pass --remote")


def archive(root: Path, *, remote: str | None = None, branch: str | None = None, push: bool = True) -> dict[str, Any]:
    root = root.resolve()
    state = load_json(root / "tools/outputs/run-state.json")
    slug = str(state.get("slug") or root.name)
    branch = branch or f"run-data/{slug}"
    if not (root / ARCHIVE_GIT).is_dir():
        subprocess.run(["git", "init", "--quiet", "--bare", str(root / ARCHIVE_GIT)], check=True)
        _git(root, "config", "core.bare", "false")
        _git(root, "config", "user.name", os.environ.get("GIT_AUTHOR_NAME", "research-control"))
        _git(root, "config", "user.email", os.environ.get("GIT_AUTHOR_EMAIL", "research-control@localhost"))
    atomic_write_text(root / ARCHIVE_GIT / "info/exclude", "\n".join(EXCLUDES) + "\n")
    _snapshot_database(root)
    bundles = _bundle_repositories(root)
    _git(root, "add", "--all", ".")
    changed = _git(root, "diff", "--cached", "--quiet", check=False).returncode != 0
    if changed:
        _git(root, "commit", "--quiet", "-m", f"Archive {slug} at {utc_now()}")
    head = _git(root, "rev-parse", "HEAD", check=False).stdout.strip()
    pushed = False
    if push and head:
        url = remote or _remote_url(root)
        for delay in (2, 4, 8, 16, 0):
            result = _git(root, "push", "--quiet", url, f"HEAD:refs/heads/{branch}", check=False)
            if result.returncode == 0:
                pushed = True
                break
            if not delay:
                raise RuntimeError(f"push to {branch} failed: {(result.stderr or result.stdout).strip()[:400]}")
            time.sleep(delay)
    return {
        "branch": branch, "commit": head, "committed": changed, "pushed": pushed,
        "repositories": {name: entry.get("status") for name, entry in bundles.items()},
    }
