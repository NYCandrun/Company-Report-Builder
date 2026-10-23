# Failure registry

This registry makes the production failures implicit in the authoritative
`README.md` explicit. Each invariant keeps a stable ID. A test marked
"semantic" is intentionally enforced by an independent model review because a
deterministic checker cannot establish meaning.

## F001 — Claimed success without output

- **Observed or anticipated failure:** A worker reports success, but an expected file is absent or invalid.
- **What goes wrong:** Downstream work trusts prose instead of on-disk evidence.
- **Invariant:** A task succeeds only after all declared outputs exist, pass required checks, and have recorded hashes.
- **Current source:** README 8.2 and 19.2.
- **Enforcement:** Worker schema, ledger validation, reconciliation, phase gate.
- **Regression test:** `test_worker_success_without_output_is_rejected`.
- **Notes:** Agent messages are never execution evidence.

## F002 — Assigned input silently disappears

- **Observed or anticipated failure:** An item in an immutable work slice has no output or disposition.
- **What goes wrong:** Coverage appears complete while records are missing.
- **Invariant:** Every assigned ID has exactly one terminal disposition.
- **Current source:** README 8.2, 8.5, and 19.3.
- **Enforcement:** Disposition schema and input-to-output reconciliation.
- **Regression test:** `test_missing_disposition_fails_reconciliation`.
- **Notes:** `completed_zero` is explicit and distinct from silence.

## F003 — Exclusive assignments overlap

- **Observed or anticipated failure:** Two workers process the same exclusive slice or ID.
- **What goes wrong:** Duplicates, conflicting edits, and misleading completion counts result.
- **Invariant:** Exclusive assignment IDs occur in only one active task.
- **Current source:** README 8.2, 8.7, 19.3, and 19.8.
- **Enforcement:** Ledger validator and assignment reconciliation.
- **Regression test:** `test_overlapping_exclusive_assignments_fail`.
- **Notes:** Explicit one-to-many output contracts remain allowed.

## F004 — Workers corrupt shared state

- **Observed or anticipated failure:** Parallel workers edit the ledger, manifest, workflow state, or another worker's files.
- **What goes wrong:** Lost updates and nondeterministic merges invalidate the run.
- **Invariant:** Shared state has one owner and worker output paths do not overlap.
- **Current source:** README -1 Shared-state ownership and 8.7.
- **Enforcement:** Runtime prompt, assignment contract, output-overlap validator.
- **Regression test:** `test_overlapping_output_paths_fail`.
- **Notes:** Some ownership violations also require repository review.

## F005 — Bounded work list is only partly processed

- **Observed or anticipated failure:** A worker stops early while returning a plausible summary.
- **What goes wrong:** Partial work is treated as full-batch completion.
- **Invariant:** Assigned, checked, and disposition counts reconcile exactly.
- **Current source:** README 8.2, 8.5, 19.3, and 19.4.
- **Enforcement:** Expected-versus-checked counts and reconciliation.
- **Regression test:** `test_checked_count_below_expected_is_unknown`.
- **Notes:** Fail closed as `UNKNOWN`, not `PASS`.

## F006 — Zero facts masquerade as processing

- **Observed or anticipated failure:** A source yields no facts and is assumed never to have been skipped.
- **What goes wrong:** No evidence proves that the source was read.
- **Invariant:** Zero-result processing has an explicit `completed_zero` disposition and evidence path.
- **Current source:** README 19.3.
- **Enforcement:** Disposition schema and extraction reconciliation.
- **Regression test:** `test_zero_results_require_explicit_disposition`.
- **Notes:** A zero count alone is insufficient.

## F007 — Citation does not support the exact claim

- **Observed or anticipated failure:** A real citation sits after wording that exceeds its receipt.
- **What goes wrong:** Readers infer evidence for a stronger claim than the source provides.
- **Invariant:** Each citation supports the exact adjacent reader-facing words.
- **Current source:** README 4.7, 15.3, and 16.2.
- **Enforcement:** Citation structure validator plus independent claim review.
- **Regression test:** Semantic planted claim/citation fixture in citation-review prompt tests.
- **Notes:** Meaning cannot be proven by code alone.

## F008 — Correct source paired with the wrong statement

- **Observed or anticipated failure:** Facts behind two citations are swapped or mapped to the wrong phrase.
- **What goes wrong:** Both sources exist, so shallow link checks pass.
- **Invariant:** Fact-to-phrase placement remains traceable from Markdown through rendered output.
- **Current source:** README 15.4, 16.1, and 16.5.
- **Enforcement:** Citation map and exhibit mapping checks plus semantic review.
- **Regression test:** `test_swapped_citation_facts_are_rejected`.
- **Notes:** The semantic half remains independently reviewed.

