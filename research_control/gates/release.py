"""Independent release acceptance bound to exact validated artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from research_control import FAIL, PASS, UNKNOWN
from research_control.hashing import checker_version, hash_path, hash_patterns, report_inputs_current, sha256_file
from research_control.io import atomic_write_json, load_json, load_jsonl, resolve_pattern, utc_now, workflow
from research_control.reconciliation.assignments import validate_ledger
from research_control.reporting import make_validation_report, print_summary
from research_control.validators.common import validate_report_shape
from .phase_gate import gate_report_is_current


FINAL_ARTIFACTS = [
    "07-final-report/company-brief.pdf",
    "07-final-report/company-brief.html",
    "07-final-report/one-page.pdf",
    "07-final-report/one-page.html",
]


def _git_commit(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else None


def _load_exceptions(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    path = root / "tools/outputs/accepted-exceptions.json"
    if not path.exists():
        return [], []
    failures: list[str] = []
    try:
        value = load_json(path)
    except Exception as error:
        return [], [f"accepted exceptions are unreadable: {error}"]
    if not isinstance(value, list):
        return [], ["accepted exceptions must be an array"]
    for index, item in enumerate(value, 1):
        if not all(str(item.get(field, "")).strip() for field in ("exception_id", "control_id", "reason", "evidence_path")):
            failures.append(f"exception {index}: missing ID, control, reason, or evidence path")
        elif not (root / item["evidence_path"]).exists():
            failures.append(f"exception {item['exception_id']}: evidence path not found")
    return value, failures


def _all_required_reports(document: dict[str, Any]) -> list[tuple[str, str]]:
    reports: list[tuple[str, str]] = []
    for phase in document["phases"]:
        for group in ("reconciliations", "validators"):
            for item in phase.get(group, []):
                if phase["id"] == "release_acceptance" and item["id"] == "release_acceptance":
                    continue
                reports.append((f"{phase['id']}:{group}:{item['id']}", item["report"]))
    for test in document.get("test_suites", []):
        reports.append((f"test:{test['id']}", test["report"]))
    return reports


def _artifact_hashes(root: Path) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for relative in FINAL_ARTIFACTS:
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(relative)
        else:
            hashes[relative] = sha256_file(path)
    return hashes, missing


def check_release(root: Path, workflow_path: Path | None = None, write_manifest: bool = True) -> tuple[dict[str, Any], Path, Path]:
    workflow_path = workflow_path or root / "WORKFLOW.yaml"
    document = workflow(workflow_path)
    failures: list[str] = []
    unknowns: list[str] = []
    checked = 0
    expected = 0

    exceptions, exception_errors = _load_exceptions(root)
    failures.extend(exception_errors)

    gate_summaries: dict[str, Any] = {}
    for phase in document["phases"]:
        gate = phase.get("gate")
        if not gate:
            continue
        gate_name = gate.get("name", phase["id"])
        expected += 1
        path = root / document["global"]["gate_directory"] / f"{gate_name}.json"
        if not path.is_file():
            unknowns.append(f"gate {gate_name}: missing report")
            continue
        try:
            report = load_json(path)
        except Exception as error:
            unknowns.append(f"gate {gate_name}: unreadable report: {error}")
            continue
        current, errors = gate_report_is_current(root, report)
        gate_summaries[gate_name] = {"status": report.get("status"), "path": str(path.relative_to(root)), "hash": sha256_file(path)}
        checked += 1
        if report.get("status") == FAIL:
            failures.append(f"gate {gate_name}: FAIL")
        elif not current:
            unknowns.extend(f"gate {gate_name}: {item}" for item in errors or ["not current"])

    report_summaries: dict[str, Any] = {}
    test_summaries: dict[str, Any] = {}
    for label, relative in _all_required_reports(document):
        expected += 1
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            unknowns.append(f"{label}: missing or empty report {relative}")
            continue
        try:
            report = load_json(path)
        except Exception as error:
            unknowns.append(f"{label}: unreadable report: {error}")
            continue
        shape = validate_report_shape(report)
        if shape:
            unknowns.extend(f"{label}: {item}" for item in shape)
        current, stale = report_inputs_current(root, report)
        if not current:
            unknowns.extend(f"{label}: stale input {item}" for item in stale)
        if report.get("status") == FAIL:
            failures.append(f"{label}: FAIL")
        elif report.get("status") != PASS:
            unknowns.append(f"{label}: {report.get('status')}")
        checked += 1
        target = test_summaries if label.startswith("test:") else report_summaries
        target[label] = {"status": report.get("status"), "path": relative, "hash": sha256_file(path)}

    expected += 1
    ledger_path = root / document["global"]["ledger"]
    if not ledger_path.is_file() or ledger_path.stat().st_size == 0:
        unknowns.append("worker ledger missing or empty")
    else:
        try:
            ledger = validate_ledger(root, load_jsonl(ledger_path))
            checked += 1
            covered_controls = {str(item.get("control_id")) for item in exceptions}
            for issue in ledger.get("failures", []):
                if "ended blocked" in issue and any(control in issue for control in covered_controls):
                    continue
                failures.append(f"worker ledger: {issue}")
            unknowns.extend(f"worker ledger: {item}" for item in ledger.get("unknowns", []))
        except Exception as error:
            unknowns.append(f"worker ledger unreadable: {error}")

    artifact_hashes, missing_artifacts = _artifact_hashes(root)
    expected += len(FINAL_ARTIFACTS)
    checked += len(FINAL_ARTIFACTS) - len(missing_artifacts)
    unknowns.extend(f"final artifact missing or empty: {item}" for item in missing_artifacts)

    binding_path = root / "tools/outputs/validations/artifact-binding.json"
    if binding_path.is_file():
        binding = load_json(binding_path)
        bound = binding.get("details", {}).get("artifact_hashes", {})
        for relative, digest in artifact_hashes.items():
            if bound.get(relative) != digest:
                failures.append(f"final artifact does not match validated hash: {relative}")
    else:
        unknowns.append("artifact-binding validation report is missing")

    status = FAIL if failures else UNKNOWN if unknowns or checked < expected else PASS
    evidence_patterns = [
        "WORKFLOW.yaml", document["global"]["ledger"], "01-sources/MANIFEST.csv",
        "02-facts/**", "05-synthesis/**", *FINAL_ARTIFACTS,
    ]
    evidence_patterns.extend(
        f"{document['global']['gate_directory']}/{phase['gate'].get('name', phase['id'])}.json"
        for phase in document["phases"] if phase.get("gate")
    )
    evidence_patterns.extend(relative for _label, relative in _all_required_reports(document))
    report = make_validation_report(
        checker="release_acceptance", checker_version=checker_version(sys.modules[__name__]),
        status=status, expected_count=expected, checked_count=checked,
        failures=failures, unknowns=unknowns,
        input_hashes=hash_patterns(root, evidence_patterns),
        details={"artifact_hashes": artifact_hashes, "exceptions": exceptions},
    )
    validation_path = root / "tools/outputs/validations/release-acceptance.json"
    atomic_write_json(validation_path, report)
    manifest_path = root / document["global"]["release_manifest"]

    if status == PASS and write_manifest:
        visual = report_summaries.get("publication_checks:validators:visual_records", {})
        manifest = {
            "schema_version": "1.0.0", "status": PASS,
            "acceptance_timestamp": utc_now(), "checker_version": report["checker_version"],
            "git_commit": _git_commit(root), "artifacts": artifact_hashes,
            "evidence_hashes": hash_patterns(root, [
                "01-sources/MANIFEST.csv", "02-facts/**", "tools/outputs/citation-map-*.json",
                "05-synthesis/company-brief.md", "05-synthesis/one-page.md", "tools/brief_html/**",
            ]),
            "gates": gate_summaries,
            "reconciliations": {key: value for key, value in report_summaries.items() if ":reconciliations:" in key},
            "tests": test_summaries,
            "visual_review": visual,
            "exceptions": exceptions,
            "validated_content_commit": _git_commit(root),
            "manifest_commit": None,
        }
        atomic_write_json(manifest_path, manifest)
    return report, validation_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workflow", type=Path)
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args()
    report, validation_path, manifest_path = check_release(args.root.resolve(), args.workflow, not args.no_manifest)
    print_summary("release", report, str(validation_path))
    if report["status"] == PASS:
        print(f"release_manifest={manifest_path}")
    raise SystemExit(0 if report["status"] == PASS else 1)


if __name__ == "__main__":
    main()
