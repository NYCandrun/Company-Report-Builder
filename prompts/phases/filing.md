TASK TYPE: FACT FILING AND LAYER-1 CHECKING

The runtime performs filing (`research_control/filing.py`) by these rules, and
a reviewer spot-checks a sample (`filing-spot-check.md`). This file is the
specification; an agent follows it only when filing is assigned to one.

Read the runtime and evidence cores. Process every candidate in
`tools/candidates/all.jsonl`. Give every candidate one terminal disposition in
`tools/outputs/filing-dispositions.jsonl`.

Merge facts only through explicit dispositions. Preserve conflicts and likely
duplicates. Write topic fact tables under `02-facts/` with all required receipt
fields. Use stable final fact IDs, normalize tags, and flag overstatement-risk
language. Never silently discard a candidate.

Run duplicate, conflict, quote, location, date, source-ID, tag, and
overstatement checks. Record the script audit and the required independent
duplicate and filter spot checks in `06-checks/`. A zero-fact topic still needs
an explicit disposition and audit record.

When filing again after new or re-extracted candidates, keep the fact ID of
every fact already in `02-facts/`: a candidate with the same source ID and
quote as a filed fact takes that fact's ID, and only new facts get new IDs.
Verification verdicts and synthesis citations are keyed by fact ID, so an
unchanged fact must not be renumbered.

When `tools/lists/supplement-sources.json` exists, those sources were
recaptured with more content and re-extracted as a supplement. Leave every
fact row already in `02-facts/` unchanged. File only candidates that are not
already filed: one with the same source ID and quote as a filed fact gets a
`duplicate` disposition naming that fact; every other candidate is appended
under a new fact ID.

A candidate marked `duplicate_of` repeats a filed fact or an earlier candidate
with the same source and quote (the reducer marks them, so extraction passes
over the same text need no cross-checking). Do not file it; record it as a
duplicate of that ID. Near-duplicates the reducer cannot see (the same claim
quoted differently) are yours to merge as before.
