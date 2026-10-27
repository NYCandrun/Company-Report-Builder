TASK TYPE: SYNTHESIS SUPPLEMENT, RECONCILING NEW FACTS WITH EXISTING SYNTHESIS

Some sources were recaptured with more content after synthesis was written
(for example a repository's source code beside its README). Their earlier
facts stand. New facts from them were appended to the fact store and are
listed in `tools/lists/supplement-facts.txt`. Read the evidence, writing, and
runtime cores, every listed fact in `02-facts/`, and the synthesis files.

For each listed fact decide where it belongs:

- it confirms a synthesis statement: cite it beside the existing citation;
- it contradicts or narrows a statement (code that does less than its README
  says, a stub, a roadmap item presented as shipped): revise the statement so
  both the claim and what the evidence shows are visible, citing both;
- it adds something the synthesis lacks and a reader of that file needs:
  add it in the file where it belongs;
- it adds nothing a reader needs: leave it uncited.

Revise only the files and passages the listed facts affect; do not rewrite
others or restyle untouched text. Keep the synthesis rules: every factual
sentence cites fact IDs, aims stay apart from shipped capabilities, and
interpretations are labeled `My inference:`. Write
`06-checks/supplement-reconciliation.md` with one row per listed fact: the
decision, the file and passage changed, and why. Run the fact-ID and writing
checks before return.
