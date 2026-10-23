# Company research prompt

The company URL is in my chat message. Apply this prompt to that company and the website the URL points to.

This prompt is designed to run in **Claude Code** from a new, existing, or partially initialized repository. Do not assume that any research directories, helper scripts, templates, manifests, agent briefs, check files, or build tools already exist unless they are present when the run begins.

Use Claude Code workflows, subagents and parallel execution wherever the dependencies below allow it. Do not stop to ask me about choices this prompt already makes. Ask only when something is genuinely ambiguous for this company, and then ask once, with a recommendation, while continuing everything that does not depend on the answer.

The repository must be reproducible from:
1. this prompt;
2. the company URL;
3. anything I provide in `00-inputs/` or chat;
4. public sources captured during the run.

No step may depend on a script, template, file, convention or prior research artifact that is neither supplied by me nor created during this run.

---

## -1. Runtime and repository bootstrap

Run this project in Claude Code from the current working directory.

### Repository rules

Before Phase 0:

1. Inspect the current directory.
2. Preserve every existing user file unless this prompt explicitly says to modify it.
3. Never delete, reset, overwrite or reinitialize unrelated repository contents.
4. If the directory is not a Git repository, initialize Git.
5. If it is already a Git repository, use it as-is. Never run a destructive reset.
6. Create the repository structure in section 7 where it does not already exist.
7. Create `WORKFLOW_STATE.md` immediately.
8. Create `prompt/PROMPT.md` containing the exact prompt supplied for this run.
9. Create `prompt/revised_prompt.md` containing the effective prompt being followed.
10. Make `README.md` an identical copy of `prompt/revised_prompt.md`.
11. Create `prompt/CHANGES.md`. If this prompt changes during the run, record each change there with the date, what changed and why.
12. Record in `WORKFLOW_STATE.md`:
    - company URL;
    - company name once resolved;
    - research start date;
    - current phase;
    - repository state found at startup;
    - files and tools created during bootstrap;
    - open issues;
    - active workflow or agent IDs where available.

### Shared-state ownership

The **main Claude Code session is the orchestrator and owns shared project state**.

Unless a worker is explicitly assigned a shared-state task, subagents and workflow workers do not:

- edit `WORKFLOW_STATE.md`;
- edit `RUN_HISTORY.md`;
- merge shared manifests;
- rebuild the global `BLOCKED.md`;
- assign source-ID ranges;
- assign fact-ID ranges;
- modify shared placement or citation maps;
- change repository-wide configuration;
- make cross-workflow scope decisions;
- overwrite another worker's output;
- commit changes that include unrelated workers' files.

The orchestrator:

1. creates work lists;
2. assigns non-overlapping input slices;
3. assigns non-overlapping source-ID or fact-ID ranges where needed;
4. assigns exact output paths;
5. records workflow and worker IDs;
6. merges shared outputs with deterministic scripts;
7. updates shared state after workers finish;
8. resolves cross-workflow conflicts;
9. controls phase transitions and gates;
10. performs or delegates final integration.

Every worker writes only to its assigned output files, manifest part, blocked part and scratch directory unless its task explicitly says otherwise.

### Tool bootstrap

The script names and command-line interfaces in this prompt are **canonical**. They are not assumptions that the files already exist.

Whenever this prompt names a script under `tools/`:

1. If the script exists, inspect it before use and confirm it implements the requirements in this prompt.
2. If it does not exist, create it before the first step that needs it.
3. Give deterministic scripts a small fixture or test case before running them over the research corpus.
4. Reuse the same script throughout the run rather than replacing it with ad hoc one-off commands.
5. Record material script creation or correction in `WORKFLOW_STATE.md`.
6. Store reusable dependencies in repo-local configuration where practical.

Before capture begins, check for the tools needed by later phases:

- Python 3;
- Git;
- Node.js and npm where needed;
- Chromium, Chrome or another headless Chromium-compatible browser;
- `yt-dlp`;
- `ffmpeg`;
- PDF text and rendering utilities such as Poppler where needed;
- a workable transcription path for media without captions;
- the Python packages needed by the scripts created for this run.

If a required command is missing:

1. install it locally or in a project-local environment where practical and permitted;
2. do not silently alter unrelated global configuration;
3. if installation is not possible, use the closest reliable substitute;
4. record the substitution and its consequences in `WORKFLOW_STATE.md` and, if it affects evidence coverage, `01-sources/BLOCKED.md`.

Create a repo-local Python virtual environment if Python dependencies are needed and no appropriate environment already exists. Save reproducible dependency information such as `requirements.txt`, `pyproject.toml`, or equivalent.

### Model use

Do not hard-code historical model product names.

Use:
- the strongest reasoning model available in Claude Code, at high effort where configurable, for extraction, judgment, verification, synthesis, adversarial review and substantive fixes;
- a faster capable model for mechanical editing, routine script execution and bounded transformations where independent judgment is limited.

Where this prompt calls for independent reviewers, use separate agent contexts even if the same underlying model must be used.

Record the model and effort used for each workflow or agent in `RUN_HISTORY.md` where Claude Code exposes that information.

### Design bootstrap

Do not assume the AirOps design system, stylesheet or previous HTML build exists.

If `00-inputs/` contains a design guide, reference artifact, stylesheet, PDF, HTML example, font instructions or template, use it under section 15.

If no design guide exists:

1. derive a restrained visual system from the company's public identity;
2. inspect its website for:
   - primary and secondary colors;
   - typography;
   - heading treatment;
   - spacing;
   - borders;
   - table treatment;
   - card treatment;
   - logo usage;
3. use only fonts that are legally available in the environment;
4. do not scrape, redistribute or embed proprietary font files merely because the website serves them;
5. document every design decision in `05-synthesis/design-notes.md`.

The final document should feel specific to the company without imitating unrelated proprietary reports.

Commit the completed bootstrap before Phase 0.

---

## 0. American English, everywhere

Write everything in American English: spelling, vocabulary and usage.

- **Copy:** organization, program, analyze, color, center, license, catalog, enroll, labeled, modeled, traveled, toward, among, while, learned, math, rÃ©sumÃ©, job posting, cell phone, on the weekend, two weeks, quarter-over-quarter.
- Use double quotation marks as the main quote style.
- **Repository structure:** folder names, file names, script names, table column names, fact topics and IDs use American spelling. For example:
  - `02-facts/people-organization.md`
  - `05-synthesis/organization.md`
  - `tools/normalize_candidate_tags.py`
- **Exceptions:** verbatim quotes keep their original spelling. Names of companies, products, people, page titles and URLs stay as they are.
- **Check:** right before the design step, a separate high-reasoning review agent checks the brief, the one-page summary and the glossary for British spelling and usage, fixes them without changing quotes, fact IDs, file names or URLs, and lists every change in `06-checks/american-english.md`.

---

## 1. Goal

I am a product marketing manager getting deeply up to speed on a complex, fast-moving company: its products, how they fit together, its offering and packaging, its positioning and how that has changed, its direction and roadmap, its customers, and its competitors.

Build a research repository in the current repo.

It has three layers:

1. **Captured sources.** Every page, document, transcript and posting used, saved with dates.
2. **A facts store.** Every fact with a verbatim quote, an exact location, a source, a date, a grade, and tags for the company it is about and who said it.
3. **Sense-making.** Built only on facts in the store, ending in a branded company brief I can read in an hour.

### Title and framing

In effect this is an onboarding-quality brief for a product marketer, but it is titled **"company brief"** so it can be shared with the company before an offer without presuming the job.

Use:
- `company-brief.md`
- `07-final-report/company-brief.pdf`
- `07-final-report/company-brief.html`

The copy never says:
- "onboarding";
- "starting at";
- "the new PMM";
- "the role".

The cover says:

**Focus: Product marketing**

The front matter says the brief is written from a product marketing point of view.

File names, running headers and the one-page eyebrow use "company brief" too.

---

## 2. Inputs

### 2.1 Company URL

The company URL is in my chat message.

Resolve:
- canonical company name;
- canonical main website;
- relevant subdomains;
- docs domains;
- help center;
- academy or university;
- developer surfaces;
- newsroom or blog;
- careers or ATS;
- status page;
- public code and package surfaces.

Record them in `00-scope.md`.

### 2.2 `00-inputs/`

Read every file in `00-inputs/` before Phase 0 if the folder exists.

Sort each file into one or more of these roles:

#### My direction

Examples:
- notes;
- questions;
- job description;
- assignment instructions;
- interview context.

Use them to set:
- products in focus;
- likely role context;
- questions the brief must answer.

#### Sources

Examples:
- documents;
- decks;
- transcripts;
- exported pages;
- lists of links.

Copy each into `01-sources/` with a manifest row whose method is `"provided"`.

Leave the original in `00-inputs/` unchanged.

#### Provided research reports

A compilation someone else wrote is a **scoping checklist**, not the receipt for a fact.

Grade it by who wrote it, usually T.

Every:
- product;
- launch;
- date;
- person;
- customer;
- competitor;
- price;

mentioned in it becomes a lead to confirm from a P or S source.

Every:
- conflict;
- caveat;
- "not verified" item;

becomes a priority check in `00-scope.md`, with the channel that should settle it.

Every link it cites goes into:

`tools/input-links.txt`

Never use a provided research report as the final receipt for a fact when the underlying source can be captured.

#### Design guide

Examples:
- brand guide;
- style guide;
- sample HTML;
- sample PDF;
- colors;
- type scale;
- template.

