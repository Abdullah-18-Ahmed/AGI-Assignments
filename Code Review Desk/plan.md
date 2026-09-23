# Plan — Code Review Desk

Architecture: agents, concurrency, tool contracts, boundary schemas.

## System Overview

```
Diff Path (CLI)
    │
    ▼
[Intake] ── split by file ──► per-file chunks
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
    │  list[Finding] from each
    ▼
[MergeAgent.as_tool] ──► merged report
    │
    ├─ (on critical security finding) ──handoff──► [RemediationAgent]
    │
    ▼
[Output Guardrail] ──► Chainlit stream + ledger.jsonl + trace
```

## Agents

### Base Reviewer
- Model: `gpt-4o-mini` (configured on instance)
- Output type: `list[Finding]`
- Instructions: built dynamically from ReviewContext at call time (no repo name in prompt)
- Tools: `read_file_chunk`, `read_ruleset` — both wrapped, never raise

### SecurityReviewer (clone)
- `base.clone(name="SecurityReviewer", instructions=SECURITY_INSTRUCTIONS)`
- Tuned for: vulnerabilities, injection, secrets, auth flaws

### TestReviewer (clone)
- `base.clone(name="TestReviewer", instructions=TEST_INSTRUCTIONS)`
- Tuned for: coverage gaps, flaky patterns, assertion quality

### StyleReviewer (clone)
- `base.clone(name="StyleReviewer", instructions=STYLE_INSTRUCTIONS)`
- Tuned for: naming, structure, convention violations

### MergeAgent
- Exposed as a tool: `merge_agent.as_tool(tool_name="merge_findings", tool_description="Merge reviewer findings into one report")`
- Input: three `list[Finding]` payloads
- Output: `MergedReport`

### RemediationAgent
- Reached via `handoff` from SecurityReviewer on critical finding
- Input: the critical `Finding` + file chunk
- Output: `RemediationProposal` (patch text + rationale)

## Concurrency

- Three reviewers run via `asyncio.gather(*[Runner.run(r, chunk, context) for r in reviewers])`
- Each reviewer is independent; no shared mutable state
- Findings stream to the UI as each gather member completes (use `asyncio.as_completed` for streaming)

## Data Models (Pydantic)

```python
from pydantic import BaseModel, Field
from enum import Enum

class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"

class Finding(BaseModel):
    file: str
    line: int
    severity: Severity
    rule: str
    message: str

class ReviewContext(BaseModel):
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

class RunLedgerEntry(BaseModel):
    timestamp: str          # ISO 8601
    agent: str
    tokens_in: int
    tokens_out: int
    findings_count: int
    duration_ms: int
```

## Tool Contracts

### `read_file_chunk(chunk_id: str) -> str`
- Returns the file chunk text for the given id
- On error: returns `{"error": "chunk not found: <id>"}` — never raises

### `read_ruleset(ruleset_id: str) -> dict`
- Reads ruleset via ReviewContext wrapper
- Generated schema exposes only `ruleset_id: str` — no wrapper params
- On error: returns `{"error": "ruleset not found: <id>"}` — never raises

### `merge_findings(security: list[Finding], tests: list[Finding], style: list[Finding]) -> MergedReport`
- Agent-as-a-tool from MergeAgent
- Deduplicates, sorts by severity

## Boundary Schemas

| Boundary | Direction | Schema |
|----------|-----------|--------|
| CLI → Intake | path: `str` | — |
| Intake → Reviewers | chunk: `str`, context: `ReviewContext` | — |
| Reviewer → Merge | `list[Finding]` | Pydantic |
| Merge → UI/report | `MergedReport` | Pydantic |
| Security → Remediation | `Finding` (handoff) | Pydantic |
| Remediation → UI | `RemediationProposal` | Pydantic |
| Any run → ledger | `RunLedgerEntry` | JSONL |

## Execution Controls

- **Output guardrail**: secret scanner on every agent's `output_guardrails`
- **Turn ceiling**: `max_turns` set on every `Runner.run`
- **Model override**: per-run `model="gpt-4o-mini"` (or `gpt-4o` for merge/remediation)
- **Error handling**: all tools wrapped; return error objects

## Observability

- **Lifecycle hooks**: capture token usage per run
- **ledger.jsonl**: custom runner appends `RunLedgerEntry` per run
- **OpenTelemetry**: one trace, three reviewer spans + merge span; slowest = max duration
- **Chainlit**: streams findings via `asyncio.as_completed`; shows trace summary
