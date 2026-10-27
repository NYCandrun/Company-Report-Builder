"""Cited-fact verification split into independent shards.

The runtime lists the fact IDs the synthesis cites, writes one packet per fact,
and groups the facts by source into shards. Each shard is verified by its own
independent worker; the runtime merges the shard verdicts in cited order.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from research_control.deeplinks import source_excerpt
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text, load_json, load_jsonl
from research_control.validators import sources
from research_control.validators.facts import load_fact_tables

CITED_LIST = "tools/lists/cited-facts.txt"
PACKET_DIR = "tools/outputs/cited-facts"
PACKET_INDEX = f"{PACKET_DIR}/index.json"
PART_DIR = "tools/outputs/worker-parts/verification"
REUSED = f"{PACKET_DIR}/reused-verdicts.jsonl"
VERDICTS = "tools/outputs/verification-verdicts.jsonl"
REPORT = "06-checks/verification-cited.md"
# Verdicts for facts cited after verification finished, judged in a sandbox (`verify-new`).
ADDED = "tools/outputs/verification-verdicts-added.jsonl"
VERDICT_VALUES = ("confirmed", "corrected", "unsupported", "source unreachable")
# Soft shard size: one worker's careful read of the captures behind it. A
# source's facts stay together so its capture is read once.
SHARD_FACTS = 50
FACT_ID = re.compile(r"\b[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?\b")


def _facts(root: Path) -> dict[str, dict[str, str]]:
    paths = sorted((root / "02-facts").glob("*.md")) + sorted(root.glob("04-competitors/*/02-facts/*.md"))
    return {row["fact_id"]: row for row in load_fact_tables(paths) if row.get("fact_id")}


def cited_fact_ids(root: Path, known: set[str]) -> list[str]:
    """Fact IDs the synthesis cites, in first-citation order across its files."""
    ordered: dict[str, None] = {}
    for path in sorted((root / "05-synthesis").glob("*.md")):
        for fact_id in FACT_ID.findall(path.read_text(encoding="utf-8", errors="replace")):
            if fact_id in known:
                ordered.setdefault(fact_id, None)
    return list(ordered)


def prepare(root: Path) -> dict[str, Any]:
    """Write the cited-fact list, one packet per cited fact, and the packet index."""
    facts = _facts(root)
    cited = cited_fact_ids(root, set(facts))
    if not cited:
        raise ValueError("the synthesis cites no known fact IDs")
    prior = _prior_verdicts(root)
    manifest_path = root / "01-sources/MANIFEST.csv"
    manifest = {row.get("id", ""): row for row in sources.load_manifest(manifest_path)} if manifest_path.is_file() else {}
    index: dict[str, dict[str, str]] = {}
    for fact_id in cited:
        packet = fact_packet(root, facts, manifest, fact_id)
        source_id = packet["source"]["id"]
        relative = f"{PACKET_DIR}/{fact_id}.json"
        atomic_write_json(root / relative, packet)
        fingerprint = _fingerprint(packet)
        index[fact_id] = {"packet": relative, "source_id": source_id, "fingerprint": fingerprint}
    # A verdict carries over only for a packet identical to the one verified.
    reused = [prior[fact_id][1] for fact_id in cited if fact_id in prior and prior[fact_id][0] == index[fact_id]["fingerprint"]]
    atomic_write_jsonl(root / REUSED, reused)
    reused_ids = {row["fact_id"] for row in reused}
    for fact_id in reused_ids:
        index[fact_id]["reused"] = True
    atomic_write_text(root / CITED_LIST, "".join(f"{fact_id}\n" for fact_id in cited))
    atomic_write_json(root / PACKET_INDEX, {"cited": cited, "facts": index})
    return {
        "status": "PASS", "cited_facts": len(cited), "reused_verdicts": len(reused_ids),
        "to_verify": len(cited) - len(reused_ids), "sources": len({row["source_id"] for row in index.values()}),
    }


def fact_packet(root: Path, facts: dict[str, dict[str, str]], manifest: dict[str, dict[str, str]], fact_id: str) -> dict[str, Any]:
    """What a verifier judges one fact from: its row, its source, and the located quote in context."""
    fact = {key: value for key, value in facts[fact_id].items() if not key.startswith("_")}
    source_id = fact.get("source_id", "")
    source = manifest.get(source_id, {})
    return {
        "fact_id": fact_id,
        "fact": fact,
        "fact_table": str(Path(facts[fact_id]["_path"]).relative_to(root)),
        "fact_table_line": facts[fact_id]["_line"],
        "source": {
            "id": source_id, "url": source.get("url", ""), "grade": source.get("grade", ""),
            "date published": source.get("date published", ""),
            "local files": [item.strip() for item in source.get("local file", "").split(";") if item.strip()],
        },
        # The located quote with its context; the fingerprint leaves it out.
        "excerpt": source_excerpt(root, source_id, fact.get("verbatim_quote", "")),
    }


# What a verifier judges; bookkeeping columns (conflict groups, cross-links,
# filing verdict notes) can change without invalidating a verdict.
JUDGED_FIELDS = ("claim", "verbatim_quote", "source_id", "location", "source_date", "grade", "about", "said_by")


def _fingerprint(packet: dict[str, Any]) -> str:
    fact = {key: packet["fact"].get(key, "") for key in JUDGED_FIELDS}
    basis = {"fact": fact, "source": packet["source"]}
    return sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _prior_verdicts(root: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    """Earlier verdicts with the fingerprint of the packet each one judged."""
    index_path = root / PACKET_INDEX
    if not index_path.is_file():
        return {}
    facts = load_json(index_path).get("facts", {})
    rows: list[dict[str, Any]] = []
    for path in [root / VERDICTS, root / REUSED, root / ADDED, *sorted((root / PART_DIR).glob("*.jsonl"))]:
        if path.is_file():
            rows.extend(load_jsonl(path))
    prior: dict[str, tuple[str, dict[str, Any]]] = {}
    for row in rows:
        fact_id = str(row.get("fact_id", ""))
        fingerprint = facts.get(fact_id, {}).get("fingerprint")
        if fingerprint is None and fact_id in facts:
            # Index written before fingerprints existed: recompute from the packet it named.
            packet_path = root / facts[fact_id]["packet"]
            fingerprint = _fingerprint(load_json(packet_path)) if packet_path.is_file() else None
        if fingerprint and row.get("verdict") in VERDICT_VALUES:
            prior[fact_id] = (fingerprint, row)
    return prior


def shards(root: Path) -> list[list[str]]:
    """Group cited facts by source, then pack whole sources into shards."""
    index = load_json(root / PACKET_INDEX)
    by_source: dict[str, list[str]] = {}
    for fact_id in index["cited"]:
        if index["facts"][fact_id].get("reused"):
            continue
        by_source.setdefault(index["facts"][fact_id]["source_id"], []).append(fact_id)
    result: list[list[str]] = []
    current: list[str] = []
    for source_id in sorted(by_source, key=lambda value: (-len(by_source[value]), value)):
        group = by_source[source_id]
        if current and len(current) + len(group) > SHARD_FACTS:
            result.append(current)
            current = []
        current.extend(group)
    if current:
        result.append(current)
    return result


def shard_id(fact_ids: list[str]) -> str:
    return sha256("\n".join(fact_ids).encode("utf-8")).hexdigest()[:12]


def validate_part(root: Path, part: str, fact_ids: list[str]) -> list[str]:
    """Problems with one shard's verdict part: exactly one well-formed verdict per assigned fact."""
    path = root / part
    if not path.is_file():
        return [f"{part} is missing"]
    failures: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(load_jsonl(path), 1):
        fact_id = str(row.get("fact_id", ""))
        if fact_id not in fact_ids:
            failures.append(f"row {index}: {fact_id or 'missing fact_id'} is not assigned to this shard")
        elif fact_id in seen:
            failures.append(f"{fact_id}: duplicate verdict")
        seen.add(fact_id)
        if row.get("verdict") not in VERDICT_VALUES:
            failures.append(f"{fact_id or index}: invalid verdict {row.get('verdict')!r}")
        if not str(row.get("reason", "")).strip():
            failures.append(f"{fact_id or index}: missing reason")
        if not row.get("evidence_paths"):
            failures.append(f"{fact_id or index}: missing evidence paths")
        if row.get("verdict") == "corrected" and not (row.get("corrected_claim") or row.get("corrected_receipt")):
            failures.append(f"{fact_id}: corrected verdict lacks corrected_claim or corrected_receipt")
    missing = [fact_id for fact_id in fact_ids if fact_id not in seen]
    if missing:
        failures.append(f"no verdict for: {', '.join(missing[:15])}")
    return failures


