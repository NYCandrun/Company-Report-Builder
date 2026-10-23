# Refactor report

## Architecture

The refactor separates one 3,399-line mixed-concern prompt into four layers:

1. `RESEARCH_CONSTITUTION.md` explains the research, evidence, reasoning,
   writing, publication, independence, and completion principles that humans
   and reasoning models need to understand.
2. `WORKFLOW.yaml` is the one canonical executable phase contract. It preserves
   the real order: capture, facts, initial synthesis, cited-fact verification,
   corrected synthesis, independent review, company brief, publication checks,
   and release acceptance.
3. `prompts/` gives each worker only its role, bounded inputs, output contract,
   relevant principles, and completion criteria. It keeps writing,
   verification, skeptical review, citation review, and visual review in
   independent contexts.
4. `research_control/` enforces deterministic requirements with schemas,
   validators, reconciliations, phase gates, hashes, stale-result detection,
   concise reports, and exact-artifact release acceptance.

`WORKFLOW.yaml` uses JSON syntax, which is valid YAML 1.2. Python can therefore
parse it without a third-party package. The deterministic integrity job needs
no model credentials or external secrets.

The five assurance layers remain separate:

| assurance layer | primary policy | deterministic controls | semantic controls |
|---|---|---|---|
| Data integrity | Constitution fact/source record rules | Source and fact schemas, ID/path/tag/date validators | Duplicate and unusual-record audit |
| Evidence validity | Constitution evidence and receipt rules | Quote/location, source, date, tag, filing, and verification reconciliation | Exact support, source grade, speaker, and correction judgment |
| Reasoning quality | Constitution inference, currency, and synthesis rules | Fact-reference and review-finding accounting | Technical, devil's-advocate, insider, editor, currency, and fixer roles |
| Publication integrity | Constitution citation and reader-facing rules | Citation numbering, notes, links, exhibit mapping, writing, artifact, and page validators | Exact-claim citation review and full visual review |
| Execution integrity | Constitution completion rules | Ledger, assignment overlap, dispositions, counts, hashes, gates, staleness, and release manifest | Anomaly challenge only. Model opinion cannot override a failed check. |

The compatibility commands required by the source prompt now exist:

```bash
python3 tools/check_phase_gate.py --phase capture
python3 tools/check_phase_gate.py --phase facts
python3 tools/check_phase_gate.py --phase verification
python3 tools/check_phase_gate.py --phase review
python3 tools/check_phase_gate.py --phase final
python3 tools/reconcile_work.py --help
python3 tools/check_release.py
```

All control reports use `PASS`, `FAIL`, or `UNKNOWN`. Missing, empty,
malformed, crashed, stale, or under-counted checks become `UNKNOWN` and block.

## Preservation

The conservative inventory contains **1,732 normative or contract-bearing
records**. The parser deliberately over-preserves list and table entries that
inherit an imperative from their lead-in. This prevents terse field lists and
unusual defensive details from disappearing during consolidation.

| measure | count |
|---|---:|
| Atomic inventory rows | 1,732 |
| Rows marked `preserved` | 1,732 |
| Rows without a destination | 0 |
| README headings and subheadings | 202 |
| Heading migration entries | 202 |
| Explicitly removed requirements | 0 |
| Registered failure modes | 68 |

Inventory by assurance layer:

| layer | requirements |
|---|---:|
| Data integrity | 17 |
| Evidence validity | 488 |
| Reasoning quality | 219 |
| Publication integrity | 511 |
| Execution integrity | 497 |

Section 19 contributes 89 inventory rows, all classified under execution
integrity. Its worker ledger, immutable assignments, attempts, dispositions,
reconciliation, status semantics, counts, checker identity, hashes, gates,
staleness, release acceptance, exact artifacts, negative tests, bounded retry,
and concise-output rules all have explicit destinations.

`MIGRATION_MAP.md` maps every source heading and documents behavioral
equivalence. `REQUIREMENT_INVENTORY.csv` preserves exact README source text and
line location for each atomic record. The original README and historical prompt
files were not edited.

## Scar tissue

`FAILURE_REGISTRY.md` contains 68 stable invariants. The converted failure
classes are:

- **F001-F006, worker completeness:** false success, missing assigned work,
  overlapping slices, shared-state corruption, partial batches, and silent
  zero-fact results.
- **F007-F013, meaning and currentness:** unsupported citations, swapped
  statement/source pairings, incorrect dates, aims presented as shipped,
  services presented as product, inference presented as fact, and stale facts
  presented as current.
