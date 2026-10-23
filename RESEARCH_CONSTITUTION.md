# Research constitution

## Status and authority

This constitution is the readable policy layer for the company-research
system. This constitution and `WORKFLOW.yaml` are the policy and executable
sources of truth. `README.md` is the operational launcher. The
`research_control` package enforces deterministic parts of the contract, and
bounded worker prompts apply the relevant portions of this constitution to
each task.

If policy and executable behavior appear to disagree, stop the affected phase,
record the discrepancy, and repair the weaker side. Never silently narrow the
research scope or weaken an evidence, review, publication, or execution rule.

## Purpose

Build an onboarding-quality company brief from a product-marketing point of
view without presuming that the reader works at the company. The research must
explain:

- what the company sells and how the products fit together;
- packaging, pricing signals, and how a buyer starts;
- customers, proof, and the authorship of that proof;
- positioning and how it has changed;
- stated direction, actual launches, and unresolved roadmap questions;
- people and organization signals;
- competitors, evidence asymmetries, and defensible comparisons;
- dependencies around the products in focus;
- evidence limits and the questions the public record cannot answer.

The repository has three durable layers:

1. Captured sources, saved with provenance and dates.
2. A fact store in which every fact has a verbatim receipt and exact location.
3. Sense-making built only on the fact store, culminating in the company brief
   and an auditable four-diagram architecture package.

A separate public-evidence brand branch runs concurrently with capture and
produces the release brand guide. It may shape typography, color, spacing,
diagram styling, and report presentation, but it never supplies company or
architecture facts.

The brand and research branches may share a run-local URL lead ledger and
content-addressed cache to avoid fetching identical public bytes twice. This is
transport reuse only. A ledger entry is not evidence, and each branch must
independently admit and record any material it uses under its own evidence
contract. Neither branch waits for the other, and shared discovery never
merges their responsibilities.

The repository must be reproducible from the effective prompt, company URL,
user-provided inputs, captured public sources, and dependencies created or
declared during the run. Incidental local files or conventions are not valid
dependencies.

## Scope

### Company record

Map the company's canonical site and relevant public surfaces, including
subdomains, docs, help, academy, developer resources, newsroom or blog,
careers or ATS, status, public code, and package surfaces. Read every file in
`00-inputs/` before scope is finalized.

User direction establishes products in focus and important questions. If it is
absent, cover products evenly and give the most depth to the flagship selected
from company evidence. Every synthesis and brief-writing context must know the
flagship and why it was selected.

The company-site sweep covers every discoverable company sitemap, including
non-English docs and relevant microsites, for PDF and embedded-media discovery.
High-value pages are captured in full. Every company-hosted PDF is downloaded
with a text copy and page boundaries. Every long-form company-channel or
company-site video is in scope for transcription. YouTube Shorts are not.

Competitor research covers five to eight justified competitors plus a watch
list unless user direction says otherwise. Public competitor docs are captured
only for the competing product in a suite, normally capped around 400 pages per
competitor with exclusions logged. Competitor videos are out except those the
company embeds. Already captured and verified evidence is never discarded only
because later scope narrows.

No dedicated secondary-source maximization is required. Relevant secondary
sources encountered during normal research are retained, and the final brief
states when first-hand third-party evidence is thin or customer proof is mostly
company reported.

### Inputs

User-provided direction may set focus, context, and questions. User-provided
source files are copied into the captured-source layer with `provided` as the
method while originals remain unchanged.

A provided research report is a scoping checklist, not the final receipt for a
fact when its underlying source can be captured. Its products, launches, dates,
people, customers, competitors, and prices become confirmation leads. Its
conflicts and caveats become priority checks. Its cited links enter the capture
work list.

Facts supplied directly by the user are preserved verbatim as a Grade-I source
and as facts with verdict `confirmed (user-provided)`. Do not independently
check them unless the user asks.

### Public-access boundary

Use only public access. Never use logins, fake accounts, paywall workarounds, or
bot-challenge bypasses. Follow `robots.txt`, back off when rate limited, and log
failed access instead of routing around it. Try the Wayback Machine once. If
the network path is blocked or repeatedly fails, stop that channel and use
dated first-party sources for messaging history.

## Evidence

### Source grades

- **P:** The company's own site, docs, API specifications, code, filings,
  releases, job postings, and statements by its people in talks or podcasts.
- **S:** A named third party with first-hand knowledge, such as a customer's or
  partner's own announcement, procurement record, customer filing, or similar
  direct record.