def reduce_verdicts(root: Path, parts: list[str]) -> dict[str, Any]:
    """Merge shard verdicts in cited order and write the verification report."""
    cited = load_json(root / PACKET_INDEX)["cited"]
    verdicts: dict[str, dict[str, Any]] = {
        str(row["fact_id"]): row for row in (load_jsonl(root / REUSED) if (root / REUSED).is_file() else [])
    }
    for part in sorted(parts):
        for row in load_jsonl(root / part):
            fact_id = str(row.get("fact_id", ""))
            if fact_id in verdicts:
                raise ValueError(f"{fact_id}: verdicts in more than one shard or also reused")
            verdicts[fact_id] = row
    missing = [fact_id for fact_id in cited if fact_id not in verdicts]
    if missing:
        raise ValueError(f"no verdict for cited facts: {', '.join(missing[:15])}")
    ordered = [verdicts[fact_id] for fact_id in cited]
    atomic_write_jsonl(root / VERDICTS, ordered)
    counts = {value: sum(1 for row in ordered if row.get("verdict") == value) for value in VERDICT_VALUES}
    lines = [
        "# Cited-fact verification",
        "",
        f"Independent verifiers checked every fact the synthesis cites ({len(cited)} facts) in {len(parts)} "
        "shards grouped by source: quote at the stated location, attribution, claim scope, and date treatment.",
        "",
        "| Verdict | Facts |",
        "|---|---|",
        *(f"| {value} | {counts[value]} |" for value in VERDICT_VALUES),
        "",
        "## Facts needing correction or removal",
        "",
    ]
    problems = [row for row in ordered if row.get("verdict") != "confirmed"]
    if not problems:
        lines.append("None.")
    for row in problems:
        reason = re.sub(r"\s+", " ", str(row.get("reason", ""))).strip()
        correction = row.get("corrected_claim") or row.get("corrected_receipt") or ""
        if isinstance(correction, dict):
            correction = json.dumps(correction, ensure_ascii=False)
        detail = f" Correction: {correction}" if correction else ""
        lines.append(f"- `{row['fact_id']}` ({row['verdict']}): {reason}{detail}")
    atomic_write_text(root / REPORT, "\n".join(lines) + "\n")
    write_cited_rows(root, ordered)
    return {"status": "PASS", "verdicts": len(ordered), "parts": len(parts), **counts}