Phase 6 follows it where legally and technically possible.

Leave `00-inputs/` unchanged.

A file can be more than one kind.

Material internal to the company is graded I and is never quoted in anything shared outside the company.

### 2.3 Facts I give in chat

Facts I give in chat during the run are recorded as:

1. a source file in `01-sources/provided/` containing my exact words;
2. a manifest row;
3. one or more facts with verdict:
   - `"confirmed (user-provided)"`.

Grade them I.

Do not independently check them unless I explicitly ask.

### Defaults

When inputs do not say otherwise:

- Company name, products and grouping: from the website.
- Products in focus: from my direction files.
- If there are no direction files, cover the products evenly and give the most depth to the flagship.
- Name the flagship in `00-scope.md` with reasons.
- Every synthesis agent and brief writer must be told what the flagship is.
- Competitors: 5 to 8.
- Find competitors from:
  - the company's comparison pages;
  - analyst coverage;
  - review sites;
  - competitors' pages that name the company.
- Give each competitor a reason.
- Add a short watch list.
- Lookback for messaging changes: 3 years.
- Today: the current session date.

---

## 3. Scope decisions made in advance

| Item | Decision |
|---|---|
| Company website | Every page in every discoverable company sitemap, including www, docs in all languages, help, academy or university, events and company microsites, is read by a script for PDF links and embedded media even if the page itself is not saved. High-value pages are saved in full. |
| PDFs | Every PDF the company hosts or publishes is downloaded with a text copy that marks page breaks. Third-party PDFs it only links to are listed, not downloaded unless needed as a direct research source. |
| Company videos | Every long-form video on the company's channels and every video embedded on any of its sites is in scope for transcription: webinars, product demos, course lessons, conference sessions and customer clips. YouTube Shorts are out. |
| Competitor videos | Out, except competitor videos the company embeds on its own pages. Competitor talks already captured stay. |
| Competitor docs | Each competitor's public docs, help center or knowledge base is captured. For suites, capture only the parts about the competing product. Cap around 400 pages per competitor and log what was left out. Videos inside competitor docs are out. |
| Secondary sources | No dedicated attempt to maximize S-grade volume. Capture relevant S sources encountered during normal research. The brief states how thin S sources are and how much customer proof is company-reported. |
| Web archives | Try the Wayback Machine once. If the host is blocked or repeatedly fails, cut the channel and reconstruct messaging history from dated primary sources. Do not waste time trying alternate clients through the same blocked network path. |
| Bot challenges | If a host serves a bot challenge, record it in `BLOCKED.md` and move on. Never bypass it. |
| Logins and paywalls | Out of scope. |
| Freshness re-check before the brief | Skipped when research occurs in one or two days. Facts from the last quarter count as current under section 6. |
| Already captured and verified material | Never drop it merely because scope narrows later. |

---

## 4. Evidence rules

Every agent follows these.

### 4.1 Grades

**P:** the company's own words:
- site;
- docs;
- API specifications;
- code;
- filings;
- press releases;
- job postings;
- talks;
- podcasts by its people.

**S:** a named third party with first-hand knowledge:
- customer's own announcement;
- partner's own announcement;
- procurement record;
- customer filing.

**T:**
- trade press;
- analysts;
- review sites;
- reprints;
- aggregators;
- competitors writing about the company.

**I:** material from me that is not public.

A customer story on the company's own site is P even when it quotes the customer.

### 4.2 Receipt for every fact

Every fact must have:

- verbatim quote;
- source ID;
- exact location in the original captured source;
- source date;
- grade;
- `about`;
- `said_by`.

The source ID must correspond to a manifest row.

Never use:
- a file path alone;
- `"count script"`;
- `"many pages"`;
- `"website"`.

as a source receipt.

Locations can be:
- line number;
- page number;
- transcript timestamp;
- JSON field;
- API specification field.

### 4.3 Quotes

Quote rather than paraphrase when wording matters.

A shortened quote must preserve the original meaning.

### 4.4 Speakers

Auto-captions and machine transcripts may lack reliable speaker labels.

Name a speaker in a fact only when the attribution is firm, for example:
- the person introduces themselves;
- another participant addresses them by name;
- the source has reliable labels.

Otherwise write:

`a speaker in the <title> webinar`

Mark:
- inferred labels: `(probable)`
- unresolved labels: `Speaker unclear`

Record known transcription errors involving:
- company names;
- product names;
- competitors;
- people.

If a fact depends on an uncertain transcription, mark it as inference or unresolved.

### 4.5 Inferences

Every inference starts:

`My inference:`

and names the facts it rests on.

### 4.6 Absence claims

Absences are scoped.

Say:

`I found no ... in [the sources searched].`

Never turn incomplete coverage into an absolute claim.

### 4.7 Citation precision

A citation supports the exact words it sits on.

Claims say no more than the receipt.

Examples:
- aims are not achievements;
- "can" is not "does";
- "some" is not "all";
- "up to" is not the typical result;
- beta is not generally available;
- a job posting is not a hire.

### 4.8 Counts

Counts come from deterministic scripts in `tools/`.

Save their output so anyone can rerun the count.

### 4.9 Dates

Keep two dates separate:

1. **date published**
2. **date last modified**

For a recorded event:
- published date is the live event date if known;
- upload date goes in notes.

Evidence preference for date published:

1. JSON-LD `datePublished`;
2. article metadata;
3. `<time>`;
4. YouTube upload date;
5. podcast `pubDate`;
6. PDF creation or printed date;
7. press-release dateline;
8. ATS posting date;
9. date printed next to title.

Do not treat:
- site-wide deploy timestamps;
- homepage metadata;
- pricing-page modification metadata;

as publication dates.

On platforms where the visible date is a modified date, record it accordingly.

A shallow Git clone gives a last-modified signal, not publication evidence.

### 4.10 Stay public

No:
- logins;
- paywall workarounds;
- fake accounts;
- bot-challenge bypasses.

Follow robots.txt.

Back off when rate-limited.

If access fails, record it rather than routing around the restriction.

---

## 5. Writing rules

Apply to every authored file.

1. Plain American English.
2. No em dashes.
3. No semicolons joining independent sentences.
4. Never use the word `"suggested"`.
5. State facts directly.
6. Do not describe how a sentence changed from an earlier draft.
7. Say things explicitly rather than alluding to them.

Verbatim quotes keep original wording and punctuation.

Create:

`tools/check_writing_rules.py`

It must:
- check rules 2 and 4 automatically;
- take an `--out` path so parallel runs do not overwrite each other.

Use model review for rules that cannot be checked mechanically.

---

## 6. What is true now

The company may change quickly.

### Current facts

Facts whose latest evidence is from the last quarter before the research date are stated plainly as current.

Older current-state claims carry:

`as of <date>`

Flagged items use:

`last confirmed <date>`

or:

`possibly retired`

Never state them plainly as current.

### Currency timeline

Create a script that records, for every:

- person's title;
- plan;
- price;
- limit;
- product;
- module name;
- integration;
- positioning line;

these fields:

- first seen;
- last seen;
- superseded by;
- current value;
- latest evidence date.

Flag:

- people whose latest role evidence is more than 6 months old;
- people missing from current people pages;
- prices, plans, limits and features whose latest evidence is more than about 3 months old;
- things present in older sources but absent from current pages, docs and changelog;
- things described as:
  - deprecated;
  - sunset;
  - removed;
  - replaced;
  - renamed;
  - "no longer";
- pages that now redirect.

Use labels such as:

`possibly moved or left: confirm`

`may have changed: confirm`

`possibly retired or renamed`

### Currency review

One high-reasoning agent reviews only flagged rows and proposed supersessions.

Rules:

- a redirect is a page change, not proof of retirement;
- two things may share a name;
- a one-off title in show notes is not automatically a title change;
- two plans existing simultaneously are not a price change;
- a third-party estimate conflicting with the company is a conflict, not a supersession.

Never state a company dollar price as current unless the company publishes it.

If company sources disagree or all prices are third-party, say so.

---

## 7. Repository layout

Create this structure during bootstrap if absent:

```text
README.md
prompt/
  PROMPT.md
  revised_prompt.md
  CHANGES.md

00-inputs/

00-scope.md
WORKFLOW_STATE.md
RUN_HISTORY.md

01-sources/
  web/
  archive/
  video/
    raw-captions/
  audio/
  docs/
  investor/
  jobs/
  press/
  third-party/
  code/
  provided/
  manifest-parts/
  blocked-parts/
  publish-dates.csv
  MANIFEST.csv
  BLOCKED.md

02-facts/

03-timelines/
  launches.md
  messaging.md
  leadership.md

04-competitors/
  <competitor-name>/
    01-sources/
      docs/
    02-facts/
    MANIFEST.csv
    BLOCKED.md

05-synthesis/
  design/
  parts/
  product-map.md
  offering.md
  customers-proof.md
  competitors.md
  glossary.md
  messaging-timeline.md
  organization.md
  direction.md
  open-questions.md
  company-brief.md
  one-page.md
  design-notes.md

06-checks/
  coverage.md
  verification-cited.md
  script-audits.md
  review-decisions.md
  american-english.md
  citation-claims-a.md
  citation-claims-b.md
  fact-fixes.md
  visual-review.md
  visual-review-2.md
  final-report.md

07-final-report/
  company-brief.pdf
  company-brief.html
  one-page.pdf
  one-page.html

tools/
  briefs/
  lists/
  outputs/
  digests/
  candidates/
  extracts/
  brief_html/

scratchpad/
```

