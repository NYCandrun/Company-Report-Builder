# Adaptive company research agent

Give the agent one public company URL. This repository discovers the available
evidence, plans work from the resulting corpus, and carries the run through a
cited and visually reviewed company brief. Do not ask the user how many pages,
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
tools for formats that need them. Respect robots rules, rate limits, logins,
paywalls, and bot challenges. Record inaccessible evidence; do not bypass the
restriction.

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

Task states are:

```text
planned -> ready -> leased -> running -> validating -> succeeded
                            \-> retryable -> ready
                            \-> failed | blocked
succeeded -> stale -> ready
```

Task counts therefore vary with the company and evidence actually found.

## Research and release contract

Read these in order when starting a run:

1. `RESEARCH_CONSTITUTION.md` — evidence and research principles.
2. `WORKFLOW.yaml` — adaptive runtime settings, phase order, and gates.
3. Only the task packet and files named by that packet while doing worker work.

Do not load `docs/legacy-prompt.md` during normal work. It is the preserved
historical policy and traceability baseline.

The controlled phases remain:

```text
bootstrap -> scope -> adaptive discovery and capture -> adaptive extraction
-> fact filing -> initial synthesis -> cited-fact verification
-> corrected synthesis -> independent skeptical review -> final brief
-> language, citation, and page-by-page visual review -> fixes and re-review
-> release acceptance
```

The final-writing packet produces `05-synthesis/company-brief.md` and
`05-synthesis/one-page.md`. Build HTML, PDFs, and page previews with:

```bash
python3 -m research_control render
```

Release remains fail-closed. It requires current phase gates, complete input
accounting, independent review identities, resolvable fact/source citations,
HTML and PDF outputs, a review record for every rendered page, and exact final
hashes. If release cannot pass, report the concrete failed control and leave the
run resumable.

## Development verification

```bash
python3 -m unittest discover -s research_control/tests -v
python3 tools/run_integrity_tests.py
python3 tools/audit_refactor.py
```

The control runtime uses only Python's standard library. CSS-capable PDF tools,
PDF rasterization, browser rendering, OCR, and transcription are used when the
host provides them and are reported by `preflight` when absent.
