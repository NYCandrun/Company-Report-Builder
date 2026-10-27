# Claude Code execution adapter

Follow `README.md` as the operational entry point. Start a company run with
`python3 -m research_control new --url URL`, then work from inside its
`runs/<slug>/` directory: rerun `python3 -m research_control run` and dispatch
every ready packet until exact-artifact release passes.

- Give every independent ready packet its own isolated subagent and a unique
  worker ID. Discovery is one task per channel: the runtime handles
  `company_site` and `sitemaps`; each of the other eight channels gets its own
  worker.
- Workers act only under a held lease: claim and start before working, succeed
  only after outputs exist. Never let a worker run discovery or capture
  commands for a task it has not claimed. To add work to a closed channel,
  reopen it with `discovery reopen` and rerun `run` so the scheduler re-queues
  the task.
- Do not invent source, page, batch, or worker quotas. Discovery channels close
  as `sufficient` against the numbered research questions or as `saturated`;
  triage then bounds extraction by those questions.
- Runtime-owned work (crawl, sitemap audit, capture and transcription,
  reducers) runs inside `run`; never hand it to an agent. Use `run --plan-only`
  while another `run` process is executing.
- Concurrency is your call. Dispatch as many ready agent packets at once, and
  set runtime and scheduler limits to whatever finishes fastest without
  failures in the environment you are in (cores, memory, network, rate limits
  you hit). The configured numbers are defaults; see README for the overrides.
- Preserve single-writer reducer ownership, record concrete access blockers,
  and never edit scheduler state directly.
- When the framework changes mid-run, change the template, commit, and run
  `python3 -m research_control --root runs/<slug> sync-engine` from the template
  checkout so the change is recorded in the run history.

## Model routing

Every packet names an advisory tier (`model_route` in its JSON). Claude Code can
select a model and effort per subagent, so apply the route on every dispatch:

| Tier | Model class | Subagent model | Effort | Task types |
|---|---|---|---|---|
| `frontier` | `strongest_available` | `fable` (Claude Fable 5.1) | `high` | cited-fact verification, devil's-advocate review, diagram modeling |
| `strong` | `flagship_capable` | `opus` (Claude Opus 5.5) | `high` | every task type not listed in another tier |
| `standard` | `balanced_capable` | `sonnet` (Claude Sonnet 5.5) | `medium` | discovery, triage, filing, language review |
| `economy` | `faster_capable` | `haiku` (Claude Haiku 5.5) | `low` | assembler |

Pass the tier's model and effort when launching the worker, and have the worker
record them on completion with
`work succeed TASK_ID --worker-id ID --model MODEL_ID --effort EFFORT`, using the
full model ID (`claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`). If
the host refuses a model, fall back to the available model and record the model
that actually ran; routing never blocks a task or relaxes a gate.