## F009 — Publication date is inferred incorrectly

- **Observed or anticipated failure:** Modified, upload, deploy, or clone time is used as publication date.
- **What goes wrong:** Timelines and currency conclusions become false.
- **Invariant:** Published and modified dates remain separate and follow the evidence hierarchy.
- **Current source:** README 4.9 and 10.12.
- **Enforcement:** Date schema, date validator, and currency review.
- **Regression test:** `test_modified_date_cannot_fill_published_without_method`.
- **Notes:** Ambiguous platform dates remain model-reviewed.

## F010 — Aims are described as shipped capabilities

- **Observed or anticipated failure:** Plans, aims, beta, or future tense become current product claims.
- **What goes wrong:** The brief overstates product reality.
- **Invariant:** Aspirations and shipped capabilities stay separate.
- **Current source:** README 4.7, 11.7, 13.4, and 14.
- **Enforcement:** Overstatement flags and technical/claim semantic review.
- **Regression test:** Planted overstated-claim fixture plus semantic review case.
- **Notes:** Keyword flags find candidates but cannot decide meaning.

## F011 — Human-delivered work becomes product capability

- **Observed or anticipated failure:** Managed services or employee work is attributed to software.
- **What goes wrong:** Product architecture and competitive comparisons are misleading.
- **Invariant:** Product capability and staff-delivered service remain distinct.
- **Current source:** README 14 Reviewer 1.
- **Enforcement:** Independent technical product-marketer review.
- **Regression test:** Semantic service-versus-product review fixture.
- **Notes:** Model judgment is required.

## F012 — Strategic inference is presented as fact

- **Observed or anticipated failure:** Directional interpretation loses its inference label and supporting IDs.
- **What goes wrong:** Speculation appears sourced.
- **Invariant:** Every inference starts with `My inference:` and names its factual basis.
- **Current source:** README 4.5, 13.2, and 14 Reviewer 2.
- **Enforcement:** Deterministic prefix/reference check and devil's-advocate review.
- **Regression test:** `test_inference_without_label_or_fact_ids_fails`.
- **Notes:** Whether the inference follows remains semantic.

## F013 — Old evidence is presented as current

- **Observed or anticipated failure:** Stale plans, titles, prices, or features are stated in the present tense.
- **What goes wrong:** Fast-changing company details mislead the reader.
- **Invariant:** Currency labels follow evidence age, current pages, and supersession review.
- **Current source:** README 6 and 13.3.
- **Enforcement:** Date/currency validator and flagged-row semantic review.
- **Regression test:** `test_stale_current_claim_is_flagged`.
- **Notes:** Absence from a current page is not deterministic proof of retirement.

## F014 — Artifact changes after validation

- **Observed or anticipated failure:** An input or final deliverable is edited after its check passes.
- **What goes wrong:** A stale pass is accepted for different bytes.
- **Invariant:** Check reports bind checker version and exact input hashes.
- **Current source:** README 19.4 through 19.7.
- **Enforcement:** Artifact hashing, gate staleness, and release acceptance.
- **Regression test:** `test_changed_artifact_invalidates_gate_and_release`.
- **Notes:** Incremental reruns are valid only for declared affected inputs.

## F015 — Validation never ran but is treated as passing

- **Observed or anticipated failure:** Missing, crashed, timed-out, or malformed validation is read as success.
- **What goes wrong:** Absence of evidence becomes evidence of absence.
- **Invariant:** Missing or incomplete execution is `UNKNOWN`, and `UNKNOWN` blocks.
- **Current source:** README 19.4.
- **Enforcement:** Validation schema and fail-closed gates.
- **Regression test:** `test_missing_validation_is_unknown_and_blocks`.
- **Notes:** An empty report is not a pass.

## F016 — Validator checks fewer records than expected

- **Observed or anticipated failure:** A checker reports zero flags over a truncated input set.
- **What goes wrong:** False confidence survives because issue count alone looks clean.
- **Invariant:** Expected and checked counts must match or have explicit dispositions.
- **Current source:** README 19.4 and 19.8.
- **Enforcement:** Validation report schema and gate evaluator.
- **Regression test:** `test_short_validator_run_cannot_pass`.
- **Notes:** Status becomes `UNKNOWN` when accounting is incomplete.

## F017 — Required reviewer reviews their own work

- **Observed or anticipated failure:** Writing and verification or synthesis and challenge share one context.
- **What goes wrong:** Anchoring and confirmation bias weaken the check.
- **Invariant:** Roles marked independent have distinct worker/task identities and contexts.
- **Current source:** README -1 Model use, 8.4, 14, and 16.2.
- **Enforcement:** Workflow contracts, ledger identities, and review reconciliation.
- **Regression test:** `test_required_independent_roles_cannot_share_task`.
- **Notes:** The same underlying model may be used in separate contexts.

