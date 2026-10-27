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

For a repository, its README and other docs are evidence of one of two scopes:
what the company offers in general (generic, reusable, described for any
buyer) or the scope of one engagement (shaped to a named client's data,
brand, systems, or deliverables). Say which in the fact's notes
(`Scope: offering` or `Scope: engagement, <client>`), and record a client
named only by a repository's or file's subject as a relationship with its
mark.

A repository capture also holds the default branch's commit history and a
"work not on the default branch" section: branches and pull requests whose
commits are unmerged. Unmerged work is proposed or in progress, not shipped:
say `Unmerged: <branch or pull request>` in the fact's notes, never describe
it as something the code does, and date it by that block's own commits. Use
the commit history to date when a feature or file appeared.

Set each candidate's `source_date` from the source's row in
`tools/outputs/source-dates.jsonl` (content date and basis), or from a date
the source states for that specific fact when it is more precise. Never
present a capture date as a publication date.
