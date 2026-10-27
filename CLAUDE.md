# Claude Code execution adapter

## Talking to the user

Write for the user in plain English. Leave out jargon and internal shorthand ("shard", "slice", "packet", "gate", "reconcile", "the X repo"): say what a thing is ("a batch of 48 facts to verify", "a chunk of a source's text", "the phase checks"), name a repository by its GitHub name (owner/repository, for example carlmueller-tribe/mori), and name a source by what it is (a podcast episode, a company blog post), not only by its ID. This holds for every message to the user, status updates included,
and for anything a worker reports that you pass on.

Follow `README.md` as the operational entry point. Start a company run with
`python3 -m research_control new --url URL`, then work from inside its
`runs/<slug>/` directory: rerun `python3 -m research_control run` and dispatch
every ready packet until exact-artifact release passes.

- `run` prints a short summary; the full result is in
  `tools/outputs/last-run.json` (`run --full` prints it). Start one subagent
  per entry in `start_workers`, with the model and effort for its
  `model_level` from the table below, and give it a one-line prompt:
  `Read <read> in full and follow it.` The file it names holds everything the
  worker needs: its worker ID, lifecycle commands, run notes, the
  `work check` it runs before it succeeds, the task's instructions (only the
  rules that task uses), and the text of the files it reads. Never paste a
  brief into the prompt: it would stay in your conversation and be re-read on
  every later step. Separate workers run work that reads different material
  in parallel; tasks that read the same files share one worker, so nothing is
  read twice; reviews whose value is independent judgment always get their
  own worker. Do not split one task's reading across workers or add workers
  beyond these entries. When a worker reports something for you, act on it; a
  small correction to a finished output is recorded with `work record-edit`.
  Discovery is one task per channel: the runtime handles `company_site` and
  `sitemaps`; each of the other eight channels gets its own worker.
- Workers act only under a held lease: claim and start before working, succeed
  only after outputs exist. Never let a worker run discovery or capture
  commands for a task it has not claimed. To add work to a closed channel,
  reopen it with `discovery reopen` and rerun `run` so the scheduler re-queues
  the task.
- Blocked captures are not the end of the line: the scheduler plans an
  alternate-copies pass once page captures finish (and a later pass for anything
  blocked after it), and its worker records a public copy of the same content,
  or that none exists, for every blocked source in its list.
- Do not invent source, page, batch, or worker quotas. Discovery channels close
  as `sufficient` against the numbered research questions or as `saturated`;
  triage then bounds extraction by those questions.
- Runtime-owned work (crawl, sitemap audit, capture and transcription,
  reducers, filing, digests) runs inside `run`; never hand it to an agent. Use `run --plan-only`
  while another `run` process is executing.
- Scripted work (crawling, capture, transcription, history, reducers) sizes its
  own parallelism to the machine's cores and memory; raise or lower it with the
  README's overrides only when the environment shows strain or slack.
- Concurrency is your call. Dispatch as many ready agent packets at once, and
  set runtime and scheduler limits to whatever finishes fastest without
  failures in the environment you are in (cores, memory, network, rate limits
  you hit). The configured numbers are defaults; see README for the overrides.
- Preserve single-writer reducer ownership, record concrete access blockers,
  and never edit scheduler state directly.
- The control agent's conversation is kept with the run: every save to
  GitHub adds what it gained since the last save to
  `08-control agent conversation history/` (secrets removed), and `run`
  saves, pushes, and confirms the push at the start of every phase. At the end
  of the run it is written as one file, checked by script against every
  earlier part, and the parts are deleted. Only write it, by those scripts;
  never read or review it unless the user asks. Questions after the run are
  not added.
- Keep the evidence. A run folder is ignored by the template's git, so after
  every `run` that captured or recaptured sources, and after each wave of
  workers, run `python3 -m research_control --root runs/<slug> archive`. It
  commits the run (captures, HTML, transcripts, facts, drafts, and a git
  bundle of every cloned repository) to the remote's `run-data/<slug>` branch.
  Never delete captures or transcripts after extraction; reuse them instead of
  capturing again.
- When the framework changes mid-run, change the template, commit, and run
  `python3 -m research_control --root runs/<slug> sync-engine` from the template
  checkout so the change is recorded in the run history.

## Model routing

Every packet names an advisory tier (`model_route` in its JSON and in the
`run` output). Extraction batches carry their own tier by the kind of source
they read: code, specs, and data on `standard`; recordings, pages, and business
records on `strong`. Claude Code can
select a model and effort per subagent, so apply the route on every dispatch:

| Tier | Model class | Subagent model | Effort | Task types |
|---|---|---|---|---|
| `frontier` | `strongest_available` | `fable` (Claude Fable 5.1) | `high` | cited-fact verification, devil's-advocate review, diagram modeling |
| `strong` | `flagship_capable` | `opus` (Claude Opus 5.5) | `high` | every task type not listed in another tier |
| `standard` | `balanced_capable` | `sonnet` (Claude Sonnet 5.5) | `medium` | discovery, triage, re-triage, filing spot check, language review |
| `economy` | `faster_capable` | `haiku` (Claude Haiku 5.5) | `low` | assembler |

Pass the tier's model and effort when launching the worker, and have the worker
record them on completion with
`work succeed TASK_ID --worker-id ID --model MODEL_ID --effort EFFORT`, using the
full model ID (`claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`). If
the host refuses a model, fall back to the available model and record the model
that actually ran; routing never blocks a task or relaxes a gate.
