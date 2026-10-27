# Evidence core

Apply this file only to tasks that inspect, extract, verify, synthesize, or cite
evidence. The immutable assignment and phase prompt define your actual work.

## Grades

- P: the company's own public words, code, filings, jobs, and statements by its people.
- S: a named third party's first-hand record, such as a customer or partner announcement.
- T: press, analysts, reviews, reprints, aggregators, and competitors describing the company.
- I: non-public material supplied by the user.

A company-authored customer story is P. Grade by authorship and first-hand
status, not merely the quoted speaker or hosting domain.

## Fact receipts

Every fact needs a verbatim quote, manifest source ID, exact location, source
date, grade, `about`, and `said_by`. A path, `website`, `many pages`, or `count
script` is not a receipt. Counts need a reproducible script and saved output.

Check a quote against the original captured source. Preserve wording when it
matters. Ellipses may shorten but never alter meaning.

Published date and modified date are different. Do not promote deploy,
homepage, pricing-page modification, or shallow-clone times to publication
dates. For recordings, use the live date when known and keep upload date in
notes.

## Claim discipline

- Aims are not achievements.
- `can` is not `does`. `some` is not `all`. `up to` is not typical.
- Beta is not general availability. A job posting is not a hire.
- Employee-delivered work is not product capability without product evidence.
- Keep contradictions visible with both sources and dates.
- Start inference with `My inference:` and name its supporting fact IDs.
- Scope every absence to the sources searched.
- Mark every customer, client, or partner relationship with its basis,
  wherever it appears: a sentence, a list, a table, a diagram label, a
  caption, or a fact row.
  - `Stated` means a source names the relationship.
  - `Inferred` means the evidence supports it but no source names it. The
    mark goes on the relationship itself (for example "Microsoft (inferred
    client: …)"), followed by the evidence and fact IDs.
  - `Lead` means an inference from thin evidence, such as one commit, a
    repository name, a demo, or one person's activity. Write it as
    "Chubb (lead, thin evidence: …)", naming the evidence. A lead may appear
    wherever it is relevant, but it carries the least weight: never use it to
    support a conclusion on its own, and never count it with stated or
    inferred relationships.

  In the fact store, record the basis in the fact's notes (`Relationship
  basis: Stated`, `Inferred`, or `Lead (thin evidence)`), so every later step
  carries it.

  In an exhibit of customers, clients, or partners (a list, table, logo
  wall, or count), order the entries stated first, then inferred, each
  marked. Put leads last, below a dividing rule, under a label such as
  "Leads (thin evidence, not established)". Counts and totals include only
  stated relationships unless the count says otherwise. Never let an
  inferred client or a lead become a stated one through summary, emphasis,
  position, or a logo, name, or count.

Name a transcript speaker only when the record establishes identity. Otherwise
use `a speaker in the <title> webinar`. Diarization labels (`Speaker 1`, ...)
group voices and mark turns but can split or merge people; tie a label to a
name only where the transcript itself establishes it, and mark it `(probable)`. Mark probable or unclear labels. A fact
depending on uncertain transcription remains inference or unresolved.

`about` names the subject company, `Market`, or `X (per Y)`. `said_by` names the
organization responsible for the source. Put a person's name in notes unless a
separate field is assigned.

## Currency

Evidence within the last quarter may support plain current wording. Older
current-state evidence needs `as of <date>`. A repository, spreadsheet, or
other document snapshot is dated by its own content or its last commit, not
by when it was captured; every fact from it carries that date. When the
snapshot is more than two quarters older than the research date, say so
wherever it is used, for example "as of December 2025, about three quarters
before this research", and never let it stand for the present. Plans,
forecasts, and targets are stated as plans with their date, not as results. Flagged rows use `last confirmed
<date>` or `possibly retired`. A redirect is not retirement proof. A one-off
title is not automatically a title change. Simultaneous plans are not a price
change. Never state a company dollar price as current unless the company
publishes it.

## Citation meaning

A citation supports the exact adjacent words. Never cite a source directly in
the brief without a fact row. Structural correctness does not establish
semantic support. An independent claim review remains required.
