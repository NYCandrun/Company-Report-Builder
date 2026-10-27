"""Deterministic single-writer reducers for parallel worker parts."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from research_control.capture import MANIFEST_FIELDS
from research_control.io import (
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_text,
    load_json,
    load_jsonl,
    utc_now,
)
from research_control.runtime import DISCOVERY_TERMINAL, UNCAPTURED_RELEVANCE, RuntimeStore
from research_control.triage import excluded_dispositions


def _json_parts(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        value = load_json(path)
        if not isinstance(value, dict):
            raise ValueError(f"{path}: worker part must be a JSON object")
        value["_part_path"] = str(path)
        rows.append(value)
    return rows


def reduce_discovery(root: Path, store: RuntimeStore) -> dict[str, Any]:
    channels = store.discovery_channels()
    if not channels:
        raise ValueError("discovery has no channel records")
    unfinished = [item["channel"] for item in channels if item["state"] not in DISCOVERY_TERMINAL]
    if unfinished:
        raise ValueError(f"discovery channels are not terminal: {', '.join(unfinished)}")
    incomplete = [item["channel"] for item in channels if item["state"] == "incomplete"]
    if incomplete:
        raise ValueError(
            "discovery hit a safety circuit breaker and is incomplete: " + ", ".join(incomplete)
        )
    parts = _json_parts(root / "tools/outputs/worker-parts/discovery")
    by_channel = {str(part.get("channel")): part for part in parts}
    missing = [item["channel"] for item in channels if item["channel"] not in by_channel]
    if missing:
        raise ValueError(f"discovery worker receipts are missing: {', '.join(missing)}")
    failures: list[str] = []
    for item in channels:
        part = by_channel[item["channel"]]
        if part.get("status") != item["state"]:
            failures.append(
                f"{item['channel']}: receipt={part.get('status')} scheduler={item['state']}"
            )
        if not str(part.get("evidence", "")).strip():
            failures.append(f"{item['channel']}: receipt lacks completion evidence")
    if failures:
        raise ValueError("invalid discovery receipts: " + "; ".join(failures))
    result = {
        "schema_version": "1.0.0",
        "status": "PASS_WITH_LIMITATIONS" if any(item["state"] == "blocked" for item in channels) else "PASS",
        "completion_rule": "first-party fixed point plus question sufficiency or saturation; never a source count",
        "channels": channels,
        "source_count": len(store.sources()),
        "receipt_count": len(parts),
        "completed_at": utc_now(),
    }
    atomic_write_json(root / "tools/outputs/discovery/final.json", result)
    return result


def reduce_capture_parts(root: Path, store: RuntimeStore) -> dict[str, Any]:
    parts = _json_parts(root / "tools/outputs/worker-parts/capture")
    by_id: dict[str, dict[str, Any]] = {}
    for part in parts:
        source_id = str(part.get("source_id", ""))
        if not source_id:
            raise ValueError(f"{part['_part_path']}: capture receipt lacks source_id")
        if source_id in by_id:
            raise ValueError(f"duplicate capture receipt: {source_id}")
        by_id[source_id] = part
    considered = [
        source for source in store.sources()
        if source["relevance"] not in UNCAPTURED_RELEVANCE
    ]
    assigned = [source for source in considered if source["status"] != "blocked"]
    missing = [source["source_id"] for source in assigned if source["source_id"] not in by_id]
    if missing:
        raise ValueError(f"capture receipts missing for discovered sources: {', '.join(missing)}")
    manifest_rows: list[dict[str, str]] = []
    publish_dates: list[dict[str, str]] = []
    dispositions: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for source in considered:
        if source["status"] != "blocked":
            continue
        part = by_id.get(source["source_id"], {})
        reason = str(
            part.get("reason")
            or part.get("disposition", {}).get("reason")
            or source.get("metadata", {}).get("capture_reason")
            or source.get("metadata", {}).get("discovery_error")
            or "source access blocked"
        )
        blocked.append({"source_id": source["source_id"], "url": source["canonical_url"], "reason": reason})
    for source in assigned:
        part = by_id[source["source_id"]]
        status = str(part.get("status", ""))
        if status == "captured":
            row = part.get("source")
            if not isinstance(row, dict):
                raise ValueError(f"{source['source_id']}: captured receipt lacks source record")
            normalized = {field: str(row.get(field, "")) for field in MANIFEST_FIELDS}
            if normalized["id"] != source["source_id"]:
                raise ValueError(f"{source['source_id']}: receipt source ID mismatch")
            local_paths = [value.strip() for value in normalized["local file"].split(";") if value.strip()]
            absent = [value for value in local_paths if not (root / value).is_file() or not (root / value).stat().st_size]
            if absent:
                raise ValueError(f"{source['source_id']}: missing captured files: {', '.join(absent)}")
            if not part.get("canonical_text_ready"):
                raise ValueError(f"{source['source_id']}: canonical text derivative is not ready")
            manifest_rows.append(normalized)
            publish_dates.append({"id": source["source_id"], "date": normalized["date published"]})
            disposition = dict(part.get("disposition") or {})
            disposition.update({
                "assignment_id": f"capture.source.{source['source_id'].casefold()}",
                "input_id": source["source_id"],
                "disposition": "completed",
                "evidence_paths": local_paths,
                "output_ids": [source["source_id"]],
            })
            disposition.setdefault("reason", "captured and canonicalized")
            dispositions.append(disposition)
        elif status == "blocked":
            reason = str(part.get("reason") or part.get("disposition", {}).get("reason") or "capture blocked")
            blocked.append({"source_id": source["source_id"], "url": source["canonical_url"], "reason": reason})
        else:
            raise ValueError(f"{source['source_id']}: nonterminal capture receipt status {status!r}")
    if not manifest_rows:
        raise ValueError("no sources were successfully captured")
    _write_csv(root / "01-sources/MANIFEST.csv", MANIFEST_FIELDS, manifest_rows)
    _write_csv(root / "01-sources/publish-dates.csv", ("id", "date"), publish_dates)
    _write_csv(
        root / "tools/lists/extraction-scope.csv",
        ("id", "local_file", "estimated_tokens"),
        [
            {
                "id": row["id"],
                "local_file": row["local file"],
                "estimated_tokens": str(by_id[row["id"]].get("estimated_tokens", "")),
            }
            for row in manifest_rows
        ],
    )
    atomic_write_jsonl(root / "tools/outputs/capture-dispositions.jsonl", dispositions)
    blocked_lines = ["# Blocked sources", ""]
    if blocked:
        blocked_lines.extend(f"- `{item['source_id']}` — {item['url']} — {item['reason']}" for item in blocked)
    else:
        blocked_lines.append("None.")
    atomic_write_text(root / "01-sources/BLOCKED.md", "\n".join(blocked_lines) + "\n")
    leads = [source for source in store.sources() if source["relevance"] == "lead"]
    coverage = [
        "# Capture coverage", "",
        "Discovery had no source-count quota. The runtime crawled the first-party site to a fixed point and "
        "search channels closed as sufficient for named research questions or saturated.", "",
        f"- Discovered records considered: {len(considered)}",
        f"- Login-walled platform URLs kept as uncaptured leads: {len(leads)}",
        f"- Captured with canonical text: {len(manifest_rows)}",
        f"- Blocked: {len(blocked)}",
        f"- Disposition records: {len(dispositions)}",
        "",
        "See `06-checks/discovery-coverage.md` for per-channel fixed-point evidence.",
    ]
    media = [part for part in parts if part.get("transcript")]
    if media:
        transcribed = [part for part in media if part["transcript"].get("status") == "transcribed"]
        coverage.extend([
            "", "## Media transcripts", "",
            f"- Media sources: {len(media)}; transcribed: {len(transcribed)}; without transcript: {len(media) - len(transcribed)}",
        ])
        coverage.extend(
            f"- `{part['source_id']}` transcript unavailable: {part['transcript'].get('reason', 'unknown')}"
            for part in media if part["transcript"].get("status") != "transcribed"
        )
    atomic_write_text(root / "06-checks/coverage.md", "\n".join(coverage) + "\n")
    return {
        "status": "PASS",
        "assigned": len(considered),
        "captured": len(manifest_rows),
        "blocked": len(blocked),
        "manifest": "01-sources/MANIFEST.csv",
    }


def reduce_extraction_parts(root: Path) -> dict[str, Any]:
    directory = root / "tools/outputs/worker-parts/extraction"
    candidate_paths = sorted(directory.glob("*.candidates.jsonl")) if directory.is_dir() else []
    disposition_paths = sorted(directory.glob("*.dispositions.jsonl")) if directory.is_dir() else []
    if not candidate_paths or not disposition_paths:
        raise ValueError("extraction worker parts are missing")
    candidates: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for path in candidate_paths:
        part_rows = load_jsonl(path)
        batch = path.name.split(".candidates.jsonl", 1)[0].upper()
        prefix = f"CAND-{batch}-"
        for row in part_rows:
            identifier = str(row.get("candidate_id", row.get("id", "")))
            if not identifier.startswith(prefix):
                raise ValueError(f"{path}: candidate ID must start with {prefix}")
        candidates.extend(part_rows)
    for path in disposition_paths:
        dispositions.extend(load_jsonl(path))
    seen: set[str] = set()
    for index, row in enumerate(candidates, 1):
        identifier = str(row.get("candidate_id", row.get("id", "")))
        if not identifier:
            raise ValueError(f"candidate row {index} lacks candidate_id")
        if identifier in seen:
            raise ValueError(f"duplicate candidate ID: {identifier}")
        seen.add(identifier)
    disposition_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(dispositions, 1):
        assignment = str(row.get("assignment_id", ""))
        input_id = str(row.get("input_id", ""))
        if not assignment or not input_id or not row.get("disposition"):
            raise ValueError(f"disposition row {index} lacks assignment_id, input_id, or disposition")
        key = (assignment, input_id)
        if key in disposition_keys:
            raise ValueError(f"duplicate extraction disposition: {assignment}/{input_id}")
        disposition_keys.add(key)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in dispositions:
        source_id = str(row.get("source_id") or str(row["input_id"]).split(":", 1)[0])
        grouped.setdefault(source_id, []).append(row)
    aggregate: list[dict[str, Any]] = []
    for source_id, rows in sorted(grouped.items()):
        values = {str(row.get("disposition")) for row in rows}
        if "blocked" in values:
            disposition = "blocked"
        elif "completed" in values:
            disposition = "completed"
        elif values == {"completed_zero"}:
            disposition = "completed_zero"
        elif len(values) == 1:
            disposition = next(iter(values))
        else:
            raise ValueError(f"{source_id}: incompatible slice dispositions: {sorted(values)}")
        evidence = list(dict.fromkeys(
            str(value) for row in rows for value in row.get("evidence_paths", []) if str(value)
        ))
        outputs = list(dict.fromkeys(
            str(value) for row in rows for value in row.get("output_ids", []) if str(value)
        ))
        aggregate.append({
            "assignment_id": "facts.dynamic-extraction",
            "input_id": source_id,
            "disposition": disposition,
            "reason": f"aggregated {len(rows)} extraction slice disposition(s): {', '.join(sorted(values))}",
            "evidence_paths": evidence,
            "output_ids": outputs,
        })
    triaged_out = [row for row in excluded_dispositions(root) if row["input_id"] not in grouped]
    aggregate.extend(triaged_out)
    atomic_write_jsonl(root / "tools/candidates/all.jsonl", candidates)
    atomic_write_jsonl(root / "tools/outputs/extraction-dispositions.jsonl", aggregate)
    return {
        "status": "PASS",
        "candidate_parts": len(candidate_paths),
        "disposition_parts": len(disposition_paths),
        "candidates": len(candidates),
        "slice_dispositions": len(dispositions),
        "dispositions": len(aggregate),
        "excluded_by_triage": len(triaged_out),
    }


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, buffer.getvalue())
