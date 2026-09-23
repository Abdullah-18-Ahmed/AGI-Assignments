# Tasks — Code Review Desk

Ordered implementation tasks. Each is independently verifiable and names the requirement it serves.

## Phase 1 — Intake and one reviewer (FR-1 … FR-4)

### T1 — Project scaffolding and .env loading
- Create package structure, `pyproject.toml`, `.env.example`, `.gitignore` (includes `.env`)
- Load `OPENAI_API_KEY` from `.env` via python-dotenv
- **Serves:** constitution (provider config), NFR-2
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

### T4 — Finding model and structured output (FR-4)
- Define Pydantic `Finding` (file, line, severity, rule, message) and `Severity` enum
- Configure base reviewer with `output_type=list[Finding]`
- Handle malformed model output gracefully
- **Serves:** FR-4
- **Verify:** findings validate against schema; malformed output caught

### T5 — Single reviewer end-to-end (FR-3)
- Wire base reviewer: chunk + context → `list[Finding]`
- Wrap tools with error handling (never raise into runner)
- Set `max_turns` ceiling
- **Serves:** FR-3, NFR-5, execution controls
- **Verify:** feed a chunk → populated findings; tool error → error object, run continues

## Phase 2 — Fan out (FR-5 … FR-9)

### T6 — Clone base into three tuned reviewers (FR-6)
- `clone()` base into SecurityReviewer, TestReviewer, StyleReviewer
- Distinct instructions per reviewer
- **Serves:** FR-6
- **Verify:** same diff → different finding distributions across reviewers

### T7 — Concurrent execution via asyncio.gather (FR-5)
- Run three reviewers concurrently with `asyncio.gather`
- Use `asyncio.as_completed` for streaming completion order
- **Serves:** FR-5 (never cut)
- **Verify:** wall-clock benchmark: concurrent < sequential; three spans overlap in trace

### T8 — Streaming findings to interface (FR-7)
- Stream each reviewer's findings as they complete (not batched)
- **Serves:** FR-7
- **Verify:** first reviewer's findings appear before slowest finishes

### T9 — Output guardrail for secrets (FR-8)
- Implement secret-scanning `Guardrail` on all agents' `output_guardrails`
- Block any finding quoting a planted secret; log refusal
- **Serves:** FR-8 (never cut), NFR-2
- **Verify:** diff with planted secret → no output echoes it; refusal recorded

### T10 — Merge agent as tool (FR-9)
- Build MergeAgent; expose via `as_tool(tool_name="merge_findings")`
- Combine three `list[Finding]` → `MergedReport` (dedupe, sort by severity)
- **Serves:** FR-9
- **Verify:** merged report contains findings from all three reviewers

## Phase 3 — Observe and ship (FR-10 … FR-13)

### T11 — Remediation agent via handoff (FR-10)
- Configure SecurityReviewer `handoffs=["RemediationAgent"]`
- Trigger on critical finding; Remediation returns `RemediationProposal`
- **Serves:** FR-10
- **Verify:** critical vulnerability → handoff fires → patch proposed

### T12 — Trace with slowest reviewer (FR-11)
- OpenTelemetry tracing: one trace, three reviewer spans + merge span
- Identify slowest reviewer by span duration
- **Serves:** FR-11, NFR-4
- **Verify:** trace shows all spans; slowest nameable

### T13 — ledger.jsonl via custom runner (FR-12)
- Lifecycle hooks capture token usage
- Custom runner appends `RunLedgerEntry` JSONL per run
- **Serves:** FR-12
- **Verify:** every run → one valid JSON line with all required fields

### T14 — Chainlit interface (FR-13)
- Chainlit app: accept diff path, run pipeline
- Stream findings live; show per-reviewer progress
- Display merged report + trace summary (slowest reviewer)
- **Serves:** FR-13, NFR-3
- **Verify:** app streams findings before all reviewers done; shows merged report

### T15 — Reproducibility check (NFR-1)
- Run same diff + context twice; compare findings
- **Serves:** NFR-1
- **Verify:** identical findings across runs

### T16 — Full test suite and benchmark
- Tests for FR-1 … FR-13, NFR-1 … NFR-5
- FR-5 wall-clock benchmark saved to `benchmark_fr5.json`
- FR-8 planted-secret tests
- ledger.jsonl format validation
- **Serves:** all requirements
- **Verify:** all tests pass; benchmark proves concurrency

## Cut List (if behind schedule)

Cut in this order:
1. FR-11 (T12) — trace slowest reviewer
2. FR-7 (T8) — streaming to interface
3. Agent-level hooks in FR-10 (T11 refinement)

**Never cut:** FR-5 (T7) or FR-8 (T9).