## F018 — Visual review silently skips pages

- **Observed or anticipated failure:** A reviewer samples pages or omits clean-page records.
- **What goes wrong:** Layout defects in unreviewed pages survive.
- **Invariant:** Every rendered PDF page has exactly one visual-review record.
- **Current source:** README 16.7 and 19.3.
- **Enforcement:** Page-to-review reconciliation and final gate.
- **Regression test:** `test_missing_visual_page_record_blocks_final`.
- **Notes:** Readability and professionalism remain visual/model judgments.

## F019 — Released artifact differs from checked artifact

- **Observed or anticipated failure:** A similarly named or later-rendered file is shipped.
- **What goes wrong:** Validation applies to a non-released version.
- **Invariant:** Release manifest hashes exactly match all validated deliverables.
- **Current source:** README 19.6 and 19.7.
- **Enforcement:** Release checker and immutable hash manifest.
- **Regression test:** `test_release_rejects_unbound_final_artifact`.
- **Notes:** The release manifest does not hash itself.

## F020 — Duplicate IDs corrupt referential integrity

- **Observed or anticipated failure:** Source IDs, fact IDs, task IDs, or worker IDs collide.
- **What goes wrong:** Receipts and dispositions resolve ambiguously.
- **Invariant:** IDs are unique within their declared namespace.
- **Current source:** README 10.12, 11.7, and 19.1.
- **Enforcement:** Schema and uniqueness validators.
- **Regression test:** `test_duplicate_ids_fail_validation`.
- **Notes:** Stable IDs are retained through retries.

## F021 — Manifest points to a missing local source

- **Observed or anticipated failure:** A manifest row exists without its captured file.
- **What goes wrong:** Facts cannot be reproduced or verified.
- **Invariant:** Every used source resolves to an existing local file unless explicitly blocked.
- **Current source:** README 4.2, 10.12, and 17.
- **Enforcement:** Source validator and capture gate.
- **Regression test:** `test_manifest_missing_file_fails_capture`.
- **Notes:** Public URL availability does not replace the local receipt.

## F022 — Date backfill overwrites stronger evidence

- **Observed or anticipated failure:** A weak inferred date replaces a known published date.
- **What goes wrong:** Later automation degrades evidence quality.
- **Invariant:** Date overlays never overwrite a stronger existing date.
- **Current source:** README 10.12.
- **Enforcement:** Date precedence validator and merge tests.
- **Regression test:** `test_weaker_date_overlay_cannot_replace_stronger_date`.
- **Notes:** Strength is encoded as an explicit date method.

## F023 — Unreliable speaker labels become attribution

- **Observed or anticipated failure:** Auto-caption labels are treated as firm speaker identity.
- **What goes wrong:** A true statement is attributed to the wrong person or organization.
- **Invariant:** Named speakers require firm evidence; uncertain labels are marked probable or unclear.
- **Current source:** README 4.4 and 11.7.
- **Enforcement:** Speaker/tag validator and semantic verification.
- **Regression test:** `test_named_speaker_requires_attribution_evidence`.
- **Notes:** Ambiguous audio requires judgment.

## F024 — Caption parser drops one-word lines

- **Observed or anticipated failure:** Rolling captions remove isolated words.
- **What goes wrong:** Quotes become incomplete or change meaning.
- **Invariant:** Caption parsing preserves one-word caption lines.
- **Current source:** README 10.3 No captions.
- **Enforcement:** Parser regression fixture.
- **Regression test:** `test_one_word_caption_lines_are_preserved`.
- **Notes:** Kept as an evidence-pipeline test category.

## F025 — Duplicate content is extracted twice

- **Observed or anticipated failure:** Reuploads, clips, translations, or identical URLs produce duplicate facts.
- **What goes wrong:** Evidence volume and apparent corroboration are inflated.
- **Invariant:** One canonical source is selected while duplicates remain captured and disposed.
- **Current source:** README 10.3 and 11.1.
- **Enforcement:** Canonical-copy reconciliation and duplicate spot review.
- **Regression test:** `test_duplicate_source_requires_canonical_disposition`.
- **Notes:** Semantic similarity detection is reviewed when hashes differ.

## F026 — Filtering drops relevant evidence

- **Observed or anticipated failure:** Guest-led or unclear-speaker passages are filtered out before extraction.
- **What goes wrong:** Important facts disappear from the record.
- **Invariant:** Filters fail open for unclear speakers and sampled miss rate cannot exceed 5 percent without a second pass.
- **Current source:** README 11.2 and 11.3.
- **Enforcement:** Filter configuration, sampling report, and facts gate.
- **Regression test:** `test_filter_miss_rate_requires_second_pass`.
- **Notes:** The 40-passage assessment remains semantic.

