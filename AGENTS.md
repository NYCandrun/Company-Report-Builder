# Codex execution adapter

Follow `README.md` as the operational entry point. Start a company run with
`python3 -m research_control new --url URL`, then work from inside its
`runs/<slug>/` directory: run `python3 -m research_control run`, dispatch every
ready packet, and repeat until exact-artifact release acceptance passes. Use
subagents for packets marked independent. Give each a unique worker ID, the
packet only, and no inherited status conversation. The SQLite scheduler, not
the parent chat, determines the task graph, retries, dependencies, and
concurrency.

Discovery is one task per channel: the runtime crawls `company_site` and audits
`sitemaps`; each of the other eight channels gets its own worker. Workers act
only under a held lease; discovery commands refuse to change a channel whose
task is not claimed. To add work to a closed channel, reopen it with
`discovery reopen` and rerun `run`. Runtime-owned work (crawl, sitemap audit,
capture and transcription, reducers) runs inside `run` and is never dispatched.
Concurrency is the orchestrator's call: tune agent dispatch and runtime limits
to whatever is most efficient in the current environment; the configured
numbers are defaults.

Do not ask the user for source, page, batch, or worker counts. Search channels
close as `sufficient` against the numbered research questions in `00-scope.md`
or as `saturated`; triage bounds extraction by the same questions. Numeric
limits are safety breakers and must produce incomplete status when reached.

Do not skip a failed control, edit scheduler state directly, or claim completion
without a passing release manifest. When repository instructions and a packet
conflict, block that packet and report the conflict; unrelated ready work may
continue. Framework changes during a run go into the template first and reach
the run through `sync-engine`, which records them in the run history.
