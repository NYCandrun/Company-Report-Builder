TASK TYPE: EDITABLE ARCHITECTURE DIAGRAM BUILD

Build from the validated `07-final-report/diagram-models.md` and
`tools/outputs/diagram-models.json`. Read the `Editorial diagrams and
architecture graphics` section of `07-final-report/brand-guide.html` for
presentation only. Do not browse, research, invent new
entities, add relationships, or upgrade H/U possibilities into facts. If the
layout exposes a model problem, correct both model files first and rerun the
model validator before rebuilding the affected SVG.

Produce these exact editable SVGs and the captions file:

- `07-final-report/01-product-capability-map.svg`
- `07-final-report/02-operating-model.svg`
- `07-final-report/03-enterprise-logical-architecture.svg`
- `07-final-report/04-technical-dependency-map.svg`
- `07-final-report/diagram-captions.md`
- `07-final-report/diagram-style-spec.md`

Before drawing, write the short style spec. It must include `Inputs and scope`,
`Semantic mapping`, `Connector channels`, `Typography and spacing`, and
`Designed extensions`. State that brand guidance controls presentation and is
not evidence. Map the guide's visual ingredients to the entity and boundary
types actually present in the validated model. Keep independent channels:
line pattern for evidence class, arrowhead for direction, written edge label
for qualifier, barred endpoint plus label for unsupported paths, boundary
annotation for unresolved paths, and fill/accent for entity or domain identity.
Include grayscale, print, and 165 mm rules. Do not change the model while doing
this mapping.

Every SVG must have `width="165mm"`, a responsive `viewBox`, true vector
geometry, selectable SVG text, and first-child `<title>` followed by nonempty
`<desc>`. Maintain logical DOM reading order. Do not use `<foreignObject>`,
scripts, screenshots, raster images, base64 assets, generic AI imagery,
decorative networks, fake server infrastructure, or remote dependencies needed
for essential meaning. Use dependable font fallbacks. Keep arrowheads, filters,
labels, and all geometry inside the viewBox. Avoid connectors crossing labels
or ambiguous junctions. Preserve meaning in grayscale.

Put `data-entity-id="STABLE_ID"` on the element that visually represents each
included entity and `data-relationship-id="STABLE_ID"` on each consequential
edge. Repeated entities retain the same stable ID and canonical label. Use consistent
entity-type colors and canonical labels across diagrams. Solid connections
mean D; dashed connections mean R. Label required, conditional, optional,
unsupported, and unresolved paths without relying on color alone. H must not
look established; U edges are omitted or shown only as a clearly unresolved
boundary.

The visible title and subtitle in each SVG are deterministic, not editorial.
Use these strings exactly, including capitalization and punctuation:

1. `Capability taxonomy / inventory`
   `What does this company offer, and how are its capabilities organized?`
2. `Operating model / behavior`
   `How does the product turn an input or need into an outcome?`
3. `Enterprise logical architecture / structure`
   `How are the major functional domains organized, and how does the platform relate to its environment?`
4. `Focused technical dependencies / receipts`
   `What consequential technical relationship, limitation, or architectural distinction does the research establish?`

Use distinct visual grammars: nested taxonomy for 01, ordered/branched
behavior for 02, bounded logical domains for 03, and a focused dependency
graph or supported-path comparison for 04. The diagrams should feel related
without recycling one card grid. Keep body labels approximately 9 pt or larger
at the declared 165 mm width.

For each figure, `diagram-captions.md` must repeat the exact deterministic
title and subtitle, then provide a concise evidence-backed takeaway, reading
guide, research references, significant R-class reconstructions, and essential
caveats. The takeaway belongs in the caption; it must not replace the fixed
visible title.

Render or open every SVG at the declared 165 mm publication width. Inspect it,
revise clipping, density, connector direction, ambiguity, contrast, grayscale
behavior, and hierarchy, then inspect again. Publication review will perform a
second independent final-size check and record it in the existing visual-review
artifact.