## F027 — Quote is absent at the claimed location

- **Observed or anticipated failure:** Text exists somewhere in a source but not at the recorded receipt.
- **What goes wrong:** Context and attribution can be wrong.
- **Invariant:** Verbatim quote and exact location resolve together.
- **Current source:** README 4.2, 11.6, and 11.7.
- **Enforcement:** Quote/location validator and verification packet.
- **Regression test:** `test_wrong_quote_and_wrong_location_are_rejected`.
- **Notes:** Semantic sufficiency is checked separately.

## F028 — A path or vague label is used as a receipt

- **Observed or anticipated failure:** `website`, `many pages`, or a file path stands in for source ID and location.
- **What goes wrong:** Evidence is neither resolvable nor auditable.
- **Invariant:** Every fact uses a manifest source ID and exact source location.
- **Current source:** README 4.2.
- **Enforcement:** Fact schema and receipt validator.
- **Regression test:** `test_vague_source_receipts_fail`.
- **Notes:** Deterministic.

## F029 — Incomplete search becomes an absolute absence claim

- **Observed or anticipated failure:** Limited coverage supports a universal negative.
- **What goes wrong:** The brief overstates what was not found.
- **Invariant:** Absence claims name the searched source set.
- **Current source:** README 4.6.
- **Enforcement:** Writing validator candidate flag and semantic claim review.
- **Regression test:** Semantic scoped-absence fixture.
- **Notes:** Coverage scope must be interpreted.

## F030 — Source grade is misclassified

- **Observed or anticipated failure:** Company-hosted customer stories, reprints, or internal inputs receive the wrong grade.
- **What goes wrong:** Evidence quality is overstated and counts are misleading.
- **Invariant:** Grades follow authorship and first-hand status, not superficial hosting labels.
- **Current source:** README 4.1 and 10.8.
- **Enforcement:** Source schema plus semantic source-grade audit.
- **Regression test:** Source-grade decision fixtures.
- **Notes:** Some publisher relationships need judgment.

## F031 — Internal material leaks into an external brief

- **Observed or anticipated failure:** Grade-I quotes or claims remain in a shareable artifact.
- **What goes wrong:** Private information is disclosed.
- **Invariant:** Grade-I material is never quoted externally and is removed unless explicitly authorized.
- **Current source:** README 2.2, 15.3, and 15.11.
- **Enforcement:** Publication validator and final semantic review.
- **Regression test:** `test_grade_i_content_is_rejected_for_external_release`.
- **Notes:** Authorization is an explicit release exception.

## F032 — Model merging corrupts the fact store

- **Observed or anticipated failure:** A model manually merges tables or reallocates IDs.
- **What goes wrong:** Rows disappear, duplicate, or lose stable references.
- **Invariant:** Filing and merging are deterministic script operations.
- **Current source:** README 11.7.
- **Enforcement:** Runtime prompt and filing reconciliation.
- **Regression test:** `test_candidate_to_fact_reconciliation_is_complete`.
- **Notes:** Models may make semantic duplicate decisions before scripted filing.

## F033 — Conflicting facts are silently harmonized

- **Observed or anticipated failure:** Disagreeing prices, dates, limits, or titles collapse into one value.
- **What goes wrong:** Uncertainty and chronology disappear.
- **Invariant:** Conflicts remain visible with both sources and dates.
- **Current source:** README 6, 11.7, 13.2, and 17.
- **Enforcement:** Conflict detector and synthesis/release review.
- **Regression test:** `test_conflicting_values_are_flagged_not_overwritten`.
- **Notes:** Equivalent numerical phrasing is normalized before flagging.

## F034 — Candidate fact disappears during filing

- **Observed or anticipated failure:** Candidate rows are dropped without duplicate or rejection evidence.
- **What goes wrong:** Extraction completeness cannot be proven.
- **Invariant:** Every candidate fact has a filed, duplicate, or rejected disposition.
- **Current source:** README 11.7 and 19.3.
- **Enforcement:** Fact filing reconciliation.
- **Regression test:** `test_candidate_without_filing_disposition_fails`.
- **Notes:** Rejected rows retain reasons.

## F035 — Review finding receives no decision

- **Observed or anticipated failure:** Review reports exist but findings are ignored.
- **What goes wrong:** Review becomes performative rather than corrective.
- **Invariant:** Every finding is applied, partly applied, or rejected with a reason.
- **Current source:** README 14 Fixers and 19.3.
- **Enforcement:** Review-finding schema and review reconciliation.
- **Regression test:** `test_undisposed_review_finding_blocks_review_gate`.
- **Notes:** Mandatory open fixes must be zero.

## F036 — Accepted fix is not applied

