#!/usr/bin/env python3
"""Reconcile a bounded assignment file with terminal dispositions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_control import PASS
from research_control.io import atomic_write_json, load_jsonl
from research_control.reconciliation.assignments import reconcile_records
from research_control.reporting import print_summary


def read_ids(path: Path) -> list[str]:
    if path.suffix == ".jsonl":
        return [str(row.get("input_id", row.get("id", ""))) for row in load_jsonl(path) if row.get("input_id", row.get("id"))]
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            return [str(item.get("input_id", item.get("id", item))) if isinstance(item, dict) else str(item) for item in value]
    return [line.strip().split(",", 1)[0] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, dest="reconciliation_id")
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--dispositions", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--allow-one-to-many", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    report = reconcile_records(
        reconciliation_id=args.reconciliation_id,
        assigned_ids=read_ids(args.assignments), dispositions=load_jsonl(args.dispositions),
        root=root,
        input_patterns=[str(args.assignments.resolve().relative_to(root)), str(args.dispositions.resolve().relative_to(root))],
        allow_one_to_many=args.allow_one_to_many,
    )
    out = args.out if args.out.is_absolute() else root / args.out
    atomic_write_json(out, report)
    print_summary(f"reconciliation:{args.reconciliation_id}", report, str(out))
    raise SystemExit(0 if report["status"] == PASS else 1)


if __name__ == "__main__":
    main()
