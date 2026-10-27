TASK TYPE: FINDINGS AND REPORT PLAN, NOT THE REPORT

This is the step between knowing the facts and writing about them. The
synthesis files lay the evidence out by topic; the report must tell a reader
what it means. Read the evidence, writing, and runtime cores, then the scope's
research questions and focus, the report outline
(`tools/lists/report-outline.json`), every reviewed synthesis file, the
timelines, and the fact digests in `tools/digests/` (one line per fact). Open a
fact's full row only when its wording or date matters, by searching
`02-facts/` for its ID; do not read the store whole. Write
`05-synthesis/findings.md`, or revise it if it exists. Every finding in it is
your inference from the cited facts: say so once at the top instead of
prefixing each one.

1. **The company in one paragraph.** What it is, what it sells, to whom, how
   it is doing, and where it is going, in plain words for a reader who meets
   the company for the first time, with fact IDs beside each claim.

2. **Findings.** Eight to fifteen numbered conclusions, ordered by what
   matters most to a reader who wants to understand the company. For each:
   - the conclusion, in one plain sentence: what the reader should take
     away, not a fact restated;
   - why it matters;
   - the evidence, strongest first: fact IDs and, in a few words each, what
     they show;
   - how strong it is (`strong`, `moderate`, or `thin`, as the inference
     catalog defines them) and what cuts against it;
   - what changed over time, with dates, when the finding is about a change.

   Join evidence that belongs together. When sources of different kinds
   describe the same thing (a demo recording and the repository it produced,
   a plan and the hiring that followed, a case study and the customer's own
   post), present them as one thing with all of its sources, and say what the
   whole shows that no single source does. Where sources disagree, say which
   reading the evidence favors and why, keeping both visible with their dates.

3. **What the evidence does not show.** The gaps that change how the company
   should be read, each scoped to the sources searched, so the report says
   each one once.

4. **The report plan.** For the executive summary: the five to eight
   sentences it must make, in order. Then for each part of the outline, in
   order: the part's main point in one sentence (what the reader should
   conclude from it); its sub-points in order, each with the findings and
   fact IDs that go under it; the exhibits it needs, each with its
   one-sentence takeaway, what kind of thing its rows are, its columns (at
   most five) in order, and the rule its rows are sorted by; and what to
   leave out (evidence that does not change the reader's understanding of
   the company, with the reason). The outline's parts and the questions each
   covers are a checklist; the plan decides the order and weight within them.

5. **Qualifiers to say once.** The caveats a reader needs (evidence more than
   two quarters old, a speaker whose identity is probable, proof the company
   wrote itself, plans rather than results, a relationship that is inferred
   or a lead) and the one place in the report where each is said, so the
   prose does not repeat them in every sentence. Relationship marks stay one
   word wherever a relationship appears.

Keep aims apart from achievements, product from staff-delivered work, and
fact from inference. Add no facts: everything rests on fact IDs that exist in
the store. Do not write the report, review your own claim support, or edit
the synthesis files. Run the fact-ID and writing checks before return.

Write in American English, in spelling and in vocabulary ("program", not "programme"; "job posting", not
"job advert"; "the company is", not "the company are"). Quotes, quoted titles, and names keep the
source's spelling. `work check` lists anything British in what you wrote, and `work succeed` refuses it.