- **Observed or anticipated failure:** A decision says "apply" but the artifact is unchanged.
- **What goes wrong:** Decision accounting passes while the defect survives.
- **Invariant:** Applied decisions name evidence paths and current artifact hashes.
- **Current source:** README 14 and 19.5.
- **Enforcement:** Review reconciliation and review gate hash inputs.
- **Regression test:** `test_applied_finding_requires_evidence_path`.
- **Notes:** Some semantic changes still require spot inspection.

## F037 — Newly cited fact bypasses verification

- **Observed or anticipated failure:** Phase 6 adds a fact after the first cited-fact verification pass.
- **What goes wrong:** The final brief cites only script-checked evidence.
- **Invariant:** Every final cited fact has a final model-verification verdict.
- **Current source:** README 12, 15.4, and 19.5.
- **Enforcement:** Citation-to-verification reconciliation and final gate.
- **Regression test:** `test_new_unverified_citation_blocks_final`.
- **Notes:** User-provided exceptions follow the explicit user-provided verdict contract.

## F038 — Corrected fact is not propagated

- **Observed or anticipated failure:** A fact changes but dependent synthesis sentences stay unchanged.
- **What goes wrong:** Verified data and reader-facing copy diverge.
- **Invariant:** Material corrections trigger dependent-copy updates and layer-1 rechecks.
- **Current source:** README 12 and 19.5.
- **Enforcement:** Verification reconciliation and stale-input hashes.
- **Regression test:** `test_fact_correction_stales_dependent_verification_gate`.
- **Notes:** Whether a correction is material is semantic.

## F039 — One source receives multiple citation numbers

- **Observed or anticipated failure:** Citation numbering duplicates a source.
- **What goes wrong:** Source notes and reading-order counts become inconsistent.
- **Invariant:** Each source has one number per artifact, reused after first occurrence.
- **Current source:** README 15.3 and 16.1.
- **Enforcement:** Citation validator.
- **Regression test:** `test_duplicate_source_number_is_caught`.
- **Notes:** The company brief has one reading-order sequence; diagrams use stable model-to-evidence bindings instead of a second citation-number sequence.

## F040 — Citation note is missing, unused, or incomplete

- **Observed or anticipated failure:** A superscript lacks a note, a note is unused, or a multi-source count omits inputs.
- **What goes wrong:** Reader-visible references do not account for evidence.
- **Invariant:** Numbers, notes, cited facts, and underlying sources reconcile bijectively where specified.
- **Current source:** README 15.3, 16.1, and 17.
- **Enforcement:** Citation reconciliation.
- **Regression test:** `test_missing_note_and_removed_source_are_caught`.
- **Notes:** Script-count notes may intentionally list several sources.

## F041 — Exhibit uses pooled citations

- **Observed or anticipated failure:** A diagram or table receives a generic list of facts.
- **What goes wrong:** Individual labels and cells appear supported without phrase-level evidence.
- **Invariant:** Exhibit facts map per group, box, part, phrase, or cell.
- **Current source:** README 15.3 and 15.4.
- **Enforcement:** Exhibit schema and mapping validator.
- **Regression test:** `test_exhibit_requires_element_level_fact_mapping`.
- **Notes:** Phrase support also receives semantic citation review.

## F042 — Repository internals leak to readers

- **Observed or anticipated failure:** Fact IDs, paths, script names, warnings, or build instructions appear in HTML/PDF.
- **What goes wrong:** The deliverable is confusing or exposes internal mechanics.
- **Invariant:** Reader-facing artifacts contain no prohibited internal tokens.
- **Current source:** README 15.3 and 15.7.
- **Enforcement:** Publication text validator and visual review.
- **Regression test:** `test_reader_facing_internal_tokens_are_rejected`.
- **Notes:** Methodology is translated into plain language.

## F043 — Deep link points to the wrong or changed content

- **Observed or anticipated failure:** A citation number links to a wrong page or stale text fragment.
- **What goes wrong:** The source is real but the reader cannot reach supporting text.
- **Invariant:** Deep links derive from the first cited fact, validate against capture, and fall back safely.
- **Current source:** README 15.3 and 16.1.
- **Enforcement:** Citation link validator and optional live check.
- **Regression test:** `test_wrong_page_and_missing_text_fragment_are_caught`.
- **Notes:** Live-page change does not invalidate the captured receipt.

## F044 — Design edits break citation placement

- **Observed or anticipated failure:** Reformatting separates a citation from its supported words.
- **What goes wrong:** Research Markdown remains right while published output is wrong.
- **Invariant:** Final HTML citation placement maps back to the pre-design reference.
- **Current source:** README 15.4 and 16.3.
- **Enforcement:** Pre-design hash, citation map, exhibit map, and claim review.
- **Regression test:** `test_html_placement_must_match_markdown_context`.
- **Notes:** Semantic review remains the final publication-integrity layer.

