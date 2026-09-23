---
name: desk-tester-evaluator
description: Use when executing test suites for FR-1..FR-13 and NFR-1..NFR-5, running wall-clock benchmarks proving FR-5 concurrency, planting synthetic secrets to verify output guardrails, validating ledger.jsonl format, or preparing viva defense answers for the Code Review Desk.
---

# Desk Tester Evaluator Skill

Automated testing, benchmark execution, and viva defense verification for the Code Review Desk.

## Responsibilities

1. Execute test suites verifying every FR-1..FR-13 and NFR-1..NFR-5
2. Run side-by-side wall-clock benchmarks: sequential vs `asyncio.gather` concurrent (FR-5)
3. Test security controls with synthetic secrets in test diffs (FR-8)
4. Validate `ledger.jsonl` output formatting
5. Prepare answers for project defense questions

## FR Test Matrix

| FR | Test Method | Pass Criteria |
|----|-------------|---------------|
| FR-1 | Two-file diff → 2 chunks; malformed diff → message | No traceback; no global client |
| FR-2 | Tool reads ruleset_id via wrapper; grep prompts for repo name | Schema has no wrapper param; no repo name in prompts |
| FR-3 | ... | ... |
| FR-4 | ... | ... |
| FR-5 | Wall-clock: sequential vs concurrent | Concurrent strictly faster; 3 reviewers overlap |
| FR-6 | ... | ... |
| FR-7 | ... | ... |
| FR-8 | Plant synthetic secret in diff | Output refuses to quote secret |
| FR-9 | ... | ... |
| FR-10 | ... | ... |
| FR-11 | ... | ... |
| FR-12 | ... | ... |
| FR-13 | ... | ... |

## FR-5 Benchmark Procedure

```python
import time, asyncio

# Sequential
start = time.perf_counter()
await run_reviewer(security, diff)
await run_reviewer(tests, diff)
await run_reviewer(style, diff)
sequential = time.perf_counter() - start

# Concurrent
start = time.perf_counter()
await asyncio.gather(
    run_reviewer(security, diff),
    run_reviewer(tests, diff),
    run_reviewer(style, diff),
)
concurrent = time.perf_counter() - start

assert concurrent < sequential
```

Report: sequential_ms, concurrent_ms, speedup_ratio, which reviewer was slowest.

## FR-8 Security Test Procedure

1. Create test diff containing synthetic secrets (fake AWS key, fake API token, fake password)
2. Run full review pipeline
3. Assert: no output field contains the synthetic secret string
4. Assert: guardrail refusal appears in findings or log

## ledger.jsonl Validation

Each line must be valid JSON with:
- `timestamp` (ISO 8601)
- `agent` (name)
- `tokens_in`, `tokens_out` (integers)
- `findings_count` (integer)
- `duration_ms` (integer)

Validate: every line parses; schema matches; no missing fields.

## NFR-1..NFR-5 Verification

- NFR-1: Reproducibility — same diff → same findings (deterministic given seed/temp)
- NFR-2: No secrets in output — covered by FR-8 tests
- NFR-3: Streaming latency — first finding appears before all reviewers complete
- NFR-4: Trace completeness — single trace contains all three reviewers
- NFR-5: Error isolation — tool failure returns error object, run continues

## Viva Defense Answers

Prepare concise answers for:
1. "How does the fan-out work?" → asyncio.gather on three Reviewer agents
2. "How do you know FR-5 is satisfied?" → wall-clock benchmark numbers
3. "What happens if a secret appears in the diff?" → output guardrail blocks it (FR-8)
4. "How is the slowest reviewer identified?" → per-reviewer spans in the trace (FR-10)
5. "Why spec-first?" → Phase 0 gate; git history is evidence
6. "What was cut and why?" → cut list order: FR-11 → FR-7 → FR-10 hooks; never FR-5/FR-8
