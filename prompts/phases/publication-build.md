TASK TYPE: PUBLICATION ASSEMBLY

Read the runtime and writing cores. Do not rewrite research conclusions. Build
the assigned HTML and PDF artifacts from the approved Markdown, citation maps,
exhibit map, and design files by running:

```bash
python3 -m research_control render
```

Confirm the company-brief HTML and PDF plus
`tools/outputs/render-metadata.json` are nonempty. Confirm that all four
editable SVGs are placed in the company-brief HTML at their 165 mm publication
size so the independent visual reviewer sees them in the target report layout.
The diagram builder owns the SVG artifacts. Do not hand-edit generated HTML or PDF. If layout needs
correction, change the Markdown or design source, rebuild all affected
artifacts, and record the change in design notes.
