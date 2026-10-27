TASK TYPE: REVIEW FIX APPLICATION, NOT NEW REVIEW

Read every assigned finding and the evidence relevant to it. Give each finding
exactly one disposition: `apply`, `apply_in_part`, or `reject`, with a reason.
Apply accepted changes only to assigned artifacts. Preserve quotes, IDs, dates,
and unrelated copy unless the finding specifically establishes an error.

Record decisions as JSONL in the assigned decision file and keep a readable
Markdown summary. Record evidence paths for applied changes. Run fact-ID and
writing validators. Return counts for all three dispositions, outstanding
mandatory fixes, changed paths, and validator status. A declared `apply`
without a changed/evidence path is incomplete.

Also apply source dating: a fact whose source date is missing, undated, or a
capture date standing in for a publication date takes the content date and
basis from `tools/outputs/source-dates.jsonl` when that table has one, and a
claim about the present that rests only on `dated` or `undated` evidence is
reworded with its date or narrowed.

A finding that only suggests capturing a new source is applied only when the
source would change a conclusion materially, and then in the lightest way (one
page, not a new research pass). Otherwise reject it with that reason; a
skipped suggestion is not reported as an open gap. A finding that two files
disagree is settled by the evidence: the stronger, more direct, or later-dated
source decides, and the change over time is shown where values differ by date.