Add `scratchpad/` to `.gitignore`.

### Prompt files

- `prompt/PROMPT.md`: exact prompt supplied at the start.
- `prompt/revised_prompt.md`: effective prompt after explicit changes made during the run.
- `README.md`: identical to `prompt/revised_prompt.md`.
- `prompt/CHANGES.md`: dated record of prompt changes during the run.

### File naming

Date first:

`2026-10-21 company.com - Product X page.html`

Transcripts:

`<date> <title> - transcription - <host>.md`

Use `" - "` as the separator.

Never use:
- `|`
- `/`
- `:`

inside generated file names.

Once a file is named and cited, never rename it.

### Captured files

Web pages:
- raw HTML;
- `.md` text copy;
- header containing:
  - URL;
  - capture date and time;
  - title;
  - method.

PDFs:
- original PDF;
- `.md` text copy;
- explicit page markers.

Transcripts:
- URL;
- embedding page where relevant;
- live date;
- upload date;
- series or course;
- every reliably identified speaker and title at the time;
- title source;
- duration;
- method;
- known caption errors;
- timestamps on paragraphs of about 30 to 60 seconds.

Transcript methods:

- `published captions`
- `published captions (auto-generated)`
- `published transcript`
- `machine transcription (<model/tool>)`

### Manifest

Columns:

```text
id, grade, title, publisher, url, date published, date captured, local file, method, notes
```

---

## 8. How to orchestrate

The main Claude Code session is the orchestrator. It owns the task graph, shared state, source and fact ID allocation, phase gates and final integration.

It should delegate large bounded work rather than doing all extraction, competitor analysis, synthesis or review itself when those tasks can be cleanly assigned to workers.

### 8.1 Gates and order

Phases run in strict dependency order.

A phase starts only when everything it depends on is complete, including capture added mid-run.

Maintain the task graph in `WORKFLOW_STATE.md`.

#### Capture gate

Facts do not start until:

- every capture job is finished;
- manifest parts are merged;
- publish dates are backfilled;
- `BLOCKED.md` is rebuilt;
- `06-checks/coverage.md` exists.

#### Facts gate

Synthesis does not start until:

- every fact has passed script checks;
- tags are checked on the full store;
- dates are checked on the full store;
- quotes are checked on the full store.

#### Verification gate

Review does not start until:

- every fact cited in synthesis has passed the model verification pass;
- corrected facts have been applied;
- synthesis sentences relying on changed facts have been fixed.

#### Review gate

The brief does not start until:

- all review decisions are made;
- accepted fixes are applied.

### Pipeline work

Do not idle at barriers.

While long work runs, prepare independent work such as:

- verification tooling;
- merge tooling;
- filter spot-check tooling;
- competitor capture;
- design template;
- rendering tools;
- phase briefs;
- work-list generation;
- deterministic checks.

### 8.2 Workflow topology

Split independent work across **multiple workflows** rather than placing every worker inside one large workflow.

Use workflows to maximize useful concurrency while keeping coordination simple.

Prefer workflows of about **two workers** when that allows more independent workflows to run concurrently.

Good candidates for separate concurrent workflows include:

- company website capture;
- video capture;
- audio capture;
- careers and people capture;
- press and investor capture;
- developer-surface capture;
- different competitor groups;
- independent extraction batches;
- independent synthesis files;
- independent verification batches;
- independent reviewers.

Where the runtime allows it, aim for roughly **8 to 16 useful workers running concurrently across workflows** during highly parallel phases.

Do not exceed **20 workers in one workflow**.

Do not create concurrency merely to hit a number. Use fewer workers when:

- work is small;
- workers would contend for the same files;
- tasks depend heavily on one another;
- the same host is rate-limited;
- the merge burden would exceed the speed gained.

Workers hitting the **same rate-limited host** stay in one coordinated workflow so request pacing is controlled centrally for that host.

The orchestrator never launches a workflow with:

- placeholder arguments;
- an unspecified input range;
- an unspecified output path;
- overlapping source-ID ranges;
- overlapping fact-ID ranges;
- a work-list slice whose size has not been checked.

Before launching a workflow:

1. create or validate its work list;
2. count the work-list records;
3. compare the count with the producing script's reported total;
4. split grouped records if necessary;
5. assign a concrete slice by IDs or row range;
6. assign exact output files;
7. assign scratch directory;
8. assign source-ID or fact-ID range where needed;
9. record the workflow and worker IDs in `WORKFLOW_STATE.md`.

A worker is done only when:

1. its assigned output file exists;
2. its output has passed any task-specific local check;
3. its short return message reports counts and paths;
4. the orchestrator confirms the expected files are present.

### 8.3 Agent prompts

Every agent prompt opens with a task-type line such as:

`TASK TYPE: EXTRACTION WORK, NOT A STATUS QUESTION`

Tell the agent:

- project-progress messages are not its task;
- it is done only when its output file has been written and checked;
- return no more than about 10 lines;
- detail belongs in its output files.

Agents read:

`tools/briefs/phase-brief-core.md`

plus a short phase-specific brief.

Create `tools/briefs/phase-brief-core.md` during bootstrap if absent.

Write each short phase-specific brief when that phase is ready to launch, so it reflects the repository's actual state at that point rather than assumptions made at bootstrap. In particular:

- write the Phase 4 brief immediately before launching Phase 4 synthesis workers;
- write the Phase 5 brief immediately before launching Phase 5 reviewers and fixers;
- write the Phase 6 brief immediately before launching Phase 6 brief writers, assemblers and final-review workers.

Do not prewrite those three briefs at the start of the project unless their contents are purely structural. Refresh any structural draft immediately before launch.

The core brief includes:
- evidence rules;
- tag rules;
- currency rules;
- speaker rules;
- writing rules;
- return format.

Never send the entire master prompt to every worker.

### 8.4 Batching

Group tasks that read the same inputs.

Aim for roughly:
- 60,000 words of source input per worker;
- at most two substantial deliverables per worker.

Do not combine roles requiring independent judgment.

Examples that stay separate:
- writing and verification;
- synthesis and skeptical review;
- original citation placement and independent citation review.

An agent may process many small records if a script controls the input and the model sees only bounded samples.

### 8.5 Work lists

Store work lists in:

`tools/lists/`

Agents consume slices by ID.

Never paste huge work lists into agent prompts.

Never launch agents with placeholder arguments.

Before batching:
- check the work-list length;
- compare it with what the generating script reported;
- split grouped records correctly.

### 8.6 Scratch space

Each worker gets its own scratch folder:

`scratchpad/<agent-label>/`

Workers do not share scratch directories.

### 8.7 Parallelism and file ownership

Each worker receives a bounded file set.

Parallel workers must not write the same file.

Use per-worker or per-batch files such as:

- `01-sources/manifest-parts/<worker>.csv`
- `01-sources/blocked-parts/<worker>.md`
- `tools/candidates/<batch>.jsonl`
- `06-checks/<reviewer>.md`

Shared files are merged or rebuilt only after the relevant workers finish.

The orchestrator or an explicitly assigned merge worker performs the merge.

Never let multiple capture workers append directly to `01-sources/MANIFEST.csv`.

Never let multiple reviewers overwrite one shared review file.

### 8.8 Resilience

Assume the container or process can stop unexpectedly.

Capture and extraction scripts must be resumable.

Extractors append source by source.

Record active workflow or agent identifiers in `WORKFLOW_STATE.md`.

After interruption:
- inspect existing outputs;
- resume rather than restarting;
- do not duplicate already completed capture or extraction.

If an orchestrator interruption also stops background workers, use the recorded workflow IDs and on-disk outputs to determine what completed before resuming.

### 8.9 Git

Commit at the end of each meaningful step.

Push when a remote exists and credentials permit it.

If no remote exists:
- commit locally;
- do not treat inability to push as a research failure.

Subagents do not make broad repository commits unless explicitly assigned.

The orchestrator should avoid committing partially merged shared state when related workers are still writing their assigned files.

At the end of every orchestrator turn, commit the current work in progress so a stop hook does not force an extra turn. Use a clear WIP commit message when the step is not otherwise ready for its normal milestone commit. If active workers are still writing, commit only stable files and leave their in-flight outputs untouched.

Do not create an otherwise unnecessary extra turn merely to satisfy the stop hook.

### 8.10 Status questions

When I ask for progress:

- answer from counts on disk;
- distinguish completed, running and queued work;
- use elapsed time from completed work to estimate remaining work if useful.

Then continue working.

When I ask a question during the run:
- answer it;
- keep independent work running;
- do not block the next action on my reply unless the decision genuinely requires me.

---

## 9. Phase 0: scope and source map

One high-reasoning agent reads:

- every file in `00-inputs/`;
- the company homepage;
- enough of the public site structure to map the record.

It writes:

`00-scope.md`

Include:

1. company name;
2. canonical URL;
3. products;
4. products in focus;
5. flagship and why;
6. public source channels;
7. URLs for each channel;
8. rough source volume;
9. capture method per channel;
10. competitors, with reasons;
11. competitor watch list;
12. priority checks;
13. unresolved ambiguities;
14. any scope change made during the run.

Do not begin bulk capture until this exists.

---

## 10. Phase 1: capture

Agents write into `01-sources/`.

Each capture agent or batch receives:
- its own manifest part;
- its own blocked part;
- a pre-assigned source-ID range.

