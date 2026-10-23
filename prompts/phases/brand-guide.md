TASK TYPE: INDEPENDENT PUBLIC BRAND-GUIDE CONSTRUCTION

This packet starts at the beginning of the capture phase so its browser work,
asset inspection, rendering, and PDF QA can run concurrently with the much
longer company-research branch. Complete the packet in this independent agent
context. Do not wait for the research corpus and do not edit research facts,
source manifests, synthesis, architecture models, or company conclusions.

The company URL and scope map are your only inputs. Starting from that URL,
reverse-engineer the current public visual system and create these exact
outputs:

- `07-final-report/brand-guide.html`
- `07-final-report/brand-guide.pdf`
- `05-synthesis/brand-guide/evidence/source-map.md`
- `05-synthesis/brand-guide/evidence/design-observations.md`
- `05-synthesis/brand-guide/evidence/asset-manifest.csv`
- `05-synthesis/brand-guide/evidence/screenshots/`
- `05-synthesis/brand-guide/evidence/acceptance-check.md`

Use the run-local shared URL ledger without waiting for the research branch.
Before each materially different discovery pass, query already known research
leads with:

```bash
python3 -m research_control web list --purpose research_discovery
```

The listing is compact and paginated. Follow `next_offset` only while another
page could expose a materially different visual surface; the page size is an
output-safety bound, not a coverage or source-count target.

Register browser-only pages and fetch reusable public HTML, CSS, SVG, or other
raw assets through the controlled cache when useful:

```bash
python3 -m research_control web register --url URL \
  --consumer capture.brand-guide --purpose brand_discovery
python3 -m research_control web fetch --url URL \
  --consumer capture.brand-guide --purpose brand_asset
```

This is opportunistic reuse, not a dependency: begin from the company URL
immediately and never wait for research discovery. Ledger entries are leads and
cached bytes are transport artifacts, not brand evidence. Cite selected pages
and assets in the brand evidence outputs, and never move their factual content
into the research claim system. Continue to use a real browser for rendered
visual inspection even when raw bytes came from cache.

The HTML and PDF are final release artifacts. The PDF is the print counterpart
of the same guide, generated from its print mode rather than authored as a
separate design. Do not call either artifact an official guide unless the
company itself supplied it as official.

## Public-evidence boundary

Use only public pages and assets. Do not sign in, create accounts, evade access
controls, accept optional tracking merely to clear an overlay, or probe private
systems. A public login page may be inspected. Record blocked or inaccessible
surfaces rather than bypassing them.

The rendered experience is primary visual evidence, but HTML, computed CSS,
font declarations, assets, print styles, and public reports are also required
implementation evidence. Visual truth beats unused tokens. Vendor-default docs,
help, status, or developer themes are not company rules unless visibly
customized or corroborated elsewhere.

Discover materially different public visual surfaces from first-party links,
sitemaps, official subdomains, docs/help/developer properties, reports,
customer stories, newsroom/blog, careers, app/login, and public brand/media
assets. Coverage ends when another evidence-led pass finds no materially new
visual surface, template, identity asset, or design invariant. There is no
page-count target. Record every checked surface, access result, classification,
and inclusion decision in the source map.

## Evidence labels

Label consequential guide decisions as `Measured`, `Observed`, `Declared`,
`Inferred`, `Designed extension`, or `Improvement`. Never fabricate a font,
color, measurement, asset URL, license, or official rule. Preserve distinctive
identity anchors while clearly labeling accessibility, coherence, and editorial
improvements. List remote font/image dependencies and licensing or availability
caveats.

The asset manifest must use at least these columns, spelled exactly:
`Source URL`, `Type`, `Usage`, `Evidence label`, `Dimensions`, `Delivery`, and
`Notes`.

## Inspect and synthesize

Visually inspect every selected surface in a real browser. Use consistent
desktop and mobile viewports, gradual scrolling for lazy content, and
representative screenshots. Inspect navigation, hero, content, data/graphic,
conversion, footer, responsive, focus, hover, and print behaviors when present.
Compare marketing, documentation, product/login, and report surfaces rather
than averaging them into a generic style.

