TASK TYPE: COMPANY-BRIEF WRITING, NOT REVIEW OR STATUS

Read the evidence, writing, and runtime cores. Use only reviewed synthesis and
verified facts: `tools/outputs/cited-fact-rows.md` lists every cited fact with
its verdict, date, and deep link. Open `02-facts/` only to look up a fact by ID
that the table lacks; do not read the fact store whole. Follow the assigned word budget and exhibit specifications.
Keep fact IDs beside the exact supported words in Markdown.

Use `07-final-report/brand-guide.html` only to derive the brief's typography,
color, spacing, and print presentation. It is not factual evidence and must not
change the research claims, architecture, or citations. Record any designed
extension in `05-synthesis/design-notes.md`.

The brief is titled `company brief`, says **Focus: Product marketing**, and
does not presume employment. Answer in order: products and architecture;
buyers and buying motion; positioning and change; direction; competitors;
dependencies; neutral early questions and whom to ask; evidence limits; source
notes. Include one opening portfolio exhibit, one section-1 product map, and
one section-3 messaging timeline without duplication.

Before evidence limits, include a catalogue exhibit drawn from
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

Section 7 uses neutral first person and topical headings, not assignments to
employees. Section 8 uses reproducible counts and plain-language method names.

Create the company-brief citation map plus its element-level exhibit map. Each
citation record links rendered placement to fact IDs, source IDs, and the
fact's deep link from `tools/outputs/fact-links.jsonl` (the file and line at
a commit, the line in a diff, the recording's timestamp, or a text fragment
on the page), with the source's publisher and its posted and recorded dates
from `tools/outputs/source-dates.jsonl`. Do not expose fact IDs in rendered output, but do not
remove them from Markdown. The architecture-diagram tasks own the separate
model and SVG deliverables; do not create a one-page summary. Do not review
your own claim support. Run writing and fact-ID checks before return.
