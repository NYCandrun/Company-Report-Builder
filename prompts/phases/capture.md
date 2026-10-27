TASK TYPE: CAPTURE WORK, NOT A STATUS QUESTION

Read `prompts/core/runtime.md` and `prompts/core/evidence.md`, `00-scope.md`,
then process only the immutable source IDs or URLs in the assignment. The
orchestrator may perform this task sequentially when the source list is still
being discovered.

For each item, write exactly one terminal disposition: `completed`,
`duplicate`, `excluded`, or `blocked`, with reason and evidence path. A capture
has raw evidence plus the required text or transcript derivative and metadata.
Do not treat an HTTP success or a manifest row alone as capture completion.

Web captures retain URL, capture timestamp, title, method, raw HTML, and text
copy. PDFs retain the original and text with explicit page markers. Transcripts
retain URL, embedding page when relevant, live and upload dates, series,
reliably identified speakers/titles, title source, duration, method, known
caption errors, and timestamps around every 30 to 60 seconds. Preserve
one-word rolling-caption lines.

Parallel workers write only assigned manifest parts, blocked parts, evidence
paths, and scratch directories. The orchestrator performs the deterministic
single-writer merge into the canonical manifest. Respect host pacing.

The completed phase must include the canonical manifest, publish-date overlay,
blocked log, coverage report, extraction work list, and one disposition per
manifest source in `tools/outputs/capture-dispositions.jsonl`. Return counts and
paths only after the local capture validator passes.
