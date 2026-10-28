"""Verify facts cited after verification finished, in a sandbox, without rerunning it.

When a run adds facts after its verification phase (a later search, such as a
market and competitor pass), only the facts newly cited in the synthesis or
the report need a verdict. `verify-new` prepares packets for just those facts
in their own folder, writes one self-contained brief for a single verifier,
checks the verdicts, and adds them to `tools/outputs/verification-verdicts-
added.jsonl`, which every verdict check reads alongside the main verdict
file. The finished verification work (its packets, shards, and merged
verdicts) is not touched: when the new facts left it marked for rerun, the
merge restores it, so nothing upstream or downstream is redone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_control import verification
from research_control.dispatch import _prompt
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text, load_json, load_jsonl, utc_now
from research_control.validators import american, sources

SANDBOX = "tools/outputs/verification-sandbox"
ADDED_ROWS = "tools/outputs/cited-fact-rows-added.md"
REPORT = "06-checks/verification-added.md"
# Where new citations appear: the synthesis and the report.
CITING_FILES = ("05-synthesis/*.md",)
VERIFICATION_TASKS = ("verification.prepare", "verification.reduce-verdicts")


def verdict_rows(root: Path) -> list[dict[str, Any]]:
    """Every verdict: the verification phase's, then those added in a sandbox for facts it never saw."""
    main = load_jsonl(root / verification.VERDICTS) if (root / verification.VERDICTS).is_file() else []
    seen = {str(row.get("fact_id")) for row in main}
    added = load_jsonl(root / verification.ADDED) if (root / verification.ADDED).is_file() else []
    return main + [row for row in added if str(row.get("fact_id")) not in seen]


def unverified(root: Path, patterns: tuple[str, ...] = CITING_FILES) -> list[str]:
    """Known facts cited in these files that have no verdict yet, in first-citation order."""
    facts = verification._facts(root)
    judged = {str(row.get("fact_id")) for row in verdict_rows(root)}
    ordered: dict[str, None] = {}
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            for fact_id in verification.FACT_ID.findall(path.read_text(encoding="utf-8", errors="replace")):
                if fact_id in facts and fact_id not in judged:
                    ordered.setdefault(fact_id, None)
    return list(ordered)


def _folder(root: Path, label: str) -> Path:
    return root / SANDBOX / label


def prepare(root: Path, label: str = "", fact_ids: list[str] | None = None) -> dict[str, Any]:
    """Packets and a brief for the unverified facts, in `SANDBOX/<label>/`."""
    label = label or utc_now().replace(":", "").replace("-", "").lower()
    facts = verification._facts(root)
    chosen = list(dict.fromkeys(fact_ids)) if fact_ids else unverified(root)
    unknown = [fact_id for fact_id in chosen if fact_id not in facts]
    if unknown:
        raise ValueError(f"not in the fact store: {', '.join(unknown[:10])}")
    if not chosen:
        return {"label": label, "facts": 0, "status": "nothing to verify"}
    manifest_path = root / "01-sources/MANIFEST.csv"
    manifest = {row.get("id", ""): row for row in sources.load_manifest(manifest_path)} if manifest_path.is_file() else {}
    folder = _folder(root, label)
    packets = [verification.fact_packet(root, facts, manifest, fact_id) for fact_id in chosen]
    for packet in packets:
        atomic_write_json(folder / "packets" / f"{packet['fact_id']}.json", packet)
    atomic_write_json(folder / "assignment.json", {"label": label, "created": utc_now(), "fact_ids": chosen})
    output = f"{SANDBOX}/{label}/verdicts.jsonl"
    rules = "\n\n".join(_prompt(root, relative, "verification").strip() for relative in (
        "prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/phases/verification.md"))
    brief = [
        f"# Verify {len(chosen)} facts cited after verification finished", "",
        "This is a sandboxed verification of new facts only. You hold no scheduler task: do not run "
        "`research_control run`, `work claim`, or `work succeed`, and edit nothing outside "
        f"`{SANDBOX}/{label}/`.", "",
        f"Judge every fact below exactly as the rules say, and write one verdict per fact, in the order listed, "
        f"to `{output}` (one JSON object per line with `fact_id`, `verdict`, `reason`, and `evidence_paths`; "
        "a corrected verdict also has `corrected_claim` or `corrected_receipt`).", "",
        f"Finish: run `python3 -m research_control verify-new --check {label}` and fix what it reports until it "
        "is clean. Then report in under 60 words, in plain English: counts by verdict and anything unusual.", "",
        "---", "", "## Rules", "", rules, "", "---", "", f"## The facts ({len(chosen)})", "",
    ]
    for packet in packets:
        brief += [f"### {packet['fact_id']}", "", "```json", json.dumps(packet, ensure_ascii=False, indent=1), "```", ""]
    atomic_write_text(folder / "brief.md", "\n".join(brief) + "\n")
    return {"label": label, "facts": len(chosen), "brief": str((folder / "brief.md").relative_to(root)),
            "verdicts": output}