- **F014-F019, fail-closed acceptance:** post-check edits, checks that never ran,
  truncated validators, self-review, skipped pages, and release of bytes other
  than those checked.
- **F020-F030, data and evidence receipts:** duplicate IDs, missing local
  sources, weak date overlays, speaker misattribution, dropped caption words,
  duplicate extraction, filter misses, wrong quote/location, vague receipts,
  absolute absence claims, and wrong source grades.
- **F031-F038, fact and review propagation:** Grade-I leakage, model-based fact
  merging, hidden conflicts, lost candidates, undisposed findings, unapplied
  accepted fixes, newly cited unverified facts, and unpropagated corrections.
- **F039-F046, publication integrity:** duplicate citation numbers, incomplete
  notes, pooled exhibit citations, leaked repository internals, wrong deep
  links, design-broken citation placement, overflow, and unintended changes
  after targeted edits.
- **F047-F055, runtime boundaries:** access bypass, unbounded rate-limit retry,
  early downstream work, stale gates, erased failure history, full-batch retry,
  undeclared dependencies, font-license violations, and renaming cited files.
- **F056-F065, special safeguards:** date-kind conflation, unsupported current
  prices, redirects treated as retirement, competitive evidence asymmetry,
  phase-number confusion, collapsed independent roles, shared-manifest writes,
  ambiguous worker assignments, fault injection in the real corpus, and
  irreproducible counts.
- **F066-F068, provenance and exceptions:** research reports used as receipts,
  empty check output treated as clean, and silent exception-based weakening.

Executable regressions cover the source prompt's six fact faults: duplicate,
conflict, wrong quote, wrong location, wrong date, and overstatement. They also
cover all six citation fault injections and the Section 19 failures: missing
worker output, missing disposition, overlapping assignment, absent/truncated
validation, premature state completion, modified final artifact, and missing
visual evidence. Additional semantic-only fixtures remain explicitly labeled
as semantic or planned in the failure registry because code cannot establish
their meaning.

## Consolidations

No scope or control was removed. Material repeated prose was consolidated as
follows:

| repeated material | classification | result |
|---|---|---|
| Phase gates in sections 8, 17, and 19 | Policy plus enforcement | One workflow graph and one phase-gate evaluator. The constitution retains the principle. |
| Exact citation support in sections 4, 15, 16, and 17 | Same invariant at different assurance layers | Fact validity and final sentence support remain separate. Structural code and independent claim review both remain. |
| Reader-facing ban on fact IDs, paths, and internals | Accidental prose duplication | One constitution rule, publication validator, and visual/release checks. |
| Worker bounds and ownership in sections -1, 8, and 19 | Policy plus enforcement | Runtime prompt plus worker schema, ledger, overlap detection, and reconciliation. |
| Planted tests in sections 11, 16, and 19 | Intentional defense in depth | One runner with five distinct categories. The categories are not merged. |
| Currency rules across evidence, synthesis, publication, and done criteria | Same invariant at different assurance layers | One policy with deterministic age/date checks and a separate flagged-row reasoning review. |
| Full-page visual review repeated in final checks and completion | Policy plus enforcement | Page reconciliation proves coverage. Independent review judges readability. |
| Completion language in sections 17, 18, and 19 | Amendment-strengthened duplication | Release acceptance is authoritative. The short run report is never completion evidence. |

## Semantic controls retained

The following remain explicit model judgments because deterministic code cannot
reliably establish them:

- mapping an unfamiliar company, selecting its flagship, and justifying the
  competitor set;
- classifying ambiguous source authorship and first-hand status;
- deciding whether a quote semantically supports a claim;
- resolving ambiguous speaker labels and attribution;
- determining whether wording overstates `can`, `aim`, `some`, `beta`, or
  similar language;
- distinguishing product capability from employee-delivered service;
- deciding whether two differently worded sources conflict or describe
  compatible states;
- scoping absence claims to the actual search record;
- determining supersession, retirement, renaming, title changes, and current
  status from flagged evidence;
- interpreting product architecture and the support for diagram arrows;
- producing competitive scores and disclosures under an evidence-asymmetry
  caveat;
- challenging strategic direction with plausible alternatives;
- judging what sounds naive, stale, incomplete, or internally implausible;
- applying, partially applying, or rejecting review findings with reasons;
- writing the company brief and neutral open questions without exceeding facts;
- judging whether the exact final phrase, table cell, label, or exhibit is
  supported by its citation;
