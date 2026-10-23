TASK TYPE: PUBLICATION FINDING DISPOSITION AND FIX APPLICATION

Read all independent language, citation-claim, exhibit, and visual reports.
Give every finding one disposition: `apply`, `apply_in_part`, or `reject`, with
a reason and evidence path. Record decisions in
`tools/outputs/publication-decisions.jsonl` and a readable summary in
`06-checks/publication-decisions.md`.

Apply accepted changes only to final Markdown, citation maps, exhibit maps, or
design sources. Never hand-edit generated HTML or PDF. Rebuild all four final
artifacts with `python3 -m research_control render`, even when the review set is
clean, so the subsequent independent re-review binds to the accepted sources.

Do not perform the re-review yourself. The prior reviewers must rerun against
the new artifact hashes before page acceptance.
