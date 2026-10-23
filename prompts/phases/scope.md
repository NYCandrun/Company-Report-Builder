TASK TYPE: SCOPE AND SOURCE-MAP WORK

Read the runtime and evidence cores, the company URL in the run state, and all
user-provided material in `00-inputs/`. Inspect the company homepage before
fixing scope.

Write `00-scope.md` with the company record, flagship and product boundaries,
research questions, first-party surfaces, people, careers, investor, press,
developer, media, third-party, and competitor source plans. Name likely
ambiguities and make a recommended decision unless the company's identity or
the requested subject is genuinely ambiguous.

Do not capture the full corpus yet. Do not omit an input. Account for every
provided input and state whether it is direction, a source, a prior report, or
design guidance. Write one terminal record per file to
`tools/outputs/input-classification.jsonl`, using its repository-relative path
as `input_id`. If `00-inputs/` is empty, write one `completed_zero` record for
`__none__` with `00-scope.md` as evidence. Finish with an explicit capture work
list.
