---
name: gatekeeper
description: Use before creating or editing any .py file, before any implementation work, or when the user mentions Phase 0, Rule 1, NFR-5, constitution.md, spec.md, plan.md, tasks.md, git gate, or provenance. Spawns the gatekeeper subagent to block code until the four spec artifacts are committed.
---

# Gatekeeper skill — Phase 0 enforcement (Rule 1 + NFR-5)

This skill is the development gate for the Saylani Student Ops Desk. It exists because Rule 1 forbids any source file before Phase 0 is complete and committed, and NFR-5 grades that order in `git log`.

## When to run

Run this skill and obey its verdict in every case:

- Before the first `.py` file is written.
- Before any agent writes, edits, or generates Python or other core codebase files.
- When `constitution.md`, `spec.md`, `plan.md`, or `tasks.md` are in question.
- When the user says “gate”, “gatekeeper”, “phase 0”, “is it safe to code”, or asks to verify provenance.
- After any interruption, new session, or compaction that could have lost Phase 0 state.

Reading docs, writing the four Phase 0 markdown files, and editing `.md`/config for the spec phase do not require a PASS. Application code does.

## Execution

1. Spawn the `gatekeeper` subagent with the Task tool. Prompt it to validate the current workspace and git history for Rule 1 and NFR-5. Tell it the project root is this OPS Desk Assignment directory.
2. Do not continue to implementation while its verdict is pending.
3. Read the verdict it returns. It must be exactly `PASS` or `BLOCK`.

## On verdict BLOCK

1. Stop. Do not create, edit, or run any application code.
2. Alert the user with the subagent’s REASON and file status table.
3. Show the auto-generated `git add` / `git commit` remediation commands for the Phase 0 markdown files.
4. Do not invent a PASS. Re-run the gatekeeper only after the user has committed the remediation.

## On verdict PASS

1. Report to the user: Phase 0 is complete and legally committed; core codebase generation may proceed.
2. Continue with implementation tasks from `tasks.md` in order.
3. Re-run this skill at the start of any new session before touching `.py` files again.

## Hard rules for the main agent

- Never write a `.py` file until the gatekeeper reports PASS.
- Never treat uncommitted Phase 0 files as complete.
- Never bundle Phase 0 markdown files and implementation code in one commit.
- If the gatekeeper and your own read of `git log` disagree, trust the gatekeeper and stop.

## Reference

Project rules live in the project guide (`PROJECT_GUIDE.md`, extracted from `student-ops-desk-project-guide.pdf`): Phase 0 requires `constitution.md`, `spec.md`, `plan.md`, `tasks.md`; NFR-5 checks their commit order against the first code commit.