## F045 — Layout overflow passes unnoticed

- **Observed or anticipated failure:** Text, labels, or superscripts cross borders or crowd padding.
- **What goes wrong:** Correct content is unreadable or unprofessional.
- **Invariant:** Measurable overflow is zero and visual-review fixes are closed.
- **Current source:** README 15.1 and 16.6 through 16.8.
- **Enforcement:** Visual-record validator, automated audit, and full-page review.
- **Regression test:** `test_visual_validation_requires_expected_page_count`.
- **Notes:** A deterministic box test cannot judge all design quality.

## F046 — Targeted edit changes unrelated pages

- **Observed or anticipated failure:** A small copy request causes page-flow or citation churn elsewhere.
- **What goes wrong:** Unrequested content changes escape notice.
- **Invariant:** Targeted edits compare page text before/after and inspect every changed page.
- **Current source:** README 15.12.
- **Enforcement:** Build workflow contract and changed-page reconciliation.
- **Regression test:** Planned release-integrity fixture for unexpected page changes.
- **Notes:** Some layout movement is allowed when explicitly reported and repaired.

## F047 — Access restriction is bypassed

- **Observed or anticipated failure:** A worker routes around robots, bot challenges, logins, or paywalls.
- **What goes wrong:** Research violates the public-access boundary.
- **Invariant:** Failed restricted access is logged, never bypassed.
- **Current source:** README 3 and 4.10.
- **Enforcement:** Capture prompt, blocked disposition, and coverage report.
- **Regression test:** Semantic capture-policy fixture.
- **Notes:** Network behavior cannot be reconstructed completely after the fact.

## F048 — Repeated fetching worsens rate limits

- **Observed or anticipated failure:** Parallel workers hammer one host or retry indefinitely.
- **What goes wrong:** More sources become unavailable and runtime is wasted.
- **Invariant:** Same-host pacing is coordinated and retries are targeted and bounded.
- **Current source:** README 4.10, 8.2, 10.3, and 19.10.
- **Enforcement:** Workflow retry policy and runtime prompt.
- **Regression test:** `test_retry_policy_has_finite_attempt_limit`.
- **Notes:** Host-specific pacing remains operator-configurable.

## F049 — Downstream phase starts before prerequisites pass

- **Observed or anticipated failure:** Assertions in state files substitute for gates.
- **What goes wrong:** Invalid artifacts contaminate later phases.
- **Invariant:** Dependent work begins only after its required executable gate returns `PASS`.
- **Current source:** README 8.1 and 19.5.
- **Enforcement:** Workflow dependency graph and phase-gate checker.
- **Regression test:** `test_dependency_gate_must_pass_before_phase`.
- **Notes:** Independent preparation may continue.

## F050 — Gate result becomes stale

- **Observed or anticipated failure:** Relevant source, fact, review, template, or output changes after a gate.
- **What goes wrong:** A historical pass is treated as current.
- **Invariant:** Gate input hashes must still match current artifacts.
- **Current source:** README 19.5 through 19.7.
- **Enforcement:** Gate report hashes and staleness evaluator.
- **Regression test:** `test_gate_staleness_detects_changed_input`.
- **Notes:** Checker version changes also invalidate cached results.

## F051 — Retry erases failed attempt history

- **Observed or anticipated failure:** A successful retry overwrites evidence of the earlier failure.
- **What goes wrong:** Reliability and unresolved patterns are hidden.
- **Invariant:** Attempt numbers are append-only and every attempt remains in the ledger.
- **Current source:** README 19.2 and 19.10.
- **Enforcement:** Ledger schema and transition validator.
- **Regression test:** `test_retry_attempts_are_append_only`.
- **Notes:** Task identity stays stable across attempts.

## F052 — Retry needlessly reprocesses validated work

- **Observed or anticipated failure:** One failed slice causes a full batch rerun.
- **What goes wrong:** Token and compute costs grow and duplicate outputs appear.
- **Invariant:** Retry only failed or unaccounted slices while preserving validated outputs.
- **Current source:** README 8.8 and 19.10.
- **Enforcement:** Retry policy and reconciliation report.
- **Regression test:** `test_retry_scope_is_subset_of_failed_inputs`.
- **Notes:** Complete reconciliation still runs before release.

## F053 — Run depends on undeclared prior artifacts

- **Observed or anticipated failure:** A script, template, or environment convention happens to exist locally.
- **What goes wrong:** A fresh repository cannot reproduce the work.
- **Invariant:** Every dependency is supplied, created, or declared during the run.
- **Current source:** README introduction and -1 Tool bootstrap.
- **Enforcement:** Bootstrap contract, CI, and dependency declarations.
- **Regression test:** CI runs control tests from a clean checkout.
- **Notes:** External capture tools may have documented substitutes.

