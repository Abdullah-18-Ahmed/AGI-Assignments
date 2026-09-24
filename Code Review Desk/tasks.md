# Tasks — Code Review Desk

Ordered implementation tasks. Each is independently verifiable and names the requirement it serves.

## Phase 1 — Intake and one reviewer (FR-1 … FR-4)

### T1 — Project scaffolding and .env loading
- Create package structure, `pyproject.toml`, `.env.example`, `.gitignore` (includes `.env`)
- Load `OPENAI_API_KEY` from `.env` via python-dotenv
- **Serves:** constitution (provider config), NFR-1
- **Verify:** `.env` is gitignored; key loads; no key in any source file

### T2 — Async diff intake and per-file split (FR-1)
- Implement async entry point reading diff from CLI path
- Split unified diff into per-file chunks before any model call
- Handle empty/malformed diff with user-facing message, not traceback
- Configure `gpt-4o-mini` on the agent instance; no global default client
- **Serves:** FR-1
- **Verify:** two-file diff → 2 chunks; empty diff → message; grep finds no global client

### T3 — ReviewContext dataclass (FR-2)
- Define `ReviewContext` (repo, language, ruleset_id, strictness)
- Pass to every run; tools read through wrapper
- Ensure generated tool schema has no wrapper parameter
- Ensure no repo name appears in any prompt
- **Serves:** FR-2
- **Verify:** tool reads ruleset_id; schema clean; grep prompts for repo name → none

### T4 — Finding model and structured output (FR-3)
- Define Pydantic `Finding` (file, line, severity Literal["critical","major","minor"], message)
- Configure base reviewer with `output_type=list[Finding]`
- Handle malformed model output gracefully
- **Serves:** FR-3
- **Verify:** findings validate against schema; count criticals with a Python expression

### T5 — Dynamic instructions per run (FR-4)
- Build instructions from ruleset + language at request time; stricter when `strictness=strict`
- Expose resolved prompt for printing before model call
- **Serves:** FR-4
- **Verify:** two contexts → two different prompts; prompt printable pre-call

## Phase 2 — Fan out (FR-5 … FR-9)

### T6 — Clone base into three tuned reviewers (FR-5)
- `clone()` base into SecurityReviewer, TestReviewer, StyleReviewer
- Distinct instructions per reviewer
- **Serves:** FR-5
- **Verify:** same diff → different finding distributions across reviewers

### T7 — Concurrent execution via asyncio.gather (FR-5)
- Run three reviewers concurrently with `asyncio.gather`
- Stream completion order to UI as each finishes
- **Serves:** FR-5 (never cut)
- **Verify:** wall-clock benchmark: concurrent ≈ slowest single, not sum of three; both numbers shown

### T8 — Merge as tool + remediation by handoff (FR-6)
- Build MergeAgent; expose via `as_tool(tool_name="merge_findings")`
- Wire Remediation via `handoff` from SecurityReviewer on critical finding
- Two-sentence justification lives in `spec.md` FR-6
- **Serves:** FR-6
- **Verify:** both paths fire on the right diff; justification present in spec

### T9 — Run-level model override (FR-7)
- Accept `model_override` on run; pass `RunConfig(model=...)` without editing agents
- **Serves:** FR-7
- **Verify:** same agent object, two models; `agent.model` unchanged

### T10 — Output guardrail for secrets (FR-8)
- Secret-scanning output guardrail on all agents
- Catch `OutputGuardrailTripwireTriggered`; report refusal; no crash
- **Serves:** FR-8 (never cut), NFR-1
- **Verify:** planted key → refusal; clean diff passes; catch line pointable

### T11 — Required tools, failing tools, ceiling (FR-9)
- Force ruleset tool via `tool_choice`
- Tools use dedicated error handler; never raise into runner
- `max_turns` ceiling; `MaxTurnsExceeded` → partial review message
- **Serves:** FR-9, NFR-4, NFR-2
- **Verify:** delete ruleset file → sensible finish; state ceiling + reasoning

## Phase 3 — Observe and ship (FR-10 … FR-13)

### T12 — Latency/tokens hooks (FR-10)
- Run-level hooks capture latency + tokens per reviewer into footer
- Agent-level hooks attached to exactly one reviewer
- **Serves:** FR-10
- **Verify:** footer has three reviewer rows from run context; agent hooks on exactly one

### T13 — ledger.jsonl via custom runner (FR-11)
- Custom runner appends `{ts, request_id, agent, ms, findings}` per run
- Registered once at startup; no agent definition mentions it
- **Serves:** FR-11, NFR-3
- **Verify:** one line per run; unregister is the only off switch

### T14 — Chainlit streaming interface (FR-12)
- Chainlit app: accept pasted diff, await pipeline
- Stream findings live; session holds context + last report
- **Serves:** FR-12, NFR-3
- **Verify:** progressive text; second diff reuses context; handler awaits

### T15 — One trace, exported (FR-13)
- One root span covering reviewers + merge + handoff
- Three reviewer spans overlap; slowest nameable by duration
- Export under configured key
- **Serves:** FR-13, NFR-3
- **Verify:** open trace; overlapping spans; name slowest

### T16 — Startup key check (NFR-1)
- Missing `OPENAI_API_KEY` → one sentence at startup, not a stack trace
- **Serves:** NFR-1
- **Verify:** unset key → sentence; no traceback

### T17 — Full test suite and benchmark
- Tests for FR-1 … FR-13, NFR-1 … NFR-5
- FR-5 wall-clock benchmark saved to `benchmark_fr5.json`
- FR-8 planted-secret tests
- ledger.jsonl format validation
- **Serves:** all requirements
- **Verify:** all tests pass; benchmark proves concurrency

## Cut List (if behind schedule)

Cut in this order (per guide):
1. FR-11 (T13) — ledger
2. FR-7 (T9) — run-level model override
3. Agent-level hooks in FR-10 (T12 refinement)

**Never cut:** FR-5 (T7) or FR-8 (T10).
