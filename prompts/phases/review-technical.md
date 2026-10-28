TASK TYPE: INDEPENDENT TECHNICAL PRODUCT REVIEW

Read only assigned synthesis files and bounded packets for facts they cite.
Review concepts, not merely quote existence. Check every diagram and every
relationship such as `X is part of Y`, `X runs on Y`, or `X leads to Y`. Check
that human-delivered services are not described as software capabilities.

Write one structured finding per problem with severity, artifact location,
factual basis, proposed fix, and stable finding ID in both the assigned
Markdown report and JSONL findings file. Do not edit synthesis. If the full
assignment yields no findings, write a JSONL completion record with
`status: clean` rather than leaving the file empty.

`06-checks/relationship-consistency.md` lists organizations whose client
relationship is marked differently in different synthesis files (found by
script). Treat each as already found: settle it by the evidence rather than
reporting the difference again.

Write in American English, in spelling and in vocabulary ("program", not "programme"; "job posting", not
"job advert"; "the company is", not "the company are"). Quotes, quoted titles, and names keep the
source's spelling. `work check` lists anything British in what you wrote, and `work succeed` refuses it.
