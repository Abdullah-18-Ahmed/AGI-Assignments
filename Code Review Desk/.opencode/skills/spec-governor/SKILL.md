---
name: spec-governor
description: Use when enforcing specification-first development (Phase 0) for the Code Review Desk project - verifying constitution.md, spec.md, plan.md, tasks.md exist before code, checking FR/NFR numbering and traceability, or rejecting premature implementation.
---

# Spec Governor Skill

Enforces specification-first development for the Code Review Desk project.

## Responsibilities

1. Verify strict adherence to specification-first development (Phase 0)
2. Confirm `constitution.md`, `spec.md`, `plan.md`, and `tasks.md` are generated and committed before any Python source code is written
3. Ensure every requirement (FR-1 through FR-13, NFR-1 through NFR-5) is numbered, testable, and explicitly mapped to implementation tasks
4. Reject any attempt to generate application source code before Phase 0 artifacts are complete and verified

## Phase 0 Gate Checklist

All four must exist and be committed before code:

- [ ] `constitution.md` — rules the build may not break (provider/level, secrets in .env only, no tool raises into runner, reproducible reviews)
- [ ] `spec.md` — behavior specification with all FR-1..FR-13, NFR-1..NFR-5, and three deliberate non-goals
- [ ] `plan.md` — architecture: agents, concurrency, tool I/O contracts, structure shapes at boundaries
- [ ] `tasks.md` — ordered, independently verifiable tasks each naming the requirement it serves

## Requirement Verification

For each requirement check:
- Numbered (FR-N or NFR-N)
- Testable (has a "Done when" criterion)
- Mapped to at least one task in `tasks.md`

## Rejection Rules

Reject if:
- Any `.py` file exists in the project before Phase 0 commit
- A commit contains both spec artifacts and implementation code
- Any FR/NFR is missing, unnumbered, or unmapped
- `constitution.md` omits any of the four minimum rules

## Cut List (for schedule pressure)

In order: FR-11 → FR-7 → agent-level hooks in FR-10.
Never cut: FR-5 (concurrency) or FR-8 (output guardrail).