Create scripts needed to merge these parts before the capture gate.

### 10.1 Company website

Discover:
- all sitemaps;
- navigation;
- relevant subdomains.

Treat navigation itself as a source when it establishes product grouping.

Save in full:

- product pages;
- solution pages;
- platform pages;
- pricing;
- packaging;
- customer stories;
- partner pages;
- trust and security;
- event pages;
- "why us";
- comparison pages;
- docs landing pages;
- terms;
- order forms where public.

Then run a **media and PDF sweep** script over every discovered sitemap page.

Write one row per discovered:
- PDF;
- embedded video;
- embedded audio;
- downloadable document;

to a work list in:

`tools/lists/`

### 10.2 Messaging history

Try Wayback CDX once.

Target:
- homepage;
- top product pages.

Aim for one snapshot per quarter across the lookback.

Capture:
- raw `id_` HTML;
- CSV containing:
  - snapshot date;
  - title;
  - meta description;
  - H1;
  - H2s.

If Wayback is blocked or persistently fails, record it and stop.

Do not spend time routing around the block.

Build the timeline later from dated first-party material.

### 10.3 Video

List company channels with:

```bash
yt-dlp --flat-playlist
```

Fetch metadata for every long-form video.

Prefer captions over audio transcription.

#### YouTube

Where appropriate, use:

```bash
yt-dlp \
  --js-runtimes node \
  --remote-components ejs:npm \
  --extractor-args "youtube:player_client=web_embedded" \
  --skip-download \
  --write-subs \
  --write-auto-subs \
  --sub-langs "en-orig,en" \
  --write-info-json \
  --ignore-errors
```

Keep `yt-dlp` current.

Space requests by roughly 15 to 30 seconds where repeated fetching risks throttling.

Retry rate-limited items once at the end in sequential batches with longer spacing.

#### Other hosts

For embedded media:
- inspect the embedding page;
- prefer published captions or transcript endpoints;
- pass the embedding page as referer where the host requires it;
- do not bypass bot challenges.

If the host structure exposes a public caption file, capture it.

#### No captions

Only when no published captions or transcript exist:

1. download audio;
2. transcribe with an available local speech-to-text model;
3. save the transcript;
4. preserve timestamps;
5. delete the temporary audio unless it is needed as evidence.

Create a shared caption parser that preserves one-word caption lines.

Rolling auto-captions often put single words on separate lines. Do not discard them.

#### Deduplication

Before transcription, deduplicate obvious:
- re-uploads;
- short edits;
- clips inside full webinars.

After transcription, run word-sequence overlap to catch duplicates not obvious from titles.

### 10.4 Audio

Capture:
- company podcasts by RSS;
- executives' guest appearances.

Prefer published transcripts.

Machine-transcribe only the highest-value episodes without transcripts.

### 10.5 People

Capture leadership plus relevant:
- product;
- engineering;
- AI;
- marketing;
- sales;
- customer;
- services;

leaders.

Record titles and dates.

Feed talks and podcast appearances into video and audio capture.

### 10.6 Careers

Capture every current public posting in:

- product;
- engineering;
- data;
- AI;
- marketing;
- sales;
- customer;
- services.

Prefer the ATS's public JSON endpoint where available.

Save raw JSON.

Create a deterministic script to count postings by team.

### 10.7 Investors

For public companies:
- SEC filings;
- earnings calls;
- investor days.

For private companies:
- funding releases;
- investor posts;
- founder interviews;
- Form D filings where applicable.

Check legal entities carefully.

Treat analyst-only funding claims as unconfirmed until matched by stronger evidence.

Compare funding rounds with the company's own "raised to date" boilerplate.

### 10.8 Press

Capture:
- newsroom;
- company blog;
- releases over the lookback.

If a wire service blocks originals:
- capture an accessible reprint;
- record that the original was blocked;
- do not pretend the reprint is the original publisher.

### 10.9 Third parties

Capture relevant:

- trade press;
- analyst material;
- review sites;
- customer announcements;
- partner announcements;
- marketplace listings;
- procurement records;
- customer filings;
- competitors' pages about the company.

### 10.10 Developer surface

Capture where relevant:

- docs;
- API references;
- changelog;
- status page;
- GitHub;
- package registries;
- public SDKs;
- MCP servers;
- plugins or connectors.

If public Git repositories can be cloned, use Git.

If package registries contain specifications or generated clients, unpack them as needed.

Create scripts for deterministic counts such as API operations.

### 10.11 Competitors

For each selected competitor capture, more lightly:

- website;
- key product pages;
- pricing;
- docs or knowledge base;
- press releases;
- two or three leader talks when useful;
- review sites;
- two homepage snapshots if Wayback works.

For suites, stay within the competing product.

Competitor docs:
- about 400 pages maximum;
- log exclusions;
- no need to transcribe videos inside competitor docs.

### 10.12 Closing capture

Create and run deterministic tools to:

1. merge manifest parts;
2. detect duplicate source IDs;
3. detect missing files;
4. validate local-file cells;
5. backfill publication dates;
6. merge competitor manifests;
7. rebuild `BLOCKED.md`.

Create:

`tools/backfill_publish_dates.py`

It writes:

`01-sources/publish-dates.csv`

The manifest merge applies this overlay without overwriting stronger existing dates.

Write:

`06-checks/coverage.md`

Coverage is reported:
- by channel;
- by competitor.

Do not pass the capture gate until these checks are complete.

---

## 11. Phase 2: facts

### 11.1 Canonical copy selection

Create a script that writes:

`tools/lists/extraction-scope.csv`

Choose one canonical source per duplicated piece of content.

Mark every other copy:

`duplicate of <source ID>`

Examples:
- re-uploads;
- shorter edits;
- clips inside webinars;
- same session on two hosts;
- identical pages at two URLs;
- translated docs.

For translated docs:
- English is canonical where available unless another language contains unique evidence.

Canonical preference:

1. longest complete version;
2. company's own copy;
3. original publisher;
4. earliest publication date.

Spot-check duplicate decisions manually with a review agent.

Duplicates remain captured.

### 11.2 Extract generation

Create a script that writes one extract per canonical source.

The extract must preserve original:
- line numbers;
- page numbers;
- timestamps.

Read in full:

- product pages;
- platform pages;
- pricing;
- solution pages;
- docs;
- launch posts;
- press releases;
- customer stories;
- comparison pages;
- research reports;
- recordings where company people present.

Use filtered extracts for:
- guest-led recordings;
- third-party pages;
- company blog guides;
- company how-to material.

The filter keeps paragraphs that contain:

- company name or known transcription variants;
- product names;
- modules;
- customers;
- prices;
- competitors;
- company-person phrasing such as:
  - "our platform";
  - "we found";
  - "we launched";
- unclear, probable or missing speaker labels.

Keep two paragraphs of context on each side.

Fail open for unclear speakers.

Competitor names are matched case-insensitively.

Repeated site chrome may be removed except:
- pricing blocks;
- plan cards;
- recurring product structures that carry substantive information.

### 11.3 Filter spot-check

One high-reasoning agent samples at least 40 dropped passages.

Weight the sample toward:
- guest-led material;
- unclear speakers;
- probable speakers;
- missing labels.

Report the miss rate.

If miss rate exceeds 5%:
- create a second-pass extract containing only newly retained passages;
- run a second extraction over that material.

### 11.4 Batches

Group extracts by:
- topic affinity;
- word count.

Target roughly:
- 60,000 to 90,000 words per extraction batch.

### 11.5 Competitor docs

Create a full-text search index over each competitor's docs.

Agents answer only the comparison questions:

- what it sells;
- who it sells to;
- developer and data access;
- AI features;
- outside AI tools;
- packaging;
- how a buyer starts;
- proof;
- anything it says about the focal company.

Open only matching pages.

### 11.6 Extraction

One high-reasoning extractor per batch reads every source in its assigned extract completely.

No sampling with:
- `head`;
- `sed`;
- `grep`;

as a substitute for reading the assigned source.

Write candidate facts as JSON Lines:

```json
{
  "topic": "",
  "claim": "",
  "quote": "",
  "source_id": "",
  "location": "",
  "source_date": "",
  "grade": "",
  "about": "",
  "said_by": "",
  "notes": ""
}
```

Append source by source.

Self-check every quote against the original captured file before finishing.

### Topics

- products-architecture
- offering-packaging-pricing
- customers-proof
- go-to-market
- roadmap-direction
- people-organization
- messaging-positioning
- partners-ecosystem
- ai-strategy
- glossary

### 11.7 Filing

Use scripts only for filing. Do not use a model to merge fact tables.

#### Normalize tags

`about`:
- company the fact is about;
- `"Market"`;
- or `"X (per Y)"` when one organization describes another.

`said_by`:
- organization responsible for the source.

A person's name belongs in notes unless the schema specifically requires it elsewhere.

Create:

`tools/normalize_candidate_tags.py`

### Final fact IDs

File candidates into topic tables.

Company facts continue each topic's numbering.

Competitor facts use:

`C-<NAME>-F###`

inside the competitor folder.

Flag likely duplicates.

Do not rerun filing after IDs are established unless explicitly repairing the database.

### Conflict detection

Flag same-company, same-subject facts that disagree on:

- numbers;
- prices;
- percentages;
- dates;
- limits;
- titles.

Recognize equivalent numerical phrasing such as:

`cut X by 96%`

versus a differently stated resulting value.

### Layer-1 checks

