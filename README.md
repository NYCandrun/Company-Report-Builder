# Adaptive company research agent

Give the agent one public company URL. This repository discovers the available
evidence, plans work from the resulting corpus, and carries the run through a
cited, visually reviewed company brief, public-evidence brand guide, and four
evidence-bounded architecture diagrams. Do not ask the user how many pages,
sources, batches, or workers to use.

## Run it

From a clean copy of this repository:

```bash
python3 -m research_control preflight
python3 -m research_control run --url "COMPANY_URL"
```

`run` initializes or resumes the durable scheduler, completes automatic
controls, plans the current phase, and writes ready packets under
`tools/outputs/task-packets/`. Continue executing the returned packets and
rerunning:

```bash
python3 -m research_control run
```

until it returns `release_ready`. Then run:

```bash
python3 -m research_control release
```

Do not stop at a plan, packet list, draft, or progress summary. Completion
requires a passing `07-final-report/release-manifest.json` bound to the exact
final artifact hashes.

If a run already exists, omit `--url`. Inspect it at any time with:

```bash
python3 -m research_control status
```

## Execute task packets

Every packet is an immutable work assignment with exact inputs, output paths,
prompts, schemas, dependencies, and validators. For each returned packet:

```bash
python3 -m research_control work claim TASK_ID --worker-id STABLE_WORKER_ID
python3 -m research_control work start TASK_ID --worker-id STABLE_WORKER_ID
# perform only the packet
python3 -m research_control work succeed TASK_ID --worker-id STABLE_WORKER_ID \
  --model MODEL --effort EFFORT
```

Model routing is advisory and optional. Each packet names an economy, standard,
or strong reasoning tier. Use it only when the current host/session exposes
model or effort selection; otherwise omit `--model` and `--effort` and use the
available model. Routing availability never blocks a task or relaxes its gates.

For long work, renew the lease:

```bash
python3 -m research_control work heartbeat TASK_ID --worker-id STABLE_WORKER_ID
```

On a recoverable failure:

```bash
python3 -m research_control work fail TASK_ID --worker-id STABLE_WORKER_ID \
  --reason "CONCRETE REASON"
```

Add `--terminal` only when retrying cannot help. Expired leases are recovered
automatically; `python3 -m research_control work recover` can run that check
explicitly.

Use a genuinely separate agent context and unique worker ID for every packet
marked `independent: true`. Parallelize all ready independent packets when the
host permits. The scheduler enforces global and per-host concurrency. Workers
write isolated parts; reducer packets are the sole writers of canonical shared
files.

The packets are host-neutral. In Codex, use subagents for ready independent
packets. In Claude Code, use isolated subagents. If no subagent facility exists,
execute the same packets in separate contexts sequentially. Never improvise a
different task graph because a host lacks a dispatch API.

## Adaptive discovery

Discovery has no source-count target. It begins with the supplied URL, expands
the first-party link frontier, and examines these evidence channels:

- company site and sitemaps;
- newsroom, blog, resources, help, and documentation;
- careers and recruiting systems;
- video, podcasts, and social accounts;
- public repositories and packages;
- relevant independent reporting and analysis.

Each applicable channel continues through materially different discovery
passes until repeated passes add no new relevant sources. A channel may instead
end as `not_applicable`, `blocked`, or `incomplete`, but only with evidence.
All channels need terminal accounting, but only `saturated` and
`not_applicable` count as complete coverage. A blocked channel remains a visible
limitation, while `incomplete` prevents the discovery reducer from passing.
Neither state may be relabeled because an arbitrary number of URLs was found.

The configured page, byte, depth, elapsed-time, concurrency, and retry limits
are circuit breakers. Reaching one produces an explicit incomplete or blocked
state; it never manufactures completion.

Useful discovery commands are embedded in discovery packets:

```bash
python3 -m research_control discovery crawl
python3 -m research_control discovery add --channel CHANNEL --url URL \
  --evidence "SEARCH OR SURFACE CHECKED"
python3 -m research_control discovery close --channel CHANNEL \
  --state not_applicable --evidence "WHY"
python3 -m research_control discovery receipt --channel CHANNEL
```

The runtime canonicalizes and deduplicates URLs. Ordinary public pages can be
captured into isolated parts with:

```bash
python3 -m research_control source capture --source-id SOURCE_ID
```

Use the host's browser, PDF, OCR, caption, transcription, repository, or media
tools for formats that need them. Respect rate limits and record inaccessible
evidence.

Research discovery and brand discovery remain separate agent responsibilities,
but share a run-local transport cache and URL lead ledger in the scheduler.
This prevents repeated public fetches without allowing brand observations into
the research claim register or research facts into the brand evidence record.
The first-party crawler and ordinary source capture use the cache automatically.
Workers can query or populate it explicitly:

```bash
python3 -m research_control web list --purpose research_discovery
python3 -m research_control web fetch --url URL \
  --consumer TASK_ID --purpose brand_asset
python3 -m research_control web export
```

URLs in this ledger are leads, not evidence. Each consuming workflow must still
apply its own inclusion rules and create its own evidence records. The workers
start concurrently and never wait on this optional sharing. Ledger listings are
compact and paginated for prompt efficiency; `next_offset` indicates another
page of leads, not a source-count completion target.

## Adaptive planning and scheduling

The scheduler uses `tools/outputs/runtime.sqlite3` as its private transactional
state and emits an append-only audit stream at
`tools/outputs/runtime-events.jsonl`. It creates work only after the necessary
scope or corpus information exists.

- Discovery work expands until channel saturation.
- One isolated capture task is created per relevant canonical source.
- Captured text is assembled into canonical extracts.
- Extraction work is packed by estimated token volume, and oversized sources
  are split into explicit stable slices.
- Failed or expired slices retry without repeating successful siblings.
- Single-writer reducers reconcile parts into manifests, candidate stores,
  dispositions, facts, reviews, and publication artifacts.
- Input or output hash changes mark affected work stale and propagate
  invalidation to its downstream consumers.
- Passing deterministic validators and reconciliations are reused only while
  both their input hashes and validation-engine hash remain identical.

Task states are:

```text
planned -> ready -> leased -> running -> validating -> succeeded
                            \-> retryable -> ready
                            \-> failed | blocked
succeeded -> stale -> ready
```

Task counts therefore vary with the company and evidence actually found.

At the start of capture, the scheduler also launches one independent brand-guide
packet. It inspects the company's public visual system while discovery and
source capture continue, so the work normally overlaps the longest research
stage instead of becoming a serial phase. The brand packet is presentation-only:
it cannot add facts to the company record or architecture model.

## Research and release contract

Read these in order when starting a run:

1. `RESEARCH_CONSTITUTION.md` — evidence and research principles.
2. `WORKFLOW.yaml` — adaptive runtime settings, phase order, and gates.
3. Only the task packet and files named by that packet while doing worker work.

The controlled phases remain:

```text
bootstrap -> scope -> adaptive discovery and capture + concurrent brand guide -> adaptive extraction
-> fact filing -> initial synthesis -> cited-fact verification
-> corrected synthesis -> independent skeptical review -> final brief
-> gated architecture modeling -> branded four-diagram build
-> language, citation, and complete visual review -> fixes and re-review
-> release acceptance
```

The brand packet produces `07-final-report/brand-guide.html` and
`07-final-report/brand-guide.pdf`, with auditable visual evidence under
`05-synthesis/brand-guide/evidence/`. The final-writing packet produces
`05-synthesis/company-brief.md`. The diagram packets first produce an auditable
model registry, then a concise `diagram-style-spec.md` from the guide's
presentation language, and finally four editable SVGs with fixed titles and
subtitles. The brand guide never supplies architecture facts. Build the
company-brief HTML, PDF, and page previews with:

```bash
python3 -m research_control render
```

The fixed figure labels are:

1. **Capability taxonomy / inventory** — What does this company offer, and how
   are its capabilities organized?
2. **Operating model / behavior** — How does the product turn an input or need
   into an outcome?
3. **Enterprise logical architecture / structure** — How are the major
   functional domains organized, and how does the platform relate to its
   environment?
4. **Focused technical dependencies / receipts** — What consequential
   technical relationship, limitation, or architectural distinction does the
   research establish?

The assembler places all four SVGs into the company-brief HTML so they are also
reviewed in the target report layout.

Publication rendering is input-hash aware. Unchanged HTML, PDF, and page
previews are reused. `tools/outputs/review-scope.json` marks changed visual
surfaces for inspection and permits prior clean records to carry forward only
when their artifact hashes match exactly. Initial review still covers every
page, diagram, brand-guide viewport, and brand-guide PDF page.

Release remains fail-closed. It requires current phase gates, complete input
accounting, independent review identities, resolvable fact/source citations,
the company-brief and brand-guide HTML/PDF pairs, all four SVGs, exact
deterministic diagram titles, a review record for every rendered report page,
diagram, brand-guide viewport, and brand-guide PDF page, and exact final hashes.
If release cannot pass, report the concrete failed control and leave the run
resumable.

The control runtime uses only Python's standard library. CSS-capable PDF tools,
PDF rasterization, browser rendering, OCR, and transcription are used when the
host provides them and are reported by `preflight` when absent. Framework
regression suites run in repository CI, not inside individual company runs.