CITED_ROWS = "tools/outputs/cited-fact-rows.md"


def write_cited_rows(root: Path, verdicts: list[dict[str, Any]], output: str = "") -> None:
    """The cited facts as one compact table with their verdicts, dates, and deep links,
    so the brief and diagrams work from it instead of the whole fact store."""
    facts = _facts(root)
    links: dict[str, dict[str, Any]] = {}
    path = root / "tools/outputs/fact-links.jsonl"
    if path.is_file():
        links = {str(row.get("fact_id", "")): row for row in load_jsonl(path)}
    rows = []
    for row in verdicts:
        fact = facts.get(str(row["fact_id"]), {})
        cells = [
            str(row["fact_id"]), row.get("verdict", ""), fact.get("claim", ""), fact.get("verbatim_quote", ""),
            fact.get("source_id", ""), fact.get("source_date", ""), fact.get("grade", ""),
            str(row.get("corrected_claim") or ""), links.get(str(row["fact_id"]), {}).get("deep_link", ""),
        ]
        rows.append("| " + " | ".join(re.sub(r"\s+", " ", str(cell)).replace("|", "/") for cell in cells) + " |")
    atomic_write_text(root / (output or CITED_ROWS), "\n".join([
        "# Cited facts", "",
        f"Every fact the synthesis cites ({len(rows)}), with its verification verdict. Full rows are in 02-facts/.", "",
        "| Fact ID | Verdict | Claim | Verbatim quote | Source ID | Source date | Grade | Correction | Deep link |",
        "|---|---|---|---|---|---|---|---|---|", *rows,
    ]) + "\n")
