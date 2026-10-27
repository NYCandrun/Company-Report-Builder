# TASK TYPE: CAPTURE REDUCER

The runtime executes this deterministic task itself inside `python3 -m research_control run`; it is not dispatched to an agent. This text documents the contract it enforces.

Act as the sole writer of the source manifest, capture dispositions, extraction
scope, publication-date table, and coverage reports. Do not fetch new sources.

Run:

```bash
python3 -m research_control reduce capture
```

Fail if a discovered in-scope source lacks a terminal receipt, a captured file
is missing, a receipt/source ID differs, or a source marked captured lacks a
canonical text derivative. Preserve blocked sources in the blocked and coverage
reports. Completion is source accounting after saturated discovery, not a
minimum or maximum source count.
