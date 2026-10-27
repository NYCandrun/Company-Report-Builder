# Writing core

Apply these rules to authored prose. Verbatim quotes preserve their source.

- Use plain American English and double quotation marks as the main quote style.
- Use no internal shorthand or jargon: say what a thing is. Name a repository by
  its GitHub name (owner/repository) and a source by what it is.
- Use no em dashes.
- Use no semicolon to join independent sentences.
- Never use the word `suggested`.
- State facts directly and explicitly.
- Do not narrate how wording changed from an earlier draft.
- Preserve proper nouns, source titles, URLs, file names, fact IDs, and quotes.

The final deliverable is a **company brief** about the whole company,
arranged top down from an executive summary and broad context to specifics,
answering every research question in the part it belongs to
(`tools/lists/report-outline.json`). Its cover says **Focus:** followed by the
scope's focus, or "The whole company" when the scope names none. It must not presume employment and must not use `onboarding`,
`starting at`, `the new PMM`, or `the role` in reader-facing copy.

Markdown retains fact IDs for traceability. Final HTML and PDF do not expose
fact IDs, repository paths, script names, build instructions, internal
warnings, or remove-before-sharing notes.

Run the writing validator assigned by the phase. A clean mechanical check does
not replace editorial or American-English review.
