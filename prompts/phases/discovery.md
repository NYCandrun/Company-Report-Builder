# TASK TYPE: SOURCE DISCOVERY

Discover the public evidence the company brief needs from the assigned channels
(see the `channels` input). There is no source, page, query, or result-count
target in either direction. Discovery serves the numbered research questions
(`Q1`, `Q2`, ...) in `00-scope.md`; read them before searching.

The runtime has already crawled the company host and its sitemaps to a fixed
point. Check what is cataloged before searching:

```bash
python3 -m research_control web list --purpose research_discovery
```

Search for what that crawl cannot reach: other first-party hosts and
subdomains, applicant tracking systems, documentation portals, public code,
recorded talks and podcasts, customer and partner announcements, independent
reporting, and competitors' public positioning. Treat cached URLs and brand
leads only as leads; apply this packet's relevance rules before admitting one.

Record each pass with:

```bash
python3 -m research_control discovery add \
  --channel CHANNEL --url URL --url URL \
  --evidence "query, surface, result pages, and inclusion reasoning"
```

An empty pass is recorded by omitting `--url`. Vary query families, product
names, executive names, date ranges, and platform-native surfaces. A source
already in the catalog is not new. Do not admit mirrors, tracking URLs,
irrelevant mentions, or search-result pages. When a pass finds a new
first-party surface, admitting it is enough; the runtime captures it.

Admit what answers a question, not everything that exists:

- Competitors: admit the pages that establish a competitor's positioning,
  packaging, pricing, or the specific capability being compared. Do not admit a
  competitor's documentation or blog wholesale.
- Social platforms that require login (LinkedIn, X, Facebook, Instagram,
  Threads, TikTok) are recorded automatically as uncaptured leads. Admit the
  official profiles and any post that a question depends on, and look for a
  public copy (a press release, blog post, or transcript) of that content.
- Video and podcasts: admit long-form company talks and interviews. The
  runtime transcribes media during capture, from published captions or from a
  public audio download transcribed locally with Whisper. When a platform yields page text only, also admit a
  transcribable copy of the appearance when one exists: the publisher's episode page, the
  episode's direct audio enclosure from its RSS feed, or a publisher-hosted
  player page.

Close each assigned channel with one terminal state and specific evidence:

- `sufficient`: the admitted sources answer the channel's share of the named
  questions, and further search would add repetition rather than a new answer.
  The evidence must name the question IDs and the sources or searches behind
  each. Requires at least one recorded pass.
- `saturated`: two materially different passes in a row added nothing.
- `not_applicable`: the channel does not exist for this company, with the
  searches that establish that.
- `blocked`: access is prohibited or failing, with the concrete failure.

```bash
python3 -m research_control discovery close \
  --channel CHANNEL --state sufficient --evidence "Q2: ...; Q5: ...; further search ..."
```

Safety limits are circuit breakers. If one is reached, record `incomplete`.
Never use a number of sources as completion evidence.

Finally run `python3 -m research_control discovery receipt --channel CHANNEL`
for every assigned channel. The task is complete only when each receipt exists
and agrees with the scheduler's terminal channel state.
