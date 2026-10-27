# TASK TYPE: ALTERNATE COPIES OF BLOCKED SOURCES

Every source in this task's `blocked_sources` input list was admitted as evidence,
but the runtime could not capture it: the site refused automated requests
(HTTP 403), the page is gone (HTTP 404), or another access failure, each with
its recorded reason. Your job is to find a publicly reachable copy of the
same content, so the evidence is not lost, and to record the outcome for every
listed source.

Good alternate copies:

- the same press release on a wire service (PR Newswire, GlobeNewswire,
  Business Wire), the issuer's own newsroom, or a trade outlet that reprints it
  in full;
- the publisher's syndicated copy of an article (for example Yahoo Finance or
  MSN) when it is public;
- the same video on YouTube, Vimeo, or the publisher's own player page;
- the same podcast episode on Apple Podcasts, Spotify, the show's site, or the
  direct audio enclosure from its RSS feed;
- the other party's own announcement of the same event, when it states the
  same facts;
- an archived copy, if an archive is reachable from this environment.

Not alternates: pages that only summarize, quote from, or comment on the
original; search-result pages; cache mirrors; paywall-removal services.

Verify each candidate is publicly reachable before recording it (for example
`python3 -m research_control web fetch --url URL --consumer TASK_ID --purpose research_discovery`,
which reports the HTTP status). Check the source catalog
(`tools/outputs/discovery/sources.jsonl`, read only) first: an equivalent copy
may already be cataloged, and you can record it by its URL.

Record one outcome per blocked source, under your claim:

```bash
python3 -m research_control discovery alternate --source-id SRC-... \
  --url ALTERNATE_URL --evidence "how it was found and why it is the same content"
python3 -m research_control discovery alternate --source-id SRC-... \
  --none --evidence "what was searched and why nothing qualifies"
```

A recorded alternate joins the original's channel without reopening it, and
the runtime captures it automatically. The task is complete only when every
source in its list has at least one recorded outcome. Return the number of sources
with an alternate, the number with none, and any that need a different access
method.