## F054 — Proprietary fonts are redistributed

- **Observed or anticipated failure:** Website-served brand fonts are scraped and embedded without permission.
- **What goes wrong:** The final artifact creates a licensing issue.
- **Invariant:** Fonts are embedded only when legally permitted and availability/substitutions are documented.
- **Current source:** README -1 Design bootstrap, 15.1, and 15.11.
- **Enforcement:** Design prompt and release checklist.
- **Regression test:** Semantic licensing checklist fixture.
- **Notes:** Legal availability is not derivable from file presence.

## F055 — A cited captured file is renamed

- **Observed or anticipated failure:** Cleanup changes a stable path after facts reference it.
- **What goes wrong:** Locations and reproducibility break.
- **Invariant:** Once named and cited, captured files retain their name.
- **Current source:** README 7 File naming.
- **Enforcement:** Manifest-to-file validation and Git diff review.
- **Regression test:** Planned manifest-history fixture.
- **Notes:** Renames require an explicit migration, never silent cleanup.

## F056 — Modified date is confused with publication date

- **Observed or anticipated failure:** Current metadata or redirects create a false event chronology.
- **What goes wrong:** Messaging and launch timelines are misdated.
- **Invariant:** Published and last-modified fields are distinct, with method evidence.
- **Current source:** README 4.9.
- **Enforcement:** Source/date schemas and date validator.
- **Regression test:** `test_published_and_modified_dates_remain_distinct`.
- **Notes:** This narrows F009 to storage semantics.

## F057 — Third-party price is stated as current company price

- **Observed or anticipated failure:** Analyst or review-site pricing becomes an unqualified current dollar amount.
- **What goes wrong:** Buyers receive unsupported pricing guidance.
- **Invariant:** A current company dollar price requires a company-published source.
- **Current source:** README 6 Currency review.
- **Enforcement:** Fact tag/date validator and semantic currency review.
- **Regression test:** Semantic third-party-pricing fixture.
- **Notes:** Conflicts are stated, not resolved by source count.

## F058 — Redirect is treated as retirement

- **Observed or anticipated failure:** A changed URL proves a product was removed.
- **What goes wrong:** Current offerings are mislabeled retired.
- **Invariant:** Redirects are page changes, not retirement proof.
- **Current source:** README 6 Currency review.
- **Enforcement:** Flagged-row semantic currency review.
- **Regression test:** Semantic redirect-versus-retirement fixture.
- **Notes:** Code may flag redirects but cannot infer product status.

## F059 — Evidence asymmetry biases competitor judgment

- **Observed or anticipated failure:** The focal company appears ahead because it has more captured evidence.
- **What goes wrong:** Scoring confuses evidence volume with capability.
- **Invariant:** Competitive synthesis discloses material evidence asymmetry and keeps judgments inferential.
- **Current source:** README 13.2 Competitors.
- **Enforcement:** Competitor synthesis and skeptical review prompts.
- **Regression test:** Semantic competitor-asymmetry review fixture.
- **Notes:** Deterministic counts inform but do not solve this bias.

## F060 — Section numbering changes actual phase order

- **Observed or anticipated failure:** "Phase 3" verification is run before initial synthesis because it appears first numerically.
- **What goes wrong:** Cited-fact targeting cannot work and review dependencies change.
- **Invariant:** Execution remains capture, facts, initial synthesis, cited-fact verification, corrected synthesis, review, brief, publication checks, release.
- **Current source:** README 8.1, 12, and 19.5.
- **Enforcement:** Canonical `WORKFLOW.yaml` dependency graph.
- **Regression test:** `test_effective_phase_dependency_order_is_preserved`.
- **Notes:** Labels may improve; dependencies may not change.

## F061 — Independent roles are combined for batching convenience

- **Observed or anticipated failure:** One worker both writes and verifies or synthesizes and challenges.
- **What goes wrong:** Required independence is lost to efficiency.
- **Invariant:** Batching never combines roles requiring independent judgment.
- **Current source:** README 8.4.
- **Enforcement:** Workflow role constraints and ledger identity check.
- **Regression test:** `test_incompatible_roles_cannot_share_assignment`.
- **Notes:** Related non-independent deliverables may still be grouped within size limits.

## F062 — Parallel workers append to one shared manifest

- **Observed or anticipated failure:** Concurrent appends interleave, duplicate, or truncate rows.
- **What goes wrong:** Source state becomes nondeterministic.
- **Invariant:** Workers write parts; a single owner merges shared files deterministically.
- **Current source:** README 8.7 and 10.
- **Enforcement:** Runtime contract, path-overlap check, merge reconciliation.
- **Regression test:** `test_shared_manifest_is_not_a_worker_output`.
- **Notes:** Applies equally to shared review files.