- **T:** Trade press, analysts, review sites, reprints, aggregators, and
  competitors describing the company.
- **I:** Non-public material supplied by the user.

A customer story hosted and authored by the company is P even when it quotes a
customer. A reprint is not silently presented as the original publisher.

### Receipt for every fact

Every fact has:

- a verbatim quote;
- a source ID resolving to a manifest row;
- an exact location in the captured source;
- a source date;
- a grade;
- an `about` tag;
- a `said_by` tag.

A file path, `count script`, `many pages`, or `website` is not a receipt.
Locations use line, page, timestamp, JSON field, or API-field precision. Counts
come from deterministic scripts with saved, reproducible inputs and output.

Quote rather than paraphrase when wording matters. Shortening must not change
meaning. Extraction checks the quote against the original capture, not merely
an intermediate extract.

### Attribution and speaker identity

Auto-captions and machine transcripts do not establish speaker identity.
Attribute a person only when the source establishes it, such as through an
introduction, direct address, or reliable labels. Otherwise use a source-level
description such as `a speaker in the <title> webinar`. Mark inferred speakers
`(probable)` and unresolved ones `Speaker unclear`. Preserve known
transcription errors for names, products, competitors, and people. A fact that
depends on uncertain transcription remains inference or unresolved.

The `about` tag names the company the fact concerns, `Market`, or `X (per Y)`
when one organization describes another. `said_by` names the organization
responsible for the source. A person's name belongs in notes unless a separate
schema field requires it.

### Claim discipline

A claim says no more than its receipt:

- an aim is not an achievement;
- `can` is not `does`;
- `some` is not `all`;
- `up to` is not typical performance;
- beta is not general availability;
- a job posting is not a hire;
- employee-delivered work is not automatically product capability.

Every inference begins `My inference:` and names the facts supporting it.
Strategic interpretations stay separate from stated aims and shipped product.
Competitive `ahead`, `level`, or `behind` judgments remain explicit inference
under a predefined rubric.

Absence claims are scoped to the sources searched. Incomplete coverage never
supports an absolute negative.

Contradictions are retained rather than harmonized. Conflicting numbers,
prices, percentages, dates, limits, and titles show both evidence trails and
dates. Equivalent numerical phrasings may be normalized, but disagreement is
not resolved merely by counting sources.

### Citation precision

A citation supports the exact words beside it. Final publication integrity is
separate from fact validity: a valid fact can still be paired with the wrong
sentence, cell, label, or source number. Reader-facing wording receives an
independent exact-claim review after structural checks.

Every final citation traces through a fact row to captured evidence. Never cite
a captured source directly in the brief without a fact row. Every newly added
fact receives the same receipt checks and, when cited, the same model
verification as earlier facts.

## Dates and currency

Published date and last-modified date are separate fields. Prefer publication
evidence in this order: JSON-LD `datePublished`, article metadata, `<time>`,
YouTube upload date, podcast `pubDate`, PDF creation or printed date,
press-release dateline, ATS posting date, and date printed beside the title.

Do not use site-wide deploy timestamps, homepage metadata, pricing-page
modification metadata, or a shallow clone timestamp as publication evidence.
For recorded events, use the live-event date when known and retain upload date
as a note. A weak date overlay never overwrites stronger evidence.

Facts whose latest evidence is within the last quarter before the research date
may be stated plainly as current. Older current-state claims use `as of
<date>`. Flagged facts use `last confirmed <date>` or `possibly retired` and
are never presented plainly as current.

Track first seen, last seen, supersession, current value, and latest evidence
for titles, plans, prices, limits, products, module names, integrations, and
positioning lines. Flag people with role evidence older than six months or
missing from current people pages, and prices, plans, limits, or features with
evidence older than roughly three months. Also flag deprecated, sunset,
removed, replaced, renamed, no-longer-present, and redirected items.

Only a dedicated reasoning review decides flagged currency rows and proposed
supersessions. A redirect is a page change, not retirement proof. Shared names,
one-off show-note titles, simultaneously existing plans, and third-party
conflicts do not automatically establish a change. Never state a company dollar
price as current unless the company publishes it.

## Writing

Write authored material in plain American English. Use double quotation marks
as the main quote style. Use no em dashes, no semicolons joining independent
sentences, and never the word `suggested`. State facts directly. Do not narrate
how a sentence changed from a prior draft. Say things explicitly rather than
alluding to them. Verbatim quotes preserve original spelling and punctuation.
proper nouns, titles, URLs, file names, and fact IDs are not rewritten.

