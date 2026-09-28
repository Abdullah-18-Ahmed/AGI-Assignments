---
name: trace-cost
description: Inspect token usage, turn counts, and model distribution across single-turn fast paths vs multi-turn reasoning paths. Use when asked about cost, token usage, model routing, or turn statistics.
---

# Trace Cost

Inspect and report token usage, turn counts, and model distribution, split by execution path:
**single-turn fast path** vs **multi-turn reasoning path**.

## When to use

- "how much did this cost", "token usage report", "which model handled what",
  "fast path vs reasoning path stats", verifying cost-tracing implementation

## Procedure

### 1. Locate trace data
Search for, in priority order:
- Trace/cost log files (`*.jsonl`, `traces/`, `logs/`, `usage*.json`)
- Test fixtures for trace verification
- The tracing module in source (grep for `usage`, `prompt_tokens`, `completion_tokens`,
  `total_tokens`, `model`, `turn`)

If no trace data and no tracing implementation exists -> report `NO_TRACE_DATA` with the files
you checked.

### 2. Classify each record
Each call/turn must be classified as:
- **fast path** — single-turn, simple lookup routed to the cheap/small model or direct
  catalogue lookup
- **reasoning path** — multi-turn, complex query routed to the larger model

If a record has no path label, report `UNCLASSIFIED` (a gap in tracing).

### 3. Aggregate

Compute per path and overall:

| Metric | Fast path | Reasoning path | Total |
|---|---|---|---|
| calls / turns | | | |
| prompt tokens | | | |
| completion tokens | | | |
| total tokens | | | |
| distinct models used | | | |

Also compute:
- **Turn count distribution** (how many turns per session: 1, 2, 3...)
- **Model distribution** (percentage of calls per model id, split by path)
- **Avg tokens per call** per path
- **Estimated cost** if pricing is available; otherwise state pricing is not configured

### 4. Sanity checks
- Every logged call has a `model` name and numeric usage values taken from the SDK response
  object (not estimated).
- Fast path calls are single-turn (turn count = 1). Multi-turn records on the fast path are a
  routing violation.
- Reasoning path is not being used for trivial lookups (cost leak).
- No API keys or secrets appear in trace output.
- Turn counts match the actual message history length.

## Output format

```
COST TRACE: OK | GAP | NO_TRACE_DATA

SOURCE: <files inspected>

TOKEN USAGE
prompt: N  completion: N  total: N

BY PATH
fast path     | calls: N | turns: N | tokens: N | models: <list>
reasoning path| calls: N | turns: N | tokens: N | models: <list>

MODEL DISTRIBUTION
- <model id>: N calls (x%) [fast|reasoning|both]

TURN COUNTS
- 1 turn: N sessions
- 2 turns: N sessions
- >2 turns: N sessions

ISSUES
- [UNCLASSIFIED|ROUTING VIOLATION|MISSING USAGE|SECRET LEAK|ESTIMATED USAGE] <detail>

VERDICT
<one sentence on whether cost tracing meets requirements>
```

Rules:
- Never fabricate numbers. If a metric cannot be computed, write `n/a` and why.
- `GAP` when any issue is found; `NO_TRACE_DATA` when nothing exists to inspect.