def check(root: Path, label: str) -> list[str]:
    """Problems with a sandbox's verdicts: one well-formed verdict per fact, in American English."""
    folder = _folder(root, label)
    fact_ids = load_json(folder / "assignment.json")["fact_ids"]
    relative = str((folder / "verdicts.jsonl").relative_to(root))
    problems = verification.validate_part(root, relative, fact_ids)
    if not problems:
        problems += [f"American English: {item}" for item in american.check_file(folder / "verdicts.jsonl")]
    return problems


def merge(root: Path, label: str) -> dict[str, Any]:
    """Add a clean sandbox's verdicts to the added-verdict file and settle the verification work."""
    problems = check(root, label)
    if problems:
        raise ValueError("the sandbox verdicts are not clean: " + "; ".join(problems[:15]))
    rows = load_jsonl(_folder(root, label) / "verdicts.jsonl")
    for row in rows:
        row["verified_in"] = f"sandbox {label}"
    new_ids = {str(row["fact_id"]) for row in rows}
    path = root / verification.ADDED
    kept = [row for row in (load_jsonl(path) if path.is_file() else []) if str(row.get("fact_id")) not in new_ids]
    added = kept + rows
    atomic_write_jsonl(path, added)
    verification.write_cited_rows(root, added, ADDED_ROWS)
    counts: dict[str, int] = {}
    for row in added:
        counts[str(row.get("verdict"))] = counts.get(str(row.get("verdict")), 0) + 1
    lines = [
        "# Facts verified after the verification phase", "",
        f"{len(added)} facts cited after verification finished were judged in sandboxes, by the same rules as "
        "the verification phase, without rerunning it: " + ", ".join(f"{count} {verdict}" for verdict, count in sorted(counts.items())) + ".",
        "", "| Fact ID | Verdict | Reason | Sandbox |", "|---|---|---|---|",
        *(f"| {row['fact_id']} | {row['verdict']} | {str(row.get('reason', '')).replace('|', '/')[:200]} | "
          f"{row.get('verified_in', '')} |" for row in added),
    ]
    atomic_write_text(root / REPORT, "\n".join(lines) + "\n")
    restored = _settle(root, label)
    from research_control.orchestration import append_history

    append_history(root, "verification-added", f"sandbox {label}: {len(rows)} verdicts added; restored {', '.join(restored) or 'nothing'}")
    return {"label": label, "added": len(rows), "verdicts": counts, "rows": ADDED_ROWS, "restored": restored}


def _settle(root: Path, label: str) -> list[str]:
    """The verification phase's finished work stands: restore it if the new facts marked it for rerun."""
    from research_control.adaptive import open_runtime

    restored: list[str] = []
    if not (root / "tools/outputs/runtime.sqlite3").is_file():
        return restored
    with open_runtime(root) as store:
        for task_id in VERIFICATION_TASKS:
            task = store.task(task_id)
            if task and task["state"] in {"stale", "ready", "planned"}:
                store.restore(task_id, f"new facts verified in sandbox {label}; finished verification stands")
                restored.append(task_id)
    return restored
