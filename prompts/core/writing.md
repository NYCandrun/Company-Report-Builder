# Writing core

Apply these rules to authored prose. Verbatim quotes preserve their source.

- Use plain American English, in spelling and vocabulary (see the runtime core), and
  double quotation marks as the main quote style.
- Use no internal shorthand or jargon: say what a thing is. Name a repository by
  its GitHub name (owner/repository) and a source by what it is.
- Use no em dashes.
- Use no semicolon to join independent sentences.
- Never use the word `suggested`.
- State facts directly and explicitly.
- Say what the facts mean, not only what they are. A page that lists facts
  in a row, however well cited, has not done its job: every part and every
  paragraph opens with what the reader should conclude, and the facts that
  show it follow. Inference stays marked.
- Keep copy tight. Length follows the evidence: as long as it needs, no longer.
- Qualify once. A caveat (a date's age, a probable speaker, proof the company
  wrote itself, a plan rather than a result) is said where it matters, once
  per part or exhibit, not attached to every sentence that touches it.
- In an exhibit cell, state the thing itself in a few words with its
  citations: the price, the stage and its date, the count, the name. Do not
  describe or allude to the evidence in the cell; the superscript's source
  note carries the quoted passage, place, and date.
- Write no filler: do not restate a heading, announce what a section will do,
  repeat what an earlier paragraph or part said, or add general commentary the
  evidence does not support.
- Stay on the questions: leave out tangents, however interesting.
- Do not drop the context that gives a fact its meaning: its date, what it
  changed from, who said it, and how strong the evidence is.
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
