# Constitution — Saylani Student Ops Desk

Binding rules for this build. No implementation may violate them. Phase 0 artifact — Spec-Kit-Plus.

## 1. Model provider and configuration level

- The Desk runs on **OpenAI native models** via the **OpenAI Agents SDK**.
- Default agent model: **`gpt-4o-mini`**, configured **at the agent level** on each agent definition.
- The model is **not** set only via a process-global default client and **not** patched per run as the sole configuration path.
- Every agent (Desk, Assignments, Careers, Summariser) **declares its own model settings** explicitly (NFR-2).
- An explicit **turn ceiling** (named integer constant) is defined for runs; the Desk raises/reports at the ceiling rather than looping forever (FR-9).

## 2. Secrets

- API keys and secrets live **only** in `.env`.
- `.env` is **gitignored**; no secret value appears in source, fixtures, or commits.
- Keys are read via `os.environ` / `os.getenv` or `python-dotenv` (`load_dotenv`) only — never hardcoded.
- A missing required key produces a **clear startup exception** (short, actionable message) before any agent run — not a stack trace three layers deep (NFR-1).

## 3. Tools never raise to the caller

- Tool implementations **must not** let exceptions escape to the runner/caller (NFR-4).
- On bad data or failure, a tool returns **a sentence the model can act on** (or a defined error value the runner handles), never a raw raise.
- Guardrail tripwires and turn-ceiling errors are **caught in program code** and converted to polite user-facing replies.

## 4. Student data and the model

- Student identity (name, roll number, tier, open tickets) enters the model **only through deliberate, authored instructions/context** built by this codebase — never by accident, never via free-form prompt concatenation of raw DB dumps.
- The prompt text must **not** embed name / roll_no / tier as a wrapper parameter pattern; profile access is via **local context / profile-reading tools** whose schemas do not expose a student wrapper (FR-3).
- No student data is logged to durable audit except what FR-10 timeline intentionally records as non-sensitive run metadata.

## 5. Specification before implementation (Rule 1 + NFR-5)

- No application `.py` source exists before `constitution.md`, `spec.md`, `plan.md`, and `tasks.md` are **committed**.
- Git history must show Phase 0 artifacts **before** the first code commit.
- A single commit may not mix Phase 0 specs with implementation code.

## 6. Structured final output

- Resolved conversation output is a **Pydantic `Ticket`**, not prose or an unparsed string (FR-7).
- Branching uses typed fields (`resolved`, `escalate`) in Python control flow.

## 7. Scope of knowledge

- Course facts come from **`courses.json`** only, reachable through tools (FR-2).
- The Desk does not invent assignment ids or policies absent from the file.

## 8. Non-goals enforcement

- The three explicit non-goals in `spec.md` are load-bearing; features that require them are rejected even if time remains.
