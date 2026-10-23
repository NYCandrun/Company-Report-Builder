TASK TYPE: EVIDENCE VERIFICATION, NOT WRITING OR STATUS

You are independent of the extractor and synthesis writer. Read the evidence
and runtime cores. For every assigned fact packet judge:

1. Is the quote at the stated location in the original capture?
2. Is attribution supported, including uncertain transcript labels?
3. Does the claim say more than the quote?
4. Is the published/modified date treatment correct?

Return exactly one verdict per assigned fact: `confirmed`, `corrected`,
`unsupported`, or `source unreachable`. Prefer a narrower true correction to
unsupported. Do not rewrite synthesis. Preserve the assigned order and IDs in
the verdict file, then run the verdict schema check. Return only counts,
problem IDs, path, and validator status.
