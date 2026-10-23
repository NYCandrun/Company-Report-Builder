TASK TYPE: INDEPENDENT FULL VISUAL REVIEW

You did not author or lay out these pages or diagrams. Open every assigned
company-brief page preview (PNG when the runtime provides rasterization,
otherwise the generated SVG) in numeric page order with no sampling. Also
inspect the final HTML in a browser. Open all four architecture SVGs at their
declared 165 mm publication width. Write exactly one record per numbered brief
page and one record per diagram, including clean artifacts.
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
or write one clean record when every page is clean.
