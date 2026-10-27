TASK TYPE: SCOPE AND SOURCE-MAP WORK

Read the runtime and evidence cores, the company URL in the run state, and all
user-provided material in `00-inputs/`. Inspect the company homepage before
fixing scope.

Write `00-scope.md` with the company record, flagship and product boundaries,
first-party surfaces, people, careers, investor, press, developer, media,
third-party, and competitor source plans. Name likely ambiguities and make a
recommended decision unless the company's identity or the requested subject is
genuinely ambiguous.

Include a `## Research questions` section. Number every question with a stable
ID (`Q1`, `Q2`, ...). Start from the brief's required sections, in order:

- Q1 product and architecture;
- Q2 buyer and buying motion (packaging, pricing signals, how a buyer starts);
- Q3 customers and proof, and who authored that proof;
- Q4 positioning and how it has changed;
- Q5 stated direction, actual launches, and unresolved roadmap questions;
- Q6 people and organization signals;
- Q7 competitors and defensible comparisons;
- Q8 dependencies around the products in focus;

then add company-specific questions from Q9 onward. Under each question, name
the source channels most likely to answer it. Discovery workers close channels
as sufficient against these IDs, and triage selects sources for extraction by
them, so phrase each question so a source can be judged against it.

Do not capture the corpus. The runtime crawls the company site and captures
admitted sources itself. Do not omit an input. Account for every provided input
and state whether it is direction, a source, a prior report, or design
guidance. Write one terminal record per file to
`tools/outputs/input-classification.jsonl`, using its repository-relative path
as `input_id`. If `00-inputs/` is empty, write one `completed_zero` record for
`__none__` with `00-scope.md` as evidence.

Write the scope in American English, in spelling and in vocabulary: questions, notes, and decisions
("program", not "programme"; "job posting", not "job advert"). Names and quoted titles keep their
spelling. `work check` lists anything British, and `work succeed` refuses it.
