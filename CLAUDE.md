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
- Preserve single-writer reducer ownership, record concrete access blockers,
  and never edit scheduler state directly.
- When the framework changes mid-run, change the template, commit, and run
  `python3 -m research_control --root runs/<slug> sync-engine` from the template
  checkout so the change is recorded in the run history.
