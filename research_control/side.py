"""A side run: a bounded add-on to a finished run, kept away from its scheduler.

When a run has moved past fact drafting and new sources arrive (a market and
competitor search after the report was written), the side run takes just those
sources through the steps they need, in its own folder under
`tools/outputs/side/<label>/`, as a stand-alone mini deliverable:

1. `side new`     lays out the folder: the scope, the source list, links to the
                  chosen sources' captures, a copy of the fact store (so filing
                  continues its numbering and finds duplicates), the earlier
                  verdicts, and one extraction brief per batch of source text.
2. `side file`    merges the extraction parts, files the facts by script,
                  computes their deep links, writes their digests, and writes
                  the brief for one worker to update the section (and the
                  synthesis file it rests on).
3. `side verify`  prepares a sandbox verification of only the facts the
                  section newly cites, and merges its verdicts.
4. `side render`  builds the section on its own, with its citations and
                  sources, as a page and PDF.
5. `side merge`   brings the new facts, their links and verdicts, and the
                  updated section into the main run as recorded edits, so no
                  finished work reruns.

Every check runs with `side check --step STEP`. The main scheduler never sees
the side run: nothing in it is a task, and the merge records what it changes.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any

from research_control import citation_build, verification, verification_sandbox
from research_control.dispatch import _prompt
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text, load_json, load_jsonl, utc_now
from research_control.validators import american, extraction as extraction_rules
from research_control.validators.facts import load_fact_tables

SIDE_DIR = "tools/outputs/side"
EXTRACTED = "tools/lists/side-extracted.json"
BATCH_TOKENS = 70_000
FACT_ID = verification.FACT_ID
COPIED = ("00-scope.md", "01-sources/MANIFEST.csv", "tools/outputs/source-dates.jsonl", "tools/outputs/source-titles.json",
          "tools/lists/withdrawn-facts.json")
RUN_NOTES = re.compile(r"^## Notes for downstream phases\s*$(.*)", re.M | re.S)


def side_root(root: Path, label: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", label):
        raise ValueError("a side run's label is lowercase letters, digits, and hyphens")
    return root / SIDE_DIR / label


def _state(folder: Path) -> dict[str, Any]:
    path = folder / "side.json"
    return load_json(path) if path.is_file() else {}


def _save(folder: Path, state: dict[str, Any]) -> None:
    atomic_write_json(folder / "side.json", state)


def extracted_text(root: Path) -> set[str]:
    """Hashes of source text a side run has extracted: the main planner does not extract it again."""
    path = root / EXTRACTED
    return set(load_json(path)) if path.is_file() else set()


def held_sources(root: Path) -> list[str]:
    """Sources whose text the main run holds for a later pass (an extraction budget)."""
    path = root / "tools/lists/deferred-slices.json"
    if not path.is_file():
        return []
    from research_control.supplement import base_source

    return sorted({base_source(key) for key, value in load_json(path).get("slices", {}).items() if value.get("by") == "budget"})


def _run_notes(root: Path) -> str:
    match = RUN_NOTES.search((root / "00-scope.md").read_text(encoding="utf-8")) if (root / "00-scope.md").is_file() else None
    return match.group(1).strip() if match else ""


def _rules(root: Path, task_type: str, phase_prompt: str, cores: tuple[str, ...]) -> str:
    return "\n\n".join(_prompt(root, relative, task_type).strip() for relative in (*cores, phase_prompt))


def _section(markdown: str, heading: str) -> tuple[int, int, list[str]]:
    """The lines of the part under a `## ` heading (start, end, lines), up to the next `## `."""
    lines = markdown.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == heading.strip()), -1)
    if start < 0:
        raise ValueError(f"the report has no heading {heading!r}")
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return start, end, lines[start:end]


def new(root: Path, label: str, questions: list[str], source_ids: list[str] | None = None, section: str = "") -> dict[str, Any]:
    """Lay out a side run for these questions over these sources (default: the held ones)."""
    root = root.resolve()
    chosen = sorted(set(source_ids or held_sources(root)))
    if not chosen:
        raise ValueError("no sources: name them with --source-id, or hold some with an extraction budget first")
    folder, questions = _layout(root, label, questions)
    inputs = _attach(root, folder, chosen)
    batches = _pack(inputs)
    briefs = [_extraction_brief(root, folder, label, batch, questions) for batch in batches]
    state = {"label": label, "created": utc_now(), "questions": questions, "sources": chosen, "section": section,
             "batches": [batch["id"] for batch in batches], "captured": [], "steps": {"new": utc_now()}}
    _save(folder, state)
    return {"label": label, "folder": str(folder.relative_to(root)), "sources": len(chosen), "batches": len(batches),
            "start_workers": [{"read": brief, "model_level": "standard", "effort": "medium"} for brief in briefs]}


def search(root: Path, label: str, questions: list[str], section: str = "", firms: list[str] | None = None) -> dict[str, Any]:
    """Lay out a side run that starts from a bounded search: one worker lists the pages and
    repositories to read; `side capture` then captures them and writes the extraction briefs."""
    root = root.resolve()
    folder, questions = _layout(root, label, questions)
    brief = _search_brief(root, folder, label, questions, firms or [])
    state = {"label": label, "created": utc_now(), "questions": questions, "sources": [], "section": section,
             "batches": [], "captured": [], "firms": firms or [], "steps": {"search": utc_now()}}
    _save(folder, state)
    return {"label": label, "folder": str(folder.relative_to(root)),
            "start_workers": [{"read": brief, "model_level": "standard", "effort": "medium"}]}


def _layout(root: Path, label: str, questions: list[str]) -> tuple[Path, list[str]]:
    folder = side_root(root, label)
    if folder.exists():
        raise ValueError(f"side run {label} already exists at {folder.relative_to(root)}")
    questions = [question.upper() for question in questions]
    scope = (root / "00-scope.md").read_text(encoding="utf-8")
    for question in questions:
        if not re.search(rf"^\*\*{question}\.", scope, re.M):
            raise ValueError(f"{question} is not a numbered question in 00-scope.md")
    folder.mkdir(parents=True)
    # The rules the sandbox verifier reads, and the engine's checks, come from the main run.
    os.symlink(root / "prompts", folder / "prompts")
    for relative in COPIED:
        if (root / relative).is_file():
            (folder / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, folder / relative)
    for path in sorted((root / "02-facts").glob("*.md")):
        (folder / "02-facts").mkdir(exist_ok=True)
        shutil.copy2(path, folder / "02-facts" / path.name)
    main_facts = sorted(row["fact_id"] for row in load_fact_tables(sorted((root / "02-facts").glob("*.md"))) if row.get("fact_id"))
    atomic_write_text(folder / "main-facts.txt", "".join(f"{fact_id}\n" for fact_id in main_facts))
    # Earlier verdicts, so facts the section still cites from the main run count as judged.
    atomic_write_jsonl(folder / verification.VERDICTS, verification_sandbox.verdict_rows(root))
    return folder, questions


def _attach(root: Path, folder: Path, chosen: list[str]) -> list[dict[str, Any]]:
    """Link the main run's captures of these sources into the side run; return extraction inputs."""
    inputs: list[dict[str, Any]] = []
    for source_id in chosen:
        capture = root / "01-sources/captures" / source_id
        if not capture.is_dir():
            raise ValueError(f"{source_id} has no capture directory")
        link = folder / "01-sources/captures" / source_id
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(capture, link)
        canonical = root / "tools/extracts/canonical" / f"{source_id}.txt"
        if not canonical.is_file():
            raise ValueError(f"{source_id} has no extracted text at {canonical.relative_to(root)}; run `run` once after capture")
        text = canonical.read_text(encoding="utf-8", errors="replace")
        (folder / "tools/extracts/canonical").mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical, folder / "tools/extracts/canonical" / f"{source_id}.txt")
        inputs.append({
            "id": source_id, "source_id": source_id, "path": f"tools/extracts/canonical/{source_id}.txt",
            "source_paths": [str(path.relative_to(root)) for path in capture.glob("*") if path.is_file()],
            "estimated_tokens": max(1, len(text) // 4), "sha256": sha256(text.encode("utf-8")).hexdigest(),
        })
    return inputs


SEARCH_LIST = "search/sources.jsonl"
SEARCH_LIMIT = 40
TEXT_SUFFIXES = {".txt", ".md", ".json", ".jsonl", ".csv", ".xml"}


def _search_brief(root: Path, folder: Path, label: str, questions: list[str], firms: list[str]) -> str:
    scope_text = (root / "00-scope.md").read_text(encoding="utf-8")
    asked = "\n\n".join(match.group(0) for question in questions
                        for match in [re.search(rf"^\*\*{question}\..*?(?=^\*\*Q\d+\.|^#|\Z)", scope_text, re.M | re.S)] if match)
    leads = root / "tools/lists/competitor-leads.md"
    known = sorted({row.get("url", "") for row in csv.DictReader((root / "01-sources/MANIFEST.csv").open(encoding="utf-8", newline=""))})
    lines = [
        f"# Side run `{label}`: list the pages and repositories to read", "",
        "This is a side run: a bounded search for a finished research run. You hold no scheduler task; do not run "
        "`research_control run`, `work`, or `discovery` commands, and do not capture anything yourself. Your only "
        f"output is `{folder.relative_to(root)}/{SEARCH_LIST}`: one JSON object per line with `url`, `grade` "
        "(P: the firm's own words; S: a named third party's first-hand record; T: press or analysts), `title`, "
        "`publisher`, `why` (one line: what the page gives the questions), and `question` (Q7). "
        f"List at most {SEARCH_LIMIT} URLs, best first.", "",
        "## What to find", "",
        "For each direct competitor named below, the pages the market and competitor instructions ask for and "
        "the first pass did not reach: its services or product pages, case studies and named customers, pricing or "
        "rate signals, careers pages (roles, locations, how it staffs work), documentation, and its public GitHub: "
        "the organization(s) and its people's work repositories, found as the instructions say (plain web searches "
        "first, reading the result snippets), plus any deleted repository worth a look. Give repository URLs "
        "(`https://github.com/ORG/REPO`), not organization pages. Skip pages already in the source list (below) "
        "and anything behind a login.", "",
        "## The direct competitors", "", *([f"- {firm}" for firm in firms] or ["(from the leads file and the questions)"]), "",
        "## The research questions", "", asked or ", ".join(questions), "",
    ]
    if leads.is_file():
        lines += ["## Leads already recorded", "", leads.read_text(encoding="utf-8").rstrip(), ""]
    lines += ["## Sources already in the run (do not list these)", "", *(f"- {url}" for url in known if url), "",
              "---", "", "## The search instructions", "",
              _rules(root, "source_discovery", "prompts/phases/discovery.md", ("prompts/core/runtime.md", "prompts/core/evidence.md")), "",
              "---", "", "## Finish", "",
              "Write in American English in `title`, `publisher`, and `why`; a page's own title keeps its spelling.", "",
              f"1. Check with `python3 -m research_control side check --label {label} --step search` from the main run's "
              "folder and fix what it reports until its status is clean.",
              "2. Report in under 80 words, in plain English: how many pages and repositories per competitor, and what "
              "could not be found.", ""]
    path = folder / "search" / "brief.md"
    atomic_write_text(path, "\n".join(lines) + "\n")
    return str(path)


def _check_search(root: Path, folder: Path) -> list[str]:
    from research_control.discovery import canonicalize_url

    path = folder / SEARCH_LIST
    if not path.is_file():
        return [f"{SEARCH_LIST} is not written yet"]
    known = {canonicalize_url(row.get("url", "")) for row in csv.DictReader((root / "01-sources/MANIFEST.csv").open(encoding="utf-8", newline="")) if row.get("url")}
    problems: list[str] = []
    seen: set[str] = set()
    rows = load_jsonl(path)
    if len(rows) > SEARCH_LIMIT:
        problems.append(f"{len(rows)} URLs listed; at most {SEARCH_LIMIT}")
    for index, row in enumerate(rows, 1):
        url = str(row.get("url", ""))
        try:
            canonical = canonicalize_url(url)
        except ValueError as error:
            problems.append(f"row {index}: {error}")
            continue
        if not url.startswith(("http://", "https://")):
            problems.append(f"row {index}: url must be absolute http(s)")
        if canonical in seen:
            problems.append(f"row {index}: {url} is listed twice")
        seen.add(canonical)
        if canonical in known:
            problems.append(f"row {index}: {url} is already in the run's source list")
        if row.get("grade") not in {"P", "S", "T"}:
            problems.append(f"row {index}: grade must be P, S, or T")
        if not str(row.get("why", "")).strip():
            problems.append(f"row {index}: say why the page matters")
        for word, advice in american.findings(" ".join(str(row.get(key, "")) for key in ("publisher", "why"))):
            problems.append(f'row {index}: American English: "{word}" (use {advice})')
    return problems


def capture(root: Path, label: str, workers: int = 4) -> dict[str, Any]:
    """Capture every listed page and repository into the side run (repositories shallowly),
    date them, and write the extraction briefs."""
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlparse

    from research_control import dating
    from research_control.capture import auto_capture_source
    from research_control.discovery import canonicalize_url
    from research_control.runtime import stable_source_id

    root = root.resolve()
    folder = side_root(root, label)
    state = _state(folder)
    problems = _check_search(root, folder)
    if problems:
        raise ValueError("the search list is not clean: " + "; ".join(problems[:10]))
    rows = load_jsonl(folder / SEARCH_LIST)
    jobs = []
    for row in rows:
        canonical = canonicalize_url(str(row["url"]))
        source_id = stable_source_id(canonical)
        if source_id in state.get("captured", []):
            continue
        github = (urlparse(canonical).hostname or "").casefold().removeprefix("www.") == "github.com"
        jobs.append((source_id, canonical, str(row.get("grade", "T")), github))

    def run(job: tuple[str, str, str, bool]) -> dict[str, Any]:
        source_id, url, grade, github = job
        return auto_capture_source(folder, url=url, source_id=source_id, grade=grade, shallow_repositories=github)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        receipts = list(pool.map(run, jobs))
    manifest_path = folder / "01-sources/MANIFEST.csv"
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
    captured, blocked = [], []
    as_of = dating.research_date(root)
    inputs: list[dict[str, Any]] = []
    for receipt in receipts:
        source_id = receipt["source_id"]
        if receipt.get("status") != "captured":
            blocked.append({"source_id": source_id, "url": receipt.get("url") or receipt.get("source", {}).get("url", ""),
                            "reason": str(receipt.get("reason", ""))[:300]})
            continue
        source = receipt["source"]
        with manifest_path.open("a", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore").writerow({key: source.get(key, "") for key in columns})
        paths = [value.strip() for value in str(source.get("local file", "")).split(";") if value.strip()]
        sections = []
        for relative in paths:
            path = folder / relative
            if path.suffix.casefold() in TEXT_SUFFIXES and path.is_file():
                sections.append(f"--- SOURCE FILE: {relative} ---\n{path.read_text(encoding='utf-8', errors='replace').rstrip()}\n")
        text = "\n".join(sections)
        canonical_path = folder / "tools/extracts/canonical" / f"{source_id}.txt"
        atomic_write_text(canonical_path, text)
        dated = dating.date_source(folder, receipt, as_of)
        dated["posted_date"] = dated.get("content_date", "")
        with (folder / "tools/outputs/source-dates.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dated, ensure_ascii=False) + "\n")
        with (folder / "tools/outputs/capture-dispositions.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"assignment_id": f"capture.source.{source_id.casefold()}", "disposition": "completed",
                                     "evidence_paths": paths, "input_id": source_id, "output_ids": [source_id],
                                     "reason": "captured with canonical text (side run)"}, ensure_ascii=False) + "\n")
        inputs.append({"id": source_id, "source_id": source_id, "path": f"tools/extracts/canonical/{source_id}.txt",
                       "source_paths": paths, "estimated_tokens": max(1, len(text) // 4),
                       "sha256": sha256(text.encode("utf-8")).hexdigest()})
        captured.append(source_id)
    atomic_write_jsonl(folder / "search/blocked.jsonl", blocked)
    batches = _pack(inputs) if inputs else []
    briefs = [_extraction_brief(root, folder, label, batch, state["questions"]) for batch in batches]
    state["captured"] = sorted(set(state.get("captured", [])) | set(captured))
    state["sources"] = sorted(set(state.get("sources", [])) | set(captured))
    state["batches"] = state.get("batches", []) + [batch["id"] for batch in batches]
    state["steps"]["capture"] = utc_now()
    _save(folder, state)
    return {"label": label, "captured": len(captured), "blocked": blocked, "batches": len(batches),
            "start_workers": [{"read": brief, "model_level": "standard", "effort": "medium"} for brief in briefs]}


def _pack(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for item in sorted(inputs, key=lambda value: value["id"]):
        if current and size + int(item["estimated_tokens"]) > BATCH_TOKENS:
            batches.append({"inputs": current})
            current, size = [], 0
        current.append(item)
        size += int(item["estimated_tokens"])
    if current:
        batches.append({"inputs": current})
    for batch in batches:
        batch["id"] = sha256("\n".join(item["id"] for item in batch["inputs"]).encode("utf-8")).hexdigest()[:12]
    return batches


def _extraction_brief(root: Path, folder: Path, label: str, batch: dict[str, Any], questions: list[str]) -> str:
    batch_id = batch["id"]
    parts = f"tools/outputs/worker-parts/extraction/{batch_id}"
    task = {
        "task_id": f"side.{label}.extract.{batch_id}", "inputs": batch["inputs"],
        "metadata": {"candidate_id_prefix": f"CAND-{batch_id.upper()}-", "candidate_part": f"{parts}.candidates.jsonl",
                     "disposition_part": f"{parts}.dispositions.jsonl"},
    }
    atomic_write_json(folder / "extract" / f"{batch_id}.json", task)
    material = []
    for item in batch["inputs"]:
        material += [f"=== FILE: {item['path']} ({item['estimated_tokens']} tokens; source {item['source_id']}) ===", "",
                     (folder / item["path"]).read_text(encoding="utf-8", errors="replace").rstrip(), ""]
    scope_lines = (root / "00-scope.md").read_text(encoding="utf-8")
    asked = "\n\n".join(match.group(0) for question in questions
                        for match in [re.search(rf"^\*\*{question}\..*?(?=^\*\*Q\d+\.|^#|\Z)", scope_lines, re.M | re.S)] if match)
    notes = _run_notes(root)
    lines = [
        f"# Side run `{label}`: draft facts from {len(batch['inputs'])} sources (batch {batch_id})", "",
        "This is a side run: a bounded add-on to a finished research run. You hold no scheduler task; do not run "
        "`research_control run`, `work claim`, `work succeed`, or `discovery` commands. Work from the side run's "
        f"folder, `{folder.relative_to(root)}/`, and write only the two output files named below and your own "
        "scratch files.", "",
        "## Start", "",
        f"1. Everything you need is in this file: the source text, then the instructions.",
        "2. The research questions this side run serves are below; extract what bears on them, and nothing outside them.", "",
        "## The research questions", "", asked or ", ".join(questions), "",
        "## The source text", "", *material,
        "---", "", "## The task's instructions", "",
        _rules(root, "extraction", "prompts/phases/extraction.md", ("prompts/core/runtime.md", "prompts/core/evidence.md")), "",
        "## This batch", "",
        f"- Candidate IDs start with `{task['metadata']['candidate_id_prefix']}` followed by a zero-padded sequence.",
        f"- Inputs (one disposition each, by input ID): {', '.join(item['id'] for item in batch['inputs'])}.",
        f"- Each disposition row has `assignment_id` (`{task['task_id']}`), `input_id`, `source_id`, `disposition`, "
        "`reason`, `evidence_paths` (a list), and `output_ids` (the candidate IDs filed from it).",
        f"- Write candidates to `{folder.relative_to(root)}/{task['metadata']['candidate_part']}` and dispositions to "
        f"`{folder.relative_to(root)}/{task['metadata']['disposition_part']}`.", "",
    ]
    if notes:
        lines += ["## Run notes", "", notes, ""]
    lines += [
        "---", "", "## Finish", "",
        "Write everything you author in American English (\"program\", not \"programme\"); quotes keep the source's spelling.", "",
        f"3. Check with `python3 -m research_control side check --label {label} --step extract` from the main run's "
        "folder and fix what it reports until its status is clean.",
        "4. Report in under 60 words, in plain English: counts of facts drafted and sources with none, and anything "
        "the orchestrator must act on.", "",
    ]
    path = folder / "extract" / f"{batch_id}.brief.md"
    atomic_write_text(path, "\n".join(lines) + "\n")
    return str(path)


def check(root: Path, label: str, step: str) -> dict[str, Any]:
    root = root.resolve()
    folder = side_root(root, label)
    state = _state(folder)
    problems: list[str] = []
    if step == "extract":
        for batch_id in state.get("batches", []):
            task = load_json(folder / "extract" / f"{batch_id}.json")
            if not (folder / task["metadata"]["candidate_part"]).is_file() or not (folder / task["metadata"]["disposition_part"]).is_file():
                problems.append(f"batch {batch_id}: its candidate or disposition part is not written yet")
                continue
            problems += [f"batch {batch_id}: {item}" for item in extraction_rules.validate_part(folder, task)]
            for relative in (task["metadata"]["candidate_part"], task["metadata"]["disposition_part"]):
                problems += [f"batch {batch_id}: American English: {item}" for item in american.check_file(folder / relative)]
    elif step == "write":
        problems += _check_writing(root, folder, state)
    elif step == "verify":
        problems += verification_sandbox.check(folder, "side")
    elif step == "search":
        problems += _check_search(root, folder)
    else:
        raise ValueError("step is search, extract, write, or verify")
    return {"label": label, "step": step, "problems": problems[:60], "status": "clean" if not problems else "problems"}


def _check_writing(root: Path, folder: Path, state: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    facts = {row["fact_id"] for row in load_fact_tables(sorted((folder / "02-facts").glob("*.md"))) if row.get("fact_id")}
    from research_control.validators.facts import withdrawn_facts

    withdrawn = set(withdrawn_facts(folder))
    for name in ("company-brief.md", "competitors.md"):
        path = folder / "05-synthesis" / name
        if not path.is_file():
            problems.append(f"05-synthesis/{name} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        for fact_id in sorted(set(FACT_ID.findall(text))):
            if fact_id not in facts and re.match(r"^[A-Z]{2,4}-\d{3}[a-z]?$", fact_id):
                problems.append(f"05-synthesis/{name} cites {fact_id}, which is not in the fact store")
            elif fact_id in withdrawn:
                problems.append(f"05-synthesis/{name} cites {fact_id}, which was withdrawn")
        problems += [f"05-synthesis/{name} American English: {item}" for item in american.check_file(path)]
    brief = folder / "05-synthesis/company-brief.md"
    if brief.is_file():
        lines = brief.read_text(encoding="utf-8").splitlines()
        headings = [line for line in lines if line.startswith("## ")]
        expected = state.get("section") or ""
        if not headings or (expected and headings[0].strip() != expected.strip()):
            problems.append(f"the section must begin with the heading {expected!r} and keep it")
        if len(headings) != 2 or not citation_build.SOURCES_HEADING.match(headings[-1]):
            problems.append("the section file holds one part heading, its subheadings, and a closing `## Sources` heading")
        problems += citation_build.build(folder)["problems"]
    return problems


def file(root: Path, label: str) -> dict[str, Any]:
    """Merge the extraction parts, file the facts, link and digest them, and write the writing brief."""
    from research_control import filing, reducers
    from research_control.deeplinks import write_fact_links
    from research_control.supplement import write_claim_digests

    root = root.resolve()
    folder = side_root(root, label)
    state = _state(folder)
    problems = check(root, label, "extract")["problems"]
    if problems:
        raise ValueError("the extraction parts are not clean: " + "; ".join(problems[:10]))
    if not (folder / "new-facts.txt").is_file():
        # Number from the main run as it is now (another side run may have merged since this
        # one was laid out), and know every verdict it holds.
        _refresh_fact_store(root, folder)
    _normalize_parts(folder, state)
    merged = reducers.reduce_extraction_parts(folder)
    filed = filing.file_candidates(folder, worker=f"side run {label}")
    main_facts = set((folder / "main-facts.txt").read_text(encoding="utf-8").split())
    new_facts = sorted(row["fact_id"] for row in load_fact_tables(sorted((folder / "02-facts").glob("*.md")))
                       if row.get("fact_id") and row["fact_id"] not in main_facts)
    atomic_write_text(folder / "new-facts.txt", "".join(f"{fact_id}\n" for fact_id in new_facts))
    links = write_fact_links(folder, fact_ids=new_facts)
    digests = write_claim_digests(folder, "tools/digests", fact_ids=new_facts)
    brief = _writing_brief(root, folder, label, state, new_facts)
    state["steps"]["file"] = utc_now()
    state["new_facts"] = len(new_facts)
    _save(folder, state)
    return {"label": label, "candidates": merged["candidates"], "filed": filed.get("filed", 0), "new_facts": len(new_facts),
            "links_located": links.get("located", links), "digests": digests,
            "start_workers": [{"read": brief, "model_level": "strong", "effort": "high"}]}


def _refresh_fact_store(root: Path, folder: Path) -> None:
    for path in sorted((folder / "02-facts").glob("*.md")):
        path.unlink()
    for path in sorted((root / "02-facts").glob("*.md")):
        shutil.copy2(path, folder / "02-facts" / path.name)
    main_facts = sorted(row["fact_id"] for row in load_fact_tables(sorted((root / "02-facts").glob("*.md"))) if row.get("fact_id"))
    atomic_write_text(folder / "main-facts.txt", "".join(f"{fact_id}\n" for fact_id in main_facts))
    atomic_write_jsonl(folder / verification.VERDICTS, verification_sandbox.verdict_rows(root))


def _normalize_parts(folder: Path, state: dict[str, Any]) -> None:
    """Fill in the bookkeeping fields of a batch's disposition rows a worker left out (the
    batch's assignment ID, the list form of evidence paths): mechanical, meaning unchanged."""
    for batch_id in state.get("batches", []):
        task = load_json(folder / "extract" / f"{batch_id}.json")
        path = folder / task["metadata"]["disposition_part"]
        if not path.is_file():
            continue
        rows = load_jsonl(path)
        changed = False
        for row in rows:
            if not row.get("assignment_id"):
                row["assignment_id"] = task["task_id"]
                changed = True
            if "evidence_paths" not in row and row.get("evidence_path"):
                row["evidence_paths"] = [row.pop("evidence_path")]
                changed = True
            if not row.get("source_id"):
                row["source_id"] = str(row.get("input_id", "")).split(":", 1)[0]
                changed = True
        if changed:
            atomic_write_jsonl(path, rows)


def _writing_brief(root: Path, folder: Path, label: str, state: dict[str, Any], new_facts: list[str]) -> str:
    section = state.get("section") or ""
    main_brief = (root / "05-synthesis/company-brief.md").read_text(encoding="utf-8")
    if section:
        _start, _end, lines = _section(main_brief, section)
    else:
        lines = ["## Section", ""]
    (folder / "05-synthesis").mkdir(exist_ok=True)
    atomic_write_text(folder / "05-synthesis/company-brief.md", "\n".join(lines).rstrip() + "\n\n## Sources\n")
    if (root / "05-synthesis/competitors.md").is_file():
        shutil.copy2(root / "05-synthesis/competitors.md", folder / "05-synthesis/competitors.md")
    digests = sorted((folder / "tools/digests").glob("*.md"))
    material = []
    for path in digests:
        material += [f"=== FILE: tools/digests/{path.name} ===", "", path.read_text(encoding="utf-8").rstrip(), ""]
    for name in ("competitors.md", "company-brief.md"):
        material += [f"=== FILE: 05-synthesis/{name} (the current text; edit this file) ===", "",
                     (folder / "05-synthesis" / name).read_text(encoding="utf-8").rstrip(), ""]
    leads = root / "tools/lists/competitor-leads.md"
    if leads.is_file():
        material += ["=== FILE: tools/lists/competitor-leads.md (leads recorded by the orchestrator) ===", "",
                     leads.read_text(encoding="utf-8").rstrip(), ""]
    notes = _run_notes(root)
    lines_out = [
        f"# Side run `{label}`: update the section from {len(new_facts)} new facts", "",
        "This is a side run: a bounded add-on to a finished research run. You hold no scheduler task; do not run "
        f"`research_control run` or `work` commands. Work in `{folder.relative_to(root)}/` and edit only "
        "`05-synthesis/competitors.md` and `05-synthesis/company-brief.md` there (the main run's files are untouched "
        "until the orchestrator merges your work).", "",
        "## Start", "",
        "1. The new facts are digested below, one line each; open a fact's full row (quote, location, notes) by "
        "searching `02-facts/` in the side run's folder for its ID. Facts the section already cites stand.",
        "2. Update `05-synthesis/competitors.md` (the synthesis file the section rests on) and then "
        "`05-synthesis/company-brief.md`, which holds only the report's section for this side run, under its part "
        "heading, and ends with an empty `## Sources` heading. Keep that heading structure.",
        "3. Cite with fact IDs in square brackets beside the exact words they support, in prose and in table cells. "
        "Do not number citations or write source notes: the build does that.", "",
        "## The material", "", *material,
        "---", "", "## The task's instructions", "",
        _rules(root, "synthesis", "prompts/phases/synthesis.md",
               ("prompts/core/runtime.md", "prompts/core/evidence.md", "prompts/core/writing.md")), "",
        "The section keeps the report's rules: tight copy with no filler or tangents, each number with its date and "
        "basis, changes shown with dates, direct competitors separated from adjacent firms with the reason each is in "
        "the set, and the market (category, size and growth where sourced, buyer spending, direction) covered. Where "
        "the new facts correct or date something the section said, change it. Where evidence is thin, say so.", "",
    ]
    if notes:
        lines_out += ["## Run notes", "", notes, ""]
    lines_out += [
        "---", "", "## Finish", "",
        "Write in American English (\"program\", not \"programme\"); quotes, titles, and names keep the source's spelling.", "",
        f"4. Check with `python3 -m research_control side check --label {label} --step write` from the main run's "
        "folder and fix what it reports until its status is clean.",
        "5. Report in under 80 words, in plain English: what changed in the section, and anything the orchestrator "
        "must act on.", "",
    ]
    path = folder / "write" / "brief.md"
    atomic_write_text(path, "\n".join(lines_out) + "\n")
    return str(path)


def verify(root: Path, label: str, merge: bool = False) -> dict[str, Any]:
    root = root.resolve()
    folder = side_root(root, label)
    state = _state(folder)
    if merge:
        result = verification_sandbox.merge(folder, "side")
        state["steps"]["verify"] = utc_now()
        _save(folder, state)
        corrected = [row for row in load_jsonl(folder / verification.ADDED) if row.get("verdict") == "corrected"]
        if corrected:
            # The section was written before these facts were judged: the writer applies the
            # corrections to its wording before the merge, as the main run's correction step does.
            result["corrections"] = len(corrected)
            result["start_workers"] = [{"read": _corrections_brief(root, folder, label, corrected), "model_level": "strong", "effort": "high"}]
        return result
    prepared = verification_sandbox.prepare(folder, "side")
    if prepared.get("facts"):
        prepared["start_workers"] = [{"read": str(folder / prepared["brief"]), "model_level": "frontier", "effort": "high"}]
        prepared["check"] = f"python3 -m research_control side check --label {label} --step verify"
    return prepared


def _corrections_brief(root: Path, folder: Path, label: str, corrected: list[dict[str, Any]]) -> str:
    rows = []
    for row in corrected:
        rows.append(f"- {row['fact_id']}: {str(row.get('reason', '')).strip()}"
                    + (f"\n  Corrected claim: {row['corrected_claim']}" if row.get("corrected_claim") else "")
                    + (f"\n  Corrected receipt: {row['corrected_receipt']}" if row.get("corrected_receipt") else ""))
    lines = [
        f"# Side run `{label}`: apply {len(corrected)} verification corrections to the section", "",
        "This is a side run: a bounded add-on to a finished research run. You hold no scheduler task; do not run "
        f"`research_control run` or `work` commands. Work in `{folder.relative_to(root)}/` and edit only "
        "`05-synthesis/company-brief.md` and `05-synthesis/competitors.md` there.", "",
        "## What to do", "",
        "An independent verifier judged the facts the section cites. The facts below were corrected: the claim said "
        "more than the quote supports, or the wording or date was off. Where the section (or the synthesis file) "
        "rests on one of them, change its wording to what the corrected claim supports, keeping the fact ID beside "
        "the words. Where the correction removes the basis for a sentence, cut the sentence. Change nothing else.", "",
        "## The corrections", "", *rows, "",
        "## The files", "",
        *(f"=== FILE: 05-synthesis/{name} ===\n\n" + (folder / "05-synthesis" / name).read_text(encoding="utf-8").rstrip() + "\n"
          for name in ("company-brief.md", "competitors.md")),
        "---", "", "## Finish", "",
        "Write in American English; quotes keep the source's spelling.", "",
        f"1. Check with `python3 -m research_control side check --label {label} --step write` from the main run's "
        "folder and fix what it reports until its status is clean.",
        "2. Report in under 60 words, in plain English: how many sentences changed or were cut.", "",
    ]
    path = folder / "write" / "corrections-brief.md"
    atomic_write_text(path, "\n".join(lines) + "\n")
    return str(path)


def render(root: Path, label: str) -> dict[str, Any]:
    """The section on its own, with linked citations and its sources, as a page and (when a renderer is there) a PDF."""
    from research_control import publication

    root = root.resolve()
    folder = side_root(root, label)
    built = citation_build.build(folder)
    if built["problems"]:
        raise ValueError("the section is not clean: " + "; ".join(built["problems"][:10]))
    try:
        result = publication.render(folder)
        outputs = {"html": "07-final-report/company-brief.html", "pdf": "07-final-report/company-brief.pdf", "pages": result.get("total_pages")}
    except Exception as error:  # no PDF renderer: the page alone is the deliverable
        markdown = (folder / "05-synthesis/company-brief.md").read_text(encoding="utf-8")
        page = publication.markdown_to_html(markdown, "Company brief: section", publication.DEFAULT_CSS, built["map"])
        atomic_write_text(folder / "07-final-report/company-brief.html", page)
        outputs = {"html": "07-final-report/company-brief.html", "pdf": None, "note": f"PDF not built: {error}"}
    state = _state(folder)
    state["steps"]["render"] = utc_now()
    _save(folder, state)
    return {"label": label, "folder": str(folder.relative_to(root)), **outputs,
            "citations": built["citations"], "sources": built["sources"]}


def merge(root: Path, label: str, worker_id: str = "runtime") -> dict[str, Any]:
    """Bring the side run's facts, links, verdicts, and section into the main run as recorded edits."""
    from research_control.orchestration import append_history
    from research_control.runtime import RuntimeStore

    root = root.resolve()
    folder = side_root(root, label)
    state = _state(folder)
    problems = _check_writing(root, folder, state)
    if problems:
        raise ValueError("the section is not clean: " + "; ".join(problems[:10]))
    unverified = verification_sandbox.unverified(folder)
    if unverified:
        raise ValueError(f"{len(unverified)} cited facts have no verdict yet (run `side verify`): {', '.join(unverified[:8])}")
    new_facts = set((folder / "new-facts.txt").read_text(encoding="utf-8").split())
    touched: list[str] = []
    captured = state.get("captured", [])
    if captured:
        _merge_sources(root, folder, captured, label, touched)
    # 1. Fact rows, their deep links, and the candidates and dispositions behind them.
    for path in sorted((folder / "02-facts").glob("*.md")):
        target = root / "02-facts" / path.name
        rows = [line for line in path.read_text(encoding="utf-8").splitlines()
                if (match := re.match(r"^\|\s*([A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?)\s*\|", line)) and match.group(1) in new_facts]
        if not rows:
            continue
        if target.is_file():
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(rows) + "\n")
        else:
            shutil.copy2(path, target)
        touched.append(f"02-facts/{path.name}")
    _append(root, folder, "tools/outputs/fact-links.jsonl", lambda row: row.get("fact_id") in new_facts, touched)
    _append(root, folder, "tools/candidates/all.jsonl", lambda row: True, touched)
    _append(root, folder, "tools/outputs/filing-dispositions.jsonl", lambda row: True, touched)
    _append(root, folder, "tools/outputs/extraction-dispositions.jsonl", lambda row: True, touched)
    parts_dir = root / "tools/outputs/worker-parts/extraction"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted((folder / "tools/outputs/worker-parts/extraction").glob("*.jsonl")):
        shutil.copy2(path, parts_dir / path.name)
    extracted = load_json(root / EXTRACTED) if (root / EXTRACTED).is_file() else {}
    for batch_id in state.get("batches", []):
        for item in load_json(folder / "extract" / f"{batch_id}.json")["inputs"]:
            extracted[item["sha256"]] = {"source_id": item["source_id"], "side": label, "at": utc_now()}
    atomic_write_json(root / EXTRACTED, extracted)
    # 2. Verdicts for the facts the section newly cites.
    added = load_jsonl(folder / verification.ADDED) if (folder / verification.ADDED).is_file() else []
    if added:
        main_added = load_jsonl(root / verification.ADDED) if (root / verification.ADDED).is_file() else []
        seen = {str(row.get("fact_id")) for row in main_added}
        main_added += [row for row in added if str(row.get("fact_id")) not in seen]
        atomic_write_jsonl(root / verification.ADDED, main_added)
        verification.write_cited_rows(root, main_added, verification_sandbox.ADDED_ROWS)
        touched += [verification.ADDED, verification_sandbox.ADDED_ROWS]
    # 3. The synthesis file and the report's section.
    if (folder / "05-synthesis/competitors.md").is_file():
        shutil.copy2(folder / "05-synthesis/competitors.md", root / "05-synthesis/competitors.md")
        touched.append("05-synthesis/competitors.md")
    section = state.get("section") or ""
    if section:
        main_path = root / "05-synthesis/company-brief.md"
        main_text = main_path.read_text(encoding="utf-8")
        start, end, _old = _section(main_text, section)
        new_lines = (folder / "05-synthesis/company-brief.md").read_text(encoding="utf-8").splitlines()
        cut = next((index for index, line in enumerate(new_lines) if citation_build.SOURCES_HEADING.match(line)), len(new_lines))
        body = new_lines[:cut]
        while body and not body[-1].strip():
            body.pop()
        lines = main_text.splitlines()
        atomic_write_text(main_path, "\n".join(lines[:start] + body + [""] + lines[end:]).rstrip() + "\n")
        touched.append("05-synthesis/company-brief.md")
    built = citation_build.build(root)
    touched += [citation_build.CITATION_MAP, citation_build.EXHIBIT_MAP]
    with RuntimeStore(root) as store:
        recorded = store.record_edit(sorted(set(touched)), "final", f"side run {label} merged: {len(new_facts)} new facts; section updated", worker_id)
    append_history(root, "side-run-merged", f"{label}: {len(new_facts)} facts, {len(added)} verdicts, section {section or '(none)'}")
    state["steps"]["merge"] = utc_now()
    _save(folder, state)
    return {"label": label, "new_facts": len(new_facts), "verdicts_added": len(added), "touched": sorted(set(touched)),
            "citations": built["citations"], "citation_problems": built["problems"][:10], "recorded": recorded}


def _merge_sources(root: Path, folder: Path, captured: list[str], label: str, touched: list[str]) -> None:
    """Sources the side run captured itself: their captures, receipts, source rows, dates, and
    dispositions join the main run, and the store knows them, without reopening any channel."""
    from research_control.discovery import host_key
    from research_control.runtime import RuntimeStore

    wanted = set(captured)
    for source_id in captured:
        source_dir = folder / "01-sources/captures" / source_id
        target = root / "01-sources/captures" / source_id
        if source_dir.is_dir() and not source_dir.is_symlink() and not target.exists():
            shutil.copytree(source_dir, target)
        receipt = folder / "tools/outputs/worker-parts/capture" / f"{source_id}.json"
        if receipt.is_file():
            (root / "tools/outputs/worker-parts/capture").mkdir(parents=True, exist_ok=True)
            shutil.copy2(receipt, root / "tools/outputs/worker-parts/capture" / receipt.name)
    with (folder / "01-sources/MANIFEST.csv").open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("id") in wanted]
    if rows:
        main_manifest = root / "01-sources/MANIFEST.csv"
        with main_manifest.open(encoding="utf-8", newline="") as handle:
            columns = csv.DictReader(handle).fieldnames or []
            known = {row["id"] for row in csv.DictReader(main_manifest.open(encoding="utf-8", newline=""))}
        with main_manifest.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            for row in rows:
                if row["id"] not in known:
                    writer.writerow(row)
        touched.append("01-sources/MANIFEST.csv")
    _append(root, folder, "tools/outputs/source-dates.jsonl", lambda row: row.get("source_id") in wanted, touched)
    _append(root, folder, "tools/outputs/capture-dispositions.jsonl", lambda row: row.get("input_id") in wanted, touched)
    with RuntimeStore(root) as store:
        for row in rows:
            source, _created = store.add_source(
                canonical_url=row["url"], original_url=row["url"], host_key=host_key(row["url"]),
                channel="market_competitors", source_kind="web_page", relevance="candidate",
                discovered_from=f"side run {label}", metadata={"side_run": label}, reopen_channel=False,
            )
            paths = [value.strip() for value in str(row.get("local file", "")).split(";") if value.strip()]
            store.update_source(source["source_id"], status="captured", local_paths=paths,
                                metadata={**source.get("metadata", {}), "side_run": label})


def _append(root: Path, folder: Path, relative: str, keep: Any, touched: list[str]) -> None:
    source = folder / relative
    if not source.is_file():
        return
    rows = [row for row in load_jsonl(source) if keep(row)]
    if not rows:
        return
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    touched.append(relative)


def status(root: Path, label: str) -> dict[str, Any]:
    folder = side_root(root.resolve(), label)
    state = _state(folder)
    return {"label": label, "steps": state.get("steps", {}), "sources": len(state.get("sources", [])),
            "batches": state.get("batches", []), "new_facts": state.get("new_facts"), "section": state.get("section")}
