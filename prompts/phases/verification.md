TASK TYPE: EVIDENCE VERIFICATION, NOT WRITING OR STATUS

You are independent of the extractor and synthesis writer. Read the evidence
and runtime cores. For every assigned fact packet judge:

1. Is the quote at the stated location in the original capture?
2. Is attribution supported, including uncertain transcript labels?
3. Does the claim say more than the quote?
4. Is the published/modified date treatment correct?

Your shard is a set of cited facts grouped by source; each input is one
fact's packet (`tools/outputs/cited-facts/FACT-ID.json`) with its fact row,
source files, and `excerpt`: the quote as the runtime located it in the
capture, with the text around it, the capture's first lines (title,
repository, speakers), and the section it sits in (a file, commit, or pull
request header). Judge from the excerpt. Open the capture only where the
excerpt is not enough: the quote was not located (`located: false`), or
attribution or dating depends on text outside it (a speaker named earlier in a
transcript, a commit date above a long diff). Do not read whole captures
otherwise.

Return exactly one verdict per assigned fact: `confirmed`, `corrected`,
`unsupported`, or `source unreachable`. Prefer a narrower true correction to
unsupported. Do not rewrite synthesis. Write the verdicts, in the assigned
order, to the packet's exact output part; the runtime merges every shard into
`tools/outputs/verification-verdicts.jsonl` and writes the verification report.
Every row includes `fact_id`, `verdict`, `reason`, and `evidence_paths`;
corrected rows also include `corrected_claim` or `corrected_receipt`.
Then run the verdict schema check. Return only counts, problem IDs, path, and
validator status.

Each fact's deep link (`tools/outputs/fact-links.jsonl`) opens the source at
the quoted words; use it, and the capture it was computed from, to check the
quote in place.

When a fact rests on a repository describing something big or ambitious (a
platform, a product, an agent system), you may make a bounded check of its
code to judge whether it was built or was an idea started and dropped: the
file tree, the size and span of its history (commit count, first and last
commit dates), and a few key files (entry points, the main module, a
configuration that wires it together), from the capture, a shallow clone
(`git clone --depth 50 --filter=blob:none`), or its archived copy. Read no
more than about a dozen files and no full history. Say what the code shows in
the verdict's reason, and correct the claim when the code shows only a start
(for example "described as a platform; the repository holds a prototype of
one component, last changed in March 2025").

Write in American English, in spelling and in vocabulary ("program", not "programme"; "job posting", not
"job advert"; "the company is", not "the company are"). Quotes, quoted titles, and names keep the
source's spelling. `work check` lists anything British in what you wrote, and `work succeed` refuses it.
