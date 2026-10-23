TASK TYPE: REVIEW FIX APPLICATION, NOT NEW REVIEW

Read every assigned finding and the evidence relevant to it. Give each finding
exactly one disposition: `apply`, `apply_in_part`, or `reject`, with a reason.
Apply accepted changes only to assigned artifacts. Preserve quotes, IDs, dates,
and unrelated copy unless the finding specifically establishes an error.

Record decisions as JSONL in the assigned decision file and keep a readable
Markdown summary. Record evidence paths for applied changes. Run fact-ID and
writing validators. Return counts for all three dispositions, outstanding
mandatory fixes, changed paths, and validator status. A declared `apply`
without a changed/evidence path is incomplete.
