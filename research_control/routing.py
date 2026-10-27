"""Advisory, host-capability-dependent model routing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from research_control.io import workflow


def model_route(root: Path, task_type: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    configuration = workflow(root / "WORKFLOW.yaml").get("adaptive_runtime", {}).get("model_routing", {})
    tiers = configuration.get("tiers", {})
    selected = str(configuration.get("default_tier", "strong"))
    for tier, record in tiers.items():
        if task_type in record.get("task_types", []):
            selected = str(tier)
            break
    # A task planned with its own tier (an extraction batch by the kind of source
    # it reads) keeps it.
    if metadata and str(metadata.get("model_tier", "")) in tiers:
        selected = str(metadata["model_tier"])
    record = tiers.get(selected, {})
    return {
        "optional": bool(configuration.get("optional", True)),
        "tier": selected,
        "model_class": str(record.get("model_class", "strongest_available")),
        "effort": str(record.get("effort", "high")),
        "fallback": str(configuration.get("fallback", "use_available_model")),
        "enforcement": "advisory_only",
    }


# Business records kept in a repository (account books, call notes, proposals,
# plans) need the judgment that transcripts do; code, specs, and data do not.
BUSINESS_WORDS = re.compile(
    r"\b(client|customer|prospect|account|deal|pipeline|budget|revenue|bookings|proposal|sow|statement of work|"
    r"contract|renewal|invoice|pricing|quota|meeting|call notes|stakeholder|engagement|org chart|headcount)\b",
    re.IGNORECASE,
)
PROSE_FILE = re.compile(r"^--- FILE: \S+\.(md|mdx|txt|pdf|docx?|rst)\b", re.MULTILINE | re.IGNORECASE)
ANY_FILE = re.compile(r"^--- FILE: ", re.MULTILINE)


def source_kind(text: str, source_paths: list[str]) -> str:
    """`recording`, `business_records`, `repository`, or `page`, for extraction routing."""
    if any(Path(path).name == "transcript.txt" for path in source_paths):
        return "recording"
    if "Repository: " not in text[:400] and not ANY_FILE.search(text) and "=== COMMIT " not in text:
        return "page"
    files = len(ANY_FILE.findall(text))
    prose = len(PROSE_FILE.findall(text))
    density = len(BUSINESS_WORDS.findall(text)) / max(len(text) / 1000, 1)
    if (files and prose / files >= 0.5 and density >= 1.0) or density >= 2.5:
        return "business_records"
    return "repository"


def extraction_tier(root: Path, kind: str) -> str:
    configuration = workflow(root / "WORKFLOW.yaml").get("adaptive_runtime", {}).get("model_routing", {})
    return str(configuration.get("extraction_tiers", {}).get(kind, configuration.get("default_tier", "strong")))
