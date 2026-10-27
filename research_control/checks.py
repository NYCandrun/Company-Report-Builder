"""Produce phase reports and evaluate operational phase completion."""

from __future__ import annotations

import json
from hashlib import sha256
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

from research_control import FAIL, PASS, UNKNOWN
from research_control.diagram_contract import DIAGRAM_CAPTIONS, DIAGRAM_MODEL_JSON, DIAGRAM_SPECS, FINAL_ARTIFACTS
from research_control.gates.phase_gate import check_phase_gate
from research_control.hashing import checker_version, hash_patterns, hash_path, report_inputs_current
from research_control.io import (
    atomic_write_json,
    find_phase,
    load_json,
    load_jsonl,
    require_nonempty_paths,
    resolve_pattern,
    workflow,
)
from research_control.orchestration import ACTIVE_PATH, all_task_definitions, load_state, set_phase_result
from research_control.reconciliation.assignments import reconcile_records, validate_ledger
from research_control.reporting import make_validation_report
from research_control.validators import brand, citations, dates, diagrams, exhibits, facts, quotes, sources, tags, visual_records, writing_rules


FACT_ID = re.compile(r"\b[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?\b")
BRITISH_FORMS = {
    "organisation": "organization",
    "organisations": "organizations",
    "prioritise": "prioritize",
    "prioritised": "prioritized",
    "analyse": "analyze",
    "analysed": "analyzed",
    "behaviour": "behavior",
    "colour": "color",
    "centre": "center",
}


