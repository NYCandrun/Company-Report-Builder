TASK TYPE: PUBLICATION FINDING DISPOSITION AND FIX APPLICATION

Read all independent language, citation-claim, exhibit, and visual reports.
Give every finding one disposition: `apply`, `apply_in_part`, or `reject`, with
a reason and evidence path. Record decisions in
`tools/outputs/publication-decisions.jsonl` and a readable summary in
`06-checks/publication-decisions.md`.

Apply accepted changes only to final Markdown, diagram model files, editable
SVGs, captions, or design sources. Citations are fact IDs in the Markdown: fix a
citation by changing the fact IDs beside the words, then run `work check`, which
rebuilds the citation and exhibit maps. Never edit those maps by hand. Never
hand-edit generated HTML or PDF. Run `python3 -m research_control render` only
when the company-brief source, its style, a placed diagram, or a brand artifact
changed. The renderer reuses the HTML, PDF, and page previews when their input
hashes are unchanged and writes a hash-scoped re-review plan. Do not render a
clean, unchanged review set merely to refresh timestamps. If a
diagram changes, revalidate its model, regenerate the SVG from that model, and
preserve its deterministic title/subtitle. The subsequent independent
re-review inspects changed hashes and retains only unchanged, hash-bound clean
records.

For accepted brand-guide findings, revise the authored brand-guide HTML,
regenerate its PDF from the same print mode, update its acceptance evidence,
and rerender the affected desktop, mobile, and PDF views. Brand changes may
alter presentation only; they may not alter the architecture model.

Do not perform the re-review yourself. The prior reviewers must rerun against
the new artifact hashes before page acceptance.
