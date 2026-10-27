"""File extraction candidates into the fact store without a model.

Filing is bookkeeping: every candidate gets one terminal disposition, repeats
of a filed fact are recorded as duplicates of it, and every other candidate is
appended to its question's fact table under a new, stable ID. A quote that is
not in its captured source is rejected rather than filed. Existing rows and
their IDs never change. A small agent task then spot-checks a sample of the
merges and filed rows (`filing-spot-check`).
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, atomic_write_text, load_json, load_jsonl, utc_now
from research_control.validators.facts import load_fact_tables
from research_control.validators.quotes import normalize as normalize_text

CANDIDATES = "tools/candidates/all.jsonl"
DISPOSITIONS = "tools/outputs/filing-dispositions.jsonl"
SCRIPT_AUDIT = "06-checks/script-audits.md"
SPOT_SAMPLE = "tools/outputs/filing-spot-sample.json"
SPOT_SAMPLE_SIZE = 20
COLUMNS = (
    "Fact ID", "Claim", "Verbatim quote", "Source ID", "Location", "Source date", "Grade", "Topics", "About",
    "Said by", "Verdict", "Candidate", "Notes", "Conflict group", "Cross-source repeats",
)
SCOPE_QUESTION = re.compile(r"^\*\*Q(\d+)\.\s+(.+?)\*\*", re.M)
CANDIDATE_ID = re.compile(r"CAND-[A-Z0-9]+-\d+")
QUESTION_IN_TOPIC = re.compile(r"\bq\s?0*(\d+)\b", re.I)
RISK_TERMS = ("can", "will", "plan", "aim", "up to", "some", "early", "beta", "coming soon")
STOP_WORDS = {"and", "the", "of", "for", "who", "how", "what", "its", "has", "with", "from", "that", "this", "over", "time"}


def scope_questions(root: Path) -> dict[int, str]:
    """The numbered research questions and their titles, from `00-scope.md`."""
    path = root / "00-scope.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {int(number): title.strip().rstrip(".") for number, title in SCOPE_QUESTION.findall(text)}


def _words(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z]+", text.casefold()) if word not in STOP_WORDS and len(word) > 2]


def _slug(title: str) -> str:
    return "-".join(_words(title)[:2]) or "topic"


def _tables(root: Path, questions: dict[int, str]) -> dict[int, tuple[Path, str]]:
    """Each question's fact table and ID prefix; existing tables keep theirs."""
    tables: dict[int, tuple[Path, str]] = {}
    used: set[str] = set()
    for path in sorted((root / "02-facts").glob("q*.md")):
        match = re.match(r"q0*(\d+)-", path.name)
        rows = load_fact_tables([path])
        prefix = rows[0]["fact_id"].rsplit("-", 1)[0] if rows else ""
        if match and prefix:
            tables[int(match.group(1))] = (path, prefix)
            used.add(prefix)
    for number, title in sorted(questions.items()):
        if number in tables:
            continue
        words = _words(title) or ["topic"]
        options = [words[0][:3].upper(), "".join(word[0] for word in words[:3]).upper().ljust(3, "X")]
        prefix = next((option for option in options if option not in used), f"{words[0][:2].upper()}{number}")
        used.add(prefix)
        tables[number] = (root / "02-facts" / f"q{number:02d}-{_slug(title)}.md", prefix)
    return tables


def _questions_for(candidate: dict[str, Any], questions: dict[int, str]) -> list[int]:
    numbers = [int(value) for value in QUESTION_IN_TOPIC.findall(str(candidate.get("topic", ""))) if int(value) in questions]
    if numbers:
        return list(dict.fromkeys(numbers))
    # A topic without a question number goes to the question whose title it shares most words with.
    words = set(_words(f"{candidate.get('topic', '')} {candidate.get('claim', '')}"))
    scored = sorted(((len(words & set(_words(title))), -number) for number, title in questions.items()), reverse=True)
    return [-scored[0][1]] if scored and scored[0][0] else [min(questions)]


def _risk(candidate: dict[str, Any]) -> str:
    quote = str(candidate.get("quote", "")).casefold()
    terms = [term for term in RISK_TERMS if re.search(rf"\b{re.escape(term)}\b", quote)]
    if not terms:
        return ""
    return (f"; script-flagged overstatement-risk (quote terms: {', '.join(terms)}); wording is source-attributed, "
            "read claim as stated by source, not as verified achievement")


def _cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).replace("|", "\\|").strip()


def _source_texts(root: Path) -> dict[str, str]:
    from research_control.validators import sources
    from research_control.checks import _source_paths

    manifest_path = root / "01-sources/MANIFEST.csv"
    manifest = sources.load_manifest(manifest_path) if manifest_path.is_file() else []
    texts: dict[str, str] = {}
    for source_id, paths in _source_paths(root, manifest).items():
        texts[source_id] = "\n".join(
            normalize_text(path.read_text(encoding="utf-8", errors="replace")) for path in paths if path.is_file()
        )
    return texts


