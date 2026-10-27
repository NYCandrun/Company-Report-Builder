# Adaptive company research agent

Give the agent one public company URL. This repository discovers the available
evidence, plans work from the resulting corpus, and carries the run through a
cited, visually reviewed company brief, public-evidence brand guide, and four
evidence-bounded architecture diagrams. Do not ask the user how many pages,
sources, batches, or workers to use.

## Run it

From the template checkout, provision an isolated run directory and start it:

```bash
python3 -m research_control preflight
python3 -m research_control new --url "COMPANY_URL"
```

`new` copies the policy, prompts, and control engine into `runs/<company-slug>/`
(ignored by the template's git) and starts the run there. The template itself
never holds run output. Every later command runs from inside the run
directory, so the run uses one consistent engine snapshot:

```bash
cd runs/<company-slug>
python3 -m research_control run
```

`run` resumes the durable scheduler, executes deterministic work itself (site
crawl, sitemap audit, page/PDF/media capture, reducers), plans the current
phase, and writes ready agent packets under `tools/outputs/task-packets/`.
Execute the returned packets and rerun `run` until it returns `release_ready`.
Then run:

```bash
python3 -m research_control release
```

Do not stop at a plan, packet list, draft, or progress summary. Completion
requires a passing `07-final-report/release-manifest.json` bound to the exact
final artifact hashes. Inspect a run at any time with
`python3 -m research_control status`.

`run --plan-only` plans and writes packets without executing runtime work. Use
it when another `run` process is already executing (for example a long capture
with transcription), so two processes never run the same deterministic work.

### Changing the framework while a run is in flight

Fix the template, then refresh the run's snapshot from the template checkout:

```bash
python3 -m research_control --root runs/<company-slug> sync-engine
```

`sync-engine` copies the policy, prompts, and engine into the run and appends
an `engine-synced` entry to the run's `RUN_HISTORY.md` with the template commit
and short hashes of the constitution, workflow, prompts, and engine. Every
capture receipt records the same fingerprint, so each source shows which rules
were in force when it was captured. Changed inputs and validators invalidate
dependent work through the normal hash checks.

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
strong, or frontier reasoning tier; frontier is reserved for the hardest
judgment work (cited-fact verification, the devil's-advocate review, and
diagram modeling). Use it only when the current host/session exposes
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
write isolated parts; reducers are the sole writers of canonical shared files.

Work happens only under a held lease. Discovery commands that change a
channel's record (`discovery add`, `close`, `exclude`, `receipt`) refuse to run
unless that channel's discovery task is claimed and started. When a closed
channel needs more work, the orchestrator reopens it with
`python3 -m research_control discovery reopen --channel CHANNEL --evidence WHY`
and reruns `run`, which re-queues the channel's task for a worker to claim.

When a source already used downstream is recaptured with more content (for
example a repository's branches and pull requests), list it with
`python3 -m research_control supplement --source-id SRC-… --reason WHY`, rerun
its capture alone with `work rerun capture.source.src-… --only --reason WHY`,
then rerun `capture.reduce-captures` the same way. Facts already filed stand;
the new text is extracted, appended at filing, and reconciled into synthesis.
Reconciliation reads a digest, not the fact store: the runtime writes one line
per new fact (ID, date, grade, source, claim, delivery status, relationship
basis) under `tools/digests/supplement/`, split by the synthesis file its
question feeds. One reconcile per synthesis file reads its share and opens full
rows only for facts it cites; the catalogue is then revised from the synthesis
files, and the runtime writes the reconciliation report, recording every fact
no reconcile cited as left uncited.
When a token budget will not cover every new slice, choose the slices worth
reading and leave the rest out with
`work defer-slices SRC-…:part-NNNN … --reason WHY`; the next `run` retires their
pending batches, and `tools/lists/deferred-slices.json` records the gap. A
deferred slice whose text later changes is planned again.

Runtime-owned tasks (marked `executor: runtime`) never become packets and
cannot be completed by a worker; `run` executes them under the reserved worker
identity `runtime-executor`.

The packets are host-neutral. In Codex, use subagents for ready independent
packets. In Claude Code, use isolated subagents. If no subagent facility exists,
execute the same packets in separate contexts sequentially. Never improvise a
different task graph because a host lacks a dispatch API.

## Keeping steps bounded

Each step reads what it judges, not whole stores. Filing is runtime work: the
runtime records duplicates, merges near-duplicates (same source and claim, or
one quote containing the other), rejects quotes not in their captured source,
and appends the rest under stable IDs; a reviewer then spot-checks a sample
(`facts.filing-spot-check`). Before groundwork the runtime writes
`tools/digests/`, one line per fact per fact table (ID, date, grade, source,
who said it, claim, delivery status, relationship basis), and groundwork and
the synthesis writers work from those, opening full rows by ID. Extraction
notes hold the marks and at most one sentence of qualifier.

Steps after synthesis read only what they judge. Verification packets carry each
quote as the runtime located it, with its context, the capture's first lines,
and its section, so verifiers open a full capture only when that is not
enough. Verification also writes `tools/outputs/cited-fact-rows.md`, one table
of the cited facts with verdicts, dates, and deep links, which the brief writer
and diagram modeler use instead of the fact store. A filed fact whose evidence
no longer holds (it described a capture omission a recapture fixed) is
withdrawn by ID in `tools/lists/withdrawn-facts.json` with a reason: it keeps
its ID, quote checks skip it, and synthesis may not cite it.

## How many workers

`run` lists, under `agents`, one entry per worker to start: tasks that read
different material get separate workers so they run in parallel, and ready
tasks of the same kind that read the same files share one worker (with a
combined brief), so nothing is read twice. Reviews whose value is independent
judgment, and the two citation checks, always get their own. Scripted work
sizes its own parallelism to the machine's cores and memory (see the
overrides below).

## The control agent's conversation

The orchestrator's whole conversation, with access tokens, keys, and other
secrets removed, is copied into `08-control agent conversation history/` and
pushed with the run every time the run is saved (`archive`) and at the start
of every phase. At each phase start a script asks the remote for the run's
branch and confirms the push landed; a push that did not land is tried again,
and the phase waits until it has. Each copy is the full conversation so far,
recorded by line count and hash. When the run is released, the whole
conversation is written as one file, a script checks that every earlier copy
matches the start of it, and the earlier copy is deleted. After that the
folder is left alone: questions after the run are not added. These files are
written by script and not read unless the user asks.

## Talking to the user

Write for the user in plain English. Leave out jargon and internal shorthand ("shard", "slice", "packet", "gate", "reconcile", "the X repo"): say what a thing is ("a batch of 48 facts to verify", "a chunk of a source's text", "the phase checks"), name a repository by its GitHub name (owner/repository, for example carlmueller-tribe/mori), and name a source by what it is (a podcast episode, a company blog post), not only by its ID. The rule is in the orchestrator's instructions (`CLAUDE.md`), in the
runtime core every task carries, in the writing core for documents, and in
every worker brief.

## Spending less without reading less

- Repository captures: a commit's added lines that are still in the current
  file are counted, not repeated (the file's text has them, and its header
  dates each line range by the commit that wrote it); removed lines, and added
  lines later changed, stay. Test files are read by their test names and
  docstrings, and test diffs are left out.
- Sources are cut at file, commit, conversation, timestamp, or paragraph
  boundaries chosen by the text there, and a finished batch covers its text
  wherever it now sits, so a recapture re-extracts only what changed. Runs that
  were cut at fixed sizes keep that cutting.
- Extraction batches carry the model tier their sources need
  (`extraction_tiers` in `WORKFLOW.yaml`): code, specs, and data on
  `standard`; recordings, pages, and business records on `strong`.
- A question added mid-run re-reads the relevant sources only where they share
  terms with it, and only for it (`focus_questions` on the input). For a rule
  change that affects one kind of source, `supplement --kind repository
  --reason WHY` lists just those sources.
- `limits --extraction-budget TOKENS` caps the source text extraction reads.
  Past it, the planner plans the slices that bear most on the questions and
  defers the rest, listed in `06-checks/extraction-budget.md`; raising the
  budget brings them back.

## Running without steering

- Every packet comes with a brief (`<task>.brief.md`, and `brief` in the `run`
  output) that a host passes to its worker unchanged: worker ID, lifecycle,
  the run notes from `00-scope.md`, `work check TASK` (what `work succeed`
  would refuse, and the synthesis checks), and completion.
- The run notes in `00-scope.md` ("Notes for downstream phases") carry what
  the research itself established that later work must apply, for example a
  company's own statement of which names are its products.
- `run` recovers expired leases, so work stopped by an interruption is
  dispatched again, and re-checks earlier gates that are stale only because an
  engine sync moved their recorded inputs.
- A check never makes a worker reword the source's text; a suspected false
  positive is reported instead.

## Small corrections to finished outputs

When the orchestrator corrects a finished task's output by hand (a name a
validator false positive made a worker change, a typo), record it with
`work record-edit PATH... --phase PHASE --reason WHY`. The edit is recorded as
a revision that owns those files, tasks that read them keep their results, and
the task that wrote them is restored instead of rerun.