## F063 — Worker assignment is unbounded or ambiguous

- **Observed or anticipated failure:** A launch uses placeholders, unknown slice size, or no exact output path.
- **What goes wrong:** Completion cannot be measured and files collide.
- **Invariant:** Every assignment has immutable IDs, exact paths, validators, and checked size.
- **Current source:** README 8.2, 8.3, and 19.2.
- **Enforcement:** Worker schema and ledger registration.
- **Regression test:** `test_worker_assignment_requires_bounded_inputs_and_outputs`.
- **Notes:** Large lists are referenced by digest, not pasted into prompts.

## F064 — Fault injection damages the real corpus

- **Observed or anticipated failure:** A planted error is introduced into live research files.
- **What goes wrong:** Tests contaminate the artifacts they are meant to protect.
- **Invariant:** Negative tests operate only on disposable fixtures or copies.
- **Current source:** README 16.5 and 19.8.
- **Enforcement:** Test harness temporary-directory contract.
- **Regression test:** `test_negative_tests_leave_source_fixture_unchanged`.
- **Notes:** Real files must still pass after fault injection tests.

## F065 — Published count lacks reproducible inputs

- **Observed or anticipated failure:** A narrative count cannot be rerun or traced.
- **What goes wrong:** Reader-facing quantities drift from the corpus.
- **Invariant:** Every published count has a deterministic script, saved output, and declared inputs.
- **Current source:** README 4.8 and 17.
- **Enforcement:** Count validation record and release checklist.
- **Regression test:** `test_published_count_requires_output_and_input_hashes`.
- **Notes:** Script-derived observations may use a special multi-source citation note.

## F066 — Provided research report becomes final evidence

- **Observed or anticipated failure:** A compilation substitutes for the underlying source.
- **What goes wrong:** Claims inherit unknown transformations and weaker receipts.
- **Invariant:** Provided reports are scoping leads; capturable P/S receipts support final facts.
- **Current source:** README 2.2 Provided research reports.
- **Enforcement:** Input/capture prompt and source-grade review.
- **Regression test:** Semantic provided-report receipt fixture.
- **Notes:** The report remains citable only where it is itself the relevant claim source.

## F067 — Empty check output is read as zero failures

- **Observed or anticipated failure:** A checker exits or emits an empty file that looks clean.
- **What goes wrong:** Corrupt reports satisfy existence-only gates.
- **Invariant:** Validation reports conform to schema and contain status, counts, checker identity, hashes, and time.
- **Current source:** README 19.4.
- **Enforcement:** Validation schema and report loader.
- **Regression test:** `test_empty_validation_report_is_unknown`.
- **Notes:** Malformed JSON also becomes `UNKNOWN`.

## F068 — Release exception silently weakens evidence rules

- **Observed or anticipated failure:** A blocked or incomplete channel is accepted without disclosure.
- **What goes wrong:** Release passes by hiding coverage limitations.
- **Invariant:** Exceptions are explicit, justified, and consistent with blocked-source and evidence-limit rules.
- **Current source:** README 15.2, 19.6, and 19.7.
- **Enforcement:** Release schema and acceptance checker.
- **Regression test:** `test_exception_requires_reason_and_evidence_path`.
- **Notes:** Exceptions cannot override failed required controls.

## F069 — Brand styling becomes architecture evidence

- **Observed or anticipated failure:** A visual specimen, color grouping, or nearby label in the brand guide creates a product, boundary, or relationship in a diagram.
- **What goes wrong:** Presentation silently changes the validated information model.
- **Invariant:** The brand guide supplies presentation only; diagram facts come only from the validated model registry.
- **Current source:** RESEARCH_CONSTITUTION.md Visual integrity; prompts/phases/diagram-building.md.
- **Enforcement:** Task-specific inputs, model validation, stable SVG entity/relationship IDs, and diagram-style-spec review.
- **Regression test:** `test_valid_models_and_editable_svgs_pass` plus operational packet separation.
- **Notes:** Designed visual extensions are allowed only when labeled and do not alter model semantics.

## F070 — Brand-guide work serializes the research run

- **Observed or anticipated failure:** Brand research waits for company research or becomes a new blocking phase at the end.
- **What goes wrong:** The added output materially lengthens wall-clock runtime without needing factual synthesis.
- **Invariant:** One independent brand-guide packet starts with capture and runs alongside discovery and source capture.
- **Current source:** README Adaptive planning and scheduling; WORKFLOW.yaml capture profile.
- **Enforcement:** Adaptive planner priority and independent task metadata.
- **Regression test:** `test_task_count_follows_discovered_corpus_and_content_volume`.
- **Notes:** The capture gate still waits if the brand branch is genuinely the slower required output.
