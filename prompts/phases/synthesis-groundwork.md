TASK TYPE: SYNTHESIS GROUNDWORK, NOT WRITING THE SYNTHESIS FILES

Read the evidence, writing, and runtime cores and the numbered research
questions in `00-scope.md`. The fact store under `02-facts/` is the only
evidence. The runtime has already written `tools/digests/`: one compact digest
per fact table, one line per fact with its ID, source date, grade, source,
who said it, claim, and delivery status and relationship basis. Work from the
digests; open a fact's full row (quote, location, notes) only when you need it,
by searching `02-facts/` for its ID, and do not read the store whole. Prepare
the rest of the shared material every synthesis writer reads:

- `03-timelines/`: dated timelines of company events, positioning, people and
  roles, and the conflicting metrics, keeping event dates apart from record
  dates and undated facts visibly undated.
- `tools/outputs/currency.csv`: one row per current-state item (positioning,
  offers, people, figures) with its first and last evidence dates and fact
  IDs, and a flag where the currency rules in the evidence core require
  `as of`, `last confirmed`, or `possibly retired` wording.

Do not rewrite the digests, write `05-synthesis/` files, or review your own
currency flags; the runtime and separate workers do those. Every row cites fact IDs that exist in the store.
