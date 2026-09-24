# Code Review Desk

Paste a unified diff → three AI reviewers (security, tests, style) run in parallel → one merged report. Built with the OpenAI Agents SDK and Chainlit.

## What it does

1. Reads a unified diff (paste or file path)
2. Splits it into per-file chunks before any model call
3. Runs **Security**, **Test**, and **Style** reviewers concurrently via `asyncio.gather`
4. Merges findings through a **Merge** agent (`as_tool`)
5. On a critical security finding, **hands off** to a **Remediation** agent for a patch proposal
6. Refuses output that looks like a secret (output guardrail)
7. Streams findings into the UI, appends to `ledger.jsonl`, and exports one OpenTelemetry trace

## Quick start

### Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (or pip)
- OpenAI API key

### Setup

```powershell
cd "Code Review Desk"

# Create venv and install deps
uv sync --extra dev --extra runtime

# Configure key
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

### Run

```powershell
.venv\Scripts\python.exe -m chainlit run app.py
```

Open **http://localhost:8000**

### Run tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

## How to use

### Input

Any one of:

| Input | Example |
|-------|---------|
| Paste a unified diff | `diff --git a/app.py b/app.py` … |
| Path to a `.diff` / `.patch` file | `C:\...\change.diff` |
| Any local file path containing a diff | `D:\project\fix.patch` |

Empty or malformed diffs return a message, not a traceback.

### Slash commands (optional)

| Command | Effect |
|---------|--------|
| `/repo <name>` | Set `ReviewContext.repo` |
| `/lang <language>` | Set `ReviewContext.language` |
| `/ruleset <id>` | Set `ReviewContext.ruleset_id` (e.g. `py-standard`) |
| `/strictness normal\|strict` | Normal or strict review mode |

Settings stick for the browser session.

### Sample paste

```diff
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 import os
+API_KEY = "sk-test1234567890abcdef"
 print("hi")
```

## Getting a diff from git

```bash
# Uncommitted changes
git diff > review.diff

# Last commit
git diff HEAD~1 > review.diff

# Between branches
git diff main..feature-branch > review.diff
```

Then type the file path into the chat, or copy-paste `git diff` output directly.

## Architecture

```
Diff → split by file
         │
         ▼
   asyncio.gather
   ┌─────────────┬─────────────┬─────────────┐
   │ Security    │ Test        │ Style       │  (clones of one base)
   └──────┬──────┴──────┬──────┴──────┬──────┘
          │             │             │
          └─────────────┼─────────────┘
                        ▼
              Desk host + Merge.as_tool
                        │
            (critical) handoff → Remediation
                        ▼
         Guardrail → UI stream + ledger + trace
```

| Component | Role |
|-----------|------|
| `SecurityReviewer` | Vulnerabilities, secrets, auth issues |
| `TestReviewer` | Coverage gaps, weak assertions |
| `StyleReviewer` | Naming, structure, dead code |
| `Desk` + `Merge` | Deduplicate + order findings (`as_tool`) |
| `Remediation` | Patch proposal on critical finding (`handoff`) |

**Model:** `gpt-4o-mini` on each agent (no global default client).

## Project layout

```
Code Review Desk/
├── app.py                 # Chainlit UI entrypoint
├── desk/
│   ├── agents.py          # Agent builders (reviewers, merge, remediation)
│   ├── pipeline.py        # Concurrent review pipeline
│   ├── prompts.py         # Dynamic instructions (FR-4)
│   ├── context.py         # ReviewContext dataclass (FR-2)
│   ├── findings.py        # Finding / MergedReport / RemediationProposal
│   ├── diff_reader.py     # Diff intake + per-file split (FR-1)
│   ├── guardrails.py      # Secret output guardrail (FR-8)
│   ├── merge.py           # Dedup + severity ordering
│   ├── hooks.py           # Latency/token metrics (FR-10)
│   ├── ledger.py          # ledger.jsonl custom runner (FR-11)
│   └── otel.py            # OpenTelemetry trace export (FR-13)
├── rulesets/
│   └── py-standard.md     # Ruleset read by read_ruleset tool
├── tests/                 # FR-1..13 + NFR tests
├── constitution.md        # Phase 0 — rules
├── spec.md                # Phase 0 — behavior (FR/NFR)
├── plan.md                # Phase 0 — architecture
├── tasks.md               # Phase 0 — ordered tasks
├── pyproject.toml
└── .env.example
```

## Requirements covered

| ID | Requirement |
|----|-------------|
| FR-1 | Diff split before model call |
| FR-2 | ReviewContext via tools, not prompts |
| FR-3 | `list[Finding]` structured output |
| FR-4 | Per-run dynamic instructions |
| FR-5 | Three cloned reviewers, concurrent |
| FR-6 | Merge as tool, remediation by handoff |
| FR-7 | Run-level model override |
| FR-8 | Output guardrail for secrets |
| FR-9 | Required tools, failing tools, max_turns |
| FR-10 | Latency/token hooks (run + one agent) |
| FR-11 | `ledger.jsonl` one line per run |
| FR-12 | Chainlit streaming UI |
| FR-13 | One review, one exported trace |
| NFR-1..5 | Secrets, cost, observability, failure, provenance |

Full text: [spec.md](spec.md) · [plan.md](plan.md) · [tasks.md](tasks.md) · [constitution.md](constitution.md)

## Side effects

| File | When |
|------|------|
| `ledger.jsonl` | Appends one line per agent run |
| `otel_trace.jsonl` | Appends spans when tracing is enabled |
| Temp `*.diff` | If pasted text is not a valid path/diff |

`.env`, `ledger.jsonl`, `otel_trace.jsonl`, and caches are gitignored.

## License

Course / assignment project.
