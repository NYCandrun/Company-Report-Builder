TASK TYPE: FILING SPOT CHECK

The runtime filed the extraction candidates: duplicates of a filed fact were
recorded against it, near-duplicates (same source and claim, or one quote
containing the other) were merged by script, quotes not found in their
captured source were rejected, and every other candidate was appended to its
question's fact table. You check a sample of that work, independently.

Read the evidence and runtime cores and `tools/outputs/filing-spot-sample.json`:
`merges` (near-duplicate merges, each naming the kept fact) and `filed` (filed
facts, each with its quote, the question it was filed under, and the captured
text around the quote). Open a fact's row by searching `02-facts/` for its ID;
do not read the fact store or the captures whole.

- `06-checks/duplicate-spot-check.md`: for each sampled merge, whether the
  merged candidate and the kept fact make the same claim from the same source
  (a correct merge) or say something different (a wrong merge, so a fact was
  lost), with the IDs.
- `06-checks/filter-spot-check.md`: for each sampled filed fact, whether the
  quote is in the captured text, the claim stays within the quote, and the
  question it was filed under fits.

Give each file a table with one row per sampled item, the counts checked and
wrong, and a line for each problem naming the candidate or fact ID and what is
wrong. Write nothing else.

Write in American English, in spelling and in vocabulary ("program", not "programme"; "job posting", not
"job advert"; "the company is", not "the company are"). Quotes, quoted titles, and names keep the
source's spelling. `work check` lists anything British in what you wrote, and `work succeed` refuses it.