The narrative artifact is titled **company brief**. Its cover says **Focus:
Product marketing**, and the front matter identifies the product-marketing
point of view. Reader-facing copy never says `onboarding`, `starting at`, `the
new PMM`, or `the role`.

Before design, a separate high-reasoning context reviews the company brief,
diagram captions, and glossary for American usage. It records every change and
does not alter quotes, fact IDs, file names, or URLs.

## Publication

Markdown remains the research trail and keeps fact IDs beside supported words.
Rendered HTML and PDF replace fact IDs with superscript source numbers. No
reader-facing output exposes repository paths, fact IDs, script names, build
instructions, internal warnings, or remove-before-sharing notes.

A source receives the next citation number on first use, in reading order.
Later uses reuse that number. Citation groups deduplicate and sort numbers. The
company brief has one sequence. Each source note appears once and contains
title, publisher, date, grade, and full public URL when one exists. Grade-I
notes have no public link but retain the same typographic treatment. Diagram
nodes and edges instead reconcile through stable model IDs to fact IDs, source
IDs, verification verdicts, and recorded inference chains.

Web citations use a validated text fragment when possible and otherwise the
plain manifest URL. YouTube citations use transcript time. Other audio and
video use the page URL with timestamp in the note. A script-derived multi-source
count has one note that names every underlying source.

Exhibit citations sit on the exact supported group, box, part, phrase, cell,
timeline wording, or change description. Exhibits never receive a pooled list
of facts. Before design, commit or checksum the Markdown reference in which
fact IDs sit beside supported words. Final exhibit and citation mappings must
still match that reference or a later justified, reverified fact.

The brief answers, in order: product and architecture; buyer and buying motion;
positioning and change; direction; competitors; dependencies; questions and
owners; evidence limits; and sources. It opens with a short summary and one
portfolio exhibit, includes the product map and messaging timeline only in
their intended sections, and targets 10 to 15 body pages excluding cover and
sources.

Section 7 frames unresolved questions neutrally as what the author would want
to understand early. Names appear only when factually useful, not as task
headings. The section does not open with Grade-I evidence or a guess about
reporting lines. Evidence limits use reproducible counts and plain-language
method names.

The architecture package contains four editable SVGs derived only after a
machine-validated model stage: capability taxonomy/inventory, operating
model/behavior, enterprise logical architecture/structure, and focused
technical dependencies/receipts. Their titles and question subtitles are
deterministic. D relationships are solid, R relationships are distinguished,
and H/U possibilities never masquerade as established architecture. Grade-I
material may remain in a private working brief but is removed from any
externally shared version unless explicitly authorized.

The brand guide is delivered in HTML and PDF. Its editorial-diagram section
supplies visual ingredients only. Before drawing, the diagram builder records a
small semantic style map; line pattern, arrowhead, written qualifier, boundary
annotation, and fill/accent remain separate channels. Any convention not found
in public brand evidence is labeled as a designed extension.

Fonts are embedded only when legally permitted and technically available.
Design notes record input-guide choices, public-identity choices, exclusions,
substitutions, and licensing constraints. The design should be company-specific
without imitating an unrelated proprietary report.

### Visual integrity

Automated layout checks find measurable overflow, tight boxes, overlaps, split
exhibits, and unexplained gaps. They do not replace visual judgment. A separate
high-reasoning reviewer opens every rendered page in order with no sampling and
records one row for every clean or defective page. The same reviewer opens all
four SVGs at 165 mm publication width and records one row per diagram. The
reviewer also checks the brand guide at desktop/mobile widths and every page of
its PDF. The orchestrator also views every page and diagram for visual quality, presumptive
employment language, exposed internals, stale counts, and stale metadata.

Fix systemic layout causes before isolated symptoms. After material pagination
changes, rerun placement, design, visual, citation, exhibit, negative, and page
reconciliation checks. Final release requires no open `fix` finding.

Targeted edits change only named Markdown plus the smallest grammar or
coherence repair. Compare PDF text page by page, report every additional
change, inspect every changed page, and restore unintended pagination without
rewriting unrelated copy.

## Model roles and independence

Use the strongest available reasoning model at high effort for extraction,
judgment, verification, synthesis, adversarial review, substantive fixes, and
visual judgment. A faster capable model may perform mechanical editing and
bounded transformations. Do not hard-code historical product names. Record
model and effort when the runtime exposes them. Never invent missing metrics.

Separate contexts are required for:

- writing and evidence verification;
- synthesis and skeptical or devil's-advocate review;
- citation placement and exact-claim citation review;
- authored pages and final visual review.

