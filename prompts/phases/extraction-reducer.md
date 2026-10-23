# TASK TYPE: EXTRACTION REDUCER

Act as the single writer for canonical candidate and extraction-disposition
stores. Do not create, remove, or reinterpret research claims.

Run:

```bash
python3 -m research_control reduce extraction
```

The reducer concatenates only assigned worker parts and must reject duplicate
candidate IDs, malformed dispositions, duplicate assignment/input pairs, or
missing parts. Preserve valid zero-fact dispositions.
