# Spec — Code Review Desk

Behavioral specification. What the Desk does, stated as behavior.

## Functional Requirements

### FR-1 — Diff intake and file splitting
The Desk reads a unified diff from a path given on the command line. Before any model sees the input, the diff is split into per-file chunks. The entry point is asynchronous. An empty or malformed diff produces a user-facing message, never a traceback. The model is `gpt-4o-mini`, configured on the agent itself. Nothing in the code sets a global default client.

**Done when:** a two-file diff produces two chunks; an empty or malformed diff is reported as a message; grepping the code finds no global default client.

### FR-2 — Repository rules in context, not in prompts
A `ReviewContext` dataclass is passed to every run and read by tools. It carries `repo`, `language`, `ruleset_id`, and `strictness`. It never appears in prompt text.

**Done when:** a tool reads `ruleset_id` through the wrapper; the generated schema for that tool has no wrapper parameter; grepping prompts finds no repository name.

### FR-3 — Single reviewer pipeline runs end-to-end
One reviewer agent accepts a file chunk plus ReviewContext and returns a list of findings in a structured format.

**Done when:** feeding a chunk produces `list[Finding]` with file, line, severity, rule, and message populated.

### FR-4 — Findings are structured and typed
All findings cross agent boundaries as Pydantic models. No free-text findings enter the merge step.

**Done when:** every finding validates against the `Finding` schema; malformed model output is caught and reported.

### FR-5 — Three reviewers run concurrently
Security, Test, and Style reviewers execute in parallel via `asyncio.gather`. They are clones of a base Reviewer agent, each with its own tuned instructions.

**Done when:** a wall-clock benchmark shows concurrent execution strictly faster than sequential; all three reviewers overlap in the trace.

### FR-6 — Reviewers are tuned differently
Each reviewer clone has distinct instructions: security focuses on vulnerabilities, tests on coverage gaps and flaky patterns, style on convention violations.

**Done when:** the same diff yields different finding distributions across the three reviewers.

### FR-7 — Findings stream as they land
Results appear in the interface as each reviewer completes, not as one batch at the end.

**Done when:** the UI shows the first reviewer's findings before the slowest reviewer finishes.

### FR-8 — Output guardrail blocks secrets
No output from any agent may quote a secret it found in the diff. An output guardrail scans every finding.

**Done when:** a diff containing a planted secret produces no finding that echoes the secret; the guardrail refusal is recorded.

### FR-9 — Merge agent combines findings
A Merge agent, exposed via `as_tool`, receives findings from all three reviewers and produces one structured report.

**Done when:** the merged report contains findings from all three reviewers, deduplicated and sorted by severity.

### FR-10 — Critical finding triggers Remediation via handoff
When the security reviewer emits a critical finding, the conversation hands off to a Remediation agent that proposes a fix.

**Done when:** a diff with a critical vulnerability triggers the handoff; the Remediation agent returns a proposed patch.

### FR-11 — Trace identifies the slowest reviewer
The entire review is one trace. Per-reviewer span durations make the slowest reviewer nameable.

**Done when:** the trace shows three reviewer spans; the slowest is identifiable by duration.

### FR-12 — Token usage is ledgered
Each run appends a structured line to `ledger.jsonl` with timestamp, agent, token counts, and findings count.

**Done when:** every run produces one valid JSON line in `ledger.jsonl`.

### FR-13 — Chainlit interface presents the review
A Chainlit app accepts a diff path, runs the pipeline, and streams findings, the merged report, and the trace summary.

**Done when:** the app shows per-reviewer progress, streams findings live, and displays the merged report.

## Non-Functional Requirements

### NFR-1 — Reproducibility
The same diff and ReviewContext produce the same findings across runs (given fixed model settings).

### NFR-2 — No secret leakage
No secret value from the diff appears in any report, log, trace, or streamed output.

### NFR-3 — Streaming latency
The first finding appears in the interface before all reviewers complete.

### NFR-4 — Trace completeness
A single trace contains all three reviewer spans and the merge step.

### NFR-5 — Error isolation
A tool failure returns an error object to the model; the run continues; no exception reaches the Runner.

## Non-Goals (what this project deliberately will not do)

1. **No multi-repository or monorepo orchestration.** The Desk reviews one diff from one repository per run. It does not coordinate across repos or manage branch state.

2. **No persistent review history or database.** Findings are produced for the current run and written to `ledger.jsonl`. There is no queryable store, no review dashboard across runs, no authentication.

3. **No automatic commit or PR integration.** The Desk proposes fixes via the Remediation agent but never pushes code, opens PRs, or mutates the repository. It is read-only with respect to the codebase.
