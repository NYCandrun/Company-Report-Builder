TASK TYPE: EXTRACTION WORK, NOT A STATUS QUESTION

Read the runtime and evidence cores. Read every assigned canonical extract or
explicit source slice in full. Sampling, `head`, `sed`, or `grep` is not a
substitute. Write only the packet's private candidate and disposition JSONL
parts so work is resumable; the reducer owns the canonical stores.

Each candidate ID must use the packet metadata's `candidate_id_prefix` followed
by a zero-padded worker-local sequence. Each candidate contains `topic`,
`claim`, `quote`, `source_id`, `location`,
`source_date`, `grade`, `about`, `said_by`, and `notes`. Use only the assigned
topic/output and ID bounds. Self-check every quote against the original capture
before completing the source.

When a fully read input or slice yields no facts, write an explicit
`completed_zero` disposition with the immutable input ID, its `source_id`, and
evidence path. Do not silently omit it. Include `source_id` on every slice
disposition so the reducer can produce exactly one final disposition per
canonical source.
Report assigned sources, sources read, candidate count, zero-fact count,
exceptions, output path, and validator result.

## Repositories

A repository is dense evidence; extract it thoroughly, not as a summary. For
each repository cover, with one fact per distinct claim:

- What it is: its name, purpose, audience, and status as the repository
  presents it.
- What the docs say: each capability, workflow, deliverable, client, partner,
  model, or integration the README and other docs describe.
- How it works: its architecture, components, models and APIs called, data it
  reads and writes, configuration, prompts, and integrations, from the code.
- What it seems to do: behavior the code implements that the docs do not
  state. This is inference: start the claim with `My inference:` and cite the
  code lines.
- How it changed: when it was created, each material change and its date,
  what an earlier version said that a later one replaced (removed `-` lines in
  the change history), and the timeline these make.
- Progress: in data files that change over time (account books, pipelines,
  plans, org charts, project trackers), each change of stage, value, owner,
  headcount, or date, with both versions and both dates. Several such changes
  for one deal or project make a timeline: record each step, and record the
  sales cycle, expansion, or apparent churn they suggest as inference with its
  steps' fact IDs.

Mark each fact's delivery status in notes:
- `Shipped`: on the default branch and implemented in its code.
- `Built, unmerged: <branch or pull request>`: implemented on a branch or pull
  request that the default branch does not contain. It is done but not
  shipped; date it by its own commits.
- `Promised`: described in a README or other doc but not implemented in the
  code captured. A doc is not proof that a capability exists.

README and docs are also evidence of one of two scopes: what the company
offers in general (generic, reusable, described for any buyer) or the scope
of one engagement (shaped to a named client's data, brand, systems, or
deliverables). Say which in notes (`Scope: offering` or `Scope: engagement,
<client>`), and record a client named only by a repository's or file's
subject as a relationship with its mark.

Date each repository fact by the commit that introduced the quoted content
(from the change history or commit log), not only by the repository's last
commit, and say which in notes. Quote single lines from a diff without its
leading `+` or `-`.

Set each candidate's `source_date` from the source's row in
`tools/outputs/source-dates.jsonl` (content date and basis), or from a date
the source states for that specific fact when it is more precise. Never
present a capture date as a publication date.

When an input's source is listed in `tools/lists/supplement-sources.json`, it
was recaptured with more content after its earlier facts were filed. Read the
facts already filed from it (search `02-facts/` for its source ID) and extract
what they do not already cover, across every dimension in "Repositories"
above (earlier passes were thinner than these rules ask), plus any earlier
claim the new text corrects or dates more precisely (say so in notes). Do not
re-extract a fact already filed.
