# Plan — Code Review Desk

Architecture: agents, concurrency, tool contracts, boundary schemas.

## System Overview

```
Diff Path (CLI / Chainlit paste)
    │
    ▼
[Intake] ── split by file ──► per-file chunks          (FR-1)
    │
    ▼
┌─────────────────────────────────────────────┐
│  asyncio.gather (FR-5)                      │
│  ┌──────────────┐                           │
│  │SecurityReview│ (clone, security tuning)  │
│  ├──────────────┤                           │
│  │TestReviewer  │ (clone, test tuning)      │
│  ├──────────────┤                           │
│  │StyleReviewer │ (clone, style tuning)     │
│  └──────────────┘                           │
└─────────────────────────────────────────────┘
    │  list[Finding] from each                 (FR-3)
    ▼
[Desk host] ── tools=[MergeAgent.as_tool] ──► merged report  (FR-6 tool)
    │
    ├─ (on critical security finding) ──handoff──► [RemediationAgent]  (FR-6 handoff)
    │   (run starts on SecurityReviewer which has handoffs=[handoff(Remediation)])
    ▼
[Output Guardrail] ──► Chainlit stream (FR-12) + ledger.jsonl (FR-11) + one trace (FR-13)
```

## Agents

### Base Reviewer
- Model: `gpt-4o-mini` (configured on instance)
- Output type: `list[Finding]`
- Instructions: built dynamically from ReviewContext at call time (no repo name in prompt) — FR-4
- Tools: `read_ruleset` (required via `tool_choice`), wrapped with `failure_error_function` — FR-9

### SecurityReviewer / TestReviewer / StyleReviewer (clones)
- `base.clone(name=..., instructions=...)` — FR-5
- Distinct instructions per reviewer — FR-6 tuning within the three clones

### MergeAgent / Desk host
- Merge exposed as a tool: `merge_agent.as_tool(tool_name="merge_findings", ...)` — FR-6
- Desk host agent holds the conversation and calls that tool — FR-6
- Deduplicates and orders by severity

### RemediationAgent
- Reached via `handoff` from SecurityReviewer on critical finding — FR-6
- On critical, pipeline starts the run on SecurityReviewer so the handoff transfers to Remediation
- Output: `RemediationProposal` (finding, patch, rationale)

## Concurrency

- Three reviewers run via `asyncio.gather` — FR-5
- Findings stream to the UI as each completes (`on_findings` callback) — FR-12

## Data Models (Pydantic)

```python
from typing import Literal
from pydantic import BaseModel

class Finding(BaseModel):
    file: str
    line: int
    severity: Literal["critical", "major", "minor"]
    message: str

class ReviewContext:  # dataclass, not Pydantic
    repo: str
    language: str
    ruleset_id: str
    strictness: str = "normal"  # "normal" | "strict"

class MergedReport(BaseModel):
    findings: list[Finding]
    reviewers_completed: list[str]
    slowest_reviewer: str | None = None
    summary: str

class RemediationProposal(BaseModel):
    finding: Finding
    patch: str
    rationale: str
```

Ledger line (FR-11), one JSON object per run:

```json
{"ts": "2026-09-23T19:04:11Z", "request_id": "req_...", "agent": "SecurityReviewer", "ms": 2140, "findings": 3}
```

## Tool Contracts

### `read_ruleset() -> str` (required tool, FR-9)
- Reads the active ruleset via ReviewContext wrapper (schema has no wrapper params)
- On missing file / error: returns a sentence the model can use — never raises
- Forced with `ModelSettings(tool_choice="read_ruleset")` on reviewers that must consult the ruleset

### `merge_findings(...)` via `as_tool` (FR-6)
- Agent-as-a-tool from MergeAgent
- Deduplicates, sorts by severity

## Boundary Schemas

| Boundary | Direction | Schema |
|----------|-----------|--------|
| CLI → Intake | path: `str` | — |
| Intake → Reviewers | chunk: `str`, context: `ReviewContext` | — |
| Reviewer → Merge | `list[Finding]` | Pydantic |
| Merge → UI/report | `list[Finding]` / `MergedReport` | Pydantic |
| Security → Remediation | `Finding` (handoff) | Pydantic |
| Remediation → UI | `RemediationProposal` | Pydantic |
| Any run → ledger | `{ts, request_id, agent, ms, findings}` | JSONL |

## Execution Controls

- **Output guardrail**: secret scanner on every agent's `output_guardrails` (FR-8)
- **Turn ceiling**: `max_turns` on every run; `MaxTurnsExceeded` caught → partial (FR-9)
- **Model override**: per-run `RunConfig(model=...)` without editing agents (FR-7)
- **Error handling**: tools use `failure_error_function`; never raise into runner (NFR-4)

## Observability

- **Run-level hooks**: latency + tokens per reviewer in report footer (FR-10)
- **Agent-level hooks**: attached to exactly one reviewer (FR-10)
- **ledger.jsonl**: custom runner wrapper, registered once at startup (FR-11)
- **OpenTelemetry**: one root span, three overlapping reviewer spans + merge; slowest = max duration; exported under configured key (FR-13)
- **Chainlit**: streams findings as each reviewer lands; session holds context + last report (FR-12)
