"""Advisory, host-capability-dependent model routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_control.io import workflow


def model_route(root: Path, task_type: str) -> dict[str, Any]:
    configuration = workflow(root / "WORKFLOW.yaml").get("adaptive_runtime", {}).get("model_routing", {})
    tiers = configuration.get("tiers", {})
    selected = str(configuration.get("default_tier", "strong"))
    for tier, record in tiers.items():
        if task_type in record.get("task_types", []):
            selected = str(tier)
            break
    record = tiers.get(selected, {})
    return {
        "optional": bool(configuration.get("optional", True)),
        "tier": selected,
        "model_class": str(record.get("model_class", "strongest_available")),
        "effort": str(record.get("effort", "high")),
        "fallback": str(configuration.get("fallback", "use_available_model")),
        "enforcement": "advisory_only",
    }
