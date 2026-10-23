#!/usr/bin/env python3
"""Build the traceability inventory from the preserved historical prompt.

The source prompt is intentionally not edited.  This parser errs on the side of
preservation: it inventories imperative prose, contract-like bullets, table
rows, and path/field declarations that participate in a normative block.  The
result is then audited alongside the migration map.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/legacy-prompt.md"
OUTPUT = ROOT / "REQUIREMENT_INVENTORY.csv"

NORMATIVE = re.compile(
    r"\b(must|never|only|do not|don't|required|cannot|can't|should|before|after|"
    r"until|unless|exactly|every|no |one |separate|independent|deterministic|"
    r"high-reasoning|create|write|record|keep|use|include|preserve|capture|"
    r"check|run|read|save|mark|assign|report|validate|verify|flag|prefer|"
    r"follow|back off|commit|push|finish|apply|build|render|resolve|retry|"
    r"remove|state|say|ask|store|split|group|target|aim|remain|stay|leave|"
    r"support|operate|compare|inspect|open|return|maintain|track|deduplicate|"
    r"normalize|rebuild|rerun|re-run|exit|emit|match|link|list)\b",
    re.IGNORECASE,
)


@dataclass
class Block:
    line: int
    section: str
    text: str
    kind: str


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def source_blocks(lines: list[str]) -> list[Block]:
    """Return auditable Markdown blocks with their heading path and line."""
    headings: dict[int, str] = {}
    out: list[Block] = []
    paragraph: list[str] = []
    paragraph_line = 0
    in_fence = False
    fence_intro: Block | None = None

    def section() -> str:
        return " > ".join(headings[level] for level in sorted(headings))

    def flush_paragraph() -> None:
        nonlocal paragraph, paragraph_line, fence_intro
        if paragraph:
            block = Block(paragraph_line, section(), clean(" ".join(paragraph)), "paragraph")
            out.append(block)
            fence_intro = block
        paragraph = []
        paragraph_line = 0

    for number, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading and not in_fence:
            flush_paragraph()
            level = len(heading.group(1))
            headings[level] = clean(heading.group(2))
            for old in list(headings):
                if old > level:
                    del headings[old]
            continue
        if line.strip().startswith("```"):
            if not in_fence:
                flush_paragraph()
                in_fence = True
            else:
                in_fence = False
            continue
        if in_fence:
            # Code/schema bodies are represented by the prose that requires them.
            continue
        if not line.strip() or line.strip() == "---":
            flush_paragraph()
            continue
        if re.match(r"^\s*\|.*\|\s*$", line):
            flush_paragraph()
            cells = [clean(x) for x in line.strip().strip("|").split("|")]
            if cells and not all(re.fullmatch(r":?-+:?", x) for x in cells):
                out.append(Block(number, section(), " | ".join(cells), "table"))
            continue
        item = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.*)$", line)
        if item:
            flush_paragraph()
            out.append(Block(number, section(), clean(item.group(1)), "list"))
            continue
        if line.startswith(" ") and out and out[-1].kind == "list":
            out[-1].text = clean(out[-1].text + " " + line)
            continue
        if not paragraph:
            paragraph_line = number
        paragraph.append(line)
    flush_paragraph()
    return out


def is_normative(block: Block) -> bool:
    text = block.text
    if block.kind in {"list", "table"}:
        # Lists and tables in this prompt commonly inherit an imperative from
        # their lead-in (required fields, inclusions, checks, or exclusions).
        return not text.startswith(("Examples:", "Example:"))
    return bool(NORMATIVE.search(text)) or text.endswith(":")


def family(section: str) -> str:
    matches = re.findall(r"(?:^| > )(-?\d+)(?:\.|\b)", section)
    return matches[-1] if matches else "intro"


def leaf(section: str) -> str:
    return section.rsplit(" > ", 1)[-1].lower()


def layer(section: str, text: str) -> str:
    group = family(section)
    s = leaf(section)
    t = text.lower()
    if group in {"-1", "8", "17", "18", "19"} or "execution integrity" in s:
        return "execution integrity"
    if group in {"0", "5", "15", "16"} or any(x in s for x in ("citation", "company brief", "writing", "visual", "design", "typesetting", "reader-facing")):
        return "publication integrity"
    if group in {"1", "6", "13", "14"} or any(x in s for x in ("sense-making", "review", "currency", "what is true now")):
        return "reasoning quality"
    if group in {"4", "10", "11", "12"} or any(x in s for x in ("evidence", "facts", "capture", "verification")):
        return "evidence validity"
    if group == "7":
        return "data integrity"
    if any(x in t for x in ("schema", "unique", "hash", "file exists", "manifest", "source id", "count")):
        return "data integrity"
    return "execution integrity"


def classification(section: str, text: str) -> str:
    group = family(section)
    s = leaf(section)
    t = text.lower()
    if (group == "18" or "final report" in s) and "report" in t:
        return "reporting"
    if any(x in s for x in ("design", "typesetting", "reader-facing", "company brief", "one-page")):
        return "presentation"
    if "scope" in s or "inputs" in s:
        return "scope"
    if any(x in t for x in ("schema", "columns:", "fields:", "field")):
        return "schema"
    if group in {"17", "19"} or any(x in s for x in ("gate", "done means", "execution integrity")):
        return "gate"
    if any(x in s for x in ("review", "verification")) and "script" not in t:
        return "semantic_review"
    if any(x in t for x in ("reconcile", "assigned input", "disposition")):
        return "reconciliation"
    if any(x in t for x in ("test", "fixture", "plant")):
        return "test"
    if any(x in t for x in ("script", "deterministic", "hash", "exit code", "validate")):
        return "deterministic_check"
    if any(x in s for x in ("workflow", "orchestrate", "phase")):
        return "procedure"
    if any(x in t for x in ("worker", "agent", "output path", "input assignment")):
        return "contract"
    if any(x in t for x in ("state", "ledger", "history")):
        return "runtime_state"
    return "principle"


def destination(section: str, text: str, klass: str) -> str:
    group = family(section)
    s = leaf(section)
    t = text.lower()
    destinations: list[str] = []
    if group in {"0", "1", "2", "3", "4", "5", "6"} or any(x in s for x in ("goal", "scope", "evidence", "writing rules", "what is true now")):
        destinations.append("RESEARCH_CONSTITUTION.md")
    if group in {"8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19"} or klass in {"procedure", "gate", "runtime_state", "reconciliation"} or "phase" in s:
        destinations.append("WORKFLOW.yaml")
    if klass == "schema":
        destinations.append("research_control/schemas/")
    if klass in {"deterministic_check", "reconciliation", "gate", "test"}:
        destinations.append("research_control/")
    if klass in {"semantic_review", "contract"} or "agent" in t or "worker" in t:
        destinations.append("prompts/")
    if klass in {"presentation", "reporting"}:
        destinations.extend(["RESEARCH_CONSTITUTION.md", "WORKFLOW.yaml"])
    if not destinations:
        destinations.append("RESEARCH_CONSTITUTION.md")
    return "; ".join(dict.fromkeys(destinations))


def enforcement(klass: str, text: str) -> str:
    t = text.lower()
    if klass == "schema":
        return "schema"
    if klass in {"gate", "reconciliation", "procedure", "runtime_state"}:
        return "workflow"
    if klass in {"deterministic_check", "test"}:
        return "script"
    if klass == "semantic_review":
        return "model_review"
    if any(x in t for x in ("view every page", "visual review", "opens every page")):
        return "human_or_model_visual_review"
    if "commit" in t or "git" in t:
        return "git"
    if any(x in t for x in ("script", "agent", "model", "deterministic")):
        return "mixed"
    return "prompt"


def existing_implementation(text: str) -> str:
    paths = re.findall(r"`([^`]+)`", text)
    existing: list[str] = []
    for raw in paths:
        if raw.startswith(("tools/", "prompt/", "0", "README", "WORKFLOW", "RUN_HISTORY")):
            candidate = ROOT / raw.rstrip("/.,:;")
            if candidate.exists():
                existing.append(raw.rstrip("/.,:;"))
    return "Present: " + ", ".join(existing) if existing else "No canonical reusable control found"


def failure_id(section: str, text: str) -> str:
    value = (section + " " + text).lower()
    mappings = [
        (("output", "absent"), "F001"),
        (("assigned", "disposition"), "F002"),
        (("overlap",), "F003"),
        (("shared state",), "F004"),
        (("zero", "facts"), "F005"),
        (("citation", "exact"), "F006"),
        (("publication date",), "F007"),
        (("aim",), "F008"),
        (("staff", "product"), "F009"),
        (("inference",), "F010"),
        (("current", "older"), "F011"),
        (("stale",), "F012"),
        (("unknown",), "F013"),
        (("expected", "checked"), "F014"),
        (("independent",), "F015"),
        (("every page",), "F016"),
        (("exact", "artifact"), "F017"),
    ]
    for words, fid in mappings:
        if all(word in value for word in words):
            return fid
    return ""


def build(status: str) -> int:
    blocks = [block for block in source_blocks(SOURCE.read_text(encoding="utf-8").splitlines(True)) if is_normative(block)]
    fields = [
        "requirement_id", "source_section", "source_text", "requirement_summary",
        "assurance_layer", "classification", "destination", "enforcement_type",
        "existing_implementation", "proposed_implementation", "failure_id",
        "preservation_status", "notes",
    ]
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index, block in enumerate(blocks, 1):
            klass = classification(block.section, block.text)
            dest = destination(block.section, block.text, klass)
            writer.writerow({
                "requirement_id": f"REQ-{index:04d}",
                "source_section": f"docs/legacy-prompt.md:{block.line} | {block.section}",
                "source_text": block.text,
                "requirement_summary": re.sub(r"[`*_]", "", block.text),
                "assurance_layer": layer(block.section, block.text),
                "classification": klass,
                "destination": dest,
                "enforcement_type": enforcement(klass, block.text),
                "existing_implementation": existing_implementation(block.text),
                "proposed_implementation": f"Preserve in {dest}",
                "failure_id": failure_id(block.section, block.text),
                "preservation_status": status,
                "notes": f"Parsed as {block.kind}; exact source retained.",
            })
    return len(blocks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=("planned", "preserved"), default="planned")
    args = parser.parse_args()
    count = build(args.status)
    print(f"Wrote {count} requirements to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
