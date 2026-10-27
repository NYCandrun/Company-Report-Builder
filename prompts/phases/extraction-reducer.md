# TASK TYPE: EXTRACTION REDUCER

The runtime executes this deterministic task itself inside `python3 -m research_control run`; it is not dispatched to an agent. This text documents the contract it enforces.

Act as the single writer for canonical candidate and extraction-disposition
stores. Do not create, remove, or reinterpret research claims.

Run:

```bash
python3 -m research_control reduce extraction
```

The reducer concatenates only assigned worker parts and must reject duplicate
candidate IDs, malformed dispositions, duplicate assignment/input pairs, or
missing parts. Preserve valid zero-fact dispositions.
