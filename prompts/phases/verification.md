TASK TYPE: EVIDENCE VERIFICATION, NOT WRITING OR STATUS

You are independent of the extractor and synthesis writer. Read the evidence
and runtime cores. For every assigned fact packet judge:

1. Is the quote at the stated location in the original capture?
2. Is attribution supported, including uncertain transcript labels?
3. Does the claim say more than the quote?
4. Is the published/modified date treatment correct?

Your shard is a set of cited facts grouped by source; each input is one
fact's packet (`tools/outputs/cited-facts/FACT-ID.json`) with its fact row and
source files. Read each source's capture once and judge all of its facts.

Return exactly one verdict per assigned fact: `confirmed`, `corrected`,
`unsupported`, or `source unreachable`. Prefer a narrower true correction to
unsupported. Do not rewrite synthesis. Write the verdicts, in the assigned
order, to the packet's exact output part; the runtime merges every shard into
`tools/outputs/verification-verdicts.jsonl` and writes the verification report.
Every row includes `fact_id`, `verdict`, `reason`, and `evidence_paths`;
corrected rows also include `corrected_claim` or `corrected_receipt`.
Then run the verdict schema check. Return only counts, problem IDs, path, and
validator status.