def _report(
    root: Path,
    checker: str,
    patterns: Iterable[str],
    expected: int,
    checked: int,
    failures: Iterable[str] = (),
    unknowns: Iterable[str] = (),
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failed = list(failures)
    unresolved = list(unknowns)
    status = FAIL if failed else UNKNOWN if unresolved or checked < expected else PASS
    return make_validation_report(
        checker=checker,
        checker_version=checker_version(sys.modules[__name__]),
        status=status,
        expected_count=expected,
        checked_count=checked,
        failures=failed,
        unknowns=unresolved,
        input_hashes=hash_patterns(root, patterns),
        details=details,
    )


def _write(root: Path, relative: str, report: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(root / relative, report)
    return report


def _validation_engine_key(root: Path) -> str:
    values = hash_patterns(root, [
        "research_control/checks.py",
        "research_control/validators/*.py",
        "research_control/reconciliation/*.py",
        "research_control/reporting/*.py",
        "research_control/hashing/*.py",
        "research_control/schemas/*.json",
        "WORKFLOW.yaml",
    ])
    return sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def _cached_pass(root: Path, relative: str, engine_key: str) -> dict[str, Any] | None:
    path = root / relative
    if not path.is_file() or not path.stat().st_size:
        return None
    try:
        report = load_json(path)
    except Exception:
        return None
    current, _stale = report_inputs_current(root, report)
    if report.get("status") == PASS and report.get("cache_key") == engine_key and current:
        return report
    return None


def _paths(root: Path, patterns: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(
            path for path in resolve_pattern(root, pattern)
            if path.is_file() and path.stat().st_size > 0
        )
    return sorted(set(found), key=lambda item: item.as_posix())


def _artifact_contract(root: Path, checker: str, patterns: list[str]) -> dict[str, Any]:
    present, missing = require_nonempty_paths(root, patterns)
    return _report(
        root,
        checker,
        patterns,
        len(patterns),
        len(patterns) - len(missing),
        unknowns=[f"missing or empty artifact: {item}" for item in missing],
        details={"present": present},
    )


def _manifest(root: Path) -> list[dict[str, str]]:
    path = root / "01-sources/MANIFEST.csv"
    return sources.load_manifest(path) if path.is_file() and path.stat().st_size else []


def _fact_records(root: Path) -> list[dict[str, str]]:
    return facts.load_fact_tables(_paths(root, ["02-facts/*.md", "04-competitors/*/02-facts/*.md"]))


TEXT_DERIVATIVE_SUFFIXES = {".txt", ".md", ".json", ".jsonl", ".csv", ".xml"}


def _source_paths(root: Path, manifest: list[dict[str, str]]) -> dict[str, list[Path]]:
    """Map each source to its canonical text derivatives (page text, PDF text, transcript).

    Quotes are checked against what extraction read, not raw HTML or binaries.
    A source with no text derivative falls back to its first local file.
    """
    result: dict[str, list[Path]] = {}
    for row in manifest:
        locals_ = [item.strip() for item in row.get("local file", "").split(";") if item.strip()]
        texts = [root / item for item in locals_ if Path(item).suffix.casefold() in TEXT_DERIVATIVE_SUFFIXES]
        if texts or locals_:
            result[row.get("id", "")] = texts or [root / locals_[0]]
    return result


def _rename(report: dict[str, Any], checker: str) -> dict[str, Any]:
    report["checker"] = checker
    return report


def _validate_bootstrap(root: Path, validator_id: str, phase: dict[str, Any]) -> dict[str, Any]:
    if validator_id == "bootstrap_paths":
        patterns = [item["path"] for item in phase["outputs"]]
        failures: list[str] = []
        checked = 0
        for pattern in patterns:
            path = root / pattern
            if path.is_file() and (path.stat().st_size > 0 or path.name == "worker-ledger.jsonl"):
                checked += 1
            else:
                failures.append(f"bootstrap artifact missing: {pattern}")
        return _report(root, validator_id, patterns, len(patterns), checked, failures)
    failures = []
    if sys.version_info < (3, 11):
        failures.append("Python 3.11 or newer is required")
    if shutil.which("git") is None:
        failures.append("git is unavailable")
    try:
        state = load_state(root)
        if not state.get("company_url"):
            failures.append("company URL is absent from run state")
    except Exception as error:
        failures.append(str(error))
    return _report(root, validator_id, ["README.md", "WORKFLOW.yaml", "tools/outputs/run-state.json"], 3, 3 - len(failures), failures)


def _validate_scope(root: Path) -> dict[str, Any]:
    path = root / "00-scope.md"
    unknowns = [] if path.is_file() and path.stat().st_size else ["00-scope.md is missing or empty"]
    failures: list[str] = []
    if not unknowns:
        text = path.read_text(encoding="utf-8", errors="replace")
        host = load_state(root).get("company_host", "")
        if host and host not in text.casefold() and load_state(root)["company_url"] not in text:
            failures.append("scope does not identify the configured company URL or host")
        for heading in ("source", "compet", "input"):
            if heading not in text.casefold():
                failures.append(f"scope does not address {heading} coverage")
        if not re.search(r"\bQ1\b", text):
            failures.append("scope does not number its research questions (Q1, Q2, ...)")
    return _report(root, "scope_contract", ["00-scope.md", "tools/outputs/run-state.json"], 1, 0 if unknowns else 1, failures, unknowns)


def _ledger(root: Path, task_types: set[str] | None = None) -> dict[str, Any]:
    path = root / "tools/outputs/worker-ledger.jsonl"
    if not path.is_file() or not path.stat().st_size:
        return _report(root, "worker_ledger", [str(path.relative_to(root))], 1, 0, unknowns=["worker ledger is empty"])
    rows = load_jsonl(path)
    report = validate_ledger(root, rows, task_types)
    selected = [row for row in rows if task_types is None or row.get("task_type") in task_types]
    label = "all" if task_types is None else "-".join(sorted(task_types))
    snapshot = root / "tools/outputs/ledger-snapshots" / f"{label}.json"
    atomic_write_json(snapshot, selected)
    report["input_hashes"] = hash_patterns(root, [str(snapshot.relative_to(root))])
    report.setdefault("details", {})["ledger_snapshot"] = str(snapshot.relative_to(root))
    return report


def _validate_synthesis_ids(root: Path, checker: str) -> dict[str, Any]:
    paths = _paths(root, ["05-synthesis/*.md"])
    known = {row.get("fact_id", "") for row in _fact_records(root)}
    failures: list[str] = []
    found: set[str] = set()
    for path in paths:
        for fact_id in FACT_ID.findall(path.read_text(encoding="utf-8", errors="replace")):
            found.add(fact_id)
            if fact_id not in known:
                failures.append(f"{path.relative_to(root)}: unknown fact ID {fact_id}")
    unknowns = [] if found else ["no fact IDs found in synthesis Markdown"]
    patterns = [str(path.relative_to(root)) for path in paths] + ["02-facts/*.md"]
    return _report(root, checker, patterns, len(paths), len(paths), failures, unknowns, {"fact_ids": len(found)})


def _verification_records(root: Path) -> list[dict[str, Any]]:
    path = root / "tools/outputs/verification-verdicts.jsonl"
    return load_jsonl(path) if path.is_file() and path.stat().st_size else []


def _validate_verdicts(root: Path, checker: str) -> dict[str, Any]:
    records = _verification_records(root)
    failures: list[str] = []
    allowed = {"confirmed", "corrected", "unsupported", "source unreachable"}
    seen: set[str] = set()
    for index, row in enumerate(records, 1):
        fact_id = str(row.get("fact_id", ""))
        if not fact_id:
            failures.append(f"row {index}: missing fact_id")
        elif fact_id in seen:
            failures.append(f"{fact_id}: duplicate verdict")
        seen.add(fact_id)
        if row.get("verdict") not in allowed:
            failures.append(f"{fact_id or index}: invalid verdict {row.get('verdict')!r}")
        if not str(row.get("reason", "")).strip():
            failures.append(f"{fact_id or index}: missing reason")
        if not row.get("evidence_paths"):
            failures.append(f"{fact_id or index}: missing evidence paths")
    unknowns = [] if records else ["verification verdict file is missing or empty"]
    return _report(root, checker, ["tools/outputs/verification-verdicts.jsonl", "tools/lists/cited-facts.txt"], len(records) or 1, len(records), failures, unknowns)


def _review_findings(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _paths(root, ["tools/outputs/review-findings-*.jsonl"]):
        rows.extend(load_jsonl(path))
    return rows


def _validate_review_records(root: Path) -> dict[str, Any]:
    report_paths = _paths(root, ["06-checks/review-technical.md", "06-checks/review-devils-advocate.md", "06-checks/review-insider*.md", "06-checks/review-editor*.md"])
    findings = _review_findings(root)
    failures: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(findings, 1):
        if row.get("status") == "clean":
            if not row.get("review_id"):
                failures.append(f"row {index}: clean record lacks review_id")
            continue
        required = ("finding_id", "review_id", "artifact", "location", "severity", "finding", "status")
        missing = [field for field in required if not str(row.get(field, "")).strip()]
        if missing:
            failures.append(f"row {index}: missing {', '.join(missing)}")
        finding_id = str(row.get("finding_id", ""))
        if finding_id and finding_id in seen:
            failures.append(f"duplicate finding ID {finding_id}")
        seen.add(finding_id)
    unknowns = [] if len(report_paths) >= 4 else [f"only {len(report_paths)} of four independent review reports exist"]
    return _report(root, "review_records", ["06-checks/review-*.md", "tools/outputs/review-findings-*.jsonl"], 4, min(4, len(report_paths)), failures, unknowns, {"findings": len(findings)})


def _validate_review_independence(root: Path) -> dict[str, Any]:
    path = root / "tools/outputs/worker-ledger.jsonl"
    rows = load_jsonl(path) if path.is_file() and path.stat().st_size else []
    required = {"technical_review", "devils_advocate", "insider_review", "editor_review"}
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("task_type") in required:
            latest[str(row["task_type"])] = row
    failures: list[str] = []
    missing = sorted(required - set(latest))
    workers = [str(row.get("worker_id")) for row in latest.values()]
    if len(workers) != len(set(workers)):
        failures.append("independent review tasks reuse a worker ID")
    for task_type, row in latest.items():
        if not row.get("independent"):
            failures.append(f"{task_type}: ledger does not mark the task independent")
    return _report(root, "review_independence", ["tools/outputs/worker-ledger.jsonl"], len(required), len(latest), failures, [f"missing independent task type {item}" for item in missing])


def _validate_accepted_fixes(root: Path) -> dict[str, Any]:
    findings = [row for row in _review_findings(root) if row.get("finding_id")]
    path = root / "tools/outputs/review-decisions.jsonl"
    decisions = load_jsonl(path) if path.is_file() and path.stat().st_size else []
    by_id = {str(row.get("finding_id", row.get("input_id", ""))): row for row in decisions}
    failures: list[str] = []
    for row in findings:
        finding_id = str(row["finding_id"])
        decision = by_id.get(finding_id)
        if not decision:
            failures.append(f"{finding_id}: missing decision")
            continue
        disposition = decision.get("disposition", decision.get("status"))
        if disposition not in {"apply", "apply_in_part", "reject", "closed"}:
            failures.append(f"{finding_id}: invalid decision {disposition!r}")
        if not str(decision.get("reason", decision.get("decision_reason", ""))).strip():
            failures.append(f"{finding_id}: missing decision reason")
        if disposition in {"apply", "apply_in_part"} and not decision.get("evidence_paths"):
            failures.append(f"{finding_id}: accepted fix has no evidence path")
    unexpected = sorted(set(by_id) - {str(row["finding_id"]) for row in findings})
    failures.extend(f"{item}: decision has no finding" for item in unexpected if item)
    unknowns = [] if path.is_file() and path.stat().st_size else ["review decision records are missing"]
    return _report(root, "accepted_fixes", ["tools/outputs/review-findings-*.jsonl", "tools/outputs/review-decisions.jsonl", "05-synthesis/*.md"], len(findings), len(set(by_id) & {str(row['finding_id']) for row in findings}), failures, unknowns)


def _validate_publication_decisions(root: Path) -> dict[str, Any]:
    finding_paths = _paths(root, ["tools/outputs/publication-findings-*.jsonl"])
    rows: list[dict[str, Any]] = []
    for path in finding_paths:
        rows.extend(load_jsonl(path))
    findings = [row for row in rows if row.get("finding_id")]
    decision_path = root / "tools/outputs/publication-decisions.jsonl"
    decisions = load_jsonl(decision_path) if decision_path.is_file() and decision_path.stat().st_size else []
    by_id = {str(row.get("finding_id", row.get("input_id", ""))): row for row in decisions}
    failures: list[str] = []
    for row in findings:
        finding_id = str(row["finding_id"])
        decision = by_id.get(finding_id)
        if not decision:
            failures.append(f"{finding_id}: missing publication decision")
            continue
        disposition = decision.get("disposition", decision.get("status"))
        if disposition not in {"apply", "apply_in_part", "reject", "closed"}:
            failures.append(f"{finding_id}: invalid publication decision {disposition!r}")
        if not str(decision.get("reason", decision.get("decision_reason", ""))).strip():
            failures.append(f"{finding_id}: missing publication decision reason")
        if disposition in {"apply", "apply_in_part"} and not decision.get("evidence_paths"):
            failures.append(f"{finding_id}: applied publication decision lacks evidence")
    unexpected = sorted(set(by_id) - {str(row["finding_id"]) for row in findings})
    failures.extend(f"{item}: publication decision has no finding" for item in unexpected if item)
    unknowns: list[str] = []
    if len(finding_paths) < 4:
        unknowns.append(f"expected four publication finding files, found {len(finding_paths)}")
    if not decision_path.is_file() or not decision_path.stat().st_size:
        unknowns.append("publication decision records are missing")
    return _report(
        root,
        "publication_decisions",
        ["tools/outputs/publication-findings-*.jsonl", "tools/outputs/publication-decisions.jsonl", "07-final-report/*"],
        len(findings),
        len(set(by_id) & {str(row["finding_id"]) for row in findings}),
        failures,
        unknowns,
    )


def _final_artifacts(root: Path) -> list[str]:
    return list(FINAL_ARTIFACTS)


def _validate_reader_facing(root: Path) -> dict[str, Any]:
    paths = _paths(root, ["07-final-report/company-brief.html", "07-final-report/brand-guide.html", *(spec["path"] for spec in DIAGRAM_SPECS)])
    failures: list[str] = []
    prohibited = ("02-facts/", "tools/outputs/", "scratchpad/", "remove-before-sharing", "source_id", "fact_id")
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".svg":
            try:
                svg = ET.fromstring(text)
                text = " ".join(
                    element.text or ""
                    for element in svg.iter()
                    if element.tag.rsplit("}", 1)[-1] in {"text", "tspan"}
                )
            except ET.ParseError:
                failures.append(f"{path.relative_to(root)}: unreadable SVG text")
        for token in prohibited:
            if token.casefold() in text.casefold():
                failures.append(f"{path.relative_to(root)}: exposes internal token {token}")
        visible = re.sub(r"<[^>]+>", " ", text)
        for fact_id in FACT_ID.findall(visible):
            failures.append(f"{path.relative_to(root)}: exposes fact ID {fact_id}")
    expected = 2 + len(DIAGRAM_SPECS)
    unknowns = [] if len(paths) == expected else [f"expected two HTML documents and four SVG diagrams, found {len(paths)} artifacts"]
    return _report(root, "reader_facing_text", ["07-final-report/{company-brief,brand-guide}.html", "07-final-report/*.svg"], expected, len(paths), failures, unknowns)


def _validate_american_english(root: Path) -> dict[str, Any]:
    paths = _paths(root, ["05-synthesis/company-brief.md", DIAGRAM_CAPTIONS])
    failures: list[str] = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            unquoted = writing_rules.unquoted(line)
            for british, american in BRITISH_FORMS.items():
                if re.search(rf"\b{british}\b", unquoted, re.IGNORECASE):
                    failures.append(f"{path.relative_to(root)}:{number}: use {american} instead of {british}")
    unknowns = [] if len(paths) == 2 else ["company brief or diagram captions are incomplete"]
    return _report(root, "american_english", [str(path.relative_to(root)) for path in paths], 2, len(paths), failures, unknowns)


def _citation_maps(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    result = []
    for path in _paths(root, ["tools/outputs/citation-map-*.json"]):
        try:
            value = load_json(path)
        except Exception:
            continue
        if isinstance(value, dict):
            result.append((path, value))
    return result


def _citation_numbers(value: str) -> list[int]:
    numbers: list[int] = []
    for match in re.finditer(r"\[((?:\d+\s*,\s*)*\d+)\]", value):
        numbers.extend(int(item.strip()) for item in match.group(1).split(","))
    return numbers


def _validate_citations(root: Path) -> dict[str, Any]:
    maps = _citation_maps(root)
    failures: list[str] = []
    checked = 0
    for path, data in maps:
        report = citations.validate_map(data, root, str(path.relative_to(root)))
        failures.extend(f"{path.name}: {item}" for item in report.get("failures", []))
        checked += report.get("checked_count", 0)
        slug = path.stem.removeprefix("citation-map-")
        markdown_path = root / f"05-synthesis/{slug}.md"
        html_path = root / f"07-final-report/{slug}.html"
        expected_numbers = [int(item.get("n")) for item in data.get("citations", []) if isinstance(item.get("n"), int)]
        if not markdown_path.is_file() or not html_path.is_file():
            failures.append(f"{path.name}: corresponding Markdown or HTML artifact is missing")
        else:
            markdown_numbers = _citation_numbers(markdown_path.read_text(encoding="utf-8", errors="replace"))
            html_numbers = _citation_numbers(re.sub(r"<[^>]+>", " ", html_path.read_text(encoding="utf-8", errors="replace")))
            if markdown_numbers != expected_numbers:
                failures.append(f"{path.name}: Markdown citation placement {markdown_numbers} does not match map {expected_numbers}")
            if html_numbers != expected_numbers:
                failures.append(f"{path.name}: rendered citation placement {html_numbers} does not match map {expected_numbers}")
    unknowns = [] if len(maps) == 1 else [f"expected one company-brief citation map, found {len(maps)}"]
    expected = sum(len(data.get("citations", [])) for _path, data in maps)
    return _report(root, "citation_structure", ["tools/outputs/citation-map-*.json"], expected, checked, failures, unknowns)


def _validate_final_cited_facts(root: Path) -> dict[str, Any]:
    cited = {
        str(fact_id)
        for _path, data in _citation_maps(root)
        for citation in data.get("citations", [])
        for fact_id in citation.get("facts", [])
    }
    model_path = root / DIAGRAM_MODEL_JSON
    if model_path.is_file() and model_path.stat().st_size:
        model = load_json(model_path)
        cited.update(
            str(fact_id)
            for group in ("entities", "relationships")
            for record in model.get(group, [])
            for fact_id in record.get("fact_ids", [])
        )
    verified = {
        str(row.get("fact_id"))
        for row in _verification_records(root)
        if row.get("verdict") in {"confirmed", "corrected"}
    }
    missing = sorted(cited - verified)
    return _report(root, "new_cited_fact_verification", ["tools/outputs/citation-map-*.json", DIAGRAM_MODEL_JSON, "tools/outputs/verification-verdicts.jsonl"], len(cited), len(cited & verified), [f"published fact lacks accepted verification: {item}" for item in missing])


def _validate_exhibits(root: Path) -> dict[str, Any]:
    path = root / "tools/outputs/exhibit-map.json"
    if not path.is_file() or not path.stat().st_size:
        return _report(root, "exhibit_mapping", ["tools/outputs/exhibit-map.json"], 1, 0, unknowns=["exhibit map is missing"])
    data = load_json(path)
    elements = data.get("elements", data if isinstance(data, list) else [])
    known = {str(row.get("fact_id")) for row in _fact_records(root)}
    return exhibits.validate(elements, known, root)


def _validate_design(root: Path) -> dict[str, Any]:
    patterns = [*_final_artifacts(root), "05-synthesis/design-notes.md", "05-synthesis/design/style.css"]
    report = _artifact_contract(root, "design_check", patterns)
    failures = report["failures"]
    for relative in _final_artifacts(root):
        path = root / relative
        if not path.is_file():
            continue
        if path.suffix == ".pdf" and not path.read_bytes().startswith(b"%PDF-"):
            failures.append(f"{relative}: invalid PDF signature")
        if path.suffix == ".html":
            text = path.read_text(encoding="utf-8", errors="replace").casefold()
            if "<style" not in text and "stylesheet" not in text:
                failures.append(f"{relative}: no stylesheet")
    brief_path = root / "07-final-report/company-brief.html"
    if brief_path.is_file():
        brief = brief_path.read_text(encoding="utf-8", errors="replace")
        for spec in DIAGRAM_SPECS:
            if f'data-report-diagram="{spec["id"]}"' not in brief:
                failures.append(f"company-brief.html does not place {spec['id']} in the target report layout")
    if failures:
        report["status"] = FAIL
        report["failure_count"] = len(failures)
    return report


def _visual_data(root: Path) -> tuple[int, list[dict[str, Any]]]:
    metadata_path = root / "tools/outputs/render-metadata.json"
    review_path = root / "06-checks/visual-review.json"
    expected = 0
    if metadata_path.is_file() and metadata_path.stat().st_size:
        metadata = load_json(metadata_path)
        expected = int(metadata.get("total_pages", 0))
    records: list[dict[str, Any]] = []
    if review_path.is_file() and review_path.stat().st_size:
        value = load_json(review_path)
        records = value.get("pages", value if isinstance(value, list) else [])
    return expected, records


def _validate_visual(root: Path, checker: str) -> dict[str, Any]:
    expected, records = _visual_data(root)
    if expected < 1:
        return _report(root, checker, ["tools/outputs/render-metadata.json", "06-checks/visual-review.json"], 1, 0, unknowns=["render metadata has no page count"])
    report = visual_records.validate(expected, records, root)
    report["checker"] = checker
    metadata = load_json(root / "tools/outputs/render-metadata.json")
    previews = metadata.get("documents", {}).get("company-brief", {}).get("page_previews", [])
    by_page = {record.get("page"): record for record in records}
    for page, relative in enumerate(previews, 1):
        expected_hash = hash_path(root / relative)
        if by_page.get(page, {}).get("artifact_sha256") != expected_hash:
            report["failures"].append(
                f"page {page}: visual review is not bound to current preview hash"
            )
    if checker == "visual_audit":
        unresolved = [row.get("page") for row in records if row.get("status") == "issues"]
        if unresolved:
            report["failures"].append(f"unresolved visual issues remain on pages {unresolved}")
    if report["failures"]:
        report["failure_count"] = len(report["failures"])
        report["status"] = FAIL
    return report


def _validate_artifact_binding(root: Path) -> dict[str, Any]:
    artifacts = _final_artifacts(root)
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for relative in artifacts:
        digest = hash_path(root / relative)
        if digest == "MISSING":
            missing.append(relative)
        else:
            hashes[relative] = digest
    return _report(root, "artifact_binding", artifacts, len(artifacts), len(hashes), unknowns=[f"artifact missing: {item}" for item in missing], details={"artifact_hashes": hashes})


def run_validator(root: Path, phase: dict[str, Any], validator_id: str) -> dict[str, Any]:
    if phase["id"] == "bootstrap":
        return _validate_bootstrap(root, validator_id, phase)
    if validator_id == "scope_contract":
        return _validate_scope(root)
    manifest = _manifest(root)
    fact_rows = _fact_records(root)
    source_ids = {row.get("id", "") for row in manifest}
    fact_patterns = ["02-facts/*.md", "04-competitors/*/02-facts/*.md"]
    if validator_id in {"source_records", "manifest_files"}:
        return _rename(sources.validate_records(manifest, root), validator_id) if manifest else _report(root, validator_id, ["01-sources/MANIFEST.csv"], 1, 0, unknowns=["source manifest is missing or empty"])
    if validator_id == "source_dates":
        return dates.validate_source_dates(manifest, root) if manifest else _report(root, validator_id, ["01-sources/MANIFEST.csv"], 1, 0, unknowns=["source manifest is missing or empty"])
    if validator_id == "capture_workers":
        return _rename(_ledger(root, {"capture"}), validator_id)
    if validator_id in {"fact_records", "fact_source_ids", "fact_overstatement", "corrected_fact_layer1"}:
        if not fact_rows:
            return _report(root, validator_id, fact_patterns, 1, 0, unknowns=["no fact records found"])
        return _rename(facts.validate_records(fact_rows, root, source_ids, fact_patterns), validator_id)
    if validator_id == "fact_quotes":
        return quotes.validate(fact_rows, _source_paths(root, manifest), root, fact_patterns) if fact_rows else _report(root, validator_id, fact_patterns, 1, 0, unknowns=["no fact records found"])
    if validator_id == "fact_dates":
        source_dates = {row.get("id", ""): row.get("date published", "") for row in manifest if row.get("date published")}
        return dates.validate_fact_dates(fact_rows, root, fact_patterns, source_dates) if fact_rows else _report(root, validator_id, fact_patterns, 1, 0, unknowns=["no fact records found"])
    if validator_id == "fact_tags":
        return tags.validate(fact_rows, root, fact_patterns) if fact_rows else _report(root, validator_id, fact_patterns, 1, 0, unknowns=["no fact records found"])
    if validator_id in {"synthesis_fact_ids", "corrected_synthesis_fact_ids"}:
        return _validate_synthesis_ids(root, validator_id)
    if validator_id == "synthesis_writing_rules":
        paths = _paths(root, ["05-synthesis/*.md"])
        return _rename(writing_rules.validate(paths, root), validator_id) if paths else _report(root, validator_id, ["05-synthesis/*.md"], 1, 0, unknowns=["synthesis files missing"])
    if validator_id == "verification_verdict_records":
        return _validate_verdicts(root, validator_id)
    if validator_id == "review_records":
        return _validate_review_records(root)
    if validator_id == "review_independence":
        return _validate_review_independence(root)
    if validator_id == "accepted_fixes":
        return _validate_accepted_fixes(root)
    if validator_id == "final_artifact_contract":
        return _artifact_contract(root, validator_id, _final_artifacts(root))
    if validator_id == "reader_facing_text":
        return _validate_reader_facing(root)
    if validator_id == "american_english":
        return _validate_american_english(root)
    if validator_id == "new_cited_fact_verification":
        return _validate_final_cited_facts(root)
    if validator_id == "citation_structure":
        return _validate_citations(root)
    if validator_id == "diagram_models":
        verified = {
            str(row.get("fact_id"))
            for row in _verification_records(root)
            if row.get("verdict") in {"confirmed", "corrected"}
        }
        return diagrams.validate_models(
            root,
            {str(row.get("fact_id")) for row in fact_rows},
            source_ids,
            verified,
        )
    if validator_id in {"brand_capture_artifacts", "brand_artifacts"}:
        return _rename(brand.validate_artifacts(root), validator_id)
    if validator_id == "brand_visual_records":
        return brand.validate_visual_records(root)
    if validator_id == "diagram_style_spec":
        return diagrams.validate_style_spec(root)
    if validator_id == "diagram_artifacts":
        return diagrams.validate_artifacts(root)
    if validator_id == "diagram_visual_records":
        return diagrams.validate_visual_records(root)
    if validator_id == "exhibit_mapping":
        return _validate_exhibits(root)
    if validator_id == "design_check":
        return _validate_design(root)
    if validator_id in {"visual_audit", "visual_records"}:
        return _validate_visual(root, validator_id)
    if validator_id == "publication_decisions":
        return _validate_publication_decisions(root)
    if validator_id == "artifact_binding":
        return _validate_artifact_binding(root)
    return _artifact_contract(root, validator_id, [item["path"] for item in phase.get("outputs", [])])


def _ids_from_text(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line.strip().split(",", 1)[0] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _records(root: Path, relative: str) -> list[dict[str, Any]]:
    path = root / relative
    return load_jsonl(path) if path.is_file() and path.stat().st_size else []


def _coverage_reconciliation(root: Path, reconciliation_id: str, assigned: list[str], completed: list[str], patterns: list[str]) -> dict[str, Any]:
    expected = set(filter(None, assigned))
    actual = set(filter(None, completed))
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    failures = [f"{item}: missing disposition or record" for item in missing] + [f"{item}: unassigned record" for item in unexpected]
    report = _report(root, f"reconcile:{reconciliation_id}", patterns, len(expected), len(expected & actual), failures)
    report["reconciliation_id"] = reconciliation_id
    return report


def run_reconciliation(root: Path, phase: dict[str, Any], reconciliation_id: str) -> dict[str, Any]:
    manifest_ids = [row.get("id", "") for row in _manifest(root)]
    if reconciliation_id == "input_classification":
        input_root = root / "00-inputs"
        assigned = [str(path.relative_to(root)) for path in sorted(input_root.rglob("*")) if path.is_file()]
        if not assigned:
            assigned = ["__none__"]
        return reconcile_records(
            reconciliation_id=reconciliation_id,
            assigned_ids=assigned,
            dispositions=_records(root, "tools/outputs/input-classification.jsonl"),
            root=root,
            input_patterns=["00-inputs/**", "tools/outputs/input-classification.jsonl", "00-scope.md"],
        )
    if reconciliation_id == "capture_sources":
        return reconcile_records(
            reconciliation_id=reconciliation_id,
            assigned_ids=manifest_ids,
            dispositions=_records(root, "tools/outputs/capture-dispositions.jsonl"),
            root=root,
            input_patterns=["01-sources/MANIFEST.csv", "tools/outputs/capture-dispositions.jsonl"],
            allow_one_to_many=True,
        )
    if reconciliation_id == "capture_assignments":
        return _rename(_ledger(root, {"capture"}), f"reconcile:{reconciliation_id}")
    if reconciliation_id == "source_extraction":
        return reconcile_records(
            reconciliation_id=reconciliation_id,
            assigned_ids=manifest_ids,
            dispositions=_records(root, "tools/outputs/extraction-dispositions.jsonl"),
            root=root,
            input_patterns=["01-sources/MANIFEST.csv", "tools/outputs/extraction-dispositions.jsonl"],
            allow_one_to_many=True,
        )
    if reconciliation_id == "candidate_filing":
        candidates = _records(root, "tools/candidates/all.jsonl")
        ids = [str(row.get("candidate_id", row.get("id", ""))) for row in candidates]
        return reconcile_records(
            reconciliation_id=reconciliation_id,
            assigned_ids=ids,
            dispositions=_records(root, "tools/outputs/filing-dispositions.jsonl"),
            root=root,
            input_patterns=["tools/candidates/all.jsonl", "tools/outputs/filing-dispositions.jsonl"],
            allow_one_to_many=True,
        )
    if reconciliation_id == "synthesis_assignments":
        return _rename(_ledger(root, {"synthesis"}), f"reconcile:{reconciliation_id}")
    if reconciliation_id == "cited_fact_verification":
        assigned = _ids_from_text(root / "tools/lists/cited-facts.txt")
        completed = [str(row.get("fact_id", "")) for row in _verification_records(root)]
        return _coverage_reconciliation(root, reconciliation_id, assigned, completed, ["tools/lists/cited-facts.txt", "tools/outputs/verification-verdicts.jsonl"])
    if reconciliation_id == "verification_corrections":
        assigned = [str(row.get("fact_id", "")) for row in _verification_records(root)]
        completed = [str(row.get("fact_id", row.get("input_id", ""))) for row in _records(root, "tools/outputs/verification-corrections.jsonl")]
        return _coverage_reconciliation(root, reconciliation_id, assigned, completed, ["tools/outputs/verification-verdicts.jsonl", "tools/outputs/verification-corrections.jsonl"])
    if reconciliation_id == "review_findings":
        assigned = [str(row.get("finding_id", "")) for row in _review_findings(root) if row.get("finding_id")]
        completed = [str(row.get("finding_id", row.get("input_id", ""))) for row in _records(root, "tools/outputs/review-decisions.jsonl")]
        return _coverage_reconciliation(root, reconciliation_id, assigned, completed, ["tools/outputs/review-findings-*.jsonl", "tools/outputs/review-decisions.jsonl"])
    if reconciliation_id == "final_cited_facts":
        assigned = sorted({str(fid) for _path, data in _citation_maps(root) for citation in data.get("citations", []) for fid in citation.get("facts", [])})
        model_path = root / DIAGRAM_MODEL_JSON
        if model_path.is_file() and model_path.stat().st_size:
            model = load_json(model_path)
            assigned = sorted(set(assigned) | {
                str(fact_id)
                for group in ("entities", "relationships")
                for record in model.get(group, [])
                for fact_id in record.get("fact_ids", [])
            })
        completed = [str(row.get("fact_id", "")) for row in _verification_records(root) if row.get("verdict") in {"confirmed", "corrected"}]
        return _coverage_reconciliation(root, reconciliation_id, assigned, completed, ["tools/outputs/citation-map-*.json", DIAGRAM_MODEL_JSON, "tools/outputs/verification-verdicts.jsonl"])
    if reconciliation_id == "citation_sources":
        assigned = sorted({str(note.get("source_id")) for _path, data in _citation_maps(root) for note in data.get("notes", []) if note.get("source_id")})
        model_path = root / DIAGRAM_MODEL_JSON
        if model_path.is_file() and model_path.stat().st_size:
            model = load_json(model_path)
            assigned = sorted(set(assigned) | {
                str(source_id)
                for group in ("entities", "relationships")
                for record in model.get(group, [])
                for source_id in record.get("source_ids", [])
            })
        completed = manifest_ids
        return _coverage_reconciliation(root, reconciliation_id, assigned, completed, ["tools/outputs/citation-map-*.json", DIAGRAM_MODEL_JSON, "01-sources/MANIFEST.csv"])
    if reconciliation_id == "visual_pages":
        expected, records = _visual_data(root)
        assigned = [str(page) for page in range(1, expected + 1)]
        completed = [str(row.get("page", "")) for row in records]
        return _coverage_reconciliation(root, reconciliation_id, assigned, completed, ["tools/outputs/render-metadata.json", "06-checks/visual-review.json"])
    if reconciliation_id == "visual_diagrams":
        review_path = root / "06-checks/visual-review.json"
        value = load_json(review_path) if review_path.is_file() and review_path.stat().st_size else {}
        assigned = [spec["id"] for spec in DIAGRAM_SPECS]
        completed = [str(row.get("diagram", "")) for row in value.get("diagrams", [])]
        return _coverage_reconciliation(root, reconciliation_id, assigned, completed, ["07-final-report/*.svg", "06-checks/visual-review.json"])
    return _rename(_ledger(root), f"reconcile:{reconciliation_id}")


def _task_failures(root: Path, phase_id: str) -> tuple[list[str], list[str]]:
    runtime_path = root / "tools/outputs/runtime.sqlite3"
    if runtime_path.is_file():
        from research_control.runtime import RuntimeStore

        with RuntimeStore(root) as store:
            store.invalidate_stale()
            tasks = store.tasks(phase=phase_id)
        failures = [
            f"task did not succeed: {task['task_id']} ({task['state']})"
            for task in tasks if task["state"] in {"failed", "blocked", "cancelled"}
        ]
        unknowns = [
            f"task incomplete: {task['task_id']} ({task['state']})"
            for task in tasks if task["state"] not in {"succeeded", "failed", "blocked", "cancelled"}
        ]
        if not tasks and phase_id not in {"bootstrap", "release_acceptance"}:
            unknowns.append(f"adaptive planner registered no work for phase {phase_id}")
        return failures, unknowns
    document = workflow(root / "WORKFLOW.yaml")
    tasks = document.get("execution_profiles", {}).get(phase_id, {}).get("tasks", [])
    ledger_path = root / document["global"]["ledger"]
    rows = load_jsonl(ledger_path) if ledger_path.is_file() and ledger_path.stat().st_size else []
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = str(row.get("task_id", ""))
        if row.get("phase") != phase_id:
            continue
        if task_id not in latest or int(row.get("attempt", 0)) > int(latest[task_id].get("attempt", 0)):
            latest[task_id] = row
    failures: list[str] = []
    unknowns: list[str] = []
    active_path = root / ACTIVE_PATH
    active = load_json(active_path) if active_path.is_file() else {}
    for task in tasks:
        task_id = f"{phase_id}.{task['id']}"
        if task_id in active:
            unknowns.append(f"task still active: {task_id}")
            continue
        row = latest.get(task_id)
        if row is None:
            unknowns.append(f"task never completed: {task_id}")
        elif row.get("status") != "succeeded":
            failures.append(f"task did not succeed: {task_id}")
        elif row.get("output_validation_status") != PASS:
            failures.append(f"task lacks local PASS: {task_id}")
    return failures, unknowns


def _operational_phase_report(root: Path, phase: dict[str, Any], reports: list[dict[str, Any]]) -> tuple[dict[str, Any], Path]:
    failures, unknowns = _task_failures(root, phase["id"])
    for report in reports:
        if report.get("status") == FAIL:
            failures.append(f"{report.get('checker')}: FAIL")
        elif report.get("status") != PASS:
            unknowns.append(f"{report.get('checker')}: {report.get('status')}")
    required_outputs = [item["path"] for item in phase.get("outputs", [])]
    _present, missing = require_nonempty_paths(root, required_outputs)
    if phase["id"] == "bootstrap" and "tools/outputs/worker-ledger.jsonl" in missing:
        ledger = root / "tools/outputs/worker-ledger.jsonl"
        if ledger.is_file():
            missing.remove("tools/outputs/worker-ledger.jsonl")
    unknowns.extend(f"phase output missing or empty: {item}" for item in missing)
    for review in phase.get("semantic_reviews", []):
        if not _paths(root, [review["path"]]):
            unknowns.append(f"semantic review missing or empty: {review['id']}")
    expected = len(reports) + len(required_outputs) + len(phase.get("semantic_reviews", []))
    checked = len(reports) + len(required_outputs) - len(missing) + len(phase.get("semantic_reviews", [])) - sum(
        1 for review in phase.get("semantic_reviews", []) if not _paths(root, [review["path"]])
    )
    report = _report(root, f"phase:{phase['id']}", phase.get("stale_if", []), expected, checked, failures, unknowns)
    path = root / "tools/outputs/gates" / f"phase-{phase['id']}.json"
    atomic_write_json(path, report)
    return report, path


def check_phase(
    root: Path,
    phase_id: str | None = None,
    update_state: bool = True,
) -> tuple[dict[str, Any], Path]:
    document = workflow(root / "WORKFLOW.yaml")
    state = load_state(root)
    if phase_id is None:
        phase_id = next(
            (phase["id"] for phase in document["phases"] if state["phases"][phase["id"]]["status"] != "complete"),
            None,
        )
    if phase_id is None:
        raise ValueError("all phases are complete")
    phase = find_phase(document, phase_id)
    if phase_id == "release_acceptance":
        raise ValueError("run `python3 -m research_control release` for release acceptance")
    if update_state:
        incomplete_dependencies = [
            dependency for dependency in phase.get("depends_on", [])
            if state["phases"][dependency]["status"] != "complete"
        ]
        if incomplete_dependencies:
            raise ValueError(f"phase dependencies are incomplete: {', '.join(incomplete_dependencies)}")

    reports: list[dict[str, Any]] = []
    engine_key = _validation_engine_key(root)
    for item in phase.get("validators", []):
        report = _cached_pass(root, item["report"], engine_key)
        if report is None:
            report = run_validator(root, phase, item["id"])
            report["cache_key"] = engine_key
            _write(root, item["report"], report)
        reports.append(report)
    for item in phase.get("reconciliations", []):
        report = _cached_pass(root, item["report"], engine_key)
        if report is None:
            report = run_reconciliation(root, phase, item["id"])
            report["cache_key"] = engine_key
            _write(root, item["report"], report)
        reports.append(report)
    if phase.get("gate"):
        report, path = check_phase_gate(root, phase_id, allow_completed_recheck=not update_state)
    else:
        report, path = _operational_phase_report(root, phase, reports)
    if update_state:
        set_phase_result(root, phase_id, report["status"], str(path.relative_to(root)))
    return report, path
