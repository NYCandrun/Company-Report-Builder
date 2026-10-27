# Runtime core

The orchestrator owns shared state. A worker edits only its exact output paths
and its private `scratchpad/<worker-label>/` directory. Do not edit the worker
ledger, `WORKFLOW_STATE.md`, `RUN_HISTORY.md`, shared manifests, global blocked
logs, citation maps, repository configuration, or another worker's output
unless the assignment names that shared-state responsibility.

The one infrastructure exception is the controlled `python3 -m research_control
web ...` interface. It may update the run-local URL ledger and immutable response
cache. That cache is transport only: a URL or cached object is not research
evidence, brand evidence, or a factual claim until the consuming packet admits
it through its own required evidence records.

## Assignment contract

Before work starts, the assignment must provide:

- task type and stable worker/task/attempt IDs;
- immutable input IDs or an exact work-list slice;
- exact output paths and scratch directory;
- required schema and validators;
- completion criteria and concise return format.

Do not infer placeholder arguments, unbounded input, ID ranges, or output paths.
Stop that assignment as blocked if one remains ambiguous, while unrelated work
continues.

## Completion

You are done only after the assigned output exists and its task-local check
passes. Return at most about 10 lines: status, assigned count, completed count,
exception count, output paths, validator result, and any blocked IDs. Detail
belongs in output files.

A progress message is not completion evidence. The orchestrator records hashes
and terminal status after inspecting outputs. Preserve partial resumable output
source by source. On interruption, inspect and resume. Do not duplicate
completed work.

Never write to a shared manifest or shared review file from parallel workers.
Write a worker-specific part for deterministic single-writer merge. Never
commit unrelated workers' files.

Back off when rate limited and record blocked items. When you use a browser
(screenshots, rendering, inspecting a page), present as desktop Chrome in a
desktop-sized window (for example 1440x900, not mobile) so you see the desktop
layout and content, unless the task asks for a mobile view.

## Checks and source wording

A check that flags text you believe is right as the source has it (a product
or standard name shaped like an ID, a quoted term) is a false positive. Do not
reword the source's text to satisfy it: leave it and name the check and the
text in your report, so the orchestrator fixes the check.

## Reports in plain English

Your report goes to the orchestrator and may be shown to the user as is.
Write for the user in plain English. Leave out jargon and internal shorthand ("shard", "slice", "packet", "gate", "reconcile", "the X repo"): say what a thing is ("a batch of 48 facts to verify", "a chunk of a source's text", "the phase checks"), name a repository by its GitHub name (owner/repository, for example carlmueller-tribe/mori), and name a source by what it is (a podcast episode, a company blog post), not only by its ID.