Every fact receives deterministic checks for:

- quote present at exact location;
- date matches manifest;
- source ID exists;
- tags valid;
- speaker label matches named speaker;
- overstatement flags.

Overstatement terms include:

- can;
- will;
- plan;
- aim;
- up to;
- some;
- early;
- beta;
- coming soon.

### Planted tests

Create known test fixtures containing:

- duplicate;
- conflict;
- wrong quote;
- wrong location;
- wrong date;
- overstated claim.

Every check must catch the corresponding test.

Then run a time-boxed high-reasoning audit of 10 decisions per script.

One fix round per script unless the failure is severe.

Record results in:

`06-checks/script-audits.md`

### Fact-store rows

Rows passing script checks receive verdict:

`pending, script-checked only`

Rows flagged for overstatement receive:

`pending, script-flagged`

Fact row schema:

```text
fact ID | claim | verbatim quote | source ID | location | source date | grade | topics | about | said by | verdict
```

Source date uses one of:

`<date> (published); captured <date>`

`as of <capture date>; last modified <date>`

`as of <capture date>`

Conflicts go in a dedicated Conflicts section in each topic file.

---

## 12. Phase 3 verification framework / post-synthesis cited-fact verification

Every fact passes script checks.

The expensive model verification runs only on facts actually cited by synthesis or the final brief.

After Phase 4, create:

`tools/cited_facts.py`

It collects every cited fact ID.

Facts not yet model-verified go through one high-reasoning verification pass.

Batch size:
- about 110 to 150 facts per reviewer.

Create:

`tools/make_snippets.py --ids`

Each fact packet includes:
- claim;
- quote;
- about 10 lines of source context;
- original location;
- manifest metadata.

For each fact verify:

1. Is the quote at the stated location?
2. Is the speaker attribution right?
3. Does the claim say more than the quote?
4. Is the date right?

Verdicts:

- confirmed
- corrected
- unsupported
- source unreachable

Prefer a narrower true claim over `"unsupported"`.

Apply verdicts with a script.

Re-run layer-1 checks on corrected rows.

Normalize quote formatting:
- line fragments joined with `" ... "`;
- no line-number markers inside quotes.

One separate agent rewrites every synthesis sentence whose supporting fact materially changed.

Remove temporary pending-check labels.

Write:

`06-checks/verification-cited.md`

Phase 6 repeats this process for any newly cited fact that has not yet been model-verified.

The final brief cites only verified facts.

---

## 13. Phase 4: sense-making

### 13.1 Preparation

Build these while extraction is running where dependencies permit.

#### Digests

One digest per synthesis file.

Include only relevant:
- topics;
- companies.

Remove duplicates.

One row per fact:

- ID;
- claim;
- date;
- grade;
- about;
- said by;
- verdict;
- conflict flag;
- current or superseded;
- staleness flag.

Do not include full quotes.

Agents look up a quote by ID only when wording matters.

If a digest exceeds about 60,000 words:
- split it across two writers;
- use a third agent to assemble.

#### Timelines

Draft by deterministic script:

- `03-timelines/launches.md`
- `03-timelines/messaging.md`
- `03-timelines/leadership.md`

Also build the currency file.

#### Competitor matrix

Build and populate the factual competitor matrix by deterministic script.

The script fills the evidence-bearing cells from the fact store, including:
- criterion or comparison field;
- relevant factual value where it can be derived directly from structured facts;
- fact IDs;
- dates;
- source or evidence metadata needed by later checks.

Do not make an agent manually re-enter factual matrix contents that can be populated from the store.

The synthesis agent writes only what requires judgment:
- criterion scores under the predefined rubric;
- positioning analysis;
- interpretation;
- ahead, level or behind judgments where the rubric calls for them;
- caveats about evidence quality or asymmetry.

Every judgment remains traceable to the script-populated evidence in the matrix.

#### Glossary

Draft by script from glossary facts.

### 13.2 Synthesis Part A

Runs without timeline dependency.

#### `product-map.md`

Cover:
- what the company sells;
- grouped the way the company groups it;
- layered diagram;
- every box backed by fact IDs;
- every arrow backed by fact IDs;
- dependencies;
- what the flagship depends on.

#### `offering.md`

Cover:
- editions;
- packaging;
- pricing signals;
- conflicting prices with both sources and dates;
- what a buyer gets at each stage.

#### `customers-proof.md`

Cover:
- named customers;
- metrics;
- source;
- date;
- whether the figure is company-authored or customer-authored;
- conflicting figures for the same customer.

#### `competitors.md`

Before scoring:
- define the columns;
- define the scoring rubric.

Then include:
- every cell sourced and dated;
- how competitors position against the company in their own words;
- ahead, level and behind only as explicit inference;
- a caveat when the company's evidence base is materially larger than competitors'.

#### `glossary.md`

One entry per company term.

Use fact-backed definitions.

Note:
- renamed terms;
- retired terms;
- possibly retired terms.

### 13.3 Timeline review

A dedicated agent reviews only:
- flagged timeline rows;
- proposed supersessions.

Apply section 6 rules.

### 13.4 Synthesis Part B

Runs after timeline review.

#### `messaging-timeline.md`

Dated table:
- wording before;
- wording after;
- what changed;
- relevant launches on the same timeline.

If wording appears across many old pages because content was edited later, say that it cannot be dated from those pages alone.

#### `organization.md`

Cover:
- leaders;
- title changes;
- people potentially moved or gone;
- teams visible in job postings.

#### `direction.md`

Cover:
- themes of direction;
- stated aims;
- what actually shipped.

Keep aims separate from shipped product.

One agent may write `organization.md` and `direction.md` together if within size limits.

#### `open-questions.md`

Write last.

Collect:
- open items;
- conflicts;
- stale items;
- unresolved flags.

Put the top five first.

For each:
- question;
- why it matters;
- what the public record says;
- who would know.

---

## 14. Phase 5: review

Reviewers read:

- synthesis files;
- only the fact rows those files cite.

Create bounded cited-fact packets in:

`tools/outputs/cited-facts/`

### Reviewer 1: technical product marketer

High-reasoning model.

Review concepts, not merely quotes.

Check every:
- diagram;
- `"X is part of Y"`;
- `"X runs on Y"`;
- `"X leads to Y"`;

against cited facts.

Check product capabilities versus staff doing the work.

### Reviewer 2: devil's advocate

High-reasoning model.

Read `direction.md` in full.

Have a script extract every:
- inference;
- `"heading toward"` claim;
- strategic directional interpretation;

from the other files.

Argue against each.

Ask:
- what else could the same facts mean?
- what evidence would decide between interpretations?

### Reviewer 3: skeptical insider

High-reasoning model.

Split into A and B if necessary.

Ask:
- what sounds naive?
- what may be out of date?
- what is missing?
- where does the currency rule change the wording?

### Reviewer 4: editor

Use a faster capable model.

Split A and B if needed.

Run the writing-rules script first.

Then:
- cut;
- tighten;
- remove repetition.

Do not alter:
- quotes;
- fact IDs;
- dates.

### Fixers

Two high-reasoning fixers, split by file group.

Each reads every relevant review report in full.

For every finding, choose:

- apply;
- apply in part;
- reject.

Give a reason.

Apply:
- accepted fixes;
- currency rule.

Merge decisions into:

`06-checks/review-decisions.md`

Include orchestrator decisions on issues escalated by fixers.

---

## 15. Phase 6: company brief

### 15.1 Design groundwork

Build this early while extraction runs.

If a design guide exists, adapt it for print.

If none exists, use the company-specific system created during bootstrap.

Create:

`tools/brief_html/`

Build a reusable print template containing:

- cover;
- running header;
- section page;
- numbered exhibit;
- finding title;
- source line;
- table;
- bar chart;
- layered product map;
- timeline;
- note;
- numbered source note.

Use `@page` rules.

Embed fonts only when:
- legally permitted;
- technically available.

Otherwise use a close available font and record the substitution.

Render using headless Chromium or equivalent.

Create:
- page-to-image rendering;
- design checks.

The design check flags:
- overflow;
- split exhibits;
- overlapping labels;
- large unexplained gaps.

### 15.2 Writing

Use two high-reasoning writers by section group.

Give each:
- explicit word budget;
- synthesis files;
- verified facts;
- exhibit specifications as fenced blocks.

Then use one high-reasoning assembler.

The brief answers, in this order:

1. What the company sells and how the pieces fit.
2. Who buys it, why and how.
3. How it positions itself and how that changed.
4. Where it is heading.
5. How it compares with competitors.
6. What the products in focus depend on, and who depends on them.
7. What to ask, and whom.
8. Evidence limits.
9. Sources cited.

### Section 1

Include the layered product map.

### Section 3

Include the messaging timeline.

### Section 7

Frame it as questions I would want to understand early.

Use neutral first person:

`The public record leaves a small set of questions I'd want to understand early.`

The exhibit headline can use:

`Five questions I'd want to resolve early across <topics>.`

Columns:

- question;
- public evidence side by side;
- whom to ask.

The follow-up list is grouped by area.

Bullet headings are topics only, for example:

`Plans and limits.`

Do not make a person's name the heading.

Do not make the section read like work being assigned to company employees.

Names belong in sentences only when factually useful.

Do not open the section with:
- a grade-I fact;
- a guess about reporting lines.

### Section 8

Evidence limits include script-generated counts for:

- blocked channels;
- source grades;
- thin S sources;
- share of customer proof that is company-reported;
- materially incomplete channels.

