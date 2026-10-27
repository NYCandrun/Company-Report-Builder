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

Runtime-owned tasks (marked `executor: runtime`) never become packets and
cannot be completed by a worker; `run` executes them under the reserved worker
identity `runtime-executor`.

The packets are host-neutral. In Codex, use subagents for ready independent
packets. In Claude Code, use isolated subagents. If no subagent facility exists,
execute the same packets in separate contexts sequentially. Never improvise a
different task graph because a host lacks a dispatch API.

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
`RESEARCH_CONTROL_AGENT_CONCURRENCY`, and `RESEARCH_CONTROL_AGENT_PER_HOST`.
Long transcriptions should never hold up page capture.
Each capture writes a terminal receipt:
`captured` with a canonical UTF-8 text derivative, or `blocked` with the
concrete reason.

- Web pages: HTTP capture with rendered-order text extraction; pages built by
  JavaScript fall back to a headless browser when the host has one.
- PDFs: `pdftotext` with page markers.
- Video and audio: a timestamped `transcript.txt`. YouTube tries published
  captions, then yt-dlp captions with the default, `web_embedded`, and
  `android_vr` player clients, then the audio through yt-dlp, then audio
  through a public Invidious instance, each transcribed locally with Whisper.
  Other media is downloaded and transcribed with Whisper. YouTube requests are
  spaced (`RESEARCH_CONTROL_YT_SPACING`, default 20 s); Invidious instances are
  set with `RESEARCH_CONTROL_INVIDIOUS`. Machine transcripts never establish
  who is speaking.

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
- One capture task is created per relevant canonical source and executed by
  the runtime.
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
