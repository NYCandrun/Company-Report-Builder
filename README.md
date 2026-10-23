# Company research agent

This repository is an executable company-research system. Given a public
company URL, carry the run from source capture through a cited, visually
reviewed company brief. Do not stop after planning or scaffolding.

## Start here

Take the company URL from the user's message. Then run, from the repository
root:

```bash
python3 -m research_control preflight
python3 -m research_control init --url "COMPANY_URL"
python3 -m research_control check --phase bootstrap
python3 -m research_control next
```

If a run already exists, do not initialize it again. Run `status` and resume:

```bash
python3 -m research_control status
python3 -m research_control next
```

`next` writes self-contained task packets under
`tools/outputs/task-packets/`. Read and execute every pending packet for the
current phase. A packet identifies its exact inputs, outputs, prompt bundle,
validation requirements, and task ID.

Before executing a packet:

```bash
python3 -m research_control task start TASK_ID --worker-id STABLE_WORKER_ID
```

After its outputs exist:

```bash
python3 -m research_control task finish TASK_ID
```

Use a different worker or genuinely separate context for every task marked
`independent: true`. Parallelize only packets that `next` presents together.
The orchestrator alone updates shared state and manifests.

When all packets for the phase are finished, run:

```bash
python3 -m research_control check
```

If the check fails or is unknown, repair only the reported failures and rerun
it. If it passes, run `next` again. Continue until the current phase is
`release_acceptance`, then run:

```bash
python3 -m research_control release
```

## Authority and context

Read these files when beginning a run:

1. `RESEARCH_CONSTITUTION.md` for research and evidence principles.
2. `WORKFLOW.yaml` for phase order and artifact contracts.
3. Only the task packet and files named by that packet while doing worker work.

Do not load `docs/legacy-prompt.md` during normal execution. It is the preserved
historical policy and traceability baseline, not the runtime prompt. Consult it
only to resolve a documented ambiguity, and record the resolution.

The workflow order is:

```text
bootstrap -> scope -> capture -> facts -> initial synthesis
          -> cited-fact verification -> corrected synthesis
          -> independent review -> final brief -> publication checks
          -> release acceptance
```

Earlier phase outputs may be prepared only where `WORKFLOW.yaml` explicitly
allows it. Never publish or claim completion merely because an agent says work
is done.

## Research execution

- Use public sources only. Respect robots rules, rate limits, logins, paywalls,
  and bot challenges. Record blocked sources rather than bypassing access.
- Preserve every source locally and record its source ID, URL, date, grade,
  capture method, and exact local receipt.
- Use the runtime's browsing and document tools for discovery and unusual
  formats. The included `capture` helper is appropriate for ordinary public
  pages; it is not permission to bypass access controls.
- Preserve partial, validated work. Retry only failed or unaccounted inputs.
- Do not silently omit a source, assignment, finding, page, or zero-fact result.
- Keep writing, cited-fact verification, skeptical review, citation-claim
  review, and visual review in independent contexts as required by the task
  packets.
- Put detailed results in repository files. Keep worker returns concise.

## Rendering

The final-writing packets create `05-synthesis/company-brief.md` and
`05-synthesis/one-page.md`. Render them with:

```bash
python3 -m research_control render
```

This creates the required HTML and PDF files in `07-final-report/`. Inspect
every rendered page and complete the visual-review packet before release.

## Completion

The run is complete only when all of the following are true:

- Every required phase check is `PASS` on current artifacts.
- Every assigned input has one terminal disposition.
- Required independent semantic reviews and their decisions exist.
- Citations resolve from the final claim to a fact and captured source.
- The company brief and one-page output exist as both HTML and PDF.
- Every rendered page has a visual-review record.
- `07-final-report/release-manifest.json` exists and records `PASS` for the
  exact final artifact hashes.

If release cannot pass, report `BLOCKED`, name the failing control and artifact,
and leave the run resumable. Never substitute a progress summary for release
acceptance.

## Useful commands

```bash
python3 -m research_control status
python3 -m research_control next
python3 -m research_control check --phase PHASE
python3 -m research_control task fail TASK_ID --reason "REASON"
python3 -m research_control capture --url URL --source-id ID --grade P
python3 -m research_control render
python3 -m research_control release
python3 -m unittest discover -s research_control/tests -v
```

The control CLI has no required third-party Python packages. It uses a local
CSS-capable PDF renderer and PDF rasterizer when available, with deterministic
fallbacks. External browsing, transcription, and final visual inspection remain
the responsibility of the supported coding-agent environment.
