# Spec — Code Review Desk

Behavioral specification. What the Desk does, stated as behavior.

## Functional Requirements

### FR-1 — A diff goes in, split by file
The Desk reads a unified diff from a path given on the command line and splits it into per-file chunks before any model sees it. The model is `gpt-4o-mini`, configured on the agent itself. The entry point is asynchronous. An empty or malformed diff is reported as a message, not a traceback. Nothing in the code sets a global default client.

**Done when:** a two-file diff produces two chunks; an empty or malformed diff is reported as a message; grepping the code finds no global default client.

### FR-2 — Repository rules live in context
A `ReviewContext` dataclass is passed to every run and read by tools. It never appears in prompt text. It carries `repo`, `language`, `ruleset_id`, and `strictness`.

**Done when:** a tool reads `ruleset_id` through the wrapper; the generated schema for that tool has no wrapper parameter; grepping prompts finds no repository name.

### FR-3 — Findings come back as a list of typed objects
A reviewer returns a list, not prose. Every finding crosses agent boundaries as a Pydantic model with `file`, `line`, `severity` (`critical` | `major` | `minor`), and `message`. The agent's `output_type` is `list[Finding]`.

**Done when:** you can iterate `final_output` and count criticals with a Python expression; every finding validates against the `Finding` schema.

### FR-4 — Reviewer instructions are built per run
The reviewer's system prompt is assembled at request time from the ruleset and the language in context, and gets terser when strictness is `strict`. The resolved prompt can be printed before any model call.

**Done when:** two contexts produce two visibly different prompts, and the resolved prompt is printable before any model call.

### FR-5 — Three reviewers, cloned, running concurrently
Security, tests, and style reviewers are clones of one base reviewer, differing in instructions and model settings. They run concurrently over the same diff, not one after another, via `asyncio.gather`.

**Done when:** the three reviews are launched together and awaited as a group; the wall clock for three concurrent reviews is close to the slowest single review, not the sum of all three; and both numbers can be shown.

### FR-6 — Merge as a tool, remediation by handoff
Two specialists, wired two different ways on purpose:

- A Merge specialist, exposed with `as_tool`, deduplicates overlapping findings and orders them by severity. The Desk keeps the conversation.
- A Remediation specialist, reached by `handoff`, takes over when a critical security finding exists, and proposes the patch directly to the user.

Merging is a tool call because the Desk must keep ownership of the conversation and needs one structured report before anything is shown to the user; remediation is a handoff because a critical finding should transfer the conversation to a specialist that speaks the fix directly to the user.

**Done when:** both paths fire on the right kind of diff, and this spec contains the two-sentence justification above.

### FR-7 — A cheaper second opinion, configured at the run level
The Desk can re-run a review on a cheaper model without touching any agent definition — the override happens on the run (`model_override` → `RunConfig(model=...)`).

**Done when:** the same reviewer object produces one review on its own model and one on the override, and no agent's `model=` changed between them.

### FR-8 — Nothing leaks: an output guardrail
An output guardrail inspects the finished report and refuses it if it contains anything shaped like a credential — an API key, token, or password copied out of the diff. The program catches the tripwire and reports the refusal; it does not crash.

**Done when:** a diff containing a fake key produces a refusal rather than a report; a clean diff passes untouched; the line that caught the exception can be pointed at.

### FR-9 — Required tools, failing tools, and a ceiling
Three controls, all present:

1. The reviewer that must consult the ruleset is configured so the model has no choice but to call it (`tool_choice`).
2. The tools hand their failures to a dedicated error handler rather than raising into the runner.
3. Every review runs under a turn ceiling (`max_turns`) that raises, is caught, and is reported as a partial review.

**Done when:** deleting the ruleset file produces a review that still finishes with a sensible message; the ceiling is stated with reasoning.

### FR-10 — Latency and tokens per reviewer
Run-level hooks record, for each reviewer, how long it took and how many tokens it used, and the report carries those numbers in a footer. Agent-level hooks are attached to exactly one reviewer.

**Done when:** the footer shows three reviewer rows with token counts read from the run context, not estimated; agent-level hooks are attached to exactly one reviewer.

### FR-11 — Every run lands in a ledger
A custom runner appends one line per run to `ledger.jsonl`, registered once at startup. No agent definition mentions it. Line shape: `{"ts", "request_id", "agent", "ms", "findings"}`.

**Done when:** one review produces one ledger line per run; removing the registration is the only change needed to switch the ledger off.

### FR-12 — Findings stream into the interface
A Chainlit page takes a pasted diff and shows findings as they arrive rather than after everything finishes. Session state holds the context and the last report. The handler awaits its run rather than calling a synchronous variant.

**Done when:** text appears progressively during a review; a second diff in the same session reuses the existing context; the handler awaits its run.

### FR-13 — One review, one trace
Tracing is enabled and exported under the configured key. A whole review — all three reviewers, the merge, any handoff — appears as one trace. Reviewer spans overlap in time rather than stack end to end.

**Done when:** the trace can be opened; the three reviewers overlap; the slowest one can be named from span durations.

## Non-functional requirements

### NFR-1 — Secrets
Keys live in `.env`, gitignored. A missing `OPENAI_API_KEY` fails at startup with a sentence, not a stack trace. No secret is ever written to the ledger or the report.

### NFR-2 — Cost
Every agent declares its own model settings. No unbounded generation anywhere (`max_turns` on every run).

### NFR-3 — Observability
Every review is traceable and every run is in the ledger.

### NFR-4 — Failure
A tool that meets bad input returns a sentence the model can use. A tool that raises into the runner is a defect.

### NFR-5 — Provenance
`git log` shows the four Phase 0 artifacts committed before the first code commit. This is checked.

## Non-Goals (what this project deliberately will not do)

1. **No multi-repository or monorepo orchestration.** The Desk reviews one diff from one repository per run. It does not coordinate across repos or manage branch state.

2. **No persistent review history or database.** Findings are produced for the current run and written to `ledger.jsonl`. There is no queryable store, no review dashboard across runs, no authentication.

3. **No automatic commit or PR integration.** The Desk proposes fixes via the Remediation agent but never pushes code, opens PRs, or mutates the repository. It is read-only with respect to the codebase.
