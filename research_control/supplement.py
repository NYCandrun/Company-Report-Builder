"""Supplementary evidence added after later phases already ran.

When a source is recaptured with more content (a repository's code, say), its
new text is extracted as a supplement: the facts already filed from it stand,
new facts are appended, and synthesis is reconciled with them instead of the
run rebuilding everything downstream.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, atomic_write_text, load_json, utc_now

SUPPLEMENT_LIST = "tools/lists/supplement-sources.json"
SUPPLEMENT_FACTS = "tools/lists/supplement-facts.txt"
SUPPLEMENT_REPORT = "06-checks/supplement-reconciliation.md"
# Slices the orchestrator chose not to extract (a token budget): each is held by
# its text's hash, so a slice whose text changes is planned again.
DEFERRED_SLICES = "tools/lists/deferred-slices.json"


def supplement_sources(root: Path) -> dict[str, str]:
    """Source IDs being supplemented, with the reason for each."""
    path = root / SUPPLEMENT_LIST
    return dict(load_json(path).get("sources", {})) if path.is_file() else {}


def supplement_added_at(root: Path) -> dict[str, str]:
    """When each source was last listed: batches planned before then do not cover its text."""
    path = root / SUPPLEMENT_LIST
    return dict(load_json(path).get("added_at", {})) if path.is_file() else {}


def add_supplement(root: Path, source_ids: list[str], reason: str, at: str | None = None) -> dict[str, Any]:
    """List sources for supplement extraction. Listing a source again (for a new
    question or new rules) has its current text extracted again; filed facts stand."""
    if not reason.strip():
        raise ValueError("a supplement needs a reason")
    sources = supplement_sources(root)
    added = supplement_added_at(root)
    stamp = at or utc_now()
    for source_id in source_ids:
        sources[source_id] = reason.strip()
        added[source_id] = stamp
    document = {"sources": dict(sorted(sources.items())), "added_at": dict(sorted(added.items()))}
    path = root / SUPPLEMENT_LIST
    if not path.is_file() or load_json(path) != document:
        atomic_write_json(path, document)
    return {"sources": sources}


def base_source(input_id: str) -> str:
    """The source ID behind an extraction input ID such as ``SRC-X:part-0002``."""
    return str(input_id).split(":", 1)[0]


def deferred_slices(root: Path) -> dict[str, dict[str, str]]:
    """Extraction slices left out on purpose, with their text's hash and the reason."""
    path = root / DEFERRED_SLICES
    return dict(load_json(path).get("slices", {})) if path.is_file() else {}


def defer_slices(root: Path, slice_ids: list[str], reason: str) -> dict[str, Any]:
    """Leave slices out of extraction; the record keeps the gap visible."""
    if not reason.strip():
        raise ValueError("deferring a slice needs a reason")
    from hashlib import sha256

    slices = deferred_slices(root)
    for slice_id in slice_ids:
        path = root / "tools/extracts/slices" / f"{slice_id.replace(':', '.')}.txt"
        if not path.is_file():
            raise KeyError(f"unknown slice: {slice_id}")
        digest = sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        slices[slice_id] = {"sha256": digest, "reason": reason.strip(), "at": utc_now()}
    atomic_write_json(root / DEFERRED_SLICES, {"slices": dict(sorted(slices.items()))})
    return {"deferred": sorted(slices)}


# A supplement is reconciled from a digest, not the fact store: one line per new
# fact (ID, date, grade, source, claim, delivery status, relationship basis),
# split by the synthesis file its question feeds, so each file's reconcile reads
# only its share and opens full rows only for the facts it cites.
SUPPLEMENT_DIGESTS = "tools/digests/supplement"
SUPPLEMENT_PARTS = "tools/outputs/worker-parts/supplement"
SYNTHESIS_TARGETS = (
    (("competitor",), "competitors"),
    (("product", "architecture", "dependenc", "technolog", "stack"), "product-map"),
    (("buyer", "offer", "pricing", "service", "sales"), "offering"),
    (("customer", "proof", "partner", "account", "engagement", "client"), "customers-proof"),
    (("position", "messag", "brand"), "messaging-timeline"),
    (("people", "org", "talent", "team", "scale", "financ", "hiring"), "organization"),
    (("direction", "launch", "acquisition", "roadmap", "context"), "direction"),
)
DELIVERY_STATUS = re.compile(r"\b(Shipped|Built, unmerged|Promised)\b")
RELATIONSHIP_BASIS = re.compile(r"Relationship basis:\s*(Stated|Inferred|Lead[^.;|]*)")


