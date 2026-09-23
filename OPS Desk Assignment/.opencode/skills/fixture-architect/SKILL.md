---
name: fixture-architect
description: Use when generating courses.json, test_profiles.py, StudentProfile fixtures, sample course data, or test data for FR-2, FR-4, and FR-9 — without writing Ops Desk app logic. Spawns the fixture-architect subagent after the gatekeeper allows file writes.
---

# Fixture Architect skill — FR-2 / FR-4 / FR-9 test data

Scaffolds the testing environment only: course JSON and profile instances. No app logic.

## Hard precondition

1. Load and run the `gatekeeper` skill/subagent first.
2. On `BLOCK`: do not create `courses.json` or `test_profiles.py`. Alert the user with the Phase 0 remediation commands and stop.
3. On `PASS` only: continue with execution 1 and 2 below.

Phase 0 files required: `constitution.md`, `spec.md`, `plan.md`, `tasks.md` committed with no `.py` before them.

## Skill execution 1 — `courses.json` (FR-2)

Spawn the `fixture-architect` subagent and instruct it to:

- Write `courses.json` at the project root.
- Include **at least 3 diverse courses** (ids, titles, schedules, policies, assignments).
- Use unique assignment ids across the file so tool lookup tests are robust.
- Keep valid JSON matching the FR-2 shape (`courses[]` with `id`, `title`, `schedule`, `policies`, `assignments[]`).

No Desk tools or loaders in this step — data file only.

## Skill execution 2 — `test_profiles.py` (FR-4, FR-9)

Have the same subagent write `test_profiles.py` with the `StudentProfile` dataclass and **three** instances:

1. **Regular, 0 tickets** — baseline dynamic prompt (FR-4).
2. **Regular, `open_tickets=3`** — must be able to demonstrate terse instructions (FR-4).
3. **Scholarship tier** — must be able to demonstrate scholarship-only tool gating (FR-9).

`course_id` on each profile must match an id in `courses.json`. Instances only — no prompt templates, no tools, no agents.

## Verify after write

- `courses.json` parses (`python -c "import json; json.load(open('courses.json'))"`).
- `test_profiles.py` compiles (`python -m py_compile test_profiles.py`).
- Count courses ≥ 3; count profiles = 3; one profile has `open_tickets == 3`; one has `tier == "scholarship"`.

## Report format

```
FIXTURE ARCHITECT: OK
- courses.json: <n> courses, <m> assignments
- test_profiles.py: 3 profiles (regular/0, regular/3, scholarship)
```

On gate failure: `FIXTURE ARCHITECT: BLOCK` + gatekeeper remediation only.

## Out of scope

App logic, tool functions, agent definitions, prompt builders, guardrails, tickets, Chainlit — those belong to later `tasks.md` work after Phase 0.
