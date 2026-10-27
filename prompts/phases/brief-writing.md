TASK TYPE: COMPANY-BRIEF WRITING, NOT REVIEW OR STATUS

Read the evidence, writing, and runtime cores. Use only reviewed synthesis and
verified facts: `tools/outputs/cited-fact-rows.md` lists every cited fact with
its verdict, date, and deep link. Open `02-facts/` only to look up a fact by ID
that the table lacks; do not read the fact store whole. Follow the outline and
exhibit specifications below.
Keep fact IDs beside the exact supported words in Markdown.

Use `07-final-report/brand-guide.html` only to derive the brief's typography,
color, spacing, and print presentation. It is not factual evidence and must not
change the research claims, architecture, or citations. Record any designed
extension in `05-synthesis/design-notes.md`.

The report's outline is `tools/lists/report-outline.json`, built from this
run's own numbered research questions. The brief is titled `company brief`,
its cover says **Focus:** followed by the outline's `focus`, and it does not
presume employment. Write, in order:

1. An opening summary with one portfolio exhibit: every offering the company
   sells or delivers (products, services, engagement types), each marked
   `Stated`, `Inferred`, or `Lead` with its evidence.
2. One section for each entry in the outline's `sections`, in that order,
   headed by the question in plain words and answering it from the synthesis.
   Where a question asks how something changed, show the change with dates.
   Where its evidence is thin, say so briefly instead of filling the space.
   Put the product capability map in the section that answers the product
   question and the messaging timeline in the one that answers positioning,
   when those questions exist, without repeating either elsewhere.
3. When the outline's `accounts_exhibit.include` is true, an exhibit of
   accounts over time, in the section that answers the accounts or customer
   question: each account with its relationship mark, what the engagement is,
   its stages with dates, budgets as they moved, and its signs of landing,
   expanding, renewing, pausing, or churning.
4. The catalogue exhibit described below.
5. Open questions and whom to ask.
6. The limits of the evidence.
7. Source notes.

Keep the report's prose within the outline's `words` (`minimum` to `maximum`;
tables and other exhibits are not counted); `work check` counts them.

Before the open questions, include a catalogue exhibit drawn from
`05-synthesis/inference-catalogue.md` in four parts:
- "What the company sells", each offering marked `Stated`, `Inferred`, or
  `Lead` with its evidence, stated first and leads last below a dividing rule;
- "How the company works" and "What the work is", each listing inferences in
  order of strength with their supporting evidence, thin ones last below a
  dividing rule. Label these two parts as inference.
- "How it has changed", the dated timelines, each step with its date and
  delivery status (shipped, built but unmerged, or promised), labelled as
  inference where the sequence is read from change history.
Never present an inferred offering or an inference as an established fact
elsewhere in the brief.

The open-questions section uses neutral first person and topical headings,
not assignments to employees. The limits-of-the-evidence section uses
reproducible counts and plain-language method names.

Create the company-brief citation map plus its element-level exhibit map. Each
citation record links rendered placement to fact IDs, source IDs, and the
fact's deep link from `tools/outputs/fact-links.jsonl` (the file and line at
a commit, the line in a diff, the recording's timestamp, or a text fragment
on the page), with the source's publisher and its posted and recorded dates
from `tools/outputs/source-dates.jsonl`. Do not expose fact IDs in rendered output, but do not
remove them from Markdown. The architecture-diagram tasks own the separate
model and SVG deliverables; do not create a one-page summary. Do not review
your own claim support. Run writing and fact-ID checks before return.
