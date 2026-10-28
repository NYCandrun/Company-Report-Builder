"""Provision an isolated run directory from the research template.

A run never writes into the template checkout. Each company run gets its own
directory holding a snapshot of the policy, prompts, and control engine it was
started with, so the run is reproducible and the template stays clean.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


TEMPLATE_FILES = ("README.md", "RESEARCH_CONSTITUTION.md", "WORKFLOW.yaml", "pyproject.toml")
TEMPLATE_DIRECTORIES = ("prompts", "research_control", "tools")
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", "outputs", "tests")
RUNS_DIRECTORY = "runs"


def _digest(paths: list[Path], base: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: value.as_posix()):
        digest.update(path.relative_to(base).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode())
    return digest.hexdigest()[:16]


def engine_fingerprint(root: Path) -> dict[str, str]:
    """Short hashes of the policy, workflow, prompts, and engine a run is using."""
    root = root.resolve()

    def files(pattern: str) -> list[Path]:
        return [path for path in root.glob(pattern) if path.is_file() and "__pycache__" not in path.parts]

    return {
        "constitution": _digest(files("RESEARCH_CONSTITUTION.md"), root),
        "workflow": _digest(files("WORKFLOW.yaml"), root),
        "prompts": _digest(files("prompts/**/*.md"), root),
        "engine": _digest(files("research_control/**/*.py"), root),
    }


def run_slug(company_url: str) -> str:
    host = (urlparse(company_url.strip()).hostname or "").casefold().removeprefix("www.")
    return re.sub(r"[^a-z0-9]+", "-", host).strip("-") or "company"


def provision_run(template_root: Path, run_root: Path) -> Path:
    """Copy the template into ``run_root``; an existing run is left untouched."""
    template_root = template_root.resolve()
    run_root = run_root.resolve()
    if run_root == template_root:
        raise ValueError("a run directory must differ from the template root")
    if (run_root / "tools/outputs/run-state.json").is_file():
        return run_root
    missing = [name for name in TEMPLATE_FILES + TEMPLATE_DIRECTORIES if not (template_root / name).exists()]
    if missing:
        raise FileNotFoundError(f"template is incomplete: {', '.join(missing)}")
    run_root.mkdir(parents=True, exist_ok=True)
    for name in TEMPLATE_FILES:
        shutil.copy2(template_root / name, run_root / name)
    for name in TEMPLATE_DIRECTORIES:
        shutil.copytree(template_root / name, run_root / name, ignore=IGNORED, dirs_exist_ok=True)
    return run_root


def sync_engine(template_root: Path, run_root: Path) -> list[str]:
    """Refresh a run's engine, prompts, and policy from the template.

    Used when the framework is revised while a run is in flight. Run outputs are
    never touched; changed validators and prompts invalidate dependent work
    through the normal input-hash and validation-engine checks.
    """
    template_root = template_root.resolve()
    run_root = run_root.resolve()
    if run_root == template_root:
        raise ValueError("sync-engine must run from the template checkout with --root pointing at the run")
    if not (run_root / "tools/outputs/run-state.json").is_file():
        raise FileNotFoundError(f"no run exists at {run_root}")
    for name in TEMPLATE_FILES:
        shutil.copy2(template_root / name, run_root / name)
    for name in TEMPLATE_DIRECTORIES:
        shutil.copytree(template_root / name, run_root / name, ignore=IGNORED, dirs_exist_ok=True)
    from research_control.orchestration import append_history

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=template_root, text=True, capture_output=True
    ).stdout.strip() or "unknown"
    fingerprint = engine_fingerprint(run_root)
    append_history(
        run_root, "engine-synced",
        f"template_commit={commit} " + " ".join(f"{key}={value}" for key, value in fingerprint.items()),
    )
    return [*TEMPLATE_FILES, *TEMPLATE_DIRECTORIES]
