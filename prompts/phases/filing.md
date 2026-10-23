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
