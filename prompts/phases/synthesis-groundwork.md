TASK TYPE: SYNTHESIS GROUNDWORK, NOT WRITING THE SYNTHESIS FILES

Read the evidence, writing, and runtime cores and the numbered research
questions in `00-scope.md`. The fact store under `02-facts/` is the only
evidence. Prepare the shared material every synthesis writer reads, so each
writer works from compact digests instead of the whole store:

- `tools/digests/`: one compact digest per topic table, with each fact's ID,
  grade, source date, speaker, claim, and conflict group. Generate them with a
  script; they restate the store and add nothing.
- `03-timelines/`: dated timelines of company events, positioning, people and
  roles, and the conflicting metrics, keeping event dates apart from record
  dates and undated facts visibly undated.
- `tools/outputs/currency.csv`: one row per current-state item (positioning,
  offers, people, figures) with its first and last evidence dates and fact
  IDs, and a flag where the currency rules in the evidence core require
  `as of`, `last confirmed`, or `possibly retired` wording.

Do not write `05-synthesis/` files or review your own currency flags; separate
workers do both. Every row cites fact IDs that exist in the store.
