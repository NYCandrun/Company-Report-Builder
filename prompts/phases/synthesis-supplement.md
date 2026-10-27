TASK TYPE: SYNTHESIS SUPPLEMENT, RECONCILING NEW FACTS WITH ONE SYNTHESIS FILE

Some sources were recaptured, or extracted again for questions added later,
after synthesis was written. Their earlier facts stand. New facts were
appended to the fact store. Your packet names one synthesis file and its
digest (`tools/digests/supplement/<file>.md`): one line per new fact for that
file, with its ID, source date, grade, source ID, claim, and delivery status
and relationship basis where the fact has them.

Read the evidence, writing, and runtime cores, your digest, and your synthesis
file. Do not read the fact store whole: open a fact's full row (quote,
location, notes) only for a fact you are about to cite, by searching
`02-facts/` for its ID.

For each digest line decide:

- it confirms a statement in your file: cite it beside the existing citation;
- it contradicts or narrows a statement (code that does less than its README
  says, a stub, a roadmap item presented as shipped, a deal that moved): revise
  the statement so both the claim and what the evidence shows are visible,
  citing both;
- it adds something your file lacks and its reader needs (what was built and
  delivered, an account's stages and timeline, land, expansion, or churn, a
  change over time): add it where it belongs;
- it adds nothing a reader of your file needs: leave it uncited.

Many facts make one point: cite the strongest few for it, not all of them.
Revise only the passages the facts affect; do not rewrite or restyle untouched
text. Keep the synthesis rules: every factual sentence cites fact IDs, aims stay
apart from shipped capabilities, relationship marks stay on every client, and
interpretations are labeled `My inference:`. Edit only your synthesis file.

Write your part file (the packet's `.jsonl` output): one JSON line for each
fact you cited or that changed text, `{"fact_id", "decision"` (`confirms`,
`narrows`, `contradicts`, or `adds`)`, "passage", "why"}`. Leave out the facts
you left uncited; the runtime records them in the reconciliation report. Run
the fact-ID and writing checks before return.
