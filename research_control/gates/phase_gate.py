"""Fail-closed phase gates driven only by WORKFLOW.yaml."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from research_control import FAIL, PASS, UNKNOWN
from research_control.hashing import checker_version, hash_patterns, report_inputs_current
from research_control.io import atomic_write_json, find_phase, load_json, load_jsonl, require_nonempty_paths, resolve_pattern, workflow
from research_control.reconciliation.assignments import validate_ledger
from research_control.reporting import make_validation_report, print_summary
from research_control.validators.common import validate_report_shape


def phases_by_id(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {phase["id"]: phase for phase in document["phases"]}


def ancestor_gates(document: dict[str, Any], phase: dict[str, Any]) -> list[str]:
    phases = phases_by_id(document)
    found: list[str] = []
    seen: set[str] = set()

    def visit(phase_id: str) -> None:
        if phase_id in seen:
            return
        seen.add(phase_id)
        candidate = phases[phase_id]
        for dependency in candidate.get("depends_on", []):
            visit(dependency)
        gate = candidate.get("gate")
        if gate:
            found.append(gate.get("name", phase_id))

    for dependency in phase.get("depends_on", []):
        visit(dependency)
    return list(dict.fromkeys(found))


def gate_report_is_current(root: Path, report: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = validate_report_shape(report)
    current, stale = report_inputs_current(root, report)
    if not current:
        errors.extend(f"stale input: {item}" for item in stale)
    return not errors and report.get("status") == PASS, errors


def _report_for_id(phase: dict[str, Any], group: str, record_id: str) -> str | None:
    for item in phase.get(group, []):
        if isinstance(item, dict) and item.get("id") == record_id:
            return item.get("report")
    return None


def _load_required_report(root: Path, relative: str, label: str, failures: list[str], unknowns: list[str]) -> dict[str, Any] | None:
    path = root / relative
    if not path.is_file() or path.stat().st_size == 0:
        unknowns.append(f"{label}: missing or empty report {relative}")
        return None
    try:
        report = load_json(path)
    except Exception as error:  # fail closed on malformed evidence
        unknowns.append(f"{label}: unreadable report {relative}: {error}")
        return None
    shape = validate_report_shape(report)
    if shape:
        unknowns.extend(f"{label}: {error}" for error in shape)
        return report
    if report.get("status") == FAIL:
        failures.append(f"{label}: report status FAIL")
    elif report.get("status") != PASS:
        unknowns.append(f"{label}: report status {report.get('status')}")
    current, stale = report_inputs_current(root, report)
    if not current:
        unknowns.extend(f"{label}: stale input {item}" for item in stale)
    return report


def _state_claims_complete_without_gate(root: Path, phase_id: str, gate_path: Path) -> bool:
    state = root / "WORKFLOW_STATE.md"
    if not state.is_file():
        return False
    if gate_path.is_file():
        try:
            prior = load_json(gate_path)
            current, _errors = gate_report_is_current(root, prior)
            if current:
                return False
        except Exception:
            pass
    text = state.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(rf"(?im)^\s*\|?\s*(?:phase\s+)?{re.escape(phase_id)}\b[^\n]*\b(done|complete)\b")
    return bool(pattern.search(text))


def check_phase_gate(
    root: Path,
    phase_name: str,
    workflow_path: Path | None = None,
    write: bool = True,
    allow_completed_recheck: bool = False,
) -> tuple[dict[str, Any], Path]:
    workflow_path = workflow_path or root / "WORKFLOW.yaml"
    document = workflow(workflow_path)
    phase = find_phase(document, phase_name)
    gate = phase.get("gate")
    if not gate:
        raise ValueError(f"phase {phase['id']} has no executable gate")
    gate_name = gate.get("name", phase["id"])
    gate_path = root / document["global"]["gate_directory"] / f"{gate_name}.json"
    failures: list[str] = []
    unknowns: list[str] = []
    checked = 0
    expected = 0

    dependencies = ancestor_gates(document, phase)
    for dependency in dependencies:
        expected += 1
        report_path = root / document["global"]["gate_directory"] / f"{dependency}.json"
        report = _load_required_report(root, str(report_path.relative_to(root)), f"dependency gate {dependency}", failures, unknowns)
        if report is not None:
            checked += 1

    required_paths = gate.get("required_paths", [])
    present, missing = require_nonempty_paths(root, required_paths)
    expected += len(required_paths)
    checked += len(required_paths) - len(missing)
    unknowns.extend(f"required path missing or empty: {path}" for path in missing)

    for group, key in (("reconciliations", "required_reconciliations"), ("validators", "required_validators")):
        for record_id in gate.get(key, []):
            expected += 1
            relative = _report_for_id(phase, group, record_id)
            if not relative:
                unknowns.append(f"{group} {record_id}: no report path in workflow")
                continue
            if _load_required_report(root, relative, f"{group} {record_id}", failures, unknowns) is not None:
                checked += 1

    for review_id in gate.get("required_semantic_reviews", []):
        expected += 1
        review = next((item for item in phase.get("semantic_reviews", []) if item.get("id") == review_id), None)
        if review is None:
            unknowns.append(f"semantic review {review_id}: not declared")
            continue
        matches = [path for path in resolve_pattern(root, review["path"]) if path.is_file() and path.stat().st_size > 0]
        if not matches:
            unknowns.append(f"semantic review {review_id}: missing or empty {review['path']}")
        else:
            checked += 1

    worker_types = set(gate.get("required_worker_task_types", []))
    if worker_types:
        expected += 1
        ledger_path = root / document["global"]["ledger"]
        if not ledger_path.is_file() or ledger_path.stat().st_size == 0:
            unknowns.append(f"worker ledger missing or empty: {ledger_path.relative_to(root)}")
        else:
            try:
                ledger_report = validate_ledger(root, load_jsonl(ledger_path), worker_types)
                checked += 1
                failures.extend(f"worker ledger: {item}" for item in ledger_report.get("failures", []))
                unknowns.extend(f"worker ledger: {item}" for item in ledger_report.get("unknowns", []))
            except Exception as error:
                unknowns.append(f"worker ledger unreadable: {error}")

    if not allow_completed_recheck and _state_claims_complete_without_gate(root, phase["id"], gate_path):
        failures.append(f"WORKFLOW_STATE.md marks {phase['id']} complete without an existing passing gate")

    status = FAIL if failures else UNKNOWN if unknowns or checked < expected else PASS
    patterns = list(phase.get("stale_if", []))
    # The gate validates the relevant ledger task types above. Do not hash the
    # entire append-only ledger here: later phases append unrelated attempts and
    # must not make an earlier gate stale. A final release refresh re-evaluates
    # every gate against the complete current ledger.
    patterns.append(str(workflow_path.relative_to(root)))
    for group, key in (("reconciliations", "required_reconciliations"), ("validators", "required_validators")):
        patterns.extend(filter(None, (_report_for_id(phase, group, item) for item in gate.get(key, []))))
    for review_id in gate.get("required_semantic_reviews", []):
        review = next((item for item in phase.get("semantic_reviews", []) if item.get("id") == review_id), None)
        if review:
            patterns.append(review["path"])
    report = make_validation_report(
        checker=f"phase_gate:{gate_name}", checker_version=checker_version(sys.modules[__name__]),
        status=status, expected_count=expected, checked_count=checked,
        failures=failures, unknowns=unknowns, input_hashes=hash_patterns(root, patterns),
        details={"present_paths": present, "required_worker_task_types": sorted(worker_types)},
    )
    report.update({"gate": gate_name, "phase": phase["id"], "dependency_gates": dependencies})
    if write:
        atomic_write_json(gate_path, report)
    return report, gate_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workflow", type=Path)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    report, path = check_phase_gate(args.root.resolve(), args.phase, args.workflow, not args.no_write)
    print_summary(f"gate:{report['gate']}", report, str(path))
    raise SystemExit(0 if report["status"] == PASS else 1)


if __name__ == "__main__":
    main()
