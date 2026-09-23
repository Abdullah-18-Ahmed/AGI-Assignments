---
name: requirements-auditor
description: Use when Phase 1, 2, or 3 is complete, or when asked to audit NFR-1, NFR-2, FR-1, FR-7, secrets, agent-level model config, turn ceiling, or Ticket typed output. Spawns the requirements-auditor subagent to scan .py files and returns a blocking punch-list before the next phase starts.
---

# Requirements Auditor skill — NFR + FR-7 phase gate

Strict read-only review of application Python against the Ops Desk spec. Violations block phase exit.

## When to run

- You announce **Phase 1**, **Phase 2**, or **Phase 3** is complete.
- User says “audit phase”, “requirements audit”, “NFR check”, “FR-7 check”, or “can we move on”.
- Automatically at the end of each phase before any next-phase task begins.

This skill does **not** replace the `gatekeeper` (Phase 0 / Rule 1). Run gatekeeper before writing code; run this auditor before **advancing a phase**.

## Execution

1. Spawn the `requirements-auditor` subagent (Task tool). Tell it the project root and which phase just finished (1, 2, or 3).
2. Wait for its verdict. Do not start the next phase while verdict is `FAIL`.
3. Show the user the full punch-list verbatim.
4. After fixes, re-run the same subagent until `REQUIREMENTS AUDITOR: PASS`.

## Phase checklist (auditor must cover)

| Phase | Must check |
|-------|------------|
| Phase 1 | NFR-1 secrets; NFR-2+FR-1 `gpt-4o-mini` at agent level, turn ceiling, `asyncio.run`; FR-7 `Ticket` typed final output |
| Phase 2 | Phase 1 checks still green + FR-5/6/8/9 behavior already in tree (tool gating, ceilings, guardrail) — note gaps as MISSING if code not yet present |
| Phase 3 | Prior checks + FR-10–13 / NFR-3–4 as implemented; never waive NFR-1 or FR-7 |

## Strict constraints (summary)

- **NFR-1:** `os.environ` or `dotenv` only; no hardcoded keys; missing key raises a clear exception; `.env` gitignored.
- **NFR-2 & FR-1:** **`gpt-4o-mini`** configured **at the agent level** (not global-only); explicit turn ceiling number in code; async entry via `asyncio.run`.
- **FR-7:** `type(result.final_output) is Ticket` (Pydantic `Ticket`), not a string; branch on `resolved` / `escalate` in Python.

## Punch-list contract

On any violation the subagent returns:

```
REQUIREMENTS AUDITOR: FAIL
PUNCH-LIST (blocking, fix before next phase):
[ ] [NFR-1] ...
[ ] [FR-1] ...
[ ] [FR-7] ...
CLEAR PHASE only when punch-list is empty.
```

- **FAIL/MISSING** → stop; user fixes; re-audit.
- **PASS** → phase may exit; next phase may begin.

## Out of scope

- Auto-fixing violations  
- Phase 0 creation (gatekeeper)  
- Fixture generation (fixture-architect)  
- Changing the model away from `gpt-4o-mini` unless the user redefines it
