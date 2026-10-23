# Refactor report

## Version 2.3 efficiency revision

- Research discovery and brand discovery still start concurrently and retain
  separate evidence authority, but now share a SQLite URL lead ledger and
  content-addressed public-response cache. Simultaneous requests coordinate so
  one worker normally fetches while the other reuses the immutable object.
- Task packets carry an optional advisory model tier. Hosts with routing can
  reserve stronger reasoning for synthesis, verification, review, and modeling;
  hosts without routing use the available session model without blocking.
- Publication rendering reuses unchanged HTML, PDF, and page previews. Visual
  review is scoped by current artifact hashes, with complete accounting and
  reuse permitted only for prior clean records bound to identical hashes.
- Passing deterministic validations and reconciliations are skipped only when
  both their recorded input hashes and the validation-engine hash are current.

## Version 2.2 brand-guide integration

One independent brand-guide packet now starts with adaptive capture and runs in
parallel with source discovery. It produces final HTML/PDF guides plus a small
audit folder. The existing diagram builder reads the guide only for
presentation, records a concise style map, and retains the separately validated
architecture model as its sole factual source. The existing visual-review gate
now covers guide desktop/mobile views, every guide PDF page, standalone 165 mm
diagrams, and their placement in the report. No separate style-agent phase or
hash-binding subsystem was added.

## Version 2.1 publication revision

The original one-page summary contract is deliberately superseded. The
research scope, evidence controls, and company brief remain; the one-page
Markdown/HTML/PDF and second citation sequence are replaced by an auditable
model registry, four editable SVG architecture diagrams, captions, exact
title/subtitle checks, model-to-evidence bindings, and one visual-review record
per diagram at 165 mm. The preserved legacy prompt and requirement inventory
remain historical traceability inputs rather than the current output contract.

## Architecture

The operational refactor separates one 3,399-line mixed-concern prompt into
five layers:

1. `README.md` is the URL-only launcher and run loop for a coding agent.
2. `RESEARCH_CONSTITUTION.md` explains the research, evidence, reasoning,
   writing, publication, independence, and completion principles that humans
   and reasoning models need to understand.
3. `WORKFLOW.yaml` is the canonical executable phase and task contract. It preserves
   the real order: capture, facts, initial synthesis, cited-fact verification,
   corrected synthesis, independent review, company brief, gated architecture
   modeling and diagram build, publication checks, and release acceptance.
4. `prompts/` gives each worker only its role, bounded inputs, output contract,
   relevant principles, and completion criteria. It keeps writing,
   verification, skeptical review, citation review, and visual review in
   independent contexts.
5. `research_control/` initializes runs and operates a SQLite-backed adaptive
   scheduler. It discovers to per-channel saturation, plans per-source capture
   and token-sized extraction work, leases and recovers tasks, merges isolated
   parts through single-writer reducers, renders final artifacts, and enforces
   schemas, validators, reconciliations, phase gates, hashes, stale-result
   propagation, and exact-artifact release acceptance.

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
equivalence. `REQUIREMENT_INVENTORY.csv` preserves exact original-README source
text and line location for each atomic record. The byte-for-byte source prompt
is preserved at `docs/legacy-prompt.md`; normal workers never load it.

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
- six categorized negative-test suites and a credential-free CI job.

Gate reporters print only status, expected and checked counts,
failure/exception counts, the report path, and bounded failing IDs. Scheduler
commands additionally return machine-readable work and state summaries. Full
research records stay on disk.

## Operational status and boundaries

The repository now supports the intended clean-room interaction: copy the
template, give a supported coding agent one public company URL, and tell it to
follow `README.md`. The agent uses `research_control` to initialize and resume
the run, request permitted task packets, record attempts, run phase checks,
render the company brief, build four editable architecture diagrams from a
validated evidence model, and perform release acceptance.

The runner now supplies the durable scheduler and first-party public-web
frontier. It does not pretend that a standard-library HTTP client can replace
model judgment or host-native browser, search, PDF, audio, video,
transcription, and visual-inspection tools. Instead, the planner issues bounded
channel and source packets for those adapters, records their receipts, and
refuses to treat access limits as complete coverage. The built-in capture
helper handles ordinary public pages conservatively and rejects non-public
network targets. The renderer prefers a local CSS-capable engine and PDF
rasterizer when present, with deterministic PDF and SVG-preview fallbacks.

The historical AirOps corpus predates this operational ledger and release
manifest. It remains useful for a future live shadow comparison, but this
refactor does not retroactively certify that historical run.

## Recommended production follow-up

1. Run the launcher against two unrelated live companies in the supported agent
   runtime, including one media-heavy site.
2. Record access, transcription, and rendering exceptions exposed by those
   runs as new stable failure fixtures rather than new monolithic prose.
3. Add optional direct CLI adapters for preferred PDF, audio, video, browser,
   and agent-host tools where they materially improve receipts; the portable
   packet protocol remains the fallback.
4. Compare the first live results against the original prompt requirement by
   requirement and retain the generated release manifests.

## Verification performed

- 37 unit and operational tests pass, including clean-room initialization,
  interruption/retry behavior, publication rendering, private-network capture
  rejection, discovery saturation, corpus-sized task planning, host limits,
  stale propagation, and a synthetic URL-to-release lifecycle.
- All six categorized suites pass: adaptive runtime, data integrity, evidence
  pipeline, citation integrity, execution integrity, and release integrity.
- The traceability audit passes with 1,732 inventory rows, 202 mapped headings,
  and 68 unique failure IDs.
- `WORKFLOW.yaml` and all schemas parse as valid JSON.
- The Python control package compiles without syntax errors.
- Mechanical writing checks pass for the constitution and scoped prompts.
- The GitHub Actions workflow runs the launcher preflight, declarative,
  traceability, categorized, clean-room, and full-discovery checks without
  model secrets.