The same underlying model may serve separate roles only in separate contexts.
Do not combine independence-required roles to save tokens.

Workers receive only task type, immutable inputs, exact output paths, required
schema, relevant principles, completion criteria, and concise return format.
They do not receive the entire master prompt. They write only assigned outputs
and private scratch space. Shared state belongs to the orchestrator or a named
single writer.

## Conceptual lifecycle

The effective dependency order is:

1. Bootstrap the repository, tools, state, and bounded task contracts.
2. Map scope and public source channels.
3. Capture and reconcile the source record while an independent brand-guide
   worker inspects, builds, renders, and checks the public visual system.
4. Extract, file, and mechanically validate facts.
5. Produce initial synthesis from script-checked facts.
6. Model-verify every fact cited by that synthesis.
7. Apply fact corrections and repair dependent synthesis.
8. Run independent technical, adversarial, insider, and editorial reviews.
9. Disposition every finding and apply accepted fixes.
10. Write and assemble the company brief; reconstruct and validate the four
    architecture information models before drawing.
11. Map brand presentation onto the validated model, build the four editable
    SVGs, then run publication, citation, claim,
    design, and complete page-and-diagram visual checks.
12. Independently accept the exact release artifacts.

The historical numbering places the verification framework before Phase 4,
but expensive cited-fact verification happens after initial synthesis. Labels
may clarify this. Dependencies must not change.

Independent preparation may run while a gate is pending, including tool,
template, work-list, competitor-capture, and phase-brief work that does not
consume unvalidated outputs. Dependent work never starts until its gate passes.

## Five assurance layers

1. **Data integrity:** Structured records, IDs, paths, fields, counts, and hashes
   are mechanically valid.
2. **Evidence validity:** Quotes, locations, attribution, dates, grades, and
   claims faithfully reflect captured evidence.
3. **Reasoning quality:** Valid facts actually justify product, market,
   competitive, and strategic conclusions.
4. **Publication integrity:** The exact reader-facing words, citations,
   exhibits, links, layout, and evidence limits stay within support.
5. **Execution integrity:** Current on-disk evidence proves every required
   process ran completely on the exact artifacts under review.

Related checks at different layers are not duplicates. A fact-level support
check does not replace a final sentence-level claim review. Reconciliation does
not replace validation. Automated layout measurement does not replace full-page
visual judgment.

## Execution and completion

The orchestrator assigns tasks, coordinates work, and integrates outputs. It is
not the authority that declares completion. Deterministic gates and independent
release acceptance do so from current on-disk evidence.

Every assignment is bounded and immutable, with stable IDs, exact outputs,
validators, and non-overlapping ownership. Every attempt remains in an
append-only single-writer ledger. Success requires process completion, valid
outputs, and hashes. Prose reassurance is never enough.

Every assigned input receives one terminal disposition. Zero facts or zero
findings require an explicit completed-zero record. Reconciliation flags
missing, duplicate, overlapping, unassigned, and unexpected work. Blocked and
excluded inputs remain coverage limitations rather than successes.

Every validation result is `PASS`, `FAIL`, or `UNKNOWN`. It records checker
identity/version, input IDs or hashes, expected and checked counts, failure
count, timestamp, and report integrity. Missing, malformed, crashed, timed-out,
or under-counted checks are `UNKNOWN`. Both `FAIL` and `UNKNOWN` block.

Gate results bind to their exact inputs and checker versions. Relevant changes
make a gate stale. Caches are valid only for matching hashes and checker
versions. Retries are targeted, bounded, and append attempts rather than
erasing history. Validated, unaffected work is preserved.

Release acceptance independently confirms every gate, reconciliation,
required test, semantic review, final verification verdict, finding
disposition, visual page record, and exact artifact hash. It writes a release
manifest only after success. Accepted exceptions are explicit, justified,
evidence-backed, and cannot override mandatory failed controls.

Deterministic code handles deterministic work. Models receive concise failing
IDs and relevant context, while full records stay on disk. Efficiency never
removes semantic review, visual review, complete reconciliation, or final
acceptance.

## Final reporting

The short run report supplements rather than replaces deliverables. It reports
source counts by grade and channel, fact verdict counts, top open questions,
blocked sources, least-certain findings and reasons, tooling substitutions,
deliverable paths, final check status, worker-attempt outcomes, reconciled
inputs, gate status, exceptions, and release-manifest path.

Never call the project complete when release acceptance fails or unresolved
required work remains.