def _quote_found(quote: str, text: str) -> bool:
    # The fact_quotes rule: every part of the quote (split at ellipses) appears in the source.
    parts = [normalize_text(item).strip(" .,;:") for item in re.split(r"\s*(?:\.\.\.|…)\s*", quote)]
    parts = [item for item in parts if len(item.split()) >= 2]
    return bool(parts) and all(item in text for item in parts)


def _source_dates(root: Path) -> dict[str, str]:
    path = root / "tools/outputs/source-dates.jsonl"
    return {str(row.get("source_id")): str(row.get("content_date") or "") for row in load_jsonl(path)} if path.is_file() else {}


def file_candidates(root: Path, worker: str = "runtime filing") -> dict[str, Any]:
    root = root.resolve()
    questions = scope_questions(root)
    if not questions:
        raise ValueError("00-scope.md lists no numbered research questions to file facts under")
    candidates = load_jsonl(root / CANDIDATES)
    by_id = {str(row.get("candidate_id")): row for row in candidates}
    tables = _tables(root, questions)
    existing = load_fact_tables(sorted((root / "02-facts").glob("*.md")))
    filed_by_candidate: dict[str, str] = {}
    by_quote: dict[tuple[str, str], str] = {}
    by_claim: dict[tuple[str, str], str] = {}
    quotes_by_source: dict[str, list[tuple[str, str]]] = defaultdict(list)
    claim_sources: dict[str, set[str]] = defaultdict(set)
    numbers: Counter[str] = Counter()
    for row in existing:
        fact_id = row.get("fact_id", "")
        prefix, _, number = fact_id.rpartition("-")
        if number.isdigit():
            numbers[prefix] = max(numbers[prefix], int(number))
        for candidate_id in CANDIDATE_ID.findall(" ".join(str(value) for key, value in row.items() if not key.startswith("_"))):
            filed_by_candidate.setdefault(candidate_id, fact_id)
        source = row.get("source_id", "")
        quote = normalize_text(row.get("verbatim_quote", ""))
        by_quote.setdefault((source, quote), fact_id)
        by_claim.setdefault((source, normalize_text(row.get("claim", ""))), fact_id)
        quotes_by_source[source].append((quote, fact_id))
        claim_sources[normalize_text(row.get("claim", ""))].add(fact_id)
    disposed = {str(row.get("input_id")) for row in load_jsonl(root / DISPOSITIONS)} if (root / DISPOSITIONS).is_file() else set()
    texts = _source_texts(root)
    dates = _source_dates(root)
    assigned: dict[str, str] = {}
    new_rows: dict[int, list[str]] = defaultdict(list)
    dispositions: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    merges: list[dict[str, str]] = []
    filed: list[dict[str, str]] = []

    def dispose(candidate_id: str, kind: str, reason: str, outputs: list[str], evidence: list[str]) -> None:
        dispositions.append({
            "assignment_id": "facts.file-facts", "input_id": candidate_id, "disposition": kind,
            "reason": reason, "evidence_paths": evidence, "output_ids": outputs,
        })

    def resolve(reference: str, depth: int = 0) -> str:
        if not reference.startswith("CAND-"):
            return reference
        if reference in assigned or reference in filed_by_candidate:
            return assigned.get(reference) or filed_by_candidate[reference]
        target = by_id.get(reference, {})
        return resolve(str(target["duplicate_of"]), depth + 1) if target.get("duplicate_of") and depth < 20 else ""

    pending = [row for row in candidates if str(row.get("candidate_id")) not in filed_by_candidate
               and str(row.get("candidate_id")) not in disposed]
    declared = []
    for candidate in pending:
        candidate_id = str(candidate["candidate_id"])
        if candidate.get("duplicate_of"):
            declared.append(candidate)
            continue
        source = str(candidate.get("source_id", ""))
        quote, claim = normalize_text(str(candidate.get("quote", ""))), normalize_text(str(candidate.get("claim", "")))
        kept = by_quote.get((source, quote))
        reason = f"same source ({source}) and quote as {kept}" if kept else ""
        if not kept:
            kept = by_claim.get((source, claim))
            reason = f"near-duplicate: same source ({source}) and the same claim as {kept}" if kept else ""
        if not kept and len(quote.split()) >= 8:
            kept = next((fact_id for other, fact_id in quotes_by_source[source]
                         if len(other.split()) >= 8 and (quote in other or other in quote)), "")
            reason = f"near-duplicate: same source ({source}) and one quote contains the other ({kept})" if kept else ""
        if kept:
            assigned[candidate_id] = kept
            dispose(candidate_id, "duplicate", f"{reason}; no new row", [kept], [CANDIDATES])
            stats["near duplicates merged" if reason.startswith("near") else "duplicates of a filed quote"] += 1
            if reason.startswith("near"):
                merges.append({"candidate_id": candidate_id, "kept": kept, "reason": reason})
            continue
        if not _quote_found(str(candidate.get("quote", "")), texts.get(source, "")):
            dispose(candidate_id, "rejected", f"quote not found in the captured text of {source}", [], [CANDIDATES])
            stats["rejected: quote not in source"] += 1
            continue
        chosen = _questions_for(candidate, questions)
        path, prefix = tables[chosen[0]]
        numbers[prefix] += 1
        fact_id = f"{prefix}-{numbers[prefix]:03d}"
        source_date = str(candidate.get("source_date") or "")
        if not re.search(r"\d{4}-\d{2}-\d{2}", source_date):
            dated = dates.get(source, "")
            source_date = f"{dated} (source dating)" if dated else f"{source_date or 'undated'}; captured {utc_now()[:10]}"
        repeats = sorted(claim_sources.get(claim, set()))
        cells = [
            fact_id, candidate.get("claim"), candidate.get("quote"), source, candidate.get("location"), source_date,
            candidate.get("grade"), "; ".join(f"Q{number} {_slug(questions[number])}" for number in chosen),
            candidate.get("about"), candidate.get("said_by"), f"filed ({worker}){_risk(candidate)}", candidate_id,
            candidate.get("notes") or "", "", ", ".join(repeats[:5]),
        ]
        new_rows[chosen[0]].append("| " + " | ".join(_cell(value) for value in cells) + " |")
        assigned[candidate_id] = fact_id
        by_quote[(source, quote)] = fact_id
        by_claim[(source, claim)] = fact_id
        quotes_by_source[source].append((quote, fact_id))
        claim_sources[claim].add(fact_id)
        dispose(candidate_id, "completed", f"filed as {fact_id} in {path.relative_to(root)}", [fact_id],
                [str(path.relative_to(root)), CANDIDATES])
        stats["filed"] += 1
        filed.append({"fact_id": fact_id, "candidate_id": candidate_id, "source_id": source,
                      "quote": str(candidate.get("quote", "")), "topic": str(candidate.get("topic", "")),
                      "filed_under": f"Q{chosen[0]}"})
    for candidate in declared:
        target = resolve(str(candidate["duplicate_of"]))
        if target:
            dispose(str(candidate["candidate_id"]), "duplicate",
                    f"marked duplicate_of {candidate['duplicate_of']} by the reducer; same source and quote as {target}",
                    [target], [CANDIDATES])
            stats["duplicates marked by the reducer"] += 1
        else:
            dispose(str(candidate["candidate_id"]), "rejected",
                    f"duplicate_of {candidate['duplicate_of']} names no filed fact", [], [CANDIDATES])
            stats["rejected: unresolved duplicate"] += 1
    header = "| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n"
    for number, rows in new_rows.items():
        path, _ = tables[number]
        if not path.is_file():
            atomic_write_text(path, f"# Q{number} {_slug(questions[number])}\n\nFiled by the runtime from {CANDIDATES}. "
                                    "Grade, said_by, source date, and notes are carried from the candidate.\n\n" + header)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")
    (root / DISPOSITIONS).parent.mkdir(parents=True, exist_ok=True)
    with (root / DISPOSITIONS).open("a", encoding="utf-8") as handle:
        for row in dispositions:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    audit = root / SCRIPT_AUDIT
    previous = audit.read_text(encoding="utf-8") if audit.is_file() else "# Script audits\n"
    atomic_write_text(audit, previous.rstrip("\n") + "\n\n" + "\n".join([
        f"## Runtime filing {utc_now()}", "",
        f"Candidates in {CANDIDATES}: {len(candidates)}; already filed or disposed: {len(candidates) - len(pending)}; "
        f"processed now: {len(pending)}.", "",
        *(f"- {key}: {value}" for key, value in sorted(stats.items())), "",
        "Checks: every candidate has one disposition; duplicates name a filed fact; filed quotes were matched "
        "against the captured text by the fact_quotes rule; overstatement-risk terms are flagged in the verdict.",
    ]) + "\n")
    seed = random.Random(len(candidates))
    sample_rows = seed.sample(filed, min(SPOT_SAMPLE_SIZE, len(filed)))
    for row in sample_rows:
        from research_control.deeplinks import source_excerpt

        row["excerpt"] = source_excerpt(root, row["source_id"], row["quote"]).get("text", "")[:1200]
    atomic_write_json(root / SPOT_SAMPLE, {
        "created": utc_now(), "merges": seed.sample(merges, min(SPOT_SAMPLE_SIZE, len(merges))), "filed": sample_rows,
    })
    return {"status": "PASS", "processed": len(pending), **dict(stats)}


def load_spot_sample(root: Path) -> dict[str, Any]:
    path = root / SPOT_SAMPLE
    return load_json(path) if path.is_file() else {}