## Adding a research question mid-run

When the research needs a question the scope did not ask, add it with
`python3 -m research_control --root runs/<slug> scope add-question --id Q13
--title TITLE --text TEXT --channels CHANNELS --reason WHY`. It appends the
question to `00-scope.md`, records the change in the run history, and requests
a re-triage: `run` plans `facts.retriage.<id>`, a standard-tier packet that
decides every captured source again against the added questions only, from
the triage index. A relevant source that was excluded is extracted; one that
was already extracted is listed for supplement and its text extracted again
for the new questions, keeping the facts already filed. Earlier decisions
never shrink. This costs one pass over the index plus the relevant sources,
instead of re-extracting the corpus and rebuilding every fact ID, citation,
and verdict downstream.

## Provenance, dates, and deep links

Every source has a row in `tools/outputs/source-dates.jsonl`: its URL,
platform, publisher or channel, the date its content reflects and the basis
for it, its posting date, and, for a recording that states when it was
recorded, the recorded date and the words that state it (extraction records
these as `Recorded:` notes). Recordings whose stated date differs from their
posting are listed in `06-checks/source-dating.md`. Every filed fact gets a
deep link in `tools/outputs/fact-links.jsonl`, computed from its quote: the
repository file and line at the captured commit, the line in a commit's or
pull request's diff, the recording's timestamp, or a text fragment that
highlights the quoted words on a page (`reduce links`; also run by
verification's prepare step). Unlocated quotes are listed in
`06-checks/fact-links.md`. The brief's citation map uses both.

## Keeping the evidence

A run folder is ignored by the template's git. `python3 -m research_control
--root runs/<slug> archive` commits the run to its own branch on the
template's remote, `run-data/<slug>`, through a separate git directory
(`tools/archive.git`), so the template branch is untouched. It keeps every
capture (page text, HTML, transcripts and captions, receipts), the fact store,
synthesis, checks, the final report, a snapshot of the scheduler database, and
a git bundle of each cloned repository with all history, branches, and pull
request heads (`01-sources/repositories/`, with a manifest; a bundle over the
remote's file limit is listed and its captured text kept). It leaves out
downloaded audio, whose transcript is kept, the HTTP transport cache, and
worker scratch space. Archive after every `run` that captures sources and
after each wave of workers.

## Question-bounded discovery

Discovery has no source-count target in either direction. Scope numbers the
research questions (`Q1`, `Q2`, ...), starting from the brief's required
sections, and every later stage is bounded by them.

There is one discovery task per channel, ten in all:

| Channel | Who does it |
|---|---|
| `company_site` | runtime: crawls the company host to a fixed point |
| `sitemaps` | runtime: audits every declared sitemap against the catalog |
| `newsroom_blog`, `docs_help`, `careers`, `code_packages` | one agent worker each, after the crawl, for what the crawl could not reach |
| `video`, `podcasts`, `social`, `independent_web` | one agent worker each, in parallel with the crawl |

A search channel closes as `sufficient` when its admitted sources answer the
named questions (the evidence must cite the question IDs), or as `saturated`
after two materially different passes in a row add nothing. A channel may also
close as `not_applicable`, `blocked`, or `incomplete`, with evidence. Only
`saturated`, `sufficient`, and `not_applicable` count as complete coverage;
`incomplete` prevents the discovery reducer from passing.

Video is in scope at every length, including Shorts, clips, and social video
drops: every video on the company's own channels and every video or podcast in
which its founders, executives, or named leaders appear. URLs on login-walled
platforms are kept as uncaptured leads, except videos admitted on the video
channel, which capture tries to transcribe. Competitor sources are admitted only
when they answer a named question, never a competitor's docs or blog wholesale.

The configured page, byte, depth, elapsed-time, concurrency, and retry limits
are circuit breakers. Reaching one produces an explicit incomplete or blocked
state; it never manufactures completion.

Worker discovery commands (they require the channel's task to be claimed):

```bash
python3 -m research_control discovery add --channel CHANNEL --url URL \
  --evidence "SEARCH OR SURFACE CHECKED"
python3 -m research_control discovery close --channel CHANNEL \
  --state sufficient --evidence "Q2: ...; Q5: ..."
python3 -m research_control discovery receipt --channel CHANNEL
```

## Capture and transcripts

The runtime captures every admitted source itself, in parallel.

Concurrency is a soft rule: do whatever is most efficient in the environment
the run is in. The runtime starts from defaults derived from the host's cores
and memory (`research_control/resources.py`), and the agent scheduler starts
from the `WORKFLOW.yaml` scheduler values. Neither is a target. Check the
environment (cores, memory, network speed, the rate limits and errors hosts
actually return) and raise or lower any limit when that would finish the work
faster without failures. Override with `RESEARCH_CONTROL_RUNTIME_WORKERS`,
`RESEARCH_CONTROL_PER_HOST`, `RESEARCH_CONTROL_HOST_INTERVAL`,
`RESEARCH_CONTROL_WHISPER_JOBS`, `RESEARCH_CONTROL_BROWSER_JOBS`,
`RESEARCH_CONTROL_AGENT_CONCURRENCY`, and `RESEARCH_CONTROL_AGENT_PER_HOST`
for one command, or set the agent limits for the rest of the run with
`python3 -m research_control limits --global N --per-host N` (kept in
`tools/lists/runtime-limits.json`; a command-line variable still wins).
Long transcriptions should never hold up page capture.
Each capture writes a terminal receipt:
`captured` with a canonical UTF-8 text derivative, or `blocked` with the
concrete reason.

- Every network step retries a transient failure (a timeout, a dropped
  connection, a server's 5xx, a rate limit) with backoff before falling back;
  a refusal or a missing page is not retried.
- Web pages: HTTP capture with rendered-order text extraction. Pages built by
  JavaScript, and pages whose plain request fails for any reason other than
  the page being gone (404, 410) or an unusable URL, fall back to a headless
  browser when the host has one. The browser
  always presents as desktop Chrome in a 1440x900 desktop window
  (`RESEARCH_CONTROL_DESKTOP_USER_AGENT` overrides the identity), so pages
  render their desktop layout and content; if that is refused it retries once
  with the browser's default identity in the same desktop window, since sites
  differ in which they serve. A browser that only reaches a
  refusal or challenge page is recorded as blocked with both reasons.
- PDFs: `pdftotext` with page markers.
- Recordings: published captions, then captions through `yt-dlp` with
  alternate player clients, then audio through `yt-dlp` or a public Invidious
  instance transcribed locally; `media retry` re-queues the ones that failed.
- GitHub: public repositories, directories, and files are captured from a
  full git clone without file contents until read (every branch and pull
  request head), retried on any transient failure. If branches cannot be
  fetched, the default branch is still captured and the gap is stated. Pull
  request and issue pages are read through the headless browser, which
  github.com serves when it refuses plain requests. Files are ranked (docs,
  manifests, code, then the rest); HTML is read as text, large datasets are
  sampled with their size and shape stated, inline base64 is replaced, and a
  large diff is included file by file. Organization listings need the GitHub
  API and are recorded as blocked; their repositories are captured
  individually. `recapture --blocked` re-queues blocked sources after a capture
  method improves.

Blocked sources get an alternate-copies pass (`capture.alternate-copies`, one
agent worker) as soon as the discovery snapshot and every page capture finish,
without waiting for long transcriptions. A source blocked after that pass was
planned gets a later pass (`capture.alternate-copies.2`, ...) over just the new
ones. Each pass for a public copy of the same content (wire-service or issuer copy of a
release, syndicated article, the same video or episode elsewhere, the other
party's announcement) and records an alternate or "none found" for every
blocked source with `discovery alternate`. Alternates join the original's
channel without reopening it and are captured automatically; `01-sources/BLOCKED.md`
shows each blocked source's alternate or that none exists. The final manifest
waits for every pass.
- Video and audio: a timestamped `transcript.txt`. YouTube tries published
  captions, then yt-dlp captions with the default, `web_embedded`, and
  `android_vr` player clients, then the audio through yt-dlp, then audio
  through a public Invidious instance, each transcribed locally with Whisper.
  Other media is downloaded and transcribed with Whisper. YouTube requests are
  spaced (`RESEARCH_CONTROL_YT_SPACING`, default 20 s); Invidious instances are
  set with `RESEARCH_CONTROL_INVIDIOUS`. Whisper transcripts label speakers
  per word by automatic diarization: NVIDIA Sortformer
  (`nvidia/diar_streaming_sortformer_4spk-v2`, CC-BY-4.0, from Hugging Face,
  via NeMo; up to four speakers per recording), falling back to `sherpa-onnx`
  with pyannote segmentation and TitaNet-Large when NeMo is not installed.
  Labels such as `Speaker 2` mark turns and group voices; they never establish
  who is speaking. Published captions carry no speaker labels.

YouTube availability from cloud networks varies by the hour. Re-queue media
whose transcript failed with:

```bash
python3 -m research_control media retry
python3 -m research_control run
```

Quotes are checked against every text derivative of a source (page text, PDF
text, transcript).

## Extraction triage

Capture is cheap, so the corpus can hold more pages than the brief can use.
Before extraction, one triage worker gives every captured source one decision,
`include` or `exclude`, naming the research questions it answers. Only
included sources are read for facts. Excluded sources keep their capture and
provenance and receive an `excluded` extraction disposition. Exclusion is never
a way to drop contradicting evidence.

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

- Discovery work runs per channel until each closes against the research
  questions or saturates.
- One capture task is created per relevant canonical source as soon as it is
  admitted, and the runtime captures it while discovery continues. Only the
  capture reducer, which writes the final manifest, waits for discovery to
  close. Phase gating applies to work whose input would be incomplete without
  the earlier step, not to work that can simply grow as new inputs arrive.
- Triage selects captured sources for extraction by research question.
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

Phases fan out wherever parts do not depend on each other:

- **Synthesis.** One groundwork task writes the digests, timelines, and
  currency file. An independent worker reviews currency. Then each synthesis
  file gets its own writer, all in parallel. Open questions is written last,
  from the other eight.
- **Verification.** The runtime lists every cited fact and writes one packet
  per fact. It groups the facts into shards by source, so each capture is read
  once. Each shard gets its own independent verifier, and the runtime merges
  the verdicts in cited order.

At the start of capture, the scheduler also dispatches the brand-guide packet
(`final.brand-guide`, marked `dispatch: early`). It belongs to the final phase
and gates only that phase: the brief writer and diagram builder depend on it,
but no research gate waits for it, so it runs alongside discovery, capture,
extraction, synthesis, verification, and review. The brand packet is
presentation-only: it cannot add facts to the company record or architecture
model.

## Research and release contract

Read these in order when starting a run:

1. `RESEARCH_CONSTITUTION.md` — evidence and research principles.
2. `WORKFLOW.yaml` — adaptive runtime settings, phase order, and gates.
3. Only the task packet and files named by that packet while doing worker work.

The controlled phases remain:

```text
bootstrap -> scope (numbered research questions)
-> per-channel discovery and runtime capture  (brand guide starts here, runs alongside)
-> extraction triage -> adaptive extraction -> fact filing
-> initial synthesis -> cited-fact verification
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
PDF rasterization, headless browser rendering, `yt-dlp`, `faster-whisper`
(with `ffmpeg`), OCR, and transcription are used when the host provides them
and are reported by `preflight` when absent. Framework
regression suites run in repository CI, not inside individual company runs.
