---
name: verify-phase
description: Systematically run verification against the current Phase requirements. Use when asked to verify, validate, check off, or close out a phase of the Shop-desk project.
---

# Verify Phase

Systematically verify that the current phase of the Shop-desk project meets its requirements
before marking it complete.

## When to use

- "verify phase N", "check phase requirements", "is this phase done", "close out the phase"

## Procedure

Follow these steps in order. Do not skip a step. Do not mark the phase complete until every
step returns a result.

### 1. Identify the phase
- Read `tasks.md` (and `plan.md` if needed) to determine which phase is in progress.
- Collect every task in that phase and the FR/NFR IDs it claims to satisfy.

### 2. Spec consistency
- Invoke the `spec-checker` subagent to validate `constitution.md`, `spec.md`, `plan.md`,
  `tasks.md` for coverage, contradictions, and unresolved placeholders.

### 3. Functional verification
- Invoke the `test-runner` subagent to execute tests and validate FR-1..FR-13 evidence.
- Confirm each FR in scope has concrete evidence (test name or output), not just a claim.

### 4. Guardrail verification
- Invoke the `check-guardrails` skill logic: confirm prices and SKUs in all outputs come
  verbatim from `catalogue.json`.

### 5. Cost/trace verification
- Invoke the `trace-cost` skill logic: confirm token usage, turn counts, and model
  distribution are recorded and sane for this phase.

### 6. Code audit
- Invoke the `code-auditor` subagent on files changed during this phase.

### 7. Report

Produce exactly:

```
PHASE VERIFICATION: <phase id/name>
STATUS: PASS | FAIL | BLOCKED

SPEC CHECK: <PASS/FAIL> (<violations count>)
TESTS:      <PASS/FAIL> (<n passed, n failed>)
GUARDRAILS: <PASS/FAIL>
TRACES:     <PASS/FAIL>
AUDIT:      <PASS/FAIL> (<blockers count>)

REMAINING TASKS
- <task id> <description> (unverified/blocked)

REQUIRED ACTIONS
1. <specific action with file path>

VERDICT
Phase may/may not be marked complete because <reason>.
```

## Rules

- Report only what was actually executed. If a check could not run, mark it `NOT RUN` and say why.
- Never mark a phase PASS on partial evidence.
- Never edit task checkboxes to "done" as part of this skill — the verdict only.
