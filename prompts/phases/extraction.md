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
