TASK TYPE: FACT FILING AND LAYER-1 CHECKING

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
