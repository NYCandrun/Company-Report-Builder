#!/usr/bin/env python3
"""Generate a complete heading-level migration map for the README prompt."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "README.md"
OUTPUT = ROOT / "MIGRATION_MAP.md"


def esc(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def family(path: str) -> str:
    # The source uses inconsistent Markdown heading depths for sections 16-19,
    # so the last numbered heading is the effective family.
    matches = re.findall(r"(?:^| > )(-?\d+)(?:\.|\b)", path)
    return matches[-1] if matches else "intro"


def mapping(path: str) -> dict[str, str]:
    group = family(path)
    low = path.lower()
    base = {
        "destination": "RESEARCH_CONSTITUTION.md; WORKFLOW.yaml",
        "wording": "Principle retained; repeated procedure wording consolidated.",
        "software": "Deterministic portions use the reusable control package.",
        "model": "Only reasoning-relevant instructions remain model-facing.",
        "schema": "No",
        "workflow": "Yes",
        "test": "Where a deterministic invalid state can be planted.",
        "consolidation": "Policy plus enforcement",
        "rationale": "The readable invariant is paired with one canonical executable contract.",
    }
    if group == "intro":
        base.update(destination="RESEARCH_CONSTITUTION.md; prompts/core/runtime.md; WORKFLOW.yaml", model="Yes: bounded runtime principles.")
    elif group == "-1":
        base.update(destination="RESEARCH_CONSTITUTION.md §Execution; WORKFLOW.yaml bootstrap; prompts/core/runtime.md; research_control/schemas/worker.schema.json", schema="Worker/runtime records", model="Yes: ownership and safe runtime behavior.")
    elif group == "0":
        base.update(destination="RESEARCH_CONSTITUTION.md §Writing; prompts/core/writing.md; research_control/validators/writing_rules.py; WORKFLOW.yaml", software="Mechanical spelling/token rules are validators; usage remains reviewed.", model="Yes: American usage and quote exceptions.")
    elif group == "1":
        base.update(destination="RESEARCH_CONSTITUTION.md §Purpose and deliverables; prompts/phases/brief-writing.md; WORKFLOW.yaml", software="Required artifact names and forbidden framing are validated.", model="Yes: audience, framing, and research goal.")
    elif group == "2":
        base.update(destination="RESEARCH_CONSTITUTION.md §Scope and evidence; WORKFLOW.yaml scope/capture contracts; prompts/phases/capture.md", software="Required input dispositions and paths reconcile.", model="Yes: interpret user direction and classify inputs.")
    elif group == "3":
        base.update(destination="RESEARCH_CONSTITUTION.md §Scope; WORKFLOW.yaml capture parameters; prompts/phases/capture.md", software="Caps, required channels, and blocked dispositions are checked where deterministic.", model="Yes: discover relevance within fixed scope.")
    elif group == "4":
        base.update(destination="RESEARCH_CONSTITUTION.md §Evidence; prompts/core/evidence.md; research_control/validators/{sources,facts,dates,tags,quotes}.py", software="Record shape, IDs, dates, tags, and quote locations are validated.", model="Yes: support, attribution, inference, absence, and grading judgments.", schema="source.schema.json; fact.schema.json", consolidation="Same invariant at different assurance layers")
    elif group == "5":
        base.update(destination="RESEARCH_CONSTITUTION.md §Writing; prompts/core/writing.md; research_control/validators/writing_rules.py", software="Forbidden tokens and mechanical rules move to code.", model="Yes: clarity rules that require language judgment.", workflow="Validator required by authoring phases")
    elif group == "6":
        base.update(destination="RESEARCH_CONSTITUTION.md §Currency; prompts/core/evidence.md; research_control/validators/dates.py; WORKFLOW.yaml currency review", software="Age thresholds and required fields are deterministic.", model="Yes: supersession and current-status interpretation.")
    elif group == "7":
        base.update(destination="WORKFLOW.yaml artifact contracts; prompts/core/runtime.md; research_control/schemas/", software="Required paths, manifest fields, and naming constraints are machine checked.", model="Yes: capture-method guidance.", schema="source and artifact contracts")
    elif group == "8":
        base.update(destination="WORKFLOW.yaml orchestration and dependencies; prompts/core/runtime.md; research_control/schemas/worker.schema.json; research_control/reconciliation/assignments.py", software="Assignments, output ownership, counts, ledger state, retries, and gates are executable.", model="Yes: bounded task behavior and status reporting.", schema="worker.schema.json; disposition.schema.json", consolidation="Policy plus enforcement")
    elif group == "9":
        base.update(destination="WORKFLOW.yaml phase `scope`; prompts/phases/capture.md", software="Required `00-scope.md` existence and review evidence are gated.", model="Yes: high-reasoning source-map judgment.")
    elif group == "10":
        base.update(destination="WORKFLOW.yaml phase `capture`; prompts/phases/capture.md; research_control/validators/sources.py; research_control/reconciliation/sources.py", software="Manifest, local files, IDs, dates, assignments, and coverage reconcile.", model="Yes: source discovery, selection, and access-policy judgment.", schema="source.schema.json; disposition.schema.json")
    elif group == "11":
        base.update(destination="WORKFLOW.yaml phase `facts`; prompts/phases/extraction.md; research_control/validators/{facts,dates,tags,quotes}.py; research_control/reconciliation/{extraction,facts}.py", software="Fact records, quote locations, tags, dates, conflicts, and candidate dispositions are checked.", model="Yes: extraction, canonical-copy spot checks, and claim support.", schema="fact.schema.json; disposition.schema.json")
    elif group == "12":
        base.update(destination="WORKFLOW.yaml phases `initial_synthesis`, `verification`, and `corrected_synthesis`; prompts/phases/verification.md; research_control/reconciliation/verification.py", software="Cited facts reconcile to verdicts; corrections stale dependent outputs.", model="Yes: quote support, speaker, overstatement, and correction judgment.", consolidation="Intentional phase-order clarification")
    elif group == "13":
        base.update(destination="WORKFLOW.yaml phases `initial_synthesis` and `corrected_synthesis`; prompts/phases/synthesis.md", software="Required inputs, outputs, fact references, and sequencing are gated.", model="Yes: product structure, competitive judgment, and synthesis.")
    elif group == "14":
        base.update(destination="WORKFLOW.yaml phase `review`; prompts/phases/review-*.md and fixer.md; research_control/reconciliation/reviews.py", software="Required independent reviews and finding dispositions reconcile.", model="Yes: all four semantic reviewer roles and fix decisions.", schema="review-finding.schema.json", consolidation="Intentional defense in depth")
    elif group == "15":
        base.update(destination="RESEARCH_CONSTITUTION.md §Publication; WORKFLOW.yaml phases `company_brief` and `publication_checks`; prompts/phases/{brief-writing,citation-review,visual-review}.md; research_control/validators/{citations,exhibits,visual_records}.py", software="Artifact contracts, citations, exhibit mappings, text rules, and page records are validated.", model="Yes: writing, exact-claim citation review, design, and full visual review.", schema="citation/exhibit records within validation contracts", consolidation="Same invariant at different assurance layers")
    elif group == "16":
        base.update(destination="WORKFLOW.yaml phase `publication_checks`; prompts/phases/{citation-review,visual-review,fixer}.md; research_control/validators/{citations,exhibits,visual_records}.py", software="Numbering, notes, receipts, mappings, negative tests, and page accounting run deterministically.", model="Yes: exact-claim and reader-quality reviews remain independent.", consolidation="Intentional defense in depth")
    elif group == "17":
        base.update(destination="WORKFLOW.yaml final completion conditions; research_control/gates/release.py", software="Definition of done is evaluated fail-closed from current evidence.", model="No completion authority; semantic reports remain required inputs.", schema="gate.schema.json; release.schema.json")
    elif group == "18":
        base.update(destination="WORKFLOW.yaml release reporting; research_control/reporting/summaries.py", software="Counts and statuses are produced from manifests and machine evidence.", model="Yes: uncertainty explanations and short narrative report.", schema="release.schema.json")
    elif group == "19":
        base.update(destination="WORKFLOW.yaml canonical gates; research_control/{schemas,reconciliation,gates,hashing,reporting}; prompts/core/runtime.md", wording="Conceptual invariant retained; low-level control logic moved to code.", software="Section 19 becomes executable ledger, reconciliation, validation, gate, staleness, and release logic.", model="Only anomaly challenge and concise repair context; never completion authority.", schema="worker, disposition, validation, gate, review-finding, release", test="Execution- and release-integrity regression suites", consolidation="Policy plus enforcement")

    if "planted" in low or "tests" in low:
        base["test"] = "Yes; invalid states are planted only in disposable fixtures."
    if "visual" in low:
        base["model"] = "Yes: every page remains visually reviewed; code only checks measurable/accounting properties."
    if "claim review" in low:
        base["model"] = "Yes: two independent contexts judge exact semantic support."
    return base


def headings() -> list[tuple[int, int, str]]:
    stack: dict[int, str] = {}
    result: list[tuple[int, int, str]] = []
    for number, line in enumerate(SOURCE.read_text(encoding="utf-8").splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        stack[level] = title
        for old in list(stack):
            if old > level:
                del stack[old]
        result.append((number, level, " > ".join(stack[key] for key in sorted(stack))))
    return result


def build() -> int:
    rows = headings()
    lines = [
        "# Migration map",
        "",
        "`README.md` on `main` is the only normative source for this refactor. The historical prompt files are retained unchanged and are not merged into the effective requirements.",
        "",
        "Every README heading is represented below. Atomic requirements under each heading are traced separately in `REQUIREMENT_INVENTORY.csv`.",
        "",
        "| source | destination | wording retained | software enforcement | model-facing | schema | workflow | regression test | consolidation | equivalence rationale |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for number, _level, path in rows:
        move = mapping(path)
        lines.append("| " + " | ".join(esc(x) for x in (
            f"README.md:{number} — {path}", move["destination"], move["wording"],
            move["software"], move["model"], move["schema"], move["workflow"],
            move["test"], move["consolidation"], move["rationale"],
        )) + " |")

    lines.extend([
        "",
        "## Deliberate consolidations",
        "",
        "| repeated rule | classification | canonical policy | canonical enforcement | why no protection is lost |",
        "|---|---|---|---|---|",
        "| Phase gates in sections 8, 17, and 19 | Policy plus enforcement | Constitution lifecycle and `WORKFLOW.yaml` dependencies | `research_control.gates.phase_gate` | Prose explains the invariant; one executable graph decides status. |",
        "| Exact citation support in sections 4, 15, 16, and 17 | Same invariant at different assurance layers | Constitution evidence and publication principles | Structural citation validators plus independent claim review | Fact support and final sentence support remain separate checks. |",
        "| No reader-facing fact IDs, paths, or build internals in sections 15 and 17 | Accidental prose duplication | Constitution publication boundary | Publication text validator and final visual review | One policy is enforced at build and release boundaries. |",
        "| Worker boundedness and ownership in sections -1, 8, and 19 | Policy plus enforcement | Runtime core prompt | Worker schema, ledger validator, assignment reconciliation | Workers still see the behavioral rule; code proves completion. |",
        "| Planted tests in sections 11, 16, and 19 | Intentional defense in depth | Test taxonomy in `WORKFLOW.yaml` | Separate data, evidence, citation, execution, and release suites | Similar fixture mechanics do not collapse distinct control systems. |",
        "| Currentness rules in sections 4, 6, 13, 15, and 17 | Same invariant at different assurance layers | Constitution currency policy | Date validator plus flagged-row semantic review and release requirements | Storage age, synthesis interpretation, and published wording remain distinct. |",
        "| Full-page visual inspection in sections 16, 17, and 19 | Policy plus enforcement | Constitution publication principle | Page reconciliation plus independent visual review records | Page accounting is deterministic; readability is not. |",
        "| Completion reporting in sections 17, 18, and 19 | Accidental duplication plus stronger amendment | Constitution definition of completion | Release checker and release manifest | Section 19's fail-closed evidence takes precedence over prose assertions. |",
        "",
        "## Source and implementation discrepancies",
        "",
        "1. `README.md` is 3,399 lines and includes Section 19. `prompt/PROMPT.md` and `prompt/revised_prompt.md` are shorter historical versions and are not identical to README, despite the old run's prompt-file mirroring rule.",
        "2. `WORKFLOW_STATE.md` names `prompt/PROMPT.md` as the prior run's governing prompt and also records later completion. That is historical run evidence, not authority for this refactor.",
        "3. The prior run marks phases complete without Section 19 gate reports, a worker ledger, reconciliations, or release acceptance. This refactor does not retroactively claim that the historical run passed the new control plane.",
        "4. Historical files use British spellings such as `organisation.md`, while current README requires American spelling. Existing user artifacts remain untouched; new contracts use American names and may declare legacy aliases explicitly.",
        "5. Existing one-off validators generally emit text/Markdown and do not all record checker version, expected and checked counts, input hashes, or `PASS`/`FAIL`/`UNKNOWN`. They remain useful domain checks but require structured adapters before satisfying gates.",
        "6. Existing source, fact, citation, and visual scripts are not governed by one declarative workflow and have no common validation schema. `WORKFLOW.yaml` becomes the canonical gate definition without deleting those historical tools.",
        "7. README's conceptual Phase 3 heading precedes Phase 4, while its expensive cited-fact verification runs after initial synthesis. The workflow names `initial_synthesis`, `verification`, and `corrected_synthesis` to preserve actual dependency order.",
        "8. README tells a fresh run to mirror README and `prompt/revised_prompt.md`; this refactor preserves all historical prompt files and does not replace the source prompt. Replacement is a future explicit migration step.",
        "",
        "## Removed requirements",
        "",
        "None. No README requirement is intentionally removed. Historical implementation details may be wrapped, adapted, or superseded only where the inventory and this map retain the protected behavior.",
    ])
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    print(f"Wrote {build()} heading migrations to {OUTPUT.relative_to(ROOT)}")
