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

Treat public sources as intentionally public: a public repository, page, or
file may be used for what it says about a firm. Record organizations,
repositories, and roles, never personal details.

Public archives keep what GitHub and the web no longer serve. Use them for the
company and for direct competitors alike:

- GH Archive, the public record of GitHub events (who pushed, opened pull
  requests or issues, starred, or forked which repository, and when; pull
  request and issue titles and bodies; branch and release names). Two routes:
  the ClickHouse public playground, one cheap SQL request each
  (`https://play.clickhouse.com/?user=play&query=` followed by a URL-encoded
  query ending in `FORMAT TSV`, or the same query posted with `curl
  --data-binary`), and, when the playground is unavailable, the raw hourly
  files at `https://data.gharchive.org/YYYY-MM-DD-H.json.gz`, scanned with a
  script for only the hours and repositories you need. The archive's date
  range is limited; state it.
- Software Heritage, the public archive of source code, which often keeps a
  repository after GitHub deleted it. Check for a copy with one request to
  `https://archive.softwareheritage.org/api/1/origin/https://github.com/OWNER/REPO/visit/latest/`;
  when one exists, admit
  `https://archive.softwareheritage.org/browse/origin/directory/?origin_url=https://github.com/OWNER/REPO`
  and the runtime reads its file list and its Markdown and CSV files at the
  last archived commit, within the archive's request limit.
- The Wayback Machine, for pages, when the network allows it.

Finding GitHub organizations, for the company and for competitors: never
guess one exact name. A firm's organization is often named differently from
its brand (`distyl-ai`, `DistylAI`, `getdistyl`, an abbreviation, a product
name, an acquired company's name), and many firms have several (product,
open source, client work, workshops, an acquired company). Search, cheapest
first, and collect every one:

- one GH Archive query for name variants in organization and account names:
  `SELECT splitByChar('/', repo_name)[1] AS org, count(), max(created_at) FROM
  github_events WHERE repo_name ILIKE '%VARIANT%' GROUP BY org ORDER BY count()
  DESC LIMIT 50` (with each variant: with and without "ai", hyphens, spaces,
  abbreviations, product names);
- web search (`FIRM github`, `site:github.com FIRM`) and GitHub's own search
  in the headless browser (`https://github.com/search?q=FIRM&type=users`,
  which lists organizations);
- links on the firm's site, documentation, careers pages, and engineering
  blog, and package registries (npm, PyPI, Docker Hub) that name the
  publisher;
- the organization listed on its people's GitHub profiles.

Confirm an organization belongs to the firm from its profile (name, website,
email domain) or its repositories, not from the name alone.

