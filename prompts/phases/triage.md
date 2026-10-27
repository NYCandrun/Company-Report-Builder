# TASK TYPE: EXTRACTION TRIAGE

Decide which captured sources are read in full for fact extraction. Capture is
deterministic and cheap, so the corpus can hold far more pages than the company
brief can use. Extraction, verification, and review are expensive. Triage keeps
that downstream work proportional to the brief's questions, not to the size of
the website.

Read `00-scope.md`, especially its numbered research questions (`Q1`, `Q2`,
...), then read every row of `tools/lists/triage-index.jsonl`. Each row gives a
captured source's ID, URL, title, channel, grade, date, size, and an opening
excerpt. Open a captured `content.txt` when the index row is not enough to
decide.

Write exactly one JSON line per captured source to
`tools/lists/extraction-triage.jsonl`:

```json
{"id": "SRC-...", "decision": "include", "questions": ["Q1", "Q3"], "reason": "Product page naming the three service lines and engagement model."}
```

Rules:

- `decision` is `include` or `exclude`. An included source names every
  question ID it can answer. An excluded source may name none.
- Include every source that is the best or only evidence for a question, every
  dated source that establishes change over time (launches, pricing,
  positioning, leadership), and every customer, partner, or third-party source
  with first-hand evidence.
- Exclude near-duplicates of an included page, navigation or legal boilerplate,
  thin tag or index pages whose items are captured individually, and pages
  whose only content repeats evidence already included. Say which included
  source covers it when that is the reason.
- Prefer breadth across questions over depth within one. A question with no
  included source must be stated in your return message as an evidence gap.
- Do not exclude a source because its claims are unflattering, contradictory,
  or inconvenient. Contradictions are evidence.
- Do not invent sources, IDs, or question IDs. Excluded sources keep their
  capture and provenance; exclusion only means they are not read for facts.

Return the included count, excluded count, per-question included counts, and
any question without an included source.

When the packet's input is `tools/lists/triage-pending.jsonl`, the corpus was
already triaged and these sources were captured afterwards. Decide only the
listed sources: append one line for each to
`tools/lists/extraction-triage.jsonl` and leave every existing line unchanged.
