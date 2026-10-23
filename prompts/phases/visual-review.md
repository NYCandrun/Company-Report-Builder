TASK TYPE: INDEPENDENT HASH-SCOPED VISUAL REVIEW

You did not author or lay out these pages or diagrams. Read
`tools/outputs/review-scope.json`. On the first review it assigns every surface
to `inspect`. On later reviews, open every target marked `inspect`, with no
sampling. A target marked `reuse` may retain its prior clean record only when
the record's `artifact_sha256` exactly equals the scope hash. Never reuse an
issues record or a record without a matching hash. Also inspect the final HTML
in a browser whenever either its desktop/mobile target or any placed report
page is marked `inspect`. Open changed architecture SVGs at their declared 165
mm publication width. The final JSON must still contain exactly one current
record per numbered brief page and per diagram, including reused clean records.
Also inspect `brand-guide.html` end to end at desktop and mobile widths and
render and inspect every page of `brand-guide.pdf`. Confirm the four diagrams
remain legible and unclipped where they are placed inside the company-brief
HTML, not only as standalone SVGs.
Check edges, citations, padding, gaps, margins, crowded or stretched exhibits,
stranded headings, orphans, one-word wraps, citation-only lines, split dates,
styling, leftover markup, odd characters, paths, fact IDs, and any other
reader-visible defect. For diagrams also check title/subtitle accuracy,
publication-size legibility, clipping, reading order, connector direction,
label ambiguity, D/R line semantics, model-to-drawing consistency, and whether
required/conditional/optional distinctions remain legible without color.

Each issue records page, location, issue, severity, and proposed fix. Do not
edit. Distinguish observed symptom from uncertain diagnosis. Write both the
assigned Markdown report and `06-checks/visual-review.json`. Page count in the
JSON `pages` records must equal the renderer's expected page count. The JSON
must also contain `diagrams`, with exactly one record for each canonical
diagram ID, `review_width_mm: 165`, `status`, and `issues`. Mirror each issue
with a stable finding ID in `tools/outputs/publication-findings-visual.jsonl`,
or write one clean record when every page is clean. It must additionally contain
`brand_guide.html` records for `desktop` and `mobile` and one `pdf_pages` record
for every brand-guide PDF page:

```json
"brand_guide": {
  "html": [
    {"viewport": "desktop", "status": "clean", "issues": []},
    {"viewport": "mobile", "status": "clean", "issues": []}
  ],
  "pdf_pages": [
    {"page": 1, "status": "clean", "issues": []}
  ]
}
```

Every page, diagram, HTML viewport, and brand-PDF page record must include the
exact `artifact_sha256` from the review scope. Report how many targets were
inspected and how many unchanged clean records were reused.
