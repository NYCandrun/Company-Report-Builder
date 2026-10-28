"""Canonical machine report and concise model-facing summaries."""

from __future__ import annotations

from typing import Any, Iterable

from research_control import FAIL, PASS, UNKNOWN
from research_control.io import utc_now


def make_validation_report(
    *,
    checker: str,
    checker_version: str,
    status: str,
    expected_count: int,
    checked_count: int,
    failures: Iterable[str] = (),
    unknowns: Iterable[str] = (),
    input_hashes: dict[str, str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failed = list(failures)
    unresolved = list(unknowns)
    if status not in {PASS, FAIL, UNKNOWN}:
        raise ValueError(f"invalid validation status: {status}")
    if checked_count < expected_count and status == PASS:
        status = UNKNOWN
        unresolved.append(f"checked {checked_count} of {expected_count} expected records")
    if failed and status == PASS:
        status = FAIL
    if unresolved and status == PASS:
        status = UNKNOWN
    return {
        "schema_version": "1.0.0",
        "checker": checker,
        "checker_version": checker_version,
        "status": status,
        "expected_count": expected_count,
        "checked_count": checked_count,
        "failure_count": len(failed),
        "exception_count": len(unresolved),
        "failures": failed,
        "unknowns": unresolved,
        "input_hashes": dict(sorted((input_hashes or {}).items())),
        "completed_at": utc_now(),
        "details": details or {},
    }


def print_summary(name: str, report: dict[str, Any], path: str) -> str:
    summary = (
        f"{name} {report['status']} expected={report['expected_count']} "
        f"checked={report['checked_count']} failures={report['failure_count']} "
        f"exceptions={report['exception_count']} report={path}"
    )
    print(summary)
    for item in (report.get("failures", []) + report.get("unknowns", []))[:20]:
        print(f"  {item}")
    return summary
