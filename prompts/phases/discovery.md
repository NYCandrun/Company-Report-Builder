# TASK TYPE: SOURCE DISCOVERY

Discover relevant public evidence for the assigned channel. There is no source,
page, query, or result-count target. Continue until the channel reaches a
documented fixed point: repeated materially different discovery passes produce
no new relevant sources.

Use the shared URL ledger and response cache opportunistically. At the start of
a pass, `python3 -m research_control web list --purpose brand_discovery` may
surface first-party leads already found by the concurrent brand worker. Treat
them only as leads: independently apply this packet's relevance and channel
rules before adding them through `discovery add`. The discovery commands
automatically register admitted URLs, and the first-party crawler automatically
reuses cached public bytes. Do not wait for brand work to finish.

For `company_site`, run `python3 -m research_control discovery crawl`; it drains
the first-party link frontier and repeats empty passes until saturated. For
other channels, use the runtime's search, browser, repository, and media tools.
Record each pass with:

```bash
python3 -m research_control discovery add \
  --channel CHANNEL --url URL --url URL \
  --evidence "query, surface, result pages, and inclusion reasoning"
```

An empty pass is recorded by omitting `--url`. Vary query families, company and
product names, executive names, date ranges, and platform-native surfaces. A
source already in the catalog is not new. Do not count mirrors, tracking URLs,
irrelevant mentions, or search-result pages as sources.

When a pass finds a new first-party sitemap, documentation, blog, newsroom, or
careers surface, run `python3 -m research_control discovery crawl` to drain the
new first-party frontier. This can reopen a previously saturated company-site
channel; the scheduler will invalidate and reissue that channel's stale receipt
rather than losing the newly reachable branch.

If a channel genuinely does not apply, or access is blocked, close it with
specific evidence:

```bash
python3 -m research_control discovery close \
  --channel CHANNEL --state not_applicable --evidence "EVIDENCE"
```

Safety limits are circuit breakers. If one is reached, record `incomplete`, not
`saturated`. Never use a requested number of sources as completion evidence.

Finally run `python3 -m research_control discovery receipt --channel CHANNEL`.
The task is complete only when its private receipt exists and agrees with the
scheduler's terminal channel state.
