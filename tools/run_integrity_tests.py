#!/usr/bin/env python3
"""Run control-plane regression categories and write fail-closed reports."""

from __future__ import annotations

import argparse
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_control import FAIL, PASS
from research_control.hashing import checker_version, hash_patterns
from research_control.io import atomic_write_json
from research_control.reporting import make_validation_report, print_summary


ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "adaptive_runtime": [
        "research_control.tests.test_runtime",
        "research_control.tests.test_discovery",
        "research_control.tests.test_adaptive_planner",
    ],
    "data_integrity": ["research_control.tests.test_sources", "research_control.tests.test_facts"],
    "evidence_pipeline": ["research_control.tests.test_facts", "research_control.tests.test_reconciliation"],
    "citation_integrity": ["research_control.tests.test_citations"],
    "execution_integrity": ["research_control.tests.test_reconciliation", "research_control.tests.test_phase_gates", "research_control.tests.test_staleness", "research_control.tests.test_visual_records"],
    "release_integrity": ["research_control.tests.test_release", "research_control.tests.test_staleness"],
}


def run_category(name: str, report_dir: Path) -> dict:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromName(module) for module in CATEGORIES[name])
    expected = suite.countTestCases()
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=1).run(suite)
    failures = [f"{test.id()}: {traceback.splitlines()[-1]}" for test, traceback in result.failures + result.errors]
    if result.unexpectedSuccesses:
        failures.extend(f"unexpected success: {test.id()}" for test in result.unexpectedSuccesses)
    report = make_validation_report(
        checker=f"test_suite:{name}", checker_version=checker_version(sys.modules[__name__]),
        status=PASS if result.wasSuccessful() else FAIL,
        expected_count=expected, checked_count=result.testsRun,
        failures=failures,
        input_hashes=hash_patterns(ROOT, [
            "research_control/**/*.py", "research_control/schemas/*.json",
            "research_control/tests/fixtures/**", "WORKFLOW.yaml",
        ]),
        details={"skipped": len(result.skipped), "runner_output": output.getvalue()},
    )
    path = report_dir / f"{name}.json"
    atomic_write_json(path, report)
    print_summary(f"tests:{name}", report, str(path))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("categories", nargs="*", choices=sorted(CATEGORIES))
    parser.add_argument("--report-dir", type=Path, default=ROOT / "tools/outputs/tests")
    args = parser.parse_args()
    names = args.categories or list(CATEGORIES)
    reports = [run_category(name, args.report_dir) for name in names]
    raise SystemExit(0 if all(report["status"] == PASS for report in reports) else 1)


if __name__ == "__main__":
    main()