Use plain-language method names.

Do not expose repo internals in reader-facing copy.

### Section 9

Numbered source notes.

One note per citation number.

Each note includes:

- source title;
- publisher;
- date;
- grade;
- full public URL as a clickable link.

### Opening summary

Open with a short summary.

Include one product portfolio exhibit showing:

- product areas grouped the way the company groups them;
- newest launches marked;
- every box sourced;
- every date sourced.

This portfolio exhibit appears only once.

Do not duplicate the section 1 product map.

---

## 15.3 Citation system

### Markdown versus rendered output

Markdown remains the research trail.

It keeps fact IDs in brackets.

Rendered HTML and PDF show superscript source numbers instead.

Never show:
- repo paths;
- fact IDs;

to the reader.

### One number per source

A source gets the next citation number the first time any fact from it appears.

New numbers appear in reading order:

1, 2, 3 ...

Every later citation of that source reuses the same number.

A source is never assigned two citation numbers.

Within a citation group:
- deduplicate;
- show numbers lowest first.

A script-generated count across multiple sources gets:
- its own number;
- a note listing every underlying source.

The one-page uses its own independent numbering sequence.

### One deep link per source

Create:

`tools/resolve_citations.py`

Support:

`--check-live`

The source number's single link is based on the first fact cited from that source.

#### Web pages

Build a text fragment:

`#:~:text=`

from the first appropriate line or table cell of the fact's verbatim quote.

Use at least two words.

Validate against the captured page first.

Then open with headless Chromium.

If the text is no longer visible because:
- live page changed;
- content is hidden;
- tab or accordion blocks it;

fall back to the plain URL.

#### YouTube

Use:

`&t=<seconds>`

from transcript timestamp.

#### Other audio/video

Use page URL.

Include timestamp in the note.

#### Script counts

Link citation number to its source note.

The note lists all underlying sources.

#### Grade I

No public link.

### Sources section

Deduplicate by source.

Each source appears once.

Display:
- number;
- grade pill;
- title;
- publisher;
- date;
- full URL.

### Exhibit citations

Citations sit next to the exact text supported.

Examples:

#### Diagram
Citation after:
- group name;
- box title;
- part label.

#### Table
Citation after the supported phrase inside the cell.

A cell with multiple independent claims may have multiple citations.

#### Timeline
Citation after:
- wording;
- change description;

using the relevant facts for each.

No generic "facts" column.

Do not list fact IDs under an exhibit.

Exhibit source lines never point to repo files.

---

## 15.4 Matching exhibit citations

Exhibit specs carry facts per:

- group;
- box;
- part;
- phrase;
- cell.

Never pass one pooled list of citations to an exhibit.

### Pre-design reference copy

Immediately after the American English check and before the first design pass:

1. save the Markdown;
2. commit it;
3. record the Git commit hash in `WORKFLOW_STATE.md`.

This is the reference copy in which fact IDs sit beside the words they support.

If Git is somehow unavailable, create an immutable file:

`05-synthesis/company-brief.pre-design.md`

and record its checksum.

### Exhibit mapping tool

Create:

`tools/map_exhibit_citations.py`

Support:

```bash
python3 tools/map_exhibit_citations.py --commit <pre-design-commit>
```

It matches exhibits by title.

For each exhibit row verify:

- row facts equal the row facts in the pre-design copy;
- newly added facts are retained only if a synthesis draft cites them inline beside the same words;
- where a draft pairs a phrase with a fact ID, the exhibit uses that fact on that phrase.

Write:

`tools/outputs/exhibit-citation-check.md`

Required result:

`0 flags`

### Resolving flags

Do not guess.

Move citations to the phrase the source draft pairs them with.

If no fact backs a phrase:
- reword to what the fact actually supports;
- or cut the phrase.

An observation generated directly from a deterministic count may appear without an ordinary source citation if its derivation is clear and the underlying count is reproducible.

### Missing facts

If a captured source shows something the fact store missed:

1. add a new fact;
2. use a verbatim receipt;
3. check the quote against the captured source;
4. add a dated note to the fact-file header explaining what was missed;
5. update `"Sources read"`;
6. update Gaps where appropriate;
7. record the fix in:
   - `06-checks/fact-fixes.md`;
8. rebuild affected digests;
9. rebuild all counts based on the fact store;
10. rerun verification if the new fact is cited.

Never cite a source directly without a fact row.

Never renumber citations by hand.

---

## 15.5 Build

Create:

`tools/brief_html/build_brief_html.py`

It converts Markdown to HTML.

Create:

`tools/brief_html/place.py`

It places exhibits based on rendered page flow.

Create:

`tools/brief_html/make_final.py`

It:

1. builds the brief;
2. renders it;
3. writes PDF;
4. writes self-contained HTML;
5. builds the one-page;
6. runs the design check.

Outputs:

`07-final-report/company-brief.pdf`

`07-final-report/company-brief.html`

`07-final-report/one-page.pdf`

`07-final-report/one-page.html`

HTML is self-contained where practical:
- CSS inlined;
- local assets embedded or packaged reproducibly;
- fonts embedded only when permitted.

---

## 15.6 Typesetting rules

Applied by the build.

### Citation groups

A citation group never breaks across lines.

Do not permit a long unbreakable run to cause Chromium to shrink the whole document unnoticed.

The visual audit must catch that.

### Keep units together

Keep on one line where practical:

- ISO dates;
- URL paths;
- month and year;
- quarter and year;
- number and unit;
- hyphenated product names.

Examples:

`/why-company`

`35,000 tasks`

`13 days`

`Multi-Model`

### Diagram labels

Use no-break spaces where needed for multiword names.

### Headings

Use balanced wrapping where supported.

### Paragraphs

Avoid a one-word final line where supported.

### Lists

A lead-in ending in a colon stays with the list.

Keep at least two lines together across a page break.

Give numbered lists enough gutter width that numbers are never clipped.

### Tables

Header and body cells have equal left and right padding.

### Sources

Grade badge leads the source entry.

The citation-number column must fit the largest number.

Grade-I citations have the same typographic treatment even though they have no external link.

---

## 15.7 Reader-facing copy

Final reader-facing output contains no:

- repo paths;
- script names;
- fact IDs;
- build instructions;
- internal warnings;
- `"remove before sharing"` notes.

Translate methodology into normal language where needed.

For example:

- `"the coverage count"`
- `"the blocked-page log"`
- `"the archive snapshot index"`

Internal details stay in `06-checks/`.

---

## 15.8 Length

Target:

**10 to 15 body pages**

Do not count:
- cover;
- source list;
- end citation pages.

Tighten layout before cutting substantive words.

---

## 15.9 American English pass

Before design:

A separate high-reasoning agent checks:

- company brief;
- one-page;
- glossary.

Fix British usage except inside:
- quotes;
- fact IDs;
- file names;
- URLs;
- proper nouns.

Write every change to:

`06-checks/american-english.md`

Then create the pre-design reference snapshot.

---

## 15.10 One-page

The assembler also writes:

`05-synthesis/one-page.md`

Contents:

**Ten things to know**

Every item is sourced.

Render in the same design system.

The one-page has its own citation sequence and links directly to public sources.

---

## 15.11 Design notes

Write:

`05-synthesis/design-notes.md`

Include:
- what was derived from the supplied guide;
- what was derived from the company's public identity;
- what was not used;
- why;
- font substitutions;
- licensing constraints.

If a supplied licensed brand font would require company permission before external distribution, say so.

Grade-I material may appear in the working brief for me but must be removed from any version intended to be shared externally unless I explicitly authorize it.

---

## 15.12 Targeted edits after the brief is final

When I ask for `"only these edits"`:

1. change only the named Markdown;
2. preserve all other copy, exhibits, citations and styling;
3. make the smallest additional change needed for grammar or coherence;
4. report that additional change.

Examples:
- remove a now-duplicated line;
- replace a pronoun that lost its antecedent.

Rebuild with:

`tools/brief_html/make_final.py`

Do not rerun exhibit-placement search unless page flow requires it.

If text before an exhibit changes:
- update that exhibit's index in:
  - `tools/brief_html/placement.json`
- so it remains after the same conceptual passage.

Compare every PDF page before and after by script using extracted text.

Confirm only expected pages changed.

If page flow moves unintentionally:
- use a layout-only page-break mechanism such as:
  - `BREAK_BEFORE`
- in the HTML builder;
- restore intended pagination without changing unrelated copy.

Re-run all checks.

If an exhibit title changed, `map_exhibit_citations.py` may match it by row labels.

Report any citation-number changes.

Because numbers are assigned at first occurrence:
- deleting the first use of a source may move that source's number;
- intervening numbers may shift.

Look at every changed page as an image before returning the PDF.

---

# 16. Final citation check

Run after the last render and after any later change.

Check against the repository, not the live web, except for link-resolution checks already specified.

## 16.1 Script check

Create:

`tools/check_citations.py`

It reads:

- final HTML;
- citation maps;
- Markdown;
- fact store;
- manifests;
- captured sources.

Citation maps live at:

`tools/outputs/citation-map-<name>.json`

Each map records:
- one note per source;
- facts behind every citation.

Check:

### Numbering
- new numbers appear in reading order;
- later citations only reuse prior numbers;
- every number has one note;
- every note is used.

### Deduplication
- no source has two numbers;
- no two notes represent the same source;
- no two notes link to the same canonical page unless explicitly justified.