Measure representative typography, foreground/background colors, spacing,
container widths, borders, radii, shadows, grids, buttons, links, inputs,
cards, tables, callouts, charts, and breakpoint changes. Inventory canonical
logo variants, symbols, favicons, fonts/weights, imagery, illustrations, icons,
report assets, and chart treatments. Do not alter official logo geometry.

Synthesize a coherent system that distinguishes reproduced, consolidated,
extended, improved, and replaced-within-brand decisions. Include copyable
color, typography, spacing, shape, diagram-role, and print tokens directly in
the guide; list external dependencies and designed extensions.

## HTML guide content

Create a polished, responsive, self-contained HTML guide with semantic markup,
visible keyboard focus, working navigation/copy/print controls, reduced-motion
support, and no external script or stylesheet required for essential behavior.
Public fonts and images may remain remote only when disclosed in the asset
manifest and the guide has a usable fallback.

Cover, at minimum:

- identity summary and evidence map;
- logo provenance, variants, backgrounds, clear space, minimum size, and misuse;
- color roles, combinations, contrast, and copyable tokens;
- typography roles, weights, fallbacks, scale, line length, and specimens;
- layout, spacing, grid, breakpoints, borders, radii, and elevation;
- navigation, buttons, links, fields, cards, tables, callouts, and states;
- imagery, illustration, icon, motion, and accessibility direction;
- quantitative-chart roles, accessible/print modes, and fictional specimens;
- editorial diagrams and architecture graphics as defined below;
- reusable report/editorial page templates and print rules;
- a fictional landing-page specimen; and
- copyable CSS/SVG tokens plus a concise coding-agent style brief.

Use fictional or plainly labeled sample data. Do not invent customers, metrics,
endorsements, product architecture, technical relationships, or real-seeming
research claims.

## Editorial diagrams and architecture graphics

This section supplies visual ingredients to the later diagram builder's
style-mapping step. It is presentation guidance only and is not evidence about products, entities,
boundaries, integrations, or technical behavior.

Define diagram-safe typography for titles, subtitles/reading guides, node and
edge labels, annotations, legends, citations, captions, and source notes.
Define ink, neutral/group surfaces, boundary/divider, muted connector, and
restrained accent roles for light, dark, grayscale, and print modes. Define
node/container geometry; group, domain, external, human/service, interface,
and data/context ingredients; connector weights, bends, arrowheads, junctions,
labels, and crossing avoidance; caveat, inference, unresolved, numbering, and
citation treatments; icon/logo rules; and density patterns for taxonomy,
ordered flow, bounded domains, and focused dependencies.

Do not assign brand colors to company-specific facts or semantic categories.
The diagram builder owns that mapping. State explicitly that:

- line pattern encodes evidence class;
- arrowhead encodes direction;
- written edge label encodes required/optional/conditional qualifier;
- barred endpoint plus label encodes explicitly unsupported paths;
- boundary annotation encodes unresolved relationships; and
- fill/accent role encodes entity or domain identity.

Include publication rules for approximately 165 mm report width, effective
type near 9 pt or larger, print-safe line and marker sizes, responsive SVG
viewBox sizing, live text, dependable fallbacks, and no remote dependency for
essential meaning. If no coherent official diagram language exists, derive the
smallest extension from the strongest brand invariants and label it `Designed
extension`. Demonstrate only the visual grammar with clearly fictional
specimens; never imply company architecture.

## Render, inspect, revise

Render and slow-scroll the entire guide at desktop and mobile sizes. Render the
PDF to one image per page. Inspect every HTML section and PDF page for overflow,
clipping, overlap, missing assets/fonts/glyphs, broken controls, chart/diagram
ambiguity, low contrast, mobile ordering, page breaks, margins, headers,
footers, and print/grayscale legibility. Check selectable PDF text and extracted
text as secondary sanity checks. Fix defects, rerender, and reinspect; do not
deliver a known defect.

Place final source and QA screenshots under the evidence screenshot directory,
including desktop, mobile, and every PDF page. `acceptance-check.md` must record
PASS, NOT APPLICABLE, or BLOCKED plus
specific evidence for every requirement above. A blocked public source is an
evidence limitation; a blocked output, missing QA render, or known visual
defect is not completion.
