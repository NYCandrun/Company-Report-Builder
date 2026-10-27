TASK TYPE: EXTRACTION WORK, NOT A STATUS QUESTION

Read the runtime and evidence cores. Read every assigned canonical extract or
explicit source slice in full. Sampling, `head`, `sed`, or `grep` is not a
substitute. Write only the packet's private candidate and disposition JSONL
parts so work is resumable; the reducer owns the canonical stores.

There is no fact count in either direction: extract everything the assigned
text supports that bears on the research questions, and nothing outside them.

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
- What was built and delivered: each system, tool, integration, deliverable,
  or service the company actually built or delivered, for whom (with its
  relationship mark), when, and the evidence that it was built or delivered
  (shipped code, a repository shaped to a client, a recorded handover, use,
  or follow-on work), kept apart from what was sold, proposed, or promised.
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
- Large files: a file headed `(data sample: …)` is a dataset too large to
  include; its header gives its size, record count, and shape, and the sample
  its first records. State totals from the header, never by counting the
  sample. A file headed `(HTML, as text)` is a page's text, not its markup.

Keep notes short: the marks this prompt asks for (delivery status,
relationship basis, scope, date basis, `Recorded:` date, sourcing) and at most
one sentence of qualifier. Do not restate the claim or the quote, explain where
you looked, or argue an inference in notes: an inference is its own fact,
starting `My inference:`.

Mark each fact's delivery status in notes:
- `Shipped`: on the default branch and implemented in its code.
- `Built, unmerged: <branch or pull request>`: implemented on a branch or pull
  request that the default branch does not contain. It is done but not
  shipped; date it by its own commits. A pull request whose page shows it
  merged is Shipped even when its commits appear as unmerged (it was merged
  by squash or rebase).
- `Promised`: described in a README or other doc but not implemented in the
  code captured. A doc is not proof that a capability exists.

README and docs are also evidence of one of two scopes: what the company
offers in general (generic, reusable, described for any buyer) or the scope
of one engagement (shaped to a named client's data, brand, systems, or
deliverables). Say which in notes (`Scope: offering` or `Scope: engagement,
<client>`), and record a client named only by a repository's or file's
subject as a relationship with its mark.

## Business records and conversations

Some sources record the business itself: account books, deal and pipeline
notes, call notes and summaries, proposals, statements of work, org charts,
plans and forecasts, and recorded talks, interviews, and podcasts in which
the company's people or its clients describe the work. Extract them as
thoroughly as code, one fact per distinct claim:

- People and roles: who is involved on each side and what they do (the
  company's people by name and role; client and prospect staff by role and
  organization only, never by name).
- Accounts: each account's status, what has happened in it, and what is
  happening now; what the engagement actually is (scope, deliverables, team,
  phase).
- Timelines: start dates, milestones, deadlines, and every shift in them,
  with both the earlier and the later date.
- Budgets and money: contract values, budgets, rates, bookings, revenue, and
  every change in them, with both figures and their dates. Plans and
  forecasts stay plans.
- Built and delivered: what the company actually built, shipped, or
  delivered for each account (systems, deliverables, workshops, staff
  placed), as the record shows it, and how that differs from what was sold
  or proposed.
- Projects: what each project is, its stage, and how its scope and stage
  shifted.
- Land, expand, churn: first engagements, follow-on phases and expansions,
  pauses, losses, and renewals, each as recorded. A pattern the steps suggest
  (a sales cycle's length, an expansion path, likely churn) is inference with
  the steps' fact IDs.
- What was said: statements by clients and by the company on calls, in
  meetings, or in talks that bear on any of the above, quoted, attributed (the
  company's speakers by name, client speakers by role and organization), and
  dated by the call or recording. Say whether a statement is a commitment, a
  request, a concern, or an opinion.
- Contradictions: where two records, two versions, or a record and a public
  statement disagree, extract both with their dates and say so in notes.
- Recording dates: a recording is dated by when it was posted
  (`tools/outputs/source-dates.jsonl`). When the recording itself states or
  implies when it was recorded (a date said aloud, a named event, "this week
  we launched X"), extract that as a fact with topic `recording date` and
  notes `Recorded: YYYY-MM-DD; basis: <what is said, at [hh:mm:ss]>`. When it
  differs from the posted date, what was said is dated by the recording.
- Sourcing: in notes, name the file, section, call, or recording each fact
  comes from, and for a repository the commit that last changed it (its date
  is when it was edited or pushed).

Date each repository fact by the commit that introduced the quoted content
(from the change history or commit log), not only by the repository's last
commit, and say which in notes. Quote single lines from a diff without its
leading `+` or `-`.

Locations are how citations resolve, so make them exact: for a recording, the
`[hh:mm:ss]` timestamp of the quoted passage; for a repository, the file path
(or commit, branch, or pull request) and line; for a page, the section
heading. Every fact also gets a deep link computed from its quote after
extraction (`tools/outputs/fact-links.jsonl`), so quote the source's exact
words.

Set each candidate's `source_date` from the source's row in
`tools/outputs/source-dates.jsonl` (content date and basis), or from a date
the source states for that specific fact when it is more precise. Never
present a capture date as a publication date.

When an input's source is listed in `tools/lists/supplement-sources.json`, it
was recaptured with more content, or listed again for a new question, after
its earlier facts were filed. Extract everything its text supports across
every dimension above and the questions the list's reason names, and say in
notes where the text corrects or dates an earlier claim more precisely. Do not
search earlier facts or candidates: duplicates are removed after extraction.
