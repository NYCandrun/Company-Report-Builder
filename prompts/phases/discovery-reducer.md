# TASK TYPE: DISCOVERY REDUCER

Act as the single writer for the final discovery snapshot. Do not perform new
research and do not reinterpret an open channel as complete.

Run:

```bash
python3 -m research_control reduce discovery
```

The reducer must fail unless every channel has a terminal state, every channel
has a worker receipt, receipt state matches scheduler state, and completion
evidence is present. `blocked` and `incomplete` remain visible limitations; they
must never be rewritten as saturation.
