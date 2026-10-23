TASK TYPE: PUBLICATION FINDING DISPOSITION AND FIX APPLICATION

Read all independent language, citation-claim, exhibit, and visual reports.
Give every finding one disposition: `apply`, `apply_in_part`, or `reject`, with
a reason and evidence path. Record decisions in
`tools/outputs/publication-decisions.jsonl` and a readable summary in
`06-checks/publication-decisions.md`.

Apply accepted changes only to final Markdown, citation maps, exhibit maps,
diagram model files, editable SVGs, captions, or design sources. Never
hand-edit generated HTML or PDF. Rebuild the company-brief HTML/PDF with
`python3 -m research_control render`, even when the review set is clean. If a
diagram changes, revalidate its model, regenerate the SVG from that model, and
preserve its deterministic title/subtitle. The subsequent independent
re-review must bind to all accepted source and artifact hashes.

For accepted brand-guide findings, revise the authored brand-guide HTML,
regenerate its PDF from the same print mode, update its acceptance evidence,
and rerender the affected desktop, mobile, and PDF views. Brand changes may
alter presentation only; they may not alter the architecture model.

Do not perform the re-review yourself. The prior reviewers must rerun against
the new artifact hashes before page acceptance.
