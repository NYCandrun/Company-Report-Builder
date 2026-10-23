#!/usr/bin/env python3
"""Audit traceability and structural acceptance for the refactored system."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_control import FAIL, PASS
from research_control.hashing import checker_version, hash_patterns
from research_control.io import atomic_write_json
from research_control.reporting import make_validation_report, print_summary


ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATIONS = {"principle", "scope", "contract", "procedure", "schema", "deterministic_check", "semantic_review", "reconciliation", "gate", "test", "runtime_state", "reporting", "presentation"}
ENFORCEMENT = {"prompt", "schema", "script", "workflow", "model_review", "human_or_model_visual_review", "git", "ci", "mixed"}
REQUIRED_PROMPTS = {
    "prompts/core/evidence.md", "prompts/core/writing.md", "prompts/core/runtime.md",
    *{f"prompts/phases/{name}.md" for name in (
        "capture", "extraction", "synthesis", "verification", "review-technical",
        "review-devils-advocate", "review-insider", "review-editor", "fixer",
        "brief-writing", "citation-review", "visual-review", "scope", "filing",
        "publication-build", "publication-fixer", "language-review", "orchestrator-review",
    )},
}
REQUIRED_SCHEMAS = {f"research_control/schemas/{name}.schema.json" for name in (
    "source", "fact", "worker", "disposition", "validation", "gate",
    "review-finding", "release", "run", "task", "verification", "visual-review",
)}


def audit(require_preserved: bool = False) -> dict:
    failures: list[str] = []
    inventory = list(csv.DictReader((ROOT / "REQUIREMENT_INVENTORY.csv").open(encoding="utf-8")))
    if not inventory:
        failures.append("requirement inventory is empty")
    ids = [row.get("requirement_id", "") for row in inventory]
    if len(ids) != len(set(ids)):
        failures.append("requirement IDs are not unique")
    for row in inventory:
        label = row.get("requirement_id", "unknown")
        if not row.get("destination"):
            failures.append(f"{label}: no destination")
        if row.get("classification") not in CLASSIFICATIONS:
            failures.append(f"{label}: invalid classification")
        if row.get("enforcement_type") not in ENFORCEMENT:
            failures.append(f"{label}: invalid enforcement type")
        if require_preserved and row.get("preservation_status") != "preserved":
            failures.append(f"{label}: preservation status is not preserved")

    headings = [line for line in (ROOT / "docs/legacy-prompt.md").read_text(encoding="utf-8").splitlines() if re.match(r"^#{1,6} ", line)]
    mapped = [line for line in (ROOT / "MIGRATION_MAP.md").read_text(encoding="utf-8").splitlines() if line.startswith("| docs/legacy-prompt.md:")]
    if len(headings) != len(mapped):
        failures.append(f"migration map has {len(mapped)} rows for {len(headings)} README headings")

    failure_ids = re.findall(r"^## (F\d+)\b", (ROOT / "FAILURE_REGISTRY.md").read_text(encoding="utf-8"), re.MULTILINE)
    if len(failure_ids) != len(set(failure_ids)) or not failure_ids:
        failures.append("failure registry IDs are empty or duplicated")

    workflow = json.loads((ROOT / "WORKFLOW.yaml").read_text(encoding="utf-8"))
    phase_ids = [phase["id"] for phase in workflow.get("phases", [])]
    expected_order = ["capture", "facts", "initial_synthesis", "verification", "corrected_synthesis", "review", "final", "publication_checks", "release_acceptance"]
    positions = [phase_ids.index(phase) if phase in phase_ids else -1 for phase in expected_order]
    if -1 in positions or positions != sorted(positions):
        failures.append("effective research phase order is missing or changed")
    gate_names = {phase.get("gate", {}).get("name") for phase in workflow.get("phases", [])}
    if not {"capture", "facts", "verification", "review", "final"}.issubset(gate_names):
        failures.append("one or more required named gates are absent")
    contract_fields = {"depends_on", "inputs", "outputs", "reconciliations", "validators", "semantic_reviews", "tests", "completion", "stale_if", "downstream"}
    for phase in workflow.get("phases", []):
        missing = contract_fields - set(phase)
        if missing:
            failures.append(f"phase {phase.get('id')}: missing contract fields {sorted(missing)}")
    profiles = workflow.get("execution_profiles", {})
    if set(profiles) != set(phase_ids):
        failures.append("execution profiles do not exactly cover workflow phases")
    for phase_id, profile in profiles.items():
        task_ids = [task.get("id") for task in profile.get("tasks", [])]
        if len(task_ids) != len(set(task_ids)):
            failures.append(f"execution profile {phase_id}: duplicate task IDs")
        for task in profile.get("tasks", []):
            label = f"{phase_id}.{task.get('id', 'unknown')}"
            for field in ("id", "task_type", "prompt", "outputs"):
                if not task.get(field):
                    failures.append(f"execution task {label}: missing {field}")
            for dependency in task.get("depends_on", []):
                if dependency not in task_ids:
                    failures.append(f"execution task {label}: unknown dependency {dependency}")

    for relative in sorted(REQUIRED_PROMPTS | REQUIRED_SCHEMAS):
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size == 0:
            failures.append(f"missing required artifact {relative}")
        elif path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                failures.append(f"invalid schema JSON {relative}: {error}")

    status = FAIL if failures else PASS
    return make_validation_report(
        checker="refactor_traceability", checker_version=checker_version(sys.modules[__name__]),
        status=status, expected_count=len(inventory) + len(headings) + len(failure_ids),
        checked_count=len(inventory) + len(mapped) + len(set(failure_ids)), failures=failures,
        input_hashes=hash_patterns(ROOT, [
            "README.md", "docs/legacy-prompt.md", "REQUIREMENT_INVENTORY.csv", "FAILURE_REGISTRY.md",
            "MIGRATION_MAP.md", "RESEARCH_CONSTITUTION.md", "WORKFLOW.yaml",
            "prompts/**", "research_control/schemas/**",
        ]),
        details={"requirements": len(inventory), "headings": len(headings), "failure_modes": len(failure_ids)},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-preserved", action="store_true")
    args = parser.parse_args()
    report = audit(args.require_preserved)
    path = args.out or ROOT / "tools/outputs/validations/refactor-traceability.json"
    atomic_write_json(path, report)
    print_summary("refactor", report, str(path))
    raise SystemExit(0 if report["status"] == PASS else 1)


if __name__ == "__main__":
    main()