def synthesis_target(fact_file: str) -> str:
    """The synthesis file a fact table's question feeds."""
    name = Path(fact_file).stem.casefold()
    return next((target for words, target in SYNTHESIS_TARGETS if any(word in name for word in words)), "open-questions")


def write_supplement_digests(root: Path, fact_ids: list[str]) -> dict[str, int]:
    from research_control.validators.facts import load_fact_tables

    from research_control.validators.facts import withdrawn_facts

    wanted = set(fact_ids) - set(withdrawn_facts(root))
    lines: dict[str, list[str]] = {}
    for path in sorted((root / "02-facts").glob("*.md")):
        for row in load_fact_tables([path]):
            if row.get("fact_id") not in wanted:
                continue
            # Notes are not a named column of the fact table; marks are read from the whole row.
            notes = " ".join(value for key, value in row.items() if not key.startswith("_") and key != "claim")
            marks = [match.group(1) for match in (DELIVERY_STATUS.search(notes),) if match]
            marks += [f"relationship {match.group(1).strip()}" for match in (RELATIONSHIP_BASIS.search(notes),) if match]
            if "My inference" in row.get("claim", ""):
                marks.append("inference")
            line = (f"- {row['fact_id']} · {row.get('source_date', '')[:10]} · {row.get('grade', '')} · "
                    f"{row.get('source_id', '')} · {row.get('claim', '').strip()}")
            lines.setdefault(synthesis_target(path.name), []).append(line + (f" [{'; '.join(marks)}]" if marks else ""))
    directory = root / SUPPLEMENT_DIGESTS
    if directory.is_dir():
        for stale in directory.glob("*.md"):
            stale.unlink()
    for target, rows in lines.items():
        atomic_write_text(directory / f"{target}.md", (
            f"# New facts for 05-synthesis/{target}.md ({len(rows)})\n\n"
            "One line per fact: ID · source date · grade · source ID · claim [delivery status; relationship basis].\n"
            "Open a fact's full row (quote, location, notes) by searching 02-facts/ for its ID.\n\n"
            + "\n".join(rows) + "\n"
        ))
    return {target: len(rows) for target, rows in lines.items()}


def reduce_supplement(root: Path, identifier: str) -> dict[str, Any]:
    """Write this pass's section of the reconciliation report: each listed fact's
    decision from the reconcile parts, or where it is cited, or left uncited."""
    import json

    listed = [line.strip() for line in (root / SUPPLEMENT_FACTS).read_text(encoding="utf-8").splitlines() if line.strip()]
    decisions: dict[str, dict[str, Any]] = {}
    for path in sorted((root / SUPPLEMENT_PARTS).glob(f"{identifier}.*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                decisions.setdefault(str(row.get("fact_id", "")), row)
    cited: dict[str, list[str]] = {}
    for path in sorted((root / "05-synthesis").glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for fact_id in listed:
            if re.search(rf"\b{re.escape(fact_id)}\b", text):
                cited.setdefault(fact_id, []).append(path.name)
    rows: list[str] = []
    counts = {"cited": 0, "left uncited": 0}
    for fact_id in listed:
        decision = decisions.get(fact_id)
        where = ", ".join(cited.get(fact_id, []))
        if decision or where:
            counts["cited"] += 1
            kind = str((decision or {}).get("decision", "cited"))
            why = str((decision or {}).get("why", "")).replace("|", "/")
            rows.append(f"| {fact_id} | {kind} | {where or (decision or {}).get('file', '')} | {why} |")
        else:
            counts["left uncited"] += 1
            rows.append(f"| {fact_id} | left uncited | | adds nothing a reader of its synthesis file needs (digest reviewed) |")
    report = root / SUPPLEMENT_REPORT
    existing = report.read_text(encoding="utf-8") if report.is_file() else "# Supplement reconciliation\n"
    marker = f"## Pass {identifier}"
    existing = re.split(rf"\n{re.escape(marker)}\b", existing, maxsplit=1)[0].rstrip("\n")
    section = [
        "", f"{marker} ({utc_now()[:10]}: {len(listed)} facts; {counts['cited']} cited, {counts['left uncited']} left uncited)", "",
        "| Fact ID | Decision | File | Why |", "|---|---|---|---|", *rows,
    ]
    atomic_write_text(report, existing + "\n" + "\n".join(section) + "\n")
    return {"listed": len(listed), **counts}