- judging page readability, hierarchy, spacing, professionalism, and design
  quality;
- evaluating font licensing and access-policy ambiguity.

The workflow preserves independent contexts for writing versus verification,
synthesis versus challenge, citation placement versus claim review, and page
authoring versus visual review.

## Deterministic controls moved to software

The reusable package now enforces or provides canonical machinery for:

- source, fact, worker, disposition, validation, gate, review-finding, and
  release schemas;
- source IDs, grades, required local files, and captured dates;
- fact IDs, source references, required fields, tags, duplicate candidates,
  declared conflicts, date agreement, quote presence, exact-location presence,
  and overstatement-risk flags;
- prohibited writing tokens;
- immutable assignment accounting, exclusive-input overlap, output-path
  overlap, attempt history, terminal state, required outputs, local validation,
  and output hashes;
- source-to-capture, source-to-extraction, candidate-to-fact,
  fact-to-verification, finding-to-decision, citation-to-note, and
  page-to-visual-record reconciliation;
- validation report shape, checker version, expected/checked count, failure
  count, exception count, timestamp, and input hashes;
- five named phase gates sourced solely from `WORKFLOW.yaml`;
- stale validation and stale gate detection after relevant inputs change;
- citation number order, source-number uniqueness, note use, source coverage,
  canonical page links, and Markdown-to-output fact placement;
- element-level exhibit fact mapping and complete page-review accounting;
- final artifact existence and binding to validation hashes;
- independent release acceptance and release-manifest creation only on `PASS`;
- five categorized negative-test suites and a credential-free CI job.

The CLI prints only status, expected and checked counts, failure/exception
counts, the report path, and bounded failing IDs. Full records stay on disk.

## Unresolved issues

These do not weaken the refactor, but they must be addressed before it replaces
the current master prompt in production:

1. The completed historical AirOps run predates Section 19. It has no worker
   ledger, structured reconciliations, current gate reports, or release
   manifest. This refactor does not retroactively claim that run passed the new
   control plane.
2. Many existing one-off scripts write prose or Markdown rather than the common
   validation schema. Their useful domain logic remains, but adapters must add
   checker version, hashes, expected/checked counts, and explicit status.
3. Historical artifacts use British file names such as `organisation.md`.
   Existing user files were preserved. A new run should use American names;
   migration of the historical corpus needs explicit aliases or a separate
   approved rename plan.
4. Semantic review files are still human-readable Markdown in the prior run.
   New runs need structured finding/disposition companions so reconciliation
   can prove every row was decided without weakening the readable reports.
5. Capture- and build-specific legacy tools have not all been rewritten into
   the package. They should emit or be wrapped by the new validation contract,
   not be deleted solely for architectural neatness.
6. The current research artifacts are a useful shadow-run fixture but are too
   large for the fast unit suite. An integration workflow should exercise a
   representative subset before a production cutover.
7. The README remains the historical source of truth. This change intentionally
   does not replace it with the refactored entry point.

## Recommended next steps

1. Add thin structured-report adapters to the existing manifest, layer-1,
   citation, exhibit, design, and PDF tools. Keep their current domain behavior.
2. Instrument the orchestrator to register worker attempts before launch and to
   write immutable input/disposition files for every bounded work list.
3. Emit structured review findings and decisions alongside the existing
   Markdown review reports.
4. Run the new control plane in shadow mode against the AirOps corpus. Record
   every mismatch between legacy `Done` claims and deterministic evidence.
5. Repair only the mismatches or adapters exposed by that shadow run, then run
   all five gates and release acceptance on a fresh end-to-end research run.
6. Compare research scope, fact coverage, synthesis order, semantic review
   findings, publication checks, and final artifacts against the original
   prompt requirement by requirement.
7. Only after that comparison passes, propose an explicit small entry prompt
   that points to the constitution, workflow, and role prompt for the assigned
   task. Preserve README as versioned historical policy rather than deleting
   it.

## Verification performed

- 25 unit tests pass.
- All five categorized suites pass: data integrity, evidence pipeline,
  citation integrity, execution integrity, and release integrity.
- The traceability audit passes with 1,732 inventory rows, 202 mapped headings,
  and 68 unique failure IDs.
- `WORKFLOW.yaml` and all eight schemas parse as valid JSON.
- The Python control package compiles without syntax errors.
- Mechanical writing checks pass for the constitution and scoped prompts.
- The GitHub Actions workflow runs the declarative, traceability, categorized,
  and full-discovery checks without model secrets.
