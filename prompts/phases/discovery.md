# TASK TYPE: SOURCE DISCOVERY

Discover the public evidence the company brief needs from the assigned channel
(see the `channels` input). Claim and start this task before running any
discovery command: `discovery add`, `close`, `exclude`, and `receipt` refuse to
change a channel whose task is not claimed. There is no source, page, query, or result-count
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
  Threads, TikTok) are recorded automatically as uncaptured leads, except
  videos admitted on the `video` channel, which the runtime tries to transcribe. Admit the
  official profiles and any post that a question depends on, and look for a
  public copy (a press release, blog post, or transcript) of that content.
- Public code (`code_packages`): catalog every public repository in the
  company's GitHub organizations. When an organization page cannot be listed
  from the environment, ask the person running the research for the list
  rather than guessing names, and look for further organization names in the
  repositories' own files (remotes, package metadata, catalog files). Then
  look for the company's work in other organizations' repositories:
  1. Clone each company repository with full history and all branches, and
     list its committers from `git log --all`. A GitHub noreply address gives
     the handle.
  2. Query GH Archive, the public record of GitHub events, for those handles,
     using the ClickHouse public playground over plain HTTP:
     `curl -sS 'https://play.clickhouse.com/?user=play' --data-binary "SELECT
     repo_name, event_type, count() c, min(created_at), max(created_at) FROM
     github_events WHERE actor_login IN ('HANDLE') GROUP BY repo_name,
     event_type ORDER BY c DESC FORMAT TSV"`. Pushes, pull requests, and
     reviews are strong signals; stars and forks are not. Also query
     `repo_name LIKE 'ORG/%'` for the company's organizations; that finds
     repositories since deleted or made private, and more of its people. The
     archive's date range is limited, so state it.
  3. Admit an outside repository only after cloning it and finding the
     commits by `git log --all --author`.

  This is professional evidence about clients, partners, and project scope,
  not about people. Record organizations and repositories, never personal
  details. A client relationship is stated when a source states it. It may
  also be inferred when the evidence is sufficient, for example:
  - several of the company's people committing to one outside organization's
    repositories;
  - sustained work over weeks;
  - work shaped to that organization (its brand, data, systems, or names in
    branches and files).

  Record such a relationship as an inference, naming the evidence and its
  strength, with the `Stated`, `Inferred`, or `Lead` mark the evidence core
  requires. A single commit, a repository name, a fork, a demo, or one
  person's activity alone is a lead: admit its source and mark the
  relationship as a lead with thin evidence, not as an inferred client. Do not
  use GitHub search or API tools
  beyond the repositories the environment permits; use the routes above.
- Video and podcasts, at every length (Shorts, clips, and social video drops
  included): enumerate every video on the company's own channels (YouTube,
  LinkedIn, X, Instagram, TikTok, Vimeo, and video embedded on the company
  site), and find every video or podcast in which the company's founders,
  executives, or named leaders appear: interviews, panels, keynotes, webinars,
  news segments, and short media drops. Search by each leader's name as well
  as the company's. The runtime transcribes each one during capture, from
  captions or from the audio with Whisper. When a platform yields page text
  only, also admit a transcribable copy of the appearance when one exists:
  the publisher's episode page, the direct audio enclosure from its RSS feed,
  or a publisher-hosted player page.

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

Finally run `python3 -m research_control discovery receipt --channel CHANNEL`.
The task is complete only when the receipt exists and agrees with the
scheduler's terminal channel state.
