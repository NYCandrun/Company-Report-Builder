TASK TYPE: EXTRACTION WORK, NOT A STATUS QUESTION

Read the runtime and evidence cores. Read every assigned canonical extract in
full. Sampling, `head`, `sed`, or `grep` is not a substitute. Append JSON Lines
source by source so work is resumable.

Each candidate contains `topic`, `claim`, `quote`, `source_id`, `location`,
`source_date`, `grade`, `about`, `said_by`, and `notes`. Use only the assigned
topic/output and ID bounds. Self-check every quote against the original capture
before completing the source.

When a fully read source yields no facts, write an explicit `completed_zero`
disposition with the source ID and evidence path. Do not silently omit it.
Report assigned sources, sources read, candidate count, zero-fact count,
exceptions, output path, and validator result.