### Nothing lost
- every source behind every cited fact appears behind a citation number;
- multi-source count notes include every underlying source.

### Back to Markdown
- each fact is cited the same number of times where appropriate;
- HTML citation placement corresponds to the fact placement in Markdown.

### Back to source
- citation URL equals the manifest URL for the source.

### Receipt
- fact quote exists in captured source;
- text fragment exists in captured HTML where applicable.

### PDF
- PDF contains the same intended links.

Write:

`tools/outputs/citation-check-<name>.md`

Required result:

`0 flags`

Run:

`tools/map_exhibit_citations.py`

at the same stage.

Required result:

`0 flags`

---

## 16.2 Claim review

Two independent high-reasoning agents split the citation-check rows at roughly 25,000 words each.

For every citation, judge:

**Does the fact support the exact words immediately before the citation?**

When unclear:
- inspect the fact row;
- inspect captured source;
- inspect local context.

Write:

- `06-checks/citation-claims-a.md`
- `06-checks/citation-claims-b.md`

Include:
- counts;
- one row per problem;
- recommended fix.

No deterministic script can replace this semantic review.

---

## 16.3 Triage

First determine whether each problem already existed in the pre-design reference copy.

If a later design or editorial edit broke a correct pairing:
- restore the pre-design pairing.

Classify every substantive issue:

### Wrong statement
The copy says something the facts or sources contradict.

Fix the words.

### Wrong citation
The claim is true, but this fact does not support it.

Replace it with the correct verified fact.

Look first:
- nearby;
- in synthesis drafts;
- in the fact store.

### Too few citations
Existing citations each support part of the claim but not the entire compound statement.

Add coverage where practical or narrow the statement.

If a correction changes a competitor rubric criterion:
- rescore the cell;
- rescore total;
- update `competitors.md`;
- update the final exhibit.

When a score refers to a particular product in a suite, name it in parentheses.

Example:

`Ahrefs (Brand Radar)`

---

## 16.4 Rebuild and re-check

Rebuild with:

`tools/brief_html/make_final.py`

Then rerun:

- `tools/check_citations.py`
- `tools/map_exhibit_citations.py`

Repeat until both report:

`0 flags`

Report for:
- body text;
- each exhibit;

these counts:

- total citations;
- new numbers;
- reused numbers;
- number-order violations.

Required:

`0 number-order violations`

---

## 16.5 Planted-error test

Create:

`tools/test_check_citations.py`

Operate only on disposable copies in a temporary directory.

Plant these six errors:

1. one source assigned two numbers;
2. one source removed from its note;
3. one new citation number out of order;
4. facts behind two citations swapped;
5. one number linked to the wrong page;
6. two source notes linked to the same page.

The test passes only if:
- all six are caught;
- real files remain unchanged;
- real files still pass.

Never plant errors in real research files.

---

## 16.6 Visual audit

### Measure

Create:

`tools/brief_html/visual_audit.py`

Lay final HTML out at the actual printed content width:

`page width - @page side margins`

Flag every:

- exhibit tile;
- part;
- group;
- table cell;
- timeline row;
- note;
- diagram box;

where:

- text spills past its edge;
- citation spills;
- padding is too tight;
- labels overlap;
- content crowds borders.

Example failure:

`Opportunities` plus superscript crossing the tile edge.

### Fix causes, not instances

Grid columns should not become narrower than their longest indivisible content.

Use rules such as:

`minmax(min-content, Nfr)`

where appropriate.

Table label columns must accommodate their longest important word.

Diagram titles must leave room for superscripts.

Never shrink text below the design type scale merely to force one box to fit.

---

## 16.7 Human visual review by agent

Render every page of both PDFs to images at about 110 dpi.

Create:

`tools/pdf_pages_to_png.py`

Output to a scratch directory.

Assign a separate high-reasoning review agent.

It opens **every page image in order with no sampling**.

It checks as a reader would for:

- text touching an edge;
- citation numbers touching an edge;
- crowding;
- uneven gaps;
- bad padding;
- bad margins;
- cramped exhibits;
- stretched exhibits;
- stranded headings;
- orphan lines;
- one-word wraps;
- citation alone on a line;
- split dates;
- inconsistent styling;
- leftover markup;
- odd characters;
- repo paths;
- visible fact IDs;
- anything broken.

Write:

`06-checks/visual-review.md`

One row per issue:

- page;
- location;
- issue;
- severity;
- fix.

Also include a line for every clean page.

The review agent edits nothing.

### Diagnose before fixing

Check each diagnosis against the actual HTML.

Do not alter a rule because a reviewer misdiagnosed normal ragged wrapping as a broken unit.

### Orchestrator review

The main Claude Code session also views every page.

In addition to visual quality, check:

- copy that presumes I already work at the company;
- internal language exposed to the reader;
- stale counts;
- stale section 8 numbers;
- stale exhibit totals;
- stale cover metadata.

---

## 16.8 Final visual loop

Fix every issue marked `"fix"`.

Fix minor issues too when inexpensive.

Fix the systemic cause:
- CSS rule;
- grid structure;
- column width;
- page-break rule;
- layout logic.

Do not hand-nudge one isolated instance unless the issue is genuinely unique.

If pagination changes:
- rerun `tools/brief_html/place.py`.

Then rerun:

- design check;
- visual audit;
- citation check;
- exhibit citation check;
- planted-error test.

Render pages again.

Have the visual reviewer re-check every changed page.

Repeat until there are no open `"fix"` issues.

If a second report is needed, write:

`06-checks/visual-review-2.md`

---

# 17. Done means

The project is done only when all of the following are true.

### Repository

- required directories exist;
- `WORKFLOW_STATE.md` marks every phase complete;
- `RUN_HISTORY.md` is current;
- `README.md` matches `prompt/revised_prompt.md`;
- `prompt/PROMPT.md` preserves the prompt supplied for the run;
- prompt changes are recorded in `prompt/CHANGES.md`;
- meaningful work is committed;
- push succeeds when a configured remote permits it.

### Sources

- every used source is in a manifest;
- every source has a publication date or stated reason it has none;
- `BLOCKED.md` lists what could not be accessed;
- coverage report exists.

### Facts

- every fact passes deterministic checks;
- every synthesis-cited fact is model-verified;
- every final-brief fact is model-verified;
- corrections are reflected back into the fact database;
- conflicts remain visible rather than silently harmonized.

### Counts

Every published count has:
- deterministic script;
- saved output;
- reproducible inputs.

### Citations

Final citation checks pass:

- `tools/check_citations.py`: 0 flags;
- `tools/map_exhibit_citations.py`: 0 flags;
- claim review issues fixed;
- citation numbers introduced in reading order;
- one citation number per source;
- one deep link per source;
- every note used;
- planted-error test passes.

### Visual output

- `tools/brief_html/visual_audit.py` reports no overflow or tight-box failure;
- visual review has no open `"fix"` issue;
- every final page has been viewed as an image at least once after the final material changes.

### Deliverables

`07-final-report/` contains:

- `company-brief.pdf`
- `company-brief.html`
- `one-page.pdf`
- `one-page.html`

The HTML files are self-contained where practical.

The brief:

- has 10 to 15 body pages;
- has citations numbered in document order;
- has working links;
- has exhibit citations next to the labels they support;
- contains no repo internals;
- does not presume I already work at the company.

---

# 18. Final report back to me

Finish with a short run report.

Include:

1. source counts by grade;
2. source counts by channel;
3. fact counts by verdict;
4. the top five open questions;
5. blocked sources or channels I may want to open manually;
6. the three findings you are least sure of;
7. why each of those three remains uncertain;
8. any material substitution caused by unavailable tooling;
9. final deliverable paths;
10. final check status.

Do not substitute this report for the deliverables.

The research repository and final artifacts are the work.

 # Amendment to company research prompt: execution integrity

Append this section to the end of the existing company research prompt. It adds execution safeguards without changing the existing research scope, evidence standards, writing rules, deliverables, or phase order. Where an existing completion instruction could be satisfied by an agent's assertion alone, the machine-verified requirements below take precedence.

---

## 19. Execution integrity and machine-enforced completion

The orchestrator remains responsible for task assignment, workflow coordination, integration, and reporting. **It is not the authority for declaring a phase or the project complete.** Deterministic gate checks and a final acceptance check determine completion from on-disk evidence.

### 19.1 Bootstrap the control layer

During the existing tool bootstrap, create and test these reusable scripts before they are needed:

- `tools/check_phase_gate.py`: validates a named phase and returns a nonzero exit code unless all requirements pass.
- `tools/reconcile_work.py`: reconciles assigned input IDs against documented output dispositions for each work list.
- `tools/check_release.py`: independently verifies final acceptance and writes a release manifest.

Create these machine-readable files or directories:

- `tools/outputs/worker-ledger.jsonl`
- `tools/outputs/gates/`
- `tools/outputs/reconciliation/`
- `07-final-report/release-manifest.json` (only after final acceptance passes)

Use deterministic schemas, atomic writes, and stable IDs. Create small fixtures for the scripts, including missing, duplicate, failed, and incomplete records. Record script creation and material changes in `WORKFLOW_STATE.md` and, where applicable, `RUN_HISTORY.md`. The ledger and gate reports are execution evidence, not substitutes for the existing research artifacts.

### 19.2 Worker execution ledger

Before launching a worker, register a record with:

- unique `worker_id`, `task_id`, workflow ID when available, and attempt number;
- exact input IDs or a bounded, immutable work-list slice;
- expected output paths and required validators;
- status: `queued`, `running`, `succeeded`, `failed`, or `blocked`;
- start and finish timestamps when available;
- process or workflow exit status when exposed;
- output-validation status and SHA-256 hashes of validated outputs.

Update the ledger as work proceeds. A worker is `succeeded` only when its execution has ended, every required output exists, its assigned output checks pass, and its output hashes have been recorded. A reassuring agent message is never sufficient. An interrupted or unobservable worker remains unresolved until on-disk outputs and the available runtime status establish its outcome. Preserve failed attempts when retrying; retries receive a new attempt number and do not erase failure history.

Workers do not edit the shared ledger directly. The orchestrator or a specifically assigned ledger writer updates it. Use atomic writes or a single-writer merge so concurrent workflows cannot corrupt the ledger.

### 19.3 Reconcile every assigned input

For each bounded work list, `tools/reconcile_work.py` compares the original assignment with the completed records. Every assigned ID must have exactly one final disposition, such as `completed`, `duplicate`, `excluded`, or `blocked`, with a reason and evidence path where applicable. Explicitly declared one-to-many outputs are allowed, but each expected output must be accounted for. Flag unassigned outputs, duplicate processing, overlapping worker assignments, missing outputs, and undocumented exclusions.

Apply reconciliation at the relevant phase boundaries to:

1. discovered sources versus captured, excluded, duplicate, or blocked sources;
2. canonical sources versus extraction dispositions;
3. candidate facts versus filed, duplicate, or rejected dispositions;
4. facts cited in synthesis or the final brief versus model-verification verdicts;
5. review findings versus applied, partly applied, or rejected decisions;
6. final citation references versus source notes and supporting fact IDs;
7. final rendered PDF pages versus visual-review records.

Write a report in `tools/outputs/reconciliation/` for each reconciliation, including assigned, completed, excluded, blocked, duplicate, missing, and unexpected counts. Do not treat zero extracted facts as proof that a source was processed: record an explicit completed-with-zero-facts disposition. A blocked or excluded item may be accounted for without being successfully captured; retain the coverage limitation in the existing blocked and coverage reports.

### 19.4 Fail-closed validation

Every required validation has one of three outcomes:

- `PASS`: it executed, checked its expected inputs, and found no disqualifying issues;
- `FAIL`: it executed and found disqualifying issues;
- `UNKNOWN`: it did not run, crashed, timed out, checked fewer than the expected inputs without an explained disposition, or produced an invalid or incomplete report.

`FAIL` and `UNKNOWN` both block the gate. An absent or empty report is not a pass. Each machine-readable check result must include the checker name and version or checksum, input identifiers or hashes, expected and checked record counts, failure count, status, and completion timestamp. A check reporting zero flags but failing to account for its expected input set does not pass.

### 19.5 Enforce phase gates in code

Implement:

```bash
python3 tools/check_phase_gate.py --phase capture
python3 tools/check_phase_gate.py --phase facts
python3 tools/check_phase_gate.py --phase verification
python3 tools/check_phase_gate.py --phase review
python3 tools/check_phase_gate.py --phase final
```

The checker reads the existing phase requirements, the ledger, reconciliations, validation reports, and required on-disk outputs. It emits a machine-readable report under `tools/outputs/gates/`, plus a concise human-readable summary. It exits with code 0 only on `PASS`; `FAIL` and `UNKNOWN` return nonzero. Include the inputs and hashes on which the result depends.

Map these gates to the existing dependencies:

- **Capture:** all registered capture work has a validated terminal disposition; manifest parts are merged; IDs and local files validate; publication dates are backfilled; blocked records and coverage are complete; capture reconciliation passes.
- **Facts:** all canonical extraction inputs are reconciled; fact filing is reconciled; required full-store quote, date, source, tag, and other layer-1 checks pass; required script fixtures and audits are recorded.
- **Verification:** every fact cited by the synthesis has a completed model-verification verdict; corrections are applied; dependent synthesis copy is updated; corrected facts pass layer-1 checks.
- **Review:** every required independent review exists; every finding has a documented disposition; accepted fixes are applied; outstanding mandatory fixes are zero.
- **Final:** all previously required gates remain valid; newly cited facts are verified; citation, exhibit, planted-error, design, and visual checks pass; every final page is accounted for; required deliverables exist.

Phase 4 synthesis still follows the existing **facts gate**. The **verification gate** runs after initial Phase 4 synthesis and before Phase 5 review, as already specified. Do not interpret the order of the gate names above as changing the prompt's phase dependencies.

Do not begin downstream dependent work unless its required gate exits successfully. Independent preparatory work may continue under the existing pipeline-work rules. `WORKFLOW_STATE.md` may report a phase complete only after the gate passes; record the gate report path and its input hashes. If relevant inputs change later, the prior gate becomes stale and must be rerun before downstream acceptance.

### 19.6 Independent release acceptance

After the final render and all final checks, run `tools/check_release.py`. This program must inspect repository artifacts and machine-readable evidence rather than relying on the orchestrator's prose summary. It must verify:

1. every required phase gate passed and remains valid for the current inputs;
2. all registered work has validated terminal dispositions, with no unresolved assigned work;
3. every required reconciliation accounts for its entire assigned input set;
4. every required test and check executed successfully against the expected inputs;
5. every cited fact has a valid final verification verdict and every required review finding has a disposition;
6. the final PDF and HTML artifacts are the exact files checked by the final validation and visual-review processes;
7. no relevant source, fact, citation map, template, or output changed after its check without the affected checks being rerun;
8. any accepted exceptions are explicit, justified, and consistent with the existing blocked-source and evidence-limit rules.

The acceptance check is deterministic and must not simply parse an agent's statement that the project is complete. A separate high-reasoning agent may inspect the acceptance evidence and challenge anomalies, but its opinion cannot override a failed machine check.

### 19.7 Bind acceptance to exact artifact versions

Only on successful release acceptance, write `07-final-report/release-manifest.json` with:

- Git commit hash where available;
- SHA-256 hashes of the final PDF, HTML, and one-page deliverables;
- hashes of the source manifest, fact store, citation maps, and relevant build inputs;
- gate names, statuses, report paths, and report hashes;
- reconciliation and required test statuses;
- final visual-review status and page counts;
- accepted exceptions and their supporting records;
- acceptance timestamp and checker version.

Avoid circular hashing: do not include the release manifest's own hash in itself. If the release manifest is committed after acceptance, record the validated content commit or tree identifier and note the manifest-only commit separately. Any material edit to a final artifact or its evidence after acceptance invalidates the release until the affected checks and acceptance run again.

### 19.8 Tests for the control layer

In addition to the existing planted citation tests, test that the control layer refuses to pass when:

- a worker reports success but a required output is absent;
- one assigned input has no final disposition;
- two workers claim the same exclusive input slice;
- a validator never ran or inspected fewer records than expected;
- a phase is marked complete in `WORKFLOW_STATE.md` without a passing gate;
- a checked final artifact is modified after validation;
- a required review or visual-inspection record is missing.

Run tests only on disposable fixtures or copies. Do not plant faults in the real research corpus. Save the test results and require them to pass at final acceptance.

### 19.9 Completion and final report additions

Section 17's definition of done additionally requires:

- worker ledger complete and consistent with on-disk outputs;
- every required input-to-output reconciliation passed;
- all phase gates passed for the final relevant inputs;
- no required validation remains `FAIL` or `UNKNOWN`;
- independent release acceptance passed;
- the release manifest identifies the exact validated deliverables.

Section 18's short final run report additionally includes the execution-integrity result: number of registered worker attempts, successful tasks, failed or blocked tasks, reconciled inputs, gate statuses, accepted exceptions, and release-manifest path. Report unresolved work explicitly; never call the project done when acceptance fails.

### 19.10 Token-efficient execution of safeguards

Implement the control layer primarily with deterministic scripts. Do not assign model agents to perform checks that scripts can reliably complete, including file existence, schemas, IDs, work-list reconciliation, counts, status transitions, hashes, and test exit codes.

Keep model-facing check output concise. Each validator prints only its gate name, `PASS`/`FAIL`/`UNKNOWN`, assigned and checked counts, number of exceptions, and the path to a detailed machine-readable report. Store complete records on disk. When a check fails, show the orchestrator only the failing IDs and the context needed to repair them, not the full ledger or research corpus.

Use incremental validation where safe: rerun checks only for inputs affected by a change, while still performing the required complete reconciliation and release acceptance before declaring the project done. Cache results only when input hashes and checker versions match. Do not weaken coverage, verification, independence, or fail-closed behavior to save tokens.

Retries must be targeted and bounded. Retry only failed or unaccounted-for work slices, preserve validated outputs, and record each attempt in the worker ledger. Escalate repeated failures as explicit blocked or unresolved items rather than repeatedly reprocessing the full batch.

Do not spawn extra high-reasoning review agents merely to confirm deterministic `PASS` results. Preserve every independent semantic and visual review required elsewhere in this prompt. Summarize their results for the orchestrator and read detailed findings only when needed for a decision or fix.

Track available usage metrics in `RUN_HISTORY.md`, including model tokens, tool execution time, retries, and the number of revalidated records where exposed by the runtime. Do not invent unavailable measurements or assert a guaranteed token-cost percentage. These optimizations are subordinate to correctness: `FAIL` and `UNKNOWN` still block the relevant gate.
