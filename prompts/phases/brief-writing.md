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

The report's outline is `tools/lists/report-outline.json`. The brief is a
company brief for a reader who wants to understand the whole company: titled
`company brief`, its cover says **Focus:** followed by the outline's `focus`,
and it does not presume employment. It is arranged top down, from broad
context to specifics, not in the order the research questions are numbered.
The research questions are a checklist the report must answer, not its
headings: many are written into the scope by default rather than asked by
the reader. Write, in order:

1. An executive summary: what the company is, what it sells, whom it sells
   to, how it is doing, how it has changed, and the most important
   uncertainties, each point grounded in the parts below. A short
   at-a-glance table may open it.
2. Each part in the outline's `parts`, in that order, under the part's
   heading. Answer every question the part `covers`, under plain topical
   subheadings (for example "Partnerships with AI labs and cloud providers"),
   never phrased as the question and never as "you asked". Open each part
   with one or two sentences that state its main point, then go from the
   general to the specific. Where something changed, show the change with
   dates. Where evidence is thin, say so briefly instead of filling the space.
   - The part on what the company sells opens with a portfolio exhibit of
     every offering (products, services, engagement types), each marked
     `Stated`, `Inferred`, or `Lead` with its evidence, and holds the product
     capability map.
   - The part on market and positioning holds the messaging timeline.
   - When the outline's `accounts_exhibit.include` is true, the part on
     customers holds an exhibit of accounts over time: each account with its
     relationship mark, what the engagement is, its stages with dates, budgets
     as they moved, and its signs of landing, expanding, renewing, pausing,
     or churning.
   No exhibit is repeated in another part.
3. The catalog exhibit described below.
4. Open questions and whom to ask.
5. The limits of the evidence.
6. A `## Sources` heading with nothing under it: the build lists every cited
   source there, numbered, once.

There is no length target. The report is as long as the evidence needs and no
longer: every question answered with the facts that bear on it, in tight
copy, with no filler and no tangents. Give an exhibit a title that states its
takeaway as a sentence, and say beneath it where its figures come from. Give
every number its date and basis, and say when a figure is your own
calculation or comes secondhand.

Before the open questions, include a catalog exhibit drawn from
`05-synthesis/inference-catalogue.md` in four parts:
- "What the company sells", each offering marked `Stated`, `Inferred`, or
  `Lead` with its evidence, stated first and leads last below a dividing rule;
- "How the company works" and "What the work is", each listing inferences in
  order of strength with their supporting evidence, thin ones last below a
  dividing rule. Label these two parts as inference.
- "How it has changed", the dated timelines, each step with its date and
  delivery status (shipped, built but unmerged, or promised), labeled as
  inference where the sequence is read from change history.
Never present an inferred offering or an inference as an established fact
elsewhere in the brief.

The open-questions section uses neutral first person and topical headings,
not assignments to employees. The limits-of-the-evidence section uses
reproducible counts and plain-language method names.

Cite with fact IDs only: put them in square brackets right beside the exact
words they support, in prose and in every table cell that states a fact (for
example `[PRD-001, PRD-014]`). Do not write citation numbers, source notes, the
citation map, or the exhibit map. `work check` builds them from your fact IDs:
it numbers each source on first use in reading order, links every superscript
number to the cited fact's deep link (the line at a commit, the moment in a
recording, the quoted words on a page), lists each source once with its grade,
publisher, and date, and maps each table cell to its facts. It also lists any
body paragraph or table row that cites no fact, and any fact that is unknown or
withdrawn: fix each in the Markdown and run it again. Rendered output never
shows fact IDs. The architecture-diagram tasks own the separate
model and SVG deliverables; do not create a one-page summary. Do not review
your own claim support. Run writing and fact-ID checks before return.

Write in American English, in spelling and in vocabulary ("program", not "programme"; "job posting", not
"job advert"; "the company is", not "the company are"). Quotes, quoted titles, and names keep the
source's spelling. `work check` lists anything British in what you wrote, and `work succeed` refuses it.
