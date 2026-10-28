"""Shared fail-closed validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_control import FAIL, PASS, UNKNOWN
from research_control.hashing import checker_version, hash_patterns
from research_control.reporting import make_validation_report


VALIDATION_REQUIRED = {
    "checker", "checker_version", "status", "expected_count", "checked_count",
    "failure_count", "exception_count", "input_hashes", "completed_at",
}


def validate_report_shape(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["report is not an object"]
    missing = sorted(VALIDATION_REQUIRED - set(value))
    if missing:
        errors.append(f"missing report fields: {', '.join(missing)}")
    if value.get("status") not in {PASS, FAIL, UNKNOWN}:
        errors.append(f"invalid status: {value.get('status')!r}")
    for field in ("expected_count", "checked_count", "failure_count", "exception_count"):
        if not isinstance(value.get(field), int) or value.get(field, -1) < 0:
            errors.append(f"{field} must be a nonnegative integer")
    if isinstance(value.get("expected_count"), int) and isinstance(value.get("checked_count"), int):
        if value.get("status") == PASS and value["checked_count"] < value["expected_count"]:
            errors.append("PASS report checked fewer records than expected")
    if value.get("status") == PASS and value.get("failure_count", 0):
        errors.append("PASS report has failures")
    if not isinstance(value.get("input_hashes"), dict):
        errors.append("input_hashes must be an object")
    return errors


def report_for(
    module: Any,
    checker: str,
    root: Path,
    patterns: list[str],
    expected: int,
    checked: int,
    failures: list[str],
    unknowns: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unresolved = unknowns or []
    status = FAIL if failures else UNKNOWN if unresolved or checked < expected else PASS
    return make_validation_report(
        checker=checker,
        checker_version=checker_version(module),
        status=status,
        expected_count=expected,
        checked_count=checked,
        failures=failures,
        unknowns=unresolved,
        input_hashes=hash_patterns(root, patterns),
        details=details,
    )