The headless browser is one command: `python3 -m research_control web render
--url URL` prints a page's title and its text as desktop Chrome renders it
(`--max-chars` to read less, `--links TEXT` to list only links containing that
text). Use it for pages that refuse plain requests, such as github.com
organization, people, repository, and profile pages.

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
- Market and competitors (`market_competitors`): build the competitor set from
  evidence, not from the best-known names. Look in three places:
  1. Firms the company names or compares itself to: its own pages, its
     leaders' interviews, its job postings, and captured sales material.
  2. Firms listed beside the company where buyers look: the partner
     directories and competency lists it appears in (cloud providers, AI labs,
     software vendors), marketplace categories, agency and review directories,
     "alternatives to" and comparison pages, award and analyst lists, its
     investors' portfolios, and trade press that names firms together.
  3. Firms selling the same offering to the same buyers in the same way: the
     same engagement model, size, and specialization.
  A direct competitor sells the same kind of offering to the same buyers in a
  similar way; an adjacent firm (a global consulting firm, a platform vendor,
  an AI lab moving into services) competes for some of the same budget. Find
  the direct competitors first, and record which each firm is and why. For
  each direct competitor, admit the pages that establish its positioning and
  offering, engagement model and packaging, pricing or rate signals, partner
  tiers, named customers or case studies, size and funding (headcount, rounds,
  acquisitions), and recent launches with dates. For the market, admit what
  sizes or describes the category: analyst and trade reports, filings and
  earnings commentary on the category, funding and acquisition activity, and
  moves by platform vendors and AI labs into the company's line of work.
  Public GitHub, for direct competitors only, as cheaply as possible. Treat
  public repositories as intentionally public. The aim is what a firm and its
  people keep in Markdown and CSV files (clients, teams, accounts, offerings,
  plans); other code is not read. Run GH Archive queries on the ClickHouse
  playground (see public archives above) with `curl`; each is one cheap
  request.
  1. Find the firm's GitHub presence by searching, never by guessing one exact
     name (see finding GitHub organizations below). Some firms have an
     organization, some work only from employees' public accounts, and many
     have several organizations as well as employees' accounts.
  2. Find who is affiliated, cheapest first. One archive query lists everyone
     who acted on the firm's repositories and how: `SELECT actor_login,
     groupUniqArray(event_type), count() FROM github_events WHERE repo_name
     LIKE 'ORG/%' GROUP BY actor_login ORDER BY count() DESC LIMIT 300`.
     Pushes, pull requests, and reviews are commits; a star (`WatchEvent`) is
     only a lead. Add the organization's public members
     (`https://github.com/orgs/ORG/people` in the headless browser) and
     handles named on the firm's own pages. Open a profile in the browser only
     when the archive leaves a handle unclear. A profile that names the firm,
     organization membership, or repeated commits to its repositories make a
     handle affiliated; a star or a single commit alone does not. Then go one
     hop out the same way: who commits to or stars the affiliated people's own
     work repositories, to find colleagues and firm work kept in personal
     accounts. Stop when a hop adds no new affiliated handle.
  3. Find the repositories, cheapest first. One archive query of the
     affiliated handles (`SELECT repo_name, groupUniqArray(event_type),
     min(created_at), max(created_at), count() FROM github_events WHERE
     actor_login IN ('HANDLE', ...) GROUP BY repo_name ORDER BY count() DESC`)
     shows the repositories they own or work in. Check names and descriptions
     in the browser's repository lists (`https://github.com/orgs/ORG/repositories`,
     `https://github.com/HANDLE?tab=repositories`). Admit a repository by its
     URL when it is the firm's work: its offering (a product, a public tool,
     an accelerator), a business record (an org chart, an account list, a
     plan), or client work. Never admit a personal project.
  4. Deleted and abandoned repositories. The archive also lists repositories
     under the organization or the affiliated handles that no longer exist,
     and live ones that went quiet. Decide which are worth a deeper look from
     what the archive kept, in one query per firm (names, first and last
     activity, pull request and issue titles, branch names, release names).
     Look deeper only where they point at a project for a named customer or
     sector, a product or service the firm tried and abandoned, or records of
     its business or operations (accounts, staffing, plans, pricing). For a
     deleted repository worth it:
     - admit its Software Heritage copy when one exists (see public archives
       above);
     - admit one archive query URL that returns what GH Archive recorded
       about it (pull request and issue titles and bodies, branch and release
       names), as the record of what the project was and when.
     A live repository that went quiet is read like any live one; say in the
     evidence when its activity stopped, so the report can show it was
     abandoned. Never admit archive results or an archived copy for a
     repository that is still live, and state the archive's date range.
  The runtime reads each admitted repository at its latest commit: the
  repository page's description and topics, the file list, and its Markdown
  and CSV files (README first, within a size limit). When the file list shows
  another single file that matters (a package description that names what a
  product is built on), admit that file by its URL
  (`https://github.com/ORG/REPO/blob/main/PATH`). Admit an archive query as a
  source only when a fact will rest on it (affiliation evidence, or a deleted
  repository). Do not clone, read history or other branches, read whole
  directories of code, or look at adjacent firms' code; that depth is for the
  company itself (`code_packages`). Record organizations, repositories, and
  roles, never personal details.
  Close as `sufficient` against the market and competitor questions, naming
  each competitor found, whether it is direct or adjacent, and the evidence.
- Social platforms that require login (LinkedIn, X, Facebook, Instagram,
  Threads, TikTok) are recorded automatically as uncaptured leads, except
  videos admitted on the `video` channel, which the runtime tries to transcribe. Admit the
  official profiles and any post that a question depends on, and look for a
  public copy (a press release, blog post, or transcript) of that content.
- Public code (`code_packages`): catalog every public repository in the
  company's GitHub organizations. List an organization's repositories and
  people through the headless browser (`https://github.com/orgs/ORG/repositories`
  and `/people`), which github.com serves when it refuses plain requests, and
  look for further organization names in the repositories' own files
  (remotes, package metadata, catalog files). Then find the company's people
  on GitHub and their public work, without being told where to look:
  - Staff handles: committers of the company's repositories (step 1 below),
    the organization's public members, handles that carry the company's name
    (GH Archive `actor_login ILIKE '%COMPANY%'`), and handles named in the
    company's own pages, documents, and repositories. People who star the
    company's repositories (`WatchEvent` in GH Archive) are leads: a profile
    that names the company or commits to its work confirm them.
  - Each staff handle's own public repositories (the browser's
    `https://github.com/HANDLE?tab=repositories`) and the repositories it
    pushed to or opened pull requests in (GH Archive, step 2). Triage them in
    bulk with a script: a shallow clone's README, file tree, and commit
    subjects. Admit a repository that is the company's work: a business record
    (an org chart, an account book, call or meeting notes, a plan), a tool or
    skill the company uses or sells, or work shaped to a client. Personal
    projects with no company tie are not admitted.
  - Anything a shallow look left unclear (an empty README, a generic name) is
    cloned with full history and all branches before it is ruled out.
  Then look for the company's work in other organizations' repositories:
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
  4. The company's deleted repositories: the `repo_name LIKE 'ORG/%'` query
     and the staff handles' activity show repositories GitHub no longer
     serves. From what the archive kept (names, activity dates, pull request
     and issue titles, branch and release names), decide which show company
     information or the history of what it tried: a past product or service,
     a client project, an attempt it abandoned, business or operations
     records. For each one worth it, admit its Software Heritage copy when
     one exists and one archive query URL that returns what GH Archive
     recorded about it. This is for company information and history, so the
     runtime reads the archived copy's file list and its Markdown and CSV
     files, not its code.

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

Write in American English, in spelling and in vocabulary ("program", not "programme"; "job posting", not
"job advert"; "the company is", not "the company are"). Quotes, quoted titles, and names keep the
source's spelling. `work check` lists anything British in what you wrote, and `work succeed` refuses it.
